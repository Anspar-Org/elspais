# Verifies: REQ-d00215-A+B+C+D+E
"""Tests for _compute_code_tested annotator."""

from elspais.graph.annotators import annotate_coverage
from elspais.graph.GraphNode import make_file_id
from elspais.graph.metrics import RollupMetrics
from tests.core.graph_test_helpers import (
    HELPER_NAMESPACE,
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
    function_extents: list[tuple[int, int]] | None = None,
):
    """Build a minimal graph with a REQ node, CODE node, FILE nodes, and IMPLEMENTS edge.

    Two shapes, matching the two answers ``attributed_lines`` can give
    (REQ-d00254-D):

    ``function_extents`` -- one ``(first, last)`` per citation -- gives each
    citation an ENCLOSING FUNCTION whose extent is known. The citation is the
    comment written on the line above the ``def``, which is where a
    ``# Implements:`` actually goes and which the pre-scan binds to the
    function it describes. Such a citation speaks for the function's whole
    body, so its implementation lines are known whether or not any run
    measured them.

    Otherwise ``impl_start``/``impl_end`` are the lines of CODE a
    function-less citation precedes, and the lines it speaks for are that
    block -- read from the file's ``line_coverage``, which is what says which
    lines are executable at all.

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
    if function_extents:
        code_refs = [
            make_code_ref(
                implements=["REQ-p00001"],
                source_path=code_path,
                start_line=first - 1,
                end_line=first - 1,
                function_name=f"func_{first}",
                function_line=first,
                function_end_line=last,
            )
            for first, last in function_extents
        ]
    else:
        code_refs = [
            make_code_ref(
                implements=["REQ-p00001"],
                source_path=code_path,
                start_line=impl_start - 1,
                end_line=impl_start - 1,
            ),
        ]
        if extra_code_refs:
            for start, _end in extra_code_refs:
                code_refs.append(
                    make_code_ref(
                        implements=["REQ-p00001"],
                        source_path=code_path,
                        start_line=start - 1,
                        end_line=start - 1,
                    )
                )

    graph = build_graph(req, *code_refs)

    # Annotate FILE node with line_coverage if provided
    if line_coverage is not None:
        file_id = make_file_id(HELPER_NAMESPACE, code_path)
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
    """A citation preceding executable lines 10-20, with partial line_coverage."""

    def test_code_tested_indirect_from_file_coverage(self):
        """Partial file coverage yields correct indirect count."""
        # The citation precedes lines 10-20 = 11 executable lines.
        # Coverage hits on lines 10,12,14,16,18,20 = 6 hits
        line_cov = {i: (1 if i % 2 == 0 else 0) for i in range(10, 21)}
        _, req_node = _build_req_with_code(
            impl_start=10,
            impl_end=20,
            line_coverage=line_cov,
        )

        rollup: RollupMetrics = req_node.get_metric("rollup_metrics")
        assert rollup is not None
        ct = rollup.code_tested
        assert ct.total_lines == 11  # lines 10..20
        assert ct.covered_lines == 6  # even lines: 10,12,14,16,18,20
        assert ct.attributed_lines == 0


class TestCodeTestedNoCoverageData:
    """No line_coverage on FILE -> nothing attributed, and that fact is said."""

    def test_code_tested_no_coverage_data(self):
        """With no measurement there is no total, and ``has_measurement`` is
        what carries the difference between the two zeros.

        Only a coverage map knows which lines are code, so a citation
        attributes nothing until one is ingested -- counting lines a run could
        never reach would report a requirement as less covered than its code
        is. That leaves "no run was measured" and "the run reached nothing"
        both looking like zero coverage, so ``has_measurement`` is asserted
        against BOTH states here: a surface reads it to say the first rather
        than showing the second.
        """
        _, unmeasured = _build_req_with_code(
            function_extents=[(10, 20)],
            line_coverage=None,
        )
        # The same code, measured -- by a run that reached none of it.
        _, reached_nothing = _build_req_with_code(
            function_extents=[(10, 20)],
            line_coverage=dict.fromkeys(range(10, 21), 0),
        )

        never_ran = unmeasured.get_metric("rollup_metrics").code_tested
        assert never_ran.total_lines == 0
        assert never_ran.covered_lines == 0
        assert never_ran.attributed_lines == 0
        assert never_ran.has_measurement is False

        ran_and_missed = reached_nothing.get_metric("rollup_metrics").code_tested
        assert ran_and_missed.total_lines == 11
        assert ran_and_missed.covered_lines == 0
        assert ran_and_missed.has_measurement is True


class TestCodeTestedDeduplicatesOverlappingRanges:
    """Two citations whose function extents overlap -> total is deduplicated."""

    def test_code_tested_deduplicates_overlapping_ranges(self):
        """Overlapping extents are deduplicated in total count.

        Nested functions are how one file produces two different, overlapping
        extents: an outer function 10-20 containing an inner one 13-18, each
        cited. The outer citation speaks for 11 lines and the inner for 6, and
        6 of the outer's lines ARE the inner's -- so the requirement's
        implementation is 11 lines, not 17. Counting the shared lines twice
        would report more implementation than the file contains.
        """
        # Outer 10-20 = 11 lines, inner 13-18 = 6 lines, union = 10..20 = 11.
        line_cov = dict.fromkeys(range(10, 21), 1)  # all covered

        _, req_node = _build_req_with_code(
            function_extents=[(10, 20), (13, 18)],
            line_coverage=line_cov,
        )

        rollup: RollupMetrics = req_node.get_metric("rollup_metrics")
        assert rollup is not None
        ct = rollup.code_tested
        assert ct.total_lines == 11  # deduplicated: 10..20, not 11 + 6
        assert ct.covered_lines == 11  # all covered


class TestCodeTestedFullCoverage:
    """All implementation lines covered -> tier is 'full'."""

    def test_code_tested_full_coverage(self):
        """Full coverage yields full tier (REQ-d00258 unified vocab)."""
        line_cov = dict.fromkeys(range(10, 21), 1)
        _, req_node = _build_req_with_code(
            impl_start=10,
            impl_end=20,
            line_coverage=line_cov,
        )

        rollup: RollupMetrics = req_node.get_metric("rollup_metrics")
        assert rollup is not None
        ct = rollup.code_tested
        assert ct.total_lines == 11
        assert ct.covered_lines == 11
        assert ct.covered_lines == ct.total_lines


class TestCodeTestedCarriesNoVerdict:
    """Line coverage records what a run executed, never a pass/fail verdict.

    ``code_tested`` is a ``LineCoverage``, not a coverage dimension, and
    carries no failure flag at all -- whether the run's tests passed is the
    results' business, reported there (REQ-d00254-B).
    """

    def test_code_tested_carries_no_failure_flag(self):
        line_cov = dict.fromkeys(range(10, 21), 1)
        _, req_node = _build_req_with_code(
            impl_start=10,
            impl_end=20,
            line_coverage=line_cov,
        )

        rollup: RollupMetrics = req_node.get_metric("rollup_metrics")
        assert rollup is not None
        assert not hasattr(rollup.code_tested, "has_failures")


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

    Mirrors ``_build_req_with_code`` above -- the citation is the comment line
    above the code it speaks for -- but adds a verifying TEST node (via
    ``make_test_ref``) and ``line_contexts`` so per-test direct attribution
    (CUR-1568) can be exercised.
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
        start_line=impl_start - 1,
        end_line=impl_start - 1,
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

    file_id = make_file_id(HELPER_NAMESPACE, code_path)
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
        assert ct.total_lines == 3  # lines 10..12
        assert ct.attributed_lines == 2
        assert ct.covered_lines == 2  # indirect stays the whole-file coverage count

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
        assert ct.attributed_lines == 0
        assert ct.covered_lines == 2  # file-level coverage credit is unaffected

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
        assert rollup.code_tested.attributed_lines == 0

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
        assert rollup.code_tested.attributed_lines == 1

    def test_no_line_contexts_direct_stays_zero(self):
        """Backward compatibility: coverage without a contexts map credits no direct."""
        _, req_node = _build_req_code_test_with_contexts(
            line_coverage={10: 1, 11: 1, 12: 0},
            line_contexts=None,
        )

        rollup: RollupMetrics = req_node.get_metric("rollup_metrics")
        assert rollup is not None
        assert rollup.code_tested.attributed_lines == 0
        assert rollup.code_tested.covered_lines == 2

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
        assert rollup.code_tested.attributed_lines == 1

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
        assert rollup.code_tested.attributed_lines == 0
