"""Fixture-driven tests of the manual-step lifecycle smoke helper. These use FIXTURE receipts
and evidence (labelled ``--source fixture``); they prove the helper's mechanics, not a real
T3 smoke, which only coordinator-supplied real receipts can provide."""

import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from automation.tests import lifecycle_smoke as smoke
from automation.tests.support import IMPLEMENTER, REVIEWER, make_git_repo


def run(*argv) -> tuple[int, dict]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = smoke.main([str(a) for a in argv])
    return code, json.loads(buf.getvalue())


class LifecycleSmokeHelperTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "smoke"
        self.files = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, payload) -> str:
        path = self.files / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return str(path)

    def evidence(self, task_id, status="result_available"):
        return self.write(f"ev-{task_id}.json", {"taskId": task_id, "runId": task_id + ":run:1", "status": status})

    def test_full_lifecycle_with_fixture_inputs_and_restart(self):
        code, out = run("--dir", self.dir, "prepare")
        self.assertEqual(code, 0)
        self.assertEqual(out["phase"], "reserved")
        auth = out["authorization"]
        sha = out["baseline"]
        self.assertTrue((self.dir / "transport.json").exists())
        # restart before any task: persisted transport and state reload, nothing posted twice
        code, out = run("--dir", self.dir, "restart")
        self.assertEqual((code, out["phase"]), (0, "reserved"))
        # bind the implementer receipt (fixture) to the exact authorization
        code, out = run("--dir", self.dir, "bind", "--receipt", self.write("impl.json", IMPLEMENTER), "--worktree", str(self.dir / "worktree"), "--branch", "smoke/om-99-01", "--authorization", auth, "--source", "fixture")
        self.assertEqual((code, out["phase"], out["source"]), (0, "claimed", "fixture"))
        code, out = run("--dir", self.dir, "head", "--sha", sha, "--task-evidence", self.evidence("task-impl-1"), "--source", "fixture")
        self.assertEqual((code, out["phase"]), (0, "implemented"))
        code, out = run("--dir", self.dir, "check", "--sha", sha)
        self.assertEqual((code, out["phase"]), (0, "checks-passed"))
        self.assertEqual(len(out["checks"]["commands"]), len(smoke.DEFAULT_CHECKS))
        code, out = run("--dir", self.dir, "authorize-review", "--sha", sha)
        self.assertEqual((code, out["phase"]), (0, "review-authorized"))
        auth_review = out["authorization"]
        code, out = run("--dir", self.dir, "bind", "--receipt", self.write("rev.json", REVIEWER), "--authorization", out["authorization"], "--source", "fixture")
        self.assertEqual((code, out["error"]["code"]), (3, "reviewer-worktree-required"))  # a reviewer names its own checkout; the receipt's isolation string proves nothing
        code, out = run("--dir", self.dir, "bind", "--receipt", self.write("rev.json", REVIEWER), "--worktree", str(self.dir / "worktree"), "--branch", "smoke/om-99-01", "--authorization", auth_review, "--source", "fixture")
        self.assertEqual((code, out["error"]["code"]), (3, "reviewer-worktree-shared"))  # the implementer's worktree is not an independent review
        make_git_repo(self.dir / "review-worktree", "smoke/om-99-01")
        code, out = run("--dir", self.dir, "bind", "--receipt", self.write("rev.json", REVIEWER), "--worktree", str(self.dir / "review-worktree"), "--branch", "smoke/om-99-01", "--authorization", auth_review, "--source", "fixture")
        self.assertEqual((code, out["phase"]), (0, "review-requested"))
        code, out = run("--dir", self.dir, "restart")
        self.assertEqual((code, out["phase"], out["active_task"]["taskId"]), (0, "review-requested", "task-review-1"))
        code, out = run("--dir", self.dir, "review", "--sha", sha, "--verdict", "approved", "--report", "r", "--task-evidence", self.evidence("task-review-1"), "--source", "fixture")
        self.assertEqual((code, out["phase"], out["approved_sha"]), (0, "review-approved", sha))
        code, status = run("--dir", self.dir, "status")
        self.assertEqual(status["evidence_class"], "fixture")  # fixture inputs never become a real smoke
        self.assertEqual([i["source"] for i in status["inputs"]], ["fixture"] * 6)  # the two refused reviewer binds were recorded too: every supplied input is kept
        self.assertEqual([i["payload"]["taskId"] for i in status["inputs"]], ["task-impl-1", "task-impl-1", "task-review-1", "task-review-1", "task-review-1", "task-review-1"])
        self.assertEqual(len(status["comments"]), 1)
        self.assertRegex(status["comments"][0], r"^<!-- unattended inst=[0-9a-f]{16} kind=claim op=claim run=smoke-run story=OM-99\.01 -->$")
        self.assertEqual([e["operation"] for e in status["log"]][:3], ["prepare", "restart", "bind"])

    def test_cancel_needs_terminal_evidence_and_restart_replays_release(self):
        code, out = run("--dir", self.dir, "prepare")
        auth = out["authorization"]
        run("--dir", self.dir, "bind", "--receipt", self.write("impl.json", IMPLEMENTER), "--worktree", str(self.dir / "worktree"), "--branch", "smoke/om-99-01", "--authorization", auth, "--source", "fixture")
        code, out = run("--dir", self.dir, "cancel", "--reason", "stop", "--source", "fixture")
        self.assertEqual((code, out["error"]["code"]), (3, "worker-not-terminal"))
        code, out = run("--dir", self.dir, "cancel", "--reason", "stop", "--task-evidence", self.evidence("task-impl-1", "cancel_requested"), "--source", "fixture")
        self.assertEqual((code, out["error"]["code"]), (3, "worker-not-terminal"))
        code, out = run("--dir", self.dir, "cancel", "--reason", "stop", "--task-evidence", self.evidence("task-impl-1", "cancelled"), "--source", "fixture")
        self.assertEqual((code, out["phase"], out["pending_intents"]), (0, "cancelled", []))
        code, out = run("--dir", self.dir, "restart")
        self.assertEqual((code, out["phase"]), (0, "cancelled"))
        code, status = run("--dir", self.dir, "status")
        self.assertEqual(len(status["comments"]), 2)  # claim + release, once each

    def test_unlaunched_authorization_is_owned_until_attested(self):
        code, out = run("--dir", self.dir, "prepare")
        auth = out["authorization"]
        code, out = run("--dir", self.dir, "cancel", "--reason", "never launched", "--source", "fixture")
        self.assertEqual((code, out["error"]["code"]), (3, "authorization-unresolved"))
        code, out = run("--dir", self.dir, "cancel", "--reason", "never launched", "--no-launch", self.write("nl.json", {"authorization": auth, "reason": "delegate_task was never called"}), "--source", "fixture")
        self.assertEqual((code, out["phase"]), (0, "cancelled"))

    def test_product_identities_and_live_transport_are_out_of_reach(self):
        run("--dir", self.dir, "prepare")
        policy = (self.dir / "policy.toml").read_text(encoding="utf-8")
        self.assertIn('allow = ["OM-99.01"]', policy)
        self.assertNotIn("OM-01", policy)
        transport = smoke.PersistedFakeTransport(self.dir / "transport.json")
        self.assertFalse(transport.live)
        self.assertEqual(sorted(transport.issues), [9900, 9901])
        run_json = json.loads((self.dir / "runs" / smoke.RUN_ID / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(run_json["environment"], "fixture")
        self.assertNotIn("subprocess.run([\"gh\"", (Path(smoke.__file__)).read_text(encoding="utf-8"))

    def test_prepare_refuses_reuse_and_source_is_mandatory(self):
        run("--dir", self.dir, "prepare")
        code, out = run("--dir", self.dir, "prepare")
        self.assertEqual(code, 3)
        with self.assertRaises(SystemExit):
            run("--dir", self.dir, "bind", "--receipt", self.write("impl.json", IMPLEMENTER))
        proc = subprocess.run(["python3", "-m", "automation.tests.lifecycle_smoke", "--dir", str(self.dir), "status"], capture_output=True, text=True, cwd=str(Path(smoke.__file__).resolve().parents[2]))
        self.assertEqual(proc.returncode, 0, proc.stderr)


class RepairRound1Tests(unittest.TestCase):
    """Findings of the fresh review of 92c42d51: durable persistence, bound worktree, syntax."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "smoke"
        self.files = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, payload) -> str:
        path = self.files / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return str(path)

    def test_interrupted_save_leaves_the_previous_complete_file(self):
        run("--dir", self.dir, "prepare")
        path = self.dir / "transport.json"
        before = path.read_text(encoding="utf-8")
        transport = smoke.PersistedFakeTransport(path)
        import os

        original = os.replace

        def interrupted(src, dst):
            raise OSError("simulated power loss before rename")

        os.replace = interrupted
        try:
            with self.assertRaises(OSError):
                transport.post_comment(9901, "lost")
        finally:
            os.replace = original
        self.assertEqual(path.read_text(encoding="utf-8"), before)  # never truncated, never partial
        self.assertEqual([p.name for p in self.dir.glob("transport.json*")], ["transport.json"])  # no temp file left behind
        reloaded = smoke.PersistedFakeTransport(path)
        self.assertEqual(len(reloaded.comments[9901]), 1)  # the claim marker from prepare

    def test_landed_comment_survives_a_crash_after_post(self):
        run("--dir", self.dir, "prepare")
        path = self.dir / "transport.json"
        transport = smoke.PersistedFakeTransport(path)
        transport.crash_after_post = True
        with self.assertRaises(smoke.CrashAfterEffect):
            transport.post_comment(9901, "<!-- unattended kind=probe op=x run=r story=OM-99.01 -->\nlanded")
        reloaded = smoke.PersistedFakeTransport(path)
        self.assertEqual([c.body.splitlines()[-1] for c in reloaded.comments[9901]][-1], "landed")  # persisted before the crash, like GitHub
        self.assertFalse(reloaded.crash_after_post)

    def test_check_uses_the_bound_worktree_not_the_prepared_one(self):
        from automation.tests.support import make_git_repo

        code, out = run("--dir", self.dir, "prepare")  # prepare creates a synthetic worktree …
        auth = out["authorization"]
        actual = self.files / "actual-checkout"  # … but the real T3 checkout is elsewhere
        sha = make_git_repo(actual, "smoke/om-99-01")
        code, out = run("--dir", self.dir, "bind", "--receipt", self.write("impl.json", IMPLEMENTER), "--worktree", str(actual), "--branch", "smoke/om-99-01", "--authorization", auth, "--source", "fixture")
        self.assertEqual((code, out["phase"]), (0, "claimed"))
        run("--dir", self.dir, "head", "--sha", sha, "--task-evidence", self.write("e.json", {"taskId": "task-impl-1", "runId": "task-impl-1:run:1", "status": "result_available"}), "--source", "fixture")
        code, out = run("--dir", self.dir, "check", "--sha", sha)
        self.assertEqual((code, out["phase"]), (0, "checks-passed"), out)
        self.assertEqual(out["checks"]["head_before"], sha)
        meta = json.loads((self.dir / "smoke.json").read_text(encoding="utf-8"))
        self.assertNotEqual(meta["worktree"], str(actual))  # the prepared path was not used

    def test_check_before_bind_is_refused(self):
        code, out = run("--dir", self.dir, "prepare")
        code, out = run("--dir", self.dir, "check", "--sha", out["baseline"])
        self.assertEqual(code, 3)
        self.assertIn("bind the implementer receipt first", out["error"]["message"])

    def test_documented_syntax_matches_the_parser(self):
        doc = smoke.__doc__
        examples = [line.strip() for line in doc.splitlines() if line.strip().startswith("python3 -m automation.tests.lifecycle_smoke")]
        self.assertGreaterEqual(len(examples), 11)
        parser = smoke.build_parser()
        for example in examples:
            argv = example.split("python3 -m automation.tests.lifecycle_smoke", 1)[1].split("(")[0].split()
            self.assertEqual(argv[:2], ["--dir", "D"], example)
            # the operation must be a known subcommand and --dir must precede it
            self.assertIn(argv[2], parser._subparsers._group_actions[0].choices, example)
            with self.assertRaises(SystemExit) as ctx:  # argparse exits 2 only for a syntax error; a parse error on the sample args is what we check next
                parser.parse_args([argv[2], "--dir", "D"])  # the old (wrong) order must not parse
            self.assertEqual(ctx.exception.code, 2)
        self.assertIn("evidence_class", doc)
        self.assertIn("declared", doc)

    def test_evidence_class_is_declared_provenance_not_success(self):
        code, out = run("--dir", self.dir, "prepare")
        # a rejected input declared "real" still counts as declared provenance only
        code, out = run("--dir", self.dir, "bind", "--receipt", self.write("bad.json", {"taskId": "x"}), "--worktree", str(self.dir / "worktree"), "--branch", "smoke/om-99-01", "--source", "real")
        self.assertEqual(code, 3)
        code, status = run("--dir", self.dir, "status")
        self.assertEqual(status["evidence_class"], "real")
        self.assertEqual(status["story"]["phase"], "reserved")  # nothing advanced
        self.assertEqual(status["log"][-1]["refused"]["code"], "receipt-invalid")


class LiveGateWordingTests(unittest.TestCase):
    def test_gate_reasons_state_the_agreement_not_superseded_prerequisites(self):
        from automation.tests.fake_transport import small_backlog
        from automation.tests.support import Harness
        from automation.unattended.coordinator import LIVE_EXECUTION_GAPS, OPERATING_AGREEMENT, Coordinator
        from automation.unattended.errors import Refused
        from automation.unattended.state import Store

        h = Harness(small_backlog())
        try:
            h.fake.live = True
            with self.assertRaises(Refused) as ctx:
                Coordinator(h.fake, h.policy, Store(h.state_dir, "run-live"), live=True)
            self.assertEqual(ctx.exception.code, "activation-required")
            self.assertEqual(ctx.exception.detail["agreement"], OPERATING_AGREEMENT)
            self.assertIn("2026-11-06", OPERATING_AGREEMENT)
            text = " ".join(LIVE_EXECUTION_GAPS)
            self.assertIn("accepting residual risk is not activation", str(ctx.exception))
            for superseded in ("hard deadline or resource bound on a delegated child", "no bounded GitHub credential has passed", "credential confinement of a delegated child is not established"):
                self.assertNotIn(superseded, text)
            self.assertIn("accepted residual risk, not a control", text)
            self.assertIn("manual by agreement", text)
            self.assertIn("opt-in only", text)
            self.assertIn("not a credential", text)
        finally:
            h.close()

    def test_permission_report_keeps_facts_separate_from_acceptance(self):
        from automation.unattended.probes import check_permissions

        def runner(argv, cwd, timeout):
            if argv[:3] == ["gh", "api", "-i"]:
                return subprocess.CompletedProcess(argv, 0, "HTTP/2.0 200\r\nx-oauth-scopes: repo, project\r\n\r\n" + json.dumps({"permissions": {"push": True, "admin": True}}), "")
            if argv[:3] == ["gh", "auth", "status"]:
                return subprocess.CompletedProcess(argv, 0, "ok", "")
            return subprocess.CompletedProcess(argv, 0, json.dumps({"data": {"repositoryOwner": {"projectV2": {"id": "P", "title": "t", "viewerCanUpdate": True}}}}), "")

        report = check_permissions("o", "r", "o", 2, runner)
        self.assertTrue(report["basic_access"])
        self.assertFalse(report["bounded"])
        self.assertFalse(report["unattended_activation_allowed"])
        self.assertIn("never certifies bounded or activation", report["owner_acceptance"])
