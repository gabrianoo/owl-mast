# Engineering conventions (backend)

These conventions implement AD-2, AD-5 and AD-16 of the [architecture spine](../_bmad-output/planning-artifacts/architecture/architecture-owl-mast-2026-11-05/ARCHITECTURE-SPINE.md). They are enforced by the build where a gate exists; the gate is named next to each rule. `scripts/verify-quality-gates.sh` proves each gate fails on a deliberate violation.

## Package by feature

Root package: `com.aisquad.owlmast`. Every feature is a direct child package (`bootstrap`, later `access`, `knowledge`, …) with this internal layout:

| Subpackage | Holds | May depend on | Must not depend on (rule in `FeatureModuleRules`) |
| --- | --- | --- | --- |
| `api` | Public records and interfaces other features may use. The lowest layer of a feature: what it publishes | `platform`, Reactor, another feature's `api` | its own `application`, `domain`, `port` and adapters; Spring (`api must not depend on application, domain or port`, `api/domain stay free of Spring and adapters`) |
| `domain` | Pure rules and values; no Spring, no adapters | its own `api` values, `platform` values, JDK | `application`, `port`, adapters, Spring, any other feature (`domain must not depend on application or port`, `domain of '<feature>' must not depend on another feature`) |
| `port` | Consumer-owned interfaces the feature needs from the outside | `api`, `domain`, `platform` | `application`, adapters (`port must not depend on application`, `application/port must not depend on adapters`) |
| `application` | Operations composing domain rules, ports and other features' `api` | `api`, `domain`, `port`, `platform`, other `*.api` | adapters; another feature's internals |
| `adapter.<kind>` | Framework, database and provider code implementing ports or exposing the API | everything inside the feature, Spring, other `*.api` | another feature's internals |

Every row has a rule and a deliberately broken fixture (`src/test/java/.../archfixtures`), so a row cannot drift from the code unnoticed. Two points changed on 2026-11-12 (E01 retrospective, A1), because the table said one thing and the code another:

- `api` no longer lists `domain`. A published type that exposes a domain type puts the feature's internals into the contract other features compile against (and, for `jobs.api` and `audit.api`, into the frozen v1 shape). The dependency runs the other way: `domain` may use its own feature's `api` values, as `audit.domain.AuditRecord` is built from the envelope types and `jobs.domain.RetryPolicy` reads the contract defaults.
- `api` may use another feature's `api`. `audit.api` names the `jobs.api` work type and bounds its publisher uses; the cycle rule keeps this one-directional.

`platform` is the shared kernel. It never depends on a feature, and it holds only what every feature needs and none owns:

| Package | Holds | Since |
| --- | --- | --- |
| `platform.scope` | `ScopeContext`, `TenantId`, `PrincipalId`, `Scopes`, the backend `ServiceIdentity` | OM-01.01, OM-01.03 |
| `platform.blocking` | `BoundedBlocking` and its typed failures | OM-01.01 |
| `platform.persistence` | `ScopedTransactions` and its typed failures | OM-01.01 |
| `platform.diagnostics` | `SafeFailure` (class names only in logs) | OM-01.02 |
| `platform.authorization` | `OperationDeniedException`: the denial signal every feature raises and audited mutations record. Only the signal lives here; the decisions belong to the access module (E02) | OM-01.03 |
| `platform.web` | `UnhandledFailureAdvice`: the common RFC 9457 error envelope and the status of the kernel's own failures | OM-01.04 |

A new `platform` package needs the same justification: used by more than one feature, owned by none, no feature dependency. `access` currently has only an adapter (the identity-provider readiness contract of OM-01.02); its `api` and `application` arrive with E02.

Cross-feature code only touches another feature's `api`; feature packages must be free of cycles. The owning feature alone creates and migrates its schema objects; the bootstrap migration `V001__bootstrap_infrastructure.sql` owns only the `bootstrap` schema and the VectorChord extension requirement.

