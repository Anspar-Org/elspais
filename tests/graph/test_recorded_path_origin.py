"""Where a relative source path in a test target's results is read from.

Each test builds an on-disk project whose one test file lives under `app/`,
with a target that runs in `app/`. A producer may record that file as
`app/tests/test_login.py` (relative to the repository root) or as
`tests/test_login.py` (relative to where it ran). The origin the reporter
declares, or the one the target declares in its place, decides which spelling
binds; a spelling read from the wrong origin binds to nothing and is reported.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from elspais.commands.health import check_unmatched_results
from elspais.config.schema import PATH_ORIGIN_CWD, PATH_ORIGIN_ROOT, TestTargetConfig
from elspais.graph.GraphNode import NodeKind
from elspais.graph.parsers.results.registry import REPORTER_REGISTRY, ReporterSpec
from elspais.graph.relations import EdgeKind
from tests.core.graph_test_helpers import record_run

_SPEC = """\
### REQ-p00001: Login

**Level**: PRD | **Status**: Active

The system SHALL let a user log in.

#### Assertions

A. The system SHALL accept valid credentials.

*End* *Login* | **Hash**: ________
"""

# The test is declared on line 2; JUnit counts lines from zero.
_TEST_SOURCE = """\
# Verifies: REQ-p00001-A
def test_logs_in():
    assert True
"""

_TEST_FILE = "app/tests/test_login.py"

_CONFIG = """\
version = 5

[project]
name = "origin"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[scanning.test]
enabled = true
directories = ["app/tests"]
file_patterns = ["test_*.py"]

