# Installation package (OM-01.02)

Owl Mast installs from the repository-owned Helm chart `deploy/helm/owl-mast` (version 0.2.0; see [Upgrading a release installed from chart 0.1.0](#upgrading-a-release-installed-from-chart-010)). The
chart packages the backend image and two **independently optional** bundles: PostgreSQL 18 with
VectorChord, and Keycloak. Disabling a bundle means supplying a compatible existing service; it never
removes the dependency. There is no value that disables authentication. Chart 0.1.0 was qualified on
2026-11-07 for GitHub issue #21 on a disposable local Kind target. Chart 0.2.0 was qualified on the same
target on 2026-11-12 and 2026-11-13 with the OM-01.03 migrations and durable work included; the last
`all` run was at `639d2b6` (2026-11-13), and `first-enable` passed uninterrupted from a fresh volume through the
bootstrap-admin retirement at `d314fa3` (2026-11-13; see [Qualification status](#qualification-status) for what ran, at which
revision, and what did not). The frontend shell
artifact and its smoke check are delivered by OM-01.04, browser realm/client/session policy by OM-02.01.

## Qualification status

| What | Chart 0.1.0 | Chart 0.2.0 |
| --- | --- | --- |
| Render, lint, negative validation (`scripts/verify-install-package.sh`) | passed | passed (CI `package-checks`) |
| PostgreSQL initialisation, provisioning and probe commands against the pinned image (Docker) | passed | passed (CI `package-checks`) |
| Keycloak on a read-only root against the pinned image (Docker) | not applicable | passed (CI `package-checks`) |
| Backend image: UID, JDK, application start on a read-only root with the environment the chart renders, up to the first database connection (image-level proof; the beans created after database initialisation, migrations, the listener and runtime writes are part of the Kind run) | not checked | passed (CI `build`) |
| NetworkPolicy enforcement on a disposable kindnet cluster | not applicable | one run on 2026-11-09, before the changes of 2026-11-11 |
| Kind qualification (`scripts/qualify-local-install.sh all`): four combinations, persistence, failure paths | passed 2026-11-07 | passed 2026-11-12, four times: at `f188d51` (PR #116, before OM-01.03; 131 ok), at `4fc415b` (141 ok, 0 FAIL), at `00b4853` (145 ok, 0 FAIL) and at `e76e30e` (Keycloak with `KC_CACHE=local`, 145 ok, 0 FAIL); passed 2026-11-13 at `c0e21ec` (now ending bundled-bundled with the bootstrap-admin retirement, 156 ok, 0 FAIL) at `9be72ee` (exit 0, 156 ok, 0 FAIL) and at `a2c3051` (exit 0, 156 ok, 0 FAIL; the script recorded `deploy`, `scripts` and `backend` as clean) and at `639d2b6` (exit 0, 156 ok, 0 FAIL; three source records, whole tree clean, one chart digest) |
| Kind qualification, `first-enable`: fresh volume, identity bundle enabled through the pre-upgrade hook, retry | passed 2026-11-07 | passed 2026-11-12 at `00b4853` up to and including the retry (fresh volume `owl-mast-fe-e01r01`); the run then stopped at the retirement, see the next rows and the note below. Passed 2026-11-13 at `d314fa3`, uninterrupted from a fresh volume (`owl-mast-fe-e01x10`) through the retirement: 63 ok, 0 FAIL (run 11 below) |
| Kind qualification: every migration applied by `owlmast_app`, durable work published by the installed backend (in all four combinations and first-enable). The probe writes a synthetic intent and its `audit.publish` item in SQL as `owlmast_app`, so it proves discovery, the claim, the handler transaction and the publisher, not the application's enqueue path; its rows are kept | not applicable (no durable work before OM-01.03) | passed 2026-11-12 at `00b4853`: migrations 001–005 applied by `owlmast_app` on the bundled and the external database (V002–V005 as an upgrade of the databases the earlier runs left at V001); durable work published in bundled-bundled, bundled-external, external-bundled, external-external and first-enable. Rechecked 2026-11-13 at `c0e21ec`, `9be72ee`, `a2c3051` and `639d2b6` (`all` only, on the retained databases: no migration was pending, so these runs re-read the history and table owners that the `00b4853` run left, and migrations were last applied at `00b4853`; durable work was published in the four combinations; `first-enable` was last run at `00b4853`). Passed 2026-11-13 at `d314fa3` in `first-enable` on a fresh database: migrations 001–005 applied by `owlmast_app`, durable work published |
| Kind qualification: Keycloak bootstrap admin retired (`identity.keycloak.bootstrapAdmin.enabled=false`), chart side only | not applicable | **failed** in the scripted run at `00b4853` (`helm upgrade --wait` timed out: chart defect). `31ee127` (no surge) only narrowed the overlap of the two Keycloak pods; the fix is `d954b21` (`KC_CACHE=local`). The manual rerun at 22:39Z passed on an uncommitted no-surge chart without `KC_CACHE=local`: its log names `bf6126b` (whose chart has `type: Recreate`), the deployed strategy was `RollingUpdate 0 1`, and the change was committed two minutes after the rerun ended, as `31ee127`, so no commit reproduces that pass. **Passed** on the shipped chart in the scripted `all` run at `c0e21ec`, on the bundled release: the retirement replaced the Keycloak pod (names before and after recorded) and `helm upgrade --wait` completed in 50 s. That run did not record whether the old pod was still terminating beside the new one, so it shows the replacement completing on the shipped chart, not that `KC_CACHE=local` was needed; the script now records every read of its terminating-pod wait. Rerun at `9be72ee`: the pod was replaced again, and the wait's first read (01:25:58Z, a few seconds after `helm upgrade --wait` returned) found no terminating Keycloak pod, so the old pod was gone by that read; an overlap is still not shown. Rerun at `a2c3051`, which records when the upgrade returned: the pod was replaced, and the upgrade's return and the wait's one read (`none`) fall in the same second (02:13:31Z). Rerun at `639d2b6`: the same, at 03:11:43Z. **Passed** as part of one complete `first-enable` on a fresh volume at `d314fa3` (run 11 below): `helm upgrade --wait` returned in about 26 s with the new Keycloak pod ready; an overlap of the two pods is still not shown |
| Frontend image deployed on the Kind target | not run | **not run** by the script (`frontend.enabled=false`); deferred |
| `helm upgrade` of a release installed from chart 0.1.0 | not applicable | **refused** by server-side apply, and not supported. Run on the Kind target on 2026-11-14 (bundled-bundled, Helm 4.3.1, which installed the 0.1.0 release and applies server-side): the API server refuses the backend Deployment's change to `type: Recreate` (`spec.strategy.rollingUpdate: Forbidden: may not be specified when strategy type is 'Recreate'`), and the refused upgrade has already replaced the PostgreSQL and Keycloak pods (run 3 of the 2026-11-14 upgrade runs below). An upgrade that Helm applies client-side (Helm 3, Helm 4 with `--server-side=false`, or Helm 4 on a release that was installed client-side) was not run; the server may accept it, and it is not supported either way. The replacement the guide gives instead (uninstall, then install this chart on the retained claim) was **not run** for a 0.1.0 installation: a render test installs the 0.1.0 values on the claim, and the Kind qualification runs the reinstall for chart 0.2.0 only. Chart 0.1.0 was never released, so the chart keeps `Recreate` and has no in-place upgrade from it (#162, decided 2026-11-15 in PR #189); see [Upgrading a release installed from chart 0.1.0](#upgrading-a-release-installed-from-chart-010) |
| Gateway API: HTTPRoute accepted by an API server with the CRDs (server-side CEL) | not run | **not run** (manifest validation only) |
| Gateway API: controller and data plane | not run | not run |

**The 2026-11-12 and 2026-11-13 runs, exactly.** All on the retained cluster `owl-mast-om0102` with a run-local kubeconfig; evidence in `~/.local/state/owlmast-eng01/product-runs/e01-r01-qual-20261112-0{1,2}-evidence/`, `e01-r01-qual-20261113-0{1,2,3,4,5}-evidence/` and `e01-x10-first-enable-20261113-01-evidence/` (private, not in the repository). "Backend image built from that commit" below is the operator's record, not the script's: in every run the image was built before the run and outside the script, tagged with the commit, and `run.txt`, which names it, is written by hand. The script checks only that the node runs the local image with that tag (`*-image.txt`). Its source records (runs 9 and 10) describe the checkout when each record was taken, which is after the build, so they do not show the tree the image was built from; in run 10 the image was created at 03:09:40Z and the first record is at 03:09:55Z.

1. `all` at `4fc415b`, backend image built from that commit: exit 0, 141 ok, 0 FAIL (21:56–22:04Z).
2. `all` at `00b4853` (after the review fixes; durable work now checked in all four combinations): exit 0, 145 ok, 0 FAIL (22:17–22:24Z).
3. `first-enable` at `00b4853` on a fresh run-owned volume (`FE_RELEASE=owl-mast-fe-e01r01`): the fresh initialisation, the first enable through the pre-upgrade hook, the AC3 checks, durable work and the idempotent retry passed (51 ok). The last phase, the retirement of the bootstrap admin, **failed**: `helm upgrade --wait --timeout 10m` with `identity.keycloak.bootstrapAdmin.enabled=false` did not complete (22:26–22:36Z). Cause: the Keycloak Deployment rolled, so the new pod ran beside the old one, tried to join it in a cluster that the NetworkPolicy does not admit, reported `Keycloak cluster health check: DOWN` and never became ready. This was the first upgrade in any qualification that changed the Keycloak pod.
4. The chart was changed (`31ee127`: the Keycloak pod is replaced without surge). This narrowed the overlap but did not remove it: under `RollingUpdate` the controller starts the new pod while the old one is still terminating. The fix came later in `d954b21` (`KC_CACHE=local`, so a Keycloak pod never looks for a cluster). Before that, the chart at `bf6126b` tried `type: Recreate`. The upgrade of the existing release to it failed twice (22:38Z and 22:39Z, `fe5r-upgrade-to-fixed-chart`); the API server refused the change (`spec.strategy.rollingUpdate: Forbidden: may not be specified when strategy type is 'Recreate'`), which is why the fix keeps `RollingUpdate` with `maxSurge: 0`. Both attempts wrote the same evidence file, which the passing rerun then overwrote, so the second refusal's output is not kept.
5. The stuck release was rolled back to its last deployed revision, upgraded with the admin still injected to a chart with the no-surge strategy that was **not committed yet** (the log says `chart head bf6126b`, whose chart has `type: Recreate`; the deployed strategy was `RollingUpdate 0 1`; the change was committed at 22:41:44Z as `31ee127`), and the script's own `retire_bootstrap_admin` was run on it: **passed** (22:39–22:40Z; the upgrade completed in 40 s, no bootstrap variable and no reference to the Secret in the Deployments or running pods, Keycloak and backend ready, Keycloak role and database unchanged). The fixture was then uninstalled and its claim retained.

6. `all` at `e76e30e` (review 5883535263: Keycloak runs with `KC_CACHE=local`), backend image built from that commit: exit 0, 145 ok, 0 FAIL (2026-11-12, 23:39–23:47Z). Evidence in `e01-r01-qual-20261113-01-evidence/`. This run did **not** exercise the Keycloak fix: its re-provisioning upgrade leaves the Keycloak pod template unchanged, and the same pod ran before and after it. `all` did not include the retirement either.
7. `all` at `c0e21ec` (review 5884091345: bundled-bundled now ends with the bootstrap-admin retirement, which must replace the Keycloak pod), backend image built from that commit: 156 ok, 0 FAIL, and the log ends with `qualification steps complete` (2026-11-13, 00:28–00:36Z; the exit status was not written to the evidence, unlike runs 1, 2 and 6). The retirement upgrade replaced `owl-mast-keycloak-554bfbdc57-6w5kv` with `owl-mast-keycloak-7667df9c75-wr4fx` and completed in 50 s, and the references were read once no Keycloak pod was terminating. The evidence does not show whether the two pods overlapped: the old pod's deletion time and the reads of the terminating-pod wait were not recorded. Evidence in `e01-r01-qual-20261113-02-evidence/`.
8. `all` at `9be72ee` (review 5884592685: the terminating-pod wait records every read), backend image built from that commit's backend: exit 0 (recorded), 156 ok, 0 FAIL (2026-11-13, 01:24–01:32Z). The retirement replaced `owl-mast-keycloak-554bfbdc57-p4ckz` with `owl-mast-keycloak-7667df9c75-87nfv`; the wait's one read at 01:25:58Z found no terminating Keycloak pod. Evidence in `e01-r01-qual-20261113-03-evidence/`.
9. `all` at `a2c3051` (review 5884955290: the script writes its own `source.txt`, the time `helm upgrade --wait` returned and every read of the wait), backend image built from that commit: exit 0 (recorded), 156 ok, 0 FAIL (2026-11-13, 02:11–02:19Z). `source.txt`: head `a2c3051`, tree clean, chart sha256 `4a0a7522…`. At that revision the script checked only `deploy`, `scripts` and `backend` and wrote one record, at the start. Since review cycle 5 it checks the whole tree (the root Gradle files are build inputs of the backend image, although a record taken after the build does not show the tree the image came from; see above), appends a record at the start, right before the retirement upgrade and at the end, and fails the run when the chart digest changes after the first record. The retirement replaced `owl-mast-keycloak-554bfbdc57-88z24` with `owl-mast-keycloak-7667df9c75-xd5vw`; `helm upgrade returned` and the wait's one read (`none`) are both at 02:13:31Z. Evidence in `e01-r01-qual-20261113-04-evidence/`.
10. `all` at `639d2b6` (review 5885379553: the source record is appended at the start, before the retirement upgrade and at the end, over the whole tree), backend image built from that commit (`0.1.0-e01r01c5-639d2b6`, the node ran image id `e1b61552…` in every combination): exit 0 (recorded), 156 ok, 0 FAIL (2026-11-13, 03:09–03:17Z). `source.txt` holds three records (03:09:55Z start, 03:11:03Z before `bb-retire-retire-upgrade`, 03:17:55Z end), each with head `639d2b6`, tree clean and chart sha256 `4a0a7522…`, the same chart as at `a2c3051`. The retirement replaced `owl-mast-keycloak-554bfbdc57-h64k8` with `owl-mast-keycloak-7667df9c75-54vnz`; `helm upgrade returned` and the wait's one read (`none`) are both at 03:11:43Z. Evidence in `e01-r01-qual-20261113-05-evidence/`.

11. `first-enable` at `d314fa3` (`main` after PR #147) on a fresh run-owned volume (`OWLMAST_FOLLOWUP_RUN_ID=e01-x10-first-enable-20261113-01`, `FE_RELEASE=owl-mast-fe-e01x10`, claim `owl-mast-fe-e01x10-postgresql-data`), backend image `0.1.0-e01x10-d314fa3` built from that commit: exit 0 (recorded), 63 ok, 0 FAIL (2026-11-13, 18:11–18:13Z). Every phase passed in one invocation: the app-only initialisation, the first enable through the pre-upgrade hook (revision 1 → 2), the AC3 checks with migrations 001–005 applied by `owlmast_app`, durable work, the idempotent retry (2 → 3, role and database oids unchanged) and the retirement (3 → 4). The retirement replaced `owl-mast-fe-e01x10-keycloak-8584c9dd6d-6kz6s` with `owl-mast-fe-e01x10-keycloak-7d5468484b-6mdw8`; `helm upgrade --wait` started at 18:12:58Z and returned at 18:13:24Z, and the wait's one read (`none`) is at 18:13:24Z. The namespace events put the old pod's stop and the new pod's start in the same second (18:12:59Z), so a short overlap can be neither ruled out nor confirmed, and whether `KC_CACHE=local` was needed is still not shown. The three source records (start, before the retirement, end) each hold head `d314fa3`, tree clean and chart sha256 `4a0a7522…`. `first-enable` does not call the script's node-image check; the node's image id for the tag (`b95e0292…`) was compared with the local build by hand after the run. Evidence in `e01-x10-first-enable-20261113-01-evidence/`.

The `00b4853` failure (run 3) did not recur: `first-enable` has now run uninterrupted from a fresh volume through the retirement on the fixed chart (run 11). What this does not amount to: proof that the two Keycloak pods overlapped and that `KC_CACHE=local` is what prevents the failure; no run has recorded an overlap. Run 11 used the fourth claim in `owl-mast-test`, made room for by deleting the 2026-11-07 fixture claim `owl-mast-fe-postgresql-data`; the 30 Gi storage quota is used up again by three retained claims, so the next fresh-volume run needs a claim freed first.

**The 2026-11-14 upgrade runs (#162), exactly.** Run by hand, not by the script, on the same cluster (`owl-mast-om0102`) with Helm 4.3.1 and a run-local kubeconfig, in a namespace of their own (`owl-mast-gh162`, default `standard` StorageClass, removed afterwards). Evidence in `~/.local/state/owlmast-eng01/product-runs/gh-162-upgrade-20261114-01-evidence/` (private, not in the repository): one directory per run, and the two scripts that made the runs (`upgrade-run.sh` for runs 1 and 2, `upgrade-run-2.sh` for runs 3 and 4). Every release was bundled-bundled with the example values. Three charts appear. "Chart 0.1.0" is the chart tree of `137e084`, the parent of the commit that made the chart 0.2.0, with the backend image of 2026-11-07 (`owl-mast/backend:0.1.0`). "This chart" in the historical run descriptions below means the chart at `397c783` (sha256 `4a0a7522…`, the chart of runs 9–11 above), whose backend Deployment is `type: Recreate`. "The no-surge variant" is a chart that was tried for #162 and **not kept**: this chart with the backend rolling without surge (`maxSurge: 0`, `maxUnavailable: 1`; sha256 `335117b8…`, taken from the working tree at `397c783`, so each run's `source.txt` records head `397c783` and a dirty tree; committed on the #162 branch as `681a125` with a different comment, sha256 `49fbe62d…`, and withdrawn on 2026-11-15). The upgrades used the backend image `0.1.0-e01x10-d314fa3` (the backend sources have not changed since `d314fa3`). None of these runs called the script's node-image check.

1. `explicit/` (16:59–17:01Z): chart 0.1.0 installed and ready, then `helm upgrade --wait` to the no-surge variant with the example values (17:00:27Z–17:01:13Z). Completed as revision 2.
2. `reuse-values/` (17:01–17:03Z): the same upgrade to the no-surge variant on a fresh release and volume, with `--reuse-values --set backend.image.tag=0.1.0-e01x10-d314fa3` (17:02:28Z–17:03:04Z). Completed as revision 2. After runs 1 and 2 the backend and Keycloak Deployments had `RollingUpdate` with `maxSurge: 0` and `maxUnavailable: 1`, all three pods were new and ready, backend readiness was `UP`, no pod was terminating when the upgrade returned, the claim was bound to the same volume, PostgreSQL reported the same system identifier and the same database oids, and `flyway_schema_history` had gone from version 001 to 001–005, each applied by `owlmast_app`.
3. `failed-then-fixed/` (17:15–17:17Z): chart 0.1.0 installed and ready, then upgraded to this chart. Refused within a second with `spec.strategy.rollingUpdate: Forbidden: may not be specified when strategy type is 'Recreate'`; revision 2 is `failed`. The refusal is not atomic: Helm had already applied the PostgreSQL and Keycloak Deployments, so both pods had been replaced (the new ones were not ready yet when the state was read 3 s later), while the backend Deployment and its pod were as chart 0.1.0 left them. The upgrade of that release to the no-surge variant completed as revision 3 (17:16:37Z–17:17:18Z), with the end state of runs 1 and 2. Its pod watch shows the two backends overlapping: the new container started at 17:16:37Z and the old one ended at 17:16:39Z.
4. `from-recreate/` (17:17–17:18Z): this chart installed and ready, upgraded to the no-surge variant (revision 2), rolled back to revision 1 with `helm rollback` (the strategy was `Recreate` again), and upgraded to the no-surge variant again (revision 4). All three were applied and the strategy was read after each. The backend pod was the same pod throughout: a strategy change alone does not change the pod template.

What the runs show: `helm upgrade` from chart 0.1.0 to this chart is refused when Helm 4.3.1 applies it server-side (run 3), and a backend that rolls without surge is accepted but runs the old and the new backend together during a rollout (about 2 s in run 3). Because of that overlap the no-surge variant was withdrawn, and because chart 0.1.0 was never released the upgrade from it is not supported (#162, decided 2026-11-15 in PR #189). Only run 3 watched the backend pods, so runs 1, 2 and 4 say nothing about an overlap. What this does not amount to: nothing was run for the combinations with an external database or identity provider, for `helm rollback` to a chart 0.1.0 revision, or for a release installed or upgraded with Helm 3, and no run measured a rollout of this chart's `Recreate` backend for an overlap. Other ways to get a 0.1.0 release past the refusal (deleting the backend Deployment before the upgrade, a forced replacement by Helm) were not tried. Before run 1 the refusal was reproduced once, and an explicit `rollingUpdate: null` next to `type: Recreate` was tried and refused with the same message (16:56Z, external-external values, pods not started, namespace `owl-mast-gh162-probe`, removed): server-side apply does not remove a field that no manager owns. Those two attempts left no evidence files; run 3 repeats the refusal with evidence, the `null` attempt is recorded here only.

The scripted qualification was also run on the no-surge variant: `all` at `681a125` with the backend image `0.1.0-e01x10-d314fa3` (node image id `b95e0292…`, compared by the script in every combination): exit 0 (recorded), 156 ok, 0 FAIL (2026-11-14, 17:22–17:31Z; the three source records each hold head `681a125`, tree clean and chart sha256 `49fbe62d…`; evidence in `gh-162-qual-20261114-01-evidence/`). It is a run of a chart that was not kept, so it is not counted in the table above. Runs 9–11 qualified chart hash `4a0a7522…`, not the current artifact. PR #189 subsequently adds digest enforcement and a bounded Flyway retry setting in four chart files, including a new backend pod environment variable. The strategy remains `Recreate`; the changed chart has render/negative tests and process-level migration tests, but the full chart runtime qualification has not been rerun.

## Pins

| Component | Pin | Where | Source / qualification |
| --- | --- | --- | --- |
| Chart | `owl-mast` 0.2.0, `appVersion` 0.1.0 | `deploy/helm/owl-mast/Chart.yaml` | This repository; package hash is produced by `helm package` from the release commit |
| Backend image | `owl-mast/backend:0.1.0`, built by `backend/Dockerfile` from the `bootJar` and referenced by tag; set `backend.image.digest` to the registry manifest digest once the image is published (a local image id from `docker build` is not a manifest digest and is not accepted by Kubernetes as one); until then the release NOTES warn that a mutable tag decides what runs. An empty tag and digest together fail rendering. `scripts/verify-backend-image.sh` (CI `build` job) checks the jar name against the Gradle version, builds the image and proves UID/GID 10001 (the chart's `runAsUser`), the qualified JVM on a read-only root, the boot jar, and that the application itself starts from the image entrypoint on that read-only root (as UID/GID 10001, no capabilities, `/tmp` the only writable path) up to configuration binding, where it stops on the deliberately missing issuer. It does not prove a complete start against a database and an issuer; that is the Kind qualification | `backend/Dockerfile`, `backend.image.*` | Base `ubuntu:26.04@sha256:6a06111c3b0a8600feadb270aec771dc239bf407b25625f93f44ab00e11f4d3c`; Temurin 27.0.1+1 Linux x64 tarball sha256 `30cb129f…` (same JDK as [toolchain-qualification.md](toolchain-qualification.md)), verified during the build |
| PostgreSQL / VectorChord | `tensorchord/vchord-postgres:pg18-v1.1.1@sha256:700ff05ebdc7e4afd4dd8442e0684293046c3833677fec326550000a04cf8a91` (PostgreSQL 18.3, VectorChord 1.1.1, pgvector 0.8.2) | `postgresql.image` | Accepted OM-01.01 pin, reused unchanged |
| Keycloak | `quay.io/keycloak/keycloak:26.8.2@sha256:3879c623248408de29a5303178b5816c77e8dfef3890c361f8c0bbeaa979ba3b` | `identity.keycloak.image` | Release 26.8.2 (2026-11-05); PostgreSQL 18 is a supported database. Kubernetes 1.36 is **not** an upstream-certified Keycloak platform: startup, database schema creation, readiness and discovery were proven on the local target below, nothing more |
| Kubernetes | `>=1.31`; qualified on Kind 0.33.0 `kindest/node:v1.36.4@sha256:099e049362a1526b2db71494e1947aae99bd16290d7c895f2b7ea312e3cbfaed` | `Chart.yaml` `kubeVersion`, `deploy/local-kind/` | Kind release notes; kubectl 1.36.1 |
| Helm | 4.3.1 (`helm-v4.3.1-linux-amd64.tar.gz` sha256 `0403a88ae20913d11b10a2467b50087721fea7581736da6b9d3992f5357fe54b`) | `scripts/verify-install-package.sh`, CI | Helm 4 supports Kubernetes 1.36; Helm 3.16 (1.28–1.31) is not used |

## Secret contract

Every credential is an **existing** Secret reference with the keys `username` and `password`. The
chart never creates or templates credential values; a missing Secret or key leaves the pod in
`CreateContainerConfigError` and nothing starts with empty credentials.

| Value | Default name | Used by |
| --- | --- | --- |
| `database.existingSecret` | `owl-mast-db` | Backend application principal (`owlmast_app` by convention); also consumed by the bundled PostgreSQL initialisation |
| `postgresql.adminExistingSecret` | `owl-mast-postgres-admin` | Bundled PostgreSQL provisioning superuser only (initialisation, extensions); no runtime component uses it |
| `identity.keycloak.database.existingSecret` | `owl-mast-keycloak-db` | Keycloak's own database principal (`keycloak_app`); referenced only when `identity.bundled=true` (by Keycloak, by the bundled PostgreSQL initialisation and by the provisioning Job) |
| `identity.keycloak.bootstrapExistingSecret` | `owl-mast-keycloak-bootstrap` | Keycloak temporary bootstrap admin; referenced only when `identity.bundled=true` and `identity.keycloak.bootstrapAdmin.enabled=true` |

With `identity.bundled=false` an install needs only `database.existingSecret` (and `postgresql.adminExistingSecret`
when the database is bundled); no Keycloak credential or database is provisioned.

Every principal has its own Secret: rendering fails, naming both keys, when two of the Secret references in
use name the same Secret. The usernames inside the Secrets are only visible at runtime, so the bundled
PostgreSQL scripts refuse, before creating anything, an application or Keycloak username equal to the
provisioning superuser's, a Keycloak username equal to the application's, and an existing role of that name
with elevated attributes (superuser, createrole, createdb, replication, bypassrls).

The bootstrap admin is temporary. Keycloak creates it from `KC_BOOTSTRAP_ADMIN_USERNAME`/`_PASSWORD` when the
master realm has no admin, and the chart injects those variables for as long as
`identity.keycloak.bootstrapAdmin.enabled` is `true` (the default). To retire it: sign in with it, create a
permanent admin, delete the temporary user, then `helm upgrade` with
`identity.keycloak.bootstrapAdmin.enabled=false`. The Keycloak pod then no longer references the Secret (a render
test asserts that nothing does) and the Secret can be deleted. The release NOTES repeat this while the admin is
injected. The switch-off was run on the Kind target on 2026-11-12 (`first-enable` ends with it): it exposed a chart defect (the Keycloak pod rolled beside the old one and never became ready), and the fix is `KC_CACHE=local` (`d954b21`). The switch-off has since passed on the shipped chart in the scripted `all` runs and in one complete `first-enable` at `d314fa3`; see [Qualification status](#qualification-status). Once it is retired,
`identity.keycloak.bootstrapExistingSecret` may be emptied, and a leftover value no longer takes part in the
distinct-Secret check. `bootstrapAdmin.enabled=false` on an **install** is an explicit choice, not refused: it
fits a reinstall on a retained volume or an external Keycloak database that already holds a permanent admin.
On a fresh database Keycloak then starts without any administrator, and the release NOTES warn about it.

## Combinations

| `database.bundled` | `identity.bundled` | Rendered | Required values | Example |
| --- | --- | --- | --- | --- |
| true | true | backend, PostgreSQL (PVC), Keycloak | defaults | `examples/bundled-bundled.yaml` |
| true | false | backend, PostgreSQL | `identity.external.issuerUri` | `examples/bundled-external.yaml` |
| false | true | backend, Keycloak | `database.external.host`, `identity.keycloak.database.external.host` | `examples/external-bundled.yaml` |
| false | false | backend | `database.external.host`, `identity.external.issuerUri` | `examples/external-external.yaml` |

`helm template` fails with the offending value named when a required external value is missing,
when a secret reference is empty, or when an unknown key (for example `auth.enabled`) is passed
(`values.schema.json` rejects unknown top-level keys).

A "compatible" external PostgreSQL is version 17 or newer with VectorChord 1.1.1 preloaded and installed in the
application database (the bundle is PostgreSQL 18.3). Only PostgreSQL 18 is qualified: every test, CI job and
Kind run uses an 18.x image. 17 is the oldest version the backend accepts (the first with `transaction_timeout`)
and has not been run. The chart cannot see the version of a server it does not
run, so the backend checks it: the `schemaBaseline` readiness component reads `server_version_num` and stays
DOWN below 17, with the log line `PostgreSQL <major> answered; Owl Mast requires PostgreSQL 17 or newer` (once per
process). The durable-work scheduler asks again at every wake-up and claims nothing while the answer is no, cannot be read or takes longer than 10 s: it logs `Durable work is paused: …` once when the pause starts and `Durable work resumes: …` when it ends, so a short database outage also shows as one pause and one resume.
Durable work bounds each handler transaction with `transaction_timeout`, which PostgreSQL 17 introduced; on an
older server every handler would fail and audit publication would retry forever.

Transport to external dependencies fails closed. `identity.external.issuerUri` must be an `https://` URL whose
host is a DNS name or IPv4 address with an optional numeric port, and with no query, fragment or user info (the
backend refuses a query, fragment or user info as well, naming `owlmast.identity.issuer-uri`); a plaintext `http://` issuer renders only with
`identity.external.allowInsecureIssuer=true`, for disposable local fixtures. `database.external.sslMode` and
`identity.keycloak.database.external.sslMode` default to `require`; `disable`, `allow` and `prefer` can fall back
to plaintext and render only with the matching `allowInsecureTransport=true`. `require` encrypts the connection
but does not authenticate the server. `verify-ca`/`verify-full`, which would, are **refused at render**: the chart
mounts no CA trust yet (deferred), so they would render and then fail every database connection of the backend
and Keycloak. The schema does not list the two modes, and the templates refuse them on their own. The issuer's
host must be one the backend's URI parser (`java.net.URI`) reads as a server host: a DNS name whose last label
starts with a letter, a single label, or an IPv4 address with octets 0–255, with an optional trailing dot on a
name. Hosts such as `idp.123` or `1.2.3.999` parse there without a host, so the chart refuses them instead of
rendering a backend that stops at startup. An IPv6 literal is not accepted by the chart. The chart tests and the
backend tests read one sample file (`backend/src/test/resources/identity/issuer-samples.txt`), so the two rules
are compared on every build. The issuer's port must be 1–65535 and its path may use only RFC 3986 path
characters and complete `%XX` escapes, which is what the backend's URI parser accepts; the backend checks the
port range as well. The
backend also refuses a plaintext `http://` issuer by itself unless `owlmast.identity.allow-insecure-issuer` is
true, which the chart sets (`OWLMAST_IDENTITY_ALLOW_INSECURE_ISSUER`) only for the cluster-local bundled Keycloak
or for `identity.external.allowInsecureIssuer=true`, so the rule holds on every deployment path. The issuer is
used verbatim: a trailing slash is part of it. For the bundled Keycloak the chart builds `KC_HOSTNAME` and the
backend's issuer from one helper (`http://<fullname>-keycloak:<identity.keycloak.service.port>`), and leaves the
port out when it is 80, because Keycloak publishes its issuer without the scheme's default port. This is render
support, covered by render tests; only the default port 8080 was run on the local target. `backend.javaToolOptions` accepts a named allow-list of JVM memory
and tuning options only: `-Xms`/`-Xmx`/`-Xmn`/`-Xss` with a size, and the `-XX` options listed next to the value
in `values.yaml` (for example `-XX:MaxRAMPercentage=75`, `-XX:+UseZGC`). System properties (`-D…`), agents,
argument files and every other `-XX` option are refused, the file-loading, hook and attach options included
(`-XX:SharedArchiveFile`, `-XX:ErrorFile`, `-XX:+StartAttachListener`, `-XX:+EnableDynamicAgentLoading`), because
a JVM system property outranks the validated environment and those options load files or open the attach
mechanism. Image tags must be valid registry tags (no whitespace). Service and container ports are integers 1–65535, Service types are `ClusterIP`,
`NodePort` or `LoadBalancer`, and database names are at most 63 characters (PostgreSQL truncates longer
identifiers). External hosts are bare DNS names (RFC 1123 labels
separated by single dots, optional trailing dot) or IPv4 addresses (no port, path or query: they are spliced
into the JDBC/R2DBC URLs). `backend.extraEnv` refuses
names that would override the validated configuration (`OWLMAST_*`, `SPRING_*`, `MANAGEMENT_*`, `SERVER_*`,
the Spring Boot launcher's `LOADER_*`, the JVM option variables, `CLASSPATH`, and every dynamic-loader variable
`LD_*`, such as `LD_PRELOAD`, `LD_AUDIT` and `LD_LIBRARY_PATH`)
as well as credential-like names, in the schema and again in the templates, so `--skip-schema-validation` does
not reopen it; `commonLabels` refuses keys under `app.kubernetes.io/` and `helm.sh/`, which
the selectors own, and values that are not valid Kubernetes label values (at most 63 characters, alphanumeric
at both ends). `commonLabels` reach every rendered object and the backend, Keycloak, frontend and provisioning
pods, so editing them restarts those pods. The PostgreSQL pod template carries no `commonLabels`: with the
`Recreate` strategy a label edit would otherwise stop the database, and the backend and Keycloak with it.
In this document `<fullname>` is `fullnameOverride` when set. Otherwise the chart's name is `nameOverride`, or
`owl-mast` when that is empty, and `<fullname>` is the release name when it contains that name and
`<release>-<nameOverride>` (by default `<release>-owl-mast`) otherwise. The commands below spell object names
as `<fullname>-postgresql` and `<fullname>-postgresql-data`. That holds for a `<fullname>` of at most 52
characters. For a `<fullname>` longer than 52 characters the PostgreSQL Deployment gets a shortened, hashed
name and the claim is that name plus `-data`, so use the Deployment and claim names that `NOTES` prints after
the install or upgrade (the render refusals print the same names); `kubectl get deploy,pvc -l
app.kubernetes.io/instance=<release>,app.kubernetes.io/component=postgresql` lists them too. Generated names stay within 63 characters for any
release name or `fullnameOverride`: the base is shortened before each suffix is appended, and a shortened base
carries a 6-character hash of the release name and full name, so two long-named releases in one namespace do not
render the same name by accident (names that fit are unchanged). The hash is not a guard against intent: a
release deliberately named after another release's shortened name plus its hash renders the same names. Helm's
ownership check then refuses the shared objects, and only the provisioning hook Job and its ConfigMap, which
Helm replaces by name, could be taken over. The one exception to the 63-character rule is the data claim, which
keeps its chart 0.1.0 name `<fullname>-postgresql-data` (a claim name may have 253 characters): shortening it
would attach a new, empty volume on upgrade. An external PostgreSQL must be version 18 with
`CREATE EXTENSION vchord CASCADE` available to the provisioning identity; the backend migration only
verifies the extension is present. An external issuer must publish an OpenID Connect discovery
document whose `issuer` equals the configured value exactly (OpenID Connect Discovery 4.3; a difference of
one trailing slash is a mismatch, because tokens carry the published value); the backend's readiness group
includes that check (`identityDiscovery`) together with the schema baseline, so a misconfigured or unreachable
identity provider keeps the backend unready while liveness stays up. On a mismatch the backend logs a warning
naming the configured value and the value the provider published, once per published value (not on every
readiness evaluation; again when the value changes or after the issuer matched in between), and the health
detail carries both on every evaluation (`issuer` and `publishedIssuer`, shortened to 200 printable characters;
health details are not shown over HTTP by default). The discovery outcome is kept for 5 s, counted from the
start of the discovery request and not from its answer (which can take up to 3 s), so
the identity provider receives at most one discovery request per 5 s however often readiness is evaluated;
`backend.probes.readiness.periodSeconds` must therefore be greater than 5, so that two consecutive probes never
read the result of the same request (smaller values are refused at render).

## Upgrading a release installed from chart 0.1.0

**An in-place `helm upgrade` from chart 0.1.0 is not supported, and server-side apply refuses it.** The backend
Deployment rolled in chart 0.1.0 and is `type: Recreate` now. A Deployment that was created without a strategy
carries the API server's default `rollingUpdate` block, and the server refuses a server-side apply that changes
only the type (`spec.strategy.rollingUpdate: Forbidden: may not be specified when strategy type is 'Recreate'`).
That is what was run: on the Kind target (2026-11-14, bundled-bundled, Helm 4.3.1 for the 0.1.0 install and for
the upgrade, so both were applied server-side) the upgrade failed within a second, and not atomically: the
PostgreSQL and Keycloak pods had already been replaced, the release was `failed`, and the 0.1.0 backend kept
running (run 3 of the 2026-11-14 upgrade runs under [Qualification status](#qualification-status)). An upgrade
that Helm applies client-side was not run: Helm 3, Helm 4 with `--server-side=false`, or Helm 4 on a release
that was installed client-side (`helm upgrade --help` of 4.3.1: `--server-side` defaults to `auto`, the previous
release's method). Such an upgrade sends a patch computed from the old manifest, the new one and the live
object instead of the whole manifest, so the server may accept it; either way it is not supported. Chart 0.1.0
was never released, so the chart keeps `Recreate` instead of giving up the single-instance rollout for that
upgrade (#162, decided 2026-11-15 in PR #189). Replace a 0.1.0 installation by uninstalling it and
installing this chart under the same release name, so that `<fullname>` and with it the claim and Secret names
stay the same. The bundled PostgreSQL claim survives the uninstall and is selected again with
`postgresql.persistence.existingClaim` (see
[Persistent volumes and retention](#persistent-volumes-and-retention-t3)); the Secrets the operator created are
not Helm's and stay. The provisioning hook cannot serve such a reinstall: install with the identity mode the
volume was initialised with (see [Enabling the identity bundle later on an initialised bundled
PostgreSQL](#enabling-the-identity-bundle-later-on-an-initialised-bundled-postgresql)). A release that the refused upgrade left `failed` is replaced in the same way. The Kind qualification proves the
uninstall retention and the reinstall on the existing claim for a release of chart 0.2.0. Not run: the same
for a release that chart 0.1.0 installed, and `helm rollback` of a `failed` release to its 0.1.0 revision.

Chart 0.2.0 (appVersion unchanged) closes the PR #109 review findings and changes these defaults; check each
against the values of the 0.1.0 installation before installing this chart with them. Every row describes what
this chart does with those values when it is installed. Where a row names `helm upgrade` or `helm rollback`, it
means a later upgrade or rollback of the release that this chart installed, not an upgrade of a 0.1.0 release.

Values: the 0.1.0 `values.yaml` lacks every key added in 0.2.0. The templates read those keys with their
0.2.0 defaults (`bootstrapAdmin.enabled=true`, `networkPolicy.enabled=true`, the probe timeouts,
`exposeActuator=false`), and the schema requires none of them, so the chart renders from 0.1.0 values; a render
test applies the 0.1.0 `values.yaml` with no new defaults, as the install on the retained claim and as an
upgrade. What 0.1.0 values cannot carry over are defaults
that 0.2.0 refuses: a 0.1.0 external database still has `sslMode: prefer` and is refused until the mode is set
(first row below).

| Change in 0.2.0 | What to set |
| --- | --- |
| External `database.external.sslMode` and `identity.keycloak.database.external.sslMode` default to `require` (was `prefer`); `disable`, `allow`, `prefer` are refused | A server without TLS: keep the mode and set the matching `allowInsecureTransport=true` |
| `identity.external.issuerUri` must be `https://` with a host the backend parses (a DNS name whose last label starts with a letter, a single label, or an IPv4 address; no IPv6 literal), optional numeric port, no query, fragment or user info | A plaintext issuer: `identity.external.allowInsecureIssuer=true` |
| External hosts must be bare DNS names or IPv4 addresses (no port, path or query) | Move a port into `*.external.port` |
| `KC_PROXY_HEADERS` is no longer set on the bundled Keycloak (was `xforwarded`) | Behind a trusted proxy that is the only path to Keycloak: `identity.keycloak.proxyHeaders=xforwarded` |
| `networkPolicy.enabled=true` renders ingress-only NetworkPolicies for the bundled PostgreSQL and Keycloak | Other clients of those services: `networkPolicy.{postgresql,keycloak}.extraFrom`, or `networkPolicy.enabled=false` |
| `postgresql.provisionKeycloakDatabase=true` is refused on install | Use it only on `helm upgrade` (`helm template --is-upgrade`) |
| `routing.apiPathPrefix` is exactly `/api`; `routing.actuatorPathPrefix` is `/actuator[/...]`; `routing.frontendPathPrefix` is `/` | Remove other prefixes; the chart renders no rewrite |
| The actuator is no longer routed by the Ingress or HTTPRoute | Only to publish it on purpose: `routing.exposeActuator=true` |
| An HTTPRoute needs `routing.gateway.hostnames` (DNS names, no IP addresses) | List the hostnames, or acknowledge every listener hostname with `routing.gateway.allowAllListenerHostnames=true` |
| Every `routing.ingress.tls` entry needs `secretName`; host labels are at most 63 characters; `routing.ingress.host` and the TLS hosts are DNS names, not IP addresses (the API server rejects an IP address) | Name the TLS Secret; use a DNS name |
| `sslMode=verify-ca` and `verify-full` are refused. The refusal names the mode and the reason (no CA trust is mounted yet), also when 0.1.0 values that used one of them are installed | Use `require` until the CA trust mount ships |
| `backend.javaToolOptions` accepts a named allow-list of JVM memory and tuning options only, each with the value form the JVM takes (sizes: a whole number with an optional `k`/`m`/`g`; percentages: a number without a suffix; counts: a whole number) | Move application settings out of JVM options; drop `-XX` options that are not listed in `values.yaml`; write `-XX:MaxRAMPercentage=75`, not `75m` |
| `identity.keycloak.proxyHeaders` needs `networkPolicy.enabled=true` and `networkPolicy.keycloak.extraFrom` entries that select the proxy; an empty peer, an empty `podSelector` or `namespaceSelector`, a selector made only of `Exists`, `NotIn` or `DoesNotExist` terms, an `ipBlock` wider than `/8` (IPv4) or `/32` (IPv6), and an IPv6 `ipBlock` that embeds an IPv4 address (IPv4-mapped `::ffff:0:0/96`, IPv4-compatible `::/96`, or any dotted form; `::ffff:0.0.0.0/96` is read as `0.0.0.0/0`) are refused | Name the proxy's pods or namespace with `matchLabels` or an `In` term, or its address range |
| `backend.probes.readiness.periodSeconds` must be greater than 5 | Raise a smaller period |
| `backend.extraEnv` refuses every `LD_*` name; `identity.keycloak.bootstrapAdmin.enabled` must be `true` or `false` (also with `--skip-schema-validation`) | Remove loader variables; write the boolean |
| `commonLabels` are no longer copied into the PostgreSQL pod template | Nothing; select the database pod by the chart's own labels |
| The backend Deployment uses the `Recreate` strategy (single instance). This is the change that server-side apply refuses on a release installed from chart 0.1.0 (above) | Expect the backend to be down for the length of its restart on every rollout |
| The bundled Keycloak pod is replaced, not rolled (`maxSurge: 0`, `maxUnavailable: 1`). Under the default rolling update the new pod waited for a cluster with the old one, which the NetworkPolicy does not allow, and never became ready, so any upgrade that changed the Keycloak pod (for example retiring the bootstrap admin) hung until `--wait` timed out. Found and fixed by the Kind qualification of 2026-11-12 | Expect sign-in and backend readiness to be down while Keycloak restarts on such an upgrade. A release stuck in that state recovers with `helm rollback` to its last deployed revision and an upgrade to this chart |
| `frontend.containerPort` is fixed at 8080, the only port the frontend image listens on (also with `--skip-schema-validation`); any other value pointed the probes and the Service at a port without a listener | Remove an override; use `frontend.service.port` to change the Service port |
| The backend image starts the JVM with `--enable-native-access=ALL-UNNAMED` (Netty's native libraries on JDK 24+) | Nothing. Do not try to pass it through `backend.javaToolOptions`: the allow-list refuses it, and the image already sets it |
| The backend applies migrations V002–V005 (durable work, audit, non-blank tenant ids) and stays not ready on a PostgreSQL server older than 17 | An external PostgreSQL must be 17 or newer; the bundled one is 18 |
| The bundled PostgreSQL pod template differs from chart 0.1.0 (probe commands, `fsGroupChangePolicy`, script-only checksum) | Nothing: replacing a 0.1.0 installation starts a new database pod in any case. A chart version bump of a release that this chart installed does not recreate the database pod |
| The backend refuses a plaintext issuer unless told otherwise; the issuer is compared exactly | Nothing for the plaintext flag (the chart sets it for the bundled Keycloak and for `allowInsecureIssuer=true`). For an external issuer, check the trailing slash: an installation that was ready on 0.1.0 with an issuer differing from the published one only by a trailing slash is unready when its values are installed with this chart, with no error at render: a trailing slash is part of the issuer. Compare `identity.external.issuerUri` with the `issuer` of the provider's discovery document before installing; afterwards the backend log names the published value (health detail `publishedIssuer`) |
| Service and container ports must be integers 1–65535; database names at most 63 characters; `backend.image.tag` or `digest` required | Correct the values |
| The HTTPRoute requires the `gateway.networking.k8s.io/v1/HTTPRoute` capability | Install the Gateway API CRDs (`helm template --api-versions gateway.networking.k8s.io/v1/HTTPRoute`) |
| `identity.keycloak.importRealm=false` requires an acknowledgement | `identity.keycloak.realmManagedByOperator=true` |
| Distinct Secrets per principal, distinct Keycloak database name on a shared server, reserved `commonLabels` keys and invalid label values, overriding `backend.extraEnv` names are refused | Give each principal its own Secret; rename the colliding values |

## Shared PostgreSQL (AC3)

The bundled instance initialises once from `postgresql-init-configmap.yaml`: databases `owlmast`
and `keycloak`, login roles `owlmast_app` and `keycloak_app` (`NOSUPERUSER NOCREATEDB NOCREATEROLE
NOINHERIT`), `REVOKE ALL … FROM PUBLIC` on both databases, on `postgres` and on `template1` (`template0` accepts
no connections), `CONNECT, TEMPORARY`
granted only to each owner, and `vchord CASCADE` installed in `owlmast` by the provisioning
identity. Verified on the local target: each runtime principal is not a superuser and is refused
(`permission denied for database`) when connecting to the other database; a `vchordrq` index on
synthetic vectors is created by `owlmast_app` and used by the planner (`Index Scan using …`); no
`hnsw`/`ivfflat` index exists. Operators supplying an external PostgreSQL must reproduce the same
separation; the init script is the reference. With Keycloak bundled on a shared server (the bundled instance,
or the same external host and port) `identity.keycloak.database.name` must differ from `database.name`. The
comparison is textual (case and a trailing dot are ignored): aliases of one server, such as an IP address and a
DNS name, are not detected. On a shared **external** server the chart checks only that the two Secrets and the
two database names differ. It cannot read the usernames inside the Secrets at render time and runs no script on
an external server, so two Secrets carrying the same username would give Keycloak and the application one
principal; the release NOTES print a warning for this combination, and the separation is the operator's to
reproduce. A volume initialised by an earlier chart keeps `PUBLIC` `CONNECT` on `template1` until the init
script is run again in the pod (the command below) or the first-enable hook runs.

The bundled PostgreSQL has no TLS: the application and Keycloak connect to it with `sslmode=disable`, so
credentials and data cross the pod network unencrypted. Isolation relies on the NetworkPolicy and on the cluster
network. Where the pod network is not trusted, an external PostgreSQL with `sslMode=require` encrypts the
connection but does not authenticate the server, so it stops a passive listener and not an active interceptor,
who can pose as the database and collect the application's and Keycloak's credentials. Server authentication
needs `sslMode=verify-full` with a mounted CA, which the chart does not ship yet; both that mount
([#121](https://github.com/gabrianoo/owl-mast/issues/121)) and TLS for the bundled PostgreSQL
([#124](https://github.com/gabrianoo/owl-mast/issues/124)) are tracked as deferred work. The release NOTES state this for every bundled-database
install.

Rendering refuses PostgreSQL's system databases as `database.name` or `identity.keycloak.database.name`,
whatever their case: `template0` and `template1` always, and `postgres` when the bundled PostgreSQL serves the
database (there the scripts would refuse it only after `initdb`, because the superuser owns it). An external
server may use `postgres`, as some managed services provide nothing else.

`database.name`, `identity.keycloak.database.name` and the usernames and passwords in the principals' Secrets are
fixed at first initialisation: the scripts run once, on an empty data directory, and a later change of these
values creates nothing. The pods then keep failing authentication or name a database that does not exist. To
change one on an initialised volume, apply it in PostgreSQL first, as the provisioning superuser
(`kubectl exec deploy/<fullname>-postgresql -- psql -U "$POSTGRES_USER" -d postgres`), then change the value or
Secret and upgrade:

- password: `ALTER ROLE <username> PASSWORD '<new password>';`
- username: `ALTER ROLE <old> RENAME TO <new>;` followed by the password statement (a rename clears an MD5 password);
- database name: stop the backend (or Keycloak), then `ALTER DATABASE <old> RENAME TO <new>;`.

The chart does not detect such a change at render time (that needs a read of the live objects, which
`helm template` cannot test); it is a documented operator procedure.

Every statement of the init script is idempotent (`CREATE ROLE`/`CREATE DATABASE` only when absent, grants
re-applied, `CREATE EXTENSION IF NOT EXISTS`). Every refusal runs first, for the application and, through
`provision-keycloak.sh --preflight`, for Keycloak, so a Keycloak collision no longer stops the script after the
application role and database were created. It refuses, before creating anything, an existing role with
elevated attributes or any role membership and an existing database owned by a role other than the expected
principal (for example `database.name` equal to the admin username, whose database the image's entrypoint
creates). The entrypoint runs it only on an empty data directory, so if a first initialisation stops midway
(for example on a refused collision), correct the Secret, then restart the PostgreSQL pod
(`kubectl delete pod -l app.kubernetes.io/instance=<release>,app.kubernetes.io/component=postgresql`): the
container reads Secret values into its environment only when it starts, and the first-initialisation script
does not rerun on the now initialised volume. Then complete it in the new pod:
`kubectl exec deploy/<fullname>-postgresql -- bash /docker-entrypoint-initdb.d/10-owl-mast-databases.sh`;
a second run creates nothing.

`networkPolicy.enabled` (default `true`) renders ingress-only NetworkPolicies: the bundled PostgreSQL accepts
:5432 only from this release's backend, Keycloak and provisioning Job (the last two are admitted even with
the identity bundle disabled, because the upgrade that enables it runs the provisioning hook under the policy
rendered before that upgrade), and the bundled Keycloak accepts :8080 only from the backend; `networkPolicy.{postgresql,keycloak}.extraFrom` adds NetworkPolicyPeer entries (for
example a Gateway data plane in front of Keycloak, OM-02.01). Node-originated traffic (kubelet probes, the
API-server proxy on a single-node target) is not governed by peer rules and stays allowed; egress is not
restricted. Enforcement depends on the cluster's network plugin. On 2026-11-09 a disposable Kind v0.33.0 cluster
(kindest/node v1.36.4, kindnet, which enforces NetworkPolicy) ran the bundled-bundled install with the frontend:
the backend became ready through both policies, API-server proxy reads of the backend and Keycloak discovery
succeeded, a pod outside the release got no response from PostgreSQL :5432 and was blocked on Keycloak :8080, a
pod carrying the backend's labels reached both, and the first-enable upgrade's provisioning hook created
Keycloak's role and database through the PostgreSQL policy. That run also caught, and the Docker test now
reproduces, an init-container failure on a real emptyDir. That run predates the changes of 2026-11-11. The
Kind qualification of 2026-11-12 ([Qualification status](#qualification-status)) installed chart 0.2.0 with its
default NetworkPolicies on the retained kindnet target: the backend reached PostgreSQL and Keycloak through
them in every combination, and the provisioning hook reached PostgreSQL. It has no negative step (a pod
outside the release being refused), so the denial side still rests on the 2026-11-09 run.

## Enabling the identity bundle later on an initialised bundled PostgreSQL

The first-initialisation script of the bundled PostgreSQL runs once, when the data directory is
empty. A volume initialised with `identity.bundled=false` therefore has no `keycloak` database or
`keycloak_app` role, and simply switching to `identity.bundled=true` leaves Keycloak failing
authentication (unready, nothing destroyed). PostgreSQL stays Ready and keeps serving the application database:
its readiness probe covers the application database only, so the backend keeps its database and the hook below
can reach the server through the Service. The explicit transition is one `helm upgrade --wait`
with `identity.bundled=true` and `postgresql.provisionKeycloakDatabase=true`. It renders a
**pre-upgrade** hook (`<fullname>-postgresql-provision-keycloak`, with its own hook ConfigMap
`<fullname>-postgresql-provision-scripts`) that runs against the PostgreSQL of the release as it is
before the upgrade: it waits, bounded, for `pg_isready`, then executes the idempotent
`provision-keycloak.sh` with the admin principal, so Keycloak's role and database exist before Helm
applies and waits for the Keycloak and backend consumers. The role is created only if absent (an
existing role keeps its password, so the Secret must match it), the database only if absent, and the
restricted grants are re-applied; nothing is dropped or recreated. The Keycloak database Secret must
exist before the upgrade (the hook fails before anything else changes otherwise). The value is rejected
unless both bundles are enabled, is refused on install (a fresh install provisions at first initialisation;
`helm template` needs `--is-upgrade` to render the hook), and should be left `false` afterwards. The hook is
bounded below Helm's default 5m timeout: it fails at once when the release's PostgreSQL Service does not
resolve (for example an upgrade that switches `database.bundled` on together with it), waits at most 20 ×
(3 s + 5 s) for `pg_isready`, and the Job has `activeDeadlineSeconds: 240` and no retry (`backoffLimit: 0`). The hook
Job and its ConfigMap carry the delete policy `before-hook-creation,hook-succeeded`: both are removed as soon as
the hook succeeds, so nothing referencing the admin and Keycloak database Secrets outlives the upgrade or an
uninstall. A failed Job stays for diagnosis; the next attempt replaces it, and `kubectl delete job,configmap -l
app.kubernetes.io/instance=<release>,app.kubernetes.io/component=postgresql-provisioning` removes it by hand.
Disabling the identity bundle later keeps the existing Keycloak database and principal untouched.

The hook cannot serve a **reinstall** that reuses a retained claim (`postgresql.persistence.existingClaim`): it is
a pre-upgrade hook, and on an initialised volume the first-initialisation script does not run. If that volume
was initialised with `identity.bundled=false` and the reinstall enables the identity bundle, nothing has
provisioned Keycloak's database. Either install with `identity.bundled=true` and then provision it in the
PostgreSQL pod, which already carries the helper and Keycloak's credentials
(`kubectl exec deploy/<fullname>-postgresql -- bash /owl-mast/provision-keycloak.sh`; idempotent), or reinstall
with the identity mode the volume was initialised with and enable the bundle afterwards with the `helm upgrade`
above. Until the database exists only Keycloak is affected: its pod fails to start (its log names the missing
database or the failed authentication), and the backend stays unready because the issuer is unreachable.
PostgreSQL itself stays Ready, so the `kubectl exec` above and the application database keep working.

Initialisation layout: only `10-owl-mast-databases.sh` is placed in `/docker-entrypoint-initdb.d`
(the image's entrypoint auto-executes every `*.sh` there); the provisioning helper is mounted at
`/owl-mast/provision-keycloak.sh` and invoked explicitly, so a volume initialised with the identity
bundle disabled completes initialisation on the first start. The synthetic external fixture
(`deploy/local-kind/external-fixtures.yaml`) declares the same two mounts. `deploy/tests/test_postgresql_init.py`
derives the layout from the actual Deployment manifests (chart and fixture) and exercises fresh
initialisations and the first-enable/retry transition against the pinned image in disposable containers.

## Probes and resources (AC1)

| Component | Startup | Liveness | Readiness | Default requests / limits |
| --- | --- | --- | --- | --- |
| Backend | `GET /actuator/health/liveness` (≤ 3 min) | same | `GET /actuator/health/readiness` (readinessState, schemaBaseline, identityDiscovery), `timeoutSeconds: 5` | 250m/512Mi – 1/1Gi |
| PostgreSQL | `pg_isready` on the Unix socket | `pg_isready` on the Unix socket | over TCP, `select 1` against the application database only; each exec probe has `timeoutSeconds: 5` | 250m/512Mi – 1/1Gi |
| Keycloak | `/health/started` on 9000 (≤ 5 min) | `/health/live` | `/health/ready` | 500m/768Mi – 1/1536Mi |

The frontend (when enabled) has `GET /` liveness and readiness probes.

The backend's readiness probe allows 5 s, more than the 3 s the identity-discovery check waits for the issuer, so
a slow issuer is reported by the check's own reason and not as a kubelet probe timeout (the Kubernetes default
is 1 s); `backend.probes.<probe>.timeoutSeconds` changes it, and a render test keeps it above the Java constant.
PostgreSQL's startup and liveness probes use the Unix socket because the image's entrypoint runs its
first-initialisation server on the socket only: a TCP probe failed for that whole phase and the kubelet could
kill a slow initialisation midway. Readiness stays on TCP, so the initialisation server is never Ready. The
Docker suite holds a container in that phase and runs the rendered probe commands in it.

The backend is a single instance (`backend.replicas` at most 1, AD-14) and its Deployment uses the `Recreate`
strategy: a rollout stops the old pod before it starts the new one, so two backends never run against one
database, at the cost of the backend being down while it restarts. That covers rollouts (an upgrade that
changes the backend pod). A backend pod that is deleted or evicted outside a rollout is replaced at once,
while it may still be shutting down, so for that time two backends share the database. A backend pod on a
node that is cut off from the API server is replaced too, and it keeps running, so there the two share the
database for as long as the node is cut off: see
[Two backends on one database](#two-backends-on-one-database) below. The actuator serves these probes inside
the cluster and is not routed externally (see routing below).

The backend may restart once on a cold install because it starts before the database accepts
connections; Flyway fails fast, the kubelet restarts the container and the second start succeeds.
All pods run as non-root with explicit numeric users, drop all capabilities and use the `RuntimeDefault`
seccomp profile; the chart passes the `restricted` Pod Security level. The backend, Keycloak and frontend
run with a read-only root filesystem: Keycloak writes only to emptyDirs at `/opt/keycloak/data`, `/tmp` and
`/opt/keycloak/lib/quarkus` (seeded from the same image by the `seed-quarkus-build` init container, because an
empty mount would hide the image's build output and Keycloak re-augments there at start); the frontend runs as
UID/GID 101 with emptyDirs at `/tmp` and `/etc/nginx/conf.d` (where the image renders its template). Both are
proven in Docker with the rendered user, read-only root, dropped capabilities and no-new-privileges, and tmpfs or
volumes at the rendered paths: `deploy/tests/test_keycloak_readonly.py` runs the rendered init container and
Keycloak against a disposable PostgreSQL with the seed volume shaped like a kubelet emptyDir (root-owned, group fsGroup, mode 2777; management `/health/ready` 200, discovery issuer as rendered), and
`scripts/verify-frontend-artifact.sh` reads the frontend's UID/GID from the chart. PostgreSQL keeps a writable root. `KC_PROXY_HEADERS` is not
set: the cluster-local Keycloak has no proxy in front of it, and `identity.keycloak.proxyHeaders`
(`xforwarded`|`forwarded`) is for a trusted proxy that is the only path to it: rendering it requires
`networkPolicy.enabled=true` and a `networkPolicy.keycloak.extraFrom` entry naming the proxy, because without the
policy any pod could send forged forwarding headers and without the entry the policy admits no proxy at all. An
entry names the proxy when its selector has a `matchLabels` entry or a `matchExpressions` term with operator `In`
(`Exists`, `NotIn` and `DoesNotExist` terms alone can match every pod or namespace), or when its `ipBlock` has a
prefix of at least `/8` for IPv4 or `/32` for IPv6. The chart cannot check that the labels or the range belong
to the proxy and to nothing else; that stays with the operator. With
`identity.keycloak.importRealm=false` the issuer realm exists only if an operator creates it, so rendering
requires the acknowledgement `identity.keycloak.realmManagedByOperator=true`.

### Two backends on one database

`Recreate` keeps a rollout to one backend at a time. Outside a rollout two backends can share the database
in two cases:

- **A pod that is deleted or evicted.** It is replaced while it may still be shutting down. The two overlap
  until the old pod has stopped.
- **A node that is cut off from the API server but still reaches the database.** Kubernetes marks the node
  unreachable. Once the pod has tolerated that for its `tolerationSeconds` (300 s where the cluster keeps the
  Kubernetes default; the chart sets no toleration and has no value for one), Kubernetes marks the pod for
  deletion and starts a replacement on another node, if the cluster has one. The kubelet on the cut-off node
  does not learn of the deletion, so the old backend is not asked to stop and is not killed. It keeps
  claiming and running durable work next to its replacement until the node reaches the API server again,
  which can take minutes or longer; then the kubelet stops it. This is how Kubernetes handles an unreachable
  node (read from its documentation, the pages "Nodes" and "Taints and Tolerations"); it was not run here.

In both cases the two backends are the same build as long as the image reference is immutable (a digest, see
[Pins](#pins)); with a tag that was pushed again the replacement can be another build, which is not covered
here. `OverlappingBackendsIT` (backend integration suite, part of `./gradlew build` and of the CI `build`
job) runs the overlap with two separate processes of the real application on one PostgreSQL and proves these
four things:

- **Migrations.** Two backends started together on an empty database both run Flyway, and every migration is
  recorded once. The test holds the first migration open: the backend inside it holds Flyway's advisory lock,
  and the other one keeps asking for the lock and is refused. That is all the test observes of the lock.
  Flyway 12.4.0 takes and releases it once per migration (read from its code, not tested), so after the first
  migration the two can take turns, and the test does not check which backend applied which migration.
- **One queue.** Two running backends drain one queue of durable work with every item claimed once and its
  effect applied once. Claimed once is counted by a trigger the test puts on the work table, one row per
  claim, because `attempt_count` alone (1 on every item) would not show a claim that was released or given
  back and then repeated. Each publication intent has one publish item among those items, so every intent
  was published once; the count of one audit event per intent would not show a repeat by itself, because
  that insert is idempotent.
- **Stopping.** A backend that is asked to stop (SIGTERM) while it holds an item gives the item back, and the
  backend that is already running completes it, with the effect applied once. Until then the running backend
  leaves the item alone, because its lease is live. The handler in this test is waiting when the stop arrives:
  it has no statement in flight and has written nothing in its transaction.
- **A late write.** A backend that is still inside a handler when its lease has expired, and finishes after the
  other backend has reclaimed and completed the item, cannot change the item: its completion write is rejected.
  An effect the handler applied outside its database transaction has then been applied twice, under the same
  idempotency key. That is the contract's at-least-once delivery
  ([durable work contract](durable-work-and-audit-contract.md)): a handler has to deduplicate such an effect by
  that key. The contract also says that what the handler wrote inside its transaction rolls back with the
  rejected write; this test does not assert that.

These four things are about the database, not about how the pod was replaced, so they are what applies in
both cases. The cases differ in how long the two backends run together. For a pod that is shutting down it
is that shutdown. For a cut-off node it is the whole time the node is cut off, and both backends are fully
running: that is the state "One queue" was tested in, for seconds and not for that long. "A late write" and
its at-least-once delivery can then occur at any moment of that time. A cut-off does not make them more
likely for one item (the case still needs a backend that stalled past its lease), but a handler has to
deduplicate its effect outside the database by the idempotency key for as long as the cut-off lasts.
"Stopping" applies when the node is back and the kubelet stops the old backend. "Migrations" matters only
when both backends start on a database that still has migrations to apply; a replacement of the same build
finds none.

A backend that is killed while it holds a lease (the grace period ran out, or the node failed) is covered by
`ProcessRestartRecoveryIT`: the lease stays until it expires (`owlmast.jobs.lease-duration`, 30 s by default),
then another backend reclaims the item. A node that is cut off while its backend keeps running is the second
case above: that backend is not killed.

Additional fault coverage in `OverlappingBackendsIT`:

- **Receiver deduplication after interruption.** A durable fixture receiver inserts one effect row under a
  unique idempotency key on a separate connection, outside the handler transaction. The old process applies
  that effect and waits before completion. One test sends SIGTERM; another sends SIGSTOP, lets the real
  30-second lease expire without editing it, waits for the replacement to complete, then sends SIGCONT.
  Both assert two deliveries of the held item but one receiver effect, and completion by the replacement.
  The resumed process is observed for three seconds with the completed row unchanged; its waiting handler
  does not attempt a late completion. The separate artificial-expiry test above exercises rejected stale
  completion writes. This is a receiver contract example, not a guarantee
  that an arbitrary external API deduplicates requests.
- **Statement in flight.** The old handler inserts a transactional row and waits in `pg_sleep(120)`.
  The test observes the active statement before SIGTERM while the replacement runs. It asserts eventual
  removal of the statement, rollback of that row, and recovery by the replacement. Cancellation need not
  immediately stop PostgreSQL: the test uses the normal 30-second lease and its server-side transaction
  deadline, and allows up to a minute to observe cleanup. The existing late-write test still deliberately
  changes lease expiry and proves a different interleaving.
- **Migration contention budget.** A test holds the first migration open, observes another process fail
  startup with `spring.flyway.lock-retry-count=1`, then starts a process with a budget of 10 and releases
  the lock after observing contention. Both surviving processes start. This tests bounded failure and
  recovery after release; it does not benchmark long migrations.

For installations that require identical image content across replacement pods, set
`backend.requireImageDigest=true` and `backend.image.digest=sha256:<64 lowercase hex digits>`.
Rendering then refuses a missing or malformed digest, including with schema validation disabled.
The rendered image includes that digest even when a tag is also set. The opt-in defaults to false for
existing local-image installations; tag-only replacements still have no different-build compatibility
qualification. A digest pins image content, not configuration or mutable external services.

`backend.migrationLockRetryCount` exposes Flyway's bounded lock budget: default 50, allowed integers
0–120. It renders `SPRING_FLYWAY_LOCK_RETRY_COUNT`; old release values missing the field use 50.
Flyway retries approximately once a second per lock acquisition. Zero requests no retry; negative
(unlimited) values are refused. This is **not** a bound on migration SQL or total startup: migrations
acquire locks separately, and connection setup and SQL execution add time. Size
`backend.probes.startup.periodSeconds × failureThreshold` for the complete expected startup, including
all migrations; the default is 180 seconds. A retry budget cannot make an incompatible migration safe,
and a process that exhausts it fails startup and can be restarted by Kubernetes.

**Kubernetes fixture run, 2026-11-15 (#189).** On Kind `owl-mast-om0102` (Kubernetes 1.36.4),
namespace `owl-mast-pr189-r16b`, two pods ran the real application plus the integration fixture against a
fresh PostgreSQL. A separate seeder queued 604 follow-ups and three audit publications. While work was
in flight, `kubectl delete pod --wait=false` removed pod UID `191fe2fc-9427-4317-b45f-dd53690b9468`,
then a `policy/v1` Eviction removed a distinct live pod, UID `903fa8ae-12eb-4e13-bd7a-1ff45f018358`.
The worker Deployment restored two running pods after each fault. Successful items advanced 8→12 across
the deletion and 13→17 across the eviction; eventually all 607 succeeded, with 604 distinct receiver
effects, 604 deliveries, and three audit events. No duplicate delivery happened in this run; the JVM
interruption tests above deliberately force that window. Workers were then scaled to zero; the isolated
namespace and database were retained for inspection.

This was an integration-fixture Deployment with two replicas, not the production chart (which remains
single-replica `Recreate`). It used synthetic handlers and stub identity, image
`owl-mast/overlap-fixture:pr189-r16`, local image ID
`sha256:480b75d2061484ee4716ac1aa2c3ecc84c94f8fda67fd206e044c3f01bc4d9ad`.
It qualifies those deletion/eviction queue-recovery cases only, not node-pressure eviction, production
routing/identity, or chart rollout behavior. Probe script and raw evidence are retained under the
coordinator's ignored `.bmad-work/pr189-cluster-*` files. An initial probe mistakenly selected the already
terminating pod for eviction; it is excluded from this eviction claim and was rerun on the fresh namespace.

Remaining qualification limits:

- Process tests use two JVMs on Testcontainers. Cluster fixture evidence is recorded separately below;
  it does not turn these tests into a production chart rollout qualification.
- No node was cut off from the API server. The available Kind cluster has one node. No prolonged partition with
  a replacement on another node, or rollout during that partition is qualified. Isolating this cluster's
  only control-plane node would also affect unrelated retained fixtures. These remain unaccepted gaps.
- Two different backend builds sharing one schema are not tested. Use the digest guard for same-content
  replacement; it does not establish compatibility across an intentional image change.

## Persistent volumes and retention (T3)

The bundled PostgreSQL is a single-replica `Recreate` Deployment mounting one explicit
`PersistentVolumeClaim` (`<fullname>-postgresql-data`, default 10Gi, `ReadWriteOnce`). The claim
carries `helm.sh/resource-policy: keep`, so `helm uninstall` leaves it (and its data) in place and
`helm upgrade` never recreates it. `postgresql.persistence.storageClass`, `accessModes` and a smaller `size`
are immutable on the existing claim: Kubernetes rejects such a change, and `helm upgrade` then fails at the
claim after earlier objects were already applied (roll back with `helm rollback`). Keep these three values as
installed; to grow the volume, raise `size` only where the StorageClass allows expansion. The chart does not
compare them with the live claim at render time: an empty `storageClass` is recorded on the claim as the
cluster's default class name, so a textual comparison would refuse every unchanged upgrade. The pod sets
`fsGroupChangePolicy: OnRootMismatch`, so volume ownership is fixed once and not by a recursive walk of the data
directory on every start, and the pod's `checksum/init` annotation hashes the init scripts only, so a chart
version bump does not recreate the database pod. Nor does a `commonLabels` edit: the PostgreSQL pod template
carries none of them (a render test compares the whole pod template across such an edit). Reinstall with
`--set postgresql.persistence.existingClaim=<fullname>-postgresql-data` to continue with the same
data; the chart never adopts an arbitrary claim without that explicit selection. Choose a
StorageClass whose reclaim policy is `Retain` for the PersistentVolume as well; the local
qualification used the run-owned `owl-mast-local-retain` class. **Snapshot cadence and provider are
not decided here**: local node storage is disposable, and no backup is implied.

## Frontend and routing values (T2/T4)

`frontend.*` deploys the independent shell artifact delivered by OM-01.04 (`frontend.image.*`;
disabled by default, and enabling without a tag or digest fails rendering). `frontend.containerPort` is fixed
at 8080: the image's nginx listens there and reads no other port, so the schema and the templates refuse any
other value; `frontend.service.port` (default 80) is the port to change. Build the image from
`frontend/Dockerfile` (Node 24.21.0 build stage, `nginxinc/nginx-unprivileged:1.31.7-alpine` runtime,
port 8080, UID 101) and verify its contract with `scripts/verify-frontend-artifact.sh`:

```sh
docker build -t owl-mast/frontend:0.1.0 frontend
scripts/verify-frontend-artifact.sh                      # non-root, SPA fallback, /owlmast-config.json, prefix guard, no JDK
helm upgrade --install owl-mast deploy/helm/owl-mast --set frontend.enabled=true --set frontend.image.tag=0.1.0 …
```

The container receives `OWLMAST_API_PATH_PREFIX` (= `routing.apiPathPrefix`) and republishes it to
the shell as `/owlmast-config.json`; the shell then calls `GET <prefix>/compatibility` on the same
origin, so the route for `routing.apiPathPrefix` must reach the backend's `/api`. The chart refuses every
`routing.apiPathPrefix` other than `/api` at render time, so a prefix the image would refuse never reaches
a pod. A container started outside the chart refuses to start on a prefix that is malformed, is the root,
or names a path the image serves or a page of the shell
([frontend.md, Image configuration](frontend.md#image-configuration) has the rule), and it answers 404
below the prefix: a request that reaches the frontend
there was misrouted, and the shell then reports that no descriptor was published instead of a healthy
backend. Before enabling or upgrading the frontend, run the pre-rollout pair check against the artifacts
being rolled out ([api-compatibility.md](api-compatibility.md)). `--frontend-url` reads the contract the
frontend image publishes at `/api-compatibility.json`; without it the script reads the manifest of the
checkout it runs from, which says nothing about an image built from another commit:

```sh
scripts/check-api-compatibility.py --frontend-url <candidate-frontend> --backend-url <candidate-or-deployed-backend>   # exit 1 = do not roll out
```

`<candidate-frontend>` is the image about to be rolled out, not the public origin, which still serves the
previous frontend (for example `docker run --rm -p 127.0.0.1:8081:8080 <image>` and
`http://127.0.0.1:8081`); [api-compatibility.md](api-compatibility.md) has the details. If an endpoint
needs credentials, pass the `Authorization` header value through `OWLMAST_COMPAT_BACKEND_AUTHORIZATION` /
`OWLMAST_COMPAT_FRONTEND_AUTHORIZATION` or `--backend-authorization-file` / `--frontend-authorization-file`,
never in the URL or as an argument; they are sent over `https` or to a loopback address only and are
never printed.

This story proves the image contract and the browser → backend path locally and in CI; deploying
the frontend image onto the Kind target remains a live qualification step that the script does not run
(deferred work: #158). `routing.*` defines the path
contract: `/api` routes to the backend, `/` to the frontend. The chart renders no rewrite, so the
prefixes are pinned to what the artifacts serve: `routing.apiPathPrefix` is exactly `/api` (the shell receives
this value and calls `/api/compatibility`, the path the backend serves; a sub-path such as `/api/v1` would give
404 on every call), `routing.actuatorPathPrefix` is `/actuator` or below `/actuator/`,
`routing.frontendPathPrefix` is `/`; anything else fails rendering (which also keeps the three prefixes
disjoint). The actuator is **not routed** by default: health, liveness and readiness serve the kubelet inside
the cluster, are unauthenticated, and readiness makes an outbound call to the identity provider (cached for
5 s). `routing.exposeActuator` (default `false`) adds the `routing.actuatorPathPrefix` rule to the Ingress or
HTTPRoute on purpose. No exposure is rendered by
default. Two mutually exclusive mechanisms exist; enabling both is refused as ambiguous:

- **Gateway API (first-class):** `routing.gateway.enabled=true` renders one stable
  `gateway.networking.k8s.io/v1` `HTTPRoute`, and only where the capability
  `gateway.networking.k8s.io/v1/HTTPRoute` is served (otherwise rendering fails naming it; for `helm template`
  pass `--api-versions gateway.networking.k8s.io/v1/HTTPRoute`), attached to the operator-supplied parent Gateway(s)
  (`routing.gateway.parentRefs[].name`, optional `namespace`, `sectionName`, `port`; at least one entry
  is required), and with `hostnames`. `routing.gateway.hostnames` is required: a route without hostnames
  attaches to every hostname of the referenced listener(s), including other tenants' hostnames on a shared
  Gateway; `routing.gateway.allowAllListenerHostnames` (default `false`) acknowledges that explicitly for a
  Gateway dedicated to this installation. IP addresses are refused as hostnames (the Gateway API Hostname type
  forbids them, although its pattern does not), and an omitted parent `namespace` counts as the release
  namespace when repeated parents are compared. Prerequisites the operator provides and qualifies: the
  Gateway API CRDs (standard channel, `v1` HTTPRoute), a GatewayClass and controller, the Gateway with
  its listeners and any TLS. The chart validates the exposed inputs against the stable HTTPRoute `v1`
  contract (hostnames as lowercase DNS names with an optional leading `*.` wildcard, at most 16 and 253
  characters each; parent `namespace` as a DNS label, `sectionName` as a DNS subdomain, `port` 1–65535, at
  most 32 parents, a distinct `sectionName` on every repeated parent; path prefixes absolute, valid
  characters only, none of `//`, `/./`, `/../`, `%2f`, `%2F`, `#`) and refuses rendering otherwise, never
  coercing values. Rendered routes are validated offline in the deploy test suite against the pinned
  upstream schema (`deploy/tests/fixtures/gateway-api/`, Gateway API v1.4.0 standard CRD, origin and SHA256
  recorded) for the ordinary schema constraints; the CRD's CEL rules are enforced by the chart for the
  inputs it exposes, in the values schema and again in the templates (the suite runs the invalid inputs with
  `--skip-schema-validation` so the template layer is exercised by itself). The chart's copy of the CEL rules
  has not been compared with a real API server that has the CRDs installed: that server-side acceptance check
  is not run anywhere yet (deferred, see [Qualification status](#qualification-status)). This is manifest
  validation, not controller acceptance: listener permission, hostname
  intersection and route status are decided by the operator's Gateway, and no Gateway controller runs on
  the qualification target (the API group is absent there), so manifest support is distinct from
  controller/runtime qualification.
- **Ingress (compatibility):** `routing.ingress.enabled=true` requires an explicit host: a lowercase DNS name
  with an optional leading `*.`, labels of at most 63 characters, no scheme, port or path. `routing.ingress.tls`
  entries are typed and need both `hosts` and `secretName`; when present, one must cover the host (exactly, or
  by a one-label wildcard). An entry without `secretName`, or a TLS block that does not cover the host, would
  make the controller serve its default certificate, so both fail rendering; annotations are string-valued. The Kubernetes
  Ingress API is frozen (GA, no removal planned) while the project recommends Gateway API; the retirement
  of the ingress-nginx controller is a separate fact and does not remove the API.

Public origins, TLS and session behaviour are OM-02.01.

## Commands

```sh
# packaging checks (lint, four renders, negative validation) with the qualified Helm; a cached Helm or
# kubectl in OWLMAST_TOOLS_DIR is re-verified (archive/binary checksum and version) on every run, and hosts
# other than linux-amd64 must name qualified binaries through OWLMAST_HELM / OWLMAST_KUBECTL
scripts/verify-install-package.sh

# backend image from the built jar
./gradlew :backend:bootJar && docker build -t owl-mast/backend:0.1.0 -f backend/Dockerfile backend
scripts/verify-backend-image.sh   # jar name vs version, docker build, UID 10001, qualified JDK, read-only-root start with the chart's environment up to the first database connection

# install (secrets must exist first; see examples/)
helm upgrade --install owl-mast deploy/helm/owl-mast -n owl-mast -f deploy/helm/owl-mast/examples/bundled-bundled.yaml --wait

# runtime qualification on the disposable Kind target (explicit run-local kubeconfig)
KUBECONFIG=<run>/kubeconfig OWLMAST_HELM=<run>/helm EVIDENCE_DIR=<private> scripts/qualify-local-install.sh all
# first-enable is not part of `all`: it needs its own identity and a release name whose volume does not exist yet;
# it ends with the retirement of the Keycloak bootstrap admin
KUBECONFIG=<run>/kubeconfig OWLMAST_HELM=<run>/helm EVIDENCE_DIR=<private> OWLMAST_FOLLOWUP_RUN_ID=<id> FE_RELEASE=<owl-mast-…> \
  scripts/qualify-local-install.sh first-enable
```

The qualification script first rejects target overrides its static manifests and the chart's
naming cannot honour (`NS`/`EXT_NS` other than the manifest namespaces, a release whose chart fullname
differs from its name) before any cluster call, then preflights every resource the selected steps
consume or change (StorageClass, namespaces, quotas, every consumed Secret, fixture objects, retained
claims, every renderable resource of each affected release including hook ConfigMap/Job, Ingress,
HTTPRoute and NetworkPolicies, and the selected pods' controller chain pod → ReplicaSet → Deployment by UID, label and
readability): an existing object must carry the expected identity's label exactly, an unreadable
ownership (denied, outage, partial discovery, unexpected output) refuses, and only an explicit API
NotFound (`--ignore-not-found` exit 0 with no object) counts as absence. The one optional kind,
HTTPRoute, counts as absent only when the typed `/apis` APIGroupList returned by the responding API server
advertises no `gateway.networking.k8s.io` group at that read, and only after the whole document validated
against the metav1 contract (kind `APIGroupList`, apiVersion `v1`, every group an object with a non-empty
string name, a non-empty versions list whose `groupVersion` equals `name/version`, a coherent
preferredVersion, no duplicate names); a malformed document is an error, never absence. When the group is
listed, `/apis/gateway.networking.k8s.io/v1` must be the `APIResourceList` with apiVersion `v1` and exactly
that `groupVersion`, listing `httproutes` of kind `HTTPRoute` whose own `group`/`version`/scope fields, if
present, agree with it; stale backend, 503, 403, malformed, contradictory or wrong documents refuse.
`kubectl api-versions` is not used: its listing silently drops versions whose aggregated discovery is Stale.
Nothing is mutated when preflight refuses. This is the server's registration view at the moment of the read
(the aggregator lists registered APIServices and auto-registered CRD groups whether or not they are
available); it is not an atomic proof about CRD storage or future registrations. `deploy/tests/test_discovery_client.py`
drives the real kubectl against a loopback discovery server to prove these outcomes end to end. Pod replacement deletes only the pods whose chain was proven
immediately before, by name. It then prepares the run-owned StorageClass, namespaces and quotas (6 CPU / 12Gi /
40Gi combined), generates synthetic secrets into the cluster only, deploys synthetic external
PostgreSQL/Keycloak fixtures (plaintext by design: every such install passes `identity.external.allowInsecureIssuer=true`
and the matching `allowInsecureTransport=true` explicitly; each Secret is created together with its ownership label in
one `create` call, and a replicated Secret is written with `create`, never `apply`, so an interrupted run leaves no
unlabelled Secret and an existing Secret is never overwritten), installs all four combinations sequentially, proves pod replacement,
uninstall retention, reinstall with the existing claim and upgrade, and exercises the failure paths
(Secret missing a key, non-existent realm). Since 2026-11-12 it also requires every migration of the checkout
to be recorded as applied in `flyway_schema_history` by the application principal `owlmast_app`, and every table
of the `jobs` and `audit` schemas to be owned by it (earlier it looked for V001 only); and in every combination
it proves durable work on the database that backend uses: it writes a synthetic audit-publication intent and
its `audit.publish` work item as the application principal for the tenant `qualification`, and requires the
installed backend to claim the item under its own lease, publish the intent into `audit.event` and mark the
item `SUCCEEDED` within `DURABLE_WORK_TIMEOUT` (120 s). Those rows are synthetic and stay in the database.
`first-enable` ends by retiring the Keycloak bootstrap admin: the admin must be injected before; `helm upgrade
--wait` runs with `identity.keycloak.bootstrapAdmin.enabled=false` and the Secret value pointed at a name that
does not exist; afterwards neither Secret name occurs in the release's Deployments or running pods, Keycloak
and the backend are ready, and the Keycloak role and database are unchanged. It does not create a permanent
administrator or delete the temporary user. The provisioning hook is proven without reading its Job: Helm
deletes the hook Job and its ConfigMap once the hook succeeded, so their status and log no longer exist after a
successful upgrade. Instead, after every provisioning upgrade (the `bundled-bundled` step and both `first-enable`
upgrades) the script reads the release record with `helm status -o json` and requires the deployed revision to list
the hook Job `<fullname>-postgresql-provision-keycloak` for `pre-upgrade` with `last_run.phase` `Succeeded` and a
`last_run.started_at` no earlier than the start of that upgrade; this is what shows the hook was rendered and run,
since every other check below also passes when no hook ran. For a provisioning upgrade on an initialised volume (the `bundled-bundled` step and the
`first-enable` retry) the script records `pg_roles.oid` of the Keycloak role and `pg_database.oid` and owner of
the Keycloak database before the upgrade, read as the Keycloak principal, and requires the same values after it
(a dropped and recreated role or database gets a new oid). It also requires that `helm upgrade --wait` returned
0 (Helm fails the upgrade when a pre-upgrade hook fails), that `helm status` shows a higher revision as
`deployed`, that the Keycloak schema is still present, and that the hook Job and ConfigMap are absent
afterwards. An unreadable identifier, or a hook object that is still present, fails the step. On the first enable
the role and database are absent before the upgrade and readable by the Keycloak principal after it. The retry no
longer shows from a Job log that the grants were re-applied; the privilege and CONNECT checks run after the first
enable. The backend image identity is read from the one Running,
non-terminating backend pod, and an empty `imageID` fails the check. AC3 checks fail the step even when the
caller runs them under `||` (first-enable). Isolation evidence requires the PostgreSQL CONNECT denial
for the other database together with a successful same-principal control connection; transport or
authentication failures fail the check. Secret inventories list metadata and key names only; no
Secret value is ever requested in a persistable form. Evidence is written to the private evidence
directory, never to the repository.
