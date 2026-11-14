"""Regressions for PR #114 round 7: review 5864099379 (17 threads, tracked in issue #118). One class
per finding, F1 to F17 in the order of the issue, with the review thread id in the docstring; each
test is named after the behaviour it pins. F14 to F17 are the assertions the review found missing:
each fails under the mutation its finding names. Every scenario runs on the fixture transport marked
live with temporary state and an injected clock; no real GitHub call and no real task is ever made,
and no test writes to the real use ledger under the home directory.

The six classes before the documentation tests are round 1 of PR #185, the walkthrough risks R1-1
to R1-5 the owner did not accept, each with its thread id (R1-5 has two classes: the journal lines
and the git child). The R1-1 to R1-3 classes and the documentation tests also carry the corrections
of its review round 2 (R2-1 to R2-3); the R1-2 class and the documentation tests carry those of
round 3 (R3-1 to R3-5). R1-1 to R1-3 return the stamp rule to the scope F9 froze (a stamp is the clock
except under a recorded `clock-regression` stop), so the tests of PR #176 that pinned the floor
without a stop, the field `issued_observed_at` and the stop `_authorize` recorded are rewritten here
to pin their absence; an authorization is not issued while the clock reads before the high-water
mark (`clock-behind-mark`)."""

from __future__ import annotations

