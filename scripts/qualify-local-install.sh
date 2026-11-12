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
#        first-enable (needs OWLMAST_FOLLOWUP_RUN_ID; a fresh run-owned volume: app-only init, enable identity via the pre-upgrade hook, retry)
# Optional: BACKEND_IMAGE_TAG (default 0.1.0), BACKEND_IMAGE_ID (expected local image id the node must run).
# The synthetic fixtures speak plaintext (http issuer, sslMode=disable): every such install passes the chart's
# explicit opt-ins (identity.external.allowInsecureIssuer, *.allowInsecureTransport); production values never do.
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
# Ownership identity of the retained qualification resource set (namespaces, Secrets, fixtures, retained
# claims). Objects carry exactly this label; a later authorized run that reuses them keeps the label and
# records its own authorization in its evidence. The first-enable fixture (step first-enable) has its own
# explicit identity, FE_RUN_ID, and never touches resources of the retained set beyond reading them.
RUN_ID="${OWLMAST_RUN_ID:-om-01-02-local-20261107-01}"
RUN_LABEL_KEY="owlmast.aisquad.com/run"
RUN_LABEL="$RUN_LABEL_KEY=$RUN_ID"
FE_RUN_ID="${OWLMAST_FOLLOWUP_RUN_ID:-}"
FE_RELEASE="${FE_RELEASE:-owl-mast-fe}"
BACKEND_IMAGE_TAG="${BACKEND_IMAGE_TAG:-0.1.0}"
BACKEND_IMAGE_ID="${BACKEND_IMAGE_ID:-}"
KIND_NODE="${KIND_NODE:-owl-mast-om0102-control-plane}"
OUT="$EVIDENCE_DIR/runtime"
mkdir -p "$OUT/preflight"
export KUBECONFIG

# -- target identities are derived from the artifacts that are applied, never assumed --------------------
# The static manifests fix their namespaces, quota names and StorageClass; the chart fixes the fullname of
# every release resource. Overrides that would make preflight look at one object while a mutation touches
# another are rejected here, before any cluster effect (N2).
manifest_field() { python3 - "$@" <<'PY'
import sys, yaml
path, kind, field = sys.argv[1], sys.argv[2], sys.argv[3]
for doc in yaml.safe_load_all(open(path)):
    if doc and doc.get("kind") == kind:
        cur = doc
        for part in field.split("."):
            cur = cur[part]
        print(cur)
PY
}
chart_fullname() { # chart_fullname <release>: the fullname Helm renders for this release (from the backend Deployment name)
  h template "$1" "$CHART" -s templates/backend-deployment.yaml 2>/dev/null | sed -n 's/^  name: \(.*\)-backend$/\1/p' | head -1
}
assert_supported_targets() {
  local manifest_ns ext_manifest_ns sc quota_ns quota_ext rel fullname
  mapfile -t manifest_ns < <(manifest_field "$ROOT/deploy/local-kind/namespaces.yaml" Namespace metadata.name)
  [ "${manifest_ns[0]:-}" = "$NS" ] && [ "${manifest_ns[1]:-}" = "$EXT_NS" ] \
    || { echo "REFUSED: NS=$NS / EXT_NS=$EXT_NS differ from the namespaces the static manifests apply (${manifest_ns[*]}); namespace overrides are not supported" >&2; exit 2; }
  mapfile -t quota_ns < <(manifest_field "$ROOT/deploy/local-kind/namespaces.yaml" ResourceQuota metadata.namespace)
  [ "${quota_ns[0]:-}" = "$NS" ] && [ "${quota_ns[1]:-}" = "$EXT_NS" ] || { echo "REFUSED: quota manifests target other namespaces" >&2; exit 2; }
  ext_manifest_ns="$(manifest_field "$ROOT/deploy/local-kind/external-fixtures.yaml" Deployment metadata.namespace | sort -u)"
  [ "$ext_manifest_ns" = "$EXT_NS" ] || { echo "REFUSED: the fixture manifest targets namespace '$ext_manifest_ns', not EXT_NS=$EXT_NS" >&2; exit 2; }
  sc="$(manifest_field "$ROOT/deploy/local-kind/external-fixtures.yaml" PersistentVolumeClaim spec.storageClassName)"
  [ "$sc" = "$STORAGE_CLASS" ] || { echo "REFUSED: the fixture claim uses StorageClass '$sc', not $STORAGE_CLASS" >&2; exit 2; }
  [ "$(manifest_field "$ROOT/deploy/local-kind/storageclass.yaml" StorageClass metadata.name)" = "$STORAGE_CLASS" ] || { echo "REFUSED: storageclass manifest name differs from $STORAGE_CLASS" >&2; exit 2; }
  for rel in "$RELEASE" "$RELEASE-broken" "$RELEASE-wrongidp" ${FE_RELEASE:+"$FE_RELEASE"}; do
    fullname="$(chart_fullname "$rel")"
    [ "$fullname" = "$rel" ] || { echo "REFUSED: release '$rel' renders chart fullname '$fullname'; this script addresses release resources as <release>-<component>, so a release name whose fullname differs is not supported" >&2; exit 2; }
  done
}
STORAGE_CLASS="owl-mast-local-retain"

