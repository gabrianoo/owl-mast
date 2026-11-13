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
# STUB_REACH_SUITE=1: `pip check` and `pip list` pass, so the deploy-test gate gets past `cd "$ROOT"` and fails in
# its suite instead.
# STUB_PIP_CHECK_FAILS=1 then fails `pip check` alone, and STUB_PIP_LIST_UNPINNED=1 lists no PyYAML/jsonschema.
if [ "${STUB_REACH_SUITE:-}" = 1 ]; then
  case "$3" in
    check) [ "${STUB_PIP_CHECK_FAILS:-}" = 1 ] && exit 1; exit 0 ;;
    list) if [ "${STUB_PIP_LIST_UNPINNED:-}" = 1 ]; then echo "pip==25.3"; else echo "PyYAML==6.0.3"; fi; exit 0 ;;
  esac
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
    """Review cycles 5 to 10: both gates remove what they create for their run on exit, also when they fail (the
    hashed environment, the directories the lint gate extracts shellcheck and the deploy-test gate extracts Helm
    into, and, when OWLMAST_TOOLS_DIR is unset, the scratch directories for the environment and for the Helm, kubectl
    and shellcheck downloads), remove nothing they did not create (a HASHED_VENV inherited from the caller), and
    leave what another run keeps in a shared OWLMAST_TOOLS_DIR alone (its environments, its extracted shellcheck and
    Helm directories, and a Helm binary an older version of the gate extracted there). A cached kubectl there is
    rewritten only when its checksum fails, and a first download into an empty shared directory is not guarded
    against a concurrent one."""

    def setUp(self):
        # Resolved: the gates resolve relative directories physically (R11-1), so every expected path is symlink-free.
        self.tmp = Path(tempfile.mkdtemp(prefix="owlmast-gate-cleanup.")).resolve()
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

    def run_gate(self, name, tools_dir=True, own_shellcheck=False, own_helm=False, own_kubectl=False, cwd=None, **extra):
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
        return subprocess.run(["bash", str(REPO / "scripts" / name)], env=env, capture_output=True, text=True, timeout=60, cwd=cwd)

    # The scratch directory each gate makes in TMPDIR for its environment when OWLMAST_TOOLS_DIR is unset.
    SCRATCH_PREFIX = {"deploy-tests-venv": "owlmast-deploy-tests.", "ruff-venv": "owlmast-lint."}

    def assert_cleaned(self, r, prefix, home=None):
        """The run failed, built exactly one environment, in `home` when given and otherwise in a scratch directory of
        its own directly under TMPDIR (R11-2, R11-3: an absolute path, never /tmp or a relative one), and removed it."""
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        created = [line.split()[-1] for line in self.log.read_text().splitlines() if line.startswith("python3 -m venv ")]
        self.assertEqual(len(created), 1, created)
        venv = Path(created[0])
        self.assertTrue(venv.is_absolute(), venv)
        if home is not None:
            self.assertEqual(venv.parent, home)
        else:
            self.assertEqual(venv.parent.parent, self.scratch, "the environment's scratch directory is not in TMPDIR")
            self.assertTrue(venv.parent.name.startswith(self.SCRATCH_PREFIX[prefix]), venv)
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

    def test_the_deploy_test_gate_never_removes_any_name_of_its_trap_that_it_inherited(self):
        """Review cycle 9 (R9-1): every name the EXIT trap removes, not only HASHED_VENV, is cleared before the trap is
        set. With OWLMAST_HELM and OWLMAST_KUBECTL supplied and OWLMAST_TOOLS_DIR set, the gate itself assigns none of
        RUN_HELM, SCRATCH_TOOLS and SCRATCH_HOME, so a value inherited from the caller would reach `rm -rf`."""
        trap = re.search(r"^trap '(.*)' EXIT$", (REPO / "scripts" / "verify-install-package.sh").read_text(), re.M).group(1)
        names = sorted(set(re.findall(r"\$\{(\w+):\+", trap)))
        self.assertEqual(names, ["HASHED_VENV", "RUN_HELM", "SCRATCH_HOME", "SCRATCH_TOOLS"])
        for name in names:
            for tools_only in (True, False):
                with self.subTest(name=name, tools_only=tools_only):
                    victim = self.tmp / f"callers-{name}"; victim.mkdir(exist_ok=True); (victim / "keep").write_text("x")
                    self.log.unlink(missing_ok=True)
                    extra = {name: str(victim)}
                    if tools_only:
                        extra["OWLMAST_VERIFY_TOOLS_ONLY"] = "1"
                    r = self.run_gate("verify-install-package.sh", **extra)
                    if tools_only:
                        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                        self.assert_tools_kept()
                    else:
                        self.assert_cleaned(r, "deploy-tests-venv", self.tools)
                    self.assertTrue((victim / "keep").exists(), f"the gate removed the caller's {name}")

    def test_a_relative_tools_directory_is_cleaned_up_after_the_gate_changes_into_the_repository(self):
        """Review cycle 9 (R9-2): run from another directory with a relative OWLMAST_TOOLS_DIR, the gate creates its
        Helm directory and environment under the absolute tools directory, and its trap still removes both after the
        suite (here a stub that fails) ran from $ROOT."""
        r = self.run_gate("verify-install-package.sh", own_helm=True, cwd=self.tmp, OWLMAST_TOOLS_DIR="tools", STUB_REACH_SUITE="1")
        self.assertIn("venv-python -m unittest", self.log.read_text(), "the stub suite was not reached")
        extracted = self.extracted()
        self.assertEqual(len(extracted), 1, extracted)
        self.assertEqual(extracted[0].parent, self.tools)  # absolute: resolved against the caller's directory
        self.assert_cleaned(r, "deploy-tests-venv", self.tools)

    def test_a_relative_tmpdir_is_cleaned_up_after_the_gate_changes_into_the_repository(self):
        """Review cycle 10 (R10-2): without OWLMAST_TOOLS_DIR, run from another directory with a relative TMPDIR, the
        gate makes its Helm download and environment scratch directories under the absolute TMPDIR, and its trap
        still removes both after the suite (a stub that fails) ran from $ROOT."""
        r = self.run_gate("verify-install-package.sh", tools_dir=False, own_helm=True, cwd=self.tmp,
                          TMPDIR=self.scratch.name, STUB_REACH_SUITE="1")
        self.assertIn("venv-python -m unittest", self.log.read_text(), "the stub suite was not reached")
        extracted = self.extracted()
        self.assertEqual(len(extracted), 1, extracted)
        self.assertEqual(extracted[0].parent.parent, self.scratch)  # absolute: resolved against the caller's directory
        self.assert_cleaned(r, "deploy-tests-venv")

    def test_the_lint_gate_never_removes_any_name_of_its_trap_that_it_inherited(self):
        """Review cycle 10 (R10-1): the lint gate clears RUN_TOOLS and SCRATCH_TOOLS before its EXIT trap, and
        scripts/hashed-venv.sh clears HASHED_VENV when sourced. With OWLMAST_SHELLCHECK supplied and OWLMAST_TOOLS_DIR
        set, the gate assigns neither RUN_TOOLS nor SCRATCH_TOOLS, and with OWLMAST_RUFF supplied it never calls
        hashed_venv, so a value inherited from the caller would reach `rm -rf`."""
        trap = re.search(r"^trap '(.*)' EXIT$", (REPO / "scripts" / "verify-script-lint.sh").read_text(), re.M).group(1)
        names = sorted(set(re.findall(r"\$\{(\w+):\+", trap)))
        self.assertEqual(names, ["HASHED_VENV", "RUN_TOOLS", "SCRATCH_TOOLS"])
        for name in names:
            for own_ruff in (False, True):
                with self.subTest(name=name, own_ruff=own_ruff):
                    victim = self.tmp / f"callers-{name}"; victim.mkdir(exist_ok=True); (victim / "keep").write_text("x")
                    self.log.unlink(missing_ok=True)
                    extra = {name: str(victim)}
                    if own_ruff:
                        extra["OWLMAST_RUFF"] = str(self.tmp / "no-ruff")
                    r = self.run_gate("verify-script-lint.sh", **extra)
                    self.assertRegex(r.stderr, r", not ruff ", r.stdout + r.stderr)
                    if own_ruff:
                        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
                        self.assertNotIn("-m venv", self.log.read_text() if self.log.exists() else "")
                        self.assert_tools_kept()
                        self.assertEqual(list(self.scratch.iterdir()), [])
                    else:
                        self.assert_cleaned(r, "ruff-venv", self.tools)
                    self.assertTrue((victim / "keep").exists(), f"the lint gate removed the caller's {name}")

    def test_without_a_tools_directory_the_lint_gate_leaves_nothing_in_tmpdir(self):
        """Review cycle 11 (R11-3): the shellcheck download and the ruff environment go to one scratch directory of the
        run directly under TMPDIR, which the gate removes on exit."""
        r = self.run_gate("verify-script-lint.sh", tools_dir=False, own_shellcheck=True)
        self.assertIn("is ruff 0.0.0-stub, not ruff", r.stderr)
        extracted = self.extracted()
        self.assertEqual(len(extracted), 1, extracted)
        self.assertEqual(extracted[0].parent.parent, self.scratch, extracted)
        self.assertTrue(extracted[0].parent.name.startswith("owlmast-lint."), extracted)
        self.assert_cleaned(r, "ruff-venv")
        venv = Path(next(line.split()[-1] for line in self.log.read_text().splitlines() if line.startswith("python3 -m venv ")))
        self.assertEqual(venv.parent, extracted[0].parent, "the environment and the download use different scratch directories")

    def test_a_path_through_a_symlink_and_dot_dot_is_resolved_to_the_directory_the_kernel_reaches(self):
        """Review cycle 11 (R11-1): `link/../dir`, with `link` a symlink, names the sibling of the link's target, as for
        mkdir, [ -d ] and mktemp; a logical `cd` would name `dir` next to the link instead. Both relative variables are
        resolved physically, and the decoy next to the link is never used."""
        caller = self.tmp / "caller"; caller.mkdir()
        (caller / "link").symlink_to(self.bin)  # link/.. is self.tmp
        for decoy in ("tools", "tmpdir"):
            (caller / decoy).mkdir()
        r = self.run_gate("verify-install-package.sh", own_helm=True, cwd=caller, OWLMAST_TOOLS_DIR="link/../tools")
        extracted = self.extracted()
        self.assertEqual(len(extracted), 1, extracted)
        self.assertEqual(extracted[0].parent, self.tools)
        self.assert_cleaned(r, "deploy-tests-venv", self.tools)
        self.log.unlink()
        r = self.run_gate("verify-install-package.sh", tools_dir=False, own_helm=True, cwd=caller, TMPDIR="link/../tmpdir")
        extracted = self.extracted()
        self.assertEqual(len(extracted), 1, extracted)
        self.assertEqual(extracted[0].parent.parent, self.scratch)
        self.assert_cleaned(r, "deploy-tests-venv")
        self.assertEqual(sorted(p.name for p in caller.iterdir()), ["link", "tmpdir", "tools"])
        for decoy in ("tools", "tmpdir"):
            self.assertEqual(list((caller / decoy).iterdir()), [], f"the gate used the decoy {decoy} next to the link")

    def test_a_relative_tmpdir_that_does_not_exist_is_left_as_given_when_no_scratch_directory_is_needed(self):
        """Review cycle 11 (R11-4): with OWLMAST_TOOLS_DIR set the gate makes nothing in TMPDIR, so a relative TMPDIR
        that does not exist must not stop it: it builds its environment in the tools directory as usual."""
        r = self.run_gate("verify-install-package.sh", cwd=self.tmp, TMPDIR="does-not-exist")
        self.assertNotIn("does-not-exist", r.stderr)
        self.assert_cleaned(r, "deploy-tests-venv", self.tools)
        self.assertFalse((self.tmp / "does-not-exist").exists())

    def test_the_deploy_test_gate_checks_its_environment_before_the_suite(self):
        """Review cycle 11 (R11-5): the environment is installed with --no-deps, so `pip check` is what proves the
        hashed set complete and consistent, and `pip list` that PyYAML and jsonschema are in it. Each runs before the
        suite, and each failing alone stops the gate before the suite runs, with its environment removed."""
        r = self.run_gate("verify-install-package.sh", STUB_REACH_SUITE="1")
        calls = [line.split(" ", 1)[1] for line in self.log.read_text().splitlines() if line.startswith("venv-python ")]
        steps = [c for c in calls if c.startswith(("-m pip check", "-m pip list", "-m unittest"))]
        self.assertEqual([" ".join(c.split()[:3]) for c in steps], ["-m pip check", "-m pip list", "-m unittest discover"], calls)
        self.assert_cleaned(r, "deploy-tests-venv", self.tools)
        for stub, step in (("STUB_PIP_CHECK_FAILS", "-m pip check"), ("STUB_PIP_LIST_UNPINNED", "-m pip list")):
            with self.subTest(stub=stub):
                self.log.unlink()
                r = self.run_gate("verify-install-package.sh", STUB_REACH_SUITE="1", **{stub: "1"})
                log = self.log.read_text()
                self.assertIn(f"venv-python {step}", log)
                self.assertNotIn("venv-python -m unittest", log, f"the suite ran although {step} failed")
                self.assert_cleaned(r, "deploy-tests-venv", self.tools)


if __name__ == "__main__":
    unittest.main()
