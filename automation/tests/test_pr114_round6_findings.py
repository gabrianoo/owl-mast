"""Regressions for PR #114 round 6: review 5862675978 (18 threads). One class per finding (thread
suffix of ``PRRT_kwDOVjxExc62R_…`` in the docstring), each test named after the behaviour it pins.
Every scenario runs on the fixture transport marked live with temporary state and an injected
clock; no real GitHub call and no real task is ever made, and no test writes to the real use
ledger under the home directory."""

from __future__ import annotations

import inspect
import json
import os
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from automation.tests import test_pr114_round5_findings as r5
from automation.tests.support import controlled_cli_clock, write_policy
from automation.tests.test_activation import S, T0
from automation.tests.test_enabling_repair_1 import claimed, refuses
from automation.tests.test_pr108_review_findings import cli_args, no_gh_calls, run_cli
from automation.tests.test_pr114_review_findings import LiveCase, clearance, regress
from automation.tests.test_pr114_round3_findings import record, write_clearance
from automation.tests.test_pr114_round4_findings import ClearanceLocationCase, stop_of
from automation.unattended import activation as activation_module
from automation.unattended import cli as cli_module
from automation.unattended import state as state_module
from automation.unattended.activation import Activation, _retryable_creation, abort_activation_use, activation_use, confirm_activation_use, ledger_path, record_activation_use, use_refusal
from automation.unattended.coordinator import Coordinator
from automation.unattended.errors import Refused
from automation.unattended.policy import load_policy
from automation.unattended.state import Store

REPO = "gabrianoo/owl-mast"
DOCS = Path(__file__).resolve().parents[2] / "docs" / "unattended-execution.md"
PLAIN = "fatal: not a git repository (or any of the parent directories): .git\n"


def set_ledger(h, **fields) -> dict:
    return r5.set_ledger(h, **fields)  # LABELLED MUTATION of the ledger record


def unconfirmed(store: Store) -> list[dict]:
    return [e["detail"] for e in store.read_journal() if e["event"] == "activation-use-unconfirmed"]


# -- Iy: the abort note per reason ----------------------------------------------------------------------------------------
class AbortReasonTests(LiveCase):
    """`abort_activation_use` returns why it did or did not mark the record, and the creation's note is
    worded for that reason; only an unmarked pending record of this run "stays pending" (thread Iy)."""

    def abort(self) -> str:
        return abort_activation_use(self.h.activation, self.h.h.state_dir, "run-live", self.store.run_path, cause=OSError(28, "No space left on device"))

    def test_each_cause_has_its_own_reason(self):
        self.assertEqual(self.abort(), "no-record")
        record_activation_use(self.h.activation, self.h.h.state_dir, "run-other", T0)
        self.assertEqual(self.abort(), "not-this-run")
        self.assertEqual(record(self.h)["state"], "pending")
        set_ledger(self.h, run_id="run-live", state="committed")
        self.assertEqual(self.abort(), "not-pending")
        set_ledger(self.h, state="pending", attempts="x")
        self.assertEqual(self.abort(), "unreadable")
        set_ledger(self.h, attempts=[{"at": T0}])
        self.assertEqual(self.abort(), "aborted")
        self.assertEqual(record(self.h)["state"], "aborted")
        set_ledger(self.h, state="pending")  # the record is classified first: only a pending record of this run reaches run.json
        self.store.run_path.parent.mkdir(parents=True)
        self.store.run_path.write_text("{}", encoding="utf-8")
        self.assertEqual(self.abort(), "run-json-exists")

    def test_a_save_that_raised_after_run_json_was_written_says_reopen_not_reissue(self):
        original = Store.save_run

        def save_then_fail(store, run):
            original(store, run)  # run.json replaced ...
            raise OSError(5, "Input/output error")  # ... then the directory fsync fails

        with mock.patch.object(Store, "save_run", save_then_fail):
            with self.assertRaises(OSError) as ctx:
                self.h.coordinator()
        notes = " ".join(getattr(ctx.exception, "__notes__", []))
        self.assertIn("run.json exists: reopen the same run", notes)
        self.assertIn("the next open confirms the record; do not re-issue", notes)
        self.assertNotIn("stays pending", notes)
        self.assertEqual(record(self.h)["state"], "pending")
        self.h.coordinator()  # the advice holds: the reopen confirms the record
        self.assertEqual(record(self.h)["state"], "committed")

    def test_a_record_that_is_not_this_runs_unreadable_or_not_pending_never_stays_pending(self):
        for reason, words in (("not-this-run", "another run"), ("unreadable", "not a valid record"), ("not-pending", "no longer pending"), ("no-record", "no record")):
            note = state_module.abort_note(reason, "run-live", self.h.h.state_dir)
            self.assertNotIn("stays pending", note, reason)
            self.assertIn(words, note, reason)
        self.assertIn("stays pending", state_module.abort_note("ledger-error", "run-live", self.h.h.state_dir))


