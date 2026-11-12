# Owl Mast

Owl Mast connects observed engineering work to reusable, authorized knowledge for people and their Claude/Codex agents. The product contract is the [specification](_bmad-output/specs/spec-owl-mast/SPEC.md) with its adopted PRD, architecture, UX and epics; engineering progress lives in [GitHub Issues and the Project](docs/engineering-tracking.md).

## Build and run

Prerequisites: a JDK 17+ to start the Gradle wrapper (it provisions the pinned Temurin 27 itself) and a Docker-compatible runtime for the integration suite.

```sh
./gradlew build                                   # compile, gates, unit + integration suites
./gradlew :backend:bootTestRun --args='--server.port=8080'   # run with a disposable VectorChord database
curl http://localhost:8080/actuator/health        # {"status":"UP"}
```

Details, environment variables for an external database and CI parity: [docs/development.md](docs/development.md). Conventions enforced by the build: [docs/engineering-conventions.md](docs/engineering-conventions.md). Pinned toolchain and the evidence behind each pin: [docs/toolchain-qualification.md](docs/toolchain-qualification.md). Durable background work and the audit envelope that later features build on: [docs/durable-work-and-audit-contract.md](docs/durable-work-and-audit-contract.md).

The web client is a separate artifact in `frontend/` (Node 24.21.0, React + TypeScript + Vite):

```sh
cd frontend && npm ci && npm run dev          # shell on http://localhost:5173, proxying /api to the backend above
npm run lint && npm run typecheck && npm test && npm run build && npm run test:e2e
```

Pins, commands, accessibility evidence and deferrals: [docs/frontend.md](docs/frontend.md). The frontend/backend version policy and its pre-rollout check: [docs/api-compatibility.md](docs/api-compatibility.md).

## Stack

Java 27 application code, Spring Boot 4.1.2 (WebFlux, R2DBC, Flyway, Actuator), Gradle 9.8.2 with Kotlin DSL, PostgreSQL 18 with VectorChord (pgvector only as its required dependency), Testcontainers. One modular reactive backend plus an independently built and packaged React/TypeScript/Vite web shell (OM-01.04; never bundled into the backend image) and Kubernetes packaging (OM-01.02).

## Installation

The Helm chart in `deploy/helm/owl-mast` packages the backend and the frontend image with independently optional PostgreSQL/VectorChord and Keycloak bundles. Pins, the secret contract, the four bundled/external combinations and retention behaviour are documented in [docs/installation.md](docs/installation.md); `scripts/verify-install-package.sh` runs the packaging checks.