Gate: `FeatureModuleRulesTest` (ArchUnit, runs in `./gradlew :backend:test`). Its rules live in `FeatureModuleRules` and are also evaluated against deliberately broken fixtures in `FeatureModuleRulesNegativeTest`: every rule there has a fixture that breaks it. `DurableWorkContractTest` adds the OM-01.03 rules: scheduling annotations only in `jobs.adapter.scheduling`, no broker/scheduler/workflow-engine client on the classpath or in the lockfile, the contract document in step with the published types, the frozen v1 shape, and the tenant-internal grant boundary (below). `scripts/verify-quality-gates.sh` injects a violation of the layering, grant, wake-up-source and frozen-shape rules into a scratch copy and requires each to fail by name.

The rules cover production code (`src/main`). Test sources are outside them on purpose: an integration test of a feature may use that feature's `application`, `domain` and `port` types to build fault-injection fixtures (`DelegatingWorkRepository`, a `WorkProcessor` with a shortened policy), and the fixture module supplies its own `TenantInternalGrants`.

## Durable work and audit

Implement AD-6 only through the owner APIs documented in [durable-work-and-audit-contract.md](durable-work-and-audit-contract.md):

- Follow-up work goes through `jobs.api.WorkEnqueue` inside the same `ScopedTransactions.inTransaction` call as the business change, so both commit or roll back together. Handlers implement `jobs.api.WorkHandler`, are registered as Spring beans, deduplicate external effects with `WorkItem.idempotencyKey()` or return `EffectOutcome.uncertain`, signal a failure no retry can cure with `jobs.api.NonRetryableWorkException`, and never put content or secrets into payloads.
- Covered mutations go through `audit.api.AuditedMutations`; the `SUCCEEDED` publication intent commits with the business row and the `audit.publish` work item publishes it idempotently. Failed and denied attempts are recorded by the same call through a separate `REQUIRES_NEW` transaction with the exception class chain as the only reason; a denial is signalled with `platform.authorization.OperationDeniedException` and a kebab-case reason code.
- Processors run as `ServiceIdentity.BACKEND` inside `ServiceIdentity.backendScope(tenant)`. Every jobs/audit statement filters on the transaction-bound tenant setting, never on a parameter. Until OM-02.04, only handlers registered as tenant-internal system work are dispatched (`TenantInternalOnlyDispatchAuthorization`).
- A handler cannot make itself tenant-internal system work. The privilege is granted by the jobs owner in `jobs.application.TenantInternalGrants` (today: `audit.publish` only); a handler that registers that way for any other type stops the application at startup, and the default recheck denies it at dispatch. Do not add a work type there to make a feature's handler run: that is a change to the authorization boundary and is reviewed as one. Other features cannot reach the class (feature isolation, restated by name in `DurableWorkContractTest`), and only `jobs` and `access` may implement `DispatchAuthorization`.
- Wake-ups are in-process Spring scheduling only (`WorkScheduler`); do not add brokers, external schedulers or worker services.

## Reactive rules

- Request and job composition is Reactor based (`Mono`/`Flux`). `api`, `application` and `domain` code never calls `block*()`, `toFuture()` or `toStream()` on a publisher (ArchUnit gate).
- Tenant/security scope is an explicit `ScopeContext` carried in the Reactor Context (`Scopes.bind`, `Scopes.current`). There is no default scope; a missing scope raises `MissingScopeException` before any work runs. `ThreadLocal` must not carry authorization or tenant state anywhere in production code (ArchUnit gate).
- Database work that needs tenant scope goes through `ScopedTransactions.inTransaction`, which opens the R2DBC transaction and binds the tenant to that transaction with a transaction-local PostgreSQL setting (`owlmast.tenant_id`), so the scope is attached to the real connection rather than to a thread. A transaction carries exactly one scope, tracked as a resource of the physical Spring transaction with a registered `TransactionSynchronization` (unbound on suspend, rebound on resume, removed after completion): nested calls with an equal tenant and principal join it; a different scope is rejected with `IncompatibleScopeException` before any effect, and the transaction's own `beforeCommit` then refuses the commit even if the caller swallowed the rejection. `PROPAGATION_REQUIRES_NEW` binds the new connection independently; a call without an actual synchronized transaction fails with `ScopeBindingUnavailableException` before any work.
- Unavoidable blocking SDK calls run through `BoundedBlocking.call(operation, callable)`: bounded threads, bounded per-thread queue and a deadline (`owlmast.blocking.*`). Pass what the blocking code needs as explicit arguments; it has no Reactor Context.
- Flyway migrations are the one accepted startup-time blocking path; runtime access is R2DBC only.
- A migration file is never edited once a database has applied it, comments included: Flyway validates a checksum of the file's text at every start, so a changed line stops every installation that already ran it. Correct a migration with a new one.

