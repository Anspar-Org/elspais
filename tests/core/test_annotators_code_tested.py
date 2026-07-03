# Verifies: REQ-d00215-A+B+C+D+E
"""Tests for _compute_code_tested annotator."""

from elspais.graph.annotators import annotate_coverage
from elspais.graph.metrics import RollupMetrics
from tests.core.graph_test_helpers import (
    build_graph,
    make_code_ref,
    make_requirement,
    make_test_ref,
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
        line_cov = dict.fromkeys(range(10, 21), 1)  # all covered

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
        line_cov = dict.fromkeys(range(10, 21), 1)
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
        line_cov = dict.fromkeys(range(10, 21), 1)
        _, req_node = _build_req_with_code(
            impl_start=10,
            impl_end=20,
            line_coverage=line_cov,
        )

        rollup: RollupMetrics = req_node.get_metric("rollup_metrics")
        assert rollup is not None
        assert rollup.code_tested.has_failures is False


# Verifies: REQ-d00254-G, REQ-d00258-E
def _build_req_code_test_with_contexts(
    *,
    line_coverage: dict[int, int],
    line_contexts: dict[int, list[str]] | None,
    impl_start: int = 10,
    impl_end: int = 12,
    code_path: str = "src/module.py",
    test_path: str = "tests/test_feat.py",
    test_function: str | None = "test_widget",
    test_class: str | None = None,
    verifies: bool = True,
):
    """Build a REQ, a CODE impl, and a TEST that Verifies the REQ, with
    line_coverage + line_contexts set on the CODE's FILE node.

    Mirrors ``_build_req_with_code`` above but adds a verifying TEST node
    (via ``make_test_ref``) and ``line_contexts`` so per-test direct
    attribution (CUR-1568) can be exercised.
    """
    req = make_requirement(
        "REQ-p00001",
        title="Test Req",
        level="PRD",
        assertions=[{"label": "A", "text": "SHALL do A"}],
    )
    code_ref = make_code_ref(
        implements=["REQ-p00001"],
        source_path=code_path,
        start_line=impl_start,
        end_line=impl_end,
    )
    test_ref = make_test_ref(
        verifies=["REQ-p00001"] if verifies else [],
        source_path=test_path,
        function_name=test_function,
        class_name=test_class,
        start_line=1,
        end_line=5,
        function_line=1,
    )

    graph = build_graph(req, code_ref, test_ref)

    file_id = f"file:{code_path}"
    file_node = graph.find_by_id(file_id)
    assert file_node is not None, f"FILE node {file_id} not found"
    file_node.set_field("line_coverage", line_coverage)
    file_node.set_field("executable_lines", len(line_coverage))
    if line_contexts is not None:
        file_node.set_field("line_contexts", line_contexts)

    annotate_coverage(graph)

    req_node = graph.find_by_id("REQ-p00001")
    assert req_node is not None
    return graph, req_node


class TestCodeTestedDirectFromContexts:
    """Direct attribution via coverage.py per-test dynamic contexts (CUR-1568)."""

    def test_contexts_attribute_direct_lines(self):
        """Lines whose recorded context names a verifying test count as direct."""
        _, req_node = _build_req_code_test_with_contexts(
            line_coverage={10: 1, 11: 1, 12: 0},
            line_contexts={
                10: ["tests/test_feat.py::test_widget|run"],
                11: ["tests/test_feat.py::test_widget|run"],
            },
        )

        rollup: RollupMetrics = req_node.get_metric("rollup_metrics")
        assert rollup is not None
        ct = rollup.code_tested
        assert ct.total == 3  # lines 10..12
        assert ct.direct == 2
        assert ct.indirect == 2  # indirect stays the whole-file coverage count

    def test_context_of_unrelated_test_does_not_credit_direct(self):
        """A context naming a test that does NOT verify this REQ credits nothing."""
        _, req_node = _build_req_code_test_with_contexts(
            line_coverage={10: 1, 11: 1, 12: 0},
            line_contexts={
                10: ["tests/test_other.py::test_x|run"],
                11: ["tests/test_other.py::test_x|run"],
            },
        )

        rollup: RollupMetrics = req_node.get_metric("rollup_metrics")
        assert rollup is not None
        ct = rollup.code_tested
        assert ct.direct == 0
        assert ct.indirect == 2  # file-level coverage credit is unaffected

    def test_setup_and_teardown_contexts_do_not_credit_direct(self):
        """Only "|run" contexts count; fixture "|setup"/"|teardown" phases don't."""
        _, req_node = _build_req_code_test_with_contexts(
            line_coverage={10: 1, 11: 1, 12: 0},
            line_contexts={
                10: ["tests/test_feat.py::test_widget|setup"],
                11: ["tests/test_feat.py::test_widget|teardown"],
            },
        )

        rollup: RollupMetrics = req_node.get_metric("rollup_metrics")
        assert rollup is not None
        assert rollup.code_tested.direct == 0

    def test_class_based_test_context_normalizes_and_credits(self):
        """Class::function context form matches a class-scoped TEST node id."""
        _, req_node = _build_req_code_test_with_contexts(
            line_coverage={10: 1, 11: 1, 12: 0},
            line_contexts={
                10: ["tests/test_feat.py::TestWidget::test_widget|run"],
            },
            test_function="test_widget",
            test_class="TestWidget",
        )

        rollup: RollupMetrics = req_node.get_metric("rollup_metrics")
        assert rollup is not None
        assert rollup.code_tested.direct == 1

    def test_no_line_contexts_direct_stays_zero(self):
        """Backward compatibility: coverage without a contexts map credits no direct."""
        _, req_node = _build_req_code_test_with_contexts(
            line_coverage={10: 1, 11: 1, 12: 0},
            line_contexts=None,
        )

        rollup: RollupMetrics = req_node.get_metric("rollup_metrics")
        assert rollup is not None
        assert rollup.code_tested.direct == 0
        assert rollup.code_tested.indirect == 2

    def test_context_credits_multiple_contexts_on_one_line(self):
        """A line covered by several tests' contexts still credits once
        when any of them verifies the requirement."""
        _, req_node = _build_req_code_test_with_contexts(
            line_coverage={10: 1, 11: 1, 12: 0},
            line_contexts={
                10: [
                    "tests/test_other.py::test_unrelated|run",
                    "tests/test_feat.py::test_widget|run",
                ],
            },
        )

        rollup: RollupMetrics = req_node.get_metric("rollup_metrics")
        assert rollup is not None
        assert rollup.code_tested.direct == 1

    def test_no_verifies_edge_direct_stays_zero(self):
        """A test with no Verifies: to this REQ never credits direct,
        even if its context covers an implementation line."""
        _, req_node = _build_req_code_test_with_contexts(
            line_coverage={10: 1, 11: 1, 12: 0},
            line_contexts={10: ["tests/test_feat.py::test_widget|run"]},
            verifies=False,
        )

        rollup: RollupMetrics = req_node.get_metric("rollup_metrics")
        assert rollup is not None
        assert rollup.code_tested.direct == 0
