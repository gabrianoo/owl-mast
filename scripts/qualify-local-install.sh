#!/usr/bin/env bash
# OM-01.02-T3/T4 runtime qualification on the disposable local Kind target.
# Every cluster command uses the explicit, run-local KUBECONFIG; the default kubeconfig is never read.
# Synthetic secrets are generated into the cluster only: no value is ever printed, logged or written to
# evidence (inventories project metadata and key names only; replication pipes a Secret object straight
# into kubectl apply without writing it anywhere).
# Ownership: before any mutation, every resource a selected step consumes or changes is preflighted.
# An existing resource must carry this run's ownership label with the exact run id; a foreign or
# unlabelled one, or one whose ownership cannot be read (denied, outage, unreadable), refuses the whole
# invocation with exit 2 before anything is created, applied, labelled, deleted or installed.
# Usage: KUBECONFIG=<run kubeconfig> OWLMAST_HELM=<helm4> EVIDENCE_DIR=<private dir> scripts/qualify-local-install.sh [step...]
# Steps: prepare fixtures bundled-bundled persistence bundled-external external-bundled external-external failure-paths inventory all
# Optional: BACKEND_IMAGE_TAG (default 0.1.0), BACKEND_IMAGE_ID (expected local image id the node must run).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
: "${KUBECONFIG:?explicit run-local KUBECONFIG is required}"
: "${OWLMAST_HELM:?OWLMAST_HELM (Helm 4.x binary) is required}"
: "${EVIDENCE_DIR:?EVIDENCE_DIR is required}"
CONTEXT="${CONTEXT:-kind-owl-mast-om0102}"
NS="${NS:-owl-mast-test}"
EXT_NS="${EXT_NS:-owl-mast-test-external}"
RELEASE="${RELEASE:-owl-mast}"
CHART="$ROOT/deploy/helm/owl-mast"
RUN_ID="om-01-02-local-20261107-01"
RUN_LABEL_KEY="owlmast.aisquad.com/run"
RUN_LABEL="$RUN_LABEL_KEY=$RUN_ID"
BACKEND_IMAGE_TAG="${BACKEND_IMAGE_TAG:-0.1.0}"
BACKEND_IMAGE_ID="${BACKEND_IMAGE_ID:-}"
KIND_NODE="${KIND_NODE:-owl-mast-om0102-control-plane}"
OUT="$EVIDENCE_DIR/runtime"
mkdir -p "$OUT/preflight"
export KUBECONFIG

k() { kubectl --context "$CONTEXT" "$@"; }
h() { "$OWLMAST_HELM" --kube-context "$CONTEXT" "$@"; }
log() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*" | tee -a "$OUT/qualification.log"; }
record() { # record <name> <command...>: run, save output to evidence, echo status
  local name="$1"; shift
  local file="$OUT/$name.txt"
  { printf '$ %s\n' "$*"; "$@"; } >"$file" 2>&1 && log "ok   $name" || { log "FAIL $name (see $file)"; return 1; }
}
record_any() { # record_any <name> <command...>: save output to evidence whatever the exit status (the caller asserts on it)
  local name="$1"; shift
  local file="$OUT/$name.txt"
  { printf '$ %s\n' "$*"; "$@"; } >"$file" 2>&1 || true
  log "saw  $name (exit status recorded, asserted by the caller)"
}
refuse() { log "REFUSED: $*"; exit 2; }

