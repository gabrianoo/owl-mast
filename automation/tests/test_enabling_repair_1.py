"""Repair round 1 of the enabling change: the six findings (R1-R6) of the independent review of
96ad53a (review-96ad53a.md). Every scenario runs on the fixture transport marked live with
temporary state; no real GitHub call and no real task is ever made."""

from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from automation.tests.support import IMPLEMENTER, REVIEWER, controlled_cli_clock, ok_worktree, passing_runner
from automation.tests.test_activation import S, T0, LiveHarness, activation_text
from automation.unattended import cli
from automation.unattended.activation import Activation, load_activation
from automation.unattended.errors import Refused, UnattendedError
from automation.unattended.state import Store

NO_CALLS: list = []
EXPIRED = "2026-11-07T14:00:01Z"  # one second past the fixture window: an injected observation, not the host clock


def POLICY(h: LiveHarness) -> Path:
    return Path(h.h.tmpdir.name) / "policy.toml"


def claimed(h: LiveHarness, run_id="run-live"):
    c = h.coordinator(run_id=run_id)
    c.reserve(S, h.h.snapshot, "base")
    c.bind_receipt(S, IMPLEMENTER, str(h.h.worktree), "t3/om-01-02", ok_worktree)
    return c


def refuses(test, fn, *codes):
    with test.assertRaises(UnattendedError) as ctx:
        fn()
    test.assertIn(ctx.exception.code, codes, str(ctx.exception))
    return ctx.exception


class R1MissingRunMetadataTests(unittest.TestCase):
    """Retained artifacts without run.json are an incomplete restore, never a pristine run."""

    def check(self, prepare):
        h = LiveHarness(run_id="run-1")
        try:
            h.h.fake.live = False
            h.h.claim()
            prepare(h)
            h.h.fake.live = True
            store = Store(h.h.state_dir, "run-1")
            before = {p: p.read_bytes() for p in store.root.rglob("*") if p.is_file()}
            store.run_path.unlink()
            h.h.fake.calls = []
            refuses(self, lambda: h.coordinator(run_id="run-1"), "run-metadata-missing")
            refuses(self, lambda: store.ensure_run(h.h.policy.repo_slug, h.h.policy.digest, "live", activation=h.activation, policy=h.h.policy, now=T0), "run-metadata-missing")
            refuses(self, lambda: store.ensure_run(h.h.policy.repo_slug, h.h.policy.digest, "fixture"), "run-metadata-missing")
            self.assertFalse(store.run_path.exists())
            self.assertEqual({p: p.read_bytes() for p in store.root.rglob("*") if p.is_file()}, {p: b for p, b in before.items() if p != store.run_path})
            self.assertEqual(h.h.fake.calls, NO_CALLS)
            args = ["--policy", str(POLICY(h)), "--activation", str(h.path), "--state-dir", str(h.h.state_dir), "--run-id", "run-1", "status"]
            # The CLI decides on an injected observation, never the host clock: inside the window the
            # retained artifacts are the refusal; past it the expired observation is, and still nothing is written.
            with controlled_cli_clock(h.clock):
                for observation, expected in ((T0, "run-metadata-missing"), (EXPIRED, "activation-expired"), (T0, "run-metadata-missing")):
                    h.clock[0] = observation
                    buf = io.StringIO()
                    with redirect_stdout(buf):
                        code = cli.main(args)
                    self.assertEqual(code, 3, observation)
                    self.assertEqual(json.loads(buf.getvalue())["error"]["code"], expected, observation)
                    self.assertFalse(store.run_path.exists(), observation)
                    self.assertEqual({p: p.read_bytes() for p in store.root.rglob("*") if p.is_file()}, {p: b for p, b in before.items() if p != store.run_path}, observation)
            self.assertEqual(h.h.fake.calls, NO_CALLS)
        finally:
            h.close()

    def test_claimed_story_with_active_task(self):
        self.check(lambda h: None)

    def test_pending_claim_intent_and_terminal_history(self):
        def prepare(h):
            st = h.h.store.load_story(S)
            st.intents[0].status = "pending"
            st.task_history.append({"taskId": "old", "runId": "old:run:1", "status": "completed", "role": "implementer", "at": T0, "operation": "record-head"})
            h.h.store.save_story(st)
        self.check(prepare)

    def test_journal_only(self):
        def prepare(h):
            h.h.store.story_path(S).unlink()
        self.check(prepare)


