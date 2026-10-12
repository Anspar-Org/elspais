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


# --- A small evaluator for the GitHub Actions expressions these workflows use ---
#
# Enough of the expression language to evaluate the `if:` conditions and the e2e
# matrix as GitHub would: string literals, context names, `==`/`!=`, `!`, `&&`,
# `||` (which yield an operand, not a boolean), parentheses and `fromJSON`. A
# name the context does not supply raises, so a condition reading something a
# test did not anticipate fails loudly rather than evaluating to nothing.

_TOKEN = re.compile(
    r"\s*(?:(?P<str>'(?:[^']|'')*')|(?P<op>==|!=|&&|\|\||!|\(|\)|,)"
    r"|(?P<name>[A-Za-z_][A-Za-z0-9_.\-]*))"
)
_LITERALS = {"true": True, "false": False, "null": None}
_FUNCTIONS = {"fromJSON": json.loads}


def _tokens(text: str) -> list[tuple[str, str]]:
    text = text.strip()
    found, pos = [], 0
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m or m.end() == pos:
            raise ValueError(f"cannot read expression at {text[pos:]!r}")
        kind = m.lastgroup
        found.append((kind, m.group(kind)))
        pos = m.end()
    return found


def _equal(a, b) -> bool:
    if isinstance(a, str) and isinstance(b, str):
        return a.lower() == b.lower()  # GitHub compares strings ignoring case
    return a == b


class _Expression:
    def __init__(self, text: str, context: dict):
        self.toks = _tokens(text)
        self.pos = 0
        self.context = context

    def _peek(self):
        return self.toks[self.pos] if self.pos < len(self.toks) else (None, None)

    def _take(self, value=None):
        tok = self._peek()
        if value is not None and tok[1] != value:
            raise ValueError(f"expected {value!r}, found {tok[1]!r}")
        self.pos += 1
        return tok

    def evaluate(self):
        value = self._or()
        if self.pos != len(self.toks):
            raise ValueError(f"trailing tokens: {self.toks[self.pos :]!r}")
        return value

    def _or(self):
        value = self._and()
        while self._peek() == ("op", "||"):
            self._take()
            right = self._and()
            value = value if value else right
        return value

    def _and(self):
        value = self._cmp()
        while self._peek() == ("op", "&&"):
            self._take()
            right = self._cmp()
            value = right if value else value
        return value

    def _cmp(self):
        value = self._unary()
        if self._peek() in (("op", "=="), ("op", "!=")):
            op = self._take()[1]
            right = self._unary()
            value = _equal(value, right) if op == "==" else not _equal(value, right)
        return value

    def _unary(self):
        if self._peek() == ("op", "!"):
            self._take()
            return not self._unary()
        return self._primary()

    def _primary(self):
        kind, value = self._take()
        if kind == "str":
            return value[1:-1].replace("''", "'")
        if (kind, value) == ("op", "("):
            inner = self._or()
            self._take(")")
            return inner
        if kind != "name":
            raise ValueError(f"unexpected token {value!r}")
        if self._peek() == ("op", "("):
            self._take()
            args = [self._or()]
            while self._peek() == ("op", ","):
                self._take()
                args.append(self._or())
            self._take(")")
            return _FUNCTIONS[value](*args)
        if value in _LITERALS:
            return _LITERALS[value]
        return self.context[value]


def _evaluate(expression, context: dict):
    """Evaluate a workflow expression (`${{ ... }}`, or a bare `if:`)."""
    if isinstance(expression, bool):
        return expression
    text = expression.strip()
    if text.startswith("${{"):
        assert text.endswith("}}"), f"unterminated expression {text!r}"
        text = text[3:-2]
    return _Expression(text, context).evaluate()


# A skipped step reports no outputs: GitHub reads them as the empty string.
_REFS = {
    "pull_request": "refs/pull/7/merge",
    "merge_group": "refs/heads/gh-readonly-queue/main/pr-7-0123456789abcdef",
    "push": "refs/heads/main",
}


