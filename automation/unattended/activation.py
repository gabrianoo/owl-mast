"""Explicit, run-bound activation authorization for the live transport (ENG-01 opt-in).

The unconditional ``live-execution-disabled`` refusal is replaced by this document. Nothing
is activated by default: without ``--activation`` every real-transport state command still
refuses (``activation-required``). An activation is a TOML file the trusted coordinator or
owner writes for exactly one run. It is an engineering approval under the trusted-machine
operating agreement, **not** a credential and **not** cryptographic authentication: anyone
who can write to the coordinator machine can write one. What it adds is an explicit,
reviewable, journaled decision that names what was approved, so that the shipped policy,
the committed candidate and copied examples can never dispatch by accident.

An activation is current only when all of these hold at the moment of the operation:
``approved = true``; it names this repository, the exact digest of the policy file in use,
the ``live`` environment and the exact run id; its story scope, targets and budgets equal
the policy's; ``issued_at <= now <= expires_at`` with a window of at most
:data:`MAX_WINDOW_MINUTES`; and it cites the published lifecycle smoke and fresh review.
Admission and every advancing operation require a current activation. Cleanup for a run
that was activated earlier (cancel, block, terminal records, cancel-run, the cleanup part
of resume) needs only the run's recorded activation binding and refuses a *different*
activation; expiry stops advancement, never cleanup.
"""

from __future__ import annotations

import hashlib
import re
import tomllib
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from .errors import Refused
from .policy import STORY_ID_RE, Policy, Target, _walk

KNOWN_KEYS = {"approved", "id", "approver", "issued_at", "expires_at", "agreement", "binding", "scope", "targets", "budgets", "evidence"}
BINDING_KEYS = {"repository", "policy_digest", "environment", "run_id"}
BUDGET_KEYS = ("max_stories_per_run", "max_concurrent_implementers", "max_repair_rounds", "max_delegated_tasks", "max_wall_clock_minutes")
EVIDENCE_KEYS = ("lifecycle_smoke", "fresh_review")
MAX_WINDOW_MINUTES = 24 * 60
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{3,120}$")
TIME_CODES = ("activation-expired", "activation-not-yet-valid")


class ActivationError(Refused):
    code = "activation-invalid"


def _parse_time(value: str, name: str, problems: list[str]) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        problems.append(f"{name} {value!r} is not an ISO-8601 UTC timestamp")
        return None


@dataclass(frozen=True)
class Activation:
    id: str
    approved: bool
    approver: str
    issued_at: str
    expires_at: str
    agreement: str
    repository: str
    policy_digest: str
    environment: str
    run_id: str
    stories: tuple[str, ...]
    targets: dict[str, Target]
    budgets: dict[str, int]
    evidence: dict[str, str]
    digest: str
    path: str

    def binding(self) -> dict:
        """What a run records at creation so later operations can tell this activation from any other."""
        return {"id": self.id, "digest": self.digest, "approver": self.approver, "issued_at": self.issued_at, "expires_at": self.expires_at, "path": self.path}

    def matches(self, binding: dict | None) -> bool:
        return bool(binding) and (binding.get("id"), binding.get("digest")) == (self.id, self.digest)

    def problems(self, policy: Policy, run_id: str | None, now: str) -> list[tuple[str, str]]:
        """Every reason this activation does not currently authorize ``run_id`` under
        ``policy`` at ``now``, as ``(code, message)`` pairs; empty means current."""
        out: list[tuple[str, str]] = []
        if not self.approved:
            out.append(("activation-unapproved", "approved is false: the owner has not approved this activation (the committed candidate is never approved)"))
        if self.environment != "live":
            out.append(("activation-invalid", f"binding.environment must be 'live', not {self.environment!r}"))
        if self.repository != policy.repo_slug:
            out.append(("activation-mismatch", f"binding.repository {self.repository!r} is not the policy repository {policy.repo_slug!r}"))
        if self.policy_digest != policy.digest:
            out.append(("activation-mismatch", f"binding.policy_digest {self.policy_digest[:12]} is not the digest of the policy in use ({policy.digest[:12]}); the policy changed since approval or another policy file is in use"))
        if run_id is not None and self.run_id != run_id:
            out.append(("activation-mismatch", f"binding.run_id {self.run_id!r} is not this run ({run_id!r}); an activation authorizes exactly one run"))
        if set(self.stories) != set(policy.allow):
            out.append(("activation-mismatch", f"scope.stories {sorted(self.stories)} differs from the policy allowlist {sorted(policy.allow)}"))
        for name, policy_target in (("implementer", policy.implementer), ("reviewer", policy.reviewer)):
            if self.targets.get(name) != policy_target:
                out.append(("activation-mismatch", f"targets.{name} differs from the policy target (provider/model/options/isolation drift)"))
        for key in BUDGET_KEYS:
            if self.budgets.get(key) != getattr(policy, key):
                out.append(("activation-mismatch", f"budgets.{key} {self.budgets.get(key)!r} differs from the policy budget {getattr(policy, key)!r}"))
        problems: list[str] = []
        issued, expires, at = _parse_time(self.issued_at, "issued_at", problems), _parse_time(self.expires_at, "expires_at", problems), _parse_time(now, "now", problems)
        out.extend(("activation-invalid", p) for p in problems)
        if issued and expires and at:
            if expires <= issued:
                out.append(("activation-invalid", "expires_at must be after issued_at"))
            elif expires - issued > timedelta(minutes=MAX_WINDOW_MINUTES):
                out.append(("activation-invalid", f"activation window exceeds {MAX_WINDOW_MINUTES} minutes"))
            if at < issued:
                out.append(("activation-not-yet-valid", f"now {now} is before issued_at {self.issued_at}"))
            if at > expires:
                out.append(("activation-expired", f"now {now} is after expires_at {self.expires_at}; advancement stops, cleanup of this run stays allowed"))
        return out

    @staticmethod
    def stop_code(problems: list[tuple[str, str]]) -> str | None:
        """One stop code for a problem list: a mismatch or an invalid document outranks a mere expiry."""
        if not problems:
            return None
        codes = {code for code, _ in problems}
        for code in ("activation-mismatch", "activation-invalid", "activation-unapproved", "activation-not-yet-valid", "activation-expired"):
            if code in codes:
                return code
        return problems[0][0]


