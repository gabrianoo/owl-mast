import io
import json
import subprocess
import os
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
        code, out = run_cli("--policy", str(self.policy), "--run-id", "r", "reserve", "OM-01.02", "--baseline", "c")
        self.assertEqual(code, 3)
        self.assertIn("--live", out["error"]["message"])
        for argv in (["authorize-repair", "OM-01.02"], ["resume", "OM-01.02"], ["rebase-revisions", "OM-01.02", "--reason", "r"], ["cancel-run", "--reason", "r"], ["probe-write", "--issue", "106"], ["block", "OM-01.02", "--reason", "r"], ["cancel", "OM-01.02", "--reason", "r"]):
            code, out = run_cli("--policy", str(self.policy), "--run-id", "r", *argv)
            self.assertEqual(code, 3, argv)
            self.assertIn("--live", out["error"]["message"])

    def test_repair_without_live_cannot_reach_the_block_fallback(self):
        """Reviewer finding E11: every indirect write is behind --live."""
        from automation.unattended.cli import WRITE_COMMANDS

        self.assertIn("authorize-repair", WRITE_COMMANDS)
        choices = list(cli.build_parser()._subparsers._group_actions[0].choices)
        self.assertNotIn("record-checks", choices)
        self.assertNotIn("claim", choices)
        for gone in ("request-review", "repair"):  # post-launch receipt commands no longer exist: authorization precedes every launch
            self.assertNotIn(gone, choices)
        for present in ("reserve", "bind-receipt", "authorize-review", "authorize-repair", "record-task-terminal"):
            self.assertIn(present, choices)

    def test_live_state_commands_refuse_on_the_real_transport_without_activation_before_any_gh_call(self):
        """The CLI only ever builds the live gh transport; without --activation every state
        command (status included) refuses activation-required and no run state is created."""
        from automation.unattended.github import GhCliTransport

        calls = []
        original = GhCliTransport._run
        GhCliTransport._run = lambda self, args, stdin=None: calls.append(args) or "{}"
        try:
            with tempfile.TemporaryDirectory() as state_dir:
                for argv in (["reserve", "OM-01.02", "--baseline", "c"], ["resume", "OM-01.02"], ["cancel-run", "--reason", "r"], ["status"]):
                    code, out = run_cli("--policy", str(self.policy), "--state-dir", state_dir, "--run-id", "r", "--live", *argv)
                    self.assertEqual(code, 3, argv)
                    self.assertEqual(out["error"]["code"], "activation-required", argv)
                    self.assertIn("accepting residual risk is not activation", out["error"]["message"])
                self.assertEqual(os.listdir(state_dir), [])
        finally:
            GhCliTransport._run = original
        self.assertEqual(calls, [])

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
    def test_run_commands_stops_at_first_failure_for_probes_and_runs_all_for_checks(self):
        commands = ["python3 -c 'print(1)'", "python3 -c 'import sys; sys.exit(4)'", "python3 -c 'print(3)'"]
        self.assertEqual([r["returncode"] for r in run_commands(commands, None, 30)], [0, 4])
        self.assertEqual([r["returncode"] for r in run_commands(commands, None, 30, fail_fast=False)], [0, 4, 0])

    def test_run_commands_redacts_token_like_output(self):
        results = run_commands(["python3 -c 'print(\"ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123\")'"], None, 30)
        self.assertIn("<redacted>", results[0]["stdout_tail"])

    def test_write_probe_is_idempotent_and_writes_comments_only(self):
        fake = small_backlog()
        first = write_probe(fake, 106, "run-x", "now")
        second = write_probe(fake, 106, "run-x", "now")
        self.assertTrue(first["idempotent"] and second["idempotent"])
        self.assertTrue(second["comment_existed"])
        self.assertEqual(len(fake.comments[106]), 1)
        self.assertEqual(fake.item_for(106).status, "In progress")
        self.assertNotIn("set_project_status", fake.calls)

    def test_write_probe_refuses_backlog_issues(self):
        fake = small_backlog()
        with self.assertRaises(Refused):
            write_probe(fake, 21, "run-x", "now")
        self.assertEqual(fake.comments[21], [])

    def test_check_permissions_never_qualifies_from_scope_headers(self):
        """Round-1 findings R1-B6/E4/V2: scope names, push and a non-admin flag never prove a
        bounded credential; activation is never allowed by this probe."""
        def runner(scopes="repo, project", admin=False, can_update=True):
            def run(argv, cwd, timeout):
                if argv[:3] == ["gh", "auth", "status"]:
                    return subprocess.CompletedProcess(argv, 0, "ok", "")
                if argv[:3] == ["gh", "api", "-i"]:
                    header = f"x-oauth-scopes: {scopes}\r\n" if scopes is not None else ""
                    return subprocess.CompletedProcess(argv, 0, "HTTP/2.0 200\r\n" + header + "\r\n" + json.dumps({"permissions": {"push": True, "admin": admin}}), "")
                return subprocess.CompletedProcess(argv, 0, json.dumps({"data": {"user": {"projectV2": {"id": "P", "title": "t", "viewerCanUpdate": can_update}}}}), "")
            return run

        for scopes, admin, can_update in (("repo, project", False, True), ("repo, read:project", False, False), ("repo, project, workflow", True, True), (None, False, False)):
            report = check_permissions("o", "r", "o", 2, runner(scopes, admin, can_update))
            self.assertTrue(report["basic_access"], (scopes, report["problems"]))
            self.assertFalse(report["bounded"], scopes)
            self.assertFalse(report["unattended_activation_allowed"], scopes)
            self.assertFalse(report["denial_tested"])
            self.assertFalse(report["resource_scope_verified"])
            self.assertTrue(any("denial" in r for r in report["bounded_reasons"]))
        report = check_permissions("o", "r", "o", 2, runner("repo, project, workflow", True, True))
        self.assertEqual(report["excess"], ["workflow"])
        self.assertTrue(any("admin" in r for r in report["bounded_reasons"]))
        report = check_permissions("o", "r", "o", 2, runner(None))
        self.assertTrue(any("cannot be read" in r for r in report["bounded_reasons"]))

        def denied(argv, cwd, timeout):
            if argv[:3] == ["gh", "api", "-i"]:
                return subprocess.CompletedProcess(argv, 0, "HTTP/2.0 200\r\nx-oauth-scopes: repo\r\n\r\n" + json.dumps({"permissions": {"push": False}}), "")
            return runner()(argv, cwd, timeout)

        report = check_permissions("o", "r", "o", 2, denied)
        self.assertFalse(report["basic_access"])
        self.assertTrue(any("project" in p for p in report["problems"]))
        self.assertIn("Projects: read", " ".join(report["minimum"]["fine_grained"]))
