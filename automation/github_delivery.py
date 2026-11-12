"""GitHub-authoritative state for the supervised bmad-build → bmad-review → bmad-walkthrough loop.

GitHub owns every piece of delivery state; local files under ``.bmad-work/`` are disposable
working copies. This helper is the only writer the skills use, so every write has one
deterministic shape:

- Ticket status: the Owl Mast engineering Project's ``Status`` field.
- Build specs: one issue (story spec) or pull-request (fix-round spec) comment per spec key,
  marked ``<!-- bmad:spec key=... -->`` and edited in place.
- Review rounds: one marked pull-request review per round, ``<!-- bmad:review round=N verdict=V -->``.
- Review findings: one review thread per finding, marked ``<!-- bmad:finding id=... -->``: inline
  when the line is in the reviewed diff, otherwise a file-level thread.
- Ticket claims: a short-lived issue comment marked ``<!-- bmad:claim token=... -->``.

Usage (from the repository root): ``python3 -m automation.github_delivery <command> --help``.
Requires an authenticated ``gh`` CLI. Python 3.9+ standard library only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

REPO = os.environ.get("OWL_GH_REPO", "gabrianoo/owl-mast")
PROJECT_OWNER = os.environ.get("OWL_GH_PROJECT_OWNER", "gabrianoo")
PROJECT_NUMBER = int(os.environ.get("OWL_GH_PROJECT_NUMBER", "2"))

STATUSES = ("Backlog", "Ready", "In progress", "In review", "Blocked", "Done")
MAX_REVIEW_ROUNDS = 6
COMMENT_LIMIT = 65536

SPEC_MARKER = re.compile(r"<!-- bmad:spec key=([A-Za-z0-9._-]+) -->")
REVIEW_MARKER = re.compile(r"<!-- bmad:review round=(\d+) verdict=(clean|changes) -->")
FINDING_MARKER = re.compile(r"<!-- bmad:finding id=([A-Za-z0-9._-]+) -->")
CLAIM_MARKER = re.compile(r"<!-- bmad:claim token=([0-9a-f]{32}) -->")
CLAIM_STALE_SECONDS = 900
BODY_SENTINEL = "<!-- bmad:spec-body -->"
HUNK = re.compile(r"^@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
FULL_SHA = re.compile(r"[0-9a-f]{40}")

Runner = Callable[[Sequence[str], Optional[str]], str]


class DeliveryError(RuntimeError):
    """A refusal or failed GitHub operation. Exit code 2, message on stderr."""


def gh_runner(args: Sequence[str], stdin: Optional[str] = None) -> str:
    try:
        done = subprocess.run(["gh", *args], input=stdin, capture_output=True, text=True, timeout=120)
    except FileNotFoundError as error:
        raise DeliveryError("gh CLI is not installed; install and authenticate it (gh auth login)") from error
    if done.returncode != 0:
        raise DeliveryError(f"gh {' '.join(args[:3])} failed: {done.stderr.strip() or done.stdout.strip()}")
    return done.stdout


# --------------------------------------------------------------------------- spec comments


def render_spec_comment(key: str, spec_text: str) -> str:
    """Serialize a spec file (YAML frontmatter + Markdown body) into its GitHub comment."""
    if not SPEC_MARKER.fullmatch(f"<!-- bmad:spec key={key} -->"):
        raise DeliveryError(f"invalid spec key {key!r}: use letters, digits, '.', '_' or '-'")
    match = re.match(r"\A---\n(.*?)\n---\n?(.*)\Z", spec_text, re.S)
    if not match:
        raise DeliveryError("spec file must start with a '---' YAML frontmatter block")
    frontmatter, body = match.group(1), match.group(2)
    if "```" in frontmatter or BODY_SENTINEL in frontmatter:
        raise DeliveryError("spec frontmatter must not contain code fences or the body sentinel")
    comment = (
        f"<!-- bmad:spec key={key} -->\n"
        f"**BMAD spec** `{key}` — machine-managed by the GitHub delivery workflow "
        "(docs/github-delivery-workflow.md). Change it through bmad-build, not by hand.\n\n"
        f"```yaml\n{frontmatter}\n```\n{BODY_SENTINEL}\n{body}"
    )
    if len(comment) > COMMENT_LIMIT:
        raise DeliveryError(f"spec comment is {len(comment)} characters; GitHub's limit is {COMMENT_LIMIT}")
    return comment


def parse_spec_comment(comment: str) -> Tuple[str, str]:
    """Return (key, spec file text) from a comment produced by render_spec_comment."""
    marker = SPEC_MARKER.search(comment)
    if not marker:
        raise DeliveryError("comment carries no bmad:spec marker")
    rest = comment[marker.end():]
    start = rest.find("```yaml\n")
    end = rest.find(f"\n```\n{BODY_SENTINEL}\n")
    if start < 0 or end < start:
        raise DeliveryError(f"spec comment {marker.group(1)} is malformed (missing yaml block or body sentinel)")
    frontmatter = rest[start + len("```yaml\n"):end]
    body = rest[end + len(f"\n```\n{BODY_SENTINEL}\n"):]
    return marker.group(1), f"---\n{frontmatter}\n---\n{body}"


# --------------------------------------------------------------------------- review anchoring


def diff_right_lines(diff_text: str) -> Dict[str, set]:
    """Map each file in a unified diff to the new-side line numbers a review comment may anchor to.

    File headers are read only between hunks: the ``@@`` header's line counts say how long a hunk
    is, so an added line whose text starts with ``++ `` (it reads ``+++ ...``) stays content.
    """
    lines: Dict[str, set] = {}
    current: Optional[str] = None
    new_line = old_left = new_left = 0
    for raw in diff_text.split("\n"):  # not splitlines(): a form feed or U+2028 in content is not a line end
        raw = raw.rstrip("\r")
        if old_left > 0 or new_left > 0:
            if raw.startswith("\\"):
                continue
            mark = raw[:1] or " "  # a context line whose trailing blank was stripped
            if mark == "-" and old_left > 0:
                old_left -= 1
                continue
            if mark in "+ " and new_left > 0 and (mark == "+" or old_left > 0):
                if current is not None:
                    lines[current].add(new_line)
                new_line += 1
                new_left -= 1
                old_left -= mark == " "
                continue
            old_left = new_left = 0  # the hunk is shorter than its header says: read the line as a header
        hunk = HUNK.match(raw)
        if hunk:
            old_left = 1 if hunk.group(1) is None else int(hunk.group(1))
            new_line = int(hunk.group(2))
            new_left = 1 if hunk.group(3) is None else int(hunk.group(3))
        elif raw.startswith("+++ "):
            target = raw[4:].strip()
            current = None if target == "/dev/null" else re.sub(r"^b/", "", target)
            if current is not None:
                lines.setdefault(current, set())
    return lines


@dataclass
class Finding:
    id: str
    path: str
    body: str
    line: Optional[int] = None


def build_review_payload(
    round_number: int,
    verdict: str,
    summary: str,
    findings: List[Finding],
    diff_text: str,
    commit_id: str,
) -> Tuple[dict, List[dict]]:
    """Build one review round: (create-review payload, file-level comment payloads).

    A finding on a line of the reviewed diff is an inline comment of the review. GitHub's
    create-review endpoint has no ``subject_type``, so a finding outside the hunks, or on a file the
    reviewed diff does not hold, is a separate ``POST pulls/{n}/comments`` payload with ``subject_type: file``
    (each carries its ``finding_id``, which the caller removes before sending). Either way every
    finding becomes one resolvable thread.
    """
    if not 1 <= round_number <= MAX_REVIEW_ROUNDS:
        raise DeliveryError(f"review round must be 1..{MAX_REVIEW_ROUNDS}, got {round_number}")
    if verdict not in ("clean", "changes"):
        raise DeliveryError("verdict must be 'clean' or 'changes'")
    if verdict == "clean" and findings:
        raise DeliveryError("a clean review cannot carry findings")
    if verdict == "changes" and not findings:
        raise DeliveryError("a 'changes' review needs at least one finding")
    anchors = diff_right_lines(diff_text)
    if findings and not anchors:
        raise DeliveryError("the pull-request diff has no files to anchor findings to")
    fallback = sorted(anchors)[0] if anchors else None
    comments: List[dict] = []
    file_comments: List[dict] = []
    seen = set()
    for finding in findings:
        if not FINDING_MARKER.fullmatch(f"<!-- bmad:finding id={finding.id} -->") or finding.id in seen:
            raise DeliveryError(f"finding id {finding.id!r} is invalid or duplicated")
        seen.add(finding.id)
        text = f"<!-- bmad:finding id={finding.id} -->\n**{finding.id}**"
        location = finding.path + (f":{finding.line}" if finding.line else "")
        if finding.path in anchors and finding.line in anchors[finding.path]:
            comments.append({"path": finding.path, "line": finding.line, "side": "RIGHT",
                             "body": f"{text}\n\n{finding.body}"})
            continue
        known = finding.path in anchors
        why = "outside the diff hunks" if known else "file not in the reviewed diff"
        file_comments.append({"finding_id": finding.id, "commit_id": commit_id,
                              "path": finding.path if known else fallback, "subject_type": "file",
                              "body": f"{text} · `{location}` ({why})\n\n{finding.body}"})
    body = f"<!-- bmad:review round={round_number} verdict={verdict} -->\n" \
           f"### bmad-review · round {round_number} of {MAX_REVIEW_ROUNDS} · {verdict}\n\n{summary.strip()}\n"
    if file_comments:
        body += "\nFile-level threads (not on a line of the reviewed diff): " \
                + ", ".join(c["finding_id"] for c in file_comments) + "\n"
    return {"commit_id": commit_id, "event": "COMMENT", "body": body, "comments": comments}, file_comments


# --------------------------------------------------------------------------- GitHub client

REVIEW_FIELDS = "body submittedAt url commit{ oid }"
THREAD_FIELDS = ("id isResolved isOutdated path line "
                 "comments(first:50){ nodes{ author{ login } body url createdAt } }")


def _age_seconds(older: dict, newer: dict) -> float:
    """Seconds between two comments' GitHub timestamps; 0 when either is missing or unreadable."""
    try:
        stamps = [datetime.fromisoformat(c["created_at"].replace("Z", "+00:00")) for c in (older, newer)]
    except (KeyError, AttributeError, ValueError):
        return 0.0
    return (stamps[1] - stamps[0]).total_seconds()


