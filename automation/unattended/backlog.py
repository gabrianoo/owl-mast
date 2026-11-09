"""Backlog snapshot and mapping verification.

A snapshot is the normalized, read-only view of the GitHub backlog the rest of the tool
reasons about: one entry per issue carrying its stable ``owl-mast-id``, native parent,
``Depends on`` / ``Epic prerequisites`` lines, task checkboxes and the Project item with its
Status and Stable ID. ``verify_mapping`` checks the tracking contract (19 epics, 85
stories, 340 tasks, relationships) and reports every discrepancy instead of guessing.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .errors import Refused
from .github import IssueRecord, ProjectItem, Transport

ID_MARKER_RE = re.compile(r"<!--\s*owl-mast-id:\s*(?P<id>E\d{2}|OM-\d{2}\.\d{2}|[A-Z]+-[0-9A-Z.]+)\s*-->")
EPIC_ID_RE = re.compile(r"^E(\d{2})$")
STORY_ID_RE = re.compile(r"^OM-(\d{2})\.(\d{2})$")
TASK_LINE_RE = re.compile(r"^\s*- \[(?P<box>[ xX])\]\s+\*\*(?P<id>OM-\d{2}\.\d{2}-T\d+)\*\*\s*(?P<text>.*)$")
DEPENDS_RE = re.compile(r"^\*\*Depends on:\*\*\s*(?P<value>.+?)\s*$", re.M)
EPIC_PREREQ_RE = re.compile(r"^\*\*Epic prerequisites:\*\*\s*(?P<value>.+?)\s*$", re.M)
REF_RE = re.compile(r"\b(E\d{2}|OM-\d{2}\.\d{2})\b")
# Strict declaration grammar: "None" or a comma-separated list of stable ids, optional final period.
DECLARATION_RE = re.compile(r"^(?:None|(?:E\d{2}|OM-\d{2}\.\d{2})(?:,\s*(?:E\d{2}|OM-\d{2}\.\d{2}))*)\.?$")
TASKS_INDEX_RE = re.compile(r"\*\*(OM-\d{2}\.\d{2}-T\d+)\*\*")
EXPECTED = {"epics": 19, "stories": 85, "tasks": 340}
OPTIONAL_EPICS = ("E17",)
LATER_EPICS = ("E19",)


@dataclass(frozen=True)
class Task:
    task_id: str
    checked: bool
    text: str


@dataclass(frozen=True)
class Entry:
    stable_id: str
    kind: str  # epic | story | other
    number: int
    node_id: str
    title: str
    state: str
    state_reason: str | None
    updated_at: str
    closed_at: str | None
    labels: tuple[str, ...]
    parent_number: int | None
    depends_on: tuple[str, ...]
    epic_prerequisites: tuple[str, ...]
    depends_on_known: bool
    epic_prerequisites_known: bool
    tasks: tuple[Task, ...]
    item_id: str | None
    status: str | None
    item_stable_id: str | None
    item_updated_at: str | None
    body_sha256: str

    @property
    def epic_id(self) -> str | None:
        m = STORY_ID_RE.match(self.stable_id)
        if m:
            return f"E{m.group(1)}"
        return self.stable_id if EPIC_ID_RE.match(self.stable_id) else None

    @property
    def bmad_key(self) -> str | None:
        """Derived ``N-M-slug`` key in bmad-loop's grammar, for traceability only."""
        m = STORY_ID_RE.match(self.stable_id)
        if not m:
            return None
        slug = re.sub(r"[^a-z0-9]+", "-", self.title.split("—", 1)[-1].strip().lower()).strip("-")
        return f"{int(m.group(1))}-{int(m.group(2))}-{slug}"


