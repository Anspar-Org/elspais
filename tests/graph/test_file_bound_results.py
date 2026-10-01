# Verifies: REQ-d00274-I+J+K
"""Results that bind to tests only through the file holding them.

A source-matched result whose source file holds tests but whose line matches
none of them binds to every test in that file. It names no test, so it credits
nothing (REQ-d00254-G). These tests pin that such results are reported as a
finding (REQ-d00274-I), at the severity the project configures (J), and that
a coverage summary states their number apart from its figures whatever that
severity is (K).

Each scenario is a small real project built through ``build_graph``: a JUnit
target with ``match = "source"`` and ``line_base = 1``, so the builder decides
the binding scope itself.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from elspais.commands.health import (
    check_file_bound_results,
    check_unmatched_results,
    run_test_checks,
)
from elspais.commands.summary import render_summary
from elspais.graph.aggregation import collect_coverage, iter_file_bound_results
from elspais.graph.annotators import result_names_no_test
from elspais.graph.GraphNode import NodeKind
from elspais.graph.metrics import tested_and_passing

_CONFIG = """\
version = 5

[project]
name = "file-bound"
namespace = "REQ"

[levels.dev]
rank = 1
letter = "d"
implements = ["dev"]

[id-patterns]
canonical = "{namespace}-{level.letter}{component}"

[id-patterns.component]
style = "numeric"
digits = 5
leading_zeros = true

[scanning.spec]
directories = ["spec"]

[scanning.test]
enabled = true
directories = ["tests"]
file_patterns = ["test_*.py"]
output_root = "results"

[[scanning.test.targets]]
name = "junit"
reporter = "junit"
results = "*.xml"
match = "source"
line_base = 1

[rules.format]
require_hash = false
require_assertions = false
require_status = false
"""

_SPEC = """\
# Requirements

---

### REQ-d00001: Login

**Level**: dev | **Status**: Active

## Assertions

A. The system SHALL accept valid credentials.

*End* *Login*
---
"""

# test_one is declared on line 2 and test_two on line 7.
_TEST_A = """\
# Verifies: REQ-d00001-A
def test_one():
    pass


# Verifies: REQ-d00001-A
def test_two():
    pass
