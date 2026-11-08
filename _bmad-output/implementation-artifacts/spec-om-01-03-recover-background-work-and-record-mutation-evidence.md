---
title: 'OM-01.03 — Recover accepted background work and record mutation evidence'
type: 'feature'
created: '2026-11-08'
status: 'in-review'
route: 'dispatch'
review_loop_iteration: 2
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

### Review Findings

Code review of PR #111 round 3 (`e3a6083..233d94a`, 2026-11-08; layers: blind-hunter, edge-case-hunter, verification-gap, acceptance-auditor).

- [x] [Review][Patch] An error-path outcome write that fails (an error, not a cancel) and is then handed to the completion observer has no test; adding `markOutcomeRecorded()` to `onErrorResume` would pass every test [backend/src/integrationTest/java/com/aisquad/owlmast/audit/AuditedMutationIT.java]
- [x] [Review][Patch] The cancellation regression does not prove the hung write rolled back: both writers carry the same reason, so a committed first write would also pass; mark the hung write's record distinctly and assert the marker is absent [backend/src/integrationTest/java/com/aisquad/owlmast/audit/AuditedMutationIT.java]
- [x] [Review][Patch] The class Javadoc's first paragraph still promises unconditionally that "Anything else ends with exactly one outcome record", contradicting the corrected guarantee below it [backend/src/main/java/com/aisquad/owlmast/audit/application/AuditedMutationService.java:33]
- [x] [Review][Defer] An `UNRESOLVED` outcome for a transaction whose commit actually landed makes the later `SUCCEEDED` publication a silent no-op while `published_at` is still set [backend/src/main/java/com/aisquad/owlmast/audit/adapter/persistence/R2dbcAuditStore.java:51] — deferred: pre-existing (`publish` conflict clause predates round 3); settle with a forced STATUS_UNKNOWN-on-commit test or in OM-16.05.

