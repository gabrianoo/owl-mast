---
title: 'OM-01.02 qualification script: prove the provisioning hook without the Job Helm deletes (PR #116, V5)'
type: 'bugfix'
created: '2026-11-12'
status: 'done'
route: 'oneshot'
review_loop_iteration: 0
baseline_commit: '6d36856eee1ff1e9127220e8d18acbb5822cbd7d'
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The owner's Kind qualification of PR #116 (V5, 2026-11-12) stopped at step `provision-keycloak-job`. Since `c7578bb` the chart sets `helm.sh/hook-delete-policy: before-hook-creation,hook-succeeded` on the pre-upgrade provisioning hook, so Helm deletes the Job and its ConfigMap once the hook succeeded. `scripts/qualify-local-install.sh` still read the Job's status and log after `helm upgrade --wait`, and Kubernetes answered NotFound. The script was never run on a cluster after `c7578bb`, and no stub test ran the step.

**Approach:** Script only; the chart is not changed. Stop reading the deleted Job and its log. Record `pg_roles.oid` of the Keycloak role and `pg_database.oid` of the Keycloak database before the provisioning upgrade and require the same values after it. Keep the schema check. Treat a successful `helm upgrade --wait` as hook success and require a new `deployed` revision. Confirm the hook Job is absent afterwards. Fix every other read of a hook object the chart deletes. Make the stub world delete the hook Job on success, so a test fails on the old script and passes on the new one, with tests for unchanged and changed identifiers. Update `docs/`.

</frozen-after-approval>

## Implementation Notes

- Scope note. The owner delegated the fix in full, so the planning checkpoint was not held. This session is the implementation sub-agent of the owner's loop, so it started no further sub-agents: the Blind Hunter review layer was skipped, and the diff was self-reviewed. The independent check is the owner's rerun on the cluster.
- Fix commit: `785194f983ce1ed6bb24ff9aa4baa3f61aa1382a`. Files: `scripts/qualify-local-install.sh`, `deploy/tests/test_qualify_script.py`, `docs/installation.md`. The chart was not touched. The Kind cluster `owl-mast-om0102` was not touched and the script was not run against it.

V5 failure:
- Evidence of the owner's run: `provision-keycloak-upgrade` ok, then `provision-keycloak-job` failed with `Error from server (NotFound): jobs.batch "owl-mast-postgresql-provision-keycloak" not found`, in the same second the upgrade returned. Helm had already deleted the Job.

What the script does now:
- New helpers `keycloak_db_identity`, `record_keycloak_identity`, `record_release_revision`, `assert_revision_advanced`, `hook_objects_removed` and `reprovision_keeps_keycloak`.
- The identity is one line, `role=<pg_roles.oid> database=<pg_database.oid> owner=<pg_database.datdba>`, read with `pg_exec` as the Keycloak principal on its own database. That the read succeeds also shows the principal can still log in. A result that is not exactly one such line fails the check; an unreadable identifier is never treated as unchanged.
- `step_bundled_bundled`: identity and `helm status` revision before, `helm upgrade --wait` with `postgresql.provisionKeycloakDatabase=true`, revision after must be higher and `deployed`, identity after must be equal, the hook Job and ConfigMap must be absent, then the existing schema check.
- `hook_objects_removed` uses the script's `resource_state`, where only an explicit NotFound is absence. Absence passes. A hook object that is still present after a bounded wait (`HOOK_GONE_TIMEOUT`, default 30 s), or a state that cannot be read, fails: the delete policy the chart documents did not apply or is unproven.
- The `helm status` lines `STATUS: deployed` and `REVISION: <n>` were checked against the Helm 4.3.1 output in the V5 evidence.

Other places fixed:
- `step_first_enable` read the same Job three more times: `fe2-hook-job` (status), `fe2-hook-log` and `fe3-hook-log` (logs). All three are gone. The step is not part of `all`, so V5 did not reach it.
- First enable (fe2): the role and database are absent before (`fe1-no-keycloak-role`, unchanged); after the upgrade the revision is higher, the Keycloak principal reads its identity, and the hook objects are absent.
- Retry (fe3): uses `reprovision_keeps_keycloak`, and the identity must also equal the one recorded after the first enable.
- Lost evidence: the retry used to show `GRANT` lines from the Job log. That can no longer be observed. The privilege and CONNECT checks (`check_shared_postgres`) run after the first enable, as before.
- No other step reads a hook Job, its log or its ConfigMap. The failure-path and persistence steps were checked. Preflight asks for the hook objects with `--ignore-not-found`, where absence is a valid answer.
- `docs/installation.md` did not describe the Job's status or log as evidence. The qualification paragraph now describes the new proof.

