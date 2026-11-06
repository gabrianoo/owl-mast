"""GitHub transport.

``Transport`` is the narrow set of reads and writes the tool needs. ``GhCliTransport``
implements it with the ``gh`` CLI, so authentication stays in the operator's ``gh`` session
(or a ``GH_TOKEN`` the operator exports from the supported secret path). Failures are
classified into ``PermissionDenied``, ``Outage``, ``NotFound`` or ``TransportError``; the
caller treats every one as fail-closed.

Precise guarantee statement: GitHub offers no compare-and-swap on issue bodies, Project
field values or comments. The tool therefore never mutates a field another writer owns:
the only write it performs is appending an issue comment that carries a unique operation
marker. Reads (issues, Project items, comments, pull requests) supply revisions that the
coordinator compares before admission and before every effect; a changed revision is a
refusal, never something the tool overwrites. Project Status stays owner-written.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from typing import Protocol

from .errors import NotFound, Outage, PermissionDenied, TransportError

MARKER_RE = re.compile(r"<!-- unattended (?P<attrs>[^>]*?) -->")


@dataclass(frozen=True)
class IssueRecord:
    number: int
    node_id: str
    title: str
    state: str  # OPEN | CLOSED
    state_reason: str | None
    updated_at: str
    closed_at: str | None
    body: str
    labels: tuple[str, ...]
    parent_number: int | None


@dataclass(frozen=True)
class ProjectItem:
    item_id: str
    issue_number: int | None
    status: str | None
    stable_id: str | None
    updated_at: str


@dataclass(frozen=True)
class ProjectInfo:
    project_id: str
    status_field_id: str
    status_options: dict[str, str]  # name -> option id


@dataclass(frozen=True)
class Comment:
    comment_id: int
    body: str
    author: str
    created_at: str

    @property
    def marker(self) -> dict[str, str] | None:
        return parse_marker(self.body)


@dataclass(frozen=True)
class PullRequestRecord:
    number: int
    state: str  # OPEN | CLOSED | MERGED
    head_sha: str
    merged: bool
    reviews: tuple[dict, ...] = field(default_factory=tuple)  # {state, commit, author, submitted_at}
    checks: str | None = None  # SUCCESS | FAILURE | PENDING | None


def render_marker(**attrs: str) -> str:
    inner = " ".join(f"{k}={v}" for k, v in sorted(attrs.items()))
    return f"<!-- unattended {inner} -->"


def parse_marker(body: str) -> dict[str, str] | None:
    m = MARKER_RE.search(body or "")
    if not m:
        return None
    out: dict[str, str] = {}
    for token in m.group("attrs").split():
        if "=" in token:
            k, v = token.split("=", 1)
            out[k] = v
    return out


class Transport(Protocol):
    def list_issues(self) -> list[IssueRecord]: ...
    def get_issue(self, number: int) -> IssueRecord: ...
    def list_comments(self, number: int) -> list[Comment]: ...
    def post_comment(self, number: int, body: str) -> Comment: ...
    def project_info(self) -> ProjectInfo: ...
    def list_project_items(self) -> list[ProjectItem]: ...
    def get_project_item(self, item_id: str) -> ProjectItem: ...
    def get_pull_request(self, number: int) -> PullRequestRecord: ...


def classify(returncode: int, stderr: str, exc: BaseException | None = None) -> TransportError:
    text = (stderr or "").strip()
    low = text.lower()
    if exc is not None and isinstance(exc, subprocess.TimeoutExpired):
        return Outage(f"gh timed out: {text[:300]}")
    if exc is not None and isinstance(exc, FileNotFoundError):
        return TransportError("gh CLI not found on PATH")
    if "http 401" in low or "http 403" in low or "bad credentials" in low or "resource not accessible" in low or "not logged in" in low or "insufficient" in low and "scope" in low:
        return PermissionDenied(f"GitHub denied the request: {text[:300]}")
    if "http 404" in low or "could not resolve to" in low:
        return NotFound(f"GitHub object not found: {text[:300]}")
    if any(t in low for t in ("http 5", "http 429", "rate limit", "timeout", "timed out", "connection refused", "no such host", "network is unreachable", "tls handshake", "eof", "temporary failure")):
        return Outage(f"GitHub unreachable or throttled: {text[:300]}")
    return TransportError(f"gh failed (exit {returncode}): {text[:300]}")


class GhCliTransport:
    """Reads and writes through ``gh``. Never touches tokens itself. ``live`` marks it as the
    production boundary: the coordinator refuses product-story admission on a live transport
    until T3 enforcement is qualified (see docs/unattended-execution.md)."""

    live = True

    def __init__(self, owner: str, repo: str, project_owner: str, project_number: int, timeout_s: float = 60.0):
        self.owner, self.repo = owner, repo
        self.project_owner, self.project_number = project_owner, project_number
        self.timeout_s = timeout_s
        self._project: ProjectInfo | None = None

    # -- low level ---------------------------------------------------------------------
    def _run(self, args: list[str], stdin: str | None = None) -> str:
        try:
            proc = subprocess.run(["gh", *args], input=stdin, capture_output=True, text=True, timeout=self.timeout_s, check=False)
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            raise classify(-1, str(exc), exc) from exc
        if proc.returncode != 0:
            raise classify(proc.returncode, proc.stderr)
        return proc.stdout

    def _graphql(self, query: str, **variables) -> dict:
        args = ["api", "graphql", "-f", f"query={query}"]
        for key, value in variables.items():
            flag = "-F" if isinstance(value, int) else "-f"
            args += [flag, f"{key}={value}"]
        try:
            data = json.loads(self._run(args))
        except json.JSONDecodeError as exc:
            raise TransportError(f"GraphQL response is not JSON: {exc}") from exc
        if not isinstance(data, dict) or ("data" not in data and not data.get("errors")):
            raise TransportError("GraphQL response has no data")
        if data.get("errors"):
            messages = "; ".join(e.get("message", "") for e in data["errors"])
            low = messages.lower()
            if "permission" in low or "not have" in low or "forbidden" in low:
                raise PermissionDenied(f"GraphQL denied: {messages[:300]}")
            if "could not resolve" in low or "not found" in low:
                raise NotFound(f"GraphQL not found: {messages[:300]}")
            raise TransportError(f"GraphQL error: {messages[:300]}")
        return data["data"]

    # -- issues ------------------------------------------------------------------------
    _ISSUE_FIELDS = "number id title state stateReason updatedAt closedAt body labels(first:20){nodes{name}} parent{number}"

    @staticmethod
    def _issue(node: dict) -> IssueRecord:
        return IssueRecord(
            number=node["number"], node_id=node["id"], title=node["title"], state=node["state"],
            state_reason=node.get("stateReason"), updated_at=node["updatedAt"], closed_at=node.get("closedAt"),
            body=node.get("body") or "", labels=tuple(l["name"] for l in node["labels"]["nodes"]),
            parent_number=(node.get("parent") or {}).get("number"),
        )

    def list_issues(self) -> list[IssueRecord]:
        out: list[IssueRecord] = []
        after = "null"
        while True:
            q = ("query{ repository(owner:\"%s\", name:\"%s\"){ issues(first:100, after:%s, states:[OPEN,CLOSED], orderBy:{field:CREATED_AT, direction:ASC}){ pageInfo{hasNextPage endCursor} nodes{ %s } } } }"
                 % (self.owner, self.repo, after, self._ISSUE_FIELDS))
            page = self._graphql(q)["repository"]["issues"]
            out.extend(self._issue(n) for n in page["nodes"])
            if not page["pageInfo"]["hasNextPage"]:
                return out
            after = json.dumps(page["pageInfo"]["endCursor"])

    def get_issue(self, number: int) -> IssueRecord:
        q = "query{ repository(owner:\"%s\", name:\"%s\"){ issue(number:%d){ %s } } }" % (self.owner, self.repo, number, self._ISSUE_FIELDS)
        node = self._graphql(q)["repository"]["issue"]
        if node is None:
            raise NotFound(f"issue #{number} not found")
        return self._issue(node)

    def list_comments(self, number: int) -> list[Comment]:
        raw = self._run(["api", "--paginate", f"repos/{self.owner}/{self.repo}/issues/{number}/comments", "--jq", ".[] | {id, body, created_at, login: .user.login}"])
        comments = []
        for line in raw.splitlines():
            if line.strip():
                d = json.loads(line)
                comments.append(Comment(d["id"], d["body"] or "", d["login"], d["created_at"]))
        return comments

    def post_comment(self, number: int, body: str) -> Comment:
        raw = self._run(["api", "-X", "POST", f"repos/{self.owner}/{self.repo}/issues/{number}/comments", "-F", "body=@-"], stdin=body)
        d = json.loads(raw)
        return Comment(d["id"], d["body"] or "", d["user"]["login"], d["created_at"])

    # -- project -----------------------------------------------------------------------
    def project_info(self) -> ProjectInfo:
        if self._project:
            return self._project
        q = ("query{ user(login:\"%s\"){ projectV2(number:%d){ id fields(first:40){ nodes{ ... on ProjectV2SingleSelectField{ id name options{ id name } } } } } } }"
             % (self.project_owner, self.project_number))
        data = self._graphql(q)["user"]["projectV2"]
        if data is None:
            raise NotFound("project not found or not readable")
        status = next((f for f in data["fields"]["nodes"] if f and f.get("name") == "Status"), None)
        if not status:
            raise TransportError("project has no Status single-select field")
        self._project = ProjectInfo(data["id"], status["id"], {o["name"]: o["id"] for o in status["options"]})
        return self._project

    _ITEM_FIELDS = ("id updatedAt fieldValues(first:16){ nodes{ ... on ProjectV2ItemFieldSingleSelectValue{ name field{ ... on ProjectV2FieldCommon{ name } } } "
                    "... on ProjectV2ItemFieldTextValue{ text field{ ... on ProjectV2FieldCommon{ name } } } } } content{ ... on Issue{ number } }")

    @staticmethod
    def _item(node: dict) -> ProjectItem:
        values = {n["field"]["name"]: (n.get("name") if "name" in n else n.get("text")) for n in node["fieldValues"]["nodes"] if n}
        content = node.get("content") or {}
        return ProjectItem(node["id"], content.get("number"), values.get("Status"), values.get("Stable ID"), node["updatedAt"])

    def list_project_items(self) -> list[ProjectItem]:
        out: list[ProjectItem] = []
        after = "null"
        while True:
            q = ("query{ user(login:\"%s\"){ projectV2(number:%d){ items(first:100, after:%s){ pageInfo{hasNextPage endCursor} nodes{ %s } } } } }"
                 % (self.project_owner, self.project_number, after, self._ITEM_FIELDS))
            page = self._graphql(q)["user"]["projectV2"]["items"]
            out.extend(self._item(n) for n in page["nodes"])
            if not page["pageInfo"]["hasNextPage"]:
                return out
            after = json.dumps(page["pageInfo"]["endCursor"])

    def get_project_item(self, item_id: str) -> ProjectItem:
        q = "query{ node(id:\"%s\"){ ... on ProjectV2Item{ %s } } }" % (item_id, self._ITEM_FIELDS)
        node = self._graphql(q)["node"]
        if not node:
            raise NotFound(f"project item {item_id} not found")
        return self._item(node)

    # -- pull requests -----------------------------------------------------------------
    def get_pull_request(self, number: int) -> PullRequestRecord:
        """Head, state, status rollup and *every* review (paginated). A page that is
        malformed, a total that does not match the collected count, or a missing cursor on a
        page that claims more, refuses instead of returning a truncated review set."""
        q = ("query{ repository(owner:\"%s\", name:\"%s\"){ pullRequest(number:%d){ number state merged headRefOid "
             "reviews(first:100){ totalCount pageInfo{hasNextPage endCursor} nodes{ state submittedAt author{login} commit{oid} } } "
             "commits(last:1){ nodes{ commit{ statusCheckRollup{ state } } } } } } }" % (self.owner, self.repo, number))
        pr = self._graphql(q)["repository"]["pullRequest"]
        if pr is None:
            raise NotFound(f"pull request #{number} not found")
        nodes, total = self._review_page(pr.get("reviews"), number)
        page = pr["reviews"]["pageInfo"]
        while page.get("hasNextPage"):
            cursor = page.get("endCursor")
            if not cursor:
                raise TransportError(f"PR #{number} reviews: page claims more results without a cursor")
            more = ("query{ repository(owner:\"%s\", name:\"%s\"){ pullRequest(number:%d){ reviews(first:100, after:%s){ totalCount pageInfo{hasNextPage endCursor} nodes{ state submittedAt author{login} commit{oid} } } } } }"
                    % (self.owner, self.repo, number, json.dumps(cursor)))
            reviews = (self._graphql(more)["repository"].get("pullRequest") or {}).get("reviews")
            page_nodes, page_total = self._review_page(reviews, number)
            if page_total != total:
                raise TransportError(f"PR #{number} reviews changed while paginating ({total} -> {page_total}); retry")
            nodes.extend(page_nodes)
            page = reviews["pageInfo"]
        if len(nodes) != total:
            raise TransportError(f"PR #{number} reviews: collected {len(nodes)} of {total}; refusing a truncated review set")
        rollup = ((pr.get("commits") or {}).get("nodes") or [{}])[0].get("commit", {}).get("statusCheckRollup")
        reviews = tuple({"state": r["state"], "commit": (r.get("commit") or {}).get("oid"), "author": (r.get("author") or {}).get("login"), "submitted_at": r.get("submittedAt")} for r in nodes)
        return PullRequestRecord(pr["number"], pr["state"], pr["headRefOid"], bool(pr["merged"]), reviews, (rollup or {}).get("state") if rollup else None)

    @staticmethod
    def _review_page(reviews, number: int) -> tuple[list[dict], int]:
        if not isinstance(reviews, dict) or not isinstance(reviews.get("nodes"), list) or not isinstance(reviews.get("pageInfo"), dict) or not isinstance(reviews.get("totalCount"), int):
            raise TransportError(f"PR #{number} reviews: malformed page")
        for node in reviews["nodes"]:
            if not isinstance(node, dict) or "state" not in node:
                raise TransportError(f"PR #{number} reviews: malformed review node")
        return list(reviews["nodes"]), reviews["totalCount"]
