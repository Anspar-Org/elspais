# Verifies: REQ-d00294-A, REQ-d00294-B, REQ-d00294-C, REQ-d00294-E, REQ-d00294-F
"""A whole build over a grid: one test, many environments, many results.

A grid runs one test in several places and writes one record for each of
them. These tests build a real project from files on disk, so the records
travel the path a project's records travel: the glob that finds them, the
reporter that reads them, the identity the factory gives them and the test
they bind to. The unit tests beside this file hold the single ingestion
step; this file holds what a reader of the built graph gets.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from elspais.commands.health import check_test_results
from elspais.graph.GraphNode import NodeKind, parse_structural_id
from elspais.graph.metrics import tested_and_passing
from elspais.graph.relations import EdgeKind
from elspais.mcp.server import _serialize_test_info

_SPEC = """\
### REQ-p00001: Login

**Level**: PRD | **Status**: Active

The system SHALL let a user log in.

#### Assertions

A. The system SHALL accept valid credentials.

*End* *Login* | **Hash**: ________
"""

# A Python test, which a pytest-shaped report names by module and function.
_PY_TEST = """\
# Verifies: REQ-p00001-A
def test_logs_in():
    assert True
"""

# A Playwright test, which its own report names by the file it sits in.
_TS_TEST = """\
// Verifies: REQ-p00001-A
test('logs in', async () => {
  expect(true).toBe(true);
});
"""

_CONFIG = """\
version = 5

[project]
name = "grid"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[scanning.test]
enabled = true
directories = ["tests"]
file_patterns = ["{pattern}"]

