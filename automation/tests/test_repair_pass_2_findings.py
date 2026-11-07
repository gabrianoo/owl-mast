"""Repair pass 2 (the last authorized) after the fresh independent review of
0f893d4255eafd79cb7654e9f41944dd3d1af553 (PR #107, repair pass 1): the two remaining code
findings the reviewer reproduced with ``/tmp/eng01-review-0f893d-probes.py`` (transcript in
``evidence/fresh-review-0f893d42-probe-before-2026-11-06.txt``).

RP2-F1 (HIGH): an issued task authorization is an ownership obligation until it is resolved
by the exact receipt of its task plus that task's terminal evidence, or by a positive
no-launch reconciliation (coordinator attestation, or the structural proof that the issuing
reservation never returned). Cancel, block, cancel-run, invalidation, expiry and a dirty
worktree revoke it but never release the claim, the concurrency slot or issue a replacement;
a late receipt binds to the exact authorization id, for cleanup only, and a reviewer receipt
carries the SHA it was authorized for, never the current head.

RP2-F2 (MEDIUM): a completed proposal (or claim) intent whose transition did not persist is
reconciled only behind every gate of a fresh attempt: run stop and expiry, local approval and
ownership, fresh revisions with unique identities, the re-read worktree and the PR. A failing
gate withholds the transition, keeps the posted effect as history, never reposts it and has
the same persisted consequence as on a fresh attempt.

Every test asserts persisted state, transport calls and GitHub effects, not only exceptions.
In-memory GitHub and a real local git worktree; nothing touches live GitHub or T3."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from automation.tests.fake_transport import CrashAfterEffect, issue, small_backlog
from automation.tests.support import IMPLEMENTER, REVIEWER, Harness, failing_runner, git_commit, ok_worktree, passing_runner, receipt, write_policy
from automation.tests.test_final_findings import fresh, markers
from automation.unattended import cli
from automation.unattended.coordinator import Coordinator
from automation.unattended.errors import BudgetExhausted, Outage, PermissionDenied, ReceiptInvalid, Refused, StaleRevision
from automation.unattended.github import Comment, PullRequestRecord, render_marker
from automation.unattended.state import Store

S = "OM-01.02"
OTHER = "OM-01.04"
LATER = "2099-01-01T00:00:00Z"
AUTH1 = "run-1:OM-01.02:1"


def two_stories(**overrides) -> Harness:
    return Harness(small_backlog(), allow='["OM-01.02", "OM-01.04"]', max_stories_per_run="2", **overrides)


def other_run(h: Harness) -> Coordinator:
    return Coordinator(h.fake, h.policy, Store(h.state_dir, "run-2"), live=True)


def journal_events(h: Harness, event: str) -> list[dict]:
    return [e for e in h.store.read_journal() if e["event"] == event]


def split_done_proposal(h: Harness) -> str:
    """A proposal that landed (intent done, comment posted) whose ``proposed`` transition did
    not persist: the phase is still ``review-approved``."""
    h.to_review_approved()
    h.fake.pull_requests[7] = PullRequestRecord(7, "OPEN", h.sha, False, [], "SUCCESS")
    h.coordinator.propose_evidence(S, h.sha, 7, ["OM-01.02-T1"], "evidence")
    state = h.store.load_story(S)
    state.phase = "review-approved"
    h.store.save_story(state)
    op = f"proposal-{h.sha[:12]}-pr7"
    assert (state.intent(op).status, len(markers(h.fake, 21, "proposal"))) == ("done", 1)
    h.fake.calls = []
    return op


class RP2F1UnresolvedAuthorizationsAreOwnershipObligations(unittest.TestCase):
    """RP2-F1: reserve → authorized launch whose receipt is late → cancel / block / cancel-run
    must not abandon the authorization, release the claim or admit another story."""

    def assert_owned_unreleased(self, h: Harness, phase: str, revoked_reason_prefix: str):
        state = h.store.load_story(S)
        auth = state.authorizations[0]
        self.assertEqual((state.phase, state.active_task, auth["status"], auth["task_id"]), (phase, None, "revoked", None))
        self.assertTrue(auth["reason"].startswith(revoked_reason_prefix), auth["reason"])
        self.assertEqual(state.unresolved_authorization()["id"], AUTH1)
        self.assertEqual((len(markers(h.fake, 21, "claim")), markers(h.fake, 21, "release"), markers(h.fake, 21, "block")), (1, [], []))
        self.assertEqual(len(other_run(h)._active_foreign_claims(21, S)), 1)  # the claim is still ours and still visible
        self.assertEqual(h.store.story_counts()["delegated_tasks"], 1)

    def test_cancel_and_block_with_an_unbound_implementation_authorization_refuse_revoke_and_keep_everything_owned(self):
        for terminal in ("cancel", "block"):
            h = two_stories()
            try:
                h.reserve()
                op = getattr(h.coordinator, terminal)
                for attempt in range(2):  # idempotent: the second refusal changes nothing more
                    with self.assertRaises(Refused) as ctx:
                        op(S, "stop after launch before receipt")
                    self.assertEqual((ctx.exception.code, ctx.exception.detail["authorization"], ctx.exception.detail["role"], ctx.exception.detail["task_id"]), ("authorization-unresolved", AUTH1, "implementer", None))
                    self.assert_owned_unreleased(h, "reserved", f"story {'cancelled' if terminal == 'cancel' else 'blocked'} requested")
                self.assertEqual(len(journal_events(h, "authorization-revoked")), 1)
                with self.assertRaises(Refused) as ctx:  # concurrency capacity is not released either
                    h.reserve(OTHER)
                self.assertIn("another story is active", str(ctx.exception))
                self.assertEqual((h.store.load_story(OTHER), markers(h.fake, 23, "claim")), (None, []))
                # the late receipt binds, for cleanup only, to the exact authorization
                with self.assertRaises(Refused) as ctx:
                    fresh(h).bind_receipt(S, IMPLEMENTER, str(h.worktree), "t3/om-01-02", ok_worktree, authorization=AUTH1)
                self.assertEqual((ctx.exception.code, ctx.exception.detail["bound_for_cleanup"], ctx.exception.detail["authorization"], ctx.exception.detail["task_id"]), ("authorization-revoked", True, AUTH1, "task-impl-1"))
                state = h.store.load_story(S)
                self.assertEqual((state.phase, state.active_task["taskId"], state.active_task["cleanup_only"], state.active_task["authorization"]), ("reserved", "task-impl-1", "authorization-revoked", AUTH1))
                self.assertEqual((state.authorizations[0]["status"], state.authorizations[0]["task_id"], state.authorizations[0]["cleanup_only"], state.unresolved_authorization()), ("consumed", "task-impl-1", "authorization-revoked", None))
                self.assertEqual((state.implementer_receipts[-1]["authorization"], state.claim["worktree_path"]), (AUTH1, str(h.worktree)))
                self.assertIn("task-impl-1", h.store.bound_task_ids())
                for advancing in (lambda: fresh(h).record_head(S, h.sha, {"taskId": "task-impl-1", "runId": "task-impl-1" + ":run:1", "status": "result_available"}), lambda: fresh(h).run_checks(S, h.sha, str(h.worktree), passing_runner)):
                    with self.assertRaises(Refused):  # no work was authorized: the phase never advanced
                        advancing()
                self.assertEqual(h.store.load_story(S).phase, "reserved")
                with self.assertRaises(Refused) as ctx:  # still owned: only that task's terminal evidence releases it
                    fresh(h).cancel(S, "finish")
                self.assertEqual((ctx.exception.code, ctx.exception.detail["task_id"], ctx.exception.detail["authorization"]), ("worker-not-terminal", "task-impl-1", AUTH1))
                with self.assertRaises(Refused):
                    fresh(h).cancel(S, "finish", {"taskId": "task-impl-9", "runId": "task-impl-9" + ":run:1", "status": "cancelled"})
                self.assertEqual(markers(h.fake, 21, "release"), [])
                state = fresh(h).cancel(S, "finish", {"taskId": "task-impl-1", "runId": "task-impl-1" + ":run:1", "status": "cancelled"})
                self.assertEqual((state.phase, state.active_task, state.task_history[-1]["taskId"], state.task_history[-1]["authorization"]), ("cancelled", None, "task-impl-1", AUTH1))
                self.assertEqual((len(markers(h.fake, 21, "release")), other_run(h)._active_foreign_claims(21, S)), (1, []))
                self.assertEqual(h.store.story_counts()["delegated_tasks"], 1)
                self.assertEqual(fresh(h).reserve(OTHER, h.snapshot, "c5d9d2e").phase, "reserved")  # capacity released only now
                self.assertEqual(h.store.story_counts()["delegated_tasks"], 2)
            finally:
                h.close()

    def test_cancel_run_with_an_unbound_authorization_reports_it_awaiting_and_binds_for_cleanup_under_the_stop(self):
        h = two_stories()
        try:
            h.reserve()
            result = h.coordinator.cancel_run("stop after launch before receipt")
            self.assertEqual((result["cancelled"], result["awaiting_worker_termination"]), ([], [{"story": S, "task_id": None, "role": "implementer", "authorization": AUTH1, "code": "authorization-unresolved"}]))
            self.assertTrue(h.store.load_run().cancelled)
            self.assert_owned_unreleased(h, "reserved", "story cancelled requested")
            with self.assertRaises(BudgetExhausted) as ctx:
                h.reserve(OTHER)
            self.assertEqual(ctx.exception.code, "run-cancelled")
            self.assertEqual(fresh(h).resume(S, ok_worktree).phase, "reserved")  # restart changes nothing: still owned
            with self.assertRaises(BudgetExhausted) as ctx:  # the stop code wins; the binding is still cleanup-only
                fresh(h).bind_receipt(S, IMPLEMENTER, str(h.worktree), "t3/om-01-02", ok_worktree, authorization=AUTH1)
            self.assertEqual((ctx.exception.code, ctx.exception.detail["bound_for_cleanup"], ctx.exception.detail["authorization"]), ("run-cancelled", True, AUTH1))
            state = h.store.load_story(S)
            self.assertEqual((state.phase, state.active_task["taskId"], state.active_task["cleanup_only"], state.authorizations[0]["status"]), ("reserved", "task-impl-1", "run-cancelled", "consumed"))
            result = fresh(h).cancel_run("finish")
            self.assertEqual(result["awaiting_worker_termination"], [{"story": S, "task_id": "task-impl-1", "role": "implementer", "authorization": AUTH1, "code": "worker-not-terminal"}])
            self.assertEqual(markers(h.fake, 21, "release"), [])
            result = fresh(h).cancel_run("finish", task_evidence={S: {"taskId": "task-impl-1", "runId": "task-impl-1" + ":run:1", "status": "cancelled"}})
            self.assertEqual(([s["phase"] for s in result["cancelled"]], result["awaiting_worker_termination"]), (["cancelled"], []))
            self.assertEqual((len(markers(h.fake, 21, "release")), h.store.story_counts()["delegated_tasks"]), (1, 1))
        finally:
            h.close()

    def test_no_launch_attestation_is_the_only_release_without_a_receipt_and_names_the_exact_authorization(self):
        h = two_stories()
        try:
            h.reserve()
            with self.assertRaises(Refused):
                h.coordinator.cancel(S, "stop")
            c = fresh(h)
            for bad in (None, {}, {"authorization": "run-1:OM-01.02:9"}, {"authorization": "run-1:OM-01.04:1"}, "run-1:OM-01.02:1"):
                with self.assertRaises(Refused) as ctx:
                    c.record_no_launch(S, bad)
                self.assertEqual(ctx.exception.code, "no-launch-invalid")
            self.assert_owned_unreleased(h, "reserved", "story cancelled requested")
            state = c.record_no_launch(S, {"authorization": AUTH1, "reason": "delegate_task failed before returning a task id"})
            auth = state.authorizations[0]
            self.assertEqual((state.phase, auth["status"], auth["resolution"], auth["task_id"], state.unresolved_authorization()), ("reserved", "not-launched", "attested", None, None))
            self.assertIn("delegate_task failed", auth["reason"])
            self.assertEqual(journal_events(h, "authorization-not-launched")[-1]["detail"]["authorization"], AUTH1)
            with self.assertRaises(Refused) as ctx:  # resolved: a late receipt has nothing to bind to, nothing is reinterpreted
                c.bind_receipt(S, IMPLEMENTER, str(h.worktree), "t3/om-01-02", ok_worktree, authorization=AUTH1)
            self.assertEqual(ctx.exception.code, "no-authorization")
            with self.assertRaises(Refused) as ctx:  # an attestation applies once
                c.record_no_launch(S, {"authorization": AUTH1})
            self.assertEqual(ctx.exception.code, "no-launch-invalid")
            state = c.cancel(S, "stop")
            self.assertEqual((state.phase, len(markers(h.fake, 21, "release")), h.store.story_counts()["delegated_tasks"]), ("cancelled", 1, 1))  # slot spent, never refunded
            self.assertEqual(fresh(h).reserve(OTHER, h.snapshot, "c5d9d2e").phase, "reserved")
        finally:
            h.close()

    def test_no_launch_can_be_presented_inline_to_cancel_block_and_cancel_run(self):
        for terminal in ("cancel", "block", "cancel_run"):
            h = two_stories()
            try:
                h.reserve()
                attest = {"authorization": AUTH1, "reason": "stopped before delegate_task"}
                if terminal == "cancel_run":
                    result = h.coordinator.cancel_run("stop", no_launch={S: attest})
                    self.assertEqual(([s["phase"] for s in result["cancelled"]], result["awaiting_worker_termination"]), (["cancelled"], []))
                else:
                    state = getattr(h.coordinator, terminal)(S, "stop", no_launch=attest)
                    self.assertEqual(state.phase, "cancelled" if terminal == "cancel" else "blocked")
                state = h.store.load_story(S)
                self.assertEqual((state.authorizations[0]["status"], state.authorizations[0]["resolution"], state.blocked["no_launch"]), ("not-launched", "attested", attest))
                self.assertEqual(len(markers(h.fake, 21, "release" if terminal != "block" else "block")), 1)
                with self.assertRaises(Refused) as ctx:  # a consumed authorization can never be attested away
                    h2 = two_stories()
                    try:
                        h2.claim()
                        h2.coordinator.cancel(S, "stop", no_launch={"authorization": AUTH1})
                    finally:
                        h2.close()
                self.assertEqual((ctx.exception.code, ctx.exception.detail["status"], ctx.exception.detail["task_id"]), ("no-launch-invalid", "consumed", "task-impl-1"))
            finally:
                h.close()

    def test_wrong_or_stale_authorization_ids_and_wrong_role_receipts_bind_nothing(self):
        h = Harness(small_backlog())
        try:
            h.reserve()
            with self.assertRaises(Refused) as ctx:
                h.coordinator.bind_receipt(S, IMPLEMENTER, str(h.worktree), "t3/om-01-02", ok_worktree, authorization="run-1:OM-01.02:2")
            self.assertEqual((ctx.exception.code, ctx.exception.detail["expected"], ctx.exception.detail["given"]), ("authorization-mismatch", AUTH1, "run-1:OM-01.02:2"))
            with self.assertRaises(ReceiptInvalid):  # a reviewer receipt cannot consume an implementation authorization
                h.coordinator.bind_receipt(S, REVIEWER, str(h.worktree), "t3/om-01-02", ok_worktree, authorization=AUTH1)
            state = h.store.load_story(S)
            self.assertEqual((state.phase, state.active_task, state.authorizations[0]["status"], state.implementer_receipts, h.store.bound_task_ids()), ("reserved", None, "pending", [], set()))
            state = h.coordinator.bind_receipt(S, IMPLEMENTER, str(h.worktree), "t3/om-01-02", ok_worktree, authorization=AUTH1)
            self.assertEqual((state.phase, state.active_task["authorization"], state.implementer_receipts[-1]["authorization"]), ("claimed", AUTH1, AUTH1))
            h.checks()
            h.coordinator.authorize_review(S, h.sha)
            with self.assertRaises(Refused) as ctx:  # the consumed implementation id is not the pending review authorization
                h.coordinator.bind_receipt(S, REVIEWER, worktree_check=ok_worktree, authorization=AUTH1)
            self.assertEqual((ctx.exception.code, ctx.exception.detail["expected"]), ("authorization-mismatch", "run-1:OM-01.02:2"))
            self.assertEqual(h.coordinator.bind_receipt(S, REVIEWER, worktree_check=ok_worktree, authorization="run-1:OM-01.02:2").reviewer_receipts[-1]["sha"], h.sha)
        finally:
            h.close()

    def test_review_authorization_invalidated_by_a_new_head_keeps_the_old_reviewer_owned_and_never_labels_it_with_the_new_sha(self):
        """The reviewer's second scenario: authorize review at A, record head B before the
        receipt, then B's checks and authorization must wait; A's late receipt is A's."""
        for resolve_by in ("receipt", "attestation"):
            h = Harness(small_backlog())
            try:
                h.claim()
                h.checks()
                old = h.coordinator.authorize_review(S, h.sha).pending_authorization()
                sha_a = h.sha
                sha_b = git_commit(h.worktree, "newhead")
                state = h.coordinator.record_head(S, sha_b)
                auth = state.authorization(old["id"])
                self.assertEqual((state.phase, state.head_sha, state.approved_sha, auth["status"], auth["sha"], state.pending_authorization()), ("implemented", sha_b, None, "revoked", sha_a, None))
                for op in (lambda: fresh(h).run_checks(S, sha_b, str(h.worktree), passing_runner), lambda: fresh(h).authorize_review(S, sha_b), lambda: fresh(h).cancel(S, "stop")):
                    with self.assertRaises(Refused) as ctx:
                        op()
                    self.assertIn(ctx.exception.code, ("authorization-unresolved", "refused"))  # unresolved A, or the phase it left behind
                state = h.store.load_story(S)
                self.assertEqual((len(state.authorizations), state.phase, state.unresolved_authorization()["id"]), (2, "implemented", old["id"]))  # no replacement issued
                self.assertEqual(h.store.story_counts()["delegated_tasks"], 2)
                if resolve_by == "receipt":
                    with self.assertRaises(Refused) as ctx:  # A's late receipt (with or without the id: A is the only unresolved slot) binds to A for cleanup
                        fresh(h).bind_receipt(S, REVIEWER, worktree_check=ok_worktree, authorization=old["id"])
                    self.assertEqual((ctx.exception.code, ctx.exception.detail["bound_for_cleanup"], ctx.exception.detail["sha"]), ("authorization-revoked", True, sha_a))
                    state = h.store.load_story(S)
                    self.assertEqual((state.phase, state.reviewer_receipts[-1]["sha"], state.reviewer_receipts[-1]["authorization"], state.active_task["role"], state.active_task["cleanup_only"]), ("implemented", sha_a, old["id"], "reviewer", "authorization-revoked"))
                    with self.assertRaises(Refused):  # the old reviewer's verdict can approve nothing
                        fresh(h).record_review(S, sha_b, "approved", "report for A", {"taskId": "task-review-1", "runId": "task-review-1" + ":run:1", "status": "result_available"})
                    with self.assertRaises(Refused):
                        fresh(h).record_review(S, sha_a, "approved", "report for A", {"taskId": "task-review-1", "runId": "task-review-1" + ":run:1", "status": "result_available"})
                    state = h.store.load_story(S)
                    self.assertEqual((state.phase, state.approved_sha, state.reviews, state.active_task["taskId"]), ("implemented", None, [], "task-review-1"))
                    with self.assertRaises(Refused) as ctx:  # B's checks still wait for the old reviewer to leave
                        fresh(h).run_checks(S, sha_b, str(h.worktree), passing_runner)
                    self.assertEqual(ctx.exception.code, "worker-not-terminal")
                    self.assertEqual(fresh(h).record_task_terminal(S, {"taskId": "task-review-1", "runId": "task-review-1" + ":run:1", "status": "cancelled"}).active_task, None)
                else:
                    state = fresh(h).record_no_launch(S, {"authorization": old["id"], "reason": "reviewer never launched"})
                    self.assertEqual((state.authorizations[-1]["status"], state.unresolved_authorization()), ("not-launched", None))
                # now B proceeds through its own authorization, receipt and verdict
                fresh(h).run_checks(S, sha_b, str(h.worktree), passing_runner)
                new = fresh(h).authorize_review(S, sha_b).pending_authorization()
                self.assertEqual((new["id"], new["sha"]), ("run-1:OM-01.02:3", sha_b))
                with self.assertRaises(Refused) as ctx:  # A's id can no longer bind anything, let alone B's slot
                    fresh(h).bind_receipt(S, receipt(REVIEWER, "task-review-2"), worktree_check=ok_worktree, authorization=old["id"])
                self.assertEqual(ctx.exception.code, "authorization-mismatch")
                state = fresh(h).bind_receipt(S, receipt(REVIEWER, "task-review-2"), worktree_check=ok_worktree, authorization=new["id"])
                self.assertEqual((state.phase, state.reviewer_receipts[-1]["sha"], state.reviewer_receipts[-1]["authorization"]), ("review-requested", sha_b, new["id"]))
                state = fresh(h).record_review(S, sha_b, "approved", "report for B", {"taskId": "task-review-2", "runId": "task-review-2" + ":run:1", "status": "result_available"})
                self.assertEqual((state.phase, state.approved_sha, [r["sha"] for r in state.reviewer_receipts]), ("review-approved", sha_b, [sha_a, sha_b] if resolve_by == "receipt" else [sha_b]))
                self.assertEqual(h.store.story_counts()["delegated_tasks"], 3)
            finally:
                h.close()

    def test_dirty_worktree_at_review_admission_revokes_the_pending_review_authorization(self):
        h = Harness(small_backlog())
        try:
            h.claim()
            h.checks()
            h.coordinator.authorize_review(S, h.sha)
            (h.worktree / "README").write_text("edited after the review was authorized")
            with self.assertRaises(Refused) as ctx:
                fresh(h).authorize_review(S, h.sha)
            self.assertEqual(ctx.exception.code, "evidence-invalidated")
            state = h.store.load_story(S)
            auth = state.authorizations[-1]
            self.assertEqual((state.phase, auth["status"], auth["sha"], state.pending_authorization()), ("implemented", "revoked", h.sha, None))
            with self.assertRaises(Refused) as ctx:  # already revoked: cancel still refuses, revokes nothing twice
                fresh(h).cancel(S, "stop")
            self.assertEqual((ctx.exception.code, len(journal_events(h, "authorization-revoked"))), ("authorization-unresolved", 0))
            self.assertEqual(h.store.load_story(S).authorizations[-1]["reason"], auth["reason"])
            with self.assertRaises(Refused) as ctx:
                fresh(h).bind_receipt(S, REVIEWER, worktree_check=ok_worktree)
            self.assertEqual((ctx.exception.code, ctx.exception.detail["bound_for_cleanup"]), ("authorization-revoked", True))
            self.assertEqual(h.store.load_story(S).phase, "implemented")
            state = fresh(h).cancel(S, "stop", {"taskId": "task-review-1", "runId": "task-review-1" + ":run:1", "status": "cancelled"})
            self.assertEqual((state.phase, len(markers(h.fake, 21, "release"))), ("cancelled", 1))
        finally:
            h.close()

    def test_repair_authorization_revoked_by_cancel_binds_for_cleanup_in_the_repair_phase(self):
        h = Harness(small_backlog())
        try:
            h.claim()
            h.checks(runner=failing_runner)
            auth = h.coordinator.authorize_repair(S).pending_authorization()
            with self.assertRaises(Refused) as ctx:
                h.coordinator.block(S, "owner decision while the repair task may be running")
            self.assertEqual((ctx.exception.code, ctx.exception.detail["purpose"]), ("authorization-unresolved", "repair"))
            self.assertEqual((h.store.load_story(S).phase, markers(h.fake, 21, "block")), ("repair-authorized", []))
            with self.assertRaises(Refused) as ctx:  # authorize-repair issues no second round while the first is unresolved
                fresh(h).authorize_repair(S)
            self.assertEqual((ctx.exception.code, h.store.load_story(S).repair_rounds, h.store.story_counts()["delegated_tasks"]), ("authorization-unresolved", 1, 2))
            with self.assertRaises(Refused) as ctx:
                fresh(h).bind_receipt(S, receipt(IMPLEMENTER, "task-impl-2"), worktree_check=ok_worktree, authorization=auth["id"])
            self.assertEqual(ctx.exception.code, "authorization-revoked")
            state = h.store.load_story(S)
            self.assertEqual((state.phase, state.active_task["taskId"], state.implementer_receipts[-1]["authorization"]), ("repair-authorized", "task-impl-2", auth["id"]))
            with self.assertRaises(Refused) as ctx:
                fresh(h).record_head(S, h.sha, {"taskId": "task-impl-2", "runId": "task-impl-2" + ":run:1", "status": "result_available"})
            self.assertEqual(ctx.exception.code, "repair-required")
            state = fresh(h).block(S, "owner decision", {"taskId": "task-impl-2", "runId": "task-impl-2" + ":run:1", "status": "cancelled"})
            self.assertEqual((state.phase, len(markers(h.fake, 21, "block")), h.store.story_counts()["delegated_tasks"]), ("blocked", 1, 2))
        finally:
            h.close()

    def test_expired_run_with_an_unbound_authorization_releases_only_through_a_receipt_or_an_attestation(self):
        for resolve_by in ("receipt", "attestation"):
            h = Harness(small_backlog())
            try:
                h.reserve()
                c = fresh(h)
                c.now = lambda: LATER
                with self.assertRaises(Refused) as ctx:  # expiry stops no child: the slot is still an obligation
                    c.cancel(S, "wall clock")
                self.assertEqual((ctx.exception.code, h.store.load_story(S).authorizations[0]["status"]), ("authorization-unresolved", "revoked"))
                self.assertEqual(markers(h.fake, 21, "release"), [])
                if resolve_by == "receipt":
                    with self.assertRaises(BudgetExhausted) as ctx:
                        c.bind_receipt(S, IMPLEMENTER, str(h.worktree), "t3/om-01-02", ok_worktree, authorization=AUTH1)
                    self.assertEqual((ctx.exception.code, ctx.exception.detail["bound_for_cleanup"]), ("wall-clock-exceeded", True))
                    with self.assertRaises(Refused):
                        c.cancel(S, "wall clock")
                    state = c.cancel(S, "wall clock", {"taskId": "task-impl-1", "runId": "task-impl-1" + ":run:1", "status": "cancelled"})
                else:
                    state = c.cancel(S, "wall clock", no_launch={"authorization": AUTH1, "reason": "never launched"})
                self.assertEqual((state.phase, len(markers(h.fake, 21, "release")), h.store.story_counts()["delegated_tasks"]), ("cancelled", 1, 1))
            finally:
                h.close()

    def test_revocation_cleanup_binding_and_ownership_survive_restarts(self):
        h = Harness(small_backlog())
        try:
            h.reserve()
            with self.assertRaises(Refused):
                fresh(h).cancel(S, "stop")
            self.assertEqual(fresh(h).resume(S, ok_worktree).unresolved_authorization()["status"], "revoked")
            with self.assertRaises(Refused):
                fresh(h).bind_receipt(S, IMPLEMENTER, str(h.worktree), "t3/om-01-02", ok_worktree, authorization=AUTH1)
            with self.assertRaises(Refused) as ctx:  # a retry of the same bind: the authorization is consumed, the id is bound; nothing double-spends
                fresh(h).bind_receipt(S, IMPLEMENTER, str(h.worktree), "t3/om-01-02", ok_worktree, authorization=AUTH1)
            self.assertEqual(ctx.exception.code, "no-authorization")
            self.assertEqual(fresh(h).resume(S, ok_worktree).active_task["taskId"], "task-impl-1")
            self.assertEqual((h.store.story_counts()["delegated_tasks"], h.store.bound_task_ids()), (1, {"task-impl-1"}))
            self.assertEqual(fresh(h).record_task_terminal(S, {"taskId": "task-impl-1", "runId": "task-impl-1" + ":run:1", "status": "result_available"}).active_task, None)
            self.assertEqual(fresh(h).cancel(S, "finish").phase, "cancelled")
        finally:
            h.close()

    def test_a_reservation_that_never_returned_is_structurally_not_launched(self):
        """claim-incomplete (crash after the claim post) and conflict entered from it: the
        coordinator never saw ``reserved``, so no task can exist; cancel needs no attestation."""
        h = Harness(small_backlog())
        try:
            h.fake.crash_after_post = True
            with self.assertRaises(CrashAfterEffect):
                h.reserve()
            state = fresh(h).cancel(S, "stop before the reservation completed")
            self.assertEqual((state.phase, state.authorizations[0]["status"], state.authorizations[0]["resolution"], state.blocked["authorizations_resolved"]), ("cancelled", "not-launched", "structural", [AUTH1]))
            self.assertEqual(len(markers(h.fake, 21, "release")), 1)
        finally:
            h.close()
        h = Harness(small_backlog())
        try:
            marker = render_marker(kind="claim", op="claim", run="run-1", story=S)
            h.fake.comments[21] += [Comment(1, marker + "\nfirst", "x", "t"), Comment(2, marker + "\nsecond", "y", "t")]
            with self.assertRaises(Exception):
                h.reserve()
            self.assertEqual(h.store.load_story(S).phase, "conflict")
            state = fresh(h).cancel(S, "duplicate marker")
            self.assertEqual((state.phase, state.authorizations[0]["status"], state.authorizations[0]["resolution"]), ("cancelled", "not-launched", "structural"))
        finally:
            h.close()
        h = Harness(small_backlog())
        try:  # but a reservation that DID return is never resolved structurally
            h.reserve()
            with self.assertRaises(Refused) as ctx:
                fresh(h).cancel(S, "stop")
            self.assertEqual(ctx.exception.code, "authorization-unresolved")
        finally:
            h.close()

    def test_cli_exposes_the_authorization_id_and_the_no_launch_attestation_behind_the_live_gate(self):
        choices = list(cli.build_parser()._subparsers._group_actions[0].choices)
        self.assertIn("record-no-launch", choices)
        from automation.unattended.github import GhCliTransport

        calls = []
        original = GhCliTransport._run
        GhCliTransport._run = lambda self, args, stdin=None: calls.append(args) or "{}"
        try:
            with tempfile.TemporaryDirectory() as tmp:
                policy = write_policy(Path(tmp), allow='["OM-01.02"]')
                for argv in (["bind-receipt", S, "--receipt", '{"taskId": "t"}', "--authorization", AUTH1], ["record-no-launch", S, "--no-launch", json.dumps({"authorization": AUTH1})],
                             ["cancel", S, "--reason", "r", "--no-launch", json.dumps({"authorization": AUTH1})], ["cancel-run", "--reason", "r", "--no-launch", json.dumps({S: {"authorization": AUTH1}})]):
                    buf = io.StringIO()
                    with redirect_stdout(buf):
                        code = cli.main(["--policy", str(policy), "--state-dir", tmp, "--run-id", "r", "--live", *argv])
                    self.assertEqual((code, json.loads(buf.getvalue())["error"]["code"]), (3, "activation-required"), argv)
        finally:
            GhCliTransport._run = original
        self.assertEqual(calls, [])


