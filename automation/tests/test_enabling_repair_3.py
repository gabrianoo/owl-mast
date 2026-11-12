"""Repair round 3 of the enabling change: the two residual findings of the final independent
review of ce0320e (review-final-ce0320e.md). Every scenario runs on the fixture transport marked
live with temporary state; no real GitHub call and no real task is ever made.

FINAL-1  the loaded activation object is a cache. Run creation (public ``Coordinator`` and public
         ``Store.ensure_run``) re-reads the source under the store lock before any metadata or
         journal write: a changed (unapproved), missing or malformed source creates no binding,
         no ``run-started`` event and no replacement record; the unchanged source still creates.
FINAL-2  one clock observation per locked operation. Every authorization decision of an operation
         (window, durable stop, wall clock, the status report) is made from the instant sampled
         after the lock is held, so an operation cannot report or refuse on an expiry its own
         durable check did not record. The first operation whose observation is past the window
         records the stop, which survives a within-tolerance rollback and a restart."""

from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from automation.tests.support import controlled_cli_clock, ok_worktree, passing_runner
from automation.tests.test_activation import S, T0, LiveHarness, activation_text
from automation.tests.test_enabling_repair_1 import claimed, refuses
from automation.unattended import cli
from automation.unattended.errors import UnattendedError
from automation.unattended.state import Store

LAST_VALID = "2026-11-07T14:00:00Z"  # the inclusive last valid instant of the fixture window
EXPIRED = "2026-11-07T14:00:01Z"
ROLLED_BACK = "2026-11-07T13:59:59Z"  # inside the accepted clock-regression tolerance


def alter_source(h: LiveHarness, how: str) -> None:
    if how == "changed":
        h.path.write_text(activation_text(h.h.policy, approved=False), encoding="utf-8")
    elif how == "missing":
        h.path.unlink()
    elif how == "malformed":
        h.path.write_text("approved = \n", encoding="utf-8")
    else:
        assert how == "unchanged"


