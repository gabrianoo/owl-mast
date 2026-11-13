"""Regressions for PR #114 round 7: review 5864099379 (17 threads, tracked in issue #118). One class
per finding, F1 to F17 in the order of the issue, with the review thread id in the docstring; each
test is named after the behaviour it pins. F14 to F17 are the assertions the review found missing:
each fails under the mutation its finding names. Every scenario runs on the fixture transport marked
live with temporary state and an injected clock; no real GitHub call and no real task is ever made,
and no test writes to the real use ledger under the home directory."""

from __future__ import annotations

import json
import os
import subprocess
import time
import unittest
from pathlib import Path
from unittest import mock

from automation.tests import test_pr114_round5_findings as r5
from automation.tests.support import IMPLEMENTER, REVIEWER, ok_worktree
from automation.tests.test_activation import S, T0
from automation.tests.test_enabling_repair_1 import claimed, refuses
from automation.tests.test_pr108_review_findings import review_authorized
from automation.tests.test_pr114_review_findings import LiveCase, clearance, regress
from automation.tests.test_pr114_round3_findings import record
from automation.tests.test_pr114_round4_findings import stop_of
from automation.unattended import activation as activation_module
from automation.unattended import cli as cli_module
from automation.unattended import state as state_module
from automation.unattended.activation import Activation, abort_activation_use, activation_use, confirm_activation_use, ledger_path, record_activation_use, run_json_presence, use_refusal
from automation.unattended.errors import Refused
from automation.unattended.state import Store

REPO = "gabrianoo/owl-mast"
ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs" / "unattended-execution.md"
README = ROOT / "automation" / "README.md"
MARK = "2026-11-07T12:00:00Z"  # the high-water mark `regress` leaves; the clock then reads 11:00
BEHIND = "2026-11-07T11:00:00Z"


def set_ledger(h, **fields) -> dict:
    return r5.set_ledger(h, **fields)  # LABELLED MUTATION of the ledger record


def write_ledger(h, data: dict) -> None:
    ledger_path(h.activation.digest, h.activation.path).write_text(json.dumps(data), encoding="utf-8")  # LABELLED MUTATION of the ledger record


def unconfirmed(store: Store) -> list[dict]:
    return [e["detail"] for e in store.read_journal() if e["event"] == "activation-use-unconfirmed"]


def save_then_fail(after=None):
    """`Store.save_run` that replaces run.json and then raises, as a failed directory fsync does;
    ``after`` runs in between (a labelled mutation of the ledger record)."""
    original = Store.save_run

    def save(store, run):
        original(store, run)
        if after is not None:
            after()
        raise OSError(5, "Input/output error")

    return mock.patch.object(Store, "save_run", save)


def stat_refusing(under: Path, error: OSError):
    """`os.stat` that raises ``error`` for every path at or under ``under`` (a directory that cannot be examined)."""
    original = os.stat
    prefix = os.fspath(under)

    def stat(path, *args, **kwargs):
        text = os.fspath(path) if isinstance(path, (str, os.PathLike)) else None
        if text is not None and (text == prefix or text.startswith(prefix + os.sep)):
            raise error
        return original(path, *args, **kwargs)

    return mock.patch.object(activation_module.os, "stat", stat)


# -- F1 ---------------------------------------------------------------------------------------------------------------------
class BadStateIsADamagedRecordTests(LiveCase):
    """F1 (thread 4542174871): a ledger record whose `state` is missing or unknown is `unreadable`
    with `field: "state"`, so confirm reports `ledger-unreadable` and abort reports `unreadable`."""

    def damage(self, state) -> None:
        data = json.loads(ledger_path(self.h.activation.digest, self.h.activation.path).read_text(encoding="utf-8"))
        if state is None:
            data.pop("state", None)
        else:
            data["state"] = state
        write_ledger(self.h, data)

    def test_a_missing_or_unknown_state_is_unreadable_and_names_the_field(self):
        self.h.coordinator()
        for state, words in ((None, "state is missing"), ("bogus", "unknown state 'bogus'"), (7, "unknown state 7"), (["pending"], "unknown state")):
            self.damage(state)
            used = activation_use(self.h.activation.digest, self.h.activation.path)
            self.assertEqual((used["unreadable"], used["field"]), (True, "state"), state)
            self.assertIn(words, used["why"], state)
        for state in ("pending", "committed", "aborted"):
            self.damage(state)
            self.assertEqual(record(self.h)["state"], state)

    def test_confirm_reports_it_as_ledger_unreadable_and_the_open_journals_it(self):
        self.h.coordinator()
        self.damage("bogus")
        outcome, detail = confirm_activation_use(self.store.load_run().activation, self.h.h.state_dir, "run-live")
        self.assertEqual((outcome, detail["type"], detail["field"]), ("error", "ledger-unreadable", "state"))
        self.h.coordinator(activation=None)
        self.h.coordinator(activation=None)
        lines = unconfirmed(self.store)
        self.assertEqual([(d["type"], d["field"]) for d in lines], [("ledger-unreadable", "state")])
        self.assertIn("unknown state 'bogus'", lines[0]["error"])

    def test_a_missing_state_is_journaled_too(self):
        self.h.coordinator()
        self.damage(None)
        self.h.coordinator(activation=None)
        self.assertEqual([(d["type"], d["field"]) for d in unconfirmed(self.store)], [("ledger-unreadable", "state")])

    def test_abort_reports_unreadable_never_not_pending(self):
        record_activation_use(self.h.activation, self.h.h.state_dir, "run-live", T0)
        for state in (None, "bogus"):
            self.damage(state)
            self.assertEqual(abort_activation_use(self.h.activation, self.h.h.state_dir, "run-live", self.store.run_path, cause=OSError(28, "No space left on device")), "unreadable", state)

    def test_it_is_a_use_never_absent(self):
        self.h.coordinator()
        self.damage("bogus")
        exc = refuses(self, lambda: self.h.coordinator(run_id="run-next"), "activation-used", "activation-mismatch")
        self.assertIn("unknown state 'bogus'", str(exc))
        self.assertIn("a damaged record is a use", use_refusal(record(self.h), "/l/x.json"))


