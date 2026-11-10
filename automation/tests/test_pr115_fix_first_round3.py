"""Regressions for the five "fix first" findings of the PR #115 recheck review at 07c363c (review
5840034191, 2026-11-10): ``dismiss-claim`` needs the run's current activation and refuses a live
claim, a re-verified ``claim-unverifiable`` conflict is restored only through the revision gate,
earliest-wins orders edited claims by their edit and re-reads once before cancelling, a legacy
split reservation without ``race_settled`` is settled, and the raw-bytes digest is accepted only
for a run that already exists under it."""

import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from automation.tests.fake_transport import FakeTransport, small_backlog
from automation.tests.support import IMPLEMENTER, Harness, ok_worktree, write_policy
from automation.tests import test_activation as activation_tests
from automation.tests import test_pr115_recheck_findings as recheck
from automation.tests import test_pr115_review_findings as prior

LiveHarness, activation_text = activation_tests.LiveHarness, activation_tests.activation_text
arm_failure_after_claim, events, fresh, markers = prior.arm_failure_after_claim, prior.events, prior.fresh, prior.markers
two_story_harness = recheck.two_story_harness
from automation.unattended import cli
from automation.unattended.activation import load_activation
from automation.unattended.coordinator import Coordinator, _claim_order
from automation.unattended.errors import Conflict, Outage, Refused, UnattendedError
from automation.unattended.github import Comment, render_marker
from automation.unattended.state import Store

S = "OM-01.02"
OTHER = "OM-01.04"  # issue 23
EARLY = "2026-11-06T12:59:00Z"
NOW = "2026-11-06T13:05:00Z"  # minutes after the fake transport's claims: a claim is younger than the wall clock


def foreign_claim(run="run-x", story=OTHER, created_at=EARLY, updated_at=None, author="stranger", comment_id=9, **extra) -> Comment:
    return Comment(comment_id, render_marker(kind="claim", run=run, story=story, op="claim", **extra) + "\nelsewhere", author, created_at, updated_at)


