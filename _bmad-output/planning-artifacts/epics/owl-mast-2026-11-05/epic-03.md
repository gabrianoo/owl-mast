---
epic: E03
status: planned
review_status: pending-owner-review
implementation_status: not-started
---

# Epic E03 — Capture and maintain versioned project knowledge

Contributors and existing Notion/Hermes flows create traceable skills and memory without duplicate saves or lost source authority. This is a reviewable planning draft; policy assumptions and storage qualification are not approved by inclusion here.

**Epic prerequisites:** E02

<a id="om-03-01"></a>

### OM-03.01 — Submit project knowledge with immutable version identity

As a contributor, I want to submit a sourced lesson, skill or memory to an authorized project, so that the next person can distinguish recorded evidence from evaluated guidance.

**Requirements:** FR-8, FR-17, FR-18; NFR-1, NFR-2, NFR-3, NFR-6; AR-02, AR-06, AR-07, AR-17; UX-DR20, UX-DR48.

**Depends on:** E02

**Acceptance criteria:**
- Given an authorized project and permitted source material, when a contributor submits knowledge, then the candidate records its kind, exact version, Markdown content, origin, applicability, known contributor/agent, source time and recorded time without implying approval or company publication.
- Given a replayed submission or a corrected source version, when ingestion repeats, then the same source-qualified submission does not create a second independent candidate and a real correction creates a new version linked to the prior version.
- Given an inaccessible source, unauthorized project, excluded secret or unverifiable collection permission, when submission is attempted, then no prohibited content reaches knowledge storage, indexes, diagnostics or duplicate-match responses and the caller receives a safe failure.
- Given the adopted full-conversation default and unresolved A-3 archive/other-record policies or actual-environment permission/destination rules, when configuring a live source, then those remaining prerequisites gate live activation; fixtures do not approve a retention duration.

**Tasks:**
- [ ] **OM-03.01-T1** Add only knowledge item/version, source-qualified submission identity and typed exact-version source/derivation lineage needed for capture; preserve source ownership, applicability, actor/time/evidence basis and explicit missing lineage.
- [ ] **OM-03.01-T2** Implement the authorized submission boundary, collection exclusions and transactional deduplication/version creation through the selected persistence adapters.
- [ ] **OM-03.01-T3** Emit safe creation/failure/correction audit events with actor, project, exact version, outcome and both timestamps for later audit consumption.
- [ ] **OM-03.01-T4** Verify same-key cross-source isolation, duplicate replay, corrected versions, revoked source access and excluded-content handling; record the A-3 pre-live gate.

<a id="om-03-02"></a>

### OM-03.02 — Preserve complete versioned skill packages

As a skill maintainer, I want complete skill files and package identity preserved with the Markdown entry point, so that clients can receive a reproducible skill instead of an incomplete text fragment.

**Requirements:** FR-8, FR-9, FR-18, FR-21; NFR-2, NFR-3, NFR-6; AR-05, AR-06, AR-07, AR-16, AR-17; UX-DR20, UX-DR32, UX-DR48.

**Depends on:** OM-03.01

**Acceptance criteria:**
- Given an authorized package, when it is captured, then an exact package version binds the entry point, manifest, permitted supporting files/assets, file checksums and originating source version; a changed file produces a distinct package version.
- Given a missing file, checksum mismatch, unsafe path, unsupported payload or collection-policy violation, when validation runs, then the package is rejected or explicitly marked incomplete and cannot be presented as a complete deliverable.
- Given a Notion- or Git-owned source package, when Owl Mast stores a permitted copy or derived index, then the source owner and version remain explicit and capture does not write back or silently create a competing source authority.
- Given large or binary assets, when storage is qualified, then the chosen bounded storage contract preserves authorized reads, checksums, backup/removal behavior and declared limits; no unqualified blob service or numeric capacity is implied.

**Tasks:**
- [ ] **OM-03.02-T1** Implement package manifest/file/checksum records and the exact-version association to knowledge records, without adding schemas for unrelated future artifacts.
- [ ] **OM-03.02-T2** Implement completeness, path, content-policy and integrity validation; store supplied scripts as data without executing them.
- [ ] **OM-03.02-T3** Qualify and record storage for large/binary package files against the selected PostgreSQL deployment and permitted external-storage option if needed, including removal and restore boundaries.
- [ ] **OM-03.02-T4** Verify complete packages, changed assets, incomplete imports, corrupt checksums, prohibited content and cross-project package denial.

<a id="om-03-03"></a>

### OM-03.03 — Synchronize permitted Notion knowledge and preserve Hermes capture

As a contributor using Notion and Hermes, I want existing captures to become discoverable project knowledge without saving twice, so that adopting Owl Mast preserves my working process.

**Requirements:** FR-3, FR-8, FR-14, FR-17, FR-18, FR-21; NFR-1, NFR-2, NFR-3, NFR-4, NFR-6; AR-06, AR-07, AR-11, AR-17; UX-DR20, UX-DR31, UX-DR48.

**Depends on:** OM-03.01, OM-03.02

**Acceptance criteria:**
- Given authorized Notion source scopes and a verified Hermes capture path, when a source record is created or changes, then Owl Mast captures its exact source identity/version and permitted content once while Notion remains authoritative for source-owned records.
- Given concurrent source edits, duplicate notifications, late records or a failed sync, when reconciliation resumes, then newer source knowledge is not overwritten, version lineage remains inspectable and failure/last-success/staleness are visible independently per connection.
- Given Claude or Codex creates an authorized Notion page, when the source is synchronized, then that creation does not prove skill reading, approval, native activation or useful reuse and does not require a second manual save.
- Given a source permission is revoked or cannot be verified, when the connector or a reader accesses a synchronized item, then protected content and derived disclosure are withheld; direct Notion access granted outside Owl Mast is documented as a separate boundary.

