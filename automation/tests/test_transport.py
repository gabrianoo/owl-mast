"""Transport contract tests: realistic ``gh`` responses (GraphQL pages, REST comment lines,
PR reviews, error texts) consumed through ``GhCliTransport`` and the coordinator. These are
fixture tests of the production boundary; they are not live qualification."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from automation.tests.support import IMPLEMENTER, REVIEWER, REVIEW_BRANCH, REVIEW_WORKTREE, make_git_repo, ok_worktree, passing_runner, write_policy
from automation.unattended.backlog import take_snapshot
from automation.unattended.coordinator import Coordinator
from automation.unattended.errors import NotFound, Outage, PermissionDenied, Refused, TransportError
from automation.unattended.github import GhCliTransport, classify
from automation.unattended.policy import load_policy
from automation.unattended.state import Store

ISSUE_FIELDS = lambda n, sid, parent=None, body_extra="", state="OPEN", reason=None, labels=("story",): {  # noqa: E731
    "number": n, "id": f"I_{n}", "title": f"{sid} — t", "state": state, "stateReason": reason, "updatedAt": "2026-11-06T10:00:00Z", "closedAt": None,
    "body": f"<!-- owl-mast-id: {sid} -->\n{body_extra}", "labels": {"nodes": [{"name": l} for l in labels]}, "parent": {"number": parent} if parent else None,
}


class ScriptedGh:
    """Replaces ``GhCliTransport._run`` with canned stdout per request shape."""

    def __init__(self):
        self.calls: list[list[str]] = []
        self.posted: list[str] = []
        self.pr_reviews = [{"state": "CHANGES_REQUESTED", "submittedAt": "1", "author": {"login": "A"}, "commit": {"oid": "HEAD"}},
                           {"state": "APPROVED", "submittedAt": "2", "author": {"login": "B"}, "commit": {"oid": "HEAD"}}]
        self.review_pages: list[list[dict]] | None = None  # when set, reviews are served page by page
        self.malformed_page = False
        self.drift_total = False
        self.head = "HEAD"
        self.comments: list[dict] = []

    def _reviews_payload(self, cursor):
        pages = self.review_pages or [self.pr_reviews]
        index = 0 if cursor is None else int(cursor[1:])
        total = sum(len(p) for p in pages) + (1 if self.drift_total and cursor else 0)
        last = index == len(pages) - 1
        if self.malformed_page and cursor:
            return {"totalCount": total, "nodes": "oops"}
        return {"totalCount": total, "pageInfo": {"hasNextPage": not last, "endCursor": None if last else f"C{index + 1}"}, "nodes": pages[index]}

    def __call__(self, args, stdin=None):
        self.calls.append(args)
        if args[:2] == ["api", "graphql"]:
            query = args[3]
            if "issues(first:100" in query:
                if "after:null" in query:
                    return json.dumps({"data": {"repository": {"issues": {"pageInfo": {"hasNextPage": True, "endCursor": "C1"}, "nodes": [
                        ISSUE_FIELDS(1, "E01", body_extra="**Epic prerequisites:** None\n", labels=("epic",)),
                        ISSUE_FIELDS(20, "OM-01.01", parent=1, body_extra="**Depends on:** None\n", state="CLOSED", reason="COMPLETED")]}}}})
                return json.dumps({"data": {"repository": {"issues": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": [
                    ISSUE_FIELDS(21, "OM-01.02", parent=1, body_extra="**Depends on:** OM-01.01\n")]}}}})
            if "items(first:100" in query:
                def item(n, sid, status):
                    return {"id": f"PVTI_{n}", "updatedAt": "2026-11-06T10:00:00Z", "content": {"number": n, "repository": {"nameWithOwner": "gabrianoo/owl-mast"}},
                            "fieldValues": {"nodes": [{"name": status, "field": {"name": "Status"}}, {"text": sid, "field": {"name": "Stable ID"}}, {}]}}
                return json.dumps({"data": {"repositoryOwner": {"projectV2": {"items": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": [item(1, "E01", "Backlog"), item(20, "OM-01.01", "Done"), item(21, "OM-01.02", "Ready")]}}}}})
            if "pullRequest(number:7)" in query and "reviews(first:100, after:" in query:
                cursor = query.split("after:", 1)[1].split(")", 1)[0].strip('"')
                return json.dumps({"data": {"repository": {"pullRequest": {"reviews": self._reviews_payload(cursor)}}}})
            if "pullRequest(number:7)" in query:
                return json.dumps({"data": {"repository": {"pullRequest": {"number": 7, "state": "OPEN", "merged": False, "headRefOid": self.head,
                                                                           "reviews": self._reviews_payload(None),
                                                                           "commits": {"nodes": [{"commit": {"statusCheckRollup": {"state": "SUCCESS"}}}]}}}}})
            if "projectV2(number:2){ id fields" in query:
                return json.dumps({"data": {"repositoryOwner": {"projectV2": {"id": "PVT", "fields": {"nodes": [{"id": "F", "name": "Status", "options": [{"id": "o1", "name": "Ready"}]}]}}}}})
            raise AssertionError(f"unexpected graphql {query[:80]}")
        if args[:3] == ["api", "user", "--jq"]:
            return "machine\n"
        if args[:2] == ["api", "--paginate"]:
            return "\n".join(json.dumps({"id": i, "body": c["body"], "created_at": "t", "login": "machine"}) for i, c in enumerate(self.comments, start=100))
        if args[:3] == ["api", "-X", "POST"]:
            self.posted.append(stdin)
            self.comments.append({"body": stdin})
            return json.dumps({"id": 99 + len(self.comments), "body": stdin, "user": {"login": "machine"}, "created_at": "t"})
        raise AssertionError(f"unexpected gh call {args[:4]}")


class TransportParsingTests(unittest.TestCase):
    def setUp(self):
        self.gh = ScriptedGh()
        self.t = GhCliTransport("gabrianoo", "owl-mast", "gabrianoo", 2)
        self.t._run = self.gh
        self.t.live = False  # fixture boundary, not production

    def test_issue_pagination_and_normalization(self):
        issues = self.t.list_issues()
        self.assertEqual([i.number for i in issues], [1, 20, 21])
        self.assertEqual(issues[2].parent_number, 1)
        self.assertEqual(issues[1].state_reason, "COMPLETED")
        self.assertEqual(sum(1 for c in self.gh.calls if "issues(first:100" in c[3]), 2)

    def test_project_items_and_snapshot_consumption(self):
        snap = take_snapshot(self.t, "gabrianoo/owl-mast", "now")
        entry = snap.by_id()["OM-01.02"]
        self.assertEqual((entry.status, entry.item_stable_id, entry.depends_on, entry.depends_on_known), ("Ready", "OM-01.02", ("OM-01.01",), True))

    def test_pull_request_reviews_reach_the_coordinator_boundary(self):
        pr = self.t.get_pull_request(7)
        self.assertEqual([r["state"] for r in pr.reviews], ["CHANGES_REQUESTED", "APPROVED"])
        self.assertEqual(pr.checks, "SUCCESS")

    def test_reviews_are_paginated_and_objections_after_page_one_are_seen(self):
        """Round-1 finding R1-E6: an objection on a later page must reach the gate."""
        from automation.unattended.coordinator import outstanding_objections

        self.gh.review_pages = [[{"state": "APPROVED", "submittedAt": "1", "author": {"login": "B"}, "commit": {"oid": "HEAD"}}],
                                [{"state": "CHANGES_REQUESTED", "submittedAt": "2", "author": {"login": "C"}, "commit": {"oid": "HEAD"}}]]
        pr = self.t.get_pull_request(7)
        self.assertEqual(len(pr.reviews), 2)
        self.assertEqual(outstanding_objections(pr), ["C"])
        self.assertEqual(sum(1 for c in self.gh.calls if "reviews(first:100, after:" in c[3]), 1)
        self.gh.review_pages = [[{"state": "CHANGES_REQUESTED", "submittedAt": "1", "author": {"login": "C"}, "commit": {"oid": "HEAD"}}],
                                [{"state": "DISMISSED", "submittedAt": "2", "author": {"login": "C"}, "commit": {"oid": "HEAD"}}]]
        self.assertEqual(outstanding_objections(self.t.get_pull_request(7)), [])

    def test_malformed_or_inconsistent_review_pages_refuse(self):
        self.gh.review_pages = [[{"state": "APPROVED", "submittedAt": "1", "author": {"login": "B"}, "commit": {"oid": "HEAD"}}], [{"state": "APPROVED", "submittedAt": "2", "author": {"login": "D"}, "commit": {"oid": "HEAD"}}]]
        self.gh.malformed_page = True
        with self.assertRaises(TransportError):
            self.t.get_pull_request(7)
        self.gh.malformed_page, self.gh.drift_total = False, True
        with self.assertRaises(TransportError):
            self.t.get_pull_request(7)
        self.gh.drift_total = False
        self.gh.review_pages = None
        self.gh._reviews_payload = lambda cursor: {"totalCount": 5, "pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": self.gh.pr_reviews}
        with self.assertRaises(TransportError):
            self.t.get_pull_request(7)  # claims 5, delivers 2

    def test_comment_lines_and_post_round_trip(self):
        posted = self.t.post_comment(21, "<!-- unattended kind=probe op=probe run=r story=ENG-21 -->\nhello")
        self.assertEqual(posted.comment_id, 100)
        comments = self.t.list_comments(21)
        self.assertEqual(comments[0].marker, {"kind": "probe", "op": "probe", "run": "r", "story": "ENG-21"})

    def test_error_classification(self):
        self.assertIsInstance(classify(1, "gh: HTTP 403: Resource not accessible by integration"), PermissionDenied)
        self.assertIsInstance(classify(1, "HTTP 401: Bad credentials"), PermissionDenied)
        self.assertIsInstance(classify(1, "gh: Not Found (HTTP 404)"), NotFound)
        self.assertIsInstance(classify(1, "HTTP 502: Bad gateway"), Outage)
        self.assertIsInstance(classify(1, "dial tcp: lookup api.github.com: no such host"), Outage)
        self.assertIsInstance(classify(1, "API rate limit exceeded (HTTP 429)"), Outage)
        self.assertIsInstance(classify(-1, "", subprocess.TimeoutExpired(["gh"], 1)), Outage)
        self.assertIs(type(classify(1, "something else entirely")), TransportError)

    def test_graphql_errors_are_classified(self):
        self.t._run = lambda args, stdin=None: json.dumps({"errors": [{"message": "Resource not accessible: you do not have permission"}]})
        with self.assertRaises(PermissionDenied):
            self.t.list_issues()
        self.t._run = lambda args, stdin=None: json.dumps({"errors": [{"message": "Could not resolve to a Repository"}]})
        with self.assertRaises(NotFound):
            self.t.get_issue(1)


class CoordinatorOverTransportTests(unittest.TestCase):
    """A review regression carried in raw GraphQL must refuse the proposal."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        tmp = Path(self.tmp.name)
        self.policy = load_policy(write_policy(tmp, allow='["OM-01.02"]'))
        self.gh = ScriptedGh()
        self.t = GhCliTransport("gabrianoo", "owl-mast", "gabrianoo", 2)
        self.t._run = self.gh
        self.t.live = False
        self.worktree = tmp / "wt"
        self.sha = make_git_repo(self.worktree)
        self.gh.head = self.sha
        for r in self.gh.pr_reviews:
            r["commit"]["oid"] = self.sha
        self.c = Coordinator(self.t, self.policy, Store(tmp / "runs", "run-t"), live=True)

    def tearDown(self):
        self.tmp.cleanup()

    def approved(self):
        snap = take_snapshot(self.t, "gabrianoo/owl-mast", "now")
        self.c.reserve("OM-01.02", snap, "base")
        self.c.bind_receipt("OM-01.02", IMPLEMENTER, str(self.worktree), "t3/om-01-02", ok_worktree)
        self.c.record_head("OM-01.02", self.sha, {"taskId": IMPLEMENTER["taskId"], "runId": IMPLEMENTER["taskId"] + ":run:1", "status": "result_available"})
        self.c.run_checks("OM-01.02", self.sha, str(self.worktree), passing_runner)
        self.c.authorize_review("OM-01.02", self.sha)
        self.c.bind_receipt("OM-01.02", REVIEWER, REVIEW_WORKTREE, REVIEW_BRANCH, ok_worktree)
        self.c.record_review("OM-01.02", self.sha, "approved", "r", {"taskId": REVIEWER["taskId"], "runId": REVIEWER["taskId"] + ":run:1", "status": "result_available"})

    def test_changes_requested_in_raw_response_refuses_proposal(self):
        self.approved()
        with self.assertRaises(Refused) as ctx:
            self.c.propose_evidence("OM-01.02", self.sha, 7, [], "s")
        self.assertIn("A", str(ctx.exception))
        self.assertEqual(len([p for p in self.gh.posted if "kind=proposal" in p]), 0)

    def test_dismissed_objection_allows_proposal_and_posts_once(self):
        self.gh.pr_reviews.append({"state": "DISMISSED", "submittedAt": "3", "author": {"login": "A"}, "commit": {"oid": self.sha}})
        self.approved()
        state = self.c.propose_evidence("OM-01.02", self.sha, 7, ["OM-01.02-T1"], "s")
        self.assertEqual(state.phase, "proposed")
        self.assertEqual(len([p for p in self.gh.posted if "kind=proposal" in p]), 1)

    def test_objection_on_a_later_page_refuses_the_proposal_through_the_coordinator(self):
        self.gh.pr_reviews = []
        self.gh.review_pages = [[{"state": "APPROVED", "submittedAt": "1", "author": {"login": "B"}, "commit": {"oid": self.sha}}],
                                [{"state": "CHANGES_REQUESTED", "submittedAt": "2", "author": {"login": "C"}, "commit": {"oid": self.sha}}]]
        self.approved()
        with self.assertRaises(Refused) as ctx:
            self.c.propose_evidence("OM-01.02", self.sha, 7, [], "s")
        self.assertIn("C", str(ctx.exception))
        self.assertEqual(len([p for p in self.gh.posted if "kind=proposal" in p]), 0)

    def test_live_transport_flag_blocks_admission_before_any_call(self):
        self.t.live = True
        take_snapshot(self.t, "gabrianoo/owl-mast", "now")
        before = len(self.gh.calls)
        with self.assertRaises(Refused) as ctx:
            Coordinator(self.t, self.policy, Store(Path(self.tmp.name) / "runs", "run-live"), live=True)
        self.assertEqual(ctx.exception.code, "activation-required")
        self.assertEqual(len(self.gh.calls), before)
        with self.assertRaises(Refused) as ctx:
            Coordinator(self.t, self.policy, Store(Path(self.tmp.name) / "runs", "run-t"), live=True)  # fixture-born state
        self.assertEqual(ctx.exception.code, "environment-mismatch")
