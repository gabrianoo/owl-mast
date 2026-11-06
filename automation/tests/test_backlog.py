import unittest

from automation.tests.fake_transport import small_backlog
from automation.tests.support import FIXTURES, ROOT
from automation.unattended.backlog import Snapshot, load_tasks_index, take_snapshot, verify_mapping


class RealBacklogMappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = Snapshot.from_json((FIXTURES / "backlog-snapshot-2026-11-06.json").read_text(encoding="utf-8"))
        cls.report = verify_mapping(cls.snapshot, load_tasks_index(ROOT))

    def test_counts_match_contract(self):
        self.assertEqual(self.report["counts"]["epics"], 19)
        self.assertEqual(self.report["counts"]["stories"], 85)
        self.assertEqual(self.report["counts"]["tasks"], 340)
        self.assertEqual(self.report["counts"]["tasks_index"], 340)
        self.assertTrue(self.report["ok"], self.report["problems"])

    def test_every_story_has_native_parent_and_project_item(self):
        by_number = self.snapshot.by_number()
        for entry in self.snapshot.entries:
            if entry.kind == "story":
                self.assertEqual(by_number[entry.parent_number].stable_id, entry.epic_id)
                self.assertEqual(entry.item_stable_id, entry.stable_id)

    def test_dependencies_resolve_and_only_point_backwards(self):
        by_id = self.snapshot.by_id()
        for entry in self.snapshot.entries:
            for dep in entry.depends_on:
                self.assertIn(dep, by_id)
                dep_entry = by_id[dep]
                self.assertLessEqual(dep_entry.epic_id, entry.epic_id, f"{entry.stable_id} depends forward on {dep}")

    def test_derived_bmad_key_is_only_a_projection(self):
        entry = self.snapshot.by_id()["OM-01.02"]
        self.assertTrue(entry.bmad_key.startswith("1-2-"))
        self.assertEqual(entry.stable_id, "OM-01.02")  # the stable id is never renumbered

    def test_engineering_issue_is_outside_backlog_counts(self):
        others = [e for e in self.snapshot.entries if e.kind == "other"]
        self.assertEqual([e.stable_id for e in others], ["ENG-01"])


class SyntheticMappingTests(unittest.TestCase):
    def test_missing_parent_and_duplicate_task_ids_are_reported(self):
        fake = small_backlog()
        snap = take_snapshot(fake, "x/y", "now")
        report = verify_mapping(snap)
        self.assertFalse(report["ok"])  # the small fixture is deliberately not 19/85/340
        self.assertIn("epics: expected 19, found 4", report["problems"])
        broken = snap.by_id()["OM-01.03"]
        self.assertEqual(broken.depends_on, ("OM-01.01",))
        self.assertEqual([t.task_id for t in broken.tasks], ["OM-01.03-T1", "OM-01.03-T2", "OM-01.03-T3", "OM-01.03-T4"])

    def test_round_trip_json(self):
        snap = take_snapshot(small_backlog(), "x/y", "now")
        again = Snapshot.from_json(snap.to_json())
        self.assertEqual(again.to_json(), snap.to_json())
