import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from automation.tests.fake_transport import small_backlog
from automation.tests.support import FIXTURES, write_policy
from automation.unattended import cli
from automation.unattended.errors import Refused
from automation.unattended.probes import check_permissions, run_commands, write_probe


def run_cli(*argv) -> tuple[int, dict]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cli.main(list(argv))
    return code, json.loads(buf.getvalue())


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.policy = write_policy(self.dir, allow='["OM-01.02"]')
        self.snapshot = str(FIXTURES / "backlog-snapshot-2026-11-06.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_verify_mapping_from_fixture(self):
        code, out = run_cli("--policy", str(self.policy), "--snapshot", self.snapshot, "--repo-root", str(FIXTURES.parents[1]), "verify-mapping")
        self.assertEqual(code, 0)
        self.assertEqual(out["counts"]["stories"], 85)

    def test_plan_dry_run_writes_nothing(self):
        code, out = run_cli("--policy", str(self.policy), "--snapshot", self.snapshot, "plan")
        self.assertEqual(code, 0)
        self.assertEqual(out["writes"], 0)
        self.assertEqual(out["decisions"][0]["outcome"], "awaiting-owner-acceptance")

    def test_write_commands_need_live(self):
        code, out = run_cli("--policy", str(self.policy), "--run-id", "r", "claim", "OM-01.02", "--receipt", "{}", "--worktree", "w", "--branch", "b", "--baseline", "c")
        self.assertEqual(code, 3)
        self.assertIn("--live", out["error"]["message"])

    def test_state_commands_need_run_id(self):
        code, out = run_cli("--policy", str(self.policy), "status")
        self.assertEqual(code, 3)
        self.assertIn("--run-id", out["error"]["message"])

    def test_invalid_policy_is_reported(self):
        bad = write_policy(self.dir, merge='"auto"')
        code, out = run_cli("--policy", str(bad), "status")
        self.assertEqual(code, 3)
        self.assertEqual(out["error"]["code"], "policy-invalid")

    def test_unreadable_snapshot_is_reported(self):
        code, out = run_cli("--policy", str(self.policy), "--snapshot", "/nonexistent.json", "plan")
        self.assertEqual(code, 3)


class ProbeTests(unittest.TestCase):
    def test_run_commands_stops_at_first_failure(self):
        results = run_commands(["python3 -c 'print(1)'", "python3 -c 'import sys; sys.exit(4)'", "python3 -c 'print(3)'"], None, 30)
        self.assertEqual([r["returncode"] for r in results], [0, 4])

    def test_run_commands_redacts_token_like_output(self):
        results = run_commands(["python3 -c 'print(\"ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123\")'"], None, 30)
        self.assertIn("<redacted>", results[0]["stdout_tail"])

    def test_write_probe_refuses_backlog_issues(self):
        fake = small_backlog()
        with self.assertRaises(Refused):
            write_probe(fake, 21, "run-x", None, "now")
        self.assertEqual(fake.comments[21], [])

    def test_write_probe_is_idempotent_and_verifies_status(self):
        fake = small_backlog()
        first = write_probe(fake, 106, "run-x", "In review", "now")
        second = write_probe(fake, 106, "run-x", None, "now")
        self.assertTrue(first["idempotent"] and second["idempotent"])
        self.assertTrue(second["comment_existed"])
        self.assertEqual(len(fake.comments[106]), 1)
        self.assertTrue(first["status"]["verified"])

    def test_check_permissions_minimum_and_excess(self):
        def runner(argv, cwd, timeout):
            if argv[:3] == ["gh", "auth", "status"]:
                return subprocess.CompletedProcess(argv, 0, "ok", "")
            if argv[:3] == ["gh", "api", "-i"]:
                return subprocess.CompletedProcess(argv, 0, "HTTP/2.0 200\r\nx-oauth-scopes: repo, project, workflow\r\n\r\n" + json.dumps({"permissions": {"push": True}}), "")
            return subprocess.CompletedProcess(argv, 0, json.dumps({"data": {"user": {"projectV2": {"id": "P", "title": "t", "viewerCanUpdate": True}}}}), "")

        report = check_permissions("o", "r", "o", 2, runner)
        self.assertTrue(report["minimum_satisfied"])
        self.assertEqual(report["excess"], ["workflow"])

        def denied(argv, cwd, timeout):
            if argv[:3] == ["gh", "api", "-i"]:
                return subprocess.CompletedProcess(argv, 0, "HTTP/2.0 200\r\nx-oauth-scopes: repo\r\n\r\n" + json.dumps({"permissions": {"push": False}}), "")
            return runner(argv, cwd, timeout)

        report = check_permissions("o", "r", "o", 2, denied)
        self.assertFalse(report["minimum_satisfied"])
        self.assertTrue(any("project" in p for p in report["problems"]))
