-- OM-01.03: audit-owned infrastructure (AD-6). Only the audit module reads or writes it.
-- Envelope v1 columns; there is deliberately no free-form payload column (AC3).
-- actor_id / project_id NULL means an explicit Unknown (project identity arrives with OM-02.02).

CREATE SCHEMA IF NOT EXISTS audit;

-- A durable audit-publication intent commits in the business transaction of a covered successful
-- mutation; the idempotent publisher (work type audit.publish) copies it into audit.event.
CREATE TABLE audit.publication_intent (
    event_id         uuid        PRIMARY KEY,
    envelope_version smallint    NOT NULL CHECK (envelope_version >= 1),
    tenant_id        text        NOT NULL,
    actor_kind       text        NOT NULL CHECK (actor_kind IN ('HUMAN', 'AGENT', 'SERVICE', 'SYSTEM')),
    actor_id         text,
    project_id       text,
    object_type      text        NOT NULL,
    object_id        text,
    object_version   text,
    action           text        NOT NULL,
    outcome          text        NOT NULL
        CHECK (outcome IN ('REQUESTED', 'SUCCEEDED', 'FAILED', 'DENIED', 'UNRESOLVED')),
    reason           text,
    occurred_at      timestamptz NOT NULL,
    recorded_at      timestamptz NOT NULL DEFAULT now(),
    correlation_id   text        NOT NULL,
    published_at     timestamptz
);

CREATE INDEX publication_intent_pending_idx
    ON audit.publication_intent (tenant_id, recorded_at)
    WHERE published_at IS NULL;

-- Audit-owned history. Exactly one row per event id (AC4); failed and denied outcomes are written
-- here directly through the separate outcome path (AC3).
CREATE TABLE audit.event (
    event_id         uuid        PRIMARY KEY,
    envelope_version smallint    NOT NULL CHECK (envelope_version >= 1),
    tenant_id        text        NOT NULL,
    actor_kind       text        NOT NULL CHECK (actor_kind IN ('HUMAN', 'AGENT', 'SERVICE', 'SYSTEM')),
    actor_id         text,
    project_id       text,
    object_type      text        NOT NULL,
    object_id        text,
    object_version   text,
    action           text        NOT NULL,
    outcome          text        NOT NULL
        CHECK (outcome IN ('REQUESTED', 'SUCCEEDED', 'FAILED', 'DENIED', 'UNRESOLVED')),
    reason           text,
    occurred_at      timestamptz NOT NULL,
    recorded_at      timestamptz NOT NULL,
    correlation_id   text        NOT NULL,
    published_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX event_object_idx
    ON audit.event (tenant_id, object_type, object_id, occurred_at DESC);

CREATE INDEX event_correlation_idx
    ON audit.event (tenant_id, correlation_id);
