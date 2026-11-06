---
epic: E14
status: planned
review_status: pending-owner-review
implementation_status: not-started
---

# Epic E14 — Understand usage and cost with defensible attribution

People inspect per-task model, effort, session, machine and token evidence alongside clearly separated cost classes. Incomplete, unassigned and unpriced portions remain visible without double-counting or disclosing restricted records. Knowledge counts stay separate from consumption and productivity claims.

**Epic prerequisites:** E06, E07, E08, E10

<a id="om-14-01"></a>

### OM-14.01 — Calculate unique observed usage with correct counter semantics

As an authorized reviewer, I want defensible token totals, so that repeated samples and overlapping observations do not inflate consumption.

**Requirements:** FR-16; NFR-1, NFR-2, NFR-3; AR-07, AR-17, AR-18; UX-DR24, UX-DR41, UX-DR46, UX-DR47

**Depends on:** E06, E07, E08, E10

**Acceptance criteria:**

- Given token observations with known units/windows, when totals are calculated, then input and output are independent; unavailable directions stay unavailable, cache categories are labeled according to provider inclusion semantics, and already-included cached input is not added twice.
- Given delta/cumulative samples, process restarts, late points or retransmission, when aggregation runs, then it honors stream identity, start/end timestamps, temporality and reset epochs; cumulative snapshots are not summed and repeated delta intervals are not new consumption.
- Given hooks, log events, metrics, traces or contextual sources describing the same work, when accounting reconciles them, then one documented source basis represents each usage portion; parent totals containing children and repeated appearances are not added together.
- Given uncertain counter semantics, unresolved overlap or a collection gap, when a subtotal is displayed, then uncertainty/coverage accompanies the permitted observed portion rather than a fabricated zero or complete total; distinct evidenced retry consumption can count once.
- Given unauthorized measurement records, when totals or filters are produced, then they are excluded under current source permissions without hidden-record counts or residual-share disclosures.

**Tasks:**

- [ ] **OM-14.01-T1** Define canonical usage portions, source precedence, input/output/cache semantics and provenance for each qualified runtime/version.
- [ ] **OM-14.01-T2** Implement temporality-aware aggregation with stream/epoch identity, replay suppression, ordered reconciliation and explicit gaps/conflicts.
- [ ] **OM-14.01-T3** Implement parent/child and cross-signal overlap handling without adding telemetry sources that describe the same consumption.
- [ ] **OM-14.01-T4** Verify cumulative resets, delta duplicates, late windows, missing directions, cache subsets, retries and inaccessible measurements with independent expected totals.

<a id="om-14-02"></a>

### OM-14.02 — Attribute usage only to evidenced work and execution segments

As a contributor, I want usage linked to the correct task/run and execution context, so that a shared session does not falsely charge one ticket or person.

**Requirements:** FR-4, FR-5, FR-16, FR-17; NFR-1, NFR-2; AR-07, AR-09, AR-17, AR-18; UX-DR30, UX-DR35, UX-DR41, UX-DR46, UX-DR47

**Depends on:** OM-14.01

**Acceptance criteria:**

- Given compatible usage portions with supported task mappings, when attributed, then project, work item, role, run, model, effort, client, agent, person, session and machine are linked only to evidenced dimensions with source/time and attribution basis.
- Given a session linked to multiple tickets or a shared external account, when evidence cannot partition consumption or identify the person, then usage remains unassigned at that dimension; a link alone does not allocate the session total or merge personal identities.
- Given model/effort/location changes or concurrent/delegated runs, when history is inspected, then time-qualified observations remain separate from configured/requested settings, and differing effort labels are not equated across providers.
- Given corrected mappings or revoked access, when summaries refresh, then permissible attribution recomputes with append-linked correction history; ticket visibility alone does not grant run, machine or usage visibility.
- Given the same usage appears under multiple permitted epics/views, when a combined total is requested, then it counts each unique portion once and labels the selected authorized work set.

**Tasks:**

- [ ] **OM-14.02-T1** Implement source-backed work/person/context attribution rules and explicit unassigned states using E10 relationship evidence.
- [ ] **OM-14.02-T2** Preserve execution segments and distinct configured/requested/observed values in attribution APIs and permitted drill-downs.
- [ ] **OM-14.02-T3** Implement correction-aware recomputation and deduplicated epic/project rollups with field-level authorization.
- [ ] **OM-14.02-T4** Verify shared sessions/accounts, ambiguous roles, concurrent children, historical machine changes and revoked-field aggregate behavior.

<a id="om-14-03"></a>

### OM-14.03 — Keep observed units, estimates, allocations and bills separate

As an authorized owner, I want clearly identified cost classes and provenance, so that observed tokens are not mistaken for an invoice or individual productivity.

**Requirements:** FR-16, FR-17, FR-18; NFR-1, NFR-2, NFR-6; AR-07, AR-17, AR-18; UX-DR24, UX-DR35, UX-DR41, UX-DR57

