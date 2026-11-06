---
epic: E02
status: planned
review_status: pending-owner-review
scope: v1
---

# Epic E02 — Manage tenants, personal accounts and authorized project access

People retain individual identities and explicit tenant/project/source permissions even when external accounts are shared.

**Epic prerequisites:** E01

This is a planning draft. [Full scope and shared requirements](../../epics.md) apply to every story. Tasks are ordered within a story; its acceptance criteria determine completion. Policy decisions and live-environment approvals remain explicit gates.

<a id="om-02-01"></a>

### OM-02.01 — Sign in with a personal Owl Mast identity

As a contributor, I want to use a local Keycloak-managed account, so that my identity and session remain distinct from shared customer accounts.

**Requirements:** FR-17, FR-19, NFR-1, AR-09, UX-DR25, UX-DR26, UX-DR27

**Depends on:** E01

**Acceptance criteria:**

- **AC1: Given** a configured Keycloak realm/client and invitation policy, **when** a person signs in, **then** Owl Mast binds a stable issuer/subject principal and validates token issuer/audience/expiry.
- **AC2: Given** an expired, revoked or wrong-audience credential, **when** a protected operation is requested, **then** access fails without cached fallback or protected error details.
- **AC3: Given** account creation, recovery or logout is requested, **when** the identity flow completes, **then** the configured Keycloak flow handles the account and Owl Mast records relevant session outcomes without storing passwords.

**Tasks:**

- [ ] **OM-02.01-T1** Resolve realm/client, account invitation/registration and browser login/session/recovery policy for separate frontend/backend deployments; explicitly select the public-origin/routing boundary without inferring it from deployment separation.
- [ ] **OM-02.01-T2** Configure Keycloak and reactive resource-server/login integration for the selected browser model, including redirect/proxy handling, cookie/token boundaries, applicable CSRF/CORS controls and revocation; keep native enrolled credentials separate.
- [ ] **OM-02.01-T3** Implement principal lifecycle and safe sign-in/out/error states in the shell; preserve source-account separation.
- [ ] **OM-02.01-T4** Use Testcontainers with a pinned Keycloak image and synthetic realm/users to exercise browser login/return across separately packaged services, wrong issuer/audience, expiration, logout/revocation and recovery; ensure diagnostics exclude credentials and apply the selected origin/CSRF policy.

<a id="om-02-02"></a>

### OM-02.02 — Create tenant and project membership boundaries

As a administrator, I want to manage tenant-scoped projects and membership, so that customer work remains separated within one installation.

**Requirements:** FR-1, FR-17, NFR-1, AR-08, AR-10, UX-DR08, UX-DR36, UX-DR41

**Depends on:** OM-02.01

**Acceptance criteria:**

- **AC1: Given** the AISQUAD tenant is configured, **when** its two pilot projects are created, **then** project identity and membership are tenant-scoped without conflating their source namespaces.
- **AC2: Given** two synthetic tenants contain identical display names and source keys, **when** records are created and queried, **then** composite identity/authorization boundaries prevent cross-tenant collision or disclosure.
- **AC3: Given** membership is removed during a request or job, **when** the next disclosure or effect is attempted, **then** current authorization is rechecked and protected results are withheld.

**Tasks:**

- [ ] **OM-02.02-T1** Define tenant/project/member identity and schema constraints; qualify transaction-bound PostgreSQL isolation for reactive access.
- [ ] **OM-02.02-T2** Implement authorized project/tenant administration APIs and S8 scope management with audit events.
- [ ] **OM-02.02-T3** Propagate trusted scope across HTTP, MCP, jobs and connection boundaries; reject client-asserted scope escalation.
- [ ] **OM-02.02-T4** Exercise synthetic two-tenant, cross-project, revoked membership and identical-key isolation cases.

<a id="om-02-03"></a>

### OM-02.03 — Map shared external accounts without merging people

As a administrator, I want to map several Owl Mast people to one customer account, so that shared source visibility does not erase individual identity or invent contribution credit.

**Requirements:** FR-4, FR-17, NFR-2, AR-07, AR-09, UX-DR36, UX-DR41, UX-DR45

**Depends on:** OM-02.02

**Acceptance criteria:**

