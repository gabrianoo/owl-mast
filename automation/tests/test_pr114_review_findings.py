"""Regressions for the bmad-review findings on PR #114 (reviews 5828027825 and 5850902826) and for
the four PR #108 threads those reviews reopened. Every scenario runs on the fixture transport
marked live with temporary state and an injected clock; no real GitHub call and no real task is
ever made. The real CLI transport is patched to count calls where the CLI is exercised."""

from __future__ import annotations

import dataclasses
import json
import os
import pwd
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from automation.tests import PRODUCTION_LEDGER_ROOT
from automation.tests.support import REVIEW_BRANCH, REVIEW_WORKTREE, REVIEWER, controlled_cli_clock, ok_worktree, write_policy
from automation.tests.test_activation import S, T0, LiveHarness, activation_text
from automation.tests.test_enabling_repair_1 import EXPIRED, POLICY, claimed, refuses
from automation.tests.test_pr108_review_findings import cli_args, no_gh_calls, review_authorized, run_cli
from automation.unattended import activation as activation_module
from automation.unattended.activation import Activation, activation_use, ledger_path, load_activation, load_clearance, record_activation_use
from automation.unattended.coordinator import Coordinator
from automation.unattended.errors import PolicyError
from automation.unattended.github import PullRequestRecord
from automation.unattended.policy import load_policy
from automation.unattended.state import Store

REPO = "gabrianoo/owl-mast"
LONG_WINDOW = dict(issued="2026-11-07T08:00:00Z", expires="2026-11-07T20:00:00Z")  # the wall clock (240 minutes from 10:00) ends before the approval does


def tree(root: Path) -> dict:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def regress(test, h: LiveHarness, c: Coordinator) -> None:
    """High-water mark 12:00, then the host clock steps back an hour: a recorded clock-regression stop."""
    h.clock[0] = "2026-11-07T12:00:00Z"
    c.status()
    h.clock[0] = "2026-11-07T11:00:00Z"
    refuses(test, lambda: c.rebase_revisions(S, "x"), "clock-regression")
    test.assertEqual(Store(h.h.state_dir, "run-live").load_run().activation_stop["code"], "clock-regression")


def clearance(h: LiveHarness, **over) -> dict:
    stop = Store(h.h.state_dir, "run-live").load_run().activation_stop or {}
    fields = {"run_id": "run-live", "activation_id": "eng01-test-activation", "approver": "owner (fixture)", "stop_observed_at": stop.get("observed_at", "none"), "reason": "clock resynced; verified by the owner", **over}
    path = Path(h.h.tmpdir.name) / "clearance.toml"
    path.write_text("".join(f"{key} = {json.dumps(value)}\n" for key, value in fields.items()), encoding="utf-8")
    return load_clearance(path)


class LiveCase(unittest.TestCase):
    OVER: dict = {}

    def setUp(self):
        self.h = LiveHarness(**self.OVER)
        self.store = Store(self.h.h.state_dir, "run-live")

    def tearDown(self):
        self.h.close()

    def events(self) -> list[str]:
        return [e["event"] for e in self.store.read_journal()]


class ReadOnlyStatusTests(LiveCase):
    """`status --read-only` from the command line takes no lock, creates nothing and writes nothing
    (reopened #108 thread on coordinator.py:1440; #114 threads on coordinator.py:290)."""

    def test_cli_read_only_status_runs_while_another_process_holds_the_store_lock(self):
        claimed(self.h)
        with controlled_cli_clock(self.h.clock), no_gh_calls() as calls, Store(self.h.h.state_dir, "run-live").locked():
            code, out = run_cli(cli_args(self.h, "status"))
            self.assertEqual((code, out["error"]["code"]), (3, "store-busy"))  # the locked form does contend
            code, out = run_cli(cli_args(self.h, "status", "--read-only"))
            self.assertEqual((code, out["read_only"], out["activation"]["would_stop"]), (0, True, None))
            code, out = run_cli(cli_args(self.h, "status", "--read-only", activation=False))
            self.assertEqual((code, out["read_only"]), (0, True))
        self.assertEqual(calls, [])

    def test_cli_read_only_status_writes_nothing_and_creates_no_lock_file(self):
        claimed(self.h)
        (self.h.h.state_dir / ".lock").unlink()
        before = tree(Path(self.h.h.tmpdir.name))
        self.h.clock[0] = EXPIRED  # an observation the locked form would record durably
        with controlled_cli_clock(self.h.clock), no_gh_calls():
            code, out = run_cli(cli_args(self.h, "status", "--read-only"))
        self.assertEqual((code, out["activation"]["would_stop"]["code"], out["activation"]["recorded_stop"]), (0, "activation-expired", None))
        self.assertEqual(tree(Path(self.h.h.tmpdir.name)), before)
        self.assertFalse((self.h.h.state_dir / ".lock").exists())

    def test_a_read_only_coordinator_runs_no_locked_operation(self):
        claimed(self.h)
        monitor = Coordinator(self.h.h.fake, self.h.h.policy, Store(self.h.h.state_dir, "run-live"), now=lambda: self.h.clock[0], live=True, activation=self.h.activation, read_only=True)
        self.assertTrue(monitor.status(read_only=True)["read_only"])
        refuses(self, lambda: monitor.status(), "read-only")
        refuses(self, lambda: monitor.cancel_run("no"), "read-only")

    def test_a_read_only_open_refuses_a_changed_or_foreign_activation(self):
        claimed(self.h)
        stale = self.h.activation
        self.h.path.write_text(self.h.path.read_text().replace("approved = true", "approved = false"), encoding="utf-8")
        refuses(self, lambda: Coordinator(self.h.h.fake, self.h.h.policy, Store(self.h.h.state_dir, "run-live"), now=lambda: self.h.clock[0], live=True, activation=stale, read_only=True), "activation-mismatch")