# -- I0: a clear that took effect is a clear ------------------------------------------------------------------------------
class ClearSaveUncertainIsAClearTests(LiveCase):
    """A clear whose save reported an error after run.json was replaced returns the normal result plus
    `save_uncertain`, and the CLI exits 0 (thread I0, owner decision)."""

    def setUp(self):
        super().setUp()
        self.c = claimed(self.h)
        regress(self, self.h, self.c)
        self.h.clock[0] = "2026-11-07T11:58:00Z"

    def test_the_result_carries_the_journal_seq_and_the_run(self):
        with mock.patch.object(state_module, "fsync_directory", side_effect=OSError(5, "Input/output error")):
            result = self.c.clear_clock_regression(clearance(self.h))
        self.assertIsNone(result["run"]["activation_stop"])
        self.assertIn("Input/output error", result["save_uncertain"])
        line = next(e for e in self.store.read_journal() if e["event"] == "activation-stop-cleared")
        self.assertEqual(result["journal_seq"], line["seq"])
        self.assertIn("save_uncertain", line["detail"])

    def test_the_cli_exits_0(self):
        path = write_clearance(Path(self.h.h.tmpdir.name) / "owner" / "clearance.toml", self.h)
        with controlled_cli_clock(self.h.clock), no_gh_calls(), mock.patch.object(state_module, "fsync_directory", side_effect=OSError(5, "Input/output error")):
            code, out = run_cli(cli_args(self.h, "clear-clock-regression", "--clearance", str(path)))
        self.assertEqual(code, 0, out)
        self.assertNotIn("error", out)
        self.assertIsInstance(out["journal_seq"], int)
        self.assertIn("save_uncertain", out)

    def test_the_docs_no_longer_name_a_refusal(self):
        text = DOCS.read_text(encoding="utf-8")
        self.assertNotIn("clear-save-uncertain", text)
        self.assertIn("plus `save_uncertain` and exits 0", text)


# -- I3: Ctrl-C after the replace ---------------------------------------------------------------------------------------------
class ClearInterruptedAfterReplaceTests(LiveCase):
    """An interrupt after run.json was replaced propagates, after a best-effort `activation-stop-cleared`
    line with `interrupted` (thread I3)."""

    def setUp(self):
        super().setUp()
        self.c = claimed(self.h)
        regress(self, self.h, self.c)
        self.h.clock[0] = "2026-11-07T11:58:00Z"

    def test_system_exit_after_the_replace_propagates_and_is_journaled(self):
        with mock.patch.object(state_module, "fsync_directory", side_effect=SystemExit("killed")):
            with self.assertRaises(SystemExit):
                self.c.clear_clock_regression(clearance(self.h))
        self.assertIsNone(stop_of(self.store))
        cleared = [e["detail"] for e in self.store.read_journal() if e["event"] == "activation-stop-cleared"]
        self.assertEqual(len(cleared), 1)
        self.assertIn("SystemExit", cleared[0]["interrupted"])

    def test_keyboard_interrupt_after_the_replace_propagates_and_is_journaled(self):
        with mock.patch.object(state_module, "fsync_directory", side_effect=KeyboardInterrupt()):
            with self.assertRaises(KeyboardInterrupt):
                self.c.clear_clock_regression(clearance(self.h))
        self.assertIsNone(stop_of(self.store))  # the clear is in effect on disk
        cleared = [e["detail"] for e in self.store.read_journal() if e["event"] == "activation-stop-cleared"]
        self.assertEqual(len(cleared), 1)
        self.assertIn("KeyboardInterrupt", cleared[0]["interrupted"])
        refuses(self, lambda: self.c.clear_clock_regression(clearance(self.h)), "no-stop-recorded")

    def test_a_journal_failure_never_replaces_the_interrupt(self):
        original = Store.journal

        def lose_cleared(store, story, event, detail=None):
            if event == "activation-stop-cleared":
                raise OSError(28, "No space left on device")
            return original(store, story, event, detail)

        with mock.patch.object(state_module, "fsync_directory", side_effect=KeyboardInterrupt()), mock.patch.object(Store, "journal", lose_cleared):
            with self.assertRaises(KeyboardInterrupt):
                self.c.clear_clock_regression(clearance(self.h))
        self.assertNotIn("activation-stop-cleared", [e["event"] for e in self.store.read_journal()])

    def test_an_interrupt_before_the_replace_writes_no_cleared_line(self):
        with mock.patch.object(Store, "save_run", side_effect=KeyboardInterrupt()):
            with self.assertRaises(KeyboardInterrupt):
                self.c.clear_clock_regression(clearance(self.h))
        self.assertEqual(stop_of(self.store)["code"], "clock-regression")
        self.assertNotIn("activation-stop-cleared", self.events())