- **AC1: Given** two personal principals share one authorized external account, **when** the mapping is configured, **then** both retain separate Owl Mast IDs and explicitly scoped source bindings.
- **AC2: Given** a source event identifies only the shared account, **when** it is imported, **then** the event remains attributable to that external account until independent evidence identifies an initiating person.
- **AC3: Given** a mapping changes, **when** history is read, **then** old evidence retains its recorded mapping basis/time and credentials are never exposed as identity data.

**Tasks:**

- [ ] **OM-02.03-T1** Implement source-qualified external-account bindings with purpose, authority, effective times and provenance.
- [ ] **OM-02.03-T2** Keep connector credential references separate from user mapping and project visibility grants.
- [ ] **OM-02.03-T3** Provide audited mapping administration and clear shared-account/unknown attribution presentation.
- [ ] **OM-02.03-T4** Verify same visibility for explicitly granted users without granting all connector-visible records to all members.

<a id="om-02-04"></a>

### OM-02.04 — Enforce resource and source permissions through one boundary

As a authorized viewer, I want to receive only currently permitted information, so that shared connections and derived views cannot bypass my access.

**Requirements:** FR-17, FR-19, NFR-1, NFR-6, AR-10, AR-17, UX-DR41

**Depends on:** OM-02.02

**Acceptance criteria:**

- **AC1: Given** a same-project user lacks access to one source record, **when** a read, search, aggregate, history or graph traversal occurs, **then** protected payloads, labels, counts, residuals and links are all withheld.
- **AC2: Given** authorization cannot be verified or a source permission is removed, **when** a cached/indexed derivative is requested, **then** the operation fails closed and new disclosure is prevented.
- **AC3: Given** an adapter or client asks for agent-control authority, **when** its permissions are evaluated, **then** the initial product exposes only observation and explicitly scoped knowledge/admin operations.

**Tasks:**

- [ ] **OM-02.04-T1** Define the authorization port and initial membership/source-resource grant model with a documented owner of authoritative grants.
- [ ] **OM-02.04-T2** Implement policy checks and revocation invalidation boundaries for feature APIs, jobs, MCP and query projections.
- [ ] **OM-02.04-T3** Add reusable negative fixtures for both project directions, unauthorized third user, revoked user and restricted same-project source.
- [ ] **OM-02.04-T4** Verify no permission fallback to company scope, no hidden counters/filter options and no execution capability in public contracts.

<a id="om-02-05"></a>

### OM-02.05 — Approve collection boundaries before enabling live sources

As a project data owner, I want to set what may be collected and where it is processed, so that integrations respect the agreed data-handling boundary.

**Requirements:** FR-18, NFR-6, AR-17, UX-DR25, UX-DR26, UX-DR36, UX-DR41

**Depends on:** OM-02.04

**Acceptance criteria:**

- **AC1: Given** a source has no approved content/destination/retention policy, **when** live ingestion is enabled, **then** activation is blocked with a specific unmet gate while synthetic qualification remains possible.
- **AC2: Given** the adopted full-conversation default and a project with resolved live-ingestion prerequisites, **when** a native exporter or connector is configured, **then** prompts, responses and tool arguments/results are collected by default within permitted scope; explicit project overrides can disable/narrow capture and secret exclusions always apply.
- **AC3: Given** policy changes or a secret-like value is observed, **when** processing occurs, **then** excluded fields are removed before durable payload storage and an audited safe outcome is available.

**Tasks:**

- [ ] **OM-02.05-T1** Record the adopted full-conversation default and resolve A-3's remaining actual-environment permissions, destinations and archive/other-record policies before live customer ingestion; do not invent retention durations.
- [ ] **OM-02.05-T2** Implement versioned collection policy and activation gates shared by connectors, native telemetry and knowledge ingestion.
- [ ] **OM-02.05-T3** Implement default-on conversation capture with project disable/narrow controls for prompts, responses, tool arguments/results and query/context fields; distinguish configured capture from live-source activation and verified coverage.
- [ ] **OM-02.05-T4** Exercise default-on capture, project opt-out and deny/redact behavior through logs, receipts, queues, caches and derived summaries; emit safe policy audit events without conversation bodies.
