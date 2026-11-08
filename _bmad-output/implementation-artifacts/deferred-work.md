- source_spec: `_bmad-output/implementation-artifacts/spec-om-01-03-recover-background-work-and-record-mutation-evidence.md`
  summary: An UNRESOLVED separate-path outcome for a transaction whose commit actually landed makes the later SUCCEEDED publication a silent ON CONFLICT no-op, so history keeps UNRESOLVED.
  evidence: Unverified (medium if true). R2dbcAuditStore.publish and recordOutcome both insert ON CONFLICT (event_id) DO NOTHING; settle with a test forcing STATUS_UNKNOWN on a committed transaction, or resolve in OM-16.05 reconciliation.

## Deferred from: code review of spec-om-01-03-recover-background-work-and-record-mutation-evidence.md (2026-11-08)

- An UNRESOLVED outcome for a transaction whose commit actually landed makes the later SUCCEEDED publication a silent ON CONFLICT no-op while published_at is still set, so the intent looks delivered; pre-existing (publish conflict clause), unverified; settle with a forced STATUS_UNKNOWN-on-commit test or in OM-16.05.
