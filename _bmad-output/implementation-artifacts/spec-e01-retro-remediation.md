---
title: 'E01 retrospective remediation (E01-R-01 … E01-R-13)'
type: 'chore'
created: '2026-11-12'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: '98496d6673250cb51710973359c2c3c51119de10'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-retro-2026-11-12.md'
  - '{project-root}/docs/engineering-conventions.md'
  - '{project-root}/docs/durable-work-and-audit-contract.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The E01 retrospective (`epic-1-retro-2026-11-12.md`, analysed at `98496d6`) ended "accepted-with-open-items": findings marked **fix** and action items E01-R-01 … R-13 are open, the scripted Kind qualification predates OM-01.03, and 47 spec-review threads on PR #110 are untriaged.

**Approach:** One branch (`t3/e01-retro-remediation` from `origin/main`) and one PR, not merged. Re-verify each finding against the code, implement every **fix** finding and R-02 … R-07, R-10, R-11; draft the spec reconciliations (R-08, R-09) in the repo for the owner to decide; run the Kind qualification at the branch head (R-01) and record its true status; fix the spec statuses (R-13, repo part); write a ready-to-run issue list for R-12.

## Boundaries & Constraints

**Always:**
- Commit the retro document at `_bmad-output/implementation-artifacts/epic-1-retro-2026-11-12.md`.
- Report real command output; a qualification that cannot complete is recorded as such, never as a pass.
- R-09 wording is marked "accepted deviation — pending owner confirmation".
- Kind work uses only a run-local kubeconfig for cluster `owl-mast-om0102` (context `kind-owl-mast-om0102`); the cluster is never deleted.
- `./gradlew build`, `scripts/verify-quality-gates.sh`, frontend lint/typecheck/test/build/e2e and `scripts/verify-install-package.sh` pass before the PR opens.
- Executable bits via `git update-index --chmod=+x`.

