"""The per-run Python environment of the deploy-test and lint gates (scripts/hashed-venv.sh, review 5884955290 R4-8).

Review cycle 3 found that a reused environment can run code no pinned distribution owns (a .pth file,
sitecustomize, a changed pip); cycle 4 that a fixed path lets two runs sharing OWLMAST_TOOLS_DIR delete each
other's environment, and that an sdist build fetches its build dependencies without hash checks. `python3` is a
stub on PATH that creates the environment's `bin/python` and records every call; no network is used.
"""

import os
import re
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


# For the gates' own downloads (no OWLMAST_SHELLCHECK, OWLMAST_HELM or OWLMAST_KUBECTL): a linux-x86_64 host, files
# that pass the checksum, and a tar that extracts the archive's last named member (shellcheck or helm, reporting the
# pinned version) into the directory given by -C. No kubectl is ever written, so a kubectl download stops the gate.
DOWNLOAD_STUBS = {
    "uname": '#!/usr/bin/env bash\ncase "$1" in -s) echo Linux ;; -m) echo x86_64 ;; *) echo Linux ;; esac\n',
    "sha256sum": '#!/usr/bin/env bash\ncat >/dev/null; exit 0\n',
    "tar": '#!/usr/bin/env bash\necho "tar $*" >> "$STUB_LOG"\nwhile [ $# -gt 0 ]; do [ "$1" = -C ] && dir="$2"; member="$1"; shift; done\n'
           'name="$(basename "$member")"; case "$name" in helm) out=v4.3.1 ;; *) out="version: 0.11.0" ;; esac\n'
           'printf \'#!/usr/bin/env bash\\necho "%s"\\n\' "$out" > "$dir/$name"; chmod +x "$dir/$name"\n',
    "curl": '#!/usr/bin/env bash\necho "curl must not be called" >&2; exit 1\n',
}


