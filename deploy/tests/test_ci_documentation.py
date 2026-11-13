"""E01 retrospective T1-T4, P3 (E01-R-07, E01-R-11): the CI description, the runner pin and the pinned Python
dependencies drifted from the workflow without any check. These tests read the workflow and the documents;
they need no Helm, cluster or network."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"
DEVELOPMENT = REPO / "docs" / "development.md"
QUALIFIED_RUNNER = "ubuntu-26.04"


def workflow_jobs() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]


class DevelopmentDocumentTest(unittest.TestCase):
    def test_the_documented_ci_jobs_are_exactly_the_jobs_of_the_workflow(self):
        section = DEVELOPMENT.read_text(encoding="utf-8").split("## Continuous integration", 1)[1].split("\n## ", 1)[0]
        documented = re.findall(r"(?m)^\d+\. `([a-z0-9-]+)`:", section)
        self.assertEqual(len(documented), len(set(documented)), documented)
        self.assertEqual(sorted(documented), sorted(workflow_jobs()))

    def test_every_job_runs_on_the_qualified_fixed_runner(self):
        for name, job in workflow_jobs().items():
            self.assertEqual(job.get("runs-on"), QUALIFIED_RUNNER, name)
        self.assertNotRegex(WORKFLOW.read_text(encoding="utf-8"), r"(?m)^\s*(runs-on|os):.*-latest")

    def test_no_document_names_a_floating_runner_as_the_ci_runner(self):
        for path in [REPO / "README.md", *sorted((REPO / "docs").glob("*.md")), REPO / "gradle" / "gradle-daemon-jvm.properties"]:
            self.assertNotIn("ubuntu-latest", path.read_text(encoding="utf-8"), path.name)
        self.assertIn(QUALIFIED_RUNNER, DEVELOPMENT.read_text(encoding="utf-8"))

    def test_every_script_a_ci_job_runs_is_listed_in_the_commands_table(self):
        document = DEVELOPMENT.read_text(encoding="utf-8")
        ran = set(re.findall(r"scripts/[a-z0-9-]+\.(?:sh|py)", WORKFLOW.read_text(encoding="utf-8")))
        self.assertTrue(ran)
        for script in sorted(ran):
            self.assertIn(f"`{script}", document, script)
            self.assertTrue((REPO / script).is_file(), script)


class PinnedPythonDependenciesTest(unittest.TestCase):
    """The deploy suite's and the linter's Python dependencies are exact versions with hashes, and no script installs a range."""

    def pins(self, path: Path) -> dict:
        text = path.read_text(encoding="utf-8")
        entries = re.findall(r"(?m)^([A-Za-z0-9_.-]+)==([^\s\;]+)", text)
        self.assertTrue(entries, path)
        for name, _ in entries:
            block = text.split(f"{name}==", 1)[1].split("\n\n", 1)[0]
            following = re.split(r"(?m)^[A-Za-z0-9_.-]+==", block, maxsplit=1)[0]
            self.assertIn("--hash=sha256:", following, f"{path.name}: {name} carries no hash")
        return {name.lower(): version for name, version in entries}

    def test_the_deploy_test_requirements_pin_the_direct_dependencies_with_hashes(self):
        direct = dict(re.findall(r"(?m)^([A-Za-z0-9_.-]+)==(\S+)$", (REPO / "deploy" / "tests" / "requirements.in").read_text(encoding="utf-8")))
        self.assertEqual(sorted(name.lower() for name in direct), ["jsonschema", "pyyaml"])
        pinned = self.pins(REPO / "deploy" / "tests" / "requirements.txt")
        for name, version in direct.items():
            self.assertEqual(pinned[name.lower()], version, name)

    def test_the_linter_is_pinned_with_hashes(self):
        self.assertEqual(list(self.pins(REPO / "scripts" / "lint-requirements.txt")), ["ruff"])

    INSTALL = re.compile(r"\b(?:pip[0-9.]*|pipx|uv(?:\s+pip)?)\s+install\b")

    def test_no_script_or_workflow_installs_an_unpinned_python_package(self):
        found = 0
        for path in [*sorted((REPO / "scripts").glob("*.sh")), WORKFLOW]:
            # a command continued with a backslash is one command
            text = re.sub(r"\\\n\s*", " ", path.read_text(encoding="utf-8"))
            for line in text.splitlines():
                if line.lstrip().startswith("#"):
                    continue
                if path.name == "hashed-venv.sh" and self.INSTALL.search(line):
                    # the one install of the shared helper: hashed, wheels only, from the file its caller names
                    self.assertIn("--require-hashes", line)
                    self.assertIn("--only-binary :all:", line)
                    self.assertRegex(line, r'-r "\$requirements"')
                elif self.INSTALL.search(line):
                    found += 1
                    self.assertIn("--require-hashes", line, f"{path.name}: {line.strip()}")
                    self.assertRegex(line, r"-r \S*requirements\.txt|-r \"\$REQUIREMENTS\"", f"{path.name}: {line.strip()}")
                elif re.search(r"^\s*hashed_venv\s", line):  # a caller of the helper (review 5884955290 R4-8)
                    found += 1
                    self.assertRegex(line, r"\s(\S*requirements\.txt|\"\$REQUIREMENTS\")$", f"{path.name}: {line.strip()}")
        self.assertGreaterEqual(found, 2, "the deploy suite and the linter each install their pinned set")

    def test_the_install_pattern_recognises_the_usual_spellings(self):
        for line in ("python3 -m pip install x", "pip3 install x", "pip3.12 install x", "pipx install x", "uv pip install x", "uv install x"):
            self.assertRegex(line, self.INSTALL, line)
        self.assertNotRegex("helm upgrade --install owl-mast", self.INSTALL)


class GradleWrapperDocumentTest(unittest.TestCase):
    """Retro T1: the wrapper moved to another Gradle version while the README, the toolchain document and the wrapper jar
    stayed behind. One version and one pair of checksums must be stated everywhere."""

    def setUp(self):
        properties = (REPO / "gradle" / "wrapper" / "gradle-wrapper.properties").read_text(encoding="utf-8")
        self.version = re.search(r"distributions/gradle-([0-9.]+)-bin\.zip", properties).group(1)
        self.distribution_sha = re.search(r"(?m)^distributionSha256Sum=([0-9a-f]{64})$", properties).group(1)
        self.toolchain = (REPO / "docs" / "toolchain-qualification.md").read_text(encoding="utf-8")
        self.pin_row = next(line for line in self.toolchain.splitlines() if line.startswith("| Gradle |"))

    def test_the_readme_and_the_toolchain_document_name_the_wrapper_version(self):
        self.assertIn(f"Gradle {self.version} with Kotlin DSL", (REPO / "README.md").read_text(encoding="utf-8"))
        self.assertIn(f"{self.version} wrapper", self.pin_row)
        self.assertIn(f"\nGradle {self.version}\n", self.toolchain, "the recorded `./gradlew --version` output")

    def test_the_documented_checksums_are_the_ones_in_the_checkout(self):
        import hashlib
        jar_sha = hashlib.sha256((REPO / "gradle" / "wrapper" / "gradle-wrapper.jar").read_bytes()).hexdigest()
        self.assertIn(f"`distributionSha256Sum` {self.distribution_sha}", self.pin_row)
        self.assertIn(f"wrapper jar sha256 {jar_sha}", self.pin_row)


if __name__ == "__main__":
    unittest.main()
