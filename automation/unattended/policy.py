"""Policy file: what may be dispatched, with which T3 targets, budgets, checks and probes.

The policy is TOML (stdlib ``tomllib``). Loading is strict: unknown sections, secret-like
keys and unsafe values fail with :class:`PolicyError`. Flags in this file are *policy*;
whether they are *enforced* depends on the credential the operator provisions (see
``docs/unattended-execution.md``).
"""

from __future__ import annotations

import hashlib
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .errors import PolicyError

SECRET_KEY_RE = re.compile(r"(token|secret|password|passwd|api[_-]?key|credential|bearer)", re.I)
SECRET_VALUE_RE = re.compile(r"^(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{20,})$")
STORY_ID_RE = re.compile(r"^OM-(\d{2})\.(\d{2})$")
KNOWN_SECTIONS = {"repository", "dispatch", "budgets", "targets", "checks", "probes", "writes"}
MACHINE_STATUSES = ("In progress", "In review", "Blocked")
OWNER_STATUSES = ("Ready", "Done")
MAX_REPAIR_ROUNDS_CEILING = 2


@dataclass(frozen=True)
class Target:
    provider: str
    model: str
    options: dict[str, str]
    isolation: str = ""


@dataclass(frozen=True)
class Policy:
    owner: str
    repo: str
    project_owner: str
    project_number: int
    allow: tuple[str, ...]
    include_optional_epics: bool
    include_later_epics: bool
    contract_design_exceptions: tuple[str, ...]
    max_stories_per_run: int
    max_concurrent_implementers: int
    max_repair_rounds: int
    max_delegated_tasks: int
    max_wall_clock_minutes: int
    implementer: Target
    reviewer: Target
    check_commands: tuple[str, ...]
    check_timeout_minutes: int
    probe_commands: tuple[str, ...]
    probe_timeout_seconds: int
    digest: str = field(default="", compare=False)

    @property
    def repo_slug(self) -> str:
        return f"{self.owner}/{self.repo}"


def _walk(obj, path: str, problems: list[str]) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            here = f"{path}.{key}" if path else key
            if SECRET_KEY_RE.search(str(key)):
                problems.append(f"secret-like key {here!r} is not allowed in policy")
            _walk(value, here, problems)
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            _walk(value, f"{path}[{index}]", problems)
    elif isinstance(obj, str) and SECRET_VALUE_RE.match(obj):
        problems.append(f"value at {path!r} looks like a credential")


def _target(raw: dict, name: str, problems: list[str]) -> Target | None:
    if not isinstance(raw, dict):
        problems.append(f"targets.{name} must be a table")
        return None
    provider = raw.get("provider")
    model = raw.get("model")
    options = raw.get("options", {})
    if not provider or not model:
        problems.append(f"targets.{name} needs provider and model")
    if not isinstance(options, dict) or not options:
        problems.append(f"targets.{name}.options must name at least one option (e.g. effort)")
        options = {}
    elif not all(isinstance(k, str) and isinstance(v, str) and v.strip() for k, v in options.items()):
        # the same rule as the activation loader: no coercion of numbers, booleans or tables, so the
        # two documents compare option values under one typing rule
        problems.append(f"targets.{name}.options must be a table of non-empty string values (write timeoutMs = \"600000\", not 600000)")
        options = {k: v for k, v in options.items() if isinstance(k, str) and isinstance(v, str)}
    return Target(str(provider), str(model), dict(options), str(raw.get("isolation", "")))


