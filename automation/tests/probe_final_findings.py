"""Re-run of the six final-disposition scenarios (PR #107 comment 6686575345) against the
remediated code. Not a unittest module (name deliberately outside ``test*.py``): run with
``PYTHONPATH=. python3 automation/tests/probe_final_findings.py``. The same scenarios against
the reviewed head a0fa769e are recorded in
``_bmad-output/implementation-artifacts/unattended-execution/evidence/final-findings-repro-before-2026-11-06.txt``.
Every scenario uses the in-memory GitHub transport and a real local git worktree; nothing
touches live GitHub or T3."""

from automation.tests.fake_transport import issue, small_backlog
from automation.tests.support import IMPLEMENTER, REVIEWER, Harness, ok_worktree, receipt
from automation.unattended.coordinator import Coordinator
from automation.unattended.eligibility import decide
from automation.unattended.errors import Outage, UnattendedError
from automation.unattended.github import PullRequestRecord
from automation.unattended.state import Store


def markers(fake, n, kind):
    return [c.comment_id for c in fake.comments[n] if c.marker and c.marker["kind"] == kind]


def fresh(h):
    return Coordinator(h.fake, h.policy, Store(h.state_dir, "run-1"), live=True)


def attempt(label, fn):
    try:
        r = fn()
        print(f"  {label}: OK -> {r}")
    except UnattendedError as e:
        print(f"  {label}: REFUSED {e.code}: {str(e)[:160]}")


def pending_proposal(h):
    h.to_review_approved()
    h.fake.pull_requests[7] = PullRequestRecord(7, "OPEN", h.sha, False, (), "SUCCESS")
    h.fake.fail_once["post_comment"] = Outage("503")
    attempt("propose (POST fails once)", lambda: h.coordinator.propose_evidence("OM-01.02", h.sha, 7, [], "s").phase)
    return [i.op for i in h.store.load_story("OM-01.02").pending_advancing_intents()]