class DismissClaimGateTests(unittest.TestCase):
    """Fix 1: ``dismiss-claim`` is an owner action gated by the run's current activation and never dismisses a live claim."""

    def test_on_the_live_transport_it_needs_the_current_activation(self):
        lh = LiveHarness()
        try:
            lh.h.fake.add_issue(small_backlog().issues[23], "Ready", OTHER)
            c = lh.coordinator()  # creates the run under the activation
            stray = lh.h.fake.add_comment(21, render_marker(kind="claim", run="run-x", story=S, op="claim") + "\nforged", "stranger")
            with self.assertRaises(Refused) as ctx:  # no activation presented: cleanup would work, a dismissal does not
                lh.coordinator(activation=None).dismiss_claim(21, stray.comment_id, "owner")
            self.assertEqual(ctx.exception.code, "activation-required")
            self.assertIn("advancing on the live transport needs a current activation", str(ctx.exception))  # the advancing gate itself, not only the run stop
            lh.path.write_text(activation_text(lh.h.policy, run_id="run-other"), encoding="utf-8")  # a different document
            with self.assertRaises(Refused) as ctx:
                lh.coordinator(activation=load_activation(lh.path)).dismiss_claim(21, stray.comment_id, "owner")
            self.assertEqual(ctx.exception.code, "activation-mismatch")
            lh.path.write_text(activation_text(lh.h.policy), encoding="utf-8")
            lh.clock[0] = "2026-11-07T14:00:01Z"  # expired: a durable stop
            with self.assertRaises(UnattendedError) as ctx:
                c.dismiss_claim(21, stray.comment_id, "owner")
            self.assertEqual(ctx.exception.code, "activation-expired")
            self.assertEqual(markers(lh.h.fake, 21, "dismiss"), [])
            self.assertEqual([e for e in Store(lh.h.state_dir, "run-live").read_journal() if e["event"].startswith("foreign-claim-dismiss")], [])
        finally:
            lh.close()

    def test_a_claim_a_run_under_this_state_directory_still_owns_is_never_dismissed(self):
        h = two_story_harness()
        try:
            other = Coordinator(h.fake, h.policy, Store(h.state_dir, "run-b"), live=True)
            other.reserve(OTHER, h.snapshot, "c5d9d2e")  # B holds OM-01.04 under the same state directory
            theirs = markers(h.fake, 23, "claim")[0]
            with self.assertRaises(Refused) as ctx:
                h.coordinator.dismiss_claim(23, theirs.comment_id, "I want the slot", force=True)
            self.assertEqual(ctx.exception.code, "dismiss-target-live")
            self.assertEqual((ctx.exception.detail["evidence"]["local_run"]["run_id"], ctx.exception.detail["evidence"]["local_run"]["owns_story"]), ("run-b", True))
            with self.assertRaises(Refused) as ctx:  # admission still blocked: both cannot end reserved
                h.reserve()
            self.assertEqual(ctx.exception.code, "run-concurrent")
            b = Store(h.state_dir, "run-b").load_story(OTHER)
            b.phase, b.blocked = "conflict", {"reason": "x", "at": NOW, "from_phase": "reserved", "conflict": True, "race_unsettled": True}  # LABELLED MUTATION: B's claim was unverifiable; resume may restore it
            Store(h.state_dir, "run-b").save_story(b)
            with self.assertRaises(Refused) as ctx:
                h.coordinator.dismiss_claim(23, theirs.comment_id, "it is in conflict", force=True)
            self.assertEqual((ctx.exception.code, ctx.exception.detail["evidence"]["local_run"]["phase"]), ("dismiss-target-live", "conflict"))
            b.phase, b.blocked = "cancelled", {"reason": "x", "at": NOW, "cancelled": True}
            Store(h.state_dir, "run-b").save_story(b)
            report = h.coordinator.dismiss_claim(23, theirs.comment_id, "B is done")  # local proof that B finished with the story: no --force needed
            self.assertEqual((report["evidence"]["local_run"]["owns_story"], report["evidence"]["local_run"]["finished"], report["evidence"]["possibly_live"], report["evidence"]["forced"]), (False, True, False, False))
        finally:
            h.close()

    def test_a_claim_younger_than_the_wall_clock_needs_force_and_the_evidence_is_journaled(self):
        h = two_story_harness()
        try:
            young = Coordinator(h.fake, h.policy, Store(h.state_dir, "run-1"), now=lambda: NOW, live=True)
            stray = h.fake.add_comment(23, render_marker(kind="claim", run="run-x", story=OTHER, op="claim") + "\nanother machine", "stranger")
            with self.assertRaises(Refused) as ctx:
                young.dismiss_claim(23, stray.comment_id, "looks stale")
            self.assertEqual(ctx.exception.code, "dismiss-target-live")
            evidence = ctx.exception.detail["evidence"]
            self.assertEqual((evidence["local_run"], evidence["possibly_live"], evidence["wall_clock_minutes"]), (None, True, 240))
            self.assertEqual(markers(h.fake, 23, "dismiss"), [])
            report = young.dismiss_claim(23, stray.comment_id, "machine x was decommissioned at 13:01, no run directory, no activity", force=True)
            self.assertTrue(report["evidence"]["forced"])
            self.assertEqual(events(h, "foreign-claim-dismissed")[0]["detail"]["evidence"]["forced"], True)
            self.assertEqual(h.coordinator.dismiss_claim(23, stray.comment_id, "again", force=True)["dismissal_comment_id"], report["dismissal_comment_id"])  # idempotent (the attestation is still needed: age proves nothing)
            self.assertEqual([e["detail"]["posted"] for e in events(h, "foreign-claim-dismissed")], [True, False])
            self.assertEqual(h.reserve().phase, "reserved")
        finally:
            h.close()

    def test_a_claim_older_than_the_wall_clock_still_needs_force_or_local_proof(self):
        h = two_story_harness()
        try:
            young = Coordinator(h.fake, h.policy, Store(h.state_dir, "run-1"), now=lambda: NOW, live=True)
            stray = h.fake.add_comment(23, render_marker(kind="claim", run="run-x", story=OTHER, op="claim") + "\nold", "stranger")  # 2026-11-06, days before now
            stopped = Coordinator(h.fake, h.policy, Store(h.state_dir, "run-1"), now=lambda: "2030-01-01T00:00:00Z", live=True)  # past the wall clock: no owner action through this run
            with self.assertRaises(UnattendedError) as ctx:
                stopped.dismiss_claim(23, stray.comment_id, "abandoned run")
            self.assertEqual(ctx.exception.code, "wall-clock-exceeded")
            edited = h.fake.add_comment(21, render_marker(kind="claim", run="run-y", story=S, op="claim") + "\nold but edited", "stranger")
            h.fake.comments[21][-1] = Comment(edited.comment_id, edited.body, edited.author, edited.created_at, "2026-11-06T13:04:00Z")
            with self.assertRaises(Refused) as ctx:  # an edited claim is as young as its edit
                young.dismiss_claim(21, edited.comment_id, "old")
            self.assertEqual((ctx.exception.code, ctx.exception.detail["evidence"]["claim_age_minutes"]), ("dismiss-target-live", 1))
            with self.assertRaises(Refused) as ctx:  # days old, no run of its id here: its coordinator (another machine, past its wall clock, task still running) may still own the story
                h.coordinator.dismiss_claim(23, stray.comment_id, "abandoned run")
            self.assertEqual(ctx.exception.code, "dismiss-target-live")
            self.assertEqual((ctx.exception.detail["evidence"]["local_run"], ctx.exception.detail["evidence"]["possibly_live"]), (None, True))
            self.assertGreater(ctx.exception.detail["evidence"]["claim_age_minutes"], 240)
            self.assertIn("wall clock still owns its story", str(ctx.exception))
            self.assertEqual(markers(h.fake, 23, "dismiss"), [])
            report = h.coordinator.dismiss_claim(23, stray.comment_id, "machine x was decommissioned, no run directory, no activity", force=True)
            self.assertEqual((report["evidence"]["possibly_live"], report["evidence"]["forced"]), (True, True))
        finally:
            h.close()

    def test_the_target_must_be_an_allowlisted_story_on_its_own_issue(self):
        h = two_story_harness()
        try:
            for number, story in ((24, "OM-02.01"), (23, S), (23, "")):
                body = render_marker(kind="claim", run="run-x", story=story, op="claim") if story else "<!-- unattended kind=claim run=run-x op=claim -->"
                stray = h.fake.add_comment(number, body + "\nmisplaced", "stranger")
                with self.assertRaises(Refused) as ctx:
                    h.coordinator.dismiss_claim(number, stray.comment_id, "owner")
                self.assertEqual(ctx.exception.code, "dismiss-target-invalid", (number, story))
            self.assertEqual(events(h, "foreign-claim-dismiss-intent"), [])
        finally:
            h.close()

    def test_the_intent_is_journaled_before_the_post_and_a_failed_post_leaves_no_dismissal(self):
        h = two_story_harness()
        try:
            stray = h.fake.add_comment(23, render_marker(kind="claim", run="run-x", story=OTHER, op="claim") + "\nold", "stranger")
            h.fake.fail_once["post_comment"] = Outage("503")
            with self.assertRaises(Outage):
                h.coordinator.dismiss_claim(23, stray.comment_id, "owner", force=True)
            self.assertEqual((len(events(h, "foreign-claim-dismiss-intent")), events(h, "foreign-claim-dismissed")), (1, []))
            self.assertIn("kind=dismiss", events(h, "foreign-claim-dismiss-intent")[0]["detail"]["body"])
            report = h.coordinator.dismiss_claim(23, stray.comment_id, "owner @someone\nsee `this`", force=True)
            body = h.fake.comments[23][-1].body
            self.assertEqual((report["dismissal_comment_id"], "@" in body, "\n" in body.split("-->", 1)[1].strip()), (h.fake.comments[23][-1].comment_id, False, False))
            self.assertTrue(events(h, "foreign-claim-dismissed")[0]["detail"]["posted"])
            buf = io.StringIO()
            (Path(h.tmpdir.name) / "p").mkdir()
            policy = str(write_policy(Path(h.tmpdir.name) / "p", allow='["OM-01.02", "OM-01.04"]', max_stories_per_run="2"))
            with mock.patch.object(cli, "GhCliTransport", lambda *a, **k: h.fake), redirect_stdout(buf):
                code = cli.main(["--policy", policy, "--state-dir", str(h.state_dir), "--run-id", "run-1", "--live", "dismiss-claim", "--issue", "23", "--comment-id", str(stray.comment_id), "--reason", "owner", "--force"])
            self.assertEqual((code, json.loads(buf.getvalue())["evidence"]["forced"]), (0, True))
        finally:
            h.close()


