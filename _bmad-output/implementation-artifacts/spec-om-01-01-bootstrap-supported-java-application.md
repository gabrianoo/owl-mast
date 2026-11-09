---
title: 'OM-01.01 — Bootstrap the supported Java application'
type: 'feature'
created: '2026-11-06'
status: 'in-review'
route: 'dispatch'
review_loop_iteration: 2
baseline_commit: '063ad881940a1621736a842eb1c8ffe1bafb0447'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
  - '{project-root}/docs/engineering-tracking.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The repository holds only planning documents; no verified Java 27 / Spring Boot 4.1.2 toolchain, application skeleton, quality gates or real-database test fixtures exist, so every later story would improvise its own.

**Approach:** Qualify and pin the toolchain from current official sources with executable checks, then add a minimal modular reactive backend (health endpoint, explicit scope/blocking/transaction primitives, bootstrap-owned schema), enforced formatting/static-analysis/module gates with negative diagnostics, and reusable VectorChord Testcontainers fixtures with real migrations. Tracking identifiers: GitHub issue #20 (OM-01.01), epic #1 (E01).

## Boundaries & Constraints

**Always:** Preserve AD-1–AD-16, AC1–AC4 and task IDs OM-01.01-T1..T4 verbatim. Pins come only from official documentation plus executed checks recorded in the repository; the user-selected Java 27 and Spring Boot 4.1.2 are fixed. Package by feature with explicit ports; the bootstrap creates only its own schema objects. Tenant/security scope travels in the Reactor Context explicitly and fails closed when absent; blocking work runs only through the bounded adapter. Integration tests use the pinned real VectorChord image (pgvector only as its required dependency) and fail explicitly, never skip, when the runtime or extension is missing. Gates must fail with a diagnostic naming the offending file/rule.

**Never:** Copy ConvaDesk pins; substitute versions or weaken tests when something is unavailable (stop and record the blocker instead); add authentication, Keycloak, Spring AI, frontend, Kubernetes packaging, durable-work tables or any feature schema (owned by OM-01.02/03/04, E02+); write sprint-status, TASKS.md progress or tracking automation; put Notion content, secrets or credentials in the repository; mark the story done.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Documented build | clean checkout, JDK ≥17 to launch wrapper, Docker | `./gradlew build` compiles Java 27 with Boot 4.1.2, runs unit + integration suites, passes gates | N/A |
| Health | app started against VectorChord container | `GET /actuator/health` → 200 `UP`, includes bootstrap schema-baseline indicator | DB unreachable → indicator DOWN, no secrets in body/logs |
| Scope present | Mono with `ScopeContext` in Reactor Context, crossing `publishOn`/blocking hop/R2DBC tx | same tenant visible downstream and via `current_setting` inside the tx; cleared after commit | N/A |
| Scope absent | no `ScopeContext` in context | `MissingScopeException`, body never executed, no connection opened | fail closed |
| Blocking bound | more concurrent calls than the configured cap, or callable exceeding deadline | `BlockingCapacityExceeded` / `BlockingDeadlineExceeded` typed errors | caller receives error, no event-loop thread blocked |
| Migration path | fresh container | Flyway applies `V001__bootstrap_infrastructure.sql`; `vchord`+`vector` installed; history row success | missing extension → startup fails with explicit message |
| Plain PostgreSQL image | fixture pointed at non-VectorChord image | explicit failure naming the missing `vchord` extension | fail, never skip |
| No container runtime | Docker unreachable | fixture throws explicit error naming the requirement and docs | fail, never skip |
| Gate violations | misformatted file / Error Prone error / cross-feature internal import / forbidden Lombok | respective Gradle task fails naming file and rule | useful diagnostic |

</frozen-after-approval>

## Code Map

