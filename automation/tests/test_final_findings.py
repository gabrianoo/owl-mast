"""Remediation pass 1: the six defects of the final exact-commit disposition of PR #107
(reviewed head a0fa769e). Every scenario here reproduced a false advance on that head
(evidence/final-findings-repro-before-2026-11-06.txt). Each class covers combined
transitions, crash/restart with a fresh coordinator, and tampered or legacy state."""

import json
import unittest

from automation.tests.fake_transport import FakeTransport, issue, small_backlog
from automation.tests.support import FIXTURES, IMPLEMENTER, REVIEWER, Harness, failing_runner, git_commit, ok_worktree, passing_runner, receipt
from automation.unattended.backlog import Snapshot, load_tasks_index, verify_mapping
from automation.unattended.coordinator import Coordinator
from automation.unattended.eligibility import decide, plan
from automation.unattended.errors import BudgetExhausted, Outage, ReceiptInvalid, Refused, StaleRevision
from automation.unattended.github import PullRequestRecord
from automation.unattended.state import STORY_SCHEMA, Store
from automation.tests.support import ROOT


def markers(fake: FakeTransport, number: int, kind: str):
    return [c for c in fake.comments[number] if c.marker and c.marker["kind"] == kind]


def fresh(h: Harness) -> Coordinator:
    """A coordinator that only knows what is on disk (restart)."""
    return Coordinator(h.fake, h.policy, Store(h.state_dir, "run-1"), live=True)


def pending_proposal(h: Harness) -> str:
    """Approved story, healthy PR, proposal POST failed once: a pending advancing intent."""
    h.to_review_approved()
    h.fake.pull_requests[7] = PullRequestRecord(7, "OPEN", h.sha, False, (), "SUCCESS")
    h.fake.fail_once["post_comment"] = Outage("503")
    with unittest.TestCase().assertRaises(Outage):
        h.coordinator.propose_evidence("OM-01.02", h.sha, 7, ["OM-01.02-T1"], "original evidence")
    ops = [i.op for i in h.store.load_story("OM-01.02").pending_advancing_intents()]
    assert ops == [f"proposal-{h.sha[:12]}-pr7"], ops
    return ops[0]


