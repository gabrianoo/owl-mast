"""Regressions for PR #114 round 7: review 5864099379 (17 threads, tracked in issue #118). One class
per finding, F1 to F17 in the order of the issue, with the review thread id in the docstring; each
test is named after the behaviour it pins. F14 to F17 are the assertions the review found missing:
each fails under the mutation its finding names. Every scenario runs on the fixture transport marked
live with temporary state and an injected clock; no real GitHub call and no real task is ever made,
and no test writes to the real use ledger under the home directory."""

from __future__ import annotations

import contextlib
import errno
import json
import os
import subprocess
import time
import unittest
from pathlib import Path
from unittest import mock

from automation.tests import test_pr114_round5_findings as r5
from automation.tests.support import IMPLEMENTER, REVIEW_BRANCH, REVIEW_WORKTREE, REVIEWER, ok_worktree, passing_runner
from automation.tests.test_activation import S, T0
from automation.tests.test_enabling_repair_1 import claimed, refuses
from automation.tests.test_pr108_review_findings import review_authorized
from automation.tests.test_pr114_review_findings import LiveCase, clearance, regress
from automation.tests.test_pr114_round3_findings import record
from automation.tests.test_pr114_round4_findings import stop_of
from automation.tests.test_pr115_review_findings import EARLY, arm_failure_after_claim
from automation.unattended import activation as activation_module
from automation.unattended import cli as cli_module
from automation.unattended import state as state_module
from automation.unattended.activation import Activation, abort_activation_use, activation_use, confirm_activation_use, ledger_path, record_activation_use, run_json_presence, use_refusal
from automation.unattended.errors import Conflict, Outage, Refused
from automation.unattended.github import Comment, PullRequestRecord, render_marker
from automation.unattended.state import Store

REPO = "gabrianoo/owl-mast"
ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs" / "unattended-execution.md"
README = ROOT / "automation" / "README.md"
MARK = "2026-11-07T12:00:00Z"  # the high-water mark `regress` leaves; the clock then reads 11:00
BEHIND = "2026-11-07T11:00:00Z"
INSIDE = "2026-11-07T11:57:00Z"  # behind the mark, inside the 5-minute tolerance: no stop is recorded


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


