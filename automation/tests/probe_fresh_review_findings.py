"""Re-run of the four code findings of the fresh independent review of
8b54fc6974abcf57e9c387b0a55db3f5223a19e8 (PR #107). Adapted from the coordinator's probe
``/tmp/eng01-independent-review.py`` (kept outside the checkout, unchanged): the same steps
in the same order, with every refusal printed instead of aborting the script, plus the
cleanup-failure, zero-marker and duplicate-marker variants. Not a unittest module; run with
``PYTHONPATH=. python3 automation/tests/probe_fresh_review_findings.py``. The transcript against
the reviewed head is ``evidence/fresh-review-8b54fc69-probe-before-2026-11-06.txt``; the
transcript after the repair is ``…-after-2026-11-06.txt``. In-memory GitHub and a real local
git worktree only; nothing touches live GitHub or T3."""

from automation.tests.fake_transport import CrashAfterEffect, small_backlog
from automation.tests.support import IMPLEMENTER, REVIEWER, Harness, ok_worktree, receipt
from automation.tests.test_final_findings import fresh, markers, pending_proposal
from automation.unattended.coordinator import Coordinator
from automation.unattended.errors import Outage, UnattendedError
from automation.unattended.state import Store

S = "OM-01.02"


def attempt(label, fn):
    try:
        r = fn()
        print(f"  {label}: OK -> {r}")
    except UnattendedError as e:
        print(f"  {label}: REFUSED {e.code}: {str(e)[:170]}")


def other_run(h):
    return Coordinator(h.fake, h.policy, Store(h.state_dir, "run-2"), live=True)


def crashed_claim(h):
    h.fake.crash_after_post = True
    try:
        h.reserve()
    except CrashAfterEffect:
        pass