class OnlyAdmissionCreatesARunTests(LiveCase):
    """A report or a cleanup command never creates the live run or spends the one-shot activation
    (#114 thread on cli.py:193)."""

    def test_status_and_other_commands_on_a_missing_run_create_nothing(self):
        fresh = Path(self.h.h.tmpdir.name) / "fresh-state"
        base = ["--policy", str(POLICY(self.h)), "--state-dir", str(fresh), "--run-id", "run-live", "--activation", str(self.h.path)]
        with controlled_cli_clock(self.h.clock), no_gh_calls() as calls:
            for rest in (["status"], ["status", "--read-only"], ["--live", "resume", S], ["--live", "cancel-run", "--reason", "x"], ["record-no-launch", S, "--no-launch", '{"authorization": "a", "reason": "r"}']):
                code, out = run_cli(base + rest)
                self.assertEqual((code, out["error"]["code"]), (3, "run-not-found"), rest)
                self.assertFalse(fresh.exists(), rest)
        self.assertIsNone(activation_use(self.h.activation.digest, self.h.activation.path))  # the approval is not spent by a probe
        self.assertEqual(calls, [])

    def test_a_non_creating_open_refuses_under_the_lock_too(self):
        fresh = Store(Path(self.h.h.tmpdir.name) / "fresh-state", "run-live")
        refuses(self, lambda: fresh.ensure_run(self.h.h.policy.repo_slug, self.h.h.policy.digest, "live", activation=self.h.activation, policy=self.h.h.policy, now=T0, create=False), "run-not-found")
        self.assertIsNone(fresh.load_run())
        self.assertIsNone(activation_use(self.h.activation.digest, self.h.activation.path))

    def test_the_admitting_path_still_creates(self):
        self.assertEqual(self.h.coordinator().run.run_id, "run-live")
        self.assertEqual(activation_use(self.h.activation.digest, self.h.activation.path)["state"], "committed")


