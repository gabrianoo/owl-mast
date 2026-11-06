"""Machine-owned run state: per-story checkpoints, an append-only journal and write-ahead
intents for every GitHub effect.

Layout under ``<state_dir>/<run_id>/``::

    run.json            budgets, counters, cancellation
    journal.jsonl       append-only events (seq, at, story, event, detail)
    stories/<ID>.json   checkpoint per story (phase, claim, head, checks, reviews, intents)

Every file write is atomic (temp file + ``os.replace``). An intent is recorded *before* the
GitHub effect and completed *after* it; ``resume`` reconciles intents left pending by a
crash by looking for their marker on GitHub.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

PHASES = ("claimed", "claim-incomplete", "implemented", "checks-passed", "checks-failed", "review-requested", "review-approved", "changes-requested", "proposed", "blocked", "cancelled")
ACTIVE_PHASES = ("claimed", "claim-incomplete", "implemented", "checks-passed", "checks-failed", "review-requested", "review-approved", "changes-requested")
TERMINAL_PHASES = ("proposed", "blocked", "cancelled")


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


@dataclass
class RunState:
    run_id: str
    repo: str
    policy_digest: str
    started_at: str
    stories_claimed: int = 0
    delegated_tasks: int = 0
    repair_rounds: int = 0
    cancelled: bool = False
    stop_reason: str | None = None


@dataclass
class Intent:
    intent_id: str
    kind: str
    marker: dict[str, str]
    status: str = "pending"  # pending | done
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
    implementer_receipts: list[dict] = field(default_factory=list)
    reviewer_receipts: list[dict] = field(default_factory=list)
    head_sha: str | None = None
    approved_sha: str | None = None
    checks: list[dict] = field(default_factory=list)
    reviews: list[dict] = field(default_factory=list)
    repair_rounds: int = 0
    blocked: dict | None = None
    status_before_claim: str | None = None
    status_written: str | None = None
    item_updated_at: str | None = None
    intents: list[Intent] = field(default_factory=list)
    proposal: dict | None = None
    updated_at: str = field(default_factory=utcnow)

    @property
    def active(self) -> bool:
        return self.phase in ACTIVE_PHASES

    def pending_intents(self) -> list[Intent]:
        return [i for i in self.intents if i.status == "pending"]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict) -> "StoryState":
        raw = dict(raw)
        raw["intents"] = [Intent(**i) for i in raw.get("intents", [])]
        return cls(**raw)


class Store:
    def __init__(self, state_dir: Path, run_id: str):
        self.root = Path(state_dir) / run_id
        self.run_id = run_id

    # -- run -----------------------------------------------------------------------------
    @property
    def run_path(self) -> Path:
        return self.root / "run.json"

    def load_run(self) -> RunState | None:
        if not self.run_path.exists():
            return None
        return RunState(**json.loads(self.run_path.read_text(encoding="utf-8")))

    def save_run(self, run: RunState) -> None:
        atomic_write_text(self.run_path, json.dumps(asdict(run), indent=1, sort_keys=True))

    def ensure_run(self, repo: str, policy_digest: str) -> RunState:
        run = self.load_run()
        if run is None:
            run = RunState(self.run_id, repo, policy_digest, utcnow())
            self.save_run(run)
            self.journal(None, "run-started", {"repo": repo, "policy_digest": policy_digest})
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
