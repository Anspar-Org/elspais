"""Tests for health check coverage and UAT features."""

from __future__ import annotations

from pathlib import Path

from elspais.commands.health import (
    check_test_coverage,
    check_uat_coverage,
    check_uat_results,
    run_uat_checks,
)
from elspais.graph.builder import TraceGraph
from elspais.graph.federated import FederatedGraph
from elspais.graph.GraphNode import GraphNode, NodeKind  # noqa: N817
from elspais.graph.metrics import CoverageDimension, RollupMetrics

# =============================================================================
# Helpers
# =============================================================================


def _make_req(req_id: str, level: str = "dev", status: str = "Active") -> GraphNode:
    """Create a REQUIREMENT node with level and status set."""
    node = GraphNode(id=req_id, kind=NodeKind.REQUIREMENT, label=req_id)
    node.set_field("level", level)
    node.set_field("status", status)
    return node


def _make_graph(*nodes: GraphNode) -> FederatedGraph:
    """Wrap requirement nodes in a FederatedGraph for testing."""
    tg = TraceGraph()
    for node in nodes:
        tg._index[node.id] = node
        if node.kind == NodeKind.REQUIREMENT:
            tg._roots.append(node)
    return FederatedGraph.from_single(tg, config=None, repo_root=Path("."))


# =============================================================================
# REQ-d00218: check_test_coverage
# =============================================================================