class ReverifiedConflictRevisionGateTests(unittest.TestCase):
    """Fix 2: a re-verified ``claim-unverifiable`` conflict is restored only through the revision gate, and only to ``reserved``."""

    def unverifiable(self) -> Harness:
        h = Harness(small_backlog())
        arm_failure_after_claim(h, reads_after_post=2, hide_ours=True)
        with self.assertRaises(Conflict):
            h.reserve()
        h.fake.list_comments = FakeTransport.list_comments.__get__(h.fake)  # the claim is readable again
        return h

    def test_changed_revisions_cancel_the_reverified_claim_and_release_it(self):
        h = self.unverifiable()
        try:
            h.fake.set_status_externally(21, "In progress")  # the owner moved the story while the claim was unverifiable
            resumed = fresh(h).resume(S, ok_worktree)
            state = h.store.load_story(S)
            self.assertEqual((resumed.phase, state.phase, state.blocked["cancelled"]), ("cancelled", "cancelled", True))
            self.assertTrue(events(h, "resume-claim-abandoned"))
            self.assertEqual(events(h, "claim-reverified"), [])
            self.assertEqual(len([c for c in markers(h.fake, 21, "release") if "run=run-1" in c.body]), 1)
            with self.assertRaises(Refused):
                fresh(h).bind_receipt(S, IMPLEMENTER, str(h.worktree), "t3/om-01-02", ok_worktree)
        finally:
            h.close()

    def test_a_from_phase_other_than_reserved_is_withheld(self):
        h = self.unverifiable()
        try:
            state = h.store.load_story(S)
            state.blocked["from_phase"] = "claimed"  # LABELLED MUTATION: a record no coordinator writes
            h.store.save_story(state)
            resumed = fresh(h).resume(S, ok_worktree)
            self.assertEqual((resumed.phase, resumed.claim["race_settled"]), ("conflict", False))
            self.assertTrue(any("restored only to reserved" in e["detail"]["reason"] for e in events(h, "reconciliation-withheld")))
        finally:
            h.close()


