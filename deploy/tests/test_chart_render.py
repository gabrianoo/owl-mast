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
            ("identity.keycloak.bootstrapExistingSecret=",),
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
            self.assertEqual(d["spec"]["template"]["metadata"]["labels"]["owlmast.aisquad.com/run"], "run-x", d["metadata"]["name"])
            self.assertEqual(d["metadata"]["labels"]["owlmast.aisquad.com/run"], "run-x")

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
            self.assertTrue(all(len(name) <= 63 for _, name in keys), [n for _, n in keys if len(n) > 63])
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
               "-cp /tmp", "-jar /tmp/x.jar", "-Xbootclasspath/a:/tmp/x.jar", "-XX:HeapDumpPath=/tmp/x", "XX:+UseZGC")
        for value in bad:
            # helm --set would split on commas and '='-free tokens are fine; --set-string keeps the value verbatim
            self.assertIn("schema", refused("--set-string", f"backend.javaToolOptions={value}").lower(), value)
            self.assertIn("backend.javaToolOptions", refused("--skip-schema-validation", "--set-string", f"backend.javaToolOptions={value}"), value)
        for value in ("", "-XX:MaxRAMPercentage=75", "-XX:MaxRAMPercentage=75.5 -Xms256m -Xmx512M -Xss1m", "-XX:+UseZGC -XX:-UseCompressedOops", "  -Xmx1g  "):
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

    def test_server_verifying_ssl_modes_fail_closed_until_a_ca_mount_exists(self):
        """116/4543777472: verify-ca/verify-full rendered and then crash-looped (no CA trust is mounted)."""
        for mode in ("verify-ca", "verify-full"):
            err = refused(*sets(*self.EXTERNAL_DB, f"database.external.sslMode={mode}"))
            self.assertIn(f"database.external.sslMode={mode} is refused", err); self.assertIn("CA trust", err)
            err = refused(*sets(*self.EXTERNAL_DB, f"identity.keycloak.database.external.sslMode={mode}"))
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
        self.assertEqual(ready.count("-h 127.0.0.1"), 2)  # TCP only: the socket-only initialisation server is never Ready
        self.assertIn('-d "$OWLMAST_APP_DATABASE"', ready); self.assertIn('-d "$OWLMAST_KEYCLOAK_DATABASE"', ready)
        self.assertIn('[ -z "${OWLMAST_KEYCLOAK_DATABASE:-}" ]', ready)
        # the variable the readiness guard reads is set exactly when Keycloak is the bundled consumer
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
        self.assertNotIn("bootstrap admin", notes(*sets("identity.keycloak.bootstrapAdmin.enabled=false")))
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
            self.assertTrue(all(len(n) <= 63 for _, n in names[release]))
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
        self.assertIn('reuses the claim "prior-data"', err); self.assertIn("bash /owl-mast/provision-keycloak.sh", err)
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
                       "qualification of chart 0.2.0 is pending", "`routing.exposeActuator`", "`routing.gateway.allowAllListenerHostnames`",
                       "`identity.keycloak.bootstrapAdmin.enabled=false`"):
            self.assertIn(phrase, doc, phrase)
        self.assertNotIn("Qualified on 2026-11-07 for GitHub issue #21 on a disposable local Kind target;", doc)  # that was chart 0.1.0


if __name__ == "__main__":
    unittest.main()