**Never:**
- Merge the PR; change branch protection or rulesets; close or edit issues; change Project Status; create GitHub issues; resolve or reply to threads on any PR (including #110).
- Fix findings marked defer/accept unless one of the items above requires it.
- Remove or edit a frozen line of `contract-shape-v1.txt`.

</frozen-after-approval>

## Code Map

- `backend/src/main/java/com/aisquad/owlmast/jobs/api/WorkRegistration.java` -- public tenant-internal factories and constructor; frozen v1 shape, so the type stays and the grant moves to the jobs owner (R-03).
- `jobs/application/HandlerRegistry.java`, `TenantInternalOnlyDispatchAuthorization.java`, `jobs/adapter/config/JobsConfiguration.java` -- where a jobs-owned `TenantInternalGrants` allow-list is enforced at startup and at dispatch.
- `integrationTest/.../fixtures/notes/NotesFixtureConfiguration.java` -- test fixture that must supply its own grants.
- `jobs/adapter/persistence/R2dbcWorkRepository.java:367` (`dueTenants`) -- `new TenantId(...)` throws on a blank row and fails discovery (R-04).
- `backend/src/main/resources/db/migration/V002`, `V003` -- `tenant_id text NOT NULL` only; add V004 (jobs) and V005 (audit) with a non-blank CHECK.
- `platform/web/UnhandledFailureAdvice.java` -- status table by class name; add the platform exceptions (R-05). Tests: `integrationTest/.../platform/web/UnhandledFailureIT.java`.
- `bootstrap/adapter/health/SchemaBaselineHealthIndicator.java`, `bootstrap/port/SchemaBaselineRepository.java`, `bootstrap/adapter/persistence/R2dbcSchemaBaselineRepository.java` -- readiness baseline; add the PostgreSQL ≥ 17 check (R-06).
- `deploy/helm/owl-mast/values.schema.json:192` -- `frontend.containerPort`; `frontend/nginx/default.conf.template:20` listens on 8080.
- `backend/src/testFixtures/java/com/aisquad/owlmast/testing/OwlMastPostgres.java` -- container superuser is the application user (R-02). Mirror `deploy/helm/owl-mast/templates/postgresql-init-configmap.yaml:100-112`.
- `backend/Dockerfile:25`, `scripts/verify-backend-image.sh` (entrypoint check), `deploy/helm/owl-mast/values.yaml:35-48` -- Netty native access (R-07).
- `docs/toolchain-qualification.md:11,21,33-37,49,59,149,150`, `README.md:28`, `gradle/gradle-daemon-jvm.properties:1,4`, `docs/development.md`, `docs/frontend.md` -- Gradle 9.8.2/9.9.0 mix, `ubuntu-latest`, missing Playwright install step.
- `backend/src/test/java/com/aisquad/owlmast/architecture/FeatureModuleRules.java`, `…NegativeTest.java`, `archfixtures/**`, `scripts/verify-quality-gates.sh`, `docs/engineering-conventions.md` -- layering table vs rules (R-10).
- `.github/workflows/ci.yml`, `scripts/verify-install-package.sh:63-65` -- no shell/Python lint; unpinned PyYAML/jsonschema (R-11).
- `scripts/qualify-local-install.sh` (`check_shared_postgres` asserts only V001; no bootstrap-admin retirement step), `deploy/tests/test_qualify_script.py`, `docs/installation.md:8,21,64,170,275`, `deferred-work.md` entry 2 (R-01).
- `_bmad-output/planning-artifacts/epics/owl-mast-2026-11-05/epic-01.md`, `TASKS.md`, `epics.md:187`, `sprint-change-proposal-2026-11-08.md` -- R-08, R-09.
- `spec-om-01-0{1,2,3,4}-*.md`, `spec-gh-116-review-cycle-*.md` -- `status` frontmatter (R-13).

## Tasks & Acceptance

**Execution:**
- [x] R-03 `jobs/application/TenantInternalGrants.java` (new) + registry, default recheck, configuration, fixture, tests, contract doc -- only work types the jobs owner granted may register as tenant-internal; module rule and gate case.
- [x] R-04 `V004__jobs_tenant_id_not_blank.sql`, `V005__audit_tenant_id_not_blank.sql`, `R2dbcWorkRepository.dueTenants` skip-and-log, tests.
- [x] R-05 `UnhandledFailureAdvice` -- 403 denial, 500 scope, 503 capacity, 504 deadline; tests.
- [x] R-06 PostgreSQL ≥ 17 in the `schemaBaseline` readiness indicator; `frontend.containerPort` pinned to 8080 in the schema; tests and docs.
- [x] R-02 `OwlMastPostgres` -- provisioning superuser plus a non-superuser owner role the application, Flyway and the scheduler use; test asserting it.
- [x] R-07 Re-run the Gradle wrapper checks and correct the evidence; README and daemon-jvm comment; `--enable-native-access=ALL-UNNAMED` in the image entrypoint; runner name, CI job list, Playwright install step.
- [x] R-10 Layering rules with negative fixtures and gate cases; conventions doc (table, `platform/authorization`, `platform/web`, Lombok annotations in use).
- [x] R-11 `scripts/verify-script-lint.sh` (pinned shellcheck and ruff), CI job, pinned `deploy/tests/requirements.txt`.
- [x] R-08 / R-09 `epic-01.md`, `TASKS.md`, `epics.md`, sprint change proposal; per-thread disposition table for the PR body.
- [x] R-13 spec `status` frontmatter.
- [x] R-12 `e01-deferred-issues-to-create.md`.
- [x] R-01 qualification step for bootstrap-admin retirement and OM-01.03 evidence; run `all` + `first-enable`; update `docs/installation.md` and `deferred-work.md`.

**Acceptance Criteria:**
- Given a feature handler that registers an ungranted type as tenant-internal, when the context starts, then startup fails naming the handler and type, and the default recheck denies it.
- Given a `jobs.work_item` row with a blank tenant, when a wake-up runs, then the other tenants' work is still processed and the skip is logged; given V004/V005, a blank `tenant_id` insert is rejected.
- Given a controller that raises a platform denial, scope or blocking exception, when the advice answers, then the status is 403, 500, 503 or 504 with the problem envelope and no exception detail.
- Given a PostgreSQL server older than 17, when readiness is read, then `schemaBaseline` is DOWN.
- Given `frontend.containerPort` other than 8080, when the chart is rendered, then validation fails.
- Given the integration suite, when it runs, then migrations and the scheduler run as a role that is not a superuser.
- Given a layering or lint violation, when the gates run, then the matching gate fails naming it.

## Implementation Notes

Implemented directly in this session (no implementation subagent): the session ran as a delegated child with the investigation already in context.

- **Approval.** The delegating request fixed the scope, the single-PR shape and the "implement, then open one pull request" instruction, so the plan checkpoint was taken as approved. The spec is over the 1,600-token guideline because the request bundles eleven action items on purpose.
- **R-03.** `TenantInternalGrants` (jobs.application, `audit.publish` only). Enforced three times: `HandlerRegistry` refuses an ungranted tenant-internal registration at startup; `TenantInternalOnlyDispatchAuthorization` checks the grant again at dispatch; the registry's startup copy of a registration is what dispatch and enqueue use. `DurableWorkContractTest` names the boundary (no production class outside jobs touches the grants; only jobs and access implement or hand out a `DispatchAuthorization`).
- **R-04.** V004/V005 add the checks `NOT VALID` and validate them when no stored row breaks them. Discovery sorts undecodable tenant ids last and warns once per distinct value. V004/V005 must not be edited again: they are applied in the retained Kind databases, and Flyway validates their checksum.
- **R-05.** Exact-class table in `UnhandledFailureAdvice`; 403 / 500 / 503 / 504.
- **R-06.** `SchemaBaseline.serverVersionNumber` read with the baseline; readiness DOWN below PostgreSQL 17, and `WorkScheduler` claims nothing until the server is confirmed as supported (a scheduled task ignores readiness). `frontend.containerPort` is `const 8080` in the schema and refused in the templates.
- **R-02.** `OwlMastPostgres` subclasses the container so the image initialises as `owlmast_provisioner` and everything else connects as `owlmast` (no privileged attribute, owner of its database). One test needed the provisioner: reading `shared_preload_libraries`.
- **R-07.** The rerun showed the distribution checksum was already 9.9.0's and the wrapper jar still 9.8.2's; the jar was regenerated. Gradle 9.9.1 exists; the pin stays on 9.9.0.
- **R-10.** Table aligned with the code (api lowest; domain may use own api; api may use another api), rules added for every row, fixtures for every rule.
- **R-11.** `scripts/verify-script-lint.sh`, `ruff.toml` (E9, F, B), pinned and hashed requirements; the deploy suite runs in its own hash-installed virtual environment.
- **R-01.** Script: every migration applied by `owlmast_app`, `check_durable_work` in all four combinations and first-enable, bootstrap-admin retirement at the end of first-enable. Runs and results: see the pull request and `docs/installation.md`.
- **R-01 result.** `all` passed at `4fc415b` (141 ok) and `00b4853` (145 ok). `first-enable` at `00b4853` passed through the retry and failed at the retirement: the Keycloak pod rolled beside the old one and never became ready. Chart fixed (surge-free rolling update; `type: Recreate` cannot be upgraded to in place), retirement rerun on the same release: passed. One uninterrupted `first-enable` on the fixed chart was not run: the namespace's storage quota is full and nothing was deleted.
- **Surprise.** A blocking call that throws after `BoundedBlocking` gave up on it is logged by Reactor with its stack trace (`onErrorDropped`), which bypasses `SafeFailure`. Not fixed here (no production caller yet); recorded in the ledger and the issue list (X4).

## Spec Change Log

## Review Triage Log

Review of the diff at `4fc415b` by three context-free reviewers (blind hunter BH, edge-case hunter EC, verification gap VG). Verdict, evidence, route.

| # | Finding | Verdict | Evidence | Route |
| --- | --- | --- | --- | --- |
| 1 | BH/EC/VG: the "fixed at 8080" comment was also added above `backend.containerPort` | medium | `values.yaml`: a replace matched both blocks; the backend port is not fixed | patch: removed |
| 2 | BH/EC: the default recheck still allowed any registration that says tenant-internal | medium | `TenantInternalOnlyDispatchAuthorization` did not read the grants, against this spec's first acceptance criterion | patch: the recheck takes the grants; unit test |
| 3 | BH/EC: readiness DOWN on PostgreSQL < 17 does not stop the scheduler; the reason was logged at every probe | medium | `WorkScheduler` is a scheduled task; `unsupportedServer` logged per call | patch: scheduler precondition, log once; `WorkSchedulerIT`, health test |
| 4 | BH/EC: undecodable tenant ids take a slot of the 100-tenant limit and warn every second | medium | `dueTenants` applied the limit before the skip | patch: such ids sort last; warning once per distinct value, bounded |
| 5 | BH/EC: the database check is narrower than `TenantId` (U+001C–U+001F) | low | true; the gap row is still skipped by discovery | patch (docs only): the contract states the gap. V004's comment is unchanged because the file is applied on the qualification target |
| 6 | BH: a check left NOT VALID is invisible afterwards; no query for the operator | low | only a one-off Flyway warning | patch: queries in the contract document |
| 7 | BH: R-01's result is recorded nowhere | — | the run was in progress when the diff was taken | done with this change: `docs/installation.md`, ledger |
| 8 | BH: this spec said in-review with unticked tasks and named a step that does not exist | low | true at that commit | fix is to this build's spec: rejected as a finding, corrected in passing |
| 9 | BH: the PR #110 disposition table is not in the repository | medium | `epic-01.md` pointed at an unnumbered pull request | patch: `e01-r08-pr110-thread-dispositions.md`, linked |
| 10 | BH: story specs set to done ahead of the evidence | false | the request asks for exactly this (E01-R-13, repo part); the owner decides the verdict | rejected |
| 11 | BH: `retire_bootstrap_admin` read container env only | medium | init containers, envFrom, volumes and the running pods were not read | patch: both Secret names searched in the release's Deployments and pods; stub test |
| 12 | BH/EC: `check_durable_work` is not exactly the rows `AuditedMutations` commits; missing in two combinations; rows accumulate | low | attempt limit 5 is deliberate; the two combinations were unchecked | patch: wording, the check in all four combinations, the accumulation stated |
| 13 | BH/EC: the pin check compared two packages and installed into the ambient interpreter | medium | transitive versions floated when the short-circuit fired | patch: hash-installed virtual environment, stamped with the requirements sha256 |
| 14 | BH/EC/VG: lint scope narrower than its comment; no negative proof | medium | four globs; no injected violation | patch: name-based discovery, comment states what is not linted, gate case in `verify-quality-gates.sh` |
| 15 | BH: nothing stops the Gradle drift from recurring | medium | retro T1 happened exactly this way | patch: `GradleWrapperDocumentTest` |
| 16 | BH: two mapped exceptions untested; finality assumed; wrapped failures answer 500 | low | constructors are package-private; cause is ignored by design | patch: `UnhandledFailureAdviceTest` (table, finality, cause) |
| 17 | BH: the fixture's role setup is a hand copy of the chart's | low | no comparison existed | patch: `OwlMastPostgresTest` |
| 18 | BH/EC: the issue-creation loop reports success on failure and duplicates on rerun | medium | no status check, no title check | patch: `set -euo pipefail`, explicit checks, skip existing titles |
| 19 | EC: a lambda bean can supply `DispatchAuthorization` past the `implement` rule | low | ArchUnit sees no implementing class | patch: no method outside jobs/access returns the port |
| 20 | EC: `pins_installed` malformed-file path | false | the function no longer exists (row 13) | rejected |
| 21 | EC: the unpinned-install test missed `pip3`, `pipx`, `uv`, continuation lines | low | true | patch |
| 22 | EC: `expected_migrations` empty reads as "all applied" | medium | the loop body never runs | patch: explicit failure; stub test |
| 23 | EC: only three named tables were checked for ownership | low | a later table would pass | patch: any table of the two schemas |
| 24 | EC: `blockingCapacity` ignored a failed `await` | low | a slow runner could answer 200 | patch |
| 25 | VG: nothing pins dispatch and enqueue to the startup registration | medium | the unit test stopped at the registry | patch: `DurableWorkIT.dispatchAndEnqueueUseTheRegistrationReadAtStartup` |
| 26 | VG: V004/V005 never ran against stored blank rows | medium | every test started from a clean schema | patch: `TenantIdConstraintMigrationIT` |
| 27 | VG: the external-bundled durable-work call had no stub test | medium | filed as defer | patch instead: all four steps run in the stub world |
| 28 | VG: the native-access smoke check may be vacuous | medium | confirmed by running the image with and without the option: no warning either way before the first database connection | patch: check removed, limitation stated in the script |
| 29 | BH: `JobsConfiguration` accepts any `TenantInternalGrants` bean, guarded only by ArchUnit | low | by design: test fixtures need it, production code cannot reach the type | rejected (unlikely in use; the fix adds a mechanism) |
| 30 | BH: `jsonschema==4.19.2` is old and pinned without a reason | low | it is the version the suite was run against | patch: reason stated in `requirements.in` |

No finding routed to intent_gap or bad_spec; no loopback.

## Design Notes

**R-03.** `WorkRegistration`'s public members are part of the frozen v1 shape, so they stay. The privilege moves from "what a handler says about itself" to "what the jobs owner granted": `TenantInternalGrants` lives in `jobs.application`, which the existing isolation rule already makes unreachable from other production features. Test fixtures (outside the rule's scope) supply their own grants bean.

**R-10.** The table is aligned with the code where the code is right, and the rules are extended to enforce the result: `api` is the lowest layer of a feature (published values and interfaces; it may use another feature's `api`, as `audit.api` uses `jobs.api` bounds), and `domain` may use its own `api` values (`AuditRecord` is built from envelope types). `api` depending on `domain` would put internal types into a published contract, so that row is removed.

## Verification

**Commands:**
- `./gradlew build` -- expected: BUILD SUCCESSFUL
- `scripts/verify-quality-gates.sh` -- expected: all gates fail correctly
- `scripts/verify-script-lint.sh` -- expected: clean
- `scripts/verify-install-package.sh` -- expected: OK
- `scripts/verify-backend-image.sh` -- expected: ok
- `cd frontend && npm ci && npm run lint && npm run typecheck && npm run test:coverage && npm run build && npx playwright test` -- expected: pass
- `scripts/qualify-local-install.sh all`, then `first-enable` (which ends with the bootstrap-admin retirement) -- expected: steps complete, or the exact failure recorded
