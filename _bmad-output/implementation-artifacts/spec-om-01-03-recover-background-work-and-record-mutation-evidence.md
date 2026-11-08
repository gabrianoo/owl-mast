---
title: 'OM-01.03 — Recover accepted background work and record mutation evidence'
type: 'feature'
created: '2026-11-08'
status: 'in-progress'
route: 'dispatch'
review_loop_iteration: 1
baseline_commit: 'eff1971d1d731ba352e001ba078235a950338142'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
  - '{project-root}/docs/engineering-conventions.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The backend has scope-bound transactions but no durable work, lease recovery or audit evidence: a mutation that needs follow-up work or an audit record would lose both when the single instance restarts, and later feature modules have no contract to enqueue work or record mutations against.

**Approach:** Add two owner modules, `jobs` (PostgreSQL-backed durable work with tenant-scoped claims, fencing-token leases, persisted retry/backoff and terminal outcomes, woken only by in-process Spring scheduling) and `audit` (versioned audit envelope, audit-publication intent committed with the business transaction, idempotent publisher keyed on event id, separate-transaction failed/denied outcome path, internal history query), publish their versioned contracts as Java API types plus a contract document, and prove AC1–AC9 with Testcontainers PostgreSQL and a test-owned fixture module. Tracking: GitHub issue #22 (OM-01.03), epic #1 (E01); ENG-01 run `run-20261108-e01`, authorization `run-20261108-e01:OM-01.03:1`.

## Boundaries & Constraints

**Always:** Preserve AD-1–AD-16, issue #22 AC1–AC9 and task IDs OM-01.03-T1..T4 verbatim. Only `jobs` and `audit` create schema objects (`V002`, `V003`); the fixture module owns its own test table. Every jobs/audit row carries `tenant_id` and every claim, completion, publication and query filters on the tenant bound to the transaction (`current_setting('owlmast.tenant_id')`), never on a caller-supplied value alone. Completion and failure writes require the current lease token; processing is at least once with an idempotency key derived from the work item or an explicit `OUTCOME_UNCERTAIN` state. The audit envelope has no free-form payload field; reasons are module-produced safe text (`SafeFailure`), never caller input. Authorization recheck at dispatch fails closed: only handlers registered as tenant-internal system work run until OM-02.04. Processors are woken by `@Scheduled` in one adapter only; Testcontainers uses the pinned VectorChord image. Owner decisions from the 2026-11-08 sprint change proposal are binding: intent + idempotent publisher design, fail-closed default recheck, live pod replacement deferred to OM-18.02.

**Never:** Merge, tick issue checkboxes, change Project Status, close or comment on #22; edit `automation/policy.toml`, `automation/examples/*`, `automation/unattended/*`; add a broker, external scheduler, workflow engine or worker service; add project identity (OM-02.02) or the real authorization port (OM-02.04); claim Kubernetes recovery support; put secrets in audit rows, work records or logs; weaken or skip tests when something is unavailable.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Atomic enqueue (AC1) | fixture writes its row and enqueues in one scoped transaction | row and work item both committed | error before or after enqueue → neither exists |
| Concurrent claims (AC2) | two processors, N pending items | each item claimed once, one lease holder, processed once | N/A |
| Stale completion (AC2) | holder's lease expired/reclaimed, writes success or failure | write rejected, 0 rows changed, item state owned by new holder | `StaleLeaseException` |
| Duplicate effect (AC2) | reclaimed item re-runs handler with external effect | effect applied once via `WorkItem.idempotencyKey()` or item `OUTCOME_UNCERTAIN` | no `SUCCEEDED` without recorded effect outcome |
| Covered mutation (AC3) | `AuditedMutations.execute` succeeds | intent with all envelope fields committed in the same transaction, publish work item enqueued | N/A |
| Rollback / denial (AC3) | business fails or raises `OperationDeniedException` | FAILED/DENIED history record in a separate transaction; no business row, no SUCCEEDED record | business error propagates |
| Secret planted (AC3) | secret string in business input and in the failure message | absent from every audit/jobs column and from captured logs | N/A |
| Fault before publication (AC4) | process stops after commit, or publish insert fails (trigger) | recovery twice → exactly one `audit.event` for the event id; zero pending intents | attempt failure recorded safely |
| Retry exhaustion (AC5) | handler always fails, max attempts 3 | attempts, capped backoff `next_attempt_at` and safe reason persisted; terminal `FAILED` listed without payload | N/A |
| Restart (AC6) | pending, leased-running and unpublished intents; new context starts | all finished by scheduling alone | N/A |
| Recheck denies / undecided (AC7) | handler not tenant-internal, or port undecided | handler not invoked; `DENIED` terminal, or `BLOCKED` reason with backoff | fail closed |
| Two tenants (AC8) | items and intents for tenant A and B | claims under A return only A; audit query under A returns only A | N/A |

</frozen-after-approval>

## Code Map

