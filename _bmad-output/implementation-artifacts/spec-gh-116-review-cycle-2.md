---
title: 'OM-01.02 review→fix loop, build cycle 2: resolve review 5866484238 (PR #116)'
type: 'bugfix'
created: '2026-11-12'
status: 'in-review'
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
- [x] `deploy/helm/owl-mast/` -- fix-first items 1–6, then the remaining chart findings and leftovers -- fail closed at render, stable names, upgrade-safe defaults.
- [x] `deploy/tests/` -- one positive or negative test per finding, including the four untested behaviours (comments 19–22) -- pins each rule.
- [x] `backend/src/` -- published issuer in the DOWN detail, production-constructor cache test, issuer sample parity -- backend and chart agree.
- [x] `scripts/`, `.github/workflows/ci.yml` -- password out of argv, read-only smoke claims what it proves.
- [x] `docs/installation.md`, `deferred-work.md` -- names, upgrade notes, deferral of bundled PostgreSQL TLS.

**Acceptance Criteria:**
- Given the branch head, when `scripts/verify-install-package.sh`, `./gradlew build` and `scripts/verify-backend-image.sh` run, then all pass locally and every CI check on PR #116 is green.
- Given each of the 22 threads, when the cycle ends, then it carries a reply naming the commit and is resolved, or is listed as deferred with its reason; the two re-raised cycle-1 threads carry a reply too.

## Implementation Notes

