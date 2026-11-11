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


FIXTURES = REPO / "deploy" / "local-kind" / "external-fixtures.yaml"


def configmap_mounts(deployment: dict, configmap_name: str) -> dict:
    """{mountPath: [keys]} for every mount of ``configmap_name`` in the Deployment's PostgreSQL container,
    exactly as the kubelet would project it: ``items`` when present, else every key (``None``)."""
    spec = deployment["spec"]["template"]["spec"]
    volumes = {v["name"]: v for v in spec["volumes"]}
    out = {}
    for mount in spec["containers"][0]["volumeMounts"]:
        volume = volumes[mount["name"]]
        if volume.get("configMap", {}).get("name") == configmap_name:
            items = volume["configMap"].get("items")
            out[mount["mountPath"]] = [i["path"] for i in items] if items else None
    return out


def chart_postgres_deployment(*sets) -> dict:
    args = [HELM, "template", "t", str(CHART), "-s", "templates/postgresql-deployment.yaml"]
    for s in sets:
        args += ["--set", s]
    return yaml.safe_load(subprocess.run(args, capture_output=True, text=True, check=True).stdout)


def fixture_postgres_deployment() -> dict:
    docs = [d for d in yaml.safe_load_all(FIXTURES.read_text()) if d]
    return next(d for d in docs if d["kind"] == "Deployment" and d["metadata"]["name"] == "external-postgresql")


def fixture_init_configmap() -> dict:
    """The init ConfigMap exactly as scripts/qualify-local-install.sh renders it for the fixture namespace."""
    out = subprocess.run([HELM, "template", "external", str(CHART), "--set", "fullnameOverride=external", "-s", "templates/postgresql-init-configmap.yaml"],
                         capture_output=True, text=True, check=True).stdout
    return yaml.safe_load(out)


