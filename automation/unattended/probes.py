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
    """``basic_access``: the identity can do what the tool needs (observed). ``bounded``: the
    credential is proven limited to the minimum. Scope names and the admin flag never prove
    that (classic ``repo`` is broad by definition), so ``bounded`` is true only when
    ``denial_tested`` and ``resource_scope_verified`` are both recorded by a qualification
    this probe does not perform; today it is always false and activation is never allowed."""
    report: dict = {
        "minimum": {
            "classic_scopes": list(MINIMUM_CLASSIC_SCOPES),
            "minimum_note": "classic `repo` is broader than needed and, per GitHub's scope documentation, also grants the ability to manage user-owned Projects; `read:project` alone would be enough for this tool's Project reads, but classic scopes are a union, so no classic token that can post comments is read-only on the Project",
            "fine_grained": ["Issues: read/write", "Pull requests: read", "Contents: read", "Metadata: read", "Projects: read (user-owned Projects are a documented fine-grained PAT limitation)"],
            "implementer_branch_privileges": "separate identity: push to implementation branches and open PRs; not part of this tool's minimum",
        },
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
            report["problems"].append("repository push permission missing (needed to post issue comments through this identity)")
        if perms.get("admin"):
            report["bounded_reasons"].append("identity has admin on the repository")
    else:
        report["problems"].append(f"repository not readable: {headers.stderr.strip()[:200]}")
    report["observed"]["token_scopes"] = scopes
    if scopes is None:
        report["bounded_reasons"].append("no classic scope header (fine-grained token or app): declared permissions cannot be read from the API")
    else:
        if "repo" not in scopes:
            report["problems"].append("missing classic scope repo")
        if not any(sc in scopes for sc in ("project", "read:project")):
            report["problems"].append("missing classic scope project or read:project")
        report["excess"] = [sc for sc in scopes if sc not in MINIMUM_CLASSIC_SCOPES and sc != "read:project"]
        if report["excess"]:
            report["bounded_reasons"].append(f"excess scopes beyond the minimum: {report['excess']}")
        if "repo" in scopes:
            report["bounded_reasons"].append("classic `repo` grants full repository access and manages user-owned Projects (write), whatever other scopes accompany it; scope names cannot prove a bounded credential")
    project = runner(["gh", "api", "graphql", "-f", f'query={{ user(login:"{project_owner}"){{ projectV2(number:{project_number}){{ id title viewerCanUpdate }} }} }}'], None, 60)
    if project.returncode == 0:
        try:
            node = json.loads(project.stdout)["data"]["user"]["projectV2"]
        except (KeyError, json.JSONDecodeError, TypeError):
            node = None
        report["observed"]["project"] = node
        if not node:
            report["problems"].append("project not readable")
        elif node.get("viewerCanUpdate"):
            report["bounded_reasons"].append("identity can update the Project although this tool only reads it")
    else:
        report["problems"].append(f"project query failed: {project.stderr.strip()[:200]}")
    report["basic_access"] = not report["problems"]
    report["denial_tested"] = False
    report["resource_scope_verified"] = False
    report["bounded_reasons"].append("denial of forbidden operations not tested (a denial probe needs a separately authorized disposable qualification resource; it is never run against the live Project or backlog)")
    report["bounded_reasons"].append("resource scope (single repository, single Project) not verified")
    report["bounded"] = False
    report["unattended_activation_allowed"] = False
    report["owner_acceptance"] = ("permission facts only: this report never certifies bounded or activation; under the trusted-machine operating agreement (2026-11-06) a broad "
                                  "credential is disclosed as broad and used where no restricted one is practical, which is an accepted residual risk, not a verdict of this probe")
    report["enforcement"] = ("basic_access is an observation that the identity can act. bounded requires denial testing and resource-scope verification that this probe does not perform; "
                             "scope headers and the admin flag alone never qualify a credential. The policy restricts what the tool writes; the credential boundary is enforced only by the token the operator provisions.")
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
