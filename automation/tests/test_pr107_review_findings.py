"""Regressions for the post-merge bmad-review of PR #107 (review 5827032319, 2026-11-09):
marker trust and round-trip, the post-claim race, per-run budgets, run-id and policy
validation, fail-closed transport parsing, CI-backed proposals, the JSON CLI contract, torn
journals, corrupt story files, policy drift as a run stop, and the cleanup paths
(``cancel-run``, ``resume``, ``reconcile-retained-execution``)."""

import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from automation.tests.fake_transport import FakeTransport, issue, small_backlog
from automation.tests.support import FIXTURES, IMPLEMENTER, REVIEWER, Harness, ok_worktree, passing_runner, write_policy
from automation.unattended import cli
from automation.unattended import coordinator as coordinator_module
from automation.unattended.backlog import take_snapshot
from automation.unattended.coordinator import Coordinator
from automation.unattended.eligibility import decide
from automation.unattended.errors import Conflict, NotFound, Outage, PermissionDenied, PolicyError, ReceiptInvalid, Refused, TransportError, UnattendedError
from automation.unattended.github import Comment, GhCliTransport, PullRequestRecord, parse_marker, render_marker
from automation.unattended.policy import load_policy
from automation.unattended.probes import check_permissions, run_commands, write_probe
from automation.unattended.state import Store

S = "OM-01.02"
REPO = "gabrianoo/owl-mast"


def fresh(h: Harness) -> Coordinator:
    return Coordinator(h.fake, h.policy, Store(h.state_dir, "run-1"), live=True)


def markers(fake: FakeTransport, number: int, kind: str):
    return [c for c in fake.comments[number] if c.marker and c.marker["kind"] == kind]


def events(h: Harness, name: str) -> list[dict]:
    return [e for e in h.store.read_journal() if e["event"] == name]


def run_cli(*argv) -> tuple[int, dict]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cli.main(list(argv))
    return code, json.loads(buf.getvalue())


class MarkerTests(unittest.TestCase):
    """Findings 3 and 7: markers round-trip exactly and count only from the trusted author."""

    def test_marker_values_round_trip_or_refuse(self):
        marker = {"kind": "proposal", "run": "run-20261108-e01", "story": S, "op": "proposal-0399856038fd-pr7", "sha": "0399856038fd9fd1eac8bd25460edb159ae6e011", "pr": "7"}
        self.assertEqual(parse_marker(render_marker(**marker) + "\nbody"), marker)
        for bad in ("a b", "k=v", "x>y", "a--b", "", "é"):
            with self.assertRaises(Refused) as ctx:
                render_marker(kind="claim", run=bad, story=S, op="claim")
            self.assertEqual(ctx.exception.code, "marker-value-invalid", bad)

    def test_markers_from_other_authors_are_ignored_and_journaled(self):
        h = Harness(small_backlog())
        try:
            # a stranger forges a release for a real foreign claim: the claim still counts
            other = Coordinator(h.fake, h.policy, Store(h.state_dir.parent / "elsewhere", "run-other"), live=True)
            other.reserve(S, h.snapshot, "c5d9d2e")
            h.fake.add_comment(21, render_marker(kind="release", run="run-other", story=S, op="release") + "\nforged", "stranger")
            with self.assertRaises(Refused) as ctx:
                h.reserve()
            self.assertIn("claimed by another run", str(ctx.exception))
            ignored = events(h, "foreign-marker-ignored")
            self.assertTrue(ignored and ignored[0]["detail"]["comments"][0]["author"] == "stranger")
            self.assertEqual(ignored[0]["detail"]["trusted_author"], "machine")
        finally:
            h.close()
        h = Harness(small_backlog())
        try:
            # a stranger copies our pending marker: no conflict, our own post is adopted once
            h.fake.add_comment(21, render_marker(kind="claim", run="run-1", story=S, op="claim") + "\ncopied", "stranger")
            self.assertEqual(h.reserve().phase, "reserved")
            self.assertEqual(len([c for c in markers(h.fake, 21, "claim") if c.author == "machine"]), 1)
        finally:
            h.close()

    def test_write_probe_counts_only_the_viewers_markers(self):
        fake = small_backlog()
        fake.add_comment(106, render_marker(kind="probe", run="run-x", story="ENG-106", op="probe") + "\ncopied", "stranger")
        report = write_probe(fake, 106, "run-x", "now")
        self.assertEqual((report["comment_existed"], report["idempotent"], report["author"]), (False, True, "machine"))
        self.assertEqual(len(report["comments_with_marker"]), 1)