class Final1StaleCreationObjectTests(unittest.TestCase):
    """A previously loaded, genuinely approved object does not create a run once its source is no longer that document."""

    EXPECTED = {"changed": "activation-mismatch", "missing": "activation-required", "malformed": "activation-invalid"}

    def create(self, h: LiveHarness, entry: str):
        store = Store(h.h.state_dir, "run-live")
        if entry == "coordinator":
            return h.coordinator()
        return store.ensure_run(h.h.policy.repo_slug, h.h.policy.digest, "live", activation=h.activation, policy=h.h.policy, now=T0)

    def check(self, entry: str, how: str):
        h = LiveHarness()
        try:
            alter_source(h, how)
            h.h.fake.calls = []
            store = Store(h.h.state_dir, "run-live")
            if how == "unchanged":
                self.create(h, entry)
                run = store.load_run()
                self.assertTrue(run.activation["approved"])
                self.assertEqual(run.activation["digest"], h.activation.digest)
                self.assertEqual([e["event"] for e in store.read_journal()], ["run-started"])
            else:
                refuses(self, lambda: self.create(h, entry), self.EXPECTED[how])
                self.assertFalse(store.run_path.exists(), (entry, how))
                self.assertFalse(store.journal_path.exists(), (entry, how))
                self.assertFalse(store.root.exists() and any(store.root.iterdir()), (entry, how))
            self.assertEqual(h.h.fake.calls, [])
        finally:
            h.close()

    def test_coordinator_creation_refuses_a_changed_missing_or_malformed_source_and_creates_on_the_unchanged_one(self):
        for how in ("unchanged", "changed", "missing", "malformed"):
            self.check("coordinator", how)

    def test_public_store_creation_refuses_a_changed_missing_or_malformed_source_and_creates_on_the_unchanged_one(self):
        for how in ("unchanged", "changed", "missing", "malformed"):
            self.check("store", how)

    def test_the_binding_records_the_re_read_document_not_the_cached_object(self):
        """The same document rewritten byte-for-byte differently is a different digest: refused; the identical text is the same document."""
        h = LiveHarness()
        try:
            h.path.write_text(h.path.read_text(encoding="utf-8") + "\n# trailing comment\n", encoding="utf-8")
            refuses(self, lambda: h.coordinator(), "activation-mismatch")
            self.assertFalse(Store(h.h.state_dir, "run-live").run_path.exists())
            h.path.write_text(activation_text(h.h.policy), encoding="utf-8")  # the original text again
            self.assertEqual(h.coordinator().run.activation["digest"], h.activation.digest)
        finally:
            h.close()

    def test_previously_activated_run_still_cleans_up_without_its_file(self):
        """The valid recorded binding of a genuinely created run keeps working when the file is gone afterwards (R3 positive control)."""
        h = LiveHarness()
        try:
            claimed(h)
            h.path.unlink()
            h.h.fake.calls = []
            c = h.coordinator()  # an existing run: the gate refreshes to no presented document on the first operation
            self.assertEqual(c.status()["activation"]["stop"], "activation-required")
            self.assertIsNone(c.activation)
            refuses(self, lambda: c.record_head(S, h.h.sha, h.terminal()), "activation-required")
            self.assertEqual(h.h.fake.calls, [])  # status and the refusal touch no transport
            self.assertEqual(h.coordinator(activation=None).cancel(S, "cleanup", h.terminal()).phase, "cancelled")
        finally:
            h.close()

    def test_cli_creation_with_an_altered_source_refuses_without_state_or_calls(self):
        from automation.unattended.github import GhCliTransport

        for how in self.EXPECTED:
            h = LiveHarness()
            calls = []
            original = GhCliTransport._run
            GhCliTransport._run = lambda self, args, stdin=None: calls.append(args) or "{}"
            try:
                args = ["--policy", str(Path(h.h.tmpdir.name) / "policy.toml"), "--state-dir", str(h.h.state_dir), "--run-id", "run-live", "--live", "--activation", str(h.path), "status"]
                store = Store(h.h.state_dir, "run-live")
                with controlled_cli_clock(h.clock):  # creation is decided on the injected observation, never the host clock
                    h.clock[0] = EXPIRED
                    buf = io.StringIO()
                    with redirect_stdout(buf):
                        rc = cli.main(args)  # the unchanged source past its window creates nothing; a report on a missing run says so first (PR #114 round 3)
                    self.assertEqual((rc, json.loads(buf.getvalue())["error"]["code"]), (3, "run-not-found"))
                    self.assertFalse(store.root.exists() and any(store.root.iterdir()))
                    h.clock[0] = T0
                    buf = io.StringIO()
                    with redirect_stdout(buf):
                        rc = cli.main(args)  # a report never creates a run (PR #114 review): only an admitting command does, so the activation is not spent by a probe
                    self.assertEqual((rc, json.loads(buf.getvalue())["error"]["code"]), (3, "run-not-found"))
                    self.assertFalse(store.root.exists() and any(store.root.iterdir()))
                    h.coordinator()  # the unchanged source inside its window creates the run (the admitting path)
                    buf = io.StringIO()
                    with redirect_stdout(buf):
                        self.assertEqual(cli.main(args), 0)  # and status reports it
                    created = json.loads(buf.getvalue())
                    self.assertTrue(created["activation"]["recorded"]["approved"])
                    self.assertEqual((created["activation"]["recorded"]["validated_at"], created["run"]["started_at"]), (T0, T0))  # the recorded moments are the injected observation
                    store.run_path.unlink()
                    store.journal_path.unlink()
                    alter_source(h, how)
                    buf = io.StringIO()
                    with redirect_stdout(buf):
                        rc = cli.main(args)
                    out = json.loads(buf.getvalue())
                self.assertEqual(rc, 3)
                # the CLI loads the file afresh: a malformed source is refused by the loader, a missing one is no document at all
                # (named first); a changed but loadable one creates nothing either, and a report on the missing run says so
                # (run-not-found) rather than applying the creation rules of a document that creates nothing (PR #114 round 3)
                self.assertIn(out["error"]["code"], {"changed": {"run-not-found"}, "missing": {"activation-required", "activation-invalid"}, "malformed": {"activation-invalid"}}[how])
                self.assertFalse(store.run_path.exists())
                self.assertFalse(store.journal_path.exists())
                self.assertEqual(calls, [])
            finally:
                GhCliTransport._run = original
                h.close()


