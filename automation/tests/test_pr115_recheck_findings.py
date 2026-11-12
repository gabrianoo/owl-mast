"""Regressions for the five "fix first" findings of the PR #115 recheck review (review 5832610891,
2026-11-09): the cross-story claim race settled after our claim lands, the owner's way out of a
stray or forged claim (``dismiss-claim``), legacy raw-digest live activations, cleanup-only review
receipts without a live reviewer worktree, and ``resume`` re-settling a ``claim-unverifiable``
conflict."""

import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from automation.tests.fake_transport import FakeTransport, small_backlog
from automation.tests.support import IMPLEMENTER, REVIEW_BRANCH, REVIEW_WORKTREE, REVIEWER, Harness, git_commit, ok_worktree, write_policy
from automation.tests import test_activation as activation_tests
from automation.tests import test_pr115_review_findings as prior

LiveHarness, activation_text = activation_tests.LiveHarness, activation_tests.activation_text  # the TestCase classes of those modules are not imported here (unittest discovery would collect them twice)
arm_failure_after_claim, events, fresh, markers = prior.arm_failure_after_claim, prior.events, prior.fresh, prior.markers
from automation.unattended import cli
from automation.unattended.activation import load_activation
from automation.unattended.coordinator import Coordinator
from automation.unattended.errors import BudgetExhausted, Conflict, Refused
from automation.unattended.github import Comment, render_marker
from automation.unattended.policy import load_policy
from automation.unattended.state import Store

S = "OM-01.02"
OTHER = "OM-01.04"  # issue 23
EARLY = "2026-11-06T12:59:00Z"


def two_story_harness() -> Harness:
    return Harness(small_backlog(), allow='["OM-01.02", "OM-01.04"]', max_stories_per_run="2")


class CrossStoryClaimRaceTests(unittest.TestCase):
    """Fix 1: after our claim lands, claims on every other allowlisted story are read again and the earliest wins."""

    def interleave(self, h: Harness, created_at: str):
        """Another coordinator's claim on OM-01.04 lands while our claim on OM-01.02 is being posted."""
        original = h.fake.post_comment

        def post(number, body):
            posted = original(number, body)
            if "kind=claim" in body and number == 21:
                h.fake.comments[23].append(Comment(9, render_marker(kind="claim", run="run-other", story=OTHER, op="claim", inst="0123456789abcdef") + "\nother machine", "machine", created_at))
            return posted

        h.fake.post_comment = post

    def test_a_concurrent_earlier_claim_on_another_story_makes_ours_cancel_and_release(self):
        h = two_story_harness()
        try:
            self.interleave(h, EARLY)
            with self.assertRaises(Conflict) as ctx:
                h.reserve()
            self.assertEqual(ctx.exception.code, "claim-active-elsewhere")
            self.assertEqual(ctx.exception.detail["winner"]["on_story"], OTHER)
            state = h.store.load_story(S)
            self.assertEqual((state.phase, state.authorizations[0]["status"], state.claim["race_settled"]), ("cancelled", "not-launched", True))
            self.assertEqual(len([c for c in markers(h.fake, 21, "release") if "run=run-1" in c.body]), 1)
            self.assertTrue(events(h, "claim-active-elsewhere") and not events(h, "claim-race-lost"))
        finally:
            h.close()

    def test_a_concurrent_later_claim_on_another_story_loses_to_ours(self):
        h = two_story_harness()
        try:
            self.interleave(h, "2026-11-06T13:59:59Z")  # after every fake-transport tick of this test
            self.assertEqual(h.reserve().phase, "reserved")
            self.assertEqual(markers(h.fake, 21, "release"), [])
            self.assertTrue(events(h, "claim-race-settled"))
            self.assertEqual(h.store.load_story(S).claim["race_settled"], True)
        finally:
            h.close()

    def test_resume_paths_apply_the_cross_story_rule_too(self):
        h = two_story_harness()
        try:
            h.fake.crash_after_post = True
            with self.assertRaises(Exception):
                h.reserve()  # claim landed, nothing checkpointed
            h.fake.comments[23].append(Comment(9, render_marker(kind="claim", run="run-other", story=OTHER, op="claim") + "\nother machine", "machine", EARLY))
            with self.assertRaises(Conflict) as ctx:  # our claim landed: earliest wins, and the other one is earlier
                fresh(h).resume(S, ok_worktree)
            self.assertEqual(ctx.exception.code, "claim-active-elsewhere")
            self.assertEqual(h.store.load_story(S).phase, "cancelled")
            self.assertEqual(len([c for c in markers(h.fake, 21, "release") if "run=run-1" in c.body]), 1)
        finally:
            h.close()
        h = two_story_harness()
        try:
            h.fake.crash_after_post = True
            with self.assertRaises(Exception):
                h.reserve()
            h.fake.comments[23].append(Comment(9, render_marker(kind="claim", run="run-other", story=OTHER, op="claim") + "\nother machine", "machine", "2026-11-06T13:59:59Z"))
            self.assertEqual(fresh(h).resume(S, ok_worktree).phase, "reserved")  # our landed claim is earlier: it wins, nothing is cancelled on our side
            self.assertEqual(markers(h.fake, 21, "release"), [])
        finally:
            h.close()


