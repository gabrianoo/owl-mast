"""Regressions for PR #114 round 4: review 5860194023 (20 threads). One class per finding (thread
suffix of ``PRRT_kwDOVjxExc62NX…`` in the comment), each test named after the behaviour it pins.
Every scenario runs on the fixture transport marked live with temporary state and an injected
clock; no real GitHub call and no real task is ever made, and no test writes to the real use
ledger under the home directory."""

from __future__ import annotations

import json
import os
import subprocess
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from automation.tests import PRODUCTION_LEDGER_ROOT
from automation.tests.support import IMPLEMENTER, REVIEW_BRANCH, REVIEW_WORKTREE, REVIEWER, controlled_cli_clock, ok_worktree, receipt, run_of
from automation.tests.test_activation import S, T0, LiveHarness, activation_text
from automation.tests.test_enabling_repair_1 import POLICY, claimed, refuses
from automation.tests.test_pr108_review_findings import cli_args, no_gh_calls, review_authorized, run_cli
from automation.tests.test_pr114_review_findings import LONG_WINDOW, LiveCase, clearance, regress
from automation.tests.test_pr114_round3_findings import ClearableClockStopTests, record, write_clearance
from automation.unattended import activation as activation_module
from automation.unattended import cli as cli_module
from automation.unattended import state as state_module
from automation.unattended.activation import Activation, abort_activation_use, is_inside, ledger_path, ledger_root, load_activation, load_clearance, record_activation_use, validate_stop_record
from automation.unattended.coordinator import Coordinator
from automation.unattended.errors import Refused
from automation.unattended.state import Store

REPO = "gabrianoo/owl-mast"
OWNER = IMPLEMENTER["taskId"]
DOCS = Path(__file__).resolve().parents[2] / "docs" / "unattended-execution.md"


def git(*args: str) -> None:
    subprocess.run(["git", "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid", *args], check=True, capture_output=True)


def stop_of(store: Store) -> dict | None:
    return store.load_run().activation_stop


# -- 2i: reconcile-retained-execution under a clearable clock stop -----------------------------------------------------
class ReconcileUnderClearableStopTests(LiveCase):
    """A clock stop the owner can still clear is not a stopped run for the reconciliation either:
    the repair authorization stays pending and binds for work after the clear (thread 2i)."""

    def test_reconcile_refuses_a_clearable_clock_stop_and_the_repair_binds_after_the_clear(self):
        c = review_authorized(self.h)
        c.bind_receipt(S, REVIEWER, REVIEW_WORKTREE, REVIEW_BRANCH, ok_worktree)
        c.record_review(S, self.h.h.sha, "changes-requested", "r.md", self.h.terminal())
        auth = c.authorize_repair(S).unresolved_authorization()
        regress(self, self.h, c)
        run5 = run_of(OWNER, 5)
        retained = {**IMPLEMENTER, "runId": run5, "dispatch": {"runId": run5, "messageId": "m"}, "startedAt": "2099-01-01T00:00:00Z"}
        evidence = {"taskId": OWNER, "runId": run5, "status": "completed"}
        exc = refuses(self, lambda: c.reconcile_retained_execution(S, auth["id"], retained, evidence, "r", "p"), "clock-regression")
        self.assertIn("clear", str(exc))
        state = self.store.load_story(S)
        self.assertEqual((state.unresolved_authorization()["id"], state.unresolved_authorization()["status"]), (auth["id"], "pending"))
        self.assertNotIn("retained-execution-reconciled", self.events())
        self.h.clock[0] = "2026-11-07T11:58:00Z"
        c.clear_clock_regression(clearance(self.h))
        state = c.bind_receipt(S, receipt(IMPLEMENTER, OWNER, ordinal=2), worktree_check=ok_worktree)
        self.assertEqual((state.phase, state.active_task["runId"], state.active_task.get("cleanup_only")), ("claimed", run_of(OWNER, 2), None))


# -- 2p, 2z, 2w, 25: where a clearance is read from --------------------------------------------------------------------
class ClearanceLocationCase(LiveCase):
    def setUp(self):
        super().setUp()
        self.c = claimed(self.h)
        regress(self, self.h, self.c)
        self.h.clock[0] = "2026-11-07T11:58:00Z"
        self.tmp = Path(self.h.h.tmpdir.name)
        self.outside = write_clearance(self.tmp / "owner" / "clearance.toml", self.h)

    def clear(self, path: Path, *extra: str) -> tuple[int, dict]:
        with controlled_cli_clock(self.h.clock), no_gh_calls():
            return run_cli(cli_args(self.h, *extra, "clear-clock-regression", "--clearance", str(path)))

    def assert_refused(self, result: tuple[int, dict]) -> dict:
        code, out = result
        self.assertEqual((code, out["error"]["code"]), (3, "clearance-invalid"), out)
        self.assertEqual(stop_of(self.store)["code"], "clock-regression")
        return out["error"]


