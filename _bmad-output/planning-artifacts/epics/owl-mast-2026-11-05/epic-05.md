---
epic: E05
status: planned
owner_review: pending
source_plan: ../../epics.md
---

# Epic E05 — Enroll executing machines and native agent clients

**Outcome:** Contributors register their existing executing machines and Claude/Codex clients, select permitted projects, and understand configuration and independently evidenced readiness without making T3 a prerequisite.

**Epic prerequisites:** E02, E04.

The full native-client target is confirmed. The exact enrollment step ceiling remains A-5; personal-alias behavior is the UX proposal, not a shared naming-authority decision. This epic defines enrollment and package contracts; E07/E08 implement the provider packages. Every enrollment, credential, project-binding and alias mutation emits the shared audit contract at the time it happens.

Initial agent access is person-owned: every native enrollment belongs to a named Owl Mast user. Unattended service-identity agent operation is deferred. Personal enrollments and credentials remain separate on shared machines. Ownership establishes responsibility and an authorization boundary, not proof that the owner initiated every observed action. Existing unknown/shared-account imported evidence remains explicit; this choice neither adds agent execution controls nor removes Owl Mast's internal background processing.

<a id="om-05-01"></a>

### OM-05.01 — Register a machine and client without conflating identities

As a contributor, I want to register an existing executing machine and agent client, so that observations can be attributed without merging people, clients, sessions or sandboxes.

**Requirements:** FR-2, FR-4, FR-17, FR-19; NFR-1, NFR-2, NFR-6; AR-07, AR-08, AR-09, AR-14, AR-17, AR-19; UX-DR33, UX-DR36, UX-DR54, UX-DR59.

**Depends on:** E02, E04.

**Acceptance criteria:**

- **Given** an authenticated contributor, **when** they enroll a machine and supported client type, **then** Owl Mast records separate stable tenant-qualified machine, client and principal identities plus configured friendly location; it requires no IP, local path or hardware-secret disclosure.
- **Given** repeated registration or two machines with the same friendly name, **when** requests are retried, **then** an idempotent retry returns the same enrollment and genuinely distinct machines remain distinct by identity.
- **Given** a client later executes elsewhere, **when** an authenticated observation supplies location evidence, **then** the configured profile stays distinct from time-qualified observed location and earlier history is preserved.
- **Given** a revoked principal or another tenant's enrollment ID, **when** registration/update/read is attempted, **then** access fails without leaking the enrollment or treating a sandbox name as isolation proof; successful and failed changes have safe audit outcomes.
- **Given** two people use the same executing machine, **when** they enroll native clients, **then** each enrollment records its own personal owner and grants without merging their credentials; an enrollment without an authorized personal owner is rejected. Observed initiator identity remains separately evidenced or unknown.

**Tasks:**

- [ ] **OM-05.01-T1** Define separate machine/client/enrollment identifiers, required personal owner, configured-location fields and observation-reference contracts; distinguish responsible owner from evidenced initiator and preserve source namespaces.
- [ ] **OM-05.01-T2** Implement authorized idempotent enrollment/update APIs and transactionally reliable audit events.
- [ ] **OM-05.01-T3** Build S5 registration and configured-versus-observed location presentation, including Unknown and Stale states.
- [ ] **OM-05.01-T4** Verify retry, duplicate-name, changed-location, cross-tenant/revocation and shared-machine personal isolation; reject ownerless/service-only native enrollment without inventing initiator attribution.

<a id="om-05-02"></a>

### OM-05.02 — Bind enrolled clients to authorized projects and revocable credentials

As a contributor, I want a reusable authorized client connection, so that my agent can access selected projects without repeating customer credentials each session.

**Requirements:** FR-2, FR-17, FR-18; NFR-1, NFR-5, NFR-6; AR-09, AR-10, AR-14, AR-17, AR-19; UX-DR25, UX-DR26, UX-DR33, UX-DR36, UX-DR41, UX-DR59.

**Depends on:** OM-05.01.

**Acceptance criteria:**

- **Given** an enrolled client and authenticated person, **when** permitted projects and purposes are bound, **then** requests derive tenant/principal/purpose authority from validated credentials and registration; caller-supplied project attributes cannot widen access.
- **Given** two people map to one customer account, **when** they enroll their clients, **then** their Owl Mast identities and grants stay separate and shared customer credentials do not become personal-attribution proof.
- **Given** credential expiry, owner suspension/revocation or project removal, **when** the client next accesses knowledge, submits telemetry/semantic observations or probes readiness, **then** denied scope is rejected and readiness changes without displaying secrets; repair/rotation does not restore revoked rights or fall back to a service identity. Owl Mast does not control whether the external agent keeps running.
- **Given** enrollment instructions, **when** a contributor repeats an ordinary session, **then** the saved connection is reused and source credentials are not requested again; actual steps/help are recorded for A-5 rather than claiming its proposed ceiling has passed.

**Tasks:**

- [ ] **OM-05.02-T1** Qualify person-bound Keycloak authentication/delegation across MCP, hooks and OTLP; document enrollment, rotation, expiry and revocation without unattended service-account enrollment or assuming every exporter refreshes OAuth credentials.
- [ ] **OM-05.02-T2** Implement personal-owner/project/purpose bindings, secret-reference configuration and credential lifecycle endpoints; enforce the intersection of current user permissions and enrollment grants.
- [ ] **OM-05.02-T3** Add project selection, repair/revoke and explicit save/error states to S5 without exposing credential values.
- [ ] **OM-05.02-T4** Test forged project attributes, shared source accounts/machines, owner suspension, expired/revoked grants and audit/redaction across MCP/hooks/OTLP; deny service-identity fallback and keep ownership separate from observed actor evidence.