Stub world and tests:
- No stub test ran `bundled-bundled` or `first-enable` past preflight before this change; the stub did not serve a Job, it answered every unknown call with `stub ok`.
- The helm stub now models the hook: on a successful provisioning upgrade the hook Job and ConfigMap are not in the world; `STUB_HOOK=failed` fails the upgrade and leaves the Job; `STUB_HOOK=kept` leaves the Job after success. It records revisions for `helm status`.
- The kubectl stub answers NotFound to `get job` and `logs job/` when the Job is not in the world, and answers the identity query from `STUB_KC_IDENTITY_<n>` (n = provisioning upgrades so far). `STUB_RUNTIME=1` adds the answers of a healthy install, so the two steps run end to end.
- New class `ProvisioningHookEvidenceTests`, 10 tests: both steps pass with the Job gone; changed role oid, database oid, owner, an unreadable identity and a malformed one each fail; a failed hook fails at the upgrade; a kept Job fails; no new revision fails; a missing schema fails; a static check that the script has no direct read of a hook object.

Verification at `785194f`:
- `scripts/verify-install-package.sh`: exit code 0, 197 tests OK, none skipped (187 before; `test_qualify_script` 38 → 48).
- `bash -n scripts/qualify-local-install.sh`: ok.
- shellcheck 0.11.0 (through `uvx --from shellcheck-py`; not installed on the machine): no new warning. One more info-level SC2015 note (20, was 19), the `A && log ok || { log FAIL; return 1; }` form the file already uses. The 3 warnings and 6 SC2016 notes are unchanged and older.
- Mutation 1: the script from `6d36856` with the new tests and stub world: 7 of the 10 new tests fail (12 failures with subtests). The output shows `FAIL provision-keycloak-job` and `FAIL fe2-hook-job`, the V5 failure. The 38 older tests pass.
- Mutation 2: the new script with the identity comparison disabled: 4 failures (the three changed-identifier subtests and the first-enable retry test).
- Not run: the script on a cluster. The owner reruns the qualification.

## Cycle-8 finding: the proof never showed that the hook ran

Review: https://github.com/gabrianoo/owl-mast/pull/116#pullrequestreview-5871692033 at `36ce4214e11739eb617358168094a86defbcdf28`, one inline comment on `reprovision_keeps_keycloak`.

- Scope note. The owner delegated the fix in full, so no planning checkpoint was held. This session is the implementation sub-agent, so it started no sub-agents: the Blind Hunter review layer was skipped, and the diff was self-reviewed.
- Fix commit: `574f0d534bae82dd4e95c70a83b12ee29da1463e`. Files: `scripts/qualify-local-install.sh`, `deploy/tests/test_qualify_script.py`. The chart and `docs/` were not changed. The Kind cluster `owl-mast-om0102` was not touched and the script was not run against it.

The finding, confirmed:
- `bundled-bundled` and the first-enable retry (fe3) passed when no hook ran. The upgrade result, the new revision, the unchanged oids, the absent hook objects and the schema are all equally true without a hook.

What the script does now:
- New helper `hook_ran_succeeded`. After the upgrade it runs `helm status <release> -n <ns> -o json` and checks the record with an inline `python3` program (`HOOK_RUN_CHECK`), the tool the script already uses for JSON.
- It requires all of these:
  - the record's `version` equals the deployed revision read just before;
  - exactly one `hooks[]` entry of kind `Job` named `<release>-postgresql-provision-keycloak`;
  - that entry has the event `pre-upgrade`;
  - `last_run.phase` is `Succeeded`;
  - `last_run.started_at` is not earlier than a timestamp the script takes just before the upgrade (`date -u +%s`);
  - `last_run.completed_at` is not earlier than `started_at`.
