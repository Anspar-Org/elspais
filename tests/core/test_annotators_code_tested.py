# Verifies: REQ-d00215-A+B+C+D+E
"""Tests for _compute_code_tested annotator."""

from elspais.graph import NodeKind
from elspais.graph.annotators import annotate_coverage
from elspais.graph.GraphNode import FileType, GraphNode
from elspais.graph.metrics import CoverageDimension, RollupMetrics
from elspais.graph.relations import Edge, EdgeKind
from tests.core.graph_test_helpers import (
    build_graph,
    make_code_ref,
    make_requirement,
)


def _build_req_with_code(
    *,
    impl_start: int = 10,
    impl_end: int = 20,
    assertion_labels: list[str] | None = None,
    line_coverage: dict[int, int] | None = None,
    code_path: str = "src/module.py",
    extra_code_refs: list[tuple[int, int]] | None = None,
):
    """Build a minimal graph with a REQ node, CODE node, FILE nodes, and IMPLEMENTS edge.

    Returns (graph, req_node).
    """
    assertions = []
    if assertion_labels is None:
        assertion_labels = ["A"]
    for label in assertion_labels:
        assertions.append({"label": label, "text": f"SHALL do {label}"})

    req = make_requirement(
        "REQ-p00001",
        title="Test Req",
        level="PRD",
        assertions=assertions,
    )
    code_refs = [
        make_code_ref(
            implements=["REQ-p00001"],
            source_path=code_path,
            start_line=impl_start,
            end_line=impl_end,
        ),
    ]
    if extra_code_refs:
        for start, end in extra_code_refs:
            code_refs.append(
                make_code_ref(
                    implements=["REQ-p00001"],
                    source_path=code_path,
                    start_line=start,
                    end_line=end,
                )
            )

    graph = build_graph(req, *code_refs)

    # Annotate FILE node with line_coverage if provided
    if line_coverage is not None:
        file_id = f"file:{code_path}"
        file_node = graph.find_by_id(file_id)
        assert file_node is not None, f"FILE node {file_id} not found"
        file_node.set_field("line_coverage", line_coverage)
        file_node.set_field("executable_lines", len(line_coverage))

    # Run the full annotator pipeline
    annotate_coverage(graph)

    req_node = graph.find_by_id("REQ-p00001")
    assert req_node is not None
    return graph, req_node


class TestCodeTestedIndirectFromFileCoverage:
    """REQ with CODE node (function lines 10-20), FILE node with partial line_coverage."""

    def test_code_tested_indirect_from_file_coverage(self):
        """Partial file coverage yields correct indirect count."""
        # Lines 10-20 = 11 lines. Coverage hits on lines 10,12,14,16,18,20 = 6 hits
        line_cov = {i: (1 if i % 2 == 0 else 0) for i in range(10, 21)}
        _, req_node = _build_req_with_code(
            impl_start=10,
            impl_end=20,
            line_coverage=line_cov,
        )

        rollup: RollupMetrics = req_node.get_metric("rollup_metrics")
        assert rollup is not None
        ct = rollup.code_tested
        assert ct.total == 11  # lines 10..20
        assert ct.indirect == 6  # even lines: 10,12,14,16,18,20
        assert ct.direct == 0
        assert ct.has_failures is False


class TestCodeTestedNoCoverageData:
    """REQ with CODE node but no line_coverage on FILE -> code_tested stays zeros."""

    def test_code_tested_no_coverage_data(self):
        """No line_coverage data means code_tested has total but zero indirect."""
        _, req_node = _build_req_with_code(
            impl_start=10,
            impl_end=20,
            line_coverage=None,
        )

        rollup: RollupMetrics = req_node.get_metric("rollup_metrics")
        assert rollup is not None
        ct = rollup.code_tested
        # total should reflect implementation lines, indirect 0 (no coverage data)
        assert ct.total == 11
        assert ct.indirect == 0
        assert ct.direct == 0


class TestCodeTestedDeduplicatesOverlappingRanges:
    """Two IMPLEMENTS edges from same function -> total is deduplicated."""

    def test_code_tested_deduplicates_overlapping_ranges(self):
        """Overlapping ranges are deduplicated in total count."""
        # First code ref: lines 10-15, second: lines 13-20
        # Union: lines 10-20 = 11 unique lines
        line_cov = {i: 1 for i in range(10, 21)}  # all covered

        _, req_node = _build_req_with_code(
            impl_start=10,
            impl_end=15,
            extra_code_refs=[(13, 20)],
            line_coverage=line_cov,
        )

        rollup: RollupMetrics = req_node.get_metric("rollup_metrics")
        assert rollup is not None
        ct = rollup.code_tested
        assert ct.total == 11  # deduplicated: 10..20
        assert ct.indirect == 11  # all covered


class TestCodeTestedFullCoverage:
    """All implementation lines covered -> tier is 'full-indirect'."""

    def test_code_tested_full_coverage(self):
        """Full coverage yields full-indirect tier."""
        line_cov = {i: 1 for i in range(10, 21)}
        _, req_node = _build_req_with_code(
            impl_start=10,
            impl_end=20,
            line_coverage=line_cov,
        )

        rollup: RollupMetrics = req_node.get_metric("rollup_metrics")
        assert rollup is not None
        ct = rollup.code_tested
        assert ct.total == 11
        assert ct.indirect == 11
        assert ct.tier == "full-indirect"


class TestCodeTestedHasFailuresAlwaysFalse:
    """Verify has_failures is False for code_tested dimension."""

    def test_code_tested_has_failures_always_false(self):
        """has_failures is always False for code_tested."""
        line_cov = {i: 1 for i in range(10, 21)}
        _, req_node = _build_req_with_code(
            impl_start=10,
            impl_end=20,
            line_coverage=line_cov,
        )

        rollup: RollupMetrics = req_node.get_metric("rollup_metrics")
        assert rollup is not None
        assert rollup.code_tested.has_failures is False
