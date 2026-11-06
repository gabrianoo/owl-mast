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

Gate: `FeatureModuleRulesTest` (ArchUnit, runs in `./gradlew :backend:test`). Its rules live in `FeatureModuleRules` and are also evaluated against deliberately broken fixtures in `FeatureModuleRulesNegativeTest`.

## Reactive rules

- Request and job composition is Reactor based (`Mono`/`Flux`). `api`, `application` and `domain` code never calls `block*()`, `toFuture()` or `toStream()` on a publisher (ArchUnit gate).
- Tenant/security scope is an explicit `ScopeContext` carried in the Reactor Context (`Scopes.bind`, `Scopes.current`). There is no default scope; a missing scope raises `MissingScopeException` before any work runs. `ThreadLocal` must not carry authorization or tenant state anywhere in production code (ArchUnit gate).
- Database work that needs tenant scope goes through `ScopedTransactions.inTransaction`, which opens the R2DBC transaction and binds the tenant to that transaction with a transaction-local PostgreSQL setting (`owlmast.tenant_id`), so the scope is attached to the real connection rather than to a thread.
- Unavoidable blocking SDK calls run through `BoundedBlocking.call(operation, callable)`: bounded threads, bounded per-thread queue and a deadline (`owlmast.blocking.*`). Pass what the blocking code needs as explicit arguments; it has no Reactor Context.
- Flyway migrations are the one accepted startup-time blocking path; runtime access is R2DBC only.

## Values, Lombok and composition

- Values are Java records with compact constructors for validation (`TenantId`, `ScopeContext`, `SchemaBaseline`). Prefer immutable collections and `Optional` return types over nulls at boundaries.
- Lombok is focused on boilerplate only: `@RequiredArgsConstructor` on Spring components, `@Slf4j` for loggers, `@Builder`/`@With` where a record would be unwieldy. `@Data`, `@Value`, `@Setter`, `@EqualsAndHashCode`, `@ToString`, `@SneakyThrows`, `val`/`var` and experimental features are rejected at compile time by `backend/lombok.config` (gate: `compileJava`).
- Prefer functional composition (streams, `Optional`, Reactor operators, small strategy records) over nested `if`/`else` or `switch` for business variation. Keep straightforward guard clauses (`if (value == null) throw …`) and exhaustive `switch` over sealed types when they are the clearest expression.
- Errors are typed exceptions with safe messages (`MissingScopeException`, `BlockingDeadlineExceededException`); never put credentials, connection strings or protected payloads into messages, logs, health details or metrics labels.

## Formatting and static analysis

- Formatting: Spotless with google-java-format (pinned in `gradle/libs.versions.toml`). Run `./gradlew :backend:spotlessApply` before committing; `spotlessCheck` is part of `build` and fails naming the file.
- Static analysis: Error Prone runs inside `javac` with every enabled check treated as an error, plus `-Xlint:all -Werror` (minus `processing` and `serial`). Fix the finding rather than suppressing it; a `@SuppressWarnings` needs a comment stating why.
- Dependencies are locked (`backend/gradle.lockfile`). Change a version in the catalog or BOM, then run `./gradlew :backend:dependencies --write-locks` and commit the lockfile.

## Tests

- `src/test`: fast unit and component tests, no container runtime.
- `src/integrationTest`: Testcontainers suite against the pinned VectorChord image; real migrations and transactions. It fails explicitly when no Docker-compatible runtime is reachable.
- `src/testFixtures`: reusable fixtures (`OwlMastPostgres`, `ContainersConfiguration`) consumed by later features.
- Name integration tests `*IT`; keep negative paths (missing scope, capacity exceeded, missing extension) next to the useful path.
