"""Gateway API input validation (review N5).

Rendered HTTPRoutes are validated offline against the pinned upstream schema in
`deploy/tests/fixtures/gateway-api/` (Gateway API v1.4.0 standard HTTPRoute CRD, version v1; origin and SHA256 in
SOURCE.md) with the Python `jsonschema` library: an explicit, reproducible dependency installed by
`scripts/verify-install-package.sh`, never a network fetch at test time. This exercises the ordinary
OpenAPI/JSON-Schema constraints (types, patterns, lengths, cardinalities, enums). The CRD's CEL rules
(`x-kubernetes-validations`) are not evaluated by jsonschema; the chart enforces the CEL rules that apply to its
exposed inputs, and those are checked here by requiring Helm to refuse. None of this is controller acceptance
or runtime qualification of a Gateway.
"""

import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path

import jsonschema
import yaml

REPO = Path(__file__).resolve().parents[2]
CHART = REPO / "deploy" / "helm" / "owl-mast"
FIXTURES = REPO / "deploy" / "tests" / "fixtures" / "gateway-api"
HELM = os.environ.get("OWLMAST_HELM") or shutil.which("helm")
SCHEMA = json.loads((FIXTURES / "httproute-v1.4.0-openapi-v1.json").read_text())
GATEWAY_ON = ["routing.gateway.enabled=true", "routing.gateway.parentRefs[0].name=shared-gw", "routing.gateway.hostnames[0]=owl.example.internal"]


def helm_template(*sets, extra=()):
    # The capability the chart requires before it renders an HTTPRoute (absent in a bare helm template).
    args = [HELM, "template", "t", str(CHART), "--api-versions", "gateway.networking.k8s.io/v1/HTTPRoute", *extra]
    for s in sets:
        args += ["--set", s]
    return subprocess.run(args, capture_output=True, text=True, check=False)


def routes(*sets):
    result = helm_template(*sets)
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return [d for d in yaml.safe_load_all(result.stdout) if d and d["kind"] == "HTTPRoute"]


def upstream_errors(route: dict) -> list:
    validator = jsonschema.Draft202012Validator(SCHEMA)
    return [f"{'/'.join(str(p) for p in e.absolute_path)}: {e.message[:120]}" for e in validator.iter_errors(route)]


class GatewaySchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if HELM is None:
            raise AssertionError("Helm 4 required (OWLMAST_HELM)")
        source = (FIXTURES / "SOURCE.md").read_text()
        assert "gateway-api/v1.4.0/config/crd/standard" in source and "SHA256" in source, "pinned schema origin must be recorded"

    def test_pinned_schema_is_the_upstream_v1_httproute_schema(self):
        self.assertEqual(SCHEMA["properties"]["spec"]["properties"]["parentRefs"]["maxItems"], 32)
        self.assertEqual(SCHEMA["properties"]["spec"]["properties"]["hostnames"]["maxItems"], 16)
        self.assertIn("pattern", SCHEMA["properties"]["spec"]["properties"]["hostnames"]["items"])

    def test_valid_renders_satisfy_the_upstream_schema(self):
        cases = (
            GATEWAY_ON,
            GATEWAY_ON + ["routing.gateway.parentRefs[0].namespace=gateway-system", "routing.gateway.parentRefs[0].sectionName=https", "routing.gateway.parentRefs[0].port=443",
                          "routing.gateway.hostnames[0]=owl.example.internal", "routing.gateway.hostnames[1]=*.owl.example.internal",
                          "frontend.enabled=true", "frontend.image.tag=0.0.1-shell"],
            GATEWAY_ON + ["routing.gateway.parentRefs[0].sectionName=http", "routing.gateway.parentRefs[1].name=shared-gw", "routing.gateway.parentRefs[1].sectionName=https"],
            GATEWAY_ON + ["routing.gateway.parentRefs[1].name=other-gw", "routing.gateway.parentRefs[1].namespace=other-ns"],
            GATEWAY_ON + ["routing.exposeActuator=true", "routing.actuatorPathPrefix=/actuator/health.x", "routing.gateway.hostnames[0]=a-b.c123"],
            ["routing.gateway.enabled=true", "routing.gateway.parentRefs[0].name=shared-gw", "routing.gateway.allowAllListenerHostnames=true"],
        )
        for sets in cases:
            for route in routes(*sets):
                self.assertEqual(upstream_errors(route), [], sets)

    def test_reviewers_invalid_inputs_are_refused_by_helm_and_would_fail_upstream(self):
        """Each input passed the chart before N5 but violates the stable HTTPRoute schema; the chart now refuses, and
        the schema check documents why (constructed object validated against the pinned upstream schema)."""
        base = routes(*GATEWAY_ON)[0]
        cases = {
            "routing.gateway.hostnames[0]=https://owl.example.internal": lambda r: r["spec"].__setitem__("hostnames", ["https://owl.example.internal"]),
            "routing.gateway.parentRefs[0].namespace=Bad_NS": lambda r: r["spec"]["parentRefs"][0].__setitem__("namespace", "Bad_NS"),
            "routing.gateway.parentRefs[0].sectionName=HTTPS": lambda r: r["spec"]["parentRefs"][0].__setitem__("sectionName", "HTTPS"),
            "routing.gateway.hostnames[0]=" + "a" * 254: lambda r: r["spec"].__setitem__("hostnames", ["a" * 254]),
            "routing.gateway.parentRefs[0].port=70000": lambda r: r["spec"]["parentRefs"][0].__setitem__("port", 70000),
            "routing.gateway.parentRefs[0].namespace=" + "n" * 64: lambda r: r["spec"]["parentRefs"][0].__setitem__("namespace", "n" * 64),
        }
        for value, mutate in cases.items():
            result = helm_template(*GATEWAY_ON, value)
            self.assertNotEqual(result.returncode, 0, value)
            self.assertTrue("schema" in result.stderr.lower() or "not a valid" in result.stderr, (value, result.stderr[:300]))
            broken = json.loads(json.dumps(base)); mutate(broken)
            self.assertNotEqual(upstream_errors(broken), [], f"upstream schema accepted {value}; the chart restriction would be over-restrictive")

    def test_cardinality_limits_match_upstream(self):
        too_many_parents = GATEWAY_ON + [f"routing.gateway.parentRefs[{i}].name=gw-{i}" for i in range(1, 33)]
        result = helm_template(*too_many_parents)
        self.assertNotEqual(result.returncode, 0); self.assertRegex(result.stderr + result.stdout, "at most 32|want 32")  # schema layer or template layer, both refuse
        ok = routes(*GATEWAY_ON, *[f"routing.gateway.parentRefs[{i}].name=gw-{i}" for i in range(1, 32)])[0]
        self.assertEqual(len(ok["spec"]["parentRefs"]), 32); self.assertEqual(upstream_errors(ok), [])
        too_many_hosts = GATEWAY_ON + [f"routing.gateway.hostnames[{i}]=h{i}.example" for i in range(17)]
        result = helm_template(*too_many_hosts)
        self.assertNotEqual(result.returncode, 0); self.assertRegex(result.stderr + result.stdout, "at most 16|want 16")
        ok = routes(*GATEWAY_ON, *[f"routing.gateway.hostnames[{i}]=h{i}.example" for i in range(16)])[0]
        self.assertEqual(len(ok["spec"]["hostnames"]), 16); self.assertEqual(upstream_errors(ok), [])

    def test_cel_rules_for_exposed_inputs_are_enforced_by_the_chart(self):
        """jsonschema cannot evaluate CEL; the chart enforces the rules that its inputs can violate."""
        for sets, expected in (
            (GATEWAY_ON + ["routing.gateway.parentRefs[1].name=shared-gw"], "every reference to the same parent must set a distinct sectionName"),
            (GATEWAY_ON + ["routing.gateway.parentRefs[0].sectionName=https", "routing.gateway.parentRefs[1].name=shared-gw", "routing.gateway.parentRefs[1].sectionName=https"], "sectionName must be unique per parent"),
            (GATEWAY_ON + ["routing.gateway.parentRefs[0].sectionName=https", "routing.gateway.parentRefs[1].name=shared-gw"], "every reference to the same parent must set a distinct sectionName"),
            (GATEWAY_ON + ["routing.apiPathPrefix=/api//x"], "not a valid HTTPRoute PathPrefix"),
            (GATEWAY_ON + ["routing.apiPathPrefix=/api/./x"], "not a valid HTTPRoute PathPrefix"),
            (GATEWAY_ON + ["routing.apiPathPrefix=/api/../x"], "not a valid HTTPRoute PathPrefix"),
            (GATEWAY_ON + ["routing.apiPathPrefix=/api%2Fx"], "not a valid HTTPRoute PathPrefix"),
            (GATEWAY_ON + ["routing.apiPathPrefix=/api#x"], "not a valid HTTPRoute PathPrefix"),
            (GATEWAY_ON + ["routing.apiPathPrefix=/api/.."], "not a valid HTTPRoute PathPrefix"),
            (GATEWAY_ON + ["routing.apiPathPrefix=/api x"], "not a valid HTTPRoute PathPrefix"),
            (["routing.apiPathPrefix=/api//x"], "not a valid HTTPRoute PathPrefix"),  # the path contract is checked for every routing mechanism
            # every exposed prefix is validated, not only the api one (review 4513680409)
            (GATEWAY_ON + ["routing.actuatorPathPrefix=/actuator//x"], "not a valid HTTPRoute PathPrefix"),
            (GATEWAY_ON + ["routing.actuatorPathPrefix=/actuator/../x"], "not a valid HTTPRoute PathPrefix"),
            (GATEWAY_ON + ["routing.actuatorPathPrefix=/actuator%2Fx"], "not a valid HTTPRoute PathPrefix"),
            (GATEWAY_ON + ["frontend.enabled=true", "frontend.image.tag=0.0.1-shell", "routing.frontendPathPrefix=/ui/../x"], "not a valid HTTPRoute PathPrefix"),
            (GATEWAY_ON + ["frontend.enabled=true", "frontend.image.tag=0.0.1-shell", "routing.frontendPathPrefix=//"], "not a valid HTTPRoute PathPrefix"),
        ):
            result = helm_template(*sets)
            self.assertNotEqual(result.returncode, 0, sets); self.assertIn(expected, result.stderr, sets)
        # the same parent on different listeners, and different parents, stay legal
        self.assertEqual(len(routes(*GATEWAY_ON, "routing.gateway.parentRefs[0].sectionName=http", "routing.gateway.parentRefs[1].name=shared-gw", "routing.gateway.parentRefs[1].sectionName=https")[0]["spec"]["parentRefs"]), 2)
        self.assertEqual(routes(*GATEWAY_ON, "routing.exposeActuator=true", "routing.actuatorPathPrefix=/actuator/v1.0~x")[0]["spec"]["rules"][0]["matches"][1]["path"]["value"], "/actuator/v1.0~x")

    def test_template_layer_refuses_on_its_own_when_the_values_schema_is_skipped(self):
        """109/4543776485: every invalid input already failed values.schema.json, so the template's own checks never
        ran in a test. With --skip-schema-validation the template is the only layer, and it must still refuse."""
        skip = ("--skip-schema-validation",)
        for sets, expected in (
            (GATEWAY_ON + ["routing.gateway.parentRefs[0].namespace=Bad_NS"], "is not a valid namespace name"),
            (GATEWAY_ON + ["routing.gateway.parentRefs[0].namespace=" + "n" * 64], "is not a valid namespace name"),
            (GATEWAY_ON + ["routing.gateway.parentRefs[0].sectionName=HTTPS"], "is not a valid listener section name"),
            (GATEWAY_ON + ["routing.gateway.parentRefs[0].port=70000"], "is outside 1-65535"),
            (GATEWAY_ON + ["routing.gateway.parentRefs[0].port=0"], "is outside 1-65535"),  # was dropped silently by `if $ref.port`
            (GATEWAY_ON + ["routing.gateway.parentRefs[0].port=-1"], "is outside 1-65535"),
            (GATEWAY_ON + ["routing.gateway.hostnames[0]=https://owl.example.internal"], "is not a valid HTTPRoute hostname"),
            (GATEWAY_ON + ["routing.gateway.hostnames[0]=" + "a" * 254], "is not a valid HTTPRoute hostname"),
            (GATEWAY_ON + ["routing.gateway.hostnames[0]=10.0.0.1"], "is an IP address"),
            (GATEWAY_ON + [f"routing.gateway.parentRefs[{i}].name=gw-{i}" for i in range(1, 33)], "at most 32"),
            (GATEWAY_ON + [f"routing.gateway.hostnames[{i}]=h{i}.example" for i in range(17)], "at most 16"),
            (["routing.gateway.enabled=true", "routing.gateway.hostnames[0]=owl.example"], "requires at least one routing.gateway.parentRefs entry"),
            (["routing.gateway.enabled=true", "routing.gateway.parentRefs[0].namespace=x", "routing.gateway.hostnames[0]=owl.example"], "needs a name"),
        ):
            result = helm_template(*sets, extra=skip)
            self.assertNotEqual(result.returncode, 0, sets); self.assertIn(expected, result.stderr, sets)
            self.assertNotIn("schema", result.stderr.lower(), sets)  # the refusal is the template's
            # and the schema layer refuses the same input by itself
            self.assertNotEqual(helm_template(*sets).returncode, 0, sets)
        # port 0 is refused by the schema too, not rendered as "no port"
        self.assertIn("schema", helm_template(*GATEWAY_ON, "routing.gateway.parentRefs[0].port=0").stderr.lower())
        self.assertEqual(routes(*GATEWAY_ON, "routing.gateway.parentRefs[0].port=1")[0]["spec"]["parentRefs"][0]["port"], 1)

    def test_gateway_annotations_are_a_string_map(self):
        """116/4543777568: the string-map fix for routing.gateway.annotations had no test on the Gateway side."""
        args = [HELM, "template", "t", str(CHART), "--api-versions", "gateway.networking.k8s.io/v1/HTTPRoute"]
        for s in GATEWAY_ON:
            args += ["--set", s]
        for bad in ('{"a":1}', '{"a":true}', '{"a":{"b":"c"}}', '["a"]'):
            result = subprocess.run(args + ["--set-json", f"routing.gateway.annotations={bad}"], capture_output=True, text=True, check=False)
            self.assertNotEqual(result.returncode, 0, bad); self.assertIn("schema", result.stderr.lower(), bad)
        route = routes(*GATEWAY_ON, "routing.gateway.annotations.example\\.com/x=y", "routing.gateway.annotations.other=z")[0]
        self.assertEqual(route["metadata"]["annotations"], {"example.com/x": "y", "other": "z"})
        self.assertEqual(upstream_errors(route), [])
        self.assertNotIn("annotations", routes(*GATEWAY_ON)[0]["metadata"])


if __name__ == "__main__":
    unittest.main()