def main() -> None:
    print("F1 claim posted, crash before checkpoint, owner changes Status, restart")
    h = Harness(small_backlog())
    crashed_claim(h)
    h.fake.set_status_externally(21, "Blocked")
    s = fresh(h).resume(S, ok_worktree)
    print("  STALE_CLAIM:", s.phase, "claim markers", len(markers(h.fake, 21, "claim")), "release markers", len(markers(h.fake, 21, "release")), "release intent", s.intent("release") and s.intent("release").status)
    attempt("cancel after the cancellation (terminal, nothing owed)", lambda: fresh(h).cancel(S, "cleanup").phase)
    print("  FOREIGN_CLAIMS (same run excluded):", fresh(h)._active_foreign_claims(21, S))
    print("  OTHER_RUN_FOREIGN_CLAIMS:", other_run(h)._active_foreign_claims(21, S))
    h.close()
    print("F1b release POST fails, restart replays it")
    h = Harness(small_backlog())
    crashed_claim(h)
    h.fake.set_status_externally(21, "Blocked")
    h.fake.fail_once["post_comment"] = Outage("503")
    s = fresh(h).resume(S, ok_worktree)
    print("  after failed release:", s.phase, "release intent", s.intent("release").status, "error", s.blocked.get("github_error", {}).get("code"), "other run sees", len(other_run(h)._active_foreign_claims(21, S)), "claim(s)")
    s = fresh(h).resume(S, ok_worktree)
    print("  after restart:", s.phase, "release intent", s.intent("release").status, "release markers", len(markers(h.fake, 21, "release")), "other run sees", other_run(h)._active_foreign_claims(21, S))
    h.close()
    print("F1c claim never landed (zero markers): no release owed")
    h = Harness(small_backlog())
    h.fake.fail_once["post_comment"] = Outage("503")
    attempt("reserve", lambda: h.reserve().phase)
    h.fake.set_status_externally(21, "Blocked")
    s = fresh(h).resume(S, ok_worktree)
    print("  ", s.phase, "comments on #21:", len(h.fake.comments[21]), "release intent:", s.intent("release"), "release_owed:", s.blocked["release_owed"])
    h.close()
    print("F1d duplicate claim markers: one release, duplicate journaled")
    h = Harness(small_backlog())
    crashed_claim(h)
    h.fake.post_comment(21, h.store.load_story(S).intent("claim").body)
    h.fake.set_status_externally(21, "Blocked")
    s = fresh(h).resume(S, ok_worktree)
    print("  ", s.phase, "claim markers", len(markers(h.fake, 21, "claim")), "release markers", len(markers(h.fake, 21, "release")), "duplicate journaled", any(e["event"] == "duplicate-marker-detected" for e in h.store.read_journal()))
    h.close()

    print("F2 posted proposal + intent done + phase review-approved; run cancelled before story cleanup; restart")
    h = Harness(small_backlog())
    op = pending_proposal(h)
    s = h.store.load_story(S); posted = h.fake.post_comment(21, s.intent(op).body); s.intent(op).status, s.intent(op).comment_id = "done", posted.comment_id; h.store.save_story(s)
    r = h.store.load_run(); r.cancelled, r.stop_reason = True, "crash before story cleanup"; h.store.save_run(r)
    s = fresh(h).resume(S, ok_worktree)
    print("  CANCELLED_DONE_RECONCILIATION:", s.phase, "run.cancelled", h.store.load_run().cancelled, "intent", s.intent(op).status, "journal", [e["detail"]["reason"] for e in h.store.read_journal() if e["event"] == "reconciliation-withheld"])
    attempt("propose after cancel", lambda: fresh(h).propose_evidence(S, h.sha, 7, [], "s").phase)
    print("  cancel_run finishes:", [x["phase"] for x in fresh(h).cancel_run("finish")["cancelled"]], "proposal markers", len(markers(h.fake, 21, "proposal")), "release markers", len(markers(h.fake, 21, "release")))
    h.close()
    print("F2b done claim + phase claim-incomplete + run cancelled: not reconciled to reserved")
    h = Harness(small_backlog())
    h.reserve(); s = h.store.load_story(S); s.phase = "claim-incomplete"; h.store.save_story(s)
    r = h.store.load_run(); r.cancelled, r.stop_reason = True, "crash"; h.store.save_run(r)
    print("  resume ->", fresh(h).resume(S, ok_worktree).phase, "| cancel_run ->", [x["phase"] for x in fresh(h).cancel_run("finish")["cancelled"]], "claim", len(markers(h.fake, 21, "claim")), "release", len(markers(h.fake, 21, "release")))
    h.close()

    print("F3 task id of a terminal story presented for another story (and another role)")
    h = Harness(small_backlog(), allow='["OM-01.02", "OM-01.04"]', max_stories_per_run="2")
    h.claim(); h.coordinator.cancel(S, "done with worker", h.terminal())
    h.reserve("OM-01.04")
    attempt("REPLAYED_TASK_OTHER_STORY bind task-impl-1 as OM-01.04 implementer", lambda: h.coordinator.bind_receipt("OM-01.04", IMPLEMENTER, str(h.worktree), "t3/om-01-02", ok_worktree).phase)
    print("  OM-01.04:", h.store.load_story("OM-01.04").phase, "active_task", h.store.load_story("OM-01.04").active_task, "bound ids run-wide", sorted(h.store.bound_task_ids()))
    attempt("bind a fresh task-impl-2", lambda: h.coordinator.bind_receipt("OM-01.04", receipt(IMPLEMENTER, "task-impl-2"), str(h.worktree), "t3/om-01-02", ok_worktree).phase)
    h.checks("OM-01.04"); h.coordinator.authorize_review("OM-01.04", h.sha)
    attempt("bind reviewer with task-impl-1 (cross-role, cross-story)", lambda: h.coordinator.bind_receipt("OM-01.04", receipt(REVIEWER, "task-impl-1"), worktree_check=ok_worktree).phase)
    attempt("bind reviewer with task-impl-2 (same story, other role)", lambda: h.coordinator.bind_receipt("OM-01.04", receipt(REVIEWER, "task-impl-2"), worktree_check=ok_worktree).phase)
    attempt("bind reviewer with fresh task-review-1", lambda: h.coordinator.bind_receipt("OM-01.04", REVIEWER, worktree_check=ok_worktree).phase)
    h.close()

    print("F4 authorize review, restart after the wall-clock deadline, repeat authorization and bind")
    h = Harness(small_backlog()); h.claim(); h.checks(); issued = h.coordinator.authorize_review(S, h.sha).pending_authorization()["id"]
    c = fresh(h); c.now = lambda: "2099-01-01T00:00:00Z"
    attempt("EXPIRED_AUTHORIZATION authorize_review again", lambda: c.authorize_review(S, h.sha).pending_authorization()["id"])
    print("  pending authorization unchanged:", h.store.load_story(S).pending_authorization()["id"] == issued, "delegated_tasks", h.store.story_counts()["delegated_tasks"])
    attempt("EXPIRED_AUTHORIZATION_BOUND bind reviewer receipt", lambda: c.bind_receipt(S, REVIEWER, worktree_check=ok_worktree).phase)
    s = h.store.load_story(S)
    print("  phase", s.phase, "active_task", s.active_task, "authorization", {k: s.authorizations[-1][k] for k in ("status", "task_id", "cleanup_only")}, "delegated_tasks", h.store.story_counts()["delegated_tasks"])
    attempt("record_review after the deadline", lambda: c.record_review(S, h.sha, "approved", "r", {"taskId": "task-review-1", "status": "result_available"}).phase)
    attempt("cancel WITHOUT terminal evidence", lambda: c.cancel(S, "budget").phase)
    attempt("cancel with implementer evidence", lambda: c.cancel(S, "budget", {"taskId": "task-impl-1", "status": "result_available"}).phase)
    attempt("cancel with the reviewer's terminal evidence", lambda: c.cancel(S, "budget", {"taskId": "task-review-1", "status": "cancelled"}).phase)
    print("  release markers", len(markers(h.fake, 21, "release")), "delegated_tasks", h.store.story_counts()["delegated_tasks"], "bound ids", sorted(h.store.bound_task_ids()))
    h.close()


if __name__ == "__main__":
    main()