**Depends on:** OM-14.02

**Acceptance criteria:**

- Given a supported observed usage portion and a matching dated price source, when an API-equivalent estimate is calculated, then it retains model/provider, units, currency, period, pricing date and basis separately from native estimated-cost telemetry and actual billed charges.
- Given a subscription allocation or an actual bill submitted through an authorized evidence path, when displayed, then the class, source, permitted period and allocation method remain explicit; the system does not invent a billing connector or distribute subscription fees by token count without a declared basis.
- Given missing pricing, incompatible currencies, uncertain model identity or unsupported attribution, when totals are requested, then unpriced/unassigned/unavailable portions remain distinct and unlike classes/currencies are not silently added or converted.
- Given a viewer can access a ticket but not bills or allocation inputs, when they open contextual cost, then restricted classes and inference-bearing residuals are withheld; observed units remain subject to their own authorization.
- Given a corrected price or billing record, when recalculated, then revision provenance and applicable historical basis are retained rather than silently rewriting all prior estimates; no usage or cost class is labeled ROI or productivity.

**Tasks:**

- [ ] **OM-14.03-T1** Define separate observed-unit, API-equivalent estimate, subscription-allocation and actual-bill records with source/date/currency and access controls.
- [ ] **OM-14.03-T2** Implement versioned price matching and estimation, plus authorized recording of allocation/billing evidence without an unsolicited payment integration.
- [ ] **OM-14.03-T3** Implement class-specific aggregation, unpriced/unassigned handling and revision-aware recalculation.
- [ ] **OM-14.03-T4** Verify wrong/missing prices, currency mixtures, changed price dates, inaccessible allocation inputs and non-additive measurement classes.

<a id="om-14-04"></a>

### OM-14.04 — Present S7 and contextual work usage with honest coverage

As an authorized viewer, I want readable usage analysis and work-level drill-down, so that I can understand the measurements and their limits.

**Requirements:** FR-15, FR-16, FR-17; NFR-1, NFR-2, NFR-5; AR-16, AR-17, AR-18; UX-DR24, UX-DR30, UX-DR35, UX-DR41, UX-DR46, UX-DR47, UX-DR57

**Depends on:** OM-14.03

**Acceptance criteria:**

- Given an authorized project/company/work scope and period, when S7 loads, then supported client/model/effort/role/device/agent/person/session/work dimensions filter the same permitted records across chart and table, retaining unassigned/unpriced portions and independent input/output coverage.
- Given a ticket or epic summary, when opened, then it preserves work-set scope, class, currency, period and attribution basis into the same detailed view; multiple model/effort/machine values expand into individual run evidence rather than choosing a representative default.
- Given totals, when displayed, then every aggregate carries the constant accessible-record basis label and known collection gaps; no supported measurement reads Unavailable, while an evidenced zero remains zero. Skill/Memory delivery/load/use counts are linked as separate measures, not folded into consumption.
- Given loading, denied, stale, unsupported, empty or failed data, when the view renders, then each state is distinct without placeholder amounts; keyboard/phone users can access the same information through the table and retained focus.
- Given access revocation while details are open, when refresh or interaction occurs, then restricted values, copied identifiers, filter options and derived differences are removed safely without exposing hidden totals.

**Tasks:**

- [ ] **OM-14.04-T1** Build authorized S7 breakdown APIs and the chart/table UI with shared query semantics, period/scope retention and explicit measurement classes.
- [ ] **OM-14.04-T2** Add ticket/epic usage summaries and run-segment drill-down with model/effort/session/machine provenance and independent In/Out states.
- [ ] **OM-14.04-T3** Add accessible loading/error/empty/unsupported/stale behavior and links to separately scoped Skill/Memory statistics.
- [ ] **OM-14.04-T4** Verify chart/table parity, phone/keyboard navigation, mixed-class display, hidden-record inference and mid-session revocation against expected calculations.

## Qualification and source notes

Owner review remains pending. Provider accounting, supported attribution fields, current prices and any billing evidence path require qualification before figures are presented as observed or billed. Default-on conversation capture does not establish personal/task attribution or authorize broader source access to fill evidence gaps.

- [OTel metrics data model](https://opentelemetry.io/docs/specs/otel/metrics/data-model/) defines delta/cumulative windows and reset semantics; aggregation must inspect received data rather than presume one temporality.
- [Claude monitoring](https://code.claude.com/docs/en/monitoring-usage) distinguishes cache token categories and approximate cost. Its emitted labels do not establish personal or task attribution by themselves.
- [Official Codex telemetry configuration](https://learn.chatgpt.com/docs/config-file/config-advanced) and [hooks](https://learn.chatgpt.com/docs/hooks) describe different available event/attempt evidence, not a universal per-task bill.
- [UX experience contract](../../ux-designs/ux-owl-mast-2026-11-05/EXPERIENCE.md) governs UX-18 fields, token overlaps and measurement classes; its proposals retain their review status.
