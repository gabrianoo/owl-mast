# OM-01.01 independent review after repair round 1

Verdict: **REQUEST CHANGES — F1 partially repaired; two concrete transaction defects remain. F2 and F3 resolved.**

Reviewed SHA: `b4024d5527a0f1ef000f1ae1531b0f2ff5a8f51f`.
Baseline: `063ad881940a1621736a842eb1c8ffe1bafb0447`.
Prior reviewed SHA: `d1d1ce25b22deceb5f5473f9b0d76ffec7ef6c95`.
Checkout: `/home/gabrianoo/.t3/worktrees/owlmast/t3-a64c6572`.
PR: https://github.com/gabrianoo/owl-mast/pull/105; issue #20.

HEAD matched and `git status --porcelain` was empty at entry and exit. Supplied diff matches `git diff <baseline> HEAD` byte-for-byte, SHA-256 `f44f3cc3b34d014d882c40a3e4d36c55da805d8ea93adc8e097606f17a6d4618`. No tracked source edits, commits, worktree changes, delegates, or GitHub updates were made. A preliminary focused Gradle invocation inadvertently ran in the reviewed checkout after export failed because `python` was unavailable; it failed with “No tests found” and affected ignored build/cache outputs only. All actual reviewer test code and reproductions subsequently used an archive export outside the checkout.

Contract reviewed: product SPEC and adopted epic-01, architecture AD-1–AD-16/deferred ownership, shared story completion and qualification gates, engineering-tracking, implementation claims, original findings and committed round-1 triage. This review combines defect, edge-case and verification-gap lenses without minimum findings or delegation. Future E02 authentication/RLS, deployment and later business features are excluded. Review-only results stay in this report, not a second Notion progress tracker.

## Findings requiring repair

### R1 — Poison does not prevent commit when participating in an externally owned transaction

**Location:** `backend/src/main/java/com/aisquad/owlmast/platform/persistence/ScopedTransactions.java:73–81,97–109`.

**Verified trigger:** an ordinary external `TransactionalOperator` owns the transaction. A scoped call for A inserts a row and completes. A subsequent scoped call for B (using another `ScopedTransactions` instance with the same operator/client) rejects the mismatch. The caller catches that rejection. The external transaction then completes successfully **and persists A's earlier row**.

Reviewer probe `reviewExternalTransactionCaughtMismatchCannotSucceed` uses the actual Spring-injected manager/operator and real fixture:

```java
var first = transactions.inTransaction(s -> insert(s, "first"))
    .contextWrite(Scopes.bind(ScopeContext.of("tenant-a", "person-a")));
var second = new ScopedTransactions(operator, databaseClient)
    .inTransaction(s -> insert(s, "second"))
    .contextWrite(Scopes.bind(ScopeContext.of("tenant-b", "person-b")))
    .onErrorResume(IncompatibleScopeException.class, e -> Mono.empty());
var flow = operator.transactional(first.then(second).thenReturn("success"));
```

The first probe expected an error and received `onNext(success)`. A second run explicitly accepted `success`/completion, then asserted no persisted notes: **failed, expected empty but was `["first"]`**. This independently proves commit, not merely an early emitted value before rollback. The rejected B work does not run; no claim of B data disclosure is made.

**Cause/impact:** poison is checked only when a scoped callback materializes. The earlier A callback has already completed; the mismatched call exits `joinOrBind` before that check. Setting the participating status rollback-only does not prevent the externally owned transaction from committing on this actual dependency stack. The advertised caught-error atomicity contract is false for external participation, violating the F1 repair requirement and AC3/AD-5.

**Required fix/verification:** enforce poison at the actual transaction completion boundary, including external owners (for example a correctly registered reactive `beforeCommit` synchronization that errors and forces rollback). Retain same-scope participation. Add a real integration regression with an external owner, two separate helper instances, a swallowed mismatch, and persisted-row assertions; verify principal-only mismatch too. Assert failure and zero committed effects, not just that the inner callback was rejected.

### R2 — Scope resource lifetime is longer than the database transaction it claims to describe