import contextlib
import errno
import json
import os
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from automation.tests import test_pr114_round5_findings as r5
from automation.tests.support import IMPLEMENTER, REVIEW_BRANCH, REVIEW_WORKTREE, REVIEWER, ok_worktree, passing_runner
from automation.tests.test_activation import S, T0
from automation.tests.test_enabling_repair_1 import claimed, refuses
from automation.tests.support import controlled_cli_clock
from automation.tests.test_pr108_review_findings import cli_args, no_gh_calls, review_authorized, run_cli
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

    def cannot_take_line(self, suffix: str, defect: str) -> None:
        """PR #176 R7-1, the other values that are no usable path: absolute, but `os.stat` refuses
        them with a `ValueError`. PR #176 R9-1: the line names the value and its defect in the words
        of the refusal (`_recorded_dir_defect`), not in those of the Python version's `os.stat`.
        One value per test: a second line of the same variant is not journaled again."""
        recorded = str(self.recorded) + suffix
        with self.assertRaises(ValueError):
            os.stat(os.path.join(recorded, "run-live", "run.json"))
        line = self.line(state_dir=recorded)
        self.assertIn(f"names the state directory {recorded!r}, not ", line["error"])
        self.assert_names_no_usable_state_directory(line, f"ValueError: the recorded state directory {recorded!r} {defect}")
        for raw in ("\0", "\ud800"):  # the line names the value escaped, never raw
            self.assertNotIn(raw, line["error"])

    def test_a_recorded_path_the_file_system_cannot_take_is_a_damaged_record_in_the_journaled_line(self):
        self.cannot_take_line(*self.UNUSABLE_ABSOLUTE[0])

    def test_a_recorded_path_that_cannot_be_encoded_is_a_damaged_record_in_the_journaled_line(self):
        self.cannot_take_line(*self.UNUSABLE_ABSOLUTE[1])

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

    # Absolute, so the R8-1 `isabs` test passes them, but no path the file system can take: `os.stat` refuses both with a `ValueError`.
    UNUSABLE_ABSOLUTE = (("\0x", "is a path the file system cannot take: it holds a NUL character"),
                         (os.sep + "\ud800", f"is a path the file system cannot take: it cannot be encoded as a file name ({sys.getfilesystemencoding()})"))

    def test_an_aborted_record_with_an_absolute_path_the_file_system_cannot_take_is_a_use_and_is_never_retried(self):
        """PR #176 R9-1: the second kind of unusable path. Such a record never matches a run, so the
        `activation-used` refusal, in the preflight and in the creation, says the record is damaged
        and names no retry: no directory accepts one, not even the recorded value itself. The
        mutation it pins: the NUL or the encoding test removed from `_recorded_dir_defect` (or the
        `use_refusal` branch back on `os.path.isabs` alone), which brings the retry advice back,
        with the raw NUL in the suggested command."""
        real = Path(os.path.realpath(self.h.h.state_dir))
        ledger = ledger_path(self.h.activation.digest, self.h.activation.path)
        for suffix, defect in self.UNUSABLE_ABSOLUTE:
            recorded = str(real) + suffix
            with self.subTest(recorded=recorded):
                self.assertTrue(os.path.isabs(recorded))  # the precondition: the R8-1 test alone lets it through
                with self.assertRaises(ValueError):
                    os.stat(recorded)
                set_ledger(self.h, state="aborted", state_dir=recorded)
                self.assertEqual(record(self.h)["state_dir"], recorded)  # the ledger file carries the value as it is
                for state_dir in (real, recorded):  # this run's directory, and the retry the old advice named
                    self.assertFalse(activation_module._same_state_dir(recorded, state_dir))
                    self.assertFalse(activation_module._retryable_creation(record(self.h), state_dir, "run-live"))
                # The match is refused by the rule itself, not because `realpath` happens to raise on such a value: with
                # one that hands the value back (as string equality would then match), the record is still not this run.
                with mock.patch.object(os.path, "realpath", lambda path, **_: os.fspath(path)):
                    self.assertFalse(activation_module._same_state_dir(recorded, recorded))
                    self.assertTrue(activation_module._same_state_dir(str(real), str(real)))  # the stand-in still matches a usable path
                preflight = [m for code, m in self.h.activation.creation_problems(self.h.h.policy, "run-live", T0, state_dir=real) if code == "activation-used"]
                refused = refuses(self, lambda: record_activation_use(self.h.activation, real, "run-live", T0), "activation-used")
                self.assertEqual(record(self.h)["state"], "aborted")
                self.assertEqual(len(preflight), 1)
                for message in (preflight[0], str(refused)):
                    self.assertIn(f"the record names no usable state directory ({recorded!r} {defect}): it is damaged, so that creation cannot be retried", message)
                    self.assertIn(f"use ledger {ledger}: aborted", message)
                    self.assertIn("inspect or restore that file", message)
                    for other in ("only that same creation may be retried", "--state-dir", "\0", "\ud800"):  # the value is named escaped, never raw
                        self.assertNotIn(other, message)

    def test_the_refusal_and_the_probe_of_the_recorded_directory_agree_on_what_is_no_usable_path(self):
        """PR #176 R9-1: one rule for a damaged record, for the recorded state directory. A value
        with a defect (`_recorded_dir_defect`) is what `_recorded_run` reports as no usable path
        (an error that is not an `OSError`, which `confirm_activation_use` journals as a damaged
        record), in the same words as the `aborted` refusal, which names no retry for it. A path
        the file system is asked about has no defect, also when it answers with an error. The
        mutation it pins: either side taking a value the other refuses, or wording it differently."""
        real = os.path.realpath(self.h.h.state_dir)
        cannot_take = dict((real + suffix, defect) for suffix, defect in self.UNUSABLE_ABSOLUTE)
        unusable = {7: "is not a path", None: "is not a path", "": "is not an absolute path", ".": "is not an absolute path", "rel": "is not an absolute path",
                    os.path.join("..", "rel"): "is not an absolute path", **cannot_take}
        too_long = os.path.join(real, "x" * 300)  # the file system is asked and refuses: an `OSError`, not a damaged record
        with self.assertRaises(OSError) as refused:
            os.stat(too_long)
        self.assertEqual(refused.exception.errno, errno.ENAMETOOLONG)
        usable = {real: "run", str(self.recorded): "gone", os.path.join(real, "no", "such", "directory"): "gone", too_long: "unknown"}
        for value, expected in {**unusable, **usable}.items():
            with self.subTest(value=value):
                defect = activation_module._recorded_dir_defect(value)
                found, problem = activation_module._recorded_run(value, "run-live")
                message = use_refusal({"run_id": "run-live", "state_dir": value, "state": "aborted", "created_at": T0}, "/l/x.json")
                if value in unusable:
                    self.assertEqual(defect, expected)
                    self.assertEqual((found, type(problem)), ("unknown", ValueError if isinstance(value, str) else TypeError))
                    self.assertEqual(str(problem), f"the recorded state directory {value!r} {expected}")
                    self.assertIn(f"names no usable state directory ({value!r} {expected}): it is damaged, so that creation cannot be retried", message)
                    self.assertNotIn("only that same creation may be retried", message)
                else:
                    self.assertIsNone(defect)
                    self.assertEqual(found, expected)
                    self.assertEqual(problem is None, expected != "unknown")
                    self.assertIsInstance(problem, (OSError, type(None)))
                    self.assertIn("only that same creation may be retried", message)
                    self.assertNotIn("damaged", message)

    def test_an_aborted_record_with_an_absolute_path_still_names_the_retry(self):
        """The other side of the R8-1 refusal: a record that names an absolute directory keeps the
        retry advice, also when it is refused for another run id."""
        set_ledger(self.h, state="aborted")
        retry = f"only that same creation may be retried (--run-id run-live --state-dir {record(self.h)['state_dir']})"
        message = use_refusal(record(self.h), "/l/x.json")
        self.assertIn(retry, message)
        self.assertNotIn("damaged", message)
        real = Path(os.path.realpath(self.h.h.state_dir))
        self.assertEqual([m for code, m in self.h.activation.creation_problems(self.h.h.policy, "run-live", T0, state_dir=real) if code == "activation-used"], [])  # that creation is the retry
        other = [m for code, m in self.h.activation.creation_problems(self.h.h.policy, "run-other", T0, state_dir=real) if code == "activation-used"]
        self.assertEqual(len(other), 1)
        self.assertIn(retry, other[0])
        self.assertNotIn("damaged", other[0])

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
    clock the Store read and is ordered by `seq` (documented). Without a recorded stop a stamp is
    the clock (PR #185 R1-3, `StampIsTheClockWithoutAStopTests`)."""

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

    def test_without_a_stop_a_clock_inside_the_tolerance_behind_the_mark_is_the_stamp(self):
        c = claimed(self.h)
        self.h.clock[0] = MARK
        c.status()
        self.h.clock[0] = INSIDE
        state = c.record_task_terminal(S, self.h.terminal())
        self.assertIsNone(stop_of(self.store))
        self.assertEqual(state.task_history[-1]["at"], INSIDE)

    def issued_at_the_mark(self, issue):
        """Run an issuing operation with the clock at the mark (nothing is issued before it,
        `clock-behind-mark`), then read 3 minutes behind the mark again: no stop is recorded."""
        self.h.clock[0] = MARK
        state = issue()
        self.h.clock[0] = INSIDE
        return state

    def approved(self, c):
        """Drive the advancing operations up to an approved review: the two issues at the mark, everything else at `INSIDE`."""
        self.issued_at_the_mark(lambda: c.reserve(S, self.h.h.snapshot, "base"))
        c.bind_receipt(S, IMPLEMENTER, str(self.h.h.worktree), "t3/om-01-02", ok_worktree)
        c.record_head(S, self.h.h.sha, self.h.terminal())
        c.run_checks(S, self.h.h.sha, str(self.h.h.worktree), passing_runner)
        self.issued_at_the_mark(lambda: c.authorize_review(S, self.h.h.sha))
        c.bind_receipt(S, REVIEWER, REVIEW_WORKTREE, REVIEW_BRANCH, ok_worktree)
        return c.record_review(S, self.h.h.sha, "approved", "report.md", self.h.terminal())

    def test_the_non_issuing_advancing_operations_stamp_the_clock_without_a_stop(self):
        """PR #185 R1-3 (rewritten from PR #176 R1-3): the advancing operations refuse under a
        recorded stop, so they never run where the floor applies: with no stop and the clock inside
        the tolerance behind the mark every stamp of a bind, a check, a review and a proposal is
        the clock, earlier than the stamps before it (the second stated cost). The issuing
        operations do not run there (`AuthorizeIssuesNothingBehindTheMarkTests`): their stamps are
        at the mark. Mutation: `_floored` flooring without a recorded stop."""
        c = self.h.coordinator()
        state = self.issued_at_the_mark(lambda: c.reserve(S, self.h.h.snapshot, "base"))
        self.assertEqual((state.claim["reserved_at"], state.authorizations[-1]["issued_at"]), (MARK, MARK))
        state = c.bind_receipt(S, IMPLEMENTER, str(self.h.h.worktree), "t3/om-01-02", ok_worktree)
        self.assertEqual((state.claim["claimed_at"], state.active_task["bound_at"], state.authorizations[-1]["bound_at"]), (INSIDE, INSIDE, INSIDE))
        c.record_head(S, self.h.h.sha, self.h.terminal())
        state = c.run_checks(S, self.h.h.sha, str(self.h.h.worktree), passing_runner)
        self.assertEqual(state.checks[-1]["at"], INSIDE)
        state = self.issued_at_the_mark(lambda: c.authorize_review(S, self.h.h.sha))
        self.assertEqual((state.authorizations[-1]["purpose"], state.authorizations[-1]["issued_at"]), ("review", MARK))
        c.bind_receipt(S, REVIEWER, REVIEW_WORKTREE, REVIEW_BRANCH, ok_worktree)
        state = c.record_review(S, self.h.h.sha, "approved", "report.md", self.h.terminal())
        self.assertEqual(state.reviews[-1]["at"], INSIDE)
        self.h.h.fake.pull_requests[7] = PullRequestRecord(7, "OPEN", self.h.h.sha, False, (), "SUCCESS")
        state = c.propose_evidence(S, self.h.h.sha, 7, [], "s")
        self.assertEqual(state.proposal["at"], INSIDE)
        proposal = next(i for i in state.intents if i.kind == "proposal")
        self.assertEqual((proposal.created_at, proposal.completed_at), (INSIDE, INSIDE))
        self.assertEqual([entry["at"] for entry in state.task_history], [INSIDE, INSIDE])
        self.assertEqual([a["issued_at"] for a in state.authorizations], [MARK, MARK])  # no authorization is dated before the mark
        self.assertIsNone(stop_of(self.store))
        self.assertEqual(self.store.load_run().last_observed_at, MARK)  # the mark is still ahead of every `INSIDE` stamp above

    def test_a_review_regression_on_github_is_stamped_with_the_clock_without_a_stop(self):
        """The review a GitHub objection records is stamped like a local one."""
        c = self.h.coordinator()
        self.approved(c)
        objection = {"state": "CHANGES_REQUESTED", "commit": self.h.h.sha, "author": "A", "submitted_at": "1"}
        self.h.h.fake.pull_requests[7] = PullRequestRecord(7, "OPEN", self.h.h.sha, False, (objection,), "SUCCESS")
        with self.assertRaises(Refused) as ctx:
            c.propose_evidence(S, self.h.h.sha, 7, [], "s")
        self.assertIn("outstanding CHANGES_REQUESTED from ['A']", str(ctx.exception))
        review = self.store.load_story(S).reviews[-1]
        self.assertEqual((review["regression"], review["at"]), (True, INSIDE))

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


def reapers_of(child) -> list[threading.Thread]:
    """The live threads that wait for ``child`` (`cli._reap_abandoned`), found by their target: the child's `wait`."""
    return [t for t in threading.enumerate() if getattr(t, "_target", None) == child.wait]


# -- F13 --------------------------------------------------------------------------------------------------------------------
class StuckGitIsBoundedTests(unittest.TestCase):
    """F13 (thread 4542174977): a git that survives `kill()` no longer hangs the call: the timeout is
    raised after waiting at most 5 seconds for the killed child."""

    class Stuck:
        """A child in uninterruptible sleep: it never answers and does not die on SIGKILL."""

        def __init__(self, exits_after_kill: bool):
            self.exits_after_kill, self.calls = exits_after_kill, []
            self.exited, self.pid = threading.Event(), 4242  # `exited` is set when the child dies after all; the pid only names the reaper thread
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
                if threading.current_thread() is threading.main_thread():
                    raise AssertionError("an unbounded wait on a child that ignores SIGKILL never returns")
                self.exited.wait()  # the reaper's wait (PR #185 R1-5): it returns when the child exits
                return -9
            if not self.exits_after_kill:
                raise subprocess.TimeoutExpired("git", timeout)
            return -9

    def run_stuck(self, exits_after_kill: bool) -> "StuckGitIsBoundedTests.Stuck":
        child = self.Stuck(exits_after_kill)
        self.addCleanup(child.exited.set)  # whatever the test asserts, a thread waiting for this child ends
        with mock.patch.object(cli_module.subprocess, "Popen", return_value=child):
            with self.assertRaises(cli_module.WorkTreeUnknown) as ctx:
                cli_module._work_tree("/somewhere/owner")
        self.assertIn("hung mount", str(ctx.exception))
        self.assertIn("/somewhere/owner", str(ctx.exception))
        return child

    def test_a_child_that_survives_the_kill_still_raises(self):
        child = self.run_stuck(exits_after_kill=False)
        reapers = reapers_of(child)  # the abandoned child is waited for on a thread of its own (`AbandonedGitIsReapedTests`)
        child.exited.set()
        for reaper in reapers:
            reaper.join(timeout=10)
        self.assertEqual(child.calls[:3], [("communicate", cli_module.GIT_TIMEOUT_SECONDS), ("kill", None), ("wait", 5)])

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

    def test_without_a_stop_a_clock_inside_the_tolerance_is_the_stamp_and_no_observed_at_is_recorded(self):
        """PR #185 R1-3 (rewritten from PR #176 R1-1): with no stop and the clock inside the
        tolerance behind the mark, the reconciliation is stamped with the clock like every other
        stamp, records no `observed_at` and its backup name carries no second observation.
        Mutations: `_floored` flooring without a recorded stop; `observed_at` recorded whenever the
        stamp differs from the reading."""
        c, auth = r5.ReconcileRevokedUnderClearableStopTests.repair(self)
        self.h.clock[0] = MARK
        c.status()
        self.h.clock[0] = INSIDE
        refuses(self, lambda: c.cancel(S, "owner stops the repair"), "authorization-unresolved")  # revoked, stamped with the clock
        c.cancel_run("owner stops the run")
        self.assertIsNone(stop_of(self.store))
        receipt, evidence = r5.ReconcileRevokedUnderClearableStopTests.evidence()
        state = c.reconcile_retained_execution(S, auth["id"], receipt, evidence, "r", "p")
        recorded = state.authorization(auth["id"])
        self.assertEqual((recorded["revoked_at"], recorded["bound_at"], recorded["reconciliation"]["at"]), (INSIDE, INSIDE, INSIDE))
        self.assertNotIn("observed_at", recorded["reconciliation"])
        self.assertEqual(state.task_history[-1]["at"], INSIDE)
        line = next(e for e in self.store.read_journal() if e["event"] == "retained-execution-reconciled")
        self.assertNotIn("-obs", line["detail"]["backup"])
        self.assertIn("2026-11-07T115700Z", line["detail"]["backup"])
        self.assertIsNone(stop_of(self.store))

    def test_an_authorization_has_no_issued_observed_at(self):
        review_authorized(self.h)
        self.assertTrue(all("issued_observed_at" not in a for a in self.store.load_story(S).authorizations))

    def test_the_refusal_reports_started_at_and_issued_at(self):
        """The `run-precedes-authorization` refusal is `main`'s: the two times it compared, nothing else."""
        c, auth = r5.ReconcileRevokedUnderClearableStopTests.repair(self)
        self.assertNotIn("issued_observed_at", auth)
        refuses(self, lambda: c.cancel(S, "owner stops the repair"), "authorization-unresolved")
        c.cancel_run("owner stops the run")
        receipt, evidence = r5.ReconcileRevokedUnderClearableStopTests.evidence()
        earlier = {**receipt, "startedAt": "2000-01-01T00:00:00Z"}
        exc = refuses(self, lambda: c.reconcile_retained_execution(S, auth["id"], earlier, evidence, "r", "p"), "run-precedes-authorization")
        self.assertEqual(exc.detail, {"started_at": earlier["startedAt"], "issued_at": auth["issued_at"]})
        self.assertNotIn("the clock read", str(exc))

    def test_under_a_clock_stop_it_is_recorded(self):
        c, auth = r5.ReconcileRevokedUnderClearableStopTests.repair(self)
        refuses(self, lambda: c.cancel(S, "owner stops the repair"), "authorization-unresolved")
        regress(self, self.h, c)
        receipt, evidence = r5.ReconcileRevokedUnderClearableStopTests.evidence()
        state = c.reconcile_retained_execution(S, auth["id"], receipt, evidence, "r", "p")
        self.assertEqual(state.authorization(auth["id"])["reconciliation"]["observed_at"], BEHIND)


# -- PR #185 R1-3: the conflicts of reserve and resume ------------------------------------------------------------------------
class ConflictStampsWithoutAStopTests(LiveCase):
    """PR #185 R1-3 (rewritten from PR #176 R1-3): `blocked.at` of a conflict that `reserve` or
    `resume` records is the clock, like the other stamps. These operations refuse under a recorded
    stop, so they only ever run without one. `reserve` issues nothing before the mark, so here it
    starts at the mark and the clock reads inside the tolerance behind it from the moment the
    claim is posted. Mutation: `_floored` flooring without a recorded stop."""

    def setUp(self):
        super().setUp()
        self.c = self.h.coordinator()
        self.h.clock[0] = MARK
        self.c.status()
        original = self.h.h.fake.post_comment

        def post(number, body):
            self.h.clock[0] = INSIDE  # after the issue: every stamp from here on is written with the clock behind the mark
            return original(number, body)

        self.h.h.fake.post_comment = post

    def blocked(self) -> dict:
        self.assertIsNone(stop_of(self.store))
        return self.store.load_story(S).blocked

    def test_a_claim_that_is_not_readable_back(self):
        arm_failure_after_claim(self.h.h, reads_after_post=2, hide_ours=True, run="run-live")
        refuses(self, lambda: self.c.reserve(S, self.h.h.snapshot, "base"), "claim-unverifiable")
        self.assertEqual((self.blocked()["race_unsettled"], self.blocked()["at"]), (True, INSIDE))

    def test_a_duplicate_marker(self):
        original = self.h.h.fake.post_comment

        def twice(number, body):
            original(number, body)
            return original(number, body)

        self.h.h.fake.post_comment = twice
        with self.assertRaises(Conflict):
            self.c.reserve(S, self.h.h.snapshot, "base")
        self.assertIn("duplicate marker for claim", self.blocked()["reason"])
        self.assertEqual(self.blocked()["at"], INSIDE)

    def test_a_lost_claim_race(self):
        original = self.h.h.fake.post_comment

        def interleaved(number, body):
            if "kind=claim" in body and not any((c.marker or {}).get("run") == "run-other" for c in self.h.h.fake.comments[number]):
                self.h.h.fake.comments[number].append(Comment(5, render_marker(kind="claim", run="run-other", story=S, op="claim") + "\nearlier", "machine", EARLY))
            return original(number, body)

        self.h.h.fake.post_comment = interleaved
        refuses(self, lambda: self.c.reserve(S, self.h.h.snapshot, "base"), "claim-race-lost")
        self.assertEqual(self.blocked()["at"], INSIDE)
        release = self.store.load_story(S).intent("release")
        self.assertEqual((release.created_at, release.completed_at), (INSIDE, INSIDE))

    def test_a_stale_claim_cancelled_by_resume(self):
        self.h.h.fake.fail_once["post_comment"] = Outage("503")
        with self.assertRaises(Outage):
            self.c.reserve(S, self.h.h.snapshot, "base")
        self.h.h.fake.set_status_externally(21, "Blocked")
        self.h.clock[0] = INSIDE
        state = self.c.resume(S, ok_worktree)
        self.assertEqual((state.phase, state.blocked["from_phase"], state.blocked["at"]), ("cancelled", "claim-incomplete", INSIDE))
        self.assertIsNone(stop_of(self.store))


# == PR #185 round 1: the walkthrough risks the owner did not accept ===========================================================
STEPPED = "2026-11-07T11:00:00Z"  # an hour behind the mark: far past the 5-minute tolerance


class AuthorizeIssuesNothingBehindTheMarkTests(LiveCase):
    """PR #185 R1-1 (thread PRRT_kwDOVjxExc63YAc7): `_authorize` records no clock stop of its own,
    and it issues nothing while the clock reads before the run's high-water mark, whether the
    clock stepped back between the operation's gate and the issue or still reads inside the
    tolerance: it refuses `clock-behind-mark`, naming the mark as the time to retry at. Nothing of
    the story, the journal or GitHub changes (the operation's gate, which ran first, may have saved
    its observation in `run.json`: PR #185 R2-3); the gate of the next operation judges the clock; at or past the
    mark the issue goes through. Mutations: the guard removed from `_authorize` (an authorization
    dated before the mark is issued); a stop recorded from `_authorize`."""

    def repair_ready(self):
        c = review_authorized(self.h)
        c.bind_receipt(S, REVIEWER, REVIEW_WORKTREE, REVIEW_BRANCH, ok_worktree)
        c.record_review(S, self.h.h.sha, "changes-requested", "r.md", self.h.terminal())
        return c, lambda: c.authorize_repair(S), "_require_no_obligation"

    def review_ready(self):
        c = claimed(self.h)
        c.record_head(S, self.h.h.sha, self.h.terminal())
        c.run_checks(S, self.h.h.sha, str(self.h.h.worktree), passing_runner)
        return c, lambda: c.authorize_review(S, self.h.h.sha), "_verify_worktree"

    def reserve_ready(self):
        c = self.h.coordinator()
        return c, lambda: c.reserve(S, self.h.h.snapshot, "base"), "_claims_elsewhere"

    def snapshot(self) -> tuple:
        path = self.store.story_path(S)
        return (path.read_text(encoding="utf-8") if path.exists() else None, self.events(), {number: list(found) for number, found in self.h.h.fake.comments.items()}, self.store.story_counts())

    def refused_then_issued(self, ready, reading: str, step_back: bool) -> None:
        """``reading`` is what the clock reads at the issue: from the operation's gate on, or, with
        ``step_back``, only after the gate passed at the mark (``method`` runs between the two)."""
        c, issue, method = ready()
        self.h.clock[0] = MARK
        c.status()
        before = self.snapshot()
        if step_back:
            original = getattr(c, method)

            def stepping(*args, **kwargs):
                self.h.clock[0] = reading
                return original(*args, **kwargs)

            with mock.patch.object(c, method, stepping):
                exc = refuses(self, issue, "clock-behind-mark")
        else:
            self.h.clock[0] = reading
            exc = refuses(self, issue, "clock-behind-mark")
        self.assertEqual(exc.detail, {"observed_at": reading, "high_water": MARK, "retry_at": MARK})
        self.assertIn(f"nothing was issued and no stop is recorded; retry once the clock reads {MARK} or later", str(exc))
        self.assertIsNone(stop_of(self.store))  # no stop of its own
        self.assertEqual(self.snapshot(), before)  # no story change, no journal line, no posted comment, no slot counted
        self.assertEqual(self.store.load_run().last_observed_at, MARK)
        self.h.clock[0] = MARK  # exactly at the mark: the issue goes through
        state = issue()
        auth = state.unresolved_authorization()
        self.assertEqual((auth["status"], auth["issued_at"]), ("pending", MARK))
        self.assertIsNone(stop_of(self.store))

    def test_reserve_after_a_step_back(self):
        self.refused_then_issued(self.reserve_ready, STEPPED, step_back=True)

    def test_authorize_review_after_a_step_back(self):
        self.refused_then_issued(self.review_ready, STEPPED, step_back=True)

    def test_authorize_repair_after_a_step_back(self):
        self.refused_then_issued(self.repair_ready, STEPPED, step_back=True)

    def test_a_step_back_of_one_second_refuses_too(self):
        self.refused_then_issued(self.repair_ready, "2026-11-07T11:59:59Z", step_back=True)

    def test_reserve_with_the_clock_inside_the_tolerance(self):
        self.refused_then_issued(self.reserve_ready, INSIDE, step_back=False)

    def test_authorize_review_with_the_clock_inside_the_tolerance(self):
        self.refused_then_issued(self.review_ready, INSIDE, step_back=False)

    def test_authorize_repair_with_the_clock_inside_the_tolerance(self):
        self.refused_then_issued(self.repair_ready, INSIDE, step_back=False)

    def test_reserve_after_a_step_back_on_a_run_with_no_later_observation(self):
        """The mark of a run with no later observation is the validated creation moment.
        Mutation: the guard reading `self.run.last_observed_at` instead of `_high_water_text()`."""
        c, issue, method = self.reserve_ready()
        self.assertIsNone(self.store.load_run().last_observed_at)
        before = self.snapshot()
        original = getattr(c, method)

        def stepping(*args, **kwargs):
            self.h.clock[0] = "2026-11-07T09:59:00Z"  # a minute before the creation at 10:00
            return original(*args, **kwargs)

        with mock.patch.object(c, method, stepping):
            exc = refuses(self, issue, "clock-behind-mark")
        self.assertEqual(exc.detail, {"observed_at": "2026-11-07T09:59:00Z", "high_water": T0, "retry_at": T0})
        self.assertIsNone(self.store.load_run().last_observed_at)
        self.assertEqual((self.snapshot(), stop_of(self.store)), (before, None))  # nothing saved, journaled or posted

    def gate_saved_then_issue_refused(self, ready) -> None:
        """PR #185 R2-3 (thread PRRT_kwDOVjxExc63YqHz): the gate runs before the issue. With the
        clock ahead of the mark at the gate and behind the new mark at the issue, the refusal
        changes nothing of the story, the journal or GitHub, but `run.json` holds the gate's
        observation, and that observation is the mark the refusal names."""
        ahead = "2026-11-07T12:01:00Z"
        c, issue, method = ready()
        self.h.clock[0] = MARK
        c.status()
        before = self.snapshot()
        self.h.clock[0] = ahead  # what the gate observes
        original = getattr(c, method)

        def stepping(*args, **kwargs):
            self.h.clock[0] = MARK  # a minute behind the gate's observation
            return original(*args, **kwargs)

        with mock.patch.object(c, method, stepping):
            exc = refuses(self, issue, "clock-behind-mark")
        self.assertEqual(exc.detail, {"observed_at": MARK, "high_water": ahead, "retry_at": ahead})
        self.assertEqual(self.store.load_run().last_observed_at, ahead)  # saved by the gate, not by the refusal
        self.assertEqual((self.snapshot(), stop_of(self.store)), (before, None))
        refuses(self, issue, "clock-behind-mark")  # the clock still reads the old mark: the mark the caller retries at moved
        self.h.clock[0] = ahead
        self.assertEqual(issue().unresolved_authorization()["issued_at"], ahead)

    def test_the_gate_of_a_refused_reserve_has_already_saved_its_observation(self):
        self.gate_saved_then_issue_refused(self.reserve_ready)

    def test_the_gate_of_a_refused_authorize_review_has_already_saved_its_observation(self):
        self.gate_saved_then_issue_refused(self.review_ready)

    def test_the_gate_of_a_refused_authorize_repair_has_already_saved_its_observation(self):
        self.gate_saved_then_issue_refused(self.repair_ready)

    def test_a_reading_or_a_mark_that_cannot_be_parsed_issues_nothing(self):
        """The guard never passes on a comparison it cannot make. Mutation: the comparison made
        through `_at_least_high_water`, which hands its input back on a parse problem. The
        wall-clock check that runs first in `_authorize` is stood in for: it does not survive such
        a value either (a load refuses such a record), and the guard must not rest on that."""
        c, _, _ = self.repair_ready()
        self.h.clock[0] = MARK
        c.status()
        state = self.store.load_story(S)
        issued = len(state.authorizations)
        with c.operation(), mock.patch.object(c, "_wall_clock", lambda: None):
            c._reload_run()
            with mock.patch.object(c, "now", lambda: "not-a-time"):
                exc = refuses(self, lambda: c._authorize(state, "repair", round_=1), "activation-invalid")
            self.assertIn("now 'not-a-time'", str(exc))
            c.run.last_observed_at = "not-a-time"  # LABELLED MUTATION in memory (a load refuses such a record)
            exc = refuses(self, lambda: c._authorize(state, "repair", round_=1), "activation-invalid")
            self.assertIn("high-water mark 'not-a-time'", str(exc))
            self.assertIn("nothing was issued", str(exc))
            c.run.last_observed_at, c.run.activation = None, {**c.run.activation, "validated_at": None}  # LABELLED MUTATION in memory: no mark at all
            refuses(self, lambda: c._authorize(state, "repair", round_=1), "activation-invalid")
        self.assertEqual(len(state.authorizations), issued)

    def test_the_cli_reports_the_refusal_with_its_detail(self):
        """Through the command line: exit 3 (a refusal) and the JSON error with the times a caller retries on."""
        self.repair_ready()
        self.h.clock[0] = MARK
        with controlled_cli_clock(self.h.clock), no_gh_calls() as calls:
            self.assertEqual(run_cli(cli_args(self.h, "status"))[0], 0)  # the mark is 12:00
            self.h.clock[0] = INSIDE
            code, out = run_cli(cli_args(self.h, "--live", "authorize-repair", S))
        error = out["error"]
        self.assertEqual((code, error["code"], error["observed_at"], error["high_water"], error["retry_at"]), (3, "clock-behind-mark", INSIDE, MARK, MARK))
        self.assertIn(f"retry once the clock reads {MARK} or later", error["message"])
        self.assertEqual((calls, stop_of(self.store), self.store.load_story(S).unresolved_authorization()), ([], None, None))

    def test_after_a_step_back_the_next_gate_judges_the_clock(self):
        c, issue, method = self.repair_ready()
        self.h.clock[0] = MARK
        original = getattr(c, method)

        def stepping(*args, **kwargs):
            self.h.clock[0] = STEPPED
            return original(*args, **kwargs)

        with mock.patch.object(c, method, stepping):
            refuses(self, issue, "clock-behind-mark")
        self.assertEqual((stop_of(self.store), self.events().count("activation-stopped")), (None, 0))
        exc = refuses(self, issue, "clock-regression")  # the gate of the next operation
        stop = stop_of(self.store)
        self.assertEqual((stop["code"], stop["observed_at"], stop["operation"]), ("clock-regression", STEPPED, "authorize-repair"))
        self.assertEqual((exc.detail["stop"], self.events().count("activation-stopped")), (stop, 1))

    def test_a_pending_authorization_is_returned_while_the_clock_is_behind(self):
        """Nothing is issued by the idempotent answer, so it is not guarded."""
        c, issue, _ = self.repair_ready()
        self.h.clock[0] = MARK
        auth = issue().unresolved_authorization()
        self.h.clock[0] = INSIDE
        with c.operation():
            c._reload_run()
            self.assertEqual(c._authorize(self.store.load_story(S), "repair", round_=1), auth)

    def test_a_fixture_run_has_no_mark_and_is_not_guarded(self):
        c, _, _ = self.repair_ready()
        self.h.clock[0] = MARK
        c.status()
        self.h.clock[0] = INSIDE
        with c.operation():
            c._reload_run()
            c.environment = "fixture"  # LABELLED MUTATION in memory
            self.assertEqual(c._authorize(self.store.load_story(S), "repair", round_=1)["issued_at"], INSIDE)

    def test_authorize_has_the_signature_of_main_and_judges_no_reading(self):
        c, _, _ = self.repair_ready()
        state = self.store.load_story(S)
        readings = []
        with c.operation(), mock.patch.object(c, "now", lambda: readings.append(1) or self.h.clock[0]), \
                mock.patch.object(c, "_observe_stop", side_effect=AssertionError("_authorize judges no reading")):
            c._reload_run()
            auth = c._authorize(state, "repair", round_=1)
        self.assertEqual((len(readings), auth["issued_at"], sorted(auth)), (1, T0, ["id", "issued_at", "purpose", "reason", "role", "round", "sha", "status", "task_id"]))


class RunOrderComparesIssuedAtTests(LiveCase):
    """PR #185 R1-2 (thread PRRT_kwDOVjxExc63YAc-): the `run-precedes-authorization` check, which
    is `main`'s, accepts no run whose `startedAt` reads before `issued_at`. It compares clock
    readings, not the order of events (PR #185 R2-1, thread PRRT_kwDOVjxExc63YqHw: a clock that
    steps back and reads at or after the mark again dates a later authorization before a run that
    started earlier; the guide states it and
    `test_a_clock_that_steps_back_and_still_reads_after_the_mark_dates_the_issue_before_an_earlier_run`
    pins it as the documented limit, PR #185 R3-5, thread PRRT_kwDOVjxExc63Y0Et). `issued_at` is
    the clock and is never before the high-water mark as it stood at the issue
    (`clock-behind-mark`; PR #185 R3-2, thread PRRT_kwDOVjxExc63Y0Ep: a later gate raises the
    mark), so a retained run that started at a reading before that mark can no longer settle an
    authorization, also inside the 5 minutes before the mark; at `issued_at` or later it is
    accepted. The class also holds the round 3 tests of the two writers of the mark (R3-1) and
    of a forward skew past the tolerance (R3-3). Mutations: the `clock-behind-mark` guard
    removed (the authorization is dated `INSIDE` and the early run is accepted); `<` to `<=`."""

    def repair_asked_for_behind_the_mark(self):
        c = review_authorized(self.h)
        c.bind_receipt(S, REVIEWER, REVIEW_WORKTREE, REVIEW_BRANCH, ok_worktree)
        c.record_review(S, self.h.h.sha, "changes-requested", "r.md", self.h.terminal())
        self.h.clock[0] = MARK
        c.status()
        self.h.clock[0] = INSIDE  # 3 minutes behind the mark: where the old window was
        refuses(self, lambda: c.authorize_repair(S), "clock-behind-mark")  # nothing is dated inside the old window
        self.h.clock[0] = MARK
        auth = c.authorize_repair(S).unresolved_authorization()
        self.assertNotIn("issued_observed_at", auth)
        refuses(self, lambda: c.cancel(S, "owner stops the repair"), "authorization-unresolved")
        c.cancel_run("owner stops the run")
        self.assertIsNone(stop_of(self.store))
        return c, auth

    def test_a_run_that_started_before_the_mark_settles_nothing_and_one_at_the_issue_does(self):
        c, auth = self.repair_asked_for_behind_the_mark()
        self.assertEqual(auth["issued_at"], MARK)
        receipt, evidence = r5.ReconcileRevokedUnderClearableStopTests.evidence()
        for started in ("2026-11-07T11:59:59Z", INSIDE, "2026-11-07T11:55:00Z", "2026-11-07T11:00:00Z"):  # one second before the issue, inside the old window, its edge, long before
            with self.subTest(started=started):
                exc = refuses(self, lambda: c.reconcile_retained_execution(S, auth["id"], {**receipt, "startedAt": started}, evidence, "r", "p"), "run-precedes-authorization")
                self.assertEqual(exc.detail, {"started_at": started, "issued_at": MARK})
                self.assertIn(f"was issued at {MARK};", str(exc))
        self.assertEqual(self.store.load_story(S).authorization(auth["id"])["status"], "revoked")  # nothing was consumed
        state = c.reconcile_retained_execution(S, auth["id"], {**receipt, "startedAt": MARK}, evidence, "r", "p")  # at the issue
        self.assertEqual(state.authorization(auth["id"])["status"], "consumed")
        self.assertTrue(all("issued_observed_at" not in a for a in state.authorizations))

    def test_a_clock_that_steps_back_and_still_reads_after_the_mark_dates_the_issue_before_an_earlier_run(self):
        """PR #185 R3-5 (thread PRRT_kwDOVjxExc63Y0Et). This pins the documented limit of the
        check (the guide's "Narrowed, not closed", #181 and #188), not a behaviour anyone wants:
        the run really started before the authorization was issued and is accepted, because the
        clock read later at its start than at the issue and never read before the mark while an
        operation ran. The run's start is simulated by its `startedAt`: the coordinator never
        observes it. If the limit is ever closed, this test is the one to turn around."""
        started, stepped_back = "2026-11-07T12:10:00Z", "2026-11-07T12:01:00Z"
        c = review_authorized(self.h)
        c.bind_receipt(S, REVIEWER, REVIEW_WORKTREE, REVIEW_BRANCH, ok_worktree)
        c.record_review(S, self.h.h.sha, "changes-requested", "r.md", self.h.terminal())
        self.h.clock[0] = MARK
        c.status()  # the gate that leaves the mark at 12:00
        # the clock runs on to 12:10, where the retained owner starts a run; no operation runs, so the mark stays at 12:00
        self.assertEqual(self.store.load_run().last_observed_at, MARK)
        self.h.clock[0] = stepped_back  # a step back of nine minutes that still reads after the mark
        auth = c.authorize_repair(S).unresolved_authorization()  # issued after the run started, dated before it
        self.assertEqual((auth["issued_at"], stop_of(self.store)), (stepped_back, None))  # no refusal and no stop: the coordinator saw nothing of the step
        self.assertEqual(self.store.load_run().last_observed_at, stepped_back)
        refuses(self, lambda: c.cancel(S, "owner stops the repair"), "authorization-unresolved")  # setup: this revokes the authorization
        c.cancel_run("owner stops the run")  # setup: the reconciliation is cleanup for a stopped run
        receipt, evidence = r5.ReconcileRevokedUnderClearableStopTests.evidence()
        state = c.reconcile_retained_execution(S, auth["id"], {**receipt, "startedAt": started}, evidence, "r", "p")
        self.assertEqual(state.authorization(auth["id"])["status"], "consumed")  # the limit: two readings are compared, not the order of events

    def test_the_issue_is_guarded_by_the_mark_at_the_issue_and_later_gates_raise_it(self):
        """PR #185 R3-2 (thread PRRT_kwDOVjxExc63Y0Ep): a stored `issued_at` is not before the mark
        as it stood at the issue; it is before the mark a later gate leaves, and a run that started
        between the two is accepted."""
        c, auth = self.repair_asked_for_behind_the_mark()
        later = "2026-11-07T12:20:00Z"
        self.h.clock[0] = later
        c.status()  # a later gate raises the mark past the stored `issued_at`
        self.assertEqual((auth["issued_at"], self.store.load_run().last_observed_at), (MARK, later))
        receipt, evidence = r5.ReconcileRevokedUnderClearableStopTests.evidence()
        refuses(self, lambda: c.reconcile_retained_execution(S, auth["id"], {**receipt, "startedAt": "2026-11-07T11:59:59Z"}, evidence, "r", "p"), "run-precedes-authorization")  # the raised mark changes nothing: `issued_at` is compared
        state = c.reconcile_retained_execution(S, auth["id"], {**receipt, "startedAt": "2026-11-07T12:05:00Z"}, evidence, "r", "p")  # after the issue, before today's mark
        self.assertEqual(state.authorization(auth["id"])["status"], "consumed")

    def test_a_clear_is_the_second_writer_of_the_mark(self):
        """PR #185 R3-1 (thread PRRT_kwDOVjxExc63Y0El): the gate saves nothing while a stop is
        recorded, and the clear sets the mark to the later of the clock and the mark. Mutation:
        `judged_at` replaced by `high_water` in the clear's save (the mark stays at 12:00)."""
        ahead = "2026-11-07T12:03:00Z"
        c = self.h.coordinator()
        regress(self, self.h, c)  # mark 12:00, a recorded clock-regression stop
        self.h.clock[0] = ahead
        c.status()  # a gate under the stop: it does not move the mark
        self.assertEqual(self.store.load_run().last_observed_at, MARK)
        c.clear_clock_regression(clearance(self.h))
        run = self.store.load_run()
        self.assertEqual((run.activation_stop, run.last_observed_at), (None, ahead))  # moved by the clear, not by a gate

    def test_a_forward_skew_past_the_tolerance_is_a_stop_that_waiting_does_not_end(self):
        """PR #185 R3-3 (thread PRRT_kwDOVjxExc63Y0Eq): an observation 10 minutes ahead becomes the
        mark; once the clock is corrected the next gate records `clock-regression`, the clear
        refuses until the clock is within the tolerance of the mark, and after the clear the issue
        still waits for the mark (`clock-behind-mark`)."""
        skewed, true_time = "2026-11-07T12:10:00Z", MARK
        c = review_authorized(self.h)
        c.bind_receipt(S, REVIEWER, REVIEW_WORKTREE, REVIEW_BRANCH, ok_worktree)
        c.record_review(S, self.h.h.sha, "changes-requested", "r.md", self.h.terminal())
        self.h.clock[0] = skewed
        c.status()  # the forward-skewed observation is the mark
        self.h.clock[0] = true_time  # corrected: 10 minutes behind the mark
        refuses(self, lambda: c.authorize_repair(S), "clock-regression")
        self.assertEqual((stop_of(self.store)["code"], self.store.load_run().last_observed_at), ("clock-regression", skewed))
        self.h.clock[0] = "2026-11-07T12:04:59Z"  # one second outside the tolerance
        refuses(self, lambda: c.clear_clock_regression(clearance(self.h)), "clock-regression")
        self.assertEqual(stop_of(self.store)["code"], "clock-regression")  # waiting did not end it
        self.h.clock[0] = "2026-11-07T12:05:00Z"
        c.clear_clock_regression(clearance(self.h))
        self.assertEqual((stop_of(self.store), self.store.load_run().last_observed_at), (None, skewed))  # the mark is not lowered
        exc = refuses(self, lambda: c.authorize_repair(S), "clock-behind-mark")
        self.assertEqual(exc.detail["retry_at"], skewed)
        self.h.clock[0] = skewed
        self.assertEqual(c.authorize_repair(S).unresolved_authorization()["issued_at"], skewed)

    def test_a_field_named_issued_observed_at_is_never_read(self):
        """A value left in a story file by a build of PR #176 is not read: the check compares `issued_at`."""
        c, auth = self.repair_asked_for_behind_the_mark()
        story = self.store.load_story(S)
        story.authorization(auth["id"])["issued_observed_at"] = "2026-11-07T11:00:00Z"  # LABELLED MUTATION of the story file
        self.store.save_story(story)
        receipt, evidence = r5.ReconcileRevokedUnderClearableStopTests.evidence()
        exc = refuses(self, lambda: c.reconcile_retained_execution(S, auth["id"], {**receipt, "startedAt": "2026-11-07T11:30:00Z"}, evidence, "r", "p"), "run-precedes-authorization")
        self.assertEqual(exc.detail, {"started_at": "2026-11-07T11:30:00Z", "issued_at": MARK})

    def test_a_malformed_issued_at_refuses(self):
        c, auth = self.repair_asked_for_behind_the_mark()
        story = self.store.load_story(S)
        story.authorization(auth["id"])["issued_at"] = "not-a-time"  # LABELLED MUTATION of the story file
        self.store.save_story(story)
        receipt, evidence = r5.ReconcileRevokedUnderClearableStopTests.evidence()
        exc = refuses(self, lambda: c.reconcile_retained_execution(S, auth["id"], receipt, evidence, "r", "p"), "correlation-missing")
        self.assertIn("authorization.issued_at", str(exc))


class StampIsTheClockWithoutAStopTests(LiveCase):
    """PR #185 R1-3 (thread PRRT_kwDOVjxExc63YAdC): a state stamp is floored at the high-water mark
    only while a `clock-regression` stop is recorded (F9). With no stop it is the clock, equal to
    what the journal line and `updated_at` of the same operation record; after a clear it is the
    clock again. Mutation: `_floored` flooring without a recorded stop (the F9 extension restored)."""

    def test_without_a_stop_the_stamp_the_journal_line_and_updated_at_agree(self):
        c = claimed(self.h)
        self.h.clock[0] = MARK
        c.status()
        self.h.clock[0] = INSIDE  # 3 minutes behind the mark: no stop
        with mock.patch.object(state_module, "utcnow", return_value=INSIDE):  # the Store's wall clock is the same clock
            state = c.record_task_terminal(S, self.h.terminal())
        self.assertIsNone(stop_of(self.store))
        line = next(e for e in reversed(self.store.read_journal()) if e["event"] == "task-terminal")
        self.assertEqual((state.task_history[-1]["at"], line["detail"]["at"], line["at"], self.store.load_story(S).updated_at), (INSIDE, INSIDE, INSIDE, INSIDE))
        self.assertEqual(self.store.load_run().last_observed_at, MARK)

    def test_every_cleanup_stamp_is_the_clock_without_a_stop(self):
        c = review_authorized(self.h)
        self.h.clock[0] = MARK
        c.status()
        self.h.clock[0] = INSIDE
        refuses(self, lambda: c.cancel(S, "owner stops"), "authorization-unresolved")  # revokes the pending review authorization
        auth = self.store.load_story(S).unresolved_authorization()
        self.assertEqual(auth["revoked_at"], INSIDE)
        state = c.record_no_launch(S, {"authorization": auth["id"], "reason": "delegate_task was never called"})
        self.assertEqual(state.authorization(auth["id"])["resolved_at"], INSIDE)
        state = c.cancel(S, "owner stops")
        self.assertEqual(state.blocked["at"], INSIDE)
        release = state.intent("release")
        self.assertEqual((release.created_at, release.completed_at), (INSIDE, INSIDE))
        self.assertIsNone(stop_of(self.store))

    def test_under_a_stop_the_stamp_is_the_mark(self):
        """F9, unchanged: the other side of the rule, in the same scenario."""
        c = review_authorized(self.h)
        regress(self, self.h, c)
        refuses(self, lambda: c.cancel(S, "owner stops"), "authorization-unresolved")
        self.assertEqual(self.store.load_story(S).unresolved_authorization()["revoked_at"], MARK)
        with c.operation():
            c._reload_run()
            self.assertEqual((c._stamp(), c._floored(BEHIND), c._floored("2026-11-07T12:20:00Z")), (MARK, MARK, "2026-11-07T12:20:00Z"))

    def test_after_a_clear_the_stamp_is_the_clock_again(self):
        """The stated cost: a stamp written after a clear that ran inside the tolerance reads
        before one floored during the stop. Nothing orders state stamps but the run-order check on
        `issued_at` (PR #185 R2-2, thread PRRT_kwDOVjxExc63YqHy); list position does."""
        c = review_authorized(self.h)
        regress(self, self.h, c)
        refuses(self, lambda: c.cancel(S, "owner stops"), "authorization-unresolved")  # revoked during the stop: floored at the mark
        self.h.clock[0] = "2026-11-07T11:58:00Z"  # the clear runs inside the tolerance, still behind the mark
        c.clear_clock_regression(clearance(self.h))
        self.assertIsNone(stop_of(self.store))
        auth = self.store.load_story(S).unresolved_authorization()
        state = c.record_no_launch(S, {"authorization": auth["id"], "reason": "delegate_task was never called"})
        resolved = state.authorization(auth["id"])
        self.assertEqual((resolved["revoked_at"], resolved["resolved_at"]), (MARK, "2026-11-07T11:58:00Z"))

    def test_an_expired_stop_does_not_floor(self):
        """The floor has the F9 scope, the `clock-regression` stop. Under an `activation-expired`
        stop a later regression of the clock is not recorded (`_observe_stop` returns once a stop
        is recorded, as on `main`), so the clock may read behind the mark there, and the stamp is
        the clock, as on `main`."""
        c = claimed(self.h)
        with c.operation():
            c._reload_run()
            c.run.last_observed_at = MARK  # LABELLED MUTATION in memory
            c.run.activation_stop = {"code": "activation-expired", "observed_at": MARK, "message": "m", "operation": "status"}
            self.assertEqual(c._floored(INSIDE), INSIDE)
            c.run.activation_stop = {**c.run.activation_stop, "code": "clock-regression"}
            self.assertEqual(c._floored(INSIDE), MARK)
            c.run.activation_stop = None
            self.assertEqual(c._floored(INSIDE), INSIDE)


class DamagedRecordRuleSpendsNoApprovalTests(LiveCase):
    """PR #185 R1-4 (thread PRRT_kwDOVjxExc63YAdF): the damaged-record rule (`_recorded_dir_defect`,
    the `aborted` refusal that names no retry) is not changed; this is the evidence that it cannot
    spend an approval by mistake. It never fires on a record the tool wrote, whatever the state
    directory is called, and a record that was damaged is repaired by restoring the ledger file:
    the same creation is then retried under the same document."""

    def directories(self) -> list[tuple[str, str]]:
        base = Path(self.h.h.tmpdir.name)
        named = [("a space", os.fspath(base / "state dir")), ("non-ASCII", os.fspath(base / "stäte-дир-状態")),
                 ("a non-UTF-8 byte", os.fsdecode(os.fsencode(base) + b"/st\xffate")), ("a symlink", os.fspath(base / "link"))]
        for label, path in named:
            if label == "a symlink":
                os.mkdir(os.fspath(base / "link-target"))
                os.symlink(os.fspath(base / "link-target"), path)
            else:
                os.mkdir(path)
        return named

    def test_a_record_the_tool_wrote_has_no_defect_and_an_aborted_one_is_retried(self):
        ledger = ledger_path(self.h.activation.digest, self.h.activation.path)
        for label, state_dir in self.directories():
            with self.subTest(directory=label):
                written = record_activation_use(self.h.activation, state_dir, "run-live", T0)
                self.assertEqual(written["state_dir"], os.path.realpath(state_dir))
                on_file = record(self.h)  # read back from the ledger file, as every later operation reads it
                self.assertEqual((on_file["state"], on_file["state_dir"]), ("pending", os.path.realpath(state_dir)))
                self.assertIsNone(activation_module._recorded_dir_defect(on_file["state_dir"]))
                self.assertEqual(abort_activation_use(self.h.activation, state_dir, "run-live", Path(state_dir) / "run-live" / "run.json", cause=OSError(28, "No space left on device")), "aborted")
                aborted = record(self.h)
                self.assertEqual(aborted["state"], "aborted")
                message = use_refusal(aborted, ledger)
                self.assertIn("only that same creation may be retried (--run-id run-live --state-dir ", message)
                self.assertNotIn("damaged", message)
                self.assertTrue(activation_module._retryable_creation(aborted, state_dir, "run-live"))
                self.assertEqual([m for code, m in self.h.activation.creation_problems(self.h.h.policy, "run-live", T0, state_dir=state_dir) if code == "activation-used"], [])
                retried = record_activation_use(self.h.activation, aborted["state_dir"], "run-live", T0)  # the retry the refusal names
                self.assertEqual((retried["state"], len(retried["attempts"])), ("pending", 2))
                self.assertEqual(confirm_activation_use(self.h.activation.binding(validated_at=T0), state_dir, "run-live")[0], "committed")
                self.assertEqual(record(self.h)["state"], "committed")
                ledger.unlink()  # LABELLED RESET: the next directory starts from an unused document

    def aborted_creation(self) -> str:
        """An `aborted` record of this run written by the tool; the recorded state directory."""
        real = os.path.realpath(self.h.h.state_dir)
        record_activation_use(self.h.activation, real, "run-live", T0)
        self.assertEqual(abort_activation_use(self.h.activation, real, "run-live", Path(real) / "run-live" / "run.json", cause=OSError(28, "No space left on device")), "aborted")
        return real

    def assert_restored_record_creates_the_run(self) -> None:
        self.h.coordinator()  # the same creation, retried under the same document
        self.assertEqual((record(self.h)["state"], record(self.h)["run_id"], len(record(self.h)["attempts"])), ("committed", "run-live", 2))
        self.assertEqual(self.store.load_run().activation["digest"], self.h.activation.digest)
        self.assertEqual(self.events().count("run-started"), 1)

    def test_a_damaged_state_dir_restored_by_hand_is_retried(self):
        real = self.aborted_creation()
        for damaged in ("rel", real + "\0x", real + os.sep + "\ud800", 7):
            with self.subTest(damaged=damaged):
                set_ledger(self.h, state_dir=damaged)  # LABELLED MUTATION: the damage
                refused = refuses(self, lambda: self.h.coordinator(), "activation-used")
                self.assertNotIn("only that same creation may be retried", str(refused))
                self.assertIsNone(self.store.load_run())
        set_ledger(self.h, state_dir=real)  # restored by hand, as the refusal says
        self.assert_restored_record_creates_the_run()

    def test_a_damaged_state_restored_by_hand_is_retried(self):
        self.aborted_creation()
        for damaged in ("abortd", None, 3):
            with self.subTest(damaged=damaged):
                set_ledger(self.h, state=damaged)  # LABELLED MUTATION: the damage
                refused = refuses(self, lambda: self.h.coordinator(), "activation-used")
                self.assertIn("inspect or restore that file", str(refused))
                self.assertIsNone(self.store.load_run())
        set_ledger(self.h, state="aborted")  # restored by hand
        self.assert_restored_record_creates_the_run()


class LinesWrittenBeforeFieldStillDedupeTests(LiveCase):
    """PR #185 R1-5 (thread PRRT_kwDOVjxExc63YAdI), first half: a journal started before `field`
    existed holds `activation-use-unconfirmed` lines without
    `field`, whose variant is in `strerror` (`unreadable`, `recorded directory exists`, `recorded
    directory gone`, or the name of the field that failed validation). After the upgrade the same
    condition, still present, adds no line; a different condition is still journaled. Mutation:
    `_legacy_unconfirmed_key` returning `None` (the old-line mapping removed)."""

    def setUp(self):
        super().setUp()
        self.h.coordinator()
        self.recorded = Path(self.h.h.tmpdir.name) / "created-under"
        self.ledger = ledger_path(self.h.activation.digest, self.h.activation.path)

    def legacy_line(self, kind: str, strerror: str) -> None:
        """A line of the format before `field`: `{error, type, errno, strerror, consequence}`."""
        self.store.journal(None, "activation-use-unconfirmed", {"error": "as it was worded then", "type": kind, "errno": None, "strerror": strerror,
                                                              "consequence": "the use ledger record stays pending; every later open retries the confirmation; until then a deleted run directory refuses as an unconfirmed creation"})

    def new_lines(self) -> list[tuple]:
        self.h.coordinator(activation=None)
        self.h.coordinator(activation=None)  # a second open adds nothing either way
        return [(d["type"], d["field"]) for d in unconfirmed(self.store) if "field" in d]

    def reading_fails(self, error: OSError):
        return VariantFieldAndReadErrnoTests.reading_fails(self, error)

    def test_an_unreadable_file_on_record_covers_a_torn_file(self):
        self.legacy_line("ledger-unreadable", "unreadable")
        self.ledger.write_text("{torn", encoding="utf-8")  # LABELLED MUTATION
        self.assertEqual(self.new_lines(), [])

    def test_an_unreadable_file_on_record_covers_a_refused_read(self):
        self.legacy_line("ledger-unreadable", "unreadable")
        with self.reading_fails(PermissionError(13, "Permission denied")):
            self.assertEqual(self.new_lines(), [])

    def test_a_directory_that_exists_on_record_covers_the_run_and_a_directory_without_it(self):
        self.legacy_line("state-dir-mismatch", "recorded directory exists")
        set_ledger(self.h, state="pending", state_dir=str(self.recorded))
        self.recorded.mkdir()
        self.assertEqual(self.new_lines(), [])  # exists without the run
        (self.recorded / "run-live").mkdir()
        (self.recorded / "run-live" / "run.json").write_text("{}", encoding="utf-8")
        self.assertEqual(self.new_lines(), [])  # holds the run

    def test_a_directory_that_is_gone_on_record_covers_what_was_called_gone(self):
        self.legacy_line("state-dir-mismatch", "recorded directory gone")
        set_ledger(self.h, state="pending", state_dir=str(self.recorded))
        self.assertEqual(self.new_lines(), [])  # gone
        with stat_refusing(self.recorded, PermissionError(13, "Permission denied")):
            self.assertEqual(self.new_lines(), [])  # cannot be examined, and `os.path.isdir` is false for it, as it was then
        self.recorded.write_text("a file", encoding="utf-8")
        self.assertEqual(self.new_lines(), [])  # exists, and is not a directory: `os.path.isdir` is false, as it was then

    def test_a_field_name_on_record_still_covers_that_field(self):
        self.legacy_line("ledger-unreadable", "attempts")
        set_ledger(self.h, state="pending", attempts="x")
        self.assertEqual(self.new_lines(), [])

    def test_a_different_condition_is_still_journaled(self):
        cases = [(("state-dir-mismatch", "recorded directory gone"), "holds", ("state-dir-mismatch", "recorded directory holds the run")),
                 (("state-dir-mismatch", "recorded directory gone"), "directory", ("state-dir-mismatch", "recorded path exists without the run")),
                 (("state-dir-mismatch", "recorded directory exists"), "gone", ("state-dir-mismatch", "recorded directory gone")),
                 (("state-dir-mismatch", "recorded directory exists"), "file", ("state-dir-mismatch", "recorded path exists without the run")),
                 (("ledger-unreadable", "unreadable"), "state_dir", ("ledger-unreadable", "state_dir")),
                 (("ledger-unreadable", "unreadable"), "state", ("ledger-unreadable", "state")),  # `state` was not validated then: no old line stands for it
                 (("ledger-unreadable", "state_dir"), "torn", ("ledger-unreadable", "json"))]  # last: the ledger file is not JSON afterwards
        for number, (on_record, now, expected) in enumerate(cases):
            with self.subTest(on_record=on_record, now=now):
                self.store.journal(None, "activation-use-confirmed", {})  # each case starts after a confirmation
                self.legacy_line(*on_record)
                recorded = Path(self.h.h.tmpdir.name) / f"created-under-{number}"
                set_ledger(self.h, state="pending", state_dir=str(recorded), attempts=[{"at": T0}])
                if now in ("holds", "directory"):
                    (recorded / ("run-live" if now == "holds" else "run-else")).mkdir(parents=True)
                    (recorded / ("run-live" if now == "holds" else "run-else") / "run.json").write_text("{}", encoding="utf-8")
                elif now == "file":
                    recorded.write_text("a file", encoding="utf-8")
                elif now == "state_dir":
                    set_ledger(self.h, state_dir=7)
                elif now == "state":
                    set_ledger(self.h, state="unknown")
                elif now == "torn":
                    self.ledger.write_text("{torn", encoding="utf-8")  # LABELLED MUTATION
                before = len(unconfirmed(self.store))
                self.h.coordinator(activation=None)
                self.h.coordinator(activation=None)
                added = unconfirmed(self.store)[before:]  # past the old line this case wrote
                self.assertEqual([(d["type"], d["field"]) for d in added], [expected])

    def test_the_key_the_old_format_wrote_for_each_condition(self):
        key = Store._legacy_unconfirmed_key
        sdm, lu = "state-dir-mismatch", "ledger-unreadable"
        self.assertEqual(key({"type": lu, "errno": 13, "strerror": "Permission denied", "field": "file"}), (lu, None, "unreadable"))
        self.assertEqual(key({"type": lu, "errno": None, "strerror": None, "field": "json"}), (lu, None, "unreadable"))
        for name in ("record", "attempts", "state_dir"):
            self.assertEqual(key({"type": lu, "errno": None, "strerror": None, "field": name}), (lu, None, name))
        self.assertIsNone(key({"type": lu, "errno": None, "strerror": None, "field": "state"}))
        for field in activation_module.RECORDED_RUN_VARIANTS.values():  # the flag alone decides, whatever the present variant is
            self.assertEqual(key({"type": sdm, "errno": None, "field": field, "recorded_is_dir": True}), (sdm, None, "recorded directory exists"))
            self.assertEqual(key({"type": sdm, "errno": 13, "field": field, "recorded_is_dir": False}), (sdm, None, "recorded directory gone"))
            self.assertIsNone(key({"type": sdm, "errno": None, "field": field, "recorded_is_dir": None}))  # no usable path: what the old code wrote cannot be told
            self.assertIsNone(key({"type": sdm, "errno": None, "field": field}))
        self.assertEqual(key({"type": "OSError", "errno": 28, "strerror": None, "field": None}), ("OSError", 28, None))  # a failed write: the key did not change
        self.assertEqual(key({"type": "OSError", "errno": None, "strerror": "odd", "field": None}), ("OSError", None, "odd"))

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root searches every directory")
    def test_a_directory_that_exists_on_record_covers_one_that_cannot_be_searched(self):
        """An existing directory without search permission "cannot be examined" now; the old code
        asked `os.path.isdir`, which is true for it, and wrote "recorded directory exists".
        Mutation: `recorded_is_dir` forced `False` unless the run or a directory without it was found."""
        self.legacy_line("state-dir-mismatch", "recorded directory exists")
        set_ledger(self.h, state="pending", state_dir=str(self.recorded))
        self.recorded.mkdir()
        self.recorded.chmod(0)
        try:
            outcome, error = confirm_activation_use(self.store.load_run().activation, self.h.h.state_dir, "run-live")
            added = self.new_lines()
        finally:
            self.recorded.chmod(0o700)  # before the harness removes the directory
        self.assertEqual((outcome, error["field"], error["errno"], error["recorded_is_dir"]), ("error", "recorded directory cannot be examined", errno.EACCES, True))
        self.assertEqual(added, [])

    def test_a_recorded_value_that_is_no_usable_path_matches_no_old_line(self):
        """The old code resolved a relative value against the current directory, so what it wrote
        for a damaged value cannot be reproduced: the flag is `None`, no old line stands for the
        condition and the damaged record is journaled once after an upgrade. Mutation: the flag
        `False` for such a value (an old "gone" line would suppress the damaged-record line)."""
        here = Path(self.h.h.tmpdir.name)
        (here / "rel").mkdir()
        real = os.path.realpath(self.h.h.state_dir)
        for damaged in ("rel", real + "\0x", real + os.sep + "\ud800"):
            with self.subTest(damaged=damaged):
                self.store.journal(None, "activation-use-confirmed", {})  # each case starts after a confirmation
                self.legacy_line("state-dir-mismatch", "recorded directory gone")
                self.legacy_line("state-dir-mismatch", "recorded directory exists")
                set_ledger(self.h, state="pending", state_dir=damaged)
                with contextlib.chdir(here):  # the relative value lines up with a directory: it is still not asked about
                    _, error = confirm_activation_use(self.store.load_run().activation, self.h.h.state_dir, "run-live")
                    self.assertEqual((error["field"], error["recorded_is_dir"]), ("recorded directory cannot be examined", None))
                    before = len(unconfirmed(self.store))
                    self.h.coordinator(activation=None)
                    self.h.coordinator(activation=None)
                added = unconfirmed(self.store)[before:]
                self.assertEqual([(d["type"], d["field"]) for d in added], [("state-dir-mismatch", "recorded directory cannot be examined")])
                self.assertIn("the use ledger record is damaged", added[0]["consequence"])

    def test_a_line_with_field_never_stands_for_another_variant_of_its_old_class(self):
        """Only a line without `field` is matched through the old key. A present-format "gone"
        line and a later file at that path are two conditions of one old class ("gone"): both are
        journaled. Mutation: the `"field" not in d` filter removed."""
        set_ledger(self.h, state="pending", state_dir=str(self.recorded))
        self.h.coordinator(activation=None)
        self.recorded.write_text("a file", encoding="utf-8")
        self.h.coordinator(activation=None)
        self.assertEqual([(d["type"], d["field"]) for d in unconfirmed(self.store)],
                         [("state-dir-mismatch", "recorded directory gone"), ("state-dir-mismatch", "recorded path exists without the run")])

    def test_recorded_is_dir_never_reaches_the_journal(self):
        """The exact keys of a journaled `state-dir-mismatch` line. Mutation: the flag copied into the line."""
        for make in (lambda: None, self.recorded.mkdir, lambda: ((self.recorded / "run-live").mkdir(), (self.recorded / "run-live" / "run.json").write_text("{}", encoding="utf-8"))):
            make()
            set_ledger(self.h, state="pending", state_dir=str(self.recorded))
            self.h.coordinator(activation=None)
        lines = [d for d in unconfirmed(self.store) if d["type"] == "state-dir-mismatch"]
        self.assertEqual(len(lines), 3)
        for line in lines:
            self.assertEqual(set(line), {"error", "type", "errno", "strerror", "field", "consequence"})

    def test_one_old_line_covers_every_later_variant_of_its_class_until_a_confirmation(self):
        """The stated caveat for a journal started before `field`: an old `unreadable` line does not
        say which condition it recorded, so a later EACCES and a later EIO add no line; after the
        next confirmation they are two lines again."""
        self.legacy_line("ledger-unreadable", "unreadable")
        for error in (PermissionError(13, "Permission denied"), OSError(5, "Input/output error")):
            with self.reading_fails(error):
                self.assertEqual(self.new_lines(), [])
        self.store.journal(None, "activation-use-confirmed", {})
        for error in (PermissionError(13, "Permission denied"), OSError(5, "Input/output error")):
            with self.reading_fails(error):
                self.h.coordinator(activation=None)
        self.assertEqual([(d["field"], d["errno"]) for d in unconfirmed(self.store) if "field" in d], [("file", 13), ("file", 5)])

    def test_a_failed_write_on_record_still_covers_the_same_failed_write(self):
        self.store.journal(None, "activation-use-unconfirmed", {"error": "OSError: [Errno 28] ...", "type": "OSError", "errno": 28, "strerror": None, "consequence": "c"})
        set_ledger(self.h, state="pending")
        with mock.patch.object(activation_module, "_write_ledger", side_effect=OSError(28, "No space left on device")):
            self.assertEqual(self.new_lines(), [])
        with mock.patch.object(activation_module, "_write_ledger", side_effect=OSError(30, "Read-only file system")):
            self.assertEqual(self.new_lines(), [("OSError", None)])  # another errno is another condition


class AbandonedGitIsReapedTests(unittest.TestCase):
    """PR #185 R1-5 (thread PRRT_kwDOVjxExc63YAdI), second half: a git that survives SIGKILL past
    the bounded wait still raises `TimeoutExpired` within the bound, and is handed to a daemon
    thread that waits for it, so it is reaped when it does exit. Mutation: the `_reap_abandoned`
    call removed from `_git_answer`."""

    def stuck(self, exits_after_kill: bool = False) -> "StuckGitIsBoundedTests.Stuck":
        child = StuckGitIsBoundedTests.Stuck(exits_after_kill)
        self.addCleanup(child.exited.set)  # registered before anything can start a reaper: no assertion below can leave one waiting
        return child

    def test_a_child_that_survives_the_kill_is_waited_for_on_a_daemon_thread(self):
        child = self.stuck()
        with mock.patch.object(cli_module.subprocess, "Popen", return_value=child):
            with self.assertRaises(subprocess.TimeoutExpired):
                cli_module._git_answer(["git", "status"], timeout=30, env={})
        (reaper,) = reapers_of(child)
        self.assertTrue(reaper.daemon)  # it never keeps the interpreter alive
        self.assertTrue(reaper.is_alive())  # the child has not exited: it is still being waited for
        self.assertEqual(child.calls[:3], [("communicate", 30), ("kill", None), ("wait", cli_module.GIT_KILL_WAIT_SECONDS)])
        child.exited.set()  # the mount answers and the child dies
        reaper.join(timeout=10)
        self.assertFalse(reaper.is_alive())
        self.assertEqual(child.calls, [("communicate", 30), ("kill", None), ("wait", cli_module.GIT_KILL_WAIT_SECONDS), ("wait", None)])

    def test_a_child_that_dies_within_the_bound_needs_no_reaper(self):
        child = self.stuck(exits_after_kill=True)
        with mock.patch.object(cli_module.subprocess, "Popen", return_value=child), mock.patch.object(cli_module, "_reap_abandoned", side_effect=AssertionError("already reaped")):
            with self.assertRaises(subprocess.TimeoutExpired):
                cli_module._git_answer(["git", "status"], timeout=30, env={})
        self.assertEqual(child.calls, [("communicate", 30), ("kill", None), ("wait", 5)])

    def test_an_interrupted_call_reaps_an_abandoned_child_too(self):
        child = self.stuck()
        child.communicate = lambda timeout=None: (_ for _ in ()).throw(KeyboardInterrupt())
        with mock.patch.object(cli_module.subprocess, "Popen", return_value=child):
            with self.assertRaises(KeyboardInterrupt):
                cli_module._git_answer(["git", "status"], timeout=30, env={})
        reapers = reapers_of(child)
        self.assertEqual(len(reapers), 1)
        child.exited.set()
        reapers[0].join(timeout=10)
        self.assertEqual(child.calls, [("kill", None), ("wait", 5), ("wait", None)])

    def test_a_reaper_that_cannot_be_started_replaces_nothing_and_the_pipes_are_closed(self):
        """`Thread.start` raises `RuntimeError` when no thread can be started. The child is then
        left to the kernel: what was raised (the timeout, or an interrupt) is still what is raised,
        and both pipes are closed. Mutations: the `RuntimeError` guard removed; the pipes closed
        only when the reaper started."""
        for raised, communicate in ((subprocess.TimeoutExpired, None), (KeyboardInterrupt, lambda timeout=None: (_ for _ in ()).throw(KeyboardInterrupt()))):
            with self.subTest(raised=raised.__name__):
                child = self.stuck()
                if communicate is not None:
                    child.communicate = communicate
                with mock.patch.object(cli_module.subprocess, "Popen", return_value=child), \
                        mock.patch.object(cli_module, "_reap_abandoned", side_effect=RuntimeError("can't start new thread")) as reap:
                    with self.assertRaises(raised):
                        cli_module._git_answer(["git", "status"], timeout=30, env={})
                self.assertEqual(reap.call_count, 1)
                self.assertEqual((child.stdout.close.call_count, child.stderr.close.call_count), (2, 2))  # one mock stands for both pipes: each was closed
                self.assertEqual(reapers_of(child), [])

    INTERRUPT = staticmethod(lambda timeout=None: (_ for _ in ()).throw(KeyboardInterrupt()))

    def test_a_kill_that_raises_replaces_nothing(self):
        """A refused `kill` is ignored: the bounded wait still runs, the pipes are closed and what
        ended the wait for the answer (the timeout, or an interrupt) is what is raised.
        Mutation: the `OSError` guard around `proc.kill()` removed."""
        for raised, communicate in ((subprocess.TimeoutExpired, None), (KeyboardInterrupt, self.INTERRUPT)):
            with self.subTest(raised=raised.__name__):
                child = self.stuck(exits_after_kill=True)
                if communicate is not None:
                    child.communicate = communicate
                child.kill = mock.Mock(side_effect=PermissionError(1, "Operation not permitted"))
                with mock.patch.object(cli_module.subprocess, "Popen", return_value=child):
                    with self.assertRaises(raised):
                        cli_module._git_answer(["git", "status"], timeout=30, env={})
                self.assertEqual((child.kill.call_count, child.calls[-1], child.stdout.close.call_count), (1, ("wait", 5), 2))

    def test_a_second_interrupt_during_the_bounded_wait_still_leaves_a_reaper(self):
        """The bounded wait is interrupted: that interrupt propagates (not the timeout it
        interrupted), the child is handed to the reaper and the pipes are closed. Mutation: the
        reaper started only on the wait's own `TimeoutExpired`."""
        child = self.stuck()
        bounded = child.wait

        def wait(timeout=None):
            if timeout is None:
                return bounded(timeout)
            child.calls.append(("wait", timeout))
            raise KeyboardInterrupt()

        child.wait = wait
        with mock.patch.object(cli_module.subprocess, "Popen", return_value=child):
            with self.assertRaises(KeyboardInterrupt):
                cli_module._git_answer(["git", "status"], timeout=30, env={})
        reapers = reapers_of(child)
        self.assertEqual((len(reapers), child.stdout.close.call_count), (1, 2))
        child.exited.set()
        reapers[0].join(timeout=10)
        self.assertEqual(child.calls, [("communicate", 30), ("kill", None), ("wait", 5), ("wait", None)])

    def test_a_real_child_is_reaped_when_it_exits(self):
        """The thread's wait collects a real exit status: the child is no zombie afterwards."""
        proc = subprocess.Popen(["sleep", "60"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        reaper = cli_module._reap_abandoned(proc)
        self.addCleanup(proc.kill)
        self.assertEqual((reaper.daemon, reaper.name, reaper.is_alive()), (True, f"reap-git-{proc.pid}", True))
        proc.kill()
        reaper.join(timeout=10)
        self.assertFalse(reaper.is_alive())
        self.assertEqual(proc.returncode, -9)  # collected by the thread, not by this test
        with self.assertRaises(ChildProcessError):
            os.waitpid(proc.pid, os.WNOHANG)  # nothing is left to reap


# -- the documentation ------------------------------------------------------------------------------------------------------
class DocumentedTests(unittest.TestCase):
    """The guide describes every changed event detail and report field, and the README names this file."""

    def test_the_guide_names_the_changed_details_and_fields(self):
        text = DOCS.read_text(encoding="utf-8")
        for needle in ("`field`", "`consequence`", "`presented_current`", "`clear_requires`", "`recovered: true`", "recorded directory cannot be examined", "`issues/0`", "5 seconds"):
            self.assertIn(needle, text, needle)
        self.assertNotIn("an `OSError` without an errno told apart by its `strerror`: the message names", text)

    def test_the_guide_states_the_stamp_rule(self):
        """PR #185 R1-3: one rule, a stamp is the clock except under a recorded `clock-regression`
        stop; the stamps it covers are still listed, and the cost after a clear is stated."""
        text = " ".join(DOCS.read_text(encoding="utf-8").split())
        for needle in ("every state stamp the coordinator writes is the clock, except while a `clock-regression` stop is recorded",
                       "an intent's `created_at` and `completed_at`", "`bound_at` and `claim.claimed_at` of a cleanup bind",
                       "`claim.reserved_at`, `checks[].at`, `reviews[].at`, `proposal.at`", "are therefore always the clock",
                       "a stamp can read up to 5 minutes before one that was floored during the stop",
                       "No code orders or compares state stamps, with one exception: the run-order check of `reconcile-retained-execution` compares an authorization's `issued_at` with the run's `startedAt`",
                       "`reconciliation.observed_at` keeps what the regressed clock read; it is recorded only under a clock stop"):
            with self.subTest(needle=needle):
                self.assertIn(needle, text)
        for gone in ("whether or not a stop is recorded and whichever operation writes it", "One stamp is an exception", "without one only when `reconciliation.at` was floored",
                     "one story therefore never holds a floored entry followed by an earlier one"):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, text)

    def test_the_guide_states_what_the_run_order_check_compares(self):
        """PR #185 R1-2: the reconcile section names the one comparison the code makes, with no accepted window before the issue."""
        text = " ".join(DOCS.read_text(encoding="utf-8").split())
        for needle in ("`startedAt` at or after the authorization's `issued_at`", "`issued_at` is the clock as it read when the authorization was issued and is never before the run's high-water mark as it stood at the issue",
                       "a run that started at a reading before that mark settles nothing", "A later gate that reads after the mark, with no stop recorded, raises it, so a stored `issued_at` is usually before the mark as later operations leave it (`last_observed_at` in `run.json`)",  # PR #185 R3-2, thread PRRT_kwDOVjxExc63Y0Ep
                       "The mark is moved only by an operation's gate and by `clear-clock-regression` (to the later of the clock and the mark)",  # PR #185 R3-1, thread PRRT_kwDOVjxExc63Y0El
                       "it compares two clock readings, not the order in which the two things happened",
                       "Narrowed, not closed: a clock that steps back before the issue and still reads at or after the mark dates the authorization before the `startedAt` of a run that really started earlier, and the check accepts that run",
                       "do not raise it (#181)", "The step back has no bound of its own",
                       "a clock that is back at or after the mark by the next operation shows neither"):
            with self.subTest(needle=needle):
                self.assertIn(needle, text)
        for gone in ("Such a step back is smaller than", "has no window before the issue in which a run is accepted", "no authorization is dated before a run that started earlier", "is accepted by design", "The mark is moved only by an operation's gate;", "that `status` reports afterwards", "cannot be told from one that started after the issue", "when `issued_at` was floored", "compared_with"):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, text)

    def test_the_guide_states_that_nothing_is_issued_before_the_mark_and_no_stop_is_recorded_for_it(self):
        """PR #185 R1-1: one observation per operation decides; a reading before the mark at the issue refuses `clock-behind-mark`."""
        text = " ".join(DOCS.read_text(encoding="utf-8").split())
        for needle in ("No later reading of the same operation is judged for a stop", "refuses `clock-behind-mark`: nothing is issued, journaled or posted, nothing of the story, the budgets or GitHub changes and no stop is recorded (the operation's gate, which ran first, may already have recorded its observation's time in `run.json`, and that time is then the mark the refusal names); the refusal carries",
                       "would be issued; nothing is issued, journaled or posted, nothing of the story, the budgets or GitHub changes and no stop is recorded (the operation's gate, which ran first, may already have recorded its observation's time in `run.json`, and that time is then the mark the refusal names); detail",
                       "the gate of the next operation judges the clock", "| `clock-behind-mark` | `reserve`, `authorize-review`, `authorize-repair` |", "`retry_at` (the mark)",
                       "whenever the clock reads before the mark", "the caller retries at `retry_at`", "`check-activation` (`current`, `--expect advance`) and `status` do not report this temporary refusal",
                       "A reading or a mark that cannot be parsed refuses `activation-invalid`",
                       "Unchanged: a clock that steps back after the issue makes a genuine run start before `issued_at`"):
            with self.subTest(needle=needle):
                self.assertIn(needle, text)
        for gone in ("saved, journaled or posted", "One later reading is also judged for a regression", "records `clock-regression` and issues nothing", "That stop names the command as its `operation`", "`wait_until` (the mark)"):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, text)

    def test_the_guide_states_the_caveats_of_the_stamp_rule_and_of_the_old_lines(self):
        text = " ".join(DOCS.read_text(encoding="utf-8").split())
        for needle in ("writes stamps that read earlier than previous ones", "Under an `activation-expired` stop a later regression of the clock is not recorded",
                       "a reading taken later in the same operation is not judged", "the same clock, read separately",
                       "one old line suppresses every later variant of its class until the next confirmation", "keeps the `consequence` text of the old line",
                       "A recorded value that is no usable path matches no old line"):
            with self.subTest(needle=needle):
                self.assertIn(needle, text)
        for gone in ("by `main`", "`main` wrote", "`main` keyed", "397c783", "all three are the clock"):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, text)

    def test_the_guide_records_the_five_decisions_after_the_walkthrough(self):
        """PR #185 round 1: each risk the owner did not accept has its decision in the guide, and the
        field the first three removed is named there only."""
        text = " ".join(DOCS.read_text(encoding="utf-8").split())
        self.assertIn("**Decisions after the walkthrough (PR #185, round 1).**", text)
        start = text.index("**Decisions after the walkthrough (PR #185, round 1).**")
        paragraph = text[start:text.index("- **Trust model.**", start)]
        for needle in ("PR #176, continued as PR #185", "R1-1", "R1-2", "R1-3", "R1-4", "R1-5", "`issued_observed_at`", "`clock-behind-mark`", "not changed", "a daemon thread", "`recorded directory exists`"):
            with self.subTest(needle=needle):
                self.assertIn(needle, paragraph)
        for needle in ("That narrows the risk and does not close it (review round 2, R2-1)", "nothing orders state stamps except the run-order check, which compares `issued_at`",
                       "the run-order check is the one comparison of a state stamp (R2-2)", "can follow a gate that already saved its observation in `run.json` (R2-3)"):  # PR #185 round 2
            with self.subTest(needle=needle):
                self.assertIn(needle, paragraph)
        for needle in ("so no authorization is dated before the mark as it stood at the issue",
                       "after a forward-skewed observation of up to 5 minutes it is as long as the skew was",
                       "A larger skew is waited out the same way only when no gate runs while the clock reads more than 5 minutes behind the mark",
                       "the run advances again only after `clear-clock-regression` (described above: owner by convention, once per run, refused until the clock reads within 5 minutes of the mark; the mark is not lowered, so issuing still waits for the clock to reach it)",
                       "A forward-skewed observation past `expires_at` or past the wall-clock budget is not a wait at all",  # PR #185 R3-3, thread PRRT_kwDOVjxExc63Y0Eq
                       "the round 2 corrections are pinned in the R1-1 to R1-3 classes and in its documentation tests",  # PR #185 R3-4, thread PRRT_kwDOVjxExc63Y0Es
                       "Round 3 changed no behaviour", "Its tests are in the R1-2 class and the documentation tests"):
            with self.subTest(needle=needle):
                self.assertIn(needle, paragraph)
        for gone in ("dated before the mark and a run", "after a forward-skewed observation it is as long as the skew was", "pinned in the same classes", "is not waited out", "only the owner's clear ends"):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, paragraph)
        self.assertEqual(text.count("issued_observed_at"), paragraph.count("issued_observed_at"))  # named in the decision text only
        readme = README.read_text(encoding="utf-8")
        for needle in ("round 1 of PR #185", "R1-1 to R1-5", "R2-1 to R2-3", "R3-1 to R3-5",
                       "(R1-5 has two); the R1-1 to R1-3 classes and the documentation tests also carry the corrections of review round 2",
                       "the R1-2 class and the documentation tests those of round 3",
                       "never before the mark as it stood at the issue"):
            with self.subTest(needle=needle):
                self.assertIn(needle, readme)
        self.assertNotIn("they also carry the corrections", readme)  # PR #185 R3-4: the R1-5 classes hold no round 2 pin

    def test_the_readme_names_this_file(self):
        self.assertIn("tests/test_pr114_round7_findings.py", README.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