[[scanning.test.targets]]
name = "unit"
cwd = "app"
reporter = "{reporter}"
results = "{results}"
match = "source"
{extra}"""


def _junit(file_attr: str) -> tuple[str, str]:
    return (
        "junit.xml",
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<testsuites>\n"
        '  <testsuite name="unit" tests="1" failures="0">\n'
        f'    <testcase classname="tests.test_login" name="test_logs_in"'
        f' file="{file_attr}" line="1" time="0.01"/>\n'
        "  </testsuite>\n"
        "</testsuites>\n",
    )


def _pytest_json(nodeid_path: str) -> tuple[str, str]:
    report = {
        "tests": [{"nodeid": f"{nodeid_path}::test_logs_in", "outcome": "passed", "duration": 0.01}]
    }
    return "report.json", json.dumps(report)


_REPORTS = {"junit": _junit, "pytest-json": _pytest_json}


def _project(tmp_path: Path, reporter: str, recorded: str, extra: str = "") -> Path:
    """One requirement, one scanned test under `app/`, one report recording *recorded*."""
    project = tmp_path / "project"
    files = {
        "spec/reqs.md": _SPEC,
        _TEST_FILE: _TEST_SOURCE,
    }
    results_name, report = _REPORTS[reporter](recorded)
    files[f".results/unit/{results_name}"] = report
    files[".elspais.toml"] = _CONFIG.format(reporter=reporter, results=results_name, extra=extra)
    for rel, text in files.items():
        path = project / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return project


def _build(project: Path):
    from elspais.graph.factory import build_graph

    return build_graph(config_path=project / ".elspais.toml", repo_root=project, scan_code=False)


def _the_result(graph):
    results = list(graph.iter_by_kind(NodeKind.RESULT))
    assert len(results) == 1, [r.id for r in results]
    return results[0]


def _bound_tests(result) -> list[str]:
    """Repo-relative paths of the tests the result is bound to."""
    bound = []
    for parent in result.iter_parents(edge_kinds={EdgeKind.YIELDS}):
        file_node = parent.file_node()
        bound.append(file_node.get_field("relative_path") if file_node else parent.id)
    return sorted(bound)


def _origin_line(origin: str) -> str:
    return f'results_origin = "{origin}"\n' if origin else ""


# ---------------------------------------------------------------------------
# D -- the results reporters the tool provides read from the repository root
# ---------------------------------------------------------------------------


# Verifies: REQ-d00327-D, REQ-d00327-E
def test_each_provided_reporter_declares_the_origin_of_its_kind():
    """Results formats read from the root and coverage formats from the target's
    working directory -- the origins each kind was read from before either was
    declarable, so a project that declares nothing binds as it did."""
    declared = {name: (spec.kind, spec.path_origin) for name, spec in REPORTER_REGISTRY.items()}
    assert declared, "the registry holds the built-in reporters"
    for name, (kind, origin) in declared.items():
        expected = PATH_ORIGIN_CWD if kind == "coverage" else PATH_ORIGIN_ROOT
        assert origin == expected, f"{name} ({kind}) declares {origin!r}"
    kinds = {kind for kind, _ in declared.values()}
    assert {"results", "coverage"} <= kinds


# Verifies: REQ-d00327-A
def test_a_reporter_may_declare_an_origin_other_than_its_kinds():
    spec = ReporterSpec(
        name="cwd-junit",
        channel="file",
        kind="results",
        parser_factory=lambda: None,
        path_origin=PATH_ORIGIN_CWD,
    )
    assert spec.path_origin == PATH_ORIGIN_CWD


# Verifies: REQ-d00327-C, REQ-d00327-D
@pytest.mark.parametrize(
    "reporter,recorded",
    [
        ("junit", _TEST_FILE),  # a location in the testcase's `file` attribute
        ("pytest-json", "app/tests/test_login.py"),  # the path inside the test's name
    ],
)
def test_a_repo_root_relative_path_binds_from_a_subdirectory_target(tmp_path, reporter, recorded):
    """A producer that records repo-root-relative paths while its target runs in
    a subdirectory binds by default."""
    graph = _build(_project(tmp_path, reporter, recorded))
    result = _the_result(graph)

    assert _bound_tests(result) == [_TEST_FILE]
    assert result.get_field("path_origin") == PATH_ORIGIN_ROOT
    assert check_unmatched_results(graph).passed is True


# ---------------------------------------------------------------------------
# B + C -- a target replaces the reporter's origin for its own results
# ---------------------------------------------------------------------------


# Verifies: REQ-d00327-B, REQ-d00327-C
@pytest.mark.parametrize("reporter", ["junit", "pytest-json"])
def test_a_working_directory_relative_path_binds_where_the_target_declares_that_origin(
    tmp_path, reporter
):
    graph = _build(
        _project(tmp_path, reporter, "tests/test_login.py", _origin_line(PATH_ORIGIN_CWD))
    )
    result = _the_result(graph)

    assert _bound_tests(result) == [_TEST_FILE]
    assert result.get_field("path_origin") == PATH_ORIGIN_CWD
    assert check_unmatched_results(graph).passed is True


# Verifies: REQ-d00327-C
def test_the_location_read_from_the_working_directory_is_repo_relative(tmp_path):
    graph = _build(
        _project(tmp_path, "junit", "tests/test_login.py", _origin_line(PATH_ORIGIN_CWD))
    )
    result = _the_result(graph)

    assert result.get_field("source_path") == "tests/test_login.py", "the path as recorded"
    assert result.get_field("source_file") == _TEST_FILE, "the path read from its origin"
    assert result.get_field("match_scope") == "test"


# Verifies: REQ-d00327-C
def test_the_test_named_by_a_working_directory_relative_name_is_the_scanned_one(tmp_path):
    graph = _build(
        _project(tmp_path, "pytest-json", "tests/test_login.py", _origin_line(PATH_ORIGIN_CWD))
    )
    result = _the_result(graph)

    assert result.get_field("test_id") == f"test:{_TEST_FILE}::test_logs_in"


# Verifies: REQ-d00327-B, REQ-d00327-D
@pytest.mark.parametrize("declared", ["", PATH_ORIGIN_ROOT], ids=["reporter-default", "declared"])
def test_a_working_directory_relative_path_read_from_the_root_binds_to_nothing(tmp_path, declared):
    """The root origin, declared or taken from the reporter, reads the path once;
    the tool does not also try the working directory."""
    graph = _build(_project(tmp_path, "junit", "tests/test_login.py", _origin_line(declared)))
    result = _the_result(graph)

    assert _bound_tests(result) == []


# Verifies: REQ-d00327-B
@pytest.mark.parametrize("reporter", ["junit", "pytest-json"])
def test_a_repo_root_relative_path_read_from_the_working_directory_binds_to_nothing(
    tmp_path, reporter
):
    graph = _build(_project(tmp_path, reporter, _TEST_FILE, _origin_line(PATH_ORIGIN_CWD)))
    result = _the_result(graph)

    assert _bound_tests(result) == []


# Verifies: REQ-d00327-B
def test_the_targets_coverage_origin_does_not_move_its_results(tmp_path):
    """Results and coverage are declared apart: a coverage origin says nothing
    about where the target's results start."""
    graph = _build(
        _project(tmp_path, "junit", _TEST_FILE, f'coverage_origin = "{PATH_ORIGIN_CWD}"\n')
    )
    assert _bound_tests(_the_result(graph)) == [_TEST_FILE]