def main() -> None:
    print("1 cancellation + pending proposal replay (B1/E1/V1)")
    h = Harness(small_backlog()); c = h.coordinator
    print("  pending:", pending_proposal(h))
    result = c.cancel_run("operator stop")
    st = h.store.load_story("OM-01.02")
    print("  cancel_run -> phase", st.phase, "intents", [(i.op, i.status) for i in st.intents], "awaiting", result["awaiting_worker_termination"])
    attempt("resume (fresh coordinator)", lambda: fresh(h).resume("OM-01.02", ok_worktree).phase)
    attempt("propose after cancel", lambda: fresh(h).propose_evidence("OM-01.02", h.sha, 7, [], "s").phase)
    print("  RESULT phase", h.store.load_story("OM-01.02").phase, "proposal comments", markers(h.fake, 21, "proposal"), "release comments", markers(h.fake, 21, "release"))
    h.close()

    print("2 local review regression + pending proposal replay (E2)")
    h = Harness(small_backlog()); c = h.coordinator
    print("  pending:", pending_proposal(h))
    st = c.record_review("OM-01.02", h.sha, "changes-requested", "second look")
    print("  after local changes-requested: phase", st.phase, "approved_sha", st.approved_sha, "intents", [(i.op, i.status) for i in st.intents if i.kind == "proposal"])
    attempt("resume", lambda: fresh(h).resume("OM-01.02", ok_worktree).phase)
    print("  RESULT phase", h.store.load_story("OM-01.02").phase, "proposal comments", markers(h.fake, 21, "proposal"))
    h.close()

    print("3 reviewer ownership through HEAD recording / invalidation (B2/E3/V3)")
    h = Harness(small_backlog()); c = h.coordinator
    h.claim(); h.checks(); h.request_review()
    st = c.record_head("OM-01.02", h.sha)
    print("  record_head(same sha) during review: phase", st.phase, "active_task", st.active_task)
    attempt("cancel WITHOUT terminal evidence", lambda: c.cancel("OM-01.02", "stop").phase)
    attempt("cancel with IMPLEMENTER evidence", lambda: c.cancel("OM-01.02", "stop", {"taskId": "task-impl-1", "runId": "task-impl-1" + ":run:1", "status": "result_available"}).phase)
    print("  RESULT phase", h.store.load_story("OM-01.02").phase, "release", markers(h.fake, 21, "release"))
    attempt("cancel with REVIEWER terminal evidence", lambda: c.cancel("OM-01.02", "stop", {"taskId": "task-review-1", "runId": "task-review-1" + ":run:1", "status": "cancelled"}).phase)
    h.close()
    h = Harness(small_backlog()); c = h.coordinator
    h.claim(); h.checks(); h.request_review()
    (h.worktree / "README").write_text("edited during review")
    attempt("record_review on dirty tree WITHOUT reviewer evidence", lambda: c.record_review("OM-01.02", h.sha, "approved", "r").phase)
    st = h.store.load_story("OM-01.02"); print("  phase", st.phase, "active_task", st.active_task)
    attempt("cancel with IMPLEMENTER evidence while reviewer active", lambda: c.cancel("OM-01.02", "stop", {"taskId": "task-impl-1", "runId": "task-impl-1" + ":run:1", "status": "result_available"}).phase)
    print("  RESULT phase", h.store.load_story("OM-01.02").phase, "release", markers(h.fake, 21, "release"))
    h.close()

    print("4 crash between claim intent completion and reserved transition (E4)")
    h = Harness(small_backlog()); c = h.coordinator
    saves = []
    orig_save = h.store.save_story
    def spy(state):
        orig_save(state); saves.append((state.phase, state.intent("claim").status if state.intent("claim") else None))
    h.store.save_story = spy
    h.reserve()
    print("  persisted (phase, claim intent) sequence:", saves, "-> split state ('claim-incomplete', 'done') present:", ("claim-incomplete", "done") in saves)
    st = h.store.load_story("OM-01.02"); st.phase = "claim-incomplete"; orig_save(st)  # legacy split state
    attempt("resume on legacy split state", lambda: fresh(h).resume("OM-01.02", ok_worktree).phase)
    print("  RESULT phase", h.store.load_story("OM-01.02").phase, "claim comments", markers(h.fake, 21, "claim"))
    attempt("bind_receipt", lambda: fresh(h).bind_receipt("OM-01.02", IMPLEMENTER, str(h.worktree), "t3/om-01-02", ok_worktree).phase)
    h.close()

    print("5 duplicate stable id (B3/E5)")
    fake = small_backlog()
    fake.add_issue(issue(121, "OM-01.02", "Install (duplicate)", labels=("story",), parent=1, depends_on="OM-01.01", tasks=4), "Ready", "OM-01.02")
    h = Harness(fake); c = h.coordinator
    d = decide("OM-01.02", h.snapshot, h.policy); print("  decide:", d.outcome, d.reasons[0][:80])
    attempt("reserve", lambda: c.reserve("OM-01.02", h.snapshot, "base").phase)
    print("  RESULT state", h.store.load_story("OM-01.02"), "claim comments on #21", markers(fake, 21, "claim"), "on #121", markers(fake, 121, "claim"))
    h.close()
    h = Harness(small_backlog()); c = h.coordinator
    h.claim()
    h.fake.add_issue(issue(121, "OM-01.02", "Install (duplicate)", labels=("story",), parent=1, depends_on="OM-01.01", tasks=4), "Ready", "OM-01.02")
    attempt("resume with the duplicate only in the fresh snapshot", lambda: fresh(h).resume("OM-01.02", ok_worktree).phase)
    h.close()

    print("6 delegation budget before launch (V2)")
    h = Harness(small_backlog(), allow='["OM-01.02", "OM-01.04"]', max_stories_per_run="2", max_delegated_tasks="2"); c = h.coordinator
    h.claim(); h.checks(); h.request_review()
    c.record_review("OM-01.02", h.sha, "changes-requested", "r", h.terminal())
    print("  authorizations issued", h.store.story_counts()["delegated_tasks"], "of", h.policy.max_delegated_tasks)
    attempt("authorize_repair (pre-launch)", lambda: c.authorize_repair("OM-01.02").phase)
    c.cancel("OM-01.02", "stop")
    attempt("reserve second story (pre-launch admission)", lambda: c.reserve("OM-01.04", h.snapshot, "base").phase)
    print("  RESULT OM-01.04 state", h.store.load_story("OM-01.04"), "claim comments on #23", markers(h.fake, 23, "claim"))
    attempt("bind without authorization", lambda: c.bind_receipt("OM-01.04", receipt(IMPLEMENTER, "task-impl-9"), str(h.worktree), "t3/om-01-02", ok_worktree).phase)
    h.close()


if __name__ == "__main__":
    main()
