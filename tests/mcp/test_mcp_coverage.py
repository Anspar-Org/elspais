# Verifies: REQ-o00064-A+B+C+D+E
# Validates REQ-o00064-A, REQ-o00064-B, REQ-o00064-C, REQ-o00064-D, REQ-o00064-E
# Validates REQ-d00066-A, REQ-d00066-B, REQ-d00066-C, REQ-d00066-D
# Validates REQ-d00066-E, REQ-d00066-F, REQ-d00066-G
# Validates REQ-d00067-A, REQ-d00067-B, REQ-d00067-C, REQ-d00067-D
# Validates REQ-d00067-E, REQ-d00067-F
# Validates REQ-d00068-A, REQ-d00068-B, REQ-d00068-C, REQ-d00068-D
# Validates REQ-d00068-E, REQ-d00068-F
# Verifies: REQ-d00069-J, REQ-d00258-A
"""Tests for MCP test coverage tools.

Tests REQ-o00064: MCP Test Coverage Tools
- get_test_coverage()
- get_uncovered_assertions()
- find_assertions_by_keywords()

All tests verify correct graph traversal for test-requirement analysis.
"""

from pathlib import Path

import pytest

from elspais.graph import EdgeKind, GraphNode, NodeKind
from elspais.graph.builder import TraceGraph

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def coverage_graph():
    """Create a TraceGraph with test coverage relationships."""
    graph = TraceGraph(repo_root=Path("/test/repo"))

    # Create requirement with assertions
    req_node = GraphNode(
        id="REQ-p00001",
        kind=NodeKind.REQUIREMENT,
        label="Platform Security",
    )
    req_node._content = {
        "level": "PRD",
        "status": "Active",
        "hash": "abc12345",
    }

    # Add assertions
    assertion_a = GraphNode(
        id="REQ-p00001-A",
        kind=NodeKind.ASSERTION,
        label="SHALL encrypt all data at rest",
    )
    assertion_a._content = {"label": "A", "text": "SHALL encrypt all data at rest"}
    req_node.link(assertion_a, EdgeKind.STRUCTURES)

    assertion_b = GraphNode(
        id="REQ-p00001-B",
        kind=NodeKind.ASSERTION,
        label="SHALL use TLS 1.3 for transit",
    )
    assertion_b._content = {"label": "B", "text": "SHALL use TLS 1.3 for transit"}
    req_node.link(assertion_b, EdgeKind.STRUCTURES)

    assertion_c = GraphNode(
        id="REQ-p00001-C",
        kind=NodeKind.ASSERTION,
        label="SHALL validate input parameters",
    )
    assertion_c._content = {"label": "C", "text": "SHALL validate input parameters"}
    req_node.link(assertion_c, EdgeKind.STRUCTURES)

    # Create TEST node that references assertion A
    test_node = GraphNode(
        id="test:test_encryption.py::test_data_encrypted",
        kind=NodeKind.TEST,
        label="test_data_encrypted",
    )
    test_node._content = {"file": "test_encryption.py", "name": "test_data_encrypted"}

    # Link assertion to test (assertion has test as child with VALIDATES edge)
    assertion_a.link(test_node, EdgeKind.VERIFIES)

    # Create TEST_RESULT for the test
    result_node = GraphNode(
        id="result:test_encryption.py::test_data_encrypted",
        kind=NodeKind.RESULT,
        label="passed",
    )
    result_node._content = {"status": "passed", "duration": 0.5}
    test_node.link(result_node, EdgeKind.YIELDS)

    # Add second requirement with no test coverage
    req_node2 = GraphNode(
        id="REQ-p00002",
        kind=NodeKind.REQUIREMENT,
        label="Performance Requirements",
    )
    req_node2._content = {
        "level": "PRD",
        "status": "Active",
        "hash": "xyz98765",
    }

    assertion_d = GraphNode(
        id="REQ-p00002-A",
        kind=NodeKind.ASSERTION,
        label="SHALL respond within 100ms",
    )
    assertion_d._content = {"label": "A", "text": "SHALL respond within 100ms"}
    req_node2.link(assertion_d, EdgeKind.STRUCTURES)

    # Register all nodes
    graph._index = {
        "REQ-p00001": req_node,
        "REQ-p00001-A": assertion_a,
        "REQ-p00001-B": assertion_b,
        "REQ-p00001-C": assertion_c,
        "REQ-p00002": req_node2,
        "REQ-p00002-A": assertion_d,
        "test:test_encryption.py::test_data_encrypted": test_node,
        "result:test_encryption.py::test_data_encrypted": result_node,
    }
    graph._roots = [req_node, req_node2]

    # Attach rollup metrics reflecting a realistic IMPLEMENTED-but-untested
    # scenario (REQ-d00258): REQ-p00001's assertions A/B/C are all implemented,
    # only A is tested -> B and C are genuine *testing* gaps. REQ-p00002-A is
    # implemented but untested. The MCP testing-gap surface is scoped to
    # implemented assertions, so without this the fixture would report no
    # testing gaps at all (an unimplemented assertion has nothing to test yet).
    from elspais.graph.metrics import CoverageDimension, RollupMetrics

    # The fractions model assertion-targeted (named) evidence attached to this
    # requirement, so they land in the IMMEDIATE DIRECT measure a work-list
    # surface reads (REQ-d00258-M) as well as in the legacy footings.
    # Whole-requirement-only and conducted evidence are exercised separately
    # (TestStrictFootingMcpGaps, TestUncoveredMeasureDetail).
    def _dim(total: int, fractions: dict[str, float]) -> CoverageDimension:
        return CoverageDimension(
            total=total,
            direct=sum(fractions.values()),
            indirect=sum(fractions.values()),
            direct_pct_by_label=dict(fractions),
            indirect_pct_by_label=dict(fractions),
            immediate_direct_by_label=dict(fractions),
            immediate_indirect_by_label=dict(fractions),
        )

    req_node.set_metric(
        "rollup_metrics",
        RollupMetrics(
            total_assertions=3,
            implemented=_dim(3, {"A": 1.0, "B": 1.0, "C": 1.0}),
            tested=_dim(3, {"A": 1.0}),
        ),
    )
    req_node2.set_metric(
        "rollup_metrics",
        RollupMetrics(
            total_assertions=1,
            implemented=_dim(1, {"A": 1.0}),
            tested=_dim(1, {}),
        ),
    )

    # Annotate keywords for keyword-based search
    from elspais.graph.annotators import annotate_keywords

    annotate_keywords(graph)

    return graph


