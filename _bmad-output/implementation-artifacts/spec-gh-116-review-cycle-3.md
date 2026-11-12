---
title: 'OM-01.02 review→fix loop, build cycle 3: resolve review 5866834124 (PR #116)'
type: 'bugfix'
created: '2026-11-12'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: 'f52b3defee57ef7f320ec3f398720463722f38de'
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The cycle-3 review of PR #116 at `f52b3de` left 20 inline comments (2 material, 18 minor or nit). The first material one is a regression from cycle 2: the PostgreSQL pods lost the run label, so the qualification script's ownership proof refuses them and its stub world hides that.

**Approach:** On branch `t3/om-01-02-review-findings`, fix each finding with a test that pins it, or reject it with a concrete reason. Reply on every thread with the commit and resolve it; update the PR body. The owner delegated this cycle in full, so the approval checkpoint is taken as given.

## Boundaries & Constraints

**Always:** CI jobs pin `ubuntu-26.04`. Gateway API HTTPRoute stays first class next to the optional Ingress (frozen API, not deprecated). Render support is stated separately from runtime qualification. A `commonLabels` edit never recreates PostgreSQL.

**Never:** Touch the main checkout. Delete or run qualification against the Kind cluster `owl-mast-om0102`. Merge the PR or post an APPROVE review. Resolve the two owner-deferred threads (`PRRT_kwDOVjxExc62YN_x`, `PRRT_kwDOVjxExc62YN0L`).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| PostgreSQL ownership | pod and ReplicaSet without the run label, Deployment owned, UIDs chained | chain proven; persistence step deletes the proven pod | a foreign label on the pod or ReplicaSet still refuses |
| Stub world | labels the chart renders for each component | stub answers the same labels | a chart change that drops a label fails a test |
| Issuer mismatch log | published issuer with CR/LF | one WARN with the escaped value; no forged line | repeated only when the published value changes |
| Readiness cache | discovery takes time, period just above `CACHE_TTL` | the next probe starts a new discovery | N/A |
| proxyHeaders peer | `Exists`-only selector; `0.0.0.0/1` + `128.0.0.0/1` | render refused | message names the entry |
| `bootstrapAdmin.enabled` | string `False` with `--skip-schema-validation` | render refused | message names the value |
| `extraEnv` | `LD_AUDIT` or any `LD_*` | render refused | schema and template |
| Frontend probes | `timeoutSeconds` set | rendered on that probe | N/A |
| Ingress host | `999.1.1.1`, `256.0.0.1` | rendered (not an IP address) | N/A |
| `javaToolOptions` | `-XX:ParallelGCThreads=1.5g`, `-XX:MaxRAMPercentage=75m` | render refused | schema and template |

</frozen-after-approval>

## Code Map

- `scripts/qualify-local-install.sh` -- `verified_pods` (pod → ReplicaSet → Deployment by UID), `preflight_release`, `step_persistence`, `step_inventory`.
- `deploy/tests/test_qualify_script.py` -- `KUBECTL_STUB` pod and ReplicaSet answers; the label each component carries must come from the rendered chart.
- `deploy/helm/owl-mast/templates/_helpers.tpl` -- `owl-mast.validate` (proxyHeaders peers, extraEnv, readiness period), `validateIngress`, `validateSslMode`, `javaToolOptionsPattern`, `keycloak.bootstrapAdminEnabled`.
- `deploy/helm/owl-mast/values.schema.json`, `values.yaml` -- the same rules in the schema; the two patterns must stay identical to the helpers.
- `deploy/helm/owl-mast/templates/{frontend-deployment,keycloak-deployment,NOTES.txt}` -- probe timeouts, external-issuer note.
- `deploy/tests/test_chart_render.py` -- `ReviewCycle2Test` is the model; add `ReviewCycle3Test`. `deploy/tests/data/values-0.1.0.yaml` is the `--reuse-values` fixture.
- `backend/src/main/java/com/aisquad/owlmast/access/adapter/identity/IdentityDiscoveryHealthIndicator.java` and its test; `IdentityPropertiesTest`; `backend/src/test/resources/identity/issuer-samples.txt` (shared with the chart test).
- `scripts/verify-backend-image.sh`, `.github/workflows/ci.yml` -- smoke run env, checks and header.
- `docs/installation.md` -- `<fullname>` definition, upgrade notes.