# ---------------------------------------------------------------------------
# G -- a result whose path names no scanned file is reported, saying why
# ---------------------------------------------------------------------------


# Verifies: REQ-d00327-G, REQ-d00284-C
@pytest.mark.parametrize(
    "reporter,recorded,declared,origin",
    [
        ("junit", "tests/test_login.py", "", PATH_ORIGIN_ROOT),
        ("pytest-json", "tests/test_login.py", "", PATH_ORIGIN_ROOT),
        ("junit", _TEST_FILE, PATH_ORIGIN_CWD, PATH_ORIGIN_CWD),
        ("pytest-json", _TEST_FILE, PATH_ORIGIN_CWD, PATH_ORIGIN_CWD),
    ],
    ids=["junit-root", "pytest-json-root", "junit-cwd", "pytest-json-cwd"],
)
def test_a_result_read_from_the_wrong_origin_is_reported_naming_path_and_origin(
    tmp_path, reporter, recorded, declared, origin
):
    graph = _build(_project(tmp_path, reporter, recorded, _origin_line(declared)))
    assert _bound_tests(_the_result(graph)) == [], "the result binds to no test"

    check = check_unmatched_results(graph)

    assert check.passed is False
    (finding,) = check.findings
    assert "matched no test" in finding.message
    assert repr(recorded) in finding.message, "the path as recorded"
    assert repr(origin) in finding.message, "the origin it was read from"


# Verifies: REQ-d00327-G
def test_a_result_that_binds_names_no_unscanned_path(tmp_path):
    graph = _build(_project(tmp_path, "junit", _TEST_FILE))
    assert _the_result(graph).get_field("unscanned_path") is None


# ---------------------------------------------------------------------------
# B -- the target's declaration is validated
# ---------------------------------------------------------------------------


# Verifies: REQ-d00327-B
@pytest.mark.parametrize("field", ["results_origin", "coverage_origin"])
@pytest.mark.parametrize("value", ["", PATH_ORIGIN_ROOT, PATH_ORIGIN_CWD])
def test_a_declarable_origin_is_accepted(field, value):
    target = TestTargetConfig(name="t", **{field: value})
    assert getattr(target, field) == value


# Verifies: REQ-d00327-B
@pytest.mark.parametrize("field", ["results_origin", "coverage_origin"])
def test_an_undeclarable_origin_is_refused_naming_the_setting_and_the_choices(field):
    with pytest.raises(ValidationError) as excinfo:
        TestTargetConfig(name="t", **{field: "cwd"})
    message = str(excinfo.value)
    assert field in message
    assert PATH_ORIGIN_ROOT in message and PATH_ORIGIN_CWD in message


# Verifies: REQ-d00327-B
@pytest.mark.parametrize("field", ["results_origin", "coverage_origin"])
def test_a_configuration_declaring_an_undeclarable_origin_does_not_load(tmp_path, field):
    from elspais.config import load_config

    project = _project(tmp_path, "junit", _TEST_FILE, f'{field} = "root"\n')

    with pytest.raises(ValueError) as excinfo:
        load_config(project / ".elspais.toml")
    message = str(excinfo.value)
    assert field in message
    assert PATH_ORIGIN_ROOT in message and PATH_ORIGIN_CWD in message


# ---------------------------------------------------------------------------
# A -- a reporter's own declaration is validated
# ---------------------------------------------------------------------------


