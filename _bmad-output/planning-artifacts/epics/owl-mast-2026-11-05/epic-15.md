---
epic: E15
status: planned
owner_review: pending
source_plan: ../../epics.md
---

# Epic E15 — Receive every eligible work update and return safely

**Outcome:** Users receive distinct eligible work updates, control visible push preferences and return to current authorized evidence on supported devices.

**Epic prerequisites:** E10, E11.

Every observed work update triggering push by default is confirmed. Browser/PWA/native packaging and generic lock-screen preview wording are not yet selected. Qualify the platform before promising delivery support. Distinct source changes must not be silently replaced by digests; this epic creates no external messaging or live schedule during planning.

<a id="om-15-01"></a>

### OM-15.01 — Qualify the notification platform and choose supported packaging

As the product owner, I want evidence of notification support on the intended devices, so that the selected UI packaging can deliver the agreed experience with honest limitations.

**Requirements:** FR-15, FR-17, FR-20; NFR-1, NFR-4, NFR-5, NFR-6; AR-02, AR-12, AR-16, AR-17; UX-DR05, UX-DR06, UX-DR37, UX-DR40, UX-DR55, UX-DR56.

**Depends on:** E10, E11.

**Acceptance criteria:**

- **Given** the actual pilot laptop/tablet/phone browser and OS matrix, **when** browser/PWA push options are qualified, **then** permission, installation, background-delivery, deep-link and revoked-session behaviors are recorded from current documentation and reproducible tests before a packaging choice is accepted.
- **Given** denied or unsupported push, **when** the proposed experience is exercised, **then** in-app updates and evidence remain usable and the limitation is clearly separate from client/agent health.
- **Given** platform constraints on background execution, arrival or notification recall, **when** support is documented, **then** it states those limits without guaranteeing delivery, inventing a silent digest or treating rich notification actions as selected.
- **Given** an unapproved packaging or preview-policy proposal, **when** implementation gates are reviewed, **then** the unresolved choice has an explicit owner and acceptance condition; subsequent transport-specific work does not assume an answer.

**Tasks:**

- [ ] **OM-15.01-T1** Inventory actual pilot devices/browser versions and research current push, installability and background constraints from primary documentation.
- [ ] **OM-15.01-T2** Build a bounded qualification harness for consent/subscription, background arrival and authorized deep-link return using synthetic data.
- [ ] **OM-15.01-T3** Record the supported platform matrix, failure limits and a reviewable browser/PWA packaging recommendation, retaining owner approval as a gate.
- [ ] **OM-15.01-T4** Validate denied/unsupported/revoked-session behavior and the proposed generic-preview policy before transport implementation.

<a id="om-15-02"></a>

### OM-15.02 — Control notification preferences without hiding work updates

As a user, I want explicit event and project preferences, so that I can control interruptions while understanding what the default feed and push behavior include.

**Requirements:** FR-7, FR-15, FR-17; NFR-1, NFR-2, NFR-5, NFR-6; AR-10, AR-17; UX-DR19, UX-DR25, UX-DR26, UX-DR37, UX-DR41, UX-DR55, UX-DR56.

**Depends on:** OM-15.01.

**Acceptance criteria:**

- **Given** an authorized connected project scope, **when** preferences are first presented, **then** every distinct eligible observed work-update kind is enabled for push by default and visible project/kind controls allow explicit opt-out; assignment/person feed filters do not change push eligibility.
- **Given** the proposed knowledge-lifecycle and meaningful connection-failure/recovery categories, **when** defaults are finalized, **then** they are identified separately from the confirmed work-update requirement and remain visible named controls rather than silently narrowing that requirement.
- **Given** consent not requested, denied, unsupported or granted, **when** S9 opens, **then** purpose and current state are explained before a platform permission request; a failed settings save retains the unsaved choice and previous active value.
- **Given** lost access to a project or preference record, **when** controls or feed results refresh, **then** protected project names, event data and counts disappear; successful preference changes and failed authorized attempts produce safe audit outcomes.

**Tasks:**

- [ ] **OM-15.02-T1** Define product notification event kinds, replay identity and explicit preference defaults, separating product changes from raw telemetry packets.
- [ ] **OM-15.02-T2** Implement authorized per-person/project/kind preferences and audit emission without coupling them to view filters.
- [ ] **OM-15.02-T3** Build S9 consent explanation, permission states, explicit save/error behavior and access-safe event/project selectors.
- [ ] **OM-15.02-T4** Verify initial all-update eligibility, opt-outs, failed saves, proposal labeling and revoked-project removal.

