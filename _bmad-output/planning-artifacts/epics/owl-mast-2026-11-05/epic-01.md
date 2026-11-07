---
epic: E01
status: planned
review_status: pending-owner-review
scope: v1
---

# Epic E01 — Install and operate a reproducible Owl Mast workspace

An operator can build, start and inspect a reproducible deployment with the agreed engineering standards.

**Epic prerequisites:** None

This is a planning draft. [Full scope and shared requirements](../../epics.md) apply to every story. Tasks are ordered within a story; its acceptance criteria determine completion. Policy decisions and live-environment approvals remain explicit gates.

<a id="om-01-01"></a>

### OM-01.01 — Bootstrap the supported Java application

As a maintainer, I want to build a minimal runnable modular application, so that subsequent features share one verified toolchain.

**Requirements:** FR-20, AR-01, AR-02, AR-03, AR-04

**Depends on:** None

**Acceptance criteria:**

- **AC1: Given** a clean checkout and supported toolchain, **when** the documented build runs, **then** Java 27 application code and Spring Boot 4.1.2 compile through Gradle Kotlin DSL and a minimal health endpoint starts.
- **AC2: Given** a deliberately invalid module dependency or formatting/static-analysis violation, **when** CI runs, **then** the relevant gate fails with a useful diagnostic; feature packages own interfaces and persistence.
- **AC3: Given** reactive request and database paths, **when** context crosses asynchronous boundaries, **then** tenant/security context is explicit and blocking adapters are bounded; no ThreadLocal-only authorization assumption is introduced.
- **AC4: Given** a supported local/CI container runtime, **when** the foundational integration suite runs, **then** Testcontainers starts an isolated PostgreSQL/VectorChord image with its required pgvector dependency, exercises the actual migration/transaction path and cleans up; missing extension support or an unavailable required test runtime fails explicitly.

**Tasks:**

- [ ] **OM-01.01-T1** Qualify and pin Gradle/JDK/Lombok/formatter/analyzer/Testcontainers compatibility and the local/CI container runtime; record evidence and dependency locks without copying stale ConvaDesk pins.
- [ ] **OM-01.01-T2** Create the minimal Spring application and feature/module convention with explicit ports; create only bootstrap-owned schema objects.
- [ ] **OM-01.01-T3** Configure formatting, static analysis, dependency/architecture verification and CI build gates; document focused Lombok/records and functional composition conventions.
- [ ] **OM-01.01-T4** Establish reusable Testcontainers PostgreSQL/VectorChord fixtures with pinned images and required extension configuration; exercise clean build/start, actual migrations and a representative reactive transaction/context test, and publish developer/CI commands.

<a id="om-01-02"></a>

### OM-01.02 — Install optional state and identity dependencies

As a operator, I want to install Owl Mast with bundled or existing dependencies, so that a home-server or AWS Kubernetes environment can run the same product.

**Requirements:** FR-20, AR-05, AR-09, AR-12, AR-13

**Depends on:** OM-01.01

**Acceptance criteria:**

- **AC1: Given** a qualified Kubernetes/storage target, **when** the documented package is installed with bundled dependencies, **then** PostgreSQL with VectorChord and Keycloak have explicit health/readiness and durable-volume configuration.
- **AC2: Given** either bundled dependency is disabled, **when** external connection values are supplied, **then** the application uses that compatible instance; missing values fail validation and disabling the bundle does not disable authentication.
- **AC3: Given** PostgreSQL is shared for the POC, **when** applications connect, **then** Owl Mast and Keycloak use separate databases/principals and restricted grants; VectorChord indexes are used and pgvector remains its allowed dependency.

**Tasks:**

