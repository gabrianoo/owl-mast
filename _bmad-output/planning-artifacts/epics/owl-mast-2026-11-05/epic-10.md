---
epic: E10
status: planned
owner_review: pending
source_plan: ../../epics.md
---

# Epic E10 — Trace work, runs, contributions and dependencies

**Outcome:** A colleague can follow a source-qualified work item through observed execution and contributions to acceptance evidence, with measured progress and inspectable relationships.

**Epic prerequisites:** E06, E09.

All source facts retain provenance and current disclosure rights. An inferred association, merged PR, completed tracker item, passed check, accepted result and deployment remain different facts. Domain corrections/mappings emit audit events immediately; E16 later provides the full audit browsing surface.

<a id="om-10-01"></a>

### OM-10.01 — Correlate source records without inventing attribution

As a viewer, I want supported links between work, people, agents and contributions, so that I can inspect why records are associated and where attribution is uncertain.

**Requirements:** FR-4, FR-5, FR-17; NFR-1, NFR-2, NFR-3; AR-07, AR-09, AR-17, AR-18; UX-DR13, UX-DR18, UX-DR30, UX-DR41, UX-DR45.

**Depends on:** E06, E09.

**Acceptance criteria:**

- **Given** records from distinct sites/accounts with identical ticket or session strings, **when** correlation runs, **then** their source-qualified identities remain distinct and every relationship carries source/time, evidence basis and confirmed-versus-inferred classification.
- **Given** owner, initiating person, agent, delegation and repository identities differ, **when** a work chain is viewed, **then** each remains distinct and a shared source account or commit author alone cannot establish the initiating person.
- **Given** duplicate, late, contradictory or retracted assertions, **when** they are reconciled, **then** idempotent observations are not multiplied, corrections retain linked history, and unresolved/unlinked evidence remains inspectable without a guessed match.
- **Given** access to a linked source is revoked, **when** a work chain is queried, **then** protected node details, relationship evidence and derived disclosures are withheld without hidden-record counts.

**Tasks:**

- [ ] **OM-10.01-T1** Define Evidence-owned source-qualified work/run/contribution identifiers and typed correlation/assertion contracts consuming the Ingestion observation envelope with provenance and correction links.
- [ ] **OM-10.01-T2** Implement deterministic correlation policies and authorized correction/mapping operations with reliable audit emission.
- [ ] **OM-10.01-T3** Expose permission-filtered evidence-chain queries including unlinked, ambiguous and contradictory records.
- [ ] **OM-10.01-T4** Verify duplicate keys, shared credentials, late corrections, conflicting mappings and revocation across chained results.

<a id="om-10-02"></a>

### OM-10.02 — Inspect each observed task and run independently

As a viewer, I want per-task run evidence, so that implementation, review, retries and delegated work retain their own model, effort, session and execution location.

**Requirements:** FR-4, FR-5, FR-16, FR-17; NFR-1, NFR-2, NFR-4; AR-07, AR-14, AR-16, AR-18; UX-DR18, UX-DR30, UX-DR41, UX-DR46.

**Depends on:** OM-10.01.

**Acceptance criteria:**

- **Given** a ticket with simultaneous implementation/review runs and delegated children, **when** its run history opens, **then** task roles, run/session/delegation identities and retries remain separate; a review label does not claim independent review.
- **Given** observed model, exact effort or machine changes within a session, **when** history is projected, **then** time-qualified segments are preserved and configured/requested values are labeled separately from runtime evidence; summary values show Multiple when appropriate.
- **Given** a missing model/effort/session/location or one missing token direction, **when** the task card renders, **then** that field remains Unknown/Unavailable with safe source/time/coverage information rather than copied current settings or zero.
- **Given** a protected session ID or machine name loses authorization, **when** its detail or copy control is used, **then** disclosure and derived summary are removed; copying a permitted ID never launches or resumes the session.

**Tasks:**

- [ ] **OM-10.02-T1** Define the per-task/per-run read projection with provider-native effort labels, time segments and independent coverage fields.
- [ ] **OM-10.02-T2** Implement current-authorization run-history and permitted full-ID retrieval APIs without flattening parent/child records.
- [ ] **OM-10.02-T3** Build responsive task cards, accessible disclosures and copy feedback using existing evidence-detail primitives.
- [ ] **OM-10.02-T4** Test multiple models/locations, role uncertainty, missing counters, long IDs and revocation during detail/copy use.

<a id="om-10-03"></a>

### OM-10.03 — Calculate progress from explicit evidence

As a viewer, I want inspectable ticket and epic progress bases, so that percentages do not imply acceptance or hide incomplete criteria and child sets.

**Requirements:** FR-5, FR-6, FR-7, FR-17; NFR-1, NFR-2, NFR-3; AR-07, AR-17, AR-18; UX-DR12, UX-DR18, UX-DR30, UX-DR41, UX-DR43, UX-DR44, UX-DR45.

**Depends on:** OM-10.01.

**Acceptance criteria:**

