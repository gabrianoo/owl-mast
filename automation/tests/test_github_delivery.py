import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from automation.github_delivery import (
    DeliveryError,
    Finding,
    GitHub,
    build_review_payload,
    diff_right_lines,
    main,
    parse_spec_comment,
    render_spec_comment,
)

SPEC = """---
title: 'Resolve the bmad-review findings on PR #108 (ENG-01 activation opt-in)'
type: 'bugfix'
created: '2026-11-09'
status: 'in-progress'
route: 'oneshot'
review_loop_iteration: 0
context: []
---

## Intent

**Problem:** A fenced example survives the round trip.

```python
print("---")
```
"""

DIFF = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,3 +10,4 @@ def f():
 keep
-old
+new
+newer
 tail
diff --git a/gone.py b/gone.py
--- a/gone.py
+++ /dev/null
@@ -1 +0,0 @@
-x
"""

PROJECT = {"user": {"projectV2": {"id": "P1", "fields": {"nodes": [
    {"id": "FS", "name": "Status", "options": [{"id": f"o{i}", "name": n} for i, n in enumerate(
        ["Backlog", "Ready", "In progress", "In review", "Blocked", "Done"])]},
    {"id": "FP", "name": "Priority", "options": [{"id": "p1", "name": "P1 - Foundation"}, {"id": "p2", "name": "P2 - Pilot"}]},
    {},
]}}}}


class FakeGh:
    """Scripted gh runner: routes by a substring of the call and records every call."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, args, stdin=None):
        joined = " ".join(args)
        self.calls.append((joined, stdin))
        for needle, reply in self.routes:
            if needle in joined:
                value = reply(joined, stdin) if callable(reply) else reply
                return value if isinstance(value, str) else json.dumps(value)
        raise AssertionError(f"unexpected gh call: {joined[:200]}")


def item(status, project="P1"):
    return {"data": {"repository": {"issueOrPullRequest": {"id": "I1", "projectItems": {"nodes": [
        {"id": "IT1", "project": {"id": project}, "status": {"name": status} if status else None}]}}}}}


class SpecCommentTests(unittest.TestCase):
    def test_round_trip_is_byte_identical(self):
        comment = render_spec_comment("spec-gh-108-review-round-1", SPEC)
        self.assertTrue(comment.startswith("<!-- bmad:spec key=spec-gh-108-review-round-1 -->\n"))
        self.assertNotIn("\n---\n", comment.split("<!-- bmad:spec-body -->")[0])
        self.assertEqual(parse_spec_comment(comment), ("spec-gh-108-review-round-1", SPEC))

    def test_refuses_missing_frontmatter_bad_key_and_oversize(self):
        with self.assertRaises(DeliveryError):
            render_spec_comment("k", "# no frontmatter\n")
        with self.assertRaises(DeliveryError):
            render_spec_comment("bad key", SPEC)
        with self.assertRaises(DeliveryError):
            render_spec_comment("k", SPEC + "x" * 70000)

    def test_malformed_comment_is_refused(self):
        with self.assertRaises(DeliveryError):
            parse_spec_comment("<!-- bmad:spec key=k -->\nno yaml here")
        with self.assertRaises(DeliveryError):
            parse_spec_comment("plain comment")


class ReviewPayloadTests(unittest.TestCase):
    def test_diff_right_lines_tracks_new_side_and_skips_deleted_files(self):
        self.assertEqual(diff_right_lines(DIFF), {"app.py": {10, 11, 12, 13}})

    def test_every_finding_becomes_a_thread(self):
        findings = [Finding("R1-1", "app.py", "in hunk", 11), Finding("R1-2", "app.py", "outside", 99),
                    Finding("R1-3", "docs/x.md", "unchanged file", 4)]
        payload = build_review_payload(1, "changes", "Two problems.", findings, DIFF, "abc")
        self.assertEqual(payload["event"], "COMMENT")
        self.assertTrue(payload["body"].startswith("<!-- bmad:review round=1 verdict=changes -->"))
        line, file_level, foreign = payload["comments"]
        self.assertEqual((line["path"], line["line"], line["side"]), ("app.py", 11, "RIGHT"))
        self.assertEqual(file_level["subject_type"], "file")
        self.assertIn("`app.py:99`", file_level["body"])
        self.assertEqual(foreign["path"], "app.py")
        self.assertIn("`docs/x.md:4` (file not changed by this PR)", foreign["body"])
        for comment, finding in zip(payload["comments"], findings):
            self.assertTrue(comment["body"].startswith(f"<!-- bmad:finding id={finding.id} -->"))

    def test_verdict_and_round_invariants(self):
        one = [Finding("R1-1", "app.py", "x", 11)]
        for args in [(0, "clean", []), (7, "clean", []), (1, "clean", one), (1, "changes", []), (1, "maybe", []),
                     (1, "changes", one * 2)]:
            with self.subTest(args=args), self.assertRaises(DeliveryError):
                build_review_payload(args[0], args[1], "s", args[2], DIFF, "abc")
        self.assertEqual(build_review_payload(6, "clean", "ok", [], DIFF, "abc")["comments"], [])


