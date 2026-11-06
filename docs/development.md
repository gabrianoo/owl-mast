# Developing Owl Mast

## Prerequisites

| Requirement | Why |
| --- | --- |
| Any JDK 17+ on `PATH` (to launch the Gradle wrapper) | The wrapper provisions the pinned Eclipse Temurin 27 daemon/toolchain automatically (`gradle/gradle-daemon-jvm.properties`); an installed Temurin 27 is reused. |
| Docker Engine or Docker Desktop reachable by Testcontainers | Integration tests, the gate script's CI parity and `bootTestRun` start disposable PostgreSQL/VectorChord containers. |
| Network access to Maven Central, the Gradle plugin portal and Docker Hub on first build | Dependencies are locked; nothing is vendored. |

No other tool is installed globally. Pins and the evidence behind them are in [toolchain-qualification.md](toolchain-qualification.md).

## Everyday commands

| Command | What it does |
| --- | --- |
| `./gradlew build` | The documented build: compile with Java 27 and Spring Boot 4.1.2, formatting check, Error Prone, unit suite, ArchUnit rules, integration suite, executable jar. CI runs exactly this. |
| `./gradlew :backend:test` | Fast unit/component suite; no containers. |
| `./gradlew :backend:integrationTest` | Container-backed suite (migrations, transactions, health, missing-extension negative case). |
| `./gradlew :backend:spotlessApply` | Reformat sources. |
| `./gradlew :backend:bootTestRun --args='--server.port=8080'` | Run the application locally against a disposable VectorChord container; `GET http://localhost:8080/actuator/health` answers `{"status":"UP"}`. Stop with Ctrl-C; the container is removed. |
| `./gradlew :backend:bootRun` | Run against an existing database; see below. |
| `scripts/verify-quality-gates.sh` | Prove that formatting, Error Prone, Lombok and module-rule gates each fail with a useful diagnostic on an injected violation. |
| `./gradlew :backend:dependencies --write-locks` | Refresh `backend/gradle.lockfile` after changing pins. |

## Running against your own PostgreSQL

The database must be PostgreSQL 18 with VectorChord 1.1.1 preloaded (`shared_preload_libraries=vchord,vector`); the first migration runs `CREATE EXTENSION IF NOT EXISTS vchord CASCADE` and fails explicitly otherwise. Configure through environment variables (no credentials live in the repository):

```sh
export OWLMAST_DATABASE_R2DBC_URL=r2dbc:postgresql://localhost:5432/owlmast
export OWLMAST_DATABASE_JDBC_URL=jdbc:postgresql://localhost:5432/owlmast
export OWLMAST_DATABASE_USERNAME=owlmast
export OWLMAST_DATABASE_PASSWORD='…'
./gradlew :backend:bootRun
```

A disposable database for this purpose:

```sh
docker run --rm -d --name owlmast-db -e POSTGRES_USER=owlmast -e POSTGRES_PASSWORD=owlmast \
  -e POSTGRES_DB=owlmast -p 5432:5432 \
  tensorchord/vchord-postgres:pg18-v1.1.1@sha256:700ff05ebdc7e4afd4dd8442e0684293046c3833677fec326550000a04cf8a91
```

## Container runtime

Integration tests use Testcontainers. When no Docker-compatible runtime is reachable they fail with:

> Owl Mast integration tests require a reachable Docker-compatible container runtime … Tests fail rather than skip.

They are never skipped, so a green `build` always includes the real-database evidence. Testcontainers honours `DOCKER_HOST` and `~/.testcontainers.properties` for remote or rootless engines. CI uses the Docker engine preinstalled on GitHub's `ubuntu-latest` runners.

The VectorChord image's default command preloads the extension; the fixture (`OwlMastPostgres`) restates `shared_preload_libraries=vchord,vector` because Testcontainers replaces the image command.

## Continuous integration

`.github/workflows/ci.yml` runs two jobs on every push to `main` and every pull request, with actions pinned by commit SHA and the Gradle wrapper validated:

1. `build`: `./gradlew build` on Temurin 27 (all gates and both test suites), uploading test reports.
2. `gate-negative-checks`: `scripts/verify-quality-gates.sh`.

## Layout

```
backend/
  build.gradle.kts            Spring Boot 4.1.2, Java 27 toolchain, gates, test suites
  lombok.config               focused-Lombok rules (compile-time)
  gradle.lockfile             locked dependency versions
  src/main/java/com/aisquad/owlmast
    OwlMastApplication.java   entry point
    platform/                 shared kernel: scope, blocking, persistence
    bootstrap/                first feature: api, application, port, adapter.*
  src/main/resources
    application.yaml          environment-driven configuration
    db/migration/V001__…sql   bootstrap-owned schema only
  src/test                    unit, ArchUnit rules and negative fixtures
  src/testFixtures            Testcontainers fixtures for every feature
  src/integrationTest         real-database suite
docs/                         conventions, toolchain evidence, tracking contract
scripts/verify-quality-gates.sh
```
