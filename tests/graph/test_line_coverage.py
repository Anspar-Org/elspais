# Verifies: REQ-d00254-B
# Verifies: REQ-d00258-C
# Verifies: REQ-d00258-E
"""Line coverage is measured, aggregated and reported apart from the
*Traceability* dimensions.

``code_tested`` counts LINES of implementation a run executed;
``CoverageDimension`` counts *Assertions* somebody wrote evidence for. They are
different measurements over different populations, so line coverage has its own
type (:class:`LineCoverage`), its own aggregation
(:func:`aggregate_line_coverage`) and its own health check
(:func:`check_line_coverage`) -- REQ-d00254-B keeps it beside the traceability
dimensions and never folded into them.

The other rule these pin is REQ-d00258-E: coverage tooling that reports only
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

# Lines 10-12 implement the requirement; the run executed 10 and 12.
_IMPL_START, _IMPL_END = 10, 12
_PARTIAL_COVERAGE = {10: 1, 11: 0, 12: 1}


def _graph(
    *,
    line_coverage: dict[int, int] | None,
    line_contexts: dict[int, list[str]] | None = None,
    status: str = "Active",
):
    """A requirement implemented by lines 10-12 of one file, plus a verifying
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
            start_line=_IMPL_START,
            end_line=_IMPL_END,
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

    def test_lines_are_counted_from_the_implementation_not_the_coverage_file(self):
        """``total_lines`` is the implementation attributed to the requirement,
        so it is known even when no run measured it. Without coverage data the
        requirement is in the denominator with nothing covered.

        This is the shape the tool has always had, and it is worth pinning
        because the reading is easy to get wrong: "0/3 lines covered" here
        means no run was measured, not that the tests reached none of the
        code. What tells the two apart is whether any coverage data exists at
        all -- the caller in ``health.py`` only runs this check when some
        requirement has implementation lines, and ``has_attribution`` answers
        the same question one level down for per-test contexts.
        """
        agg = aggregate_line_coverage(_graph(line_coverage=None))
        assert agg.total_lines == 3
        assert agg.covered_lines == 0
        assert agg.req_count == 1
        assert agg.req_with_covered == 0

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

    # Verifies: REQ-d00258-E
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

    # Verifies: REQ-d00258-E
    def test_attribution_is_reported_when_the_tooling_produced_it(self):
        check = check_line_coverage(
            _graph(line_coverage=_PARTIAL_COVERAGE, line_contexts=_CONTEXTS)
        )
        assert "1/3 attributed to a verifying test (33%)" in check.message
        assert check.details["attributed_lines"] == 1
        assert check.details["attributed_pct"] == pytest.approx(33.3, abs=0.1)

    # Verifies: REQ-d00258-E
    def test_absent_attribution_is_said_rather_than_shown_as_zero(self):
        """Aggregate-only coverage must produce no attribution figure at all:
        a "0/3 attributed" would read as a finding about the tests rather than
        about the coverage data."""
        check = check_line_coverage(_graph(line_coverage=_PARTIAL_COVERAGE))
        assert "per-test attribution not available from this coverage data" in check.message
        assert "attributed to a verifying test" not in check.message
        assert "attributed_lines" not in check.details
        assert "attributed_pct" not in check.details

    # Verifies: REQ-d00258-E
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
