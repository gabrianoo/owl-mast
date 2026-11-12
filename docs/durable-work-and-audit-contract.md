# Durable work and audit envelope contract (v1)

Owner: OM-01.03 (issue #22), the single owning story in the architecture spine's Deferred table for "durable-work and audit envelope versions, transaction adapter and common outcome/retry semantics". Feature producers (E06, E11, E15, E16, …) enqueue work and record mutations only through the Java API types below. `DurableWorkContractTest` fails the build when this document and the types drift apart.

Binding decisions: AD-3 (tenant scope on every record), AD-4 (fail-closed recheck), AD-5 (scoped reactive transactions), AD-6 (atomic business/work/audit commit, at-least-once processing). Owner decisions from the 2026-11-08 sprint change proposal: audit-publication intent plus idempotent publisher keyed on event id; fail-closed dispatch recheck until OM-02.04; live Kubernetes pod replacement proof belongs to OM-18.02.

## Versioning and compatibility rule

Both contracts carry an integer version: `WorkItemContract.VERSION = 1` and `AuditEnvelopeContract.VERSION = 1`. Every stored work item (`contract_version`) and audit record (`envelope_version`) records the version it was written with.

- Within a version, a field or payload key may only be **added**, and only with a meaning that an absent value preserves (readers treat absence exactly as they treated records written before the addition). Readers ignore fields they do not know.
- **Removing, renaming or changing the meaning** of a field, a vocabulary constant or a payload key requires a new version. The owner publishes the new version here first, keeps reading every version ever written, and migrates in-flight work items deliberately before producers emit the new version.
- Vocabularies (`WorkStatus`, `EffectOutcome`, `DispatchDecision`, `ActorKind`, `AuditOutcome`) may gain constants within a version only if every existing reader maps an unknown constant to an explicit unknown/unsupported state rather than failing or guessing.

## Durable work-item contract (`com.aisquad.owlmast.jobs.api`)

### Owner API

| Type | Role |
| --- | --- |
| `WorkEnqueue.enqueue(EnqueueRequest)` | Inserts a work record for the tenant bound in the caller's `ScopeContext`. Joins the caller's active scoped transaction, so a business row and its work record commit or roll back together; rejects a different scope; fails closed without one. A work type that no handler in this build registers is rejected with `IllegalArgumentException` before the transaction opens: claims take only registered types, so such an item would stay `PENDING` for good, never terminal and never listed. Every instance of one build registers the same handlers, so this never refuses work a peer of the same build could run. |
| `EnqueueRequest(type, payload, correlationId, maxAttempts)` | `WorkType`, identifier-only payload (`Map<String,String>`, at most 32 entries, keys ≤ 64 and values ≤ 512 characters), optional correlation id (≤ 256, the same bound as the audit envelope's correlation id: an audited mutation's correlation id becomes its publish item's), optional per-item `maxAttempts` (≥ 1; absent means the configured `max-attempts`, so requests written before the field was added keep their meaning). `withMaxAttempts(n)` sets it. |
| `WorkHandler` | A Spring bean per `WorkType`: `registration()` and `handle(WorkItem) → Mono<EffectOutcome>`. Invoked inside a scoped transaction bound to the item's tenant under the backend service identity; its database writes commit with the item's completion. An error signal is a failed attempt; a `NonRetryableWorkException` is a terminal one. |
| `NonRetryableWorkException` | A handler's signal that no retry can cure the failure (a payload that cannot name its subject, a referenced record that no longer exists). The item becomes terminal `FAILED` on the current attempt, whatever its remaining budget, and appears in the failure listing. Only the class chain is persisted. |
| `WorkRegistration(type, tenantInternalSystemWork)` | `tenantInternalSystemWork = true` declares the handler changes only the tenant's own records under the service identity with no disclosure or external effect on anyone's behalf. |
| `WorkItem` | Handler view: `id`, `tenant`, `type`, `contractVersion`, `payload`, `attempt`, `maxAttempts`, `correlationId`, plus the derived `idempotencyKey()` = `owlmast-work:<id>`, identical on every attempt and reclaim. |
| `EffectOutcome` | `Applied(reference)` or `Uncertain(reference)`; the reference is an identifier (idempotency key or remote id), never content. |
| `DispatchAuthorization.recheck(item, registration)` | Port rechecked before every dispatch. Decisions: `ALLOW`, `DENY`, `UNDECIDED`. Supplied by the access module in OM-02.04 as a Spring bean; the default until then allows only `tenantInternalSystemWork` registrations and denies all others. Errors count as `UNDECIDED`. |
| `FailedWorkQuery.listTerminalFailures(limit)` | Operator listing for the bound tenant: `FailedWorkItem(id, tenant, type, status, attemptCount, safeReason, finishedAt)`; never payloads. |
| `WorkItemContract` | The constants in this document. |

### Service identity

Processors run as `ServiceIdentity.BACKEND` (`service:owl-mast-backend`, platform.scope). `ServiceIdentity.backendScope(tenant)` is the `ScopeContext` bound for every claim, dispatch, completion and publication of that tenant's items. Audit records produced under it use actor kind `SERVICE`.

### Lifecycle and semantics

Statuses (`WorkStatus`): `PENDING` → `RUNNING` → `SUCCEEDED` | `FAILED` | `DENIED` | `OUTCOME_UNCERTAIN`; the last four are terminal.

- **Tenant discovery** returns at most 100 tenants per wake-up, ordered by each tenant's longest-waiting due item (then tenant id), so tenants beyond the limit are reached as the earlier ones drain instead of starving behind lower tenant ids. A failure while processing one tenant is logged and does not stop the others.
- **Claiming** is tenant-scoped and bounded: per wake-up, per tenant, at most `claim-batch-size` items that are `PENDING` and due, or `RUNNING` with an expired lease, that still have attempts left, and **that this instance can run**: a work type with a registered handler and a `contract_version` no newer than the one this build reads. During a rolling deploy an instance without the new handler, or without the new contract version, leaves such items (and tenants that only have such items) for an instance that has them, consuming no attempt. A claimed row that cannot be decoded into a `WorkItem` (a payload that is not a map of strings, a tightened bound, a hand-edited row) is failed terminally with reason `undecodable-work-item` under the lease the claim took; it uses one slot of the batch without ending it, so poison rows neither stall their tenant's queue nor delay the valid items behind them to a later wake-up. Items are leased **one at a time, each immediately before its dispatch**, so a lease never runs while the item waits behind others. Each claim increments `attempt`, sets a new lease token and `lease_expires_at = clock_timestamp() + lease-duration`. `FOR UPDATE SKIP LOCKED` guarantees one current lease holder per item.
- **Completion and failure writes are fenced** by the lease token and require an unexpired lease measured with the wall clock (`clock_timestamp()`, not the transaction-start `now()`): a write from an expired or reclaimed lease, including one whose lease expired while the handler was still running, is rejected and changes nothing, and the handler's database effects in that transaction roll back with it. A lease token exists only while the item is `RUNNING` (the database checks this); `lease_owner` and `lease_expires_at` stay as a record of the last lease. There is no heartbeat in v1: a handler still running at the handler deadline (`handler-deadline`, default nine tenths of `lease-duration`, `RetryPolicy.handlerDeadline()`, always shorter than the lease) is cancelled, its transaction rolls back and the attempt fails with reason `handler-deadline-exceeded` under the lease that claimed it, then is retried with backoff. The deadline is measured from the claim, so the authorization recheck and the handler share one budget. The recheck may use at most half of it (`RetryPolicy.recheckDeadline()`): a recheck that has not allowed the dispatch by then counts as `UNDECIDED`, so the handler always starts with at least half of its deadline and a slow deciding component is never charged to the item as a failed attempt. A deadline overrun is an ordinary failed attempt: like a process that dies mid-effect, it is retried, which is why external effects must be idempotent by `WorkItem.idempotencyKey()` or reported as `Uncertain` (processing is at least once). Every statement of the handler's transaction is also bounded on the server (`statement_timeout`, halfway between the deadline and the lease expiry, `RetryPolicy.statementTimeout()`), so a handler blocked inside the database is cancelled by PostgreSQL in time for the rollback. Dispatch is serial, so these bounds are what keep one hung handler from stalling every other item and tenant.
- **Effects are at least once**: deduplicate through `WorkItem.idempotencyKey()` or return `Uncertain`, which parks the item in `OUTCOME_UNCERTAIN` for reconciliation (OM-16.05). The database refuses `SUCCEEDED` without an `APPLIED` effect outcome.
- **Retries**: a failed attempt persists `attempt_count`, the exception class chain (`SafeFailure`, never messages) as `failure_reason`, and `next_attempt_at = now + min(backoff-base × 2^(attempt−1), backoff-cap)`. After `max-attempts` (or the item's own `maxAttempts`), or at once when the handler signals `NonRetryableWorkException`, the item is terminal `FAILED`. A completion clears `failure_reason`, so a `SUCCEEDED` or `OUTCOME_UNCERTAIN` row never carries the reason of an earlier attempt. A handler that completes without an `EffectOutcome` fails the attempt with reason `handler-returned-no-effect-outcome`. An item with its own `maxAttempts` above the configured one logs a warning on every failed attempt from the configured limit on, so a publish item that keeps failing is visible to operators although it never becomes terminal. A `RUNNING` item whose lease expires after its last permitted attempt becomes `FAILED` with reason `lease-expired-attempts-exhausted`.
- **Authorization recheck**: `DENY` → terminal `DENIED` with reason `authorization-denied`; `UNDECIDED` (an undecided answer, an error, or no `ALLOW` within the recheck's half of the deadline) → the item is **released** with reason `authorization-undecided`: back to `PENDING`, the attempt **not** counted, so an outage of the deciding component never exhausts an item's budget. Consecutive releases are counted (`release_count`) and back off like failed attempts, `min(backoff-base × 2^(releases−1), backoff-cap)`, so a long outage is not a fixed-rate loop; an attempt that runs the handler resets the count. A released item never becomes terminal, so from `max-attempts` consecutive releases on, every further release logs a warning naming the item. The handler is never invoked in either case.
- **Bounded steps**: every processor step outside the handler (tenant discovery, the exhausted-lease sweep, the claim, and the release, deny and failure writes) is bounded by `lease-duration` (`RetryPolicy.stepTimeout()`), on the client and, inside its transaction, on the server (`statement_timeout`). The handler's transaction as a whole (begin, handler, completion write, commit) is likewise cut off on the client when the lease that claimed the item runs out, because no write of that dispatch can count after it. A statement or commit stalled by the database or the network fails its step (and at most that tenant's batch for this wake-up) instead of stopping every later wake-up. Socket-level settings (TCP keepalive, connect timeout) belong to the connection URL the deployment supplies.
- **Graceful shutdown**: stopping the application ends the wake-up in flight and cancels its dispatch. The item is then **given back** at once and uncounted with reason `dispatch-cancelled` (back to `PENDING`, due immediately, `release_count` unchanged) in a write fenced by the lease that dispatch holds, and the shutdown waits (at most 10 s) for that write before connections close. A rolling deploy therefore neither leaves an item `RUNNING` until its lease expires nor costs it an attempt. A process that dies without a shutdown (a kill, a crash) is still recovered by lease expiry, which counts the attempt. The handler's own transaction rolls back with the cancellation; external effects stay at least once.
- **Lease owner**: `lease_owner` is `owl-mast-backend/<instance>/<random>`. The instance part is `owlmast.jobs.instance-id`, by default the `HOSTNAME` environment variable or the local host name (the pod name on Kubernetes), reduced to `[A-Za-z0-9._-]` and 128 characters; the random part tells two starts of one instance apart. The value is logged once at startup, so a lease can be traced to the pod that held it.
- **Wake-ups** come only from in-process Spring scheduling (`jobs.adapter.scheduling.WorkScheduler`, fixed delay `poll-interval`, first run after `initial-delay`, by default immediately at startup). Every `owlmast.jobs.*` setting, the two scheduler delays included, is bound and validated by `JobsProperties` at start-up. No broker, external scheduler, workflow engine or separate worker service exists or is permitted.

### Defaults (`owlmast.jobs.*`)

| Property | Default | Constant |
| --- | --- | --- |
| `max-attempts` | 5 | `DEFAULT_MAX_ATTEMPTS` |
| `backoff-base` | PT1S | `DEFAULT_BACKOFF_BASE` |
| `backoff-cap` | PT5M | `DEFAULT_BACKOFF_CAP` |
| `lease-duration` | PT30S | `DEFAULT_LEASE_DURATION` |
| `claim-batch-size` | 10 | `DEFAULT_CLAIM_BATCH_SIZE` |
| `poll-interval` | PT1S | `DEFAULT_POLL_INTERVAL` |
| `initial-delay` | PT0S | `DEFAULT_INITIAL_DELAY` |
| `handler-deadline` | nine tenths of `lease-duration` | (derived; must be shorter than the lease) |
| `instance-id` | `HOSTNAME`, else the local host name | (names the instance in `lease_owner`) |

### Storage

`jobs.work_item` (migration `V002__jobs_infrastructure.sql`), owned and written by the jobs module alone. Every statement filters on the tenant bound to the transaction (`current_setting('owlmast.tenant_id')`), never on a parameter.

## Audit envelope contract (`com.aisquad.owlmast.audit.api`)

### Owner API

| Type | Role |
| --- | --- |
| `AuditedMutations.execute(AuditedMutation<T>) → Mono<AuditedResult<T>>` | Performs a covered mutation. Success: business change, `SUCCEEDED` publication intent and the `audit.publish` work item commit in one scoped transaction. Failure: the business transaction rolls back and a `FAILED` record (or `DENIED` for `OperationDeniedException`) commits in a separate `REQUIRES_NEW` transaction, then the error is re-signalled. A rollback of an enclosing transaction after a successful call is observed and recorded as `FAILED` (see Durability path). |
| `AuditedMutation(actor, project, objectType, objectId, action, correlationId, business)` | Envelope fields known up front; `business: ScopeContext → Mono<MutationOutcome<T>>` performs the change. |
| `MutationOutcome(value, objectId, objectVersion)` | What the business function reports on success. When the mutation named its object up front (`AuditedMutation.changing`), the outcome must report the same object id; a different one fails the mutation (`OutcomeObjectMismatchException`), which rolls back and is recorded as `FAILED` on the requested object, so a success is never filed under an object nobody asked to change. |
| `AuditHistoryQuery` | Internal, tenant-scoped reads: `find(eventId)`, `listByObject(type, id, limit)`, `countUnpublishedIntents()`. E16 builds authorized projections on it. |
| `AuditEnvelopeContract` | `VERSION`, `PUBLISH_WORK_TYPE = audit.publish`, `PAYLOAD_EVENT_ID = eventId`, `PUBLISH_MAX_ATTEMPTS = Integer.MAX_VALUE`, `MAX_FIELD_LENGTH = 256` (bound of every textual field). |

A **covered mutation** is any mutation made through `AuditedMutations`; later feature stories declare which of their mutations are covered.

### Envelope fields (`AuditEnvelope`, v1)

| Field | Java component | Column | Meaning |
| --- | --- | --- | --- |
| Envelope version | `envelopeVersion` | `envelope_version` | Version the record was written with. |
| Event id | `eventId` | `event_id` | UUID; exactly one history row per event id. |
| Actor | `actor` | `actor_kind`, `actor_id` | `AuditActor(kind, id)`; `ActorKind` ∈ `HUMAN`, `AGENT`, `SERVICE`, `SYSTEM`; absent id is an explicit Unknown (`NULL`). The id follows the rule of every textual field (non-blank, single line, at most `MAX_FIELD_LENGTH`) and is rejected otherwise when the actor is built. |
| Tenant | `tenant` | `tenant_id` | Bound transaction tenant, never a request value. |
| Project | `project` | `project_id` | Explicit Unknown (`NULL`) until OM-02.02 supplies project identity. |
| Object type | `objectType` | `object_type` | Producer-owned object class. |
| Object id | `objectId` | `object_id` | Unknown (`NULL`) when the attempt never produced an object. |
| Object version | `objectVersion` | `object_version` | Version after the change; Unknown for unsuccessful attempts. |
| Action | `action` | `action` | Producer-owned action code. |
| Outcome | `outcome` | `outcome` | `AuditOutcome` ∈ `REQUESTED`, `SUCCEEDED`, `FAILED`, `DENIED`, `UNRESOLVED` (OM-16.01's requested/successful/failed/unresolved plus the AD-6 denied path). |
| Reason | `reason` | `reason` | Module-produced safe text only: exception class chain or a denial reason code, normalised before the write to a non-blank single line of at most `MAX_FIELD_LENGTH` characters (`unknown-failure` when the diagnostics could not name one), so every stored row reads back. |
| Occurred time | `occurredAt` | `occurred_at` | `timestamptz`, from the application clock when the attempt started. |
| Recorded time | `recordedAt` | `recorded_at` | `timestamptz`, database time of the write. |
| Correlation id | `correlationId` | `correlation_id` | Ties the record to the request and the publish work item; at most 256 characters, validated before any business work runs (`WorkItemContract.MAX_CORRELATION_ID_LENGTH`). |

There is **no free-form payload field**, by design. All fields are bounded single-line identifiers or codes (≤ 256 characters); a secret in the business input has no place to land. Producers must never put request values into `reason`, `action` or `objectType`.

### Durability path

1. `audit.publication_intent` row (`SUCCEEDED`) and an `audit.publish` work item commit with the business change. The publish item is enqueued with `maxAttempts = PUBLISH_MAX_ATTEMPTS`, so a fault of any length delays publication (retries back off up to `backoff-cap`) but never abandons the intent: once recovery completes, no committed covered mutation lacks its history record. The one exception is a publish item that cannot name an intent at all (no or malformed event id, or no intent for the bound tenant; intent and item commit together, so this needs a hand-edited row): it fails terminally as `NonRetryableWorkException` and appears in the failure listing instead of retrying for good.
2. The publisher handler (`AuditPublishHandler`, tenant-internal) copies the intent into `audit.event` keyed on `event_id` and sets `published_at`, inside the processor's scoped transaction. Repeating it inserts nothing new; recovery after a crash before publication yields exactly one history row. If the separate path already wrote an unsuccessful row for the event (the commit's outcome was reported unknown although it landed: `UNRESOLVED` from the completion observer, or `FAILED` with the transaction exception's class chain from the error path when the observer's write failed), publication replaces that row with the intent, because the intent exists only when the business transaction committed. This correction is the one way a history row changes; an existing `SUCCEEDED` row is never touched.
3. `FAILED`, `DENIED` and `UNRESOLVED` outcomes are written straight into `audit.event` by the separate outcome path; no intent is needed because no business write exists to be atomic with.
4. A synchronization is registered on the physical transaction before the business function runs, and the error path also attempts the write, so a non-committing end is recorded for the same event id through the separate path whenever one of those outcome writes commits: a business error or denial keeps its exception class chain or denial code; a cancelled subscription records `FAILED` with reason `execution-cancelled`; a rollback of an enclosing transaction after this call succeeded records `FAILED` with reason `enclosing-transaction-rolled-back` (the success intent is gone with the rollback); a commit of this call's own transaction that was refused and rolled back (for example by a deferred constraint) records `FAILED` with reason `commit-rolled-back`, the refusing exception's class chain going to the log; an unknown completion status records `UNRESOLVED` with reason `transaction-completion-unknown`; a business function that completes without a `MutationOutcome` fails with `MissingMutationOutcomeException`, rolls back and records `FAILED` with that class name. An `UNRESOLVED` row with no intent means the commit did not land; reconciling such rows belongs to OM-16.05. Because the commit can land although `execute` signals a transaction exception, callers must make retries of a covered mutation idempotent. The execution counts as recorded only after an outcome write has committed, so a cancelled or failed outcome write leaves the completion observer free to write it; the history insert is idempotent on the event id, so an execution never leaves more than one outcome record. Each outcome write is bounded by `owlmast.audit.outcome-write-deadline` (default `PT5S`): failing mutations cluster during database trouble, exactly when this write is slow, so a write that passes the deadline is cancelled and treated as failed, and the caller's error is held for at most one deadline per writer (the completion observer and the error path) instead of for the length of the stall. If every outcome write fails (for example, the database is unavailable), only a safe log line remains; it names the event id and correlation id, so the row can be reconstructed by hand.
5. The separate outcome transaction takes a second connection while the failing transaction still holds its own (the completion observer runs before Spring releases it). The backend uses unpooled R2DBC connections, so this costs one extra PostgreSQL connection per concurrent failure and fails fast at the server's connection limit rather than waiting. Introducing a connection pool must keep that headroom, for example a separate pool for the outcome path, or concurrent failures could wait on each other for connections.

### Storage

`audit.publication_intent` and `audit.event` (migration `V003__audit_infrastructure.sql`), owned and written by the audit module alone, tenant-filtered like the jobs table.

## Out of scope for v1

Project identity (OM-02.02), the real dispatch authorization port (OM-02.04), lease heartbeats/renewal, reconciliation of `OUTCOME_UNCERTAIN` items (OM-16.05), operator-facing audit queries and coverage reporting (OM-16.01), and live Kubernetes pod-replacement qualification (OM-18.02).