# ─────────────────────────────────────────────────────────────────────────────
# Tests for get_test_coverage() - REQ-d00066
# ─────────────────────────────────────────────────────────────────────────────


class TestGetTestCoverage:
    """Tests for get_test_coverage() tool."""

    def test_REQ_d00066_A_finds_test_nodes_targeting_requirement(self, coverage_graph):
        """REQ-d00066-A: SHALL find TEST nodes by searching for edges targeting the requirement."""
        from elspais.mcp.server import _get_test_coverage

        result = _get_test_coverage(coverage_graph, "REQ-p00001")

        assert result["success"] is True
        assert len(result["test_nodes"]) == 1
        assert result["test_nodes"][0]["id"] == "test:test_encryption.py::test_data_encrypted"

    def test_REQ_d00066_B_returns_test_results(self, coverage_graph):
        """REQ-d00066-B: SHALL return TEST_RESULT nodes associated with found TEST nodes."""
        from elspais.mcp.server import _get_test_coverage

        result = _get_test_coverage(coverage_graph, "REQ-p00001")

        assert len(result["test_nodes"][0]["results"]) == 1
        assert result["test_nodes"][0]["results"][0]["status"] == "passed"

    def test_REQ_d00066_C_identifies_coverage_gaps(self, coverage_graph):
        """REQ-d00066-C: SHALL identify assertion coverage gaps."""
        from elspais.mcp.server import _get_test_coverage

        result = _get_test_coverage(coverage_graph, "REQ-p00001")

        # Assertion A is covered, B and C are not
        assert result["covered_assertions"] == ["REQ-p00001-A"]
        assert set(result["uncovered_assertions"]) == {"REQ-p00001-B", "REQ-p00001-C"}

    def test_REQ_d00066_D_returns_coverage_percentage(self, coverage_graph):
        """REQ-d00066-D: SHALL return coverage percentage and breakdown."""
        from elspais.mcp.server import _get_test_coverage

        result = _get_test_coverage(coverage_graph, "REQ-p00001")

        # 1 of 3 assertions covered = 33.3%
        assert result["total_assertions"] == 3
        assert result["covered_count"] == 1
        assert 33 <= result["referenced_pct"] <= 34

    def test_REQ_d00066_E_handles_no_test_coverage(self, coverage_graph):
        """REQ-d00066-E: SHALL handle requirements with no test coverage gracefully."""
        from elspais.mcp.server import _get_test_coverage

        result = _get_test_coverage(coverage_graph, "REQ-p00002")

        assert result["success"] is True
        assert result["test_nodes"] == []
        assert result["referenced_pct"] == 0
        assert result["uncovered_assertions"] == ["REQ-p00002-A"]

    # Verifies: REQ-d00258-O
    def test_REQ_d00258_O_reports_the_tested_breakdown(self, coverage_graph):
        """The tool reports what came back from the tests it counts: A is
        tested and its result passed, B fails, and C is tested with no verdict
        -- so the three account for the whole tested set."""
        from elspais.graph.metrics import CoverageDimension
        from elspais.mcp.server import _get_test_coverage

        rollup = coverage_graph.find_by_id("REQ-p00001").get_metric("rollup_metrics")
        rollup.tested = CoverageDimension(
            total=3,
            direct=3.0,
            indirect=3.0,
            direct_labels={"A", "B", "C"},
            indirect_labels={"A", "B", "C"},
            direct_pct_by_label={"A": 1.0, "B": 1.0, "C": 1.0},
            indirect_pct_by_label={"A": 1.0, "B": 1.0, "C": 1.0},
        )
        rollup.verified = CoverageDimension(
            total=3,
            direct=1.0,
            indirect=1.0,
            has_failures=True,
            failing_labels={"B"},
            direct_labels={"A"},
            indirect_labels={"A"},
            direct_pct_by_label={"A": 1.0},
            indirect_pct_by_label={"A": 1.0},
        )

        result = _get_test_coverage(coverage_graph, "REQ-p00001")

        assert result["tested_breakdown"] == {"passed": 1, "failed": 1, "awaiting_result": 1}