**Location:** `backend/src/main/java/com/aisquad/owlmast/platform/persistence/ScopedTransactions.java:35,88–95`.

**Verified triggers:**

1. Outer scoped REQUIRED transaction A invokes another helper configured with Spring `PROPAGATION_REQUIRES_NEW` under the same scope. The new connection's `boundTenant()` is empty: probe expected `tenant-a`, received sentinel `MISSING`.
2. An external `PROPAGATION_SUPPORTS` operator with no database transaction wraps two sequential default scoped REQUIRED calls, first A then B. The first physical transaction ends; the second incorrectly rejects B as incompatible with A. Probe expected `tenant-b`, received `IncompatibleScopeException`.

**Cause/impact:** `bindResource` alone does not attach lifecycle callbacks. Nothing unbinds this static-key resource after completion or suspends/restores it when the actual R2DBC resource is suspended. The equality branch mistakes a surviving resource for proof that the current connection has been initialized. This causes unscoped work on a new transaction and false rejection after an earlier transaction has ended. The exported tests use supported Spring operator configuration through the existing public constructor; no production API or authorization feature is invented.

**Required fix/verification:** bind state to the actual transaction lifecycle, with cleanup after commit/rollback and suspension/resumption matching the database resource; alternatively explicitly reject unsupported participation before executing work. Do not silently run work on an unbound connection. Cover REQUIRES_NEW same-scope binding and outer restoration, sequential transactions within SUPPORTS, rollback cleanup, and retain existing same-scope/default REQUIRED composition. Mere lexical cleanup on inner helper return would break legitimate same-transaction participation.

Spring's reactive synchronization contract explicitly provides resource suspend/resume and completion callbacks, and describes errors from `beforeCommit` as causing rollback: [Spring Framework TransactionSynchronization](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/reactive/TransactionSynchronization.html). Local Spring 7.0.10 bytecode inspection additionally confirms `TransactionContext.clear()` does not clear its resource map. The database probes are the decisive evidence.

## Lens disposition

- **Defect lens:** R1 and R2 are executable failures, not hypothetical missing tests.
- **Edge-case lens:** external-owner completion bypasses the callback poison check (R1); transaction suspension and completion lack scope-resource lifetime handling (R2). Same-scope nesting, principal equality checks, missing-scope rejection, bounded blocking and bounded diagnostic cause traversal have explicit handling.
- **Verification-gap lens:** repository-wide searches for `ScopedTransactions`/`SCOPE_RESOURCE` found the production wiring, helper and its unit/integration tests. The existing eight integration tests cover helper-owned transactions, including swallowed errors inside an outer helper callback. None exercises an external owner, separate instances, suspension, or sequential physical transactions within an ambient context. Those missing boundary assertions let R1/R2 pass. Close these gaps with the regression cases above; do not count them as additional independent defects.

## F1–F3 verdicts

**F1 — partially resolved, remains open.** Existing same-scope nesting uses the same backend PID and preserves the tenant. Different tenant/principal rejects before inner work; a swallowed mismatch inside an outer helper callback produces the poison error and rolls back. All those existing tests pass independently. An additional reviewer probe across separate helper instances and `publishOn` passed and committed the expected row. R1 and R2 nevertheless show that the resource is not fully bound to the actual transaction lifecycle and poison is not universally enforced. Committed triage describes the caught-error test as `UnexpectedRollbackException`; actual test/source expects `IncompatibleScopeException` containing “cannot commit”. Correct that evidence wording when recording repair results.

**F2 — resolved.** Health logs pass only the String returned by `SafeFailure.describe`, never the Throwable. Actual source uses exception class names, identity-cycle detection and a five-entry depth bound; it excludes messages, stacks and suppressed exceptions. The captured-output component test checks outer/nested secret markers and stack lines are absent, retains safe DOWN details, and requires the useful class chain. Both helper tests and the health tests passed independently. This preserves failure category/cause-category diagnostics without retaining unrestricted exception text. No claim is made that every third-party startup logger is sanitized by this helper.