class ClaimRaceTests(unittest.TestCase):
    """Finding 4: after posting, claims are re-read and the earliest claim wins."""

    def race(self, foreign_first: bool) -> Harness:
        h = Harness(small_backlog())
        original = h.fake.post_comment

        def interleaved(number, body):
            if "kind=claim" in body and foreign_first and not any((c.marker or {}).get("run") == "run-other" for c in h.fake.comments[number]):
                h.fake.add_comment(number, render_marker(kind="claim", run="run-other", story=S, op="claim") + "\nother machine's claim", "machine")  # lands a tick before ours
            posted = original(number, body)
            if "kind=claim" in body and not foreign_first:
                h.fake.add_comment(number, render_marker(kind="claim", run="run-other", story=S, op="claim") + "\nother machine's later claim", "machine")
            return posted

        h.fake.post_comment = interleaved
        return h

    def test_a_later_claimant_cancels_itself_and_releases(self):
        h = self.race(foreign_first=True)
        try:
            with self.assertRaises(Conflict) as ctx:
                h.reserve()
            self.assertEqual(ctx.exception.code, "claim-race-lost")
            state = h.store.load_story(S)
            self.assertEqual((state.phase, state.blocked["conflict"], state.blocked["winner"]["run"]), ("cancelled", True, "run-other"))
            self.assertEqual(state.authorizations[0]["status"], "not-launched")  # reserve never reported reserved: nothing was launched
            self.assertEqual([i.status for i in state.intents if i.kind == "release"], ["done"])
            self.assertEqual(len([c for c in markers(h.fake, 21, "release") if "run=run-1" in c.body]), 1)
            self.assertTrue(events(h, "claim-race-lost"))
            with self.assertRaises(Refused) as ctx:  # no reclaim in this run; the other run owns the story
                fresh(h).reserve(S, h.snapshot, "c5d9d2e")
            self.assertEqual(ctx.exception.code, "no-reclaim")
        finally:
            h.close()

    def test_an_earlier_claimant_keeps_the_reservation(self):
        h = self.race(foreign_first=False)
        try:
            self.assertEqual(h.reserve().phase, "reserved")
            self.assertEqual(markers(h.fake, 21, "release"), [])
        finally:
            h.close()


