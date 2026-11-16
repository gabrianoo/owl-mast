"""Failure-path checks for the opt-in network qualification harness (no Docker needed)."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("worker_partition", Path(__file__).resolve().parents[2] / "scripts/qualify-worker-partition.py")
probe_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe_module)


class PartitionSafetyTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.probe = probe_module.Probe(SimpleNamespace(cluster="owl-pr189-partition-test", evidence=self.directory.name, image="fixture:test"))
        self.probe.cp_ip = "172.18.0.2"

    def test_rules_target_only_owned_node_and_one_api_endpoint(self):
        with patch.object(probe_module, "command") as command:
            self.probe.iptables(("OUTPUT", "172.18.0.2"), "-I")
        args = command.call_args.args
        self.assertEqual(args[:4], ("docker", "exec", "owl-pr189-partition-test-worker", "iptables"))
        self.assertIn("172.18.0.2/32", args)
        self.assertEqual(args[args.index("--dport") + 1], "6443")
        self.assertEqual(args[args.index("--comment") + 1], "owl-pr189-partition-test")
        self.assertNotIn("-F", args)

    def test_ipv6_api_rule_is_not_an_ipv4_only_partition(self):
        with patch.object(probe_module, "command") as command:
            self.probe.iptables(("FORWARD", "fc00::3"), "-I")
        args = command.call_args.args
        self.assertEqual(args[3], "ip6tables")
        self.assertIn("fc00::3/128", args)
        self.assertEqual(args[args.index("--dport") + 1], "6443")

    def test_recent_commit_proves_db_access_even_between_connections(self):
        self.probe.old["replacement"] = dict(name="worker-old", ip="10.0.0.2", container="owned")
        with patch.object(probe_module, "command", return_value=SimpleNamespace(stdout='{"status":{"state":"CONTAINER_RUNNING"}}')):
            with patch.object(self.probe, "number", side_effect=[0, 1]):
                result = self.probe.alive_and_connected("replacement")
        self.assertEqual(result["db_sessions"], 0)
        self.assertEqual(result["recent_committed_observations"], 1)

    def test_idle_session_without_recent_commit_is_not_db_liveness(self):
        self.probe.old["replacement"] = dict(name="worker-old", ip="10.0.0.2", container="owned")
        with patch.object(probe_module, "command", return_value=SimpleNamespace(stdout='{"status":{"state":"CONTAINER_RUNNING"}}')):
            with patch.object(self.probe, "number", side_effect=[1, 0]):
                with self.assertRaisesRegex(AssertionError, "no recent committed"):
                    self.probe.alive_and_connected("replacement")

    def test_restore_continues_second_chain_when_first_delete_fails(self):
        self.probe.rules = [("OUTPUT", "172.18.0.2"), ("FORWARD", "172.18.0.2")]
        calls = []
        remaining = {"OUTPUT", "FORWARD"}

        def rule(rule, action, check=True):
            chain, address = rule
            calls.append((chain, action))
            if action == "-D":
                if chain == "OUTPUT":
                    raise RuntimeError("injected deletion failure")
                remaining.remove(chain)
            return SimpleNamespace(returncode=0 if chain in remaining else 1)

        with patch.object(self.probe, "iptables", side_effect=rule):
            with self.assertRaisesRegex(AssertionError, "RESTORATION FAILED"):
                self.probe.restore()
        self.assertIn(("FORWARD", "-D"), calls)
        self.assertEqual(self.probe.rules, [("OUTPUT", "172.18.0.2")])

    def test_restore_does_not_delete_absent_rule_after_uncertain_insert(self):
        self.probe.rules = [("OUTPUT", "172.18.0.2")]
        with patch.object(self.probe, "iptables", return_value=SimpleNamespace(returncode=1)) as rule:
            self.probe.restore()
        self.assertEqual(self.probe.rules, [])
        self.assertTrue(all(call.args[1] == "-C" for call in rule.call_args_list))

    def test_restore_check_errors_are_not_claimed_as_absent(self):
        self.probe.rules = [("OUTPUT", "172.18.0.2")]
        with patch.object(self.probe, "iptables", return_value=SimpleNamespace(returncode=2)):
            with self.assertRaisesRegex(AssertionError, "RESTORATION FAILED"):
                self.probe.restore()
        self.assertEqual(self.probe.rules, [("OUTPUT", "172.18.0.2")])

    def test_existing_user_namespace_refused_before_image_load_or_mutation(self):
        with patch.object(probe_module, "command", return_value=SimpleNamespace(stdout="config")) as command:

            def get(resource, *args):
                if resource == "nodes":
                    return {"items": [{"metadata": {"name": name}} for name in (self.probe.control, self.probe.victim, self.probe.healthy)]}
                if resource == "pods":
                    return {"items": []}
                return {"items": [{"metadata": {"name": "retained-fixture"}}]}

            with patch.object(self.probe, "get", side_effect=get):
                with self.assertRaisesRegex(AssertionError, "previously used cluster"):
                    self.probe.prepare()
        self.assertEqual(command.call_count, 1)
        self.assertEqual(command.call_args.args[:3], ("kind", "get", "kubeconfig"))

    def test_existing_evidence_refused_before_cluster_access(self):
        (self.probe.root / "events.jsonl").write_text("retained")
        with patch.object(probe_module, "command") as command:
            with self.assertRaisesRegex(AssertionError, "already used"):
                self.probe.prepare()
        command.assert_not_called()
