"""Test package. The activation use ledger is a fixed directory per user account and machine in
production (``activation.ledger_root``); the suite replaces it with a directory beside each test's
own activation file, so tests never write to the home directory and never see each other's records
(most of them create runs from byte-identical documents). A test of the cross-copy rule puts both
copies on one shared root explicitly (``test_pr114_round3_findings``).

The override must hold however the tests are loaded: :func:`install_test_ledger` is idempotent and
is called here and by every ``LiveHarness`` (the one way the suite creates live runs), and the
production function is captured exactly once, so this module running again under another package
name (``tests`` as well as ``automation.tests``) can never record the override as "production"."""

from pathlib import Path

from automation.unattended import activation as _activation


def _test_ledger_root(source_path: str) -> Path:
    return Path(source_path).resolve().parent / ".activation-ledger"


_test_ledger_root.is_test_ledger = True  # how a second copy of this module recognizes the override already in force


def _production(current):
    return getattr(current, "production", current) if getattr(current, "is_test_ledger", False) else current


PRODUCTION_LEDGER_ROOT = _production(_activation.ledger_root)  # kept for the one test that checks the production rule itself
_test_ledger_root.production = PRODUCTION_LEDGER_ROOT


def install_test_ledger() -> None:
    """Put the per-test ledger root in force (again) unless a test has patched in its own."""
    if not getattr(_activation.ledger_root, "is_test_ledger", False) and _activation.ledger_root is PRODUCTION_LEDGER_ROOT:
        _activation.ledger_root = _test_ledger_root


install_test_ledger()
