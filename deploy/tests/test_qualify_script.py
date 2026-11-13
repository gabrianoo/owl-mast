"""Stub-harness tests for scripts/qualify-local-install.sh (OM-01.02 review R3/R4/R5).

`kubectl` and `helm` are replaced by stubs on PATH that answer from a declared "world" of resource
ownership states and record every invocation. No cluster is touched. The tests prove that a foreign,
unlabelled or unreadable resource refuses the whole invocation before any mutating call, that direct
step entry is preflighted too, that a sentinel Secret value never reaches evidence or output on
success, failure or interruption, and that the isolation and readiness evaluators accept only the
intended PostgreSQL denial / backend 503 and reject transport, authentication and generic failures.
"""

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "qualify-local-install.sh"
RUN_ID = "om-01-02-local-20261107-01"
SENTINEL = "SENTINEL-SECRET-VALUE-9f3a7c"
CHART = REPO / "deploy" / "helm" / "owl-mast"
HELM = os.environ.get("OWLMAST_HELM") or shutil.which("helm")
RUN_LABEL_KEY = "owlmast.aisquad.com/run"
COMPONENTS = ("backend", "postgresql", "keycloak")  # the components whose pods the script proves


def rendered_pod_run_labels():
    """component -> whether the pod template the CHART renders carries the run label, when the label is set the way the
    qualification script sets it (commonLabels). The real Helm renders it; None when no Helm 4 is available."""
    if HELM is None:
        return None
    import yaml
    r = subprocess.run([HELM, "template", "owl-mast", str(CHART), "--set", f"commonLabels.{RUN_LABEL_KEY.replace('.', chr(92) + '.')}={RUN_ID}"],
                       capture_output=True, text=True, check=False)
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    out = {}
    for doc in yaml.safe_load_all(r.stdout):
        if doc and doc["kind"] == "Deployment":
            comp = doc["metadata"]["labels"]["app.kubernetes.io/component"]
            if doc["metadata"]["labels"].get(RUN_LABEL_KEY) != RUN_ID:
                raise AssertionError(f"the {comp} Deployment itself must carry the run label: the ownership proof ends there")
            out[comp] = doc["spec"]["template"]["metadata"]["labels"].get(RUN_LABEL_KEY) == RUN_ID
    return out


def template_pod_run_labels():
    """The same answer read from the template sources (no Helm): does the pod template include commonLabels?"""
    out = {}
    for comp in COMPONENTS:
        text = (CHART / "templates" / f"{comp}-deployment.yaml").read_text()
        pod_metadata = text.split("\n  template:\n", 1)[1].split("\n    spec:\n", 1)[0]
        out[comp] = ".Values.commonLabels" in pod_metadata or 'include "owl-mast.labels"' in pod_metadata
    return out


# The stub world answers the labels of the REAL rendered objects (review 5866834124, comment 4544473145): a stub that
# labelled every pod hid that the PostgreSQL pods have no run label, which made the script refuse them on a cluster.
POD_RUN_LABELS = rendered_pod_run_labels() or template_pod_run_labels()
UNLABELLED_COMPONENTS = sorted(c for c in COMPONENTS if not POD_RUN_LABELS[c])

# The migrations of this checkout (V001__..., V002__...): what the backend built from it applies and what the script requires.
MIGRATIONS = sorted(p.name[1:].split("__", 1)[0] for p in (REPO / "backend" / "src" / "main" / "resources" / "db" / "migration").glob("V*__*.sql"))

MUTATING = re.compile(r"(^| )(create|apply|label|annotate|patch|delete|exec|rollout|upgrade|uninstall|install)( |$)")

