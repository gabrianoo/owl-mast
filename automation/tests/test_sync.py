"""Synchronization faults: stale revisions, duplicates, retries, partial writes, crash/restart,
denial, outage, locking and run binding. Every fault must leave the story without a false
advance and never turn a conflict into success."""

import unittest
from dataclasses import replace

from automation.tests.fake_transport import CrashAfterEffect, FakeTransport, small_backlog
from automation.tests.support import IMPLEMENTER, Harness, ok_worktree
from automation.unattended.backlog import take_snapshot
from automation.unattended.coordinator import Coordinator
from automation.unattended.errors import Conflict, Outage, PermissionDenied, Refused, StaleRevision
from automation.unattended.github import Comment, PullRequestRecord, render_marker
from automation.unattended.state import Store, StoreBusy


def markers(fake: FakeTransport, number: int, kind: str):
    return [c for c in fake.comments[number] if c.marker and c.marker["kind"] == kind]


class StaleRevisionTests(unittest.TestCase):
    def setUp(self):
        self.h = Harness(small_backlog())

    def tearDown(self):
        self.h.close()

    def test_project_item_edited_after_snapshot_is_stale(self):
        self.h.fake.set_status_externally(21, "Ready")  # same value, newer updatedAt
        with self.assertRaises(StaleRevision) as ctx:
            self.h.claim()
        self.assertIn("OM-01.02", ctx.exception.detail["changed"])
        self.assertIsNone(self.h.store.load_story("OM-01.02"))
        self.assertEqual(self.h.fake.comments[21], [])

    def test_owner_moved_status_after_snapshot_is_stale(self):
        self.h.fake.set_status_externally(21, "Blocked")
        with self.assertRaises(StaleRevision):
            self.h.claim()
        self.assertEqual(self.h.fake.comments[21], [])

    def test_story_closed_and_dependency_reopened_after_snapshot(self):
        """Reviewer probe B1/E1/V2: issue changes outside the Project item must refuse."""
        self.h.fake.issues[20] = replace(self.h.fake.issues[20], state="OPEN", state_reason=None, closed_at=None, updated_at="later")
        self.h.fake.issues[21] = replace(self.h.fake.issues[21], state="CLOSED", state_reason="NOT_PLANNED", updated_at="later")
        with self.assertRaises(StaleRevision) as ctx:
            self.h.claim()
        self.assertEqual(sorted(ctx.exception.detail["changed"]), ["OM-01.01", "OM-01.02"])
        self.assertIsNone(self.h.store.load_story("OM-01.02"))

    def test_dependency_body_edit_after_snapshot_is_stale(self):
        self.h.fake.issues[20] = replace(self.h.fake.issues[20], body=self.h.fake.issues[20].body + "\nedited\n")
        with self.assertRaises(StaleRevision):
            self.h.claim()

    def test_parent_epic_edit_after_snapshot_is_stale(self):
        self.h.fake.issues[1] = replace(self.h.fake.issues[1], updated_at="later")
        with self.assertRaises(StaleRevision):
            self.h.claim()

    def test_proposal_refuses_changed_revisions_and_rebase_is_explicit(self):
        self.h.to_review_approved()
        self.h.fake.pull_requests[7] = PullRequestRecord(7, "OPEN", self.h.sha, False, (), "SUCCESS")
        self.h.fake.set_status_externally(21, "In progress")  # owner moved the board
        with self.assertRaises(StaleRevision):
            self.h.coordinator.propose_evidence("OM-01.02", self.h.sha, 7, [], "s")
        self.assertEqual(self.h.store.load_story("OM-01.02").phase, "review-approved")
        self.assertEqual(markers(self.h.fake, 21, "proposal"), [])
        state = self.h.coordinator.rebase_revisions("OM-01.02", "owner moved Status to In progress; verified")
        self.assertEqual(state.revisions["OM-01.02"]["status"], "In progress")
        self.assertTrue(any(e["event"] == "revisions-rebased" for e in self.h.store.read_journal()))
        self.assertEqual(self.h.coordinator.propose_evidence("OM-01.02", self.h.sha, 7, [], "s").phase, "proposed")

    def test_resume_refuses_changed_revisions_instead_of_replacing_them(self):
        """Reviewer finding E5: resume never adopts a newer revision silently."""
        self.h.claim()
        self.h.fake.set_status_externally(21, "In progress")
        with self.assertRaises(StaleRevision):
            self.h.coordinator.resume("OM-01.02", ok_worktree)
        state = self.h.store.load_story("OM-01.02")
        self.assertEqual(state.phase, "claimed")
        self.assertEqual(state.revisions["OM-01.02"]["status"], "Ready")

    def test_foreign_active_claim_is_refused(self):
        # another coordinator on another machine (its own state directory) holds the claim marker
        other = Coordinator(self.h.fake, self.h.policy, Store(self.h.state_dir.parent / "elsewhere", "run-other"), live=True)
        other.reserve("OM-01.02", self.h.snapshot, "c5d9d2e")
        self.h.snapshot = take_snapshot(self.h.fake, "gabrianoo/owl-mast", "now")
        with self.assertRaises(Refused) as ctx:
            self.h.claim()
        self.assertIn("claimed by another run", str(ctx.exception))

    def test_another_run_in_the_same_state_dir_with_an_active_story_blocks_admission(self):
        """PR #107 review finding 5: budgets are per run id, so a second run id under the same
        state directory admits nothing while an earlier run still owns a story."""
        self.h.close()
        self.h = Harness(small_backlog(), allow='["OM-01.02", "OM-01.04"]')
        other = Coordinator(self.h.fake, self.h.policy, Store(self.h.state_dir, "run-other"), live=True)
        other.reserve("OM-01.02", self.h.snapshot, "c5d9d2e")
        with self.assertRaises(Refused) as ctx:
            self.h.coordinator.reserve("OM-01.04", self.h.snapshot, "c5d9d2e")
        self.assertEqual(ctx.exception.code, "run-concurrent")
        self.assertEqual(ctx.exception.detail["runs"], {"run-other": ["OM-01.02 (reserved)"]})
        self.assertEqual(self.h.coordinator.status()["other_runs_with_active_stories"], {"run-other": ["OM-01.02 (reserved)"]})
        other.cancel("OM-01.02", "stop", no_launch={"authorization": "run-other:OM-01.02:1", "reason": "never launched"})
        self.assertEqual(self.h.coordinator.reserve("OM-01.04", self.h.snapshot, "c5d9d2e").phase, "reserved")

    def test_owner_status_is_never_written(self):
        self.h.to_review_approved()
        self.h.fake.pull_requests[7] = PullRequestRecord(7, "OPEN", self.h.sha, False, (), "SUCCESS")
        self.h.coordinator.propose_evidence("OM-01.02", self.h.sha, 7, [], "s")
        self.assertEqual(self.h.fake.item_for(21).status, "Ready")  # untouched through the whole cycle
        self.assertNotIn("set_project_status", self.h.fake.calls)


