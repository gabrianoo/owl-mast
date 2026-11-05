# PRD input reconciliation

2026-11-05. Reconciles the supplied finalized [PRD](../../prds/prd-owl-mast-2026-11-05/prd.md), [addendum](../../prds/prd-owl-mast-2026-11-05/addendum.md), [memlog](../../prds/prd-owl-mast-2026-11-05/.memlog.md), and [review disposition](../../prds/prd-owl-mast-2026-11-05/review-disposition.md), using the [full extraction](.working/source-prd.md), against draft [DESIGN.md](DESIGN.md) and [EXPERIENCE.md](EXPERIENCE.md). Latest authority: UX-01–13 in the [UX memlog](.memlog.md).

This is required source reconciliation, not the optional reviewer gate or a usability/accessibility/integration test. Sources remain inherited by reference; this report does not require every upstream implementation or acceptance detail to be duplicated. Stable section/surface references below identify the inspected draft rather than mutable line numbers.

## Functional requirement coverage

**E** = EXPERIENCE.md; **D** = DESIGN.md. “Partial” identifies a concrete user-facing source requirement missing from the draft, detailed below.

| FR | Draft coverage location | Reconciliation |
| --- | --- | --- |
| FR-1 Separate connections | E: IA S5/S8; J2 steps 1–2; connection readiness; state S8. | Covered: both source environments, separate Jira identities, authorized capabilities, source/account boundaries. |
| FR-2 Minimal enrollment | E: Foundation; S5; J2 steps 4–5; state S5. D: connection readiness. | Covered: both clients, explicit project, separate readiness, minimal recurrence; exact step ceiling remains A-5. |
| FR-3 Health/recovery | E: connection readiness; state S1/S5/S8; J1/J2 failures; Voice and Tone. | Covered: last successful collection, partial/unsupported/stale states, independent failures and useful recovery. |
| FR-4 Attribution | E: work record, evidence detail, epic group; Evidence semantics; SC-1; J8. | Covered: owner/initiator/agent/delegation/repository identity, unknown and inferred mappings, shared/unlinked work. |
| FR-5 Evidence chain | E: S2; evidence detail; SC-1; Evidence semantics. D: evidence detail. | **Partial — R-01:** chain and distinct outcomes retained; approving authority/configured acceptance rule needs a visible field. |
| FR-6 Progress/dependencies | E: progress evidence; Evidence/progress semantics; SC-1; J8. D: progress evidence, epic group. | Covered: source, scope, denominator, time, changed scope, explicit/inferred relationships; no inferred parent acceptance. UX-07 selects ticket criteria/checklist basis. |
| FR-7 Attention | E: S1/S2; attention item; J1/SC-1; stale states. D: attention item. | Covered: reason/source/time, no telemetry-to-failure inference, skipped/not-run evidence, no execution actions. |
| FR-8 Capture/provenance | E: S3/S4; knowledge record; Knowledge semantics; SC-2 steps 1–2. | Covered: scoped submission, origin/applicability/evidence, candidate versus approved, duplicate lineage, existing capture path. |
| FR-9 Lifecycle/review | E: S4/S6; knowledge record; Knowledge semantics; SC-2 step 2. | **Partial — R-02:** lifecycle/version/conflict retained; human versus automated evaluator and evaluation timestamp need explicit presentation. A-1 remains unresolved. |
| FR-10 Scoped delivery | E: Foundation UX-08; S3/S4; Knowledge semantics; SC-2 steps 3–4 and failures. | Covered: on-demand agent search, explicit scope, applicable version/source/freshness, empty versus failure, truncation and no cross-project fallback. |
| FR-11 Receipt/reuse | E: delivery receipt; Knowledge semantics; SC-2 steps 5–6; S4 state. D: delivery receipt. | Covered: available/retrieved/delivered/reused distinction, permitted recipient/project/version/time, human-verified task usefulness. |
| FR-12 Promotion | E: S6; promotion review/settings; Promotion semantics; SC-3. D: promotion review. | Covered: three modes, exact evaluated content/version/audience, checks/rationale/history, project-designated authority, changed-version/mode invalidation. A-4 remains unresolved. |
| FR-13 Withdrawal/supersession | E: S4/S6 states; Promotion semantics; SC-3 steps 6–7 and failure; assumptions. | Covered: lifecycle/history, fresh eligibility check, limits on old copies/actions; detailed quarantine/withdrawal default explicitly inherited as A-2. |
| FR-14 Hermes/Notion continuity | E: Foundation; Knowledge semantics; SC-2 steps 1–4/failure; S3 state. | Covered: continued capture, validated delivery, no bulk migration/duplicate save or silent overwrite. |
| FR-15 Authorized views | E: S1/S2/S5/S7/S10; scope bar; state patterns; SC-1/J8. D: scope bar, summaries. | Covered: project/company contexts, connected clients, retained scope/time, permitted evidence, empty/unavailable/incomplete distinction. |
| FR-16 Usage/cost | E: S7; usage breakdown; Usage semantics; J6. D: usage breakdown. | **Partial — R-03:** measurement classes, attribution/coverage, unknown/unpriced/unassigned and pricing date retained; model/agent/person breakdowns are not explicit. |
| FR-17 Access | E: Foundation; scope bar; global/S1–S10 states; interaction primitives; J7; SC-3. | Covered across search/detail/aggregates/notifications: source rights, revoked/unverifiable access, safe errors, no cached bypass or hidden-count disclosure. |
| FR-18 Collection governance | E: S8; J2 step 3; S8 diagnostics; A-3 register. | Covered as administrator collection/retention configuration with source contract inherited. A-3 explicitly unresolved before real ingestion; no secrets in ordinary text. |
| FR-19 Execution boundary | E: Foundation; attention/external-link/focus behavior; J1/SC-1/J7/J8. D: external link and permitted actions. | Covered and reaffirmed by UX-06: read/inspect/navigate; direct agent interaction later, no dispatch/reply/status mutation proxy. |
| FR-20 Repeatability | E: Foundation open-source scope; S8; J2 step 1. | Covered at UX level by setup prerequisites, supported boundaries, and secret-free instructions; detailed reproduction/public-release requirements remain upstream, not a new deployment selection. |
| FR-21 Notion-backed clients | E: Foundation; S3–S5; Knowledge semantics; J2 climax; SC-2 steps 1–4. | Covered: both clients, page-writing versus unverified skill reading, source version/scope, preserved existing workflow without a replacement-store claim. |