# Verifies: REQ-d00327-A
@pytest.mark.parametrize("origin", ["cwd", "working_dir", "root"])
def test_a_reporter_declaring_an_undeclarable_origin_is_refused(origin):
    """A misspelt origin is refused, not read as the repository root."""
    with pytest.raises(ValueError) as excinfo:
        ReporterSpec(
            name="misdeclared",
            channel="file",
            kind="coverage",
            parser_factory=lambda: None,
            path_origin=origin,
        )
    message = str(excinfo.value)
    assert "misdeclared" in message and repr(origin) in message
    assert PATH_ORIGIN_ROOT in message and PATH_ORIGIN_CWD in message


# ---------------------------------------------------------------------------
# H -- the test names in coverage contexts follow the results origin
# ---------------------------------------------------------------------------

_CODE_FILE = "app/src/work.py"

_CODE_SOURCE = """\
# Implements: REQ-p00001-A
def work():
    return 1
"""

_CONTEXT_CONFIG = """\
version = 5

[project]
name = "origin"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[scanning.code]
directories = ["app/src"]

[scanning.test]
enabled = true
directories = ["app/tests"]
file_patterns = ["test_*.py"]

[[scanning.test.targets]]
name = "unit"
cwd = "app"
reporter = "pytest-json"
results = "report.json"
coverage = "coverage.json"
match = "source"
{extra}"""


def _context_project(
    tmp_path: Path,
    recorded: str,
    extra: str = "",
    measured: str = "src/work.py",
    also_measured: tuple[str, ...] = (),
) -> Path:
    """A target in `app/` whose results and coverage contexts name the test as *recorded*.

    Each path in *also_measured* is a further measured file, with the same lines.
    """
    project = tmp_path / "project"
    _, report = _pytest_json(recorded)
    measurement = {
        "executed_lines": [2, 3],
        "missing_lines": [],
        "summary": {"num_statements": 2, "covered_lines": 2},
        "contexts": {
            "2": [f"{recorded}::test_logs_in|run"],
            "3": [f"{recorded}::test_logs_in|run"],
        },
    }
    # By default measured relative to the target's working directory, as
    # coverage.py run from `app/` records it.
    coverage = {"files": dict.fromkeys((measured, *also_measured), measurement)}
    files = {
        "spec/reqs.md": _SPEC,
        _TEST_FILE: _TEST_SOURCE,
        _CODE_FILE: _CODE_SOURCE,
        ".results/unit/report.json": report,
        ".results/unit/coverage.json": json.dumps(coverage),
        ".elspais.toml": _CONTEXT_CONFIG.format(extra=extra),
    }
    for rel, text in files.items():
        path = project / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return project


def _attributed_lines(project: Path) -> int:
    from elspais.graph.factory import build_graph

    graph = build_graph(config_path=project / ".elspais.toml", repo_root=project)
    rollup = graph.find_by_id("REQ-p00001").get_metric("rollup_metrics")
    assert rollup.code_tested.has_contexts is True
    assert rollup.code_tested.covered_lines > 0, "the coverage itself was read"
    return rollup.code_tested.attributed_lines


# Verifies: REQ-d00327-H, REQ-d00327-D
def test_a_repo_root_relative_context_credits_its_test_by_default(tmp_path):
    assert _attributed_lines(_context_project(tmp_path, _TEST_FILE)) > 0


# Verifies: REQ-d00327-H, REQ-d00327-B
def test_a_working_directory_relative_context_credits_where_the_results_origin_says_so(
    tmp_path,
):
    project = _context_project(tmp_path, "tests/test_login.py", _origin_line(PATH_ORIGIN_CWD))
    assert _attributed_lines(project) > 0


# Verifies: REQ-d00327-H
def test_a_working_directory_relative_context_read_from_the_root_credits_nothing(tmp_path):
    assert _attributed_lines(_context_project(tmp_path, "tests/test_login.py")) == 0


# Verifies: REQ-d00327-H, REQ-d00327-B
def test_the_test_names_in_contexts_follow_the_results_origin_not_the_coverage_origin(
    tmp_path,
):
    """The coverage tool records its measured path from the root while the runner
    names its tests from `app/`: each is read from its own origin."""
    project = _context_project(
        tmp_path,
        "tests/test_login.py",
        _origin_line(PATH_ORIGIN_CWD) + f'coverage_origin = "{PATH_ORIGIN_ROOT}"\n',
        measured=_CODE_FILE,
    )
    assert _attributed_lines(project) > 0


