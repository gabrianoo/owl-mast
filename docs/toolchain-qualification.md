# Toolchain qualification (OM-01.01-T1)

Qualified on 2026-11-06 for GitHub issue #20 (story OM-01.01, epic E01). Every pin below was taken from the primary source named in the table and then exercised by the commands in the *Executable checks* section on this machine (WSL2 Linux x86_64, Docker Desktop 29.9.2) and in CI (`.github/workflows/ci.yml`). The user-selected Java 27 and Spring Boot 4.1.2 were fixed inputs; everything else was selected here. No ConvaDesk pin was copied.

Re-qualified on 2026-11-12 (E01 retrospective T1, E01-R-07). Commit `143584b` moved the wrapper from Gradle 9.8.2 to 9.9.0 on `main` without a pull request and without rerunning these checks: it changed `distributionUrl` and `distributionSha256Sum` only, left the 9.8.2 wrapper jar in place, and this document then paired 9.9.0 with 9.8.2's checksum note and `--version` output. The Gradle rows and the *Gradle distribution and wrapper* section below are the checks as rerun on that date (WSL2 Linux x86_64, Docker Desktop 29.9.3); the wrapper jar was regenerated for 9.9.0 in the same change. Sections that were not rerun keep their 2026-11-06 output and say so.

## Pins

