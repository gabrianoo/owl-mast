# Epic 1 Context: Install and operate a reproducible Owl Mast workspace

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

E01 gives an operator a reproducible deployment of Owl Mast built on the agreed engineering standards: one verified Java 27 / Spring Boot 4.1.2 toolchain, a modular reactive backend with explicit module ownership, optional bundled state/identity dependencies, durable background work with atomic audit, and an independently built accessible web shell. Everything later in the plan (identity, knowledge, observation, views) assumes this foundation exists and that its build, test and dependency gates are enforced in CI. E01 has no prerequisites and is the first priority (P1 - Foundation).

## Stories

- Story 1.1 (OM-01.01): Bootstrap the supported Java application
- Story 1.2 (OM-01.02): Install optional state and identity dependencies
- Story 1.3 (OM-01.03): Recover accepted background work and record mutation evidence
- Story 1.4 (OM-01.04): Open an accessible workspace shell

## Requirements & Constraints

- Reproducibility: an authorized pilot operator must be able to reproduce the supported setup from the repository and documented prerequisites alone; public-release packaging is a separate later gate.
- Toolchain: Java 27 application code, Spring Boot 4.1.2, Gradle Kotlin DSL build scripts (Kotlin is the build DSL, not the application language). Every other dependency, plugin, JDK distribution/patch, container image and tool version must be qualified against current official documentation and executable checks before it is pinned; never copy the older ConvaDesk reference pins (Java 25 / Boot 3.5 / Maven / Lombok 1.18.46 / pgvector native indexes).
- Reactive baseline: WebFlux/Reactor with R2DBC persistence is the seed to qualify. No blocking calls on event-loop threads, no detached subscriptions inside application services, bounded isolated adapters with deadlines and backpressure for unavoidable blocking SDKs. Tenant/security context must be explicit across async boundaries and database scope bound to the actual connection/transaction; a ThreadLocal-only authorization assumption is forbidden.
- Engineering standards: package by feature, functional composition and immutable values, concise records and focused Lombok (no blanket setters/toString/equality), readable guard clauses. CI enforces qualified formatting, static analysis, dependency/module rules and (later) independent web/API compatibility. Violations must fail with a useful diagnostic.
- Testing: Testcontainers with real pinned PostgreSQL/VectorChord images including the required pgvector dependency, exercising actual migrations and reactive transactions; fast unit/component tests retained. Missing extension support or an unavailable required container runtime must fail explicitly, never silently skip or substitute a database.
- Data ownership: only a story's owning module creates or mutates its schema objects and records; the bootstrap creates only its own infrastructure schema; feature packages own their interfaces and persistence; cross-feature access goes through public operations, ports or versioned events, never shared-table joins.
- Deployment: Kubernetes target, single application instance accepted for the POC, PostgreSQL/VectorChord and Keycloak independently optional bundled dependencies (disable = must supply compatible external instance), separate logical databases/principals when sharing PostgreSQL, PVC-backed state outside pods, frontend and backend as independent artifacts/images with an API compatibility gate (never bundle UI into the backend image).
- Durable work/audit: business change, required work record and audit record (or durable audit-publication intent) commit atomically; failed/denied attempts use a separate safe outcome path; PostgreSQL owns versioned work state, leases, bounded retries and terminal outcomes; Spring scheduling only wakes processors; processing is at-least-once with deduplicated or reconciled effects.
- Diagnostic safety: no credentials, secrets or protected payloads in logs, errors, metrics labels or diagnostics; explicit denied/stale/unavailable/unsupported/unknown states.
- Accessibility and UX (shell story only): preserve the accepted owl asset, exact light/dark tokens, typography, spacing, system-theme override, 320px/200% zoom usability, 44px controls, focus restoration and distinct safe loading/offline/denied/unsupported states.
- A planned task is never permission to ingest customer data, create external accounts, schedule backups or publish a release.

## Technical Decisions

- Paradigm: modular monolith with ports and adapters; one Spring backend deployable containing API, MCP/OTLP receivers (later) and bounded background processing. Dependency direction: inbound adapters -> feature public API -> application operations -> pure domain / consumer-owned ports <- outbound adapters; cross-feature dependencies acyclic and only via public APIs.
- Feature package seed (ownership, not frozen names): access, enrollment, connections, ingestion, evidence, knowledge, retrieval, usage, notifications, audit, governance, jobs. E01 touches only bootstrap/infrastructure, jobs (durable work) and audit envelope contracts.
- Vector storage: VectorChord indexes with pgvector allowed only as the required type/operator dependency (CREATE EXTENSION vchord CASCADE); never pgvector HNSW/IVFFlat indexes.
- Authorization: the access module owns an initial replaceable authorization port; OpenFGA is later evolution. Scope is derived from validated identity, rechecked at every operation and side-effect boundary, failing closed.
- Background work: PostgreSQL-backed durable work with claims/leases/retries behind module interfaces; no broker, workflow engine (Temporal/Restate) or separate worker service initially.
- Spring AI (2.0.x line) only when AI is actually needed; it is not part of the bootstrap.
- Deferred qualification owned by E01 stories: OM-01.01 owns Gradle wrapper, JDK distribution/patch, reactive persistence baseline, Lombok/formatter/analyzers, Testcontainers and module-library pins; OM-01.02 owns packaging, Kubernetes target, image/chart pins and external-service configuration; OM-01.03 owns durable-work and audit envelope versions and the transaction adapter; OM-01.04 owns frontend framework/pins and web/API compatibility contracts. Each owner publishes its contract once before consumers rely on it.
- Verified planning evidence (not executed proof): Boot 4.1.2 supports Java 17-27 and Gradle 9.x; Gradle 9.8.x adds Java 27 toolchain support; Lombok 1.18.48 adds JDK 27 support; Spotless/google-java-format and ArchUnit are evaluated candidates; Boot 4.1.2 provides Testcontainers service connections including R2DBC for PostgreSQL containers. All require executable re-verification in OM-01.01-T1.

## Cross-Story Dependencies

- OM-01.02, OM-01.03 and OM-01.04 all depend on OM-01.01's published toolchain, build conventions and Testcontainers fixtures.
- OM-01.02 packages the backend and defines frontend deployment values but the real frontend artifact smoke check belongs to OM-01.04.
- OM-01.03 publishes the durable-work/audit contracts consumed by every later mutating feature (E06, E11, E15, E16).
- Browser authentication/origin/session qualification belongs to OM-02.01, not E01. Live collection, retention and recovery gates are later prerequisites and do not block synthetic foundation qualification.
- E02 and all later epics depend on E01; E18 acceptance re-verifies the E01 reproduction evidence.