class D1CancellationAbandonsAdvancingIntents(unittest.TestCase):
    """B1/E1/V1: cancellation plus a pending proposal must never produce cancelled → proposed."""

    def setUp(self):
        self.h = Harness(small_backlog())

    def tearDown(self):
        self.h.close()

    def test_cancel_run_after_failed_proposal_post_never_proposes_on_resume(self):
        op = pending_proposal(self.h)
        result = self.h.coordinator.cancel_run("operator stop")
        self.assertEqual([s["phase"] for s in result["cancelled"]], ["cancelled"])
        state = self.h.store.load_story("OM-01.02")
        self.assertEqual(state.intent(op).status, "abandoned")  # abandoned in the same write as the terminal phase
        self.assertEqual(state.blocked["abandoned_intents"], [op])
        state = fresh(self.h).resume("OM-01.02", ok_worktree)
        self.assertEqual(state.phase, "cancelled")
        self.assertEqual(markers(self.h.fake, 21, "proposal"), [])
        self.assertEqual(len(markers(self.h.fake, 21, "release")), 1)
        self.assertTrue(self.h.store.load_run().cancelled)
        with self.assertRaises(BudgetExhausted) as ctx:
            fresh(self.h).propose_evidence("OM-01.02", self.h.sha, 7, [], "s")
        self.assertEqual(ctx.exception.code, "run-cancelled")
        self.assertEqual(markers(self.h.fake, 21, "proposal"), [])

    def test_story_cancel_and_block_abandon_the_pending_proposal_atomically(self):
        for terminal in ("cancel", "block"):
            h = Harness(small_backlog())
            try:
                op = pending_proposal(h)
                original = h.store.journal

                def crash(story, event, detail=None, _orig=original, _t=terminal):
                    if event in ("cancelled", "blocked"):
                        raise RuntimeError("synthetic crash after the terminal save")
                    return _orig(story, event, detail)

                h.store.journal = crash
                with self.assertRaises(RuntimeError):
                    getattr(h.coordinator, terminal)("OM-01.02", "stop")
                h.store.journal = original
                state = h.store.load_story("OM-01.02")  # what survived the crash
                self.assertEqual(state.phase, "cancelled" if terminal == "cancel" else "blocked")
                self.assertEqual(state.intent(op).status, "abandoned")
                self.assertEqual([i.op for i in state.pending_intents()], ["release" if terminal == "cancel" else "block"])
                state = fresh(h).resume("OM-01.02", ok_worktree)
                self.assertEqual(state.pending_intents(), [])
                self.assertEqual(markers(h.fake, 21, "proposal"), [])
                self.assertEqual(len(markers(h.fake, 21, "release" if terminal == "cancel" else "block")), 1)
            finally:
                h.close()

    def test_cancel_abandons_a_pending_claim_and_resume_posts_only_the_release(self):
        self.h.fake.fail_once["post_comment"] = Outage("503")
        with self.assertRaises(Outage):
            self.h.claim()
        state = self.h.coordinator.cancel("OM-01.02", "stop before the reservation completed")
        self.assertEqual((state.phase, state.intent("claim").status), ("cancelled", "abandoned"))
        self.assertEqual(state.pending_authorization(), None)  # the unbound implementer slot is abandoned, still counted
        self.assertEqual(self.h.store.story_counts()["delegated_tasks"], 1)
        fresh(self.h).resume("OM-01.02", ok_worktree)
        self.assertEqual(markers(self.h.fake, 21, "claim"), [])
        self.assertEqual(len(markers(self.h.fake, 21, "release")), 1)

    def test_run_cancelled_before_the_story_cancel_blocks_replay_but_keeps_ownership(self):
        """Crash between save_run(cancelled) and the per-story cancel: the pending proposal
        is abandoned on resume, nothing is posted, the story stays for cancel-run to finish."""
        op = pending_proposal(self.h)
        run = self.h.store.load_run()
        run.cancelled, run.stop_reason = True, "crash after save_run"
        self.h.store.save_run(run)
        state = fresh(self.h).resume("OM-01.02", ok_worktree)
        self.assertEqual((state.phase, state.intent(op).status), ("review-approved", "abandoned"))
        self.assertEqual(markers(self.h.fake, 21, "proposal"), [])
        self.assertTrue(any(e["event"] == "resume-advancing-abandoned" and e["detail"]["reason"] == "run is cancelled" for e in self.h.store.read_journal()))
        result = fresh(self.h).cancel_run("finish")
        self.assertEqual([s["phase"] for s in result["cancelled"]], ["cancelled"])
        self.assertEqual(markers(self.h.fake, 21, "proposal"), [])

    def test_terminal_story_with_a_pending_advancing_intent_is_never_replayed(self):
        """Legacy or tampered state: a cancelled story still carrying a pending proposal."""
        op = pending_proposal(self.h)
        state = self.h.store.load_story("OM-01.02")
        state.phase, state.blocked = "cancelled", {"reason": "legacy", "at": "t", "from_phase": "review-approved", "cancelled": True}
        self.h.store.save_story(state)
        state = fresh(self.h).resume("OM-01.02", ok_worktree)
        self.assertEqual((state.phase, state.intent(op).status), ("cancelled", "abandoned"))
        self.assertEqual(markers(self.h.fake, 21, "proposal"), [])

    def test_cancelled_run_refuses_every_advancing_operation(self):
        self.h.claim()
        self.h.checks()
        c = self.h.coordinator
        c.cancel_run("stop")  # story has no active task: cancelled immediately
        h2 = Harness(small_backlog(), allow='["OM-01.02", "OM-01.04"]', max_stories_per_run="2")
        try:
            h2.claim()  # implementer active: stays owned after cancel-run
            self.assertEqual(h2.coordinator.cancel_run("stop")["awaiting_worker_termination"][0]["story"], "OM-01.02")
            c2 = fresh(h2)
            for op in (lambda: c2.reserve("OM-01.04", h2.snapshot, "b"), lambda: c2.record_head("OM-01.02", h2.sha, h2.terminal()),
                       lambda: c2.run_checks("OM-01.02", h2.sha, str(h2.worktree), passing_runner), lambda: c2.authorize_review("OM-01.02", h2.sha),
                       lambda: c2.authorize_repair("OM-01.02"), lambda: c2.record_review("OM-01.02", h2.sha, "approved", "r"),
                       lambda: c2.propose_evidence("OM-01.02", h2.sha, 7, [], "s"), lambda: c2.bind_receipt("OM-01.02", REVIEWER, worktree_check=ok_worktree)):
                with self.assertRaises(BudgetExhausted) as ctx:
                    op()
                self.assertEqual(ctx.exception.code, "run-cancelled")
            self.assertEqual(h2.store.load_story("OM-01.02").phase, "claimed")
            self.assertEqual(h2.store.load_story("OM-01.04"), None)
            self.assertEqual(c2.record_task_terminal("OM-01.02", h2.terminal()).active_task, None)  # evidence is still accepted
            self.assertEqual(c2.cancel("OM-01.02", "stop").phase, "cancelled")
        finally:
            h2.close()