# -- ownership -------------------------------------------------------------------------------------
# resource_state <namespace|-> <kind> <name>: prints absent | owned | foreign:<owner or unlabelled> | error:<message>.
# Only an explicit NotFound is absence; any other failure (denied, outage, unreadable) is an error.
resource_state() {
  local ns="$1" kind="$2" name="$3" out rc=0
  local -a nsarg=()
  [ "$ns" != "-" ] && nsarg=(-n "$ns")
  out="$(k "${nsarg[@]}" get "$kind" "$name" -o jsonpath="{.metadata.labels.owlmast\.aisquad\.com/run}" 2>&1)" || rc=$?
  if [ "$rc" -eq 0 ]; then
    if [ "$out" = "$RUN_ID" ]; then echo owned
    elif [ -z "$out" ]; then echo "foreign:unlabelled"
    else echo "foreign:$out"; fi
  elif grep -q '(NotFound)' <<<"$out"; then echo absent
  else echo "error:$(tr '\n' ' ' <<<"$out" | cut -c1-200)"; fi
}
release_state() { # release_state <release>: absent | owned | foreign:<why> | error:<message>
  local rel="$1" out rc=0 dep
  out="$(h status "$rel" -n "$NS" 2>&1)" || rc=$?
  if [ "$rc" -ne 0 ]; then
    if grep -qi 'release: not found' <<<"$out"; then echo absent; else echo "error:$(tr '\n' ' ' <<<"$out" | cut -c1-200)"; fi
    return
  fi
  dep="$(resource_state "$NS" deployment "$rel-backend")"
  case "$dep" in
    owned) echo owned ;;
    absent) echo "foreign:release exists without this run's backend deployment" ;;
    *) echo "$dep" ;;
  esac
}
PREFLIGHT_FAILED=0
preflight_resource() { # preflight_resource <namespace|-> <kind> <name>
  local state; state="$(resource_state "$1" "$2" "$3")"
  printf '%s %s/%s %s\n' "$2" "$1" "$3" "$state" >>"$OUT/preflight/resources.txt"
  case "$state" in
    absent) log "preflight $2 $1/$3: absent" ;;
    owned) log "preflight $2 $1/$3: owned by this run" ;;
    foreign:*) log "preflight $2 $1/$3: exists but owner is '${state#foreign:}', not $RUN_ID: no adoption, overwrite or deletion"; PREFLIGHT_FAILED=1 ;;
    *) log "preflight $2 $1/$3: ownership unreadable (${state#error:}): refusing rather than assuming absence"; PREFLIGHT_FAILED=1 ;;
  esac
}
preflight_release() { # preflight_release <release>
  local state; state="$(release_state "$1")"
  printf 'release %s/%s %s\n' "$NS" "$1" "$state" >>"$OUT/preflight/resources.txt"
  case "$state" in
    absent) log "preflight release $NS/$1: absent" ;;
    owned) log "preflight release $NS/$1: owned by this run (its steps upgrade or uninstall it)" ;;
    foreign:*) log "preflight release $NS/$1: ${state#foreign:}: refusing"; PREFLIGHT_FAILED=1 ;;
    *) log "preflight release $NS/$1: state unreadable (${state#error:}): refusing"; PREFLIGHT_FAILED=1 ;;
  esac
}
preflight_secrets_of() { # the four synthetic Secrets of a namespace
  local ns="$1" s
  for s in owl-mast-postgres-admin owl-mast-db owl-mast-keycloak-db owl-mast-keycloak-bootstrap; do preflight_resource "$ns" secret "$s"; done
}
preflight_install_target() { preflight_release "$RELEASE"; preflight_resource "$NS" pvc "$RELEASE-postgresql-data"; preflight_resource "$NS" namespace "$NS" >/dev/null 2>&1 || true; }
preflight() { # preflight <step...>: every resource the selected steps consume or change, before any mutation
  log "== preflight for: $*"
  : >"$OUT/preflight/resources.txt"
  local step
  for step in "$@"; do
    case "$step" in
      prepare)
        preflight_resource - storageclass owl-mast-local-retain
        preflight_resource - namespace "$NS"; preflight_resource - namespace "$EXT_NS"
        preflight_resource "$NS" resourcequota owl-mast-test-budget; preflight_resource "$EXT_NS" resourcequota owl-mast-test-external-budget
        preflight_secrets_of "$NS"; preflight_secrets_of "$EXT_NS"
        preflight_resource "$NS" secret owl-mast-external-db; preflight_resource "$NS" secret owl-mast-external-keycloak-db ;;
      fixtures)
        preflight_resource "$EXT_NS" configmap external-postgresql-init; preflight_resource "$EXT_NS" configmap external-keycloak-realm
        preflight_resource "$EXT_NS" pvc external-postgresql-data
        preflight_resource "$EXT_NS" service external-postgresql; preflight_resource "$EXT_NS" service external-keycloak
        preflight_resource "$EXT_NS" deployment external-postgresql; preflight_resource "$EXT_NS" deployment external-keycloak ;;
      bundled-bundled|persistence|bundled-external|external-bundled|external-external)
        preflight_release "$RELEASE"; preflight_resource "$NS" pvc "$RELEASE-postgresql-data" ;;
      failure-paths)
        preflight_resource "$NS" secret owl-mast-db-broken; preflight_release "$RELEASE-broken"; preflight_release "$RELEASE-wrongidp" ;;
      inventory) ;;
    esac
  done
  if [ "$PREFLIGHT_FAILED" -ne 0 ]; then refuse "preflight found resources this run does not own or cannot read; nothing was mutated (see $OUT/preflight/resources.txt)"; fi
  log "preflight passed: every existing resource is owned by $RUN_ID"
}

