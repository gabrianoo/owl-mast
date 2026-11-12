---
title: 'OM-01.02 review→fix loop, build cycle 6: resolve review 5867533032 (PR #116)'
type: 'bugfix'
created: '2026-11-12'
status: 'done'
route: 'oneshot'
review_loop_iteration: 0
baseline_commit: 'de12f814bf2202d3e4a44b6ea919aa8a770667a5'
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The cycle-6 review of PR #116 at `de12f81` left 2 inline comments. Material: with `identity.keycloak.service.port=80` the chart renders `KC_HOSTNAME` and the backend's issuer with `:80`, Keycloak publishes its issuer without the default port, and the exact issuer comparison keeps the backend DOWN. Minor: the database names `postgres`, `template0` and `template1` pass render and fail only after `initdb`.

**Approach:** On branch `t3/om-01-02-review-findings`, build the bundled Keycloak base URL in one helper that leaves out `:80`, and use it for `KC_HOSTNAME` and for the backend's issuer. Add render tests for port 80 and for other ports that show the two values match. Check every other place that builds the URL or uses the port (NOTES, the qualification script, the NetworkPolicy, docs). Refuse the system database names at render, ignoring case, with negative tests. Reply on each thread with the commit and resolve it; add a cycle-6 line to the PR body; record new decisions after D30. The owner delegated this cycle in full, so the approval checkpoint is taken as given. Do not touch the main checkout or the Kind cluster `owl-mast-om0102`, do not merge or approve, and leave the two owner-deferred threads open.

</frozen-after-approval>

## Implementation Notes

- Scope note. The owner delegated the cycle in full, so the planning checkpoint was not held. This session is itself the implementation sub-agent of the owner's review→fix loop, so it started no further sub-agents: the Blind Hunter review layer was skipped, and the independent review of this change is the loop's next review cycle. The diff was self-reviewed.
- Fix commit: `f6a1001a52c97d51949866e64df769e7e58f095c`.
- The review's claim about Keycloak was checked against the upstream source: `HostnameV2Provider` sets the port to `-1` when it is the scheme's default ("sanitize ports"). The claim holds.

Finding 1 (bundled Keycloak on Service port 80):
- New helper `owl-mast.keycloak.baseUrl` in `deploy/helm/owl-mast/templates/_helpers.tpl`. It prints `http://<fullname>-keycloak` for port 80 and `http://<fullname>-keycloak:<port>` for every other port. The port is read through `int`, so a float from a values file and a string from `--set-string` give the same result.
- `owl-mast.identity.issuerUri` and `KC_HOSTNAME` (`keycloak-deployment.yaml`) both include the helper. `identity.keycloak.service.port` is now read in one place in the helpers and in `keycloak-service.yaml`.
- `:443` is not dropped. The bundle is http only, so 443 is not its default port and Keycloak keeps it.
- Other places checked, no change needed:
  - `NOTES.txt` prints `owl-mast.identity.issuerUri`, so it follows the helper. A test reads the printed value.
  - `networkpolicy.yaml` admits port 8080, which is the container port. A NetworkPolicy port is the pod's port, so the Service port does not belong there. A test pins this for Service port 80.
  - `keycloak-service.yaml` still exposes the configured Service port and targets the named container port `http`.
  - `scripts/qualify-local-install.sh` greps the issuer with `:8080`. It installs with the default port only, so it stays correct.
- Docs: `docs/installation.md` (issuer paragraph) and the `values.yaml` comment on `identity.keycloak.service.port` state the rule. The docs say this is render support: only port 8080 ran on the local target.
- The backend did not change. An issuer without a port already parses.

Finding 2 (system database names):
- New helper `owl-mast.validateDatabaseName`, called from `owl-mast.validate` for `database.name` always and for `identity.keycloak.database.name` when `identity.bundled=true`. It compares in lower case, so it also holds with `--skip-schema-validation` (the schema admits lowercase names only).
- `template0` and `template1` are refused on every server. `$defs.databaseName` in `values.schema.json` also excludes them.
- `postgres` is refused only when `database.bundled=true`. That is where the chart's scripts run and where the review's failure happens. An external server may use `postgres`; some managed services provide no other database, and the chart runs no script there.
- Docs: `docs/installation.md` (before the "fixed at first initialisation" paragraph) and a `values.yaml` comment.

Tests, all in `deploy/tests/test_chart_render.py`, class `ReviewCycle6Test` (6 tests):

| Test | What it shows |
|---|---|
| `test_bundled_keycloak_on_port_80_publishes_the_issuer_the_backend_expects` | port 80: `KC_HOSTNAME`, the backend issuer and the NOTES line carry no port and match; the Service still listens on 80; float and string port values give the same result |
| `test_bundled_keycloak_on_another_port_keeps_it_in_both_values` | ports 8080, 8081, 443, 8, 800, 65535 stay in both values and match |
| `test_the_bundled_base_url_has_one_source` | both templates include the helper; the port is read once in the helpers |
| `test_the_keycloak_network_policy_admits_the_container_port_whatever_the_service_port` | the policy port stays 8080 with Service port 80 |
| `test_postgresql_system_databases_are_refused_as_database_names` | both keys, three names, three spellings, with and without the schema; `postgres` renders on an external server; names that only contain a reserved name render |
| `test_an_unused_keycloak_database_name_is_not_validated_by_the_templates` | with an external issuer the Keycloak database name is not checked by the templates; `database.name` still is |

Mutation check: with the chart directory reverted to `de12f81` and the new tests kept, 4 of the 6 fail (port 80, the single source, both database-name tests). The other two pass by design: they pin behaviour that was already correct (other ports, the NetworkPolicy port).

Disposition (comment id → outcome). PR #116 review 5867533032, 2 threads, both fixed:

| Comment | Thread | Outcome | Where |
|---|---|---|---|
| 4545058435 bundled Keycloak on Service port 80 never becomes ready (material) | `PRRT_kwDOVjxExc62bIQ4` | fixed | `owl-mast.keycloak.baseUrl`; 4 tests |
| 4545058440 system database names pass render (minor) | `PRRT_kwDOVjxExc62bIQ9` | fixed | `owl-mast.validateDatabaseName`, `$defs.databaseName`; 2 tests |

New owner decisions:
- **D31** The bundled Keycloak base URL leaves out port 80 and keeps every other port, 443 included, because the bundle is http only. The alternative was to refuse port 80 at render.
- **D32** `template0` and `template1` are refused as database names on every server. `postgres` is refused only with `database.bundled=true`; an external server may use it. The alternative was to refuse all three everywhere through the schema.

Left open on purpose, owner-deferred from cycle 1: `PRRT_kwDOVjxExc62YN_x` (Kind rerun for chart 0.2.0) and `PRRT_kwDOVjxExc62YN0L` (Gateway CEL rules against a real API server).

Verification record, local, 2026-11-12:
- `scripts/verify-install-package.sh`: exit 0; 187 tests, no failures, no skips (181 at `de12f81`). Helm v4.3.1 and kubectl v1.36.1, both checksum verified.
- `./gradlew build` was not run: no backend file changed.
- Not run: a Keycloak on port 80 in a cluster, the Kind qualification (cluster `owl-mast-om0102` untouched) and any server-side Gateway API check. Port 80 is render support only.

## Verification

**Commands:**
- `scripts/verify-install-package.sh` -- expected: exit 0, all deploy tests pass.
- `OWLMAST_HELM=<helm 4.3.1> python3 -m unittest deploy.tests.test_chart_render.ReviewCycle6Test` -- expected: 6 tests pass.
