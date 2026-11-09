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
    every advancing consumer of recorded evidence (record-head, run-checks, authorize-review, authorize-repair, record-review, propose-evidence, resume proposal replay/reconciliation) ──_require_advancing_evidence: identified, linked, successful implementer (and reviewer-for-SHA) execution──> else REFUSED, phase unchanged
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

A run's state is bound to the environment (fixture or live) it was created in. On a live
transport nothing runs by default: a live run can only be created with, and admission and
every advancing operation require, a current run-bound activation authorization
(``automation/unattended/activation.py``, ``--activation``); without one no live run is created
and every admitting or advancing command refuses ``activation-required``. Cleanup of a run that was activated earlier (cancel, block,
terminal records, cancel-run, the cleanup part of resume) needs only the run's recorded
binding; an expired activation stops advancement like a wall-clock expiry and a different
activation is refused everywhere. The activation is a trusted-coordinator engineering
approval, not authentication.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from .activation import Activation, _parse_time, _utc_text, refresh_activation
from .backlog import Entry, Snapshot, take_snapshot
from .eligibility import Decision, decide
from .errors import BudgetExhausted, Conflict, ReceiptInvalid, Refused, StaleRevision, UnattendedError
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
    "live execution is opt-in only: the shipped policy (empty allowlist) and the committed activation candidate (approved = false) dispatch nothing; a real-transport state command advances only under a current activation authorization (--activation) that the owner approved for exactly this repository, policy digest, run id, story scope, targets, budgets and time window, citing the published engineering-only lifecycle smoke and fresh independent review; missing, malformed, unapproved, expired or changed activation refuses admission and advancement (cleanup of an activated run stays allowed)",
    "trust, not authentication: an activation is an engineering approval written by the trusted coordinator/owner on the trusted machine; it is not a credential, not signed and not cryptographically verified",
    "accepted residual risk, not a control: budgets are coordinator-enforced best effort (stop dispatch and request cancellation on expiry); a coordinator failure can leave a worker running; T3 timeoutMs bounds only the wait",
    "accepted residual risk, not a control: the operator's development machine is trusted; worktrees isolate files, not host credentials; the child runs with the machine's credentials and no credential confinement is claimed",
    "disclosed, not certified: the operator credential is broad (repository admin, excess scopes); check-permissions reports facts only and never certifies a bounded credential; restricted credentials are used where practical",
    "manual by agreement: Project Status and acceptance are owner actions; machine comments are evidence proposals, not synchronization",
)
# Terminal statuses the real T3 transport reports. A deliberately cancelled (task_cancel) run
# terminates as ``interrupted`` (task_status: status/latestTerminalStatus "interrupted", workState
# "result_available", hasPendingChildRuns false); it is an acknowledged termination, never a success.
TERMINAL_TASK_STATES = ("result_available", "completed", "failed", "cancelled", "terminal", "interrupted")
# Terminal statuses that acknowledge termination without any completed work. They release
# ownership (record-task-terminal, cancel, block, cancel-run) but can never stand in for the
# successful completion that an advancing operation records. Success is only a status in
# StoryState.SUCCESSFUL_STATUSES; everything else terminal (including the bare "terminal"
# marker) is unsuccessful for advancement.
SUCCESSFUL_TERMINAL_TASK_STATES = StoryState.SUCCESSFUL_STATUSES
NON_SUCCESS_TERMINAL_TASK_STATES = tuple(s for s in TERMINAL_TASK_STATES if s not in SUCCESSFUL_TERMINAL_TASK_STATES)
ADVANCING_EVIDENCE_OPERATIONS = ("record-head", "record-review")
CLEANUP_KINDS = ("release", "block")
# purpose -> (phase in which the authorization is issued, phase after the receipt is bound, role)
AUTHORIZATION_FLOW = {
    "implementation": ("reserved", "claimed", "implementer"),
    "review": ("review-authorized", "review-requested", "reviewer"),
    "repair": ("repair-authorized", "claimed", "implementer"),
}
STOP_REASONS = {"run-cancelled": "run is cancelled", "wall-clock-exceeded": "run wall clock budget exceeded",
                "policy-drift": "the policy file changed since this run was created (digest drift); nothing is admitted or advanced under a policy the run was not bound to, cleanup proceeds",
                "activation-required": "no activation authorization presented for this live run", "activation-expired": "activation authorization expired",
                "activation-not-yet-valid": "activation authorization not yet valid", "activation-unapproved": "activation authorization is not approved",
                "activation-mismatch": "activation authorization no longer matches the policy or run", "activation-invalid": "activation authorization is invalid",
                "clock-regression": "the clock moved backwards past an earlier observation; the activation window cannot be trusted"}
ACTIVATION_STOPS = tuple(code for code in STOP_REASONS if code.startswith("activation-") or code == "clock-regression")
CLOCK_REGRESSION_TOLERANCE_MINUTES = 5  # ordinary NTP slew; a larger backward step is a durable stop


def unsuccessful_code(status: str | None) -> str:
    """Refusal code for an execution whose outcome is not a success: the established
    ``worker-interrupted`` for the transport's interrupted status, ``worker-unsuccessful``
    for failed/cancelled/other."""
    return "worker-interrupted" if status == "interrupted" else "worker-unsuccessful"


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


