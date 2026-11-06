"""Command line entry point: ``python3 -m automation.unattended <command>``.

Every command prints one JSON document. Read-only commands never write to GitHub. Commands
that write require ``--live``; without it they refuse and say so.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .backlog import Snapshot, load_tasks_index, take_snapshot, verify_mapping
from .coordinator import Coordinator
from .eligibility import plan
from .errors import UnattendedError
from .github import GhCliTransport
from .policy import load_policy
from .probes import check_permissions, run_commands, write_probe
from .state import Store, utcnow

# Every command that can reach a GitHub write, directly or through a fallback (repair may block).
WRITE_COMMANDS = {"claim", "repair", "propose-evidence", "block", "cancel", "cancel-run", "resume", "rebase-revisions", "probe-write"}


def _json(obj) -> None:
    print(json.dumps(obj, indent=1, sort_keys=True, default=str))


def _load_json_arg(value: str) -> dict:
    path = Path(value)
    text = path.read_text(encoding="utf-8") if path.exists() else value
    return json.loads(text)


def _snapshot(args, transport, policy) -> Snapshot:
    if args.snapshot:
        try:
            return Snapshot.from_json(Path(args.snapshot).read_text(encoding="utf-8"))
        except (OSError, ValueError, KeyError) as exc:
            raise UnattendedError(f"snapshot {args.snapshot} unreadable: {exc}") from exc
    return take_snapshot(transport, policy.repo_slug, utcnow())


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python3 -m automation.unattended", description=__doc__)
    p.add_argument("--policy", default="automation/policy.toml")
    p.add_argument("--state-dir", default=".unattended-runs")
    p.add_argument("--run-id", default=None, help="run identifier (required for state commands)")
    p.add_argument("--repo-root", default=".")
    p.add_argument("--snapshot", default=None, help="use a saved snapshot JSON instead of reading GitHub")
    p.add_argument("--live", action="store_true", help="allow GitHub writes (claim, block, cancel, resume, propose-evidence, probe-write)")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("snapshot", help="read-only normalized backlog snapshot").add_argument("--out", default=None)
    vm = sub.add_parser("verify-mapping", help="read-only mapping verification (19/85/340, relationships)")
    vm.add_argument("--out", default=None)
    pl = sub.add_parser("plan", help="read-only eligibility decisions for the allowlist")
    pl.add_argument("--dry-run", action="store_true", default=True)
    pl.add_argument("--out", default=None)
    sub.add_parser("check-permissions", help="probe the minimum GitHub permissions")
    sub.add_parser("probe", help="run the policy environment probes")
    pw = sub.add_parser("probe-write", help="bounded live write probe on an engineering-automation issue")
    pw.add_argument("--issue", type=int, required=True)

    c = sub.add_parser("claim", help="claim a dispatchable story for one implementer")
    c.add_argument("story"); c.add_argument("--receipt", required=True); c.add_argument("--worktree", required=True); c.add_argument("--branch", required=True); c.add_argument("--baseline", required=True)
    rh = sub.add_parser("record-head"); rh.add_argument("story"); rh.add_argument("--sha", required=True)
    rc = sub.add_parser("run-checks", help="execute the full configured check set on the exact claimed HEAD and record it"); rc.add_argument("story"); rc.add_argument("--sha", required=True); rc.add_argument("--cwd", required=True)
    rq = sub.add_parser("request-review"); rq.add_argument("story"); rq.add_argument("--sha", required=True); rq.add_argument("--receipt", required=True)
    rv = sub.add_parser("record-review"); rv.add_argument("story"); rv.add_argument("--sha", required=True); rv.add_argument("--verdict", choices=["approved", "changes-requested"], required=True); rv.add_argument("--report", required=True)
    rp = sub.add_parser("repair"); rp.add_argument("story"); rp.add_argument("--receipt", required=True)
    pe = sub.add_parser("propose-evidence"); pe.add_argument("story"); pe.add_argument("--sha", required=True); pe.add_argument("--pr", type=int, required=True); pe.add_argument("--task", action="append", default=[]); pe.add_argument("--summary", required=True)
    b = sub.add_parser("block"); b.add_argument("story"); b.add_argument("--reason", required=True)
    ca = sub.add_parser("cancel"); ca.add_argument("story"); ca.add_argument("--reason", required=True)
    cr = sub.add_parser("cancel-run"); cr.add_argument("--reason", required=True)
    rs = sub.add_parser("resume"); rs.add_argument("story")
    rb = sub.add_parser("rebase-revisions", help="explicitly accept changed GitHub revisions after human verification"); rb.add_argument("story"); rb.add_argument("--reason", required=True)
    sub.add_parser("status")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        policy = load_policy(Path(args.policy))
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
            _json(write_probe(transport, args.issue, args.run_id or f"probe-{utcnow()}", utcnow()))
            return 0
        if not args.run_id:
            raise UnattendedError("--run-id is required for state commands")
        coordinator = Coordinator(transport, policy, Store(Path(args.state_dir), args.run_id), live=bool(args.live))
        if args.command == "claim":
            state = coordinator.claim(args.story, _snapshot(args, transport, policy), _load_json_arg(args.receipt), args.worktree, args.branch, args.baseline)
        elif args.command == "record-head":
            state = coordinator.record_head(args.story, args.sha)
        elif args.command == "run-checks":
            state = coordinator.run_checks(args.story, args.sha, args.cwd)
        elif args.command == "request-review":
            state = coordinator.request_review(args.story, args.sha, _load_json_arg(args.receipt))
        elif args.command == "record-review":
            state = coordinator.record_review(args.story, args.sha, args.verdict, args.report)
        elif args.command == "repair":
            state = coordinator.repair(args.story, _load_json_arg(args.receipt))
        elif args.command == "propose-evidence":
            state = coordinator.propose_evidence(args.story, args.sha, args.pr, args.task, args.summary)
        elif args.command == "block":
            state = coordinator.block(args.story, args.reason)
        elif args.command == "cancel":
            state = coordinator.cancel(args.story, args.reason)
        elif args.command == "cancel-run":
            _json({"cancelled": [s.to_dict() for s in coordinator.cancel_run(args.reason)]})
            return 0
        elif args.command == "resume":
            state = coordinator.resume(args.story)
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


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