class StatusTests(unittest.TestCase):
    def client(self, status):
        fake = FakeGh([("projectV2(number:$number){ id", {"data": PROJECT}),
                       ("issueOrPullRequest", {"data": item(status)["data"]}),
                       ("updateProjectV2ItemFieldValue", {"data": {"updateProjectV2ItemFieldValue": {}}})])
        return GitHub(run=fake), fake

    def test_claim_moves_ready_to_in_progress(self):
        gh, fake = self.client("Ready")
        self.assertEqual(gh.set_status(5, "In progress", ["Ready"]), {"issue": 5, "from": "Ready", "to": "In progress"})
        update = [c for c, _ in fake.calls if "updateProjectV2ItemFieldValue" in c]
        self.assertEqual(len(update), 1)
        self.assertIn("o=o2", update[0])

    def test_expect_guard_refuses_a_ticket_someone_else_moved(self):
        gh, fake = self.client("In progress")
        with self.assertRaisesRegex(DeliveryError, "expected one of"):
            gh.set_status(5, "In progress", ["Ready"])
        self.assertFalse([c for c, _ in fake.calls if "updateProjectV2ItemFieldValue" in c])

    def test_same_status_is_a_no_op(self):
        gh, fake = self.client("In review")
        gh.set_status(5, "In review")
        self.assertFalse([c for c, _ in fake.calls if "updateProjectV2ItemFieldValue" in c])


class ReadyTests(unittest.TestCase):
    def test_orders_by_priority_then_stable_id_and_skips_non_ready(self):
        def node(n, status, priority, stable, state="OPEN"):
            return {"status": {"name": status}, "priority": {"name": priority}, "stable": {"text": stable},
                    "content": {"number": n, "title": f"t{n}", "url": f"u{n}", "state": state,
                                "assignees": {"nodes": []}}}
        page = {"data": {"user": {"projectV2": {"items": {"pageInfo": {"hasNextPage": False, "endCursor": None},
                "nodes": [node(9, "Ready", "P2 - Pilot", "OM-02.01"), node(8, "Ready", "P1 - Foundation", "OM-01.06"),
                          node(7, "Ready", "P1 - Foundation", "OM-01.05"), node(6, "Backlog", "P1 - Foundation", "OM-01.07"),
                          node(5, "Ready", "P1 - Foundation", "OM-01.01", state="CLOSED"), {"content": None}]}}}}}
        gh = GitHub(run=FakeGh([("projectV2(number:$number){ id", {"data": PROJECT}), ("items(first:100", page)]))
        self.assertEqual([i["number"] for i in gh.ready()], [7, 8, 9])


class SpecSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_push_creates_then_edits_in_place_then_pull_restores_file(self):
        store = []

        def comments(_, __):
            return [store]

        def create(_, stdin):
            store.append({"id": 1, "body": json.loads(stdin)["body"], "html_url": "c1", "updated_at": "t"})
            return store[-1]

        def edit(_, stdin):
            store[0]["body"] = json.loads(stdin)["body"]
            return store[0]

        fake = FakeGh([("--paginate", comments), ("-X POST", create), ("-X PATCH", edit)])
        gh = GitHub(run=fake)
        spec = self.dir / "spec-om-01-05-x.md"
        spec.write_text(SPEC, encoding="utf-8")
        self.assertTrue(gh.spec_push(42, "spec-om-01-05-x", spec)["changed"])
        self.assertFalse(gh.spec_push(42, "spec-om-01-05-x", spec)["changed"])
        spec.write_text(SPEC.replace("in-progress", "done"), encoding="utf-8")
        self.assertTrue(gh.spec_push(42, "spec-om-01-05-x", spec)["changed"])
        self.assertEqual(len(store), 1)
        self.assertEqual(sum("-X PATCH" in c for c, _ in fake.calls), 1)
        out = self.dir / "hydrated" / "spec.md"
        gh.spec_pull(42, None, out)
        self.assertEqual(out.read_text(encoding="utf-8"), SPEC.replace("in-progress", "done"))

    def test_duplicate_spec_comments_are_refused(self):
        body = render_spec_comment("k", SPEC)
        dup = [[{"id": 1, "body": body, "html_url": "a"}, {"id": 2, "body": body, "html_url": "b"}]]
        with self.assertRaisesRegex(DeliveryError, "two spec comments"):
            GitHub(run=FakeGh([("--paginate", dup)])).spec_list(1)