class R2BindingProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.h = LiveHarness()
        self.c = claimed(self.h)
        self.store = Store(self.h.h.state_dir, "run-live")

    def tearDown(self):
        self.h.close()

    def corrupt(self, binding):
        run = self.store.load_run()
        run.activation = binding
        self.store.save_run(run)

    def test_partial_or_foreign_persisted_bindings_refuse_every_consumer_without_effects(self):
        good = self.store.load_run().activation
        cases = {"id-only": {"id": "partial"}, "digest-only": {"digest": "partial"}, "string": "bad", "list": [1], "foreign-run": {**good, "run_id": "other"},
                 "foreign-repo": {**good, "repository": "x/y"}, "foreign-digest": {**good, "policy_digest": "0" * 64}, "unapproved": {**good, "approved": False},
                 "truthy-approved": {**good, "approved": 1}, "naive-expiry": {**good, "expires_at": "2026-11-07T14:00:00"}, "extra-key": {**good, "token": "x"}, "fixture-env": {**good, "environment": "fixture"}}
        for name, binding in cases.items():
            self.corrupt(binding)
            self.h.h.fake.calls = []
            for activation in (None, "file"):
                refuses(self, lambda: self.h.coordinator(activation=activation), "activation-binding-invalid")
            for op in (lambda: self.c.cancel(S, "x", self.h.terminal()), lambda: self.c.block(S, "x", self.h.terminal()), lambda: self.c.record_task_terminal(S, self.h.terminal()),
                       lambda: self.c.cancel_run("x", {S: self.h.terminal()}), lambda: self.c.resume(S, ok_worktree), lambda: self.c.record_head(S, self.h.h.sha, self.h.terminal()),
                       lambda: self.c.record_no_launch(S, {"authorization": "run-live:OM-01.02:1"}), lambda: self.c.rebase_revisions(S, "x")):
                refuses(self, op, "activation-binding-invalid")
            self.assertEqual(self.h.h.fake.calls, NO_CALLS, name)
            state = self.store.load_story(S)
            self.assertEqual((state.phase, state.active_task["taskId"]), ("claimed", IMPLEMENTER["taskId"]), name)
            self.assertEqual(self.store.load_run().activation, binding, name)  # nothing replaced or migrated
        self.corrupt(good)
        self.assertEqual(self.c.cancel(S, "authorized cleanup", self.h.terminal()).phase, "cancelled")  # positive control on the valid binding
        self.assertIn("post_comment", self.h.h.fake.calls)

    def test_public_store_cannot_record_a_dictionary_or_an_unapproved_activation(self):
        policy = self.h.h.policy
        for label, kwargs in {"dict": dict(activation=self.h.activation.binding()), "none": {}, "no-policy": dict(activation=self.h.activation), "no-now": dict(activation=self.h.activation, policy=policy)}.items():
            st = Store(self.h.h.state_dir, "run-public")
            refuses(self, lambda: st.ensure_run(policy.repo_slug, policy.digest, "live", **kwargs), "activation-required")
            self.assertFalse(st.run_path.exists(), label)
        other = Path(self.h.h.tmpdir.name) / "unapproved.toml"
        other.write_text(activation_text(policy, run_id="foreign-run", approved=False), encoding="utf-8")
        st = Store(self.h.h.state_dir, "run-live-2")
        refuses(self, lambda: st.ensure_run(policy.repo_slug, policy.digest, "live", activation=load_activation(other), policy=policy, now=T0), "activation-mismatch", "activation-unapproved")
        other.write_text(activation_text(policy, run_id="run-live-2", approved=False), encoding="utf-8")
        refuses(self, lambda: st.ensure_run(policy.repo_slug, policy.digest, "live", activation=load_activation(other), policy=policy, now=T0), "activation-unapproved")
        self.assertFalse(st.run_path.exists())
        self.assertFalse(st.root.exists())

    def test_same_instance_reload_checks_the_persisted_binding_before_advancing(self):
        run = self.store.load_run()
        run.activation = None
        self.store.save_run(run)
        refuses(self, lambda: self.c.record_head(S, self.h.h.sha, self.h.terminal()), "activation-required")
        refuses(self, lambda: self.c.cancel(S, "x", self.h.terminal()), "activation-required")
        state = self.store.load_story(S)
        self.assertEqual((state.phase, state.head_sha, state.active_task["taskId"]), ("claimed", None, IMPLEMENTER["taskId"]))

    def test_record_shape_is_complete_and_validated(self):
        binding = self.store.load_run().activation
        self.assertEqual(set(binding), {"id", "digest", "approver", "issued_at", "expires_at", "path", "repository", "policy_digest", "environment", "run_id", "approved", "validated_at"})
        self.assertEqual((binding["run_id"], binding["approved"], binding["validated_at"], binding["environment"]), ("run-live", True, T0, "live"))


