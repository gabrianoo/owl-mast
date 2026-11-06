---
epic: E16
status: planned
owner_review: pending
source_plan: ../../epics.md
---

# Epic E16 — Inspect full-system audit and govern retained data

**Outcome:** Authorized people inspect attributable Owl Mast activity and apply collection, retention, removal and revocation policy consistently across primary records, derived data and recovery.

**Epic prerequisites:** E02, E06, E11.

Every earlier mutation story already emits the shared audit contract through its reliable write path. This epic makes that history inspectable and governs retained data; it is not the first audit instrumentation. Full-system coverage is the target. A-3 now selects full capture and 30 active days followed by retained archive, with no automatic archive purge or 30-day knowledge expiry. Archive implementation/recovery, other record-class policies and actual-environment permissions/destinations still require qualification; A-2 applies before live promotion/lifecycle acceptance. No cryptographic immutability or backup-erasure guarantee is invented here.

<a id="om-16-01"></a>

### OM-16.01 — Query full-system audit with explicit coverage

As an authorized operator, I want a consistent audit query across object types, so that I can trace system activity without mistaking incomplete history or failed attempts for success.

**Requirements:** FR-3, FR-12, FR-13, FR-17, FR-18; NFR-1, NFR-2, NFR-3, NFR-6; AR-02, AR-07, AR-10, AR-17, AR-18; UX-DR19, UX-DR26, UX-DR39, UX-DR41, UX-DR51.

**Depends on:** E02, E06, E11.

**Acceptance criteria:**

- **Given** the shared audit records already emitted by feature modules, **when** audit queries are made, **then** they preserve object/type/version, action, requested/successful/failed/unresolved outcome, human/agent/service actor, source/recorded times, reason and permitted causal references without becoming another owner of business state.
- **Given** the complete coverage inventory, **when** coverage is inspected, **then** it accounts for knowledge/skills/evaluations/publications/lifecycle, receipts/load/use, observations/correlations, summaries, enrollment/configuration/policy/aliases and notifications/outcomes; an unimplemented or delayed producer is visibly unsupported/incomplete rather than silently excluded.
- **Given** corrections or failed creation/delivery attempts, **when** history is projected, **then** corrections remain additional linked events and failures do not imply an object or external delivery succeeded; unknown actor/time/causality remains Unknown.
- **Given** restricted actors, objects, recipients or source evidence, **when** records, counts or filters are returned, **then** independent disclosure checks apply and opaque references/order do not reveal hidden gaps or historical payloads.

**Tasks:**

- [ ] **OM-16.01-T1** Inventory every producer/object class against the shared audit event contract and define testable coverage/completeness reporting.
- [ ] **OM-16.01-T2** Implement bounded tenant/project/object/action/actor/time audit queries with independent field and causal-link authorization.
- [ ] **OM-16.01-T3** Add explicit delayed/unsupported/failed/unknown projections and correction links without rewriting authoritative business history.
- [ ] **OM-16.01-T4** Verify producer contract fixtures for all required classes, replay/correction behavior and inference-resistant filtered counts/IDs.

<a id="om-16-02"></a>

### OM-16.02 — Inspect audit timelines and object changes accessibly

As a maintainer or operator, I want system and object-level history views, so that I can understand what changed, why, and which evidence supports it.

**Requirements:** FR-9, FR-11, FR-12, FR-13, FR-15, FR-17; NFR-1, NFR-2, NFR-5, NFR-6; AR-07, AR-10, AR-17; UX-DR19, UX-DR26, UX-DR32, UX-DR39, UX-DR40, UX-DR41, UX-DR42, UX-DR51.

**Depends on:** OM-16.01.

**Acceptance criteria:**

- **Given** a covered object or S11 entry, **when** history opens, **then** chronological bounded rows expose authorized action/object-version/actor-kind/outcome/time with filters and a safe return to the originating object/version.
- **Given** permitted before/after fields, version differences and causal evidence, **when** details expand, **then** labels and source/recorded timestamps remain readable on phone and keyboard, while unavailable/redacted fields never reveal the original value.
- **Given** no events, no matches, incomplete coverage or failed operations, **when** the timeline renders, **then** those states remain distinct and no continuity or creation/delivery claim is fabricated.
- **Given** revoked access, offline mode or new arrivals while reading, **when** the view updates, **then** protected history is removed immediately, no protected cached payload is revealed, and authorized content otherwise preserves focus/position with coalesced updates.

**Tasks:**

- [ ] **OM-16.02-T1** Build S11 filters, bounded activity-list rows, coverage labels and object-history navigation using the existing components.
- [ ] **OM-16.02-T2** Implement accessible authorized diff/version/causal disclosures and stable source/recorded-time presentation.
- [ ] **OM-16.02-T3** Apply safe empty/error/offline/revoked states, route focus and scoped return behavior.
- [ ] **OM-16.02-T4** Test mobile/keyboard timelines, independently restricted actors/diffs, delayed producers and revocation during expanded history.

<a id="om-16-03"></a>