# ─────────────────────────────────────────────────────────────────────────────
# Tests for get_uncovered_assertions() - REQ-d00067
# ─────────────────────────────────────────────────────────────────────────────


class TestGetUncoveredAssertions:
    """Tests for get_uncovered_assertions() tool."""

    def test_REQ_d00067_A_iterates_all_assertions_when_no_req_id(self, coverage_graph):
        """REQ-d00067-A: SHALL iterate all ASSERTION nodes when req_id is None."""
        from elspais.mcp.server import _get_uncovered_assertions

        result = _get_uncovered_assertions(coverage_graph, req_id=None)

        # Returns requirement-level summaries with uncovered labels
        reqs = {r["req_id"]: r for r in result["requirements"]}
        assert "REQ-p00001" in reqs
        assert "B" in reqs["REQ-p00001"]["uncovered_labels"]
        assert "C" in reqs["REQ-p00001"]["uncovered_labels"]
        assert "A" not in reqs["REQ-p00001"]["uncovered_labels"]  # covered
        assert "REQ-p00002" in reqs
        assert "A" in reqs["REQ-p00002"]["uncovered_labels"]

    def test_REQ_d00067_B_iterates_child_assertions_when_req_id_provided(self, coverage_graph):
        """REQ-d00067-B: SHALL iterate only child assertions when req_id is provided."""
        from elspais.mcp.server import _get_uncovered_assertions

        result = _get_uncovered_assertions(coverage_graph, req_id="REQ-p00001")

        assert result["req_id"] == "REQ-p00001"
        assert "B" in result["uncovered_labels"]
        assert "C" in result["uncovered_labels"]
        assert "A" not in result["uncovered_labels"]  # covered

    def test_REQ_d00067_D_returns_requirement_context(self, coverage_graph):
        """REQ-d00067-D: SHALL return requirement id, title, and uncovered label summary."""
        from elspais.mcp.server import _get_uncovered_assertions

        result = _get_uncovered_assertions(coverage_graph, req_id="REQ-p00001")

        assert result["req_id"] == "REQ-p00001"
        assert result["title"]  # has a title
        assert result["total_assertions"] == 3
        assert result["uncovered_count"] == 2
        assert set(result["uncovered_labels"]) == {"B", "C"}

    def test_REQ_d00067_E_sorts_by_requirement_id(self, coverage_graph):
        """REQ-d00067-E: SHALL sort results by requirement ID for logical grouping."""
        from elspais.mcp.server import _get_uncovered_assertions

        result = _get_uncovered_assertions(coverage_graph, req_id=None)

        req_ids = [r["req_id"] for r in result["requirements"]]
        assert req_ids == sorted(req_ids)