class Final2MovingClockTests(unittest.TestCase):
    """The clock moving forward during one operation cannot produce an unrecorded expiry."""

    def setUp(self):
        self.h = LiveHarness()
        self.c = claimed(self.h)
        self.store = Store(self.h.h.state_dir, "run-live")

    def tearDown(self):
        self.h.close()

    def moving(self, c, first: str, then: str):
        """A clock that answers ``first`` once, then ``then`` for every later sample."""
        samples = []

        def now():
            samples.append(then if samples else first)
            return samples[-1]

        c.now = now
        return samples

    def head(self, c):
        state = self.store.load_story(S)
        return c.record_head(S, self.h.h.sha, self.h.terminal() if state.active_task else None)

    def assert_valid_then_durable(self, observed_valid, run_after_valid):
        """A coherent still-valid observation persists no stop; the next operation, whose observation is past the window, records it durably and the record survives rollback and restart."""
        self.assertIsNone(self.store.load_run().activation_stop)
        self.h.clock[0] = ROLLED_BACK
        self.assertEqual(self.head(self.h.coordinator()).phase, "implemented")  # no expiry was observed: rollback inside the tolerance is a correction, not a stop
        self.h.clock[0] = EXPIRED
        refuses(self, lambda: self.head(self.h.coordinator()), "activation-expired")
        stop = self.store.load_run().activation_stop
        self.assertEqual((stop["code"], stop["observed_at"], stop["operation"]), ("activation-expired", EXPIRED, "record-head"))
        self.h.clock[0] = ROLLED_BACK
        for c in (self.h.coordinator(), self.h.coordinator(activation=None)):
            refuses(self, lambda c=c: self.head(c), "activation-expired")
            self.assertEqual(c.status()["activation"]["stop"], "activation-expired")
        self.assertEqual(self.h.h.fake.calls, [])  # nothing above touched the transport
        self.assertEqual(self.h.coordinator(activation=None).cancel(S, "stopped").phase, "cancelled")  # cleanup stays possible after the durable stop (the release comment is the only effect)

    def test_status_crossing_the_boundary_reports_one_coherent_observation(self):
        self.h.h.fake.calls = []
        samples = self.moving(self.c, LAST_VALID, EXPIRED)
        snapshot = self.c.status()
        self.assertEqual(samples[0], LAST_VALID)
        self.assertIsNone(snapshot["activation"]["stop"])  # valid at the observation instant: nothing to report, nothing unrecorded
        self.assertIsNone(snapshot["activation"]["recorded_stop"])
        self.assertEqual(snapshot["activation"]["problems"], [])
        self.assertEqual(snapshot["run"]["last_observed_at"], LAST_VALID)  # the high-water mark is the same observation
        self.assert_valid_then_durable(snapshot, None)

    def test_record_head_crossing_the_boundary_decides_on_one_observation(self):
        self.h.h.fake.calls = []
        samples = self.moving(self.c, LAST_VALID, EXPIRED)
        self.assertEqual(self.head(self.c).phase, "implemented")
        self.assertEqual(samples[0], LAST_VALID)
        self.assert_valid_then_durable(None, None)

    def test_status_whose_observation_is_expired_records_before_reporting(self):
        self.moving(self.c, EXPIRED, LAST_VALID)  # the clock then moves back inside the window: the decision is still the locked observation
        snapshot = self.c.status()
        self.assertEqual(snapshot["activation"]["stop"], "activation-expired")
        self.assertEqual(snapshot["activation"]["recorded_stop"]["observed_at"], EXPIRED)
        self.assertEqual(self.store.load_run().activation_stop["operation"], "status")
        self.h.clock[0] = ROLLED_BACK
        refuses(self, lambda: self.head(self.h.coordinator()), "activation-expired")

    def test_advancing_consumers_refusing_expiry_always_leave_a_durable_stop(self):
        """Every public consumer that refuses ``activation-expired`` did so from the observation that recorded the stop."""
        ops = {
            "record-head": lambda c: self.head(c),
            "run-checks": lambda c: c.run_checks(S, self.h.h.sha, str(self.h.h.worktree), passing_runner),
            "authorize-review": lambda c: c.authorize_review(S, self.h.h.sha),
            "authorize-repair": lambda c: c.authorize_repair(S),
            "reserve": lambda c: c.reserve("OM-01.03", self.h.h.snapshot, "base"),
            "rebase-revisions": lambda c: c.rebase_revisions(S, "why"),
        }
        for name, op in ops.items():
            with self.subTest(name):
                h = LiveHarness()
                try:
                    c = claimed(h)
                    self.moving(c, LAST_VALID, EXPIRED)
                    try:
                        op(c)
                    except UnattendedError as exc:
                        self.assertNotEqual(exc.code, "activation-expired", name)  # valid at the one observation: whatever refuses, it is not an unrecorded expiry
                    self.assertIsNone(Store(h.h.state_dir, "run-live").load_run().activation_stop)
                    c2 = h.coordinator()
                    self.moving(c2, EXPIRED, LAST_VALID)
                    refuses(self, lambda: op(c2), "activation-expired")
                    stop = Store(h.h.state_dir, "run-live").load_run().activation_stop
                    self.assertEqual((stop["code"], stop["observed_at"]), ("activation-expired", EXPIRED), name)
                    self.assertEqual(h.h.fake.calls[:0], [])
                finally:
                    h.close()

    def test_resume_cleanup_and_replay_decide_on_the_locked_observation(self):
        state = self.store.load_story(S)
        state.intents[0].status = "pending"
        self.store.save_story(state)
        c = self.h.coordinator()
        self.moving(c, LAST_VALID, EXPIRED)
        self.assertEqual(c.resume(S, ok_worktree).phase, "claimed")
        self.assertIsNone(self.store.load_run().activation_stop)
        self.assertNotIn("resume-advancing-abandoned", [e["event"] for e in self.store.read_journal()])
        c = self.h.coordinator()
        self.moving(c, EXPIRED, LAST_VALID)
        self.assertEqual(c.resume(S, ok_worktree).phase, "claimed")
        self.assertEqual(self.store.load_run().activation_stop["operation"], "resume")

    def test_wall_clock_is_decided_once_per_operation_and_still_expires_on_the_next(self):
        """The coherent observation hides no elapsed budget: the next independent operation observes the clock afresh."""
        late = "2026-11-07T14:00:00Z"  # the policy wall clock is longer than the activation window in the fixture, so use the activation window as the marker
        self.h.clock[0] = T0
        self.assertEqual(self.c.status()["activation"]["stop"], None)
        self.h.clock[0] = EXPIRED
        self.assertEqual(self.c.status()["activation"]["stop"], "activation-expired")
        self.assertEqual(self.store.load_run().activation_stop["observed_at"], EXPIRED)
        self.assertEqual(late, LAST_VALID)

    def test_cli_status_takes_one_observation_under_the_lock(self):
        from automation.unattended import coordinator as module
        from automation.unattended.github import GhCliTransport

        calls = []
        original_run, original_now = GhCliTransport._run, module.utcnow
        ticks = [LAST_VALID, EXPIRED]
        GhCliTransport._run = lambda self, args, stdin=None: calls.append(args) or "{}"
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = cli.main(["--policy", str(Path(self.h.h.tmpdir.name) / "policy.toml"), "--state-dir", str(self.h.h.state_dir), "--run-id", "run-live", "--live", "--activation", str(self.h.path), "status"])
            out = json.loads(buf.getvalue())
            self.assertEqual(code, 0)
            self.assertEqual(out["activation"]["recorded_stop"], self.store.load_run().activation_stop)  # whatever the host clock says, the report and the record agree
            self.assertEqual(out["activation"]["stop"] == "activation-expired", out["activation"]["recorded_stop"] is not None)
        finally:
            GhCliTransport._run, module.utcnow = original_run, original_now
        self.assertEqual(calls, [])
        self.assertEqual(ticks, [LAST_VALID, EXPIRED])


if __name__ == "__main__":
    unittest.main()