Rejected:
- false — the observer's own outcome write can be cancelled, leaving no writer: the observer runs inside Spring's commit/rollback, which `Flux.usingWhen` (Reactor 3.8.8) runs as a cleanup subscription that downstream cancel does not reach; `aCancellationAfterTheBusinessWriteStillRecordsAFailedOutcome` relies on it.
- false — `aCommittedOutcomeStopsEveryLaterWriterForThatExecution` is racy: in both paths the first write completes before the second writer subscribes (rollback precedes error propagation; the error path's write precedes outer completion).
- false — round-3 test counts don't add up: round 2 (e3a6083) ran 67 unit + 58 IT; +3 IT gives 61; the 65/52 line is round 1's.
- false — PR body correction (d) unverified: the PR #111 description now reads "whenever one of its outcome writes commits".
- low — overlapping writers can disagree (FAILED vs UNRESOLVED), first commit wins: overlap needs a STATUS_UNKNOWN concurrent with an in-flight error-path write; not demonstrated, fix adds pinning state.
- low — a losing writer logs "recorded as" for a no-op insert: only in cancellation-after-commit races; fix changes the port signature.
- low — deferred-work entry wording/fields; no concurrent both-commit test (PostgreSQL unique-index semantics); hand-copied wiring in `auditedOver`/`singleItemProcessor`; raw SQL suffix in `insert`; `dispose()` not in `finally`; no timeout on the hanging `Mono.never()`; commit-without-success-signal not covered end to end.
- spec edit — round-3 authorization id and `review_loop_iteration` bump: fix edits the spec under review.

## Implementation Notes

- 2026-11-08: Executed directly by the unattended implementer (coordinator authorization `run-20261108-e01:OM-01.03:1` stands in for the interactive checkpoints, as in OM-01.01). No Open Questions remained: the sprint change proposal already fixed the three owner decisions.
- Design: audit publication reuses the jobs machinery (`audit.publish`, tenant-internal) so intents inherit claims, leases, retries and restart recovery; `audit.publication_intent` carries the envelope, `audit.event` is inserted `ON CONFLICT DO NOTHING`. Failed/denied outcomes go straight into the history through a `REQUIRES_NEW` scoped transaction. Handler and completion share one lease-fenced transaction; a stale lease rolls the handler's database effects back. Every jobs/audit statement filters on `current_setting('owlmast.tenant_id')`, never a parameter. The default dispatch recheck is `TenantInternalOnlyDispatchAuthorization`; the real port (OM-02.04) replaces it by registering a `DispatchAuthorization` bean.
- Surprises: (1) a PostgreSQL CHECK passes when its expression is NULL, so the "succeeded requires effect outcome" constraints use `coalesce`. (2) `DatabaseClient` joins the transaction found in the Reactor context, so the fixture's "another process expires the lease" injection must `contextWrite(ctx -> Context.empty())` to run on its own connection. (3) `SpringApplicationBuilder.properties(...)` ranks below `application.yaml`; the restart test passes settings as command-line arguments. (4) The OM-01.01 migration test asserted that only bootstrap objects exist; it now lists the three story-owned infrastructure tables. (5) Spring `@Scheduled` string delays accept ISO-8601 only, so `owlmast.jobs.*` durations are written as `PT…` values.
- Scope kept out: lease heartbeats, reconciliation of `OUTCOME_UNCERTAIN` (OM-16.05), project identity (OM-02.02), operator audit queries (OM-16.01), live pod replacement (OM-18.02). The fixture module and its table exist only in `src/integrationTest`.
- Repair round 1 (2026-11-08, authorization `run-20261108-e01:OM-01.03:3`): lease fence and lease arithmetic use `clock_timestamp()`; `WorkProcessor.processTenant` claims one item per short transaction right before dispatching it (batch size bounds the wake-up only); `AuditedMutationService` registers a `TransactionSynchronization` after writing the intent and, on `STATUS_ROLLED_BACK`/unknown, records `FAILED`/`UNRESOLVED` detached from the completed transaction, with an at-most-once guard shared with the error path. `AuditOutcome.separateOutcomePath()` now includes `UNRESOLVED`.
- Repair round 2 (2026-11-08, authorization `run-20261108-e01:OM-01.03:5`, final): the completion synchronization is registered before the business function runs and records the original error or denial (class chain or code), `execution-cancelled` on a cancelled subscription, `enclosing-transaction-rolled-back` or `UNRESOLVED` otherwise, one record per execution. Correlation ids share one bound (`WorkItemContract.MAX_CORRELATION_ID_LENGTH = 256`) validated in `AuditedMutation` before any business work. `ProcessRestartRecoveryIT` now launches two separate JVMs (`fixtures/restart/RestartFixtureProcess`) from the test classpath against one Testcontainers database: the first seeds work through the owner APIs, claims an item under a lease its hanging handler never releases, and is SIGKILLed; the second finishes everything by scheduling alone; the test observes the database over JDBC. Lease tests use latches and single-item processors instead of sleeps.
- Repair round 3 (2026-11-08, interactive `/bmad-build` repair of e3a60833a00961bd3f7bd46b19155cc66450a21e, scope limited to the two findings below; earlier fixes stay untouched). (a) `AuditedMutationService`: the per-attempt guard means "an outcome record has committed", not "a writer started". `recordOutcome` skips only when a committed record is already known; it marks the attempt recorded in the success signal of the `REQUIRES_NEW` scoped transaction (after commit), so a cancelled or failed outcome write leaves the completion observer (and any later path) free to record. Two writers may then overlap; `R2dbcAuditStore.recordOutcome` inserts `ON CONFLICT (event_id) DO NOTHING`, so the `audit.event` primary key keeps it to exactly one durable row per execution even if a commit lands without its success signal. Class/port Javadoc states this guarantee. (b) Regression `AuditedMutationIT.aCancellationDuringTheSeparateOutcomeWriteStillLeavesOneFailedOutcome`: a test-built `AuditedMutationService` (same wiring as `AuditConfiguration`, REQUIRES_NEW separate transactions) over an `AuditStore` decorator whose first `recordOutcome` performs the real insert, counts down a "pending" latch and then never completes (counting down a "cancelled" latch on cancel); later calls delegate. A business error inside an enclosing scoped transaction reaches the error path, the test waits on the pending latch, disposes the subscription, asserts the cancelled latch, then observes exactly one `FAILED` `audit.event` row with the business error's safe reason, no business row, no intent and no work item. Latches only; the final DB observation may use Awaitility polling as the existing cancellation test does. (c) `recoveryAfterAFaultBeforePublicationYieldsExactlyOneHistoryRecord` runs its initial faulted attempt with a single-item processor (`RetryPolicy` with claim batch size 1, as in `DurableWorkIT.singleItemProcessor`), so exactly one attempt never depends on the 100 ms backoff. (d) The PR #111 description's "every non-committing end" wording is corrected to the exact guarantee.
- Verified 2026-11-08 on the committed tree: `./gradlew build --console=plain` (65 unit + 52 integration tests, 0 failures, 0 skipped; Spotless and Error Prone clean), `scripts/verify-quality-gates.sh` (5/5 gates fail on injected violations), `python3 -m unittest discover -s automation/tests -t .` (339 tests OK). Matrix audit: every I/O row is covered by a named test in `DurableWorkIT`, `AuditedMutationIT` or `ProcessRestartRecoveryIT`, all of which ran in the build.
- Verified round 3 (2026-11-08) on the working tree before commit: `./gradlew build --console=plain` (67 unit + 61 integration tests, 0 failures, 0 skipped; Spotless and Error Prone clean), `scripts/verify-quality-gates.sh` (all gates fail on injected violations), `python3 -m unittest discover -s automation/tests -t .` (339 OK), `AuditedMutationIT` alone twice with `--rerun` (17/17 each). The new regression test fails on the pre-repair service ("Expected size: 1 but was: 0"); removing the conflict clause or the guard's skip fails the two added tests. Review-layer coverage additions: `aRepeatedOutcomeWriteForOneEventIdKeepsTheFirstCommittedRow`, `aCommittedOutcomeStopsEveryLaterWriterForThatExecution`. Local note: this WSL host's clock steps back about 0.6 s every ~10 s, which can make an enqueue-then-claim test see a not-yet-due item; CI runners are unaffected.

## Spec Change Log

## Review Triage Log

- Independent review of e3a60833a00961bd3f7bd46b19155cc66450a21e (round 3, interactive repair): CHANGES REQUESTED. P1 (AC3) `AuditedMutationService.java:122` claimed the at-most-once guard before the `REQUIRES_NEW` outcome write committed; inside an enclosing transaction the business error reaches `onErrorResume` first, and a cancellation during that write rolled it back while the observer saw the claimed guard and skipped, leaving no durable failed outcome — confirmed by reading the code path, fixed (guard set only after commit, idempotent outcome insert; `aCancellationDuringTheSeparateOutcomeWriteStillLeavesOneFailedOutcome`). P2 `AuditedMutationIT.java:359` initial faulted publication attempt used the ten-item processor with 100 ms backoff while requiring exactly one attempt — confirmed, fixed (single-item processor for that attempt).
  - Build review of the round-3 diff (blind, edge-case, verification-gap layers), triage:
    - medium, patch: the regression test did not prove the observer took over the write — fixed (delegate call count asserted as 2).
    - medium, patch: `ON CONFLICT (event_id) DO NOTHING` on the outcome insert had no test — fixed (store-level double-commit test, one row, first reason kept).
    - low, patch: the committed-outcome guard's skip branch was hidden by the idempotent insert — fixed (counting store asserts one write for plain and enclosing failures).
    - medium (unverified), defer: an `UNRESOLVED` outcome for a transaction whose commit actually landed blocks the later `SUCCEEDED` publication via `ON CONFLICT`; publication's conflict clause predates this round and reconciliation is OM-16.05.
    - low, reject: a losing overlapping writer logs "recorded as" although its insert was a no-op (reachable only in cancellation races; the fix changes the port signature).
    - low, reject: overlapping writers may differ in reason (both derive from the same captured failure in every demonstrated path).
    - false, reject: the faulted-publication test no longer uses `runOnce` for its first attempt (requested by the R3 review; recovery still uses `runOnce`).
    - low, reject: `auditedOver` duplicates `AuditConfiguration` wiring; the raw SQL suffix in `insert` is stringly typed; check-then-act may open a second blocked connection (intended overlap).
    - reject, pre-existing: total outcome-write failure leaves only a log line (documented since round 1).
    - maybe-false low, reject: a cancelled sole writer with no registered synchronization leaves no log; an observer blocked forever on a lock whose rollback never arrives (registration always precedes business work; PostgreSQL releases locks on rollback or disconnect).

- Independent review of 5c4996b53a99f7f238f5196a299b0b00905ab871 (round 2, final): CHANGES REQUESTED. P1 cancellation after the business write bypassed both the error path and the late-registered observer — confirmed, fixed (observer registered first; `aCancellationAfterTheBusinessWriteStillRecordsAFailedOutcome`). P2 correlation-id bound mismatch (256 vs 128) let an accepted id roll back after business work — confirmed, fixed (shared 256 bound, up-front validation; `correlationIdBoundaryMatchesTheAuditEnvelope`, `correlationIdsAreValidatedUpFrontAgainstTheSharedBound`, `aCorrelationIdAtTheSharedBoundTravelsThroughIntentWorkItemAndHistory`). P2 restart proof ran in one JVM with a manufactured lease — confirmed, fixed (two child JVMs, natural lease, SIGKILL; `aSeparateProcessFinishesTheWorkAndIntentsAKilledProcessLeftBehind`). P2 timing-dependent lease tests — confirmed, fixed (latches, DB-observed expiry, single-item processors; `aLeaseThatExpiresNaturallyWhileTheHandlerRunsCannotCommit`, `itemsWaitingInABatchStayUnclaimedUntilTheirOwnDispatch`).

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
