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


def run_commands(commands: list[str], cwd: str | None, timeout: int, runner: Runner = default_runner, fail_fast: bool = True) -> list[dict]:
    """Run each command in order. ``fail_fast`` stops at the first failure (probes);
    deterministic checks run the full set so the record shows every command."""
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
        if fail_fast and results[-1]["returncode"] != 0:
            break
    return results


def check_permissions(owner: str, repo: str, project_owner: str, project_number: int, runner: Runner = default_runner) -> dict:
    """Two separate verdicts. ``basic_access`` says the identity can do what the tool needs.
    ``bounded`` says the credential is provably limited to the minimum: known classic scopes
    equal to exactly the minimum set. Unknown scopes (fine-grained tokens expose none) or any
    excess scope leave ``bounded`` false, and unattended activation is not allowed."""
    report: dict = {
        "minimum": {"classic_scopes": list(MINIMUM_CLASSIC_SCOPES), "fine_grained": ["Issues: read/write", "Pull requests: read", "Contents: read", "Metadata: read", "Projects (user account): read/write"]},
        "observed": {}, "problems": [], "excess": [], "bounded_reasons": [],
    }
    auth = runner(["gh", "auth", "status"], None, 60)
    report["observed"]["gh_auth_status_exit"] = auth.returncode
    if auth.returncode != 0:
        report["problems"].append("gh is not authenticated")
    headers = runner(["gh", "api", "-i", f"repos/{owner}/{repo}"], None, 60)
    scopes: list[str] | None = None
    if headers.returncode == 0:
        m = re.search(r"^x-oauth-scopes:\s*(.*)$", headers.stdout, re.I | re.M)
        scopes = [sc.strip() for sc in m.group(1).split(",") if sc.strip()] if m else None
        body = headers.stdout.split("\r\n\r\n", 1)[-1].split("\n\n", 1)[-1]
        try:
            perms = json.loads(body).get("permissions", {})
        except json.JSONDecodeError:
            perms = {}
        report["observed"]["repository_permissions"] = perms
        if not perms.get("push"):
            report["problems"].append("repository push permission missing (needed for issue comments and PR branches)")
        if perms.get("admin"):
            report["bounded_reasons"].append("identity has admin on the repository")
    else:
        report["problems"].append(f"repository not readable: {headers.stderr.strip()[:200]}")
    report["observed"]["token_scopes"] = scopes
    if scopes is None:
        report["bounded_reasons"].append("no classic scope header (fine-grained token or app): declared permissions cannot be read from the API; unknown is not bounded")
    else:
        missing = [sc for sc in MINIMUM_CLASSIC_SCOPES if sc not in scopes]
        if missing:
            report["problems"].append(f"missing classic scopes {missing}")
        report["excess"] = [sc for sc in scopes if sc not in MINIMUM_CLASSIC_SCOPES]
        if report["excess"]:
            report["bounded_reasons"].append(f"excess scopes beyond the minimum: {report['excess']}")
    project = runner(["gh", "api", "graphql", "-f", f'query={{ user(login:"{project_owner}"){{ projectV2(number:{project_number}){{ id title viewerCanUpdate }} }} }}'], None, 60)
    if project.returncode == 0:
        try:
            node = json.loads(project.stdout)["data"]["user"]["projectV2"]
        except (KeyError, json.JSONDecodeError, TypeError):
            node = None
        report["observed"]["project"] = node
        if not node:
            report["problems"].append("project not readable")
    else:
        report["problems"].append(f"project query failed: {project.stderr.strip()[:200]}")
    report["basic_access"] = not report["problems"]
    report["bounded"] = report["basic_access"] and not report["bounded_reasons"]
    report["denial_tested"] = False
    report["unattended_activation_allowed"] = report["bounded"]
    report["enforcement"] = ("The policy restricts what the tool writes; the credential boundary is enforced only by the token the operator provisions. "
                             "basic_access proves the identity can act; bounded proves it cannot act beyond the minimum. Denial of forbidden operations has not been tested.")
    return report


def write_probe(transport: Transport, issue_number: int, run_id: str, now: str) -> dict:
    """Bounded live-transport probe on an engineering-automation issue only: one idempotent
    marker comment. It never writes Project Status or any other owner field."""
    issue = transport.get_issue(issue_number)
    if "engineering-automation" not in issue.labels or any(l in issue.labels for l in STORY_LABELS):
        raise Refused(f"issue #{issue_number} is not an engineering-automation issue; write probes never touch backlog issues")
    marker = {"kind": "probe", "run": run_id, "story": f"ENG-{issue_number}", "op": "probe"}
    before = [c for c in transport.list_comments(issue_number) if c.marker == marker]
    posted = None
    if not before:
        posted = transport.post_comment(issue_number, f"{render_marker(**marker)}\nWrite probe from run `{run_id}` at {now}: verifies idempotent marker comments on the engineering issue only; no Project Status or body is written.")
    after = [c for c in transport.list_comments(issue_number) if c.marker == marker]
    return {"issue": issue_number, "marker": marker, "comment_existed": bool(before), "posted": posted.comment_id if posted else None, "comments_with_marker": [c.comment_id for c in after], "idempotent": len(after) == 1}