class TestCheckTestCoverage:
    """Tests for check_test_coverage health check."""

    # Implements: REQ-d00218-A
    def test_returns_info_severity(self):
        """check_test_coverage always returns severity=info (informational)."""
        graph = _make_graph()
        result = check_test_coverage(graph, exclude_status=set())
        assert result.severity == "info"
        assert result.passed is True

    # Implements: REQ-d00218-A
    def test_no_requirements_zero_coverage(self):
        """Empty graph reports 0/0 test coverage."""
        graph = _make_graph()
        result = check_test_coverage(graph, exclude_status=set())
        assert result.name == "coverage.tested"
        assert result.category == "coverage"
        assert result.details["total_requirements"] == 0
        assert result.details["reqs_with_any_coverage"] == 0

    # Implements: REQ-d00218-A
    def test_req_with_direct_tested_counted(self):
        """Requirement with direct_tested > 0 is counted as test-covered."""
        req = _make_req("REQ-d00001")
        metrics = RollupMetrics(
            total_assertions=2,
            tested=CoverageDimension(total=2, direct=1, indirect=1),
        )
        req.set_metric("rollup_metrics", metrics)

        graph = _make_graph(req)
        result = check_test_coverage(graph, exclude_status=set())

        assert result.details["reqs_with_any_coverage"] == 1
        assert result.details["total_requirements"] == 1
        assert result.details["req_coverage_percent"] == 100.0

    # Implements: REQ-d00218-A
    def test_req_without_direct_tested_not_counted(self):
        """Requirement with tested.direct == 0 is not test-covered."""
        req = _make_req("REQ-d00001")
        metrics = RollupMetrics(
            total_assertions=2,
            tested=CoverageDimension(total=2, direct=0, indirect=0),
        )
        req.set_metric("rollup_metrics", metrics)

        graph = _make_graph(req)
        result = check_test_coverage(graph, exclude_status=set())

        assert result.details["reqs_with_any_coverage"] == 0

    # Implements: REQ-d00218-B
    def test_test_coverage_separate_from_code_coverage(self):
        """Test coverage uses tested.direct, not implemented.direct (which includes CODE)."""
        req = _make_req("REQ-d00001")
        # implemented.direct includes CODE refs; tested.direct is TEST-only
        metrics = RollupMetrics(
            total_assertions=3,
            implemented=CoverageDimension(total=3, direct=2, indirect=2),
            tested=CoverageDimension(total=3, direct=0, indirect=0),
        )
        req.set_metric("rollup_metrics", metrics)

        graph = _make_graph(req)
        result = check_test_coverage(graph, exclude_status=set())

        # Test coverage should be 0 even though implemented.direct is 2
        assert result.details["reqs_with_any_coverage"] == 0

    # Implements: REQ-d00218-C
    def test_excluded_statuses_filter_requirements(self):
        """Requirements with excluded status are not counted."""
        active_req = _make_req("REQ-d00001", status="Active")
        active_metrics = RollupMetrics(
            total_assertions=1,
            tested=CoverageDimension(total=1, direct=1, indirect=1),
        )
        active_req.set_metric("rollup_metrics", active_metrics)

        deprecated_req = _make_req("REQ-d00002", status="Deprecated")
        dep_metrics = RollupMetrics(
            total_assertions=1,
            tested=CoverageDimension(total=1, direct=0, indirect=0),
        )
        deprecated_req.set_metric("rollup_metrics", dep_metrics)

        graph = _make_graph(active_req, deprecated_req)
        result = check_test_coverage(graph, exclude_status={"Deprecated"})

        assert result.details["total_requirements"] == 1
        assert result.details["reqs_with_any_coverage"] == 1

    # Implements: REQ-d00218-C
    def test_parent_credit_from_child_test_coverage(self):
        """Parent REQ with rolled-up direct_tested > 0 counts as test-covered.

        RollupMetrics.direct_tested is already rolled up by the annotation
        pipeline, so a parent whose children have tests will have
        direct_tested > 0 in its metrics.
        """
        parent = _make_req("REQ-p00001", level="prd")
        # Simulate rollup: parent gets credit from child's test coverage
        parent_metrics = RollupMetrics(
            total_assertions=1,
            tested=CoverageDimension(total=1, direct=1, indirect=1),
        )
        parent.set_metric("rollup_metrics", parent_metrics)

        child = _make_req("REQ-d00001", level="dev")
        child_metrics = RollupMetrics(
            total_assertions=1,
            tested=CoverageDimension(total=1, direct=1, indirect=1),
        )
        child.set_metric("rollup_metrics", child_metrics)

        graph = _make_graph(parent, child)
        result = check_test_coverage(graph, exclude_status=set())

        assert result.details["reqs_with_any_coverage"] == 2
        assert result.details["total_requirements"] == 2

    # Implements: REQ-d00218-A
    def test_no_rollup_metrics_not_counted(self):
        """Requirement with no rollup_metrics at all is not test-covered."""
        req = _make_req("REQ-d00001")
        # No metrics set

        graph = _make_graph(req)
        result = check_test_coverage(graph, exclude_status=set())

        assert result.details["reqs_with_any_coverage"] == 0
        assert result.details["total_requirements"] == 1

    # Implements: REQ-d00218-A
    def test_multiple_reqs_mixed_coverage(self):
        """Mix of covered and uncovered requirements reports correctly."""
        req1 = _make_req("REQ-d00001")
        req1.set_metric(
            "rollup_metrics",
            RollupMetrics(
                total_assertions=2,
                tested=CoverageDimension(total=2, direct=2, indirect=2),
            ),
        )

        req2 = _make_req("REQ-d00002")
        req2.set_metric(
            "rollup_metrics",
            RollupMetrics(
                total_assertions=1,
                tested=CoverageDimension(total=1, direct=0, indirect=0),
            ),
        )

        req3 = _make_req("REQ-d00003")
        req3.set_metric(
            "rollup_metrics",
            RollupMetrics(
                total_assertions=3,
                tested=CoverageDimension(total=3, direct=1, indirect=1),
            ),
        )

        graph = _make_graph(req1, req2, req3)
        result = check_test_coverage(graph, exclude_status=set())

        assert result.details["total_requirements"] == 3
        assert result.details["reqs_with_any_coverage"] == 2
        assert result.details["req_coverage_percent"] == round(2 / 3 * 100, 1)


# =============================================================================
# REQ-d00219: check_uat_coverage
# =============================================================================