# -- F2 ---------------------------------------------------------------------------------------------------------------------
class AbortNoteWhenRunJsonExistsTests(LiveCase):
    """F2 (thread 4542174884): when `save_run` raised after run.json was replaced, the note keeps its
    reason and says "run.json exists: reopen the same run"; it never promises a retry that writes a
    record or refuses."""

    REASONS = (("no-record", "no record"), ("unreadable", "not a valid record"), ("not-pending", "no longer pending"), ("not-this-run", "another run"), ("ledger-error", "could not be marked aborted"))

    def creation_note(self, after) -> str:
        with save_then_fail(after):
            with self.assertRaises(OSError) as ctx:
                self.h.coordinator()
        return " ".join(getattr(ctx.exception, "__notes__", []))

    def assert_reopen(self, note: str, words: str) -> None:
        self.assertIn("run.json exists: reopen the same run", note)
        self.assertIn(words, note)
        for promise in ("a retry writes", "a retry refuses", "a retry is judged", "a retry may refuse"):
            self.assertNotIn(promise, note)

    def test_every_reason_keeps_its_words_and_says_reopen(self):
        for reason, words in self.REASONS:
            self.assert_reopen(state_module.abort_note(reason, "run-live", self.h.h.state_dir, run_json_exists=True), words)
        self.assert_reopen(state_module.abort_note("something-new", "run-live", self.h.h.state_dir, run_json_exists=True), "something-new")

    def test_without_run_json_the_retry_advice_is_unchanged(self):
        self.assertIn("a retry writes a new record", state_module.abort_note("no-record", "run-live", self.h.h.state_dir))
        self.assertIn("a retry refuses activation-used", state_module.abort_note("unreadable", "run-live", self.h.h.state_dir))
        self.assertIn("a retry refuses activation-used", state_module.abort_note("not-this-run", "run-live", self.h.h.state_dir))
        for reason, _ in self.REASONS:
            self.assertNotIn("run.json exists", state_module.abort_note(reason, "run-live", self.h.h.state_dir), reason)

    def test_run_json_that_could_not_be_examined_gives_both_advices(self):
        for reason, words in self.REASONS:
            note = state_module.abort_note(reason, "run-live", self.h.h.state_dir, run_json_exists=None)
            self.assertIn(words, note, reason)
            self.assertIn("whether run.json exists could not be examined: if it does, a retry reopens the same run", note, reason)
            self.assertIn("if it does not, a retry", note, reason)
            self.assertNotIn("run.json exists: reopen", note, reason)

    def test_the_creation_passes_the_unknown_answer_on(self):
        with mock.patch.object(Store, "save_run", side_effect=OSError(5, "Input/output error")), mock.patch.object(state_module, "abort_activation_use", return_value="ledger-error"), \
                mock.patch.object(state_module, "run_json_presence", return_value=None):
            with self.assertRaises(OSError) as ctx:
                self.h.coordinator()
        note = " ".join(getattr(ctx.exception, "__notes__", []))
        self.assertIn("whether run.json exists could not be examined", note)
        self.assertIn("if it does not, a retry refuses activation-used", note)

    def test_a_record_removed_before_the_save_failed(self):
        note = self.creation_note(lambda: ledger_path(self.h.activation.digest, self.h.activation.path).unlink())
        self.assert_reopen(note, "no record")
        self.h.coordinator()  # the advice holds: the retry reopens the run that exists, and writes no record
        self.assertIsNone(record(self.h))

    def test_a_record_of_another_run(self):
        self.assert_reopen(self.creation_note(lambda: set_ledger(self.h, run_id="run-other")), "another run")
        self.h.coordinator()  # reopens; nothing refuses activation-used
        self.assertEqual(record(self.h)["run_id"], "run-other")

    def test_a_record_that_is_no_longer_pending(self):
        self.assert_reopen(self.creation_note(lambda: set_ledger(self.h, state="aborted")), "no longer pending")
        self.h.coordinator()
        self.assertEqual(record(self.h)["state"], "committed")  # as the note says: the reopen confirms an aborted record of this run

    def test_an_unreadable_record(self):
        self.assert_reopen(self.creation_note(lambda: set_ledger(self.h, state_dir=7)), "not a valid record")
        self.h.coordinator()
        self.assertEqual([d["type"] for d in unconfirmed(self.store)], ["ledger-unreadable"])  # as the note says

    def test_run_json_is_examined_first_and_only_absence_marks_the_record(self):
        self.assertIs(run_json_presence(self.store.run_path), False)
        record_activation_use(self.h.activation, self.h.h.state_dir, "run-live", T0)
        with stat_refusing(self.store.root, PermissionError(13, "Permission denied")):
            self.assertIsNone(run_json_presence(self.store.run_path))
            self.assertEqual(abort_activation_use(self.h.activation, self.h.h.state_dir, "run-live", self.store.run_path), "ledger-error")
        self.assertEqual(record(self.h)["state"], "pending")
        self.store.root.mkdir(parents=True)
        self.store.run_path.write_text("{}", encoding="utf-8")
        self.assertIs(run_json_presence(self.store.run_path), True)


# -- F3 ---------------------------------------------------------------------------------------------------------------------
class ConsequenceMatchesTheErrorTests(LiveCase):
    """F3 (thread 4542174894): the journaled `consequence` says what the condition means: a damaged
    record, or one that cannot be settled from here; "stays pending, every open retries" is said
    only of a confirmation that could not be written (`OSError` / `Refused`)."""

    RETRY = "every later open retries the confirmation"

    def test_a_damaged_record_is_damaged_not_pending(self):
        self.h.coordinator()
        set_ledger(self.h, state="pending", state_dir=7)
        self.h.coordinator(activation=None)
        (line,) = unconfirmed(self.store)
        self.assertIn("damaged, not pending", line["consequence"])
        self.assertIn("no open repairs it", line["consequence"])
        self.assertNotIn(self.RETRY, line["consequence"])

    def test_a_record_under_a_directory_that_is_gone_cannot_be_settled_from_here(self):
        self.h.coordinator()
        set_ledger(self.h, state="pending", state_dir=str(Path(self.h.h.tmpdir.name) / "moved-away"))
        self.h.coordinator(activation=None)
        (line,) = unconfirmed(self.store)
        self.assertEqual(line["type"], "state-dir-mismatch")
        self.assertIn("cannot be settled from here", line["consequence"])
        self.assertIn("cannot be settled from here", line["error"])  # the line no longer contradicts itself
        self.assertNotIn(self.RETRY, line["consequence"])
        self.assertNotIn("stays pending;", line["consequence"])

    def test_a_record_whose_run_is_still_under_the_recorded_directory(self):
        self.h.coordinator()
        other = Path(self.h.h.tmpdir.name) / "created-under"
        (other / "run-live").mkdir(parents=True)
        (other / "run-live" / "run.json").write_text("{}", encoding="utf-8")
        set_ledger(self.h, state="pending", state_dir=str(other))
        self.h.coordinator(activation=None)
        (line,) = unconfirmed(self.store)
        self.assertIn("cannot be settled from this state directory", line["consequence"])
        self.assertIn("through the recorded directory confirms it", line["consequence"])
        self.assertNotIn(self.RETRY, line["consequence"])

    def test_a_failed_write_still_stays_pending_and_is_retried(self):
        self.h.coordinator()
        for error in (OSError(28, "No space left on device"), Refused("the ledger has no home", code="activation-ledger-unwritable")):
            set_ledger(self.h, state="pending")
            with mock.patch.object(activation_module, "_write_ledger", side_effect=error):
                self.h.coordinator(activation=None)
        lines = unconfirmed(self.store)
        self.assertEqual([d["type"] for d in lines], ["OSError", "Refused"])
        for line in lines:
            self.assertIn("stays pending", line["consequence"])
            self.assertIn(self.RETRY, line["consequence"])

    def test_confirm_returns_the_consequence_with_each_error(self):
        self.h.coordinator()
        binding = self.store.load_run().activation
        set_ledger(self.h, state="pending", attempts=[])
        self.assertIn("damaged", confirm_activation_use(binding, self.h.h.state_dir, "run-live")[1]["consequence"])
        set_ledger(self.h, attempts=[{"at": T0}])
        with mock.patch.object(activation_module, "_write_ledger", side_effect=OSError(28, "No space left on device")):
            self.assertIsNone(confirm_activation_use(binding, self.h.h.state_dir, "run-live")[1]["consequence"])  # the caller's fallback applies