# ─────────────────────────────────────────────────────────────────────────────
# REQ-d00258-J/M: an uncovered entry carries the work-list fraction its verdict
# was taken on, plus the four measures of REQ-d00069-L behind it, so evidence
# the gap does not count (whole-requirement, conducted up a `Refines:` chain)
# stays visible without deciding the verdict. Additive alongside the flat
# ``uncovered_assertions`` / ``uncovered_labels`` lists.
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def refines_conduction_graph():
    """Graph with an assertion (REQ-200-X) covered only by REFINES conduction,
    and with no test reference of its own.

    REQ-200 has a single assertion X. REQ-030 refines REQ-200-X and has two
    assertions of its own (P, Q); only P is directly tested, so REQ-030's
    own "tested" coverage is 0.5. Under equal-weight conduction
    (REQ-d00069-J), X carries 0.5 of ROLLED DIRECT coverage and nothing at all
    on the immediate direct measure -- no citation names X.
    """
    from elspais.graph.annotators import annotate_coverage
    from tests.core.graph_test_helpers import (
        build_graph,
        make_code_ref,
        make_requirement,
        make_test_ref,
    )

    graph = build_graph(
        make_requirement(
            "REQ-200",
            level="PRD",
            assertions=[{"label": "X", "text": "Assertion X"}],
        ),
        make_requirement(
            "REQ-030",
            level="OPS",
            refines=["REQ-200-X"],
            assertions=[
                {"label": "P", "text": "Assertion P"},
                {"label": "Q", "text": "Assertion Q"},
            ],
        ),
        # REQ-200-X is IMPLEMENTED by a citation naming it (so it stays a
        # *testing* gap under the implemented-scoped MCP surface), and reaches
        # 0.5 of conducted test coverage from REQ-030-P.
        make_code_ref(implements=["REQ-200-X"], source_path="src/x.py"),
        make_test_ref(verifies=["REQ-030-P"], source_path="tests/test_p.py"),
    )
    annotate_coverage(graph)
    return graph


# Verifies: REQ-d00258-J, REQ-d00258-M, REQ-d00069-L
class TestUncoveredMeasureDetail:
    """A gap's detail reports the work-list measure and publishes the four."""

    def test_get_test_coverage_conducted_assertion_is_a_gap_at_zero(self, refines_conduction_graph):
        """REQ-d00258-M: conduction from a refining requirement is not a
        citation naming X, so X is work and its work-list fraction is 0."""
        from elspais.mcp.server import _get_test_coverage

        result = _get_test_coverage(refines_conduction_graph, "REQ-200")

        assert result["uncovered_assertions"] == ["REQ-200-X"]
        detail_by_id = {d["id"]: d for d in result["uncovered_detail"]}
        assert detail_by_id["REQ-200-X"]["fraction"] == 0.0

    def test_get_test_coverage_detail_publishes_the_conducted_measure(
        self, refines_conduction_graph
    ):
        """REQ-d00258-J: the conducted evidence the verdict does not count is
        published beside it rather than dropped."""
        from elspais.mcp.server import _get_test_coverage

        result = _get_test_coverage(refines_conduction_graph, "REQ-200")

        measures = {d["id"]: d for d in result["uncovered_detail"]}["REQ-200-X"]["measures"]
        assert measures["tested"]["rolled_direct"] == 0.5
        assert measures["tested"]["immediate_direct"] == 0.0

    def test_get_test_coverage_unevidenced_assertion_reads_zero_everywhere(self, coverage_graph):
        """An *Assertion* nothing tests reads 0 on every measure, so a caller
        can tell it apart from one carrying evidence the verdict discounts."""
        from elspais.mcp.server import _get_test_coverage

        result = _get_test_coverage(coverage_graph, "REQ-p00001")

        detail = {d["id"]: d for d in result["uncovered_detail"]}["REQ-p00001-B"]
        assert detail["fraction"] == 0.0
        assert set(detail["measures"]["tested"].values()) == {0.0}

    def test_get_uncovered_assertions_req_id_reports_the_measures(self, refines_conduction_graph):
        from elspais.mcp.server import _get_uncovered_assertions

        result = _get_uncovered_assertions(refines_conduction_graph, req_id="REQ-200")

        assert result["uncovered_labels"] == ["X"]
        detail = {d["label"]: d for d in result["uncovered_detail"]}["X"]
        assert detail["id"] == "REQ-200-X"
        assert detail["fraction"] == 0.0
        assert detail["measures"]["tested"]["rolled_direct"] == 0.5

    def test_get_uncovered_assertions_scan_all_reports_the_measures(self, refines_conduction_graph):
        from elspais.mcp.server import _get_uncovered_assertions

        result = _get_uncovered_assertions(refines_conduction_graph, req_id=None)

        reqs = {r["req_id"]: r for r in result["requirements"]}
        detail = {d["label"]: d for d in reqs["REQ-200"]["uncovered_detail"]}["X"]
        assert detail["fraction"] == 0.0
        assert detail["measures"]["tested"]["rolled_direct"] == 0.5

    def test_uncovered_assertions_measures_cover_each_axis_asked_about(
        self, refines_conduction_graph
    ):
        """The measures are reported per dimension the ``source`` asked about,
        so a caller can see which axis the evidence belongs to."""
        from elspais.mcp.server import _get_uncovered_assertions

        result = _get_uncovered_assertions(
            refines_conduction_graph, req_id="REQ-200", source="both"
        )

        detail = {d["label"]: d for d in result["uncovered_detail"]}["X"]
        assert set(detail["measures"]) == {"tested", "uat_coverage"}


