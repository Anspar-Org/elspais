"""Tests for CI/CD workflow configuration (REQ-o00066).

Validates that GitHub Actions workflow files declare the jobs and steps
required by the CI/CD Pipeline Enforcement specification. Uses YAML parsing
to verify workflow structure without executing the pipelines.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).parent.parent
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
PR_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pr-validation.yml"


@pytest.fixture(scope="module")
def ci_config():
    with open(CI_WORKFLOW) as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def pr_config():
    with open(PR_WORKFLOW) as f:
        return yaml.safe_load(f)


def _step_names(job: dict) -> list[str]:
    """Extract step names from a job config."""
    return [s.get("name", s.get("uses", "")) for s in job.get("steps", [])]


def _step_runs(job: dict) -> str:
    """Concatenate all run commands in a job."""
    return "\n".join(s.get("run", "") for s in job.get("steps", []))


def _step_run_containing(job: dict, needle: str) -> str:
    """Return the run command of the one step whose command contains needle."""
    matches = [s["run"] for s in job.get("steps", []) if needle in s.get("run", "")]
    assert len(matches) == 1, f"expected one step running {needle!r}, found {len(matches)}"
    return matches[0]


# The e2e job's matrix is a GitHub expression choosing one JSON array for a
# pull request and another for every other event. Its exact shape is asserted,
# so a reshaped expression fails here rather than evaluating to nothing.
_EVENT_MATRIX = re.compile(
    r"\$\{\{\s*fromJSON\(\s*github\.event_name\s*==\s*'pull_request'\s*&&\s*"
    r"'(?P<pr>\[[^']*\])'\s*\|\|\s*'(?P<other>\[[^']*\])'\s*\)\s*\}\}"
)


def _e2e_versions(ci_config, event: str) -> list[str]:
    """Evaluate the e2e job's python-version matrix for one triggering event."""
    expression = ci_config["jobs"]["e2e-test"]["strategy"]["matrix"]["python-version"]
    assert isinstance(expression, str), f"expected an event expression, got {expression!r}"
    match = _EVENT_MATRIX.fullmatch(expression.strip())
    assert match, f"e2e matrix expression has an unexpected shape: {expression!r}"
    pr_versions = json.loads(match["pr"])
    other_versions = json.loads(match["other"])
    for versions in (pr_versions, other_versions):
        assert isinstance(versions, list)
        assert all(isinstance(v, str) for v in versions)
    # `A && B || C` yields B when A holds and B is a non-empty string.
    return pr_versions if event == "pull_request" else other_versions


def _unit_versions(ci_config) -> list[str]:
    return ci_config["jobs"]["test"]["strategy"]["matrix"]["python-version"]


# --- Assertions I, J, K: which tiers run on which Python versions ---


class TestCITestSuite:
    # Verifies: REQ-o00066-J
    def test_REQ_o00066_J_pull_request_runs_e2e_on_a_supported_version(self, ci_config):
        """A pull request runs the e2e tier on at least one version, and only
        on versions the unit job supports."""
        versions = _e2e_versions(ci_config, "pull_request")
        assert versions, "a pull request must run the e2e tier on some version"
        assert set(versions) <= set(_unit_versions(ci_config))

    # Verifies: REQ-o00066-K
    def test_REQ_o00066_K_push_to_main_runs_e2e_on_every_version(self, ci_config):
        """A push to main runs the e2e tier on every supported version."""
        versions = _e2e_versions(ci_config, "push")
        assert sorted(versions) == sorted(_unit_versions(ci_config))
        assert len(versions) == len(set(versions))

    # Verifies: REQ-o00066-J+K
    def test_REQ_o00066_J_e2e_job_runs_the_tier_on_every_change(self, ci_config):
        """The e2e job runs the tier through the hook's runner and sits behind
        no path filter, so every pull request and push reaches it."""
        job = ci_config["jobs"]["e2e-test"]
        assert ".githooks/run-e2e-tier" in _step_run_containing(job, "run-e2e-tier")
        assert not any("paths-filter" in s.get("uses", "") for s in job["steps"])

    # Verifies: REQ-o00066-I
    def test_REQ_o00066_I_test_job_exists(self, ci_config):
        assert "test" in ci_config["jobs"]

    # Verifies: REQ-o00066-I
    def test_REQ_o00066_I_test_job_has_python_matrix(self, ci_config):
        matrix = ci_config["jobs"]["test"]["strategy"]["matrix"]
        versions = matrix["python-version"]
        assert len(versions) >= 2, "Should test multiple Python versions"
        assert "3.10" in versions

    # Verifies: REQ-o00066-I+K
    def test_REQ_o00066_I_triggers_on_push_and_pr(self, ci_config):
        # PyYAML converts the YAML key `on` to boolean True
        triggers = ci_config[True]
        assert "push" in triggers
        assert "pull_request" in triggers
        assert "main" in triggers["push"]["branches"]
        assert "main" in triggers["pull_request"]["branches"]

    # Verifies: REQ-o00066-I+K
    def test_REQ_o00066_I_test_job_runs_pytest(self, ci_config):
        """The unit job runs the tier through the runner the pre-commit hook
        calls, so CI and the hook run the same tests the same way."""
        assert ".githooks/run-unit-tier" in _step_run_containing(
            ci_config["jobs"]["test"], "run-unit-tier"
        )


