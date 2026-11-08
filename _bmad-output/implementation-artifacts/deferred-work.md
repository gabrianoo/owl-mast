- source_spec: `_bmad-output/implementation-artifacts/spec-om-01-03-recover-background-work-and-record-mutation-evidence.md`
  summary: The audit actor recorded by AuditedMutations is caller-supplied and is not checked against the principal bound in the ScopeContext, so a feature could record another actor.
  evidence: AuditedMutationService.execute never compares AuditedMutation.actor with scope.principal(); AC3 requires the actor field, not its binding. Belongs with the authorization boundary (OM-02.04) or the first feature that records human actors.

- source_spec: `_bmad-output/implementation-artifacts/spec-om-01-03-recover-background-work-and-record-mutation-evidence.md`
  summary: The failure listing (FailedWorkQuery) is tenant-scoped only; AC5's "authorized operator" check needs the real authorization port.
  evidence: FailedWorkQueryService checks only that a scope is bound; the story spec forbids adding the real authorization port before OM-02.04.

- source_spec: `_bmad-output/implementation-artifacts/spec-om-01-03-recover-background-work-and-record-mutation-evidence.md`
  summary: Layering drift from docs/engineering-conventions.md: audit.api imports jobs.api (AuditIdentifiers, AuditEnvelopeContract) and domain imports api (audit.domain.AuditRecord, jobs.domain.RetryPolicy), which the layer table does not allow and FeatureModuleRules does not check.
  evidence: Owner decision needed: either amend the layer table (api may use another feature's api; domain may use its own api values) or move the shared bounds and records; then add the rule to FeatureModuleRules.