class GitFailureRefusesTests(ClearanceLocationCase):
    """When git cannot say whether a path is inside a work tree, the clear refuses (thread 2p)."""

    def test_git_that_cannot_be_run_refuses_the_clear(self):
        with mock.patch.object(cli_module.subprocess, "run", side_effect=OSError(2, "No such file or directory: 'git'")):
            error = self.assert_refused(self.clear(self.outside))
        self.assertIn("cannot determine the work tree", error["message"])

    def test_a_git_timeout_refuses_the_clear(self):
        with mock.patch.object(cli_module.subprocess, "run", side_effect=subprocess.TimeoutExpired("git", 30)):
            self.assert_refused(self.clear(self.outside))

    def test_a_git_failure_other_than_not_a_repository_refuses_the_clear(self):
        dubious = subprocess.CompletedProcess(["git"], 128, stdout="", stderr="fatal: detected dubious ownership in repository at '/mnt/c/x'")
        with mock.patch.object(cli_module.subprocess, "run", return_value=dubious):
            self.assert_refused(self.clear(self.outside))

    def test_not_a_git_repository_is_the_one_answer_that_allows(self):
        self.assertIsNone(cli_module._work_tree(self.outside.parent))
        code, out = self.clear(self.outside)
        self.assertEqual((code, out["run"]["activation_stop"]), (0, None))


class AnyWorkTreeRefusedTests(ClearanceLocationCase):
    """A clearance inside any git work tree is refused, a delegated task's worktree included (thread 2z)."""

    def test_a_clearance_inside_a_delegated_worktree_is_refused(self):
        main = self.tmp / "main-checkout"
        main.mkdir()
        git("init", "-q", str(main))
        git("-C", str(main), "commit", "-q", "--allow-empty", "-m", "init")
        task = self.tmp / "task-worktree"
        git("-C", str(main), "worktree", "add", "-q", str(task))  # a linked worktree, as delegate_task creates one
        inside = write_clearance(task / "notes" / "clearance.toml", self.h)
        unrelated = self.tmp / "unrelated"
        unrelated.mkdir()
        error = self.assert_refused(self.clear(inside, "--repo-root", str(unrelated)))
        self.assertTrue(error["inside"].startswith("a git work tree"), error)

    def test_a_clearance_inside_an_unrelated_checkout_is_refused(self):
        other = self.tmp / "other-checkout"
        other.mkdir()
        git("init", "-q", str(other))
        self.assert_refused(self.clear(write_clearance(other / "clearance.toml", self.h)))


class CaseInsensitiveContainmentTests(ClearanceLocationCase):
    """A path that differs from the state directory or a work tree only by case is inside it (thread 2w)."""

    def test_is_inside_ignores_case(self):
        self.assertTrue(is_inside(self.tmp / "RUNS" / "x.toml", self.tmp / "runs"))
        self.assertTrue(is_inside(self.tmp / "runs", self.tmp / "Runs"))
        self.assertFalse(is_inside(self.tmp / "runs-2" / "x.toml", self.tmp / "runs"))

    def test_a_case_variant_of_the_state_directory_is_refused_by_the_loader_and_the_coordinator(self):
        variant = write_clearance(self.store.state_dir.parent / self.store.state_dir.name.upper() / "clearance.toml", self.h)
        refuses(self, lambda: load_clearance(variant, refuse_inside={"--state-dir": self.store.state_dir}), "clearance-invalid")
        refuses(self, lambda: self.c.clear_clock_regression(load_clearance(variant)), "clearance-invalid")
        self.assert_refused(self.clear(variant))

    def test_a_case_variant_of_the_repository_work_tree_is_refused(self):
        repo = self.tmp / "checkout"
        repo.mkdir()
        git("init", "-q", str(repo))
        variant = write_clearance(self.tmp / "CHECKOUT" / "clearance.toml", self.h)
        self.assert_refused(self.clear(variant, "--repo-root", str(repo)))


