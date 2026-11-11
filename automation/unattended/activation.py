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
import json
import os
import pwd
import re
import tempfile
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
# A recorded stop also carries ``stop_id`` (a uuid4 hex), so two stops observed at the same second are still two
# stops (the once-per-run clear compares it); older stops have none and are still valid.
STOP_RECORD_OPTIONAL_KEYS = {"stop_id"}
STOP_ID_RE = re.compile(r"[0-9a-f]{32}")  # used with fullmatch: no trailing newline
STOP_RECORD_CODES = ("activation-expired", "clock-regression")
DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
BUDGET_KEYS = ("max_stories_per_run", "max_concurrent_implementers", "max_repair_rounds", "max_delegated_tasks", "max_wall_clock_minutes")
EVIDENCE_KEYS = ("lifecycle_smoke", "fresh_review")
MAX_WINDOW_MINUTES = 24 * 60
CLEARANCE_KEYS = {"run_id", "activation_id", "approver", "stop_observed_at", "reason"}
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{3,120}$")
TIME_CODES = ("activation-expired", "activation-not-yet-valid")
# An evidence reference is a published GitHub comment or review on the policy repository: an issue
# or pull request comment (``#issuecomment-N``) or a pull request review (``#pullrequestreview-N``,
# only under ``pull/``: reviews exist only on pull requests).
# Placeholders (``REPLACE…``, angle brackets) and anything else are not citations.
# Only the shape is checked (the whole value, ASCII digits, the owner/repository compared without
# regard to case, as GitHub does): the tool never fetches the comment, so what it says, who wrote
# it and whether it is the smoke or the review stay the approver's statement. The comment or review
# id is 1 to 20 digits, leading zeros included: a sanity limit (GitHub ids are far shorter); a longer
# value is not a citation, and neither is an id whose value is 0 (``-0``, ``-000``: GitHub never issues it).
EVIDENCE_URL_RE = re.compile(r"https://github\.com/([^/\s#?]+/[^/\s#?]+)/(?:issues/[0-9]+#issuecomment|pull/[0-9]+#(?:issuecomment|pullrequestreview))-([0-9]{1,20})", re.ASCII)
PLACEHOLDER_RE = re.compile(r"^\s*REPLACE|[<>]")
# The use ledger: one record per activation **digest** in one directory per user account and machine
# (the home directory of the account running the tool), written when a live run is created from the
# document. It is keyed on the content, not on the file name, so a copy, a symlink, a hard link or
# another spelling of the path is the same approval, and it lives outside every state directory and
# work tree, so it survives the run directory. Another account, another WSL distribution or another
# host starts with an empty ledger: the one-run rule holds per account and machine (trusted-machine
# convention, ``check-activation`` and ``status`` print the ledger root).
USE_LEDGER_DIR = (".local", "state", "owl-mast", "activation-ledger")  # under the home directory of the coordinator's user
# Ledger record states: ``pending`` (written before run.json; a crash or a deleted run directory leaves it
# ambiguous), ``committed`` (run.json exists), ``aborted`` (the creation failed and run.json was absent).
LEDGER_STATES = ("pending", "committed", "aborted")
# A retried creation keeps its first attempt and the latest ones in ``attempts``; older ones are dropped.
MAX_RECENT_ATTEMPTS = 10


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

    def __post_init__(self) -> None:
        # The source file is the approval and is re-read at every decision boundary; an object without
        # one could never be re-read, so it is not an activation (``load_activation`` is the only constructor).
        if not isinstance(self.path, str) or not self.path.strip():
            raise ActivationError("an Activation needs the path of the source document it was loaded from (load_activation is the only constructor)", code="activation-invalid")

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
        ``policy`` at ``now``, as ``(code, message)`` pairs; empty means current. A run id is
        needed: an activation authorizes exactly one run, so without one (``None`` or blank) it
        is current for nothing. A new activation must name the canonical digest of ``policy``;
        the legacy raw-bytes digest is accepted only for a run that already exists and is bound
        to it (``bound_digest``, the digest recorded in its ``run.json``), never for creating a
        run. These are the conditions every advancing operation re-checks mid-run; the rules that
        hold only when a run is created (evidence citations, the use ledger, the remaining
        window) are in :meth:`creation_problems`, so tightening them never strands a run that
        was created under an earlier rule."""
        out: list[tuple[str, str]] = []
        if not isinstance(run_id, str) or not run_id.strip():
            out.append(("activation-invalid", "no run id to check the activation against; an activation authorizes exactly one run (--run-id)"))
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
        if isinstance(run_id, str) and run_id.strip() and self.run_id != run_id:
            out.append(("activation-mismatch", f"binding.run_id {self.run_id!r} is not this run ({run_id!r}); an activation authorizes exactly one run"))
        if tuple(sorted(self.stories)) != tuple(sorted(policy.allow)):
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

    def evidence_problems(self, policy: Policy) -> list[tuple[str, str]]:
        """The citation rule, applied when a run is created (never mid-run): each ``evidence``
        value is a GitHub comment or review URL on the policy repository, no placeholder, and the
        two keys cite two different comments. Shape only: the content is not fetched or verified."""
        out: list[tuple[str, str]] = []
        for key in EVIDENCE_KEYS:
            value = self.evidence.get(key, "")
            match = EVIDENCE_URL_RE.fullmatch(value)
            if PLACEHOLDER_RE.search(value):
                out.append(("activation-invalid", f"evidence.{key} {value!r} is a placeholder, not a citation of the published {key.replace('_', ' ')}"))
            elif not match or match.group(1).lower() != policy.repo_slug.lower():
                out.append(("activation-invalid", f"evidence.{key} {value!r} is not a GitHub comment or review URL on {policy.repo_slug} (https://github.com/{policy.repo_slug}/(issues|pull)/<n>#issuecomment-<id>, or pull/<n>#pullrequestreview-<id>: reviews exist only on pull requests)"))
        for key in EVIDENCE_KEYS:
            match = EVIDENCE_URL_RE.fullmatch(self.evidence.get(key, ""))
            if match and not PLACEHOLDER_RE.search(self.evidence.get(key, "")) and int(match.group(2)) == 0:
                out.append(("activation-invalid", f"evidence.{key} {self.evidence[key]!r} cites id 0, which GitHub never issues; a placeholder-like id is not a citation"))
        if not out:
            # the numeric id is the publication, whatever kind or issue/pull path the URL spells and however
            # many leading zeros it carries: ``issuecomment-05`` and ``pullrequestreview-5`` cite one id twice
            cited = [int(EVIDENCE_URL_RE.fullmatch(self.evidence[key]).group(2)) for key in EVIDENCE_KEYS]
            if len(set(cited)) != len(cited):
                out.append(("activation-invalid", f"evidence.{EVIDENCE_KEYS[0]} and evidence.{EVIDENCE_KEYS[1]} cite the same comment or review id ({cited[0]}); the lifecycle smoke and the fresh review are two publications"))
        return out

    def creation_problems(self, policy: Policy, run_id: str | None, now: str, state_dir: str | os.PathLike | None = None) -> list[tuple[str, str]]:
        """:meth:`problems` plus the conditions that hold only when a run is created, none of
        which a mid-run operation ever applies: the evidence citations (:meth:`evidence_problems`),
        the use ledger (``activation-used``: this document already created a run; an interrupted
        creation of this same run under this same ``state_dir`` may be retried), and a remaining
        window that covers the run's wall-clock budget (``activation-window-short``), without which
        the run would reserve work and launch a worker only to hit a durable expiry stop partway
        through, spending the slot and keeping the story owned."""
        out = self.problems(policy, run_id, now)
        out.extend(self.evidence_problems(policy))
        used = activation_use(self.digest, self.path)
        if used is not None and not _retryable_creation(used, state_dir, run_id):
            out.append(("activation-used", use_refusal(used, ledger_path(self.digest, self.path))))
        problems: list[str] = []
        expires, at = _parse_time(self.expires_at, "expires_at", problems), _parse_time(now, "now", problems)
        if policy.max_wall_clock_minutes >= MAX_WINDOW_MINUTES:
            out.append(("activation-window-short", f"the policy's wall-clock budget of {policy.max_wall_clock_minutes} minutes does not fit inside one activation window (at most {MAX_WINDOW_MINUTES} minutes, and the run starts after issued_at); no activation can create a live run under this policy: lower budgets.max_wall_clock_minutes"))
        elif expires and at and at <= expires and expires - at < timedelta(minutes=policy.max_wall_clock_minutes):
            remaining = int((expires - at).total_seconds() // 60)
            out.append(("activation-window-short", f"only {remaining} minutes remain before expires_at {self.expires_at}; a run needs its whole wall-clock budget of {policy.max_wall_clock_minutes} minutes inside the approval window (re-issue the activation with a later expiry)"))
        return out

    @staticmethod
    def stop_code(problems: list[tuple[str, str]]) -> str | None:
        """One stop code for a problem list: a mismatch or an invalid document outranks a used
        one, and a used one outranks the time codes (re-issuing a later window does not help a
        document that already created its run; ``check-activation`` lists every code as ``stops``)."""
        if not problems:
            return None
        codes = {code for code, _ in problems}
        for code in STOP_CODE_ORDER:
            if code in codes:
                return code
        return problems[0][0]

    @staticmethod
    def stop_codes(problems: list[tuple[str, str]]) -> list[str]:
        """Every distinct code of a problem list, in the order :meth:`stop_code` ranks them."""
        codes = {code for code, _ in problems}
        return [code for code in STOP_CODE_ORDER if code in codes] + sorted(codes - set(STOP_CODE_ORDER))


STOP_CODE_ORDER = ("activation-mismatch", "activation-invalid", "activation-unapproved", "activation-used", "activation-not-yet-valid", "activation-expired", "activation-window-short")


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
        entries = scope["stories"]
        if not all(isinstance(s, str) for s in entries):
            problems.append("scope.stories entries must be strings (no coercion of numbers, booleans or tables)")
        stories = tuple(s for s in entries if isinstance(s, str))
        for story in stories:
            if not STORY_ID_RE.match(story):
                problems.append(f"scope.stories entry {story!r} is not an OM-xx.yy story id")
        if len(set(stories)) != len(stories):
            problems.append(f"scope.stories repeats {sorted({s for s in stories if stories.count(s) > 1})}; the scope lists each story once")
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
    operation, run creation included."""
    if activation is None:
        return None
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