KUBECTL_STUB = r'''#!/usr/bin/env bash
# Stub kubectl: answers ownership queries from $STUB_WORLD (lines: kind ns name state), records calls.
args="$*"
printf '%s\n' "$args" >> "$STUB_CALLS"
if [ -n "${STUB_FAIL_ON:-}" ] && [[ "$args" =~ $STUB_FAIL_ON ]]; then echo "stub: injected failure" >&2; exit 1; fi
if [ -n "${STUB_INTERRUPT_ON:-}" ] && [[ "$args" =~ $STUB_INTERRUPT_ON ]]; then
  pid=$PPID  # interrupt this stub's own ancestor script only (never another invocation on the machine)
  while [ "$pid" -gt 1 ]; do
    if tr '\0' ' ' </proc/$pid/cmdline 2>/dev/null | grep -q 'qualify-local-install.sh'; then kill -TERM "$pid"; break; fi
    pid=$(awk '/^PPid/{print $2}' /proc/$pid/status 2>/dev/null || echo 1)
  done
  exit 1
fi
state_of() { # kind ns name
  awk -v k="$1" -v n="$2" -v m="$3" '$1==k && $2==n && $3==m {print $4; found=1} END {if (!found) print "absent"}' "$STUB_WORLD"
}
ns="-"; set -- "$@"; argv=("$@")
for ((i=0;i<${#argv[@]};i++)); do [ "${argv[$i]}" = "-n" ] && ns="${argv[$((i+1))]}"; done
# Discovery: `get --raw /apis` and `get --raw /apis/gateway.networking.k8s.io/v1` answer typed documents from the world line
# `discovery - gateway <current|nogateway|stale|forbidden|unavailable|malformed|wrongkind|aggregated|noresource|wronggv>`; no line = current.
# When STUB_DISCOVERY_SERVER is set, these two reads are forwarded to the REAL kubectl ($STUB_REAL_KUBECTL) against that
# loopback server with --kubeconfig=/dev/null, so the actual client behaviour is what the script sees.
if [[ "$args" == *" get --raw /apis"* ]]; then
  path="$(sed -E 's/.* get --raw ([^ ]+).*/\1/' <<<"$args")"
  if [ -n "${STUB_DISCOVERY_SERVER:-}" ]; then
    exec "$STUB_REAL_KUBECTL" --kubeconfig=/dev/null --server="$STUB_DISCOVERY_SERVER" --cache-dir="$STUB_CACHE_DIR" --request-timeout=10s get --raw "$path"
  fi
  state="$(state_of discovery - gateway)"; [ "$state" = absent ] && state=current
  groups='{"kind":"APIGroupList","apiVersion":"v1","groups":[{"name":"apps","versions":[{"groupVersion":"apps/v1","version":"v1"}],"preferredVersion":{"groupVersion":"apps/v1","version":"v1"}}'
  gw=',{"name":"gateway.networking.k8s.io","versions":[{"groupVersion":"gateway.networking.k8s.io/v1","version":"v1"}],"preferredVersion":{"groupVersion":"gateway.networking.k8s.io/v1","version":"v1"}}'
  if [ "$path" = "/apis" ]; then
    case "$state" in
      nogateway) printf '%s]}' "$groups"; exit 0 ;;
      forbidden) echo 'Error from server (Forbidden): forbidden: User "system:anonymous" cannot get path "/apis"' >&2; exit 1 ;;
      unavailable) echo 'Error from server (ServiceUnavailable): the server is currently unable to handle the request' >&2; exit 1 ;;
      malformed) printf '<html>503 Service Unavailable</html>'; exit 0 ;;
      wrongkind) printf '{"kind":"APIResourceList","apiVersion":"v1","groupVersion":"apps/v1","resources":[]}'; exit 0 ;;
      badname) printf '{"kind":"APIGroupList","apiVersion":"v1","groups":[{"name":["gateway.networking.k8s.io"],"versions":[{"groupVersion":"gateway.networking.k8s.io/v1","version":"v1"}]}]}'; exit 0 ;;
      aggregated) printf '{"kind":"APIGroupDiscoveryList","apiVersion":"apidiscovery.k8s.io/v2","items":[]}'; exit 0 ;;
      *) printf '%s%s]}' "$groups" "$gw"; exit 0 ;;   # current, stale, noresource, wronggv list the group
    esac
  fi
  case "$state" in
    stale) echo 'Error from server (ServiceUnavailable): the server is currently unable to handle the request' >&2; exit 1 ;;
    noresource) printf '{"kind":"APIResourceList","apiVersion":"v1","groupVersion":"gateway.networking.k8s.io/v1","resources":[{"name":"gateways","kind":"Gateway","namespaced":true}]}'; exit 0 ;;
    wronggv) printf '{"kind":"APIResourceList","apiVersion":"v1","groupVersion":"gateway.networking.k8s.io/v1beta1","resources":[{"name":"httproutes","kind":"HTTPRoute","namespaced":true}]}'; exit 0 ;;
    resourceversion) printf '{"kind":"APIResourceList","apiVersion":"v1","groupVersion":"gateway.networking.k8s.io/v1","resources":[{"name":"httproutes","kind":"HTTPRoute","namespaced":true,"version":"v1beta1"}]}'; exit 0 ;;
    noapiversion) printf '{"kind":"APIResourceList","groupVersion":"gateway.networking.k8s.io/v1","resources":[{"name":"httproutes","kind":"HTTPRoute","namespaced":true}]}'; exit 0 ;;
    *) printf '{"kind":"APIResourceList","apiVersion":"v1","groupVersion":"gateway.networking.k8s.io/v1","resources":[{"name":"httproutes","kind":"HTTPRoute","namespaced":true},{"name":"gateways","kind":"Gateway","namespaced":true}]}'; exit 0 ;;
  esac
fi
if [[ "$args" == *" get "* && "$args" == *"--ignore-not-found"* && "$args" == *"metadata.labels.owlmast"* ]]; then
  for ((i=0;i<${#argv[@]};i++)); do if [ "${argv[$i]}" = "get" ]; then kind="${argv[$((i+1))]}"; name="${argv[$((i+2))]}"; fi; done
  [ "$kind" = "httproutes.v1.gateway.networking.k8s.io" ] && kind=httproute
  state="$(state_of "$kind" "$ns" "$name")"
  case "$state" in
    owned) printf '%s|%s' "$name" "$STUB_RUN_ID" ;;
    foreign:unlabelled) printf '%s|' "$name" ;;
    foreign:*) printf '%s|%s' "$name" "${state#foreign:}" ;;
    absent) exit 0 ;;   # --ignore-not-found: NotFound is exit 0 with no output
    kind-unavailable) echo "error: the server doesn't have a resource type \"$kind\"" >&2; exit 1 ;;
    mixed-forbidden) echo "E1107 memcache.go:287] couldn't get resource list for gateway.networking.k8s.io/v1: Forbidden" >&2; echo "error: the server doesn't have a resource type \"$kind\"" >&2; exit 1 ;;
    mixed-unavailable) echo "E1107 memcache.go:287] couldn't get resource list for gateway.networking.k8s.io/v1: the server is currently unable to handle the request" >&2; echo "error: the server doesn't have a resource type \"$kind\"" >&2; exit 1 ;;
    forbidden) echo "Error from server (Forbidden): $kind \"$name\" is forbidden" >&2; exit 1 ;;
    warn-shape) printf 'weird output without separator'; echo "W1107 warnings.go:70] stale discovery cache" >&2; exit 0 ;;
    garbage) printf 'not-the-object'; exit 0 ;;
    *) echo "Unable to connect to the server: dial tcp 10.0.0.1:6443: connect: connection refused" >&2; exit 1 ;;
  esac
  exit 0
fi
# Controller chain world: `pods <ns> <release>-<component> <state>` drives the pod list, the ReplicaSet and the Deployment answers.
# UIDs: deployment dep-<rel>-<comp>, replicaset rs-<rel>-<comp>. States: owned | foreign:unlabelled | foreign:<label> |
# foreign:owner (ReplicaSet named for another release) | foreign:rs-foreign | foreign:rs-missing | foreign:rs-unreadable |
# foreign:uid | foreign:deploy | foreign:ambiguous | foreign:no-controller | error
# The run label of an `owned` pod and ReplicaSet is what the CHART renders for that component: components named in
# $STUB_UNLABELLED_COMPONENTS (derived from the rendered chart by the test module) have none, like the real objects.
lbl_of() { case " ${STUB_UNLABELLED_COMPONENTS:-} " in *" $1 "*) printf '' ;; *) printf '%s' "$STUB_RUN_ID" ;; esac; }
if [[ "$args" == *" get pods -l "* && "$args" == *"ownerReferences"* ]]; then
  sel="$(sed -E 's/.* -l ([^ ]+).*/\1/' <<<"$args")"; rel="${sel#app.kubernetes.io/instance=}"; rel="${rel%%,*}"; comp="${sel##*component=}"
  state="$(state_of pods "$ns" "$rel-$comp")"; pod="$rel-$comp-abc12-xyz"; rs="$rel-$comp-abc12"; uid="rs-$rel-$comp"; lbl="$(lbl_of "$comp")"
  case "$state" in
    absent) exit 0 ;;
    owned|foreign:rs-foreign|foreign:rs-missing|foreign:rs-unreadable|foreign:deploy) printf '%s|%s|ReplicaSet/%s/%s/true \n' "$pod" "$lbl" "$rs" "$uid"; exit 0 ;;
    foreign:owner) printf '%s|%s|ReplicaSet/other-%s-abc12/rs-other/true \n' "$pod" "$lbl" "$comp"; exit 0 ;;
    foreign:uid) printf '%s|%s|ReplicaSet/%s/stale-uid/true \n' "$pod" "$lbl" "$rs"; exit 0 ;;
    foreign:ambiguous) printf '%s|%s|ReplicaSet/%s/%s/true ReplicaSet/%s-old/rs-old/true \n' "$pod" "$lbl" "$rs" "$uid" "$rs"; exit 0 ;;
    foreign:no-controller) printf '%s|%s|ReplicaSet/%s/%s/false \n' "$pod" "$lbl" "$rs" "$uid"; exit 0 ;;
    foreign:unlabelled) printf '%s||ReplicaSet/%s/%s/true \n' "$pod" "$rs" "$uid"; exit 0 ;;
    foreign:*) printf '%s|%s|ReplicaSet/%s/%s/true \n' "$pod" "${state#foreign:}" "$rs" "$uid"; exit 0 ;;
    *) echo "Unable to connect to the server: dial tcp 10.0.0.1:6443: connect: connection refused" >&2; exit 1 ;;
  esac
fi
if [[ "$args" == *" get replicaset "* ]]; then
  rs="$(sed -E 's/.* get replicaset ([^ ]+).*/\1/' <<<"$args")"; base="${rs%-abc12}"; base="${base%-old}"
  if [[ "$rs" == other-* ]]; then printf 'rs-other|%s|Deployment/other-%s/dep-other/true \n' "$STUB_RUN_ID" "${base#other-}"; exit 0; fi
  state="$(state_of pods "$ns" "$base")"; lbl="$(lbl_of "${base##*-}")"
  case "$state" in
    foreign:rs-missing) echo "Error from server (NotFound): replicasets.apps \"$rs\" not found" >&2; exit 1 ;;
    foreign:rs-unreadable) echo "Error from server (Forbidden): replicasets.apps \"$rs\" is forbidden" >&2; exit 1 ;;
    foreign:rs-foreign) printf 'rs-%s|someone-else|Deployment/%s/dep-%s/true \n' "$base" "$base" "$base"; exit 0 ;;
    foreign:deploy) printf 'rs-%s|%s|Deployment/%s-other/dep-%s-other/true \n' "$base" "$lbl" "$base" "$base"; exit 0 ;;
    *) printf 'rs-%s|%s|Deployment/%s/dep-%s/true \n' "$base" "$lbl" "$base" "$base"; exit 0 ;;
  esac
fi
if [[ "$args" == *" get deployment "* && "$args" == *"{.metadata.uid}|"* ]]; then
  dep="$(sed -E 's/.* get deployment ([^ ]+).*/\1/' <<<"$args")"
  state="$(state_of deployment "$ns" "$dep")"
  case "$state" in
    absent) echo "Error from server (NotFound): deployments.apps \"$dep\" not found" >&2; exit 1 ;;
    owned) printf 'dep-%s|%s' "$dep" "$STUB_RUN_ID"; exit 0 ;;
    foreign:*) printf 'dep-%s|%s' "$dep" "${state#foreign:}"; exit 0 ;;
    *) echo "Unable to connect to the server" >&2; exit 1 ;;
  esac
fi
# The retained volume of the persistence step (T3): reclaim policy and class as the qualification's StorageClass gives them.
if [[ "$args" == *" get pv "* && "$args" == *"persistentVolumeReclaimPolicy"* ]]; then printf 'Retain owl-mast-local-retain'; exit 0; fi
if [[ "$args" == *" get secret"* ]]; then
  if [[ "$args" == *"-o json"* || "$args" == *"-o yaml"* || ( "$args" == *".data"* && "$args" != *'$k, $v := .data}}{{$k}}'* ) ]]; then
    printf '{"apiVersion":"v1","kind":"Secret","type":"Opaque","metadata":{"name":"x","namespace":"%s"},"data":{"username":"dXNlcg==","password":"%s"}}\n' "$ns" "$STUB_SENTINEL"
  else
    printf 'owl-mast-test/owl-mast-db type=Opaque keys=[password username ] owner=%s\n' "$STUB_RUN_ID"
  fi
  exit 0
fi
# Backend image identity: the Running pods as custom-columns rows "NAME DELETING" (STUB_BACKEND_PODS) and the container status (STUB_IMAGE_ID).
if [[ "$args" == *"--field-selector=status.phase=Running"* ]]; then printf '%b' "${STUB_BACKEND_PODS:-}"; exit 0; fi
if [[ "$args" == *"].image} {.status.containerStatuses[0].imageID}"* ]]; then printf 'docker.io/owl-mast/backend:stub %s\n' "${STUB_IMAGE_ID:-}"; exit 0; fi
if [[ "$args" == *"{.status.containerStatuses[0].imageID}"* ]]; then printf '%s' "${STUB_IMAGE_ID:-}"; exit 0; fi
# The provisioning hook Job as the cluster serves it: the chart's delete policy (before-hook-creation,hook-succeeded) removes
# the Job and its ConfigMap once the hook succeeded, so a direct read after a successful upgrade is NotFound. The world holds
# a `job` line only for a hook that failed or was kept (the helm stub writes it, see STUB_HOOK).
if [[ "$args" == *" get job "* ]]; then
  job="$(sed -E 's/.* get job ([^ ]+).*/\1/' <<<"$args")"
  if [ "$(state_of job "$ns" "$job")" = absent ]; then echo "Error from server (NotFound): jobs.batch \"$job\" not found" >&2; exit 1; fi
  printf '1 \n'; exit 0
fi
if [[ "$args" == *" logs job/"* ]]; then
  job="$(sed -E 's/.* logs job\/([^ ]+).*/\1/' <<<"$args")"
  if [ "$(state_of job "$ns" "$job")" = absent ]; then echo "error: error from server (NotFound): jobs.batch \"$job\" not found" >&2; exit 1; fi
  printf 'GRANT\n'; exit 0
fi
# Pods of the release that are being deleted (wait_no_terminating_pods): STUB_TERMINATING=<n> reports one for the first n reads.
if [[ "$args" == *" get pods "* && "$args" == *"?(@.metadata.deletionTimestamp)"* ]]; then
  [ "${STUB_TERMINATING_READ:-}" = fail ] && { echo "error: the server is currently unable to handle the request" >&2; exit 1; }
  n=0; [ -e "$STUB_WORLD.terminating" ] && n="$(grep -c . "$STUB_WORLD.terminating")"
  if [ "$n" -lt "${STUB_TERMINATING:-0}" ]; then echo read >> "$STUB_WORLD.terminating"; printf 'owl-mast-fe-keycloak-old-abc12\n'; fi
  exit 0
fi
# Runtime answers for whole-step runs (STUB_RUNTIME=1): what a healthy install returns to the script's observations.
if [ "${STUB_RUNTIME:-}" = 1 ]; then
  if [[ "$args" == *" get --raw /api/v1/namespaces/"* ]]; then
    svc="$(sed -E 's/.*\/services\/([^:\/]+).*/\1/' <<<"$args")"
    if [[ "$args" == *"openid-configuration"* ]]; then printf '{"issuer":"http://%s:8080/realms/owl-mast"}\n' "$svc"; else printf '{"status":"UP"}\n'; fi
    exit 0
  fi
  # The release's Keycloak pods that are not being deleted, as `name deletionTimestamp` lines (keycloak_pod_names): a retired
  # release runs a new pod, unless STUB_RETIRE=same-pod keeps the old one.
  if [[ "$args" == *" get pods "* && "$args" == *"app.kubernetes.io/component=keycloak"* && "$args" == *'{.metadata.name}{" "}{.metadata.deletionTimestamp}'* ]]; then
    rel="$(sed -E 's/.*app\.kubernetes\.io\/instance=([^ ,]+).*/\1/' <<<"$args")"
    if [ -e "$STUB_WORLD.retired" ] && [ "${STUB_RETIRE:-}" != same-pod ]; then printf '%s-keycloak-new-def34 \n' "$rel"; else printf '%s-keycloak-old-abc12 \n' "$rel"; fi
    # STUB_RETIRE=deleting-listed: a pod that is being deleted is also listed, with its deletionTimestamp, before and after.
    if [ "${STUB_RETIRE:-}" = deleting-listed ]; then printf '%s-keycloak-gone-xyz98 2026-11-13T00:29:00Z\n' "$rel"; fi
    exit 0
  fi
  # The Keycloak container environment as `NAME=<secret or empty>` lines (retire_bootstrap_admin). The helm stub marks the
  # release retired when an upgrade sets bootstrapAdmin.enabled=false; STUB_RETIRE=kept leaves the variables in place.
  if [[ "$args" == *" get deploy "*"-keycloak "* && "$args" == *"{.name}={.valueFrom.secretKeyRef.name}"* ]]; then
    rel="$(sed -E 's/.* get deploy ([^ ]+)-keycloak .*/\1/' <<<"$args")"
    printf 'KC_DB=\nKC_DB_USERNAME=%s-keycloak-db\nKC_DB_PASSWORD=%s-keycloak-db\n' "$rel" "$rel"
    if [ ! -e "$STUB_WORLD.retired" ]; then printf 'KC_BOOTSTRAP_ADMIN_USERNAME=%s-keycloak-bootstrap\nKC_BOOTSTRAP_ADMIN_PASSWORD=%s-keycloak-bootstrap\n' "$rel" "$rel"; fi
    exit 0
  fi
  # The release's Deployments and running pods as JSON (retire_bootstrap_admin looks for the bootstrap Secret's name in every
  # field that can carry one). STUB_RETIRE=volume: the environment is clean but a pod still mounts the Secret as a volume.
  if [[ "$args" == *" get deploy,pods "* && "$args" == *"-o json"* ]]; then
    rel="$(sed -E 's/.*app\.kubernetes\.io\/instance=([^ ,]+).*/\1/' <<<"$args")"
    volume=""; [ "${STUB_RETIRE:-}" = volume ] && volume="{\"name\": \"bootstrap\", \"secret\": {\"secretName\": \"$rel-keycloak-bootstrap\"}}"
    printf '{"apiVersion": "v1", "kind": "List", "items": [{"kind": "Deployment", "metadata": {"name": "%s-keycloak"}, "spec": {"template": {"spec": {"containers": [{"name": "keycloak", "env": [{"name": "KC_DB_PASSWORD", "valueFrom": {"secretKeyRef": {"name": "%s-keycloak-db", "key": "password"}}}]}], "volumes": [%s]}}}}]}\n' "$rel" "$rel" "$volume"
    exit 0
  fi
  if [[ "$args" == *" get pods "* && "$args" == *"READY:.status.containerStatuses[0].ready"* ]]; then printf 'NAME READY RESTARTS\npostgresql-abc12-xyz   true   0\n'; exit 0; fi
  if [[ "$args" == *" logs deploy/"* ]]; then printf 'identity bundle disabled; no Keycloak database or principal provisioned\nPostgreSQL init process complete; ready for start up.\n'; exit 0; fi
  if [[ "$args" == *" get pvc "* && "$args" == *"{.metadata.uid}"* ]]; then
    if [[ "$args" == *"metadata.labels"* ]]; then printf 'pvc-uid-1 Bound %s\n' "${STUB_FE_RUN_ID:-}"; elif [[ "$args" == *"{.status.phase}"* ]]; then printf 'pvc-uid-1 Bound\n'; else printf 'pvc-uid-1'; fi
    exit 0
  fi
  if [[ "$args" == *" exec "* && "$args" == *"from pg_database where datname="* ]]; then printf '0\n0\n'; exit 0; fi
  if [[ "$args" == *" exec "* && "$args" == *"qualification_marker"* ]]; then printf 'before-enable\n'; exit 0; fi
fi
if [[ "$args" == *" exec "* ]]; then
  db="$(sed -E "s/.* -d '([^']+)'.*/\1/" <<<"$args")"
  # The Keycloak role/database identifiers (keycloak_db_identity). STUB_KC_IDENTITY_<n> is the answer after n successful
  # provisioning upgrades (counted by the helm stub); unset = the same identifiers every time; empty = the read fails.
  if [[ "$args" == *"'role='||r.oid"* ]]; then
    n=0; [ -e "$STUB_WORLD.provisioned" ] && n="$(grep -c . "$STUB_WORLD.provisioned")"
    var="STUB_KC_IDENTITY_$n"; identity="${!var-role=16385 database=16386 owner=16385}"
    if [ -z "$identity" ]; then printf 'psql: error: connection to server at "127.0.0.1", port 5432 failed: FATAL:  password authentication failed for user "keycloak_app"\ncommand terminated with exit code 2\n'; exit 2; fi
    printf '%s\n' "$identity"; exit 0
  fi
  if [ -n "${STUB_KC_SCHEMA:-}" ] && [[ "$args" == *"information_schema.tables"* ]]; then printf '%s\n' "$STUB_KC_SCHEMA"; exit 0; fi
  if [ "${STUB_EXEC_MODE:-}" = ac3 ]; then
    # Every AC3 observation of check_shared_postgres succeeds; only the CONNECT attempts follow STUB_AC3_CONNECT
    # (denied: the intended denial for the other database; allowed: both principals connect everywhere;
    # keycloak-allowed / app-allowed: only that principal crosses over, the other one is still denied).
    if [[ "$args" == *"select current_database()"* ]]; then
      mode="${STUB_AC3_CONNECT:-denied}"; app_denied=0; kc_denied=0
      case "$mode" in denied) app_denied=1; kc_denied=1 ;; keycloak-allowed) app_denied=1 ;; app-allowed) kc_denied=1 ;; esac
      if { [ "$app_denied" = 1 ] && [[ "$args" == *OWLMAST_APP_PASSWORD* ]] && [ "$db" = keycloak ]; } || { [ "$kc_denied" = 1 ] && [[ "$args" == *OWLMAST_KEYCLOAK_PASSWORD* ]] && [ "$db" = owlmast ]; }; then
        printf 'FATAL:  permission denied for database "%s"\nDETAIL:  User does not have CONNECT privilege.\ncommand terminated with exit code 2\n' "$db"; exit 2
      fi
      printf '%s\n' "$db"; exit 0
    fi
    # STUB_FLYWAY_HISTORY: the flyway_schema_history rows (default: every migration of this checkout, applied);
    # STUB_MIGRATED_BY: who applied them; STUB_TABLE_OWNER: owner of the jobs and audit tables;
    # STUB_DURABLE_WORK: the state of the synthetic audit.publish item as check_durable_work reads it.
    printf 'owlmast_app|f|f|f\nkeycloak_app|f|f|f\nvchord=1.1.1\nvector=0.8.2\nt\n%b' "$STUB_FLYWAY_HISTORY"
    printf 'migrated-by|%s\n' "${STUB_MIGRATED_BY:-owlmast_app}"
    for table in audit.event audit.publication_intent jobs.work_item; do printf 'table-owner|%s|%s\n' "$table" "${STUB_TABLE_OWNER:-owlmast_app}"; done
    [ -n "${STUB_EXTRA_TABLE:-}" ] && printf '%s\n' "$STUB_EXTRA_TABLE"
    printf '%s\n' "${STUB_DURABLE_WORK:-durable-work|SUCCEEDED|1|true|owl-mast-backend/owl-mast-backend-abc12-xyz/8d6c1f0e|-}"
    printf 'Index Scan using vectors_vchordrq on vectors\nCREATE INDEX vectors_vchordrq ON qualification.vectors USING vchordrq (embedding vector_l2_ops)\n'; exit 0
  fi
  case "${STUB_EXEC_MODE:-denied}" in
    denied) if [ "$db" = "${STUB_DENIED_DB:-keycloak}" ]; then printf 'psql: error: connection to server at "127.0.0.1", port 5432 failed: FATAL:  permission denied for database "%s"\nDETAIL:  User does not have CONNECT privilege.\ncommand terminated with exit code 2\n' "$db"; exit 2; fi; printf '%s\n' "$db"; exit 0 ;;
    refused) echo "Unable to connect to the server: dial tcp 10.0.0.1:6443: connect: connection refused"; exit 1 ;;
    authfail) printf 'psql: error: connection to server at "127.0.0.1", port 5432 failed: FATAL:  password authentication failed for user "owlmast_app"\ncommand terminated with exit code 2\n'; exit 2 ;;
    podgone) echo 'Error from server (NotFound): pods "owl-mast-postgresql-abc" not found'; exit 1 ;;
    connected) printf '%s\n' "$db"; exit 0 ;;
    denied-control-broken) if [ "$db" = "keycloak" ]; then printf 'FATAL:  permission denied for database "keycloak"\nDETAIL:  User does not have CONNECT privilege.\n'; exit 2; fi; echo "Unable to connect to the server"; exit 1 ;;
  esac
fi
if [[ "$args" == *" create secret generic "* ]]; then
  name="$(sed -E 's/.* create secret generic ([^ ]+).*/\1/' <<<"$args")"
  if [[ "$args" == *"--dry-run=client"* ]]; then  # built client-side only: nothing reaches the stub world
    # a value fed on stdin is counted, never stored: the test checks that the password arrived there and not in argv
    if [[ "$args" == *"--from-file=password=/dev/stdin"* ]]; then printf '%s %s\n' "$name" "$(wc -c | tr -d ' ')" >> "$STUB_CALLS.stdin"; fi
    printf '{"apiVersion":"v1","kind":"Secret","type":"Opaque","metadata":{"name":"%s"},"data":{"username":"dXNlcg==","password":"%s"}}\n' "$name" "$STUB_SENTINEL"; exit 0
  fi
  # a bare create leaves an object WITHOUT the ownership label (what a later run refuses as foreign)
  printf 'secret %s %s foreign:unlabelled\n' "$ns" "$name" >> "$STUB_WORLD"; echo "secret/$name created"; exit 0
fi
if [[ "$args" == *" create -f -"* ]]; then  # a Secret arrives on stdin; the world records it with the label it carries, never its data
  dst="$(STUB_NS="$ns" python3 -c 'import json,os,sys
o=json.load(sys.stdin); m=o["metadata"]; owner=(m.get("labels") or {}).get("owlmast.aisquad.com/run")
ns=m.get("namespace") or os.environ["STUB_NS"]
state="owned" if owner==os.environ["STUB_RUN_ID"] else ("foreign:"+owner if owner else "foreign:unlabelled")
print("secret", ns, m["name"], state)' 2>/dev/null || echo "secret - - foreign:unparsed")"
  if awk -v l="$dst" 'BEGIN{split(l,a," ")} $1=="secret" && $2==a[2] && $3==a[3] {found=1} END{exit !found}' "$STUB_WORLD"; then
    echo "Error from server (AlreadyExists): error when creating \"STDIN\": secrets already exists" >&2; exit 1  # create never overwrites
  fi
  printf '%s\n' "$dst" >> "$STUB_WORLD"; echo "stub: created"; exit 0
fi
if [[ "$args" == *" apply "* ]]; then [[ "$args" == *" -f -"* ]] && cat >/dev/null; echo "stub: applied"; exit 0; fi
echo "stub ok"
'''

