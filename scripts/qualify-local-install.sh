#!/usr/bin/env bash
# OM-01.02-T3/T4 runtime qualification on the disposable local Kind target.
# Every cluster command uses the explicit, run-local KUBECONFIG; the default kubeconfig is never read.
# Synthetic secrets are generated into the cluster only (never printed, logged or written to Git).
# Usage: KUBECONFIG=<run kubeconfig> OWLMAST_HELM=<helm4> EVIDENCE_DIR=<private dir> scripts/qualify-local-install.sh [step...]
# Steps: prepare fixtures bundled-bundled persistence bundled-external external-bundled external-external failure-paths all
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
RUN_LABEL="owlmast.aisquad.com/run=om-01-02-local-20261107-01"
BACKEND_IMAGE_TAG="${BACKEND_IMAGE_TAG:-0.1.0}"
OUT="$EVIDENCE_DIR/runtime"
mkdir -p "$OUT"
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
owned_or_absent() { # owned_or_absent <namespace> <kind> <name>: fail closed when a named resource exists without this run's label
  if k -n "$1" get "$2" "$3" >/dev/null 2>&1; then
    k -n "$1" get "$2" "$3" -o jsonpath='{.metadata.labels}' | grep -q 'owlmast.aisquad.com/run":"om-01-02-local-20261107-01' \
      || { log "$2 $1/$3 exists without this run's ownership label: refusing to adopt, replace or delete it"; exit 2; }
    log "$2 $1/$3 exists and is owned by this run (reused)"
  fi
}
ensure_secret() { # ensure_secret <namespace> <name> <username>: random password, created only if absent
  local ns="$1" name="$2" user="$3"
  if k -n "$ns" get secret "$name" >/dev/null 2>&1; then
    log "secret $ns/$name exists (kept)"; return
  fi
  local password; password="$(openssl rand -base64 30 | tr -d '/+=' | cut -c1-32)"
  k -n "$ns" create secret generic "$name" --from-literal=username="$user" --from-literal=password="$password" >/dev/null
  k -n "$ns" label secret "$name" "$RUN_LABEL" >/dev/null
  log "secret $ns/$name created (synthetic, value not recorded)"
}
replicate_secret() { # replicate_secret <src-ns> <src-name> <dst-ns> <dst-name>: same values, never printed
  local src_ns="$1" src="$2" dst_ns="$3" dst="$4"
  if k -n "$dst_ns" get secret "$dst" >/dev/null 2>&1; then log "secret $dst_ns/$dst exists (kept)"; return; fi
  k -n "$src_ns" get secret "$src" -o json \
    | python3 -c 'import json,sys; s=json.load(sys.stdin); print(json.dumps({"apiVersion":"v1","kind":"Secret","type":s["type"],"metadata":{"name":sys.argv[1],"namespace":sys.argv[2],"labels":{"owlmast.aisquad.com/run":"om-01-02-local-20261107-01"}},"data":s["data"]}))' "$dst" "$dst_ns" \
    | k apply -f - >/dev/null
  log "secret $dst_ns/$dst replicated from $src_ns/$src (synthetic, value not recorded)"
}
pg_exec() { # pg_exec <namespace> <deployment> <role-env-prefix> <database> <sql...>
  local ns="$1" deploy="$2" prefix="$3" db="$4"; shift 4
  k -n "$ns" exec "deploy/$deploy" -- sh -c "PGPASSWORD=\"\$${prefix}_PASSWORD\" psql -v ON_ERROR_STOP=1 -h 127.0.0.1 -U \"\$${prefix}_USERNAME\" -d '$db' -Atc \"$*\""
}
proxy_get() { # proxy_get <namespace> <service:port> <path>
  k get --raw "/api/v1/namespaces/$1/services/$2/proxy$3"
}
wait_ready() { # wait_ready <namespace> <deployment> <seconds>
  k -n "$1" rollout status "deploy/$2" --timeout="$3s"
}

