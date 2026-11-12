# Engineering conventions (backend)

These conventions implement AD-2, AD-5 and AD-16 of the [architecture spine](../_bmad-output/planning-artifacts/architecture/architecture-owl-mast-2026-11-05/ARCHITECTURE-SPINE.md). They are enforced by the build where a gate exists; the gate is named next to each rule. `scripts/verify-quality-gates.sh` proves each gate fails on a deliberate violation.

## Package by feature

Root package: `com.aisquad.owlmast`. Every feature is a direct child package (`bootstrap`, later `access`, `knowledge`, …) with this internal layout:

| Subpackage | Holds | May depend on |
| --- | --- | --- |
| `api` | Public records and interfaces other features may use | `domain`, `platform`, Reactor |
| `application` | Operations composing domain rules, ports and other features' `api` | `api`, `domain`, `port`, `platform`, other `*.api` |
| `domain` | Pure rules and values; no Spring, no adapters | `platform` values, JDK |
| `port` | Consumer-owned interfaces the feature needs from the outside | `api`, `domain` |
| `adapter.<kind>` | Framework, database and provider code implementing ports or exposing the API | everything inside the feature, Spring |

`platform` is the shared kernel (scope, bounded blocking, scoped transactions). It never depends on a feature. Cross-feature code only touches another feature's `api`; feature packages must be free of cycles. The owning feature alone creates and migrates its schema objects; the bootstrap migration `V001__bootstrap_infrastructure.sql` owns only the `bootstrap` schema and the VectorChord extension requirement.

Gate: `FeatureModuleRulesTest` (ArchUnit, runs in `./gradlew :backend:test`). Its rules live in `FeatureModuleRules` and are also evaluated against deliberately broken fixtures in `FeatureModuleRulesNegativeTest`. `DurableWorkContractTest` adds the OM-01.03 rules: scheduling annotations only in `jobs.adapter.scheduling`, no broker/scheduler/workflow-engine client on the classpath or in the lockfile, and the contract document in step with the published types.

## Durable work and audit

Implement AD-6 only through the owner APIs documented in [durable-work-and-audit-contract.md](durable-work-and-audit-contract.md):

- Follow-up work goes through `jobs.api.WorkEnqueue` inside the same `ScopedTransactions.inTransaction` call as the business change, so both commit or roll back together. Handlers implement `jobs.api.WorkHandler`, are registered as Spring beans, deduplicate external effects with `WorkItem.idempotencyKey()` or return `EffectOutcome.uncertain`, signal a failure no retry can cure with `jobs.api.NonRetryableWorkException`, and never put content or secrets into payloads.
- Covered mutations go through `audit.api.AuditedMutations`; the `SUCCEEDED` publication intent commits with the business row and the `audit.publish` work item publishes it idempotently. Failed and denied attempts are recorded by the same call through a separate `REQUIRES_NEW` transaction with the exception class chain as the only reason; a denial is signalled with `platform.authorization.OperationDeniedException` and a kebab-case reason code.
- Processors run as `ServiceIdentity.BACKEND` inside `ServiceIdentity.backendScope(tenant)`. Every jobs/audit statement filters on the transaction-bound tenant setting, never on a parameter. Until OM-02.04, only handlers registered as tenant-internal system work are dispatched (`TenantInternalOnlyDispatchAuthorization`).
- Wake-ups are in-process Spring scheduling only (`WorkScheduler`); do not add brokers, external schedulers or worker services.

## Reactive rules

- Request and job composition is Reactor based (`Mono`/`Flux`). `api`, `application` and `domain` code never calls `block*()`, `toFuture()` or `toStream()` on a publisher (ArchUnit gate).
- Tenant/security scope is an explicit `ScopeContext` carried in the Reactor Context (`Scopes.bind`, `Scopes.current`). There is no default scope; a missing scope raises `MissingScopeException` before any work runs. `ThreadLocal` must not carry authorization or tenant state anywhere in production code (ArchUnit gate).
- Database work that needs tenant scope goes through `ScopedTransactions.inTransaction`, which opens the R2DBC transaction and binds the tenant to that transaction with a transaction-local PostgreSQL setting (`owlmast.tenant_id`), so the scope is attached to the real connection rather than to a thread. A transaction carries exactly one scope, tracked as a resource of the physical Spring transaction with a registered `TransactionSynchronization` (unbound on suspend, rebound on resume, removed after completion): nested calls with an equal tenant and principal join it; a different scope is rejected with `IncompatibleScopeException` before any effect, and the transaction's own `beforeCommit` then refuses the commit even if the caller swallowed the rejection. `PROPAGATION_REQUIRES_NEW` binds the new connection independently; a call without an actual synchronized transaction fails with `ScopeBindingUnavailableException` before any work.
- Unavoidable blocking SDK calls run through `BoundedBlocking.call(operation, callable)`: bounded threads, bounded per-thread queue and a deadline (`owlmast.blocking.*`). Pass what the blocking code needs as explicit arguments; it has no Reactor Context.
- Flyway migrations are the one accepted startup-time blocking path; runtime access is R2DBC only.

## Values, Lombok and composition

- Values are Java records with compact constructors for validation (`TenantId`, `ScopeContext`, `SchemaBaseline`). Prefer immutable collections and `Optional` return types over nulls at boundaries.
- Lombok is focused on boilerplate only: `@RequiredArgsConstructor` on Spring components, `@Slf4j` for loggers, `@Builder`/`@With` where a record would be unwieldy. `@Data`, `@Value`, `@Setter`, `@EqualsAndHashCode`, `@ToString`, `@SneakyThrows`, `val`/`var` and experimental features are rejected at compile time by `backend/lombok.config` (gate: `compileJava`).
- Prefer functional composition (streams, `Optional`, Reactor operators, small strategy records) over nested `if`/`else` or `switch` for business variation. Keep straightforward guard clauses (`if (value == null) throw …`) and exhaustive `switch` over sealed types when they are the clearest expression.
- Errors are typed exceptions with safe messages (`MissingScopeException`, `BlockingDeadlineExceededException`); never put credentials, connection strings or protected payloads into messages, logs, health details or metrics labels. When logging a caught failure, log `SafeFailure.describe(failure)` (exception class names only), never the throwable itself; tests that cover a failure path capture the log output and assert markers from the message and its causes are absent.

## Formatting and static analysis

- Formatting: Spotless with google-java-format (pinned in `gradle/libs.versions.toml`). Run `./gradlew :backend:spotlessApply` before committing; `spotlessCheck` is part of `build` and fails naming the file.
- Static analysis: Error Prone runs inside `javac` with every enabled check treated as an error, plus `-Xlint:all -Werror` (minus `processing` and `serial`). Fix the finding rather than suppressing it; a `@SuppressWarnings` needs a comment stating why.
- Dependencies are locked (`backend/gradle.lockfile`). Change a version in the catalog or BOM, then run `./gradlew :backend:dependencies --write-locks` and commit the lockfile.

## Tests

- `src/test`: fast unit and component tests, no container runtime.
- `src/integrationTest`: Testcontainers suite against the pinned VectorChord image; real migrations and transactions. It fails explicitly when no Docker-compatible runtime is reachable.
- `src/testFixtures`: reusable fixtures (`OwlMastPostgres`, `ContainersConfiguration`) consumed by later features.
- Name integration tests `*IT`; keep negative paths (missing scope, capacity exceeded, missing extension) next to the useful path.