# ─────────────────────────────────────────────────────────────────────────────
# REQ-d00258: MCP get_uncovered_assertions realigns the *testing* gap to the
# relative denominator -- a testing gap is IMPLEMENTED and not tested, so an
# unimplemented assertion is NOT a testing gap (mirrors CLI `gaps untested` and
# the viewer). The UAT axis stays UNRESTRICTED (an unvalidated assertion is a
# UAT gap regardless of implementation).
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def denominator_graph():
    """One REQ with A implemented-untested, B unimplemented-untested,
    C unimplemented but UAT-validated.

    Coverage after annotation:
      implemented: {A}          tested: {}          uat_coverage: {C}

    So the axis-by-axis gap composition is:
      test -> {A}       (implemented AND not tested; B/C excluded, unimplemented)
      uat  -> {A, B}    (not validated; C excluded, validated)
      both -> {A, B}    (test {A} UNION uat {A,B}; C excluded -- validated,
                         and not a test gap since unimplemented)
    """
    from elspais.graph.annotators import annotate_coverage
    from tests.core.graph_test_helpers import (
        build_graph,
        make_code_ref,
        make_journey,
        make_requirement,
    )

    graph = build_graph(
        make_requirement(
            "REQ-500",
            level="PRD",
            assertions=[
                {"label": "A", "text": "Assertion A"},
                {"label": "B", "text": "Assertion B"},
                {"label": "C", "text": "Assertion C"},
            ],
        ),
        make_code_ref(implements=["REQ-500-A"], source_path="src/a.py"),
        make_journey("UJ-1", validates=["REQ-500-C"], source_path="spec/j.md"),
    )
    annotate_coverage(graph)
    return graph


# Verifies: REQ-d00067-A, REQ-d00258-A
class TestUncoveredTestingGapDenominator:
    """The testing gap is scoped to implemented assertions (REQ-d00258)."""

    def test_source_test_implemented_untested_is_uncovered(self, denominator_graph):
        """(a) An IMPLEMENTED, untested assertion IS a testing gap."""
        from elspais.mcp.server import _get_uncovered_assertions

        result = _get_uncovered_assertions(denominator_graph, req_id="REQ-500", source="test")
        assert "A" in result["uncovered_labels"]

    def test_source_test_unimplemented_untested_is_not_uncovered(self, denominator_graph):
        """(b) An UNIMPLEMENTED, untested assertion is NOT a testing gap.

        This is the realignment: previously B (untested) was reported as a gap
        regardless of implementation; now it is excluded because nothing is
        built to test yet.
        """
        from elspais.mcp.server import _get_uncovered_assertions

        result = _get_uncovered_assertions(denominator_graph, req_id="REQ-500", source="test")
        assert result["uncovered_labels"] == ["A"]
        assert "B" not in result["uncovered_labels"]
        assert "C" not in result["uncovered_labels"]

    def test_source_uat_is_unrestricted_by_implementation(self, denominator_graph):
        """(c) The UAT axis stays unrestricted: an UNIMPLEMENTED, unvalidated
        assertion still surfaces as a UAT gap; a validated one does not."""
        from elspais.mcp.server import _get_uncovered_assertions

        result = _get_uncovered_assertions(denominator_graph, req_id="REQ-500", source="uat")
        assert set(result["uncovered_labels"]) == {"A", "B"}  # C is validated

    def test_source_both_composes_test_and_uat_axes(self, denominator_graph):
        """`both` = test gaps (implemented AND untested) UNION uat gaps
        (unvalidated). An unimplemented-but-validated assertion (C) appears in
        neither; an unimplemented-and-unvalidated one (B) still shows as a UAT
        gap."""
        from elspais.mcp.server import _get_uncovered_assertions

        result = _get_uncovered_assertions(denominator_graph, req_id="REQ-500", source="both")
        assert set(result["uncovered_labels"]) == {"A", "B"}
        assert "C" not in result["uncovered_labels"]

    def test_mcp_test_axis_agrees_with_cli_gaps_untested(self, denominator_graph):
        """Cross-surface agreement: the MCP test-axis uncovered set matches the
        CLI `gaps untested` surface on the same graph (design section 6)."""
        from elspais.commands.gaps import collect_gaps
        from elspais.mcp.server import _get_uncovered_assertions

        mcp = _get_uncovered_assertions(denominator_graph, req_id="REQ-500", source="test")
        mcp_labels = set(mcp["uncovered_labels"])

        data = collect_gaps(denominator_graph, exclude_status=set(), config={})
        cli_labels: set[str] = set()
        for entry in data.untested:
            if entry.req_id != "REQ-500":
                continue
            for _aid, label, _frac in entry.assertions:
                cli_labels.add(label)

        assert mcp_labels == cli_labels == {"A"}


