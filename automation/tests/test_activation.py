"""The explicit opt-in that replaces the unconditional live refusal (ENG-01 enabling change).

Everything here runs on the fixture transport marked ``live`` (the production boundary) with
temporary state; no real GitHub call and no real task is ever made. The real CLI transport is
patched to count calls in the CLI tests."""

from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from automation.tests.fake_transport import small_backlog
from automation.tests.support import Harness, IMPLEMENTER, REVIEWER, REVIEW_BRANCH, REVIEW_WORKTREE, ROOT, ok_worktree, passing_runner, write_policy
from automation.unattended import cli
from automation.unattended.activation import Activation, load_activation
from automation.unattended.coordinator import Coordinator
from automation.unattended.errors import BudgetExhausted, Refused, UnattendedError
from automation.unattended.policy import load_policy
from automation.unattended.state import Store

S = "OM-01.02"
CANDIDATE = ROOT / "automation/examples/activation-om-01-02.candidate.toml"
CANDIDATE_POLICY = ROOT / "automation/examples/first-run-om-01-02.toml"
T0 = "2026-11-07T10:00:00Z"


def activation_text(policy, run_id="run-live", approved=True, issued=T0, expires="2026-11-07T14:00:00Z", **over) -> str:
    """A valid activation for ``policy`` and ``run_id`` with field overrides for the negative cases."""
    fields = {
        "approved": "true" if approved else "false", "id": '"eng01-test-activation"', "approver": '"owner (fixture)"', "issued_at": f'"{issued}"', "expires_at": f'"{expires}"',
        "agreement": '"spec-eng-01-trusted-operation.md"', "repository": f'"{policy.repo_slug}"', "policy_digest": f'"{policy.digest}"', "environment": '"live"', "run_id": f'"{run_id}"',
        "stories": json.dumps(list(policy.allow)), "impl_model": '"claude-fable-5-1"', "rev_model": '"gpt-6-astra"', "max_delegated_tasks": "6", "max_wall_clock_minutes": "240",
        "extra": "", "smoke": f'"https://github.com/{policy.repo_slug}/pull/107#issuecomment-6706853226"', "review": f'"https://github.com/{policy.repo_slug}/pull/107#issuecomment-6706853227"',
    }
    fields.update(over)
    return f"""
approved = {fields['approved']}
id = {fields['id']}
approver = {fields['approver']}
issued_at = {fields['issued_at']}
expires_at = {fields['expires_at']}
agreement = {fields['agreement']}
{fields['extra']}
[binding]
repository = {fields['repository']}
policy_digest = {fields['policy_digest']}
environment = {fields['environment']}
run_id = {fields['run_id']}
[scope]
stories = {fields['stories']}
[targets]
implementer = {{ provider = "claudeAgent", model = {fields['impl_model']}, isolation = "worktree", options = {{ effort = "high" }} }}
reviewer = {{ provider = "codex", model = {fields['rev_model']}, isolation = "worktree", options = {{ reasoningEffort = "high" }} }}
[budgets]
max_stories_per_run = 1
max_concurrent_implementers = 1
max_repair_rounds = 2
max_delegated_tasks = {fields['max_delegated_tasks']}
max_wall_clock_minutes = {fields['max_wall_clock_minutes']}
[evidence]
lifecycle_smoke = {fields['smoke']}
fresh_review = {fields['review']}
"""


class LiveHarness:
    """A Harness whose fake transport is marked live, plus a movable clock and an activation file."""

    def __init__(self, **over):
        self.h = Harness(small_backlog())
        self.h.fake.live = True
        self.clock = [T0]
        self.path = Path(self.h.tmpdir.name) / "activation.toml"
        self.path.write_text(activation_text(self.h.policy, **over), encoding="utf-8")
        self.activation = load_activation(self.path)

    def coordinator(self, run_id="run-live", activation="file"):
        act = self.activation if activation == "file" else activation
        return Coordinator(self.h.fake, self.h.policy, Store(self.h.state_dir, run_id), now=lambda: self.clock[0], live=True, activation=act)

    def terminal(self, story=S, status="result_available", run_id="run-live"):
        state = Store(self.h.state_dir, run_id).load_story(story)
        return {"taskId": state.active_task["taskId"], "runId": state.active_task["runId"], "status": status}

    def close(self):
        self.h.close()


