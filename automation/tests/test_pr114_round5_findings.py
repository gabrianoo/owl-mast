"""Regressions for PR #114 round 5: review 5861377408 (21 threads). One class per finding (thread
suffix of ``PRRT_kwDOVjxExc62Pk…`` in the docstring), each test named after the behaviour it pins.
Every scenario runs on the fixture transport marked live with temporary state and an injected
clock; no real GitHub call and no real task is ever made, and no test writes to the real use
ledger under the home directory."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from automation.tests.support import IMPLEMENTER, REVIEW_BRANCH, REVIEW_WORKTREE, REVIEWER, controlled_cli_clock, ok_worktree, run_of
from automation.tests.test_activation import S, T0, LiveHarness
from automation.tests.test_enabling_repair_1 import claimed, refuses
from automation.tests.test_pr108_review_findings import cli_args, no_gh_calls, review_authorized, run_cli
from automation.tests.test_pr114_review_findings import LiveCase, clearance, regress
from automation.tests.test_pr114_round3_findings import ClearableClockStopTests, record, write_clearance
from automation.tests.test_pr114_round4_findings import ClearanceLocationCase, git, stop_of
from automation.unattended import activation as activation_module
from automation.unattended import cli as cli_module
from automation.unattended import state as state_module
from automation.unattended.activation import Activation, _retryable_creation, _same_run, abort_activation_use, activation_use, ledger_path, load_activation, load_clearance, record_activation_use
from automation.unattended.coordinator import Coordinator
from automation.unattended.errors import Refused
from automation.unattended.state import Store

REPO = "gabrianoo/owl-mast"
OWNER = IMPLEMENTER["taskId"]
DOCS = Path(__file__).resolve().parents[2] / "docs" / "unattended-execution.md"
AS_ROOT = hasattr(os, "geteuid") and os.geteuid() == 0


def completed(rc: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(["git"], rc, stdout=stdout, stderr=stderr)


def set_ledger(h: LiveHarness, **fields) -> dict:
    path = ledger_path(h.activation.digest, h.activation.path)
    data = {**json.loads(path.read_text(encoding="utf-8")), **fields}
    path.write_text(json.dumps(data), encoding="utf-8")  # LABELLED MUTATION of the ledger record
    return data


# -- OE: a dangling gitfile, an ancestor .git ---------------------------------------------------------------------------
class DanglingGitfileTests(ClearanceLocationCase):
    """Only git's plain discovery failure means "outside every work tree"; a `.git` entry above the
    clearance refuses whatever git makes of it (thread OE)."""

    def dangling(self) -> Path:
        folder = self.tmp / "pruned-worktree"
        folder.mkdir()
        (folder / ".git").write_text("gitdir: /nonexistent/.git/worktrees/x\n", encoding="utf-8")
        return folder

    def test_a_dangling_gitfile_is_not_a_not_a_work_tree_answer(self):
        with self.assertRaises(cli_module.WorkTreeUnknown):
            cli_module._work_tree(self.dangling())

    def test_a_clearance_beside_a_dangling_gitfile_is_refused(self):
        self.assert_refused(self.clear(write_clearance(self.dangling() / "notes" / "clearance.toml", self.h)))

    def test_an_ancestor_with_any_git_entry_refuses_even_when_git_says_not_a_repository(self):
        folder = self.tmp / "odd"
        (folder / ".git").mkdir(parents=True)  # an empty .git directory: git ignores it and keeps walking
        inside = write_clearance(folder / "deep" / "notes" / "clearance.toml", self.h)
        self.assertIsNone(cli_module._work_tree(inside.parent))  # git's own answer allows ...
        error = self.assert_refused(self.clear(inside))  # ... the ancestor rule does not
        self.assertIn(".git entry", error["message"])

    def test_a_stop_at_a_file_system_boundary_is_not_the_allowing_answer(self):
        boundary = completed(128, stderr="fatal: not a git repository (or any parent up to mount point /tmp)\nStopping at filesystem boundary (GIT_DISCOVERY_ACROSS_FILESYSTEM not set).\n")
        with mock.patch.object(cli_module.subprocess, "run", return_value=boundary):
            with self.assertRaises(cli_module.WorkTreeUnknown):
                cli_module._work_tree(self.outside.parent)

    def test_a_warning_before_the_plain_answer_still_allows(self):
        warned = completed(128, stderr="warning: unable to access '/home/x/.config/git/config': Permission denied\nfatal: not a git repository (or any of the parent directories): .git\n")
        with mock.patch.object(cli_module.subprocess, "run", return_value=warned):
            self.assertIsNone(cli_module._work_tree(self.outside.parent))

    def test_an_ancestor_git_entry_that_cannot_be_examined_refuses(self):
        original = os.lstat

        def lstat(path, *args, **kwargs):
            if os.path.basename(os.fspath(path)) == ".git":
                raise PermissionError(13, "Permission denied", os.fspath(path))
            return original(path, *args, **kwargs)

        with mock.patch.object(cli_module.os, "lstat", lstat):
            error = self.assert_refused(self.clear(self.outside))
        self.assertIn("cannot determine whether", error["message"])

    def test_git_walks_across_file_systems(self):
        self.assertEqual(cli_module._git_env()["GIT_DISCOVERY_ACROSS_FILESYSTEM"], "1")
        with mock.patch.object(cli_module.subprocess, "run", return_value=completed(128, stderr="fatal: not a git repository (or any of the parent directories): .git\n")) as run:
            self.assertIsNone(cli_module._work_tree(self.outside.parent))
        self.assertEqual(run.call_args.kwargs["env"]["GIT_DISCOVERY_ACROSS_FILESYSTEM"], "1")


# -- P1: the tri-state ----------------------------------------------------------------------------------------------------
class WorkTreeTriStateTests(ClearanceLocationCase):
    """An empty answer and a non-128 exit are unknown, never "outside" (thread P1)."""

    def test_exit_zero_with_an_empty_answer_refuses(self):
        with mock.patch.object(cli_module.subprocess, "run", return_value=completed(0, stdout="\n")):
            with self.assertRaises(cli_module.WorkTreeUnknown):
                cli_module._work_tree(self.outside.parent)
            self.assert_refused(self.clear(self.outside))

    def test_another_exit_code_with_the_not_a_repository_message_refuses(self):
        with mock.patch.object(cli_module.subprocess, "run", return_value=completed(1, stderr="fatal: not a git repository (or any of the parent directories): .git")):
            with self.assertRaises(cli_module.WorkTreeUnknown):
                cli_module._work_tree(self.outside.parent)
            self.assert_refused(self.clear(self.outside))


# -- Pp: the locale -------------------------------------------------------------------------------------------------------
class GitLocaleTests(unittest.TestCase):
    """git runs in the C locale, so a translated message never turns "outside" into "unknown" (thread Pp).
    The fake git answers in German unless it runs under ``LC_ALL=C``, as a translated git would."""

    @staticmethod
    def translated_git(args, **kwargs):
        if (kwargs.get("env") or {}).get("LC_ALL") == "C":
            return completed(128, stderr="fatal: not a git repository (or any of the parent directories): .git\n")
        return completed(128, stderr="fatal: Kein Git-Repository (oder irgendeines der Elternverzeichnisse): .git\n")

    def test_a_translated_git_still_answers_not_a_work_tree(self):
        with mock.patch.dict(os.environ, {"LANG": "de_DE.UTF-8", "LC_ALL": "de_DE.UTF-8", "LANGUAGE": "de"}), mock.patch.object(cli_module.subprocess, "run", side_effect=self.translated_git):
            self.assertIsNone(cli_module._work_tree("/anywhere"))


# -- O6: what kind of path the clearance is --------------------------------------------------------------------------------
class ClearancePathKindTests(ClearanceLocationCase):
    """A clearance that is not a readable regular file is reported as what it is (thread O6)."""

    def test_a_missing_file_is_no_such_file(self):
        self.assertIn("no such file", self.assert_refused(self.clear(self.tmp / "owner" / "missing.toml"))["message"])

    def test_a_directory_is_not_a_regular_file(self):
        folder = self.tmp / "owner" / "a-directory.toml"
        folder.mkdir()
        message = self.assert_refused(self.clear(folder))["message"]
        self.assertIn("not a regular file", message)
        self.assertIn("directory", message)

    @unittest.skipIf(AS_ROOT, "root reads through mode 000")
    def test_an_unsearchable_directory_is_permission_denied(self):
        locked = self.tmp / "locked"
        locked.mkdir()
        inside = write_clearance(locked / "clearance.toml", self.h)
        locked.chmod(0)
        try:
            message = self.assert_refused(self.clear(inside))["message"]
        finally:
            locked.chmod(0o700)
        self.assertIn("permission denied", message)
        self.assertNotIn("no such file", message)

    @unittest.skipIf(AS_ROOT, "root reads through mode 000")
    def test_an_unreadable_regular_file_is_permission_denied(self):
        inside = write_clearance(self.tmp / "owner" / "unreadable.toml", self.h)
        inside.chmod(0)
        try:
            message = self.assert_refused(self.clear(inside))["message"]
        finally:
            inside.chmod(0o600)
        self.assertIn("permission denied", message)
        self.assertIn("not readable", message)


# -- QS: os.stat, not Path.exists() -------------------------------------------------------------------------------------
def exists_as_on_python_313(self, *args, **kwargs):
    """``Path.exists()`` from Python 3.13 on: ``False`` on any OSError (3.12 raises). Installed on every
    version, so a revert to ``exists()`` fails on 3.12 as on 3.14."""
    try:
        os.stat(self)
    except OSError:
        return False
    return True


@unittest.skipIf(AS_ROOT, "root reads through mode 000")
class UnreadableRunDirectoryTests(LiveCase):
    """A run directory that cannot be examined never marks the creation aborted (thread QS)."""

    def test_abort_on_a_mode_000_run_directory_leaves_the_record_pending(self):
        record_activation_use(self.h.activation, self.h.h.state_dir, "run-live", T0)
        root = self.store.run_path.parent
        root.mkdir(parents=True)
        root.chmod(0)
        try:
            with mock.patch.object(Path, "exists", exists_as_on_python_313):
                self.assertEqual(abort_activation_use(self.h.activation, self.h.h.state_dir, "run-live", self.store.run_path), "ledger-error")  # adapted in round 6 (Iy): a reason, not a bool
        finally:
            root.chmod(0o700)
        self.assertEqual(record(self.h)["state"], "pending")

    def test_a_failed_creation_in_a_mode_000_run_directory_stays_pending(self):
        root = self.store.run_path.parent

        def save_then_lock(run):
            root.mkdir(parents=True, exist_ok=True)
            root.chmod(0)  # run.json may be in there: it cannot be told
            raise OSError(28, "No space left on device")

        try:
            with mock.patch.object(Store, "save_run", side_effect=save_then_lock), mock.patch.object(Path, "exists", exists_as_on_python_313):
                with self.assertRaises(OSError):
                    self.h.coordinator()
        finally:
            root.chmod(0o700)
        self.assertEqual(record(self.h)["state"], "pending")
        refuses(self, lambda: self.h.coordinator(), "activation-used", "run-metadata-missing")

    def test_a_missing_run_json_is_still_marked_aborted(self):
        record_activation_use(self.h.activation, self.h.h.state_dir, "run-live", T0)
        self.assertEqual(abort_activation_use(self.h.activation, self.h.h.state_dir, "run-live", self.store.run_path, cause=OSError(28, "No space left on device")), "aborted")  # adapted in round 6 (Iy)
        self.assertEqual(record(self.h)["state"], "aborted")


# -- Pf, Pi: the state directory of a ledger record ------------------------------------------------------------------
class StateDirIdentityTests(LiveCase):
    """The recorded state directory is the same real path, or the same directory by samefile; never a
    case-folded spelling, which on a case-sensitive file system is another directory (thread Pf)."""

    def used(self, state_dir) -> dict:
        return {"run_id": "run-live", "state_dir": state_dir, "state": "aborted"}

    def test_a_case_variant_on_a_case_sensitive_file_system_is_another_directory(self):
        here = Path(os.path.realpath(self.h.h.tmpdir.name))
        lower, upper = here / "state", here / "State"
        lower.mkdir()
        upper.mkdir()
        if os.path.samefile(lower, upper):
            self.skipTest("case-insensitive file system")
        self.assertFalse(_same_run(self.used(str(lower)), upper, "run-live"))
        self.assertFalse(_same_run(self.used(str(upper)), lower, "run-live"))
        self.assertFalse(_retryable_creation(self.used(str(lower)), upper, "run-live"))
        self.assertFalse(_same_run(self.used(str(here / "STATE-missing")), here / "state-missing", "run-live"))  # neither exists: compared exactly

    def test_another_spelling_of_the_same_directory_is_the_same_run(self):
        real = Path(os.path.realpath(self.h.h.state_dir))
        real.mkdir(parents=True, exist_ok=True)
        link = Path(self.h.h.tmpdir.name) / "state-link"
        link.symlink_to(real, target_is_directory=True)
        self.assertTrue(_same_run(self.used(str(real)), link, "run-live"))  # realpath of the presented spelling
        self.assertTrue(_same_run(self.used(str(link)), real, "run-live"))  # a recorded spelling of the same directory: samefile
        self.assertTrue(_retryable_creation(self.used(str(link)), real, "run-live"))

    def test_a_value_that_is_not_a_path_never_matches_and_never_raises(self):
        for recorded in (7, None, "bad\0path"):
            self.assertFalse(_same_run(self.used(recorded), self.h.h.state_dir, "run-live"), recorded)
        self.assertFalse(_same_run(self.used(str(self.h.h.state_dir)), "bad\0path", "run-live"))

    def test_a_reopen_journals_a_record_spelled_in_another_case_as_another_directory(self):
        self.h.coordinator()
        upper = os.path.realpath(self.h.h.state_dir).upper()
        if os.path.exists(upper):
            self.skipTest("case-insensitive file system")
        set_ledger(self.h, state="pending", state_dir=upper)
        self.h.coordinator(activation=None)
        self.assertEqual(record(self.h)["state"], "pending")
        self.assertIn("state-dir-mismatch", [e["detail"]["type"] for e in self.store.read_journal() if e["event"] == "activation-use-unconfirmed"])

    def test_a_reopen_with_a_nul_in_the_recorded_state_dir_still_opens(self):
        self.h.coordinator()
        set_ledger(self.h, state="pending", state_dir="bad\0path")
        self.assertEqual(self.h.coordinator(activation=None).status()["run"]["run_id"], "run-live")


class StateDirMissingIsUnreadableTests(LiveCase):
    """A record without a string state directory is unreadable, not a state-dir mismatch."""

    def test_a_missing_or_non_string_state_dir_is_an_unreadable_record(self):
        self.h.coordinator()
        for bad in (None, 7, ["x"]):
            set_ledger(self.h, state="pending", state_dir=bad)
            used = activation_use(self.h.activation.digest, self.h.activation.path)
            self.assertIs(used["unreadable"], True, bad)
            self.assertIn("state_dir", used["why"], bad)  # adapted in round 6 (I-): the field is named
            self.h.coordinator(activation=None)
        # adapted in round 6 (I7): an unreadable record of this run is journaled once per failing variant (the why), never a state-dir mismatch
        self.assertEqual([e["detail"]["type"] for e in self.store.read_journal() if e["event"] == "activation-use-unconfirmed"], ["ledger-unreadable"] * 3)


class StateDirMismatchJournaledTests(LiveCase):
    """A record of this run id under another state directory is journaled, not silently left pending (thread Pi)."""

    def test_a_record_under_another_state_directory_is_journaled_once(self):
        self.h.coordinator()
        set_ledger(self.h, state="pending", state_dir=str(Path(self.h.h.tmpdir.name) / "moved-from"))
        for _ in range(3):
            self.h.coordinator(activation=None)
        lines = [e["detail"] for e in self.store.read_journal() if e["event"] == "activation-use-unconfirmed"]
        self.assertEqual([d["type"] for d in lines], ["state-dir-mismatch"])
        self.assertIn("moved-from", lines[0]["error"])
        self.assertEqual(record(self.h)["state"], "pending")

    def test_another_run_id_is_still_left_alone(self):
        self.h.coordinator()
        set_ledger(self.h, state="pending", run_id="run-other", state_dir=str(Path(self.h.h.tmpdir.name) / "elsewhere"))
        self.h.coordinator(activation=None)
        self.assertNotIn("activation-use-unconfirmed", self.events())


# -- PE: the dedupe set -----------------------------------------------------------------------------------------------------
class UnconfirmedDedupeSetTests(LiveCase):
    """Duplicates are suppressed against every key since the last confirmation; an errno-less
    OSError is told apart by its strerror (thread PE)."""

    def unconfirmed(self) -> list[tuple]:
        return [(d["type"], d["errno"], d.get("strerror")) for d in (e["detail"] for e in self.store.read_journal() if e["event"] == "activation-use-unconfirmed")]

    def reopen_failing(self, exc: BaseException) -> None:
        with mock.patch.object(activation_module, "_write_ledger", side_effect=exc):
            self.h.coordinator(activation=None)

    def test_alternating_errors_add_no_line_once_each_is_on_record(self):
        self.h.coordinator()
        set_ledger(self.h, state="pending")
        for errno in (28, 5, 28, 5, 28):
            self.reopen_failing(OSError(errno, os.strerror(errno)))
        self.assertEqual(self.unconfirmed(), [("OSError", 28, None), ("OSError", 5, None)])

    def test_errno_less_os_errors_are_told_apart_by_strerror(self):
        self.h.coordinator()
        set_ledger(self.h, state="pending")
        for exc in (OSError(None, "ledger volume detached"), OSError(None, "ledger volume detached"), OSError(None, "quota exceeded")):
            self.reopen_failing(exc)
        self.assertEqual(self.unconfirmed(), [("OSError", None, "ledger volume detached"), ("OSError", None, "quota exceeded")])

    def test_an_errno_less_error_without_strerror_keys_on_its_class_alone(self):
        self.h.coordinator()
        set_ledger(self.h, state="pending")
        for name in ("aaaa", "bbbb"):  # the message names a random temporary file: never part of the key
            self.reopen_failing(OSError(f"cannot replace .tmp-{name}.json"))
        self.assertEqual(self.unconfirmed(), [("OSError", None, None)])

    def test_a_successful_confirmation_resets_the_set(self):
        self.h.coordinator()
        set_ledger(self.h, state="pending")
        self.reopen_failing(OSError(28, "No space left on device"))
        self.h.coordinator(activation=None)  # the confirmation goes through
        self.assertEqual(record(self.h)["state"], "committed")
        self.assertEqual(self.events().count("activation-use-confirmed"), 1)
        self.h.coordinator(activation=None)
        self.assertEqual(self.events().count("activation-use-confirmed"), 1)  # nothing was unconfirmed since
        set_ledger(self.h, state="pending")
        self.reopen_failing(OSError(28, "No space left on device"))
        self.assertEqual(self.unconfirmed(), [("OSError", 28, None)] * 2)  # the same cause after a confirmation is a new episode


# -- Ot, QK: the attempt history ------------------------------------------------------------------------------------------
class AttemptHistoryValidationTests(LiveCase):
    """`attempts` is a list of records or the record is unreadable; it is bounded and records why an
    attempt failed (thread Ot)."""

    def abort_once(self) -> None:
        with mock.patch.object(Store, "save_run", side_effect=OSError(28, "No space left on device")):
            with self.assertRaises(OSError):
                self.h.coordinator()
        self.assertEqual(record(self.h)["state"], "aborted")

    def test_attempts_that_are_not_a_list_of_records_refuse_as_unreadable(self):
        self.abort_once()
        for bad in ("abc", {"at": T0}, 7, [T0], [{"at": T0}, "x"], [], [{"pid": 1}]):
            set_ledger(self.h, attempts=bad)
            used = activation_use(self.h.activation.digest, self.h.activation.path)
            self.assertIs(used["unreadable"], True, bad)
            exc = refuses(self, lambda: self.h.coordinator(), "activation-used")
            self.assertIn("attempts is not a non-empty list", str(exc))  # adapted in round 6 (I-): the field is named, not "cannot be read"
        self.assertFalse(self.store.run_path.exists())

    def test_the_history_keeps_the_first_and_the_latest_ten(self):
        self.abort_once()
        history = [{"at": f"2026-11-07T09:{m:02d}:00Z", "pid": m, "source": "s"} for m in range(15)]
        set_ledger(self.h, attempts=history)
        self.h.coordinator()
        attempts = record(self.h)["attempts"]
        self.assertEqual(len(attempts), 1 + activation_module.MAX_RECENT_ATTEMPTS)
        self.assertEqual(attempts[0]["pid"], 0)
        self.assertEqual([a["pid"] for a in attempts[1:-1]], list(range(6, 15)))
        self.assertEqual(attempts[-1]["pid"], os.getpid())

    def test_the_abort_cause_is_recorded_and_moves_into_the_history(self):
        self.abort_once()
        self.assertIn("No space left on device", record(self.h)["abort_cause"])
        self.h.coordinator()
        used = record(self.h)
        self.assertNotIn("abort_cause", used)
        self.assertIn("No space left on device", used["attempts"][0]["abort_cause"])
        self.assertNotIn("abort_cause", used["attempts"][-1])


class RetrySourceTests(LiveCase):
    """A retry from another path of the same document names that path (thread QK)."""

    def test_a_retry_from_a_second_path_records_its_source(self):
        with mock.patch.object(Store, "save_run", side_effect=OSError(28, "No space left on device")):
            with self.assertRaises(OSError):
                self.h.coordinator()
        second = Path(self.h.h.tmpdir.name) / "activation-copy.toml"  # beside the first: the suite's ledger lives next to the document
        shutil.copyfile(self.h.path, second)
        self.h.activation = load_activation(second)
        self.h.coordinator()
        used = record(self.h)
        self.assertEqual(used["source"], os.path.realpath(second))
        self.assertEqual(used["attempts"][-1]["source"], used["source"])
        self.assertEqual(used["attempts"][0]["source"], os.path.realpath(self.h.path))


# -- PS, PZ: evidence ids ---------------------------------------------------------------------------------------------------
class EvidenceIdValueTests(LiveCase):
    """An all-zero id is not a citation, and the 20-digit bound is exact (threads PS, PZ)."""

    def problems(self, smoke_id: str) -> list[str]:
        document = Activation(**{**self.h.activation.__dict__, "evidence": {"lifecycle_smoke": f"https://github.com/{REPO}/pull/107#issuecomment-{smoke_id}", "fresh_review": f"https://github.com/{REPO}/pull/107#pullrequestreview-5"}})
        return [code for code, _ in document.evidence_problems(self.h.h.policy)]

    def test_an_all_zero_id_refuses(self):
        for zero in ("0", "000", "0" * 20):
            self.assertEqual(self.problems(zero), ["activation-invalid"], zero)

    def test_the_twenty_digit_bound_is_exact(self):
        self.assertEqual(self.problems("9" * 20), [])
        self.assertEqual(self.problems("0" * 19 + "1"), [])
        self.assertEqual(self.problems("9" * 21), ["activation-invalid"])
        self.assertEqual(self.problems("0" * 20 + "1"), ["activation-invalid"])


# -- O0: the refusal wording -------------------------------------------------------------------------------------------------
class CaseVariantWordingTests(ClearanceLocationCase):
    """A case-only sibling is refused with words that say so (thread O0)."""

    def test_the_refusal_says_inside_or_a_case_variant(self):
        variant = write_clearance(self.store.state_dir.parent / self.store.state_dir.name.upper() / "clearance.toml", self.h)
        with self.assertRaises(Refused) as ctx:
            load_clearance(variant, refuse_inside={"--state-dir": self.store.state_dir})
        self.assertIn("case variant", str(ctx.exception))
        with self.assertRaises(Refused) as ctx:
            self.c.clear_clock_regression(load_clearance(variant))
        self.assertIn("case variant", str(ctx.exception))


# -- Og: the abort note --------------------------------------------------------------------------------------------------------
class AbortFalseNoteTests(LiveCase):
    """When the record cannot be marked aborted the creation's error says what that means (thread Og)."""

    def test_a_record_that_was_not_marked_adds_a_note(self):
        with mock.patch.object(Store, "save_run", side_effect=OSError(28, "No space left on device")), mock.patch.object(state_module, "abort_activation_use", return_value="ledger-error"):  # adapted in round 6 (Iy): a reason
            with self.assertRaises(OSError) as ctx:
                self.h.coordinator()
        notes = getattr(ctx.exception, "__notes__", [])
        self.assertTrue(any("could not be marked aborted" in n and "activation-used" in n for n in notes), notes)

    def test_a_marked_record_adds_no_note(self):
        with mock.patch.object(Store, "save_run", side_effect=OSError(28, "No space left on device")):
            with self.assertRaises(OSError) as ctx:
                self.h.coordinator()
        self.assertEqual(getattr(ctx.exception, "__notes__", []), [])


