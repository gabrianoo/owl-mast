"""Real first-initialisation of the bundled PostgreSQL scripts against the pinned image (review F1/F2).

Each scenario renders the chart's init ConfigMap, materialises the scripts exactly as the pod mounts
them (only `10-owl-mast-databases.sh` in /docker-entrypoint-initdb.d, the helper at
/owl-mast/provision-keycloak.sh) and starts the pinned PostgreSQL/VectorChord image in a disposable
container: no network, tmpfs data directory, synthetic credentials that are never printed. The
container must complete initialisation on its own (no restart, no recovery) and serve the expected
databases and principals. The first-enable transition is then exercised in the same disposable
container: the helper provisions Keycloak's role/database over the socket, a rerun is a no-op and
application data survives. Requires Docker and Helm 4 (OWLMAST_HELM); both are failures, not skips,
when absent (the repository rule for container runtime).
"""

import os
import secrets
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
CHART = REPO / "deploy" / "helm" / "owl-mast"
HELM = os.environ.get("OWLMAST_HELM") or shutil.which("helm")
IMAGE = "tensorchord/vchord-postgres:pg18-v1.1.1@sha256:700ff05ebdc7e4afd4dd8442e0684293046c3833677fec326550000a04cf8a91"


def render_scripts(*sets) -> dict:
    args = [HELM, "template", "t", str(CHART), "-s", "templates/postgresql-init-configmap.yaml"]
    for s in sets:
        args += ["--set", s]
    out = subprocess.run(args, capture_output=True, text=True, check=True).stdout
    return yaml.safe_load(out)["data"]


class DisposablePostgres:
    """The pinned image started like the pod: init dir with only the first-init script, helper mounted separately."""

    def __init__(self, scripts: dict, keycloak: bool):
        self.tmp = Path(tempfile.mkdtemp(prefix="owlmast-pginit."))
        init = self.tmp / "initdb.d"; init.mkdir()
        helper = self.tmp / "owl-mast"; helper.mkdir()
        (init / "10-owl-mast-databases.sh").write_text(scripts["10-owl-mast-databases.sh"])
        (helper / "provision-keycloak.sh").write_text(scripts["provision-keycloak.sh"])
        for p in (init / "10-owl-mast-databases.sh", helper / "provision-keycloak.sh"):
            p.chmod(0o555)
        for d in (init, helper, self.tmp):
            d.chmod(0o755)
        self.env = {"POSTGRES_USER": "owlmast_admin", "POSTGRES_PASSWORD": secrets.token_urlsafe(24), "PGDATA": "/var/lib/postgresql/data/pgdata",
                    "OWLMAST_APP_DATABASE": "owlmast", "OWLMAST_APP_USERNAME": "owlmast_app", "OWLMAST_APP_PASSWORD": secrets.token_urlsafe(24)}
        self.keycloak_env = {"OWLMAST_KEYCLOAK_DATABASE": "keycloak", "OWLMAST_KEYCLOAK_USERNAME": "keycloak_app", "OWLMAST_KEYCLOAK_PASSWORD": secrets.token_urlsafe(24)}
        if keycloak:
            self.env.update(self.keycloak_env)
        env_file = self.tmp / "env"; env_file.write_text("".join(f"{k}={v}\n" for k, v in self.env.items())); env_file.chmod(0o600)
        self.name = f"owlmast-pginit-{secrets.token_hex(4)}"
        subprocess.run(["docker", "run", "-d", "--name", self.name, "--network", "none", "--tmpfs", "/var/lib/postgresql/data:rw,size=512m",
                        "--env-file", str(env_file), "-v", f"{init}:/docker-entrypoint-initdb.d:ro", "-v", f"{helper}:/owl-mast:ro",
                        IMAGE, "postgres", "-c", "shared_preload_libraries=vchord,vector"], check=True, capture_output=True, text=True)

    def wait_ready(self, timeout=120) -> str:
        deadline = time.time() + timeout
        while time.time() < deadline:
            state = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}} {{.State.ExitCode}} {{.RestartCount}}", self.name], capture_output=True, text=True).stdout.split()
            logs = self.logs()
            if state and state[0] == "false":
                raise AssertionError(f"container exited with code {state[1]} during initialisation:\n{logs[-4000:]}")
            # The entrypoint starts a temporary server for init scripts, stops it, then starts the real one: two ready lines.
            if logs.count("database system is ready to accept connections") >= 2 and "PostgreSQL init process complete" in logs:
                return logs
            time.sleep(1)
        raise AssertionError("initialisation did not complete in time:\n" + self.logs()[-4000:])

    def logs(self) -> str:
        return subprocess.run(["docker", "logs", self.name], capture_output=True, text=True).stdout + subprocess.run(["docker", "logs", self.name], capture_output=True, text=True).stderr

    def sql(self, user_env_prefix: str, db: str, sql: str) -> subprocess.CompletedProcess:
        user = self.env.get(f"{user_env_prefix}_USERNAME") or self.keycloak_env["OWLMAST_KEYCLOAK_USERNAME"]
        password = self.env.get(f"{user_env_prefix}_PASSWORD") or self.keycloak_env["OWLMAST_KEYCLOAK_PASSWORD"]
        if user_env_prefix == "ADMIN":
            user, password = self.env["POSTGRES_USER"], self.env["POSTGRES_PASSWORD"]
        return subprocess.run(["docker", "exec", "-e", f"PGPASSWORD={password}", self.name, "psql", "-v", "ON_ERROR_STOP=1", "-h", "127.0.0.1", "-U", user, "-d", db, "-Atc", sql],
                              capture_output=True, text=True)

    def provision_keycloak(self) -> subprocess.CompletedProcess:
        """What the pre-upgrade Job does, over the socket: the helper with the Keycloak credentials."""
        env = [f"-e{k}={v}" for k, v in {**self.keycloak_env, "POSTGRES_USER": self.env["POSTGRES_USER"], "PGPASSWORD": self.env["POSTGRES_PASSWORD"]}.items()]
        return subprocess.run(["docker", "exec", *env, self.name, "bash", "/owl-mast/provision-keycloak.sh"], capture_output=True, text=True)

    def close(self):
        subprocess.run(["docker", "rm", "-f", self.name], capture_output=True)
        shutil.rmtree(self.tmp, ignore_errors=True)


class PostgresInitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if HELM is None:
            raise AssertionError("Helm 4 required (OWLMAST_HELM)")
        if subprocess.run(["docker", "version"], capture_output=True).returncode != 0:
            raise AssertionError("Docker is required for the real initialisation test and is not available (never skipped)")

    def assert_restricted(self, pg, prefix, db):
        r = pg.sql(prefix, db, "select current_user, rolsuper, rolcreatedb, rolcreaterole from pg_roles where rolname = current_user")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertRegex(r.stdout.strip(), r"^[a-z_]+\|f\|f\|f$")

    def test_external_identity_fresh_volume_initialises_completely_without_keycloak_credentials(self):
        """F1: no Keycloak variables at all; init must finish and the server must serve the app database."""
        pg = DisposablePostgres(render_scripts("identity.bundled=false", "identity.external.issuerUri=https://idp.example/realms/owl-mast"), keycloak=False)
        try:
            logs = pg.wait_ready()
            self.assertIn("identity bundle disabled; no Keycloak database or principal provisioned", logs)
            self.assertNotIn("running /docker-entrypoint-initdb.d/provision-keycloak.sh", logs)
            self.assertNotIn("parameter null or not set", logs)
            self.assertEqual(subprocess.run(["docker", "inspect", "-f", "{{.RestartCount}}", pg.name], capture_output=True, text=True).stdout.strip(), "0")
            self.assertEqual(pg.sql("OWLMAST_APP", "owlmast", "select extname from pg_extension where extname in ('vchord','vector') order by 1").stdout.split(), ["vchord", "vector"])
            self.assertEqual(pg.sql("ADMIN", "postgres", "select count(*) from pg_roles where rolname='keycloak_app'").stdout.strip(), "0")
            self.assertEqual(pg.sql("ADMIN", "postgres", "select count(*) from pg_database where datname='keycloak'").stdout.strip(), "0")
            self.assert_restricted(pg, "OWLMAST_APP", "owlmast")
            # F2: first enable on this freshly initialised app-only instance, then retry, with app data intact.
            self.assertEqual(pg.sql("OWLMAST_APP", "owlmast", "create table marker(v text primary key); insert into marker values ('before-enable'); select count(*) from marker").stdout.strip().splitlines()[-1], "1")
            first = pg.provision_keycloak()
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            self.assertIn("CREATE ROLE", first.stdout); self.assertIn("CREATE DATABASE", first.stdout); self.assertIn("GRANT", first.stdout)
            self.assertEqual(pg.sql("OWLMAST_KEYCLOAK", "keycloak", "select current_database()").stdout.strip(), "keycloak")
            self.assert_restricted(pg, "OWLMAST_KEYCLOAK", "keycloak")
            denied = pg.sql("OWLMAST_KEYCLOAK", "owlmast", "select 1")
            self.assertNotEqual(denied.returncode, 0); self.assertIn('permission denied for database "owlmast"', denied.stderr)
            again = pg.provision_keycloak()
            self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
            self.assertNotIn("CREATE ROLE", again.stdout); self.assertNotIn("CREATE DATABASE", again.stdout); self.assertIn("GRANT", again.stdout)
            self.assertEqual(pg.sql("OWLMAST_KEYCLOAK", "keycloak", "select current_database()").stdout.strip(), "keycloak")  # the existing role kept its password
            self.assertEqual(pg.sql("OWLMAST_APP", "owlmast", "select v from marker").stdout.strip(), "before-enable")
        finally:
            pg.close()

    def test_bundled_identity_fresh_volume_provisions_both_principals(self):
        pg = DisposablePostgres(render_scripts(), keycloak=True)
        try:
            logs = pg.wait_ready()
            self.assertIn("CREATE DATABASE", logs)
            self.assertNotIn("parameter null or not set", logs)
            self.assertEqual(pg.sql("OWLMAST_KEYCLOAK", "keycloak", "select current_database()").stdout.strip(), "keycloak")
            self.assertEqual(pg.sql("OWLMAST_APP", "owlmast", "select current_database()").stdout.strip(), "owlmast")
            self.assert_restricted(pg, "OWLMAST_APP", "owlmast"); self.assert_restricted(pg, "OWLMAST_KEYCLOAK", "keycloak")
            for prefix, db in (("OWLMAST_APP", "keycloak"), ("OWLMAST_KEYCLOAK", "owlmast")):
                denied = pg.sql(prefix, db, "select 1")
                self.assertNotEqual(denied.returncode, 0); self.assertIn(f'permission denied for database "{db}"', denied.stderr)
            self.assertEqual(pg.sql("OWLMAST_APP", "owlmast", "select extname from pg_extension where extname in ('vchord','vector') order by 1").stdout.split(), ["vchord", "vector"])
        finally:
            pg.close()

    def test_helper_without_a_consumer_is_a_safe_no_op_and_the_init_dir_holds_only_the_init_script(self):
        scripts = render_scripts("identity.bundled=false", "identity.external.issuerUri=https://idp.example/realms/owl-mast")
        r = subprocess.run(["bash", "-c", scripts["provision-keycloak.sh"]], capture_output=True, text=True, env={"PATH": os.environ["PATH"]})
        self.assertEqual(r.returncode, 0, r.stderr); self.assertIn("nothing to provision", r.stdout)
        deployment = yaml.safe_load(subprocess.run([HELM, "template", "t", str(CHART), "-s", "templates/postgresql-deployment.yaml"], capture_output=True, text=True, check=True).stdout)
        volumes = {v["name"]: v for v in deployment["spec"]["template"]["spec"]["volumes"]}
        self.assertEqual([i["path"] for i in volumes["init"]["configMap"]["items"]], ["10-owl-mast-databases.sh"])
        self.assertEqual([i["path"] for i in volumes["provisioning"]["configMap"]["items"]], ["provision-keycloak.sh"])
        mounts = {m["name"]: m["mountPath"] for m in deployment["spec"]["template"]["spec"]["containers"][0]["volumeMounts"]}
        self.assertEqual((mounts["init"], mounts["provisioning"]), ("/docker-entrypoint-initdb.d", "/owl-mast"))


if __name__ == "__main__":
    unittest.main()