| Component | Pin | Where it is pinned | Primary source consulted |
| --- | --- | --- | --- |
| Java language/runtime | 27 (Eclipse Temurin 27.0.1+1, `jdk-27.0.1.0.2+1`; `java.runtime.version` `27.0.1.0.2+1`) | `gradle.properties` (`owlmast.qualified.jdk.runtime`/`vendor`, enforced on daemon, compiler, test and application launchers), `gradle/gradle-daemon-jvm.properties`, `backend/build.gradle.kts` toolchain, CI `setup-java` `27.0.1` | https://api.adoptium.net/v3/info/release_versions?version=%5B27%2C28%29&release_type=ga (GA builds 27+35 and 27.0.1+1); https://api.adoptium.net/v3/assets/feature_releases/27/ga |
| Spring Boot | 4.1.2 | `gradle/libs.versions.toml` | https://docs.spring.io/spring-boot/system-requirements.html: "Spring Boot 4.1.2 requires at least Java 17 and is compatible with versions up to and including Java 27 … Gradle 8.x (8.14 or later) and 9.x"; BOM on Maven Central (`spring-boot-dependencies/4.1.2`) |
| Gradle | 9.9.0 wrapper, `distributionSha256Sum` 0b00b0ffe07c4d4789c12d4935a44a7057d55774b7540bd4a3f76f336deb177a, wrapper jar sha256 621008afc4f5d59357fcf06ffa644dd5aade5e091bdc363742710445f73cdaf8 (both equal to the checksums Gradle publishes for 9.9.0) | `gradle/wrapper/gradle-wrapper.properties`, `gradle/wrapper/gradle-wrapper.jar` | https://services.gradle.org/distributions/gradle-9.9.0-bin.zip.sha256 and `gradle-9.9.0-wrapper.jar.sha256`; https://docs.gradle.org/9.9.0/userguide/compatibility.html (Java compatibility table: Java 27, toolchains from 9.8.0, running Gradle "9.8.0 and after"). On 2026-11-12 https://services.gradle.org/versions/current reported 9.9.1 (built 2026-11-10); the pin stays on 9.9.0, the version that was built and tested here, and a move to 9.9.1 reruns this section. |
| Toolchain provisioning | Foojay resolver convention plugin 1.0.0 | `settings.gradle.kts` | https://plugins.gradle.org/m2/org/gradle/toolchains/foojay-resolver-convention/…/maven-metadata.xml |
| Lombok | 1.18.48 (managed by the Boot BOM) | BOM | https://projectlombok.org/changelog: "v1.18.48 (September 1st, 2026) PLATFORM: JDK27 support added" |
| Formatter | Spotless Gradle plugin 8.11.0 with google-java-format 2.0.0 | `gradle/libs.versions.toml` | Spotless `plugin-gradle/CHANGES.md` 8.11.0 (2026-11-02): default google-java-format bumped to 2.0.0; https://github.com/google/google-java-format/releases/tag/v2.0.0 (2026-10-30) |
| Static analysis | Error Prone 2.52.0 via `net.ltgt.errorprone` 5.2.0; `javac -Xlint:all -Werror` | `gradle/libs.versions.toml`, `backend/build.gradle.kts` | https://github.com/google/error-prone/releases/tag/v2.52.0 (2026-11-02). Error Prone's own CI matrix covers JDK 21/25/EA, not 27, so compatibility was proven by the executable checks below. |
| Module/dependency rules | ArchUnit 1.5.1 (`archunit-junit5`) | `gradle/libs.versions.toml` | Maven Central metadata (`com.tngtech.archunit:archunit-junit5`), https://www.archunit.org/userguide/html/000_Index.html |
| Reactive persistence | Spring Boot R2DBC starter with `r2dbc-postgresql` 1.1.3.RELEASE; Flyway 12.4.0 over JDBC (`postgresql` 42.7.14) for migrations | BOM | Flyway PostgreSQL page (verified versions 9.2 and 18, page updated 2026-11-05): https://documentation.red-gate.com/flyway/reference/database-driver-reference/postgresql-database |
| Testcontainers | 2.0.5 (`testcontainers-postgresql`, `testcontainers-r2dbc`) with `spring-boot-testcontainers` 4.1.2 | BOM | https://docs.spring.io/spring-boot/reference/testing/testcontainers.html; Maven Central metadata for the 2.x artifacts |
| Database image | `tensorchord/vchord-postgres:pg18-v1.1.1@sha256:700ff05ebdc7e4afd4dd8442e0684293046c3833677fec326550000a04cf8a91` (PostgreSQL 18.3, VectorChord 1.1.1, pgvector 0.8.2; image created 2026-02-28) | `OwlMastImages` | https://docs.vectorchord.ai/vectorchord/getting-started/installation.html (`docker run … tensorchord/vchord-postgres:pg18-v1.1.1`; `CREATE EXTENSION IF NOT EXISTS vchord CASCADE`); Docker Hub tag listing |
| Negative-test image | `postgres:18.2-alpine@sha256:035b9ab53cfa147d7202b61f5f7782b939ae815b7d6bc81c96b7b42ff1fca950` | `OwlMastImages` | Docker Hub official image |
| Container runtime | Docker Engine (local: Docker Desktop 29.9.2 on WSL2, 29.9.3 at the 2026-11-12 rerun; CI: the Docker engine preinstalled on GitHub's pinned `ubuntu-26.04` runner) | docs/development.md, `.github/workflows/ci.yml` (`runs-on: ubuntu-26.04` on every job) | `docker version` |
| CI actions | `actions/checkout` v7.0.1 `3d3c42e5aac5ba805825da76410c181273ba90b1`; `actions/setup-java` v6.2.0 `77dd5b2ce225ea11469928ac317850245a74ae78`; `gradle/actions` v6.4.1 `8da46b539cd8fe6ab27ca75128919a18d757604c` | `.github/workflows/ci.yml` | GitHub releases and tag dereference via the GitHub API |

Boot-BOM-managed versions recorded from `spring-boot-dependencies-4.1.2.pom`: Spring Framework 7.0.10, Reactor BOM 2025.0.8 (reactor-core 3.8.8), Netty 4.2.19.Final, JUnit Jupiter 6.0.3, AssertJ 3.27.7, Micrometer 1.17.2, Jackson 3.1.7, Spring Security 7.1.2 (not yet used). All resolved versions are locked in `backend/gradle.lockfile`.

## Executable checks and results

Commands are relative to the repository root unless stated. Outputs are abbreviated to the decisive lines.

### Gradle distribution and wrapper

Rerun on 2026-11-12 (E01-R-07):

```
$ curl -sSL https://services.gradle.org/versions/current
"version":"9.9.1","buildTime":"20261110162215+0000"           # newer than the pin; not adopted here
$ curl -sSL https://services.gradle.org/distributions/gradle-9.9.0-bin.zip.sha256
0b00b0ffe07c4d4789c12d4935a44a7057d55774b7540bd4a3f76f336deb177a
$ curl -fsSL -O https://services.gradle.org/distributions/gradle-9.9.0-bin.zip && sha256sum gradle-9.9.0-bin.zip
0b00b0ffe07c4d4789c12d4935a44a7057d55774b7540bd4a3f76f336deb177a  gradle-9.9.0-bin.zip     # = distributionSha256Sum
$ curl -sSL https://services.gradle.org/distributions/gradle-9.9.0-wrapper.jar.sha256
621008afc4f5d59357fcf06ffa644dd5aade5e091bdc363742710445f73cdaf8
$ sha256sum gradle/wrapper/gradle-wrapper.jar                 # before: the jar 143584b left in place
3b8a25775a69158b5ad2b1d17a80a88dc7b40a352a73eb27d06c612a7ce68e98                          # = gradle-9.8.2-wrapper.jar.sha256
$ ./gradlew wrapper --gradle-version 9.9.0 --distribution-type bin \
    --gradle-distribution-sha256-sum 0b00b0ffe07c4d4789c12d4935a44a7057d55774b7540bd4a3f76f336deb177a
BUILD SUCCESSFUL                                               # gradle-wrapper.jar rewritten; properties and gradlew unchanged
$ sha256sum gradle/wrapper/gradle-wrapper.jar                 # after
621008afc4f5d59357fcf06ffa644dd5aade5e091bdc363742710445f73cdaf8                          # = the published 9.9.0 wrapper jar
$ ./gradlew --version
Gradle 9.9.0
Build time:    2026-11-06 15:49:35 UTC
Revision:      dabfe84a6c2590fa6ecaab03ff6fefe5b838d558
Kotlin:        2.4.21
Launcher JVM:  27.0.1.0.2 (Eclipse Adoptium 27.0.1.0.2+1)
Daemon JVM:    Compatible with Java 27, Eclipse Temurin, nativeImageCapable=false (from gradle/gradle-daemon-jvm.properties)
OS:            Linux 6.18.58.1-microsoft-standard-WSL2 amd64
```

What the rerun found: the distribution checksum in `gradle-wrapper.properties` was already 9.9.0's, so the build has been running 9.9.0 since `143584b`; the earlier text here labelled that checksum as `gradle-9.8.2-bin.zip` and quoted 9.8.2's checksum (`21bd5da2…`) as the current version's. The wrapper jar, however, was still 9.8.2's. Both are official Gradle wrapper jars, which is why CI's `validate-wrappers` step passed; the jar now matches the pinned distribution. The 2026-11-06 run of this section recorded Gradle 9.8.2.

### JDK

`./gradlew updateDaemonJvm --jvm-version=27 --jvm-vendor=adoptium` generated Foojay redirect ids; those ids resolved to the 27+35 GA build, so the properties file was rewritten with direct Adoptium release assets for 27.0.1+1. Daemon criteria and toolchains only constrain the major version and vendor, so the exact runtime is enforced separately (review finding F3):

- `settings.gradle.kts` fails the build unless the daemon JVM reports `java.runtime.version` `27.0.1.0.2+1` and `java.vendor` `Eclipse Adoptium`;
- `backend/build.gradle.kts` checks the resolved compiler, test launcher and application launcher metadata (`javaRuntimeVersion`, vendor `Eclipse Temurin`) before each compile, test and run task;
- `QualifiedJdkTest` checks the JVM that actually executes the tests against the pin the build passes in;
- CI requests `java-version: '27.0.1'` with `check-latest: false`.

Supported platforms are bounded by executable qualification: Linux x86_64 (this machine and GitHub's pinned `ubuntu-26.04` runner; the first CI run on 2026-11-06 used the then-floating runner label, which was replaced by the fixed pin). Linux aarch64 and macOS aarch64 have provisioning URLs for the same build but no executed build. Windows x86_64 and macOS x86_64 had no 27.0.1+1 asset on 2026-11-06 and are unsupported until one is pinned and qualified; an installed 27+35 is rejected by the guard. Adoptium checksums for the pinned assets:

| Asset | sha256 |
| --- | --- |
| OpenJDK27U-jdk_x64_linux_hotspot_27.0.1.0.2_1.tar.gz | 30cb129f6cf299c852cec0feca9ea2a596d2ee9f26d8605d3a253951f6c8b20f |
| OpenJDK27U-jdk_aarch64_linux_hotspot_27.0.1.0.2_1.tar.gz | 5ddacf925244a00b60cac828b61ff2f67a68cd32b8dfe5cee1405e333b4589e5 |
| OpenJDK27U-jdk_aarch64_mac_hotspot_27.0.1.0.2_1.tar.gz | c2619cb73ff1d296edd0644d92ae8ed94039bc1bdd43282398835b7f88134fb6 |

`-Dorg.gradle.java.home=<JDK 21>` was probed and does not override the daemon criteria (the daemon stayed on Temurin 27), so a mismatched daemon cannot be forced that way; the deterministic negative check runs the real JVM against a different pin (`scripts/verify-quality-gates.sh`, case `jdk-pin`). The bypass for a machine with another Temurin 27 patch installed is `-Porg.gradle.java.installations.auto-detect=false`, which makes Gradle provision the pinned archive.

On the qualification machine Gradle detected a system Temurin package rather than downloading: `/usr/lib/jvm/temurin-27-jdk-amd64/release` reports `IMPLEMENTOR_VERSION="Temurin-27.0.1.0.2+1"`, and the daemon process runs on that JDK (`ps` shows `/usr/lib/jvm/temurin-27-jdk-amd64/bin/java`). CI installs the same distribution through `actions/setup-java` (`distribution: temurin`, `java-version: '27'`).

### Compile, analyzers and formatter on JDK 27

Rerun on 2026-11-12 with the 9.9.0 wrapper, after stopping the daemon (the first run of this section, on 2026-11-06 with Gradle 9.8.2, had 23 unit and 11 integration tests):

```
$ ./gradlew --stop && ./gradlew clean build --no-build-cache --no-configuration-cache --warning-mode all --console=plain
> Task :backend:compileJava            # javac 27 + Lombok 1.18.48 + Error Prone 2.52.0, -Xlint:all -Werror
> Task :backend:test                   # 127 tests, 0 failures, 0 errors, 0 skipped
> Task :backend:integrationTest        # 147 tests, 0 failures, 0 errors, 0 skipped
> Task :backend:spotlessJavaCheck      # google-java-format 2.0.0 on Java 27 sources
BUILD SUCCESSFUL in 2m 15s
20 actionable tasks: 18 executed, 2 up-to-date
```

`--warning-mode all` printed no Gradle deprecation; the only warnings are Lombok's `sun.misc.Unsafe` notice below. `scripts/verify-quality-gates.sh` passed on the same wrapper (13 backend and frontend gates fail on their injected violations), and CI validates the wrapper jar on every run.

Observations (2026-11-06, unchanged): Error Prone reported a real defect during development (`[FormatString] extra format arguments` on a mis-parenthesised `String.formatted` call), confirming it runs inside javac 27. Lombok prints a JDK 27 deprecation notice at compile time (`sun.misc.Unsafe::objectFieldOffset has been called by lombok.permit.Permit`); it is a warning from Lombok's own internals, not from project code, and does not affect `-Werror`. Gradle reports no deprecated build-script features (`--warning-mode all`).

### Negative gate diagnostics

Output of the first run (2026-11-06, five backend gates). The script has since gained the layering, tenant-internal-grant, wake-up-source and frozen-contract gates and the frontend gates; its current list is in [development.md](development.md#everyday-commands).

```
$ scripts/verify-quality-gates.sh
ok   [formatting]:   ':backend:spotlessJavaCheck' failed with diagnostic matching /OwlMastApplication\.java…|spotlessApply/
ok   [error-prone]:  ':backend:compileJava' failed with diagnostic matching /\[DeadException\]…DeadExceptionViolation\.java/
ok   [lombok]:       ':backend:compileJava' failed with diagnostic matching /DataViolation\.java.*@Data|Use of @Data is flagged/
ok   [module-rules]: ':backend:test --tests …FeatureModuleRulesTest' failed with diagnostic matching /platform must not depend on feature packages|PlatformLeak/
ok   [jdk-pin]:      'help -Powlmast.qualified.jdk.runtime=27.0.0+35' failed with diagnostic matching /is not the qualified JDK.*Eclipse Adoptium 27\.0\.0\+35/
all gates fail correctly on deliberate violations
```

### Container runtime and VectorChord image

Output of 2026-11-06; not rerun on 2026-11-12 (the image digest is pinned and the integration suite above started it).

```
$ docker version        # Client 29.9.2, Server Docker Desktop 4.98.0 (Engine 29.9.2), containerd v2.4.2
$ docker pull tensorchord/vchord-postgres:pg18-v1.1.1
Digest: sha256:700ff05ebdc7e4afd4dd8442e0684293046c3833677fec326550000a04cf8a91
$ docker image inspect tensorchord/vchord-postgres:pg18-v1.1.1 --format '{{json .Config.Cmd}}'
["postgres","-c","shared_preload_libraries=vchord,vector"]
$ docker run -d --name om-qual-vchord -e POSTGRES_PASSWORD=qual tensorchord/vchord-postgres:pg18-v1.1.1
$ docker exec om-qual-vchord psql -U postgres -At \
    -c "select version();" -c "show shared_preload_libraries;" \
    -c "create extension if not exists vchord cascade;" \
    -c "select extname, extversion from pg_extension where extname in ('vchord','vector') order by 1;"
PostgreSQL 18.3 (Debian 18.3-1.pgdg12+1) on x86_64-pc-linux-gnu …
vchord,vector
NOTICE:  installing required extension "vector"
CREATE EXTENSION
vchord|1.1.1
vector|0.8.2
$ docker run -d --name om-qual-plain -e POSTGRES_PASSWORD=qual postgres:18.2-alpine
$ docker exec om-qual-plain psql -U postgres -At -c "create extension if not exists vchord cascade;"
ERROR:  extension "vchord" is not available
```

Finding: Testcontainers' `PostgreSQLContainer` replaces the image command, which drops the preload; the first integration run failed with `ERROR: vchord must be loaded via shared_preload_libraries`. The fixture therefore sets `postgres -c shared_preload_libraries=vchord,vector -c fsync=off` explicitly (`OwlMastPostgres.VECTORCHORD_COMMAND`). Boot's R2DBC service connection additionally needs `org.testcontainers:testcontainers-r2dbc` on the test runtime classpath (`NoClassDefFoundError: org/testcontainers/r2dbc/R2DBCDatabaseContainer` otherwise).

### Integration suite evidence (AC1, AC3, AC4)

From `backend/build/test-results/integrationTest` after the clean build of 2026-11-06 (the suite has grown with every story since; the 2026-11-12 rerun above counts 147 tests):

| Test class | Tests | Proves |
| --- | --- | --- |
| `HealthEndpointIT` | 2 | Application starts against the container; `GET /actuator/health` → 200 `{"status":"UP"}` without component details; readiness probe exposed |
| `BootstrapMigrationIT` | 4 | Flyway applied `V001` successfully; `vchord 1.1.1` and `vector 0.8.2` installed and preloaded; schema baseline readable through the feature API; only bootstrap-owned and extension-owned relations exist |
| `ScopedTransactionsIT` | 16 | Tenant bound to the real transaction survives `publishOn` and a bounded blocking hop; commit persists; failure rolls back; missing scope fails closed before work runs; concurrent transactions keep their own tenant; same-scope nesting joins the same connection and keeps the binding; a nested call with another tenant or principal is rejected before any effect and the joined transaction rolls back; the outer binding survives a caught rejection and the transaction cannot commit; an externally owned transaction cannot commit after a swallowed tenant or principal mismatch; REQUIRES_NEW binds the new connection and restores the outer; sequential transactions inside a SUPPORTS context and after a rollback bind their own scope; participation without an actual transaction is refused |
| `MissingExtensionIT` | 1 | Startup against plain PostgreSQL fails with `extension "vchord" is not available` naming `V001__bootstrap_infrastructure.sql`, without leaking credentials |

Container cleanup: after each run only the Testcontainers reaper (`testcontainers-ryuk`) remains for a few seconds; no PostgreSQL containers are left (`docker ps -a --filter label=org.testcontainers=true`).

### Local run

```
$ ./gradlew :backend:bootTestRun --args='--server.port=18080'
… Successfully applied 1 migration to schema "public", now at version v001
… Netty started on port 18080 (http)
… Started OwlMastApplication in 4.222 seconds
$ curl -s http://localhost:18080/actuator/health
{"groups":["liveness","readiness"],"status":"UP"}
```

## Not adopted, and why

- PMD and Checkstyle: Gradle's 9.8.2 notes (read on 2026-11-06) state PMD does not yet support Java 27; Error Prone plus javac lint and google-java-format cover the static-analysis and style scope without a second parser.
- NullAway/JSpecify: deferred until a feature with nullable boundaries exists; the Boot BOM already manages `jspecify` 1.0.1.
- Spring Modulith: ArchUnit rules are sufficient for the package-by-feature contract and avoid an extra framework pin.
- Spring Security, Keycloak fixtures, Spring AI: owned by E02/OM-04.x; nothing was pinned.
- Palantir Java Format: google-java-format matches the user-cited standard.

## Open items carried forward

- Windows x86_64 and macOS x86_64 are unsupported until Adoptium publishes 27.0.1+1 for them; add the asset URL and qualify a build before claiming support.
- Lombok's `Unsafe` notice will become an error in a future JDK; track Lombok releases before moving past JDK 27.
- Netty prints a JDK native-access notice unless `--enable-native-access=ALL-UNNAMED` is passed. Tests pass it (`backend/build.gradle.kts`), and since 2026-11-12 the runtime image does too: the option is part of the image's `ENTRYPOINT` (`backend/Dockerfile`), because the chart's `backend.javaToolOptions` allow-list refuses everything except named memory and tuning options and so cannot carry it. `scripts/verify-backend-image.sh` checks the entrypoint, that the allow-list still does not admit the option, and that no start prints the JDK's native-access warning. `./gradlew :backend:bootRun` and `bootTestRun` do not pass it; the notice there is harmless on JDK 27.
- The first CI run, on 2026-11-06 on the then-floating GitHub runner label (Docker preinstalled), passed both jobs: https://github.com/gabrianoo/owl-mast/actions/runs/42203046822 (build 1m47s, gate negatives 1m27s). Every job now runs on the fixed `ubuntu-26.04` runner; the current job list is in [development.md](development.md#continuous-integration). The repository has `core.fileMode=false`, so executable bits for `gradlew` and `scripts/verify-quality-gates.sh` must be recorded with `git update-index --chmod=+x` when such files are added.

## Re-check commands

```
curl -sSL https://services.gradle.org/versions/current
curl -sSL 'https://api.adoptium.net/v3/info/release_versions?version=%5B27%2C28%29&release_type=ga'
curl -sSL https://repo1.maven.org/maven2/org/springframework/boot/spring-boot-dependencies/maven-metadata.xml
curl -sSL https://repo1.maven.org/maven2/org/projectlombok/lombok/maven-metadata.xml
curl -sSL https://repo1.maven.org/maven2/com/google/errorprone/error_prone_core/maven-metadata.xml
curl -sSL https://plugins.gradle.org/m2/com/diffplug/spotless/spotless-plugin-gradle/maven-metadata.xml
curl -sSL https://repo1.maven.org/maven2/com/tngtech/archunit/archunit-junit5/maven-metadata.xml
curl -sSL 'https://hub.docker.com/v2/repositories/tensorchord/vchord-postgres/tags?page_size=100'
curl -sSL https://services.gradle.org/distributions/gradle-9.9.0-bin.zip.sha256      # must equal distributionSha256Sum
curl -sSL https://services.gradle.org/distributions/gradle-9.9.0-wrapper.jar.sha256  # must equal sha256sum gradle/wrapper/gradle-wrapper.jar
./gradlew --version && ./gradlew clean build --no-build-cache && scripts/verify-quality-gates.sh
```