# -- OR: clearable only inside the recorded window -------------------------------------------------------------------------
class ClearableOnlyInsideTheWindowTests(LiveCase):
    """A clock stop past the recorded expires_at can never be cleared, so it has the durable
    consequences at once (thread OR). The run's recorded window is shortened to 12:30 (a run created
    before the window had to cover the wall-clock budget), so the wall clock (until 14:00) is not
    what ends it."""

    def shorten_window(self) -> None:
        raw = json.loads(self.store.run_path.read_text(encoding="utf-8"))
        raw["activation"]["expires_at"] = "2026-11-07T12:30:00Z"  # LABELLED MUTATION: an older run whose window ends before its wall clock
        self.store.run_path.write_text(json.dumps(raw), encoding="utf-8")

    def test_resume_abandons_once_the_recorded_window_is_over(self):
        c = ClearableClockStopTests.pending_proposal(self)
        regress(self, self.h, c)
        self.shorten_window()
        self.h.clock[0] = "2026-11-07T12:10:00Z"
        with c.operation():
            c._reload_run()
            self.assertTrue(c._clearable_clock_stop())  # still inside the window
        self.h.clock[0] = "2026-11-07T12:40:00Z"
        with c.operation():
            c._reload_run()
            self.assertFalse(c._clearable_clock_stop())
        state = c.resume(S, ok_worktree)  # not deferred: the stop is durable, the pending proposal is abandoned (nothing posted)
        self.assertEqual(state.phase, "review-approved")
        self.assertIn("resume-advancing-abandoned", self.events())
        self.assertEqual([i.status for i in self.store.load_story(S).pending_advancing_intents()], [])

    def test_a_late_receipt_binds_for_cleanup_once_the_recorded_window_is_over(self):
        c = review_authorized(self.h)
        regress(self, self.h, c)
        self.shorten_window()
        self.h.clock[0] = "2026-11-07T12:40:00Z"
        exc = refuses(self, lambda: c.bind_receipt(S, REVIEWER, REVIEW_WORKTREE, REVIEW_BRANCH, ok_worktree), "clock-regression")
        self.assertTrue(exc.detail["bound_for_cleanup"])

    def set_expiry(self, at: str) -> None:
        raw = json.loads(self.store.run_path.read_text(encoding="utf-8"))
        raw["activation"]["expires_at"] = at  # LABELLED MUTATION: an older run whose window ends before its wall clock
        self.store.run_path.write_text(json.dumps(raw), encoding="utf-8")

    def test_the_clear_refuses_by_the_same_rule(self):
        c = claimed(self.h)
        regress(self, self.h, c)  # high-water mark 12:00
        self.set_expiry("2026-11-07T11:58:00Z")
        self.h.clock[0] = "2026-11-07T11:56:00Z"  # within the tolerance of the mark, before expires_at on its own
        with c.operation():
            c._reload_run()
            self.assertFalse(c._clearable_clock_stop())
        refuses(self, lambda: c.clear_clock_regression(clearance(self.h)), "activation-expired")
        self.assertEqual(stop_of(self.store)["code"], "clock-regression")  # nothing cleared
        self.assertNotIn("activation-stop-clear-started", self.events())

    def test_a_mark_exactly_at_expires_at_is_still_clearable_and_the_clear_succeeds(self):
        c = claimed(self.h)
        regress(self, self.h, c)
        self.set_expiry("2026-11-07T12:00:00Z")
        self.h.clock[0] = "2026-11-07T11:58:00Z"
        with c.operation():
            c._reload_run()
            self.assertTrue(c._clearable_clock_stop())
        self.assertIsNone(c.clear_clock_regression(clearance(self.h))["run"]["activation_stop"])

    def test_the_high_water_mark_past_the_window_counts_too(self):
        c = claimed(self.h)
        regress(self, self.h, c)  # high-water mark 12:00
        raw = json.loads(self.store.run_path.read_text(encoding="utf-8"))
        raw["activation"]["expires_at"] = "2026-11-07T11:30:00Z"  # LABELLED MUTATION: the window ended before the mark
        self.store.run_path.write_text(json.dumps(raw), encoding="utf-8")
        self.h.clock[0] = "2026-11-07T11:20:00Z"  # the clock itself is still inside the window
        with c.operation():
            c._reload_run()
            self.assertFalse(c._clearable_clock_stop())