@contextlib.contextmanager
def stat_raising(errors: dict):
    """`os.stat` that raises ``errors[path]`` for exactly the paths it names and nothing under them;
    yields the list of the paths it raised for, in order."""
    original = os.stat
    by_path = {os.fspath(path): error for path, error in errors.items()}
    raised = []

    def stat(path, *args, **kwargs):
        text = os.fspath(path) if isinstance(path, (str, os.PathLike)) else None
        if text in by_path:
            raised.append(text)
            raise by_path[text]
        return original(path, *args, **kwargs)

    with mock.patch.object(activation_module.os, "stat", stat):
        yield raised


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

    def line(self, state_dir: str | None = None) -> dict:
        set_ledger(self.h, state="pending", state_dir=str(self.recorded) if state_dir is None else state_dir)
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
        self.assert_cannot_be_examined(line, errno.EACCES, "Permission denied", "PermissionError: Permission denied", permission=True)

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

    def test_a_run_directory_that_cannot_be_searched_is_unknown_though_the_recorded_directory_answers(self):
        """PR #176 R5-1, the first stat (`<recorded>/<run_id>/run.json`). The mutation it pins: its
        `except (OSError, ValueError)` handler turned into `pass`, so the error falls through to the
        stat of the recorded directory, which answers, and the line reads "exists without the run"."""
        self.recorded.mkdir()
        error = PermissionError(13, "Permission denied")
        with stat_refusing(self.recorded / "run-live", error):
            os.stat(self.recorded)  # the recorded directory itself answers: only the first stat is refused
            with self.assertRaises(PermissionError):
                os.stat(self.recorded / "run-live" / "run.json")
            found, problem = activation_module._recorded_run(str(self.recorded), "run-live")
            line = self.line()
        self.assertEqual(found, "unknown")
        self.assertIs(problem, error)
        self.assert_cannot_be_examined(line, errno.EACCES, "Permission denied", "PermissionError: Permission denied", permission=True)

    def assert_cannot_be_examined(self, line: dict, errno: int | None, strerror: str | None, reason: str, *, permission: bool) -> None:
        """PR #176 R6-2. The advice names both paths the probe stats, the recorded directory and the
        run directory under it (either may be the one refused, or a directory above them), and
        carries the reason of the error: `<type>: <text>`. The mutations it pins: the run directory
        dropped from the advice, and the reason cut down to the type alone.

        PR #176 R7-1. The remedy follows the error: search permission along the path for a
        permission refusal (`permission=True`: `EACCES` / `EPERM`) and only for one; any other
        `OSError` is told to clear that error and is not sent to the permissions. The mutation it
        pins: the `PermissionError` test dropped, so every `OSError` gets the search-permission
        remedy."""
        self.assertEqual((line["field"], line["errno"], line["strerror"]), ("recorded directory cannot be examined", errno, strerror))
        self.assertIn("cannot be examined", line["error"])
        paths = f"{str(self.recorded)!r} and the run directory 'run-live' under it"
        if permission:
            self.assertIn(f"make {paths} reachable (every directory on the path searchable) and open the run again", line["error"])
        else:
            self.assertIn(f"clear that error on the path to {paths} and open the run again", line["error"])
            for other in ("searchable", "reachable", "permission"):
                self.assertNotIn(other, line["error"])
        self.assertIn(f"cannot be examined ({reason}), so whether the run is still there is not known", line["error"])
        for other in ("is spent", "holds no run", "no longer exists", "damaged"):
            self.assertNotIn(other, line["error"])
        self.assertIn("cannot be settled from here", line["consequence"])
        self.assertIn("is not known", line["consequence"])
        self.assertNotIn("every later open retries", line["consequence"])

    def test_an_operation_not_permitted_gets_the_search_permission_remedy_too(self):
        """PR #176 R7-1: `EPERM` is a permission refusal like `EACCES`."""
        with stat_refusing(self.recorded, PermissionError(errno.EPERM, "Operation not permitted")):
            line = self.line()
        self.assert_cannot_be_examined(line, errno.EPERM, "Operation not permitted", "PermissionError: Operation not permitted", permission=True)

    def test_an_error_without_an_errno_is_not_sent_to_the_permissions(self):
        """PR #176 R7-1 review. An `OSError` that carries neither errno nor strerror: the reason
        falls back to the text of the error, and nothing says it is a permission refusal. The
        mutation it pins: `{strerror or problem}` cut down to `{strerror}`, which leaves
        `(OSError: None)`."""
        with stat_refusing(self.recorded, OSError("an odd failure")):
            line = self.line()
        self.assert_cannot_be_examined(line, None, None, "OSError: an odd failure", permission=False)

    def test_a_symlink_loop_is_not_sent_to_the_permissions(self):
        """PR #176 R7-1 review: an errno that is neither a permission refusal nor a disk error."""
        with stat_refusing(self.recorded, OSError(errno.ELOOP, "Too many levels of symbolic links")):
            line = self.line()
        self.assert_cannot_be_examined(line, errno.ELOOP, "Too many levels of symbolic links", "OSError: Too many levels of symbolic links", permission=False)

    def test_a_recorded_directory_that_cannot_be_examined_is_unknown_though_the_run_is_absent(self):
        """PR #176 R5-1, the second stat (`<recorded>`). The mutation it pins: its handlers folded
        into `except (OSError, ValueError): return "gone", None`, so an error that is not absence
        reads as "gone" once the first stat has answered that `run.json` is absent."""
        error = OSError(5, "Input/output error")
        with stat_raising({self.recorded: error}) as raised:  # run.json is absent on the file system itself: the first stat answers ENOENT
            found, problem = activation_module._recorded_run(str(self.recorded), "run-live")
            self.assertEqual(raised, [str(self.recorded)])  # the second stat, and only it, was refused
            line = self.line()
        self.assertEqual(found, "unknown")
        self.assertIs(problem, error)
        self.assert_cannot_be_examined(line, errno.EIO, "Input/output error", "OSError: Input/output error", permission=False)

    def test_a_value_the_file_system_cannot_take_is_unknown_at_either_stat(self):
        """PR #176 R5-1 review. The mutation it pins: `except (OSError, ValueError)` narrowed to
        `except OSError` at the first stat, or at the second (the `ValueError` then escapes)."""
        found, problem = activation_module._recorded_run(str(self.recorded) + "\0x", "run-live")  # absolute, so the first stat is reached
        self.assertEqual((found, type(problem)), ("unknown", ValueError))
        error = ValueError("embedded null byte")
        with stat_raising({self.recorded: error}) as raised:
            found, problem = activation_module._recorded_run(str(self.recorded), "run-live")
        self.assertEqual((found, raised), ("unknown", [str(self.recorded)]))
        self.assertIs(problem, error)

    def test_a_recorded_path_under_a_file_is_gone(self):
        """PR #176 R5-1 review. The mutation it pins: `NotADirectoryError` dropped from the second
        stat's absence handler, so a recorded path whose parent is a file reads as `unknown`."""
        parent = Path(self.h.h.tmpdir.name) / "a-file"
        parent.write_text("a file", encoding="utf-8")
        with self.assertRaises(NotADirectoryError):
            os.stat(parent / "created-under")
        self.assertEqual(activation_module._recorded_run(str(parent / "created-under"), "run-live"), ("gone", None))

    def test_a_run_directory_without_run_json_holds_no_run(self):
        """PR #176 R6-1, the `run` / `no-run` boundary. The mutation it pins: the first stat probing
        the run directory, `<recorded>/<run_id>`, instead of `<recorded>/<run_id>/run.json`, so an
        empty or partial run directory (the run was moved out of it) gets the advice to open the
        run through a directory that does not hold it."""
        (self.recorded / "run-live").mkdir(parents=True)
        self.assertEqual(activation_module._recorded_run(str(self.recorded), "run-live"), ("no-run", None))  # empty
        (self.recorded / "run-live" / "journal.jsonl").write_text("", encoding="utf-8")
        self.assertEqual(activation_module._recorded_run(str(self.recorded), "run-live"), ("no-run", None))  # partial
        line = self.line()
        self.assertEqual(line["field"], "recorded path exists without the run")
        self.assertIn("holds no run 'run-live'", line["error"])
        self.assertIn("is spent", line["error"])
        self.assertNotIn("open the run through the directory it was created under", line["error"])
        self.assertNotIn("an open of the run through the recorded directory confirms it", line["consequence"])

    def test_a_recorded_path_that_is_not_absolute_says_so_in_the_journaled_line(self):
        """PR #176 R6-2 and R7-1: a recorded path that is not absolute is a damaged record, and the
        line says what is wrong with the path. The mutation it pins: `({type(problem).__name__}:
        {problem})` cut down to the type, which leaves `(ValueError)`."""
        line = self.line(state_dir="rel")
        self.assert_names_no_usable_state_directory(line, "ValueError: the recorded state directory 'rel' is not an absolute path")

    def test_a_recorded_path_the_file_system_cannot_take_is_a_damaged_record_in_the_journaled_line(self):
        """PR #176 R7-1, the other value that is no usable path: absolute, so the first stat is
        reached and raises the `ValueError` itself."""
        recorded = str(self.recorded) + "\0x"
        with self.assertRaises(ValueError) as refused:  # the text differs between Python versions: take it from the stat itself
            os.stat(os.path.join(recorded, "run-live", "run.json"))
        line = self.line(state_dir=recorded)
        self.assert_names_no_usable_state_directory(line, f"ValueError: {refused.exception}")

    def mismatch_lines(self) -> list[dict]:
        return [d for d in unconfirmed(self.store) if d["type"] == "state-dir-mismatch"]

    def test_a_relative_recorded_path_that_lines_up_with_the_current_directory_is_not_confirmed(self):
        """PR #176 R8-1 (#183): the damaged-record line says that moving the run does not settle the
        record, so the match must not depend on the current directory. Here the current directory
        is the parent of the state directory, so its bare name, resolved against it, is the state
        directory itself. The mutation it pins: the `os.path.isabs(recorded)` guard removed from
        `_same_state_dir`, which commits the record and journals no line."""
        real = Path(os.path.realpath(self.h.h.state_dir))
        with contextlib.chdir(real.parent):
            self.assertTrue(os.path.samefile(real.name, real))  # the precondition: resolved against the cwd, the relative name would match
            set_ledger(self.h, state="pending", state_dir=real.name)
            self.h.coordinator(activation=None)
            self.assertEqual((record(self.h)["state"], record(self.h)["state_dir"]), ("pending", real.name))
            lines = self.mismatch_lines()
            self.assertEqual(len(lines), 1)
            self.assert_names_no_usable_state_directory(lines[0], f"ValueError: the recorded state directory {real.name!r} is not an absolute path")

    def test_no_relative_spelling_of_the_state_directory_is_the_same_run(self):
        """PR #176 R8-1 (#183): every relative spelling that the current directory would resolve to
        the state directory, from its parent and from inside it. A relative `--state-dir` is still
        resolved: only the recorded value must be absolute."""
        real = Path(os.path.realpath(self.h.h.state_dir))
        cases = [(real.parent, s) for s in (real.name, os.path.join(".", real.name), os.path.join(real.name, ""), os.path.join("..", real.parent.name, real.name))]
        cases += [(real, s) for s in (".", "", os.path.join("..", real.name))]
        for cwd, relative in cases:
            with self.subTest(cwd=str(cwd), relative=relative), contextlib.chdir(cwd):
                if relative:
                    self.assertTrue(os.path.samefile(relative, real))  # the precondition
                for state in ("pending", "aborted"):
                    used = {"run_id": "run-live", "state_dir": relative, "state": state}
                    self.assertFalse(activation_module._same_run(used, real, "run-live"))
                    self.assertTrue(activation_module._same_run_id_other_state_dir(used, real, "run-live"))
                    self.assertFalse(activation_module._retryable_creation(used, real, "run-live"))
        with contextlib.chdir(real.parent):
            self.assertTrue(activation_module._same_run({"run_id": "run-live", "state_dir": str(real), "state": "pending"}, real.name, "run-live"))

    def test_an_aborted_record_with_a_relative_path_is_a_use_and_is_never_retried(self):
        """PR #176 R8-1 (#183): "until then it is a use: a later creation from this document refuses
        activation-used" holds from every current directory, in the preflight and in the creation,
        and the refusal does not name a retry that no directory accepts. The mutation it pins: the
        guard removed, so the preflight reports nothing and the creation is retried (the record
        goes back to `pending`)."""
        real = Path(os.path.realpath(self.h.h.state_dir))
        ledger = ledger_path(self.h.activation.digest, self.h.activation.path)
        with contextlib.chdir(real.parent):
            set_ledger(self.h, state="aborted", state_dir=real.name)
            preflight = [m for code, m in self.h.activation.creation_problems(self.h.h.policy, "run-live", T0, state_dir=real) if code == "activation-used"]
            refused = refuses(self, lambda: record_activation_use(self.h.activation, real, "run-live", T0), "activation-used")
            self.assertEqual(record(self.h)["state"], "aborted")
        self.assertEqual(len(preflight), 1)
        for message in (preflight[0], str(refused)):
            self.assertIn(f"the record names no usable state directory ({real.name!r} is not an absolute path): it is damaged, so that creation cannot be retried", message)
            self.assertIn(f"use ledger {ledger}: aborted", message)
            self.assertIn("inspect or restore that file", message)
            for other in ("only that same creation may be retried", "--state-dir"):
                self.assertNotIn(other, message)

    def test_an_aborted_record_with_an_absolute_path_still_names_the_retry(self):
        """The other side of the R8-1 refusal: a record that names an absolute directory keeps the
        retry advice, also when it is refused for another run id."""
        set_ledger(self.h, state="aborted")
        message = use_refusal(record(self.h), "/l/x.json")
        self.assertIn(f"only that same creation may be retried (--run-id run-live --state-dir {record(self.h)['state_dir']})", message)
        self.assertNotIn("damaged", message)

    def assert_names_no_usable_state_directory(self, line: dict, reason: str) -> None:
        """PR #176 R7-1. A recorded state directory that is not a usable path means the record is
        damaged: no permission change and no move of the run settles it, and that is known. Until
        the ledger file is restored the record is a use (PR #176 R8-1). The
        mutation it pins: the `not isinstance(problem, OSError)` branch removed, so the line falls
        back to the "cannot be examined ... is not known" advice and a remedy on the path."""
        self.assertEqual((line["field"], line["errno"], line["strerror"]), ("recorded directory cannot be examined", None, None))
        ledger = str(ledger_path(self.h.activation.digest, self.h.activation.path))
        self.assertIn(f"the record names no usable state directory ({reason}): it is damaged, and neither a permission change nor moving the run settles it; "
                      f"inspect or restore the ledger file {ledger!r} (its state_dir is the absolute path of the directory the run was created under)", line["error"])
        for other in ("reachable", "searchable", "clear that error", "open the run again", "is not known", "cannot be examined (", "is spent"):
            self.assertNotIn(other, line["error"])
        self.assertIn("the use ledger record is damaged", line["consequence"])
        self.assertIn("not settled until the ledger file is restored; until then it is a use: a later creation from this document refuses activation-used", line["consequence"])
        for other in ("is not known", "from here", "every later open retries"):
            self.assertNotIn(other, line["consequence"])

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
        self.assertEqual([i.created_at for i in cleanup], [MARK])  # PR #176 R1-2: never the Store's wall clock, which reads earlier than `blocked.at` saved with it

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

    def inside_the_tolerance(self):
        """A live run with no stop whose clock reads 3 minutes behind its high-water mark."""
        c = self.h.coordinator()
        self.h.clock[0] = MARK
        c.status()
        self.h.clock[0] = INSIDE
        return c

    def approved(self, c):
        """Drive the advancing operations up to an approved review, all at `INSIDE`."""
        c.reserve(S, self.h.h.snapshot, "base")
        c.bind_receipt(S, IMPLEMENTER, str(self.h.h.worktree), "t3/om-01-02", ok_worktree)
        c.record_head(S, self.h.h.sha, self.h.terminal())
        c.run_checks(S, self.h.h.sha, str(self.h.h.worktree), passing_runner)
        c.authorize_review(S, self.h.h.sha)
        c.bind_receipt(S, REVIEWER, REVIEW_WORKTREE, REVIEW_BRANCH, ok_worktree)
        return c.record_review(S, self.h.h.sha, "approved", "report.md", self.h.terminal())

    def test_the_advancing_operations_are_floored_without_a_stop(self):
        """PR #176 R1-3 (thread PRRT_kwDOVjxExc63TXCx): the advancing operations refuse under a
        recorded stop, so their floor applies with no stop and the clock inside the tolerance behind
        the mark. Mutation: the stamp of `issued_at`, `reserved_at`, `checks[].at`, `reviews[].at`,
        `proposal.at` or an intent's `created_at` / `completed_at` back to `self.now()`. The
        `blocked.at` of the reserve and resume conflicts is in `ConflictStampsWithoutAStopTests`."""
        c = self.inside_the_tolerance()
        state = c.reserve(S, self.h.h.snapshot, "base")
        self.assertEqual(state.claim["reserved_at"], MARK)
        self.assertEqual((state.authorizations[-1]["purpose"], state.authorizations[-1]["issued_at"]), ("implementation", MARK))
        self.assertEqual(state.authorizations[-1]["issued_observed_at"], INSIDE)  # floored, so what the clock read is kept
        claim = next(i for i in state.intents if i.kind == "claim")
        self.assertEqual((claim.created_at, claim.completed_at), (MARK, MARK))
        c.bind_receipt(S, IMPLEMENTER, str(self.h.h.worktree), "t3/om-01-02", ok_worktree)
        c.record_head(S, self.h.h.sha, self.h.terminal())
        state = c.run_checks(S, self.h.h.sha, str(self.h.h.worktree), passing_runner)
        self.assertEqual(state.checks[-1]["at"], MARK)
        state = c.authorize_review(S, self.h.h.sha)
        self.assertEqual((state.authorizations[-1]["purpose"], state.authorizations[-1]["issued_at"]), ("review", MARK))
        c.bind_receipt(S, REVIEWER, REVIEW_WORKTREE, REVIEW_BRANCH, ok_worktree)
        state = c.record_review(S, self.h.h.sha, "approved", "report.md", self.h.terminal())
        self.assertEqual(state.reviews[-1]["at"], MARK)
        self.h.h.fake.pull_requests[7] = PullRequestRecord(7, "OPEN", self.h.h.sha, False, (), "SUCCESS")
        state = c.propose_evidence(S, self.h.h.sha, 7, [], "s")
        self.assertEqual(state.proposal["at"], MARK)
        proposal = next(i for i in state.intents if i.kind == "proposal")
        self.assertEqual((proposal.created_at, proposal.completed_at), (MARK, MARK))
        self.assertIsNone(stop_of(self.store))  # the floor was never a stop's doing
        self.assertEqual(self.h.clock[0], INSIDE)

    def test_a_review_regression_on_github_is_floored_without_a_stop(self):
        """PR #176 R1-3: the review a GitHub objection records is stamped like a local one."""
        c = self.inside_the_tolerance()
        self.approved(c)
        objection = {"state": "CHANGES_REQUESTED", "commit": self.h.h.sha, "author": "A", "submitted_at": "1"}
        self.h.h.fake.pull_requests[7] = PullRequestRecord(7, "OPEN", self.h.h.sha, False, (objection,), "SUCCESS")
        with self.assertRaises(Refused) as ctx:
            c.propose_evidence(S, self.h.h.sha, 7, [], "s")
        self.assertIn("outstanding CHANGES_REQUESTED from ['A']", str(ctx.exception))
        review = self.store.load_story(S).reviews[-1]
        self.assertEqual((review["regression"], review["at"]), (True, MARK))

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

    def test_git_is_given_the_sanitized_environment_and_no_stdin(self):
        """PR #176 R1-4 (thread PRRT_kwDOVjxExc63TXC4): `_git_answer` hands the child the
        environment `_work_tree` built, and no stdin. Mutation: `env=env` or `stdin=DEVNULL`
        dropped from the `Popen` call."""
        child = mock.Mock(returncode=128)
        child.communicate.return_value = ("", "fatal: not a git repository (or any of the parent directories): .git\n")
        inherited = {"GIT_DIR": "/elsewhere/.git", "GIT_WORK_TREE": "/elsewhere", "LC_ALL": "de_DE.UTF-8", "LANGUAGE": "de", "PATH": os.environ.get("PATH", "")}
        with mock.patch.dict(os.environ, inherited), mock.patch.object(cli_module.subprocess, "Popen", return_value=child) as popen:
            self.assertIsNone(cli_module._work_tree("/x"))
        kwargs = popen.call_args.kwargs
        env = kwargs["env"]
        self.assertEqual((env["LC_ALL"], env["LANGUAGE"], env["GIT_DISCOVERY_ACROSS_FILESYSTEM"]), ("C", "", "1"))
        self.assertEqual([k for k in env if k.startswith("GIT_")], ["GIT_DISCOVERY_ACROSS_FILESYSTEM"])
        self.assertEqual(env["PATH"], inherited["PATH"])  # the rest of the caller's environment is kept
        self.assertIs(kwargs["stdin"], subprocess.DEVNULL)
        self.assertEqual(popen.call_args.args[0], ["git", "-C", "/x", "rev-parse", "--show-toplevel"])

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
    `observed_at` while its stamp is the clock. Mutation: the condition replaced by `if True:`."""

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

    def test_without_a_stop_a_floored_reconciliation_never_sorts_before_the_revocation(self):
        """PR #176 R1-1 (thread PRRT_kwDOVjxExc63TXCh): with no stop and the clock inside the
        tolerance behind the mark, the reconciliation is floored like every other stamp, so it never
        follows a floored `revoked_at` with an earlier time; the raw reading is kept beside it.
        Mutation: `stamp = observed_at` when no clock stop is recorded."""
        c, auth = r5.ReconcileRevokedUnderClearableStopTests.repair(self)
        self.h.clock[0] = MARK
        c.status()
        self.h.clock[0] = INSIDE
        refuses(self, lambda: c.cancel(S, "owner stops the repair"), "authorization-unresolved")  # revoked: floored at the mark
        c.cancel_run("owner stops the run")
        self.assertIsNone(stop_of(self.store))
        receipt, evidence = r5.ReconcileRevokedUnderClearableStopTests.evidence()
        state = c.reconcile_retained_execution(S, auth["id"], receipt, evidence, "r", "p")
        recorded = state.authorization(auth["id"])
        self.assertEqual((recorded["revoked_at"], recorded["bound_at"], recorded["reconciliation"]["at"]), (MARK, MARK, MARK))
        self.assertGreaterEqual(recorded["reconciliation"]["at"], recorded["revoked_at"])
        self.assertEqual(recorded["reconciliation"]["observed_at"], INSIDE)  # floored, so what the clock read is kept
        stamps = [entry["at"] for entry in state.task_history]
        self.assertEqual((stamps, stamps[-1]), (sorted(stamps), MARK))
        line = next(e for e in self.store.read_journal() if e["event"] == "retained-execution-reconciled")
        self.assertIn("-obs2026-11-07T115700Z", line["detail"]["backup"])
        self.assertIsNone(stop_of(self.store))

    def test_a_run_started_on_the_real_clock_after_a_floored_issue_is_reconciled(self):
        """A repair authorized with the clock inside the tolerance has `issued_at` at the mark; its
        task starts on the real clock, before the mark. The reconciliation compares `startedAt`
        with what the clock read at issue, so the genuine run is not refused
        `run-precedes-authorization`, and a run that started before that reading still is.

        PR #176 R2-1: a `startedAt` in [`issued_observed_at`, `issued_at`) is accepted by design.
        The check cannot tell a run that started there after the issue from one that started there
        before it on a correct clock (up to the tolerance before the mark). The lower edge of the
        window is pinned on both sides: the reading itself is accepted, one second before it is refused.
        PR #176 R2-2: the refusal keeps `issued_at` as recorded and names the reading it compared.
        PR #176 R3-2 (a pin of behaviour round 2 added): `issued_at` is validated also when the reading is compared, because it is reported.
        Mutations: `issued_at=<the compared value>` back in the detail; the label of the compared
        field back to `authorization.issued_at`; `<` to `<=` in the comparison; `issued_at` parsed
        only when the authorization has no reading."""
        c = review_authorized(self.h)
        c.bind_receipt(S, REVIEWER, REVIEW_WORKTREE, REVIEW_BRANCH, ok_worktree)
        c.record_review(S, self.h.h.sha, "changes-requested", "r.md", self.h.terminal())
        self.h.clock[0] = MARK
        c.status()
        self.h.clock[0] = INSIDE
        auth = c.authorize_repair(S).unresolved_authorization()
        self.assertEqual((auth["issued_at"], auth["issued_observed_at"]), (MARK, INSIDE))
        refuses(self, lambda: c.cancel(S, "owner stops the repair"), "authorization-unresolved")
        c.cancel_run("owner stops the run")
        receipt, evidence = r5.ReconcileRevokedUnderClearableStopTests.evidence()
        earlier = {**receipt, "startedAt": "2026-11-07T11:56:59Z"}  # before the clock read 11:57 at issue
        exc = refuses(self, lambda: c.reconcile_retained_execution(S, auth["id"], earlier, evidence, "r", "p"), "run-precedes-authorization")
        self.assertEqual((exc.detail["issued_at"], exc.detail["issued_observed_at"], exc.detail["compared_with"]), (MARK, INSIDE, "issued_observed_at"))
        self.assertIn(f"issued at {MARK} (the clock read {INSIDE})", str(exc))
        broken = self.store.load_story(S)
        broken.authorization(auth["id"])["issued_observed_at"] = "not-a-time"
        self.store.save_story(broken)
        exc = refuses(self, lambda: c.reconcile_retained_execution(S, auth["id"], receipt, evidence, "r", "p"), "correlation-missing")
        self.assertIn("authorization.issued_observed_at", str(exc))  # the field that is malformed, not `issued_at`
        broken.authorization(auth["id"])["issued_observed_at"] = INSIDE
        broken.authorization(auth["id"])["issued_at"] = "not-a-time"  # the reading is intact and is what the check compares
        self.store.save_story(broken)
        exc = refuses(self, lambda: c.reconcile_retained_execution(S, auth["id"], receipt, evidence, "r", "p"), "correlation-missing")
        self.assertIn("authorization.issued_at", str(exc))
        self.assertEqual(self.store.load_story(S).authorization(auth["id"])["status"], "revoked")  # nothing was consumed
        broken.authorization(auth["id"])["issued_at"] = MARK
        self.store.save_story(broken)
        genuine = {**receipt, "startedAt": INSIDE}  # the lower edge of the accepted window [issued_observed_at, issued_at): at the reading, before the mark
        state = c.reconcile_retained_execution(S, auth["id"], genuine, evidence, "r", "p")
        self.assertEqual(state.authorization(auth["id"])["status"], "consumed")

    def repair_issued_after_a_step_back(self, reading: str):
        """A coordinator ready for `authorize-repair` with the clock at the mark, and a patch under
        which the clock reads ``reading`` after the gate and before the authorization is issued
        (a host resume or an NTP step between the two readings)."""
        c = review_authorized(self.h)
        c.bind_receipt(S, REVIEWER, REVIEW_WORKTREE, REVIEW_BRANCH, ok_worktree)
        c.record_review(S, self.h.h.sha, "changes-requested", "r.md", self.h.terminal())
        self.h.clock[0] = MARK
        check = c._require_no_obligation  # runs after the gate, before the authorization is issued

        def step_back(*args, **kwargs):
            self.h.clock[0] = reading
            return check(*args, **kwargs)

        return c, mock.patch.object(c, "_require_no_obligation", step_back)

    def test_a_reading_past_the_tolerance_after_the_gate_is_a_recorded_stop_and_issues_nothing(self):
        """PR #176 R3-1 (thread PRRT_kwDOVjxExc63UHV6): the reading `_authorize` keeps as
        `issued_observed_at` is taken after the operation's gated observation. Read further behind
        the mark than the tolerance, it is a clock regression like the gate's: recorded durably,
        nothing issued, so the window the reconciliation accepts never exceeds the tolerance.
        Mutations: the `_observe_stop(operation, at=observed_at)` call removed from `_authorize`
        (an authorization is issued with a reading an hour behind); `at` ignored by `_stop_candidate`."""
        c, stepped = self.repair_issued_after_a_step_back("2026-11-07T11:54:59Z")  # one second past the 5-minute tolerance
        before = self.store.load_story(S)
        with stepped:
            exc = refuses(self, lambda: c.authorize_repair(S), "clock-regression")
        stop = stop_of(self.store)
        self.assertEqual((stop["code"], stop["observed_at"], stop["operation"]), ("clock-regression", "2026-11-07T11:54:59Z", "authorize-repair"))
        self.assertEqual(exc.detail["stop"], stop)
        self.assertEqual(self.events().count("activation-stopped"), 1)
        after = self.store.load_story(S)
        self.assertEqual((after.authorizations, after.repair_rounds, after.phase), (before.authorizations, before.repair_rounds, before.phase))
        self.assertEqual(self.store.load_run().last_observed_at, MARK)
        self.h.clock[0] = MARK  # the clock is back at the mark: only the recorded stop refuses now
        exc = refuses(self, lambda: c.authorize_repair(S), "clock-regression")
        self.assertEqual((exc.detail["stop"], stop_of(self.store)), (stop, stop))

    def test_a_reading_at_the_tolerance_after_the_gate_is_issued_with_that_reading(self):
        """The other side of the edge: exactly the tolerance behind the mark is no stop, here as at the gate."""
        c, stepped = self.repair_issued_after_a_step_back("2026-11-07T11:55:00Z")
        with stepped:
            auth = c.authorize_repair(S).unresolved_authorization()
        self.assertEqual((auth["issued_at"], auth["issued_observed_at"]), (MARK, "2026-11-07T11:55:00Z"))
        self.assertIsNone(stop_of(self.store))
        self.assertEqual((self.store.load_run().last_observed_at, self.events().count("activation-stopped")), (MARK, 0))

    def test_a_review_authorization_judges_its_reading_the_same_way(self):
        """`authorize-review` reads the worktree between the gate and the issue; the stop names that command."""
        c = claimed(self.h)
        c.record_head(S, self.h.h.sha, self.h.terminal())
        c.run_checks(S, self.h.h.sha, str(self.h.h.worktree), passing_runner)
        self.h.clock[0] = MARK
        verify = c._verify_worktree

        def step_back(*args, **kwargs):
            self.h.clock[0] = "2026-11-07T11:00:00Z"
            return verify(*args, **kwargs)

        with mock.patch.object(c, "_verify_worktree", step_back):
            refuses(self, lambda: c.authorize_review(S, self.h.h.sha), "clock-regression")
        state = self.store.load_story(S)
        self.assertEqual((stop_of(self.store)["operation"], state.phase, state.unresolved_authorization()), ("authorize-review", "checks-passed", None))

    def test_a_reservation_judges_its_reading_the_same_way_and_leaves_nothing_behind(self):
        """PR #176 R4-1 (thread PRRT_kwDOVjxExc63UeAe): `reserve` reads GitHub between the gate and
        the issue. A reading past the tolerance there is a stop that names `reserve`, recorded
        before any of: the story saved, `reserved` journaled, the claim posted. The story is not
        admitted, so a later run can still reserve it.
        Mutations: the operation name that `reserve` passes to `_authorize` replaced by another
        command's; in `reserve`, `save_story`, the `reserved` journal line or `_post_intent` moved
        ahead of `_authorize`."""
        c = self.h.coordinator()
        self.h.clock[0] = MARK
        c.status()
        reading = "2026-11-07T11:54:59Z"  # one second past the 5-minute tolerance
        comments = self.h.h.fake.comments
        posted = {number: list(found) for number, found in comments.items()}
        counts, journaled = self.store.story_counts(), self.events()
        elsewhere = c._claims_elsewhere  # the last GitHub read after the gate, before the authorization is issued

        def step_back(*args, **kwargs):
            self.h.clock[0] = reading
            return elsewhere(*args, **kwargs)

        with mock.patch.object(c, "_claims_elsewhere", step_back):
            exc = refuses(self, lambda: c.reserve(S, self.h.h.snapshot, "base"), "clock-regression")
        stop = stop_of(self.store)
        self.assertEqual((stop["code"], stop["observed_at"], stop["operation"]), ("clock-regression", reading, "reserve"))
        self.assertEqual(exc.detail["stop"], stop)
        self.assertEqual({number: list(found) for number, found in comments.items()}, posted)  # no claim comment
        self.assertIsNone(self.store.load_story(S))
        self.assertEqual(self.events(), journaled + ["activation-stopped"])  # no `reserved`, no intent
        self.assertEqual((self.store.story_counts(), self.store.load_run().last_observed_at), (counts, MARK))
        self.h.clock[0] = MARK  # the clock is back at the mark: only the recorded stop refuses now, and not as `no-reclaim`
        exc = refuses(self, lambda: c.reserve(S, self.h.h.snapshot, "base"), "clock-regression")
        self.assertEqual((exc.detail["stop"], stop_of(self.store), self.store.load_story(S)), (stop, stop, None))

    def test_an_authorization_issued_at_or_past_the_mark_keeps_no_second_reading(self):
        review_authorized(self.h)
        self.assertTrue(all("issued_observed_at" not in a for a in self.store.load_story(S).authorizations))

    def test_the_refusal_for_an_unfloored_authorization_names_issued_at_only(self):
        """PR #176 R2-2: with no second reading the refusal compares with `issued_at` and says so."""
        c, auth = r5.ReconcileRevokedUnderClearableStopTests.repair(self)
        self.assertNotIn("issued_observed_at", auth)
        refuses(self, lambda: c.cancel(S, "owner stops the repair"), "authorization-unresolved")
        c.cancel_run("owner stops the run")
        receipt, evidence = r5.ReconcileRevokedUnderClearableStopTests.evidence()
        earlier = {**receipt, "startedAt": "2000-01-01T00:00:00Z"}
        exc = refuses(self, lambda: c.reconcile_retained_execution(S, auth["id"], earlier, evidence, "r", "p"), "run-precedes-authorization")
        self.assertEqual(exc.detail, {"started_at": earlier["startedAt"], "issued_at": auth["issued_at"], "compared_with": "issued_at"})
        self.assertNotIn("the clock read", str(exc))

    def test_under_a_clock_stop_it_is_recorded(self):
        c, auth = r5.ReconcileRevokedUnderClearableStopTests.repair(self)
        refuses(self, lambda: c.cancel(S, "owner stops the repair"), "authorization-unresolved")
        regress(self, self.h, c)
        receipt, evidence = r5.ReconcileRevokedUnderClearableStopTests.evidence()
        state = c.reconcile_retained_execution(S, auth["id"], receipt, evidence, "r", "p")
        self.assertEqual(state.authorization(auth["id"])["reconciliation"]["observed_at"], BEHIND)