# -- F4 ---------------------------------------------------------------------------------------------------------------------
class UnchangedCommittedRecordSettlesTests(LiveCase):
    """F4 (thread 4542174902): an open that finds this run's record `committed` settles the
    unconfirmed lines on record (`activation-use-confirmed`), so a later recurrence is journaled again."""

    def test_a_record_restored_by_hand_settles_and_a_recurrence_is_journaled_again(self):
        self.h.coordinator()
        good = record(self.h)["state_dir"]
        set_ledger(self.h, state="pending", state_dir=7)
        self.h.coordinator(activation=None)
        self.assertEqual(len(unconfirmed(self.store)), 1)
        self.assertNotIn("activation-use-confirmed", self.events())
        set_ledger(self.h, state="committed", state_dir=good)  # restored by hand
        self.h.coordinator(activation=None)
        self.assertEqual(self.events().count("activation-use-confirmed"), 1)
        self.h.coordinator(activation=None)
        self.assertEqual(self.events().count("activation-use-confirmed"), 1)  # nothing unconfirmed since: no second line
        set_ledger(self.h, state="pending", state_dir=7)  # the same damage again
        self.h.coordinator(activation=None)
        self.assertEqual([d["field"] for d in unconfirmed(self.store)], ["state_dir", "state_dir"])  # journaled again, not suppressed

    def test_a_run_committed_from_its_original_directory_settles_a_mismatch(self):
        self.h.coordinator()
        good = record(self.h)["state_dir"]
        set_ledger(self.h, state="pending", state_dir=str(Path(self.h.h.tmpdir.name) / "moved-away"))
        self.h.coordinator(activation=None)
        self.assertEqual([d["type"] for d in unconfirmed(self.store)], ["state-dir-mismatch"])
        set_ledger(self.h, state="committed", state_dir=good)
        self.h.coordinator(activation=None)
        self.assertEqual(self.events().count("activation-use-confirmed"), 1)

    def test_a_copy_is_settled_once_the_original_committed(self):
        self.h.coordinator()
        other = Path(self.h.h.tmpdir.name) / "created-under"
        (other / "run-live").mkdir(parents=True)
        (other / "run-live" / "run.json").write_text("{}", encoding="utf-8")
        set_ledger(self.h, state="pending", state_dir=str(other))  # this state directory is the copy
        self.h.coordinator(activation=None)
        self.assertEqual([d["type"] for d in unconfirmed(self.store)], ["state-dir-mismatch"])
        set_ledger(self.h, state="committed")  # the original was opened through its own directory; the record still names it
        self.assertEqual(confirm_activation_use(self.store.load_run().activation, self.h.h.state_dir, "run-live"), ("unchanged", {"committed": True}))
        self.h.coordinator(activation=None)
        self.assertEqual(self.events().count("activation-use-confirmed"), 1)

    def test_confirm_tells_this_runs_committed_record_from_every_other_unchanged(self):
        self.h.coordinator()
        binding = self.store.load_run().activation
        self.assertEqual(confirm_activation_use(binding, self.h.h.state_dir, "run-live"), ("unchanged", {"committed": True}))
        set_ledger(self.h, run_id="run-other")
        self.assertEqual(confirm_activation_use(binding, self.h.h.state_dir, "run-live"), ("unchanged", None))  # committed, but another run's
        ledger_path(self.h.activation.digest, self.h.activation.path).unlink()
        self.assertEqual(confirm_activation_use(binding, self.h.h.state_dir, "run-live"), ("unchanged", None))

    def test_an_ordinary_open_journals_nothing(self):
        self.h.coordinator()
        before = self.events()
        self.h.coordinator(activation=None)
        self.assertEqual(self.events(), before)


# -- F5 ---------------------------------------------------------------------------------------------------------------------
class VariantFieldAndReadErrnoTests(LiveCase):
    """F5 (thread 4542174916): the variant is carried in `field`, which is part of the dedupe key;
    `strerror` holds operating-system text only; a ledger file that cannot be read keeps its errno,
    so EACCES and EIO are two lines."""

    def reading_fails(self, error: OSError):
        original = Path.read_text
        target = ledger_path(self.h.activation.digest, self.h.activation.path)

        def read_text(path, *args, **kwargs):
            if path == target:
                raise error
            return original(path, *args, **kwargs)

        return mock.patch.object(Path, "read_text", read_text)

    def test_a_read_error_keeps_its_errno_and_two_errnos_are_two_lines(self):
        self.h.coordinator()
        for error in (PermissionError(13, "Permission denied"), OSError(5, "Input/output error"), PermissionError(13, "Permission denied")):
            with self.reading_fails(error):
                self.assertEqual(activation_use(self.h.activation.digest, self.h.activation.path)["errno"], error.errno)
                self.h.coordinator(activation=None)
        lines = unconfirmed(self.store)
        self.assertEqual([(d["type"], d["errno"], d["field"], d["strerror"]) for d in lines],
                         [("ledger-unreadable", 13, "file", "Permission denied"), ("ledger-unreadable", 5, "file", "Input/output error")])
        self.assertIn("Permission denied", lines[0]["error"])
        self.assertIn("Input/output error", lines[1]["error"])
        for line in lines:  # a refused read says nothing about the record: it is not called damaged, and the next open tries again
            self.assertIn("cannot be read", line["error"])
            self.assertNotIn("is not a valid record", line["error"])
            self.assertIn("unknown while the file cannot be read", line["consequence"])
            self.assertIn("every later open tries again", line["consequence"])
            self.assertIn("it is a use", line["consequence"])
            self.assertNotIn("damaged", line["consequence"])

    def test_a_refused_read_is_retried_by_the_next_open(self):
        self.h.coordinator()
        set_ledger(self.h, state="pending")
        with self.reading_fails(PermissionError(13, "Permission denied")):
            self.h.coordinator(activation=None)
        self.assertEqual(record(self.h)["state"], "pending")
        self.h.coordinator(activation=None)  # readable again: the record was intact
        self.assertEqual(record(self.h)["state"], "committed")
        self.assertEqual(self.events().count("activation-use-confirmed"), 1)

    def test_a_torn_ledger_file_has_its_own_field(self):
        self.h.coordinator()
        ledger_path(self.h.activation.digest, self.h.activation.path).write_text("{torn", encoding="utf-8")  # LABELLED MUTATION
        self.assertEqual(activation_use(self.h.activation.digest, self.h.activation.path), {"unreadable": True, "field": "json", "why": "the file is not JSON"})
        self.h.coordinator(activation=None)
        self.h.coordinator(activation=None)
        lines = unconfirmed(self.store)
        self.assertEqual([(d["type"], d["field"], d["errno"], d["strerror"]) for d in lines], [("ledger-unreadable", "json", None, None)])
        self.assertIn("the file is not JSON", lines[0]["error"])
        self.assertIn("damaged, not pending", lines[0]["consequence"])
        with self.reading_fails(OSError("no errno")):  # an errno-less read error is another key: a second line
            self.h.coordinator(activation=None)
        self.assertEqual([d["field"] for d in unconfirmed(self.store)], ["json", "file"])

    def test_a_read_error_is_still_a_use_that_cannot_be_read(self):
        self.h.coordinator()
        with self.reading_fails(PermissionError(13, "Permission denied")):
            used = activation_use(self.h.activation.digest, self.h.activation.path)
        self.assertEqual((used["unreadable"], used["field"], used["strerror"]), (True, "file", "Permission denied"))
        message = use_refusal(used, "/l/x.json")
        self.assertIn("cannot be read", message)
        self.assertIn("Permission denied", message)
        self.assertNotIn("exists", message)  # EACCES on a parent directory refuses the same way: existence is not claimed

    def test_strerror_is_never_a_field_name_or_a_directory_state(self):
        self.h.coordinator()
        set_ledger(self.h, state="pending", state_dir=7)
        self.h.coordinator(activation=None)
        set_ledger(self.h, state_dir=str(Path(self.h.h.tmpdir.name) / "moved-away"))
        self.h.coordinator(activation=None)
        lines = unconfirmed(self.store)
        self.assertEqual([(d["type"], d["field"], d["strerror"]) for d in lines], [("ledger-unreadable", "state_dir", None), ("state-dir-mismatch", "recorded directory gone", None)])

    def test_the_field_is_in_the_dedupe_key(self):
        key = Store._unconfirmed_key
        self.assertEqual(key({"type": "ledger-unreadable", "errno": None, "strerror": None, "field": "state"}), ("ledger-unreadable", None, "state"))
        self.assertNotEqual(key({"type": "ledger-unreadable", "errno": None, "field": "state"}), key({"type": "ledger-unreadable", "errno": None, "field": "attempts"}))
        self.assertNotEqual(key({"type": "ledger-unreadable", "errno": 13, "field": "file"}), key({"type": "ledger-unreadable", "errno": 5, "field": "file"}))
        self.assertEqual(key({"type": "OSError", "errno": None, "strerror": "odd", "field": None}), ("OSError", None, "odd"))  # an OSError without an errno is still told apart by its strerror
        self.assertEqual(key({"type": "OSError", "errno": 28, "strerror": "x", "field": None}), ("OSError", 28, None))

    def test_a_line_written_before_the_field_existed_still_dedupes(self):
        self.h.coordinator()
        self.store.journal(None, "activation-use-unconfirmed", {"type": "ledger-unreadable", "errno": None, "strerror": "state_dir"})  # the round-6 shape
        set_ledger(self.h, state="pending", state_dir=7)
        self.h.coordinator(activation=None)
        self.assertEqual(len(unconfirmed(self.store)), 1)


