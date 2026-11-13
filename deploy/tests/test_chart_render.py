"""Deterministic packaging checks for the owl-mast chart (OM-01.02-T1/T4).

Runs `helm lint` and `helm template` for the four bundled/external combinations and asserts the
fail-closed validations. Requires Helm 4.x; set OWLMAST_HELM to the binary (scripts/verify-install-package.sh
fetches a checksum-verified Helm 4.3.1 when none is available).
"""

import os
import re
import shutil
import subprocess
import unittest
from pathlib import Path

import yaml  # PyYAML is bundled with the Python used in CI (setup-python) and this repository's checks.

REPO = Path(__file__).resolve().parents[2]
CHART = REPO / "deploy" / "helm" / "owl-mast"
EXAMPLES = CHART / "examples"
HELM = os.environ.get("OWLMAST_HELM") or shutil.which("helm")
# The HTTPRoute renders only where the Gateway API CRDs are served; helm template has no cluster, so the
# capability is declared explicitly (as an operator would with --api-versions).
GATEWAY_API = ["--api-versions", "gateway.networking.k8s.io/v1/HTTPRoute"]
# The provisioning hook is refused on install; its renders model the upgrade it belongs to.
UPGRADE = ["--is-upgrade"]

COMBINATIONS = {
    "bundled-bundled": [],
    "bundled-external": ["--set", "identity.bundled=false", "--set", "identity.external.issuerUri=https://idp.example/realms/owl-mast"],
    "external-bundled": [
        "--set", "database.bundled=false", "--set", "database.external.host=pg.example",
        "--set", "identity.keycloak.database.external.host=pg.example",
    ],
    "external-external": [
        "--set", "database.bundled=false", "--set", "database.external.host=pg.example",
        "--set", "identity.bundled=false", "--set", "identity.external.issuerUri=https://idp.example/realms/owl-mast",
    ],
}


def helm(*args):
    return subprocess.run([HELM, *args], capture_output=True, text=True, check=False)


def render(*args):
    result = helm("template", "t", str(CHART), *args)
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def by_kind(docs, kind):
    return [d for d in docs if d["kind"] == kind]


def refused(*args):
    """helm template must fail; returns stderr for the caller to check the named value."""
    result = helm("template", "t", str(CHART), *args)
    if result.returncode == 0:
        raise AssertionError(f"rendering succeeded but must be refused: {args}")
    return result.stderr


def sets(*values):
    return [a for v in values for a in ("--set", v)]


def notes(*args):
    """NOTES.txt as Helm prints it after an install (client-side dry run, no cluster)."""
    result = helm("install", "t", str(CHART), "--dry-run=client", *args)
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return result.stdout.split("NOTES:", 1)[1]


def env_of(deployment):
    return {e["name"]: e for e in deployment["spec"]["template"]["spec"]["containers"][0]["env"]}


@unittest.skipIf(HELM is None, "helm binary required (OWLMAST_HELM)")
class ChartRenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        version = helm("version", "--template", "{{.Version}}")
        if not version.stdout.startswith("v4."):
            raise AssertionError(f"Helm 4.x required for Kubernetes 1.36 (found {version.stdout!r})")

    def test_lint_passes(self):
        result = helm("lint", str(CHART))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_bundled_bundled_renders_both_bundles_with_probes_and_retained_claim(self):
        docs = render()
        deployments = {d["metadata"]["name"]: d for d in by_kind(docs, "Deployment")}
        self.assertEqual(set(deployments), {"t-owl-mast-backend", "t-owl-mast-postgresql", "t-owl-mast-keycloak"})
        for d in deployments.values():
            c = d["spec"]["template"]["spec"]["containers"][0]
            self.assertIn("startupProbe", c, d["metadata"]["name"])
            self.assertIn("livenessProbe", c, d["metadata"]["name"])
            self.assertIn("readinessProbe", c, d["metadata"]["name"])
            self.assertIn("limits", c["resources"])
            self.assertIn("requests", c["resources"])
        pvc = by_kind(docs, "PersistentVolumeClaim")
        self.assertEqual(len(pvc), 1)
        self.assertEqual(pvc[0]["metadata"]["annotations"]["helm.sh/resource-policy"], "keep")
        self.assertEqual(deployments["t-owl-mast-postgresql"]["spec"]["strategy"]["type"], "Recreate")
        self.assertEqual(
            deployments["t-owl-mast-postgresql"]["spec"]["template"]["spec"]["volumes"][0]["persistentVolumeClaim"]["claimName"],
            "t-owl-mast-postgresql-data",
        )
        backend_env = env_of(deployments["t-owl-mast-backend"])
        self.assertEqual(backend_env["OWLMAST_IDENTITY_ISSUER_URI"]["value"], "http://t-owl-mast-keycloak:8080/realms/owl-mast")
        self.assertEqual(backend_env["OWLMAST_DATABASE_R2DBC_URL"]["value"], "r2dbc:postgresql://t-owl-mast-postgresql:5432/owlmast?sslMode=disable")
        self.assertEqual(backend_env["OWLMAST_DATABASE_PASSWORD"]["valueFrom"]["secretKeyRef"], {"name": "owl-mast-db", "key": "password"})
        kc_env = env_of(deployments["t-owl-mast-keycloak"])
        self.assertEqual(kc_env["KC_DB_URL"]["value"], "jdbc:postgresql://t-owl-mast-postgresql:5432/keycloak?sslmode=disable")
        self.assertEqual(kc_env["KC_DB_USERNAME"]["valueFrom"]["secretKeyRef"]["name"], "owl-mast-keycloak-db")
        self.assertEqual(kc_env["KC_HOSTNAME"]["value"], "http://t-owl-mast-keycloak:8080")

    def test_images_are_digest_pinned(self):
        docs = render()
        images = {
            d["metadata"]["name"]: d["spec"]["template"]["spec"]["containers"][0]["image"] for d in by_kind(docs, "Deployment")
        }
        self.assertEqual(
            images["t-owl-mast-postgresql"],
            "tensorchord/vchord-postgres:pg18-v1.1.1@sha256:700ff05ebdc7e4afd4dd8442e0684293046c3833677fec326550000a04cf8a91",
        )
        self.assertEqual(
            images["t-owl-mast-keycloak"],
            "quay.io/keycloak/keycloak:26.8.2@sha256:3879c623248408de29a5303178b5816c77e8dfef3890c361f8c0bbeaa979ba3b",
        )
        pinned = render("--set", "backend.image.digest=sha256:" + "a" * 64)
        self.assertEqual(
            {d["metadata"]["name"]: d for d in by_kind(pinned, "Deployment")}["t-owl-mast-backend"]["spec"]["template"]["spec"]["containers"][0]["image"],
            "owl-mast/backend:0.1.0@sha256:" + "a" * 64,
        )

    def test_external_database_omits_bundle_and_points_both_consumers_at_it(self):
        docs = render(*COMBINATIONS["external-bundled"])
        names = {d["metadata"]["name"] for d in docs}
        self.assertNotIn("t-owl-mast-postgresql", names)
        self.assertNotIn("t-owl-mast-postgresql-data", names)
        deployments = {d["metadata"]["name"]: d for d in by_kind(docs, "Deployment")}
        # D1: the external transport defaults to require (never a silent plaintext fallback)
        self.assertEqual(env_of(deployments["t-owl-mast-backend"])["OWLMAST_DATABASE_JDBC_URL"]["value"], "jdbc:postgresql://pg.example:5432/owlmast?sslmode=require")
        self.assertEqual(env_of(deployments["t-owl-mast-backend"])["OWLMAST_DATABASE_R2DBC_URL"]["value"], "r2dbc:postgresql://pg.example:5432/owlmast?sslMode=require")
        self.assertEqual(env_of(deployments["t-owl-mast-keycloak"])["KC_DB_URL"]["value"], "jdbc:postgresql://pg.example:5432/keycloak?sslmode=require")

    def test_external_identity_omits_keycloak_but_keeps_issuer(self):
        docs = render(*COMBINATIONS["bundled-external"])
        names = {d["metadata"]["name"] for d in docs}
        self.assertNotIn("t-owl-mast-keycloak", names)
        self.assertNotIn("t-owl-mast-keycloak-realm", names)
        backend = {d["metadata"]["name"]: d for d in by_kind(docs, "Deployment")}["t-owl-mast-backend"]
        self.assertEqual(env_of(backend)["OWLMAST_IDENTITY_ISSUER_URI"]["value"], "https://idp.example/realms/owl-mast")

    def test_external_identity_needs_no_keycloak_credentials(self):
        """R2: with the identity bundle disabled, no rendered object references a Keycloak Secret or
        Keycloak database credentials, so the install needs only the application and admin Secrets."""
        docs = render(*COMBINATIONS["bundled-external"])
        referenced = set()
        for d in by_kind(docs, "Deployment") + by_kind(docs, "Job"):
            for c in d["spec"]["template"]["spec"]["containers"]:
                for e in c.get("env", []):
                    ref = e.get("valueFrom", {}).get("secretKeyRef")
                    if ref:
                        referenced.add(ref["name"])
                    self.assertFalse(e["name"].startswith("OWLMAST_KEYCLOAK"), e["name"])
        self.assertEqual(referenced, {"owl-mast-db", "owl-mast-postgres-admin"})
        init = {d["metadata"]["name"]: d for d in by_kind(docs, "ConfigMap")}["t-owl-mast-postgresql-init"]
        self.assertIn('if [ -n "${OWLMAST_KEYCLOAK_USERNAME:-}" ]', init["data"]["10-owl-mast-databases.sh"])
        bundled = render()
        pg = {d["metadata"]["name"]: d for d in by_kind(bundled, "Deployment")}["t-owl-mast-postgresql"]
        self.assertEqual(env_of(pg)["OWLMAST_KEYCLOAK_PASSWORD"]["valueFrom"]["secretKeyRef"], {"name": "owl-mast-keycloak-db", "key": "password"})

    def test_keycloak_provisioning_job_is_explicit_and_idempotent(self):
        """R2: enabling Keycloak on an initialised volume is an explicit opt-in Job, never a silent recreation."""
        self.assertEqual(by_kind(render(), "Job"), [])
        self.assertEqual(by_kind(render(*UPGRADE), "Job"), [])
        docs = render("--set", "postgresql.provisionKeycloakDatabase=true", *UPGRADE)
        job = by_kind(docs, "Job")
        self.assertEqual(len(job), 1)
        self.assertEqual(job[0]["metadata"]["annotations"]["helm.sh/hook"], "pre-upgrade")  # F2: provisions before Helm waits for the consumers
        self.assertEqual(job[0]["spec"]["template"]["spec"]["containers"][0]["command"], ["bash", "/owl-mast/provision-keycloak.sh"])
        self.assertEqual(job[0]["spec"]["template"]["spec"]["volumes"][0]["configMap"]["name"], "t-owl-mast-postgresql-provision-scripts")
        hook_cm = {d["metadata"]["name"]: d for d in by_kind(docs, "ConfigMap")}["t-owl-mast-postgresql-provision-scripts"]
        self.assertEqual((hook_cm["metadata"]["annotations"]["helm.sh/hook"], hook_cm["metadata"]["annotations"]["helm.sh/hook-weight"]), ("pre-upgrade", "-5"))
        script = {d["metadata"]["name"]: d for d in by_kind(docs, "ConfigMap")}["t-owl-mast-postgresql-init"]["data"]["provision-keycloak.sh"]
        self.assertEqual(hook_cm["data"]["provision-keycloak.sh"], script)  # the hook carries the same script, independent of the release ConfigMap
        self.assertIn("pg_isready", script)  # bounded readiness wait before provisioning over the network
        self.assertIn("WHERE NOT EXISTS (SELECT 1 FROM pg_roles", script)
        self.assertIn("WHERE NOT EXISTS (SELECT 1 FROM pg_database", script)
        self.assertNotIn("DROP", script.upper())
        for sets in (
            ("postgresql.provisionKeycloakDatabase=true", "identity.bundled=false", "identity.external.issuerUri=https://idp.example/realms/x"),
            ("postgresql.provisionKeycloakDatabase=true", "database.bundled=false", "database.external.host=pg.example", "identity.keycloak.database.external.host=pg.example"),
        ):
            result = helm("template", "t", str(CHART), *UPGRADE, *[a for s_ in sets for a in ("--set", s_)])
            self.assertNotEqual(result.returncode, 0, sets)
            self.assertIn("provisionKeycloakDatabase=true applies only", result.stderr)

    def test_external_external_renders_only_the_backend(self):
        docs = render(*COMBINATIONS["external-external"])
        self.assertEqual([d["metadata"]["name"] for d in by_kind(docs, "Deployment")], ["t-owl-mast-backend"])
        self.assertEqual(by_kind(docs, "PersistentVolumeClaim"), [])

    def test_missing_external_values_fail_rendering_with_the_value_named(self):
        cases = {
            ("database.bundled=false",): "database.external.host",
            ("identity.bundled=false",): "identity.external.issuerUri",
            ("identity.bundled=false", "identity.external.issuerUri=idp.example/realms/x"): "absolute https:// URL",
            ("database.bundled=false", "database.external.host=pg.example"): "identity.keycloak.database.external.host",
            ("frontend.enabled=true",): "frontend.image.tag or frontend.image.digest",
            ("routing.ingress.enabled=true",): "routing.ingress.host",
        }
        for sets, expected in cases.items():
            args = [a for s in sets for a in ("--set", s)]
            result = helm("template", "t", str(CHART), *args)
            self.assertNotEqual(result.returncode, 0, sets)
            self.assertIn(expected, result.stderr, sets)

    def test_secret_references_and_unknown_keys_fail_schema_validation(self):
        for sets in (
            ("database.existingSecret=",),
            ("postgresql.adminExistingSecret=",),
            ("identity.keycloak.database.existingSecret=",),
            ("auth.enabled=false",),  # no such knob: authentication cannot be switched off
            ("identity.enabled=false",),
            ("postgresql.image.digest=",),
            ("backend.extraEnv[0].name=DB_PASSWORD", "backend.extraEnv[0].value=x"),
        ):
            args = [a for s in sets for a in ("--set", s)]
            result = helm("template", "t", str(CHART), *args)
            self.assertNotEqual(result.returncode, 0, sets)
            self.assertIn("schema", result.stderr.lower(), sets)

    def test_frontend_values_are_independent_of_the_backend_image(self):
        docs = render("--set", "frontend.enabled=true", "--set", "frontend.image.tag=0.0.1-shell",
                      "--set", "routing.ingress.enabled=true", "--set", "routing.ingress.host=owl-mast.local")
        deployments = {d["metadata"]["name"]: d for d in by_kind(docs, "Deployment")}
        self.assertEqual(deployments["t-owl-mast-frontend"]["spec"]["template"]["spec"]["containers"][0]["image"], "owl-mast/frontend:0.0.1-shell")
        self.assertEqual(deployments["t-owl-mast-backend"]["spec"]["template"]["spec"]["containers"][0]["image"], "owl-mast/backend:0.1.0")
        ingress = by_kind(docs, "Ingress")[0]
        paths = {p["path"]: p["backend"]["service"]["name"] for p in ingress["spec"]["rules"][0]["http"]["paths"]}
        self.assertEqual(paths, {"/api": "t-owl-mast-backend", "/": "t-owl-mast-frontend"})  # the actuator is not routed by default

    def test_common_labels_reach_pod_templates(self):
        docs = render("--set", "commonLabels.owlmast\\.aisquad\\.com/run=run-x", "--set", "postgresql.provisionKeycloakDatabase=true", *UPGRADE)
        for d in by_kind(docs, "Deployment") + by_kind(docs, "Job"):
            self.assertEqual(d["metadata"]["labels"]["owlmast.aisquad.com/run"], "run-x")
            pod_labels = d["spec"]["template"]["metadata"]["labels"]
            if d["metadata"]["name"].endswith("-postgresql"):
                # the database pod template is the exception: a label edit must not restart PostgreSQL (ReviewCycle2Test)
                self.assertNotIn("owlmast.aisquad.com/run", pod_labels)
            else:
                self.assertEqual(pod_labels["owlmast.aisquad.com/run"], "run-x", d["metadata"]["name"])

    def test_gateway_api_route_is_optional_explicit_and_exclusive_with_ingress(self):
        """Owner steering: stable Gateway API routing as a first-class option; the Gateway itself is operator-supplied."""
        self.assertEqual(by_kind(render(), "HTTPRoute"), [])
        docs = render(*GATEWAY_API, "--set", "routing.gateway.enabled=true", "--set", "routing.gateway.parentRefs[0].name=shared-gw",
                      "--set", "routing.gateway.parentRefs[0].namespace=gateway-system", "--set", "routing.gateway.parentRefs[0].sectionName=https",
                      "--set", "routing.gateway.hostnames[0]=owl-mast.example.internal")
        routes = by_kind(docs, "HTTPRoute")
        self.assertEqual(len(routes), 1)
        route = routes[0]
        self.assertEqual(route["apiVersion"], "gateway.networking.k8s.io/v1")
        self.assertEqual(route["metadata"]["name"], "t-owl-mast")
        self.assertEqual(route["spec"]["parentRefs"], [{"group": "gateway.networking.k8s.io", "kind": "Gateway", "name": "shared-gw", "namespace": "gateway-system", "sectionName": "https"}])
        self.assertEqual(route["spec"]["hostnames"], ["owl-mast.example.internal"])
        self.assertEqual(len(route["spec"]["rules"]), 1)  # backend only while the frontend is disabled
        self.assertEqual([m["path"]["value"] for m in route["spec"]["rules"][0]["matches"]], ["/api"])
        self.assertEqual(route["spec"]["rules"][0]["backendRefs"], [{"name": "t-owl-mast-backend", "port": 8080}])
        self.assertEqual(by_kind(docs, "Ingress"), [])
        with_frontend = by_kind(render(*GATEWAY_API, "--set", "routing.gateway.enabled=true", "--set", "routing.gateway.parentRefs[0].name=shared-gw",
                                       "--set", "routing.gateway.hostnames[0]=owl-mast.example.internal",
                                       "--set", "frontend.enabled=true", "--set", "frontend.image.tag=0.0.1-shell"), "HTTPRoute")[0]
        self.assertEqual(with_frontend["spec"]["rules"][1]["matches"][0]["path"]["value"], "/")
        self.assertEqual(with_frontend["spec"]["rules"][1]["backendRefs"], [{"name": "t-owl-mast-frontend", "port": 80}])
        for sets, expected in (
            (("routing.gateway.enabled=true",), "requires at least one routing.gateway.parentRefs entry"),
            (("routing.gateway.enabled=true", "routing.gateway.parentRefs[0].name=gw", "routing.ingress.enabled=true", "routing.ingress.host=h"), "both true: choose one routing mechanism"),
        ):
            result = helm("template", "t", str(CHART), *GATEWAY_API, *[a for s_ in sets for a in ("--set", s_)])
            self.assertNotEqual(result.returncode, 0, sets); self.assertIn(expected, result.stderr, sets)
        for sets in (("routing.gateway.enabled=true", "routing.gateway.parentRefs[0].namespace=x"), ("routing.gateway.parentRefs[0].name=gw", "routing.gateway.parentRefs[0].listener=https")):
            result = helm("template", "t", str(CHART), *[a for s_ in sets for a in ("--set", s_)])
            self.assertNotEqual(result.returncode, 0, sets); self.assertIn("schema", result.stderr.lower(), sets)

    def test_no_ingress_or_frontend_by_default(self):
        docs = render()
        self.assertEqual(by_kind(docs, "Ingress"), [])
        self.assertEqual(by_kind(docs, "HTTPRoute"), [])
        self.assertNotIn("t-owl-mast-frontend", {d["metadata"]["name"] for d in docs})

    def test_examples_render_and_contain_no_credentials(self):
        examples = sorted(EXAMPLES.glob("*.yaml"))
        self.assertEqual([p.name for p in examples], [
            "bundled-bundled.yaml", "bundled-external.yaml", "external-bundled.yaml", "external-external.yaml",
        ])
        for example in examples:
            text = example.read_text()
            self.assertNotRegex(text.lower(), r"password:|token:", example.name)
            render("-f", str(example))