class D2ProposalReplayRequiresCurrentApproval(unittest.TestCase):
    """E2: a pending proposal replays only with a current local approval for the exact SHA."""

    def setUp(self):
        self.h = Harness(small_backlog())

    def tearDown(self):
        self.h.close()

    def test_local_changes_requested_abandons_the_pending_proposal(self):
        op = pending_proposal(self.h)
        state = self.h.coordinator.record_review("OM-01.02", self.h.sha, "changes-requested", "second look")
        self.assertEqual((state.phase, state.approved_sha, state.intent(op).status), ("changes-requested", None, "abandoned"))
        self.h.fake.calls = []
        state = fresh(self.h).resume("OM-01.02", ok_worktree)
        self.assertEqual(state.phase, "changes-requested")
        self.assertEqual(markers(self.h.fake, 21, "proposal"), [])
        self.assertNotIn("post_comment", self.h.fake.calls)

    def test_new_head_after_approval_abandons_the_pending_proposal(self):
        op = pending_proposal(self.h)
        new = git_commit(self.h.worktree, "late.txt")
        state = self.h.coordinator.record_head("OM-01.02", new)
        self.assertEqual((state.phase, state.intent(op).status), ("implemented", "abandoned"))
        state = fresh(self.h).resume("OM-01.02", ok_worktree)
        self.assertEqual((state.phase, state.head_sha), ("implemented", new))
        self.assertEqual(markers(self.h.fake, 21, "proposal"), [])

    def test_unreported_worktree_change_during_replay_abandons_the_proposal(self):
        op = pending_proposal(self.h)
        (self.h.worktree / "README").write_text("edited after approval")
        with self.assertRaises(Refused) as ctx:
            fresh(self.h).resume("OM-01.02", ok_worktree)
        self.assertEqual(ctx.exception.code, "evidence-invalidated")
        state = self.h.store.load_story("OM-01.02")
        self.assertEqual((state.phase, state.intent(op).status), ("implemented", "abandoned"))
        self.assertEqual(markers(self.h.fake, 21, "proposal"), [])

    def test_replay_checks_phase_and_exact_sha_before_github(self):
        """Tampered or legacy state: approval missing or for another commit, phase drifted."""
        for mutate in (lambda s: setattr(s, "approved_sha", None), lambda s: setattr(s, "approved_sha", "other"),
                       lambda s: setattr(s, "head_sha", "other"), lambda s: setattr(s, "phase", "checks-passed"),
                       lambda s: setattr(s, "active_task", {"taskId": "task-review-9", "role": "reviewer", "authorization": "x", "bound_at": "t"})):
            h = Harness(small_backlog())
            try:
                op = pending_proposal(h)
                state = h.store.load_story("OM-01.02")
                mutate(state)
                h.store.save_story(state)
                h.fake.calls = []
                try:
                    fresh(h).resume("OM-01.02", ok_worktree)
                except (Refused, StaleRevision):
                    pass
                state = h.store.load_story("OM-01.02")
                self.assertEqual(state.intent(op).status, "abandoned")
                self.assertNotEqual(state.phase, "proposed")
                self.assertEqual(markers(h.fake, 21, "proposal"), [])
                self.assertNotIn("get_pull_request", h.fake.calls)  # refused on local state before any PR read
            finally:
                h.close()

    def test_reapproval_at_the_same_commit_after_an_abandoned_proposal_posts_once(self):
        op = pending_proposal(self.h)
        c = self.h.coordinator
        c.record_review("OM-01.02", self.h.sha, "changes-requested", "second look")
        self.h.repair(receipt_=receipt(IMPLEMENTER, "task-impl-2"))
        self.h.checks()  # same commit re-recorded by the repair task
        self.h.request_review(receipt_=receipt(REVIEWER, "task-review-2"))
        c.record_review("OM-01.02", self.h.sha, "approved", "third look", self.h.terminal())
        state = c.propose_evidence("OM-01.02", self.h.sha, 7, ["OM-01.02-T1"], "re-approved evidence")
        self.assertEqual(state.phase, "proposed")
        self.assertEqual(state.intent(op).status, "done")
        posted = markers(self.h.fake, 21, "proposal")
        self.assertEqual(len(posted), 1)
        self.assertIn("re-approved evidence", posted[0].body)


