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


SECTION_KEYS = {
    "repository": {"owner", "name", "project_owner", "project_number"},
    "dispatch": {"allow", "include_optional_epics", "include_later_epics", "contract_design_exceptions"},
    "budgets": {"max_stories_per_run", "max_concurrent_implementers", "max_repair_rounds", "max_delegated_tasks", "max_wall_clock_minutes"},
    "targets": {"implementer", "reviewer"},
    "checks": {"commands", "timeout_minutes"},
    "probes": {"commands", "timeout_seconds"},
    "writes": {"apply_task_checkboxes", "merge", "auto_deploy", "auto_release", "live_collection"},
}


def _table(raw: dict, name: str, problems: list[str]) -> dict:
    """A section as a table with known keys only; anything else is a problem (a mistyped budget
    key must never fall back to a default) and reads as empty."""
    value = raw.get(name, {})
    if not isinstance(value, dict):
        problems.append(f"{name} must be a table, not {type(value).__name__}")
        return {}
    unknown = set(value) - SECTION_KEYS[name]
    if unknown:
        problems.append(f"{name} has unknown keys {sorted(unknown)}; known keys are {sorted(SECTION_KEYS[name])}")
    return value


def _bool(section: dict, path: str, key: str, default: bool, problems: list[str]) -> bool:
    """A TOML boolean exactly; ``"false"`` (a string) or ``0`` are refused, never coerced."""
    value = section.get(key, default)
    if not isinstance(value, bool):
        problems.append(f"{path}.{key} must be a boolean (true/false), not {type(value).__name__} {value!r}")
        return default
    return value


def _int(section: dict, path: str, key: str, default: int, problems: list[str], lo: int | None = None, hi: int | None = None) -> int:
    """A TOML integer exactly (``type(v) is int``: no booleans, floats or strings) within ``lo..hi``."""
    value = section.get(key, default)
    if type(value) is not int:
        problems.append(f"{path}.{key} must be an integer, not {type(value).__name__} {value!r}")
        return default
    if (lo is not None and value < lo) or (hi is not None and value > hi):
        bounds = f"{lo if lo is not None else ''}..{hi if hi is not None else ''}"
        problems.append(f"{path}.{key} must be within {bounds}, not {value}")
    return value


def _strings(section: dict, path: str, key: str, problems: list[str]) -> tuple[str, ...]:
    """An array of non-empty strings; a scalar (which would iterate character by character) or
    a non-string entry is refused."""
    value = section.get(key, [])
    if not isinstance(value, list):
        problems.append(f"{path}.{key} must be an array, not {type(value).__name__}")
        return ()
    bad = [v for v in value if not isinstance(v, str) or not v.strip()]
    if bad:
        problems.append(f"{path}.{key} entries must be non-empty strings; found {bad[:3]!r}")
        return tuple(v for v in value if isinstance(v, str) and v.strip())
    return tuple(value)


