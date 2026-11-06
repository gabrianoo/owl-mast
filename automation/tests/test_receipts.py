import unittest

from automation.tests.support import IMPLEMENTER, REVIEWER
from automation.unattended.errors import ReceiptInvalid
from automation.unattended.policy import Target
from automation.unattended.receipts import validate_receipt

IMPL = Target("claudeAgent", "claude-fable-5-1", {"effort": "high"}, "worktree")
REV = Target("codex", "gpt-6-astra", {"reasoningEffort": "high"})


class ReceiptTests(unittest.TestCase):
    def test_list_and_mapping_options_both_accepted(self):
        self.assertEqual(validate_receipt(IMPLEMENTER, IMPL, "implementer")["options"], {"effort": "high"})
        self.assertEqual(validate_receipt(REVIEWER, REV, "reviewer")["options"], {"reasoningEffort": "high"})

    def test_missing_effort_fails_closed(self):
        with self.assertRaises(ReceiptInvalid) as ctx:
            validate_receipt({**IMPLEMENTER, "options": {}}, IMPL, "implementer")
        self.assertIn("effort", str(ctx.exception))

    def test_wrong_effort_fails_closed(self):
        with self.assertRaises(ReceiptInvalid):
            validate_receipt({**IMPLEMENTER, "options": {"effort": "medium"}}, IMPL, "implementer")

    def test_wrong_model_or_provider_fails(self):
        with self.assertRaises(ReceiptInvalid):
            validate_receipt({**IMPLEMENTER, "model": "claude-opus-5-5"}, IMPL, "implementer")
        with self.assertRaises(ReceiptInvalid):
            validate_receipt({**REVIEWER, "providerInstanceId": "claudeAgent"}, REV, "reviewer")

    def test_isolation_required_for_implementer(self):
        with self.assertRaises(ReceiptInvalid):
            validate_receipt({**IMPLEMENTER, "isolation": "shared"}, IMPL, "implementer")

    def test_task_id_reuse_is_not_fresh(self):
        with self.assertRaises(ReceiptInvalid):
            validate_receipt(REVIEWER, REV, "reviewer", {"task-review-1"})

    def test_missing_task_id_fails(self):
        with self.assertRaises(ReceiptInvalid):
            validate_receipt({k: v for k, v in IMPLEMENTER.items() if k != "taskId"}, IMPL, "implementer")

    def test_actual_t3_receipt_shape_from_orchestrator_capabilities(self):
        """The shape T3 reported for this very task (inherited target), see evidence."""
        receipt = {"taskId": "owl-unattended-foundation-implementation-20261106", "providerInstanceId": "claudeAgent", "model": "claude-fable-5-1",
                   "options": [{"id": "effort", "value": "high"}], "isolation": "worktree"}
        self.assertEqual(validate_receipt(receipt, IMPL, "implementer")["model"], "claude-fable-5-1")
