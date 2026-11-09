"""Tool verification in scripts/verify-install-package.sh (PR #109 review 4513680560).

A cached Helm or kubectl in OWLMAST_TOOLS_DIR must never run as the qualified tool unless it is proven to be
the pinned artifact, and a platform other than linux-amd64 must fail clearly instead of downloading the
linux-amd64 binaries. `curl` and `uname` are replaced by stubs on PATH; no network is used. The positive
controls reuse the already verified tools of this run (OWLMAST_HELM's archive and OWLMAST_KUBECTL).
"""

import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "verify-install-package.sh"
HELM = os.environ.get("OWLMAST_HELM") or shutil.which("helm")
KUBECTL = os.environ.get("OWLMAST_KUBECTL")


def helm_archive():
    if not HELM:
        return None
    for name in ("helm.tar.gz", "helm-v4.3.1-linux-amd64.tar.gz"):
        candidate = Path(HELM).parent / name
        if candidate.exists():
            return candidate
    return None


class ToolVerificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="owlmast-tools."))
        self.tools = self.tmp / "tools"; self.tools.mkdir()
        self.bin = self.tmp / "bin"; self.bin.mkdir()
        self.marker = self.tmp / "impostor-ran"
        self.stub("curl", f'#!/usr/bin/env bash\necho "curl $*" >> "{self.tmp}/curl-calls"\nexit 22\n')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def stub(self, name, text, where=None):
        p = (where or self.bin) / name
        p.write_text(text); p.chmod(p.stat().st_mode | stat.S_IXUSR)
        return p

    def impostor(self, name, version_output):
        return self.stub(name, f'#!/usr/bin/env bash\ntouch "{self.marker}"\necho "{version_output}"\n', where=self.tools)

    def run_script(self, **env):
        base = {"PATH": f"{self.bin}:{os.environ['PATH']}", "HOME": os.environ.get("HOME", "/"), "OWLMAST_TOOLS_DIR": str(self.tools), "OWLMAST_VERIFY_TOOLS_ONLY": "1"}
        base.update(env)
        return subprocess.run(["bash", str(SCRIPT)], env=base, capture_output=True, text=True, timeout=120)

    def curl_calls(self):
        p = self.tmp / "curl-calls"
        return p.read_text().splitlines() if p.exists() else []

    def test_cached_helm_without_a_verified_archive_is_not_used(self):
        self.impostor("helm", "v4.3.1")
        r = self.run_script(OWLMAST_KUBECTL=KUBECTL or "/bin/true")
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(self.marker.exists(), "the unverified cached helm was executed")
        self.assertTrue(any("get.helm.sh" in c for c in self.curl_calls()))

    def test_cached_helm_next_to_a_tampered_archive_is_not_used(self):
        self.impostor("helm", "v4.3.1")
        (self.tools / "helm.tar.gz").write_bytes(b"not the pinned archive")
        r = self.run_script(OWLMAST_KUBECTL=KUBECTL or "/bin/true")
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(self.marker.exists())

    def test_cached_kubectl_with_a_wrong_checksum_is_not_used(self):
        if not HELM:
            self.fail("Helm 4 required (OWLMAST_HELM)")
        self.impostor("kubectl", "Client Version: v1.36.1")
        r = self.run_script(OWLMAST_HELM=HELM)
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(self.marker.exists(), "the unverified cached kubectl was executed")
        self.assertTrue(any("dl.k8s.io" in c for c in self.curl_calls()))

    def test_missing_tools_dir_is_created(self):
        archive = helm_archive()
        if archive is None or not KUBECTL:
            self.fail("the verified Helm archive next to OWLMAST_HELM and OWLMAST_KUBECTL are required")
        nested = self.tmp / "not" / "yet"
        r = self.run_script(OWLMAST_TOOLS_DIR=str(nested), OWLMAST_KUBECTL=KUBECTL)
        self.assertTrue(nested.is_dir())
        self.assertNotIn("No such file or directory", r.stderr)
        self.assertTrue(any("get.helm.sh" in c for c in self.curl_calls()))  # reached the download into the created directory

    def test_unsupported_platform_fails_clearly_without_downloading(self):
        self.stub("uname", '#!/usr/bin/env bash\ncase "$1" in -s) echo Linux ;; -m) echo aarch64 ;; *) echo Linux ;; esac\n')
        r = self.run_script()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("linux-amd64 only; this host is Linux-aarch64", r.stderr)
        self.assertIn("OWLMAST_HELM and OWLMAST_KUBECTL", r.stderr)
        self.assertEqual(self.curl_calls(), [])

    def test_verified_cache_is_reused_and_a_stale_binary_is_replaced_from_the_archive(self):
        archive = helm_archive()
        if archive is None or not KUBECTL:
            self.fail("the verified Helm archive next to OWLMAST_HELM and OWLMAST_KUBECTL are required for the positive control")
        shutil.copy(archive, self.tools / "helm.tar.gz")
        shutil.copy(KUBECTL, self.tools / "kubectl")
        self.impostor("helm", "v4.3.1")  # a stale cached binary next to the verified archive
        r = self.run_script()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.curl_calls(), [])  # nothing downloaded: both cached artifacts verified
        self.assertFalse(self.marker.exists(), "the stale cached helm was executed instead of the archive's")
        self.assertIn("v4.3.1", r.stdout)
        self.assertIn("Client Version: v1.36.1", r.stdout)


if __name__ == "__main__":
    unittest.main()
