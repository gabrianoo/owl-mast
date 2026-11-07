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

import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path

from .activation import Activation, validate_binding, validate_high_water, validate_stop_record
from .errors import Refused

PHASES = ("claim-incomplete", "reserved", "claimed", "implemented", "checks-passed", "checks-failed", "review-authorized", "review-requested", "review-approved", "changes-requested", "repair-authorized", "proposed", "blocked", "cancelled", "conflict")
ACTIVE_PHASES = ("claim-incomplete", "reserved", "claimed", "implemented", "checks-passed", "checks-failed", "review-authorized", "review-requested", "review-approved", "changes-requested", "repair-authorized")
TERMINAL_PHASES = ("proposed", "blocked", "cancelled", "conflict")
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


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
        bad = [a.get("status") for a in raw.get("authorizations", []) if a.get("status") not in AUTHORIZATION_STATUSES]
        if bad:
            raise Refused(f"story state for {raw.get('story')!r} carries authorization statuses {bad}; expected {list(AUTHORIZATION_STATUSES)} (no silent migration)", code="state-schema-mismatch")
        raw["intents"] = [Intent(**i) for i in raw.get("intents", [])]
        return cls(**raw)


class Store:
    def __init__(self, state_dir: Path, run_id: str):
        self.state_dir = Path(state_dir)
        self.root = self.state_dir / run_id
        self.run_id = run_id
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
        self.state_dir.mkdir(parents=True, exist_ok=True)
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
    OPTIONAL_RUN_KEYS = frozenset({"activation", "last_observed_at", "activation_stop"})  # live-only controls, absent from records written before the opt-in (read as null; never added by a load)
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
        for key in ("stories_claimed", "delegated_tasks", "repair_rounds"):
            if not isinstance(raw[key], int) or isinstance(raw[key], bool) or raw[key] < 0:
                problems.append(f"{key} must be a non-negative integer")
        if not isinstance(raw["cancelled"], bool):
            problems.append("cancelled must be a boolean")
        if raw["stop_reason"] is not None and not isinstance(raw["stop_reason"], str):
            problems.append("stop_reason must be null or a string")
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

    def ensure_run(self, repo: str, policy_digest: str, environment: str, activation: Activation | None = None, policy=None, now: str | None = None) -> RunState:
        """Create the run or validate its binding, under the store lock. A run belongs to exactly
        one repository, policy digest and transport environment (fixture or live); any other
        pairing is refused before recovery or effects, so synthetic state can never drive
        production.

        This is the only place a live run is created. It needs the loaded :class:`Activation`
        itself (never a dictionary), the :class:`Policy` in use and the current time, and it
        persists the binding record only after ``Activation.problems`` is empty for exactly this
        run id, policy and moment. Retained run artifacts (story checkpoints, a journal) without
        run metadata are an incomplete restore: no new run is created around them and nothing is
        written (``run-metadata-missing``). An existing live run's record is re-validated on every
        call; a presented activation must be the one the run was created under."""
        with self.locked():
            run = self.bound_run()
            if run is None:
                retained = self.retained_artifacts()
                if retained:
                    raise Refused(f"run {self.run_id}: run.json is missing but {len(retained)} run artifact(s) are retained ({', '.join(retained[:4])}{'…' if len(retained) > 4 else ''}); refusing to create a new {environment} run around state of unknown provenance; restore the run metadata or recover by hand (nothing written)", code="run-metadata-missing", retained=retained)
                binding = None
                if environment == "live":
                    if not isinstance(activation, Activation) or policy is None or now is None:
                        raise Refused(f"run {self.run_id}: a live run is created only under a loaded, validated activation authorization (Activation, policy and current time); a binding dictionary or an unvalidated record is refused", code="activation-required")
                    problems = activation.problems(policy, self.run_id, now)
                    if problems:
                        raise Refused(f"run {self.run_id}: activation {activation.id} does not currently authorize this run: " + "; ".join(m for _, m in problems), code=Activation.stop_code(problems), problems=[m for _, m in problems])
                    if (activation.repository, activation.policy_digest) != (repo, policy_digest):
                        raise Refused(f"run {self.run_id}: activation {activation.id} binds {activation.repository} / {activation.policy_digest[:12]}, not {repo} / {policy_digest[:12]}", code="activation-mismatch")
                    binding = validate_binding(activation.binding(validated_at=now), self.run_id, repo, policy_digest)
                run = RunState(self.run_id, repo, policy_digest, utcnow(), environment=environment, activation=binding)
                self.save_run(run)
                self.journal(None, "run-started", {"repo": repo, "policy_digest": policy_digest, "environment": environment, "activation": run.activation})
            elif (run.repo, run.policy_digest) != (repo, policy_digest):
                raise Refused(f"run {self.run_id} is bound to {run.repo} / policy {run.policy_digest[:12]}; refusing {repo} / {policy_digest[:12]}", code="run-binding-mismatch")
            elif run.environment != environment:
                raise Refused(f"run {self.run_id} state belongs to the {run.environment!r} environment; refusing to reuse it with a {environment!r} transport", code="environment-mismatch")
            elif environment == "live" and activation is not None:
                if not isinstance(activation, Activation):
                    raise Refused(f"run {self.run_id}: an activation is presented as the loaded document, not as a dictionary", code="activation-invalid")
                if not run.activation:
                    raise Refused(f"run {self.run_id} was never activated; activation {activation.id} cannot adopt it (a run is activated only at creation)", code="activation-required")
                if not activation.matches(run.activation):
                    raise Refused(f"run {self.run_id} was created under activation {run.activation.get('id')!r}; refusing activation {activation.id!r} (digest {activation.digest[:12]})", code="activation-mismatch")
            return run

    # -- stories -------------------------------------------------------------------------
    def story_path(self, story: str) -> Path:
        return self.root / "stories" / f"{story}.json"

    def load_story(self, story: str) -> StoryState | None:
        path = self.story_path(story)
        if not path.exists():
            return None
        return StoryState.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def save_story(self, state: StoryState) -> None:
        state.updated_at = utcnow()
        atomic_write_text(self.story_path(state.story), json.dumps(state.to_dict(), indent=1, sort_keys=True))

    def list_stories(self) -> list[StoryState]:
        folder = self.root / "stories"
        if not folder.exists():
            return []
        return [StoryState.from_dict(json.loads(p.read_text(encoding="utf-8"))) for p in sorted(folder.glob("*.json"))]

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

    def story_counts(self) -> dict[str, int]:
        """Durable budget consumption derived from the story files: stories admitted, task
        authorizations issued (every issued authorization counts, bound or not, so a crash or
        retry cannot reclaim a spent slot) and repair rounds authorized."""
        stories = self.list_stories()
        return {
            "stories_claimed": len(stories),
            "delegated_tasks": sum(len(s.authorizations) for s in stories),
            "repair_rounds": sum(s.repair_rounds for s in stories),
        }

    # -- journal -------------------------------------------------------------------------
    @property
    def journal_path(self) -> Path:
        return self.root / "journal.jsonl"

    def journal(self, story: str | None, event: str, detail: dict | None = None) -> int:
        self.root.mkdir(parents=True, exist_ok=True)
        seq = self.journal_count() + 1
        line = json.dumps({"seq": seq, "at": utcnow(), "story": story, "event": event, "detail": detail or {}}, sort_keys=True)
        with self.journal_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        return seq

    def journal_count(self) -> int:
        if not self.journal_path.exists():
            return 0
        with self.journal_path.open("r", encoding="utf-8") as fh:
            return sum(1 for _ in fh)

    def read_journal(self) -> list[dict]:
        if not self.journal_path.exists():
            return []
        return [json.loads(l) for l in self.journal_path.read_text(encoding="utf-8").splitlines() if l.strip()]