class IdempotencyAndRetryTests(unittest.TestCase):
    def setUp(self):
        self.h = Harness(small_backlog())

    def tearDown(self):
        self.h.close()

    def test_duplicate_claim_event_posts_one_comment(self):
        self.h.claim()
        with self.assertRaises(Refused):
            self.h.reserve()
        self.assertEqual(len(markers(self.h.fake, 21, "claim")), 1)

    def test_transient_outage_on_post_then_retry_has_single_effect(self):
        self.h.fake.fail_once["post_comment"] = Outage("HTTP 502")
        with self.assertRaises(Outage):
            self.h.claim()
        state = self.h.store.load_story("OM-01.02")
        self.assertEqual(state.phase, "claim-incomplete")
        self.h.coordinator.resume("OM-01.02", ok_worktree)
        self.assertEqual(self.h.store.load_story("OM-01.02").phase, "reserved")
        self.assertEqual(len(markers(self.h.fake, 21, "claim")), 1)
        self.assertIn("Unattended reservation by run", markers(self.h.fake, 21, "claim")[0].body)  # persisted body, not a synthetic one

    def test_partial_write_crash_after_comment_is_adopted_on_resume(self):
        self.h.fake.crash_after_post = True
        with self.assertRaises(CrashAfterEffect):
            self.h.claim()
        state = self.h.store.load_story("OM-01.02")
        self.assertEqual(state.pending_intents()[0].op, "claim")
        fresh = Coordinator(self.h.fake, self.h.policy, Store(self.h.state_dir, "run-1"), live=True)
        fresh.resume("OM-01.02", ok_worktree)
        state = self.h.store.load_story("OM-01.02")
        self.assertEqual(state.pending_intents(), [])
        self.assertEqual(state.phase, "reserved")
        self.assertEqual(len(markers(self.h.fake, 21, "claim")), 1)
        self.assertIn("comment-adopted", [e["event"] for e in self.h.store.read_journal()])

    def test_duplicate_marker_is_a_conflict_on_claim_and_stays_one_on_resume(self):
        """Reviewer probe B5/E4: recovery enforces the same exactly-one-marker rule."""
        marker = render_marker(kind="claim", op="claim", run="run-1", inst=self.h.store.load_run().instance, story="OM-01.02")
        self.h.fake.comments[21].append(Comment(1, marker + "\nfirst", "machine", "t"))  # the trusted author's own duplicates
        self.h.fake.comments[21].append(Comment(2, marker + "\nsecond", "machine", "t"))
        with self.assertRaises(Conflict):
            self.h.claim()
        self.assertEqual(self.h.store.load_story("OM-01.02").phase, "conflict")
        # conflict is terminal: resume replays no advancing intent (the claim is abandoned), posts nothing
        state = self.h.coordinator.resume("OM-01.02", ok_worktree)
        self.assertEqual((state.phase, [i.status for i in state.intents if i.kind == "claim"]), ("conflict", ["abandoned"]))
        self.assertEqual(len(markers(self.h.fake, 21, "claim")), 2)
        with self.assertRaises(Refused):
            self.h.coordinator.record_head("OM-01.02", "s1")

    def test_proposal_retry_reuses_the_same_operation_identity(self):
        """Reviewer probe B7c/E6/V5: a failed proposal retried posts no second comment."""
        self.h.to_review_approved()
        self.h.fake.pull_requests[7] = PullRequestRecord(7, "OPEN", self.h.sha, False, (), "SUCCESS")
        self.h.fake.crash_after_post = True
        with self.assertRaises(CrashAfterEffect):
            self.h.coordinator.propose_evidence("OM-01.02", self.h.sha, 7, [], "s")
        self.assertEqual(self.h.store.load_story("OM-01.02").phase, "review-approved")
        state = self.h.coordinator.propose_evidence("OM-01.02", self.h.sha, 7, [], "s")
        self.assertEqual(state.phase, "proposed")
        proposals = markers(self.h.fake, 21, "proposal")
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0].marker["op"], f"proposal-{self.h.sha[:12]}-pr7")

    def test_stale_proposal_replay_is_validated_before_posting_and_keeps_its_body(self):
        """Round-1 findings R1-B2/E2/V4: a pending proposal is re-validated (revisions, worktree,
        PR head/reviews/checks) before any post, and the replay carries the original payload."""
        self.h.to_review_approved()
        self.h.fake.pull_requests[7] = PullRequestRecord(7, "OPEN", self.h.sha, False, (), "SUCCESS")
        self.h.fake.fail_once["post_comment"] = Outage("503")
        with self.assertRaises(Outage):
            self.h.coordinator.propose_evidence("OM-01.02", self.h.sha, 7, ["OM-01.02-T1"], "original evidence")
        pending = self.h.store.load_story("OM-01.02").pending_intents()
        self.assertEqual([i.kind for i in pending], ["proposal"])
        self.assertIn("original evidence", pending[0].body)
        # owner edit + PR regression after the failure
        self.h.fake.set_status_externally(21, "Blocked")
        self.h.fake.pull_requests[7] = PullRequestRecord(7, "OPEN", "new-head", False, (), "FAILURE")
        self.h.fake.calls = []
        with self.assertRaises(StaleRevision):
            self.h.coordinator.resume("OM-01.02", ok_worktree)
        self.assertEqual(markers(self.h.fake, 21, "proposal"), [])  # nothing posted
        self.assertNotIn("post_comment", self.h.fake.calls)
        # revisions accepted explicitly, PR still regressed: still nothing posted, PR is read
        self.h.coordinator.rebase_revisions("OM-01.02", "verified")
        self.h.fake.calls = []
        with self.assertRaises(Refused):
            self.h.coordinator.resume("OM-01.02", ok_worktree)
        self.assertIn("get_pull_request", self.h.fake.calls)
        self.assertEqual(markers(self.h.fake, 21, "proposal"), [])
        # PR healthy again: the replay posts exactly the persisted body
        self.h.fake.pull_requests[7] = PullRequestRecord(7, "OPEN", self.h.sha, False, (), "SUCCESS")
        state = self.h.coordinator.resume("OM-01.02", ok_worktree)
        self.assertEqual(state.phase, "proposed")
        posted = markers(self.h.fake, 21, "proposal")
        self.assertEqual(len(posted), 1)
        self.assertIn("original evidence", posted[0].body)
        self.assertIn("- [ ] OM-01.02-T1", posted[0].body)

    def test_proposal_replay_abandoned_on_github_review_regression(self):
        self.h.to_review_approved()
        self.h.fake.pull_requests[7] = PullRequestRecord(7, "OPEN", self.h.sha, False, (), "SUCCESS")
        self.h.fake.fail_once["post_comment"] = Outage("503")
        with self.assertRaises(Outage):
            self.h.coordinator.propose_evidence("OM-01.02", self.h.sha, 7, [], "s")
        self.h.fake.pull_requests[7] = PullRequestRecord(7, "OPEN", self.h.sha, False, ({"state": "CHANGES_REQUESTED", "commit": self.h.sha, "author": "A", "submitted_at": "1"},), "SUCCESS")
        with self.assertRaises(Refused):
            self.h.coordinator.resume("OM-01.02", ok_worktree)
        state = self.h.store.load_story("OM-01.02")
        self.assertEqual(state.phase, "changes-requested")
        self.assertEqual([i.status for i in state.intents if i.kind == "proposal"], ["abandoned"])
        self.assertEqual(markers(self.h.fake, 21, "proposal"), [])

    def test_cancel_release_failure_is_replayed_on_resume(self):
        """Reviewer probe B7a/E8: terminal cleanup is never stranded."""
        self.h.claim()
        self.h.fake.fail_once["post_comment"] = Outage("503")
        state = self.h.coordinator.cancel("OM-01.02", "stop", self.h.terminal())
        self.assertEqual(state.phase, "cancelled")
        self.assertEqual([i.op for i in state.pending_intents()], ["release"])
        state = self.h.coordinator.resume("OM-01.02", ok_worktree)
        self.assertEqual(state.phase, "cancelled")
        self.assertEqual(state.pending_intents(), [])
        self.assertEqual(len(markers(self.h.fake, 21, "release")), 1)

    def test_crash_after_terminal_save_before_post_is_recovered(self):
        """Round-1 finding R1-B4: the terminal phase and its cleanup intent persist together."""
        self.h.claim()
        original = self.h.store.journal

        def crash(story, event, detail=None):
            if event == "cancelled":
                raise RuntimeError("synthetic process crash")
            return original(story, event, detail)

        self.h.store.journal = crash
        with self.assertRaises(RuntimeError):
            self.h.coordinator.cancel("OM-01.02", "stop", self.h.terminal())
        self.h.store.journal = original
        state = self.h.store.load_story("OM-01.02")
        self.assertEqual((state.phase, [i.op for i in state.pending_intents()]), ("cancelled", ["release"]))
        fresh = Coordinator(self.h.fake, self.h.policy, Store(self.h.state_dir, "run-1"), live=True)
        state = fresh.resume("OM-01.02", ok_worktree)
        self.assertEqual(state.pending_intents(), [])
        self.assertEqual(len(markers(self.h.fake, 21, "release")), 1)