class CandidateAndLoaderTests(unittest.TestCase):
    def test_committed_candidate_is_unapproved_and_cannot_authorize_any_run(self):
        policy = load_policy(CANDIDATE_POLICY)
        act = load_activation(CANDIDATE)
        self.assertFalse(act.approved)
        problems = act.problems(policy, "any-run", "2026-11-07T12:00:00Z")
        codes = {c for c, _ in problems}
        self.assertEqual(Activation.stop_code(problems), "activation-mismatch")
        for code in ("activation-unapproved", "activation-mismatch", "activation-expired"):
            self.assertIn(code, codes)
        fake = small_backlog()
        fake.live = True
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(UnattendedError) as ctx:
                Coordinator(fake, policy, Store(Path(tmp) / "runs", "any-run"), live=True, activation=act)
            self.assertEqual(ctx.exception.code, "activation-mismatch")
            self.assertEqual(os.listdir(tmp), [])
        self.assertEqual(fake.calls, [])

    def test_shipped_policy_and_candidate_refuse_through_the_cli_without_state_or_calls(self):
        from automation.unattended.github import GhCliTransport

        calls = []
        original = GhCliTransport._run
        GhCliTransport._run = lambda self, args, stdin=None: calls.append(args) or "{}"
        try:
            with tempfile.TemporaryDirectory() as state_dir:
                for policy in (ROOT / "automation/policy.toml", CANDIDATE_POLICY):
                    buf = io.StringIO()
                    with redirect_stdout(buf):
                        code = cli.main(["--policy", str(policy), "--activation", str(CANDIDATE), "--run-id", "r", "check-activation"])
                    out = json.loads(buf.getvalue())
                    self.assertEqual((code, out["current"], out["approved"]), (2, False, False), policy)
                    buf = io.StringIO()
                    with redirect_stdout(buf):
                        code = cli.main(["--policy", str(policy), "--activation", str(CANDIDATE), "--state-dir", state_dir, "--run-id", "r", "--live", "reserve", S, "--baseline", "c"])
                    self.assertEqual((code, json.loads(buf.getvalue())["error"]["code"]), (3, "activation-mismatch"), policy)
                self.assertEqual(os.listdir(state_dir), [])
        finally:
            GhCliTransport._run = original
        self.assertEqual(calls, [])

    def test_malformed_activations_refuse_at_load(self):
        h = Harness(small_backlog())
        try:
            tmp = Path(h.tmpdir.name)
            cases = {
                "unknown-key": activation_text(h.policy, extra='rogue = "x"'),
                "secret-like-key": activation_text(h.policy, extra='token = "x"'),
                "credential-value": activation_text(h.policy, approver='"ghp_' + "a" * 36 + '"'),
                "bad-story": activation_text(h.policy, stories='["E17"]'),
                "missing-evidence": "\n".join(l for l in activation_text(h.policy).splitlines() if not l.startswith("fresh_review")),
                "stories-not-strings": activation_text(h.policy, stories='["OM-01.02", 1]'),
                "stories-duplicate": activation_text(h.policy, stories='["OM-01.02", "OM-01.02"]'),
                "approved-not-bool": activation_text(h.policy).replace("approved = true", 'approved = "yes"'),
                "not-toml": "approved = \n",
            }
            for name, text in cases.items():
                path = tmp / f"{name}.toml"
                path.write_text(text, encoding="utf-8")
                with self.assertRaises(UnattendedError, msg=name) as ctx:
                    load_activation(path)
                self.assertEqual(ctx.exception.code, "activation-invalid", name)
            with self.assertRaises(UnattendedError) as ctx:
                load_activation(tmp / "absent.toml")
            self.assertEqual(ctx.exception.code, "activation-invalid")
        finally:
            h.close()


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.lh = LiveHarness()

    def tearDown(self):
        self.lh.close()

    def test_current_activation_admits_and_advances_on_the_live_marked_fixture_transport(self):
        c = self.lh.coordinator()
        state = c.reserve(S, self.lh.h.snapshot, "c5d9d2e")
        self.assertEqual(state.phase, "reserved")
        c.bind_receipt(S, IMPLEMENTER, str(self.lh.h.worktree), "t3/om-01-02", ok_worktree)
        c.record_head(S, self.lh.h.sha, self.lh.terminal())
        c.run_checks(S, self.lh.h.sha, str(self.lh.h.worktree), passing_runner)
        c.authorize_review(S, self.lh.h.sha)
        c.bind_receipt(S, REVIEWER, REVIEW_WORKTREE, REVIEW_BRANCH, ok_worktree)
        state = c.record_review(S, self.lh.h.sha, "approved", "report.md", self.lh.terminal())
        self.assertEqual(state.phase, "review-approved")
        status = c.status()
        self.assertEqual(status["environment"], "live")
        self.assertEqual(status["activation"]["recorded"]["id"], "eng01-test-activation")
        self.assertIsNone(status["activation"]["stop"])
        self.assertEqual(Store(self.lh.h.state_dir, "run-live").load_run().activation["digest"], self.lh.activation.digest)
        self.assertTrue(any("kind=claim" in c_.body for c_ in self.lh.h.fake.comments[21]))

    def test_foreign_scope_and_drift_refuse_before_any_call_and_create_no_run(self):
        policy = self.lh.h.policy
        cases = {
            "activation-mismatch:run": dict(run_id="run-other"),
            "activation-mismatch:repo": dict(repository='"someone/else"'),
            "activation-mismatch:digest": dict(policy_digest=f'"{hashlib.sha256(b"other").hexdigest()}"'),
            "activation-mismatch:scope": dict(stories='["OM-01.03"]'),
            "activation-mismatch:model": dict(impl_model='"claude-opus-5-5"'),
            "activation-mismatch:reviewer": dict(rev_model='"gpt-5"'),
            "activation-mismatch:budget": dict(max_delegated_tasks="7"),
            "activation-mismatch:wall-clock": dict(max_wall_clock_minutes="480"),
            "activation-unapproved": dict(approved=False),
            "activation-invalid:environment": dict(environment='"fixture"'),
            "activation-invalid:window": dict(expires="2026-11-09T10:00:01Z"),
            "activation-invalid:order": dict(expires="2026-11-07T09:00:00Z"),
            "activation-not-yet-valid": dict(issued="2026-11-07T11:00:00Z", expires="2026-11-07T15:00:00Z"),
            "activation-expired": dict(issued="2026-11-07T05:00:00Z", expires="2026-11-07T09:00:00Z"),
        }
        for label, over in cases.items():
            code = label.split(":")[0]
            path = Path(self.lh.h.tmpdir.name) / "neg.toml"
            path.write_text(activation_text(policy, **{"run_id": "run-neg", **over}), encoding="utf-8")
            act = load_activation(path)
            self.lh.h.fake.calls = []
            store = Store(self.lh.h.state_dir, "run-neg")
            with self.assertRaises(Refused, msg=label) as ctx:
                Coordinator(self.lh.h.fake, policy, store, now=lambda: T0, live=True, activation=act)
            self.assertEqual(ctx.exception.code, code, label)
            self.assertEqual(self.lh.h.fake.calls, [], label)
            self.assertIsNone(store.load_run(), label)

    def test_policy_drift_after_activation_refuses_the_existing_run(self):
        c = self.lh.coordinator()
        c.reserve(S, self.lh.h.snapshot, "c5d9d2e")
        drift_dir = Path(self.lh.h.tmpdir.name) / "d"
        drift_dir.mkdir()
        drifted = load_policy(write_policy(drift_dir, allow='["OM-01.02"]', max_delegated_tasks="7"))
        with self.assertRaises(Refused) as ctx:  # the activation names the old digest, so a new run is refused…
            Coordinator(self.lh.h.fake, drifted, Store(self.lh.h.state_dir, "run-new"), now=lambda: T0, live=True, activation=self.lh.activation)
        self.assertEqual(ctx.exception.code, "activation-mismatch")
        # …and the existing run opens under the changed policy as a stopped run (policy drift, journaled once):
        # the activation binds the old digest so advancement refuses, while cleanup proceeds (PR #107 review finding 23)
        drifted_c = Coordinator(self.lh.h.fake, drifted, Store(self.lh.h.state_dir, "run-live"), now=lambda: T0, live=True, activation=self.lh.activation)
        status = drifted_c.status()
        self.assertEqual((status["stop"], status["policy_drift"]["policy_digest"]), ("policy-drift", drifted.digest))
        with self.assertRaises(Refused) as ctx:
            drifted_c.bind_receipt(S, IMPLEMENTER, str(self.lh.h.worktree), "t3/om-01-02", ok_worktree)
        self.assertEqual((ctx.exception.code, ctx.exception.detail.get("bound_for_cleanup")), ("policy-drift", True))  # a late receipt binds for cleanup only
        with self.assertRaises(Refused) as ctx:
            drifted_c.record_head(S, self.lh.h.sha, self.lh.terminal())
        self.assertEqual(ctx.exception.code, "activation-mismatch")  # the activation names the old digest: nothing advances
        result = drifted_c.cancel_run("policy changed under the run", task_evidence={S: self.lh.terminal(status="cancelled")})
        self.assertEqual([s["phase"] for s in result["cancelled"]], ["cancelled"])
        events = [e["event"] for e in Store(self.lh.h.state_dir, "run-live").read_journal()]
        self.assertEqual(events.count("policy-drift"), 1)

    def test_changed_activation_refuses_every_operation_including_cleanup(self):
        c = self.lh.coordinator()
        c.reserve(S, self.lh.h.snapshot, "c5d9d2e")
        c.bind_receipt(S, IMPLEMENTER, str(self.lh.h.worktree), "t3/om-01-02", ok_worktree)
        self.lh.path.write_text(activation_text(self.lh.h.policy, expires="2026-11-07T15:00:00Z"), encoding="utf-8")  # re-issued with a longer window: another document
        changed = load_activation(self.lh.path)
        with self.assertRaises(Refused) as ctx:
            self.lh.coordinator(activation=changed)
        self.assertEqual(ctx.exception.code, "activation-mismatch")
        other_path = self.lh.path.parent / "o.toml"
        other_path.write_text(activation_text(self.lh.h.policy, id='"eng01-other"'), encoding="utf-8")
        with self.assertRaises(Refused) as ctx:
            self.lh.coordinator(activation=load_activation(other_path))
        self.assertEqual(ctx.exception.code, "activation-mismatch")
        self.assertEqual(Store(self.lh.h.state_dir, "run-live").load_story(S).phase, "claimed")


