---
epic: E19
status: planned
review_status: pending-owner-review
scope: later-evolution
---

# Epic E19 — Evolve tenant scale, permissions and availability

Later deployments can enable the already-planned tenant and availability capabilities without changing the core evidence contracts.

**Epic prerequisites:** E18

This is a planning draft. [Full scope and shared requirements](../../epics.md) apply to every story. Tasks are ordered within a story; its acceptance criteria determine completion. Policy decisions and live-environment approvals remain explicit gates.

<a id="om-19-01"></a>

### OM-19.01 — Operate multiple active tenants

As a installation operator, I want to onboard another isolated tenant, so that the self-hosted foundation can serve a future multi-tenant installation.

**Requirements:** FR-17, FR-20, AR-08, AR-20, UX-DR08, UX-DR36, UX-DR41

**Depends on:** E18

**Acceptance criteria:**

- **AC1: Given** a second active tenant is onboarded, **when** accounts, source bindings, agents, knowledge and usage are configured, **then** the same explicit tenant model isolates every path without duplicating application installations.
- **AC2: Given** tenant-specific limits or export/removal operations are introduced, **when** administration runs, **then** authorization and data ownership remain tenant-bound and one noisy tenant cannot silently starve another.
- **AC3: Given** a single-tenant self-hosted profile is used, **when** the same version starts, **then** it remains usable without a hosted SaaS dependency or billing integration.

**Tasks:**

- [ ] **OM-19.01-T1** Define operator-led tenant onboarding/offboarding and per-tenant configuration over the existing tenant model; leave monetization outside scope.
- [ ] **OM-19.01-T2** Exercise two-real-tenant-equivalent synthetic workloads across all stores, jobs, MCP/OTLP, notifications and audit views.
- [ ] **OM-19.01-T3** Qualify per-tenant quotas/fair processing and export/removal boundaries before external tenant onboarding.
- [ ] **OM-19.01-T4** Document migration from the AISQUAD-only profile and verify the independent single-tenant installation remains supported.

<a id="om-19-02"></a>

### OM-19.02 — Introduce fine-grained OpenFGA authorization

As a administrator, I want to grant different people project/resource visibility, so that shared external accounts can coexist with narrower internal permissions.

**Requirements:** FR-17, AR-09, AR-10, AR-20, UX-DR36, UX-DR41

**Depends on:** OM-19.01

**Acceptance criteria:**

- **AC1: Given** an approved authorization model and migration plan, **when** the OpenFGA adapter is enabled, **then** feature modules continue using the same authorization port and current source restrictions still apply.
- **AC2: Given** tuple synchronization is delayed or policy cannot be verified, **when** a restricted request occurs, **then** the configured fail-closed behavior prevents disclosure and the operator sees a safe diagnostic.
- **AC3: Given** the migration is compared or rolled back, **when** decisions are evaluated, **then** shadow comparison and rollback preserve recorded grants, revocations and audit history.

**Tasks:**

- [ ] **OM-19.02-T1** Model tenant/project/resource and permitted-use relationships; review how source revocation combines with internal grants.
- [ ] **OM-19.02-T2** Implement the optional OpenFGA adapter and idempotent versioned grant synchronization without bypassing source authorization.
- [ ] **OM-19.02-T3** Run shadow comparisons and all original/new negative cases before switching enforcement.
- [ ] **OM-19.02-T4** Document rollback, model migration and outage behavior; add the optional deployment only when this later capability is selected.

<a id="om-19-03"></a>

### OM-19.03 — Run multiple application pods with compatible upgrades

As a operator, I want to roll application updates with redundant replicas, so that availability improves without relying on process-local state.

**Requirements:** FR-3, FR-20, NFR-3, AR-03, AR-11, AR-12, AR-13, AR-20

**Depends on:** E18

**Acceptance criteria:**

- **AC1: Given** two ready application replicas run, **when** requests, MCP calls and background work overlap, **then** scope/session behavior and idempotent claims remain correct without irreplaceable local state.
- **AC2: Given** an update runs with old and new versions overlapping, **when** traffic drains and schemas migrate, **then** readiness, graceful shutdown and expand/contract compatibility prevent application-level interruption under the tested conditions.
- **AC3: Given** the database, identity provider, node or storage fails, **when** availability is assessed, **then** the result distinguishes application redundancy from dependency HA and makes no blanket zero-downtime claim.

**Tasks:**

- [ ] **OM-19.03-T1** Qualify multi-pod sessions/MCP behavior, any blob-volume access-mode constraints and cross-node placement/capacity.
- [ ] **OM-19.03-T2** Implement rolling-update readiness/drain settings and backward-compatible schema/event migration procedures.
- [ ] **OM-19.03-T3** Run overlapping-version, duplicate-worker and connection-drain scenarios with two replicas.
- [ ] **OM-19.03-T4** Define separately scoped PostgreSQL/Keycloak/storage failover decisions if the availability target requires them; preserve the simple POC profile.

<a id="om-19-04"></a>

### OM-19.04 — Extract components only when measurements justify them

As a technical owner, I want to evaluate separate workers or durable workflow services against evidence, so that later scaling decisions solve a demonstrated bottleneck.

**Requirements:** FR-20, AR-02, AR-11, AR-20

**Depends on:** E18

**Acceptance criteria:**

- **AC1: Given** a measured workload or coordination need exceeds the baseline, **when** an extraction proposal is evaluated, **then** it names the problem, baseline, candidate options, operational cost and migration/rollback plan.
- **AC2: Given** a worker or workflow engine is selected in a later decision, **when** in-flight work is migrated, **then** versioned payloads, ownership, idempotency, authorization and audit remain compatible.
- **AC3: Given** no threshold is met, **when** the roadmap is reviewed, **then** the existing modular deployment remains valid and no Temporal/Restate/queue dependency is introduced by default.

**Tasks:**

- [ ] **OM-19.04-T1** Instrument and measure queue age, workload fairness, recovery burden and resource bottlenecks against agreed targets.
- [ ] **OM-19.04-T2** Compare separating the existing worker adapter with workflow-engine options only for demonstrated needs.
- [ ] **OM-19.04-T3** Produce a concrete migration design including in-flight work, duplicate effects, version compatibility and rollback.
- [ ] **OM-19.04-T4** Create implementation stories for the chosen later solution after that decision; keep this story a bounded evaluation deliverable.
