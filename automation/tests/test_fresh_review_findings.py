"""Repair pass 1 after the fresh independent review of 8b54fc6974abcf57e9c387b0a55db3f5223a19e8
(PR #107, remediation pass 1): the four code findings F1–F4 the coordinator reproduced with
``/tmp/eng01-independent-review.py`` (transcript in
``evidence/fresh-review-8b54fc69-probe-before-2026-11-06.txt``). Each class combines the
transition with a crash/restart (fresh coordinator from disk), the cleanup failure path and
the zero/one/many marker possibilities, and asserts what persisted, what was posted and what
other runs observe. Nothing here touches live GitHub or T3."""

import json
import unittest

from automation.tests.fake_transport import CrashAfterEffect, small_backlog
from automation.tests.support import IMPLEMENTER, REVIEWER, Harness, failing_runner, ok_worktree, passing_runner, receipt
from automation.tests.test_final_findings import fresh, markers, pending_proposal
from automation.unattended.backlog import take_snapshot
from automation.unattended.coordinator import Coordinator
from automation.unattended.errors import BudgetExhausted, Outage, ReceiptInvalid, Refused
from automation.unattended.state import Store

S = "OM-01.02"
LATER = "2099-01-01T00:00:00Z"  # far past max_wall_clock_minutes


def crashed_claim(h: Harness) -> None:
    """The claim comment landed and the process died before the checkpoint: claim intent
    pending on disk, one claim marker on GitHub."""
    h.fake.crash_after_post = True
    with unittest.TestCase().assertRaises(CrashAfterEffect):
        h.reserve()
    state = h.store.load_story(S)
    assert (state.phase, state.intent("claim").status) == ("claim-incomplete", "pending"), (state.phase, state.intent("claim").status)
    assert len(markers(h.fake, 21, "claim")) == 1


def other_run(h: Harness, run_id: str = "run-2") -> Coordinator:
    return Coordinator(h.fake, h.policy, Store(h.state_dir, run_id), live=True)


