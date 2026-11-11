"""Regressions for the bmad-review of PR #115 (review 5831815549, 2026-11-09): the claim race
settled on every path, trust that fails closed across identities and shared run ids, the
GitHub-side single-active-story check, fail-closed eligibility over unknown facts, tolerant
recovery over corrupt files, durable directories, the canonical policy digest, nested-connection
pagination, the reviewer's own worktree, late receipts under drift, the CLI argument contract,
and the verification gaps (queries pinned, real git failures, receipt isolation)."""

import io
import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from automation.tests.fake_transport import FakeTransport, issue, small_backlog
from automation.tests.support import FIXTURES, IMPLEMENTER, REVIEW_BRANCH, REVIEW_WORKTREE, REVIEWER, Harness, ok_worktree, passing_runner, receipt, write_policy
from automation.unattended import cli
from automation.unattended import coordinator as coordinator_module
from automation.unattended import state as state_module
from automation.unattended.backlog import take_snapshot, verify_mapping
from automation.unattended.coordinator import Coordinator, git_clean
from automation.unattended.eligibility import decide
from automation.unattended.errors import Conflict, Outage, PermissionDenied, PolicyError, ReceiptInvalid, Refused, TransportError, UnattendedError
from automation.unattended.github import Comment, GhCliTransport, classify, render_marker
from automation.unattended.policy import Target, canonical_digest, load_policy
from automation.unattended.probes import check_permissions
from automation.unattended.receipts import validate_receipt
from automation.unattended.state import Store, StoryState, validate_run_id

S = "OM-01.02"
REPO = "gabrianoo/owl-mast"
EARLY = "2026-11-06T12:59:00Z"  # before any fake-transport tick


def fresh(h: Harness, run_id: str = "run-1") -> Coordinator:
    return Coordinator(h.fake, h.policy, Store(h.state_dir, run_id), live=True)


def markers(fake: FakeTransport, number: int, kind: str):
    return [c for c in fake.comments[number] if c.marker and c.marker["kind"] == kind]


def events(h: Harness, name: str) -> list[dict]:
    return [e for e in h.store.read_journal() if e["event"] == name]


def run_cli(*argv) -> tuple[int, dict]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cli.main(list(argv))
    return code, json.loads(buf.getvalue())


def arm_failure_after_claim(h: Harness, reads_after_post: int, failure=None, hide_ours: bool = False, run: str = "run-1"):
    """Fail (or hide our own claim, the one of ``run``, in) the N-th comment read after our claim comment lands."""
    original_list, original_post = h.fake.list_comments, h.fake.post_comment
    state = {"posted": False, "reads": 0}

    def post(number, body):
        comment = original_post(number, body)
        if "kind=claim" in body:
            state["posted"] = True
        return comment

    def listing(number):
        comments = original_list(number)
        if state["posted"]:
            state["reads"] += 1
            if state["reads"] == reads_after_post:
                if failure is not None:
                    raise failure
            if state["reads"] >= reads_after_post and hide_ours:
                return [c for c in comments if not (c.author == "machine" and (c.marker or {}).get("kind") == "claim" and (c.marker or {}).get("run") == run)]
        return comments

    h.fake.list_comments, h.fake.post_comment = listing, post


