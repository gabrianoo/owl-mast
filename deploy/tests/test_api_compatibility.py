"""OM-01.04 AC4: the pre-rollout API compatibility check detects incompatible frontend/backend pairs."""
from __future__ import annotations

import contextlib
import http.server
import importlib.util
import io
import json
import socket
import struct
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
    def __init__(self, status: int, body: bytes, content_type: str = "application/json", served: tuple[str, ...] = ("/api/compatibility", "/api-compatibility.json")):
        self.response = (status, body, content_type)
        self.served = served
        self.paths: list[str] = []
        super().__init__(("127.0.0.1", 0), StubHandler)


class StubHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - http.server API
        status, body, content_type = self.server.response  # type: ignore[attr-defined]
        self.server.paths.append(self.path)  # type: ignore[attr-defined]
        if self.path not in self.server.served:  # type: ignore[attr-defined]
            status, body, content_type = 404, b'{"status":404,"title":"Not Found"}', "application/problem+json"
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):  # silence
        return


@contextlib.contextmanager
def serving(status: int, body: bytes, content_type: str = "application/json", served: tuple[str, ...] | None = None, paths: list[str] | None = None):
    server = StubBackend(status, body, content_type) if served is None else StubBackend(status, body, content_type, served)
    if paths is not None:
        server.paths = paths
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


