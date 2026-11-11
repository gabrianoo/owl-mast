---
title: 'OM-01.02 review→fix loop, build cycle 1: resolve reviews 5865988027 (PR #109) and 5865989182 (PR #116)'
type: 'bugfix'
created: '2026-11-11'
status: 'in-progress'
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

See the disposition table and verification record appended at the end of the cycle.

## Spec Change Log

## Review Triage Log

## Verification

**Commands:**
- `OWLMAST_HELM=… OWLMAST_KUBECTL=… scripts/verify-install-package.sh` -- expected: all deploy tests OK.
- `./gradlew build --console=plain` -- expected: BUILD SUCCESSFUL.
- `scripts/verify-backend-image.sh` -- expected: all checks ok.
