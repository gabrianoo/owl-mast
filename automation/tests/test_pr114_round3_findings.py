"""Regressions for PR #114 round 3: review 5851770529 (19 threads) and the two reopened threads
(r4531696320 self-clear, r4531696403 stale spec-gh-108). One class per finding, each test named
after the behaviour it pins. Every scenario runs on the fixture transport marked live with
temporary state and an injected clock; no real GitHub call and no real task is ever made, and no
test writes to the real use ledger under the home directory."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest import mock

import automation.tests as tests_package
from automation.tests import PRODUCTION_LEDGER_ROOT
from automation.tests.fake_transport import FakeTransport
from automation.tests.support import REVIEW_BRANCH, REVIEW_WORKTREE, REVIEWER, ok_worktree, controlled_cli_clock, write_policy
from automation.tests.test_activation import S, T0, LiveHarness
from automation.tests.test_enabling_repair_1 import POLICY, claimed, refuses
from automation.tests.test_pr108_review_findings import cli_args, no_gh_calls, review_authorized, run_cli
from automation.tests.test_pr114_review_findings import LONG_WINDOW, LiveCase, clearance, regress
from automation.tests.test_pr115_review_findings import arm_failure_after_claim
from automation.unattended import activation as activation_module
from automation.unattended import state as state_module
from automation.unattended.activation import Activation, activation_use, ledger_path, ledger_root, load_activation, load_clearance, record_activation_use
from automation.unattended.coordinator import Coordinator
from automation.unattended.errors import Conflict, Outage
from automation.unattended.github import PullRequestRecord
from automation.unattended.policy import load_policy
from automation.unattended.state import Store

REPO = "gabrianoo/owl-mast"


def record(h: LiveHarness) -> dict | None:
    return activation_use(h.activation.digest, h.activation.path)


def write_clearance(path: Path, h: LiveHarness) -> Path:
    stop = Store(h.h.state_dir, "run-live").load_run().activation_stop
    fields = {"run_id": "run-live", "activation_id": "eng01-test-activation", "approver": "owner (fixture)", "stop_observed_at": stop["observed_at"], "reason": "clock resynced"}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{key} = {json.dumps(value)}\n" for key, value in fields.items()), encoding="utf-8")
    return path


# -- fix-first 1 and threads ii, ka: the use ledger states ------------------------------------------------------------
class UnconfirmedCreationTests(LiveCase):
    """A run created from a document whose ledger record could not be confirmed is never created
    twice: the confirmation failure is journaled, the record stays `pending`, and a `pending`
    record without run.json refuses as an unconfirmed creation (thread ii)."""

    def test_a_failed_confirmation_is_journaled_and_a_deleted_run_refuses_as_unconfirmed(self):
        original = activation_module._write_ledger

        def confirm_fails(path, rec, replace):
            if replace:
                raise OSError(28, "No space left on device")
            return original(path, rec, replace)

        with mock.patch.object(activation_module, "_write_ledger", confirm_fails):
            self.assertEqual(self.h.coordinator().run.run_id, "run-live")  # run.json exists: the creation itself stands
        self.assertEqual(record(self.h)["state"], "pending")
        unconfirmed = [e for e in self.store.read_journal() if e["event"] == "activation-use-unconfirmed"]
        self.assertEqual(len(unconfirmed), 1)
        self.assertIn("No space left", unconfirmed[0]["detail"]["error"])
        shutil.rmtree(self.store.root)  # the run directory is deleted before any reopen confirmed the record
        exc = refuses(self, lambda: self.h.coordinator(), "activation-used")
        self.assertIn("unconfirmed", str(exc))
        self.assertIsNone(self.store.load_run())

    def test_a_process_that_died_between_the_ledger_and_run_json_refuses_as_unconfirmed(self):
        record_activation_use(self.h.activation, self.h.h.state_dir, "run-live", T0)  # LABELLED MUTATION: the process died right after the ledger write
        exc = refuses(self, lambda: self.h.coordinator(), "activation-used")
        self.assertIn("unconfirmed", str(exc))
        self.assertIn("run-live", str(exc))
        self.assertIn(str(self.h.h.state_dir.resolve()), str(exc))
        self.assertIsNone(self.store.load_run())

    def test_a_reopen_confirms_a_pending_or_aborted_record_of_its_run(self):
        self.h.coordinator()
        path = ledger_path(self.h.activation.digest, self.h.activation.path)
        for state in ("pending", "aborted"):
            path.write_text(json.dumps({**json.loads(path.read_text(encoding="utf-8")), "state": state}), encoding="utf-8")  # LABELLED MUTATION
            self.h.coordinator(activation=None)
            self.assertEqual(record(self.h)["state"], "committed", state)


class AbortedCreationTests(LiveCase):
    """A creation whose run.json was never written is `aborted`: only that same creation retries,
    and every other one is told which creation failed and how to retry it (threads ii, ka)."""

    def fail_creation(self):
        with mock.patch.object(Store, "save_run", side_effect=OSError(28, "No space left on device")):
            with self.assertRaises(OSError):
                self.h.coordinator()

    def test_a_failed_save_marks_the_record_aborted_and_only_that_creation_retries(self):
        self.fail_creation()
        self.assertEqual(record(self.h)["state"], "aborted")
        other = Store(Path(self.h.h.tmpdir.name) / "runs-2", "run-live")
        exc = refuses(self, lambda: Coordinator(self.h.h.fake, self.h.h.policy, other, now=lambda: self.h.clock[0], live=True, activation=self.h.activation), "activation-used")
        self.assertIn("failed", str(exc))
        self.assertIn(f"--run-id run-live --state-dir {self.h.h.state_dir.resolve()}", str(exc))  # how to retry it
        problems = [m for code, m in self.h.activation.creation_problems(self.h.h.policy, "run-other", T0, state_dir=self.h.h.state_dir) if code == "activation-used"]
        self.assertEqual(len(problems), 1)  # another run id under the same state directory: the same named refusal
        self.assertIn("aborted", problems[0])
        self.assertEqual(self.h.coordinator().run.run_id, "run-live")  # the same creation, retried
        self.assertEqual(record(self.h)["state"], "committed")

    def test_a_retry_that_dies_again_is_pending_and_refuses(self):
        self.fail_creation()
        with mock.patch.object(Store, "save_run", side_effect=SystemExit("killed")), mock.patch.object(state_module, "abort_activation_use", return_value=False):  # the process dies inside the retry
            with self.assertRaises(SystemExit):
                self.h.coordinator()
        self.assertEqual(record(self.h)["state"], "pending")  # the retry set it pending again before run.json
        refuses(self, lambda: self.h.coordinator(), "activation-used")

    def test_a_marking_failure_leaves_the_record_pending_and_reraises_the_original_error(self):
        original = activation_module._write_ledger

        def abort_fails(path, rec, replace):
            if replace and rec.get("state") == "aborted":
                raise OSError(5, "Input/output error")
            return original(path, rec, replace)

        with mock.patch.object(Store, "save_run", side_effect=OSError(28, "No space left on device")), mock.patch.object(activation_module, "_write_ledger", abort_fails):
            with self.assertRaises(OSError) as ctx:
                self.h.coordinator()
        self.assertEqual(ctx.exception.errno, 28)
        self.assertEqual(record(self.h)["state"], "pending")


# -- threads i0 and i5: per-user ledger and its root ------------------------------------------------------------------
class LedgerRootTests(LiveCase):
    """The ledger is per user account and machine and says where it is; an account without a
    passwd entry is a coded refusal, never a crash (threads i0, i5)."""

    def test_check_activation_and_status_print_the_ledger_root_and_record(self):
        with controlled_cli_clock(self.h.clock), no_gh_calls():
            code, out = run_cli(cli_args(self.h, "check-activation"))
        self.assertEqual((code, out["ledger_root"], out["used"]), (0, str(ledger_root(self.h.activation.path)), None))
        c = claimed(self.h)
        ledger = c.status()["activation"]["ledger"]
        self.assertEqual((ledger["root"], ledger["record"]["state"]), (str(ledger_root(self.h.activation.path)), "committed"))
        self.assertEqual(c.status(read_only=False)["activation"]["ledger"]["record"]["run_id"], "run-live")

    def test_a_uid_without_an_account_entry_refuses_instead_of_crashing(self):
        with mock.patch.object(activation_module, "ledger_root", PRODUCTION_LEDGER_ROOT), mock.patch.object(activation_module.pwd, "getpwuid", side_effect=KeyError("getpwuid(): uid not found: 4242")):
            refuses(self, lambda: ledger_path("d" * 64, "x.toml"), "activation-ledger-unwritable")
            refuses(self, lambda: self.h.coordinator(), "activation-ledger-unwritable")
            with controlled_cli_clock(self.h.clock), no_gh_calls():
                code, out = run_cli(cli_args(self.h, "check-activation"))
        self.assertEqual(code, 2)  # a negative answer, not an internal error (exit 4)
        self.assertIn("activation-ledger-unwritable", out["stops"])
        self.assertIsNone(out["ledger_root"])
        self.assertIsNone(self.store.load_run())


# -- fix-first 2, r4531696320: clearance placement and plain wording --------------------------------------------------
class ClearancePlacementTests(LiveCase):
    """Owner-only is a convention; a clearance inside the state directory or a repository work
    tree is refused (reopened thread r4531696320)."""

    def setUp(self):
        super().setUp()
        self.c = claimed(self.h)
        regress(self, self.h, self.c)
        self.h.clock[0] = "2026-11-07T11:58:00Z"

    def test_a_clearance_inside_the_state_directory_is_refused(self):
        inside = write_clearance(self.h.h.state_dir / "clearance.toml", self.h)
        refuses(self, lambda: load_clearance(inside, refuse_inside={"--state-dir": self.h.h.state_dir}), "clearance-invalid")
        refuses(self, lambda: self.c.clear_clock_regression(load_clearance(inside)), "clearance-invalid")  # the coordinator checks its own state directory too
        with controlled_cli_clock(self.h.clock), no_gh_calls():
            code, out = run_cli(cli_args(self.h, "clear-clock-regression", "--clearance", str(inside)))
        self.assertEqual((code, out["error"]["code"]), (3, "clearance-invalid"))
        self.assertEqual(self.store.load_run().activation_stop["code"], "clock-regression")

    def test_a_clearance_inside_a_repository_work_tree_is_refused(self):
        repo = Path(self.h.h.tmpdir.name) / "checkout"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        inside = write_clearance(repo / "notes" / "clearance.toml", self.h)
        with controlled_cli_clock(self.h.clock), no_gh_calls():
            code, out = run_cli(cli_args(self.h, "--repo-root", str(repo), "clear-clock-regression", "--clearance", str(inside)))
        self.assertEqual((code, out["error"]["code"]), (3, "clearance-invalid"))
        outside = write_clearance(Path(self.h.h.tmpdir.name) / "owner" / "clearance.toml", self.h)
        with controlled_cli_clock(self.h.clock), no_gh_calls():
            code, out = run_cli(cli_args(self.h, "--repo-root", str(repo), "clear-clock-regression", "--clearance", str(outside)))
        self.assertEqual((code, out["run"]["activation_stop"]), (0, None))

    def test_the_help_and_the_docs_say_owner_only_is_a_convention(self):
        from automation.unattended.cli import build_parser

        commands = next(a for a in build_parser()._actions if a.dest == "command")
        text = next(c.help for c in commands._choices_actions if c.dest == "clear-clock-regression")
        self.assertIn("convention", text)
        self.assertIn("--state-dir", text)
        docs = (Path(__file__).resolve().parents[2] / "docs" / "unattended-execution.md").read_text(encoding="utf-8")
        self.assertIn("Owner-only is a convention on the trusted machine, not a control", docs)
        self.assertNotIn("The unattended loop holds the activation but is never given a clearance", docs)


# -- fix-first 3, threads io and jw: the clear's write-ahead and its wall clock ---------------------------------------
class ClearWriteAheadTests(LiveCase):
    """The one clear is spent only by a clear that happened; a failed save leaves it to retry
    (thread io)."""

    def setUp(self):
        super().setUp()
        self.c = claimed(self.h)
        regress(self, self.h, self.c)
        self.h.clock[0] = "2026-11-07T11:58:00Z"

    def regress_again(self):
        self.h.clock[0] = "2026-11-07T13:00:00Z"
        self.c.status()
        self.h.clock[0] = "2026-11-07T12:10:00Z"
        refuses(self, lambda: self.c.rebase_revisions(S, "x"), "clock-regression")
        self.h.clock[0] = "2026-11-07T12:58:00Z"

    def test_a_clear_whose_save_fails_is_not_spent_and_may_be_retried(self):
        with mock.patch.object(Store, "save_run", side_effect=OSError(28, "No space left on device")):
            with self.assertRaises(OSError):
                self.c.clear_clock_regression(clearance(self.h))
        self.assertEqual(self.store.load_run().activation_stop["code"], "clock-regression")
        events = [e["event"] for e in self.store.read_journal()]
        self.assertIn("activation-stop-clear-started", events)
        self.assertNotIn("activation-stop-cleared", events)
        self.assertIsNone(self.c.clear_clock_regression(clearance(self.h))["run"]["activation_stop"])  # the retry of the same stop proceeds
        self.regress_again()
        refuses(self, lambda: self.c.clear_clock_regression(clearance(self.h)), "clock-clear-exhausted")  # after a clear that happened, a second stop is exhausted

    def test_a_clear_whose_confirming_line_was_lost_is_spent(self):
        original = Store.journal

        def lose_cleared(store, story, event, detail=None):
            if event == "activation-stop-cleared":
                raise OSError(28, "No space left on device")
            return original(store, story, event, detail)

        with mock.patch.object(Store, "journal", lose_cleared):
            with self.assertRaises(OSError):
                self.c.clear_clock_regression(clearance(self.h))
        self.assertIsNone(self.store.load_run().activation_stop)  # the save went through
        self.regress_again()
        refuses(self, lambda: self.c.clear_clock_regression(clearance(self.h)), "clock-clear-exhausted")  # a clear-started line for an earlier stop is a clear that happened


class ClearWallClockOnHighWaterTests(LiveCase):
    """The clear judges the wall clock on the later of the clock and the high-water mark: a clock
    still within the tolerance behind never buys time (thread jw)."""

    OVER = LONG_WINDOW  # approval until 20:00; the 240-minute wall clock ends at 14:00

    def test_a_run_over_budget_at_the_high_water_mark_is_not_cleared(self):
        c = claimed(self.h)
        self.h.clock[0] = "2026-11-07T14:02:00Z"
        c.status()  # high-water mark 14:02, two minutes past the wall clock
        self.h.clock[0] = "2026-11-07T12:00:00Z"
        refuses(self, lambda: c.rebase_revisions(S, "x"), "clock-regression", "wall-clock-exceeded")
        self.assertEqual(self.store.load_run().activation_stop["code"], "clock-regression")
        self.h.clock[0] = "2026-11-07T13:58:00Z"  # within the 5-minute tolerance of 14:02, and 238 minutes after the start on this clock
        exc = refuses(self, lambda: c.clear_clock_regression(clearance(self.h)), "wall-clock-exceeded")
        self.assertIn("14:02:00Z", str(exc))
        self.assertEqual(self.store.load_run().activation_stop["code"], "clock-regression")


# -- fix-first 4, thread jU: a clearable clock stop defers ------------------------------------------------------------
class ClearableClockStopTests(LiveCase):
    """Under a clock-regression stop the owner can still clear, resume defers and a work bind binds
    nothing, so the clear restores the run intact (thread jU)."""

    def pending_proposal(self) -> Coordinator:
        c = review_authorized(self.h)
        c.bind_receipt(S, REVIEWER, REVIEW_WORKTREE, REVIEW_BRANCH, ok_worktree)
        c.record_review(S, self.h.h.sha, "approved", "report.md", self.h.terminal())
        self.h.h.fake.pull_requests[7] = PullRequestRecord(7, "OPEN", self.h.h.sha, False, (), "SUCCESS")
        self.h.h.fake.fail_once["post_comment"] = Outage("503 on the proposal post")
        with self.assertRaises(Outage):
            c.propose_evidence(S, self.h.h.sha, 7, [], "s")
        self.assertEqual([i.status for i in self.store.load_story(S).pending_advancing_intents()], ["pending"])
        return c

    def test_resume_defers_under_a_clearable_clock_stop_and_completes_after_the_clear(self):
        c = self.pending_proposal()
        regress(self, self.h, c)
        self.h.h.fake.calls = []
        exc = refuses(self, lambda: c.resume(S, ok_worktree), "clock-regression")
        self.assertTrue(exc.detail["deferred"])
        self.assertEqual(len(exc.detail["ops"]), 1)
        self.assertTrue(exc.detail["ops"][0].startswith("proposal-"))
        self.assertEqual(self.h.h.fake.calls, [])
        state = self.store.load_story(S)
        self.assertEqual((state.phase, [i.status for i in state.pending_advancing_intents()]), ("review-approved", ["pending"]))  # nothing abandoned
        self.assertNotIn("resume-advancing-abandoned", self.events())
        self.h.clock[0] = "2026-11-07T11:58:00Z"
        c.clear_clock_regression(clearance(self.h))
        self.assertEqual(c.resume(S, ok_worktree).phase, "proposed")  # the deferred step completes

    def test_a_work_bind_under_a_clearable_clock_stop_binds_nothing(self):
        c = review_authorized(self.h)
        regress(self, self.h, c)
        exc = refuses(self, lambda: c.bind_receipt(S, REVIEWER, REVIEW_WORKTREE, REVIEW_BRANCH, ok_worktree), "clock-regression")
        self.assertFalse(exc.detail["bound_for_cleanup"])
        state = self.store.load_story(S)
        self.assertEqual((state.phase, state.active_task, state.unresolved_authorization()["status"]), ("review-authorized", None, "pending"))
        self.h.clock[0] = "2026-11-07T11:58:00Z"
        c.clear_clock_regression(clearance(self.h))
        self.assertEqual(c.bind_receipt(S, REVIEWER, REVIEW_WORKTREE, REVIEW_BRANCH, ok_worktree).phase, "review-requested")

    def test_for_cleanup_still_binds_under_a_clearable_clock_stop(self):
        c = review_authorized(self.h)
        regress(self, self.h, c)
        refuses(self, lambda: c.bind_receipt(S, REVIEWER, worktree_check=ok_worktree, for_cleanup=True, reason="owner decided to stop"), "cleanup-requested")
        self.assertEqual(self.store.load_story(S).active_task["cleanup_only"], "cleanup-requested")

    def test_once_the_clear_is_spent_the_stop_is_cleanup_only_again(self):
        c = review_authorized(self.h)
        regress(self, self.h, c)
        self.h.clock[0] = "2026-11-07T11:58:00Z"
        c.clear_clock_regression(clearance(self.h))
        self.h.clock[0] = "2026-11-07T13:00:00Z"
        c.status()
        self.h.clock[0] = "2026-11-07T12:10:00Z"
        refuses(self, lambda: c.rebase_revisions(S, "x"), "clock-regression")
        exc = refuses(self, lambda: c.bind_receipt(S, REVIEWER, worktree_check=ok_worktree), "clock-regression")
        self.assertTrue(exc.detail["bound_for_cleanup"])


# -- fix-first 5, threads lB and lN: untested branches ----------------------------------------------------------------
class ConflictRaceUnsettledDeferralTests(unittest.TestCase):
    """A resume without the file on a `conflict` story whose claim race is unsettled defers and
    touches GitHub not at all (thread lB)."""

    def test_an_unverifiable_claim_is_deferred_without_any_github_call(self):
        h = LiveHarness()
        try:
            arm_failure_after_claim(h.h, reads_after_post=2, hide_ours=True, run="run-live")  # the post's read-back sees our claim, the race re-read does not
            with self.assertRaises(Conflict) as ctx:
                h.coordinator().reserve(S, h.h.snapshot, "base")
            self.assertEqual(ctx.exception.code, "claim-unverifiable")
            h.h.fake.list_comments = FakeTransport.list_comments.__get__(h.h.fake)  # the claim is readable again
            store = Store(h.h.state_dir, "run-live")
            before = store.load_story(S)
            self.assertEqual((before.phase, before.blocked["race_unsettled"]), ("conflict", True))
            bare = h.coordinator(activation=None)
            h.h.fake.calls = []
            exc = refuses(self, lambda: bare.resume(S, ok_worktree), "activation-required")
            self.assertEqual((exc.detail["deferred"], exc.detail["ops"]), (True, ["claim"]))
            self.assertEqual(h.h.fake.calls, [])
            after = store.load_story(S)
            self.assertEqual((after.phase, after.blocked["race_unsettled"]), ("conflict", True))
            self.assertEqual([e["event"] for e in store.read_journal()].count("reconciliation-deferred"), 1)
        finally:
            h.close()


class RecordedStopOverPolicyDriftTests(LiveCase):
    """A recorded stop outranks policy drift: it is the journaled cause (thread lN)."""

    def test_a_recorded_clock_stop_is_reported_ahead_of_policy_drift(self):
        c = review_authorized(self.h)
        regress(self, self.h, c)
        folder = Path(self.h.h.tmpdir.name) / "drift"
        folder.mkdir()
        drifted = load_policy(write_policy(folder, allow='["OM-01.02"]', max_delegated_tasks="7"))
        reopened = Coordinator(self.h.h.fake, drifted, Store(self.h.h.state_dir, "run-live"), now=lambda: self.h.clock[0], live=True, activation=None)
        status = reopened.status()
        self.assertEqual((status["stop"], status["policy_drift"]["policy_digest"]), ("clock-regression", drifted.digest))
        exc = refuses(self, lambda: reopened.bind_receipt(S, REVIEWER, worktree_check=ok_worktree), "clock-regression")
        self.assertTrue(exc.detail["bound_for_cleanup"])
        self.assertEqual(self.store.load_story(S).active_task["cleanup_only"], "clock-regression")


# -- thread jN: --for-cleanup -----------------------------------------------------------------------------------------
class ForCleanupReasonTests(LiveCase):
    """`--for-cleanup` needs a reason, journals it, and is refused while the current activation
    is presented (thread jN)."""

    def test_for_cleanup_needs_a_reason(self):
        review_authorized(self.h)
        bare = self.h.coordinator(activation=None)
        for reason in (None, "", "   "):
            refuses(self, lambda: bare.bind_receipt(S, REVIEWER, worktree_check=ok_worktree, for_cleanup=True, reason=reason), "reason-required")
        self.assertIsNone(self.store.load_story(S).active_task)
        with controlled_cli_clock(self.h.clock), no_gh_calls():
            code, out = run_cli(cli_args(self.h, "bind-receipt", S, "--receipt", json.dumps(REVIEWER), "--for-cleanup", activation=False))
        self.assertEqual((code, out["error"]["code"]), (3, "reason-required"))
        refuses(self, lambda: bare.bind_receipt(S, REVIEWER, worktree_check=ok_worktree, for_cleanup=True, reason="activation file lost"), "cleanup-requested")
        bound = [e for e in self.store.read_journal() if e["event"] == "receipt-bound-cleanup-only"]
        self.assertEqual(bound[-1]["detail"]["reason"], "activation file lost")

    def test_for_cleanup_is_refused_under_the_current_activation(self):
        c = review_authorized(self.h)
        exc = refuses(self, lambda: c.bind_receipt(S, REVIEWER, worktree_check=ok_worktree, for_cleanup=True, reason="stray flag"), "cleanup-not-needed")
        self.assertNotIn("bound_for_cleanup", exc.detail)
        state = self.store.load_story(S)
        self.assertEqual((state.phase, state.active_task), ("review-authorized", None))
        self.assertEqual(c.bind_receipt(S, REVIEWER, REVIEW_WORKTREE, REVIEW_BRANCH, ok_worktree).phase, "review-requested")  # it binds for work


# -- thread je: a deferred resume never exits 0 on an active story ----------------------------------------------------
class DeferredResumeAlwaysRefusesTests(LiveCase):
    """(thread je)"""

    def test_cli_resume_without_the_file_on_an_active_story_exits_3_with_revisions_deferred(self):
        claimed(self.h)
        with controlled_cli_clock(self.h.clock), no_gh_calls() as calls:
            code, out = run_cli(cli_args(self.h, "--live", "resume", S, activation=False))
        self.assertEqual((code, out["error"]["code"], out["error"]["deferred"], out["error"]["ops"]), (3, "activation-required", True, ["revisions"]))
        self.assertEqual(calls, [])


# -- thread jl: run-not-found before creation problems ----------------------------------------------------------------
class RunNotFoundFirstTests(LiveCase):
    """A non-creating command on a run that does not exist says so, not why the document could not
    create it (thread jl)."""

    def test_a_mistyped_state_dir_or_a_short_window_reports_run_not_found(self):
        claimed(self.h)  # the document is used now
        typo = Path(self.h.h.tmpdir.name) / "runz"
        base = ["--policy", str(POLICY(self.h)), "--state-dir", str(typo), "--run-id", "run-live", "--activation", str(self.h.path)]
        with controlled_cli_clock(self.h.clock), no_gh_calls() as calls:
            for rest in (["status"], ["--live", "cancel-run", "--reason", "x"]):
                code, out = run_cli(base + rest)
                self.assertEqual((code, out["error"]["code"]), (3, "run-not-found"), rest)
            code, out = run_cli(base + ["--live", "reserve", S, "--baseline", "b"])
            self.assertEqual((code, out["error"]["code"]), (3, "activation-used"))  # the admitting command still applies the creation rules
        self.assertFalse(typo.exists())
        self.assertEqual(calls, [])
        short = LiveHarness(expires="2026-11-07T11:00:00Z")
        try:
            refuses(self, lambda: Coordinator(short.h.fake, short.h.policy, Store(short.h.state_dir, "run-live"), now=lambda: T0, live=True, activation=short.activation, create=False), "run-not-found")
            refuses(self, lambda: Coordinator(short.h.fake, short.h.policy, Store(short.h.state_dir, "run-live"), now=lambda: T0, live=True, activation=None, create=False), "activation-required")  # no document at all is still named first
            refuses(self, lambda: Coordinator(short.h.fake, short.h.policy, Store(short.h.state_dir, "run-live"), now=lambda: T0, live=True, activation=short.activation), "activation-window-short")
        finally:
            short.close()


# -- thread k2: one journal read per resume ---------------------------------------------------------------------------
class JournalOnceCostTests(LiveCase):
    """A deferred resume reads the journal once, however many steps it defers (thread k2)."""

    def test_a_resume_deferring_several_steps_reads_the_journal_once(self):
        c = review_authorized(self.h)
        c.bind_receipt(S, REVIEWER, REVIEW_WORKTREE, REVIEW_BRANCH, ok_worktree)
        c.record_review(S, self.h.h.sha, "approved", "report.md", self.h.terminal())
        self.h.h.fake.pull_requests[7] = PullRequestRecord(7, "OPEN", self.h.h.sha, False, (), "SUCCESS")
        c.propose_evidence(S, self.h.h.sha, 7, [], "s")
        raw = json.loads(self.store.story_path(S).read_text(encoding="utf-8"))
        proposal = next(i for i in raw["intents"] if i["kind"] == "proposal")
        raw["intents"].append({**proposal, "op": proposal["op"] + "-copy"})  # LABELLED MUTATION: two completed proposals whose transition did not persist
        raw["phase"] = "review-approved"
        self.store.story_path(S).write_text(json.dumps(raw), encoding="utf-8")
        bare = self.h.coordinator(activation=None)
        with mock.patch.object(Store, "read_journal", autospec=True, side_effect=Store.read_journal) as reads:
            exc = refuses(self, lambda: bare.resume(S, ok_worktree), "activation-required")
        self.assertEqual(len(exc.detail["ops"]), 2)
        self.assertEqual(reads.call_count, 1)
        self.assertEqual([e["event"] for e in self.store.read_journal()].count("reconciliation-deferred"), 2)
        refuses(self, lambda: bare.resume(S, ok_worktree), "activation-required")
        self.assertEqual([e["event"] for e in self.store.read_journal()].count("reconciliation-deferred"), 2)  # still once per unchanged situation


# -- threads j8, kJ, kQ: check-activation -----------------------------------------------------------------------------
class CheckActivationExpectTests(LiveCase):
    """`--expect create|advance`, retained artifacts and the clock high-water mark (threads j8, kJ, kQ)."""

    def check(self, *extra: str) -> tuple[int, dict]:
        with controlled_cli_clock(self.h.clock), no_gh_calls() as calls:
            code, out = run_cli(cli_args(self.h, "check-activation", *extra))
        self.assertEqual(calls, [])
        return code, out

    def test_expect_tells_may_create_from_may_advance(self):
        self.assertEqual(self.check("--expect", "create")[0], 0)
        self.assertEqual(self.check("--expect", "advance")[0], 2)  # a run that does not exist cannot advance
        claimed(self.h)
        self.assertEqual(self.check("--expect", "create")[0], 2)  # the run exists: this document creates nothing more
        self.assertEqual(self.check("--expect", "advance")[0], 0)
        self.assertEqual(self.check()[0], 0)  # without --expect: current, as before
        code, out = run_cli(cli_args(self.h, "check-activation", "--expect", "maybe"))
        self.assertEqual((code, out["error"]["code"]), (3, "input-invalid"))

    def test_retained_artifacts_without_run_json_cannot_be_created(self):
        claimed(self.h)
        self.store.run_path.unlink()
        code, out = self.check("--expect", "create")
        self.assertEqual((code, out["can_create"], out["run_exists"]), (2, False, False))
        self.assertTrue(any("retained" in m for m in out["creation_problems"]))
        self.assertIn("run-metadata-missing", out["stops"])

    def test_a_clock_behind_the_high_water_mark_is_not_current(self):
        c = claimed(self.h)
        self.h.clock[0] = "2026-11-07T12:00:00Z"
        c.status()
        self.h.clock[0] = "2026-11-07T11:00:00Z"
        code, out = self.check("--expect", "advance")
        self.assertEqual((code, out["current"], out["stop"]), (2, False, "clock-regression"))
        self.assertIsNone(self.store.load_run().activation_stop)  # reported, not recorded
        self.h.clock[0] = "2026-11-07T11:56:00Z"  # within the tolerance
        self.assertEqual(self.check("--expect", "advance")[0], 0)


# -- threads kp, kv: evidence shape and ids ---------------------------------------------------------------------------
class EvidenceIdTests(LiveCase):
    """Reviews only under pull/, and one numeric id is one citation whatever its spelling (threads kp, kv)."""

    def problems(self, smoke: str, review: str = f"https://github.com/{REPO}/pull/107#issuecomment-900") -> list[str]:
        document = Activation(**{**self.h.activation.__dict__, "evidence": {"lifecycle_smoke": smoke, "fresh_review": review}})
        return [m for _, m in document.evidence_problems(self.h.h.policy)]

    def test_a_review_fragment_is_accepted_only_under_pull(self):
        self.assertEqual(self.problems(f"https://github.com/{REPO}/pull/108#pullrequestreview-5851770529"), [])
        self.assertEqual(len(self.problems(f"https://github.com/{REPO}/issues/108#pullrequestreview-5851770529")), 1)
        self.assertEqual(self.problems(f"https://github.com/{REPO}/issues/106#issuecomment-5"), [])

    def test_one_numeric_id_is_one_citation_whatever_its_spelling(self):
        for smoke, review in ((f"https://github.com/{REPO}/pull/1#issuecomment-05", f"https://github.com/{REPO}/pull/1#issuecomment-5"),
                              (f"https://github.com/{REPO}/pull/1#pullrequestreview-5", f"https://github.com/{REPO}/issues/2#issuecomment-5")):
            problems = self.problems(smoke, review)
            self.assertEqual(len(problems), 1, (smoke, review))
            self.assertIn("same comment or review id (5)", problems[0])
        self.assertEqual(self.problems(f"https://github.com/{REPO}/pull/1#issuecomment-5", f"https://github.com/{REPO}/pull/1#issuecomment-6"), [])


# -- thread jE: the test ledger override ------------------------------------------------------------------------------
class TestLedgerOverrideTests(unittest.TestCase):
    """The suite's ledger override holds however the tests are loaded, and the cross-copy rule is
    tested on one shared root (thread jE)."""

    def test_a_copy_in_another_directory_is_the_same_approval_on_one_shared_root(self):
        h = LiveHarness()
        try:
            shared = Path(h.h.tmpdir.name) / "shared-ledger"
            with mock.patch.object(activation_module, "ledger_root", lambda source_path: shared):
                h.coordinator()
                elsewhere = Path(h.h.tmpdir.name) / "elsewhere"
                elsewhere.mkdir()
                shutil.copyfile(h.path, elsewhere / "approved.toml")
                copy = load_activation(elsewhere / "approved.toml")
                other = Store(Path(h.h.tmpdir.name) / "runs-2", "run-live")
                exc = refuses(self, lambda: Coordinator(h.h.fake, h.h.policy, other, now=lambda: h.clock[0], live=True, activation=copy), "activation-used")
                self.assertIn("already created live run 'run-live'", str(exc))
                self.assertIsNone(other.load_run())
            self.assertEqual([p.name for p in shared.iterdir()], [f"{h.activation.digest}.json"])
        finally:
            h.close()

    def test_loading_the_package_again_never_records_the_override_as_production(self):
        spec = importlib.util.spec_from_file_location("tests_loaded_again", Path(tests_package.__file__))
        again = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(again)  # e.g. pytest importing the directory as ``tests`` as well as ``automation.tests``
        self.assertIs(again.PRODUCTION_LEDGER_ROOT, PRODUCTION_LEDGER_ROOT)
        self.assertEqual(PRODUCTION_LEDGER_ROOT.__module__, "automation.unattended.activation")
        self.assertTrue(getattr(activation_module.ledger_root, "is_test_ledger", False))

    def test_a_live_harness_restores_the_override(self):
        with mock.patch.object(activation_module, "ledger_root", PRODUCTION_LEDGER_ROOT):  # as if the override were lost (another loader, a reload)
            h = LiveHarness()
            try:
                self.assertTrue(getattr(activation_module.ledger_root, "is_test_ledger", False))  # checked before anything could write a ledger record
                self.assertEqual(ledger_path(h.activation.digest, h.activation.path).parent, h.path.resolve().parent / ".activation-ledger")
            finally:
                h.close()


# -- coordinator follow-up review of round 3 --------------------------------------------------------------------------
class FollowUpCliTests(LiveCase):
    """check-activation and help details found by the follow-up review."""

    def test_the_clear_help_renders_the_tolerance(self):
        from automation.unattended.cli import build_parser

        text = " ".join(build_parser().format_help().split())
        self.assertIn("more than 5 minutes (the tolerance)", text)
        self.assertNotIn("{CLOCK_REGRESSION_TOLERANCE_MINUTES}", text)

    def test_expect_advance_needs_an_existing_run(self):
        with controlled_cli_clock(self.h.clock), no_gh_calls():
            code, out = run_cli(cli_args(self.h, "check-activation", "--expect", "advance"))
        self.assertEqual((code, out["run_exists"], out["current"]), (2, False, True))

    def test_a_malformed_run_id_is_a_reported_problem(self):
        with controlled_cli_clock(self.h.clock), no_gh_calls():
            code, out = run_cli(["--policy", str(POLICY(self.h)), "--state-dir", str(self.h.h.state_dir), "--run-id", "Bad Run", "--activation", str(self.h.path), "check-activation"])
        self.assertEqual(code, 2)
        self.assertIn("run-id-invalid", out["stops"])
        self.assertFalse(out["current"])

    def test_an_unreadable_high_water_mark_fails_closed(self):
        claimed(self.h)
        from automation.unattended import cli as cli_module

        real = cli_module.parse_utc
        mark = self.store.load_run().last_observed_at or self.store.load_run().activation["validated_at"]

        seen = []

        def broken(value):  # the mark is compared first; started_at (the same instant here) parses normally afterwards
            if value == mark and not seen:
                seen.append(value)
                raise ValueError("unreadable mark")
            return real(value)

        with mock.patch.object(cli_module, "parse_utc", broken):
            with controlled_cli_clock(self.h.clock), no_gh_calls():
                code, out = run_cli(cli_args(self.h, "check-activation", "--expect", "advance"))
        self.assertEqual((code, out["current"]), (2, False))
        self.assertIn("run-state-invalid", out["stops"])


class FollowUpClearTests(LiveCase):
    def setUp(self):
        super().setUp()
        self.c = claimed(self.h)
        regress(self, self.h, self.c)
        self.h.clock[0] = "2026-11-07T11:58:00Z"

    def test_the_clear_started_line_carries_the_whole_decision(self):
        original = Store.journal

        def lose_cleared(store, story, event, detail=None):
            if event == "activation-stop-cleared":
                raise OSError(28, "No space left on device")
            return original(store, story, event, detail)

        with mock.patch.object(Store, "journal", lose_cleared):
            with self.assertRaises(OSError):
                self.c.clear_clock_regression(clearance(self.h))
        started = [e for e in self.store.read_journal() if e["event"] == "activation-stop-clear-started"][-1]["detail"]
        self.assertEqual((started["reason"], started["high_water"], started["clearance"]["run_id"]), ("clock resynced; verified by the owner", "2026-11-07T12:00:00Z", "run-live"))

    def test_a_clearance_without_a_source_path_is_refused(self):
        document = {k: v for k, v in clearance(self.h).items() if k != "path"}
        refuses(self, lambda: self.c.clear_clock_regression(document), "clearance-invalid")
        self.assertEqual(self.store.load_run().activation_stop["code"], "clock-regression")

    def test_a_clearance_under_the_tool_s_own_work_tree_is_refused(self):
        import tempfile

        from automation.unattended import cli as cli_module

        unrelated = Path(self.h.h.tmpdir.name) / "unrelated"
        unrelated.mkdir()
        subprocess.run(["git", "init", "-q", str(unrelated)], check=True)
        own = Path(tempfile.mkdtemp(prefix=".round3-clearance-", dir=Path(cli_module.__file__).resolve().parents[2]))
        try:
            inside = write_clearance(own / "clearance.toml", self.h)
            with controlled_cli_clock(self.h.clock), no_gh_calls():
                code, out = run_cli(cli_args(self.h, "--repo-root", str(unrelated), "clear-clock-regression", "--clearance", str(inside)))
            self.assertEqual((code, out["error"]["code"], out["error"]["inside"]), (3, "clearance-invalid", "the work tree of this tool"))
        finally:
            shutil.rmtree(own)

    def test_load_clearance_reads_the_path_it_checked(self):
        target = write_clearance(Path(self.h.h.tmpdir.name) / "owner" / "real.toml", self.h)
        link = Path(self.h.h.tmpdir.name) / "link.toml"
        link.symlink_to(target)
        read = []
        original = Path.read_bytes
        with mock.patch.object(Path, "read_bytes", lambda self: read.append(self) or original(self)):
            load_clearance(link, refuse_inside={"--state-dir": self.h.h.state_dir})
        self.assertEqual(read, [target.resolve()])


class FollowUpBindTests(LiveCase):
    def test_a_reason_without_for_cleanup_is_refused(self):
        c = review_authorized(self.h)
        refuses(self, lambda: c.bind_receipt(S, REVIEWER, REVIEW_WORKTREE, REVIEW_BRANCH, ok_worktree, reason="why"), "reason-without-for-cleanup")
        self.assertIsNone(self.store.load_story(S).active_task)

    def test_a_revoked_authorization_binds_for_cleanup_under_a_clearable_stop(self):
        c = review_authorized(self.h)
        refuses(self, lambda: c.cancel(S, "owner stop"), "authorization-unresolved")  # revokes the review authorization
        regress(self, self.h, c)
        exc = refuses(self, lambda: c.bind_receipt(S, REVIEWER, worktree_check=ok_worktree), "authorization-revoked")
        self.assertTrue(exc.detail["bound_for_cleanup"])


class FollowUpClearableOverBudgetTests(LiveCase):
    """A clearable stop whose high-water mark is past the wall clock is a durable stop (guards
    ``_elapsed(on_high_water=True)`` in ``_durable_run_stop``)."""

    OVER = LONG_WINDOW

    def over_budget_on_the_mark(self, c):
        self.h.clock[0] = "2026-11-07T14:02:00Z"
        c.status()
        self.h.clock[0] = "2026-11-07T12:00:00Z"
        refuses(self, lambda: c.rebase_revisions(S, "x"), "clock-regression")
        self.h.clock[0] = "2026-11-07T13:58:00Z"  # 238 minutes on this clock, 242 on the mark

    def test_resume_abandons(self):
        c = ClearableClockStopTests.pending_proposal(self)
        self.over_budget_on_the_mark(c)
        c.resume(S, ok_worktree)
        self.assertIn("resume-advancing-abandoned", self.events())

    def test_a_work_bind_binds_for_cleanup(self):
        c = review_authorized(self.h)
        self.over_budget_on_the_mark(c)
        exc = refuses(self, lambda: c.bind_receipt(S, REVIEWER, REVIEW_WORKTREE, REVIEW_BRANCH, ok_worktree), "clock-regression")
        self.assertTrue(exc.detail["bound_for_cleanup"])


class FollowUpLedgerTests(LiveCase):
    def test_save_run_failing_after_run_json_exists_is_not_aborted(self):
        real = state_module.fsync_directory

        def fail_after_replace(path):
            if (Path(path) / "run.json").exists():
                raise OSError(5, "Input/output error")
            return real(path)

        with mock.patch.object(state_module, "fsync_directory", fail_after_replace):
            with self.assertRaises(OSError):
                self.h.coordinator()
        self.assertEqual(record(self.h)["state"], "pending")
        shutil.rmtree(self.store.root)
        exc = refuses(self, lambda: self.h.coordinator(), "activation-used")
        self.assertIn("unconfirmed", str(exc))

    def test_a_reopen_journals_a_failing_confirmation_once_per_error(self):
        self.h.coordinator()
        path = ledger_path(self.h.activation.digest, self.h.activation.path)
        path.write_text(json.dumps({**json.loads(path.read_text(encoding="utf-8")), "state": "pending"}), encoding="utf-8")  # LABELLED MUTATION
        for error in ("No space left on device", "No space left on device", "Input/output error"):
            with mock.patch.object(activation_module, "_write_ledger", side_effect=OSError(28, error)):
                self.h.coordinator(activation=None)
        lines = [e["detail"]["error"] for e in self.store.read_journal() if e["event"] == "activation-use-unconfirmed"]
        self.assertEqual(len(lines), 2)
        self.assertEqual(record(self.h)["state"], "pending")

    def test_an_interrupted_save_marks_the_record_aborted_and_the_same_creation_retries(self):
        with mock.patch.object(Store, "save_run", side_effect=KeyboardInterrupt()):
            with self.assertRaises(KeyboardInterrupt):
                self.h.coordinator()
        self.assertEqual(record(self.h)["state"], "aborted")
        self.assertEqual(self.h.coordinator().run.run_id, "run-live")

    def test_a_failure_building_the_run_record_marks_it_aborted(self):
        with mock.patch.object(state_module, "RunState", side_effect=TypeError("broken record")):
            with self.assertRaises(TypeError):
                self.h.coordinator()
        self.assertEqual(record(self.h)["state"], "aborted")

    def test_an_unknown_ledger_state_is_a_use_with_its_own_message(self):
        record_activation_use(self.h.activation, self.h.h.state_dir, "run-live", T0)
        path = ledger_path(self.h.activation.digest, self.h.activation.path)
        path.write_text(json.dumps({**json.loads(path.read_text(encoding="utf-8")), "state": "weird"}), encoding="utf-8")  # LABELLED MUTATION
        exc = refuses(self, lambda: self.h.coordinator(), "activation-used")
        self.assertIn("unknown state 'weird'", str(exc))
        self.assertNotIn("already created", str(exc))


class FollowUpDocsTests(unittest.TestCase):
    def test_the_clock_bullet_matches_the_clearable_stop(self):
        docs = (Path(__file__).resolve().parents[2] / "docs" / "unattended-execution.md").read_text(encoding="utf-8")
        self.assertNotIn("after that the run never advances again", docs)
        self.assertNotIn("is cleared only by the owner", docs)


if __name__ == "__main__":
    unittest.main()
