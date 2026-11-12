"""Regressions for the bmad-review findings on PR #108 (review 5827052511, 2026-11-09) on the
activation opt-in. Every scenario runs on the fixture transport marked live with temporary
state and an injected clock; no real GitHub call and no real task is ever made. The real CLI
transport is patched to count calls where the CLI is exercised."""

from __future__ import annotations

import dataclasses
import io
import json
import shutil
import unittest
from contextlib import contextmanager, redirect_stdout
from pathlib import Path
from unittest import mock

from automation.tests.fake_transport import small_backlog
from automation.tests.support import IMPLEMENTER, REVIEW_BRANCH, REVIEW_WORKTREE, REVIEWER, Harness, controlled_cli_clock, git_commit, ok_worktree, passing_runner, write_policy
from automation.tests.test_activation import CANDIDATE, CANDIDATE_POLICY, S, T0, LiveHarness, activation_text
from automation.tests.test_enabling_repair_1 import EXPIRED, POLICY, claimed, refuses
from automation.unattended import cli
from automation.unattended.activation import Activation, ActivationError, activation_use, ledger_path, load_activation, load_clearance
from automation.unattended.coordinator import Coordinator
from automation.unattended.errors import PolicyError
from automation.unattended.github import GhCliTransport
from automation.unattended.policy import load_policy
from automation.unattended.state import Store

REPO = "gabrianoo/owl-mast"


def run_cli(argv: list[str]) -> tuple[int, dict]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cli.main(argv)
    return code, json.loads(buf.getvalue())


@contextmanager
def no_gh_calls():
    """The real transport's process runner, replaced by a recorder: the test asserts it stays empty."""
    calls: list = []
    with mock.patch.object(GhCliTransport, "_run", lambda self, args, stdin=None: calls.append(args) or "{}"):
        yield calls


def cli_args(h: LiveHarness, *rest: str, activation: bool = True) -> list[str]:
    args = ["--policy", str(POLICY(h)), "--state-dir", str(h.h.state_dir), "--run-id", "run-live"]
    if activation:
        args += ["--activation", str(h.path)]
    return args + list(rest)


def review_authorized(h: LiveHarness) -> Coordinator:
    c = claimed(h)
    c.record_head(S, h.h.sha, h.terminal())
    c.run_checks(S, h.h.sha, str(h.h.worktree), passing_runner)
    c.authorize_review(S, h.h.sha)
    return c


