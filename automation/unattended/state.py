"""Machine-owned run state: per-story checkpoints, an append-only journal, write-ahead
intents for every external effect, a cross-process store lock and run binding.

Layout under ``<state_dir>/``::

    .lock                       exclusive advisory lock (fcntl) held for every operation
    <run_id>/run.json           binding (repo, policy digest), budgets, counters, cancellation
    <run_id>/journal.jsonl      append-only events (seq, at, story, event, detail)
    <run_id>/stories/<ID>.json  checkpoint per story (phase, claim, revisions, head, checks,
                                reviews, intents, task authorizations, active task)

Every file write is atomic (temp file + ``os.replace``). Atomic replacement alone does not
serialize two processes, so every operation that reads budgets or produces effects runs
inside :meth:`Store.locked`, which takes the store-wide lock non-blockingly and refuses
when another process holds it. A run is bound to one repository and one policy digest;
reopening it with another refuses before any recovery or effect.

Budgets (stories admitted, task authorizations issued, repair rounds) are derived from the
story files under the lock; the counters in ``run.json`` are a refreshed cache for
``status`` only, so a crash between two file writes can never under-count a spent budget.
"""

from __future__ import annotations

import errno
import fcntl
import json
import os
import re
import tempfile
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path

from .activation import Activation, _parse_time, abort_activation_use, confirm_activation_use, record_activation_use, refresh_activation, validate_binding, validate_high_water, validate_stop_record
from .errors import Refused

# A run id names a directory under the state dir and a marker value: one path segment, no
# separators, no leading dot, at most 64 characters, lowercase only (state dirs may live on a
# case-insensitive filesystem, where ``Run-1`` and ``run-1`` would share one directory but write
# different marker values) and never ``--`` (a marker value cannot carry it).
RUN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


def validate_run_id(run_id) -> str:
    if not isinstance(run_id, str) or not RUN_ID_RE.match(run_id) or run_id in (".", "..") or "--" in run_id:
        raise Refused(f"run id {run_id!r} is invalid: one path segment of lowercase [a-z0-9._-] (1..64 characters, starting with a letter or digit, no '--')", code="run-id-invalid", run_id=str(run_id))
    return run_id

PHASES = ("claim-incomplete", "reserved", "claimed", "implemented", "checks-passed", "checks-failed", "review-authorized", "review-requested", "review-approved", "changes-requested", "repair-authorized", "proposed", "blocked", "cancelled", "conflict")
ACTIVE_PHASES = ("claim-incomplete", "reserved", "claimed", "implemented", "checks-passed", "checks-failed", "review-authorized", "review-requested", "review-approved", "changes-requested", "repair-authorized")
TERMINAL_PHASES = ("proposed", "blocked", "cancelled", "conflict")
FINISHED_PHASES = ("proposed", "blocked", "cancelled")  # the phases in which a run no longer owns the story; ``conflict`` still does (its claim may be restored)