# -- OM: reconcile a revoked repair under a clearable stop -----------------------------------------------------------------
class ReconcileRevokedUnderClearableStopTests(LiveCase):
    """A revoked repair authorization is reconciled under a clock stop the owner can still clear; a
    pending one still refuses and says to clear the stop or cancel the run (thread OM)."""

    def repair(self) -> tuple[Coordinator, dict]:
        c = review_authorized(self.h)
        c.bind_receipt(S, REVIEWER, REVIEW_WORKTREE, REVIEW_BRANCH, ok_worktree)
        c.record_review(S, self.h.h.sha, "changes-requested", "r.md", self.h.terminal())
        return c, c.authorize_repair(S).unresolved_authorization()

    @staticmethod
    def evidence() -> tuple[dict, dict]:
        run5 = run_of(OWNER, 5)
        return ({**IMPLEMENTER, "runId": run5, "dispatch": {"runId": run5, "messageId": "m"}, "startedAt": "2099-01-01T00:00:00Z"},
                {"taskId": OWNER, "runId": run5, "status": "completed"})

    def test_a_revoked_repair_is_reconciled_under_a_clearable_clock_stop(self):
        c, auth = self.repair()
        refuses(self, lambda: c.cancel(S, "owner stops the repair"), "authorization-unresolved")  # revokes it
        self.assertEqual(self.store.load_story(S).authorization(auth["id"])["status"], "revoked")
        regress(self, self.h, c)
        with c.operation():
            c._reload_run()
            self.assertTrue(c._clearable_clock_stop())
        receipt, evidence = self.evidence()
        state = c.reconcile_retained_execution(S, auth["id"], receipt, evidence, "r", "p")
        self.assertEqual(state.authorization(auth["id"])["status"], "consumed")
        self.assertIn("retained-execution-reconciled", self.events())
        self.assertEqual(stop_of(self.store)["code"], "clock-regression")  # the stop is untouched
        again = c.reconcile_retained_execution(S, auth["id"], receipt, evidence, "r", "p")  # identical evidence: idempotent, still under the stop
        self.assertEqual(again.authorization(auth["id"])["status"], "consumed")

    def test_a_pending_repair_still_refuses_and_says_clear_or_cancel(self):
        c, auth = self.repair()
        regress(self, self.h, c)
        receipt, evidence = self.evidence()
        exc = refuses(self, lambda: c.reconcile_retained_execution(S, auth["id"], receipt, evidence, "r", "p"), "clock-regression")
        self.assertIn("clear the stop or cancel the run", str(exc))
        self.assertEqual(self.store.load_story(S).authorization(auth["id"])["status"], "pending")

    def test_an_unknown_authorization_under_a_clearable_stop_is_refused_as_without_a_stop(self):
        c, auth = self.repair()
        regress(self, self.h, c)
        receipt, evidence = self.evidence()
        refuses(self, lambda: c.reconcile_retained_execution(S, "run-live:OM-01.02:99", receipt, evidence, "r", "p"), "authorization-mismatch")
        with self.assertRaises(Refused) as ctx:
            c.reconcile_retained_execution("OM-99.99", auth["id"], receipt, evidence, "r", "p")
        self.assertNotEqual(ctx.exception.code, "clock-regression")

    def test_the_docs_no_longer_contradict_the_rule(self):
        text = DOCS.read_text(encoding="utf-8")
        self.assertIn("a **revoked** authorization is reconciled", text)
        self.assertNotIn("under a clock stop the owner can still clear it refuses `clock-regression` and reconciles nothing (the repair authorization stays pending and binds for work after the clear)", text)