class R3SourceRereadTests(unittest.TestCase):
    def setUp(self):
        self.h = LiveHarness()
        self.c = claimed(self.h)
        self.store = Store(self.h.h.state_dir, "run-live")

    def tearDown(self):
        self.h.close()

    def test_changed_source_refuses_advancing_and_cleanup_on_the_same_instance(self):
        self.h.path.write_text(self.h.path.read_text().replace("approved = true", "approved = false"), encoding="utf-8")
        self.h.h.fake.calls = []
        refuses(self, lambda: self.c.record_head(S, self.h.h.sha, self.h.terminal()), "activation-mismatch")
        refuses(self, lambda: self.c.cancel(S, "x", self.h.terminal()), "activation-mismatch")
        refuses(self, lambda: self.c.resume(S, ok_worktree), "activation-mismatch")
        self.assertEqual(self.h.h.fake.calls, NO_CALLS)
        state = self.store.load_story(S)
        self.assertEqual((state.phase, state.head_sha), ("claimed", None))
        self.h.path.write_text(activation_text(self.h.h.policy), encoding="utf-8")  # restored byte-identically: the same document again
        self.assertEqual(self.c.record_head(S, self.h.h.sha, self.h.terminal()).head_sha, self.h.h.sha)

    def test_malformed_source_refuses_until_omitted(self):
        self.h.path.write_text("approved = \n", encoding="utf-8")
        refuses(self, lambda: self.c.record_head(S, self.h.h.sha, self.h.terminal()), "activation-invalid")
        refuses(self, lambda: self.c.cancel(S, "x", self.h.terminal()), "activation-invalid")
        self.assertEqual(self.store.load_story(S).phase, "claimed")
        bare = self.h.coordinator(activation=None)
        self.assertEqual(bare.cancel(S, "cleanup on the recorded binding", self.h.terminal()).phase, "cancelled")

    def test_missing_source_stops_advancement_but_cleanup_proceeds_on_the_recorded_binding(self):
        self.c.record_head(S, self.h.h.sha, self.h.terminal())
        self.c.run_checks(S, self.h.h.sha, str(self.h.h.worktree), passing_runner)
        self.c.authorize_review(S, self.h.h.sha)
        self.h.path.unlink()
        self.h.h.fake.calls = []
        refuses(self, lambda: self.c.record_head(S, self.h.h.sha), "activation-required")
        refuses(self, lambda: self.c.authorize_repair(S), "activation-required")
        exc = refuses(self, lambda: self.c.bind_receipt(S, REVIEWER, worktree_check=ok_worktree), "activation-required")
        self.assertNotIn("bound_for_cleanup", exc.detail)  # a missing file is not a run stop (PR #108 review): nothing is bound, the slot is not spent for cleanup
        state = self.store.load_story(S)
        self.assertEqual((state.phase, state.active_task, state.unresolved_authorization()["status"]), ("review-authorized", None, "pending"))
        self.assertEqual(self.h.h.fake.calls, NO_CALLS)
        self.h.path.write_text(activation_text(self.h.h.policy), encoding="utf-8")  # the same document presented again (a fresh instance: this one saw the source go): the receipt binds for work
        self.assertEqual(self.h.coordinator().bind_receipt(S, REVIEWER, worktree_check=ok_worktree).phase, "review-requested")
        self.h.path.unlink()
        refuses(self, lambda: self.c.record_review(S, self.h.h.sha, "approved", "r.md", self.h.terminal()), "activation-required")
        state = self.store.load_story(S)
        self.assertEqual((state.phase, state.active_task["taskId"]), ("review-requested", REVIEWER["taskId"]))
        self.assertEqual(self.c.cancel(S, "source gone", self.h.terminal()).phase, "cancelled")
        self.assertTrue(any("kind=release" in c_.body for c_ in self.h.h.fake.comments[21]))

    def test_missing_source_on_resume_defers_advancing_replays_and_keeps_cleanup(self):
        state = self.store.load_story(S)
        state.intents[0].status = "pending"
        self.store.save_story(state)
        self.h.path.unlink()
        state = self.c.resume(S, ok_worktree)
        self.assertEqual(state.phase, "claimed")
        events = [e["event"] for e in self.store.read_journal()]
        self.assertIn("resume-advancing-deferred", events)  # a missing file on a healthy run defers the replay (PR #108 review); it never abandons it
        self.assertNotIn("resume-advancing-abandoned", events)
        self.assertEqual(self.store.load_story(S).intents[0].status, "pending")
        self.assertEqual(len([c_ for c_ in self.h.h.fake.comments[21] if "kind=claim" in c_.body]), 1)
        self.h.path.write_text(activation_text(self.h.h.policy), encoding="utf-8")
        self.h.coordinator().resume(S, ok_worktree)  # with the same document presented again the replay completes (marker adopted, nothing reposted)
        self.assertEqual(self.store.load_story(S).intents[0].status, "done")
        self.assertEqual(len([c_ for c_ in self.h.h.fake.comments[21] if "kind=claim" in c_.body]), 1)


