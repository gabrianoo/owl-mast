# Installation package (OM-01.02)

Owl Mast installs from the repository-owned Helm chart `deploy/helm/owl-mast` (version 0.1.0). The
chart packages the backend image and two **independently optional** bundles: PostgreSQL 18 with
VectorChord, and Keycloak. Disabling a bundle means supplying a compatible existing service; it never
removes the dependency. There is no value that disables authentication. Qualified on 2026-11-07 for
GitHub issue #21 on a disposable local Kind target; the frontend shell artifact and its smoke check
are delivered by OM-01.04, browser realm/client/session policy by OM-02.01.

## Pins

| Component | Pin | Where | Source / qualification |
| --- | --- | --- | --- |
| Chart | `owl-mast` 0.1.0, `appVersion` 0.1.0 | `deploy/helm/owl-mast/Chart.yaml` | This repository; package hash is produced by `helm package` from the release commit |
| Backend image | `owl-mast/backend:0.1.0`, built by `backend/Dockerfile` from the `bootJar` and referenced by tag; set `backend.image.digest` to the registry manifest digest once the image is published (a local image id from `docker build` is not a manifest digest and is not accepted by Kubernetes as one) | `backend/Dockerfile`, `backend.image.*` | Base `ubuntu:26.04@sha256:6a06111c3b0a8600feadb270aec771dc239bf407b25625f93f44ab00e11f4d3c`; Temurin 27.0.1+1 Linux x64 tarball sha256 `30cb129f…` (same JDK as [toolchain-qualification.md](toolchain-qualification.md)), verified during the build |
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
| `identity.keycloak.bootstrapExistingSecret` | `owl-mast-keycloak-bootstrap` | Keycloak temporary bootstrap admin; referenced only when `identity.bundled=true` |

With `identity.bundled=false` an install needs only `database.existingSecret` (and `postgresql.adminExistingSecret`
when the database is bundled); no Keycloak credential or database is provisioned.

## Combinations

| `database.bundled` | `identity.bundled` | Rendered | Required values | Example |
| --- | --- | --- | --- | --- |
| true | true | backend, PostgreSQL (PVC), Keycloak | defaults | `examples/bundled-bundled.yaml` |
| true | false | backend, PostgreSQL | `identity.external.issuerUri` | `examples/bundled-external.yaml` |
| false | true | backend, Keycloak | `database.external.host`, `identity.keycloak.database.external.host` | `examples/external-bundled.yaml` |
| false | false | backend | `database.external.host`, `identity.external.issuerUri` | `examples/external-external.yaml` |

`helm template` fails with the offending value named when a required external value is missing,
when a secret reference is empty, or when an unknown key (for example `auth.enabled`) is passed
(`values.schema.json` rejects unknown top-level keys). An external PostgreSQL must be version 18 with
`CREATE EXTENSION vchord CASCADE` available to the provisioning identity; the backend migration only
verifies the extension is present. An external issuer must publish an OpenID Connect discovery
document whose `issuer` equals the configured value; the backend's readiness group includes that
check (`identityDiscovery`) together with the schema baseline, so a misconfigured or unreachable
identity provider keeps the backend unready while liveness stays up.

## Shared PostgreSQL (AC3)

The bundled instance initialises once from `postgresql-init-configmap.yaml`: databases `owlmast`
and `keycloak`, login roles `owlmast_app` and `keycloak_app` (`NOSUPERUSER NOCREATEDB NOCREATEROLE
NOINHERIT`), `REVOKE ALL … FROM PUBLIC` on both databases and on `postgres`, `CONNECT, TEMPORARY`
granted only to each owner, and `vchord CASCADE` installed in `owlmast` by the provisioning
identity. Verified on the local target: each runtime principal is not a superuser and is refused
(`permission denied for database`) when connecting to the other database; a `vchordrq` index on
synthetic vectors is created by `owlmast_app` and used by the planner (`Index Scan using …`); no
`hnsw`/`ivfflat` index exists. Operators supplying an external PostgreSQL must reproduce the same
separation; the init script is the reference.

## Enabling the identity bundle later on an initialised bundled PostgreSQL

The first-initialisation script of the bundled PostgreSQL runs once, when the data directory is
empty. A volume initialised with `identity.bundled=false` therefore has no `keycloak` database or
`keycloak_app` role, and simply switching to `identity.bundled=true` leaves Keycloak failing
authentication (unready, nothing destroyed). The explicit transition is one `helm upgrade --wait`
with `identity.bundled=true` and `postgresql.provisionKeycloakDatabase=true`. It renders a
**pre-upgrade** hook (`<release>-postgresql-provision-keycloak`, with its own hook ConfigMap
`<release>-postgresql-provision-scripts`) that runs against the PostgreSQL of the release as it is
before the upgrade: it waits, bounded, for `pg_isready`, then executes the idempotent
`provision-keycloak.sh` with the admin principal, so Keycloak's role and database exist before Helm
applies and waits for the Keycloak and backend consumers. The role is created only if absent (an
existing role keeps its password, so the Secret must match it), the database only if absent, and the
restricted grants are re-applied; nothing is dropped or recreated. The Keycloak database Secret must
exist before the upgrade (the hook fails before anything else changes otherwise). The value is rejected
unless both bundles are enabled, is meaningful only on an upgrade of an existing release (a fresh
install provisions at first initialisation), and should be left `false` afterwards. Disabling the
identity bundle later keeps the existing Keycloak database and principal untouched.