class DismissClaimTests(unittest.TestCase):
    """Fix 2: the owner clears a stray or forged claim with a journaled dismissal marker."""

    def test_a_dismissed_claim_no_longer_blocks_anywhere_and_the_refusal_names_the_way_out(self):
        h = two_story_harness()
        try:
            stray = h.fake.add_comment(23, render_marker(kind="claim", run="run-x", story=OTHER, op="claim") + "\nforged", "stranger")
            with self.assertRaises(Refused) as ctx:
                h.reserve()
            self.assertEqual(ctx.exception.code, "claim-active-elsewhere")
            self.assertIn("dismiss-claim --issue <n> --comment-id <id>", str(ctx.exception))
            with self.assertRaises(Refused) as ctx:  # not a claim marker
                h.coordinator.dismiss_claim(23, h.fake.add_comment(23, "just a comment", "stranger").comment_id, "no")
            self.assertEqual(ctx.exception.code, "dismiss-target-invalid")
            with self.assertRaises(Refused):
                h.coordinator.dismiss_claim(23, stray.comment_id, "   ")
            with self.assertRaises(Refused) as ctx:  # no run here proves the stranger's coordinator finished: the attestation is required however old the claim
                h.coordinator.dismiss_claim(23, stray.comment_id, "stranger's comment, owner checked the issue")
            self.assertEqual(ctx.exception.code, "dismiss-target-live")
            report = h.coordinator.dismiss_claim(23, stray.comment_id, "stranger's comment, owner checked the issue: no such run anywhere", force=True)
            self.assertEqual((report["target"], report["target_author"]), (stray.comment_id, "stranger"))
            dismissals = markers(h.fake, 23, "dismiss")
            self.assertEqual((len(dismissals), dismissals[0].author, dismissals[0].marker["target"]), (1, "machine", str(stray.comment_id)))
            self.assertEqual(h.coordinator.dismiss_claim(23, stray.comment_id, "again", force=True)["dismissal_comment_id"], dismissals[0].comment_id)
            self.assertEqual(len(markers(h.fake, 23, "dismiss")), 1)  # idempotent
            self.assertEqual(len(events(h, "foreign-claim-dismissed")), 2)
            self.assertEqual(h.reserve().phase, "reserved")
            # a dismissal by another author clears nothing; our own claim cannot be dismissed
            other = Coordinator(h.fake, h.policy, Store(h.state_dir.parent / "elsewhere", "run-other"), live=True)
            own = [c for c in markers(h.fake, 21, "claim") if c.author == "machine"][0]
            with self.assertRaises(Refused) as ctx:
                h.coordinator.dismiss_claim(21, own.comment_id, "oops")
            self.assertEqual(ctx.exception.code, "dismiss-target-invalid")
            second = h.fake.add_comment(23, render_marker(kind="claim", run="run-y", story=OTHER, op="claim") + "\nforged again", "stranger2")
            h.fake.add_comment(23, render_marker(kind="dismiss", run="run-z", story=OTHER, op="dismiss-1", target=str(second.comment_id)) + "\nforged dismissal", "stranger3")
            self.assertEqual([c["comment_id"] for c in other._active_foreign_claims(23, OTHER)], [second.comment_id])  # a dismissal by another author clears nothing
        finally:
            h.close()

    def test_dismiss_claim_needs_live_and_is_a_cli_command(self):
        h = Harness(small_backlog(), live=False)
        try:
            stray = h.fake.add_comment(21, render_marker(kind="claim", run="run-x", story=S, op="claim") + "\nforged", "stranger")
            with self.assertRaises(Refused) as ctx:
                h.coordinator.dismiss_claim(21, stray.comment_id, "r")
            self.assertEqual(ctx.exception.code, "live-required")
        finally:
            h.close()
        h = Harness(small_backlog())
        try:
            stray = h.fake.add_comment(21, render_marker(kind="claim", run="run-x", story=S, op="claim") + "\nforged", "stranger")
            (Path(h.tmpdir.name) / "p").mkdir()
            policy = str(write_policy(Path(h.tmpdir.name) / "p", allow='["OM-01.02"]'))
            with mock.patch.object(cli, "GhCliTransport", lambda *a, **k: h.fake):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = cli.main(["--policy", policy, "--state-dir", str(h.state_dir), "--run-id", "run-1", "dismiss-claim", "--issue", "21", "--comment-id", str(stray.comment_id), "--reason", "owner"])
                self.assertEqual((code, json.loads(buf.getvalue())["error"]["message"]), (3, "dismiss-claim writes to GitHub; pass --live to confirm"))
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = cli.main(["--policy", policy, "--state-dir", str(h.state_dir), "--run-id", "run-1", "--live", "dismiss-claim", "--issue", "21", "--comment-id", str(stray.comment_id), "--reason", "owner"])
                self.assertEqual((code, json.loads(buf.getvalue())["error"]["code"]), (3, "dismiss-target-live"))
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = cli.main(["--policy", policy, "--state-dir", str(h.state_dir), "--run-id", "run-1", "--live", "dismiss-claim", "--issue", "21", "--comment-id", str(stray.comment_id), "--reason", "owner: machine x is gone", "--force"])
                self.assertEqual((code, json.loads(buf.getvalue())["target"]), (0, stray.comment_id))
        finally:
            h.close()