class F1StaleClaimCancellationReleasesTheClaim(unittest.TestCase):
    """F1: a reservation that cannot complete (owner changed Status before the checkpoint)
    is cancelled together with the release it owes; the claim never blocks another run."""

    def setUp(self):
        self.h = Harness(small_backlog())

    def tearDown(self):
        self.h.close()

    def test_crash_after_the_claim_post_then_owner_change_cancels_and_releases_in_one_write(self):
        crashed_claim(self.h)
        self.h.fake.set_status_externally(21, "Blocked")
        seen = []
        store = Store(self.h.state_dir, "run-1")
        original = store.save_story

        def spy(state):
            original(state)
            seen.append((state.phase, state.intent("release") is not None, state.intent("release").status if state.intent("release") else None))

        store.save_story = spy
        state = Coordinator(self.h.fake, self.h.policy, store, live=True).resume(S, ok_worktree)
        self.assertEqual((state.phase, state.intent("claim").status, state.intent("release").status), ("cancelled", "abandoned", "done"))
        self.assertEqual((state.blocked["release_owed"], len(state.blocked["claim_comment_ids"]), state.pending_authorization()), (True, 1, None))
        self.assertFalse(any(phase == "cancelled" and not has_release for phase, has_release, _ in seen), seen)  # never cancelled without the owed release intent
        self.assertEqual((len(markers(self.h.fake, 21, "claim")), len(markers(self.h.fake, 21, "release"))), (1, 1))
        self.assertEqual(other_run(self.h)._active_foreign_claims(21, S), [])
        self.assertEqual(self.h.store.story_counts()["delegated_tasks"], 1)  # the issued slot stays spent
        self.h.fake.calls = []
        self.assertEqual(fresh(self.h).resume(S, ok_worktree).phase, "cancelled")  # idempotent: nothing more is posted
        self.assertNotIn("post_comment", self.h.fake.calls)
        with self.assertRaises(Refused):
            fresh(self.h).cancel(S, "cleanup")  # terminal already; nothing is owed
        self.h.fake.set_status_externally(21, "Ready")  # the owner re-accepts: another run may now reserve the story
        snapshot = take_snapshot(self.h.fake, "gabrianoo/owl-mast", "2026-11-06T14:00:00Z")
        self.assertEqual(other_run(self.h).reserve(S, snapshot, "c5d9d2e").phase, "reserved")

    def test_release_post_failure_is_recorded_and_replayed_on_the_next_resume(self):
        crashed_claim(self.h)
        self.h.fake.set_status_externally(21, "Blocked")
        self.h.fake.fail_once["post_comment"] = Outage("503")
        state = fresh(self.h).resume(S, ok_worktree)
        self.assertEqual((state.phase, state.intent("release").status, state.blocked["github_error"]["code"]), ("cancelled", "pending", "outage"))
        self.assertEqual(markers(self.h.fake, 21, "release"), [])
        self.assertEqual(len(other_run(self.h)._active_foreign_claims(21, S)), 1)  # honest: still claimed until the release lands
        state = fresh(self.h).resume(S, ok_worktree)  # restart: the pending cleanup is replayed first
        self.assertEqual((state.phase, state.intent("release").status), ("cancelled", "done"))
        self.assertEqual(len(markers(self.h.fake, 21, "release")), 1)
        self.assertEqual(other_run(self.h)._active_foreign_claims(21, S), [])
        self.h.fake.calls = []
        fresh(self.h).resume(S, ok_worktree)
        self.assertNotIn("post_comment", self.h.fake.calls)
        self.assertEqual(len(markers(self.h.fake, 21, "release")), 1)

    def test_crash_right_after_the_cancellation_save_leaves_the_release_pending_for_the_next_resume(self):
        crashed_claim(self.h)
        self.h.fake.set_status_externally(21, "Blocked")
        store = Store(self.h.state_dir, "run-1")
        original = store.journal

        def crash(story, event, detail=None):
            if event == "resume-claim-abandoned":
                raise RuntimeError("synthetic crash after the cancellation save, before the release post")
            return original(story, event, detail)

        store.journal = crash
        with self.assertRaises(RuntimeError):
            Coordinator(self.h.fake, self.h.policy, store, live=True).resume(S, ok_worktree)
        state = self.h.store.load_story(S)
        self.assertEqual((state.phase, [i.op for i in state.pending_intents()]), ("cancelled", ["release"]))
        self.assertEqual(markers(self.h.fake, 21, "release"), [])
        state = fresh(self.h).resume(S, ok_worktree)
        self.assertEqual((state.phase, state.pending_intents()), ("cancelled", []))
        self.assertEqual(len(markers(self.h.fake, 21, "release")), 1)

    def test_a_claim_that_never_landed_owes_no_release(self):
        self.h.fake.fail_once["post_comment"] = Outage("503")
        with self.assertRaises(Outage):
            self.h.reserve()
        self.assertEqual(self.h.fake.comments[21], [])
        self.h.fake.set_status_externally(21, "Blocked")
        state = fresh(self.h).resume(S, ok_worktree)
        self.assertEqual((state.phase, state.intent("claim").status, state.intent("release"), state.blocked["release_owed"]), ("cancelled", "abandoned", None, False))
        self.assertEqual(self.h.fake.comments[21], [])  # no stray comment on the owner's issue
        self.assertEqual(other_run(self.h)._active_foreign_claims(21, S), [])

    def test_duplicate_claim_markers_are_released_once_and_journaled(self):
        crashed_claim(self.h)
        self.h.fake.post_comment(21, self.h.store.load_story(S).intent("claim").body)  # a concurrent writer posted the same event
        self.assertEqual(len(markers(self.h.fake, 21, "claim")), 2)
        self.h.fake.set_status_externally(21, "Blocked")
        state = fresh(self.h).resume(S, ok_worktree)
        self.assertEqual((state.phase, len(state.blocked["claim_comment_ids"]), state.intent("release").status), ("cancelled", 2, "done"))
        self.assertEqual(len(markers(self.h.fake, 21, "release")), 1)
        self.assertTrue(any(e["event"] == "duplicate-marker-detected" and e["detail"]["op"] == "claim" for e in self.h.store.read_journal()))
        self.assertEqual(other_run(self.h)._active_foreign_claims(21, S), [])

    def test_done_claim_in_a_split_state_with_changed_revisions_is_cancelled_with_its_release(self):
        """Legacy split state (claim done, phase claim-incomplete) whose revisions changed:
        reconciliation does not reserve stale work; the landed claim is released."""
        self.h.reserve()
        state = self.h.store.load_story(S)
        state.phase = "claim-incomplete"
        self.h.store.save_story(state)
        self.h.fake.set_status_externally(21, "Blocked")
        state = fresh(self.h).resume(S, ok_worktree)
        self.assertEqual((state.phase, state.intent("claim").status, state.intent("release").status), ("cancelled", "done", "done"))
        self.assertEqual((state.authorizations[0]["status"], state.authorizations[0]["resolution"]), ("not-launched", "structural"))  # reserve never returned: no launch could follow
        self.assertEqual((len(markers(self.h.fake, 21, "claim")), len(markers(self.h.fake, 21, "release"))), (1, 1))
        self.assertEqual(self.h.store.story_counts()["delegated_tasks"], 1)
        self.assertEqual(other_run(self.h)._active_foreign_claims(21, S), [])