class R4TimestampTests(unittest.TestCase):
    def test_naive_malformed_and_date_only_timestamps_refuse_at_load_and_through_the_cli(self):
        h = LiveHarness()
        try:
            cases = {"naive-issued": dict(issued="2026-11-07T10:00:00"), "naive-expires": dict(expires="2026-11-07T14:00:00"), "both-naive": dict(issued="2026-11-07T10:00:00", expires="2026-11-07T14:00:00"),
                     "date-only": dict(issued="2026-11-07"), "garbage": dict(issued="not a time"), "year-overflow": dict(expires="99999-01-01T00:00:00Z"), "number": dict(issued="1")}
            for name, over in cases.items():
                path = Path(h.h.tmpdir.name) / f"{name}.toml"
                text = activation_text(h.h.policy, **over).replace('issued_at = "1"', "issued_at = 1")
                path.write_text(text, encoding="utf-8")
                exc = refuses(self, lambda: load_activation(path), "activation-invalid")
                self.assertTrue(exc.detail.get("problems"), name)
                refuses(self, lambda: LiveHarness(**over), "activation-invalid") if name != "number" else None
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = cli.main(["--policy", str(POLICY(h)), "--activation", str(path), "--state-dir", str(Path(h.h.tmpdir.name) / "cli-state"), "--run-id", "run-live", "status"])
                self.assertEqual((code, json.loads(buf.getvalue())["error"]["code"]), (3, "activation-invalid"), name)
            self.assertFalse((Path(h.h.tmpdir.name) / "cli-state").exists())
        finally:
            h.close()

    def test_offsets_normalize_and_injected_now_is_validated_structurally(self):
        h = LiveHarness(issued="2026-11-07T12:00:00+02:00", expires="2026-11-07T16:00:00+02:00")
        try:
            self.assertEqual((h.activation.issued_at, h.activation.expires_at), ("2026-11-07T10:00:00Z", "2026-11-07T14:00:00Z"))
            for now, code in (("2026-11-07T11:00:00", "activation-invalid"), ("2026-11-07", "activation-invalid"), ("", "activation-invalid"), ("0001-01-01T00:00:00Z", "activation-not-yet-valid"), ("9999-12-31T23:59:59Z", "activation-expired")):
                self.assertEqual(Activation.stop_code(h.activation.problems(h.h.policy, "run-live", now)), code, now)
            h.clock[0] = "2026-11-07T11:00:00"  # a naive injected clock on a live coordinator refuses, it never crashes
            refuses(self, lambda: h.coordinator(), "activation-invalid")
            self.assertIsNone(Store(h.h.state_dir, "run-live").load_run())
            h.clock[0] = T0
            c = claimed(h)
            h.clock[0] = "2026-11-07T11:00:00"
            refuses(self, lambda: c.record_head(S, h.h.sha, h.terminal()), "activation-invalid")
            self.assertEqual(Store(h.h.state_dir, "run-live").load_story(S).phase, "claimed")
        finally:
            h.close()