def ledger_root(source_path: str) -> Path:
    """The directory of the use ledger, one per user account and machine. One fixed place, not
    configurable by a flag or an environment variable (the unattended loop could set either): the
    home directory comes from the account database, not from ``$HOME``. A uid without an account
    entry (a container, an NSS outage) has no ledger and refuses ``activation-ledger-unwritable``,
    and so does an entry whose home directory is empty or relative (some container and system
    accounts): the ledger would resolve under the current directory, and another directory would
    be another, empty ledger. The test suite replaces this function; ``source_path`` (the activation
    file) is unused here."""
    uid = os.getuid()
    try:
        home = pwd.getpwuid(uid).pw_dir
    except KeyError as exc:
        raise Refused(f"the use ledger has no home: uid {uid} has no entry in the account database (a container uid or an NSS outage); no live run is created and no use can be checked without the ledger", code="activation-ledger-unwritable", uid=uid) from exc
    if not isinstance(home, str) or not home or not os.path.isabs(home):
        raise Refused(f"the use ledger has no home: the account entry of uid {uid} names the home directory {home!r}, which is not an absolute path; the ledger would follow the current directory, so no live run is created and no use can be checked", code="activation-ledger-unwritable", uid=uid, home=home)
    return Path(home).joinpath(*USE_LEDGER_DIR)