class DisposablePostgres:
    """The pinned image started with the script layout a Deployment manifest actually declares (mounts of the
    init ConfigMap, honouring ``items``), tmpfs data, no network, synthetic credentials."""

    def __init__(self, scripts: dict, keycloak: bool, layout: dict | None = None, env_overrides: dict | None = None):
        self.tmp = Path(tempfile.mkdtemp(prefix="owlmast-pginit."))
        layout = layout if layout is not None else {"/docker-entrypoint-initdb.d": ["10-owl-mast-databases.sh"], "/owl-mast": ["provision-keycloak.sh"]}
        self.layout = layout
        mounts = []
        for index, (mount_path, keys) in enumerate(layout.items()):
            host = self.tmp / f"mount{index}"; host.mkdir()
            for key in (keys if keys is not None else list(scripts)):
                (host / key).write_text(scripts[key]); (host / key).chmod(0o555)
            host.chmod(0o755)
            mounts += ["-v", f"{host}:{mount_path}:ro"]
        self.mounts = mounts
        self.tmp.chmod(0o755)
        self.env = {"POSTGRES_USER": "owlmast_admin", "POSTGRES_PASSWORD": secrets.token_urlsafe(24), "PGDATA": "/var/lib/postgresql/data/pgdata",
                    "OWLMAST_APP_DATABASE": "owlmast", "OWLMAST_APP_USERNAME": "owlmast_app", "OWLMAST_APP_PASSWORD": secrets.token_urlsafe(24)}
        self.keycloak_env = {"OWLMAST_KEYCLOAK_DATABASE": "keycloak", "OWLMAST_KEYCLOAK_USERNAME": "keycloak_app", "OWLMAST_KEYCLOAK_PASSWORD": secrets.token_urlsafe(24)}
        if keycloak:
            self.env.update(self.keycloak_env)
        self.env.update(env_overrides or {})
        env_file = self.tmp / "env"; env_file.write_text("".join(f"{k}={v}\n" for k, v in self.env.items())); env_file.chmod(0o600)
        self.name = f"owlmast-pginit-{secrets.token_hex(4)}"
        subprocess.run(["docker", "run", "-d", "--name", self.name, "--network", "none", "--tmpfs", "/var/lib/postgresql/data:rw,size=512m",
                        "--env-file", str(env_file), *self.mounts,
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

    def wait_exit(self, timeout=120) -> tuple[str, str]:
        """For a refused initialisation: the container must stop on its own; returns (exit code, logs)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            state = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}} {{.State.ExitCode}}", self.name], capture_output=True, text=True).stdout.split()
            if state and state[0] == "false":
                return state[1], self.logs()
            time.sleep(1)
        raise AssertionError("the refused initialisation did not stop:\n" + self.logs()[-4000:])

    def rerun_init(self) -> subprocess.CompletedProcess:
        """The recovery path (docs/installation.md): the first-initialisation script run again in the pod."""
        return subprocess.run(["docker", "exec", "-e", f"PGPASSWORD={self.env['POSTGRES_PASSWORD']}", self.name, "bash", "/docker-entrypoint-initdb.d/10-owl-mast-databases.sh"],
                              capture_output=True, text=True)

    def logs(self) -> str:
        return subprocess.run(["docker", "logs", self.name], capture_output=True, text=True).stdout + subprocess.run(["docker", "logs", self.name], capture_output=True, text=True).stderr

    def sql(self, user_env_prefix: str, db: str, sql: str) -> subprocess.CompletedProcess:
        user = self.env.get(f"{user_env_prefix}_USERNAME") or self.keycloak_env["OWLMAST_KEYCLOAK_USERNAME"]
        password = self.env.get(f"{user_env_prefix}_PASSWORD") or self.keycloak_env["OWLMAST_KEYCLOAK_PASSWORD"]
        if user_env_prefix == "ADMIN":
            user, password = self.env["POSTGRES_USER"], self.env["POSTGRES_PASSWORD"]
        return subprocess.run(["docker", "exec", "-e", f"PGPASSWORD={password}", self.name, "psql", "-v", "ON_ERROR_STOP=1", "-h", "127.0.0.1", "-U", user, "-d", db, "-Atc", sql],
                              capture_output=True, text=True)

    def provision_keycloak(self, **overrides) -> subprocess.CompletedProcess:
        """What the pre-upgrade Job does, over the socket: the helper with the Keycloak credentials (and, like the
        Job, the application principal and database, inherited from the container environment)."""
        env = [f"-e{k}={v}" for k, v in {**self.keycloak_env, "POSTGRES_USER": self.env["POSTGRES_USER"], "PGPASSWORD": self.env["POSTGRES_PASSWORD"], **overrides}.items()]
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

    def probe(self, pg, name, **env):
        """The chart's rendered PostgreSQL probe command, executed in the disposable container as the kubelet would."""
        container = chart_postgres_deployment()["spec"]["template"]["spec"]["containers"][0]
        command = container[name]["exec"]["command"]
        return subprocess.run(["docker", "exec", *[f"-e{k}={v}" for k, v in env.items()], pg.name, *command], capture_output=True, text=True)

    def test_runtime_principals_cannot_connect_to_template1_or_postgres(self):
        """109/4543776411: 'connect only to their own database' includes template1, which keeps PUBLIC CONNECT by default."""
        pg = DisposablePostgres(render_scripts(), keycloak=True)
        try:
            pg.wait_ready()
            for prefix in ("OWLMAST_APP", "OWLMAST_KEYCLOAK"):
                for db in ("template1", "postgres"):
                    denied = pg.sql(prefix, db, "select 1")
                    self.assertNotEqual(denied.returncode, 0, (prefix, db)); self.assertIn(f'permission denied for database "{db}"', denied.stderr, (prefix, db))
            # the provisioning identity still creates databases from the template
            self.assertEqual(pg.sql("ADMIN", "postgres", "create database scratch").returncode, 0)
        finally:
            pg.close()

    def test_first_enable_closes_template1_on_a_volume_initialised_before_the_revoke(self):
        """A volume initialised by an older chart: the provisioning helper (the first-enable hook) applies the revoke too."""
        pg = DisposablePostgres(render_scripts("identity.bundled=false", "identity.external.issuerUri=https://idp.example/realms/owl-mast"), keycloak=False)
        try:
            pg.wait_ready()
            self.assertEqual(pg.sql("ADMIN", "postgres", "grant connect on database template1 to public; select 1").returncode, 0)  # the older state
            self.assertEqual(pg.sql("OWLMAST_APP", "template1", "select 1").returncode, 0)
            self.assertEqual(pg.provision_keycloak().returncode, 0)
            for prefix in ("OWLMAST_APP", "OWLMAST_KEYCLOAK"):
                self.assertIn('permission denied for database "template1"', pg.sql(prefix, "template1", "select 1").stderr, prefix)
        finally:
            pg.close()

    def test_keycloak_collision_is_refused_before_the_application_role_and_database_exist(self):
        """116 review body (init-configmap:104): the Keycloak owner/role refusals ran only after the application role,
        database and extension had been created, leaving a half-initialised volume behind a 'nothing created' message."""
        for overrides, message in (({"OWLMAST_KEYCLOAK_DATABASE": "postgres"}, "the existing database postgres is owned by owlmast_admin, not keycloak_app"),
                                   ({"OWLMAST_KEYCLOAK_DATABASE": "owlmast_admin"}, "the existing database owlmast_admin is owned by owlmast_admin, not keycloak_app"),
                                   ({"OWLMAST_KEYCLOAK_DATABASE": "owlmast"}, "the Keycloak database name equals the application database name")):
            pg = DisposablePostgres(render_scripts(), keycloak=True, env_overrides=overrides)
            try:
                code, logs = pg.wait_exit()
                self.assertNotEqual(code, "0", overrides)
                self.assertIn(message, logs, overrides)
                ours = logs.split("running /docker-entrypoint-initdb.d/10-owl-mast-databases.sh", 1)[1]
                for statement in ("CREATE ROLE", "CREATE DATABASE", "CREATE EXTENSION", "REVOKE", "GRANT"):
                    self.assertNotIn(statement, ours, (overrides, statement))
            finally:
                pg.close()

    def test_probes_during_socket_only_first_initialisation(self):
        """109/4543776343, at runtime: an extra init script holds the entrypoint in its initialisation phase, when the
        temporary server listens on the Unix socket only. The rendered startup and liveness probes pass there (the
        former TCP probes fail, which is what let the kubelet kill a slow initialisation); readiness stays false."""
        scripts = dict(render_scripts("identity.bundled=false", "identity.external.issuerUri=https://idp.example/realms/owl-mast"))
        scripts["05-hold.sh"] = "#!/bin/bash\necho owl-mast-test: holding initialisation\nwhile [ ! -e /tmp/release ]; do sleep 0.2; done\n"
        layout = {"/docker-entrypoint-initdb.d": ["05-hold.sh", "10-owl-mast-databases.sh"], "/owl-mast": ["provision-keycloak.sh"]}
        pg = DisposablePostgres(scripts, keycloak=False, layout=layout)
        try:
            deadline = time.time() + 120
            while "holding initialisation" not in pg.logs():
                self.assertLess(time.time(), deadline, pg.logs()[-2000:]); time.sleep(0.5)
            self.assertEqual(self.probe(pg, "startupProbe").returncode, 0)
            self.assertEqual(self.probe(pg, "livenessProbe").returncode, 0)
            tcp = subprocess.run(["docker", "exec", pg.name, "sh", "-c", 'pg_isready -U "$POSTGRES_USER" -d postgres -h 127.0.0.1'], capture_output=True, text=True)
            self.assertNotEqual(tcp.returncode, 0, "the initialisation server must not listen on TCP; the old probe would have passed")
            self.assertNotEqual(self.probe(pg, "readinessProbe").returncode, 0)  # not Ready while initialising
            subprocess.run(["docker", "exec", pg.name, "touch", "/tmp/release"], check=True)
            pg.wait_ready()
            for name in ("startupProbe", "livenessProbe", "readinessProbe"):
                self.assertEqual(self.probe(pg, name).returncode, 0, name)
        finally:
            pg.close()

    def test_preflight_creates_nothing_and_the_full_run_still_provisions(self):
        pg = DisposablePostgres(render_scripts("identity.bundled=false", "identity.external.issuerUri=https://idp.example/realms/owl-mast"), keycloak=False)
        try:
            pg.wait_ready()
            env = [f"-e{k}={v}" for k, v in {**pg.keycloak_env, "POSTGRES_USER": pg.env["POSTGRES_USER"], "PGPASSWORD": pg.env["POSTGRES_PASSWORD"]}.items()]
            r = subprocess.run(["docker", "exec", *env, pg.name, "bash", "/owl-mast/provision-keycloak.sh", "--preflight"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr); self.assertIn("preflight passed; nothing created", r.stdout)
            self.assertEqual(pg.sql("ADMIN", "postgres", "select (select count(*) from pg_roles where rolname='keycloak_app') + (select count(*) from pg_database where datname='keycloak')").stdout.strip(), "0")
            self.assertEqual(pg.provision_keycloak().returncode, 0)
            self.assertEqual(pg.sql("OWLMAST_KEYCLOAK", "keycloak", "select current_database()").stdout.strip(), "keycloak")
        finally:
            pg.close()

    def test_rendered_probes_run_in_the_image_and_readiness_ignores_keycloaks_database(self):
        """109/4543776343 and 116/4544181074: the probe commands as rendered. Startup and liveness answer on the Unix socket
        (the only listener during first initialisation); readiness needs TCP and the APPLICATION database only. The
        identity bundle enabled on a volume initialised without it must leave PostgreSQL Ready: otherwise its Service
        loses its endpoints, the backend loses its database, and the provisioning hook cannot reach the server."""
        pg = DisposablePostgres(render_scripts("identity.bundled=false", "identity.external.issuerUri=https://idp.example/realms/owl-mast"), keycloak=False)
        try:
            pg.wait_ready()
            for name in ("startupProbe", "livenessProbe", "readinessProbe"):
                r = self.probe(pg, name)
                self.assertEqual(r.returncode, 0, (name, r.stdout, r.stderr))
            # the bundle-on-old-volume case: Keycloak's database does not exist, and the pod carries Keycloak's variables
            self.assertNotEqual(pg.sql("ADMIN", "keycloak", "select 1").returncode, 0)
            for name in ("readinessProbe", "livenessProbe"):
                r = self.probe(pg, name, OWLMAST_KEYCLOAK_DATABASE="keycloak")
                self.assertEqual(r.returncode, 0, (name, r.stdout, r.stderr))
            # the repair the docs name still works in that state, and readiness is unchanged by it
            self.assertEqual(pg.provision_keycloak().returncode, 0)
            self.assertEqual(self.probe(pg, "readinessProbe", OWLMAST_KEYCLOAK_DATABASE="keycloak").returncode, 0)
            # readiness does follow the application database: a name that does not exist is not Ready
            self.assertNotEqual(self.probe(pg, "readinessProbe", OWLMAST_APP_DATABASE="missing").returncode, 0)
        finally:
            pg.close()

    def test_external_fixture_manifest_layout_initialises_a_fresh_volume_with_both_principals(self):
        """N1: the fixture Deployment's actual mounts of the ConfigMap the qualification script renders for it,
        with the fixture's four credentials, on a fresh volume: init completes on the first start and the
        external Keycloak's role/database exist with the same isolation as the chart's PostgreSQL."""
        configmap = fixture_init_configmap()
        self.assertEqual(configmap["metadata"]["name"], "external-postgresql-init")
        layout = configmap_mounts(fixture_postgres_deployment(), "external-postgresql-init")
        self.assertEqual(layout, {"/docker-entrypoint-initdb.d": ["10-owl-mast-databases.sh"], "/owl-mast": ["provision-keycloak.sh"]})
        pg = DisposablePostgres(configmap["data"], keycloak=True, layout=layout)
        try:
            logs = pg.wait_ready()
            self.assertEqual(subprocess.run(["docker", "inspect", "-f", "{{.RestartCount}} {{.State.Running}}", pg.name], capture_output=True, text=True).stdout.strip(), "0 true")
            self.assertNotIn("No such file or directory", logs); self.assertNotIn("parameter null or not set", logs)
            self.assertIn("CREATE DATABASE", logs)
            self.assertEqual(pg.sql("OWLMAST_KEYCLOAK", "keycloak", "select current_database()").stdout.strip(), "keycloak")
            self.assertEqual(pg.sql("OWLMAST_APP", "owlmast", "select extname from pg_extension where extname in ('vchord','vector') order by 1").stdout.split(), ["vchord", "vector"])
            self.assert_restricted(pg, "OWLMAST_APP", "owlmast"); self.assert_restricted(pg, "OWLMAST_KEYCLOAK", "keycloak")
            for prefix, db in (("OWLMAST_APP", "keycloak"), ("OWLMAST_KEYCLOAK", "owlmast")):
                denied = pg.sql(prefix, db, "select 1")
                self.assertNotEqual(denied.returncode, 0); self.assertIn(f'permission denied for database "{db}"', denied.stderr)
        finally:
            pg.close()

    def test_chart_manifest_layout_matches_the_tested_layout(self):
        """The chart's PostgreSQL Deployment declares the same init/helper separation the other tests materialise."""
        self.assertEqual(configmap_mounts(chart_postgres_deployment(), "t-owl-mast-postgresql-init"),
                         {"/docker-entrypoint-initdb.d": ["10-owl-mast-databases.sh"], "/owl-mast": ["provision-keycloak.sh"]})

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


    # -- PR #109 post-merge review (5827094734) ------------------------------------------------------------

    def test_first_initialisation_script_is_idempotent_and_a_rerun_is_a_no_op(self):
        """4513680506: a failed first initialisation can be completed by rerunning the script; a rerun creates nothing."""
        pg = DisposablePostgres(render_scripts(), keycloak=True)
        try:
            logs = pg.wait_ready()
            self.assertIn("CREATE ROLE", logs); self.assertIn("CREATE DATABASE", logs)
            self.assertEqual(pg.sql("OWLMAST_APP", "owlmast", "create table marker(v text primary key); insert into marker values ('kept'); select count(*) from marker").stdout.strip().splitlines()[-1], "1")
            again = pg.rerun_init()
            self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
            self.assertNotIn("CREATE ROLE", again.stdout); self.assertNotIn("CREATE DATABASE", again.stdout)
            self.assertEqual(pg.sql("OWLMAST_APP", "owlmast", "select v from marker").stdout.strip(), "kept")
            self.assertEqual(pg.sql("OWLMAST_KEYCLOAK", "keycloak", "select current_database()").stdout.strip(), "keycloak")
            self.assert_restricted(pg, "OWLMAST_APP", "owlmast")
            # half-initialised volume (the script stopped before Keycloak's principal was provisioned): the rerun completes it
            for statement in ("drop database keycloak", "drop role keycloak_app"):
                dropped = pg.sql("ADMIN", "postgres", statement)
                self.assertEqual(dropped.returncode, 0, dropped.stderr)
            completed = pg.rerun_init()
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("CREATE ROLE", completed.stdout); self.assertIn("CREATE DATABASE", completed.stdout)
            self.assertEqual(pg.sql("OWLMAST_KEYCLOAK", "keycloak", "select current_database()").stdout.strip(), "keycloak")
        finally:
            pg.close()

    def test_application_principal_equal_to_the_superuser_is_refused_before_anything_is_created(self):
        pg = DisposablePostgres(render_scripts("identity.bundled=false", "identity.external.issuerUri=https://idp.example/realms/owl-mast"), keycloak=False,
                                env_overrides={"OWLMAST_APP_USERNAME": "owlmast_admin"})
        try:
            code, logs = pg.wait_exit()
            self.assertNotEqual(code, "0", logs[-2000:])
            self.assertIn("refusing to initialise: the application username equals the provisioning superuser username", logs)
            ours = logs.split("running /docker-entrypoint-initdb.d/10-owl-mast-databases.sh", 1)[1]  # the entrypoint's own POSTGRES_DB creation precedes it
            self.assertNotIn("CREATE ROLE", ours); self.assertNotIn("CREATE DATABASE", ours)
        finally:
            pg.close()

    def test_keycloak_principal_equal_to_the_application_principal_is_refused_at_initialisation(self):
        pg = DisposablePostgres(render_scripts(), keycloak=True, env_overrides={"OWLMAST_KEYCLOAK_USERNAME": "owlmast_app"})
        try:
            code, logs = pg.wait_exit()
            self.assertNotEqual(code, "0")
            self.assertIn("the Keycloak username equals the application username", logs)
            self.assertNotIn("CREATE", logs.split("running /docker-entrypoint-initdb.d/10-owl-mast-databases.sh", 1)[1])
        finally:
            pg.close()

    def test_provisioning_refuses_a_privileged_or_colliding_keycloak_role_before_creating_anything(self):
        pg = DisposablePostgres(render_scripts("identity.bundled=false", "identity.external.issuerUri=https://idp.example/realms/owl-mast"), keycloak=False)
        try:
            pg.wait_ready()
            for overrides, message in (({"OWLMAST_KEYCLOAK_USERNAME": "owlmast_app"}, "equals the application username"),
                                       ({"OWLMAST_KEYCLOAK_USERNAME": "owlmast_admin"}, "equals the provisioning superuser username"),
                                       ({"OWLMAST_KEYCLOAK_DATABASE": "owlmast"}, "database name equals the application database name")):
                r = pg.provision_keycloak(**overrides)
                self.assertNotEqual(r.returncode, 0, overrides); self.assertIn(message, r.stderr, overrides)
                self.assertNotIn("CREATE", r.stdout, overrides)
            created = pg.sql("ADMIN", "postgres", "create role keycloak_app login createrole; select 1")
            self.assertEqual(created.returncode, 0, created.stderr)
            r = pg.provision_keycloak()
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("the existing role keycloak_app is privileged", r.stderr)
            self.assertNotIn("CREATE DATABASE", r.stdout)
            self.assertEqual(pg.sql("ADMIN", "postgres", "select count(*) from pg_database where datname='keycloak'").stdout.strip(), "0")
        finally:
            pg.close()

    def test_provisioning_hook_fails_at_once_when_the_postgresql_service_does_not_resolve(self):
        """4513680443: an upgrade whose release has no bundled PostgreSQL yet must not wait out the Helm timeout."""
        tmp = Path(tempfile.mkdtemp(prefix="owlmast-pgjob."))
        try:
            (tmp / "provision-keycloak.sh").write_text(render_scripts()["provision-keycloak.sh"]); tmp.chmod(0o755); (tmp / "provision-keycloak.sh").chmod(0o555)
            env = {"PGHOST": "t-owl-mast-postgresql", "PGPORT": "5432", "POSTGRES_USER": "owlmast_admin", "PGPASSWORD": secrets.token_urlsafe(12),
                   "OWLMAST_APP_USERNAME": "owlmast_app", "OWLMAST_APP_DATABASE": "owlmast",
                   "OWLMAST_KEYCLOAK_DATABASE": "keycloak", "OWLMAST_KEYCLOAK_USERNAME": "keycloak_app", "OWLMAST_KEYCLOAK_PASSWORD": secrets.token_urlsafe(12)}
            started = time.time()
            r = subprocess.run(["docker", "run", "--rm", "--network", "none", "-v", f"{tmp}:/owl-mast:ro", *[a for k, v in env.items() for a in ("-e", f"{k}={v}")],
                                "--entrypoint", "bash", IMAGE, "/owl-mast/provision-keycloak.sh"], capture_output=True, text=True, timeout=120)
            elapsed = time.time() - started
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("PostgreSQL service t-owl-mast-postgresql does not resolve", r.stderr)
            self.assertNotIn("waiting for PostgreSQL", r.stdout)
            self.assertLess(elapsed, 60)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


    def test_application_database_owned_by_another_role_is_refused(self):
        """database.name equal to the admin username: the entrypoint already created that database, owned by the superuser."""
        pg = DisposablePostgres(render_scripts("identity.bundled=false", "identity.external.issuerUri=https://idp.example/realms/owl-mast"), keycloak=False,
                                env_overrides={"OWLMAST_APP_DATABASE": "owlmast_admin"})
        try:
            code, logs = pg.wait_exit()
            self.assertNotEqual(code, "0")
            self.assertIn("the existing database owlmast_admin is owned by owlmast_admin, not owlmast_app", logs)
            self.assertNotIn("CREATE ROLE", logs.split("running /docker-entrypoint-initdb.d/10-owl-mast-databases.sh", 1)[1])
        finally:
            pg.close()

    def test_provisioning_refuses_a_member_role_or_a_foreign_owned_keycloak_database(self):
        pg = DisposablePostgres(render_scripts("identity.bundled=false", "identity.external.issuerUri=https://idp.example/realms/owl-mast"), keycloak=False)
        try:
            pg.wait_ready()
            self.assertEqual(pg.sql("ADMIN", "postgres", "create database keycloak").returncode, 0)  # owned by the superuser
            r = pg.provision_keycloak()
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("the existing database keycloak is owned by owlmast_admin, not keycloak_app", r.stderr)
            self.assertNotIn("CREATE ROLE", r.stdout)
            self.assertEqual(pg.sql("ADMIN", "postgres", "select count(*) from pg_roles where rolname='keycloak_app'").stdout.strip(), "0")
            self.assertEqual(pg.sql("ADMIN", "postgres", "drop database keycloak").returncode, 0)
            for statement in ("create role keycloak_app login", "grant pg_read_all_data to keycloak_app"):
                done = pg.sql("ADMIN", "postgres", statement)
                self.assertEqual(done.returncode, 0, done.stderr)
            r = pg.provision_keycloak()
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("is privileged (superuser, createrole, createdb, replication or bypassrls) or a member of another role", r.stderr)
            self.assertEqual(pg.sql("ADMIN", "postgres", "select count(*) from pg_database where datname='keycloak'").stdout.strip(), "0")
        finally:
            pg.close()

    def test_rerun_refuses_an_application_role_that_became_a_member(self):
        pg = DisposablePostgres(render_scripts("identity.bundled=false", "identity.external.issuerUri=https://idp.example/realms/owl-mast"), keycloak=False)
        try:
            pg.wait_ready()
            self.assertEqual(pg.sql("ADMIN", "postgres", "grant pg_read_all_data to owlmast_app").returncode, 0)
            r = pg.rerun_init()
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("the existing role owlmast_app is privileged", r.stderr)
        finally:
            pg.close()


if __name__ == "__main__":
    unittest.main()