class ClearClockRegressionOwnerTests(LiveCase):
    """`clear-clock-regression` needs an owner clearance the loop does not hold, refuses while the
    clock is still behind, and works once per run (reopened #108 thread on coordinator.py:134;
    #114 threads on coordinator.py:1485 and :1513)."""

    def setUp(self):
        super().setUp()
        self.c = claimed(self.h)

    def test_the_activation_alone_does_not_clear_the_stop(self):
        regress(self, self.h, self.c)
        self.h.clock[0] = "2026-11-07T11:58:00Z"
        for label, wrong in (("another stop", dict(stop_observed_at="2026-11-07T10:30:00Z")), ("another approver", dict(approver="the loop")), ("another run", dict(run_id="run-other")), ("another activation", dict(activation_id="eng01-other"))):
            exc = refuses(self, lambda: self.c.clear_clock_regression(clearance(self.h, **wrong)), "clearance-mismatch")
            self.assertIn(next(iter(wrong)), str(exc), label)
        self.assertEqual(self.store.load_run().activation_stop["code"], "clock-regression")
        self.assertNotIn("activation-stop-cleared", self.events())

    def test_a_clearance_is_a_strict_document(self):
        path = Path(self.h.h.tmpdir.name) / "c.toml"
        for text in ("", 'run_id = "run-live"\n', 'run_id = "r"\nactivation_id = "a"\napprover = "o"\nstop_observed_at = "t"\nreason = ""\n', 'run_id = "r"\nactivation_id = "a"\napprover = "o"\nstop_observed_at = "t"\nreason = "x"\nextra = "y"\n', "not toml ="):
            path.write_text(text, encoding="utf-8")
            refuses(self, lambda: load_clearance(path), "clearance-invalid")
        refuses(self, lambda: load_clearance(Path(self.h.h.tmpdir.name) / "missing.toml"), "clearance-invalid")

    def test_clear_refuses_while_the_clock_is_still_behind_the_high_water_mark(self):
        regress(self, self.h, self.c)
        for still_behind in ("2026-11-07T11:05:00Z", "2026-11-07T11:54:59Z"):
            self.h.clock[0] = still_behind
            exc = refuses(self, lambda: self.c.clear_clock_regression(clearance(self.h)), "clock-regression")
            self.assertEqual(exc.detail["high_water"], "2026-11-07T12:00:00Z")
        run = self.store.load_run()
        self.assertEqual((run.activation_stop["code"], run.last_observed_at), ("clock-regression", "2026-11-07T12:00:00Z"))  # nothing cleared, the high-water mark untouched
        self.h.clock[0] = "2026-11-07T11:55:00Z"  # caught up to within the tolerance
        self.c.clear_clock_regression(clearance(self.h))
        self.assertEqual(self.store.load_run().last_observed_at, "2026-11-07T12:00:00Z")  # kept: the window and the wall clock are never judged on the slower clock

    def test_a_run_is_cleared_at_most_once(self):
        regress(self, self.h, self.c)
        self.h.clock[0] = "2026-11-07T11:58:00Z"
        self.c.clear_clock_regression(clearance(self.h))
        self.h.clock[0] = "2026-11-07T13:00:00Z"
        self.c.status()
        self.h.clock[0] = "2026-11-07T12:10:00Z"
        refuses(self, lambda: self.c.rebase_revisions(S, "x"), "clock-regression")
        self.h.clock[0] = "2026-11-07T12:58:00Z"
        refuses(self, lambda: self.c.clear_clock_regression(clearance(self.h)), "clock-clear-exhausted")
        self.assertEqual(self.store.load_run().activation_stop["code"], "clock-regression")

    def test_the_clear_is_journaled_before_the_stop_is_gone(self):
        regress(self, self.h, self.c)
        self.h.clock[0] = "2026-11-07T11:58:00Z"
        with mock.patch.object(Store, "journal", side_effect=OSError(28, "No space left on device")):
            with self.assertRaises(OSError):
                self.c.clear_clock_regression(clearance(self.h))
        self.assertEqual(self.store.load_run().activation_stop["code"], "clock-regression")  # no journal line, no clear: the once-per-run limit can always see a clear that happened

    def test_cli_clear_with_a_clearance(self):
        regress(self, self.h, self.c)
        self.h.clock[0] = "2026-11-07T11:58:00Z"
        clearance(self.h)
        with controlled_cli_clock(self.h.clock), no_gh_calls():
            code, out = run_cli(cli_args(self.h, "clear-clock-regression", "--clearance", str(Path(self.h.h.tmpdir.name) / "clearance.toml")))
        self.assertEqual((code, out["cleared"]["code"], out["run"]["activation_stop"]), (0, "clock-regression", None))


