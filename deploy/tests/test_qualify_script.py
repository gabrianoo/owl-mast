"""Stub-harness tests for scripts/qualify-local-install.sh (OM-01.02 review R3/R4/R5).

`kubectl` and `helm` are replaced by stubs on PATH that answer from a declared "world" of resource
ownership states and record every invocation. No cluster is touched. The tests prove that a foreign,
unlabelled or unreadable resource refuses the whole invocation before any mutating call, that direct
step entry is preflighted too, that a sentinel Secret value never reaches evidence or output on
success, failure or interruption, and that the isolation and readiness evaluators accept only the
intended PostgreSQL denial / backend 503 and reject transport, authentication and generic failures.
"""

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
      aggregated) printf '{"kind":"APIGroupDiscoveryList","apiVersion":"apidiscovery.k8s.io/v2","items":[]}'; exit 0 ;;
      *) printf '%s%s]}' "$groups" "$gw"; exit 0 ;;   # current, stale, noresource, wronggv list the group
    esac
  fi
  case "$state" in
    stale) echo 'Error from server (ServiceUnavailable): the server is currently unable to handle the request' >&2; exit 1 ;;
    noresource) printf '{"kind":"APIResourceList","apiVersion":"v1","groupVersion":"gateway.networking.k8s.io/v1","resources":[{"name":"gateways","kind":"Gateway","namespaced":true}]}'; exit 0 ;;
    wronggv) printf '{"kind":"APIResourceList","apiVersion":"v1","groupVersion":"gateway.networking.k8s.io/v1beta1","resources":[{"name":"httproutes","kind":"HTTPRoute","namespaced":true}]}'; exit 0 ;;
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
if [[ "$args" == *" get pods -l "* && "$args" == *"ownerReferences"* ]]; then
  sel="$(sed -E 's/.* -l ([^ ]+).*/\1/' <<<"$args")"; rel="${sel#app.kubernetes.io/instance=}"; rel="${rel%%,*}"; comp="${sel##*component=}"
  state="$(state_of pods "$ns" "$rel-$comp")"; pod="$rel-$comp-abc12-xyz"; rs="$rel-$comp-abc12"; uid="rs-$rel-$comp"
  case "$state" in
    absent) exit 0 ;;
    owned|foreign:rs-foreign|foreign:rs-missing|foreign:rs-unreadable|foreign:deploy) printf '%s|%s|ReplicaSet/%s/%s/true \n' "$pod" "$STUB_RUN_ID" "$rs" "$uid"; exit 0 ;;
    foreign:owner) printf '%s|%s|ReplicaSet/other-%s-abc12/rs-other/true \n' "$pod" "$STUB_RUN_ID" "$comp"; exit 0 ;;
    foreign:uid) printf '%s|%s|ReplicaSet/%s/stale-uid/true \n' "$pod" "$STUB_RUN_ID" "$rs"; exit 0 ;;
    foreign:ambiguous) printf '%s|%s|ReplicaSet/%s/%s/true ReplicaSet/%s-old/rs-old/true \n' "$pod" "$STUB_RUN_ID" "$rs" "$uid" "$rs"; exit 0 ;;
    foreign:no-controller) printf '%s|%s|ReplicaSet/%s/%s/false \n' "$pod" "$STUB_RUN_ID" "$rs" "$uid"; exit 0 ;;
    foreign:unlabelled) printf '%s||ReplicaSet/%s/%s/true \n' "$pod" "$rs" "$uid"; exit 0 ;;
    foreign:*) printf '%s|%s|ReplicaSet/%s/%s/true \n' "$pod" "${state#foreign:}" "$rs" "$uid"; exit 0 ;;
    *) echo "Unable to connect to the server: dial tcp 10.0.0.1:6443: connect: connection refused" >&2; exit 1 ;;
  esac
fi
if [[ "$args" == *" get replicaset "* ]]; then
  rs="$(sed -E 's/.* get replicaset ([^ ]+).*/\1/' <<<"$args")"; base="${rs%-abc12}"; base="${base%-old}"
  if [[ "$rs" == other-* ]]; then printf 'rs-other|%s|Deployment/other-%s/dep-other/true \n' "$STUB_RUN_ID" "${base#other-}"; exit 0; fi
  state="$(state_of pods "$ns" "$base")"
  case "$state" in
    foreign:rs-missing) echo "Error from server (NotFound): replicasets.apps \"$rs\" not found" >&2; exit 1 ;;
    foreign:rs-unreadable) echo "Error from server (Forbidden): replicasets.apps \"$rs\" is forbidden" >&2; exit 1 ;;
    foreign:rs-foreign) printf 'rs-%s|someone-else|Deployment/%s/dep-%s/true \n' "$base" "$base" "$base"; exit 0 ;;
    foreign:deploy) printf 'rs-%s|%s|Deployment/%s-other/dep-%s-other/true \n' "$base" "$STUB_RUN_ID" "$base" "$base"; exit 0 ;;
    *) printf 'rs-%s|%s|Deployment/%s/dep-%s/true \n' "$base" "$STUB_RUN_ID" "$base" "$base"; exit 0 ;;
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
if [[ "$args" == *" get secret"* ]]; then
  if [[ "$args" == *"-o json"* || "$args" == *"-o yaml"* || ( "$args" == *".data"* && "$args" != *'$k, $v := .data}}{{$k}}'* ) ]]; then
    printf '{"apiVersion":"v1","kind":"Secret","type":"Opaque","metadata":{"name":"x","namespace":"%s"},"data":{"username":"dXNlcg==","password":"%s"}}\n' "$ns" "$STUB_SENTINEL"
  else
    printf 'owl-mast-test/owl-mast-db type=Opaque keys=[password username ] owner=%s\n' "$STUB_RUN_ID"
  fi
  exit 0
