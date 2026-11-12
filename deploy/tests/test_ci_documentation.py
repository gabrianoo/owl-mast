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

    def test_no_script_or_workflow_installs_an_unpinned_python_package(self):
        for path in [*sorted((REPO / "scripts").glob("*.sh")), WORKFLOW]:
            for line in path.read_text(encoding="utf-8").splitlines():
                if "pip install" in line and not line.lstrip().startswith("#"):
                    self.assertIn("--require-hashes", line, f"{path.name}: {line.strip()}")
                    self.assertRegex(line, r"-r \S*requirements\.txt|-r \"\$REQUIREMENTS\"", f"{path.name}: {line.strip()}")


if __name__ == "__main__":
    unittest.main()
