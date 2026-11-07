"""Repair round 2 of the enabling change: the three findings (F1-F3) of the independent review of
aa80168 (review-aa80168.md). Every scenario runs on the fixture transport marked live with
temporary state; no real GitHub call and no real task is ever made.

F1  a genuine run.json restored from another run (same policy, legitimately activated) is a
    foreign record: every consumer and every public Store entrypoint refuses ``run-identity-mismatch``
    without transport calls, without rewriting the record and without touching the obligations.
F2  persisted temporal facts are validated at the load boundary: ``validated_at`` must be present
    and inside the approval window; ``last_observed_at`` and ``activation_stop`` are null or exactly
    the supported record; nothing malformed is read as "no control" or replaced by the current time.
F3  ``status`` runs under the same locked gate as every other consumer: it reloads and validates
    the run, re-reads the source and records an observed expiry or clock regression durably, so a
    stop first seen by status survives rollback and restart for admission, review authorization,
    proposal and replay; a valid recorded binding without the file still reports."""

from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from automation.tests.support import IMPLEMENTER, REVIEWER, controlled_cli_clock, ok_worktree, passing_runner
from automation.tests.test_activation import S, T0, LiveHarness, activation_text
from automation.tests.test_enabling_repair_1 import claimed, refuses
from automation.unattended import cli
from automation.unattended.activation import load_activation
from automation.unattended.errors import Refused
from automation.unattended.state import Store

NO_CALLS: list = []
EXPIRED = "2026-11-07T14:00:01Z"


def story_bytes(h: LiveHarness, run_id="run-live") -> bytes:
    return Store(h.h.state_dir, run_id).story_path(S).read_bytes()


def write_run(h: LiveHarness, mutate, run_id="run-live") -> bytes:
    """Mutate the persisted run record through the raw JSON (the way a restore or a hand edit
    would), return the bytes written so the test can prove nothing rewrote them."""
    store = Store(h.h.state_dir, run_id)
    raw = json.loads(store.run_path.read_text(encoding="utf-8"))
    mutate(raw)
    store.run_path.write_text(json.dumps(raw, indent=1, sort_keys=True), encoding="utf-8")
    return store.run_path.read_bytes()


