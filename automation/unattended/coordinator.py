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
    review-authorized | review-requested | review-approved ──record-head(new sha) | unreported worktree change──> implemented (evidence invalidated; pending proposal abandoned; pending review authorization revoked, still owned)
    any phase with an unresolved authorization ──cancel | block | cancel-run | run-checks | authorize-* | propose──> REFUSED (authorization-unresolved); its late receipt binds for cleanup only; record-no-launch resolves it
    review-approved ──propose-evidence (revisions unchanged, worktree re-read, PR head/reviews/checks)──> proposed
    any active | conflict ──block | cancel (terminal evidence for the active task)──> blocked | cancelled (pending advancing intents abandoned)
    duplicate marker ──> conflict

Task capacity is authorized durably BEFORE a launch (``reserve``, ``authorize-review``,
``authorize-repair``); every issued authorization counts against ``max_delegated_tasks``
whether or not it is ever bound, ``bind-receipt`` consumes exactly one authorization — the
exact one named by its id (or the single unresolved one) — and budgets are derived from the
story files under the lock, never from cached counters. A receipt is fresh only if its task id
was never bound anywhere in the run (any story, any role, terminal or not).

An issued authorization is an ownership obligation until it is resolved: a launch is invisible
to this tool, so an unbound authorization may already have a running task behind it. It is
resolved only by the exact receipt of its task followed by that task's terminal evidence, or by
a positive no-launch reconciliation: the coordinator's explicit attestation
(``record-no-launch`` naming the authorization id) or the structural proof that the operation
which issued it never returned (a reservation still in ``claim-incomplete``). Cancelling or
blocking the story, invalidating the evidence and stopping the run do not resolve it: they
*revoke* it (no work is authorized any more), its late receipt binds for cleanup only, and the
claim, the concurrency slot and the story stay owned — no release, no replacement authorization
— until the obligation is resolved. The active task (id and role) is likewise independent of
the phase: HEAD recording, review verdicts and evidence invalidation never release ownership;
only terminal task evidence does.

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
behind the same gates as a fresh attempt (run neither cancelled nor past its wall clock,
matching phase, exact-SHA approval, no active task or unresolved authorization, then fresh
revisions with unique identities, the re-read worktree and the PR); otherwise its effect stays
recorded as history and the phase is not advanced. A reservation whose revisions changed before it was checkpointed is cancelled
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
from .receipts import execution_run_id, validate_receipt
from .state import ACTIVE_PHASES, UNRESOLVED_AUTHORIZATION_STATUSES, Intent, Store, StoryState, utcnow

WorktreeCheck = Callable[[str, str], tuple[bool, str]]

# What the installed T3 tools do not establish; verified against the tool metadata. The
# protocol itself (authorize under the lock before delegate_task, bind the receipt afterwards,
# keep ownership until task_status/task_cancel report a terminal state) is supported by the
# tools and implemented below, but it has not been qualified with an actual worker.
OPERATING_AGREEMENT = "trusted-machine operating agreement accepted by the owner on 2026-11-06 (spec-eng-01-trusted-operation.md)"
# Why real-transport state commands are still refused, stated under the accepted agreement. These are
# the current reasons, not the superseded strict prerequisites (hard child bounds, exhaustive
# credential-denial qualification, automated Project Status synchronization). Accepting a residual
# risk is not activation: the gate stays unconditional for this effort.
LIVE_EXECUTION_GAPS = (
    "live execution is disabled for this effort: product dispatch and every real-transport state command stay refused until the engineering-only lifecycle smoke (real T3 receipts and terminal evidence, exact-SHA checks and a fresh independent review) is published and the owner separately authorizes activation",
    "accepted residual risk, not a control: budgets are coordinator-enforced best effort (stop dispatch and request cancellation on expiry); a coordinator failure can leave a worker running; T3 timeoutMs bounds only the wait",
    "accepted residual risk, not a control: the operator's development machine is trusted; worktrees isolate files, not host credentials; the child runs with the machine's credentials and no credential confinement is claimed",
    "disclosed, not certified: the operator credential is broad (repository admin, excess scopes); check-permissions reports facts only and never certifies a bounded credential; restricted credentials are used where practical",
    "manual by agreement: Project Status and acceptance are owner actions; machine comments are evidence proposals, not synchronization",
)
TERMINAL_TASK_STATES = ("result_available", "completed", "failed", "cancelled", "terminal")
CLEANUP_KINDS = ("release", "block")
# purpose -> (phase in which the authorization is issued, phase after the receipt is bound, role)
AUTHORIZATION_FLOW = {
    "implementation": ("reserved", "claimed", "implementer"),
    "review": ("review-authorized", "review-requested", "reviewer"),
    "repair": ("repair-authorized", "claimed", "implementer"),
}
STOP_REASONS = {"run-cancelled": "run is cancelled", "wall-clock-exceeded": "run wall clock budget exceeded"}


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