class MissingFileIsNotARunStopTests(unittest.TestCase):
    """Findings 4513640212 / 4513640218 / 4513640228: an omitted --activation on a healthy run is a
    temporary refusal, never a permanent stop that spends slots, abandons intents or opens cleanup."""

    def setUp(self):
        self.h = LiveHarness()
        self.store = Store(self.h.h.state_dir, "run-live")

    def tearDown(self):
        self.h.close()

    def test_bind_receipt_without_the_file_refuses_before_any_state_change(self):
        review_authorized(self.h)
        before = self.store.story_counts()
        bare = self.h.coordinator(activation=None)
        self.h.h.fake.calls = []
        exc = refuses(self, lambda: bare.bind_receipt(S, REVIEWER, REVIEW_WORKTREE, REVIEW_BRANCH, ok_worktree), "activation-required")
        self.assertNotIn("bound_for_cleanup", exc.detail)
        state = self.store.load_story(S)
        self.assertEqual((state.phase, state.active_task, state.unresolved_authorization()["status"]), ("review-authorized", None, "pending"))
        self.assertEqual(self.store.story_counts(), before)
        self.assertNotIn(REVIEWER["taskId"], self.store.bound_task_ids())
        self.assertNotIn("receipt-bound-cleanup-only", [e["event"] for e in self.store.read_journal()])
        self.assertEqual(self.h.h.fake.calls, [])
        self.assertEqual(self.h.coordinator().bind_receipt(S, REVIEWER, REVIEW_WORKTREE, REVIEW_BRANCH, ok_worktree).phase, "review-requested")

    def test_bind_receipt_without_the_file_still_binds_for_cleanup_on_a_stopped_run(self):
        c = review_authorized(self.h)
        self.h.clock[0] = EXPIRED
        self.assertEqual(c.status()["activation"]["stop"], "activation-expired")  # the expiry is recorded durably
        bare = self.h.coordinator(activation=None)
        exc = refuses(self, lambda: bare.bind_receipt(S, REVIEWER, worktree_check=ok_worktree), "activation-expired")
        self.assertTrue(exc.detail["bound_for_cleanup"])
        self.assertEqual(self.store.load_story(S).active_task["taskId"], REVIEWER["taskId"])

    def test_reconcile_retained_execution_without_the_file_is_not_a_stopped_run(self):
        c = review_authorized(self.h)
        c.bind_receipt(S, REVIEWER, REVIEW_WORKTREE, REVIEW_BRANCH, ok_worktree)
        c.record_review(S, self.h.h.sha, "changes-requested", "r.md", self.h.terminal())
        auth = c.authorize_repair(S).unresolved_authorization()
        bare = self.h.coordinator(activation=None)
        refuses(self, lambda: bare.reconcile_retained_execution(S, auth["id"], {"taskId": IMPLEMENTER["taskId"]}, {"taskId": IMPLEMENTER["taskId"], "runId": "x", "status": "completed"}, "r", "p"), "run-not-stopped")
        self.assertEqual(self.store.load_story(S).unresolved_authorization()["status"], "pending")

    def test_bind_receipt_without_the_file_binds_a_revoked_authorization_for_cleanup_only(self):
        c = review_authorized(self.h)
        c.record_head(S, git_commit(self.h.h.worktree, "second"))  # a new head revokes the pending review authorization (evidence invalidated)
        self.assertEqual(self.store.load_story(S).unresolved_authorization()["status"], "revoked")
        bare = self.h.coordinator(activation=None)
        exc = refuses(self, lambda: bare.bind_receipt(S, REVIEWER, worktree_check=ok_worktree), "authorization-revoked")
        self.assertTrue(exc.detail["bound_for_cleanup"])  # a revoked authorization's late receipt is cleanup: it binds without the file, for cleanup only
        self.assertEqual(self.store.load_story(S).active_task["taskId"], REVIEWER["taskId"])

    def test_resume_without_the_file_defers_a_completed_claim_reconciliation(self):
        c = claimed(self.h)
        state = self.store.load_story(S)
        state.phase = "claim-incomplete"  # the claim comment landed; the reserved transition did not persist
        self.store.save_story(state)
        bare = self.h.coordinator(activation=None)
        self.h.h.fake.calls = []
        for _ in range(2):  # a deferred resume is a refusal, not a completed resume, and a repeated one adds no journal line
            exc = refuses(self, lambda: bare.resume(S, ok_worktree), "activation-required")
            self.assertEqual((exc.detail["deferred"], exc.detail["ops"]), (True, ["claim"]))
        self.assertEqual(self.h.h.fake.calls, [])  # nothing is read from or written to GitHub by a deferred resume (no revision check either)
        self.assertEqual(self.store.load_story(S).phase, "claim-incomplete")
        events = [e["event"] for e in self.store.read_journal()]
        self.assertEqual((events.count("reconciliation-deferred"), events.count("reconciliation-withheld")), (1, 0))
        self.assertEqual(c.resume(S, ok_worktree).phase, "reserved")  # the same document presented again completes the transition


