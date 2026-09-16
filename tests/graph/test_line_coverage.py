# Verifies: REQ-d00254-B
# Verifies: REQ-d00258-C
# Verifies: REQ-d00258-W
"""Line coverage is measured, aggregated and reported apart from the
*Traceability* dimensions.

``code_tested`` counts LINES of implementation a run executed;
``CoverageDimension`` counts *Assertions* somebody wrote evidence for. They are
different measurements over different populations, so line coverage has its own
type (:class:`LineCoverage`), its own aggregation
(:func:`aggregate_line_coverage`) and its own health check
(:func:`check_line_coverage`) -- REQ-d00254-B keeps it beside the traceability
dimensions and never folded into them.

The other rule these pin is REQ-d00258-W: coverage tooling that reports only
aggregate hit counts records no per-test context, so it cannot say which test
reached a line. A surface must then render nothing rather than a ``0`` that
would read as "no test exercises this".
"""

import pytest

from elspais.commands.health import check_line_coverage
from elspais.graph.aggregation import aggregate_line_coverage
from elspais.graph.annotators import annotate_coverage
from elspais.graph.GraphNode import make_file_id
from elspais.graph.metrics import LineCoverage
from tests.core.graph_test_helpers import (
    HELPER_NAMESPACE,
    build_graph,
    make_code_ref,
    make_requirement,
    make_test_ref,
)

# Lines 10-12 implement the requirement -- a function whose extent the
# pre-scan knows, cited by the comment on line 9 above its ``def``, which is
# where a ``# Implements:`` is written. The run executed 10 and 12. Because
# the extent is the function's, it is known whether or not any run measured
# it (REQ-d00254-D).
_CITATION_LINE = 9
_FUNC_START, _FUNC_END = 10, 12
_PARTIAL_COVERAGE = {10: 1, 11: 0, 12: 1}


def _graph(
    *,
    line_coverage: dict[int, int] | None,
    line_contexts: dict[int, list[str]] | None = None,
    status: str = "Active",
):
    """A requirement implemented by a function on lines 10-12 of one file --
    cited by the comment on line 9, above its ``def`` -- plus a verifying
    test, with the file's coverage data set as given."""
    req = make_requirement(
        "REQ-p00001",
        title="Line Coverage Req",
        level="PRD",
        status=status,
        assertions=[{"label": "A", "text": "SHALL do A"}],
    )
    graph = build_graph(
        req,
        make_code_ref(
            implements=["REQ-p00001"],
            source_path="src/module.py",
            start_line=_CITATION_LINE,
            end_line=_CITATION_LINE,
            function_name="do_a",
            function_line=_FUNC_START,
            function_end_line=_FUNC_END,
        ),
        make_test_ref(
            verifies=["REQ-p00001"],
            source_path="tests/test_feat.py",
            function_name="test_widget",
            start_line=1,
            end_line=5,
            function_line=1,
        ),
    )
    if line_coverage is not None:
        file_node = graph.find_by_id(make_file_id(HELPER_NAMESPACE, "src/module.py"))
        assert file_node is not None
        file_node.set_field("line_coverage", line_coverage)
        file_node.set_field("executable_lines", len(line_coverage))
        if line_contexts is not None:
            file_node.set_field("line_contexts", line_contexts)
    annotate_coverage(graph)
    return graph


# The contexts pytest-cov writes for the verifying test above. Only line 10
# carries one, so attribution is real but partial.
_CONTEXTS = {10: ["tests/test_feat.py::test_widget|run"]}


class TestLineCoverageIsNotACoverageDimension:
    """REQ-d00254-B: line coverage is a measurement in lines, kept apart."""

    def test_rollup_carries_a_line_type_not_a_dimension(self):
        """``code_tested`` is a ``LineCoverage``. Nothing about it is
        per-*Assertion*, so it carries none of the four measures and no
        pass/fail verdict."""
        rollup = (
            _graph(line_coverage=_PARTIAL_COVERAGE)
            .find_by_id("REQ-p00001")
            .get_metric("rollup_metrics")
        )
        assert isinstance(rollup.code_tested, LineCoverage)
        assert rollup.code_tested.total_lines == 3
        assert rollup.code_tested.covered_lines == 2
        for absent in ("total_by_label", "covered", "has_failures", "immediate_direct_by_label"):
            assert not hasattr(rollup.code_tested, absent), absent