# -- F6 ---------------------------------------------------------------------------------------------------------------------
class MovedDirectoryFourAdvicesTests(LiveCase):
    """F6 (thread 4542174922): the advice after a move depends on what the recorded path holds: the
    run itself, something without it, nothing, or it cannot be examined; "gone" is said only on
    `FileNotFoundError` / `NotADirectoryError`."""

    def setUp(self):
        super().setUp()
        self.h.coordinator()
        self.recorded = Path(self.h.h.tmpdir.name) / "created-under"

    def line(self) -> dict:
        set_ledger(self.h, state="pending", state_dir=str(self.recorded))
        self.h.coordinator(activation=None)
        lines = [d for d in unconfirmed(self.store) if d["type"] == "state-dir-mismatch"]
        return lines[-1]

    def test_the_recorded_directory_holds_the_run(self):
        (self.recorded / "run-live").mkdir(parents=True)
        (self.recorded / "run-live" / "run.json").write_text("{}", encoding="utf-8")
        line = self.line()
        self.assertEqual(line["field"], "recorded directory holds the run")
        self.assertIn("open the run through the directory it was created under", line["error"])
        self.assertNotIn("spent", line["error"])

    def test_an_unrelated_directory_at_the_recorded_path_holds_no_run(self):
        (self.recorded / "run-else").mkdir(parents=True)
        (self.recorded / "run-else" / "run.json").write_text("{}", encoding="utf-8")
        line = self.line()
        self.assertEqual(line["field"], "recorded path exists without the run")
        self.assertIn("holds no run 'run-live'", line["error"])
        self.assertIn("cannot be settled from here", line["error"])
        self.assertNotIn("open the run through the directory it was created under", line["error"])
        self.assertNotIn("no longer exists", line["error"])
        self.assertIn("cannot be settled from here", line["consequence"])
        self.assertNotIn("every later open retries", line["consequence"])

    def test_a_recorded_path_that_is_not_a_directory_is_not_gone(self):
        self.recorded.write_text("a file", encoding="utf-8")
        line = self.line()
        self.assertEqual(line["field"], "recorded path exists without the run")
        self.assertNotIn("no longer exists", line["error"])

    def test_a_recorded_directory_that_is_gone(self):
        line = self.line()
        self.assertEqual(line["field"], "recorded directory gone")
        self.assertIn("no longer exists", line["error"])
        self.assertIn("moving the directory back", line["error"])

    def test_a_recorded_directory_that_cannot_be_examined_is_not_gone(self):
        with stat_refusing(self.recorded, PermissionError(13, "Permission denied")):
            line = self.line()
        self.assertEqual((line["field"], line["errno"], line["strerror"]), ("recorded directory cannot be examined", 13, "Permission denied"))
        self.assertIn("cannot be examined", line["error"])
        self.assertNotIn("no longer exists", line["error"])
        self.assertNotIn("is spent", line["error"])
        self.assertIn("cannot be settled from here", line["consequence"])
        self.assertNotIn("every later open retries", line["consequence"])

    def test_a_recorded_path_that_is_not_absolute_is_never_resolved_against_the_current_directory(self):
        here = Path(self.h.h.tmpdir.name) / "cwd"
        (here / "run-live").mkdir(parents=True)
        (here / "run-live" / "run.json").write_text("{}", encoding="utf-8")
        (here / "rel" / "run-live").mkdir(parents=True)
        (here / "rel" / "run-live" / "run.json").write_text("{}", encoding="utf-8")
        before = os.getcwd()
        os.chdir(here)
        try:
            for recorded in ("", ".", "rel"):
                found, problem = activation_module._recorded_run(recorded, "run-live")
                self.assertEqual(found, "unknown", recorded)
                self.assertIn("not an absolute path", str(problem))
            self.assertEqual(activation_module._recorded_run(str(here), "run-live")[0], "run")
        finally:
            os.chdir(before)

    def test_only_absence_reads_as_gone(self):
        probe = activation_module._recorded_run
        self.assertEqual(probe(str(self.recorded), "run-live")[0], "gone")
        with stat_refusing(self.recorded, OSError(5, "Input/output error")):
            found, problem = probe(str(self.recorded), "run-live")
        self.assertEqual((found, problem.errno), ("unknown", 5))
        self.assertEqual(probe("bad\0path", "run-live")[0], "unknown")
        self.assertEqual(probe(7, "run-live")[0], "unknown")

    def test_each_variant_is_its_own_line(self):
        fields = [self.line()["field"]]  # gone
        self.recorded.mkdir()
        fields.append(self.line()["field"])  # exists, no run
        (self.recorded / "run-live").mkdir()
        (self.recorded / "run-live" / "run.json").write_text("{}", encoding="utf-8")
        fields.append(self.line()["field"])  # holds the run
        self.h.coordinator(activation=None)
        self.assertEqual(fields, ["recorded directory gone", "recorded path exists without the run", "recorded directory holds the run"])
        self.assertEqual(len([d for d in unconfirmed(self.store) if d["type"] == "state-dir-mismatch"]), 3)


# -- F7 ---------------------------------------------------------------------------------------------------------------------
class ClearNeedsTheActivationTests(LiveCase):
    """F7 (thread 4542174930): `clock_stop` reports whether the activation the clear needs is
    presented and current (`presented_current`, `clear_requires`); `clearable` keeps its meaning."""

    def setUp(self):
        super().setUp()
        self.c = claimed(self.h)
        regress(self, self.h, self.c)

    def test_no_activation_presented(self):
        bare = self.h.coordinator(activation=None)
        report = bare.status()["activation"]["clock_stop"]
        self.assertIs(report["clearable"], True)  # unchanged: the stop is not durable
        self.assertIsNone(report["reason"])
        self.assertIs(report["presented_current"], False)
        self.assertIn("--activation", report["clear_requires"])
        self.assertIn("none is presented", report["clear_requires"])
        self.assertIn("activation-required", report["clear_requires"])
        self.assertNotIn("judged again", report["clear_requires"])  # no document was judged: waiting does not present one
        self.h.clock[0] = "2026-11-07T11:58:00Z"
        refuses(self, lambda: bare.clear_clock_regression(clearance(self.h)), "activation-required")  # what the report warned of

    def test_an_activation_that_is_not_current(self):
        self.h.clock[0] = "2026-11-07T09:50:00Z"  # before issued_at: the document is the run's, and not yet valid
        report = self.c.status()["activation"]["clock_stop"]
        self.assertIs(report["clearable"], True)
        self.assertIs(report["presented_current"], False)
        self.assertIn("--activation", report["clear_requires"])
        self.assertIn("activation-not-yet-valid", report["clear_requires"])
        self.assertIn("before issued_at", report["clear_requires"])
        self.assertEqual(report["wait_until"], "2026-11-07T11:55:00Z")  # the clock is behind: waiting is what is needed
        self.assertIn("judged on the present clock (2026-11-07T09:50:00Z)", report["clear_requires"])
        self.assertIn("judged again once the clock reaches 2026-11-07T11:55:00Z", report["clear_requires"])
        refuses(self, lambda: self.c.clear_clock_regression(clearance(self.h)), "activation-not-yet-valid")

    def test_the_current_activation_requires_nothing_more(self):
        report = self.c.status()["activation"]["clock_stop"]
        self.assertEqual((report["clearable"], report["presented_current"], report["clear_requires"]), (True, True, None))
        self.assertEqual(self.c.status(read_only=True)["activation"]["clock_stop"]["presented_current"], True)

    def test_a_stop_that_is_not_clearable_requires_no_document(self):
        self.c.cancel_run("owner stops")
        report = self.h.coordinator(activation=None).status()["activation"]["clock_stop"]
        self.assertEqual((report["clearable"], report["presented_current"], report["clear_requires"]), (False, False, None))
        self.assertIn("cancelled", report["reason"])


