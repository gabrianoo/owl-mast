"""Manual-step synthetic lifecycle smoke helper (engineering-only, no network).

Each invocation performs ONE operation against temporary, isolated, persisted state under
``--dir``: a JSON-persisted in-memory GitHub transport (no network, fixture environment) and
the coordinator's own run store. The coordinator (a human or the T3 coordinator thread)
calls the operations in order between real ``delegate_task`` turns and supplies the
receipts, terminal evidence and worktree it actually obtained from T3. The helper never
fabricates a receipt or evidence: whatever is passed in is recorded verbatim with its
``source`` label, and the published smoke counts as real only when those inputs came from
real T3 tasks. Unit tests drive it with fixture inputs and are labelled fixtures.

Story namespace: a fixture-only epic E99 with story OM-99.01, never a product identity.
There is no internal delegation, waiting or looping here.

``--dir`` is a global option and comes BEFORE the operation:

    python3 -m automation.tests.lifecycle_smoke --dir D prepare   [--worktree W --branch B] [--check-command C ...]
    python3 -m automation.tests.lifecycle_smoke --dir D bind      --receipt R.json --worktree W --branch B [--authorization ID] --source real|fixture
    python3 -m automation.tests.lifecycle_smoke --dir D head      --sha SHA --task-evidence E.json --source real|fixture
    python3 -m automation.tests.lifecycle_smoke --dir D check     --sha SHA
    python3 -m automation.tests.lifecycle_smoke --dir D authorize-review --sha SHA
    python3 -m automation.tests.lifecycle_smoke --dir D bind      --receipt R.json --worktree W2 --branch B [--authorization ID] --source real|fixture      (reviewer: its OWN checkout, never the implementer's)
    python3 -m automation.tests.lifecycle_smoke --dir D review    --sha SHA --verdict approved|changes-requested --report REF --task-evidence E.json --source real|fixture
    python3 -m automation.tests.lifecycle_smoke --dir D cancel    --reason R [--task-evidence E.json] [--no-launch N.json] --source real|fixture
    python3 -m automation.tests.lifecycle_smoke --dir D terminal  --task-evidence E.json --source real|fixture
    python3 -m automation.tests.lifecycle_smoke --dir D restart             (fresh process: reload persisted transport and state, resume)
    python3 -m automation.tests.lifecycle_smoke --dir D status
    python3 -m automation.tests.lifecycle_smoke --dir D reconcile --authorization ID --receipt R.json --task-evidence E.json --reason R --provenance P --source real|fixture

Receipts and terminal evidence identify an execution as a ``(taskId, runId)`` pair; see
``automation/unattended/receipts.py`` and ``coordinator.normalize_task_evidence`` for the
canonical shapes. ``--run-id`` selects the persisted run (default ``smoke-run``); a legacy
state directory holding ``fixture-transport.pickle`` instead of ``transport.json`` is loaded
read-only from that pickle (the parent's isolated copy of a historical run).

``status.evidence_class`` only summarizes the *declared* provenance of the inputs supplied
so far (``real`` when every input was declared real); it says nothing about whether those
inputs were accepted or whether the lifecycle succeeded. The story phase, the log and the
refusals are the outcome; qualification is the published smoke plus its independent review.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from automation.tests.fake_transport import CrashAfterEffect, FakeTransport, issue
from automation.tests.support import make_git_repo, write_policy
from automation.unattended.backlog import take_snapshot
from automation.unattended.coordinator import Coordinator, git_worktree_check
from automation.unattended.errors import UnattendedError
from automation.unattended.github import Comment, IssueRecord, ProjectItem, PullRequestRecord
from automation.unattended.policy import load_policy
from automation.unattended.state import Store, atomic_write_text, utcnow

STORY = "OM-99.01"
EPIC = "E99"
RUN_ID = "smoke-run"
DEFAULT_CHECKS = ["git diff --check", "python3 -c 'import sys; print(sys.version)'"]
SOURCES = ("real", "fixture")


class PersistedFakeTransport(FakeTransport):
    """``FakeTransport`` whose issues, items, comments and PRs live in a JSON file, so that a
    later process (restart) sees exactly what an earlier one left. Fixture environment:
    ``live`` stays false, there is no network."""

    def __init__(self, path: Path):
        super().__init__()
        self.path = path
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            self.issues = {int(k): IssueRecord(**{**v, "labels": tuple(v["labels"])}) for k, v in raw["issues"].items()}
            self.items = {k: ProjectItem(**v) for k, v in raw["items"].items()}
            self.comments = {int(k): [Comment(**c) for c in v] for k, v in raw["comments"].items()}
            self.pull_requests = {int(k): PullRequestRecord(**{**v, "reviews": tuple(v["reviews"])}) for k, v in raw["pull_requests"].items()}
            self._ids = iter(range(raw["next_id"], 10**9))
            self._ticks = iter(range(raw["next_tick"], 10**9))

    def save(self) -> None:
        """Atomic and durable (temp file, fsync, rename): an interrupted write leaves the
        previous complete file, never a truncated one."""
        next_id, next_tick = next(self._ids), next(self._ticks)
        self._ids, self._ticks = iter(range(next_id, 10**9)), iter(range(next_tick, 10**9))
        raw = {"issues": {k: asdict(v) for k, v in self.issues.items()}, "items": {k: asdict(v) for k, v in self.items.items()},
               "comments": {k: [asdict(c) for c in v] for k, v in self.comments.items()}, "pull_requests": {k: asdict(v) for k, v in self.pull_requests.items()},
               "next_id": next_id, "next_tick": next_tick}
        atomic_write_text(self.path, json.dumps(raw, indent=1, sort_keys=True))

    def post_comment(self, number: int, body: str) -> Comment:
        """The landed effect is persisted before any simulated after-effect crash, so a reload
        after such a crash sees the comment that GitHub would also still hold."""
        crash = self.crash_after_post
        self.crash_after_post = False
        comment = super().post_comment(number, body)
        self.save()
        if crash:
            raise CrashAfterEffect("process died after posting")
        return comment


def synthetic_backlog(transport: FakeTransport) -> None:
    transport.add_issue(issue(9900, EPIC, "Fixture-only smoke epic", labels=("epic",), epic_prereq="None"), "Backlog", EPIC)
    transport.add_issue(issue(9901, STORY, "Fixture-only smoke story", labels=("story",), parent=9900, depends_on="None", tasks=1), "Ready", STORY)


def _load_json(value: str | None):
    if value is None:
        return None
    path = Path(value)
    return json.loads(path.read_text(encoding="utf-8") if path.exists() else value)


def _tag(payload, source: str, kind: str) -> dict:
    """The coordinator's input, passed through unchanged (the coordinator validates and
    normalizes receipts itself); its provenance is recorded by :meth:`Smoke.keep`."""
    return dict(payload)


def load_legacy_pickle(path: Path) -> FakeTransport:
    """A historical smoke kept its fixture transport as a pickle of ``FakeTransport``. Loaded
    only from an explicitly given state directory; comments posted later are persisted back."""
    import pickle

    with path.open("rb") as fh:
        transport = pickle.load(fh)
    if not isinstance(transport, FakeTransport) or transport.live:
        raise UnattendedError(f"{path} is not a fixture FakeTransport")
    return transport


class Smoke:
    def __init__(self, directory: Path, run_id: str = RUN_ID):
        self.dir = directory
        self.run_id = run_id
        legacy = self.dir / "fixture-transport.pickle"
        if not (self.dir / "transport.json").exists() and legacy.exists():
            self.transport = PersistedFakeTransport(self.dir / "transport.json")
            source = load_legacy_pickle(legacy)
            self.transport.issues, self.transport.items, self.transport.comments, self.transport.pull_requests = source.issues, source.items, source.comments, source.pull_requests
            self.transport._ids, self.transport._ticks = source._ids, source._ticks
            self.transport.save()
        else:
            self.transport = PersistedFakeTransport(self.dir / "transport.json")
        self.policy_path = self.dir / "policy.toml"
        self.log_path = self.dir / "smoke-log.jsonl"

    def coordinator(self) -> Coordinator:
        policy = load_policy(self.policy_path)
        return Coordinator(self.transport, policy, Store(self.dir / "runs", self.run_id), live=True)

    def keep(self, operation: str, kind: str, payload: dict, source: str) -> None:
        """Persist the supplied input verbatim with its declared source, so the published
        smoke shows exactly what the coordinator provided and whether it was real or fixture."""
        folder = self.dir / "inputs"
        folder.mkdir(parents=True, exist_ok=True)
        n = len(list(folder.glob("*.json"))) + 1
        (folder / f"{n:03d}-{operation}-{kind}.json").write_text(json.dumps({"kind": kind, "source": source, "recorded_at": utcnow(), "payload": payload, "note": "supplied by the coordinator; the helper cannot verify it"}, indent=1, sort_keys=True), encoding="utf-8")

    def log(self, operation: str, detail: dict) -> None:
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"at": utcnow(), "operation": operation, **detail}, sort_keys=True, default=str) + "\n")

    def prepare(self, worktree: str | None, branch: str | None, checks: list[str] | None) -> dict:
        if self.transport.path.exists():
            raise UnattendedError(f"{self.dir} is already prepared; use a fresh --dir for a new smoke")
        self.dir.mkdir(parents=True, exist_ok=True)
        synthetic_backlog(self.transport)
        self.transport.save()
        branch = branch or "smoke/om-99-01"
        baseline = None
        if worktree is None:
            worktree = str(self.dir / "worktree")
            baseline = make_git_repo(Path(worktree), branch)
        commands = checks or DEFAULT_CHECKS
        write_policy(self.dir, allow=f'["{STORY}"]', commands=json.dumps(commands))
        (self.dir / "smoke.json").write_text(json.dumps({"story": STORY, "epic": EPIC, "worktree": worktree, "branch": branch, "baseline": baseline, "checks": commands, "environment": "fixture-transport (no network); receipts and evidence must come from real T3 tasks to count as real smoke"}, indent=1), encoding="utf-8")
        c = self.coordinator()
        snapshot = take_snapshot(self.transport, c.policy.repo_slug, utcnow())
        state = c.reserve(STORY, snapshot, baseline or "unknown")
        auth = state.unresolved_authorization()
        out = {"phase": state.phase, "authorization": auth["id"] if auth else None, "worktree": worktree, "branch": branch, "baseline": baseline, "checks": commands}
        self.log("prepare", out)
        return out

    def bind(self, receipt: dict, source: str, worktree: str | None, branch: str | None, authorization: str | None) -> dict:
        self.keep("bind", "receipt", receipt, source)
        state = self.coordinator().bind_receipt(STORY, _tag(receipt, source, "receipt"), worktree, branch, git_worktree_check, authorization)
        out = {"phase": state.phase, "active_task": state.active_task, "source": source}
        self.log("bind", out)
        return out

    def head(self, sha: str, evidence: dict, source: str) -> dict:
        self.keep("head", "terminal-evidence", evidence, source)
        state = self.coordinator().record_head(STORY, sha, _tag(evidence, source, "terminal-evidence"))
        out = {"phase": state.phase, "head": state.head_sha, "source": source}
        self.log("head", out)
        return out

    def check(self, sha: str) -> dict:
        """Checks run in the worktree bound at ``bind`` (the claim is authoritative), not in
        whatever ``prepare`` suggested: the real T3 checkout path is only known after launch."""
        c = self.coordinator()
        state = c.store.load_story(STORY)
        bound = (state.claim or {}).get("worktree_path") if state else None
        if not bound:
            raise UnattendedError("check: no worktree is bound to the story yet; bind the implementer receipt first")
        state = c.run_checks(STORY, sha, bound)
        out = {"phase": state.phase, "checks": state.checks[-1]}
        self.log("check", out)
        return out

    def authorize_review(self, sha: str) -> dict:
        state = self.coordinator().authorize_review(STORY, sha)
        auth = state.unresolved_authorization()
        out = {"phase": state.phase, "authorization": auth["id"] if auth else None, "sha": sha}
        self.log("authorize-review", out)
        return out

    def review(self, sha: str, verdict: str, report: str, evidence: dict, source: str) -> dict:
        self.keep("review", "terminal-evidence", evidence, source)
        state = self.coordinator().record_review(STORY, sha, verdict, report, _tag(evidence, source, "terminal-evidence"))
        out = {"phase": state.phase, "approved_sha": state.approved_sha, "source": source}
        self.log("review", out)
        return out

    def cancel(self, reason: str, evidence: dict | None, no_launch: dict | None, source: str) -> dict:
        if evidence:
            self.keep("cancel", "terminal-evidence", evidence, source)
        if no_launch:
            self.keep("cancel", "no-launch-attestation", no_launch, source)
        state = self.coordinator().cancel(STORY, reason, _tag(evidence, source, "terminal-evidence") if evidence else None, no_launch)
        out = {"phase": state.phase, "pending_intents": [i.op for i in state.pending_intents()], "source": source}
        self.log("cancel", out)
        return out

    def terminal(self, evidence: dict, source: str) -> dict:
        self.keep("terminal", "terminal-evidence", evidence, source)
        state = self.coordinator().record_task_terminal(STORY, _tag(evidence, source, "terminal-evidence"))
        out = {"phase": state.phase, "active_task": state.active_task, "source": source}
        self.log("terminal", out)
        return out

    def reconcile(self, authorization: str, receipt: dict, evidence: dict, reason: str, provenance: str, source: str) -> dict:
        self.keep("reconcile", "receipt", receipt, source)
        self.keep("reconcile", "terminal-evidence", evidence, source)
        state = self.coordinator().reconcile_retained_execution(STORY, authorization, receipt, evidence, reason, provenance)
        auth = state.authorization(authorization)
        out = {"phase": state.phase, "authorization": auth, "active_task": state.active_task, "source": source}
        self.log("reconcile", out)
        return out

    def restart(self) -> dict:
        """A fresh coordinator over the persisted transport and store: resume."""
        state = self.coordinator().resume(STORY, git_worktree_check)
        out = {"phase": state.phase, "pending_intents": [i.op for i in state.pending_intents()], "active_task": state.active_task}
        self.log("restart", out)
        return out

    def status(self) -> dict:
        state = self.coordinator().store.load_story(STORY)
        inputs = [json.loads(f.read_text(encoding="utf-8")) for f in sorted((self.dir / "inputs").glob("*.json"))] if (self.dir / "inputs").exists() else []
        sources = sorted({i["source"] for i in inputs})
        return {"story": state.to_dict() if state else None, "comments": [c.body.splitlines()[0] for c in self.transport.comments.get(9901, [])],
                "inputs": inputs, "evidence_class": ("real" if sources == ["real"] else "fixture") if inputs else "none",
                "log": [json.loads(l) for l in self.log_path.read_text(encoding="utf-8").splitlines()] if self.log_path.exists() else []}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python3 -m automation.tests.lifecycle_smoke", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dir", required=True, help="temporary isolated directory for this smoke (transport, policy, state, log)")
    p.add_argument("--run-id", default=RUN_ID, help="persisted run under <dir>/runs (default smoke-run; a historical copy names its own)")
    sub = p.add_subparsers(dest="command", required=True)
    pr = sub.add_parser("prepare"); pr.add_argument("--worktree"); pr.add_argument("--branch"); pr.add_argument("--check-command", action="append")
    bd = sub.add_parser("bind"); bd.add_argument("--receipt", required=True); bd.add_argument("--worktree"); bd.add_argument("--branch"); bd.add_argument("--authorization"); bd.add_argument("--source", choices=SOURCES, required=True)
    hd = sub.add_parser("head"); hd.add_argument("--sha", required=True); hd.add_argument("--task-evidence", required=True); hd.add_argument("--source", choices=SOURCES, required=True)
    ck = sub.add_parser("check"); ck.add_argument("--sha", required=True)
    ar = sub.add_parser("authorize-review"); ar.add_argument("--sha", required=True)
    rv = sub.add_parser("review"); rv.add_argument("--sha", required=True); rv.add_argument("--verdict", choices=["approved", "changes-requested"], required=True); rv.add_argument("--report", required=True); rv.add_argument("--task-evidence", required=True); rv.add_argument("--source", choices=SOURCES, required=True)
    ca = sub.add_parser("cancel"); ca.add_argument("--reason", required=True); ca.add_argument("--task-evidence"); ca.add_argument("--no-launch"); ca.add_argument("--source", choices=SOURCES, required=True)
    te = sub.add_parser("terminal"); te.add_argument("--task-evidence", required=True); te.add_argument("--source", choices=SOURCES, required=True)
    rc2 = sub.add_parser("reconcile"); rc2.add_argument("--authorization", required=True); rc2.add_argument("--receipt", required=True); rc2.add_argument("--task-evidence", required=True); rc2.add_argument("--reason", required=True); rc2.add_argument("--provenance", required=True); rc2.add_argument("--source", choices=SOURCES, required=True)
    sub.add_parser("restart")
    sub.add_parser("status")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    smoke = Smoke(Path(args.dir), args.run_id)
    try:
        if args.command == "prepare":
            out = smoke.prepare(args.worktree, args.branch, args.check_command)
        elif args.command == "bind":
            out = smoke.bind(_load_json(args.receipt), args.source, args.worktree, args.branch, args.authorization)
        elif args.command == "head":
            out = smoke.head(args.sha, _load_json(args.task_evidence), args.source)
        elif args.command == "check":
            out = smoke.check(args.sha)
        elif args.command == "authorize-review":
            out = smoke.authorize_review(args.sha)
        elif args.command == "review":
            out = smoke.review(args.sha, args.verdict, args.report, _load_json(args.task_evidence), args.source)
        elif args.command == "cancel":
            out = smoke.cancel(args.reason, _load_json(args.task_evidence), _load_json(args.no_launch), args.source)
        elif args.command == "terminal":
            out = smoke.terminal(_load_json(args.task_evidence), args.source)
        elif args.command == "reconcile":
            out = smoke.reconcile(args.authorization, _load_json(args.receipt), _load_json(args.task_evidence), args.reason, args.provenance, args.source)
        elif args.command == "restart":
            out = smoke.restart()
        else:
            out = smoke.status()
        print(json.dumps({"ok": True, "environment": "fixture-transport", **out}, indent=1, sort_keys=True, default=str))
        return 0
    except UnattendedError as exc:
        smoke.log(args.command, {"refused": exc.as_dict()})
        print(json.dumps({"ok": False, "environment": "fixture-transport", "error": exc.as_dict()}, indent=1, sort_keys=True, default=str))
        return 3


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