class ClaimRaceDurabilityTests(unittest.TestCase):
    """Finding 1: the race is settled on every path, or the reservation is not reported."""

    def arm_failure_after_claim(self, h: Harness, reads_after_post: int, failure=None, hide_ours: bool = False):
        arm_failure_after_claim(h, reads_after_post, failure, hide_ours)

    def test_failed_re_read_leaves_the_race_unsettled_until_resume_settles_it(self):
        h = Harness(small_backlog())
        try:
            self.arm_failure_after_claim(h, reads_after_post=2, failure=Outage("503 at the race re-read"))  # read 1: the post's read-back; read 2: the race
            with self.assertRaises(Outage):
                h.reserve()
            state = h.store.load_story(S)
            self.assertEqual((state.phase, state.claim["race_settled"]), ("reserved", False))
            with self.assertRaises(Refused) as ctx:  # nothing may bind while the race is open: reserve never reported reserved
                fresh(h).bind_receipt(S, IMPLEMENTER, str(h.worktree), "t3/om-01-02", ok_worktree)
            self.assertEqual(ctx.exception.code, "claim-race-unsettled")
            h.fake.list_comments = FakeTransport.list_comments.__get__(h.fake)  # the transport recovers
            resumed = fresh(h).resume(S, ok_worktree)
            self.assertEqual((resumed.phase, resumed.claim["race_settled"]), ("reserved", True))
            self.assertTrue(events(h, "claim-race-settled"))
            self.assertEqual(fresh(h).bind_receipt(S, IMPLEMENTER, str(h.worktree), "t3/om-01-02", ok_worktree).phase, "claimed")
        finally:
            h.close()

    def test_resume_settles_a_lost_race_by_cancelling_and_releasing(self):
        h = Harness(small_backlog())
        try:
            self.arm_failure_after_claim(h, reads_after_post=2, failure=Outage("503"))
            with self.assertRaises(Outage):
                h.reserve()
            h.fake.list_comments = FakeTransport.list_comments.__get__(h.fake)
            # another machine's claim that landed before ours, which the failed re-read never saw
            h.fake.comments[21].insert(0, Comment(5, render_marker(kind="claim", run="run-other", story=S, op="claim") + "\nearlier", "machine", EARLY))
            with self.assertRaises(Conflict) as ctx:
                fresh(h).resume(S, ok_worktree)
            self.assertEqual(ctx.exception.code, "claim-race-lost")
            state = h.store.load_story(S)
            self.assertEqual((state.phase, state.blocked["winner"]["run"], state.authorizations[0]["status"]), ("cancelled", "run-other", "not-launched"))
            self.assertEqual(len([c for c in markers(h.fake, 21, "release") if "run=run-1" in c.body]), 1)
            with self.assertRaises(Refused) as ctx:
                fresh(h).bind_receipt(S, IMPLEMENTER, str(h.worktree), "t3/om-01-02", ok_worktree)
            self.assertEqual(ctx.exception.code, "no-authorization")
        finally:
            h.close()

    def test_a_claim_that_cannot_be_read_back_is_conflict_not_reserved(self):
        h = Harness(small_backlog())
        try:
            self.arm_failure_after_claim(h, reads_after_post=2, hide_ours=True)  # the post's read-back sees it, the race re-read does not
            with self.assertRaises(Conflict) as ctx:
                h.reserve()
            self.assertEqual(ctx.exception.code, "claim-unverifiable")
            state = h.store.load_story(S)
            self.assertEqual((state.phase, state.blocked["conflict"], state.blocked["race_unsettled"]), ("conflict", True, True))
            h.fake.list_comments = FakeTransport.list_comments.__get__(h.fake)
            cancelled = fresh(h).cancel(S, "operator decision")  # structurally unlaunched: cancel needs no attestation
            self.assertEqual((cancelled.phase, cancelled.authorizations[0]["status"], cancelled.authorizations[0]["resolution"]), ("cancelled", "not-launched", "structural"))
            self.assertEqual(len(markers(h.fake, 21, "release")), 1)
        finally:
            h.close()

    def test_lost_race_with_a_failed_release_post_stays_pending_and_resume_posts_it_once(self):
        """Finding 27: the ``except UnattendedError`` branch of ``_settle_claim_race``."""
        h = Harness(small_backlog())
        original_post = h.fake.post_comment

        def interleaved(number, body):
            if "kind=claim" in body and not any((c.marker or {}).get("run") == "run-other" for c in h.fake.comments[number]):
                h.fake.comments[number].append(Comment(5, render_marker(kind="claim", run="run-other", story=S, op="claim") + "\nearlier", "machine", EARLY))
                posted = original_post(number, body)
                h.fake.fail_once["post_comment"] = Outage("503 on the release")  # the NEXT post (our release) fails once
                return posted
            return original_post(number, body)

        h.fake.post_comment = interleaved
        try:
            with self.assertRaises(Conflict) as ctx:
                h.reserve()
            self.assertEqual(ctx.exception.code, "claim-race-lost")
            state = h.store.load_story(S)
            self.assertEqual((state.phase, state.blocked["github_error"]["code"]), ("cancelled", "outage"))
            self.assertEqual([i.status for i in state.intents if i.kind == "release"], ["pending"])
            self.assertTrue(events(h, "cancelled-github-write-failed"))
            self.assertEqual(markers(h.fake, 21, "release"), [])
            h.fake.post_comment = original_post
            resumed = fresh(h).resume(S, ok_worktree)
            self.assertEqual([i.status for i in resumed.intents if i.kind == "release"], ["done"])
            self.assertEqual(len(markers(h.fake, 21, "release")), 1)
            fresh(h).resume(S, ok_worktree)
            self.assertEqual(len(markers(h.fake, 21, "release")), 1)  # exactly once
        finally:
            h.close()

    def test_resume_completing_a_claim_settles_the_race(self):
        h = Harness(small_backlog())
        try:
            h.fake.crash_after_post = True
            with self.assertRaises(Exception):
                h.reserve()
            self.assertEqual(h.store.load_story(S).phase, "claim-incomplete")
            resumed = fresh(h).resume(S, ok_worktree)
            self.assertEqual((resumed.phase, resumed.claim["race_settled"]), ("reserved", True))
            self.assertTrue(events(h, "reservation-completed-on-resume") and events(h, "claim-race-settled"))
        finally:
            h.close()

    def test_a_crash_after_the_resume_post_is_settled_by_the_next_resume(self):
        h = Harness(small_backlog())
        try:
            h.fake.fail_once["post_comment"] = Outage("503 on the claim post")
            with self.assertRaises(Outage):
                h.reserve()
            self.assertEqual(h.store.load_story(S).phase, "claim-incomplete")  # the claim intent is pending, nothing landed
            h.fake.crash_after_post = True
            with self.assertRaises(Exception):
                fresh(h).resume(S, ok_worktree)  # the replayed post lands, the process dies before the settle
            state = h.store.load_story(S)
            self.assertEqual((state.phase, state.claim["race_settled"]), ("claim-incomplete", False))  # the post landed, nothing was checkpointed
            with self.assertRaises(Refused):
                fresh(h).bind_receipt(S, IMPLEMENTER, str(h.worktree), "t3/om-01-02", ok_worktree)
            resumed = fresh(h).resume(S, ok_worktree)  # adopts the landed marker, then settles the race before reporting reserved
            self.assertEqual((resumed.phase, resumed.claim["race_settled"], len(markers(h.fake, 21, "claim"))), ("reserved", True, 1))
        finally:
            h.close()

    def test_a_pending_claim_replay_re_checks_claims_elsewhere(self):
        h = Harness(small_backlog(), allow='["OM-01.02", "OM-01.04"]', max_stories_per_run="2")
        try:
            h.fake.fail_once["post_comment"] = Outage("503 on the claim post")
            with self.assertRaises(Outage):
                h.reserve()
            other = Coordinator(h.fake, h.policy, Store(h.state_dir.parent / "another-machine", "run-other"), live=True)
            other.reserve("OM-01.04", h.snapshot, "c5d9d2e")  # lands while our reservation is interrupted
            resumed = fresh(h).resume(S, ok_worktree)
            self.assertEqual((resumed.phase, resumed.blocked["release_owed"]), ("cancelled", False))
            self.assertIn("another coordinator claimed another allowlisted story", resumed.blocked["reason"])
            self.assertEqual([c for c in markers(h.fake, 21, "claim")], [])  # nothing was posted
        finally:
            h.close()

    def test_states_without_the_flag_are_read_as_settled(self):
        h = Harness(small_backlog())
        try:
            h.reserve()
            state = h.store.load_story(S)
            del state.claim["race_settled"]  # LABELLED MUTATION: a reservation written before the flag existed
            h.store.save_story(state)
            self.assertEqual(fresh(h).bind_receipt(S, IMPLEMENTER, str(h.worktree), "t3/om-01-02", ok_worktree).phase, "claimed")
        finally:
            h.close()


