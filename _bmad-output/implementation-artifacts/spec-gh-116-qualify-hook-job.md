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