# -- I7: an unreadable record is journaled on open ------------------------------------------------------------------------------
class UnreadableRecordJournaledTests(LiveCase):
    """A record of this run's document that fails validation is journaled once as `ledger-unreadable`,
    naming the field (thread I7)."""

    def test_an_invalid_state_dir_is_journaled_once_and_named(self):
        self.h.coordinator()
        set_ledger(self.h, state="pending", state_dir=7)
        for _ in range(3):
            self.h.coordinator(activation=None)
        lines = unconfirmed(self.store)
        self.assertEqual([d["type"] for d in lines], ["ledger-unreadable"])
        self.assertIn("state_dir is not a string", lines[0]["error"])

    def test_malformed_attempts_are_journaled_and_named(self):
        self.h.coordinator()
        set_ledger(self.h, attempts=[])
        self.h.coordinator(activation=None)
        lines = unconfirmed(self.store)
        self.assertEqual([d["type"] for d in lines], ["ledger-unreadable"])
        self.assertIn("attempts is not a non-empty list", lines[0]["error"])

    def test_confirm_reports_an_unreadable_record_as_an_error(self):
        self.h.coordinator()
        set_ledger(self.h, state_dir=None)
        outcome, detail = confirm_activation_use(self.store.load_run().activation, self.h.h.state_dir, "run-live")
        self.assertEqual((outcome, detail["type"], detail["errno"]), ("error", "ledger-unreadable", None))


# -- I-: the refusal names the field ----------------------------------------------------------------------------------------------
class InvalidRecordNamesTheFieldTests(LiveCase):
    """A record that parses but fails validation is not reported as "cannot be read" (thread I-)."""

    def test_activation_use_says_why(self):
        self.h.coordinator()
        set_ledger(self.h, state_dir=["x"])
        self.assertIn("state_dir is not a string", activation_use(self.h.activation.digest, self.h.activation.path)["why"])
        set_ledger(self.h, state_dir=str(self.h.h.state_dir), attempts={"at": T0})
        self.assertIn("attempts", activation_use(self.h.activation.digest, self.h.activation.path)["why"])
        ledger_path(self.h.activation.digest, self.h.activation.path).write_text("[1, 2]", encoding="utf-8")
        self.assertIn("not an object", activation_use(self.h.activation.digest, self.h.activation.path)["why"])

    def test_the_refusal_prints_why_and_a_damaged_file_still_says_cannot_be_read(self):
        message = use_refusal({"unreadable": True, "why": "state_dir is missing"}, "/l/x.json")
        self.assertIn("state_dir is missing", message)
        self.assertNotIn("cannot be read", message)
        self.assertIn("cannot be read", use_refusal({"unreadable": True}, "/l/x.json"))

    def test_a_creation_refusal_names_the_field(self):
        self.h.coordinator()
        set_ledger(self.h, state_dir=7)
        exc = refuses(self, lambda: self.h.coordinator(run_id="run-next"), "activation-used", "activation-mismatch")
        self.assertIn("state_dir is not a string", str(exc))  # every problem is in the message, the use among them
        problems = Activation.creation_problems(self.h.activation, self.h.h.policy, "run-live", T0, state_dir=self.h.h.state_dir)
        self.assertIn("state_dir is not a string", " ".join(m for c, m in problems if c == "activation-used"))


# -- JC: the advice after a move ------------------------------------------------------------------------------------------------
class MovedStateDirAdviceTests(LiveCase):
    """When the recorded state directory is gone, the message says the record cannot be settled from here
    (thread JC)."""

    def mismatch(self, recorded: Path) -> str:
        self.h.coordinator()
        set_ledger(self.h, state="pending", state_dir=str(recorded))
        self.h.coordinator(activation=None)
        lines = [d for d in unconfirmed(self.store) if d["type"] == "state-dir-mismatch"]
        self.assertEqual(len(lines), 1)
        return lines[0]["error"]

    def test_a_directory_that_no_longer_exists_cannot_be_settled_from_here(self):
        message = self.mismatch(Path(self.h.h.tmpdir.name) / "moved-away")
        self.assertIn("cannot be settled from here", message)
        self.assertIn("document is spent", message)
        self.assertIn("moving the directory back", message)
        self.assertNotIn("open the run through the directory it was created under", message)

    def test_a_directory_that_still_exists_is_opened_through(self):
        other = Path(self.h.h.tmpdir.name) / "copied-from"
        other.mkdir()
        message = self.mismatch(other)
        self.assertIn("open the run through the directory it was created under", message)
        self.assertNotIn("spent", message)


