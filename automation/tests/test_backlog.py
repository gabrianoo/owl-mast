import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from automation.unattended import cli

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

    def test_every_real_declaration_is_understood(self):
        for entry in self.snapshot.entries:
            self.assertTrue(entry.depends_on_known and entry.epic_prerequisites_known, entry.stable_id)

    def test_derived_bmad_key_is_only_a_projection(self):
        entry = self.snapshot.by_id()["OM-01.02"]
        self.assertTrue(entry.bmad_key.startswith("1-2-"))
        self.assertEqual(entry.stable_id, "OM-01.02")  # the stable id is never renumbered

    def test_engineering_issue_is_outside_backlog_counts(self):
        others = [e for e in self.snapshot.entries if e.kind == "other"]
        self.assertEqual([e.stable_id for e in others], ["ENG-01"])


class RealBacklogNegativeMappingTests(unittest.TestCase):
    """Round-1 finding R1-V1: a full, otherwise valid snapshot with one broken relationship
    must produce a named discrepancy and a nonzero CLI exit."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.text = (FIXTURES / "backlog-snapshot-2026-11-06.json").read_text(encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def mutate(self, fn):
        raw = json.loads(self.text)
        for entry in raw["entries"]:
            fn(entry)
        return Snapshot.from_json(json.dumps(raw)), raw

    def cli_exit(self, raw) -> tuple[int, dict]:
        path = Path(self.tmp.name) / "snap.json"
        path.write_text(json.dumps(raw), encoding="utf-8")
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli.main(["--snapshot", str(path), "--repo-root", str(ROOT), "verify-mapping"])
        return code, json.loads(buf.getvalue())

    def test_missing_native_parent_is_named(self):
        snap, raw = self.mutate(lambda e: e.update(parent_number=None) if e["stable_id"] == "OM-01.02" else None)
        report = verify_mapping(snap, load_tasks_index(ROOT))
        self.assertFalse(report["ok"])
        self.assertIn("OM-01.02 (#21) has no native parent issue", report["problems"])
        code, out = self.cli_exit(raw)
        self.assertEqual(code, 2)
        self.assertIn("OM-01.02 (#21) has no native parent issue", out["problems"])

    def test_wrong_native_parent_is_named(self):
        snap, raw = self.mutate(lambda e: e.update(parent_number=2) if e["stable_id"] == "OM-01.02" else None)
        report = verify_mapping(snap, load_tasks_index(ROOT))
        self.assertIn("OM-01.02 parent is E02, expected E01", report["problems"])
        self.assertEqual(self.cli_exit(raw)[0], 2)

    def test_duplicate_task_id_is_named(self):
        def dup(e):
            if e["stable_id"] == "OM-01.02":
                e["tasks"][1]["task_id"] = "OM-01.02-T1"
        snap, raw = self.mutate(dup)
        report = verify_mapping(snap, load_tasks_index(ROOT))
        self.assertIn("OM-01.02: task 2 is OM-01.02-T1", report["problems"])
        self.assertTrue(any("differ from TASKS.md" in p for p in report["problems"]))
        self.assertEqual(self.cli_exit(raw)[0], 2)

    def test_unknown_dependency_target_and_missing_item_are_named(self):
        def mut(e):
            if e["stable_id"] == "OM-01.03":
                e["depends_on"] = ["OM-01.99"]
            if e["stable_id"] == "OM-01.04":
                e["item_id"] = None
        snap, raw = self.mutate(mut)
        report = verify_mapping(snap, load_tasks_index(ROOT))
        self.assertIn("OM-01.03 depends on unknown OM-01.99", report["problems"])
        self.assertIn("OM-01.04 (#23) has no Project item", report["problems"])
        self.assertEqual(self.cli_exit(raw)[0], 2)

    def test_untouched_fixture_passes_the_same_path(self):
        code, out = self.cli_exit(json.loads(self.text))
        self.assertEqual((code, out["ok"]), (0, True))


class SyntheticMappingTests(unittest.TestCase):
    def test_missing_parent_and_duplicate_task_ids_are_reported(self):
        fake = small_backlog()
        snap = take_snapshot(fake, "gabrianoo/owl-mast", "now")
        report = verify_mapping(snap)
        self.assertFalse(report["ok"])  # the small fixture is deliberately not 19/85/340
        self.assertIn("epics: expected 19, found 4", report["problems"])
        broken = snap.by_id()["OM-01.03"]
        self.assertEqual(broken.depends_on, ("OM-01.01",))
        self.assertEqual([t.task_id for t in broken.tasks], ["OM-01.03-T1", "OM-01.03-T2", "OM-01.03-T3", "OM-01.03-T4"])

    def test_round_trip_json(self):
        snap = take_snapshot(small_backlog(), "gabrianoo/owl-mast", "now")
        again = Snapshot.from_json(snap.to_json())
        self.assertEqual(again.to_json(), snap.to_json())
