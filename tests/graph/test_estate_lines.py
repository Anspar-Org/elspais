# Verifies: REQ-d00254-W+X
"""Estate-wide line figures count distinct lines over one set of files.

``aggregate_estate_lines`` states how many lines the estate holds, how many
ran, and how many of those that ran implement a counted requirement. A line
serving several requirements is one line (REQ-d00254-W), and every figure is
taken over the files whose source was analysed (REQ-d00254-X), so the
difference between two figures is itself a count of lines.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from elspais.graph.aggregation import aggregate_estate_lines, aggregate_line_coverage
from elspais.graph.annotators import annotate_coverage
from elspais.graph.federated import FederatedGraph
from elspais.graph.GraphNode import make_file_id
from tests.core.graph_test_helpers import (
    HELPER_NAMESPACE,
    build_graph,
    make_code_ref,
    make_requirement,
)

_MODULE = "src/module.py"

# do_shared (lines 10-12) implements both requirements through ONE citation.
# do_own (lines 20-22) implements the second requirement alone.
_SHARED = range(10, 13)
_OWN = range(20, 23)


def _req(req_id: str, status: str = "Active"):
    return make_requirement(
        req_id,
        title=req_id,
        level="PRD",
        status=status,
        assertions=[{"label": "A", "text": "SHALL do A"}],
    )


def _citation(implements: list[str], name: str, lines: range):
    return make_code_ref(
        implements=implements,
        source_path=_MODULE,
        start_line=lines.start - 1,
        end_line=lines.start - 1,
        function_name=name,
        function_line=lines.start,
        function_end_line=lines.stop - 1,
    )


def _graph(
    *,
    second_status: str = "Active",
    own: bool = False,
    line_coverage: dict[int, int] | None = None,
    source_analysed: bool | None = None,
):
    """Two requirements sharing do_shared; optionally the second also has do_own."""
    contents = [
        _req("REQ-p00001"),
        _req("REQ-p00002", status=second_status),
        _citation(["REQ-p00001", "REQ-p00002"], "do_shared", _SHARED),
    ]
    if own:
        contents.append(_citation(["REQ-p00002"], "do_own", _OWN))
    graph = build_graph(*contents)
    file_node = graph.find_by_id(make_file_id(HELPER_NAMESPACE, _MODULE))
    assert file_node is not None
    if line_coverage is not None:
        file_node.set_field("line_coverage", line_coverage)
        file_node.set_field("executable_lines", len(line_coverage))
    if source_analysed is not None:
        file_node.set_field("source_analysed", source_analysed)
    annotate_coverage(graph)
    return graph


def _all_hit(*ranges: range) -> dict[int, int]:
    return {ln: 1 for r in ranges for ln in r}


class TestALineIsCountedOnce:
    """REQ-d00254-W: a line serving two requirements is one line."""

    # Verifies: REQ-d00254-W
    def test_REQ_d00254_W_a_shared_line_is_counted_once(self):
        graph = _graph(line_coverage=_all_hit(_SHARED))

        estate = aggregate_estate_lines(graph)

        assert estate.requirement_executed_lines == 3
        # The per-requirement sum counts the same three lines twice; the
        # estate figure is not that sum.
        assert aggregate_line_coverage(graph).covered_lines == 6

    # Verifies: REQ-d00254-W
    def test_REQ_d00254_W_only_executed_lines_are_counted(self):
        graph = _graph(own=True, line_coverage={10: 1, 11: 0, 12: 1, 20: 0, 21: 1, 22: 0})

        estate = aggregate_estate_lines(graph)

        assert estate.executable_lines == 6
        assert estate.executed_lines == 3
        assert estate.requirement_executed_lines == 3

    # Verifies: REQ-d00254-W, REQ-d00258-C
    @pytest.mark.parametrize(
        "second_status,expected",
        [("Active", 6), ("Draft", 3)],
        ids=["counted", "excluded-status"],
    )
    def test_REQ_d00254_W_an_excluded_status_contributes_nothing(self, second_status, expected):
        """The same status gate as ``aggregate_line_coverage``: the second
        requirement's own function enters the requirement figure only while
        its status counts for coverage. The shared function still counts
        through the first requirement."""
        graph = _graph(second_status=second_status, own=True, line_coverage=_all_hit(_SHARED, _OWN))

        estate = aggregate_estate_lines(graph)

        assert estate.executed_lines == 6
        assert estate.requirement_executed_lines == expected
        assert estate.executed_without_requirement == 6 - expected


class TestEveryFigureOverOneSetOfFiles:
    """REQ-d00254-X: figures stated beside each other share their files."""

    # Verifies: REQ-d00254-X
    @pytest.mark.parametrize(
        "coverage",
        [_all_hit(_SHARED, _OWN), {10: 1, 11: 0, 12: 0, 20: 1, 21: 1, 22: 0}, {10: 0}],
        ids=["all-hit", "partial", "nothing-ran"],
    )
    def test_REQ_d00254_X_the_figures_nest(self, coverage):
        estate = aggregate_estate_lines(_graph(own=True, line_coverage=coverage))

        assert 0 <= estate.requirement_executed_lines <= estate.executed_lines
        assert estate.executed_lines <= estate.executable_lines
        assert (
            estate.executed_without_requirement
            == estate.executed_lines - estate.requirement_executed_lines
        )

    # Verifies: REQ-d00254-Q+X
    def test_REQ_d00254_X_an_unanalysed_file_enters_no_figure(self):
        """A counted requirement implementing lines in an unanalysed file
        contributes nothing: its lines ran in a file of unknown size."""
        graph = _graph(line_coverage=_all_hit(_SHARED), source_analysed=False)

        estate = aggregate_estate_lines(graph)

        assert estate.executable_lines == 0
        assert estate.executed_lines == 0
        assert estate.requirement_executed_lines == 0
        assert estate.unmeasured_files == 1

        # The contrast: the same file, analysed, is in every figure.
        analysed = aggregate_estate_lines(_graph(line_coverage=_all_hit(_SHARED)))
        assert analysed.executed_lines == 3
        assert analysed.requirement_executed_lines == 3
        assert analysed.unmeasured_files == 0


class TestProjectSummaryPublishesTheEstate:
    """The MCP project summary publishes the estate figures."""

    _KEYS = {
        "executable_lines",
        "executed_lines",
        "requirement_executed_lines",
        "executed_without_requirement",
        "unmeasured_files",
    }

    @staticmethod
    def _summary(graph):
        pytest.importorskip("mcp")
        from elspais.mcp.server import _get_project_summary

        fed = FederatedGraph.from_single(
            graph, config={"project": {"name": "test", "namespace": "REQ"}}, repo_root=Path(".")
        )
        return _get_project_summary(fed, Path("."))

    # Verifies: REQ-d00254-W+X
    def test_REQ_d00254_W_code_coverage_carries_the_estate_figures(self):
        result = self._summary(_graph(own=True, line_coverage=_all_hit(_SHARED, _OWN)))

        code = result["code_coverage"]
        assert set(code) == self._KEYS
        assert code["requirement_executed_lines"] == 6
        for retired in ("total_executable_lines", "total_covered_lines", "total_attributed_lines"):
            assert retired not in code

    # Verifies: REQ-d00254-W
    def test_REQ_d00254_W_nothing_measured_publishes_no_figure(self):
        assert "code_coverage" not in self._summary(_graph())

    # Verifies: REQ-d00254-Q
    def test_REQ_d00254_Q_an_estate_of_unanalysed_files_is_still_reported(self):
        result = self._summary(_graph(line_coverage=_all_hit(_SHARED), source_analysed=False))

        assert result["code_coverage"]["unmeasured_files"] == 1
        assert result["code_coverage"]["executed_lines"] == 0