# -- JF: a finished reconciliation is answered under a clearable stop -------------------------------------------------------
class ReconcileRepeatUnderClearableStopTests(LiveCase):
    """An authorization already consumed by a reconciliation is answered under a clearable clock stop,
    whatever its previous status; the identical-evidence check still applies (thread JF)."""

    def reconciled_from_pending(self):
        c, auth = r5.ReconcileRevokedUnderClearableStopTests.repair(self)
        refuses(self, lambda: c.cancel(S, "owner stops the repair"), "authorization-unresolved")
        regress(self, self.h, c)
        receipt, evidence = r5.ReconcileRevokedUnderClearableStopTests.evidence()
        c.reconcile_retained_execution(S, auth["id"], receipt, evidence, "r", "p")
        state = self.store.load_story(S)
        state.authorization(auth["id"])["reconciliation"]["previous_status"] = "pending"  # LABELLED MUTATION: reconciled from a pending authorization (e.g. on a cancelled run before)
        self.store.save_story(state)
        return c, auth, receipt, evidence

    def test_an_identical_repeat_is_answered_as_already_reconciled(self):
        c, auth, receipt, evidence = self.reconciled_from_pending()
        with c.operation():
            c._reload_run()
            self.assertTrue(c._clearable_clock_stop())
        state = c.reconcile_retained_execution(S, auth["id"], receipt, evidence, "r", "p")
        self.assertEqual(state.authorization(auth["id"])["status"], "consumed")
        self.assertIn("retained-execution-already-reconciled", self.events())

    def test_a_different_repeat_is_still_conflicting_evidence(self):
        c, auth, receipt, evidence = self.reconciled_from_pending()
        changed = {**receipt, "dispatch": {**receipt["dispatch"], "messageId": "another"}}
        refuses(self, lambda: c.reconcile_retained_execution(S, auth["id"], changed, evidence, "r", "p"), "conflicting-evidence")


# -- JJ: stamped with the high-water mark -------------------------------------------------------------------------------------
class ReconcileStampedWithHighWaterTests(LiveCase):
    """Under a clearable clock stop the reconciliation is stamped with the later of the clock and the
    high-water mark, and records what the clock read (thread JJ)."""

    def test_every_stamp_is_the_high_water_mark(self):
        c, auth = r5.ReconcileRevokedUnderClearableStopTests.repair(self)
        refuses(self, lambda: c.cancel(S, "owner stops the repair"), "authorization-unresolved")
        regress(self, self.h, c)  # high-water mark 12:00, clock 11:00
        receipt, evidence = r5.ReconcileRevokedUnderClearableStopTests.evidence()
        state = c.reconcile_retained_execution(S, auth["id"], receipt, evidence, "r", "p")
        recorded = state.authorization(auth["id"])
        self.assertEqual(recorded["bound_at"], "2026-11-07T12:00:00Z")
        self.assertEqual(recorded["reconciliation"]["at"], "2026-11-07T12:00:00Z")
        self.assertEqual(recorded["reconciliation"]["observed_at"], "2026-11-07T11:00:00Z")
        self.assertEqual(state.task_history[-1]["at"], "2026-11-07T12:00:00Z")
        line = next(e for e in self.store.read_journal() if e["event"] == "retained-execution-reconciled")
        self.assertIn("2026-11-07T120000Z", line["detail"]["backup"])