# -- F8 ---------------------------------------------------------------------------------------------------------------------
class PastTheWindowReasonTests(LiveCase):
    """F8 (thread 4542174944): the past-the-window reason prints the time that is past `expires_at`
    and says whether it is the clock or the mark."""

    def setUp(self):
        super().setUp()
        self.c = claimed(self.h)
        regress(self, self.h, self.c)

    def test_the_clock_passed_the_window_and_the_mark_did_not(self):
        self.h.clock[0] = "2026-11-07T14:30:00Z"  # past expires_at 14:00; the mark is still 12:00
        report = self.c.status()["activation"]["clock_stop"]
        self.assertFalse(report["clearable"])
        self.assertEqual(report["high_water"], MARK)
        self.assertIn("2026-11-07T14:30:00Z (the clock)", report["reason"])
        self.assertIn("past the recorded expires_at 2026-11-07T14:00:00Z", report["reason"])
        self.assertNotIn(MARK, report["reason"])  # a time before expires_at is never given as the reason for being past it

    def test_the_mark_passed_the_window(self):
        raw = json.loads(self.store.run_path.read_text(encoding="utf-8"))
        raw["activation"]["expires_at"] = "2026-11-07T11:30:00Z"  # LABELLED MUTATION: an older run whose window ended before the mark
        self.store.run_path.write_text(json.dumps(raw), encoding="utf-8")
        self.h.clock[0] = "2026-11-07T11:20:00Z"
        report = self.c.status()["activation"]["clock_stop"]
        self.assertFalse(report["clearable"])
        self.assertIn(f"{MARK} (the high-water mark)", report["reason"])
        self.assertNotIn("11:20", report["reason"])


# -- F9 ---------------------------------------------------------------------------------------------------------------------
class StateStampsUnderAClockStopTests(LiveCase):
    """F9 (thread 4542174952): while a clock-regression stop is recorded, every state stamp is at
    least the high-water mark, whichever cleanup operation writes it; the journal `at` stays the
    clock the Store read and is ordered by `seq` (documented)."""

    def test_record_task_terminal(self):
        c = claimed(self.h)
        regress(self, self.h, c)
        state = c.record_task_terminal(S, self.h.terminal())
        self.assertEqual(state.task_history[-1]["at"], MARK)

    def terminal_operation(self, operation: str) -> None:
        c = claimed(self.h)
        regress(self, self.h, c)
        state = getattr(c, operation)(S, "owner stops", self.h.terminal())
        self.assertEqual(state.blocked["at"], MARK)
        self.assertEqual(state.task_history[-1]["at"], MARK)
        cleanup = [i for i in state.intents if i.kind in ("release", "block")]
        self.assertEqual([i.completed_at for i in cleanup], [MARK])

    def test_block(self):
        self.terminal_operation("block")

    def test_cancel(self):
        self.terminal_operation("cancel")

    def test_a_cleanup_bind(self):
        c = review_authorized(self.h)
        regress(self, self.h, c)
        bare = self.h.coordinator(activation=None)
        refuses(self, lambda: bare.bind_receipt(S, REVIEWER, worktree_check=ok_worktree, for_cleanup=True, reason="activation file lost"), "cleanup-requested")
        state = self.store.load_story(S)
        self.assertEqual(state.active_task["bound_at"], MARK)
        self.assertEqual(state.unresolved_authorization(), None)
        self.assertEqual(state.authorizations[-1]["bound_at"], MARK)

    def test_an_authorization_revoked_and_one_resolved(self):
        c = review_authorized(self.h)
        regress(self, self.h, c)
        refuses(self, lambda: c.cancel(S, "owner stops"), "authorization-unresolved")  # revokes the pending review authorization
        auth = self.store.load_story(S).unresolved_authorization()
        self.assertEqual((auth["status"], auth["revoked_at"]), ("revoked", MARK))
        state = c.record_no_launch(S, {"authorization": auth["id"], "reason": "delegate_task was never called"})
        self.assertEqual(state.authorization(auth["id"])["resolved_at"], MARK)

    def test_a_terminal_entry_never_sorts_before_a_floored_reconcile_entry(self):
        c, auth = r5.ReconcileRevokedUnderClearableStopTests.repair(self)
        refuses(self, lambda: c.cancel(S, "owner stops the repair"), "authorization-unresolved")
        regress(self, self.h, c)
        receipt, evidence = r5.ReconcileRevokedUnderClearableStopTests.evidence()
        state = c.reconcile_retained_execution(S, auth["id"], receipt, evidence, "r", "p")
        self.h.clock[0] = "2026-11-07T11:10:00Z"  # still behind the mark
        state = c.cancel(S, "owner stops")
        stamps = [entry["at"] for entry in state.task_history]
        self.assertEqual(stamps, sorted(stamps))
        self.assertEqual(state.blocked["at"], MARK)

    def test_without_a_stop_the_stamp_is_the_clock_at_or_past_the_mark_or_when_not_live(self):
        c = claimed(self.h)
        self.h.clock[0] = MARK
        c.status()
        self.assertEqual(c._stamp(), MARK)  # at the mark
        self.h.clock[0] = "2026-11-07T11:57:00Z"  # behind the mark, inside the tolerance: no stop is recorded
        c.environment = "fixture"  # LABELLED MUTATION in memory: a fixture run has no mark
        self.assertEqual(c._stamp(), "2026-11-07T11:57:00Z")
        c.environment = "live"
        self.h.clock[0] = "2026-11-07T12:10:00Z"  # past the mark
        state = c.record_task_terminal(S, self.h.terminal())
        self.assertIsNone(stop_of(self.store))
        self.assertEqual(state.task_history[-1]["at"], "2026-11-07T12:10:00Z")

    def test_without_a_stop_a_clock_inside_the_tolerance_behind_the_mark_is_floored(self):
        c = claimed(self.h)
        self.h.clock[0] = MARK
        c.status()
        self.h.clock[0] = "2026-11-07T11:57:00Z"
        state = c.record_task_terminal(S, self.h.terminal())
        self.assertIsNone(stop_of(self.store))
        self.assertEqual(state.task_history[-1]["at"], MARK)

    def test_a_stamp_after_the_clear_never_sorts_before_one_floored_during_the_stop(self):
        c = review_authorized(self.h)
        regress(self, self.h, c)
        refuses(self, lambda: c.cancel(S, "owner stops"), "authorization-unresolved")  # revoked during the stop: floored at the mark
        self.h.clock[0] = "2026-11-07T11:58:00Z"  # the clear runs inside the tolerance, still behind the mark
        c.clear_clock_regression(clearance(self.h))
        self.assertIsNone(stop_of(self.store))
        auth = self.store.load_story(S).unresolved_authorization()
        state = c.record_no_launch(S, {"authorization": auth["id"], "reason": "delegate_task was never called"})
        resolved = state.authorization(auth["id"])
        self.assertEqual((resolved["revoked_at"], resolved["resolved_at"]), (MARK, MARK))
        self.assertGreaterEqual(resolved["resolved_at"], resolved["revoked_at"])

    def test_a_cleanup_bind_of_the_implementer_floors_claimed_at(self):
        c = self.h.coordinator()
        c.reserve(S, self.h.h.snapshot, "base")
        regress(self, self.h, c)
        bare = self.h.coordinator(activation=None)
        refuses(self, lambda: bare.bind_receipt(S, IMPLEMENTER, str(self.h.h.worktree), "t3/om-01-02", ok_worktree, for_cleanup=True, reason="activation file lost"), "cleanup-requested")
        state = self.store.load_story(S)
        self.assertEqual((state.claim["claimed_at"], state.active_task["bound_at"], state.authorizations[-1]["bound_at"]), (MARK, MARK, MARK))

    def test_a_clock_ahead_of_the_mark_stamps_the_clock(self):
        c = claimed(self.h)
        regress(self, self.h, c)
        self.h.clock[0] = "2026-11-07T12:20:00Z"
        state = c.record_task_terminal(S, self.h.terminal())
        self.assertEqual(state.task_history[-1]["at"], "2026-11-07T12:20:00Z")

    def test_the_journal_is_not_floored_and_the_rule_is_documented(self):
        c = claimed(self.h)
        regress(self, self.h, c)
        with mock.patch.object(state_module, "utcnow", return_value=BEHIND):  # what the Store's wall clock reads
            c.record_task_terminal(S, self.h.terminal())
        line = next(e for e in reversed(self.store.read_journal()) if e["event"] == "task-terminal")
        self.assertEqual(line["at"], BEHIND)  # the record of what the clock read
        self.assertEqual(line["detail"]["at"], MARK)  # the state stamp it journals is floored
        self.assertEqual([e["seq"] for e in self.store.read_journal()], list(range(1, len(self.store.read_journal()) + 1)))
        text = DOCS.read_text(encoding="utf-8")
        self.assertIn("every state stamp", text)
        self.assertIn("ordered by `seq`", text)