## Values, Lombok and composition

- Values are Java records with compact constructors for validation (`TenantId`, `ScopeContext`, `SchemaBaseline`). Prefer immutable collections and `Optional` return types over nulls at boundaries.
- Lombok is focused on boilerplate only: `@RequiredArgsConstructor` on Spring components, `@Slf4j` for loggers, `@Builder`/`@With` where a record would be unwieldy, and `@AllArgsConstructor`/`@NoArgsConstructor` with an explicit `access` level (`@AllArgsConstructor(access = AccessLevel.PRIVATE)` behind a static factory, as in `BoundedBlocking`; `@NoArgsConstructor(access = AccessLevel.PRIVATE)` on a holder of statics). Without an access level they generate a public constructor that bypasses the factory or the validation, so write the constructor by hand instead. `@Data`, `@Value`, `@Setter`, `@EqualsAndHashCode`, `@ToString`, `@SneakyThrows`, `val`/`var` and experimental features are rejected at compile time by `backend/lombok.config` (gate: `compileJava`).
- Prefer functional composition (streams, `Optional`, Reactor operators, small strategy records) over nested `if`/`else` or `switch` for business variation. Keep straightforward guard clauses (`if (value == null) throw …`) and exhaustive `switch` over sealed types when they are the clearest expression.
- Errors are typed exceptions with safe messages (`MissingScopeException`, `BlockingDeadlineExceededException`); never put credentials, connection strings or protected payloads into messages, logs, health details or metrics labels. When logging a caught failure, log `SafeFailure.describe(failure)` (exception class names only), never the throwable itself; tests that cover a failure path capture the log output and assert markers from the message and its causes are absent.

## Formatting and static analysis

- Formatting: Spotless with google-java-format (pinned in `gradle/libs.versions.toml`). Run `./gradlew :backend:spotlessApply` before committing; `spotlessCheck` is part of `build` and fails naming the file.
- Static analysis: Error Prone runs inside `javac` with every enabled check treated as an error, plus `-Xlint:all -Werror` (minus `processing` and `serial`). Fix the finding rather than suppressing it; a `@SuppressWarnings` needs a comment stating why. `-Xlint:-serial` is off because exceptions here are never serialized (no RMI, no session replication, no serialized caches), so the lint's demand for a `serialVersionUID` on every exception would be noise. The consequence is that `@Serial private static final long serialVersionUID` is optional: the OM-01.01 exceptions carry it, the OM-01.03 ones do not, and both are accepted. Do not add Java serialization of an exception without turning the lint back on.
- Shell and Python: `scripts/verify-script-lint.sh` runs shellcheck (severity `warning`) over the repository's shell scripts and ruff (rules in `ruff.toml`: syntax errors, pyflakes, bugbear) over `scripts/`, `deploy/` and `automation/`; CI job `script-lint`. Both tools are pinned (shellcheck by release checksum, ruff with hashes in `scripts/lint-requirements.txt`). The Python test dependencies of the deploy suite are pinned with hashes in `deploy/tests/requirements.txt`.
- Dependencies are locked (`backend/gradle.lockfile`). Change a version in the catalog or BOM, then run `./gradlew :backend:dependencies --write-locks` and commit the lockfile.

## Tests

- `src/test`: fast unit and component tests, no container runtime.
- `src/integrationTest`: Testcontainers suite against the pinned VectorChord image; real migrations and transactions. It fails explicitly when no Docker-compatible runtime is reachable. The application connects as a role without any privileged attribute that owns its database, as an installation does: `OwlMastPostgres` keeps the image's superuser as a separate provisioning identity (`OwlMastPostgres.PROVISIONER`) that creates the role, hands it the database and installs VectorChord. A test that needs something only a superuser may do (reading `shared_preload_libraries`) runs it as the provisioner inside the container, never by widening the application role.
- `src/testFixtures`: reusable fixtures (`OwlMastPostgres`, `ContainersConfiguration`) consumed by later features.
- Name integration tests `*IT`; keep negative paths (missing scope, capacity exceeded, missing extension) next to the useful path.
