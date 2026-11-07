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
if [[ "$args" == *" get "* && "$args" == *"jsonpath={.metadata.labels.owlmast"* ]]; then
  for ((i=0;i<${#argv[@]};i++)); do if [ "${argv[$i]}" = "get" ]; then kind="${argv[$((i+1))]}"; name="${argv[$((i+2))]}"; fi; done
  state="$(state_of "$kind" "$ns" "$name")"
  case "$state" in
    owned) printf '%s' "$STUB_RUN_ID" ;;
    foreign:unlabelled) printf '' ;;
    foreign:*) printf '%s' "${state#foreign:}" ;;
    absent) echo "Error from server (NotFound): $kind \"$name\" not found" >&2; exit 1 ;;
    *) echo "Unable to connect to the server: dial tcp 10.0.0.1:6443: connect: connection refused" >&2; exit 1 ;;
  esac
  exit 0
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

    def test_existing_release_without_this_runs_backend_refuses(self):
        r = self.run_refused(BASE_WORLD + "release - owl-mast owned\n", "bundled-bundled")  # release exists, deployment absent/unlabelled
        self.assertIn("release exists without this run's backend deployment", r.stdout)
        self.run_refused(BASE_WORLD + "release - owl-mast owned\ndeployment owl-mast-test owl-mast-backend foreign:unlabelled\n", "persistence")
        self.run_refused(BASE_WORLD + "release - owl-mast-wrongidp error\n", "failure-paths")

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
