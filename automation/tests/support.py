from __future__ import annotations

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


IMPLEMENTER = {"taskId": "task-impl-1", "providerInstanceId": "claudeAgent", "model": "claude-fable-5-1", "options": [{"id": "effort", "value": "high"}], "isolation": "worktree"}
REVIEWER = {"taskId": "task-review-1", "providerInstanceId": "codex", "model": "gpt-6-astra", "options": {"reasoningEffort": "high"}}


def receipt(base: dict, task_id: str) -> dict:
    return {**base, "taskId": task_id}


class Harness:
    def __init__(self, fake, allow='["OM-01.02"]', **overrides):
        self.tmpdir = tempfile.TemporaryDirectory()
        tmp = Path(self.tmpdir.name)
        self.policy = load_policy(write_policy(tmp, allow=allow, **overrides))
        self.fake = fake
        self.store = Store(tmp / "runs", "run-1")
        self.coordinator = Coordinator(fake, self.policy, self.store)
        self.snapshot = take_snapshot(fake, "gabrianoo/owl-mast", "2026-11-06T12:00:00Z")

    def claim(self, story="OM-01.02", receipt_=None):
        return self.coordinator.claim(story, self.snapshot, receipt_ or IMPLEMENTER, "/tmp/wt", "t3/om-01-02", "c5d9d2e", ok_worktree)

    def to_review_approved(self, story="OM-01.02", sha="abc123"):
        c = self.coordinator
        self.claim(story)
        c.record_head(story, sha)
        c.record_checks(story, sha, True, {"commands": []})
        c.request_review(story, sha, REVIEWER)
        return c.record_review(story, sha, "approved", "report.md")

    def close(self):
        self.tmpdir.cleanup()
