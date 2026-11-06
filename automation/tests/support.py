from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from automation.unattended.backlog import take_snapshot
from automation.unattended.coordinator import Coordinator
from automation.unattended.policy import load_policy
from automation.unattended.state import Store

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
POLICY_TEXT = (ROOT / "automation/policy.toml").read_text(encoding="utf-8")


def write_policy(tmp: Path, **overrides: str) -> Path:
    """The repository policy with line-level overrides (``allow='["OM-01.02"]'``)."""
    lines = []
    skipping = False
    for line in POLICY_TEXT.splitlines():
        if skipping:
            if line.strip().startswith("]"):
                skipping = False
            continue
        key = line.split("=", 1)[0].strip()
        if "=" in line and key in overrides:
            lines.append(f"{key} = {overrides[key]}")
            skipping = line.rstrip().endswith("[")
        else:
            lines.append(line)
    path = tmp / "policy.toml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def ok_worktree(path: str, branch: str) -> tuple[bool, str]:
    return True, "ok"


def passing_runner(argv, cwd, timeout):
    return subprocess.CompletedProcess(argv, 0, "ok\n", "")


def failing_runner(argv, cwd, timeout):
    return subprocess.CompletedProcess(argv, 1, "", "boom\n")


def run_of(task_id: str, ordinal: int = 1) -> str:
    """Fixture run identity: executions are (taskId, runId) pairs; the first run of a fixture
    task is ``<taskId>:run:1``."""
    return f"{task_id}:run:{ordinal}"


IMPLEMENTER = {"taskId": "task-impl-1", "runId": run_of("task-impl-1"), "providerInstanceId": "claudeAgent", "model": "claude-fable-5-1", "options": [{"id": "effort", "value": "high"}], "isolation": "worktree"}
REVIEWER = {"taskId": "task-review-1", "runId": run_of("task-review-1"), "providerInstanceId": "codex", "model": "gpt-6-astra", "options": {"reasoningEffort": "high"}}


def receipt(base: dict, task_id: str, ordinal: int = 1) -> dict:
    return {**base, "taskId": task_id, "runId": run_of(task_id, ordinal)}


def evidence(task_id: str, status: str = "result_available", ordinal: int = 1) -> dict:
    return {"taskId": task_id, "runId": run_of(task_id, ordinal), "status": status}


def make_git_repo(path: Path, branch: str = "t3/om-01-02") -> str:
    """A real git repository with one commit; returns its HEAD sha."""
    path.mkdir(parents=True, exist_ok=True)
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid", "HOME": str(path), "PATH": "/usr/bin:/bin:/usr/local/bin"}
    subprocess.run(["git", "init", "-q", "-b", branch], cwd=path, check=True, env=env)
    (path / "README").write_text("x\n")
    subprocess.run(["git", "add", "README"], cwd=path, check=True, env=env)
    subprocess.run(["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "init"], cwd=path, check=True, env=env)
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=path, check=True, capture_output=True, text=True, env=env).stdout.strip()


def git_commit(path: Path, name: str) -> str:
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid", "HOME": str(path), "PATH": "/usr/bin:/bin:/usr/local/bin"}
    (path / name).write_text(name)
    subprocess.run(["git", "add", name], cwd=path, check=True, env=env)
    subprocess.run(["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", name], cwd=path, check=True, env=env)
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=path, check=True, capture_output=True, text=True, env=env).stdout.strip()


class Harness:
    def __init__(self, fake, allow='["OM-01.02"]', live=True, **overrides):
        self.tmpdir = tempfile.TemporaryDirectory()
        tmp = Path(self.tmpdir.name)
        self.policy = load_policy(write_policy(tmp, allow=allow, **overrides))
        self.fake = fake
        self.state_dir = tmp / "runs"
        self.store = Store(self.state_dir, "run-1")
        self.coordinator = Coordinator(fake, self.policy, self.store, live=live)
        self.snapshot = take_snapshot(fake, "gabrianoo/owl-mast", "2026-11-06T12:00:00Z")
        self.worktree = tmp / "wt"
        self.sha = make_git_repo(self.worktree)

    def reserve(self, story="OM-01.02"):
        return self.coordinator.reserve(story, self.snapshot, "c5d9d2e")

    def claim(self, story="OM-01.02", receipt_=None):
        """Reserve (admission + implementer authorization) before the simulated delegate,
        then bind its receipt and worktree, consuming the authorization."""
        self.reserve(story)
        return self.coordinator.bind_receipt(story, receipt_ or IMPLEMENTER, str(self.worktree), "t3/om-01-02", ok_worktree)

    def terminal(self, story="OM-01.02", status="result_available"):
        """Terminal evidence for the story's active task (whatever its role)."""
        state = self.store.load_story(story)
        return {"taskId": state.active_task["taskId"], "runId": state.active_task["runId"], "status": status}

    def checks(self, story="OM-01.02", sha=None, runner=passing_runner):
        """The implementer returned (terminal evidence), its head is recorded, checks run."""
        sha = sha or self.sha
        self.coordinator.record_head(story, sha, self.terminal(story))
        return self.coordinator.run_checks(story, sha, str(self.worktree), runner)

    def request_review(self, story="OM-01.02", receipt_=None):
        """Authorize the reviewer task before the simulated launch, then bind its receipt."""
        self.coordinator.authorize_review(story, self.sha)
        return self.coordinator.bind_receipt(story, receipt_ or REVIEWER, worktree_check=ok_worktree)

    def repair(self, story="OM-01.02", receipt_=None):
        """Authorize a repair round before the simulated launch, then bind its receipt."""
        state = self.coordinator.authorize_repair(story)
        if state.phase != "repair-authorized":
            return state  # blocked
        return self.coordinator.bind_receipt(story, receipt_, worktree_check=ok_worktree)

    def to_review_approved(self, story="OM-01.02"):
        c = self.coordinator
        self.claim(story)
        self.checks(story)
        self.request_review(story)
        return c.record_review(story, self.sha, "approved", "report.md", self.terminal(story))

    def close(self):
        self.tmpdir.cleanup()
