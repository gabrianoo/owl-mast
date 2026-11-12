import io
import json
import subprocess
import sys
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

SHA = "a" * 40
HEAD = "b" * 40
REPO_ROOT = Path(__file__).resolve().parents[2]

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

    def test_added_line_that_looks_like_a_file_header_stays_content(self):
        diff = ("diff --git a/doc.md b/doc.md\n--- a/doc.md\n+++ b/doc.md\n@@ -1,2 +1,4 @@\n keep\n"
                "+++ b/not-a-file\n+-- also content\n tail\n"
                "diff --git a/next.py b/next.py\n--- a/next.py\n+++ b/next.py\n@@ -3 +3 @@\n-old\n+new\n")
        self.assertEqual(diff_right_lines(diff), {"doc.md": {1, 2, 3, 4}, "next.py": {3}})

    def test_removed_line_that_looks_like_a_file_header_and_stripped_blank_context(self):
        diff = ("--- a/doc.md\n+++ b/doc.md\n@@ -1,4 +1,3 @@\n keep\n--- a/not-a-file\n\n tail\n"
                "\\ No newline at end of file\n")
        self.assertEqual(diff_right_lines(diff), {"doc.md": {1, 2, 3}})

    def test_no_newline_marker_inside_a_hunk_does_not_end_it(self):
        diff = ("--- a/f.txt\n+++ b/f.txt\n@@ -1,2 +1,3 @@\n keep\n-old\n\\ No newline at end of file\n+new\n+more\n")
        self.assertEqual(diff_right_lines(diff), {"f.txt": {1, 2, 3}})

    def test_hunk_shorter_than_its_header_gives_way_to_the_next_file(self):
        diff = ("--- a/a.py\n+++ b/a.py\n@@ -1,9 +1,9 @@\n keep\n+new\n"
                "diff --git a/b.py b/b.py\n--- a/b.py\n+++ b/b.py\n@@ -0,0 +1 @@\n+only\n")
        self.assertEqual(diff_right_lines(diff), {"a.py": {1, 2}, "b.py": {1}})

    def test_form_feed_and_crlf_in_content_do_not_split_or_shift_lines(self):
        diff = "--- a/a.c\n+++ b/a.c\n@@ -1,2 +1,3 @@\n one\r\n+page\x0cbreak\u2028here\r\n two\r\n"
        self.assertEqual(diff_right_lines(diff), {"a.c": {1, 2, 3}})

    def test_every_finding_becomes_a_thread(self):
        findings = [Finding("R1-1", "app.py", "in hunk", 11), Finding("R1-2", "app.py", "outside", 99),
                    Finding("R1-3", "docs/x.md", "unchanged file", 4)]
        payload, file_comments = build_review_payload(1, "changes", "Two problems.", findings, DIFF, SHA)
        self.assertEqual((payload["event"], payload["commit_id"]), ("COMMENT", SHA))
        self.assertTrue(payload["body"].startswith("<!-- bmad:review round=1 verdict=changes -->"))
        self.assertIn("File-level threads (not on a line of the reviewed diff): R1-2, R1-3", payload["body"])
        (line,) = payload["comments"]
        self.assertEqual(line, {"path": "app.py", "line": 11, "side": "RIGHT",
                                "body": "<!-- bmad:finding id=R1-1 -->\n**R1-1**\n\nin hunk"})
        file_level, foreign = file_comments
        self.assertEqual({k: file_level[k] for k in ("finding_id", "commit_id", "path", "subject_type")},
                         {"finding_id": "R1-2", "commit_id": SHA, "path": "app.py", "subject_type": "file"})
        self.assertIn("`app.py:99` (outside the diff hunks)", file_level["body"])
        self.assertEqual(foreign["path"], "app.py")
        self.assertIn("`docs/x.md:4` (file not in the reviewed diff)", foreign["body"])
        for comment, finding in zip([line, file_level, foreign], findings):
            self.assertTrue(comment["body"].startswith(f"<!-- bmad:finding id={finding.id} -->"))

    def test_create_review_comments_use_only_the_fields_that_endpoint_documents(self):
        findings = [Finding("R1-1", "app.py", "in hunk", 11), Finding("R1-2", "app.py", "outside", 99)]
        payload, _ = build_review_payload(1, "changes", "s", findings, DIFF, SHA)
        allowed = {"path", "position", "body", "line", "side", "start_line", "start_side"}
        for comment in payload["comments"]:
            self.assertLessEqual(set(comment), allowed)

    def test_verdict_and_round_invariants(self):
        one = [Finding("R1-1", "app.py", "x", 11)]
        for args in [(0, "clean", []), (7, "clean", []), (1, "clean", one), (1, "changes", []), (1, "maybe", []),
                     (1, "changes", one * 2)]:
            with self.subTest(args=args), self.assertRaises(DeliveryError):
                build_review_payload(args[0], args[1], "s", args[2], DIFF, SHA)
        payload, file_comments = build_review_payload(6, "clean", "ok", [], DIFF, SHA)
        self.assertEqual((payload["comments"], file_comments), ([], []))


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

    def test_rework_then_fix_round_and_a_resumed_fix_round_both_pass_the_guard(self):
        """Walkthrough Rework leaves the ticket In review; the fix round moves it, and may run twice."""
        fix_round = ["In review", "In progress"]
        gh, fake = self.client("In review")
        self.assertEqual(gh.set_status(5, "In progress", fix_round)["from"], "In review")
        self.assertEqual(sum("updateProjectV2ItemFieldValue" in c for c, _ in fake.calls), 1)
        gh, fake = self.client("In progress")
        self.assertEqual(gh.set_status(5, "In progress", fix_round)["from"], "In progress")
        self.assertFalse([c for c, _ in fake.calls if "updateProjectV2ItemFieldValue" in c])
        gh, _ = self.client("Ready")
        with self.assertRaisesRegex(DeliveryError, "expected one of"):
            gh.set_status(5, "In progress", fix_round)