# -- F10 --------------------------------------------------------------------------------------------------------------------
class RecoveredRunStartedTests(LiveCase):
    """F10 (thread 4542174959): a reopen that commits the record of a run whose journal has no
    `run-started` line journals it with `recovered: true`."""

    def started(self) -> list[dict]:
        return [e["detail"] for e in self.store.read_journal() if e["event"] == "run-started"]

    def test_a_reopen_after_a_crashed_creation_journals_the_start(self):
        with save_then_fail():
            with self.assertRaises(OSError):
                self.h.coordinator()
        self.assertEqual(self.started(), [])
        self.h.coordinator()
        self.assertEqual(record(self.h)["state"], "committed")
        (line,) = self.started()
        run = self.store.load_run()
        self.assertIs(line["recovered"], True)
        self.assertEqual((line["activation"], line["instance"], line["started_at"], line["environment"]), (run.activation, run.instance, run.started_at, "live"))
        self.h.coordinator()
        self.assertEqual(len(self.started()), 1)  # once

    def test_a_creation_that_died_after_the_confirmation_is_recovered_too(self):
        self.h.coordinator()
        self.store.journal_path.unlink()  # LABELLED MUTATION: the process died after the ledger confirmation and before the first journal line
        self.assertEqual(record(self.h)["state"], "committed")
        self.h.coordinator(activation=None)
        (line,) = self.started()
        self.assertIs(line["recovered"], True)
        self.assertEqual(line["started_at"], self.store.load_run().started_at)
        self.h.coordinator(activation=None)
        self.assertEqual(len(self.started()), 1)

    def test_an_open_whose_confirmation_errors_still_journals_the_start(self):
        for damage, kind in ((dict(state_dir=7), "ledger-unreadable"), (dict(state_dir=str(Path(self.h.h.tmpdir.name) / "moved-away")), "state-dir-mismatch")):
            with self.subTest(kind):
                with save_then_fail(lambda: set_ledger(self.h, **damage)):
                    with self.assertRaises(OSError):
                        self.h.coordinator()
                self.h.coordinator()
                self.assertEqual([d.get("recovered") for d in self.started()], [True])
                self.assertEqual([d["type"] for d in unconfirmed(self.store)], [kind])
                self.assertLess(self.events().index("run-started"), self.events().index("activation-use-unconfirmed"))
            self.tearDown()
            self.setUp()

    def test_an_ordinary_creation_is_not_recovered(self):
        self.h.coordinator()
        (line,) = self.started()
        self.assertNotIn("recovered", line)

    def test_a_reopen_that_commits_a_run_whose_start_is_on_record_adds_no_line(self):
        self.h.coordinator()
        set_ledger(self.h, state="pending")  # the confirmation was lost after run-started was journaled
        self.h.coordinator(activation=None)
        self.assertEqual(record(self.h)["state"], "committed")
        self.assertEqual(len(self.started()), 1)
        self.assertNotIn("recovered", self.started()[0])

    def test_a_torn_line_is_not_read_as_the_start(self):
        with save_then_fail():
            with self.assertRaises(OSError):
                self.h.coordinator()
        self.store.root.mkdir(parents=True, exist_ok=True)
        self.store.journal_path.write_text('{"event": "run-started", "seq": 1\n', encoding="utf-8")  # torn by the crash
        self.h.coordinator()
        self.assertEqual([d.get("recovered") for d in self.started()], [True])


# -- F11 --------------------------------------------------------------------------------------------------------------------
class ScanCostDocstringTests(LiveCase):
    """F11 (thread 4542174965): the docstring states the real cost of the backward scan: its own
    full read on every open, not shared with `journal`."""

    def test_the_docstring_no_longer_claims_a_shared_read(self):
        doc = " ".join(Store._unconfirmed_since_confirmation.__doc__.split())
        self.assertNotIn("already pays", doc)
        self.assertIn("one full read of the journal file per call", doc)
        self.assertIn("not shared with :meth:`journal`", doc)
        self.assertIn("every ordinary open of a live run", doc)
        self.assertIn("Nothing is cached", doc)

    def test_the_cost_is_as_documented(self):
        self.h.coordinator()
        with mock.patch.object(Path, "read_text", autospec=True, side_effect=Path.read_text) as read:
            self.store._unconfirmed_since_confirmation()
        self.assertEqual([call.args[0] for call in read.call_args_list], [self.store.journal_path])  # exactly one read of the journal


