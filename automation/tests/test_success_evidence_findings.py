"""Success-evidence repair (final independent ENG-01 evidence review of 2026-11-07, findings 1
and 2): terminal acknowledgement is not successful result evidence.

A released interrupted/failed/cancelled execution clears ownership but may never advance the
story: record-head and record-review are gated on the durable terminal record of exactly the
bound (task, run) in the relevant role (the reviewer's for exactly the authorized SHA), on the
direct path AND after record-task-terminal plus a reload. Legacy history is read from its
status, fail-closed; a proposal cannot rest on an unsuccessful reviewer. Cleanup, cancel, block
and restart stay possible for every supported terminal status."""

import json
import unittest

from automation.tests.fake_transport import small_backlog
from automation.tests.support import IMPLEMENTER, REVIEWER, Harness, evidence, failing_runner, git_commit, ok_worktree, passing_runner, receipt, run_of
from automation.unattended.coordinator import NON_SUCCESS_TERMINAL_TASK_STATES, SUCCESSFUL_TERMINAL_TASK_STATES, Coordinator
from automation.unattended.errors import Refused
from automation.unattended.github import PullRequestRecord
from automation.unattended.state import Store, StoryState

S = "OM-01.02"
OWNER = "task-impl-1"
REVIEW_TASK = "task-review-1"
UNSUCCESSFUL = ("interrupted", "failed", "cancelled")
CODE = {"interrupted": "worker-interrupted", "failed": "worker-unsuccessful", "cancelled": "worker-unsuccessful"}


class Base(unittest.TestCase):
    def setUp(self):
        self.h = Harness(small_backlog())
        self.c = self.h.coordinator

    def tearDown(self):
        self.h.close()

    def fresh(self) -> Coordinator:
        """A new Coordinator/Store over the persisted state, as after a process restart."""
        return Coordinator(self.h.fake, self.h.policy, Store(self.h.state_dir, "run-1"), live=True)

    def story(self) -> StoryState:
        return Store(self.h.state_dir, "run-1").load_story(S)

    def to_review_requested(self):
        self.h.claim()
        self.h.checks()
        self.h.request_review()


class ClassificationTests(unittest.TestCase):
    def test_only_completed_and_result_available_are_successful(self):
        self.assertEqual(SUCCESSFUL_TERMINAL_TASK_STATES, ("completed", "result_available"))
        for status in UNSUCCESSFUL + ("terminal",):
            self.assertIn(status, NON_SUCCESS_TERMINAL_TASK_STATES, status)

    def test_legacy_records_are_read_from_their_status_fail_closed(self):
        ok = StoryState.record_successful
        self.assertTrue(ok({"status": "completed"}))  # legacy: no flag
        self.assertTrue(ok({"status": "result_available", "successful": True}))
        for status in UNSUCCESSFUL + ("terminal",):
            self.assertFalse(ok({"status": status}), status)  # legacy unsuccessful: never defaulted to success
            self.assertFalse(ok({"status": status, "successful": True}), status)  # contradictory flag never counts
        self.assertFalse(ok({"status": "completed", "successful": False}))  # a false flag is honoured
        self.assertFalse(ok({"status": "completed", "successful": "true"}))  # a non-boolean flag is not a success
        self.assertFalse(ok({}))
        self.assertFalse(ok(None))