def claim_comment(comment_id, created="2026-11-12T10:00:00Z"):
    return {"id": comment_id, "body": f"<!-- bmad:claim token={'c' * 32} -->\nclaiming", "html_url": f"claim-{comment_id}",
            "created_at": created}


class ClaimTests(unittest.TestCase):
    def client(self, statuses, others=()):
        """A ticket whose Status reads return `statuses` in turn, with `others` already commented on it."""
        reads = iter(statuses)
        fake = FakeGh([("projectV2(number:$number){ id", {"data": PROJECT}),
                       ("issueOrPullRequest", lambda *_: {"data": item(next(reads))["data"]}),
                       ("updateProjectV2ItemFieldValue", {"data": {"updateProjectV2ItemFieldValue": {}}}),
                       ("-X POST repos/gabrianoo/owl-mast/issues/5/comments", claim_comment(50, "2026-11-12T10:05:00Z")),
                       ("--paginate", lambda *_: [list(others) + [claim_comment(50, "2026-11-12T10:05:00Z")]]),
                       ("-X DELETE repos/gabrianoo/owl-mast/issues/comments/50", "")])
        return GitHub(run=fake), fake

    def calls(self, fake, needle):
        return [c for c, _ in fake.calls if needle in c]

    def test_uncontested_claim_writes_status_then_removes_its_marker(self):
        gh, fake = self.client(["Ready", "Ready"], others=[{"id": 7, "body": "a human comment", "created_at": "x"}])
        result = gh.set_status(5, "In progress", ["Ready"], claim=True)
        self.assertEqual(result, {"issue": 5, "from": "Ready", "to": "In progress", "claimed": True})
        order = [c for c, _ in fake.calls if "updateProjectV2ItemFieldValue" in c or "-X " in c]
        self.assertEqual([("POST" in c, "update" in c, "DELETE" in c) for c in order],
                         [(True, False, False), (False, True, False), (False, False, True)])
        self.assertIn("<!-- bmad:claim token=", json.loads(fake.calls[[c for c, _ in fake.calls].index(order[0])][1])["body"])

    def test_later_claim_backs_off_and_removes_its_marker(self):
        gh, fake = self.client(["Ready", "Ready"], others=[claim_comment(40, "2026-11-12T10:04:30Z")])
        with self.assertRaisesRegex(DeliveryError, "being claimed by another run \\(claim-40\\)"):
            gh.set_status(5, "In progress", ["Ready"], claim=True)
        self.assertFalse(self.calls(fake, "updateProjectV2ItemFieldValue"))
        self.assertEqual(len(self.calls(fake, "-X DELETE")), 1)

    def test_claim_refuses_when_a_rival_settled_before_the_marker_appeared(self):
        gh, fake = self.client(["Ready", "In progress"])
        with self.assertRaisesRegex(DeliveryError, "became 'In progress' while it was being claimed"):
            gh.set_status(5, "In progress", ["Ready"], claim=True)
        self.assertFalse(self.calls(fake, "updateProjectV2ItemFieldValue"))
        self.assertEqual(len(self.calls(fake, "-X DELETE")), 1)

    def test_marker_of_a_dead_run_and_a_later_marker_do_not_block(self):
        gh, fake = self.client(["Ready", "Ready"], others=[claim_comment(40, "2026-11-12T09:00:00Z"), claim_comment(60)])
        self.assertTrue(gh.set_status(5, "In progress", ["Ready"], claim=True)["claimed"])
        self.assertEqual(len(self.calls(fake, "updateProjectV2ItemFieldValue")), 1)

    def failing(self, needle):
        """A claim client whose first route matching `needle` refuses."""
        gh, fake = self.client(["Ready", "Ready"])

        def refuse(*_):
            raise DeliveryError("gh api failed: boom")
        fake.routes.insert(0, (needle, refuse))
        return gh, fake

    def test_failed_status_write_still_removes_the_marker_and_refuses(self):
        gh, fake = self.failing("updateProjectV2ItemFieldValue")
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            self.assertEqual(main(["status", "5", "In progress", "--expect", "Ready", "--claim"], client=gh), 2)
        self.assertIn("boom", err.getvalue())
        self.assertEqual(len(self.calls(fake, "-X DELETE")), 1)

    def test_marker_that_cannot_be_removed_after_a_good_claim_is_reported_not_raised(self):
        gh, _ = self.failing("-X DELETE")
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(["status", "5", "In progress", "--expect", "Ready", "--claim"], client=gh), 0)
        self.assertEqual(json.loads(out.getvalue()),
                         {"issue": 5, "from": "Ready", "to": "In progress", "claimed": True, "claim_marker_left": "claim-50"})

    def test_backing_off_with_a_marker_that_cannot_be_removed_names_it(self):
        gh, fake = self.failing("-X DELETE")
        fake.routes.insert(0, ("--paginate", [[claim_comment(40, "2026-11-12T10:04:30Z"),
                                               claim_comment(50, "2026-11-12T10:05:00Z")]]))
        with self.assertRaisesRegex(DeliveryError, "claimed by another run.*delete it by hand: claim-50"):
            gh.set_status(5, "In progress", ["Ready"], claim=True)

    def test_claim_needs_expect_without_the_target_and_cli_passes_the_flag(self):
        gh, fake = self.client(["Ready", "Ready"])
        for expect in ([], ["Ready", "In progress"]):
            with self.subTest(expect=expect), self.assertRaisesRegex(DeliveryError, "--claim needs"):
                gh.set_status(5, "In progress", expect, claim=True)
        self.assertFalse(fake.calls)
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(["status", "5", "In progress", "--expect", "Ready", "--claim"], client=gh), 0)
        self.assertTrue(json.loads(out.getvalue())["claimed"])


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
        "number": 12, "url": "pr12", "state": "OPEN", "headRefName": "t3/x", "headRefOid": HEAD,
        "baseRefName": "main", "isDraft": False, "mergeable": "MERGEABLE",
        "closingIssuesReferences": {"nodes": [{"number": 5}]},
        "reviews": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": reviews},
        "reviewThreads": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": threads}}}}}