**Tasks:**
- [ ] **OM-03.03-T1** Inspect the real permitted Hermes-to-Notion capture and source schema, document ownership/write responsibilities and qualify the available Notion synchronization interface before connector implementation.
- [ ] **OM-03.03-T2** Implement the scoped Notion adapter with protected credential references, durable synchronization/reconciliation jobs, source-version conflict handling and safe connection health.
- [ ] **OM-03.03-T3** Map authorized source lessons and complete skills to the existing knowledge/package contracts, preserving source links without bulk migration or duplicate manual capture.
- [ ] **OM-03.03-T4** Verify authorized Hermes capture continuity and Claude/Codex page creation separately from skill reading, plus restart, duplicate, late-edit and source-revocation cases; gate live content on A-3.

<a id="om-03-04"></a>

### OM-03.04 — Evaluate and correct project knowledge lifecycle states

As a project knowledge maintainer, I want to evaluate exact versions and expose conflicts or corrections, so that recipients can judge which guidance is eligible and trustworthy.

**Requirements:** FR-9, FR-13, FR-17; NFR-1, NFR-2, NFR-6; AR-07, AR-10, AR-16, AR-17; UX-DR20, UX-DR32, UX-DR48.

**Depends on:** OM-03.01, OM-03.02

**Acceptance criteria:**
- Given an authorized maintainer or configured validation policy, when an exact candidate version is evaluated, then the resulting lifecycle state records evaluator kind, permitted identity, basis, time and version without treating an automatic evaluation as human review.
- Given conflicting guidance or a correction, when the conflict/supersession is recorded, then the relationship and uncertainty remain visible to authorized readers; the newest text does not silently become truth and previous history is not overwritten.
- Given a stale version, concurrent update or lost maintainer/source permission, when a lifecycle mutation is submitted, then it fails without altering a different version or leaking restricted conflict/duplicate information.
- Given the adopted A-1 validated-only default, when eligibility is evaluated, then only an explicit client inclusion choice permits eligible unvalidated candidates with status/provenance labels; automated validation can approve an exact version under configured checks. Adopted A-2 blocks ordinary retrieval of withdrawn/quarantined versions and promoted derivatives while preserving restricted history; the client inclusion choice cannot override it.

**Tasks:**
- [ ] **OM-03.04-T1** Implement exact-version evaluation, conflict, supersession, withdrawal and quarantine records with permission-checked transitions and append-linked corrections; preserve distinct validation/policy, derivation and supersession lineage rather than rewriting prior versions.
- [ ] **OM-03.04-T2** Expose a current-eligibility query and lifecycle-change event contract usable by retrieval/publication adapters without depending on those later consumers.
- [ ] **OM-03.04-T3** Implement concurrent-version guards and safe audit events for requested, successful, denied and failed lifecycle changes.
- [ ] **OM-03.04-T4** Verify conflicting versions, stale decisions, revoked maintainer/source access, correction history and the adopted A-1 default/explicit-client opt-in; verify adopted A-2 withdrawal/derivative behavior and preserved restricted lineage.

<a id="om-03-05"></a>

### OM-03.05 — Browse and maintain knowledge in the scoped catalog and detail UI

As an authorized contributor or maintainer, I want a knowledge catalog and exact-version detail view, so that I can submit, inspect and maintain guidance with its provenance and lifecycle visible.

**Requirements:** FR-8, FR-9, FR-14, FR-17, FR-21; NFR-1, NFR-2, NFR-5, NFR-6; AR-06, AR-07, AR-10; UX-DR20, UX-DR25, UX-DR26, UX-DR27, UX-DR31, UX-DR32, UX-DR48.

**Depends on:** OM-03.03, OM-03.04

**Acceptance criteria:**
- Given an authorized project, when S3 or S4 opens, then the catalog and exact-version view expose permitted kind, provenance, source authority, applicability, evaluator/lifecycle, conflicts and package completeness with consistent filters and version history.
- Given a submission or maintenance action, when it is saved, then fields validate before submission, pending state prevents duplicate actions, failures retain permitted unsaved input and only the actual result is shown in both themes and supported layouts.
- Given no knowledge, no filter matches, an unavailable source, incomplete synchronization or denied access, when the UI renders, then it distinguishes those states without revealing hidden-match counts or substituting another project's records.
- Given access changes while detail is open, when authorization is rechecked, then protected content, comparisons, source links and history are removed safely; unavailable future measurements are not fabricated as zero or success.

**Tasks:**
- [ ] **OM-03.05-T1** Build authorized catalog/detail read models and bounded filters from the knowledge module, including source lineage, exact versions and package completeness.
- [ ] **OM-03.05-T2** Implement S3/S4 submission, lifecycle review and history presentation using the shared accessible components and explicit save/result behavior.
- [ ] **OM-03.05-T3** Add permission-safe loading, empty, stale, unsupported, failure and revoked-content states, retaining authorized route/filter context.
- [ ] **OM-03.05-T4** Verify submission and maintenance journeys, restricted conflicts, duplicate privacy, keyboard/screen-reader access, both themes and phone reflow without relying on future statistics or promotion modules.