# -- secrets (values never leave the cluster or an in-memory pipe) ----------------------------------
ensure_secret() { # ensure_secret <namespace> <name> <username>: random password, created only if absent and owned if present
  local ns="$1" name="$2" user="$3" state
  state="$(resource_state "$ns" secret "$name")"
  case "$state" in
    owned) log "secret $ns/$name exists and is owned by this run (kept)"; return ;;
    absent) ;;
    *) refuse "secret $ns/$name: $state" ;;
  esac
  local password; password="$(openssl rand -base64 30 | tr -d '/+=' | cut -c1-32)"
  k -n "$ns" create secret generic "$name" --from-literal=username="$user" --from-literal=password="$password" >/dev/null
  k -n "$ns" label secret "$name" "$RUN_LABEL" >/dev/null  # newly created by this run: labelled once, never --overwrite
  log "secret $ns/$name created (synthetic, value not recorded)"
}
replicate_secret() { # replicate_secret <src-ns> <src-name> <dst-ns> <dst-name>: same values, owned source only, piped in memory only
  local src_ns="$1" src="$2" dst_ns="$3" dst="$4" state
  state="$(resource_state "$src_ns" secret "$src")"
  [ "$state" = owned ] || refuse "secret $src_ns/$src cannot be replicated: $state"
  state="$(resource_state "$dst_ns" secret "$dst")"
  case "$state" in
    owned) log "secret $dst_ns/$dst exists and is owned by this run (kept)"; return ;;
    absent) ;;
    *) refuse "secret $dst_ns/$dst: $state" ;;
  esac
  k -n "$src_ns" get secret "$src" -o json \
    | python3 -c 'import json,sys; s=json.load(sys.stdin); print(json.dumps({"apiVersion":"v1","kind":"Secret","type":s["type"],"metadata":{"name":sys.argv[1],"namespace":sys.argv[2],"labels":{sys.argv[3]:sys.argv[4]}},"data":s["data"]}))' "$dst" "$dst_ns" "$RUN_LABEL_KEY" "$RUN_ID" \
    | k apply -f - >/dev/null 2>&1
  log "secret $dst_ns/$dst replicated from $src_ns/$src (synthetic, value not recorded)"
}
ensure_broken_secret() { # a Secret with the username key only (the failure path); created only if absent, labelled once
  local state; state="$(resource_state "$NS" secret owl-mast-db-broken)"
  case "$state" in
    owned) log "secret $NS/owl-mast-db-broken exists and is owned by this run (kept)"; return ;;
    absent) k -n "$NS" create secret generic owl-mast-db-broken --from-literal=username=owlmast_app >/dev/null
            k -n "$NS" label secret owl-mast-db-broken "$RUN_LABEL" >/dev/null
            log "secret $NS/owl-mast-db-broken created (username only, no password key)" ;;
    *) refuse "secret $NS/owl-mast-db-broken: $state" ;;
  esac
}
secrets_inventory() { # metadata and key names only; values are never requested in a persistable form
  k get secrets -A -l "$RUN_LABEL" -o go-template='{{range .items}}{{.metadata.namespace}}/{{.metadata.name}} type={{.type}} keys=[{{range $k, $v := .data}}{{$k}} {{end}}] owner={{index .metadata.labels "owlmast.aisquad.com/run"}}{{"\n"}}{{end}}'
}

# -- database and identity observations -------------------------------------------------------------
pg_exec() { # pg_exec <namespace> <deployment> <role-env-prefix> <database> <sql...>
  local ns="$1" deploy="$2" prefix="$3" db="$4"; shift 4
  k -n "$ns" exec "deploy/$deploy" -- sh -c "PGPASSWORD=\"\$${prefix}_PASSWORD\" psql -v ON_ERROR_STOP=1 -h 127.0.0.1 -U \"\$${prefix}_USERNAME\" -d '$db' -Atc \"$*\""
}
expect_connect_denied() { # expect_connect_denied <name> <ns> <deploy> <prefix> <denied-db> <allowed-db>
  # Evidence is the intended PostgreSQL CONNECT denial for the other database together with a
  # successful control connection of the same principal to its own database. Transport, pod or
  # authentication failures are failures of the check, never denial evidence.
  local name="$1" ns="$2" deploy="$3" prefix="$4" denied="$5" allowed="$6" out rc=0
  local file="$OUT/$name.txt"
  out="$(pg_exec "$ns" "$deploy" "$prefix" "$denied" "select current_database()" 2>&1)" || rc=$?
  printf '$ pg_exec %s %s %s %s "select current_database()"\n%s\n[exit %s]\n' "$ns" "$deploy" "$prefix" "$denied" "$out" "$rc" >"$file"
  if [ "$rc" -eq 0 ]; then log "FAIL $name: the principal connected to $denied"; return 1; fi
  if grep -qiE 'authentication failed|unable to connect|connection refused|unable to upgrade connection|pods? .* not found|error: Internal error|command terminated with exit code 1[^0-9]|No such file' <<<"$out" \
     && ! grep -q "permission denied for database \"$denied\"" <<<"$out"; then
    log "FAIL $name: the attempt failed for a reason other than the database CONNECT denial (not evidence)"; return 1
  fi
  if ! grep -q "permission denied for database \"$denied\"" <<<"$out" || ! grep -q "does not have CONNECT privilege" <<<"$out"; then
    log "FAIL $name: no PostgreSQL CONNECT denial for \"$denied\" in the refusal"; return 1
  fi
  rc=0; out="$(pg_exec "$ns" "$deploy" "$prefix" "$allowed" "select current_database()" 2>&1)" || rc=$?
  printf '$ pg_exec %s %s %s %s "select current_database()"  (control)\n%s\n[exit %s]\n' "$ns" "$deploy" "$prefix" "$allowed" "$out" "$rc" >>"$file"
  if [ "$rc" -ne 0 ] || [ "$out" != "$allowed" ]; then log "FAIL $name: the same principal could not reach its own database $allowed (control failed)"; return 1; fi
  log "ok   $name (PostgreSQL CONNECT denied for $denied; the same principal reaches $allowed)"
}
proxy_get() { # proxy_get <namespace> <service:port> <path>
  k get --raw "/api/v1/namespaces/$1/services/$2/proxy$3"
}
assert_proxied_readiness_down() { # assert_proxied_readiness_down <file>: the verbose kubectl transcript must carry the backend's own 503 status and DOWN body
  # kubectl -v=8 logs `"Response" ... status="503 Service Unavailable"` and `"Response Body" body="{\"status\":\"DOWN\"}"`;
  # an API-server Status document (generic outage/denial) is not the backend's answer and fails this check.
  grep -qE 'status="503 |Response Status: 503' "$1" && grep -qE 'status\\?":\\?"DOWN' "$1" && ! grep -qE 'kind\\?":\\?"Status' "$1"
}
wait_ready() { # wait_ready <namespace> <deployment> <seconds>
  k -n "$1" rollout status "deploy/$2" --timeout="$3s"
}
verify_backend_image() { # verify_backend_image <name>: the running backend is exactly the local build loaded for this run
  local name="$1" pod image_id node_id
  pod="$(k -n "$NS" get pods -l "app.kubernetes.io/instance=$RELEASE,app.kubernetes.io/component=backend" -o jsonpath='{.items[0].metadata.name}')"
  record "$name-image" k -n "$NS" get pod "$pod" -o jsonpath='{.status.containerStatuses[0].image} {.status.containerStatuses[0].imageID}{"\n"}'
  [ -n "$BACKEND_IMAGE_ID" ] || { log "note $name-image: BACKEND_IMAGE_ID not supplied; running image recorded, not compared"; return; }
  # The node's record for the tag: its image id (the config digest, identical to the local docker image id)
  # and the import digests containerd assigned when `kind load` imported this exact build.
  node_id="$(docker exec "$KIND_NODE" crictl inspecti -o go-template --template '{{.status.id}}' "docker.io/owl-mast/backend:$BACKEND_IMAGE_TAG" 2>/dev/null || true)"
  local node_digests; node_digests="$(docker exec "$KIND_NODE" crictl inspecti -o go-template --template '{{range .status.repoDigests}}{{.}} {{end}}' "docker.io/owl-mast/backend:$BACKEND_IMAGE_TAG" 2>/dev/null || true)"
  image_id="$(k -n "$NS" get pod "$pod" -o jsonpath='{.status.containerStatuses[0].imageID}')"
  printf 'expected local image id: %s\nnode image id for tag %s: %s\nnode import digests: %s\npod imageID: %s\n' "$BACKEND_IMAGE_ID" "$BACKEND_IMAGE_TAG" "$node_id" "$node_digests" "$image_id" >>"$OUT/$name-image.txt"
  if [ "$node_id" = "$BACKEND_IMAGE_ID" ] && { [ "$image_id" = "$BACKEND_IMAGE_ID" ] || grep -qF -- "$image_id" <<<"$node_digests"; }; then
    log "ok   $name-image-identity (node tag resolves to the expected local build and the pod runs it)"
  else
    log "FAIL $name-image-identity: the pod does not run the expected local build (see $OUT/$name-image.txt)"; return 1
  fi
}