# ─────────────────────────────────────────────────────────────────────────────
# Tests for find_assertions_by_keywords() - REQ-d00068
# ─────────────────────────────────────────────────────────────────────────────


class TestFindAssertionsByKeywords:
    """Tests for find_assertions_by_keywords() tool."""

    def test_REQ_d00068_A_searches_assertion_text(self, coverage_graph):
        """REQ-d00068-A: SHALL iterate ASSERTION nodes and check text content."""
        from elspais.mcp.server import _find_assertions_by_keywords

        result = _find_assertions_by_keywords(coverage_graph, keywords=["encrypt"])

        assert len(result["assertions"]) == 1
        assert result["assertions"][0]["id"] == "REQ-p00001-A"

    def test_REQ_d00068_B_match_all_true_requires_all_keywords(self, coverage_graph):
        """REQ-d00068-B: SHALL support match_all=True for AND logic."""
        from elspais.mcp.server import _find_assertions_by_keywords

        # Both keywords must match
        result = _find_assertions_by_keywords(
            coverage_graph, keywords=["encrypt", "data"], match_all=True
        )
        assert len(result["assertions"]) == 1

        # These won't both match
        result = _find_assertions_by_keywords(
            coverage_graph, keywords=["encrypt", "TLS"], match_all=True
        )
        assert len(result["assertions"]) == 0

    def test_REQ_d00068_C_match_all_false_accepts_any_keyword(self, coverage_graph):
        """REQ-d00068-C: SHALL support match_all=False for OR logic."""
        from elspais.mcp.server import _find_assertions_by_keywords

        result = _find_assertions_by_keywords(
            coverage_graph, keywords=["encrypt", "TLS"], match_all=False
        )

        # Should find both encryption and TLS assertions
        ids = [a["id"] for a in result["assertions"]]
        assert "REQ-p00001-A" in ids  # encrypt
        assert "REQ-p00001-B" in ids  # TLS

    def test_REQ_d00068_D_returns_assertion_context(self, coverage_graph):
        """REQ-d00068-D: SHALL return assertion id, text, label, and parent context."""
        from elspais.mcp.server import _find_assertions_by_keywords

        result = _find_assertions_by_keywords(coverage_graph, keywords=["validate"])

        assert len(result["assertions"]) == 1
        assertion = result["assertions"][0]
        assert assertion["id"] == "REQ-p00001-C"
        assert assertion["label"] == "C"
        assert "validate" in assertion["text"].lower()
        assert assertion["parent_id"] == "REQ-p00001"

    def test_REQ_d00068_E_case_insensitive_matching(self, coverage_graph):
        """REQ-d00068-E: SHALL normalize keywords to lowercase for case-insensitive matching."""
        from elspais.mcp.server import _find_assertions_by_keywords

        # Uppercase keyword should still match
        result = _find_assertions_by_keywords(coverage_graph, keywords=["ENCRYPT"])
        assert len(result["assertions"]) == 1

        result = _find_assertions_by_keywords(coverage_graph, keywords=["Tls"])
        assert len(result["assertions"]) == 1


# ─────────────────────────────────────────────────────────────────────────────
# REQ-d00258-M: the MCP uncovered-assertion and test-coverage tools determine
# gaps on the STRICT footing -- an assertion with no evidence naming it is
# reported however much whole-requirement evidence its requirement carries.
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def blanket_evidence_graph():
    """REQ-700 with A covered ONLY by whole-requirement evidence.

    ``Implements: REQ-700`` (blanket) + ``Implements: REQ-700-B`` (named) +
    ``Verifies: REQ-700`` (blanket). Strict footing: implemented = {B},
    tested = {}. Generous footing: everything covered.
    """
    from elspais.graph.annotators import annotate_coverage
    from tests.core.graph_test_helpers import (
        build_graph,
        make_code_ref,
        make_requirement,
        make_test_ref,
    )

    graph = build_graph(
        make_requirement(
            "REQ-700",
            level="PRD",
            assertions=[
                {"label": "A", "text": "Assertion A"},
                {"label": "B", "text": "Assertion B"},
            ],
        ),
        make_code_ref(implements=["REQ-700"], source_path="src/whole.py"),
        make_code_ref(implements=["REQ-700-B"], source_path="src/b.py"),
        make_test_ref(verifies=["REQ-700"], source_path="tests/test_whole.py"),
    )
    annotate_coverage(graph)
    return graph