KUBECTL_BIN="${OWLMAST_KUBECTL:-kubectl}"
k() { "$KUBECTL_BIN" --context "$CONTEXT" "$@"; }
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
# optional_httproute_state: absent | served | error:<message>
# Absence of the one optional kind is established from TYPED discovery documents, never from error text,
# exit status alone or a lossy version listing:
#  1. GET /apis must return a well-formed APIGroupList (kind, apiVersion v1, groups). The API server builds
#     this legacy list from every registered APIService and every established CRD group, regardless of
#     availability, so a group that is Stale/unavailable in aggregated discovery is still listed here.
#     Only a listing that does not contain the group is positive, typed absence.
#  2. If the group is listed, GET /apis/<group>/<version> must return a well-formed APIResourceList for
#     exactly that groupVersion naming the `httproutes` resource of kind HTTPRoute: then the kind is served.
#     A failing or malformed version document (stale backend, 503, 403, wrong kind/version, resource missing)
#     is an error: the kind may exist but cannot be verified, so preflight refuses.
# Any non-zero status, stderr output or unparseable body at either step is an error (fail closed).
OPTIONAL_KIND_HTTPROUTE_GROUP="gateway.networking.k8s.io"
OPTIONAL_KIND_HTTPROUTE_VERSION="v1"
_typed_discovery() { # _typed_discovery <path> <python-check> : prints the check's verdict, or error:<message>
  local path="$1" check="$2" out err rc=0 verdict
  err="$(mktemp)"
  out="$(k get --raw "$path" 2>"$err")" || rc=$?
  if [ "$rc" -ne 0 ] || [ -s "$err" ]; then
    echo "error:GET $path failed (exit $rc): $(tr '\n' ' ' <"$err" | cut -c1-160)"; rm -f "$err"; return
  fi
  rm -f "$err"
  verdict="$(printf '%s' "$out" | python3 -c "$check" "$OPTIONAL_KIND_HTTPROUTE_GROUP" "$OPTIONAL_KIND_HTTPROUTE_VERSION" 2>&1)" || verdict="error:discovery document check failed: $(tr '\n' ' ' <<<"$verdict" | cut -c1-120)"
  echo "$verdict"
}
optional_httproute_state() {
  # Both documents are validated field by field against the metav1 contracts (APIGroupList/APIGroup/
  # GroupVersionForDiscovery and APIResourceList/APIResource: kind, apiVersion "v1", string identities,
  # coherent groupVersion = name/version). Any malformed or contradictory document is an error, never
  # absence and never served.
  local groups version
  groups="$(_typed_discovery /apis 'import json,sys
group=sys.argv[1]
def bad(msg):
    print("error:/apis APIGroupList malformed: "+msg); sys.exit(0)
def nonempty_str(v):
    return isinstance(v,str) and v.strip()!="" and v==v.strip()
try:
    doc=json.load(sys.stdin)
except Exception as exc:
    print("error:/apis is not JSON: "+str(exc)[:80]); sys.exit(0)
if not isinstance(doc,dict) or doc.get("kind")!="APIGroupList" or doc.get("apiVersion")!="v1" or not isinstance(doc.get("groups"),list):
    print("error:/apis did not return a typed APIGroupList v1 (got kind=%r apiVersion=%r)"%(doc.get("kind") if isinstance(doc,dict) else type(doc).__name__, doc.get("apiVersion") if isinstance(doc,dict) else None)); sys.exit(0)
names=[]
for i,g in enumerate(doc["groups"]):
    if not isinstance(g,dict): bad("groups[%d] is not an object"%i)
    name=g.get("name")
    if not nonempty_str(name): bad("groups[%d].name is not a non-empty string (%r)"%(i,name))
    versions=g.get("versions")
    if not isinstance(versions,list) or not versions: bad("groups[%d] (%s) has no versions list"%(i,name))
    for j,v in enumerate(versions):
        if not isinstance(v,dict) or not nonempty_str(v.get("groupVersion")) or not nonempty_str(v.get("version")): bad("groups[%d].versions[%d] of %s lacks string groupVersion/version"%(i,j,name))
        if v["groupVersion"]!=name+"/"+v["version"]: bad("groups[%d].versions[%d] groupVersion %r contradicts %s/%s"%(i,j,v["groupVersion"],name,v["version"]))
    pv=g.get("preferredVersion")
    if pv is not None and (not isinstance(pv,dict) or not nonempty_str(pv.get("groupVersion")) or not nonempty_str(pv.get("version")) or pv["groupVersion"]!=name+"/"+pv["version"]): bad("groups[%d] (%s) preferredVersion is incoherent"%(i,name))
    names.append(name)
if len(set(names))!=len(names): bad("duplicate group names")
print("listed" if group in names else "unlisted")')"
  case "$groups" in
    unlisted) echo absent; return ;;
    listed) ;;
    *) echo "$groups"; return ;;
  esac
  version="$(_typed_discovery "/apis/$OPTIONAL_KIND_HTTPROUTE_GROUP/$OPTIONAL_KIND_HTTPROUTE_VERSION" 'import json,sys
group,version=sys.argv[1],sys.argv[2]
def bad(msg):
    print("error:version document malformed: "+msg); sys.exit(0)
def nonempty_str(v):
    return isinstance(v,str) and v.strip()!="" and v==v.strip()
try:
    doc=json.load(sys.stdin)
except Exception as exc:
    print("error:version document is not JSON: "+str(exc)[:80]); sys.exit(0)
if not isinstance(doc,dict) or doc.get("kind")!="APIResourceList" or doc.get("apiVersion")!="v1" or doc.get("groupVersion")!=group+"/"+version or not isinstance(doc.get("resources"),list):
    print("error:version document is not the APIResourceList v1 of %s/%s (kind=%r apiVersion=%r groupVersion=%r)"%(group,version,doc.get("kind") if isinstance(doc,dict) else None, doc.get("apiVersion") if isinstance(doc,dict) else None, doc.get("groupVersion") if isinstance(doc,dict) else None)); sys.exit(0)
match=None
for i,r in enumerate(doc["resources"]):
    if not isinstance(r,dict): bad("resources[%d] is not an object"%i)
    if not nonempty_str(r.get("name")) or not nonempty_str(r.get("kind")): bad("resources[%d] lacks string name/kind"%i)
    if "namespaced" in r and not isinstance(r["namespaced"],bool): bad("resources[%d] (%s) namespaced is not boolean"%(i,r["name"]))
    if "verbs" in r and (not isinstance(r["verbs"],list) or not all(isinstance(x,str) for x in r["verbs"])): bad("resources[%d] (%s) verbs is not a string list"%(i,r["name"]))
    # APIResource.group/version are set only for resources served from another group/version (subresources);
    # for the resource under test they must agree with the document identity.
    if r["name"]=="httproutes":
        if r["kind"]!="HTTPRoute": bad("resource httproutes has kind %r, expected HTTPRoute"%r["kind"])
        if "group" in r and r["group"]!=group: bad("resource httproutes declares group %r under %s"%(r["group"],group))
        if "version" in r and r["version"]!=version: bad("resource httproutes declares version %r under %s"%(r["version"],version))
        if r.get("namespaced") is False: bad("resource httproutes is declared cluster-scoped; HTTPRoute is namespaced")
        if match is not None: bad("resource httproutes is listed twice")
        match=r
print("served" if match else "error:%s/%s is served but does not list the httproutes resource of kind HTTPRoute"%(group,version))')"
  echo "$version"
}
OPTIONAL_KIND_HTTPROUTE_RESOURCE="httproutes.v1.gateway.networking.k8s.io"
resource_state() {
  local ns="$1" kind="$2" name="$3" owner="${4:-$RUN_ID}" out err rc=0 served
  local resource="$kind"
  local -a nsarg=()
  [ "$ns" != "-" ] && nsarg=(-n "$ns")
  if [ "$kind" = httproute ]; then
    served="$(optional_httproute_state)"
    case "$served" in
      absent) echo kind-unavailable; return ;;
      served) resource="$OPTIONAL_KIND_HTTPROUTE_RESOURCE" ;;
      *) echo "$served"; return ;;
    esac
  fi
  # --ignore-not-found: an explicit API NotFound yields exit 0 with no output; every other failure keeps its
  # non-zero status (Forbidden, unreachable, unresolvable kind, partial discovery), so absence is never inferred
  # from error text. Diagnostics on stderr with exit 0 are also treated as a failed read.
  err="$(mktemp)"
  out="$(k "${nsarg[@]}" get "$resource" "$name" --ignore-not-found -o jsonpath='{.metadata.name}|{.metadata.labels.owlmast\.aisquad\.com/run}' 2>"$err")" || rc=$?
  if [ "$rc" -ne 0 ] || [ -s "$err" ]; then
    echo "error:$(tr '\n' ' ' <"$err" | cut -c1-200)"; rm -f "$err"; return
  fi
  rm -f "$err"
  if [ -z "$out" ]; then echo absent; return; fi
  case "$out" in
    "$name|$owner") echo owned ;;
    "$name|") echo "foreign:unlabelled" ;;
    "$name|"*) echo "foreign:${out#*|}" ;;
    *) echo "error:unexpected object projection '$(cut -c1-120 <<<"$out")'" ;;
  esac
}
release_state() { # release_state <release>: absent | present | error:<message>  (Helm's own record; resources are checked one by one)
  local rel="$1" out rc=0
  out="$(h status "$rel" -n "$NS" 2>&1)" || rc=$?
  if [ "$rc" -eq 0 ]; then echo present
  elif grep -qi 'release: not found' <<<"$out"; then echo absent
  else echo "error:$(tr '\n' ' ' <<<"$out" | cut -c1-200)"; fi
}
RELEASE_KINDS_AND_SUFFIXES=( "deployment:-backend" "deployment:-postgresql" "deployment:-keycloak" "deployment:-frontend"
  "service:-backend" "service:-postgresql" "service:-keycloak" "service:-frontend"
  "configmap:-postgresql-init" "configmap:-keycloak-realm" "configmap:-postgresql-provision-scripts"
  "job:-postgresql-provision-keycloak" "ingress:" "httproute:" "pvc:-postgresql-data"
  "networkpolicy:-postgresql" "networkpolicy:-keycloak" )
