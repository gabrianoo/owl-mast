"""Upgrade and replay repair (fresh independent review of e8fd5c3, findings 1-3): every
advancing consumer of recorded evidence, on every path (direct, release-then-reload, upgrade
from older state, restart replay of pending and completed proposals), passes one common gate:
the latest bound implementer execution and, for a reviewed commit, the reviewer execution
authorized for exactly that SHA must be identified ``(task, run)`` executions bound to exactly
the selected authorization in that role with a successful terminal record.

Part 1 runs the current coordinator over state the BASELINE coordinator (bb4c3ee, whose bug let
an unsuccessful execution record a head or a verdict) produced through its own public APIs
(``legacy_baseline.generate``; committed fixtures, regenerated when the ref is reachable). No
story file of those scenarios is edited by hand except the labelled worktree relocation and the
labelled ``*-done-proposal`` phase reset documented there. Part 2 exercises the identity and
linkage rules of finding 3 on current state with explicitly labelled synthetic mutations.
Part 3 checks the positive controls and that cleanup stays possible."""

import json
import os
from datetime import datetime, timedelta
import tempfile
import unittest
from pathlib import Path

from automation.tests import legacy_baseline as lb
from automation.tests.fake_transport import small_backlog
from automation.tests.support import Harness, evidence, ok_worktree, passing_runner, write_policy
from automation.unattended.coordinator import Coordinator
from automation.unattended.errors import Refused
from automation.unattended.github import PullRequestRecord
from automation.unattended.policy import load_policy
from automation.unattended.state import Store

S = lb.S
PR = lb.PR
OWNER = "task-impl-1"
REVIEW_TASK = "task-review-1"
UNSUCCESSFUL = lb.UNSUCCESSFUL
CODE = {"interrupted": "worker-interrupted", "failed": "worker-unsuccessful", "cancelled": "worker-unsuccessful"}


def proposal_markers(fake) -> list:
    return [c for c in fake.comments.get(21, []) if (c.marker or {}).get("kind") == "proposal"]


