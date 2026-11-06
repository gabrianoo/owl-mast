---
epic: E12
status: planned
review_status: pending-owner-review
implementation_status: not-started
---

# Epic E12 — Demonstrate skill and memory use and useful reuse

Reviewers distinguish availability, retrieval, delivery, native loading, observed use and human-verified useful outcomes. Statistics cover permitted project memory and skills, not personal Notion memory, and do not imply productivity or ROI. The proposed A-6 proof-case minimum remains pending owner confirmation.

**Epic prerequisites:** E04, E07, E08

<a id="om-12-01"></a>

### OM-12.01 — Preserve distinct exact-version knowledge evidence

As a reviewer, I want client observations and receipts retained as distinct facts, so that a search, transfer or read is never counted as proven application or useful reuse.

**Requirements:** FR-11, FR-16, FR-17, FR-18, FR-21; NFR-1, NFR-2, NFR-3, NFR-6; AR-07, AR-14, AR-16, AR-17, AR-18; UX-DR21, UX-DR32, UX-DR50.

**Depends on:** E04, E07, E08

**Acceptance criteria:**
- Given a supported native client event or receipt, when it is normalized, then availability, retrieval, confirmed delivery, successful read/load, observed application and verified reuse remain distinct evidence types with exact item/package version, recipient context, source identity/time and recorded time where supported.
- Given only a search match, UI click, source page view, package fetch or successful delivery without read acknowledgment, when evidence is classified, then it does not become an agent load, native invocation or application; partial/failed attempts are not successful deliveries or loads.
- Given duplicate or out-of-order events, when they arrive, then source-qualified event identity deduplicates replay while preserving genuinely distinct reloads; missing prerequisite observations are not manufactured to form a complete sequence.
- Given unknown versions, ambiguous task/client attribution, unsupported observation or revoked access, when evidence is retained or shown, then unsupported claims remain unassigned/unavailable and source/recipient restrictions prevent prohibited payloads and derived disclosure.

**Tasks:**
- [ ] **OM-12.01-T1** Add Evidence-owned native load/application/reuse assertion and link records consuming Ingestion observations and referencing Knowledge-owned exact versions/delivery receipts; do not duplicate receipt or lifecycle authority, preserving exact versions, event identity, independent states and coverage provenance.
- [ ] **OM-12.01-T2** Implement event validation, idempotency, late-arrival handling and explicit unassigned/unsupported classification without reconstructing facts from conversation text.
- [ ] **OM-12.01-T3** Apply recipient/item/source/purpose authorization and A-3 collection limits before storing evidence or emitting safe audit events; keep raw queries/conversations unnecessary.
- [ ] **OM-12.01-T4** Verify both native clients' supported read/load/use signals, fetch-without-load, partial receipts, unknown versions, duplicate transport and genuinely repeated cached loads.

<a id="om-12-02"></a>

### OM-12.02 — Record human-verified useful reuse against task evidence

As an authorized reviewer, I want to connect an exact knowledge version to a subsequent task artifact and verify its usefulness, so that claimed reuse has inspectable evidence beyond a retrieval count.

**Requirements:** FR-11, FR-17; NFR-1, NFR-2, NFR-6; AR-07, AR-10, AR-16, AR-17; UX-DR21, UX-DR32, UX-DR50.

**Depends on:** OM-12.01

**Acceptance criteria:**
- Given an exact knowledge version, permitted recipient/task context and subsequent action/output evidence, when an authorized human verifies usefulness, then a reuse record binds those references, the verifier, time and verification basis without asserting causal productivity or monetary impact.
- Given no exact version, no supported subsequent task evidence, inaccessible evidence or an unauthorized verifier, when verification is attempted, then it cannot become verified reuse and the user receives a safe actionable explanation without hidden record details.
- Given a correction, duplicate verification submission or later permission loss, when the record is revisited, then retries do not multiply reuse, corrections remain append-linked and protected artifact/recipient/verifier details disappear from all dependent views and counts.
- Given A-6 remains provisional, when pilot samples are prepared, then the proposed one verified cross-contributor reuse per project plus one company-safe cross-project reuse is presented for product-owner/participant confirmation before acceptance, not claimed as an approved statistical effectiveness target.

**Tasks:**
- [ ] **OM-12.02-T1** Implement the exact-version/task-artifact human verification contract and scoped persistence with explicit evidence and verifier authorization.
- [ ] **OM-12.02-T2** Add idempotent verification, correction/retraction and permitted audit history without overwriting earlier recorded claims.
- [ ] **OM-12.02-T3** Expose a permission-checked Record verified reuse action from an eligible receipt/detail record with honest missing-evidence validation.
- [ ] **OM-12.02-T4** Verify positive and missing/denied-evidence cases, duplicate verification, corrections and recipient revocation; prepare the unresolved A-6 sample-selection checkpoint.