class TestAggregateLineCoverage:
    """``aggregate_line_coverage`` sums the lines, in its own aggregate."""

    def test_sums_lines_and_counts_requirements(self):
        agg = aggregate_line_coverage(_graph(line_coverage=_PARTIAL_COVERAGE))
        assert agg.total_lines == 3
        assert agg.covered_lines == 2
        assert agg.req_count == 1
        assert agg.req_with_covered == 1

    def test_an_unmeasured_estate_reports_nothing_not_an_empty_denominator(self):
        """Lines are counted from the coverage map, so an estate no run
        measured reports NOTHING -- not a denominator of lines with nothing
        covered.

        The coverage map is the only thing that knows which lines are code: a
        function's extent spans its docstring, its blanks and its comments,
        none of which any run can reach. Counting those would make "0/3 lines
        covered" a claim about the tests when it is a fact about the data, and
        would report every requirement as less covered than its code is. So
        the requirement leaves the aggregate entirely and ``has_measurement``
        is what says why -- the same question ``has_attribution`` answers one
        level down for per-test contexts.
        """
        agg = aggregate_line_coverage(_graph(line_coverage=None))
        assert agg.total_lines == 0
        assert agg.covered_lines == 0
        assert agg.req_count == 0
        assert agg.req_with_covered == 0
        assert agg.has_measurement is False

        # The contrast: the same requirement, measured, IS in the aggregate.
        measured = aggregate_line_coverage(_graph(line_coverage=_PARTIAL_COVERAGE))
        assert measured.req_count == 1
        assert measured.has_measurement is True

    # Verifies: REQ-d00258-C
    def test_excluded_statuses_are_excluded_here_too(self):
        """The same status-inclusion gate as the assertion dimensions, so the
        two reports describe one estate rather than two."""
        agg = aggregate_line_coverage(_graph(line_coverage=_PARTIAL_COVERAGE, status="Draft"))
        assert agg.req_count == 0
        assert agg.total_lines == 0

    def test_level_filter_narrows_the_estate(self):
        graph = _graph(line_coverage=_PARTIAL_COVERAGE)
        assert aggregate_line_coverage(graph, level_filter=lambda lv: lv == "DEV").req_count == 0
        assert aggregate_line_coverage(graph, level_filter=lambda lv: lv == "PRD").req_count == 1

    # Verifies: REQ-d00258-W
    @pytest.mark.parametrize(
        "contexts,expected_attributed,expected_has",
        [(None, 0.0, False), (_CONTEXTS, 1.0, True)],
        ids=["aggregate-only", "per-test-contexts"],
    )
    def test_has_attribution_distinguishes_absent_from_zero(
        self, contexts, expected_attributed, expected_has
    ):
        """Aggregate-only coverage records no naming context, so nothing is
        attributed AND ``has_attribution`` is false -- the two facts a surface
        needs to tell "no test reached this" from "the question was not
        asked"."""
        agg = aggregate_line_coverage(
            _graph(line_coverage=_PARTIAL_COVERAGE, line_contexts=contexts)
        )
        assert agg.attributed_lines == expected_attributed
        assert agg.has_attribution is expected_has
        assert agg.req_with_attribution == (1 if expected_has else 0)


class TestCheckLineCoverage:
    """The health check reports lines, never fails the build."""

    def test_reports_lines_and_never_fails(self):
        check = check_line_coverage(_graph(line_coverage=_PARTIAL_COVERAGE))
        assert check.name == "code.code_tested"
        assert check.category == "code"
        assert check.severity == "info"
        assert check.passed is True
        assert "1/1 REQs with covered implementation lines" in check.message
        assert "2/3 lines covered (67%)" in check.message

    def test_details_payload_carries_the_line_figures(self):
        details = check_line_coverage(_graph(line_coverage=_PARTIAL_COVERAGE)).details
        assert details["dimension"] == "code_tested"
        assert details["total_lines"] == 3
        assert details["covered_lines"] == 2
        assert details["covered_pct"] == pytest.approx(66.7, abs=0.1)
        assert details["total_requirements"] == 1
        assert details["reqs_with_covered_lines"] == 1

    # Verifies: REQ-d00258-W
    def test_attribution_is_reported_when_the_tooling_produced_it(self):
        check = check_line_coverage(
            _graph(line_coverage=_PARTIAL_COVERAGE, line_contexts=_CONTEXTS)
        )
        assert "1/3 attributed to a verifying test (33%)" in check.message
        assert check.details["attributed_lines"] == 1
        assert check.details["attributed_pct"] == pytest.approx(33.3, abs=0.1)

    # Verifies: REQ-d00258-W
    def test_absent_attribution_is_said_rather_than_shown_as_zero(self):
        """Aggregate-only coverage must produce no attribution figure at all:
        a "0/3 attributed" would read as a finding about the tests rather than
        about the coverage data."""
        check = check_line_coverage(_graph(line_coverage=_PARTIAL_COVERAGE))
        assert "per-test attribution not available from this coverage data" in check.message
        assert "attributed to a verifying test" not in check.message
        assert "attributed_lines" not in check.details
        assert "attributed_pct" not in check.details

    # Verifies: REQ-d00254-B
    def test_unmeasured_implementation_is_said_rather_than_shown_as_zero(self):
        """No coverage run ingested at all is not the same fact as a run that
        reached nothing, so it must not be reported through the same zero:
        "0/N lines covered" would read as a finding about the tests."""
        check = check_line_coverage(_graph(line_coverage=None))
        assert check.passed is True
        assert "no line-coverage data ingested" in check.message
        assert "lines covered" not in check.message
        assert check.details["has_measurement"] is False
        assert "covered_pct" not in check.details
