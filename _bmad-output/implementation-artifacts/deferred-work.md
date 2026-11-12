# Deferred work

- source_spec: `_bmad-output/implementation-artifacts/spec-gh-109-resolve-review-findings.md`
  summary: Mount an operator-supplied CA trust (Secret) for external PostgreSQL so `sslMode=verify-ca|verify-full` work for JDBC (Flyway, Keycloak) and R2DBC, then restore `verify-full` in `examples/external-external.yaml`.
  status: still deferred after review cycle 1 (2026-11-11). The chart now REFUSES `verify-ca`/`verify-full` at render (they rendered and then crash-looped), so the gap is fail-closed; `require` encrypts without authenticating the server. Owner decision: ship the CA trust mount (values for a CA Secret, `sslrootcert`/`sslRootCert` on the JDBC and R2DBC URLs, Keycloak `KC_DB_URL`), with a TLS PostgreSQL fixture to qualify it.
  evidence: The chart accepts verify-ca/verify-full since OM-01.02 but mounts no root certificate; pgjdbc's default LibPQFactory needs `~/.postgresql/root.crt` or `sslrootcert`, which the read-only backend (no home directory) does not have. Pre-existing; round-1 review finding B13 of PR #109's follow-up.

- source_spec: `_bmad-output/implementation-artifacts/spec-gh-116-review-cycle-1.md`
  summary: Rerun the owner-run Kind qualification (`scripts/qualify-local-install.sh all` plus `first-enable`) against chart 0.2.0 and record the evidence, including the retirement of the Keycloak bootstrap admin (`identity.keycloak.bootstrapAdmin.enabled=false`).
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

