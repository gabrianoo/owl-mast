# Local Kind qualification target (OM-01.02)

Disposable, local-only target used by `scripts/qualify-local-install.sh`. Nothing here is a
production topology: node storage is disposable, there is no ingress, and secrets are synthetic.

| Item | Value |
| --- | --- |
| Kind | 0.33.0 with `kindest/node:v1.36.4@sha256:099e049362a1526b2db71494e1947aae99bd16290d7c895f2b7ea312e3cbfaed` |
| Cluster / context | `owl-mast-om0102` / `kind-owl-mast-om0102`, explicit `--kubeconfig` on every command |
| Helm | 4.3.1 (`get.helm.sh` archive sha256 `0403a88a…`), isolated binary; installed Helm 3.x is unsupported for Kubernetes 1.36 |
| Namespaces | `owl-mast-test` (product installs) and `owl-mast-test-external` (synthetic external fixtures) |
| Quotas | 4 CPU / 8Gi / 30Gi and 2 CPU / 4Gi / 10Gi limits respectively (6 CPU / 12Gi / 40Gi combined) |
| Storage | `owl-mast-local-retain`: run-owned StorageClass on the Kind `rancher.io/local-path` provisioner with `Retain` and `WaitForFirstConsumer`; the pre-existing `standard` class is never modified |

Files: `kind-config.yaml` (cluster), `namespaces.yaml` (namespaces, quotas, limit ranges),
`storageclass.yaml`, `external-fixtures.yaml` (synthetic PostgreSQL/VectorChord and Keycloak in
`owl-mast-test-external`, same pinned images as the chart; their init ConfigMap is rendered from the
chart so the principal/grant contract is identical).