class RunIdAndStateTests(unittest.TestCase):
    """Findings 6, 21, 22, 34, 35: run ids, torn journals, corrupt story files, backups."""

    def test_run_id_is_validated_everywhere(self):
        with tempfile.TemporaryDirectory() as tmp:
            for bad in ("../x", "/abs", "a/b", "", ".hidden", "..", "x" * 65, "run 1"):
                with self.assertRaises(Refused) as ctx:
                    Store(Path(tmp), bad)
                self.assertEqual(ctx.exception.code, "run-id-invalid", bad)
            Store(Path(tmp), "run-20261108-e01.a_b")
            policy = write_policy(Path(tmp), allow='["OM-01.02"]')
            code, out = run_cli("--policy", str(policy), "--state-dir", tmp, "--run-id", "../escape", "status")
            self.assertEqual((code, out["error"]["code"]), (3, "run-id-invalid"))
            self.assertEqual(sorted(os.listdir(tmp)), ["policy.toml"])
            code, out = run_cli("--policy", str(policy), "--live", "probe-write", "--issue", "106")
            self.assertEqual((code, out["error"]["code"]), (3, "run-id-required"))
            other = Path(tmp) / "run-other" / "stories"
            other.mkdir(parents=True)
            (other / "OM-01.02.json").write_text("{broken")
            self.assertEqual(Store(Path(tmp), "run-1").other_runs_with_active_stories(), {})  # no run.json: not a run directory (a backup or a copy)
            (Path(tmp) / "run-other" / "run.json").write_text("{}")
            self.assertEqual(Store(Path(tmp), "run-1").other_runs_with_active_stories(), {"run-other": ["OM-01.02 (unreadable story file OM-01.02.json)"]})

    def test_torn_journal_line_is_repaired_and_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp), "run-1")
            store.journal(None, "first", {})
            with store.journal_path.open("a", encoding="utf-8") as fh:
                fh.write('{"seq": 2, "at": "x", "story": null, "event": "torn", "det')  # crash mid-write, no newline
            seq = store.journal(None, "third", {})
            entries = store.read_journal()
            self.assertEqual([e["event"] for e in entries], ["first", "journal-torn-line", "third"])
            self.assertEqual((seq, entries[-1]["seq"], store.journal_count()), (3, 3, 3))
            self.assertIn("torn", entries[1]["detail"]["raw"])
            with store.journal_path.open("a", encoding="utf-8") as fh:
                fh.write("[1, 2]\n")  # parses, but is not an event record
            self.assertEqual(store.read_journal()[-1]["event"], "journal-torn-line")

    def test_corrupt_story_files_refuse_state_corrupt(self):
        h = Harness(small_backlog())
        try:
            h.claim()
            path = h.store.story_path(S)
            valid = json.loads(path.read_text(encoding="utf-8"))
            for text in ("{not json", "[1, 2]", json.dumps({"schema": 3, "story": S})):
                path.write_text(text, encoding="utf-8")
                with self.assertRaises(Refused) as ctx:
                    fresh(h).status()
                self.assertIn(ctx.exception.code, ("state-corrupt", "state-schema-mismatch"), text)
                with self.assertRaises(Refused) as ctx:
                    fresh(h).cancel(S, "x")
                self.assertIn(ctx.exception.code, ("state-corrupt", "state-schema-mismatch"), text)
            raw = {**valid, "intents": ["not-an-intent"]}  # every key present, but an intent that is not a record
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(Refused) as ctx:
                fresh(h).status()
            self.assertEqual(ctx.exception.code, "state-corrupt")
            self.assertEqual(ctx.exception.detail["path"], "OM-01.02.json")
        finally:
            h.close()

    def test_atomic_write_fsyncs_the_directory(self):
        from automation.unattended import state as state_module

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(state_module, "fsync_directory", wraps=state_module.fsync_directory) as spy:
            state_module.atomic_write_text(Path(tmp) / "a" / "f.json", "{}")
            spy.assert_called_once_with(Path(tmp) / "a")