class HonestSymlinkCommentTests(unittest.TestCase):
    """The comment on the read no longer promises a symlink-race guarantee (thread 25)."""

    def test_the_comment_states_the_limit(self):
        source = Path(activation_module.__file__).read_text(encoding="utf-8")
        self.assertNotIn("a symlink swapped in between is not read", source)
        self.assertIn("narrows a race, it does not close one", source)


# -- 3E, 3J, 3O, 3U, 3Y: the use ledger --------------------------------------------------------------------------------
class UnconfirmedStableKeyTests(LiveCase):
    """`activation-use-unconfirmed` is journaled once per (type, errno), whatever the random temporary
    name in the message (thread 3E)."""

    def unconfirmed(self) -> list[dict]:
        return [e["detail"] for e in self.store.read_journal() if e["event"] == "activation-use-unconfirmed"]

    def test_many_opens_with_random_temp_names_journal_one_line(self):
        self.h.coordinator()
        path = ledger_path(self.h.activation.digest, self.h.activation.path)
        path.write_text(json.dumps({**json.loads(path.read_text(encoding="utf-8")), "state": "pending"}), encoding="utf-8")  # LABELLED MUTATION
        for _ in range(4):
            failing = OSError(28, "No space left on device", f".tmp-{uuid.uuid4().hex[:8]}.json")
            with mock.patch.object(activation_module, "_write_ledger", side_effect=failing):
                self.h.coordinator(activation=None)
        lines = self.unconfirmed()
        self.assertEqual(len(lines), 1)
        self.assertEqual((lines[0]["type"], lines[0]["errno"]), ("OSError", 28))
        self.assertIn(".tmp-", lines[0]["error"])  # the full message is kept, as a non-key field
        with mock.patch.object(activation_module, "_write_ledger", side_effect=OSError(5, "Input/output error", ".tmp-zz.json")):
            self.h.coordinator(activation=None)
        with mock.patch.object(activation_module, "_write_ledger", side_effect=Refused("ledger gone", code="activation-ledger-unwritable")):
            self.h.coordinator(activation=None)
        self.assertEqual([(d["type"], d["errno"]) for d in self.unconfirmed()], [("OSError", 28), ("OSError", 5), ("Refused", None)])

    def test_confirm_returns_type_errno_and_message(self):
        self.h.coordinator()
        path = ledger_path(self.h.activation.digest, self.h.activation.path)
        path.write_text(json.dumps({**json.loads(path.read_text(encoding="utf-8")), "state": "pending"}), encoding="utf-8")  # LABELLED MUTATION
        with mock.patch.object(activation_module, "_write_ledger", side_effect=OSError(28, "No space left on device")):
            answer = activation_module.confirm_activation_use(self.store.load_run().activation, self.h.h.state_dir, "run-live")
        self.assertEqual((answer["type"], answer["errno"]), ("OSError", 28))
        self.assertIn("No space left", answer["message"])


class AbortHandlerNeverMasksTests(LiveCase):
    """Nothing raised while marking the record aborted replaces the creation's own error (thread 3J)."""

    def test_an_error_inside_the_abort_handler_keeps_the_original_error(self):
        for inner in (TypeError("odd ledger record"), KeyError("state"), KeyboardInterrupt()):
            h = LiveHarness()  # each case burns its document (the record stays pending)
            try:
                with mock.patch.object(Store, "save_run", side_effect=OSError(28, "No space left on device")), mock.patch.object(state_module, "abort_activation_use", side_effect=inner):
                    with self.assertRaises(OSError) as ctx:
                        h.coordinator()
                self.assertEqual(ctx.exception.errno, 28, inner)
                self.assertTrue(any(type(inner).__name__ in note for note in getattr(ctx.exception, "__notes__", [])), inner)
                self.assertEqual(record(h)["state"], "pending")  # unmarked: refused as unconfirmed, never retried as aborted
                self.assertEqual(Store(h.h.state_dir, "run-live").retained_artifacts(), [])  # nothing journaled before run.json (a journal would refuse the retry as retained state)
            finally:
                h.close()

    def test_abort_returns_false_when_the_run_path_cannot_be_checked(self):
        record_activation_use(self.h.activation, self.h.h.state_dir, "run-live", T0)
        unreadable = mock.Mock(exists=mock.Mock(side_effect=PermissionError(13, "Permission denied")))
        self.assertFalse(abort_activation_use(self.h.activation, self.h.h.state_dir, "run-live", unreadable))
        self.assertEqual(record(self.h)["state"], "pending")