class TestCheckUatCoverage:
    """Tests for check_uat_coverage health check."""

    # Implements: REQ-d00219-A
    def test_returns_info_severity(self):
        """check_uat_coverage always returns severity=info."""
        graph = _make_graph()
        result = check_uat_coverage(graph, exclude_status=set())
        assert result.severity == "info"
        assert result.passed is True
        assert result.category == "uat"

    # Implements: REQ-d00219-A
    def test_no_requirements_zero_uat(self):
        """Empty graph reports 0/0 UAT coverage."""
        graph = _make_graph()
        result = check_uat_coverage(graph, exclude_status=set())
        assert result.name == "uat.uat_coverage"
        assert result.details["total_requirements"] == 0
        assert result.details["reqs_with_any_coverage"] == 0

    # Implements: REQ-d00219-A
    def test_req_with_uat_covered_counted(self):
        """Requirement with uat_covered > 0 is counted."""
        req = _make_req("REQ-d00001")
        metrics = RollupMetrics(
            total_assertions=2,
            uat_coverage=CoverageDimension(total=2, direct=1, indirect=1),
        )
        req.set_metric("rollup_metrics", metrics)

        graph = _make_graph(req)
        result = check_uat_coverage(graph, exclude_status=set())

        assert result.details["reqs_with_any_coverage"] == 1
        assert result.details["req_coverage_percent"] == 100.0

    # Implements: REQ-d00219-A
    def test_req_without_uat_covered_not_counted(self):
        """Requirement with uat_coverage.indirect == 0 is not counted."""
        req = _make_req("REQ-d00001")
        metrics = RollupMetrics(
            total_assertions=2,
            uat_coverage=CoverageDimension(total=2, direct=0, indirect=0),
        )
        req.set_metric("rollup_metrics", metrics)

        graph = _make_graph(req)
        result = check_uat_coverage(graph, exclude_status=set())

        assert result.details["reqs_with_any_coverage"] == 0

    # Implements: REQ-d00219-A
    def test_excluded_statuses_filter(self):
        """UAT coverage excludes requirements with excluded status."""
        active = _make_req("REQ-d00001", status="Active")
        active.set_metric(
            "rollup_metrics",
            RollupMetrics(
                uat_coverage=CoverageDimension(total=1, direct=1, indirect=1),
            ),
        )

        rejected = _make_req("REQ-d00002", status="Rejected")
        rejected.set_metric(
            "rollup_metrics",
            RollupMetrics(
                uat_coverage=CoverageDimension(total=1, direct=1, indirect=1),
            ),
        )

        graph = _make_graph(active, rejected)
        result = check_uat_coverage(graph, exclude_status={"Rejected"})

        assert result.details["total_requirements"] == 1
        assert result.details["reqs_with_any_coverage"] == 1

    # Implements: REQ-d00219-A
    def test_no_rollup_metrics_not_counted(self):
        """Requirement with no metrics is not UAT-covered."""
        req = _make_req("REQ-d00001")
        graph = _make_graph(req)
        result = check_uat_coverage(graph, exclude_status=set())

        assert result.details["reqs_with_any_coverage"] == 0
        assert result.details["total_requirements"] == 1


# =============================================================================
# REQ-d00219: check_uat_results
# =============================================================================