"""

_TEST_B = "def test_nothing():\n    pass\n"

TEST_ONE = "test:tests/test_a.py::test_one"
TEST_TWO = "test:tests/test_a.py::test_two"
TEST_NOTHING = "test:tests/test_b.py::test_nothing"

# One <testcase> per entry. ``line`` None leaves the attribute out.
_PRECISE_ONE = ("test_one", "tests/test_a.py", 2)
_PRECISE_TWO = ("test_two", "tests/test_a.py", 7)
_LINE_MATCHES_NONE = ("test_gone", "tests/test_a.py", 40)
_NO_LINE = ("test_unlined", "tests/test_a.py", None)
_FILE_HAS_NO_TESTS = ("test_elsewhere", "tests/test_missing.py", 4)


def _junit(cases) -> str:
    rows = []
    for name, source, line in cases:
        line_attr = f' line="{line}"' if line is not None else ""
        rows.append(
            f'  <testcase name="{name}" classname="tests.x" file="{source}"{line_attr} time="0.1"/>'
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<testsuite name="s" tests="{len(rows)}">\n' + "\n".join(rows) + "\n</testsuite>\n"
    )


def _project(root: Path, artifacts: dict[str, list]):
    """Build a project whose junit target reads the given artifacts.

    ``artifacts`` maps a results file name to the testcases it holds.
    Returns the federated graph and the repository's configuration.
    """
    from elspais.graph.factory import build_graph

    (root / "spec").mkdir(parents=True)
    (root / "tests").mkdir()
    out = root / "results" / "junit"
    out.mkdir(parents=True)
    (root / ".elspais.toml").write_text(_CONFIG)
    (root / "spec" / "requirements.md").write_text(_SPEC)
    (root / "tests" / "test_a.py").write_text(_TEST_A)
    (root / "tests" / "test_b.py").write_text(_TEST_B)
    for name, cases in artifacts.items():
        (out / name).write_text(_junit(cases))
    graph = build_graph(repo_root=root)
    (entry,) = list(graph.iter_repos())
    return graph, entry.config


def _with_severity(config: dict, severity: str) -> dict:
    rules = dict(config.get("rules") or {})
    rules["severity"] = {**(rules.get("severity") or {}), "tests.file_bound_results": severity}
    return {**config, "rules": rules}


def _result_named(graph, name: str):
    for node in graph.iter_by_kind(NodeKind.RESULT):
        if node.get_field("name") == name:
            return node
    raise AssertionError(f"no RESULT named {name!r}")


def _repo_root(graph) -> Path:
    (entry,) = list(graph.iter_repos())
    return entry.repo_root


def _render_all(data: dict, config: dict) -> dict[str, str]:
    return {fmt: render_summary(dict(data), fmt, config) for fmt in ("text", "markdown", "csv")}


_SENTENCE = "name no test, only the file holding their tests"
_CSV_LABEL = "Results Naming No Test"


@pytest.fixture(scope="module")
def mixed(tmp_path_factory):
    """One artifact holding a precise result, two file-bound results and one
    result whose file holds no tests."""
    root = tmp_path_factory.mktemp("mixed") / "proj"
    return _project(
        root,
        {
            "results.xml": [_PRECISE_ONE, _LINE_MATCHES_NONE, _NO_LINE, _FILE_HAS_NO_TESTS],
        },
    )


@pytest.fixture(scope="module")
def precise(tmp_path_factory):
    """Every result binds at test scope."""
    root = tmp_path_factory.mktemp("precise") / "proj"
    return _project(root, {"results.xml": [_PRECISE_ONE, _PRECISE_TWO]})


class TestTheFindingNamesTheArtifact:
    """REQ-d00274-I: the report names the artifact and the candidate tests."""

    # Verifies: REQ-d00274-I+J
    def test_REQ_d00274_I_one_finding_per_artifact_naming_its_candidate_tests(self, mixed):
        graph, config = mixed
        check = check_file_bound_results(graph, config)

        assert check.name == "tests.file_bound_results"
        assert check.passed is False
        assert check.severity == "warning"
        assert check.details == {"count": 2, "artifacts": 1}
        assert "2 ingested result(s) in 1 artifact(s) name no test" in check.message
        (finding,) = check.findings
        assert finding.file_path == "results/junit/results.xml"
        # The lower of the two records' lines in the artifact.
        lines = [
            _result_named(graph, name).get_field("result_line")
            for name in (_LINE_MATCHES_NONE[0], _NO_LINE[0])
        ]
        assert finding.line == min(lines)
        assert "2 result(s) in results/junit/results.xml" in finding.message
        # Every test in the file the records name, and none from another file.
        assert finding.related == [TEST_ONE, TEST_TWO]
        assert TEST_NOTHING not in finding.related
        assert finding.repo == "file-bound"

    # Verifies: REQ-d00274-I
    def test_REQ_d00274_I_each_artifact_is_its_own_finding(self, tmp_path):
        graph, config = _project(
            tmp_path / "proj",
            {"first.xml": [_LINE_MATCHES_NONE], "second.xml": [_NO_LINE, _PRECISE_TWO]},
        )
        check = check_file_bound_results(graph, config)

        assert check.details == {"count": 2, "artifacts": 2}
        assert sorted(f.file_path for f in check.findings) == [
            "results/junit/first.xml",
            "results/junit/second.xml",
        ]

    # Verifies: REQ-d00274-I
    def test_REQ_d00274_I_the_check_is_one_of_the_test_checks(self, mixed):
        graph, config = mixed
        names = {c.name for c in run_test_checks(graph, config=config)}
        assert "tests.file_bound_results" in names

    # Verifies: REQ-d00274-I
    def test_REQ_d00274_I_precise_results_raise_no_finding(self, precise):
        graph, config = precise
        check = check_file_bound_results(graph, config)

        assert check.passed is True
        assert check.findings == []


class TestSeverityIsTheProjects:
    """REQ-d00274-J: configured severity, else a warning."""

    # Verifies: REQ-d00274-J
    @pytest.mark.parametrize("severity", ["error", "warning", "info"])
    def test_REQ_d00274_J_configured_severity_is_honoured(self, mixed, severity):
        graph, config = mixed
        check = check_file_bound_results(graph, _with_severity(config, severity))

        assert check.passed is False
        assert check.severity == severity
        assert len(check.findings) == 1

    # Verifies: REQ-d00274-J
    def test_REQ_d00274_J_off_withholds_the_finding(self, mixed):
        graph, config = mixed
        check = check_file_bound_results(graph, _with_severity(config, "off"))

        assert check.passed is True
        assert check.severity == "info"
        assert check.findings == []
        assert "not reported" in check.message


class TestTheSummaryStatesTheNumber:
    """REQ-d00274-K: the number stands apart from the figures, exactly where
    any exist, whatever severity their finding carries."""

    # Verifies: REQ-d00274-K
    @pytest.mark.parametrize("severity", ["warning", "error", "off"])
    def test_REQ_d00274_K_the_number_is_stated_whatever_the_severity(self, mixed, severity):
        graph, base = mixed
        config = _with_severity(base, severity)
        data = collect_coverage(graph, config)

        assert data["file_bound_results"] == {
            "count": 2,
            "artifacts": [
                {"namespace": "REQ", "artifact": "results/junit/results.xml", "count": 2}
            ],
        }
        rendered = _render_all(data, config)
        assert f"2 result(s) in 1 artifact(s) {_SENTENCE}" in rendered["text"]
        assert f"2 result(s) in 1 artifact(s) {_SENTENCE}" in rendered["markdown"]
        assert f"{_CSV_LABEL},2,Artifacts,1" in rendered["csv"]

    # Verifies: REQ-d00274-K
    def test_REQ_d00274_K_nothing_is_stated_where_none_exist(self, precise):
        graph, config = precise
        data = collect_coverage(graph, config)

        assert "file_bound_results" not in data
        for fmt, text in _render_all(data, config).items():
            assert _SENTENCE not in text, fmt
            assert _CSV_LABEL not in text, fmt
        assert "file_bound_results" not in render_summary(dict(data), "json", config)

    # Verifies: REQ-d00274-K
    @pytest.mark.parametrize("severity", ["warning", "off"])
    def test_REQ_d00274_K_json_and_mcp_state_the_same_number(self, mixed, severity):
        pytest.importorskip("mcp")
        import json

        from elspais.mcp.server import _get_project_summary

        graph, base = mixed
        config = _with_severity(base, severity)
        cli = json.loads(render_summary(collect_coverage(graph, config), "json", config))
        mcp = _get_project_summary(graph, _repo_root(graph), config)

        assert cli["file_bound_results"]["count"] == 2
        assert mcp["file_bound_results"] == cli["file_bound_results"]

    # Verifies: REQ-d00274-K
    def test_REQ_d00274_K_mcp_states_nothing_where_none_exist(self, precise):
        pytest.importorskip("mcp")
        from elspais.mcp.server import _get_project_summary

        graph, config = precise
        assert "file_bound_results" not in _get_project_summary(graph, _repo_root(graph), config)


class TestDisjointFromUnmatched:
    """REQ-d00274-I: a result bound to no test is the unmatched check's, and a
    result bound to its file only is this check's; no result is in both."""

    # Verifies: REQ-d00274-I
    def test_REQ_d00274_I_each_result_is_reported_by_at_most_one_check(self, mixed):
        graph, config = mixed
        check = check_file_bound_results(graph, config)
        # Every file-bound result id, not only the one each finding leads with.
        file_bound = {rid for rec in iter_file_bound_results(graph) for rid in rec.result_ids}
        unmatched = {f.node_id for f in check_unmatched_results(graph, config).findings}

        assert {f.node_id for f in check.findings} <= file_bound
        precise_id = _result_named(graph, _PRECISE_ONE[0]).id
        bound_ids = {_result_named(graph, n).id for n in (_LINE_MATCHES_NONE[0], _NO_LINE[0])}
        orphan_id = _result_named(graph, _FILE_HAS_NO_TESTS[0]).id

        assert file_bound == bound_ids
        assert unmatched == {orphan_id}
        assert precise_id not in file_bound | unmatched
        assert file_bound.isdisjoint(unmatched)


class TestFileBoundResultsCreditNothing:
    """REQ-d00254-G: a result naming no test credits no Passing, and the
    predicate the report selects by is the one the annotator credits by."""

    # Verifies: REQ-d00254-G, REQ-d00274-I
    @pytest.mark.parametrize(
        "case,names_no_test,passing",
        [
            (_PRECISE_ONE, False, 1.0),
            (_LINE_MATCHES_NONE, True, 0.0),
            (_NO_LINE, True, 0.0),
        ],
        ids=["test-scope", "line-matches-no-test", "no-line-attribute"],
    )
    def test_REQ_d00274_I_a_file_bound_pass_credits_no_passing(
        self, tmp_path, case, names_no_test, passing
    ):
        graph, _config = _project(tmp_path / "proj", {"results.xml": [case]})
        result = _result_named(graph, case[0])
        rollup = graph.find_by_id("REQ-d00001").get_metric("rollup_metrics")

        assert result.get_field("status") == "passed"
        assert result_names_no_test(result) is names_no_test
        # Both tests cite A, so A is Tested whichever way the result bound.
        assert rollup.tested.covered == 1.0
        assert tested_and_passing(rollup).covered == passing