class R5NestedTargetTests(unittest.TestCase):
    def test_unknown_nested_keys_and_lossy_types_refuse_at_load_and_through_check_activation(self):
        h = LiveHarness()
        try:
            base = activation_text(h.h.policy)
            cases = {
                "implementer-unknown": base.replace('isolation = "worktree",', 'isolation = "worktree", surprise = "ignored",'),
                "reviewer-unknown": base.replace('options = { reasoningEffort = "high" } }', 'options = { reasoningEffort = "high" }, budget = 3 }'),
                "option-int": base.replace('effort = "high"', "effort = 1"),
                "option-bool": base.replace('reasoningEffort = "high"', "reasoningEffort = true"),
                "option-table": base.replace('reasoningEffort = "high"', 'reasoningEffort = { x = "y" }'),
                "model-int": base.replace('model = "gpt-6-astra"', "model = 6"),
                "isolation-bool": base.replace('isolation = "worktree"', "isolation = true"),
                "empty-options": base.replace('options = { effort = "high" }', "options = { }"),
            }
            for name, text in cases.items():
                path = Path(h.h.tmpdir.name) / f"{name}.toml"
                path.write_text(text, encoding="utf-8")
                refuses(self, lambda: load_activation(path), "activation-invalid")
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = cli.main(["--policy", str(POLICY(h)), "--activation", str(path), "--run-id", "run-live", "check-activation"])
                self.assertEqual((code, json.loads(buf.getvalue())["error"]["code"]), (3, "activation-invalid"), name)
            self.assertEqual(load_activation(h.path).problems(h.h.policy, "run-live", T0), [])  # the unchanged document stays current
        finally:
            h.close()