class UseLedgerTests(LiveCase):
    """The use ledger is keyed on the document digest in one per-machine directory, is crash-safe
    and does not burn an approval whose creation failed (reopened #108 thread on state.py:418;
    #114 threads on activation.py and state.py:421)."""

    def other(self, name="runs-2", run_id="run-live") -> Store:
        return Store(Path(self.h.h.tmpdir.name) / name, run_id)

    def create(self, store: Store, activation: Activation) -> Coordinator:
        return Coordinator(self.h.h.fake, self.h.h.policy, store, now=lambda: self.h.clock[0], live=True, activation=activation)

    def test_a_copy_a_symlink_and_a_hard_link_are_the_same_approval(self):
        self.h.coordinator()
        folder = Path(self.h.h.tmpdir.name)
        shutil.copyfile(self.h.path, folder / "copy.toml")
        os.symlink(self.h.path, folder / "symlink.toml")
        os.link(self.h.path, folder / "hardlink.toml")
        for name in ("copy.toml", "symlink.toml", "hardlink.toml"):
            again = load_activation(folder / name)
            self.assertEqual(again.digest, self.h.activation.digest, name)
            exc = refuses(self, lambda: self.create(self.other(f"runs-{name}"), again), "activation-used")
            self.assertEqual(exc.detail["problems"][-1].count("already created live run 'run-live'"), 1, name)
            self.assertIsNone(self.other(f"runs-{name}").load_run(), name)

    def test_the_ledger_itself_refuses_a_second_use_and_is_not_rewritten(self):
        self.h.coordinator()
        path = ledger_path(self.h.activation.digest, self.h.activation.path)
        before = path.read_bytes()
        exc = refuses(self, lambda: record_activation_use(self.h.activation, self.other().state_dir, "run-live", T0), "activation-used")  # the exclusive create, not the pre-check
        self.assertEqual((exc.detail["used"]["run_id"], exc.detail["used"]["state_dir"]), ("run-live", str(self.h.h.state_dir.resolve())))
        refuses(self, lambda: record_activation_use(self.h.activation, self.h.h.state_dir, "run-live", T0), "activation-used")  # committed: not even this run again
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual([p.name for p in path.parent.iterdir()], [path.name])  # no temporary file left behind

    def test_a_creation_that_fails_after_the_ledger_write_does_not_burn_the_approval(self):
        with mock.patch.object(Store, "save_run", side_effect=OSError(28, "No space left on device")):
            with self.assertRaises(OSError):
                self.h.coordinator()
        self.assertIsNone(self.store.load_run())
        self.assertEqual(activation_use(self.h.activation.digest, self.h.activation.path)["state"], "pending")
        refuses(self, lambda: self.create(self.other(), self.h.activation), "activation-used")  # pending for another state directory is still a use
        refuses(self, lambda: self.create(self.other("runs-3", "run-live"), self.h.activation), "activation-used")
        self.assertEqual(self.h.coordinator().run.run_id, "run-live")  # the same creation, retried: not refused
        self.assertEqual(activation_use(self.h.activation.digest, self.h.activation.path)["state"], "committed")
        shutil.rmtree(self.store.root)
        refuses(self, lambda: self.h.coordinator(), "activation-used")  # once the run existed, deleting it refunds nothing

    def test_a_crash_between_run_json_and_the_confirmation_is_settled_by_the_next_open(self):
        self.h.coordinator()
        path = ledger_path(self.h.activation.digest, self.h.activation.path)
        path.write_text(json.dumps({**json.loads(path.read_text(encoding="utf-8")), "state": "pending"}), encoding="utf-8")  # LABELLED MUTATION: the process died right after run.json was written
        self.h.coordinator(activation=None)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["state"], "committed")

    def test_an_unwritable_ledger_creates_no_run(self):
        self.h.h.fake.calls = []
        with mock.patch.object(activation_module, "_write_ledger", side_effect=PermissionError(13, "Permission denied")):
            refuses(self, lambda: self.h.coordinator(), "activation-ledger-unwritable")
        root = ledger_path(self.h.activation.digest, self.h.activation.path).parent
        shutil.rmtree(root, ignore_errors=True)
        root.write_text("not a directory", encoding="utf-8")
        refuses(self, lambda: self.h.coordinator(), "activation-ledger-unwritable")
        root.unlink()
        self.assertIsNone(self.store.load_run())
        self.assertEqual(self.h.h.fake.calls, [])
        self.assertEqual(self.h.coordinator().run.run_id, "run-live")  # nothing was marked: the document still creates its run

    def test_a_failed_write_leaves_no_partial_ledger(self):
        with mock.patch.object(activation_module.json, "dump", side_effect=OSError(5, "Input/output error")):
            refuses(self, lambda: self.h.coordinator(), "activation-ledger-unwritable")
        self.assertIsNone(activation_use(self.h.activation.digest, self.h.activation.path))
        self.assertEqual(list(ledger_path(self.h.activation.digest, self.h.activation.path).parent.iterdir()), [])

    def test_an_unreadable_ledger_is_a_use(self):
        self.h.coordinator()
        ledger_path(self.h.activation.digest, self.h.activation.path).write_text("{torn", encoding="utf-8")
        self.assertEqual(activation_use(self.h.activation.digest, self.h.activation.path), {"unreadable": True})
        exc = refuses(self, lambda: self.create(self.other(), self.h.activation), "activation-used")
        self.assertIn("cannot be read", str(exc))  # named as a damaged record, not as a run "None under None"
        exc = refuses(self, lambda: record_activation_use(self.h.activation, self.other().state_dir, "run-live", T0), "activation-used")
        self.assertIn("cannot be read", str(exc))

    def test_a_reissued_activation_at_the_same_path_creates_its_own_run(self):
        self.h.coordinator()
        self.h.path.write_text(activation_text(self.h.h.policy, run_id="run-next", expires="2026-11-07T15:00:00Z"), encoding="utf-8")  # the owner re-issues in place: another document, another digest
        reissued = load_activation(self.h.path)
        self.assertEqual(reissued.creation_problems(self.h.h.policy, "run-next", T0, state_dir=self.h.h.state_dir), [])
        self.assertEqual(self.create(Store(self.h.h.state_dir, "run-next"), reissued).run.run_id, "run-next")

    def test_a_used_document_reports_used_before_expired(self):
        self.h.coordinator()
        problems = self.h.activation.creation_problems(self.h.h.policy, "run-live", EXPIRED, state_dir=self.other().state_dir)
        self.assertEqual((Activation.stop_code(problems), Activation.stop_codes(problems)), ("activation-used", ["activation-used", "activation-expired"]))

    def test_the_production_ledger_is_one_fixed_directory_outside_every_tree(self):
        with mock.patch.object(activation_module, "ledger_root", PRODUCTION_LEDGER_ROOT):  # the function the suite replaces (automation/tests/__init__.py)
            a, b = ledger_path("d" * 64, "/somewhere/a.toml"), ledger_path("d" * 64, "relative/b.toml")
        self.assertEqual(a, b)
        self.assertEqual(a, Path(pwd.getpwuid(os.getuid()).pw_dir) / ".local/state/owl-mast/activation-ledger" / ("d" * 64 + ".json"))
        with mock.patch.dict(os.environ, {"HOME": "/tmp/elsewhere", "XDG_STATE_HOME": "/tmp/elsewhere"}), mock.patch.object(activation_module, "ledger_root", PRODUCTION_LEDGER_ROOT):
            self.assertEqual(ledger_path("d" * 64, "x.toml"), a)  # not movable through the environment the loop controls