# --- Assertion B: static analysis (linting) ---


class TestCILinting:
    # Verifies: REQ-o00066-B
    def test_REQ_o00066_B_lint_job_exists(self, ci_config):
        assert "lint" in ci_config["jobs"]

    # Verifies: REQ-o00066-B
    def test_REQ_o00066_B_lint_runs_ruff(self, ci_config):
        run_text = _step_runs(ci_config["jobs"]["lint"])
        assert "ruff" in run_text


# --- Assertion C: self-validate specs ---


class TestCISelfValidate:
    # Verifies: REQ-o00066-C
    def test_REQ_o00066_C_self_validate_job_exists(self, ci_config):
        assert "self-validate" in ci_config["jobs"]

    # Verifies: REQ-o00066-C
    def test_REQ_o00066_C_runs_elspais_health(self, ci_config):
        run_text = _step_runs(ci_config["jobs"]["self-validate"])
        assert "elspais checks" in run_text

    # Verifies: REQ-o00066-C
    def test_REQ_o00066_C_generates_traceability(self, ci_config):
        run_text = _step_runs(ci_config["jobs"]["self-validate"])
        assert "elspais trace" in run_text


# --- Assertion D: secret scanning ---


class TestCISecretScanning:
    # Verifies: REQ-o00066-D
    def test_REQ_o00066_D_security_job_exists(self, ci_config):
        assert "security" in ci_config["jobs"]

    # Verifies: REQ-o00066-D
    def test_REQ_o00066_D_scans_for_secrets(self, ci_config):
        steps = ci_config["jobs"]["security"]["steps"]
        secret_steps = [
            s
            for s in steps
            if "trufflehog" in str(s.get("uses", "")).lower()
            or "gitleaks" in str(s.get("uses", "")).lower()
            or "secret" in str(s.get("name", "")).lower()
        ]
        assert len(secret_steps) >= 1, "Should have a secret scanning step"


# --- Assertion E: dependency vulnerability audit ---


class TestCIDependencyAudit:
    # Verifies: REQ-o00066-E
    def test_REQ_o00066_E_audits_dependencies(self, ci_config):
        run_text = _step_runs(ci_config["jobs"]["security"])
        assert "pip-audit" in run_text or "safety" in run_text


# --- Assertion F: PR title requires Linear ticket ---


class TestPRTitleValidation:
    # Verifies: REQ-o00066-F
    def test_REQ_o00066_F_validate_pr_title_job_exists(self, pr_config):
        assert "validate-pr-title" in pr_config["jobs"]

    # Verifies: REQ-o00066-F
    def test_REQ_o00066_F_checks_for_ticket_reference(self, pr_config):
        run_text = _step_runs(pr_config["jobs"]["validate-pr-title"])
        assert "[A-Z]{2,10}-[0-9]+" in run_text


# --- Assertion G: commit messages require ticket + REQ refs ---


class TestCommitMessageValidation:
    # Verifies: REQ-o00066-G
    def test_REQ_o00066_G_validate_commits_job_exists(self, pr_config):
        assert "validate-commit-messages" in pr_config["jobs"]

    # Verifies: REQ-o00066-G
    def test_REQ_o00066_G_checks_for_ticket_and_req(self, pr_config):
        run_text = _step_runs(pr_config["jobs"]["validate-commit-messages"])
        assert "[A-Z]{2,10}-[0-9]+" in run_text
        assert "REQ-" in run_text


# --- Assertion H: code formatting ---


class TestCIFormatting:
    # Verifies: REQ-o00066-H
    def test_REQ_o00066_H_lint_checks_formatting(self, ci_config):
        """A job that only lints does not satisfy H -- the formatter must run."""
        run_text = _step_runs(ci_config["jobs"]["lint"])
        assert "ruff format --check" in run_text

    # Verifies: REQ-o00066-H
    @pytest.mark.parametrize("tree", ["src/", "tests/"])
    def test_REQ_o00066_H_formatting_covers_tree(self, ci_config, tree):
        run = _step_run_containing(ci_config["jobs"]["lint"], "ruff format --check")
        assert tree in run


# --- act -l validation (workflow syntax) ---


@pytest.mark.e2e
@pytest.mark.skipif(
    not shutil.which("act"),
    reason="act not installed",
)
class TestActValidation:
    # Verifies: REQ-o00066-K
    def test_REQ_o00066_K_ci_workflow_valid(self):
        """Verify ci.yml is syntactically valid via act -l."""
        result = subprocess.run(
            ["act", "-l", "-W", str(CI_WORKFLOW)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "test" in result.stdout

    # Verifies: REQ-o00066-F
    def test_REQ_o00066_F_pr_workflow_valid(self):
        """Verify pr-validation.yml is syntactically valid via act -l."""
        result = subprocess.run(
            ["act", "-l", "-W", str(PR_WORKFLOW)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "validate-pr-title" in result.stdout
