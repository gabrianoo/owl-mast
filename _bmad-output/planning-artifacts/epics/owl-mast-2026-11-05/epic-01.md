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

- **AC1: Given** a feature mutation requires follow-up work, **when** its database transaction commits or rolls back, **then** the required work record and mutation succeed or fail together.
- **AC2: Given** two processors overlap or one loses its lease, **when** work is claimed and completed, **then** only current ownership may commit completion, retries are bounded/persisted and repeated external effects are idempotent or explicitly reconciled.
- **AC3: Given** a covered successful mutation, **when** its business transaction commits, **then** the audit record or a durable audit-publication intent commits atomically with it and carries actor, tenant/project, object/version, action/outcome and both times without secret payloads; denied and failed attempts are recorded through a separate safe outcome path.
- **AC4: Given** a crash after a successful mutation commits but before audit publication completes, **when** recovery runs, **then** the committed audit intent is published idempotently and the successful mutation cannot disappear from the permitted audit history.

**Tasks:**

- [ ] **OM-01.03-T1** Define the durable-work and minimal audit-envelope contracts, owner APIs and versioning rules consumed by later modules.
- [ ] **OM-01.03-T2** Implement only the work/audit infrastructure tables, atomic business-change/work/audit-intent commit through module APIs and reactive transaction integration; keep failed-attempt audit independent of rolled-back business writes.
- [ ] **OM-01.03-T3** Implement bounded claiming, lease recovery, retry/backoff, failure visibility and authorization recheck hooks; schedule wakeups without an external job service.
- [ ] **OM-01.03-T4** Exercise rollback-before-enqueue, crash-after-commit-before-audit-publication, failed-attempt recording, stale-owner completion, concurrent claims and duplicate effect recovery.

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