class ClaimOrderTests(unittest.TestCase):
    """Fix 3: earliest-wins orders an edited claim by its edit, fails closed on unparseable times and re-reads once before cancelling."""

    def edited_after_ours(self, h: Harness, created_at: str = EARLY) -> None:
        """Another coordinator's claim on OM-01.04 lands during our post, created at ``created_at`` and edited after ours."""
        recheck.CrossStoryClaimRaceTests.interleave(recheck.CrossStoryClaimRaceTests(), h, created_at)
        original = h.fake.post_comment

        def post(number, body):
            posted = original(number, body)
            h.fake.comments[23][:] = [Comment(c.comment_id, c.body, c.author, c.created_at, "2026-11-06T13:00:59Z") if c.comment_id == 9 else c for c in h.fake.comments[23]]
            return posted

        h.fake.post_comment = post

    def test_an_edited_earlier_claim_still_wins_and_the_loss_names_the_edit(self):
        """Fail closed: an edit to a legitimate earlier claim must not let two coordinators win; a backdated edit costs us our slot and the owner clears it."""
        h = two_story_harness()
        try:
            self.edited_after_ours(h)
            with self.assertRaises(Conflict) as ctx:
                h.reserve()
            self.assertEqual(ctx.exception.code, "claim-active-elsewhere")
            self.assertIn("edited 2026-11-06T13:00:59Z", str(ctx.exception))
            self.assertIn("dismiss-claim", str(ctx.exception))
            self.assertEqual(h.store.load_story(S).phase, "cancelled")
        finally:
            h.close()

    def test_an_edited_later_claim_loses_and_our_own_edited_claim_loses(self):
        h = two_story_harness()
        try:
            self.edited_after_ours(h, created_at="2026-11-06T13:00:30Z")  # created after ours lands (ours is 13:00:1x)
            state = h.reserve()
            self.assertEqual((state.phase, state.claim["race_settled"]), ("reserved", True))
        finally:
            h.close()
        h = two_story_harness()
        try:
            recheck.CrossStoryClaimRaceTests.interleave(recheck.CrossStoryClaimRaceTests(), h, "2026-11-06T13:00:30Z")
            original = h.fake.post_comment

            def post(number, body):
                posted = original(number, body)
                h.fake.comments[21][:] = [Comment(c.comment_id, c.body, c.author, c.created_at, "2026-11-06T13:00:59Z") if c.comment_id == posted.comment_id else c for c in h.fake.comments[21]]  # someone edited OUR claim
                return posted

            h.fake.post_comment = post
            with self.assertRaises(Conflict) as ctx:
                h.reserve()
            self.assertEqual(ctx.exception.code, "claim-active-elsewhere")
        finally:
            h.close()

    def test_unparseable_timestamps_fail_closed(self):
        self.assertLess(_claim_order({"comment_id": 5, "created_at": "yesterday"}), _claim_order({"comment_id": 1, "created_at": EARLY}))
        self.assertGreater(_claim_order({"comment_id": 5, "created_at": None}, ours=True), _claim_order({"comment_id": 1, "created_at": "2999-01-01T00:00:00Z"}))
        self.assertEqual(_claim_order({"comment_id": 5, "created_at": EARLY, "updated_at": "2999-01-01T00:00:00Z"}), _claim_order({"comment_id": 5, "created_at": EARLY}))  # a foreign edit does not move it
        self.assertGreater(_claim_order({"comment_id": 5, "created_at": EARLY, "updated_at": "2999-01-01T00:00:00Z"}, ours=True), _claim_order({"comment_id": 5, "created_at": EARLY}, ours=True))
        h = two_story_harness()
        try:
            recheck.CrossStoryClaimRaceTests.interleave(recheck.CrossStoryClaimRaceTests(), h, "not a time")  # lands after our post: only the settle sees it
            with self.assertRaises(Conflict) as ctx:
                h.reserve()
            self.assertEqual(ctx.exception.code, "claim-active-elsewhere")
        finally:
            h.close()

    def test_an_earlier_claim_released_between_the_two_reads_does_not_cost_our_slot(self):
        h = two_story_harness()
        try:
            recheck.CrossStoryClaimRaceTests.interleave(recheck.CrossStoryClaimRaceTests(), h, EARLY)
            original = h.fake.list_comments
            reads = {"n": 0}

            def listing(number):
                comments = original(number)
                if number == 23 and any(c.comment_id == 9 for c in comments):
                    reads["n"] += 1
                    if reads["n"] == 1:  # the loser's release lands between our first and second read
                        h.fake.comments[23].append(Comment(11, render_marker(kind="release", run="run-other", story=OTHER, op="release", inst="0123456789abcdef") + "\nlost", "machine", "2026-11-06T13:00:50Z"))
                return comments

            h.fake.list_comments = listing
            state = h.reserve()
            self.assertEqual((state.phase, state.claim["race_settled"]), ("reserved", True))
            self.assertEqual(events(h, "claim-race-reread")[0]["detail"]["released"], [9])
            self.assertEqual(markers(h.fake, 21, "release"), [])
        finally:
            h.close()

    def test_an_earlier_claim_that_merely_vanishes_from_the_re_read_still_wins(self):
        h = two_story_harness()
        try:
            recheck.CrossStoryClaimRaceTests.interleave(recheck.CrossStoryClaimRaceTests(), h, EARLY)
            original = h.fake.list_comments
            reads = {"n": 0}

            def listing(number):
                comments = original(number)
                if number == 23 and any(c.comment_id == 9 for c in comments):
                    reads["n"] += 1
                    if reads["n"] >= 2:  # the second read does not list it (no release anywhere)
                        return [c for c in comments if c.comment_id != 9]
                return comments

            h.fake.list_comments = listing
            with self.assertRaises(Conflict) as ctx:
                h.reserve()
            self.assertEqual(ctx.exception.code, "claim-active-elsewhere")
            self.assertEqual(events(h, "claim-race-reread"), [])
        finally:
            h.close()