# -- steps -------------------------------------------------------------------------------------------
step_prepare() {
  log "== prepare target (cluster/context $CONTEXT)"
  record target-nodes k get nodes -o wide
  record target-storageclass-before k get storageclass
  record apply-storageclass k apply -f "$ROOT/deploy/local-kind/storageclass.yaml"
  record apply-namespaces k apply -f "$ROOT/deploy/local-kind/namespaces.yaml"
  local ns
  for ns in "$NS" "$EXT_NS"; do
    ensure_secret "$ns" owl-mast-postgres-admin owlmast_admin
    ensure_secret "$ns" owl-mast-db owlmast_app
    ensure_secret "$ns" owl-mast-keycloak-db keycloak_app
    ensure_secret "$ns" owl-mast-keycloak-bootstrap temp-admin
  done
  # The synthetic external instance has its own credentials; the product install in $NS references
  # them under distinct names, exactly as an operator would for an existing service.
  replicate_secret "$EXT_NS" owl-mast-db "$NS" owl-mast-external-db
  replicate_secret "$EXT_NS" owl-mast-keycloak-db "$NS" owl-mast-external-keycloak-db
  record secrets-inventory secrets_inventory
  record quotas k get resourcequota -A
}

step_fixtures() {
  log "== synthetic external fixtures in $EXT_NS"
  h template external "$CHART" --set fullnameOverride=external --set commonLabels."owlmast\.aisquad\.com/run"="$RUN_ID" -s templates/postgresql-init-configmap.yaml \
    | sed "s/^  namespace: .*//" | k -n "$EXT_NS" apply -f - >"$OUT/fixtures-init-configmap.txt" 2>&1
  record fixtures-apply k apply -f "$ROOT/deploy/local-kind/external-fixtures.yaml"
  record fixtures-postgresql-ready wait_ready "$EXT_NS" external-postgresql 300
  record fixtures-keycloak-ready wait_ready "$EXT_NS" external-keycloak 600
  record fixtures-keycloak-discovery proxy_get "$EXT_NS" external-keycloak:http /realms/owl-mast/.well-known/openid-configuration
  grep -q '"issuer":"http://external-keycloak.owl-mast-test-external.svc:8080/realms/owl-mast"' "$OUT/fixtures-keycloak-discovery.txt" \
    && log "ok   fixtures-keycloak-issuer" || { log "FAIL fixtures-keycloak-issuer"; return 1; }
  record fixtures-pods k get pods -n "$EXT_NS" -o wide
}