- [ ] **OM-01.02-T1** Select and document the installation packaging and compatible immutable image/chart pins; validate optional-dependency values and existing-secret references.
- [ ] **OM-01.02-T2** Package the backend and independently optional PostgreSQL/VectorChord and Keycloak with probes, resources and external connection settings; define separate frontend deployment/image/routing values for the shell artifact delivered by OM-01.04.
- [ ] **OM-01.02-T3** Configure persistent-volume ownership and safe upgrade/uninstall retention behavior; leave snapshot cadence/provider decisions explicit.
- [ ] **OM-01.02-T4** Validate bundled/bundled, bundled/external, external/bundled and external/external configurations using synthetic data; check independent frontend/backend image and routing values, then publish secret-free examples. Complete the real frontend artifact smoke check in OM-01.04.

<a id="om-01-03"></a>

### OM-01.03 — Recover accepted background work and record mutation evidence

As a operator, I want to recover committed processing after pod replacement, so that accepted work is not lost when the single application instance restarts.

**Requirements:** FR-3, NFR-3, NFR-6, AR-02, AR-07, AR-11, UX-DR51

**Depends on:** OM-01.01

**Acceptance criteria:**

- **AC1: Given** a test-owned fixture module that changes its own business row and enqueues follow-up work through the jobs owner API in one scoped transaction, **when** that transaction commits, or rolls back for any reason including an error raised after the enqueue call, **then** the business row and the work record both exist after commit and neither exists after rollback.
- **AC2: Given** pending work, two processors claiming concurrently, or a lease that expires before its holder finishes, **when** work is claimed, reclaimed and completed, **then** each item has at most one current lease holder; a completion or failure write from a holder whose lease expired or was reclaimed is rejected and changes nothing; a repeated external effect after reclaim is either applied once through an idempotency key derived from the work item or leaves the item in an explicit outcome-uncertain state awaiting reconciliation; and no item is marked succeeded without a recorded effect outcome.
- **AC3: Given** a covered mutation (any mutation made through the audited-mutation API; later feature stories declare which of their mutations are covered), **when** its business transaction commits, **then** a durable audit-publication intent commits in the same transaction carrying envelope version, event id, actor kind (human, agent, service or system) and actor id or explicit Unknown, tenant, project or explicit Unknown until OM-02.02 supplies project identity, object type/id/version, action, outcome, occurred time and recorded time with timezone, and correlation id. The envelope has no free-form payload field, and a secret value planted in the business input appears in no audit row, work record or log line. **Given** a business transaction that rolls back or an operation that is denied, **then** a failed or denied outcome record commits in a separate transaction, survives the rollback, and creates no business row and no succeeded record.
- **AC4: Given** a fault injected after a covered mutation's transaction commits and before its audit intent is published, **when** recovery runs, including running twice, **then** exactly one audit record exists for that event id in the audit-owned history, readable through the audit module's internal query API, and once recovery completes no committed covered mutation lacks its audit record.
- **AC5: Given** a handler that fails, **when** it is retried, **then** attempt count, next-attempt time from a capped backoff and a safe failure reason persist across restarts; after the configured maximum attempts (default stated in the contract) the item enters a terminal failed state that an authorized operator can list with tenant, work type, attempt count and safe reason, but without payload contents.
- **AC6: Given** non-terminal work and unpublished audit intents when the application process stops, **when** a new application instance starts against the same database, **then** all of them are claimed and finished without manual action. This story proves process restart with Testcontainers only; live Kubernetes pod-replacement qualification belongs to OM-18.02 (AC2, T3), and this story claims no Kubernetes recovery support.
- **AC7: Given** the authorization recheck port at dispatch, **when** it denies or cannot decide, **then** the handler is not invoked and the item records a safe denied or blocked outcome; until OM-02.04 supplies the real port, the default allows only handlers registered as tenant-internal system work and denies all others.
- **AC8: Given** work and audit records for two synthetic tenants, **when** processors claim and the audit query runs under one tenant's scope, **then** each record is processed only under its own tenant's scope and none is returned or completed under the other's.
- **AC9: Given** a later feature module, **when** it enqueues work or records audit, **then** it can do so only through the published, versioned work-item and audit-envelope contracts (Java API types plus a contract document with a compatibility rule for added fields and versions), enforced by module-rule and compatibility tests; processors are woken only by in-process Spring scheduling, with no external scheduler, broker or worker service.