class Upgraded:
    """A current Coordinator over one generated legacy scenario."""

    def __init__(self, fixture_dir: Path, name: str):
        self.tmpdir = tempfile.TemporaryDirectory()
        tmp = Path(self.tmpdir.name)
        self.fake, self.state_dir, self.worktree, self.sha, self.meta = lb.materialize(fixture_dir, name, tmp)
        self.policy = load_policy(write_policy(tmp, allow='["OM-01.02"]'))
        # The committed fixtures carry the wall clock of the day they were generated (started_at,
        # last observation). The upgraded coordinator observes a deterministic instant one minute
        # after the latest persisted moment of the scenario, never the host clock, so the matrix
        # gives the same results whenever it runs (the 240-minute wall-clock budget is measured
        # from started_at).
        run = json.loads((self.state_dir / "run-1" / "run.json").read_text(encoding="utf-8"))
        moments = [run["started_at"], run.get("last_observed_at"), (run.get("activation") or {}).get("validated_at")]
        latest = max(datetime.fromisoformat(m.replace("Z", "+00:00")) for m in moments if m)
        self.moment = (latest + timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

    def fresh(self) -> Coordinator:
        return Coordinator(self.fake, self.policy, Store(self.state_dir, "run-1"), now=lambda: self.moment, live=True)

    def story(self):
        return Store(self.state_dir, "run-1").load_story(S)

    def close(self):
        self.tmpdir.cleanup()


class LegacyMatrix:
    """The assertions for every scenario of ``legacy_baseline.scenarios()``; ``fixture_dir``
    is either the committed copy or a fresh generation."""

    def __init__(self, case: unittest.TestCase, fixture_dir: Path):
        self.t, self.dir = case, fixture_dir

    def refused(self, fn, code, **detail):
        with self.t.assertRaises(Refused) as ctx:
            fn()
        self.t.assertEqual(ctx.exception.code, code, str(ctx.exception))
        for k, v in detail.items():
            self.t.assertEqual(ctx.exception.detail.get(k), v, (k, ctx.exception.detail))
        return ctx.exception

    def run_all(self):
        manifest = json.loads((self.dir / "manifest.json").read_text())
        self.t.assertEqual(manifest["ref"], lb.BASELINE_REF)
        self.t.assertEqual(len(manifest["scenarios"]), 44)
        for name in manifest["scenarios"]:
            with self.t.subTest(scenario=name):
                role, status, stage = name.split("-", 2)
                u = Upgraded(self.dir, name)
                try:
                    getattr(self, f"stage_{stage.replace('-', '_')}")(u, role, status)
                    self.cleanup_control(u, status)
                finally:
                    u.close()

    # -- shared expectations ----------------------------------------------------------------
    def expect_unchanged(self, u: Upgraded, phase: str):
        state = u.story()
        self.t.assertEqual((state.phase, state.head_sha, state.active_task), (phase, u.sha, None))
        self.t.assertEqual(json.loads((u.state_dir / "run-1" / "stories" / f"{S}.json").read_text())["task_history"], [dict(r) for r in state.task_history])  # nothing rewritten

    def task_of(self, role):
        return OWNER if role == "implementer" else REVIEW_TASK

    def cleanup_control(self, u: Upgraded, status):
        """Whatever the outcome, an active story can still be cancelled (release posted) by a fresh process."""
        if not u.story().active:
            return  # a completed control that reached proposed is terminal already
        before = len(u.fake.comments[21])
        state = u.fresh().cancel(S, "owner decision")
        self.t.assertEqual((state.phase, state.active_task), ("cancelled", None))
        self.t.assertEqual(len(u.fake.comments[21]), before + 1)
        self.t.assertEqual(u.fresh().resume(S, ok_worktree).phase, "cancelled")

    # -- implementer stages (reviewer never reaches these) ------------------------------------
    def stage_head_recorded(self, u, role, status):
        c = u.fresh()
        if status in UNSUCCESSFUL:
            self.refused(lambda: c.run_checks(S, u.sha, str(u.worktree), passing_runner), CODE[status], role="implementer", task_id=OWNER)
            self.refused(lambda: u.fresh().record_head(S, u.sha), CODE[status])  # the same-sha no-op is gated too
            self.expect_unchanged(u, "implemented")
            self.t.assertEqual(u.story().checks, [])
        else:
            self.t.assertEqual(c.run_checks(S, u.sha, str(u.worktree), passing_runner).phase, "checks-passed")

    def stage_checks_passed(self, u, role, status):
        c = u.fresh()
        if status in UNSUCCESSFUL:
            self.refused(lambda: c.authorize_review(S, u.sha), CODE[status], role="implementer", task_id=OWNER)
            self.expect_unchanged(u, "checks-passed")
            self.t.assertEqual(len(u.story().authorizations), 1)  # no reviewer slot issued
            self.refused(lambda: u.fresh().run_checks(S, u.sha, str(u.worktree), passing_runner), CODE[status])  # re-running checks is no better
        else:
            state = c.authorize_review(S, u.sha)
            self.t.assertEqual(state.phase, "review-authorized")
            u.fresh().record_no_launch(S, {"authorization": state.authorizations[-1]["id"], "reason": "test"})  # leave nothing unresolved for the cleanup control

    def stage_checks_failed(self, u, role, status):
        c = u.fresh()
        if status in UNSUCCESSFUL:
            self.refused(lambda: c.authorize_repair(S), CODE[status], role="implementer", task_id=OWNER)
            self.expect_unchanged(u, "checks-failed")
            state = u.story()
            self.t.assertEqual((state.repair_rounds, len(state.authorizations)), (0, 1))  # no round counted, no slot issued
        else:
            state = c.authorize_repair(S)
            self.t.assertEqual((state.phase, state.repair_rounds), ("repair-authorized", 1))
            u.fresh().record_no_launch(S, {"authorization": state.authorizations[-1]["id"], "reason": "test"})  # leave nothing unresolved for the cleanup control

    def stage_review_approved(self, u, role, status):
        c = u.fresh()
        u.fake.pull_requests[PR] = PullRequestRecord(PR, "OPEN", u.sha, False, (), "SUCCESS")
        if status in UNSUCCESSFUL:
            self.refused(lambda: c.propose_evidence(S, u.sha, PR, [], "s"), CODE[status], role=role, task_id=self.task_of(role))
            self.refused(lambda: u.fresh().record_review(S, u.sha, "approved", "again.md"), CODE[status], role=role)
            self.expect_unchanged(u, "review-approved")
            state = u.story()
            self.t.assertEqual((state.proposal, [i for i in state.intents if i.kind == "proposal"], proposal_markers(u.fake)), (None, [], []))
            self.t.assertEqual(u.fresh().resume(S, ok_worktree).phase, "review-approved")  # restart does not advance either
            self.t.assertEqual(proposal_markers(u.fake), [])
        else:
            self.t.assertEqual(c.propose_evidence(S, u.sha, PR, [], "s").phase, "proposed")
            self.t.assertEqual(len(proposal_markers(u.fake)), 1)

    def stage_pending_proposal(self, u, role, status):
        """Pending intent, nothing landed: a failing gate abandons it and posts nothing."""
        self.t.assertEqual(proposal_markers(u.fake), [])
        state = u.fresh().resume(S, ok_worktree)
        intent = next(i for i in state.intents if i.kind == "proposal")
        if status in UNSUCCESSFUL:
            self.t.assertEqual((state.phase, intent.status, proposal_markers(u.fake)), ("review-approved", "abandoned", []))
            self.t.assertIn(CODE[status], intent.reason)
            self.t.assertEqual(u.fresh().resume(S, ok_worktree).phase, "review-approved")  # a second restart changes nothing
            self.t.assertEqual(proposal_markers(u.fake), [])
            self.refused(lambda: u.fresh().propose_evidence(S, u.sha, PR, [], "s"), CODE[status], role=role)
            self.expect_unchanged(u, "review-approved")
        else:
            self.t.assertEqual((state.phase, intent.status, len(proposal_markers(u.fake))), ("proposed", "done", 1))

    def stage_landed_proposal(self, u, role, status):
        """Pending intent whose comment landed before the crash: the effect stays history, it
        is never reposted, and the transition applies only behind the gate."""
        self.t.assertEqual(len(proposal_markers(u.fake)), 1)
        state = u.fresh().resume(S, ok_worktree)
        intent = next(i for i in state.intents if i.kind == "proposal")
        self.t.assertEqual(len(proposal_markers(u.fake)), 1)  # never a second post, either way
        if status in UNSUCCESSFUL:
            self.t.assertEqual((state.phase, intent.status, intent.comment_id), ("review-approved", "abandoned", None))
            self.t.assertIn(CODE[status], intent.reason)
            self.refused(lambda: u.fresh().propose_evidence(S, u.sha, PR, [], "s"), CODE[status], role=role)
            self.t.assertEqual(len(proposal_markers(u.fake)), 1)
            self.expect_unchanged(u, "review-approved")
        else:
            self.t.assertEqual((state.phase, intent.status, intent.comment_id), ("proposed", "done", proposal_markers(u.fake)[0].comment_id))

    def stage_done_proposal(self, u, role, status):
        """Completed intent whose transition did not persist (labelled synthetic reset): the
        effect stays recorded as done history; the phase advances only behind the gate."""
        self.t.assertEqual(u.meta["synthetic_mutation"][:11], "phase reset")
        self.t.assertEqual(len(proposal_markers(u.fake)), 1)
        state = u.fresh().resume(S, ok_worktree)
        intent = next(i for i in state.intents if i.kind == "proposal")
        self.t.assertEqual((intent.status, intent.comment_id, len(proposal_markers(u.fake))), ("done", proposal_markers(u.fake)[0].comment_id, 1))
        journal = Store(u.state_dir, "run-1").read_journal()
        if status in UNSUCCESSFUL:
            self.t.assertEqual(state.phase, "review-approved")
            withheld = [e for e in journal if e["event"] == "reconciliation-withheld"]
            self.t.assertEqual(len(withheld), 1)
            self.t.assertIn(CODE[status], withheld[0]["detail"]["reason"])
            self.t.assertEqual(u.fresh().resume(S, ok_worktree).phase, "review-approved")
            self.expect_unchanged(u, "review-approved")
        else:
            self.t.assertEqual(state.phase, "proposed")
            self.t.assertEqual([e["event"] for e in journal if e["event"] in ("reconciliation-withheld", "transition-reconciled")], ["transition-reconciled"])


class CommittedLegacyFixturesTests(unittest.TestCase):
    """The full matrix on the committed baseline-generated fixtures (runs everywhere)."""

    def test_manifest_records_the_baseline_bug_it_was_generated_from(self):
        manifest = json.loads((lb.FIXTURE_DIR / "manifest.json").read_text())
        for name, meta in manifest["scenarios"].items():
            role, status, stage = name.split("-", 2)
            with self.subTest(scenario=name):
                record = next(r for r in meta["task_history"] if r["role"] == role)
                self.assertEqual(record["status"], status)
                if status in ("failed", "cancelled"):
                    self.assertIs(record["successful"], True)  # the baseline's contradictory flag, kept as generated
                self.assertTrue(meta["phase"] in ("implemented", "checks-passed", "checks-failed", "review-approved"))
                self.assertEqual(meta["synthetic_mutation"] is not None, stage == "done-proposal")

    def test_full_matrix_on_committed_fixtures(self):
        LegacyMatrix(self, lb.FIXTURE_DIR).run_all()


class RegeneratedLegacyFixturesTests(unittest.TestCase):
    """The same matrix on a fresh generation from the baseline commit (skipped when the commit
    is not reachable, e.g. a shallow clone)."""

    def test_full_matrix_on_a_fresh_generation(self):
        if not lb.ref_reachable():
            if os.environ.get("GITHUB_ACTIONS") == "true" or os.environ.get("OWLMAST_REQUIRE_BASELINE"):  # PR #107 review finding 1: in CI this matrix must run, so a shallow clone is a failure, not a skip
                self.fail(f"baseline {lb.BASELINE_REF[:12]} is not reachable in this checkout; CI must check out the full history (fetch-depth: 0) so the regenerated fixture matrix runs")
            self.skipTest(f"baseline {lb.BASELINE_REF[:12]} not reachable in this clone")
        with tempfile.TemporaryDirectory() as tmp:
            manifest = lb.generate(lb.BASELINE_REF, Path(tmp) / "fixtures")
            committed = json.loads((lb.FIXTURE_DIR / "manifest.json").read_text())
            self.assertEqual(manifest["sha"], committed["sha"])
            strip = lambda m: {k: {kk: vv for kk, vv in v.items() if kk != "worktree_path_at_generation"} for k, v in m["scenarios"].items()}
            self.assertEqual(strip(manifest), strip(committed))  # the committed copy is what the baseline generates today
            LegacyMatrix(self, Path(tmp) / "fixtures").run_all()


class Identity(unittest.TestCase):
    """Finding 3: identity and linkage of the durable record, through the public consumers.
    Every scenario here is an EXPLICITLY LABELLED SYNTHETIC MUTATION of current state."""

    def setUp(self):
        self.h = Harness(small_backlog())
        self.c = self.h.coordinator

    def tearDown(self):
        self.h.close()

    def fresh(self):
        return Coordinator(self.h.fake, self.h.policy, Store(self.h.state_dir, "run-1"), live=True)

    def mutate(self, fn):
        """SYNTHETIC MUTATION of the persisted story file (labelled)."""
        path = Store(self.h.state_dir, "run-1").story_path(S)
        raw = json.loads(path.read_text())
        fn(raw)
        path.write_text(json.dumps(raw))

    def released_implementer(self):
        self.h.claim()
        self.c.record_task_terminal(S, evidence(OWNER, status="completed"))

    def released_reviewer(self):
        self.h.claim(); self.h.checks(); self.h.request_review()
        self.c.record_task_terminal(S, evidence(REVIEW_TASK, status="completed"))

    def record(self, raw, role):
        return next(r for r in raw["task_history"] if r["role"] == role)

    def auth(self, raw, role):
        return next(a for a in raw["authorizations"] if a["role"] == role)

    def assert_refused(self, fn, code, phase):
        with self.assertRaises(Refused) as ctx:
            fn()
        self.assertEqual(ctx.exception.code, code, str(ctx.exception))
        self.assertEqual(Store(self.h.state_dir, "run-1").load_story(S).phase, phase)

    def test_missing_run_identity_never_advances_either_role(self):
        for role in ("implementer", "reviewer"):
            with self.subTest(role=role, where="everywhere"):
                self.setUp()
                try:
                    getattr(self, f"released_{role}")()
                    def strip(raw):  # SYNTHETIC: a task-only legacy history (no run ids anywhere)
                        self.auth(raw, role).pop("run_id")
                        self.record(raw, role).pop("runId")
                        for r in raw["implementer_receipts"] + raw["reviewer_receipts"]:
                            r.pop("runId", None)
                    self.mutate(strip)
                    if role == "implementer":
                        self.assert_refused(lambda: self.fresh().record_head(S, self.h.sha), "run-identity-missing", "claimed")
                    else:
                        self.assert_refused(lambda: self.fresh().record_review(S, self.h.sha, "approved", "r.md"), "run-identity-missing", "review-requested")
                finally:
                    self.tearDown()
            with self.subTest(role=role, where="record only"):
                self.setUp()
                try:
                    getattr(self, f"released_{role}")()
                    self.mutate(lambda raw: self.record(raw, role).pop("runId"))  # SYNTHETIC: the authorization names a run, the record does not
                    if role == "implementer":
                        self.assert_refused(lambda: self.fresh().record_head(S, self.h.sha), "no-successful-execution", "claimed")
                    else:
                        self.assert_refused(lambda: self.fresh().record_review(S, self.h.sha, "approved", "r.md"), "no-successful-execution", "review-requested")
                finally:
                    self.tearDown()

    def test_contradictory_or_missing_authorization_linkage_refuses(self):
        for role in ("implementer", "reviewer"):
            for label, change in (("wrong authorization", lambda r: r.__setitem__("authorization", "run-1:OM-01.02:999")),
                                  ("missing authorization", lambda r: r.pop("authorization")),
                                  ("null authorization", lambda r: r.__setitem__("authorization", None)),
                                  ("wrong role", lambda r: r.__setitem__("role", "reviewer" if r["role"] == "implementer" else "implementer"))):
                with self.subTest(role=role, mutation=label):
                    self.setUp()
                    try:
                        getattr(self, f"released_{role}")()
                        self.mutate(lambda raw: change(self.record(raw, role)))  # SYNTHETIC
                        if role == "implementer":
                            self.assert_refused(lambda: self.fresh().record_head(S, self.h.sha), "conflicting-evidence", "claimed")
                        else:
                            self.assert_refused(lambda: self.fresh().record_review(S, self.h.sha, "approved", "r.md"), "conflicting-evidence", "review-requested")
                    finally:
                        self.tearDown()

    def test_another_run_of_the_same_task_or_a_missing_status_proves_nothing(self):
        self.released_implementer()
        self.mutate(lambda raw: self.record(raw, "implementer").__setitem__("runId", "task-impl-1:run:2"))  # SYNTHETIC: terminal record of another run
        self.assert_refused(lambda: self.fresh().record_head(S, self.h.sha), "no-successful-execution", "claimed")
        self.mutate(lambda raw: (self.record(raw, "implementer").__setitem__("runId", "task-impl-1:run:1"), self.record(raw, "implementer").pop("status")))  # SYNTHETIC: no status
        self.assert_refused(lambda: self.fresh().record_head(S, self.h.sha), "worker-unsuccessful", "claimed")
        self.mutate(lambda raw: (self.record(raw, "implementer").__setitem__("status", "completed"), self.record(raw, "implementer").__setitem__("successful", None)))  # legacy: flag absent (null) is read from the status
        self.assertEqual(self.fresh().record_head(S, self.h.sha).phase, "implemented")

    def test_proposal_and_replay_consumers_validate_identity_and_linkage(self):
        """A review-approved story whose implementer record was unlinked after the fact: direct
        proposal, pending replay and completed-intent reconciliation all refuse without posting."""
        self.h.to_review_approved()
        self.h.fake.pull_requests[PR] = PullRequestRecord(PR, "OPEN", self.h.sha, False, (), "SUCCESS")
        self.mutate(lambda raw: self.record(raw, "implementer").__setitem__("authorization", "run-1:OM-01.02:999"))  # SYNTHETIC
        self.assert_refused(lambda: self.fresh().propose_evidence(S, self.h.sha, PR, [], "s"), "conflicting-evidence", "review-approved")
        self.assertEqual(proposal_markers(self.h.fake), [])
        # pending replay (SYNTHETIC intent record, as the baseline persists one before its POST)
        def pending(raw):
            raw["intents"].append({"op": f"proposal-{self.h.sha[:12]}-pr{PR}", "kind": "proposal", "marker": {"kind": "proposal", "run": "run-1", "story": S, "op": f"proposal-{self.h.sha[:12]}-pr{PR}", "sha": self.h.sha, "pr": str(PR)},
                                   "body": "x", "preconditions": {"sha": self.h.sha, "pr": PR, "revisions": raw["revisions"]}, "status": "pending", "reason": None, "comment_id": None, "created_at": "2026-11-07T00:00:00Z", "completed_at": None})
        self.mutate(pending)
        state = self.fresh().resume(S, ok_worktree)
        self.assertEqual((state.phase, state.intents[-1].status, proposal_markers(self.h.fake)), ("review-approved", "abandoned", []))
        self.assertIn("conflicting-evidence", state.intents[-1].reason)
        # completed intent whose transition did not persist (SYNTHETIC)
        self.mutate(lambda raw: raw["intents"][-1].update({"status": "done", "comment_id": 4242}))
        state = self.fresh().resume(S, ok_worktree)
        self.assertEqual((state.phase, state.intents[-1].status, state.intents[-1].comment_id, proposal_markers(self.h.fake)), ("review-approved", "done", 4242, []))
        self.assertIn("conflicting-evidence", [e for e in Store(self.h.state_dir, "run-1").read_journal() if e["event"] == "reconciliation-withheld"][-1]["detail"]["reason"])
        self.assertEqual(self.fresh().cancel(S, "cleanup").phase, "cancelled")

    def test_successful_execution_helper_requires_every_identity(self):
        self.released_implementer()
        state = Store(self.h.state_dir, "run-1").load_story(S)
        ok = state.successful_execution(OWNER, "task-impl-1:run:1", "implementer", "run-1:OM-01.02:1")
        self.assertTrue(ok and ok["successful"])
        for args in ((OWNER, None, "implementer", "run-1:OM-01.02:1"), (None, "task-impl-1:run:1", "implementer", "run-1:OM-01.02:1"), (OWNER, "task-impl-1:run:1", "implementer", None),
                     (OWNER, "task-impl-1:run:1", "implementer", ""), (OWNER, "task-impl-1:run:1", "reviewer", "run-1:OM-01.02:1"), (OWNER, "task-impl-1:run:1", "implementer", "run-1:OM-01.02:2"),
                     (OWNER, "task-impl-1:run:2", "implementer", "run-1:OM-01.02:1"), ("task-impl-2", "task-impl-1:run:1", "implementer", "run-1:OM-01.02:1")):
            self.assertIsNone(state.successful_execution(*args), args)


class PositiveControls(unittest.TestCase):
    """Current-state lifecycles keep working end to end through every gated consumer, direct
    and across restarts, and the two-repair ceiling is unchanged."""

    def test_completed_lifecycle_through_every_gate_across_restarts(self):
        h = Harness(small_backlog())
        try:
            fresh = lambda: Coordinator(h.fake, h.policy, Store(h.state_dir, "run-1"), live=True)
            h.claim()
            h.coordinator.record_task_terminal(S, evidence(OWNER, status="completed"))
            self.assertEqual(fresh().record_head(S, h.sha).phase, "implemented")
            self.assertEqual(fresh().run_checks(S, h.sha, str(h.worktree), passing_runner).phase, "checks-passed")
            self.assertEqual(fresh().authorize_review(S, h.sha).phase, "review-authorized")
            h.request_review()
            fresh().record_task_terminal(S, evidence(REVIEW_TASK, status="result_available"))
            self.assertEqual(fresh().record_review(S, h.sha, "approved", "r.md").phase, "review-approved")
            h.fake.pull_requests[PR] = PullRequestRecord(PR, "OPEN", h.sha, False, (), "SUCCESS")
            self.assertEqual(fresh().resume(S, ok_worktree).phase, "review-approved")
            self.assertEqual(fresh().propose_evidence(S, h.sha, PR, ["OM-01.02-T1"], "s").phase, "proposed")
            self.assertEqual(len(proposal_markers(h.fake)), 1)
        finally:
            h.close()

    def test_repair_ceiling_and_latest_bound_implementer_still_govern(self):
        from automation.tests.support import IMPLEMENTER, failing_runner, git_commit, receipt
        h = Harness(small_backlog())
        try:
            h.claim(); h.checks(runner=failing_runner)
            self.assertEqual(h.repair(receipt_=receipt(IMPLEMENTER, "task-impl-2")).phase, "claimed")
            sha2 = git_commit(h.worktree, "fix1")
            h.coordinator.record_head(S, sha2, evidence("task-impl-2", status="completed"))
            self.assertEqual(h.coordinator.run_checks(S, sha2, str(h.worktree), failing_runner).phase, "checks-failed")
            self.assertEqual(h.repair(receipt_=receipt(IMPLEMENTER, "task-impl-3")).phase, "claimed")
            sha3 = git_commit(h.worktree, "fix2")
            h.coordinator.record_head(S, sha3, evidence("task-impl-3", status="completed"))
            self.assertEqual(h.coordinator.run_checks(S, sha3, str(h.worktree), failing_runner).phase, "checks-failed")
            self.assertEqual(h.coordinator.authorize_repair(S).phase, "blocked")  # third round: blocked, as before
        finally:
            h.close()


if __name__ == "__main__":
    unittest.main()