class LegacyDigestActivationTests(unittest.TestCase):
    """Fix 3: a live run that already exists bound to the raw-bytes digest of exactly these bytes still takes an activation naming it
    (a new activation must name the canonical digest: ``test_pr115_fix_first_round3.RawDigestScopeTests``)."""

    def test_raw_digest_activation_is_current_only_for_a_run_bound_to_it(self):
        lh = LiveHarness()
        try:
            lh.path.write_text(activation_text(lh.h.policy, policy_digest=f'"{lh.h.policy.raw_digest}"'), encoding="utf-8")
            lh.activation = load_activation(lh.path)
            self.assertEqual(lh.activation.problems(lh.h.policy, "run-live", lh.clock[0], bound_digest=lh.h.policy.raw_digest), [])
            self.assertEqual(lh.activation.problems(lh.h.policy, "run-live", lh.clock[0])[0][0], "activation-mismatch")  # no existing run: a new activation names the canonical digest
            lh.path.write_text(activation_text(lh.h.policy, policy_digest='"' + "f" * 64 + '"'), encoding="utf-8")
            self.assertEqual(load_activation(lh.path).problems(lh.h.policy, "run-live", lh.clock[0], bound_digest="f" * 64)[0][0], "activation-mismatch")  # bound to a digest that is not this policy's
        finally:
            lh.close()


class CleanupOnlyReviewReceiptTests(unittest.TestCase):
    """Fix 4: a review receipt that binds for cleanup only needs no live reviewer worktree."""

    def setUp(self):
        self.h = Harness(small_backlog())

    def tearDown(self):
        self.h.close()

    def test_revoked_review_authorization_binds_without_a_worktree(self):
        self.h.claim()
        self.h.checks()
        self.h.coordinator.authorize_review(S, self.h.sha)
        new_sha = git_commit(self.h.worktree, "more")
        self.h.coordinator.record_head(S, new_sha)  # invalidates the evidence and revokes the pending review authorization
        self.assertEqual(self.h.store.load_story(S).authorizations[-1]["status"], "revoked")
        with self.assertRaises(Refused) as ctx:  # a branch without a worktree is not a checkout
            self.h.coordinator.bind_receipt(S, REVIEWER, None, "b")
        self.assertEqual(ctx.exception.code, "reviewer-worktree-required")
        with self.assertRaises(Refused) as ctx:  # the reviewer's worktree is gone: binds on task identity alone
            self.h.coordinator.bind_receipt(S, REVIEWER)
        self.assertEqual((ctx.exception.code, ctx.exception.detail["bound_for_cleanup"]), ("authorization-revoked", True))
        state = self.h.store.load_story(S)
        self.assertEqual((state.active_task["taskId"], state.active_task["cleanup_only"], state.reviewer_receipts[-1]["worktree"], state.reviewer_receipts[-1]["head_at_bind"], state.reviewer_receipts[-1]["worktree_verified"]), ("task-review-1", "authorization-revoked", None, None, False))

        self.assertEqual(self.h.coordinator.record_task_terminal(S, self.h.terminal(status="cancelled")).active_task, None)

    def test_stopped_run_binds_the_late_review_receipt_without_a_worktree_but_never_in_the_implementers_tree(self):
        self.h.claim()
        self.h.checks()
        self.h.coordinator.authorize_review(S, self.h.sha)
        self.h.coordinator.cancel_run("stop")
        with self.assertRaises(Refused) as ctx:  # a supplied path is still checked against the implementer's worktree
            self.h.coordinator.bind_receipt(S, REVIEWER, str(self.h.worktree), "t3/om-01-02", lambda p, b: (False, "gone"))
        self.assertEqual(ctx.exception.code, "reviewer-worktree-shared")
        with self.assertRaises(BudgetExhausted) as ctx:
            self.h.coordinator.bind_receipt(S, REVIEWER, worktree_check=lambda p, b: (False, "gone"))
        self.assertEqual((ctx.exception.code, ctx.exception.detail["bound_for_cleanup"]), ("run-cancelled", True))
        self.assertEqual(self.h.store.load_story(S).active_task["taskId"], "task-review-1")
        # an ordinary (not cleanup) review bind still needs the reviewer's own verified worktree
        h2 = Harness(small_backlog())
        try:
            h2.claim(); h2.checks(); h2.coordinator.authorize_review(S, h2.sha)
            with self.assertRaises(Refused) as ctx:
                h2.coordinator.bind_receipt(S, REVIEWER)
            self.assertEqual(ctx.exception.code, "reviewer-worktree-required")
            self.assertEqual(h2.coordinator.bind_receipt(S, REVIEWER, REVIEW_WORKTREE, REVIEW_BRANCH, ok_worktree).phase, "review-requested")
        finally:
            h2.close()


