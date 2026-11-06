---
epic: E11
status: planned
review_status: pending-owner-review
implementation_status: not-started
---

# Epic E11 — Publish and revoke company-safe learning

Maintainers operate automatic/manual/disabled promotion and withdraw exact versions with permission-preserving derivative handling. Automatic promotion is the preferred mode after policy and audience configuration; A-2 withdrawal propagation and A-4 disabled-mode behavior are adopted; this draft does not authorize live publication.

**Epic prerequisites:** E03, E04

<a id="om-11-01"></a>

### OM-11.01 — Configure project promotion policy and permitted audiences

As a project knowledge maintainer, I want explicit publication modes and audience policy, so that reusable learning can be shared only under the project's authorized rules.

**Requirements:** FR-9, FR-12, FR-17; NFR-1, NFR-2, NFR-6; AR-07, AR-09, AR-10, AR-17; UX-DR23, UX-DR25, UX-DR34, UX-DR49.

**Depends on:** E03, E04

**Acceptance criteria:**
- Given an authorized project maintainer and permitted-use owner, when policy is saved, then automatic/manual/disabled mode, allowed audience, checks and policy version are recorded with actor/time and no company-wide right is inferred from project membership or ownership.
- Given automatic mode is enabled, when existing candidates are considered, then they are evaluated under the current policy and explicit audience; activation does not publish unevaluated candidates or claim that every candidate qualifies.
- Given an unauthorized or stale policy update, when save is attempted, then the operation is denied or reports a version conflict with no silent overwrite, and permitted unsaved input remains available to the user.
- Given adopted A-4, when promotion is disabled, then new automatic and manual publications cannot commit, including work already queued or in flight, while existing published versions remain retrievable under current permissions and lifecycle rules. Disabling promotion does not withdraw existing versions or break lineage; the permitted-use input owner must be assigned separately.

**Tasks:**
- [ ] **OM-11.01-T1** Implement project promotion policy/audience versions and maintainer/permitted-use ownership bindings behind current authorization.
- [ ] **OM-11.01-T2** Implement concurrency-safe policy save and mode-change events that invalidate work carrying the prior policy revision.
- [ ] **OM-11.01-T3** Add mode-specific explanations and validation, including automatic candidate evaluation and adopted A-4: disabled mode stops new publication while existing eligible publications remain available until separately withdrawn, superseded or otherwise ineligible.
- [ ] **OM-11.01-T4** Verify unauthorized policy changes, missing permitted-use ownership, stale saves, automatic/manual/disabled transitions and queued/in-flight publication rejection after disabling; existing eligible publications and lineage remain readable with safe audit evidence.

<a id="om-11-02"></a>

### OM-11.02 — Evaluate an exact company-safe publication candidate

As a maintainer, I want a versioned proposed publication checked against permitted use and source evidence, so that reusable content can stand alone without exposing a customer's restricted material.

**Requirements:** FR-9, FR-12, FR-17, FR-18; NFR-1, NFR-2, NFR-6; AR-06, AR-07, AR-10, AR-11, AR-17; UX-DR20, UX-DR23, UX-DR48, UX-DR49.

**Depends on:** OM-11.01

**Acceptance criteria:**
- Given a project knowledge version and configured audience/policy, when a publication candidate is evaluated, then checks bind to its exact proposed content/version, origin version and policy version and cover provenance, reusable applicability, permitted audience/use, restricted details/secrets, contradiction and withdrawal.
- Given candidate text is sanitized for wider use, when the candidate is stored, then it has a separate publication identity without a source-project key; restricted origin references and evaluation details remain visible only to separately authorized readers.
- Given a failed or uncertain check, when evaluation completes, then the source remains project-scoped with an authorized reason; confidence scores and human override cannot bypass missing source/use permission.
- Given content, origin eligibility, audience or policy changes, when a prior evaluation is reused, then it is rejected as stale and the changed candidate requires evaluation again.

**Tasks:**
- [ ] **OM-11.02-T1** Add only publication-candidate/version, restricted lineage and check-result records required for company-safe publication.
- [ ] **OM-11.02-T2** Implement durable evaluation jobs with current policy/content bindings and explicit passed/failed/uncertain check evidence; qualify any optional Spring AI processing destination before use.
- [ ] **OM-11.02-T3** Produce separate company-reader and maintainer projections, excluding source keys, private links, named actors or detailed reasons without their own authorization.
- [ ] **OM-11.02-T4** Verify sensitive-content failures, unresolved contradiction, missing permitted-use approval, changed sanitized text and hidden-origin disclosure cases.

<a id="om-11-03"></a>

### OM-11.03 — Publish safely in automatic and manual modes under races

As a maintainer, I want qualifying versions published exactly once under the current mode, so that background retries or stale approvals cannot widen disclosure.

**Requirements:** FR-9, FR-12, FR-17; NFR-1, NFR-2, NFR-3, NFR-6; AR-07, AR-10, AR-11, AR-17; UX-DR20, UX-DR23, UX-DR27, UX-DR34, UX-DR49.

**Depends on:** OM-11.01, OM-11.02

**Acceptance criteria:**
- Given all current checks pass in automatic mode, when publication commits, then one exact company publication records audience, publisher automation, policy/version, basis and time; retries do not create duplicate publications.
- Given manual mode, when an authorized maintainer approves the exact evaluated publication version, then publication additionally records that human decision; inaccessible source material or insufficient maintainer authority prevents the decision.
- Given disabled mode or a mode/content/audience/policy/permission change while a job or review is pending, when it tries to commit, then the current conditions are rechecked atomically and stale publication is rejected without a success notification or accessible partial publication.
- Given publication fails or a worker restarts, when processing resumes, then operation state and idempotent retry behavior distinguish requested, successful, failed and unresolved outcomes; terminal failures are visible to authorized operators.