class F2ReconciliationNeverAdvancesCancelledWork(unittest.TestCase):
    """F2: a completed advancing intent whose transition did not persist is reconciled only
    behind the guards of a fresh attempt; a cancelled run advances nothing, the historical
    effect stays recorded and cancel-run finishes the story."""

    def setUp(self):
        self.h = Harness(small_backlog())

    def tearDown(self):
        self.h.close()

    def split_done_proposal(self) -> str:
        """Proposal comment posted, intent marked done, phase still review-approved (crash before the transition)."""
        op = pending_proposal(self.h)
        state = self.h.store.load_story(S)
        posted = self.h.fake.post_comment(21, state.intent(op).body)
        state.intent(op).status, state.intent(op).comment_id = "done", posted.comment_id
        self.h.store.save_story(state)
        return op

    def cancel_run_on_disk(self, reason: str = "crash before story cleanup") -> None:
        run = self.h.store.load_run()
        run.cancelled, run.stop_reason = True, reason
        self.h.store.save_run(run)

    def test_done_proposal_in_a_cancelled_run_is_not_reconciled_to_proposed(self):
        op = self.split_done_proposal()
        self.cancel_run_on_disk()
        self.h.fake.calls = []
        state = fresh(self.h).resume(S, ok_worktree)
        self.assertEqual((state.phase, state.intent(op).status), ("review-approved", "done"))  # history kept, phase not advanced
        self.assertTrue(self.h.store.load_run().cancelled)
        self.assertNotIn("post_comment", self.h.fake.calls)
        withheld = [e for e in self.h.store.read_journal() if e["event"] == "reconciliation-withheld"]
        self.assertEqual((withheld[-1]["detail"]["op"], withheld[-1]["detail"]["reason"]), (op, "run is cancelled"))
        with self.assertRaises(BudgetExhausted) as ctx:
            fresh(self.h).propose_evidence(S, self.h.sha, 7, [], "s")
        self.assertEqual(ctx.exception.code, "run-cancelled")
        result = fresh(self.h).cancel_run("finish")
        self.assertEqual([s["phase"] for s in result["cancelled"]], ["cancelled"])
        self.assertEqual((len(markers(self.h.fake, 21, "proposal")), len(markers(self.h.fake, 21, "release"))), (1, 1))  # the landed proposal is history; the release says no completion is implied
        self.assertEqual(fresh(self.h).resume(S, ok_worktree).phase, "cancelled")

    def test_done_proposal_without_current_approval_or_ownership_is_withheld(self):
        for mutate in (lambda s: setattr(s, "approved_sha", None), lambda s: setattr(s, "approved_sha", "other"), lambda s: setattr(s, "head_sha", "other"),
                       lambda s: setattr(s, "phase", "changes-requested"),
                       lambda s: setattr(s, "active_task", {"taskId": "task-review-9", "role": "reviewer", "authorization": "x", "bound_at": "t"})):
            h = Harness(small_backlog())
            try:
                self.h.close()
                self.h = h
                op = self.split_done_proposal()
                state = h.store.load_story(S)
                mutate(state)
                before = state.phase
                h.store.save_story(state)
                h.fake.calls = []
                try:
                    fresh(h).resume(S, ok_worktree)
                except Refused:
                    pass
                state = h.store.load_story(S)
                self.assertEqual((state.phase, state.intent(op).status), (before, "done"))
                self.assertNotIn("post_comment", h.fake.calls)
                self.assertTrue(any(e["event"] == "reconciliation-withheld" and e["detail"]["op"] == op for e in h.store.read_journal()))
            finally:
                pass

    def test_done_proposal_with_current_approval_in_a_live_run_is_still_reconciled(self):
        op = self.split_done_proposal()
        self.h.fake.calls = []
        state = fresh(self.h).resume(S, ok_worktree)
        self.assertEqual((state.phase, state.intent(op).status), ("proposed", "done"))
        self.assertNotIn("post_comment", self.h.fake.calls)
        self.assertEqual(len(markers(self.h.fake, 21, "proposal")), 1)

    def test_done_claim_in_a_cancelled_run_is_not_reconciled_to_reserved(self):
        self.h.reserve()
        state = self.h.store.load_story(S)
        state.phase = "claim-incomplete"
        self.h.store.save_story(state)
        self.cancel_run_on_disk()
        self.h.fake.calls = []
        state = fresh(self.h).resume(S, ok_worktree)
        self.assertEqual((state.phase, state.intent("claim").status), ("claim-incomplete", "done"))
        self.assertNotIn("post_comment", self.h.fake.calls)
        with self.assertRaises(Refused) as ctx:  # reserve never returned, so no launch could follow it: nothing binds to an incomplete claim
            fresh(self.h).bind_receipt(S, IMPLEMENTER, str(self.h.worktree), "t3/om-01-02", ok_worktree)
        self.assertEqual(ctx.exception.detail["phase"], "claim-incomplete")
        result = fresh(self.h).cancel_run("finish")
        self.assertEqual([s["phase"] for s in result["cancelled"]], ["cancelled"])
        state = self.h.store.load_story(S)
        self.assertEqual((state.phase, state.intent("claim").status, state.authorizations[0]["status"]), ("cancelled", "done", "not-launched"))
        self.assertEqual((len(markers(self.h.fake, 21, "claim")), len(markers(self.h.fake, 21, "release"))), (1, 1))
        self.assertEqual(self.h.store.story_counts()["delegated_tasks"], 1)

    def test_wall_clock_expiry_abandons_pending_advancing_replays_but_still_replays_cleanups(self):
        op = pending_proposal(self.h)
        c = fresh(self.h)
        c.now = lambda: LATER
        state = c.resume(S, ok_worktree)
        self.assertEqual((state.phase, state.intent(op).status), ("review-approved", "abandoned"))
        self.assertEqual(markers(self.h.fake, 21, "proposal"), [])
        self.assertTrue(any(e["event"] == "resume-advancing-abandoned" and e["detail"]["reason"] == "run wall clock budget exceeded" for e in self.h.store.read_journal()))
        self.h.fake.fail_once["post_comment"] = Outage("503")
        self.assertEqual(c.cancel(S, "budget").intent("release").status, "pending")  # cleanup is allowed after expiry …
        c2 = fresh(self.h)
        c2.now = lambda: LATER
        self.assertEqual(c2.resume(S, ok_worktree).intent("release").status, "done")  # … and replayed on restart
        self.assertEqual(len(markers(self.h.fake, 21, "release")), 1)