class D3ActiveTaskOwnershipIsIndependent(unittest.TestCase):
    """B2/E3/V3: the active task (id, role) survives HEAD recording and invalidation; only
    terminal evidence for exactly that task releases it."""

    def setUp(self):
        self.h = Harness(small_backlog())
        self.c = self.h.coordinator

    def tearDown(self):
        self.h.close()

    def test_same_sha_head_recording_during_review_keeps_reviewer_ownership(self):
        self.h.claim()
        self.h.checks()
        self.h.request_review()
        state = self.c.record_head("OM-01.02", self.h.sha)  # same sha, no evidence
        self.assertEqual((state.phase, state.active_task["taskId"], state.active_task["role"]), ("review-requested", "task-review-1", "reviewer"))
        for evidence in (None, {"taskId": "task-impl-1", "status": "result_available"}, {"taskId": "task-review-1", "status": "cancel_requested"}):
            with self.assertRaises(Refused) as ctx:
                self.c.cancel("OM-01.02", "stop", evidence)
            self.assertEqual(ctx.exception.code, "worker-not-terminal")
            with self.assertRaises(Refused):
                fresh(self.h).block("OM-01.02", "stop", evidence)
        self.assertEqual(self.h.store.load_story("OM-01.02").phase, "review-requested")
        self.assertEqual(markers(self.h.fake, 21, "release") + markers(self.h.fake, 21, "block"), [])
        state = fresh(self.h).cancel("OM-01.02", "stop", {"taskId": "task-review-1", "status": "cancelled"})
        self.assertEqual((state.phase, state.active_task, state.task_history[-1]["taskId"]), ("cancelled", None, "task-review-1"))

    def test_new_sha_during_review_invalidates_evidence_but_keeps_reviewer_ownership(self):
        self.h.claim()
        self.h.checks()
        self.h.request_review()
        new = git_commit(self.h.worktree, "during-review.txt")
        state = self.c.record_head("OM-01.02", new)
        self.assertEqual((state.phase, state.approved_sha, state.active_task["role"]), ("implemented", None, "reviewer"))
        for op in (lambda: self.c.run_checks("OM-01.02", new, str(self.h.worktree), passing_runner), lambda: self.c.cancel("OM-01.02", "x"),
                   lambda: self.c.block("OM-01.02", "x", {"taskId": "task-impl-1", "status": "result_available"})):
            with self.assertRaises(Refused) as ctx:
                op()
            self.assertEqual(ctx.exception.code, "worker-not-terminal")
        state = fresh(self.h).record_task_terminal("OM-01.02", {"taskId": "task-review-1", "status": "result_available"})
        self.assertEqual(state.active_task, None)
        self.assertEqual(self.c.run_checks("OM-01.02", new, str(self.h.worktree), passing_runner).phase, "checks-passed")
        self.assertEqual(self.c.authorize_review("OM-01.02", new).phase, "review-authorized")

    def test_invalidation_at_the_verdict_gate_keeps_the_reviewer_until_its_evidence(self):
        self.h.claim()
        self.h.checks()
        self.h.request_review()
        (self.h.worktree / "README").write_text("edited during review")
        with self.assertRaises(Refused) as ctx:
            self.c.record_review("OM-01.02", self.h.sha, "approved", "r")  # no evidence: refused before the worktree is even read
        self.assertEqual(ctx.exception.code, "worker-not-terminal")
        with self.assertRaises(Refused):
            self.c.record_review("OM-01.02", self.h.sha, "approved", "r", {"taskId": "task-impl-1", "status": "result_available"})
        self.assertEqual(self.h.store.load_story("OM-01.02").phase, "review-requested")
        with self.assertRaises(Refused) as ctx:
            self.c.record_review("OM-01.02", self.h.sha, "approved", "r", self.h.terminal())
        self.assertEqual(ctx.exception.code, "evidence-invalidated")
        state = self.h.store.load_story("OM-01.02")
        self.assertEqual((state.phase, state.active_task, state.task_history[-1]["role"]), ("implemented", None, "reviewer"))

    def test_record_head_requires_the_implementer_terminal_evidence(self):
        self.h.claim()
        for evidence in (None, {"taskId": "other", "status": "result_available"}, {"taskId": "task-impl-1", "status": "working"}, {"taskId": "task-impl-1"}):
            with self.assertRaises(Refused) as ctx:
                self.c.record_head("OM-01.02", self.h.sha, evidence)
            self.assertEqual(ctx.exception.code, "worker-not-terminal")
        self.assertEqual(self.h.store.load_story("OM-01.02").head_sha, None)
        state = self.c.record_head("OM-01.02", self.h.sha, {"taskId": "task-impl-1", "status": "result_available"})
        self.assertEqual((state.phase, state.active_task, state.task_history[-1]["status"]), ("implemented", None, "result_available"))
        with self.assertRaises(Refused) as ctx:
            self.c.record_task_terminal("OM-01.02", {"taskId": "task-impl-1", "status": "result_available"})
        self.assertEqual(ctx.exception.code, "no-active-task")

    def test_ownership_survives_restart_and_reviewer_launch_waits_for_implementer(self):
        self.h.claim()
        c2 = fresh(self.h)
        with self.assertRaises(Refused) as ctx:
            c2.cancel("OM-01.02", "stop")
        self.assertEqual(ctx.exception.detail, {"task_id": "task-impl-1", "role": "implementer", "authorization": "run-1:OM-01.02:1"})
        self.assertEqual(c2.status()["stories"][0]["active_task"]["taskId"], "task-impl-1")
        c2.record_head("OM-01.02", self.h.sha, {"taskId": "task-impl-1", "status": "result_available"})
        c2.run_checks("OM-01.02", self.h.sha, str(self.h.worktree), passing_runner)
        state = c2.authorize_review("OM-01.02", self.h.sha)
        state = c2.bind_receipt("OM-01.02", REVIEWER, worktree_check=ok_worktree)
        self.assertEqual((state.phase, state.active_task["role"]), ("review-requested", "reviewer"))

    def test_legacy_story_schema_is_refused_not_reinterpreted(self):
        self.h.claim()
        path = self.h.store.story_path("OM-01.02")
        raw = json.loads(path.read_text())
        raw.pop("active_task"); raw["worker_state"] = "returned"
        path.write_text(json.dumps(raw))
        with self.assertRaises(Refused) as ctx:
            fresh(self.h).resume("OM-01.02", ok_worktree)
        self.assertEqual(ctx.exception.code, "state-schema-mismatch")
        self.assertEqual(STORY_SCHEMA, 3)
        # schema 2 recorded a stopped-but-maybe-launched authorization as "abandoned"; such a file is refused, not reinterpreted as resolved
        self.h.close(); self.h = Harness(small_backlog()); self.h.reserve()
        path = self.h.store.story_path("OM-01.02")
        raw = json.loads(path.read_text())
        raw["schema"], raw["authorizations"][0]["status"] = 2, "abandoned"
        path.write_text(json.dumps(raw))
        with self.assertRaises(Refused) as ctx:
            fresh(self.h).resume("OM-01.02", ok_worktree)
        self.assertEqual(ctx.exception.code, "state-schema-mismatch")
        raw["schema"] = STORY_SCHEMA  # right schema number, unknown status: still refused
        path.write_text(json.dumps(raw))
        with self.assertRaises(Refused) as ctx:
            fresh(self.h).resume("OM-01.02", ok_worktree)
        self.assertEqual(ctx.exception.code, "state-schema-mismatch")


