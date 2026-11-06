# OM-01.01 independent initial review

Verdict: **REQUEST CHANGES**.

Reviewed head: `d1d1ce25b22deceb5f5473f9b0d76ffec7ef6c95`.
Baseline: `063ad881940a1621736a842eb1c8ffe1bafb0447`.
Checkout: `/home/gabrianoo/.t3/worktrees/owlmast/t3-a64c6572`.
PR: https://github.com/gabrianoo/owl-mast/pull/105
Issue: https://github.com/gabrianoo/owl-mast/issues/20

`git status --porcelain` was empty at entry and exit; HEAD matched the requested SHA both times. The supplied unified diff exactly matches `git diff <baseline> HEAD`: both SHA-256 digests are `4d926367c616eda636425f1d25080edba6efa079f82c2552dabc389e47d584e4`. No checkout edits, GitHub updates, pushes or delegates were made. Focused reproduction used a Git archive exported to `/tmp/owl-mast-review-probe-d1d1ce25`, with only an additional reviewer test in that external copy.

This is the assigned independent review phase of bmad-build, covering defect discovery, the supplied edge-case path-tracing lens, and the supplied verification-gap lens in one task. It does not start another build workflow or its delegation. Contract basis: SPEC.md, architecture spine AD-1–AD-16 and Deferred owners, epic-01 OM-01.01 AC1–AC4/T1–T4, epics.md shared completion/qualification gates, and engineering-tracking.md. Implementation claims were checked against source/test evidence, not accepted as proof.

## Findings requiring changes

### F1 — Nested scoped transactions silently change the outer transaction's tenant

**Location:** `backend/src/main/java/com/aisquad/owlmast/platform/persistence/ScopedTransactions.java:33–38,52–57`.

**Verified failure:** `inTransaction` unconditionally runs transaction-local `set_config`. Its default Spring TransactionalOperator participates in an existing transaction. An outer call bound to tenant A can invoke an inner call under tenant B's Reactor Context; the inner call overwrites the same connection's setting. After the inner publisher completes, the outer Reactor scope is A but the database scope remains B.

Independent real-database reproduction added `reviewNestedScopeDoesNotOverwriteOuterTenant` to the external copy of ScopedTransactionsIT:

```java
Mono<String> flow = transactions.inTransaction(outer ->
    transactions.inTransaction(inner -> transactions.boundTenant())
        .contextWrite(Scopes.bind(ScopeContext.of("tenant-b", "person-b")))
        .then(transactions.boundTenant()))
    .contextWrite(Scopes.bind(ScopeContext.of("tenant-a", "person-a")));
StepVerifier.create(flow).expectNext("tenant-a").verifyComplete();
```

Command: `./gradlew :backend:integrationTest --tests '*reviewNestedScopeDoesNotOverwriteOuterTenant' --console=plain` in the external copy. Result: **1 test executed, 1 failed**, `expected value: tenant-a; actual value: tenant-b`. Log: `/tmp/owl-mast-review-nested.log`; XML under `/tmp/owl-mast-review-probe-d1d1ce25/backend/build/test-results/integrationTest/`.

**Impact:** the shared primitive violates AD-5/AC3's binding of explicit scope to the actual transaction. Subsequent outer SQL observes the wrong tenant. This is a demonstrated primitive failure, not a claim of a presently exploitable authenticated endpoint or implemented RLS.

**Required fix/verification:** define safe participation semantics. Reject incompatible scope before executing inner work or changing a joined transaction's setting; preserve same-scope composition. Test real-database same-scope nesting, mismatched scope rejection without inner effects, outer scope after rejection, and rollback. Consider principal changes as part of the explicit security-context contract. Do not silently use independent transactions if that breaks intended atomicity.

**Existing evidence:** repository-wide ScopedTransactions references lead to its unit test and four integration tests. They cover absent scope, top-level commit/rollback, async hops and two independent concurrent transactions; none tests joining an existing transaction under another scope. No existing production business operation invokes it yet; this is the foundation primitive introduced for future callers.

### F2 — Health failures leak the exception into logs despite a passing secret-safety test

**Location:** `backend/src/main/java/com/aisquad/owlmast/bootstrap/adapter/health/SchemaBaselineHealthIndicator.java:26–29`; `backend/src/test/java/com/aisquad/owlmast/bootstrap/adapter/health/SchemaBaselineHealthIndicatorTest.java:39–49`.

**Verified failure:** the error handler returns a safe health detail but calls `log.warn("Schema baseline health check failed", failure)`. The existing test deliberately injects an exception containing a synthetic password marker and asserts only that the returned details omit it. The actual existing passing test XML contains the exception's complete unsafe message in `<system-out>` at lines 7–9. Thus this is already reproduced by the submitted tests, not speculation about a driver possibly logging something. The marker is synthetic; no real credential was inspected or reproduced in this report.

