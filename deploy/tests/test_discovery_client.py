"""Real-client discovery regression for the optional HTTPRoute kind (review N4).

A finite loopback HTTP server in this process impersonates the Kubernetes API discovery endpoints. The real
`kubectl` (the qualified binary named by OWLMAST_KUBECTL, else `kubectl` on PATH; both required, never skipped)
is driven against it with `--kubeconfig=/dev/null`, an explicit `--server`, a private `--cache-dir` and no
credentials. The committed qualification script runs its normal entry path (`bundled-bundled`) through the
stub harness, whose fake kubectl forwards exactly the two typed discovery reads to the real client; every other
cluster call stays stubbed and recorded. The scenarios reproduce the reviewer's finding: aggregated discovery
that marks gateway.networking.k8s.io/v1 Stale while the group is still registered must refuse before any
effect; genuine absence (no group registered) passes the optional check; a current group proceeds to the
ownership gate of the object. Permission, outage, malformed and wrong-kind responses refuse. The server is
shut down after each scenario; nothing contacts a cluster.
"""

import http.server
import json
import os
import shutil
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

from deploy.tests.test_qualify_script import BASE_WORLD, Harness

KUBECTL = os.environ.get("OWLMAST_KUBECTL") or shutil.which("kubectl")
GROUP = "gateway.networking.k8s.io"

LEGACY_APPS = {"name": "apps", "versions": [{"groupVersion": "apps/v1", "version": "v1"}], "preferredVersion": {"groupVersion": "apps/v1", "version": "v1"}}
LEGACY_GATEWAY = {"name": GROUP, "versions": [{"groupVersion": f"{GROUP}/v1", "version": "v1"}], "preferredVersion": {"groupVersion": f"{GROUP}/v1", "version": "v1"}}
VERSION_DOC = {"kind": "APIResourceList", "apiVersion": "v1", "groupVersion": f"{GROUP}/v1",
               "resources": [{"name": "httproutes", "singularName": "httproute", "namespaced": True, "kind": "HTTPRoute", "verbs": ["get", "list"]},
                             {"name": "gateways", "singularName": "gateway", "namespaced": True, "kind": "Gateway", "verbs": ["get", "list"]}]}


def status(code, reason, message):
    return {"kind": "Status", "apiVersion": "v1", "metadata": {}, "status": "Failure", "message": message, "reason": reason, "code": code}