class D4ClaimCompletionIsAtomic(unittest.TestCase):
    """E4: intent completion and its phase transition persist in one write; a completed
    intent whose transition did not persist is reconciled on resume."""

    def setUp(self):
        self.h = Harness(small_backlog())

    def tearDown(self):
        self.h.close()

    def persisted_states(self, action):
        seen = []
        original = self.h.store.save_story

        def spy(state):
            original(state)
            seen.append((state.phase, {i.op: i.status for i in state.intents}))

        self.h.store.save_story = spy
        try:
            action()
        finally:
            self.h.store.save_story = original
        return seen

    def test_no_persisted_state_has_a_done_claim_without_the_reserved_phase(self):
        seen = self.persisted_states(self.h.reserve)
        self.assertIn(("claim-incomplete", {"claim": "pending"}), seen)
        self.assertIn(("reserved", {"claim": "done"}), seen)
        self.assertNotIn(("claim-incomplete", {"claim": "done"}), seen)

    def test_no_persisted_state_has_a_done_proposal_without_the_proposed_phase(self):
        self.h.to_review_approved()
        self.h.fake.pull_requests[7] = PullRequestRecord(7, "OPEN", self.h.sha, False, (), "SUCCESS")
        op = f"proposal-{self.h.sha[:12]}-pr7"
        seen = self.persisted_states(lambda: self.h.coordinator.propose_evidence("OM-01.02", self.h.sha, 7, [], "s"))
        self.assertTrue(any(phase == "proposed" and intents[op] == "done" for phase, intents in seen))
        self.assertFalse(any(phase != "proposed" and intents.get(op) == "done" for phase, intents in seen))

    def test_crash_right_after_the_claim_post_is_recovered_as_reserved_with_one_comment(self):
        original = self.h.store.journal

        def crash(story, event, detail=None):
            if event == "comment-posted":
                raise RuntimeError("synthetic crash after the post, before the save")
            return original(story, event, detail)

        self.h.store.journal = crash
        with self.assertRaises(RuntimeError):
            self.h.reserve()
        self.h.store.journal = original
        state = self.h.store.load_story("OM-01.02")
        self.assertEqual((state.phase, state.intent("claim").status), ("claim-incomplete", "pending"))
        state = fresh(self.h).resume("OM-01.02", ok_worktree)
        self.assertEqual((state.phase, state.intent("claim").status), ("reserved", "done"))
        self.assertEqual(len(markers(self.h.fake, 21, "claim")), 1)
        self.assertEqual(fresh(self.h).bind_receipt("OM-01.02", IMPLEMENTER, str(self.h.worktree), "t3/om-01-02", ok_worktree).phase, "claimed")

    def test_legacy_claim_incomplete_with_a_done_intent_is_reconciled_without_posting(self):
        self.h.reserve()
        state = self.h.store.load_story("OM-01.02")
        state.phase = "claim-incomplete"  # the split state the reviewed head could leave behind
        self.h.store.save_story(state)
        self.h.fake.calls = []
        state = fresh(self.h).resume("OM-01.02", ok_worktree)
        self.assertEqual(state.phase, "reserved")
        self.assertNotIn("post_comment", self.h.fake.calls)
        self.assertEqual(len(markers(self.h.fake, 21, "claim")), 1)
        self.assertTrue(any(e["event"] == "transition-reconciled" for e in self.h.store.read_journal()))
        self.assertEqual(fresh(self.h).bind_receipt("OM-01.02", IMPLEMENTER, str(self.h.worktree), "t3/om-01-02", ok_worktree).phase, "claimed")

    def test_legacy_review_approved_with_a_done_proposal_is_reconciled_without_posting(self):
        self.h.to_review_approved()
        self.h.fake.pull_requests[7] = PullRequestRecord(7, "OPEN", self.h.sha, False, (), "SUCCESS")
        self.h.coordinator.propose_evidence("OM-01.02", self.h.sha, 7, [], "s")
        state = self.h.store.load_story("OM-01.02")
        state.phase = "review-approved"
        self.h.store.save_story(state)
        self.h.fake.calls = []
        self.assertEqual(fresh(self.h).resume("OM-01.02", ok_worktree).phase, "proposed")
        self.assertNotIn("post_comment", self.h.fake.calls)
        self.assertEqual(len(markers(self.h.fake, 21, "proposal")), 1)