# -- OW: docs and help only ------------------------------------------------------------------------------------------------
class ForwardSkewDocumentedTests(unittest.TestCase):
    """A forward skew larger than the remaining budget ends the run, and the docs and help say so (thread OW)."""

    def test_docs_and_help_state_that_a_forward_skew_ends_the_run(self):
        self.assertIn("a forward skew larger than the remaining wall-clock budget ends the run", DOCS.read_text(encoding="utf-8"))
        sub = next(a for a in cli_module.build_parser()._actions if a.dest == "command")
        helps = {choice.dest: choice.help for choice in sub._choices_actions}
        self.assertIn("a forward skew larger than the remaining wall-clock budget ends the run", helps["clear-clock-regression"])


# -- Ol, QD: a clear whose save reported an error --------------------------------------------------------------------------
class ClearSaveUncertainTests(LiveCase):
    """A clear that took effect on disk is reported and journaled as such (thread Ol). Adapted in round 6
    (I0, owner decision): the normal clear result plus ``save_uncertain``, exit 0; no refusal."""

    def test_a_clear_that_took_effect_is_journaled_and_coded(self):
        c = claimed(self.h)
        regress(self, self.h, c)
        self.h.clock[0] = "2026-11-07T11:58:00Z"
        with mock.patch.object(state_module, "fsync_directory", side_effect=OSError(5, "Input/output error")):
            result = c.clear_clock_regression(clearance(self.h))
        self.assertIn("took effect", result["save_uncertain"])
        self.assertIsNone(stop_of(self.store))
        cleared = [e["detail"] for e in self.store.read_journal() if e["event"] == "activation-stop-cleared"]
        self.assertEqual(len(cleared), 1)
        self.assertIn("Input/output error", cleared[0]["save_uncertain"])
        refuses(self, lambda: c.clear_clock_regression(clearance(self.h)), "no-stop-recorded")

    def test_a_clear_whose_confirming_line_also_fails_says_so(self):
        c = claimed(self.h)
        regress(self, self.h, c)
        self.h.clock[0] = "2026-11-07T11:58:00Z"
        original = Store.journal

        def lose_cleared(store, story, event, detail=None):
            if event == "activation-stop-cleared":
                raise OSError(28, "No space left on device")
            return original(store, story, event, detail)

        with mock.patch.object(state_module, "fsync_directory", side_effect=OSError(5, "Input/output error")), mock.patch.object(Store, "journal", lose_cleared):
            result = c.clear_clock_regression(clearance(self.h))
        self.assertIsNone(result["journal_seq"])
        self.assertIn("could not be written", result["save_uncertain"])
        self.assertIsNone(json.loads(self.store.run_path.read_text(encoding="utf-8"))["activation_stop"])
        self.assertNotIn("activation-stop-cleared", self.events())
        refuses(self, lambda: c.clear_clock_regression(clearance(self.h)), "no-stop-recorded")

    def test_the_cli_exits_0_with_save_uncertain(self):
        c = claimed(self.h)
        regress(self, self.h, c)
        self.h.clock[0] = "2026-11-07T11:58:00Z"
        path = write_clearance(Path(self.h.h.tmpdir.name) / "owner" / "clearance.toml", self.h)
        with controlled_cli_clock(self.h.clock), no_gh_calls(), mock.patch.object(state_module, "fsync_directory", side_effect=OSError(5, "Input/output error")):
            code, out = run_cli(cli_args(self.h, "clear-clock-regression", "--clearance", str(path)))
        self.assertEqual(code, 0, out)
        self.assertIn("Input/output error", out["save_uncertain"])