class ImplementerUnsuccessfulTests(Base):
    """Three unsuccessful statuses, direct and released-then-reloaded: no head is recorded."""

    def assert_not_advanced(self, phase="claimed"):
        state = self.story()
        self.assertEqual((state.phase, state.head_sha, state.approved_sha), (phase, None, None))

    def test_direct_unsuccessful_evidence_refuses_and_keeps_ownership(self):
        for status in UNSUCCESSFUL:
            with self.subTest(status=status):
                h = Harness(small_backlog())
                try:
                    h.claim()
                    with self.assertRaises(Refused) as ctx:
                        h.coordinator.record_head(S, h.sha, evidence(OWNER, status=status))
                    self.assertEqual(ctx.exception.code, CODE[status])
                    state = h.store.load_story(S)
                    self.assertEqual((state.phase, state.head_sha, state.active_task["runId"], state.task_history), ("claimed", None, run_of(OWNER, 1), []))
                    state = h.coordinator.record_head(S, h.sha, h.terminal(status="completed"))  # the same pair completing is still a result
                    self.assertEqual((state.phase, state.head_sha, state.active_task, state.task_history[-1]["successful"]), ("implemented", h.sha, None, True))
                finally:
                    h.close()

    def test_terminal_release_then_reload_refuses_record_head(self):
        for status in UNSUCCESSFUL:
            with self.subTest(status=status):
                h = Harness(small_backlog())
                try:
                    h.claim()
                    state = h.coordinator.record_task_terminal(S, evidence(OWNER, status=status))
                    self.assertEqual((state.phase, state.active_task, state.task_history[-1]["status"], state.task_history[-1]["successful"]), ("claimed", None, status, False))
                    c2 = Coordinator(h.fake, h.policy, Store(h.state_dir, "run-1"), live=True)
                    with self.assertRaises(Refused) as ctx:
                        c2.record_head(S, h.sha)
                    self.assertEqual(ctx.exception.code, CODE[status])
                    self.assertEqual(ctx.exception.detail.get("task_id"), OWNER)
                    with self.assertRaises(Refused):  # presenting the evidence again is no better (nothing is active)
                        c2.record_head(S, h.sha, evidence(OWNER, status=status))
                    reloaded = Store(h.state_dir, "run-1").load_story(S)
                    self.assertEqual((reloaded.phase, reloaded.head_sha, reloaded.active_task), ("claimed", None, None))
                    self.assertEqual([r["successful"] for r in reloaded.task_history], [False])
                finally:
                    h.close()

    def test_completed_control_direct_and_released_then_reloaded(self):
        # direct
        self.h.claim()
        state = self.c.record_head(S, self.h.sha, self.h.terminal(status="completed"))
        self.assertEqual((state.phase, state.head_sha, state.active_task), ("implemented", self.h.sha, None))
        # released first, then recorded by a fresh process
        h = Harness(small_backlog())
        try:
            h.claim()
            state = h.coordinator.record_task_terminal(S, evidence(OWNER, status="completed"))
            self.assertEqual((state.phase, state.active_task, state.task_history[-1]["successful"]), ("claimed", None, True))
            c2 = Coordinator(h.fake, h.policy, Store(h.state_dir, "run-1"), live=True)
            state = c2.record_head(S, h.sha)
            self.assertEqual((state.phase, state.head_sha, state.active_task), ("implemented", h.sha, None))
            state = c2.record_head(S, h.sha)  # idempotent
            self.assertEqual(state.phase, "implemented")
        finally:
            h.close()

    def test_stale_successful_worker_does_not_cover_an_unsuccessful_repair(self):
        """A prior successful implementer run exists; the current (repair) run was interrupted,
        failed or cancelled: the latest bound implementer execution is the one that counts."""
        for status in UNSUCCESSFUL:
            with self.subTest(status=status):
                h = Harness(small_backlog())
                try:
                    h.claim()
                    h.checks(runner=failing_runner)  # successful implementer run, then failed checks
                    h.repair(receipt_=receipt(IMPLEMENTER, "task-impl-2"))
                    state = h.coordinator.record_task_terminal(S, evidence("task-impl-2", status=status))
                    self.assertEqual((state.phase, state.active_task), ("claimed", None))
                    self.assertEqual([r["successful"] for r in state.task_history], [True, False])
                    c2 = Coordinator(h.fake, h.policy, Store(h.state_dir, "run-1"), live=True)
                    sha2 = git_commit(h.worktree, "repair")
                    with self.assertRaises(Refused) as ctx:
                        c2.record_head(S, sha2)
                    self.assertEqual((ctx.exception.code, ctx.exception.detail.get("task_id")), (CODE[status], "task-impl-2"))
                    self.assertEqual((h.store.load_story(S).phase, h.store.load_story(S).head_sha), ("claimed", h.sha))
                finally:
                    h.close()