class ConcurrencyAndBindingTests(unittest.TestCase):
    def setUp(self):
        self.h = Harness(small_backlog(), allow='["OM-01.02", "OM-01.04"]', max_stories_per_run="2")

    def tearDown(self):
        self.h.close()

    def test_interleaved_claim_from_another_coordinator_is_refused_by_the_lock(self):
        """Reviewer probe B2/#8: a second coordinator entering during a claim cannot pass the budget."""
        c2 = Coordinator(self.h.fake, self.h.policy, self.h.store, live=True)
        original = self.h.coordinator._active_foreign_claims
        seen = {}

        def interleave(issue, story, context="admission"):
            try:
                c2.reserve("OM-01.04", self.h.snapshot, "base")
            except StoreBusy as exc:
                seen["busy"] = str(exc)
            return original(issue, story, context)

        self.h.coordinator._active_foreign_claims = interleave
        self.h.reserve()
        self.assertIn("busy", seen)
        self.assertEqual([(s.story, s.phase) for s in self.h.store.list_stories()], [("OM-01.02", "reserved")])
        self.assertEqual(self.h.store.load_run().stories_claimed, 1)

    def test_no_reclaim_in_the_same_run_and_second_run_owns_after_release(self):
        """Round-1 findings R1-B3/E3: cancel then reclaim defeated cross-run exclusion."""
        self.h = Harness(small_backlog(), max_stories_per_run="3")
        self.h.claim()
        self.h.coordinator.cancel("OM-01.02", "stop", self.h.terminal())
        with self.assertRaises(Refused) as ctx:
            self.h.reserve()
        self.assertEqual(ctx.exception.code, "no-reclaim")
        c2 = Coordinator(self.h.fake, self.h.policy, Store(self.h.state_dir, "run-2"), live=True)
        snap = take_snapshot(self.h.fake, "gabrianoo/owl-mast", "now")
        self.assertEqual(c2.reserve("OM-01.02", snap, "base").phase, "reserved")
        self.assertEqual(c2._active_foreign_claims(21, "OM-01.02"), [])
        c3 = Coordinator(self.h.fake, self.h.policy, Store(self.h.state_dir.parent / "elsewhere", "run-3"), live=True)  # another machine: only the marker protects the story
        with self.assertRaises(Refused) as ctx:
            c3.reserve("OM-01.02", take_snapshot(self.h.fake, "gabrianoo/owl-mast", "now"), "base")
        self.assertIn("claimed by another run", str(ctx.exception))

    def test_lock_is_held_across_the_whole_operation_against_other_processes(self):
        import fcntl

        self.h.claim()
        with self.h.store.locked():
            fh = open(self.h.state_dir / ".lock", "a+")
            with self.assertRaises(OSError):
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fh.close()

    def test_run_is_bound_to_repository_and_policy(self):
        """Reviewer probe B6/E9: reopening the store with another repo/policy refuses."""
        from dataclasses import replace as dc_replace

        self.h.claim()
        other = dc_replace(self.h.policy, digest="different", repo="another-repo", allow=())
        with self.assertRaises(Refused) as ctx:
            Coordinator(self.h.fake, other, self.h.store, live=True)
        self.assertEqual(ctx.exception.code, "run-binding-mismatch")
        other_repo = dc_replace(self.h.policy, repo="another-repo")
        with self.assertRaises(Refused):
            Coordinator(self.h.fake, other_repo, self.h.store, live=True)


