---
date: 2026-11-08
trigger_story: OM-01.03
issue: https://github.com/gabrianoo/owl-mast/issues/22
mode: incremental
scope: minor
status: approved
---

# Sprint Change Proposal — OM-01.03 acceptance criteria

## 1. Issue summary

A read-only readiness check of OM-01.03 (*Recover accepted background work and record mutation evidence*, issue #22) on 2026-11-08, against `main` at `0192c30`, found the story not dispatchable as written:

- The `plan` dry run returned `awaiting-owner-acceptance`: Project Status is Backlog.
- AC2 combines four separate claims and leaves "bounded" and "explicitly reconciled" undefined.
- AC3 leaves "covered mutation", "both times" and the secret-payload test undefined. It requires a project identity the code does not have yet (`ScopeContext` holds only tenant and principal). Its rule that a failed attempt survives the business rollback appears only in T2.
- AC4 is meaningful only if the implementer chooses the intent design that AC3 leaves open. It also refers to an audit history whose read API does not exist until OM-16.01.
- Five pieces of required behaviour had tasks but no AC:
  - recovery after a restart, which is the story's own stated goal
  - the authorization recheck that AD-6 requires
  - tenant-scoped claims (AD-3)
  - operator-visible failures (FR-3, NFR-6)
  - the versioned contract the architecture's Deferred table assigns to this story
- The FR-3 and UX-DR51 rows in the `epics.md` coverage table omit E01, but `VALIDATION.md` maps both to OM-01.03.

Issue type: the requirements were under-specified. Nothing was found broken in implementation, and no OM-01.03 code exists yet.

## 2. Impact analysis

- **Epic impact:** E01 remains completable as planned. No epic is added, removed, resequenced or redefined.
- **Story impact:** OM-01.03 only. AC1–AC4 are rewritten and AC5–AC9 added. T1–T4 keep their IDs and are reworded. The expected counts (19 epics, 85 stories, 340 tasks) used by `automation.unattended verify-mapping` stay valid.
- **Downstream stories:**
  - E06, E11, E15 and E16, which consume this contract, get a firmer contract and need no edits.
  - OM-16.01 AC1 already expects the envelope fields specified here.
  - OM-18.02 AC2 and T3 already cover pod termination and stale-lease recovery, so moving the live pod-replacement proof there requires no edit to OM-18.02.
  - Project identity comes from OM-02.02 and the real authorization port from OM-02.04. Neither becomes a prerequisite: the envelope records project as explicit Unknown, and the recheck port starts fail-closed.
- **PRD:** no conflict. MVP unaffected.
- **Architecture:** no conflict. AD-6 permits "audit record or durable audit-publication intent"; this story selects the intent design. AD-3, AD-4 and AD-6 are now each covered by an acceptance criterion.
- **UX:** no change. `EXPERIENCE.md` (audit event contract) remains the source for the envelope fields.
- **Technical:** Testcontainers PostgreSQL only. No live cluster or external service is needed, so an unattended run remains feasible.

## 3. Recommended approach

**Direct adjustment.** Effort and risk are both low, and the schedule is unchanged.

- **Rollback:** not viable, because there is nothing to roll back.
- **MVP review:** unnecessary.

Owner decisions recorded during this workflow:

| Decision | Choice |
|---|---|
| Where the live pod-replacement proof lives | Deferred to OM-18.02. OM-01.03 proves process restart with Testcontainers and claims no Kubernetes recovery support. |
| Default authorization recheck before E02 | Fail closed. Only handlers registered as tenant-internal system work may run. OM-02.04 replaces the port. |
| Audit durability design | Durable audit-publication intent plus an idempotent publisher job, keyed on event id. |

## 4. Detailed change proposals

### 4.1 Story — `epics/owl-mast-2026-11-05/epic-01.md`, OM-01.03, Acceptance criteria

All four existing ACs are replaced and AC5–AC9 are appended.

OLD:

```markdown
- **AC1: Given** a feature mutation requires follow-up work, **when** its database transaction commits or rolls back, **then** the required work record and mutation succeed or fail together.
- **AC2: Given** two processors overlap or one loses its lease, **when** work is claimed and completed, **then** only current ownership may commit completion, retries are bounded/persisted and repeated external effects are idempotent or explicitly reconciled.
- **AC3: Given** a covered successful mutation, **when** its business transaction commits, **then** the audit record or a durable audit-publication intent commits atomically with it and carries actor, tenant/project, object/version, action/outcome and both times without secret payloads; denied and failed attempts are recorded through a separate safe outcome path.
- **AC4: Given** a crash after a successful mutation commits but before audit publication completes, **when** recovery runs, **then** the committed audit intent is published idempotently and the successful mutation cannot disappear from the permitted audit history.
```

NEW:

```markdown
- **AC1: Given** a test-owned fixture module that changes its own business row and enqueues follow-up work through the jobs owner API in one scoped transaction, **when** that transaction commits, or rolls back for any reason including an error raised after the enqueue call, **then** the business row and the work record both exist after commit and neither exists after rollback.
- **AC2: Given** pending work, two processors claiming concurrently, or a lease that expires before its holder finishes, **when** work is claimed, reclaimed and completed, **then** each item has at most one current lease holder; a completion or failure write from a holder whose lease expired or was reclaimed is rejected and changes nothing; a repeated external effect after reclaim is either applied once through an idempotency key derived from the work item or leaves the item in an explicit outcome-uncertain state awaiting reconciliation; and no item is marked succeeded without a recorded effect outcome.
- **AC3: Given** a covered mutation (any mutation made through the audited-mutation API; later feature stories declare which of their mutations are covered), **when** its business transaction commits, **then** a durable audit-publication intent commits in the same transaction carrying envelope version, event id, actor kind (human, agent, service or system) and actor id or explicit Unknown, tenant, project or explicit Unknown until OM-02.02 supplies project identity, object type/id/version, action, outcome, occurred time and recorded time with timezone, and correlation id. The envelope has no free-form payload field, and a secret value planted in the business input appears in no audit row, work record or log line. **Given** a business transaction that rolls back or an operation that is denied, **then** a failed or denied outcome record commits in a separate transaction, survives the rollback, and creates no business row and no succeeded record.
- **AC4: Given** a fault injected after a covered mutation's transaction commits and before its audit intent is published, **when** recovery runs, including running twice, **then** exactly one audit record exists for that event id in the audit-owned history, readable through the audit module's internal query API, and once recovery completes no committed covered mutation lacks its audit record.
- **AC5: Given** a handler that fails, **when** it is retried, **then** attempt count, next-attempt time from a capped backoff and a safe failure reason persist across restarts; after the configured maximum attempts (default stated in the contract) the item enters a terminal failed state that an authorized operator can list with tenant, work type, attempt count and safe reason, but without payload contents.
- **AC6: Given** non-terminal work and unpublished audit intents when the application process stops, **when** a new application instance starts against the same database, **then** all of them are claimed and finished without manual action. This story proves process restart with Testcontainers only; live Kubernetes pod-replacement qualification belongs to OM-18.02 (AC2, T3), and this story claims no Kubernetes recovery support.
- **AC7: Given** the authorization recheck port at dispatch, **when** it denies or cannot decide, **then** the handler is not invoked and the item records a safe denied or blocked outcome; until OM-02.04 supplies the real port, the default allows only handlers registered as tenant-internal system work and denies all others.
- **AC8: Given** work and audit records for two synthetic tenants, **when** processors claim and the audit query runs under one tenant's scope, **then** each record is processed only under its own tenant's scope and none is returned or completed under the other's.
- **AC9: Given** a later feature module, **when** it enqueues work or records audit, **then** it can do so only through the published, versioned work-item and audit-envelope contracts (Java API types plus a contract document with a compatibility rule for added fields and versions), enforced by module-rule and compatibility tests; processors are woken only by in-process Spring scheduling, with no external scheduler, broker or worker service.
```

Rationale:

- **AC1:** names the fixture module, because no feature module exists yet.
- **AC2:** separates claims and effects from retries, and turns "explicitly reconciled" into a recorded state.
- **AC3:** defines "covered", the times, the secret rule and the project field before E02, and moves the rollback-survival rule up from T2.
- **AC4:** makes "crash" an injected fault and replaces "permitted audit history", which belongs to E16, with the audit module's internal query API.
- **AC5–AC9:** give acceptance criteria to required behaviour that previously had tasks but none (AR-11, FR-3, NFR-6, AD-3, AD-6, and the contract this story owns in the architecture's Deferred table).

### 4.2 Story — `epic-01.md`, OM-01.03, Tasks (IDs unchanged)

OLD:

```markdown
- [ ] **OM-01.03-T1** Define the durable-work and minimal audit-envelope contracts, owner APIs and versioning rules consumed by later modules.
- [ ] **OM-01.03-T2** Implement only the work/audit infrastructure tables, atomic business-change/work/audit-intent commit through module APIs and reactive transaction integration; keep failed-attempt audit independent of rolled-back business writes.
- [ ] **OM-01.03-T3** Implement bounded claiming, lease recovery, retry/backoff, failure visibility and authorization recheck hooks; schedule wakeups without an external job service.
- [ ] **OM-01.03-T4** Exercise rollback-before-enqueue, crash-after-commit-before-audit-publication, failed-attempt recording, stale-owner completion, concurrent claims and duplicate effect recovery.
```

NEW:

```markdown
- [ ] **OM-01.03-T1** Define and document the versioned durable-work and audit-envelope contracts (AC3 fields; outcome and actor-kind vocabularies aligned with OM-16.01; a compatibility rule for added fields and versions), the audited-mutation and enqueue owner APIs, the backend service identity used by processors, and the authorization recheck port with its fail-closed default.
- [ ] **OM-01.03-T2** Implement only the jobs- and audit-owned infrastructure tables; atomic business-change/work/audit-intent commit through module APIs and reactive transaction integration; the idempotent audit-intent publisher; and failed/denied outcome recording in a separate transaction independent of rolled-back business writes.
- [ ] **OM-01.03-T3** Implement tenant-scoped bounded claiming, lease expiry and reclaim, persisted retry/backoff with terminal failure, an operator failure listing without payloads and the dispatch-time authorization recheck; wake processors with in-process Spring scheduling only.
- [ ] **OM-01.03-T4** Exercise, with Testcontainers PostgreSQL and a test-owned fixture module: rollback before and after enqueue, fault-injected crash after commit before audit publication with repeated recovery, failed and denied attempt recording, secret non-disclosure, stale-owner completion, concurrent claims, duplicate effect recovery, retry exhaustion, process-restart recovery, fail-closed authorization and two-tenant isolation.
```

Rationale: every task now maps to at least one AC and every AC to at least one task (see 5.3). Keeping the IDs preserves the 340-task mapping.

### 4.3 Task index — `epics/owl-mast-2026-11-05/TASKS.md`, OM-01.03 entry

Mirror the four new task texts from 4.2 in the existing `- **OM-01.03-Tn** — …` format. IDs and the prerequisite line are unchanged.

### 4.4 Plan — `epics.md`, Requirements coverage map

```markdown
OLD: | FR-3 | E05, E06, E09, E16, E17 |
NEW: | FR-3 | E01, E05, E06, E09, E16, E17 |

OLD: | UX-DR51 | E16 |
NEW: | UX-DR51 | E01, E16 |
```

Rationale: OM-01.03 already cites both requirements, and `VALIDATION.md` already maps them to it.

### 4.5 Tracking — GitHub issue #22 (after merge, separate approval to post)

Reconcile the body with the merged specification: replace the acceptance criteria and task text, and add a link to the merge commit's specification. Status and progress remain untouched, as the tracking contract requires (`docs/engineering-tracking.md`).

No PRD, architecture or UX edits are proposed.

## 5. Implementation handoff

### 5.1 Scope classification

**Minor.** These are text-only edits to three planning files. No backlog reorganization is needed.

### 5.2 Responsibilities

| Role | Responsibility |
|---|---|
| Developer agent | Apply 4.1–4.4 on a branch and open a PR. Run `python3 -m automation.unattended verify-mapping` and `python3 -m unittest discover -s automation/tests -t .`. |
| Owner (Hedwig) | Review and merge the PR. Approve posting the #22 body update (4.5). Move #22 from Backlog to Ready. Separately approve the run's `activation.toml` if OM-01.03 is to run unattended. |

### 5.3 AC-to-task trace after the change

| AC | Tasks |
|---|---|
| AC1 atomic enqueue | T2, T4 |
| AC2 claims/leases/effects | T3, T4 |
| AC3 audit intent and envelope | T1, T2, T4 |
| AC4 audit crash recovery | T2, T4 |
| AC5 retries and terminal failure | T3, T4 |
| AC6 restart recovery | T3, T4 |
| AC7 authorization recheck | T1, T3, T4 |
| AC8 tenant isolation | T3, T4 |
| AC9 versioned contract, in-process wakeups | T1, T3 |

### 5.4 Success criteria

- `epic-01.md`, `TASKS.md` and `epics.md` contain the approved text, and nothing else in them changes.
- `verify-mapping` still reports 19 epics, 85 stories and 340 tasks, with no TASKS.md ID mismatch.
- Issue #22 matches the merged specification.
- A fresh `plan` run reports OM-01.03 as dispatchable once the owner sets Ready.