install_combo() { # install_combo <name> <helm args...>
  local name="$1"; shift
  log "== install $name"
  record "$name-install" h upgrade --install "$RELEASE" "$CHART" -n "$NS" --wait --timeout 15m \
    --set backend.image.tag="$BACKEND_IMAGE_TAG" --set backend.image.pullPolicy=Never \
    --set commonLabels."owlmast\.aisquad\.com/run"="$RUN_ID" \
    --set postgresql.persistence.storageClass=owl-mast-local-retain "$@"
  record "$name-pods" k get pods,pvc -n "$NS" -o wide
  record "$name-backend-readiness" proxy_get "$NS" "$RELEASE-backend:http" /actuator/health/readiness
  grep -q '"status":"UP"' "$OUT/$name-backend-readiness.txt" && log "ok   $name-backend-readiness-up" || { log "FAIL $name readiness not UP"; return 1; }
  record "$name-backend-liveness" proxy_get "$NS" "$RELEASE-backend:http" /actuator/health/liveness
  verify_backend_image "$name"
  record "$name-helm-status" h status "$RELEASE" -n "$NS"
}

check_shared_postgres() { # check_shared_postgres <namespace> <deployment>  (AC3 on whichever instance is the shared one)
  local ns="$1" deploy="$2"
  record "ac3-$ns-app-not-superuser" pg_exec "$ns" "$deploy" OWLMAST_APP owlmast "select current_user, rolsuper, rolcreatedb, rolcreaterole from pg_roles where rolname = current_user"
  grep -q 'owlmast_app|f|f|f' "$OUT/ac3-$ns-app-not-superuser.txt" || { log "FAIL app principal privileges"; return 1; }
  record "ac3-$ns-keycloak-not-superuser" pg_exec "$ns" "$deploy" OWLMAST_KEYCLOAK keycloak "select current_user, rolsuper, rolcreatedb, rolcreaterole from pg_roles where rolname = current_user"
  grep -q 'keycloak_app|f|f|f' "$OUT/ac3-$ns-keycloak-not-superuser.txt" || { log "FAIL keycloak principal privileges"; return 1; }
  expect_connect_denied "ac3-$ns-app-cannot-connect-keycloak-db" "$ns" "$deploy" OWLMAST_APP keycloak owlmast
  expect_connect_denied "ac3-$ns-keycloak-cannot-connect-owlmast-db" "$ns" "$deploy" OWLMAST_KEYCLOAK owlmast keycloak
  record "ac3-$ns-extensions" pg_exec "$ns" "$deploy" OWLMAST_APP owlmast "select extname||'='||extversion from pg_extension where extname in ('vchord','vector') order by 1"
  grep -q 'vchord=1.1.1' "$OUT/ac3-$ns-extensions.txt" && grep -q 'vector=0.8.2' "$OUT/ac3-$ns-extensions.txt" || { log "FAIL extensions"; return 1; }
  record "ac3-$ns-keycloak-schema-present" pg_exec "$ns" "$deploy" OWLMAST_KEYCLOAK keycloak "select count(*) > 10 from information_schema.tables where table_schema='public'"
  grep -qx 't' "$OUT/ac3-$ns-keycloak-schema-present.txt" || { log "FAIL keycloak schema"; return 1; }
  record "ac3-$ns-flyway-history" pg_exec "$ns" "$deploy" OWLMAST_APP owlmast "select version||'|'||success from flyway_schema_history order by installed_rank"
  grep -q '^001|true$' "$OUT/ac3-$ns-flyway-history.txt" || { log "FAIL flyway history"; return 1; }
  # VectorChord index usage on synthetic data with the application principal (AC3); re-entry appends, never drops.
  record "ac3-$ns-vchord-index" pg_exec "$ns" "$deploy" OWLMAST_APP owlmast "create schema if not exists qualification; create table if not exists qualification.vectors(id int primary key, embedding vector(3)); insert into qualification.vectors select g, array[g, g*2, g*3]::vector from generate_series(1,200) g on conflict do nothing; create index if not exists vectors_vchordrq on qualification.vectors using vchordrq (embedding vector_l2_ops) with (options = E'residual_quantization = true\\n[build.internal]\\nlists = []'); analyze qualification.vectors; set enable_seqscan = off; explain (costs off) select id from qualification.vectors order by embedding <-> '[3,6,9]' limit 3; select id from qualification.vectors order by embedding <-> '[3,6,9]' limit 3; select indexdef from pg_indexes where schemaname='qualification' and indexname='vectors_vchordrq'"
  grep -q 'Index Scan using vectors_vchordrq' "$OUT/ac3-$ns-vchord-index.txt" && grep -q 'USING vchordrq' "$OUT/ac3-$ns-vchord-index.txt" || { log "FAIL vchord index usage"; return 1; }
  grep -qiE 'hnsw|ivfflat' "$OUT/ac3-$ns-vchord-index.txt" && { log "FAIL pgvector index type appeared"; return 1; }
  log "ok   ac3-$ns-vchord-index (vchordrq index scan on synthetic vectors)"
}