# -- F12 --------------------------------------------------------------------------------------------------------------------
class EvidenceNumberTests(LiveCase):
    """F12 (thread 4542174971): `issues/0`, `pull/0` and a number with leading zeros are not citations."""

    GOOD = f"https://github.com/{REPO}/pull/107#pullrequestreview-5"

    def problems(self, url: str) -> list[str]:
        document = Activation(**{**self.h.activation.__dict__, "evidence": {"lifecycle_smoke": url, "fresh_review": self.GOOD}})
        return [m for _, m in document.evidence_problems(self.h.h.policy)]

    def test_number_zero_and_leading_zeros_are_refused(self):
        for bad in ("issues/0#issuecomment-6", "pull/0#issuecomment-6", "pull/0#pullrequestreview-6", "issues/007#issuecomment-6", "pull/0107#pullrequestreview-6", "issues/00#issuecomment-6"):
            problems = self.problems(f"https://github.com/{REPO}/{bad}")
            self.assertEqual(len(problems), 1, bad)
            self.assertIn(f"is not a GitHub comment or review URL on {REPO}", problems[0], bad)

    def test_the_number_is_at_most_20_digits_like_the_id(self):
        self.assertEqual(len(self.problems(f"https://github.com/{REPO}/issues/{'1' * 21}#issuecomment-6")), 1)
        self.assertEqual(self.problems(f"https://github.com/{REPO}/issues/{'1' * 20}#issuecomment-6"), [])

    def test_a_positive_number_still_passes(self):
        for good in ("issues/7#issuecomment-6", "issues/106#issuecomment-6", "pull/10#pullrequestreview-6", "pull/100#issuecomment-06"):
            self.assertEqual(self.problems(f"https://github.com/{REPO}/{good}"), [], good)

    def test_a_creation_under_such_a_citation_refuses(self):
        self.h.path.write_text(self.h.path.read_text(encoding="utf-8").replace("pull/107#issuecomment-6706853226", "issues/0#issuecomment-6706853226"), encoding="utf-8")
        self.h.activation = activation_module.load_activation(self.h.path)
        refuses(self, self.h.coordinator, "activation-invalid", "activation-mismatch")
        self.assertIsNone(self.store.load_run())


# -- F13 --------------------------------------------------------------------------------------------------------------------
class StuckGitIsBoundedTests(unittest.TestCase):
    """F13 (thread 4542174977): a git that survives `kill()` no longer hangs the call: the timeout is
    raised after waiting at most 5 seconds for the killed child."""

    class Stuck:
        """A child in uninterruptible sleep: it never answers and does not die on SIGKILL."""

        def __init__(self, exits_after_kill: bool):
            self.exits_after_kill, self.calls = exits_after_kill, []
            self.stdout = self.stderr = mock.Mock()
            self.returncode = None

        def communicate(self, timeout=None):
            self.calls.append(("communicate", timeout))
            raise subprocess.TimeoutExpired("git", timeout)

        def kill(self):
            self.calls.append(("kill", None))

        def wait(self, timeout=None):
            self.calls.append(("wait", timeout))
            if timeout is None:
                raise AssertionError("an unbounded wait on a child that ignores SIGKILL never returns")
            if not self.exits_after_kill:
                raise subprocess.TimeoutExpired("git", timeout)
            return -9

    def run_stuck(self, exits_after_kill: bool) -> "StuckGitIsBoundedTests.Stuck":
        child = self.Stuck(exits_after_kill)
        with mock.patch.object(cli_module.subprocess, "Popen", return_value=child):
            with self.assertRaises(cli_module.WorkTreeUnknown) as ctx:
                cli_module._work_tree("/somewhere/owner")
        self.assertIn("hung mount", str(ctx.exception))
        self.assertIn("/somewhere/owner", str(ctx.exception))
        return child

    def test_a_child_that_survives_the_kill_still_raises(self):
        child = self.run_stuck(exits_after_kill=False)
        self.assertEqual(child.calls, [("communicate", cli_module.GIT_TIMEOUT_SECONDS), ("kill", None), ("wait", 5)])

    def test_a_child_that_dies_raises_too(self):
        child = self.run_stuck(exits_after_kill=True)
        self.assertEqual(child.calls, [("communicate", 30), ("kill", None), ("wait", 5)])
        self.assertEqual((cli_module.GIT_TIMEOUT_SECONDS, cli_module.GIT_KILL_WAIT_SECONDS), (30, 5))

    def test_an_interrupt_kills_and_reaps_the_child_then_propagates(self):
        child = self.Stuck(exits_after_kill=True)
        child.communicate = lambda timeout=None: (child.calls.append(("communicate", timeout)), (_ for _ in ()).throw(KeyboardInterrupt()))[1]
        with mock.patch.object(cli_module.subprocess, "Popen", return_value=child):
            with self.assertRaises(KeyboardInterrupt):
                cli_module._work_tree("/somewhere/owner")
        self.assertEqual(child.calls, [("communicate", 30), ("kill", None), ("wait", 5)])
        self.assertEqual((child.stdout.close.call_count, child.stderr.close.call_count), (2, 2))  # one mock stands for both pipes: each was closed

    def test_a_real_child_is_killed_and_the_call_returns(self):
        started = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            cli_module._git_answer(["sleep", "60"], timeout=0.2, env=dict(os.environ))
        self.assertLess(time.monotonic() - started, 0.2 + cli_module.GIT_KILL_WAIT_SECONDS)

    def test_an_answer_is_returned_as_before(self):
        out = cli_module._git_answer(["sh", "-c", "printf out; printf err >&2; exit 3"], timeout=30, env=dict(os.environ))
        self.assertEqual((out.returncode, out.stdout, out.stderr), (3, "out", "err"))

    def test_subprocess_run_is_no_longer_used_for_the_work_tree(self):
        with mock.patch.object(cli_module.subprocess, "run", side_effect=AssertionError("subprocess.run waits for a killed child without a limit")):
            self.assertIsNone(cli_module._work_tree("/"))


# -- F14 --------------------------------------------------------------------------------------------------------------------
class WaitUntilOnlyWhenClearableTests(LiveCase):
    """F14 (thread 4542174988): on a stop that is not clearable, with the clock behind the mark,
    `wait_until` is null: waiting unlocks nothing. Mutation: `wait_until if clearable else None`
    replaced by `wait_until`."""

    def setUp(self):
        super().setUp()
        self.c = claimed(self.h)
        regress(self, self.h, self.c)  # the clock reads 11:00, more than the tolerance behind the 12:00 mark

    def report(self, c=None) -> dict:
        return (c or self.c).status()["activation"]["clock_stop"]

    def test_a_clearable_stop_says_when(self):
        self.assertEqual(self.report()["wait_until"], "2026-11-07T11:55:00Z")

    def test_a_spent_clear(self):
        self.h.clock[0] = "2026-11-07T11:58:00Z"
        self.c.clear_clock_regression(clearance(self.h))
        regress(self, self.h, self.c)
        report = self.report()
        self.assertEqual((report["clearable"], report["clear_spent"]), (False, True))
        self.assertIsNone(report["wait_until"])

    def test_a_cancelled_run(self):
        self.c.cancel_run("owner stops")
        report = self.report()
        self.assertFalse(report["clearable"])
        self.assertIsNone(report["wait_until"])

    def test_policy_drift(self):
        from automation.tests.support import write_policy
        from automation.unattended.coordinator import Coordinator
        from automation.unattended.policy import load_policy
        folder = Path(self.h.h.tmpdir.name) / "drift"
        folder.mkdir()
        drifted = load_policy(write_policy(folder, allow='["OM-01.02"]', max_delegated_tasks="7"))
        reopened = Coordinator(self.h.h.fake, drifted, Store(self.h.h.state_dir, "run-live"), now=lambda: self.h.clock[0], live=True, activation=None)
        report = self.report(reopened)
        self.assertFalse(report["clearable"])
        self.assertIsNone(report["wait_until"])

    def test_a_spent_wall_clock(self):
        raw = json.loads(self.store.run_path.read_text(encoding="utf-8"))
        raw["started_at"] = "2026-11-07T00:00:00Z"  # LABELLED MUTATION: the budget judged on the 12:00 mark is spent
        self.store.run_path.write_text(json.dumps(raw), encoding="utf-8")
        report = self.report()
        self.assertFalse(report["clearable"])
        self.assertIsNone(report["wait_until"])

    def test_a_stop_past_the_recorded_window(self):
        raw = json.loads(self.store.run_path.read_text(encoding="utf-8"))
        raw["activation"]["expires_at"] = "2026-11-07T11:30:00Z"  # LABELLED MUTATION: an older run whose window ended before the mark
        self.store.run_path.write_text(json.dumps(raw), encoding="utf-8")
        self.h.clock[0] = "2026-11-07T11:20:00Z"
        report = self.report()
        self.assertFalse(report["clearable"])
        self.assertIsNone(report["wait_until"])


