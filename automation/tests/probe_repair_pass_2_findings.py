"""Re-run of the two code findings of the fresh independent review of
0f893d4255eafd79cb7654e9f41944dd3d1af553 (PR #107, repair pass 1). Adapted from the reviewer's
probe ``/tmp/eng01-review-0f893d-probes.py`` (kept outside the checkout, unchanged): the same
steps in the same order, with every refusal printed instead of aborting the script, plus the
resolution paths (late receipt for cleanup, no-launch attestation), the restart and the
recovery variants. Not a unittest module; run with
``PYTHONPATH=. python3 automation/tests/probe_repair_pass_2_findings.py``. The reviewer's own
transcript against the reviewed head is
``evidence/fresh-review-0f893d42-probe-before-2026-11-06.txt``; the transcript after the repair
is ``…-after-2026-11-06.txt``. In-memory GitHub and a real local git worktree only; nothing
touches live GitHub or T3."""

import json

from automation.tests.fake_transport import small_backlog
from automation.tests.support import IMPLEMENTER, REVIEWER, Harness, git_commit, ok_worktree, passing_runner, receipt
from automation.tests.test_final_findings import fresh, markers
from automation.unattended.errors import UnattendedError
from automation.unattended.github import PullRequestRecord

S = "OM-01.02"


def attempt(label, fn):
    try:
        r = fn()
        print(f"  {label}: OK -> {r}")
        return r
    except UnattendedError as e:
        print(f"  {label}: REFUSED {e.code}: {str(e)[:150]}")
        return e


def split(h):
    h.to_review_approved()
    h.fake.pull_requests[7] = PullRequestRecord(7, "OPEN", h.sha, False, [], "SUCCESS")
    h.coordinator.propose_evidence(S, h.sha, 7, [], "evidence")
    s = h.store.load_story(S)
    s.phase = "review-approved"
    h.store.save_story(s)
    h.fake.calls = []