check_bundled_keycloak() {
  record "ac1-keycloak-ready" proxy_get "$NS" "$RELEASE-keycloak:management" /health/ready
  record "ac1-keycloak-discovery" proxy_get "$NS" "$RELEASE-keycloak:http" /realms/owl-mast/.well-known/openid-configuration
  grep -q "\"issuer\":\"http://$RELEASE-keycloak:8080/realms/owl-mast\"" "$OUT/ac1-keycloak-discovery.txt" && log "ok   ac1-keycloak-issuer" || { log "FAIL keycloak issuer"; return 1; }
}

step_bundled_bundled() {
  install_combo bundled-bundled
  record ac1-probes k get deploy -n "$NS" -o jsonpath='{range .items[*]}{.metadata.name}{" startup="}{.spec.template.spec.containers[0].startupProbe.httpGet.path}{.spec.template.spec.containers[0].startupProbe.exec.command}{" readiness="}{.spec.template.spec.containers[0].readinessProbe.httpGet.path}{.spec.template.spec.containers[0].readinessProbe.exec.command}{"\n"}{end}'
  check_bundled_keycloak
  check_shared_postgres "$NS" "$RELEASE-postgresql"
  # Explicit re-provisioning on an already initialised volume (R2): idempotent, nothing dropped, Keycloak schema intact.
  record provision-keycloak-upgrade h upgrade "$RELEASE" "$CHART" -n "$NS" --wait --timeout 10m --reuse-values --set postgresql.provisionKeycloakDatabase=true
  record provision-keycloak-job k -n "$NS" get job "$RELEASE-postgresql-provision-keycloak" -o jsonpath='{.status.succeeded} {.status.failed}{"\n"}'
  grep -q '^1 ' "$OUT/provision-keycloak-job.txt" || { log "FAIL provisioning job did not succeed exactly once"; return 1; }
  record provision-keycloak-job-log k -n "$NS" logs "job/$RELEASE-postgresql-provision-keycloak"
  grep -qiE 'CREATE ROLE|CREATE DATABASE' "$OUT/provision-keycloak-job-log.txt" && { log "FAIL provisioning recreated an existing role or database"; return 1; }
  record provision-keycloak-schema-intact pg_exec "$NS" "$RELEASE-postgresql" OWLMAST_KEYCLOAK keycloak "select count(*) > 10 from information_schema.tables where table_schema='public'"
  grep -qx 't' "$OUT/provision-keycloak-schema-intact.txt" && log "ok   provision-keycloak-idempotent (existing role/database kept, grants re-applied, schema intact)" || { log "FAIL keycloak schema after provisioning"; return 1; }
}

step_persistence() {
  log "== persistence, pod replacement, uninstall retention, reinstall with existing claim, upgrade (T3)"
  local pvc="$RELEASE-postgresql-data"
  record t3-pvc-before k get pvc "$pvc" -n "$NS" -o jsonpath='{.metadata.uid} {.spec.volumeName} {.status.phase} {.metadata.annotations.helm\.sh/resource-policy}'
  local uid; uid="$(k get pvc "$pvc" -n "$NS" -o jsonpath='{.metadata.uid}')"
  local pv; pv="$(k get pvc "$pvc" -n "$NS" -o jsonpath='{.spec.volumeName}')"
  record t3-pv-reclaim k get pv "$pv" -o jsonpath='{.spec.persistentVolumeReclaimPolicy} {.spec.storageClassName}'
  grep -q 'Retain owl-mast-local-retain' "$OUT/t3-pv-reclaim.txt" || { log "FAIL PV reclaim policy"; return 1; }
  # Re-entry keeps earlier synthetic rows: the marker is inserted only if absent and the count is recorded, never reset.
  record t3-write-marker pg_exec "$NS" "$RELEASE-postgresql" OWLMAST_APP owlmast "create table if not exists qualification.persistence(marker text primary key, written_at timestamptz default now()); insert into qualification.persistence(marker) values ('om-01-02-marker') on conflict do nothing; select count(*) from qualification.persistence"
  record t3-delete-pod k delete pod -n "$NS" -l "app.kubernetes.io/instance=$RELEASE,app.kubernetes.io/component=postgresql" --wait=true
  record t3-pod-replaced wait_ready "$NS" "$RELEASE-postgresql" 300
  record t3-marker-after-replacement pg_exec "$NS" "$RELEASE-postgresql" OWLMAST_APP owlmast "select marker from qualification.persistence"
  grep -q om-01-02-marker "$OUT/t3-marker-after-replacement.txt" || { log "FAIL marker lost on pod replacement"; return 1; }
  record t3-uninstall h uninstall "$RELEASE" -n "$NS" --wait
  record t3-pvc-after-uninstall k get pvc "$pvc" -n "$NS" -o jsonpath='{.metadata.uid} {.status.phase}'
  grep -q "$uid Bound" "$OUT/t3-pvc-after-uninstall.txt" && log "ok   t3-pvc-retained-same-uid" || { log "FAIL PVC not retained"; return 1; }
  record t3-nothing-else-left k get all -n "$NS"
  install_combo bundled-bundled-reinstall --set postgresql.persistence.existingClaim="$pvc"
  record t3-marker-after-reinstall pg_exec "$NS" "$RELEASE-postgresql" OWLMAST_APP owlmast "select marker from qualification.persistence"
  grep -q om-01-02-marker "$OUT/t3-marker-after-reinstall.txt" && log "ok   t3-data-survives-uninstall-reinstall" || { log "FAIL marker lost across uninstall"; return 1; }
  record t3-upgrade h upgrade "$RELEASE" "$CHART" -n "$NS" --wait --timeout 15m --reuse-values --set backend.resources.requests.cpu=300m
  record t3-pvc-after-upgrade k get pvc "$pvc" -n "$NS" -o jsonpath='{.metadata.uid} {.status.phase}'
  grep -q "$uid Bound" "$OUT/t3-pvc-after-upgrade.txt" || { log "FAIL PVC changed on upgrade"; return 1; }
  record t3-marker-after-upgrade pg_exec "$NS" "$RELEASE-postgresql" OWLMAST_APP owlmast "select marker from qualification.persistence"
  grep -q om-01-02-marker "$OUT/t3-marker-after-upgrade.txt" && log "ok   t3-data-survives-upgrade" || { log "FAIL marker lost on upgrade"; return 1; }
  record t3-history h history "$RELEASE" -n "$NS"
  record t3-uninstall-2 h uninstall "$RELEASE" -n "$NS" --wait
  record t3-pvc-retained-final k get pvc -n "$NS"
}