class EvidenceRuleTests(LiveCase):
    """The citation rule applies when a run is created, never mid-run, and checks the whole value
    (#114 threads on activation.py:156, :158, :58, :161)."""

    def problems(self, **evidence) -> list[str]:
        document = dataclasses.replace(self.h.activation, evidence={**self.h.activation.evidence, **evidence})
        return [m for _, m in document.evidence_problems(self.h.h.policy)]

    def test_the_shape_is_checked_strictly(self):
        good = f"https://github.com/{REPO}/pull/107#issuecomment-1"
        self.assertEqual(self.problems(lifecycle_smoke=good), [])
        self.assertEqual(self.problems(lifecycle_smoke="https://github.com/Gabrianoo/Owl-Mast/pull/107#issuecomment-1"), [])  # GitHub slugs are case-insensitive
        for label, bad in (("trailing newline", good + "\n"), ("non-ASCII digits", f"https://github.com/{REPO}/pull/107#issuecomment-١٢٣"), ("trailing text", good + " and more"), ("query", f"https://github.com/{REPO}/pull/107?x=1#issuecomment-1"), ("another repository", "https://github.com/gabrianoo/owl-mast-2/pull/1#issuecomment-1")):
            self.assertEqual(len(self.problems(lifecycle_smoke=bad)), 1, label)

    def test_the_two_keys_cite_two_comments(self):
        same = f"https://github.com/{REPO}/pull/107#issuecomment-6706853226"
        problems = self.problems(lifecycle_smoke=same, fresh_review=same)
        self.assertEqual(len(problems), 1)
        self.assertIn("cite the same comment", problems[0])
        respelled = self.problems(lifecycle_smoke=f"https://github.com/{REPO}/issues/107#issuecomment-5", fresh_review=f"https://github.com/{REPO}/pull/108#issuecomment-5")
        self.assertEqual(len(respelled), 1)  # the same comment under another issue or pull request path is still one publication

    def test_a_run_created_under_the_earlier_rule_keeps_advancing(self):
        h = LiveHarness(smoke='"fixture smoke reference"', review='"fixture review reference"')  # what main accepted before the URL rule
        try:
            refuses(self, lambda: h.coordinator(), "activation-invalid")  # today such a document creates nothing
            with mock.patch.object(Activation, "evidence_problems", lambda self, policy: []):  # LABELLED MUTATION: the run was created before the rule existed
                c = claimed(h)
            self.assertEqual(h.activation.problems(h.h.policy, "run-live", T0), [])
            self.assertEqual(c.record_head(S, h.h.sha, h.terminal()).phase, "implemented")  # mid-run: not stranded by the new rule
            self.assertIsNone(h.coordinator().status()["stop"])
            with controlled_cli_clock(h.clock), no_gh_calls():
                code, out = run_cli(cli_args(h, "check-activation"))
            self.assertEqual((code, out["current"], out["can_create"]), (0, True, False))
            self.assertTrue(any("evidence." in m for m in out["creation_problems"]))
        finally:
            h.close()