class PolicyStrictnessTests(unittest.TestCase):
    """Findings 13 to 17: no coercion, tables, bounds, arrays, reviewer isolation."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def rejects(self, needle, **overrides):
        with self.assertRaises(PolicyError) as ctx:
            load_policy(write_policy(self.dir, **overrides))
        self.assertIn(needle, str(ctx.exception), overrides)

    def test_quoted_false_does_not_enable_optional_epics(self):
        self.rejects("include_optional_epics must be a boolean", include_optional_epics='"false"')
        self.rejects("include_later_epics must be a boolean", include_later_epics="1")

    def test_numbers_are_integers_and_bounded(self):
        self.rejects("max_delegated_tasks must be an integer", max_delegated_tasks='"two"')
        self.rejects("max_delegated_tasks must be an integer", max_delegated_tasks="true")
        self.rejects("project_number must be an integer", project_number='"2"')
        self.rejects("timeout_minutes must be within 1..", timeout_minutes="0")
        self.rejects("timeout_seconds must be within 1..", timeout_seconds="-5")
        self.rejects("max_wall_clock_minutes must be within 1..", max_wall_clock_minutes="0")

    def test_commands_must_be_arrays_of_strings_and_sections_tables(self):
        self.rejects("commands must be an array", commands='"./gradlew build"')
        self.rejects("commands entries must be non-empty strings", commands='["./gradlew build", 3]')
        self.rejects("allow must be an array", allow='"OM-01.02"')
        text = write_policy(self.dir).read_text().replace("max_wall_clock_minutes = 240", "max_wall_clock_minute = 240")  # a typo must not fall back to the default
        (self.dir / "policy.toml").write_text(text)
        with self.assertRaises(PolicyError) as ctx:
            load_policy(self.dir / "policy.toml")
        self.assertIn("budgets has unknown keys ['max_wall_clock_minute']", str(ctx.exception))
        text = write_policy(self.dir).read_text().replace("[budgets]\n", "budgets = 3\n[budgets_x]\n")
        (self.dir / "policy.toml").write_text(text)
        with self.assertRaises(PolicyError) as ctx:
            load_policy(self.dir / "policy.toml")
        self.assertIn("unknown sections", str(ctx.exception))

    def test_reviewer_needs_worktree_isolation(self):
        text = write_policy(self.dir).read_text().replace('isolation = "worktree"           # the reviewer', 'isolation = "shared"           # the reviewer')
        (self.dir / "policy.toml").write_text(text)
        with self.assertRaises(PolicyError) as ctx:
            load_policy(self.dir / "policy.toml")
        self.assertIn("targets.reviewer.isolation must be 'worktree'", str(ctx.exception))
        self.assertEqual(load_policy(write_policy(self.dir)).reviewer.isolation, "worktree")


class TransportFailClosedTests(unittest.TestCase):
    """Findings 9, 10, 20, 25, 26, 27: truncation, repository, owner kind, typed errors, shapes."""

    def setUp(self):
        self.t = GhCliTransport("gabrianoo", "owl-mast", "gabrianoo", 2)
        self.t.live = False

    def scripted(self, payload):
        self.t._run = lambda args, stdin=None: payload if isinstance(payload, str) else json.dumps(payload)

    def test_graphql_errors_classify_on_type_first(self):
        for typ, cls in (("RATE_LIMITED", Outage), ("FORBIDDEN", PermissionDenied), ("INSUFFICIENT_SCOPES", PermissionDenied), ("NOT_FOUND", NotFound), ("SOMETHING_ELSE", TransportError)):
            self.scripted({"errors": [{"type": typ, "message": "you do not have the time"}]})
            with self.assertRaises(cls, msg=typ) as ctx:
                self.t.get_issue(1)
            self.assertIs(type(ctx.exception), cls, typ)
        self.scripted({"errors": [{"message": "API rate limit exceeded for user"}]})
        with self.assertRaises(Outage):
            self.t.get_issue(1)
        # the production path: ``gh api graphql`` exits 1 and prints the response with its typed errors
        def failing_gh(argv, input=None, capture_output=True, text=True, timeout=None, check=False):
            return subprocess.CompletedProcess(argv, 1, json.dumps({"data": None, "errors": [{"type": "RATE_LIMITED", "message": "API rate limit exceeded"}]}), "gh: API rate limit exceeded (HTTP 200)")
        real = GhCliTransport("gabrianoo", "owl-mast", "gabrianoo", 2)
        with mock.patch.object(subprocess, "run", failing_gh):
            with self.assertRaises(Outage):
                real.get_issue(1)
        def forbidden_gh(argv, input=None, capture_output=True, text=True, timeout=None, check=False):
            return subprocess.CompletedProcess(argv, 1, json.dumps({"data": None, "errors": [{"type": "FORBIDDEN", "message": "Resource not accessible"}]}), "gh: Resource not accessible")
        with mock.patch.object(subprocess, "run", forbidden_gh):
            with self.assertRaises(PermissionDenied):
                real.get_issue(1)
        self.scripted({"errors": [{"message": "we do not have any record of that"}]})  # message-only fallback stays conservative
        with self.assertRaises(PermissionDenied):
            self.t.get_issue(1)

    def test_null_data_and_truncated_connections_refuse(self):
        self.scripted({"data": None})
        with self.assertRaises(TransportError):
            self.t.get_issue(1)
        node = {"number": 1, "id": "I_1", "title": "t", "state": "OPEN", "stateReason": None, "updatedAt": "u", "closedAt": None, "body": "", "labels": {"pageInfo": {"hasNextPage": True}, "nodes": [{"name": "story"}]}, "parent": None}
        self.scripted({"data": {"repository": {"issue": node}}})
        with self.assertRaises(TransportError) as ctx:
            self.t.get_issue(1)
        self.assertIn("truncated", str(ctx.exception))
        item = {"id": "PVTI_1", "updatedAt": "u", "content": {"number": 1, "repository": {"nameWithOwner": REPO}}, "fieldValues": {"pageInfo": {"hasNextPage": True}, "nodes": []}}
        self.scripted({"data": {"node": item}})
        with self.assertRaises(TransportError):
            self.t.get_project_item("PVTI_1")
        self.scripted({"data": {"repositoryOwner": {"projectV2": {"id": "P", "fields": {"pageInfo": {"hasNextPage": True}, "nodes": []}}}}})
        with self.assertRaises(TransportError):
            self.t.project_info()

    def test_project_owner_may_be_an_organization_and_null_is_not_found(self):
        self.scripted({"data": {"repositoryOwner": None}})
        with self.assertRaises(NotFound):
            self.t.project_info()
        self.scripted({"data": {"repositoryOwner": {"projectV2": None}}})
        with self.assertRaises(NotFound):
            self.t.list_project_items()
        queries = []
        self.t._run = lambda args, stdin=None: queries.append(args[3]) or json.dumps({"data": {"repositoryOwner": {"projectV2": {"id": "P", "fields": {"nodes": [{"id": "F", "name": "Status", "options": []}]}}}}})
        self.t.project_info()
        self.assertIn('repositoryOwner(login:"gabrianoo"){ ... on ProjectV2Owner{ projectV2(number:2)', queries[0])
        self.assertNotIn("user(login", queries[0])

    def test_items_of_other_repositories_are_dropped_and_duplicates_refuse(self):
        fake = small_backlog()
        fake.add_foreign_item("PVTI_X", 21, "Done", "OM-01.02", "someone/else")  # another repo's #21 is Done
        snap = take_snapshot(fake, REPO, "now")
        self.assertEqual(snap.by_id()[S].status, "Ready")
        fake.add_foreign_item("PVTI_DUP", 21, "Done", "OM-01.02", REPO)
        with self.assertRaises(Refused) as ctx:
            take_snapshot(fake, REPO, "now")
        self.assertEqual(ctx.exception.code, "ambiguous-project-item")
        fake = small_backlog()
        fake.items["PVTI_21"] = fake.items["PVTI_21"].__class__(**{**fake.items["PVTI_21"].__dict__, "repository": None})  # unknown repository: dropped
        self.assertEqual(take_snapshot(fake, REPO, "now").by_id()[S].item_id, None)

    def test_unexpected_comment_json_is_a_transport_error(self):
        self.t._run = lambda args, stdin=None: '{"id": 1, "body": "x", "created_at": "t"}\nnot json'
        with self.assertRaises(TransportError):
            self.t.list_comments(1)
        self.t._run = lambda args, stdin=None: '{"id": 1, "body": "x", "created_at": "t"}'  # no login
        with self.assertRaises(TransportError):
            self.t.list_comments(1)
        self.t._run = lambda args, stdin=None: '{"id": 5, "body": "x", "created_at": "t"}'  # no user on the POST response
        with self.assertRaises(TransportError):
            self.t.post_comment(1, "x")
        self.t._run = lambda args, stdin=None: "machine\n"
        self.assertEqual(self.t.viewer_login(), "machine")
        self.t._run = lambda args, stdin=None: "\n"
        with self.assertRaises(TransportError):
            self.t.viewer_login()
        for payload in ({"data": {"repository": {"issues": {"nodes": [{"number": 1}], "pageInfo": {"hasNextPage": False}}}}}, {"data": {"repository": {"issues": "nope"}}}, {"data": {"repository": {}}}):
            self.scripted(payload)
            with self.assertRaises(TransportError, msg=str(payload)):
                self.t.list_issues()
        self.scripted({"data": {"repositoryOwner": {"projectV2": {"items": {"nodes": [{"id": "PVTI_1"}], "pageInfo": {"hasNextPage": False}}}}}})
        with self.assertRaises(TransportError):
            self.t.list_project_items()
        self.scripted({"data": {"repository": {"pullRequest": {"number": 7}}}})
        with self.assertRaises(TransportError):
            self.t.get_pull_request(7)


class EligibilityAndProposalTests(unittest.TestCase):
    """Findings 11 and 12: CI-backed proposals and unknown dependencies."""

    def test_unknown_dependency_or_prerequisite_is_unknown_even_with_the_exception(self):
        fake = small_backlog()
        fake.add_issue(issue(25, "OM-02.02", "Ghost dep", labels=("story",), parent=2, depends_on="OM-09.09", tasks=2), "Ready", "OM-02.02")
        snap = take_snapshot(fake, REPO, "now")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        policy = load_policy(write_policy(Path(tmp.name), allow='["OM-02.02"]', contract_design_exceptions='["OM-02.02"]'))
        d = decide("OM-02.02", snap, policy)
        self.assertEqual(d.outcome, "unknown-eligibility")
        self.assertIn("OM-09.09: dependency not in the snapshot", d.reasons)
        fake = small_backlog()
        fake.add_issue(issue(3, "E03", "Prereq ghost", labels=("epic",), epic_prereq="E42"), "Backlog", "E03")
        fake.add_issue(issue(26, "OM-03.01", "Child", labels=("story",), parent=3, depends_on="None", tasks=2), "Ready", "OM-03.01")
        d = decide("OM-03.01", take_snapshot(fake, REPO, "now"), load_policy(write_policy(Path(tmp.name), allow='["OM-03.01"]', contract_design_exceptions='["OM-03.01"]')))
        self.assertEqual((d.outcome, d.reasons), ("unknown-eligibility", ("E42: epic prerequisite not in the snapshot",)))

    def test_proposal_needs_a_successful_rollup(self):
        for checks in ("PENDING", "ERROR", "EXPECTED", None):
            h = Harness(small_backlog())
            try:
                h.to_review_approved()
                h.fake.pull_requests[7] = PullRequestRecord(7, "OPEN", h.sha, False, (), checks)
                with self.assertRaises(Refused) as ctx:
                    h.coordinator.propose_evidence(S, h.sha, 7, [], "s")
                self.assertEqual(ctx.exception.code, "pr-checks-not-successful", checks)
                self.assertEqual(markers(h.fake, 21, "proposal"), [])
                self.assertEqual(h.store.load_story(S).phase, "review-approved")
            finally:
                h.close()


class CliContractTests(unittest.TestCase):
    """Findings 18, 19, 24: one JSON document and exit code 3 whatever the input."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.policy = str(write_policy(self.dir, allow='["OM-01.02"]'))

    def tearDown(self):
        self.tmp.cleanup()

    def test_bad_json_arguments_are_input_invalid(self):
        for bad in ("{not json", "x" * 5000, str(self.dir / "missing.json"), "{\"a\": 1} trailing"):  # bad JSON, a path too long to test, a missing file, trailing garbage
            with self.assertRaises(UnattendedError) as ctx:
                cli._load_json_arg(bad)
            self.assertEqual(ctx.exception.code, "input-invalid", bad[:30])
        (self.dir / "ok.json").write_text('{"taskId": "t"}')
        self.assertEqual(cli._load_json_arg(str(self.dir / "ok.json")), {"taskId": "t"})
        self.assertEqual(cli._load_json_arg('{"taskId": "t"}'), {"taskId": "t"})
        snapshot = json.loads((FIXTURES / "backlog-snapshot-2026-11-06.json").read_text())
        snapshot["entries"][0]["surprise"] = 1  # a newer or foreign entry shape
        (self.dir / "snap.json").write_text(json.dumps(snapshot))
        code, out = run_cli("--policy", self.policy, "--snapshot", str(self.dir / "snap.json"), "plan")
        self.assertEqual((code, out["error"]["code"]), (3, "input-invalid"))

    def test_unexpected_exceptions_stay_inside_the_json_contract(self):
        with mock.patch.object(cli, "load_policy", side_effect=RuntimeError("boom")):
            code, out = run_cli("--policy", self.policy, "status")
        self.assertEqual((code, out["error"]["code"]), (4, "internal"))  # 4: the tool crashed; 3 stays the refusal code
        self.assertIn("RuntimeError: boom", out["error"]["message"])
        self.assertTrue(any("RuntimeError" in line for line in out["error"]["traceback"]))

    def test_probe_write_exit_code_reports_non_idempotence(self):
        with mock.patch.object(cli, "GhCliTransport", lambda *a, **k: small_backlog()):
            code, out = run_cli("--policy", self.policy, "--live", "--run-id", "probe-1", "probe-write", "--issue", "106")
            self.assertEqual((code, out["idempotent"]), (0, True))
            with mock.patch.object(cli, "write_probe", return_value={"idempotent": False, "comments_with_marker": [1, 2]}):
                code, out = run_cli("--policy", self.policy, "--live", "--run-id", "probe-1", "probe-write", "--issue", "106")
            self.assertEqual((code, out["idempotent"]), (2, False))