class IdentityAndInstanceTests(unittest.TestCase):
    """Findings 2, 3 and 4: shared run ids, claims from any author count, release by its own author clears, App tokens."""

    def test_two_coordinators_sharing_a_run_id_do_not_adopt_each_others_claim(self):
        h = Harness(small_backlog())
        try:
            other = Coordinator(h.fake, h.policy, Store(h.state_dir.parent / "elsewhere", "run-1"), live=True)  # same run id, another state dir
            other.reserve(S, h.snapshot, "c5d9d2e")
            self.assertRegex(markers(h.fake, 21, "claim")[0].body, r"inst=[0-9a-f]{16}")
            with self.assertRaises(Refused) as ctx:
                h.reserve()
            self.assertIn("claimed by another run", str(ctx.exception))
            self.assertEqual(len(markers(h.fake, 21, "claim")), 1)  # nothing posted, nothing adopted
            self.assertIsNone(h.store.load_story(S))
        finally:
            h.close()

    def test_a_claim_by_another_identity_blocks_and_only_its_own_release_clears_it(self):
        h = Harness(small_backlog())
        try:
            h.fake.add_comment(21, render_marker(kind="claim", run="run-b", story=S, op="claim") + "\noperator B's machine", "operator-b")
            with self.assertRaises(Refused) as ctx:
                h.reserve()
            self.assertEqual(ctx.exception.detail["foreign"][0]["author"], "operator-b")
            self.assertEqual(len(events(h, "foreign-claim-counted")), 1)
            h.fake.add_comment(21, render_marker(kind="release", run="run-b", story=S, op="release") + "\nforged", "stranger")  # a stranger cannot release B's claim
            with self.assertRaises(Refused):
                h.reserve()
            h.fake.add_comment(21, render_marker(kind="release", run="run-b", story=S, op="release") + "\nB is done", "machine")  # nor can our identity release it
            with self.assertRaises(Refused):
                h.reserve()
            h.fake.add_comment(21, render_marker(kind="release", run="run-b", story=S, op="release") + "\nB is done", "operator-b")  # B's own release does
            self.assertEqual(h.reserve().phase, "reserved")
            self.assertEqual(len(events(h, "foreign-claim-counted")), 1)  # journaled once per comment, not per read
        finally:
            h.close()

    def test_viewer_login_falls_back_to_graphql_for_integration_tokens(self):
        t = GhCliTransport("gabrianoo", "owl-mast", "gabrianoo", 2)
        calls = []

        def run(args, stdin=None):
            calls.append(args)
            if args[:2] == ["api", "user"]:
                raise PermissionDenied("HTTP 403: Resource not accessible by integration")
            return json.dumps({"data": {"viewer": {"login": "owl-mast-bot[bot]"}}})

        t._run = run
        self.assertEqual(t.viewer_login(), "owl-mast-bot[bot]")
        self.assertIn("viewer{ login }", calls[1][3])
        t._run = lambda args, stdin=None: (_ for _ in ()).throw(PermissionDenied("HTTP 403")) if args[:2] == ["api", "user"] else json.dumps({"data": {"viewer": None}})
        with self.assertRaises(TransportError):
            t.viewer_login()


class ClaimsElsewhereTests(unittest.TestCase):
    """Finding 10: one active story across state directories and machines, checked on GitHub."""

    def test_an_active_claim_on_another_allowlisted_story_refuses_admission_anywhere(self):
        h = Harness(small_backlog(), allow='["OM-01.02", "OM-01.04"]', max_stories_per_run="2")
        try:
            other = Coordinator(h.fake, h.policy, Store(h.state_dir.parent / "another-machine", "run-other"), live=True)
            other.reserve("OM-01.04", h.snapshot, "c5d9d2e")
            with self.assertRaises(Refused) as ctx:
                h.reserve()
            self.assertEqual(ctx.exception.code, "claim-active-elsewhere")
            self.assertEqual(list(ctx.exception.detail["claims"]), ["OM-01.04"])
            self.assertIsNone(h.store.load_story(S))
            auth = other.store.load_story("OM-01.04").authorizations[0]["id"]
            other.cancel("OM-01.04", "done elsewhere", no_launch={"authorization": auth, "reason": "never launched"})  # the release by the same identity and run clears it
            self.assertEqual(h.reserve().phase, "reserved")
        finally:
            h.close()