step_prepare() {
  log "== prepare target (cluster/context $CONTEXT)"
  record target-nodes k get nodes -o wide
  record target-storageclass-before k get storageclass
  if k get storageclass owl-mast-local-retain >/dev/null 2>&1; then
    k get storageclass owl-mast-local-retain -o jsonpath='{.metadata.labels}' | grep -q om-01-02-local-20261107-01 \
      || { log "StorageClass owl-mast-local-retain exists without our run label: refusing to adopt"; exit 2; }
  fi
  record apply-storageclass k apply -f "$ROOT/deploy/local-kind/storageclass.yaml"
  for ns in "$NS" "$EXT_NS"; do
    if k get namespace "$ns" >/dev/null 2>&1; then
      k get namespace "$ns" -o jsonpath='{.metadata.labels}' | grep -q om-01-02-local-20261107-01 \
        || { log "namespace $ns exists without our run label: refusing to adopt"; exit 2; }
    fi
  done
  record apply-namespaces k apply -f "$ROOT/deploy/local-kind/namespaces.yaml"
  # Re-entry on an existing target: retained claims and any lingering release objects must be this run's own.
  owned_or_absent "$NS" pvc "$RELEASE-postgresql-data"
  owned_or_absent "$EXT_NS" pvc external-postgresql-data
  owned_or_absent "$EXT_NS" deployment external-postgresql
  owned_or_absent "$EXT_NS" deployment external-keycloak
  for rel in "$RELEASE" "$RELEASE-broken" "$RELEASE-wrongidp"; do
    if h status "$rel" -n "$NS" >/dev/null 2>&1; then
      owned_or_absent "$NS" deployment "$rel-backend"
      log "release $rel exists in $NS (owned by this run); it is upgraded or uninstalled by the steps below"
    fi
  done
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
  record secrets-inventory k get secrets -A -l "$RUN_LABEL" -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name,KEYS:.data
  sed -i -E 's/(KEYS +)(.*)/\1<redacted>/; s/map\[.*\]/<redacted>/' "$OUT/secrets-inventory.txt"
  record quotas k get resourcequota -A
}

step_fixtures() {
  log "== synthetic external fixtures in $EXT_NS"
  h template external "$CHART" --set fullnameOverride=external -s templates/postgresql-init-configmap.yaml \
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
    --set commonLabels."owlmast\.aisquad\.com/run"=om-01-02-local-20261107-01 \
    --set postgresql.persistence.storageClass=owl-mast-local-retain "$@"
  record "$name-pods" k get pods,pvc -n "$NS" -o wide
  record "$name-backend-readiness" proxy_get "$NS" "$RELEASE-backend:http" /actuator/health/readiness
  grep -q '"status":"UP"' "$OUT/$name-backend-readiness.txt" && log "ok   $name-backend-readiness-up" || { log "FAIL $name readiness not UP"; return 1; }
  record "$name-backend-liveness" proxy_get "$NS" "$RELEASE-backend:http" /actuator/health/liveness
  record "$name-helm-status" h status "$RELEASE" -n "$NS"
}