- `docs/engineering-tracking.md` -- repository tracking contract; do not change status semantics.
- `_bmad-output/specs/spec-owl-mast/SPEC.md`, `_bmad-output/planning-artifacts/architecture/.../ARCHITECTURE-SPINE.md` -- binding AD-2, AD-5, AD-16 and Deferred table row owned by this story.
- `_bmad-output/planning-artifacts/epics/owl-mast-2026-11-05/epic-01.md` -- AC1–AC4, T1–T4 wording (read-only).
- `.gitignore` -- extend for Gradle/IDE outputs; keep BMAD entries.
- Qualified pins (executed 2026-11-06): Gradle 9.8.2 (services.gradle.org current, sha256 `21bd5da2…`), Temurin JDK 27.0.1+1 (api.adoptium.net), Boot 4.1.2 BOM (Testcontainers 2.0.5, Flyway 12.4.0, r2dbc-postgresql 1.1.3, Lombok 1.18.48, JUnit 6.0.3), Spotless 8.11.0 + google-java-format 2.0.0, Error Prone 2.52.0 + net.ltgt.errorprone 5.2.0, ArchUnit 1.5.1, foojay resolver 1.0.0, image `tensorchord/vchord-postgres:pg18-v1.1.1@sha256:700ff05e…` (PostgreSQL 18.3, vchord 1.1.1, vector 0.8.2), negative image `postgres:18.2-alpine@sha256:035b9ab5…`, GitHub Actions checkout v7.0.1 / setup-java v6.2.0 / gradle/actions v6.4.1 commit SHAs. Error Prone on javac 27 is unverified until compiled.

## Tasks & Acceptance

**Execution:**
- [x] `gradle/wrapper/*`, `gradlew*`, `gradle/gradle-daemon-jvm.properties`, `settings.gradle.kts`, `gradle.properties`, `gradle/libs.versions.toml` -- Gradle 9.8.2 wrapper with checksum, foojay toolchain resolver, daemon JVM criteria 27, version catalog, dependency locking -- T1 pins.
- [x] `docs/toolchain-qualification.md` -- sources, commands, outputs, blockers, reproducible re-check commands -- T1 evidence.
- [x] `backend/build.gradle.kts`, `backend/lombok.config`, `backend/gradle.lockfile` -- Boot 4.1.2 plugin, Java 27 toolchain, WebFlux/Actuator/R2DBC/Flyway deps, Spotless, Error Prone, `-Xlint -Werror`, JVM test suites, test fixtures -- T2/T3.
- [x] `backend/src/main/java/com/aisquad/owlmast/OwlMastApplication.java`, `backend/src/main/resources/application.yaml`, `db/migration/V001__bootstrap_infrastructure.sql` -- minimal app, env-driven DB config, bootstrap-owned extension/schema/baseline table -- T2.
- [x] `backend/src/main/java/com/aisquad/owlmast/platform/{scope,blocking,persistence}` -- `ScopeContext`/`Scopes` (Reactor Context, fail-closed), `BoundedBlocking` (bounded scheduler, deadline, capacity), `ScopedTransactions` (TransactionalOperator + `set_config` bound to the tx) -- AC3.
- [x] `backend/src/main/java/com/aisquad/owlmast/bootstrap/{api,application,port,adapter}` -- schema-baseline query API, consumer-owned port, R2DBC adapter, reactive health indicator -- feature convention example, T2.
- [x] `backend/src/test/java/.../architecture/*` -- ArchUnit rules on production classes plus negative fixture packages proving diagnostics -- AC2.
- [x] `backend/src/test/java/.../platform/*` -- unit tests for scope, bounded blocking, runtime-availability guard message -- AC3/AC4.
- [x] `backend/src/testFixtures/java/.../testing/*` -- `OwlMastPostgres` pinned container factory, explicit runtime check, `ContainersConfiguration` with `@ServiceConnection`, `TestOwlMastApplication` for `bootTestRun` -- T4.
- [x] `backend/src/integrationTest/java/...` -- health 200/UP, migration history + extensions, scoped transaction across async hops (commit/rollback/absent), plain-image explicit failure -- AC1/AC3/AC4.
- [x] `scripts/verify-quality-gates.sh` -- injects formatting, Error Prone, Lombok and module violations into a temp copy and asserts each gate fails with its diagnostic -- AC2 negative check.
- [x] `.github/workflows/ci.yml`, `.editorconfig`, `.gitattributes` -- pinned actions, wrapper validation, `./gradlew build`, gate negative job -- T3 CI.
- [x] `docs/engineering-conventions.md`, `docs/development.md`, `README.md` -- feature/module convention, Lombok/records/composition rules, developer and CI commands -- T3/T4.

