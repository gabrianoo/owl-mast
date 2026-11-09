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

from .errors import NotFound, Outage, PermissionDenied, Refused, TransportError

MARKER_RE = re.compile(r"<!-- unattended (?P<attrs>[^>]*?) -->")
# Marker values must survive ``render_marker`` → comment → ``parse_marker`` unchanged: no whitespace,
# no ``=``, no ``>`` and no ``--``. Run ids, story ids, operation names, SHAs and PR numbers fit.
MARKER_VALUE_RE = re.compile(r"^[A-Za-z0-9._:/-]+$")
MARKER_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")


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
    repository: str | None = None  # ``owner/name`` of the linked issue; None for drafts or unknown content


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
    """Render a marker whose every key and value reads back identically through
    :func:`parse_marker`. A value with whitespace, ``=``, ``>`` or ``--`` would be split or cut
    on the way back and refuses (``marker-value-invalid``) before anything is posted."""
    for key, value in attrs.items():
        if not MARKER_KEY_RE.match(str(key)):
            raise Refused(f"marker key {key!r} is not a lowercase identifier", code="marker-value-invalid", key=str(key))
        if not isinstance(value, str) or not MARKER_VALUE_RE.match(value) or "--" in value:
            raise Refused(f"marker value {key}={value!r} cannot round-trip through a comment marker (allowed: [A-Za-z0-9._:/-], no '--')", code="marker-value-invalid", key=str(key), value=str(value))
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
    def viewer_login(self) -> str: ...


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
            if args[:2] == ["api", "graphql"]:
                # ``gh api graphql`` exits 1 when the response carries GraphQL errors and still prints the
                # response: classify on the typed errors first, before the generic stderr text
                errors = self._graphql_errors_in(proc.stdout)
                if errors:
                    raise self._classify_graphql_errors(errors)
            raise classify(proc.returncode, proc.stderr)
        return proc.stdout

    @staticmethod
    def _graphql_errors_in(stdout: str) -> list | None:
        try:
            data = json.loads(stdout) if stdout and stdout.strip() else None
        except json.JSONDecodeError:
            return None
        return data["errors"] if isinstance(data, dict) and isinstance(data.get("errors"), list) and data["errors"] else None

    @staticmethod
    def _shaped(read, what: str):
        """Read a value out of a GraphQL response; a missing key or an unexpected type is a
        classified transport failure, never a raw ``KeyError``/``TypeError``."""
        try:
            return read()
        except (KeyError, TypeError, IndexError, AttributeError) as exc:
            raise TransportError(f"{what}: unexpected response shape ({type(exc).__name__}: {exc})") from exc

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
            raise self._classify_graphql_errors(data["errors"])
        if not isinstance(data.get("data"), dict):
            raise TransportError(f"GraphQL response data is {type(data.get('data')).__name__}, not an object")
        return data["data"]

    @staticmethod
    def _classify_graphql_errors(errors) -> TransportError:
        """Classify on the error ``type`` GitHub reports (``RATE_LIMITED``, ``FORBIDDEN``,
        ``NOT_FOUND``, ``INSUFFICIENT_SCOPES``); the message text is a fallback only when no
        error carries a type."""
        entries = [e for e in errors if isinstance(e, dict)] if isinstance(errors, list) else []
        messages = "; ".join(str(e.get("message", "")) for e in entries) or str(errors)[:300]
        types = {str(e.get("type")).upper() for e in entries if e.get("type")}
        if types:
            if "RATE_LIMITED" in types:
                return Outage(f"GraphQL rate limited: {messages[:300]}")
            if types & {"FORBIDDEN", "INSUFFICIENT_SCOPES", "UNAUTHORIZED"}:
                return PermissionDenied(f"GraphQL denied: {messages[:300]}")
            if "NOT_FOUND" in types:
                return NotFound(f"GraphQL not found: {messages[:300]}")
            return TransportError(f"GraphQL error ({', '.join(sorted(types))}): {messages[:300]}")
        low = messages.lower()
        if "rate limit" in low:
            return Outage(f"GraphQL rate limited: {messages[:300]}")
        if "permission" in low or "do not have" in low or "does not have" in low or "forbidden" in low:
            return PermissionDenied(f"GraphQL denied: {messages[:300]}")
        if "could not resolve" in low or "not found" in low:
            return NotFound(f"GraphQL not found: {messages[:300]}")
        return TransportError(f"GraphQL error: {messages[:300]}")

    @staticmethod
    def _complete(connection, what: str) -> list:
        """The nodes of a connection that was requested whole: a page that claims more refuses
        instead of returning a truncated field, label or option set."""
        if not isinstance(connection, dict) or not isinstance(connection.get("nodes"), list):
            raise TransportError(f"{what}: malformed connection")
        if (connection.get("pageInfo") or {}).get("hasNextPage"):
            raise TransportError(f"{what}: more entries than requested; refusing a truncated read")
        return connection["nodes"]

    def viewer_login(self) -> str:
        """The GitHub login the transport acts as: the only author whose markers are trusted."""
        raw = self._run(["api", "user", "--jq", ".login"]).strip()
        if not raw:
            raise TransportError("gh api user returned no login")
        return raw

    # -- issues ------------------------------------------------------------------------
    _ISSUE_FIELDS = "number id title state stateReason updatedAt closedAt body labels(first:50){pageInfo{hasNextPage} nodes{name}} parent{number}"

    @classmethod
    def _issue(cls, node: dict) -> IssueRecord:
        return cls._shaped(lambda: IssueRecord(
            number=node["number"], node_id=node["id"], title=node["title"], state=node["state"],
            state_reason=node.get("stateReason"), updated_at=node["updatedAt"], closed_at=node.get("closedAt"),
            body=node.get("body") or "", labels=tuple(l["name"] for l in cls._complete(node.get("labels"), f"issue #{node.get('number')} labels")),
            parent_number=(node.get("parent") or {}).get("number"),
        ), f"issue #{node.get('number') if isinstance(node, dict) else node!r}")

    def list_issues(self) -> list[IssueRecord]:
        out: list[IssueRecord] = []
        after = "null"
        while True:
            q = ("query{ repository(owner:\"%s\", name:\"%s\"){ issues(first:100, after:%s, states:[OPEN,CLOSED], orderBy:{field:CREATED_AT, direction:ASC}){ pageInfo{hasNextPage endCursor} nodes{ %s } } } }"
                 % (self.owner, self.repo, after, self._ISSUE_FIELDS))
            data = self._graphql(q)
            page = self._shaped(lambda: data["repository"]["issues"], "issues page")
            out.extend(self._issue(n) for n in self._shaped(lambda: list(page["nodes"]), "issues page"))
            if not self._shaped(lambda: page["pageInfo"]["hasNextPage"], "issues page"):
                return out
            after = json.dumps(self._shaped(lambda: page["pageInfo"]["endCursor"], "issues page"))

    def get_issue(self, number: int) -> IssueRecord:
        q = "query{ repository(owner:\"%s\", name:\"%s\"){ issue(number:%d){ %s } } }" % (self.owner, self.repo, number, self._ISSUE_FIELDS)
        data = self._graphql(q)
        node = self._shaped(lambda: data["repository"]["issue"], f"issue #{number}")
        if node is None:
            raise NotFound(f"issue #{number} not found")
        return self._issue(node)

    @staticmethod
    def _comment(d, where: str) -> Comment:
        """One comment from the REST shape; anything unexpected is a classified transport
        failure, never a raw ``KeyError``/``TypeError`` escaping the fail-closed contract."""
        try:
            if not isinstance(d, dict):
                raise TypeError(f"comment is {type(d).__name__}")
            login = d["login"] if "login" in d else d["user"]["login"]
            return Comment(int(d["id"]), d.get("body") or "", str(login), str(d["created_at"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise TransportError(f"{where}: unexpected comment JSON ({exc})") from exc

    def list_comments(self, number: int) -> list[Comment]:
        raw = self._run(["api", "--paginate", f"repos/{self.owner}/{self.repo}/issues/{number}/comments", "--jq", ".[] | {id, body, created_at, login: .user.login}"])
        comments = []
        for line in raw.splitlines():
            if line.strip():
                try:
                    d = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise TransportError(f"issue #{number} comments: line is not JSON ({exc})") from exc
                comments.append(self._comment(d, f"issue #{number} comments"))
        return comments

    def post_comment(self, number: int, body: str) -> Comment:
        raw = self._run(["api", "-X", "POST", f"repos/{self.owner}/{self.repo}/issues/{number}/comments", "-F", "body=@-"], stdin=body)
        try:
            d = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise TransportError(f"issue #{number} comment post: response is not JSON ({exc}); the comment may have been posted", posted_unverified=True) from exc
        return self._comment(d, f"issue #{number} comment post")

    # -- project -----------------------------------------------------------------------
    # ``repositoryOwner`` resolves a user or an organization; ``ProjectV2Owner`` is implemented by both,
    # so an organization-owned Project is read the same way instead of crashing on ``user: null``.
    _PROJECT_SELECTOR = "repositoryOwner(login:\"%s\"){ ... on ProjectV2Owner{ projectV2(number:%d){ %s } } }"

    def _project_node(self, inner: str) -> dict:
        data = self._graphql("query{ %s }" % (self._PROJECT_SELECTOR % (self.project_owner, self.project_number, inner)))
        owner = data.get("repositoryOwner")
        if not isinstance(owner, dict):
            raise NotFound(f"project owner {self.project_owner!r} not found or not readable")
        project = owner.get("projectV2")
        if not isinstance(project, dict):
            raise NotFound(f"project #{self.project_number} of {self.project_owner!r} not found or not readable")
        return project

    def project_info(self) -> ProjectInfo:
        if self._project:
            return self._project
        data = self._project_node("id fields(first:50){ pageInfo{hasNextPage} nodes{ ... on ProjectV2SingleSelectField{ id name options{ id name } } } }")
        fields = self._complete(data.get("fields"), "project fields")
        status = next((f for f in fields if f and f.get("name") == "Status"), None)
        if not status:
            raise TransportError("project has no Status single-select field")
        self._project = ProjectInfo(data["id"], status["id"], {o["name"]: o["id"] for o in status["options"]})
        return self._project

    _ITEM_FIELDS = ("id updatedAt fieldValues(first:30){ pageInfo{hasNextPage} nodes{ ... on ProjectV2ItemFieldSingleSelectValue{ name field{ ... on ProjectV2FieldCommon{ name } } } "
                    "... on ProjectV2ItemFieldTextValue{ text field{ ... on ProjectV2FieldCommon{ name } } } } } content{ ... on Issue{ number repository{ nameWithOwner } } }")

    @classmethod
    def _item(cls, node: dict) -> ProjectItem:
        def build():
            values = {n["field"]["name"]: (n.get("name") if "name" in n else n.get("text")) for n in cls._complete(node.get("fieldValues"), f"project item {node.get('id')} field values") if n}
            content = node.get("content") or {}
            return ProjectItem(node["id"], content.get("number"), values.get("Status"), values.get("Stable ID"), node["updatedAt"], (content.get("repository") or {}).get("nameWithOwner"))
        return cls._shaped(build, f"project item {node.get('id') if isinstance(node, dict) else node!r}")

    def list_project_items(self) -> list[ProjectItem]:
        out: list[ProjectItem] = []
        after = "null"
        while True:
            project = self._project_node("items(first:100, after:%s){ pageInfo{hasNextPage endCursor} nodes{ %s } }" % (after, self._ITEM_FIELDS))
            page = self._shaped(lambda: project["items"], "project items page")
            out.extend(self._item(n) for n in self._shaped(lambda: list(page["nodes"]), "project items page"))
            if not self._shaped(lambda: page["pageInfo"]["hasNextPage"], "project items page"):
                return out
            after = json.dumps(self._shaped(lambda: page["pageInfo"]["endCursor"], "project items page"))

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
        data = self._graphql(q)
        pr = self._shaped(lambda: data["repository"]["pullRequest"], f"PR #{number}")
        if pr is None:
            raise NotFound(f"pull request #{number} not found")
        if not isinstance(pr, dict) or not isinstance(pr.get("reviews"), dict) or not isinstance(pr["reviews"].get("pageInfo"), dict):
            raise TransportError(f"PR #{number}: malformed pull request node")
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
        def build():
            rollup = ((pr.get("commits") or {}).get("nodes") or [{}])[0].get("commit", {}).get("statusCheckRollup")
            reviews = tuple({"state": r["state"], "commit": (r.get("commit") or {}).get("oid"), "author": (r.get("author") or {}).get("login"), "submitted_at": r.get("submittedAt")} for r in nodes)
            return PullRequestRecord(pr["number"], pr["state"], pr["headRefOid"], bool(pr["merged"]), reviews, (rollup or {}).get("state") if rollup else None)
        return self._shaped(build, f"PR #{number}")

    @staticmethod
    def _review_page(reviews, number: int) -> tuple[list[dict], int]:
        if not isinstance(reviews, dict) or not isinstance(reviews.get("nodes"), list) or not isinstance(reviews.get("pageInfo"), dict) or not isinstance(reviews.get("totalCount"), int):
            raise TransportError(f"PR #{number} reviews: malformed page")
        for node in reviews["nodes"]:
            if not isinstance(node, dict) or "state" not in node:
                raise TransportError(f"PR #{number} reviews: malformed review node")
        return list(reviews["nodes"]), reviews["totalCount"]
