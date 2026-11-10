"""Explicit, run-bound activation authorization for the live transport (ENG-01 opt-in).

The unconditional ``live-execution-disabled`` refusal is replaced by this document. Nothing
is activated by default: without ``--activation`` no live run is created and every admitting or
advancing real-transport command refuses (``activation-required``); cleanup and ``status`` of a
run activated earlier work on its validated recorded binding without the file. An activation is a TOML file the trusted coordinator or
owner writes for exactly one run. It is an engineering approval under the trusted-machine
operating agreement, **not** a credential and **not** cryptographic authentication: anyone
who can write to the coordinator machine can write one. What it adds is an explicit,
reviewable, journaled decision that names what was approved, so that the shipped policy,
the committed candidate and copied examples can never dispatch by accident.

An activation is current only when all of these hold at the moment of the operation:
``approved = true``; it names this repository, the canonical digest of the policy in use (``Policy.digest``: the parsed content, so comments and whitespace do not change it; only a run that already exists bound to the legacy raw-bytes digest of exactly these bytes still accepts an activation naming that digest, never a new run),
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
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .errors import Refused
from .policy import STORY_ID_RE, Policy, Target, _walk

KNOWN_KEYS = {"approved", "id", "approver", "issued_at", "expires_at", "agreement", "binding", "scope", "targets", "budgets", "evidence"}
BINDING_KEYS = {"repository", "policy_digest", "environment", "run_id"}
TARGET_KEYS = {"provider", "model", "options", "isolation"}
# The record a live run persists at creation (``RunState.activation``). It carries the facts a later
# operation needs to re-check without the file: the document identity (id, digest), the approval window,
# and the run binding it was validated against. Anything short of exactly this shape is not a binding.
BINDING_RECORD_KEYS = {"id", "digest", "approver", "issued_at", "expires_at", "path", "repository", "policy_digest", "environment", "run_id", "approved", "validated_at"}
# The durable observed stop a live run persists (``RunState.activation_stop``): exactly this shape, one of these
# codes, a strict UTC observation time. Anything else is not "no stop": it is a malformed record and refuses.
STOP_RECORD_KEYS = {"code", "observed_at", "message", "operation"}
STOP_RECORD_CODES = ("activation-expired", "clock-regression")
DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
BUDGET_KEYS = ("max_stories_per_run", "max_concurrent_implementers", "max_repair_rounds", "max_delegated_tasks", "max_wall_clock_minutes")
EVIDENCE_KEYS = ("lifecycle_smoke", "fresh_review")
MAX_WINDOW_MINUTES = 24 * 60
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{3,120}$")
TIME_CODES = ("activation-expired", "activation-not-yet-valid")


class ActivationError(Refused):
    code = "activation-invalid"


def parse_utc(value) -> datetime:
    """Strict timestamp: an ISO-8601 string with a time part AND an explicit UTC offset
    (``2026-11-07T10:00:00Z`` or ``+00:00``), normalized to UTC. Date-only, timezone-naive,
    non-string and unparsable values raise ``ValueError`` so no consumer ever compares a naive
    and an aware datetime."""
    if not isinstance(value, str) or "T" not in value:
        raise ValueError(f"{value!r} is not an ISO-8601 timestamp with a time part")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{value!r} has no UTC offset (timezone-naive timestamps are refused)")
    return parsed.astimezone(timezone.utc)


def _parse_time(value, name: str, problems: list[str]) -> datetime | None:
    try:
        return parse_utc(value)
    except (ValueError, OverflowError, TypeError) as exc:
        problems.append(f"{name} {value!r} is not an ISO-8601 UTC timestamp with a time part and offset: {exc}")
        return None


def _utc_text(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


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

    def binding(self, validated_at: str | None = None) -> dict:
        """What a live run records at creation so later operations can tell this activation from
        any other and re-check the approval facts without the file. Only ``Store.ensure_run``
        persists it, after ``problems`` came back empty, and ``validate_binding`` re-checks the
        complete record on every reload."""
        return {"id": self.id, "digest": self.digest, "approver": self.approver, "issued_at": self.issued_at, "expires_at": self.expires_at, "path": self.path,
                "repository": self.repository, "policy_digest": self.policy_digest, "environment": self.environment, "run_id": self.run_id, "approved": self.approved, "validated_at": validated_at}

    def matches(self, binding: dict | None) -> bool:
        return isinstance(binding, dict) and (binding.get("id"), binding.get("digest")) == (self.id, self.digest)

    def problems(self, policy: Policy, run_id: str | None, now: str, bound_digest: str | None = None) -> list[tuple[str, str]]:
        """Every reason this activation does not currently authorize ``run_id`` under
        ``policy`` at ``now``, as ``(code, message)`` pairs; empty means current. A new
        activation must name the canonical digest of ``policy``; the legacy raw-bytes digest is
        accepted only for a run that already exists and is bound to it (``bound_digest``, the
        digest recorded in its ``run.json``), never for creating a run."""
        out: list[tuple[str, str]] = []
        if not self.approved:
            out.append(("activation-unapproved", "approved is false: the owner has not approved this activation (the committed candidate is never approved)"))
        if self.environment != "live":
            out.append(("activation-invalid", f"binding.environment must be 'live', not {self.environment!r}"))
        if self.repository != policy.repo_slug:
            out.append(("activation-mismatch", f"binding.repository {self.repository!r} is not the policy repository {policy.repo_slug!r}"))
        legacy = bound_digest is not None and self.policy_digest == bound_digest and bound_digest == getattr(policy, "raw_digest", None)  # an existing run bound to the raw-bytes digest of exactly these bytes
        if self.policy_digest != policy.digest and not legacy:
            hint = f" (the run is bound to {bound_digest[:12]})" if bound_digest and bound_digest != self.policy_digest else ""
            out.append(("activation-mismatch", f"binding.policy_digest {self.policy_digest[:12]} is not the canonical digest of the policy in use ({policy.digest[:12]}, see check-activation){hint}; the policy changed since approval, another policy file is in use, or a new activation names the legacy raw-bytes digest (accepted only for a run that already exists under it)"))
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
            if not isinstance(t, dict):
                problems.append(f"targets.{name} must be a table")
                continue
            unknown_target = set(t) - TARGET_KEYS
            if unknown_target:
                problems.append(f"targets.{name} has unknown keys {sorted(unknown_target)}; only {sorted(TARGET_KEYS)} are allowed")
            options = t.get("options")
            if not isinstance(options, dict) or not options or not all(isinstance(k, str) and isinstance(v, str) and v.strip() for k, v in options.items()):
                problems.append(f"targets.{name}.options must be a non-empty table of string values (no coercion of numbers, booleans or tables)")
            for key in ("provider", "model"):
                if not isinstance(t.get(key), str) or not t[key].strip():
                    problems.append(f"targets.{name}.{key} must be a non-empty string")
            if "isolation" in t and (not isinstance(t["isolation"], str) or not t["isolation"].strip()):
                problems.append(f"targets.{name}.isolation must be a non-empty string when present")
            if unknown_target or not isinstance(options, dict) or any(not isinstance(t.get(k), str) for k in ("provider", "model")) or ("isolation" in t and not isinstance(t["isolation"], str)):
                continue
            targets[name] = Target(t["provider"], t["model"], {k: v for k, v in options.items() if isinstance(k, str) and isinstance(v, str)}, t.get("isolation", ""))
    budgets: dict[str, int] = {}
    raw_budgets = raw.get("budgets")
    if not isinstance(raw_budgets, dict) or set(raw_budgets) != set(BUDGET_KEYS) or not all(isinstance(raw_budgets[k], int) and not isinstance(raw_budgets[k], bool) for k in BUDGET_KEYS):
        problems.append(f"budgets must be a table with exactly {list(BUDGET_KEYS)} as integers")
    else:
        budgets = {k: int(raw_budgets[k]) for k in BUDGET_KEYS}
    times: dict[str, str] = {}
    for key in ("issued_at", "expires_at"):
        if isinstance(raw.get(key), str):
            parsed = _parse_time(raw[key], key, problems)
            if parsed is not None:
                times[key] = _utc_text(parsed)
    evidence = raw.get("evidence")
    if not isinstance(evidence, dict) or set(evidence) != set(EVIDENCE_KEYS) or not all(isinstance(evidence[k], str) and evidence[k].strip() for k in EVIDENCE_KEYS):
        problems.append(f"evidence must be a table with exactly {list(EVIDENCE_KEYS)} as non-empty references")
        evidence = {k: "" for k in EVIDENCE_KEYS}
    if problems:
        raise ActivationError(f"activation {path} rejected: " + "; ".join(problems), code="activation-invalid", problems=problems)
    return Activation(
        id=str(raw["id"]), approved=bool(raw["approved"]), approver=str(raw["approver"]), issued_at=times["issued_at"], expires_at=times["expires_at"],
        agreement=str(raw["agreement"]), repository=str(binding["repository"]), policy_digest=str(binding["policy_digest"]), environment=str(binding["environment"]),
        run_id=str(binding["run_id"]), stories=stories, targets=targets, budgets=budgets, evidence={k: str(v) for k, v in evidence.items()},
        digest=hashlib.sha256(text).hexdigest(), path=str(path),
    )


def refresh_activation(activation: Activation | None, operation: str) -> Activation | None:
    """Re-read the source the presented document was loaded from. The file is the approval; the
    loaded object is a cache and is never trusted across a decision boundary. Returns the fresh
    document, or ``None`` when the source is gone (nothing is presented any more). A source that
    no longer loads refuses ``activation-invalid``; one whose digest changed refuses
    ``activation-mismatch``: both are a different document from the one presented, for every
    operation, run creation included. An object without a source path (tests) is returned as is."""
    if activation is None or not activation.path:
        return activation
    path = Path(activation.path)
    if not path.exists():
        return None
    try:
        fresh = load_activation(path)
    except Refused as exc:
        raise Refused(f"{operation}: the activation source {path} no longer loads ({exc}); a malformed source is not the document that was presented; omit --activation to clean up on the recorded binding", code="activation-invalid", problems=exc.detail.get("problems")) from exc
    if fresh.digest != activation.digest:
        raise Refused(f"{operation}: the activation source {path} changed since it was loaded (digest {fresh.digest[:12]} vs {activation.digest[:12]}); a changed document is refused for every operation, cleanup included; omit --activation to clean up on the recorded binding", code="activation-mismatch")
    return fresh


class BindingError(Refused):
    code = "activation-binding-invalid"


def validate_binding(binding, run_id: str, repo: str, policy_digest: str) -> dict:
    """The persisted activation record of a live run, re-checked strictly on every load: exactly
    :data:`BINDING_RECORD_KEYS`, a well-formed id and file digest, strict UTC timestamps in
    order within the maximum window, a non-null ``validated_at`` inside that window (the moment
    ``ensure_run`` validated the document), ``approved`` exactly true, and a run binding equal to
    the run selected by the caller (run id, repository, policy digest, ``live``). A partial, foreign, unapproved or otherwise inconsistent
    record is not a binding: it refuses with ``activation-binding-invalid`` and the run's
    obligations stay where they are (nothing is replaced, migrated or inferred). ``None`` or an
    empty value is reported separately by the caller as ``activation-required``."""
    problems: list[str] = []
    if not isinstance(binding, dict):
        raise BindingError(f"run {run_id}: persisted activation binding is {type(binding).__name__}, not a record; a live run without a valid recorded activation can neither advance nor release (restore run.json from the run that created it, or recover by hand)", code="activation-binding-invalid")
    if set(binding) != BINDING_RECORD_KEYS:
        problems.append(f"keys {sorted(set(binding) ^ BINDING_RECORD_KEYS)} differ from the binding record shape {sorted(BINDING_RECORD_KEYS)}")
    for key in ("id", "digest", "approver", "issued_at", "expires_at", "path", "repository", "policy_digest", "environment", "run_id"):
        if not isinstance(binding.get(key), str) or not binding.get(key, "").strip():
            problems.append(f"{key} must be a non-empty string")
    if isinstance(binding.get("id"), str) and not ID_RE.match(binding["id"]):
        problems.append("id is malformed")
    if isinstance(binding.get("digest"), str) and not DIGEST_RE.match(binding["digest"]):
        problems.append("digest is not a sha256 hex digest")
    if binding.get("approved") is not True:
        problems.append("approved is not exactly true")
    issued, expires = _parse_time(binding.get("issued_at"), "issued_at", problems), _parse_time(binding.get("expires_at"), "expires_at", problems)
    validated = _parse_time(binding.get("validated_at"), "validated_at", problems)  # the creation moment is required: a record without it was never persisted by ensure_run
    if issued and expires:
        if expires <= issued:
            problems.append("expires_at must be after issued_at")
        elif expires - issued > timedelta(minutes=MAX_WINDOW_MINUTES):
            problems.append(f"approval window exceeds {MAX_WINDOW_MINUTES} minutes")
        if validated is not None and not (issued <= validated <= expires):
            problems.append(f"validated_at {binding.get('validated_at')!r} is outside the approval window {binding.get('issued_at')!r}..{binding.get('expires_at')!r}; no validated creation can have happened then")
    for key, expected in (("run_id", run_id), ("repository", repo), ("policy_digest", policy_digest), ("environment", "live")):
        if binding.get(key) != expected:
            problems.append(f"{key} {binding.get(key)!r} is not this run's {expected!r}")
    if problems:
        raise BindingError(f"run {run_id}: persisted activation binding is not a valid binding for this run: " + "; ".join(problems) + "; nothing is advanced or released on it (restore run.json from the run that created it, or recover by hand)", code="activation-binding-invalid", problems=problems)
    return binding


def validate_stop_record(stop, run_id: str) -> dict | None:
    """The persisted durable stop of a live run: ``None`` (no stop observed) or exactly
    :data:`STOP_RECORD_KEYS` with a code from :data:`STOP_RECORD_CODES`, a strict UTC
    ``observed_at`` and non-empty ``message`` / ``operation`` strings. Nothing else is read as
    the absence of a stop: ``false``, a list, a string, a partial or unknown-code record refuse
    ``run-state-invalid`` (no truthiness, no silent replacement)."""
    if stop is None:
        return None
    problems: list[str] = []
    if not isinstance(stop, dict):
        raise Refused(f"run {run_id}: persisted activation_stop is {type(stop).__name__}, not a stop record or null; a malformed stop is never read as 'no stop' (restore run.json from the run that wrote it, or recover by hand)", code="run-state-invalid")
    if set(stop) != STOP_RECORD_KEYS:
        problems.append(f"keys {sorted(set(stop) ^ STOP_RECORD_KEYS)} differ from the stop record shape {sorted(STOP_RECORD_KEYS)}")
    if stop.get("code") not in STOP_RECORD_CODES:
        problems.append(f"code {stop.get('code')!r} is not a recorded stop code {list(STOP_RECORD_CODES)}")
    _parse_time(stop.get("observed_at"), "observed_at", problems)
    for key in ("message", "operation"):
        if not isinstance(stop.get(key), str) or not stop.get(key, "").strip():
            problems.append(f"{key} must be a non-empty string")
    if problems:
        raise Refused(f"run {run_id}: persisted activation_stop is not a valid stop record: " + "; ".join(problems) + "; the run neither advances nor releases on it (restore run.json from the run that wrote it, or recover by hand)", code="run-state-invalid", problems=problems)
    return stop


def validate_high_water(value, run_id: str) -> str | None:
    """``RunState.last_observed_at``: ``None`` or a strict UTC timestamp. A malformed value is
    refused (``run-state-invalid``), never replaced by the current time."""
    if value is None:
        return None
    problems: list[str] = []
    if _parse_time(value, "last_observed_at", problems) is None:
        raise Refused(f"run {run_id}: persisted last_observed_at is not a valid observation time: " + "; ".join(problems) + "; the clock-regression high-water mark cannot be trusted (restore run.json from the run that wrote it, or recover by hand)", code="run-state-invalid", problems=problems)
    return value
