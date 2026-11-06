"""Fail-closed dispatch eligibility.

A story is dispatchable only when every rule answers yes. Any unknown fact (missing Project
item, unknown dependency, inconsistent issue state) is a refusal, never a guess.
"""

from __future__ import annotations

from dataclasses import dataclass

from .backlog import LATER_EPICS, OPTIONAL_EPICS, Entry, Snapshot
from .policy import Policy

DISPATCHABLE = "dispatchable"
DISPATCHABLE_CONTRACT_DESIGN = "dispatchable-contract-design-only"


@dataclass(frozen=True)
class Decision:
    story: str
    outcome: str
    reasons: tuple[str, ...]
    entry_number: int | None = None

    @property
    def dispatchable(self) -> bool:
        return self.outcome in (DISPATCHABLE, DISPATCHABLE_CONTRACT_DESIGN)

    def as_dict(self) -> dict:
        return {"story": self.story, "outcome": self.outcome, "reasons": list(self.reasons), "issue": self.entry_number, "dispatchable": self.dispatchable}


def dependency_state(dep: Entry | None, dep_id: str) -> tuple[bool, str]:
    """A dependency is satisfied only when its Project Status is Done and the issue is
    closed as completed. Anything else, including a Done-but-open (reopened) issue, is not."""
    if dep is None:
        return False, f"{dep_id}: unknown (not in snapshot)"
    if dep.status == "Done" and dep.state == "CLOSED" and (dep.state_reason or "COMPLETED") == "COMPLETED":
        return True, f"{dep_id}: Done and closed"
    if dep.status == "Done" and dep.state == "OPEN":
        return False, f"{dep_id}: Done but reopened (OPEN) — inconsistent, fail closed"
    if dep.state == "CLOSED" and dep.status != "Done":
        return False, f"{dep_id}: closed but Status {dep.status!r} (closed as not planned is not Done)"
    return False, f"{dep_id}: Status {dep.status!r}, state {dep.state}"


def decide(story_id: str, snapshot: Snapshot, policy: Policy) -> Decision:
    by_id = snapshot.by_id()
    entry = by_id.get(story_id)
    if story_id not in policy.allow:
        return Decision(story_id, "not-allowlisted", ("story is not in dispatch.allow",), entry.number if entry else None)
    if entry is None or entry.kind != "story":
        return Decision(story_id, "unknown-story", ("story id not found in the GitHub snapshot",))
    epic_id = entry.epic_id or ""
    if epic_id in OPTIONAL_EPICS and not policy.include_optional_epics:
        return Decision(story_id, "excluded-epic", (f"{epic_id} is optional; include_optional_epics is false",), entry.number)
    if epic_id in LATER_EPICS and not policy.include_later_epics:
        return Decision(story_id, "excluded-epic", (f"{epic_id} is later evolution; include_later_epics is false",), entry.number)
    if entry.item_id is None or entry.status is None:
        return Decision(story_id, "unknown-eligibility", ("no Project item or empty Status",), entry.number)
    if entry.item_stable_id != entry.stable_id:
        return Decision(story_id, "unknown-eligibility", (f"Project Stable ID {entry.item_stable_id!r} differs from issue id",), entry.number)
    if not entry.depends_on_known:
        return Decision(story_id, "unknown-eligibility", ("'Depends on' declaration missing, duplicated or not understood; fail closed",), entry.number)
    if entry.state == "CLOSED":
        return Decision(story_id, "closed", (f"issue closed ({entry.state_reason}); Status {entry.status}",), entry.number)
    if entry.status == "Done":
        return Decision(story_id, "reopened-inconsistent", ("Status Done but issue OPEN; owner must restore a justified status",), entry.number)
    if entry.status in ("In progress", "In review"):
        return Decision(story_id, "already-active", (f"Status {entry.status}: claimed or awaiting review/acceptance",), entry.number)
    if entry.status == "Blocked":
        return Decision(story_id, "blocked", ("Status Blocked; owner decision or evidence missing",), entry.number)
    if entry.status != "Ready":
        return Decision(story_id, "awaiting-owner-acceptance", (f"Status {entry.status!r}; Ready requires owner acceptance",), entry.number)

    unmet: list[str] = []
    met: list[str] = []

    def epic_complete(epic_id: str) -> tuple[bool, str]:
        if epic_id not in by_id:
            return False, f"{epic_id}: unknown epic prerequisite"
        epic = by_id[epic_id]
        if not epic.epic_prerequisites_known:
            return False, f"{epic_id}: its own prerequisites declaration is not understood; fail closed"
        children = [e for e in snapshot.entries if e.kind == "story" and e.epic_id == epic_id]
        if any(not c.depends_on_known for c in children):
            return False, f"{epic_id}: a story of this epic has an unreadable dependency declaration; fail closed"
        incomplete = [c.stable_id for c in children if not dependency_state(c, c.stable_id)[0]]
        if not children or incomplete:
            return False, f"{epic_id}: epic prerequisite incomplete ({', '.join(incomplete[:4]) or 'no stories'})"
        return True, f"{epic_id}: all stories Done and closed"

    for dep_id in entry.depends_on:
        dep = by_id.get(dep_id)
        ok, text = epic_complete(dep_id) if dep is not None and dep.kind == "epic" else dependency_state(dep, dep_id)
        (met if ok else unmet).append(text)
    parent = snapshot.by_number().get(entry.parent_number) if entry.parent_number else None
    if parent is None:
        return Decision(story_id, "unknown-eligibility", ("story has no native parent epic",), entry.number)
    if parent.kind != "epic" or parent.stable_id != entry.epic_id:
        return Decision(story_id, "unknown-eligibility", (f"parent #{parent.number} is {parent.stable_id}, not {entry.epic_id}",), entry.number)
    if not parent.epic_prerequisites_known:
        return Decision(story_id, "unknown-eligibility", (f"{parent.stable_id} 'Epic prerequisites' declaration missing or not understood; fail closed",), entry.number)
    for prereq in parent.epic_prerequisites:
        ok, text = epic_complete(prereq)
        (met if ok else unmet).append(text)
    if unmet:
        if story_id in policy.contract_design_exceptions:
            return Decision(story_id, DISPATCHABLE_CONTRACT_DESIGN, tuple(["designated contract-design portion only; synthetic fixtures; production implementation and completion keep prerequisites"] + unmet), entry.number)
        return Decision(story_id, "blocked-by-dependency", tuple(unmet), entry.number)
    return Decision(story_id, DISPATCHABLE, tuple(met) or ("no prerequisites",), entry.number)


def plan(snapshot: Snapshot, policy: Policy) -> list[Decision]:
    return [decide(story, snapshot, policy) for story in policy.allow]
