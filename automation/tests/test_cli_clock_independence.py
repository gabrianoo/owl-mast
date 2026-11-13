"""OM-01.02 repair round 1: the CLI scenarios of the enabling repairs decide on injected
observations, never on the host clock. The five scenarios that read the wall clock through the
CLI (``R1MissingRunMetadataTests.check``, ``F3StatusUnderTheSharedGateTests
.test_cli_status_records_the_observed_stop`` and ``Final1StaleCreationObjectTests
.test_cli_creation_with_an_altered_source_refuses_without_state_or_calls``) are re-run here with
the host clock simulated before, inside, just after and years after the fixture activation window
(``expires_at`` 2026-11-07T14:00:00Z). Every run must succeed identically: the only clock the
production code reads for those decisions is the one the tests inject through
``controlled_cli_clock``. Nothing in production is modified; the host clock is simulated by
patching the ``datetime`` name ``state.utcnow`` reads, within this test only."""

from __future__ import annotations

import io
import unittest
from datetime import datetime
from unittest import mock

from automation.tests import test_enabling_repair_1, test_enabling_repair_2, test_enabling_repair_3, test_upgrade_replay_findings
from automation.unattended import state as state_module

HOST_CLOCKS = ("2026-11-07T09:00:00Z", "2026-11-07T13:59:59Z", "2026-11-07T14:00:01Z", "2026-11-08T00:00:00Z", "2031-01-01T00:00:00Z")
SCENARIOS = (
    (test_enabling_repair_1.R1MissingRunMetadataTests, None),
    (test_enabling_repair_2.F3StatusUnderTheSharedGateTests, "test_cli_status_records_the_observed_stop"),
    (test_enabling_repair_3.Final1StaleCreationObjectTests, "test_cli_creation_with_an_altered_source_refuses_without_state_or_calls"),
)


def _fixed_host_clock(text: str):
    instant = datetime.fromisoformat(text.replace("Z", "+00:00"))

    class FixedHostClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant if tz is None else instant.astimezone(tz)

    return FixedHostClock


class CliClockIndependenceTests(unittest.TestCase):
    def test_the_cli_scenarios_pass_identically_under_every_simulated_host_clock(self):
        for host in HOST_CLOCKS:
            with mock.patch.object(state_module, "datetime", _fixed_host_clock(host)):
                self.assertEqual(state_module.utcnow(), host)  # the simulated host clock is what the production default would read
                for case, name in SCENARIOS:
                    suite = unittest.TestLoader().loadTestsFromName(name, case) if name else unittest.TestLoader().loadTestsFromTestCase(case)
                    out = io.StringIO()
                    result = unittest.TextTestRunner(stream=out, verbosity=0).run(suite)
                    self.assertTrue(result.wasSuccessful(), f"host clock {host}, {case.__name__}.{name or '*'}:\n{out.getvalue()}")
                    self.assertGreater(result.testsRun, 0)

    def test_the_committed_legacy_matrix_passes_under_a_host_clock_past_its_wall_clock_budget(self):
        """The committed legacy fixtures started at 2026-11-07T12:06Z with a 240-minute budget; the
        upgraded coordinator must observe the scenario's own instant, so the matrix passes identically
        with the host clock years later."""
        for host in ("2026-11-07T17:00:00Z", "2031-01-01T00:00:00Z"):
            with mock.patch.object(state_module, "datetime", _fixed_host_clock(host)):
                suite = unittest.TestLoader().loadTestsFromName("test_full_matrix_on_committed_fixtures", test_upgrade_replay_findings.CommittedLegacyFixturesTests)
                out = io.StringIO()
                result = unittest.TextTestRunner(stream=out, verbosity=0).run(suite)
                self.assertTrue(result.wasSuccessful(), f"host clock {host}:\n{out.getvalue()[-3000:]}")

    def test_without_injection_the_host_clock_decides(self):
        """Control: the production default really reads the host clock, so the injection above is what makes the scenarios deterministic."""
        for host in ("2026-11-07T09:00:00Z", "2031-01-01T00:00:00Z"):
            with mock.patch.object(state_module, "datetime", _fixed_host_clock(host)):
                from automation.unattended.coordinator import Coordinator
                import inspect
                self.assertEqual(inspect.signature(Coordinator.__init__).parameters["now"].default(), host)


if __name__ == "__main__":
    unittest.main()