class ReviewerUnsuccessfulTests(Base):
    """Three unsuccessful statuses, direct and released-then-reloaded: no verdict is recorded."""

    def test_direct_unsuccessful_evidence_refuses_and_keeps_ownership(self):
        for status in UNSUCCESSFUL:
            with self.subTest(status=status):
                h = Harness(small_backlog())
                try:
                    h.claim(); h.checks(); h.request_review()
                    with self.assertRaises(Refused) as ctx:
                        h.coordinator.record_review(S, h.sha, "approved", "report.md", h.terminal(status=status))
                    self.assertEqual(ctx.exception.code, CODE[status])
                    state = h.store.load_story(S)
                    self.assertEqual((state.phase, state.approved_sha, state.reviews, state.active_task["taskId"]), ("review-requested", None, [], REVIEW_TASK))
                    state = h.coordinator.record_review(S, h.sha, "approved", "report.md", h.terminal(status="completed"))
                    self.assertEqual((state.phase, state.approved_sha, state.active_task), ("review-approved", h.sha, None))
                finally:
                    h.close()

    def test_terminal_release_then_reload_refuses_record_review(self):
        for status in UNSUCCESSFUL:
            for verdict in ("approved", "changes-requested"):
                with self.subTest(status=status, verdict=verdict):
                    h = Harness(small_backlog())
                    try:
                        h.claim(); h.checks(); h.request_review()
                        state = h.coordinator.record_task_terminal(S, evidence(REVIEW_TASK, status=status))
                        self.assertEqual((state.phase, state.active_task, state.task_history[-1]["successful"]), ("review-requested", None, False))
                        c2 = Coordinator(h.fake, h.policy, Store(h.state_dir, "run-1"), live=True)
                        with self.assertRaises(Refused) as ctx:
                            c2.record_review(S, h.sha, verdict, "report.md")
                        self.assertEqual((ctx.exception.code, ctx.exception.detail.get("task_id"), ctx.exception.detail.get("sha")), (CODE[status], REVIEW_TASK, h.sha))
                        reloaded = Store(h.state_dir, "run-1").load_story(S)
                        self.assertEqual((reloaded.phase, reloaded.approved_sha, reloaded.reviews, reloaded.active_task), ("review-requested", None, [], None))
                        # no proposal either: the story never reached review-approved
                        h.fake.pull_requests[7] = PullRequestRecord(7, "OPEN", h.sha, False, (), "SUCCESS")
                        with self.assertRaises(Refused):
                            c2.propose_evidence(S, h.sha, 7, [], "s")
                        self.assertEqual(Store(h.state_dir, "run-1").load_story(S).phase, "review-requested")
                        # cleanup stays possible on a fresh process
                        state = c2.cancel(S, f"reviewer {status}")
                        self.assertEqual((state.phase, state.active_task), ("cancelled", None))
                    finally:
                        h.close()

    def test_completed_control_released_then_reloaded_records_the_verdict(self):
        self.to_review_requested()
        state = self.c.record_task_terminal(S, evidence(REVIEW_TASK, status="completed"))
        self.assertEqual((state.phase, state.active_task, state.task_history[-1]["successful"]), ("review-requested", None, True))
        state = self.fresh().record_review(S, self.h.sha, "approved", "report.md")
        self.assertEqual((state.phase, state.approved_sha), ("review-approved", self.h.sha))
        self.h.fake.pull_requests[7] = PullRequestRecord(7, "OPEN", self.h.sha, False, (), "SUCCESS")
        self.assertEqual(self.fresh().propose_evidence(S, self.h.sha, 7, [], "s").phase, "proposed")

    def test_a_successful_review_of_an_earlier_sha_does_not_cover_the_current_one(self):
        """Role and SHA correlation: the reviewer that completed reviewed sha1; the reviewer
        authorized for sha2 was interrupted. Its release must not let sha2 be approved."""
        self.h.claim(); self.h.checks(); self.h.request_review()
        state = self.c.record_review(S, self.h.sha, "changes-requested", "r1.md", self.h.terminal(status="completed"))
        self.assertEqual(state.phase, "changes-requested")
        self.h.repair(receipt_=receipt(IMPLEMENTER, "task-impl-2"))
        sha2 = git_commit(self.h.worktree, "fix")
        self.c.record_head(S, sha2, evidence("task-impl-2", status="completed"))
        self.c.run_checks(S, sha2, str(self.h.worktree), passing_runner)
        self.c.authorize_review(S, sha2)
        self.c.bind_receipt(S, receipt(REVIEWER, "task-review-2"), worktree_check=ok_worktree)
        self.c.record_task_terminal(S, evidence("task-review-2", status="interrupted"))
        with self.assertRaises(Refused) as ctx:
            self.fresh().record_review(S, sha2, "approved", "r2.md")
        self.assertEqual((ctx.exception.code, ctx.exception.detail.get("task_id"), ctx.exception.detail.get("sha")), ("worker-interrupted", "task-review-2", sha2))
        state = self.story()
        self.assertEqual((state.phase, state.approved_sha, len(state.reviews)), ("review-requested", None, 1))
        self.assertTrue(state.successful_execution(REVIEW_TASK, run_of(REVIEW_TASK, 1), "reviewer"))  # the sha1 record is intact but irrelevant
        # an implementer's successful record never stands in for the reviewer's
        self.assertIsNone(state.successful_execution("task-impl-2", run_of("task-impl-2", 1), "reviewer"))