def duplicate_issue(number: int = 121):
    return issue(number, "OM-01.02", "Install (duplicate marker)", labels=("story",), parent=1, depends_on="OM-01.01", tasks=4)


class D5DuplicateStableIdsAreRefused(unittest.TestCase):
    """B3/E5: a duplicated stable id anywhere makes the mapping ambiguous; refused before any
    by_id reduction, on the plan snapshot and on every fresh read."""

    def test_duplicate_in_the_plan_snapshot_is_refused_before_admission(self):
        fake = small_backlog()
        fake.add_issue(duplicate_issue(), "Ready", "OM-01.02")
        h = Harness(fake)
        try:
            decision = decide("OM-01.02", h.snapshot, h.policy)
            self.assertEqual((decision.outcome, decision.dispatchable, decision.entry_number), ("ambiguous-identity", False, None))
            self.assertEqual([d.outcome for d in plan(h.snapshot, h.policy)], ["ambiguous-identity"])
            with self.assertRaises(Refused) as ctx:
                h.reserve()
            self.assertEqual((ctx.exception.code, ctx.exception.detail["duplicates"]), ("ambiguous-identity", ["OM-01.02"]))
            self.assertEqual(h.store.load_story("OM-01.02"), None)
            self.assertEqual(markers(fake, 21, "claim") + markers(fake, 121, "claim"), [])
            self.assertEqual(h.store.story_counts()["delegated_tasks"], 0)
        finally:
            h.close()

    def test_duplicate_appearing_only_in_the_fresh_snapshot_is_refused(self):
        h = Harness(small_backlog())
        try:
            h.fake.add_issue(duplicate_issue(), "Ready", "OM-01.02")  # after the plan snapshot was taken
            with self.assertRaises(Refused) as ctx:
                h.reserve()
            self.assertEqual(ctx.exception.code, "ambiguous-identity")
            self.assertEqual(h.store.load_story("OM-01.02"), None)
            self.assertEqual(markers(h.fake, 21, "claim") + markers(h.fake, 121, "claim"), [])
        finally:
            h.close()

    def test_duplicate_epic_id_is_ambiguous_too(self):
        fake = small_backlog()
        fake.add_issue(issue(31, "E01", "Foundation again", labels=("epic",), epic_prereq="None"), "Backlog", "E01")
        h = Harness(fake)
        try:
            self.assertEqual(decide("OM-01.02", h.snapshot, h.policy).outcome, "ambiguous-identity")
        finally:
            h.close()

    def test_fresh_duplicate_refuses_resume_proposal_and_rebase_on_an_admitted_story(self):
        h = Harness(small_backlog())
        try:
            h.to_review_approved()
            h.fake.pull_requests[7] = PullRequestRecord(7, "OPEN", h.sha, False, (), "SUCCESS")
            h.fake.add_issue(duplicate_issue(), "Ready", "OM-01.02")
            for op in (lambda: h.coordinator.resume("OM-01.02", ok_worktree), lambda: h.coordinator.propose_evidence("OM-01.02", h.sha, 7, [], "s"),
                       lambda: h.coordinator.rebase_revisions("OM-01.02", "x")):
                with self.assertRaises(Refused) as ctx:
                    op()
                self.assertEqual(ctx.exception.code, "ambiguous-identity")
            self.assertEqual(h.store.load_story("OM-01.02").phase, "review-approved")
            self.assertEqual(markers(h.fake, 21, "proposal"), [])
        finally:
            h.close()

    def test_real_snapshot_with_a_duplicated_id_is_named_and_not_dispatchable(self):
        raw = json.loads((FIXTURES / "backlog-snapshot-2026-11-06.json").read_text(encoding="utf-8"))
        for entry in raw["entries"]:
            if entry["stable_id"] == "OM-01.03":
                entry["stable_id"] = "OM-01.02"
        snap = Snapshot.from_json(json.dumps(raw))
        self.assertEqual(snap.duplicate_ids(), ["OM-01.02"])
        self.assertIn("duplicate stable ids: ['OM-01.02']", verify_mapping(snap, load_tasks_index(ROOT))["problems"])
        h = Harness(small_backlog())
        try:
            self.assertEqual(decide("OM-01.02", snap, h.policy).outcome, "ambiguous-identity")
        finally:
            h.close()