**Impact:** exception messages/causes containing credentials or restricted payloads pass unchanged into diagnostics. This violates SPEC constraints, NFR-6 and the documented backend convention even though the HTTP health payload stays safe. The CI workflow uploads HTML test reports, making captured diagnostic output another relevant sink.

**Required fix/verification:** log only safe bounded diagnostic metadata; do not attach an unrestricted throwable/message/cause chain. Extend the component test to capture actual logging output and verify that markers in both outer and nested exception messages are absent, while DOWN and a useful safe reason remain observable. Retain response-body assertions. This does not require E02 authentication work.

### F3 — The qualified JDK patch is documented but not enforced locally or in CI

**Location:** `gradle/gradle-daemon-jvm.properties:4–9`; `backend/build.gradle.kts:16–20`; `.github/workflows/ci.yml:22–25,46–49`; `docs/toolchain-qualification.md` JDK/pins sections.

**Verified configuration defect:** both daemon criteria and compiler toolchain select only Java major 27 and vendor ADOPTIUM. Both CI jobs request Temurin `java-version: '27'`. Direct daemon download URLs select particular archives only when no matching local JDK exists. An already-installed Temurin 27 of another patch satisfies the criteria; neither a build guard nor test compares the resolved daemon/compiler/test JVM full version with the qualified patch. CI can resolve a newer patch without a repository change. The qualification document itself confirms local reuse rather than download.

Vendor/distribution **is** constrained; do not report that any vendor is accepted. Patch **is not** constrained. The actual local release file reports `Temurin-27.0.1.0.2+1`, consistent with the recorded successful build. No alternate-JDK build was run; the defect is the demonstrably insufficient selection/validation configuration, not a claim that another patch fails compilation.

**Impact:** T1 and the architecture Deferred gate require qualified JDK distribution/patch pins before shared build reliance. Current green builds demonstrate today's selected patch, not reproducibility of that pin on another machine or future CI run.

**Required fix/verification:** specify an explicit qualified full version in CI, enforce/validate resolved daemon and compilation/test runtime versions locally, and fail with a clear diagnostic for unqualified installed patches. If multiple platform-specific builds are intentionally accepted, document and validate an explicit qualified matrix. Show the qualified build passes and a mismatched installed patch fails or is bypassed in favor of the pin.

**OS scope:** executable qualification currently covers WSL2 Linux x86_64 and Ubuntu CI. Linux/aarch64 and macOS/aarch64 download URLs alone are not runtime qualification. Windows x64 intentionally references GA 27+35; that alone is not evidence it is incompatible. The comment/documentation says macOS x64 pins GA, but there is no MAC_OS.X86_64 URL. Correct that documentation or supply/qualify the intended platform; this review does not demand Windows/macOS support or a broader OS test matrix as an unstated AC.

