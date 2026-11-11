---
title: 'OM-01.02 review→fix loop, build cycle 2: resolve review 5866484238 (PR #116)'
type: 'bugfix'
created: '2026-11-12'
status: 'in-progress'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: '031da2cf01f65e84ee3f807d56d14fd46937bd32'
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The cycle-2 review of PR #116 at `031da2c` left 22 inline comments (16 material, 6 minor or nit; two re-raise cycle-1 threads) and five small leftovers on fixed threads. Several are upgrade or availability hazards: a renamed data claim, PostgreSQL readiness tied to Keycloak's database, and issuers that render and then crash the backend.

**Approach:** On branch `t3/om-01-02-review-findings`, fix each finding with a test that pins it, reject it with a concrete reason, or defer it only when an owner decision is needed. Reply on every thread with the commit and resolve it; update the PR body. The owner delegated this cycle in full, so the approval checkpoint is taken as given.

## Boundaries & Constraints

**Always:** CI jobs pin `ubuntu-26.04`. Gateway API HTTPRoute stays first class next to the optional Ingress (frozen API, not deprecated). Render support is stated separately from runtime qualification. Every changed chart rule has a render or negative test. The 0.1.0 data claim name stays stable.

**Never:** Touch the main checkout. Delete or run qualification against the Kind cluster `owl-mast-om0102` or its volumes. Merge the PR or post an APPROVE review. Resolve the two owner-deferred threads (`PRRT_kwDOVjxExc62YN_x`, `PRRT_kwDOVjxExc62YN0L`).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| PostgreSQL readiness | identity bundle on, Keycloak's database missing | PostgreSQL Ready; only Keycloak is unready | N/A |
| Data claim name | fullname of 48–52 characters | claim is `<fullname>-postgresql-data`, as in 0.1.0 | N/A |
| Issuer host | `https://idp.123/…`, `https://1.2.3.999/…`, `https://idp.example.1/…`, `https://a.b-c.9z/…` | render refused | message names the value |
| Issuer parity | every sample the chart accepts | `IdentityProperties` accepts it | shared sample file |
| proxyHeaders peer | `extraFrom` of `{}`, `{namespaceSelector: {}}`, `{podSelector: {}}`, `ipBlock` `/0` | render refused | message names the entry |
| `--reuse-values` from 0.1.0 | 0.1.0 values without the 0.2.0 keys | renders with the 0.2.0 defaults | N/A |
| Ingress host | `10.0.0.1` as `host` or in `tls[].hosts` | render refused | schema and template |
| `extraEnv` override | `JAVA_TOOL_OPTIONS` with `--skip-schema-validation` | render refused | template names the entry |
| `commonLabels` edit | label added | PostgreSQL `spec.template` unchanged | N/A |
| Probe timeouts | defaults | PostgreSQL exec probes carry `timeoutSeconds` | N/A |

</frozen-after-approval>

## Code Map

- `deploy/helm/owl-mast/templates/_helpers.tpl` -- `owl-mast.validate*`, `suffixedName`, `postgresql.dataClaim`; all render-time rules.
- `deploy/helm/owl-mast/values.schema.json`, `values.yaml` -- typed values and defaults; 0.2.0-only keys must not be `required`.
- `deploy/helm/owl-mast/templates/{postgresql-deployment,keycloak-deployment,backend-deployment,frontend-deployment,httproute,ingress,networkpolicy,NOTES.txt}` -- rendered objects; new keys read with defaults.
- `deploy/tests/test_chart_render.py`, `test_postgresql_init.py`, `test_qualify_script.py` -- render, negative, Docker-backed and script tests; `deploy/tests/data/values-0.1.0.yaml` is the 0.1.0 values fixture.
- `backend/src/main/java/com/aisquad/owlmast/access/adapter/identity/` -- `IdentityProperties`, `IdentityDiscoveryHealthIndicator`; `backend/src/test/resources/identity/issuer-samples.txt` is shared with the chart test.
- `scripts/qualify-local-install.sh`, `scripts/verify-backend-image.sh`, `.github/workflows/ci.yml` -- secret creation, image contract, step name.
- `docs/installation.md`, `deferred-work.md`, `frontend/nginx/default.conf.template` -- operator contract, deferrals, stale comment.

## Tasks & Acceptance

**Execution:**
- [ ] `deploy/helm/owl-mast/` -- fix-first items 1–6, then the remaining chart findings and leftovers -- fail closed at render, stable names, upgrade-safe defaults.
- [ ] `deploy/tests/` -- one positive or negative test per finding, including the four untested behaviours (comments 19–22) -- pins each rule.
- [ ] `backend/src/` -- published issuer in the DOWN detail, production-constructor cache test, issuer sample parity -- backend and chart agree.
- [ ] `scripts/`, `.github/workflows/ci.yml` -- password out of argv, read-only smoke claims what it proves.
- [ ] `docs/installation.md`, `deferred-work.md` -- names, upgrade notes, deferral of bundled PostgreSQL TLS.

**Acceptance Criteria:**
- Given the branch head, when `scripts/verify-install-package.sh`, `./gradlew build` and `scripts/verify-backend-image.sh` run, then all pass locally and every CI check on PR #116 is green.
- Given each of the 22 threads, when the cycle ends, then it carries a reply naming the commit and is resolved, or is listed as deferred with its reason; the two re-raised cycle-1 threads carry a reply too.

## Implementation Notes

## Spec Change Log

## Review Triage Log

## Verification

**Commands:**
- `OWLMAST_TOOLS_DIR=… scripts/verify-install-package.sh` -- expected: all deploy tests OK.
- `./gradlew build --console=plain` -- expected: BUILD SUCCESSFUL.
- `scripts/verify-backend-image.sh` -- expected: all checks ok.