- The timestamp is stricter than the previous revision's `info.last_deployed`. Both sides use this host's clock, because Helm stamps `started_at` in the client process the script starts.
- A failed `helm status`, output that is not JSON, or any other shape fails the check.
- Only a projection goes to evidence: release name, revision, and one line per hook with kind, name, events, phase and times. The whole record (chart, values, manifests, live objects) is not written.
- The check runs in `reprovision_keeps_keycloak` (`bundled-bundled` and fe3) and in the first enable (fe2), as the review suggested.
- `assert_revision_advanced` now logs `revision <a> -> <b>, deployed` and no longer says that the hook succeeded. The `provision-keycloak-idempotent` and `fe3-retry-no-op` lines say "hook run recorded as Succeeded".
- `HOOK_GONE_TIMEOUT` must be digits only. Anything else is refused with exit 2 before any cluster call.
- Not done: the fe3 retry still does not show that the grants were re-applied. No cheap proof was found; a privilege query shows that grants exist, not that the retry applied them.

Helm 4.3.1 release record, verified:
- Source at the commit of the vendored binary (`c0d08d0d6d9424d4a14febb5e8a3e51b0dd00dff`, `helm version` of `tools/helm`):
  - `pkg/release/v1/release.go`: top-level keys `name`, `info`, `chart`, `config`, `manifest`, `hooks`, `version`, `namespace`, `apply_method`. `hooks` has `omitempty`.
  - `pkg/release/v1/hook.go`: a hook has `name`, `kind`, `path`, `manifest`, `events`, `last_run`, `weight`, `delete_policies`. `last_run` has `started_at`, `completed_at` and `phase`; zero times are omitted. Phases: `Unknown`, `Running`, `Succeeded`, `Failed`.
  - `pkg/action/hooks.go`: Helm sets `last_run` on the hook in the release when it runs it, and the deletion by policy does not clear it. `pkg/action/upgrade.go` stores the release after the hooks.
  - `pkg/cmd/status.go`: `-o json` prints the whole release.
- Binary: `tools/helm install --dry-run=client -o json` on a scratch chart with the two hooks printed the same keys. A hook that was not run has `"last_run": {"phase": ""}`.
- Run: a small Go program against the module `helm.sh/helm/v4 v4.3.1` ran a real install and upgrade (memory storage, fake Kubernetes client) with a pre-upgrade Job hook that has the chart's delete policy. The stored record of revision 2 had, for the Job: `"last_run": {"started_at": "2026-11-12T10:01:50.545521982+01:00", "completed_at": "2026-11-12T10:01:50.545522612+01:00", "phase": "Succeeded"}`. So `last_run` survives the hook deletion, and `started_at` is later than the revision's `info.last_deployed`.
- Time format: RFC 3339 with up to nine fractional digits and the local offset (or `Z`).
- Not verified: a hook run on a real cluster. The owner's rerun covers it.

Stub world and tests:
- The helm stub answers `status -o json` with a record in that shape. It keeps the hooks of the current revision per release.
- New `STUB_HOOK` outcomes, all with a successful upgrade, a new revision and no hook object:
  - `skipped`: the record has no hooks;
  - `not-run`: the hook is listed with `last_run` `{"phase":""}`, as after `helm upgrade --no-hooks`;
  - `stale`: Succeeded, but started before the upgrade;
  - `phase-failed` and `phase-running`.
- `STUB_HOOK_<n>` overrides the outcome of the n-th provisioning upgrade, so the retry can differ from the first enable.
- `STUB_STATUS_JSON` = `error`, `malformed` or `old-revision` for a record that cannot be used.
- 7 new tests in `ProvisioningHookEvidenceTests` (17 in the class):
  - `bundled-bundled` fails in each of the five outcomes;
  - the fe3 retry fails in each of them, after fe2 passed;
  - fe2 fails when its hook was skipped;
  - an unreadable, malformed or old-revision record fails;
  - 23 cases on the evaluator alone, with time formats and wrong shapes;
  - the record is not written to evidence whole;
  - `HOOK_GONE_TIMEOUT` values that are not digits are refused before any call.

Verification at `574f0d5`:
- `scripts/verify-install-package.sh`: exit code 0, 204 tests OK, none skipped (197 before; `test_qualify_script` 48 → 55).
- `bash -n scripts/qualify-local-install.sh`: ok.
- shellcheck 0.11.0 (through `uvx --from shellcheck-py`): the same counts as at `36ce421` (3 warnings, 20 SC2015 notes, 6 SC2016 notes). No new finding.
- Mutation: with both `hook_ran_succeeded` calls removed, 7 tests of the class fail (16 failures and 1 error with subtests). That includes all five outcomes for `bundled-bundled` and for the fe3 retry, `skipped` among them. The other 48 tests pass.
- Not run: the script on a cluster.