class CheckActivationTests(unittest.TestCase):
    """Findings 4513640239 / 4513640249: the go/no-go command needs the run id and its success path is tested."""

    def setUp(self):
        self.h = LiveHarness()

    def tearDown(self):
        self.h.close()

    def test_check_activation_without_run_id_is_current_for_nothing(self):
        fresh = Path(self.h.h.tmpdir.name) / "cli-state"
        with controlled_cli_clock(self.h.clock), no_gh_calls() as calls:
            code, out = run_cli(["--policy", str(POLICY(self.h)), "--activation", str(self.h.path), "--state-dir", str(fresh), "check-activation"])
        self.assertEqual((code, out["current"], out["can_create"], out["stop"], out["run_id"]), (2, False, False, "activation-invalid", None))
        self.assertEqual(out["policy_digest"], self.h.h.policy.digest)  # the digest an activation must name is still reported
        self.assertFalse(fresh.exists())
        self.assertEqual(calls, [])

    def test_check_activation_success_path_reports_current_without_state_or_calls(self):
        fresh = Path(self.h.h.tmpdir.name) / "cli-state"
        with controlled_cli_clock(self.h.clock), no_gh_calls() as calls:
            code, out = run_cli(["--policy", str(POLICY(self.h)), "--activation", str(self.h.path), "--state-dir", str(fresh), "--run-id", "run-live", "check-activation", "--expect", "create"])
        self.assertEqual((code, out["current"], out["can_create"], out["run_exists"], out["stop"], out["problems"]), (0, True, True, False, None, []))
        self.assertEqual(out["activation"]["id"], "eng01-test-activation")
        self.assertFalse(fresh.exists())
        self.assertIsNone(activation_use(self.h.activation.digest, self.h.activation.path))  # read-only: the document is not used by a check
        self.assertEqual(calls, [])

    def test_check_activation_bound_to_another_run_is_not_current(self):
        with controlled_cli_clock(self.h.clock), no_gh_calls():
            code, out = run_cli(["--policy", str(POLICY(self.h)), "--activation", str(self.h.path), "--run-id", "run-other", "check-activation", "--expect", "create"])
        self.assertEqual((code, out["current"], out["stop"]), (2, False, "activation-mismatch"))

    def test_problems_never_skips_the_run_binding(self):
        for run_id in ("", None):
            problems = self.h.activation.problems(self.h.h.policy, run_id, T0)  # type: ignore[arg-type]
            self.assertEqual(Activation.stop_code(problems), "activation-invalid", run_id)
            self.assertFalse(any("is not this run" in m for _, m in problems), run_id)  # one problem for a missing run id, not a spurious mismatch too

    def test_problems_reports_run_id_and_digest_drift_together(self):
        drift_dir = Path(self.h.h.tmpdir.name) / "drift"
        drift_dir.mkdir()
        drifted = load_policy(write_policy(drift_dir, allow='["OM-01.02"]', max_delegated_tasks="7"))
        messages = "; ".join(m for _, m in self.h.activation.problems(drifted, "run-other", T0))
        self.assertIn("binding.policy_digest", messages)
        self.assertIn("binding.run_id", messages)

    def test_check_activation_reports_a_used_document(self):
        claimed(self.h)
        other = Path(self.h.h.tmpdir.name) / "other-state"
        with controlled_cli_clock(self.h.clock), no_gh_calls():
            code, out = run_cli(["--policy", str(POLICY(self.h)), "--activation", str(self.h.path), "--state-dir", str(other), "--run-id", "run-live", "check-activation", "--expect", "create"])
        self.assertEqual((code, out["current"], out["can_create"], out["stop"]), (2, False, False, "activation-used"))
        self.assertEqual(out["used"]["run_id"], "run-live")
        self.assertFalse(other.exists())