def load_activation(path: Path) -> Activation:
    """Strict load. Malformed documents, unknown keys, secret-like keys or values and
    non-story scopes refuse with ``activation-invalid``; ``approved = false`` loads but is
    reported as unapproved by :meth:`Activation.problems`."""
    try:
        text = path.read_bytes()
        raw = tomllib.loads(text.decode("utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ActivationError(f"cannot read activation {path}: {exc}", code="activation-invalid") from exc
    problems: list[str] = []
    unknown = set(raw) - KNOWN_KEYS
    if unknown:
        problems.append(f"unknown keys: {sorted(unknown)}")
    missing = KNOWN_KEYS - set(raw)
    if missing:
        problems.append(f"missing keys: {sorted(missing)}")
    _walk(raw, "", problems)
    if not isinstance(raw.get("approved"), bool):
        problems.append("approved must be a boolean")
    for key in ("id", "approver", "issued_at", "expires_at", "agreement"):
        if not isinstance(raw.get(key), str) or not raw.get(key, "").strip():
            problems.append(f"{key} must be a non-empty string")
    if isinstance(raw.get("id"), str) and not ID_RE.match(raw["id"]):
        problems.append("id must be 4..121 characters of [A-Za-z0-9._:-]")
    binding = raw.get("binding")
    if not isinstance(binding, dict) or set(binding) != BINDING_KEYS or not all(isinstance(binding[k], str) and binding[k].strip() for k in BINDING_KEYS):
        problems.append(f"binding must be a table with exactly {sorted(BINDING_KEYS)} as non-empty strings")
        binding = {k: "" for k in BINDING_KEYS}
    scope = raw.get("scope")
    stories: tuple[str, ...] = ()
    if not isinstance(scope, dict) or set(scope) != {"stories"} or not isinstance(scope.get("stories"), list) or not scope["stories"]:
        problems.append("scope must be a table with a non-empty stories list")
    else:
        stories = tuple(str(s) for s in scope["stories"])
        for story in stories:
            if not STORY_ID_RE.match(story):
                problems.append(f"scope.stories entry {story!r} is not an OM-xx.yy story id")
    targets: dict[str, Target] = {}
    raw_targets = raw.get("targets")
    if not isinstance(raw_targets, dict) or set(raw_targets) != {"implementer", "reviewer"}:
        problems.append("targets must name exactly implementer and reviewer")
    else:
        for name in ("implementer", "reviewer"):
            t = raw_targets[name]
            options = t.get("options") if isinstance(t, dict) else None
            if not isinstance(t, dict) or not isinstance(options, dict) or not options or not t.get("provider") or not t.get("model"):
                problems.append(f"targets.{name} needs provider, model and a non-empty options table")
                continue
            targets[name] = Target(str(t["provider"]), str(t["model"]), {str(k): str(v) for k, v in options.items()}, str(t.get("isolation", "")))
    budgets: dict[str, int] = {}
    raw_budgets = raw.get("budgets")
    if not isinstance(raw_budgets, dict) or set(raw_budgets) != set(BUDGET_KEYS) or not all(isinstance(raw_budgets[k], int) and not isinstance(raw_budgets[k], bool) for k in BUDGET_KEYS):
        problems.append(f"budgets must be a table with exactly {list(BUDGET_KEYS)} as integers")
    else:
        budgets = {k: int(raw_budgets[k]) for k in BUDGET_KEYS}
    evidence = raw.get("evidence")
    if not isinstance(evidence, dict) or set(evidence) != set(EVIDENCE_KEYS) or not all(isinstance(evidence[k], str) and evidence[k].strip() for k in EVIDENCE_KEYS):
        problems.append(f"evidence must be a table with exactly {list(EVIDENCE_KEYS)} as non-empty references")
        evidence = {k: "" for k in EVIDENCE_KEYS}
    if problems:
        raise ActivationError(f"activation {path} rejected: " + "; ".join(problems), code="activation-invalid", problems=problems)
    return Activation(
        id=str(raw["id"]), approved=bool(raw["approved"]), approver=str(raw["approver"]), issued_at=str(raw["issued_at"]), expires_at=str(raw["expires_at"]),
        agreement=str(raw["agreement"]), repository=str(binding["repository"]), policy_digest=str(binding["policy_digest"]), environment=str(binding["environment"]),
        run_id=str(binding["run_id"]), stories=stories, targets=targets, budgets=budgets, evidence={k: str(v) for k, v in evidence.items()},
        digest=hashlib.sha256(text).hexdigest(), path=str(path),
    )
