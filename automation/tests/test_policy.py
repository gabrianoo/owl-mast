import tempfile
import unittest
from pathlib import Path

from automation.tests.support import write_policy
from automation.unattended.errors import PolicyError
from automation.unattended.policy import load_policy


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_repository_policy_loads_with_empty_allowlist(self):
        policy = load_policy(write_policy(self.dir))
        self.assertEqual(policy.allow, ())
        self.assertEqual(policy.implementer.model, "claude-fable-5-1")
        self.assertEqual(policy.implementer.options, {"effort": "high"})
        self.assertEqual(policy.reviewer.model, "gpt-6-astra")
        self.assertEqual(policy.reviewer.options, {"reasoningEffort": "high"})
        self.assertEqual(policy.max_repair_rounds, 2)
        self.assertEqual(len(policy.digest), 64)

    def _rejects(self, text_or_overrides, needle):
        if isinstance(text_or_overrides, dict):
            path = write_policy(self.dir, **text_or_overrides)
        else:
            path = self.dir / "policy.toml"
            path.write_text(text_or_overrides, encoding="utf-8")
        with self.assertRaises(PolicyError) as ctx:
            load_policy(path)
        self.assertIn(needle, str(ctx.exception))

    def test_secret_like_key_is_refused(self):
        base = write_policy(self.dir).read_text()
        self._rejects(base + '\n[writes.credentials]\ngithub_token = "x"\n', "secret-like key")

    def test_credential_like_value_is_refused(self):
        self._rejects({"owner": '"ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456"'}, "looks like a credential")

    def test_checkbox_application_is_refused(self):
        self._rejects({"apply_task_checkboxes": "true"}, "apply_task_checkboxes")

    def test_merge_must_stay_owner(self):
        self._rejects({"merge": '"auto"'}, "merge")

    def test_repair_round_ceiling(self):
        self._rejects({"max_repair_rounds": "3"}, "max_repair_rounds")

    def test_single_implementer_is_fixed(self):
        self._rejects({"max_concurrent_implementers": "2"}, "max_concurrent_implementers")

    def test_allowlist_entries_must_be_story_ids(self):
        self._rejects({"allow": '["E01"]'}, "not an OM-xx.yy")

    def test_empty_checks_or_probes_refused(self):
        self._rejects({"commands": "[]"}, "commands must not be empty")

    def test_unknown_section_refused(self):
        self._rejects(write_policy(self.dir).read_text() + "\n[merge]\nauto = true\n", "unknown sections")

    def test_effort_option_required_on_targets(self):
        self._rejects({"options": "{ }"}, "options must name at least one option")