class F3TaskIdsAreFreshRunWide(unittest.TestCase):
    """F3: a T3 task id binds exactly once per run, whatever story or role presents it, and
    the record survives cancellation, blocking and restarts."""

    def two_stories(self) -> Harness:
        return Harness(small_backlog(), allow='["OM-01.02", "OM-01.04"]', max_stories_per_run="2")

    def test_task_id_of_a_cancelled_story_cannot_be_rebound_in_another_story(self):
        h = self.two_stories()
        try:
            h.claim()  # task-impl-1
            h.coordinator.cancel(S, "done with the worker", h.terminal())
            self.assertEqual(h.store.bound_task_ids(), {"task-impl-1"})
            h.reserve("OM-01.04")
            with self.assertRaises(ReceiptInvalid) as ctx:
                fresh(h).bind_receipt("OM-01.04", IMPLEMENTER, str(h.worktree), "t3/om-01-02", ok_worktree)
            self.assertEqual(ctx.exception.detail["task_id"], "task-impl-1")
            state = h.store.load_story("OM-01.04")
            self.assertEqual((state.phase, state.active_task, state.pending_authorization()["status"]), ("reserved", None, "pending"))
            self.assertEqual(h.store.story_counts()["delegated_tasks"], 2)
            state = fresh(h).bind_receipt("OM-01.04", receipt(IMPLEMENTER, "task-impl-2"), str(h.worktree), "t3/om-01-02", ok_worktree)
            self.assertEqual((state.phase, state.active_task["taskId"]), ("claimed", "task-impl-2"))
            self.assertEqual(h.store.bound_task_ids(), {"task-impl-1", "task-impl-2"})
        finally:
            h.close()

    def test_cross_role_reuse_is_refused_in_both_directions(self):
        h = self.two_stories()
        try:
            h.to_review_approved()  # task-impl-1 (implementer), task-review-1 (reviewer), both terminal
            h.coordinator.cancel(S, "stop")
            self.assertEqual(h.store.bound_task_ids(), {"task-impl-1", "task-review-1"})
            h.reserve("OM-01.04")
            with self.assertRaises(ReceiptInvalid):  # a reviewer's id presented as the implementer of another story
                h.coordinator.bind_receipt("OM-01.04", receipt(IMPLEMENTER, "task-review-1"), str(h.worktree), "t3/om-01-02", ok_worktree)
            h.coordinator.bind_receipt("OM-01.04", receipt(IMPLEMENTER, "task-impl-2"), str(h.worktree), "t3/om-01-02", ok_worktree)
            h.coordinator.record_head("OM-01.04", h.sha, h.terminal("OM-01.04"))
            h.coordinator.run_checks("OM-01.04", h.sha, str(h.worktree), passing_runner)
            h.coordinator.authorize_review("OM-01.04", h.sha)
            for reused in ("task-impl-1", "task-review-1", "task-impl-2"):  # another story's implementer, its reviewer, this story's own implementer
                with self.assertRaises(ReceiptInvalid) as ctx:
                    fresh(h).bind_receipt("OM-01.04", receipt(REVIEWER, reused), worktree_check=ok_worktree)
                self.assertEqual(ctx.exception.detail["task_id"], reused)
            self.assertEqual(h.store.load_story("OM-01.04").phase, "review-authorized")
            self.assertEqual(h.coordinator.bind_receipt("OM-01.04", receipt(REVIEWER, "task-review-2"), worktree_check=ok_worktree).phase, "review-requested")
        finally:
            h.close()

    def test_history_survives_blocked_stories_terminal_evidence_and_restart(self):
        h = self.two_stories()
        try:
            h.claim()
            h.checks(runner=failing_runner)
            h.repair(receipt_=receipt(IMPLEMENTER, "task-impl-2"))
            h.coordinator.block(S, "owner decision", h.terminal())
            state = h.store.load_story(S)
            self.assertEqual((state.phase, state.active_task, [r["taskId"] for r in state.implementer_receipts]), ("blocked", None, ["task-impl-1", "task-impl-2"]))
            self.assertEqual(Store(h.state_dir, "run-1").bound_task_ids(), {"task-impl-1", "task-impl-2"})
            h.reserve("OM-01.04")
            for reused in ("task-impl-1", "task-impl-2"):
                with self.assertRaises(ReceiptInvalid):
                    fresh(h).bind_receipt("OM-01.04", receipt(IMPLEMENTER, reused), str(h.worktree), "t3/om-01-02", ok_worktree)
            self.assertEqual(h.store.load_story("OM-01.04").phase, "reserved")
        finally:
            h.close()

    def test_same_story_reuse_is_still_refused(self):
        h = Harness(small_backlog())
        try:
            h.claim()
            h.checks()
            h.coordinator.authorize_review(S, h.sha)
            with self.assertRaises(ReceiptInvalid):
                h.coordinator.bind_receipt(S, {**REVIEWER, "taskId": "task-impl-1"}, worktree_check=ok_worktree)
        finally:
            h.close()