# -- JM: status says whether the clock stop can be cleared ---------------------------------------------------------------------
class StatusClockStopTests(LiveCase):
    """`status` reports `activation.clock_stop` while a clock-regression stop is recorded (thread JM)."""

    def setUp(self):
        super().setUp()
        self.c = claimed(self.h)

    def test_no_stop_no_report(self):
        self.assertNotIn("clock_stop", self.c.status()["activation"])

    def test_a_clearable_stop(self):
        regress(self, self.h, self.c)
        report = self.c.status()["activation"]["clock_stop"]
        self.assertEqual(report, {"clearable": True, "clear_spent": False, "high_water": "2026-11-07T12:00:00Z", "expires_at": self.store.load_run().activation["expires_at"], "wait_until": "2026-11-07T11:55:00Z", "reason": None})
        self.assertEqual(self.c.status(read_only=True)["activation"]["clock_stop"]["clearable"], True)

    def test_a_spent_clear(self):
        regress(self, self.h, self.c)
        self.h.clock[0] = "2026-11-07T11:58:00Z"
        self.c.clear_clock_regression(clearance(self.h))
        regress(self, self.h, self.c)
        report = self.c.status()["activation"]["clock_stop"]
        self.assertEqual((report["clearable"], report["clear_spent"]), (False, True))
        self.assertIn("spent", report["reason"])

    def test_a_stop_past_the_recorded_window(self):
        regress(self, self.h, self.c)
        raw = json.loads(self.store.run_path.read_text(encoding="utf-8"))
        raw["activation"]["expires_at"] = "2026-11-07T11:30:00Z"  # LABELLED MUTATION: an older run whose window ended before the mark
        self.store.run_path.write_text(json.dumps(raw), encoding="utf-8")
        self.h.clock[0] = "2026-11-07T11:20:00Z"
        report = self.c.status()["activation"]["clock_stop"]
        self.assertFalse(report["clearable"])
        self.assertIn("expires_at", report["reason"])


# -- JQ: the reverse scan ------------------------------------------------------------------------------------------------------
class UnconfirmedReverseScanTests(LiveCase):
    """The unconfirmed set is found by a backward scan that stops at the last confirmation and parses
    only `activation-use-` lines (thread JQ)."""

    def test_only_the_lines_after_the_last_confirmation_are_parsed(self):
        self.h.coordinator()
        for n in range(60):
            self.store.journal(None, "filler", {"n": n})
        self.store.journal(None, "activation-use-unconfirmed", {"type": "OSError", "errno": 5})
        self.store.journal(None, "activation-use-confirmed", {})
        self.store.journal(None, "filler", {"n": 61})
        self.store.journal(None, "activation-use-unconfirmed", {"type": "OSError", "errno": 28})
        self.store.journal(None, "activation-use-unconfirmed", {"type": "state-dir-mismatch", "errno": None})
        with mock.patch.object(state_module.json, "loads", wraps=json.loads) as loads, mock.patch.object(Store, "read_journal", side_effect=AssertionError("full parse")):
            lines, keys = self.store._unconfirmed_since_confirmation()
        self.assertEqual([d["detail"]["errno"] for d in lines], [28, None])
        self.assertEqual(keys, {("OSError", 28, None), ("state-dir-mismatch", None, None)})
        self.assertEqual(loads.call_count, 3)  # two unconfirmed lines and the confirmation; nothing before it

    def test_a_torn_line_is_skipped(self):
        self.h.coordinator()
        self.store.journal(None, "activation-use-unconfirmed", {"type": "OSError", "errno": 5})
        with self.store.journal_path.open("a", encoding="utf-8") as fh:
            fh.write('{"event": "activation-use-confirm\n')
        lines, _ = self.store._unconfirmed_since_confirmation()
        self.assertEqual([d["detail"]["errno"] for d in lines], [5])


# -- JX: a tagged result --------------------------------------------------------------------------------------------------------
class ConfirmTaggedResultTests(LiveCase):
    """`confirm_activation_use` answers on one channel per outcome (thread JX)."""

    def test_the_three_outcomes(self):
        self.assertEqual(confirm_activation_use(None, self.h.h.state_dir, "run-live"), ("unchanged", None))
        self.h.coordinator()
        binding = self.store.load_run().activation
        self.assertEqual(confirm_activation_use(binding, self.h.h.state_dir, "run-live"), ("unchanged", None))  # already committed
        set_ledger(self.h, state="pending")
        with mock.patch.object(activation_module, "_write_ledger", side_effect=OSError(28, "No space left on device")):
            outcome, detail = confirm_activation_use(binding, self.h.h.state_dir, "run-live")
        self.assertEqual((outcome, detail["errno"]), ("error", 28))
        self.assertEqual(confirm_activation_use(binding, self.h.h.state_dir, "run-live"), ("committed", None))

    def test_no_report_success_flag_is_left(self):
        self.assertNotIn("report_success", inspect.signature(confirm_activation_use).parameters)

    def test_a_success_at_creation_is_never_journaled_as_unconfirmed(self):
        with mock.patch.object(state_module, "confirm_activation_use", return_value=("committed", None)):
            self.h.coordinator()
        self.assertEqual(unconfirmed(self.store), [])