# Components whose pod template carries no commonLabels, so their pods and ReplicaSets have NO run label: the
# chart keeps commonLabels off the PostgreSQL pod template (a label edit must not recreate the database).
# Ownership of such a pod is proven through its Deployment alone (see verified_pods).
CHAIN_UNLABELLED_COMPONENTS="postgresql"
verified_pods() { # verified_pods <release> <component> <owner>: prints the names of the selected pods whose controller chain is proven
  # Each selected pod must have exactly one controller reference to a ReplicaSet that exists, is readable, has
  # that UID and is itself controlled (one controller reference, matching UID) by the expected Deployment
  # <release>-<component>, which must exist, be readable and carry the owner label. The pod and the ReplicaSet
  # must carry the owner label too, except for CHAIN_UNLABELLED_COMPONENTS: there the label is absent by design,
  # so an ABSENT label is accepted and the UID chain to the owned Deployment is the proof; a label naming anyone
  # else still refuses. Anything else refuses. This proves the chain at the moment of reading; a pod replaced
  # afterwards is not covered by this proof (no atomic guarantee is claimed).
  local rel="$1" comp="$2" owner="$3" out rc=0 line name label refs dep_uid dep_label rs_out rs_uid rs_label rs_refs unlabelled_ok=0
  case " $CHAIN_UNLABELLED_COMPONENTS " in *" $comp "*) unlabelled_ok=1 ;; esac
  local proven_file="$OUT/preflight/proven-pods-$rel-$comp.txt"; : >"$proven_file"  # the proven names, read by callers
  dep_uid="$(k -n "$NS" get deployment "$rel-$comp" -o jsonpath='{.metadata.uid}|{.metadata.labels.owlmast\.aisquad\.com/run}' 2>&1)" || rc=$?
  if [ "$rc" -ne 0 ]; then
    if grep -q '(NotFound)' <<<"$dep_uid"; then dep_uid="absent|"; else log "chain $rel/$comp: deployment unreadable ($(tr '\n' ' ' <<<"$dep_uid" | cut -c1-120)): refusing"; return 1; fi
  fi
  dep_label="${dep_uid#*|}"; dep_uid="${dep_uid%%|*}"
  rc=0
  out="$(k -n "$NS" get pods -l "app.kubernetes.io/instance=$rel,app.kubernetes.io/component=$comp" -o jsonpath='{range .items[*]}{.metadata.name}{"|"}{.metadata.labels.owlmast\.aisquad\.com/run}{"|"}{range .metadata.ownerReferences[*]}{.kind}/{.name}/{.uid}/{.controller}{" "}{end}{"\n"}{end}' 2>&1)" || rc=$?
  if [ "$rc" -ne 0 ]; then log "chain $rel/$comp: pod selection unreadable ($(tr '\n' ' ' <<<"$out" | cut -c1-120)): refusing"; return 1; fi
  local failed=0
  while IFS='|' read -r name label refs; do
    [ -n "$name" ] || continue
    printf 'pod %s/%s label=%s refs=%s\n' "$NS" "$name" "$label" "$refs" >>"$OUT/preflight/resources.txt"
    if [ "$label" != "$owner" ] && ! { [ "$unlabelled_ok" -eq 1 ] && [ -z "$label" ]; }; then log "chain pod $NS/$name: label '$label' is not $owner: refusing"; failed=1; continue; fi
    local controllers; controllers="$(tr ' ' '\n' <<<"$refs" | grep -E '/true$' || true)"
    if [ "$(grep -c . <<<"$controllers")" -ne 1 ] || [ -z "$controllers" ]; then log "chain pod $NS/$name: expected exactly one controller reference, got '$refs': refusing"; failed=1; continue; fi
    local ckind cname cuid; IFS='/' read -r ckind cname cuid _ <<<"$controllers"
    if [ "$ckind" != ReplicaSet ]; then log "chain pod $NS/$name: controller is $ckind, not a ReplicaSet: refusing"; failed=1; continue; fi
    rc=0; rs_out="$(k -n "$NS" get replicaset "$cname" -o jsonpath='{.metadata.uid}|{.metadata.labels.owlmast\.aisquad\.com/run}|{range .metadata.ownerReferences[*]}{.kind}/{.name}/{.uid}/{.controller}{" "}{end}' 2>&1)" || rc=$?
    if [ "$rc" -ne 0 ]; then
      if grep -q '(NotFound)' <<<"$rs_out"; then log "chain pod $NS/$name: controller ReplicaSet $cname is missing: refusing"; else log "chain pod $NS/$name: controller ReplicaSet $cname unreadable: refusing"; fi
      failed=1; continue
    fi
    IFS='|' read -r rs_uid rs_label rs_refs <<<"$rs_out"
    if [ "$rs_uid" != "$cuid" ]; then log "chain pod $NS/$name: ReplicaSet $cname UID $rs_uid differs from the pod's controller reference $cuid: refusing"; failed=1; continue; fi
    if [ "$rs_label" != "$owner" ] && ! { [ "$unlabelled_ok" -eq 1 ] && [ -z "$rs_label" ]; }; then log "chain pod $NS/$name: ReplicaSet $cname label '$rs_label' is not $owner: refusing"; failed=1; continue; fi
    local rs_controllers; rs_controllers="$(tr ' ' '\n' <<<"$rs_refs" | grep -E '/true$' || true)"
    if [ "$(grep -c . <<<"$rs_controllers")" -ne 1 ] || [ -z "$rs_controllers" ]; then log "chain pod $NS/$name: ReplicaSet $cname has no single controller: refusing"; failed=1; continue; fi
    local dkind dname duid; IFS='/' read -r dkind dname duid _ <<<"$rs_controllers"
    if [ "$dkind/$dname" != "Deployment/$rel-$comp" ] || [ "$duid" != "$dep_uid" ] || [ "$dep_label" != "$owner" ]; then
      log "chain pod $NS/$name: ReplicaSet $cname is controlled by $dkind/$dname ($duid), expected Deployment/$rel-$comp ($dep_uid) owned by $owner: refusing"; failed=1; continue
    fi
    if [ -z "$label" ] || [ -z "$rs_label" ]; then
      log "chain pod $NS/$name: proven ($name -> ReplicaSet/$cname $rs_uid -> Deployment/$rel-$comp $dep_uid, Deployment owned by $owner; the $comp pod template carries no run label)"
    else
      log "chain pod $NS/$name: proven ($name -> ReplicaSet/$cname $rs_uid -> Deployment/$rel-$comp $dep_uid, all $owner)"
    fi
    printf '%s\n' "$name" >>"$proven_file"
  done <<<"$out"
  [ "$failed" -eq 0 ]
}
preflight_pods() { # preflight_pods <release> <component> <owner>
  verified_pods "$1" "$2" "$3" || PREFLIGHT_FAILED=1
}
preflight_release() { # preflight_release <release> [owner]: Helm record plus every resource the chart can render, hooks included, plus selected pods
  local rel="$1" owner="${2:-$RUN_ID}" state entry kind suffix
  state="$(release_state "$rel")"
  printf 'release %s/%s %s\n' "$NS" "$rel" "$state" >>"$OUT/preflight/resources.txt"
  case "$state" in
    absent|present) log "preflight release $NS/$rel: $state (each of its resources is checked below)" ;;
    *) log "preflight release $NS/$rel: Helm record unreadable (${state#error:}): refusing"; PREFLIGHT_FAILED=1 ;;
  esac
  for entry in "${RELEASE_KINDS_AND_SUFFIXES[@]}"; do
    kind="${entry%%:*}"; suffix="${entry#*:}"
    preflight_resource "$NS" "$kind" "$rel$suffix" "$owner"
  done
  for kind in backend postgresql keycloak; do preflight_pods "$rel" "$kind" "$owner"; done
}
PREFLIGHT_FAILED=0
preflight_resource() { # preflight_resource <namespace|-> <kind> <name> [owner]
  local state; state="$(resource_state "$1" "$2" "$3" "${4:-$RUN_ID}")"
  printf '%s %s/%s %s\n' "$2" "$1" "$3" "$state" >>"$OUT/preflight/resources.txt"
  case "$state" in
    absent) log "preflight $2 $1/$3: absent" ;;
    kind-unavailable) log "preflight $2 $1/$3: the typed /apis APIGroupList has no group $OPTIONAL_KIND_HTTPROUTE_GROUP (no APIService or established CRD registers it): the optional HTTPRoute kind cannot exist here and routing.gateway stays disabled" ;;
    owned) log "preflight $2 $1/$3: owned by this run" ;;
    foreign:*) log "preflight $2 $1/$3: exists but owner is '${state#foreign:}', not ${4:-$RUN_ID}: no adoption, overwrite or deletion"; PREFLIGHT_FAILED=1 ;;
    *) log "preflight $2 $1/$3: ownership unreadable (${state#error:}): refusing rather than assuming absence"; PREFLIGHT_FAILED=1 ;;
  esac
}
preflight_secrets_of() { # the four synthetic Secrets of a namespace
  local ns="$1" s
  for s in owl-mast-postgres-admin owl-mast-db owl-mast-keycloak-db owl-mast-keycloak-bootstrap; do preflight_resource "$ns" secret "$s"; done
}
preflight_install_common() { # what every product install in $NS consumes
  preflight_resource - storageclass "$STORAGE_CLASS"
  preflight_resource - namespace "$NS"
}
preflight_fixture_endpoints() { # what every external combination consumes from the fixture namespace (read-only use)
  preflight_resource - namespace "$EXT_NS"
  preflight_resource "$EXT_NS" service external-postgresql; preflight_resource "$EXT_NS" deployment external-postgresql
  preflight_resource "$EXT_NS" service external-keycloak; preflight_resource "$EXT_NS" deployment external-keycloak
}
preflight() { # preflight <step...>: every resource the selected steps consume or change, before any mutation
  log "== preflight for: $*"
  : >"$OUT/preflight/resources.txt"
  local step
  for step in "$@"; do
    case "$step" in
      prepare)
        preflight_resource - storageclass "$STORAGE_CLASS"
        preflight_resource - namespace "$NS"; preflight_resource - namespace "$EXT_NS"
        preflight_resource "$NS" resourcequota owl-mast-test-budget; preflight_resource "$EXT_NS" resourcequota owl-mast-test-external-budget
        preflight_secrets_of "$NS"; preflight_secrets_of "$EXT_NS"
        preflight_resource "$NS" secret owl-mast-external-db; preflight_resource "$NS" secret owl-mast-external-keycloak-db ;;
      fixtures)
        preflight_resource - storageclass "$STORAGE_CLASS"  # consumed by the fixture claim
        preflight_resource - namespace "$EXT_NS"
        preflight_secrets_of "$EXT_NS"
        preflight_resource "$EXT_NS" configmap external-postgresql-init; preflight_resource "$EXT_NS" configmap external-keycloak-realm
        preflight_resource "$EXT_NS" pvc external-postgresql-data
        preflight_resource "$EXT_NS" service external-postgresql; preflight_resource "$EXT_NS" service external-keycloak
        preflight_resource "$EXT_NS" deployment external-postgresql; preflight_resource "$EXT_NS" deployment external-keycloak ;;
      bundled-bundled|persistence)
        preflight_install_common; preflight_secrets_of "$NS"; preflight_release "$RELEASE" ;;
      bundled-external)
        preflight_install_common; preflight_resource "$NS" secret owl-mast-postgres-admin; preflight_resource "$NS" secret owl-mast-db
        preflight_fixture_endpoints; preflight_release "$RELEASE" ;;
      external-bundled)
        preflight_install_common; preflight_resource "$NS" secret owl-mast-external-db; preflight_resource "$NS" secret owl-mast-external-keycloak-db
        preflight_resource "$NS" secret owl-mast-keycloak-bootstrap; preflight_fixture_endpoints; preflight_release "$RELEASE" ;;
      external-external)
        preflight_install_common; preflight_resource "$NS" secret owl-mast-external-db; preflight_fixture_endpoints; preflight_release "$RELEASE" ;;
      first-enable)
        [ -n "$FE_RUN_ID" ] || refuse "step first-enable needs OWLMAST_FOLLOWUP_RUN_ID, the explicit identity of its fixture"
        preflight_install_common; preflight_fixture_endpoints
        local s; for s in postgres-admin db keycloak-db keycloak-bootstrap; do preflight_resource "$NS" secret "$FE_RELEASE-$s" "$FE_RUN_ID"; done
        preflight_release "$FE_RELEASE" "$FE_RUN_ID" ;;
      failure-paths)
        preflight_install_common; preflight_fixture_endpoints
        preflight_resource "$NS" secret owl-mast-db-broken; preflight_resource "$NS" secret owl-mast-external-db
        preflight_release "$RELEASE-broken"; preflight_release "$RELEASE-wrongidp" ;;
      inventory) ;;
    esac
  done
  if [ "$PREFLIGHT_FAILED" -ne 0 ]; then refuse "preflight found resources this run does not own or cannot read; nothing was mutated (see $OUT/preflight/resources.txt)"; fi
  log "preflight passed: every existing resource is owned by its expected identity"
}

