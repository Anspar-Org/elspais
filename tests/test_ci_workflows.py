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
IMAGE_WORKFLOW = WORKFLOWS / "build-ci-image.yml"
PRERELEASE_WORKFLOW = WORKFLOWS / "prerelease-pypi.yml"


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


def _context(
    event: str,
    filter_output: str = "",
    ref: str | None = None,
    base_ref: str | None = None,
    **plan,
) -> dict:
    """A run of ci.yml its own trigger started, with the plan job's outputs.

    `ref` replaces the event's usual ref, and `base_ref` the branch a pull
    request targets (GitHub sets `github.base_ref` only for a pull request,
    and reads it as the empty string otherwise). A run its own trigger started
    holds no inputs, and GitHub reads a property of the empty `inputs` object
    as null. A skipped step reports no outputs: GitHub reads them as the empty
    string. The run is not cancelled.
    """
    if base_ref is None:
        base_ref = "main" if event == "pull_request" else ""
    return {
        "run.cancelled": False,
        "github.event_name": event,
        "github.ref": _REFS[event] if ref is None else ref,
        "github.base_ref": base_ref,
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

    # Verifies: REQ-o00080-C+E
    @pytest.mark.parametrize("full", [False, True], ids=["impacted", "full"])
    def test_REQ_o00080_C_automain_push_runs_what_a_main_push_runs(self, ci_config, full):
        """A push to automain runs every job a push to main runs in the same
        mode, except what a run of main publishes: the promoted CI image and
        the recorded baseline. The plan records only for main, so the automain
        run carries `record=false` (TestPlanScript runs that decision). The
        one job automain runs beyond main's builds its pre-release package."""
        main = _jobs_that_run(ci_config, _context("push", full=full, record=full))
        automain = _jobs_that_run(
            ci_config, _context("push", ref="refs/heads/automain", full=full, record=False)
        )
        assert main - automain == ({"promote-image", "save-baseline"} if full else set())
        assert automain - main == {"prerelease-build"}

    # Verifies: REQ-o00080-E
    @pytest.mark.parametrize("event", ["push", "schedule"])
    def test_REQ_o00080_E_automain_never_promotes_the_image(self, ci_config, event):
        """Promoting the production CI image tag is a publication of main: a
        full run of automain does not promote it even where the plan's outputs
        would ask a run of main to, while the same run of main does."""
        plan = {"full": True, "record": True}
        main = _jobs_that_run(ci_config, _context(event, ref="refs/heads/main", **plan))
        automain = _jobs_that_run(ci_config, _context(event, ref="refs/heads/automain", **plan))
        assert "promote-image" in main
        assert "promote-image" not in automain

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

    # Verifies: REQ-o00066-O, REQ-o00080-C
    def test_REQ_o00080_C_push_trigger_names_both_trunks(self, ci_config):
        """A push to either trunk runs CI; other branches run through their
        pull requests."""
        push = _triggers(ci_config)["push"]
        assert sorted(push["branches"]) == ["automain", "main"]
        assert "branches-ignore" not in push

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


def _run_step(
    step: dict, env: dict, tmp_path: Path, fakes: dict[str, str], cwd: Path | None = None
):
    """Run one step's script with stand-ins first on PATH, in `cwd` if given.

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
        [*_BASH, str(script)], env=full_env, capture_output=True, text=True, timeout=30, cwd=cwd
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
        "refs/heads/gh-readonly-queue/automain/pr-42-" + _SHA,
        {"QUEUE_REF": "refs/heads/gh-readonly-queue/automain/pr-42-" + _SHA},
        "baseline",
        ("true", "false", "false"),
        "repos/o/r/issues/42/labels",
        id="automain-queue-labelled",
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

    # Verifies: REQ-o00080-C+E
    @pytest.mark.parametrize("labels", ["publish", "baseline"])
    @pytest.mark.parametrize("branch,record", [("main", "true"), ("automain", "false")])
    def test_REQ_o00080_E_a_full_push_run_records_only_on_main(
        self, ci_config, tmp_path, branch, record, labels
    ):
        """A labelled push to automain is full, as one to main is, and reads
        the merged pull request's labels the same way; only main's run records
        the baseline every later run selects from."""
        step = _step_with_id(ci_config["jobs"]["plan"], "mode")
        env = {**_plan_env("push", f"refs/heads/{branch}", {}), "FAKE_LABELS": labels}
        result, outputs, calls = _run_step(step, env, tmp_path, {"gh": _FAKE_LABELS_GH})
        assert result.returncode == 0, result.stderr
        assert (outputs["full"], outputs["skip"], outputs["record"]) == ("true", "false", record)
        assert [c.split()[1] for c in calls] == [f"repos/o/r/commits/{_SHA}/pulls"]

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
    # Verifies: REQ-o00066-L+F+G, REQ-o00080-A
    @pytest.mark.parametrize("workflow", sorted(_WORKFLOWS))
    def test_REQ_o00066_L_pull_request_runs_whatever_its_base(self, workflow):
        """A pull request stacked on another one's branch is checked too: the
        pull_request trigger filters on no base branch."""
        triggers = _triggers(_load(workflow))
        assert "pull_request" in triggers
        pr_trigger = triggers["pull_request"] or {}
        assert not {"branches", "branches-ignore"} & set(pr_trigger), pr_trigger

    # Verifies: REQ-o00066-M, REQ-o00080-B
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

    # Verifies: REQ-o00080-A+B
    @pytest.mark.parametrize("full", [False, True], ids=["impacted", "full"])
    @pytest.mark.parametrize("workflow", sorted(_WORKFLOWS))
    @pytest.mark.parametrize(
        "event,main,automain",
        [
            pytest.param(
                "pull_request",
                {"base_ref": "main"},
                {"base_ref": "automain"},
                id="pull-request",
            ),
            pytest.param(
                "merge_group",
                {"ref": "refs/heads/gh-readonly-queue/main/pr-7-0123456789abcdef"},
                {"ref": "refs/heads/gh-readonly-queue/automain/pr-7-0123456789abcdef"},
                id="merge-queue",
            ),
        ],
    )
    def test_REQ_o00080_A_automain_target_runs_the_checks_main_gets(
        self, workflow, full, event, main, automain
    ):
        """A pull request, or a merge-queue candidate, targeting automain runs
        every job one targeting main runs: no condition reads the base."""
        config = _load(workflow)
        into_main = _jobs_that_run(config, _context(event, full=full, **main))
        into_automain = _jobs_that_run(config, _context(event, full=full, **automain))
        assert into_main
        assert into_automain == into_main


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
        """Every checkout of a job a called run executes is at the commit the
        release names, never at the caller's own commit."""
        context = _called_context(caller_event)
        ran = _jobs_that_run(ci_config, context)
        checkouts = [
            step
            for name, job in ci_config["jobs"].items()
            if name in ran
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

    # Verifies: REQ-o00066-N, REQ-o00080-D
    @pytest.mark.parametrize("head_branch", ["main", "automain"])
    @pytest.mark.parametrize("conclusion", ["success", "failure", "cancelled", "skipped"])
    @pytest.mark.parametrize("event", ["push", "pull_request", "merge_group", "workflow_dispatch"])
    def test_REQ_o00080_D_release_starts_only_from_a_passing_push_run_of_main(
        self, release_config, event, conclusion, head_branch
    ):
        """Only a passing push run of main starts a release; a passing push
        run of automain does not, whatever the trigger's branch filter says."""
        context = {
            "github.event.workflow_run.event": event,
            "github.event.workflow_run.conclusion": conclusion,
            "github.event.workflow_run.head_branch": head_branch,
        }
        expected = event == "push" and conclusion == "success" and head_branch == "main"
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


# --- REQ-o00080-D: the release publishes only a commit main contains ---

_FAKE_COMPARE_GH = """#!/bin/sh
printf '%s\\n' "$*" >> "$GH_LOG"
if [ -n "$FAKE_GH_FAIL" ]; then echo "gh: HTTP 404: Not Found" >&2; exit 1; fi
printf '%s\\n' "$FAKE_STATUS"
"""


class TestReleaseOnMain:
    # Verifies: REQ-o00080-D
    def test_REQ_o00080_D_gate_confirms_main_before_reading_the_commit(self, publish_jobs):
        """The gate asks whether main contains the resolved commit before it
        checks that commit out, and asks about the commit it resolved."""
        steps = publish_jobs["gate"]["steps"]
        ids = [s.get("id") for s in steps]
        checkouts = [
            i for i, s in enumerate(steps) if str(s.get("uses", "")).startswith("actions/checkout@")
        ]
        assert checkouts
        assert ids.index("commit") < ids.index("on-main") < checkouts[0]
        step = _step_with_id(publish_jobs["gate"], "on-main")
        assert set(step["env"]) == {"GH_TOKEN", "REPOSITORY", "SHA"}
        context = {"steps.commit.outputs.sha": _RELEASED_SHA}
        assert _evaluate(step["env"]["SHA"], context) == _RELEASED_SHA

    # Verifies: REQ-o00080-D
    @pytest.mark.parametrize(
        "status,gh_fails,passes",
        [
            pytest.param("identical", False, True, id="main-is-the-commit"),
            pytest.param("behind", False, True, id="main-contains-the-commit"),
            pytest.param("ahead", False, False, id="commit-is-past-main"),
            pytest.param("diverged", False, False, id="commit-is-off-main"),
            pytest.param("", True, False, id="forge-unreachable"),
        ],
    )
    def test_REQ_o00080_D_gate_refuses_a_commit_main_does_not_contain(
        self, publish_jobs, tmp_path, status, gh_fails, passes
    ):
        """A commit on automain, or anywhere else main does not reach, is
        refused naming the commit; an unanswered question refuses too."""
        step = _step_with_id(publish_jobs["gate"], "on-main")
        env = {
            "GH_TOKEN": "token",
            "REPOSITORY": "o/r",
            "SHA": _RELEASED_SHA,
            "FAKE_STATUS": status,
            **({"FAKE_GH_FAIL": "1"} if gh_fails else {}),
        }
        result, _, calls = _run_step(step, env, tmp_path, {"gh": _FAKE_COMPARE_GH})
        said = result.stdout + result.stderr
        assert (result.returncode == 0) == passes, said
        assert [c.split()[:2] for c in calls] == [
            ["api", f"repos/o/r/compare/main...{_RELEASED_SHA}"]
        ]
        if not passes and not gh_fails:
            assert "::error::" in said
            assert _RELEASED_SHA in said


# --- REQ-o00080-E: the production CI image is built only from main ---


class TestCIImageFromMain:
    # Verifies: REQ-o00080-E
    @pytest.mark.parametrize(
        "ref,builds",
        [
            ("refs/heads/main", True),
            ("refs/heads/automain", False),
            ("refs/heads/feature", False),
        ],
    )
    def test_REQ_o00080_E_production_image_is_pushed_only_from_main(self, ref, builds):
        """The manual build pushes the image tag every CI job runs in, so a
        dispatch from any branch but main builds nothing."""
        job = _load_path(IMAGE_WORKFLOW)["jobs"]["build"]
        assert _runs(job, {"github.ref": ref}) == builds


# --- REQ-o00081: automain's pre-releases ---


# --- REQ-o00081-A+D: CI builds the pre-release package, without the credential ---

_FAKE_BUILD_GIT = """#!/bin/sh
printf 'git %s\\n' "$*" >> "$GH_LOG"
echo 812
"""

_FAKE_BUILD_CURL = """#!/bin/sh
printf 'curl %s\\n' "$*" >> "$GH_LOG"
if [ -n "$FAKE_CURL_FAIL" ]; then echo "curl: (22) 503" >&2; exit 22; fi
while [ $# -gt 0 ]; do
  if [ "$1" = "-o" ]; then printf '{"releases": {}}' > "$2"; fi
  shift
done
"""

_FAKE_BUILD_PYTHON = """#!/bin/sh
printf 'python %s\\n' "$*" >> "$GH_LOG"
if [ "$FAKE_TOOL_RC" -eq 0 ]; then echo 0.130.0.dev812; else echo "refused" >&2; fi
exit "$FAKE_TOOL_RC"
"""


def _after(call: str, option: str) -> str:
    words = call.split()
    return words[words.index(option) + 1]


class TestPrereleaseBuild:
    # Verifies: REQ-o00081-A+D
    @pytest.mark.parametrize(
        "event,ref,inputs_ref,runs",
        [
            pytest.param("push", "refs/heads/automain", None, True, id="automain-push"),
            pytest.param("push", "refs/heads/main", None, False, id="main-push"),
            pytest.param("pull_request", None, None, False, id="pull-request"),
            pytest.param(
                "merge_group",
                "refs/heads/gh-readonly-queue/automain/pr-7-0123456789abcdef",
                None,
                False,
                id="automain-queue",
            ),
            pytest.param("schedule", None, None, False, id="schedule"),
            pytest.param("workflow_dispatch", "refs/heads/automain", None, False, id="dispatch"),
            pytest.param(
                "push", "refs/heads/automain", _RELEASED_SHA, False, id="called-from-a-push"
            ),
        ],
    )
    def test_REQ_o00081_A_builds_only_for_a_push_to_automain(
        self, ci_config, event, ref, inputs_ref, runs
    ):
        """Only a push to automain builds a pre-release package; a called run
        carries its caller's event and ref, so `inputs.ref` must rule it out."""
        context = {**_context(event, ref=ref), "inputs.ref": inputs_ref}
        assert _runs(ci_config["jobs"]["prerelease-build"], context) == runs

    # Verifies: REQ-o00081-D
    def test_REQ_o00081_D_the_build_job_holds_no_credential(self, ci_config):
        job = ci_config["jobs"]["prerelease-build"]
        assert job["permissions"] == {"contents": "read"}
        assert not any("secrets." in t for t in _strings(job))

    # Verifies: REQ-o00081-A+B
    def test_REQ_o00081_A_builds_the_computed_version_and_uploads_it(self, ci_config):
        job = ci_config["jobs"]["prerelease-build"]
        (checkout,) = [
            s for s in job["steps"] if str(s.get("uses", "")).startswith("actions/checkout@")
        ]
        assert str(checkout["with"]["fetch-depth"]) == "0"
        version = _step_with_id(job, "version")
        for option in (
            "python -m tools.prerelease_version",
            "--pyproject pyproject.toml",
            "--write",
        ):
            assert option in version["run"], option
        build = _step_running(job, "python -m build")
        (upload,) = [
            s for s in job["steps"] if str(s.get("uses", "")).startswith("actions/upload-artifact@")
        ]
        assert upload["with"]["name"] == "prerelease-dist"
        assert upload["with"]["if-no-files-found"] == "error"
        steps = job["steps"]
        assert steps.index(version) < steps.index(build) < steps.index(upload)

    # Verifies: REQ-o00081-A+C
    @pytest.mark.parametrize("built", [True, False])
    def test_REQ_o00081_C_a_refused_version_builds_nothing(self, ci_config, built):
        job = ci_config["jobs"]["prerelease-build"]
        context = {"steps.version.outputs.built": "true" if built else "false"}
        build = _step_running(job, "python -m build")
        (upload,) = [
            s for s in job["steps"] if str(s.get("uses", "")).startswith("actions/upload-artifact@")
        ]
        assert _runs(build, context) == built
        assert _runs(upload, context) == built

    # Verifies: REQ-o00081-A+C
    @pytest.mark.parametrize(
        "tool_rc,curl_fails,rc,built",
        [
            pytest.param(0, False, 0, "true", id="computed"),
            pytest.param(1, False, 0, "false", id="refused"),
            pytest.param(2, False, 2, None, id="tool-broke"),
            pytest.param(0, True, None, None, id="index-unreachable"),
        ],
    )
    def test_REQ_o00081_C_version_step_tolerates_only_a_refusal(
        self, ci_config, tmp_path, tool_rc, curl_fails, rc, built
    ):
        """A refusal -- a re-run for a commit already published -- builds
        nothing and passes with a warning; any other failure fails the job.
        The tool reads the index the step fetched and the commit's count."""
        step = _step_with_id(ci_config["jobs"]["prerelease-build"], "version")
        env = {
            "GITHUB_SHA": _SHA,
            "RUNNER_TEMP": str(tmp_path),
            "FAKE_TOOL_RC": str(tool_rc),
            **({"FAKE_CURL_FAIL": "1"} if curl_fails else {}),
        }
        fakes = {"git": _FAKE_BUILD_GIT, "curl": _FAKE_BUILD_CURL, "python": _FAKE_BUILD_PYTHON}
        result, outputs, calls = _run_step(step, env, tmp_path, fakes)
        said = result.stdout + result.stderr
        if rc is None:
            assert result.returncode != 0, said
        else:
            assert result.returncode == rc, said
        assert outputs.get("built") == built
        assert ("::warning::" in said) == (built == "false")
        (git,) = [c for c in calls if c.startswith("git ")]
        assert "rev-list --count --first-parent" in git and _SHA in git
        tools = [c for c in calls if c.startswith("python ")]
        if curl_fails:
            assert tools == []
            return
        (curl,) = [c for c in calls if c.startswith("curl ")]
        (tool,) = tools
        assert "-m tools.prerelease_version" in tool
        assert _after(tool, "--count") == "812"
        assert _after(tool, "--index") == _after(curl, "-o")


@pytest.fixture(scope="module")
def prerelease_config():
    return _load_path(PRERELEASE_WORKFLOW)


def _strings(value):
    """Every string a parsed workflow value holds, keys included."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _strings(key)
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _evaluate_template(text: str, context: dict) -> str:
    """A string value with `${{ ... }}` expressions in it, as GitHub fills it."""
    return re.sub(r"\$\{\{(.*?)\}\}", lambda m: str(_evaluate(m.group(1), context)), text)


def _index_of_step_running(job: dict, needle: str) -> int:
    (index,) = [i for i, s in enumerate(job["steps"]) if needle in s.get("run", "")]
    return index


class TestPrereleaseWorkflow:
    # Verifies: REQ-o00081-A, REQ-o00080-E
    def test_REQ_o00081_A_follows_ci_on_automain_alone(self, prerelease_config, ci_config):
        """Only a completed CI run on automain starts a pre-release: no person,
        tag, push or caller can start one."""
        triggers = _triggers(prerelease_config)
        assert set(triggers) == {"workflow_run"}
        run = triggers["workflow_run"]
        assert run["workflows"] == [ci_config["name"]]
        assert run["types"] == ["completed"]
        assert run["branches"] == ["automain"]

    # Verifies: REQ-o00081-A+C
    @pytest.mark.parametrize(
        "first,second", [(_SHA, _RELEASED_SHA[::-1]), (_RELEASED_SHA, _RELEASED_SHA)]
    )
    def test_REQ_o00081_A_holds_no_default_permissions_and_never_cancels(
        self, prerelease_config, first, second
    ):
        """A run is never cancelled, in progress or pending: GitHub keeps one
        pending run per group and cancels the older, so runs of two commits
        never share a group, and two runs of one commit do."""
        assert prerelease_config["permissions"] == {}
        concurrency = prerelease_config["concurrency"]
        assert concurrency["cancel-in-progress"] is False

        def group(sha: str) -> str:
            return _evaluate_template(
                concurrency["group"], {"github.event.workflow_run.head_sha": sha}
            )

        assert (group(first) == group(second)) == (first == second)
        assert set(prerelease_config["jobs"]) == {"prerelease"}

    # Verifies: REQ-o00081-A, REQ-o00080-E
    @pytest.mark.parametrize("head_branch", ["automain", "main"])
    @pytest.mark.parametrize("conclusion", ["success", "failure"])
    @pytest.mark.parametrize("event", ["push", "pull_request"])
    def test_REQ_o00081_A_publishes_only_after_a_passing_automain_push_run(
        self, prerelease_config, event, conclusion, head_branch
    ):
        context = {
            "github.event.workflow_run.event": event,
            "github.event.workflow_run.conclusion": conclusion,
            "github.event.workflow_run.head_branch": head_branch,
        }
        expected = event == "push" and conclusion == "success" and head_branch == "automain"
        assert _runs(prerelease_config["jobs"]["prerelease"], context) == expected

    # Verifies: REQ-o00081-A
    def test_REQ_o00081_A_confirms_automain_contains_the_commit(self, prerelease_config):
        job = prerelease_config["jobs"]["prerelease"]
        run = _step_run_containing(job, "merge-base --is-ancestor")
        assert "origin/automain" in run
        assert _index_of_step_running(job, "merge-base --is-ancestor") < (
            _index_of_step_running(job, "twine upload")
        )

    # Verifies: REQ-o00081-B+C, REQ-o00080-E
    def test_REQ_o00081_B_publishes_the_package_ci_built_at_the_computed_version(
        self, prerelease_config
    ):
        """The version is computed here, from the index and the first-parent
        count, without writing anything; the package is the one this commit's
        CI run built, and the check reads the version computed here."""
        job = prerelease_config["jobs"]["prerelease"]
        compute = _step_with_id(job, "version")
        assert "python -m tools.prerelease_version" in compute["run"]
        for option in ("--pyproject", "--index", "--count"):
            assert option in compute["run"], option
        assert "--write" not in compute["run"]
        assert "rev-list --count --first-parent" in compute["run"]
        (download,) = [
            s
            for s in job["steps"]
            if str(s.get("uses", "")).startswith("actions/download-artifact@")
        ]
        assert download["with"]["name"] == "prerelease-dist"
        run_id = {"github.event.workflow_run.id": "4242"}
        assert str(_evaluate(download["with"]["run-id"], run_id)) == "4242"
        check = _step_running(job, "twine check")
        computed = {"steps.version.outputs.version": "0.130.0.dev812"}
        assert _evaluate(check["env"]["VERSION"], computed) == "0.130.0.dev812"
        steps = job["steps"]
        assert (
            steps.index(compute)
            < steps.index(download)
            < steps.index(check)
            < _index_of_step_running(job, "twine upload")
        )

    # Verifies: REQ-o00081-D
    def test_REQ_o00081_D_only_the_publishing_job_reads_the_credential(self, prerelease_config):
        jobs = prerelease_config["jobs"]
        holders = [
            name for name, job in jobs.items() if any("secrets." in t for t in _strings(job))
        ]
        assert holders == ["prerelease"]
        assert jobs["prerelease"]["permissions"] == {"contents": "read", "actions": "read"}
        assert any("secrets.PYPI_TOKEN" in t for t in _strings(jobs["prerelease"]))

    # Verifies: REQ-o00081-D
    def test_REQ_o00081_D_the_commit_is_checked_out_as_data_beside_the_tool(
        self, prerelease_config
    ):
        """Nothing is checked out into the workspace root: the published
        commit lands in `commit/` with no credential left in it, and the code
        that runs comes from main, in `tool/`."""
        job = prerelease_config["jobs"]["prerelease"]
        context = {"github.event.workflow_run.head_sha": _RELEASED_SHA}
        checkouts = [
            s for s in job["steps"] if str(s.get("uses", "")).startswith("actions/checkout@")
        ]
        paths = [s.get("with", {}).get("path", "") for s in checkouts]
        assert sorted(paths) == ["commit", "tool"]
        by_path = dict(zip(paths, checkouts, strict=True))
        commit = by_path["commit"]["with"]
        assert _evaluate_template(commit["ref"], context) == _RELEASED_SHA
        assert commit["persist-credentials"] is False
        assert str(commit["fetch-depth"]) == "0"
        tool = by_path["tool"]["with"]
        assert _evaluate_template(tool["ref"], context) == "main"
        for step in checkouts:
            if _evaluate_template(step["with"]["ref"], context) == _RELEASED_SHA:
                assert step["with"]["path"] == "commit"

    # Verifies: REQ-o00081-D
    def test_REQ_o00081_D_every_module_run_is_main_s_tool(self, prerelease_config):
        job = prerelease_config["jobs"]["prerelease"]
        assert "defaults" not in job
        modules = [s for s in job["steps"] if "python -m" in s.get("run", "")]
        assert modules
        for step in modules:
            assert step.get("working-directory") == "tool", step["name"]

    # Verifies: REQ-o00081-D
    def test_REQ_o00081_D_no_step_executes_the_commit(self, prerelease_config):
        """The commit is read with git and its pyproject.toml is passed as
        data; nothing runs from inside it, and no step builds or installs it."""
        job = prerelease_config["jobs"]["prerelease"]
        runs = [s for s in job["steps"] if "run" in s]
        assert runs
        reads = re.compile(r"git -C (?:\.\./)?commit\b|--pyproject \.\./commit/pyproject\.toml")
        for step in runs:
            rest = reads.sub("", step["run"])
            assert "commit/" not in rest, step["name"]
            assert not re.search(r"(?:\bcd|-C)\s+(?:\.\./)?commit\b", rest), step["name"]
            assert "commit" not in str(step.get("working-directory", "")), step["name"]
            assert not re.search(r"\bmake\b", step["run"]), step["name"]
        assert not any(str(s.get("uses", "")).startswith(".") for s in job["steps"])
        texts = list(_strings(prerelease_config))
        for forbidden in ("python -m build", "pip install -e", "pip install ."):
            assert not any(forbidden in t for t in texts), forbidden

    # Verifies: REQ-o00081-D
    def test_REQ_o00081_D_installs_against_main_s_lock(self, prerelease_config):
        job = prerelease_config["jobs"]["prerelease"]
        installs = [s["run"] for s in job["steps"] if "pip install" in s.get("run", "")]
        assert installs
        for run in installs:
            assert "-c tool/requirements/dev.lock" in run
            assert not re.search(r"(?:-c|-r|--constraint|--requirement)[ =](?!tool/)", run), run

    # Verifies: REQ-o00081-C
    def test_REQ_o00081_C_an_upload_never_passes_over_a_taken_number(self, prerelease_config):
        """An upload of a version the index already holds fails the run rather
        than reading as success."""
        job = prerelease_config["jobs"]["prerelease"]
        assert "twine upload" in _step_run_containing(job, "twine upload")
        assert not any("--skip-existing" in text for text in _strings(prerelease_config))

    # Verifies: REQ-o00080-E
    @pytest.mark.parametrize(
        "publication",
        ["gh release", "git tag", "git push", "repository-dispatch", "/dispatches"],
    )
    def test_REQ_o00080_E_publishes_nothing_but_the_pre_release(
        self, prerelease_config, publication
    ):
        """No tag, no GitHub release and no Homebrew dispatch: those publish
        a release, and a release is a decision about main."""
        texts = list(_strings(prerelease_config["jobs"]))
        assert any("twine upload" in t for t in texts)
        assert not any(publication in t for t in texts)


# --- REQ-o00081-B+D: the publishing job's check of the package CI built ---

#: Stands in for pkginfo where the venv lacks it: it reads a wheel's
#: METADATA and an sdist's top-level PKG-INFO, as pkginfo does.
_PKGINFO_STAND_IN = """
import email.parser
import tarfile
import zipfile


class _Distribution:
    def __init__(self, text):
        message = email.parser.Parser().parsestr(text)
        self.name = message["Name"]
        self.version = message["Version"]


class Wheel(_Distribution):
    def __init__(self, path):
        with zipfile.ZipFile(path) as archive:
            (name,) = [n for n in archive.namelist() if n.endswith(".dist-info/METADATA")]
            super().__init__(archive.read(name).decode())


class SDist(_Distribution):
    def __init__(self, path):
        with tarfile.open(path) as archive:
            (member,) = [
                m for m in archive.getmembers()
                if m.name.count("/") == 1 and m.name.endswith("/PKG-INFO")
            ]
            super().__init__(archive.extractfile(member).read().decode())
"""

_FAKE_TWINE = """#!/bin/sh
printf '%s\\n' "$*" >> "$GH_LOG"
exit "${FAKE_TWINE_RC:-0}"
"""


def _metadata(name: str, version: str) -> bytes:
    return f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n".encode()


def _wheel(path: Path, name: str, version: str) -> None:
    import zipfile

    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(f"{name}-{version}.dist-info/METADATA", _metadata(name, version))


def _sdist(path: Path, name: str, version: str) -> None:
    import io
    import tarfile

    data = _metadata(name, version)
    with tarfile.open(path, "w:gz") as archive:
        info = tarfile.TarInfo(f"{name}-{version}/PKG-INFO")
        info.size = len(data)
        archive.addfile(info, io.BytesIO(data))


_DEV = "0.130.0.dev812"

#: (expected VERSION, [(file name, metadata name, metadata version)], twine rc, passes)
_PACKAGES = [
    pytest.param(
        _DEV,
        [
            (f"elspais-{_DEV}-py3-none-any.whl", "elspais", _DEV),
            (f"elspais-{_DEV}.tar.gz", "elspais", _DEV),
        ],
        0,
        True,
        id="the-package",
    ),
    pytest.param(
        _DEV,
        [
            (f"elspais-{_DEV}-py3-none-any.whl", "elspais", _DEV),
            (f"elspais-{_DEV}.tar.gz", "elspais", _DEV),
            ("notes.txt", None, None),
        ],
        0,
        False,
        id="extra-file",
    ),
    pytest.param(
        _DEV,
        [(f"elspais-{_DEV}-py3-none-any.whl", "elspais", _DEV)],
        0,
        False,
        id="sdist-missing",
    ),
    pytest.param(
        _DEV,
        [
            (f"elspais-{_DEV}-py3-none-any.whl", "elspais", "9.9.9"),
            (f"elspais-{_DEV}.tar.gz", "elspais", _DEV),
        ],
        0,
        False,
        id="final-release-renamed",
    ),
    pytest.param(
        _DEV,
        [
            (f"elspais-{_DEV}-py3-none-any.whl", "elspais", _DEV),
            (f"elspais-{_DEV}.tar.gz", "not-elspais", _DEV),
        ],
        0,
        False,
        id="other-project",
    ),
    pytest.param(
        "0.130.0",
        [
            ("elspais-0.130.0-py3-none-any.whl", "elspais", "0.130.0"),
            ("elspais-0.130.0.tar.gz", "elspais", "0.130.0"),
        ],
        0,
        False,
        id="expected-is-a-release",
    ),
    pytest.param(
        _DEV,
        [
            (f"elspais-{_DEV}-py3-none-any.whl", "elspais", _DEV),
            (f"elspais-{_DEV}.tar.gz", "elspais", _DEV),
        ],
        1,
        False,
        id="twine-check-fails",
    ),
]


class TestPrereleasePackageCheck:
    # Verifies: REQ-o00081-B+D
    @pytest.mark.parametrize("expected,files,twine_rc,passes", _PACKAGES)
    def test_REQ_o00081_D_publishes_only_the_package_at_the_computed_version(
        self, prerelease_config, tmp_path, expected, files, twine_rc, passes
    ):
        """The package came from a job that ran the commit's code, so it is
        read as data: the dist directory holds exactly the wheel and sdist of
        elspais at the computed developmental version, or nothing ships."""
        step = _step_running(prerelease_config["jobs"]["prerelease"], "twine check")
        work = tmp_path / "work"
        dist = work / "dist"
        dist.mkdir(parents=True)
        for file_name, name, version in files:
            if file_name.endswith(".whl"):
                _wheel(dist / file_name, name, version)
            elif file_name.endswith(".tar.gz"):
                _sdist(dist / file_name, name, version)
            else:
                (dist / file_name).write_text("x")
        env = {"VERSION": expected, "FAKE_TWINE_RC": str(twine_rc)}
        try:
            import pkginfo  # noqa: F401
        except ImportError:
            stand_in = tmp_path / "stand_in"
            stand_in.mkdir()
            (stand_in / "pkginfo.py").write_text(_PKGINFO_STAND_IN)
            env["PYTHONPATH"] = str(stand_in)
        fakes = {"twine": _FAKE_TWINE, "python": f'#!/bin/sh\nexec "{sys.executable}" "$@"\n'}
        result, _, calls = _run_step(step, env, tmp_path, fakes, cwd=work)
        said = result.stdout + result.stderr
        assert (result.returncode == 0) == passes, said
        assert calls and calls[0].startswith("check dist/"), calls
        if passes:
            assert f"elspais {expected}" in result.stdout
        elif twine_rc == 0:
            assert "::error::" in said


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