class CheckActivationRunAwareTests(LiveCase):
    """`check-activation` answers "is my running activation still current" for a run that exists
    and "can this document create the run" for one that does not (#114 thread on cli.py:114)."""

    def check(self, *extra: str) -> tuple[int, dict]:
        with controlled_cli_clock(self.h.clock), no_gh_calls() as calls:
            code, out = run_cli(cli_args(self.h, "check-activation", *extra))
        self.assertEqual(calls, [])
        return code, out

    def test_an_existing_run_under_its_own_activation_is_current(self):
        code, out = self.check()
        self.assertEqual((code, out["current"], out["can_create"], out["run_exists"]), (0, True, True, False))
        claimed(self.h)
        before = tree(Path(self.h.h.tmpdir.name))
        code, out = self.check()
        self.assertEqual((code, out["current"], out["can_create"], out["run_exists"], out["stop"], out["problems"]), (0, True, False, True, None, []))
        self.assertEqual(out["used"]["state"], "committed")
        self.assertEqual(tree(Path(self.h.h.tmpdir.name)), before)  # read-only

    def test_an_existing_run_past_its_window_or_under_a_recorded_stop_is_not_current(self):
        c = claimed(self.h)
        self.h.clock[0] = EXPIRED
        code, out = self.check()
        self.assertEqual((code, out["current"], out["stop"]), (2, False, "activation-expired"))
        c.status()  # records the stop durably
        self.h.clock[0] = T0  # a clock set back does not make the run current again
        code, out = self.check()
        self.assertEqual((code, out["current"], out["stop"]), (2, False, "activation-expired"))

    def test_a_cancelled_or_over_time_run_is_not_current(self):
        c = claimed(self.h)
        self.h.clock[0] = "2026-11-07T13:59:00Z"  # inside the window; the fixture budget of 240 minutes ends at 14:00 with it
        self.assertEqual(self.check()[1]["current"], True)
        c.cancel_run("owner stop")
        code, out = self.check()
        self.assertEqual((code, out["current"], out["stop"], out["stops"]), (2, False, "run-cancelled", ["run-cancelled"]))

    def test_an_over_time_run_inside_a_longer_window_is_not_current(self):
        h = LiveHarness(**LONG_WINDOW)
        try:
            claimed(h)
            h.clock[0] = "2026-11-07T14:30:00Z"
            with controlled_cli_clock(h.clock), no_gh_calls():
                code, out = run_cli(cli_args(h, "check-activation"))
            self.assertEqual((code, out["current"], out["stop"]), (2, False, "wall-clock-exceeded"))
        finally:
            h.close()

    def test_without_an_activation_only_the_policy_digest_is_reported(self):
        with no_gh_calls() as calls:
            code, out = run_cli(["--policy", str(POLICY(self.h)), "check-activation"])
        self.assertEqual((code, out["policy_digest"], out["current"], out["stop"]), (2, self.h.h.policy.digest, False, "activation-required"))
        self.assertEqual(calls, [])

    def test_another_document_is_not_the_run_s_activation(self):
        claimed(self.h)
        other = Path(self.h.h.tmpdir.name) / "other.toml"
        other.write_text(activation_text(self.h.h.policy, expires="2026-11-07T15:00:00Z"), encoding="utf-8")
        with controlled_cli_clock(self.h.clock), no_gh_calls():
            code, out = run_cli(["--policy", str(POLICY(self.h)), "--state-dir", str(self.h.h.state_dir), "--run-id", "run-live", "--activation", str(other), "check-activation"])
        self.assertEqual((code, out["current"], out["stop"]), (2, False, "activation-mismatch"))


