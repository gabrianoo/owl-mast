"""Unattended execution foundation: GitHub-authoritative dispatch, synchronization and
T3 coordination policy for Owl Mast engineering work.

The package has no third-party dependencies. GitHub access goes through the ``gh`` CLI
session (``github.GhCliTransport``); nothing here reads or stores credentials.
"""

__all__ = ["__version__"]
__version__ = "0.1.0"