# ---------------------------------------------------------------------------
# I -- coverage of which no measured file is scanned is reported
# ---------------------------------------------------------------------------

_COVERAGE_FILE = ".results/unit/coverage.json"


def _coverage_faults(graph) -> list:
    """The coverage-stage ingestion faults recorded for target `unit`."""
    return [
        fault
        for entry in graph.iter_repos()
        for fault in graph.ingestion_faults(namespace=entry.namespace)
        if fault.stage == "coverage" and fault.target == "unit"
    ]


def _covered_lines(graph) -> int:
    rollup = graph.find_by_id("REQ-p00001").get_metric("rollup_metrics")
    return rollup.code_tested.covered_lines


def _build_with_code(project: Path):
    from elspais.graph.factory import build_graph

    return build_graph(config_path=project / ".elspais.toml", repo_root=project)


# Verifies: REQ-d00327-I
def test_coverage_read_from_an_origin_where_nothing_is_scanned_is_reported(tmp_path):
    """Repo-root-relative coverage read from the target's working directory
    (the default for coverage) names `app/app/src/work.py`, which is not
    scanned, so the coverage credits nothing and is reported."""
    graph = _build_with_code(_context_project(tmp_path, _TEST_FILE, measured=_CODE_FILE))
    assert _covered_lines(graph) == 0, "no measured file attached"

    (fault,) = _coverage_faults(graph)

    assert fault.path == _COVERAGE_FILE
    assert PATH_ORIGIN_CWD in fault.cause, "the origin it was read from"
    assert repr(_CODE_FILE) in fault.cause, "one path as recorded"


# Verifies: REQ-d00327-I
def test_the_health_check_reports_coverage_read_from_an_origin_where_nothing_is_scanned(
    tmp_path,
):
    from elspais.commands.health import check_ingestion_faults

    graph = _build_with_code(_context_project(tmp_path, _TEST_FILE, measured=_CODE_FILE))

    check = check_ingestion_faults(graph, {})

    assert check.passed is False
    (finding,) = (f for f in check.findings if f.file_path == _COVERAGE_FILE)
    assert "target unit" in finding.message
    assert PATH_ORIGIN_CWD in finding.message
    assert repr(_CODE_FILE) in finding.message


# Verifies: REQ-d00327-I
@pytest.mark.parametrize(
    "measured,also_measured,extra",
    [
        (_CODE_FILE, (), f'coverage_origin = "{PATH_ORIGIN_ROOT}"\n'),
        ("src/work.py", ("/elsewhere/vendor/lib.py",), ""),
    ],
    ids=["read-from-the-root", "one-of-two-scanned"],
)
def test_coverage_of_which_a_measured_file_is_scanned_is_not_reported(
    tmp_path, measured, also_measured, extra
):
    project = _context_project(
        tmp_path, _TEST_FILE, extra, measured=measured, also_measured=also_measured
    )
    graph = _build_with_code(project)
    assert _covered_lines(graph) > 0, "the scanned file's lines attached"

    assert _coverage_faults(graph) == []


# ---------------------------------------------------------------------------
# The declared origin and the fingerprint judgement compose: results read from
# the target's working directory still bind once their run is judged stale,
# and are carried with the reason; coverage read from its own declared origin
# is carried by the same judgement.
# ---------------------------------------------------------------------------

_JUDGED_CONFIG = """\
version = 5

[project]
name = "origin"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[scanning.code]
directories = ["app/src"]

[scanning.test]
enabled = true
directories = ["app/tests"]
file_patterns = ["test_*.py"]

[[scanning.test.targets]]
name = "unit"
cwd = "app"
reporter = "{reporter}"
results = "{results}"
coverage = "coverage.json"
match = "source"
results_origin = "{results_origin}"
coverage_origin = "{coverage_origin}"
"""

# The runner, run in `app/`, names its test from there; the coverage tool
# records the measured file from the repository root.
_RECORDED_TEST = "tests/test_login.py"