**F3 — resolved for qualified Linux x86_64 scope, with bounded evidence.** Settings compares the actual daemon runtime/vendor; backend `JavaCompile`, `Test`, and `JavaExec` actions compare resolved compiler/launcher metadata through `QualifiedJdk`. Test execution also asserts its own runtime/vendor. CI requests Temurin `27.0.1`; guards require full `27.0.1.0.2+1`, so another build cannot silently satisfy the ordinary executing tasks. Distribution/vendor aliases are handled. The platform qualification claim is narrowed appropriately. This is enforcement by rejection, not an exact-patch Gradle selector; [Gradle toolchains documentation](https://docs.gradle.org/current/userguide/toolchains.html) describes the underlying selection model.

The existing negative case changes the expected pin, so it proves the daemon guard rejects a runtime mismatch, not alternate-installed-JVM selection or every launcher rejection path. I independently reran it in the export: `help -Powlmast.qualified.jdk.runtime=27.0.0+35` failed at settings line 33 and named actual/expected builds. Source inspection plus positive real compilation/test execution and exact-head CI provide meaningful adequacy for the reported F3 fix. No observed compiler/launcher bypass is asserted; an alternate installed JVM matrix remains unexecuted. Do not describe this negative as having selected another installed JVM.

## Acceptance criteria

| Criterion | Verdict and basis |
| --- | --- |
| AC1 / T1 | Pass for qualified Linux x86_64 path. Java 27/Boot 4.1.2 Kotlin-DSL build and health tests pass; exact JDK enforcement is present. Clean build is coordinator evidence, not a new full-build claim from this reviewer. |
| AC2 | Pass for story scope. Feature owns its API/port/persistence; production ArchUnit import is asserted; formatter/Error Prone/Lombok/module negative fixtures have useful diagnostic checks and CI succeeds. No new failure found. |
| AC3 | Request changes: R1/R2. Explicit async scope and bounded blocking pass, but transaction lifetime and caught-mismatch rollback are incomplete. |
| AC4 | Pass for foundational fixture path. Actual pinned VectorChord/pgvector, Flyway migration/ownership, commit/rollback, health and plain-PostgreSQL failure tests pass. Runtime guard fails explicitly rather than skipping. R1/R2 remain AC3 defects; this does not waive them. |

## Executed evidence and limits

Temporary archive: `/tmp/owl-mast-round1-independent-probe`. Added probes are retained in `backend/src/integrationTest/java/com/aisquad/owlmast/platform/persistence/ReviewScopeProbeIT.java`; original `ScopedTransactionsIT.java` was restored in this export before rerunning original tests.

- `/tmp/owl-mast-round1-probe.log`: four new probes; one pass, three failures (R1, two manifestations of R2).
- `/tmp/owl-mast-round1-external.log`: follow-up explicitly proves persisted `["first"]` after swallowed mismatch and successful external completion.
- `/tmp/owl-mast-round1-existing-tests.log`: `:backend:test :backend:integrationTest` with filters selecting the four original integration classes; **26 unit/component + 15 integration tests, zero failures/errors/skips**, independently counted from resulting XML. No original test source was weakened.
- `/tmp/owl-mast-round1-jdk-negative.log`: expected pin mismatch fails explicitly.
- GitHub API observed [CI run 42206224899](https://github.com/gabrianoo/owl-mast/actions/runs/42206224899) completed/success at exactly `b4024d5527a0f1ef000f1ae1531b0f2ff5a8f51f`. No watch or GitHub mutation was used.

The four other negative gates and clean build were not unnecessarily repeated; CI/coordinator evidence and source were inspected. Docker-unavailable discovery was not independently induced end-to-end. Arbitrary cancellation schedules, other transaction managers, alternate installed JVMs and unqualified operating systems are not claimed proven. No E02 auth/RLS implementation is requested.

PR https://github.com/gabrianoo/owl-mast/pull/105, head b4024d5527a0f1ef000f1ae1531b0f2ff5a8f51f, checks and reviews CI SUCCESS; original 41 tests PASS; independent review REQUEST CHANGES (F1 partial: R1/R2; F2/F3 resolved).