# -- F15 --------------------------------------------------------------------------------------------------------------------
class HighWaterFallsBackToValidatedAtTests(LiveCase):
    """F15 (thread 4542174998): a stop recorded before any later observation is judged and stamped
    on `validated_at`. Mutation: `_high_water_text` returning `self.run.last_observed_at`."""

    EARLY = "2026-11-07T09:00:00Z"  # an hour before the creation at 10:00

    def stopped_before_any_later_observation(self):
        c, auth = r5.ReconcileRevokedUnderClearableStopTests.repair(self)
        refuses(self, lambda: c.cancel(S, "owner stops the repair"), "authorization-unresolved")  # revokes it
        self.assertIsNone(self.store.load_run().last_observed_at)  # every operation so far read the creation moment
        self.h.clock[0] = self.EARLY
        refuses(self, lambda: c.rebase_revisions(S, "x"), "clock-regression")
        run = self.store.load_run()
        self.assertEqual((run.activation_stop["code"], run.last_observed_at, run.activation["validated_at"]), ("clock-regression", None, T0))
        return c, auth

    def test_status_reports_validated_at_as_the_mark_and_the_stop_is_clearable(self):
        c, _ = self.stopped_before_any_later_observation()
        report = c.status()["activation"]["clock_stop"]
        self.assertEqual(report["high_water"], T0)
        self.assertIs(report["clearable"], True)
        self.assertIsNone(report["reason"])
        self.assertEqual(report["wait_until"], "2026-11-07T09:55:00Z")

    def test_reconcile_is_stamped_with_validated_at(self):
        c, auth = self.stopped_before_any_later_observation()
        receipt, evidence = r5.ReconcileRevokedUnderClearableStopTests.evidence()
        state = c.reconcile_retained_execution(S, auth["id"], receipt, evidence, "r", "p")
        recorded = state.authorization(auth["id"])
        self.assertEqual((recorded["bound_at"], recorded["reconciliation"]["at"], recorded["reconciliation"]["observed_at"]), (T0, T0, self.EARLY))
        self.assertEqual(state.task_history[-1]["at"], T0)

    def test_the_other_state_stamps_use_validated_at_too(self):
        c, _ = self.stopped_before_any_later_observation()
        state = c.record_no_launch(S, {"authorization": self.store.load_story(S).unresolved_authorization()["id"], "reason": "never launched"})
        self.assertEqual(state.authorizations[-1]["resolved_at"], T0)


# -- F16 --------------------------------------------------------------------------------------------------------------------
class StampWithTheClockAheadOfTheMarkTests(LiveCase):
    """F16 (thread 4542175002): under a durable stop with the clock ahead of the frozen mark, the
    reconciliation is stamped with the clock. Mutation: `_at_least_high_water` returning
    `_utc_text(high_water)`."""

    AHEAD = "2026-11-07T12:30:00Z"  # past the 12:00 mark, inside expires_at 14:00

    def test_the_stamps_are_the_clock_and_the_backup_name_has_no_observation_part(self):
        c, auth = r5.ReconcileRevokedUnderClearableStopTests.repair(self)
        refuses(self, lambda: c.cancel(S, "owner stops the repair"), "authorization-unresolved")
        regress(self, self.h, c)
        self.h.clock[0] = "2026-11-07T11:58:00Z"
        c.clear_clock_regression(clearance(self.h))
        regress(self, self.h, c)  # a second stop: the one clear is spent, the stop is durable and the mark frozen
        self.h.clock[0] = self.AHEAD
        with c.operation():
            c._reload_run()
            self.assertFalse(c._clearable_clock_stop())
        receipt, evidence = r5.ReconcileRevokedUnderClearableStopTests.evidence()
        state = c.reconcile_retained_execution(S, auth["id"], receipt, evidence, "r", "p")
        self.assertEqual(self.store.load_run().last_observed_at, MARK)  # frozen under the stop
        recorded = state.authorization(auth["id"])
        self.assertEqual(recorded["bound_at"], self.AHEAD)
        self.assertEqual(recorded["reconciliation"]["at"], self.AHEAD)
        self.assertEqual(recorded["reconciliation"]["observed_at"], self.AHEAD)
        self.assertEqual(state.task_history[-1]["at"], self.AHEAD)
        line = next(e for e in self.store.read_journal() if e["event"] == "retained-execution-reconciled")
        self.assertNotIn("-obs", line["detail"]["backup"])
        self.assertIn("2026-11-07T123000Z", line["detail"]["backup"])


# -- F17 --------------------------------------------------------------------------------------------------------------------
class ObservedAtOnlyUnderAClockStopTests(LiveCase):
    """F17 (thread 4542175007): a reconciliation on a cancelled run without a clock stop records no
    `observed_at`. Mutation: `if under_clock_stop:` replaced by `if True:`."""

    def test_a_cancelled_run_without_a_clock_stop_records_no_observed_at(self):
        c, auth = r5.ReconcileRevokedUnderClearableStopTests.repair(self)
        refuses(self, lambda: c.cancel(S, "owner stops the repair"), "authorization-unresolved")
        c.cancel_run("owner stops the run")
        self.assertIsNone(stop_of(self.store))
        self.h.clock[0] = "2026-11-07T10:30:00Z"
        receipt, evidence = r5.ReconcileRevokedUnderClearableStopTests.evidence()
        state = c.reconcile_retained_execution(S, auth["id"], receipt, evidence, "r", "p")
        reconciliation = state.authorization(auth["id"])["reconciliation"]
        self.assertNotIn("observed_at", reconciliation)
        self.assertEqual((reconciliation["at"], state.authorization(auth["id"])["bound_at"]), ("2026-11-07T10:30:00Z", "2026-11-07T10:30:00Z"))

    def test_under_a_clock_stop_it_is_recorded(self):
        c, auth = r5.ReconcileRevokedUnderClearableStopTests.repair(self)
        refuses(self, lambda: c.cancel(S, "owner stops the repair"), "authorization-unresolved")
        regress(self, self.h, c)
        receipt, evidence = r5.ReconcileRevokedUnderClearableStopTests.evidence()
        state = c.reconcile_retained_execution(S, auth["id"], receipt, evidence, "r", "p")
        self.assertEqual(state.authorization(auth["id"])["reconciliation"]["observed_at"], BEHIND)


# -- the documentation ------------------------------------------------------------------------------------------------------
class DocumentedTests(unittest.TestCase):
    """The guide describes every changed event detail and report field, and the README names this file."""

    def test_the_guide_names_the_changed_details_and_fields(self):
        text = DOCS.read_text(encoding="utf-8")
        for needle in ("`field`", "`consequence`", "`presented_current`", "`clear_requires`", "`recovered: true`", "recorded directory cannot be examined", "`issues/0`", "5 seconds"):
            self.assertIn(needle, text, needle)
        self.assertNotIn("an `OSError` without an errno told apart by its `strerror`: the message names", text)

    def test_the_readme_names_this_file(self):
        self.assertIn("tests/test_pr114_round7_findings.py", README.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