check_shared_postgres() { # check_shared_postgres <namespace> <deployment>  (AC3 on whichever instance is the shared one)
  local ns="$1" deploy="$2"
  record "ac3-$ns-app-not-superuser" pg_exec "$ns" "$deploy" OWLMAST_APP owlmast "select current_user, rolsuper, rolcreatedb, rolcreaterole from pg_roles where rolname = current_user"
  grep -q 'owlmast_app|f|f|f' "$OUT/ac3-$ns-app-not-superuser.txt" || { log "FAIL app principal privileges"; return 1; }
  record "ac3-$ns-keycloak-not-superuser" pg_exec "$ns" "$deploy" OWLMAST_KEYCLOAK keycloak "select current_user, rolsuper, rolcreatedb, rolcreaterole from pg_roles where rolname = current_user"
  grep -q 'keycloak_app|f|f|f' "$OUT/ac3-$ns-keycloak-not-superuser.txt" || { log "FAIL keycloak principal privileges"; return 1; }
  if pg_exec "$ns" "$deploy" OWLMAST_APP keycloak "select 1" >"$OUT/ac3-$ns-app-cannot-connect-keycloak-db.txt" 2>&1; then
    log "FAIL owlmast_app connected to the keycloak database"; return 1
  else log "ok   ac3-$ns-app-cannot-connect-keycloak-db (permission denied as required)"; fi
  if pg_exec "$ns" "$deploy" OWLMAST_KEYCLOAK owlmast "select 1" >"$OUT/ac3-$ns-keycloak-cannot-connect-owlmast-db.txt" 2>&1; then
    log "FAIL keycloak_app connected to the owlmast database"; return 1
  else log "ok   ac3-$ns-keycloak-cannot-connect-owlmast-db (permission denied as required)"; fi
  record "ac3-$ns-extensions" pg_exec "$ns" "$deploy" OWLMAST_APP owlmast "select extname||'='||extversion from pg_extension where extname in ('vchord','vector') order by 1"
  grep -q 'vchord=1.1.1' "$OUT/ac3-$ns-extensions.txt" && grep -q 'vector=0.8.2' "$OUT/ac3-$ns-extensions.txt" || { log "FAIL extensions"; return 1; }
  record "ac3-$ns-keycloak-schema-present" pg_exec "$ns" "$deploy" OWLMAST_KEYCLOAK keycloak "select count(*) > 10 from information_schema.tables where table_schema='public'"
  grep -qx 't' "$OUT/ac3-$ns-keycloak-schema-present.txt" || { log "FAIL keycloak schema"; return 1; }
  record "ac3-$ns-flyway-history" pg_exec "$ns" "$deploy" OWLMAST_APP owlmast "select version||'|'||success from flyway_schema_history order by installed_rank"
  grep -q '^001|true$' "$OUT/ac3-$ns-flyway-history.txt" || { log "FAIL flyway history"; return 1; }
  # VectorChord index usage on synthetic data with the application principal (AC3).
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
  record t3-delete-pod k delete pod -n "$NS" -l app.kubernetes.io/component=postgresql --wait=true
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
  install_combo bundled-external --set identity.bundled=false \
    --set identity.external.issuerUri="http://external-keycloak.$EXT_NS.svc:8080/realms/owl-mast"
  record bundled-external-no-keycloak k get deploy -n "$NS" -o name
  grep -q keycloak "$OUT/bundled-external-no-keycloak.txt" && { log "FAIL keycloak rendered"; return 1; } || log "ok   bundled-external-no-bundled-keycloak"
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
  k -n "$NS" create secret generic owl-mast-db-broken --from-literal=username=owlmast_app >/dev/null 2>&1 || true
  k -n "$NS" label secret owl-mast-db-broken "$RUN_LABEL" --overwrite >/dev/null
  if h upgrade --install "$RELEASE-broken" "$CHART" -n "$NS" --wait --timeout 90s \
      --set backend.image.tag="$BACKEND_IMAGE_TAG" --set backend.image.pullPolicy=Never \
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
      --set backend.image.tag="$BACKEND_IMAGE_TAG" --set backend.image.pullPolicy=Never \
      --set database.bundled=false --set database.existingSecret=owl-mast-external-db --set database.external.host="external-postgresql.$EXT_NS.svc" --set database.external.sslMode=disable \
      --set identity.bundled=false --set identity.external.issuerUri="http://external-keycloak.$EXT_NS.svc:8080/realms/does-not-exist" \
      >"$OUT/fail-wrong-issuer-install.txt" 2>&1; then
    log "FAIL install became ready with a non-existent realm"; return 1
  fi
  record fail-wrong-issuer-pods k get pods -n "$NS" -l app.kubernetes.io/instance="$RELEASE-wrongidp" -o custom-columns=NAME:.metadata.name,READY:.status.containerStatuses[0].ready,RESTARTS:.status.containerStatuses[0].restartCount
  # The Service has no endpoints while readiness is DOWN, so read the probe through the pod proxy.
  local pod; pod="$(k get pods -n "$NS" -l app.kubernetes.io/instance="$RELEASE-wrongidp" -o jsonpath='{.items[0].metadata.name}')"
  record fail-wrong-issuer-no-endpoints k get endpointslices -n "$NS" -l kubernetes.io/service-name="$RELEASE-wrongidp-backend" -o jsonpath='{.items[*].endpoints[*].conditions.ready}'
  record_any fail-wrong-issuer-readiness k get --raw "/api/v1/namespaces/$NS/pods/$pod:8080/proxy/actuator/health/readiness"
  record fail-wrong-issuer-liveness k get --raw "/api/v1/namespaces/$NS/pods/$pod:8080/proxy/actuator/health/liveness"
  # The readiness probe answers 503; the API proxy surfaces that as ServiceUnavailable without a body.
  grep -qE '"status":"DOWN"|ServiceUnavailable' "$OUT/fail-wrong-issuer-readiness.txt" && grep -qx false "$OUT/fail-wrong-issuer-no-endpoints.txt" \
    && log "ok   fail-wrong-issuer (readiness 503/DOWN, no ready endpoints, never ready)" || { log "FAIL wrong issuer readiness"; return 1; }
  record fail-wrong-issuer-uninstall h uninstall "$RELEASE-wrongidp" -n "$NS" --wait
}

step_inventory() {
  record inventory-all k get all,pvc,pv,secrets,configmap,resourcequota -A -l "$RUN_LABEL" -o custom-columns=KIND:.kind,NS:.metadata.namespace,NAME:.metadata.name,CREATED:.metadata.creationTimestamp
  record inventory-pv k get pv -o custom-columns=NAME:.metadata.name,CLAIM:.spec.claimRef.name,NS:.spec.claimRef.namespace,RECLAIM:.spec.persistentVolumeReclaimPolicy,CLASS:.spec.storageClassName,PHASE:.status.phase
  record inventory-helm h list -A
}

steps=("$@"); [ ${#steps[@]} -eq 0 ] && steps=(all)
for step in "${steps[@]}"; do
  case "$step" in
    all) step_prepare; step_fixtures; step_bundled_bundled; step_persistence; step_bundled_external; step_external_bundled; step_external_external; step_failure_paths; step_inventory ;;
    prepare) step_prepare ;; fixtures) step_fixtures ;; bundled-bundled) step_bundled_bundled ;; persistence) step_persistence ;;
    bundled-external) step_bundled_external ;; external-bundled) step_external_bundled ;; external-external) step_external_external ;;
    failure-paths) step_failure_paths ;; inventory) step_inventory ;;
    *) echo "unknown step $step"; exit 2 ;;
  esac
done
log "qualification steps complete: ${steps[*]}"