class RetryAttemptHistoryTests(LiveCase):
    """A retried creation records its own time and keeps the attempt history (thread 3O)."""

    OVER = LONG_WINDOW  # a retry five minutes later still has the whole wall-clock budget inside the window

    def test_a_retry_records_its_own_time_and_keeps_every_attempt(self):
        with mock.patch.object(Store, "save_run", side_effect=OSError(28, "No space left on device")):
            with self.assertRaises(OSError):
                self.h.coordinator()
        self.h.clock[0] = "2026-11-07T10:05:00Z"
        with mock.patch.object(Store, "save_run", side_effect=SystemExit("killed")), mock.patch.object(state_module, "abort_activation_use", return_value=False):
            with self.assertRaises(SystemExit):
                self.h.coordinator()
        used = record(self.h)
        self.assertEqual((used["state"], used["created_at"], used["first_attempt_at"]), ("pending", "2026-11-07T10:05:00Z", T0))
        self.assertEqual([a["at"] for a in used["attempts"]], [T0, "2026-11-07T10:05:00Z"])
        self.assertEqual(used["attempts"][-1]["pid"], os.getpid())
        self.assertNotIn("retried_at", used)
        exc = refuses(self, lambda: self.h.coordinator(), "activation-used")
        self.assertIn("at 2026-11-07T10:05:00Z is unconfirmed", str(exc))  # the attempt that may have created the run, not the first one


class RetryLedgerWriteRefusalTests(LiveCase):
    """A retry whose `pending` write fails creates nothing and leaves the record `aborted` (thread 3U)."""

    def test_a_retry_that_cannot_rewrite_the_ledger_refuses_and_creates_nothing(self):
        with mock.patch.object(Store, "save_run", side_effect=OSError(28, "No space left on device")):
            with self.assertRaises(OSError):
                self.h.coordinator()
        self.assertEqual(record(self.h)["state"], "aborted")
        original = activation_module._write_ledger

        def pending_fails(path, rec, replace):
            if replace and rec.get("state") == "pending":
                raise OSError(5, "Input/output error")
            return original(path, rec, replace)

        with mock.patch.object(activation_module, "_write_ledger", pending_fails):
            refuses(self, lambda: self.h.coordinator(), "activation-ledger-unwritable")
        self.assertFalse(self.store.run_path.exists())
        self.assertEqual(record(self.h)["state"], "aborted")


class ConfirmRulesTests(LiveCase):
    """A reopen tolerates a `Refused` ledger and never touches another creation's record (thread 3Y)."""

    def test_a_reopen_with_no_account_entry_still_opens_and_journals_once(self):
        c = claimed(self.h)
        path = ledger_path(self.h.activation.digest, self.h.activation.path)
        path.write_text(json.dumps({**json.loads(path.read_text(encoding="utf-8")), "state": "pending"}), encoding="utf-8")  # LABELLED MUTATION
        with mock.patch.object(activation_module, "ledger_root", PRODUCTION_LEDGER_ROOT), mock.patch.object(activation_module.pwd, "getpwuid", side_effect=KeyError("uid not found")):
            for _ in range(2):
                report = self.h.coordinator(activation=None).status()
        self.assertEqual(report["run"]["run_id"], "run-live")
        lines = [e["detail"] for e in self.store.read_journal() if e["event"] == "activation-use-unconfirmed"]
        self.assertEqual([(d["type"], d["errno"]) for d in lines], [("Refused", None)])
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["state"], "pending")
        del c

    def test_a_reopen_leaves_another_creation_s_record_alone(self):
        self.h.coordinator()
        path = ledger_path(self.h.activation.digest, self.h.activation.path)
        foreign = {**json.loads(path.read_text(encoding="utf-8")), "state": "pending", "run_id": "run-other", "state_dir": str(Path(self.h.h.tmpdir.name) / "elsewhere")}
        path.write_text(json.dumps(foreign), encoding="utf-8")  # LABELLED MUTATION: a record of another creation of the same document
        self.h.coordinator(activation=None)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), foreign)


