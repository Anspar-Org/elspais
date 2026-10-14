"""Tests for CI/CD workflow configuration (REQ-o00066).

Validates that GitHub Actions workflow files declare the jobs and steps
required by the CI/CD Pipeline Enforcement specification. Uses YAML parsing
to verify workflow structure, evaluates the `if:` conditions that decide which
jobs and steps a run executes, and runs the shell scripts that decide a run's
mode and a release's verdict with stand-ins for the programs they call.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml

from tests._workflow_expressions import evaluate as _evaluate
from tests._workflow_expressions import runs as _runs

REPO_ROOT = Path(__file__).parent.parent
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
CI_WORKFLOW = WORKFLOWS / "ci.yml"
PR_WORKFLOW = WORKFLOWS / "pr-validation.yml"
PUBLISH_WORKFLOW = WORKFLOWS / "publish-pypi.yml"
RELEASE_WORKFLOW = WORKFLOWS / "auto-release.yml"


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
    return _step_running(job, needle)["run"]


def _step_running(job: dict, needle: str) -> dict:
    """Return the one step whose command contains needle."""
    matches = [s for s in job.get("steps", []) if needle in s.get("run", "")]
    assert len(matches) == 1, f"expected one step running {needle!r}, found {len(matches)}"
    return matches[0]


def _step_with_id(job: dict, step_id: str) -> dict:
    (step,) = [s for s in job["steps"] if s.get("id") == step_id]
    return step


_REFS = {
    "pull_request": "refs/pull/7/merge",
    "merge_group": "refs/heads/gh-readonly-queue/main/pr-7-0123456789abcdef",
    "push": "refs/heads/main",
    "schedule": "refs/heads/main",
    "workflow_dispatch": "refs/heads/main",
}


def _plan(full: bool = False, skip: bool = False, record: bool = False) -> dict:
    """The outputs of the `plan` job. A job output is always a string."""
    return {
        "needs.plan.outputs.full": "true" if full else "false",
        "needs.plan.outputs.skip": "true" if skip else "false",
        "needs.plan.outputs.record": "true" if record else "false",
    }


def _context(event: str, filter_output: str = "", **plan) -> dict:
    """A run of ci.yml its own trigger started, with the plan job's outputs.

    A run its own trigger started holds no inputs, and GitHub reads a property
    of the empty `inputs` object as null. A skipped step reports no outputs:
    GitHub reads them as the empty string. The run is not cancelled.
    """
    return {
        "run.cancelled": False,
        "github.event_name": event,
        "github.ref": _REFS[event],
        "inputs.ref": None,
        "steps.filter.outputs.concurrency": filter_output,
        "steps.filter.outputs.viewer": filter_output,
        **_plan(**plan),
    }


def _triggers(config: dict) -> dict:
    # PyYAML reads the YAML key `on` as the boolean True.
    return config[True]


_STATUS_FUNCTION = re.compile(r"\b(always|cancelled|success|failure)\(")
_UNMODELLED_STATUS_FUNCTION = re.compile(r"\b(success|failure)\(")


def _jobs_that_run(config: dict, context: dict) -> set[str]:
    """The jobs a run executes, every job that runs succeeding.

    A job whose condition calls no status function is skipped where any job it
    needs did not run (GitHub's implicit `success()`), so it runs only when its
    own condition holds and every job it needs ran. A job whose condition calls
    `always()` or `cancelled()` loses that implicit check and runs exactly when
    its condition holds; it reads each job it needs as `success` where that job
    ran and `skipped` where it did not.
    """
    jobs = config["jobs"]
    decided: dict[str, bool] = {}

    def decide(name: str) -> bool:
        if name not in decided:
            job = jobs[name]
            condition = str(job.get("if", ""))
            assert not _UNMODELLED_STATUS_FUNCTION.search(condition), (
                f"{name}: success() or failure() in a job condition is not modelled here"
            )
            needs = job.get("needs", [])
            needs = [needs] if isinstance(needs, str) else needs
            results = {f"needs.{n}.result": "success" if decide(n) else "skipped" for n in needs}
            holds = _runs(job, {**context, **results})
            if _STATUS_FUNCTION.search(condition):
                decided[name] = holds
            else:
                decided[name] = all(r == "success" for r in results.values()) and holds
        return decided[name]

    return {name for name in jobs if decide(name)}


def _supported_python() -> list[str]:
    """The Python versions the project supports: the one its metadata names."""
    with open(REPO_ROOT / "pyproject.toml", "rb") as f:
        requires = tomllib.load(f)["project"]["requires-python"]
    m = re.fullmatch(r">=\s*(\d+\.\d+)", requires)
    assert m, f"requires-python {requires!r} does not name one version"
    return [m.group(1)]


def _matrix_versions(ci_config, job: str, context: dict) -> list[str]:
    """Evaluate a job's python-version matrix in one context."""
    matrix = ci_config["jobs"][job]["strategy"]["matrix"]["python-version"]
    versions = _evaluate(matrix, context) if isinstance(matrix, str) else matrix
    assert isinstance(versions, list)
    assert all(isinstance(v, str) for v in versions)
    return versions


# Every job in ci.yml, by what a run uses it for.
_PREPARE = {"plan", "compute-hash", "prepare-image"}
_TIERS = {"test", "e2e-test", "stress-test", "browser-test"}
_CHECKS = {"lint", "self-validate", "security"}


# --- Assertions I, J, M, O: which jobs a run executes ---


class TestWhichJobsRun:
    # Verifies: REQ-o00066-I+J+M
    @pytest.mark.parametrize("event", ["pull_request", "merge_group"])
    @pytest.mark.parametrize(
        "plan,expected",
        [
            pytest.param({}, _PREPARE | _TIERS | _CHECKS, id="impacted"),
            pytest.param(
                {"full": True}, _PREPARE | _TIERS | _CHECKS | {"full-suite"}, id="labelled-full"
            ),
        ],
    )
    def test_REQ_o00066_I_pull_request_runs_unit_and_e2e_tiers(
        self, ci_config, event, plan, expected
    ):
        """A pull request, and its merge-queue candidate, run the unit and
        e2e tiers whether or not a label asks for the full suite; only a full
        run reaches `Full Suite`, and neither promotes an image."""
        assert _jobs_that_run(ci_config, _context(event, **plan)) == expected

    # Verifies: REQ-o00066-O
    @pytest.mark.parametrize(
        "event,plan,expected",
        [
            pytest.param("push", {}, _PREPARE | {"test"} | _CHECKS, id="push-impacted"),
            pytest.param(
                "push",
                {"full": True, "record": True},
                _PREPARE | _TIERS | _CHECKS | {"full-suite", "promote-image", "save-baseline"},
                id="push-labelled-full",
            ),
            pytest.param("schedule", {"skip": True}, {"plan"}, id="schedule-already-recorded"),
            pytest.param(
                "schedule",
                {"full": True, "record": True},
                _PREPARE | _TIERS | {"full-suite", "promote-image", "save-baseline"},
                id="schedule-unrecorded",
            ),
            pytest.param(
                "workflow_dispatch",
                {"full": True, "record": True},
                _PREPARE | _TIERS | _CHECKS | {"full-suite", "save-baseline"},
                id="dispatch",
            ),
        ],
    )
    def test_REQ_o00066_O_main_runs_impacted_tests_unless_full(
        self, ci_config, event, plan, expected
    ):
        """A push to main runs the unit tier and none of the slower tiers
        unless the run is full; a scheduled run that finds its commit already
        recorded runs nothing but the plan; only a full run of main promotes
        the image it tested; only a recording run saves a baseline."""
        assert _jobs_that_run(ci_config, _context(event, **plan)) == expected

    # Verifies: REQ-o00066-N
    def test_REQ_o00066_N_full_suite_job_runs_after_every_tier(self, ci_config):
        """`Full Suite` stands for the whole suite: it needs every tier job,
        so it is skipped where any tier did not run and pass."""
        job = ci_config["jobs"]["full-suite"]
        assert job["name"] == "Full Suite"
        assert _TIERS <= set(job["needs"])
        assert "full-suite" in ci_config["jobs"]["promote-image"]["needs"]


# --- Assertions I, J, O: what the tier jobs execute ---


class TestCITestSuite:
    # Verifies: REQ-o00066-J
    def test_REQ_o00066_J_e2e_job_runs_the_tier_on_every_change(self, ci_config):
        """The e2e job runs the tier through the hook's runner and sits behind
        no path filter, so every pull request reaches it."""
        job = ci_config["jobs"]["e2e-test"]
        assert ".githooks/run-e2e-tier" in _step_run_containing(job, "run-e2e-tier")
        assert not any("paths-filter" in s.get("uses", "") for s in job["steps"])

    # Verifies: REQ-o00066-J
    @pytest.mark.parametrize("event", ["pull_request", "merge_group"])
    def test_REQ_o00066_J_e2e_runs_on_a_supported_version(self, ci_config, event):
        versions = _matrix_versions(ci_config, "e2e-test", _context(event))
        assert versions
        assert set(versions) <= set(_supported_python())

    # Verifies: REQ-o00066-I
    def test_REQ_o00066_I_test_job_exists(self, ci_config):
        assert "test" in ci_config["jobs"]

    # Verifies: REQ-o00066-O
    def test_REQ_o00066_O_push_trigger_is_main_only(self, ci_config):
        """Other branches run through their pull requests."""
        assert _triggers(ci_config)["push"]["branches"] == ["main"]

    # Verifies: REQ-o00066-I+O
    @pytest.mark.parametrize("event", ["pull_request", "merge_group", "push"])
    def test_REQ_o00066_I_impacted_run_runs_the_selection(self, ci_config, event):
        """A run that is not full restores the newest baseline and runs the
        tests Test Impact Analysis selects, not the full tier."""
        job = ci_config["jobs"]["test"]
        context = _context(event)
        impacted = _step_running(job, "python -m tools.tia run")
        full = _step_running(job, ".githooks/run-unit-tier")
        (restore,) = [
            s for s in job["steps"] if s.get("uses", "").startswith("actions/cache/restore")
        ]
        assert _runs(impacted, context)
        assert _runs(restore, context)
        assert not _runs(full, context)

    # Verifies: REQ-o00066-I+O+N
    @pytest.mark.parametrize(
        "event,record", [("pull_request", False), ("push", True), ("schedule", True)]
    )
    def test_REQ_o00066_N_full_run_runs_the_whole_unit_tier(self, ci_config, event, record):
        """A full run runs the unit tier through the runner the pre-commit
        hook calls, and records a baseline exactly where the plan says to."""
        job = ci_config["jobs"]["test"]
        context = _context(event, full=True, record=record)
        impacted = _step_running(job, "python -m tools.tia run")
        full = _step_running(job, ".githooks/run-unit-tier")
        assert _runs(full, context)
        assert not _runs(impacted, context)
        assert _evaluate(full["env"]["ELSPAIS_TIA_RECORD"], context) == ("1" if record else "")

    # Verifies: REQ-o00066-I+O
    def test_REQ_o00066_O_baseline_is_saved_where_runs_look_for_it(self, ci_config):
        """A recording run publishes the baseline as the artifact a
        developer's hook fetches; `save-baseline` downloads that artifact and
        saves it under the key the scheduled plan looks for and the impacted
        runs restore from."""
        jobs = ci_config["jobs"]
        test = jobs["test"]
        saver = jobs["save-baseline"]
        (publish,) = [
            s
            for s in test["steps"]
            if s.get("uses", "").startswith("actions/upload-artifact")
            and "record" in str(s.get("if", ""))
        ]
        (download,) = [
            s for s in saver["steps"] if s.get("uses", "").startswith("actions/download-artifact")
        ]
        (save,) = [s for s in saver["steps"] if s.get("uses", "").startswith("actions/cache/save")]
        (restore,) = [
            s for s in test["steps"] if s.get("uses", "").startswith("actions/cache/restore")
        ]
        recorded = _step_with_id(jobs["plan"], "recorded")
        assert publish["with"]["name"] == "tia-baseline-${{ github.sha }}"
        assert "needs.plan.outputs.record == 'true'" in publish["if"]
        assert download["with"]["name"] == publish["with"]["name"]
        assert download["with"]["path"] == save["with"]["path"]
        assert save["with"]["key"] == recorded["with"]["key"]
        assert save["with"]["key"] == restore["with"]["restore-keys"] + "${{ github.sha }}"
        assert restore["with"]["key"].startswith(restore["with"]["restore-keys"])
        assert "test" in saver["needs"]
        assert "needs.plan.outputs.record == 'true'" in saver["if"]
        assert "needs.test.result == 'success'" in saver["if"]
        assert not any(s.get("uses", "").startswith("actions/cache/save") for s in test["steps"])

    # Verifies: REQ-o00066-O
    def test_REQ_o00066_O_no_job_writing_the_cache_runs_repository_code(self, ci_config):
        """The cache is shared with every later run on main, so a job that
        saves to it checks out nothing: what it saves can only be files an
        earlier job published, never the output of code the run checked out."""
        savers = {
            name: job
            for name, job in ci_config["jobs"].items()
            if any(
                str(s.get("uses", "")).startswith("actions/cache/save@")
                for s in job.get("steps", [])
            )
        }
        assert savers, "no job saves to the cache"
        for name, job in savers.items():
            assert not any(
                str(s.get("uses", "")).startswith("actions/checkout@") for s in job["steps"]
            ), name


# --- One supported Python version ---


def _python_versions_by_job() -> list[tuple[str, str, list[str]]]:
    """Every (workflow, job, versions) naming a Python version to run on."""
    found = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        config = yaml.safe_load(path.read_text())
        for name, job in config.get("jobs", {}).items():
            matrix = (job.get("strategy") or {}).get("matrix") or {}
            if "python-version" in matrix:
                found.append((path.name, name, matrix["python-version"]))
            for step in job.get("steps", []):
                if str(step.get("uses", "")).startswith("actions/setup-python@"):
                    found.append((path.name, name, [str(step["with"]["python-version"])]))
            image = str(job.get("container", ""))
            m = re.search(r"elspais-ci:py(\d+\.\d+)$", image)
            if m:
                found.append((path.name, name, [m.group(1)]))
    return found


class TestSupportedPython:
    # Verifies: REQ-o00066-N
    @pytest.mark.parametrize(
        "workflow,job,versions",
        [pytest.param(*row, id=f"{row[0]}-{row[1]}") for row in _python_versions_by_job()],
    )
    def test_REQ_o00066_N_every_job_runs_the_supported_version(self, workflow, job, versions):
        """Every job naming a Python names exactly the one the project supports,
        so a full run on it is a run on every supported version."""
        assert versions == _supported_python()

    # Verifies: REQ-o00066-N
    def test_REQ_o00066_N_every_tier_job_is_found(self):
        """The scan above reaches every tier job, so the check is not vacuous."""
        found = {job for wf, job, _ in _python_versions_by_job() if wf == "ci.yml"}
        assert _TIERS <= found


# --- The plan job's decision, run as GitHub runs it ---

#: How GitHub runs a `run:` step that names no shell.
_BASH = ["bash", "--noprofile", "--norc", "-e"]

_SHA = "0123456789abcdef0123456789abcdef01234567"


def _executable(path: Path, text: str) -> None:
    path.write_text(text)
    path.chmod(0o755)


def _run_step(step: dict, env: dict, tmp_path: Path, fakes: dict[str, str]):
    """Run one step's script with stand-ins first on PATH.

    Returns the finished process, the outputs written to GITHUB_OUTPUT, and
    the arguments of every `gh` call.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, text in fakes.items():
        _executable(bin_dir / name, text)
    script = tmp_path / "step.sh"
    script.write_text(step["run"])
    output = tmp_path / "github_output"
    output.write_text("")
    log = tmp_path / "gh.log"
    full_env = {
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "GITHUB_OUTPUT": str(output),
        "GH_LOG": str(log),
        **env,
    }
    result = subprocess.run(
        [*_BASH, str(script)], env=full_env, capture_output=True, text=True, timeout=30
    )
    outputs = dict(line.split("=", 1) for line in output.read_text().splitlines() if line)
    calls = log.read_text().splitlines() if log.exists() else []
    return result, outputs, calls


_FAKE_LABELS_GH = """#!/bin/sh
printf '%s\\n' "$*" >> "$GH_LOG"
if [ -n "$FAKE_GH_FAIL" ]; then echo "gh: HTTP 401: Bad credentials" >&2; exit 1; fi
printf '%s' "$FAKE_LABELS"
"""

#: (event, ref, extra env, labels, expected outputs, the endpoint gh is asked, or None)
_PLANS = [
    pytest.param(
        "pull_request",
        "refs/pull/7/merge",
        {},
        "",
        ("false", "false", "false"),
        "repos/o/r/issues/7/labels",
        id="pr-unlabelled",
    ),
    pytest.param(
        "pull_request",
        "refs/pull/7/merge",
        {},
        "publish",
        ("true", "false", "false"),
        "repos/o/r/issues/7/labels",
        id="pr-publish",
    ),
    pytest.param(
        "pull_request",
        "refs/pull/7/merge",
        {},
        "documentation\nbaseline",
        ("true", "false", "false"),
        "repos/o/r/issues/7/labels",
        id="pr-baseline-among-others",
    ),
    pytest.param(
        "pull_request",
        "refs/pull/7/merge",
        {},
        "publish-later\nrebaseline",
        ("false", "false", "false"),
        "repos/o/r/issues/7/labels",
        id="pr-label-only-contains-name",
    ),
    pytest.param(
        "merge_group",
        "refs/heads/gh-readonly-queue/main/pr-42-" + _SHA,
        {"QUEUE_REF": "refs/heads/gh-readonly-queue/main/pr-42-" + _SHA},
        "baseline",
        ("true", "false", "false"),
        "repos/o/r/issues/42/labels",
        id="queue-labelled",
    ),
    pytest.param(
        "merge_group",
        "refs/heads/gh-readonly-queue/main/pr-42-" + _SHA,
        {"QUEUE_REF": "refs/heads/gh-readonly-queue/main/pr-42-" + _SHA},
        "",
        ("false", "false", "false"),
        "repos/o/r/issues/42/labels",
        id="queue-unlabelled",
    ),
    pytest.param(
        "merge_group",
        "refs/heads/elsewhere",
        {"QUEUE_REF": "refs/heads/elsewhere"},
        "publish",
        ("false", "false", "false"),
        None,
        id="queue-ref-names-no-pull-request",
    ),
    pytest.param(
        "push",
        "refs/heads/main",
        {},
        "",
        ("false", "false", "false"),
        f"repos/o/r/commits/{_SHA}/pulls",
        id="push-unlabelled",
    ),
    pytest.param(
        "push",
        "refs/heads/main",
        {},
        "publish",
        ("true", "false", "true"),
        f"repos/o/r/commits/{_SHA}/pulls",
        id="push-publish-records",
    ),
    pytest.param(
        "schedule",
        "refs/heads/main",
        {"RECORDED": "true"},
        "",
        ("false", "true", "false"),
        None,
        id="schedule-already-recorded",
    ),
    pytest.param(
        "schedule",
        "refs/heads/main",
        {"RECORDED": ""},
        "",
        ("true", "false", "true"),
        None,
        id="schedule-unrecorded",
    ),
    pytest.param(
        "workflow_dispatch",
        "refs/heads/main",
        {},
        "",
        ("true", "false", "true"),
        None,
        id="dispatch-main",
    ),
    pytest.param(
        "workflow_dispatch",
        "refs/heads/feature",
        {},
        "",
        ("true", "false", "false"),
        None,
        id="dispatch-branch",
    ),
    pytest.param(
        "release",
        "refs/tags/v1.2.3",
        {"REF_INPUT": _SHA},
        "",
        ("true", "false", "false"),
        None,
        id="called-from-release",
    ),
    pytest.param(
        "push",
        "refs/heads/main",
        {"REF_INPUT": _SHA},
        "",
        ("true", "false", "false"),
        f"repos/o/r/commits/{_SHA}/pulls",
        id="called-from-push",
    ),
]


def _plan_env(event: str, ref: str, extra: dict) -> dict:
    return {
        "GH_TOKEN": "token",
        "REPOSITORY": "o/r",
        "EVENT": event,
        "REF_INPUT": "",
        "GIT_REF": ref,
        "SHA": _SHA,
        "PR_NUMBER": "7" if event == "pull_request" else "",
        "QUEUE_REF": "",
        "RECORDED": "",
        **extra,
    }


class TestPlanScript:
    # Verifies: REQ-o00066-I+O
    def test_REQ_o00066_I_the_script_reads_the_inputs_the_step_supplies(self, ci_config):
        """The stand-in environment below sets exactly what the step passes."""
        step = _step_with_id(ci_config["jobs"]["plan"], "mode")
        assert set(step["env"]) == set(_plan_env("push", "refs/heads/main", {}))

    # Verifies: REQ-o00066-I+O+N
    @pytest.mark.parametrize("event,ref,extra,labels,expected,endpoint", _PLANS)
    def test_REQ_o00066_O_plan_decides_full_skip_and_record(
        self, ci_config, tmp_path, event, ref, extra, labels, expected, endpoint
    ):
        """A run is full where a label, the schedule, a person or a release
        asks for it; only a full run of main records a baseline."""
        step = _step_with_id(ci_config["jobs"]["plan"], "mode")
        env = {**_plan_env(event, ref, extra), "FAKE_LABELS": labels}
        result, outputs, calls = _run_step(step, env, tmp_path, {"gh": _FAKE_LABELS_GH})
        assert result.returncode == 0, result.stderr
        assert (outputs["full"], outputs["skip"], outputs["record"]) == expected
        assert [c.split()[1] for c in calls] == ([endpoint] if endpoint else [])

    # Verifies: REQ-o00066-I
    @pytest.mark.parametrize("event", ["pull_request", "push"])
    def test_REQ_o00066_I_a_failed_label_lookup_fails_the_plan(self, ci_config, tmp_path, event):
        """A run whose labels cannot be read does not quietly run as impacted."""
        step = _step_with_id(ci_config["jobs"]["plan"], "mode")
        env = {**_plan_env(event, _REFS[event], {}), "FAKE_LABELS": "", "FAKE_GH_FAIL": "1"}
        result, outputs, _ = _run_step(step, env, tmp_path, {"gh": _FAKE_LABELS_GH})
        assert result.returncode != 0
        assert outputs == {}


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
    # Verifies: REQ-o00066-M
    @pytest.mark.parametrize("job_name", sorted(_FILTERED))
    def test_REQ_o00066_M_merge_group_runs_tier_unconditionally(self, ci_config, job_name):
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

    # Verifies: REQ-o00066-N
    @pytest.mark.parametrize("job_name", sorted(_FILTERED))
    def test_REQ_o00066_N_full_pull_request_ignores_the_filter(self, ci_config, job_name):
        """A pull request labelled for the full suite runs every tier."""
        filter_step, tier, notices = _filter_steps(ci_config["jobs"][job_name], _FILTERED[job_name])
        context = _context("pull_request", full=True)
        assert not _runs(filter_step, context)
        assert all(_runs(s, context) for s in tier)
        assert not any(_runs(s, context) for s in notices)


# --- Assertion L (and F, G): which events run the checks ---

_WORKFLOWS = {"ci": CI_WORKFLOW, "pr-validation": PR_WORKFLOW}


def _load(name: str) -> dict:
    with open(_WORKFLOWS[name]) as f:
        return yaml.safe_load(f)


class TestTriggers:
    # Verifies: REQ-o00066-L+F+G
    @pytest.mark.parametrize("workflow", sorted(_WORKFLOWS))
    def test_REQ_o00066_L_pull_request_runs_whatever_its_base(self, workflow):
        """A pull request stacked on another one's branch is checked too: the
        pull_request trigger filters on no base branch."""
        triggers = _triggers(_load(workflow))
        assert "pull_request" in triggers
        pr_trigger = triggers["pull_request"] or {}
        assert not {"branches", "branches-ignore"} & set(pr_trigger), pr_trigger

    # Verifies: REQ-o00066-M
    @pytest.mark.parametrize("workflow", sorted(_WORKFLOWS))
    def test_REQ_o00066_M_runs_on_merge_group(self, workflow):
        triggers = _triggers(_load(workflow))
        assert "merge_group" in triggers
        assert not {"branches", "branches-ignore"} & set(triggers["merge_group"] or {})

    # Verifies: REQ-o00066-M
    @pytest.mark.parametrize("full", [False, True])
    @pytest.mark.parametrize("workflow", sorted(_WORKFLOWS))
    def test_REQ_o00066_M_merge_group_runs_every_job_a_pull_request_runs(self, workflow, full):
        """No job-level condition drops a merge-queue candidate from a job a
        pull request into main gets (a job skipped by its own condition
        reports success, so it never holds the queue)."""
        jobs = _load(workflow)["jobs"]
        for name, job in jobs.items():
            needs = job.get("needs", [])
            needs = [needs] if isinstance(needs, str) else needs
            results = {f"needs.{n}.result": "success" for n in needs}
            assert _runs(job, {**_context("merge_group", full=full), **results}) == _runs(
                job, {**_context("pull_request", full=full), **results}
            ), name


# --- Assertion N: a release publishes only a commit that passed the full suite ---

#: The commit a release names when it calls ci.yml.
_RELEASED_SHA = "0123456789abcdef0123456789abcdef01234567"

#: Events a run calling ci.yml may have started from. A called run carries
#: its caller's event, so none of them may decide what the called run tests.
_CALLER_EVENTS = {
    "release": "refs/tags/v1.2.3",
    "workflow_dispatch": "refs/heads/main",
    "workflow_run": "refs/heads/main",
    "push": "refs/heads/main",
    "pull_request": "refs/pull/7/merge",
}


def _called_context(caller_event: str) -> dict:
    """ci.yml called with a commit to test, from a run of `caller_event`. The
    plan job reads a called run as full and records nothing. A path filter
    step that does not run reports an empty output."""
    return {
        "run.cancelled": False,
        "github.event_name": caller_event,
        "github.ref": _CALLER_EVENTS[caller_event],
        "github.sha": "fedcba9876543210fedcba9876543210fedcba98",
        "inputs.ref": _RELEASED_SHA,
        "steps.filter.outputs.concurrency": "",
        "steps.filter.outputs.viewer": "",
        **_plan(full=True),
    }


def _load_path(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


class TestReleaseRunsTheFullSuite:
    # Verifies: REQ-o00066-N
    def test_REQ_o00066_N_ci_is_callable_with_the_commit_to_test(self, ci_config):
        call = _triggers(ci_config)["workflow_call"]
        assert call["inputs"]["ref"]["required"] is True

    # Verifies: REQ-o00066-N
    @pytest.mark.parametrize("caller_event", sorted(_CALLER_EVENTS))
    def test_REQ_o00066_N_called_run_runs_every_tier_and_the_full_suite(
        self, ci_config, caller_event
    ):
        """A called run runs each tier on every supported Python and reaches
        `Full Suite`, whatever event started its caller, promotes no image and
        saves no baseline."""
        context = _called_context(caller_event)
        ran = _jobs_that_run(ci_config, context)
        assert _TIERS | {"full-suite"} <= ran
        assert "promote-image" not in ran
        assert "save-baseline" not in ran
        for job_name in _TIERS:
            assert _matrix_versions(ci_config, job_name, context) == _supported_python()

    # Verifies: REQ-o00066-N
    @pytest.mark.parametrize("caller_event", sorted(_CALLER_EVENTS))
    def test_REQ_o00066_N_called_run_runs_the_whole_unit_tier(self, ci_config, caller_event):
        job = ci_config["jobs"]["test"]
        context = _called_context(caller_event)
        assert _runs(_step_running(job, ".githooks/run-unit-tier"), context)
        assert not _runs(_step_running(job, "python -m tools.tia run"), context)

    # Verifies: REQ-o00066-N
    @pytest.mark.parametrize("caller_event", sorted(_CALLER_EVENTS))
    @pytest.mark.parametrize("job_name", sorted(_FILTERED))
    def test_REQ_o00066_N_called_run_ignores_the_path_filter(
        self, ci_config, job_name, caller_event
    ):
        filter_step, tier, notices = _filter_steps(ci_config["jobs"][job_name], _FILTERED[job_name])
        context = _called_context(caller_event)
        assert not _runs(filter_step, context)
        assert all(_runs(s, context) for s in tier)
        assert not any(_runs(s, context) for s in notices)

    # Verifies: REQ-o00066-N
    @pytest.mark.parametrize("caller_event", sorted(_CALLER_EVENTS))
    def test_REQ_o00066_N_called_run_checks_out_the_released_commit(self, ci_config, caller_event):
        """Every checkout in a called run is at the commit the release names,
        never at the caller's own commit."""
        context = _called_context(caller_event)
        checkouts = [
            step
            for job in ci_config["jobs"].values()
            for step in job.get("steps", [])
            if str(step.get("uses", "")).startswith("actions/checkout@")
        ]
        assert checkouts
        for step in checkouts:
            assert _evaluate(step["with"]["ref"], context) == _RELEASED_SHA, step


def _publish_context(
    *,
    gate: str,
    verdict: str,
    tests: str,
    publish: str = "skipped",
    skip_pypi: bool = False,
    cancelled: bool = False,
) -> dict:
    return {
        "run.cancelled": cancelled,
        "inputs.skip_pypi": skip_pypi,
        "needs.gate.result": gate,
        "needs.gate.outputs.verdict": verdict,
        "needs.tests.result": tests,
        "needs.publish.result": publish,
    }


#: (gate result, gate verdict, tests result) -> whether the commit may ship.
#: A gate that refused reports no verdict, and `tests` is then skipped.
_VERDICTS = [
    pytest.param("success", "passed", "skipped", True, id="ci-passed"),
    pytest.param("success", "untested", "success", True, id="release-tests-passed"),
    pytest.param("success", "untested", "failure", False, id="release-tests-failed"),
    pytest.param("success", "untested", "cancelled", False, id="release-tests-cancelled"),
    pytest.param("failure", "", "skipped", False, id="gate-refused"),
]


@pytest.fixture(scope="module")
def publish_jobs():
    return _load_path(PUBLISH_WORKFLOW)["jobs"]


@pytest.fixture(scope="module")
def release_config():
    return _load_path(RELEASE_WORKFLOW)


class TestReleaseGate:
    # Verifies: REQ-o00066-N
    @pytest.mark.parametrize("verdict", ["passed", "untested", ""])
    def test_REQ_o00066_N_release_runs_tests_only_without_a_verdict(self, publish_jobs, verdict):
        """The release runs the suite itself only where CI holds no verdict,
        and runs it on the commit the gate resolved."""
        job = publish_jobs["tests"]
        context = {"needs.gate.outputs.verdict": verdict, "needs.gate.outputs.sha": _RELEASED_SHA}
        assert _runs(job, context) == (verdict == "untested")
        assert job["uses"] == "./.github/workflows/ci.yml"
        assert _evaluate(job["with"]["ref"], context) == _RELEASED_SHA

    # Verifies: REQ-o00066-N
    def test_REQ_o00066_N_release_tests_may_read_what_the_plan_reads(self, publish_jobs, ci_config):
        """A called workflow holds no more than its caller grants, so the
        release grants every permission ci.yml's jobs ask for."""
        granted = publish_jobs["tests"]["permissions"]
        for name, job in ci_config["jobs"].items():
            for scope, level in (job.get("permissions") or {}).items():
                assert granted.get(scope) in (level, "write"), (name, scope)

    # Verifies: REQ-o00066-N
    @pytest.mark.parametrize("gate,verdict,tests,ships", _VERDICTS)
    def test_REQ_o00066_N_publish_needs_a_passing_verdict(
        self, publish_jobs, gate, verdict, tests, ships
    ):
        context = _publish_context(gate=gate, verdict=verdict, tests=tests)
        assert _runs(publish_jobs["publish"], context) == ships
        assert not _runs(publish_jobs["publish"], {**context, "run.cancelled": True})

    # Verifies: REQ-o00066-N
    @pytest.mark.parametrize("skip_pypi", [False, True])
    @pytest.mark.parametrize("gate,verdict,tests,ships", _VERDICTS)
    def test_REQ_o00066_N_homebrew_needs_a_passing_verdict(
        self, publish_jobs, gate, verdict, tests, ships, skip_pypi
    ):
        """The tap is updated after PyPI, or alone where PyPI is skipped, and
        in neither case for a commit without a passing verdict."""
        publish = "success" if ships and not skip_pypi else "skipped"
        context = _publish_context(
            gate=gate, verdict=verdict, tests=tests, publish=publish, skip_pypi=skip_pypi
        )
        assert _runs(publish_jobs["update-homebrew"], context) == ships


# --- The release gate's reading of CI's verdict, run as GitHub runs it ---

_FAKE_RUNS_GH = """#!/bin/sh
printf '%s\\n' "$*" >> "$GH_LOG"
case "$1 $2" in
  "run list") printf '%s' "$FAKE_RUNS" ;;
  "api --paginate")
    id=$(printf '%s' "$3" | sed -n 's|.*/runs/\\([0-9][0-9]*\\)/jobs.*|\\1|p')
    cat "$FAKE_JOBS/$id" ;;
  *) echo "unexpected: gh $*" >&2; exit 2 ;;
esac
"""

#: The CI image carries no `jq`, so the gate's two filters are answered by a
#: stand-in that refuses any other, keeping the test identical on every machine.
_FAKE_JQ = f"""#!{sys.executable}
import json, sys
args = sys.argv[1:]
runs = json.load(sys.stdin)
if args == ["-r", ".[].databaseId"]:
    for run in runs:
        print(run["databaseId"])
elif args[:3] == ["-r", "--argjson", "id"] and args[4:] == [
    ".[] | select(.databaseId == $id) | .status"
]:
    for run in runs:
        if run["databaseId"] == json.loads(args[3]):
            print(run["status"])
else:
    sys.exit("jq stand-in: unexpected arguments " + repr(args))
"""

_ALL_PASSED = [
    ("success", "Plan"),
    ("success", "Test (Python 3.14)"),
    ("success", "E2E (Python 3.14)"),
    ("success", "Full Suite"),
]
_IMPACTED = [
    ("success", "Plan"),
    ("success", "Test (Python 3.14)"),
    ("skipped", "E2E (Python 3.14)"),
    ("skipped", "Full Suite"),
]

#: (runs: [(id, status, jobs)], exit status, verdict)
_GATE_CASES = [
    pytest.param([(1, "completed", _ALL_PASSED)], 0, "passed", id="full-run-passed"),
    pytest.param([(1, "completed", _IMPACTED)], 0, "untested", id="impacted-run-passed"),
    pytest.param(
        [(1, "completed", [j for j in _ALL_PASSED if j[1] != "Full Suite"])],
        0,
        "untested",
        id="every-job-passed-but-none-is-full-suite",
    ),
    pytest.param(
        [(1, "completed", [("failure", "Test (Python 3.14)"), ("skipped", "Full Suite")])],
        1,
        None,
        id="run-failed",
    ),
    pytest.param([(1, "in_progress", _ALL_PASSED)], 0, "untested", id="run-in-progress"),
    pytest.param([], 0, "untested", id="no-push-run"),
    pytest.param(
        [(1, "completed", _IMPACTED), (2, "completed", _ALL_PASSED)],
        0,
        "passed",
        id="impacted-then-full",
    ),
]


class TestGateVerdictScript:
    # Verifies: REQ-o00066-N
    @pytest.mark.parametrize("runs,rc,verdict", _GATE_CASES)
    def test_REQ_o00066_N_only_a_passed_full_suite_is_a_verdict(
        self, publish_jobs, tmp_path, runs, rc, verdict
    ):
        """A push run counts as CI's verdict only where every job passed and
        `Full Suite` was among them; a failed job refuses the release."""
        step = _step_with_id(publish_jobs["gate"], "verdict")
        jobs_dir = tmp_path / "jobs"
        jobs_dir.mkdir()
        for run_id, _, jobs in runs:
            (jobs_dir / str(run_id)).write_text("".join(f"{c}\t{n}\n" for c, n in jobs))
        env = {
            "GH_TOKEN": "token",
            "REPOSITORY": "o/r",
            "SHA": _RELEASED_SHA,
            "FAKE_RUNS": json.dumps(
                [{"databaseId": i, "status": s, "conclusion": None} for i, s, _ in runs]
            ),
            "FAKE_JOBS": str(jobs_dir),
        }
        assert set(step["env"]) <= set(env)
        result, outputs, calls = _run_step(
            step, env, tmp_path, {"gh": _FAKE_RUNS_GH, "jq": _FAKE_JQ}
        )
        assert "stand-in" not in result.stderr, result.stderr
        assert result.returncode == rc, result.stdout + result.stderr
        assert outputs.get("verdict") == verdict
        assert any(c.startswith("run list") and f"--commit {_RELEASED_SHA}" in c for c in calls)
        assert ("Refusing to publish" in result.stdout) == bool(rc)


class TestAutoRelease:
    # Verifies: REQ-o00066-N
    def test_REQ_o00066_N_release_follows_ci_on_main(self, release_config, ci_config):
        trigger = _triggers(release_config)["workflow_run"]
        assert trigger["workflows"] == [ci_config["name"]]
        assert trigger["types"] == ["completed"]
        assert trigger["branches"] == ["main"]

    # Verifies: REQ-o00066-N
    @pytest.mark.parametrize("conclusion", ["success", "failure", "cancelled", "skipped"])
    @pytest.mark.parametrize("event", ["push", "pull_request", "merge_group", "workflow_dispatch"])
    def test_REQ_o00066_N_release_starts_only_from_a_passing_push_run(
        self, release_config, event, conclusion
    ):
        context = {
            "github.event.workflow_run.event": event,
            "github.event.workflow_run.conclusion": conclusion,
        }
        expected = event == "push" and conclusion == "success"
        assert _runs(release_config["jobs"]["release"], context) == expected

    # Verifies: REQ-o00066-N
    def test_REQ_o00066_N_release_targets_the_tested_commit(self, release_config):
        """The tag, the version read and the published commit are the commit
        the CI run tested, not whatever main holds when the release runs."""
        context = {"github.event.workflow_run.head_sha": _RELEASED_SHA}
        job = release_config["jobs"]["release"]
        (checkout,) = [
            s for s in job["steps"] if str(s.get("uses", "")).startswith("actions/checkout@")
        ]
        assert _evaluate(checkout["with"]["ref"], context) == _RELEASED_SHA
        (create,) = [s for s in job["steps"] if "gh release create" in s.get("run", "")]
        assert '--target "${SHA}"' in create["run"]
        assert _evaluate(create["env"]["SHA"], context) == _RELEASED_SHA
        assert _evaluate(job["outputs"]["sha"], context) == _RELEASED_SHA
        assert (
            release_config["jobs"]["publish"]["with"]["sha"] == "${{ needs.release.outputs.sha }}"
        )


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
    # Verifies: REQ-o00066-M
    @pytest.mark.parametrize(
        "job_name",
        [
            "validate-pr-title",
            "validate-commit-messages",
        ],
    )
    def test_REQ_o00066_M_every_job_runs_a_step_in_merge_queue(self, pr_config, job_name):
        """Each required check reports on a merge-queue candidate by running
        something there, rather than by having nothing to run."""
        steps = pr_config["jobs"][job_name]["steps"]
        assert any(_runs(s, _context("merge_group")) for s in steps)

    # Verifies: REQ-o00066-M+F+G
    def test_REQ_o00066_M_title_and_commit_checks_skip_merge_queue(self, pr_config):
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
    # Verifies: REQ-o00066-I+O
    def test_REQ_o00066_I_ci_workflow_valid(self):
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