class EvidenceReferenceTests(unittest.TestCase):
    """Finding 4513640263: placeholder evidence never passes; a citation is a GitHub comment or review URL on the repository."""

    def test_committed_candidate_placeholders_are_reported(self):
        problems = load_activation(CANDIDATE).creation_problems(load_policy(CANDIDATE_POLICY), "r", T0)
        placeholders = [m for c, m in problems if c == "activation-invalid" and "placeholder" in m]
        self.assertEqual(len(placeholders), 2, problems)

    def test_placeholder_or_foreign_reference_refuses_creation(self):
        for label, over in (
            ("placeholder", dict(smoke='"REPLACE: published smoke reference"')),
            ("angle-brackets", dict(review='"<fresh review url>"')),
            ("foreign-host", dict(smoke='"https://example.com/smoke"')),
            ("foreign-repository", dict(review='"https://github.com/someone/else/pull/1#issuecomment-1"')),
            ("not-a-comment", dict(smoke=f'"https://github.com/{REPO}/pull/107"')),
        ):
            h = LiveHarness(**over)
            try:
                h.h.fake.calls = []
                exc = refuses(self, lambda: h.coordinator(), "activation-invalid")
                self.assertTrue(any("evidence." in m for m in exc.detail["problems"]), label)
                self.assertIsNone(Store(h.h.state_dir, "run-live").load_run(), label)
                self.assertEqual(h.h.fake.calls, [], label)
            finally:
                h.close()

    def test_issue_comment_and_review_urls_are_citations(self):
        h = LiveHarness(smoke=f'"https://github.com/{REPO}/issues/106#issuecomment-6706853226"', review=f'"https://github.com/{REPO}/pull/108#pullrequestreview-5827052511"')
        try:
            self.assertEqual(h.coordinator().status()["activation"]["problems"], [])
        finally:
            h.close()


class StatusWriteTests(unittest.TestCase):
    """Finding 4513640278: status is a locked write by default; --read-only takes no lock and records nothing."""

    def setUp(self):
        self.h = LiveHarness()
        self.c = claimed(self.h)
        self.store = Store(self.h.h.state_dir, "run-live")

    def tearDown(self):
        self.h.close()

    def test_read_only_status_reports_a_would_be_stop_without_recording_it(self):
        before = self.store.run_path.read_bytes()
        self.h.clock[0] = EXPIRED
        report = self.c.status(read_only=True)
        self.assertTrue(report["read_only"])
        self.assertEqual(report["activation"]["would_stop"]["code"], "activation-expired")
        self.assertIsNone(report["activation"]["recorded_stop"])
        self.assertEqual(self.store.run_path.read_bytes(), before)
        self.assertNotIn("activation-stopped", [e["event"] for e in self.store.read_journal()])
        self.assertEqual(self.c.status()["activation"]["recorded_stop"]["code"], "activation-expired")  # the locked form records it

    def test_read_only_status_never_moves_the_high_water_mark(self):
        self.h.clock[0] = "2026-11-07T12:00:00Z"
        self.c.status(read_only=True)
        self.assertIsNone(self.store.load_run().last_observed_at)
        self.c.status()
        self.assertEqual(self.store.load_run().last_observed_at, "2026-11-07T12:00:00Z")

    def test_read_only_status_runs_while_another_coordinator_holds_the_lock(self):
        with Store(self.h.h.state_dir, "run-live").locked():
            refuses(self, lambda: self.c.status(), "store-busy")
            self.assertEqual(self.c.status(read_only=True)["activation"]["would_stop"], None)

    def test_cli_status_read_only(self):
        self.h.clock[0] = EXPIRED
        with controlled_cli_clock(self.h.clock), no_gh_calls() as calls:
            code, out = run_cli(cli_args(self.h, "status", "--read-only"))
        self.assertEqual((code, out["read_only"], out["activation"]["would_stop"]["code"], out["activation"]["recorded_stop"]), (0, True, "activation-expired", None))
        self.assertEqual(calls, [])


