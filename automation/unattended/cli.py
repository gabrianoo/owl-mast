"""Command line entry point: ``python3 -m automation.unattended <command>``.

Every command prints one JSON document. Read-only commands never write to GitHub. Commands
that write require ``--live``; without it they refuse and say so. On the real transport every
state command that admits or advances additionally needs ``--activation`` naming a current
run-bound activation authorization; without one it refuses ``activation-required`` before any
GitHub call, and no live run is created without one. Cleanup and ``status`` of a run that was
activated earlier work on the run's validated recorded binding without the file.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

from .activation import load_activation
from .backlog import Snapshot, load_tasks_index, take_snapshot, verify_mapping
from .coordinator import Coordinator
from .eligibility import plan
from .errors import UnattendedError
from .github import GhCliTransport
from .policy import load_policy
from .probes import check_permissions, run_commands, write_probe
from .state import Store, utcnow, validate_run_id

# Every command that can reach a GitHub write, directly or through a fallback (authorize-repair may block).
WRITE_COMMANDS = {"reserve", "authorize-repair", "propose-evidence", "block", "cancel", "cancel-run", "resume", "rebase-revisions", "probe-write"}


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
    p.add_argument("--live", action="store_true", help="allow GitHub writes (reserve, authorize-repair, block, cancel, cancel-run, resume, rebase-revisions, probe-write)")
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
    sub.add_parser("check-activation", help="read-only: load --activation and report whether it currently authorizes --run-id under --policy (touches no state, no GitHub)")
    pw = sub.add_parser("probe-write", help="bounded live write probe on an engineering-automation issue")
    pw.add_argument("--issue", type=int, required=True)

    evidence_help = "JSON for the ACTIVE execution: normalized {taskId, runId, status} or task_status-shaped {taskId, workState: result_available, hasPendingChildRuns: false, latestTerminalRunId, latestTerminalStatus} (childRunId/status/summary are stale and ignored); interrupted/failed/cancelled are terminal for release/cleanup only, never a success: only a completed/result_available record of the bound (task, run), in the relevant role and linked to the selected authorization, lets record-head/run-checks/authorize-review/authorize-repair/record-review/propose-evidence/resume advance, on the direct path, after record-task-terminal, after an upgrade and on restart"
    rv0 = sub.add_parser("reserve", help="admit a dispatchable story and authorize its implementer task BEFORE delegating it")
    rv0.add_argument("story"); rv0.add_argument("--baseline", required=True)
    bd = sub.add_parser("bind-receipt", help="bind the delegated task receipt to the exact authorization its task was launched for (implementation and review receipts need --worktree/--branch: the task's own checkout; a reviewer in the implementer's worktree is refused)")
    bd.add_argument("story"); bd.add_argument("--receipt", required=True); bd.add_argument("--worktree", default=None); bd.add_argument("--branch", default=None)
    bd.add_argument("--authorization", default=None, help="id of the authorization the task was launched for (from reserve / authorize-review / authorize-repair); must match the story's unresolved authorization")
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
    sub.add_parser("status")
    return p


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)  # inside the contract: a malformed call is one JSON document with exit 3, never usage text with exit 2
        policy = load_policy(Path(args.policy))
        activation = load_activation(Path(args.activation)) if args.activation else None
        if args.command == "check-activation":
            if activation is None:
                raise UnattendedError("check-activation needs --activation", code="activation-required")
            problems = activation.problems(policy, args.run_id, utcnow())
            _json({"activation": activation.binding(), "approved": activation.approved, "run_id": args.run_id, "policy_digest": policy.digest, "current": not problems, "stop": activation.stop_code(problems), "problems": [m for _, m in problems]})
            return 0 if not problems else 2
        transport = GhCliTransport(policy.owner, policy.repo, policy.project_owner, policy.project_number)
        if args.command in WRITE_COMMANDS and not args.live:
            raise UnattendedError(f"{args.command} writes to GitHub; pass --live to confirm")
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
        coordinator = Coordinator(transport, policy, Store(Path(args.state_dir), args.run_id), live=bool(args.live), activation=activation)
        if args.command == "reserve":
            with coordinator.operation():
                coordinator.require_activation("reserve")  # before any GitHub read on a live transport, under the lock
            state = coordinator.reserve(args.story, _snapshot(args, transport, policy), args.baseline)
        elif args.command == "bind-receipt":
            state = coordinator.bind_receipt(args.story, _load_json_arg(args.receipt), args.worktree, args.branch, authorization=args.authorization)
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
        elif args.command == "status":
            _json(coordinator.status())
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