# -- Jc: one problem per citation ------------------------------------------------------------------------------------------------
class EvidenceIdZeroWrongRepositoryTests(LiveCase):
    """A wrong-repository citation with id 0 is reported once, as the wrong repository (thread Jc)."""

    def test_one_problem_for_one_bad_citation(self):
        document = Activation(**{**self.h.activation.__dict__, "evidence": {"lifecycle_smoke": "https://github.com/someone/else/pull/107#issuecomment-0", "fresh_review": f"https://github.com/{REPO}/pull/107#pullrequestreview-5"}})
        problems = document.evidence_problems(self.h.h.policy)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn(f"is not a GitHub comment or review URL on {REPO}", problems[0][1])

    def test_the_right_repository_with_id_0_is_still_refused(self):
        document = Activation(**{**self.h.activation.__dict__, "evidence": {"lifecycle_smoke": f"https://github.com/{REPO}/pull/107#issuecomment-0", "fresh_review": f"https://github.com/{REPO}/pull/107#pullrequestreview-5"}})
        problems = document.evidence_problems(self.h.h.policy)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("cites id 0", problems[0][1])


# -- Je: the docstring ------------------------------------------------------------------------------------------------------------
class RetryableCreationDocstringTests(unittest.TestCase):
    """The `_retryable_creation` docstring states the comparison `_same_run` makes (thread Je)."""

    def test_the_docstring_names_samefile(self):
        doc = _retryable_creation.__doc__
        self.assertIn("samefile", doc)
        self.assertNotIn("(compared by realpath)", doc)


# -- Jj: a hung mount -----------------------------------------------------------------------------------------------------------------
class GitTimeoutNamesTheDirectoryTests(ClearanceLocationCase):
    """A git timeout names the directory and the likely cause (thread Jj)."""

    def test_the_timeout_names_the_directory_and_a_hung_mount(self):
        with mock.patch.object(cli_module.subprocess, "run", side_effect=subprocess.TimeoutExpired("git", 30)):
            with self.assertRaises(cli_module.WorkTreeUnknown) as ctx:
                cli_module._work_tree(self.outside.parent)
            error = self.assert_refused(self.clear(self.outside))
        self.assertIn(str(self.outside.parent), str(ctx.exception))
        self.assertIn("hung mount", str(ctx.exception))
        self.assertIn("hung mount", error["message"])

    def test_the_lstat_walk_says_why_it_needs_no_timeout(self):
        self.assertIn("needs no timeout", cli_module._git_entry_above.__doc__)


# -- Jm: only the plain discovery failure ---------------------------------------------------------------------------------------------
class OnlyThePlainAnswerAllowsTests(ClearanceLocationCase):
    """An answer that carries another diagnostic beside the plain message is not "outside every work
    tree" (thread Jm: `fullmatch`, never `search`)."""

    def test_an_extra_diagnostic_is_unknown_and_refuses(self):
        extra = subprocess.CompletedProcess(["git"], 128, stdout="", stderr="error: something\n" + PLAIN)
        with mock.patch.object(cli_module.subprocess, "run", return_value=extra):
            with self.assertRaises(cli_module.WorkTreeUnknown):
                cli_module._work_tree(self.outside.parent)
            self.assert_refused(self.clear(self.outside))

    def test_the_plain_answer_alone_still_allows(self):
        with mock.patch.object(cli_module.subprocess, "run", return_value=subprocess.CompletedProcess(["git"], 128, stdout="", stderr=PLAIN)):
            self.assertIsNone(cli_module._work_tree(self.outside.parent))


# -- Jp: NotADirectoryError means absent ------------------------------------------------------------------------------------------------
class NotADirectoryMeansAbsentTests(LiveCase):
    """A run path whose directory is a regular file cannot hold run.json: the creation is aborted (thread Jp)."""

    def test_a_run_directory_replaced_by_a_file_marks_the_record_aborted(self):
        record_activation_use(self.h.activation, self.h.h.state_dir, "run-live", T0)
        root = self.store.run_path.parent
        root.parent.mkdir(parents=True, exist_ok=True)
        root.write_text("not a directory", encoding="utf-8")
        with self.assertRaises(NotADirectoryError):
            os.stat(self.store.run_path)
        self.assertEqual(abort_activation_use(self.h.activation, self.h.h.state_dir, "run-live", self.store.run_path, cause=OSError(20, "Not a directory")), "aborted")
        self.assertEqual(record(self.h)["state"], "aborted")


# -- Js: the confirmed line needs an unconfirmed one ---------------------------------------------------------------------------------
class ConfirmedNeedsAnUnconfirmedLineTests(LiveCase):
    """A reopen that settles a pending record with no unconfirmed line on record journals nothing (thread Js)."""

    def test_settling_a_crashed_creation_journals_no_confirmation(self):
        self.h.coordinator()
        set_ledger(self.h, state="pending")
        self.h.coordinator(activation=None)
        self.assertEqual(record(self.h)["state"], "committed")
        self.assertNotIn("activation-use-confirmed", self.events())


