---
title: 'OM-01.02 — Install optional state and identity dependencies'
type: 'feature'
created: '2026-11-07'
status: 'in-progress'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: '3f1ef89693b5511e823d9ae5e0f93123073821bc'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
  - '{project-root}/docs/engineering-tracking.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The repository has a qualified backend but no installable package: no Kubernetes manifests, no pinned PostgreSQL/VectorChord or Keycloak deployment, no external-dependency contract, and no proof of durable-volume ownership or retention. Every later story would otherwise improvise its own deployment.

**Approach:** Add a repository-owned Helm chart (`owl-mast` 0.1.0) that packages the backend image with independently optional PostgreSQL/VectorChord and Keycloak bundles, fail-closed values/existing-secret validation, probes, resources, retained run-owned PVCs, and separate frontend image/routing values. Qualify it on the owner-approved disposable Kind target (run `om-01-02-local-20261107-01`) with synthetic fixtures across bundled/external combinations. Tracking: GitHub issue #21 (OM-01.02), epic #1 (E01); authorization `om-01-02-local-20261107-01:OM-01.02:1`.

## Boundaries & Constraints

**Always:** Preserve AD-1–AD-16, AC1–AC3 and OM-01.02-T1..T4 verbatim; product SPEC and epic files unchanged. Pins are immutable digests from the owner-approved packet (kindest/node v1.36.4, vchord-postgres pg18-v1.1.1, Keycloak 26.8.2, Helm 4.3.1 sha256 `0403a88a…`); chart/image hashes are derived from produced artifacts. Disabling a bundle requires compatible external connection values plus an existing Secret reference and never removes the identity provider; missing values fail rendering. Shared PostgreSQL uses separate databases (`owlmast`, `keycloak`) and principals (`owlmast_app`, `keycloak_app`) with restricted grants; runtime principals are not superusers; VectorChord indexes are used, pgvector only as dependency. PVCs are run-owned, labelled, kept on uninstall (`helm.sh/resource-policy: keep`) and never deleted on upgrade; existing claims require explicit selection. Local target only: run-local kubeconfig, namespaces `owl-mast-test` / `owl-mast-test-external`, quotas 6 CPU / 12Gi / 40Gi, no ingress. No secret values in Git, logs, values files or evidence.

**Never:** Merge the PR, deploy elsewhere, schedule, or delete retained volumes/cluster; adopt pre-existing resources without proven ownership; add browser session/realm/client policy (OM-02.01), the real frontend artifact smoke (OM-01.04), durable-work tables (OM-01.03), backup/snapshot providers, third-party chart dependencies; weaken tests or label mocks as runtime qualification; modify automation code/policy/state; edit root `.java-version`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Bundled/bundled install | defaults, required Secrets present | PostgreSQL and Keycloak Deployments ready via probes; backend readiness UP incl. schema baseline and identity discovery | N/A |
| Database bundle off | `database.bundled=false`, external host/port/db + Secret | backend and Keycloak point at the external instance; no bundled PG resources rendered | missing host/Secret → `helm template` fails naming the value |
| Identity bundle off | `identity.bundled=false`, `identity.external.issuerUri` | backend gets issuer; Keycloak not rendered; readiness still gated on discovery | missing issuer → render fails; no "auth disabled" value exists |
| Secret key missing at runtime | referenced Secret lacks `password` | pod stays unready with CreateContainerConfigError, nothing starts with empty credentials | fail closed |
| Shared PG principals | bundled PG initialised | `owlmast_app` cannot connect to `keycloak` DB and vice versa; neither is superuser; `vchord` present in `owlmast` | connect attempt fails with permission error |
| VectorChord index | synthetic table with vector column | `CREATE INDEX … USING vchordrq` succeeds and EXPLAIN shows it; pgvector hnsw/ivfflat not used | N/A |
| Uninstall / reinstall | release removed | PVC and data retained; reinstall with `existingClaim` reads the same rows | N/A |
| Upgrade | `helm upgrade` with changed resources | PVC untouched, pods replaced, data intact | N/A |
| Backend without issuer | property absent | startup fails with explicit message naming `owlmast.identity.issuer-uri` | fail closed |