@unittest.skipIf(HELM is None, "helm binary required (OWLMAST_HELM)")
class ReviewFindingsTest(unittest.TestCase):
    """PR #109 post-merge review (5827094734): one negative or regression test per finding."""

    EXTERNAL_DB = ["database.bundled=false", "database.external.host=pg.example", "identity.keycloak.database.external.host=pg.example"]
    EXTERNAL_ID = ["identity.bundled=false"]

    def test_external_issuer_requires_https_unless_plaintext_is_opted_in(self):
        for issuer in ("http://idp/realms/x", "http://idp.example:8080/realms/x"):
            err = refused(*sets(*self.EXTERNAL_ID, f"identity.external.issuerUri={issuer}"))
            self.assertIn("identity.external.allowInsecureIssuer", err, issuer)
        for issuer in ("https://idp.example:8443/realms/x", "https://10.0.0.5/realms/x", "https://idp.example"):
            render(*sets(*self.EXTERNAL_ID, f"identity.external.issuerUri={issuer}"))
        docs = render(*sets(*self.EXTERNAL_ID, "identity.external.issuerUri=http://idp/realms/x", "identity.external.allowInsecureIssuer=true"))
        backend = {d["metadata"]["name"]: d for d in by_kind(docs, "Deployment")}["t-owl-mast-backend"]
        self.assertEqual(env_of(backend)["OWLMAST_IDENTITY_ISSUER_URI"]["value"], "http://idp/realms/x")
        for issuer in ("https://", "https:///realms/x", "http://", "https://idp/realms/x?a=b", "https://idp/realms/x#f", "https://user@idp/realms/x",
                       "https://:8443/realms/x", "https://idp:abc/realms/x", "https://idp:/realms/x", "https://a..b/realms/x", "https://-idp/realms/x"):
            err = refused(*sets(*self.EXTERNAL_ID, f"identity.external.issuerUri={issuer}", "identity.external.allowInsecureIssuer=true"))
            self.assertIn("identity.external.issuerUri", err, issuer)

    def test_weak_external_database_transport_needs_an_explicit_opt_in(self):
        for mode in ("disable", "allow", "prefer"):
            err = refused(*sets(*self.EXTERNAL_DB, f"database.external.sslMode={mode}"))
            self.assertIn("database.external.allowInsecureTransport", err, mode)
            err = refused(*sets(*self.EXTERNAL_DB, f"identity.keycloak.database.external.sslMode={mode}"))
            self.assertIn("identity.keycloak.database.external.allowInsecureTransport", err, mode)
        docs = render(*sets(*self.EXTERNAL_DB, "database.external.sslMode=disable", "database.external.allowInsecureTransport=true",
                            "identity.keycloak.database.external.sslMode=disable", "identity.keycloak.database.external.allowInsecureTransport=true"))
        deployments = {d["metadata"]["name"]: d for d in by_kind(docs, "Deployment")}
        self.assertTrue(env_of(deployments["t-owl-mast-backend"])["OWLMAST_DATABASE_JDBC_URL"]["value"].endswith("sslmode=disable"))
        self.assertTrue(env_of(deployments["t-owl-mast-keycloak"])["KC_DB_URL"]["value"].endswith("sslmode=disable"))
        render(*sets(*self.EXTERNAL_DB, "database.external.sslMode=require"))

    def test_principals_need_distinct_secrets(self):
        err = refused(*sets("database.existingSecret=shared", "postgresql.adminExistingSecret=shared"))
        self.assertIn("database.existingSecret", err); self.assertIn("postgresql.adminExistingSecret", err)
        err = refused(*sets("identity.keycloak.database.existingSecret=owl-mast-db"))
        self.assertIn("database.existingSecret and identity.keycloak.database.existingSecret", err)
        err = refused(*sets("identity.keycloak.bootstrapExistingSecret=owl-mast-postgres-admin"))
        self.assertIn("postgresql.adminExistingSecret and identity.keycloak.bootstrapExistingSecret", err)
        err = refused(*sets(*self.EXTERNAL_DB, "identity.keycloak.database.existingSecret=owl-mast-db"))
        self.assertIn("identity.keycloak.database.existingSecret", err)
        # Inactive references do not collide: an external issuer needs no Keycloak Secret at all.
        render(*sets(*self.EXTERNAL_ID, "identity.external.issuerUri=https://idp.example/realms/x", "identity.keycloak.database.existingSecret=owl-mast-db"))

    def test_keycloak_database_name_must_differ_on_a_shared_server(self):
        err = refused(*sets("identity.keycloak.database.name=owlmast"))
        self.assertIn("identity.keycloak.database.name and database.name", err)
        err = refused(*sets(*self.EXTERNAL_DB, "identity.keycloak.database.name=owlmast"))
        self.assertIn("same PostgreSQL server", err)
        # case and a trailing dot do not make it a different server; aliases (IP vs name) are not detected (documented)
        err = refused(*sets(*self.EXTERNAL_DB, "identity.keycloak.database.name=owlmast", "identity.keycloak.database.external.host=PG.example."))
        self.assertIn("same PostgreSQL server", err)
        # different servers (host or port) may use the same database name
        render(*sets(*self.EXTERNAL_DB, "identity.keycloak.database.name=owlmast", "identity.keycloak.database.external.host=kc-pg.example"))
        render(*sets(*self.EXTERNAL_DB, "identity.keycloak.database.name=owlmast", "identity.keycloak.database.external.port=5433"))

    def test_extra_env_cannot_override_validated_configuration(self):
        for name in ("OWLMAST_IDENTITY_ISSUER_URI", "OWLMAST_DATABASE_JDBC_URL", "owlmast_identity_issuer_uri", "SPRING_R2DBC_URL",
                     "MANAGEMENT_ENDPOINT_HEALTH_GROUP_READINESS_INCLUDE", "SERVER_PORT", "JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "owlmast.identity.issuer-uri",
                     "LOADER_PATH", "loader_main", "LD_PRELOAD", "LD_LIBRARY_PATH", "CLASSPATH"):
            err = refused(*sets(f"backend.extraEnv[0].name={name}", "backend.extraEnv[0].value=x"))
            self.assertIn("schema", err.lower(), name)
        docs = render(*sets("backend.extraEnv[0].name=LOGGING_LEVEL_ROOT", "backend.extraEnv[0].value=INFO"))
        backend = {d["metadata"]["name"]: d for d in by_kind(docs, "Deployment")}["t-owl-mast-backend"]
        self.assertEqual(env_of(backend)["LOGGING_LEVEL_ROOT"]["value"], "INFO")

    def test_routing_prefixes_are_pinned_to_what_the_artifacts_serve(self):
        for value, key in (("routing.apiPathPrefix=/v1", "routing.apiPathPrefix"), ("routing.apiPathPrefix=/", "routing.apiPathPrefix"),
                           ("routing.apiPathPrefix=/apix", "routing.apiPathPrefix"), ("routing.apiPathPrefix=/actuator", "routing.apiPathPrefix"),
                           ("routing.actuatorPathPrefix=/ops", "routing.actuatorPathPrefix"), ("routing.actuatorPathPrefix=/api", "routing.actuatorPathPrefix"),
                           ("routing.frontendPathPrefix=/ui", "routing.frontendPathPrefix"), ("routing.frontendPathPrefix=/api", "routing.frontendPathPrefix")):
            err = refused(*sets(value, "frontend.enabled=true", "frontend.image.tag=x"))
            self.assertIn(key, err, value); self.assertIn("rewrite", err, value)
        docs = render(*sets("routing.exposeActuator=true", "routing.actuatorPathPrefix=/actuator/health", "routing.ingress.enabled=true", "routing.ingress.host=owl.example"))
        paths = [p["path"] for p in by_kind(docs, "Ingress")[0]["spec"]["rules"][0]["http"]["paths"]]
        self.assertEqual(paths, ["/api", "/actuator/health"])

    def test_gateway_route_requires_the_httproute_capability(self):
        on = sets("routing.gateway.enabled=true", "routing.gateway.parentRefs[0].name=gw", "routing.gateway.hostnames[0]=owl.example")
        err = refused(*on)
        self.assertIn("gateway.networking.k8s.io/v1/HTTPRoute", err)
        err = refused("--api-versions", "gateway.networking.k8s.io/v1beta1/HTTPRoute", *on)
        self.assertIn("gateway.networking.k8s.io/v1/HTTPRoute", err)
        self.assertEqual(len(by_kind(render(*GATEWAY_API, *on), "HTTPRoute")), 1)
        self.assertEqual(by_kind(render(), "HTTPRoute"), [])  # disabled routing needs no capability

    def test_ingress_host_tls_and_annotations_are_validated(self):
        on = ["routing.ingress.enabled=true"]
        for host in ("https://x.example/", "x.example:443", "X.Example", "x.example/path", "-x.example"):
            err = refused(*sets(*on, f"routing.ingress.host={host}"))
            self.assertTrue("schema" in err.lower() or "routing.ingress.host" in err, (host, err))
        err = refused(*sets(*on, "routing.ingress.host=owl.example", "routing.ingress.tls[0].hosts[0]=other.example", "routing.ingress.tls[0].secretName=owl-tls"))
        self.assertIn("does not cover routing.ingress.host", err)
        err = refused(*sets(*on, "routing.ingress.host=owl.example", "routing.ingress.tls[0].hosts[0]=*.owl.example", "routing.ingress.tls[0].secretName=owl-tls"))
        self.assertIn("does not cover", err)  # a wildcard covers exactly one more label, not the apex
        base = sets(*on, "routing.ingress.host=owl.example")
        for bad in (sets("routing.ingress.tls[0].secretName=owl-tls"),                                         # TLS entry without hosts
                    sets("routing.ingress.tls[0].hosts[0]=owl.example", "routing.ingress.tls[0].secret=owl-tls"),  # unknown TLS key
                    ["--set-json", 'routing.ingress.annotations={"a":1}']):                                        # non-string annotation
            self.assertIn("schema", refused(*base, *bad).lower(), bad)
        docs = render(*sets(*on, "routing.ingress.host=a.owl.example", "routing.ingress.tls[0].hosts[0]=*.owl.example", "routing.ingress.tls[0].secretName=owl-tls",
                            "routing.ingress.annotations.example\\.com/x=y"))
        ingress = by_kind(docs, "Ingress")[0]
        self.assertEqual(ingress["spec"]["tls"], [{"hosts": ["*.owl.example"], "secretName": "owl-tls"}])
        self.assertEqual(ingress["metadata"]["annotations"], {"example.com/x": "y"})
        # 116/4543777463: a covering TLS entry without a Secret would make the controller serve its default certificate
        no_secret = sets(*on, "routing.ingress.host=owl.example", "routing.ingress.tls[0].hosts[0]=owl.example")
        self.assertIn("schema", refused(*no_secret).lower())
        self.assertIn("routing.ingress.tls[0].secretName is required", refused("--skip-schema-validation", *no_secret))
        render(*no_secret, *sets("routing.ingress.tls[0].secretName=owl-tls"))
        # 116/4543777547: a DNS label is at most 63 characters, for the host and for TLS hosts
        long_label = "a" * 64 + ".example"
        for bad in (sets(*on, f"routing.ingress.host={long_label}"),
                    sets(*on, "routing.ingress.host=owl.example", f"routing.ingress.tls[0].hosts[0]={long_label}", "routing.ingress.tls[0].secretName=owl-tls")):
            self.assertIn("schema", refused(*bad).lower(), bad)
            self.assertIn("not a valid", refused("--skip-schema-validation", *bad), bad)
        render(*sets(*on, "routing.ingress.host=" + "a" * 63 + ".example"))

    def test_provisioning_hook_is_refused_on_install_and_bounded_on_upgrade(self):
        err = refused(*sets("postgresql.provisionKeycloakDatabase=true"))
        self.assertIn("refused on install", err); self.assertIn("--is-upgrade", err)
        hook_docs = render(*UPGRADE, *sets("postgresql.provisionKeycloakDatabase=true"))
        job = by_kind(hook_docs, "Job")[0]
        # 116/4543777484, 109/4543776376: nothing of the hook outlives a successful run; a failed Job stays for diagnosis
        hook_cm = {d["metadata"]["name"]: d for d in by_kind(hook_docs, "ConfigMap")}["t-owl-mast-postgresql-provision-scripts"]
        for hook in (job, hook_cm):
            self.assertEqual(hook["metadata"]["annotations"]["helm.sh/hook-delete-policy"], "before-hook-creation,hook-succeeded", hook["kind"])
        self.assertNotIn("ttlSecondsAfterFinished", job["spec"])  # the delete policy owns cleanup; a TTL would also remove a failed Job
        self.assertLess(job["spec"]["activeDeadlineSeconds"], 300)  # below Helm's default 5m hook timeout
        self.assertEqual(job["spec"]["backoffLimit"], 0)
        self.assertEqual(job["spec"]["template"]["spec"]["restartPolicy"], "Never")
        env = job["spec"]["template"]["spec"]["containers"][0]["env"]
        self.assertIn({"name": "OWLMAST_APP_USERNAME", "valueFrom": {"secretKeyRef": {"name": "owl-mast-db", "key": "username"}}}, env)
        script = {d["metadata"]["name"]: d for d in by_kind(render(), "ConfigMap")}["t-owl-mast-postgresql-init"]["data"]["provision-keycloak.sh"]
        self.assertIn('getent hosts "$PGHOST"', script)
        attempts = int(re.search(r"OWLMAST_PG_WAIT_ATTEMPTS:-(\d+)", script).group(1))
        self.assertLess(attempts * (5 + 3), job["spec"]["activeDeadlineSeconds"])  # the whole wait fits inside the deadline

    def test_long_release_names_keep_every_generated_name_within_63_characters(self):
        release = "r" * 40
        for extra in ([*UPGRADE, *sets("postgresql.provisionKeycloakDatabase=true", "frontend.enabled=true", "frontend.image.tag=x", "routing.ingress.enabled=true", "routing.ingress.host=owl.example")],
                      [*GATEWAY_API, *sets("routing.gateway.enabled=true", "routing.gateway.parentRefs[0].name=gw", "routing.gateway.hostnames[0]=owl.example")],
                      sets(f"fullnameOverride={'f' * 63}")):
            result = helm("template", release, str(CHART), *extra)
            self.assertEqual(result.returncode, 0, result.stderr)
            docs = [d for d in yaml.safe_load_all(result.stdout) if d]
            keys = [(d["kind"], d["metadata"]["name"]) for d in docs]
            # the data claim keeps its 0.1.0 spelling (a claim name may have 253 characters); every other name fits a label
            self.assertTrue(all(len(name) <= (253 if kind == "PersistentVolumeClaim" else 63) for kind, name in keys), [n for _, n in keys if len(n) > 63])
            self.assertEqual(len(keys), len(set(keys)), keys)
            names = {d["metadata"]["name"] for d in docs}
            # references resolve to rendered objects
            pg = [d for d in docs if d["kind"] == "Deployment" and d["metadata"]["name"].endswith("-postgresql")][0]
            vols = {v["name"]: v for v in pg["spec"]["template"]["spec"]["volumes"]}
            self.assertIn(vols["init"]["configMap"]["name"], names)
            self.assertIn(vols["data"]["persistentVolumeClaim"]["claimName"], names)
            for d in docs:
                if d["kind"] == "Deployment" and d["metadata"]["name"].endswith("-backend"):
                    issuer = env_of(d)["OWLMAST_IDENTITY_ISSUER_URI"]["value"]
                    self.assertIn(issuer.split("//")[1].split(":")[0], names)

    def test_common_labels_cannot_use_chart_managed_keys(self):
        for key in ("app\\.kubernetes\\.io/name", "app\\.kubernetes\\.io/instance", "app\\.kubernetes\\.io/component", "helm\\.sh/chart"):
            err = refused(*sets(f"commonLabels.{key}=x"))
            self.assertIn("schema", err.lower(), key)
        render(*sets("commonLabels.team=owl", "commonLabels.tier=a-b_c.d"))
        for value in ("-bad", "bad-", "has space", "a/b", "x" * 64):
            err = refused(*sets(f"commonLabels.team={value}"))
            self.assertIn("schema", err.lower(), value)

    def test_external_hosts_cannot_inject_url_parts(self):
        for host in ("pg:5432/x?sslmode=disable", "pg/x", "pg?sslmode=disable", "pg&a=b", "user@pg", "pg:5432", "a..b", "a.-b", "a-.b", ".pg", "pg.."):
            for key in ("database.external.host", "identity.keycloak.database.external.host"):
                err = refused(*sets(*self.EXTERNAL_DB, f"{key}={host}"))
                self.assertIn("schema", err.lower(), (key, host))
        render(*sets(*self.EXTERNAL_DB, "database.external.host=10.0.0.12", "identity.keycloak.database.external.host=pg-1.data.example.internal."))

    def test_bundled_keycloak_without_realm_import_needs_an_acknowledgement(self):
        err = refused(*sets("identity.keycloak.importRealm=false"))
        self.assertIn("identity.keycloak.realmManagedByOperator=true", err)
        docs = render(*sets("identity.keycloak.importRealm=false", "identity.keycloak.realmManagedByOperator=true"))
        self.assertNotIn("t-owl-mast-keycloak-realm", {d["metadata"]["name"] for d in docs})
        kc = {d["metadata"]["name"]: d for d in by_kind(docs, "Deployment")}["t-owl-mast-keycloak"]
        self.assertNotIn("--import-realm", kc["spec"]["template"]["spec"]["containers"][0]["args"])

    def test_existing_claim_reinstall_mounts_the_kept_claim_and_renders_no_new_one(self):
        docs = render(*sets("postgresql.persistence.existingClaim=prior-data"))
        self.assertEqual(by_kind(docs, "PersistentVolumeClaim"), [])
        pg = {d["metadata"]["name"]: d for d in by_kind(docs, "Deployment")}["t-owl-mast-postgresql"]
        vols = {v["name"]: v for v in pg["spec"]["template"]["spec"]["volumes"]}
        self.assertEqual(vols["data"]["persistentVolumeClaim"]["claimName"], "prior-data")
        self.assertNotIn("is retained when this", notes(*sets("postgresql.persistence.existingClaim=prior-data")))
        self.assertIn("existingClaim=t-owl-mast-postgresql-data", notes())

    def test_backend_env_names_match_what_application_yaml_reads(self):
        """Both directions, for all four combinations: every ${OWLMAST_*} placeholder is set, nothing else OWLMAST_* is."""
        application = (REPO / "backend" / "src" / "main" / "resources" / "application.yaml").read_text()
        read = set(re.findall(r"\$\{(OWLMAST_[A-Z0-9_]+)", application))
        self.assertEqual(read, {"OWLMAST_DATABASE_R2DBC_URL", "OWLMAST_DATABASE_JDBC_URL", "OWLMAST_DATABASE_USERNAME", "OWLMAST_DATABASE_PASSWORD", "OWLMAST_IDENTITY_ISSUER_URI",
                                "OWLMAST_IDENTITY_ALLOW_INSECURE_ISSUER"})
        for combo, args in COMBINATIONS.items():
            backend = {d["metadata"]["name"]: d for d in by_kind(render(*args), "Deployment")}["t-owl-mast-backend"]
            rendered = {name for name in env_of(backend) if name.startswith("OWLMAST_")}
            self.assertEqual(rendered, read, combo)
            for name in read:
                e = env_of(backend)[name]
                self.assertTrue(e.get("value") or e.get("valueFrom"), (combo, name))

    def test_network_policies_isolate_the_bundled_dependencies(self):
        docs = render()
        policies = {d["metadata"]["name"]: d for d in by_kind(docs, "NetworkPolicy")}
        self.assertEqual(set(policies), {"t-owl-mast-postgresql", "t-owl-mast-keycloak"})
        def peers(policy):
            rule = policy["spec"]["ingress"]
            self.assertEqual(len(rule), 1)
            return [p["podSelector"]["matchLabels"]["app.kubernetes.io/component"] for p in rule[0]["from"]], rule[0]["ports"]
        pg = policies["t-owl-mast-postgresql"]
        self.assertEqual(pg["spec"]["policyTypes"], ["Ingress"])
        self.assertEqual(pg["spec"]["podSelector"]["matchLabels"], {"app.kubernetes.io/name": "owl-mast", "app.kubernetes.io/instance": "t", "app.kubernetes.io/component": "postgresql"})
        self.assertEqual(peers(pg), (["backend", "keycloak", "postgresql-provisioning"], [{"protocol": "TCP", "port": 5432}]))
        kc = policies["t-owl-mast-keycloak"]
        self.assertEqual(kc["spec"]["podSelector"]["matchLabels"]["app.kubernetes.io/component"], "keycloak")
        self.assertEqual(peers(kc), (["backend"], [{"protocol": "TCP", "port": 8080}]))
        # the selected labels are the ones the pods actually carry
        deployments = {d["metadata"]["name"]: d for d in by_kind(docs, "Deployment")}
        for comp in ("backend", "keycloak", "postgresql"):
            pod_labels = deployments[f"t-owl-mast-{comp}"]["spec"]["template"]["metadata"]["labels"]
            self.assertEqual(pod_labels["app.kubernetes.io/component"], comp)
        job = by_kind(render(*UPGRADE, *sets("postgresql.provisionKeycloakDatabase=true")), "Job")[0]
        self.assertEqual(job["spec"]["template"]["metadata"]["labels"]["app.kubernetes.io/component"], "postgresql-provisioning")
        # bundled database with an external issuer: no Keycloak policy, but the PostgreSQL policy already admits this
        # release's provisioning hook, because the upgrade that enables the identity bundle runs that hook under the
        # policy rendered before it (first-enable)
        ext_id = {d["metadata"]["name"]: d for d in by_kind(render(*COMBINATIONS["bundled-external"]), "NetworkPolicy")}
        self.assertEqual(set(ext_id), {"t-owl-mast-postgresql"})
        self.assertEqual(peers(ext_id["t-owl-mast-postgresql"])[0], ["backend", "keycloak", "postgresql-provisioning"])
        for peer in ext_id["t-owl-mast-postgresql"]["spec"]["ingress"][0]["from"]:
            self.assertEqual(peer["podSelector"]["matchLabels"]["app.kubernetes.io/instance"], "t")  # scoped to this release
        # 116/4543777575: an external database with the bundled Keycloak still isolates Keycloak (the policy is not
        # nested in the bundled-database block)
        ext_db = {d["metadata"]["name"]: d for d in by_kind(render(*COMBINATIONS["external-bundled"]), "NetworkPolicy")}
        self.assertEqual(set(ext_db), {"t-owl-mast-keycloak"})
        self.assertEqual(peers(ext_db["t-owl-mast-keycloak"]), (["backend"], [{"protocol": "TCP", "port": 8080}]))
        self.assertEqual(by_kind(render(*COMBINATIONS["external-external"]), "NetworkPolicy"), [])
        self.assertEqual(by_kind(render(*sets("networkPolicy.enabled=false")), "NetworkPolicy"), [])
        extra = render("--set-json", 'networkPolicy.keycloak.extraFrom=[{"namespaceSelector":{"matchLabels":{"kubernetes.io/metadata.name":"gateway-system"}}}]')
        kc = {d["metadata"]["name"]: d for d in by_kind(extra, "NetworkPolicy")}["t-owl-mast-keycloak"]
        self.assertEqual(kc["spec"]["ingress"][0]["from"][1], {"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "gateway-system"}}})
        self.assertIn("schema", refused("--set-json", 'networkPolicy.postgresql.extraFrom=[{"bogus":1}]').lower())

    def test_keycloak_and_frontend_carry_the_backend_hardening(self):
        docs = render(*sets("frontend.enabled=true", "frontend.image.tag=x"))
        deployments = {d["metadata"]["name"]: d for d in by_kind(docs, "Deployment")}
        for name in deployments:
            c = deployments[name]["spec"]["template"]["spec"]["containers"][0]
            self.assertTrue(c["securityContext"].get("readOnlyRootFilesystem") or name.endswith("-postgresql"), name)
            self.assertEqual(c["securityContext"]["capabilities"], {"drop": ["ALL"]}, name)
        fe = deployments["t-owl-mast-frontend"]["spec"]["template"]["spec"]
        self.assertEqual((fe["securityContext"]["runAsUser"], fe["securityContext"]["runAsGroup"]), (101, 101))
        self.assertIn("livenessProbe", fe["containers"][0])
        self.assertEqual({m["mountPath"] for m in fe["containers"][0]["volumeMounts"]}, {"/tmp", "/etc/nginx/conf.d"})
        self.assertTrue(all("emptyDir" in v for v in fe["volumes"]))
        kc = deployments["t-owl-mast-keycloak"]["spec"]["template"]["spec"]
        self.assertEqual({m["mountPath"] for m in kc["containers"][0]["volumeMounts"]}, {"/tmp", "/opt/keycloak/data", "/opt/keycloak/lib/quarkus", "/opt/keycloak/data/import"})
        seed = kc["initContainers"][0]
        self.assertEqual(seed["image"], kc["containers"][0]["image"])  # the build output comes from the very image that runs
        self.assertEqual(seed["volumeMounts"], [{"name": "quarkus", "mountPath": "/seed"}])
        self.assertIn("/opt/keycloak/lib/quarkus/. /seed/", seed["command"][-1])
        self.assertTrue(seed["securityContext"]["readOnlyRootFilesystem"])
        self.assertNotIn("KC_PROXY_HEADERS", env_of(deployments["t-owl-mast-keycloak"]))  # no proxy in front of a cluster-local Keycloak
        proxy = ["--set-json", 'networkPolicy.keycloak.extraFrom=[{"namespaceSelector":{"matchLabels":{"kubernetes.io/metadata.name":"gateway-system"}}}]']
        kc = {d["metadata"]["name"]: d for d in by_kind(render(*sets("identity.keycloak.proxyHeaders=xforwarded"), *proxy), "Deployment")}["t-owl-mast-keycloak"]
        self.assertEqual(env_of(kc)["KC_PROXY_HEADERS"]["value"], "xforwarded")
        # 116/4543777533: header trust needs the policy and a named proxy peer, or any pod could forge the headers
        for mode in ("xforwarded", "forwarded"):
            self.assertIn("networkPolicy.keycloak.extraFrom", refused(*sets(f"identity.keycloak.proxyHeaders={mode}")), mode)
            self.assertIn("networkPolicy.enabled=true", refused(*sets(f"identity.keycloak.proxyHeaders={mode}", "networkPolicy.enabled=false"), *proxy), mode)
        self.assertIn("schema", refused(*sets("identity.keycloak.proxyHeaders=yes")).lower())

    def test_notes_warn_while_the_backend_image_is_a_mutable_tag(self):
        self.assertIn("WARNING: the backend image owl-mast/backend:0.1.0 is referenced by a mutable tag", notes())
        self.assertNotIn("WARNING: the backend image", notes(*sets("backend.image.digest=sha256:" + "a" * 64)))
        self.assertNotIn("WARNING: the frontend image", notes())  # frontend disabled
        self.assertIn("WARNING: the frontend image owl-mast/frontend:0.0.1 is referenced by a mutable tag", notes(*sets("frontend.enabled=true", "frontend.image.tag=0.0.1")))
        self.assertNotIn("WARNING: the frontend image", notes(*sets("frontend.enabled=true", "frontend.image.tag=0.0.1", "frontend.image.digest=sha256:" + "b" * 64)))


IDENTITY_JAVA = REPO / "backend" / "src" / "main" / "java" / "com" / "aisquad" / "owlmast" / "access" / "adapter" / "identity"
GATEWAY_ON = ["routing.gateway.enabled=true", "routing.gateway.parentRefs[0].name=gw", "routing.gateway.hostnames[0]=owl.example"]
INGRESS_ON = ["routing.ingress.enabled=true", "routing.ingress.host=owl.example"]


def deployments_of(docs):
    return {d["metadata"]["name"]: d for d in by_kind(docs, "Deployment")}


@unittest.skipIf(HELM is None, "helm binary required (OWLMAST_HELM)")
class ReviewCycle1Test(unittest.TestCase):
    """2026-11-11 reviews 5865988027 (PR #109) and 5865989182 (PR #116): one test per finding, named by comment id."""

    EXTERNAL_DB = ReviewFindingsTest.EXTERNAL_DB
    EXTERNAL_ID = ["identity.bundled=false", "identity.external.issuerUri=https://idp.example/realms/x"]

    def test_java_tool_options_accept_only_jvm_tuning_flags(self):
        """116/4543777441: a system property, agent or argument file would override the validated issuer and database."""
        bad = ("-Dowlmast.identity.issuer-uri=http://attacker/realms/x", "-Dspring.r2dbc.url=r2dbc:postgresql://x/y", "-Dspring.config.additional-location=/tmp/x",
               "-javaagent:/tmp/agent.jar", "-agentlib:jdwp=transport=dt_socket", "-agentpath:/tmp/x.so", "@/tmp/argfile", "-XX:MaxRAMPercentage=75 -Dx=y",
               "-XX:VMOptionsFile=opts", "-XX:Flags=hotspotrc", "-XX:OnOutOfMemoryError=id", "-XX:OnError=id", "--add-opens=java.base/java.lang=ALL-UNNAMED",
               "-cp /tmp", "-jar /tmp/x.jar", "-Xbootclasspath/a:/tmp/x.jar", "-XX:HeapDumpPath=/tmp/x", "XX:+UseZGC",
               # cycle 2 (4544181092): a named allow-list, so file-loading and attach-enabling options are refused too
               "-XX:SharedArchiveFile=x", "-XX:AOTCache=x", "-XX:ErrorFile=x", "-XX:CompilerDirectivesFile=x", "-XX:+StartAttachListener",
               "-XX:+EnableDynamicAgentLoading", "-XX:+HeapDumpOnOutOfMemoryError", "-XX:MaxRAMPercentage=x", "-XX:+UnlockDiagnosticVMOptions",
               "-XX:MaxRAMPercentage=75 -XX:+StartAttachListener")
        for value in bad:
            # helm --set would split on commas and '='-free tokens are fine; --set-string keeps the value verbatim
            self.assertIn("schema", refused("--set-string", f"backend.javaToolOptions={value}").lower(), value)
            self.assertIn("backend.javaToolOptions", refused("--skip-schema-validation", "--set-string", f"backend.javaToolOptions={value}"), value)
        for value in ("", "-XX:MaxRAMPercentage=75", "-XX:MaxRAMPercentage=75.5 -Xms256m -Xmx512M -Xss1m", "-XX:+UseZGC -XX:-UseCompressedOops", "  -Xmx1g  ",
                      "-XX:MaxMetaspaceSize=256m -XX:ActiveProcessorCount=2 -XX:+UseG1GC -XX:MaxGCPauseMillis=200 -XX:+ExitOnOutOfMemoryError"):
            backend = deployments_of(render("--set-string", f"backend.javaToolOptions={value}"))["t-owl-mast-backend"]
            self.assertEqual(env_of(backend)["JAVA_TOOL_OPTIONS"]["value"], value)

    def test_api_prefix_is_exactly_what_the_backend_serves_and_the_frontend_calls(self):
        """116/4543777452: /api/v1 rendered, and every frontend call then returned 404."""
        for value in ("/api/v1", "/api/", "/api/v1.0~x", "/apix", "/"):
            err = refused(*sets(f"routing.apiPathPrefix={value}", "frontend.enabled=true", "frontend.image.tag=x"))
            self.assertIn("routing.apiPathPrefix", err, value); self.assertIn("exactly /api", err, value)
        docs = render(*sets("frontend.enabled=true", "frontend.image.tag=x", *INGRESS_ON))
        prefix = env_of(deployments_of(docs)["t-owl-mast-frontend"])["OWLMAST_API_PATH_PREFIX"]["value"]
        controller = (REPO / "backend/src/main/java/com/aisquad/owlmast/compatibility/adapter/web/CompatibilityController.java").read_text()
        served = re.search(r'String PATH = "([^"]+)"', controller).group(1)
        self.assertEqual(served, prefix + "/compatibility")  # what the shell calls is a path the backend serves
        routed = [p["path"] for p in by_kind(docs, "Ingress")[0]["spec"]["rules"][0]["http"]["paths"]]
        self.assertIn(prefix, routed)

    def test_a_prefix_the_frontend_image_refuses_never_reaches_it(self):
        """PR #119 walkthrough, risk 3: the image's start-up guard refuses the root, its own paths and the shell's
        pages; none of them may render, or the mistake would only show when the container starts."""
        guard = (REPO / "frontend/docker-entrypoint.d/16-owlmast-api-prefix.envsh").read_text()
        pages = re.search(r'^owlmast_shell_routes="([^"]+)"$', guard, re.M).group(1).split()
        self.assertGreaterEqual(len(pages), 5)
        self.assertNotIn("api", pages)  # the one prefix the chart renders must be one the image starts with
        refused_by_the_image = [
            "/", "/assets", "/assets/x", "/owlmast-config.json", "/api-compatibility.json", "/index.html", "/theme-boot.js",
            "/owl-mark.svg", *(f"/{page}" for page in pages), f"/{pages[0]}/x", "//evil.example", "/a/../b", "/a//b", "api",
        ]
        frontend = ("frontend.enabled=true", "frontend.image.tag=x")
        for value in refused_by_the_image:
            for skip in ((), ("--skip-schema-validation",)):
                err = refused(*skip, *sets(f"routing.apiPathPrefix={value}", *frontend))
                # a malformed value is refused by the path rule, a well-formed one by the pin to /api
                self.assertRegex(err, r"apiPathPrefix|routing path prefix", (value, skip))
        # the one value that reaches the image is the pinned one, in every routing mode, and nothing else is passed
        for args in (sets(*frontend), sets(*frontend, *INGRESS_ON), [*GATEWAY_API, *sets(*frontend, *GATEWAY_ON)]):
            container = deployments_of(render(*args))["t-owl-mast-frontend"]["spec"]["template"]["spec"]["containers"][0]
            self.assertEqual(container["env"], [{"name": "OWLMAST_API_PATH_PREFIX", "value": "/api"}])
            self.assertNotIn("envFrom", container)
        # there is no values path to another environment for the frontend container: the schema refuses the key, and
        # without the schema the template still renders only the pinned prefix
        override = ("frontend.extraEnv[0].name=OWLMAST_API_PATH_PREFIX", "frontend.extraEnv[0].value=/usage")
        self.assertIn("extraEnv", refused(*sets(*frontend, *override)))
        container = deployments_of(render("--skip-schema-validation", *sets(*frontend, *override)))["t-owl-mast-frontend"]["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(container["env"], [{"name": "OWLMAST_API_PATH_PREFIX", "value": "/api"}])

    def test_server_verifying_ssl_modes_fail_closed_until_a_ca_mount_exists(self):
        """116/4543777472: verify-ca/verify-full rendered and then crash-looped (no CA trust is mounted)."""
        for mode in ("verify-ca", "verify-full"):
            # the template refuses with or without the schema and names the deferral (cycle 3, 4544473172: the schema lets
            # the modes through so that this message, not a bare enum error, is what a normal render prints)
            self.assertIn(f"database.external.sslMode={mode} is refused", refused(*sets(*self.EXTERNAL_DB, f"database.external.sslMode={mode}")))
            self.assertIn(f"identity.keycloak.database.external.sslMode={mode} is refused", refused(*sets(*self.EXTERNAL_DB, f"identity.keycloak.database.external.sslMode={mode}")))
            err = refused("--skip-schema-validation", *sets(*self.EXTERNAL_DB, f"database.external.sslMode={mode}"))
            self.assertIn(f"database.external.sslMode={mode} is refused", err); self.assertIn("CA trust", err)
            err = refused("--skip-schema-validation", *sets(*self.EXTERNAL_DB, f"identity.keycloak.database.external.sslMode={mode}"))
            self.assertIn(f"identity.keycloak.database.external.sslMode={mode} is refused", err)
            # the opt-in for plaintext does not unlock a mode that cannot work
            refused(*sets(*self.EXTERNAL_DB, f"database.external.sslMode={mode}", "database.external.allowInsecureTransport=true"))
        for example in sorted(EXAMPLES.glob("external-*.yaml")):
            self.assertNotRegex(example.read_text(), r"sslMode:\s*verify-", example.name)

    def test_gateway_route_needs_hostnames_or_an_explicit_acknowledgement(self):
        """109/4543776272: an empty hostnames list attached the route to every hostname of the listener."""
        base = sets("routing.gateway.enabled=true", "routing.gateway.parentRefs[0].name=gw")
        err = refused(*GATEWAY_API, *base)
        self.assertIn("routing.gateway.hostnames is empty", err); self.assertIn("routing.gateway.allowAllListenerHostnames=true", err)
        route = by_kind(render(*GATEWAY_API, *base, *sets("routing.gateway.allowAllListenerHostnames=true")), "HTTPRoute")[0]
        self.assertNotIn("hostnames", route["spec"])
        route = by_kind(render(*GATEWAY_API, *sets(*GATEWAY_ON)), "HTTPRoute")[0]
        self.assertEqual(route["spec"]["hostnames"], ["owl.example"])
        self.assertIn("schema", refused(*GATEWAY_API, *base, *sets("routing.gateway.allowAllListenerHostnames=yes-please")).lower())

    def test_actuator_is_not_routed_unless_exposed_explicitly(self):
        """109/4543776281: /actuator was published on both routing mechanisms by default."""
        route = by_kind(render(*GATEWAY_API, *sets(*GATEWAY_ON)), "HTTPRoute")[0]
        self.assertEqual([m["path"]["value"] for r in route["spec"]["rules"] for m in r["matches"]], ["/api"])
        ingress = by_kind(render(*sets(*INGRESS_ON)), "Ingress")[0]
        self.assertEqual([p["path"] for p in ingress["spec"]["rules"][0]["http"]["paths"]], ["/api"])
        route = by_kind(render(*GATEWAY_API, *sets(*GATEWAY_ON, "routing.exposeActuator=true")), "HTTPRoute")[0]
        self.assertEqual([m["path"]["value"] for m in route["spec"]["rules"][0]["matches"]], ["/api", "/actuator"])
        ingress = by_kind(render(*sets(*INGRESS_ON, "routing.exposeActuator=true")), "Ingress")[0]
        self.assertEqual({p["path"]: p["backend"]["service"]["name"] for p in ingress["spec"]["rules"][0]["http"]["paths"]},
                         {"/api": "t-owl-mast-backend", "/actuator": "t-owl-mast-backend"})
        # the in-cluster probes do not depend on the route
        probes = deployments_of(render())["t-owl-mast-backend"]["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(probes["readinessProbe"]["httpGet"]["path"], "/actuator/health/readiness")

    def test_readiness_probe_timeout_exceeds_the_identity_discovery_timeout(self):
        """109/4543776297: the 1 s kubelet default was shorter than the indicator's own discovery timeout."""
        source = (IDENTITY_JAVA / "IdentityDiscoveryHealthIndicator.java").read_text()
        discovery_timeout = int(re.search(r"Duration TIMEOUT = Duration\.ofSeconds\((\d+)\)", source).group(1))
        backend = deployments_of(render())["t-owl-mast-backend"]["spec"]["template"]["spec"]["containers"][0]
        self.assertGreater(backend["readinessProbe"]["timeoutSeconds"], discovery_timeout)
        self.assertNotIn("timeoutSeconds", backend["livenessProbe"])  # liveness makes no outbound call
        custom = deployments_of(render(*sets("backend.probes.readiness.timeoutSeconds=9", "backend.probes.liveness.timeoutSeconds=2")))["t-owl-mast-backend"]["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual((custom["readinessProbe"]["timeoutSeconds"], custom["livenessProbe"]["timeoutSeconds"]), (9, 2))
        self.assertIn("schema", refused(*sets("backend.probes.readiness.timeoutSeconds=0")).lower())

    def test_init_checksum_follows_the_scripts_not_the_labels(self):
        """109/4543776333: every chart bump or commonLabels edit recreated the PostgreSQL pod."""
        import hashlib, json
        def checksum(*args):
            pg = [d for name, d in deployments_of(render(*args)).items() if name.endswith("-postgresql")][0]
            return pg["spec"]["template"]["metadata"]["annotations"]["checksum/init"]
        base = checksum()
        self.assertEqual(base, checksum(*sets("commonLabels.team=owl")))
        self.assertEqual(base, checksum(*sets("nameOverride=other")))  # app.kubernetes.io/name changes, the scripts do not
        whole = helm("template", "t", str(CHART), "-s", "templates/postgresql-init-configmap.yaml").stdout
        self.assertNotEqual(base, hashlib.sha256(whole.encode()).hexdigest())  # not the rendered object with its helm.sh/chart label
        data = yaml.safe_load(whole)["data"]
        # exactly the scripts: Helm's toJson of the data map (Go encoding: sorted keys, compact, HTML-safe escapes)
        encoded = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        encoded = encoded.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
        self.assertEqual(base, hashlib.sha256(encoded.encode()).hexdigest())

    def test_realm_change_rolls_keycloak(self):
        """109/4543776443: a changed identity.realm moved the backend's issuer while Keycloak never restarted to import it."""
        def annotations(*args):
            return deployments_of(render(*args))["t-owl-mast-keycloak"]["spec"]["template"]["metadata"]["annotations"]
        base = annotations()["checksum/realm"]
        self.assertNotEqual(base, annotations(*sets("identity.realm=other"))["checksum/realm"])
        self.assertEqual(base, annotations(*sets("commonLabels.team=owl"))["checksum/realm"])
        self.assertNotIn("checksum/realm", annotations(*sets("identity.keycloak.importRealm=false", "identity.keycloak.realmManagedByOperator=true")))

    def test_postgresql_probes_survive_socket_only_initialisation_and_cover_every_database(self):
        """109/4543776343: TCP startup/liveness probes failed during the socket-only first initialisation; readiness ignored Keycloak's database."""
        c = deployments_of(render())["t-owl-mast-postgresql"]["spec"]["template"]["spec"]["containers"][0]
        for probe in ("startupProbe", "livenessProbe"):
            command = c[probe]["exec"]["command"][-1]
            self.assertIn("-h /var/run/postgresql", command, probe); self.assertNotIn("127.0.0.1", command, probe)
        self.assertIn({"name": "run", "mountPath": "/var/run/postgresql"}, c["volumeMounts"])
        ready = c["readinessProbe"]["exec"]["command"][-1]
        self.assertEqual(ready.count("-h 127.0.0.1"), 1)  # TCP only: the socket-only initialisation server is never Ready
        self.assertIn('-d "$OWLMAST_APP_DATABASE"', ready)
        # cycle 2 (4544181074): readiness covers the application database only, never Keycloak's
        self.assertNotIn("KEYCLOAK", ready)
        # the variable the provisioning helper reads is set exactly when Keycloak is the bundled consumer
        self.assertIn("OWLMAST_KEYCLOAK_DATABASE", env_of(deployments_of(render())["t-owl-mast-postgresql"]))
        self.assertNotIn("OWLMAST_KEYCLOAK_DATABASE", env_of(deployments_of(render(*sets(*self.EXTERNAL_ID)))["t-owl-mast-postgresql"]))

    def test_bootstrap_admin_can_be_retired(self):
        """109/4543776353: the 'temporary' bootstrap admin stayed in the pod spec forever."""
        kc = deployments_of(render())["t-owl-mast-keycloak"]
        self.assertEqual(env_of(kc)["KC_BOOTSTRAP_ADMIN_PASSWORD"]["valueFrom"]["secretKeyRef"], {"name": "owl-mast-keycloak-bootstrap", "key": "password"})
        retired = render(*sets("identity.keycloak.bootstrapAdmin.enabled=false"))
        env = env_of(deployments_of(retired)["t-owl-mast-keycloak"])
        self.assertFalse([n for n in env if n.startswith("KC_BOOTSTRAP_ADMIN")])
        self.assertNotIn("owl-mast-keycloak-bootstrap", yaml.safe_dump_all(retired))  # the Secret is no longer referenced anywhere
        self.assertIn("identity.keycloak.bootstrapAdmin.enabled=false", notes())
        self.assertNotIn("temporary Keycloak bootstrap admin", notes(*sets("identity.keycloak.bootstrapAdmin.enabled=false")))
        self.assertIn("schema", refused(*sets("identity.keycloak.bootstrapAdmin.enabled=maybe")).lower())

    def test_duplicate_parent_check_treats_the_release_namespace_as_the_default(self):
        """109/4543776357: {name: gw} and {name: gw, namespace: <release namespace>} name the same Gateway."""
        same = sets(*GATEWAY_ON, "routing.gateway.parentRefs[1].name=gw", "routing.gateway.parentRefs[1].namespace=owl-ns")
        err = refused(*GATEWAY_API, "--namespace", "owl-ns", *same)
        self.assertIn("every reference to the same parent must set a distinct sectionName", err)
        self.assertEqual(len(by_kind(render(*GATEWAY_API, "--namespace", "elsewhere", *same), "HTTPRoute")[0]["spec"]["parentRefs"]), 2)  # a different Gateway
        distinct = sets(*GATEWAY_ON, "routing.gateway.parentRefs[0].sectionName=http", "routing.gateway.parentRefs[1].name=gw",
                        "routing.gateway.parentRefs[1].namespace=owl-ns", "routing.gateway.parentRefs[1].sectionName=https")
        self.assertEqual(len(by_kind(render(*GATEWAY_API, "--namespace", "owl-ns", *distinct), "HTTPRoute")[0]["spec"]["parentRefs"]), 2)

    def test_gateway_hostnames_refuse_ip_addresses(self):
        """109/4543776362: the Gateway API Hostname type forbids IP addresses; the upstream pattern does not enforce it."""
        for host in ("10.0.0.1", "192.168.1.250"):
            bad = sets("routing.gateway.enabled=true", "routing.gateway.parentRefs[0].name=gw", f"routing.gateway.hostnames[0]={host}")
            self.assertIn("schema", refused(*GATEWAY_API, *bad).lower(), host)
            self.assertIn("is an IP address", refused(*GATEWAY_API, "--skip-schema-validation", *bad), host)
        render(*GATEWAY_API, *sets("routing.gateway.enabled=true", "routing.gateway.parentRefs[0].name=gw", "routing.gateway.hostnames[0]=10.0.0.example"))

    def test_backend_rollout_never_runs_two_instances(self):
        """109/4543776391: the single-instance cap with the default RollingUpdate surged to two backends on every rollout."""
        backend = deployments_of(render())["t-owl-mast-backend"]
        self.assertEqual(backend["spec"]["strategy"], {"type": "Recreate"})
        self.assertEqual(backend["spec"]["replicas"], 1)
        self.assertIn("schema", refused(*sets("backend.replicas=2")).lower())

    def test_postgresql_volume_ownership_is_not_walked_on_every_start(self):
        """109/4543776402"""
        pod = deployments_of(render())["t-owl-mast-postgresql"]["spec"]["template"]["spec"]
        self.assertEqual(pod["securityContext"]["fsGroupChangePolicy"], "OnRootMismatch")
        self.assertEqual(pod["securityContext"]["fsGroup"], 999)

    def test_backend_image_needs_a_tag_or_a_digest(self):
        """109/4543776419: an empty tag and digest rendered `owl-mast/backend:`."""
        err = refused(*sets("backend.image.tag="))
        self.assertIn("backend.image.tag or backend.image.digest is required", err)
        image = deployments_of(render(*sets("backend.image.tag=", "backend.image.digest=sha256:" + "c" * 64)))["t-owl-mast-backend"]["spec"]["template"]["spec"]["containers"][0]["image"]
        self.assertEqual(image, "owl-mast/backend@sha256:" + "c" * 64)

    def test_service_ports_and_types_are_constrained(self):
        """109/4543776426: a string, 0 or a port above 65535 rendered and failed at the API server or at runtime."""
        for key in ("backend.service.port", "frontend.service.port", "postgresql.service.port", "identity.keycloak.service.port",
                    "identity.keycloak.service.managementPort", "backend.containerPort", "frontend.containerPort"):
            for value in ("0", "65536", "-1"):
                self.assertIn("schema", refused(*sets(f"{key}={value}")).lower(), (key, value))
            self.assertIn("schema", refused("--set-string", f"{key}=8080").lower(), key)
        for key in ("backend.service.type", "frontend.service.type"):
            self.assertIn("schema", refused(*sets(f"{key}=ExternalName")).lower(), key)
        self.assertIn("schema", refused(*sets("backend.service.nodePort=30000")).lower())
        docs = render(*sets("backend.service.port=65535", "postgresql.service.port=1", "backend.service.type=NodePort"))
        services = {d["metadata"]["name"]: d for d in by_kind(docs, "Service")}
        self.assertEqual(services["t-owl-mast-backend"]["spec"]["ports"][0]["port"], 65535)
        self.assertEqual(services["t-owl-mast-backend"]["spec"]["type"], "NodePort")
        self.assertIn("t-owl-mast-postgresql:1/", env_of(deployments_of(docs)["t-owl-mast-backend"])["OWLMAST_DATABASE_JDBC_URL"]["value"])

    def test_database_names_fit_postgresql_identifiers(self):
        """109/4543776430: PostgreSQL truncates identifiers to 63 bytes; the URLs would name a database that does not exist."""
        for key in ("database.name", "identity.keycloak.database.name"):
            self.assertIn("schema", refused(*sets(f"{key}={'d' * 64}")).lower(), key)
            render(*sets(f"{key}={'d' * 63}"))

    def test_keycloak_external_database_values_are_its_own(self):
        """109/4543776471: every earlier test gave Keycloak exactly the application's external values."""
        docs = render(*sets("database.bundled=false", "database.external.host=pg.example", "identity.keycloak.database.external.host=kc-pg.example",
                            "identity.keycloak.database.external.port=5433", "identity.keycloak.database.external.sslMode=disable",
                            "identity.keycloak.database.external.allowInsecureTransport=true"))
        d = deployments_of(docs)
        self.assertEqual(env_of(d["t-owl-mast-keycloak"])["KC_DB_URL"]["value"], "jdbc:postgresql://kc-pg.example:5433/keycloak?sslmode=disable")
        self.assertEqual(env_of(d["t-owl-mast-backend"])["OWLMAST_DATABASE_JDBC_URL"]["value"], "jdbc:postgresql://pg.example:5432/owlmast?sslmode=require")
        self.assertEqual(env_of(d["t-owl-mast-backend"])["OWLMAST_DATABASE_R2DBC_URL"]["value"], "r2dbc:postgresql://pg.example:5432/owlmast?sslMode=require")
        # and the reverse: the application's values never leak into Keycloak's URL
        docs = render(*sets("database.bundled=false", "database.external.host=pg.example", "database.external.port=6432", "database.external.sslMode=disable",
                            "database.external.allowInsecureTransport=true", "identity.keycloak.database.external.host=kc-pg.example"))
        self.assertEqual(env_of(deployments_of(docs)["t-owl-mast-keycloak"])["KC_DB_URL"]["value"], "jdbc:postgresql://kc-pg.example:5432/keycloak?sslmode=require")

    def test_route_backend_ports_are_the_service_ports(self):
        """109/4543776479: the backendRef port was only asserted where Service port and containerPort are both 8080."""
        docs = render(*GATEWAY_API, *sets(*GATEWAY_ON, "backend.service.port=9090", "frontend.service.port=8081", "frontend.enabled=true", "frontend.image.tag=x"))
        services = {d["metadata"]["name"]: d for d in by_kind(docs, "Service")}
        rules = by_kind(docs, "HTTPRoute")[0]["spec"]["rules"]
        self.assertEqual(rules[0]["backendRefs"], [{"name": "t-owl-mast-backend", "port": 9090}])
        self.assertEqual(rules[1]["backendRefs"], [{"name": "t-owl-mast-frontend", "port": 8081}])
        for rule in rules:
            ref = rule["backendRefs"][0]
            self.assertIn(ref["port"], [p["port"] for p in services[ref["name"]]["spec"]["ports"]])
        self.assertEqual(deployments_of(docs)["t-owl-mast-backend"]["spec"]["template"]["spec"]["containers"][0]["ports"][0]["containerPort"], 8080)

    def test_truncated_names_of_different_releases_do_not_collide(self):
        """116/4543777515: two long release names sharing the kept prefix rendered identical hook and claim names."""
        names = {}
        for release in ("a" * 40 + "-x", "a" * 40 + "-y"):
            result = helm("template", release, str(CHART), *UPGRADE, *sets("postgresql.provisionKeycloakDatabase=true"))
            self.assertEqual(result.returncode, 0, result.stderr)
            names[release] = {(d["kind"], d["metadata"]["name"]) for d in yaml.safe_load_all(result.stdout) if d}
            self.assertTrue(all(len(n) <= 63 for kind, n in names[release] if kind != "PersistentVolumeClaim"))
        first, second = names.values()
        self.assertEqual(first & second, set())
        self.assertTrue(any(n.endswith("-postgresql-provision-scripts") for _, n in first))
        # names that fit are unchanged (no hash), so existing short-named releases keep their objects
        short = {d["metadata"]["name"] for d in render(*UPGRADE, *sets("postgresql.provisionKeycloakDatabase=true"))}
        self.assertLessEqual({"t-owl-mast-postgresql-provision-scripts", "t-owl-mast-postgresql-data", "t-owl-mast-backend"}, short)

    def test_issuer_port_range_and_path_characters_match_what_the_backend_parses(self):
        """116/4543777509: ports 0 and 99999 and characters java.net.URI rejects rendered, then crash-looped the backend."""
        for issuer in ("https://idp.example:0/realms/x", "https://idp.example:99999/realms/x", "https://idp.example:65536", "https://idp.example:00443/realms/x",
                       'https://idp.example/realms/x"', "https://idp.example/realms/<x>", "https://idp.example/realms/{x}", "https://idp.example/realms/x|y",
                       "https://idp.example/realms/x^y", "https://idp.example/realms/x`y", "https://idp.example/realms/%zz", "https://idp.example/realms/x%2",
                       "https://idp.example/realms/a b"):
            err = refused("--set-string", f"identity.external.issuerUri={issuer}", *sets("identity.bundled=false", "identity.external.allowInsecureIssuer=true"))
            self.assertIn("identity.external.issuerUri", err, issuer)
        for issuer in ("https://idp.example:1/realms/x", "https://idp.example:65535/realms/x", "https://idp.example/realms/owl-mast/", "https://idp.example/a%20b/~x;y=1"):
            backend = deployments_of(render("--set-string", f"identity.external.issuerUri={issuer}", *sets("identity.bundled=false")))["t-owl-mast-backend"]
            self.assertEqual(env_of(backend)["OWLMAST_IDENTITY_ISSUER_URI"]["value"], issuer)  # verbatim, a trailing slash included

    def test_backend_is_told_when_a_plaintext_issuer_is_accepted(self):
        """116/4543777526: the https rule lived only in the chart; the backend now refuses http unless this flag is true."""
        def flag(*args):
            return env_of(deployments_of(render(*args))["t-owl-mast-backend"])["OWLMAST_IDENTITY_ALLOW_INSECURE_ISSUER"]["value"]
        self.assertEqual(flag(), "true")  # the cluster-local bundled Keycloak speaks http by design
        self.assertEqual(flag(*sets(*self.EXTERNAL_ID)), "false")
        self.assertEqual(flag(*sets("identity.bundled=false", "identity.external.issuerUri=http://idp/realms/x", "identity.external.allowInsecureIssuer=true")), "true")
        # a stale opt-in does not weaken an https issuer's backend beyond what was asked, and is still a boolean
        self.assertEqual(flag(*sets(*self.EXTERNAL_ID, "identity.external.allowInsecureIssuer=false")), "false")
        application = (REPO / "backend" / "src" / "main" / "resources" / "application.yaml").read_text()
        self.assertIn("allow-insecure-issuer: ${OWLMAST_IDENTITY_ALLOW_INSECURE_ISSUER:false}", application)

    def test_shared_external_server_warns_that_usernames_are_unchecked(self):
        """116/4543777500: distinct Secrets can still carry one username on an external server, where no script runs."""
        shared = notes(*sets(*self.EXTERNAL_DB))
        self.assertIn("WARNING: Keycloak and the application share the external PostgreSQL pg.example:5432", shared)
        self.assertIn("cannot read the usernames", shared)
        self.assertNotIn("share the external PostgreSQL", notes(*sets(*self.EXTERNAL_DB, "identity.keycloak.database.external.host=kc-pg.example")))
        self.assertNotIn("share the external PostgreSQL", notes())
        self.assertNotIn("share the external PostgreSQL", notes(*sets("database.bundled=false", "database.external.host=pg.example", *self.EXTERNAL_ID)))

    def test_bundled_postgresql_plaintext_is_stated(self):
        """109/4543776321: the bundled database has no TLS; that is stated instead of implied."""
        text = notes()
        self.assertIn("the bundled PostgreSQL has no TLS", text); self.assertIn("NetworkPolicy\n(rendered)", text)
        self.assertIn("DISABLED by networkPolicy.enabled=false", notes(*sets("networkPolicy.enabled=false")))
        self.assertNotIn("has no TLS", notes(*sets(*self.EXTERNAL_DB)))
        d = deployments_of(render())
        self.assertTrue(env_of(d["t-owl-mast-backend"])["OWLMAST_DATABASE_R2DBC_URL"]["value"].endswith("sslMode=disable"))
        self.assertTrue(env_of(d["t-owl-mast-keycloak"])["KC_DB_URL"]["value"].endswith("sslmode=disable"))

    def test_existing_claim_install_with_the_hook_names_the_real_provisioning_path(self):
        """116/4543777557: the refusal said a fresh install provisions Keycloak, which is false for a reused volume."""
        err = refused(*sets("postgresql.provisionKeycloakDatabase=true", "postgresql.persistence.existingClaim=prior-data"))
        self.assertIn('reuses the claim "prior-data"', err); self.assertIn("kubectl exec deploy/t-owl-mast-postgresql -- bash /owl-mast/provision-keycloak.sh", err)
        self.assertNotIn("<release>", err)  # the Deployment is named after the fullname, not the release
        self.assertNotIn("a fresh install provisions", err)
        # the helper the message points at is mounted in the PostgreSQL pod with Keycloak's credentials
        pg = deployments_of(render(*sets("postgresql.persistence.existingClaim=prior-data")))["t-owl-mast-postgresql"]
        self.assertIn({"name": "provisioning", "mountPath": "/owl-mast", "readOnly": True}, pg["spec"]["template"]["spec"]["containers"][0]["volumeMounts"])
        self.assertIn("OWLMAST_KEYCLOAK_PASSWORD", env_of(pg))

    def test_init_scripts_run_every_refusal_first_and_close_template1(self):
        """116 review body (init-configmap:104) and 109/4543776411, as rendered text; the Docker suite proves the behaviour."""
        data = {d["metadata"]["name"]: d for d in by_kind(render(), "ConfigMap")}["t-owl-mast-postgresql-init"]["data"]
        init, helper = data["10-owl-mast-databases.sh"], data["provision-keycloak.sh"]
        self.assertLess(init.index("bash /owl-mast/provision-keycloak.sh --preflight"), init.index("CREATE ROLE"))
        self.assertLess(helper.index('"--preflight"'), helper.index("CREATE ROLE"))
        self.assertGreater(helper.index('"--preflight"'), helper.index("is owned by $owner"))  # after the last refusal
        for script in (init, helper):
            self.assertIn("REVOKE ALL ON DATABASE template1 FROM PUBLIC;", script)

    def test_installation_doc_states_the_contracts_the_chart_cannot_enforce(self):
        """109/4543776435, 4543776449, 4543776321, 116/4543777495: documented limits, kept in step with the chart."""
        doc = " ".join((REPO / "docs" / "installation.md").read_text().split())
        for phrase in ("fixed at first initialisation", "`ALTER ROLE", "are immutable on the existing claim", "has no TLS",
                       "`routing.exposeActuator`", "`routing.gateway.allowAllListenerHostnames`",
                       "`identity.keycloak.bootstrapAdmin.enabled=false`"):
            self.assertIn(phrase, doc, phrase)
        self.assertNotIn("Qualified on 2026-11-07 for GitHub issue #21 on a disposable local Kind target;", doc)  # that was chart 0.1.0
        # E01-R-01: the qualification status is stated as it is, per revision, including what failed and what was not run.
        self.assertNotIn("qualification of chart 0.2.0 is pending", doc)
        for phrase in ("**The 2026-11-12 and 2026-11-13 runs, exactly.**", "What this does not amount to:", "**not run** on a cluster (render support only)",
                       "**not run** by the script (`frontend.enabled=false`)"):
            self.assertIn(phrase, doc, phrase)


ISSUER_REASONS = ("host", "port", "userinfo", "query")  # the refusal reasons a sample line may name (IdentityPropertiesTest.REASONS)


def parse_issuer_sample(line):
    """One line of the sample file as (kind, reason, issuer); the reason is '' for a line that is accepted."""
    head, sep, issuer = line.partition(" ")
    kind, colon, reason = head.partition(":")
    refusal = kind in ("refuse", "refuse-insecure")
    if not sep or not issuer or issuer.startswith(" ") or kind not in ("accept", "refuse", "chart-refuse", "accept-insecure", "refuse-insecure") \
            or refusal != (reason in ISSUER_REASONS) or (not refusal and colon):
        raise AssertionError(f"malformed sample line: {line}")
    return kind, reason, issuer


def issuer_samples():
    """(kind, reason, issuer) triples of the sample file the backend's IdentityPropertiesTest reads as well."""
    lines = (REPO / "backend" / "src" / "test" / "resources" / "identity" / "issuer-samples.txt").read_text().splitlines()
    return [parse_issuer_sample(line) for line in lines if line.strip() and not line.startswith("#")]


@unittest.skipIf(HELM is None, "helm binary required (OWLMAST_HELM)")
class ReviewCycle2Test(unittest.TestCase):
    """2026-11-12 review 5866484238 (PR #116 at 031da2c): one test per finding, named by comment id."""

    EXTERNAL_DB = ReviewFindingsTest.EXTERNAL_DB
    EXTERNAL_ID = ReviewCycle1Test.EXTERNAL_ID
    PROXY = ["identity.keycloak.proxyHeaders=xforwarded"]

    @staticmethod
    def container(docs, name):
        return deployments_of(docs)[name]["spec"]["template"]["spec"]["containers"][0]

    def test_postgresql_readiness_never_depends_on_keycloaks_database(self):
        """4544181074: a missing Keycloak database took PostgreSQL out of its Service, so the backend lost its database and
        the corrective pre-upgrade hook (pg_isready against the Service) could not reach the server."""
        for args in ([], sets("postgresql.persistence.existingClaim=prior-data"), [*UPGRADE, *sets("postgresql.provisionKeycloakDatabase=true")]):
            docs = render(*args)
            ready = self.container(docs, "t-owl-mast-postgresql")["readinessProbe"]["exec"]["command"][-1]
            self.assertEqual(ready, """psql -U "$POSTGRES_USER" -d "$OWLMAST_APP_DATABASE" -h 127.0.0.1 -Atc 'select 1' | grep -qx 1""")
        # the Service keeps the default endpoint rule: readiness alone decides, and it is the application database's
        service = [d for d in by_kind(render(), "Service") if d["metadata"]["name"] == "t-owl-mast-postgresql"][0]
        self.assertNotIn("publishNotReadyAddresses", service["spec"])
        doc = " ".join((REPO / "docs" / "installation.md").read_text().split())
        self.assertIn("PostgreSQL stays Ready and keeps serving the application database", doc)
        self.assertNotIn("its readiness probe covers every database the chart provisions", doc)

    def test_data_claim_keeps_the_chart_0_1_0_name(self):
        """4544181069: fullnames of 48-52 characters installed with chart 0.1.0 got a hashed claim name on upgrade, which
        attached a new empty volume and left the data behind. The claim is <fullname>-postgresql-data, as in 0.1.0."""
        def claim(release, *args):
            result = helm("template", release, str(CHART), *args)
            self.assertEqual(result.returncode, 0, result.stderr)
            docs = [d for d in yaml.safe_load_all(result.stdout) if d]
            pvc = by_kind(docs, "PersistentVolumeClaim")
            self.assertEqual(len(pvc), 1)
            pg = [d for d in by_kind(docs, "Deployment") if d["metadata"]["labels"]["app.kubernetes.io/component"] == "postgresql"][0]
            mounted = [v for v in pg["spec"]["template"]["spec"]["volumes"] if v["name"] == "data"][0]["persistentVolumeClaim"]["claimName"]
            self.assertEqual(mounted, pvc[0]["metadata"]["name"])
            self.assertEqual(pvc[0]["metadata"]["annotations"]["helm.sh/resource-policy"], "keep")
            return mounted, pg["metadata"]["name"]
        # every fullname chart 0.1.0 could install: up to 52 characters (its Service <fullname>-postgresql had to fit 63)
        for length in (1, 30, 47, 48, 49, 50, 51, 52):
            fullname = "f" * length
            self.assertEqual(claim("t", *sets(f"fullnameOverride={fullname}")), (f"{fullname}-postgresql-data", f"{fullname}-postgresql"), length)
        # the reviewed case: a 41-character release name gives the 50-character fullname <release>-owl-mast
        release = "r" * 41
        self.assertEqual(claim(release)[0], f"{release}-owl-mast-postgresql-data")
        # the literal chart 0.1.0 expression, kept here so that a change of either helper is caught
        legacy = (CHART / "templates" / "_helpers.tpl").read_text()
        self.assertIn('{{- define "owl-mast.postgresql.dataClaim" -}}{{ printf "%s-data" (include "owl-mast.postgresql.fullname" .) }}{{- end -}}', legacy)
        # longer fullnames could not install with 0.1.0: the claim follows the shortened, hashed PostgreSQL name
        mounted, deployment = claim("t", *sets(f"fullnameOverride={'f' * 60}"))
        self.assertEqual(mounted, f"{deployment}-data"); self.assertLessEqual(len(deployment), 63)
        self.assertIn(f"existingClaim={release}-owl-mast-postgresql-data", notes_for(release))

    def test_issuer_host_is_what_the_backend_parses(self):
        """4544181050 (re-raised PRRT_kwDOVjxExc62YN_3): idp.123, 1.2.3.999 and similar hosts rendered, and the backend then
        refused them at startup. The samples are the ones IdentityPropertiesTest runs through the backend."""
        samples = [s for s in issuer_samples() if s[0] in ("accept", "refuse", "chart-refuse")]  # the plaintext kinds: ReviewCycle3Test
        self.assertGreaterEqual(len([s for s in samples if s[0] == "refuse"]), 15); self.assertGreaterEqual(len([s for s in samples if s[0] == "accept"]), 10)
        for kind, _, issuer in samples:
            args = ["--set-string", f"identity.external.issuerUri={issuer}", *sets("identity.bundled=false")]
            if kind == "accept":
                backend = deployments_of(render(*args))["t-owl-mast-backend"]
                self.assertEqual(env_of(backend)["OWLMAST_IDENTITY_ISSUER_URI"]["value"], issuer)
            else:
                self.assertIn("identity.external.issuerUri", refused(*args), issuer)
        for issuer in ("https://idp.123/realms/x", "https://1.2.3.999/realms/x", "https://idp.example.1/realms/x", "https://a.b-c.9z/realms/x"):
            self.assertIn(("refuse", "host", issuer), samples)  # the four reviewed issuers
        java_test = (REPO / "backend/src/test/java/com/aisquad/owlmast/access/adapter/identity/IdentityPropertiesTest.java").read_text()
        self.assertIn("identity/issuer-samples.txt", java_test)  # the backend half of the comparison exists

    def test_common_labels_edit_does_not_touch_the_postgresql_pod_template(self):
        """4544181064 (re-raised PRRT_kwDOVjxExc62YNzu): commonLabels were copied into the pod template, so an edit recreated
        the database pod (strategy Recreate) although the annotation checksum was stable."""
        def template(name, *args):
            return [d for n, d in deployments_of(render(*args)).items() if n.endswith(name)][0]["spec"]["template"]
        base = template("-postgresql")
        self.assertEqual(base, template("-postgresql", *sets("commonLabels.team=owl")))
        self.assertEqual(base, template("-postgresql", *sets("commonLabels.team=owl", "commonLabels.unit=core")))
        self.assertEqual(set(base["metadata"]["labels"]), {"app.kubernetes.io/name", "app.kubernetes.io/instance", "app.kubernetes.io/component"})
        # the labels still reach the Deployment, the Service, the claim and the policy of the database
        labelled = render(*sets("commonLabels.team=owl"))
        for kind in ("Deployment", "Service", "PersistentVolumeClaim", "NetworkPolicy", "ConfigMap"):
            for d in by_kind(labelled, kind):
                self.assertEqual(d["metadata"]["labels"]["team"], "owl", (kind, d["metadata"]["name"]))
        # documented: the stateless pods do carry them, so an edit restarts those
        for name in ("-backend", "-keycloak"):
            self.assertEqual(template(name, *sets("commonLabels.team=owl"))["metadata"]["labels"]["team"], "owl")
        doc = " ".join((REPO / "docs" / "installation.md").read_text().split())
        self.assertIn("The PostgreSQL pod template carries no `commonLabels`", doc)

    def test_postgresql_exec_probes_carry_a_timeout(self):
        """4544181081: no timeoutSeconds was rendered, so the enforced 1 s kubelet default applied to sh + psql + grep."""
        c = self.container(render(), "t-owl-mast-postgresql")
        for probe in ("startupProbe", "livenessProbe", "readinessProbe"):
            self.assertEqual(c[probe]["timeoutSeconds"], 5, probe)
        custom = self.container(render(*sets("postgresql.probes.readiness.timeoutSeconds=9", "postgresql.probes.liveness.timeoutSeconds=7", "postgresql.probes.startup.timeoutSeconds=3")), "t-owl-mast-postgresql")
        self.assertEqual([custom[p]["timeoutSeconds"] for p in ("startupProbe", "livenessProbe", "readinessProbe")], [3, 7, 9])
        self.assertIn("schema", refused(*sets("postgresql.probes.readiness.timeoutSeconds=0")).lower())
        # the Keycloak probes share the definition: nothing by default, passed through when set
        kc = self.container(render(), "t-owl-mast-keycloak")
        self.assertNotIn("timeoutSeconds", kc["readinessProbe"])
        kc = self.container(render(*sets("identity.keycloak.probes.readiness.timeoutSeconds=4")), "t-owl-mast-keycloak")
        self.assertEqual(kc["readinessProbe"]["timeoutSeconds"], 4)

    def test_proxy_headers_need_a_peer_that_names_the_proxy(self):
        """4544181085: extraFrom [{namespaceSelector: {}}] satisfied the guard and admitted every pod of the cluster."""
        def peers(value):
            return ["--set-json", f"networkPolicy.keycloak.extraFrom={value}", *sets(*self.PROXY)]
        for value, named in (('[{"namespaceSelector":{}}]', "extraFrom[0].namespaceSelector is empty"),
                             ('[{"podSelector":{}}]', "extraFrom[0].podSelector is empty"),
                             ('[{"podSelector":{"matchLabels":{}}}]', "extraFrom[0].podSelector is empty"),
                             ('[{"namespaceSelector":{"matchExpressions":[]}}]', "extraFrom[0].namespaceSelector is empty"),
                             ('[{"namespaceSelector":{},"podSelector":{"matchLabels":{"app":"gw"}}}]', "extraFrom[0].namespaceSelector is empty"),
                             ('[{"podSelector":{"matchLabels":{"app":"gw"}}},{"podSelector":{}}]', "extraFrom[1].podSelector is empty"),
                             ('[{"ipBlock":{"cidr":"0.0.0.0/0"}}]', 'ipBlock.cidr "0.0.0.0/0" is refused'),
                             ('[{"ipBlock":{"cidr":"::/0"}}]', 'ipBlock.cidr "::/0" is refused'),
                             ('[{"ipBlock":{}}]', "ipBlock.cidr")):
            err = refused(*peers(value))
            self.assertIn("networkPolicy.keycloak." + named if named.startswith("extraFrom") else named, err, value)
            self.assertIn("identity.keycloak.proxyHeaders=xforwarded", err, value)
        # an empty peer: the schema refuses it, and so does the template on its own
        self.assertIn("schema", refused(*peers("[{}]")).lower())
        self.assertIn("networkPolicy.keycloak.extraFrom[0] is empty", refused("--skip-schema-validation", *peers("[{}]")))
        for value in ('[{"podSelector":{"matchLabels":{"app":"gw"}}}]',
                      '[{"namespaceSelector":{"matchLabels":{"kubernetes.io/metadata.name":"gateway-system"}},"podSelector":{"matchExpressions":[{"key":"app","operator":"In","values":["gw"]}]}}]',
                      '[{"ipBlock":{"cidr":"10.1.2.0/24"}}]'):
            docs = render(*peers(value))
            self.assertEqual(env_of(deployments_of(docs)["t-owl-mast-keycloak"])["KC_PROXY_HEADERS"]["value"], "xforwarded", value)
            policy = [d for d in by_kind(docs, "NetworkPolicy") if d["metadata"]["name"] == "t-owl-mast-keycloak"][0]
            self.assertEqual(len(policy["spec"]["ingress"][0]["from"]), 2)
        # without proxyHeaders the peers are the operator's own policy choice and are rendered as given
        render("--set-json", 'networkPolicy.keycloak.extraFrom=[{"namespaceSelector":{}}]')

    def test_extra_env_denylist_holds_without_the_schema(self):
        """4544181089: the denylist was schema-only, so --skip-schema-validation let JAVA_TOOL_OPTIONS back in through extraEnv,
        after the chart's own variable (the later duplicate wins in Kubernetes)."""
        for name in ("JAVA_TOOL_OPTIONS", "OWLMAST_IDENTITY_ALLOW_INSECURE_ISSUER", "OWLMAST_IDENTITY_ISSUER_URI", "owlmast_database_jdbc_url", "SPRING_R2DBC_URL",
                     "MANAGEMENT_SERVER_PORT", "SERVER_PORT", "LOADER_PATH", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS", "JAVA_OPTS", "CLASSPATH", "LD_PRELOAD",
                     "LD_LIBRARY_PATH", "PATH", "JAVA_HOME"):
            args = sets(f"backend.extraEnv[0].name={name}", "backend.extraEnv[0].value=x")
            self.assertIn("schema", refused(*args).lower(), name)
            err = refused("--skip-schema-validation", *args)
            self.assertIn(f'backend.extraEnv[0].name "{name}" is refused', err, name)
        for name, message in (("DB_PASSWORD", "looks like a credential"), ("api_token", "looks like a credential"), ("1BAD", "not a valid environment variable name"), ("A-B", "not a valid environment variable name")):
            self.assertIn(message, refused("--skip-schema-validation", *sets(f"backend.extraEnv[0].name={name}", "backend.extraEnv[0].value=x")), name)
        self.assertIn("backend.extraEnv[1].name", refused("--skip-schema-validation", *sets("backend.extraEnv[0].name=TZ", "backend.extraEnv[0].value=UTC", "backend.extraEnv[1].name=JAVA_TOOL_OPTIONS", "backend.extraEnv[1].value=-Dx=y")))
        for skip in ([], ["--skip-schema-validation"]):
            env = self.container(render(*skip, *sets("backend.extraEnv[0].name=TZ", "backend.extraEnv[0].value=UTC")), "t-owl-mast-backend")["env"]
            self.assertEqual(env[-1], {"name": "TZ", "value": "UTC"})
            self.assertEqual(len([e for e in env if e["name"] == "JAVA_TOOL_OPTIONS"]), 1)

    def test_java_tool_options_pattern_is_one_named_allow_list_in_schema_and_template(self):
        """4544181092: -XX:Name=value was open apart from four names. Both layers now use the same named allow-list."""
        import json
        helper = re.search(r'define "owl-mast.javaToolOptionsPattern" -}}\n(.*)\n', (CHART / "templates" / "_helpers.tpl").read_text()).group(1)
        schema = json.loads((CHART / "values.schema.json").read_text())["properties"]["backend"]["properties"]["javaToolOptions"]
        self.assertEqual(schema["pattern"], helper)
        self.assertNotIn("not", schema)  # no deny-list left: what is not named is refused
        self.assertNotIn("[A-Za-z0-9]+=", helper); self.assertNotIn("[+-][A-Za-z0-9]+", helper)  # no open -XX form
        comment = (CHART / "values.yaml").read_text()
        # three valued groups since cycle 3 (4544473258): sizes, percentages, counts
        valued, flags = "|".join(re.findall(r"XX:\(([A-Za-z0-9|]+)\)=", helper)), re.search(r"XX:\[\+-\]\(([A-Za-z0-9|]+)\)", helper).group(1)
        self.assertIn("MaxRAMPercentage", valued); self.assertIn("UseZGC", flags)
        for name in (valued + "|" + flags).split("|"):
            self.assertIn(name, comment, name)  # every accepted option is listed for the operator

    def test_notes_say_that_require_does_not_authenticate_the_server(self):
        """4544181102: NOTES recommended sslMode=require for an untrusted network without saying it leaves the server unauthenticated."""
        text = " ".join(notes().split())
        self.assertIn("sslMode=require encrypts the connection but does NOT authenticate the server", text)
        self.assertIn("an active interceptor can still pose as the database", text)
        self.assertIn("sslMode=verify-full with a mounted CA) is not shipped yet (deferred", text)
        # Deferred work is tracked as GitHub issues, not in a repository ledger: the CA trust mount for
        # sslMode=verify-ca|verify-full is #121; leftover of thread zl, TLS for the bundled PostgreSQL, is #124.
        guide = (REPO / "docs" / "installation.md").read_text()
        self.assertIn("https://github.com/gabrianoo/owl-mast/issues/121", guide)
        self.assertIn("https://github.com/gabrianoo/owl-mast/issues/124", guide)

    def test_readiness_period_is_longer_than_the_backends_cache_interval(self):
        """4544181114: the cache interval was tied to the probe period only by a literal 10 s in a Java test."""
        source = (IDENTITY_JAVA / "IdentityDiscoveryHealthIndicator.java").read_text()
        ttl = int(re.search(r"Duration CACHE_TTL = Duration\.ofSeconds\((\d+)\)", source).group(1))
        self.assertGreater(self.container(render(), "t-owl-mast-backend")["readinessProbe"]["periodSeconds"], ttl)
        for period in (1, ttl - 1, ttl):
            args = sets(f"backend.probes.readiness.periodSeconds={period}")
            self.assertIn("schema", refused(*args).lower(), period)
            err = refused("--skip-schema-validation", *args)
            self.assertIn(f"backend.probes.readiness.periodSeconds={period} is refused", err); self.assertIn(f"greater than {ttl}", err)
        accepted = self.container(render(*sets(f"backend.probes.readiness.periodSeconds={ttl + 1}")), "t-owl-mast-backend")
        self.assertEqual(accepted["readinessProbe"]["periodSeconds"], ttl + 1)
        # liveness and startup make no cached outbound call and stay free
        render(*sets("backend.probes.liveness.periodSeconds=1", "backend.probes.startup.periodSeconds=1"))

    def chart_with_0_1_0_values(self):
        """What `helm upgrade --reuse-values` renders from: the new templates and schema over the OLD chart's values (Helm
        replaces the new chart's defaults with the old release's coalesced values)."""
        import tempfile
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        chart = Path(tmp.name) / "owl-mast"
        shutil.copytree(CHART, chart)
        shutil.copy(REPO / "deploy" / "tests" / "data" / "values-0.1.0.yaml", chart / "values.yaml")
        return chart

    def test_reuse_values_from_chart_0_1_0_renders_with_the_new_defaults(self):
        """4544181120: --reuse-values keeps the 0.1.0 values without the new keys; the schema then refused the missing
        bootstrapAdmin, and the templates dereferenced nil."""
        chart = self.chart_with_0_1_0_values()
        old = yaml.safe_load((chart / "values.yaml").read_text())
        self.assertNotIn("bootstrapAdmin", old["identity"]["keycloak"]); self.assertNotIn("networkPolicy", old)  # really the 0.1.0 values
        def template(*args):
            result = helm("template", "t", str(chart), *UPGRADE, *args)
            self.assertEqual(result.returncode, 0, result.stderr)
            return [d for d in yaml.safe_load_all(result.stdout) if d]
        docs = template()
        d = deployments_of(docs)
        self.assertIn("KC_BOOTSTRAP_ADMIN_PASSWORD", env_of(d["t-owl-mast-keycloak"]))  # bootstrapAdmin.enabled defaults to true
        self.assertEqual({p["metadata"]["name"] for p in by_kind(docs, "NetworkPolicy")}, {"t-owl-mast-postgresql", "t-owl-mast-keycloak"})  # default on
        backend = d["t-owl-mast-backend"]["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(backend["readinessProbe"]["timeoutSeconds"], 5)  # still longer than the discovery timeout
        self.assertEqual(env_of(d["t-owl-mast-backend"])["OWLMAST_IDENTITY_ALLOW_INSECURE_ISSUER"]["value"], "true")
        pg = d["t-owl-mast-postgresql"]["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(pg["readinessProbe"]["timeoutSeconds"], 5)
        self.assertEqual(by_kind(docs, "PersistentVolumeClaim")[0]["metadata"]["name"], "t-owl-mast-postgresql-data")
        # the same with the routing and frontend values a 0.1.0 release could carry, and with the other three combinations
        routed = template(*sets("frontend.enabled=true", "frontend.image.tag=x", *INGRESS_ON))
        frontend = deployments_of(routed)["t-owl-mast-frontend"]["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(frontend["livenessProbe"]["httpGet"]["path"], "/")
        self.assertNotIn("/actuator", [p["path"] for p in by_kind(routed, "Ingress")[0]["spec"]["rules"][0]["http"]["paths"]])
        template(*GATEWAY_API, *sets("routing.gateway.enabled=true", "routing.gateway.parentRefs[0].name=gw", "routing.gateway.hostnames[0]=owl.example"))
        template(*sets("identity.bundled=false", "identity.external.issuerUri=https://idp.example/realms/owl-mast"))
        template(*sets("identity.keycloak.bootstrapAdmin.enabled=false"))
        # a 0.1.0 external database kept the old default sslMode=prefer: that is refused with the value named, not a nil error
        result = helm("template", "t", str(chart), *UPGRADE, *sets("database.bundled=false", "database.external.host=pg.example"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("database.external.sslMode=prefer can send database credentials in plaintext", result.stderr)
        template(*sets("database.bundled=false", "database.external.host=pg.example", "database.external.sslMode=require",
                       "identity.keycloak.database.external.host=kc.example", "identity.keycloak.database.external.sslMode=require"))
        # helm lint over the same values: the schema requires no key that chart 0.1.0 did not have
        self.assertEqual(helm("lint", str(chart)).returncode, 0)
        doc = " ".join((REPO / "docs" / "installation.md").read_text().split())
        self.assertIn("`--reuse-values`", doc); self.assertIn("`--reset-then-reuse-values`", doc)

    def test_schema_says_which_ssl_modes_the_chart_refuses(self):
        """4544181137: the schema listed verify-ca and verify-full without saying that the template always refuses them.
        Cycle 3 (4544473172) keeps them in the enum on purpose, so that the template's explanation is what the operator
        reads; the description states it, and an unknown mode is still a schema error."""
        import json
        schema = json.loads((CHART / "values.schema.json").read_text())
        self.assertEqual(schema["$defs"]["sslMode"]["enum"], ["disable", "allow", "prefer", "require", "verify-ca", "verify-full"])
        self.assertIn("CA trust", schema["$defs"]["sslMode"]["description"])
        self.assertIn("listed only so that the templates can refuse them with the reason", schema["$defs"]["sslMode"]["description"])
        self.assertIn("schema", refused(*sets(*self.EXTERNAL_DB, "database.external.sslMode=bogus")).lower())
        self.assertIn("must be one of disable, allow, prefer, require", refused("--skip-schema-validation", *sets(*self.EXTERNAL_DB, "database.external.sslMode=bogus")))

    def test_ingress_hosts_refuse_ip_addresses(self):
        """4544181145: routing.ingress.host=10.0.0.1 rendered, and the API server then rejected the Ingress mid-install."""
        for host in ("10.0.0.1", "192.168.1.10", "1.2.3.4"):
            args = sets("routing.ingress.enabled=true", f"routing.ingress.host={host}")
            self.assertIn("schema", refused(*args).lower(), host)
            err = refused("--skip-schema-validation", *args)
            self.assertIn(f'routing.ingress.host "{host}" is an IP address', err)
            tls = sets(*INGRESS_ON, f"routing.ingress.tls[0].hosts[0]={host}", "routing.ingress.tls[0].hosts[1]=owl.example", "routing.ingress.tls[0].secretName=owl-tls")
            self.assertIn("schema", refused(*tls).lower(), host)
            self.assertIn(f'routing.ingress.tls[0].hosts entry "{host}" is an IP address', refused("--skip-schema-validation", *tls))
        # DNS names with numeric labels are not IP addresses
        for host in ("10.0.0.1.nip.io", "1.2.3", "a.1.2.3.4", "1-2-3-4.example"):
            docs = render(*sets("routing.ingress.enabled=true", f"routing.ingress.host={host}"))
            self.assertEqual(by_kind(docs, "Ingress")[0]["spec"]["rules"][0]["host"], host)

    def test_install_without_a_bootstrap_admin_is_an_explicit_warned_choice(self):
        """4544181156: bootstrapAdmin.enabled=false on a fresh install starts Keycloak with no administrator. It is not refused
        (a reinstall on a retained volume, or an external Keycloak database, already holds one), but NOTES says so."""
        text = " ".join(notes(*sets("identity.keycloak.bootstrapAdmin.enabled=false")).split())
        self.assertIn("WARNING: identity.keycloak.bootstrapAdmin.enabled=false on an install: Keycloak starts WITHOUT a bootstrap administrator", text)
        self.assertNotIn("WITHOUT a bootstrap administrator", notes())
        self.assertNotIn("WITHOUT a bootstrap administrator", notes(*sets(*self.EXTERNAL_ID, "identity.keycloak.bootstrapAdmin.enabled=false")))
        self.assertIn("enabled=false on a FRESH install is an explicit", (CHART / "values.yaml").read_text())

    def test_bootstrap_secret_is_required_only_while_the_admin_is_enabled(self):
        """4544181161: the schema refused an empty bootstrapExistingSecret, so the helper's 'required only when enabled' branch
        was dead and a retired bootstrap admin could not clear the value."""
        err = refused(*sets("identity.keycloak.bootstrapExistingSecret="))
        self.assertIn("identity.keycloak.bootstrapExistingSecret is required when identity.bundled=true and identity.keycloak.bootstrapAdmin.enabled=true", err)
        docs = render(*sets("identity.keycloak.bootstrapExistingSecret=", "identity.keycloak.bootstrapAdmin.enabled=false"))
        self.assertFalse([n for n in env_of(deployments_of(docs)["t-owl-mast-keycloak"]) if n.startswith("KC_BOOTSTRAP_ADMIN")])
        render(*sets("identity.keycloak.bootstrapExistingSecret=", *self.EXTERNAL_ID))  # not referenced without the bundle
        self.assertIn("schema", refused(*sets("identity.keycloak.bootstrapExistingSecret=Not_A_Name")).lower())

    def test_retired_bootstrap_secret_leaves_the_distinct_secret_check(self):
        """4544181191: nothing exercised the rule that the bootstrap Secret joins the distinct-Secret check only while enabled."""
        for other in ("owl-mast-postgres-admin", "owl-mast-db", "owl-mast-keycloak-db"):
            same = [f"identity.keycloak.bootstrapExistingSecret={other}"]
            err = refused(*sets(*same))
            self.assertIn("identity.keycloak.bootstrapExistingSecret", err); self.assertIn("each principal needs its own Secret", err)
            docs = render(*sets(*same, "identity.keycloak.bootstrapAdmin.enabled=false"))  # a retired leftover value is not a principal
            self.assertFalse([n for n in env_of(deployments_of(docs)["t-owl-mast-keycloak"]) if n.startswith("KC_BOOTSTRAP_ADMIN")])

    def test_shared_external_server_warning_ignores_case_and_trailing_dot_and_respects_the_port(self):
        """4544181189: the warning's normalisation and its port clause were not pinned."""
        marker = "share the external PostgreSQL"
        for host in ("PG.example.", "pg.example.", "PG.EXAMPLE", "pg.example"):
            self.assertIn(marker, notes(*sets(*self.EXTERNAL_DB, f"identity.keycloak.database.external.host={host}")), host)
        self.assertIn(marker, notes(*sets("database.bundled=false", "database.external.host=PG.Example.", "identity.keycloak.database.external.host=pg.example")))
        # two servers on one host: a different port is a different server
        self.assertNotIn(marker, notes(*sets(*self.EXTERNAL_DB, "identity.keycloak.database.external.port=5433")))
        self.assertNotIn(marker, notes(*sets(*self.EXTERNAL_DB, "database.external.port=6432")))
        self.assertIn(marker, notes(*sets(*self.EXTERNAL_DB, "database.external.port=6432", "identity.keycloak.database.external.port=6432")))
        # the same rule decides the database-name refusal (AC3)
        same_name = "identity.keycloak.database.name=owlmast"
        self.assertIn("AC3", refused(*sets(*self.EXTERNAL_DB, "identity.keycloak.database.external.host=PG.example.", same_name)))
        render(*sets(*self.EXTERNAL_DB, "identity.keycloak.database.external.port=5433", same_name))

    def test_startup_probe_timeout_is_passed_through(self):
        """4544181197: the startupProbe.timeoutSeconds passthrough had no test."""
        self.assertNotIn("timeoutSeconds", self.container(render(), "t-owl-mast-backend")["startupProbe"])
        c = self.container(render(*sets("backend.probes.startup.timeoutSeconds=4")), "t-owl-mast-backend")
        self.assertEqual(c["startupProbe"]["timeoutSeconds"], 4)
        self.assertNotIn("timeoutSeconds", c["livenessProbe"]); self.assertEqual(c["readinessProbe"]["timeoutSeconds"], 5)

    def test_image_tags_cannot_be_blank(self):
        """Leftover of the cycle-1 thread on an empty image tag: a whitespace-only tag still rendered 'owl-mast/backend: '."""
        for tag in (" ", "  ", "a b", "-x", ".x", "x" * 129):
            args = ["--set-string", f"backend.image.tag={tag}"]
            self.assertIn("schema", refused(*args).lower(), repr(tag))
            self.assertIn("backend.image.tag", refused("--skip-schema-validation", *args), repr(tag))
            self.assertIn("frontend.image.tag", refused("--skip-schema-validation", "--set-string", f"frontend.image.tag={tag}", *sets("frontend.enabled=true")), repr(tag))
        for tag in ("0.1.0", "v1_2-rc.3", "x" * 128):
            self.assertEqual(self.container(render("--set-string", f"backend.image.tag={tag}"), "t-owl-mast-backend")["image"], f"owl-mast/backend:{tag}")

    def test_documents_name_objects_after_the_fullname(self):
        """Leftovers of fixed cycle-1 threads: <release>-postgresql in the docs, and the frontend comment about /actuator."""
        doc = (REPO / "docs" / "installation.md").read_text()
        self.assertNotIn("<release>-postgresql", doc)
        self.assertIn("<fullname>-postgresql", doc)
        nginx = (REPO / "frontend" / "nginx" / "default.conf.template").read_text()
        self.assertNotIn("routes `/api` and `/actuator`", nginx)
        flat = " ".join(doc.split())
        for phrase in ("deliberately named after another release's shortened name", "a trailing slash is part of the issuer", "publishedIssuer"):
            self.assertIn(phrase, flat, phrase)


@unittest.skipIf(HELM is None, "helm binary required (OWLMAST_HELM)")
class ReviewCycle3Test(unittest.TestCase):
    """2026-11-12 review 5866834124 (PR #116 at f52b3de): one test per finding, named by comment id."""

    EXTERNAL_DB = ReviewFindingsTest.EXTERNAL_DB
    EXTERNAL_ID = ReviewCycle1Test.EXTERNAL_ID
    PROXY = ReviewCycle2Test.PROXY
    container = staticmethod(ReviewCycle2Test.container)
    chart_with_0_1_0_values = ReviewCycle2Test.chart_with_0_1_0_values

    def test_readiness_period_rule_rests_on_a_cache_counted_from_the_request(self):
        """4544473160: the cache interval started when discovery ANSWERED (up to 3 s later), so a period of 6-8 s could read
        one cached result twice. The backend now counts the interval from the start of the request, which makes 'period
        greater than CACHE_TTL' sufficient; the chart rule is unchanged and its wording says what it rests on."""
        source = (IDENTITY_JAVA / "IdentityDiscoveryHealthIndicator.java").read_text()
        ttl = int(re.search(r"Duration CACHE_TTL = Duration\.ofSeconds\((\d+)\)", source).group(1))
        self.assertIn("remaining(cacheTtl, timed.startedNanos())", source)  # the interval left after the answer arrived
        self.assertNotIn(".cache(cacheTtl)", source)                        # not the answer-time interval
        java_test = (REPO / "backend/src/test/java/com/aisquad/owlmast/access/adapter/identity/IdentityDiscoveryHealthIndicatorTest.java").read_text()
        self.assertIn("void theCacheIntervalIsCountedFromTheStartOfTheDiscoveryRequest()", java_test)
        self.assertIn("StubIdentityProvider.startSlow(", java_test)
        err = refused("--skip-schema-validation", *sets(f"backend.probes.readiness.periodSeconds={ttl}"))
        self.assertIn("counted from the start of the discovery request", err)
        self.assertIn("two consecutive probes never read the result of the same request", err)
        self.assertEqual(self.container(render(*sets(f"backend.probes.readiness.periodSeconds={ttl + 1}")), "t-owl-mast-backend")["readinessProbe"]["periodSeconds"], ttl + 1)
        self.assertIn("counted from the", (CHART / "values.yaml").read_text())

    def test_proxy_headers_peer_must_name_the_proxy_positively(self):
        """4544473165: a namespaceSelector of key Exists selects every namespace, and 0.0.0.0/1 with 128.0.0.0/1 every IPv4
        address; both satisfied the guard."""
        def peers(value):
            return ["--set-json", f"networkPolicy.keycloak.extraFrom={value}", *sets(*self.PROXY)]
        exists = '{"matchExpressions":[{"key":"kubernetes.io/metadata.name","operator":"Exists"}]}'
        for value, named in (
                (f'[{{"namespaceSelector":{exists}}}]', "extraFrom[0].namespaceSelector names nothing"),
                (f'[{{"podSelector":{exists}}}]', "extraFrom[0].podSelector names nothing"),
                ('[{"podSelector":{"matchExpressions":[{"key":"app","operator":"NotIn","values":["x"]}]}}]', "extraFrom[0].podSelector names nothing"),
                ('[{"podSelector":{"matchExpressions":[{"key":"app","operator":"DoesNotExist"}]}}]', "extraFrom[0].podSelector names nothing"),
                ('[{"podSelector":{"matchExpressions":[{"key":"app","operator":"In","values":[]}]}}]', "extraFrom[0].podSelector names nothing"),
                ('[{"podSelector":{"matchExpressions":[{"key":"a","operator":"Exists"},{"key":"b","operator":"NotIn","values":["x"]}]}}]', "extraFrom[0].podSelector names nothing"),
                (f'[{{"podSelector":{{"matchLabels":{{"app":"gw"}}}},"namespaceSelector":{exists}}}]', "extraFrom[0].namespaceSelector names nothing"),
                (f'[{{"podSelector":{{"matchLabels":{{"app":"gw"}}}}}},{{"namespaceSelector":{exists}}}]', "extraFrom[1].namespaceSelector names nothing"),
                ('[{"ipBlock":{"cidr":"0.0.0.0/1"}},{"ipBlock":{"cidr":"128.0.0.0/1"}}]', 'extraFrom[0].ipBlock.cidr "0.0.0.0/1" is refused'),
                ('[{"ipBlock":{"cidr":"10.1.2.0/24"}},{"ipBlock":{"cidr":"128.0.0.0/1"}}]', 'extraFrom[1].ipBlock.cidr "128.0.0.0/1" is refused'),
                ('[{"ipBlock":{"cidr":"10.0.0.0/7"}}]', "prefix of at least /8"),
                ('[{"ipBlock":{"cidr":"::/1"}}]', "prefix of at least /32"),
                ('[{"ipBlock":{"cidr":"2001:db8::/31"}}]', "prefix of at least /32"),
                ('[{"ipBlock":{"cidr":"0.0.0.0/00"}}]', "prefix of at least /8"),
                ('[{"ipBlock":{"cidr":"::ffff:0.0.0.0/96"}}]', "must not embed a dotted IPv4 address"),
                ('[{"ipBlock":{"cidr":"::ffff:0:0/96"}}]', "must not be an IPv4-mapped"),
                ('[{"ipBlock":{"cidr":"::ffff:10.0.0.0/104"}}]', "must not embed a dotted IPv4 address"),
                ('[{"ipBlock":{"cidr":"10.0.0.1"}}]', "in CIDR form"),
                ('[{"ipBlock":{"cidr":"10.0.0.0/8/0"}}]', "in CIDR form")):
            err = refused(*peers(value))
            self.assertIn(named, err, value)
            self.assertIn("identity.keycloak.proxyHeaders=xforwarded", err, value)
        for value in ('[{"podSelector":{"matchExpressions":[{"key":"app","operator":"In","values":["gw"]},{"key":"tier","operator":"Exists"}]}}]',
                      '[{"namespaceSelector":{"matchLabels":{"kubernetes.io/metadata.name":"gateway-system"},"matchExpressions":[{"key":"x","operator":"DoesNotExist"}]}}]',
                      '[{"ipBlock":{"cidr":"10.0.0.0/8"}}]', '[{"ipBlock":{"cidr":"192.168.7.9/32"}}]', '[{"ipBlock":{"cidr":"2001:db8::/32"}}]',
                      '[{"ipBlock":{"cidr":"fd00:1::/64","except":["fd00:1::1/128"]}}]'):
            docs = render(*peers(value))
            self.assertEqual(env_of(deployments_of(docs)["t-owl-mast-keycloak"])["KC_PROXY_HEADERS"]["value"], "xforwarded", value)
        # without proxyHeaders the peers stay the operator's own policy choice
        render("--set-json", f'networkPolicy.keycloak.extraFrom=[{{"namespaceSelector":{exists}}},{{"ipBlock":{{"cidr":"0.0.0.0/1"}}}}]')
        self.assertIn("Exists", " ".join((REPO / "docs" / "installation.md").read_text().split()))

    def test_ssl_mode_refusal_explains_itself_on_a_normal_render(self):
        """4544473172: with verify-ca/verify-full out of the schema enum, a normal render (or a --reuse-values upgrade of a 0.1.0
        release that used verify-full) printed only Helm's enum error; the explanation needed --skip-schema-validation."""
        for path, extra in (("database.external", []), ("identity.keycloak.database.external", [])):
            for mode in ("verify-ca", "verify-full"):
                for skip in ([], ["--skip-schema-validation"]):
                    err = refused(*skip, *sets(*self.EXTERNAL_DB, f"{path}.sslMode={mode}", *extra))
                    self.assertIn(f"{path}.sslMode={mode} is refused: it needs a CA trust the chart does not mount yet", err, (path, mode, skip))
                    self.assertIn("Use require", err)
                    self.assertNotIn("values don't meet the specifications of the schema", err)
        # the upgrade the comment names: 0.1.0 values that carry verify-full, rendered as --reuse-values does
        chart = self.chart_with_0_1_0_values()
        result = helm("template", "t", str(chart), *UPGRADE, *sets("database.bundled=false", "database.external.host=pg.example", "database.external.sslMode=verify-full"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("database.external.sslMode=verify-full is refused: it needs a CA trust", result.stderr)
        doc = " ".join((REPO / "docs" / "installation.md").read_text().split())
        self.assertIn("names the mode and the reason", doc)

    def test_image_smoke_run_uses_the_environment_the_chart_renders(self):
        """4544473182, 4544473187, 4544473197: the smoke run set database URLs without the sslMode parameter the chart always
        renders and never the default (http issuer, opt-in true); its binding check only looked for absent lines, its endpoint
        check for a fixed count, and its header claimed every bean."""
        script = (REPO / "scripts" / "verify-backend-image.sh").read_text()
        function = script.split("smoke() {", 1)[1].split("\n}\n", 1)[0]
        set_by_script = dict(re.findall(r'-e "?([A-Z0-9_]+)=([^" ]*)"?', function))
        backend = deployments_of(render())["t-owl-mast-backend"]
        rendered = env_of(backend)
        self.assertEqual(set(set_by_script), set(rendered))  # exactly the variables of the default Deployment, no more, no fewer
        self.assertEqual(set_by_script["SERVER_PORT"], rendered["SERVER_PORT"]["value"])
        self.assertEqual(set_by_script["JAVA_TOOL_OPTIONS"], rendered["JAVA_TOOL_OPTIONS"]["value"])
        for name in ("OWLMAST_DATABASE_R2DBC_URL", "OWLMAST_DATABASE_JDBC_URL"):
            shape = lambda url: re.sub(r"//[^/]+/", "//HOST/", url)  # the host and port differ by design (closed loopback port)
            self.assertEqual(shape(set_by_script[name]), shape(rendered[name]["value"]), name)
        self.assertTrue(set_by_script["OWLMAST_DATABASE_R2DBC_URL"].endswith("?sslMode=disable"))
        self.assertTrue(set_by_script["OWLMAST_DATABASE_JDBC_URL"].endswith("?sslmode=disable"))
        # the default bundled install: an http issuer to the cluster-local Keycloak, with the opt-in
        issuer, allow = rendered["OWLMAST_IDENTITY_ISSUER_URI"]["value"], rendered["OWLMAST_IDENTITY_ALLOW_INSECURE_ISSUER"]["value"]
        self.assertTrue(issuer.startswith("http://")); self.assertEqual(allow, "true")
        starts = re.findall(r"^smoke (\S+) (true|false)$", script, re.M)
        self.assertEqual([(i.split(":")[0], a) for i, a in starts], [("https", "false"), ("http", "true"), ("http", "false")])
        self.assertEqual(starts[1][0].rsplit("/realms/", 1)[1], issuer.rsplit("/realms/", 1)[1])
        # a positive marker, logged by the identity configuration, and a control that the marker's absence is detectable
        marker = re.search(r'grep -qF "(Identity issuer \$2 \(plaintext issuer accepted: \$3\))"', script)
        self.assertIsNotNone(marker)
        configuration = (IDENTITY_JAVA / "IdentityConfiguration.java").read_text()
        self.assertIn('"Identity issuer {} (plaintext issuer accepted: {})"', configuration)
        self.assertIn("owlmast.identity.issuer-uri must use https", script)
        self.assertIn("Exposing [0-9]+ endpoints? beneath base path", script); self.assertNotIn("Exposing 1 endpoint", script)
        # the header claims what the run proves
        flat = " ".join(line.lstrip("# ") for line in script.splitlines())
        self.assertIn("creates the beans that PRECEDE database initialisation", flat)
        self.assertIn("NOT proven here (image-level proof, not runtime qualification): the beans Spring Boot creates only after database initialisation", flat)
        self.assertNotIn("creates its beans and stops", flat)
        ci = (REPO / ".github" / "workflows" / "ci.yml").read_text()
        self.assertIn("read-only-root start with the chart's environment, up to the first database connection", ci)

    def test_plaintext_issuer_samples_agree_with_the_backend(self):
        """4544473213, 4544473219: no shared sample covered the http branch, a refusal's reason was not checked, and a
        malformed line failed with an unrelated error."""
        samples = issuer_samples()
        insecure = [s for s in samples if s[0] == "accept-insecure"]; refuse_insecure = [s for s in samples if s[0] == "refuse-insecure"]
        self.assertGreaterEqual(len(insecure), 3); self.assertGreaterEqual(len(refuse_insecure), 4)
        malformed = "must be an absolute https:// URL with a host the backend can parse"
        for kind, reason, issuer in samples:
            base = ["--set-string", f"identity.external.issuerUri={issuer}", *sets("identity.bundled=false")]
            opted = [*base, *sets("identity.external.allowInsecureIssuer=true")]
            if kind == "accept-insecure":
                self.assertTrue(issuer.startswith("http://"), issuer)
                env = env_of(deployments_of(render(*opted))["t-owl-mast-backend"])
                self.assertEqual(env["OWLMAST_IDENTITY_ISSUER_URI"]["value"], issuer)
                self.assertEqual(env["OWLMAST_IDENTITY_ALLOW_INSECURE_ISSUER"]["value"], "true")
                err = refused(*base)  # the same issuer without the opt-in: the plaintext refusal, not the malformed one
                self.assertIn("uses plaintext http", err, issuer); self.assertNotIn(malformed, err, issuer)
            elif kind == "refuse-insecure":
                self.assertTrue(issuer.startswith("http://"), issuer)
                for args in (opted, base):  # malformed with or without the opt-in, and never mistaken for a plaintext refusal
                    err = refused(*args)
                    self.assertIn(malformed, err, issuer); self.assertNotIn("uses plaintext http", err, issuer)
            elif kind == "refuse":
                err = refused(*base)  # the chart has one message for every malformed issuer; the backend names the reason
                self.assertIn(malformed, err, issuer); self.assertIn(reason, ISSUER_REASONS)
        self.assertEqual({r for k, r, _ in samples if k == "refuse"}, set(ISSUER_REASONS))  # every reason has a sample
        java_test = (REPO / "backend/src/test/java/com/aisquad/owlmast/access/adapter/identity/IdentityPropertiesTest.java").read_text()
        for reason in ISSUER_REASONS:
            self.assertIn(f'"{reason}", "owlmast.identity.issuer-uri', java_test)  # the backend half checks the reason's message
        for kind in ("accept-insecure", "refuse-insecure"):
            self.assertIn(f'case "{kind}"', java_test)
        for line in ("accept", "accepthttps://idp.example", "refuse https://idp.123/x", "refuse:nonsense x", "accept:host https://idp.example",
                     "accept  https://idp.example", "accept ", "sometimes https://idp.example", "refuse:insecure http://idp.example"):
            with self.assertRaises(AssertionError) as raised:
                parse_issuer_sample(line)
            self.assertEqual(str(raised.exception), f"malformed sample line: {line}")
        self.assertEqual(parse_issuer_sample("refuse:port https://idp.example:0/x"), ("refuse", "port", "https://idp.example:0/x"))

    def test_bootstrap_admin_flag_is_true_or_false(self):
        """4544473231: with --skip-schema-validation the string False matched neither branch: no bootstrap admin, no Secret
        requirement and no NOTES warning."""
        for value in ("False", "TRUE", "no", "0", "yes", " false"):
            args = ["--skip-schema-validation", "--set-string", f"identity.keycloak.bootstrapAdmin.enabled={value}"]
            self.assertIn(f'identity.keycloak.bootstrapAdmin.enabled "{value}" must be a boolean: true or false', refused(*args), value)
            self.assertIn("schema", refused("--set-string", f"identity.keycloak.bootstrapAdmin.enabled={value}").lower(), value)
        # the two accepted spellings behave as the booleans do, also as strings
        for value, present in (("true", True), ("false", False)):
            for args in (sets(f"identity.keycloak.bootstrapAdmin.enabled={value}"), ["--skip-schema-validation", "--set-string", f"identity.keycloak.bootstrapAdmin.enabled={value}"]):
                env = env_of(deployments_of(render(*args))["t-owl-mast-keycloak"])
                self.assertEqual("KC_BOOTSTRAP_ADMIN_PASSWORD" in env, present, (value, args))
        # not evaluated where no Keycloak is rendered
        render("--skip-schema-validation", "--set-string", "identity.keycloak.bootstrapAdmin.enabled=False", *sets(*self.EXTERNAL_ID))

    def test_extra_env_refuses_every_dynamic_loader_variable(self):
        """4544473238: LD_AUDIT loads a library into java just as LD_PRELOAD does, and was not on the list."""
        for name in ("LD_AUDIT", "LD_PRELOAD", "LD_LIBRARY_PATH", "LD_DEBUG", "LD_BIND_NOW", "ld_audit", "Ld_Preload"):
            args = sets(f"backend.extraEnv[0].name={name}", "backend.extraEnv[0].value=x")
            self.assertIn("schema", refused(*args).lower(), name)
            err = refused("--skip-schema-validation", *args)
            self.assertIn(f'backend.extraEnv[0].name "{name}" is refused', err, name); self.assertIn("every LD_* variable", err)
        for name in ("LDAP_URL", "OLD_VALUE", "TZ", "FIELD_LD"):  # not loader variables
            for skip in ([], ["--skip-schema-validation"]):
                env = self.container(render(*skip, *sets(f"backend.extraEnv[0].name={name}", "backend.extraEnv[0].value=x")), "t-owl-mast-backend")["env"]
                self.assertEqual(env[-1], {"name": name, "value": "x"})
        self.assertIn("`LD_*`", (REPO / "docs" / "installation.md").read_text())

    def test_frontend_probe_timeouts_are_rendered(self):
        """4544473245: the shared probe schema accepted frontend timeoutSeconds, and the template dropped them."""
        on = sets("frontend.enabled=true", "frontend.image.tag=x")
        c = self.container(render(*on), "t-owl-mast-frontend")
        self.assertNotIn("timeoutSeconds", c["livenessProbe"]); self.assertNotIn("timeoutSeconds", c["readinessProbe"])
        c = self.container(render(*on, *sets("frontend.probes.readiness.timeoutSeconds=9", "frontend.probes.liveness.timeoutSeconds=4")), "t-owl-mast-frontend")
        self.assertEqual(c["readinessProbe"]["timeoutSeconds"], 9); self.assertEqual(c["livenessProbe"]["timeoutSeconds"], 4)
        c = self.container(render(*on, *sets("frontend.probes.readiness.timeoutSeconds=9")), "t-owl-mast-frontend")
        self.assertEqual(c["readinessProbe"]["timeoutSeconds"], 9); self.assertNotIn("timeoutSeconds", c["livenessProbe"])
        self.assertIn("schema", refused(*on, *sets("frontend.probes.readiness.timeoutSeconds=0")).lower())
        # a 0.1.0 release has no liveness block and no timeouts: nothing is rendered for them
        chart = self.chart_with_0_1_0_values()
        result = helm("template", "t", str(chart), *UPGRADE, *on)
        self.assertEqual(result.returncode, 0, result.stderr)
        old = self.container([d for d in yaml.safe_load_all(result.stdout) if d], "t-owl-mast-frontend")
        self.assertNotIn("timeoutSeconds", old["livenessProbe"]); self.assertNotIn("timeoutSeconds", old["readinessProbe"])

    def test_numeric_labels_that_are_not_an_address_are_dns_names(self):
        """4544473250: ^[0-9]+(\\.[0-9]+){3}$ also refused 999.1.1.1 and 256.0.0.1, which the API server takes as DNS names, and
        called them IP addresses."""
        import json
        helper = re.search(r'define "owl-mast.ipv4Pattern" -}}\n(.*)\n', (CHART / "templates" / "_helpers.tpl").read_text()).group(1)
        schema = json.loads((CHART / "values.schema.json").read_text())
        self.assertEqual(schema["$defs"]["ingressHost"]["not"]["pattern"], helper)
        self.assertNotIn("[0-9]+(\\\\.[0-9]+){3}", (CHART / "values.schema.json").read_text())  # no second, looser copy
        self.assertNotIn('"^[0-9]+', (CHART / "templates" / "_helpers.tpl").read_text())
        for host in ("999.1.1.1", "256.0.0.1", "1.2.3.256", "300.300.300.300", "1.2.3.4.5", "1.2.3"):
            for skip in ([], ["--skip-schema-validation"]):
                docs = render(*skip, *sets("routing.ingress.enabled=true", f"routing.ingress.host={host}"))
                self.assertEqual(by_kind(docs, "Ingress")[0]["spec"]["rules"][0]["host"], host)
                docs = render(*skip, *GATEWAY_API, "--set-string", f"routing.gateway.hostnames[0]={host}", *sets("routing.gateway.enabled=true", "routing.gateway.parentRefs[0].name=gw"))
                self.assertEqual(by_kind(docs, "HTTPRoute")[0]["spec"]["hostnames"], [host])
        # addresses, in every spelling the API server's parser reads as one (leading zeros included)
        for host in ("10.0.0.1", "255.255.255.255", "0.0.0.0", "010.0.0.1", "1.2.3.04", "001.002.003.004"):
            args = sets("routing.ingress.enabled=true", f"routing.ingress.host={host}")
            self.assertIn("schema", refused(*args).lower(), host)
            self.assertIn(f'routing.ingress.host "{host}" is an IP address', refused("--skip-schema-validation", *args))
            gw = [*GATEWAY_API, "--set-string", f"routing.gateway.hostnames[0]={host}", *sets("routing.gateway.enabled=true", "routing.gateway.parentRefs[0].name=gw")]
            self.assertIn("schema", refused(*gw).lower(), host)
            self.assertIn("is an IP address", refused("--skip-schema-validation", *gw), host)

    def test_java_tool_options_take_the_value_form_the_jvm_takes(self):
        """4544473258: every valued option took a decimal and a size suffix, so -XX:MaxRAMPercentage=75m rendered and the JVM
        then exited with 'Improperly specified VM option'."""
        bad = ("-XX:ParallelGCThreads=1.5g", "-XX:ActiveProcessorCount=2k", "-XX:MaxRAMPercentage=75m", "-XX:MaxRAMPercentage=75g", "-XX:InitialRAMPercentage=1.5k",
               "-XX:MinRAMPercentage=50M", "-XX:MaxMetaspaceSize=1.5g", "-XX:MaxDirectMemorySize=0.5g", "-XX:NewSize=1.5m", "-XX:MaxRAM=1.5g", "-XX:ParallelGCThreads=1.5",
               "-XX:MaxGCPauseMillis=200m", "-XX:NewRatio=2.5", "-XX:TieredStopAtLevel=1k", "-XX:ConcGCThreads=2G", "-XX:MaxRAMPercentage=75.", "-XX:MaxRAMPercentage=.5",
               "-XX:MaxRAMPercentage=75 -XX:ParallelGCThreads=1.5g")
        for value in bad:
            self.assertIn("schema", refused("--set-string", f"backend.javaToolOptions={value}").lower(), value)
            err = refused("--skip-schema-validation", "--set-string", f"backend.javaToolOptions={value}")
            self.assertIn("backend.javaToolOptions", err, value); self.assertIn("the value form the JVM takes", err, value)
        for value in ("-XX:MaxRAMPercentage=75", "-XX:MaxRAMPercentage=75.5 -XX:InitialRAMPercentage=50.0 -XX:MinRAMPercentage=25",
                      "-XX:MaxMetaspaceSize=256m -XX:MetaspaceSize=96M -XX:MaxDirectMemorySize=1g -XX:ReservedCodeCacheSize=240m -XX:G1HeapRegionSize=4m",
                      "-XX:SoftMaxHeapSize=2G -XX:MaxNewSize=512m -XX:NewSize=268435456 -XX:MaxRAM=4g",
                      "-XX:ActiveProcessorCount=2 -XX:ParallelGCThreads=4 -XX:ConcGCThreads=1 -XX:MaxGCPauseMillis=200 -XX:InitiatingHeapOccupancyPercent=45",
                      "-XX:MaxHeapFreeRatio=70 -XX:MinHeapFreeRatio=40 -XX:NewRatio=2 -XX:SurvivorRatio=8 -XX:TieredStopAtLevel=1"):
            backend = deployments_of(render("--set-string", f"backend.javaToolOptions={value}"))["t-owl-mast-backend"]
            self.assertEqual(env_of(backend)["JAVA_TOOL_OPTIONS"]["value"], value)
        helper = re.search(r'define "owl-mast.javaToolOptionsPattern" -}}\n(.*)\n', (CHART / "templates" / "_helpers.tpl").read_text()).group(1)
        sizes, percentages, counts = re.findall(r"XX:\(([A-Za-z0-9|]+)\)=", helper)
        self.assertIn("MaxMetaspaceSize", sizes.split("|")); self.assertEqual(set(percentages.split("|")), {"MaxRAMPercentage", "InitialRAMPercentage", "MinRAMPercentage"})
        self.assertIn("ParallelGCThreads", counts.split("|")); self.assertFalse(set(sizes.split("|")) & set(counts.split("|")))

    def test_keycloak_probe_timeouts_land_on_their_own_probe(self):
        """4544473263: only the readiness passthrough was tested; a dropped or mis-nested startup or liveness block passed."""
        kc = self.container(render(), "t-owl-mast-keycloak")
        for probe in ("startupProbe", "livenessProbe", "readinessProbe"):
            self.assertNotIn("timeoutSeconds", kc[probe], probe)  # nothing by default: the kubelet default applies
        kc = self.container(render(*sets("identity.keycloak.probes.startup.timeoutSeconds=3", "identity.keycloak.probes.liveness.timeoutSeconds=7",
                                         "identity.keycloak.probes.readiness.timeoutSeconds=9")), "t-owl-mast-keycloak")
        self.assertEqual([kc[p]["timeoutSeconds"] for p in ("startupProbe", "livenessProbe", "readinessProbe")], [3, 7, 9])
        for one, value in (("startup", 3), ("liveness", 7), ("readiness", 9)):
            kc = self.container(render(*sets(f"identity.keycloak.probes.{one}.timeoutSeconds={value}")), "t-owl-mast-keycloak")
            for probe in ("startup", "liveness", "readiness"):
                self.assertEqual(kc[f"{probe}Probe"].get("timeoutSeconds"), value if probe == one else None, (one, probe))

    def test_notes_state_the_exact_issuer_rule_for_an_external_issuer(self):
        """4544473269: no test rendered the external-issuer NOTES block."""
        text = " ".join(notes(*sets(*self.EXTERNAL_ID)).split())
        self.assertIn("NOTE: the backend becomes ready only when the issuer's discovery document publishes exactly https://idp.example/realms/x (a trailing slash is part of the issuer)", text)
        self.assertIn("the backend log names the published issuer", text)
        other = " ".join(notes(*sets("identity.bundled=false", "identity.external.issuerUri=https://sso.example:8443/realms/owl-mast/")).split())
        self.assertIn("publishes exactly https://sso.example:8443/realms/owl-mast/ (a trailing slash", other)
        for bundled in (notes(), notes(*sets(*self.EXTERNAL_DB))):
            self.assertNotIn("publishes exactly", bundled); self.assertNotIn("the backend log names the published issuer", bundled)

    def test_reuse_values_fallback_defaults_are_the_documented_ones(self):
        """4544473275: the 0.1.0-fixture test checked only the frontend liveness path and the PostgreSQL readiness timeout."""
        chart = self.chart_with_0_1_0_values()
        old = yaml.safe_load((chart / "values.yaml").read_text())
        self.assertNotIn("liveness", old["frontend"]["probes"])  # the keys really are absent from the 0.1.0 values
        for probe in ("startup", "liveness", "readiness"):
            self.assertNotIn("timeoutSeconds", old["postgresql"]["probes"][probe])
        result = helm("template", "t", str(chart), *UPGRADE, *sets("frontend.enabled=true", "frontend.image.tag=x"))
        self.assertEqual(result.returncode, 0, result.stderr)
        docs = [d for d in yaml.safe_load_all(result.stdout) if d]
        frontend = self.container(docs, "t-owl-mast-frontend")["livenessProbe"]
        self.assertEqual((frontend["httpGet"]["path"], frontend["periodSeconds"], frontend["failureThreshold"]), ("/", 15, 3))
        pg = self.container(docs, "t-owl-mast-postgresql")
        self.assertEqual([pg[p]["timeoutSeconds"] for p in ("startupProbe", "livenessProbe", "readinessProbe")], [5, 5, 5])
        # the same numbers are what the current values.yaml ships, so an upgraded and a fresh release agree
        new = yaml.safe_load((CHART / "values.yaml").read_text())
        self.assertEqual((new["frontend"]["probes"]["liveness"]["periodSeconds"], new["frontend"]["probes"]["liveness"]["failureThreshold"]), (15, 3))
        fresh = self.container(render(), "t-owl-mast-postgresql")
        self.assertEqual([fresh[p]["timeoutSeconds"] for p in ("startupProbe", "livenessProbe", "readinessProbe")], [5, 5, 5])

    def test_fullname_definition_covers_name_override_and_shortened_names(self):
        """4544473225: the <fullname> definition left out nameOverride, and for long fullnames the documented commands name
        objects that do not exist (the Deployment and the claim are shortened, hashed names)."""
        def names(release, *args):
            result = helm("template", release, str(CHART), *args)
            self.assertEqual(result.returncode, 0, result.stderr)
            docs = [d for d in yaml.safe_load_all(result.stdout) if d]
            pg = [d for d in by_kind(docs, "Deployment") if d["metadata"]["labels"]["app.kubernetes.io/component"] == "postgresql"][0]
            return pg["metadata"]["name"], by_kind(docs, "PersistentVolumeClaim")[0]["metadata"]["name"]
        # the definition, case by case, against what the chart renders
        self.assertEqual(names("r", *sets("fullnameOverride=fo"))[0], "fo-postgresql")
        self.assertEqual(names("r", *sets("nameOverride=app"))[0], "r-app-postgresql")
        self.assertEqual(names("my-app", *sets("nameOverride=app"))[0], "my-app-postgresql")  # the release name contains the name
        self.assertEqual(names("my-owl-mast")[0], "my-owl-mast-postgresql")
        self.assertEqual(names("r")[0], "r-owl-mast-postgresql")
        doc = " ".join((REPO / "docs" / "installation.md").read_text().split())
        for phrase in ("`<release>-<nameOverride>`", "the release name when it contains that name", "longer than 52 characters",
                       "use the Deployment and claim names that `NOTES` prints"):
            self.assertIn(phrase, doc, phrase)
        # a long fullname: the real names are not <fullname>-postgresql, and NOTES and the refusal print them
        long = "f" * 60
        deployment, claim = names("t", *sets(f"fullnameOverride={long}"))
        self.assertNotEqual(deployment, f"{long}-postgresql"); self.assertEqual(claim, f"{deployment}-data")
        printed = " ".join(notes(*sets(f"fullnameOverride={long}")).split())
        self.assertIn(f"The PersistentVolumeClaim {claim} is retained", printed); self.assertIn(f"existingClaim={claim}", printed)
        self.assertIn(f"Deployment {deployment}", printed)
        err = refused(*sets(f"fullnameOverride={long}", "postgresql.provisionKeycloakDatabase=true", "postgresql.persistence.existingClaim=prior"))
        self.assertIn(f"kubectl exec deploy/{deployment} ", err)


class ReviewCycle4Test(unittest.TestCase):
    """2026-11-12 review 5867158649 (PR #116 at 689e692): one test per finding, named by comment id."""

    PROXY = ReviewCycle2Test.PROXY

    def test_proxy_headers_ip_block_cannot_embed_an_ipv4_range(self):
        """4544747310: ::ffff:0.0.0.0/96 met the IPv6 /32 floor, and Go's net.ParseCIDR reads it as 0.0.0.0/0. An IPv6 range
        that embeds an IPv4 address is refused in every spelling, whatever its prefix."""
        def peers(*cidrs):
            value = "[" + ",".join(f'{{"ipBlock":{{"cidr":"{cidr}"}}}}' for cidr in cidrs) + "]"
            return ["--set-json", f"networkPolicy.keycloak.extraFrom={value}", *sets(*self.PROXY)]
        mapped = ("::ffff:0:0/96", "::FFFF:0:0/96", "::fFfF:0:0/96", "0:0:0:0:0:ffff:0:0/96", "0:0:0:0:0:FFFF:0:0/96",
                  "0000:0000:0000:0000:0000:ffff:0000:0000/96", "0000:0000:0000:0000:0000:FFFF:0000:0000/96", "0::ffff:0:0/96",
                  "::0:ffff:0:0/96", "0:0::ffff:0:0/96", "0:0:0:0:0:ffff::/96", "::ffff:a00:0/104", "::ffff:0a00:0000/104",
                  "::ffff:c0a8:709/128", "::ffff:0:0/128",
                  # IPv4-compatible (deprecated): the same embedding without the ffff group
                  "::a00:0/104", "::/96", "0:0:0:0:0:0:a00:0/104", "::1/128")
        for cidr in mapped:
            for skip in ([], ["--skip-schema-validation"]):
                err = refused(*skip, *peers(cidr))
                self.assertIn(f'extraFrom[0].ipBlock.cidr "{cidr}" is refused', err, cidr)
                self.assertIn("must not be an IPv4-mapped (::ffff:0:0/96) or IPv4-compatible (::/96) one", err, cidr)
                self.assertIn("write the proxy's IPv4 range itself", err, cidr)
                self.assertIn("identity.keycloak.proxyHeaders=xforwarded", err, cidr)
        dotted = ("::ffff:0.0.0.0/96", "::FFFF:0.0.0.0/96", "0:0:0:0:0:ffff:0.0.0.0/96", "0000:0000:0000:0000:0000:FFFF:0.0.0.0/96",
                  "::ffff:10.0.0.0/104", "::ffff:192.168.7.9/128", "::0.0.0.0/96", "::10.0.0.0/104", "64:ff9b::10.0.0.0/104")
        for cidr in dotted:
            err = refused(*peers(cidr))
            self.assertIn(f'extraFrom[0].ipBlock.cidr "{cidr}" is refused', err, cidr)
            self.assertIn("must not embed a dotted IPv4 address", err, cidr)
            self.assertIn("write the proxy's IPv4 range itself", err, cidr)
        # the entry is named by its index, next to a valid one
        self.assertIn('extraFrom[1].ipBlock.cidr "::ffff:0:0/96" is refused', refused(*peers("10.1.2.0/24", "::ffff:0:0/96")))
        # the prefix floor still answers first for a wide block
        self.assertIn("prefix of at least /32", refused(*peers("::ffff:0:0/24")))
        # an address that cannot be read group by group is refused, not guessed at
        for cidr in ("1::2::3/64", "1:2:3:4:5:6:7:8:9/64", "12345::/64", ":1::/64", "1:2:3:4:5:6:7::8/64", "1:2:3/64", "2001:db8:::/64",
                     "2001:db8::1:/64"):
            self.assertIn("not an IPv6 address of eight hexadecimal groups", refused(*peers(cidr)), cidr)
        # real IPv6 ranges, including ones that merely contain an ffff group or leading zero groups elsewhere
        for cidr in ("2001:db8:1234::/48", "fd00:10:244::/56", "2001:DB8::1/128", "2001:db8:0:0:0:ffff:0:0/96", "0:0:0:0:1:ffff:0:0/96",
                     "0:0:0:1:0:ffff:0:0/96", "1:2:3:4:5:6:7:8/128", "ffff::/32", "10.1.2.0/24", "192.168.7.9/32"):
            docs = render(*peers(cidr))
            self.assertEqual(env_of(deployments_of(docs)["t-owl-mast-keycloak"])["KC_PROXY_HEADERS"]["value"], "xforwarded", cidr)
            policy = [d for d in by_kind(docs, "NetworkPolicy") if d["metadata"]["name"] == "t-owl-mast-keycloak"][0]
            self.assertIn({"ipBlock": {"cidr": cidr}}, policy["spec"]["ingress"][0]["from"], cidr)
        # without proxyHeaders the peers stay the operator's own policy choice
        render("--set-json", 'networkPolicy.keycloak.extraFrom=[{"ipBlock":{"cidr":"::ffff:0.0.0.0/96"}}]')
        doc = " ".join((REPO / "docs" / "installation.md").read_text().split())
        self.assertIn("IPv4-mapped", doc)

    def test_notes_print_the_postgresql_claim_the_release_uses(self):
        """4544747330: only the Deployment half of the "Bundled PostgreSQL" line was asserted. The claim name, the existingClaim
        choice and the bundled-only guard were free to regress, and docs/installation.md sends operators to that line."""
        def line(*args):
            printed = [l for l in notes(*args).splitlines() if l.startswith("Bundled PostgreSQL:")]
            self.assertEqual(len(printed), 1, printed)
            return printed[0]
        def rendered(*args):
            docs = render(*args)
            pg = [d for d in by_kind(docs, "Deployment") if d["metadata"]["labels"]["app.kubernetes.io/component"] == "postgresql"][0]
            mounted = [v["persistentVolumeClaim"]["claimName"] for v in pg["spec"]["template"]["spec"]["volumes"] if "persistentVolumeClaim" in v]
            self.assertEqual(len(mounted), 1, mounted)
            return pg["metadata"]["name"], mounted[0], [d["metadata"]["name"] for d in by_kind(docs, "PersistentVolumeClaim")]
        # default: the chart's own claim, which is the one rendered and mounted
        deployment, mounted, claims = rendered()
        self.assertEqual((deployment, mounted, claims), ("t-owl-mast-postgresql", "t-owl-mast-postgresql-data", ["t-owl-mast-postgresql-data"]))
        self.assertEqual(line(), "Bundled PostgreSQL: Deployment t-owl-mast-postgresql, data claim t-owl-mast-postgresql-data")
        # existingClaim: the release's own claim is printed, never the chart's default name, and no claim is rendered
        existing = sets("postgresql.persistence.existingClaim=prior-data")
        deployment, mounted, claims = rendered(*existing)
        self.assertEqual((mounted, claims), ("prior-data", []))
        self.assertEqual(line(*existing), f"Bundled PostgreSQL: Deployment {deployment}, data claim prior-data")
        self.assertNotIn("t-owl-mast-postgresql-data", notes(*existing))
        self.assertNotIn("is retained when this", notes(*existing))
        # a shortened, hashed fullname: both names are the rendered ones
        long = sets("fullnameOverride=" + "f" * 60)
        deployment, mounted, claims = rendered(*long)
        self.assertNotEqual(deployment, "f" * 60 + "-postgresql"); self.assertEqual(claims, [mounted])
        self.assertEqual(line(*long), f"Bundled PostgreSQL: Deployment {deployment}, data claim {mounted}")
        deployment, mounted, _ = rendered(*long, *existing)
        self.assertEqual(line(*long, *existing), f"Bundled PostgreSQL: Deployment {deployment}, data claim prior-data")
        # an external database: no bundled Deployment and no claim, so no such line (and nothing about a retained claim)
        for combination in ("external-bundled", "external-external"):
            printed = notes(*COMBINATIONS[combination])
            self.assertNotIn("Bundled PostgreSQL:", printed, combination)
            self.assertNotIn("data claim", printed, combination)
            self.assertNotIn("PersistentVolumeClaim", printed, combination)
            self.assertNotIn("t-owl-mast-postgresql", printed, combination)
        # the line is not tied to the identity bundle
        self.assertEqual(line(*COMBINATIONS["bundled-external"]), "Bundled PostgreSQL: Deployment t-owl-mast-postgresql, data claim t-owl-mast-postgresql-data")

    def test_every_schema_copy_of_the_ipv4_pattern_is_the_helpers(self):
        """4544747354: the Gateway hostname copy of the IPv4 pattern was not compared with owl-mast.ipv4Pattern, so an edit to one
        copy could make the schema and the template disagree."""
        import json
        text = (CHART / "templates" / "_helpers.tpl").read_text()
        helper = re.search(r'define "owl-mast.ipv4Pattern" -}}\n(.*)\n', text).group(1)
        schema = json.loads((CHART / "values.schema.json").read_text())
        hostnames = schema["properties"]["routing"]["properties"]["gateway"]["properties"]["hostnames"]["items"]
        self.assertEqual(hostnames["not"]["pattern"], helper)
        self.assertEqual(schema["$defs"]["ingressHost"]["not"]["pattern"], helper)
        # every "not an address" rule in the schema is that expression: a third copy cannot be added without the helper
        found = []
        def walk(node, path):
            if isinstance(node, dict):
                if isinstance(node.get("not"), dict) and "pattern" in node["not"]:
                    found.append((path, node["not"]["pattern"]))
                for key, value in node.items():
                    walk(value, f"{path}/{key}")
            elif isinstance(node, list):
                for index, value in enumerate(node):
                    walk(value, f"{path}/{index}")
        walk(schema, "")
        addresses = [(path, pattern) for path, pattern in found if "25[0-5]" in pattern]
        self.assertEqual(sorted(path for path, _ in addresses), ["/$defs/ingressHost", "/properties/routing/properties/gateway/properties/hostnames/items"])
        for path, pattern in addresses:
            self.assertEqual(pattern, helper, path)
        # and the template reads the helper for both, with no literal copy of its own
        self.assertEqual(text.count('include "owl-mast.ipv4Pattern"'), 2)
        self.assertEqual(text.count("25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])\\.){3}0*"), 1)
        # the two rules agree, with and without the schema, on spellings on either side of the pattern
        for host, address in (("0.0.0.0", True), ("255.255.255.255", True), ("0255.1.1.1", True), ("1.1.1.0255", True), ("00.00.00.00", True),
                              ("256.1.1.1", False), ("1.1.1.256", False), ("1.1.1", False), ("1.1.1.1.1", False), ("2550.1.1.1", False)):
            gw = [*GATEWAY_API, "--set-string", f"routing.gateway.hostnames[0]={host}", *sets("routing.gateway.enabled=true", "routing.gateway.parentRefs[0].name=gw")]
            ing = [*sets("routing.ingress.enabled=true"), "--set-string", f"routing.ingress.host={host}"]
            for args in (gw, ing):
                if address:
                    self.assertIn("schema", refused(*args).lower(), host)
                    self.assertIn("is an IP address", refused("--skip-schema-validation", *args), host)
                else:
                    render(*args); render("--skip-schema-validation", *args)


@unittest.skipIf(HELM is None, "helm binary required (OWLMAST_HELM)")
class ReviewCycle6Test(unittest.TestCase):
    """PR #116 review 5867533032 (cycle 6)."""

    def bundled_issuer(self, *args):
        """(KC_HOSTNAME, backend issuer, NOTES issuer, Service port) of one bundled-Keycloak render."""
        docs = render(*args)
        d = deployments_of(docs)
        service = next(s for s in by_kind(docs, "Service") if s["metadata"]["name"] == "t-owl-mast-keycloak")
        printed = re.search(r"^Identity:\s+bundled Keycloak -> (\S+)$", notes(*args), re.M).group(1)
        return (env_of(d["t-owl-mast-keycloak"])["KC_HOSTNAME"]["value"], env_of(d["t-owl-mast-backend"])["OWLMAST_IDENTITY_ISSUER_URI"]["value"],
                printed, service["spec"]["ports"][0])

    def test_bundled_keycloak_on_port_80_publishes_the_issuer_the_backend_expects(self):
        """4545058435: Keycloak drops the scheme's default port from the issuer it publishes, so a rendered ':80' never matched."""
        hostname, issuer, printed, port = self.bundled_issuer(*sets("identity.keycloak.service.port=80"))
        self.assertEqual(hostname, "http://t-owl-mast-keycloak")
        self.assertEqual(issuer, "http://t-owl-mast-keycloak/realms/owl-mast")
        self.assertEqual(issuer, f"{hostname}/realms/owl-mast")
        self.assertEqual(printed, issuer)
        # the Service still listens on 80 and still targets the container's http port
        self.assertEqual((port["port"], port["targetPort"]), (80, "http"))
        # a values file carries the port as a float, --set-string as a string: the same result
        for args in (["--set-json", "identity.keycloak.service.port=80.0"], ["--skip-schema-validation", "--set-string", "identity.keycloak.service.port=80"]):
            self.assertEqual(self.bundled_issuer(*args)[:2], (hostname, issuer), args)

    def test_bundled_keycloak_on_another_port_keeps_it_in_both_values(self):
        """4545058435: every port but 80 stays, 443 included (the bundle is http, so 443 is not its default port)."""
        for value in (8080, 8081, 443, 8, 800, 65535):
            hostname, issuer, printed, port = self.bundled_issuer(*sets(f"identity.keycloak.service.port={value}"))
            self.assertEqual(hostname, f"http://t-owl-mast-keycloak:{value}", value)
            self.assertEqual(issuer, f"{hostname}/realms/owl-mast", value)
            self.assertEqual(printed, issuer, value)
            self.assertEqual(port["port"], value)

    def test_the_bundled_base_url_has_one_source(self):
        """4545058435: the two values came from two printf calls that could drift apart."""
        helpers = (CHART / "templates" / "_helpers.tpl").read_text()
        deployment = (CHART / "templates" / "keycloak-deployment.yaml").read_text()
        self.assertIn('value: {{ include "owl-mast.keycloak.baseUrl" . | quote }}', deployment)
        self.assertIn('printf "%s/realms/%s" (include "owl-mast.keycloak.baseUrl" .)', helpers)
        for text in (deployment, (CHART / "templates" / "NOTES.txt").read_text()):
            self.assertNotIn("keycloak.service.port", text)
        self.assertEqual(helpers.count("keycloak.service.port"), 1)

    def test_keycloak_is_replaced_not_rolled(self):
        """Kind qualification 2026-11-12 (E01-R-01): retiring the bootstrap admin changed the Keycloak pod for the first time. Under the
        default rolling update the new pod waited for a cluster with the old one that the NetworkPolicy does not allow, never became
        ready, and `helm upgrade --wait` timed out. The strategy stays RollingUpdate without surge: the same run showed that an
        existing release cannot be upgraded to `type: Recreate` (the server refuses it next to the defaulted rollingUpdate block).
        Review 5883535263: no surge does not stop the two pods overlapping, so Keycloak runs with a local cache and never waits for a cluster."""
        keycloak = deployments_of(render())["t-owl-mast-keycloak"]
        self.assertEqual(keycloak["spec"]["strategy"], {"type": "RollingUpdate", "rollingUpdate": {"maxSurge": 0, "maxUnavailable": 1}})
        self.assertEqual(keycloak["spec"]["replicas"], 1)
        policy = next(p for p in by_kind(render(), "NetworkPolicy") if p["metadata"]["name"] == "t-owl-mast-keycloak")
        ports = [p["port"] for rule in policy["spec"]["ingress"] for p in rule["ports"]]
        self.assertNotIn(7800, ports, "no cluster port is admitted, so two Keycloak pods must never try to form a cluster")
        # RollingUpdate without surge still lets the new pod start while the old one terminates (the controller does not
        # count a terminating pod), so the overlap is made harmless instead: a local cache never looks for a cluster.
        env = {e["name"]: e.get("value") for e in keycloak["spec"]["template"]["spec"]["containers"][0]["env"]}
        self.assertEqual(env.get("KC_CACHE"), "local")

    def test_the_frontend_container_port_is_fixed_at_the_port_the_image_listens_on(self):
        """E01-R-06 (retro B6): any port was accepted, but the image's nginx listens on 8080 only, so the probes failed."""
        listen = (REPO / "frontend" / "nginx" / "default.conf.template").read_text()
        self.assertRegex(listen, r"(?m)^\s*listen\s+8080;")
        frontend = ("frontend.enabled=true", "frontend.image.tag=0.0.1-shell")
        for value in ("8081", "80", "8443"):
            self.assertIn("schema", refused(*sets(*frontend, f"frontend.containerPort={value}")).lower(), value)
            err = refused("--skip-schema-validation", *sets(*frontend, f"frontend.containerPort={value}"))
            self.assertIn(f"frontend.containerPort {value} is refused", err, value)
            self.assertIn("listens on 8080 only", err, value)
        # Refused with the frontend disabled too: the value is wrong whenever it is enabled later.
        self.assertIn("schema", refused(*sets("frontend.containerPort=8081")).lower())
        docs = render(*sets(*frontend, "frontend.containerPort=8080", "frontend.service.port=8088"))
        container = deployments_of(docs)["t-owl-mast-frontend"]["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(container["ports"], [{"name": "http", "containerPort": 8080}])
        service = next(d for d in by_kind(docs, "Service") if d["metadata"]["name"] == "t-owl-mast-frontend")
        self.assertEqual(service["spec"]["ports"][0]["port"], 8088)

    def test_the_keycloak_network_policy_admits_the_container_port_whatever_the_service_port(self):
        """4545058435: a NetworkPolicy port is the pod's port; the Service port must not leak into it."""
        docs = render(*sets("identity.keycloak.service.port=80"))
        policy = next(p for p in by_kind(docs, "NetworkPolicy") if p["metadata"]["name"] == "t-owl-mast-keycloak")
        self.assertEqual([p["port"] for rule in policy["spec"]["ingress"] for p in rule["ports"]], [8080])
        container = deployments_of(docs)["t-owl-mast-keycloak"]["spec"]["template"]["spec"]["containers"][0]
        self.assertIn({"name": "http", "containerPort": 8080}, [{k: p[k] for k in ("name", "containerPort")} for p in container["ports"]])

    def test_postgresql_system_databases_are_refused_as_database_names(self):
        """4545058440: postgres, template0 and template1 rendered and failed only after initdb."""
        for key in ("database.name", "identity.keycloak.database.name"):
            for name in ("template0", "template1"):
                self.assertIn("schema", refused(*sets(f"{key}={name}")).lower(), (key, name))
                for spelling in (name, name.upper(), name.capitalize()):
                    err = refused("--skip-schema-validation", *sets(f"{key}={spelling}"))
                    self.assertIn(f'{key}="{spelling}" is refused: template0 and template1', err, (key, spelling))
                # an external server does not make a template database usable
                err = refused(*sets(*ReviewFindingsTest.EXTERNAL_DB, f"{key}={name}"))
                self.assertIn("schema", err.lower(), (key, name))
                err = refused("--skip-schema-validation", *sets(*ReviewFindingsTest.EXTERNAL_DB, f"{key}={name}"))
                self.assertIn(f'{key}="{name}" is refused', err, (key, name))
            err = refused(*sets(f"{key}=postgres"))
            self.assertIn(f'{key}="postgres" is refused with database.bundled=true', err, key)
            for spelling in ("POSTGRES", "Postgres"):
                self.assertIn("schema", refused(*sets(f"{key}={spelling}")).lower(), (key, spelling))
                err = refused("--skip-schema-validation", *sets(f"{key}={spelling}"))
                self.assertIn(f'{key}="{spelling}" is refused with database.bundled=true', err, (key, spelling))
            # an external server may use postgres: the chart runs no script there
            render(*sets(*ReviewFindingsTest.EXTERNAL_DB, f"{key}=postgres"))
            # names that only contain a reserved name are ordinary names
            for name in ("postgres_app", "template2", "template01", "my_template1"):
                render(*sets(f"{key}={name}"))

    def test_an_unused_keycloak_database_name_is_not_validated_by_the_templates(self):
        """4545058440: with an external issuer nothing reads identity.keycloak.database.name."""
        external_id = sets(*ReviewFindingsTest.EXTERNAL_ID, "identity.external.issuerUri=https://idp.example/realms/x")
        render(*external_id, *sets("identity.keycloak.database.name=postgres"))
        render("--skip-schema-validation", *external_id, *sets("identity.keycloak.database.name=template1"))
        self.assertIn('database.name="postgres" is refused', refused(*external_id, *sets("database.name=postgres")))


def notes_for(release, *args):
    result = helm("install", release, str(CHART), "--dry-run=client", *args)
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return result.stdout.split("NOTES:", 1)[1]


if __name__ == "__main__":
    unittest.main()