class LegacyHistoryTests(Base):
    """Persisted history from before the ``successful`` flag (or with a contradictory one) is
    interpreted from its status; nothing is migrated or rewritten."""

    def rewrite_last_record(self, **changes):
        path = Store(self.h.state_dir, "run-1").story_path(S)
        raw = json.loads(path.read_text())
        record = raw["task_history"][-1]
        for key, value in changes.items():
            if value is ...:
                record.pop(key, None)
            else:
                record[key] = value
        path.write_text(json.dumps(raw))
        return record

    def test_legacy_implementer_record_without_flag_is_read_from_status(self):
        for status, advances in (("completed", True), ("result_available", True), ("failed", False), ("cancelled", False), ("interrupted", False), ("terminal", False)):
            with self.subTest(status=status):
                h = Harness(small_backlog())
                try:
                    h.claim()
                    h.coordinator.record_task_terminal(S, evidence(OWNER, status="completed"))
                    path = Store(h.state_dir, "run-1").story_path(S)
                    raw = json.loads(path.read_text())
                    raw["task_history"][-1].pop("successful")
                    raw["task_history"][-1]["status"] = status
                    path.write_text(json.dumps(raw))
                    c2 = Coordinator(h.fake, h.policy, Store(h.state_dir, "run-1"), live=True)
                    if advances:
                        self.assertEqual(c2.record_head(S, h.sha).phase, "implemented")
                    else:
                        with self.assertRaises(Refused) as ctx:
                            c2.record_head(S, h.sha)
                        self.assertEqual(ctx.exception.code, CODE.get(status, "worker-unsuccessful"))
                        self.assertEqual(Store(h.state_dir, "run-1").load_story(S).phase, "claimed")
                        self.assertEqual(json.loads(path.read_text())["task_history"][-1].get("successful"), None)  # not migrated
                finally:
                    h.close()

    def test_contradictory_flags_fail_closed(self):
        self.h.claim()
        self.c.record_task_terminal(S, evidence(OWNER, status="completed"))
        self.rewrite_last_record(status="failed", successful=True)  # a flag claiming success over a failed status
        with self.assertRaises(Refused) as ctx:
            self.fresh().record_head(S, self.h.sha)
        self.assertEqual(ctx.exception.code, "worker-unsuccessful")
        self.rewrite_last_record(status="completed", successful=False)  # a flag denying a completed status
        with self.assertRaises(Refused) as ctx:
            self.fresh().record_head(S, self.h.sha)
        self.assertEqual(ctx.exception.code, "worker-unsuccessful")
        self.rewrite_last_record(status="completed", successful=True)
        self.assertEqual(self.fresh().record_head(S, self.h.sha).phase, "implemented")

    def test_legacy_review_approved_over_an_unsuccessful_reviewer_cannot_propose(self):
        self.h.to_review_approved()
        self.rewrite_last_record(status="interrupted", successful=...)  # history as an older coordinator could have left it
        self.h.fake.pull_requests[7] = PullRequestRecord(7, "OPEN", self.h.sha, False, (), "SUCCESS")
        with self.assertRaises(Refused) as ctx:
            self.fresh().propose_evidence(S, self.h.sha, 7, [], "s")
        self.assertEqual((ctx.exception.code, ctx.exception.detail.get("task_id")), ("worker-interrupted", REVIEW_TASK))
        state = self.story()
        self.assertEqual((state.phase, state.proposal, [i.kind for i in state.intents if i.kind == "proposal"]), ("review-approved", None, []))
        self.assertEqual(self.fresh().cancel(S, "unsuccessful reviewer").phase, "cancelled")  # cleanup still possible