class EligibilityUnknownFactsTests(unittest.TestCase):
    """Finding 5: every unknown dependency fact is unknown-eligibility, exception or not."""

    def policy(self, tmp, **overrides):
        return load_policy(write_policy(Path(tmp), **overrides))

    def test_dropped_project_item_unknown_close_reason_and_reopened_dependency_are_unknown(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        policy = self.policy(tmp.name, allow='["OM-01.02"]', contract_design_exceptions='["OM-01.02"]')
        fake = small_backlog()
        fake.items["PVTI_20"] = fake.items["PVTI_20"].__class__(**{**fake.items["PVTI_20"].__dict__, "repository": "someone/else"})  # the dependency's item belongs to another repo: dropped
        d = decide(S, take_snapshot(fake, REPO, "now"), policy)
        self.assertEqual(d.outcome, "unknown-eligibility")
        self.assertIn("OM-01.01: no Project item or empty Status; fail closed", d.reasons)
        fake = small_backlog()
        closed = fake.issues[20]
        fake.issues[20] = closed.__class__(**{**closed.__dict__, "state_reason": "DUPLICATE"})
        self.assertEqual(decide(S, take_snapshot(fake, REPO, "now"), policy).outcome, "unknown-eligibility")
        fake.issues[20] = closed.__class__(**{**closed.__dict__, "state": "OPEN", "closed_at": None, "state_reason": None})
        self.assertEqual(decide(S, take_snapshot(fake, REPO, "now"), policy).outcome, "unknown-eligibility")
        fake.issues[20] = closed.__class__(**{**closed.__dict__, "state": "OPEN", "closed_at": None, "state_reason": None})
        fake.set_status_externally(20, "In progress")  # consistently not done: unmet, so the exception applies
        self.assertEqual(decide(S, take_snapshot(fake, REPO, "now"), policy).outcome, "dispatchable-contract-design-only")

    def test_epic_prerequisite_with_an_unknown_child_is_unknown(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        fake = small_backlog()
        fake.add_issue(issue(3, "E03", "Prereq", labels=("epic",), epic_prereq="E01"), "Backlog", "E03")
        fake.add_issue(issue(26, "OM-03.01", "Child", labels=("story",), parent=3, depends_on="None", tasks=2), "Ready", "OM-03.01")
        policy = self.policy(tmp.name, allow='["OM-03.01"]', contract_design_exceptions='["OM-03.01"]')
        fake.set_status_externally(22, "Done")  # OM-01.03 Done but OPEN: inconsistent, so E01 is unknown, not incomplete
        d = decide("OM-03.01", take_snapshot(fake, REPO, "now"), policy)
        self.assertEqual(d.outcome, "unknown-eligibility")
        self.assertIn("E01: the state of OM-01.03 is unknown; fail closed", d.reasons)


class RepositoryFilterTests(unittest.TestCase):
    """Finding 6: case-insensitive repository match, dropped items reported, an all-foreign Project refuses."""

    def test_case_differences_attach_and_dropped_items_are_counted(self):
        fake = small_backlog()
        for item_id, item in list(fake.items.items()):
            fake.items[item_id] = item.__class__(**{**item.__dict__, "repository": "Gabrianoo/Owl-Mast"})
        fake.add_foreign_item("PVTI_X", 21, "Done", "OM-01.02", "someone/else")
        fake.add_foreign_item("PVTI_Y", 5, "Done", None, None)
        snap = take_snapshot(fake, REPO, "now")
        self.assertEqual(snap.by_id()[S].status, "Ready")
        self.assertEqual(snap.dropped_items, {"someone/else": 1, "?": 1})
        self.assertEqual(verify_mapping(snap)["counts"]["dropped_project_items"], {"someone/else": 1, "?": 1})
        self.assertEqual(snap.from_json(snap.to_json()).dropped_items, snap.dropped_items)

    def test_a_project_without_any_item_of_this_repository_refuses(self):
        fake = small_backlog()
        for item_id, item in list(fake.items.items()):
            fake.items[item_id] = item.__class__(**{**item.__dict__, "repository": "renamed/elsewhere"})
        with self.assertRaises(Refused) as ctx:
            take_snapshot(fake, REPO, "now")
        self.assertEqual(ctx.exception.code, "project-items-foreign")
        for item_id, item in list(fake.items.items()):
            fake.items[item_id] = item.__class__(**{**item.__dict__, "repository": None})  # drafts, or a transport that reports no repository: no evidence of a foreign Project
        snap = take_snapshot(fake, REPO, "now")
        self.assertEqual((snap.by_id()[S].item_id, snap.dropped_items), (None, {"?": len(fake.items)}))


class CorruptStateTests(unittest.TestCase):
    """Findings 7, 8 and 9: cancel-run and status survive one corrupt file; field values are validated."""

    def setUp(self):
        self.h = Harness(small_backlog(), allow='["OM-01.02", "OM-01.04"]', max_stories_per_run="2")

    def tearDown(self):
        self.h.close()

    def test_cancel_run_releases_the_readable_stories_and_reports_the_corrupt_one(self):
        self.h.claim()
        (self.h.store.story_path("OM-01.04")).write_text("{broken", encoding="utf-8")
        result = self.h.coordinator.cancel_run("stop", task_evidence={S: self.h.terminal(status="cancelled")})
        self.assertEqual([s["phase"] for s in result["cancelled"]], ["cancelled"])
        self.assertEqual([(a["story"], a["code"]) for a in result["awaiting_worker_termination"]], [("OM-01.04", "state-corrupt")])
        self.assertTrue(self.h.store.load_run().cancelled)
        self.assertEqual(len(markers(self.h.fake, 21, "release")), 1)

    def test_status_reports_the_corrupt_file_and_counts_the_rest(self):
        self.h.claim()
        (self.h.store.story_path("OM-01.04")).write_text("[]", encoding="utf-8")
        report = fresh(self.h).status()
        self.assertEqual(report["budgets"]["stories_claimed"], 1)
        self.assertEqual([u["story"] for u in report["unreadable_stories"]], ["OM-01.04"])
        self.assertEqual([s.get("error") for s in report["stories"]], [None, "state-corrupt"])

    def test_a_record_with_every_key_but_a_bad_phase_or_type_is_corrupt(self):
        self.h.claim()
        path = self.h.store.story_path(S)
        valid = json.loads(path.read_text(encoding="utf-8"))
        for mutation in ({"phase": "Reserved"}, {"phase": None}, {"phase": "done"}, {"issue": "21"}, {"authorizations": [{"status": "pending"}]}, {"claim": "x"}, {"repair_rounds": -1}):
            path.write_text(json.dumps({**valid, **mutation}), encoding="utf-8")
            with self.assertRaises(Refused, msg=str(mutation)) as ctx:
                Store(self.h.state_dir, "run-1").load_story(S)
            self.assertEqual((ctx.exception.code, ctx.exception.detail["path"]), ("state-corrupt", "OM-01.02.json"), mutation)
            stories, unreadable = Store(self.h.state_dir, "run-1").list_stories_tolerant()
            self.assertEqual((len(stories), [u["code"] for u in unreadable]), (0, ["state-corrupt"]))
        path.write_text(json.dumps(valid), encoding="utf-8")
        self.assertEqual(Store(self.h.state_dir, "run-1").load_story(S).phase, "claimed")


class RunIdAndDurabilityTests(unittest.TestCase):
    """Findings 11, 12 and 13: lowercase run ids without ``--``; new directories are durable."""

    def test_run_ids_are_lowercase_and_never_carry_a_double_dash(self):
        for bad in ("Run-1", "RUN", "run--1", "a--", "r-é"):
            with self.assertRaises(Refused) as ctx:
                validate_run_id(bad)
            self.assertEqual(ctx.exception.code, "run-id-invalid", bad)
        self.assertEqual(validate_run_id("run-20261108-e01.a_b"), "run-20261108-e01.a_b")
        with tempfile.TemporaryDirectory() as tmp:
            own = Path(tmp) / "Run-1"  # a copy of the run under another spelling on a case-insensitive filesystem is never "another run"
            (own / "stories").mkdir(parents=True)
            (own / "run.json").write_text("{}")
            (own / "stories" / "OM-01.02.json").write_text("{broken")
            self.assertEqual(Store(Path(tmp), "run-1").other_runs_with_active_stories(), {})

    def test_journal_creation_and_new_directories_fsync_their_parents(self):
        synced: list[Path] = []
        real = os.fsync

        def spy(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                synced.append(Path(os.readlink(f"/proc/self/fd/{fd}")).resolve())
            return real(fd)

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(os, "fsync", spy):
            store = Store(Path(tmp) / "state", "run-1")
            store.journal(None, "first", {})
            root = (Path(tmp) / "state" / "run-1").resolve()
            self.assertIn(Path(tmp).resolve(), synced)  # ``state`` entry
            self.assertIn((Path(tmp) / "state").resolve(), synced)  # ``run-1`` entry
            self.assertIn(root, synced)  # the journal's own entry
            synced.clear()
            store.journal(None, "second", {})
            self.assertEqual(synced, [])  # nothing new to make durable


class PolicyDigestAndBoundsTests(unittest.TestCase):
    """Findings 14 and 18: canonical digest (legacy raw digest still bound), bounded wall clock."""

    def test_cosmetic_edits_keep_the_digest_and_value_edits_change_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = load_policy(write_policy(Path(tmp), allow='["OM-01.02"]'))
            text = (Path(tmp) / "policy.toml").read_text()
            (Path(tmp) / "policy.toml").write_text("# a new comment\n\n" + text.replace("max_wall_clock_minutes = 240", "max_wall_clock_minutes   =   240   # same value"))
            cosmetic = load_policy(Path(tmp) / "policy.toml")
            self.assertEqual(cosmetic.digest, base.digest)
            self.assertNotEqual(cosmetic.raw_digest, base.raw_digest)
            self.assertEqual(base.digest, canonical_digest(base))
            changed = load_policy(write_policy(Path(tmp), allow='["OM-01.02"]', max_wall_clock_minutes="241"))
            self.assertNotEqual(changed.digest, base.digest)

    def test_a_run_bound_to_the_legacy_raw_digest_is_not_drift_and_an_edited_policy_is(self):
        h = Harness(small_backlog())
        try:
            h.claim()
            text = Path(h.tmpdir.name, "policy.toml").read_text()
            (Path(h.tmpdir.name) / "cosmetic.toml").write_text("# cosmetic\n" + text)
            cosmetic = load_policy(Path(h.tmpdir.name) / "cosmetic.toml")
            self.assertIsNone(Coordinator(h.fake, cosmetic, Store(h.state_dir, "run-1"), live=True).status()["stop"])  # a canonical-digest run: cosmetic edits strand nothing
            run_path = h.store.run_path
            raw = json.loads(run_path.read_text())
            raw["policy_digest"] = h.policy.raw_digest  # LABELLED MUTATION: what a run created before the canonical digest recorded
            run_path.write_text(json.dumps(raw))
            self.assertIsNone(fresh(h).status()["stop"])  # bound to exactly these bytes, as before
            self.assertEqual(fresh(h).record_head(S, h.sha, h.terminal()).phase, "implemented")
            self.assertEqual(Coordinator(h.fake, cosmetic, Store(h.state_dir, "run-1"), live=True).status()["stop"], "policy-drift")  # a legacy raw-bytes binding gets no cosmetic tolerance: nothing is rewritten or guessed
            drifted = load_policy(write_policy(Path(h.tmpdir.name), allow='["OM-01.02"]', max_delegated_tasks="7"))
            self.assertEqual(Coordinator(h.fake, drifted, Store(h.state_dir, "run-1"), live=True).status()["stop"], "policy-drift")
        finally:
            h.close()

    def test_wall_clock_and_timeouts_have_ceilings(self):
        with tempfile.TemporaryDirectory() as tmp:
            for key, value, bound in (("max_wall_clock_minutes", str(10**13), "1..10080"), ("timeout_minutes", "100000", "1..1440"), ("timeout_seconds", "1000000", "1..86400"), ("max_stories_per_run", "1001", "1..1000"), ("max_delegated_tasks", "10001", "1..10000")):
                with self.assertRaises(PolicyError) as ctx:
                    load_policy(write_policy(Path(tmp), **{key: value}))
                self.assertIn(f"{key} must be within {bound}", str(ctx.exception))


class TransportPaginationAndPinnedQueriesTests(unittest.TestCase):
    """Findings 16, 17, 22, 23, 24 and body finding 1: nested connections paginate, shapes are guarded,
    the selections the fail-closed reads depend on are pinned, HTTP 403 rate limits are outages."""

    def setUp(self):
        self.t = GhCliTransport("gabrianoo", "owl-mast", "gabrianoo", 2)
        self.t.live = False
        self.queries: list[str] = []

    def scripted(self, pages):
        """Serve ``pages`` in order (each a response dict or JSON text), recording the queries."""
        it = iter(pages)
        self.queries = []

        def run(args, stdin=None):
            self.queries.append(args[3] if len(args) > 3 else " ".join(args))
            payload = next(it)
            return payload if isinstance(payload, str) else json.dumps(payload)

        self.t._run = run

    def test_issue_labels_paginate_and_a_cursorless_or_endless_page_refuses(self):
        node = {"number": 1, "id": "I_1", "title": "t", "state": "OPEN", "stateReason": None, "updatedAt": "u", "closedAt": None, "body": "", "parent": None,
                "labels": {"pageInfo": {"hasNextPage": True, "endCursor": "c1"}, "nodes": [{"name": "story"}]}}
        self.scripted([{"data": {"repository": {"issue": node}}}, {"data": {"repository": {"issue": {"labels": {"pageInfo": {"hasNextPage": False}, "nodes": [{"name": "engineering-automation"}]}}}}}])
        self.assertEqual(self.t.get_issue(1).labels, ("story", "engineering-automation"))
        self.assertIn('labels(first:50, after:"c1")', self.queries[1])
        self.assertIn("labels(first:50){pageInfo{hasNextPage endCursor}", self.queries[0])  # the selection the refusal depends on is in the live query
        self.scripted([{"data": {"repository": {"issue": {**node, "labels": {"pageInfo": {"hasNextPage": True}, "nodes": []}}}}}])
        with self.assertRaises(TransportError) as ctx:
            self.t.get_issue(1)
        self.assertIn("truncated", str(ctx.exception))
        endless = {"data": {"repository": {"issue": {"labels": {"pageInfo": {"hasNextPage": True, "endCursor": "again"}, "nodes": []}}}}}
        self.scripted([{"data": {"repository": {"issue": node}}}] + [endless] * 60)
        with self.assertRaises(TransportError) as ctx:
            self.t.get_issue(1)
        self.assertIn("runaway", str(ctx.exception))

    def test_field_values_and_project_fields_paginate_and_project_info_shapes_are_guarded(self):
        item = {"id": "PVTI_1", "updatedAt": "u", "content": {"number": 21, "repository": {"nameWithOwner": REPO}},
                "fieldValues": {"pageInfo": {"hasNextPage": True, "endCursor": "v1"}, "nodes": [{"name": "Ready", "field": {"name": "Status"}}]}}
        self.scripted([{"data": {"node": item}}, {"data": {"node": {"fieldValues": {"pageInfo": {"hasNextPage": False}, "nodes": [{"text": "OM-01.02", "field": {"name": "Stable ID"}}]}}}}])
        got = self.t.get_project_item("PVTI_1")
        self.assertEqual((got.status, got.stable_id, got.repository), ("Ready", "OM-01.02", REPO))
        self.assertIn('fieldValues(first:30, after:"v1")', self.queries[1])
        self.assertIn("fieldValues(first:30){ pageInfo{hasNextPage endCursor}", self.queries[0])
        self.assertIn("repository{ nameWithOwner }", self.queries[0])  # finding 24: the repository filter depends on this selection
        fields1 = {"pageInfo": {"hasNextPage": True, "endCursor": "f1"}, "nodes": [{"id": "F0", "name": "Other", "options": []}]}
        fields2 = {"pageInfo": {"hasNextPage": False}, "nodes": [{"id": "F", "name": "Status", "options": [{"id": "o1", "name": "Ready"}]}]}
        self.scripted([{"data": {"repositoryOwner": {"projectV2": {"id": "P", "fields": fields1}}}}, {"data": {"repositoryOwner": {"projectV2": {"fields": fields2}}}}])
        self.assertEqual(self.t.project_info().status_options, {"Ready": "o1"})
        self.assertIn('fields(first:50, after:"f1")', self.queries[1])
        self.assertIn("fields(first:50){ pageInfo{hasNextPage endCursor}", self.queries[0])
        for broken in ({"id": "P", "fields": {"pageInfo": {"hasNextPage": False}, "nodes": [{"id": "F", "name": "Status", "options": "nope"}]}},
                       {"fields": {"pageInfo": {"hasNextPage": False}, "nodes": [{"id": "F", "name": "Status", "options": [{"name": "Ready"}]}]}}):
            self.t._project = None
            self.scripted([{"data": {"repositoryOwner": {"projectV2": broken}}}])
            with self.assertRaises(TransportError, msg=str(broken)):
                self.t.project_info()

    def test_items_query_requests_page_info_for_every_nested_connection(self):
        self.scripted([{"data": {"repositoryOwner": {"projectV2": {"items": {"pageInfo": {"hasNextPage": False}, "nodes": []}}}}}])
        self.assertEqual(self.t.list_project_items(), [])
        self.assertIn("fieldValues(first:30){ pageInfo{hasNextPage endCursor}", self.queries[0])
        self.assertIn("repository{ nameWithOwner }", self.queries[0])
        self.scripted([{"data": {"repository": {"issues": {"pageInfo": {"hasNextPage": False}, "nodes": []}}}}])
        self.assertEqual(self.t.list_issues(), [])
        self.assertIn("labels(first:50){pageInfo{hasNextPage endCursor}", self.queries[0])

    def test_secondary_rate_limit_on_rest_is_an_outage(self):
        for text in ("HTTP 403: You have exceeded a secondary rate limit. Please wait a few minutes before you try again.", "HTTP 403: API rate limit exceeded for user ID 1", "HTTP 429: too many requests", "abuse detection mechanism triggered"):
            self.assertIsInstance(classify(1, text), Outage, text)
        self.assertIsInstance(classify(1, "HTTP 403: Resource not accessible by personal access token"), PermissionDenied)

    def test_check_permissions_query_is_pinned_to_repository_owner(self):
        argvs = []

        def runner(argv, cwd, timeout):
            argvs.append(argv)
            if argv[:3] == ["gh", "api", "graphql"]:
                return subprocess.CompletedProcess(argv, 0, json.dumps({"data": {"repositoryOwner": {"projectV2": {"id": "P", "title": "t", "viewerCanUpdate": False}}}}), "")
            return subprocess.CompletedProcess(argv, 0, "x-oauth-scopes: repo, read:project\r\n\r\n" + json.dumps({"permissions": {"push": True, "admin": False}}), "")

        report = check_permissions("gabrianoo", "owl-mast", "some-org", 2, runner)
        query = next(a for a in argvs if a[:3] == ["gh", "api", "graphql"])[-1]
        self.assertIn('repositoryOwner(login:"some-org")', query)
        self.assertNotIn("user(login", query)
        self.assertTrue(report["basic_access"])


class ReviewerWorktreeAndIsolationTests(unittest.TestCase):
    """Body finding 2 and finding 26: the reviewer names its own checkout; isolation is verified and tested."""

    def setUp(self):
        self.h = Harness(small_backlog())

    def tearDown(self):
        self.h.close()

    def test_review_receipt_needs_its_own_verified_worktree(self):
        self.h.claim()
        self.h.checks()
        self.h.coordinator.authorize_review(S, self.h.sha)
        with self.assertRaises(Refused) as ctx:
            self.h.coordinator.bind_receipt(S, REVIEWER, worktree_check=ok_worktree)
        self.assertEqual(ctx.exception.code, "reviewer-worktree-required")
        with self.assertRaises(Refused) as ctx:
            self.h.coordinator.bind_receipt(S, REVIEWER, str(self.h.worktree), "t3/om-01-02", ok_worktree)
        self.assertEqual(ctx.exception.code, "reviewer-worktree-shared")
        with self.assertRaises(Refused) as ctx:  # nested inside the implementer's checkout is not independent either
            self.h.coordinator.bind_receipt(S, REVIEWER, str(self.h.worktree / "review"), "t3/om-01-02", ok_worktree)
        self.assertEqual(ctx.exception.code, "reviewer-worktree-shared")
        with self.assertRaises(Refused) as ctx:
            self.h.coordinator.bind_receipt(S, REVIEWER, REVIEW_WORKTREE, REVIEW_BRANCH, lambda p, b: (False, "not a checkout"))
        self.assertEqual(ctx.exception.code, "worktree-mismatch")
        self.assertIsNone(self.h.store.load_story(S).active_task)
        state = self.h.coordinator.bind_receipt(S, REVIEWER, REVIEW_WORKTREE, REVIEW_BRANCH, ok_worktree)
        self.assertEqual((state.phase, state.reviewer_receipts[-1]["worktree"], state.reviewer_receipts[-1]["branch"]), ("review-requested", REVIEW_WORKTREE, REVIEW_BRANCH))
        self.assertIn("head_at_bind", state.reviewer_receipts[-1])  # observed for the record; the reviewer checks the SHA out itself

    def test_non_isolated_reviewer_receipts_are_refused_by_the_validator_and_by_bind(self):
        target = Target("codex", "gpt-6-astra", {"reasoningEffort": "high"}, "worktree")
        for bad in ({**REVIEWER, "isolation": "shared"}, {k: v for k, v in REVIEWER.items() if k != "isolation"}):
            with self.assertRaises(ReceiptInvalid):
                validate_receipt(bad, target, "reviewer")
        self.h.claim()
        self.h.checks()
        self.h.coordinator.authorize_review(S, self.h.sha)
        with self.assertRaises(ReceiptInvalid):
            self.h.coordinator.bind_receipt(S, {**REVIEWER, "isolation": "shared"}, REVIEW_WORKTREE, REVIEW_BRANCH, ok_worktree)
        self.assertEqual(self.h.store.load_story(S).phase, "review-authorized")


class LateReceiptUnderDriftTests(unittest.TestCase):
    """Body finding 3: a late receipt under policy drift validates against the recorded targets."""

    def test_drifted_reviewer_target_still_binds_the_late_receipt_for_cleanup(self):
        h = Harness(small_backlog())
        try:
            h.claim()
            h.checks()
            h.coordinator.authorize_review(S, h.sha)
            text = Path(h.tmpdir.name, "policy.toml").read_text().replace('model = "gpt-6-astra"', 'model = "gpt-7-nova"')
            (Path(h.tmpdir.name) / "drifted.toml").write_text(text)
            drifted = load_policy(Path(h.tmpdir.name) / "drifted.toml")
            c = Coordinator(h.fake, drifted, Store(h.state_dir, "run-1"), live=True)
            self.assertEqual(c.status()["stop"], "policy-drift")
            with self.assertRaises(Refused) as ctx:
                c.bind_receipt(S, REVIEWER, REVIEW_WORKTREE, REVIEW_BRANCH, ok_worktree)  # the receipt names the model the task was launched with
            self.assertEqual((ctx.exception.code, ctx.exception.detail["bound_for_cleanup"]), ("policy-drift", True))
            state = h.store.load_story(S)
            self.assertEqual((state.active_task["taskId"], state.active_task["cleanup_only"]), ("task-review-1", "policy-drift"))
            self.assertEqual(c.record_task_terminal(S, h.terminal(status="cancelled")).active_task, None)
            self.assertEqual(c.cancel(S, "policy changed").phase, "cancelled")
        finally:
            h.close()


class GitFailureTests(unittest.TestCase):
    """Finding 21: the real ``git_clean`` reports a failure as ``None`` and the gate refuses without invalidating."""

    def test_real_git_clean_returns_none_when_git_cannot_answer(self):
        with tempfile.TemporaryDirectory() as tmp:
            gone = Path(tmp) / "gone"
            self.assertIsNone(git_clean(str(gone))[0])
        with mock.patch.object(coordinator_module.subprocess, "run", return_value=subprocess.CompletedProcess(["git"], 128, "", "fatal: not a git repository")):
            clean, why = git_clean("/anywhere")
            self.assertEqual((clean, "not a git repository" in why), (None, True))
        with mock.patch.object(coordinator_module.subprocess, "run", side_effect=subprocess.TimeoutExpired(["git"], 60)):
            self.assertIsNone(git_clean("/anywhere")[0])

    def test_gate_end_to_end_over_a_timing_out_git_status(self):
        h = Harness(small_backlog())
        try:
            h.to_review_approved()
            real_run = coordinator_module.subprocess.run

            def flaky(args, **kwargs):
                if "status" in args:
                    raise subprocess.TimeoutExpired(args, 60)
                return real_run(args, **kwargs)

            with mock.patch.object(coordinator_module.subprocess, "run", flaky):
                with self.assertRaises(Refused) as ctx:
                    h.coordinator.record_review(S, h.sha, "approved", "again", None)
            self.assertEqual(ctx.exception.code, "worktree-unreadable")
            state = h.store.load_story(S)
            self.assertEqual((state.phase, state.approved_sha), ("review-approved", h.sha))
            self.assertEqual(events(h, "unreported-worktree-change"), [])
        finally:
            h.close()


class CliArgumentContractTests(unittest.TestCase):
    """Finding 20: argument errors are JSON with exit 3; exit 2 stays the negative-result code."""

    def test_argument_errors_are_input_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            policy = str(write_policy(Path(tmp), allow='["OM-01.02"]'))
            for argv in (("--policy", policy, "--run-id", "r1", "cancel", "OM-01.02"), ("--policy", policy, "no-such-command"), ("--policy", policy, "--live", "probe-write", "--issue", "x")):
                code, out = run_cli(*argv)
                self.assertEqual((code, out["error"]["code"]), (3, "input-invalid"), argv)
                self.assertIn("usage", out["error"]["usage"])
            with self.assertRaises(SystemExit) as ctx:
                run_cli("--help")
            self.assertEqual(ctx.exception.code, 0)


class HistoricalFixtureReplayTests(unittest.TestCase):
    """Finding 15: the historical pre-recovery state replays in CI from a committed, scrubbed copy
    (``/home/<operator>`` relocated, pickle converted to ``transport.json``; no other edit)."""

    FIXTURE = FIXTURES / "historical-eng01-trusted-20261106"
    RUN = "eng01-trusted-20261106"

    def test_supplied_evidence_reconciles_the_committed_historical_copy(self):
        from automation.tests import lifecycle_smoke as smoke

        before = self.tree_digest(self.FIXTURE)
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "copy"
            shutil.copytree(self.FIXTURE, copy)
            policy_copy = copy / "policy.toml"  # LABELLED EDIT of the temporary copy only: the backup predates targets.reviewer.isolation; the digest change is policy drift (a stop), and reconcile/cancel are cleanup
            policy_copy.write_text(policy_copy.read_text(encoding="utf-8").replace('model = "gpt-6-astra"\n', 'model = "gpt-6-astra"\nisolation = "worktree"\n', 1), encoding="utf-8")
            supplied = json.loads((copy / "supplied-original-coordinator-evidence.json").read_text())
            dispatch = json.loads((copy / "repair-dispatch.json").read_text())
            rec = {"taskId": supplied["taskId"], "runId": supplied["runId"], "providerInstanceId": supplied["providerInstanceId"], "model": supplied["model"], "options": supplied["options"], "isolation": "worktree",
                   "dispatch": {"runId": dispatch["runId"], "messageId": dispatch["messageId"]}, "startedAt": supplied["startedAt"], "completedAt": supplied["completedAt"]}
            (copy / "r.json").write_text(json.dumps(rec))
            (copy / "e.json").write_text(json.dumps(supplied["task_status_snapshot"]))
            argv = ["--dir", str(copy), "--run-id", self.RUN, "reconcile", "--authorization", supplied["historical_authorization"], "--receipt", str(copy / "r.json"), "--task-evidence", str(copy / "e.json"),
                    "--reason", "repair run ordinal5 completed under the retained owner", "--provenance", supplied["provenance"], "--source", "real"]
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = smoke.main(argv)
            out = json.loads(buf.getvalue())
            self.assertEqual(code, 0, out)
            self.assertEqual((out["phase"], out["authorization"]["status"], out["authorization"]["run_id"]), ("repair-authorized", "consumed", supplied["runId"]))
            self.assertTrue(list((copy / "runs" / self.RUN / "stories").glob("*.bak-*")))
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(smoke.main(argv), 0)  # idempotent
            status = Store(copy / "runs", self.RUN).load_run()
            self.assertTrue(status.cancelled)
            buf = io.StringIO()
            with redirect_stdout(buf):  # the drifted policy still allows cleanup: the story can be released
                self.assertEqual(smoke.main(["--dir", str(copy), "--run-id", self.RUN, "cancel", "--reason", "cleanup after reconciliation", "--source", "real"]), 0)
            self.assertEqual(json.loads(buf.getvalue())["phase"], "cancelled")
        # the committed fixture itself is untouched by the replay (every file, byte for byte)
        self.assertEqual(self.tree_digest(self.FIXTURE), before)
        self.assertEqual(json.loads((self.FIXTURE / "runs" / self.RUN / "stories" / "OM-99.01.json").read_text())["authorizations"][2]["status"], "revoked")
        self.assertFalse((self.FIXTURE / "fixture-transport.pickle").exists())

    @staticmethod
    def tree_digest(root: Path) -> dict[str, str]:
        import hashlib

        return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*")) if p.is_file()}


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
