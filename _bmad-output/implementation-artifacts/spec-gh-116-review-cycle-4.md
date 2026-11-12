---
title: 'OM-01.02 review→fix loop, build cycle 4: resolve review 5867158649 (PR #116)'
type: 'bugfix'
created: '2026-11-12'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: '689e6920757de0531615d1382ed3e3cc179466ea'
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The cycle-4 review of PR #116 at `689e692` left 5 inline comments (3 material, 2 minor). The first is a way around the cycle-3 `ipBlock` floor (D23): an IPv4-mapped IPv6 range such as `::ffff:0.0.0.0/96` meets the IPv6 `/32` floor, and Go reads it as `0.0.0.0/0`. The others are tests that were missing or depended on machine speed.

**Approach:** On branch `t3/om-01-02-review-findings`, fix each finding with a test that pins it, or reject it with a concrete reason. Reply on every thread with the commit and resolve it; update the PR body. The owner delegated this cycle in full, so the approval checkpoint is taken as given.

## Boundaries & Constraints

**Always:** CI jobs pin `ubuntu-26.04`. Gateway API HTTPRoute stays first class next to the optional Ingress (frozen API, not deprecated). Render support is stated separately from runtime qualification.

**Never:** Touch the main checkout. Delete or run qualification against the Kind cluster `owl-mast-om0102`. Merge the PR or post an APPROVE review. Resolve the two owner-deferred threads (`PRRT_kwDOVjxExc62YN_x`, `PRRT_kwDOVjxExc62YN0L`).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| IPv4-mapped peer | `proxyHeaders` set; `ipBlock.cidr` `::ffff:0:0/96`, `::FFFF:0:0/96`, `0:0:0:0:0:ffff:0:0/96`, zero-padded groups | render refused | message names the entry and says to write the IPv4 range |
| Dotted form | `::ffff:0.0.0.0/96`, `::ffff:10.0.0.0/104`, `64:ff9b::10.0.0.0/104` | render refused | "must not embed a dotted IPv4 address" |
| IPv4-compatible peer | `::a00:0/104`, `::/96`, `::1/128` | render refused | same message as mapped |
| Malformed IPv6 | two `::`, nine groups, a five-digit group | render refused | "not an IPv6 address of eight hexadecimal groups" |
| Real IPv6 range | `2001:db8:1234::/48`, `2001:db8:0:0:0:ffff:0:0/96` | rendered | N/A |
| Mismatch warning | published value A, then B, then A | three WARN lines, in order | a repeated value adds none |
| Mismatch warning | A, then the matching issuer, then A | two WARN lines for A | none while the issuer matches |
| Cache interval | answer takes 1.5 s, interval 2 s, virtual clock | cached until 2 s after the request start, then a new request | N/A |
| NOTES claim | default; `existingClaim=prior-data`; shortened fullname | the claim the PostgreSQL pod mounts | line absent for an external database |
| Schema IPv4 pattern | Gateway hostname copy | equal to `owl-mast.ipv4Pattern` | a third copy fails the test |

</frozen-after-approval>

## Code Map

- `deploy/helm/owl-mast/templates/_helpers.tpl` -- `owl-mast.validate`, the `ipBlock` branch of the `proxyHeaders` peer loop; `owl-mast.ipv4Pattern`.
- `deploy/helm/owl-mast/templates/NOTES.txt` -- the "Bundled PostgreSQL" line (not changed).
- `deploy/helm/owl-mast/values.schema.json` -- `routing.gateway.hostnames.items.not.pattern` and `$defs.ingressHost.not.pattern` (not changed).
- `deploy/tests/test_chart_render.py` -- `ReviewCycle4Test`; `ReviewCycle3Test.test_readiness_period_rule_rests_on_a_cache_counted_from_the_request` reads the Java source text `remaining(cacheTtl, timed.startedNanos())`, which must stay.
- `backend/src/main/java/com/aisquad/owlmast/access/adapter/identity/IdentityDiscoveryHealthIndicator.java` -- clock and timer as constructor arguments.
- `backend/src/testFixtures/java/com/aisquad/owlmast/testing/StubIdentityProvider.java` -- `publish`, `holdAnswers`, `releaseAnswers`.
- `backend/src/test/java/com/aisquad/owlmast/access/adapter/identity/IdentityDiscoveryHealthIndicatorTest.java`.
- `docs/installation.md`, `deploy/helm/owl-mast/values.yaml` -- the `proxyHeaders` peer rule.

## Tasks & Acceptance

**Execution:**
- [x] `deploy/helm/owl-mast/templates/_helpers.tpl` -- refuse an IPv6 `ipBlock` that embeds an IPv4 address; read an IPv6 address group by group.
- [x] `deploy/tests/test_chart_render.py` -- `ReviewCycle4Test`: the CIDR spellings, the NOTES claim line, the schema pattern copies.
- [x] `backend/src/` -- switchable and holdable stub provider; re-log tests; cache tests on a virtual clock.
- [x] `docs/installation.md`, `values.yaml` -- state the new refusal.