# -- PR #176 R1-3: the conflicts of reserve and resume ------------------------------------------------------------------------
class ConflictStampsWithoutAStopTests(LiveCase):
    """PR #176 R1-3: `blocked.at` of a conflict that `reserve` or `resume` records is floored like
    the other stamps. These operations refuse under a recorded stop, so the floor applies with no
    stop and the clock inside the tolerance behind the mark. Mutation: the `blocked.at` of the
    duplicate marker, the unreadable claim, the lost race or the stale claim back to `self.now()`."""

    def setUp(self):
        super().setUp()
        self.c = self.h.coordinator()
        self.h.clock[0] = MARK
        self.c.status()
        self.h.clock[0] = INSIDE

    def blocked(self) -> dict:
        self.assertIsNone(stop_of(self.store))
        return self.store.load_story(S).blocked

    def test_a_claim_that_is_not_readable_back(self):
        arm_failure_after_claim(self.h.h, reads_after_post=2, hide_ours=True, run="run-live")
        refuses(self, lambda: self.c.reserve(S, self.h.h.snapshot, "base"), "claim-unverifiable")
        self.assertEqual((self.blocked()["race_unsettled"], self.blocked()["at"]), (True, MARK))

    def test_a_duplicate_marker(self):
        original = self.h.h.fake.post_comment

        def twice(number, body):
            original(number, body)
            return original(number, body)

        self.h.h.fake.post_comment = twice
        with self.assertRaises(Conflict):
            self.c.reserve(S, self.h.h.snapshot, "base")
        self.assertIn("duplicate marker for claim", self.blocked()["reason"])
        self.assertEqual(self.blocked()["at"], MARK)

    def test_a_lost_claim_race(self):
        original = self.h.h.fake.post_comment

        def interleaved(number, body):
            if "kind=claim" in body and not any((c.marker or {}).get("run") == "run-other" for c in self.h.h.fake.comments[number]):
                self.h.h.fake.comments[number].append(Comment(5, render_marker(kind="claim", run="run-other", story=S, op="claim") + "\nearlier", "machine", EARLY))
            return original(number, body)

        self.h.h.fake.post_comment = interleaved
        refuses(self, lambda: self.c.reserve(S, self.h.h.snapshot, "base"), "claim-race-lost")
        self.assertEqual(self.blocked()["at"], MARK)
        release = self.store.load_story(S).intent("release")
        self.assertEqual((release.created_at, release.completed_at), (MARK, MARK))

    def test_a_stale_claim_cancelled_by_resume(self):
        self.h.h.fake.fail_once["post_comment"] = Outage("503")
        with self.assertRaises(Outage):
            self.c.reserve(S, self.h.h.snapshot, "base")
        self.h.h.fake.set_status_externally(21, "Blocked")
        state = self.c.resume(S, ok_worktree)
        self.assertEqual((state.phase, state.blocked["from_phase"], state.blocked["at"]), ("cancelled", "claim-incomplete", MARK))
        self.assertIsNone(stop_of(self.store))


