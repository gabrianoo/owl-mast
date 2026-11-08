"""OM-01.04 AC4: the pre-rollout API compatibility check detects incompatible frontend/backend pairs."""
from __future__ import annotations

import contextlib
import http.server
import importlib.util
import io
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check-api-compatibility.py"
spec = importlib.util.spec_from_file_location("check_api_compatibility", SCRIPT)
assert spec and spec.loader
check = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = check
spec.loader.exec_module(check)


def write(directory: Path, name: str, content: str) -> Path:
    path = directory / name
    path.write_text(content, encoding="utf-8")
    return path


def manifest(major: int = 1, min_minor: int = 0) -> str:
    return json.dumps({"frontendVersion": "0.1.0-test", "supportedApiContract": {"major": major, "minMinor": min_minor}, "descriptorPath": "/compatibility"})


def properties(major: int, minor: int) -> str:
    return f"# test\napiContract.major={major}\napiContract.minor={minor}\n"


class StubBackend(http.server.ThreadingHTTPServer):
    def __init__(self, status: int, body: bytes, content_type: str = "application/json"):
        self.response = (status, body, content_type)
        super().__init__(("127.0.0.1", 0), StubHandler)


class StubHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - http.server API
        status, body, content_type = self.server.response  # type: ignore[attr-defined]
        if self.path != "/api/compatibility":
            status, body, content_type = 404, b'{"status":404,"title":"Not Found"}', "application/problem+json"
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):  # silence
        return


class ApiCompatibilityCheckTest(unittest.TestCase):
    def run_check(self, *args: str) -> int:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return check.main(list(args))

    def test_checkout_pair_is_compatible(self):
        self.assertEqual(self.run_check(), 0)

    def test_frontend_manifest_and_backend_contract_agree_on_the_published_major(self):
        supported, _, _ = check.read_frontend_manifest(check.DEFAULT_FRONTEND_MANIFEST)
        backend = check.read_backend_properties(check.DEFAULT_BACKEND_CONTRACT)
        self.assertEqual(supported.major, backend.major)
        self.assertLessEqual(supported.min_minor, backend.minor)

    def test_static_rule_accepts_newer_minor_and_rejects_major_or_lower_minor(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            fm = write(directory, "fm.json", manifest(1, 2))
            self.assertEqual(self.run_check("--frontend-manifest", str(fm), "--backend-contract", str(write(directory, "ok.properties", properties(1, 5)))), 0)
            self.assertEqual(self.run_check("--frontend-manifest", str(fm), "--backend-contract", str(write(directory, "major.properties", properties(2, 0)))), 1)
            self.assertEqual(self.run_check("--frontend-manifest", str(fm), "--backend-contract", str(write(directory, "minor.properties", properties(1, 1)))), 1)
            self.assertEqual(self.run_check("--frontend-manifest", str(fm), "--backend-contract", str(write(directory, "broken.properties", "apiContract.major=one\n"))), 1)

    def test_verdict_names_both_contracts(self):
        ok, message = check.evaluate(check.Contract(2, 0), check.Supported(1, 0))
        self.assertFalse(ok)
        self.assertIn("1.x", message)
        self.assertIn("2.0", message)
        ok, message = check.evaluate(check.Contract(1, 1), check.Supported(1, 3))
        self.assertFalse(ok)
        self.assertIn("1.3", message)
        self.assertIn("1.1", message)
        self.assertTrue(check.evaluate(check.Contract(1, 3), check.Supported(1, 3))[0])

    def test_live_descriptor_compatible_incompatible_and_missing(self):
        cases = [
            (200, json.dumps({"service": "owl-mast-backend", "backendVersion": "0.1.0", "apiContract": {"major": 1, "minor": 0}}).encode(), 0),
            (200, json.dumps({"service": "owl-mast-backend", "backendVersion": "9.0.0", "apiContract": {"major": 2, "minor": 0}}).encode(), 1),
            (404, b'{"status":404,"title":"Not Found"}', 1),
            (200, b"not json", 1),
        ]
        for status, body, expected in cases:
            with self.subTest(status=status, body=body[:20]):
                server = StubBackend(status, body)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    url = f"http://127.0.0.1:{server.server_address[1]}"
                    self.assertEqual(self.run_check("--backend-url", url, "--timeout", "5"), expected)
                finally:
                    server.shutdown()
                    server.server_close()

    def test_unreachable_backend_fails_closed(self):
        self.assertEqual(self.run_check("--backend-url", "http://127.0.0.1:9", "--timeout", "1"), 1)


if __name__ == "__main__":
    unittest.main()