def git_clean(path: str) -> tuple[bool | None, str]:
    """``(True, "")`` for a clean tree, ``(False, dirt)`` for a dirty one and ``(None, why)``
    when git could not answer: an unreadable status is not an observed change."""
    try:
        out = subprocess.run(["git", "-C", path, "status", "--porcelain", "--untracked-files=normal"], capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"git status failed: {exc}"
    if out.returncode != 0:
        return None, f"git status failed: {out.stderr.strip()[:200]}"
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
      refuses; nothing is inferred. ``interrupted`` (the real transport's terminal status of a
      cancelled run) is terminal for release and cleanup but never a success."""
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
    def __init__(self, transport: Transport, policy: Policy, store: Store, now: Callable[[], str] = utcnow, live: bool = False, activation: Activation | None = None):
        self.transport, self.policy, self.store, self.now, self.live, self.activation = transport, policy, store, now, live, activation
        self.environment = "live" if getattr(transport, "live", False) else "fixture"
        self._moment: str | None = None  # the one clock observation of the locked operation in progress (see ``operation``)
        self._author: str | None = None  # the transport's own login, read once per coordinator (``_trusted_author``)
        self._foreign_reported: set[int] | None = None  # comment ids already journaled as foreign markers (loaded from the journal on first use)
        with self.operation(lock=False):
            if self.environment == "live" and store.load_run() is None:
                self._refresh_activation("run-start")  # the loaded object is a cache: creation is decided on the source as it is now
                self._refuse_unless_current("run-start", creating=True)  # a live run is created only under a current activation
            # the only creation path: Store.ensure_run re-reads the source under its lock and validates the document for this run, policy and moment before persisting its binding
            self.run = store.ensure_run(policy.repo_slug, policy.digest, self.environment, activation=self.activation, policy=policy, now=self._at())

    # -- one observation per operation ---------------------------------------------------------
    @contextmanager
    def operation(self, lock: bool = True):
        """The boundary of one coordinator operation: the store lock (re-entrant for this
        instance) and **one** clock observation shared by every authorization decision inside it
        (activation window, durable stop, wall clock, status report). A moving clock cannot
        report an expiry that a decision a moment earlier did not persist: the decision and the
        durable record are made from the same instant, under the same lock. Nested operations
        share the outer observation; independent operations each take a fresh one, so elapsed
        budgets and later expiries are observed, and persisted, by the next operation."""
        outer = self._moment is None
        try:
            if lock:
                with self.store.locked(self):
                    if outer:
                        self._moment = self.now()  # sampled after the lock is held, with the state it governs
                    yield
            else:
                if outer:
                    self._moment = self.now()
                yield
        finally:
            if outer:
                self._moment = None

    def _at(self) -> str:
        """The operation's clock observation; outside an operation, the clock itself."""
        return self._moment if self._moment is not None else self.now()

    # -- guards --------------------------------------------------------------------------
    def _activation_problems(self) -> list[tuple[str, str]]:
        if self.activation is None:
            return [("activation-required", "no activation authorization presented (--activation); accepting residual risk is not activation")]
        return self.activation.problems(self.policy, self.store.run_id, self._at())

    def _activation_stop(self) -> str | None:
        """Why a live run advances nothing: a durable observed stop, else no, expired or non-matching activation. ``None`` on fixtures."""
        if self.environment != "live":
            return None
        if self.run.activation_stop is not None:
            return self.run.activation_stop["code"]
        return Activation.stop_code(self._activation_problems())

    def _refuse_unless_current(self, operation: str, creating: bool = False) -> None:
        problems = self._activation_problems()
        code = Activation.stop_code(problems)
        if code:
            what = "creating a live run" if creating else "advancing"
            raise Refused(f"{operation}: {what} on the live transport needs a current activation authorization: " + "; ".join(m for _, m in problems) + f" ({OPERATING_AGREEMENT}; accepting residual risk is not activation)",
                          code=code, problems=[m for _, m in problems], agreement=OPERATING_AGREEMENT, gaps=list(LIVE_EXECUTION_GAPS))

    def _refresh_activation(self, operation: str) -> None:
        """Re-read the activation source the presented document came from. The file is the
        approval; the loaded object is a cache. A changed file (another digest) or a malformed
        one is a different document and refuses every operation, cleanup included
        (``activation-mismatch`` / ``activation-invalid``: omit --activation to clean up on the
        recorded binding). A missing file leaves nothing presented: advancement stops
        (``activation-required``) while cleanup proceeds on the validated recorded binding."""
        self.activation = refresh_activation(self.activation, operation)  # the same re-read Store.ensure_run performs at creation

    def _observe_stop(self, operation: str) -> None:
        """Record, durably and under the lock, the first observation that the recorded approval
        window is over (``activation-expired``) or that the clock moved backwards past an earlier
        observation (``clock-regression``). Once recorded the run never advances again, after a
        clock correction, a rollback or a restart; cleanup, late receipts (cleanup only) and
        terminal evidence stay allowed; approvals, obligations and budgets are untouched."""
        if self.run.activation_stop is not None or self.run.activation is None:
            return
        problems: list[str] = []
        at = self._at()
        now, expires = _parse_time(at, "now", problems), _parse_time(self.run.activation["expires_at"], "expires_at", problems)
        # the high-water mark is the latest observation, else the validated creation moment (both strict at load); a parse problem refuses, it is never replaced by now
        source = ("last_observed_at", self.run.last_observed_at) if self.run.last_observed_at is not None else ("activation.validated_at", self.run.activation["validated_at"])
        high_water = _parse_time(source[1], source[0], problems)
        if problems or high_water is None:
            raise Refused(f"{operation}: cannot evaluate the activation window: " + "; ".join(problems), code="activation-invalid", problems=problems)
        stop = None
        if now > expires:
            stop = {"code": "activation-expired", "observed_at": at, "message": f"now {at} is after the recorded expires_at {self.run.activation['expires_at']}"}
        elif now < high_water - timedelta(minutes=CLOCK_REGRESSION_TOLERANCE_MINUTES):
            stop = {"code": "clock-regression", "observed_at": at, "message": f"now {at} is before the latest recorded observation {_utc_text(high_water)}; the approval window cannot be trusted"}
        if stop:
            self.run.activation_stop = {**stop, "operation": operation}
            self.store.save_run(self.run)
            self.store.journal(None, "activation-stopped", self.run.activation_stop)
        elif now > high_water:
            self.run.last_observed_at = _utc_text(now)
            self.store.save_run(self.run)

    def require_activation(self, operation: str, advancing: bool = True) -> None:
        """The live gate, one validation for every consumer, run under the operation lock. It
        reloads the run from disk (binding to repository, policy digest and environment, then the
        persisted activation record validated strictly against this run), re-reads the activation
        source, records an observed expiry or clock regression durably, and compares the presented
        document to the recorded binding. Fixture transports only reload. On the live transport the
        run must carry a valid recorded binding and any activation presented now must be that same
        document; an advancing operation additionally needs it present and current (approved,
        bound to this policy digest, run, scope, targets and budgets, inside its window) and no
        durable stop. Cleanup (``advancing=False``) is allowed after expiry, after a recorded stop
        or without the file, never with a different, changed or malformed one."""
        if self.environment != "live":
            self._reload_run()
            return
        persisted = self.store.bound_run()  # fresh locked state; a partial or foreign record refuses here (activation-binding-invalid)
        if persisted is None or not persisted.activation:
            raise Refused(f"{operation}: live run {self.store.run_id} was never activated; nothing can be admitted, advanced or released here ({OPERATING_AGREEMENT}; accepting residual risk is not activation)", code="activation-required", agreement=OPERATING_AGREEMENT, gaps=list(LIVE_EXECUTION_GAPS))
        self._reload_run()
        if self.activation is not None and not self.activation.matches(self.run.activation):
            raise Refused(f"{operation}: activation {self.activation.id} (digest {self.activation.digest[:12]}) is not the activation this run was created under ({self.run.activation['id']}, digest {self.run.activation['digest'][:12]}); a changed or different authorization is refused for every operation", code="activation-mismatch")
        self._refresh_activation(operation)
        if self.activation is not None and not self.activation.matches(self.run.activation):  # a re-read that no longer matches is a different document
            raise Refused(f"{operation}: the re-read activation {self.activation.id} is not the one this run was created under", code="activation-mismatch")
        if self.store._lock_depth:
            self._observe_stop(operation)
        if advancing:
            if self.run.activation_stop is not None:
                stop = self.run.activation_stop
                raise BudgetExhausted(f"{operation}: {STOP_REASONS[stop['code']]} (observed {stop['observed_at']} during {stop.get('operation')}: {stop['message']}); the run never advances again; only cancel, block, record-task-terminal, record-no-launch, cancel-run, resume (cleanup) and status are allowed", code=stop["code"], stop=stop)
            self._refuse_unless_current(operation)

    def _reload_run(self) -> None:
        """Fresh locked state: the run as persisted now, never a cached object. The repository,
        policy digest and environment binding and (live) the strict activation record are
        validated on every reload."""
        run = self.store.bound_run()
        if run is None or (run.repo, run.environment) != (self.policy.repo_slug, self.environment):
            raise Refused("run binding changed on disk", code="run-binding-mismatch")
        self.run = run  # a policy digest that differs from the run's binding is policy drift: a run stop (``_run_stop``), not a rebind

    def _policy_drift(self) -> bool:
        return not self.store.digest_bound(self.run.policy_digest, self.policy)

    def _bound_target(self, role: str) -> Target:
        """The target a receipt is validated against: under policy drift the targets recorded
        when the run was created (a late receipt for a task launched under the bound policy must
        still bind, for cleanup), otherwise the policy's."""
        recorded = self.run.targets.get(role) if self._policy_drift() and isinstance(self.run.targets, dict) and isinstance(self.run.targets.get(role), dict) else None
        if recorded is not None:
            return Target(str(recorded.get("provider")), str(recorded.get("model")), {str(k): str(v) for k, v in (recorded.get("options") or {}).items()}, str(recorded.get("isolation") or ""))
        return self.policy.implementer if role == "implementer" else self.policy.reviewer

    def _elapsed(self) -> timedelta:
        return datetime.fromisoformat(self._at().replace("Z", "+00:00")) - datetime.fromisoformat(self.run.started_at.replace("Z", "+00:00"))

    def _run_stop(self) -> str | None:
        """Why the run admits and advances nothing any more: ``run-cancelled`` or
        ``wall-clock-exceeded`` (a local expiry; it does not stop a launched child), a durable
        activation stop, else the activation's current problems, else None."""
        if self.run.cancelled:
            return "run-cancelled"
        if self._policy_drift():
            return "policy-drift"
        if self._elapsed() > timedelta(minutes=self.policy.max_wall_clock_minutes):
            return "wall-clock-exceeded"
        return self._activation_stop()

    def _stop_message(self, code: str) -> str:
        if code == "run-cancelled":
            return f"run is cancelled ({self.run.stop_reason})"
        if code == "policy-drift":
            return STOP_REASONS[code] + f" (run bound to policy digest {self.run.policy_digest[:12]}, policy in use {self.policy.digest[:12]})"
        if code in ACTIVATION_STOPS:
            if self.run.activation_stop is not None and self.run.activation_stop["code"] == code:
                return STOP_REASONS[code] + f" (durable stop observed {self.run.activation_stop['observed_at']}: {self.run.activation_stop['message']})"
            return STOP_REASONS[code] + ": " + "; ".join(m for _, m in self._activation_problems())
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
        code = self._run_stop()
        if code and code != "run-cancelled":
            raise BudgetExhausted(self._stop_message(code), code=code)

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
        # ``reserved`` is reported only once the claim race is settled (``reserve`` and ``resume`` both settle before returning),
        # so a reservation whose race is still unsettled was never reported either: structurally nothing was launched for it
        never_returned = state.phase == "claim-incomplete" or (state.phase == "conflict" and (state.blocked or {}).get("from_phase") == "claim-incomplete") \
            or (state.phase in ("reserved", "conflict") and self._claim_unsettled(state))
        if not never_returned:
            return None
        return self._resolve_not_launched(state, auth, "reservation never returned to the coordinator (claim-incomplete or claim race unsettled); the protocol launches only after reserve reports reserved", "structural")

    @staticmethod
    def _claim_unsettled(state: StoryState) -> bool:
        """True while the post-claim race check has not completed for this reservation (the flag
        is written ``False`` with the claim and ``True`` by ``_settle_claim_race``; states written
        before the flag existed carry no key and are read as settled)."""
        return bool(state.claim) and state.claim.get("race_settled") is False

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
        successful = evidence["status"] in SUCCESSFUL_TERMINAL_TASK_STATES
        if operation in ADVANCING_EVIDENCE_OPERATIONS and not successful:
            raise Refused(f"{operation}: {active['role']} task {active['taskId']} of {state.story} terminated as {evidence['status']!r} (run {active['runId']}); an unsuccessful execution completed nothing and cannot advance the story; it stays owned until released (record-task-terminal, cancel or block)",
                          code=unsuccessful_code(evidence["status"]), task_id=active["taskId"], role=active["role"], authorization=active.get("authorization"), status=evidence["status"], run_id=active["runId"])
        record = {"taskId": active["taskId"], "runId": active["runId"], "role": active["role"], "status": evidence["status"], "successful": successful, "at": self.now(), "operation": operation, "authorization": active.get("authorization"), "evidence_shape": evidence["shape"]}
        state.task_history.append(record)
        state.active_task = None
        return record

    def _require_successful_execution(self, state: StoryState, role: str, operation: str, sha: str | None = None) -> dict:
        """The durable result evidence an advancing operation needs, independent of ownership:
        the latest consumed ``role`` authorization of the story (for a reviewer, the one issued
        for exactly ``sha``) names a bound execution ``(task_id, run_id)`` whose terminal history
        record is a successful completion in that role. Terminal acknowledgement alone (a
        released interrupted/failed/cancelled task, a cleanup-only binding, a legacy record whose
        flag contradicts its status) never authorizes a head, a verdict or a proposal. Returns
        the history record."""
        relevant = [a for a in state.authorizations if a["role"] == role and a.get("task_id") and (sha is None or a.get("sha") == sha)]
        if not relevant:
            raise Refused(f"{operation}: {state.story} has no bound {role} execution" + (f" authorized for {sha}" if sha else "") + "; nothing completed that could advance the story",
                          code="no-successful-execution", role=role, sha=sha)
        auth = relevant[-1]
        if auth.get("status") != "consumed" or auth.get("cleanup_only"):
            raise Refused(f"{operation}: {role} task {auth['task_id']} of {state.story} was bound to authorization {auth['id']} for cleanup only ({auth.get('cleanup_only') or auth.get('status')}); no work was authorized, so its outcome cannot advance the story",
                          code="no-successful-execution", role=role, task_id=auth["task_id"], authorization=auth["id"], sha=sha)
        detail = {"role": role, "task_id": auth["task_id"], "run_id": auth.get("run_id"), "authorization": auth["id"], "sha": sha}
        if not auth.get("run_id"):
            raise Refused(f"{operation}: {role} task {auth['task_id']} of {state.story} was bound to authorization {auth['id']} without a run identity (legacy task-only record); task-only completion is not an identified execution and is not inferred, so the story cannot advance",
                          code="run-identity-missing", **detail)
        latest = state.terminal_record(auth["task_id"], auth["run_id"])
        if latest is None:
            raise Refused(f"{operation}: {role} task {auth['task_id']} (run {auth['run_id']}) of {state.story}, authorization {auth['id']}" + (f" for {sha}" if sha else "") + " has no identified terminal record; nothing completed that could advance the story",
                          code="no-successful-execution", **detail)
        if latest.get("role") != role or not latest.get("authorization") or str(latest.get("authorization")) != str(auth["id"]):
            raise Refused(f"{operation}: the terminal record of {role} task {auth['task_id']} (run {auth['run_id']}) of {state.story} is recorded for role {latest.get('role')!r} and authorization {latest.get('authorization')!r}; the selected authorization is {auth['id']} ({role}); contradictory or unlinked evidence is not successful result evidence",
                          code="conflicting-evidence", recorded_role=latest.get("role"), recorded_authorization=latest.get("authorization"), **detail)
        record = state.successful_execution(auth["task_id"], auth["run_id"], role, auth["id"])
        if record is None:
            status = latest.get("status")
            raise Refused(f"{operation}: {role} task {auth['task_id']} (run {auth['run_id']}) of {state.story}, authorization {auth['id']}" + (f" for {sha}" if sha else "") + f", terminated as {status!r} and completed nothing; terminal acknowledgement is not successful result evidence, so the story cannot advance",
                          code=unsuccessful_code(status), status=status, successful=latest.get("successful"), **detail)
        return record

    def _require_advancing_evidence(self, state: StoryState, operation: str, sha: str | None = None) -> None:
        """The one gate every advancing consumer of recorded evidence passes, whatever path led
        here (direct evidence, release then reload, upgrade from older state, restart replay):
        the latest bound implementer execution completed successfully and, when ``sha`` names
        the reviewed commit, so did the reviewer execution authorized for exactly that SHA.
        A head, a check result, an approval or a posted proposal recorded by an older
        coordinator over an unsuccessful or unidentified execution is history, never evidence."""
        self._require_successful_execution(state, "implementer", operation)
        if sha is not None:
            self._require_successful_execution(state, "reviewer", operation, sha)

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
        if head is None or clean is None:
            # git could not answer: nothing was observed, so nothing is invalidated; refuse and retry later
            raise Refused(f"{gate}: worktree {state.claim['worktree_path']} is unreadable (HEAD {head}, status: {dirt or 'unavailable'}); evidence untouched, retry when git answers", code="worktree-unreadable", head=head, status=dirt)
        if head != sha or not clean:
            abandoned = self._invalidate_evidence(state, head, f"unreported worktree change at {gate}: HEAD {head}, clean={clean}")
            self.store.save_story(state)
            self.store.journal(state.story, "unreported-worktree-change", {"gate": gate, "expected": sha, "head": head, "clean": clean, "dirt": dirt, "abandoned_intents": abandoned})
            raise Refused(f"{gate}: worktree HEAD {head} / clean={clean} differs from the evidence at {sha}; check and review evidence invalidated", code="evidence-invalidated", head=head, clean=clean)

    def _trusted_author(self) -> str:
        """The comment author whose unattended markers are **ours**: the identity the transport
        acts as. Anyone who can comment can copy a marker, so only this author's markers are ever
        adopted as our own effects or counted as duplicates of them."""
        if self._author is None:
            self._author = self.transport.viewer_login()
        return self._author

    def _marked_comments(self, issue: int, story: str | None, context: str, trusted_only: bool = True) -> list:
        """Comments on ``issue`` carrying an unattended marker (for ``story`` when given). Trust is
        asymmetric and fails closed: a ``claim`` from **any** author blocks admission and takes
        part in the claim race (``trusted_only=False`` returns them too), while a release, block,
        proposal or probe marker from another author is ignored (it could only unblock), and no
        other author's marker is ever adopted as ours. Markers from other authors are journaled
        once per comment id (``foreign-claim-counted`` for a claim, ``foreign-marker-ignored`` for
        the ignored kinds) and never re-reported on later reads."""
        author = self._trusted_author()
        trusted, foreign = [], []
        for c in self.transport.list_comments(issue):
            m = c.marker
            if not m or (story is not None and m.get("story") != story):
                continue
            (trusted if c.author == author else foreign).append(c)
        if foreign:
            if self._foreign_reported is None:
                self._foreign_reported = {int(c["id"]) for e in self.store.read_journal() if e.get("event") in ("foreign-marker-ignored", "foreign-claim-counted") for c in (e.get("detail") or {}).get("comments", []) if isinstance(c, dict) and "id" in c}
            for event, is_claim in (("foreign-claim-counted", True), ("foreign-marker-ignored", False)):
                new = [c for c in foreign if c.comment_id not in self._foreign_reported and (c.marker.get("kind") == "claim") is is_claim]
                if new:
                    effect = "counts as a foreign claim (fail closed)" if is_claim else "never adopted as ours; clears only a claim posted by the same author and run"
                    self.store.journal(story, event, {"context": context, "issue": issue, "trusted_author": author, "effect": effect, "comments": [{"id": c.comment_id, "author": c.author, "marker": c.marker} for c in new]})
                    self._foreign_reported.update(c.comment_id for c in new)
        if trusted_only:
            return trusted
        return trusted + foreign  # every author's markers, for the claim pairing in ``_active_foreign_claims``

    def _own_marker(self, m: dict) -> bool:
        """A marker this run directory wrote: same run id and our instance nonce. Only a run that
        itself predates the nonce (``run.json`` without ``instance``) reads a marker without
        ``inst`` as its own; a run with a nonce treats every marker without one, or with another
        one, as another coordinator's, so sharing a run id with a pre-nonce coordinator is not
        a way to adopt its claim."""
        return m.get("run") == self.store.run_id and m.get("inst") == self.run.instance

    def _same_effect(self, comment, intent: Intent) -> bool:
        """The comment carries exactly this intent's marker, nonce included (a legacy run has no
        nonce on either side)."""
        return dict(comment.marker or {}) == dict(intent.marker)

    def _active_foreign_claims(self, issue: int, story: str, context: str = "admission") -> list[dict]:
        """Claims by other coordinators that no later release, block or proposal **by the same
        author, run and instance** cleared. A claim counts whoever posted it (fail closed), and
        another author's release can clear only that author's own claim, never one of ours or of
        a third identity; a run id equal to ours with another instance nonce is another
        coordinator. Each entry carries the marker, the comment id, its author and creation time."""
        claims: dict[tuple, dict] = {}
        released: set[tuple] = set()
        author = self._trusted_author()
        for c in self._marked_comments(issue, story, context, trusted_only=False):
            m = c.marker
            key = (m.get("run", ""), m.get("inst"), c.author)
            if m.get("kind") == "claim":
                claims[key] = {**m, "comment_id": c.comment_id, "created_at": c.created_at, "author": c.author}
            elif m.get("kind") in ("release", "block", "proposal"):
                released.add(key)
        return [m for key, m in claims.items() if not (key[2] == author and self._own_marker(m)) and key not in released]

    def _claims_elsewhere(self, snapshot: Snapshot, story: str) -> dict[str, list[dict]]:
        """Active claims by any other coordinator on any other allowlisted story: the GitHub-side
        single-active-story check across state directories and machines (budgets are local)."""
        found: dict[str, list[dict]] = {}
        by_id = snapshot.by_id()
        for sid in self.policy.allow:
            entry = by_id.get(sid)
            if sid == story or entry is None:
                continue
            claims = self._active_foreign_claims(entry.number, sid, "admission scan")
            if claims:
                found[sid] = claims
        return found

    def _new_intent(self, state: StoryState, op: str, kind: str, body: str, preconditions: dict | None = None, **extra: str) -> Intent:
        """Record the complete effect (identity, marker and exact body) before attempting it."""
        existing = state.intent(op)
        if existing is not None:
            return existing
        marker = {"kind": kind, "run": self.store.run_id, "story": state.story, "op": op, **({"inst": self.run.instance} if self.run.instance else {}), **extra}
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
        found = [c for c in self._marked_comments(state.issue, state.story, f"post {intent.op}") if self._same_effect(c, intent)]
        if not found:
            posted = self.transport.post_comment(state.issue, intent.body)
            found = [c for c in self._marked_comments(state.issue, state.story, f"post {intent.op}") if self._same_effect(c, intent)]
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
        with self.operation():
            self.require_activation("reserve")
            self._reload_run()
            self._require_run_active("reserve")
            if self.store.load_story(story) is not None:
                raise Refused(f"{story} already has state in run {self.store.run_id}; a story is admitted at most once per run (no reclaim)", code="no-reclaim")
            others = self.store.other_runs_with_active_stories()
            if others:
                raise Refused(f"another run under {self.store.state_dir} still owns a story: {others}; budgets and the single-active-story rule are per run id, so this run admits nothing until those stories are terminal: finish them, or cancel/block them in their own run with their tasks' terminal evidence (cancel-run alone leaves owned stories active)", code="run-concurrent", runs=others)
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
            elsewhere = self._claims_elsewhere(fresh, story)
            if elsewhere:
                raise Refused(f"another coordinator still holds an active claim on a story of this policy's allowlist: {elsewhere}; one active story at a time across every state directory and machine, so nothing is admitted until those claims are released, blocked or proposed by their own run", code="claim-active-elsewhere", claims=elsewhere)
            state = StoryState(story=story, issue=entry.number, item_id=entry.item_id, phase="claim-incomplete", run_id=self.store.run_id,
                               claim={"baseline_sha": baseline_sha, "reserved_at": self.now(), "scope": decision.outcome, "worktree_path": None, "branch": None, "race_settled": False},
                               revisions=current)
            auth = self._authorize(state, "implementation")  # refuses before any save or post when the task budget is spent
            intent = self._new_intent(state, "claim", "claim", f"Unattended reservation by run `{self.store.run_id}` from `{baseline_sha}` (scope: {decision.outcome}). An implementer task is delegated only after this reservation; its receipt is bound to the reservation. Project Status is owner-maintained; completion still requires checks, independent review and owner acceptance.", {"revisions": current})
            self.store.save_story(state)
            self.store.journal(story, "reserved", {"issue": entry.number, "baseline": baseline_sha, "scope": decision.outcome, "authorization": auth["id"]})
            self._counts()
            self.store.save_run(self.run)
            self._post_intent(state, intent, phase_after="reserved")
            self._settle_claim_race(state, intent, entry.number)
            return state

    def _settle_claim_race(self, state: StoryState, claim: Intent, issue: int) -> None:
        """Two coordinators can both see no foreign claim and both post. After our claim landed
        the claims are read again and the earliest one wins (creation time, then comment id).
        A later claimant cancels itself in the same operation: its unlaunched authorization is
        resolved structurally (``reserve`` never reported ``reserved``, so no task exists), the
        release it owes is posted and the call refuses ``claim-race-lost``.

        The outcome is durable: ``claim.race_settled`` stays ``False`` until the re-read
        succeeded, so a transport failure or a crash here leaves a reservation that ``resume``
        settles before anything may bind to it (``bind-receipt`` refuses ``claim-race-unsettled``
        until then). A claim comment that cannot be read back is ``conflict``, never ``reserved``."""
        if not self._claim_unsettled(state):
            return  # settled by an earlier operation; states written before the flag are read as settled
        mine = next((c for c in self._marked_comments(issue, state.story, "claim race") if c.comment_id == claim.comment_id), None)
        if mine is None:
            state.blocked = {"reason": f"claim comment {claim.comment_id} is not readable back after posting; the claim race cannot be settled", "at": self.now(), "from_phase": state.phase, "conflict": True, "race_unsettled": True}
            state.phase = "conflict"
            self.store.save_story(state)
            self.store.journal(state.story, "claim-unverifiable", {"comment_id": claim.comment_id})
            raise Conflict(f"claim comment {claim.comment_id} of {state.story} is no longer readable after posting; the story is in conflict, nothing may be launched for it", code="claim-unverifiable", comment_id=claim.comment_id)
        foreign = self._active_foreign_claims(issue, state.story, "claim race")
        earlier = sorted((m for m in foreign if (m["created_at"], m["comment_id"]) < (mine.created_at, mine.comment_id)), key=lambda m: (m["created_at"], m["comment_id"]))
        if not earlier:
            state.claim["race_settled"] = True
            self.store.save_story(state)
            self.store.journal(state.story, "claim-race-settled", {"ours": {"comment_id": mine.comment_id, "created_at": mine.created_at}, "later_claims": len(foreign)})
            return
        winner = earlier[0]
        reason = f"lost the claim race for {state.story} to run {winner.get('run')} (comment {winner['comment_id']} at {winner['created_at']} precedes ours, {mine.comment_id} at {mine.created_at})"
        resolved = []
        auth = state.unresolved_authorization()
        if auth is not None and auth["purpose"] == "implementation":
            resolved.append(self._resolve_not_launched(state, auth, "reservation lost the claim race before reserve returned; the protocol launches only after reserve reports reserved", "structural")["id"])
        abandoned = state.abandon_advancing_intents(reason)
        state.phase = "cancelled"
        state.claim["race_settled"] = True
        state.blocked = {"reason": reason, "at": self.now(), "from_phase": "reserved", "cancelled": True, "conflict": True, "winner": winner, "abandoned_intents": abandoned, "authorizations_resolved": resolved}
        release = self._new_intent(state, "release", "release", f"Claim released by run `{self.store.run_id}`: {reason}. No completion is implied. Project Status is owner-maintained.")
        self.store.save_story(state)  # cancellation, the owed release and the resolution persist together
        self.store.journal(state.story, "claim-race-lost", {"winner": winner, "ours": {"comment_id": mine.comment_id, "created_at": mine.created_at}, "authorizations_resolved": resolved})
        try:
            self._post_intent(state, release)
        except UnattendedError as exc:
            state.blocked["github_error"] = exc.as_dict()
            self.store.save_story(state)
            self.store.journal(state.story, "cancelled-github-write-failed", exc.as_dict())
        raise Conflict(f"{state.story}: {reason}; this reservation is cancelled and released, nothing may be launched for it; its story slot and task authorization stay spent in this run (an issued slot is spent), so with max_stories_per_run = 1 the run admits nothing more and a new run id is needed", code="claim-race-lost", winner=winner)

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
        with self.operation():
            self.require_activation("bind-receipt", advancing=False)
            self._reload_run()
            if not isinstance(receipt, dict):
                raise ReceiptInvalid(f"bind-receipt: the receipt must be a JSON object, not {type(receipt).__name__}")
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
            if auth["purpose"] == "implementation" and self._claim_unsettled(state):
                raise Refused(f"bind-receipt: the claim race of {story} is not settled (the reservation's re-read failed or the process died before it); run resume first, which settles it or cancels the reservation; nothing should have been launched for it", code="claim-race-unsettled")
            target: Target = self._bound_target(role)  # under policy drift: the targets the run was created with, so a late receipt still binds for cleanup
            retained = state.owner_task() if auth["purpose"] == "repair" else None  # only the story's own implementer may be re-run, only for a repair
            if retained and str(receipt.get("taskId", "")) == retained:
                if state.legacy_task_only_history(retained):
                    raise Refused(f"bind-receipt: retained task {retained} of {story} has legacy task-only history (no run identity); its previous execution cannot be told from a new one, so an ordinary rebind is refused; a stopped run may be reconciled with reconcile-retained-execution and exact dispatch/time correlation", code="run-identity-missing", task_id=retained)
                if not state.predecessor_terminal(retained, identified=True):
                    raise Refused(f"bind-receipt: retained task {retained} has no identified terminal predecessor execution recorded for {story}; a new run of it cannot be bound", code="predecessor-not-terminal", task_id=retained)
            receipt = validate_receipt(receipt, target, role, self.store.bound_task_ids(), self.store.bound_executions(), retained)  # run-wide freshness of task ids (reviewers always fresh) and of (task, run) pairs
            if auth["purpose"] == "implementation":
                if not worktree_path or not branch:
                    raise Refused("bind-receipt for the implementation task needs --worktree and --branch")
            elif auth["purpose"] == "review":
                # review evidence must come from a checkout independent of the tree under review: the reviewer's own
                # worktree is named, verified, and refused when it is the implementer's (a self-reported "worktree" proves nothing)
                if not worktree_path or not branch:
                    raise Refused("bind-receipt for the review task needs --worktree and --branch naming the reviewer's own checkout (isolation is verified, not taken from the receipt)", code="reviewer-worktree-required")
                claimed = (state.claim or {}).get("worktree_path")
                if claimed:
                    theirs, ours = Path(worktree_path).resolve(), Path(claimed).resolve()
                    if theirs == ours or theirs.is_relative_to(ours) or ours.is_relative_to(theirs):
                        raise Refused(f"bind-receipt: the reviewer worktree {worktree_path} is, or is nested with, the implementer's claimed worktree {claimed}; a review in the tree under review is not independent", code="reviewer-worktree-shared", worktree=worktree_path, claimed=claimed)
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
                state.reviewer_receipts.append({**record, "sha": auth["sha"], "worktree": worktree_path, "branch": branch, "head_at_bind": git_head(worktree_path)})  # the exact commit this reviewer was authorized for, the independent checkout it reviewed in, and what that checkout read at binding (observed, not asserted: the reviewer checks the SHA out itself)
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
        with self.operation():
            self.require_activation("record-task-terminal", advancing=False)
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
        with self.operation():
            self.require_activation("record-no-launch", advancing=False)
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
        with self.operation():
            self.require_activation("reconcile-retained-execution", advancing=False)
            self._reload_run()  # binding validated and the latest cancellation/budgets read under the lock; never saved from a stale object
            stop = self._run_stop()
            if not stop:
                raise Refused("reconcile-retained-execution is cleanup for a stopped run only (cancelled or past its wall clock); an active run binds a receipt through bind-receipt", code="run-not-stopped")
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
            def parse_timestamp(value, label):
                if not isinstance(value, str) or not value.strip():
                    raise Refused(f"{label} must be a nonempty timestamp string", code="correlation-missing")
                try:
                    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                except ValueError as exc:
                    raise Refused(f"invalid {label}: {exc}", code="correlation-missing") from exc
                if parsed.utcoffset() is None:
                    raise Refused(f"{label} must include a timezone", code="correlation-missing")
                return parsed

            def correlated_timestamp(field):
                # Validate every supplied value before selecting a source. Neither a receipt
                # nor a terminal report may hide contradictory or malformed evidence.
                supplied = [(source, payload[field]) for source, payload in
                            (("receipt", receipt), ("terminal evidence", task_evidence))
                            if payload.get(field) is not None]
                parsed = [(value, parse_timestamp(value, f"{source}.{field}"))
                          for source, value in supplied]
                if len(parsed) == 2 and parsed[0][1] != parsed[1][1]:
                    raise Refused(f"receipt and terminal evidence disagree on {field}",
                                  code="conflicting-evidence", field=field)
                return parsed[0] if parsed else (None, None)

            started, started_dt = correlated_timestamp("startedAt")
            completed, completed_dt = correlated_timestamp("completedAt")
            if started_dt is None:
                raise Refused("startedAt is required to correlate the resumed run with its authorization", code="correlation-missing")
            issued_dt = parse_timestamp(auth["issued_at"], "authorization.issued_at")
            if started_dt < issued_dt:
                raise Refused(f"run {run_id} started at {started}, before authorization {auth['id']} was issued at {auth['issued_at']}; an earlier run of the retained task cannot settle a later authorization", code="run-precedes-authorization", started_at=str(started), issued_at=auth["issued_at"])
            if completed_dt is not None and completed_dt < started_dt:
                raise Refused(f"run {run_id} completedAt {completed} precedes startedAt {started}", code="correlation-missing")
            already = auth["status"] == "consumed" and auth.get("task_id") == owner and auth.get("run_id") == run_id
            if auth["status"] == "consumed" and not already:
                raise Refused(f"authorization {auth['id']} is already consumed by ({auth.get('task_id')}, {auth.get('run_id')}); conflicting evidence refused", code="conflicting-evidence", authorization=auth["id"], bound_task=auth.get("task_id"), bound_run=auth.get("run_id"))
            if auth["status"] not in UNRESOLVED_AUTHORIZATION_STATUSES and not already:
                raise Refused(f"authorization {auth['id']} is {auth['status']}; only an unresolved (pending or revoked) authorization can be reconciled", code="authorization-mismatch", status=auth["status"])
            if not already and (owner, run_id) in self.store.bound_executions():
                raise Refused(f"execution ({owner}, {run_id}) is already bound; a replayed pair cannot resolve {auth['id']}", code="execution-replayed", run_id=run_id)
            if not state.predecessor_terminal(owner, identified=False):
                raise Refused(f"retained task {owner} has no terminal predecessor execution recorded; its new run cannot be reconciled", code="predecessor-not-terminal")
            if state.active_task is not None:
                raise Refused(f"{story} has an active task {state.active_task['taskId']}; reconcile after it is terminal", code="worker-not-terminal", task_id=state.active_task["taskId"])
            target = self.policy.implementer
            probe = {**receipt, "taskId": owner}
            executions = self.store.bound_executions() - ({(owner, run_id)} if already else set())
            normalized = validate_receipt(probe, target, "implementer", set(), executions, owner)  # provider/model/effort/isolation of the retained owner revalidated, also on a repeat
            worktree = receipt.get("worktree") or (state.claim or {}).get("worktree_path")
            branch = receipt.get("branch") or (state.claim or {}).get("branch")
            if not state.claim or worktree != state.claim.get("worktree_path") or branch != state.claim.get("branch"):
                raise Refused(f"the receipt's worktree/branch ({worktree}, {branch}) do not match the bound claim ({(state.claim or {}).get('worktree_path')}, {(state.claim or {}).get('branch')})", code="worktree-mismatch")
            if already:
                # Idempotent only for IDENTICAL evidence: the same terminal status, dispatch record, timestamps,
                # target and worktree as recorded. Anything else is conflicting evidence, not a repeat.
                rec = auth.get("reconciliation") or {}
                recorded = {"status": rec.get("status"), "dispatch": rec.get("dispatch"), "startedAt": rec.get("startedAt"), "completedAt": rec.get("completedAt"), "worktree": state.claim.get("worktree_path"), "branch": state.claim.get("branch")}
                presented = {"status": evidence["status"], "dispatch": {"runId": str(dispatch["runId"]), "messageId": dispatch.get("messageId")}, "startedAt": str(started), "completedAt": str(completed) if completed else None, "worktree": worktree, "branch": branch}
                if recorded != presented:
                    raise Refused(f"authorization {auth['id']} was reconciled with different evidence; identical evidence is idempotent, this is conflicting: {presented} vs {recorded}", code="conflicting-evidence", authorization=auth["id"], recorded=recorded, presented=presented)
                self.store.journal(story, "retained-execution-already-reconciled", {"authorization": auth["id"], "task": owner, "run": run_id})
                return state
            safe_auth = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in auth["id"])
            backup = self.store.story_path(story).with_name(f"{story}.json.bak-{self.now().replace(':', '')}-{safe_auth}")
            if backup.exists():
                raise Refused(f"backup {backup.name} already exists; refusing to overwrite an earlier audit copy (retry a moment later)", code="backup-exists", backup=backup.name)
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
        with self.operation():
            self.require_activation("record-head")
            self._reload_run()
            self._require_run_active("record-head")
            state = self._story(story)
            if state.phase in ("checks-failed", "changes-requested", "repair-authorized"):
                raise Refused(f"{story} is {state.phase}; a new implementation needs a budgeted repair authorization bound to a fresh task first", code="repair-required", phase=state.phase)
            self._require_phase(state, "claimed", "implemented", "checks-passed", "review-authorized", "review-requested", "review-approved")
            if task_evidence is not None or (state.active_task and state.active_task["role"] == "implementer"):
                self._apply_task_evidence(state, task_evidence, "record-head")
            self._require_advancing_evidence(state, "record-head")  # released ownership is not a result: the bound implementer run must have completed
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
        with self.operation():
            self.require_activation("run-checks")
            self._reload_run()
            self._require_run_active("run-checks")
            state = self._story(story)
            self._require_phase(state, "implemented", "checks-passed", "checks-failed")
            self._require_no_obligation(state, "run-checks")  # a reviewer launched for an invalidated commit may still be running
            self._require_advancing_evidence(state, "run-checks")  # a head recorded over an unsuccessful or unidentified implementer run (older state) is not checkable evidence
            if not state.claim or not state.claim.get("worktree_path") or Path(cwd).resolve() != Path(state.claim["worktree_path"]).resolve():
                raise Refused(f"checks must run in the claimed worktree {state.claim and state.claim.get('worktree_path')}")
            if state.head_sha != sha:
                raise Refused(f"checks at {sha} do not match the recorded head {state.head_sha}", head=state.head_sha)
            head_before = git_head(cwd)
            if head_before != sha:
                raise Refused(f"worktree HEAD {head_before} is not the recorded sha {sha}")
            clean_before, dirt = git_clean(cwd)
            if clean_before is None:
                raise Refused(f"worktree status is unreadable before checks: {dirt}", code="worktree-unreadable")
            if not clean_before:
                raise Refused(f"worktree is not clean before checks: {dirt}")
            commands = list(self.policy.check_commands)
            kwargs = {"runner": runner} if runner else {}
            results = run_commands(commands, cwd, self.policy.check_timeout_minutes * 60, fail_fast=False, **kwargs)
            head_after = git_head(cwd)
            clean_after, dirt_after = git_clean(cwd)
            if head_after is None or clean_after is None:
                # git could not answer after the commands: no observation, so no check record (a failed record would spend a repair round)
                raise Refused(f"run-checks: worktree is unreadable after the commands (HEAD {head_after}, status: {dirt_after or 'unavailable'}); nothing recorded, retry when git answers", code="worktree-unreadable", head=head_after, status=dirt_after, commands=results)
            executed_all = len(results) == len(commands) and all("returncode" in r for r in results)
            passed = executed_all and all(r.get("returncode") == 0 for r in results) and head_after == sha and clean_after is True
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
        with self.operation():
            self.require_activation("authorize-review")
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
            self._require_advancing_evidence(state, "authorize-review")  # no reviewer is authorized for a head that no successful implementer run produced
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
        with self.operation():
            self.require_activation("authorize-repair")
            self._reload_run()
            self._require_run_active("authorize-repair")
            state = self._story(story)
            self._require_phase(state, "checks-failed", "changes-requested", "repair-authorized")
            self._require_no_active_task(state, "authorize-repair")
            pending = state.pending_authorization()
            if pending is not None and pending["purpose"] == "repair":
                return state
            self._require_advancing_evidence(state, "authorize-repair")  # a repair round builds on a head some successful implementer run produced; otherwise cancel or block
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
        with self.operation():
            self.require_activation("record-review")
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
            self._require_advancing_evidence(state, "record-review", sha)  # and must have completed, for exactly this commit, over a successful implementer run; a released interrupted/failed/cancelled worker proves nothing
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
        if pr.checks != "SUCCESS":
            # CI-backed evidence means a successful rollup: FAILURE, ERROR, EXPECTED, PENDING and no checks at all refuse alike
            raise Refused(f"PR #{pr_number} status check rollup at {sha} is {pr.checks or 'absent'}, not SUCCESS; a proposal needs CI-backed evidence", code="pr-checks-not-successful", checks=pr.checks)
        return pr

    def _require_current_approval(self, state: StoryState, sha: str, operation: str) -> None:
        """A proposal (first attempt or replay) needs the current local state to approve
        exactly ``sha``: phase review-approved, approved and head SHA equal to it, no active task."""
        self._require_phase(state, "review-approved")
        if state.head_sha != sha or state.approved_sha != sha:
            raise Refused(f"{operation}: approval is for {state.approved_sha}, head is {state.head_sha}, proposal names {sha}", code="approval-mismatch")
        self._require_no_obligation(state, operation)
        self._require_advancing_evidence(state, operation, sha)  # an approval recorded over an unsuccessful or unidentified implementer/reviewer execution (older state) is not current approval

    def propose_evidence(self, story: str, sha: str, pr_number: int, tasks: list[str], summary: str) -> StoryState:
        with self.operation():
            self.require_activation("propose-evidence")
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
        with self.operation():
            self.require_activation("block", advancing=False)
            return self._terminal(story, "blocked", reason, "block", "block", f"Blocked by run `{self.store.run_id}`: {reason}. Owner decision or new evidence required; nothing advanced. Project Status is owner-maintained.", task_evidence, no_launch)

    def cancel(self, story: str, reason: str, task_evidence: dict | None = None, no_launch: dict | None = None) -> StoryState:
        with self.operation():
            self.require_activation("cancel", advancing=False)
            return self._terminal(story, "cancelled", reason, "release", "release", f"Claim released by run `{self.store.run_id}`: {reason}. No completion is implied. Project Status is owner-maintained.", task_evidence, no_launch)

    def cancel_run(self, reason: str, task_evidence: dict[str, dict] | None = None, no_launch: dict[str, dict] | None = None) -> dict:
        """Stop admissions and release every story that owes nothing. Stories with an active
        task and no terminal evidence, or with an unresolved authorization and no no-launch
        attestation, stay owned (their pending authorization is revoked) and are reported; a
        cancelled run never advances or replays an advancing intent for them."""
        with self.operation():
            self.require_activation("cancel-run", advancing=False)
            self._reload_run()
            for name, value in (("task-evidence", task_evidence), ("no-launch", no_launch)):
                if value is not None and not isinstance(value, dict):
                    raise Refused(f"cancel-run: --{name} must be a JSON object keyed by story, not {type(value).__name__}", code="input-invalid")
            self.run.cancelled, self.run.stop_reason = True, reason
            self.store.save_run(self.run)
            self.store.journal(None, "run-cancelled", {"reason": reason})
            released, awaiting = [], []
            stories, unreadable = self.store.list_stories_tolerant()  # one corrupt file never aborts the release of the others
            for u in unreadable:
                awaiting.append({"story": u["story"], "task_id": None, "role": None, "authorization": None, "code": u["code"], "error": u["error"]})
            for s in stories:
                if not (s.active or s.phase == "conflict"):
                    continue
                try:
                    released.append(self.cancel(s.story, reason, (task_evidence or {}).get(s.story), (no_launch or {}).get(s.story)).to_dict())
                except Refused as exc:
                    # every refusal of one story is reported, none aborts the release of the others
                    awaiting.append({"story": s.story, "task_id": exc.detail.get("task_id"), "role": exc.detail.get("role"), "authorization": exc.detail.get("authorization"), "code": exc.code})
            return {"cancelled": released, "awaiting_worker_termination": awaiting}

    # -- recovery -------------------------------------------------------------------------
    def _cancel_stale_claim(self, state: StoryState, claim: Intent, changed: dict, why: str | None = None) -> StoryState:
        """The reservation can no longer complete: its revisions changed before it was
        checkpointed (or, ``why``, another admission precondition no longer holds). The story is
        cancelled and, when the claim comment reached GitHub (one or more markers), the release
        it owes is recorded as a cleanup intent in the same write as the cancellation, then
        posted idempotently; a failed post leaves it pending and the next resume replays it.
        Zero markers ⇒ the claim never landed, no release is owed. A done claim keeps its
        ``done`` record (history); a pending one is abandoned."""
        reason = f"{why or 'revisions changed'} before the reservation completed: {sorted(changed)}"
        found = [c for c in self._marked_comments(state.issue, state.story, "stale claim") if self._same_effect(c, claim)]
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
        with self.operation():
            self.require_activation("resume", advancing=False)
            self._reload_run()
            state = self._story(story)
            # owed cleanups (release, block) replay first and unconditionally: a cancelled or blocked
            # story whose worktree is gone still owes its comment, or its claim stays visible to other runs
            for intent in state.pending_intents():
                if intent.kind in CLEANUP_KINDS:
                    self._post_intent(state, intent)
            if state.active and state.claim and state.claim.get("worktree_path"):
                ok, why = worktree_check(state.claim["worktree_path"], state.claim["branch"])
                if not ok:
                    raise Refused(f"cannot resume {story}: {why}", code="worktree-mismatch")
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
                    self._settle_claim_race(state, claim, state.issue)
            if claim is not None and claim.status == "done" and state.phase == "reserved" and self._claim_unsettled(state):
                # the reservation posted its claim but the race re-read failed or the process died: settle it now (a lost race cancels and releases)
                if stop:
                    self._withhold_reconciliation(state, claim, STOP_REASONS[stop] + " (claim race unsettled; cancel-run finishes the story)")
                else:
                    self._settle_claim_race(state, claim, state.issue)
            for intent in state.intents:
                if intent.kind != "proposal" or intent.status != "done" or state.phase == "proposed":
                    continue
                sha, pr = intent.preconditions.get("sha"), intent.preconditions.get("pr")
                unresolved = state.unresolved_authorization()
                if stop:
                    self._withhold_reconciliation(state, intent, STOP_REASONS[stop])
                    continue
                if pr is None or sha is None:
                    self._withhold_reconciliation(state, intent, f"no current approval for {sha}: the completed proposal names no sha/pr ({sha}, {pr})")
                    continue
                try:  # the same current-approval gate as a fresh proposal, successful implementer and reviewer executions included
                    self._require_current_approval(state, sha, "resume-reconcile-proposal")
                except UnattendedError as exc:
                    self._withhold_reconciliation(state, intent, f"no current approval for {sha}: {exc.code}: {exc} (phase {state.phase}, approved {state.approved_sha}, head {state.head_sha}, active task {state.active_task}, unresolved authorization {unresolved and unresolved['id']}, pr {pr})")
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
                    elsewhere = self._claims_elsewhere(fresh, story)  # the same admission check as a fresh reserve, before the claim is posted
                    if elsewhere:
                        return self._cancel_stale_claim(state, intent, {f"claim elsewhere on {sid}": c for sid, c in elsewhere.items()}, why="another coordinator claimed another allowlisted story before this reservation completed")
                    self._post_intent(state, intent, phase_after="reserved" if state.phase == "claim-incomplete" else None)
                    self.store.journal(story, "reservation-completed-on-resume", {})
                    self._settle_claim_race(state, intent, state.issue)
                elif intent.kind == "proposal":
                    sha = intent.preconditions["sha"]
                    unresolved = state.unresolved_authorization()
                    try:  # the same current-approval gate as a fresh proposal; a failing gate abandons the replay, nothing is posted
                        self._require_current_approval(state, sha, "resume-proposal")
                    except UnattendedError as exc:
                        intent.status, intent.reason = "abandoned", f"no current approval for {sha}: {exc.code}: {exc} (phase {state.phase}, approved {state.approved_sha}, head {state.head_sha}, active task {state.active_task}, unresolved authorization {unresolved and unresolved['id']})"
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
        with self.operation():
            self.require_activation("rebase-revisions")
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
        """A coherent snapshot taken under the same locked gate as every other consumer: the run
        is reloaded and validated (identity, record shape, binding), the activation source is
        re-read, and an observed expiry or clock regression is recorded durably before it is
        reported, so a stop that status reports survives rollback and restart like one observed by
        record-head. The whole report is computed inside the lock from the operation's single
        clock observation: it cannot report an expiry its own durable check did not record. A valid recorded binding without the file is reported, never refused; a
        changed or malformed source, a foreign or malformed record refuse structurally."""
        with self.operation():
            self.require_activation("status", advancing=False)
            stories, unreadable = self.store.list_stories_tolerant()  # the recovery overview survives one corrupt file and names it; advancing operations stay strict
            counts = self.store.story_counts(stories)
            self.run.stories_claimed, self.run.delegated_tasks, self.run.repair_rounds = counts["stories_claimed"], counts["delegated_tasks"], counts["repair_rounds"]
            return {"run": self.run.__dict__, "budgets": {**counts, "unreadable_stories": len(unreadable), "partial": bool(unreadable)}, "environment": self.environment, "stories": [s.to_dict() for s in stories] + [{"story": u["story"], "error": u["code"], "detail": u["error"]} for u in unreadable], "unreadable_stories": unreadable, "journal_events": self.store.journal_count(), "live": self.live,
                    "stop": self._run_stop(), "policy_drift": {"bound_digest": self.run.policy_digest, "policy_digest": self.policy.digest} if self._policy_drift() else None,
                    "other_runs_with_active_stories": self.store.other_runs_with_active_stories(), "activation": {"recorded": self.run.activation, "recorded_stop": self.run.activation_stop, "presented": self.activation.binding() if self.activation else None, "stop": self._activation_stop(), "problems": [m for _, m in self._activation_problems()] if self.environment == "live" else []}, "agreement": OPERATING_AGREEMENT, "gaps": list(LIVE_EXECUTION_GAPS)}
