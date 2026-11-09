---
title: 'Resolve the PR #109 post-merge review findings (OM-01.02 install package)'
type: 'bugfix'
created: '2026-11-09'
status: 'done'
baseline_commit: '137e084625adb328a3248399a428d850c9ef4fbd'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/docs/installation.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-om-01-02-install-optional-state-and-identity-dependencies.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The post-merge review of PR #109 (review 5827094734, 26 inline comments plus 1 in the body, 31 findings) found fail-open validation, weak transport defaults, missing isolation, hardening gaps, and verification gaps in the OM-01.02 Helm chart, its qualification script, and CI. All of them are still open on `main` at 137e084.

**Approach:** Resolve every finding, one at a time, in one follow-up PR from `main`. Each fix gets a negative or regression test. Afterwards, reply to and resolve every PR #109 review thread with a link to the fix.

Owner instruction (2026-11-09): "resolve all the code review findings one by one, push to a new PR, make sure it is green, and don't stop until you finish". The checkpoint approval is taken as given. The design choices below were made by the agent under that instruction, and the PR lists them for owner acceptance.

**Decisions (agent, under the owner's no-stop instruction):**
- D1 Insecure transport needs an explicit opt-in. `identity.external.issuerUri` must be `https://` with a host, and plaintext requires `identity.external.allowInsecureIssuer=true`. The external DB `sslMode` defaults change from `prefer` to `require` (`verify-*` needs a CA trust the chart does not mount yet). `disable`, `allow` and `prefer` need `database.external.allowInsecureTransport=true` (and the Keycloak equivalent). The Kind qualification script passes these opt-ins.
- D2 Routing prefixes are pinned to what the artifacts serve. The api prefix is `/api` or `/api/...`, the actuator prefix is `/actuator` or `/actuator/...`, and the frontend prefix is `/`. Pinning makes the prefixes disjoint by construction, so no rewrite filters are needed.
- D3 The `NetworkPolicy` is default-on (`networkPolicy.enabled=true`) and ingress-only: PostgreSQL :5432 from backend, Keycloak and the provisioning Job, and Keycloak :8080 from the backend, plus optional extra peers. Node-originated traffic (probes, API-server proxy on single-node Kind) stays allowed by Kubernetes semantics. The policies are verified at manifest level only.
- D4 The backend digest stays optional, because no registry image exists yet. The comment is corrected, and NOTES warns when the image is referenced by a mutable tag.
- D5 Bundled Keycloak with `importRealm=false` requires `identity.keycloak.realmManagedByOperator=true`.
- D6 The stale PR #109 test counts are corrected in the OM-01.02 story record. The merged PR body is not edited.

## Boundaries & Constraints

**Always:** Fail closed at render time, naming the value. Keep the four combinations and the examples rendering. Keep CI jobs on `ubuntu-26.04`. Keep Gateway API HTTPRoute first-class next to the optional Ingress. Keep the executable bit on new scripts (`git update-index --chmod=+x`). Keep secrets out of values, tests and evidence.

**Never:** Touch the retained Kind cluster `owl-mast-om0102` or its volumes. Edit the merged PR #109 body. Add credentials to examples. Weaken an existing test to make it pass.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Plain issuer | `issuerUri=http://idp/realms/x` | render fails | names `allowInsecureIssuer` |
| Plain issuer opted in | the above plus `allowInsecureIssuer=true` | renders | N/A |
| Weak DB TLS | external, `sslMode=prefer` | render fails | names `allowInsecureTransport` |
| Shared secrets | `database.existingSecret == postgresql.adminExistingSecret` | render fails | names both keys |
| Same DB name on a shared server | `identity.keycloak.database.name == database.name` | render fails | N/A |
| Runtime collision | app username == admin username, or the Keycloak role is privileged | init or provisioning script exits non-zero before it creates anything | message names the collision |
| Env override | `extraEnv` name `OWLMAST_IDENTITY_ISSUER_URI` | schema refusal | N/A |
| Unserved prefix | `apiPathPrefix=/v1`, `frontendPathPrefix=/ui` | render fails | N/A |
| Gateway without CRD | gateway enabled, no `--api-versions` capability | render fails | names the capability |
| Bad Ingress host/TLS | `host=https://x/`, or TLS hosts do not cover the host | render fails | N/A |
| Hook on install | `provisionKeycloakDatabase=true` on install | render fails | N/A |
| Hook on an absent service | Job runs where the PostgreSQL Service does not resolve | Job fails immediately; the whole Job is bounded by `activeDeadlineSeconds` below Helm's 5m | clear log line |
| Long release name | release of 40 characters | every generated name is at most 63 characters, and names stay distinct | N/A |
| Reserved labels | `commonLabels` key `app.kubernetes.io/name` | schema refusal | N/A |
| Init rerun | init script run twice | second run is a no-op | N/A |
| Bad external host | `host=pg:5432/x?sslmode=disable` | schema refusal | N/A |
| Issuer with query | `https://idp/realms/x?a=b` | backend startup fails | names the property |
| Bundled realm without import | `importRealm=false` | render fails unless D5 is acknowledged | N/A |

</frozen-after-approval>

## Code Map

- `deploy/helm/owl-mast/templates/_helpers.tpl` -- `owl-mast.validate` (:86-147) and the name helpers (:1-49). The validation and name-truncation fixes go here.
- `deploy/helm/owl-mast/values.yaml`, `values.schema.json` -- new opt-in values; sslMode default; patterns for extraEnv, commonLabels, hosts, ingress, tls and annotations.
- `templates/{httproute,ingress}.yaml` -- capability guard; Ingress host and TLS.
- `templates/keycloak-deployment.yaml` -- proxy headers value; read-only root (emptyDirs at `/opt/keycloak/data`, `/opt/keycloak/lib/quarkus`, `/tmp`); realm acknowledgement.
- `templates/frontend-deployment.yaml` -- UID/GID 101 (the nginx-unprivileged image), read-only root (emptyDirs at `/tmp` and `/etc/nginx/conf.d`), liveness probe.
- `templates/postgresql-init-configmap.yaml` -- idempotent init SQL (`\gexec`); refusals for username collisions and privileged roles; provisioning-script service-resolution check and shorter wait.
- `templates/postgresql-provision-keycloak-job.yaml` -- `IsInstall` guard (via `validate`); `activeDeadlineSeconds`; `backoffLimit`.
- New `templates/networkpolicy.yaml`; `NOTES.txt` (mutable-tag warning).
- `backend/.../identity/IdentityProperties.java` and its test -- reject a query or fragment.
- `scripts/qualify-local-install.sh` -- :520-521 `|| return 1`; :446-461 Running-pod selection and empty-`imageID` failure; D1 opt-ins on every http issuer and `sslMode=disable` install.
- `scripts/verify-install-package.sh` -- re-verify cached tools; fail on non-linux-amd64.
- New `scripts/verify-backend-image.sh` plus a CI `build` step -- docker build plus a smoke check (UID 10001, `java -version`, jar present).
- `deploy/tests/test_chart_render.py`, `test_gateway_schema.py` (helper gains `--api-versions`; the hook renders gain `--is-upgrade`), `test_postgresql_init.py`, `test_qualify_script.py` -- new negative and regression tests.
- `docs/installation.md`, `examples/external-external.yaml` (sslMode `require`), and the OM-01.02 story record (counts).

## Tasks & Acceptance

**Execution:**
- [x] Chart: helpers, values, schema and templates for every finding (D1-D5), following the Code Map.
- [x] Scripts: qualification fixes and opt-ins; tool verification; backend image check plus the CI step.
- [x] Backend: issuer query/fragment rejection plus tests.
- [x] Tests: one negative or regression test per matrix row, plus the existingClaim render, actuator/frontend PathPrefix refusals, the env-name contract (application.yaml `${OWLMAST_*}` ↔ backend env across the four combinations), and `check_shared_postgres` under `||`.
- [x] Docs, examples and story record updated; a reply on every PR #109 thread, each resolved.

**Acceptance Criteria:**
- Given the follow-up PR, when CI runs, then every job is green, including the new backend image check.
- Given each of the 27 PR #109 review comments, when the PR is opened, then each has a reply naming the fix commit and test (or the recorded decision) and is resolved.

## Implementation Notes

- Orchestrator, after round-1 patches (2026-11-09): disposable Kind cluster `owl-mast-gh109` (kindest/node v1.36.4, kindnet) — bundled-bundled + frontend install ready; NetworkPolicy denial/admission probes as recorded in the triage log; first-enable hook under the policy succeeded; Keycloak seed init container defect found and fixed (R1-K). D3's "manifest level only" is superseded by this runtime evidence for kindnet; the owner-run `qualify-local-install.sh` has not been rerun. Cluster deleted afterwards; `owl-mast-om0102` untouched.

- 2026-11-09, worktree `om0102-review` (branch `t3/om-01-02-review-findings`, base 137e084). Code, tests and docs done; nothing committed or pushed (per the Verification instruction), so the follow-up PR, its CI run and the replies/resolution of the 27 PR #109 threads are still open. `scripts/verify-backend-image.sh` is staged with mode 100755 so the executable bit survives `core.fileMode=false`.
- Finding → fix map (review 5827094734). 4513680364 issuer https/opt-in (D1, `owl-mast.validate`); 4513680372 sslMode `require` default + `allowInsecureTransport` (D1, `owl-mast.validateSslMode`); 4513680380 distinct Secrets and Keycloak database name (render) plus username/privileged-role refusals (init and provisioning scripts); 4513680387 `extraEnv` name schema; 4513680398/4513680403 pinned prefixes (D2); 4513680409 actuator/frontend PathPrefix refusals; 4513680418 HTTPRoute capability; 4513680427 Ingress host/TLS/annotations; 4513680435 `KC_PROXY_HEADERS` opt-in (`identity.keycloak.proxyHeaders`); 4513680443 `IsInstall` refusal, `getent` fail-fast, 20×(3+5)s wait, `activeDeadlineSeconds: 240`, `backoffLimit: 0`, `restartPolicy: Never`; 4513680449 NetworkPolicy (D3); 4513680461 Keycloak/frontend read-only root, frontend UID/GID 101 and liveness; 4513680475 values comment and NOTES mutable-tag warning (D4); 4513680479 `owl-mast.suffixedName`; 4513680496 `commonLabels` propertyNames; 4513680506 idempotent init (`\gexec`) and recovery doc; 4513680517 `dnsHost` pattern; 4513680527 `IdentityProperties` query/fragment; 4513680539 `|| return 1`; 4513680551 Running non-terminating pod, non-empty `imageID`, exact digest match; 4513680560 cached-tool re-verification and platform guard; 4513680571 `realmManagedByOperator` (D5); 4513680579 existingClaim render test; 4513680598 `scripts/verify-backend-image.sh` + CI `build` step; 4513680608 env-name contract test; body finding: counts corrected in the OM-01.02 story record (D6).
- Deviation from the Code Map, found by the Keycloak read-only smoke: an emptyDir at `/opt/keycloak/lib/quarkus` hides the image's build output (`quarkus-application.dat`), and Keycloak 26.8.2 then exits with `NoSuchFileException`. The Deployment therefore gains an init container `seed-quarkus-build` (same image, read-only root, no capabilities) that copies `/opt/keycloak/lib/quarkus/.` into the emptyDir; Keycloak re-augments there at start. Smoke (`docker run --read-only`, UID 1000, cap-drop ALL, tmpfs at `/tmp` and `/opt/keycloak/data`, the seeded volume at `lib/quarkus`, realm import bind-mounted, disposable pinned PostgreSQL): `/health/ready` 200 UP and discovery `issuer` = configured hostname; without seeding: exit with the missing-file error.
- Design refinement of D3, found while checking the first-enable flow: the pre-upgrade provisioning hook runs under the PostgreSQL policy rendered before the upgrade, so with identity previously disabled an enforcing CNI would have blocked it. The PostgreSQL policy always admits this release's Keycloak and provisioning pods (release-scoped selectors, matching nothing until those pods exist).
- Additional regression checks: `scripts/verify-frontend-artifact.sh` reruns the image as 101:101 on a read-only root with tmpfs at the chart's emptyDir paths; `scripts/verify-install-package.sh` gains `OWLMAST_VERIFY_TOOLS_ONLY=1` for `deploy/tests/test_verify_install_package.py`; the qualification script's preflight enumerates the two NetworkPolicies.
- Verification (local): `scripts/verify-install-package.sh` with the qualified tools 96 tests OK (baseline 63), and again in CI mode (no `OWLMAST_HELM`/`OWLMAST_KUBECTL`, cached archive plus a stale helm binary that was replaced); the new chart tests fail 16/18 against the baseline chart (the other two are the regression guards the review asked for), the new script tests 5/5 against the baseline script; `./gradlew :backend:test` 44 tests 0 failures (IdentityPropertiesTest 6/6), `spotlessCheck` OK; `scripts/verify-backend-image.sh` and `scripts/verify-frontend-artifact.sh` pass, and the backend check fails on a bumped Gradle version and on a chart/image UID mismatch; every install variant of `scripts/qualify-local-install.sh` renders with the real Helm. Not run: the Kind qualification (cluster `owl-mast-om0102` untouched), the full `./gradlew build` integration suites, CI.
- Coordinator review round (2026-11-09): chart `version` 0.2.0 (appVersion 0.1.0) with an "Upgrading a release installed from chart 0.1.0" section; failed-init recovery restarts the PostgreSQL pod before the rerun (Secret env is fixed at container start); init/provisioning scripts also refuse a role with any membership and an existing database owned by another role; `IdentityProperties` rejects user info; `extraEnv` also refuses `LOADER_*`, `CLASSPATH`, `LD_PRELOAD`, `LD_LIBRARY_PATH`; `commonLabels` values follow the label-value rule; issuer host is a DNS name/IPv4 with optional numeric port, external hosts are label-based (optional trailing dot, trimmed for the shared-server comparison; aliases not detected); `verify_backend_image` selects pods with custom-columns and filters `<none>` in bash; new Docker-backed `deploy/tests/test_keycloak_readonly.py` (package-checks timeout 20 min); frontend read-only run derives UID/GID from the chart with cap-drop/no-new-privileges; `verify-install-package.sh` checks kubectl's gitVersion and creates the tools dir.

## Spec Change Log

## Review Triage Log

Round 1 (review_loop_iteration 0, diff since 137e084): blind-hunter (B), edge-case-hunter (E), verification-gap (V).

| ID | Finding | Verdict | Evidence | Route |
|----|---------|---------|----------|-------|
| B1 | Recovery doc reruns the init script with the pod's original (stale) Secret env | medium | `secretKeyRef` env is fixed at container start; docs say correct the Secret then exec | patch P1 |
| B2/E3 | Privileged-role check ignores role memberships (superuser group, pg_write_all_data, ...) | medium | SQL checks attributes only; an operator-created member role passes | patch P2 |
| B3/E1 | Existing database owned by another role is skipped silently | medium | `CREATE DATABASE ... WHERE NOT EXISTS`; the entrypoint's default POSTGRES_DB is the admin username, so `database.name` = admin username yields a superuser-owned app DB | patch P2 |
| B4 | Tautological distinct-names assertion in the long-name test | low | `len(names) == len({n for n in names})` always holds; (kind,name) uniqueness on the line before is real | patch P13 (delete) |
| B5 | Breaking default changes ship without a chart version bump or upgrade notes | medium | sslMode default, KC_PROXY_HEADERS, default-on NetworkPolicy, hook refusal on install, prefix pins; Chart.yaml stays 0.1.0 | patch P3 |
| B6/V2 | Default-on NetworkPolicies never exercised on an enforcing cluster | maybe-false (medium if true) | manifest tests only; needs traffic on an enforcing CNI | defer unless a disposable Kind run settles it |
| B7/E4 | Backend accepts issuer user info; http accepted without opt-in | low (user info); false (http) | `IdentityProperties` has no `getRawUserInfo` check; http must stay accepted for the cluster-local bundled issuer | patch P4 (user info only) |
| B8 | extraEnv denylist misses LOADER_*, LD_PRELOAD, LD_LIBRARY_PATH, CLASSPATH | low | schema pattern does not list them; regex extension is a direct correction | patch P5 |
| B9 | commonLabels values are not validated (length/charset) | low | schema `type: string` only; the API server rejects later; reserved-key breadth is correct because the chart sets part-of/version/managed-by too | patch P6 (values only) |
| B10 | Backend image check does not prove the read-only root contract | false | docs claim "qualified JVM on a read-only root", which is exactly what is checked; the full JDK ships `jar` | reject |
| B11/V1 | Keycloak read-only root and seed init container have no automated runtime check | medium | manifest-only assertions; a seed/cp regression crash-loops Keycloak with CI green | patch P7 |
| B12 | Frontend read-only smoke hardcodes UID 101 and omits cap-drop/no-new-privileges | low | `verify-frontend-artifact.sh` literal `--user 101:101`; backend script reads the chart | patch P8 |
| B13 | verify-ca/verify-full accepted but no CA trust is mounted | medium | pre-existing (accepted before this change; JDBC needs root.crt) | defer (CA trust mount is new surface) |
| B14/E6 | Tool header overstates checks; kubectl version not checked | low | only Helm's version is compared | patch P9 |
| B15/V3 | Frontend mutable-tag NOTES warning untested | low | only backend warning asserted | patch P10 |
| B16 | NetworkPolicy blocks monitoring of Keycloak management port | false | metrics are not enabled (no KC_METRICS_ENABLED); management serves probes, which are node traffic | reject |
| B17 | Committed spec stale / machine paths | n/a | fix would edit this build's spec | reject |
| B18 | Seed init container resources hardcoded; re-augment each start | false | re-augmentation per pod start predates this change (fresh container fs); startup budget 300s; smoke ready | reject |
| B19/E5/E9 | Issuer regex accepts empty host / non-numeric port; host pattern allows `a..b`; shared-server check compares raw strings | low | `https://:8443/x` renders then fails at backend startup; trailing-dot aliases skip the separate-DB rule | patch P11 |
| E2 | Rerun after password change keeps the old role password | false | documented design: an existing role keeps its password and the Secret must match; a refused collision creates nothing | reject |
| E7 | OWLMAST_TOOLS_DIR that does not exist gives an opaque curl error | low | no `mkdir -p`; direct correction | patch P9 |
| E8 | Positive-control tool tests fail hard without the archive | false | repository rule: required tools fail, never skip; the suite runs via verify-install-package.sh which provides the archive | reject |
| V4 | deletionTimestamp filter only asserted as source text | medium | stub ignores the go-template; a broken filter passes | patch P12 |
| B6/V2 (settled) | NetworkPolicy runtime | resolved | 2026-11-09 disposable Kind v0.33.0/kindnet run (cluster `owl-mast-gh109`, deleted afterwards): backend ready through both policies, foreign pod denied on :5432 and :8080, backend-labelled pod admitted, first-enable hook provisioned through the policy | no defer |
| R1-K | Kind run: `seed-quarkus-build` crash-loops on a real emptyDir (`cp -a` cannot preserve times on the root-owned mount) | high | reproduced on Kind; the Docker test had chowned its volume to the runtime user, hiding it | patch (orchestrator): `cp -R`, test volume shaped like a kubelet emptyDir; red before, green after |

## Verification

Work only in the worktree `/home/gabrianoo/.t3/worktrees/owlmast/om0102-review` (branch `t3/om-01-02-review-findings`); the main checkout holds unrelated uncommitted work. Do not commit or push. Qualified tools: `OWLMAST_HELM=/home/gabrianoo/.local/state/owlmast-eng01/product-runs/om-01-02-local-20261107-01-evidence/tools/helm`, `OWLMAST_KUBECTL=/home/gabrianoo/.local/state/owlmast-eng01/product-runs/om-01-02-discovery-20261107-01-evidence/tools/kubectl`. Docker is available.

**Commands:**
- `scripts/verify-install-package.sh` (with the two tool variables above) -- expected: all tests OK (the baseline was 63).
- `./gradlew :backend:test --tests '*IdentityPropertiesTest'` -- expected: pass.
- `scripts/verify-backend-image.sh` and `scripts/verify-frontend-artifact.sh` -- expected: pass.
- Docker read-only smoke for Keycloak (`--read-only` plus tmpfs at the chart's emptyDir paths, with a disposable PostgreSQL) -- expected: `/health/ready` 200.