# -- secrets (values never leave the cluster or an in-memory pipe) ----------------------------------
create_labelled_secret() { # create_labelled_secret <namespace> <name> <owner> <kubectl create secret generic args...>
  # One API call creates the Secret WITH its ownership label: the object is built client-side (--dry-run=client,
  # nothing reaches the server), labelled in memory and created with `create`, which never overwrites. A separate
  # `label` call could fail or be interrupted after the create and leave an unlabelled Secret that every later
  # run refuses as foreign. A value the caller pipes in on stdin (--from-file=<key>=/dev/stdin) exists only in
  # pipes; a --from-literal value is a kubectl argument, visible in the process list while the command runs, so
  # it is for non-secret keys only.
  local ns="$1" name="$2" owner="$3" err; shift 3
  if ! err="$(k -n "$ns" create secret generic "$name" "$@" --dry-run=client -o json \
        | python3 -c 'import json,sys; s=json.load(sys.stdin); s["metadata"].setdefault("labels",{})[sys.argv[1]]=sys.argv[2]; print(json.dumps(s))' "$RUN_LABEL_KEY" "$owner" \
        | k -n "$ns" create -f - 2>&1 >/dev/null)"; then
    refuse "secret $ns/$name could not be created with its ownership label (nothing unlabelled was left behind): ${err%%$'\n'*}"
  fi
}
ensure_secret() { # ensure_secret <namespace> <name> <username> [owner]: random password, created only if absent and owned if present
  local ns="$1" name="$2" user="$3" owner="${4:-$RUN_ID}" state
  state="$(resource_state "$ns" secret "$name" "$owner")"
  case "$state" in
    owned) log "secret $ns/$name exists and is owned by this run (kept)"; return ;;
    absent) ;;
    *) refuse "secret $ns/$name: $state" ;;
  esac
  local password; password="$(openssl rand -base64 30 | tr -d '/+=' | cut -c1-32)"
  # The password goes in on stdin, written by a shell builtin: it is never an argument of any process. printf
  # adds no newline, so the Secret holds exactly the generated value.
  # (Process substitution, not a pipeline: the function must run in this shell so that its refusal stops the run.)
  create_labelled_secret "$ns" "$name" "$owner" --from-literal=username="$user" --from-file=password=/dev/stdin \
    < <(printf '%s' "$password")  # created with its explicit identity in one call
  log "secret $ns/$name created (synthetic, value not recorded)"
}
replicate_secret() { # replicate_secret <src-ns> <src-name> <dst-ns> <dst-name>: same values, owned source only, piped in memory only
  local src_ns="$1" src="$2" dst_ns="$3" dst="$4" state err
  state="$(resource_state "$src_ns" secret "$src")"
  [ "$state" = owned ] || refuse "secret $src_ns/$src cannot be replicated: $state"
  state="$(resource_state "$dst_ns" secret "$dst")"
  case "$state" in
    owned) log "secret $dst_ns/$dst exists and is owned by this run (kept)"; return ;;
    absent) ;;
    *) refuse "secret $dst_ns/$dst: $state" ;;
  esac
  # `create`, never `apply`: a Secret that appeared after the absence check above is not overwritten, the call
  # fails and the step refuses. The failure is reported (first line of the client's error, never the object).
  if ! err="$(k -n "$src_ns" get secret "$src" -o json \
        | python3 -c 'import json,sys; s=json.load(sys.stdin); print(json.dumps({"apiVersion":"v1","kind":"Secret","type":s["type"],"metadata":{"name":sys.argv[1],"namespace":sys.argv[2],"labels":{sys.argv[3]:sys.argv[4]}},"data":s["data"]}))' "$dst" "$dst_ns" "$RUN_LABEL_KEY" "$RUN_ID" \
        | k create -f - 2>&1 >/dev/null)"; then
    refuse "secret $dst_ns/$dst could not be replicated from $src_ns/$src (an existing Secret is never overwritten): ${err%%$'\n'*}"
  fi
  log "secret $dst_ns/$dst replicated from $src_ns/$src (synthetic, value not recorded)"
}
ensure_broken_secret() { # a Secret with the username key only (the failure path); created only if absent, labelled once
  local state; state="$(resource_state "$NS" secret owl-mast-db-broken)"
  case "$state" in
    owned) log "secret $NS/owl-mast-db-broken exists and is owned by this run (kept)"; return ;;
    absent) create_labelled_secret "$NS" owl-mast-db-broken "$RUN_ID" --from-literal=username=owlmast_app
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
  local name="$1" rows pods pod image_id node_id node_digests
  # Exactly one Running pod that is not terminating: after a rollout the old pod may still be listed first.
  rows="$(k -n "$NS" get pods -l "app.kubernetes.io/instance=$RELEASE,app.kubernetes.io/component=backend" --field-selector=status.phase=Running \
    -o custom-columns=NAME:.metadata.name,DELETING:.metadata.deletionTimestamp --no-headers)" \
    || { log "FAIL $name-image-identity: backend pod selection unreadable"; return 1; }
  pods="$(awk '$2 == "<none>" {print $1}' <<<"$rows")"
  if [ "$(grep -c . <<<"$pods")" -ne 1 ]; then
    log "FAIL $name-image-identity: expected exactly one Running, non-terminating backend pod, found '$(tr '\n' ' ' <<<"$pods")'"; return 1
  fi
  pod="$pods"
  record "$name-image" k -n "$NS" get pod "$pod" -o jsonpath='{.status.containerStatuses[0].image} {.status.containerStatuses[0].imageID}{"\n"}' || return 1
  image_id="$(k -n "$NS" get pod "$pod" -o jsonpath='{.status.containerStatuses[0].imageID}')" || { log "FAIL $name-image-identity: imageID unreadable"; return 1; }
  # An empty imageID would match any digest list; it is never evidence.
  [ -n "$image_id" ] || { log "FAIL $name-image-identity: pod $pod reports no imageID (container not started)"; return 1; }
  [ -n "$BACKEND_IMAGE_ID" ] || { log "note $name-image: BACKEND_IMAGE_ID not supplied; running image recorded, not compared"; return; }
  # The node's record for the tag: its image id (the config digest, identical to the local docker image id)
  # and the import digests containerd assigned when `kind load` imported this exact build.
  node_id="$(docker exec "$KIND_NODE" crictl inspecti -o go-template --template '{{.status.id}}' "docker.io/owl-mast/backend:$BACKEND_IMAGE_TAG" 2>/dev/null || true)"
  node_digests="$(docker exec "$KIND_NODE" crictl inspecti -o go-template --template '{{range .status.repoDigests}}{{.}} {{end}}' "docker.io/owl-mast/backend:$BACKEND_IMAGE_TAG" 2>/dev/null || true)"
  printf 'expected local image id: %s\nnode image id for tag %s: %s\nnode import digests: %s\npod imageID: %s\n' "$BACKEND_IMAGE_ID" "$BACKEND_IMAGE_TAG" "$node_id" "$node_digests" "$image_id" >>"$OUT/$name-image.txt"
  if [ "$node_id" = "$BACKEND_IMAGE_ID" ] && { [ "$image_id" = "$BACKEND_IMAGE_ID" ] || tr ' ' '\n' <<<"$node_digests" | grep -qxF -- "$image_id"; }; then
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
  # Every check returns explicitly: callers may invoke this under `||` (first-enable), which disables
  # `set -e` for the whole body, so a failed check must never fall through to the next one.
  local ns="$1" deploy="$2"
  record "ac3-$ns-app-not-superuser" pg_exec "$ns" "$deploy" OWLMAST_APP owlmast "select current_user, rolsuper, rolcreatedb, rolcreaterole from pg_roles where rolname = current_user" || return 1
  grep -q 'owlmast_app|f|f|f' "$OUT/ac3-$ns-app-not-superuser.txt" || { log "FAIL app principal privileges"; return 1; }
  record "ac3-$ns-keycloak-not-superuser" pg_exec "$ns" "$deploy" OWLMAST_KEYCLOAK keycloak "select current_user, rolsuper, rolcreatedb, rolcreaterole from pg_roles where rolname = current_user" || return 1
  grep -q 'keycloak_app|f|f|f' "$OUT/ac3-$ns-keycloak-not-superuser.txt" || { log "FAIL keycloak principal privileges"; return 1; }
  expect_connect_denied "ac3-$ns-app-cannot-connect-keycloak-db" "$ns" "$deploy" OWLMAST_APP keycloak owlmast || return 1
  expect_connect_denied "ac3-$ns-keycloak-cannot-connect-owlmast-db" "$ns" "$deploy" OWLMAST_KEYCLOAK owlmast keycloak || return 1
  record "ac3-$ns-extensions" pg_exec "$ns" "$deploy" OWLMAST_APP owlmast "select extname||'='||extversion from pg_extension where extname in ('vchord','vector') order by 1" || return 1
  grep -q 'vchord=1.1.1' "$OUT/ac3-$ns-extensions.txt" && grep -q 'vector=0.8.2' "$OUT/ac3-$ns-extensions.txt" || { log "FAIL extensions"; return 1; }
  record "ac3-$ns-keycloak-schema-present" pg_exec "$ns" "$deploy" OWLMAST_KEYCLOAK keycloak "select count(*) > 10 from information_schema.tables where table_schema='public'" || return 1
  grep -qx 't' "$OUT/ac3-$ns-keycloak-schema-present.txt" || { log "FAIL keycloak schema"; return 1; }
  record "ac3-$ns-flyway-history" pg_exec "$ns" "$deploy" OWLMAST_APP owlmast "select version||'|'||success from flyway_schema_history order by installed_rank" || return 1
  grep -q '^001|true$' "$OUT/ac3-$ns-flyway-history.txt" || { log "FAIL flyway history"; return 1; }
  # VectorChord index usage on synthetic data with the application principal (AC3); re-entry appends, never drops.
  record "ac3-$ns-vchord-index" pg_exec "$ns" "$deploy" OWLMAST_APP owlmast "create schema if not exists qualification; create table if not exists qualification.vectors(id int primary key, embedding vector(3)); insert into qualification.vectors select g, array[g, g*2, g*3]::vector from generate_series(1,200) g on conflict do nothing; create index if not exists vectors_vchordrq on qualification.vectors using vchordrq (embedding vector_l2_ops) with (options = E'residual_quantization = true\\n[build.internal]\\nlists = []'); analyze qualification.vectors; set enable_seqscan = off; explain (costs off) select id from qualification.vectors order by embedding <-> '[3,6,9]' limit 3; select id from qualification.vectors order by embedding <-> '[3,6,9]' limit 3; select indexdef from pg_indexes where schemaname='qualification' and indexname='vectors_vchordrq'" || return 1
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
  # Replace the PostgreSQL pod: the pods are re-proven through their controller chain immediately before
  # deletion and deleted by name; the selector is only how they are found.
  verified_pods "$RELEASE" postgresql "$RUN_ID" || { log "FAIL pod controller chain not proven; nothing deleted"; return 1; }
  local proven_pods; proven_pods="$(cat "$OUT/preflight/proven-pods-$RELEASE-postgresql.txt")"
  [ -n "$proven_pods" ] || { log "FAIL no PostgreSQL pod selected for replacement"; return 1; }
  printf '%s\n' "$proven_pods" >"$OUT/t3-delete-pod-proven.txt"
  # shellcheck disable=SC2086
  record t3-delete-pod k delete pod -n "$NS" $proven_pods --wait=true
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
    --set identity.external.allowInsecureIssuer=true --set identity.external.issuerUri="http://external-keycloak.$EXT_NS.svc:8080/realms/owl-mast" \
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
    --set database.external.host="external-postgresql.$EXT_NS.svc" --set database.external.sslMode=disable --set database.external.allowInsecureTransport=true \
    --set identity.keycloak.database.existingSecret=owl-mast-external-keycloak-db \
    --set identity.keycloak.database.external.host="external-postgresql.$EXT_NS.svc" --set identity.keycloak.database.external.sslMode=disable --set identity.keycloak.database.external.allowInsecureTransport=true
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
    --set database.external.host="external-postgresql.$EXT_NS.svc" --set database.external.sslMode=disable --set database.external.allowInsecureTransport=true \
    --set identity.bundled=false --set identity.external.allowInsecureIssuer=true --set identity.external.issuerUri="http://external-keycloak.$EXT_NS.svc:8080/realms/owl-mast"
  record external-external-only-backend k get deploy,pvc,svc -n "$NS" -o name
  record external-external-uninstall h uninstall "$RELEASE" -n "$NS" --wait
}