# -- Ju: the 500-character cap ------------------------------------------------------------------------------------------------------
class AbortCauseCapTests(LiveCase):
    """`abort_cause` is capped at 500 characters, in the record and in the history (thread Ju)."""

    def test_a_long_cause_is_capped(self):
        record_activation_use(self.h.activation, self.h.h.state_dir, "run-live", T0)
        self.assertEqual(abort_activation_use(self.h.activation, self.h.h.state_dir, "run-live", self.store.run_path, cause=OSError(28, "x" * 2000)), "aborted")
        self.assertEqual(len(record(self.h)["abort_cause"]), 500)
        self.h.coordinator()  # the retry moves the cause into the history
        attempts = record(self.h)["attempts"]
        self.assertLessEqual(len(attempts[0]["abort_cause"]), 500)
        self.assertTrue(all(len(a.get("abort_cause", "")) <= 500 for a in attempts))


# -- review follow-up -------------------------------------------------------------------------------------------------------
class UnconfirmedVariantKeyTests(LiveCase):
    """A change of advice is a new line: the mismatch keys on whether the recorded directory exists, the
    unreadable record on the field that failed."""

    def test_a_recorded_directory_that_vanishes_after_the_first_line_adds_a_second(self):
        self.h.coordinator()
        other = Path(self.h.h.tmpdir.name) / "copied-from"
        other.mkdir()
        set_ledger(self.h, state="pending", state_dir=str(other))
        self.h.coordinator(activation=None)
        self.h.coordinator(activation=None)
        other.rmdir()
        self.h.coordinator(activation=None)
        self.h.coordinator(activation=None)
        lines = [d for d in unconfirmed(self.store) if d["type"] == "state-dir-mismatch"]
        self.assertEqual([d["strerror"] for d in lines], ["recorded directory exists", "recorded directory gone"])
        self.assertIn("cannot be settled from here", lines[1]["error"])

    def test_another_failing_field_adds_a_line(self):
        self.h.coordinator()
        set_ledger(self.h, state_dir=7)
        self.h.coordinator(activation=None)
        set_ledger(self.h, state_dir=str(self.h.h.state_dir), attempts=[])
        self.h.coordinator(activation=None)
        self.h.coordinator(activation=None)
        lines = [d for d in unconfirmed(self.store) if d["type"] == "ledger-unreadable"]
        self.assertEqual(len(lines), 2)
        self.assertIn("state_dir", lines[0]["strerror"])
        self.assertIn("attempts", lines[1]["strerror"])


class AbortClassifiesTheRecordFirstTests(LiveCase):
    """The record is classified before run.json is examined: `run-json-exists` is said only of a pending
    record of this run, and a record of another run is `not-this-run` whatever its state."""

    def abort(self) -> str:
        return abort_activation_use(self.h.activation, self.h.h.state_dir, "run-live", self.store.run_path)

    def test_run_json_exists_is_said_only_of_this_runs_pending_record(self):
        self.store.run_path.parent.mkdir(parents=True)
        self.store.run_path.write_text("{}", encoding="utf-8")
        self.assertEqual(self.abort(), "no-record")
        record_activation_use(self.h.activation, self.h.h.state_dir, "run-other", T0)
        self.assertEqual(self.abort(), "not-this-run")
        set_ledger(self.h, run_id="run-live", attempts="x")
        self.assertEqual(self.abort(), "unreadable")
        set_ledger(self.h, attempts=[{"at": T0}], state="committed")
        self.assertEqual(self.abort(), "not-pending")
        set_ledger(self.h, state="pending")
        self.assertEqual(self.abort(), "run-json-exists")

    def test_a_committed_record_of_another_run_is_not_this_run(self):
        record_activation_use(self.h.activation, self.h.h.state_dir, "run-other", T0)
        set_ledger(self.h, state="committed")
        self.assertEqual(self.abort(), "not-this-run")


class RetryCapsACopiedAbortCauseTests(LiveCase):
    """An over-long `abort_cause` already in the record is capped when the retry copies it."""

    def test_a_hand_written_cause_is_capped_in_the_history(self):
        with mock.patch.object(Store, "save_run", side_effect=OSError(28, "No space left on device")):
            with self.assertRaises(OSError):
                self.h.coordinator()
        set_ledger(self.h, abort_cause="y" * 2000)  # written by hand or by an older version
        self.h.coordinator()
        self.assertEqual(len(record(self.h)["attempts"][0]["abort_cause"]), 500)