class ClearClockRegressionTests(unittest.TestCase):
    """Finding 4513640293: a backward clock step is recoverable by a journaled owner action; expiry is not."""

    def setUp(self):
        self.h = LiveHarness()
        self.c = claimed(self.h)
        self.store = Store(self.h.h.state_dir, "run-live")

    def tearDown(self):
        self.h.close()

    def regress(self):
        self.h.clock[0] = "2026-11-07T12:00:00Z"
        self.c.status()  # high-water mark 12:00
        self.h.clock[0] = "2026-11-07T11:00:00Z"  # the host clock corrected itself backwards by an hour
        refuses(self, lambda: self.c.record_head(S, self.h.h.sha, self.h.terminal()), "clock-regression")
        self.assertEqual(self.store.load_run().activation_stop["code"], "clock-regression")

    def clearance(self, h=None, **over) -> dict:
        h = h or self.h
        stop = Store(h.h.state_dir, "run-live").load_run().activation_stop or {}
        fields = {"run_id": "run-live", "activation_id": "eng01-test-activation", "approver": "owner (fixture)", "stop_observed_at": stop.get("observed_at", "none"), "reason": "WSL2 clock resynced after resume; verified by the owner", **over}
        path = Path(h.h.tmpdir.name) / "clearance.toml"
        path.write_text("".join(f"{key} = {json.dumps(value)}\n" for key, value in fields.items()), encoding="utf-8")
        return load_clearance(path)

    def test_clear_needs_the_presented_current_activation_and_restores_advancement(self):
        self.regress()
        self.h.clock[0] = "2026-11-07T11:56:00Z"  # back within the tolerance of the 12:00 high-water mark
        refuses(self, lambda: self.h.coordinator(activation=None).clear_clock_regression(self.clearance()), "activation-required")
        self.assertEqual(self.store.load_run().activation_stop["code"], "clock-regression")
        report = self.c.clear_clock_regression(self.clearance())
        run = self.store.load_run()
        self.assertEqual((run.activation_stop, run.last_observed_at, report["cleared"]["code"]), (None, "2026-11-07T12:00:00Z", "clock-regression"))  # the high-water mark is kept, never lowered
        events = [e for e in self.store.read_journal() if e["event"] == "activation-stop-cleared"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["detail"]["reason"], "WSL2 clock resynced after resume; verified by the owner")
        self.assertEqual(events[0]["detail"]["clearance"]["stop_observed_at"], "2026-11-07T11:00:00Z")
        self.assertEqual(self.c.record_head(S, self.h.h.sha, self.h.terminal()).phase, "implemented")

    def test_clear_refuses_without_a_stop_and_never_clears_expiry(self):
        refuses(self, lambda: self.c.clear_clock_regression(self.clearance()), "no-stop-recorded")
        self.h.clock[0] = EXPIRED
        refuses(self, lambda: self.c.record_head(S, self.h.h.sha, self.h.terminal()), "activation-expired")
        refuses(self, lambda: self.c.clear_clock_regression(self.clearance()), "activation-expired")
        self.assertEqual(self.store.load_run().activation_stop["code"], "activation-expired")

    def test_clear_refuses_when_the_presented_activation_is_not_current_at_this_observation(self):
        self.regress()
        self.h.clock[0] = EXPIRED  # by the time the owner reacts, the window is over
        refuses(self, lambda: self.c.clear_clock_regression(self.clearance()), "activation-expired")
        self.assertEqual(self.store.load_run().activation_stop["code"], "clock-regression")

    def test_clear_refuses_on_a_cancelled_run_and_after_the_wall_clock(self):
        h = LiveHarness(issued="2026-11-07T08:00:00Z", expires="2026-11-07T20:00:00Z")  # a long window: the wall clock (240 min) runs out before the approval does
        try:
            c = claimed(h)
            store = Store(h.h.state_dir, "run-live")
            h.clock[0] = "2026-11-07T12:00:00Z"
            c.status()
            h.clock[0] = "2026-11-07T11:00:00Z"
            refuses(self, lambda: c.record_head(S, h.h.sha, h.terminal()), "clock-regression")
            h.clock[0] = "2026-11-07T14:30:00Z"  # 270 minutes after the start: the wall clock is over
            refuses(self, lambda: c.clear_clock_regression(self.clearance(h)), "wall-clock-exceeded")
            self.assertEqual(store.load_run().activation_stop["code"], "clock-regression")
            h.clock[0] = "2026-11-07T12:30:00Z"
            c.cancel_run("owner stop")
            refuses(self, lambda: c.clear_clock_regression(self.clearance(h)), "run-cancelled")
            self.assertEqual(store.load_run().activation_stop["code"], "clock-regression")
        finally:
            h.close()

    def test_cli_clear_clock_regression(self):
        path = Path(self.h.h.tmpdir.name) / "clearance.toml"
        self.clearance()
        with controlled_cli_clock(self.h.clock), no_gh_calls():
            code, out = run_cli(cli_args(self.h, "clear-clock-regression", "--clearance", str(path)))
            self.assertEqual((code, out["error"]["code"]), (3, "no-stop-recorded"))
            code, out = run_cli(cli_args(self.h, "clear-clock-regression"))
            self.assertEqual((code, out["error"]["code"]), (3, "input-invalid"))  # no clearance, no clear: a reason on the command line is not an owner action
            path.write_text('run_id = "run-live"\n', encoding="utf-8")
            code, out = run_cli(cli_args(self.h, "clear-clock-regression", "--clearance", str(path)))
            self.assertEqual((code, out["error"]["code"]), (3, "clearance-invalid"))