## Tasks & Acceptance

**Execution:**
- [x] `scripts/qualify-local-install.sh`, `deploy/tests/test_qualify_script.py` -- prove PostgreSQL ownership through the owned Deployment; stub labels follow the rendered chart.
- [x] `backend/src/` -- test the mismatch warning and its escaping; warn once per published value; cache age counted from the request.
- [x] `deploy/helm/owl-mast/`, `deploy/tests/test_chart_render.py` -- the chart findings, each with a positive or negative render test.
- [x] `scripts/verify-backend-image.sh`, `.github/workflows/ci.yml` -- chart-rendered env, positive binding marker, accurate header.
- [x] `docs/installation.md` -- `<fullname>` with `nameOverride` and shortened names.

**Acceptance Criteria:**
- Given the branch head, when `scripts/verify-install-package.sh`, `./gradlew build` and `scripts/verify-backend-image.sh` run, then all pass locally and every CI check on PR #116 is green.
- Given each of the 20 threads, when the cycle ends, then it carries a reply naming the commit and is resolved, or is listed as rejected or deferred with its reason.

## Implementation Notes

- Scope note. The owner delegated the cycle in full, so the planning checkpoint was not held. This session is itself the implementation sub-agent of the owner's review→fix loop, so it started no further sub-agents: the implementation was done directly, and the independent review of this change is the loop's next review cycle, not an in-session reviewer layer. The diff was self-reviewed.
- Fix commit: `12fad937587c83508b053e8458308ce5552e854a`.
- Mutation checks: 22 single changes (18 in the chart, the scripts and the stub; 4 in the health indicator) were applied one at a time, and each time the test written for the finding failed.
- JVM check for comment 4544473258, on the qualified Temurin 27.0.1: the percentage options refuse a size suffix and the size options refuse a decimal ("Improperly specified VM option"). `-XX:ActiveProcessorCount=2k` starts, so the finding's claim for count options does not hold; the chart refuses a suffix there anyway.

Disposition (comment id → outcome). PR #116 review 5866834124, 20 threads, all fixed, none rejected, none deferred:

| Comment | Thread | Outcome | Where |
|---|---|---|---|
| 4544473145 PostgreSQL pods without the run label (material) | `PRRT_kwDOVjxExc62Zzm8` | fixed | `verified_pods` proves the pod through the owned Deployment; stub labels come from a render of the chart; three new script tests |
| 4544473154 mismatch warning untested (material) | `PRRT_kwDOVjxExc62ZznB` | fixed | output capture in `IdentityDiscoveryHealthIndicatorTest` |
| 4544473160 cache timer starts at the answer | `PRRT_kwDOVjxExc62ZznE` | fixed | interval counted from the request start; slow-provider tests; wording in the chart and docs |
| 4544473165 proxyHeaders peers that admit everything | `PRRT_kwDOVjxExc62ZznJ` | fixed | `matchLabels` or an `In` term required; minimum prefix /8 and /32 |
| 4544473172 SSL-mode refusal needs the schema skipped | `PRRT_kwDOVjxExc62ZznN` | fixed | both modes back in the enum; the template explains |
| 4544473182 smoke env is not the chart's | `PRRT_kwDOVjxExc62ZznT` | fixed | chart-rendered names and URL forms; http start with the opt-in; render test compares |
| 4544473187 negative-only binding check, fixed count | `PRRT_kwDOVjxExc62ZznV` | fixed | start-up log line as marker, control start, count pattern |
| 4544473197 header overclaims | `PRRT_kwDOVjxExc62Zznd` | fixed | header, CI step name, closing line, docs |
| 4544473205 warning on every refresh | `PRRT_kwDOVjxExc62Zznh` | fixed | once per published value |
| 4544473213 no http sample | `PRRT_kwDOVjxExc62Zznm` | fixed | `accept-insecure`, `refuse-insecure` kinds on both sides |
| 4544473219 reasons unchecked, obscure failure | `PRRT_kwDOVjxExc62Zznr` | fixed | `refuse:<reason>`; "malformed sample line" in both readers |
| 4544473225 `<fullname>` definition | `PRRT_kwDOVjxExc62Zznw` | fixed | docs; NOTES name the Deployment and the claim |
| 4544473231 `bootstrapAdmin.enabled` strings | `PRRT_kwDOVjxExc62Zzn0` | fixed | helper fails unless `true` or `false` |
| 4544473238 `LD_AUDIT` | `PRRT_kwDOVjxExc62Zzn5` | fixed | every `LD_*` refused, template and schema |
| 4544473245 frontend `timeoutSeconds` dropped | `PRRT_kwDOVjxExc62Zzn_` | fixed | rendered on both probes |
| 4544473250 Ingress IP pattern | `PRRT_kwDOVjxExc62ZzoD` | fixed | `owl-mast.ipv4Pattern`, octets 0–255, also for Gateway hostnames |
| 4544473258 `javaToolOptions` value forms | `PRRT_kwDOVjxExc62ZzoJ` | fixed | sizes, percentages, counts |
| 4544473263 Keycloak startup and liveness timeouts | `PRRT_kwDOVjxExc62ZzoN` | fixed | test |
| 4544473269 external-issuer NOTES | `PRRT_kwDOVjxExc62ZzoQ` | fixed | test |
| 4544473275 `--reuse-values` fallback defaults | `PRRT_kwDOVjxExc62ZzoU` | fixed | test |

