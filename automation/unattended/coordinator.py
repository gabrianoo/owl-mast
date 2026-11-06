"""The per-story state machine the T3 coordinator drives.

Phases (``state.PHASES``)::

    reserve ──(admission under lock, implementer authorization, claim marker)──> reserved
    reserved ──bind-receipt (consumes the authorization; worktree identity)──> claimed            active task: implementer
    claimed ──record-head (+ implementer terminal evidence)──> implemented                         active task: none
    implemented ──run-checks (full set, exact clean HEAD)──> checks-passed | checks-failed
    checks-passed ──authorize-review (worktree re-read, reviewer authorization)──> review-authorized
    review-authorized ──bind-receipt (fresh reviewer receipt)──> review-requested                   active task: reviewer
    review-requested ──record-review (+ reviewer terminal evidence)──> review-approved | changes-requested
    checks-failed | changes-requested ──authorize-repair (round ≤ 2, implementer authorization)──> repair-authorized ; otherwise ──> blocked
    repair-authorized ──bind-receipt──> claimed                                                     active task: implementer
    checks-failed | changes-requested ──record-head──> REFUSED (repair-required)
    review-authorized | review-requested | review-approved ──record-head(new sha) | unreported worktree change──> implemented (evidence invalidated; pending proposal abandoned)
    review-approved ──propose-evidence (revisions unchanged, worktree re-read, PR head/reviews/checks)──> proposed
    any active | conflict ──block | cancel (terminal evidence for the active task)──> blocked | cancelled (pending advancing intents abandoned)
    duplicate marker ──> conflict

Task capacity is authorized durably BEFORE a launch (``reserve``, ``authorize-review``,
``authorize-repair``); every issued authorization counts against ``max_delegated_tasks``
whether or not it is ever bound, ``bind-receipt`` consumes exactly one pending authorization,
and budgets are derived from the story files under the lock, never from cached counters. A
receipt is fresh only if its task id was never bound anywhere in the run (any story, any
role, terminal or not). The active task (id and role) is tracked independently of the phase:
HEAD recording, review verdicts and evidence invalidation never release ownership; only
terminal task evidence does.

The wall-clock budget is a local expiry of the run: once exceeded (or once the run is
cancelled) no authorization is issued or returned, every advancing operation refuses, and a
receipt for an authorization issued earlier binds for cleanup only (slot spent, task id bound,
task owned, phase unchanged) so that the launched worker can only leave through its terminal
evidence. This expiry never stops a child; T3 offers no hard child lifetime bound.

External effects are append-only marker comments only (``claim``, ``release``, ``block``,
``proposal``). Each is a write-ahead intent carrying its stable operation identity and its
complete comment body; a replay posts exactly that body, and advancing replays re-validate
their preconditions (local phase, exact-SHA approval, revisions, worktree, PR) first. A
terminal phase, its cleanup intent and the abandonment of every pending advancing intent
persist in one write; a cancelled run or a terminal story never replays an advancing intent.
On resume, a completed advancing intent whose transition did not persist is reconciled only
behind the same guards as a fresh attempt (run not cancelled, matching phase, exact-SHA
approval, no active task); otherwise its effect stays recorded as history and the phase is
not advanced. A reservation whose revisions changed before it was checkpointed is cancelled
together with the release it owes (when its claim comment landed) in one write.

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
from .policy import Policy, Target
from .probes import run_commands
from .receipts import validate_receipt
from .state import ACTIVE_PHASES, Intent, Store, StoryState, utcnow

WorktreeCheck = Callable[[str, str], tuple[bool, str]]

# What the installed T3 tools do not establish; verified against the tool metadata. The
# protocol itself (authorize under the lock before delegate_task, bind the receipt afterwards,
# keep ownership until task_status/task_cancel report a terminal state) is supported by the
# tools and implemented below, but it has not been qualified with an actual worker.
LIVE_EXECUTION_GAPS = (
    "no hard deadline or resource bound on a delegated child: delegate_task timeoutMs limits the wait in mode=wait only and does not cancel the child",
    "credential confinement of a delegated child is not established: the child runs with the coordinator's credentials and runtime mode",
    "pre-launch task authorization, receipt binding and terminal task evidence (task_status workState result_available; task_cancel reporting a terminal state) are implemented as protocol but not qualified with an actual bounded worker; launches themselves are invisible to this tool, which bounds only what can be bound",
    "no bounded GitHub credential has passed the permission probe (denial of forbidden operations untested)",
)
TERMINAL_TASK_STATES = ("result_available", "completed", "failed", "cancelled", "terminal")
CLEANUP_KINDS = ("release", "block")
# purpose -> (phase in which the authorization is issued, phase after the receipt is bound, role)
AUTHORIZATION_FLOW = {
    "implementation": ("reserved", "claimed", "implementer"),
    "review": ("review-authorized", "review-requested", "reviewer"),
    "repair": ("repair-authorized", "claimed", "implementer"),
}


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


def require_unique_ids(snapshot: Snapshot, context: str) -> None:
    """Refuse before any ``by_id`` reduction when a stable id is carried by several issues."""
    dupes = snapshot.duplicate_ids()
    if dupes:
        raise Refused(f"{context}: duplicate stable ids {dupes} in the snapshot; identity mapping is ambiguous, nothing is admitted", code="ambiguous-identity", duplicates=dupes)


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

    def _elapsed(self) -> timedelta:
        return datetime.fromisoformat(self.now().replace("Z", "+00:00")) - datetime.fromisoformat(self.run.started_at.replace("Z", "+00:00"))

    def _run_stop(self) -> str | None:
        """Why the run admits and advances nothing any more: ``run-cancelled`` or
        ``wall-clock-exceeded`` (a local expiry; it does not stop a launched child), else None."""
        if self.run.cancelled:
            return "run-cancelled"
        if self._elapsed() > timedelta(minutes=self.policy.max_wall_clock_minutes):
            return "wall-clock-exceeded"
        return None

    def _stop_message(self, code: str) -> str:
        if code == "run-cancelled":
            return f"run is cancelled ({self.run.stop_reason})"
        return f"wall clock budget of {self.policy.max_wall_clock_minutes} minutes exceeded ({int(self._elapsed().total_seconds() // 60)} minutes elapsed since {self.run.started_at})"

    def _require_run_active(self, operation: str) -> None:
        """A cancelled run, or one past its wall-clock budget, advances nothing: no admission,
        authorization, binding into work, evidence recording or proposal. Terminal operations
        (cancel/block/record-task-terminal) and recovery stay allowed."""
        code = self._run_stop()
        if code:
            raise BudgetExhausted(f"{operation}: {self._stop_message(code)}; only cancel, block, record-task-terminal, resume and status are allowed", code=code, stop_reason=self.run.stop_reason)

    def _story(self, story: str) -> StoryState:
        state = self.store.load_story(story)
        if state is None:
            raise Refused(f"{story} has no state in run {self.store.run_id}")
        return state

    def _require_phase(self, state: StoryState, *phases: str) -> None:
        if state.phase not in phases:
            raise Refused(f"{state.story} is {state.phase}; this operation needs {phases}", phase=state.phase)

    def _counts(self) -> dict[str, int]:
        """Durable budget consumption from the story files; refreshes the run.json cache."""
        counts = self.store.story_counts()
        self.run.stories_claimed, self.run.delegated_tasks, self.run.repair_rounds = counts["stories_claimed"], counts["delegated_tasks"], counts["repair_rounds"]
        return counts

    def _wall_clock(self) -> None:
        if self._run_stop() == "wall-clock-exceeded":
            raise BudgetExhausted(self._stop_message("wall-clock-exceeded"), code="wall-clock-exceeded")

    def _budget_admission(self) -> None:
        self._wall_clock()
        counts = self._counts()
        if counts["stories_claimed"] + 1 > self.policy.max_stories_per_run:
            raise BudgetExhausted(f"story budget {self.policy.max_stories_per_run} exhausted")
        active = [s.story for s in self.store.list_stories() if s.active or s.phase == "conflict"]
        if len(active) + 1 > self.policy.max_concurrent_implementers:
            raise Refused(f"another story is active in this run: {active}", active=active)

    def _authorize(self, state: StoryState, purpose: str, sha: str | None = None, round_: int | None = None) -> dict:
        """Issue (or return the already pending) durable task authorization for ``purpose``.
        Refuses BEFORE any launch when the delegated-task budget would be exceeded. The
        authorization is counted from the moment it is saved, bound or not."""
        role = AUTHORIZATION_FLOW[purpose][2]
        self._wall_clock()  # an expired run returns no authorization, pending or new; the pending slot stays spent
        pending = state.pending_authorization()
        if pending is not None:
            if (pending["purpose"], pending["sha"], pending["round"]) == (purpose, sha, round_):
                return pending  # idempotent: the same unconsumed slot, no second count
            raise Refused(f"{state.story} already has a pending {pending['purpose']} authorization {pending['id']}; bind or abandon it first", code="authorization-pending", authorization=pending)
        counts = self._counts()
        if counts["delegated_tasks"] + 1 > self.policy.max_delegated_tasks:
            raise BudgetExhausted(f"delegated task budget {self.policy.max_delegated_tasks} exhausted ({counts['delegated_tasks']} authorizations issued); no task may be launched", issued=counts["delegated_tasks"])
        auth = {"id": f"{self.store.run_id}:{state.story}:{len(state.authorizations) + 1}", "role": role, "purpose": purpose, "sha": sha, "round": round_,
                "issued_at": self.now(), "status": "pending", "task_id": None, "reason": None}
        state.authorizations.append(auth)
        return auth

    def _abandon_authorization(self, state: StoryState, reason: str) -> dict | None:
        pending = state.pending_authorization()
        if pending is not None:
            pending["status"], pending["reason"] = "abandoned", reason  # stays counted: the slot was issued
        return pending

    def _apply_task_evidence(self, state: StoryState, task_evidence: dict | None, operation: str) -> dict | None:
        """Terminal task evidence (task_status workState result_available or a terminal
        task_cancel result) for the active task clears ownership; anything else refuses.
        Returns the history record, or None when no task is active and no evidence given."""
        active = state.active_task
        if active is None:
            if task_evidence is not None:
                raise Refused(f"{operation}: {state.story} has no active task; task evidence {task_evidence} matches nothing", code="no-active-task")
            return None
        if (not isinstance(task_evidence, dict) or task_evidence.get("taskId") != active["taskId"]
                or task_evidence.get("status") not in TERMINAL_TASK_STATES):
            raise Refused(f"{operation}: {active['role']} task {active['taskId']} of {state.story} is still owned; present terminal task evidence for exactly that task (task_status workState result_available or a terminal task_cancel result) before releasing it",
                          code="worker-not-terminal", task_id=active["taskId"], role=active["role"])
        record = {"taskId": active["taskId"], "role": active["role"], "status": task_evidence["status"], "at": self.now(), "operation": operation, "authorization": active.get("authorization")}
        state.task_history.append(record)
        state.active_task = None
        return record

    def _require_no_active_task(self, state: StoryState, operation: str) -> None:
        if state.active_task is not None:
            raise Refused(f"{operation}: {state.active_task['role']} task {state.active_task['taskId']} of {state.story} is still active; present its terminal evidence (record-task-terminal) first",
                          code="worker-not-terminal", task_id=state.active_task["taskId"], role=state.active_task["role"])

    def _fresh_snapshot(self) -> Snapshot:
        return take_snapshot(self.transport, self.policy.repo_slug, self.now())

    def _current_revisions(self, story: str, snapshot: Snapshot | None = None) -> tuple[Snapshot, dict[str, dict]]:
        fresh = snapshot or self._fresh_snapshot()
        require_unique_ids(fresh, "fresh snapshot")
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

    def _invalidate_evidence(self, state: StoryState, head: str | None, reason: str) -> list[str]:
        """Check and review evidence no longer describe the source: phase ``implemented``,
        approval cleared, pending proposal intents and a pending review authorization
        abandoned. The active task is untouched (ownership is not evidence)."""
        abandoned = state.abandon_advancing_intents(reason)
        self._abandon_authorization(state, reason)
        state.phase, state.head_sha, state.approved_sha = "implemented", head, None
        return abandoned

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
            abandoned = self._invalidate_evidence(state, head, f"unreported worktree change at {gate}: HEAD {head}, clean={clean}")
            self.store.save_story(state)
            self.store.journal(state.story, "unreported-worktree-change", {"gate": gate, "expected": sha, "head": head, "clean": clean, "dirt": dirt, "abandoned_intents": abandoned})
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

    def _post_intent(self, state: StoryState, intent: Intent, phase_after: str | None = None) -> Intent:
        """Idempotent post of a recorded intent: zero markers ⇒ post the persisted body,
        one ⇒ adopt, more ⇒ conflict. The intent's completion and the phase transition it
        carries (``phase_after``) persist in one write, so a crash cannot separate them."""
        if not self.live:
            raise Refused(f"{intent.kind} for {state.story} needs live writes (--live)", code="live-required")
        if intent.status == "done":
            if phase_after and state.phase != phase_after:
                state.phase = phase_after
                self.store.save_story(state)
                self.store.journal(state.story, "transition-reconciled", {"op": intent.op, "phase": phase_after})
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
        if phase_after:
            state.phase = phase_after
        self.store.save_story(state)  # completion and transition in one write
        return intent

    # -- admission -------------------------------------------------------------------------
    def reserve(self, story: str, snapshot: Snapshot, baseline_sha: str) -> StoryState:
        """Admission BEFORE any delegated task exists: budgets (stories and delegated tasks),
        unique identity and eligibility on the plan snapshot and on a fresh read, no foreign
        claim, implementer authorization, claim marker. The receipt of the task the
        coordinator then launches is bound with :meth:`bind_receipt`."""
        with self.store.locked(self):
            self.require_not_live("reserve")
            self._reload_run()
            self._require_run_active("reserve")
            if self.store.load_story(story) is not None:
                raise Refused(f"{story} already has state in run {self.store.run_id}; a story is admitted at most once per run (no reclaim)", code="no-reclaim")
            require_unique_ids(snapshot, "plan snapshot")
            decision: Decision = decide(story, snapshot, self.policy)
            if not decision.dispatchable:
                raise Refused(f"{story} is not dispatchable: {decision.outcome} ({'; '.join(decision.reasons)})", decision=decision.as_dict())
            self._budget_admission()
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
            auth = self._authorize(state, "implementation")  # refuses before any save or post when the task budget is spent
            intent = self._new_intent(state, "claim", "claim", f"Unattended reservation by run `{self.store.run_id}` from `{baseline_sha}` (scope: {decision.outcome}). An implementer task is delegated only after this reservation; its receipt is bound to the reservation. Project Status is owner-maintained; completion still requires checks, independent review and owner acceptance.", {"revisions": current})
            self.store.save_story(state)
            self.store.journal(story, "reserved", {"issue": entry.number, "baseline": baseline_sha, "scope": decision.outcome, "authorization": auth["id"]})
            self._counts()
            self.store.save_run(self.run)
            self._post_intent(state, intent, phase_after="reserved")
            return state

    def bind_receipt(self, story: str, receipt: dict, worktree_path: str | None = None, branch: str | None = None, worktree_check: WorktreeCheck = git_worktree_check) -> StoryState:
        """Bind the delegated task's receipt to the story's pending authorization, consuming
        it: implementation (needs the worktree identity), review or repair (re-check the
        bound worktree). Exactly one bind per authorization; no authorization ⇒ refused. The
        task id must be fresh run-wide (never bound in any story or role, terminal or not).

        If the run stopped (cancelled or past its wall clock) after the authorization was
        issued, the task may already have been launched: the receipt still binds, but for
        cleanup only. The slot stays spent, the task id stays bound, the task becomes the
        story's active task (released only by its terminal evidence) and the phase does not
        advance; the call then refuses with ``bound_for_cleanup`` so the coordinator cancels
        the task instead of working it. Nothing is refunded."""
        with self.store.locked(self):
            self.require_not_live("bind-receipt")
            self._reload_run()
            state = self._story(story)
            stop = self._run_stop()
            auth = state.pending_authorization()
            if auth is None:
                if stop:
                    raise BudgetExhausted(f"bind-receipt: {self._stop_message(stop)}; nothing is authorized for {story}", code=stop, stop_reason=self.run.stop_reason)
                raise Refused(f"{story} has no pending task authorization; reserve / authorize-review / authorize-repair must precede every launch, and each authorization binds once", code="no-authorization")
            issued_phase, next_phase, role = AUTHORIZATION_FLOW[auth["purpose"]]
            self._require_phase(state, issued_phase)
            self._require_no_active_task(state, "bind-receipt")
            target: Target = self.policy.implementer if role == "implementer" else self.policy.reviewer
            receipt = validate_receipt(receipt, target, role, self.store.bound_task_ids())  # run-wide freshness, every story and role, kept through terminal phases
            if auth["purpose"] == "implementation":
                if not worktree_path or not branch:
                    raise Refused("bind-receipt for the implementation task needs --worktree and --branch")
            else:
                worktree_path, branch = state.claim["worktree_path"], state.claim["branch"]
            ok, why = worktree_check(worktree_path, branch)
            if not ok:
                raise Refused(f"worktree identity check failed: {why}", code="worktree-mismatch")
            if auth["purpose"] == "implementation":
                state.claim.update({"worktree_path": worktree_path, "branch": branch, "claimed_at": self.now()})
            auth["status"], auth["task_id"] = "consumed", receipt["taskId"]
            if role == "implementer":
                state.implementer_receipts.append(receipt)
            else:
                state.reviewer_receipts.append({**receipt, "sha": auth["sha"]})
            state.active_task = {"taskId": receipt["taskId"], "role": role, "authorization": auth["id"], "bound_at": self.now()}
            if stop:
                # Authorized before the run stopped, possibly launched: keep the slot spent, the id bound
                # and the task owned; authorize no work and leave the phase where the authorization was issued.
                auth["cleanup_only"] = stop
                state.active_task["cleanup_only"] = stop
                self.store.save_story(state)
                self._counts()
                self.store.save_run(self.run)
                self.store.journal(story, "receipt-bound-cleanup-only", {"task": receipt["taskId"], "role": role, "purpose": auth["purpose"], "authorization": auth["id"], "stop": stop, "phase": state.phase})
                raise BudgetExhausted(f"bind-receipt: {self._stop_message(stop)}; {role} task {receipt['taskId']} is bound to {story} for cleanup only (slot spent, ownership kept, phase {state.phase} unchanged, no work authorized): cancel it and present its terminal evidence",
                                      code=stop, task_id=receipt["taskId"], role=role, bound_for_cleanup=True, stop_reason=self.run.stop_reason)
            state.phase = next_phase
            self.store.save_story(state)
            self._counts()
            self.store.save_run(self.run)
            self.store.journal(story, "receipt-bound", {"task": receipt["taskId"], "role": role, "purpose": auth["purpose"], "authorization": auth["id"], "branch": branch, "worktree": worktree_path})
            return state

    def record_task_terminal(self, story: str, task_evidence: dict) -> StoryState:
        """Role-agnostic acknowledgment that the active task is terminal. The only way, with
        the evidence arguments of record-head, record-review, cancel and block, to release
        task ownership; it changes no other state."""
        with self.store.locked(self):
            self.require_not_live("record-task-terminal")
            state = self._story(story)
            record = self._apply_task_evidence(state, task_evidence, "record-task-terminal")
            self.store.save_story(state)
            self.store.journal(story, "task-terminal", record or {})
            return state

    # -- implementation ---------------------------------------------------------------------
    def record_head(self, story: str, sha: str, task_evidence: dict | None = None) -> StoryState:
        """Record the implementer's exact commit. While an implementer task is active its
        terminal evidence is required; a reviewer task stays active regardless (the head is
        not the reviewer's). The same SHA changes nothing; a new SHA invalidates evidence."""
        with self.store.locked(self):
            self.require_not_live("record-head")
            self._reload_run()
            self._require_run_active("record-head")
            state = self._story(story)
            if state.phase in ("checks-failed", "changes-requested", "repair-authorized"):
                raise Refused(f"{story} is {state.phase}; a new implementation needs a budgeted repair authorization bound to a fresh task first", code="repair-required", phase=state.phase)
            self._require_phase(state, "claimed", "implemented", "checks-passed", "review-authorized", "review-requested", "review-approved")
            if task_evidence is not None or (state.active_task and state.active_task["role"] == "implementer"):
                self._apply_task_evidence(state, task_evidence, "record-head")
            if state.head_sha == sha and state.phase != "claimed":
                self.store.save_story(state)
                self.store.journal(story, "head-unchanged", {"sha": sha, "phase": state.phase, "active_task": state.active_task})
                return state
            invalidated = state.phase in ("review-authorized", "review-requested", "review-approved")
            abandoned = self._invalidate_evidence(state, sha, f"new head {sha} recorded") if invalidated else []
            state.head_sha, state.phase, state.approved_sha = sha, "implemented", None
            self.store.save_story(state)
            self.store.journal(story, "head-recorded", {"sha": sha, "approval_invalidated": invalidated, "abandoned_intents": abandoned, "active_task": state.active_task})
            return state

    def run_checks(self, story: str, sha: str, cwd: str, runner=None) -> StoryState:
        """Execute the full configured check set on the exact claimed HEAD in a clean tree.
        This is the only way checks become evidence; there is no asserted pass."""
        with self.store.locked(self):
            self.require_not_live("run-checks")
            self._reload_run()
            self._require_run_active("run-checks")
            state = self._story(story)
            self._require_phase(state, "implemented", "checks-passed", "checks-failed")
            self._require_no_active_task(state, "run-checks")
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

    def authorize_review(self, story: str, sha: str) -> StoryState:
        """Pre-launch authorization of the reviewer task at the exact checked commit: full
        check set passed at ``sha``, worktree re-read, implementer task terminal, delegated
        task budget. Idempotent while the authorization is pending."""
        with self.store.locked(self):
            self.require_not_live("authorize-review")
            self._reload_run()
            self._require_run_active("authorize-review")
            state = self._story(story)
            self._require_phase(state, "checks-passed", "review-authorized")
            last = state.checks[-1] if state.checks else None
            configured = len(self.policy.check_commands)
            if (state.head_sha != sha or not last or last["sha"] != sha or not last["passed"] or not last.get("executed")
                    or len(last.get("commands", [])) != configured or any(c.get("returncode") != 0 for c in last["commands"])
                    or last.get("head_after") != sha or not last.get("clean_after")):
                raise Refused(f"the full configured check set ({configured} commands) has not been executed and passed at {sha}")
            self._verify_worktree(state, sha, "authorize-review")
            self._require_no_active_task(state, "authorize-review")
            auth = self._authorize(state, "review", sha=sha)
            state.phase = "review-authorized"
            self.store.save_story(state)
            self._counts()
            self.store.save_run(self.run)
            self.store.journal(story, "review-authorized", {"sha": sha, "authorization": auth["id"]})
            return state

    def authorize_repair(self, story: str) -> StoryState:
        """Pre-launch authorization of a repair implementer task: previous task terminal,
        round ≤ max (otherwise blocked), delegated task budget. The round is counted at
        authorization. Idempotent while the authorization is pending."""
        with self.store.locked(self):
            self.require_not_live("authorize-repair")
            self._reload_run()
            self._require_run_active("authorize-repair")
            state = self._story(story)
            self._require_phase(state, "checks-failed", "changes-requested", "repair-authorized")
            self._require_no_active_task(state, "authorize-repair")
            pending = state.pending_authorization()
            if pending is not None and pending["purpose"] == "repair":
                return state
            if state.repair_rounds + 1 > self.policy.max_repair_rounds:
                self.store.journal(story, "repair-refused", {"rounds": state.repair_rounds})
                return self.block(story, f"repair rounds exhausted ({self.policy.max_repair_rounds}); unresolved after {state.phase}")
            auth = self._authorize(state, "repair", round_=state.repair_rounds + 1)
            state.repair_rounds += 1
            state.phase = "repair-authorized"
            self.store.save_story(state)
            self._counts()
            self.store.save_run(self.run)
            self.store.journal(story, "repair-authorized", {"round": state.repair_rounds, "authorization": auth["id"]})
            return state

    def record_review(self, story: str, sha: str, verdict: str, report: str, task_evidence: dict | None = None) -> StoryState:
        with self.store.locked(self):
            self.require_not_live("record-review")
            self._reload_run()
            self._require_run_active("record-review")
            state = self._story(story)
            if verdict not in ("approved", "changes-requested"):
                raise Refused("verdict must be approved or changes-requested")
            self._require_phase(state, "review-requested", "review-approved")
            if state.head_sha != sha:
                raise Refused(f"review at {sha} does not match head {state.head_sha}; a code change invalidates it", head=state.head_sha)
            if task_evidence is not None or state.active_task is not None:
                self._apply_task_evidence(state, task_evidence, "record-review")  # the reviewer must be terminal before its verdict is evidence
            self._verify_worktree(state, sha, "record-review")
            regression = state.phase == "review-approved" and verdict == "changes-requested"
            state.reviews.append({"sha": sha, "verdict": verdict, "report": report, "at": self.now(), "regression": regression})
            abandoned: list[str] = []
            if verdict == "approved":
                state.phase, state.approved_sha = "review-approved", sha
            else:
                state.phase, state.approved_sha = "changes-requested", None
                abandoned = state.abandon_advancing_intents(f"local review changes-requested at {sha}")
            self.store.save_story(state)
            self.store.journal(story, "review-recorded", {"sha": sha, "verdict": verdict, "regression": regression, "abandoned_intents": abandoned})
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
            abandoned = state.abandon_advancing_intents(f"review regression on PR #{pr_number} by {objections}")
            self.store.save_story(state)
            self.store.journal(state.story, "review-regression-on-github", {"pr": pr_number, "sha": sha, "reviewers": objections, "abandoned_intents": abandoned})
            raise Refused(f"PR #{pr_number} has outstanding CHANGES_REQUESTED from {objections}; approval invalid")
        if pr.checks == "FAILURE":
            raise Refused(f"PR #{pr_number} status checks failed at {sha}")
        return pr

    def _require_current_approval(self, state: StoryState, sha: str, operation: str) -> None:
        """A proposal (first attempt or replay) needs the current local state to approve
        exactly ``sha``: phase review-approved, approved and head SHA equal to it, no active task."""
        self._require_phase(state, "review-approved")
        if state.head_sha != sha or state.approved_sha != sha:
            raise Refused(f"{operation}: approval is for {state.approved_sha}, head is {state.head_sha}, proposal names {sha}", code="approval-mismatch")
        self._require_no_active_task(state, operation)

    def propose_evidence(self, story: str, sha: str, pr_number: int, tasks: list[str], summary: str) -> StoryState:
        with self.store.locked(self):
            self.require_not_live("propose-evidence")
            self._reload_run()
            self._require_run_active("propose-evidence")
            state = self._story(story)
            self._require_current_approval(state, sha, "propose-evidence")
            self._check_revisions(state)
            self._verify_worktree(state, sha, "propose-evidence")
            pr = self._validate_pr(state, sha, pr_number)
            op = f"proposal-{sha[:12]}-pr{pr_number}"
            intent = state.intent(op)
            if intent is None or intent.status == "abandoned":
                task_lines = "\n".join(f"- [ ] {t}" for t in tasks) or "- (no task completion proposed)"
                body = (f"Evidence proposal from run `{self.store.run_id}` at exact commit `{sha}` (PR #{pr_number}, CI rollup: {pr.checks or 'pending'}).\n"
                        f"{summary}\n\nProposed task completion for owner application (the machine does not tick checkboxes or change Project Status):\n{task_lines}\n\n"
                        "Checked boxes, CI pass, review approval, acceptance, merge and deployment remain distinct facts; this comment records review-approved implementation only.")
                if intent is not None:  # a re-approval at the same commit after an abandoned attempt reuses the operation identity
                    intent.status, intent.reason, intent.body, intent.preconditions = "pending", None, f"{render_marker(**intent.marker)}\n{body}", {"sha": sha, "pr": pr_number, "revisions": dict(state.revisions)}
                else:
                    intent = self._new_intent(state, op, "proposal", body, {"sha": sha, "pr": pr_number, "revisions": dict(state.revisions)}, sha=sha, pr=str(pr_number))
                state.proposal = {"sha": sha, "pr": pr_number, "tasks": tasks, "at": self.now(), "ci": pr.checks}
                self.store.save_story(state)
            self._post_intent(state, intent, phase_after="proposed")
            self.store.journal(story, "proposed", {"sha": sha, "pr": pr_number})
            return state

    # -- terminal -------------------------------------------------------------------------
    def _terminal(self, story: str, phase: str, reason: str, op: str, kind: str, body: str, task_evidence: dict | None) -> StoryState:
        state = self._story(story)
        self._require_phase(state, *ACTIVE_PHASES, "conflict")
        # refuses while a task is owned without its terminal evidence; evidence for no active task releases nothing
        evidence = self._apply_task_evidence(state, task_evidence, phase) if state.active_task is not None else None
        abandoned = state.abandon_advancing_intents(f"story {phase}: {reason}")
        self._abandon_authorization(state, f"story {phase}: {reason}")
        state.blocked = {"reason": reason, "at": self.now(), "from_phase": state.phase, "cancelled": phase == "cancelled", "task_evidence": task_evidence, "abandoned_intents": abandoned}
        state.phase = phase
        intent = self._new_intent(state, op, kind, body)
        self.store.save_story(state)  # terminal phase, cleanup intent and abandonments persist together
        self.store.journal(story, phase, {"reason": reason, "abandoned_intents": abandoned, "task_evidence": evidence})
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
        """Stop admissions and release every story whose task is terminal. Stories with an
        active task and no terminal evidence stay owned and are reported; a cancelled run
        never advances or replays an advancing intent for them."""
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
                    awaiting.append({"story": s.story, "task_id": exc.detail.get("task_id"), "role": exc.detail.get("role")})
            return {"cancelled": released, "awaiting_worker_termination": awaiting}

    # -- recovery -------------------------------------------------------------------------
    def _cancel_stale_claim(self, state: StoryState, claim: Intent, changed: dict) -> StoryState:
        """The reservation can no longer complete: its revisions changed before it was
        checkpointed. The story is cancelled and, when the claim comment reached GitHub (one
        or more markers), the release it owes is recorded as a cleanup intent in the same
        write as the cancellation, then posted idempotently; a failed post leaves it pending
        and the next resume replays it. Zero markers ⇒ the claim never landed, no release is
        owed. A done claim keeps its ``done`` record (history); a pending one is abandoned."""
        reason = f"revisions changed before the reservation completed: {sorted(changed)}"
        found = [c for c in self.transport.list_comments(state.issue) if c.marker == claim.marker]
        abandoned = state.abandon_advancing_intents(reason)
        self._abandon_authorization(state, reason)
        state.phase = "cancelled"
        state.blocked = {"reason": reason, "at": self.now(), "from_phase": "claim-incomplete", "cancelled": True, "changed": sorted(changed),
                         "claim_comment_ids": [c.comment_id for c in found], "release_owed": bool(found), "abandoned_intents": abandoned}
        release = self._new_intent(state, "release", "release", f"Claim released by run `{self.store.run_id}`: {reason}. No completion is implied. Project Status is owner-maintained.") if found else None
        self.store.save_story(state)  # cancellation and the owed cleanup persist together
        self.store.journal(state.story, "resume-claim-abandoned", {"changed": sorted(changed), "claim_markers": len(found), "release_owed": release is not None})
        if len(found) > 1:
            self.store.journal(state.story, "duplicate-marker-detected", {"op": claim.op, "comment_ids": [c.comment_id for c in found]})
        if release is not None:
            try:
                self._post_intent(state, release)
            except UnattendedError as exc:
                state.blocked["github_error"] = exc.as_dict()
                self.store.save_story(state)
                self.store.journal(state.story, "cancelled-github-write-failed", exc.as_dict())
        return state

    def _withhold_reconciliation(self, state: StoryState, intent: Intent, why: str) -> None:
        """A completed advancing intent whose transition cannot be applied: its effect stays
        recorded (comment id, status done), the phase is not advanced, the reason is journaled."""
        self.store.journal(state.story, "reconciliation-withheld", {"op": intent.op, "comment_id": intent.comment_id, "phase": state.phase, "reason": why})

    def resume(self, story: str, worktree_check: WorktreeCheck = git_worktree_check) -> StoryState:
        """Restart recovery. Order: live gate, ownership identity, cleanups replayed
        unconditionally, completed advancing intents reconciled with their transition only
        behind the guards of a fresh attempt (run not cancelled; for a claim: unchanged
        revisions, otherwise cancelled with its release; for a proposal: phase
        ``review-approved``, exact-SHA approval and head, no active task), then pending
        advancing replays only for an active story in a run that is neither cancelled nor past
        its wall clock and only after their preconditions (local phase and exact-SHA approval,
        revisions, worktree, PR) re-verify; otherwise they are abandoned. Finally the revision
        verification."""
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
            stop = self._run_stop()
            # Completed advancing intents whose transition did not persist (legacy or partial state):
            # the effect is history and stays recorded; the transition applies only where a fresh
            # attempt would be allowed. A cancelled run advances nothing (cancel-run finishes the story).
            claim = state.intent("claim")
            if claim is not None and claim.status == "done" and state.phase == "claim-incomplete":
                if self.run.cancelled:
                    self._withhold_reconciliation(state, claim, "run is cancelled")
                else:
                    fresh, current = self._current_revisions(story)
                    changed = revision_diff(claim.preconditions.get("revisions", state.revisions), current)
                    if changed:
                        return self._cancel_stale_claim(state, claim, changed)
                    self._post_intent(state, claim, phase_after="reserved")
            for intent in state.intents:
                if intent.kind != "proposal" or intent.status != "done" or state.phase == "proposed":
                    continue
                sha = intent.preconditions.get("sha")
                if self.run.cancelled:
                    self._withhold_reconciliation(state, intent, "run is cancelled")
                elif state.phase != "review-approved" or state.approved_sha != sha or state.head_sha != sha or state.active_task is not None:
                    self._withhold_reconciliation(state, intent, f"no current approval for {sha}: phase {state.phase}, approved {state.approved_sha}, head {state.head_sha}, active task {state.active_task}")
                else:
                    self._post_intent(state, intent, phase_after="proposed")
            pending_advancing = state.pending_advancing_intents()
            if pending_advancing and (not state.active or stop):
                why = {"run-cancelled": "run is cancelled", "wall-clock-exceeded": "run wall clock budget exceeded"}.get(stop) if stop else f"story is {state.phase}"
                abandoned = state.abandon_advancing_intents(f"not replayed on resume: {why}")
                self.store.save_story(state)
                self.store.journal(story, "resume-advancing-abandoned", {"reason": why, "ops": abandoned})
                pending_advancing = []
            for intent in pending_advancing:
                if intent.kind == "claim":
                    fresh, current = self._current_revisions(story)
                    changed = revision_diff(intent.preconditions.get("revisions", state.revisions), current)
                    if changed:
                        return self._cancel_stale_claim(state, intent, changed)
                    self._post_intent(state, intent, phase_after="reserved" if state.phase == "claim-incomplete" else None)
                    self.store.journal(story, "reservation-completed-on-resume", {})
                elif intent.kind == "proposal":
                    sha = intent.preconditions["sha"]
                    if state.phase != "review-approved" or state.approved_sha != sha or state.head_sha != sha or state.active_task is not None:
                        intent.status, intent.reason = "abandoned", f"no current approval for {sha}: phase {state.phase}, approved {state.approved_sha}, head {state.head_sha}, active task {state.active_task}"
                        self.store.save_story(state)
                        self.store.journal(story, "resume-proposal-abandoned", {"op": intent.op, "reason": intent.reason})
                        continue
                    self._check_revisions(state)
                    self._verify_worktree(state, sha, "resume-proposal")
                    self._validate_pr(state, sha, int(intent.preconditions["pr"]))
                    self._post_intent(state, intent, phase_after="proposed")
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
        with self.store.locked(self):
            counts = self._counts()
        return {"run": self.run.__dict__, "budgets": counts, "environment": self.environment, "stories": [s.to_dict() for s in self.store.list_stories()], "journal_events": self.store.journal_count(), "live": self.live, "gaps": list(LIVE_EXECUTION_GAPS)}