Primary semantics: [Gradle daemon auto-detection/provisioning](https://docs.gradle.org/current/userguide/gradle_daemon.html#sec:daemon_jvm_auto_detection) explains that platform URLs are used only when no local matching JDK exists; [Gradle toolchains](https://docs.gradle.org/current/userguide/toolchains.html) describes language-version/vendor selection. [Spring transaction propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html) explains participation in an existing REQUIRED transaction; F1 additionally has executable evidence.

## Verification-gap lens

### The health-error test verifies the response but misses the diagnostic sink (F2)

- **Changed surface:** health failure handling, SchemaBaselineHealthIndicator.java:26–29.
- **Impacted consumer:** application log output and captured test reports; health endpoint response is separately covered.
- **Existing test evidence:** SchemaBaselineHealthIndicatorTest.java:39–49 asserts DOWN and sanitized details, but never observes logs. Its passing XML already contains the supplied synthetic secret marker in system-out.
- **Missing verification:** captured logging assertions covering exception messages and causes.
- **Demonstration:** leaking the original exception to the logger ships green because only Health.details is examined.
- **Consequence:** diagnostic-safety failure is accepted as a passing safety test.
- **Disposition:** patch the same component test with captured log-output assertions while fixing F2.

F1 is a correctness defect with a missing nested-transaction case, not a separate duplicated gap finding. F3 is an enforcement defect, not a request for source-text tests. Repository symbol/import searches and the actual tests were examined before describing their limits.

## Edge-case lens (unhandled paths, deduplicated with findings)

```json
[
  {
    "location": "backend/src/main/java/com/aisquad/owlmast/platform/persistence/ScopedTransactions.java:33-38",
    "trigger_condition": "A nested transaction binds another tenant while joining an existing transaction",
    "guard_snippet": "rejectIncompatibleScopeBeforeBindingOrWork(existingTransactionScope, requestedScope);",
    "potential_consequence": "Outer Reactor scope and database tenant disagree after the inner operation"
  },
  {
    "location": "backend/src/main/java/com/aisquad/owlmast/bootstrap/adapter/health/SchemaBaselineHealthIndicator.java:26-29",
    "trigger_condition": "The failed health query supplies an exception containing sensitive text",
    "guard_snippet": "log.warn(\"Schema baseline health check failed\");",
    "potential_consequence": "Sensitive exception messages and causes enter application logs and captured reports"
  },
  {
    "location": "gradle/gradle-daemon-jvm.properties:8-9",
    "trigger_condition": "Another Temurin 27 patch is installed or selected by CI",
    "guard_snippet": "validateResolvedJvmsAgainstQualifiedFullVersions();",
    "potential_consequence": "Builds silently use an unqualified patch despite the documented pin"
  }
]
```

The diff adds files and ignore entries; it deletes no meaningful pre-existing implementation, so the secondary deletion review is inapplicable. Claims about safe diagnostics and fully pinned runtime are contradicted by F2/F3. Claims about basic startup, real migrations and ordinary transaction paths are supported by the actual tests.

## Acceptance and evidence

| Criterion | Evidence and verdict |
|---|---|
| AC1 | **Build/start behavior passes on the qualified observed machine; T1 pin gate remains incomplete (F3).** Existing XML shows HealthEndpointIT's two real HTTP checks succeed against the container. Gradle Kotlin DSL selects Java 27 and Boot 4.1.2. Official [Boot system requirements](https://docs.spring.io/spring-boot/system-requirements.html) support Java 27/Gradle 9.x; [Gradle 9.8.2 notes](https://docs.gradle.org/9.8.2/release-notes.html) support Java 27 for daemon and toolchains. No guessed version substitution is needed. |
| AC2 | **Pass for story scope.** Bootstrap owns its public query interface, repository port and persistence adapter. Actual production classes are imported into ArchUnit; rules cover cross-feature private imports, cycles, platform direction, adapter direction, ThreadLocal and publisher blocking. Negative fixtures assert useful rule/class diagnostics; CI's separate negative job injects formatter, Error Prone, Lombok and module violations. No requirement for E02 or frontend gates is introduced. |
| AC3 | **Request changes (F1).** Reactor Context explicitly carries tenant/principal; absence fails before transaction acquisition, async/blocking hops and concurrent top-level transactions are tested, bounded scheduler capacity/deadline tests are meaningful. Nevertheless joined transactions can corrupt scope as independently reproduced. No ThreadLocal-only authorization or existing detached application subscription was found. |
| AC4 | **Pass for the qualified local/CI path, with stated verification limits.** Eleven existing integration tests cover actual Flyway V001, bootstrap-owned relations, pinned vchord 1.1.1/vector 0.8.2, preloading, real commits/rollbacks, health, and explicit failure on a plain PostgreSQL image. Spring owns service-container teardown; the plain container uses try-with-resources. Independent probe also ran the real fixture. Final `docker ps -a --filter label=org.testcontainers=true` was empty. Missing-runtime guard explicitly throws, is invoked by the fixture, and has true/false unit checks; I did not independently disable Docker to test discovery failure end-to-end. |

Cross-cutting contract: **request changes for diagnostic safety (F2)** even though successful AC1/AC4 paths pass.

Existing checkout XML totals: **23 unit/component tests + 11 integration tests, zero failures/errors/skips**. These are inspected existing results, not a newly claimed full build. The coordinator supplied its clean no-cache build result; this review did not repeat the full build unnecessarily.

GitHub API independently confirmed run https://github.com/gabrianoo/owl-mast/actions/runs/42203364755 is completed/success at the exact reviewed head and both jobs are success. This review does not override that check result; the newly added independent nested-scope probe fails despite those checks.

Dependency inspection: backend lockAllConfigurations is enabled; committed lock entries cover compile/runtime, annotation processing/Error Prone, unit/test-fixture and integration classpaths. Boot BOM and plugin versions are explicit; wrapper distribution has a checksum; database images include digests. No concrete lock-resolution failure was found. This is not a claim that application dependency locks pin the JDK or every plugin-internal artifact.

Other limits: cleanup was observed, not tested by a dedicated lifecycle assertion. No proof is claimed for arbitrary Docker-compatible engines, non-Linux hosts, cancellation/pooled-connection reuse under every schedule, or production database failure logging outside this handler. These are not inflated into additional findings. E02 authentication/authorization, deployment, frontend, durable jobs/audit and later stories remain excluded. The health/bootstrap schema is infrastructure, so lack of tenant authorization on its baseline query is not treated as an E02 defect.

The report and probe artifacts remain outside the reviewed checkout. No engineering status was changed in GitHub or mirrored into Notion.

PR https://github.com/gabrianoo/owl-mast/pull/105, head d1d1ce25b22deceb5f5473f9b0d76ffec7ef6c95, checks and reviews existing CI SUCCESS; independent review REQUEST CHANGES (F1–F3)