New owner decisions, D21–D28 in the PR body:

- D21: the qualification script proves PostgreSQL pods through the Deployment; the pod template stays without a run label.
- D22: the readiness cache interval is counted from the request start; the chart rule stays "greater than 5".
- D23: proxyHeaders peers need `matchLabels` or an `In` term; `ipBlock` needs at least /8 (IPv4) or /32 (IPv6).
- D24: `verify-ca` and `verify-full` are in the schema enum again. This reverses the schema half of the cycle-2 fix for 4544181137.
- D25: `backend.extraEnv` refuses every `LD_*` name.
- D26: the issuer-mismatch warning is logged once per published value.
- D27: count options in `backend.javaToolOptions` take a whole number only, which is stricter than the JVM.
- D28: the backend logs the configured issuer at INFO on every start.

Left open on purpose, owner-deferred from cycle 1: `PRRT_kwDOVjxExc62YN_x` (Kind rerun for chart 0.2.0) and `PRRT_kwDOVjxExc62YN0L` (Gateway CEL rules against a real API server).

Verification record for `12fad93`, local, 2026-11-12:
- `scripts/verify-install-package.sh` with a freshly downloaded, checksum-verified Helm 4.3.1 and kubectl 1.36.1: 178 tests OK, none skipped (160 at `9ca009b`). Per module: `test_chart_render` 94, `test_gateway_schema` 7, `test_discovery_client` 7, `test_postgresql_init` 19 (Docker), `test_keycloak_readonly` 1 (Docker), `test_qualify_script` 38, `test_verify_install_package` 6, `test_api_compatibility` 6. After that run one line of one render test changed (a ninth malformed sample line); that test was rerun alone and passed.
- `./gradlew build`: BUILD SUCCESSFUL; 63 unit tests and 27 integration tests, no failures, no skips (JUnit XML).
- `scripts/verify-backend-image.sh`: all 25 checks ok, with three application starts.
- Not run: the Kind qualification (cluster `owl-mast-om0102` untouched), so the corrected `qualify-local-install.sh` is proven against the stub world only. No server-side Gateway API check was run. Both stay deferred.

## Spec Change Log

## Review Triage Log

## Verification

**Commands:**
- `OWLMAST_TOOLS_DIR=… scripts/verify-install-package.sh` -- expected: all deploy tests OK.
- `./gradlew build --console=plain` -- expected: BUILD SUCCESSFUL.
- `scripts/verify-backend-image.sh` -- expected: all checks ok.
