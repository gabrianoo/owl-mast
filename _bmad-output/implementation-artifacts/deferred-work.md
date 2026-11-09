# Deferred work

- source_spec: `_bmad-output/implementation-artifacts/spec-gh-109-resolve-review-findings.md`
  summary: Mount an operator-supplied CA trust (Secret) for external PostgreSQL so `sslMode=verify-ca|verify-full` work for JDBC (Flyway, Keycloak) and R2DBC, then restore `verify-full` in `examples/external-external.yaml`.
  evidence: The chart accepts verify-ca/verify-full since OM-01.02 but mounts no root certificate; pgjdbc's default LibPQFactory needs `~/.postgresql/root.crt` or `sslrootcert`, which the read-only backend (no home directory) does not have. Pre-existing; round-1 review finding B13 of PR #109's follow-up.