@dataclass
class Snapshot:
    taken_at: str
    repo: str
    entries: list[Entry] = field(default_factory=list)

    def duplicate_ids(self) -> list[str]:
        """Stable ids carried by more than one issue. ``by_id`` keeps only one of them, so
        every admission path must refuse while this is non-empty (ambiguous identity)."""
        seen: dict[str, int] = {}
        for e in self.entries:
            seen[e.stable_id] = seen.get(e.stable_id, 0) + 1
        return sorted(i for i, n in seen.items() if n > 1)

    def by_id(self) -> dict[str, Entry]:
        """Dictionary reduction; callers that admit work check :meth:`duplicate_ids` first."""
        return {e.stable_id: e for e in self.entries}

    def by_number(self) -> dict[int, Entry]:
        return {e.number: e for e in self.entries}

    def to_json(self) -> str:
        return json.dumps({"taken_at": self.taken_at, "repo": self.repo, "entries": [asdict(e) for e in self.entries]}, indent=1, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> "Snapshot":
        raw = json.loads(text)
        entries = []
        for e in raw["entries"]:
            e = dict(e)
            e["tasks"] = tuple(Task(**t) for t in e["tasks"])
            for key in ("labels", "depends_on", "epic_prerequisites"):
                e[key] = tuple(e[key])
            entries.append(Entry(**e))
        return cls(raw["taken_at"], raw["repo"], entries)


def parse_declaration(value: str | None) -> tuple[tuple[str, ...], bool]:
    """``(refs, known)``. ``known`` is true only when the declaration is present and matches
    the strict grammar exactly; a missing, malformed or partially understood line yields
    ``known=False`` so eligibility fails closed instead of reading it as "no dependencies"."""
    if value is None:
        return (), False
    text = value.strip()
    if not DECLARATION_RE.match(text):
        return (), False
    return tuple(dict.fromkeys(REF_RE.findall(text))), True


def normalize(issue: IssueRecord, item: ProjectItem | None, body_sha256: str) -> Entry:
    marker = ID_MARKER_RE.search(issue.body)
    stable_id = marker.group("id") if marker else f"#{issue.number}"
    kind = "epic" if EPIC_ID_RE.match(stable_id) else "story" if STORY_ID_RE.match(stable_id) else "other"
    depends = DEPENDS_RE.findall(issue.body)
    prereq = EPIC_PREREQ_RE.findall(issue.body)
    # exactly one declaration line is understood; zero or several are unknown
    depends_on, depends_known = parse_declaration(depends[0] if len(depends) == 1 else None)
    prereqs, prereqs_known = parse_declaration(prereq[0] if len(prereq) == 1 else None)
    if kind == "story":
        prereqs, prereqs_known = (), True  # stories inherit their epic's prerequisites
    elif kind == "epic":
        depends_on, depends_known = (), True  # epics declare prerequisites, not dependencies
    else:
        depends_on, depends_known, prereqs, prereqs_known = (), True, (), True
    tasks = tuple(Task(m.group("id"), m.group("box") != " ", m.group("text").strip()) for m in (TASK_LINE_RE.match(line) for line in issue.body.splitlines()) if m)
    return Entry(
        stable_id=stable_id, kind=kind, number=issue.number, node_id=issue.node_id, title=issue.title, state=issue.state,
        state_reason=issue.state_reason, updated_at=issue.updated_at, closed_at=issue.closed_at, labels=issue.labels,
        parent_number=issue.parent_number, depends_on=depends_on, epic_prerequisites=prereqs,
        depends_on_known=depends_known, epic_prerequisites_known=prereqs_known, tasks=tasks,
        item_id=item.item_id if item else None, status=item.status if item else None,
        item_stable_id=item.stable_id if item else None, item_updated_at=item.updated_at if item else None,
        body_sha256=body_sha256,
    )


def project_items_for(items: list[ProjectItem], repo: str) -> dict[int, ProjectItem]:
    """The Project items that belong to ``repo``, keyed by issue number. Items of other
    repositories (a user Project can hold several) and items whose repository is unknown are
    dropped: another repository's Status must never attach to this backlog's story. Two items
    for one issue of this repository are ambiguous and refuse."""
    out: dict[int, ProjectItem] = {}
    for item in items:
        if item.issue_number is None or item.repository != repo:
            continue
        if item.issue_number in out:
            raise Refused(f"Project holds more than one item for {repo}#{item.issue_number} ({out[item.issue_number].item_id}, {item.item_id}); the Status is ambiguous, nothing is admitted", code="ambiguous-project-item", issue=item.issue_number)
        out[item.issue_number] = item
    return out


def take_snapshot(transport: Transport, repo: str, now: str) -> Snapshot:
    import hashlib

    issues = transport.list_issues()
    items = project_items_for(transport.list_project_items(), repo)
    entries = [normalize(i, items.get(i.number), hashlib.sha256(i.body.encode("utf-8")).hexdigest()) for i in issues]
    return Snapshot(now, repo, entries)


def verify_mapping(snapshot: Snapshot, tasks_index_text: str | None = None) -> dict:
    """Check the tracking contract; return a JSON-able report with ``ok`` and ``problems``."""
    problems: list[str] = []
    by_id = snapshot.by_id()
    by_number = snapshot.by_number()
    epics = [e for e in snapshot.entries if e.kind == "epic"]
    stories = [e for e in snapshot.entries if e.kind == "story"]
    others = [e for e in snapshot.entries if e.kind == "other"]
    tasks = [t for s in stories for t in s.tasks]

    counts = {"epics": len(epics), "stories": len(stories), "tasks": len(tasks), "other_issues": len(others), "project_items": sum(1 for e in snapshot.entries if e.item_id)}
    for key, expected in EXPECTED.items():
        if counts[key] != expected:
            problems.append(f"{key}: expected {expected}, found {counts[key]}")

    dupes = snapshot.duplicate_ids()
    if dupes:
        problems.append(f"duplicate stable ids: {dupes}")
    for epic in epics:
        if "epic" not in epic.labels:
            problems.append(f"{epic.stable_id} (#{epic.number}) lacks the epic label")
        if epic.parent_number is not None:
            problems.append(f"{epic.stable_id} has a parent issue; epics must be roots")
    for story in stories:
        if "story" not in story.labels:
            problems.append(f"{story.stable_id} (#{story.number}) lacks the story label")
        parent = by_number.get(story.parent_number) if story.parent_number else None
        if parent is None:
            problems.append(f"{story.stable_id} (#{story.number}) has no native parent issue")
        elif parent.stable_id != story.epic_id:
            problems.append(f"{story.stable_id} parent is {parent.stable_id}, expected {story.epic_id}")
        for index, task in enumerate(story.tasks, start=1):
            if task.task_id != f"{story.stable_id}-T{index}":
                problems.append(f"{story.stable_id}: task {index} is {task.task_id}")
        if not story.depends_on_known:
            problems.append(f"{story.stable_id} has no single well-formed 'Depends on' declaration")
        for dep in story.depends_on:
            if dep not in by_id:
                problems.append(f"{story.stable_id} depends on unknown {dep}")
    for epic in epics:
        if not epic.epic_prerequisites_known:
            problems.append(f"{epic.stable_id} has no single well-formed 'Epic prerequisites' declaration")
        for dep in epic.epic_prerequisites:
            if dep not in by_id:
                problems.append(f"{epic.stable_id} prerequisite {dep} unknown")
    for entry in epics + stories:
        if entry.item_id is None:
            problems.append(f"{entry.stable_id} (#{entry.number}) has no Project item")
        elif entry.item_stable_id != entry.stable_id:
            problems.append(f"{entry.stable_id} Project Stable ID is {entry.item_stable_id!r}")
        if entry.status is None and entry.item_id is not None:
            problems.append(f"{entry.stable_id} Project Status is empty")
    for entry in others:
        if "engineering-automation" not in entry.labels:
            problems.append(f"issue #{entry.number} ({entry.title!r}) is neither backlog nor engineering-automation")

    if tasks_index_text is not None:
        indexed = set(TASKS_INDEX_RE.findall(tasks_index_text))
        github_ids = {t.task_id for t in tasks}
        if indexed != github_ids:
            problems.append(f"task ids differ from TASKS.md: missing on GitHub {sorted(indexed - github_ids)[:5]}, extra on GitHub {sorted(github_ids - indexed)[:5]}")
        counts["tasks_index"] = len(indexed)

    return {
        "ok": not problems, "taken_at": snapshot.taken_at, "repo": snapshot.repo, "counts": counts, "problems": problems,
        "checked_tasks": sum(1 for t in tasks if t.checked),
        "status_counts": _count(e.status for e in epics + stories),
        "mapping": [{"stable_id": e.stable_id, "issue": e.number, "item": e.item_id, "status": e.status, "state": e.state, "parent": e.parent_number, "depends_on": list(e.depends_on), "declaration_known": e.depends_on_known and e.epic_prerequisites_known, "bmad_key": e.bmad_key, "tasks": len(e.tasks)} for e in epics + stories],
    }


def _count(values) -> dict[str, int]:
    out: dict[str, int] = {}
    for v in values:
        out[str(v)] = out.get(str(v), 0) + 1
    return dict(sorted(out.items()))


def load_tasks_index(root: Path) -> str | None:
    path = root / "_bmad-output/planning-artifacts/epics/owl-mast-2026-11-05/TASKS.md"
    return path.read_text(encoding="utf-8") if path.exists() else None