### OM-16.03 — Approve collection and retention policy before live ingestion

As a project data owner or authorized administrator, I want explicit collection and retention policies, so that clients and integrations store only permitted data for an agreed duration.

**Requirements:** FR-1, FR-17, FR-18, FR-20; NFR-1, NFR-4, NFR-6; AR-06, AR-10, AR-13, AR-17, AR-19; UX-DR25, UX-DR26, UX-DR36, UX-DR39, UX-DR41, UX-DR51.

**Depends on:** OM-16.01.

**Acceptance criteria:**

- **Given** an integration or client awaiting live ingestion, **when** its policy is configured, **then** it starts from the adopted full-conversation capture default with project overrides; product/project data owners resolve remaining archive/other-record policies, query/context handling, allowed destinations and actual-environment permissions before live activation. Synthetic qualification uses synthetic content.
- **Given** raw transcript, prompt, tool-output or other sensitive fields, **when** data enters a governed path, **then** collection/redaction rules apply before durable persistence and derivative generation, with rejected or redacted fields excluded from diagnostics and audit previews.
- **Given** the adopted 30-day active conversation window, **when** content reaches its archive boundary, **then** it becomes eligible for verified archiving rather than age-based deletion; project skills/memories/lessons remain under their own lifecycle. Other record-class policies and authorized removal rules remain explicit; no automatic archive expiry or backup-erasure guarantee is inferred.
- **Given** unauthorized policy edits, expired authority or save failure, **when** a change is attempted, **then** active policy remains safe, failure is visible, and a successful policy version is attributable and applied to new work without obsolete in-flight rules silently continuing.

**Tasks:**

- [ ] **OM-16.03-T1** Model Governance-owned versioned collection/retention policies, including backup retention, responsible owners and A-3 live-ingestion gates for source and client paths.
- [ ] **OM-16.03-T2** Define and integrate pre-persistence field allowlists/redaction decisions with ingestion, knowledge, audit and diagnostic contracts.
- [ ] **OM-16.03-T3** Build authorized policy configuration and audited activation showing 30 active days then archive, no automatic archive purge and preserved project knowledge; keep other record-class and backup policy choices explicit.
- [ ] **OM-16.03-T4** Test default-on conversation capture, project opt-out, secret redaction, changed policies during queued work and unauthorized/failed policy saves; distinguish stopping new capture from deleting already retained content.

<a id="om-16-04"></a>

### OM-16.04 — Propagate removal and revocation through derived records

As a project data owner, I want lifecycle and removal decisions applied consistently, so that withdrawn or unauthorized content does not remain exposed through search, summaries, history or queued work.

**Requirements:** FR-10, FR-13, FR-17, FR-18; NFR-1, NFR-2, NFR-3, NFR-6; AR-05, AR-06, AR-07, AR-10, AR-11, AR-17; UX-DR26, UX-DR32, UX-DR39, UX-DR41, UX-DR42, UX-DR48, UX-DR51.

**Depends on:** OM-16.03, E11.

**Acceptance criteria:**

- **Given** current permission revocation or a version subject to the approved lifecycle/removal policy, **when** the event is accepted, **then** disclosure fails closed immediately while durable propagation covers authoritative snapshots, blobs, embeddings/index entries, caches, summaries, receipts/history views and queued notification/publication work as applicable.
- **Given** source-owned knowledge and Owl Mast-derived copies, **when** removal is processed, **then** original source authority is respected; no source deletion is performed merely because a derived copy is removed, and permitted tombstone/audit handling follows the resolved A-2/A-3 policy.
- **Given** duplicate commands, worker interruption or one failed derivative adapter, **when** propagation resumes, **then** work is idempotent, incomplete targets and safe operator remediation remain visible, and no unsupported claim of complete erasure is returned.
- **Given** an earlier external agent/notification copy, **when** lifecycle status is reported, **then** the UI explains that past external copies/actions cannot be recalled and independently governed source access is not falsely reported revoked.

**Tasks:**

- [ ] **OM-16.04-T1** Define the authorized removal/revocation event and target inventory with separate immediate disclosure denial and asynchronous cleanup outcomes.
- [ ] **OM-16.04-T2** Implement idempotent PostgreSQL-backed propagation jobs and per-target adapters/contracts for primary and derived storage.
- [ ] **OM-16.04-T3** Add inspectable safe progress/failure/audit records and ensure query/dispatch paths consult current eligibility during cleanup.
- [ ] **OM-16.04-T4** Test index/cache/summary/history leakage, interrupted cleanup, duplicate commands, source-authority boundaries and unrecoverable external copies.

<a id="om-16-05"></a>

### OM-16.05 — Preserve governance during replay and snapshot recovery

As an operator, I want restored or replayed data revalidated before serving, so that recovery cannot silently resurrect expired, withdrawn or unauthorized information.

**Requirements:** FR-3, FR-13, FR-17, FR-18, FR-20; NFR-1, NFR-2, NFR-3, NFR-4, NFR-6; AR-07, AR-11, AR-13, AR-17, AR-18; UX-DR26, UX-DR39, UX-DR41, UX-DR42, UX-DR51.

