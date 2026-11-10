"""Test package. The activation use ledger is a fixed per-machine directory in production
(``activation.ledger_root``); the suite replaces it with a directory beside each test's own
activation file, so tests never write to the home directory and never see each other's records
(most of them create runs from byte-identical documents)."""

from pathlib import Path

from automation.unattended import activation as _activation


def _test_ledger_root(source_path: str) -> Path:
    return Path(source_path).resolve().parent / ".activation-ledger"


PRODUCTION_LEDGER_ROOT = _activation.ledger_root  # kept for the one test that checks the production rule itself
_activation.ledger_root = _test_ledger_root