## Concrete source omissions

| ID | Source obligation and draft evidence | Minimal reconciliation needed |
| --- | --- | --- |
| **R-01 — acceptance authority** | PRD vocabulary line 48 defines acceptance evidence by its approving authority or configured source rule; FR-5 requires actual acceptance evidence. E S2/SC-1 shows acceptance evidence and provenance but does not tell the viewer which person/rule establishes acceptance. | Add the acceptance authority/configured source rule and referenced artifact to S2's evidence contract; absent authority must not imply verified acceptance. Pilot authority selection remains upstream. |
| **R-02 — evaluation kind** | FR-9, PRD line 136 explicitly distinguishes automatically evaluated from human-reviewed guidance and records evaluator/policy, evaluated version, basis, and time. E S4/knowledge record uses generic “evaluation”/review metadata, while promotion mode is a separate concept. | Make S4 show evaluation kind, responsible person or validation policy, basis, version, and timestamp. Do not let an automatic promotion badge substitute for knowledge-review provenance. |
| **R-03 — usage dimensions** | FR-16, PRD line 197 requires supported breakdowns by project, client/model, agent, person, or work item. E S7/J6 names client/session/work filters and attribution, but omits model/agent/person dimensions. | Add those supported dimensions to S7/usage breakdown; unavailable attribution remains explicitly unavailable/unassigned rather than fabricated. |