class DiscoveryServer(http.server.BaseHTTPRequestHandler):
    """Scenario-driven impersonation of an API server's discovery surface (no auth, loopback only)."""

    scenario = "current"

    def log_message(self, *args):  # quiet
        pass

    def reply(self, code, body, content_type="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802
        path = self.path.split("?")[0]
        s = self.scenario
        if path == "/api":
            return self.reply(200, {"kind": "APIVersions", "versions": ["v1"], "serverAddressByClientCIDRs": [{"clientCIDR": "0.0.0.0/0", "serverAddress": "127.0.0.1"}]})
        if path == "/apis":
            if s == "forbidden":
                return self.reply(403, status(403, "Forbidden", 'forbidden: User "system:anonymous" cannot get path "/apis"'))
            if s == "unavailable":
                return self.reply(503, status(503, "ServiceUnavailable", "the server is currently unable to handle the request"))
            if s == "malformed":
                return self.reply(200, b"<html><body>503 Service Unavailable</body></html>", "text/html")
            if s == "aggregated-only":  # a server answering only the v2 aggregated shape (what the reviewer's probe served)
                items = [{"metadata": {"name": GROUP}, "versions": [{"version": "v1", "freshness": "Stale", "resources": []}]}]
                return self.reply(200, {"kind": "APIGroupDiscoveryList", "apiVersion": "apidiscovery.k8s.io/v2", "items": items},
                                  "application/json;g=apidiscovery.k8s.io;v=v2;as=APIGroupDiscoveryList")
            groups = [LEGACY_APPS] if s == "absent" else [LEGACY_APPS, LEGACY_GATEWAY]
            return self.reply(200, {"kind": "APIGroupList", "apiVersion": "v1", "groups": groups})
        if path == f"/apis/{GROUP}/v1":
            if s == "stale":  # the group is registered (APIService/CRD) but its backend cannot serve the version document
                return self.reply(503, status(503, "ServiceUnavailable", f"the server is currently unable to handle the request (get {GROUP}/v1)"))
            if s == "noresource":
                return self.reply(200, {**VERSION_DOC, "resources": VERSION_DOC["resources"][1:]})
            if s == "wronggv":
                return self.reply(200, {**VERSION_DOC, "groupVersion": f"{GROUP}/v1beta1"})
            if s == "absent":
                return self.reply(404, status(404, "NotFound", "the server could not find the requested resource"))
            return self.reply(200, VERSION_DOC)
        return self.reply(404, status(404, "NotFound", "the server could not find the requested resource"))


class RealClientDiscoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not KUBECTL:
            raise AssertionError("a kubectl client is required for the discovery regression (OWLMAST_KUBECTL or PATH); not skipped")
        version = subprocess.run([KUBECTL, "version", "--client", "-o", "json"], capture_output=True, text=True, check=True).stdout
        cls.client_version = json.loads(version)["clientVersion"]["gitVersion"]
        major, minor = (int(x) for x in cls.client_version.lstrip("v").split(".")[:2])
        assert (major, minor) >= (1, 31), f"kubectl {cls.client_version} is older than the qualified client line"
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), DiscoveryServer)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def run_scenario(self, scenario, world=BASE_WORLD, step="bundled-bundled"):
        DiscoveryServer.scenario = scenario
        cache = tempfile.mkdtemp(prefix="owlmast-kubectl-cache.")
        h = Harness(world)
        try:
            r = h.run(step, STUB_DISCOVERY_SERVER=self.url, STUB_REAL_KUBECTL=KUBECTL, STUB_CACHE_DIR=cache)
            return r, h.calls.read_text().splitlines(), h.mutating_calls()
        finally:
            h.close()
            shutil.rmtree(cache, ignore_errors=True)

    def test_client_sees_the_typed_documents(self):
        """Control: the real client returns the legacy APIGroupList for /apis and the APIResourceList for the version."""
        DiscoveryServer.scenario = "current"
        cache = tempfile.mkdtemp(prefix="owlmast-kubectl-cache.")
        try:
            base = [KUBECTL, "--kubeconfig=/dev/null", f"--server={self.url}", f"--cache-dir={cache}", "--request-timeout=10s", "get", "--raw"]
            groups = json.loads(subprocess.run(base + ["/apis"], capture_output=True, text=True, check=True).stdout)
            self.assertEqual((groups["kind"], groups["apiVersion"]), ("APIGroupList", "v1"))
            self.assertIn(GROUP, [g["name"] for g in groups["groups"]])
            version = json.loads(subprocess.run(base + [f"/apis/{GROUP}/v1"], capture_output=True, text=True, check=True).stdout)
            self.assertEqual(version["groupVersion"], f"{GROUP}/v1")
            DiscoveryServer.scenario = "stale"
            failed = subprocess.run(base + [f"/apis/{GROUP}/v1"], capture_output=True, text=True)
            self.assertNotEqual(failed.returncode, 0); self.assertIn("ServiceUnavailable", failed.stderr)
            DiscoveryServer.scenario = "aggregated-only"
            api_versions = subprocess.run([KUBECTL, "--kubeconfig=/dev/null", f"--server={self.url}", f"--cache-dir={cache}", "api-versions"], capture_output=True, text=True)
            self.assertEqual((api_versions.returncode, api_versions.stdout.strip(), api_versions.stderr), (0, "v1", ""))  # the lossy listing the fix no longer trusts
        finally:
            shutil.rmtree(cache, ignore_errors=True)

    def test_stale_group_refuses_before_any_effect(self):
        r, calls, mutations = self.run_scenario("stale")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("REFUSED", r.stdout)
        self.assertIn(f"GET /apis/{GROUP}/v1 failed", r.stdout)
        self.assertEqual(mutations, [])
        self.assertTrue(all(" upgrade " not in c for c in calls))

    def test_genuine_absence_passes_the_optional_check_and_proceeds(self):
        r, calls, _ = self.run_scenario("absent")
        self.assertIn(f"the typed /apis APIGroupList has no group {GROUP}", r.stdout)
        self.assertIn("preflight passed", r.stdout)
        self.assertTrue(all("httproutes" not in c for c in calls), "an absent kind must never be queried as an object")
        self.assertTrue(any(" upgrade --install " in c for c in calls), "the step was reached after preflight")  # stubbed Helm, no cluster

    def test_current_group_proceeds_to_the_object_ownership_gate(self):
        r, calls, mutations = self.run_scenario("current", BASE_WORLD + "httproute owl-mast-test owl-mast foreign:other\n")
        self.assertEqual(r.returncode, 2); self.assertIn("preflight httproute owl-mast-test/owl-mast: exists but owner is 'other'", r.stdout); self.assertEqual(mutations, [])
        r, calls, _ = self.run_scenario("current", BASE_WORLD + "httproute owl-mast-test owl-mast owned\n")
        self.assertIn("preflight httproute owl-mast-test/owl-mast: owned by this run", r.stdout)
        self.assertTrue(any(f" get httproutes.v1.{GROUP} owl-mast --ignore-not-found" in c for c in calls))

    def test_permission_outage_malformed_and_wrong_shape_refuse_with_zero_mutations(self):
        for scenario, message in (("forbidden", "GET /apis failed"), ("unavailable", "GET /apis failed"), ("malformed", "/apis is not JSON"),
                                  ("aggregated-only", "did not return a typed APIGroupList"), ("noresource", "does not list the httproutes resource"),
                                  ("wronggv", f"is not the APIResourceList of {GROUP}/v1")):
            r, calls, mutations = self.run_scenario(scenario)
            self.assertEqual(r.returncode, 2, (scenario, r.stdout[-800:], r.stderr[-300:]))
            self.assertIn(message, r.stdout, scenario)
            self.assertEqual(mutations, [], scenario)


if __name__ == "__main__":
    unittest.main()