@dataclass
class GitHub:
    run: Runner = gh_runner
    repo: str = REPO
    project_owner: str = PROJECT_OWNER
    project_number: int = PROJECT_NUMBER
    _project: Optional[dict] = field(default=None, repr=False)

    @property
    def owner(self) -> str:
        return self.repo.split("/")[0]

    @property
    def name(self) -> str:
        return self.repo.split("/")[1]

    def graphql(self, query: str, **variables) -> dict:
        args = ["api", "graphql", "-f", f"query={query}"]
        for key, value in variables.items():
            args += ["-F" if isinstance(value, int) else "-f", f"{key}={value}"]
        data = json.loads(self.run(args, None))
        if data.get("errors"):
            raise DeliveryError(f"GraphQL error: {data['errors']}")
        return data["data"]

    def rest(self, method: str, path: str, payload: Optional[dict] = None):
        args = ["api", "-X", method, path]
        if payload is not None:
            args += ["--input", "-"]
        out = self.run(args, json.dumps(payload) if payload is not None else None)
        return json.loads(out) if out.strip() else None

    # ---- project

    def project(self) -> dict:
        if self._project is None:
            q = """query($login:String!,$number:Int!){ user(login:$login){ projectV2(number:$number){ id
                 fields(first:50){ nodes{ ... on ProjectV2SingleSelectField{ id name options{ id name } } } } } } }"""
            data = self.graphql(q, login=self.project_owner, number=self.project_number)["user"]["projectV2"]
            fields = {f["name"]: f for f in data["fields"]["nodes"] if f}
            if "Status" not in fields:
                raise DeliveryError("project has no Status single-select field")
            self._project = {"id": data["id"], "fields": fields}
        return self._project

    def issue_item(self, number: int) -> Tuple[str, str, Optional[str]]:
        """Return (issue node id, project item id or '', current Status)."""
        q = """query($owner:String!,$name:String!,$number:Int!){ repository(owner:$owner,name:$name){
               issueOrPullRequest(number:$number){ ... on Issue{ id projectItems(first:20){ nodes{ id
               project{ id } status: fieldValueByName(name:"Status"){ ... on ProjectV2ItemFieldSingleSelectValue{ name } } } } } } } }"""
        node = self.graphql(q, owner=self.owner, name=self.name, number=number)["repository"]["issueOrPullRequest"]
        if not node or "id" not in node:
            raise DeliveryError(f"#{number} is not an issue in {self.repo}")
        project_id = self.project()["id"]
        for item in node["projectItems"]["nodes"]:
            if item["project"]["id"] == project_id:
                return node["id"], item["id"], (item.get("status") or {}).get("name")
        return node["id"], "", None

    def set_status(self, number: int, status: str, expect: Sequence[str] = (), claim: bool = False) -> dict:
        """Move an issue's Status. ``expect`` guards the move; ``claim`` also serializes rival moves.

        GitHub has no compare-and-set for a Project field, so the guard alone is check-then-act.
        With ``claim`` the run first posts a claim marker comment and backs off when an earlier
        marker exists or the Status changed meanwhile (see ``_claim``).
        """
        if status not in STATUSES:
            raise DeliveryError(f"unknown status {status!r}; choose one of {', '.join(STATUSES)}")
        if claim and (not expect or status in expect):
            raise DeliveryError("--claim needs at least one --expect status, and the target status cannot be one of them")
        issue_id, item_id, current = self.issue_item(number)
        if expect and current not in expect:
            raise DeliveryError(f"#{number} is {current!r}, expected one of {list(expect)}; refusing to move it to {status!r}")
        project = self.project()
        status_field = project["fields"]["Status"]
        option = next((o["id"] for o in status_field["options"] if o["name"] == status), None)
        if option is None:
            raise DeliveryError(f"project Status has no option {status!r}")
        marker = self._claim(number, status, expect) if claim else None
        try:
            if not item_id:
                m = "mutation($p:ID!,$c:ID!){ addProjectV2ItemById(input:{projectId:$p,contentId:$c}){ item{ id } } }"
                item_id = self.graphql(m, p=project["id"], c=issue_id)["addProjectV2ItemById"]["item"]["id"]
            if current != status:
                m = """mutation($p:ID!,$i:ID!,$f:ID!,$o:String!){ updateProjectV2ItemFieldValue(input:{projectId:$p,itemId:$i,
                       fieldId:$f,value:{singleSelectOptionId:$o}}){ projectV2Item{ id } } }"""
                self.graphql(m, p=project["id"], i=item_id, f=status_field["id"], o=option)
        finally:
            leftover = marker is not None and not self._drop_claim(marker)
        result = {"issue": number, "from": current, "to": status}
        if claim:
            result["claimed"] = True
            if leftover:
                result["claim_marker_left"] = marker["html_url"]
        return result

    def _claim(self, number: int, status: str, expect: Sequence[str]) -> dict:
        """Post this run's claim marker and return it, or refuse when another run is ahead.

        Comment ids only grow, so of two markers on the issue the lower id wins and the other run
        backs off. The winner re-reads the Status after its marker is up: a rival that finished (wrote
        the Status, removed its marker) before this marker appeared is caught there. A marker older
        than CLAIM_STALE_SECONDS belongs to a run that died and is ignored.
        """
        token = uuid.uuid4().hex
        mine = self.rest("POST", f"repos/{self.repo}/issues/{number}/comments", {"body": (
            f"<!-- bmad:claim token={token} -->\nbmad-build is claiming this ticket "
            "(docs/github-delivery-workflow.md). This comment is removed once the claim settles.")})
        try:
            for other in self.comments(number):
                if other["id"] >= mine["id"] or not CLAIM_MARKER.match(other.get("body") or ""):
                    continue
                if _age_seconds(other, mine) <= CLAIM_STALE_SECONDS:
                    raise DeliveryError(f"#{number} is being claimed by another run ({other.get('html_url')}); "
                                        f"refusing to move it to {status!r}")
            current = self.issue_item(number)[2]
            if current not in expect:
                raise DeliveryError(f"#{number} became {current!r} while it was being claimed, expected one of "
                                    f"{list(expect)}; refusing to move it to {status!r}")
        except BaseException as error:
            if not self._drop_claim(mine) and isinstance(error, DeliveryError):
                raise DeliveryError(f"{error}; this run's claim marker could not be removed, delete it by hand: "
                                    f"{mine.get('html_url')}") from error
            raise
        return mine

    def _drop_claim(self, marker: dict) -> bool:
        try:
            self.rest("DELETE", f"repos/{self.repo}/issues/comments/{marker['id']}")
        except DeliveryError:
            return False
        return True

    def ready(self) -> List[dict]:
        """Open issues whose project Status is Ready, ordered by Priority option order, then Stable ID."""
        project = self.project()
        priority_order = [o["name"] for o in project["fields"].get("Priority", {}).get("options", [])]
        items, cursor = [], None
        while True:
            q = """query($login:String!,$number:Int!,$after:String){ user(login:$login){ projectV2(number:$number){
                   items(first:100, after:$after){ pageInfo{ hasNextPage endCursor } nodes{
                   status: fieldValueByName(name:"Status"){ ... on ProjectV2ItemFieldSingleSelectValue{ name } }
                   priority: fieldValueByName(name:"Priority"){ ... on ProjectV2ItemFieldSingleSelectValue{ name } }
                   stable: fieldValueByName(name:"Stable ID"){ ... on ProjectV2ItemFieldTextValue{ text } }
                   content{ ... on Issue{ number title url state assignees(first:5){ nodes{ login } } } } } } } } }"""
            variables = {"login": self.project_owner, "number": self.project_number}
            if cursor:
                variables["after"] = cursor
            page = self.graphql(q, **variables)["user"]["projectV2"]["items"]
            for node in page["nodes"]:
                content = node.get("content") or {}
                if (node.get("status") or {}).get("name") != "Ready" or content.get("state") != "OPEN":
                    continue
                priority = (node.get("priority") or {}).get("name")
                items.append({
                    "number": content["number"], "title": content["title"], "url": content["url"],
                    "stable_id": (node.get("stable") or {}).get("text"), "priority": priority,
                    "assignees": [a["login"] for a in content["assignees"]["nodes"]],
                })
            if not page["pageInfo"]["hasNextPage"]:
                break
            cursor = page["pageInfo"]["endCursor"]
        rank = {name: index for index, name in enumerate(priority_order)}
        items.sort(key=lambda i: (rank.get(i["priority"], len(rank)), i["stable_id"] or "", i["number"]))
        return items

    # ---- spec comments

    def comments(self, number: int) -> List[dict]:
        out = self.run(["api", "--paginate", "--slurp", f"repos/{self.repo}/issues/{number}/comments"], None)
        pages = json.loads(out)
        return [c for page in pages for c in page]

    def spec_comments(self, number: int) -> Dict[str, dict]:
        found: Dict[str, dict] = {}
        for comment in self.comments(number):
            marker = SPEC_MARKER.match(comment.get("body") or "")
            if marker:
                if marker.group(1) in found:
                    raise DeliveryError(f"#{number} has two spec comments for key {marker.group(1)}; delete the stale one")
                found[marker.group(1)] = comment
        return found

    def spec_pull(self, number: int, key: Optional[str], out: Path) -> dict:
        specs = self.spec_comments(number)
        if key is None:
            if len(specs) != 1:
                raise DeliveryError(f"#{number} has {len(specs)} spec comments ({', '.join(specs) or 'none'}); pass --key")
            key = next(iter(specs))
        if key not in specs:
            raise DeliveryError(f"#{number} has no spec comment for key {key}")
        parsed_key, text = parse_spec_comment(specs[key]["body"])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        return {"number": number, "key": parsed_key, "file": str(out), "comment": specs[key]["html_url"]}

    def spec_push(self, number: int, key: str, spec_file: Path) -> dict:
        body = render_spec_comment(key, spec_file.read_text(encoding="utf-8"))
        existing = self.spec_comments(number).get(key)
        if existing:
            if existing["body"] == body:
                return {"number": number, "key": key, "comment": existing["html_url"], "changed": False}
            done = self.rest("PATCH", f"repos/{self.repo}/issues/comments/{existing['id']}", {"body": body})
        else:
            done = self.rest("POST", f"repos/{self.repo}/issues/{number}/comments", {"body": body})
        return {"number": number, "key": key, "comment": done["html_url"], "changed": True}

    def spec_list(self, number: int) -> List[dict]:
        return [{"key": k, "comment": c["html_url"], "updated_at": c["updated_at"]}
                for k, c in self.spec_comments(number).items()]

    # ---- reviews

    def review_state(self, pr: int) -> dict:
        q = """query($owner:String!,$name:String!,$number:Int!){ repository(owner:$owner,name:$name){ pullRequest(number:$number){
               number url state headRefName headRefOid baseRefName isDraft mergeable
               closingIssuesReferences(first:5){ nodes{ number } }
               reviews(first:100){ pageInfo{ hasNextPage endCursor } nodes{ %s } }
               reviewThreads(first:100){ pageInfo{ hasNextPage endCursor } nodes{ %s } } } } }""" % (REVIEW_FIELDS, THREAD_FIELDS)
        pr_node = self.graphql(q, owner=self.owner, name=self.name, number=pr)["repository"]["pullRequest"]
        if not pr_node:
            raise DeliveryError(f"#{pr} is not a pull request in {self.repo}")
        rounds = []
        for review in self._all_nodes(pr, "reviews", REVIEW_FIELDS, pr_node["reviews"]):
            marker = REVIEW_MARKER.match(review.get("body") or "")
            if marker:
                rounds.append({"round": int(marker.group(1)), "verdict": marker.group(2),
                               "commit": (review.get("commit") or {}).get("oid"),
                               "url": review["url"], "submitted_at": review["submittedAt"]})
        rounds.sort(key=lambda r: r["round"])
        bmad, other = [], []
        for thread in self._all_nodes(pr, "reviewThreads", THREAD_FIELDS, pr_node["reviewThreads"]):
            comments = thread["comments"]["nodes"]
            marker = FINDING_MARKER.search(comments[0]["body"]) if comments else None
            entry = {
                "thread_id": thread["id"], "finding_id": marker.group(1) if marker else None,
                "resolved": thread["isResolved"], "outdated": thread["isOutdated"],
                "path": thread["path"], "line": thread["line"], "url": comments[0]["url"] if comments else None,
                "comments": [{"author": (c.get("author") or {}).get("login"), "body": c["body"]} for c in comments],
            }
            (bmad if marker else other).append(entry)
        open_bmad = [t for t in bmad if not t["resolved"]]
        last = rounds[-1]["round"] if rounds else 0
        return {
            "pr": pr_node["number"], "url": pr_node["url"], "state": pr_node["state"],
            "head": pr_node["headRefName"], "head_sha": pr_node["headRefOid"], "base": pr_node["baseRefName"],
            "draft": pr_node["isDraft"], "mergeable": pr_node["mergeable"],
            "issues": [n["number"] for n in pr_node["closingIssuesReferences"]["nodes"]],
            "rounds": rounds, "rounds_done": last, "next_round": last + 1, "max_rounds": MAX_REVIEW_ROUNDS,
            "last_round_at_head": bool(rounds) and rounds[-1]["commit"] == pr_node["headRefOid"],
            "open_findings": open_bmad, "resolved_findings": len(bmad) - len(open_bmad),
            "finding_ids": [t["finding_id"] for t in bmad],
            "other_unresolved_threads": [t for t in other if not t["resolved"]],
        }

    def _all_nodes(self, pr: int, connection: str, selection: str, first_page: dict) -> List[dict]:
        """Every node of a pull-request connection: the first page plus all following pages."""
        nodes, info = list(first_page["nodes"]), first_page["pageInfo"]
        while info["hasNextPage"]:
            q = """query($owner:String!,$name:String!,$number:Int!,$after:String!){ repository(owner:$owner,name:$name){
                   pullRequest(number:$number){ %s(first:100, after:$after){ pageInfo{ hasNextPage endCursor }
                   nodes{ %s } } } } }""" % (connection, selection)
            page = self.graphql(q, owner=self.owner, name=self.name, number=pr,
                                after=info["endCursor"])["repository"]["pullRequest"][connection]
            nodes += page["nodes"]
            info = page["pageInfo"]
        return nodes

    def post_review(self, pr: int, round_number: int, verdict: str, summary: str, findings: List[Finding],
                    commit: str) -> dict:
        """Post one round against ``commit``, the SHA the reviewer staged, never the head at posting time.

        File-level findings go first, one comment each, and are skipped when their id already has a
        thread; the review with the round marker goes last. So a run that failed part-way is finished
        by running the same command again, and a round is recorded only once everything is up.
        """
        if not FULL_SHA.fullmatch(commit):
            raise DeliveryError(f"--commit must be the full 40-character reviewed SHA, got {commit!r}")
        state = self.review_state(pr)
        if state["state"] != "OPEN":
            raise DeliveryError(f"PR #{pr} is {state['state']}; a review round needs an open pull request")
        if round_number != state["next_round"]:
            hint = ""
            if round_number == state["rounds_done"]:
                hint = (f". Round {round_number} is already posted ({state['rounds'][-1]['url']}): if this is a rerun "
                        "of a post that timed out, it went through; do not post it again under the next number")
            raise DeliveryError(f"PR #{pr} is at round {state['rounds_done']}; the next review must be round "
                                f"{state['next_round']}{hint}")
        if commit != state["head_sha"]:
            try:
                compared = self.rest("GET", f"repos/{self.repo}/compare/{commit}...{state['head_sha']}") or {}
            except DeliveryError as error:
                raise DeliveryError(f"reviewed commit {commit} cannot be compared with the head of PR #{pr}: {error}") from error
            if compared.get("status") not in ("identical", "ahead"):
                raise DeliveryError(f"reviewed commit {commit} is not in the history of PR #{pr}'s head "
                                    f"{state['head_sha']}; review the current head again")
            summary = f"{summary.strip()}\n\nThe PR head moved to `{state['head_sha']}` after this review."
        summary = f"{summary.strip()}\n\nReviewed commit: `{commit}`."
        ahead = self.rest("GET", f"repos/{self.repo}/compare/{state['base']}...{commit}") or {}
        if not ahead.get("ahead_by"):
            raise DeliveryError(f"reviewed commit {commit} is not ahead of {state['base']}, so it is not a commit of PR #{pr}")
        if len(ahead.get("files") or []) >= 300:
            raise DeliveryError(f"the diff of PR #{pr} at {commit} has 300 or more files; GitHub truncates it, "
                                "so findings cannot be anchored reliably")
        diff_text = self.run(["api", "-H", "Accept: application/vnd.github.diff",
                              f"repos/{self.repo}/compare/{state['base']}...{commit}"], None)
        payload, file_comments = build_review_payload(round_number, verdict, summary, findings, diff_text, commit)
        if len(payload["body"]) > COMMENT_LIMIT:
            raise DeliveryError(f"review body is {len(payload['body'])} characters; GitHub's limit is {COMMENT_LIMIT}")
        posted = set(state["finding_ids"])
        skipped = []
        for comment in file_comments:
            finding_id = comment.pop("finding_id")
            if finding_id in posted:
                skipped.append(finding_id)
            else:
                self.rest("POST", f"repos/{self.repo}/pulls/{pr}/comments", comment)
        done = self.rest("POST", f"repos/{self.repo}/pulls/{pr}/reviews", payload)
        return {"pr": pr, "round": round_number, "verdict": verdict, "url": done.get("html_url"), "commit": commit,
                "findings": len(findings), "file_level": len(file_comments), "already_posted": skipped}

    def resolve(self, thread_ids: Sequence[str]) -> List[str]:
        m = "mutation($t:ID!){ resolveReviewThread(input:{threadId:$t}){ thread{ id isResolved } } }"
        return [self.graphql(m, t=t)["resolveReviewThread"]["thread"]["id"] for t in thread_ids]

    def reply(self, thread_id: str, body: str) -> str:
        m = """mutation($t:ID!,$b:String!){ addPullRequestReviewThreadReply(input:{pullRequestReviewThreadId:$t,body:$b}){
               comment{ url } } }"""
        return self.graphql(m, t=thread_id, b=body)["addPullRequestReviewThreadReply"]["comment"]["url"]