# -- 3d: status --read-only prints the ledger --------------------------------------------------------------------------
class ReadOnlyStatusLedgerTests(LiveCase):
    """(thread 3d)"""

    def test_status_read_only_reports_the_ledger_root_and_record(self):
        claimed(self.h)
        monitor = Coordinator(self.h.h.fake, self.h.h.policy, Store(self.h.h.state_dir, "run-live"), now=lambda: self.h.clock[0], live=True, activation=None, read_only=True)
        ledger = monitor.status(read_only=True)["activation"]["ledger"]
        self.assertEqual((ledger["root"], ledger["record"]["state"]), (str(ledger_root(self.h.activation.path)), "committed"))
        with controlled_cli_clock(self.h.clock), no_gh_calls():
            code, out = run_cli(cli_args(self.h, "status", "--read-only", activation=False))
        self.assertEqual((code, out["read_only"], out["activation"]["ledger"]["record"]["run_id"]), (0, True, "run-live"))


# -- 3i: the wall clock on the high-water mark everywhere --------------------------------------------------------------
class WallClockOnHighWaterTests(LiveCase):
    """A clock within the tolerance behind the high-water mark never gives a run back time (thread 3i)."""

    OVER = LONG_WINDOW  # approval until 20:00; the 240-minute wall clock ends at 14:00

    def test_a_run_over_budget_at_the_mark_is_stopped_on_a_clock_slightly_behind(self):
        c = claimed(self.h)
        self.h.clock[0] = "2026-11-07T14:02:00Z"
        c.status()  # high-water mark 14:02
        self.h.clock[0] = "2026-11-07T13:58:00Z"  # within the 5-minute tolerance: no regression stop; 238 minutes on this clock
        self.assertEqual(c.status()["stop"], "wall-clock-exceeded")
        self.assertIsNone(stop_of(self.store))
        exc = refuses(self, lambda: c.authorize_repair(S), "wall-clock-exceeded")
        self.assertIn("high-water mark", str(exc))
        with controlled_cli_clock(self.h.clock), no_gh_calls():
            code, out = run_cli(cli_args(self.h, "check-activation", "--expect", "advance"))
        self.assertEqual((code, out["current"]), (2, False))
        self.assertIn("wall-clock-exceeded", out["stops"])


# -- 31: the --reason pairing writes nothing ---------------------------------------------------------------------------
class ReasonPairingFirstTests(LiveCase):
    """A malformed `--reason` / `--for-cleanup` pairing is refused before the gate writes anything (thread 31)."""

    def test_a_malformed_pairing_leaves_run_json_untouched(self):
        c = review_authorized(self.h)
        self.h.clock[0] = "2026-11-07T10:30:00Z"  # an observation the gate would record as the new high-water mark
        before = self.store.run_path.read_bytes()
        refuses(self, lambda: c.bind_receipt(S, REVIEWER, REVIEW_WORKTREE, REVIEW_BRANCH, ok_worktree, reason="why"), "reason-without-for-cleanup")
        refuses(self, lambda: c.bind_receipt(S, REVIEWER, worktree_check=ok_worktree, for_cleanup=True, reason=" "), "reason-required")
        self.assertEqual(self.store.run_path.read_bytes(), before)

    def test_the_cli_refuses_the_pairing_before_opening_any_run(self):
        fresh = Path(self.h.h.tmpdir.name) / "no-such-state"
        args = ["--policy", str(POLICY(self.h)), "--state-dir", str(fresh), "--run-id", "run-live", "--activation", str(self.h.path), "bind-receipt", S, "--receipt", json.dumps(REVIEWER)]
        with controlled_cli_clock(self.h.clock), no_gh_calls() as calls:
            code, out = run_cli(args + ["--reason", "why"])
            self.assertEqual((code, out["error"]["code"]), (3, "reason-without-for-cleanup"))  # not run-not-found: nothing was opened
            code, out = run_cli(args + ["--for-cleanup"])
            self.assertEqual((code, out["error"]["code"]), (3, "reason-required"))
        self.assertFalse(fresh.exists())
        self.assertEqual(calls, [])


# -- 38: a failed clear keeps the stop in memory -----------------------------------------------------------------------
class FailedClearRestoresTheStopTests(LiveCase):
    """(thread 38)"""

    def test_a_failed_save_restores_the_stop_and_the_mark_on_the_coordinator(self):
        c = claimed(self.h)
        regress(self, self.h, c)
        self.h.clock[0] = "2026-11-07T11:58:00Z"
        c._reload_run()
        stop, mark = dict(c.run.activation_stop), c.run.last_observed_at
        with mock.patch.object(Store, "save_run", side_effect=OSError(28, "No space left on device")):
            with self.assertRaises(OSError):
                c.clear_clock_regression(clearance(self.h))
        self.assertEqual((c.run.activation_stop, c.run.last_observed_at), (stop, mark))
        self.assertTrue(c._clearable_clock_stop())


