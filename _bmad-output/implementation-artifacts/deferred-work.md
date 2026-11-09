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