- **Given** measurable ticket criteria, **when** progress is calculated, **then** the result exposes completed/total basis, source and observation time; no criteria or no measurable items produces Unknown, and changed criteria visibly change the denominator.
- **Given** criteria and a separate checklist disagree, **when** progress is viewed, **then** both labeled measures or Basis needs review are shown without an invented combined percentage.
- **Given** an epic child set, **when** the proposed closure summary is built, **then** it shows child tickets closed over known authorized children, names assigned subset versus permitted child set, carries the constant accessible-record label and leaves parent acceptance separate.
- **Given** stale collection, revoked child access or a merged contribution, **when** summaries refresh, **then** coverage and authorized bases update safely; stale data never proves blockage and merge/check/closure never becomes accepted/deployed automatically.

**Tasks:**

- [ ] **OM-10.03-T1** Implement pure ticket-progress policies for measurable, empty, changed and conflicting denominators.
- [ ] **OM-10.03-T2** Implement the proposed epic child-closure projection with named set, deduplication and independent acceptance evidence.
- [ ] **OM-10.03-T3** Build progress-evidence drill-down with basis/source/time and accessible Unknown/conflict states.
- [ ] **OM-10.03-T4** Verify denominator changes, inconsistent checklists, partial collection, permission changes and independent completion dimensions.

<a id="om-10-04"></a>

### OM-10.04 — Inspect the authorized dependency graph and equivalent list

As a viewer, I want a bounded graph and readable relationship list, so that I can understand prerequisites and contributions without losing evidence or exposing restricted work.

**Requirements:** FR-5, FR-6, FR-17, FR-19; NFR-1, NFR-2, NFR-3; AR-05, AR-07, AR-10, AR-17; UX-DR18, UX-DR30, UX-DR41, UX-DR53.

**Depends on:** OM-10.01.

**Acceptance criteria:**

- **Given** ticket dependencies and PR contribution assertions, **when** a neighborhood is requested, **then** graph and list expose the same authorized relations with distinct prerequisite-to-dependent and contributes-to types, explicit/inferred labels and provenance.
- **Given** an authorized visible cycle or collection gap, **when** it is displayed, **then** the explanation is limited to observed relations and does not claim all work is blocked or that incomplete collection proves no dependencies.
- **Given** a phone or keyboard/screen-reader user, **when** they inspect and expand nodes, **then** bounded focus, safe return and equivalent list access expose all permitted information without canvas dragging or tiny labels.
- **Given** access changes during expansion, **when** another neighborhood is fetched, **then** nodes, edges, evidence and counts are reauthorized together; no hidden-node placeholder, edge stub or residual count appears.

**Tasks:**

- [ ] **OM-10.04-T1** Define bounded relation query/paging contracts and graph/list parity rules over PostgreSQL typed assertions.
- [ ] **OM-10.04-T2** Implement authorization-aware expansion and cycle/gap classification without requiring a graph database.
- [ ] **OM-10.04-T3** Build labeled directed graph interactions and the equivalent keyboard/phone relationship list.
- [ ] **OM-10.04-T4** Test contradictory edges, multiple PRs, visible cycles, bounded traversal, graph/list parity and revoked-node suppression.

<a id="om-10-05"></a>

### OM-10.05 — Follow work evidence into source tools safely

As a colleague, I want one coherent work-detail view, so that I can understand the evidence and continue in the existing source tool without Owl Mast taking execution authority.

**Requirements:** FR-5, FR-6, FR-7, FR-15, FR-17, FR-19; NFR-1, NFR-2, NFR-5; AR-07, AR-16, AR-17; UX-DR13, UX-DR14, UX-DR18, UX-DR28, UX-DR30, UX-DR41, UX-DR45, UX-DR52.

**Depends on:** OM-10.02, OM-10.03, OM-10.04.

**Acceptance criteria:**

- **Given** an authorized ticket or epic, **when** S2 opens from a summary or deep link, **then** source-qualified work identity, owner/agent roles, progress, run evidence, contributions and acceptance authority/artifact remain individually inspectable; original source status stays separate from any explicitly evidenced SDLC stage and missing stage mapping remains Unknown.
- **Given** an explicit blocker or request whose text is excluded by collection policy, **when** attention is expanded, **then** the permitted reason/source/time/link and policy explanation remain visible without fetching or inventing excluded text.
- **Given** an allowed external source link, **when** it is opened and the user returns, **then** navigation preserves safe context and does not mark an external action complete; missing/unsupported links are explained and no agent-control action is offered.
- **Given** no linked evidence, unmatched records, stale sources or revoked run access, **when** S2 renders, **then** their states remain distinct, healthy authorized evidence stays usable, and protected cached detail is not substituted.

**Tasks:**

- [ ] **OM-10.05-T1** Compose the S2 query model from the earlier bounded projections without adding a second owner for work or run facts.
- [ ] **OM-10.05-T2** Implement source-qualified ticket chips, work records, evidence sections and safe descriptive source links.
- [ ] **OM-10.05-T3** Add independent acceptance/check/deployment evidence, explicit blocker/request-policy states and a source-status-versus-evidenced-stage slot with mapping provenance.
- [ ] **OM-10.05-T4** Verify authorized deep links, missing links, stale/partial evidence, return context and absence of execution controls.