**Depends on:** OM-16.03, OM-16.04.

**Acceptance criteria:**

- **Given** late source events or replay after an interruption, **when** records are reprocessed, **then** the current collection/lifecycle policy and relevant revocation/removal state are applied before recreating derived content; older events cannot silently reinstate withdrawn access.
- **Given** a snapshot predating a policy/removal change, **when** the application restores, **then** the Governance-owned recovery gate withholds protected serving and external dispatch until authoritative policy/permission, knowledge eligibility and effect outcomes are reconciled; the recovery design identifies how changes newer than the snapshot are recovered or marks the unresolved coverage explicitly.
- **Given** snapshot retention or deletion limitations, **when** removal status is reported, **then** online cleanup, retained recovery copies and eventual backup expiry are distinguished according to the approved policy; no immediate selective erasure from immutable snapshots is promised.
- **Given** a recovery qualification failure, **when** health/readiness and audit are inspected, **then** affected data remains unavailable with safe remediation and known recovery gaps, while no unchosen RPO/RTO or successful restore is claimed.

**Tasks:**

- [ ] **OM-16.05-T1** Specify Governance-owned replay ordering/current-policy rules and the shared restore quarantine/reconciliation/release contract consumed by protected reads, dispatch and readiness, including state newer than the selected snapshot.
- [ ] **OM-16.05-T2** Implement the single Governance-owned recovery quarantine/release gate and idempotent reconciliation of lifecycle/removal/permission state and effect outcomes via owner APIs; reads and external dispatch consume this gate before resuming. OM-18.02 qualifies this implementation rather than creating a second release authority.
- [ ] **OM-16.05-T3** Document governed snapshot retention/expiry and removal-reporting limits alongside the operational restore runbook.
- [ ] **OM-16.05-T4** Verify synthetic restore-before-revocation, replay-before-withdrawal, missing policy evidence and incomplete cleanup cases without creating live backup schedules.


<a id="om-16-06"></a>

### OM-16.06 — Archive conversations after 30 days without losing knowledge

As a project contributor, I want older conversations archived and still retrievable, so that active storage stays manageable without losing project knowledge or its supporting evidence.

**Requirements:** FR-3, FR-8, FR-11, FR-13, FR-17, FR-18, FR-20; NFR-1, NFR-2, NFR-3, NFR-6; AR-06, AR-07, AR-10, AR-11, AR-13, AR-17; UX-DR19, UX-DR36, UX-DR39, UX-DR41, UX-DR42, UX-DR48.

**Depends on:** OM-16.05.

**Acceptance criteria:**

- **Given** conversation/tool content reaches the documented 30-day active boundary, **when** archive processing runs, **then** it preserves the content and stable identities, provenance, message/turn/tool relationships and work/knowledge links; it does not delete skills, memories or lessons or automatically expire archived content.
- **Given** archive writing, verification or locator publication fails, **when** recovery retries the job, **then** an intact readable copy remains and the operation resumes idempotently; active content is not released before durable archive integrity and authorized readback are verified.
- **Given** an authorized person follows an older evidence link, **when** its content is archived, **then** metadata remains discoverable and content can be retrieved/restored through the owning module with current source/project checks; archived, retrieving, unavailable and deleted states are distinct and no direct object URL bypasses access control.
- **Given** revocation, authorized removal or a policy change races with archiving or retrieval, **when** the next disclosure or durable transition occurs, **then** current policy is enforced and archive retries/restores cannot resurrect removed content or withdrawn access.
- **Given** an isolated recovery exercise includes archived conversations, **when** storage and metadata are restored, **then** integrity and evidence links are verified alongside active records and curated knowledge; archive storage alone is not claimed as a backup or a no-loss guarantee.

**Tasks:**

- [ ] **OM-16.06-T1** Define the archive contract through the evidence-owning module API: immutable content/version identity, checksum, locator/status, policy version and the 30-day clock for late arrivals and long-running sessions; qualify storage without adding a mandatory separate service.
- [ ] **OM-16.06-T2** Implement database-backed idempotent archive jobs with write/verify/publish transitions, integrity/readback checks and safe active-copy release only after a durable archive is reachable; preserve recovery checkpoints and audit outcomes.
- [ ] **OM-16.06-T3** Preserve searchable authorized metadata and stable evidence links; implement permission-checked archive read/restore and archived/retrieving/unavailable presentation in existing detail views without treating archival as knowledge approval.
- [ ] **OM-16.06-T4** Propagate revocation/removal/policy changes across archive metadata and payloads; cover archive inventory, credentials/configuration references and integrity checks in recovery procedures without promising unsupported snapshot erasure.
- [ ] **OM-16.06-T5** Verify the 30-day boundary, late data, duplicate jobs, failed/corrupt archive writes, crash between verification and locator publication, retrieval denial and restore; assert project knowledge and its evidence links survive archiving and no age-only archive purge occurs.