class TestStrictFootingMcpGaps:
    """Validates REQ-d00258-M: MCP gap tools answer on the strict footing."""

    # Verifies: REQ-d00258-M
    def test_REQ_d00258_M_test_coverage_reports_blanket_only_assertion_uncovered(
        self, blanket_evidence_graph
    ) -> None:
        """(a) B is tested only by a whole-requirement `Verifies:`, so
        get_test_coverage reports it as uncovered, not covered."""
        from elspais.mcp.server import _get_test_coverage

        result = _get_test_coverage(blanket_evidence_graph, "REQ-700")
        assert "REQ-700-B" in result["uncovered_assertions"]
        assert "REQ-700-B" not in result["covered_assertions"]

    # Verifies: REQ-d00258-M
    def test_REQ_d00258_M_test_coverage_still_lists_the_whole_req_test(
        self, blanket_evidence_graph
    ) -> None:
        """The whole-requirement test is real evidence and stays in the tool's
        test listing -- only the covered/uncovered verdict goes strict."""
        from elspais.mcp.server import _get_test_coverage

        result = _get_test_coverage(blanket_evidence_graph, "REQ-700")
        assert result["test_nodes"], "whole-requirement test must still be listed"

    # Verifies: REQ-d00258-M
    def test_REQ_d00258_M_uncovered_detail_fraction_matches_strict_verdict(
        self, blanket_evidence_graph
    ) -> None:
        """An assertion reported as a gap must not be annotated with a
        generous-footing fraction of 1.0."""
        from elspais.mcp.server import _get_test_coverage

        result = _get_test_coverage(blanket_evidence_graph, "REQ-700")
        detail = {d["id"]: d for d in result["uncovered_detail"]}
        assert detail["REQ-700-B"]["fraction"] == 0.0

    # Verifies: REQ-d00258-M
    def test_REQ_d00258_M_uncovered_assertions_uses_strict_numerator(
        self, blanket_evidence_graph
    ) -> None:
        """(a) B is implemented by name but tested only by a whole-requirement
        test, so it IS a testing gap."""
        from elspais.mcp.server import _get_uncovered_assertions

        result = _get_uncovered_assertions(blanket_evidence_graph, req_id="REQ-700", source="test")
        assert "B" in result["uncovered_labels"]

    # Verifies: REQ-d00258-M
    def test_REQ_d00258_M_uncovered_assertions_denominator_is_also_strict(
        self, blanket_evidence_graph
    ) -> None:
        """(d) A is implemented only by whole-requirement evidence, so it is
        not in the strict implemented denominator and is not a testing gap."""
        from elspais.mcp.server import _get_uncovered_assertions

        result = _get_uncovered_assertions(blanket_evidence_graph, req_id="REQ-700", source="test")
        assert result["uncovered_labels"] == ["B"]

    # Verifies: REQ-d00258-M
    def test_REQ_d00258_M_mcp_agrees_with_cli_gaps_on_strict_footing(
        self, blanket_evidence_graph
    ) -> None:
        """(b/c) The MCP test axis and the CLI `gaps untested` surface report
        the same strict-footing gap set."""
        from elspais.commands.gaps import collect_gaps
        from elspais.mcp.server import _get_uncovered_assertions

        mcp = _get_uncovered_assertions(blanket_evidence_graph, req_id="REQ-700", source="test")
        data = collect_gaps(blanket_evidence_graph, exclude_status=set(), config={})
        cli = {
            label
            for entry in data.untested
            if entry.req_id == "REQ-700"
            for _aid, label, _frac in entry.assertions
        }
        assert set(mcp["uncovered_labels"]) == cli == {"B"}


# ─────────────────────────────────────────────────────────────────────────────
# REQ-d00258-A/C: get_project_summary publishes the headline measure and the
# four measures behind it, and reports the same figures the CLI summary does.
# ─────────────────────────────────────────────────────────────────────────────