class DeferredResumeTests(LiveCase):
    """A resume without the file defers, visibly: a refusal with `deferred`, its own journal event,
    no GitHub call; the proposal branch is covered (reopened #108 thread on coordinator.py:1330;
    #114 threads on coordinator.py:1394, :1409, :1410 and the unanchored revision-check finding)."""

    def proposed_then_rolled_back(self) -> Coordinator:
        c = review_authorized(self.h)
        c.bind_receipt(S, REVIEWER, REVIEW_WORKTREE, REVIEW_BRANCH, ok_worktree)
        c.record_review(S, self.h.h.sha, "approved", "report.md", self.h.terminal())
        self.h.h.fake.pull_requests[7] = PullRequestRecord(7, "OPEN", self.h.h.sha, False, (), "SUCCESS")
        self.assertEqual(c.propose_evidence(S, self.h.h.sha, 7, [], "s").phase, "proposed")
        state = self.store.load_story(S)
        state.phase = "review-approved"  # the proposal comment landed; the proposed transition did not persist
        self.store.save_story(state)
        return c

    def test_resume_without_the_file_defers_a_completed_proposal(self):
        c = self.proposed_then_rolled_back()
        bare = self.h.coordinator(activation=None)
        self.h.h.fake.calls = []
        exc = refuses(self, lambda: bare.resume(S, ok_worktree), "activation-required")
        self.assertTrue(exc.detail["deferred"])
        self.assertEqual(len(exc.detail["ops"]), 1)
        self.assertTrue(exc.detail["ops"][0].startswith("proposal-"))
        self.assertEqual(self.store.load_story(S).phase, "review-approved")  # nothing advanced without a current activation
        self.assertEqual(self.h.h.fake.calls, [])  # and nothing was read from GitHub: no revision check, no PR validation
        deferred = [e for e in self.store.read_journal() if e["event"] == "reconciliation-deferred"]
        self.assertEqual((len(deferred), deferred[0]["detail"]["code"]), (1, "activation-required"))
        self.assertNotIn("reconciliation-withheld", self.events())
        self.assertEqual(c.resume(S, ok_worktree).phase, "proposed")  # with the file the same resume completes

    def test_cli_deferred_resume_is_not_a_success(self):
        self.proposed_then_rolled_back()
        with controlled_cli_clock(self.h.clock), no_gh_calls() as calls:
            code, out = run_cli(cli_args(self.h, "--live", "resume", S, activation=False))
        self.assertEqual((code, out["error"]["code"], out["error"]["deferred"]), (3, "activation-required", True))
        self.assertEqual(calls, [])

    def test_a_resume_with_nothing_to_defer_still_succeeds_without_the_file(self):
        claimed(self.h)
        bare = self.h.coordinator(activation=None)
        self.h.h.fake.calls = []
        self.assertEqual(bare.resume(S, ok_worktree).phase, "claimed")
        self.assertEqual(self.h.h.fake.calls, [])
        self.assertNotIn("reconciliation-deferred", self.events())
        bare.resume(S, ok_worktree)
        self.assertEqual(self.events().count("resume-revisions-unverified"), 1)  # on record, once: this resume verified no revisions

    def test_an_unsettled_claim_race_is_deferred_not_settled_without_the_file(self):
        c = self.h.coordinator()
        c.reserve(S, self.h.h.snapshot, "base")
        state = self.store.load_story(S)
        state.claim["race_settled"] = False  # the process died before the race re-read
        self.store.save_story(state)
        bare = self.h.coordinator(activation=None)
        self.h.h.fake.calls = []
        exc = refuses(self, lambda: bare.resume(S, ok_worktree), "activation-required")
        self.assertEqual(exc.detail["ops"], ["claim"])
        self.assertEqual(self.h.h.fake.calls, [])
        self.assertEqual(self.store.load_story(S).claim["race_settled"], False)


class RunStopOrderTests(LiveCase):
    """One definition of the durable stops, and a recorded stop outranks the wall clock
    (#114 threads on coordinator.py:448, :443, :442)."""

    OVER = LONG_WINDOW

    def test_a_recorded_stop_outranks_an_exceeded_wall_clock(self):
        c = review_authorized(self.h)
        regress(self, self.h, c)
        self.h.clock[0] = "2026-11-07T14:30:00Z"  # 270 minutes after the start: the wall clock ran out too
        with c.operation():
            self.assertEqual((c._run_stop(), c._durable_run_stop()), ("clock-regression", "clock-regression"))
        self.assertEqual(c.status()["stop"], "clock-regression")
        refuses(self, lambda: c.authorize_repair(S), "clock-regression")
        bare = self.h.coordinator(activation=None)
        exc = refuses(self, lambda: bare.bind_receipt(S, REVIEWER, worktree_check=ok_worktree), "clock-regression")
        self.assertTrue(exc.detail["bound_for_cleanup"])
        self.assertEqual(self.store.load_story(S).active_task["cleanup_only"], "clock-regression")

    def test_the_two_stop_readings_agree_on_every_durable_cause(self):
        c = claimed(self.h)
        bare = self.h.coordinator(activation=None)
        with bare.operation():
            self.assertEqual((bare._durable_run_stop(), bare._run_stop()), (None, "activation-required"))  # a missing file is the only difference, and it is not durable
        self.h.clock[0] = "2026-11-07T14:30:00Z"
        for coordinator in (c, bare):
            with coordinator.operation():
                self.assertEqual((coordinator._durable_run_stop(), coordinator._run_stop()), ("wall-clock-exceeded", "wall-clock-exceeded"))
        self.h.clock[0] = "2026-11-07T11:00:00Z"
        c.cancel_run("stop")
        for coordinator in (c, bare):
            with coordinator.operation():
                coordinator._reload_run()
                self.assertEqual((coordinator._durable_run_stop(), coordinator._run_stop()), ("run-cancelled", "run-cancelled"))


