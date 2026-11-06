"""Story lifecycle: claims, checks before review, SHA-bound approval, repair cap, regression,
cancel/resume, budgets and the evidence proposal."""

import unittest

from automation.tests.fake_transport import small_backlog
from automation.tests.support import IMPLEMENTER, REVIEWER, Harness, receipt
from automation.unattended.errors import BudgetExhausted, ReceiptInvalid, Refused
from automation.unattended.github import PullRequestRecord


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.h = Harness(small_backlog())
        self.c = self.h.coordinator

    def tearDown(self):
        self.h.close()

    def test_claim_writes_in_progress_and_marker(self):
        state = self.h.claim()
        self.assertEqual(state.phase, "claimed")
        self.assertEqual(self.h.fake.item_for(21).status, "In progress")
        self.assertEqual(state.status_before_claim, "Ready")
        self.assertEqual(self.h.store.load_run().stories_claimed, 1)
        self.assertEqual(self.h.store.load_run().delegated_tasks, 1)

    def test_claim_refuses_non_dispatchable(self):
        with self.assertRaises(Refused) as ctx:
            self.h.claim("OM-01.03")
        self.assertEqual(ctx.exception.detail["decision"]["outcome"], "not-allowlisted")

    def test_claim_requires_effort_in_receipt(self):
        with self.assertRaises(ReceiptInvalid):
            self.h.claim(receipt_={**IMPLEMENTER, "options": {}})
        self.assertIsNone(self.h.store.load_story("OM-01.02"))

    def test_claim_requires_worktree_identity(self):
        with self.assertRaises(Refused):
            self.c.claim("OM-01.02", self.h.snapshot, IMPLEMENTER, "/nope", "b", "c5", lambda p, b: (False, "missing"))

    def test_one_active_implementer_per_run(self):
        self.h = Harness(small_backlog(), allow='["OM-01.02", "OM-01.04"]', max_stories_per_run="2")
        self.h.claim("OM-01.02")
        with self.assertRaises(Refused) as ctx:
            self.h.claim("OM-01.04")
        self.assertIn("another story is active", str(ctx.exception))

    def test_story_budget(self):
        self.h = Harness(small_backlog(), allow='["OM-01.02", "OM-01.04"]')
        self.h.claim("OM-01.02")
        self.h.coordinator.cancel("OM-01.02", "test")
        with self.assertRaises(BudgetExhausted):
            self.h.claim("OM-01.04")

    def test_review_requires_passing_checks_at_head(self):
        self.h.claim()
        self.c.record_head("OM-01.02", "sha1")
        with self.assertRaises(Refused):
            self.c.request_review("OM-01.02", "sha1", REVIEWER)
        self.c.record_checks("OM-01.02", "sha1", False, {})
        with self.assertRaises(Refused):
            self.c.request_review("OM-01.02", "sha1", REVIEWER)
        with self.assertRaises(Refused):
            self.c.record_checks("OM-01.02", "sha2", True, {})  # checks for a sha that is not head

    def test_review_sha_must_match_head(self):
        self.h.claim()
        self.c.record_head("OM-01.02", "sha1")
        self.c.record_checks("OM-01.02", "sha1", True, {})
        self.c.request_review("OM-01.02", "sha1", REVIEWER)
        with self.assertRaises(Refused):
            self.c.record_review("OM-01.02", "sha0", "approved", "r")

    def test_new_commit_invalidates_approval(self):
        self.h.to_review_approved(sha="sha1")
        state = self.c.record_head("OM-01.02", "sha2")
        self.assertEqual(state.phase, "implemented")
        self.assertEqual(state.approved_sha, "sha1")  # history only; proposal refuses
        with self.assertRaises(Refused):
            self.c.propose_evidence("OM-01.02", "sha2", 7, [], "s")
        self.assertTrue(any(e["event"] == "head-recorded" and e["detail"]["approval_invalidated"] for e in self.h.store.read_journal()))

    def test_reviewer_task_must_be_fresh(self):
        self.h.claim()
        self.c.record_head("OM-01.02", "sha1")
        self.c.record_checks("OM-01.02", "sha1", True, {})
        with self.assertRaises(ReceiptInvalid):
            self.c.request_review("OM-01.02", "sha1", {**REVIEWER, "taskId": "task-impl-1"})

    def test_repair_cap_blocks_after_two_rounds(self):
        self.h.claim()
        for n, sha in enumerate(("s1", "s2"), start=1):
            self.c.record_head("OM-01.02", sha)
            self.c.record_checks("OM-01.02", sha, False, {})
            state = self.c.repair("OM-01.02", receipt(IMPLEMENTER, f"task-impl-{n + 1}"))
            self.assertEqual(state.repair_rounds, n)
            self.assertEqual(state.phase, "claimed")
        self.c.record_head("OM-01.02", "s3")
        self.c.record_checks("OM-01.02", "s3", False, {})
        state = self.c.repair("OM-01.02", receipt(IMPLEMENTER, "task-impl-9"))
        self.assertEqual(state.phase, "blocked")
        self.assertIn("repair rounds exhausted", state.blocked["reason"])
        self.assertEqual(self.h.fake.item_for(21).status, "Blocked")
        self.assertEqual(state.repair_rounds, 2)

    def test_review_regression_after_approval(self):
        self.h.to_review_approved(sha="sha1")
        state = self.c.record_review("OM-01.02", "sha1", "changes-requested", "second look")
        self.assertEqual(state.phase, "changes-requested")
        self.assertIsNone(state.approved_sha)
        self.assertTrue(state.reviews[-1]["regression"])
        state = self.c.repair("OM-01.02", receipt(IMPLEMENTER, "task-impl-2"))
        self.assertEqual(state.repair_rounds, 1)

    def test_delegated_task_budget(self):
        self.h = Harness(small_backlog(), max_delegated_tasks="2")
        self.h.claim()
        self.h.coordinator.record_head("OM-01.02", "s1")
        self.h.coordinator.record_checks("OM-01.02", "s1", True, {})
        self.h.coordinator.request_review("OM-01.02", "s1", REVIEWER)
        self.h.coordinator.record_review("OM-01.02", "s1", "changes-requested", "r")
        with self.assertRaises(BudgetExhausted):
            self.h.coordinator.repair("OM-01.02", receipt(IMPLEMENTER, "task-impl-2"))

    def test_wall_clock_budget(self):
        self.h.claim()
        self.c.record_head("OM-01.02", "s1")
        self.c.record_checks("OM-01.02", "s1", True, {})
        self.c.now = lambda: "2026-11-07T13:00:00Z"
        with self.assertRaises(BudgetExhausted):
            self.c.request_review("OM-01.02", "s1", REVIEWER)
        self.assertEqual(self.h.store.load_story("OM-01.02").phase, "checks-passed")

    def test_cancel_restores_ready(self):
        self.h.claim()
        state = self.c.cancel("OM-01.02", "operator stop")
        self.assertEqual(state.phase, "cancelled")
        self.assertEqual(self.h.fake.item_for(21).status, "Ready")
        release = [c for c in self.h.fake.comments[21] if c.marker and c.marker["kind"] == "release"]
        self.assertEqual(len(release), 1)
        with self.assertRaises(Refused):
            self.c.record_head("OM-01.02", "s1")  # cancelled stories accept no further work

    def test_resume_refuses_worktree_mismatch(self):
        self.h.claim()
        with self.assertRaises(Refused) as ctx:
            self.c.resume("OM-01.02", lambda p, b: (False, "worktree is on 'main', expected 't3/om-01-02'"))
        self.assertIn("cannot resume", str(ctx.exception))
        state = self.c.resume("OM-01.02", lambda p, b: (True, "ok"))
        self.assertEqual(state.phase, "claimed")

    def test_cancel_run_stops_everything(self):
        self.h.claim()
        self.c.cancel_run("budget")
        self.assertTrue(self.h.store.load_run().cancelled)
        with self.assertRaises(BudgetExhausted):
            self.h.claim()

    def test_propose_evidence_posts_proposal_and_in_review(self):
        self.h.to_review_approved(sha="sha1")
        self.h.fake.pull_requests[7] = PullRequestRecord(7, "OPEN", "sha1", False, ({"state": "APPROVED", "commit": "sha1", "author": "rev", "submitted_at": "t"},), "SUCCESS")
        state = self.c.propose_evidence("OM-01.02", "sha1", 7, ["OM-01.02-T1"], "summary")
        self.assertEqual(state.phase, "proposed")
        self.assertEqual(self.h.fake.item_for(21).status, "In review")
        proposal = [c for c in self.h.fake.comments[21] if c.marker and c.marker["kind"] == "proposal"]
        self.assertEqual(len(proposal), 1)
        self.assertIn("- [ ] OM-01.02-T1", proposal[0].body)  # proposed, never ticked in the body
        self.assertEqual(self.h.fake.issues[21].body.count("[x]"), 0)
        self.assertNotIn("Done", [self.h.fake.item_for(21).status])

    def test_propose_refuses_merged_pr_head_mismatch_and_github_regression(self):
        self.h.to_review_approved(sha="sha1")
        self.h.fake.pull_requests[7] = PullRequestRecord(7, "MERGED", "sha1", True, (), "SUCCESS")
        with self.assertRaises(Refused):
            self.c.propose_evidence("OM-01.02", "sha1", 7, [], "s")
        self.h.fake.pull_requests[7] = PullRequestRecord(7, "OPEN", "sha9", False, (), None)
        with self.assertRaises(Refused):
            self.c.propose_evidence("OM-01.02", "sha1", 7, [], "s")
        self.h.fake.pull_requests[7] = PullRequestRecord(7, "OPEN", "sha1", False, ({"state": "CHANGES_REQUESTED", "commit": "sha1", "author": "rev", "submitted_at": "t"},), "SUCCESS")
        with self.assertRaises(Refused):
            self.c.propose_evidence("OM-01.02", "sha1", 7, [], "s")
        self.assertEqual(self.h.store.load_story("OM-01.02").phase, "changes-requested")

    def test_no_merge_or_done_path_exists(self):
        import inspect

        from automation.unattended import cli, coordinator, github

        source = inspect.getsource(coordinator) + inspect.getsource(cli) + inspect.getsource(github)
        self.assertNotIn("pr merge", source)
        self.assertNotIn("mergePullRequest", source)
        self.assertNotIn('"Done"', inspect.getsource(coordinator).split("def _write_status")[1].split("def claim")[0])
        for line in inspect.getsource(coordinator).splitlines():
            if "_write_status(" in line and "def " not in line:
                self.assertNotIn("Done", line)
