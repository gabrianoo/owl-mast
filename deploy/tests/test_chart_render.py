"""Deterministic packaging checks for the owl-mast chart (OM-01.02-T1/T4).

Runs `helm lint` and `helm template` for the four bundled/external combinations and asserts the
fail-closed validations. Requires Helm 4.x; set OWLMAST_HELM to the binary (scripts/verify-install-package.sh
fetches a checksum-verified Helm 4.3.1 when none is available).
"""

import os
import shutil
import subprocess
import unittest
from pathlib import Path

import yaml  # PyYAML is bundled with the Python used in CI (setup-python) and this repository's checks.

REPO = Path(__file__).resolve().parents[2]
CHART = REPO / "deploy" / "helm" / "owl-mast"
EXAMPLES = CHART / "examples"
HELM = os.environ.get("OWLMAST_HELM") or shutil.which("helm")

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
        self.assertEqual(env_of(deployments["t-owl-mast-backend"])["OWLMAST_DATABASE_JDBC_URL"]["value"], "jdbc:postgresql://pg.example:5432/owlmast?sslmode=prefer")
        self.assertEqual(env_of(deployments["t-owl-mast-keycloak"])["KC_DB_URL"]["value"], "jdbc:postgresql://pg.example:5432/keycloak?sslmode=prefer")

    def test_external_identity_omits_keycloak_but_keeps_issuer(self):
        docs = render(*COMBINATIONS["bundled-external"])
        names = {d["metadata"]["name"] for d in docs}
        self.assertNotIn("t-owl-mast-keycloak", names)
        self.assertNotIn("t-owl-mast-keycloak-realm", names)
        backend = {d["metadata"]["name"]: d for d in by_kind(docs, "Deployment")}["t-owl-mast-backend"]
        self.assertEqual(env_of(backend)["OWLMAST_IDENTITY_ISSUER_URI"]["value"], "https://idp.example/realms/owl-mast")

    def test_external_external_renders_only_the_backend(self):
        docs = render(*COMBINATIONS["external-external"])
        self.assertEqual([d["metadata"]["name"] for d in by_kind(docs, "Deployment")], ["t-owl-mast-backend"])
        self.assertEqual(by_kind(docs, "PersistentVolumeClaim"), [])

    def test_missing_external_values_fail_rendering_with_the_value_named(self):
        cases = {
            ("database.bundled=false",): "database.external.host",
            ("identity.bundled=false",): "identity.external.issuerUri",
            ("identity.bundled=false", "identity.external.issuerUri=idp.example/realms/x"): "absolute http(s) URL",
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
        self.assertEqual(paths, {"/api": "t-owl-mast-backend", "/actuator": "t-owl-mast-backend", "/": "t-owl-mast-frontend"})

    def test_no_ingress_or_frontend_by_default(self):
        docs = render()
        self.assertEqual(by_kind(docs, "Ingress"), [])
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


if __name__ == "__main__":
    unittest.main()