<a id="om-12-03"></a>

### OM-12.03 — Aggregate Skills and Memory measurements without false completeness

As a reviewer, I want separate scoped knowledge measurements with their counting basis and coverage, so that I can understand adoption without mistaking it for effectiveness.

**Requirements:** FR-11, FR-16, FR-17; NFR-1, NFR-2, NFR-3, NFR-4; AR-07, AR-16, AR-17, AR-18; UX-DR24, UX-DR35, UX-DR50.

**Depends on:** OM-12.01, OM-12.02

**Acceptance criteria:**
- Given authorized evidence for a project/period, when statistics are calculated, then Skills and Memory have separate successful read/load, delivery, observed application and verified-reuse measures with units, exact-version scope, coverage and attribution basis.
- Given duplicate receipts, real reloads, a multi-item load or a shared session, when counts are calculated, then replay is counted once, distinct evidenced reloads remain distinct, each included item/version requires observed inclusion and distinct agents/sessions/items are not synonyms for load count.
- Given a known gap, unsupported source or a known-complete empty window, when a metric is returned, then it is respectively partial, Unavailable or zero; source event time defines the period, with any recorded-time fallback and delay explicitly labeled.
- Given restricted recipients, task evidence, item versions or filter values, when aggregate and drill-down results are requested, then they use the same authorized evidence set and the label Counted from records you can access, without hidden unique-count differences or residual shares revealing inaccessible records.
- Given model, machine or task breakdowns lack supporting attribution, when filters/groupings are requested, then unsupported dimensions remain unassigned or unavailable instead of being guessed from a session association.

**Tasks:**
- [ ] **OM-12.03-T1** Implement bounded authorized aggregate queries for distinct Skills/Memory metrics and supported dimensions, using event identity and exact-version links.
- [ ] **OM-12.03-T2** Encode period selection, event-time/fallback rules, coverage completeness and zero/partial/unavailable semantics in the statistics contract.
- [ ] **OM-12.03-T3** Implement matching authorized drill-down and filter-option queries with current recipient/source/item permissions and revocation invalidation.
- [ ] **OM-12.03-T4** Verify replay versus reload counting, multi-item inclusion, late events, unknown attribution, complete/partial windows and permission-safe unique counts.

<a id="om-12-04"></a>

### OM-12.04 — Inspect knowledge receipts, statistics and reuse evidence

As an authorized contributor or lead, I want consistent item-level and overview knowledge statistics, so that I can inspect what reached agents and what demonstrably helped their work.

**Requirements:** FR-11, FR-16, FR-17, FR-21; NFR-1, NFR-2, NFR-5, NFR-6; AR-10, AR-16, AR-17; UX-DR21, UX-DR24, UX-DR32, UX-DR35, UX-DR50.

**Depends on:** OM-12.02, OM-12.03

**Acceptance criteria:**
- Given authorized S3/S4 item/version detail or S7 project/period scope, when the knowledge statistics view opens, then separate Skills/Memory measures, coverage, units and accessible-record basis agree across chart/table and detail views.
- Given a selected count or receipt, when the viewer drills down, then permitted item/version/client/session/task/machine evidence and timestamps explain the count; recipient identity requires its own authorization and absent dimensions stay unknown.
- Given a supported verification opportunity, when the reviewer uses Record verified reuse, then the exact version and task evidence are explicit and the UI reflects the actual permission-checked result without renaming mere loading as reuse.
- Given unsupported Notion/client observation, no complete historical window or permission loss while open, when the view renders or refreshes, then it shows Unavailable/partial coverage or removes protected details and derived counts safely rather than fabricating zeros or retaining stale disclosure.

**Tasks:**
- [ ] **OM-12.04-T1** Add item/version knowledge statistics to S3/S4 and the separate Skills/Memory section of S7 using the shared metrics contract and equivalent accessible chart/table representations.
- [ ] **OM-12.04-T2** Implement receipt/event drill-down and contextual verification flows with stable project/period/version filters and explicit source/recipient disclosure boundaries.
- [ ] **OM-12.04-T3** Provide honest empty, partial, unavailable, pending, failure and revoked-access states, including distinctions among delivery, load, use and verified reuse.
- [ ] **OM-12.04-T4** Verify the J9 knowledge-measurement journey and FR-11 verification flow with both native clients, keyboard/screen-reader navigation, both themes and phone layouts; keep A-6 acceptance approval pending.