# --------------------------------------------------------------------------- CLI


def _findings(path: Path) -> List[Finding]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise DeliveryError("findings file must hold a JSON array")
    try:
        return [Finding(id=str(f["id"]), path=str(f["path"]), body=str(f["body"]),
                        line=int(f["line"]) if f.get("line") else None) for f in data]
    except (KeyError, TypeError, ValueError) as error:
        raise DeliveryError(f"each finding needs id, path, body and an optional integer line: {error}") from error


def main(argv: Optional[Sequence[str]] = None, client: Optional[GitHub] = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m automation.github_delivery", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("ready", help="list Ready issues in pickup order")
    p = sub.add_parser("status", help="set an issue's Project Status")
    p.add_argument("issue", type=int)
    p.add_argument("to", choices=STATUSES)
    p.add_argument("--expect", action="append", choices=STATUSES, default=[],
                   help="refuse unless the current Status is one of these (repeatable)")
    p.add_argument("--claim", action="store_true",
                   help="serialize rival runs with a claim marker comment; use it when picking up a ticket")
    p = sub.add_parser("spec-pull", help="hydrate a spec file from its issue/PR comment")
    p.add_argument("number", type=int)
    p.add_argument("--key")
    p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("spec-push", help="publish a spec file to its issue/PR comment (create or edit in place)")
    p.add_argument("number", type=int)
    p.add_argument("--file", type=Path, required=True)
    p.add_argument("--key", help="defaults to the file name without .md")
    p = sub.add_parser("spec-list", help="list spec comments on an issue/PR")
    p.add_argument("number", type=int)
    p = sub.add_parser("review-state", help="head, rounds, open bmad findings and other unresolved threads of a PR")
    p.add_argument("pr", type=int)
    p = sub.add_parser("post-review", help="post one bmad-review round")
    p.add_argument("pr", type=int)
    p.add_argument("--round", type=int, required=True)
    p.add_argument("--commit", required=True, help="full SHA of the reviewed commit (head_sha when the diff was staged)")
    p.add_argument("--verdict", choices=("clean", "changes"), required=True)
    p.add_argument("--summary-file", type=Path, required=True)
    p.add_argument("--findings-file", type=Path, help="JSON array of {id, path, line?, body}")
    p = sub.add_parser("reply", help="reply to a review thread")
    p.add_argument("thread_id")
    p.add_argument("--body-file", type=Path, required=True)
    p = sub.add_parser("resolve", help="resolve review threads")
    p.add_argument("thread_ids", nargs="+")
    args = parser.parse_args(argv)
    gh = client or GitHub()
    try:
        if args.command == "ready":
            result = gh.ready()
        elif args.command == "status":
            result = gh.set_status(args.issue, args.to, args.expect, args.claim)
        elif args.command == "spec-pull":
            result = gh.spec_pull(args.number, args.key, args.out)
        elif args.command == "spec-push":
            result = gh.spec_push(args.number, args.key or args.file.stem, args.file)
        elif args.command == "spec-list":
            result = gh.spec_list(args.number)
        elif args.command == "review-state":
            result = gh.review_state(args.pr)
        elif args.command == "post-review":
            findings = _findings(args.findings_file) if args.findings_file else []
            result = gh.post_review(args.pr, args.round, args.verdict,
                                    args.summary_file.read_text(encoding="utf-8"), findings, args.commit)
        elif args.command == "reply":
            result = {"url": gh.reply(args.thread_id, args.body_file.read_text(encoding="utf-8"))}
        else:
            result = {"resolved": gh.resolve(args.thread_ids)}
    except DeliveryError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
