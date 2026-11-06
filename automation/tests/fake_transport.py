"""In-memory GitHub transport with fault injection for the qualification suite.

Faults: ``fail_once[op] = exception`` raises on the next call of ``op`` and then clears;
``fail_always[op]`` raises on every call; ``crash_after_post`` raises after a comment has
been appended (partial write). ``set_status_externally`` and direct edits of ``issues``
simulate owner edits. ``live`` marks the transport as a production boundary for the gate test.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

from automation.unattended.github import Comment, IssueRecord, ProjectInfo, ProjectItem, PullRequestRecord

STATUS_OPTIONS = {"Backlog": "f75ad846", "Ready": "0ed1e913", "In progress": "47fc9ee4", "In review": "6807a163", "Blocked": "8f1d7041", "Done": "98236657"}


class CrashAfterEffect(RuntimeError):
    """Simulates the process dying after the GitHub effect landed."""


@dataclass
class FakeTransport:
    live: bool = False
    issues: dict[int, IssueRecord] = field(default_factory=dict)
    items: dict[str, ProjectItem] = field(default_factory=dict)
    comments: dict[int, list[Comment]] = field(default_factory=dict)
    pull_requests: dict[int, PullRequestRecord] = field(default_factory=dict)
    fail_once: dict[str, Exception] = field(default_factory=dict)
    fail_always: dict[str, Exception] = field(default_factory=dict)
    crash_after_post: bool = False
    calls: list[str] = field(default_factory=list)
    _ids: itertools.count = field(default_factory=lambda: itertools.count(1000))
    _ticks: itertools.count = field(default_factory=lambda: itertools.count(1))

    def _tick(self) -> str:
        return f"2026-11-06T13:00:{next(self._ticks):02d}Z"

    def _fault(self, op: str) -> None:
        self.calls.append(op)
        if op in self.fail_always:
            raise self.fail_always[op]
        if op in self.fail_once:
            raise self.fail_once.pop(op)

    # -- builder helpers ----------------------------------------------------------------
    def add_issue(self, issue: IssueRecord, status: str | None, stable_id: str | None = None) -> None:
        self.issues[issue.number] = issue
        self.comments.setdefault(issue.number, [])
        if status is not None:
            item_id = f"PVTI_{issue.number}"
            self.items[item_id] = ProjectItem(item_id, issue.number, status, stable_id, self._tick())

    def item_for(self, number: int) -> ProjectItem:
        return next(i for i in self.items.values() if i.issue_number == number)

    def set_status_externally(self, number: int, status: str) -> None:
        item = self.item_for(number)
        self.items[item.item_id] = ProjectItem(item.item_id, number, status, item.stable_id, self._tick())

    # -- Transport ------------------------------------------------------------------------
    def list_issues(self) -> list[IssueRecord]:
        self._fault("list_issues")
        return [self.issues[n] for n in sorted(self.issues)]

    def get_issue(self, number: int) -> IssueRecord:
        self._fault("get_issue")
        return self.issues[number]

    def list_comments(self, number: int) -> list[Comment]:
        self._fault("list_comments")
        return list(self.comments.get(number, []))

    def post_comment(self, number: int, body: str) -> Comment:
        self._fault("post_comment")
        comment = Comment(next(self._ids), body, "machine", self._tick())
        self.comments.setdefault(number, []).append(comment)
        if self.crash_after_post:
            self.crash_after_post = False
            raise CrashAfterEffect("process died after posting")
        return comment

    def project_info(self) -> ProjectInfo:
        self._fault("project_info")
        return ProjectInfo("PVT_fake", "PVTSSF_status", dict(STATUS_OPTIONS))

    def list_project_items(self) -> list[ProjectItem]:
        self._fault("list_project_items")
        return list(self.items.values())

    def get_project_item(self, item_id: str) -> ProjectItem:
        self._fault("get_project_item")
        return self.items[item_id]

    def get_pull_request(self, number: int) -> PullRequestRecord:
        self._fault("get_pull_request")
        return self.pull_requests[number]


def issue(number: int, stable_id: str, title: str, *, state: str = "OPEN", state_reason: str | None = None, labels=(), parent: int | None = None,
          depends_on: str = "None", epic_prereq: str | None = None, tasks: int = 0, checked: int = 0) -> IssueRecord:
    lines = [f"<!-- owl-mast-id: {stable_id} -->", "", f"### {stable_id} — {title}", ""]
    if epic_prereq is not None:
        lines.append(f"**Epic prerequisites:** {epic_prereq}")
    if tasks:
        lines += [f"**Depends on:** {depends_on}", "", "**Tasks:**", ""]
        for n in range(1, tasks + 1):
            box = "x" if n <= checked else " "
            lines.append(f"- [{box}] **{stable_id}-T{n}** Task {n} text.")
    return IssueRecord(number, f"I_{number}", f"{stable_id} — {title}", state, state_reason, "2026-11-06T10:00:00Z",
                       "2026-11-06T11:00:00Z" if state == "CLOSED" else None, "\n".join(lines) + "\n", tuple(labels), parent)


def small_backlog() -> FakeTransport:
    """E01 with four stories (OM-01.01 Done+closed), E17 and E19 with one story each, ENG issue."""
    fake = FakeTransport()
    fake.add_issue(issue(1, "E01", "Foundation", labels=("epic",), epic_prereq="None"), "Backlog", "E01")
    fake.add_issue(issue(2, "E02", "Access", labels=("epic",), epic_prereq="E01"), "Backlog", "E02")
    fake.add_issue(issue(17, "E17", "Optional", labels=("epic",), epic_prereq="None"), "Backlog", "E17")
    fake.add_issue(issue(19, "E19", "Later", labels=("epic",), epic_prereq="None"), "Backlog", "E19")
    fake.add_issue(issue(20, "OM-01.01", "Bootstrap", state="CLOSED", state_reason="COMPLETED", labels=("story",), parent=1, tasks=4, checked=4), "Done", "OM-01.01")
    fake.add_issue(issue(21, "OM-01.02", "Install", labels=("story",), parent=1, depends_on="OM-01.01", tasks=4), "Ready", "OM-01.02")
    fake.add_issue(issue(22, "OM-01.03", "Recover", labels=("story",), parent=1, depends_on="OM-01.01", tasks=4), "Backlog", "OM-01.03")
    fake.add_issue(issue(23, "OM-01.04", "Shell", labels=("story",), parent=1, depends_on="OM-01.01", tasks=4), "Ready", "OM-01.04")
    fake.add_issue(issue(24, "OM-02.01", "Auth", labels=("story",), parent=2, depends_on="OM-01.02, OM-01.04", tasks=3), "Ready", "OM-02.01")
    fake.add_issue(issue(90, "OM-17.01", "T3 context", labels=("story",), parent=17, depends_on="None", tasks=2), "Ready", "OM-17.01")
    fake.add_issue(issue(101, "OM-19.01", "Multi tenant", labels=("story",), parent=19, depends_on="None", tasks=2), "Ready", "OM-19.01")
    fake.add_issue(IssueRecord(106, "I_106", "ENG-01 — automation", "OPEN", None, "2026-11-06T10:00:00Z", None, "<!-- owl-mast-id: ENG-01 -->\n", ("engineering-automation",), None), "In progress", "ENG-01")
    return fake
