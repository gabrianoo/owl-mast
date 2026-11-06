---
epic: E13
status: planned
owner_review: pending
source_plan: ../../epics.md
---

# Epic E13 — Understand daily work and personal focus

**Outcome:** Contributors and leads understand their own and colleagues' work through Daily Work, explicit company views, concurrent epic Focus and an observed six-stage kanban.

**Epic prerequisites:** E10.

Daily Work and Focus are confirmed separate destinations. Exact section order, grouped/combined presentation, Today reporting default and epic closure display remain the existing UX proposals. All summaries consume E10 evidence contracts; this epic does not introduce alternate progress calculations or source mutations.

<a id="om-13-01"></a>

### OM-13.01 — Understand own and colleague work from Daily Work

As a contributor, I want a scoped daily overview of my own and colleagues' work, so that I can understand closures, explicit attention and progress without requesting a manual recap.

**Requirements:** FR-5, FR-6, FR-7, FR-15, FR-17; NFR-1, NFR-2, NFR-3, NFR-5; AR-07, AR-10, AR-17; UX-DR08, UX-DR09, UX-DR10, UX-DR11, UX-DR12, UX-DR13, UX-DR14, UX-DR15, UX-DR18, UX-DR19, UX-DR26, UX-DR29, UX-DR30, UX-DR41, UX-DR43, UX-DR44, UX-DR45.

**Depends on:** E10.

**Acceptance criteria:**

- **Given** an authorized project and explicit reporting period, **when** S1 opens or a permitted person filter changes, **then** closures, evidenced blockers/review needs, measured progress, recent updates and coverage share that scope; Daily Work is not silently limited to viewer assignments.
- **Given** a displayed count or attention item, **when** selected, **then** its drill-down preserves the same permitted record basis and time window, includes the constant accessible-record label and opens E10 source evidence rather than recomputing a different total.
- **Given** stale or partially failed collection, **when** the overview refreshes, **then** healthy authorized sections remain usable and empty/no-match/no-connected-coverage/unknown states remain distinct; missing telemetry never produces an invented blocker or zero.
- **Given** a source/person permission is revoked, **when** filters or summaries are requested, **then** protected labels, derived counts and preview text disappear without revealing hidden residuals.

**Tasks:**

- [ ] **OM-13.01-T1** Define S1 query composition and person/project/period filters over the established work-evidence read contracts.
- [ ] **OM-13.01-T2** Build the proposed overview layout with summary, attention, progress, work/agent chips, updates and collection coverage components.
- [ ] **OM-13.01-T3** Connect each summary/count to its exact permitted detail set and preserve source/time/coverage labels.
- [ ] **OM-13.01-T4** Verify own/colleague views, partial outages, source identity ambiguity and permission-filtered drill-down consistency.

<a id="om-13-02"></a>

### OM-13.02 — Compare authorized project context in a company view

As an authorized lead, I want an explicitly selected company overview, so that I can inspect permitted project health and drill into evidence without merging customer boundaries.

**Requirements:** FR-6, FR-7, FR-15, FR-17; NFR-1, NFR-2, NFR-3; AR-08, AR-10, AR-17; UX-DR08, UX-DR09, UX-DR10, UX-DR18, UX-DR26, UX-DR29, UX-DR41, UX-DR44, UX-DR45.

**Depends on:** OM-13.01.

**Acceptance criteria:**

- **Given** company-view authority, **when** the viewer explicitly changes scope, **then** project progress, agent activity, attention and available knowledge/usage entry points retain project boundaries and the selected period; company scope does not change knowledge search defaults.
- **Given** a project summary, **when** selected, **then** navigation enters that permitted project before detailed work inspection and preserves safe company return context.
- **Given** inaccessible projects or source records, **when** aggregates and filters are produced, **then** no private project name, hidden count or residual share appears, and every aggregate uses the same constant accessible-record basis label.
- **Given** one source becomes unavailable or rights cannot be checked, **when** company data is refreshed, **then** known collection gaps and unavailable permissions remain distinct while unaffected authorized projects stay usable.

**Tasks:**

- [ ] **OM-13.02-T1** Define authorized company aggregate queries with per-project coverage and independent disclosure checks.
- [ ] **OM-13.02-T2** Build explicit company scope selection, project summaries and safe project drill-down/return navigation.
- [ ] **OM-13.02-T3** Add stable basis/coverage labels and contract-level entry points for knowledge and usage capabilities as they become available.
- [ ] **OM-13.02-T4** Test inaccessible projects, restricted same-project sources, partial collection and unchanged project-default knowledge scope.

<a id="om-13-03"></a>

### OM-13.03 — Follow assigned work across concurrent epics

As a contributor, I want a separate Focus board across my authorized projects, so that I can understand parallel epic work and agent contributions without losing source ownership or attribution gaps.

**Requirements:** FR-4, FR-5, FR-6, FR-15, FR-17, FR-19; NFR-1, NFR-2, NFR-5; AR-07, AR-09, AR-16, AR-17; UX-DR08, UX-DR10, UX-DR13, UX-DR14, UX-DR15, UX-DR16, UX-DR17, UX-DR18, UX-DR26, UX-DR38, UX-DR41, UX-DR44, UX-DR45.

**Depends on:** OM-13.01.

**Acceptance criteria:**