class R6DurableStopTests(unittest.TestCase):
    def setUp(self):
        self.h = LiveHarness()
        self.c = claimed(self.h)
        self.store = Store(self.h.h.state_dir, "run-live")

    def tearDown(self):
        self.h.close()

    def budget_and_approvals(self):
        run, st = self.store.load_run(), self.store.load_story(S)
        return run.activation, [a["status"] for a in st.authorizations], self.store.story_counts()

    def test_observed_expiry_survives_rollback_and_restart_across_every_advancing_consumer(self):
        before = self.budget_and_approvals()
        self.h.clock[0] = "2026-11-07T14:00:01Z"
        refuses(self, lambda: self.c.record_head(S, self.h.h.sha, self.h.terminal()), "activation-expired")
        stop = self.store.load_run().activation_stop
        self.assertEqual((stop["code"], stop["observed_at"]), ("activation-expired", "2026-11-07T14:00:01Z"))
        self.h.clock[0] = T0  # clock rolled back; the activation document itself is current again
        self.assertEqual(self.h.activation.problems(self.h.h.policy, "run-live", T0), [])
        for restart in (self.c, self.h.coordinator(), self.h.coordinator(activation=None)):
            self.h.h.fake.calls = []
            refuses(self, lambda: restart.record_head(S, self.h.h.sha, self.h.terminal()), "activation-expired")
            refuses(self, lambda: restart.reserve("OM-01.03", self.h.h.snapshot, "base"), "activation-expired")
            refuses(self, lambda: restart.authorize_review(S, self.h.h.sha), "activation-expired")
            refuses(self, lambda: restart.authorize_repair(S), "activation-expired")
            refuses(self, lambda: restart.run_checks(S, self.h.h.sha, str(self.h.h.worktree), passing_runner), "activation-expired")
            refuses(self, lambda: restart.propose_evidence(S, self.h.h.sha, 1, [], "x"), "activation-expired")
            refuses(self, lambda: restart.rebase_revisions(S, "x"), "activation-expired")
            self.assertEqual(restart.status()["activation"]["stop"], "activation-expired")
            self.assertEqual(self.h.h.fake.calls, NO_CALLS)
        state = self.store.load_story(S)
        state.intents[0].status = "pending"
        self.store.save_story(state)
        state = self.h.coordinator().resume(S, ok_worktree)  # advancing replay abandoned, cleanup kept
        self.assertEqual(state.phase, "claimed")
        self.assertIn("resume-advancing-abandoned", [e["event"] for e in self.store.read_journal()])
        self.assertEqual(self.budget_and_approvals(), before)  # approvals and budgets untouched by the stop
        self.assertEqual(self.store.load_story(S).active_task["taskId"], IMPLEMENTER["taskId"])
        self.assertEqual(self.h.coordinator().cancel(S, "expired", self.h.terminal()).phase, "cancelled")
        self.assertTrue(any("kind=release" in c_.body for c_ in self.h.h.fake.comments[21]))

    def test_late_receipt_after_durable_stop_binds_for_cleanup_only(self):
        self.c.record_head(S, self.h.h.sha, self.h.terminal())
        self.c.run_checks(S, self.h.h.sha, str(self.h.h.worktree), passing_runner)
        self.c.authorize_review(S, self.h.h.sha)
        self.h.clock[0] = "2026-11-07T14:00:01Z"
        refuses(self, lambda: self.c.record_head(S, self.h.h.sha), "activation-expired")
        self.h.clock[0] = T0
        exc = refuses(self, lambda: self.h.coordinator().bind_receipt(S, REVIEWER, worktree_check=ok_worktree), "activation-expired")
        self.assertTrue(exc.detail["bound_for_cleanup"])
        refuses(self, lambda: self.h.coordinator().record_review(S, self.h.h.sha, "approved", "r.md", self.h.terminal()), "activation-expired")
        state = self.h.coordinator(activation=None).cancel(S, "x", self.h.terminal())
        self.assertEqual((state.phase, state.active_task), ("cancelled", None))

    def test_clock_regression_past_an_observation_is_a_durable_stop(self):
        self.h.clock[0] = "2026-11-07T12:00:00Z"
        self.c.record_head(S, self.h.h.sha, self.h.terminal())
        self.assertEqual(self.store.load_run().last_observed_at, "2026-11-07T12:00:00Z")
        self.h.clock[0] = "2026-11-07T11:57:00Z"  # within the slew tolerance: not a regression
        self.c.run_checks(S, self.h.h.sha, str(self.h.h.worktree), passing_runner)
        self.h.clock[0] = T0
        refuses(self, lambda: self.c.authorize_review(S, self.h.h.sha), "clock-regression")
        self.assertEqual(self.store.load_run().activation_stop["code"], "clock-regression")
        self.h.clock[0] = "2026-11-07T13:00:00Z"
        refuses(self, lambda: self.h.coordinator().authorize_review(S, self.h.h.sha), "clock-regression")
        self.assertEqual(self.h.coordinator(activation=None).cancel(S, "x").phase, "cancelled")


if __name__ == "__main__":
    unittest.main()