- Scope note. The owner delegated the cycle in full, so the planning checkpoint was not held. This session is itself the implementation sub-agent of the owner's review→fix loop, so it started no further sub-agents: the implementation was done directly, and the independent review of this change is the loop's next review cycle, not an in-session reviewer layer. The diff was self-reviewed, and eleven chart fixes and the cache fix were mutation-checked (each test failed with its fix reverted).
- Fix commit: `9ca009b9404b110d062cfc008a6be9457233c225`.
- D13 of cycle 1 (PostgreSQL not Ready until Keycloak's database exists) is reversed by comment 4544181074, which the owner listed first. New decisions D14–D20 are in the PR body.
- The issuer host rule was also fuzzed outside CI: 3,000,000 random hosts against `java.net.URI` on JDK 27.0.1. The chart accepted no host the backend refuses; the backend-only cases were IPv4 addresses with a leading zero.

Disposition (comment id → outcome). PR #116 review 5866484238, 22 threads:

| Comment | Thread | Outcome | Where |
|---|---|---|---|
| 4544181050 issuer host (re-raised `PRRT_kwDOVjxExc62YN_3`) | `PRRT_kwDOVjxExc62ZI7d` | fixed | host rule in `owl-mast.validate`; `issuer-samples.txt` read by the chart test and `IdentityPropertiesTest` |
| 4544181064 commonLabels (re-raised `PRRT_kwDOVjxExc62YNzu`) | `PRRT_kwDOVjxExc62ZI7j` | fixed | no `commonLabels` on the PostgreSQL pod template; whole `spec.template` compared |
| 4544181069 data claim renamed | `PRRT_kwDOVjxExc62ZI7n` | fixed | `owl-mast.postgresql.dataClaim` is `<postgresql fullname>-data` again |
| 4544181074 readiness and Keycloak's database | `PRRT_kwDOVjxExc62ZI7r` | fixed | readiness on the application database only; render and Docker tests |
| 4544181081 exec probe timeout | `PRRT_kwDOVjxExc62ZI7v` | fixed | `timeoutSeconds: 5` on the PostgreSQL probes |
| 4544181085 proxyHeaders peer | `PRRT_kwDOVjxExc62ZI7w` | fixed | empty peer, empty selector and `/0` block refused |
| 4544181089 extraEnv denylist | `PRRT_kwDOVjxExc62ZI7z` | fixed | repeated in `owl-mast.validate` |
| 4544181092 `-XX` allow-list (minor) | `PRRT_kwDOVjxExc62ZI71` | fixed | named allow-list, one expression for schema and template |
| 4544181102 NOTES and `require` | `PRRT_kwDOVjxExc62ZI74` | fixed | NOTES and docs wording |
| 4544181109 password in argv (minor) | `PRRT_kwDOVjxExc62ZI7-` | fixed | stdin, `--from-file=password=/dev/stdin` |
| 4544181114 CACHE_TTL and period | `PRRT_kwDOVjxExc62ZI8B` | fixed | period of 5 or less refused; render test reads the constant |
| 4544181120 `--reuse-values` | `PRRT_kwDOVjxExc62ZI8E` | fixed | new keys defaulted, not required; 0.1.0 values fixture |
| 4544181129 read-only smoke claim | `PRRT_kwDOVjxExc62ZI8K` | fixed | start reaches the first database connection; header, step name and docs reworded |
| 4544181137 schema sslMode (minor) | `PRRT_kwDOVjxExc62ZI8O` | fixed | enum without `verify-ca`/`verify-full` |
| 4544181145 Ingress IPv4 host | `PRRT_kwDOVjxExc62ZI8V` | fixed | schema and `validateIngress` |
| 4544181156 no admin on install (minor) | `PRRT_kwDOVjxExc62ZI8c` | fixed by documentation and a NOTES warning | a refusal would break reinstalls on a retained volume |
| 4544181161 dead branch (nit) | `PRRT_kwDOVjxExc62ZI8g` | fixed | schema allows an empty value |
| 4544181170 trailing slash on upgrade (minor) | `PRRT_kwDOVjxExc62ZI8n` | fixed | `publishedIssuer` detail and warning; upgrade notes; NOTES |
| 4544181182 production constructor cache | `PRRT_kwDOVjxExc62ZI8r` | fixed | two tests |
| 4544181189 shared-server warning rules | `PRRT_kwDOVjxExc62ZI8x` | fixed | test |
| 4544181191 retired bootstrap Secret | `PRRT_kwDOVjxExc62ZI8y` | fixed | test |
| 4544181197 startup probe timeout | `PRRT_kwDOVjxExc62ZI83` | fixed | test |

Leftovers named in the review body, all fixed:

| Leftover | Where |
|---|---|
| `<release>-postgresql` in the refusal and docs | the refusal prints the real Deployment name; docs use `<fullname>` and define it |
| `frontend/nginx/default.conf.template` says the gateway routes `/actuator` | comment corrected |
| a whitespace-only `backend.image.tag` renders | tag pattern in the schema, `owl-mast.validateImageTag` |
| TLS for the bundled PostgreSQL untracked | new entry in `deferred-work.md` |
| a chosen short name can collide with a hashed long one | documented as a limit of the hash (helper comment, docs); it cannot be closed, because a 6-character hash can be matched on purpose |

Left open on purpose, owner-deferred from cycle 1: `PRRT_kwDOVjxExc62YN_x` (Kind rerun for chart 0.2.0) and `PRRT_kwDOVjxExc62YN0L` (Gateway CEL rules against a real API server).

Verification record for `9ca009b`, local, 2026-11-12:
- `scripts/verify-install-package.sh` with the qualified Helm 4.3.1 and kubectl 1.36.1: 160 tests OK, none skipped (139 at `c7578bb`). Per module: `test_chart_render` 80, `test_gateway_schema` 7, `test_discovery_client` 7, `test_postgresql_init` 19 (Docker), `test_keycloak_readonly` 1 (Docker), `test_qualify_script` 34, `test_verify_install_package` 6, `test_api_compatibility` 6. The full run preceded one last change to `scripts/qualify-local-install.sh` (process substitution instead of a pipeline); `test_qualify_script` was rerun after it, 34 OK.
- `./gradlew build`: BUILD SUCCESSFUL; 58 unit tests and 27 integration tests, no failures, no skips (JUnit XML).
- `scripts/verify-backend-image.sh`: all 16 checks ok; the application start reaches the first database connection on the read-only root.
- Not run: the Kind qualification (cluster `owl-mast-om0102` untouched) and any server-side Gateway API check. Both stay deferred. The `--reuse-values` upgrade is render support only; it was not run on a cluster.

## Spec Change Log

## Review Triage Log

## Verification

**Commands:**
- `OWLMAST_TOOLS_DIR=… scripts/verify-install-package.sh` -- expected: all deploy tests OK.
- `./gradlew build --console=plain` -- expected: BUILD SUCCESSFUL.
- `scripts/verify-backend-image.sh` -- expected: all checks ok.