class CleanupStaysPossibleTests(Base):
    def test_every_unsuccessful_status_still_releases_cancels_blocks_and_restarts(self):
        for status in UNSUCCESSFUL:
            for role in ("implementer", "reviewer"):
                with self.subTest(status=status, role=role):
                    h = Harness(small_backlog())
                    try:
                        if role == "implementer":
                            h.claim(); task = OWNER; phase = "claimed"
                        else:
                            h.claim(); h.checks(); h.request_review(); task = REVIEW_TASK; phase = "review-requested"
                        state = h.coordinator.record_task_terminal(S, evidence(task, status=status))
                        self.assertEqual((state.phase, state.active_task), (phase, None))
                        c2 = Coordinator(h.fake, h.policy, Store(h.state_dir, "run-1"), live=True)
                        self.assertEqual(c2.resume(S, ok_worktree).phase, phase)  # restart keeps the released story where it is
                        self.assertTrue(Store(h.state_dir, "run-1").load_story(S).predecessor_terminal(task))
                        state = c2.block(S, "owner decision") if status == "failed" else c2.cancel(S, "released")
                        self.assertEqual((state.phase, state.active_task), ("blocked" if status == "failed" else "cancelled", None))
                        self.assertEqual(Coordinator(h.fake, h.policy, Store(h.state_dir, "run-1"), live=True).resume(S, ok_worktree).phase, state.phase)
                        self.assertEqual([r["successful"] for r in Store(h.state_dir, "run-1").load_story(S).task_history if r["taskId"] == task], [False])
                    finally:
                        h.close()

    def test_cancel_run_releases_unsuccessful_workers_without_advancing(self):
        self.h.claim()
        for status in UNSUCCESSFUL:
            with self.subTest(status=status):
                h = Harness(small_backlog())
                try:
                    h.claim()
                    result = h.coordinator.cancel_run("stop", task_evidence={S: evidence(OWNER, status=status)})
                    state = h.store.load_story(S)
                    self.assertEqual((state.phase, state.active_task, state.head_sha, state.task_history[-1]["successful"]), ("cancelled", None, None, False))
                    self.assertTrue(h.store.load_run().cancelled, result)
                finally:
                    h.close()


if __name__ == "__main__":
    unittest.main()