def story_ownership(path: Path) -> tuple[str, bool]:
    """How a story file of another run reads for ownership: ``(phase label, owned)``. The label
    is the recorded phase when it is one of ``PHASES``; a file that is not readable JSON, not a
    record, has no string phase or names a phase this code does not know is reported as such
    and counts as owned (fail closed). Every reader of another run's ownership uses this one
    rule, so admission and ``dismiss-claim`` never disagree."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        phase = raw.get("phase") if isinstance(raw, dict) else None
        if not isinstance(phase, str):
            raise ValueError("no phase")
    except (OSError, UnicodeDecodeError, ValueError):
        return f"unreadable story file {path.name}", True
    if phase not in PHASES:
        return f"unknown phase {phase!r} in story file {path.name}", True
    return phase, phase not in FINISHED_PHASES
ADVANCING_KINDS = ("claim", "proposal")  # intents that move a story forward; never replayed from a terminal story or a cancelled run
# A task authorization is an ownership obligation from the moment it is issued until it is resolved:
#   pending      issued, may be launched, its receipt binds into work
#   revoked      no longer authorizes work (story stopped, evidence invalidated) but a launch may have
#                happened: its receipt binds for cleanup only; UNRESOLVED
#   consumed     a receipt was bound (task_id set); ownership continues as the active task
#   not-launched the coordinator attested, or the state proves, that no task was launched for it
UNRESOLVED_AUTHORIZATION_STATUSES = ("pending", "revoked")
AUTHORIZATION_STATUSES = UNRESOLVED_AUTHORIZATION_STATUSES + ("consumed", "not-launched")
STORY_SCHEMA = 3  # 3: authorization statuses above (2 used "abandoned", which hid a possibly launched task)


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def fsync_directory(path: Path) -> None:
    """Make a rename in ``path`` durable: without this a power loss can bring the old file back.
    A filesystem that cannot sync a directory handle (``EINVAL``/``ENOTSUP`` on some network or
    translated mounts) leaves the write as durable as the file sync made it; any other error
    propagates, the write having already landed."""
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    except OSError as exc:
        if exc.errno not in (errno.EINVAL, errno.ENOTSUP, errno.EOPNOTSUPP):
            raise
    finally:
        os.close(fd)


def ensure_directory(path: Path) -> None:
    """``mkdir -p`` whose new directory entries are durable: every directory created here is
    fsynced in its parent (top-down), so a power loss cannot drop a new run or stories directory
    whose first checkpoint, or whose claim comment, already exists."""
    path = Path(path)
    missing: list[Path] = []
    probe = path
    while not probe.exists():
        missing.append(probe)
        if probe.parent == probe:
            break
        probe = probe.parent
    if not missing:
        return
    path.mkdir(parents=True, exist_ok=True)
    for created in reversed(missing):  # top-down: a parent's entry before its child's
        fsync_directory(created.parent)


def atomic_write_text(path: Path, text: str) -> None:
    ensure_directory(path.parent)
    fd, tmp = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    fsync_directory(path.parent)


class StoreBusy(Refused):
    code = "store-busy"


@dataclass
class RunState:
    run_id: str
    repo: str
    policy_digest: str
    started_at: str
    environment: str = "fixture"  # fixture | live — the transport kind this run's state belongs to
    stories_claimed: int = 0  # cache of Store.story_counts(); enforcement never reads these three
    delegated_tasks: int = 0  # task authorizations issued (bound or not)
    repair_rounds: int = 0
    cancelled: bool = False
    stop_reason: str | None = None
    activation: dict | None = None  # live runs only: the activation binding record (activation.BINDING_RECORD_KEYS) the run was created under
    last_observed_at: str | None = None  # live runs only: the latest injected/current time an operation observed under the lock (clock-regression high-water)
    activation_stop: dict | None = None  # live runs only: a durable observed stop {code, observed_at, message}; once recorded the run never advances again, whatever the clock says
    instance: str | None = None  # this run directory's nonce, carried as ``inst`` in its markers: two coordinators that share a run id (two machines, two state dirs) are still told apart; absent on runs created before it existed
    targets: dict | None = None  # the policy targets (implementer, reviewer) the run was created under; a late receipt under policy drift is validated against these, not against the drifted policy


@dataclass
class Intent:
    """A write-ahead record of one external effect. ``op`` is the stable operation identity
    (``claim``, ``release``, ``block``, ``proposal-<sha12>-pr<n>``); a retry of the same
    operation reuses the same intent and marker instead of allocating a new one."""

    op: str
    kind: str
    marker: dict[str, str]
    body: str = ""  # the complete comment text; a replay posts exactly this
    preconditions: dict = field(default_factory=dict)  # what must still hold before an advancing replay
    status: str = "pending"  # pending | done | abandoned
    reason: str | None = None
    comment_id: int | None = None
    created_at: str = field(default_factory=utcnow)
    completed_at: str | None = None


@dataclass
class StoryState:
    story: str
    issue: int
    item_id: str
    phase: str
    run_id: str
    claim: dict | None = None
    revisions: dict = field(default_factory=dict)  # issue/item revisions verified at admission
    implementer_receipts: list[dict] = field(default_factory=list)
    reviewer_receipts: list[dict] = field(default_factory=list)
    head_sha: str | None = None
    approved_sha: str | None = None
    checks: list[dict] = field(default_factory=list)
    reviews: list[dict] = field(default_factory=list)
    repair_rounds: int = 0
    blocked: dict | None = None
    intents: list[Intent] = field(default_factory=list)
    proposal: dict | None = None
    # Task capacity and ownership, independent of ``phase`` and of HEAD notifications.
    authorizations: list[dict] = field(default_factory=list)  # {id, role, purpose, sha, round, issued_at, status (AUTHORIZATION_STATUSES), task_id, reason, ...}
    active_task: dict | None = None  # {taskId, role, authorization, bound_at[, cleanup_only]}; cleared only by terminal task evidence
    task_history: list[dict] = field(default_factory=list)  # terminal evidence records {taskId, role, status, at, operation}
    schema: int = STORY_SCHEMA
    updated_at: str = field(default_factory=utcnow)

    @property
    def active(self) -> bool:
        return self.phase in ACTIVE_PHASES

    def pending_intents(self) -> list[Intent]:
        return [i for i in self.intents if i.status == "pending"]

    def pending_advancing_intents(self) -> list[Intent]:
        return [i for i in self.pending_intents() if i.kind in ADVANCING_KINDS]

    def intent(self, op: str) -> Intent | None:
        return next((i for i in self.intents if i.op == op), None)

    def pending_authorization(self) -> dict | None:
        """The authorization that still authorizes work (a receipt binds into work)."""
        return next((a for a in self.authorizations if a["status"] == "pending"), None)

    def unresolved_authorization(self) -> dict | None:
        """The authorization that is still an ownership obligation: pending or revoked. At most
        one exists per story, because no authorization is issued while one is unresolved."""
        return next((a for a in self.authorizations if a["status"] in UNRESOLVED_AUTHORIZATION_STATUSES), None)

    def authorization(self, auth_id: str) -> dict | None:
        return next((a for a in self.authorizations if a["id"] == auth_id), None)

    def owner_task(self) -> str | None:
        """The implementer task that owns this story: the one bound to its implementation
        authorization. Only it may be re-run for a repair."""
        auth = next((a for a in self.authorizations if a["purpose"] == "implementation" and a.get("task_id")), None)
        return auth["task_id"] if auth else None

    def executions(self) -> set[tuple[str, str]]:
        """Every (taskId, runId) pair this story has bound or recorded. Legacy task-only
        records (no run id) contribute nothing here; they are never completed by inference."""
        pairs = set()
        for r in self.implementer_receipts + self.reviewer_receipts + self.task_history:
            if r.get("taskId") and r.get("runId"):
                pairs.add((r["taskId"], r["runId"]))
        for a in self.authorizations:
            if a.get("task_id") and a.get("run_id"):
                pairs.add((a["task_id"], a["run_id"]))
        if self.active_task and self.active_task.get("runId"):
            pairs.add((self.active_task["taskId"], self.active_task["runId"]))
        return pairs

    TERMINAL_STATUSES = ("completed", "cancelled", "failed", "result_available", "terminal", "interrupted")  # the real transport reports a cancelled run as interrupted
    # Only these terminal statuses are a completed execution. interrupted (task_cancel), failed and
    # cancelled acknowledge termination without any completed work; the bare "terminal" marker says
    # nothing about the outcome. Success is never derived from a record merely being terminal.
    SUCCESSFUL_STATUSES = ("completed", "result_available")

    @classmethod
    def record_successful(cls, record: dict) -> bool:
        """Outcome of a terminal history record, interpreted fail-closed: the status must be a
        successful one AND the stored ``successful`` flag, when present, must agree. A legacy
        record without the flag is read from its status; a contradictory flag (``true`` on a
        failed/cancelled/interrupted status, or ``false`` on a completed one) never counts as
        success."""
        if not isinstance(record, dict):
            return False
        flag = record.get("successful")
        if flag is not None and flag is not True:
            return False
        return record.get("status") in cls.SUCCESSFUL_STATUSES

    def terminal_record(self, task_id: str | None, run_id: str | None) -> dict | None:
        """The latest terminal history record of exactly the identified execution
        ``(task_id, run_id)``, whatever its role, authorization or outcome; None when either
        identity is missing (a task-only legacy record identifies no execution)."""
        if not task_id or not run_id:
            return None
        return next((r for r in reversed(self.task_history) if r.get("taskId") == task_id and r.get("runId") == run_id), None)

    def successful_execution(self, task_id: str | None, run_id: str | None, role: str, authorization: str | None) -> dict | None:
        """The terminal history record proving that exactly the identified execution
        ``(task_id, run_id)``, bound to exactly ``authorization`` in ``role``, completed
        successfully; None otherwise. Every identity must be present and match exactly: an
        absent task, run or authorization identity (on the selection or on the record) never
        matches, another run of the same task, another role, another authorization or an
        unsuccessful/contradictory outcome proves nothing. Task-only completion is not an
        identified execution."""
        record = self.terminal_record(task_id, run_id)
        if record is None or not authorization or not record.get("runId") or not record.get("authorization"):
            return None
        if record.get("role") != role or str(record.get("authorization")) != str(authorization):
            return None
        return record if self.record_successful(record) else None

    def predecessor_terminal(self, task_id: str, identified: bool = True) -> bool:
        """True when ``task_id`` is not the active task and a terminal record exists for it.
        ``identified`` (the ordinary fresh-execution check) counts only records that carry a
        run id: a legacy task-only terminal record cannot prove which run ended, so it never
        admits an ordinary rebind. The audited stopped-run recovery passes ``identified=False``
        and supplies its own dispatch/time correlation instead."""
        if self.active_task and self.active_task.get("taskId") == task_id:
            return False
        return any(r.get("taskId") == task_id and r.get("status") in self.TERMINAL_STATUSES and (r.get("runId") or not identified) for r in self.task_history)

    def legacy_task_only_history(self, task_id: str) -> bool:
        return any(r.get("taskId") == task_id and not r.get("runId") for r in self.task_history + self.implementer_receipts + self.reviewer_receipts)

    def abandon_advancing_intents(self, reason: str) -> list[str]:
        """Mark every pending advancing intent abandoned (in memory; the caller saves)."""
        ops = []
        for intent in self.pending_advancing_intents():
            intent.status, intent.reason = "abandoned", reason
            ops.append(intent.op)
        return ops

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict) -> "StoryState":
        raw = dict(raw)
        expected = {f.name for f in fields(cls)}
        if raw.get("schema") != STORY_SCHEMA or set(raw) != expected:
            raise Refused(f"story state for {raw.get('story')!r} has schema {raw.get('schema')!r} / keys {sorted(set(raw) ^ expected)}; expected schema {STORY_SCHEMA} (no silent migration)", code="state-schema-mismatch")
        problems = cls._value_problems(raw)
        if problems:
            raise Refused(f"story state for {raw.get('story')!r} is not a story record: " + "; ".join(problems) + "; nothing is advanced or released on it", code="state-corrupt", problems=problems)
        bad = [a.get("status") for a in raw.get("authorizations", []) if a.get("status") not in AUTHORIZATION_STATUSES]
        if bad:
            raise Refused(f"story state for {raw.get('story')!r} carries authorization statuses {bad}; expected {list(AUTHORIZATION_STATUSES)} (no silent migration)", code="state-schema-mismatch")
        raw["intents"] = [Intent(**i) for i in raw.get("intents", [])]
        return cls(**raw)

    @staticmethod
    def _value_problems(raw: dict) -> list[str]:
        """Field values a record must carry to be read at all: a known phase and the basic types
        of every field a budget, an ownership check or a release reads. A file with every key but
        ``"phase": "Reserved"`` or ``null`` would otherwise load as neither active nor conflict and
        be skipped silently by admission and by ``cancel-run``."""
        problems: list[str] = []
        if raw.get("phase") not in PHASES:
            problems.append(f"phase {raw.get('phase')!r} is not one of {list(PHASES)}")
        for key in ("story", "run_id"):
            if not isinstance(raw.get(key), str) or not raw.get(key, "").strip():
                problems.append(f"{key} must be a non-empty string")
        if not isinstance(raw.get("issue"), int) or isinstance(raw.get("issue"), bool):
            problems.append("issue must be an integer")
        if not isinstance(raw.get("item_id"), str):
            problems.append("item_id must be a string")
        for key in ("claim", "blocked", "active_task", "proposal"):
            if raw.get(key) is not None and not isinstance(raw.get(key), dict):
                problems.append(f"{key} must be null or an object")
        for key in ("revisions",):
            if not isinstance(raw.get(key), dict):
                problems.append(f"{key} must be an object")
        for key in ("implementer_receipts", "reviewer_receipts", "checks", "reviews", "intents", "authorizations", "task_history"):
            value = raw.get(key)
            if not isinstance(value, list) or any(not isinstance(v, dict) for v in value):
                problems.append(f"{key} must be a list of objects")
        if not isinstance(raw.get("repair_rounds"), int) or isinstance(raw.get("repair_rounds"), bool) or raw.get("repair_rounds", 0) < 0:
            problems.append("repair_rounds must be a non-negative integer")
        for key in ("head_sha", "approved_sha"):
            if raw.get(key) is not None and not isinstance(raw.get(key), str):
                problems.append(f"{key} must be null or a string")
        if isinstance(raw.get("authorizations"), list):
            for a in raw["authorizations"]:
                if isinstance(a, dict) and (not isinstance(a.get("id"), str) or not isinstance(a.get("purpose"), str) or not isinstance(a.get("role"), str)):
                    problems.append("every authorization needs string id, purpose and role")
                    break
        return problems


class Store:
    def __init__(self, state_dir: Path, run_id: str):
        self.state_dir = Path(state_dir)
        self.run_id = validate_run_id(run_id)  # one directory segment: no escape from the state dir, no shared root
        self.root = self.state_dir / self.run_id
        self._lock_depth = 0
        self._lock_fh = None
        self._lock_owner = None

    # -- locking -------------------------------------------------------------------------
    @contextmanager
    def locked(self, owner: object = None):
        """Exclusive, non-blocking, store-wide (fcntl). Re-entrant only for the same
        ``owner`` (one Coordinator instance); any other caller, in this process or another,
        gets :class:`StoreBusy` instead of interleaving."""
        if self._lock_depth:
            if owner is not None and owner is self._lock_owner:
                self._lock_depth += 1
                try:
                    yield
                finally:
                    self._lock_depth -= 1
                return
            raise StoreBusy(f"store {self.state_dir} is locked by another coordinator in this process")
        ensure_directory(self.state_dir)
        fh = open(self.state_dir / ".lock", "a+", encoding="utf-8")
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            fh.close()
            raise StoreBusy(f"another coordinator holds the store lock {self.state_dir / '.lock'}: {exc}") from exc
        self._lock_fh, self._lock_depth, self._lock_owner = fh, 1, owner
        try:
            yield
        finally:
            self._lock_depth = 0
            self._lock_fh = None
            self._lock_owner = None
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            finally:
                fh.close()

    # -- run -----------------------------------------------------------------------------
    @property
    def run_path(self) -> Path:
        return self.root / "run.json"

    RUN_KEYS = frozenset(f.name for f in fields(RunState))
    OPTIONAL_RUN_KEYS = frozenset({"activation", "last_observed_at", "activation_stop", "instance", "targets"})  # controls absent from records written before they existed (read as null; never added by a load)
    ENVIRONMENTS = ("fixture", "live")

    def load_run(self) -> RunState | None:
        """The run record as persisted, validated at this one load boundary before anything reads
        it: exactly the :class:`RunState` fields with their types, the ``run_id`` **equal to the
        run this store was opened for** (a genuine record restored from another run directory is
        a foreign record, not this run: ``run-identity-mismatch``), and well-formed time controls
        (``last_observed_at`` null or a strict UTC time; ``activation_stop`` null or a complete stop
        record). A malformed record refuses ``run-state-invalid`` and is never rewritten, migrated
        or read as the absence of a control. The live activation record itself is validated by
        :meth:`bound_run`."""
        if not self.run_path.exists():
            return None
        try:
            raw = json.loads(self.run_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            raise Refused(f"run {self.run_id}: run.json is not readable JSON ({exc}); nothing is advanced or released on it", code="run-state-invalid") from exc
        if not isinstance(raw, dict) or not (self.RUN_KEYS - self.OPTIONAL_RUN_KEYS) <= set(raw) <= self.RUN_KEYS:
            raise Refused(f"run {self.run_id}: run.json keys {sorted(set(raw) ^ self.RUN_KEYS) if isinstance(raw, dict) else type(raw).__name__} differ from the run record shape; no silent migration (restore run.json from the run that wrote it, or recover by hand)", code="run-state-invalid")
        raw = {**{k: None for k in self.OPTIONAL_RUN_KEYS}, **raw}
        problems: list[str] = []
        for key in ("run_id", "repo", "policy_digest", "started_at", "environment"):
            if not isinstance(raw[key], str) or not raw[key].strip():
                problems.append(f"{key} must be a non-empty string")
        if raw["environment"] not in self.ENVIRONMENTS:
            problems.append(f"environment {raw['environment']!r} is not one of {list(self.ENVIRONMENTS)}")
        if isinstance(raw["started_at"], str) and raw["started_at"].strip():
            _parse_time(raw["started_at"], "started_at", problems)  # the wall-clock origin: a strict UTC time, or the record refuses instead of crashing in _elapsed
        for key in ("stories_claimed", "delegated_tasks", "repair_rounds"):
            if not isinstance(raw[key], int) or isinstance(raw[key], bool) or raw[key] < 0:
                problems.append(f"{key} must be a non-negative integer")
        if not isinstance(raw["cancelled"], bool):
            problems.append("cancelled must be a boolean")
        if raw["stop_reason"] is not None and not isinstance(raw["stop_reason"], str):
            problems.append("stop_reason must be null or a string")
        if raw["instance"] is not None and (not isinstance(raw["instance"], str) or not re.match(r"^[0-9a-f]{8,32}$", raw["instance"])):
            problems.append("instance must be null or a lowercase hex nonce")
        if raw["targets"] is not None and (not isinstance(raw["targets"], dict) or set(raw["targets"]) != {"implementer", "reviewer"} or any(not isinstance(t, dict) for t in raw["targets"].values())):
            problems.append("targets must be null or an object with implementer and reviewer records")
        if problems:
            raise Refused(f"run {self.run_id}: run.json is not a valid run record: " + "; ".join(problems) + "; nothing is advanced or released on it (restore run.json from the run that wrote it, or recover by hand)", code="run-state-invalid", problems=problems)
        if raw["run_id"] != self.run_id:
            raise Refused(f"run {self.run_id}: run.json records run {raw['run_id']!r}; a record restored from another run is not this run and authorizes nothing here (its approvals and obligations belong to {raw['run_id']!r}); nothing is advanced, released or rewritten", code="run-identity-mismatch", recorded_run_id=raw["run_id"])
        validate_high_water(raw["last_observed_at"], self.run_id)
        validate_stop_record(raw["activation_stop"], self.run_id)
        return RunState(**raw)

    def save_run(self, run: RunState) -> None:
        atomic_write_text(self.run_path, json.dumps(asdict(run), indent=1, sort_keys=True))

    def retained_artifacts(self) -> list[str]:
        """Run artifacts present without run metadata: story checkpoints and the journal."""
        found = []
        if self.journal_path.exists():
            found.append("journal.jsonl")
        folder = self.root / "stories"
        if folder.exists():
            found.extend(f"stories/{p.name}" for p in sorted(folder.glob("*.json")))
        return found

    def bound_run(self) -> RunState | None:
        """The run as persisted (:meth:`load_run`: shape, time controls and run identity), with a
        live run's activation binding re-validated strictly against **the run selected by this
        store** (``Store.run_id``), never against identities read from the same file. A live run
        whose record is missing is returned as is (its consumers report ``activation-required``);
        a partial, foreign or inconsistent record refuses ``activation-binding-invalid`` and
        nothing is advanced or released."""
        run = self.load_run()
        if run is not None and run.environment == "live" and run.activation is not None:
            validate_binding(run.activation, self.run_id, run.repo, run.policy_digest)
        return run

    @staticmethod
    def digest_bound(recorded: str, policy) -> bool:
        """Whether a run recorded under ``recorded`` is bound to ``policy``: its canonical digest,
        or the legacy raw-bytes digest of exactly these bytes (runs created before the canonical
        digest existed are recognized, never rewritten)."""
        return recorded in (policy.digest, getattr(policy, "raw_digest", None))

    def ensure_run(self, repo: str, policy_digest: str, environment: str, activation: Activation | None = None, policy=None, now: str | None = None, owner: object = None, create: bool = True) -> RunState:
        """Create the run or validate its binding, under the store lock (re-entrant for ``owner``,
        the coordinator that already holds it). A run belongs to exactly one repository and
        transport environment (fixture or live); any other pairing is refused before recovery or
        effects, so synthetic state can never drive production. A run is also bound to the policy
        digest it was created under: reopening it under a policy whose bytes changed is **policy
        drift**, journaled once here and reported by the coordinator as a run stop (nothing is
        admitted or advanced; cleanup proceeds), never a silent rebind.

        This is the only place a live run is created. It needs the loaded :class:`Activation`
        itself (never a dictionary), the :class:`Policy` in use and the current time, and it
        re-reads the activation source under the lock (a missing, changed or malformed source
        refuses: the loaded object is a cache, the file is the approval) and persists the binding
        record only after ``Activation.creation_problems`` of the fresh document is empty for exactly
        this run id, policy and moment (current, and with a window that still covers the wall-clock
        budget). The use of the document is recorded in the use ledger first (``record_activation_use``,
        ``pending``; ``committed`` once ``run.json`` exists; ``aborted`` when ``save_run`` raised with
        no ``run.json``, so only that same creation may be retried): one activation creates exactly
        one run. A confirmation that cannot be written is journaled (``activation-use-unconfirmed``)
        and retried by every later open; the record stays ``pending`` until then. With
        ``create=False`` (every caller but an admitting one) a run that does not exist is refused
        ``run-not-found`` and nothing is written: a report or a cleanup command never starts a run
        or spends an approval. ``started_at`` is that same validated moment. Retained
        run artifacts (story checkpoints, a journal) without run metadata are an incomplete restore:
        no new run is created around them and nothing is written (``run-metadata-missing``). An
        existing live run's record is re-validated on every call; a presented activation is re-read
        from its source and must be the one the run was created under."""
        with self.locked(owner):
            run = self.bound_run()
            created = run is None
            if run is None:
                retained = self.retained_artifacts()
                if retained:
                    raise Refused(f"run {self.run_id}: run.json is missing but {len(retained)} run artifact(s) are retained ({', '.join(retained[:4])}{'…' if len(retained) > 4 else ''}); refusing to create a new {environment} run around state of unknown provenance; restore the run metadata or recover by hand (nothing written)", code="run-metadata-missing", retained=retained)
                if not create:
                    raise Refused(f"run {self.run_id} does not exist under {self.state_dir}; only an admitting command (reserve) creates a run (nothing written)", code="run-not-found")
                binding = None
                if environment == "live":
                    if not isinstance(activation, Activation) or policy is None or now is None:
                        raise Refused(f"run {self.run_id}: a live run is created only under a loaded, validated activation authorization (Activation, policy and current time); a binding dictionary or an unvalidated record is refused", code="activation-required")
                    # the loaded object is a cache: the source is re-read here, under the lock, and only the
                    # document as it is now can create the binding (missing: nothing is presented; changed or
                    # malformed: a different document; both refuse before any metadata or journal write)
                    activation = refresh_activation(activation, "run-start")
                    if activation is None:
                        raise Refused(f"run {self.run_id}: the activation source is gone; a live run is created only under a currently presented, approved activation (nothing written)", code="activation-required")
                    problems = activation.creation_problems(policy, self.run_id, now, state_dir=self.state_dir)
                    if problems:
                        raise Refused(f"run {self.run_id}: activation {activation.id} does not currently authorize creating this run: " + "; ".join(m for _, m in problems), code=Activation.stop_code(problems), problems=[m for _, m in problems])
                    if activation.repository != repo or activation.policy_digest != policy.digest:
                        raise Refused(f"run {self.run_id}: activation {activation.id} binds {activation.repository} / {activation.policy_digest[:12]}, not {repo} / {policy.digest[:12]}", code="activation-mismatch")
                    policy_digest = policy.digest  # a new live run binds the canonical digest (the raw-bytes digest is recognized only on runs that already carry it)
                    binding = validate_binding(activation.binding(validated_at=now), self.run_id, repo, policy_digest)
                    record_activation_use(activation, self.state_dir, self.run_id, now)  # one document, one run: refused (activation-used) before anything of this run is written; pending until run.json exists
                try:  # from the ledger record on: any failure before run.json exists marks the creation aborted
                    targets = {name: asdict(getattr(policy, name)) for name in ("implementer", "reviewer")} if policy is not None else None
                    run = RunState(self.run_id, repo, policy_digest, now or utcnow(), environment=environment, activation=binding, instance=uuid.uuid4().hex[:16], targets=targets)
                    self.save_run(run)
                except BaseException as original:
                    if binding is not None:
                        try:
                            abort_activation_use(activation, self.state_dir, self.run_id, self.run_path)  # known failed, no run.json: only this same creation may retry; a failure to mark leaves it pending (refused as unconfirmed)
                        except BaseException as inner:  # noqa: BLE001 - nothing raised while marking may replace the creation's own error
                            # not journaled: a journal line before run.json would be a retained artifact that refuses the retry
                            original.add_note(f"marking the use ledger record aborted also failed ({type(inner).__name__}: {inner}); it stays pending and refuses as an unconfirmed creation")
                    raise
                unconfirmed = confirm_activation_use(binding, self.state_dir, self.run_id)  # run.json exists: the document has now created its one run
                self.journal(None, "run-started", {"repo": repo, "policy_digest": policy_digest, "environment": environment, "activation": run.activation, "instance": run.instance})
                if unconfirmed:
                    self._journal_unconfirmed(unconfirmed)
            elif run.repo != repo:
                raise Refused(f"run {self.run_id} is bound to {run.repo}; refusing {repo}", code="run-binding-mismatch")
            elif run.environment != environment:
                raise Refused(f"run {self.run_id} state belongs to the {run.environment!r} environment; refusing to reuse it with a {environment!r} transport", code="environment-mismatch")
            elif run.policy_digest != policy_digest and not (policy is not None and self.digest_bound(run.policy_digest, policy)):
                # a changed policy strands nothing: the drift is recorded once and the coordinator treats it as a run stop
                last = next((e for e in reversed(self.read_journal()) if e.get("event") == "policy-drift"), None)
                if not last or (last.get("detail") or {}).get("policy_digest") != policy_digest:
                    self.journal(None, "policy-drift", {"bound_digest": run.policy_digest, "policy_digest": policy_digest, "consequence": "advancing refuses policy-drift; cleanup proceeds under the recorded binding"})
            if not created and environment == "live":
                unconfirmed = confirm_activation_use(run.activation, self.state_dir, self.run_id)  # settles a creation that died between run.json and the ledger confirmation
                if unconfirmed:
                    self._journal_unconfirmed(unconfirmed)
            if not created and environment == "live" and activation is not None:
                if not isinstance(activation, Activation):
                    raise Refused(f"run {self.run_id}: an activation is presented as the loaded document, not as a dictionary", code="activation-invalid")
                if not run.activation:
                    raise Refused(f"run {self.run_id} was never activated; activation {activation.id} cannot adopt it (a run is activated only at creation)", code="activation-required")
                activation = refresh_activation(activation, "run-open")  # the file is the approval here too: a source edited or removed since it was loaded is not the presented document
                if activation is not None and not activation.matches(run.activation):
                    raise Refused(f"run {self.run_id} was created under activation {run.activation.get('id')!r}; refusing activation {activation.id!r} (digest {activation.digest[:12]})", code="activation-mismatch")
            return run

    def _journal_unconfirmed(self, error: dict) -> None:
        """The ledger record of this run's creation could not be marked ``committed``: it stays
        ``pending``, so deleting the run directory now would leave an unconfirmed creation that
        refuses every later creation from the document (``activation-used``), never one that
        creates the run again. Journaled once per distinct ``(type, errno)``, the stable part of the
        error (its message names a random temporary file, so it differs on every attempt); every
        later open retries."""
        key = (error.get("type"), error.get("errno"))
        last = next((e for e in reversed(self.read_journal()) if e.get("event") == "activation-use-unconfirmed"), None)
        detail = (last or {}).get("detail") or {}
        if last is None or (detail.get("type"), detail.get("errno")) != key:
            self.journal(None, "activation-use-unconfirmed", {"error": error.get("message"), "type": key[0], "errno": key[1], "consequence": "the use ledger record stays pending; every later open retries the confirmation; until then a deleted run directory refuses as an unconfirmed creation"})

    # -- stories -------------------------------------------------------------------------
    def story_path(self, story: str) -> Path:
        return self.root / "stories" / f"{story}.json"

    def _read_story(self, path: Path) -> StoryState:
        """One story checkpoint, fail-closed: unreadable JSON, a non-object or a shape the
        dataclass cannot take refuse ``state-corrupt`` (a schema mismatch keeps its own code)."""
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            raise Refused(f"run {self.run_id}: story file {path.name} is not readable JSON ({exc}); nothing is advanced or released on it (restore it from the run that wrote it, or recover by hand)", code="state-corrupt", path=path.name) from exc
        if not isinstance(raw, dict):
            raise Refused(f"run {self.run_id}: story file {path.name} holds a {type(raw).__name__}, not a story record; nothing is advanced or released on it", code="state-corrupt", path=path.name)
        try:
            return StoryState.from_dict(raw)
        except Refused as exc:
            exc.detail.setdefault("path", path.name)
            raise
        except (TypeError, ValueError, AttributeError) as exc:
            raise Refused(f"run {self.run_id}: story file {path.name} does not fit the story record shape ({exc}); nothing is advanced or released on it", code="state-corrupt", path=path.name) from exc

    def load_story(self, story: str) -> StoryState | None:
        path = self.story_path(story)
        if not path.exists():
            return None
        return self._read_story(path)

    def save_story(self, state: StoryState) -> None:
        state.updated_at = utcnow()
        atomic_write_text(self.story_path(state.story), json.dumps(state.to_dict(), indent=1, sort_keys=True))

    def story_paths(self) -> list[Path]:
        folder = self.root / "stories"
        if not folder.exists():
            return []
        return sorted(folder.glob("*.json"))

    def list_stories(self) -> list[StoryState]:
        """Every story checkpoint, strictly: one unreadable file refuses (advancing operations and
        budgets never decide over a story they cannot read)."""
        return [self._read_story(p) for p in self.story_paths()]

    def list_stories_tolerant(self) -> tuple[list[StoryState], list[dict]]:
        """Every readable story checkpoint plus one ``{story, code, error}`` record per file that
        cannot be read: the recovery overview (``status``) and run-wide cleanup (``cancel-run``)
        must keep working, and keep reporting, exactly when one file is corrupt."""
        stories, unreadable = [], []
        for path in self.story_paths():
            try:
                stories.append(self._read_story(path))
            except Refused as exc:
                unreadable.append({"story": path.stem, "code": exc.code, "error": str(exc)})
        return stories, unreadable

    def other_runs_with_active_stories(self) -> dict[str, list[str]]:
        """Stories still owned by *other* runs under this state directory (any phase but
        ``proposed``, ``blocked`` or ``cancelled``: active, ``conflict``, unknown), by run id. Budgets and the single-active-story rule are scoped to
        one run id, so admission consults this before a second run can take a story while an
        earlier run of the same operator still owns one. A story file another run left
        unreadable, or in a phase this code does not know, is reported as owned (fail closed;
        ``story_ownership`` is the one rule, shared with ``dismiss-claim``)."""
        found: dict[str, list[str]] = {}
        if not self.state_dir.exists():
            return found
        # a run directory is one that carries run metadata; other directories under the state dir (backups, copies) are not runs
        for run_dir in sorted(p for p in self.state_dir.iterdir() if p.is_dir() and p.name.casefold() != self.run_id.casefold() and (p / "run.json").is_file()):
            for path in sorted((run_dir / "stories").glob("*.json")) if (run_dir / "stories").is_dir() else []:
                phase, owned = story_ownership(path)
                if owned:
                    found.setdefault(run_dir.name, []).append(f"{path.stem} ({phase})")
        return found

    def bound_executions(self) -> set[tuple[str, str]]:
        """Every (taskId, runId) pair bound anywhere in the run."""
        pairs = set()
        for story in self.list_stories():
            pairs |= story.executions()
        return pairs

    def bound_task_ids(self) -> set[str]:
        """Every T3 task id ever bound anywhere in the run: receipts of both roles, active
        tasks, consumed authorizations and terminal history, across every story and kept
        through cancellation and terminal phases. A task id is a run-wide identity that binds
        exactly once; a receipt reusing one is never fresh, whatever story or role presents it."""
        ids: set[str] = set()
        for s in self.list_stories():
            ids.update(str(r["taskId"]) for r in s.implementer_receipts + s.reviewer_receipts if r.get("taskId"))
            ids.update(str(r["taskId"]) for r in s.task_history if r.get("taskId"))
            if s.active_task and s.active_task.get("taskId"):
                ids.add(str(s.active_task["taskId"]))
            ids.update(str(a["task_id"]) for a in s.authorizations if a.get("task_id"))
        return ids

    def story_counts(self, stories: list[StoryState] | None = None) -> dict[str, int]:
        """Durable budget consumption derived from the story files: stories admitted, task
        authorizations issued (every issued authorization counts, bound or not, so a crash or
        retry cannot reclaim a spent slot) and repair rounds authorized. ``stories`` lets a
        tolerant reader (``status``) count what it could read; admission always reads strictly."""
        stories = self.list_stories() if stories is None else stories
        return {
            "stories_claimed": len(stories),
            "delegated_tasks": sum(len(s.authorizations) for s in stories),
            "repair_rounds": sum(s.repair_rounds for s in stories),
        }

    # -- journal -------------------------------------------------------------------------
    @property
    def journal_path(self) -> Path:
        return self.root / "journal.jsonl"

    def _journal_torn_tail(self) -> bool:
        """True when the journal ends in a partial line (a crash during an append)."""
        try:
            size = self.journal_path.stat().st_size
        except OSError:
            return False
        if size == 0:
            return False
        with self.journal_path.open("rb") as fh:
            fh.seek(-1, os.SEEK_END)
            return fh.read(1) != b"\n"

    def journal(self, story: str | None, event: str, detail: dict | None = None) -> int:
        ensure_directory(self.root)
        created = not self.journal_path.exists()
        torn = self._journal_torn_tail()  # a torn last line is terminated first, so the new event never concatenates onto it
        seq = self.journal_count() + 1
        line = json.dumps({"seq": seq, "at": utcnow(), "story": story, "event": event, "detail": detail or {}}, sort_keys=True)
        with self.journal_path.open("a", encoding="utf-8") as fh:
            fh.write(("\n" if torn else "") + line + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        if created:
            fsync_directory(self.root)  # the journal's own directory entry is durable from its first line
        return seq

    def journal_count(self) -> int:
        if not self.journal_path.exists():
            return 0
        with self.journal_path.open("r", encoding="utf-8") as fh:
            return sum(1 for _ in fh)

    def read_journal(self) -> list[dict]:
        """Every journal line in order. A line that does not parse (torn by a crash) is reported
        as a ``journal-torn-line`` entry carrying the raw text instead of making the whole
        journal unreadable; it occupies its line number so later ``seq`` values stay aligned."""
        if not self.journal_path.exists():
            return []
        out = []
        for number, line in enumerate(self.journal_path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                if not isinstance(entry, dict):
                    raise ValueError("not an object")
            except ValueError as exc:
                entry = {"seq": number, "at": None, "story": None, "event": "journal-torn-line", "detail": {"raw": line[:500], "error": str(exc)}}
            out.append(entry)
        return out
