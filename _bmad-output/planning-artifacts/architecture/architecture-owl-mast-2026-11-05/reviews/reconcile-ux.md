# UX reconciliation — architecture spine

Date: 2026-11-06. Reviewed the first complete AD-1–AD-16 draft against `DESIGN.md` and `EXPERIENCE.md` in `ux-owl-mast-2026-11-05`. Scope: architectural consistency, not a second UX or visual review.

## Verdict

No contradictory adopted decision or new product-choice blocker found. The spine preserves the major UX constraints, including lineage, client-led knowledge loading, publication/withdrawal, source access and separate deployment. Three concise additions would prevent independently built UI, usage and notification features from interpreting inherited UX requirements differently. These are reconciliations of existing behavior, not new requirements.

## Findings

### UX-R1 — Make shared work scope explicit in AD-13 (medium)

**Source:** EXPERIENCE Foundation, Information Architecture and J7/J8; DESIGN Layout & Spacing. Daily Work and the separate assigned-to-me Focus board have different scopes. Focus is not a replacement landing page. Notification eligibility includes authorized connected-project work; person/assignment feed filters do not narrow it. The six nonlinear stages are Plan, Design, Build, Test, Deploy and Maintain, with unmapped work retained.

**Gap:** AD-13 says only that “six-stage Focus mapping is observational” and that push sends every eligible update. The combined Evidence/Usage/Web capability mapping does not name the two work projections or distinguish their selection predicates. A shared endpoint or notification consumer could reuse Focus's assigned-work filter and silently omit colleague updates while still treating every resulting record as eligible.

**Fix:** Add a short rule to AD-13: Daily Work and assigned-work Focus are separate projections; the six named stages preserve source status and unmapped work; feed/person/assignment filters do not alter notification eligibility. The existing E10/E13/E15 contracts own implementation. Do not add a new service or UI page.

### UX-R2 — Retain the financial measurement classes in the shared view contract (medium)

**Source:** EXPERIENCE Usage, Contextual cost presentation, `usage-breakdown`, and ticket-run accounting semantics. Observed units, API-equivalent estimates, subscription allocations and actual bills remain distinct, with currency, period, attribution/pricing basis, coverage and unassigned portions. A linked session alone does not allocate its usage to a ticket.

**Gap:** AD-13's fact/inference/estimate/unknown labels and deduplication rules do not carry these non-interchangeable accounting classes. The usage owner and contextual ticket/epic consumers could expose one generic amount/total and erase the estimate/allocation/bill distinction.

**Fix:** Add one AD-13 clause preserving the four classes and supported attribution; unknown allocation remains unassigned and incompatible classes/currencies are never added. Detailed fields/calculations remain in E14 and UX rather than the spine.

### UX-R3 — Include permission-driven UI invalidation in the common state contract (medium)

**Source:** EXPERIENCE State Patterns, Accessibility Floor and J7. Normal updates wait behind “New updates” and preserve focus/read position. Permission/scope removal immediately removes protected content instead of waiting for that refresh. Offline browsing cannot newly disclose protected cached content, and publication/admin writes are not queued offline.

**Gap:** AD-4 governs operation-time authorization and AD-13 governs authorized projections, but neither states how already displayed/cache-held data behaves while the UI deliberately defers ordinary refresh. The common web/API contract in OM-01.04 could otherwise treat revocation as just another pending update; separate feature views could implement incompatible cache/offline behavior.

**Fix:** Add a compact consistency convention: normal refresh preserves the reader's position; permission invalidation overrides buffered refresh and purges protected UI/cache state, with a neutral focus destination; no offline protected disclosure or queued publication/admin mutations. OM-01.04 owns the common state contract, with E02's authorization boundary providing the invalidation semantics. Do not infer a particular push/WebSocket protocol.

## Preserved without further spine expansion

- AD-1 preserves observational V1 and source navigation rather than execution controls, including native Notion/Hermes continuity.
- AD-3/4 distinguish individual users, source accounts, enrollment, observed execution and current source/recipient permissions; shared identities are not attribution proof.
- AD-7/12 retain exact-version typed lineage, history, archive identity and derivative-aware withdrawal without implying recall of external copies.
- AD-9 carries validated-default client-led bounded discovery and selected loads, explicit candidate inclusion and the distinction from work-update push.
- AD-10/11 preserve full capture by default, 30 days active followed by retained archive, and A-4's publication-disable semantics.
- AD-8/13 distinguish evidence of delivery/load/application/verified reuse, scope-filter graph/list together and preserve unknown/partial coverage.
- AD-14 and Deferred preserve separate frontend/backend deployments without inventing browser origins, session ownership, push packaging or native credential refresh.
- Accepted owl artwork, exact colors/themes, responsive layouts, controls, typography and component-level accessibility remain governed by DESIGN/EXPERIENCE and the frontend shell story. Copying their detailed visual rules into this spine would add duplication rather than architectural consistency.
- Earlier mockup/review claims and the original handoff prohibition on epic generation are historical; subsequent explicit user instructions and adopted architecture decisions govern.

No source or spine files changed by this reconciliation.
