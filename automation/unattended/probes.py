"""Permission, environment and deterministic-check probes, plus the bounded live write probe."""

from __future__ import annotations

import json
import re
import shlex
import subprocess
from collections.abc import Callable

from .errors import Refused
from .github import Transport, render_marker

Runner = Callable[[list[str], str | None, int], subprocess.CompletedProcess]

MINIMUM_CLASSIC_SCOPES = ("repo", "project")
EXCESS_SCOPES = ("workflow", "admin:public_key", "gist", "delete_repo", "admin:org", "write:org", "admin:repo_hook", "user", "admin:gpg_key", "codespace")
STORY_LABELS = ("epic", "story")


def default_runner(argv: list[str], cwd: str | None, timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False)


TOKEN_RE = re.compile(r"\b(gh[pousr]_[A-Za-z0-9_]{8,}|github_pat_[A-Za-z0-9_]{8,}|sk-[A-Za-z0-9]{8,})\b")


def _tail(text: str, limit: int = 4000) -> str:
    return TOKEN_RE.sub("<redacted>", text[-limit:]) if text else ""


def run_commands(commands: list[str], cwd: str | None, timeout: int, runner: Runner = default_runner) -> list[dict]:
    results = []
    for command in commands:
        argv = shlex.split(command)
        try:
            proc = runner(argv, cwd, timeout)
            results.append({"command": command, "returncode": proc.returncode, "stdout_tail": _tail(proc.stdout), "stderr_tail": _tail(proc.stderr)})
        except subprocess.TimeoutExpired:
            results.append({"command": command, "returncode": -1, "error": f"timeout after {timeout}s"})
        except OSError as exc:
            results.append({"command": command, "returncode": -1, "error": str(exc)})
        if results[-1]["returncode"] != 0:
            break  # fail fast: later checks are not evidence once one failed
    return results


def check_permissions(owner: str, repo: str, project_owner: str, project_number: int, runner: Runner = default_runner) -> dict:
    report: dict = {"minimum": {"classic_scopes": list(MINIMUM_CLASSIC_SCOPES), "fine_grained": ["Issues: read/write", "Pull requests: read", "Contents: read", "Metadata: read", "Projects (user): read/write"]}, "observed": {}, "problems": [], "excess": []}
    auth = runner(["gh", "auth", "status"], None, 60)
    report["observed"]["gh_auth_status_exit"] = auth.returncode
    if auth.returncode != 0:
        report["problems"].append("gh is not authenticated")
    headers = runner(["gh", "api", "-i", f"repos/{owner}/{repo}"], None, 60)
    scopes: list[str] = []
    if headers.returncode == 0:
        m = re.search(r"^x-oauth-scopes:\s*(.*)$", headers.stdout, re.I | re.M)
        scopes = [s.strip() for s in m.group(1).split(",") if s.strip()] if m else []
        body = headers.stdout.split("\r\n\r\n", 1)[-1].split("\n\n", 1)[-1]
        try:
            perms = json.loads(body).get("permissions", {})
        except json.JSONDecodeError:
            perms = {}
        report["observed"]["repository_permissions"] = perms
        if not perms.get("push"):
            report["problems"].append("repository push permission missing (needed for issue writes and PR branches)")
    else:
        report["problems"].append(f"repository not readable: {headers.stderr.strip()[:200]}")
    report["observed"]["token_scopes"] = scopes
    if scopes:
        missing = [s for s in MINIMUM_CLASSIC_SCOPES if s not in scopes]
        if missing:
            report["problems"].append(f"missing classic scopes {missing}")
        report["excess"] = [s for s in scopes if s in EXCESS_SCOPES]
    else:
        report["observed"]["note"] = "no classic scope header: fine-grained token or app; verify permissions manually"
    project = runner(["gh", "api", "graphql", "-f", f'query={{ user(login:"{project_owner}"){{ projectV2(number:{project_number}){{ id title viewerCanUpdate }} }} }}'], None, 60)
    if project.returncode == 0:
        try:
            node = json.loads(project.stdout)["data"]["user"]["projectV2"]
        except (KeyError, json.JSONDecodeError, TypeError):
            node = None
        report["observed"]["project"] = node
        if not node:
            report["problems"].append("project not readable")
        elif not node.get("viewerCanUpdate"):
            report["problems"].append("project is readable but not updatable by this identity")
    else:
        report["problems"].append(f"project query failed: {project.stderr.strip()[:200]}")
    report["minimum_satisfied"] = not report["problems"]
    report["enforcement"] = ("The policy restricts what the tool writes; the credential boundary is enforced only by the token the operator provisions. "
                             "Excess scopes listed above are not used but are not blocked by the tool.")
    return report


def write_probe(transport: Transport, issue_number: int, run_id: str, target_status: str | None, now: str) -> dict:
    """Bounded live-transport probe on an engineering-automation issue only."""
    issue = transport.get_issue(issue_number)
    if "engineering-automation" not in issue.labels or any(l in issue.labels for l in STORY_LABELS):
        raise Refused(f"issue #{issue_number} is not an engineering-automation issue; write probes never touch backlog issues")
    marker = {"kind": "probe", "run": run_id, "story": f"ENG-{issue_number}", "seq": "1"}
    before = [c for c in transport.list_comments(issue_number) if c.marker == marker]
    posted = None
    if not before:
        posted = transport.post_comment(issue_number, f"{render_marker(**marker)}\nWrite probe from run `{run_id}` at {now}: verifies idempotent marker comments and verified Status writes on the engineering issue only.")
    after = [c for c in transport.list_comments(issue_number) if c.marker == marker]
    result = {"issue": issue_number, "marker": marker, "comment_existed": bool(before), "posted": posted.comment_id if posted else None, "comments_with_marker": [c.comment_id for c in after], "idempotent": len(after) == 1}
    if target_status:
        info = transport.project_info()
        item = next((i for i in transport.list_project_items() if i.issue_number == issue_number), None)
        if item is None:
            raise Refused(f"issue #{issue_number} has no Project item")
        pre = transport.get_project_item(item.item_id)
        if pre.updated_at != item.updated_at:
            result["status"] = {"stale": True, "snapshot_updated_at": item.updated_at, "pre_write_updated_at": pre.updated_at}
            return result
        transport.set_project_status(item.item_id, info.status_options[target_status])
        post = transport.get_project_item(item.item_id)
        result["status"] = {"from": pre.status, "to": target_status, "verified": post.status == target_status, "pre_updated_at": pre.updated_at, "post_updated_at": post.updated_at}
    return result
