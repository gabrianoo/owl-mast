"""Regressions for the PR #115 recheck review at 35c8832 (review 5842090200, 2026-11-10): a claim's
age never dismisses it without ``--force`` (local proof that its run finished, or the attestation),
the local run lookup of ``dismiss-claim`` owns by the same rule as admission (no phase, an unknown
phase and an unreadable file are owned), and ``check-activation`` without ``--run-id`` looks no
run up."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from automation.tests import test_activation as activation_tests
from automation.tests import test_pr115_recheck_findings as recheck
from automation.tests import test_pr115_review_findings as prior
from automation.unattended import cli
from automation.unattended.coordinator import Coordinator
from automation.unattended.errors import Refused
from automation.unattended.github import render_marker
from automation.unattended.state import Store, story_ownership

LiveHarness, activation_text = activation_tests.LiveHarness, activation_tests.activation_text
markers = prior.markers
two_story_harness = recheck.two_story_harness

S = "OM-01.02"
OTHER = "OM-01.04"  # issue 23
NOW = "2026-11-06T13:05:00Z"


class LocalRunOwnershipTests(unittest.TestCase):
    def test_story_ownership_is_one_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "OM-01.02.json"
            for raw, expected in (("{broken", ("unreadable story file OM-01.02.json", True)), ("[]", ("unreadable story file OM-01.02.json", True)),
                                  ('{"x": 1}', ("unreadable story file OM-01.02.json", True)), ('{"phase": 7}', ("unreadable story file OM-01.02.json", True)),
                                  ('{"phase": "done"}', ("unknown phase \'done\' in story file OM-01.02.json", True)),
                                  ('{"phase": "reserved"}', ("reserved", True)), ('{"phase": "conflict"}', ("conflict", True)),
                                  ('{"phase": "proposed"}', ("proposed", False)), ('{"phase": "blocked"}', ("blocked", False)), ('{"phase": "cancelled"}', ("cancelled", False))):
                path.write_text(raw, encoding="utf-8")
                self.assertEqual(story_ownership(path), expected, raw)
            self.assertEqual(story_ownership(Path(tmp) / "missing.json"), ("unreadable story file missing.json", True))
            other = Path(tmp) / "run-other"
            (other / "stories").mkdir(parents=True)
            (other / "run.json").write_text("{}", encoding="utf-8")
            (other / "stories" / "OM-01.02.json").write_text('{"phase": "done"}', encoding="utf-8")
            (other / "stories" / "OM-01.04.json").write_text('{"x": 1}', encoding="utf-8")
            (other / "stories" / "OM-01.05.json").write_text('{"phase": "proposed"}', encoding="utf-8")
            self.assertEqual(Store(Path(tmp), "run-1").other_runs_with_active_stories(), {"run-other": ["OM-01.02 (unknown phase \'done\' in story file OM-01.02.json)", "OM-01.04 (unreadable story file OM-01.04.json)"]})

    def test_dismiss_claim_owns_a_local_story_exactly_as_admission_does(self):
        h = two_story_harness()
        try:
            other = Coordinator(h.fake, h.policy, Store(h.state_dir, "run-b"), live=True)
            other.reserve(OTHER, h.snapshot, "c5d9d2e")
            theirs = markers(h.fake, 23, "claim")[0]
            story_file = h.state_dir / "run-b" / "stories" / f"{OTHER}.json"
            for raw, label in (('{"x": 1}', f"unreadable story file {OTHER}.json"), ('{"phase": "finished"}', f"unknown phase \'finished\' in story file {OTHER}.json"), ("{broken", f"unreadable story file {OTHER}.json")):
                story_file.write_text(raw, encoding="utf-8")  # LABELLED MUTATION: a story file another run left without a phase, with a phase this code does not know, or torn
                self.assertEqual(Store(h.state_dir, "run-1").other_runs_with_active_stories(), {"run-b": [f"{OTHER} ({label})"]})
                with self.assertRaises(Refused) as ctx:
                    h.coordinator.dismiss_claim(23, theirs.comment_id, "B looks finished", force=True)
                self.assertEqual((ctx.exception.code, ctx.exception.detail["evidence"]["local_run"]["phase"], ctx.exception.detail["evidence"]["local_run"]["owns_story"]), ("dismiss-target-live", label, True), raw)
                self.assertEqual(markers(h.fake, 23, "dismiss"), [])
        finally:
            h.close()

    def test_a_local_run_proves_a_claim_finished_only_for_its_own_instance_and_story(self):
        h = two_story_harness()
        try:
            other = Coordinator(h.fake, h.policy, Store(h.state_dir, "run-b"), live=True)
            other.reserve(OTHER, h.snapshot, "c5d9d2e")
            other.cancel(OTHER, "done here", no_launch={"authorization": f"run-b:{OTHER}:1", "reason": "never launched"})
            theirs = markers(h.fake, 23, "claim")[0]
            twin = h.fake.add_comment(23, render_marker(kind="claim", run="run-b", story=OTHER, op="claim", inst="feedfacefeedface") + "\nsame run id on another machine", "stranger")
            with self.assertRaises(Refused) as ctx:  # run-b here is cancelled, but this claim is another run-b's (another instance): no proof
                h.coordinator.dismiss_claim(23, twin.comment_id, "run-b is cancelled")
            self.assertEqual(ctx.exception.code, "dismiss-target-live")
            self.assertEqual((ctx.exception.detail["evidence"]["local_run"]["same_instance"], ctx.exception.detail["evidence"]["local_run"]["finished"], ctx.exception.detail["evidence"]["possibly_live"]), (False, False, True))
            (h.state_dir / "run-b" / "stories" / f"{OTHER}.json").unlink()  # LABELLED MUTATION: the run exists but never recorded the story: no proof either
            with self.assertRaises(Refused) as ctx:
                h.coordinator.dismiss_claim(23, theirs.comment_id, "run-b is cancelled")
            self.assertEqual((ctx.exception.code, ctx.exception.detail["evidence"]["local_run"]["phase"], ctx.exception.detail["evidence"]["local_run"]["finished"]), ("dismiss-target-live", None, False))
            self.assertEqual(markers(h.fake, 23, "dismiss"), [])
            self.assertTrue(h.coordinator.dismiss_claim(23, theirs.comment_id, "attested dead", force=True)["evidence"]["forced"])
        finally:
            h.close()

    def test_a_legacy_run_without_an_instance_proves_only_a_claim_without_inst(self):
        h = two_story_harness()
        try:
            run_json = h.state_dir / "run-b" / "run.json"
            (h.state_dir / "run-b" / "stories").mkdir(parents=True)
            record = json.loads((h.state_dir / "run-1" / "run.json").read_text(encoding="utf-8"))
            record["instance"], record["run_id"] = None, "run-b"  # LABELLED MUTATION: a run created before the instance nonce existed
            run_json.write_text(json.dumps(record), encoding="utf-8")
            (h.state_dir / "run-b" / "stories" / f"{OTHER}.json").write_text('{"phase": "cancelled"}', encoding="utf-8")  # LABELLED MUTATION: only the phase matters to the ownership rule
            legacy = h.fake.add_comment(23, render_marker(kind="claim", run="run-b", story=OTHER, op="claim") + "\nbefore the nonce", "stranger")
            nonced = h.fake.add_comment(23, render_marker(kind="claim", run="run-b", story=OTHER, op="claim", inst="feedfacefeedface") + "\nafter the nonce", "stranger")
            with self.assertRaises(Refused) as ctx:  # a nonced claim is not the legacy run's
                h.coordinator.dismiss_claim(23, nonced.comment_id, "run-b is cancelled")
            self.assertEqual((ctx.exception.code, ctx.exception.detail["evidence"]["local_run"]["same_instance"]), ("dismiss-target-live", False))
            report = h.coordinator.dismiss_claim(23, legacy.comment_id, "run-b is cancelled")  # the legacy pairing: proof, no --force
            self.assertEqual((report["evidence"]["local_run"]["same_instance"], report["evidence"]["local_run"]["finished"], report["evidence"]["forced"]), (True, True, False))
            run_json.write_text("[]", encoding="utf-8")  # LABELLED MUTATION: a torn run record is never read as a legacy run
            torn = h.fake.add_comment(23, render_marker(kind="claim", run="run-b", story=OTHER, op="claim") + "\nanother", "stranger")
            with self.assertRaises(Refused) as ctx:
                h.coordinator.dismiss_claim(23, torn.comment_id, "run-b is cancelled", force=True)
            self.assertEqual((ctx.exception.code, ctx.exception.detail["evidence"]["local_run"]["phase"], ctx.exception.detail["evidence"]["local_run"]["owns_story"]), ("dismiss-target-live", "unreadable", True))
            self.assertIn("not a record", ctx.exception.detail["evidence"]["local_run"]["error"])
        finally:
            h.close()


class CheckActivationWithoutRunIdTests(unittest.TestCase):
    def test_check_activation_without_run_id_reports_the_digest_and_looks_no_run_up(self):
        lh = LiveHarness()
        try:
            lh.coordinator()  # a run exists; without --run-id it is not consulted
            with mock.patch.object(cli, "utcnow", lambda: lh.clock[0]):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = cli.main(["--policy", str(Path(lh.h.tmpdir.name) / "policy.toml"), "--state-dir", str(lh.h.state_dir), "--activation", str(lh.path), "check-activation"])
                out = json.loads(buf.getvalue())
            # the digest is reported and no run is looked up; without a run id the document is current for nothing (PR #108 review: an activation authorizes exactly one run)
            self.assertEqual((code, out["run_id"], out["bound_digest"], out["run_exists"], out["policy_digest"], out["current"], out["stop"]), (2, None, None, False, lh.h.policy.digest, False, "activation-invalid"))
        finally:
            lh.close()
