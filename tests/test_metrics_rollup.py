# elspais: expected-broken-links 1
"""Tests for RollupMetrics accumulation in TraceGraphBuilder.

These tests verify metrics roll-up from leaves to roots including:
- Assertion counting and coverage
- Test counting and pass rates
- Exclusion of requirements by status
- Percentage calculations

Note: Tests import from graph_builder.py (renamed from tree_builder.py).
"""

from __future__ import annotations

import pytest
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class MockRequirement:
    """Mock requirement for testing."""

    id: str
    title: str
    status: str = "Active"
    level: str = "DEV"
    implements: list[str] = field(default_factory=list)
    assertions: list = field(default_factory=list)
    is_conflict: bool = False
    file_path: Path | None = None
    line_number: int | None = None


@dataclass
class MockAssertion:
    """Mock assertion for testing."""

    label: str
    text: str


class TestComputeMetrics:
    """Tests for TraceGraphBuilder.compute_metrics()."""

    def test_compute_metrics_single_requirement(self) -> None:
        """Compute metrics for a single requirement with assertions."""
        from elspais.core.graph_builder import TraceGraphBuilder

        req = MockRequirement(
            id="REQ-d00001",
            title="Test requirement",
            assertions=[
                MockAssertion(label="A", text="First assertion"),
                MockAssertion(label="B", text="Second assertion"),
            ],
        )

        builder = TraceGraphBuilder(repo_root=Path.cwd())
        builder.add_requirements({"REQ-d00001": req})
        graph = builder.build()

        builder.compute_metrics(graph)

        node = graph.find_by_id("REQ-d00001")
        assert node is not None
        assert node.metrics["total_assertions"] == 2
        assert node.metrics["covered_assertions"] == 0  # No tests linked

    def test_compute_metrics_with_test_coverage(self) -> None:
        """Compute metrics when tests cover assertions."""
        from elspais.core.graph import NodeKind, TraceNode
        from elspais.core.graph_builder import TraceGraphBuilder
        from elspais.core.graph_schema import RollupMetrics

        req = MockRequirement(
            id="REQ-d00001",
            title="Test requirement",
            assertions=[
                MockAssertion(label="A", text="First assertion"),
            ],
        )

        builder = TraceGraphBuilder(repo_root=Path.cwd())
        builder.add_requirements({"REQ-d00001": req})

        # Add a test that covers the assertion
        test_node = TraceNode(
            id="test_something",
            kind=NodeKind.TEST,
            label="test_something",
            metrics={},
        )
        test_node.metrics["_validates_targets"] = ["REQ-d00001-A"]
        test_node.metrics["_test_status"] = "passed"
        builder.add_test_coverage([test_node])

        graph = builder.build()
        builder.compute_metrics(graph)

        # Assertion should be covered
        assertion_node = graph.find_by_id("REQ-d00001-A")
        assert assertion_node is not None
        assert assertion_node.metrics["covered_assertions"] == 1

        # Requirement should show coverage
        req_node = graph.find_by_id("REQ-d00001")
        assert req_node is not None
        assert req_node.metrics["total_assertions"] == 1
        assert req_node.metrics["covered_assertions"] == 1
        assert req_node.metrics["coverage_pct"] == 100.0

    def test_compute_metrics_hierarchy_rollup(self) -> None:
        """Metrics roll up through requirement hierarchy."""
        from elspais.core.graph_builder import TraceGraphBuilder

        # PRD -> OPS -> DEV (each with assertions)
        prd = MockRequirement(
            id="REQ-p00001",
            title="PRD requirement",
            level="PRD",
            assertions=[MockAssertion(label="A", text="PRD assertion")],
        )
        ops = MockRequirement(
            id="REQ-o00001",
            title="OPS requirement",
            level="OPS",
            implements=["REQ-p00001"],
            assertions=[MockAssertion(label="A", text="OPS assertion")],
        )
        dev = MockRequirement(
            id="REQ-d00001",
            title="DEV requirement",
            level="DEV",
            implements=["REQ-o00001"],
            assertions=[
                MockAssertion(label="A", text="DEV assertion 1"),
                MockAssertion(label="B", text="DEV assertion 2"),
            ],
        )

        builder = TraceGraphBuilder(repo_root=Path.cwd())
        builder.add_requirements({
            "REQ-p00001": prd,
            "REQ-o00001": ops,
            "REQ-d00001": dev,
        })
        graph = builder.build()

        builder.compute_metrics(graph)

        # DEV has 2 assertions
        dev_node = graph.find_by_id("REQ-d00001")
        assert dev_node.metrics["total_assertions"] == 2

        # OPS has 1 assertion + 2 from DEV child = 3
        ops_node = graph.find_by_id("REQ-o00001")
        assert ops_node.metrics["total_assertions"] == 3

        # PRD has 1 assertion + 3 from OPS child = 4
        prd_node = graph.find_by_id("REQ-p00001")
        assert prd_node.metrics["total_assertions"] == 4