HELM_STUB = r'''#!/usr/bin/env bash
args="$*"
printf 'helm %s\n' "$args" >> "$STUB_CALLS"
if [[ "$args" == *" template "* && "$args" == *"backend-deployment.yaml"* ]]; then  # the chart's fullname rule: release containing the chart name is the fullname
  rel="$(sed -E 's/.* template ([^ ]+).*/\1/' <<<"$args")"
  if [[ "$rel" == *owl-mast* ]]; then full="$rel"; else full="$rel-owl-mast"; fi
  printf 'apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: %s-backend\n' "$full"; exit 0
fi
rev_file() { printf '%s.rev.%s' "$STUB_WORLD" "$1"; }
hooks_file() { printf '%s.hooks.%s' "$STUB_WORLD" "$1"; }   # the hooks[] of the release record of the current revision
go_now() { date +%Y-%m-%dT%H:%M:%S.%N%:z; }   # time.Time as Go's encoding/json prints it: RFC 3339, nine fractional digits, local offset
# One hooks[] entry as Helm 4.3.1 stores it (pkg/release/v1/hook.go): hook_entry <name> <kind> <weight> <last_run json>.
# `weight` has omitempty, so the Job (weight 0) carries none. A hook that was not run has last_run {"phase":""}.
hook_entry() {
  local weight=""; [ "$3" != 0 ] && weight="\"weight\":$3,"
  printf '{"name":"%s","kind":"%s","path":"owl-mast/templates/postgresql-provision-keycloak-job.yaml","manifest":"stub","events":["pre-upgrade"],"last_run":%s,%s"delete_policies":["before-hook-creation","hook-succeeded"]}' "$1" "$2" "$4" "$weight"
}
if [[ "$args" == *" status "* ]]; then
  rel="$(sed -E 's/.* status ([^ ]+).*/\1/' <<<"$args")"; ns="$(sed -E 's/.* -n ([^ ]+).*/\1/' <<<"$args")"
  state="$(awk -v m="$rel" '$1=="release" && $3==m {print $4; found=1} END {if (!found) print "absent"}' "$STUB_WORLD")"
  case "$state" in
    absent) echo "Error: release: not found" >&2; exit 1 ;;
    error) echo "Error: Kubernetes cluster unreachable" >&2; exit 1 ;;
  esac
  rev=1; [ -e "$(rev_file "$rel")" ] && rev="$(grep -c . "$(rev_file "$rel")")"
  if [[ "$args" != *" -o json"* ]]; then printf 'NAME: %s\nSTATUS: deployed\nREVISION: %s\n' "$rel" "$rev"; exit 0; fi
  # `helm status -o json` (Helm 4.3.1): the release record, keys as in pkg/release/v1/release.go; `hooks` has omitempty.
  # STUB_STATUS_JSON: error = the read fails; malformed = not JSON; old-revision = the record of the revision before.
  case "${STUB_STATUS_JSON:-}" in
    error) echo "Error: Kubernetes cluster unreachable: the server has asked for the client to provide credentials" >&2; exit 1 ;;
    malformed) printf '{"name":"%s","hooks":[\n' "$rel"; exit 0 ;;
    old-revision) rev=$((rev - 1)) ;;
  esac
  hooks=""; [ -s "$(hooks_file "$rel")" ] && hooks="\"hooks\":[$(cat "$(hooks_file "$rel")")],"
  printf '{"name":"%s","info":{"first_deployed":"2026-11-07T09:00:00.000000001+01:00","last_deployed":"%s","description":"Upgrade complete","status":"deployed"},"chart":{"metadata":{"name":"owl-mast","version":"0.1.0"}},"manifest":"stub",%s"version":%s,"namespace":"%s","apply_method":"ssa"}\n' \
    "$rel" "$(go_now)" "$hooks" "$rev" "$ns"
  exit 0
fi
# An upgrade records the release and a new revision. A provisioning upgrade (postgresql.provisionKeycloakDatabase=true) runs the
# pre-upgrade hook as Helm does, by STUB_HOOK: succeeded (default) = Helm deleted the hook Job and ConfigMap (hook-succeeded);
# failed = the upgrade fails and the failed Job stays for diagnosis; kept = the upgrade succeeds but the hook objects remain
# (a delete policy that did not apply). STUB_HELM_NO_NEW_REVISION=1 = a provisioning upgrade that records no new revision.
# The release record of the new revision carries the hook's run, which outlives the deleted Job. More STUB_HOOK outcomes, all
# with a successful upgrade, a new revision and no hook object left:
#   skipped = no hook was rendered or run: the record has no hooks (the hook condition is false, or the value was dropped);
#   not-run = the hook is in the record but was not run (`helm upgrade --no-hooks`): last_run {"phase":""};
#   stale = last_run is Succeeded but started long before this upgrade;
#   phase-failed = last_run is Failed;  phase-running = last_run is Running and has no completed_at.
# STUB_HOOK_<n> overrides STUB_HOOK for the n-th provisioning upgrade (1 = the first), so one upgrade of a step can differ.
if [[ "$args" == *" upgrade "* ]]; then
  rel="$(sed -E 's/.* upgrade (--install )?([^ ]+).*/\2/' <<<"$args")"; ns="$(sed -E 's/.* -n ([^ ]+).*/\1/' <<<"$args")"
  job="job $ns $rel-postgresql-provision-keycloak"; cm="configmap $ns $rel-postgresql-provision-scripts"
  if [[ "$args" == *"provisionKeycloakDatabase=true"* ]]; then
    grep -vE "^($job|$cm) " "$STUB_WORLD" > "$STUB_WORLD.tmp" || true; mv "$STUB_WORLD.tmp" "$STUB_WORLD"   # before-hook-creation
    n=1; [ -e "$STUB_WORLD.provisioned" ] && n=$(( $(grep -c . "$STUB_WORLD.provisioned") + 1 ))
    var="STUB_HOOK_$n"; mode="${!var:-${STUB_HOOK:-succeeded}}"
    started="$(go_now)"; ran="{\"started_at\":\"$started\",\"completed_at\":\"$(go_now)\",\"phase\":\"Succeeded\"}"
    case "$mode" in
      failed) printf '%s owned\n%s owned\n' "$job" "$cm" >> "$STUB_WORLD"
              echo "Error: UPGRADE FAILED: pre-upgrade hooks failed: 1 error occurred: * job $rel-postgresql-provision-keycloak failed: BackoffLimitExceeded" >&2; exit 1 ;;
      kept) printf '%s owned\n%s owned\n' "$job" "$cm" >> "$STUB_WORLD" ;;
      skipped) ran="" ;;
      not-run) ran='{"phase":""}' ;;
      stale) ran='{"started_at":"2026-11-07T09:00:00.123456789+01:00","completed_at":"2026-11-07T09:00:04.5+01:00","phase":"Succeeded"}' ;;
      phase-failed) ran="{\"started_at\":\"$started\",\"completed_at\":\"$(go_now)\",\"phase\":\"Failed\"}" ;;
      phase-running) ran="{\"started_at\":\"$started\",\"phase\":\"Running\"}" ;;
    esac
    if [ -n "$ran" ]; then printf '%s,%s' "$(hook_entry "$rel-postgresql-provision-scripts" ConfigMap -5 "$ran")" "$(hook_entry "$rel-postgresql-provision-keycloak" Job 0 "$ran")" > "$(hooks_file "$rel")"
    else : > "$(hooks_file "$rel")"; fi
    echo "$rel" >> "$STUB_WORLD.provisioned"
    [ "${STUB_HELM_NO_NEW_REVISION:-}" = 1 ] && { echo "stub helm ok"; exit 0; }
  else
    : > "$(hooks_file "$rel")"   # a revision whose render has no provisioning hook records none
  fi
  if [[ "$args" == *"bootstrapAdmin.enabled=false"* ]] && [ "${STUB_RETIRE:-retired}" != kept ]; then : > "$STUB_WORLD.retired"; fi
  if grep -q "^release - $rel " "$STUB_WORLD"; then [ -e "$(rev_file "$rel")" ] || echo "$rel" >> "$(rev_file "$rel")"   # a release the world started with is at revision 1
  else printf 'release - %s owned\n' "$rel" >> "$STUB_WORLD"; fi
  echo "$rel" >> "$(rev_file "$rel")"
  echo "stub helm ok"; exit 0
fi
echo "stub helm ok"
'''


def chart_digest(chart: Path) -> str:
    """The digest record_source writes, computed without the script: sha256sum's `<hex>  ./<path>` line for every
    file in byte order of the path, hashed together."""
    files = sorted((p for p in chart.rglob("*") if p.is_file()), key=lambda p: ("./" + p.relative_to(chart).as_posix()).encode())
    lines = "".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  ./{p.relative_to(chart).as_posix()}\n" for p in files)
    return hashlib.sha256(lines.encode()).hexdigest()