class F1ForeignRunRecordTests(unittest.TestCase):
    """A genuine donor run.json copied into another run directory authorizes nothing there."""

    def setUp(self):
        self.h = LiveHarness()
        self.c = claimed(self.h)
        donor_path = self.h.path.parent / "donor.toml"
        donor_path.write_text(activation_text(self.h.h.policy, run_id="donor-run"), encoding="utf-8")
        self.donor = self.h.coordinator(run_id="donor-run", activation=load_activation(donor_path))  # legitimately created through the public creation API
        self.store = Store(self.h.h.state_dir, "run-live")
        self.story_before = story_bytes(self.h)
        self.store.run_path.write_bytes(self.donor.store.run_path.read_bytes())
        self.run_before = self.store.run_path.read_bytes()
        self.h.h.fake.calls = []

    def tearDown(self):
        self.h.close()

    def unchanged(self):
        self.assertEqual(self.store.run_path.read_bytes(), self.run_before, "the foreign record was rewritten")
        self.assertEqual(story_bytes(self.h), self.story_before, "the recipient's obligations changed")
        self.assertEqual(self.h.h.fake.calls, NO_CALLS)

    def test_every_fresh_consumer_refuses_at_construction_with_and_without_the_file(self):
        for activation in ("file", None):
            refuses(self, lambda: self.h.coordinator(activation=activation), "run-identity-mismatch")
        self.unchanged()

    def test_same_instance_consumers_refuse_on_the_fresh_locked_reload(self):
        c = self.c
        for op in (lambda: c.cancel(S, "recovery", self.h.terminal()), lambda: c.cancel_run("recovery"), lambda: c.block(S, "x", self.h.terminal()),
                   lambda: c.record_task_terminal(S, self.h.terminal()), lambda: c.bind_receipt(S, REVIEWER, worktree_check=ok_worktree),
                   lambda: c.resume(S, ok_worktree), lambda: c.record_head(S, self.h.h.sha, self.h.terminal()), lambda: c.status(),
                   lambda: c.reserve("OM-01.03", self.h.h.snapshot, "base")):
            refuses(self, op, "run-identity-mismatch")
        self.unchanged()
        self.assertEqual(self.store.load_story(S).phase, "claimed")

    def test_public_store_entrypoints_refuse_the_foreign_record(self):
        policy = self.h.h.policy
        refuses(self, self.store.load_run, "run-identity-mismatch")
        refuses(self, self.store.bound_run, "run-identity-mismatch")
        refuses(self, lambda: self.store.ensure_run(policy.repo_slug, policy.digest, "live", activation=self.h.activation, policy=policy, now=T0), "run-identity-mismatch")
        refuses(self, lambda: self.store.ensure_run(policy.repo_slug, policy.digest, "live"), "run-identity-mismatch")
        refuses(self, lambda: self.store.ensure_run(policy.repo_slug, policy.digest, "fixture"), "run-identity-mismatch")
        self.unchanged()
        self.assertEqual(self.donor.store.load_run().run_id, "donor-run")  # the donor itself stays a valid run

    def test_late_receipt_and_pending_cleanup_replay_refuse_before_any_effect(self):
        state = self.store.load_story(S)
        state.intents[0].status = "pending"  # a cleanup replay would otherwise post on resume
        self.store.save_story(state)
        self.story_before = story_bytes(self.h)
        refuses(self, lambda: self.h.coordinator(activation=None), "run-identity-mismatch")
        refuses(self, lambda: self.c.resume(S, ok_worktree), "run-identity-mismatch")
        refuses(self, lambda: self.c.bind_receipt(S, REVIEWER, worktree_check=ok_worktree), "run-identity-mismatch")
        self.unchanged()

    def test_cli_reports_the_structured_refusal_without_calls(self):
        from automation.unattended.github import GhCliTransport

        calls = []
        original = GhCliTransport._run
        GhCliTransport._run = lambda self, args, stdin=None: calls.append(args) or "{}"
        try:
            for argv in (["status"], ["cancel", S, "--reason", "r", "--task-evidence", json.dumps(self.h.terminal())], ["cancel-run", "--reason", "r"]):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = cli.main(["--policy", str(Path(self.h.h.tmpdir.name) / "policy.toml"), "--state-dir", str(self.h.h.state_dir), "--run-id", "run-live", "--live", *argv])
                self.assertEqual((code, json.loads(buf.getvalue())["error"]["code"]), (3, "run-identity-mismatch"), argv)
        finally:
            GhCliTransport._run = original
        self.assertEqual(calls, [])
        self.unchanged()

    def test_mutated_run_ids_in_both_records_are_the_same_foreign_record(self):
        self.store.run_path.write_bytes(self.c.store.run_path.read_bytes())  # back to the genuine record…
        self.run_before = write_run(self.h, lambda raw: (raw.__setitem__("run_id", "run-x"), raw["activation"].__setitem__("run_id", "run-x")))  # …then both identities edited consistently
        refuses(self, lambda: self.h.coordinator(activation=None).cancel(S, "recovery", self.h.terminal()), "run-identity-mismatch")
        self.run_before = write_run(self.h, lambda raw: (raw.__setitem__("run_id", "run-live"), raw["activation"].__setitem__("run_id", "run-x")))  # run id right, binding foreign
        refuses(self, lambda: self.h.coordinator(activation=None).cancel(S, "recovery", self.h.terminal()), "activation-binding-invalid")
        self.unchanged()