step_bundled_external() {
  # Bundled PostgreSQL with an external issuer must need no Keycloak credentials at all (R2): the
  # Keycloak Secret names are pointed at names that do not exist; any remaining reference would
  # leave a pod in CreateContainerConfigError instead of reaching readiness.
  install_combo bundled-external --set identity.bundled=false \
    --set identity.external.issuerUri="http://external-keycloak.$EXT_NS.svc:8080/realms/owl-mast" \
    --set identity.keycloak.database.existingSecret=absent-keycloak-db-secret \
    --set identity.keycloak.bootstrapExistingSecret=absent-keycloak-bootstrap-secret
  record bundled-external-no-keycloak k get deploy -n "$NS" -o name
  grep -q keycloak "$OUT/bundled-external-no-keycloak.txt" && { log "FAIL keycloak rendered"; return 1; } || log "ok   bundled-external-no-bundled-keycloak"
  record bundled-external-secret-references k get deploy -n "$NS" -o jsonpath='{range .items[*]}{range .spec.template.spec.containers[*].env[*]}{.valueFrom.secretKeyRef.name}{"\n"}{end}{end}'
  grep -q 'absent-keycloak' "$OUT/bundled-external-secret-references.txt" && { log "FAIL a Keycloak Secret is still referenced with the identity bundle disabled"; return 1; }
  log "ok   bundled-external-no-keycloak-credentials (only $(sort -u "$OUT/bundled-external-secret-references.txt" | grep -v '^\$' | grep -c .) distinct Secret references, none for Keycloak)"
  record bundled-external-issuer-env k get deploy "$RELEASE-backend" -n "$NS" -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="OWLMAST_IDENTITY_ISSUER_URI")].value}'
  record bundled-external-uninstall h uninstall "$RELEASE" -n "$NS" --wait
}

step_external_bundled() {
  install_combo external-bundled --set database.bundled=false --set database.existingSecret=owl-mast-external-db \
    --set database.external.host="external-postgresql.$EXT_NS.svc" --set database.external.sslMode=disable \
    --set identity.keycloak.database.existingSecret=owl-mast-external-keycloak-db \
    --set identity.keycloak.database.external.host="external-postgresql.$EXT_NS.svc" --set identity.keycloak.database.external.sslMode=disable
  # Only deployments are checked: the retained claim from the bundled run is expected to persist (T3).
  record external-bundled-no-postgres k get deploy -n "$NS" -o name
  grep -q postgresql "$OUT/external-bundled-no-postgres.txt" && { log "FAIL bundled postgresql rendered"; return 1; } || log "ok   external-bundled-no-bundled-postgresql"
  record external-bundled-retained-claim-untouched k get pvc -n "$NS" -o name
  check_bundled_keycloak
  check_shared_postgres "$EXT_NS" external-postgresql
  record external-bundled-uninstall h uninstall "$RELEASE" -n "$NS" --wait
}

step_external_external() {
  install_combo external-external --set database.bundled=false --set database.existingSecret=owl-mast-external-db \
    --set database.external.host="external-postgresql.$EXT_NS.svc" --set database.external.sslMode=disable \
    --set identity.bundled=false --set identity.external.issuerUri="http://external-keycloak.$EXT_NS.svc:8080/realms/owl-mast"
  record external-external-only-backend k get deploy,pvc,svc -n "$NS" -o name
  record external-external-uninstall h uninstall "$RELEASE" -n "$NS" --wait
}

