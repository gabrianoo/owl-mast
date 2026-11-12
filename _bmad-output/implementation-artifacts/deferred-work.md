# Deferred work

- source_spec: `_bmad-output/implementation-artifacts/spec-gh-109-resolve-review-findings.md`
  summary: Mount an operator-supplied CA trust (Secret) for external PostgreSQL so `sslMode=verify-ca|verify-full` work for JDBC (Flyway, Keycloak) and R2DBC, then restore `verify-full` in `examples/external-external.yaml`.
  status: still deferred after review cycle 1 (2026-11-11). The chart now REFUSES `verify-ca`/`verify-full` at render (they rendered and then crash-looped), so the gap is fail-closed; `require` encrypts without authenticating the server. Owner decision: ship the CA trust mount (values for a CA Secret, `sslrootcert`/`sslRootCert` on the JDBC and R2DBC URLs, Keycloak `KC_DB_URL`), with a TLS PostgreSQL fixture to qualify it.
  evidence: The chart accepts verify-ca/verify-full since OM-01.02 but mounts no root certificate; pgjdbc's default LibPQFactory needs `~/.postgresql/root.crt` or `sslrootcert`, which the read-only backend (no home directory) does not have. Pre-existing; round-1 review finding B13 of PR #109's follow-up.

- source_spec: `_bmad-output/implementation-artifacts/spec-gh-116-review-cycle-1.md`
  summary: Rerun the owner-run Kind qualification (`scripts/qualify-local-install.sh all` plus `first-enable`) against chart 0.2.0 and record the evidence, including the retirement of the Keycloak bootstrap admin (`identity.keycloak.bootstrapAdmin.enabled=false`).
  status: partly resolved 2026-11-12 (E01-R-01). `all` passed for chart 0.2.0 three times that day: at `f188d51` (131 ok, PR #116, which this entry had not recorded), at `4fc415b` (141 ok) and at `00b4853` (145 ok, 0 FAIL), the last two with the OM-01.03 migrations applied by `owlmast_app` and durable work published by the installed backend. `first-enable` at `00b4853` passed through the retry on a fresh volume, then failed at the new bootstrap-admin retirement: the Keycloak pod rolled beside the old one and never became ready (chart defect, fixed in `31ee127`). The retirement passed when rerun on the same release with the fixed chart. Still open: one uninterrupted `first-enable` on a fresh volume with the fixed chart (the namespace's 30Gi storage quota is used up by the three retained claims; none was deleted). Details and evidence paths: `docs/installation.md`, Qualification status.
  evidence: PR #116 thread 4543777495 and PR #109 thread 4543776353. Chart 0.2.0 changes probes, NetworkPolicies, read-only roots, the backend strategy and the hook policy; only chart 0.1.0 was qualified (2026-11-07). The run mutates the retained cluster `owl-mast-om0102` and needs an owner-authorized run window, so it was not started in this cycle. `docs/installation.md` marks the 0.2.0 qualification as pending.

- source_spec: `_bmad-output/implementation-artifacts/spec-gh-116-review-cycle-1.md`
  summary: Check the rendered HTTPRoutes and each refused input against a real API server that has the pinned Gateway API v1.4.0 standard CRDs installed (`kubectl apply --dry-run=server`, no controller), so the chart's hand-written copy of the CEL rules is compared with the upstream CEL.
  evidence: PR #109 thread 4543776368. The offline suite validates the OpenAPI schema with jsonschema and cannot evaluate CEL. A server-side check needs a cluster with cluster-scoped CRDs: either the retained Kind target (owner-authorized mutation) or a disposable Kind cluster in CI (a new CI job and its runtime budget). Owner decision on where it runs; reported as manifest/API-server acceptance, separate from controller qualification.

- source_spec: `_bmad-output/implementation-artifacts/spec-gh-116-review-cycle-2.md`
  summary: TLS for the bundled PostgreSQL: serve a certificate from the bundled instance and connect the backend and Keycloak with a verifying `sslmode`, so credentials and data do not cross the pod network in plaintext.
  evidence: PR #109 thread 4543776321 (cycle 1) was closed by documentation only, and the cycle-2 review (5866484238) noted that nothing tracked it. Today the bundled instance has no TLS and both consumers use `sslmode=disable`; isolation rests on the NetworkPolicy and the cluster network (NOTES and `docs/installation.md` say so). It depends on the CA trust mount deferred above (`sslMode=verify-ca|verify-full`), because the clients need the same trust to verify the bundled server. Owner decision: certificate source (operator-supplied Secret or a generated one) and whether it ships with the CA mount.

- source_spec: `_bmad-output/implementation-artifacts/spec-om-01-03-recover-background-work-and-record-mutation-evidence.md`
  summary: The audit actor recorded by AuditedMutations is caller-supplied and is not checked against the principal bound in the ScopeContext, so a feature could record another actor.
  evidence: AuditedMutationService.execute never compares AuditedMutation.actor with scope.principal(); AC3 requires the actor field, not its binding. Belongs with the authorization boundary (OM-02.04) or the first feature that records human actors.

- source_spec: `_bmad-output/implementation-artifacts/spec-om-01-03-recover-background-work-and-record-mutation-evidence.md`
  summary: The failure listing (FailedWorkQuery) is tenant-scoped only; AC5's "authorized operator" check needs the real authorization port.
  evidence: FailedWorkQueryService checks only that a scope is bound; the story spec forbids adding the real authorization port before OM-02.04.

- source_spec: `_bmad-output/implementation-artifacts/spec-om-01-03-recover-background-work-and-record-mutation-evidence.md`
  summary: Layering drift from docs/engineering-conventions.md: audit.api imports jobs.api (AuditIdentifiers, AuditEnvelopeContract) and domain imports api (audit.domain.AuditRecord, jobs.domain.RetryPolicy), which the layer table does not allow and FeatureModuleRules does not check.
  status: resolved 2026-11-12 (E01-R-10). The table was aligned with the code (api is the lowest layer and may use another feature's api; domain may use its own api values) and `FeatureModuleRules` now enforces every row, each with a negative fixture.
  evidence: Owner decision needed: either amend the layer table (api may use another feature's api; domain may use its own api values) or move the shared bounds and records; then add the rule to FeatureModuleRules.

- source_spec: `_bmad-output/implementation-artifacts/spec-om-01-03-recover-background-work-and-record-mutation-evidence.md`
  summary: Tenants are processed one at a time per wake-up (concatMap over tenants and items), so one slow handler delays every other tenant's work, audit publication included; bounded tenant parallelism with a configurable concurrency is needed before multi-tenant load.
  evidence: PR #111 review comment 4511332988 (WorkProcessor.runOnce). Serial dispatch is the documented v1 model (contract "Lifecycle"); parallel tenants also multiply the unpooled connections the REQUIRES_NEW audit outcome path relies on (contract, durability step 5), so the change needs the pooling decision first.

- source_spec: `_bmad-output/implementation-artifacts/spec-om-01-03-recover-background-work-and-record-mutation-evidence.md`
  summary: No lease renewal or heartbeat: every handler must finish within the handler deadline while its transaction and connection stay open across any external I/O.
  evidence: PR #111 review comment 4511333006 (WorkProcessor.run). The contract lists lease heartbeats/renewal as out of scope for v1; R5 made the deadline configurable (`owlmast.jobs.handler-deadline`) and anchored it at the claim, but a fenced `extendLease` with a heartbeat remains a design change to the lease model.

- source_spec: `_bmad-output/implementation-artifacts/spec-om-01-03-recover-background-work-and-record-mutation-evidence.md`
  summary: `audit.event` accepts UPDATE and DELETE from the application role and the publication correction overwrites the prior UNRESOLVED/FAILED row in place; an append-only history (REVOKE UPDATE/DELETE, a trigger allowing only the not-SUCCEEDED→SUCCEEDED correction, prior rows kept in `audit.event_correction`) needs a schema and role decision.
  evidence: PR #111 review comment 4511333060 (R2dbcAuditStore CORRECT_UNSUCCESSFUL). The R4 triage documented the correction as the one way a history row changes; the backend currently connects with a single database role, so grants need the role split first.

- source_spec: `_bmad-output/implementation-artifacts/spec-om-01-03-recover-background-work-and-record-mutation-evidence.md`
  summary: Tenant and module isolation for `jobs.work_item` and `audit.*` rely only on `tenant_id = current_setting('owlmast.tenant_id')` in each statement; row-level security with a tenant policy, a SECURITY DEFINER discovery function and per-module grants would catch a query that forgets the filter.
  evidence: PR #111 review comment 4511333071 (V002). R5 added tests that pin the tenant predicates of the deny write and the exhausted-lease sweep; RLS is an architecture decision (AD-3/AD-5 enforcement layer) spanning every schema, not this story's.

- source_spec: `_bmad-output/implementation-artifacts/spec-om-01-03-recover-background-work-and-record-mutation-evidence.md`
  summary: No retention for published intents (`audit.publication_intent`) or succeeded work items (`jobs.work_item`): both tables and their indexes grow without bound.
  evidence: PR #111 review comment 4511333076 (V003). Retention periods for audit evidence are a product/compliance decision (OM-16.01 operator audit scope); the technical shape is a retention work type plus a supporting partial index.

- source_spec: `_bmad-output/implementation-artifacts/spec-om-01-03-recover-background-work-and-record-mutation-evidence.md`
  summary: A failed separate-path outcome write leaves only a log line; a failure metric or readiness signal (for example `owlmast_audit_outcome_write_failures_total`) would make the gap visible to operators.
  evidence: PR #111 review comment 4511333029 (AuditedMutationService.writeOutcome). R5 put the event id and correlation id into that log line; no Micrometer meters exist in the backend yet, so the first metric should set the naming and registration convention rather than appear ad hoc here.

- source_spec: `_bmad-output/implementation-artifacts/spec-om-01-03-recover-background-work-and-record-mutation-evidence.md`
  summary: No operator-facing listing of work items that are blocked but not terminal (`PENDING` with `release_count > 0` after undecided authorization rechecks); today the count is stored on the row and each release past `max-attempts` logs a warning.
  evidence: PR #111 review comment 4549349820 (WorkProcessor.release). R6 added the count, the exponential backoff and the WARN; `FailedWorkQuery` lists terminal items only (AC5), and an authorized operator view of non-terminal work belongs with the operator surface (OM-16.01) and the real authorization port (OM-02.04).

- source_spec: `_bmad-output/implementation-artifacts/spec-om-01-03-recover-background-work-and-record-mutation-evidence.md`
  summary: The R2DBC connection carries no TCP keepalive or connect timeout, so a connection lost to a network partition is only abandoned by the client-side step bounds, not closed promptly.
  evidence: PR #111 review comment 4549349838 (WorkProcessor.runOnce). R6 bounds every processor step and the handler transaction on the client and the server, which removes the stall; the socket options are parameters of the connection URL the install package renders (`OWLMAST_DATABASE_R2DBC_URL`, OM-01.02 chart), so they belong to a packaging change with its own render tests.


- source_spec: `_bmad-output/implementation-artifacts/spec-om-01-03-recover-background-work-and-record-mutation-evidence.md`
  summary: The frozen v1 shape test does not record whether an interface method is abstract or default, nor type-parameter bounds, so adding an abstract method to `WorkHandler` or `DispatchAuthorization` (which breaks every implementer) passes as an appended line and turning a default method abstract changes no line at all.
  evidence: Owner-deferred 2026-11-12. Source: walkthrough of PR #111 at 285d862 and the spec's "Independent review of d3b985d (R4)" (B3; `DurableWorkContractTest.java:279`, `contract-shape-v1.txt`). `shapeOf` writes `method <type> <signature>` from `getDeclaredMethods()` without `Method.isDefault()` or `getTypeParameters()` bounds. Both published interfaces have only abstract methods today, so nothing is misrecorded yet; the fix changes the format of every frozen method line, which is why it was not folded into R9.

- source_spec: `_bmad-output/implementation-artifacts/spec-om-01-03-recover-background-work-and-record-mutation-evidence.md`
  summary: Readers of the stored vocabularies use `valueOf` and throw on an unknown constant, although the contract's compatibility rule allows adding an enum constant within a version only if every reader maps unknown constants to an explicit unknown state.
  evidence: Owner-deferred 2026-11-12. Source: walkthrough of PR #111 at 285d862 and the spec's "Independent review of d3b985d (R4)" (B5; `R2dbcAuditStore.java:173`, `:181` for `ActorKind` and `AuditOutcome`, `R2dbcWorkRepository.java:386` for `WorkStatus`). A row written by a newer build with a new constant makes an older instance fail the history query or the failure listing during a rolling deploy. No constant has been added since v1, so no such row exists; the fix needs an explicit unknown state in the published enums or in the read models, which is an API decision.

- source_spec: `_bmad-output/implementation-artifacts/spec-om-01-03-recover-background-work-and-record-mutation-evidence.md`
  summary: `owlmast.jobs.lease-duration` has no upper bound: above about 24.8 days the millisecond value passed to PostgreSQL's `statement_timeout` and `transaction_timeout` exceeds its integer limit, the setting is rejected and every processor step and handler transaction fails.
  evidence: Owner-deferred 2026-11-12. Source: walkthrough of PR #111 at 285d862 and the spec's "Independent review of d3b985d (R4)" (B6; `RetryPolicy`, `JobsProperties`, `R2dbcWorkRepository.limitStatementTime` and `limitTransactionTime`). PostgreSQL accepts at most 2147483647 ms for both settings. R9 replaced the handler's per-statement limit by a transaction limit counted from the claim but added no bound on the lease, so the gap is unchanged; a lease of weeks is far outside any sensible configuration (default PT30S), and the fix is a documented maximum validated at binding time.

- source_spec: `_bmad-output/implementation-artifacts/spec-om-01-03-recover-background-work-and-record-mutation-evidence.md`
  summary: When an `audit.event` row with the same event id already exists for another tenant, the guarded publication upsert changes no row, yet the intent is marked published, so that tenant's committed mutation has no history record (AC4) and nothing reports it.
  evidence: Owner-deferred 2026-11-12. Source: walkthrough of PR #111 at 285d862 and the spec's "Independent review of d3b985d (R4)" (B7; `R2dbcAuditStore.java:54` `where ... audit.event.tenant_id = excluded.tenant_id`, and the `published_at` update that follows). `event_id` is the primary key across tenants and event ids are server-generated random UUIDs, so a collision needs a hand-inserted row; a fix would tell a repeat (0 rows, own tenant's `SUCCEEDED` row present) from a foreign-tenant conflict and fail the latter as non-retryable.

- source_spec: `_bmad-output/implementation-artifacts/spec-om-01-03-recover-background-work-and-record-mutation-evidence.md`
  summary: Tenant discovery ranks a tenant's expired leases by `lease_expires_at`, while the claim inside a tenant orders every due item by `next_attempt_at`, so the item that made a tenant first in the wake-up is not necessarily the one claimed first.
  evidence: Owner-deferred 2026-11-12. Source: walkthrough of PR #111 at 285d862 and the spec's "Independent review of d3b985d (R4)" (B8; `R2dbcWorkRepository.dueTenants` `order by min(case when status = 'PENDING' then next_attempt_at else lease_expires_at end)` against the claim's `order by next_attempt_at, created_at`). Both orders are fair on their own and no due item becomes unclaimable; the mismatch only changes the order inside one tenant when an expired lease and older pending items coexist. Aligning them means choosing one waiting-time definition for both queries and re-pinning `anExpiredLeaseCountsAsWaitingSinceItsLeaseRanOut`.

- source_spec: `_bmad-output/implementation-artifacts/spec-gh-112-resolve-review-findings.md`
  summary: Gate protected features on the compatibility verdict: expose the verdict to the API client (for example a provider) and refuse protected requests unless the pair is Compatible.
  evidence: PR #112 thread 4551653214. The verdict is computed and displayed in ConnectionPanel only; no protected feature exists yet, so docs/api-compatibility.md now says "displayed only". Belongs to the first story that adds a protected fetch (E02).

- source_spec: `_bmad-output/implementation-artifacts/spec-gh-112-resolve-review-findings.md`
  summary: Run the pre-rollout API compatibility check automatically (Helm pre-upgrade hook or pipeline step) against the candidate frontend and backend artifacts.
  evidence: PR #112 thread 4551653219. The image now publishes /api-compatibility.json and the script has --frontend-url, but running it is still an operator step; a hook needs egress to both artifacts, an image for the check and an owner decision on failure policy.

- source_spec: `_bmad-output/implementation-artifacts/spec-gh-112-resolve-review-findings.md`
  summary: Bring failures raised outside controllers (web filters, codecs) and authentication/authorization exceptions under the RFC 9457 envelope with their own status.
  status: partly resolved 2026-11-12 (PR #119 round 4, walkthrough risk 6; E01-R-05). UnhandledFailureAdvice now keeps the status of an `ErrorResponse`, a `@ResponseStatus` class and Spring Security's `AccessDeniedException`/`AuthenticationException` (by class name: 403/401), and gives the shared kernel's own failures theirs (`OperationDeniedException` 403, bounded-blocking capacity 503 and deadline 504, scope failures 500). Still deferred: failures raised outside controllers (web filters, codecs), and the authentication challenge (`WWW-Authenticate`), which E02 owns. E02 must also remove the two security class names from the guard (or replace them with its own advice): a controller advice answers before Spring Security's exception translation filter sees the failure.
  evidence: PR #112 thread 4551653387. UnhandledFailureAdvice covers controller exceptions (500); a filter-level failure still gets Spring Boot's default application/json body, and a future AccessDeniedException would answer 500 unless mapped. No filter or security dependency exists before E02.


- source_spec: `_bmad-output/implementation-artifacts/spec-gh-112-resolve-review-findings.md`
  summary: Decide whether the frontend image should ship the nginx base image's `50x.html`, and clear the web root before copying the build output if not.
  evidence: PR #119 round 2 self-review (2B12). The Dockerfile copies `dist` over `/usr/share/nginx/html` without clearing it, so the base image's `50x.html` is served at `/50x.html`; no error_page refers to it. Pre-existing since OM-01.04.

- source_spec: `_bmad-output/implementation-artifacts/spec-gh-112-resolve-review-findings.md`
  summary: Recover automatically from a shown Incompatible verdict or denial to Compatible when a later check passes, instead of waiting behind "New updates".
  evidence: Owner-deferred 2026-11-12. Source: walkthrough of PR #119 at 2570202 (risk 7) and triage row B13. Failing closed is automatic (`invalidatesView` in `frontend/src/routes/ConnectionPanel.tsx`), but `retainsView` holds a descriptor and a denial against later answers, so after a backend is rolled forward again, or access is restored, the panel keeps the old state until the person activates "Show update"; pinned by tests in `routes.test.tsx`. The change needs a decision on which transitions may replace shown content without a user action (UX-DR "changed values wait behind one polite announcement").

- source_spec: `_bmad-output/implementation-artifacts/spec-gh-112-resolve-review-findings.md`
  summary: Generate the list of shell pages the frontend image refuses as an API prefix from one source instead of keeping a literal copy in the start-up guard.
  evidence: Owner-deferred 2026-11-12. Source: walkthrough of PR #119 at 2570202 (risk 12) and round 3 finding S2. `owlmast_shell_routes` in `frontend/docker-entrypoint.d/16-owlmast-api-prefix.envsh` repeats the first path segments of `DESTINATIONS` (`frontend/src/app/destinations.ts`); `src/app/destinations.test.ts` fails when they differ, so the copy cannot drift unnoticed. A generated list needs a second build output outside the web root that the Dockerfile copies next to the guard.

- source_spec: `_bmad-output/implementation-artifacts/spec-e01-retro-remediation.md`
  summary: A blocking call that fails after `BoundedBlocking` gave up on it at its deadline is logged by Reactor with its stack trace and message, which bypasses the rule that failures are logged as class names only.
  evidence: Found while writing `UnhandledFailureIT` for E01-R-05: the worker thread is interrupted at the deadline, the late exception has no subscriber, and Reactor reports it through `onErrorDropped` at ERROR with the trace. No production code calls `BoundedBlocking` yet, so nothing leaks today; the first caller would. Fix in `platform/blocking/BoundedBlocking.java` (drop or `SafeFailure`-log the late failure) with a test that plants a secret in the late exception.

- source_spec: `_bmad-output/implementation-artifacts/spec-e01-retro-remediation.md`
  summary: The Kind qualification never deploys the frontend image, so the chart-routed frontend, its NetworkPolicy path and `/api/compatibility` through the route are not part of the scripted evidence.
  evidence: Retrospective B8. `scripts/qualify-local-install.sh` installs with `frontend.enabled=false`; `docs/installation.md` calls deploying the frontend image onto the Kind target a live qualification step. The retrospective's own behaviour check ran a bundled install with the frontend once at 98496d6 in a scratch namespace (not scripted, not repeated here). Adding it means loading a frontend image into the cluster and a step that reads the shell and the compatibility endpoint through the Service.

- source_spec: `_bmad-output/implementation-artifacts/spec-e01-retro-remediation.md`
  summary: The retirement step of the Kind qualification switches off the injection of the Keycloak bootstrap admin but does not create a permanent administrator or delete the temporary user, so the documented operator procedure is proven only from the chart's side.
  evidence: E01-R-01. `retire_bootstrap_admin` in `scripts/qualify-local-install.sh` proves that after `identity.keycloak.bootstrapAdmin.enabled=false` no Deployment or running pod names a bootstrap variable or the Secret and that Keycloak and the backend stay ready. Creating the permanent admin and deleting the temporary one are admin-console (or `kcadm`) steps on a read-only-root pod; scripting them needs a decision on how the qualification authenticates to Keycloak.

- source_spec: `_bmad-output/implementation-artifacts/spec-e01-retro-remediation.md`
  summary: Gradle 9.9.1 was released on 2026-11-10; the wrapper stays on 9.9.0, the version that was built and tested.
  evidence: E01-R-07. `https://services.gradle.org/versions/current` on 2026-11-12. Moving means rerunning the *Gradle distribution and wrapper* section of `docs/toolchain-qualification.md` (both checksums, `--version`, clean build, gates); `GradleWrapperDocumentTest` fails until the README and the document follow the wrapper.

- source_spec: `_bmad-output/implementation-artifacts/spec-e01-retro-remediation.md`
  summary: Shell embedded in other files is not linted: the chart's ConfigMap scripts (`postgresql-init-configmap.yaml`, the provisioning Job), the Kind fixture manifest and the bash stubs inside `deploy/tests/test_qualify_script.py`.
  evidence: E01-R-11 review. `scripts/verify-script-lint.sh` runs shellcheck over shell files only. The ConfigMap scripts run as the database superuser at first initialisation, so they are the ones a lint would matter for; linting them means extracting each block scalar from the rendered template and mapping findings back to the template line.

- source_spec: `_bmad-output/implementation-artifacts/spec-e01-retro-remediation.md`
  summary: `helm upgrade` of a release installed from chart 0.1.0 would very likely be refused, because the backend Deployment rolled in 0.1.0 and is `type: Recreate` now.
  evidence: Kind qualification 2026-11-12. Changing the Keycloak Deployment of an existing release from the default rolling update to `type: Recreate` was refused by the API server under Helm 4's server-side apply (`spec.strategy.rollingUpdate: Forbidden: may not be specified when strategy type is 'Recreate'`), because the object still carries the rollingUpdate block the server defaulted. The backend made the same change between 0.1.0 and 0.2.0, and `docs/installation.md` says that upgrade was never run on a cluster. Not verified for the backend itself: it needs a 0.1.0 release on the target. Fix candidates: a surge-free rolling update as for Keycloak, or a documented uninstall/reinstall on the retained volume.

- source_spec: `_bmad-output/implementation-artifacts/spec-e01-retro-remediation.md`
  summary: Run one uninterrupted `first-enable` (fresh volume through the bootstrap-admin retirement) on the Kind target with the fixed chart.
  evidence: E01-R-01. The scripted run at `00b4853` passed through the retry and failed at the retirement (chart defect); the retirement passed when rerun on the same release with the fix. A fresh run needs a fourth 10Gi claim in `owl-mast-test`, whose 30Gi storage quota is used up by `owl-mast-postgresql-data`, `owl-mast-fe-postgresql-data` and `owl-mast-fe-e01r01-postgresql-data`. Freeing one is a deletion on the retained cluster and needs the owner.