class GateCleanupTests(unittest.TestCase):
    """Review cycles 5 to 8: both gates remove what they create for their run on exit, also when they fail (the
    hashed environment, the directories the lint gate extracts shellcheck and the deploy-test gate extracts Helm
    into, and, when OWLMAST_TOOLS_DIR is unset, the scratch directories for the environment and for the Helm, kubectl
    and shellcheck downloads), remove nothing they did not create (a HASHED_VENV inherited from the caller), and
    leave what another run keeps in a shared OWLMAST_TOOLS_DIR alone (its environments, its extracted shellcheck and
    Helm directories, and a Helm binary an older version of the gate extracted there). A cached kubectl there is
    rewritten only when its checksum fails, and a first download into an empty shared directory is not guarded
    against a concurrent one."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="owlmast-gate-cleanup."))
        self.tools = self.tmp / "tools"; self.tools.mkdir()
        self.kept = ["deploy-tests-venv.other1", "helm", "helm.other1", "ruff-venv.other1", "shellcheck.other1"]  # another run's entries
        for name in self.kept:
            if name == "helm":
                (self.tools / name).write_text("another run's helm\n")
            else:
                (self.tools / name).mkdir()
        self.scratch = self.tmp / "tmpdir"; self.scratch.mkdir()  # TMPDIR of the gate
        self.bin = self.tmp / "bin"; self.bin.mkdir()
        self.download_bin = self.tmp / "download-bin"; self.download_bin.mkdir()
        self.log = self.tmp / "calls"
        stubs = {
            "python3": GATE_PYTHON3_STUB,
            "helm": '#!/usr/bin/env bash\necho "v4.3.1"\n',
            "kubectl": '#!/usr/bin/env bash\necho "Client Version: v1.36.1"\n',
            "shellcheck": '#!/usr/bin/env bash\necho "version: 0.11.0"\n',
        }
        for directory, texts in ((self.bin, stubs), (self.download_bin, DOWNLOAD_STUBS)):
            for name, text in texts.items():
                stub = directory / name
                stub.write_text(text); stub.chmod(stub.stat().st_mode | stat.S_IXUSR)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_gate(self, name, tools_dir=True, own_shellcheck=False, own_helm=False, own_kubectl=False, **extra):
        path = f"{self.bin}:{os.environ['PATH']}"
        downloads = own_shellcheck or own_helm or own_kubectl
        env = {"PATH": f"{self.download_bin}:{path}" if downloads else path, "HOME": str(self.tmp), "STUB_LOG": str(self.log),
               "TMPDIR": str(self.scratch)}
        if tools_dir:
            env["OWLMAST_TOOLS_DIR"] = str(self.tools)
        if not own_shellcheck:
            env["OWLMAST_SHELLCHECK"] = str(self.bin / "shellcheck")
        if not own_helm:
            env["OWLMAST_HELM"] = str(self.bin / "helm")
        if not own_kubectl:
            env["OWLMAST_KUBECTL"] = str(self.bin / "kubectl")
        env.update(extra)
        return subprocess.run(["bash", str(REPO / "scripts" / name)], env=env, capture_output=True, text=True, timeout=60)

    def assert_cleaned(self, r, prefix, home=None):
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        created = [line.split()[-1] for line in self.log.read_text().splitlines() if line.startswith("python3 -m venv ")]
        self.assertEqual(len(created), 1, created)
        venv = Path(created[0])
        if home is not None:
            self.assertEqual(venv.parent, home)
        self.assertTrue(venv.name.startswith(prefix + "."), venv)
        self.assertFalse(venv.exists(), "the run's environment was left behind")
        self.assert_tools_kept()
        self.assertEqual(list(self.scratch.iterdir()), [], "the run left a scratch directory in TMPDIR")

    def assert_tools_kept(self):
        self.assertEqual(sorted(p.name for p in self.tools.iterdir()), self.kept)
        self.assertEqual((self.tools / "helm").read_text(), "another run's helm\n")

    def extracted(self):
        return [Path(line.split()[line.split().index("-C") + 1]) for line in self.log.read_text().splitlines() if line.startswith("tar ")]

    def assert_failed_at_kubectl_in_scratch(self, r):
        """The stubbed download writes no kubectl, so the gate stops at its chmod; the path shows which directory the
        kubectl branch used."""
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertRegex(r.stderr, rf"chmod: .*{re.escape(str(self.scratch))}/owlmast-tools\.[^/]+/kubectl")
        self.assertNotIn("python3 -m venv", self.log.read_text() if self.log.exists() else "")
        self.assertEqual(list(self.scratch.iterdir()), [], "the run left its download directory in TMPDIR")

    def test_the_deploy_test_gate_removes_its_environment_when_it_fails(self):
        self.assert_cleaned(self.run_gate("verify-install-package.sh"), "deploy-tests-venv", self.tools)

    def test_the_lint_gate_removes_its_environment_when_it_fails(self):
        r = self.run_gate("verify-script-lint.sh")
        self.assertIn("is ruff 0.0.0-stub, not ruff", r.stderr)
        self.assert_cleaned(r, "ruff-venv", self.tools)

    def test_the_lint_gate_removes_the_shellcheck_it_extracted_for_its_run(self):
        r = self.run_gate("verify-script-lint.sh", own_shellcheck=True)
        self.assertIn("is ruff 0.0.0-stub, not ruff", r.stderr)
        extracted = [line.split()[line.split().index("-C") + 1] for line in self.log.read_text().splitlines() if line.startswith("tar ")]
        self.assertEqual(len(extracted), 1, extracted)
        self.assertEqual(Path(extracted[0]).parent, self.tools)
        self.assertTrue(Path(extracted[0]).name.startswith("shellcheck."), extracted)
        self.assert_cleaned(r, "ruff-venv", self.tools)

    def test_without_a_tools_directory_the_deploy_test_gate_leaves_nothing_in_tmpdir(self):
        self.assert_cleaned(self.run_gate("verify-install-package.sh", tools_dir=False), "deploy-tests-venv")

    def test_without_a_tools_directory_the_deploy_test_gate_removes_its_helm_download(self):
        """Review cycle 7 (R7-1): without OWLMAST_TOOLS_DIR and OWLMAST_HELM the Helm archive and binary go to a
        scratch directory in TMPDIR, which the gate removes on exit like its environment."""
        r = self.run_gate("verify-install-package.sh", tools_dir=False, own_helm=True)
        extracted = self.extracted()
        self.assertEqual(len(extracted), 1, extracted)
        self.assertEqual(extracted[0].parent.parent, self.scratch)
        self.assertTrue(extracted[0].parent.name.startswith("owlmast-tools."), extracted)
        self.assertTrue(extracted[0].name.startswith("helm."), extracted)
        self.assert_cleaned(r, "deploy-tests-venv")

    def test_without_a_tools_directory_the_deploy_test_gate_removes_its_kubectl_download_when_it_fails(self):
        """Review cycle 7 (R7-1): the kubectl download uses the same scratch directory, and a failure there (the stub
        writes no kubectl) still leaves nothing in TMPDIR."""
        r = self.run_gate("verify-install-package.sh", tools_dir=False, own_helm=True, own_kubectl=True)
        self.assertEqual(self.extracted()[0].parent / "kubectl",
                         Path(re.search(r"chmod: .*'([^']+)'", r.stderr).group(1)), r.stderr)  # the Helm download's directory
        self.assert_failed_at_kubectl_in_scratch(r)

    def test_without_a_tools_directory_the_deploy_test_gate_removes_a_kubectl_only_download(self):
        """Review cycle 8 (R8-2): with OWLMAST_HELM supplied, the kubectl branch creates the scratch directory itself,
        and the gate still removes it."""
        self.assert_failed_at_kubectl_in_scratch(self.run_gate("verify-install-package.sh", tools_dir=False, own_kubectl=True))

    def test_the_deploy_test_gate_extracts_helm_for_its_run_and_leaves_another_runs_helm_alone(self):
        """Review cycle 8 (R8-3): in a shared OWLMAST_TOOLS_DIR, Helm is extracted into a directory of this run, which
        is removed on exit; another run's binary and directory there are not touched."""
        r = self.run_gate("verify-install-package.sh", own_helm=True)
        extracted = self.extracted()
        self.assertEqual(len(extracted), 1, extracted)
        self.assertEqual(extracted[0].parent, self.tools)
        self.assertTrue(extracted[0].name.startswith("helm."), extracted)
        self.assertNotEqual(extracted[0].name, "helm.other1")
        self.assert_cleaned(r, "deploy-tests-venv", self.tools)

    def test_the_deploy_test_gate_never_removes_a_hashed_venv_it_inherited(self):
        """Review cycle 8 (R8-1): the EXIT trap is set before the helper is sourced, so a HASHED_VENV exported by the
        caller must not be removed, neither on the tools-only exit nor on a run that fails after building its own."""
        victim = self.tmp / "callers-venv"; victim.mkdir(); (victim / "keep").write_text("x")
        r = self.run_gate("verify-install-package.sh", HASHED_VENV=str(victim), OWLMAST_VERIFY_TOOLS_ONLY="1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((victim / "keep").exists(), "the tools-only exit removed the caller's HASHED_VENV")
        self.assert_tools_kept()
        r = self.run_gate("verify-install-package.sh", HASHED_VENV=str(victim))
        self.assert_cleaned(r, "deploy-tests-venv", self.tools)
        self.assertTrue((victim / "keep").exists(), "the failing run removed the caller's HASHED_VENV")

    def test_without_a_tools_directory_the_lint_gate_leaves_nothing_in_tmpdir(self):
        r = self.run_gate("verify-script-lint.sh", tools_dir=False, own_shellcheck=True)
        self.assertIn("is ruff 0.0.0-stub, not ruff", r.stderr)
        self.assert_cleaned(r, "ruff-venv")


if __name__ == "__main__":
    unittest.main()