<a id="om-15-03"></a>

### OM-15.03 — Dispatch distinct updates through durable authorized work

As a user, I want each eligible observed change delivered independently, so that retries do not multiply events and infrastructure failures do not silently erase updates.

**Requirements:** FR-3, FR-7, FR-15, FR-17, FR-18; NFR-1, NFR-2, NFR-3, NFR-4, NFR-6; AR-10, AR-11, AR-17, AR-18; UX-DR19, UX-DR26, UX-DR37, UX-DR41, UX-DR42, UX-DR55, UX-DR56.

**Depends on:** OM-15.01, OM-15.02.

**Acceptance criteria:**

- **Given** a newly observed eligible tracker, attention, run-state or contribution/evidence change, **when** notification work is created, **then** stable source-event/recipient identity deduplicates replay while each distinct change retains its own source time and notification identity; unchanged polling and token streams do not become work updates.
- **Given** queued dispatch, **when** delivery is attempted, **then** recipient/source rights, active device/session eligibility and current preferences are rechecked; unauthorized or unverifiable events produce no push, including no generic preview.
- **Given** a transient transport error, expired subscription, process restart or uncertain external response, **when** work recovers, **then** durable retry/terminal/uncertain outcomes remain inspectable and bounded; accepted work is not silently dropped, and external arrival is not claimed from a queue record.
- **Given** a burst of distinct eligible updates, **when** the platform groups presentation, **then** application identities remain distinct and no silent digest/throttle discards events; safe previews contain only authorized policy-permitted content and audit records omit subscription secrets.

**Tasks:**

- [ ] **OM-15.03-T1** Implement the event-to-recipient eligibility projection and atomic notification job creation using the existing PostgreSQL job module.
- [ ] **OM-15.03-T2** Implement the selected platform subscription/transport adapter, credential references, revoke/expiry handling and permission rechecks at dispatch.
- [ ] **OM-15.03-T3** Persist dispatch attempts and distinct outcomes with retry/backoff, replay deduplication and safe audit/diagnostic metadata.
- [ ] **OM-15.03-T4** Test duplicate source events, bursts, changed preferences, revoked/ended sessions, pod restart, transport failure and ambiguous external delivery outcomes.

<a id="om-15-04"></a>

### OM-15.04 — Open the current authorized state from a notification

As a user returning from a notification, I want the current relevant evidence and a safe way back, so that an old alert does not expose revoked content or urge an obsolete action.

**Requirements:** FR-5, FR-7, FR-15, FR-17, FR-19; NFR-1, NFR-2, NFR-3, NFR-5; AR-10, AR-16, AR-17; UX-DR26, UX-DR37, UX-DR40, UX-DR41, UX-DR42, UX-DR55, UX-DR56.

**Depends on:** OM-15.03.

**Acceptance criteria:**

- **Given** a valid notification reference, **when** it is opened, **then** current authorization and source/lifecycle state are checked before showing S2/S4/S6/S5 content; resolved attention or withdrawn knowledge is presented in its current permitted state.
- **Given** a revoked or unverifiable target, **when** the notification opens, **then** a neutral unavailable heading and safe return link reveal no old title, source snippet, recipient context or cached protected detail.
- **Given** a supported phone or keyboard/screen-reader user, **when** navigation completes, **then** title/h1 focus, notification time/current-state context and an Other updates since this notification link are accessible; Back restores safe history or the authorized project chooser.
- **Given** offline return or an external source link, **when** it is used, **then** no new protected cache disclosure or execution action occurs and returning from the source tool does not imply completion.

**Tasks:**

- [ ] **OM-15.04-T1** Implement notification-reference resolution with current per-target authorization and lifecycle-aware destinations.
- [ ] **OM-15.04-T2** Build safe route/focus/return behavior and current-state explanations for resolved, superseded, withdrawn and unavailable targets.
- [ ] **OM-15.04-T3** Integrate a scoped updates link without changing notification preferences or exposing hidden event counts.
- [ ] **OM-15.04-T4** Verify old alerts, revoked rights, unavailable projects, offline opening and accessible phone/keyboard return flows.