class ClockSourceTests(unittest.TestCase):
    """Findings 4513640306 / 4513640435: one creation observation for the run and the binding; a malformed started_at refuses."""

    def test_started_at_is_the_validated_creation_observation(self):
        h = LiveHarness()
        try:
            h.coordinator()
            run = Store(h.h.state_dir, "run-live").load_run()
            self.assertEqual((run.started_at, run.activation["validated_at"]), (T0, T0))
        finally:
            h.close()

    def test_malformed_started_at_refuses_structurally(self):
        for value in ("2026-11-07 10:00:00", "2026-11-07T10:00:00", "soon", ""):
            h = LiveHarness()
            try:
                claimed(h)
                store = Store(h.h.state_dir, "run-live")
                raw = json.loads(store.run_path.read_text(encoding="utf-8"))
                raw["started_at"] = value
                store.run_path.write_text(json.dumps(raw), encoding="utf-8")
                refuses(self, lambda: h.coordinator(), "run-state-invalid")
                refuses(self, lambda: h.coordinator(activation=None), "run-state-invalid")
            finally:
                h.close()


class RunOpenRefreshTests(unittest.TestCase):
    """Findings 4513640321 / 4513640333: reopening a run re-reads the source; an activation always has a source."""

    def setUp(self):
        self.h = LiveHarness()
        claimed(self.h)
        self.store = Store(self.h.h.state_dir, "run-live")
        self.policy = self.h.h.policy

    def tearDown(self):
        self.h.close()

    def ensure(self, activation):
        return self.store.ensure_run(self.policy.repo_slug, self.policy.digest, "live", activation=activation, policy=self.policy, now=T0)

    def test_store_ensure_run_re_reads_a_changed_or_malformed_source_for_an_existing_run(self):
        stale = self.h.activation  # loaded before the edits below; it matches the recorded binding in memory
        self.h.path.write_text(self.h.path.read_text().replace("approved = true", "approved = false"), encoding="utf-8")
        refuses(self, lambda: self.ensure(stale), "activation-mismatch")
        self.h.path.write_text("approved = \n", encoding="utf-8")
        refuses(self, lambda: self.ensure(stale), "activation-invalid")
        self.h.path.unlink()
        self.assertEqual(self.ensure(stale).run_id, "run-live")  # nothing is presented any more: the run opens on its recorded binding
        self.h.path.write_text(activation_text(self.policy), encoding="utf-8")
        self.assertEqual(self.ensure(stale).run_id, "run-live")

    def test_an_activation_without_a_source_path_cannot_exist(self):
        with self.assertRaises(ActivationError) as ctx:  # inside the CLI's JSON error contract, never a bare ValueError
            Activation(**{**dataclasses.asdict(self.h.activation), "path": ""})
        self.assertEqual(ctx.exception.code, "activation-invalid")