def normalize_task_evidence(task_evidence) -> dict:
    """Canonical terminal evidence ``{taskId, runId, status, shape}`` from either shape the
    coordinator can report:

    - normalized: ``{"taskId", "runId", "status"}`` with a terminal status;
    - task_status-shaped: ``{"taskId", "workState": "result_available", "hasPendingChildRuns": false,
      "latestTerminalRunId", "latestTerminalStatus"}``. The run and status come ONLY from the
      latest terminal fields; ``childRunId``, ``status`` and ``summary`` are the stale first-run
      fields and are ignored. Live or pending child work, a missing latest terminal run, a
      non-terminal or ``cancel_requested`` status, or a disagreement between the two shapes
      refuses; nothing is inferred."""
    if not isinstance(task_evidence, dict) or not task_evidence.get("taskId"):
        raise Refused("terminal evidence must be a JSON object naming taskId", code="worker-not-terminal")
    task_id = str(task_evidence["taskId"])
    has_status_shape = any(k in task_evidence for k in ("workState", "latestTerminalRunId", "latestTerminalStatus", "hasPendingChildRuns"))
    if has_status_shape:
        if task_evidence.get("workState") != "result_available":
            raise Refused(f"task_status reports workState {task_evidence.get('workState')!r}; the task is not terminal", code="worker-not-terminal", work_state=task_evidence.get("workState"))
        if task_evidence.get("hasPendingChildRuns") not in (False, 0):
            raise Refused("task_status reports pending child work; the task is not terminal", code="worker-not-terminal", pending_children=task_evidence.get("hasPendingChildRuns"))
        run_id, status = task_evidence.get("latestTerminalRunId"), task_evidence.get("latestTerminalStatus")
        if not run_id or not status:
            raise Refused("task_status carries no latestTerminalRunId/latestTerminalStatus; the terminal execution cannot be identified (childRunId/status/summary are stale first-run fields and are not used)", code="run-identity-missing")
        declared = task_evidence.get("runId")
        if declared and str(declared) != str(run_id):
            raise Refused(f"evidence declares runId {declared} but task_status's latest terminal run is {run_id}; ambiguous", code="run-identity-ambiguous")
        declared_status = task_evidence.get("status")
        if declared_status and declared_status != status and "workState" in task_evidence:
            # a plain `status` next to task_status fields is the stale first-run status; ignored, but it must not be the only terminal claim
            pass
        shape = "task_status"
    else:
        run_id, status, shape = task_evidence.get("runId"), task_evidence.get("status"), "normalized"
    if status == "cancel_requested" or status not in TERMINAL_TASK_STATES:
        raise Refused(f"status {status!r} is not terminal (cancel_requested is a request, not an acknowledgement)", code="worker-not-terminal", status=status)
    if not run_id:
        raise Refused("terminal evidence carries no runId; the execution cannot be identified and is not inferred", code="run-identity-missing")
    return {"taskId": task_id, "runId": str(run_id), "status": str(status), "shape": shape}


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
            raise Refused(f"{operation}: live execution is disabled for this effort ({OPERATING_AGREEMENT}); accepting residual risk is not activation", code="live-execution-disabled", agreement=OPERATING_AGREEMENT, gaps=list(LIVE_EXECUTION_GAPS))

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
        unresolved = state.unresolved_authorization()
        if unresolved is not None:
            if unresolved["status"] == "pending" and (unresolved["purpose"], unresolved["sha"], unresolved["round"]) == (purpose, sha, round_):
                return unresolved  # idempotent: the same unconsumed slot, no second count
            if unresolved["status"] == "pending":
                raise Refused(f"{state.story} already has a pending {unresolved['purpose']} authorization {unresolved['id']}; bind it or attest no launch (record-no-launch) first", code="authorization-pending", authorization=unresolved)
            raise self._unresolved_refusal(state, f"authorize {purpose}", unresolved)  # revoked: a task may run for it; no replacement until it is resolved
        counts = self._counts()
        if counts["delegated_tasks"] + 1 > self.policy.max_delegated_tasks:
            raise BudgetExhausted(f"delegated task budget {self.policy.max_delegated_tasks} exhausted ({counts['delegated_tasks']} authorizations issued); no task may be launched", issued=counts["delegated_tasks"])
        auth = {"id": f"{self.store.run_id}:{state.story}:{len(state.authorizations) + 1}", "role": role, "purpose": purpose, "sha": sha, "round": round_,
                "issued_at": self.now(), "status": "pending", "task_id": None, "reason": None}
        state.authorizations.append(auth)
        return auth

    def _revoke_authorization(self, state: StoryState, reason: str) -> dict | None:
        """The pending authorization no longer authorizes work, but it stays an unresolved
        obligation (a task may have been launched for it): its receipt binds for cleanup only
        and nothing is released or re-issued until it is resolved. Stays counted."""
        pending = state.pending_authorization()
        if pending is not None:
            pending["status"], pending["reason"], pending["revoked_at"] = "revoked", reason, self.now()
        return pending

    def _resolve_not_launched(self, state: StoryState, auth: dict, reason: str, source: str) -> dict:
        """Positive no-launch reconciliation of an unresolved authorization (in memory; the
        caller saves and journals). The slot stays counted: an issued slot is spent."""
        auth["status"], auth["reason"], auth["resolved_at"], auth["resolution"] = "not-launched", reason, self.now(), source
        return auth

    def _unreturned_authorization(self, state: StoryState) -> dict | None:
        """The one structural no-launch proof this tool has: the implementation authorization
        of a reservation that never returned (phase still ``claim-incomplete``, or ``conflict``
        entered from it). The protocol launches only after ``reserve`` reports ``reserved``, so
        no task can exist for it. Resolved in memory; the caller saves and journals."""
        auth = state.unresolved_authorization()
        if auth is None or auth["purpose"] != "implementation":
            return None
        never_returned = state.phase == "claim-incomplete" or (state.phase == "conflict" and (state.blocked or {}).get("from_phase") == "claim-incomplete")
        if not never_returned:
            return None
        return self._resolve_not_launched(state, auth, "reservation never returned to the coordinator (claim-incomplete); the protocol launches only after reserve reports reserved", "structural")

    def _apply_no_launch(self, state: StoryState, no_launch: dict, operation: str) -> dict:
        """The coordinator's explicit attestation that no task was launched for exactly the
        named authorization. It is a report, like a receipt or terminal evidence, and the only
        positive no-launch evidence besides the structural proof; it never applies to a
        consumed or already resolved authorization. In memory; the caller saves and journals."""
        if not isinstance(no_launch, dict) or not no_launch.get("authorization"):
            raise Refused(f'{operation}: a no-launch attestation names the exact authorization id: {{"authorization": "<id>", "reason": "..."}}', code="no-launch-invalid")
        auth = state.authorization(str(no_launch["authorization"]))
        if auth is None:
            raise Refused(f"{operation}: {state.story} has no authorization {no_launch['authorization']}", code="no-launch-invalid", authorization=str(no_launch["authorization"]))
        if auth["status"] not in UNRESOLVED_AUTHORIZATION_STATUSES:
            raise Refused(f"{operation}: authorization {auth['id']} is {auth['status']} (task {auth.get('task_id')}); a no-launch attestation applies only to an unresolved authorization", code="no-launch-invalid", authorization=auth["id"], status=auth["status"], task_id=auth.get("task_id"))
        return self._resolve_not_launched(state, auth, f"coordinator attested no launch: {no_launch.get('reason') or 'no reason given'}", "attested")

    def _unresolved_refusal(self, state: StoryState, operation: str, unresolved: dict) -> Refused:
        return Refused(f"{operation}: {unresolved['role']} authorization {unresolved['id']} of {state.story} ({unresolved['purpose']}, sha {unresolved['sha']}) is {unresolved['status']} and unresolved; a task may have been launched for it. "
                       f"Bind its receipt (bind-receipt --authorization {unresolved['id']}) and present that task's terminal evidence, or attest that no task was launched (record-no-launch), before anything is released or re-issued",
                       code="authorization-unresolved", authorization=unresolved["id"], role=unresolved["role"], purpose=unresolved["purpose"], sha=unresolved["sha"], status=unresolved["status"], task_id=None)

    def _settle_authorizations(self, state: StoryState, operation: str, reason: str, no_launch: dict | None) -> list[str]:
        """Before a story can be released: resolve the structurally unlaunched authorization,
        apply an explicit no-launch attestation, then refuse while an authorization is still
        unresolved — revoking a pending one durably so that its late receipt binds for
        cleanup only. Returns the ids resolved here."""
        resolved = []
        unreturned = self._unreturned_authorization(state)
        if unreturned is not None:
            resolved.append(unreturned["id"])
        if no_launch is not None:
            resolved.append(self._apply_no_launch(state, no_launch, operation)["id"])
        unresolved = state.unresolved_authorization()
        if unresolved is None:
            return resolved
        if unresolved["status"] == "pending":
            self._revoke_authorization(state, f"story {operation} requested: {reason}")
            self.store.save_story(state)  # the revocation is durable even though the release is refused
            self.store.journal(state.story, "authorization-revoked", {"authorization": unresolved["id"], "role": unresolved["role"], "purpose": unresolved["purpose"], "sha": unresolved["sha"], "operation": operation, "reason": reason})
        raise self._unresolved_refusal(state, operation, unresolved)

    def _apply_task_evidence(self, state: StoryState, task_evidence: dict | None, operation: str) -> dict | None:
        """Terminal task evidence for exactly the active execution ``(taskId, runId)`` clears
        ownership; anything else refuses. Returns the history record, or None when no task is
        active and no evidence given. A legacy active task without a run id cannot be matched
        and stays owned: the missing fact is reported, never inferred."""
        active = state.active_task
        if active is None:
            if task_evidence is not None:
                raise Refused(f"{operation}: {state.story} has no active task; task evidence {task_evidence} matches nothing", code="no-active-task")
            return None
        try:
            evidence = normalize_task_evidence(task_evidence)
        except Refused as exc:
            raise Refused(f"{operation}: {active['role']} task {active['taskId']} of {state.story} is still owned; {exc}", code=exc.code, task_id=active["taskId"], role=active["role"], authorization=active.get("authorization"), **exc.detail) from exc
        if evidence["taskId"] != active["taskId"]:
            raise Refused(f"{operation}: {active['role']} task {active['taskId']} of {state.story} is still owned; the evidence names task {evidence['taskId']}",
                          code="worker-not-terminal", task_id=active["taskId"], role=active["role"], authorization=active.get("authorization"))
        if not active.get("runId"):
            raise Refused(f"{operation}: {active['role']} task {active['taskId']} of {state.story} was bound without a run identity (legacy task-only record); its execution cannot be matched to terminal evidence for run {evidence['runId']} and is not inferred; it stays owned",
                          code="run-identity-missing", task_id=active["taskId"], role=active["role"], authorization=active.get("authorization"), evidence_run=evidence["runId"])
        if evidence["runId"] != active["runId"]:
            raise Refused(f"{operation}: {active['role']} task {active['taskId']} of {state.story} is still owned; the evidence is for run {evidence['runId']}, the bound execution is run {active['runId']}",
                          code="run-mismatch", task_id=active["taskId"], role=active["role"], authorization=active.get("authorization"), bound_run=active["runId"], evidence_run=evidence["runId"])
        record = {"taskId": active["taskId"], "runId": active["runId"], "role": active["role"], "status": evidence["status"], "at": self.now(), "operation": operation, "authorization": active.get("authorization"), "evidence_shape": evidence["shape"]}
        state.task_history.append(record)
        state.active_task = None
        return record

    def _require_no_active_task(self, state: StoryState, operation: str) -> None:
        if state.active_task is not None:
            raise Refused(f"{operation}: {state.active_task['role']} task {state.active_task['taskId']} of {state.story} is still active; present its terminal evidence (record-task-terminal) first",
                          code="worker-not-terminal", task_id=state.active_task["taskId"], role=state.active_task["role"], authorization=state.active_task.get("authorization"))

    def _require_no_obligation(self, state: StoryState, operation: str) -> None:
        """No active task and no unresolved authorization: nothing may run for the story."""
        self._require_no_active_task(state, operation)
        unresolved = state.unresolved_authorization()
        if unresolved is not None:
            raise self._unresolved_refusal(state, operation, unresolved)

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
        approval cleared, pending proposal intents abandoned and a pending review
        authorization revoked (it stays an unresolved obligation: its reviewer may have been
        launched for the old commit). The active task is untouched (ownership is not evidence)."""
        abandoned = state.abandon_advancing_intents(reason)
        self._revoke_authorization(state, reason)
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

    def bind_receipt(self, story: str, receipt: dict, worktree_path: str | None = None, branch: str | None = None, worktree_check: WorktreeCheck = git_worktree_check, authorization: str | None = None) -> StoryState:
        """Bind the delegated task's receipt to the story's unresolved authorization, consuming
        it: implementation (needs the worktree identity), review or repair (re-check the
        bound worktree). The receipt binds to the exact authorization its task was launched
        for: ``authorization`` names its id and must match; without it the single unresolved
        authorization is the only candidate (none is ever issued while one is unresolved, so a
        late receipt can never land on a successor). A reviewer receipt carries the exact SHA
        of its authorization, never the current head. Exactly one bind per authorization; no
        unresolved authorization ⇒ refused. The task id must be fresh run-wide.

        If the authorization was revoked (story cancel/block requested, evidence invalidated)
        or the run stopped (cancelled or past its wall clock) after it was issued, the task may
        already have been launched: the receipt still binds, but for cleanup only. The slot
        stays spent, the task id stays bound, the task becomes the story's active task
        (released only by its terminal evidence) and the phase does not advance; the call then
        refuses with ``bound_for_cleanup`` so the coordinator cancels the task instead of
        working it. Nothing is refunded."""
        with self.store.locked(self):
            self.require_not_live("bind-receipt")
            self._reload_run()
            state = self._story(story)
            stop = self._run_stop()
            auth = state.unresolved_authorization()
            if auth is None:
                if stop:
                    raise BudgetExhausted(f"bind-receipt: {self._stop_message(stop)}; nothing is authorized for {story}", code=stop, stop_reason=self.run.stop_reason)
                raise Refused(f"{story} has no unresolved task authorization; reserve / authorize-review / authorize-repair must precede every launch, and each authorization binds once", code="no-authorization")
            if authorization is not None and str(authorization) != auth["id"]:
                raise Refused(f"bind-receipt: authorization {authorization} is not the unresolved authorization of {story} ({auth['id']}: {auth['purpose']}, sha {auth['sha']}, {auth['status']}); a receipt binds only to the exact authorization its task was launched for",
                              code="authorization-mismatch", expected=auth["id"], given=str(authorization))
            issued_phase, next_phase, role = AUTHORIZATION_FLOW[auth["purpose"]]
            revoked = auth["status"] == "revoked"
            if revoked:
                self._require_phase(state, *ACTIVE_PHASES)  # the phase may have moved on (evidence invalidated); the story is still owned
            else:
                self._require_phase(state, issued_phase)
            self._require_no_active_task(state, "bind-receipt")
            target: Target = self.policy.implementer if role == "implementer" else self.policy.reviewer
            retained = state.owner_task() if auth["purpose"] == "repair" else None  # only the story's own implementer may be re-run, only for a repair
            if retained and str(receipt.get("taskId", "")) == retained and not state.predecessor_terminal(retained):
                raise Refused(f"bind-receipt: retained task {retained} has no terminal predecessor execution recorded for {story}; a new run of it cannot be bound", code="predecessor-not-terminal", task_id=retained)
            receipt = validate_receipt(receipt, target, role, self.store.bound_task_ids(), self.store.bound_executions(), retained)  # run-wide freshness of task ids (reviewers always fresh) and of (task, run) pairs
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
            auth["status"], auth["task_id"], auth["run_id"], auth["bound_at"] = "consumed", receipt["taskId"], receipt["runId"], self.now()
            record = {**receipt, "authorization": auth["id"]}
            if role == "implementer":
                state.implementer_receipts.append(record)
            else:
                state.reviewer_receipts.append({**record, "sha": auth["sha"]})  # the exact commit this reviewer was authorized for
            state.active_task = {"taskId": receipt["taskId"], "runId": receipt["runId"], "role": role, "authorization": auth["id"], "bound_at": self.now(), "retained": receipt["retained"]}
            cleanup = stop or ("authorization-revoked" if revoked else None)
            if cleanup:
                # Authorized before the stop or the revocation, possibly launched: keep the slot spent, the id bound
                # and the task owned; authorize no work and leave the phase where it is.
                auth["cleanup_only"] = cleanup
                state.active_task["cleanup_only"] = cleanup
                self.store.save_story(state)
                self._counts()
                self.store.save_run(self.run)
                self.store.journal(story, "receipt-bound-cleanup-only", {"task": receipt["taskId"], "role": role, "purpose": auth["purpose"], "authorization": auth["id"], "sha": auth["sha"], "cleanup": cleanup, "revoked_reason": auth.get("reason") if revoked else None, "phase": state.phase})
                why = self._stop_message(stop) if stop else f"authorization {auth['id']} was revoked ({auth.get('reason')})"
                message = f"bind-receipt: {why}; {role} task {receipt['taskId']} is bound to {story} for cleanup only (slot spent, ownership kept, phase {state.phase} unchanged, no work authorized): cancel it and present its terminal evidence"
                detail = {"task_id": receipt["taskId"], "role": role, "bound_for_cleanup": True, "authorization": auth["id"], "sha": auth["sha"]}
                if stop:
                    raise BudgetExhausted(message, code=stop, stop_reason=self.run.stop_reason, **detail)
                raise Refused(message, code="authorization-revoked", reason=auth.get("reason"), **detail)
            state.phase = next_phase
            self.store.save_story(state)
            self._counts()
            self.store.save_run(self.run)
            self.store.journal(story, "receipt-bound", {"task": receipt["taskId"], "role": role, "purpose": auth["purpose"], "authorization": auth["id"], "sha": auth["sha"], "branch": branch, "worktree": worktree_path})
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

    def record_no_launch(self, story: str, no_launch: dict) -> StoryState:
        """Positive no-launch reconciliation: the coordinator attests that no task was ever
        launched for exactly the named unresolved authorization (``delegate_task`` was never
        called, or returned no task). Resolves the obligation (status ``not-launched``), keeps
        the slot counted and changes nothing else. Allowed on a stopped run (it is cleanup).
        Like receipts and terminal evidence it is the coordinator's report; a false
        attestation is not detectable."""
        with self.store.locked(self):
            self.require_not_live("record-no-launch")
            state = self._story(story)
            auth = self._apply_no_launch(state, no_launch, "record-no-launch")
            self.store.save_story(state)
            self.store.journal(story, "authorization-not-launched", {"authorization": auth["id"], "role": auth["role"], "purpose": auth["purpose"], "sha": auth["sha"], "reason": auth["reason"], "resolution": auth["resolution"]})
            return state

    def reconcile_retained_execution(self, story: str, authorization: str, receipt: dict, task_evidence: dict, reason: str, provenance: str) -> StoryState:
        """Audited cleanup of a historical obligation: a revoked (or pending) repair
        authorization whose task WAS launched as a new run of the story's retained owner task
        but was never bound, because the resumption returned no fresh task id. Resolves only
        that obligation, for cleanup: the authorization becomes ``consumed`` with the exact
        execution pair, the receipt and the terminal record are appended, nothing is
        re-authorized, approved or admitted, the run stays cancelled, budgets are unchanged
        and no no-launch attestation is created. Identical evidence is idempotent;
        conflicting evidence refuses. A backup of the story file is written first."""
        with self.store.locked(self):
            self.require_not_live("reconcile-retained-execution")
            state = self._story(story)
            if not reason or not provenance:
                raise Refused("reconcile-retained-execution needs --reason and --provenance (who observed the terminal evidence, and how)", code="provenance-missing")
            auth = state.authorization(str(authorization))
            if auth is None:
                raise Refused(f"{story} has no authorization {authorization}", code="authorization-mismatch", given=str(authorization))
            owner = state.owner_task()
            if auth["purpose"] != "repair" or auth["role"] != "implementer":
                raise Refused(f"authorization {auth['id']} is a {auth['purpose']} authorization; only an implementer repair of the retained owner can be reconciled this way", code="authorization-mismatch", authorization=auth["id"])
            if owner is None:
                raise Refused(f"{story} has no retained owner task (no bound implementation authorization); nothing can be reconciled", code="run-identity-missing")
            evidence = normalize_task_evidence(task_evidence)
            if not isinstance(receipt, dict) or str(receipt.get("taskId", "")) != owner:
                raise Refused(f"the receipt names task {receipt.get('taskId') if isinstance(receipt, dict) else receipt!r}; the retained owner of {story} is {owner}", code="owner-mismatch", owner=owner)
            run_id = execution_run_id(receipt, retained=True)
            if evidence["taskId"] != owner or evidence["runId"] != run_id:
                raise Refused(f"terminal evidence is for ({evidence['taskId']}, {evidence['runId']}); the receipt is for ({owner}, {run_id})", code="run-mismatch", evidence_run=evidence["runId"], receipt_run=run_id)
            # Explicit correlation of THIS run with THIS authorization: the dispatch record of the resumed
            # run must name the same run, and the run must have started at or after the authorization was
            # issued. Legacy task-only history carries no run ids, so an older completed run of the same task
            # (started before the authorization) can never settle a later authorization by task match alone.
            dispatch = receipt.get("dispatch")
            if not isinstance(dispatch, dict) or not dispatch.get("runId"):
                raise Refused("the receipt needs the dispatch record of the resumed run ({\"dispatch\": {\"runId\": …, \"messageId\": …}}) to correlate it with the authorization", code="correlation-missing")
            if str(dispatch["runId"]) != run_id:
                raise Refused(f"dispatch record names run {dispatch['runId']}; the receipt names run {run_id}", code="run-mismatch", dispatch_run=str(dispatch["runId"]), receipt_run=run_id)
            started = receipt.get("startedAt") or task_evidence.get("startedAt") if isinstance(task_evidence, dict) else None
            completed = receipt.get("completedAt") or task_evidence.get("completedAt") if isinstance(task_evidence, dict) else None
            if not started:
                raise Refused("the receipt needs startedAt of the resumed run to correlate it with the authorization's issued_at", code="correlation-missing")
            try:
                started_dt = datetime.fromisoformat(str(started).replace("Z", "+00:00"))
                issued_dt = datetime.fromisoformat(str(auth["issued_at"]).replace("Z", "+00:00"))
                completed_dt = datetime.fromisoformat(str(completed).replace("Z", "+00:00")) if completed else None
            except ValueError as exc:
                raise Refused(f"unparseable timestamps for correlation: {exc}", code="correlation-missing") from exc
            if started_dt < issued_dt:
                raise Refused(f"run {run_id} started at {started}, before authorization {auth['id']} was issued at {auth['issued_at']}; an earlier run of the retained task cannot settle a later authorization", code="run-precedes-authorization", started_at=str(started), issued_at=auth["issued_at"])
            if completed_dt is not None and completed_dt < started_dt:
                raise Refused(f"run {run_id} completedAt {completed} precedes startedAt {started}", code="correlation-missing")
            if auth["status"] == "consumed":
                if auth.get("task_id") == owner and auth.get("run_id") == run_id:
                    self.store.journal(story, "retained-execution-already-reconciled", {"authorization": auth["id"], "task": owner, "run": run_id})
                    return state
                raise Refused(f"authorization {auth['id']} is already consumed by ({auth.get('task_id')}, {auth.get('run_id')}); conflicting evidence refused", code="conflicting-evidence", authorization=auth["id"], bound_task=auth.get("task_id"), bound_run=auth.get("run_id"))
            if auth["status"] not in UNRESOLVED_AUTHORIZATION_STATUSES:
                raise Refused(f"authorization {auth['id']} is {auth['status']}; only an unresolved (pending or revoked) authorization can be reconciled", code="authorization-mismatch", status=auth["status"])
            if (owner, run_id) in self.store.bound_executions():
                raise Refused(f"execution ({owner}, {run_id}) is already bound; a replayed pair cannot resolve {auth['id']}", code="execution-replayed", run_id=run_id)
            if not state.predecessor_terminal(owner):
                raise Refused(f"retained task {owner} has no terminal predecessor execution recorded; its new run cannot be reconciled", code="predecessor-not-terminal")
            if state.active_task is not None:
                raise Refused(f"{story} has an active task {state.active_task['taskId']}; reconcile after it is terminal", code="worker-not-terminal", task_id=state.active_task["taskId"])
            target = self.policy.implementer
            probe = {**receipt, "taskId": owner}
            normalized = validate_receipt(probe, target, "implementer", set(), self.store.bound_executions(), owner)  # provider/model/effort/isolation of the retained owner revalidated
            worktree = receipt.get("worktree") or (state.claim or {}).get("worktree_path")
            branch = receipt.get("branch") or (state.claim or {}).get("branch")
            if not state.claim or worktree != state.claim.get("worktree_path") or branch != state.claim.get("branch"):
                raise Refused(f"the receipt's worktree/branch ({worktree}, {branch}) do not match the bound claim ({(state.claim or {}).get('worktree_path')}, {(state.claim or {}).get('branch')})", code="worktree-mismatch")
            backup = self.store.story_path(story).with_name(f"{story}.json.bak-{self.now().replace(':', '')}")
            backup.write_text(self.store.story_path(story).read_text(encoding="utf-8"), encoding="utf-8")
            auth.update({"status": "consumed", "task_id": owner, "run_id": run_id, "bound_at": self.now(), "cleanup_only": "retained-execution-reconciled",
                         "reconciliation": {"reason": reason, "provenance": provenance, "evidence_shape": evidence["shape"], "status": evidence["status"], "at": self.now(), "previous_status": "revoked" if auth.get("revoked_at") else "pending",
                                            "dispatch": {"runId": str(dispatch["runId"]), "messageId": dispatch.get("messageId")}, "startedAt": str(started), "completedAt": str(completed) if completed else None}})
            state.implementer_receipts.append({**normalized, "authorization": auth["id"], "reconciled": True})
            state.task_history.append({"taskId": owner, "runId": run_id, "role": "implementer", "status": evidence["status"], "at": self.now(), "operation": "reconcile-retained-execution", "authorization": auth["id"], "evidence_shape": evidence["shape"], "provenance": provenance})
            self.store.save_story(state)
            self._counts()
            self.store.save_run(self.run)
            self.store.journal(story, "retained-execution-reconciled", {"authorization": auth["id"], "task": owner, "run": run_id, "status": evidence["status"], "reason": reason, "provenance": provenance, "backup": backup.name, "phase": state.phase, "run_cancelled": self.run.cancelled})
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
            self._require_no_obligation(state, "run-checks")  # a reviewer launched for an invalidated commit may still be running
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
            self._require_no_obligation(state, "authorize-repair")  # before the round is counted or the block fallback runs
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
        self._require_no_obligation(state, operation)

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
    def _terminal(self, story: str, phase: str, reason: str, op: str, kind: str, body: str, task_evidence: dict | None, no_launch: dict | None = None) -> StoryState:
        state = self._story(story)
        self._require_phase(state, *ACTIVE_PHASES, "conflict")
        # refuses while an authorization is unresolved (revoking it) or a task is owned without its terminal evidence;
        # evidence for no active task releases nothing
        resolved = self._settle_authorizations(state, phase, reason, no_launch)
        evidence = self._apply_task_evidence(state, task_evidence, phase) if state.active_task is not None else None
        abandoned = state.abandon_advancing_intents(f"story {phase}: {reason}")
        state.blocked = {"reason": reason, "at": self.now(), "from_phase": state.phase, "cancelled": phase == "cancelled", "task_evidence": task_evidence, "no_launch": no_launch, "abandoned_intents": abandoned, "authorizations_resolved": resolved}
        state.phase = phase
        intent = self._new_intent(state, op, kind, body)
        self.store.save_story(state)  # terminal phase, cleanup intent, abandonments and authorization resolutions persist together
        self.store.journal(story, phase, {"reason": reason, "abandoned_intents": abandoned, "task_evidence": evidence, "authorizations_resolved": resolved})
        try:
            self._post_intent(state, intent)
        except UnattendedError as exc:
            state.blocked["github_error"] = exc.as_dict()
            self.store.save_story(state)
            self.store.journal(story, f"{phase}-github-write-failed", exc.as_dict())
        return state

    def block(self, story: str, reason: str, task_evidence: dict | None = None, no_launch: dict | None = None) -> StoryState:
        with self.store.locked(self):
            self.require_not_live("block")
            return self._terminal(story, "blocked", reason, "block", "block", f"Blocked by run `{self.store.run_id}`: {reason}. Owner decision or new evidence required; nothing advanced. Project Status is owner-maintained.", task_evidence, no_launch)

    def cancel(self, story: str, reason: str, task_evidence: dict | None = None, no_launch: dict | None = None) -> StoryState:
        with self.store.locked(self):
            self.require_not_live("cancel")
            return self._terminal(story, "cancelled", reason, "release", "release", f"Claim released by run `{self.store.run_id}`: {reason}. No completion is implied. Project Status is owner-maintained.", task_evidence, no_launch)

    def cancel_run(self, reason: str, task_evidence: dict[str, dict] | None = None, no_launch: dict[str, dict] | None = None) -> dict:
        """Stop admissions and release every story that owes nothing. Stories with an active
        task and no terminal evidence, or with an unresolved authorization and no no-launch
        attestation, stay owned (their pending authorization is revoked) and are reported; a
        cancelled run never advances or replays an advancing intent for them."""
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
                    released.append(self.cancel(s.story, reason, (task_evidence or {}).get(s.story), (no_launch or {}).get(s.story)).to_dict())
                except Refused as exc:
                    if exc.code not in ("worker-not-terminal", "authorization-unresolved"):
                        raise
                    awaiting.append({"story": s.story, "task_id": exc.detail.get("task_id"), "role": exc.detail.get("role"), "authorization": exc.detail.get("authorization"), "code": exc.code})
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
        resolved = self._settle_authorizations(state, "cancelled", reason, None)  # the reservation never returned: structurally no launch
        abandoned = state.abandon_advancing_intents(reason)
        state.phase = "cancelled"
        state.blocked = {"reason": reason, "at": self.now(), "from_phase": "claim-incomplete", "cancelled": True, "changed": sorted(changed),
                         "claim_comment_ids": [c.comment_id for c in found], "release_owed": bool(found), "abandoned_intents": abandoned, "authorizations_resolved": resolved}
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
        behind the gates of a fresh attempt (run neither cancelled nor past its wall clock; for
        a claim: unchanged revisions, otherwise cancelled with its release; for a proposal:
        phase ``review-approved``, exact-SHA approval and head, no active task or unresolved
        authorization, then fresh revisions with unique identities, the re-read worktree and the
        PR — a failing gate withholds the transition, keeps the posted effect as history and
        has the same consequence as on a fresh attempt), then pending advancing replays only for
        an active story in a run that is neither cancelled nor past its wall clock and only
        after their preconditions (local phase and exact-SHA approval, revisions, worktree, PR)
        re-verify; otherwise they are abandoned. Finally the revision verification."""
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
            # attempt would be allowed. A stopped run (cancelled or past its wall clock) advances
            # nothing (cancel-run finishes the story).
            claim = state.intent("claim")
            if claim is not None and claim.status == "done" and state.phase == "claim-incomplete":
                if stop:
                    self._withhold_reconciliation(state, claim, STOP_REASONS[stop])
                else:
                    fresh, current = self._current_revisions(story)
                    changed = revision_diff(claim.preconditions.get("revisions", state.revisions), current)
                    if changed:
                        return self._cancel_stale_claim(state, claim, changed)
                    self._post_intent(state, claim, phase_after="reserved")
            for intent in state.intents:
                if intent.kind != "proposal" or intent.status != "done" or state.phase == "proposed":
                    continue
                sha, pr = intent.preconditions.get("sha"), intent.preconditions.get("pr")
                unresolved = state.unresolved_authorization()
                if stop:
                    self._withhold_reconciliation(state, intent, STOP_REASONS[stop])
                    continue
                if state.phase != "review-approved" or state.approved_sha != sha or state.head_sha != sha or state.active_task is not None or unresolved is not None or pr is None:
                    self._withhold_reconciliation(state, intent, f"no current approval for {sha}: phase {state.phase}, approved {state.approved_sha}, head {state.head_sha}, active task {state.active_task}, unresolved authorization {unresolved and unresolved['id']}, pr {pr}")
                    continue
                try:  # the same current-evidence gates as a fresh proposal, with the same consequences (stale ⇒ refused, dirty ⇒ invalidated, objection ⇒ regression)
                    self._check_revisions(state)  # fresh read, unique identities, revisions of the closure
                    self._verify_worktree(state, sha, "resume-reconcile-proposal")
                    self._validate_pr(state, sha, int(pr))
                except UnattendedError as exc:
                    self._withhold_reconciliation(state, intent, f"current evidence refused the transition: {exc.code}: {exc}")
                    raise
                self._post_intent(state, intent, phase_after="proposed")
            pending_advancing = state.pending_advancing_intents()
            if pending_advancing and (not state.active or stop):
                why = STOP_REASONS[stop] if stop else f"story is {state.phase}"
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
                    unresolved = state.unresolved_authorization()
                    if state.phase != "review-approved" or state.approved_sha != sha or state.head_sha != sha or state.active_task is not None or unresolved is not None:
                        intent.status, intent.reason = "abandoned", f"no current approval for {sha}: phase {state.phase}, approved {state.approved_sha}, head {state.head_sha}, active task {state.active_task}, unresolved authorization {unresolved and unresolved['id']}"
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
        return {"run": self.run.__dict__, "budgets": counts, "environment": self.environment, "stories": [s.to_dict() for s in self.store.list_stories()], "journal_events": self.store.journal_count(), "live": self.live, "agreement": OPERATING_AGREEMENT, "gaps": list(LIVE_EXECUTION_GAPS)}