class LegacySplitReservationTests(unittest.TestCase):
    """Fix 4: state saved without ``race_settled`` is settled before it is reported reserved."""

    def split(self, h: Harness, pending: bool) -> None:
        h.fake.crash_after_post = True
        with self.assertRaises(prior.CrashAfterEffect if hasattr(prior, "CrashAfterEffect") else Exception):
            h.reserve()
        state = h.store.load_story(S)
        self.assertEqual(state.phase, "claim-incomplete")
        if not pending:  # the claim was marked done but the transition never persisted (pre-1e2ea57 split state)
            intent = state.intent("claim")
            intent.status, intent.comment_id = "done", markers(h.fake, 21, "claim")[0].comment_id
        state.claim.pop("race_settled")  # LABELLED MUTATION: written before the flag existed
        h.store.save_story(state)

    def test_a_done_claim_without_the_flag_is_settled_against_other_stories(self):
        h = two_story_harness()
        try:
            self.split(h, pending=False)
            h.fake.comments[23].append(foreign_claim(created_at=EARLY, author="machine", inst="0123456789abcdef", run="run-other"))
            with self.assertRaises(Conflict) as ctx:
                fresh(h).resume(S, ok_worktree)
            self.assertEqual(ctx.exception.code, "claim-active-elsewhere")
            state = h.store.load_story(S)
            self.assertEqual((state.phase, state.claim["race_settled"]), ("cancelled", True))
            self.assertTrue(events(h, "claim-race-flag-added"))
            self.assertEqual(len([c for c in markers(h.fake, 21, "release") if "run=run-1" in c.body]), 1)
        finally:
            h.close()

    def test_a_pending_claim_without_the_flag_is_settled_too(self):
        h = two_story_harness()
        try:
            self.split(h, pending=True)
            h.fake.comments[23].append(foreign_claim(created_at=EARLY, author="machine", inst="0123456789abcdef", run="run-other"))
            with self.assertRaises(Conflict) as ctx:
                fresh(h).resume(S, ok_worktree)
            self.assertEqual(ctx.exception.code, "claim-active-elsewhere")
            self.assertEqual(h.store.load_story(S).phase, "cancelled")
            self.assertTrue(events(h, "claim-race-flag-added"))
        finally:
            h.close()

    def test_without_a_competing_claim_the_legacy_reservation_is_reported_reserved(self):
        h = two_story_harness()
        try:
            self.split(h, pending=False)
            resumed = fresh(h).resume(S, ok_worktree)
            self.assertEqual((resumed.phase, resumed.claim["race_settled"]), ("reserved", True))
        finally:
            h.close()