Initialisation layout: only `10-owl-mast-databases.sh` is placed in `/docker-entrypoint-initdb.d`
(the image's entrypoint auto-executes every `*.sh` there); the provisioning helper is mounted at
`/owl-mast/provision-keycloak.sh` and invoked explicitly, so a volume initialised with the identity
bundle disabled completes initialisation on the first start. `deploy/tests/test_postgresql_init.py`
exercises both fresh initialisations and the first-enable/retry transition against the pinned image.

## Probes and resources (AC1)

| Component | Startup | Liveness | Readiness | Default requests / limits |
| --- | --- | --- | --- | --- |
| Backend | `GET /actuator/health/liveness` (≤ 3 min) | same | `GET /actuator/health/readiness` (readinessState, schemaBaseline, identityDiscovery) | 250m/512Mi – 1/1Gi |
| PostgreSQL | `pg_isready` | `pg_isready` | `select 1` against the application database (initialisation complete) | 250m/512Mi – 1/1Gi |
| Keycloak | `/health/started` on 9000 (≤ 5 min) | `/health/live` | `/health/ready` | 500m/768Mi – 1/1536Mi |

The backend may restart once on a cold install because it starts before the database accepts
connections; Flyway fails fast, the kubelet restarts the container and the second start succeeds.
All pods run as non-root with a read-only root filesystem where the image allows it, drop all
capabilities and use the `RuntimeDefault` seccomp profile; the chart passes the `restricted` Pod
Security level.

## Persistent volumes and retention (T3)

The bundled PostgreSQL is a single-replica `Recreate` Deployment mounting one explicit
`PersistentVolumeClaim` (`<release>-postgresql-data`, default 10Gi, `ReadWriteOnce`). The claim
carries `helm.sh/resource-policy: keep`, so `helm uninstall` leaves it (and its data) in place and
`helm upgrade` never recreates it. Reinstall with
`--set postgresql.persistence.existingClaim=<release>-postgresql-data` to continue with the same
data; the chart never adopts an arbitrary claim without that explicit selection. Choose a
StorageClass whose reclaim policy is `Retain` for the PersistentVolume as well; the local
qualification used the run-owned `owl-mast-local-retain` class. **Snapshot cadence and provider are
not decided here**: local node storage is disposable, and no backup is implied.

## Frontend and routing values (T2/T4)

`frontend.*` deploys the independent shell artifact (`frontend.image.*`, disabled until OM-01.04
supplies an image; enabling without a tag or digest fails rendering). `routing.*` defines the path
contract: `/api` and `/actuator` route to the backend, `/` to the frontend. The Ingress is disabled
by default and requires an explicit host; public origins, TLS and session behaviour are OM-02.01.

## Commands

```sh
# packaging checks (lint, four renders, negative validation) with the qualified Helm
scripts/verify-install-package.sh

# backend image from the built jar
./gradlew :backend:bootJar && docker build -t owl-mast/backend:0.1.0 -f backend/Dockerfile backend

# install (secrets must exist first; see examples/)
helm upgrade --install owl-mast deploy/helm/owl-mast -n owl-mast -f deploy/helm/owl-mast/examples/bundled-bundled.yaml --wait

# runtime qualification on the disposable Kind target (explicit run-local kubeconfig)
KUBECONFIG=<run>/kubeconfig OWLMAST_HELM=<run>/helm EVIDENCE_DIR=<private> scripts/qualify-local-install.sh all
```

The qualification script first preflights every resource the selected steps consume or change
(StorageClass, namespaces, quotas, Secrets, fixture objects, retained claims, Helm releases): an
existing object must carry this run's ownership label with the exact run id, an unreadable
ownership (denied, outage) refuses, and only an explicit NotFound counts as absence; nothing is
mutated when preflight refuses. It then prepares the run-owned StorageClass, namespaces and quotas (6 CPU / 12Gi /
40Gi combined), generates synthetic secrets into the cluster only, deploys synthetic external
PostgreSQL/Keycloak fixtures, installs all four combinations sequentially, proves pod replacement,
uninstall retention, reinstall with the existing claim and upgrade, and exercises the failure paths
(Secret missing a key, non-existent realm). Isolation evidence requires the PostgreSQL CONNECT denial
for the other database together with a successful same-principal control connection; transport or
authentication failures fail the check. Secret inventories list metadata and key names only; no
Secret value is ever requested in a persistable form. Evidence is written to the private evidence
directory, never to the repository.