# -- 4A: _clear_spent once per operation -------------------------------------------------------------------------------
class ClearSpentOncePerOperationTests(LiveCase):
    """Under a clock stop the journal is scanned for the clear once per operation (thread 4A)."""

    def scans(self, fn) -> int:
        with mock.patch.object(Store, "read_journal", autospec=True, side_effect=Store.read_journal) as reads:
            try:
                fn()
            except Refused:
                pass
        return reads.call_count

    def test_a_work_bind_under_a_clearable_stop_reads_the_journal_once(self):
        c = review_authorized(self.h)
        regress(self, self.h, c)
        self.assertEqual(self.scans(lambda: c.bind_receipt(S, REVIEWER, REVIEW_WORKTREE, REVIEW_BRANCH, ok_worktree)), 1)

    def test_a_deferred_resume_under_a_clearable_stop_reads_the_journal_once(self):
        c = ClearableClockStopTests.pending_proposal(self)
        regress(self, self.h, c)
        self.assertEqual(self.scans(lambda: c.resume(S, ok_worktree)), 1)


# -- 4H: stop_id -------------------------------------------------------------------------------------------------------
class StopIdTests(LiveCase):
    """Each recorded stop has its own id, so a stop at the same second as a cleared one is another stop (thread 4H)."""

    def test_new_stops_carry_a_stop_id_and_the_record_validates(self):
        c = claimed(self.h)
        regress(self, self.h, c)
        stop = stop_of(self.store)
        self.assertRegex(stop["stop_id"], r"^[0-9a-f]{32}$")
        legacy = {k: v for k, v in stop.items() if k != "stop_id"}
        self.assertEqual(validate_stop_record(legacy, "run-live"), legacy)  # a stop recorded before round 4
        for bad in ("x", 7, "A" * 32):
            refuses(self, lambda: validate_stop_record({**stop, "stop_id": bad}, "run-live"), "run-state-invalid")
        refuses(self, lambda: validate_stop_record({**stop, "other": 1}, "run-live"), "run-state-invalid")

    def test_a_second_stop_at_the_same_second_as_a_cleared_one_is_exhausted(self):
        c = claimed(self.h)
        regress(self, self.h, c)
        first = stop_of(self.store)
        self.h.clock[0] = "2026-11-07T11:58:00Z"
        original = Store.journal

        def lose_cleared(store, story, event, detail=None):
            if event == "activation-stop-cleared":
                raise OSError(28, "No space left on device")
            return original(store, story, event, detail)

        with mock.patch.object(Store, "journal", lose_cleared):
            with self.assertRaises(OSError):
                c.clear_clock_regression(clearance(self.h))  # the save went through, the confirming line was lost
        started = [e["detail"] for e in self.store.read_journal() if e["event"] == "activation-stop-clear-started"][-1]
        self.assertEqual(started["stop_id"], first["stop_id"])
        self.h.clock[0] = first["observed_at"]  # the clock regresses again and lands on the same second
        refuses(self, lambda: c.rebase_revisions(S, "x"), "clock-regression")
        second = stop_of(self.store)
        self.assertEqual(second["observed_at"], first["observed_at"])
        self.assertNotEqual(second["stop_id"], first["stop_id"])
        self.h.clock[0] = "2026-11-07T11:58:00Z"
        refuses(self, lambda: c.clear_clock_regression(clearance(self.h)), "clock-clear-exhausted")

    def test_a_legacy_stop_without_an_id_is_compared_on_its_observation(self):
        c = claimed(self.h)
        regress(self, self.h, c)
        raw = json.loads(self.store.run_path.read_text(encoding="utf-8"))
        raw["activation_stop"].pop("stop_id")  # LABELLED MUTATION: a stop recorded before round 4
        self.store.run_path.write_text(json.dumps(raw), encoding="utf-8")
        self.h.clock[0] = "2026-11-07T11:58:00Z"
        self.assertIsNone(c.clear_clock_regression(clearance(self.h))["run"]["activation_stop"])


