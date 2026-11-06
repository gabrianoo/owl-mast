"""Synchronization faults: stale revisions, duplicates, retries, partial writes, crash/restart,
denial and outage. Every fault must leave the story without a false advance."""

import unittest

from automation.tests.fake_transport import CrashAfterEffect, FakeTransport, small_backlog
from automation.tests.support import IMPLEMENTER, Harness
from automation.unattended.backlog import take_snapshot
from automation.unattended.coordinator import Coordinator
from automation.unattended.errors import Conflict, Outage, PermissionDenied, Refused, StaleRevision
from automation.unattended.github import Comment, render_marker
from automation.unattended.state import Store


def markers(fake: FakeTransport, number: int, kind: str):
    return [c for c in fake.comments[number] if c.marker and c.marker["kind"] == kind]


class StaleAndConcurrentEditTests(unittest.TestCase):
    def setUp(self):
        self.h = Harness(small_backlog())

    def tearDown(self):
        self.h.close()

    def test_project_item_edited_after_snapshot_is_stale(self):
        self.h.fake.set_status_externally(21, "Ready")  # same value, newer updatedAt
        with self.assertRaises(StaleRevision):
            self.h.claim()
        state = self.h.store.load_story("OM-01.02")
        self.assertEqual(state.phase, "claim-incomplete")
        self.assertEqual(self.h.fake.item_for(21).status, "Ready")

    def test_owner_moved_status_after_snapshot_is_stale(self):
        self.h.fake.set_status_externally(21, "Blocked")
        with self.assertRaises(StaleRevision) as ctx:
            self.h.claim()
        self.assertEqual(ctx.exception.detail["observed"], "Blocked")

    def test_residual_window_edit_is_not_detectable_documented_limitation(self):
        """GitHub has no compare-and-swap: an edit that lands between the pre-write read and
        the write is overwritten and the post-write verification cannot tell. This test pins
        that limitation so the documentation stays honest; the pre-write check above is the
        only protection, and it closes everything before that read."""
        self.h.fake.mutate_before_write = lambda f: f.set_status_externally(21, "Blocked")
        state = self.h.claim()
        self.assertEqual(state.phase, "claimed")
        self.assertEqual(self.h.fake.item_for(21).status, "In progress")  # last writer wins on GitHub
        journal = [e["event"] for e in self.h.store.read_journal()]
        self.assertIn("status-verified", journal)  # verification passed although an edit was lost

    def test_foreign_active_claim_is_refused(self):
        other = Coordinator(self.h.fake, self.h.policy, Store(self.h.store.root.parent, "run-other"))
        other.claim("OM-01.02", self.h.snapshot, dict(IMPLEMENTER), "/tmp/other", "t3/om-01-02", "c5d9d2e", lambda p, b: (True, "ok"))
        self.h.fake.set_status_externally(21, "Ready")  # pretend the owner reset it
        self.h.snapshot = take_snapshot(self.h.fake, "x/y", "now")
        with self.assertRaises(Refused) as ctx:
            self.h.claim()
        self.assertIn("claimed by another run", str(ctx.exception))


class IdempotencyAndRetryTests(unittest.TestCase):
    def setUp(self):
        self.h = Harness(small_backlog())

    def tearDown(self):
        self.h.close()

    def test_duplicate_claim_event_posts_one_comment(self):
        self.h.claim()
        with self.assertRaises(Refused):
            self.h.claim()  # duplicate event: already claimed in this run
        self.assertEqual(len(markers(self.h.fake, 21, "claim")), 1)

    def test_transient_outage_on_post_then_retry_has_single_effect(self):
        self.h.fake.fail_once["post_comment"] = Outage("HTTP 502")
        with self.assertRaises(Outage):
            self.h.claim()
        state = self.h.store.load_story("OM-01.02")
        self.assertEqual(state.phase, "claim-incomplete")
        self.assertEqual(self.h.fake.item_for(21).status, "Ready")
        self.h.coordinator.resume("OM-01.02", lambda p, b: (True, "ok"))
        self.assertEqual(self.h.store.load_story("OM-01.02").phase, "claimed")
        self.assertEqual(len(markers(self.h.fake, 21, "claim")), 1)
        self.assertEqual(self.h.fake.item_for(21).status, "In progress")

    def test_partial_write_crash_after_comment_is_adopted_on_resume(self):
        self.h.fake.crash_after_post = True
        with self.assertRaises(CrashAfterEffect):
            self.h.claim()
        state = self.h.store.load_story("OM-01.02")
        self.assertEqual(state.pending_intents()[0].kind, "claim")
        self.assertEqual(len(markers(self.h.fake, 21, "claim")), 1)
        # restart: a fresh coordinator over the same store
        fresh = Coordinator(self.h.fake, self.h.policy, Store(self.h.store.root.parent, "run-1"))
        fresh.resume("OM-01.02", lambda p, b: (True, "ok"))
        state = self.h.store.load_story("OM-01.02")
        self.assertEqual(state.pending_intents(), [])
        self.assertEqual(state.phase, "claimed")
        self.assertEqual(len(markers(self.h.fake, 21, "claim")), 1)  # not posted twice
        events = [e["event"] for e in self.h.store.read_journal()]
        self.assertIn("intents-adopted", events)

    def test_duplicate_marker_from_concurrent_writer_is_a_conflict(self):
        marker = render_marker(kind="claim", run="run-1", story="OM-01.02", seq="1")
        self.h.fake.comments[21].append(Comment(1, marker + "\nfirst", "x", "t"))
        self.h.fake.comments[21].append(Comment(2, marker + "\nsecond", "y", "t"))
        with self.assertRaises(Conflict):
            self.h.claim()


class DenialAndOutageTests(unittest.TestCase):
    def setUp(self):
        self.h = Harness(small_backlog())

    def tearDown(self):
        self.h.close()

    def test_permission_denied_on_status_write_does_not_advance(self):
        self.h.fake.fail_always["set_project_status"] = PermissionDenied("HTTP 403")
        with self.assertRaises(PermissionDenied):
            self.h.claim()
        self.assertEqual(self.h.store.load_story("OM-01.02").phase, "claim-incomplete")
        self.assertEqual(self.h.fake.item_for(21).status, "Ready")

    def test_outage_on_read_fails_closed_before_any_effect(self):
        self.h.fake.fail_always["list_comments"] = Outage("no such host")
        with self.assertRaises(Outage):
            self.h.claim()
        self.assertEqual(self.h.fake.comments[21], [])
        self.assertEqual(self.h.fake.item_for(21).status, "Ready")

    def test_block_records_github_failure_but_stays_blocked_locally(self):
        self.h.claim()
        self.h.fake.fail_always["post_comment"] = Outage("HTTP 503")
        state = self.h.coordinator.block("OM-01.02", "checks cannot run")
        self.assertEqual(state.phase, "blocked")
        self.assertEqual(state.blocked["github_error"]["code"], "outage")

    def test_resume_abandons_claim_when_owner_changed_status(self):
        self.h.fake.fail_once["set_project_status"] = Outage("HTTP 502")
        with self.assertRaises(Outage):
            self.h.claim()
        self.h.fake.set_status_externally(21, "Blocked")
        state = self.h.coordinator.resume("OM-01.02", lambda p, b: (True, "ok"))
        self.assertEqual(state.phase, "cancelled")
        self.assertEqual(len(markers(self.h.fake, 21, "release")), 1)
        self.assertEqual(self.h.fake.item_for(21).status, "Blocked")  # never overwritten
