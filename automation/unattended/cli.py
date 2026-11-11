"""Command line entry point: ``python3 -m automation.unattended <command>``.

Every command prints one JSON document. Read-only commands never write to GitHub. Commands
that write require ``--live``; without it they refuse and say so. On the real transport every
state command that admits or advances additionally needs ``--activation`` naming a current
run-bound activation authorization; without one it refuses ``activation-required`` before any
GitHub call, and no live run is created without one. Cleanup and ``status`` of a run that was
activated earlier work on the run's validated recorded binding without the file. ``status`` is a
locked state write (it records an observed expiry or clock regression durably) unless
``--read-only`` is passed.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import traceback
from datetime import timedelta
from pathlib import Path

from .activation import Activation, ledger_report, load_activation, load_clearance, parse_utc
from .backlog import Snapshot, load_tasks_index, take_snapshot, verify_mapping
from .coordinator import CLOCK_REGRESSION_TOLERANCE_MINUTES, Coordinator, check_cleanup_reason
from .eligibility import plan
from .errors import Refused, UnattendedError
from .github import GhCliTransport
from .policy import load_policy
from .probes import check_permissions, run_commands, write_probe
from .state import Store, utcnow, validate_run_id

# Every command that can reach a GitHub write, directly or through a fallback (authorize-repair may block).
WRITE_COMMANDS = {"reserve", "authorize-repair", "propose-evidence", "block", "cancel", "cancel-run", "resume", "rebase-revisions", "probe-write", "dismiss-claim"}


def _json(obj) -> None:
    print(json.dumps(obj, indent=1, sort_keys=True, default=str))


def _load_json_arg(value: str):
    """A JSON document given inline or as a file path. Unreadable input (bad JSON, an unreadable
    file, a path too long to test) is ``input-invalid`` inside the JSON error contract."""
    text = value
    try:
        looks_inline = value.lstrip()[:1] in ("{", "[", '"') or value.strip() in ("null", "true", "false")
        if not looks_inline:
            path = Path(value)
            if path.exists():
                text = path.read_text(encoding="utf-8")
    except (OSError, ValueError) as exc:  # ENAMETOOLONG, permission errors, embedded NUL
        raise UnattendedError(f"argument {value[:60]!r} is neither readable JSON nor a readable file: {exc}", code="input-invalid") from exc
    try:
        return json.loads(text)
    except ValueError as exc:
        raise UnattendedError(f"argument {value[:60]!r} is not valid JSON: {exc}", code="input-invalid") from exc


def _snapshot(args, transport, policy) -> Snapshot:
    if args.snapshot:
        try:
            return Snapshot.from_json(Path(args.snapshot).read_text(encoding="utf-8"))
        except (OSError, ValueError, KeyError, TypeError) as exc:  # TypeError: an older or foreign entry shape
            raise UnattendedError(f"snapshot {args.snapshot} unreadable: {exc}", code="input-invalid") from exc
    return take_snapshot(transport, policy.repo_slug, utcnow())


class _Parser(argparse.ArgumentParser):
    """Argument errors stay inside the JSON error contract (``input-invalid``, exit 3) instead of
    argparse's usage text and exit 2, which is the exit code of a *negative result* (``probe-write``
    not idempotent, ``plan``/``check-activation`` with problems) and must not be shared with a
    malformed call. ``--help`` still prints the usage and exits 0."""

    def error(self, message: str) -> None:  # type: ignore[override]
        raise UnattendedError(f"invalid arguments: {message}", code="input-invalid", usage=self.format_usage().strip())


def build_parser() -> argparse.ArgumentParser:
    p = _Parser(prog="python3 -m automation.unattended", description=__doc__)
    p.add_argument("--policy", default="automation/policy.toml")
    p.add_argument("--state-dir", default=".unattended-runs")
    p.add_argument("--run-id", default=None, help="run identifier (required for state commands)")
    p.add_argument("--repo-root", default=".")
    p.add_argument("--snapshot", default=None, help="use a saved snapshot JSON instead of reading GitHub")
    p.add_argument("--live", action="store_true", help=f"allow GitHub writes ({', '.join(sorted(WRITE_COMMANDS))})")
    p.add_argument("--activation", default=None, help="run-bound activation authorization TOML (see automation/examples/activation-om-01-02.candidate.toml); required on the real transport to create a live run and for every admitting/advancing command; cleanup and status of a run activated earlier work on its recorded binding without it; the shipped candidate is unapproved and refuses")
    sub = p.add_subparsers(dest="command", required=True, parser_class=_Parser)

    sub.add_parser("snapshot", help="read-only normalized backlog snapshot").add_argument("--out", default=None)
    vm = sub.add_parser("verify-mapping", help="read-only mapping verification (19/85/340, relationships)")
    vm.add_argument("--out", default=None)
    pl = sub.add_parser("plan", help="read-only eligibility decisions for the allowlist")
    pl.add_argument("--dry-run", action="store_true", default=True)
    pl.add_argument("--out", default=None)
    sub.add_parser("check-permissions", help="probe the minimum GitHub permissions")
    sub.add_parser("probe", help="run the policy environment probes")
    ck = sub.add_parser("check-activation", help="read-only: load --activation and report, for --run-id under --policy and --state-dir, whether it can create that run now (can_create) or, when the run already exists, whether it is still that run's current activation (current); also the use ledger root (one per user account and machine) and this document's record; touches no state, no GitHub. With --run-id, --expect create|advance is required (expect-required, exit 3, otherwise). Without --run-id it reports the policy digest and is current for nothing (exit 2)")
    ck.add_argument("--expect", choices=["create", "advance"], default=None, help="required with --run-id: exit 0 only for this answer: create = can_create (a fresh run may be reserved now), advance = the run exists and is current (it may advance under this document); exit 2 otherwise")
    pw = sub.add_parser("probe-write", help="bounded live write probe on an engineering-automation issue")
    pw.add_argument("--issue", type=int, required=True)

    evidence_help = "JSON for the ACTIVE execution: normalized {taskId, runId, status} or task_status-shaped {taskId, workState: result_available, hasPendingChildRuns: false, latestTerminalRunId, latestTerminalStatus} (childRunId/status/summary are stale and ignored); interrupted/failed/cancelled are terminal for release/cleanup only, never a success: only a completed/result_available record of the bound (task, run), in the relevant role and linked to the selected authorization, lets record-head/run-checks/authorize-review/authorize-repair/record-review/propose-evidence/resume advance, on the direct path, after record-task-terminal, after an upgrade and on restart"
    rv0 = sub.add_parser("reserve", help="admit a dispatchable story and authorize its implementer task BEFORE delegating it")
    rv0.add_argument("story"); rv0.add_argument("--baseline", required=True)
    bd = sub.add_parser("bind-receipt", help="bind the delegated task receipt to the exact authorization its task was launched for (implementation and review receipts need --worktree/--branch: the task's own checkout; a reviewer in the implementer's worktree is refused)")
    bd.add_argument("story"); bd.add_argument("--receipt", required=True); bd.add_argument("--worktree", default=None); bd.add_argument("--branch", default=None)
    bd.add_argument("--authorization", default=None, help="id of the authorization the task was launched for (from reserve / authorize-review / authorize-repair); must match the story's unresolved authorization")
    bd.add_argument("--for-cleanup", action="store_true", help="bind the receipt for cleanup only (slot spent, task owned, phase unchanged, no work authorized; exits 3 with cleanup-requested): the way to record a launched task when the activation file is lost for good on a run that is not stopped; needs --reason (journaled) and is refused while the run's current activation is presented (cleanup-not-needed)")
    bd.add_argument("--reason", default=None, help="why the receipt is bound for cleanup only (required with --for-cleanup, journaled)")
    rt = sub.add_parser("record-task-terminal", help="release the active task with its terminal evidence; changes nothing else"); rt.add_argument("story"); rt.add_argument("--task-evidence", required=True, help=evidence_help)
    no_launch_help = 'JSON {"authorization": "<id>", "reason": "..."}: the coordinator attests that no task was launched for exactly that unresolved authorization'
    nl = sub.add_parser("record-no-launch", help="resolve an unresolved authorization by attesting that no task was launched for it; changes nothing else"); nl.add_argument("story"); nl.add_argument("--no-launch", required=True, help=no_launch_help)
    rh = sub.add_parser("record-head", help="record the implementer's exact commit (its terminal evidence is required while it is active)"); rh.add_argument("story"); rh.add_argument("--sha", required=True); rh.add_argument("--task-evidence", default=None, help=evidence_help)
    rc = sub.add_parser("run-checks", help="execute the full configured check set on the exact claimed HEAD and record it"); rc.add_argument("story"); rc.add_argument("--sha", required=True); rc.add_argument("--cwd", required=True)
    ar = sub.add_parser("authorize-review", help="authorize the reviewer task at the checked commit BEFORE delegating it"); ar.add_argument("story"); ar.add_argument("--sha", required=True)
    rv = sub.add_parser("record-review", help="record the reviewer's verdict (its terminal evidence is required while it is active)"); rv.add_argument("story"); rv.add_argument("--sha", required=True); rv.add_argument("--verdict", choices=["approved", "changes-requested"], required=True); rv.add_argument("--report", required=True); rv.add_argument("--task-evidence", default=None, help=evidence_help)
    rp = sub.add_parser("authorize-repair", help="authorize a budgeted repair task BEFORE delegating it (blocks when rounds are exhausted)"); rp.add_argument("story")
    pe = sub.add_parser("propose-evidence"); pe.add_argument("story"); pe.add_argument("--sha", required=True); pe.add_argument("--pr", type=int, required=True); pe.add_argument("--task", action="append", default=[]); pe.add_argument("--summary", required=True)
    b = sub.add_parser("block"); b.add_argument("story"); b.add_argument("--reason", required=True); b.add_argument("--task-evidence", default=None, help=evidence_help); b.add_argument("--no-launch", default=None, help=no_launch_help)
    ca = sub.add_parser("cancel"); ca.add_argument("story"); ca.add_argument("--reason", required=True); ca.add_argument("--task-evidence", default=None, help=evidence_help); ca.add_argument("--no-launch", default=None, help=no_launch_help)
    cr = sub.add_parser("cancel-run"); cr.add_argument("--reason", required=True); cr.add_argument("--task-evidence", default=None, help="JSON {story: {taskId, status}}"); cr.add_argument("--no-launch", default=None, help='JSON {story: {"authorization": "<id>", "reason": "..."}}')
    rr = sub.add_parser("reconcile-retained-execution", help="audited cleanup: resolve a revoked repair authorization whose task ran as a new run of the retained owner task but was never bound (no re-authorization, approval or admission)")
    rr.add_argument("story"); rr.add_argument("--authorization", required=True); rr.add_argument("--receipt", required=True, help="JSON receipt of the retained owner task with its runId (and provider/model/options; optional worktree/branch)"); rr.add_argument("--task-evidence", required=True, help=evidence_help); rr.add_argument("--reason", required=True); rr.add_argument("--provenance", required=True, help="who observed the terminal evidence and how (e.g. original coordinator task_status snapshot, user-supplied)")
    rs = sub.add_parser("resume"); rs.add_argument("story")
    rb = sub.add_parser("rebase-revisions", help="explicitly accept changed GitHub revisions after human verification"); rb.add_argument("story"); rb.add_argument("--reason", required=True)
    cc = sub.add_parser("clear-clock-regression", help=f"owner action by convention, journaled: clear a recorded clock-regression stop under the presented, current activation and a clearance naming exactly that stop (--clearance). Owner-only is a trusted-machine convention, not a control: every clearance field is readable by the unattended loop, so the tool cannot tell who wrote it; it refuses a clearance inside --state-dir, inside any git work tree (the repository's, the tool's, a delegated task's worktree) or where git cannot tell (clearance-invalid), comparing paths without regard to case. Refuses while the clock is more than {CLOCK_REGRESSION_TOLERANCE_MINUTES} minutes (the tolerance) behind the run's high-water mark and judges the wall clock on that mark; at most once per run; an activation-expired stop is never cleared")
    cc.add_argument("--clearance", required=True, help="TOML file with exactly run_id, activation_id, approver, stop_observed_at and reason (see docs/unattended-execution.md), kept outside --state-dir and outside every git work tree")
    st = sub.add_parser("status", help="run report of an existing run; a locked state write by default (records an observed expiry or clock regression durably)")
    st.add_argument("--read-only", action="store_true", help="monitoring form: the run is opened and reported without the store lock and without creating or writing anything; a would-be stop is reported as would_stop, never recorded")
    dc = sub.add_parser("dismiss-claim", help="owner action: post a journaled dismissal of a stray or forged claim marker (by comment id) so it no longer blocks admission under this identity; never dismisses this run's own claim nor a claim a run under this state directory still owns; needs --live, the --run-id of an existing run and (live transport) its current activation (--activation), which journals it")
    dc.add_argument("--issue", type=int, required=True); dc.add_argument("--comment-id", type=int, required=True); dc.add_argument("--reason", required=True)
    dc.add_argument("--force", action="store_true", help="dismiss a claim that no run under --state-dir proves finished (its coordinator may still be running elsewhere, however old the claim: a run past its wall clock still owns its story until its task finishes); --reason must attest that it is dead")
    return p


class WorkTreeUnknown(Exception):
    """git could not say whether a path is inside a work tree (it failed, timed out, or refused
    for another reason than "not a git repository", such as dubious ownership)."""


def _git_env() -> dict[str, str]:
    """The environment git runs in for the work-tree rule: no inherited ``GIT_*`` variable (``GIT_DIR``,
    ``GIT_WORK_TREE``, ``GIT_CEILING_DIRECTORIES``... could make git answer "not a git repository" inside a
    work tree) and the C locale, so the one message that allows is never translated."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(LC_ALL="C", LANGUAGE="")
    return env