step_first_enable() {
  # F1/F2 on the real target: a fresh run-owned volume is initialised with the identity bundle disabled
  # and no Keycloak credentials, then the identity bundle is enabled with the pre-upgrade provisioning
  # hook under `helm upgrade --wait`, then the transition is retried as a no-op. Explicit fixture identity
  # $FE_RUN_ID; the retained qualification set is only read (external issuer fixture).
  log "== first-enable transition on a fresh volume (release $FE_RELEASE, identity $FE_RUN_ID)"
  local s
  ensure_secret "$NS" "$FE_RELEASE-postgres-admin" owlmast_admin "$FE_RUN_ID"
  ensure_secret "$NS" "$FE_RELEASE-db" owlmast_app "$FE_RUN_ID"
  ensure_secret "$NS" "$FE_RELEASE-keycloak-db" keycloak_app "$FE_RUN_ID"
  ensure_secret "$NS" "$FE_RELEASE-keycloak-bootstrap" temp-admin "$FE_RUN_ID"
  local -a common=(--set backend.image.tag="$BACKEND_IMAGE_TAG" --set backend.image.pullPolicy=Never
    --set commonLabels."owlmast\.aisquad\.com/run"="$FE_RUN_ID" --set postgresql.persistence.storageClass=owl-mast-local-retain
    --set postgresql.adminExistingSecret="$FE_RELEASE-postgres-admin" --set database.existingSecret="$FE_RELEASE-db"
    --set identity.keycloak.database.existingSecret="$FE_RELEASE-keycloak-db" --set identity.keycloak.bootstrapExistingSecret="$FE_RELEASE-keycloak-bootstrap")
  record fe1-install-external-identity h upgrade --install "$FE_RELEASE" "$CHART" -n "$NS" --wait --timeout 10m "${common[@]}" \
    --set identity.bundled=false --set identity.external.allowInsecureIssuer=true --set identity.external.issuerUri="http://external-keycloak.$EXT_NS.svc:8080/realms/owl-mast"
  record fe1-postgresql-pod k -n "$NS" get pods -l "app.kubernetes.io/instance=$FE_RELEASE,app.kubernetes.io/component=postgresql" -o custom-columns=NAME:.metadata.name,READY:.status.containerStatuses[0].ready,RESTARTS:.status.containerStatuses[0].restartCount
  grep -qE '^\S+ +true +0$' "$OUT/fe1-postgresql-pod.txt" || { log "FAIL fresh PostgreSQL did not initialise on its first start without restarts"; return 1; }
  record fe1-postgresql-init-log k -n "$NS" logs "deploy/$FE_RELEASE-postgresql"
  grep -q 'identity bundle disabled; no Keycloak database or principal provisioned' "$OUT/fe1-postgresql-init-log.txt" && grep -q 'PostgreSQL init process complete' "$OUT/fe1-postgresql-init-log.txt" \
    && ! grep -qE 'provision-keycloak.sh|parameter null or not set' "$OUT/fe1-postgresql-init-log.txt" \
    && log "ok   fe1-fresh-init-without-keycloak (complete first initialisation, helper never auto-executed)" || { log "FAIL fresh app-only initialisation evidence"; return 1; }
  record fe1-no-keycloak-role k -n "$NS" exec "deploy/$FE_RELEASE-postgresql" -- sh -c 'psql -U "$POSTGRES_USER" -h 127.0.0.1 -d postgres -Atc "select count(*) from pg_roles where rolname='"'"'keycloak_app'"'"'; select count(*) from pg_database where datname='"'"'keycloak'"'"'"'
  [ "$(grep -cx 0 "$OUT/fe1-no-keycloak-role.txt")" -eq 2 ] || { log "FAIL app-only volume already has Keycloak objects"; return 1; }
  record fe1-backend-readiness proxy_get "$NS" "$FE_RELEASE-backend:http" /actuator/health/readiness
  grep -q '"status":"UP"' "$OUT/fe1-backend-readiness.txt" || { log "FAIL backend not UP on external identity"; return 1; }
  local fe_pvc_uid; fe_pvc_uid="$(k get pvc "$FE_RELEASE-postgresql-data" -n "$NS" -o jsonpath='{.metadata.uid}')"
  record fe1-app-marker k -n "$NS" exec "deploy/$FE_RELEASE-postgresql" -- sh -c 'PGPASSWORD="$OWLMAST_APP_PASSWORD" psql -v ON_ERROR_STOP=1 -U "$OWLMAST_APP_USERNAME" -h 127.0.0.1 -d owlmast -Atc "create table if not exists qualification_marker(v text primary key); insert into qualification_marker values ('"'"'before-enable'"'"') on conflict do nothing; select v from qualification_marker"'
  grep -q before-enable "$OUT/fe1-app-marker.txt" || { log "FAIL marker"; return 1; }
  log "== enable the identity bundle with the pre-upgrade provisioning hook (helm upgrade --wait)"
  record fe2-enable-upgrade h upgrade "$FE_RELEASE" "$CHART" -n "$NS" --wait --timeout 10m "${common[@]}" \
    --set identity.bundled=true --set postgresql.provisionKeycloakDatabase=true
  record fe2-hook-job k -n "$NS" get job "$FE_RELEASE-postgresql-provision-keycloak" -o jsonpath='{.status.succeeded} {.status.failed}{"\n"}'
  grep -q '^1 ' "$OUT/fe2-hook-job.txt" || { log "FAIL provisioning hook did not succeed exactly once"; return 1; }
  record fe2-hook-log k -n "$NS" logs "job/$FE_RELEASE-postgresql-provision-keycloak"
  grep -q 'CREATE ROLE' "$OUT/fe2-hook-log.txt" && grep -q 'CREATE DATABASE' "$OUT/fe2-hook-log.txt" && grep -q 'GRANT' "$OUT/fe2-hook-log.txt" \
    && log "ok   fe2-first-enable-provisioned (role and database created by the pre-upgrade hook)" || { log "FAIL first-enable hook log"; return 1; }
  record fe2-keycloak-ready proxy_get "$NS" "$FE_RELEASE-keycloak:management" /health/ready
  record fe2-keycloak-discovery proxy_get "$NS" "$FE_RELEASE-keycloak:http" /realms/owl-mast/.well-known/openid-configuration
  grep -q "\"issuer\":\"http://$FE_RELEASE-keycloak:8080/realms/owl-mast\"" "$OUT/fe2-keycloak-discovery.txt" || { log "FAIL bundled issuer after enable"; return 1; }
  record fe2-backend-readiness proxy_get "$NS" "$FE_RELEASE-backend:http" /actuator/health/readiness
  grep -q '"status":"UP"' "$OUT/fe2-backend-readiness.txt" || { log "FAIL backend not UP on the bundled issuer"; return 1; }
  record fe2-backend-issuer-env k get deploy "$FE_RELEASE-backend" -n "$NS" -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="OWLMAST_IDENTITY_ISSUER_URI")].value}'
  record fe2-pvc-same-uid k get pvc "$FE_RELEASE-postgresql-data" -n "$NS" -o jsonpath='{.metadata.uid} {.status.phase}'
  grep -q "$fe_pvc_uid Bound" "$OUT/fe2-pvc-same-uid.txt" || { log "FAIL volume changed across enable"; return 1; }
  record fe2-app-marker k -n "$NS" exec "deploy/$FE_RELEASE-postgresql" -- sh -c 'PGPASSWORD="$OWLMAST_APP_PASSWORD" psql -v ON_ERROR_STOP=1 -U "$OWLMAST_APP_USERNAME" -h 127.0.0.1 -d owlmast -Atc "select v from qualification_marker"'
  grep -q before-enable "$OUT/fe2-app-marker.txt" && log "ok   fe2-app-data-preserved" || { log "FAIL app data after enable"; return 1; }
  local saved_release="$RELEASE"; RELEASE="$FE_RELEASE"
  check_shared_postgres "$NS" "$FE_RELEASE-postgresql" || { RELEASE="$saved_release"; return 1; }
  RELEASE="$saved_release"
  log "== retry the same transition: idempotent no-op"
  record fe3-retry-upgrade h upgrade "$FE_RELEASE" "$CHART" -n "$NS" --wait --timeout 10m "${common[@]}" \
    --set identity.bundled=true --set postgresql.provisionKeycloakDatabase=true
  record fe3-hook-log k -n "$NS" logs "job/$FE_RELEASE-postgresql-provision-keycloak"
  grep -q 'GRANT' "$OUT/fe3-hook-log.txt" && ! grep -qE 'CREATE ROLE|CREATE DATABASE' "$OUT/fe3-hook-log.txt" \
    && log "ok   fe3-retry-no-op (grants re-applied, nothing recreated)" || { log "FAIL retry was not a no-op"; return 1; }
  record fe3-app-marker k -n "$NS" exec "deploy/$FE_RELEASE-postgresql" -- sh -c 'PGPASSWORD="$OWLMAST_APP_PASSWORD" psql -v ON_ERROR_STOP=1 -U "$OWLMAST_APP_USERNAME" -h 127.0.0.1 -d owlmast -Atc "select v from qualification_marker"'
  grep -q before-enable "$OUT/fe3-app-marker.txt" || { log "FAIL app data after retry"; return 1; }
  record fe3-keycloak-schema k -n "$NS" exec "deploy/$FE_RELEASE-postgresql" -- sh -c 'PGPASSWORD="$OWLMAST_KEYCLOAK_PASSWORD" psql -U "$OWLMAST_KEYCLOAK_USERNAME" -h 127.0.0.1 -d keycloak -Atc "select count(*) > 10 from information_schema.tables where table_schema='"'"'public'"'"'"'
  grep -qx t "$OUT/fe3-keycloak-schema.txt" || { log "FAIL keycloak schema after retry"; return 1; }
  record fe4-uninstall h uninstall "$FE_RELEASE" -n "$NS" --wait
  record fe4-retained-claim k get pvc "$FE_RELEASE-postgresql-data" -n "$NS" -o jsonpath='{.metadata.uid} {.status.phase} {.metadata.labels.owlmast\.aisquad\.com/run}{"\n"}'
  grep -q "$fe_pvc_uid Bound $FE_RUN_ID" "$OUT/fe4-retained-claim.txt" && log "ok   fe4-fixture-claim-retained (owned by $FE_RUN_ID, not deleted)" || { log "FAIL fixture claim"; return 1; }
}