def ledger_path(digest: str, source_path: str) -> Path:
    return ledger_root(source_path) / f"{digest}.json"


def activation_use(digest: str, source_path: str) -> dict | None:
    """The use on record for a document digest: ``None`` when it never created a run, the ledger
    record otherwise. A ledger that cannot be read is a use (``{"unreadable": True}``), never the
    absence of one."""
    path = ledger_path(digest, source_path)
    try:
        used = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, NotADirectoryError):  # no record, or no ledger directory at all (creating it is refused separately)
        return None
    except (OSError, ValueError):
        return {"unreadable": True}
    if not isinstance(used, dict):
        return {"unreadable": True}
    if "attempts" in used and not (isinstance(used["attempts"], list) and all(isinstance(a, dict) for a in used["attempts"])):
        return {"unreadable": True}  # only this tool writes the history: anything but a list of records is a damaged record, a use
    return used


def _same_run(used: dict, state_dir, run_id) -> bool:
    """Whether the record names this run: the same run id under the same state directory, compared by
    real path and without regard to case (:func:`_fold`), like every containment check (the state
    directory may sit on a case-insensitive mount)."""
    return state_dir is not None and used.get("run_id") == run_id and isinstance(used.get("state_dir"), str) and _fold(used["state_dir"]) == _fold(state_dir)


