"""Third repair (spec-eng-01-run-identity-repair): executions are (taskId, runId) pairs.

Covers same-task/new-run repair binding, replayed pairs, wrong run or owner, stale task_status
fields, live/pending child work, reviewer reuse, legacy task-only state, and the audited
reconciliation of a revoked repair authorization whose run completed under the retained
owner task. Inputs are coordinator reports, never platform provenance."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from automation.tests.fake_transport import small_backlog
from automation.tests.support import Harness, IMPLEMENTER, REVIEWER, REVIEW_BRANCH, REVIEW_WORKTREE, evidence, ok_worktree, receipt, run_of
from automation.unattended.coordinator import Coordinator, normalize_task_evidence
from automation.unattended.errors import ReceiptInvalid, Refused
from automation.unattended.state import Store

S = "OM-01.02"
OWNER = "task-impl-1"
# Immutable pre-recovery backup of the historical run (never the mutable live source). The
# generated legacy tests below are authoritative; this replay is optional and machine-specific.
HISTORICAL = Path("/home/gabrianoo/.local/state/owlmast-eng01/repair3-20261107/historical-pre-recovery-backup")
SUPPLIED = Path("/home/gabrianoo/.local/state/owlmast-eng01/repair3-20261107/supplied-original-coordinator-evidence.json")


def status_shaped(task_id, run_id, status="completed", **extra):
    return {"taskId": task_id, "workState": "result_available", "hasPendingChildRuns": False, "latestTerminalRunId": run_id, "latestTerminalStatus": status,
            "childRunId": run_of(task_id, 1), "status": "starting", "summary": "stale first-run summary", **extra}


class TerminalEvidenceShapeTests(unittest.TestCase):
    def test_task_status_shape_uses_latest_terminal_fields_only(self):
        e = normalize_task_evidence(status_shaped(OWNER, run_of(OWNER, 5)))
        self.assertEqual((e["taskId"], e["runId"], e["status"], e["shape"]), (OWNER, run_of(OWNER, 5), "completed", "task_status"))

    def test_live_pending_missing_or_ambiguous_refuse(self):
        for bad, code in ((status_shaped(OWNER, run_of(OWNER, 5), workState="working"), "worker-not-terminal"),
                          (status_shaped(OWNER, run_of(OWNER, 5), hasPendingChildRuns=True), "worker-not-terminal"),
                          (status_shaped(OWNER, None), "run-identity-missing"),
                          (status_shaped(OWNER, run_of(OWNER, 5), runId=run_of(OWNER, 4)), "run-identity-ambiguous"),
                          ({"taskId": OWNER, "runId": run_of(OWNER, 5), "status": "cancel_requested"}, "worker-not-terminal"),
                          ({"taskId": OWNER, "status": "completed"}, "run-identity-missing"),
                          ({"taskId": OWNER}, "worker-not-terminal")):
            with self.assertRaises(Refused) as ctx:
                normalize_task_evidence(bad)
            self.assertEqual(ctx.exception.code, code, bad)


class ExecutionPairTests(unittest.TestCase):
    def setUp(self):
        self.h = Harness(small_backlog())
        self.c = self.h.coordinator

    def tearDown(self):
        self.h.close()

    def to_repair_authorized(self):
        self.h.claim()
        self.h.checks()
        self.h.request_review()
        self.c.record_review(S, self.h.sha, "changes-requested", "r", self.h.terminal())
        return self.c.authorize_repair(S)

    def test_wrong_run_evidence_keeps_ownership(self):
        self.h.claim()
        with self.assertRaises(Refused) as ctx:
            self.c.record_head(S, self.h.sha, evidence(OWNER, ordinal=2))
        self.assertEqual(ctx.exception.code, "run-mismatch")
        self.assertEqual(self.h.store.load_story(S).active_task["runId"], run_of(OWNER, 1))
        state = self.c.record_head(S, self.h.sha, status_shaped(OWNER, run_of(OWNER, 1)))  # stale childRunId/status ignored, latest terminal used
        self.assertIsNone(state.active_task)
        self.assertEqual(state.task_history[-1]["runId"], run_of(OWNER, 1))

    def test_same_task_new_run_binds_a_repair_only_and_old_evidence_cannot_clear_it(self):
        state = self.to_repair_authorized()
        self.assertEqual(state.phase, "repair-authorized")
        state = self.c.bind_receipt(S, receipt(IMPLEMENTER, OWNER, ordinal=2), worktree_check=ok_worktree)
        self.assertEqual((state.phase, state.active_task["taskId"], state.active_task["runId"], state.active_task["retained"]), ("claimed", OWNER, run_of(OWNER, 2), True))
        with self.assertRaises(Refused) as ctx:
            self.c.record_head(S, self.h.sha, evidence(OWNER, ordinal=1))  # the old run's terminal evidence
        self.assertEqual(ctx.exception.code, "run-mismatch")
        self.assertIsNotNone(self.h.store.load_story(S).active_task)
        self.assertEqual(self.c.record_head(S, self.h.sha, evidence(OWNER, ordinal=2)).active_task, None)

    def test_replayed_pair_wrong_owner_and_reviewer_reuse_refuse(self):
        self.to_repair_authorized()
        with self.assertRaises(ReceiptInvalid) as ctx:
            self.c.bind_receipt(S, receipt(IMPLEMENTER, OWNER, ordinal=1), worktree_check=ok_worktree)  # replayed pair
        self.assertEqual(ctx.exception.code, "execution-replayed")
        with self.assertRaises(ReceiptInvalid):
            self.c.bind_receipt(S, {**receipt(IMPLEMENTER, "task-review-1", ordinal=2)}, worktree_check=ok_worktree)  # a reviewer task is never an implementer
        with self.assertRaises(ReceiptInvalid) as ctx:
            self.c.bind_receipt(S, {**IMPLEMENTER, "taskId": "task-impl-7", "runId": run_of("task-impl-7", 2), "childRunId": run_of("task-impl-7", 3)}, worktree_check=ok_worktree)
        self.assertEqual(ctx.exception.code, "run-identity-ambiguous")  # a fresh task naming two different runs is ambiguous
        with self.assertRaises(ReceiptInvalid) as ctx:
            self.c.bind_receipt(S, {k: v for k, v in receipt(IMPLEMENTER, "task-impl-7").items() if k != "runId"}, worktree_check=ok_worktree)
        self.assertEqual(ctx.exception.code, "run-identity-missing")
        self.assertEqual(self.h.store.load_story(S).phase, "repair-authorized")

    def test_retained_receipt_prefers_run_id_over_stale_child_run(self):
        self.to_repair_authorized()
        state = self.c.bind_receipt(S, {**IMPLEMENTER, "taskId": OWNER, "runId": run_of(OWNER, 2), "childRunId": run_of(OWNER, 1)}, worktree_check=ok_worktree)
        self.assertEqual(state.active_task["runId"], run_of(OWNER, 2))

    def test_reviewer_new_run_on_old_task_is_not_fresh_review(self):
        self.h.claim()
        self.h.checks()
        self.h.request_review()
        self.c.record_review(S, self.h.sha, "changes-requested", "r", self.h.terminal())
        self.h.repair(receipt_=receipt(IMPLEMENTER, "task-impl-2"))
        self.h.checks()
        self.c.authorize_review(S, self.h.sha)
        with self.assertRaises(ReceiptInvalid) as ctx:
            self.c.bind_receipt(S, receipt(REVIEWER, "task-review-1", ordinal=2), REVIEW_WORKTREE, REVIEW_BRANCH, ok_worktree)
        self.assertIn("fresh", str(ctx.exception))
        self.assertEqual(self.c.bind_receipt(S, receipt(REVIEWER, "task-review-2"), REVIEW_WORKTREE, REVIEW_BRANCH, ok_worktree).phase, "review-requested")

    def test_other_story_cannot_bind_the_retained_owner(self):
        h = Harness(small_backlog(), allow='["OM-01.02", "OM-01.04"]', max_stories_per_run="2")
        try:
            h.claim()
            h.coordinator.record_head(S, h.sha, h.terminal())
            h.coordinator.cancel(S, "stop")
            h.reserve("OM-01.04")
            with self.assertRaises(ReceiptInvalid):
                h.coordinator.bind_receipt("OM-01.04", receipt(IMPLEMENTER, OWNER, ordinal=2), str(h.worktree), "t3/om-01-02", ok_worktree)
        finally:
            h.close()

    def test_legacy_task_only_history_blocks_an_ordinary_rebind_of_the_retained_owner(self):
        """Second-turn finding 2: a task-only terminal record cannot prove which run ended."""
        self.to_repair_authorized()
        state = self.h.store.load_story(S)
        for rec in state.task_history + state.implementer_receipts:
            rec.pop("runId", None)
        for a in state.authorizations:
            a.pop("run_id", None)
        self.h.store.save_story(state)
        with self.assertRaises(Refused) as ctx:
            self.c.bind_receipt(S, receipt(IMPLEMENTER, OWNER, ordinal=2), worktree_check=ok_worktree)
        self.assertEqual(ctx.exception.code, "run-identity-missing")
        self.assertIn("reconcile-retained-execution", str(ctx.exception))
        state = self.h.store.load_story(S)
        self.assertEqual((state.phase, state.active_task), ("repair-authorized", None))
        self.assertEqual(state.unresolved_authorization()["status"], "pending")
        # an identified predecessor still binds normally
        h2 = Harness(small_backlog())
        try:
            h2.claim(); h2.checks(); h2.request_review()
            h2.coordinator.record_review(S, h2.sha, "changes-requested", "r", h2.terminal())
            h2.coordinator.authorize_repair(S)
            self.assertEqual(h2.coordinator.bind_receipt(S, receipt(IMPLEMENTER, OWNER, ordinal=2), worktree_check=ok_worktree).phase, "claimed")
        finally:
            h2.close()

    def test_legacy_active_task_without_run_id_stays_owned_and_reports_the_missing_fact(self):
        self.h.claim()
        state = self.h.store.load_story(S)
        del state.active_task["runId"]
        self.h.store.save_story(state)
        with self.assertRaises(Refused) as ctx:
            self.c.record_head(S, self.h.sha, evidence(OWNER))
        self.assertEqual(ctx.exception.code, "run-identity-missing")
        self.assertIsNotNone(self.h.store.load_story(S).active_task)


class HistoricalReconciliationTests(unittest.TestCase):
    """The historical situation: implementation run bound and terminal, review terminal,
    repair authorization issued, the repair resumed the retained owner task as a new run
    (no fresh task id), the run was cancelled and the authorization revoked unresolved."""

    def setUp(self):
        self.h = Harness(small_backlog())
        c = self.h.coordinator
        self.h.claim()
        self.h.checks()
        self.h.request_review()
        c.record_review(S, self.h.sha, "changes-requested", "r", self.h.terminal())
        self.auth = c.authorize_repair(S).unresolved_authorization()
        c.cancel_run("qualification stopped: no fresh task id")
        state = self.h.store.load_story(S)
        self.assertEqual(state.unresolved_authorization()["status"], "revoked")
        # legacy task-only history: strip run ids as the historical state has them
        for rec in state.task_history + state.implementer_receipts + state.reviewer_receipts:
            rec.pop("runId", None)
        for a in state.authorizations:
            a.pop("run_id", None)
        self.h.store.save_story(state)
        self.run5 = run_of(OWNER, 5)
        self.receipt = {**IMPLEMENTER, "runId": self.run5, "childRunId": run_of(OWNER, 1), "dispatch": {"runId": self.run5, "messageId": "msg-repair"}, "startedAt": "2099-01-01T00:00:00Z", "completedAt": "2099-01-01T00:02:00Z"}
        self.evidence = status_shaped(OWNER, self.run5)

    def tearDown(self):
        self.h.close()

    def reconcile(self, **overrides):
        kwargs = {"authorization": self.auth["id"], "receipt": self.receipt, "task_evidence": self.evidence, "reason": "repair run completed under the retained owner", "provenance": "original coordinator snapshot, user-supplied"}
        kwargs.update(overrides)
        return self.h.coordinator.reconcile_retained_execution(S, **kwargs)

    def test_reconciliation_resolves_only_the_obligation_and_is_idempotent(self):
        state = self.reconcile()
        auth = state.authorization(self.auth["id"])
        self.assertEqual((auth["status"], auth["task_id"], auth["run_id"], auth["cleanup_only"]), ("consumed", OWNER, self.run5, "retained-execution-reconciled"))
        self.assertEqual((state.phase, state.active_task, state.approved_sha), ("repair-authorized", None, None))
        self.assertTrue(self.h.store.load_run().cancelled)
        self.assertTrue(any(p.name.startswith("OM-01.02.json.bak-") for p in self.h.store.story_path(S).parent.iterdir()))
        self.assertEqual(state.task_history[-1]["runId"], self.run5)
        again = self.reconcile()
        self.assertEqual(len(again.task_history), len(state.task_history))
        self.assertIn("retained-execution-already-reconciled", [e["event"] for e in self.h.store.read_journal()])
        # the story is now cleanly releasable, without approval or new admission
        released = self.h.coordinator.cancel(S, "cleanup after reconciliation")
        self.assertEqual(released.phase, "cancelled")
        self.assertEqual(len([c for c in self.h.fake.comments[21] if c.marker["kind"] == "release"]), 1)
        with self.assertRaises(Refused):
            self.h.coordinator.authorize_repair(S)

    def test_conflicting_old_run_wrong_authorization_or_missing_correlation_refuse(self):
        before = json.loads(self.h.store.story_path(S).read_text())
        cases = [
            ({"receipt": {**self.receipt, "startedAt": "2000-01-01T00:00:00Z"}}, "run-precedes-authorization"),  # an older run of the same task
            ({"receipt": {k: v for k, v in self.receipt.items() if k != "dispatch"}}, "correlation-missing"),
            ({"receipt": {**self.receipt, "dispatch": {"runId": run_of(OWNER, 4)}}}, "run-mismatch"),
            ({"task_evidence": status_shaped(OWNER, run_of(OWNER, 4))}, "run-mismatch"),
            ({"task_evidence": status_shaped(OWNER, self.run5, workState="working")}, "worker-not-terminal"),
            ({"authorization": "eng01:wrong"}, "authorization-mismatch"),
            ({"authorization": self.h.store.load_story(S).authorizations[1]["id"]}, "authorization-mismatch"),  # the review authorization
            ({"receipt": {**self.receipt, "taskId": "task-impl-9"}, "task_evidence": status_shaped("task-impl-9", self.run5)}, "owner-mismatch"),
            ({"receipt": {**self.receipt, "worktree": "/elsewhere"}}, "worktree-mismatch"),
            ({"provenance": ""}, "provenance-missing"),
        ]
        for overrides, code in cases:
            with self.assertRaises(Refused) as ctx:
                self.reconcile(**overrides)
            self.assertEqual(ctx.exception.code, code, overrides)
        self.assertEqual(json.loads(self.h.store.story_path(S).read_text()), before)  # nothing mutated
        self.reconcile()
        with self.assertRaises(Refused) as ctx:
            self.reconcile(receipt={**self.receipt, "runId": run_of(OWNER, 6), "dispatch": {"runId": run_of(OWNER, 6)}}, task_evidence=status_shaped(OWNER, run_of(OWNER, 6)))
        self.assertEqual(ctx.exception.code, "conflicting-evidence")

    def test_timestamp_conflicts_and_invalid_values_never_mutate_initial_or_replayed_recovery(self):
        def snapshot():
            return {str(p.relative_to(self.h.store.root)): p.read_bytes()
                    for p in self.h.store.root.rglob("*") if p.is_file()}

        cases = [
            ({}, {"startedAt": "2000-01-01T00:00:00Z", "completedAt": "1999-01-01T00:00:00Z"}),
            ({}, {"startedAt": "2099-01-01T00:00:01Z"}),
            ({}, {"completedAt": "2099-01-01T00:02:01Z"}),
        ]
        for field in ("startedAt", "completedAt"):
            for invalid in ("bad", "", "2099-01-01T00:00:00", 42, False):
                cases.append(({}, {field: invalid}))
                cases.append(({field: invalid}, {field: self.receipt[field]}))
        # Agreement does not excuse stale runs or completion before start.
        cases.extend([
            ({"startedAt": "2000-01-01T00:00:00Z"}, {"startedAt": "2000-01-01T00:00:00Z"}),
            ({"completedAt": "2098-12-31T23:59:59Z"}, {"completedAt": "2098-12-31T23:59:59Z"}),
        ])
        for replay in (False, True):
            if replay:
                self.reconcile()
            before = snapshot()
            for receipt_change, evidence_change in cases:
                with self.subTest(replay=replay, receipt=receipt_change, evidence=evidence_change):
                    with self.assertRaises(Refused):
                        self.reconcile(receipt={**self.receipt, **receipt_change},
                                       task_evidence={**self.evidence, **evidence_change})
                    self.assertEqual(snapshot(), before)

    def test_matching_timestamp_instants_from_both_sources_are_accepted_and_repeatable(self):
        ev = {**self.evidence, "startedAt": "2099-01-01T01:00:00+01:00",
              "completedAt": "2099-01-01T01:02:00+01:00"}
        first = self.reconcile(task_evidence=ev)
        again = self.reconcile(task_evidence=ev)
        self.assertIsNone(again.unresolved_authorization())
        self.assertEqual(first.task_history, again.task_history)
        self.assertTrue(self.h.store.load_run().cancelled)

    def test_timestamps_may_come_from_terminal_evidence_alone(self):
        rec = {k: v for k, v in self.receipt.items() if k not in ("startedAt", "completedAt")}
        ev = {**self.evidence, "startedAt": self.receipt["startedAt"],
              "completedAt": self.receipt["completedAt"]}
        first = self.reconcile(receipt=rec, task_evidence=ev)
        again = self.reconcile(receipt=rec, task_evidence=ev)
        self.assertEqual(first.task_history, again.task_history)
        self.assertIsNone(again.unresolved_authorization())

    def test_stale_coordinator_cannot_overwrite_the_cancellation(self):
        """Second-turn finding 1: the run is reloaded under the lock; a stale object never saves."""
        stale = Coordinator(self.h.fake, self.h.policy, self.h.store, live=True)
        self.assertTrue(self.h.store.load_run().cancelled)
        state = stale.reconcile_retained_execution(S, self.auth["id"], self.receipt, self.evidence, "r", "p")
        run = self.h.store.load_run()
        self.assertTrue(run.cancelled)
        self.assertEqual(run.stop_reason, "qualification stopped: no fresh task id")
        self.assertEqual(run.delegated_tasks, 3)
        self.assertEqual(state.authorization(self.auth["id"])["status"], "consumed")

    def test_reconciliation_is_cleanup_for_a_stopped_run_only(self):
        h = Harness(small_backlog())
        try:
            h.claim(); h.checks(); h.request_review()
            h.coordinator.record_review(S, h.sha, "changes-requested", "r", h.terminal())
            auth = h.coordinator.authorize_repair(S).unresolved_authorization()
            rec = {**IMPLEMENTER, "runId": run_of(OWNER, 5), "dispatch": {"runId": run_of(OWNER, 5)}, "startedAt": "2099-01-01T00:00:00Z"}
            with self.assertRaises(Refused) as ctx:
                h.coordinator.reconcile_retained_execution(S, auth["id"], rec, status_shaped(OWNER, run_of(OWNER, 5)), "r", "p")
            self.assertEqual(ctx.exception.code, "run-not-stopped")
            self.assertEqual(h.store.load_story(S).unresolved_authorization()["status"], "pending")
        finally:
            h.close()

    def test_repeat_with_changed_status_dispatch_timestamp_target_or_worktree_is_conflicting(self):
        """Second-turn finding 3: identical evidence is idempotent; any change is a conflict."""
        before = self.reconcile()
        n_hist, n_rec = len(before.task_history), len(before.implementer_receipts)
        for overrides, code in (
            ({"task_evidence": status_shaped(OWNER, self.run5, status="failed")}, "conflicting-evidence"),
            ({"receipt": {**self.receipt, "dispatch": {"runId": self.run5, "messageId": "msg-other"}}}, "conflicting-evidence"),
            ({"receipt": {**self.receipt, "startedAt": "2099-01-01T00:00:30Z"}}, "conflicting-evidence"),
            ({"receipt": {**self.receipt, "completedAt": None}}, "conflicting-evidence"),
            ({"receipt": {**self.receipt, "options": {"effort": "medium"}}}, "receipt-invalid"),
            ({"receipt": {**self.receipt, "model": "claude-opus-5-5"}}, "receipt-invalid"),
            ({"receipt": {**self.receipt, "worktree": "/elsewhere"}}, "worktree-mismatch"),
            ({"task_evidence": status_shaped(OWNER, self.run5, workState="working")}, "worker-not-terminal"),
        ):
            with self.assertRaises(Refused) as ctx:
                self.reconcile(**overrides)
            self.assertEqual(ctx.exception.code, code, overrides)
        same = self.reconcile()
        self.assertEqual((len(same.task_history), len(same.implementer_receipts)), (n_hist, n_rec))  # no second record on the identical repeat

    def test_restart_after_reconciliation_keeps_the_resolution(self):
        self.reconcile()
        fresh = Coordinator(self.h.fake, self.h.policy, Store(self.h.state_dir, "run-1"), live=True)
        state = fresh.store.load_story(S)
        self.assertEqual(state.authorization(self.auth["id"])["status"], "consumed")
        self.assertIsNone(state.unresolved_authorization())


@unittest.skipUnless(HISTORICAL.exists() and SUPPLIED.exists(), "immutable historical pre-recovery backup not present on this machine (optional replay; the generated legacy tests above are authoritative)")
class HistoricalCopyTests(unittest.TestCase):
    """Optional, machine-specific replay against a temporary COPY of the immutable pre-recovery
    backup. Never reads the mutable live historical run. The CI replay of the same state runs from
    the committed scrubbed copy (``test_pr115_review_findings.HistoricalFixtureReplayTests``)."""

    def test_supplied_evidence_reconciles_the_historical_copy(self):
        import io
        from contextlib import redirect_stdout

        from automation.tests import lifecycle_smoke as smoke

        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "copy"
            shutil.copytree(HISTORICAL, copy)
            policy_copy = copy / "policy.toml"  # LABELLED EDIT of the temporary copy only: the backup predates targets.reviewer.isolation; the digest change is policy drift (a stop), and reconcile/cancel are cleanup
            policy_copy.write_text(policy_copy.read_text(encoding="utf-8").replace('model = "gpt-6-astra"\n', 'model = "gpt-6-astra"\nisolation = "worktree"\n', 1), encoding="utf-8")
            supplied = json.loads(SUPPLIED.read_text())
            dispatch = json.loads((HISTORICAL / "repair-dispatch.json").read_text())
            rec = {"taskId": supplied["taskId"], "runId": supplied["runId"], "providerInstanceId": supplied["providerInstanceId"], "model": supplied["model"], "options": supplied["options"], "isolation": "worktree",
                   "dispatch": {"runId": dispatch["runId"], "messageId": dispatch["messageId"]}, "startedAt": supplied["startedAt"], "completedAt": supplied["completedAt"]}
            (copy / "r.json").write_text(json.dumps(rec)); (copy / "e.json").write_text(json.dumps(supplied["task_status_snapshot"]))
            argv = ["--dir", str(copy), "--run-id", "eng01-trusted-20261106", "reconcile", "--authorization", supplied["historical_authorization"], "--receipt", str(copy / "r.json"), "--task-evidence", str(copy / "e.json"),
                    "--reason", "repair run ordinal5 completed under the retained owner", "--provenance", supplied["provenance"], "--source", "real"]
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = smoke.main(argv)
            out = json.loads(buf.getvalue())
            self.assertEqual(code, 0, out)
            self.assertEqual((out["phase"], out["authorization"]["status"], out["authorization"]["run_id"]), ("repair-authorized", "consumed", supplied["runId"]))
            self.assertTrue(list((copy / "runs" / "eng01-trusted-20261106" / "stories").glob("*.bak-*")))
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(smoke.main(argv), 0)  # idempotent
            # the immutable backup was not touched
            self.assertEqual(json.loads((HISTORICAL / "runs/eng01-trusted-20261106/stories/OM-99.01.json").read_text())["authorizations"][2]["status"], "revoked")


# Real-transport shape of a deliberately cancelled run (task_cancel): the engineering-only
# cancellation smoke of 2026-11-07 reported task_status status "interrupted", workState
# "result_available", hasPendingChildRuns false and latestTerminalStatus "interrupted" for the
# matching latestTerminalRunId. The ids below reproduce T3's percent-encoded identity format.
T3_TASK = "node:delegated-task:command%3Amcp%3A00000000-0000-4000-8000-000000000000%3Adelegate-task%3Aeng01-active-cancel-smoke"
T3_RUN = "run:thread:thread%3Adelegated-task%3Acommand%253Amcp%253A00000000-0000-4000-8000-000000000000%253Adelegate-task%253Aeng01-active-cancel-smoke:ordinal:1"


def t3_interrupted(task_id=T3_TASK, run_id=T3_RUN, **extra):
    """Raw ``task_status`` of an interrupted (cancelled) run, every field the transport reports."""
    return {"taskId": task_id, "childThreadId": task_id.replace("node:", "thread:", 1), "childRunId": run_id, "childNodeId": task_id,
            "status": "interrupted", "workState": "result_available", "hasPendingChildRuns": False,
            "latestTerminalRunId": run_id, "latestTerminalStatus": "interrupted", "latestTerminalSummary": None, "latestTerminalResultContextTransferId": None,
            "providerInstanceId": "claudeAgent", "model": "claude-fable-5-1", "options": [{"id": "effort", "value": "high"}],
            "summary": "Reporting checkout state, then running the single finite timer command.", "hasPendingQuestion": False, "pendingApproval": None, "waitTimedOut": False, **extra}


class InterruptedTerminalEvidenceTests(unittest.TestCase):
    """The real transport terminates a cancelled run as ``interrupted``: terminal for release and
    cleanup, never a success, never inferred past pending children or a cancel request."""

    def setUp(self):
        self.h = Harness(small_backlog())
        self.c = self.h.coordinator

    def tearDown(self):
        self.h.close()

    def restarted(self) -> Coordinator:
        return Coordinator(self.h.fake, self.h.policy, Store(self.h.state_dir, "run-1"), live=True)

    def test_raw_t3_interrupted_task_status_normalizes_to_the_latest_terminal_pair(self):
        e = normalize_task_evidence(t3_interrupted())
        self.assertEqual(e, {"taskId": T3_TASK, "runId": T3_RUN, "status": "interrupted", "shape": "task_status"})
        e = normalize_task_evidence({"taskId": OWNER, "runId": run_of(OWNER, 1), "status": "interrupted"})
        self.assertEqual((e["status"], e["shape"]), ("interrupted", "normalized"))

    def test_interrupted_with_pending_children_live_work_or_a_cancel_request_refuses(self):
        for bad, code in ((t3_interrupted(hasPendingChildRuns=True), "worker-not-terminal"),
                          (t3_interrupted(workState="working"), "worker-not-terminal"),
                          (t3_interrupted(workState="cancel_requested"), "worker-not-terminal"),
                          (t3_interrupted(latestTerminalStatus="cancel_requested"), "worker-not-terminal"),
                          (t3_interrupted(latestTerminalRunId=None), "run-identity-missing"),
                          (t3_interrupted(runId=T3_RUN + "-other"), "run-identity-ambiguous"),
                          ({"taskId": T3_TASK, "runId": T3_RUN, "status": "cancel_requested"}, "worker-not-terminal"),
                          ({"taskId": T3_TASK, "status": "interrupted"}, "run-identity-missing")):
            with self.assertRaises(Refused) as ctx:
                normalize_task_evidence(bad)
            self.assertEqual(ctx.exception.code, code, bad)

    def test_cancel_releases_the_owned_task_on_interrupted_evidence_for_the_exact_pair(self):
        self.h.claim()
        raw = {**t3_interrupted(OWNER, run_of(OWNER, 1)), "childRunId": run_of(OWNER, 1)}
        with self.assertRaises(Refused) as ctx:  # another run of the same task releases nothing
            self.c.cancel(S, "smoke", {**raw, "latestTerminalRunId": run_of(OWNER, 2)})
        self.assertEqual(ctx.exception.code, "run-mismatch")
        self.assertEqual(self.h.store.load_story(S).active_task["runId"], run_of(OWNER, 1))
        state = self.c.cancel(S, "cancellation smoke", raw)
        self.assertEqual((state.phase, state.active_task), ("cancelled", None))
        record = state.task_history[-1]
        self.assertEqual((record["taskId"], record["runId"], record["status"], record["successful"], record["evidence_shape"], record["operation"]),
                         (OWNER, run_of(OWNER, 1), "interrupted", False, "task_status", "cancelled"))
        self.assertEqual((state.head_sha, state.approved_sha, state.reviews), (None, None, []))  # nothing advanced

    def test_record_task_terminal_then_cleanup_and_restart_keep_the_interrupted_record(self):
        self.h.claim()
        state = self.c.record_task_terminal(S, evidence(OWNER, status="interrupted"))
        self.assertEqual((state.phase, state.active_task, state.task_history[-1]["status"]), ("claimed", None, "interrupted"))
        state = self.restarted().cancel(S, "released after interruption")
        self.assertEqual((state.phase, state.active_task), ("cancelled", None))
        reloaded = Store(self.h.state_dir, "run-1").load_story(S)
        self.assertEqual([r["status"] for r in reloaded.task_history], ["interrupted"])
        self.assertTrue(reloaded.predecessor_terminal(OWNER))  # an interrupted predecessor is terminal, not inferred live
        self.assertEqual(self.restarted().resume(S, ok_worktree).phase, "cancelled")

    def test_interrupted_implementer_evidence_cannot_record_a_head(self):
        self.h.claim()
        for bad in (evidence(OWNER, status="interrupted"), {**t3_interrupted(OWNER, run_of(OWNER, 1)), "childRunId": run_of(OWNER, 1)}):
            with self.assertRaises(Refused) as ctx:
                self.c.record_head(S, self.h.sha, bad)
            self.assertEqual(ctx.exception.code, "worker-interrupted")
            state = self.h.store.load_story(S)
            self.assertEqual((state.phase, state.head_sha, state.active_task["runId"], state.task_history), ("claimed", None, run_of(OWNER, 1), []))
        state = self.c.record_head(S, self.h.sha, self.h.terminal())  # a successful completion of the same pair still advances
        self.assertEqual((state.phase, state.head_sha, state.active_task), ("implemented", self.h.sha, None))

    def test_interrupted_reviewer_evidence_cannot_record_a_verdict(self):
        self.h.claim()
        self.h.checks()
        self.h.request_review()
        with self.assertRaises(Refused) as ctx:
            self.c.record_review(S, self.h.sha, "approved", "report.md", self.h.terminal(status="interrupted"))
        self.assertEqual(ctx.exception.code, "worker-interrupted")
        state = self.h.store.load_story(S)
        self.assertEqual((state.phase, state.approved_sha, state.reviews, state.active_task["taskId"]), ("review-requested", None, [], "task-review-1"))
        state = self.c.cancel(S, "reviewer interrupted", self.h.terminal(status="interrupted"))  # release is the only way out
        self.assertEqual((state.phase, state.active_task, state.task_history[-1]["status"]), ("cancelled", None, "interrupted"))

    def test_cancel_run_releases_an_interrupted_worker_and_keeps_a_pending_children_one_owned(self):
        self.h.claim()
        raw = {**t3_interrupted(OWNER, run_of(OWNER, 1)), "childRunId": run_of(OWNER, 1)}
        result = self.c.cancel_run("budget", {S: {**raw, "hasPendingChildRuns": True}})
        self.assertEqual(([s["phase"] for s in result["cancelled"]], [a["story"] for a in result["awaiting_worker_termination"]]), ([], [S]))
        self.assertEqual(self.h.store.load_story(S).active_task["taskId"], OWNER)
        state = self.restarted().cancel(S, "budget", raw)
        self.assertEqual((state.phase, state.active_task, state.task_history[-1]["status"]), ("cancelled", None, "interrupted"))