step_failure_paths() {
  log "== failure paths: missing secret key, wrong issuer"
  ensure_broken_secret
  if h upgrade --install "$RELEASE-broken" "$CHART" -n "$NS" --wait --timeout 90s \
      --set backend.image.tag="$BACKEND_IMAGE_TAG" --set backend.image.pullPolicy=Never --set commonLabels."owlmast\.aisquad\.com/run"="$RUN_ID" \
      --set database.bundled=false --set database.external.host="external-postgresql.$EXT_NS.svc" --set database.external.sslMode=disable --set database.external.allowInsecureTransport=true \
      --set database.existingSecret=owl-mast-db-broken \
      --set identity.bundled=false --set identity.external.allowInsecureIssuer=true --set identity.external.issuerUri="http://external-keycloak.$EXT_NS.svc:8080/realms/owl-mast" \
      >"$OUT/fail-missing-secret-key-install.txt" 2>&1; then
    log "FAIL install succeeded with a Secret missing the password key"; return 1
  fi
  record fail-missing-secret-key-pods k get pods -n "$NS" -l app.kubernetes.io/instance="$RELEASE-broken" -o custom-columns=NAME:.metadata.name,STATUS:.status.containerStatuses[0].state.waiting.reason
  grep -q CreateContainerConfigError "$OUT/fail-missing-secret-key-pods.txt" && log "ok   fail-missing-secret-key (CreateContainerConfigError, nothing started)" || { log "FAIL unexpected pod state"; return 1; }
  record fail-missing-secret-key-uninstall h uninstall "$RELEASE-broken" -n "$NS" --wait
  if h upgrade --install "$RELEASE-wrongidp" "$CHART" -n "$NS" --wait --timeout 150s \
      --set backend.image.tag="$BACKEND_IMAGE_TAG" --set backend.image.pullPolicy=Never --set commonLabels."owlmast\.aisquad\.com/run"="$RUN_ID" \
      --set database.bundled=false --set database.existingSecret=owl-mast-external-db --set database.external.host="external-postgresql.$EXT_NS.svc" --set database.external.sslMode=disable --set database.external.allowInsecureTransport=true \
      --set identity.bundled=false --set identity.external.allowInsecureIssuer=true --set identity.external.issuerUri="http://external-keycloak.$EXT_NS.svc:8080/realms/does-not-exist" \
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
  record inventory-all k get all,pvc,pv,secrets,configmap,resourcequota -A -l "$RUN_LABEL_KEY" -o custom-columns=KIND:.kind,NS:.metadata.namespace,NAME:.metadata.name,OWNER:.metadata.labels.owlmast\.aisquad\.com/run,CREATED:.metadata.creationTimestamp
  # The PostgreSQL pods and ReplicaSets carry no run label (CHAIN_UNLABELLED_COMPONENTS), so the label query above
  # cannot list them: they are listed by component with their controller references, which lead to the labelled Deployment.
  record inventory-unlabelled-pods k get pods,replicasets -n "$NS" -l app.kubernetes.io/component=postgresql -o custom-columns=KIND:.kind,NS:.metadata.namespace,NAME:.metadata.name,INSTANCE:.metadata.labels.app\.kubernetes\.io/instance,CONTROLLER:.metadata.ownerReferences[0].kind,CONTROLLER-NAME:.metadata.ownerReferences[0].name,CREATED:.metadata.creationTimestamp
  record inventory-pv k get pv -o custom-columns=NAME:.metadata.name,CLAIM:.spec.claimRef.name,NS:.spec.claimRef.namespace,RECLAIM:.spec.persistentVolumeReclaimPolicy,CLASS:.spec.storageClassName,PHASE:.status.phase
  record inventory-helm h list -A
}

ALL_STEPS=(prepare fixtures bundled-bundled persistence bundled-external external-bundled external-external failure-paths inventory)
# first-enable is run explicitly (it needs OWLMAST_FOLLOWUP_RUN_ID) and is not part of `all`.
main() {
  local steps=("$@") step
  [ ${#steps[@]} -eq 0 ] && steps=(all)
  local expanded=()
  for step in "${steps[@]}"; do
    case "$step" in
      all) expanded+=("${ALL_STEPS[@]}") ;;
      prepare|fixtures|bundled-bundled|persistence|bundled-external|external-bundled|external-external|first-enable|failure-paths|inventory) expanded+=("$step") ;;
      *) echo "unknown step $step"; exit 2 ;;
    esac
  done
  assert_supported_targets
  preflight "${expanded[@]}"
  for step in "${expanded[@]}"; do "step_${step//-/_}"; done
  log "qualification steps complete: ${expanded[*]}"
}
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then main "$@"; fi