def load_policy(path: Path) -> Policy:
    try:
        text = path.read_bytes()
        raw = tomllib.loads(text.decode("utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise PolicyError(f"cannot read policy {path}: {exc}") from exc
    problems: list[str] = []
    unknown = set(raw) - KNOWN_SECTIONS
    if unknown:
        problems.append(f"unknown sections: {sorted(unknown)}")
    _walk(raw, "", problems)

    repository = raw.get("repository", {})
    dispatch = raw.get("dispatch", {})
    budgets = raw.get("budgets", {})
    targets = raw.get("targets", {})
    checks = raw.get("checks", {})
    probes = raw.get("probes", {})
    writes = raw.get("writes", {})

    for key in ("owner", "name", "project_owner", "project_number"):
        if key not in repository:
            problems.append(f"repository.{key} is required")

    allow = tuple(str(s) for s in dispatch.get("allow", []))
    for story in allow:
        if not STORY_ID_RE.match(story):
            problems.append(f"dispatch.allow entry {story!r} is not an OM-xx.yy story id")
    exceptions = tuple(str(s) for s in dispatch.get("contract_design_exceptions", []))
    for story in exceptions:
        if not STORY_ID_RE.match(story):
            problems.append(f"dispatch.contract_design_exceptions entry {story!r} is not an OM-xx.yy story id")

    max_repair = int(budgets.get("max_repair_rounds", MAX_REPAIR_ROUNDS_CEILING))
    if max_repair > MAX_REPAIR_ROUNDS_CEILING or max_repair < 0:
        problems.append(f"budgets.max_repair_rounds must be 0..{MAX_REPAIR_ROUNDS_CEILING}")
    concurrent = int(budgets.get("max_concurrent_implementers", 1))
    if concurrent != 1:
        problems.append("budgets.max_concurrent_implementers must be 1 (one active implementer per story and per run)")
    for key in ("max_stories_per_run", "max_delegated_tasks", "max_wall_clock_minutes"):
        if int(budgets.get(key, 1)) < 1:
            problems.append(f"budgets.{key} must be >= 1")

    implementer = _target(targets.get("implementer"), "implementer", problems)
    reviewer = _target(targets.get("reviewer"), "reviewer", problems)
    if implementer and implementer.isolation != "worktree":
        problems.append("targets.implementer.isolation must be 'worktree'")

    if writes.get("apply_task_checkboxes", False):
        problems.append("writes.apply_task_checkboxes must stay false: task completion is proposed, never applied by the machine")
    if writes.get("merge", "owner") != "owner":
        problems.append("writes.merge must be 'owner': the tool has no merge path")
    for key in ("auto_deploy", "auto_release", "live_collection"):
        if writes.get(key, False):
            problems.append(f"writes.{key} must be false")

    check_commands = tuple(str(c) for c in checks.get("commands", []))
    probe_commands = tuple(str(c) for c in probes.get("commands", []))
    if not check_commands:
        problems.append("checks.commands must not be empty (deterministic checks run before review)")
    if not probe_commands:
        problems.append("probes.commands must not be empty (environment probes run before dispatch)")

    if problems:
        raise PolicyError("policy rejected: " + "; ".join(problems), problems=problems)
    assert implementer and reviewer
    return Policy(
        owner=str(repository["owner"]),
        repo=str(repository["name"]),
        project_owner=str(repository["project_owner"]),
        project_number=int(repository["project_number"]),
        allow=allow,
        include_optional_epics=bool(dispatch.get("include_optional_epics", False)),
        include_later_epics=bool(dispatch.get("include_later_epics", False)),
        contract_design_exceptions=exceptions,
        max_stories_per_run=int(budgets.get("max_stories_per_run", 1)),
        max_concurrent_implementers=concurrent,
        max_repair_rounds=max_repair,
        max_delegated_tasks=int(budgets.get("max_delegated_tasks", 6)),
        max_wall_clock_minutes=int(budgets.get("max_wall_clock_minutes", 240)),
        implementer=implementer,
        reviewer=reviewer,
        check_commands=check_commands,
        check_timeout_minutes=int(checks.get("timeout_minutes", 45)),
        probe_commands=probe_commands,
        probe_timeout_seconds=int(probes.get("timeout_seconds", 60)),
        digest=hashlib.sha256(text).hexdigest(),
    )