**Acceptance Criteria:** AC1–AC4 as stated in epic-01.md for OM-01.01; verified by the commands below.

## Implementation Notes

- 2026-11-06: Executed directly (no subagents, per coordinator). Checkpoint approval came from the coordinator's pre-authorization of all four tasks; no Open Questions were needed (all choices routine).
- Toolchain: Gradle 9.8.2 wrapper (sha256 pinned) bootstrapped from a checksum-verified distribution; daemon JVM criteria pin Temurin 27 with direct Adoptium asset URLs (27.0.1+1; Windows x64 27+35 as the only published asset). Gradle detected an already installed `temurin-27-jdk` 27.0.1.0.2+1 package on this machine instead of downloading.
- Surprises recorded in docs/toolchain-qualification.md: Testcontainers replaces the VectorChord image command, dropping `shared_preload_libraries`, so the fixture restates it; Boot's R2DBC service connection needs `testcontainers-r2dbc`; Boot 4 `WebTestClient` requires `@AutoConfigureWebTestClient`, so the health test binds a client to the random port via `@LocalServerPort` (`org.springframework.boot.test.web.server`); Reactor `boundedElastic` requires a per-thread queue of at least 1, so the property is `max-queued-per-thread`; `current_setting(name, true)` is NULL outside a transaction and must be mapped through `Optional`.
- Error Prone caught a real defect during development (`[FormatString]`), which is cited as executable evidence that it works on javac 27.
- Health endpoint exposes only `status` (show-details never) plus liveness/readiness groups; the bootstrap `schemaBaseline` indicator contributes to the aggregate.
- Files: root Gradle files, `backend/**`, `docs/{toolchain-qualification,engineering-conventions,development}.md`, `README.md`, `scripts/verify-quality-gates.sh`, `.github/workflows/ci.yml`, `.editorconfig`, `.gitattributes`, `.gitignore` additions.
- Verified: `./gradlew clean build --no-build-cache` (23 unit + 11 integration tests, 0 failures/skips, 17s), `scripts/verify-quality-gates.sh` (4/4 gates fail on injected violations), `bootTestRun` health UP. CI: first run failed with exit 126 because the repository has `core.fileMode=false` and the executable bits of `gradlew`/`scripts/verify-quality-gates.sh` were not recorded; fixed with `git update-index --chmod=+x` (commit b595b8d). Second run https://github.com/gabrianoo/owl-mast/actions/runs/42203046822 passed both jobs (build 1m47s, gate negatives 1m27s) on GitHub `ubuntu-latest` with Docker. PR https://github.com/gabrianoo/owl-mast/pull/105.

