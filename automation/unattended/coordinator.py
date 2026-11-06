"""The per-story state machine the T3 coordinator drives.

Phases (``state.PHASES``)::

    reserve ──(admission under lock, claim marker)──> reserved ──bind-receipt (worktree identity)──> claimed
    claimed ──record-head──> implemented ──run-checks (full set, exact clean HEAD)──> checks-passed | checks-failed
    checks-passed ──request-review (worktree re-read, fresh reviewer receipt)──> review-requested ──record-review──> review-approved | changes-requested
    checks-failed | changes-requested ──repair (budgeted, round ≤ 2)──> claimed ; otherwise ──> blocked
    checks-failed | changes-requested ──record-head──> REFUSED (repair-required)
    review-approved ──record-head(new sha) | unreported worktree change──> implemented (evidence invalidated)
    review-approved ──propose-evidence (revisions unchanged, worktree re-read, PR head/reviews/checks)──> proposed
    any active | conflict ──block | cancel (terminal worker evidence when a worker is running)──> blocked | cancelled
    duplicate marker ──> conflict

External effects are append-only marker comments only (``claim``, ``release``, ``block``,
``proposal``). Each is a write-ahead intent carrying its stable operation identity and its
complete comment body; a replay posts exactly that body, and advancing replays re-validate
their preconditions first. Terminal phases persist together with their cleanup intent.

Every operation refuses a live transport (``live-execution-disabled``) and a run's state is
bound to the environment (fixture or live) it was created in. The live gate stays until the
T3 execution protocol is qualified with an actual bounded worker, which this foundation has
not done.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

from .backlog import Entry, Snapshot, take_snapshot
from .eligibility import Decision, decide
from .errors import BudgetExhausted, Conflict, Refused, StaleRevision, UnattendedError
from .github import PullRequestRecord, Transport, render_marker
from .policy import Policy
from .probes import run_commands
from .receipts import validate_receipt
from .state import ACTIVE_PHASES, Intent, Store, StoryState, utcnow

WorktreeCheck = Callable[[str, str], tuple[bool, str]]

# What the installed T3 tools do not establish; verified against the tool metadata. The
# protocol itself (reserve under the lock before delegate_task, bind the receipt afterwards,
# keep ownership until task_status/task_cancel report a terminal state) is supported by the
# tools and implemented below, but it has not been qualified with an actual worker.
LIVE_EXECUTION_GAPS = (
    "no hard deadline or resource bound on a delegated child: delegate_task timeoutMs limits the wait in mode=wait only and does not cancel the child",
    "credential confinement of a delegated child is not established: the child runs with the coordinator's credentials and runtime mode",
    "reserve-before-delegate, receipt binding and terminal task evidence (task_status workState result_available; task_cancel reporting a terminal state) are implemented as protocol but not qualified with an actual bounded worker",
    "no bounded GitHub credential has passed the permission probe (denial of forbidden operations untested)",
)
TERMINAL_TASK_STATES = ("result_available", "completed", "failed", "cancelled", "terminal")
CLEANUP_KINDS = ("release", "block")


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


def git_clean(path: str) -> tuple[bool, str]:
    try:
        out = subprocess.run(["git", "-C", path, "status", "--porcelain", "--untracked-files=normal"], capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"git status failed: {exc}"
    if out.returncode != 0:
        return False, f"git status failed: {out.stderr.strip()[:200]}"
    return (out.stdout.strip() == ""), out.stdout.strip()[:500]


def outstanding_objections(pr: PullRequestRecord) -> list[str]:
    """Reviewers whose latest effective review is CHANGES_REQUESTED, at any commit. A later
    approval by another reviewer does not clear it; only that reviewer's own later
    APPROVED or a DISMISSED review does."""
    effective: dict[str, str] = {}
    for review in sorted(pr.reviews, key=lambda r: r.get("submitted_at") or ""):
        if review.get("state") in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED"):
            effective[review.get("author") or "?"] = review["state"]
    return sorted(a for a, s in effective.items() if s == "CHANGES_REQUESTED")


def closure(snapshot: Snapshot, entry: Entry) -> list[Entry]:
    """The entries whose revisions decide ``entry``'s eligibility: itself, its parent epic,
    direct dependencies, and for epic dependencies / parent prerequisites the epic plus
    every story of it."""
    by_id, by_number = snapshot.by_id(), snapshot.by_number()
    out: dict[str, Entry] = {entry.stable_id: entry}
    parent = by_number.get(entry.parent_number) if entry.parent_number else None
    epics: list[str] = []
    if parent:
        out[parent.stable_id] = parent
        epics += list(parent.epic_prerequisites)
    for dep in entry.depends_on:
        dep_entry = by_id.get(dep)
        if dep_entry is None:
            continue
        out[dep] = dep_entry
        if dep_entry.kind == "epic":
            epics.append(dep)
    for epic_id in epics:
        epic = by_id.get(epic_id)
        if epic:
            out[epic_id] = epic
        for story in snapshot.entries:
            if story.kind == "story" and story.epic_id == epic_id:
                out[story.stable_id] = story
    return list(out.values())


def revisions_of(entries: list[Entry]) -> dict[str, dict]:
    return {e.stable_id: {"issue_updated_at": e.updated_at, "body_sha256": e.body_sha256, "state": e.state, "state_reason": e.state_reason,
                          "item_id": e.item_id, "item_updated_at": e.item_updated_at, "status": e.status} for e in entries}


def revision_diff(recorded: dict[str, dict], current: dict[str, dict]) -> dict[str, dict]:
    changed = {}
    for key in sorted(set(recorded) | set(current)):
        if recorded.get(key) != current.get(key):
            changed[key] = {"recorded": recorded.get(key), "current": current.get(key)}
    return changed


class Coordinator:
    def __init__(self, transport: Transport, policy: Policy, store: Store, now: Callable[[], str] = utcnow, live: bool = False):
        self.transport, self.policy, self.store, self.now, self.live = transport, policy, store, now, live
        self.environment = "live" if getattr(transport, "live", False) else "fixture"
        self.run = store.ensure_run(policy.repo_slug, policy.digest, self.environment)

    # -- guards --------------------------------------------------------------------------
    def require_not_live(self, operation: str) -> None:
        """Every state-advancing operation and every recovery refuses a production transport.
        No live state can exist, so there is nothing a bounded cleanup could release there."""
        if self.environment == "live":
            raise Refused(f"{operation}: live execution is disabled; the T3 execution protocol and a bounded credential are not qualified", code="live-execution-disabled", gaps=list(LIVE_EXECUTION_GAPS))

    def _reload_run(self) -> None:
        run = self.store.load_run()
        if run is None or (run.repo, run.policy_digest, run.environment) != (self.policy.repo_slug, self.policy.digest, self.environment):
            raise Refused("run binding changed on disk", code="run-binding-mismatch")
        self.run = run

    def _story(self, story: str) -> StoryState:
        state = self.store.load_story(story)
        if state is None:
            raise Refused(f"{story} has no state in run {self.store.run_id}")
        return state

    def _require_phase(self, state: StoryState, *phases: str) -> None:
        if state.phase not in phases:
            raise Refused(f"{state.story} is {state.phase}; this operation needs {phases}", phase=state.phase)

    def _budget(self, *, delegation: bool = False, admission: bool = False) -> None:
        run = self.run
        if run.cancelled:
            raise BudgetExhausted("run is cancelled", stop_reason=run.stop_reason)
        elapsed = datetime.fromisoformat(self.now().replace("Z", "+00:00")) - datetime.fromisoformat(run.started_at.replace("Z", "+00:00"))
        if elapsed > timedelta(minutes=self.policy.max_wall_clock_minutes):
            raise BudgetExhausted(f"wall clock budget of {self.policy.max_wall_clock_minutes} minutes exceeded")
        if delegation and run.delegated_tasks + 1 > self.policy.max_delegated_tasks:
            raise BudgetExhausted(f"delegated task budget {self.policy.max_delegated_tasks} exhausted")
        if admission:
            if run.stories_claimed + 1 > self.policy.max_stories_per_run:
                raise BudgetExhausted(f"story budget {self.policy.max_stories_per_run} exhausted")
            active = [s.story for s in self.store.list_stories() if s.active or s.phase == "conflict"]
            if len(active) + 1 > self.policy.max_concurrent_implementers:
                raise Refused(f"another story is active in this run: {active}", active=active)

    def _count_delegation(self) -> None:
        self.run.delegated_tasks += 1
        self.store.save_run(self.run)

    def _fresh_snapshot(self) -> Snapshot:
        return take_snapshot(self.transport, self.policy.repo_slug, self.now())

    def _current_revisions(self, story: str, snapshot: Snapshot | None = None) -> tuple[Snapshot, dict[str, dict]]:
        fresh = snapshot or self._fresh_snapshot()
        entry = fresh.by_id().get(story)
        return fresh, (revisions_of(closure(fresh, entry)) if entry else {})

    def _check_revisions(self, state: StoryState, snapshot: Snapshot | None = None) -> Snapshot:
        """Re-read GitHub and refuse when any revision in the story's closure differs from
        the ones recorded at admission. Never rebases silently."""
        fresh, current = self._current_revisions(state.story, snapshot)
        changed = revision_diff(state.revisions, current)
        if changed:
            self.store.journal(state.story, "revision-mismatch", {"changed": sorted(changed)})
            raise StaleRevision(f"{state.story}: revisions changed since admission for {sorted(changed)}; re-plan or rebase-revisions explicitly", changed=changed)
        return fresh

    def _verify_worktree(self, state: StoryState, sha: str, gate: str) -> None:
        """Re-read the actual worktree identity, HEAD and cleanliness at an evidence gate.
        An unreported change invalidates the recorded check and review evidence."""
        if not state.claim or not state.claim.get("worktree_path"):
            raise Refused(f"{gate}: no worktree bound to {state.story}")
        ok, why = git_worktree_check(state.claim["worktree_path"], state.claim["branch"])
        if not ok:
            raise Refused(f"{gate}: worktree identity check failed: {why}", code="worktree-mismatch")
        head = git_head(state.claim["worktree_path"])
        clean, dirt = git_clean(state.claim["worktree_path"])
        if head != sha or not clean:
            state.phase, state.head_sha, state.approved_sha = "implemented", head, None
            self.store.save_story(state)
            self.store.journal(state.story, "unreported-worktree-change", {"gate": gate, "expected": sha, "head": head, "clean": clean, "dirt": dirt})
            raise Refused(f"{gate}: worktree HEAD {head} / clean={clean} differs from the evidence at {sha}; check and review evidence invalidated", code="evidence-invalidated", head=head, clean=clean)

    def _active_foreign_claims(self, issue: int, story: str) -> list[dict]:
        claims: dict[str, dict] = {}
        released: set[str] = set()
        for c in self.transport.list_comments(issue):
            m = c.marker
            if not m or m.get("story") != story:
                continue
            run = m.get("run", "")
            if m.get("kind") == "claim":
                claims[run] = m
            elif m.get("kind") in ("release", "block", "proposal"):
                released.add(run)
        return [m for run, m in claims.items() if run != self.store.run_id and run not in released]

    def _new_intent(self, state: StoryState, op: str, kind: str, body: str, preconditions: dict | None = None, **extra: str) -> Intent:
        """Record the complete effect (identity, marker and exact body) before attempting it."""
        existing = state.intent(op)
        if existing is not None:
            return existing
        marker = {"kind": kind, "run": self.store.run_id, "story": state.story, "op": op, **extra}
        intent = Intent(op, kind, marker, body=f"{render_marker(**marker)}\n{body}", preconditions=preconditions or {})
        state.intents.append(intent)
        return intent

    def _post_intent(self, state: StoryState, intent: Intent) -> Intent:
        """Idempotent post of a recorded intent: zero markers ⇒ post the persisted body,
        one ⇒ adopt, more ⇒ conflict."""
        if not self.live:
            raise Refused(f"{intent.kind} for {state.story} needs live writes (--live)", code="live-required")
        if intent.status == "done":
            return intent
        if intent.status == "abandoned":
            raise Refused(f"{intent.op} for {state.story} was abandoned: {intent.reason}")
        found = [c for c in self.transport.list_comments(state.issue) if c.marker == intent.marker]
        if not found:
            posted = self.transport.post_comment(state.issue, intent.body)
            found = [c for c in self.transport.list_comments(state.issue) if c.marker == intent.marker]
            self.store.journal(state.story, "comment-posted", {"op": intent.op, "comment_id": posted.comment_id})
            if not found:
                raise Conflict(f"comment {intent.op} was posted (id {posted.comment_id}) but is not readable back", comment_id=posted.comment_id)
        else:
            self.store.journal(state.story, "comment-adopted", {"op": intent.op, "comment_id": found[0].comment_id})
        if len(found) > 1:
            ids = [c.comment_id for c in found]
            self.store.journal(state.story, "duplicate-marker-detected", {"op": intent.op, "comment_ids": ids})
            if state.active:
                state.blocked = {"reason": f"duplicate marker for {intent.op}: {ids}", "at": self.now(), "from_phase": state.phase, "conflict": True}
                state.phase = "conflict"
                self.store.save_story(state)
            raise Conflict(f"marker {intent.marker} appears {len(found)} times; a concurrent writer posted the same event", comment_ids=ids)
        intent.status, intent.comment_id, intent.completed_at = "done", found[0].comment_id, self.now()
        self.store.save_story(state)
        return intent

    # -- admission -------------------------------------------------------------------------
    def reserve(self, story: str, snapshot: Snapshot, baseline_sha: str) -> StoryState:
        """Admission BEFORE any delegated task exists: budgets, eligibility on the plan
        snapshot and on a fresh read, no foreign claim, claim marker. The receipt of the task
        the coordinator then launches is bound with :meth:`bind_receipt`."""
        with self.store.locked(self):
            self.require_not_live("reserve")
            self._reload_run()
            if self.store.load_story(story) is not None:
                raise Refused(f"{story} already has state in run {self.store.run_id}; a story is admitted at most once per run (no reclaim)", code="no-reclaim")
            decision: Decision = decide(story, snapshot, self.policy)
            if not decision.dispatchable:
                raise Refused(f"{story} is not dispatchable: {decision.outcome} ({'; '.join(decision.reasons)})", decision=decision.as_dict())
            self._budget(admission=True)
            planned = snapshot.by_id()[story]
            fresh, current = self._current_revisions(story)
            changed = revision_diff(revisions_of(closure(snapshot, planned)), current)
            if changed:
                raise StaleRevision(f"{story}: GitHub changed since the plan snapshot for {sorted(changed)}; re-plan from a fresh snapshot", changed=changed)
            fresh_decision = decide(story, fresh, self.policy)
            if not fresh_decision.dispatchable:
                raise Refused(f"{story} is not dispatchable on the fresh snapshot: {fresh_decision.outcome}", decision=fresh_decision.as_dict())
            entry = fresh.by_id()[story]
            foreign = self._active_foreign_claims(entry.number, story)
            if foreign:
                raise Refused(f"{story} is claimed by another run: {foreign}", foreign=foreign)
            state = StoryState(story=story, issue=entry.number, item_id=entry.item_id, phase="claim-incomplete", run_id=self.store.run_id,
                               claim={"baseline_sha": baseline_sha, "reserved_at": self.now(), "scope": decision.outcome, "worktree_path": None, "branch": None},
                               revisions=current)
            intent = self._new_intent(state, "claim", "claim", f"Unattended reservation by run `{self.store.run_id}` from `{baseline_sha}` (scope: {decision.outcome}). An implementer task is delegated only after this reservation; its receipt is bound to the reservation. Project Status is owner-maintained; completion still requires checks, independent review and owner acceptance.", {"revisions": current})
            self.store.save_story(state)
            self.run.stories_claimed += 1
            self.store.save_run(self.run)
            self.store.journal(story, "reserved", {"issue": entry.number, "baseline": baseline_sha, "scope": decision.outcome})
            self._post_intent(state, intent)
            state.phase = "reserved"
            self.store.save_story(state)
            return state

    def bind_receipt(self, story: str, receipt: dict, worktree_path: str, branch: str, worktree_check: WorktreeCheck = git_worktree_check) -> StoryState:
        """Bind the delegated implementer task (its receipt and worktree) to the reservation."""
        with self.store.locked(self):
            self.require_not_live("bind-receipt")
            self._reload_run()
            state = self._story(story)
            self._require_phase(state, "reserved")
            self._budget(delegation=True)
            receipt = validate_receipt(receipt, self.policy.implementer, "implementer")
            ok, why = worktree_check(worktree_path, branch)
            if not ok:
                raise Refused(f"worktree identity check failed: {why}", code="worktree-mismatch")
            state.claim.update({"worktree_path": worktree_path, "branch": branch, "claimed_at": self.now()})
            state.implementer_receipts.append(receipt)
            state.worker_state, state.phase = "running", "claimed"
            self.store.save_story(state)
            self._count_delegation()
            self.store.journal(story, "receipt-bound", {"task": receipt["taskId"], "branch": branch, "worktree": worktree_path})
            return state

    # -- implementation ---------------------------------------------------------------------
    def record_head(self, story: str, sha: str) -> StoryState:
        with self.store.locked(self):
            self.require_not_live("record-head")
            state = self._story(story)
            if state.phase in ("checks-failed", "changes-requested"):
                raise Refused(f"{story} is {state.phase}; a new implementation needs a budgeted repair authorization first", code="repair-required", phase=state.phase)
            self._require_phase(state, "claimed", "implemented", "checks-passed", "review-requested", "review-approved")
            state.worker_state = "returned"
            if state.head_sha == sha and state.phase != "claimed":
                self.store.save_story(state)
                return state
            invalidated = state.phase in ("review-requested", "review-approved")
            state.head_sha, state.phase, state.approved_sha = sha, "implemented", None
            self.store.save_story(state)
            self.store.journal(story, "head-recorded", {"sha": sha, "approval_invalidated": invalidated})
            return state

    def run_checks(self, story: str, sha: str, cwd: str, runner=None) -> StoryState:
        """Execute the full configured check set on the exact claimed HEAD in a clean tree.
        This is the only way checks become evidence; there is no asserted pass."""
        with self.store.locked(self):
            self.require_not_live("run-checks")
            state = self._story(story)
            self._require_phase(state, "implemented", "checks-passed", "checks-failed")
            if not state.claim or not state.claim.get("worktree_path") or Path(cwd).resolve() != Path(state.claim["worktree_path"]).resolve():
                raise Refused(f"checks must run in the claimed worktree {state.claim and state.claim.get('worktree_path')}")
            if state.head_sha != sha:
                raise Refused(f"checks at {sha} do not match the recorded head {state.head_sha}", head=state.head_sha)
            head_before = git_head(cwd)
            if head_before != sha:
                raise Refused(f"worktree HEAD {head_before} is not the recorded sha {sha}")
            clean_before, dirt = git_clean(cwd)
            if not clean_before:
                raise Refused(f"worktree is not clean before checks: {dirt}")
            commands = list(self.policy.check_commands)
            kwargs = {"runner": runner} if runner else {}
            results = run_commands(commands, cwd, self.policy.check_timeout_minutes * 60, fail_fast=False, **kwargs)
            head_after = git_head(cwd)
            clean_after, dirt_after = git_clean(cwd)
            executed_all = len(results) == len(commands) and all("returncode" in r for r in results)
            passed = executed_all and all(r.get("returncode") == 0 for r in results) and head_after == sha and clean_after
            detail = {"commands": results, "executed": executed_all, "head_before": head_before, "head_after": head_after, "clean_before": clean_before, "clean_after": clean_after, "dirt_after": dirt_after}
            state.checks.append({"sha": sha, "passed": passed, "at": self.now(), **detail})
            state.phase = "checks-passed" if passed else "checks-failed"
            self.store.save_story(state)
            self.store.journal(story, "checks-recorded", {"sha": sha, "passed": passed, "commands": len(results)})
            return state

    def request_review(self, story: str, sha: str, receipt: dict) -> StoryState:
        with self.store.locked(self):
            self.require_not_live("request-review")
            self._reload_run()
            state = self._story(story)
            self._require_phase(state, "checks-passed")
            last = state.checks[-1] if state.checks else None
            configured = len(self.policy.check_commands)
            if (state.head_sha != sha or not last or last["sha"] != sha or not last["passed"] or not last.get("executed")
                    or len(last.get("commands", [])) != configured or any(c.get("returncode") != 0 for c in last["commands"])
                    or last.get("head_after") != sha or not last.get("clean_after")):
                raise Refused(f"the full configured check set ({configured} commands) has not been executed and passed at {sha}")
            self._verify_worktree(state, sha, "request-review")
            self._budget(delegation=True)
            used = {r["taskId"] for r in state.reviewer_receipts + state.implementer_receipts}
            receipt = validate_receipt(receipt, self.policy.reviewer, "reviewer", used)
            state.reviewer_receipts.append({**receipt, "sha": sha})
            state.phase, state.worker_state = "review-requested", "running"
            self.store.save_story(state)
            self._count_delegation()
            self.store.journal(story, "review-requested", {"sha": sha, "task": receipt["taskId"]})
            return state

    def record_review(self, story: str, sha: str, verdict: str, report: str) -> StoryState:
        with self.store.locked(self):
            self.require_not_live("record-review")
            state = self._story(story)
            if verdict not in ("approved", "changes-requested"):
                raise Refused("verdict must be approved or changes-requested")
            self._require_phase(state, "review-requested", "review-approved")
            if state.head_sha != sha:
                raise Refused(f"review at {sha} does not match head {state.head_sha}; a code change invalidates it", head=state.head_sha)
            self._verify_worktree(state, sha, "record-review")
            regression = state.phase == "review-approved" and verdict == "changes-requested"
            state.reviews.append({"sha": sha, "verdict": verdict, "report": report, "at": self.now(), "regression": regression})
            state.worker_state = "returned"
            if verdict == "approved":
                state.phase, state.approved_sha = "review-approved", sha
            else:
                state.phase, state.approved_sha = "changes-requested", None
            self.store.save_story(state)
            self.store.journal(story, "review-recorded", {"sha": sha, "verdict": verdict, "regression": regression})
            return state

    def repair(self, story: str, receipt: dict) -> StoryState:
        with self.store.locked(self):
            self.require_not_live("repair")
            self._reload_run()
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
            state.phase, state.worker_state = "claimed", "running"
            self.run.repair_rounds += 1
            self.store.save_run(self.run)
            self.store.save_story(state)
            self._count_delegation()
            self.store.journal(story, "repair-started", {"round": state.repair_rounds, "task": receipt["taskId"]})
            return state

    # -- proposal -------------------------------------------------------------------------
    def _validate_pr(self, state: StoryState, sha: str, pr_number: int) -> PullRequestRecord:
        pr = self.transport.get_pull_request(pr_number)
        if pr.head_sha != sha:
            raise Refused(f"PR #{pr_number} head {pr.head_sha} differs from approved {sha}")
        if pr.state != "OPEN" or pr.merged:
            raise Refused(f"PR #{pr_number} is {pr.state}; proposals need an open, unmerged PR")
        objections = outstanding_objections(pr)
        if objections:
            state.phase, state.approved_sha = "changes-requested", None
            state.reviews.append({"sha": sha, "verdict": "changes-requested", "report": f"GitHub review on PR #{pr_number} by {objections}", "at": self.now(), "regression": True})
            for intent in state.pending_intents():
                if intent.kind == "proposal":
                    intent.status, intent.reason = "abandoned", f"review regression on PR #{pr_number} by {objections}"
            self.store.save_story(state)
            self.store.journal(state.story, "review-regression-on-github", {"pr": pr_number, "sha": sha, "reviewers": objections})
            raise Refused(f"PR #{pr_number} has outstanding CHANGES_REQUESTED from {objections}; approval invalid")
        if pr.checks == "FAILURE":
            raise Refused(f"PR #{pr_number} status checks failed at {sha}")
        return pr

    def propose_evidence(self, story: str, sha: str, pr_number: int, tasks: list[str], summary: str) -> StoryState:
        with self.store.locked(self):
            self.require_not_live("propose-evidence")
            state = self._story(story)
            self._require_phase(state, "review-approved")
            if state.head_sha != sha or state.approved_sha != sha:
                raise Refused(f"approval is for {state.approved_sha}, head is {state.head_sha}, proposal names {sha}")
            self._check_revisions(state)
            self._verify_worktree(state, sha, "propose-evidence")
            pr = self._validate_pr(state, sha, pr_number)
            op = f"proposal-{sha[:12]}-pr{pr_number}"
            intent = state.intent(op)
            if intent is None:
                task_lines = "\n".join(f"- [ ] {t}" for t in tasks) or "- (no task completion proposed)"
                body = (f"Evidence proposal from run `{self.store.run_id}` at exact commit `{sha}` (PR #{pr_number}, CI rollup: {pr.checks or 'pending'}).\n"
                        f"{summary}\n\nProposed task completion for owner application (the machine does not tick checkboxes or change Project Status):\n{task_lines}\n\n"
                        "Checked boxes, CI pass, review approval, acceptance, merge and deployment remain distinct facts; this comment records review-approved implementation only.")
                intent = self._new_intent(state, op, "proposal", body, {"sha": sha, "pr": pr_number, "revisions": dict(state.revisions)}, sha=sha, pr=str(pr_number))
                state.proposal = {"sha": sha, "pr": pr_number, "tasks": tasks, "at": self.now(), "ci": pr.checks}
                self.store.save_story(state)
            self._post_intent(state, intent)
            state.phase = "proposed"
            self.store.save_story(state)
            self.store.journal(story, "proposed", {"sha": sha, "pr": pr_number})
            return state

    # -- terminal -------------------------------------------------------------------------
    def _require_worker_terminal(self, state: StoryState, task_evidence: dict | None, operation: str) -> None:
        """A story whose delegated task has not returned keeps its ownership until the
        coordinator presents terminal task evidence (task_status / task_cancel result)."""
        if state.worker_state != "running":
            return
        receipts = state.reviewer_receipts if state.phase == "review-requested" else state.implementer_receipts
        task_id = receipts[-1]["taskId"] if receipts else None
        if not isinstance(task_evidence, dict) or task_evidence.get("taskId") != task_id or task_evidence.get("status") not in TERMINAL_TASK_STATES:
            raise Refused(f"{operation}: delegated task {task_id} is still running; present terminal task evidence (task_status workState result_available or a terminal task_cancel result) before releasing ownership", code="worker-not-terminal", task_id=task_id)

    def _terminal(self, story: str, phase: str, reason: str, op: str, kind: str, body: str, task_evidence: dict | None) -> StoryState:
        state = self._story(story)
        self._require_phase(state, *ACTIVE_PHASES, "conflict")
        self._require_worker_terminal(state, task_evidence, phase)
        state.blocked = {"reason": reason, "at": self.now(), "from_phase": state.phase, "cancelled": phase == "cancelled", "task_evidence": task_evidence}
        state.phase = phase
        state.worker_state = "none"
        intent = self._new_intent(state, op, kind, body)
        self.store.save_story(state)  # terminal phase and its cleanup intent persist together
        self.store.journal(story, phase, {"reason": reason})
        try:
            self._post_intent(state, intent)
        except UnattendedError as exc:
            state.blocked["github_error"] = exc.as_dict()
            self.store.save_story(state)
            self.store.journal(story, f"{phase}-github-write-failed", exc.as_dict())
        return state

    def block(self, story: str, reason: str, task_evidence: dict | None = None) -> StoryState:
        with self.store.locked(self):
            self.require_not_live("block")
            return self._terminal(story, "blocked", reason, "block", "block", f"Blocked by run `{self.store.run_id}`: {reason}. Owner decision or new evidence required; nothing advanced. Project Status is owner-maintained.", task_evidence)

    def cancel(self, story: str, reason: str, task_evidence: dict | None = None) -> StoryState:
        with self.store.locked(self):
            self.require_not_live("cancel")
            return self._terminal(story, "cancelled", reason, "release", "release", f"Claim released by run `{self.store.run_id}`: {reason}. No completion is implied. Project Status is owner-maintained.", task_evidence)

    def cancel_run(self, reason: str, task_evidence: dict[str, dict] | None = None) -> dict:
        """Stop admissions and release every story whose worker is terminal. Stories with a
        running worker and no terminal evidence stay owned and are reported."""
        with self.store.locked(self):
            self.require_not_live("cancel-run")
            self._reload_run()
            self.run.cancelled, self.run.stop_reason = True, reason
            self.store.save_run(self.run)
            self.store.journal(None, "run-cancelled", {"reason": reason})
            released, awaiting = [], []
            for s in self.store.list_stories():
                if not (s.active or s.phase == "conflict"):
                    continue
                try:
                    released.append(self.cancel(s.story, reason, (task_evidence or {}).get(s.story)).to_dict())
                except Refused as exc:
                    if exc.code != "worker-not-terminal":
                        raise
                    awaiting.append({"story": s.story, "task_id": exc.detail.get("task_id")})
            return {"cancelled": released, "awaiting_worker_termination": awaiting}

    # -- recovery -------------------------------------------------------------------------
    def resume(self, story: str, worktree_check: WorktreeCheck = git_worktree_check) -> StoryState:
        """Restart recovery. Order: live gate, ownership identity, then replay of pending
        effects with their persisted payload: cleanups unconditionally, advancing effects only
        after their preconditions are re-verified, then revision verification."""
        with self.store.locked(self):
            self.require_not_live("resume")
            self._reload_run()
            state = self._story(story)
            if state.claim and state.claim.get("worktree_path"):
                ok, why = worktree_check(state.claim["worktree_path"], state.claim["branch"])
                if not ok:
                    raise Refused(f"cannot resume {story}: {why}", code="worktree-mismatch")
            for intent in state.pending_intents():
                if intent.kind in CLEANUP_KINDS:
                    self._post_intent(state, intent)
            for intent in state.pending_intents():
                if intent.kind == "claim":
                    fresh, current = self._current_revisions(story)
                    changed = revision_diff(intent.preconditions.get("revisions", state.revisions), current)
                    if changed:
                        self.store.journal(story, "resume-claim-abandoned", {"changed": sorted(changed)})
                        intent.status, intent.reason = "abandoned", f"revisions changed before the reservation completed: {sorted(changed)}"
                        state.phase = "cancelled"
                        state.blocked = {"reason": intent.reason, "at": self.now(), "from_phase": "claim-incomplete", "cancelled": True}
                        self.store.save_story(state)
                        return state
                    self._post_intent(state, intent)
                    if state.phase == "claim-incomplete":
                        state.phase = "reserved"
                        self.store.save_story(state)
                        self.store.journal(story, "reservation-completed-on-resume", {})
                elif intent.kind == "proposal":
                    self._check_revisions(state)
                    self._verify_worktree(state, intent.preconditions["sha"], "resume-proposal")
                    self._validate_pr(state, intent.preconditions["sha"], int(intent.preconditions["pr"]))
                    self._post_intent(state, intent)
                    state.phase = "proposed"
                    self.store.save_story(state)
                    self.store.journal(story, "proposal-completed-on-resume", {"op": intent.op})
            if state.active and state.phase not in ("claim-incomplete",):
                self._check_revisions(state)
            return state

    def rebase_revisions(self, story: str, reason: str) -> StoryState:
        """Explicit, journaled acceptance of changed revisions after a human verified them."""
        with self.store.locked(self):
            self.require_not_live("rebase-revisions")
            state = self._story(story)
            self._require_phase(state, *ACTIVE_PHASES)
            fresh, current = self._current_revisions(story)
            if story not in fresh.by_id():
                raise Refused(f"{story} is no longer in the snapshot")
            changed = revision_diff(state.revisions, current)
            state.revisions = current
            for intent in state.pending_intents():
                if "revisions" in intent.preconditions:
                    intent.preconditions["revisions"] = dict(current)
            self.store.save_story(state)
            self.store.journal(story, "revisions-rebased", {"reason": reason, "changed": changed})
            return state

    def status(self) -> dict:
        return {"run": self.run.__dict__, "environment": self.environment, "stories": [s.to_dict() for s in self.store.list_stories()], "journal_events": self.store.journal_count(), "live": self.live, "gaps": list(LIVE_EXECUTION_GAPS)}