class F2PersistedTemporalFactsTests(unittest.TestCase):
    def setUp(self):
        self.h = LiveHarness()
        self.c = claimed(self.h)
        self.store = Store(self.h.h.state_dir, "run-live")

    def tearDown(self):
        self.h.close()

    def check(self, mutate, code, *, same_instance_ops=True):
        story_before = story_bytes(self.h)
        run_before = write_run(self.h, mutate)
        self.h.h.fake.calls = []
        refuses(self, lambda: self.h.coordinator(activation=None), code)
        refuses(self, lambda: self.h.coordinator(), code)
        refuses(self, self.store.bound_run, code)
        ops = [lambda: self.c.cancel(S, "recovery", self.h.terminal()), lambda: self.c.cancel_run("recovery"), lambda: self.c.record_head(S, self.h.h.sha, self.h.terminal()),
               lambda: self.c.status(), lambda: self.c.resume(S, ok_worktree), lambda: self.c.bind_receipt(S, REVIEWER, worktree_check=ok_worktree), lambda: self.c.record_task_terminal(S, self.h.terminal())]
        for op in ops:
            refuses(self, op, code)
        self.assertEqual(self.store.run_path.read_bytes(), run_before, "malformed metadata was rewritten or replaced")
        self.assertEqual(story_bytes(self.h), story_before)
        self.assertEqual(self.h.h.fake.calls, NO_CALLS)

    def test_validated_at_must_be_present_and_inside_the_approval_window(self):
        for value in (None, "2026-11-06T10:00:00Z", "2026-11-07T15:00:00Z", "2026-11-07T10:00:00", "2026-11-07", 1, True, ""):
            with self.subTest(value=value):
                self.check(lambda raw, v=value: raw["activation"].__setitem__("validated_at", v), "activation-binding-invalid")

    def test_window_wider_than_the_maximum_is_not_a_binding(self):
        self.check(lambda raw: raw["activation"].__setitem__("expires_at", "2026-11-09T10:00:01Z"), "activation-binding-invalid")

    def test_high_water_mark_is_null_or_a_strict_timestamp_and_never_replaced_by_now(self):
        for value in ("bad", "2026-11-07", "2026-11-07T11:00:00", 0, False, [], {}):
            with self.subTest(value=value):
                self.check(lambda raw, v=value: raw.__setitem__("last_observed_at", v), "run-state-invalid")

    def test_stop_record_is_null_or_exactly_the_supported_record(self):
        good = {"code": "activation-expired", "observed_at": EXPIRED, "message": "m", "operation": "record-head"}
        bad = [[], False, "", "activation-expired", 0, {}, {"code": "activation-expired"}, {**good, "extra": 1}, {**good, "code": "run-cancelled"}, {**good, "code": "activation-required"},
               {**good, "observed_at": "2026-11-07T14:00:01"}, {**good, "observed_at": None}, {**good, "message": ""}, {**good, "message": 3}, {**good, "operation": None}]
        for value in bad:
            with self.subTest(value=value):
                self.check(lambda raw, v=value: raw.__setitem__("activation_stop", v), "run-state-invalid")
        # the supported record itself stays a durable stop: advancing refuses with it, cleanup proceeds
        write_run(self.h, lambda raw: raw.__setitem__("activation_stop", good))
        c = self.h.coordinator(activation=None)
        refuses(self, lambda: c.record_head(S, self.h.h.sha, self.h.terminal()), "activation-expired")
        self.assertEqual(c.status()["activation"]["recorded_stop"], good)
        self.assertEqual(c.cancel(S, "stopped", self.h.terminal()).phase, "cancelled")

    def test_unknown_or_missing_record_keys_and_wrong_types_refuse_as_run_state(self):
        for mutate in (lambda raw: raw.__setitem__("rogue", 1), lambda raw: raw.pop("repo"), lambda raw: raw.__setitem__("cancelled", "no"), lambda raw: raw.__setitem__("environment", "prod"),
                       lambda raw: raw.__setitem__("delegated_tasks", True), lambda raw: raw.__setitem__("stop_reason", 5)):
            with self.subTest(mutate=mutate):
                self.check(mutate, "run-state-invalid")

    def test_unreadable_json_is_a_structured_refusal(self):
        self.store.run_path.write_text("{not json", encoding="utf-8")
        self.h.h.fake.calls = []
        refuses(self, lambda: self.h.coordinator(activation=None), "run-state-invalid")
        refuses(self, lambda: self.c.cancel(S, "recovery", self.h.terminal()), "run-state-invalid")
        self.assertEqual(self.h.h.fake.calls, NO_CALLS)

    def test_legacy_record_without_the_live_only_fields_still_loads_and_valid_expired_cleanup_still_works(self):
        write_run(self.h, lambda raw: [raw.pop(k) for k in ("activation", "activation_stop", "last_observed_at")], run_id="run-live")
        bare = self.h.coordinator(activation=None)  # loads: the three controls read as null
        refuses(self, lambda: bare.cancel(S, "recovery", self.h.terminal()), "activation-required")  # a live record without a binding was never activated: nothing releases on it
        refuses(self, bare.status, "activation-required")
        self.h.h.fake.live = False
        fixture_store = Store(self.h.h.state_dir, "fixture-run")
        fixture_store.ensure_run(self.h.h.policy.repo_slug, self.h.h.policy.digest, "fixture")
        write_run(self.h, lambda raw: [raw.pop(k) for k in ("activation", "activation_stop", "last_observed_at")], run_id="fixture-run")
        self.assertIsNone(fixture_store.load_run().activation)
        self.h.h.fake.live = True
        # a valid record whose window merely expired still releases (expiry stops advancement, never cleanup)
        h2 = LiveHarness()
        try:
            claimed(h2)
            h2.clock[0] = EXPIRED
            self.assertEqual(h2.coordinator(activation=None).cancel(S, "expired", h2.terminal()).phase, "cancelled")
        finally:
            h2.close()