**Acceptance Criteria:**
- Given the branch head, when `scripts/verify-install-package.sh`, `./gradlew build` and `scripts/verify-backend-image.sh` run, then all pass locally and every CI check on PR #116 is green.
- Given each of the 5 threads, when the cycle ends, then it carries a reply naming the commit and is resolved, or is listed as rejected or deferred with its reason.
- Given `lastWarnedIssuer.set(null)` is deleted, when the backend tests run, then a test fails.

## Implementation Notes

- Scope note. The owner delegated the cycle in full, so the planning checkpoint was not held. This session is itself the implementation sub-agent of the owner's review→fix loop, so it started no further sub-agents: the implementation was done directly, and the independent review of this change is the loop's next review cycle, not an in-session reviewer layer. The diff was self-reviewed.
- Fix commit: `c729bb918ba5fc95383aa405b5e77a301350efed`.
- Mutation checks: 12 single changes were applied one at a time, and each time a test written for the finding failed.
  - Backend (3): `lastWarnedIssuer.set(null)` deleted; `getAndSet` replaced by a one-shot `compareAndSet(null, …)`; the interval counted from the answer.
  - Chart (9): the NOTES `default` dropped; only `existingClaim` printed; the `database.bundled` guard removed; the mapped check off; the compatible check off; the dotted check off; no zero stripping; no lowercasing; the Gateway copy of the schema pattern edited.
- The IPv6 refusal was not checked against a Go program or an API server in this cycle. The claim that Go reads `::ffff:0.0.0.0/96` as `0.0.0.0/0` is the review's; the chart refuses the range whether or not a given cluster would admit it.
- Production behaviour of the health indicator is unchanged: the two existing constructors pass `System::nanoTime` and `Schedulers.parallel()`, which is what `Mono.cache` used before.

Disposition (comment id → outcome). PR #116 review 5867158649, 5 threads, all fixed, none rejected, none deferred:

| Comment | Thread | Outcome | Where |
|---|---|---|---|
| 4544747310 IPv4-mapped `ipBlock` passes the D23 floor (material) | `PRRT_kwDOVjxExc62abat` | fixed | `_helpers.tpl`: an IPv6 range that embeds an IPv4 address is refused; `test_proxy_headers_ip_block_cannot_embed_an_ipv4_range` (28 refused spellings, 8 malformed, 10 accepted) |
| 4544747325 no test logs the warning a second time (material) | `PRRT_kwDOVjxExc62aba1` | fixed | `theMismatchWarningIsLoggedAgainWhenThePublishedValueChanges`, `theMismatchWarningIsLoggedAgainAfterTheIssuerMatchedInBetween`; `StubIdentityProvider.publish` |
| 4544747330 NOTES claim line partly tested (material) | `PRRT_kwDOVjxExc62aba5` | fixed | `test_notes_print_the_postgresql_claim_the_release_uses` |
| 4544747340 0.5 s margin in the cache test | `PRRT_kwDOVjxExc62abbB` | fixed | virtual clock and held answers; three timing tests no longer sleep |
| 4544747354 Gateway copy of the IPv4 pattern not pinned | `PRRT_kwDOVjxExc62abbI` | fixed | `test_every_schema_copy_of_the_ipv4_pattern_is_the_helpers` |

New owner decisions, D29–D30 in the PR body:

- D29: with `proxyHeaders`, an IPv6 `ipBlock` that embeds an IPv4 address is refused outright, whatever its prefix. This covers IPv4-mapped ranges, IPv4-compatible ranges (so also `::1/128` and every range below `::/80`), and any dotted spelling (so also NAT64 written as `64:ff9b::10.0.0.0/104`). The alternative was to apply the IPv4 `/8` floor to the embedded prefix.
- D30: `IdentityDiscoveryHealthIndicator` has a package-private constructor that takes the nano clock and the expiry timer, used by tests only.

Left open on purpose, owner-deferred from cycle 1: `PRRT_kwDOVjxExc62YN_x` (Kind rerun for chart 0.2.0) and `PRRT_kwDOVjxExc62YN0L` (Gateway CEL rules against a real API server).

Verification record for `c729bb9`, local, 2026-11-12:
- `scripts/verify-install-package.sh` with a freshly downloaded, checksum-verified Helm and kubectl: 181 tests OK, none skipped (178 at `12fad93`).
- `./gradlew build`: BUILD SUCCESSFUL; 66 unit tests and 27 integration tests, no failures, no skips (JUnit XML). 63 unit tests at `12fad93`.
- `IdentityDiscoveryHealthIndicatorTest` was run five more times in a row: 22 tests, all passed each time.
- `scripts/verify-backend-image.sh`: exit code 0, 26 `ok` lines.
- Not run: the Kind qualification (cluster `owl-mast-om0102` untouched) and any server-side Gateway API check. Both stay deferred.

## Spec Change Log

## Review Triage Log

## Verification

**Commands:**
- `OWLMAST_TOOLS_DIR=… scripts/verify-install-package.sh` -- expected: all deploy tests OK.
- `./gradlew build --console=plain` -- expected: BUILD SUCCESSFUL.
- `scripts/verify-backend-image.sh` -- expected: all checks ok.