class RawDigestScopeTests(unittest.TestCase):
    """Fix 5: a new activation must name the canonical digest; the raw-bytes digest is accepted only for a run that already exists under it."""

    def test_a_new_activation_naming_the_raw_digest_creates_no_run(self):
        lh = LiveHarness()
        try:
            lh.path.write_text(activation_text(lh.h.policy, policy_digest=f'"{lh.h.policy.raw_digest}"'), encoding="utf-8")
            lh.activation = load_activation(lh.path)
            self.assertEqual(lh.activation.problems(lh.h.policy, "run-live", lh.clock[0])[0][0], "activation-mismatch")
            with self.assertRaises(Refused) as ctx:
                lh.coordinator()
            self.assertEqual(ctx.exception.code, "activation-mismatch")
            self.assertFalse((lh.h.state_dir / "run-live").exists())
        finally:
            lh.close()

    def test_an_existing_run_bound_to_the_raw_digest_still_advances_under_its_activation(self):
        lh = LiveHarness()
        try:
            lh.coordinator()  # created under the canonical digest
            raw_path = Path(lh.h.tmpdir.name) / "activation-raw.toml"
            raw_path.write_text(activation_text(lh.h.policy, policy_digest=f'"{lh.h.policy.raw_digest}"'), encoding="utf-8")
            raw = load_activation(raw_path)
            run_json = lh.h.state_dir / "run-live" / "run.json"
            record = json.loads(run_json.read_text(encoding="utf-8"))  # LABELLED MUTATION: what a run created under a raw-digest activation (before this fix) recorded
            record["policy_digest"], record["activation"]["policy_digest"], record["activation"]["digest"], record["activation"]["path"] = lh.h.policy.raw_digest, lh.h.policy.raw_digest, raw.digest, raw.path
            run_json.write_text(json.dumps(record), encoding="utf-8")
            self.assertEqual(raw.problems(lh.h.policy, "run-live", lh.clock[0], bound_digest=lh.h.policy.raw_digest), [])
            self.assertEqual(raw.problems(lh.h.policy, "run-live", lh.clock[0], bound_digest=lh.h.policy.digest)[0][0], "activation-mismatch")  # a run bound to the canonical digest does not take it
            c = lh.coordinator(activation=raw)
            self.assertIsNone(c.status()["stop"])
            self.assertEqual(c.reserve(S, lh.h.snapshot, "c5d9d2e").phase, "reserved")
            with mock.patch.object(cli, "utcnow", lambda: lh.clock[0]):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = cli.main(["--policy", str(Path(lh.h.tmpdir.name) / "policy.toml"), "--state-dir", str(lh.h.state_dir), "--run-id", "run-live", "--activation", str(raw_path), "check-activation"])
                self.assertEqual((code, json.loads(buf.getvalue())["bound_digest"]), (0, lh.h.policy.raw_digest))
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = cli.main(["--policy", str(Path(lh.h.tmpdir.name) / "policy.toml"), "--state-dir", str(lh.h.state_dir), "--run-id", "run-new", "--activation", str(raw_path), "check-activation"])
                self.assertEqual((code, json.loads(buf.getvalue())["current"]), (2, False))
                run_json.write_text("{not json", encoding="utf-8")
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = cli.main(["--policy", str(Path(lh.h.tmpdir.name) / "policy.toml"), "--state-dir", str(lh.h.state_dir), "--run-id", "run-live", "--activation", str(raw_path), "check-activation"])
                self.assertEqual(code, 2)
                self.assertTrue(any("run.json is not readable JSON" in m for m in json.loads(buf.getvalue())["problems"]))  # a corrupt run is reported, never read as "no run"
        finally:
            lh.close()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