class WindowCoverageTests(unittest.TestCase):
    """Finding 4513640355: the remaining window must cover the wall-clock budget at creation, and only then."""

    def test_short_window_refuses_creation_and_check_activation(self):
        h = LiveHarness(expires="2026-11-07T11:00:00Z")  # 60 minutes left, budget 240
        try:
            h.h.fake.calls = []
            refuses(self, lambda: h.coordinator(), "activation-window-short")
            self.assertIsNone(Store(h.h.state_dir, "run-live").load_run())
            self.assertEqual(h.h.fake.calls, [])
            with controlled_cli_clock(h.clock), no_gh_calls():
                code, out = run_cli(cli_args(h, "check-activation", "--expect", "create"))
            self.assertEqual((code, out["current"], out["stop"]), (2, False, "activation-window-short"))
            self.assertEqual(h.activation.problems(h.h.policy, "run-live", T0), [])  # current, just too short to start a run
        finally:
            h.close()

    def test_coverage_is_not_rechecked_mid_run(self):
        h = LiveHarness()
        try:
            c = claimed(h)
            h.clock[0] = "2026-11-07T13:30:00Z"  # 30 minutes left in the window
            self.assertEqual(c.record_head(S, h.h.sha, h.terminal()).phase, "implemented")
        finally:
            h.close()


class LiveHelpTests(unittest.TestCase):
    """Finding 4513640367: the --live help lists every command that can reach a GitHub write."""

    def test_live_help_is_built_from_write_commands(self):
        live = next(a for a in cli.build_parser()._actions if "--live" in a.option_strings)  # the option's own help, not the whole usage (which lists every subcommand anyway)
        for command in cli.WRITE_COMMANDS:
            self.assertIn(command, live.help)
        self.assertIn("propose-evidence", live.help)


class UnlockedSnapshotTests(unittest.TestCase):
    """Finding 4513640411: the GitHub snapshot between the CLI pre-gate and reserve runs unlocked; reserve re-gates."""

    def setUp(self):
        self.h = LiveHarness()
        self.store = Store(self.h.h.state_dir, "run-live")

    def tearDown(self):
        self.h.close()

    def reserve_with_snapshot(self, during_snapshot):
        def snapshot(transport, repo, taken_at):
            during_snapshot()
            return self.h.h.snapshot
        with controlled_cli_clock(self.h.clock), no_gh_calls() as calls, mock.patch.object(cli, "take_snapshot", snapshot):
            code, out = run_cli(cli_args(self.h, "--live", "reserve", S, "--baseline", "c5d9d2e"))
        return code, out, calls

    def test_activation_expiring_during_the_snapshot_refuses_reserve_with_no_write(self):
        code, out, calls = self.reserve_with_snapshot(lambda: self.h.clock.__setitem__(0, EXPIRED))
        self.assertEqual((code, out["error"]["code"]), (3, "activation-expired"))
        self.assertIsNone(self.store.load_story(S))
        self.assertEqual(self.store.load_run().activation_stop["code"], "activation-expired")
        self.assertEqual(calls, [])

    def test_activation_edited_during_the_snapshot_refuses_reserve_with_no_write(self):
        code, out, calls = self.reserve_with_snapshot(lambda: self.h.path.write_text(self.h.path.read_text().replace("approved = true", "approved = false"), encoding="utf-8"))
        self.assertEqual((code, out["error"]["code"]), (3, "activation-mismatch"))
        self.assertIsNone(self.store.load_story(S))
        self.assertEqual(calls, [])