class Harness:
    def __init__(self, world: str):
        self.tmp = Path(tempfile.mkdtemp(prefix="owlmast-qualify-stub."))
        self.bin = self.tmp / "bin"; self.bin.mkdir()
        for name, text in (("kubectl", KUBECTL_STUB), ("helm", HELM_STUB)):
            p = self.bin / name; p.write_text(text); p.chmod(p.stat().st_mode | stat.S_IXUSR)
        self.world = self.tmp / "world.txt"; self.world.write_text(world)
        self.calls = self.tmp / "calls.txt"; self.calls.write_text("")
        self.evidence = self.tmp / "evidence"
        (self.tmp / "kubeconfig").write_text("apiVersion: v1\nkind: Config\n")

    def env(self, **extra):
        env = {"PATH": f"{self.bin}:{os.environ['PATH']}", "HOME": os.environ.get("HOME", "/"), "KUBECONFIG": str(self.tmp / "kubeconfig"),
               "OWLMAST_HELM": str(self.bin / "helm"), "EVIDENCE_DIR": str(self.evidence), "STUB_WORLD": str(self.world), "STUB_CALLS": str(self.calls), "STUB_RUN_ID": RUN_ID, "STUB_SENTINEL": SENTINEL,
               "BACKEND_IMAGE_TAG": "stub", "STUB_UNLABELLED_COMPONENTS": " ".join(UNLABELLED_COMPONENTS),
               "STUB_FLYWAY_HISTORY": "".join(f"{version}|true\\n" for version in MIGRATIONS), "DURABLE_WORK_TIMEOUT": "0"}
        env.update(extra)
        return env

    def run(self, *steps, **extra):
        return subprocess.run(["bash", str(SCRIPT), *steps], env=self.env(**extra), stdin=subprocess.DEVNULL, capture_output=True, text=True, check=False, timeout=60)

    def source(self, body: str, **extra):
        return subprocess.run(["bash", "-c", f"source '{SCRIPT}'; {body}"], env=self.env(**extra), stdin=subprocess.DEVNULL, capture_output=True, text=True, check=False, timeout=60)

    def mutating_calls(self):
        return [c for c in self.calls.read_text().splitlines() if MUTATING.search(c)]

    def evidence_text(self):
        return "\n".join(p.read_text(errors="replace") for p in self.evidence.rglob("*") if p.is_file()) if self.evidence.exists() else ""

    def close(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


BASE_WORLD = "namespace - owl-mast-test owned\nnamespace - owl-mast-test-external owned\n"


class PreflightTests(unittest.TestCase):
    def run_refused(self, world, *steps):
        h = Harness(world)
        try:
            r = h.run(*steps)
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("REFUSED", r.stdout)
            self.assertEqual(h.mutating_calls(), [], "a mutating call was made after a refusal")
            self.assertNotIn(SENTINEL, r.stdout + r.stderr + h.evidence_text())
            return r
        finally:
            h.close()

    def test_prepare_proceeds_only_with_owned_or_absent_resources_and_labels_only_new_objects(self):
        h = Harness(BASE_WORLD + "secret owl-mast-test owl-mast-db owned\nsecret owl-mast-test-external owl-mast-db owned\n")
        try:
            r = h.run("prepare")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            calls = h.calls.read_text().splitlines()
            created = [c for c in calls if " create secret generic " in c]
            self.assertEqual(len(created), 6)  # eight synthetic Secrets minus the two that already exist and are owned
            # 109/4543776459: each Secret is built client-side and created WITH its label in one call; no separate label call exists
            self.assertTrue(all("--dry-run=client" in c and "-o json" in c for c in created), created)
            self.assertEqual([c for c in calls if " label " in c and " secret" in c], [])
            # 109/4543776464: six labelled creations plus the two replications, all `create` (never `apply`, which overwrites)
            self.assertEqual(sum(" create -f -" in c for c in calls), 8)
            self.assertEqual(sum(" apply -f -" in c for c in calls), 0)  # no Secret is ever written with apply
            world = h.world.read_text().splitlines()
            self.assertEqual([l for l in world if l.startswith("secret ") and not l.endswith(" owned")], [], "every created Secret carries this run's label")
            self.assertEqual(len([l for l in world if l.startswith("secret ")]), 2 + 8)
            self.assertIn("owned by this run (kept)", r.stdout)
            self.assertNotIn(SENTINEL, r.stdout + r.stderr + h.evidence_text())
            inventory = (h.evidence / "runtime" / "secrets-inventory.txt").read_text()
            self.assertIn("keys=[password username ]", inventory)
            self.assertNotIn("dXNlcg", inventory)
        finally:
            h.close()

    def test_foreign_secret_in_the_run_namespace_refuses_before_any_mutation(self):
        r = self.run_refused(BASE_WORLD + "secret owl-mast-test owl-mast-db foreign:another-run\n", "prepare")
        self.assertIn("owner is 'another-run'", r.stdout)

    def test_unlabelled_existing_claim_refuses(self):
        self.run_refused(BASE_WORLD + "pvc owl-mast-test owl-mast-postgresql-data foreign:unlabelled\n", "bundled-bundled")

    def test_unreadable_ownership_is_not_absence(self):
        r = self.run_refused(BASE_WORLD + "storageclass - owl-mast-local-retain error\n", "prepare")
        self.assertIn("ownership unreadable", r.stdout)

    def test_foreign_namespace_refuses(self):
        self.run_refused("namespace - owl-mast-test foreign:someone\nnamespace - owl-mast-test-external owned\n", "prepare")

    def test_direct_step_entry_is_preflighted(self):
        self.run_refused(BASE_WORLD + "secret owl-mast-test owl-mast-db-broken foreign:unlabelled\n", "failure-paths")
        self.run_refused(BASE_WORLD + "configmap owl-mast-test-external external-keycloak-realm foreign:unlabelled\n", "fixtures")
        self.run_refused(BASE_WORLD + "service owl-mast-test-external external-postgresql foreign:other\n", "fixtures")
        self.run_refused(BASE_WORLD + "resourcequota owl-mast-test owl-mast-test-budget foreign:unlabelled\n", "prepare")

    def test_existing_release_resources_are_checked_one_by_one(self):
        self.run_refused(BASE_WORLD + "release - owl-mast owned\ndeployment owl-mast-test owl-mast-backend foreign:unlabelled\n", "persistence")
        self.run_refused(BASE_WORLD + "release - owl-mast owned\nservice owl-mast-test owl-mast-keycloak foreign:other\n", "bundled-bundled")
        self.run_refused(BASE_WORLD + "configmap owl-mast-test owl-mast-postgresql-init foreign:unlabelled\n", "external-bundled")
        self.run_refused(BASE_WORLD + "release - owl-mast-wrongidp error\n", "failure-paths")

    def test_review_omission_cases_now_refuse(self):
        """The three omissions reproduced by the final review (F3), each before any mutation."""
        r = self.run_refused(BASE_WORLD + "secret owl-mast-test owl-mast-db foreign:another-run\n", "bundled-external")
        self.assertIn("preflight secret owl-mast-test/owl-mast-db", r.stdout)
        r = self.run_refused(BASE_WORLD + "secret owl-mast-test-external owl-mast-keycloak-db foreign:another-run\n", "fixtures")
        self.assertIn("preflight secret owl-mast-test-external/owl-mast-keycloak-db", r.stdout)
        r = self.run_refused(BASE_WORLD + "job owl-mast-test owl-mast-postgresql-provision-keycloak foreign:another-run\n", "all")
        self.assertIn("preflight job owl-mast-test/owl-mast-postgresql-provision-keycloak", r.stdout)
        self.run_refused(BASE_WORLD + "configmap owl-mast-test owl-mast-postgresql-provision-scripts foreign:unlabelled\n", "bundled-bundled")
        self.run_refused(BASE_WORLD + "secret owl-mast-test owl-mast-external-db foreign:unlabelled\n", "external-external")
        self.run_refused(BASE_WORLD + "secret owl-mast-test owl-mast-keycloak-bootstrap foreign:unlabelled\n", "external-bundled")
        self.run_refused(BASE_WORLD + "secret owl-mast-test owl-mast-postgres-admin foreign:unlabelled\n", "bundled-external")
        self.run_refused(BASE_WORLD + "deployment owl-mast-test-external external-keycloak foreign:unlabelled\n", "external-external")

    def test_selected_pods_must_prove_their_controller_chain(self):
        """N3: pod -> ReplicaSet (UID, label, readable) -> expected Deployment (UID, label); every break refuses."""
        dep = "deployment owl-mast-test owl-mast-postgresql owned\n"
        cases = {
            "foreign:owner": "expected Deployment/owl-mast-postgresql",            # ReplicaSet of another release
            "foreign:another-run": "label 'another-run' is not",                    # pod label foreign
            "foreign:rs-foreign": "label 'someone-else' is not",                    # ReplicaSet exists but foreign
            "foreign:rs-missing": "controller ReplicaSet owl-mast-postgresql-abc12 is missing",
            "foreign:rs-unreadable": "controller ReplicaSet owl-mast-postgresql-abc12 unreadable",
            "foreign:uid": "UID rs-owl-mast-postgresql differs from the pod's controller reference stale-uid",
            "foreign:deploy": "controlled by Deployment/owl-mast-postgresql-other",
            "foreign:ambiguous": "expected exactly one controller reference",
            "foreign:no-controller": "expected exactly one controller reference",
            "error": "pod selection unreadable",
        }
        for state, message in cases.items():
            r = self.run_refused(BASE_WORLD + dep + f"pods owl-mast-test owl-mast-postgresql {state}\n", "persistence")
            self.assertIn(message, r.stdout, state)
        # a component whose pod template DOES carry the run label: an unlabelled pod or ReplicaSet is refused there
        bdep = dep + "pods owl-mast-test owl-mast-postgresql owned\ndeployment owl-mast-test owl-mast-backend owned\n"
        r = self.run_refused(BASE_WORLD + bdep + "pods owl-mast-test owl-mast-backend foreign:unlabelled\n", "persistence")
        self.assertIn("chain pod owl-mast-test/owl-mast-backend-abc12-xyz: label '' is not", r.stdout)
        # a proven pod whose Deployment is absent or foreign is refused too
        self.run_refused(BASE_WORLD + "pods owl-mast-test owl-mast-postgresql owned\n", "persistence")
        self.run_refused(BASE_WORLD + "deployment owl-mast-test owl-mast-postgresql foreign:other\npods owl-mast-test owl-mast-postgresql owned\n", "persistence")

    def test_proven_chain_is_accepted_and_deletion_targets_only_proven_names(self):
        world = BASE_WORLD + "deployment owl-mast-test owl-mast-postgresql owned\npods owl-mast-test owl-mast-postgresql owned\n"
        h = Harness(world)
        try:
            r = h.source("verified_pods owl-mast postgresql om-01-02-local-20261107-01")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual((h.evidence / "runtime" / "preflight" / "proven-pods-owl-mast-postgresql.txt").read_text().split(), ["owl-mast-postgresql-abc12-xyz"])
            self.assertIn("proven (owl-mast-postgresql-abc12-xyz -> ReplicaSet/owl-mast-postgresql-abc12 rs-owl-mast-postgresql -> Deployment/owl-mast-postgresql dep-owl-mast-postgresql", r.stdout)
            calls = h.calls.read_text()
            self.assertIn(" get replicaset owl-mast-postgresql-abc12 ", calls); self.assertIn(" get deployment owl-mast-postgresql ", calls)
        finally:
            h.close()

    def test_stub_pod_labels_are_the_labels_the_chart_renders(self):
        """4544473145: commit 9ca009b took commonLabels (and with them the run label) off the PostgreSQL pod template, and the
        stub world went on answering a labelled pod. The stub's labels now come from the rendered chart, and the script's
        list of unlabelled components must be exactly that."""
        self.assertEqual(set(POD_RUN_LABELS), set(COMPONENTS))
        self.assertEqual(UNLABELLED_COMPONENTS, ["postgresql"])  # what chart 0.2.0 renders; a change here must be deliberate
        declared = re.search(r'^CHAIN_UNLABELLED_COMPONENTS="([^"]*)"$', SCRIPT.read_text(), re.M).group(1).split()
        self.assertEqual(sorted(declared), UNLABELLED_COMPONENTS)
        self.assertEqual(template_pod_run_labels(), POD_RUN_LABELS)  # the Helm-free fallback agrees with the render
        if HELM is not None:
            self.assertEqual(rendered_pod_run_labels(), POD_RUN_LABELS)

    def test_unlabelled_postgresql_pods_are_proven_through_the_owned_deployment(self):
        """4544473145: the pod and its ReplicaSet have no run label; the UID chain to the owned Deployment proves them. A label
        naming someone else, or a Deployment that is not owned, still refuses. The same world fails if the script requires the label."""
        world = BASE_WORLD + "deployment owl-mast-test owl-mast-postgresql owned\npods owl-mast-test owl-mast-postgresql owned\n"
        h = Harness(world)
        try:
            r = h.source("verified_pods owl-mast postgresql " + RUN_ID)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            calls = h.calls.read_text()
            self.assertIn("Deployment owned by " + RUN_ID + "; the postgresql pod template carries no run label", r.stdout)
            self.assertNotIn("refusing", r.stdout)
            # what the stub answered is what the chart renders: no label on the pod or the ReplicaSet
            resources = (h.evidence / "runtime" / "preflight" / "resources.txt").read_text()
            self.assertIn("pod owl-mast-test/owl-mast-postgresql-abc12-xyz label= refs=ReplicaSet/owl-mast-postgresql-abc12/", resources)
            self.assertIn(" get replicaset owl-mast-postgresql-abc12 ", calls)
            # a script that still required the label (the regression) refuses this very world
            r = h.source("CHAIN_UNLABELLED_COMPONENTS=''; verified_pods owl-mast postgresql " + RUN_ID)
            self.assertEqual(r.returncode, 1); self.assertIn("label '' is not", r.stdout)
        finally:
            h.close()
        for bad, message in (("pods owl-mast-test owl-mast-postgresql foreign:another-run\n", "label 'another-run' is not"),
                             ("pods owl-mast-test owl-mast-postgresql foreign:rs-foreign\n", "label 'someone-else' is not")):
            r = self.run_refused(BASE_WORLD + "deployment owl-mast-test owl-mast-postgresql owned\n" + bad, "persistence")
            self.assertIn(message, r.stdout)
        r = self.run_refused(BASE_WORLD + "deployment owl-mast-test owl-mast-postgresql foreign:unlabelled\npods owl-mast-test owl-mast-postgresql owned\n", "persistence")
        self.assertIn("exists but owner is 'unlabelled'", r.stdout)

    def test_persistence_step_replaces_the_proven_unlabelled_postgresql_pod(self):
        """4544473145: T3 stopped at 'pod controller chain not proven; nothing deleted' and the re-entry preflight refused every
        existing release. With the labels the chart renders, the step passes preflight, proves the chain and deletes by name."""
        world = BASE_WORLD + "release - owl-mast owned\npvc owl-mast-test owl-mast-postgresql-data owned\n"
        for comp in COMPONENTS:
            world += f"deployment owl-mast-test owl-mast-{comp} owned\npods owl-mast-test owl-mast-{comp} owned\n"
        h = Harness(world)
        try:
            r = h.run("persistence")
            self.assertNotIn("REFUSED", r.stdout, r.stdout)
            self.assertIn("preflight passed", r.stdout)
            self.assertNotIn("pod controller chain not proven", r.stdout)
            deletes = [c for c in h.calls.read_text().splitlines() if " delete pod " in c]
            self.assertEqual(len(deletes), 1, r.stdout)
            self.assertIn(" delete pod -n owl-mast-test owl-mast-postgresql-abc12-xyz --wait=true", deletes[0])
            self.assertEqual((h.evidence / "runtime" / "t3-delete-pod-proven.txt").read_text().split(), ["owl-mast-postgresql-abc12-xyz"])
        finally:
            h.close()

    def test_inventory_lists_the_unlabelled_postgresql_pods(self):
        """4544473145: the label-selected inventory cannot list objects that carry no run label."""
        h = Harness(BASE_WORLD)
        try:
            h.source("step_inventory")
            calls = h.calls.read_text()
            self.assertIn("get pods,replicasets -n owl-mast-test -l app.kubernetes.io/component=postgresql", calls)
        finally:
            h.close()

    def test_unsupported_namespace_release_or_class_overrides_refuse_before_any_call(self):
        """N2: the static manifests and the chart fix the real targets; an override that would make preflight
        inspect other objects than the ones mutated is rejected before preflight, with zero cluster calls."""
        for env, text in (
            ({"EXT_NS": "other"}, "namespace overrides are not supported"),
            ({"NS": "other"}, "namespace overrides are not supported"),
            ({"RELEASE": "sample"}, "renders chart fullname 'sample-owl-mast'"),
            ({"FE_RELEASE": "sample", "OWLMAST_FOLLOWUP_RUN_ID": "fe"}, "renders chart fullname 'sample-owl-mast'"),
        ):
            for step in ("fixtures", "prepare", "bundled-bundled", "all"):
                h = Harness(BASE_WORLD + "namespace - other owned\ndeployment owl-mast-test-external external-postgresql foreign:other\njob owl-mast-test sample-owl-mast-postgresql-provision-keycloak foreign:other\n")
                try:
                    r = h.run(step, **env)
                    self.assertEqual(r.returncode, 2, (env, step, r.stdout, r.stderr))
                    self.assertIn("REFUSED", r.stderr); self.assertIn(text, r.stderr)
                    kubectl_calls = [c for c in h.calls.read_text().splitlines() if not c.startswith("helm ")]
                    self.assertEqual(kubectl_calls, [], (env, step))  # not even a read reached the cluster
                    self.assertEqual(h.mutating_calls(), [])
                finally:
                    h.close()

    def test_absent_gateway_api_is_established_only_by_the_typed_group_list(self):
        """N4: the optional HTTPRoute kind is absent only when a well-formed APIGroupList lacks its group; the
        object is then never queried. Every other discovery state refuses with zero mutations."""
        h = Harness(BASE_WORLD + "discovery - gateway nogateway\nhttproute owl-mast-test owl-mast mixed-forbidden\n")
        try:
            r = h.run("bundled-bundled")
            self.assertIn("the typed /apis APIGroupList has no group gateway.networking.k8s.io", r.stdout)
            self.assertNotIn("REFUSED", r.stdout)
            calls = h.calls.read_text().splitlines()
            self.assertTrue(all("httproutes" not in c for c in calls), "the unlisted kind was still queried")
            self.assertTrue(any(" get --raw /apis" in c and not c.endswith("/v1") for c in calls))
        finally:
            h.close()
        for discovery, message in (
            ("stale", "GET /apis/gateway.networking.k8s.io/v1 failed"),     # group registered, version backend unavailable: never absence
            ("forbidden", "GET /apis failed"), ("unavailable", "GET /apis failed"),
            ("malformed", "/apis is not JSON"), ("wrongkind", "did not return a typed APIGroupList"), ("aggregated", "did not return a typed APIGroupList"),
            ("noresource", "does not list the httproutes resource"), ("wronggv", "is not the APIResourceList v1 of gateway.networking.k8s.io/v1"),
            ("badname", "/apis APIGroupList malformed"), ("resourceversion", "declares version 'v1beta1'"), ("noapiversion", "is not the APIResourceList v1"),
        ):
            r = self.run_refused(BASE_WORLD + f"discovery - gateway {discovery}\n", "bundled-bundled")
            self.assertIn(message, r.stdout, discovery)
            self.assertIn("ownership unreadable", r.stdout, discovery)

    def test_mixed_discovery_errors_on_a_served_kind_refuse_and_never_reach_helm(self):
        """N4: the reviewer's reproductions, at full invocation: partial discovery plus a mapping miss is an error, not absence."""
        for state in ("mixed-forbidden", "mixed-unavailable", "forbidden", "kind-unavailable", "warn-shape", "garbage", "error"):
            r = self.run_refused(BASE_WORLD + f"httproute owl-mast-test owl-mast {state}\n", "bundled-bundled")
            self.assertIn("preflight httproute owl-mast-test/owl-mast: ownership unreadable", r.stdout, state)
            self.assertTrue(all(" upgrade " not in c for c in r.stdout.splitlines()), state)
        # the text that used to be trusted is not an exception for any other kind
        for kind in ("configmap", "job", "service"):
            name = {"configmap": "owl-mast-postgresql-init", "job": "owl-mast-postgresql-provision-keycloak", "service": "owl-mast-backend"}[kind]
            self.run_refused(BASE_WORLD + f"{kind} owl-mast-test {name} kind-unavailable\n", "bundled-bundled")
            self.run_refused(BASE_WORLD + f"{kind} owl-mast-test {name} mixed-forbidden\n", "bundled-bundled")

    def test_served_gateway_api_kind_follows_the_ordinary_ownership_rules(self):
        self.run_refused(BASE_WORLD + "httproute owl-mast-test owl-mast foreign:other\n", "bundled-bundled")
        self.run_refused(BASE_WORLD + "httproute owl-mast-test owl-mast foreign:unlabelled\n", "bundled-bundled")
        h = Harness(BASE_WORLD + "httproute owl-mast-test owl-mast owned\n")
        try:
            r = h.source("preflight bundled-bundled")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("preflight httproute owl-mast-test/owl-mast: owned by this run", r.stdout)
            self.assertIn(" get httproutes.v1.gateway.networking.k8s.io owl-mast --ignore-not-found", h.calls.read_text())
        finally:
            h.close()
        h = Harness(BASE_WORLD)  # served but absent: an explicit NotFound (exit 0, no output) is absence
        try:
            r = h.source("preflight bundled-bundled")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("preflight httproute owl-mast-test/owl-mast: absent", r.stdout)
        finally:
            h.close()

    def test_direct_fixtures_checks_the_consumed_storage_class(self):
        r = self.run_refused(BASE_WORLD + "storageclass - owl-mast-local-retain foreign:other\n", "fixtures")
        self.assertIn("preflight storageclass -/owl-mast-local-retain", r.stdout)
        self.run_refused(BASE_WORLD + "storageclass - owl-mast-local-retain error\n", "fixtures")

    def test_first_enable_needs_its_own_identity_and_checks_its_own_resources(self):
        h = Harness(BASE_WORLD)
        try:
            r = h.run("first-enable")
            self.assertEqual(r.returncode, 2); self.assertIn("needs OWLMAST_FOLLOWUP_RUN_ID", r.stdout); self.assertEqual(h.mutating_calls(), [])
        finally:
            h.close()
        h = Harness(BASE_WORLD + "secret owl-mast-test owl-mast-fe-db foreign:other\n")
        try:
            r = h.run("first-enable", OWLMAST_FOLLOWUP_RUN_ID="fe-run")
            self.assertEqual(r.returncode, 2, r.stdout); self.assertIn("not fe-run", r.stdout); self.assertEqual(h.mutating_calls(), [])
        finally:
            h.close()
        h = Harness(BASE_WORLD + "pvc owl-mast-test owl-mast-fe-postgresql-data foreign:" + RUN_ID + "\n")  # even the retained set's label is foreign to the fixture identity
        try:
            r = h.run("first-enable", OWLMAST_FOLLOWUP_RUN_ID="fe-run")
            self.assertEqual(r.returncode, 2, r.stdout); self.assertEqual(h.mutating_calls(), [])
        finally:
            h.close()

    def test_positive_control_every_enumerated_resource_owned_passes_preflight_for_all_steps(self):
        """Every object the enumeration can name exists and is owned (releases present, pods with proven chains): preflight passes, zero mutations."""
        world = BASE_WORLD + "storageclass - owl-mast-local-retain owned\nresourcequota owl-mast-test owl-mast-test-budget owned\nresourcequota owl-mast-test-external owl-mast-test-external-budget owned\n"
        for ns in ("owl-mast-test", "owl-mast-test-external"):
            for sec in ("owl-mast-postgres-admin", "owl-mast-db", "owl-mast-keycloak-db", "owl-mast-keycloak-bootstrap"):
                world += f"secret {ns} {sec} owned\n"
        world += "secret owl-mast-test owl-mast-external-db owned\nsecret owl-mast-test owl-mast-external-keycloak-db owned\nsecret owl-mast-test owl-mast-db-broken owned\n"
        for rel in ("owl-mast", "owl-mast-broken", "owl-mast-wrongidp"):
            world += f"release - {rel} owned\n"
            for kind, suffix in (("deployment", "-backend"), ("deployment", "-postgresql"), ("deployment", "-keycloak"), ("deployment", "-frontend"), ("service", "-backend"), ("service", "-postgresql"), ("service", "-keycloak"), ("service", "-frontend"),
                                 ("configmap", "-postgresql-init"), ("configmap", "-keycloak-realm"), ("configmap", "-postgresql-provision-scripts"), ("job", "-postgresql-provision-keycloak"), ("ingress", ""), ("httproute", ""), ("pvc", "-postgresql-data"),
                                 ("networkpolicy", "-postgresql"), ("networkpolicy", "-keycloak")):
                world += f"{kind} owl-mast-test {rel}{suffix} owned\n"
            for comp in ("backend", "postgresql", "keycloak"):
                world += f"pods owl-mast-test {rel}-{comp} owned\n"
        for obj in ("configmap external-postgresql-init", "configmap external-keycloak-realm", "pvc external-postgresql-data", "service external-postgresql", "service external-keycloak", "deployment external-postgresql", "deployment external-keycloak"):
            world += f"{obj.split()[0]} owl-mast-test-external {obj.split()[1]} owned\n"
        h = Harness(world)
        try:
            r = h.source("preflight prepare fixtures bundled-bundled persistence bundled-external external-bundled external-external failure-paths inventory")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("preflight passed", r.stdout)
            self.assertEqual(h.mutating_calls(), [])
            resources = (h.evidence / "runtime" / "preflight" / "resources.txt").read_text().splitlines()
            states = [line.rsplit(" ", 1)[-1] for line in resources if not line.startswith("pod ")]
            self.assertNotIn("absent", states, resources)  # everything enumerated was found and owned, not merely absent
            self.assertTrue(all(st in ("owned", "present") for st in states), set(states))
            self.assertEqual(r.stdout.count("proven ("), 5 * 3 + 2 * 3)  # owl-mast in five steps, broken and wrongidp once, three components each
            self.assertGreaterEqual(len(resources), 80)
        finally:
            h.close()

    def test_replication_requires_an_owned_source(self):
        self.run_refused(BASE_WORLD + "secret owl-mast-test-external owl-mast-db foreign:unlabelled\n", "prepare")

    def test_all_preflights_every_step_before_the_first_mutation(self):
        r = self.run_refused(BASE_WORLD + "deployment owl-mast-test-external external-keycloak foreign:unlabelled\n", "all")
        self.assertIn("preflight deployment owl-mast-test-external/external-keycloak", r.stdout)


class SecretValueSentinelTests(unittest.TestCase):
    def test_success_path_persists_no_value(self):
        h = Harness(BASE_WORLD)
        try:
            r = h.run("prepare")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertNotIn(SENTINEL, r.stdout + r.stderr + h.evidence_text())
            for call in h.calls.read_text().splitlines():
                if " get secret" in call and ("json" in call or "yaml" in call):
                    self.assertIn(" get secret owl-mast-", call)  # the only value read is the replication source, piped to apply
        finally:
            h.close()

    def test_failure_during_replication_persists_no_value(self):
        h = Harness(BASE_WORLD)
        try:
            r = h.run("prepare", STUB_FAIL_ON=" create -f -")
            self.assertNotEqual(r.returncode, 0)
            self.assertNotIn(SENTINEL, r.stdout + r.stderr + h.evidence_text())
        finally:
            h.close()

    def test_interruption_while_reading_the_source_persists_no_value(self):
        h = Harness(BASE_WORLD)
        try:
            r = h.run("prepare", STUB_INTERRUPT_ON=" get secret owl-mast-db -o json")
            self.assertNotEqual(r.returncode, 0)
            self.assertNotIn(SENTINEL, r.stdout + r.stderr + h.evidence_text())
        finally:
            h.close()

    def test_inventory_projection_is_key_names_only(self):
        h = Harness(BASE_WORLD)
        try:
            r = h.source("secrets_inventory")
            self.assertEqual(r.returncode, 0, r.stderr)
            call = [c for c in h.calls.read_text().splitlines() if "get secrets -A" in c][0]
            self.assertIn("$k, $v := .data}}{{$k}}", call)
            self.assertNotIn("-o json", call); self.assertNotIn("KEYS:.data", call)
            self.assertNotIn(SENTINEL, r.stdout)
        finally:
            h.close()


class EvidenceEvaluatorTests(unittest.TestCase):
    def denial(self, mode, denied="keycloak"):
        h = Harness(BASE_WORLD)
        try:
            r = h.source("expect_connect_denied probe owl-mast-test owl-mast-postgresql OWLMAST_APP keycloak owlmast", STUB_EXEC_MODE=mode, STUB_DENIED_DB=denied)
            return r.returncode, r.stdout, (h.evidence / "runtime" / "probe.txt").read_text() if (h.evidence / "runtime" / "probe.txt").exists() else ""
        finally:
            h.close()

    def test_connect_denial_needs_the_specific_denial_and_a_successful_control(self):
        rc, out, _ = self.denial("denied")
        self.assertEqual(rc, 0, out); self.assertIn("ok   probe (PostgreSQL CONNECT denied for keycloak; the same principal reaches owlmast)", out)
        for mode in ("refused", "authfail", "podgone", "connected", "denied-control-broken"):
            rc, out, _ = self.denial(mode)
            self.assertNotEqual(rc, 0, mode); self.assertIn("FAIL probe", out, mode)
        rc, out, _ = self.denial("denied", denied="owlmast")  # denial for a different database than the one under test is not evidence either
        self.assertNotEqual(rc, 0, out)

    def test_proxied_readiness_requires_the_backends_own_503_body(self):
        h = Harness(BASE_WORLD)
        try:
            ok = h.tmp / "ok.txt"; ok.write_text('I1107 "Response" verb="GET" status="503 Service Unavailable"\nI1107 "Response Body" body="{\\"status\\":\\"DOWN\\"}"\n')
            generic = h.tmp / "generic.txt"; generic.write_text('I1107 "Response" verb="GET" status="503 Service Unavailable"\nI1107 "Response Body" body="{\\"kind\\":\\"Status\\",\\"status\\":\\"Failure\\",\\"message\\":\\"the server is currently unable to handle the request\\"}"\n')
            up = h.tmp / "up.txt"; up.write_text('I1107 "Response" verb="GET" status="200 OK"\nI1107 "Response Body" body="{\\"status\\":\\"UP\\"}"\n')
            plain = h.tmp / "plain.txt"; plain.write_text("Error from server (ServiceUnavailable): the server is currently unable to handle the request\n")
            self.assertEqual(h.source(f"assert_proxied_readiness_down '{ok}'").returncode, 0)
            for bad in (generic, up, plain):
                self.assertNotEqual(h.source(f"assert_proxied_readiness_down '{bad}'").returncode, 0, bad.name)
        finally:
            h.close()


class ReviewFindingsTests(unittest.TestCase):
    """PR #109 post-merge review (5827094734) findings on the qualification script."""

    def test_second_connect_denial_failure_is_not_swallowed_either(self):
        """116/4543777563: only the keycloak principal can reach the other database, so the FIRST check passes and the
        second one (keycloak -> owlmast) is the first failure; its `|| return 1` must stop the function."""
        h = Harness(BASE_WORLD)
        try:
            r = h.source("check_shared_postgres owl-mast-test owl-mast-postgresql && echo PASSED || echo CAUGHT", STUB_EXEC_MODE="ac3", STUB_AC3_CONNECT="keycloak-allowed")
            self.assertEqual(r.stdout.strip().splitlines()[-1], "CAUGHT", r.stdout + r.stderr)
            self.assertIn("ok   ac3-owl-mast-test-app-cannot-connect-keycloak-db", r.stdout)  # the first check passed
            self.assertIn("FAIL ac3-owl-mast-test-keycloak-cannot-connect-owlmast-db: the principal connected to owlmast", r.stdout)
            self.assertNotIn("ac3-owl-mast-test-extensions", r.stdout)  # nothing after the failed check ran
            self.assertNotIn("PASSED", r.stdout)
        finally:
            h.close()
        # the mirror image: only the application principal crosses over, so the first check is the failure
        h = Harness(BASE_WORLD)
        try:
            r = h.source("check_shared_postgres owl-mast-test owl-mast-postgresql && echo PASSED || echo CAUGHT", STUB_EXEC_MODE="ac3", STUB_AC3_CONNECT="app-allowed")
            self.assertEqual(r.stdout.strip().splitlines()[-1], "CAUGHT", r.stdout + r.stderr)
            self.assertIn("FAIL ac3-owl-mast-test-app-cannot-connect-keycloak-db", r.stdout)
            self.assertNotIn("keycloak-cannot-connect-owlmast-db", r.stdout)
        finally:
            h.close()

    def test_secret_creation_is_atomic_and_never_leaves_an_unlabelled_object(self):
        """109/4543776459: a failed or interrupted creation leaves nothing behind, so a rerun is not refused as foreign."""
        for step, name in (("ensure_secret owl-mast-test owl-mast-db owlmast_app", "owl-mast-db"), ("ensure_broken_secret", "owl-mast-db-broken")):
            h = Harness(BASE_WORLD)
            try:
                r = h.source(f"{step}; echo CONTINUED", STUB_FAIL_ON=" create -f -")
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr); self.assertNotIn("CONTINUED", r.stdout)
                self.assertIn(f"REFUSED: secret owl-mast-test/{name} could not be created with its ownership label", r.stdout)
                self.assertNotIn(f"secret owl-mast-test {name}", h.world.read_text())  # nothing exists, labelled or not
                self.assertNotIn(SENTINEL, r.stdout + r.stderr + h.evidence_text())
                rerun = h.source(f"{step}; echo CONTINUED")  # the next run starts clean and owns what it creates
                self.assertEqual(rerun.returncode, 0, rerun.stdout + rerun.stderr); self.assertIn("CONTINUED", rerun.stdout)
                self.assertIn(f"secret owl-mast-test {name} owned", h.world.read_text())
                self.assertEqual([c for c in h.calls.read_text().splitlines() if " label " in c], [])
            finally:
                h.close()

    def test_generated_password_is_never_a_process_argument(self):
        """116/4544181109: the password was a --from-literal argument of kubectl, visible in the process list, while the
        comment said it existed only in the pipe. It is now written to kubectl's stdin by a shell builtin."""
        h = Harness(BASE_WORLD)
        try:
            r = h.source("ensure_secret owl-mast-test owl-mast-db owlmast_app; echo CONTINUED")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr); self.assertIn("CONTINUED", r.stdout)
            calls = h.calls.read_text().splitlines()
            self.assertEqual([c for c in calls if "password=" in c and "--from-file=password=/dev/stdin" not in c], [])
            created = [c for c in calls if " create secret generic owl-mast-db " in c]
            self.assertEqual(len(created), 1)
            self.assertIn("--from-file=password=/dev/stdin", created[0]); self.assertIn("--from-literal=username=owlmast_app", created[0])
            name, size = Path(str(h.calls) + ".stdin").read_text().split()
            self.assertEqual(name, "owl-mast-db")
            self.assertTrue(20 <= int(size) <= 32, size)  # the generated value, without a trailing newline
            self.assertIn("secret owl-mast-test owl-mast-db owned", h.world.read_text())
        finally:
            h.close()
        script = (REPO / "scripts" / "qualify-local-install.sh").read_text()
        self.assertNotIn("--from-literal=password", script)

    def test_replication_never_overwrites_and_reports_its_failure(self):
        """109/4543776464: the destination appears between the absence check and the write, or the write fails."""
        source = "secret owl-mast-test owl-mast-db owned\n"
        h = Harness(BASE_WORLD + source)
        try:
            r = h.source("replicate_secret owl-mast-test owl-mast-db owl-mast-test-external owl-mast-db; echo CONTINUED", STUB_FAIL_ON=" create -f -")
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr); self.assertNotIn("CONTINUED", r.stdout)
            self.assertIn("REFUSED: secret owl-mast-test-external/owl-mast-db could not be replicated from owl-mast-test/owl-mast-db", r.stdout)
            self.assertIn("stub: injected failure", r.stdout)  # the client's error is reported, not discarded
            self.assertNotIn("replicated from", r.stdout.replace("could not be replicated from", ""))
            calls = h.calls.read_text()
            self.assertNotIn(" apply ", calls)
            self.assertNotIn(SENTINEL, r.stdout + r.stderr + h.evidence_text())
        finally:
            h.close()
        # the racing object: absent at the check (the stub answers the check from a world that does not list it yet),
        # present at the write. `create` fails with AlreadyExists and the foreign object is untouched.
        h = Harness(BASE_WORLD + source)
        try:
            race = ("resource_state() { if [ \"$3\" = owl-mast-db ] && [ \"$1\" = owl-mast-test-external ]; then "
                    "printf 'secret owl-mast-test-external owl-mast-db foreign:someone-else\\n' >> \"$STUB_WORLD\"; echo absent; else echo owned; fi; }")
            r = h.source(f"{race}; replicate_secret owl-mast-test owl-mast-db owl-mast-test-external owl-mast-db; echo CONTINUED")
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("could not be replicated", r.stdout); self.assertIn("AlreadyExists", r.stdout)
            self.assertIn("secret owl-mast-test-external owl-mast-db foreign:someone-else", h.world.read_text())
            self.assertNotIn("secret owl-mast-test-external owl-mast-db owned", h.world.read_text())
        finally:
            h.close()

    def test_connect_denial_failure_is_not_swallowed_when_called_under_or(self):
        """4513680539: first-enable calls check_shared_postgres under `||`, which disables set -e in its body."""
        for connect, expected in (("allowed", "CAUGHT"), ("denied", "PASSED")):
            h = Harness(BASE_WORLD)
            try:
                r = h.source("check_shared_postgres owl-mast-test owl-mast-postgresql && echo PASSED || echo CAUGHT", STUB_EXEC_MODE="ac3", STUB_AC3_CONNECT=connect)
                self.assertEqual(r.stdout.strip().splitlines()[-1], expected, r.stdout + r.stderr)
                if connect == "allowed":
                    self.assertIn("FAIL ac3-owl-mast-test-app-cannot-connect-keycloak-db: the principal connected to keycloak", r.stdout)
                    self.assertNotIn("ac3-owl-mast-test-extensions", r.stdout)  # nothing after the failed check ran
            finally:
                h.close()

    def image_check(self, pods, image_id, node_id="sha256:local", digests="docker.io/owl-mast/backend@sha256:import "):
        h = Harness(BASE_WORLD)
        try:
            docker = h.bin / "docker"
            docker.write_text('#!/usr/bin/env bash\nif [[ "$*" == *".status.id"* ]]; then printf %s "$STUB_NODE_ID"; else printf %s "$STUB_NODE_DIGESTS"; fi\n')
            docker.chmod(0o755)
            r = h.source("verify_backend_image combo && echo PASSED || echo CAUGHT", STUB_BACKEND_PODS=pods, STUB_IMAGE_ID=image_id, STUB_NODE_ID=node_id,
                         STUB_NODE_DIGESTS=digests, BACKEND_IMAGE_ID="sha256:local")
            r.calls = h.calls.read_text()
            return r
        finally:
            h.close()

    def test_image_identity_requires_one_running_pod_with_a_non_empty_image_id(self):
        """4513680551: an empty imageID matched any digest list, and items[0] could be the terminating pod."""
        new = "owl-mast-backend-new   <none>\n"
        old = "owl-mast-backend-old   2026-11-09T10:00:00Z\n"
        ok = self.image_check(new, "docker.io/owl-mast/backend@sha256:import")
        self.assertIn("PASSED", ok.stdout, ok.stdout + ok.stderr)
        self.assertIn("ok   combo-image-identity", ok.stdout)
        ok = self.image_check(new, "sha256:local")
        self.assertIn("PASSED", ok.stdout, ok.stdout + ok.stderr)
        # a terminating pod listed first is excluded; the check reads the live one
        ok = self.image_check(old + new, "docker.io/owl-mast/backend@sha256:import")
        self.assertIn("PASSED", ok.stdout, ok.stdout + ok.stderr)
        self.assertIn(" get pod owl-mast-backend-new ", ok.calls)
        self.assertNotIn(" get pod owl-mast-backend-old ", ok.calls)
        for pods, image_id, message in (
            (new, "", "reports no imageID"),
            ("", "docker.io/owl-mast/backend@sha256:import", "expected exactly one Running, non-terminating backend pod"),
            (old, "docker.io/owl-mast/backend@sha256:import", "expected exactly one Running, non-terminating backend pod"),  # only a terminating pod is Running
            ("owl-mast-backend-a   <none>\n" + new, "docker.io/owl-mast/backend@sha256:import", "expected exactly one Running, non-terminating backend pod"),
            (new, "sha256:imp", "does not run the expected local build"),  # a prefix of a listed digest is not a match
        ):
            r = self.image_check(pods, image_id)
            self.assertIn("CAUGHT", r.stdout, (pods, image_id, r.stdout))
            self.assertIn(message, r.stdout, (pods, image_id))
        r = self.image_check("owl-mast-backend-new   <none>\n", "docker.io/owl-mast/backend@sha256:import", node_id="sha256:other")
        self.assertIn("CAUGHT", r.stdout)

    def test_backend_pod_selection_excludes_terminating_and_non_running_pods(self):
        text = SCRIPT.read_text()
        body = text[text.index("verify_backend_image() {"):text.index("\n}\n", text.index("verify_backend_image() {"))]
        self.assertIn("--field-selector=status.phase=Running", body)
        self.assertIn("DELETING:.metadata.deletionTimestamp", body)
        self.assertNotIn("items[0]", body)

    def test_plaintext_fixture_installs_carry_the_explicit_insecure_opt_ins(self):
        """D1: the chart refuses http issuers and weak sslMode unless opted in; every fixture install must opt in."""
        text = SCRIPT.read_text()
        http_issuers = [l for l in text.splitlines() if 'identity.external.issuerUri="http://' in l]
        self.assertGreaterEqual(len(http_issuers), 5)
        self.assertTrue(all("identity.external.allowInsecureIssuer=true" in l for l in http_issuers), http_issuers)
        for key in ("database.external", "identity.keycloak.database.external"):
            weak = [l for l in text.splitlines() if f"--set {key}.sslMode=disable" in l]
            self.assertTrue(weak, key)
            self.assertTrue(all(f"--set {key}.allowInsecureTransport=true" in l for l in weak), weak)

    def test_network_policies_are_part_of_the_release_enumeration(self):
        h = Harness(BASE_WORLD + "networkpolicy owl-mast-test owl-mast-postgresql foreign:unlabelled\n")
        try:
            r = h.run("bundled-bundled")
            self.assertEqual(r.returncode, 2, r.stdout); self.assertIn("preflight networkpolicy owl-mast-test/owl-mast-postgresql", r.stdout)
            self.assertEqual(h.mutating_calls(), [])
        finally:
            h.close()