# -- the documentation ------------------------------------------------------------------------------------------------------
class DocumentedTests(unittest.TestCase):
    """The guide describes every changed event detail and report field, and the README names this file."""

    def test_the_guide_names_the_changed_details_and_fields(self):
        text = DOCS.read_text(encoding="utf-8")
        for needle in ("`field`", "`consequence`", "`presented_current`", "`clear_requires`", "`recovered: true`", "recorded directory cannot be examined", "`issues/0`", "5 seconds"):
            self.assertIn(needle, text, needle)
        self.assertNotIn("an `OSError` without an errno told apart by its `strerror`: the message names", text)

    def test_the_guide_states_the_stamp_rule_without_the_reconciliation_exception(self):
        """PR #176 R1-1, R1-2: the reconciliation and an intent's `created_at` are floored like the rest."""
        text = DOCS.read_text(encoding="utf-8")
        for needle in ("an intent's `created_at` and `completed_at`", "One stamp is an exception: a story's `updated_at`", "without one only when `reconciliation.at` was floored",
                       "`issued_observed_at`", "`claim.reserved_at`, `checks[].at`, `reviews[].at`, `proposal.at`", "`bound_at` and `claim.claimed_at` of a bind (for work or for cleanup)"):
            self.assertIn(needle, text, needle)
        for gone in ("Two stamps are exceptions", "floored at the mark only while a `clock-regression` stop is recorded", "is recorded only under a clock stop"):
            self.assertNotIn(gone, text, gone)

    def test_the_guide_states_what_the_run_order_check_compares_and_its_bound(self):
        """PR #176 R2-1, R2-2: the reconcile section names the comparison the code makes (the clock's
        reading at issue), the window it accepts by design and what the refusal reports."""
        text = DOCS.read_text(encoding="utf-8")
        for needle in ("`startedAt` at or after the time the clock read when the authorization was issued (`issued_observed_at` when `issued_at` was floored, otherwise `issued_at`",
                       "a `startedAt` from `issued_observed_at` up to `issued_at` is accepted by design", "cannot be told from one that started after the issue",
                       "`compared_with` naming the field that was compared, plus `issued_observed_at` when the authorization has one"):
            self.assertIn(needle, text, needle)
        for gone in ("`startedAt` at or after the authorization's `issued_at`", "can never settle a later authorization"):
            self.assertNotIn(gone, text, gone)

    def test_the_guide_states_that_the_issue_reading_is_judged_against_the_mark(self):
        """PR #176 R3-1: the bound the reconcile section gives for the accepted window rests on this rule."""
        text = " ".join(DOCS.read_text(encoding="utf-8").split())
        for needle in ("the clock reading an authorization is issued with (`reserve`, `authorize-review`, `authorize-repair`) is taken after that observation",
                       "records `clock-regression` and issues nothing, so a recorded `issued_observed_at` is never more than the tolerance before `issued_at`",
                       "That stop names the command as its `operation` and the later reading as its `observed_at`"):
            with self.subTest(needle=needle):
                self.assertIn(needle, text)

    def test_the_readme_names_this_file(self):
        self.assertIn("tests/test_pr114_round7_findings.py", README.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