**Tasks:**

- [ ] **OM-01.03-T1** Define and document the versioned durable-work and audit-envelope contracts (AC3 fields; outcome and actor-kind vocabularies aligned with OM-16.01; a compatibility rule for added fields and versions), the audited-mutation and enqueue owner APIs, the backend service identity used by processors, and the authorization recheck port with its fail-closed default.
- [ ] **OM-01.03-T2** Implement only the jobs- and audit-owned infrastructure tables; atomic business-change/work/audit-intent commit through module APIs and reactive transaction integration; the idempotent audit-intent publisher; and failed/denied outcome recording in a separate transaction independent of rolled-back business writes.
- [ ] **OM-01.03-T3** Implement tenant-scoped bounded claiming, lease expiry and reclaim, persisted retry/backoff with terminal failure, an operator failure listing without payloads and the dispatch-time authorization recheck; wake processors with in-process Spring scheduling only.
- [ ] **OM-01.03-T4** Exercise, with Testcontainers PostgreSQL and a test-owned fixture module: rollback before and after enqueue, fault-injected crash after commit before audit publication with repeated recovery, failed and denied attempt recording, secret non-disclosure, stale-owner completion, concurrent claims, duplicate effect recovery, retry exhaustion, process-restart recovery, fail-closed authorization and two-tenant isolation.

<a id="om-01-04"></a>

### OM-01.04 — Open an accessible workspace shell

As a contributor, I want to navigate a consistent responsive workspace, so that feature views can be added without losing scope, readability or accessibility.

**Requirements:** FR-15, FR-20, NFR-5, AR-02, AR-04, AR-12, UX-DR01, UX-DR02, UX-DR03, UX-DR04, UX-DR05, UX-DR06, UX-DR07, UX-DR08, UX-DR09, UX-DR25, UX-DR26, UX-DR27, UX-DR28, UX-DR40, UX-DR42

**Depends on:** OM-01.01

**Acceptance criteria:**

- **AC1: Given** the UI framework decision is recorded, **when** the shell is rendered, **then** the accepted owl asset and exact light/dark tokens, typography, spacing and system-theme override are preserved.
- **AC2: Given** keyboard, screen reader or enlarged-text interaction, **when** navigation or a dialog changes context, **then** title/focus/labels/return behavior remain usable at 320px and 200% zoom with visible 44px controls.
- **AC3: Given** a route is loading, offline, denied or unsupported, **when** its state changes, **then** distinct safe messages appear, protected content is not newly exposed from cache, and pending operations never show invented success.
- **AC4: Given** separately packaged frontend and backend artifacts, **when** a supported frontend/backend version pair is built, tested or deployed, **then** neither requires bundling the UI into the backend image; the documented API compatibility policy is checked and incompatible pairs are detected before rollout.

**Tasks:**

- [ ] **OM-01.04-T1** Qualify the recommended React/TypeScript/Vite seed and pins; create the independent frontend build/test/image pipeline and API compatibility policy, retaining browser authentication/origin and push support as explicit qualification gates.
- [ ] **OM-01.04-T2** Implement shell navigation, scope/period context, accepted logo, theme/tokens and common settings/state/action/link primitives.
- [ ] **OM-01.04-T3** Implement focus restoration, accessible loading/error/empty patterns and stable New updates interaction primitives.
- [ ] **OM-01.04-T4** Validate component behavior, API contract compatibility, independent frontend/backend build artifacts and a focused browser-to-backend smoke path; check contrast, keyboard flow, screen-reader labels, reduced motion and responsive layouts against DESIGN.md. Real authenticated journeys follow in E02/E18.