class UnverifiableClaimResettleTests(unittest.TestCase):
    """Fix 5: a ``claim-unverifiable`` conflict is re-verified by ``resume`` and settled once the claim is readable."""

    def unverifiable(self) -> Harness:
        h = Harness(small_backlog())
        arm_failure_after_claim(h, reads_after_post=2, hide_ours=True)
        with self.assertRaises(Conflict) as ctx:
            h.reserve()
        self.assertEqual(ctx.exception.code, "claim-unverifiable")
        return h

    def test_resume_restores_and_settles_once_the_claim_is_readable(self):
        h = self.unverifiable()
        try:
            resumed = fresh(h).resume(S, ok_worktree)  # still hidden: stays in conflict, nothing posted
            self.assertEqual((resumed.phase, len(markers(h.fake, 21, "claim"))), ("conflict", 1))
            self.assertTrue(events(h, "claim-still-unverifiable"))
            h.fake.list_comments = FakeTransport.list_comments.__get__(h.fake)  # read-after-write lag is over
            resumed = fresh(h).resume(S, ok_worktree)
            self.assertEqual((resumed.phase, resumed.blocked, resumed.claim["race_settled"]), ("reserved", None, True))
            self.assertTrue(events(h, "claim-reverified") and events(h, "claim-race-settled"))
            self.assertEqual(len(markers(h.fake, 21, "claim")), 1)  # nothing reposted
            self.assertEqual(fresh(h).bind_receipt(S, IMPLEMENTER, str(h.worktree), "t3/om-01-02", ok_worktree).phase, "claimed")
        finally:
            h.close()

    def test_resume_cancels_a_reverified_claim_that_lost_the_race(self):
        h = self.unverifiable()
        try:
            h.fake.list_comments = FakeTransport.list_comments.__get__(h.fake)
            h.fake.comments[21].insert(0, Comment(5, render_marker(kind="claim", run="run-other", story=S, op="claim") + "\nearlier", "machine", EARLY))
            with self.assertRaises(Conflict) as ctx:
                fresh(h).resume(S, ok_worktree)
            self.assertEqual(ctx.exception.code, "claim-race-lost")
            state = h.store.load_story(S)
            self.assertEqual((state.phase, state.authorizations[0]["status"]), ("cancelled", "not-launched"))
            self.assertEqual(len([c for c in markers(h.fake, 21, "release") if "run=run-1" in c.body]), 1)
        finally:
            h.close()

    def test_a_stopped_run_withholds_the_reverification(self):
        h = self.unverifiable()
        try:
            h.fake.list_comments = FakeTransport.list_comments.__get__(h.fake)
            stopped = Coordinator(h.fake, h.policy, Store(h.state_dir, "run-1"), now=lambda: "2030-01-01T00:00:00Z", live=True)  # past the wall clock
            resumed = stopped.resume(S, ok_worktree)
            self.assertEqual((resumed.phase, resumed.claim["race_settled"], len(h.fake.comments[21])), ("conflict", False, 1))  # nothing settled, nothing posted
            self.assertTrue(any("claim unverifiable" in e["detail"]["reason"] for e in events(h, "reconciliation-withheld")))
        finally:
            h.close()

if __name__ == "__main__":  # pragma: no cover
    unittest.main()