class F4ExpiredAuthorizationsBindForCleanupOnly(unittest.TestCase):
    """F4: the wall-clock budget is a local expiry. After it no authorization is returned or
    issued, no advancing operation runs, and a receipt for an earlier authorization binds for
    cleanup only: the slot stays spent, the id stays bound, the task stays owned until its
    terminal evidence, the phase does not advance. It is not a bound on the child's lifetime."""

    def setUp(self):
        self.h = Harness(small_backlog())

    def tearDown(self):
        self.h.close()

    def expired(self) -> Coordinator:
        c = fresh(self.h)
        c.now = lambda: LATER
        return c

    def test_pending_authorization_is_not_returned_after_the_deadline_and_stays_spent(self):
        self.h.claim()
        self.h.checks()
        issued = self.h.coordinator.authorize_review(S, self.h.sha).pending_authorization()
        with self.assertRaises(BudgetExhausted) as ctx:
            self.expired().authorize_review(S, self.h.sha)
        self.assertEqual(ctx.exception.code, "wall-clock-exceeded")
        state = self.h.store.load_story(S)
        self.assertEqual((state.phase, state.pending_authorization()["id"], state.pending_authorization()["status"]), ("review-authorized", issued["id"], "pending"))
        self.assertEqual(self.h.store.story_counts()["delegated_tasks"], 2)  # not refunded, not re-issued
        h2 = Harness(small_backlog(), allow='["OM-01.02", "OM-01.04"]', max_stories_per_run="2")
        try:
            h2.coordinator.now = lambda: LATER
            for op in (lambda: h2.reserve("OM-01.04"), lambda: h2.coordinator.authorize_repair(S)):
                with self.assertRaises(BudgetExhausted) as ctx:
                    op()
                self.assertEqual(ctx.exception.code, "wall-clock-exceeded")
            self.assertEqual(h2.store.list_stories(), [])
        finally:
            h2.close()

    def test_expired_bind_keeps_accounting_and_ownership_but_authorizes_no_work(self):
        self.h.claim()
        self.h.checks()
        self.h.coordinator.authorize_review(S, self.h.sha)
        c = self.expired()
        with self.assertRaises(BudgetExhausted) as ctx:
            c.bind_receipt(S, REVIEWER, worktree_check=ok_worktree)
        self.assertEqual((ctx.exception.code, ctx.exception.detail["bound_for_cleanup"], ctx.exception.detail["task_id"]), ("wall-clock-exceeded", True, "task-review-1"))
        state = self.h.store.load_story(S)
        self.assertEqual((state.phase, state.active_task["taskId"], state.active_task["role"], state.active_task["cleanup_only"]), ("review-authorized", "task-review-1", "reviewer", "wall-clock-exceeded"))
        self.assertEqual((state.authorizations[-1]["status"], state.authorizations[-1]["task_id"], state.pending_authorization()), ("consumed", "task-review-1", None))
        self.assertEqual(self.h.store.story_counts()["delegated_tasks"], 2)
        self.assertIn("task-review-1", self.h.store.bound_task_ids())
        for op in (lambda: c.record_review(S, self.h.sha, "approved", "r", {"taskId": "task-review-1", "status": "result_available"}),
                   lambda: c.authorize_review(S, self.h.sha), lambda: c.propose_evidence(S, self.h.sha, 7, [], "s")):
            with self.assertRaises(BudgetExhausted) as ctx:
                op()
            self.assertEqual(ctx.exception.code, "wall-clock-exceeded")
        with self.assertRaises(BudgetExhausted) as ctx:
            c.bind_receipt(S, receipt(REVIEWER, "task-review-2"), worktree_check=ok_worktree)  # nothing pending any more
        self.assertEqual(ctx.exception.code, "wall-clock-exceeded")
        self.assertEqual(self.h.store.load_story(S).phase, "review-authorized")
        c2 = self.expired()  # restart: the launched worker is still owned
        for evidence in (None, {"taskId": "task-impl-1", "status": "result_available"}, {"taskId": "task-review-1", "status": "cancel_requested"}):
            with self.assertRaises(Refused) as ctx:
                c2.cancel(S, "budget", evidence)
            self.assertEqual(ctx.exception.code, "worker-not-terminal")
        self.assertEqual(markers(self.h.fake, 21, "release"), [])
        state = c2.cancel(S, "budget", {"taskId": "task-review-1", "status": "cancelled"})
        self.assertEqual((state.phase, state.active_task, state.task_history[-1]["taskId"]), ("cancelled", None, "task-review-1"))
        self.assertEqual(len(markers(self.h.fake, 21, "release")), 1)
        self.assertEqual(self.h.store.story_counts()["delegated_tasks"], 2)

    def test_record_task_terminal_releases_a_cleanup_only_task_and_nothing_can_be_reissued(self):
        self.h.claim()
        self.h.checks()
        self.h.coordinator.authorize_review(S, self.h.sha)
        c = self.expired()
        with self.assertRaises(BudgetExhausted):
            c.bind_receipt(S, REVIEWER, worktree_check=ok_worktree)
        self.assertEqual(c.record_task_terminal(S, {"taskId": "task-review-1", "status": "result_available"}).active_task, None)
        with self.assertRaises(BudgetExhausted) as ctx:
            c.authorize_review(S, self.h.sha)
        self.assertEqual(ctx.exception.code, "wall-clock-exceeded")
        self.assertEqual(self.h.store.load_story(S).pending_authorization(), None)
        self.assertEqual(c.cancel(S, "budget").phase, "cancelled")

    def test_expired_implementation_bind_records_the_worktree_and_keeps_the_implementer_owned(self):
        self.h.reserve()
        c = self.expired()
        with self.assertRaises(BudgetExhausted) as ctx:
            c.bind_receipt(S, IMPLEMENTER, str(self.h.worktree), "t3/om-01-02", ok_worktree)
        self.assertEqual((ctx.exception.code, ctx.exception.detail["role"]), ("wall-clock-exceeded", "implementer"))
        state = self.h.store.load_story(S)
        self.assertEqual((state.phase, state.active_task["taskId"], state.claim["worktree_path"]), ("reserved", "task-impl-1", str(self.h.worktree)))
        for op in (lambda: c.record_head(S, self.h.sha, {"taskId": "task-impl-1", "status": "result_available"}), lambda: c.run_checks(S, self.h.sha, str(self.h.worktree), passing_runner)):
            with self.assertRaises(BudgetExhausted) as ctx:
                op()
            self.assertEqual(ctx.exception.code, "wall-clock-exceeded")
        with self.assertRaises(Refused) as ctx:
            self.expired().resume(S, lambda p, b: (False, "wrong worktree"))  # identity still guards recovery
        self.assertEqual(ctx.exception.code, "worktree-mismatch")
        self.assertEqual(self.expired().resume(S, ok_worktree).active_task["taskId"], "task-impl-1")
        state = self.expired().cancel(S, "budget", {"taskId": "task-impl-1", "status": "cancelled"})
        self.assertEqual((state.phase, len(markers(self.h.fake, 21, "release"))), ("cancelled", 1))

    def test_deadline_passing_mid_story_refuses_advancing_operations_but_allows_cleanup(self):
        self.h.claim()
        c = self.expired()
        for op in (lambda: c.record_head(S, self.h.sha, self.h.terminal()), lambda: c.authorize_review(S, self.h.sha)):
            with self.assertRaises(BudgetExhausted) as ctx:
                op()
            self.assertEqual(ctx.exception.code, "wall-clock-exceeded")
        self.assertEqual(self.h.store.load_story(S).active_task["taskId"], "task-impl-1")
        self.assertEqual(c.status()["budgets"]["delegated_tasks"], 1)
        self.assertEqual(c.record_task_terminal(S, self.h.terminal()).active_task, None)
        result = c.cancel_run("wall clock")
        self.assertEqual(([s["phase"] for s in result["cancelled"]], result["awaiting_worker_termination"]), (["cancelled"], []))
        self.assertEqual(len(markers(self.h.fake, 21, "release")), 1)

    def test_run_cancelled_between_authorization_and_bind_binds_for_cleanup_only(self):
        self.h.reserve()
        run = self.h.store.load_run()
        run.cancelled, run.stop_reason = True, "crash after save_run"
        self.h.store.save_run(run)
        with self.assertRaises(BudgetExhausted) as ctx:
            fresh(self.h).bind_receipt(S, IMPLEMENTER, str(self.h.worktree), "t3/om-01-02", ok_worktree)
        self.assertEqual((ctx.exception.code, ctx.exception.detail["bound_for_cleanup"]), ("run-cancelled", True))
        state = self.h.store.load_story(S)
        self.assertEqual((state.phase, state.active_task["taskId"], state.active_task["cleanup_only"]), ("reserved", "task-impl-1", "run-cancelled"))
        result = fresh(self.h).cancel_run("finish")
        self.assertEqual(result["awaiting_worker_termination"], [{"story": S, "task_id": "task-impl-1", "role": "implementer", "authorization": "run-1:OM-01.02:1", "code": "worker-not-terminal"}])
        self.assertEqual(fresh(self.h).cancel(S, "finish", {"taskId": "task-impl-1", "status": "cancelled"}).phase, "cancelled")
        self.assertEqual(self.h.store.story_counts()["delegated_tasks"], 1)
        raw = json.loads(self.h.store.story_path(S).read_text())
        self.assertEqual(raw["authorizations"][0]["cleanup_only"], "run-cancelled")


if __name__ == "__main__":
    unittest.main()