- `backend/src/main/java/com/aisquad/owlmast/platform/persistence/ScopedTransactions.java` -- reuse for every scoped write; build a `REQUIRES_NEW` instance for the separate outcome transaction (pattern in `ScopedTransactionsIT.requiresNew`).
- `backend/src/main/java/com/aisquad/owlmast/platform/scope/*` -- `ScopeContext`, `TenantId`, `PrincipalId`; add the backend service identity and `OperationDeniedException`.
- `backend/src/main/java/com/aisquad/owlmast/platform/diagnostics/SafeFailure.java` -- the only source of failure reasons.
- `backend/src/main/java/com/aisquad/owlmast/bootstrap/adapter/persistence/R2dbcSchemaBaselineRepository.java` -- `DatabaseClient` adapter style to mirror.
- `backend/src/main/java/com/aisquad/owlmast/access/adapter/identity/{IdentityProperties,IdentityConfiguration}.java` -- `@ConfigurationProperties` record and adapter configuration pattern.
- `backend/src/test/java/com/aisquad/owlmast/architecture/FeatureModuleRules.java` -- cross-feature access only through `*.api`; `api`/`domain` free of Spring; add scheduling/broker rules in a new test, not here.
- `backend/src/testFixtures/java/com/aisquad/owlmast/testing/*` -- `ContainersConfiguration`, `StubIdentityConfiguration`, `OwlMastPostgres` for every IT.
- `backend/src/test/java/com/aisquad/owlmast/bootstrap/adapter/health/SchemaBaselineHealthIndicatorTest.java` -- `OutputCaptureExtension` log-capture pattern.
- `backend/gradle.lockfile` -- Jackson 3 (`tools.jackson`) and Awaitility are already locked; no new dependency.
- `docs/engineering-conventions.md`, `docs/development.md`, `README.md` -- document the new modules and link the contract document.

## Tasks & Acceptance

**Execution:**
- [x] `docs/durable-work-and-audit-contract.md` -- versioned work-item v1 and audit-envelope v1 contracts, vocabularies, defaults, compatibility rule, owner APIs, service identity, recheck port -- T1.
- [x] `backend/src/main/java/com/aisquad/owlmast/platform/scope/ServiceIdentity.java`, `platform/authorization/OperationDeniedException.java` -- backend service principal for processors; denial signal -- T1.
- [x] `backend/src/main/java/com/aisquad/owlmast/jobs/api/*` -- `WorkType`, `WorkItem`, `EnqueueRequest`, `WorkEnqueue`, `WorkHandler`, `WorkRegistration`, `EffectOutcome`, `DispatchAuthorization`/`DispatchDecision`, `FailedWorkQuery`/`FailedWorkItem`, `WorkStatus`, `WorkItemContract` -- T1/AC9.
- [x] `backend/src/main/resources/db/migration/V002__jobs_infrastructure.sql`, `V003__audit_infrastructure.sql` -- jobs- and audit-owned tables only -- T2.
- [x] `backend/src/main/java/com/aisquad/owlmast/jobs/{domain,application,port,adapter}` -- retry policy and backoff, enqueue in the caller's scoped transaction, tenant-scoped bounded claim with `FOR UPDATE SKIP LOCKED`, lease expiry/reclaim, fenced completion, dispatch recheck, failure listing, `@Scheduled` reactive wakeup, properties -- T2/T3.
- [x] `backend/src/main/java/com/aisquad/owlmast/audit/{api,domain,application,port,adapter}` -- envelope types, `AuditedMutations`, intent/history store, publish handler (tenant-internal), separate-transaction outcome recorder, `AuditHistoryQuery` -- T1/T2.
- [x] `backend/src/test/java/com/aisquad/owlmast/{jobs,audit,architecture}` -- backoff/policy/registry/fail-closed/envelope unit tests, contract-document compatibility tests, lockfile broker check, scheduling-location rule -- AC5/AC7/AC9.
- [x] `backend/src/integrationTest/java/com/aisquad/owlmast/fixtures/notes/*` -- test-owned fixture module (own table, handlers, effect store, DB probe) -- T4.
- [x] `backend/src/integrationTest/java/com/aisquad/owlmast/{jobs,audit}/*IT.java` -- AC1–AC5, AC7, AC8 against Testcontainers; `ProcessRestartRecoveryIT` for AC6 with two sequential contexts -- T4.
- [x] `docs/engineering-conventions.md`, `docs/development.md`, `README.md`, `application.yaml` -- module docs, `owlmast.jobs.*` defaults -- T1/T3.

**Acceptance Criteria:** AC1–AC9 as stated in issue #22 and `epic-01.md` for OM-01.03; verified by the commands below.

## Implementation Notes

