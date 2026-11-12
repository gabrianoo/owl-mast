"""The bundled Keycloak starts on a read-only root exactly as the chart renders it (PR #109 review 4513680461).

`templates/keycloak-deployment.yaml` is rendered and executed in Docker: a disposable PostgreSQL (pinned image)
on a private, internal docker network with Keycloak's own database and principal; the rendered
`seed-quarkus-build` init container run with its rendered command into a volume; then Keycloak started with the
rendered image, args, user/group, read-only root, dropped capabilities, no-new-privileges, the rendered mount
paths (emptyDirs as tmpfs, the seeded volume, the realm import from the rendered ConfigMap) and the rendered env
(Secret references replaced by synthetic values, the DB URL pointed at the disposable PostgreSQL). Management
`/health/ready` must answer 200 and the realm's discovery document must carry the rendered issuer. Requires
Docker and Helm 4 (OWLMAST_HELM); both are failures, never skips, when absent.
"""

import json
import os
import secrets
import shutil
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
CHART = REPO / "deploy" / "helm" / "owl-mast"
HELM = os.environ.get("OWLMAST_HELM") or shutil.which("helm")
POSTGRES_IMAGE = "tensorchord/vchord-postgres:pg18-v1.1.1@sha256:700ff05ebdc7e4afd4dd8442e0684293046c3833677fec326550000a04cf8a91"


def render(template: str) -> dict:
    out = subprocess.run([HELM, "template", "t", str(CHART), "-s", template], capture_output=True, text=True, check=True).stdout
    return yaml.safe_load(out)


def docker(*args, check=True, timeout=600):
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=check, timeout=timeout)


def get(url: str):
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()
    except (urllib.error.URLError, ConnectionError, OSError):
        return None, ""


class KeycloakReadOnlyRootTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if HELM is None:
            raise AssertionError("Helm 4 required (OWLMAST_HELM)")
        if subprocess.run(["docker", "version"], capture_output=True).returncode != 0:
            raise AssertionError("Docker is required for the Keycloak read-only start test and is not available (never skipped)")

    def setUp(self):
        self.suffix = secrets.token_hex(4)
        self.network = f"owlmast-kc-{self.suffix}"
        self.pg = f"owlmast-kc-pg-{self.suffix}"
        self.kc = f"owlmast-kc-{self.suffix}"
        self.volume = f"owlmast-kc-quarkus-{self.suffix}"
        self.tmp = Path(tempfile.mkdtemp(prefix="owlmast-kc."))
        self.tmp.chmod(0o755)

    def tearDown(self):
        for name in (self.kc, self.pg):
            docker("rm", "-f", name, check=False)
        docker("volume", "rm", "-f", self.volume, check=False)
        docker("network", "rm", self.network, check=False)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def start_postgres(self, password: str):
        admin_password = secrets.token_urlsafe(18)
        docker("network", "create", "--internal", self.network)
        docker("run", "-d", "--name", self.pg, "--network", self.network, "--tmpfs", "/var/lib/postgresql/data:rw,size=512m",
               "-e", "PGDATA=/var/lib/postgresql/data/pgdata", "-e", "POSTGRES_USER=owlmast_admin", "-e", f"POSTGRES_PASSWORD={admin_password}",
               POSTGRES_IMAGE)
        deadline = time.time() + 120
        while time.time() < deadline:
            if docker("exec", self.pg, "pg_isready", "-h", "127.0.0.1", "-U", "owlmast_admin", "-q", check=False).returncode == 0:
                break
            time.sleep(1)
        else:
            raise AssertionError("disposable PostgreSQL did not become ready")
        for sql in (f"CREATE ROLE keycloak_app LOGIN PASSWORD '{password}' NOSUPERUSER NOCREATEDB NOCREATEROLE", "CREATE DATABASE keycloak OWNER keycloak_app"):
            docker("exec", "-e", f"PGPASSWORD={admin_password}", self.pg, "psql", "-v", "ON_ERROR_STOP=1", "-h", "127.0.0.1", "-U", "owlmast_admin", "-d", "postgres", "-qc", sql)

    def test_rendered_keycloak_starts_on_a_read_only_root(self):
        deployment = render("templates/keycloak-deployment.yaml")
        realm = render("templates/keycloak-realm-configmap.yaml")
        pod = deployment["spec"]["template"]["spec"]
        user, group = pod["securityContext"]["runAsUser"], pod["securityContext"]["runAsGroup"]
        volumes = {v["name"]: v for v in pod["volumes"]}
        seed, = pod["initContainers"]
        kc, = pod["containers"]

        def hardening(container):
            sc = container["securityContext"]
            self.assertTrue(sc["readOnlyRootFilesystem"], container["name"])
            self.assertFalse(sc["allowPrivilegeEscalation"], container["name"])
            self.assertEqual(sc["capabilities"], {"drop": ["ALL"]}, container["name"])
            return ["--user", f"{user}:{group}", "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges"]

        def mounts(container):
            args = []
            for m in container["volumeMounts"]:
                volume = volumes[m["name"]]
                if m["name"] == "quarkus":
                    args += ["-v", f"{self.volume}:{m['mountPath']}"]
                elif "emptyDir" in volume:
                    args += ["--tmpfs", f"{m['mountPath']}:rw,uid={user},gid={group}"]
                elif "configMap" in volume:
                    self.assertEqual(volume["configMap"]["name"], realm["metadata"]["name"])
                    host = self.tmp / m["name"]; host.mkdir(); host.chmod(0o755)
                    for key, text in realm["data"].items():
                        (host / key).write_text(text); (host / key).chmod(0o644)
                    args += ["-v", f"{host}:{m['mountPath']}:ro"]
                else:
                    raise AssertionError(f"unexpected volume {m['name']}")
            return args

        db_password = secrets.token_urlsafe(18)
        self.start_postgres(db_password)
        # the quarkus emptyDir exactly as the kubelet provides it: a root-owned directory, group fsGroup, mode 2777
        # (setgid). The runtime user does NOT own it, so the seed command must not try to change its attributes
        # (a `cp -a` into it fails with "preserving times for '/seed/.': Operation not permitted" on a real node).
        fs_group = pod.get("securityContext", {}).get("fsGroup", group)
        docker("volume", "create", self.volume)
        docker("run", "--rm", "--user", "0", "-v", f"{self.volume}:/v", "--entrypoint", "sh", seed["image"], "-c", f"chown 0:{fs_group} /v && chmod 2777 /v")
        result = docker("run", "--rm", "--network", "none", *hardening(seed), *mounts(seed), "--entrypoint", seed["command"][0], seed["image"], *seed["command"][1:], check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

        synthetic = {"KC_DB_USERNAME": "keycloak_app", "KC_DB_PASSWORD": db_password, "KC_BOOTSTRAP_ADMIN_USERNAME": "temp-admin", "KC_BOOTSTRAP_ADMIN_PASSWORD": secrets.token_urlsafe(18)}
        env = {}
        for e in kc["env"]:
            env[e["name"]] = synthetic[e["name"]] if "valueFrom" in e else e["value"]
        self.assertIn("sslmode=disable", env["KC_DB_URL"])
        env["KC_DB_URL"] = f"jdbc:postgresql://{self.pg}:5432/keycloak?sslmode=disable"
        env_file = self.tmp / "env"; env_file.write_text("".join(f"{k}={v}\n" for k, v in env.items())); env_file.chmod(0o600)
        ports = {p["name"]: p["containerPort"] for p in kc["ports"]}
        # an internal network has no published ports; the test reaches Keycloak through a second, non-internal network
        bridge = f"{self.network}-host"
        docker("network", "create", bridge)
        self.addCleanup(lambda: docker("network", "rm", bridge, check=False))
        docker("create", "--name", self.kc, "--network", self.network, *hardening(kc), *mounts(kc), "--env-file", str(env_file),
               *[a for port in ports.values() for a in ("-p", f"127.0.0.1::{port}")], kc["image"], *kc["args"])
        docker("network", "connect", bridge, self.kc)
        docker("start", self.kc)

        def host_port(name):
            return docker("port", self.kc, f"{ports[name]}/tcp").stdout.splitlines()[0].rsplit(":", 1)[1]

        readiness = kc["readinessProbe"]["httpGet"]
        management, http = host_port(readiness["port"]), host_port("http")
        deadline = time.time() + 300
        status, body = None, ""
        while time.time() < deadline:
            if docker("inspect", "-f", "{{.State.Running}}", self.kc).stdout.strip() != "true":
                raise AssertionError("Keycloak exited on the read-only root:\n" + docker("logs", self.kc, check=False).stderr[-3000:])
            status, body = get(f"http://127.0.0.1:{management}{readiness['path']}")
            if status == 200:
                break
            time.sleep(3)
        self.assertEqual(status, 200, body + docker("logs", self.kc, check=False).stderr[-3000:])
        self.assertEqual(json.loads(body)["status"], "UP")
        realm_name = json.loads(next(iter(realm["data"].values())))["realm"]
        status, body = get(f"http://127.0.0.1:{http}/realms/{realm_name}/.well-known/openid-configuration")
        self.assertEqual(status, 200, body)
        self.assertEqual(json.loads(body)["issuer"], f"{env['KC_HOSTNAME']}/realms/{realm_name}")


if __name__ == "__main__":
    unittest.main()