class F3StatusUnderTheSharedGateTests(unittest.TestCase):
    def setUp(self):
        self.h = LiveHarness()
        self.c = claimed(self.h)
        self.store = Store(self.h.h.state_dir, "run-live")

    def tearDown(self):
        self.h.close()

    def advancing_ops(self, c):
        return (lambda: c.record_head(S, self.h.h.sha, self.h.terminal()), lambda: c.authorize_review(S, self.h.h.sha), lambda: c.propose_evidence(S, self.h.h.sha, 1, [], "x"),
                lambda: c.reserve("OM-01.03", self.h.h.snapshot, "base"), lambda: c.rebase_revisions(S, "x"))

    def test_status_only_expiry_is_durable_across_rollback_and_restart(self):
        self.h.clock[0] = EXPIRED
        snapshot = self.c.status()
        self.assertEqual(snapshot["activation"]["stop"], "activation-expired")
        self.assertEqual(snapshot["activation"]["recorded_stop"]["code"], "activation-expired")
        self.assertEqual(snapshot["run"]["activation_stop"], snapshot["activation"]["recorded_stop"])  # coherent: the reported run is the persisted run
        self.assertEqual(self.store.load_run().activation_stop["operation"], "status")
        self.assertIn("activation-stopped", [e["event"] for e in self.store.read_journal()])
        self.h.clock[0] = T0
        for c in (self.c, self.h.coordinator(), self.h.coordinator(activation=None)):
            for op in self.advancing_ops(c):
                refuses(self, op, "activation-expired")
            self.assertEqual(c.status()["activation"]["stop"], "activation-expired")
        state = self.store.load_story(S)
        state.intents[0].status = "pending"
        self.store.save_story(state)
        self.assertEqual(self.h.coordinator().resume(S, ok_worktree).phase, "claimed")
        self.assertIn("resume-advancing-abandoned", [e["event"] for e in self.store.read_journal()])
        self.assertEqual(self.h.coordinator(activation=None).cancel(S, "stopped", self.h.terminal()).phase, "cancelled")

    def test_status_only_high_water_then_rollback_is_a_durable_clock_regression(self):
        self.h.clock[0] = "2026-11-07T12:00:00Z"
        self.assertIsNone(self.c.status()["activation"]["stop"])
        self.assertEqual(self.store.load_run().last_observed_at, "2026-11-07T12:00:00Z")
        self.h.clock[0] = "2026-11-07T11:57:00Z"  # inside the tolerance
        self.assertIsNone(self.h.coordinator().status()["activation"]["stop"])
        self.h.clock[0] = T0
        self.assertEqual(self.h.coordinator().status()["activation"]["stop"], "clock-regression")
        self.assertEqual(self.store.load_run().activation_stop["code"], "clock-regression")
        self.h.clock[0] = "2026-11-07T12:30:00Z"  # the clock "recovers": the stop stays
        for op in self.advancing_ops(self.h.coordinator()):
            refuses(self, op, "clock-regression")
        self.assertEqual(self.h.coordinator(activation=None).cancel(S, "stopped", self.h.terminal()).phase, "cancelled")

    def test_status_reports_fresh_persisted_facts_not_cached_ones(self):
        other = self.h.coordinator(activation=None)
        self.h.clock[0] = EXPIRED
        refuses(self, lambda: self.h.coordinator().record_head(S, self.h.h.sha, self.h.terminal()), "activation-expired")  # another instance records the stop
        self.h.clock[0] = T0
        self.assertEqual(other.status()["activation"]["recorded_stop"]["operation"], "record-head")  # the long-lived instance reports the persisted stop, not its cache
        self.assertEqual(other.status()["run"]["activation_stop"]["code"], "activation-expired")

    def test_status_without_the_file_reports_on_the_recorded_binding_but_a_changed_or_malformed_source_refuses(self):
        bare = self.h.coordinator(activation=None)
        self.assertIsNone(bare.status()["activation"]["presented"])
        self.assertEqual(bare.status()["activation"]["stop"], "activation-required")
        c = self.c
        self.h.path.write_text(activation_text(self.h.h.policy, expires="2026-11-07T15:00:00Z"), encoding="utf-8")
        refuses(self, c.status, "activation-mismatch")
        self.h.path.write_text("approved = \n", encoding="utf-8")
        refuses(self, c.status, "activation-invalid")
        self.h.path.unlink()
        self.assertEqual(c.status()["activation"]["stop"], "activation-required")  # missing file: cleanup/status route on the recorded binding
        self.assertIsNone(c.status()["activation"]["presented"])
        self.assertEqual(self.store.load_story(S).phase, "claimed")

    def test_fixture_status_is_unaffected(self):
        self.h.h.fake.live = False
        store = Store(self.h.h.state_dir, "fixture-run")
        from automation.unattended.coordinator import Coordinator
        c = Coordinator(self.h.h.fake, self.h.h.policy, store, now=lambda: self.h.clock[0])
        status = c.status()
        self.assertEqual((status["environment"], status["activation"]["stop"], status["activation"]["problems"]), ("fixture", None, []))

    def test_cli_status_records_the_observed_stop(self):
        from automation.unattended.github import GhCliTransport

        calls = []
        original = GhCliTransport._run
        GhCliTransport._run = lambda self, args, stdin=None: calls.append(args) or "{}"
        args = ["--policy", str(Path(self.h.h.tmpdir.name) / "policy.toml"), "--state-dir", str(self.h.h.state_dir), "--run-id", "run-live", "--live", "status"]

        def status():
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = cli.main(args)
            return code, json.loads(buf.getvalue())

        try:
            self.h.h.fake.live = True
            with controlled_cli_clock(self.h.clock):  # the CLI observes the injected clock, never the host clock
                self.h.clock[0] = T0
                code, out = status()
                self.assertEqual((code, out["activation"]["stop"]), (0, "activation-required"))  # inside the window the no-file route reports; nothing is recorded
                self.assertIsNone(self.store.load_run().activation_stop)
                self.h.clock[0] = EXPIRED
                code, out = status()
                self.assertEqual((code, out["activation"]["stop"]), (0, "activation-expired"))  # the first observation past the window is recorded by status itself
                stop = self.store.load_run().activation_stop
                self.assertEqual((stop["code"], stop["observed_at"], stop["operation"]), ("activation-expired", EXPIRED, "status"))
                self.assertEqual(out["activation"]["recorded_stop"], stop)
                self.h.clock[0] = T0  # a later observation inside the window again (rollback) does not lift the durable stop
                code, out = status()
                self.assertEqual((code, out["activation"]["stop"], out["activation"]["recorded_stop"]), (0, "activation-expired", stop))
                refuses(self, lambda: self.h.coordinator().record_head(S, self.h.h.sha, self.h.terminal()), "activation-expired")
        finally:
            GhCliTransport._run = original
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