# Verifies: REQ-d00258-A, REQ-d00258-C, REQ-d00069-L, REQ-d00069-N
class TestProjectSummaryPublishesTheMeasures:
    """The MCP project summary answers the coverage question the CLI answers."""

    _DIMENSIONS = ("implemented", "tested", "passing", "uat_covered", "uat_passed")

    def _levels(self, graph, config, tmp_path):
        from elspais.mcp.server import _get_project_summary

        return _get_project_summary(graph, tmp_path, config)["coverage_by_level"]

    @pytest.mark.parametrize("dimension", _DIMENSIONS)
    def test_every_dimension_carries_its_headline_and_its_four_measures(
        self, canonical_graph, canonical_config, tmp_path, dimension
    ):
        """REQ-d00258-A: the headline figure is published together with the
        evidence that produced it, for every dimension the payload reports."""
        pytest.importorskip("mcp")
        level = self._levels(canonical_graph, canonical_config, tmp_path)[0]

        assert f"{dimension}_total_covered" in level
        for measure in (
            "immediate_direct",
            "immediate_indirect",
            "rolled_direct",
            "rolled_indirect",
        ):
            assert f"{dimension}_{measure}" in level

    @pytest.mark.parametrize("dimension", _DIMENSIONS)
    def test_the_headline_never_exceeds_the_assertion_count(
        self, canonical_graph, canonical_config, tmp_path, dimension
    ):
        """REQ-d00069-N: the total is taken per *Assertion* as the greatest of
        the four, so an *Assertion* covered several ways is counted once and
        the headline can never exceed the assertions there are to cover."""
        pytest.importorskip("mcp")
        for level in self._levels(canonical_graph, canonical_config, tmp_path):
            assert level[f"{dimension}_total_covered"] <= level["total_assertions"]

    @pytest.mark.parametrize("dimension", _DIMENSIONS)
    def test_the_headline_is_at_least_each_measure_behind_it(
        self, canonical_graph, canonical_config, tmp_path, dimension
    ):
        """REQ-d00069-N: no single measure can report more coverage than the
        total that takes the greatest of all four."""
        pytest.importorskip("mcp")
        for level in self._levels(canonical_graph, canonical_config, tmp_path):
            headline = level[f"{dimension}_total_covered"]
            for measure in (
                "immediate_direct",
                "immediate_indirect",
                "rolled_direct",
                "rolled_indirect",
            ):
                assert level[f"{dimension}_{measure}"] <= headline + 1e-9

    def test_mcp_reports_the_figures_the_cli_summary_reports(
        self, canonical_graph, canonical_config, tmp_path
    ):
        """REQ-d00258-C: identical questions receive identical answers, so the
        per-level rows come from the one shared collector rather than a second
        derivation of the same numbers."""
        pytest.importorskip("mcp")
        from elspais.graph.aggregation import collect_coverage

        assert (
            self._levels(canonical_graph, canonical_config, tmp_path)
            == collect_coverage(canonical_graph, canonical_config)["levels"]
        )


# Verifies: REQ-d00258-M, REQ-d00069-L
class TestUatValidatedPctMeasure:
    """``get_test_coverage``'s UAT figures answer on one measure.

    The tool reports which assertions still need work (REQ-d00258-M), so every
    figure in it -- ``uat.covered_count``/``referenced_pct`` and
    ``uat.validated_pct`` alike -- counts evidence that named the *Assertion*.
    A blanket journey must not lift one of them while leaving the other at
    zero.
    """

    def _with_uat_verified(self, graph, immediate_direct):
        from elspais.graph.metrics import CoverageDimension

        rollup = graph.find_by_id("REQ-p00001").get_metric("rollup_metrics")
        rollup.uat_verified = CoverageDimension(
            total=3,
            direct=len(immediate_direct),
            indirect=3,
            # A journey naming the requirement reaches every assertion on the
            # legacy blended footing...
            direct_pct_by_label=dict.fromkeys(immediate_direct, 1.0),
            indirect_pct_by_label={"A": 1.0, "B": 1.0, "C": 1.0},
            immediate_indirect_by_label={"A": 1.0, "B": 1.0, "C": 1.0},
            # ...but named only these by name.
            immediate_direct_by_label=dict.fromkeys(immediate_direct, 1.0),
        )
        return graph

    def test_validated_pct_counts_only_assertions_a_journey_named(self, coverage_graph):
        """Two of three assertions are reached only by whole-requirement
        validation. They are not validated work; the figure says so."""
        from elspais.mcp.server import _get_test_coverage

        graph = self._with_uat_verified(coverage_graph, ["A"])
        result = _get_test_coverage(graph, "REQ-p00001")

        # 1 of 3 named -> 33.3, NOT the 100.0 the blended footing reports.
        assert result["uat"]["validated_pct"] == 33.3

    def test_validated_pct_reaches_full_when_every_assertion_is_named(self, coverage_graph):
        """The figure is not merely deflated -- naming every assertion still
        reaches 100."""
        from elspais.mcp.server import _get_test_coverage

        graph = self._with_uat_verified(coverage_graph, ["A", "B", "C"])
        result = _get_test_coverage(graph, "REQ-p00001")

        assert result["uat"]["validated_pct"] == 100.0
