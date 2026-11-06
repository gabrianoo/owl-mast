"""Story lifecycle: claims, executed checks before review, SHA-bound approval, budgeted
repair, per-reviewer objections, cancel/resume ordering, budgets and the evidence proposal."""

import inspect
import unittest
from pathlib import Path

from automation.tests.fake_transport import small_backlog
from automation.tests.support import IMPLEMENTER, REVIEWER, Harness, failing_runner, git_commit, ok_worktree, passing_runner, receipt
from automation.unattended import cli, coordinator, github
from automation.unattended.errors import BudgetExhausted, ReceiptInvalid, Refused
from automation.unattended.coordinator import Coordinator
from automation.unattended.github import PullRequestRecord
from automation.unattended.state import Store


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.h = Harness(small_backlog())
        self.c = self.h.coordinator

    def tearDown(self):
        self.h.close()

    def test_reserve_precedes_delegation_and_bind_binds_the_receipt(self):
        state = self.h.reserve()
        self.assertEqual((state.phase, state.worker_state), ("reserved", "none"))
        self.assertEqual(self.h.store.load_run().delegated_tasks, 0)
        with self.assertRaises(Refused):
            self.c.record_head("OM-01.02", "s1")  # nothing bound yet
        with self.assertRaises(Refused):
            self.c.bind_receipt("OM-01.04", IMPLEMENTER, str(self.h.worktree), "t3/om-01-02", ok_worktree)  # no reservation
        state = self.c.bind_receipt("OM-01.02", IMPLEMENTER, str(self.h.worktree), "t3/om-01-02", ok_worktree)
        self.assertEqual((state.phase, state.worker_state), ("claimed", "running"))
        self.assertEqual(self.h.store.load_run().delegated_tasks, 1)
        with self.assertRaises(Refused):
            self.c.bind_receipt("OM-01.02", IMPLEMENTER, str(self.h.worktree), "t3/om-01-02", ok_worktree)  # bound once

    def test_claim_posts_marker_and_records_revisions(self):
        state = self.h.claim()
        self.assertEqual(state.phase, "claimed")
        self.assertEqual(sorted(state.revisions), ["E01", "OM-01.01", "OM-01.02"])
        self.assertEqual(self.h.fake.item_for(21).status, "Ready")  # owner field untouched
        self.assertEqual(self.h.store.load_run().stories_claimed, 1)
        self.assertEqual(self.h.store.load_run().delegated_tasks, 1)

    def test_claim_refuses_non_dispatchable(self):
        with self.assertRaises(Refused) as ctx:
            self.h.claim("OM-01.03")
        self.assertEqual(ctx.exception.detail["decision"]["outcome"], "not-allowlisted")

    def test_claim_requires_effort_in_receipt(self):
        with self.assertRaises(ReceiptInvalid):
            self.h.claim(receipt_={**IMPLEMENTER, "options": {}})
        self.assertEqual(self.h.store.load_story("OM-01.02").phase, "reserved")

    def test_claim_requires_worktree_identity(self):
        self.h.reserve()
        with self.assertRaises(Refused):
            self.c.bind_receipt("OM-01.02", IMPLEMENTER, "/nope", "b", lambda p, b: (False, "missing"))

    def test_one_active_implementer_per_run(self):
        self.h = Harness(small_backlog(), allow='["OM-01.02", "OM-01.04"]', max_stories_per_run="2")
        self.h.claim("OM-01.02")
        with self.assertRaises(Refused) as ctx:
            self.h.claim("OM-01.04")
        self.assertIn("another story is active", str(ctx.exception))

    def test_story_budget(self):
        self.h = Harness(small_backlog(), allow='["OM-01.02", "OM-01.04"]')
        self.h.claim("OM-01.02")
        self.h.coordinator.cancel("OM-01.02", "test", self.h.terminal())
        with self.assertRaises(BudgetExhausted):
            self.h.claim("OM-01.04")

    # -- checks --------------------------------------------------------------------------
    def test_checks_execute_full_set_on_exact_head(self):
        self.h.claim()
        state = self.h.checks()
        self.assertEqual(state.phase, "checks-passed")
        last = state.checks[-1]
        self.assertEqual(len(last["commands"]), len(self.h.policy.check_commands))
        self.assertTrue(last["executed"] and last["clean_before"] and last["clean_after"])
        self.assertEqual(last["head_after"], self.h.sha)

    def test_failed_command_fails_checks_but_runs_whole_set(self):
        self.h.claim()
        state = self.h.checks(runner=failing_runner)
        self.assertEqual(state.phase, "checks-failed")
        self.assertEqual(len(state.checks[-1]["commands"]), len(self.h.policy.check_commands))

    def test_checks_refuse_wrong_head_dirty_tree_and_foreign_cwd(self):
        self.h.claim()
        self.c.record_head("OM-01.02", "notthehead")
        with self.assertRaises(Refused):
            self.c.run_checks("OM-01.02", "notthehead", str(self.h.worktree), passing_runner)
        self.c.record_head("OM-01.02", self.h.sha)
        (self.h.worktree / "dirty.txt").write_text("x")
        with self.assertRaises(Refused):
            self.c.run_checks("OM-01.02", self.h.sha, str(self.h.worktree), passing_runner)
        (self.h.worktree / "dirty.txt").unlink()
        with self.assertRaises(Refused):
            self.c.run_checks("OM-01.02", self.h.sha, str(self.h.worktree.parent), passing_runner)

    def test_checks_that_modify_the_tree_do_not_pass(self):
        self.h.claim()

        def dirtying(argv, cwd, timeout):
            (Path(cwd) / "generated.txt").write_text("x")
            return passing_runner(argv, cwd, timeout)

        state = self.h.checks(runner=dirtying)
        self.assertEqual(state.phase, "checks-failed")
        self.assertFalse(state.checks[-1]["clean_after"])

    def test_no_asserted_pass_exists(self):
        self.assertFalse(hasattr(self.c, "record_checks"))
        self.assertNotIn("record-checks", inspect.getsource(cli))

    def test_review_requires_executed_passing_checks_at_head(self):
        self.h.claim()
        self.c.record_head("OM-01.02", self.h.sha)
        with self.assertRaises(Refused):
            self.c.request_review("OM-01.02", self.h.sha, REVIEWER)
        self.h.checks(runner=failing_runner)
        with self.assertRaises(Refused):
            self.c.request_review("OM-01.02", self.h.sha, REVIEWER)
        self.c.repair("OM-01.02", receipt(IMPLEMENTER, "task-impl-2"))
        # tamper: a check record whose command list is shorter than the configured set is refused
        self.h.checks()
        state = self.h.store.load_story("OM-01.02")
        state.checks[-1]["commands"] = state.checks[-1]["commands"][:1]
        self.h.store.save_story(state)
        with self.assertRaises(Refused):
            self.c.request_review("OM-01.02", self.h.sha, REVIEWER)

    # -- review / repair ----------------------------------------------------------------
    def test_unreported_worktree_change_invalidates_evidence_at_review_admission(self):
        """Round-1 findings R1-B5/E5/V5: HEAD and cleanliness are re-read at the gate."""
        self.h.claim()
        self.h.checks()
        new = git_commit(self.h.worktree, "changed")
        with self.assertRaises(Refused) as ctx:
            self.c.request_review("OM-01.02", self.h.sha, REVIEWER)
        self.assertEqual(ctx.exception.code, "evidence-invalidated")
        state = self.h.store.load_story("OM-01.02")
        self.assertEqual((state.phase, state.head_sha), ("implemented", new))
        self.assertTrue(any(e["event"] == "unreported-worktree-change" for e in self.h.store.read_journal()))

    def test_dirty_worktree_at_review_admission_is_refused(self):
        self.h.claim()
        self.h.checks()
        (self.h.worktree / "README").write_text("changed after checks")
        with self.assertRaises(Refused) as ctx:
            self.c.request_review("OM-01.02", self.h.sha, REVIEWER)
        self.assertEqual(ctx.exception.code, "evidence-invalidated")
        self.assertEqual(self.h.store.load_story("OM-01.02").phase, "implemented")

    def test_worktree_change_before_review_verdict_or_proposal_invalidates(self):
        self.h.claim()
        self.h.checks()
        self.c.request_review("OM-01.02", self.h.sha, REVIEWER)
        (self.h.worktree / "README").write_text("edited during review")
        with self.assertRaises(Refused):
            self.c.record_review("OM-01.02", self.h.sha, "approved", "r")
        self.assertEqual(self.h.store.load_story("OM-01.02").phase, "implemented")
        h2 = Harness(small_backlog())
        try:
            h2.to_review_approved()
            h2.fake.pull_requests[7] = PullRequestRecord(7, "OPEN", h2.sha, False, (), "SUCCESS")
            git_commit(h2.worktree, "late")
            with self.assertRaises(Refused):
                h2.coordinator.propose_evidence("OM-01.02", h2.sha, 7, [], "s")
            self.assertEqual(h2.store.load_story("OM-01.02").phase, "implemented")
            self.assertEqual([c for c in h2.fake.comments[21] if c.marker["kind"] == "proposal"], [])
        finally:
            h2.close()

    def test_review_sha_must_match_head(self):
        self.h.claim()
        self.h.checks()
        self.c.request_review("OM-01.02", self.h.sha, REVIEWER)
        with self.assertRaises(Refused):
            self.c.record_review("OM-01.02", "sha0", "approved", "r")

    def test_new_commit_invalidates_approval(self):
        self.h.to_review_approved()
        new = git_commit(self.h.worktree, "more.txt")
        state = self.c.record_head("OM-01.02", new)
        self.assertEqual(state.phase, "implemented")
        with self.assertRaises(Refused):
            self.c.propose_evidence("OM-01.02", new, 7, [], "s")
        self.assertTrue(any(e["event"] == "head-recorded" and e["detail"]["approval_invalidated"] for e in self.h.store.read_journal()))

    def test_reviewer_task_must_be_fresh(self):
        self.h.claim()
        self.h.checks()
        with self.assertRaises(ReceiptInvalid):
            self.c.request_review("OM-01.02", self.h.sha, {**REVIEWER, "taskId": "task-impl-1"})

    def test_record_head_after_failure_requires_budgeted_repair(self):
        """Reviewer probe B4: failed phases cannot loop through record-head."""
        self.h.claim()
        self.h.checks(runner=failing_runner)
        for n in range(5):
            with self.assertRaises(Refused) as ctx:
                self.c.record_head("OM-01.02", f"sha{n}")
            self.assertEqual(ctx.exception.code, "repair-required")
        state = self.h.store.load_story("OM-01.02")
        self.assertEqual((state.phase, state.repair_rounds), ("checks-failed", 0))
        self.c.repair("OM-01.02", receipt(IMPLEMENTER, "task-impl-2"))
        self.assertEqual(self.h.store.load_story("OM-01.02").repair_rounds, 1)

    def test_repair_cap_blocks_after_two_rounds(self):
        self.h.claim()
        for n in range(1, 3):
            self.h.checks(runner=failing_runner)
            state = self.c.repair("OM-01.02", receipt(IMPLEMENTER, f"task-impl-{n + 1}"))
            self.assertEqual((state.repair_rounds, state.phase), (n, "claimed"))
        self.h.checks(runner=failing_runner)
        state = self.c.repair("OM-01.02", receipt(IMPLEMENTER, "task-impl-9"))
        self.assertEqual(state.phase, "blocked")
        self.assertIn("repair rounds exhausted", state.blocked["reason"])
        self.assertEqual(len([c for c in self.h.fake.comments[21] if c.marker["kind"] == "block"]), 1)
        self.assertEqual(self.h.fake.item_for(21).status, "Ready")  # Status is not written

    def test_review_regression_after_approval(self):
        self.h.to_review_approved()
        state = self.c.record_review("OM-01.02", self.h.sha, "changes-requested", "second look")
        self.assertEqual((state.phase, state.approved_sha), ("changes-requested", None))
        self.assertTrue(state.reviews[-1]["regression"])
        with self.assertRaises(Refused):
            self.c.record_head("OM-01.02", "s2")
        self.assertEqual(self.c.repair("OM-01.02", receipt(IMPLEMENTER, "task-impl-2")).repair_rounds, 1)

    def test_delegated_task_budget(self):
        self.h = Harness(small_backlog(), max_delegated_tasks="2")
        self.h.claim()
        self.h.checks()
        self.h.coordinator.request_review("OM-01.02", self.h.sha, REVIEWER)
        self.h.coordinator.record_review("OM-01.02", self.h.sha, "changes-requested", "r")
        with self.assertRaises(BudgetExhausted):
            self.h.coordinator.repair("OM-01.02", receipt(IMPLEMENTER, "task-impl-2"))

    def test_wall_clock_budget(self):
        self.h.claim()
        self.h.checks()
        self.c.now = lambda: "2026-11-07T13:00:00Z"
        with self.assertRaises(BudgetExhausted):
            self.c.request_review("OM-01.02", self.h.sha, REVIEWER)
        self.assertEqual(self.h.store.load_story("OM-01.02").phase, "checks-passed")

    # -- cancel / resume ------------------------------------------------------------------
    def test_cancel_posts_release_and_accepts_no_further_work(self):
        self.h.claim()
        state = self.c.cancel("OM-01.02", "operator stop", self.h.terminal())
        self.assertEqual(state.phase, "cancelled")
        self.assertEqual(len([c for c in self.h.fake.comments[21] if c.marker["kind"] == "release"]), 1)
        self.assertEqual(self.h.fake.item_for(21).status, "Ready")
        with self.assertRaises(Refused):
            self.c.record_head("OM-01.02", "s1")

    def test_resume_checks_identity_before_any_effect(self):
        """Reviewer finding V6: an incomplete claim is not completed on a wrong worktree."""
        from automation.unattended.errors import Outage

        self.h.fake.fail_once["post_comment"] = Outage("503")
        with self.assertRaises(Outage):
            self.h.claim()
        state = self.h.store.load_story("OM-01.02")
        state.claim.update({"worktree_path": str(self.h.worktree), "branch": "t3/om-01-02"})
        self.h.store.save_story(state)
        with self.assertRaises(Refused) as ctx:
            self.c.resume("OM-01.02", lambda p, b: (False, "wrong worktree"))
        self.assertEqual(ctx.exception.code, "worktree-mismatch")
        state = self.h.store.load_story("OM-01.02")
        self.assertEqual(state.phase, "claim-incomplete")
        self.assertEqual(self.h.fake.comments[21], [])
        self.assertEqual(self.c.resume("OM-01.02", ok_worktree).phase, "reserved")

    def test_cancel_run_stops_everything(self):
        self.h = Harness(small_backlog(), allow='["OM-01.02", "OM-01.04"]', max_stories_per_run="2")
        self.h.claim()
        self.h.coordinator.record_head("OM-01.02", self.h.sha)  # worker returned
        result = self.h.coordinator.cancel_run("budget")
        self.assertEqual(result["awaiting_worker_termination"], [])
        self.assertEqual(self.h.store.load_story("OM-01.02").phase, "cancelled")
        self.assertTrue(self.h.store.load_run().cancelled)
        with self.assertRaises(BudgetExhausted):
            self.h.reserve("OM-01.04")

    # -- proposal -------------------------------------------------------------------------
    def test_propose_evidence_posts_proposal_only(self):
        self.h.to_review_approved()
        self.h.fake.pull_requests[7] = PullRequestRecord(7, "OPEN", self.h.sha, False, ({"state": "APPROVED", "commit": self.h.sha, "author": "rev", "submitted_at": "t"},), "SUCCESS")
        state = self.c.propose_evidence("OM-01.02", self.h.sha, 7, ["OM-01.02-T1"], "summary")
        self.assertEqual(state.phase, "proposed")
        proposal = [c for c in self.h.fake.comments[21] if c.marker["kind"] == "proposal"]
        self.assertEqual(len(proposal), 1)
        self.assertIn("- [ ] OM-01.02-T1", proposal[0].body)
        self.assertEqual(self.h.fake.issues[21].body.count("[x]"), 0)
        self.assertEqual(self.h.fake.item_for(21).status, "Ready")

    def test_propose_refuses_merged_pr_and_head_mismatch(self):
        self.h.to_review_approved()
        self.h.fake.pull_requests[7] = PullRequestRecord(7, "MERGED", self.h.sha, True, (), "SUCCESS")
        with self.assertRaises(Refused):
            self.c.propose_evidence("OM-01.02", self.h.sha, 7, [], "s")
        self.h.fake.pull_requests[7] = PullRequestRecord(7, "OPEN", "sha9", False, (), None)
        with self.assertRaises(Refused):
            self.c.propose_evidence("OM-01.02", self.h.sha, 7, [], "s")

    def test_another_reviewers_approval_does_not_mask_an_objection(self):
        """Reviewer probe B8/E10: objections are effective per reviewer."""
        self.h.to_review_approved()
        sha = self.h.sha
        self.h.fake.pull_requests[7] = PullRequestRecord(7, "OPEN", sha, False, (
            {"state": "CHANGES_REQUESTED", "commit": sha, "author": "A", "submitted_at": "1"},
            {"state": "APPROVED", "commit": sha, "author": "B", "submitted_at": "2"},
        ), "SUCCESS")
        with self.assertRaises(Refused) as ctx:
            self.c.propose_evidence("OM-01.02", sha, 7, [], "s")
        self.assertIn("A", str(ctx.exception))
        self.assertEqual(self.h.store.load_story("OM-01.02").phase, "changes-requested")

    def test_objection_at_an_earlier_commit_still_counts_until_dismissed_or_re_reviewed(self):
        self.h.to_review_approved()
        sha = self.h.sha
        pr = PullRequestRecord(7, "OPEN", sha, False, (
            {"state": "CHANGES_REQUESTED", "commit": "old", "author": "A", "submitted_at": "1"},
            {"state": "APPROVED", "commit": sha, "author": "B", "submitted_at": "2"},
        ), "SUCCESS")
        self.assertEqual(coordinator.outstanding_objections(pr), ["A"])
        pr2 = PullRequestRecord(7, "OPEN", sha, False, pr.reviews + ({"state": "DISMISSED", "commit": "old", "author": "A", "submitted_at": "3"},), "SUCCESS")
        self.assertEqual(coordinator.outstanding_objections(pr2), [])
        pr3 = PullRequestRecord(7, "OPEN", sha, False, pr.reviews + ({"state": "COMMENTED", "commit": sha, "author": "A", "submitted_at": "3"},), "SUCCESS")
        self.assertEqual(coordinator.outstanding_objections(pr3), ["A"])
        self.h.fake.pull_requests[7] = pr2
        self.assertEqual(self.c.propose_evidence("OM-01.02", sha, 7, [], "s").phase, "proposed")

    def test_no_merge_status_or_done_write_path_exists(self):
        source = inspect.getsource(coordinator) + inspect.getsource(cli) + inspect.getsource(github)
        for needle in ("pr merge", "mergePullRequest", "updateProjectV2ItemFieldValue", "set_project_status", "updateIssue", "closeIssue"):
            self.assertNotIn(needle, source)

    def test_every_operation_refuses_live_before_any_call(self):
        self.h.fake.live = True
        live = Coordinator(self.h.fake, self.h.policy, Store(self.h.state_dir, "run-live"), live=True)
        self.h.fake.calls = []
        for op in (lambda: live.reserve("OM-01.02", self.h.snapshot, "b"), lambda: live.resume("OM-01.02"), lambda: live.cancel_run("x"),
                   lambda: live.rebase_revisions("OM-01.02", "x"), lambda: live.block("OM-01.02", "x")):
            with self.assertRaises(Refused) as ctx:
                op()
            self.assertEqual(ctx.exception.code, "live-execution-disabled")
        self.assertEqual(self.h.fake.calls, [])
        self.assertEqual(live.status()["environment"], "live")
