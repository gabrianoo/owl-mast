"""The per-run Python environment of the deploy-test and lint gates (scripts/hashed-venv.sh, review 5884955290 R4-8).

Review cycle 3 found that a reused environment can run code no pinned distribution owns (a .pth file,
sitecustomize, a changed pip); cycle 4 that a fixed path lets two runs sharing OWLMAST_TOOLS_DIR delete each
other's environment, and that an sdist build fetches its build dependencies without hash checks. `python3` is a
stub on PATH that creates the environment's `bin/python` and records every call; no network is used.
"""

import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HELPER = REPO / "scripts" / "hashed-venv.sh"

PYTHON3_STUB = r"""#!/usr/bin/env bash
echo "python3 $*" >> "$STUB_LOG"
if [ "$1 $2" = "-m venv" ]; then
  [ "${STUB_VENV_FAILS:-}" = 1 ] && exit 1
  mkdir -p "$3/bin"
  printf '#!/usr/bin/env bash\necho "venv-python $*" >> "$STUB_LOG"\n' > "$3/bin/python"
  chmod +x "$3/bin/python"
  exit 0
fi
exit 1
"""


class HashedVenvTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="owlmast-hashed-venv."))
        self.home = self.tmp / "tools"; self.home.mkdir()
        self.bin = self.tmp / "bin"; self.bin.mkdir()
        self.log = self.tmp / "calls"
        stub = self.bin / "python3"
        stub.write_text(PYTHON3_STUB); stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
        # An environment an earlier run left at the old fixed path, with code that no distribution owns.
        planted = self.home / "deploy-tests-venv" / "lib" / "site-packages"
        planted.mkdir(parents=True)
        (planted / "owned-by-nobody.pth").write_text("import os; os.system('touch ran')\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_helper(self, then="", **env):
        script = f'set -euo pipefail; . "{HELPER}"; hashed_venv "{self.home}" deploy-tests-venv reqs.txt; echo "$HASHED_VENV"; {then}'
        base = {"PATH": f"{self.bin}:{os.environ['PATH']}", "STUB_LOG": str(self.log)}
        base.update(env)
        return subprocess.run(["bash", "-c", script], env=base, capture_output=True, text=True, timeout=60)

    def test_every_call_gets_a_new_environment_and_leaves_other_ones_alone(self):
        first, second = self.run_helper(), self.run_helper()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        a, b = Path(first.stdout.strip()), Path(second.stdout.strip())
        self.assertNotEqual(a, b)
        for venv in (a, b):
            self.assertEqual(venv.parent, self.home)
            self.assertRegex(venv.name, r"^deploy-tests-venv\.[A-Za-z0-9]{6}$")
            self.assertEqual(sorted(p.name for p in venv.iterdir()), ["bin"])  # nothing an earlier run left
        # Neither the earlier environment nor the other run's is deleted.
        self.assertTrue((self.home / "deploy-tests-venv" / "lib" / "site-packages" / "owned-by-nobody.pth").exists())
        self.assertTrue(a.exists())

    def test_the_install_is_hash_checked_wheels_only_and_without_dependencies(self):
        r = self.run_helper()
        self.assertEqual(r.returncode, 0, r.stderr)
        venv = r.stdout.strip()
        calls = self.log.read_text().splitlines()
        self.assertEqual(calls[0], f"python3 -m venv {venv}")
        self.assertEqual(len(calls), 2, calls)
        install = calls[1].split()
        self.assertEqual(install[:4], ["venv-python", "-m", "pip", "install"])
        for flag in ("--require-hashes", "--no-deps"):
            self.assertIn(flag, install)
        self.assertIn(":all:", install)
        self.assertEqual(install[install.index(":all:") - 1], "--only-binary")
        self.assertEqual(install[install.index("-r") + 1], "reqs.txt")

    def test_a_failed_step_stops_the_caller(self):
        r = self.run_helper(then="echo reached", STUB_VENV_FAILS="1")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("reached", r.stdout)

    def test_both_gates_use_the_helper_and_build_no_environment_of_their_own(self):
        for name in ("verify-install-package.sh", "verify-script-lint.sh"):
            text = (REPO / "scripts" / name).read_text()
            self.assertIn('. "$ROOT/scripts/hashed-venv.sh"', text, name)
            self.assertIn("hashed_venv ", text, name)
            self.assertNotIn("-m venv", text, name)
            self.assertNotIn("pip install", text, name)


if __name__ == "__main__":
    unittest.main()