class TestMetricsExclusions:
    """Tests for status-based metric exclusions."""

    def test_deprecated_requirement_excluded(self) -> None:
        """Deprecated requirements are excluded from parent metrics."""
        from elspais.core.graph_builder import TraceGraphBuilder

        parent = MockRequirement(
            id="REQ-p00001",
            title="Parent",
            level="PRD",
            assertions=[MockAssertion(label="A", text="Parent assertion")],
        )
        active_child = MockRequirement(
            id="REQ-d00001",
            title="Active child",
            level="DEV",
            status="Active",
            implements=["REQ-p00001"],
            assertions=[MockAssertion(label="A", text="Active assertion")],
        )
        deprecated_child = MockRequirement(
            id="REQ-d00002",
            title="Deprecated child",
            level="DEV",
            status="Deprecated",
            implements=["REQ-p00001"],
            assertions=[
                MockAssertion(label="A", text="Should not count"),
                MockAssertion(label="B", text="Should not count"),
            ],
        )

        builder = TraceGraphBuilder(repo_root=Path.cwd())
        builder.add_requirements({
            "REQ-p00001": parent,
            "REQ-d00001": active_child,
            "REQ-d00002": deprecated_child,
        })
        graph = builder.build()

        # Exclude Deprecated status
        builder.compute_metrics(graph, exclude_status=["Deprecated"])

        # Parent should only count assertions from active child
        parent_node = graph.find_by_id("REQ-p00001")
        # 1 (parent) + 1 (active child) = 2, NOT 1 + 1 + 2 = 4
        assert parent_node.metrics["total_assertions"] == 2

    def test_draft_requirement_excluded_by_default(self) -> None:
        """Draft requirements are excluded from parent metrics by default."""
        from elspais.core.graph_builder import TraceGraphBuilder
        from elspais.core.graph_schema import GraphSchema

        parent = MockRequirement(
            id="REQ-p00001",
            title="Parent",
            level="PRD",
            assertions=[MockAssertion(label="A", text="Parent assertion")],
        )
        draft_child = MockRequirement(
            id="REQ-d00001",
            title="Draft child",
            level="DEV",
            status="Draft",
            implements=["REQ-p00001"],
            assertions=[MockAssertion(label="A", text="Draft assertion")],
        )

        schema = GraphSchema.default()
        builder = TraceGraphBuilder(repo_root=Path.cwd(), schema=schema)
        builder.add_requirements({
            "REQ-p00001": parent,
            "REQ-d00001": draft_child,
        })
        graph = builder.build()

        # Use default exclusions from schema
        builder.compute_metrics(graph)

        # Parent should only count its own assertions (Draft excluded)
        parent_node = graph.find_by_id("REQ-p00001")
        assert parent_node.metrics["total_assertions"] == 1

    def test_custom_exclusion_list(self) -> None:
        """Custom exclusion list overrides defaults."""
        from elspais.core.graph_builder import TraceGraphBuilder

        parent = MockRequirement(
            id="REQ-p00001",
            title="Parent",
            level="PRD",
            assertions=[MockAssertion(label="A", text="Parent assertion")],
        )
        review_child = MockRequirement(
            id="REQ-d00001",
            title="In Review child",
            level="DEV",
            status="In Review",
            implements=["REQ-p00001"],
            assertions=[MockAssertion(label="A", text="In Review assertion")],
        )

        builder = TraceGraphBuilder(repo_root=Path.cwd())
        builder.add_requirements({
            "REQ-p00001": parent,
            "REQ-d00001": review_child,
        })
        graph = builder.build()

        # Exclude "In Review" status
        builder.compute_metrics(graph, exclude_status=["In Review"])

        parent_node = graph.find_by_id("REQ-p00001")
        # Only parent's assertion counted
        assert parent_node.metrics["total_assertions"] == 1