No direct execution-scope conflict, weakened access boundary, replacement-Notion commitment, or invented integration readiness was found. These omissions are focused source-to-surface corrections, not requests to reopen settled product decisions.

**Resolution:** R-01–R-03 were applied to EXPERIENCE.md after this reconciliation: `evidence-detail` names acceptance authority/rule and artifact; `knowledge-record` names evaluation kind, evaluator/policy, basis, version, and time; S7, `usage-breakdown`, and J6 expose the supported attribution dimensions. The table above preserves the findings at inspection time; none remains open.

## Six inherited assumptions remain distinct

| Assumption | Draft treatment | Status |
| --- | --- | --- |
| A-1 Default delivery eligibility | E SC-2 step 2/failure, Promotion semantics, final register. UX-08 selects retrieval initiation only. | Still unconfirmed; exact original text/owner/revisit retained by reference and in canonical memlog. |
| A-2 Withdrawal/quarantine default | E Promotion semantics; SC-3 step 7; final register. | Still unconfirmed; no claim to erase external copies or reverse past actions. |
| A-3 Collection defaults | E J2 step 3; final register. | Still unconfirmed before live-content ingestion. |
| A-4 Disabled mode and existing publication | E settings field; SC-3 step 7; final register. | Still unconfirmed; disabled publication is not silently equated with withdrawal. |
| A-5 Enrollment step ceiling | E J2 step 4 explicitly tagged; final register. | Still unconfirmed; minimal recurring effort remains confirmed separately. |
| A-6 Minimum reuse samples | E SC-2 climax explicitly provisional; final register. | Still unconfirmed; no fabricated effectiveness threshold. |

All six exact proposals and owner/revisit conditions remain in the extraction, upstream PRD index, and canonical UX memlog. Later UX answers do not silently settle them.

## Late decisions and qualitative intent

| Decision | Reflected location / disposition |
| --- | --- |
| UX-06: direct agent interaction later; phone execution in another app. | E Foundation, J1, SC-1, Responsive, J7, J8. No PRD expansion. |
| UX-07: percentage from completed criteria/checklist; Unknown without breakdown. | E Voice, progress evidence, progress semantics, SC-1; D progress evidence/Shapes. Epic closure measure stays a labeled proposal. |
| UX-08: agent searches when needed. | E Foundation, SC-2 step 3, resolved-question register. No default injection/manual sending; Notion integration remains unverified. |
| UX-09: project-designated maintainers handle exceptions/manual reviews. | E Foundation, promotion review, SC-3, register. No real permission assignment follows from the persona. |
| UX-10: every observed update triggers push; feed retains updates. | E Foundation, activity list, J7 and failure semantics, register. No silent attention-only/digest substitution; replay dedup does not suppress distinct updates. |
| UX-11: separate assigned-work Focus board. | E S10/J8, navigation proposal and state table; D Layout, focus-board component. Daily landing remains separate. |
| UX-12: concurrent agents across multiple epics. | E epic-group, S10/J8 with shared/unmapped records and deduplicated totals; D epic-group/layout. Grouped/combined mechanics remain proposals, not invented user preferences. |
| UX-13: displayed colors/mobile study and owl accepted. | D Brand & Style distinguishes accepted displayed direction/mark from delegated exact tokens and untested implementation. Existing accepted mark retained. |

ConvaDesk evidence concepts, Ponytail visual influence, dedicated multidevice UI, low recurring setup, both project/provider combinations, existing Hermes/Notion continuity, and the understanding-to-reuse outcomes remain present. Detailed architecture, license, connector feasibility, target calibration, and real-environment proof remain upstream/downstream work rather than dropped UX preferences.

## Finalization addendum — 2026-11-05

The earlier pending Focus/reference statements describe the reconciliation snapshot. All ten surfaces now have visual references, with a separate shared navigation/company example. Review dispositions cover the later UX-15 identity chips, UX-17 contextual cost, explicit system quarantine (FR-13), and derivative permissions. Original A-1–A-6 remain unconfirmed. See [review disposition](review-disposition.md).