</frozen-after-approval>

## Code Map

- `backend/src/main/resources/application.yaml` -- env-driven DB config (`OWLMAST_DATABASE_*`); add `owlmast.identity.issuer-uri` and readiness group membership.
- `backend/src/main/java/com/aisquad/owlmast/bootstrap/adapter/health/SchemaBaselineHealthIndicator.java` -- reactive indicator pattern to mirror for identity discovery (SafeFailure logging).
- `backend/src/test/java/com/aisquad/owlmast/architecture/FeatureModuleRules.java` -- new `access` feature must keep Spring in `adapter` packages only.
- `backend/src/testFixtures/java/com/aisquad/owlmast/testing/*` -- `OwlMastImages` pin reuse; add stub identity provider fixture.
- `backend/src/integrationTest/java/com/aisquad/owlmast/HealthEndpointIT.java` -- extend with issuer property via fixture.
- `docs/toolchain-qualification.md` -- qualified JDK 27.0.1+1 asset sha256 `30cb129f…` reused for the runtime image.
- `scripts/verify-quality-gates.sh`, `.github/workflows/ci.yml` -- add chart render/validation job; existing jobs unchanged.
- `automation/**` -- do not touch.

## Tasks & Acceptance

**Execution:**
- [ ] `deploy/helm/owl-mast/{Chart.yaml,values.yaml,values.schema.json,templates/*}` -- chart 0.1.0: backend, optional postgresql/keycloak, frontend values, PVC keep policy, fail-closed helpers -- T1/T2/T3.
- [ ] `backend/Dockerfile` -- runtime image on pinned `ubuntu:26.04` digest + Temurin 27.0.1+1 tarball (checksum verified), non-root -- T2.
- [ ] `backend/src/main/java/com/aisquad/owlmast/access/adapter/identity/*` -- `IdentityProperties` (required issuer) and `IdentityDiscoveryHealthIndicator` -- AC2.
- [ ] `backend/src/test*/…` -- unit/integration coverage for properties, indicator, readiness group -- AC2.
- [ ] `deploy/tests/test_chart_render.py`, `scripts/verify-install-package.sh` -- lint, four-combination render, negative validation -- T1/T4.
- [ ] `deploy/local-kind/*.yaml`, `scripts/qualify-local-install.sh` -- storage class, quotas, external fixtures, runtime qualification sequence -- T3/T4.
- [ ] `docs/installation.md`, `deploy/helm/owl-mast/examples/*.yaml`, `README.md` -- pins, secret contract, four secret-free examples, retention and snapshot decisions left explicit -- T1/T4.
- [ ] `.github/workflows/ci.yml` -- package-checks job with checksum-verified Helm 4.3.1 -- T4.

**Acceptance Criteria:** AC1–AC3 as stated in epic-01.md for OM-01.02; verified by the commands below and the runtime evidence report.

## Implementation Notes

## Spec Change Log

## Review Triage Log

## Design Notes

Bundled PostgreSQL is a single-replica `Recreate` Deployment with an explicit PVC resource rather than a StatefulSet template: retention and `existingClaim` adoption stay explicit and visible in the manifest. Initialisation runs once from a mounted script that creates both databases/principals from Secret-provided credentials and installs `vchord CASCADE` in `owlmast` with the admin principal, so the app principal never needs superuser. Keycloak runs `start` with `KC_HTTP_ENABLED`/`KC_HOSTNAME_STRICT=false` behind the cluster-local Service and imports a minimal synthetic realm; browser/client policy remains OM-02.01.

## Verification

**Commands:**
- `./gradlew build --console=plain` -- expected: all suites pass including new access tests.
- `scripts/verify-quality-gates.sh` -- expected: 5/5 gates still fail on injected violations.
- `python3 -m unittest discover -s automation/tests -t .` -- expected: unchanged pass.
- `scripts/verify-install-package.sh` -- expected: lint, four renders and negative validations pass.
- `scripts/qualify-local-install.sh` (run-local kubeconfig) -- expected: evidence per matrix row recorded under the private evidence root.