- 2026-11-08: Executed directly by the unattended implementer (coordinator authorization `run-20261108-e01:OM-01.03:1` stands in for the interactive checkpoints, as in OM-01.01). No Open Questions remained: the sprint change proposal already fixed the three owner decisions.
- Design: audit publication reuses the jobs machinery (`audit.publish`, tenant-internal) so intents inherit claims, leases, retries and restart recovery; `audit.publication_intent` carries the envelope, `audit.event` is inserted `ON CONFLICT DO NOTHING`. Failed/denied outcomes go straight into the history through a `REQUIRES_NEW` scoped transaction. Handler and completion share one lease-fenced transaction; a stale lease rolls the handler's database effects back. Every jobs/audit statement filters on `current_setting('owlmast.tenant_id')`, never a parameter. The default dispatch recheck is `TenantInternalOnlyDispatchAuthorization`; the real port (OM-02.04) replaces it by registering a `DispatchAuthorization` bean.
- Surprises: (1) a PostgreSQL CHECK passes when its expression is NULL, so the "succeeded requires effect outcome" constraints use `coalesce`. (2) `DatabaseClient` joins the transaction found in the Reactor context, so the fixture's "another process expires the lease" injection must `contextWrite(ctx -> Context.empty())` to run on its own connection. (3) `SpringApplicationBuilder.properties(...)` ranks below `application.yaml`; the restart test passes settings as command-line arguments. (4) The OM-01.01 migration test asserted that only bootstrap objects exist; it now lists the three story-owned infrastructure tables. (5) Spring `@Scheduled` string delays accept ISO-8601 only, so `owlmast.jobs.*` durations are written as `PT…` values.
- Scope kept out: lease heartbeats, reconciliation of `OUTCOME_UNCERTAIN` (OM-16.05), project identity (OM-02.02), operator audit queries (OM-16.01), live pod replacement (OM-18.02). The fixture module and its table exist only in `src/integrationTest`.
- Repair round 1 (2026-11-08, authorization `run-20261108-e01:OM-01.03:3`): lease fence and lease arithmetic use `clock_timestamp()`; `WorkProcessor.processTenant` claims one item per short transaction right before dispatching it (batch size bounds the wake-up only); `AuditedMutationService` registers a `TransactionSynchronization` after writing the intent and, on `STATUS_ROLLED_BACK`/unknown, records `FAILED`/`UNRESOLVED` detached from the completed transaction, with an at-most-once guard shared with the error path. `AuditOutcome.separateOutcomePath()` now includes `UNRESOLVED`.
- Verified 2026-11-08 on the committed tree: `./gradlew build --console=plain` (65 unit + 52 integration tests, 0 failures, 0 skipped; Spotless and Error Prone clean), `scripts/verify-quality-gates.sh` (5/5 gates fail on injected violations), `python3 -m unittest discover -s automation/tests -t .` (339 tests OK). Matrix audit: every I/O row is covered by a named test in `DurableWorkIT`, `AuditedMutationIT` or `ProcessRestartRecoveryIT`, all of which ran in the build.

## Spec Change Log

## Review Triage Log

- Independent review of e08165bc3267d82d98badcc8c8d4970bbe745665 (round 1): CHANGES REQUESTED. P1 lease fence used transaction-start `now()`, so a handler finishing after expiry could still commit — confirmed, fixed (`clock_timestamp()` fence; `aLeaseThatExpiresNaturallyWhileTheHandlerRunsCannotCommit`). P1 enclosing rollback after a successful `execute` lost the failed outcome — confirmed, fixed (transaction synchronization records `FAILED`/`UNRESOLVED` through the separate path; `anEnclosingRollbackAfterASuccessfulCallStillRecordsAFailedOutcome`). P2 batch claiming leased items while they waited — confirmed, fixed (lease per item immediately before dispatch; `itemsWaitingInABatchDoNotConsumeTheirLeases`).

## Design Notes

- Audit publication is itself a work item (`audit.publish`, tenant-internal) so intents inherit claims, leases, retries and restart recovery from `jobs`; the intent row (`audit.publication_intent`) carries the envelope and the history row (`audit.event`) is inserted `ON CONFLICT (event_id) DO NOTHING`, which makes repeated recovery idempotent. Failed/denied outcomes are written straight into the history in a `REQUIRES_NEW` scoped transaction because no business write exists to be atomic with.
- The handler and its completion write share one scoped transaction: a stale lease rolls back database effects along with the rejected completion; external effects use `WorkItem.idempotencyKey()` or return `EffectOutcome.uncertain`.
- Tenant discovery for the processor is an unscoped identifier-only query; every item is then claimed and processed inside `ScopeContext.service(tenant)` so the SQL tenant filter is the bound setting, not a parameter.

## Verification

**Commands:**
- `./gradlew build --console=plain` -- expected: unit, ArchUnit, contract and integration suites pass, Spotless and Error Prone clean.
- `scripts/verify-quality-gates.sh` -- expected: every injected violation still fails its gate.
- `python3 -m unittest discover -s automation/tests -t .` -- expected: automation suite unchanged and passing.