def main() -> None:
    print("RP2-F2 done proposal (intent done, phase review-approved) + current evidence changed; resume")
    for variant in ("revision", "objection", "dirty", "expired", "outage", "duplicate-id"):
        h = Harness(small_backlog())
        split(h)
        c = fresh(h)
        if variant == "revision":
            h.fake.set_status_externally(21, "Blocked")
        elif variant == "objection":
            h.fake.pull_requests[7].reviews.append({"author": "r", "state": "CHANGES_REQUESTED", "submitted_at": "2026-11-06T19:00:00Z"})
        elif variant == "dirty":
            (h.worktree / "README").write_text("changed")
        elif variant == "expired":
            c.now = lambda: "2099-01-01T00:00:00Z"
        elif variant == "outage":
            from automation.unattended.errors import Outage
            h.fake.fail_once["list_issues"] = Outage("503")
        elif variant == "duplicate-id":
            from automation.tests.fake_transport import issue
            h.fake.add_issue(issue(121, S, "Install (duplicate)", labels=("story",), parent=1, depends_on="OM-01.01", tasks=4), "Ready", S)
        h.fake.calls = []
        try:
            result = c.resume(S, ok_worktree).phase
        except Exception as e:  # the reviewer's probe prints the exception type and message
            result = type(e).__name__ + ":" + str(e)[:110]
        s = h.store.load_story(S)
        withheld = [e["detail"]["reason"][:60] for e in h.store.read_journal() if e["event"] == "reconciliation-withheld"]
        print(json.dumps({"case": "done_proposal_" + variant, "result": result, "persisted_phase": s.phase, "intent": s.intents[-1].status, "proposal_markers": len(markers(h.fake, 21, "proposal")), "calls": h.fake.calls, "withheld": withheld}))
        if variant == "outage":
            h.fake.calls = []
            attempt("  resume after the outage cleared (clean recovery, no repost)", lambda: (fresh(h).resume(S, ok_worktree).phase, "post_comment" in h.fake.calls, len(markers(h.fake, 21, "proposal"))))
        h.close()

    print("RP2-F1 reserve -> authorized launch, receipt delayed -> cancel / cancel_run / block / invalidate_review")
    for variant in ("cancel", "cancel_run", "block", "invalidate_review"):
        h = Harness(small_backlog(), allow='["OM-01.02", "OM-01.04"]', max_stories_per_run="2")
        if variant == "invalidate_review":
            h.claim(); h.checks(); auth = h.coordinator.authorize_review(S, h.sha).pending_authorization()
            h.coordinator.record_head(S, "b" * 40)
            rec = REVIEWER
        else:
            auth = h.reserve().pending_authorization(); rec = IMPLEMENTER
            if variant == "cancel_run":
                r = h.coordinator.cancel_run("stop after launch before receipt")
                print("  cancel_run ->", json.dumps(r["awaiting_worker_termination"]))
            elif variant == "block":
                attempt("block", lambda: h.coordinator.block(S, "stop after launch before receipt").phase)
            else:
                attempt("cancel", lambda: h.coordinator.cancel(S, "stop after launch before receipt").phase)
        s = h.store.load_story(S)
        print(json.dumps({"case": "after_stop_" + variant, "phase": s.phase, "active_task": s.active_task, "authorization": {k: s.authorizations[-1][k] for k in ("id", "status", "sha", "task_id")}, "release_markers": len(markers(h.fake, 21, "release")), "block_markers": len(markers(h.fake, 21, "block"))}))
        attempt("reserve OM-01.04 while unresolved", lambda: h.reserve("OM-01.04").phase)
        attempt("late bind with a WRONG authorization id", lambda: fresh(h).bind_receipt(S, rec, str(h.worktree), "t3/om-01-02", ok_worktree, authorization="run-1:OM-01.02:9").phase)
        attempt("late bind with the exact authorization id", lambda: fresh(h).bind_receipt(S, rec, str(h.worktree), "t3/om-01-02", ok_worktree, authorization=auth["id"]).phase)
        s = h.store.load_story(S)
        print(json.dumps({"case": "late_receipt_" + variant, "phase": s.phase, "active_task": s.active_task, "authorization": {k: s.authorizations[-1].get(k) for k in ("id", "status", "sha", "task_id", "cleanup_only")}, "receipt_sha": (s.reviewer_receipts or [{}])[-1].get("sha"), "delegated_tasks": h.store.story_counts()["delegated_tasks"]}))
        attempt("cancel WITHOUT terminal evidence", lambda: fresh(h).cancel(S, "finish").phase)
        attempt("cancel with the task's terminal evidence", lambda: fresh(h).cancel(S, "finish", {"taskId": rec["taskId"], "status": "cancelled"}).phase)
        print("  release markers", len(markers(h.fake, 21, "release")), "delegated_tasks", h.store.story_counts()["delegated_tasks"])
        attempt("reserve OM-01.04 after resolution", lambda: fresh(h).reserve("OM-01.04", h.snapshot, "c5d9d2e").phase)
        h.close()

    print("RP2-F1 no-launch attestation instead of a receipt")
    h = Harness(small_backlog(), allow='["OM-01.02", "OM-01.04"]', max_stories_per_run="2")
    auth = h.reserve().pending_authorization()
    attempt("cancel", lambda: h.coordinator.cancel(S, "stop").phase)
    attempt("record_no_launch with the wrong id", lambda: h.coordinator.record_no_launch(S, {"authorization": "run-1:OM-01.02:9"}).phase)
    attempt("record_no_launch with the exact id", lambda: {k: v for k, v in h.coordinator.record_no_launch(S, {"authorization": auth["id"], "reason": "delegate_task never called"}).authorizations[0].items() if k in ("status", "resolution")})
    attempt("record_no_launch again (applies once)", lambda: h.coordinator.record_no_launch(S, {"authorization": auth["id"]}).phase)
    attempt("late bind after the attestation", lambda: fresh(h).bind_receipt(S, IMPLEMENTER, str(h.worktree), "t3/om-01-02", ok_worktree, authorization=auth["id"]).phase)
    attempt("cancel after the attestation", lambda: fresh(h).cancel(S, "stop").phase)
    print("  release markers", len(markers(h.fake, 21, "release")), "delegated_tasks", h.store.story_counts()["delegated_tasks"])
    attempt("reserve OM-01.04", lambda: fresh(h).reserve("OM-01.04", h.snapshot, "c5d9d2e").phase)
    h.close()

    print("RP2-F1 authorize review A -> new head B before receipt -> B's review; A's late receipt")
    h = Harness(small_backlog()); h.claim(); h.checks()
    old = h.coordinator.authorize_review(S, h.sha).pending_authorization(); old_sha = h.sha
    h.sha = git_commit(h.worktree, "newhead"); h.coordinator.record_head(S, h.sha)
    s = h.store.load_story(S)
    print(json.dumps({"after_record_head_B": {"phase": s.phase, "old_authorization": {k: s.authorizations[-1][k] for k in ("id", "status", "sha")}}}))
    attempt("run_checks(B) while A unresolved", lambda: h.coordinator.run_checks(S, h.sha, str(h.worktree), passing_runner).phase)
    attempt("authorize_review(B) while A unresolved", lambda: h.coordinator.authorize_review(S, h.sha).pending_authorization())
    attempt("A's late receipt binds (cleanup only)", lambda: h.coordinator.bind_receipt(S, REVIEWER, worktree_check=ok_worktree, authorization=old["id"]).phase)
    s = h.store.load_story(S)
    print(json.dumps({"after_A_receipt": {"phase": s.phase, "bound_receipt_sha": s.reviewer_receipts[-1]["sha"], "bound_authorization": s.reviewer_receipts[-1]["authorization"], "active_task": s.active_task}}))
    attempt("record_review(B, approved) with A's reviewer evidence", lambda: h.coordinator.record_review(S, h.sha, "approved", "report for old commit", {"taskId": REVIEWER["taskId"], "status": "result_available"}).phase)
    attempt("record_task_terminal(A)", lambda: h.coordinator.record_task_terminal(S, {"taskId": REVIEWER["taskId"], "status": "result_available"}).active_task)
    attempt("run_checks(B)", lambda: h.coordinator.run_checks(S, h.sha, str(h.worktree), passing_runner).phase)
    new = attempt("authorize_review(B)", lambda: h.coordinator.authorize_review(S, h.sha).pending_authorization())
    attempt("bind a fresh reviewer to B", lambda: h.coordinator.bind_receipt(S, receipt(REVIEWER, "task-review-2"), worktree_check=ok_worktree, authorization=new["id"]).phase)
    attempt("record_review(B, approved) with the new reviewer's evidence", lambda: h.coordinator.record_review(S, h.sha, "approved", "report for B", {"taskId": "task-review-2", "status": "result_available"}).phase)
    s = h.store.load_story(S)
    print(json.dumps({"case": "late_old_review_cannot_consume_new_authorization", "old_sha": old_sha, "new_sha": h.sha, "old_authorization": old["id"], "new_authorization": new["id"], "phase": s.phase, "approved_sha": s.approved_sha, "reviewer_receipt_shas": [r["sha"] for r in s.reviewer_receipts], "delegated_tasks": h.store.story_counts()["delegated_tasks"]}))
    h.close()


if __name__ == "__main__":
    main()