class D6CapacityIsAuthorizedBeforeLaunch(unittest.TestCase):
    """V2: delegated-task capacity is reserved durably before a launch for implementation,
    review and repair; bind consumes exactly one authorization; crash or retry cannot
    double-spend or bypass the budget."""

    def test_exhausted_task_budget_refuses_admission_before_any_launch(self):
        h = Harness(small_backlog(), allow='["OM-01.02", "OM-01.04"]', max_stories_per_run="2", max_delegated_tasks="2")
        try:
            h.claim()
            h.checks()
            h.request_review()  # authorization 2 of 2
            h.coordinator.record_review("OM-01.02", h.sha, "changes-requested", "r", h.terminal())
            with self.assertRaises(BudgetExhausted):
                h.coordinator.authorize_repair("OM-01.02")
            h.coordinator.cancel("OM-01.02", "stop")
            with self.assertRaises(BudgetExhausted) as ctx:
                h.reserve("OM-01.04")
            self.assertIn("no task may be launched", str(ctx.exception))
            self.assertEqual(h.store.load_story("OM-01.04"), None)
            self.assertEqual(markers(h.fake, 23, "claim"), [])
            self.assertEqual(h.store.story_counts()["delegated_tasks"], 2)
        finally:
            h.close()

    def test_authorizations_are_idempotent_while_pending_and_bind_consumes_exactly_one(self):
        h = Harness(small_backlog())
        try:
            c = h.coordinator
            h.claim()
            h.checks()
            first = c.authorize_review("OM-01.02", h.sha).pending_authorization()
            again = fresh(h).authorize_review("OM-01.02", h.sha).pending_authorization()
            self.assertEqual(first["id"], again["id"])
            self.assertEqual(h.store.story_counts()["delegated_tasks"], 2)
            with self.assertRaises(ReceiptInvalid):
                c.bind_receipt("OM-01.02", receipt(IMPLEMENTER, "task-impl-2"), worktree_check=ok_worktree)  # wrong role for the slot
            state = c.bind_receipt("OM-01.02", REVIEWER, worktree_check=ok_worktree)
            self.assertEqual((state.phase, state.pending_authorization(), state.authorizations[-1]["task_id"]), ("review-requested", None, "task-review-1"))
            with self.assertRaises(Refused) as ctx:
                fresh(h).bind_receipt("OM-01.02", receipt(REVIEWER, "task-review-2"), worktree_check=ok_worktree)
            self.assertEqual(ctx.exception.code, "no-authorization")
            self.assertEqual(h.store.story_counts()["delegated_tasks"], 2)
        finally:
            h.close()

    def test_bind_without_an_authorization_is_refused_for_every_role(self):
        h = Harness(small_backlog())
        try:
            c = h.coordinator
            h.claim()
            h.checks()  # checks-passed: a reviewer launch without authorize-review
            with self.assertRaises(Refused) as ctx:
                c.bind_receipt("OM-01.02", REVIEWER, worktree_check=ok_worktree)
            self.assertEqual(ctx.exception.code, "no-authorization")
            h.request_review()
            c.record_review("OM-01.02", h.sha, "changes-requested", "r", h.terminal())  # changes-requested: a repair launch without authorize-repair
            with self.assertRaises(Refused) as ctx:
                c.bind_receipt("OM-01.02", receipt(IMPLEMENTER, "task-impl-2"), worktree_check=ok_worktree)
            self.assertEqual(ctx.exception.code, "no-authorization")
            self.assertEqual(h.store.load_story("OM-01.02").phase, "changes-requested")
        finally:
            h.close()

    def test_corrupted_run_counters_cannot_bypass_the_budget_after_a_restart(self):
        h = Harness(small_backlog(), max_delegated_tasks="2")
        try:
            h.claim()
            h.checks()
            h.coordinator.authorize_review("OM-01.02", h.sha)
            run = h.store.load_run()
            run.delegated_tasks = 0  # crash between the story save and the cache refresh, or tampering
            h.store.save_run(run)
            c2 = fresh(h)
            c2.bind_receipt("OM-01.02", REVIEWER, worktree_check=ok_worktree)
            c2.record_review("OM-01.02", h.sha, "changes-requested", "r", h.terminal())
            with self.assertRaises(BudgetExhausted):
                c2.authorize_repair("OM-01.02")
            self.assertEqual(c2.status()["budgets"]["delegated_tasks"], 2)
        finally:
            h.close()

    def test_an_unbound_authorization_stays_spent_after_cancel(self):
        h = Harness(small_backlog(), allow='["OM-01.02", "OM-01.04"]', max_stories_per_run="2", max_delegated_tasks="2")
        try:
            auth = h.reserve("OM-01.02").pending_authorization()  # slot 1 issued, never bound
            with self.assertRaises(Refused) as ctx:  # the tool cannot see launches: an unbound slot is an obligation until it is resolved
                h.coordinator.cancel("OM-01.02", "operator stop before launch")
            self.assertEqual((ctx.exception.code, h.store.load_story("OM-01.02").authorizations[0]["status"]), ("authorization-unresolved", "revoked"))
            h.coordinator.cancel("OM-01.02", "operator stop before launch", no_launch={"authorization": auth["id"], "reason": "delegate_task was never called"})
            self.assertEqual(h.store.load_story("OM-01.02").authorizations[0]["status"], "not-launched")
            h.claim("OM-01.04")  # slot 2
            h.coordinator.record_head("OM-01.04", h.sha, h.terminal("OM-01.04"))
            h.coordinator.run_checks("OM-01.04", h.sha, str(h.worktree), passing_runner)
            with self.assertRaises(BudgetExhausted):
                h.coordinator.authorize_review("OM-01.04", h.sha)
            self.assertEqual(h.store.load_story("OM-01.04").phase, "checks-passed")
        finally:
            h.close()

    def test_repair_round_is_counted_at_authorization_and_capped_before_launch(self):
        h = Harness(small_backlog())
        try:
            c = h.coordinator
            h.claim()
            h.checks(runner=failing_runner)
            state = c.authorize_repair("OM-01.02")
            self.assertEqual((state.phase, state.repair_rounds), ("repair-authorized", 1))
            self.assertEqual(fresh(h).authorize_repair("OM-01.02").repair_rounds, 1)  # idempotent, not a second round
            with self.assertRaises(Refused) as ctx:
                c.record_head("OM-01.02", h.sha, {"taskId": "task-impl-9", "status": "result_available"})  # nothing bound: no head without a bound task
            self.assertEqual(ctx.exception.code, "repair-required")
            c.bind_receipt("OM-01.02", receipt(IMPLEMENTER, "task-impl-2"), worktree_check=ok_worktree)
            h.checks(runner=failing_runner)
            h.repair(receipt_=receipt(IMPLEMENTER, "task-impl-3"))
            h.checks(runner=failing_runner)
            state = c.authorize_repair("OM-01.02")
            self.assertEqual((state.phase, state.repair_rounds, state.pending_authorization()), ("blocked", 2, None))
            self.assertEqual(h.store.story_counts(), {"stories_claimed": 1, "delegated_tasks": 3, "repair_rounds": 2})
        finally:
            h.close()
