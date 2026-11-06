"""The per-story state machine the T3 coordinator drives.

Phases (``state.PHASES``)::

    claimed -> implemented -> checks-passed -> review-requested -> review-approved -> proposed
                 ^              |                                   |
                 |          checks-failed --repair (<=2)--+  changes-requested --repair (<=2)--+
                 +--------------------------------------------------------------------------+
    any active phase -> blocked | cancelled

GitHub effects are limited to marker comments (claim, release, block, proposal) and Project
Status writes (``In progress``, ``Blocked``, ``In review``, and ``Ready`` restored on cancel).
Every effect goes through a write-ahead intent and the check-then-write-then-verify
protocol documented in ``github.py``. ``Done`` is never written here.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

from .backlog import Snapshot
from .eligibility import Decision, decide
from .errors import BudgetExhausted, Conflict, Refused, StaleRevision, TransportError
from .github import Transport, render_marker
from .policy import Policy
from .receipts import validate_receipt
from .state import ACTIVE_PHASES, Intent, Store, StoryState, utcnow

WorktreeCheck = Callable[[str, str], tuple[bool, str]]


def git_worktree_check(path: str, branch: str) -> tuple[bool, str]:
    """Default identity check: the path exists and is checked out on ``branch``."""
    if not Path(path).is_dir():
        return False, f"worktree path {path} does not exist"
    try:
        out = subprocess.run(["git", "-C", path, "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"git failed: {exc}"
    current = out.stdout.strip()
    if out.returncode != 0 or current != branch:
        return False, f"worktree is on {current!r}, expected {branch!r}"
    return True, "ok"


def git_head(path: str) -> str | None:
    try:
        out = subprocess.run(["git", "-C", path, "rev-parse", "HEAD"], capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


class Coordinator:
    def __init__(self, transport: Transport, policy: Policy, store: Store, now: Callable[[], str] = utcnow):
        self.transport, self.policy, self.store, self.now = transport, policy, store, now
        self.run = store.ensure_run(policy.repo_slug, policy.digest)

    # -- helpers -------------------------------------------------------------------------
    def _story(self, story: str) -> StoryState:
        state = self.store.load_story(story)
        if state is None:
            raise Refused(f"{story} has no state in run {self.store.run_id}")
        return state

    def _require_phase(self, state: StoryState, *phases: str) -> None:
        if state.phase not in phases:
            raise Refused(f"{state.story} is {state.phase}; this operation needs {phases}", phase=state.phase)

    def _budget(self, *, delegation: bool = False, claim: bool = False) -> None:
        run = self.run
        if run.cancelled:
            raise BudgetExhausted("run is cancelled", stop_reason=run.stop_reason)
        started = run.started_at
        if datetime.fromisoformat(self.now().replace("Z", "+00:00")) - datetime.fromisoformat(started.replace("Z", "+00:00")) > timedelta(minutes=self.policy.max_wall_clock_minutes):
            raise BudgetExhausted(f"wall clock budget of {self.policy.max_wall_clock_minutes} minutes exceeded")
        if delegation and run.delegated_tasks + 1 > self.policy.max_delegated_tasks:
            raise BudgetExhausted(f"delegated task budget {self.policy.max_delegated_tasks} exhausted")
        if claim:
            if run.stories_claimed + 1 > self.policy.max_stories_per_run:
                raise BudgetExhausted(f"story budget {self.policy.max_stories_per_run} exhausted")
            active = [s.story for s in self.store.list_stories() if s.active]
            if len(active) + 1 > self.policy.max_concurrent_implementers:
                raise Refused(f"another story is active in this run: {active}", active=active)

    def _count_delegation(self) -> None:
        self.run.delegated_tasks += 1
        self.store.save_run(self.run)

    def _active_foreign_claims(self, state_issue: int, story: str) -> list[dict]:
        comments = self.transport.list_comments(state_issue)
        claims: dict[str, dict] = {}
        released: set[str] = set()
        for c in comments:
            m = c.marker
            if not m or m.get("story") != story:
                continue
            run = m.get("run", "")
            if m.get("kind") == "claim":
                claims[run] = m
            elif m.get("kind") in ("release", "block", "proposal"):
                released.add(run)
        return [m for run, m in claims.items() if run != self.store.run_id and run not in released]

    def _post_marked(self, state: StoryState, kind: str, body: str, **extra: str) -> Intent:
        """Idempotent marked comment with a write-ahead intent."""
        seq = sum(1 for i in state.intents if i.kind == kind) + 1
        marker = {"kind": kind, "run": self.store.run_id, "story": state.story, "seq": str(seq), **extra}
        existing = next((i for i in state.intents if i.marker == marker), None)
        intent = existing or Intent(f"{kind}-{seq}", kind, marker)
        if existing is None:
            state.intents.append(intent)
            self.store.save_story(state)
            self.store.journal(state.story, "intent-recorded", {"intent": intent.intent_id, "marker": marker})
        if intent.status == "done":
            return intent
        marker_text = render_marker(**marker)
        found = [c for c in self.transport.list_comments(state.issue) if c.marker == marker]
        if not found:
            posted = self.transport.post_comment(state.issue, f"{marker_text}\n{body}")
            found = [c for c in self.transport.list_comments(state.issue) if c.marker == marker]
            if not found:
                raise Conflict(f"comment {marker} was posted (id {posted.comment_id}) but is not readable back", comment_id=posted.comment_id)
            self.store.journal(state.story, "comment-posted", {"intent": intent.intent_id, "comment_id": posted.comment_id})
        else:
            self.store.journal(state.story, "comment-adopted", {"intent": intent.intent_id, "comment_id": found[0].comment_id})
        if len(found) > 1:
            self.store.journal(state.story, "duplicate-marker-detected", {"intent": intent.intent_id, "comment_ids": [c.comment_id for c in found]})
            raise Conflict(f"marker {marker} appears {len(found)} times; a concurrent writer posted the same event", comment_ids=[c.comment_id for c in found])
        intent.status, intent.comment_id, intent.completed_at = "done", found[0].comment_id, self.now()
        self.store.save_story(state)
        return intent

    def _write_status(self, state: StoryState, target: str, expected_current: str) -> None:
        info = self.transport.project_info()
        option = info.status_options.get(target)
        if option is None:
            raise Refused(f"project has no Status option {target!r}")
        before = self.transport.get_project_item(state.item_id)
        if before.status != expected_current:
            raise StaleRevision(f"{state.story} Status is {before.status!r}, expected {expected_current!r} before writing {target!r}", observed=before.status, expected=expected_current)
        if state.item_updated_at and before.updated_at != state.item_updated_at:
            raise StaleRevision(f"{state.story} Project item changed at {before.updated_at} after our last read {state.item_updated_at}", observed=before.updated_at, expected=state.item_updated_at)
        self.store.journal(state.story, "status-write", {"from": expected_current, "to": target, "pre_updated_at": before.updated_at})
        self.transport.set_project_status(state.item_id, option)
        after = self.transport.get_project_item(state.item_id)
        if after.status != target:
            raise Conflict(f"{state.story} Status reads {after.status!r} after writing {target!r}", observed=after.status, expected=target)
        state.status_written, state.item_updated_at = target, after.updated_at
        self.store.save_story(state)
        self.store.journal(state.story, "status-verified", {"status": target, "updated_at": after.updated_at})

    # -- operations ----------------------------------------------------------------------
    def claim(self, story: str, snapshot: Snapshot, receipt: dict, worktree_path: str, branch: str, baseline_sha: str, worktree_check: WorktreeCheck = git_worktree_check) -> StoryState:
        existing = self.store.load_story(story)
        if existing and existing.phase not in ("cancelled",):
            raise Refused(f"{story} already has state {existing.phase} in this run", phase=existing.phase)
        decision: Decision = decide(story, snapshot, self.policy)
        if not decision.dispatchable:
            raise Refused(f"{story} is not dispatchable: {decision.outcome} ({'; '.join(decision.reasons)})", decision=decision.as_dict())
        self._budget(delegation=True, claim=True)
        entry = snapshot.by_id()[story]
        receipt = validate_receipt(receipt, self.policy.implementer, "implementer")
        ok, why = worktree_check(worktree_path, branch)
        if not ok:
            raise Refused(f"worktree identity check failed: {why}")
        foreign = self._active_foreign_claims(entry.number, story)
        if foreign:
            raise Refused(f"{story} is claimed by another run: {foreign}", foreign=foreign)
        state = StoryState(story=story, issue=entry.number, item_id=entry.item_id, phase="claim-incomplete", run_id=self.store.run_id,
                           claim={"worktree_path": worktree_path, "branch": branch, "baseline_sha": baseline_sha, "claimed_at": self.now(), "scope": decision.outcome},
                           implementer_receipts=[receipt], status_before_claim=entry.status, item_updated_at=entry.item_updated_at)
        self.store.save_story(state)
        self.run.stories_claimed += 1
        self.store.save_run(self.run)
        self._count_delegation()
        self.store.journal(story, "claimed", {"issue": entry.number, "branch": branch, "baseline": baseline_sha, "task": receipt["taskId"], "scope": decision.outcome})
        self._post_marked(state, "claim", f"Unattended claim by run `{self.store.run_id}`: branch `{branch}` in an isolated worktree from `{baseline_sha}`; implementer T3 task `{receipt['taskId']}` ({receipt['providerInstanceId']}/{receipt['model']}, {receipt['options']}). Scope: {decision.outcome}. Completion still requires checks, independent review and owner acceptance.")
        self._write_status(state, "In progress", "Ready")
        state.phase = "claimed"
        self.store.save_story(state)
        return state

    def record_head(self, story: str, sha: str) -> StoryState:
        state = self._story(story)
        self._require_phase(state, *ACTIVE_PHASES)
        if state.phase == "claim-incomplete":
            raise Refused(f"{story} claim is incomplete; run resume first")
        if state.head_sha == sha:
            return state
        invalidated = state.phase == "review-approved" and state.approved_sha != sha
        state.head_sha, state.phase = sha, "implemented"
        self.store.save_story(state)
        self.store.journal(story, "head-recorded", {"sha": sha, "approval_invalidated": invalidated})
        return state

    def record_checks(self, story: str, sha: str, passed: bool, detail: dict) -> StoryState:
        state = self._story(story)
        self._require_phase(state, "implemented", "checks-passed", "checks-failed")
        if state.head_sha != sha:
            raise Refused(f"checks at {sha} do not match head {state.head_sha}", head=state.head_sha)
        state.checks.append({"sha": sha, "passed": passed, "at": self.now(), **detail})
        state.phase = "checks-passed" if passed else "checks-failed"
        self.store.save_story(state)
        self.store.journal(story, "checks-recorded", {"sha": sha, "passed": passed})
        return state

    def run_checks(self, story: str, sha: str, cwd: str, runner: Callable[[list[str], str, int], list[dict]]) -> StoryState:
        state = self._story(story)
        self._require_phase(state, "implemented", "checks-passed", "checks-failed")
        if not state.claim or Path(cwd).resolve() != Path(state.claim["worktree_path"]).resolve():
            raise Refused(f"checks must run in the claimed worktree {state.claim and state.claim['worktree_path']}")
        head = git_head(cwd)
        if head != sha:
            raise Refused(f"worktree HEAD {head} is not the recorded sha {sha}")
        results = runner(list(self.policy.check_commands), cwd, self.policy.check_timeout_minutes * 60)
        passed = all(r.get("returncode") == 0 for r in results)
        return self.record_checks(story, sha, passed, {"commands": results})

    def request_review(self, story: str, sha: str, receipt: dict) -> StoryState:
        state = self._story(story)
        self._require_phase(state, "checks-passed")
        if state.head_sha != sha or not state.checks or state.checks[-1]["sha"] != sha or not state.checks[-1]["passed"]:
            raise Refused(f"deterministic checks have not passed at {sha}")
        self._budget(delegation=True)
        used = {r["taskId"] for r in state.reviewer_receipts + state.implementer_receipts}
        receipt = validate_receipt(receipt, self.policy.reviewer, "reviewer", used)
        state.reviewer_receipts.append({**receipt, "sha": sha})
        state.phase = "review-requested"
        self.store.save_story(state)
        self._count_delegation()
        self.store.journal(story, "review-requested", {"sha": sha, "task": receipt["taskId"]})
        return state

    def record_review(self, story: str, sha: str, verdict: str, report: str) -> StoryState:
        state = self._story(story)
        if verdict not in ("approved", "changes-requested"):
            raise Refused("verdict must be approved or changes-requested")
        self._require_phase(state, "review-requested", "review-approved")
        if state.head_sha != sha:
            raise Refused(f"review at {sha} does not match head {state.head_sha}; a code change invalidates it", head=state.head_sha)
        regression = state.phase == "review-approved" and verdict == "changes-requested"
        state.reviews.append({"sha": sha, "verdict": verdict, "report": report, "at": self.now(), "regression": regression})
        if verdict == "approved":
            state.phase, state.approved_sha = "review-approved", sha
        else:
            state.phase, state.approved_sha = "changes-requested", None
        self.store.save_story(state)
        self.store.journal(story, "review-recorded", {"sha": sha, "verdict": verdict, "regression": regression})
        return state

    def repair(self, story: str, receipt: dict) -> StoryState:
        state = self._story(story)
        self._require_phase(state, "checks-failed", "changes-requested")
        if state.repair_rounds + 1 > self.policy.max_repair_rounds:
            self.store.journal(story, "repair-refused", {"rounds": state.repair_rounds})
            return self.block(story, f"repair rounds exhausted ({self.policy.max_repair_rounds}); unresolved after {state.phase}")
        self._budget(delegation=True)
        used = {r["taskId"] for r in state.reviewer_receipts + state.implementer_receipts}
        receipt = validate_receipt(receipt, self.policy.implementer, "implementer", used)
        state.implementer_receipts.append(receipt)
        state.repair_rounds += 1
        state.phase = "claimed"
        self.run.repair_rounds += 1
        self.store.save_run(self.run)
        self.store.save_story(state)
        self._count_delegation()
        self.store.journal(story, "repair-started", {"round": state.repair_rounds, "task": receipt["taskId"]})
        return state

    def propose_evidence(self, story: str, sha: str, pr_number: int, tasks: list[str], summary: str) -> StoryState:
        state = self._story(story)
        self._require_phase(state, "review-approved")
        if state.head_sha != sha or state.approved_sha != sha:
            raise Refused(f"approval is for {state.approved_sha}, head is {state.head_sha}, proposal names {sha}")
        pr = self.transport.get_pull_request(pr_number)
        if pr.head_sha != sha:
            raise Refused(f"PR #{pr_number} head {pr.head_sha} differs from approved {sha}")
        if pr.state != "OPEN" or pr.merged:
            raise Refused(f"PR #{pr_number} is {pr.state}; proposals need an open, unmerged PR")
        latest = [r for r in sorted(pr.reviews, key=lambda r: r.get("submitted_at") or "") if r.get("commit") == sha]
        if latest and latest[-1]["state"] == "CHANGES_REQUESTED":
            state.phase, state.approved_sha = "changes-requested", None
            state.reviews.append({"sha": sha, "verdict": "changes-requested", "report": f"GitHub review on PR #{pr_number}", "at": self.now(), "regression": True})
            self.store.save_story(state)
            self.store.journal(story, "review-regression-on-github", {"pr": pr_number, "sha": sha})
            raise Refused(f"PR #{pr_number} carries CHANGES_REQUESTED at {sha}; approval invalid")
        if pr.checks == "FAILURE":
            raise Refused(f"PR #{pr_number} status checks failed at {sha}")
        task_lines = "\n".join(f"- [ ] {t}" for t in tasks) or "- (no task completion proposed)"
        body = (f"Evidence proposal from run `{self.store.run_id}` at exact commit `{sha}` (PR #{pr_number}, CI rollup: {pr.checks or 'pending'}).\n"
                f"{summary}\n\nProposed task completion for owner application (the machine does not tick checkboxes):\n{task_lines}\n\n"
                "Checked boxes, CI pass, review approval, acceptance, merge and deployment remain distinct facts; this comment records review-approved implementation only.")
        state.proposal = {"sha": sha, "pr": pr_number, "tasks": tasks, "at": self.now(), "ci": pr.checks}
        self.store.save_story(state)
        self._post_marked(state, "proposal", body, sha=sha, pr=str(pr_number))
        self._write_status(state, "In review", "In progress")
        state.phase = "proposed"
        self.store.save_story(state)
        self.store.journal(story, "proposed", {"sha": sha, "pr": pr_number})
        return state

    def block(self, story: str, reason: str) -> StoryState:
        state = self._story(story)
        self._require_phase(state, *ACTIVE_PHASES)
        state.blocked = {"reason": reason, "at": self.now(), "from_phase": state.phase}
        state.phase = "blocked"
        self.store.save_story(state)
        self.store.journal(story, "blocked", {"reason": reason})
        try:
            self._post_marked(state, "block", f"Blocked by run `{self.store.run_id}`: {reason}. Owner decision or new evidence required; nothing advanced.")
            if state.status_written == "In progress":
                self._write_status(state, "Blocked", "In progress")
        except (TransportError, StaleRevision, Conflict) as exc:
            state.blocked["github_error"] = exc.as_dict()
            self.store.save_story(state)
            self.store.journal(story, "block-github-write-failed", exc.as_dict())
        return state

    def cancel(self, story: str, reason: str) -> StoryState:
        state = self._story(story)
        self._require_phase(state, *ACTIVE_PHASES)
        state.phase = "cancelled"
        state.blocked = {"reason": reason, "at": self.now(), "cancelled": True}
        self.store.save_story(state)
        self.store.journal(story, "cancelled", {"reason": reason})
        try:
            self._post_marked(state, "release", f"Claim released by run `{self.store.run_id}`: {reason}. No completion is implied.")
            if state.status_written == "In progress":
                self._write_status(state, "Ready", "In progress")
        except (TransportError, StaleRevision, Conflict) as exc:
            state.blocked["github_error"] = exc.as_dict()
            self.store.save_story(state)
            self.store.journal(story, "cancel-github-write-failed", exc.as_dict())
        return state

    def cancel_run(self, reason: str) -> list[StoryState]:
        out = [self.cancel(s.story, reason) for s in self.store.list_stories() if s.active]
        self.run.cancelled, self.run.stop_reason = True, reason
        self.store.save_run(self.run)
        self.store.journal(None, "run-cancelled", {"reason": reason})
        return out

    def resume(self, story: str, worktree_check: WorktreeCheck = git_worktree_check) -> StoryState:
        state = self._story(story)
        adopted = []
        for intent in state.pending_intents():
            found = [c for c in self.transport.list_comments(state.issue) if c.marker == intent.marker]
            if found:
                intent.status, intent.comment_id, intent.completed_at = "done", found[0].comment_id, self.now()
                adopted.append(intent.intent_id)
        if adopted:
            self.store.save_story(state)
            self.store.journal(story, "intents-adopted", {"intents": adopted})
        if state.phase == "claim-incomplete":
            claim_intent = next((i for i in state.intents if i.kind == "claim"), None)
            if claim_intent is None or claim_intent.status != "done":
                self._post_marked(state, "claim", f"Unattended claim by run `{self.store.run_id}` (re-posted on resume).")
            item = self.transport.get_project_item(state.item_id)
            if item.status == "In progress" and state.status_written == "In progress":
                state.phase = "claimed"
            elif item.status == "Ready":
                state.item_updated_at = item.updated_at
                self._write_status(state, "In progress", "Ready")
                state.phase = "claimed"
            else:
                self.store.journal(story, "resume-claim-abandoned", {"status": item.status})
                return self.cancel(story, f"Status is {item.status!r} on resume; claim abandoned")
            self.store.save_story(state)
            self.store.journal(story, "claim-completed-on-resume", {})
        if state.active and state.claim:
            ok, why = worktree_check(state.claim["worktree_path"], state.claim["branch"])
            if not ok:
                raise Refused(f"cannot resume {story}: {why}")
        return state

    def status(self) -> dict:
        return {"run": self.run.__dict__, "stories": [s.to_dict() for s in self.store.list_stories()], "journal_events": self.store.journal_count()}
