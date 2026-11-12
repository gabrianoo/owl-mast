-- OM-01.03: jobs-owned durable work infrastructure (AD-6). Only the jobs module reads or writes it.
-- Tenant scope is enforced by the module's statements through the transaction-bound setting
-- owlmast.tenant_id; the constraints below make the contract's invariants hold in the database too.

CREATE SCHEMA IF NOT EXISTS jobs;

CREATE TABLE jobs.work_item (
    id               uuid        PRIMARY KEY,
    tenant_id        text        NOT NULL,
    work_type        text        NOT NULL,
    contract_version smallint    NOT NULL CHECK (contract_version >= 1),
    -- Identifiers only (work-item contract v1); never content or secrets.
    payload          jsonb       NOT NULL DEFAULT '{}'::jsonb,
    status           text        NOT NULL
        CHECK (status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'DENIED', 'OUTCOME_UNCERTAIN')),
    attempt_count    integer     NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    max_attempts     integer     NOT NULL CHECK (max_attempts >= 1),
    -- Consecutive uncounted give-backs after an undecided authorization recheck; drives their
    -- backoff and is reset by the next attempt that runs the handler or ends the item.
    release_count    integer     NOT NULL DEFAULT 0 CHECK (release_count >= 0),
    next_attempt_at  timestamptz NOT NULL,
    lease_owner      text,
    lease_token      uuid,
    lease_expires_at timestamptz,
    -- Exception class chain or a fixed reason code; never a message, payload or secret.
    failure_reason   text,
    effect_outcome   text        CHECK (effect_outcome IN ('APPLIED', 'UNCERTAIN')),
    effect_reference text,
    enqueued_by      text        NOT NULL,
    correlation_id   text,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    finished_at      timestamptz,
    -- AC2: no item is marked succeeded without a recorded effect outcome.
    CONSTRAINT work_item_succeeded_requires_applied_effect
        CHECK (status <> 'SUCCEEDED' OR coalesce(effect_outcome, '') = 'APPLIED'),
    CONSTRAINT work_item_uncertain_requires_uncertain_effect
        CHECK (status <> 'OUTCOME_UNCERTAIN' OR coalesce(effect_outcome, '') = 'UNCERTAIN'),
    CONSTRAINT work_item_running_requires_lease
        CHECK (status <> 'RUNNING' OR (lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)),
    -- AC2: the fencing token exists only while the item is RUNNING; lease_owner and
    -- lease_expires_at remain as a record of the last lease.
    CONSTRAINT work_item_lease_token_only_while_running
        CHECK (status = 'RUNNING' OR lease_token IS NULL),
    CONSTRAINT work_item_terminal_is_finished
        CHECK (status IN ('PENDING', 'RUNNING') OR finished_at IS NOT NULL)
);

CREATE INDEX work_item_due_idx
    ON jobs.work_item (tenant_id, next_attempt_at)
    WHERE status = 'PENDING';

CREATE INDEX work_item_lease_idx
    ON jobs.work_item (tenant_id, lease_expires_at)
    WHERE status = 'RUNNING';

CREATE INDEX work_item_terminal_idx
    ON jobs.work_item (tenant_id, finished_at DESC)
    WHERE status IN ('FAILED', 'DENIED', 'OUTCOME_UNCERTAIN');