def pr_payload(reviews, threads):
    return {"data": {"repository": {"pullRequest": {
        "number": 12, "url": "pr12", "state": "OPEN", "headRefName": "t3/x", "headRefOid": "sha1",
        "baseRefName": "main", "isDraft": False, "mergeable": "MERGEABLE",
        "closingIssuesReferences": {"nodes": [{"number": 5}]},
        "reviews": {"nodes": reviews},
        "reviewThreads": {"pageInfo": {"hasNextPage": False}, "nodes": threads}}}}}


def thread(tid, body, resolved):
    return {"id": tid, "isResolved": resolved, "isOutdated": False, "path": "app.py", "line": 11,
            "comments": {"nodes": [{"author": {"login": "a"}, "body": body, "url": f"u-{tid}", "createdAt": "t"}]}}


class ReviewStateTests(unittest.TestCase):
    def test_counts_rounds_and_splits_bmad_from_other_threads(self):
        reviews = [{"body": "<!-- bmad:review round=1 verdict=changes -->\n...", "submittedAt": "t1", "url": "r1"},
                   {"body": "LGTM from a human", "submittedAt": "t2", "url": "r2"}]
        threads = [thread("T1", "<!-- bmad:finding id=R1-1 -->\nx", False),
                   thread("T2", "<!-- bmad:finding id=R1-2 -->\ny", True),
                   thread("T3", "human nit", False)]
        state = GitHub(run=FakeGh([("pullRequest(number", pr_payload(reviews, threads))])).review_state(12)
        self.assertEqual((state["rounds_done"], state["next_round"], state["issues"]), (1, 2, [5]))
        self.assertEqual([t["finding_id"] for t in state["open_findings"]], ["R1-1"])
        self.assertEqual(state["resolved_findings"], 1)
        self.assertEqual([t["thread_id"] for t in state["other_unresolved_threads"]], ["T3"])

    def test_post_review_refuses_a_skipped_or_repeated_round(self):
        reviews = [{"body": "<!-- bmad:review round=1 verdict=changes -->", "submittedAt": "t", "url": "r1"}]
        gh = GitHub(run=FakeGh([("pullRequest(number", pr_payload(reviews, []))]))
        for round_number in (1, 3):
            with self.subTest(round=round_number), self.assertRaisesRegex(DeliveryError, "next review must be round 2"):
                gh.post_review(12, round_number, "clean", "ok", [])

    def test_post_review_sends_payload_against_the_head_commit(self):
        fake = FakeGh([("pullRequest(number", pr_payload([], [])), ("pr diff", DIFF),
                       ("pulls/12/reviews", {"html_url": "rev"})])
        result = GitHub(run=fake).post_review(12, 1, "changes", "s", [Finding("R1-1", "app.py", "b", 12)])
        self.assertEqual(result["url"], "rev")
        sent = json.loads(next(stdin for call, stdin in fake.calls if "pulls/12/reviews" in call))
        self.assertEqual((sent["commit_id"], len(sent["comments"])), ("sha1", 1))


class CliTests(unittest.TestCase):
    def test_refusal_exits_2_with_message(self):
        fake = FakeGh([("projectV2(number:$number){ id", {"data": PROJECT}),
                       ("issueOrPullRequest", {"data": item("Done")["data"]})])
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            code = main(["status", "5", "In progress", "--expect", "Ready"], client=GitHub(run=fake))
        self.assertEqual(code, 2)
        self.assertIn("refusing", err.getvalue())

    def test_missing_gh_is_a_refusal_not_a_crash(self):
        def missing(args, stdin=None):
            raise DeliveryError("gh CLI is not installed; install and authenticate it (gh auth login)")
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            self.assertEqual(main(["ready"], client=GitHub(run=missing)), 2)
        self.assertIn("gh CLI is not installed", err.getvalue())


if __name__ == "__main__":
    unittest.main()