def _context(event: str, filter_output: str = "") -> dict:
    return {
        "github.event_name": event,
        "github.ref": _REFS[event],
        "steps.filter.outputs.concurrency": filter_output,
        "steps.filter.outputs.viewer": filter_output,
    }


def _runs(item: dict, context: dict) -> bool:
    """Whether a job or step with this `if:` runs (no `if:` means it runs)."""
    return bool(_evaluate(item.get("if", True), context))


def _e2e_versions(ci_config, event: str) -> list[str]:
    """Evaluate the e2e job's python-version matrix for one triggering event."""
    expression = ci_config["jobs"]["e2e-test"]["strategy"]["matrix"]["python-version"]
    assert isinstance(expression, str), f"expected an event expression, got {expression!r}"
    versions = _evaluate(expression, _context(event))
    assert isinstance(versions, list)
    assert all(isinstance(v, str) for v in versions)
    return versions


def _triggers(config: dict) -> dict:
    # PyYAML reads the YAML key `on` as the boolean True.
    return config[True]


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

    # Verifies: REQ-o00066-K
    def test_REQ_o00066_K_push_trigger_is_main_only(self, ci_config):
        """The full-suite push run is for main; other branches run through
        their pull requests."""
        assert _triggers(ci_config)["push"]["branches"] == ["main"]

    # Verifies: REQ-o00066-J
    def test_REQ_o00066_J_merge_group_runs_e2e_on_one_version(self, ci_config):
        """A merge-queue candidate runs the e2e tier as a pull request does."""
        versions = _e2e_versions(ci_config, "merge_group")
        assert versions == _e2e_versions(ci_config, "pull_request") == ["3.13"]

    # Verifies: REQ-o00066-I+K
    # Verifies: REQ-o00066-I+K
    def test_REQ_o00066_I_test_job_runs_pytest(self, ci_config):
        """The unit job runs the tier through the runner the pre-commit hook
        calls, so CI and the hook run the same tests the same way."""
        assert ".githooks/run-unit-tier" in _step_run_containing(
            ci_config["jobs"]["test"], "run-unit-tier"
        )


# --- Assertions I, J, L (and F, G): which events run the checks ---

_WORKFLOWS = {"ci": CI_WORKFLOW, "pr-validation": PR_WORKFLOW}


def _load(name: str) -> dict:
    with open(_WORKFLOWS[name]) as f:
        return yaml.safe_load(f)


#: Jobs that run for a pull request and deliberately not in the merge queue.
#: test-impact selects a subset of the unit tier for fast feedback on a pull
#: request; the queue runs the full tier in `test`, so a selection adds nothing.
_PR_ONLY_ADVISORY_JOBS = {"ci": ("test-impact",)}


class TestTriggers:
    # Verifies: REQ-o00066-I+J+F+G
    @pytest.mark.parametrize("workflow", sorted(_WORKFLOWS))
    def test_REQ_o00066_I_pull_request_runs_whatever_its_base(self, workflow):
        """A pull request stacked on another one's branch is checked too: the
        pull_request trigger filters on no base branch."""
        triggers = _triggers(_load(workflow))
        assert "pull_request" in triggers
        pr_trigger = triggers["pull_request"] or {}
        assert not {"branches", "branches-ignore"} & set(pr_trigger), pr_trigger

    # Verifies: REQ-o00066-L
    @pytest.mark.parametrize("workflow", sorted(_WORKFLOWS))
    def test_REQ_o00066_L_runs_on_merge_group(self, workflow):
        triggers = _triggers(_load(workflow))
        assert "merge_group" in triggers
        assert not {"branches", "branches-ignore"} & set(triggers["merge_group"] or {})

    # Verifies: REQ-o00066-L
    @pytest.mark.parametrize("workflow", sorted(_WORKFLOWS))
    def test_REQ_o00066_L_merge_group_runs_every_job_a_pull_request_runs(self, workflow):
        """No job-level condition drops a merge-queue candidate from a job a
        pull request into main gets, except the advisory ones the queue has
        no use for (a job skipped by its own condition reports success, so it
        never holds the queue)."""
        jobs = _load(workflow)["jobs"]
        for name, job in jobs.items():
            if name in _PR_ONLY_ADVISORY_JOBS.get(workflow, ()):
                assert _runs(job, _context("pull_request")), name
                assert not _runs(job, _context("merge_group")), name
                continue
            assert _runs(job, _context("merge_group")) == _runs(job, _context("pull_request")), name