# -- 3t, 3y: check-activation ------------------------------------------------------------------------------------------
class ExpectRequiredTests(LiveCase):
    """With `--run-id`, `--expect` is required (thread 3t)."""

    def test_run_id_without_expect_is_a_malformed_call(self):
        with controlled_cli_clock(self.h.clock), no_gh_calls() as calls:
            for activation in (True, False):
                code, out = run_cli(cli_args(self.h, "check-activation", activation=activation))
                self.assertEqual((code, out["error"]["code"]), (3, "expect-required"), activation)
            code, out = run_cli(["--policy", str(POLICY(self.h)), "--activation", str(self.h.path), "check-activation"])
            self.assertEqual((code, out["current"]), (2, False))  # without --run-id it is not needed: current for nothing
        self.assertEqual(calls, [])

    def test_every_documented_run_id_example_passes_expect(self):
        texts = {DOCS: DOCS.read_text(encoding="utf-8"), Path("candidate"): (DOCS.parents[1] / "automation/examples/activation-om-01-02.candidate.toml").read_text(encoding="utf-8")}
        for where, text in texts.items():
            for line in text.splitlines():
                if "check-activation" in line and "--run-id <" in line and "python3 -m automation.unattended" in line:
                    self.assertIn("--expect", line, (where, line))


class OneReportShapeTests(LiveCase):
    """The no-activation report has the same keys as every other report (thread 3y)."""

    def test_both_reports_have_the_same_keys_and_expect(self):
        with controlled_cli_clock(self.h.clock), no_gh_calls():
            code_with, with_file = run_cli(cli_args(self.h, "check-activation", "--expect", "create"))
            code_without, without = run_cli(cli_args(self.h, "check-activation", "--expect", "create", activation=False))
        self.assertEqual((code_with, code_without), (0, 2))
        self.assertEqual(sorted(with_file), sorted(without))
        self.assertEqual((without["expect"], without["stop"], without["activation"], without["ledger_root"]), ("create", "activation-required", None, None))


# -- 4M, 4P: ledger home and evidence id -------------------------------------------------------------------------------
class LedgerHomeTests(LiveCase):
    """An empty or relative home directory has no ledger (thread 4M)."""

    def test_an_empty_or_relative_home_refuses(self):
        for home in ("", "relative/home", "."):
            entry = SimpleNamespace(pw_dir=home)
            with mock.patch.object(activation_module, "ledger_root", PRODUCTION_LEDGER_ROOT), mock.patch.object(activation_module.pwd, "getpwuid", return_value=entry):
                refuses(self, lambda: ledger_path("d" * 64, "x.toml"), "activation-ledger-unwritable")
                refuses(self, lambda: self.h.coordinator(), "activation-ledger-unwritable")
        self.assertIsNone(self.store.load_run())


class EvidenceIdBoundTests(LiveCase):
    """An evidence id longer than 20 digits is not a citation, and never a crash (thread 4P)."""

    def test_a_huge_id_is_an_invalid_citation(self):
        huge = f"https://github.com/{REPO}/pull/107#issuecomment-{'9' * 5000}"
        document = Activation(**{**self.h.activation.__dict__, "evidence": {"lifecycle_smoke": huge, "fresh_review": f"https://github.com/{REPO}/pull/107#issuecomment-5"}})
        problems = document.evidence_problems(self.h.h.policy)
        self.assertEqual([code for code, _ in problems], ["activation-invalid"])
        twenty = f"https://github.com/{REPO}/pull/107#issuecomment-{'9' * 20}"
        self.assertEqual(Activation(**{**self.h.activation.__dict__, "evidence": {"lifecycle_smoke": twenty, "fresh_review": huge.replace('9' * 5000, '5')}}).evidence_problems(self.h.h.policy), [])

    def test_check_activation_reports_a_huge_id_instead_of_crashing(self):
        path = Path(self.h.h.tmpdir.name) / "huge.toml"
        path.write_text(activation_text(self.h.h.policy, smoke=f'"https://github.com/{REPO}/pull/107#issuecomment-{"9" * 5000}"'), encoding="utf-8")
        self.assertEqual(load_activation(path).approved, True)
        with controlled_cli_clock(self.h.clock), no_gh_calls():
            code, out = run_cli(["--policy", str(POLICY(self.h)), "--state-dir", str(self.h.h.state_dir), "--run-id", "run-live", "--activation", str(path), "check-activation", "--expect", "create"])
        self.assertEqual((code, out["can_create"]), (2, False))
        self.assertIn("activation-invalid", out["stops"])


if __name__ == "__main__":
    unittest.main()