class OneActivationOneRunTests(unittest.TestCase):
    """Finding 4513640423: a use ledger keyed on the document digest makes a second live run from it impossible."""

    def ledger(self) -> Path:
        return ledger_path(self.h.activation.digest, self.h.activation.path)

    def setUp(self):
        self.h = LiveHarness()
        self.c = claimed(self.h)
        self.store = Store(self.h.h.state_dir, "run-live")

    def tearDown(self):
        self.h.close()

    def test_ledger_is_written_at_creation_and_confirmed(self):
        ledger = json.loads(self.ledger().read_text(encoding="utf-8"))
        self.assertEqual((ledger["run_id"], ledger["digest"], ledger["state_dir"], ledger["created_at"], ledger["state"]), ("run-live", self.h.activation.digest, str(self.h.h.state_dir.resolve()), T0, "committed"))
        self.assertEqual(self.ledger().name, self.h.activation.digest + ".json")  # keyed on the content, not on the file name

    def test_second_state_dir_refuses(self):
        other = Store(Path(self.h.h.tmpdir.name) / "runs-2", "run-live")
        self.h.h.fake.calls = []
        exc = refuses(self, lambda: Coordinator(self.h.h.fake, self.h.h.policy, other, now=lambda: T0, live=True, activation=self.h.activation), "activation-used")
        self.assertIn(str(self.ledger()), str(exc))
        other.state_dir.mkdir()  # the locked creation (not only the coordinator's pre-check) refuses a direct Store creation too
        exc = refuses(self, lambda: other.ensure_run(self.h.h.policy.repo_slug, self.h.h.policy.digest, "live", activation=self.h.activation, policy=self.h.h.policy, now=T0), "activation-used")
        self.assertIsNone(other.load_run())
        self.assertEqual(self.h.h.fake.calls, [])

    def test_deleted_run_directory_does_not_refund_the_activation(self):
        shutil.rmtree(self.store.root)
        refuses(self, lambda: self.h.coordinator(), "activation-used")
        self.assertIsNone(self.store.load_run())
        self.assertTrue(self.ledger().exists())

    def test_the_existing_run_keeps_working_with_its_ledger(self):
        self.assertEqual(self.c.record_head(S, self.h.h.sha, self.h.terminal()).phase, "implemented")
        self.assertEqual(self.h.coordinator().status()["activation"]["stop"], None)


class RebaseRevisionsStopTests(unittest.TestCase):
    """Finding 4513640440: rebase-revisions on a cancelled run rewrites nothing."""

    def test_cancelled_run_refuses_rebase(self):
        h = Harness(small_backlog())
        try:
            h.claim()
            h.coordinator.cancel_run("stop")
            before = h.store.load_story(S).revisions
            refuses(self, lambda: h.coordinator.rebase_revisions(S, "x"), "run-cancelled")
            self.assertEqual(h.store.load_story(S).revisions, before)
        finally:
            h.close()

    def test_cancelled_live_run_refuses_rebase(self):
        h = LiveHarness()
        try:
            c = claimed(h)
            c.cancel_run("stop")
            refuses(self, lambda: c.rebase_revisions(S, "x"), "run-cancelled")
        finally:
            h.close()

    def test_recorded_activation_stop_refuses_rebase(self):
        h = LiveHarness()
        try:
            c = claimed(h)
            h.clock[0] = EXPIRED
            refuses(self, lambda: c.rebase_revisions(S, "x"), "activation-expired")
            self.assertEqual(Store(h.h.state_dir, "run-live").load_run().activation_stop["code"], "activation-expired")
        finally:
            h.close()


class TargetOptionTypingTests(unittest.TestCase):
    """Unanchored finding: policy and activation compare target options under one typing rule."""

    def test_policy_refuses_non_string_option_values(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = write_policy(Path(tmp), options='{ effort = "high", timeoutMs = 600000 }')
            with self.assertRaises(PolicyError) as ctx:
                load_policy(path)
            self.assertIn("string values", str(ctx.exception))
            self.assertEqual(load_policy(write_policy(Path(tmp), options='{ effort = "high", timeoutMs = "600000" }')).implementer.options, {"effort": "high", "timeoutMs": "600000"})


if __name__ == "__main__":
    unittest.main()
