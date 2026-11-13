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


# A python3 stub for the gates themselves: the environment's interpreter accepts the install (and, for the lint
# gate, puts a ruff there that reports the wrong version) and fails `pip check`, so each gate stops right after
# its environment was built. The EXIT trap must still remove that environment.
GATE_PYTHON3_STUB = r"""#!/usr/bin/env bash
echo "python3 $*" >> "$STUB_LOG"
if [ "$1 $2" = "-m venv" ]; then
  mkdir -p "$3/bin"
  cat > "$3/bin/python" <<'PY'
#!/usr/bin/env bash
echo "venv-python $*" >> "$STUB_LOG"
if [ "$3" = install ]; then
  bindir="$(dirname "$0")"
  printf '#!/usr/bin/env bash\necho "ruff 0.0.0-stub"\n' > "$bindir/ruff"; chmod +x "$bindir/ruff"
  exit 0
fi
exit 1
PY
  chmod +x "$3/bin/python"
  exit 0
fi
exit 1
"""


class GateCleanupTests(unittest.TestCase):
    """Review cycle 5: both gates remove the environment of their run on exit, also when they fail, and leave what
    another run keeps in a shared OWLMAST_TOOLS_DIR alone."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="owlmast-gate-cleanup."))
        self.tools = self.tmp / "tools"; self.tools.mkdir()
        self.other = self.tools / "deploy-tests-venv.other1"; self.other.mkdir()  # another run's environment
        (self.tools / "ruff-venv.other1").mkdir()
        self.bin = self.tmp / "bin"; self.bin.mkdir()
        self.log = self.tmp / "calls"
        stubs = {
            "python3": GATE_PYTHON3_STUB,
            "helm": '#!/usr/bin/env bash\necho "v4.3.1"\n',
            "kubectl": '#!/usr/bin/env bash\necho "Client Version: v1.36.1"\n',
            "shellcheck": '#!/usr/bin/env bash\necho "version: 0.11.0"\n',
        }
        for name, text in stubs.items():
            stub = self.bin / name
            stub.write_text(text); stub.chmod(stub.stat().st_mode | stat.S_IXUSR)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_gate(self, name):
        env = {"PATH": f"{self.bin}:{os.environ['PATH']}", "HOME": str(self.tmp), "STUB_LOG": str(self.log),
               "OWLMAST_TOOLS_DIR": str(self.tools), "OWLMAST_HELM": str(self.bin / "helm"),
               "OWLMAST_KUBECTL": str(self.bin / "kubectl"), "OWLMAST_SHELLCHECK": str(self.bin / "shellcheck")}
        return subprocess.run(["bash", str(REPO / "scripts" / name)], env=env, capture_output=True, text=True, timeout=60)

    def assert_cleaned(self, r, prefix):
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        created = [line.split()[-1] for line in self.log.read_text().splitlines() if line.startswith("python3 -m venv ")]
        self.assertEqual(len(created), 1, created)
        venv = Path(created[0])
        self.assertEqual(venv.parent, self.tools)
        self.assertTrue(venv.name.startswith(prefix + "."), venv)
        self.assertFalse(venv.exists(), "the run's environment was left behind")
        self.assertEqual(sorted(p.name for p in self.tools.iterdir()), ["deploy-tests-venv.other1", "ruff-venv.other1"])

    def test_the_deploy_test_gate_removes_its_environment_when_it_fails(self):
        self.assert_cleaned(self.run_gate("verify-install-package.sh"), "deploy-tests-venv")

    def test_the_lint_gate_removes_its_environment_when_it_fails(self):
        r = self.run_gate("verify-script-lint.sh")
        self.assertIn("is ruff 0.0.0-stub, not ruff", r.stderr)
        self.assert_cleaned(r, "ruff-venv")


if __name__ == "__main__":
    unittest.main()