class ClockStopReportBranchesTests(LiveCase):
    """`clock_stop` says when the clear can run, and why not on every branch."""

    def setUp(self):
        super().setUp()
        self.c = claimed(self.h)
        regress(self, self.h, self.c)

    def report(self, c=None) -> dict:
        return (c or self.c).status()["activation"]["clock_stop"]

    def test_wait_until_is_null_once_the_clock_has_caught_up(self):
        self.assertEqual(self.report()["wait_until"], "2026-11-07T11:55:00Z")
        self.h.clock[0] = "2026-11-07T11:58:00Z"
        self.assertIsNone(self.report()["wait_until"])

    def test_policy_drift_is_not_clearable(self):
        folder = Path(self.h.h.tmpdir.name) / "drift"
        folder.mkdir()
        drifted = load_policy(write_policy(folder, allow='["OM-01.02"]', max_delegated_tasks="7"))
        reopened = Coordinator(self.h.h.fake, drifted, Store(self.h.h.state_dir, "run-live"), now=lambda: self.h.clock[0], live=True, activation=None)
        report = self.report(reopened)
        self.assertFalse(report["clearable"])
        self.assertIn("policy drift", report["reason"])

    def test_an_unparseable_time_has_its_own_reason(self):
        with self.c.operation():
            self.c._reload_run()
            self.c.run.last_observed_at = "not a time"  # LABELLED MUTATION in memory: the load boundary refuses it on disk
            report = self.c._clock_stop_report()
        self.assertFalse(report["clearable"])
        self.assertIn("cannot be parsed", report["reason"])
        self.assertNotIn("expires_at", report["reason"])

    def test_a_cancelled_run(self):
        self.c.cancel_run("owner stops")
        report = self.report()
        self.assertFalse(report["clearable"])
        self.assertIn("cancelled", report["reason"])

    def test_a_spent_wall_clock(self):
        raw = json.loads(self.store.run_path.read_text(encoding="utf-8"))
        raw["started_at"] = "2026-11-07T00:00:00Z"  # LABELLED MUTATION: the budget judged on the 12:00 mark is spent
        self.store.run_path.write_text(json.dumps(raw), encoding="utf-8")
        report = self.report()
        self.assertFalse(report["clearable"])
        self.assertIn("wall-clock budget", report["reason"])


class ReconcileBackupAndDurableStopStampTests(LiveCase):
    """The backup name carries the real observation when it differs from the stamp, and a durable
    clock-regression stop is stamped with the high-water mark too."""

    def revoked_under_stop(self):
        c, auth = r5.ReconcileRevokedUnderClearableStopTests.repair(self)
        refuses(self, lambda: c.cancel(S, "owner stops the repair"), "authorization-unresolved")
        regress(self, self.h, c)
        return c, auth, *r5.ReconcileRevokedUnderClearableStopTests.evidence()

    def test_a_retry_after_a_failed_save_does_not_hit_backup_exists(self):
        c, auth, receipt, evidence = self.revoked_under_stop()
        with mock.patch.object(Store, "save_story", side_effect=OSError(28, "No space left on device")):
            with self.assertRaises(OSError):
                c.reconcile_retained_execution(S, auth["id"], receipt, evidence, "r", "p")
        self.h.clock[0] = "2026-11-07T11:01:00Z"  # still behind the 12:00 mark
        c.reconcile_retained_execution(S, auth["id"], receipt, evidence, "r", "p")
        line = next(e for e in self.store.read_journal() if e["event"] == "retained-execution-reconciled")
        self.assertIn("2026-11-07T120000Z-obs2026-11-07T110100Z", line["detail"]["backup"])

    def test_a_durable_clock_stop_is_stamped_with_the_high_water_mark(self):
        c, auth, receipt, evidence = self.revoked_under_stop()
        self.h.clock[0] = "2026-11-07T11:58:00Z"
        c.clear_clock_regression(clearance(self.h))
        regress(self, self.h, c)  # a second stop: the one clear is spent, the stop is durable
        with c.operation():
            c._reload_run()
            self.assertFalse(c._clearable_clock_stop())
        state = c.reconcile_retained_execution(S, auth["id"], receipt, evidence, "r", "p")
        recorded = state.authorization(auth["id"])
        self.assertEqual((recorded["bound_at"], recorded["reconciliation"]["observed_at"]), ("2026-11-07T12:00:00Z", "2026-11-07T11:00:00Z"))


if __name__ == "__main__":
    unittest.main()