class ProvisioningHookEvidenceTests(unittest.TestCase):
    """V5 (owner's Kind qualification of PR #116, 2026-11-12): the script read the provisioning hook Job's status and log after
    `helm upgrade --wait`, but the chart deletes the Job and its ConfigMap once the hook succeeded (hook-delete-policy
    before-hook-creation,hook-succeeded), so the read was NotFound and the run stopped at `provision-keycloak-job`. The stub world
    now deletes the hook objects on success like Helm does, and the script proves the hook from what outlives it."""

    RUNTIME = {"STUB_RUNTIME": "1", "STUB_EXEC_MODE": "ac3", "STUB_BACKEND_PODS": "owl-mast-backend-new   <none>\n",
               "STUB_IMAGE_ID": "docker.io/owl-mast/backend@sha256:import", "HOOK_GONE_TIMEOUT": "0"}
    FE_RUN_ID = "om-01-02-followup-stub-01"

    def direct_hook_reads(self, calls):  # the ownership query (--ignore-not-found, absence is an answer) is not a read of the Job's status
        return [c for c in calls.splitlines() if " logs job/" in c or (" get job " in c and "--ignore-not-found" not in c)]

    def step(self, step, **extra):
        h = Harness(BASE_WORLD)
        try:
            r = h.run(step, **{**self.RUNTIME, **extra})
            r.calls = h.calls.read_text()
            r.world = h.world.read_text()
            runtime = h.evidence / "runtime"
            r.evidence = {p.stem: p.read_text() for p in runtime.glob("*.txt")} if runtime.exists() else {}
            return r
        finally:
            h.close()

    def first_enable(self, **extra):
        return self.step("first-enable", OWLMAST_FOLLOWUP_RUN_ID=self.FE_RUN_ID, STUB_FE_RUN_ID=self.FE_RUN_ID, **extra)

    def test_bundled_bundled_passes_when_the_succeeded_hook_job_is_gone(self):
        r = self.step("bundled-bundled")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for line in ("ok   provision-keycloak-upgrade", "ok   provision-keycloak-revision (revision 1 -> 2, deployed)",
                     "ok   provision-keycloak-hook-run (hook Job/owl-mast-postgresql-provision-keycloak events=pre-upgrade phase=Succeeded started_at=",
                     "ok   provision-keycloak-identity-unchanged (role=16385 database=16386 owner=16385)",
                     "ok   provision-keycloak-hook-removed (hook Job and ConfigMap absent after success",
                     "ok   provision-keycloak-idempotent", "qualification steps complete: bundled-bundled"):
            self.assertIn(line, r.stdout)
        self.assertNotIn("FAIL", r.stdout)
        # the world really has no hook Job after the successful upgrade, and the script never reads it or its log directly
        self.assertNotIn("job owl-mast-test owl-mast-postgresql-provision-keycloak", r.world)
        self.assertEqual(self.direct_hook_reads(r.calls), [])
        self.assertEqual(r.evidence["provision-keycloak-identity-before"].splitlines()[-1], r.evidence["provision-keycloak-identity-after"].splitlines()[-1])
        self.assertEqual(r.evidence["provision-keycloak-hook-removed"].splitlines(),
                         ["job owl-mast-test/owl-mast-postgresql-provision-keycloak absent", "configmap owl-mast-test/owl-mast-postgresql-provision-scripts absent"])
        # the identifiers are read before the upgrade and again after it
        calls = r.calls.splitlines()
        upgrade = next(i for i, c in enumerate(calls) if "provisionKeycloakDatabase=true" in c)
        retire = next(i for i, c in enumerate(calls) if "bootstrapAdmin.enabled=false" in c)
        reads = [i for i, c in enumerate(calls) if "'role='||r.oid" in c and i < retire]  # the retirement reads them once more
        self.assertEqual(len(reads), 2, reads); self.assertLess(reads[0], upgrade); self.assertGreater(reads[1], upgrade)

    def test_a_direct_read_of_the_succeeded_hook_job_is_not_found_in_the_stub_world(self):
        """What made the old script fail on the cluster, reproduced by the stub: the Job read and the log read are NotFound."""
        h = Harness(BASE_WORLD)
        try:
            body = ('h upgrade owl-mast "$CHART" -n "$NS" --wait --set postgresql.provisionKeycloakDatabase=true >/dev/null; '
                    'k -n "$NS" get job owl-mast-postgresql-provision-keycloak -o jsonpath="{.status.succeeded}" && echo get=0 || echo get=1; '
                    'k -n "$NS" logs job/owl-mast-postgresql-provision-keycloak && echo logs=0 || echo logs=1')
            r = h.source(body)
            self.assertIn("get=1", r.stdout); self.assertIn("logs=1", r.stdout)
            self.assertEqual(r.stderr.count('(NotFound): jobs.batch "owl-mast-postgresql-provision-keycloak" not found'), 2, r.stderr)
            r = h.source(body.replace(">/dev/null;", ">/dev/null 2>&1 || true;"), STUB_HOOK="failed")  # a failed hook Job stays for diagnosis
            self.assertIn("get=0", r.stdout); self.assertIn("logs=0", r.stdout)
        finally:
            h.close()

    def test_changed_or_unreadable_identifiers_fail_the_step(self):
        for after, message in (("role=16999 database=16386 owner=16999", "FAIL provision-keycloak-identity: provisioning dropped or recreated an existing role or database"),
                               ("role=16385 database=17001 owner=16385", "FAIL provision-keycloak-identity: provisioning dropped or recreated an existing role or database"),
                               ("role=16385 database=16386 owner=10", "FAIL provision-keycloak-identity: provisioning dropped or recreated an existing role or database"),
                               ("", "FAIL provision-keycloak-identity-after"),
                               ("stub ok", "FAIL provision-keycloak-identity-after: the Keycloak role/database identifiers were not read")):
            with self.subTest(after=after):
                r = self.step("bundled-bundled", STUB_KC_IDENTITY_1=after)
                self.assertNotEqual(r.returncode, 0, r.stdout)
                self.assertIn(message, r.stdout)
                self.assertNotIn("ok   provision-keycloak-idempotent", r.stdout)
                self.assertNotIn("qualification steps complete", r.stdout)
        r = self.step("bundled-bundled", STUB_KC_IDENTITY_0="")  # unreadable before the upgrade: the upgrade is never started
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("FAIL provision-keycloak-identity-before", r.stdout)
        self.assertNotIn("provisionKeycloakDatabase=true", r.calls)

    def test_a_failed_hook_fails_the_step_at_the_upgrade(self):
        r = self.step("bundled-bundled", STUB_HOOK="failed")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("FAIL provision-keycloak-upgrade", r.stdout)
        self.assertIn("pre-upgrade hooks failed", r.evidence["provision-keycloak-upgrade"])
        for later in ("provision-keycloak-revision-after", "provision-keycloak-identity-after", "provision-keycloak-idempotent"):
            self.assertNotIn(later, r.stdout)

    def test_a_hook_job_that_outlives_its_success_fails_the_step(self):
        r = self.step("bundled-bundled", STUB_HOOK="kept")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("FAIL provision-keycloak-hook-removed: hook job owl-mast-test/owl-mast-postgresql-provision-keycloak is not absent after the successful upgrade (owned)", r.stdout)
        self.assertNotIn("ok   provision-keycloak-idempotent", r.stdout)

    def test_an_upgrade_without_a_new_deployed_revision_fails_the_step(self):
        r = self.step("bundled-bundled", STUB_HELM_NO_NEW_REVISION="1")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("FAIL provision-keycloak-revision: the upgrade left no new deployed revision (before 1, after 1)", r.stdout)

    def test_the_schema_check_is_kept(self):
        r = self.step("bundled-bundled", STUB_KC_SCHEMA="f")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("FAIL keycloak schema", r.stdout)
        self.assertNotIn("ok   provision-keycloak-idempotent", r.stdout)

    def test_first_enable_passes_when_the_succeeded_hook_job_is_gone(self):
        r = self.first_enable()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for line in ("ok   fe2-revision (revision 1 -> 2, deployed)", "ok   fe2-hook-removed",
                     "ok   fe2-hook-run (hook Job/owl-mast-fe-postgresql-provision-keycloak events=pre-upgrade phase=Succeeded started_at=",
                     "ok   fe3-hook-run (hook Job/owl-mast-fe-postgresql-provision-keycloak events=pre-upgrade phase=Succeeded started_at=",
                     "ok   fe2-first-enable-provisioned (role and database absent before, present after the pre-upgrade hook: role=16385 database=16386 owner=16385)",
                     "ok   fe3-revision (revision 2 -> 3, deployed)", "ok   fe3-identity-unchanged", "ok   fe3-hook-removed", "ok   fe3-retry-no-op", "ok   fe3-keycloak-schema-intact",
                     "ok   fe2-durable-work (the installed backend claimed the synthetic audit.publish item as the restricted principal",
                     "ok   fe5-revision (revision 3 -> 4, deployed)",
                     "ok   fe5-bootstrap-admin-retired (injected before; after bootstrapAdmin.enabled=false no bootstrap variable and no reference to the bootstrap Secret",
                     "qualification steps complete: first-enable"):
            self.assertIn(line, r.stdout)
        self.assertNotIn("FAIL", r.stdout)
        self.assertEqual(self.direct_hook_reads(r.calls), [])

    def test_every_all_run_retires_the_bootstrap_admin_and_replaces_the_keycloak_pod(self):
        """Review 5884091345: the re-provisioning upgrade leaves the Keycloak pod template unchanged, so `all` never replaced the
        Keycloak pod. Bundled-bundled now ends with the retirement, which must replace it. This checks the step only: that the
        retirement runs after the re-provisioning, replaces the pod and records what the terminating-pod wait saw."""
        r = self.step("bundled-bundled")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("ok   bb-retire-bootstrap-admin-retired", r.stdout)
        self.assertEqual(r.evidence["bb-retire-keycloak-pod-replaced"].splitlines(),
                         ["before: owl-mast-keycloak-old-abc12", "after: owl-mast-keycloak-new-def34"])
        wait = r.evidence["bb-retire-terminating-wait"].splitlines()
        self.assertEqual(len(wait), 2, wait)  # review 5884955290 R4-4: when helm returned, then the wait's one read
        self.assertRegex(wait[0], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ helm upgrade returned$")
        self.assertRegex(wait[1], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ terminating: none$")
        calls = r.calls.splitlines()
        retire = [c for c in calls if c.startswith("helm ") and "bootstrapAdmin.enabled=false" in c]
        self.assertEqual(len(retire), 1, retire)
        self.assertIn(" --reuse-values", retire[0])
        provision = [i for i, c in enumerate(calls) if c.startswith("helm ") and "provisionKeycloakDatabase=true" in c]
        self.assertLess(provision[-1], calls.index(retire[0]))

    def test_a_keycloak_pod_being_deleted_counts_neither_before_nor_after_the_retirement(self):
        """Review cycle 3: keycloak_pod_names drops listed pods that carry a deletionTimestamp."""
        r = self.step("bundled-bundled", STUB_RETIRE="deleting-listed")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.evidence["bb-retire-keycloak-pod-replaced"].splitlines(),
                         ["before: owl-mast-keycloak-old-abc12", "after: owl-mast-keycloak-new-def34"])

    def test_the_retirement_fails_when_the_keycloak_pod_was_not_replaced(self):
        r = self.step("bundled-bundled", STUB_RETIRE="same-pod")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("FAIL bb-retire: the Keycloak pod was not replaced by the retirement (before: owl-mast-keycloak-old-abc12; after: owl-mast-keycloak-old-abc12)", r.stdout)
        self.assertNotIn("ok   bb-retire-bootstrap-admin-retired", r.stdout)

    def test_first_enable_retires_the_bootstrap_admin_and_proves_it_from_the_pod(self):
        """E01-R-01: the switch-off of the Keycloak bootstrap admin was documented as part of the Kind qualification but no step ran it."""
        r = self.first_enable()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        calls = r.calls.splitlines()
        retire = [c for c in calls if c.startswith("helm ") and "bootstrapAdmin.enabled=false" in c]
        self.assertEqual(len(retire), 1, retire)
        # the Secret value is pointed at a name that does not exist: a remaining reference would fail `helm upgrade --wait`
        self.assertIn("identity.keycloak.bootstrapExistingSecret=absent-keycloak-bootstrap-secret", retire[0])
        self.assertIn(" --wait ", retire[0])
        self.assertIn("identity.bundled=true", retire[0])
        self.assertNotIn("provisionKeycloakDatabase=true", retire[0])
        # the retirement runs after the retry and before the fixture is uninstalled
        order = [i for i, c in enumerate(calls) if c.startswith("helm ") and (" upgrade " in c or " uninstall " in c)]
        self.assertEqual([("uninstall" if " uninstall " in calls[i] else "retire" if "bootstrapAdmin.enabled=false" in calls[i] else "upgrade") for i in order][-2:], ["retire", "uninstall"])
        self.assertIn("KC_BOOTSTRAP_ADMIN_PASSWORD=owl-mast-fe-keycloak-bootstrap", r.evidence["fe5-keycloak-env-before"])
        self.assertNotIn("KC_BOOTSTRAP_ADMIN", r.evidence["fe5-keycloak-env-after"])
        self.assertIn("KC_DB_PASSWORD=owl-mast-fe-keycloak-db", r.evidence["fe5-keycloak-env-after"])

    def test_the_retirement_reads_the_secret_references_only_once_the_replaced_pod_is_gone(self):
        """Review 5883535263: `helm upgrade --wait` can return while the replaced Keycloak pod still terminates, and that pod still
        names the bootstrap Secret; reading the references then would report a retirement that worked as failed."""
        r = self.first_enable(STUB_TERMINATING="1", TERMINATING_POD_TIMEOUT="30")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("ok   fe5-bootstrap-admin-retired", r.stdout)
        calls = r.calls.splitlines()
        waits = [i for i, c in enumerate(calls) if "?(@.metadata.deletionTimestamp)" in c]
        reads = [i for i, c in enumerate(calls) if " get deploy,pods " in c and "-o json" in c]
        self.assertEqual(len(waits), 2, waits)  # one read still saw the terminating pod, the next one none
        self.assertEqual([line.split(" ", 1)[1] for line in r.evidence["fe5-terminating-wait"].splitlines()],
                         ["helm upgrade returned", "terminating: owl-mast-fe-keycloak-old-abc12", "terminating: none"])
        for i in waits:  # review 5884091345: the exact namespace and selector of the release's Keycloak pods
            self.assertIn(" -n owl-mast-test ", calls[i])
            self.assertIn(" -l app.kubernetes.io/instance=owl-mast-fe,app.kubernetes.io/component=keycloak ", calls[i])
        self.assertEqual(len(reads), 1, reads)
        self.assertLess(waits[-1], reads[0])
        r = self.first_enable(STUB_TERMINATING="1000", TERMINATING_POD_TIMEOUT="0")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("FAIL fe5: pod(s) still terminating after 0s: owl-mast-fe-keycloak-old-abc12", r.stdout)
        self.assertNotIn("ok   fe5-bootstrap-admin-retired", r.stdout)
        self.assertNotIn(" get deploy,pods ", r.calls)

    def test_a_failed_read_of_the_terminating_pods_is_recorded_and_fails_the_retirement(self):
        """Review 5884955290 R4-10: the wait's evidence names a read that failed, instead of ending without a line."""
        r = self.first_enable(STUB_TERMINATING_READ="fail")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("FAIL fe5: the release's Keycloak pods could not be listed", r.stdout)
        self.assertEqual([line.split(" ", 1)[1] for line in r.evidence["fe5-terminating-wait"].splitlines()],
                         ["helm upgrade returned", "read failed"])
        self.assertNotIn(" get deploy,pods ", r.calls)

    def test_a_rerun_with_the_same_prefix_keeps_the_earlier_reads(self):
        """Review 5884955290 R4-12: the wait appends, so a second retirement in the same evidence directory keeps the first one's reads."""
        h = Harness(BASE_WORLD)
        try:
            out = h.evidence / "runtime"; out.mkdir(parents=True, exist_ok=True)
            (out / "rr-terminating-wait.txt").write_text("2026-11-13T00:00:00Z terminating: none\n")
            r = h.source("OUT='%s'; NS=owl-mast-test; wait_no_terminating_pods rr owl-mast-fe" % out, STUB_TERMINATING="0")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            lines = (out / "rr-terminating-wait.txt").read_text().splitlines()
            self.assertEqual(lines[0], "2026-11-13T00:00:00Z terminating: none")
            self.assertEqual([line.split(" ", 1)[1] for line in lines[1:]], ["terminating: none"])
        finally:
            h.close()

    def test_every_run_records_its_own_source(self):
        """Review 5884955290 R4-3 and cycle 5: the script appends a record at the start, before the retirement upgrade
        and at the end: the commit, whether the whole tree differs from it, and digests of the chart and of itself,
        computed here independently of the script."""
        r = self.step("bundled-bundled")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        blocks = [b.splitlines() for b in re.split(r"(?m)^(?=== )", r.evidence["source"]) if b]
        self.assertEqual([re.sub(r"^== \S+ ", "", b[0]) for b in blocks],
                         ["start: bundled-bundled", "before bb-retire-retire-upgrade", "end: bundled-bundled"])
        head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        porcelain = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain"], capture_output=True, text=True, check=True).stdout
        for block in blocks:
            self.assertRegex(block[0], r"^== \d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ ")
            self.assertEqual(block[1], f"head {head}")
            self.assertEqual(block[2], f"chart {CHART} sha256 {chart_digest(CHART)}")
            self.assertEqual(block[3], f"script sha256 {hashlib.sha256(SCRIPT.read_bytes()).hexdigest()}")
            self.assertEqual(block[4], "tree clean" if not porcelain else "tree dirty:")
        self.assertEqual(len(re.findall(r"source \((start|before|end)[^)]*\): head [0-9a-f]{40}, tree (clean|DIRTY \(see source.txt\)), "
                                        rf"chart sha256 {chart_digest(CHART)}", r.stdout)), 3)

    @staticmethod
    def throwaway_checkout(h):
        """A git repository holding a copy of the script and a one-file chart, so a test can change the chart and the
        tree without touching the real checkout."""
        repo = h.tmp / "repo"
        (repo / "scripts").mkdir(parents=True)
        shutil.copy(SCRIPT, repo / "scripts" / SCRIPT.name)
        chart = repo / "deploy" / "helm" / "owl-mast"; chart.mkdir(parents=True)
        (chart / "Chart.yaml").write_text("name: owl-mast\n")
        (repo / "settings.gradle.kts").write_text("// root build input\n")
        git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
        subprocess.run([*git, "init", "-q"], check=True)
        subprocess.run([*git, "add", "-A"], check=True)
        subprocess.run([*git, "commit", "-q", "-m", "fixture"], check=True)
        return repo, chart

    def test_the_retirement_stops_before_its_upgrade_when_the_chart_changed_after_the_first_record(self):
        """Review cycle 6 (R6-2): the record before the retirement upgrade is what keeps a chart edited mid-run (the
        22:39Z case) from being installed, so a changed chart must stop the retirement before `helm upgrade`."""
        def retire(change_chart):
            h = Harness(BASE_WORLD + "release owl-mast-test owl-mast-fe owned\n")
            try:
                repo, chart = self.throwaway_checkout(h)
                change = f"echo 'version: 2' >> '{chart / 'Chart.yaml'}'; " if change_chart else ""
                body = (f"source '{repo / 'scripts' / SCRIPT.name}'; record_source first || exit 10; {change}"
                        "retire_bootstrap_admin fe5 owl-mast-fe fe3-identity-after --timeout 10m && echo PASSED || echo CAUGHT")
                r = subprocess.run(["bash", "-c", body], env=h.env(**self.RUNTIME), stdin=subprocess.DEVNULL, capture_output=True, text=True, check=False, timeout=60)
                return r, h.calls.read_text()
            finally:
                h.close()
        # Control: on an unchanged chart the retirement gets as far as its upgrade.
        r, calls = retire(False)
        self.assertIn(" upgrade owl-mast-fe ", calls, r.stdout + r.stderr)
        self.assertIn("ok   fe5-retire-upgrade", r.stdout)
        self.assertNotIn("the chart changed", r.stdout)
        r, calls = retire(True)
        self.assertEqual(r.stdout.strip().splitlines()[-1], "CAUGHT", r.stdout + r.stderr)
        self.assertIn("FAIL source (before fe5-retire-upgrade): the chart changed during the run", r.stdout)
        self.assertNotIn(" upgrade ", calls)
        self.assertNotIn("ok   fe5-retire-upgrade", r.stdout)

    def test_the_source_record_names_dirty_paths_keeps_earlier_records_and_fails_on_a_changed_chart(self):
        """Review cycle 5: dirty detection covers the whole tree (a root Gradle file builds the image too), each call
        appends, and a chart that changes after the first record fails the run."""
        h = Harness(BASE_WORLD)
        try:
            repo, chart = self.throwaway_checkout(h)
            clean_digest = chart_digest(chart)
            body = (f"source '{repo / 'scripts' / SCRIPT.name}'; record_source first || exit 10; "
                    f"echo changed >> '{repo / 'settings.gradle.kts'}'; record_source second || exit 11; "
                    f"echo 'version: 2' >> '{chart / 'Chart.yaml'}'; record_source third || exit 12")
            r = subprocess.run(["bash", "-c", body], env=h.env(), stdin=subprocess.DEVNULL, capture_output=True, text=True, check=False, timeout=60)
            self.assertEqual(r.returncode, 12, r.stdout + r.stderr)
            text = (h.evidence / "runtime" / "source.txt").read_text()
            blocks = [b.splitlines() for b in re.split(r"(?m)^(?=== )", text) if b]
            self.assertEqual([b[0].split(" ", 2)[2] for b in blocks], ["first", "second", "third"])
            self.assertEqual(blocks[0][2], f"chart {chart} sha256 {clean_digest}")
            self.assertEqual(blocks[0][4:], ["tree clean"])
            self.assertEqual(blocks[1][2], f"chart {chart} sha256 {clean_digest}")
            self.assertEqual(blocks[1][4:], ["tree dirty:", " M settings.gradle.kts"])
            self.assertNotEqual(chart_digest(chart), clean_digest)
            self.assertEqual(blocks[2][2], f"chart {chart} sha256 {chart_digest(chart)}")
            self.assertEqual(blocks[2][4:], ["tree dirty:", " M deploy/helm/owl-mast/Chart.yaml", " M settings.gradle.kts"])
            self.assertIn("source (second): head", r.stdout)
            self.assertIn("tree DIRTY (see source.txt)", r.stdout)
            self.assertIn(f"FAIL source (third): the chart changed during the run (sha256 {clean_digest}, now {chart_digest(chart)})", r.stdout)
        finally:
            h.close()

    def test_first_enable_fails_when_the_bootstrap_admin_is_still_injected_after_the_retirement(self):
        r = self.first_enable(STUB_RETIRE="kept")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("FAIL fe5: the Keycloak pod still takes a bootstrap admin variable or references the bootstrap Secret", r.stdout)
        self.assertNotIn("ok   fe5-bootstrap-admin-retired", r.stdout)
        self.assertNotIn("qualification steps complete", r.stdout)
        self.assertNotIn("helm uninstall", r.calls)  # the failed fixture is left for diagnosis

    def test_first_enable_fails_when_a_pod_still_mounts_the_bootstrap_secret(self):
        """The environment alone is not the whole pod: a Secret volume (or envFrom, or an init container) would keep the reference."""
        r = self.first_enable(STUB_RETIRE="volume")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("FAIL fe5: a Deployment or a running pod of the release still references the bootstrap Secret", r.stdout)
        self.assertNotIn("ok   fe5-bootstrap-admin-retired", r.stdout)
        self.assertIn('"secretName": "owl-mast-fe-keycloak-bootstrap"', r.evidence["fe5-secret-references"])
        self.assertNotIn("KC_DB_PASSWORD", r.evidence["fe5-secret-references"])  # only the matching name fields are kept
        r = self.first_enable()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("no reference", r.evidence["fe5-secret-references"])

    def test_the_retirement_needs_the_admin_to_be_injected_before_it(self):
        """A release that never injected the admin proves nothing about switching it off."""
        h = Harness(BASE_WORLD)
        try:
            (h.tmp / "world.txt.retired").write_text("")
            r = h.source("retire_bootstrap_admin fe5 owl-mast-fe fe3-identity-after --timeout 10m && echo PASSED || echo CAUGHT", **self.RUNTIME)
            self.assertEqual(r.stdout.strip().splitlines()[-1], "CAUGHT", r.stdout + r.stderr)
            self.assertIn("FAIL fe5: the bootstrap admin was not injected before the retirement", r.stdout)
            self.assertNotIn("helm upgrade", h.calls.read_text())
        finally:
            h.close()

    def test_every_migration_of_the_checkout_must_be_applied_by_the_application_principal(self):
        """Retro R12: the script only looked for V001, so a database that never ran the jobs and audit migrations passed."""
        self.assertGreaterEqual(len(MIGRATIONS), 5, MIGRATIONS)
        r = self.step("bundled-bundled", STUB_FLYWAY_HISTORY="001|true\\n")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("FAIL flyway history: migration 002 is not applied", r.stdout)
        r = self.step("bundled-bundled", STUB_FLYWAY_HISTORY="".join(f"{v}|true\\n" for v in MIGRATIONS[:-1]) + f"{MIGRATIONS[-1]}|false\\n")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn(f"FAIL flyway history: migration {MIGRATIONS[-1]} is not applied", r.stdout)
        r = self.step("bundled-bundled", STUB_MIGRATED_BY="owlmast_admin")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("FAIL migrations were not all applied by the application principal owlmast_app", r.stdout)
        r = self.step("bundled-bundled", STUB_TABLE_OWNER="owlmast_admin")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("FAIL jobs.work_item is not owned by owlmast_app", r.stdout)
        # a table added to either schema later is covered without naming it in the script
        r = self.step("bundled-bundled", STUB_EXTRA_TABLE="table-owner|jobs.future_table|owlmast_admin")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("FAIL a jobs or audit table is not owned by owlmast_app: table-owner|jobs.future_table|owlmast_admin", r.stdout)
        r = self.step("bundled-bundled")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(f"ok   ac3-owl-mast-test-flyway-history (applied: {' '.join(MIGRATIONS)} )", r.stdout)
        self.assertIn("ok   ac3-owl-mast-test-migrated-by", r.stdout)

    def test_a_checkout_without_migrations_cannot_pass_the_migration_check(self):
        """An empty expectation (moved directory, wrong root) must not read as 'everything applied'."""
        h = Harness(BASE_WORLD)
        try:
            r = h.source("expected_migrations() { :; }; check_shared_postgres owl-mast-test owl-mast-postgresql && echo PASSED || echo CAUGHT", STUB_EXEC_MODE="ac3")
            self.assertEqual(r.stdout.strip().splitlines()[-1], "CAUGHT", r.stdout + r.stderr)
            self.assertIn("FAIL flyway history: no migration found in this checkout", r.stdout)
        finally:
            h.close()

    def test_every_combination_with_a_database_proves_durable_work_on_the_database_its_backend_uses(self):
        """E01-R-01: the proof runs wherever a backend is installed, against the bundled or the external PostgreSQL it connects to."""
        for step, namespace, deployment in (("bundled-bundled", "owl-mast-test", "owl-mast-postgresql"), ("bundled-external", "owl-mast-test", "owl-mast-postgresql"),
                                            ("external-bundled", "owl-mast-test-external", "external-postgresql"), ("external-external", "owl-mast-test-external", "external-postgresql")):
            with self.subTest(step):
                r = self.step(step)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertIn(f"ok   {step}-durable-work (", r.stdout)
                enqueue = [c for c in r.calls.splitlines() if "insert into audit.publication_intent" in c]
                self.assertEqual(len(enqueue), 1, enqueue)
                self.assertIn(f"-n {namespace} exec deploy/{deployment} ", enqueue[0])
                r = self.step(step, STUB_DURABLE_WORK="durable-work|FAILED|0|false|owl-mast-backend/pod/1|x")
                self.assertNotEqual(r.returncode, 0, r.stdout)
                self.assertIn(f"FAIL {step}-durable-work", r.stdout)

    def test_the_installed_backend_must_finish_real_durable_work(self):
        """Retro R12: the scheduler had never been shown to run under the chart's restricted principal."""
        r = self.step("bundled-bundled")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("ok   bundled-bundled-durable-work (", r.stdout)
        enqueue = [c for c in r.calls.splitlines() if "insert into audit.publication_intent" in c]
        self.assertEqual(len(enqueue), 1, enqueue)
        # written as the application principal, for the synthetic tenant, as the publisher's own work type
        self.assertIn("OWLMAST_APP_PASSWORD", enqueue[0])
        self.assertIn("'qualification'", enqueue[0])
        self.assertIn("'audit.publish'", enqueue[0])
        for state, reason in (("durable-work|PENDING|0|false|-|-", "still pending at the deadline"),
                              ("durable-work|FAILED|0|false|owl-mast-backend/pod/1|io.r2dbc.postgresql.ExceptionFactory$PostgresqlBadGrammarException", "terminal failure"),
                              ("durable-work|SUCCEEDED|0|true|owl-mast-backend/pod/1|-", "succeeded without a history row"),
                              ("durable-work|SUCCEEDED|1|true|-|-", "no lease owner: not claimed by the backend"),
                              ("stub ok", "unreadable")):
            with self.subTest(reason):
                r = self.step("bundled-bundled", STUB_DURABLE_WORK=state)
                self.assertNotEqual(r.returncode, 0, r.stdout)
                self.assertIn("FAIL bundled-bundled-durable-work: the synthetic audit.publish item was not published within 0s", r.stdout)
                self.assertNotIn("ok   bundled-bundled-durable-work (", r.stdout)
                self.assertNotIn("provision-keycloak-upgrade", r.stdout)  # the step stopped there

    def test_first_enable_fails_when_the_role_is_missing_after_the_hook_or_recreated_by_the_retry(self):
        r = self.first_enable(STUB_KC_IDENTITY_1="")  # the Keycloak principal cannot log in after the first enable
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("FAIL fe2-keycloak-identity", r.stdout)
        self.assertNotIn("ok   fe2-first-enable-provisioned", r.stdout)
        r = self.first_enable(STUB_KC_IDENTITY_2="role=16385 database=17001 owner=16385")  # the retry recreated the database
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("FAIL fe3-identity: provisioning dropped or recreated an existing role or database", r.stdout)
        self.assertNotIn("ok   fe3-retry-no-op", r.stdout)
        r = self.first_enable(STUB_HOOK="failed")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("FAIL fe2-enable-upgrade", r.stdout)

    # -- cycle-8 review of PR #116 (review 5871692033): every check above is equally true when no hook ran. The run of the hook
    # is read from the release record (`helm status -o json`, hooks[].last_run), which outlives the deleted Job.
    HOOK_RUN_FAILURES = (
        ("skipped", "the release record lists 0 hooks of kind Job named {job}; the hook was not rendered for this upgrade"),
        ("not-run", "the hook Job last_run.phase is '', not Succeeded; the hook did not run to success on this upgrade"),
        ("stale", "the hook Job last_run.started_at 2026-11-07T09:00:00.123456789+01:00 is earlier than the start of this upgrade"),
        ("phase-failed", "the hook Job last_run.phase is 'Failed', not Succeeded"),
        ("phase-running", "the hook Job last_run.phase is 'Running', not Succeeded"),
    )

    def test_bundled_bundled_fails_when_the_release_record_does_not_show_the_hook_ran(self):
        for mode, reason in self.HOOK_RUN_FAILURES:
            with self.subTest(mode=mode):
                r = self.step("bundled-bundled", STUB_HOOK=mode)
                self.assertNotEqual(r.returncode, 0, r.stdout)
                self.assertIn("FAIL provision-keycloak-hook-run: " + reason.format(job="owl-mast-postgresql-provision-keycloak"), r.stdout)
                # everything the review listed still holds without the hook: the upgrade, the new revision, and no hook object
                self.assertIn("ok   provision-keycloak-upgrade", r.stdout)
                self.assertIn("ok   provision-keycloak-revision (revision 1 -> 2, deployed)", r.stdout)
                self.assertNotIn("job owl-mast-test owl-mast-postgresql-provision-keycloak", r.world)
                for later in ("provision-keycloak-identity-unchanged", "provision-keycloak-hook-removed", "ok   provision-keycloak-idempotent", "qualification steps complete"):
                    self.assertNotIn(later, r.stdout)

    def test_first_enable_retry_fails_when_the_release_record_does_not_show_the_hook_ran(self):
        for mode, reason in self.HOOK_RUN_FAILURES:
            with self.subTest(mode=mode):
                r = self.first_enable(STUB_HOOK_2=mode)  # the first enable ran its hook; only the retry (fe3) did not
                self.assertNotEqual(r.returncode, 0, r.stdout)
                self.assertIn("ok   fe2-hook-run", r.stdout)
                self.assertIn("ok   fe2-first-enable-provisioned", r.stdout)
                self.assertIn("ok   fe3-retry-upgrade", r.stdout)
                self.assertIn("ok   fe3-revision (revision 2 -> 3, deployed)", r.stdout)
                self.assertIn("FAIL fe3-hook-run: " + reason.format(job="owl-mast-fe-postgresql-provision-keycloak"), r.stdout)
                for later in ("fe3-identity-unchanged", "fe3-hook-removed", "ok   fe3-retry-no-op", "qualification steps complete"):
                    self.assertNotIn(later, r.stdout)

    def test_first_enable_fails_when_the_release_record_does_not_show_the_first_hook_ran(self):
        r = self.first_enable(STUB_HOOK="skipped")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("FAIL fe2-hook-run: the release record lists 0 hooks of kind Job named owl-mast-fe-postgresql-provision-keycloak", r.stdout)
        self.assertNotIn("ok   fe2-first-enable-provisioned", r.stdout)

    def test_an_unreadable_or_malformed_release_record_fails_the_step(self):
        for mode, message in (("error", "FAIL provision-keycloak-hook-run: the release record of owl-mast could not be read (helm status -o json exit 1; not evidence)"),
                              ("malformed", "FAIL provision-keycloak-hook-run: the helm status output is not JSON"),
                              ("old-revision", "FAIL provision-keycloak-hook-run: the record is of revision 1, not of the deployed revision 2")):
            with self.subTest(mode=mode):
                r = self.step("bundled-bundled", STUB_STATUS_JSON=mode)
                self.assertNotEqual(r.returncode, 0, r.stdout)
                self.assertIn(message, r.stdout)
                self.assertNotIn("ok   provision-keycloak-idempotent", r.stdout)

    def test_the_release_record_check_accepts_only_a_succeeded_run_of_this_upgrade(self):
        """The evaluator on its own, with records in the shape Helm 4.3.1 prints (taken from an install and upgrade run with the
        4.3.1 module): time formats it must read, and shapes it must refuse."""
        job = "owl-mast-postgresql-provision-keycloak"
        def record(last_run, version=2, kind="Job", name=job, events=("pre-upgrade",)):
            return {"name": "owl-mast", "info": {"last_deployed": "2026-11-12T10:01:50.545494161+01:00", "status": "deployed"}, "version": version,
                    "hooks": [{"name": "owl-mast-postgresql-provision-scripts", "kind": "ConfigMap", "events": ["pre-upgrade"], "weight": -5,
                               "last_run": {"started_at": "2026-11-12T10:01:50.545519722+01:00", "completed_at": "2026-11-12T10:01:50.545521572+01:00", "phase": "Succeeded"}},
                              {"name": name, "kind": kind, "events": list(events), "last_run": last_run}]}
        ok = {"started_at": "2026-11-12T10:01:50.545521982+01:00", "completed_at": "2026-11-12T10:01:50.545522612+01:00", "phase": "Succeeded"}
        since = 1794474110  # 2026-11-12T09:01:50Z, the second in which that hook started
        cases = (
            (record(ok), since, 0, "verdict: ok"),
            (record(ok), since + 1, 1, "is earlier than the start of this upgrade"),
            (record({**ok, "started_at": "2026-11-12T09:01:50Z", "completed_at": "2026-11-12T09:01:50.5Z"}), since, 0, "verdict: ok"),  # UTC, no or short fraction
            (record({**ok, "started_at": "2026-11-12T04:01:50.9-05:00", "completed_at": "2026-11-12T04:01:51-05:00"}), since, 0, "verdict: ok"),  # a negative offset
            (record({**ok, "started_at": "2026-11-12T11:01:49.999999999+02:00"}), since, 1, "is earlier than the start of this upgrade"),  # one nanosecond early
            (record({**ok, "started_at": "2026-11-12 10:01:50"}), since, 1, "last_run.started_at is missing or not an RFC 3339 time"),
            (record({**ok, "started_at": "2026-13-45T10:01:50Z"}), since, 1, "last_run.started_at is not a valid time"),
            (record({"phase": "Succeeded"}), since, 1, "last_run.started_at is missing or not an RFC 3339 time"),
            (record({"started_at": ok["started_at"], "phase": "Succeeded"}), since, 1, "last_run.completed_at is missing or not an RFC 3339 time"),
            (record({**ok, "completed_at": "2026-11-12T10:01:50.5+01:00"}), since, 1, "completed_at is earlier than its started_at"),
            (record({**ok, "phase": "Unknown"}), since, 1, "last_run.phase is 'Unknown', not Succeeded"),
            (record({"phase": ""}), since, 1, "last_run.phase is '', not Succeeded"),
            (record(None), since, 1, "the hook Job has no last_run"),
            (record(ok, kind="ConfigMap"), since, 1, f"lists 0 hooks of kind Job named {job}"),
            (record(ok, name="other-postgresql-provision-keycloak"), since, 1, f"lists 0 hooks of kind Job named {job}"),
            (record(ok, events=("post-upgrade",)), since, 1, "the hook Job is not a pre-upgrade hook"),
            (record(ok, version=3), since, 1, "the record is of revision 3, not of the deployed revision 2"),
            (record(ok, version="2"), since, 1, "the record is of revision 2, not of the deployed revision 2"),
            ({"name": "owl-mast", "version": 2}, since, 1, f"lists 0 hooks of kind Job named {job}"),  # hooks has omitempty
            ({"name": "owl-mast", "version": 2, "hooks": {}}, since, 1, "hooks is not a list of objects"),
            ({"name": "owl-mast", "version": 2, "hooks": ["x"]}, since, 1, "hooks is not a list of objects"),
            ([], since, 1, "the helm status output is not a release object"),
            ("", since, 1, "the helm status output is not JSON"),
        )
        h = Harness(BASE_WORLD)
        try:
            for i, (doc, not_before, code, text) in enumerate(cases):
                with self.subTest(case=i, text=text):
                    payload = doc if isinstance(doc, str) else json.dumps(doc)
                    r = subprocess.run(["bash", "-c", f"source '{SCRIPT}'; python3 -c \"$HOOK_RUN_CHECK\" {job} {not_before} 2"], env=h.env(), input=payload,
                                       capture_output=True, text=True, check=False, timeout=60)
                    self.assertEqual(r.returncode, code, r.stdout + r.stderr)
                    self.assertIn(text, r.stdout)
                    self.assertEqual(r.stdout.count("verdict: "), 1, r.stdout)
        finally:
            h.close()

    def test_the_release_record_is_never_written_to_evidence_whole(self):
        r = self.step("bundled-bundled")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        text = r.evidence["provision-keycloak-hook-run"]
        self.assertEqual(text.splitlines()[-1], "verdict: ok")
        self.assertIn("hook ConfigMap/owl-mast-postgresql-provision-scripts events=pre-upgrade phase=Succeeded", text)
        self.assertNotIn("{", text)
        for whole in ('"manifest"', '"chart"', '"last_run"'):
            self.assertNotIn(whole, "\n".join(r.evidence.values()))

    def test_hook_gone_timeout_must_be_a_whole_number(self):
        for value in ("30s", "-1", "1.5", "abc", " ", "08", "030"):
            with self.subTest(value=value):
                r = self.step("bundled-bundled", HOOK_GONE_TIMEOUT=value)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn(f"REFUSED: HOOK_GONE_TIMEOUT must be a whole number of seconds (digits only, no leading zero), got '{value}'", r.stderr)
                self.assertEqual(r.calls, "")

    def test_the_step_timeouts_must_be_whole_numbers_without_a_leading_zero(self):
        """Review 5883535263: `08` passed `^[0-9]+$` and then aborted the step in bash's octal arithmetic."""
        for name in ("DURABLE_WORK_TIMEOUT", "TERMINATING_POD_TIMEOUT"):
            for value in ("08", "030", "-1", "1.5", " ", "2m", "1234567890", "99999999999999999999"):
                with self.subTest(name=name, value=value):
                    r = self.step("bundled-bundled", **{name: value})
                    self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                    self.assertIn(f"REFUSED: {name} must be a whole number of seconds (digits only, no leading zero, at most 9 digits), got '{value}'", r.stderr)
                    self.assertEqual(r.calls, "")

    def test_the_script_reads_no_hook_object_the_chart_deletes_on_success(self):
        """The delete policy the script depends on is the chart's, and no step reads the hook Job, its log or its ConfigMap directly."""
        hook = (CHART / "templates" / "postgresql-provision-keycloak-job.yaml").read_text()
        self.assertEqual(hook.count("helm.sh/hook-delete-policy: before-hook-creation,hook-succeeded"), 2)
        text = "\n".join(l for l in SCRIPT.read_text().splitlines() if not l.lstrip().startswith("#"))
        for pattern in (r"\bget job\b", r"\blogs\s+\"?job/", r"get configmap\b.*provision-scripts", r"hook-log", r"hook-job"):
            self.assertIsNone(re.search(pattern, text), pattern)


if __name__ == "__main__":
    unittest.main()