# Each path-filtered job: the job and the filter output its steps read.
_FILTERED = {"stress-test": "concurrency", "browser-test": "viewer"}


def _filter_steps(job: dict, output: str) -> tuple[dict, list[dict], list[dict]]:
    """Split a path-filtered job into its filter step, the steps that run its
    tier, and the steps that only announce the tier was not required."""
    steps = job["steps"]
    (filter_step,) = [s for s in steps if s.get("id") == "filter"]
    gated = [s for s in steps if f"steps.filter.outputs.{output}" in str(s.get("if", ""))]
    notices = [s for s in gated if s.get("run", "").lstrip().startswith("echo")]
    tier = [s for s in gated if s not in notices]
    assert any("pytest" in s.get("run", "") for s in tier), "no gated step runs the tier"
    assert notices, "no step announces a skipped tier"
    return filter_step, tier, notices


class TestPathFilteredTiers:
    # Verifies: REQ-o00066-L
    @pytest.mark.parametrize("job_name", sorted(_FILTERED))
    def test_REQ_o00066_L_merge_group_runs_tier_unconditionally(self, ci_config, job_name):
        """In the merge queue the filter step is skipped (its output reads
        empty) and the tier runs anyway; the skip notice does not."""
        filter_step, tier, notices = _filter_steps(ci_config["jobs"][job_name], _FILTERED[job_name])
        context = _context("merge_group", filter_output="")
        assert not _runs(filter_step, context)
        assert all(_runs(s, context) for s in tier)
        assert not any(_runs(s, context) for s in notices)

    # Verifies: REQ-o00066-I
    @pytest.mark.parametrize("changed", [True, False])
    @pytest.mark.parametrize("job_name", sorted(_FILTERED))
    def test_REQ_o00066_I_pull_request_honours_the_filter(self, ci_config, job_name, changed):
        filter_step, tier, notices = _filter_steps(ci_config["jobs"][job_name], _FILTERED[job_name])
        context = _context("pull_request", filter_output="true" if changed else "false")
        assert _runs(filter_step, context)
        assert all(_runs(s, context) == changed for s in tier)
        assert all(_runs(s, context) != changed for s in notices)


def _pr_check_steps(pr_config) -> list[dict]:
    """The steps that read a pull request: its title and its commit range."""
    jobs = pr_config["jobs"]
    title = _step_with(jobs["validate-pr-title"], "PR_TITLE")
    commits = _step_with(jobs["validate-commit-messages"], "git log")
    return [title, commits]


def _step_with(job: dict, needle: str) -> dict:
    (step,) = [s for s in job["steps"] if needle in s.get("run", "")]
    return step


class TestPRValidationInMergeQueue:
    # Verifies: REQ-o00066-L
    @pytest.mark.parametrize(
        "job_name",
        [
            "validate-pr-title",
            "validate-commit-messages",
        ],
    )
    def test_REQ_o00066_L_every_job_runs_a_step_in_merge_queue(self, pr_config, job_name):
        """Each required check reports on a merge-queue candidate by running
        something there, rather than by having nothing to run."""
        steps = pr_config["jobs"][job_name]["steps"]
        assert any(_runs(s, _context("merge_group")) for s in steps)

    # Verifies: REQ-o00066-L+F+G
    def test_REQ_o00066_L_title_and_commit_checks_skip_merge_queue(self, pr_config):
        """The merge queue has no title or commit range to read; a pull
        request still has both checked."""
        for step in _pr_check_steps(pr_config):
            assert not _runs(step, _context("merge_group"))
            assert _runs(step, _context("pull_request"))


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