fi
if [[ "$args" == *" exec "* ]]; then
  db="$(sed -E "s/.* -d '([^']+)'.*/\1/" <<<"$args")"
  case "${STUB_EXEC_MODE:-denied}" in
    denied) if [ "$db" = "${STUB_DENIED_DB:-keycloak}" ]; then printf 'psql: error: connection to server at "127.0.0.1", port 5432 failed: FATAL:  permission denied for database "%s"\nDETAIL:  User does not have CONNECT privilege.\ncommand terminated with exit code 2\n' "$db"; exit 2; fi; printf '%s\n' "$db"; exit 0 ;;
    refused) echo "Unable to connect to the server: dial tcp 10.0.0.1:6443: connect: connection refused"; exit 1 ;;
    authfail) printf 'psql: error: connection to server at "127.0.0.1", port 5432 failed: FATAL:  password authentication failed for user "owlmast_app"\ncommand terminated with exit code 2\n'; exit 2 ;;
    podgone) echo 'Error from server (NotFound): pods "owl-mast-postgresql-abc" not found'; exit 1 ;;
    connected) printf '%s\n' "$db"; exit 0 ;;
    denied-control-broken) if [ "$db" = "keycloak" ]; then printf 'FATAL:  permission denied for database "keycloak"\nDETAIL:  User does not have CONNECT privilege.\n'; exit 2; fi; echo "Unable to connect to the server"; exit 1 ;;
  esac
fi
if [[ "$args" == *" create secret generic "* ]]; then  # the stub world learns what the script created, labelled by the following label call
  name="$(sed -E 's/.* create secret generic ([^ ]+).*/\1/' <<<"$args")"; printf 'secret %s %s owned\n' "$ns" "$name" >> "$STUB_WORLD"; echo "secret/$name created"; exit 0
fi
if [[ "$args" == *" apply -f -"* ]]; then  # a replicated Secret arrives on stdin; it is consumed, never stored
  dst="$(python3 -c 'import json,sys; o=json.load(sys.stdin); print(o["metadata"]["namespace"], o["metadata"]["name"])' 2>/dev/null || echo "- -")"
  printf 'secret %s owned\n' "$dst" >> "$STUB_WORLD"; echo "stub: applied"; exit 0
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
if [[ "$args" == *" status "* ]]; then
  rel="$(sed -E 's/.* status ([^ ]+).*/\1/' <<<"$args")"
  state="$(awk -v m="$rel" '$1=="release" && $3==m {print $4; found=1} END {if (!found) print "absent"}' "$STUB_WORLD")"
  case "$state" in
    absent) echo "Error: release: not found" >&2; exit 1 ;;
    error) echo "Error: Kubernetes cluster unreachable" >&2; exit 1 ;;
    *) echo "STATUS: deployed"; exit 0 ;;
  esac
fi
echo "stub helm ok"
'''


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
               "BACKEND_IMAGE_TAG": "stub"}
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


BASE_WORLD = f"namespace - owl-mast-test owned\nnamespace - owl-mast-test-external owned\n"


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
        h = Harness(BASE_WORLD + f"secret owl-mast-test owl-mast-db owned\nsecret owl-mast-test-external owl-mast-db owned\n")
        try:
            r = h.run("prepare")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            calls = h.calls.read_text().splitlines()
            created = [c for c in calls if " create secret generic " in c]
            labelled = [c for c in calls if " label secret " in c]
            self.assertEqual(len(created), 6)  # eight synthetic Secrets minus the two that already exist and are owned
            self.assertEqual(len(labelled), 6)
            self.assertTrue(all("--overwrite" not in c for c in labelled))
            self.assertTrue(all(any(name in c for c in created) for name in [c.split(" label secret ")[1].split()[0] for c in labelled]), "only newly created Secrets are labelled")
            self.assertEqual(sum(" apply -f -" in c for c in calls), 2)  # the two replications, piped
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
            "foreign:unlabelled": "label '' is not",                                # pod unlabelled
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
            ("noresource", "does not list the httproutes resource"), ("wronggv", "is not the APIResourceList of gateway.networking.k8s.io/v1"),
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
                                 ("configmap", "-postgresql-init"), ("configmap", "-keycloak-realm"), ("configmap", "-postgresql-provision-scripts"), ("job", "-postgresql-provision-keycloak"), ("ingress", ""), ("httproute", ""), ("pvc", "-postgresql-data")):
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
            r = h.run("prepare", STUB_FAIL_ON=" apply -f -")
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


if __name__ == "__main__":
    unittest.main()