class CleanupBindTests(LiveCase):
    """A launched worker can be put on record when the activation file is lost for good
    (#114 threads on coordinator.py:866 and :868)."""

    def test_for_cleanup_binds_the_task_without_the_file_and_authorizes_no_work(self):
        review_authorized(self.h)
        bare = self.h.coordinator(activation=None)
        refuses(self, lambda: bare.bind_receipt(S, REVIEWER, REVIEW_WORKTREE, REVIEW_BRANCH, ok_worktree), "activation-required")
        self.assertIsNone(self.store.load_story(S).active_task)
        exc = refuses(self, lambda: bare.bind_receipt(S, REVIEWER, worktree_check=ok_worktree, for_cleanup=True), "cleanup-requested")
        self.assertTrue(exc.detail["bound_for_cleanup"])
        state = self.store.load_story(S)
        self.assertEqual((state.phase, state.active_task["taskId"], state.active_task["cleanup_only"]), ("review-authorized", REVIEWER["taskId"], "cleanup-requested"))
        self.assertIn("receipt-bound-cleanup-only", self.events())
        refuses(self, lambda: self.h.coordinator().record_review(S, self.h.h.sha, "approved", "r.md", self.h.terminal()), "refused")  # no work was authorized by it: the phase never moved to review-requested
        self.assertEqual(bare.cancel(S, "activation file lost", self.h.terminal()).phase, "cancelled")  # the real terminal evidence is accepted: no false no-launch attestation needed

    def test_cli_for_cleanup(self):
        review_authorized(self.h)
        with controlled_cli_clock(self.h.clock), no_gh_calls():
            code, out = run_cli(cli_args(self.h, "bind-receipt", S, "--receipt", json.dumps(REVIEWER), "--for-cleanup", activation=False))
        self.assertEqual((code, out["error"]["code"], out["error"]["bound_for_cleanup"]), (3, "cleanup-requested", True))


class ConstructionTests(LiveCase):
    """The coordinator holds the document the locked open saw; the locked creation decides on its
    own; a refused creation leaves nothing (#114 threads on state.py:434, :415, coordinator.py:281)."""

    def test_a_source_removed_before_the_open_is_not_presented(self):
        claimed(self.h)
        self.h.path.unlink()
        c = self.h.coordinator()  # the stale loaded object is passed in
        self.assertIsNone(c.activation)
        self.assertEqual(c.status()["activation"]["presented"], None)

    def test_the_locked_creation_refuses_a_short_window_without_the_coordinator_pre_check(self):
        h = LiveHarness(expires="2026-11-07T11:00:00Z")  # 60 minutes left, budget 240
        try:
            store = Store(Path(h.h.tmpdir.name) / "direct", "run-live")
            refuses(self, lambda: store.ensure_run(h.h.policy.repo_slug, h.h.policy.digest, "live", activation=h.activation, policy=h.h.policy, now=T0), "activation-window-short")
            self.assertFalse(store.run_path.exists())
            self.assertIsNone(activation_use(h.activation.digest, h.activation.path))
        finally:
            h.close()

    def test_a_creation_refused_by_the_pre_check_leaves_no_state_directory(self):
        h = LiveHarness(expires="2026-11-07T11:00:00Z")
        try:
            fresh = Path(h.h.tmpdir.name) / "fresh-state"
            refuses(self, lambda: Coordinator(h.h.fake, h.h.policy, Store(fresh, "run-live"), now=lambda: T0, live=True, activation=h.activation), "activation-window-short")
            self.assertFalse(fresh.exists())
            self.assertFalse(ledger_path(h.activation.digest, h.activation.path).parent.exists())
        finally:
            h.close()


class PolicyLoaderTests(unittest.TestCase):
    """The policy loader follows the activation loader's rules, and a wall-clock budget must fit
    inside one activation window (#114 threads on activation.py:148, :187 and policy.py:95)."""

    def rejected(self, **overrides) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(PolicyError) as ctx:
                load_policy(write_policy(Path(tmp), **overrides))
            return str(ctx.exception)

    def test_a_repeated_or_non_string_allow_entry_is_refused(self):
        self.assertIn("dispatch.allow lists a story more than once", self.rejected(allow='["OM-01.02", "OM-01.02"]'))
        self.assertIn("dispatch.allow entries must be non-empty strings", self.rejected(allow='["OM-01.02", 7]'))

    def test_target_fields_are_strings(self):
        self.assertIn("string values", self.rejected(options='{ effort = "high", timeoutMs = 600000 }'))

    def test_a_wall_clock_that_does_not_fit_one_activation_window_creates_no_live_run_and_says_so(self):
        h = LiveHarness(issued="2026-11-07T10:00:00Z", expires="2026-11-08T10:00:00Z")  # the longest window there is
        try:
            with tempfile.TemporaryDirectory() as tmp:
                long_policy = load_policy(write_policy(Path(tmp), allow='["OM-01.02"]', max_wall_clock_minutes="1440"))  # still loads: runs that exist under such a policy stay reportable and cleanable
            problems = h.activation.creation_problems(long_policy, "run-live", T0, state_dir=h.h.state_dir)
            self.assertTrue(any(code == "activation-window-short" and "does not fit inside one activation window" in message for code, message in problems))
        finally:
            h.close()


if __name__ == "__main__":
    unittest.main()