class DenialOutageAndLiveGateTests(unittest.TestCase):
    def setUp(self):
        self.h = Harness(small_backlog())

    def tearDown(self):
        self.h.close()

    def test_permission_denied_on_post_does_not_advance(self):
        self.h.fake.fail_always["post_comment"] = PermissionDenied("HTTP 403")
        with self.assertRaises(PermissionDenied):
            self.h.claim()
        self.assertEqual(self.h.store.load_story("OM-01.02").phase, "claim-incomplete")
        self.assertEqual(self.h.fake.comments[21], [])

    def test_outage_on_read_fails_closed_before_any_effect(self):
        self.h.fake.fail_always["list_comments"] = Outage("no such host")
        with self.assertRaises(Outage):
            self.h.claim()
        self.assertEqual(self.h.fake.comments[21], [])

    def test_outage_during_fresh_snapshot_refuses_admission(self):
        self.h.fake.fail_once["list_issues"] = Outage("HTTP 503")
        with self.assertRaises(Outage):
            self.h.claim()
        self.assertIsNone(self.h.store.load_story("OM-01.02"))

    def test_block_records_github_failure_but_stays_blocked_locally(self):
        self.h.claim()
        self.h.fake.fail_always["post_comment"] = Outage("HTTP 503")
        state = self.h.coordinator.block("OM-01.02", "checks cannot run", self.h.terminal())
        self.assertEqual(state.phase, "blocked")
        self.assertEqual(state.blocked["github_error"]["code"], "outage")
        self.assertEqual([i.op for i in state.pending_intents()], ["block"])

    def test_live_transport_refuses_product_admission_without_activation(self):
        self.h.fake.live = True
        self.h.fake.calls = []
        with self.assertRaises(Refused) as ctx:
            Coordinator(self.h.fake, self.h.policy, Store(self.h.state_dir, "run-live"), live=True)
        self.assertEqual(ctx.exception.code, "activation-required")
        self.assertEqual(self.h.fake.calls, [])
        self.assertIsNone(Store(self.h.state_dir, "run-live").load_run())

    def test_fixture_state_cannot_be_reused_with_a_live_transport(self):
        """Round-1 findings R1-B1/E1: recovery and every other operation refuse on live."""
        self.h.fake.fail_once["post_comment"] = Outage("503")
        with self.assertRaises(Outage):
            self.h.claim()
        self.h.fake.live = True
        with self.assertRaises(Refused) as ctx:
            Coordinator(self.h.fake, self.h.policy, Store(self.h.state_dir, "run-1"), live=True)
        self.assertEqual(ctx.exception.code, "environment-mismatch")
        # even a coordinator object built before the flag flipped refuses every operation
        self.h.coordinator.environment = "live"
        for op in (lambda: self.h.coordinator.resume("OM-01.02", ok_worktree), lambda: self.h.coordinator.record_head("OM-01.02", "s"),
                   lambda: self.h.coordinator.cancel("OM-01.02", "x"), lambda: self.h.coordinator.block("OM-01.02", "x"),
                   lambda: self.h.coordinator.rebase_revisions("OM-01.02", "x"), lambda: self.h.coordinator.cancel_run("x"),
                   lambda: self.h.coordinator.propose_evidence("OM-01.02", "s", 7, [], "s"), lambda: self.h.coordinator.authorize_repair("OM-01.02"),
                   lambda: self.h.coordinator.authorize_review("OM-01.02", "s"), lambda: self.h.coordinator.record_review("OM-01.02", "s", "approved", "r"),
                   lambda: self.h.coordinator.record_task_terminal("OM-01.02", {"taskId": "t", "runId": "t" + ":run:1", "status": "cancelled"}),
                   lambda: self.h.coordinator.run_checks("OM-01.02", "s", str(self.h.worktree)), lambda: self.h.coordinator.bind_receipt("OM-01.02", IMPLEMENTER, str(self.h.worktree), "t3/om-01-02", ok_worktree)):
            with self.assertRaises(Refused) as ctx:
                op()
            self.assertEqual(ctx.exception.code, "activation-required")  # a run that was never activated releases nothing either
        self.assertEqual(self.h.fake.comments[21], [])
        self.assertEqual(self.h.store.load_story("OM-01.02").phase, "claim-incomplete")

    def test_running_worker_keeps_ownership_until_terminal_evidence(self):
        self.h.claim()
        with self.assertRaises(Refused) as ctx:
            self.h.coordinator.cancel("OM-01.02", "stop")
        self.assertEqual(ctx.exception.code, "worker-not-terminal")
        with self.assertRaises(Refused):
            self.h.coordinator.cancel("OM-01.02", "stop", {"taskId": "task-impl-1", "runId": "task-impl-1" + ":run:1", "status": "cancel_requested"})
        with self.assertRaises(Refused):
            self.h.coordinator.cancel("OM-01.02", "stop", {"taskId": "other", "runId": "other" + ":run:1", "status": "cancelled"})
        self.assertEqual(self.h.store.load_story("OM-01.02").phase, "claimed")
        self.assertEqual(markers(self.h.fake, 21, "release"), [])
        result = self.h.coordinator.cancel_run("stop")
        self.assertEqual(result["awaiting_worker_termination"], [{"story": "OM-01.02", "task_id": "task-impl-1", "role": "implementer", "authorization": "run-1:OM-01.02:1", "code": "worker-not-terminal"}])
        self.assertTrue(self.h.store.load_run().cancelled)
        state = self.h.coordinator.cancel("OM-01.02", "stop", {"taskId": "task-impl-1", "runId": "task-impl-1" + ":run:1", "status": "cancelled"})
        self.assertEqual(state.phase, "cancelled")
        self.assertEqual(len(markers(self.h.fake, 21, "release")), 1)

    def test_non_live_coordinator_cannot_write(self):
        h = Harness(small_backlog(), live=False)
        try:
            with self.assertRaises(Refused) as ctx:
                h.claim()
            self.assertEqual(ctx.exception.code, "live-required")
            self.assertEqual(h.fake.comments[21], [])
        finally:
            h.close()