class CleanupPathTests(unittest.TestCase):
    """Findings 23, 28, 29, 30, 31, 35: drift, unreadable git, cancel-run, resume, receipts, backups."""

    def setUp(self):
        self.h = Harness(small_backlog(), allow='["OM-01.02", "OM-01.04"]', max_stories_per_run="2")

    def tearDown(self):
        self.h.close()

    def test_policy_drift_is_a_run_stop_that_leaves_cleanup_open(self):
        self.h.claim()
        (Path(self.h.tmpdir.name) / "d").mkdir(exist_ok=True)
        drifted = load_policy(write_policy(Path(self.h.tmpdir.name) / "d", allow='["OM-01.02", "OM-01.04"]', max_stories_per_run="2", max_delegated_tasks="7"))
        c = Coordinator(self.h.fake, drifted, Store(self.h.state_dir, "run-1"), live=True)
        self.assertEqual(c.status()["stop"], "policy-drift")
        for op in (lambda: c.reserve("OM-01.04", self.h.snapshot, "c5d9d2e"), lambda: c.record_head(S, self.h.sha, self.h.terminal()), lambda: c.authorize_review(S, self.h.sha)):
            with self.assertRaises(Refused) as ctx:
                op()
            self.assertEqual(ctx.exception.code, "policy-drift")
        self.assertEqual(c.record_task_terminal(S, self.h.terminal(status="cancelled")).active_task, None)
        self.assertEqual(c.cancel(S, "policy changed").phase, "cancelled")
        self.assertEqual(len(markers(self.h.fake, 21, "release")), 1)
        self.assertEqual(len(events(self.h, "policy-drift")), 1)
        Coordinator(self.h.fake, drifted, Store(self.h.state_dir, "run-1"), live=True).status()
        self.assertEqual(len(events(self.h, "policy-drift")), 1)  # journaled once per digest, not per open

    def test_unreadable_git_refuses_without_invalidating_evidence(self):
        self.h.to_review_approved()
        with mock.patch.object(coordinator_module, "git_head", return_value=None):
            with self.assertRaises(Refused) as ctx:
                self.h.coordinator.record_review(S, self.h.sha, "approved", "again", None)
            self.assertEqual(ctx.exception.code, "worktree-unreadable")
        with mock.patch.object(coordinator_module, "git_clean", return_value=(None, "git status failed: timeout")):
            self.h.fake.pull_requests[7] = PullRequestRecord(7, "OPEN", self.h.sha, False, (), "SUCCESS")
            with self.assertRaises(Refused) as ctx:
                self.h.coordinator.propose_evidence(S, self.h.sha, 7, [], "s")
            self.assertEqual(ctx.exception.code, "worktree-unreadable")
        state = self.h.store.load_story(S)
        self.assertEqual((state.phase, state.approved_sha), ("review-approved", self.h.sha))
        self.assertEqual(events(self.h, "unreported-worktree-change"), [])

    def test_run_checks_refuses_when_git_cannot_answer_and_records_nothing(self):
        self.h.claim()
        self.h.coordinator.record_head(S, self.h.sha, self.h.terminal())
        with mock.patch.object(coordinator_module, "git_clean", return_value=(None, "git status failed: timeout")):
            with self.assertRaises(Refused) as ctx:
                self.h.coordinator.run_checks(S, self.h.sha, str(self.h.worktree), passing_runner)
            self.assertEqual(ctx.exception.code, "worktree-unreadable")
        heads = iter([self.h.sha, None])  # fine before the commands, unreadable after them
        with mock.patch.object(coordinator_module, "git_head", side_effect=lambda cwd: next(heads)):
            with self.assertRaises(Refused) as ctx:
                self.h.coordinator.run_checks(S, self.h.sha, str(self.h.worktree), passing_runner)
            self.assertEqual(ctx.exception.code, "worktree-unreadable")
        state = self.h.store.load_story(S)
        self.assertEqual((state.phase, state.checks), ("implemented", []))

    def test_cancel_run_reports_every_refusal_and_validates_its_maps(self):
        self.h.claim()
        with self.assertRaises(Refused) as ctx:
            self.h.coordinator.cancel_run("stop", task_evidence=[{"taskId": "x"}])
        self.assertEqual(ctx.exception.code, "input-invalid")
        self.assertFalse(self.h.store.load_run().cancelled)
        result = self.h.coordinator.cancel_run("stop", task_evidence={S: {"taskId": "task-impl-1", "runId": "task-impl-1:run:9", "status": "cancelled"}})  # wrong run: refused per story, run still cancelled
        self.assertEqual([a["code"] for a in result["awaiting_worker_termination"]], ["run-mismatch"])
        self.assertTrue(self.h.store.load_run().cancelled)
        self.assertEqual(self.h.store.load_story(S).phase, "claimed")

    def test_resume_replays_owed_cleanups_before_the_worktree_check(self):
        self.h.claim()
        self.h.fake.fail_once["post_comment"] = Outage("503")
        with self.assertRaises(Refused) as ctx:  # cancel needs terminal evidence; give it, the release post fails once
            self.h.coordinator.cancel(S, "stop")
        self.assertEqual(ctx.exception.code, "worker-not-terminal")
        state = self.h.coordinator.cancel(S, "stop", self.h.terminal(status="cancelled"))
        self.assertEqual((state.phase, [i.status for i in state.intents if i.kind == "release"]), ("cancelled", ["pending"]))
        gone = lambda path, branch: (False, "worktree removed")  # noqa: E731
        resumed = fresh(self.h).resume(S, gone)
        self.assertEqual([i.status for i in resumed.intents if i.kind == "release"], ["done"])
        self.assertEqual(len(markers(self.h.fake, 21, "release")), 1)

    def test_non_object_receipt_is_receipt_invalid(self):
        self.h.reserve()
        for receipt in (["taskId"], "task-impl-1", 7):
            with self.assertRaises(ReceiptInvalid):
                self.h.coordinator.bind_receipt(S, receipt, str(self.h.worktree), "t3/om-01-02", ok_worktree)
        self.assertEqual(self.h.store.load_story(S).phase, "reserved")

    def test_backup_names_carry_the_authorization_and_never_overwrite(self):
        from automation.tests.test_run_identity import HistoricalReconciliationTests

        case = HistoricalReconciliationTests("test_reconciliation_resolves_only_the_obligation_and_is_idempotent")
        case.setUp()
        try:
            moment = ["2026-11-09T10:00:00Z"]
            case.h.coordinator.now = lambda: moment[0]
            state = case.reconcile()
            backups = sorted(p.name for p in case.h.store.story_path(S).parent.iterdir() if ".bak-" in p.name)
            self.assertEqual(backups, [f"OM-01.02.json.bak-2026-11-09T100000Z-{case.auth['id'].replace(':', '_')}"])
            self.assertEqual(state.authorization(case.auth["id"])["status"], "consumed")
            # a different reconciliation at the same instant must not overwrite the first audit copy
            blocked = Coordinator(case.h.fake, case.h.policy, Store(case.h.state_dir, "run-1"), now=lambda: moment[0], live=True)
            other_evidence = {**case.evidence, "latestTerminalStatus": "failed"}
            with self.assertRaises(Refused) as ctx:
                blocked.reconcile_retained_execution(S, case.auth["id"], case.receipt, other_evidence, "r", "p")
            self.assertEqual(ctx.exception.code, "conflicting-evidence")  # idempotency check refuses before the backup
            story = case.h.store.load_story(S)
            story.authorizations[-1]["status"], story.authorizations[-1]["task_id"], story.authorizations[-1]["run_id"] = "revoked", None, None  # LABELLED MUTATION: reopen the obligation so a second reconcile reaches the backup
            story.task_history = [r for r in story.task_history if r.get("runId") != case.run5]
            story.implementer_receipts = [r for r in story.implementer_receipts if not r.get("reconciled")]
            case.h.store.save_story(story)
            with self.assertRaises(Refused) as ctx:
                blocked.reconcile_retained_execution(S, case.auth["id"], case.receipt, case.evidence, "r", "p")
            self.assertEqual(ctx.exception.code, "backup-exists")
        finally:
            case.tearDown()


class ProbeRobustnessTests(unittest.TestCase):
    """Findings 32 and 33: commands that cannot be parsed and a gh that is missing or hangs."""

    def test_unparsable_or_empty_commands_are_failed_results(self):
        results = run_commands(["echo 'unbalanced", "", "   "], None, 5, fail_fast=False)
        self.assertEqual([r["returncode"] for r in results], [-1, -1, -1])
        self.assertTrue(all("cannot be parsed" in r["error"] for r in results))

    def test_check_permissions_reports_a_missing_or_hanging_gh(self):
        def missing(argv, cwd, timeout):
            raise FileNotFoundError("gh")

        report = check_permissions("o", "r", "o", 2, missing)
        self.assertFalse(report["basic_access"])
        self.assertTrue(any("could not be observed" in p for p in report["problems"]))

        def hanging(argv, cwd, timeout):
            raise subprocess.TimeoutExpired(argv, timeout)

        report = check_permissions("o", "r", "o", 2, hanging)
        self.assertFalse(report["basic_access"])
        self.assertEqual(len([p for p in report["problems"] if "could not be observed" in p]), 3)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
