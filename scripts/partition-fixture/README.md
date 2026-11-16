# Worker/API partition qualification

This opt-in probe needs Docker, Kind, kubectl, the qualified Java toolchain and enough
memory for a control plane, two workers, two PostgreSQL fixtures and three JVMs.
It uses the real backend with synthetic handlers and stub identity. It is not a
production chart installation or a different-version/schema compatibility test.

Use a **new** name beginning `owl-pr189-partition-` and a fresh evidence directory:

```sh
run_dir="$PWD/.bmad-work/partition-EXAMPLE"
cluster=owl-pr189-partition-EXAMPLE
mkdir -p "$run_dir"
./gradlew :backend:bootJar
docker build -t owl-mast/partition-base:EXAMPLE -f backend/Dockerfile backend
scripts/build-partition-fixture.sh "$run_dir/image" owl-mast/partition-fixture:EXAMPLE owl-mast/partition-base:EXAMPLE
kind create cluster --name "$cluster" --image kindest/node:v1.36.4 \
  --config scripts/partition-fixture/kind.yaml --kubeconfig "$run_dir/kubeconfig" --retain
python3 scripts/qualify-worker-partition.py --cluster "$cluster" \
  --image owl-mast/partition-fixture:EXAMPLE --evidence "$run_dir"
```

Replace `EXAMPLE` with a unique lowercase identifier in all arguments. The build
exports a fresh integration runtime classpath and records the source head, backend
diff, source hashes and local image ID. Keep these together with the run evidence.
A local image ID is not a registry manifest digest.

The harness refuses a cluster with existing user namespaces or pods, validates its
three exact Kind node containers, and gets that cluster's kubeconfig explicitly.
It never uses the caller's default kubectl context. No credentials or Secrets are
included in the evidence; the kubeconfig itself stays private with mode 0600.
PostgreSQL uses trust authentication only in this disposable fixture.

Two namespaces run concurrently on one worker. The `replacement` fixture uses a
standalone ReplicaSet, the same controller that manages a Deployment's replicas.
Its first worker waits for another worker to complete one held item. After that
worker starts, only the ReplicaSet template is changed to normal handling for its
successor; there is no Deployment rollout in this scenario. The `rollout` fixture
uses a one-replica Recreate Deployment and a slow handler with queued work.

The only firewall changes are tagged DROP rules for each IPv4/IPv6 API endpoint inside the disposable worker
container, OUTPUT and FORWARD to the control-plane addresses on TCP 6443.
This blocks worker-to-API traffic, including established kubelet connections; it
preserves PostgreSQL and other traffic. It does not model every bidirectional or
whole-node network failure. A bounded TCP attempt to every resolved API endpoint must time out. Both address
families matter: Kind can reconnect the kubelet over IPv6 after an IPv4-only block. The probe waits
for actual unreachable NoExecute tainting, records the default 300-second pod
tolerations, and observes replacement on the healthy worker. It requests a
Recreate template change during the partition and checks whether that rollout
waits for the old terminating pod. Docker/containerd inspection independently
checks that the old container is running; PostgreSQL sessions, a committed fixture polling heartbeat and continuing
fixture effects establish DB reachability beyond stale Kubernetes pod status.

The replacement must leave a still-live lease alone. A separate, explicit
fixture-only SQL update then sets that held lease into the past, allowing a late
completion attempt before the old handler's original deadline. The probe checks
stale-write rejection, replacement ownership of the terminal row, two deliveries
and one durable receiver receipt. **This is artificial lease expiry**, not evidence
that the API partition naturally expires a live worker's lease. The existing JVM
SIGSTOP test covers real elapsed lease expiry. No blanket exactly-once guarantee
or arbitrary external receiver behavior follows from this fixture.

The probe restores its exact rules in `finally`, checks they are absent, proves
API connectivity returns, waits for the rollout to recover and both queues to
finish, then scales its workers to zero. The DBs, cluster and evidence are retained.
It starts no background proxy, port forward or watcher. No host firewall is changed.
SIGINT/SIGTERM trigger restoration; SIGKILL or host failure cannot do so. In that
case inspect the private `restore-network.sh` in the evidence directory and run it
to remove only the tagged rules. Never flush a chain or touch another cluster.
A failure retains partial evidence and may leave fixture workers running; inspect
those namespaced workloads before a new run. Cluster, namespaces, images and build
artifacts require separate owner-approved cleanup. Do not rerun on retained data.

`events.jsonl`, the before/during/recovered snapshots and `owned-rules.txt` contain
sanitized observations. A PASS requires both queue/effect audits, rollout recovery,
network restoration and worker shutdown. Keep build and runtime errors too; a
partial run is not a passing qualification.