def _same_document_other_dir(used: dict, state_dir, run_id) -> bool:
    """The record names this run id under another state directory (another mount path, a moved or
    copied directory): this run cannot confirm it."""
    return state_dir is not None and used.get("run_id") == run_id and not _same_run(used, state_dir, run_id)


def _retryable_creation(used: dict, state_dir, run_id) -> bool:
    """Whether the use on record is a creation of exactly this run that is known to have failed:
    ``aborted`` (``save_run`` raised and ``run.json`` was absent) under the same state directory
    (compared by realpath) and run id. Only that creation may be retried. A ``pending`` record is
    never retryable: it is what a process that died between the ledger and ``run.json``, or a run
    directory deleted after a creation whose confirmation failed, leaves behind, and the two cannot
    be told apart."""
    return used.get("state") == "aborted" and _same_run(used, state_dir, run_id)


def use_refusal(used: dict, path) -> str:
    """Why a use on record refuses another creation, in the words of its state."""
    if not used.get("unreadable") and used.get("state") not in LEDGER_STATES:  # fail closed like a damaged record: a use, never "already created"
        return f"the use ledger record of this document ({path}) has the unknown state {used.get('state')!r} (expected one of {list(LEDGER_STATES)}); a record that cannot be interpreted is a use, never the absence of one (inspect or restore that file; re-issuing the activation creates a new record)"
    if used.get("unreadable"):
        return f"the use ledger record of this document ({path}) exists but cannot be read; a damaged record is a use, never the absence of one (inspect or restore that file; re-issuing the activation creates a new record)"
    run, where, at = used.get("run_id"), used.get("state_dir"), used.get("created_at")
    if used.get("state") == "pending":
        return f"this document's creation of live run {run!r} under {where!r} at {at} is unconfirmed (use ledger {path} is still pending: the process died between the ledger record and run.json, or the run directory was deleted after a creation whose confirmation failed); whether that run was created cannot be told, so this document creates nothing more: re-issue the activation"
    if used.get("state") == "aborted":
        return f"this document's creation of live run {run!r} under {where!r} failed at {at} before its run.json was written (use ledger {path}: aborted); only that same creation may be retried (--run-id {run} --state-dir {where}); any other run needs a newly issued activation"
    return f"this document already created live run {run!r} under {where!r} at {at} (use ledger {path}); one activation creates exactly one run, and a new run needs a newly issued activation (any change to the document, such as a later window, is a new document)"


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_ledger(path: Path, record: dict, replace: bool) -> None:
    """Crash-safe: the record is written to a temporary file in the ledger directory and synced,
    then linked (first use: fails if the name exists) or renamed (state change) to its final name,
    and the directory is synced. The final name never holds a partial record."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(record, fh, indent=1, sort_keys=True)
            fh.flush()
            os.fsync(fh.fileno())
        if replace:
            os.replace(tmp, path)
        else:
            os.link(tmp, path)  # atomic and exclusive: FileExistsError when another creation got there first
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
    _fsync_dir(path.parent)


def record_activation_use(activation: Activation, state_dir: str | os.PathLike, run_id: str, now: str) -> dict:
    """Mark the activation document as used, right before the run it creates is persisted. One
    activation creates exactly one live run: a second creation from the same content, under
    another ``--state-dir``, another run id, another file name (a copy, a link) or after the run
    directory was deleted, refuses ``activation-used`` and names the use on record. The record is
    keyed on the document digest in :func:`ledger_root`, carries the absolute state directory and
    is written crash-safely (:func:`_write_ledger`); this tool never removes it.

    It is written ``pending`` and confirmed (:func:`confirm_activation_use`) once ``run.json``
    exists. A creation whose ``save_run`` raised while ``run.json`` was absent is marked ``aborted``
    (:func:`abort_activation_use`): only that same creation (same state directory, same run id)
    may be retried, and the retry sets the record back to ``pending`` with ``created_at`` set to the
    retry, ``first_attempt_at`` kept and the attempt appended to ``attempts``. A ``pending`` record without
    ``run.json`` is ambiguous (the process died in between, or the run directory was deleted
    after a confirmation that failed) and refuses ``activation-used``: the document is burned and
    is re-issued. Like the activation itself this is a trusted-machine control, not
    authentication: whoever can write to the machine can remove a record."""
    path = ledger_path(activation.digest, activation.path)
    record = {"activation_id": activation.id, "digest": activation.digest, "source": os.path.realpath(activation.path), "state_dir": os.path.realpath(state_dir), "run_id": run_id, "created_at": now, "state": "pending"}
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    except OSError as exc:
        raise Refused(f"run {run_id}: cannot create the use ledger directory {path.parent}: {exc}; no run is created without the record (the document itself is valid)", code="activation-ledger-unwritable", ledger=str(path)) from exc
    try:
        _write_ledger(path, record, replace=False)
    except FileExistsError:
        used = activation_use(activation.digest, activation.path) or {"unreadable": True}
        if not _retryable_creation(used, state_dir, run_id):
            raise Refused(f"run {run_id}: activation {activation.id}: " + use_refusal(used, path), code="activation-used", used=used, ledger=str(path)) from None
        # the failed creation of this same run, retried: pending again until its run.json exists. ``created_at`` is this
        # attempt (an unconfirmed refusal names when the creation that may exist was tried); the history is kept
        first = used.get("first_attempt_at") or used.get("created_at")
        attempts = [dict(a) for a in (used.get("attempts") or [{"at": used.get("created_at"), "pid": None, "source": used.get("source")}])]
        if used.get("abort_cause") is not None:
            attempts[-1]["abort_cause"] = used["abort_cause"]  # why the attempt that is retried now failed
        attempts.append({"at": now, "pid": os.getpid(), "source": os.path.realpath(activation.path)})
        if len(attempts) > 1 + MAX_RECENT_ATTEMPTS:
            attempts = attempts[:1] + attempts[-MAX_RECENT_ATTEMPTS:]  # bounded: the first attempt and the latest ones
        record = {**{k: v for k, v in used.items() if k not in ("retried_at", "abort_cause")}, "state": "pending", "created_at": now, "first_attempt_at": first, "attempts": attempts, "source": os.path.realpath(activation.path)}
        try:
            _write_ledger(path, record, replace=True)
        except OSError as exc:
            raise Refused(f"run {run_id}: cannot mark the retried creation of activation {activation.id} pending in the use ledger ({path}): {exc}; no run is created without the record", code="activation-ledger-unwritable", ledger=str(path)) from exc
        return record
    except OSError as exc:
        raise Refused(f"run {run_id}: cannot record the use of activation {activation.id} in the use ledger ({path}): {exc}; no run is created without the record (the document itself is valid; make {path.parent} writable)", code="activation-ledger-unwritable", ledger=str(path)) from exc
    return record


def confirm_activation_use(binding: dict | None, state_dir: str | os.PathLike, run_id: str, report_success: bool = False) -> dict | None:
    """Mark the use of a run's activation as ``committed`` once its ``run.json`` exists: from then
    on the document creates nothing again, even after the run directory is deleted. Called after
    creation and on every later open of the run, so a ``pending`` (crash between ``run.json`` and
    this write) or ``aborted`` record of this run is settled by the next open. A missing record (a
    run created before the ledger existed), an unreadable one and a record of another run are left
    alone. Returns ``None`` when nothing is left to confirm, or why the confirmation could not be
    written as ``{type, errno, message}`` (the record stays as it is; the caller journals
    ``activation-use-unconfirmed`` once per ``(type, errno)``, the refusal code standing in for the errno of a ``Refused``: the message carries the random name
    of the temporary file and differs on every attempt; an ``OSError`` without an errno is told apart
    by its ``strerror``). An unconfirmed record of this run id under a state directory that is not
    this one (another mount path, a moved directory) is reported as ``state-dir-mismatch``: it cannot
    be confirmed from here, and it is not silently left pending. With ``report_success`` a record that
    this call marked ``committed`` returns ``{"confirmed": True}``."""
    if not isinstance(binding, dict) or not isinstance(binding.get("digest"), str) or not isinstance(binding.get("path"), str):
        return None
    try:
        used = activation_use(binding["digest"], binding["path"])
        if used is None or used.get("state") not in ("pending", "aborted"):
            return None
        if _same_document_other_dir(used, state_dir, run_id):
            return {"type": "state-dir-mismatch", "errno": None, "strerror": None, "message": f"the use ledger record of run {run_id} names the state directory {used.get('state_dir')!r}, not {os.path.realpath(state_dir)!r}; it stays {used.get('state')} (open the run through the directory it was created under to confirm it)"}
        if not _same_run(used, state_dir, run_id):
            return None
        _write_ledger(ledger_path(binding["digest"], binding["path"]), {**used, "state": "committed"}, replace=True)
    except (OSError, Refused) as exc:
        # errno identifies an OSError; a Refused is identified by its code (two different refusals are two lines)
        errno = exc.code if isinstance(exc, Refused) else getattr(exc, "errno", None)
        strerror = (getattr(exc, "strerror", None) or str(exc)) if isinstance(exc, OSError) and errno is None else None
        return {"type": type(exc).__name__, "errno": errno, "strerror": strerror, "message": f"{type(exc).__name__}: {exc}"}
    return {"confirmed": True} if report_success else None


def abort_activation_use(activation: Activation, state_dir: str | os.PathLike, run_id: str, run_path: Path, cause: BaseException | None = None) -> bool:
    """After ``save_run`` raised: mark this run's ``pending`` record ``aborted`` when ``run.json``
    is known not to exist, so the same creation may be retried; ``cause`` (the creation's error) is
    recorded as ``abort_cause``. Returns whether the record was marked; a failure leaves it
    ``pending`` (refused as unconfirmed). Only ``FileNotFoundError`` / ``NotADirectoryError`` from
    ``os.stat`` mean the file is absent: ``Path.exists()`` answers ``False`` for an unreadable run
    directory from Python 3.13 on, which would mark a creation aborted whose ``run.json`` may exist.
    A ledger or file-system error returns ``False``; the caller (``Store.ensure_run``) also guards
    against anything else, so the original error is never replaced."""
    try:
        try:
            os.stat(run_path)
        except (FileNotFoundError, NotADirectoryError):
            pass  # known absent
        else:
            return False  # run.json exists: the creation is not known to have failed
        path = ledger_path(activation.digest, activation.path)
        used = activation_use(activation.digest, activation.path)
        if used is None or used.get("state") != "pending" or not _same_run(used, state_dir, run_id):
            return False
        marked = {**used, "state": "aborted"}
        if cause is not None:
            marked["abort_cause"] = f"{type(cause).__name__}: {cause}"[:500]
        _write_ledger(path, marked, replace=True)
    except (OSError, Refused):
        return False
    return True


def ledger_report(digest: str, source_path: str) -> dict:
    """What ``check-activation`` and ``status`` print about the ledger: its root and the record."""
    try:
        return {"root": str(ledger_root(source_path)), "record": activation_use(digest, source_path)}
    except Refused as exc:
        return {"root": None, "record": None, "error": exc.code, "message": str(exc)}


def _fold(path: str | os.PathLike) -> tuple[str, ...]:
    """The components of a real path, case-folded: the comparison form for containment. The state
    directory may sit on a case-insensitive mount (WSL drvfs under ``/mnt/c``), where ``realpath``
    does not normalise case, so a path that differs only by case is the same place."""
    return Path(os.path.normcase(os.path.realpath(path)).casefold()).parts


def is_inside(path: str | os.PathLike, root: str | os.PathLike) -> bool:
    """Whether ``path`` is ``root`` or lies under it, by real path and without regard to case
    (:func:`_fold`): a clearance spelled with another case is still inside."""
    inner, outer = _fold(path), _fold(root)
    return inner[:len(outer)] == outer


def load_clearance(path: Path, refuse_inside: dict[str, str | os.PathLike] | None = None) -> dict:
    """The owner's clearance of one recorded ``clock-regression`` stop, for
    ``clear-clock-regression --clearance``: a TOML file with exactly :data:`CLEARANCE_KEYS` as
    non-empty strings (the run id, the id and approver of the activation the run was created
    under, the ``observed_at`` of the stop being cleared, and the reason). Returned with its
    ``digest`` and ``path`` for the journal. Anything else refuses ``clearance-invalid``.

    Owner-only is a **convention** on the trusted machine, not a control: every field is readable
    by the unattended loop (``run.json``, ``status``), so a process on this machine can write a
    valid clearance. What the tool enforces is where it is read from: a clearance whose real path
    lies inside one of ``refuse_inside`` (the state directory, any git work tree the CLI found) refuses
    ``clearance-invalid``, so one is never picked up from where the loop works. The comparison
    ignores case (:func:`is_inside`)."""
    real = Path(os.path.realpath(path))
    for label, root in (refuse_inside or {}).items():
        if root is None:
            continue
        base = Path(os.path.realpath(root))
        if is_inside(real, base):
            raise Refused(f"clearance {path} lies inside, or inside a case variant of, {label} ({base}; paths are compared without regard to case); a clearance is the owner's document and is kept outside the state directory and outside every git work tree, where the unattended loop works (owner-only is a trusted-machine convention, not authentication)", code="clearance-invalid", path=str(real), inside=label)
    try:
        # the resolved path that was checked, not the name again. This narrows a race, it does not close one: the path is
        # resolved again component by component, so a directory swapped for a symlink after the check is followed, and a
        # hard link is never detected. Where a clearance is read from is hygiene on the trusted machine, not a control.
        text = real.read_bytes()
        raw = tomllib.loads(text.decode("utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise Refused(f"cannot read clearance {path}: {exc}", code="clearance-invalid") from exc
    problems: list[str] = []
    if set(raw) != CLEARANCE_KEYS:
        problems.append(f"keys {sorted(set(raw) ^ CLEARANCE_KEYS)} differ from exactly {sorted(CLEARANCE_KEYS)}")
    problems.extend(f"{key} must be a non-empty string" for key in sorted(CLEARANCE_KEYS & set(raw)) if not isinstance(raw[key], str) or not raw[key].strip())
    _walk(raw, "", problems)
    if problems:
        raise Refused(f"clearance {path} rejected: " + "; ".join(problems), code="clearance-invalid", problems=problems)
    return {**{key: raw[key] for key in sorted(CLEARANCE_KEYS)}, "digest": hashlib.sha256(text).hexdigest(), "path": str(path)}


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
    :data:`STOP_RECORD_KEYS` (plus the optional ``stop_id``, a uuid4 hex) with a code from
    :data:`STOP_RECORD_CODES`, a strict UTC ``observed_at`` and non-empty ``message`` /
    ``operation`` strings. Nothing else is read as
    the absence of a stop: ``false``, a list, a string, a partial or unknown-code record refuse
    ``run-state-invalid`` (no truthiness, no silent replacement)."""
    if stop is None:
        return None
    problems: list[str] = []
    if not isinstance(stop, dict):
        raise Refused(f"run {run_id}: persisted activation_stop is {type(stop).__name__}, not a stop record or null; a malformed stop is never read as 'no stop' (restore run.json from the run that wrote it, or recover by hand)", code="run-state-invalid")
    if set(stop) - STOP_RECORD_OPTIONAL_KEYS != STOP_RECORD_KEYS:
        problems.append(f"keys {sorted((set(stop) - STOP_RECORD_OPTIONAL_KEYS) ^ STOP_RECORD_KEYS)} differ from the stop record shape {sorted(STOP_RECORD_KEYS)} (plus the optional {sorted(STOP_RECORD_OPTIONAL_KEYS)})")
    if "stop_id" in stop and not (isinstance(stop["stop_id"], str) and STOP_ID_RE.fullmatch(stop["stop_id"])):
        problems.append(f"stop_id {stop.get('stop_id')!r} is not a 32-digit lowercase hex id")
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