class TestCheckUatResults:
    """Tests for check_uat_results parsing UAT CSV files."""

    # Implements: REQ-d00219-B
    def test_missing_csv_reports_skipped(self, tmp_path):
        """Missing CSV file produces info-severity passed check."""
        config = {
            "scanning": {"journey": {"results_file": "nonexistent.csv"}},
            "_git_root": str(tmp_path),
        }
        graph = _make_graph()
        result = check_uat_results(graph, config=config)

        assert result.passed is True
        assert result.severity == "info"
        assert result.name == "uat.results"
        assert "nonexistent.csv" in result.message

    # Implements: REQ-d00219-C
    def test_all_passing_csv(self, tmp_path):
        """CSV with all pass results produces passing check."""
        csv_file = tmp_path / "uat-results.csv"
        csv_file.write_text("journey_id,status\nJNY-001,pass\nJNY-002,passed\n")

        config = {
            "scanning": {"journey": {"results_file": str(csv_file)}},
        }
        graph = _make_graph()
        result = check_uat_results(graph, config=config)

        assert result.passed is True
        assert result.name == "uat.results"
        assert result.details["passed"] == 2
        assert result.details["failed"] == 0
        assert result.details["skipped"] == 0

    # Implements: REQ-d00219-D
    def test_failures_flagged(self, tmp_path):
        """CSV with failures produces failing check with findings."""
        csv_file = tmp_path / "uat-results.csv"
        csv_file.write_text(
            "journey_id,status\n" "JNY-001,pass\n" "JNY-002,fail\n" "JNY-003,failed\n"
        )

        config = {
            "scanning": {"journey": {"results_file": str(csv_file)}},
        }
        graph = _make_graph()
        result = check_uat_results(graph, config=config)

        assert result.passed is False
        assert result.severity == "warning"
        assert result.details["passed"] == 1
        assert result.details["failed"] == 2
        assert len(result.findings) == 2
        finding_ids = [f.node_id for f in result.findings]
        assert "JNY-002" in finding_ids
        assert "JNY-003" in finding_ids

    # Implements: REQ-d00219-C
    def test_pass_fail_skip_counts(self, tmp_path):
        """CSV with all status types reports correct counts."""
        csv_file = tmp_path / "uat-results.csv"
        csv_file.write_text(
            "journey_id,status\n"
            "JNY-001,pass\n"
            "JNY-002,passed\n"
            "JNY-003,fail\n"
            "JNY-004,skip\n"
            "JNY-005,skipped\n"
        )

        config = {
            "scanning": {"journey": {"results_file": str(csv_file)}},
        }
        graph = _make_graph()
        result = check_uat_results(graph, config=config)

        assert result.details["passed"] == 2
        assert result.details["failed"] == 1
        assert result.details["skipped"] == 2
        assert result.details["pass_rate"] == round(2 / 5 * 100, 1)

    # Implements: REQ-d00219-B
    def test_default_results_file(self, tmp_path):
        """Defaults to uat-results.csv when no config provided."""
        # No config at all — should try uat-results.csv in cwd
        graph = _make_graph()
        result = check_uat_results(graph, config=None)

        # With no file present, should be info/skipped
        assert result.passed is True
        assert result.severity == "info"

    # Implements: REQ-d00219-B
    def test_empty_csv_reports_info(self, tmp_path):
        """Empty CSV file (headers only) is reported as info."""
        csv_file = tmp_path / "uat-results.csv"
        csv_file.write_text("journey_id,status\n")

        config = {
            "scanning": {"journey": {"results_file": str(csv_file)}},
        }
        graph = _make_graph()
        result = check_uat_results(graph, config=config)

        assert result.passed is True
        assert result.severity == "info"

    # Implements: REQ-d00219-C
    def test_uat_results_category_is_uat(self, tmp_path):
        """check_uat_results returns category='uat'."""
        csv_file = tmp_path / "uat-results.csv"
        csv_file.write_text("journey_id,status\nJNY-001,pass\n")

        config = {
            "scanning": {"journey": {"results_file": str(csv_file)}},
        }
        graph = _make_graph()
        result = check_uat_results(graph, config=config)

        assert result.category == "uat"

    # Implements: REQ-d00219-C
    def test_pass_rate_calculation(self, tmp_path):
        """Pass rate is correctly calculated."""
        csv_file = tmp_path / "uat-results.csv"
        csv_file.write_text(
            "journey_id,status\n"
            "JNY-001,pass\n"
            "JNY-002,pass\n"
            "JNY-003,fail\n"
            "JNY-004,pass\n"
        )

        config = {
            "scanning": {"journey": {"results_file": str(csv_file)}},
        }
        graph = _make_graph()
        result = check_uat_results(graph, config=config)

        assert result.details["pass_rate"] == 75.0

    # Implements: REQ-d00219-B
    def test_git_root_path_resolution(self, tmp_path):
        """Relative results_file path resolves via _git_root config."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        csv_file = tmp_path / "my-results.csv"
        csv_file.write_text("journey_id,status\nJNY-001,pass\n")

        config = {
            "scanning": {"journey": {"results_file": "my-results.csv"}},
            "_git_root": str(tmp_path),
        }
        graph = _make_graph()
        result = check_uat_results(graph, config=config)

        assert result.passed is True
        assert result.details["passed"] == 1


# =============================================================================
# REQ-d00219: run_uat_checks
# =============================================================================


class TestRunUatChecks:
    """Tests for the run_uat_checks aggregation function."""

    # Implements: REQ-d00219-A
    def test_returns_coverage_verified_and_results(self):
        """run_uat_checks returns uat.uat_coverage, uat.uat_verified, and uat.results checks."""
        graph = _make_graph()
        checks = run_uat_checks(graph, exclude_status=set(), config={})

        assert len(checks) == 3
        names = {c.name for c in checks}
        assert "uat.uat_coverage" in names
        assert "uat.uat_verified" in names
        assert "uat.results" in names

    # Implements: REQ-d00219-A
    def test_passes_exclude_status_to_coverage(self):
        """run_uat_checks forwards exclude_status to check_uat_coverage."""
        req_active = _make_req("REQ-d00001", status="Active")
        req_active.set_metric(
            "rollup_metrics",
            RollupMetrics(
                uat_coverage=CoverageDimension(total=1, direct=1, indirect=1),
            ),
        )

        req_deprecated = _make_req("REQ-d00002", status="Deprecated")
        req_deprecated.set_metric(
            "rollup_metrics",
            RollupMetrics(
                uat_coverage=CoverageDimension(total=1, direct=1, indirect=1),
            ),
        )

        graph = _make_graph(req_active, req_deprecated)
        checks = run_uat_checks(graph, exclude_status={"Deprecated"}, config={})

        coverage_check = next(c for c in checks if c.name == "uat.uat_coverage")
        assert coverage_check.details["total_requirements"] == 1
        assert coverage_check.details["reqs_with_any_coverage"] == 1