step_failure_paths() {
  log "== failure paths: missing secret key, wrong issuer"
  ensure_broken_secret
  if h upgrade --install "$RELEASE-broken" "$CHART" -n "$NS" --wait --timeout 90s \
      --set backend.image.tag="$BACKEND_IMAGE_TAG" --set backend.image.pullPolicy=Never --set commonLabels."owlmast\.aisquad\.com/run"="$RUN_ID" \
      --set database.bundled=false --set database.external.host="external-postgresql.$EXT_NS.svc" --set database.external.sslMode=disable \
      --set database.existingSecret=owl-mast-db-broken \
      --set identity.bundled=false --set identity.external.issuerUri="http://external-keycloak.$EXT_NS.svc:8080/realms/owl-mast" \
      >"$OUT/fail-missing-secret-key-install.txt" 2>&1; then
    log "FAIL install succeeded with a Secret missing the password key"; return 1
  fi
  record fail-missing-secret-key-pods k get pods -n "$NS" -l app.kubernetes.io/instance="$RELEASE-broken" -o custom-columns=NAME:.metadata.name,STATUS:.status.containerStatuses[0].state.waiting.reason
  grep -q CreateContainerConfigError "$OUT/fail-missing-secret-key-pods.txt" && log "ok   fail-missing-secret-key (CreateContainerConfigError, nothing started)" || { log "FAIL unexpected pod state"; return 1; }
  record fail-missing-secret-key-uninstall h uninstall "$RELEASE-broken" -n "$NS" --wait
  if h upgrade --install "$RELEASE-wrongidp" "$CHART" -n "$NS" --wait --timeout 150s \
      --set backend.image.tag="$BACKEND_IMAGE_TAG" --set backend.image.pullPolicy=Never --set commonLabels."owlmast\.aisquad\.com/run"="$RUN_ID" \
      --set database.bundled=false --set database.existingSecret=owl-mast-external-db --set database.external.host="external-postgresql.$EXT_NS.svc" --set database.external.sslMode=disable \
      --set identity.bundled=false --set identity.external.issuerUri="http://external-keycloak.$EXT_NS.svc:8080/realms/does-not-exist" \
      >"$OUT/fail-wrong-issuer-install.txt" 2>&1; then
    log "FAIL install became ready with a non-existent realm"; return 1
  fi
  record fail-wrong-issuer-pods k get pods -n "$NS" -l app.kubernetes.io/instance="$RELEASE-wrongidp" -o custom-columns=NAME:.metadata.name,READY:.status.containerStatuses[0].ready,RESTARTS:.status.containerStatuses[0].restartCount
  # The Service has no endpoints while readiness is DOWN, so read the probe through the pod proxy; the
  # verbose transcript carries the backend's own 503 status and body, which is what is asserted.
  local pod; pod="$(k get pods -n "$NS" -l app.kubernetes.io/instance="$RELEASE-wrongidp" -o jsonpath='{.items[0].metadata.name}')"
  record fail-wrong-issuer-no-endpoints k get endpointslices -n "$NS" -l kubernetes.io/service-name="$RELEASE-wrongidp-backend" -o jsonpath='{.items[*].endpoints[*].conditions.ready}'
  record_any fail-wrong-issuer-readiness k get --raw "/api/v1/namespaces/$NS/pods/$pod:8080/proxy/actuator/health/readiness" -v=8
  record fail-wrong-issuer-liveness k get --raw "/api/v1/namespaces/$NS/pods/$pod:8080/proxy/actuator/health/liveness"
  assert_proxied_readiness_down "$OUT/fail-wrong-issuer-readiness.txt" && grep -qx false "$OUT/fail-wrong-issuer-no-endpoints.txt" && grep -q '"status":"UP"' "$OUT/fail-wrong-issuer-liveness.txt" \
    && log "ok   fail-wrong-issuer (backend readiness body 503 DOWN, endpoint not ready, liveness UP)" || { log "FAIL wrong issuer readiness evidence"; return 1; }
  record fail-wrong-issuer-uninstall h uninstall "$RELEASE-wrongidp" -n "$NS" --wait
}

step_inventory() {
  record inventory-all k get all,pvc,pv,secrets,configmap,resourcequota -A -l "$RUN_LABEL" -o custom-columns=KIND:.kind,NS:.metadata.namespace,NAME:.metadata.name,CREATED:.metadata.creationTimestamp
  record inventory-pv k get pv -o custom-columns=NAME:.metadata.name,CLAIM:.spec.claimRef.name,NS:.spec.claimRef.namespace,RECLAIM:.spec.persistentVolumeReclaimPolicy,CLASS:.spec.storageClassName,PHASE:.status.phase
  record inventory-helm h list -A
}

ALL_STEPS=(prepare fixtures bundled-bundled persistence bundled-external external-bundled external-external failure-paths inventory)
main() {
  local steps=("$@") step
  [ ${#steps[@]} -eq 0 ] && steps=(all)
  local expanded=()
  for step in "${steps[@]}"; do
    case "$step" in
      all) expanded+=("${ALL_STEPS[@]}") ;;
      prepare|fixtures|bundled-bundled|persistence|bundled-external|external-bundled|external-external|failure-paths|inventory) expanded+=("$step") ;;
      *) echo "unknown step $step"; exit 2 ;;
    esac
  done
  preflight "${expanded[@]}"
  for step in "${expanded[@]}"; do "step_${step//-/_}"; done
  log "qualification steps complete: ${expanded[*]}"
}
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then main "$@"; fi