def next_page(connection, nodes, cursor=None):
    return {"data": {"repository": {"pullRequest": {connection: {
        "pageInfo": {"hasNextPage": cursor is not None, "endCursor": cursor}, "nodes": nodes}}}}}


def round_review(number, verdict="changes", commit=HEAD):
    return {"body": f"<!-- bmad:review round={number} verdict={verdict} -->", "submittedAt": "t", "url": f"r{number}",
            "commit": {"oid": commit}}


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
        self.assertEqual(state["finding_ids"], ["R1-1", "R1-2"])
        self.assertFalse(state["last_round_at_head"])
        self.assertEqual([t["thread_id"] for t in state["other_unresolved_threads"]], ["T3"])

    def test_a_round_covers_the_head_only_when_it_was_posted_against_it(self):
        def at_head(reviews):
            return GitHub(run=FakeGh([("pullRequest(number", pr_payload(reviews, []))])).review_state(12)["last_round_at_head"]
        self.assertTrue(at_head([round_review(1), round_review(2, "clean")]))
        self.assertFalse(at_head([round_review(1), round_review(2, "clean", commit=SHA)]))
        self.assertFalse(at_head([]))

    def test_reviews_and_threads_past_the_first_page_are_counted(self):
        first = pr_payload([round_review(1)] + [{"body": "human", "submittedAt": "t", "url": "h"}] * 99,
                           [thread("T1", "<!-- bmad:finding id=R1-1 -->", True)])
        pull = first["data"]["repository"]["pullRequest"]
        pull["reviews"]["pageInfo"] = {"hasNextPage": True, "endCursor": "RC1"}
        pull["reviewThreads"]["pageInfo"] = {"hasNextPage": True, "endCursor": "TC1"}
        fake = FakeGh([("after=RC1", next_page("reviews", [round_review(2)], "RC2")),
                       ("after=RC2", next_page("reviews", [round_review(3, "clean")])),
                       ("after=TC1", next_page("reviewThreads", [thread("T2", "<!-- bmad:finding id=R2-1 -->", False)])),
                       ("pullRequest(number", first)])
        state = GitHub(run=fake).review_state(12)
        self.assertEqual((state["rounds_done"], state["next_round"]), (3, 4))
        self.assertEqual(state["rounds"][-1]["verdict"], "clean")
        self.assertEqual(state["finding_ids"], ["R1-1", "R2-1"])
        self.assertEqual([t["thread_id"] for t in state["open_findings"]], ["T2"])
        self.assertTrue(all("reviews(first:100, after:$after)" in c for c, _ in fake.calls if "after=RC" in c))

    def test_post_review_refuses_a_skipped_or_repeated_round(self):
        gh = GitHub(run=FakeGh([("pullRequest(number", pr_payload([round_review(1)], []))]))
        for round_number in (1, 3):
            with self.subTest(round=round_number), self.assertRaisesRegex(DeliveryError, "next review must be round 2"):
                gh.post_review(12, round_number, "clean", "ok", [], HEAD)
        with self.assertRaisesRegex(DeliveryError, r"Round 1 is already posted \(r1\).*do not post it again"):
            gh.post_review(12, 1, "clean", "ok", [], HEAD)

    def test_post_review_refuses_a_pull_request_that_is_not_open(self):
        merged = pr_payload([], [])
        merged["data"]["repository"]["pullRequest"]["state"] = "MERGED"
        with self.assertRaisesRegex(DeliveryError, "is MERGED; a review round needs an open pull request"):
            GitHub(run=FakeGh([("pullRequest(number", merged)])).post_review(12, 1, "clean", "ok", [], HEAD)

    def routes(self, commit=HEAD, threads=(), compare=None, base=None):
        routes = [("pullRequest(number", pr_payload([], list(threads))),
                  (f"-X GET repos/gabrianoo/owl-mast/compare/main...{commit}",
                   base or {"ahead_by": 2, "files": [{"filename": "app.py"}]}),
                  (f"Accept: application/vnd.github.diff repos/gabrianoo/owl-mast/compare/main...{commit}", DIFF),
                  ("pulls/12/comments", {"id": 1}), ("pulls/12/reviews", {"html_url": "rev"})]
        if compare is not None:
            routes.insert(0, (f"-X GET repos/gabrianoo/owl-mast/compare/{commit}...{HEAD}", compare))
        return routes

    def post(self, findings, commit=HEAD, verdict="changes", **state):
        fake = FakeGh(self.routes(commit, **state))
        result = GitHub(run=fake).post_review(12, 1, verdict, "s", findings, commit)
        sent = [(call, json.loads(stdin)) for call, stdin in fake.calls if "-X POST" in call]
        return result, sent, fake

    def test_post_review_anchors_the_round_to_the_reviewed_commit_not_the_head(self):
        result, sent, fake = self.post([Finding("R1-1", "app.py", "b", 12)], commit=SHA, compare={"status": "ahead"})
        self.assertEqual((result["url"], result["commit"], result["file_level"]), ("rev", SHA, 0))
        ((call, review),) = sent
        self.assertIn("pulls/12/reviews", call)
        self.assertEqual((review["commit_id"], len(review["comments"])), (SHA, 1))
        self.assertIn(f"Reviewed commit: `{SHA}`.", review["body"])
        self.assertIn(f"The PR head moved to `{HEAD}` after this review.", review["body"])
        self.assertTrue([c for c, _ in fake.calls if f"Accept: application/vnd.github.diff repos/gabrianoo/owl-mast/compare/main...{SHA}" in c])
        self.assertFalse([c for c, _ in fake.calls if c.startswith("pr diff")])

    def test_post_review_at_the_head_needs_no_history_check(self):
        _, sent, fake = self.post([Finding("R1-1", "app.py", "b", 12)])
        self.assertEqual(sent[0][1]["commit_id"], HEAD)
        self.assertNotIn("head moved", sent[0][1]["body"])
        self.assertFalse([c for c, _ in fake.calls if f"...{HEAD}" in c and "compare/main" not in c])

    def test_post_review_refuses_a_commit_that_is_not_on_the_pr(self):
        for compare in ({"status": "diverged"}, {"status": "behind"}):
            with self.subTest(compare=compare), self.assertRaisesRegex(DeliveryError, "not in the history"):
                self.post([Finding("R1-1", "app.py", "b", 12)], commit=SHA, compare=compare)
        for bad in ("abc1234", "HEAD", ""):
            with self.subTest(commit=bad), self.assertRaisesRegex(DeliveryError, "full 40-character"):
                GitHub(run=FakeGh([])).post_review(12, 1, "clean", "ok", [], bad)

        def gone(*_):
            raise DeliveryError("gh api -X GET failed: Not Found")
        with self.assertRaisesRegex(DeliveryError, "cannot be compared"):
            self.post([Finding("R1-1", "app.py", "b", 12)], commit=SHA, compare=gone)

    def test_post_review_refuses_a_base_commit_a_truncated_diff_and_an_oversize_body(self):
        one = [Finding("R1-1", "app.py", "b", 12)]
        with self.assertRaisesRegex(DeliveryError, "is not ahead of main"):
            self.post(one, commit=SHA, compare={"status": "ahead"}, base={"ahead_by": 0, "files": []})
        with self.assertRaisesRegex(DeliveryError, "300 or more files"):
            self.post(one, base={"ahead_by": 1, "files": [{}] * 300})
        fake = FakeGh(self.routes())
        with self.assertRaisesRegex(DeliveryError, "review body is"):
            GitHub(run=fake).post_review(12, 1, "changes", "x" * 70000, [Finding("R1-1", "app.py", "outside", 99)], HEAD)
        self.assertFalse([c for c, _ in fake.calls if "-X POST" in c])

    def test_file_level_findings_are_single_comments_posted_before_the_review(self):
        findings = [Finding("R1-1", "app.py", "in hunk", 11), Finding("R1-2", "app.py", "outside", 99),
                    Finding("R1-3", "docs/x.md", "unchanged file", 4)]
        result, sent, _ = self.post(findings)
        self.assertEqual((result["findings"], result["file_level"], result["already_posted"]), (3, 2, []))
        self.assertEqual(["comments", "comments", "reviews"], [call.rsplit("/", 1)[-1].split()[0] for call, _ in sent])
        for _, comment in sent[:2]:
            self.assertEqual(set(comment), {"commit_id", "path", "subject_type", "body"})
            self.assertEqual((comment["commit_id"], comment["path"], comment["subject_type"]), (HEAD, "app.py", "file"))
        review = sent[2][1]
        self.assertEqual([c["line"] for c in review["comments"]], [11])
        self.assertFalse([c for c in review["comments"] if "subject_type" in c])

    def test_rerun_after_a_partial_post_skips_file_level_findings_that_have_a_thread(self):
        findings = [Finding("R1-1", "app.py", "outside", 99), Finding("R1-2", "docs/x.md", "unchanged file", 4)]
        result, sent, _ = self.post(findings, threads=[thread("T1", "<!-- bmad:finding id=R1-1 -->\nx", False)])
        self.assertEqual(result["already_posted"], ["R1-1"])
        self.assertEqual(len([c for c, _ in sent if "pulls/12/comments" in c]), 1)
        self.assertIn("bmad:finding id=R1-2", sent[0][1]["body"])
        self.assertIn("pulls/12/reviews", sent[1][0])