- **Given** confirmed source identity or an authorized mapping, **when** Focus opens, **then** it shows assigned work across explicitly labeled authorized project sections with visible project filters; an unconfirmed mapping warns that assignments may be missing instead of claiming none.
- **Given** several epics and agents contributing concurrently, **when** grouped or combined presentation is selected, **then** explicit epic relations, shared/unlinked/unknown records and source statuses remain intact and combined totals count unique evidence once.
- **Given** an epic group, **when** its progress is inspected, **then** the view distinguishes the viewer's assigned subset from the authorized whole-child context and preserves E10's closure/acceptance semantics.
- **Given** missing epic mapping, stale evidence or revoked work access, **when** the board updates, **then** work remains in an explicit ungrouped/unknown state where authorized, protected counterpart links/counts are withheld, and no source assignment or agent execution is changed.

**Tasks:**

- [ ] **OM-13.03-T1** Implement assignment queries using confirmed identity mappings, with explicit shared/unknown source-identity states.
- [ ] **OM-13.03-T2** Build the separate Focus route and proposed stacked-epic/combined views with persistent project and person context.
- [ ] **OM-13.03-T3** Integrate unique-work/run grouping, explicit ungrouped areas and E10 detail/dependency navigation.
- [ ] **OM-13.03-T4** Verify simultaneous epics, shared runs, unconfirmed identity, partial mappings and cross-project disclosure boundaries.

<a id="om-13-04"></a>

### OM-13.04 — Inspect work through the six observed SDLC stages

As a contributor, I want a kanban presentation of my work, so that I can inspect observed stage evidence while preserving the source workflow and concurrent contributions.

**Requirements:** FR-5, FR-6, FR-15, FR-17, FR-19; NFR-1, NFR-2, NFR-5; AR-07, AR-16, AR-17; UX-DR12, UX-DR13, UX-DR14, UX-DR16, UX-DR17, UX-DR18, UX-DR26, UX-DR38, UX-DR41, UX-DR43, UX-DR45, UX-DR52, UX-DR53.

**Depends on:** OM-13.03.

**Acceptance criteria:**

- **Given** authorized explicit project-stage mappings or artifact evidence, **when** kanban is selected, **then** tickets appear under Plan, Design, Build, Test, Deploy or Maintain with inspectable mapping version/source/time and their original source status.
- **Given** no supported mapping, a blocker or another-stage contribution, **when** a ticket is displayed, **then** unmapped work stays outside the six columns, blockers use evidence-backed badges and concurrent contributions remain separate from the single primary placement.
- **Given** stage order and source transitions, **when** new observations arrive, **then** the view does not require linear movement, infer Build from In progress or Maintain from Done/merge, and offers no drag-to-change source status or assignment.
- **Given** phone/keyboard use or access loss, **when** presentation changes or an item is selected, **then** readable selected/stacked columns and grouped-list equivalents preserve the focused authorized work, filters and unique-ticket count basis.

**Tasks:**

- [ ] **OM-13.04-T1** Implement versioned authorized project-stage mapping configuration and provenance projection, auditing mapping changes.
- [ ] **OM-13.04-T2** Build six-stage kanban, Stage not mapped area, blocker badges and distinct concurrent-contribution indicators.
- [ ] **OM-13.04-T3** Provide phone/keyboard grouped-list parity and links to the same E10 evidence/dependency records.
- [ ] **OM-13.04-T4** Verify nonlinear movement, absent/changed mappings, original status preservation, unique counts and revocation during view changes.

<a id="om-13-05"></a>

### OM-13.05 — Keep live work views accessible and stable during change

As a person reading a changing workspace, I want predictable navigation and updates, so that new observations do not move my focus or disclose data after access changes.

**Requirements:** FR-3, FR-15, FR-17; NFR-1, NFR-2, NFR-3, NFR-5; AR-10, AR-17; UX-DR05, UX-DR06, UX-DR08, UX-DR09, UX-DR19, UX-DR26, UX-DR29, UX-DR30, UX-DR38, UX-DR40, UX-DR41, UX-DR42.

**Depends on:** OM-13.01, OM-13.02, OM-13.03, OM-13.04.

**Acceptance criteria:**

- **Given** a focused disclosure or reading position, **when** new observations arrive, **then** existing content remains stable behind a politely coalesced New updates control; activation focuses the first new item/changed section without per-event screen-reader interruptions.
- **Given** route entry, bounded load-more or a temporary dialog, **when** navigation occurs, **then** title/h1 focus, announced result counts, inert dialog background, Escape and trigger-focus restoration follow the shared interaction contract.
- **Given** revoked scope affecting focused content, **when** access changes, **then** protected content is removed immediately and focus moves to a surviving heading or neutral state without naming restricted records; this overrides stable-reading retention.
- **Given** offline, reconnect, enlarged text or reduced-motion preferences, **when** views render/update, **then** no new protected cached disclosure or queued admin write occurs, reconnect reauthorizes, and essential information/actions remain usable at 320 CSS px and 200% zoom.

**Tasks:**

- [ ] **OM-13.05-T1** Apply shared update-buffering, scope-change and safe-return behavior to S1, company, S2 entry and S10 views.
- [ ] **OM-13.05-T2** Add coalesced announcements, accessible paging and route/dialog focus behavior using the foundation components.
- [ ] **OM-13.05-T3** Implement immediate protected-content removal and explicit offline/reconnect states without duplicating observation projections.
- [ ] **OM-13.05-T4** Run meaningful keyboard, screen-reader, zoom/reflow, reduced-motion and revoked-focus scenarios across the completed work views.
