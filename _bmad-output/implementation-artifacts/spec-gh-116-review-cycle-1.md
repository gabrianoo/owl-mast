---
title: 'OM-01.02 review→fix loop, build cycle 1: resolve reviews 5865988027 (PR #109) and 5865989182 (PR #116)'
type: 'bugfix'
created: '2026-11-11'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: '24dc0d0059f18e342e1be19cb071d14599a0c9e0'
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The 2026-11-11 reviews left 27 unresolved threads on PR #109 (merged) and 18 threads plus one body finding on PR #116. Fifteen of the #116 comments say earlier fixes are missing, partial or untested.

**Approach:** On branch `t3/om-01-02-review-findings` (PR #116), fix each finding with a test that pins it, reject it with a concrete reason, or defer it when the fix needs an owner decision. Reply on every thread with the commit and resolve it; update the PR body. The owner delegated this cycle in full, so the approval checkpoint is taken as given.

## Boundaries & Constraints

**Always:** CI jobs pin `ubuntu-26.04`. Gateway API HTTPRoute stays a first-class routing option next to the optional Ingress (frozen API, not deprecated). Render/manifest support is stated separately from runtime qualification. Every chart rule has a render or negative test.

**Never:** Touch the main checkout. Delete or mutate the Kind cluster `owl-mast-om0102` or its volumes. Merge the PR or post an APPROVE review. Rebase or merge `main` unless CI or a conflict requires it.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| JVM option injection | `backend.javaToolOptions=-Dowlmast.identity.issuer-uri=…` or `-javaagent:…` | render refused | schema and template name the value |
| API prefix | `routing.apiPathPrefix=/api/v1` | render refused | message names the value |
| TLS entry | `routing.ingress.tls[0]` without `secretName` | render refused | schema |
| Server-verifying sslMode | `sslMode=verify-ca` or `verify-full` | render refused until a CA mount exists | message names the deferral |
| Hook cleanup | provisioning hook rendered | delete policy `before-hook-creation,hook-succeeded` on Job and ConfigMap | N/A |
| Gateway hostnames | gateway enabled, `hostnames` empty | render refused unless `allowAllListenerHostnames=true` | message names both values |
| Actuator exposure | any routing enabled, defaults | no `/actuator` rule | rendered only with `routing.exposeActuator=true` |
| Readiness probe | defaults | `timeoutSeconds` greater than the indicator's discovery timeout | N/A |
| Issuer comparison | configured `https://idp/`, published `https://idp` (or reverse) | readiness DOWN | N/A |
| Init checksum | `commonLabels` or chart labels change | `checksum/init` unchanged | N/A |

</frozen-after-approval>

## Code Map

- `deploy/helm/owl-mast/templates/_helpers.tpl` -- `owl-mast.validate*`, `suffixedName`; all render-time rules.
- `deploy/helm/owl-mast/values.schema.json`, `values.yaml` -- typed values and defaults.
- `deploy/helm/owl-mast/templates/{httproute,ingress,backend-deployment,postgresql-*,keycloak-deployment,NOTES.txt}` -- rendered objects.
- `deploy/tests/test_chart_render.py`, `test_gateway_schema.py`, `test_postgresql_init.py`, `test_qualify_script.py` -- render, negative, Docker-backed and script tests.
- `backend/src/main/java/com/aisquad/owlmast/access/adapter/identity/` -- `IdentityProperties`, `IdentityDiscoveryHealthIndicator`.
- `scripts/qualify-local-install.sh`, `scripts/verify-backend-image.sh` -- qualification and image contract.
- `docs/installation.md` -- operator contract; `deferred-work.md` -- deferrals.

## Tasks & Acceptance

**Execution:**
- [x] Chart rules, schema, templates -- every fix-first item and the remaining chart findings -- fail closed at render.
- [x] Deploy tests -- one positive or negative test per finding; template-layer Gateway checks exercised with `--skip-schema-validation`.
- [x] Backend identity -- exact issuer comparison, cached discovery result, port range, https unless `allow-insecure-issuer`.
- [x] Scripts -- atomic labelled Secret creation, `create` instead of `apply`, a real application start on a read-only root.
- [x] Docs and deferrals -- installation contract, upgrade table, qualification status, deferred-work entries.

**Acceptance Criteria:**
- Given the branch head, when `scripts/verify-install-package.sh`, `./gradlew build` and `scripts/verify-backend-image.sh` run, then all pass locally and every CI check on PR #116 is green.
- Given each of the 45 threads and the body finding, when the cycle ends, then it carries a reply naming the commit and is resolved, or is listed as deferred with its reason.

## Implementation Notes

- Scope note. The owner delegated the cycle in full, so the planning checkpoint was not held; this session is itself the implementation sub-agent, so no further sub-agent was started.
- `main` (b9a1837) was merged into the branch as `6d77f7d` before the backend change: `main` had rewritten `IdentityDiscoveryHealthIndicator` (Lombok constructor, `@NonNull`), the class this cycle must change for the exact issuer comparison and the cache, so a conflict was certain. The merge itself was clean.
- Fix commit: `c7578bb74145b63d213db349be632f33f642515e`.

Disposition (comment id → outcome). PR #116 review 5865989182, 18 threads and one body finding:

| Comment | Outcome | Where |
|---|---|---|
| 4543777441 javaToolOptions | fixed | schema allowlist and `owl-mast.validate` |
| 4543777452 apiPathPrefix | fixed | exactly `/api` |
| 4543777463 TLS secretName | fixed | schema `required`, `validateIngress` |
| 4543777472 verify-ca/verify-full | fixed, fail closed | `validateSslMode`; CA mount stays deferred |
| 4543777479 read-only proof | fixed | `verify-backend-image.sh` starts the application |
| 4543777484 hook delete policy | fixed | `before-hook-creation,hook-succeeded` |
| 4543777495 chart 0.2.0 unqualified | deferred (owner) | docs mark it pending; rerun needs an authorized run |
| 4543777500 shared external principal | fixed by documentation | AC3 section, NOTES warning |
| 4543777509 issuer port and path | fixed | chart regex, `IdentityProperties` port range |
| 4543777515 suffixedName collision | fixed | hash on truncation |
| 4543777526 https in the backend | fixed | `owlmast.identity.allow-insecure-issuer` |
| 4543777533 proxyHeaders | fixed | requires policy and proxy peer |
| 4543777539 verification record | fixed | correction in the gh-109 spec; record below |
| 4543777547 host label length | fixed | 63-character labels |
| 4543777557 existingClaim reinstall | fixed | message, docs, readiness covers Keycloak's database |
| 4543777563 second CONNECT denial | fixed | stub mode `keycloak-allowed` |
| 4543777568 gateway annotations | fixed | positive and negative test |
| 4543777575 NetworkPolicy external-bundled | fixed | test |
| body: init refusals order | fixed | `provision-keycloak.sh --preflight` |

PR #109 review 5865988027, 27 threads:

| Comment | Outcome | Where |
|---|---|---|
| 4543776272 empty hostnames | fixed | `allowAllListenerHostnames` |
| 4543776281 actuator routed | fixed | `routing.exposeActuator` |
| 4543776285 uncached readiness | fixed | 5 s cache |
| 4543776297 probe timeout | fixed | `timeoutSeconds: 5` |
| 4543776309 issuer comparison | fixed | exact equality |
| 4543776321 bundled PostgreSQL plaintext | fixed by documentation | NOTES, docs |
| 4543776333 checksum/init | fixed | data only |
| 4543776343 PostgreSQL probes | fixed | socket probes, readiness covers Keycloak |
| 4543776353 bootstrap admin | fixed | `bootstrapAdmin.enabled`; cluster check in the Kind rerun |
| 4543776357 duplicate parent | fixed | release namespace default |
| 4543776362 IP hostnames | fixed | schema and template |
| 4543776368 CEL against a real API server | deferred (owner) | needs a cluster with the CRDs |
| 4543776376 hook delete policy | fixed | as 4543777484 |
| 4543776391 backend strategy | fixed | `Recreate` |
| 4543776402 fsGroupChangePolicy | fixed | PostgreSQL pod; the Job has no fsGroup volume |
| 4543776411 template1 | fixed | revoke in both scripts |
| 4543776419 empty image tag | fixed | render refusal |
| 4543776426 service ports | fixed | schema |
| 4543776430 database name length | fixed | schema |
| 4543776435 changed name or credentials | fixed by documentation | re-provisioning procedure |
| 4543776443 realm checksum | fixed | `checksum/realm` |
| 4543776449 immutable PVC fields | documented; proposed guard rejected | false refusal with an empty `storageClass` |
| 4543776459 create-then-label | fixed | `create_labelled_secret` |
| 4543776464 replication apply | fixed | `create`, error reported |
| 4543776471 Keycloak external values | fixed | test |
| 4543776479 backendRef port | fixed | test |
| 4543776485 template-layer checks | fixed | `--skip-schema-validation` tests, port 0 |

Verification record for `c7578bb`, local, 2026-11-11:
- `scripts/verify-install-package.sh` with the qualified Helm 4.3.1 and kubectl 1.36.1: 139 tests OK, none skipped (101 at `24dc0d0`). Per module: `test_chart_render` 60, `test_gateway_schema` 7, `test_discovery_client` 7, `test_postgresql_init` 19 (Docker), `test_keycloak_readonly` 1 (Docker), `test_qualify_script` 33, `test_verify_install_package` 6, `test_api_compatibility` 6.
- `./gradlew build`: BUILD SUCCESSFUL; 54 unit tests and 27 integration tests, no failures, no skips (JUnit XML).
- `scripts/verify-backend-image.sh`: all checks ok, including the application start on the read-only root.
- CI for `c7578bb`: https://github.com/gabrianoo/owl-mast/actions/runs/43113497280 (six jobs; `package-checks` runs the Docker-backed suites).
- Not run: the Kind qualification (cluster `owl-mast-om0102` untouched), and any server-side Gateway API check. Both are deferred.

## Spec Change Log

## Review Triage Log

## Verification

**Commands:**
- `OWLMAST_HELM=… OWLMAST_KUBECTL=… scripts/verify-install-package.sh` -- expected: all deploy tests OK.
- `./gradlew build --console=plain` -- expected: BUILD SUCCESSFUL.
- `scripts/verify-backend-image.sh` -- expected: all checks ok.