class TestTestMetrics:
    """Tests for test-related metrics."""

    def test_test_pass_rate_calculation(self) -> None:
        """Test pass rate is calculated correctly."""
        from elspais.core.graph import NodeKind, TraceNode
        from elspais.core.graph_builder import TraceGraphBuilder
        from elspais.core.graph_schema import RollupMetrics

        req = MockRequirement(
            id="REQ-d00001",
            title="Test requirement",
            assertions=[MockAssertion(label="A", text="Assertion")],
        )

        builder = TraceGraphBuilder(repo_root=Path.cwd())
        builder.add_requirements({"REQ-d00001": req})

        # Add tests with mixed results
        tests = [
            TraceNode(
                id="test_pass_1",
                kind=NodeKind.TEST,
                label="test_pass_1",
                metrics={},
            ),
            TraceNode(
                id="test_pass_2",
                kind=NodeKind.TEST,
                label="test_pass_2",
                metrics={},
            ),
            TraceNode(
                id="test_fail",
                kind=NodeKind.TEST,
                label="test_fail",
                metrics={},
            ),
        ]
        # Set up validates targets
        for test in tests:
            test.metrics["_validates_targets"] = ["REQ-d00001-A"]
            test.metrics["_test_status"] = "passed" if "pass" in test.id else "failed"

        builder.add_test_coverage(tests)
        graph = builder.build()
        builder.compute_metrics(graph)

        req_node = graph.find_by_id("REQ-d00001")
        assert req_node.metrics["total_tests"] == 3
        assert req_node.metrics["passed_tests"] == 2
        assert req_node.metrics["failed_tests"] == 1
        # Pass rate = 2/3 * 100 = 66.67%
        assert abs(req_node.metrics["pass_rate_pct"] - 66.67) < 0.01

    def test_skipped_tests_counted(self) -> None:
        """Skipped tests are counted separately."""
        from elspais.core.graph import NodeKind, TraceNode
        from elspais.core.graph_builder import TraceGraphBuilder
        from elspais.core.graph_schema import RollupMetrics

        req = MockRequirement(
            id="REQ-d00001",
            title="Test requirement",
            assertions=[MockAssertion(label="A", text="Assertion")],
        )

        builder = TraceGraphBuilder(repo_root=Path.cwd())
        builder.add_requirements({"REQ-d00001": req})

        test = TraceNode(
            id="test_skipped",
            kind=NodeKind.TEST,
            label="test_skipped",
            metrics={},
        )
        test.metrics["_validates_targets"] = ["REQ-d00001-A"]
        test.metrics["_test_status"] = "skipped"

        builder.add_test_coverage([test])
        graph = builder.build()
        builder.compute_metrics(graph)

        req_node = graph.find_by_id("REQ-d00001")
        assert req_node.metrics["total_tests"] == 1
        assert req_node.metrics["skipped_tests"] == 1
        assert req_node.metrics["passed_tests"] == 0


class TestCoveragePercentage:
    """Tests for coverage percentage calculations."""

    def test_zero_assertions_zero_coverage(self) -> None:
        """Zero assertions results in zero coverage (not division error)."""
        from elspais.core.graph_builder import TraceGraphBuilder

        req = MockRequirement(
            id="REQ-d00001",
            title="No assertions",
            assertions=[],
        )

        builder = TraceGraphBuilder(repo_root=Path.cwd())
        builder.add_requirements({"REQ-d00001": req})
        graph = builder.build()

        builder.compute_metrics(graph)

        node = graph.find_by_id("REQ-d00001")
        assert node.metrics["total_assertions"] == 0
        assert node.metrics["coverage_pct"] == 0.0

    def test_partial_coverage_calculation(self) -> None:
        """Partial coverage is calculated correctly."""
        from elspais.core.graph import NodeKind, TraceNode
        from elspais.core.graph_builder import TraceGraphBuilder
        from elspais.core.graph_schema import RollupMetrics

        req = MockRequirement(
            id="REQ-d00001",
            title="Four assertions",
            assertions=[
                MockAssertion(label="A", text="First"),
                MockAssertion(label="B", text="Second"),
                MockAssertion(label="C", text="Third"),
                MockAssertion(label="D", text="Fourth"),
            ],
        )

        builder = TraceGraphBuilder(repo_root=Path.cwd())
        builder.add_requirements({"REQ-d00001": req})

        # Add test covering only first assertion
        test = TraceNode(
            id="test_a",
            kind=NodeKind.TEST,
            label="test_a",
            metrics={},
        )
        test.metrics["_validates_targets"] = ["REQ-d00001-A"]
        builder.add_test_coverage([test])

        graph = builder.build()
        builder.compute_metrics(graph)

        node = graph.find_by_id("REQ-d00001")
        assert node.metrics["total_assertions"] == 4
        assert node.metrics["covered_assertions"] == 1
        # 1/4 * 100 = 25%
        assert node.metrics["coverage_pct"] == 25.0

    def test_full_coverage_calculation(self) -> None:
        """Full coverage is 100%."""
        from elspais.core.graph import NodeKind, TraceNode
        from elspais.core.graph_builder import TraceGraphBuilder
        from elspais.core.graph_schema import RollupMetrics

        req = MockRequirement(
            id="REQ-d00001",
            title="Two assertions",
            assertions=[
                MockAssertion(label="A", text="First"),
                MockAssertion(label="B", text="Second"),
            ],
        )

        builder = TraceGraphBuilder(repo_root=Path.cwd())
        builder.add_requirements({"REQ-d00001": req})

        # Add tests covering both assertions
        tests = [
            TraceNode(id="test_a", kind=NodeKind.TEST, label="test_a", metrics={}),
            TraceNode(id="test_b", kind=NodeKind.TEST, label="test_b", metrics={}),
        ]
        tests[0].metrics["_validates_targets"] = ["REQ-d00001-A"]
        tests[1].metrics["_validates_targets"] = ["REQ-d00001-B"]
        builder.add_test_coverage(tests)

        graph = builder.build()
        builder.compute_metrics(graph)

        node = graph.find_by_id("REQ-d00001")
        assert node.metrics["total_assertions"] == 2
        assert node.metrics["covered_assertions"] == 2
        assert node.metrics["coverage_pct"] == 100.0