class ExpiryAndCleanupTests(unittest.TestCase):
    def setUp(self):
        self.lh = LiveHarness()
        self.c = self.lh.coordinator()
        self.c.reserve(S, self.lh.h.snapshot, "c5d9d2e")
        self.c.bind_receipt(S, IMPLEMENTER, str(self.lh.h.worktree), "t3/om-01-02", ok_worktree)
        self.store = Store(self.lh.h.state_dir, "run-live")

    def tearDown(self):
        self.lh.close()

    def expire(self):
        self.lh.clock[0] = "2026-11-07T14:00:01Z"

    def test_expiry_stops_every_advancing_operation_and_the_wall_clock_is_untouched(self):
        self.expire()
        for op in (lambda: self.c.record_head(S, self.lh.h.sha, self.lh.terminal()), lambda: self.c.run_checks(S, self.lh.h.sha, str(self.lh.h.worktree), passing_runner),
                   lambda: self.c.authorize_review(S, self.lh.h.sha), lambda: self.c.authorize_repair(S), lambda: self.c.propose_evidence(S, self.lh.h.sha, 1, [], "x"),
                   lambda: self.c.reserve("OM-01.03", self.lh.h.snapshot, "c5d9d2e"), lambda: self.c.rebase_revisions(S, "x")):
            with self.assertRaises(Refused) as ctx:
                op()
            self.assertEqual(ctx.exception.code, "activation-expired")
        self.assertEqual(self.c.status()["activation"]["stop"], "activation-expired")
        self.assertEqual(self.store.load_story(S).phase, "claimed")
        self.assertFalse(self.store.load_run().cancelled)

    def test_late_receipt_after_expiry_binds_for_cleanup_only(self):
        c = self.c
        c.record_head(S, self.lh.h.sha, self.lh.terminal())
        c.run_checks(S, self.lh.h.sha, str(self.lh.h.worktree), passing_runner)
        c.authorize_review(S, self.lh.h.sha)  # the reviewer may already have been launched
        self.expire()
        with self.assertRaises(BudgetExhausted) as ctx:
            c.bind_receipt(S, REVIEWER, REVIEW_WORKTREE, REVIEW_BRANCH, ok_worktree)
        self.assertEqual(ctx.exception.code, "activation-expired")
        self.assertTrue(ctx.exception.detail["bound_for_cleanup"])
        state = self.store.load_story(S)
        self.assertEqual(state.active_task["taskId"], REVIEWER["taskId"])
        with self.assertRaises(Refused) as ctx:
            c.record_review(S, self.lh.h.sha, "approved", "r.md", self.lh.terminal())
        self.assertEqual(ctx.exception.code, "activation-expired")
        state = c.cancel(S, "expired", self.lh.terminal())
        self.assertEqual(state.phase, "cancelled")
        self.assertIsNone(state.active_task)

    def test_cleanup_after_expiry_works_with_the_same_or_no_activation_but_never_advances(self):
        self.expire()
        with self.assertRaises(Refused) as ctx:
            self.c.cancel(S, "expired")  # ownership still needs terminal evidence
        self.assertNotIn("activation", ctx.exception.code)
        state = self.c.record_task_terminal(S, self.lh.terminal())
        self.assertIsNone(state.active_task)
        bare = self.lh.coordinator(activation=None)  # restart without the file: the recorded binding suffices for cleanup
        self.assertEqual(bare.status()["activation"]["stop"], "activation-expired")  # the expiry observed above is a durable stop (R6), reported before the missing file
        self.assertEqual(bare.status()["activation"]["recorded_stop"]["code"], "activation-expired")
        with self.assertRaises(Refused) as ctx:
            bare.record_head(S, self.lh.h.sha)
        self.assertEqual(ctx.exception.code, "activation-expired")
        state = bare.resume(S, ok_worktree)
        self.assertEqual(state.phase, "claimed")
        report = bare.cancel_run("expired activation")
        self.assertTrue(self.store.load_run().cancelled)
        self.assertEqual(self.store.load_story(S).phase, "cancelled")
        self.assertTrue(any("kind=release" in c_.body for c_ in self.lh.h.fake.comments[21]))
        with self.assertRaises(Refused) as ctx:
            bare.reserve("OM-01.03", self.lh.h.snapshot, "c5d9d2e")
        self.assertIn(ctx.exception.code, ("run-cancelled", "activation-required", "activation-expired"))
        self.assertIsInstance(report, dict)

    def test_restart_after_expiry_replays_cleanup_but_not_advancing_intents(self):
        c = self.c
        state = self.store.load_story(S)
        state.intents[0].status = "pending"  # the claim comment landed; its completion did not persist
        self.store.save_story(state)
        self.expire()
        state = self.lh.coordinator().resume(S, ok_worktree)
        self.assertEqual(state.phase, "claimed")
        journal = [e["event"] for e in self.store.read_journal()]
        self.assertIn("resume-advancing-abandoned", journal)
        self.assertNotIn("reservation-completed-on-resume", journal)
        self.assertEqual(len([c_ for c_ in self.lh.h.fake.comments[21] if "kind=claim" in c_.body]), 1)


if __name__ == "__main__":
    unittest.main()