class FailedReloadRestoresTests(LiveCase):
    """When the save and the reload both fail, the in-memory stop and mark are restored (thread QD)."""

    def test_the_fallback_restore_runs_when_the_reload_fails(self):
        c = claimed(self.h)
        regress(self, self.h, c)
        self.h.clock[0] = "2026-11-07T11:58:00Z"
        c._reload_run()
        stop, mark = dict(c.run.activation_stop), c.run.last_observed_at

        def save_fails(run):
            c._reload_run = mock.Mock(side_effect=OSError(5, "Input/output error"))  # the reload after the failed save fails too
            raise OSError(28, "No space left on device")

        try:
            with mock.patch.object(Store, "save_run", side_effect=save_fails):
                with self.assertRaises(OSError) as ctx:
                    c.clear_clock_regression(clearance(self.h))
        finally:
            c.__dict__.pop("_reload_run", None)
        self.assertEqual(ctx.exception.errno, 28)  # the save's own error
        self.assertEqual((c.run.activation_stop, c.run.last_observed_at), (stop, mark))
        with c.operation():
            self.assertTrue(c._clearable_clock_stop())


# -- P5: the _clear_spent memo ---------------------------------------------------------------------------------------------
class ClearSpentMemoInvalidationTests(LiveCase):
    """The memo never answers across operations or for another stop (thread P5)."""

    def test_a_clear_journaled_by_another_store_is_seen_by_the_next_operation(self):
        c = claimed(self.h)
        regress(self, self.h, c)
        with c.operation():
            c._reload_run()
            self.assertFalse(c._clear_spent())
        self.assertIsNone(c._clear_spent_memo)  # reset when the operation ends
        Store(self.h.h.state_dir, "run-live").journal(None, "activation-stop-cleared", {"by": "another coordinator"})
        self.h.clock[0] = "2026-11-07T11:58:00Z"
        refuses(self, lambda: c.clear_clock_regression(clearance(self.h)), "clock-clear-exhausted")

    def test_a_stale_memo_is_dropped_when_an_operation_starts(self):
        c = claimed(self.h)
        regress(self, self.h, c)
        Store(self.h.h.state_dir, "run-live").journal(None, "activation-stop-cleared", {"by": "another coordinator"})
        stop = stop_of(self.store)
        c._clear_spent_memo = ((stop["stop_id"], stop["observed_at"]), False)  # LABELLED MUTATION: a memo left behind
        with c.operation():
            c._reload_run()
            self.assertTrue(c._clear_spent())

    def test_outside_an_operation_the_memo_is_not_used(self):
        c = claimed(self.h)
        regress(self, self.h, c)
        Store(self.h.h.state_dir, "run-live").journal(None, "activation-stop-cleared", {"by": "another coordinator"})
        c._reload_run()
        stop = c.run.activation_stop
        c._clear_spent_memo = ((stop["stop_id"], stop["observed_at"]), False)  # LABELLED MUTATION
        self.assertTrue(c._clear_spent())

    def test_a_different_stop_inside_one_operation_is_not_answered_from_the_memo(self):
        c = claimed(self.h)
        regress(self, self.h, c)
        first = stop_of(self.store)
        Store(self.h.h.state_dir, "run-live").journal(None, "activation-stop-clear-started", {"stop_observed_at": first["observed_at"], "stop_id": first["stop_id"]})
        with c.operation():
            c._reload_run()
            self.assertFalse(c._clear_spent())  # a started clear of this very stop: retryable
            c.run.activation_stop = {**first, "stop_id": "f" * 32}  # another stop, seen in the same operation
            self.assertTrue(c._clear_spent())  # the started line names a stop other than this one


if __name__ == "__main__":
    unittest.main()