**Tasks:**
- [ ] **OM-11.03-T1** Implement the publication commit boundary with exact content/policy/audience revision guards and fresh maintainer/source/use authorization.
- [ ] **OM-11.03-T2** Wire automatic durable jobs and manual exact-version decisions to the same guarded publication operation; ensure disabled mode cannot enqueue or commit new publication.
- [ ] **OM-11.03-T3** Emit idempotent publication/lifecycle/audit events and expose authorized operation outcomes without depending on notification or audit UI epics.
- [ ] **OM-11.03-T4** Verify concurrent edits, pending automatic-to-manual/disabled changes, permission revocation, stale human approval, retry-after-commit and restart failure cases.

<a id="om-11-04"></a>

### OM-11.04 — Withdraw or quarantine guidance and its promoted derivatives

As a maintainer, I want unreliable guidance removed from future delivery with controlled history, so that already-published derivatives cannot bypass a correction or withdrawal.

**Requirements:** FR-9, FR-12, FR-13, FR-17; NFR-1, NFR-2, NFR-3, NFR-4, NFR-6; AR-07, AR-10, AR-11, AR-17; UX-DR20, UX-DR32, UX-DR41, UX-DR48, UX-DR49.

**Depends on:** OM-11.03

**Acceptance criteria:**
- Given a version is withdrawn/quarantined under the qualified lifecycle policy, when future retrieval or cached delivery is attempted, then the affected version and promoted derivatives are ineligible, including while asynchronous index/cache invalidation is pending.
- Given supersession or republication, when a new version is offered, then it preserves the historical relation and undergoes fresh evaluation under the current policy rather than inheriting approval.
- Given a viewer loses access to the original source but retains independently authorized company-publication access, when the company version is read, then no revoked source metadata is exposed; source ACL changes are not conflated with withdrawal of the publication's own permission or reliability.
- Given previous delivery receipts or external cached copies, when history is inspected, then only authorized history is retained/disclosed and Owl Mast explains that it cannot erase prior external context or actions; unverifiable current eligibility blocks a new delivery.
- Given adopted A-2 and A-4, when preparing live promotion, then withdrawal/derivative/cache behavior blocks affected versions while disabling promotion alone preserves existing eligible publications and prevents new commits. Derivation/publication lineage is retained for restricted history; delivered-to or used-in relations alone do not revoke unrelated work.

**Tasks:**
- [ ] **OM-11.04-T1** Implement transitive derivation/publication-aware eligibility invalidation and immediate delivery guards using exact-version lineage, with durable idempotent index/cache cleanup; ordinary retrieval stays denied while cleanup is pending.
- [ ] **OM-11.04-T2** Implement supersession and fresh-evaluation republication paths while distinguishing source ACL changes from publication permission and reliability changes.
- [ ] **OM-11.04-T3** Preserve permission-filtered lifecycle/receipt history and append-linked corrections with explicit external-copy and retention limits.
- [ ] **OM-11.04-T4** Verify withdrawn cached versions, derivative chains, stalled cleanup jobs, independent company-publication access and lost publication permission; verify A-2 lineage preservation and A-4 disabled-mode behavior without conflating stopping publication with withdrawal.

<a id="om-11-05"></a>

### OM-11.05 — Review promotion policy, exceptions and lifecycle in S6

As a project maintainer, I want one authorized promotion workspace, so that I can understand the exact publication and resolve exceptions without bypassing policy.

**Requirements:** FR-9, FR-12, FR-13, FR-17; NFR-1, NFR-2, NFR-5, NFR-6; AR-07, AR-10, AR-17; UX-DR20, UX-DR23, UX-DR25, UX-DR27, UX-DR32, UX-DR34, UX-DR41, UX-DR48, UX-DR49.

**Depends on:** OM-11.01, OM-11.02, OM-11.03, OM-11.04

**Acceptance criteria:**
- Given a permitted maintainer, when S6 opens, then it shows current mode/policy, exact proposed publication text/version, audience, authorized checks/basis and actual publication/withheld outcomes with a safe return to source detail.
- Given an exception, when the maintainer acts, then choices are bounded to retaining project scope with a reason, creating a corrected version, or requesting reevaluation after the authorized owner supplies missing input; no override bypasses required checks.
- Given stale content/policy, revoked rights or failed save/publication, when an action completes, then the UI reports the real result, invalidates stale approval and retains only permitted unsaved input without displaying false success or retrying a protected mutation while offline.
- Given a company reader lacks origin/recipient permissions, when a published item or history opens, then only independently authorized publication fields appear, with no hidden origins, recipient counts, filter values or differences revealing restricted records.

**Tasks:**
- [ ] **OM-11.05-T1** Build S6 policy controls, exact-version preview, manual decisions and automatic exception views using the existing authorized application contracts.
- [ ] **OM-11.05-T2** Add lifecycle/history navigation and separate company-reader presentation with field-level source, actor and recipient authorization.
- [ ] **OM-11.05-T3** Implement accessible pending/save/conflict/error/offline behavior and explanations for policy changes, changed content and unavailable source authority.
- [ ] **OM-11.05-T4** Verify manual and automatic journeys, all bounded exception paths, stale/revoked decisions, keyboard/phone use and restricted-history disclosure.