def _recorded_project(tmp_path: Path, reporter: str) -> Path:
    """A target in `app/` whose results and coverage are written by one recorded run.

    The results record the test relative to the working directory and declare
    that origin; the coverage records the code file relative to the repository
    root and declares that origin.
    """
    project = tmp_path / "project"
    results_name, report = _REPORTS[reporter](_RECORDED_TEST)
    measurement = {
        "executed_lines": [2, 3],
        "missing_lines": [],
        "summary": {"num_statements": 2, "covered_lines": 2},
        "contexts": {
            "2": [f"{_RECORDED_TEST}::test_logs_in|run"],
            "3": [f"{_RECORDED_TEST}::test_logs_in|run"],
        },
    }
    files = {
        "spec/reqs.md": _SPEC,
        _TEST_FILE: _TEST_SOURCE,
        _CODE_FILE: _CODE_SOURCE,
        ".elspais.toml": _JUDGED_CONFIG.format(
            reporter=reporter,
            results=results_name,
            results_origin=PATH_ORIGIN_CWD,
            coverage_origin=PATH_ORIGIN_ROOT,
        ),
    }
    for rel, text in files.items():
        path = project / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    record_run(
        project,
        "unit",
        {results_name: report, "coverage.json": json.dumps({"files": {_CODE_FILE: measurement}})},
    )
    return project


def _change_an_input(project: Path) -> None:
    """Edit the target's own test file after its run, as an author does."""
    with (project / _TEST_FILE).open("a", encoding="utf-8") as fh:
        fh.write("\n# Edited after the run.\n")


def _assert_stale_because_the_test_changed(reason: str) -> None:
    assert reason.startswith("inputs changed since it ran:"), reason
    assert _TEST_FILE in reason, reason


# Verifies: REQ-d00327-B+C, REQ-d00323-F
@pytest.mark.parametrize("reporter", ["junit", "pytest-json"])
def test_results_read_from_the_declared_origin_bind_fresh_and_carried_alike(tmp_path, reporter):
    """The judgement decides whether the results are carried and the origin
    decides which test they bind to; neither answer moves the other."""
    project = _recorded_project(tmp_path, reporter)

    fresh = _the_result(_build_with_code(project))
    assert _bound_tests(fresh) == [_TEST_FILE]
    assert fresh.get_field("path_origin") == PATH_ORIGIN_CWD
    assert fresh.get_field("carried") is False
    assert fresh.get_field("stale_reason") == ""

    _change_an_input(project)
    stale = _the_result(_build_with_code(project))

    assert _bound_tests(stale) == [_TEST_FILE], "the origin still applies once stale"
    assert stale.get_field("path_origin") == PATH_ORIGIN_CWD
    assert stale.get_field("carried") is True
    _assert_stale_because_the_test_changed(stale.get_field("stale_reason"))


# Verifies: REQ-d00327-B+H, REQ-d00323-I
def test_coverage_read_from_the_declared_origin_is_carried_when_its_run_is_stale(tmp_path):
    """Coverage placed from the repository root, with its contexts naming the
    test from the working directory, keeps every line and its attribution once
    the run is stale, and records why."""
    project = _recorded_project(tmp_path, "pytest-json")

    def _code_file(graph):
        return next(
            f
            for f in graph.iter_by_kind(NodeKind.FILE)
            if f.get_field("relative_path") == _CODE_FILE
        )

    fresh = _build_with_code(project)
    assert _code_file(fresh).get_field("line_coverage_stale_reason") == ""
    fresh_lines = fresh.find_by_id("REQ-p00001").get_metric("rollup_metrics").code_tested
    assert fresh_lines.attributed_lines > 0
    assert fresh_lines.carried is False

    _change_an_input(project)
    stale = _build_with_code(project)

    assert _code_file(stale).get_field("line_coverage"), "the coverage still attaches"
    _assert_stale_because_the_test_changed(
        _code_file(stale).get_field("line_coverage_stale_reason")
    )
    stale_lines = stale.find_by_id("REQ-p00001").get_metric("rollup_metrics").code_tested
    assert (stale_lines.covered_lines, stale_lines.attributed_lines) == (
        fresh_lines.covered_lines,
        fresh_lines.attributed_lines,
    )
    assert stale_lines.carried is True
    _assert_stale_because_the_test_changed(stale_lines.stale_reason)
