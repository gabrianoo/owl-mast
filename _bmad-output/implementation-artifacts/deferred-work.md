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