class CustomizationTests(unittest.TestCase):
    """The team overrides the delivery workflow depends on must parse and merge."""

    @unittest.skipIf(sys.version_info < (3, 11), "tomllib needs Python 3.11+")
    def test_every_team_override_is_valid_toml_and_resolves(self):
        import tomllib
        overrides = sorted((REPO_ROOT / "_bmad" / "custom").glob("*.toml"))
        self.assertTrue(overrides)
        for path in overrides:
            with self.subTest(file=path.name), path.open("rb") as handle:
                tomllib.load(handle)
        resolver = REPO_ROOT / "_bmad" / "scripts" / "resolve_customization.py"
        for skill, needle in (("bmad-build", "1. bmad-build"), ("bmad-review", "2. bmad-review"),
                              ("bmad-walkthrough", "3. bmad-walkthrough")):
            with self.subTest(skill=skill):
                done = subprocess.run([sys.executable, str(resolver), "--project-root", str(REPO_ROOT), "--skill",
                                       str(REPO_ROOT / ".claude" / "skills" / skill)], capture_output=True, text=True)
                self.assertEqual(done.returncode, 0, done.stderr)
                workflow = json.loads(done.stdout)["workflow"]
                self.assertIn(needle, " ".join(workflow["activation_steps_prepend"]))
                self.assertIn(needle, workflow["on_complete"])

    @unittest.skipIf(sys.version_info < (3, 11), "tomllib needs Python 3.11+")
    def test_review_override_keeps_the_team_rules_next_to_the_delivery_steps(self):
        import tomllib
        with (REPO_ROOT / "_bmad" / "custom" / "bmad-review.toml").open("rb") as handle:
            workflow = tomllib.load(handle)["workflow"]
        steps = " ".join(workflow["activation_steps_prepend"])
        self.assertIn("Standing rule for this run", steps)
        self.assertIn("GitHub delivery", steps)
        self.assertIn("post-review", workflow["on_complete"])
        self.assertIn("A. Check the reviewed SHA.", workflow["on_complete"])
        self.assertIn("ubuntu-26.04", " ".join(workflow["persistent_facts"]))


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

    def test_post_review_cli_posts_against_the_commit_it_was_given(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary, findings = Path(tmp) / "s.md", Path(tmp) / "f.json"
            summary.write_text("One problem.", encoding="utf-8")
            findings.write_text(json.dumps([{"id": "R1-1", "path": "app.py", "line": 12, "body": "b"}]), encoding="utf-8")
            fake = FakeGh(ReviewStateTests().routes(SHA, compare={"status": "ahead"}))
            with redirect_stdout(io.StringIO()) as out:
                code = main(["post-review", "12", "--round", "1", "--commit", SHA, "--verdict", "changes",
                             "--summary-file", str(summary), "--findings-file", str(findings)], client=GitHub(run=fake))
        self.assertEqual((code, json.loads(out.getvalue())["commit"]), (0, SHA))
        sent = json.loads(next(stdin for call, stdin in fake.calls if "pulls/12/reviews" in call))
        self.assertEqual((sent["commit_id"], sent["comments"][0]["line"]), (SHA, 12))

    def test_post_review_requires_the_reviewed_commit(self):
        with redirect_stderr(io.StringIO()) as err, self.assertRaises(SystemExit):
            main(["post-review", "12", "--round", "1", "--verdict", "clean", "--summary-file", "s.md"])
        self.assertIn("--commit", err.getvalue())


if __name__ == "__main__":
    unittest.main()
