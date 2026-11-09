import tempfile
import unittest
from pathlib import Path

from automation.tests.fake_transport import small_backlog
from automation.tests.support import write_policy
from automation.unattended.backlog import take_snapshot
from automation.unattended.eligibility import decide, plan
from automation.unattended.github import IssueRecord
from automation.unattended.policy import load_policy


class EligibilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.fake = small_backlog()

    def tearDown(self):
        self.tmp.cleanup()

    def policy(self, **overrides):
        return load_policy(write_policy(self.dir, **overrides))

    def snap(self):
        return take_snapshot(self.fake, "gabrianoo/owl-mast", "now")

    def test_ready_story_with_done_closed_dependency_is_dispatchable(self):
        d = decide("OM-01.02", self.snap(), self.policy(allow='["OM-01.02"]'))
        self.assertEqual(d.outcome, "dispatchable")

    def test_not_allowlisted_fails_closed(self):
        self.assertEqual(decide("OM-01.02", self.snap(), self.policy()).outcome, "not-allowlisted")

    def test_unknown_story(self):
        self.assertEqual(decide("OM-01.09", self.snap(), self.policy(allow='["OM-01.09"]')).outcome, "unknown-story")

    def test_owner_gate_backlog(self):
        d = decide("OM-01.03", self.snap(), self.policy(allow='["OM-01.03"]'))
        self.assertEqual(d.outcome, "awaiting-owner-acceptance")

    def test_optional_and_later_epics_excluded_by_default(self):
        p = self.policy(allow='["OM-17.01", "OM-19.01"]')
        self.assertEqual([d.outcome for d in plan(self.snap(), p)], ["excluded-epic", "excluded-epic"])
        p2 = self.policy(allow='["OM-17.01", "OM-19.01"]', include_optional_epics="true", include_later_epics="true")
        self.assertEqual([d.outcome for d in plan(self.snap(), p2)], ["dispatchable", "dispatchable"])

    def test_dependency_not_done_blocks(self):
        d = decide("OM-02.01", self.snap(), self.policy(allow='["OM-02.01"]'))
        self.assertEqual(d.outcome, "blocked-by-dependency")
        self.assertTrue(any("OM-01.02" in r for r in d.reasons))
        self.assertTrue(any("E01: epic prerequisite incomplete" in r for r in d.reasons))

    def test_contract_design_exception_is_scoped(self):
        d = decide("OM-02.01", self.snap(), self.policy(allow='["OM-02.01"]', contract_design_exceptions='["OM-02.01"]'))
        self.assertEqual(d.outcome, "dispatchable-contract-design-only")
        self.assertTrue(d.dispatchable)

    def test_reopened_dependency_fails_closed(self):
        closed = self.fake.issues[20]
        self.fake.issues[20] = IssueRecord(**{**closed.__dict__, "state": "OPEN", "closed_at": None, "state_reason": None})
        d = decide("OM-01.02", self.snap(), self.policy(allow='["OM-01.02"]'))
        self.assertEqual(d.outcome, "blocked-by-dependency")
        self.assertIn("reopened", d.reasons[0])

    def test_closed_as_not_planned_is_not_done(self):
        closed = self.fake.issues[20]
        self.fake.issues[20] = IssueRecord(**{**closed.__dict__, "state_reason": "NOT_PLANNED"})
        self.fake.set_status_externally(20, "Backlog")
        d = decide("OM-01.02", self.snap(), self.policy(allow='["OM-01.02"]'))
        self.assertEqual(d.outcome, "blocked-by-dependency")
        self.assertIn("not planned", d.reasons[0])

    def test_unknown_dependency_close_reason_fails_closed(self):
        """Round-1 findings R1-B7/V6: only an explicit COMPLETED reason satisfies a dependency."""
        closed = self.fake.issues[20]
        self.fake.issues[20] = IssueRecord(**{**closed.__dict__, "state_reason": None})
        d = decide("OM-01.02", self.snap(), self.policy(allow='["OM-01.02"]'))
        self.assertEqual(d.outcome, "blocked-by-dependency")
        self.assertIn("unknown", d.reasons[0])
        self.fake.issues[20] = IssueRecord(**{**closed.__dict__, "state_reason": "DUPLICATE"})
        self.assertEqual(decide("OM-01.02", self.snap(), self.policy(allow='["OM-01.02"]')).outcome, "blocked-by-dependency")

    def test_reopened_story_itself_is_inconsistent(self):
        self.fake.set_status_externally(21, "Done")
        d = decide("OM-01.02", self.snap(), self.policy(allow='["OM-01.02"]'))
        self.assertEqual(d.outcome, "reopened-inconsistent")

    def test_missing_project_item_is_unknown(self):
        item = self.fake.item_for(21)
        del self.fake.items[item.item_id]
        d = decide("OM-01.02", self.snap(), self.policy(allow='["OM-01.02"]'))
        self.assertEqual(d.outcome, "unknown-eligibility")

    def test_unparsed_dependency_text_fails_closed(self):
        """Reviewer probe B9/E2/V3: malformed declarations are unknown, not empty."""
        for text in ("TBD pending owner", "OM-01.01 and OM-01.03", "OM-01.01 (pending)", "", "None, OM-01.01"):
            body = self.fake.issues[21].body.replace("**Depends on:** OM-01.01", f"**Depends on:** {text}")
            self.fake.issues[21] = IssueRecord(**{**self.fake.issues[21].__dict__, "body": body})
            snap = self.snap()
            self.assertFalse(snap.by_id()["OM-01.02"].depends_on_known, text)
            d = decide("OM-01.02", snap, self.policy(allow='["OM-01.02"]'))
            self.assertEqual(d.outcome, "unknown-eligibility", text)

    def test_missing_or_duplicated_declaration_fails_closed(self):
        body = self.fake.issues[21].body.replace("**Depends on:** OM-01.01\n", "")
        self.fake.issues[21] = IssueRecord(**{**self.fake.issues[21].__dict__, "body": body})
        self.assertEqual(decide("OM-01.02", self.snap(), self.policy(allow='["OM-01.02"]')).outcome, "unknown-eligibility")
        body = self.fake.issues[23].body + "**Depends on:** None\n"
        self.fake.issues[23] = IssueRecord(**{**self.fake.issues[23].__dict__, "body": body})
        self.assertEqual(decide("OM-01.04", self.snap(), self.policy(allow='["OM-01.04"]')).outcome, "unknown-eligibility")

    def test_unknown_epic_prerequisites_fail_closed(self):
        body = self.fake.issues[1].body.replace("**Epic prerequisites:** None", "**Epic prerequisites:** see plan")
        self.fake.issues[1] = IssueRecord(**{**self.fake.issues[1].__dict__, "body": body})
        self.assertEqual(decide("OM-01.02", self.snap(), self.policy(allow='["OM-01.02"]')).outcome, "unknown-eligibility")

    def test_strict_declaration_grammar_accepts_real_forms(self):
        from automation.unattended.backlog import parse_declaration

        self.assertEqual(parse_declaration("None"), ((), True))
        self.assertEqual(parse_declaration("OM-16.03, OM-16.04."), (("OM-16.03", "OM-16.04"), True))
        self.assertEqual(parse_declaration("E01, E02, E03"), (("E01", "E02", "E03"), True))
        self.assertEqual(parse_declaration("OM-16.03, E11."), (("OM-16.03", "E11"), True))
        self.assertEqual(parse_declaration(None), ((), False))
        self.assertEqual(parse_declaration("none"), ((), False))

    def test_active_and_blocked_statuses_are_not_dispatchable(self):
        for status, outcome in (("In progress", "already-active"), ("In review", "already-active"), ("Blocked", "blocked")):
            self.fake.set_status_externally(21, status)
            self.assertEqual(decide("OM-01.02", self.snap(), self.policy(allow='["OM-01.02"]')).outcome, outcome)