@contextlib.contextmanager
def raw_server(behaviour):
    """A socket that accepts one connection and runs `behaviour(connection, release)`: transport failures no HTTP stub can produce."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    release = threading.Event()

    def serve():
        try:
            connection, _ = listener.accept()
        except OSError:
            return
        with connection:
            try:
                connection.recv(65536)
                behaviour(connection, release)
            except OSError:
                pass

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{listener.getsockname()[1]}"
    finally:
        release.set()
        listener.close()
        thread.join(timeout=5)


class ApiCompatibilityCheckTest(unittest.TestCase):
    def run_check(self, *args: str) -> int:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return check.main(list(args))

    def run_verdict(self, *args: str) -> tuple[int, str, str]:
        """Exit code, stdout and stderr; any exception escaping main() fails the test (no traceback contract)."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = check.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def assert_unverifiable(self, *args: str) -> str:
        code, out, err = self.run_verdict(*args)
        self.assertEqual(code, 1, err)
        self.assertEqual(out, "")
        self.assertEqual(len(err.strip().splitlines()), 1, err)
        self.assertTrue(err.startswith("INCOMPATIBLE (unverifiable): "), err)
        self.assertNotIn("Traceback", err)
        return err

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

    def test_unverifiable_verdict_names_the_frontend_contract(self):
        """112/4551653234: the matrix requires both contracts named for an unreachable descriptor."""
        with tempfile.TemporaryDirectory() as tmp:
            fm = write(Path(tmp), "fm.json", manifest(1, 2))
            err = self.assert_unverifiable("--frontend-manifest", str(fm), "--backend-url", "http://127.0.0.1:9", "--timeout", "1")
            self.assertIn("frontend 0.1.0-test supports API contract 1.x (at least 1.2)", err)
            self.assertIn("backend contract unknown", err)
            with serving(404, b'{"status":404,"title":"Not Found"}', "application/problem+json") as url:
                err = self.assert_unverifiable("--frontend-manifest", str(fm), "--backend-url", url)
                self.assertIn("answered 404", err)
                self.assertIn("1.x (at least 1.2)", err)
            err = self.assert_unverifiable("--frontend-manifest", str(fm), "--backend-contract", str(Path(tmp) / "missing.properties"))
            self.assertIn("1.x (at least 1.2)", err)

    def test_unreadable_manifest_is_a_verdict_not_a_traceback(self):
        """112/4551653249: a JSON array raised AttributeError and a non-UTF-8 file UnicodeDecodeError."""
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            cases = {
                "array.json": b"[]",
                "scalar.json": b"7",
                "null.json": b"null",
                "latin1.json": '{"frontendVersion":"caf\u00e9"}'.encode("latin-1"),
                "utf16.json": manifest().encode("utf-16"),
                "broken.json": b"{",
                "no-contract.json": b"{}",
                "bool.json": b'{"supportedApiContract":{"major":true,"minMinor":0}}',
            }
            for name, content in cases.items():
                with self.subTest(name=name):
                    path = directory / name
                    path.write_bytes(content)
                    err = self.assert_unverifiable("--frontend-manifest", str(path))
                    self.assertIn("frontend contract unknown", err)
            self.assertIn("frontend contract unknown", self.assert_unverifiable("--frontend-manifest", str(directory / "absent.json")))
            self.assertIn("frontend contract unknown", self.assert_unverifiable("--frontend-manifest", str(directory)))

    def test_transport_failures_are_a_verdict_not_a_traceback(self):
        """112/4551653255: a read timeout, a reset and a truncated body are not URLError."""
        def stall(connection, release):
            release.wait(timeout=10)

        def stall_mid_body(connection, release):
            connection.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 100\r\n\r\n{")
            release.wait(timeout=10)

        def truncate(connection, release):
            connection.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 100\r\n\r\n{")

        def reset(connection, release):
            connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))  # close with RST

        def garbage(connection, release):
            connection.sendall(b"not http at all\r\n\r\n")

        for name, behaviour in (("stall", stall), ("stall-mid-body", stall_mid_body), ("truncate", truncate), ("reset", reset), ("garbage", garbage)):
            with self.subTest(name=name), raw_server(behaviour) as url:
                err = self.assert_unverifiable("--backend-url", url, "--timeout", "0.5")
                self.assertIn("supports API contract 1.x", err)

    def test_malformed_urls_are_a_verdict_not_a_traceback(self):
        """112/4551653265: backend:8080 raised ValueError: unknown url type."""
        for option in ("--backend-url", "--frontend-url"):
            # "" and " ": an unset pipeline variable must not silently fall back to the checkout.
            for value in ("backend:8080", "localhost", "ftp://backend/", "http://", "http://host:port", "http://[::1", "//backend", "", " ",
                          "http://127.0.0.1:9/?x=1", "http://127.0.0.1:9/#x"):
                with self.subTest(option=option, value=value):
                    err = self.assert_unverifiable(option, value, "--timeout", "1")
                    self.assertIn(f"invalid {option}", err)
        # 119/4552568111: a credential in the URL must never reach the verdict (CI logs keep it).
        for option in ("--backend-url", "--frontend-url"):
            for value in ("https://u5er-marker:s3cr3t-token@127.0.0.1:9", "http://s3cr3t-token@127.0.0.1:9", "http://u5er-marker:s3cr3t-token@host:port",
                          "http://u5er-marker:s3cr3t-token@[::1", "http://u5er-marker:s3cr3t-token@127.0.0.1:9/?x=1", "ftp://u5er-marker:s3cr3t-token@host"):
                with self.subTest(option=option, value=value):
                    err = self.assert_unverifiable(option, value, "--timeout", "1")
                    self.assertIn(f"invalid {option}: credentials in the URL", err)
                    self.assertNotIn("s3cr3t-token", err)
                    self.assertNotIn("u5er-marker", err)
            # A refused URL is never repeated, whatever the reason: a token can sit in the query or the host part too.
            for value in ("https://127.0.0.1:9/?access_token=s3cr3t-token", "https://127.0.0.1:9/#s3cr3t-token", "https://?s3cr3t-token",
                          "ftp://s3cr3t-token/", "http://s3cr3t-token:port", "http://[s3cr3t-token"):
                with self.subTest(option=option, value=value):
                    self.assertNotIn("s3cr3t-token", self.assert_unverifiable(option, value, "--timeout", "1"))
        for value in ("http://127.0.0.1:9/a b", "http://127.0.0.1:9/a\nCOMPATIBLE: forged", "http://127.0.0.1:9/a\x1b[31m", "http://127.0.0.1:9/a\x00",
                      "http://127.0.0.1:9/a\x7f", "http://127.0.0.1:9/a\x9b31m", "http://127.0.0.1:9/a\u202e"):
            with self.subTest(value=value):
                err = self.assert_unverifiable("--backend-url", value, "--timeout", "1")
                self.assertIn("invalid --backend-url", err)
                self.assertTrue(err.rstrip("\n").isprintable(), repr(err))
        # The prefix becomes part of the URL: the same plain-path rule as the shell and the image apply.
        for prefix in ("/a\nCOMPATIBLE: forged", "/a\x1b[31m", "/a?x=1", "/a#x", "/a/../b", "/a b", "//evil.example", "/a//", "/" + "a" * 2000):
            with self.subTest(prefix=prefix):
                err = self.assert_unverifiable("--backend-url", "http://127.0.0.1:9", "--api-path-prefix", prefix, "--timeout", "1")
                self.assertIn("invalid --api-path-prefix", err)
                self.assertTrue(err.rstrip("\n").isprintable(), repr(err))
                self.assertLess(len(err), 700)
        for prefix in ("api", ".invalid", ""):
            with self.subTest(prefix=prefix):
                self.assertIn("invalid --api-path-prefix", self.assert_unverifiable("--backend-url", "http://127.0.0.1:9", "--api-path-prefix", prefix, "--timeout", "1"))
        for timeout in ("inf", "nan", "0", "-1", "1e30"):
            with self.subTest(timeout=timeout):
                self.assertIn("invalid --timeout", self.assert_unverifiable("--backend-url", "http://127.0.0.1:9", "--timeout", timeout))

    def test_hostile_remote_content_is_a_one_line_verdict(self):
        """Remote bodies are untrusted: deep nesting, oversized bodies and multi-line versions keep the verdict contract."""
        deep = b"[" * 200_000
        with serving(200, deep) as url:
            self.assertIn("is not JSON", self.assert_unverifiable("--backend-url", url))
            self.assertIn("is not JSON", self.assert_unverifiable("--frontend-url", url))
        with serving(200, b" " * (check.MAX_BODY_BYTES + 1)) as url:
            self.assertIn("more than", self.assert_unverifiable("--backend-url", url))
        forged = "1.0\nCOMPATIBLE: forged"
        descriptor = json.dumps({"service": "owl-mast-backend", "backendVersion": forged, "apiContract": {"major": 2, "minor": 0}}).encode()
        with serving(200, descriptor) as url:
            code, out, err = self.run_verdict("--backend-url", url)
            self.assertEqual(code, 1)
            self.assertEqual(len(out.strip().splitlines()), 1, out)
            self.assertTrue(out.startswith("INCOMPATIBLE: "), out)
        published = json.dumps({"frontendVersion": forged, "supportedApiContract": {"major": 1, "minMinor": 0}}).encode()
        with serving(200, published) as url:
            code, out, err = self.run_verdict("--frontend-url", url)
            self.assertEqual(code, 0, err)
            self.assertEqual(len(out.strip().splitlines()), 1, out)
            err = self.assert_unverifiable("--frontend-url", url, "--backend-url", "http://127.0.0.1:9", "--timeout", "1")
            self.assertIn("supports API contract 1.x", err)

    def test_remote_descriptor_path_is_a_plain_path_or_the_pair_is_unverifiable(self):
        """119/4552568047: descriptorPath is remote text that becomes part of the backend URL and of the verdict."""
        descriptor = json.dumps({"service": "owl-mast-backend", "backendVersion": "9.1.0", "apiContract": {"major": 1, "minor": 0}}).encode()
        for path in ("/c\nCOMPATIBLE: forged", "/c\rCOMPATIBLE: forged", "/c d", "//evil.example/x", "/a/../b", "/a/./b", "/a/..", "/a//b", "/a/",
                     "/", "/a?x=1", "/a#x", "/a%0Ab", "/@evil.example", "compatibility", "", 7, None, ["/compatibility"]):
            with self.subTest(path=path):
                published = json.dumps({"frontendVersion": "7.0.0", "supportedApiContract": {"major": 1, "minMinor": 0}, "descriptorPath": path}).encode()
                backend_paths: list[str] = []
                with serving(200, published, served=("/api-compatibility.json",)) as frontend, \
                        serving(200, descriptor, served=("/api/compatibility",), paths=backend_paths) as backend:
                    err = self.assert_unverifiable("--frontend-url", frontend, "--backend-url", backend)
                    self.assertIn("invalid descriptorPath", err)
                    self.assertNotIn("forged failed", err)
                    self.assertEqual(backend_paths, [], "the backend must not be asked at a refused path")
        # The rejected value is shown escaped and shortened; an accepted one is bounded too.
        for path in ("/c\x1b[31m" + "x" * 5000, "/" + "x" * 5000):
            published = json.dumps({"frontendVersion": "7.0.0", "supportedApiContract": {"major": 1, "minMinor": 0}, "descriptorPath": path}).encode()
            with serving(200, published, served=("/api-compatibility.json",)) as frontend:
                err = self.assert_unverifiable("--frontend-url", frontend, "--backend-url", "http://127.0.0.1:9")
                self.assertIn("invalid descriptorPath", err)
                self.assertTrue(err.rstrip("\n").isprintable(), repr(err))
                self.assertLess(len(err), 600)
        with tempfile.TemporaryDirectory() as tmp:
            fm = write(Path(tmp), "fm.json", json.dumps({"supportedApiContract": {"major": 1, "minMinor": 0}, "descriptorPath": "/c\nCOMPATIBLE: forged"}))
            self.assertIn("invalid descriptorPath", self.assert_unverifiable("--frontend-manifest", str(fm)))

    def test_rejected_remote_values_are_bounded_in_the_verdict(self):
        """119/4552568129: a rejected value is echoed, but never at the size the remote side chose."""
        huge = "9" * (check.MAX_BODY_BYTES - 200)
        for body in (
            json.dumps({"service": "owl-mast-backend", "backendVersion": "1", "apiContract": {"major": huge, "minor": 0}}),
            json.dumps({"service": "owl-mast-backend", "backendVersion": "1", "apiContract": {"major": 1, "minor": [huge]}}),
        ):
            with serving(200, body.encode()) as url:
                err = self.assert_unverifiable("--backend-url", url)
                self.assertIn("must be a non-negative integer", err)
                self.assertLess(len(err), 600)
        published = json.dumps({"frontendVersion": "1", "supportedApiContract": {"major": 1, "minMinor": huge}})
        with serving(200, published.encode()) as url:
            err = self.assert_unverifiable("--frontend-url", url)
            self.assertIn("supportedApiContract.minMinor", err)
            self.assertLess(len(err), 600)
        self.assertLessEqual(len(check._verdict_line("x " * 5000)), check.MAX_VERDICT_CHARS)
        self.assertEqual(check._verdict_line("a\nb\r\n c\u2028d\x1b[2K\x00\x9b\u202ee"), "a b c d?[2K???e")
        # A value nested deeper than repr()/str() can walk is still a verdict, not a traceback.
        deep: object = []
        for _ in range(100_000):
            deep = [deep]
        self.assertEqual(check._shown(deep), "<deeply nested value>")
        self.assertEqual(check._one_line(deep), "unknown")
        # End to end the depth a JSON parser accepts differs between Python versions: either the
        # parser refuses the body or the value is refused, and both are one unverifiable line.
        nested = "[" * 50_000 + "]" * 50_000
        with serving(200, ('{"service":"owl-mast-backend","backendVersion":"1","apiContract":{"major":' + nested + ',"minor":0}}').encode()) as url:
            self.assertRegex(self.assert_unverifiable("--backend-url", url), "must be a non-negative integer|is not JSON")
        with serving(200, ('{"frontendVersion":' + nested + ',"supportedApiContract":{"major":1,"minMinor":0}}').encode()) as url:
            code, out, err = self.run_verdict("--frontend-url", url)
            self.assertNotIn("Traceback", out + err)
            self.assertEqual(len((out + err).strip().splitlines()), 1, out + err)
            self.assertTrue((code, out[:11]) == (0, "COMPATIBLE:") or (code, err[:28]) == (1, "INCOMPATIBLE (unverifiable):"), out + err)
        # Remote versions and local paths cannot put a control sequence or a second line on stdout either.
        with serving(200, json.dumps({"frontendVersion": "1\x1b[31m\nCOMPATIBLE: forged", "supportedApiContract": {"major": 1, "minMinor": 0}}).encode()) as url:
            code, out, err = self.run_verdict("--frontend-url", url)
            self.assertEqual(code, 0, err)
            self.assertEqual(len(out.strip().splitlines()), 1, out)
            self.assertTrue(out.rstrip("\n").isprintable(), repr(out))
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "x\nINCOMPATIBLE: forged"
            directory.mkdir()
            code, out, err = self.run_verdict("--frontend-manifest", str(write(directory, "fm.json", manifest(1, 0))))
            self.assertEqual(code, 0, err)
            self.assertEqual(len(out.strip().splitlines()), 1, out)

    def test_both_artifacts_are_read_from_their_own_urls(self):
        """The documented pre-rollout command: the manifest from the frontend, the descriptor from the backend, at the manifest's descriptorPath."""
        published = json.dumps({"frontendVersion": "7.0.0", "supportedApiContract": {"major": 3, "minMinor": 1}, "descriptorPath": "/contract"}).encode()
        descriptor = json.dumps({"service": "owl-mast-backend", "backendVersion": "9.1.0", "apiContract": {"major": 3, "minor": 2}}).encode()
        frontend_paths: list[str] = []
        backend_paths: list[str] = []
        with serving(200, published, served=("/api-compatibility.json",), paths=frontend_paths) as frontend, \
                serving(200, descriptor, served=("/owl/api/contract",), paths=backend_paths) as backend:
            code, out, err = self.run_verdict("--frontend-url", frontend + "/", "--backend-url", backend, "--api-path-prefix", "/owl/api/")
            self.assertEqual(code, 0, err)
            self.assertIn("backend API contract 3.2 satisfies frontend requirement 3.x (at least 3.1)", out)
            self.assertIn(f"frontend 7.0.0 from {frontend}", out)
            self.assertIn(f"backend 9.1.0 from {backend}", out)
            self.assertEqual(frontend_paths, ["/api-compatibility.json"])
            self.assertEqual(backend_paths, ["/owl/api/contract"])
            # Swapped: each side answers 404 for the other's path, so the pair is unverifiable.
            self.assert_unverifiable("--frontend-url", backend, "--backend-url", frontend)

    def test_properties_are_read_as_java_reads_them(self):
        """112/4551653276: the backend loads the file with java.util.Properties; the check must agree."""
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            for name, content, expected in (
                ("colon", "apiContract.major:1\napiContract.minor:4\n", check.Contract(1, 4)),
                ("space", "apiContract.major 1\napiContract.minor\t4\n", check.Contract(1, 4)),
                ("padded", "  apiContract.major = 1  \n\tapiContract.minor : 4\n", check.Contract(1, 4)),
                ("last-wins", "apiContract.major=9\napiContract.major=1\napiContract.minor=0\n", check.Contract(1, 0)),
                ("comments", "! note\n# apiContract.major=9\napiContract.major=1\napiContract.minor=0\n", check.Contract(1, 0)),
                ("crlf", "apiContract.major=1\r\napiContract.minor=2\r\n", check.Contract(1, 2)),
                ("cr", "apiContract.major=1\rapiContract.minor=2\r", check.Contract(1, 2)),
                ("escaped-backslash", "note=a\\\\\napiContract.major=1\napiContract.minor=2\n", check.Contract(1, 2)),
                # 112/4552553468: Java decodes escapes in keys, so an escaped spelling is the same key (and wins when later).
                ("unicode-escape-key", "apiContract.major=1\napiContract.m\\u0061jor=2\napiContract.minor=0\n", check.Contract(2, 0)),
                ("unicode-escape-upper", "\\u0061piContract.major=3\napiContract.minor\\u003D=7\napiContract.minor=0\n", check.Contract(3, 0)),
                ("plain-escape-key", "\\a\\p\\iContract.major=4\napiContract\\.minor=5\n", check.Contract(4, 5)),
                ("escaped-separator-key", "apiContract.major\\=x=9\napiContract.major=1\napiContract.minor=0\n", check.Contract(1, 0)),
                # \t \n \r \f inside a key are those characters to Java, not the letters: neither line below is the contract key.
                ("control-escapes-are-not-letters", "apiContract.major=1\napiCon\\tract.major=2\napiCo\\ntract.major=3\napiCont\\ract.major=4\napiContract.minor=0\n", check.Contract(1, 0)),
                ("form-feed-escape-is-not-a-letter", "apiContract.minor=0\napiContract.major=1\napiContract.mino\\fr=5\n", check.Contract(1, 0)),
                ("escaped-control-key", "apiContract.major\\t=9\napiContract.major\\n=9\napiContract.major=1\napiContract.minor=0\n", check.Contract(1, 0)),
            ):
                with self.subTest(name=name):
                    self.assertEqual(check.read_backend_properties(write(directory, f"{name}.properties", content)), expected)
            fm = write(directory, "fm.json", manifest(1, 0))
            for name, content in (
                ("negative", "apiContract.major=-1\napiContract.minor=0\n"),
                ("underscore", "apiContract.major=1_0\napiContract.minor=0\n"),
                ("plus", "apiContract.major=+1\napiContract.minor=0\n"),
                ("float", "apiContract.major=1.0\napiContract.minor=0\n"),
                ("arabic-digits", "apiContract.major=\u0661\napiContract.minor=0\n"),
                ("overflow", "apiContract.major=2147483648\napiContract.minor=0\n"),
                ("empty", "apiContract.major=\napiContract.minor=0\n"),
                ("missing", "apiContract.minor=0\n"),
                ("other-key", "apiContract.majority=1\napiContract.minor=0\n"),
                ("huge", "apiContract.major=" + "9" * 5000 + "\napiContract.minor=0\n"),
                ("nbsp", "apiContract.major=1\u00a0\napiContract.minor=0\n"),
                # Java keeps reading the same line after NEL / FS; splitting there would invent a key.
                ("nel-is-not-a-line-end", "note=x\u0085apiContract.major=1\napiContract.minor=0\n"),
                # Java throws on a malformed \\uXXXX, in a key or a value; a value written with an escape is not a plain decimal.
                ("malformed-unicode-key", "apiContract.m\\u00zzjor=1\napiContract.major=1\napiContract.minor=0\n"),
                ("short-unicode-key", "apiContract.major=1\napiContract.minor=0\nx\\u12=1\n"),
                ("malformed-unicode-value", "apiContract.major=1\napiContract.minor=0\nnote=\\uZZZZ\n"),
                ("unicode-escape-value", "apiContract.major=\\u0031\napiContract.minor=0\n"),
                # Java joins the next line to "note"; reading it as a key would judge a number the backend never loads.
                ("continuation", "note=x\\\napiContract.major=1\napiContract.major=2\napiContract.minor=0\n"),
            ):
                with self.subTest(name=name):
                    path = directory / f"{name}.properties"
                    path.write_bytes(content.encode("iso-8859-1", errors="replace"))
                    err = self.assert_unverifiable("--frontend-manifest", str(fm), "--backend-contract", str(path))
                    self.assertIn({"continuation": "continuation", "malformed-unicode-key": "malformed", "short-unicode-key": "malformed", "malformed-unicode-value": "malformed"}.get(name, "apiContract.major"), err)

    def test_frontend_url_reads_the_manifest_the_deployed_artifact_publishes(self):
        """112/4551653219: the pre-rollout check must judge the artifact, not whatever checkout runs it."""
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            v1 = write(directory, "v1.properties", properties(1, 0))
            v2 = write(directory, "v2.properties", properties(2, 0))
            with serving(200, manifest(2, 0).encode()) as url:
                # The deployed frontend needs 2.x: the checkout's 1.x manifest must not be what is judged.
                code, out, _ = self.run_verdict("--frontend-url", url, "--backend-contract", str(v2))
                self.assertEqual(code, 0, out)
                self.assertIn(f"frontend 0.1.0-test from {url}", out)
                code, out, _ = self.run_verdict("--frontend-url", url, "--backend-contract", str(v1))
                self.assertEqual(code, 1)
                self.assertIn("2.x", out)
                self.assertIn("1.0", out)
            # An image without the manifest answers with its SPA fallback (HTML) or 404: unverifiable.
            with serving(200, b"<!doctype html><div id=root></div>", "text/html") as url:
                self.assertIn("is not JSON", self.assert_unverifiable("--frontend-url", url, "--backend-contract", str(v1)))
            with serving(404, b"") as url:
                self.assertIn("answered 404", self.assert_unverifiable("--frontend-url", url, "--backend-contract", str(v1)))
            with serving(200, b"[]") as url:
                self.assertIn("must be a JSON object", self.assert_unverifiable("--frontend-url", url, "--backend-contract", str(v1)))
            self.assert_unverifiable("--frontend-url", "http://127.0.0.1:9", "--timeout", "1")


if __name__ == "__main__":
    unittest.main()