def _target(raw, name: str, problems: list[str]) -> Target | None:
    if not isinstance(raw, dict):
        problems.append(f"targets.{name} must be a table")
        return None
    provider = raw.get("provider")
    model = raw.get("model")
    options = raw.get("options", {})
    for key, value in (("provider", provider), ("model", model)):
        if not isinstance(value, str) or not value.strip():
            problems.append(f"targets.{name}.{key} must be a non-empty string")
    if not isinstance(options, dict) or not options:
        problems.append(f"targets.{name}.options must name at least one option (e.g. effort)")
        options = {}
    elif not all(isinstance(k, str) and isinstance(v, str) and v.strip() for k, v in options.items()):
        problems.append(f"targets.{name}.options values must be strings (no coercion of numbers, booleans or tables)")
        options = {k: v for k, v in options.items() if isinstance(k, str) and isinstance(v, str)}
    isolation = raw.get("isolation", "")
    if not isinstance(isolation, str):
        problems.append(f"targets.{name}.isolation must be a string")
        isolation = ""
    if isolation != "worktree":
        problems.append(f"targets.{name}.isolation must be 'worktree' (every delegated task, reviewer included, runs in its own checkout)")
    return Target(str(provider), str(model), {str(k): str(v) for k, v in options.items()}, isolation)


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

    repository = _table(raw, "repository", problems)
    dispatch = _table(raw, "dispatch", problems)
    budgets = _table(raw, "budgets", problems)
    targets = _table(raw, "targets", problems)
    checks = _table(raw, "checks", problems)
    probes = _table(raw, "probes", problems)
    writes = _table(raw, "writes", problems)

    for key in ("owner", "name", "project_owner"):
        if not isinstance(repository.get(key), str) or not repository[key].strip():
            problems.append(f"repository.{key} is required and must be a non-empty string")
    if "project_number" not in repository:
        problems.append("repository.project_number is required")
        project_number = 0
    else:
        project_number = _int(repository, "repository", "project_number", 0, problems, lo=1)

    allow = _strings(dispatch, "dispatch", "allow", problems)
    for story in allow:
        if not STORY_ID_RE.match(story):
            problems.append(f"dispatch.allow entry {story!r} is not an OM-xx.yy story id")
    if len(set(allow)) != len(allow):
        problems.append("dispatch.allow lists a story more than once")
    exceptions = _strings(dispatch, "dispatch", "contract_design_exceptions", problems)
    for story in exceptions:
        if not STORY_ID_RE.match(story):
            problems.append(f"dispatch.contract_design_exceptions entry {story!r} is not an OM-xx.yy story id")
    include_optional = _bool(dispatch, "dispatch", "include_optional_epics", False, problems)
    include_later = _bool(dispatch, "dispatch", "include_later_epics", False, problems)

    max_repair = _int(budgets, "budgets", "max_repair_rounds", MAX_REPAIR_ROUNDS_CEILING, problems, lo=0, hi=MAX_REPAIR_ROUNDS_CEILING)
    concurrent = _int(budgets, "budgets", "max_concurrent_implementers", 1, problems, lo=1, hi=1)
    max_stories = _int(budgets, "budgets", "max_stories_per_run", 1, problems, lo=1)
    max_tasks = _int(budgets, "budgets", "max_delegated_tasks", 6, problems, lo=1)
    max_wall = _int(budgets, "budgets", "max_wall_clock_minutes", 240, problems, lo=1)

    implementer = _target(targets.get("implementer"), "implementer", problems)
    reviewer = _target(targets.get("reviewer"), "reviewer", problems)

    if _bool(writes, "writes", "apply_task_checkboxes", False, problems):
        problems.append("writes.apply_task_checkboxes must stay false: task completion is proposed, never applied by the machine")
    if writes.get("merge", "owner") != "owner":
        problems.append("writes.merge must be 'owner': the tool has no merge path")
    for key in ("auto_deploy", "auto_release", "live_collection"):
        if _bool(writes, "writes", key, False, problems):
            problems.append(f"writes.{key} must be false")

    check_commands = _strings(checks, "checks", "commands", problems)
    probe_commands = _strings(probes, "probes", "commands", problems)
    if not check_commands:
        problems.append("checks.commands must not be empty (deterministic checks run before review)")
    if not probe_commands:
        problems.append("probes.commands must not be empty (environment probes run before dispatch)")
    check_timeout = _int(checks, "checks", "timeout_minutes", 45, problems, lo=1)
    probe_timeout = _int(probes, "probes", "timeout_seconds", 60, problems, lo=1)

    if problems:
        raise PolicyError("policy rejected: " + "; ".join(problems), problems=problems)
    assert implementer and reviewer
    return Policy(
        owner=repository["owner"],
        repo=repository["name"],
        project_owner=repository["project_owner"],
        project_number=project_number,
        allow=allow,
        include_optional_epics=include_optional,
        include_later_epics=include_later,
        contract_design_exceptions=exceptions,
        max_stories_per_run=max_stories,
        max_concurrent_implementers=concurrent,
        max_repair_rounds=max_repair,
        max_delegated_tasks=max_tasks,
        max_wall_clock_minutes=max_wall,
        implementer=implementer,
        reviewer=reviewer,
        check_commands=check_commands,
        check_timeout_minutes=check_timeout,
        probe_commands=probe_commands,
        probe_timeout_seconds=probe_timeout,
        digest=hashlib.sha256(text).hexdigest(),
    )