class RP2F2DoneProposalReconciliationRunsEveryGate(unittest.TestCase):
    """RP2-F2: a landed proposal whose ``proposed`` transition did not persist is advanced on
    resume only when every gate of a fresh proposal still holds."""

    def setUp(self):
        self.h = Harness(small_backlog())

    def tearDown(self):
        self.h.close()

    def withheld(self, op: str) -> dict:
        entries = [e for e in journal_events(self.h, "reconciliation-withheld") if e["detail"]["op"] == op]
        self.assertTrue(entries)
        return entries[-1]["detail"]

    def test_remote_status_change_withholds_refuses_stale_and_recovers_only_after_an_explicit_rebase(self):
        op = split_done_proposal(self.h)
        self.h.fake.set_status_externally(21, "Blocked")
        with self.assertRaises(StaleRevision):
            fresh(self.h).resume(S, ok_worktree)
        state = self.h.store.load_story(S)
        self.assertEqual((state.phase, state.intent(op).status, state.intent(op).comment_id is not None), ("review-approved", "done", True))
        self.assertIn("stale-revision", self.withheld(op)["reason"])
        self.assertEqual((self.h.fake.calls[:2], "post_comment" in self.h.fake.calls, len(markers(self.h.fake, 21, "proposal"))), (["list_issues", "list_project_items"], False, 1))
        with self.assertRaises(StaleRevision):  # a fresh attempt is refused the same way; nothing was silently advanced meanwhile
            fresh(self.h).propose_evidence(S, self.h.sha, 7, [], "s")
        self.assertEqual(self.h.store.load_story(S).phase, "review-approved")
        self.h.fake.calls = []
        fresh(self.h).rebase_revisions(S, "owner verified the Status change")
        state = fresh(self.h).resume(S, ok_worktree)
        self.assertEqual((state.phase, state.intent(op).status, "post_comment" in self.h.fake.calls, len(markers(self.h.fake, 21, "proposal"))), ("proposed", "done", False, 1))

    def test_pr_objection_withholds_and_records_the_regression_like_a_fresh_attempt(self):
        op = split_done_proposal(self.h)
        self.h.fake.pull_requests[7].reviews.append({"author": "r", "state": "CHANGES_REQUESTED", "submitted_at": "2026-11-06T19:00:00Z"})
        with self.assertRaises(Refused) as ctx:
            fresh(self.h).resume(S, ok_worktree)
        self.assertIn("CHANGES_REQUESTED", str(ctx.exception))
        state = self.h.store.load_story(S)
        self.assertEqual((state.phase, state.approved_sha, state.intent(op).status, state.reviews[-1]["regression"], state.reviews[-1]["verdict"]), ("changes-requested", None, "done", True, "changes-requested"))
        self.assertIn("get_pull_request", self.h.fake.calls)
        self.assertEqual(("post_comment" in self.h.fake.calls, len(markers(self.h.fake, 21, "proposal"))), (False, 1))
        self.assertTrue(journal_events(self.h, "review-regression-on-github"))
        self.withheld(op)
        self.assertEqual(fresh(self.h).resume(S, ok_worktree).phase, "changes-requested")  # a second resume reconciles nothing: the phase moved on
        self.assertEqual(fresh(self.h).authorize_repair(S).phase, "repair-authorized")  # the repair path is open, as after a fresh objection

    def test_dirty_worktree_withholds_and_invalidates_the_evidence(self):
        op = split_done_proposal(self.h)
        (self.h.worktree / "README").write_text("changed after the proposal landed")
        with self.assertRaises(Refused) as ctx:
            fresh(self.h).resume(S, ok_worktree)
        self.assertEqual(ctx.exception.code, "evidence-invalidated")
        state = self.h.store.load_story(S)
        self.assertEqual((state.phase, state.approved_sha, state.intent(op).status, "post_comment" in self.h.fake.calls), ("implemented", None, "done", False))
        self.assertTrue(journal_events(self.h, "unreported-worktree-change"))
        self.withheld(op)
        self.assertEqual(len(markers(self.h.fake, 21, "proposal")), 1)

    def test_expired_run_withholds_before_any_evidence_check_and_cleanup_still_works(self):
        op = split_done_proposal(self.h)
        c = fresh(self.h)
        c.now = lambda: LATER
        state = c.resume(S, ok_worktree)
        self.assertEqual((state.phase, state.intent(op).status), ("review-approved", "done"))
        detail = self.withheld(op)
        self.assertEqual(detail["reason"], "run wall clock budget exceeded")
        self.assertNotIn("post_comment", self.h.fake.calls)
        with self.assertRaises(BudgetExhausted) as ctx:
            c.propose_evidence(S, self.h.sha, 7, [], "s")
        self.assertEqual(ctx.exception.code, "wall-clock-exceeded")
        state = c.cancel(S, "wall clock")
        self.assertEqual((state.phase, len(markers(self.h.fake, 21, "release")), len(markers(self.h.fake, 21, "proposal"))), ("cancelled", 1, 1))

    def test_outage_and_denial_during_the_fresh_evidence_read_fail_closed_and_recover_cleanly(self):
        op = split_done_proposal(self.h)
        self.h.fake.fail_once["list_issues"] = Outage("503")
        with self.assertRaises(Outage):
            fresh(self.h).resume(S, ok_worktree)
        state = self.h.store.load_story(S)
        self.assertEqual((state.phase, state.intent(op).status, "post_comment" in self.h.fake.calls), ("review-approved", "done", False))
        self.assertIn("outage", self.withheld(op)["reason"])
        self.h.fake.fail_once["get_pull_request"] = PermissionDenied("403")
        with self.assertRaises(PermissionDenied):
            fresh(self.h).resume(S, ok_worktree)
        state = self.h.store.load_story(S)
        self.assertEqual((state.phase, state.intent(op).status, "post_comment" in self.h.fake.calls), ("review-approved", "done", False))
        self.assertIn("permission-denied", self.withheld(op)["reason"])
        self.h.fake.calls = []
        state = fresh(self.h).resume(S, ok_worktree)  # transient faults gone: the valid recovery still completes without a repost
        self.assertEqual((state.phase, state.intent(op).status, "post_comment" in self.h.fake.calls, len(markers(self.h.fake, 21, "proposal"))), ("proposed", "done", False, 1))

    def test_duplicate_stable_id_in_the_fresh_snapshot_withholds(self):
        op = split_done_proposal(self.h)
        self.h.fake.add_issue(issue(121, S, "Install (duplicate)", labels=("story",), parent=1, depends_on="OM-01.01", tasks=4), "Ready", S)
        with self.assertRaises(Refused) as ctx:
            fresh(self.h).resume(S, ok_worktree)
        self.assertEqual(ctx.exception.code, "ambiguous-identity")
        state = self.h.store.load_story(S)
        self.assertEqual((state.phase, state.intent(op).status, "post_comment" in self.h.fake.calls), ("review-approved", "done", False))
        self.assertIn("ambiguous-identity", self.withheld(op)["reason"])

    def test_unresolved_authorization_or_missing_pr_withholds_locally_without_transport_calls(self):
        for mutate in (lambda s: s.authorizations.append({"id": "run-1:OM-01.02:9", "role": "reviewer", "purpose": "review", "sha": s.head_sha, "round": None, "issued_at": "t", "status": "revoked", "task_id": None, "reason": "tampered"}),
                       lambda s: s.intent(f"proposal-{self.h.sha[:12]}-pr7").preconditions.pop("pr")):
            h = Harness(small_backlog())
            try:
                self.h.close()
                self.h = h
                op = split_done_proposal(h)
                state = h.store.load_story(S)
                mutate(state)
                h.store.save_story(state)
                h.fake.calls = []
                try:
                    fresh(h).resume(S, ok_worktree)
                except (Refused, StaleRevision):
                    pass
                state = h.store.load_story(S)
                self.assertEqual((state.phase, state.intent(op).status), ("review-approved", "done"))
                self.assertIn("no current approval", self.withheld(op)["reason"])
                self.assertNotIn("post_comment", h.fake.calls)
            finally:
                pass

    def test_clean_state_is_still_reconciled_without_a_repost(self):
        op = split_done_proposal(self.h)
        state = fresh(self.h).resume(S, ok_worktree)
        self.assertEqual((state.phase, state.intent(op).status), ("proposed", "done"))
        self.assertEqual((self.h.fake.calls.count("post_comment"), len(markers(self.h.fake, 21, "proposal"))), (0, 1))
        self.assertIn("get_pull_request", self.h.fake.calls)  # the PR was really re-read

    def test_done_claim_reconciliation_withholds_on_expiry_and_cancel_releases_it(self):
        self.h.reserve()
        state = self.h.store.load_story(S)
        state.phase = "claim-incomplete"
        self.h.store.save_story(state)
        self.h.fake.calls = []
        c = fresh(self.h)
        c.now = lambda: LATER
        state = c.resume(S, ok_worktree)
        self.assertEqual((state.phase, state.intent("claim").status, self.h.fake.calls), ("claim-incomplete", "done", []))
        self.assertEqual(self.withheld("claim")["reason"], "run wall clock budget exceeded")
        state = c.cancel(S, "wall clock")  # the reservation never returned: structurally not launched
        self.assertEqual((state.phase, state.authorizations[0]["status"], len(markers(self.h.fake, 21, "claim")), len(markers(self.h.fake, 21, "release"))), ("cancelled", "not-launched", 1, 1))


if __name__ == "__main__":
    unittest.main()