[[scanning.test.targets]]
name = "{target}"
reporter = "{reporter}"
{target_body}"""


def _pytest_junit(*, failure: bool = False) -> str:
    """One pytest-shaped record, which names its test by module and function."""
    inner = '<failure message="timed out"/>' if failure else ""
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<testsuites>\n"
        '  <testsuite name="pytest" tests="1">\n'
        '    <testcase classname="tests.e2e.test_login" name="test_logs_in" time="0.5">'
        f"{inner}</testcase>\n"
        "  </testsuite>\n"
        "</testsuites>\n"
    )


def _playwright_junit(*hosts: tuple[str, bool]) -> str:
    """One Playwright-shaped report: a suite for each project it ran.

    Playwright writes one `<testsuite>` for each project, carries the
    project name in `hostname`, names the test by the file it sits in and
    writes no `file` attribute. Every record of one grid therefore agrees
    about everything the tool reads except the suite it sits in.
    """
    suites = []
    for host, failure in hosts:
        inner = '<failure message="timed out"/>' if failure else ""
        suites.append(
            f'  <testsuite name="login.spec.ts" hostname="{host}" tests="1">\n'
            '    <testcase classname="login.spec.ts" name="logs in" time="0.5">'
            f"{inner}</testcase>\n"
            "  </testsuite>\n"
        )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n<testsuites>\n'
        + "".join(suites)
        + "</testsuites>\n"
    )


def _project(
    tmp_path: Path,
    *,
    target_body: str,
    artifacts: dict[str, str],
    test_file: str = "tests/e2e/test_login.py",
    test_source: str = _PY_TEST,
    pattern: str = "test_*.py",
    reporter: str = "junit",
    target: str = "e2e",
) -> Path:
    """An on-disk project: one requirement, one scanned test, some reports."""
    project = tmp_path / "project"
    (project / "spec").mkdir(parents=True)
    (project / "spec" / "reqs.md").write_text(_SPEC, encoding="utf-8")

    source = project / test_file
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(test_source, encoding="utf-8")

    for relative, text in artifacts.items():
        artifact = project / relative
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text(text, encoding="utf-8")

    (project / ".elspais.toml").write_text(
        _CONFIG.format(pattern=pattern, reporter=reporter, target=target, target_body=target_body),
        encoding="utf-8",
    )
    return project


def _build(project: Path, **kwargs):
    from elspais.graph.factory import build_graph

    return build_graph(
        config_path=project / ".elspais.toml", repo_root=project, scan_code=False, **kwargs
    )


def _results(graph) -> list:
    return sorted(graph.iter_by_kind(NodeKind.RESULT), key=lambda n: n.id)


def _tests_yielding(results) -> list:
    """The distinct test nodes the results are bound to.

    A YIELDS edge is built ``test.link(result)``, so the test is the parent.
    """
    seen: dict[str, object] = {}
    for result in results:
        for parent in result.iter_parents(edge_kinds={EdgeKind.YIELDS}):
            seen[parent.id] = parent
    return list(seen.values())


# One artifact for each device, found by one glob. The wildcard segment of
# that glob is the device the records under it were written on.
_DEVICE_GRID = {
    "target_body": 'results = "evidence/*/junit.xml"\nenvironment = "results-path"\n',
    "artifacts": {
        "evidence/pixel-8/junit.xml": _pytest_junit(),
        "evidence/iphone-15/junit.xml": _pytest_junit(),
    },
}

# One artifact holding a suite for each browser. The suite says which one.
_BROWSER_GRID = {
    "target_body": (
        'results = "test-results/junit.xml"\n'
        'match = "source"\n'
        'classname = "source-file"\n'
        'environment = "suite-hostname"\n'
    ),
    "artifacts": {
        "test-results/junit.xml": _playwright_junit(("chromium", False), ("firefox", False)),
    },
    "test_file": "tests/e2e/login.spec.ts",
    "test_source": _TS_TEST,
    "pattern": "*.spec.ts",
}

_GRIDS = {
    "devices": (
        _DEVICE_GRID,
        [
            "result:REQ:evidence/iphone-15/junit.xml:1",
            "result:REQ:evidence/pixel-8/junit.xml:1",
        ],
        ["iphone-15", "pixel-8"],
    ),
    "browsers": (
        _BROWSER_GRID,
        [
            "result:REQ:test-results/junit.xml:1",
            "result:REQ:test-results/junit.xml:2",
        ],
        ["chromium", "firefox"],
    ),
}


@pytest.fixture(params=sorted(_GRIDS), ids=sorted(_GRIDS))
def grid(request, tmp_path):
    """A built grid, with the ids and environments its records should have."""
    kwargs, ids, environments = _GRIDS[request.param]
    graph = _build(_project(tmp_path, **kwargs))
    return graph, ids, environments


# Verifies: REQ-d00294-A
def test_a_grid_holds_every_record_as_its_own_result(grid):
    """Every record of the grid survives, told apart by where it was written.

    The records agree about the test, the class and the time, so without a
    place of record in the identity the later one takes the earlier one's
    place and its verdict is lost.
    """
    graph, ids, _ = grid

    assert [node.id for node in _results(graph)] == ids


# Verifies: REQ-d00294-A
def test_a_grid_binds_every_record_to_the_one_test(grid):
    """One test that ran in several places is still one test in the graph."""
    graph, _, _ = grid
    results = _results(graph)

    bound = _tests_yielding(results)

    assert len(bound) == 1
    assert bound[0].kind is NodeKind.TEST
    assert sum(1 for child in bound[0].iter_children() if child.kind is NodeKind.RESULT) == len(
        results
    )


# Verifies: REQ-d00294-C, REQ-d00294-F
def test_a_grid_carries_the_environment_on_each_record(grid):
    """The environment sits on the record, and the records are named alike.

    A reader tells the records apart by the environment beside them. The
    name stays the name of the one test that ran.
    """
    graph, _, environments = grid
    results = _results(graph)

    assert sorted(node.get_field("environment") for node in results) == environments
    assert len({node.get_label() for node in results}) == 1
    assert graph.ingestion_faults() == []


# Verifies: REQ-d00294-A
def test_a_result_is_placed_by_a_repo_relative_path(grid, tmp_path):
    """The place of record is repo-relative, so any checkout reads alike.

    An absolute path would put the machine that built the graph into every
    identity, and two checkouts of one project would disagree about which
    results they hold.
    """
    graph, _, _ = grid

    for node in _results(graph):
        _, _, place, _ = parse_structural_id(node.id)
        assert not Path(place).is_absolute()
        assert str(tmp_path) not in place


# Verifies: REQ-d00294-B
def test_a_captured_target_places_its_records_by_the_target(tmp_path):
    """Results read from a runner's output are placed by the target.

    No artifact holds them, so the place of record an artifact would give
    does not exist and the target is what the tool read them from.
    """
    stream = (
        '{"type":"suite","suite":{"id":0,"platform":"vm","path":"tests/e2e/test_login.py"}}\n'
        '{"type":"testStart","test":{"id":1,"name":"logs in","suiteID":0,'
        '"line":2,"column":1,"metadata":{},"root_line":2,"root_column":1}}\n'
        '{"type":"testDone","testID":1,"result":"success","hidden":false,"time":42}\n'
        '{"type":"testStart","test":{"id":2,"name":"logs in","suiteID":0,'
        '"line":2,"column":1,"metadata":{},"root_line":2,"root_column":1}}\n'
        '{"type":"testDone","testID":2,"result":"failure","hidden":false,"time":43}\n'
    )
    project = _project(
        tmp_path,
        target="widgets",
        reporter="flutter-machine",
        target_body='match = "source"\ncommand = "flutter test --machine"\n',
        artifacts={},
    )

    graph = _build(project, captured_results={"widgets": stream})

    results = _results(graph)
    assert [node.id for node in results] == ["result:REQ:widgets:1", "result:REQ:widgets:2"]
    assert {node.get_field("status") for node in results} == {"passed", "failed"}


# Verifies: REQ-d00294-E
def test_one_failing_record_takes_the_assertion_out_of_passing(tmp_path):
    """A test that failed in one place is not passing anywhere.

    The assertion stays tested, because the test that names it ran. It
    does not pass, because one of that test's own results failed.
    """
    grid = dict(_DEVICE_GRID)
    grid["artifacts"] = {
        "evidence/pixel-8/junit.xml": _pytest_junit(),
        "evidence/iphone-15/junit.xml": _pytest_junit(failure=True),
    }
    graph = _build(_project(tmp_path, **grid))

    metrics = graph.find_by_id("REQ-p00001").get_metric("rollup_metrics")

    assert metrics.tested.total_by_label.get("A") == 1.0
    assert metrics.verified.failing_labels == {"A"}
    assert tested_and_passing(metrics).total_by_label.get("A", 0.0) == 0.0


# Verifies: REQ-d00294-E, REQ-d00294-F
def test_the_failing_record_of_a_grid_is_the_one_reported(tmp_path):
    """The report names the record that failed and the place it failed in.

    Every record of the grid reads alike without that, so a reader learns
    that the test failed but not where.
    """
    grid = dict(_DEVICE_GRID)
    grid["artifacts"] = {
        "evidence/pixel-8/junit.xml": _pytest_junit(),
        "evidence/iphone-15/junit.xml": _pytest_junit(failure=True),
    }
    graph = _build(_project(tmp_path, **grid))

    chk = check_test_results(graph, config=None)

    assert chk.passed is False
    assert chk.details["failed"] == 1
    assert [f.node_id for f in chk.findings] == ["result:REQ:evidence/iphone-15/junit.xml:1"]
    assert "[iphone-15]" in chk.findings[0].message
    assert chk.findings[0].file_path == "evidence/iphone-15/junit.xml"


def _keys_anywhere(value) -> set[str]:
    """Every key in a nested envelope, however deep it sits."""
    found: set[str] = set()
    if isinstance(value, dict):
        found |= set(value)
        for item in value.values():
            found |= _keys_anywhere(item)
    elif isinstance(value, list):
        for item in value:
            found |= _keys_anywhere(item)
    return found


# Verifies: REQ-d00294-F
def test_a_project_in_one_environment_reads_as_it_did(tmp_path):
    """One environment, one report: the envelope carries no environment.

    Most projects run their tests in one place and declare no source for
    an environment. They get the test they had, with the results it had,
    and no key that was not there before.
    """
    project = _project(
        tmp_path,
        target_body='results = "reports/junit.xml"\n',
        artifacts={"reports/junit.xml": _pytest_junit()},
    )
    graph = _build(project)

    results = _results(graph)
    assert [node.id for node in results] == ["result:REQ:reports/junit.xml:1"]
    assert results[0].get_field("environment") is None

    test_node = _tests_yielding(results)[0]
    assert test_node.id == "test:tests/e2e/test_login.py::test_logs_in"
    envelope = _serialize_test_info(test_node, graph)
    assert "environment" not in _keys_anywhere(envelope)
    assert graph.ingestion_faults() == []


# Verifies: REQ-d00294-F
def test_a_test_is_named_the_same_whether_or_not_its_results_say_where(tmp_path):
    """Declaring an environment source moves no part of the test's name.

    The environment belongs to the result. The test is one test wherever
    it ran, so its identity and its label are untouched.
    """
    named = []
    for where, source in (("silent", ""), ("declared", 'environment = "results-path"\n')):
        grid = dict(_DEVICE_GRID, target_body='results = "evidence/*/junit.xml"\n' + source)
        graph = _build(_project(tmp_path / where, **grid))
        test_node = _tests_yielding(_results(graph))[0]
        relative = test_node.id.split("test:", 1)[1]
        named.append((relative, test_node.get_label(), test_node.get_field("function_name")))

    assert named[0] == named[1]