- Repair round 1 (2026-11-06), review of d1d1ce25: F1 fixed by recording the bound scope as a resource of the actual Spring transaction (`ScopedTransactions.Binding`), joining equal scopes, rejecting different tenant/principal before any effect, marking rollback-only and poisoning the transaction so a caught rejection still fails at the end (Spring's participating rollback-only alone did not stop the outer commit in the probe). F2 fixed with `platform.diagnostics.SafeFailure` (class-name chain only) and a captured-log test. F3 fixed with `owlmast.qualified.jdk.*` pins in gradle.properties enforced in settings (daemon), buildSrc `QualifiedJdk` (compiler/test/application launchers) and `QualifiedJdkTest` (test JVM); CI pins `27.0.1`; daemon properties restricted to published 27.0.1+1 assets and the macOS x64 claim removed; gate script gains the `jdk-pin` negative case. Probe: `-Dorg.gradle.java.home` cannot override daemon criteria. Verified locally: 26 unit + 15 integration tests, 5/5 gates, clean build. Review record: [PR #105 archive, review of d1d1ce25](https://github.com/gabrianoo/owl-mast/pull/105#issuecomment-6741007782). The archived files, deleted in c988f50, remain in git history under `_bmad-output/implementation-artifacts/reviews/` at 137e084 and can be read with `git show <blob>`: om-01-01-review-initial.md = 34010f381232d0b967dbf9c87411c5b989407a1c, om-01-01-review-triage-round-1.md = 110d7df41f97a90bb7aa13fb5f2d39b1795009e7.

- Repair round 2 (2026-11-06, final authorized), review of b4024d5: R1 fixed by registering a reactive `TransactionSynchronization` on the physical transaction whose `beforeCommit` refuses the commit of a poisoned transaction for any owner (external operator included). R2 fixed by tying the binding's lifetime to that synchronization (unbind on suspend, rebind on resume, remove after completion, identity-checked) and refusing calls without an actual synchronized transaction (`ScopeBindingUnavailableException`) before work. `Binding` became a plain class (identity semantics). Eight new real-database regressions in `ScopedTransactionsIT`; the reviewer's probe class passed unchanged as a one-off. Round-1 triage wording corrected (IncompatibleScopeException, not UnexpectedRollbackException). Review record, including the reviewer probe: [PR #105 archive, review of b4024d5](https://github.com/gabrianoo/owl-mast/pull/105#issuecomment-6741008298). The archived files, deleted in c988f50, remain in git history under `_bmad-output/implementation-artifacts/reviews/` at 137e084 and can be read with `git show <blob>`: om-01-01-review-round-1.md = acf786da3fe009994e351cc52e6c6efaddc60285, om-01-01-review-round-1-probe-ReviewScopeProbeIT.java.txt = 34790ff3db2ba4e7d257ad8a64134398542a3bf6, om-01-01-review-triage-round-2.md = b2b3037975c0ee46d154a979dfd33b3083d7717d.

## Spec Change Log

- Round 1 (2026-11-06): no spec amendment; the frozen intent and acceptance already required fail-closed scope binding, secret-free diagnostics and qualified JDK pins. Findings were implementation defects. KEEP: real-database nested-transaction tests, captured-log assertions, pin enforcement on daemon/compiler/test JVMs.

## Review Triage Log

- Second independent review (2026-11-06, after repair round 1), of b4024d5527a0f1ef000f1ae1531b0f2ff5a8f51f: REQUEST CHANGES. F2 resolved, F3 resolved; F1 partial with R1 high (external owner commits after swallowed mismatch) — confirmed, fixed; R2 high (binding lifetime longer than the physical transaction; REQUIRES_NEW and sequential SUPPORTS cases) — confirmed, fixed. Report and triage: [PR #105 archive, review of b4024d5](https://github.com/gabrianoo/owl-mast/pull/105#issuecomment-6741008298).
- First independent review (2026-11-06), of d1d1ce25b22deceb5f5473f9b0d76ffec7ef6c95: REQUEST CHANGES. F1 high (nested transaction overwrites outer tenant) — confirmed, fixed. F2 high (raw throwable logged) — confirmed, fixed. F3 medium (JDK patch not enforced, macOS x64 claim wrong) — confirmed, fixed. Full report, triage, and evidence: [PR #105 archive, review of d1d1ce25](https://github.com/gabrianoo/owl-mast/pull/105#issuecomment-6741007782). Coordinator runs a fresh independent review on the repaired head (the entry above).

## Design Notes

Feature package shape: `<feature>.api` (records + interfaces, only package other features may import), `.application` (operations, Reactor composition, no blocking), `.domain` (pure), `.port` (consumer-owned interfaces), `.adapter.<kind>` (framework/provider code). `platform.*` is a shared kernel of boundary values and primitives; it never depends on features. Scope is a Reactor Context entry, never a ThreadLocal; `ScopedTransactions` reads it, opens the R2DBC transaction and executes `select set_config('owlmast.tenant_id', $1, true)` so database scope is bound to the real transaction. Migrations run through Flyway over JDBC at startup (bounded, startup-only blocking); runtime access is R2DBC.

## Verification

**Commands:**
- `./gradlew --version` -- expected: Gradle 9.8.2, daemon JVM 27.
- `./gradlew build` -- expected: compiles on toolchain 27, `spotlessCheck`, Error Prone, unit tests, ArchUnit and integration suite pass.
- `./gradlew :backend:test` -- expected: fast suite passes without Docker.
- `./gradlew :backend:integrationTest` -- expected: VectorChord container starts, migration/transaction/health tests pass, containers removed.
- `scripts/verify-quality-gates.sh` -- expected: each injected violation fails its gate with a diagnostic naming the file/rule.
