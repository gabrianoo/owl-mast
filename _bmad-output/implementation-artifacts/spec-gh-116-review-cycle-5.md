---
title: 'OM-01.02 review→fix loop, build cycle 5: resolve review 5867361425 (PR #116)'
type: 'bugfix'
created: '2026-11-12'
status: 'done'
route: 'oneshot'
review_loop_iteration: 0
baseline_commit: '077366186040d063baac4c70c7995dc028488a58'
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The cycle-5 review of PR #116 at `0773661` left 1 inline comment (material, verification gap). `c729bb9` moved every test where a positive cache interval runs out onto a virtual clock, so no test lets a positive interval expire on the pair production uses: `System::nanoTime` and `Schedulers.parallel()` (`IdentityDiscoveryHealthIndicator.java:69`).

**Approach:** On branch `t3/om-01-02-review-findings`, add one real-time test on the production constructor that checks only the expiry side: a small positive interval, a bounded polling wait until well past it, then a second discovery request. Prove by mutation that a timer that never fires makes it fail. Reply on the thread with the commit and resolve it; add a cycle-5 line to the PR body. The owner delegated this cycle in full, so the approval checkpoint is taken as given. Do not touch the main checkout or the Kind cluster `owl-mast-om0102`, do not merge or approve, and leave the two owner-deferred threads open.

</frozen-after-approval>

## Implementation Notes

- Scope note. The owner delegated the cycle in full, so the planning checkpoint was not held. This session is itself the implementation sub-agent of the owner's review→fix loop, so it started no further sub-agents: the Blind Hunter review layer was skipped, and the independent review of this change is the loop's next review cycle. The diff was self-reviewed.
- Changed: `backend/src/test/java/com/aisquad/owlmast/access/adapter/identity/IdentityDiscoveryHealthIndicatorTest.java` only. New test `aPositiveIntervalExpiresOnTheProductionClockAndTimer`. No production code changed.
- What the test does. It builds the indicator with the three-argument constructor (the one the two-argument production constructor delegates to with `CACHE_TTL`) and a 250 ms interval. After the first answer it evaluates `health()` every 25 ms until the stub has received a second request or 10 s have passed, then asserts exactly one more request. It makes no "still cached" assertion in real time.
- Guard against a vacuous pass. If the first answer takes 250 ms or longer, `remaining()` may be zero and nothing is handed to the timer, so the attempt would prove nothing. The test measures the first answer and, in that case, retries with a new indicator (up to five attempts, then it fails). Run alone, the cold first request does exceed 250 ms and the second attempt is the one that counts (0.63 s per run); inside the class the first attempt counts (0.27 s).
- Fix commit: `b58a97b69ebb5ce5c551bc76168e571807fdfb1e`.

Mutation checks, each applied alone and then reverted (`IdentityDiscoveryHealthIndicatorTest`, 23 tests):

| Mutation | Result |
|---|---|
| M1, test: five-argument constructor with `System::nanoTime` and a `VirtualTimeScheduler` that is never advanced (a timer that never fires) | the new test fails after its 10 s deadline: "expected: 2 but was: 1"; the other 22 pass |
| M5, production: the three-argument constructor passes a scheduler that accepts a delayed task and never runs it | the new test fails the same way; the other 22 pass. Only the new test detects this |
| M2, production: `Schedulers.immediate()` instead of `Schedulers.parallel()` | 15 tests fail, the new one included (blocking read times out) |
| M3, production: a disposed scheduler | 15 tests fail, the new one included |
| M4, production: the clock in seconds instead of nanoseconds | the new test passes; `anAnswerSlowerThanTheIntervalIsDeliveredButNotKept` fails |

- Correction to the review text. The review says the suite would still pass with `Schedulers.immediate()` or a disposed scheduler. It does not: 14 tests that already existed at `0773661` fail under M2 and M3, because the rejected delayed task leaves the evaluation without an answer. The gap that was real is a timer that accepts the task and never fires (M1, M5), and a clock that runs too slow is caught by an existing test (M4).
- Not covered by the new test: a clock that runs too fast against the timer (the result is then never kept). The cache-hit tests on the production constructor (`theProductionConstructorCachesForTheDocumentedInterval`, `theConfiguredBeanCachesToo`) cover that direction.

Disposition (comment id → outcome). PR #116 review 5867361425, 1 thread, fixed:

| Comment | Thread | Outcome | Where |
|---|---|---|---|
| 4544917211 no test lets a positive interval expire on the production clock and timer (material) | `PRRT_kwDOVjxExc62az6Y` | fixed | `aPositiveIntervalExpiresOnTheProductionClockAndTimer` |

No new owner decision in this cycle.

Left open on purpose, owner-deferred from cycle 1: `PRRT_kwDOVjxExc62YN_x` (Kind rerun for chart 0.2.0) and `PRRT_kwDOVjxExc62YN0L` (Gateway CEL rules against a real API server).

Verification record, local, 2026-11-12:
- Stability: the new test was run alone 25 times in a row with `--rerun`: 25 passes, 0.61–0.66 s each.
- `./gradlew build`: BUILD SUCCESSFUL; 67 unit tests and 27 integration tests, no failures, no skips (JUnit XML). 66 unit tests at `0773661`.
- `scripts/verify-install-package.sh` was not run: the change is one backend test file and this record.
- Not run: the Kind qualification (cluster `owl-mast-om0102` untouched) and any server-side Gateway API check. Both stay deferred.

## Verification

**Commands:**
- `./gradlew build --console=plain` -- expected: BUILD SUCCESSFUL.
- `./gradlew :backend:test --rerun --tests '*IdentityDiscoveryHealthIndicatorTest.aPositiveIntervalExpiresOnTheProductionClockAndTimer'` -- expected: passes on every run.