def _work_tree(path) -> str | None:
    """The git work tree containing ``path``; ``None`` only when git answers that it is not inside
    one (exit 128 with "not a git repository"). Any other outcome (git missing, a timeout, another
    exit code or message, an empty answer) raises :class:`WorkTreeUnknown`: a rule that depends on
    git never passes because git failed."""
    try:
        out = subprocess.run(["git", "-C", str(path), "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=30, env=_git_env())
    except (OSError, subprocess.SubprocessError) as exc:
        raise WorkTreeUnknown(f"git could not be run on {path}: {type(exc).__name__}: {exc}") from exc
    if out.returncode == 0 and out.stdout.strip():
        return out.stdout.strip()
    if out.returncode == 128 and "not a git repository" in out.stderr:
        return None
    raise WorkTreeUnknown(f"git rev-parse on {path} exited {out.returncode}: {(out.stderr or out.stdout).strip()[:300]}")


def _clearance_forbidden(args) -> dict[str, str | None]:
    """Where a clearance is never read from: the state directory and every git work tree, where
    the unattended loop and its delegated tasks work: the one the clearance itself lies in (a
    delegated task's worktree included), ``--repo-root``'s and the one this tool runs from. When git
    cannot answer for any of them the clear refuses ``clearance-invalid`` (cannot determine the work
    tree): the rule never passes because git failed."""
    clearance = Path(os.path.realpath(args.clearance))
    if not clearance.is_file():  # a mistyped path is reported as what it is, before git is asked about a directory that may not exist
        raise Refused(f"cannot read clearance {args.clearance}: no such file", code="clearance-invalid", path=str(clearance))
    # the named places first, so a refusal says the most specific one; the clearance's own work tree covers every other
    places = {"--repo-root": Path(args.repo_root), "the tool's own location": Path(__file__).resolve().parent, "the clearance's own directory": clearance.parent}
    roots: dict[str, str | None] = {"--state-dir": args.state_dir}
    labels = {"--repo-root": "the repository work tree (--repo-root)", "the tool's own location": "the work tree of this tool", "the clearance's own directory": "a git work tree (a delegated task's worktree, or any other checkout)"}
    for name, where in places.items():
        try:
            roots[labels[name]] = _work_tree(where)
        except WorkTreeUnknown as exc:
            raise Refused(f"clear-clock-regression: cannot determine the work tree of {name} ({where}): {exc}; a clearance is refused inside any git work tree, so when git cannot answer nothing is cleared (fix git, e.g. safe.directory, or keep the clearance where git answers)", code="clearance-invalid", path=str(clearance), unknown=name) from exc
    return roots


REPORT_KEYS = ("activation", "approved", "run_id", "policy_digest", "bound_digest", "run_exists", "current", "can_create", "stop", "stops", "problems", "creation_problems", "used", "ledger_root", "expect")


def _activation_report(**fields) -> dict:
    """The one shape of every ``check-activation`` report: every key of :data:`REPORT_KEYS`, with
    ``None`` for what does not apply (no document presented, no run looked up), so a script reads
    the same keys whether or not the file was forgotten."""
    unknown = set(fields) - set(REPORT_KEYS)
    if unknown:  # pragma: no cover - a programming error, not an input
        raise ValueError(f"unknown report keys {sorted(unknown)}")
    return {key: fields.get(key) for key in REPORT_KEYS}


def _check_activation(args, policy, activation) -> tuple[dict, bool]:
    """The ``check-activation`` report and whether it is a go. Two questions with two answers:
    ``can_create`` (may this document create ``--run-id`` now: current, cited, unused, with the
    whole wall-clock budget inside its window) and, for a run that already exists under
    ``--state-dir``, ``current`` (is this document that run's activation and still current for
    advancing: what every advancing operation checks). For a run that does not exist yet the two
    are the same. A run that exists is also not current once it is cancelled, past its wall
    clock, under a recorded stop, or when the host clock reads more than the regression tolerance
    behind the run's high-water mark (the next locked operation would record ``clock-regression``).
    A run that does not exist but whose artifacts are retained cannot be created
    (``run-metadata-missing``). A run record that does not load is reported, never read as "no
    run"; without ``--run-id`` no run is looked up and the document is current for nothing."""
    now, run, problems = utcnow(), None, []
    store = None
    if args.run_id:
        try:
            store = Store(Path(args.state_dir), args.run_id)
            run = store.load_run()
        except UnattendedError as exc:
            problems.append((exc.code, str(exc)))
    bound = run.policy_digest if run is not None else None
    try:
        creation = activation.creation_problems(policy, args.run_id, now, state_dir=args.state_dir)
    except UnattendedError as exc:  # the ledger itself cannot be consulted (no account entry): a coded problem, never a crash
        creation = [(exc.code, str(exc))]
    if run is None and store is not None:
        retained = store.retained_artifacts()
        if retained:
            creation.append(("run-metadata-missing", f"run {args.run_id} has no run.json under {args.state_dir} but {len(retained)} run artifact(s) are retained ({', '.join(retained[:4])}); reserve refuses to create a run around them"))
    if run is not None:
        creation.append(("activation-used", f"run {args.run_id} already exists under {args.state_dir}; a run is created once"))
        problems += activation.problems(policy, args.run_id, now, bound_digest=bound)
        if run.environment == "live" and not activation.matches(run.activation):
            problems.append(("activation-mismatch", f"run {args.run_id} was created under activation {(run.activation or {}).get('id')!r}, not this document ({activation.id}, digest {activation.digest[:12]})"))
        if run.activation_stop is not None:
            problems.append((run.activation_stop["code"], f"the run carries a recorded stop: {run.activation_stop['message']}"))
        elif run.environment == "live" and isinstance(run.activation, dict):
            mark = run.last_observed_at or run.activation.get("validated_at")
            try:
                behind = parse_utc(mark) - timedelta(minutes=CLOCK_REGRESSION_TOLERANCE_MINUTES) > parse_utc(now)
            except (TypeError, ValueError, OverflowError) as exc:  # fail closed: an unreadable mark is never "not behind"
                behind = False
                problems.append(("run-state-invalid", f"the run's high-water mark {mark!r} cannot be compared with the clock ({exc}); the clock-regression check cannot be made"))
            if behind:
                problems.append(("clock-regression", f"the host clock reads {now}, more than {CLOCK_REGRESSION_TOLERANCE_MINUTES} minutes behind the run's latest observation {mark}; the next locked operation records a durable clock-regression stop (wait for the clock to catch up)"))
        if run.cancelled:
            problems.append(("run-cancelled", f"run {args.run_id} is cancelled ({run.stop_reason}); it advances nothing"))
        else:
            # judged like every locked operation: on the later of the clock and the run's high-water mark, so a clock still
            # within the regression tolerance behind the mark never reports a run current that already used its budget
            judged = parse_utc(now)
            if run.last_observed_at is not None:
                judged = max(judged, parse_utc(run.last_observed_at))
            if judged - parse_utc(run.started_at) > timedelta(minutes=policy.max_wall_clock_minutes):
                problems.append(("wall-clock-exceeded", f"run {args.run_id} started at {run.started_at} and is past its wall-clock budget of {policy.max_wall_clock_minutes} minutes (judged at {judged.isoformat().replace('+00:00', 'Z')}, the later of the clock and the run's high-water mark); it advances nothing"))
    elif not problems:
        problems = list(creation)
    ledger = ledger_report(activation.digest, activation.path)
    report = _activation_report(activation=activation.binding(), approved=activation.approved, run_id=args.run_id, policy_digest=policy.digest, bound_digest=bound, run_exists=run is not None,
                                current=not problems, can_create=run is None and not problems and not creation, stop=activation.stop_code(problems), stops=Activation.stop_codes(problems), problems=[m for _, m in problems],
                                creation_problems=[m for _, m in creation], used=ledger["record"], ledger_root=ledger["root"], expect=getattr(args, "expect", None))
    expect = getattr(args, "expect", None)
    if expect == "create":
        go = report["can_create"]
    elif expect == "advance":
        go = report["run_exists"] and report["current"]  # advancing needs a run to advance
    else:
        go = report["current"]  # without --run-id (no --expect needed): current for nothing, so never a go
    return report, go


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)  # inside the contract: a malformed call is one JSON document with exit 3, never usage text with exit 2
        policy = load_policy(Path(args.policy))
        activation = load_activation(Path(args.activation)) if args.activation else None
        if args.command == "check-activation":
            if args.run_id and not args.expect:  # exit 0 must answer one question: may I create this run, or may it advance
                raise UnattendedError("check-activation --run-id needs --expect create|advance: without it exit 0 would not say whether the run may be created or may advance (a mistyped or new run id would read as current)", code="expect-required")
            if args.expect and not args.run_id:  # an expectation about no run would be answered by nothing
                raise UnattendedError("check-activation --expect needs --run-id: create and advance are questions about one run", code="expect-required")
            if activation is None:  # the digest an activation must name is readable before any activation exists; nothing is current without one
                _json(_activation_report(run_id=args.run_id, policy_digest=policy.digest, current=False, can_create=False, stop="activation-required", stops=["activation-required"], problems=["no activation presented (--activation); only the policy digest is reported"], expect=args.expect))
                return 2
            report, go = _check_activation(args, policy, activation)
            _json(report)
            return 0 if go else 2
        transport = GhCliTransport(policy.owner, policy.repo, policy.project_owner, policy.project_number)
        if args.command in WRITE_COMMANDS and not args.live:
            raise UnattendedError(f"{args.command} writes to GitHub; pass --live to confirm")
        if args.command == "bind-receipt":
            check_cleanup_reason(args.reason, bool(args.for_cleanup))  # a malformed pairing is refused before any run is opened or any state written
        if args.command == "snapshot":
            snap = _snapshot(args, transport, policy)
            if args.out:
                Path(args.out).write_text(snap.to_json(), encoding="utf-8")
            _json({"taken_at": snap.taken_at, "entries": len(snap.entries), "out": args.out})
            return 0
        if args.command == "verify-mapping":
            report = verify_mapping(_snapshot(args, transport, policy), load_tasks_index(Path(args.repo_root)))
            if args.out:
                Path(args.out).write_text(json.dumps(report, indent=1, sort_keys=True), encoding="utf-8")
            _json({k: v for k, v in report.items() if k != "mapping"})
            return 0 if report["ok"] else 2
        if args.command == "plan":
            decisions = [d.as_dict() for d in plan(_snapshot(args, transport, policy), policy)]
            out = {"dry_run": True, "writes": 0, "allow": list(policy.allow), "decisions": decisions}
            if args.out:
                Path(args.out).write_text(json.dumps(out, indent=1, sort_keys=True), encoding="utf-8")
            _json(out)
            return 0
        if args.command == "check-permissions":
            report = check_permissions(policy.owner, policy.repo, policy.project_owner, policy.project_number)
            _json(report)
            return 0 if report["unattended_activation_allowed"] else 2
        if args.command == "probe":
            results = run_commands(list(policy.probe_commands), args.repo_root, policy.probe_timeout_seconds)
            ok = bool(results) and all(r["returncode"] == 0 for r in results) and len(results) == len(policy.probe_commands)
            _json({"ok": ok, "results": results})
            return 0 if ok else 2
        if args.command == "probe-write":
            if not args.run_id:
                raise UnattendedError("probe-write needs --run-id: the probe is idempotent only for a fixed identity (a second call with the same --run-id must find the first marker)", code="run-id-required")
            report = write_probe(transport, args.issue, validate_run_id(args.run_id), utcnow())
            _json(report)
            return 0 if report["idempotent"] else 2
        if not args.run_id:
            raise UnattendedError("--run-id is required for state commands", code="run-id-required")
        # Only an admitting command creates a run: a report or a cleanup command on a run that does not exist refuses
        # run-not-found and never starts a run or spends an activation. status --read-only opens without the lock.
        coordinator = Coordinator(transport, policy, Store(Path(args.state_dir), args.run_id), live=bool(args.live), activation=activation,
                                  create=args.command == "reserve", read_only=args.command == "status" and bool(args.read_only))
        if args.command == "reserve":
            with coordinator.operation():
                coordinator.require_activation("reserve")  # before any GitHub read on a live transport, under the lock
            state = coordinator.reserve(args.story, _snapshot(args, transport, policy), args.baseline)
        elif args.command == "bind-receipt":
            state = coordinator.bind_receipt(args.story, _load_json_arg(args.receipt), args.worktree, args.branch, authorization=args.authorization, for_cleanup=bool(args.for_cleanup), reason=args.reason)
        elif args.command == "record-task-terminal":
            state = coordinator.record_task_terminal(args.story, _load_json_arg(args.task_evidence))
        elif args.command == "record-no-launch":
            state = coordinator.record_no_launch(args.story, _load_json_arg(args.no_launch))
        elif args.command == "record-head":
            state = coordinator.record_head(args.story, args.sha, _load_json_arg(args.task_evidence) if args.task_evidence else None)
        elif args.command == "run-checks":
            state = coordinator.run_checks(args.story, args.sha, args.cwd)
        elif args.command == "authorize-review":
            state = coordinator.authorize_review(args.story, args.sha)
        elif args.command == "record-review":
            state = coordinator.record_review(args.story, args.sha, args.verdict, args.report, _load_json_arg(args.task_evidence) if args.task_evidence else None)
        elif args.command == "authorize-repair":
            state = coordinator.authorize_repair(args.story)
        elif args.command == "propose-evidence":
            state = coordinator.propose_evidence(args.story, args.sha, args.pr, args.task, args.summary)
        elif args.command == "block":
            state = coordinator.block(args.story, args.reason, _load_json_arg(args.task_evidence) if args.task_evidence else None, _load_json_arg(args.no_launch) if args.no_launch else None)
        elif args.command == "cancel":
            state = coordinator.cancel(args.story, args.reason, _load_json_arg(args.task_evidence) if args.task_evidence else None, _load_json_arg(args.no_launch) if args.no_launch else None)
        elif args.command == "cancel-run":
            _json(coordinator.cancel_run(args.reason, _load_json_arg(args.task_evidence) if args.task_evidence else None, _load_json_arg(args.no_launch) if args.no_launch else None))
            return 0
        elif args.command == "resume":
            state = coordinator.resume(args.story)
        elif args.command == "reconcile-retained-execution":
            state = coordinator.reconcile_retained_execution(args.story, args.authorization, _load_json_arg(args.receipt), _load_json_arg(args.task_evidence), args.reason, args.provenance)
        elif args.command == "rebase-revisions":
            state = coordinator.rebase_revisions(args.story, args.reason)
        elif args.command == "clear-clock-regression":
            _json(coordinator.clear_clock_regression(load_clearance(Path(args.clearance), refuse_inside=_clearance_forbidden(args))))
            return 0
        elif args.command == "status":
            _json(coordinator.status(read_only=bool(args.read_only)))
            return 0
        elif args.command == "dismiss-claim":
            _json(coordinator.dismiss_claim(args.issue, args.comment_id, args.reason, force=args.force))
            return 0
        else:  # pragma: no cover
            raise UnattendedError(f"unknown command {args.command}")
        _json(state.to_dict())
        return 0
    except UnattendedError as exc:
        _json({"error": exc.as_dict()})
        return 3
    except Exception as exc:  # noqa: BLE001 - the contract is one JSON document, never a bare traceback
        # exit 4 tells a scripted caller apart from a refusal (3): the tool crashed, nothing was decided
        _json({"error": {"code": "internal", "message": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc().splitlines()[-6:]}})
        return 4


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