<a id="om-05-03"></a>

### OM-05.03 — Show observation and knowledge readiness independently

As a contributor, I want to see which integration capabilities actually work, so that a healthy connection does not hide missing telemetry or unread knowledge.

**Requirements:** FR-2, FR-3, FR-17; NFR-1, NFR-2, NFR-3, NFR-4, NFR-5; AR-14, AR-16, AR-18; UX-DR22, UX-DR26, UX-DR33, UX-DR54, UX-DR59.

**Depends on:** OM-05.02.

**Acceptance criteria:**

- **Given** a configured client with no validated observation receipt, **when** S5 renders, **then** observation says configured/awaiting evidence rather than ready, while a separately successful authorized MCP check can establish knowledge connectivity without claiming native skill loading.
- **Given** capability evidence supplied through the defined status interface, **when** a supported observation/delivery check succeeds or fails, **then** S5 shows per-client/project result, last successful time, freshness and safe remediation; unsupported differs from failed, stale and unverified.
- **Given** one shared source fails, **when** dependent clients are listed, **then** all affected capabilities show the same source gap while other project/source capabilities remain usable.
- **Given** denied access or offline status, **when** a readiness view refreshes, **then** protected results are withheld and no check launches an agent or implies its current running location.

**Tasks:**

- [ ] **OM-05.03-T1** Define capability and evidence-receipt status contracts consumed later by ingestion and native adapters; include configured/unknown/unsupported/stale states.
- [ ] **OM-05.03-T2** Implement independent knowledge-connectivity probes and observation-status projection with declared freshness configuration.
- [ ] **OM-05.03-T3** Build the connection-readiness component and S5 per-client/project details with configured and observed location labels.
- [ ] **OM-05.03-T4** Verify status transitions with contract fixtures, partial source failures, expired authorization and absence of execution side effects.

<a id="om-05-04"></a>

### OM-05.04 — Define portable native configuration packages and safe repair

As a contributor, I want consistent installation and repair instructions for my agent, so that standalone and T3-hosted sessions can connect from the executing machine without overwriting my setup.

**Requirements:** FR-2, FR-3, FR-18, FR-19, FR-20, FR-21; NFR-5, NFR-6; AR-14, AR-15, AR-17, AR-18, AR-19; UX-DR22, UX-DR33, UX-DR36, UX-DR59.

**Depends on:** OM-05.02, OM-05.03.

**Acceptance criteria:**

- **Given** a supported native runtime, **when** an enrollment configuration is generated, **then** it describes the authenticated MCP endpoint, native package/hook interface and OTLP receiver configuration using secret references and explicit project/client identities; no separate always-on companion is required by this contract.
- **Given** existing user/project settings and hooks, **when** installation or repair is proposed, **then** the package identifies a reversible scoped merge and validation result, preserving unrelated settings and explaining runtime trust/configuration precedence.
- **Given** standalone or T3-hosted operation, **when** configuration is checked on the actual executing machine, **then** the same integration contracts apply and unsupported inheritance, connectivity or offline-delivery behavior is reported explicitly rather than treated as supported.
- **Given** A-3's remaining live-content permission/destination and archive/other-record-policy prerequisites are unresolved, **when** configuration is prepared, **then** live sensitive ingestion stays gated; examples contain no credentials or private conversation data and do not enable execution controls.

**Tasks:**

- [ ] **OM-05.04-T1** Specify versioned enrollment/package manifests and the MCP, hook and OTLP configuration contracts implemented separately in E07/E08.
- [ ] **OM-05.04-T2** Build secret-free generated setup/readiness instructions and a runtime capability matrix for standalone and T3-hosted modes.
- [ ] **OM-05.04-T3** Define scoped configuration merge, repair, disable/revoke and compatibility checks without editing live user environments during development.
- [ ] **OM-05.04-T4** Validate generated fixtures against existing-settings, unavailable endpoint, unsupported capability and A-3-gated scenarios.

<a id="om-05-05"></a>

### OM-05.05 — Personalize agent appearance without changing identity

As a viewer, I want personal owl aliases and accessible colors for my clients, so that I recognize them while the original agent type and evidence identity remain clear.

**Requirements:** FR-2, FR-4, FR-17; NFR-1, NFR-2, NFR-5; AR-07, AR-09, AR-10; UX-DR15, UX-DR25, UX-DR26, UX-DR33, UX-DR41, UX-DR58.

**Depends on:** OM-05.01, OM-05.02.

**Acceptance criteria:**

- **Given** a client visible to the viewer, **when** the proposed personal alias/color setting is saved, **then** only that viewer's presentation changes; provider/type, source-qualified client identity and all prior evidence remain intact.
- **Given** the proposed 1–32 trimmed visible-character rule, **when** an empty, overlong or control-only alias is submitted, **then** an inline error explains correction; duplicate aliases retain a visible short client ID and colors retain text/check indicators.
- **Given** a save failure or reset, **when** the operation finishes, **then** failure preserves unsaved and previous active values, while successful reset restores type plus short ID and slate marker; the result is audited.
- **Given** revoked client access, **when** appearance is read or edited, **then** the protected setting disappears without leaking the client and no shared naming authority is inferred from the personal setting.

**Tasks:**

- [ ] **OM-05.05-T1** Record the proposed alias validation/personal ownership rules and keep any shared-alias policy as an explicit unresolved decision.
- [ ] **OM-05.05-T2** Implement viewer/client-scoped appearance persistence, validation, save/reset and audit events.
- [ ] **OM-05.05-T3** Build named color selection and alias preview in S5; retain fixed provider/type labeling and accessible agent chips.
- [ ] **OM-05.05-T4** Test duplicate names, validation, failed saves, cross-viewer isolation, contrast and revocation.
