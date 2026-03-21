# Validates REQ-d00086-A, REQ-d00086-B, REQ-d00086-C, REQ-d00086-D
"""Tests for elspais summary command.

Validates that the summary command produces correct level groupings
and supports all four output formats (text, markdown, json, csv).
Summary is level-aggregated only; per-requirement detail is in the trace command.
"""

from __future__ import annotations

import csv
import io
import json

from elspais.commands.summary import _collect_coverage, _pct, _render
from elspais.graph.builder import TraceGraph
from elspais.graph.GraphNode import GraphNode, NodeKind
from elspais.graph.metrics import RollupMetrics

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_graph() -> TraceGraph:
    """Create a minimal empty TraceGraph."""
    return TraceGraph()


def _add_requirement(
    graph: TraceGraph,
    req_id: str,
    title: str = "Requirement Title",
    level: str = "prd",
    status: str = "Active",
    *,
    as_root: bool = True,
) -> GraphNode:
    """Add a REQUIREMENT node with level and status set."""
    node = GraphNode(req_id, NodeKind.REQUIREMENT, label=title)
    node.set_field("level", level)
    node.set_field("status", status)
    graph._index[req_id] = node
    if as_root:
        graph._roots.append(node)
    return node


def _set_rollup(
    node: GraphNode,
    total: int = 0,
    covered: int = 0,
    tested: int = 0,
    validated: int = 0,
    has_failures: bool = False,
) -> None:
    """Attach a RollupMetrics to a node."""
    from elspais.graph.metrics import CoverageDimension

    rm = RollupMetrics(
        total_assertions=total,
        implemented=CoverageDimension(total=total, direct=covered, indirect=covered),
        tested=CoverageDimension(total=total, direct=tested, indirect=tested),
        verified=CoverageDimension(
            total=total, direct=validated, indirect=validated, has_failures=has_failures
        ),
    )
    node.set_metric("rollup_metrics", rm)


def _build_mixed_graph() -> TraceGraph:
    """Build a graph with PRD, OPS, DEV requirements for multi-level tests.

    Layout:
      PRD: REQ-p00001 (3 assertions, 2 implemented, 1 tested, 1 passing)
           REQ-p00002 (2 assertions, 2 implemented, 2 tested, 0 passing)
      OPS: REQ-o00001 (4 assertions, 3 implemented, 2 tested, 2 passing)
      DEV: REQ-d00001 (1 assertion, 1 implemented, 1 tested, 1 passing)
           REQ-d00002 (Draft - should be excluded)
           REQ-d00003 (Deprecated - should be excluded)
    """
    graph = _make_graph()

    # PRD
    p1 = _add_requirement(graph, "REQ-p00001", "PRD Req One", level="prd")
    _set_rollup(p1, total=3, covered=2, tested=1, validated=1)

    p2 = _add_requirement(graph, "REQ-p00002", "PRD Req Two", level="prd")
    _set_rollup(p2, total=2, covered=2, tested=2, validated=0)

    # OPS
    o1 = _add_requirement(graph, "REQ-o00001", "OPS Req One", level="ops")
    _set_rollup(o1, total=4, covered=3, tested=2, validated=2)

    # DEV
    d1 = _add_requirement(graph, "REQ-d00001", "DEV Req One", level="dev")
    _set_rollup(d1, total=1, covered=1, tested=1, validated=1)

    d2 = _add_requirement(graph, "REQ-d00002", "DEV Draft", level="dev", status="Draft")
    _set_rollup(d2, total=2, covered=2, tested=2, validated=2)

    d3 = _add_requirement(graph, "REQ-d00003", "DEV Deprecated", level="dev", status="Deprecated")
    _set_rollup(d3, total=1, covered=1, tested=1, validated=1)

    return graph


# ===========================================================================
# Verifies: _collect_coverage data structure
# ===========================================================================


class TestCollectCoverage:
    """Validates REQ-d00086-D: Uses existing graph aggregate functions."""

    def test_REQ_d00086_D_returns_levels_and_excluded_keys(self):
        """_collect_coverage returns dict with 'levels' list and 'excluded' dict."""
        graph = _make_graph()
        data = _collect_coverage(graph)

        assert "levels" in data
        assert "excluded" in data
        assert isinstance(data["levels"], list)
        assert isinstance(data["excluded"], dict)
        # Empty graph has 3 zero-count levels and no exclusions
        assert len(data["levels"]) == 3
        assert all(lv["total"] == 0 for lv in data["levels"])
        assert data["excluded"] == {}

    def test_REQ_d00086_D_levels_always_three(self):
        """There are always exactly 3 level entries (PRD, OPS, DEV)."""
        graph = _make_graph()
        data = _collect_coverage(graph)

        assert len(data["levels"]) == 3
        level_names = [lv["level"] for lv in data["levels"]]
        assert level_names == ["PRD", "OPS", "DEV"]

    def test_REQ_d00086_D_no_requirements_key(self):
        """Coverage data no longer includes per-requirement rows."""
        graph = _make_graph()
        _add_requirement(graph, "REQ-p00001", "Test", level="prd")
        data = _collect_coverage(graph)
        assert "requirements" not in data


# ===========================================================================
# Verifies: Level grouping
# ===========================================================================


class TestLevelGrouping:
    """Validates REQ-d00086-A: Group by level (PRD, OPS, DEV) with counts and percentages."""

    def test_REQ_d00086_A_groups_by_level(self):
        """Requirements are grouped into correct level buckets."""
        graph = _build_mixed_graph()
        data = _collect_coverage(graph)

        prd, ops, dev = data["levels"]

        assert prd["level"] == "PRD"
        assert prd["total"] == 2

        assert ops["level"] == "OPS"
        assert ops["total"] == 1

        # DEV: 1 active req (d00002=Draft, d00003=Deprecated excluded)
        assert dev["level"] == "DEV"
        assert dev["total"] == 1

    def test_REQ_d00086_A_level_assertion_counts(self):
        """Level summaries aggregate assertion counts from child requirements."""
        graph = _build_mixed_graph()
        data = _collect_coverage(graph)

        prd, ops, dev = data["levels"]

        # PRD: p00001(3) + p00002(2) = 5 total assertions
        assert prd["total_assertions"] == 5
        assert prd["implemented_assertions"] == 4  # 2 + 2
        assert prd["validated_assertions"] == 3  # 1 + 2
        assert prd["passing_assertions"] == 1  # 1 + 0

        # OPS: o00001 only
        assert ops["total_assertions"] == 4
        assert ops["implemented_assertions"] == 3
        assert ops["validated_assertions"] == 2
        assert ops["passing_assertions"] == 2

        # DEV: d00001 only (d00002 Draft excluded, d00003 Deprecated excluded)
        assert dev["total_assertions"] == 1
        assert dev["implemented_assertions"] == 1
        assert dev["validated_assertions"] == 1
        assert dev["passing_assertions"] == 1

    def test_REQ_d00086_A_with_code_refs_count(self):
        """with_code_refs counts reqs that have at least one implemented assertion."""
        graph = _build_mixed_graph()
        data = _collect_coverage(graph)

        prd, ops, dev = data["levels"]

        assert prd["with_code_refs"] == 2
        assert ops["with_code_refs"] == 1
        assert dev["with_code_refs"] == 1

    def test_REQ_d00086_A_with_test_refs_count(self):
        """with_test_refs counts reqs that have at least one validated assertion."""
        graph = _build_mixed_graph()
        data = _collect_coverage(graph)

        prd, ops, dev = data["levels"]

        assert prd["with_test_refs"] == 2
        assert ops["with_test_refs"] == 1
        assert dev["with_test_refs"] == 1

    def test_REQ_d00086_A_with_passing_count(self):
        """with_passing counts reqs that have at least one passing assertion."""
        graph = _build_mixed_graph()
        data = _collect_coverage(graph)

        prd, ops, dev = data["levels"]

        assert prd["with_passing"] == 1  # only p00001 has passing > 0
        assert ops["with_passing"] == 1
        assert dev["with_passing"] == 1

    def test_REQ_d00086_A_empty_level(self):
        """Levels with no requirements have zero counts."""
        graph = _make_graph()
        _add_requirement(graph, "REQ-p00001", "Solo", level="prd")

        data = _collect_coverage(graph)
        prd, ops, dev = data["levels"]

        assert prd["total"] == 1
        assert ops["total"] == 0
        assert dev["total"] == 0
        assert ops["total_assertions"] == 0


# ===========================================================================
# Verifies: Draft/Deprecated exclusion
# ===========================================================================


class TestStatusExclusion:
    """Validates REQ-d00086-A: Draft and Deprecated requirements are excluded."""

    def test_REQ_d00086_A_excludes_draft_from_counts(self):
        """Draft requirements are excluded from level counts."""
        graph = _make_graph()
        _add_requirement(graph, "REQ-d00001", "Active", level="dev", status="Active")
        draft = _add_requirement(graph, "REQ-d00002", "Draft", level="dev", status="Draft")
        _set_rollup(draft, total=5, covered=5, tested=5, validated=5)

        data = _collect_coverage(graph)
        dev = data["levels"][2]

        assert dev["total"] == 1
        assert dev["total_assertions"] == 0

    def test_REQ_d00086_A_excludes_deprecated_from_counts(self):
        """Deprecated requirements are excluded from level counts."""
        graph = _make_graph()
        _add_requirement(graph, "REQ-d00001", "Active", level="dev", status="Active")
        dep = _add_requirement(graph, "REQ-d00003", "Deprecated", level="dev", status="Deprecated")
        _set_rollup(dep, total=3, covered=3, tested=3, validated=3)

        data = _collect_coverage(graph)
        dev = data["levels"][2]

        assert dev["total"] == 1
        assert dev["total_assertions"] == 0


# ===========================================================================
# Verifies: Output format - Text
# ===========================================================================


class TestTextFormat:
    """Validates REQ-d00086-C: Text format output."""

    def test_REQ_d00086_C_text_has_header(self):
        """Text output starts with 'Coverage Summary' header."""
        graph = _make_graph()
        data = _collect_coverage(graph)
        output = _render(data, "text")

        assert output.startswith("Coverage Summary\n")

    def test_REQ_d00086_C_text_level_summary(self):
        """Text output contains level summary section."""
        graph = _make_graph()
        node = _add_requirement(graph, "REQ-p00001", "Test", level="prd")
        _set_rollup(node, total=2, covered=1, tested=1, validated=1)

        data = _collect_coverage(graph)
        output = _render(data, "text")

        assert "Summary by Level" in output
        assert "PRD:" in output
        assert "Implemented:" in output
        assert "Validated:" in output
        assert "Passing:" in output

    def test_REQ_d00086_C_text_no_per_requirement_section(self):
        """Text output does not contain per-requirement section."""
        graph = _make_graph()
        node = _add_requirement(graph, "REQ-p00001", "My Requirement", level="prd")
        _set_rollup(node, total=2, covered=1, tested=1, validated=0)

        data = _collect_coverage(graph)
        output = _render(data, "text")

        assert "Per-Requirement Coverage" not in output

    def test_REQ_d00086_C_text_skips_empty_levels(self):
        """Text output skips levels with zero requirements."""
        graph = _make_graph()
        _add_requirement(graph, "REQ-p00001", "Only PRD", level="prd")

        data = _collect_coverage(graph)
        output = _render(data, "text")

        assert "PRD:" in output
        assert "OPS:" not in output
        assert "DEV:" not in output


# ===========================================================================
# Verifies: Output format - Markdown
# ===========================================================================


class TestMarkdownFormat:
    """Validates REQ-d00086-C: Markdown format output."""

    def test_REQ_d00086_C_markdown_has_heading(self):
        """Markdown output starts with '# Coverage Summary'."""
        graph = _make_graph()
        data = _collect_coverage(graph)
        output = _render(data, "markdown")

        assert "# Coverage Summary" in output

    def test_REQ_d00086_C_markdown_level_summary_table(self):
        """Markdown output has a level summary table with correct headers."""
        graph = _make_graph()
        node = _add_requirement(graph, "REQ-p00001", "Test", level="prd")
        _set_rollup(node, total=2, covered=1, tested=1, validated=1)

        data = _collect_coverage(graph)
        output = _render(data, "markdown")

        assert "## Summary by Level" in output
        assert "| Level | Requirements | Assertions | Implemented | Validated | Passing |" in output
        assert "|-------|" in output

    def test_REQ_d00086_C_markdown_no_per_requirement_table(self):
        """Markdown output does not contain per-requirement table."""
        graph = _make_graph()
        node = _add_requirement(graph, "REQ-p00001", "Test", level="prd")
        _set_rollup(node, total=2, covered=1, tested=1, validated=1)

        data = _collect_coverage(graph)
        output = _render(data, "markdown")

        assert "## Per-Requirement Coverage" not in output

    def test_REQ_d00086_C_markdown_level_rows_pipe_delimited(self):
        """Markdown level rows use pipe delimiters."""
        graph = _make_graph()
        node = _add_requirement(graph, "REQ-p00001", "Test", level="prd")
        _set_rollup(node, total=2, covered=2, tested=1, validated=1)

        data = _collect_coverage(graph)
        output = _render(data, "markdown")

        lines = output.split("\n")
        data_lines = [ln for ln in lines if "| PRD |" in ln]
        assert len(data_lines) >= 1
        assert data_lines[0].startswith("| ")
        assert data_lines[0].endswith(" |")


# ===========================================================================
# Verifies: Output format - JSON
# ===========================================================================


class TestJsonFormat:
    """Validates REQ-d00086-C: JSON format output."""

    def test_REQ_d00086_C_json_has_levels_and_excluded(self):
        """JSON output contains 'levels' and 'excluded' keys."""
        graph = _build_mixed_graph()
        data = _collect_coverage(graph)
        output = _render(data, "json")

        parsed = json.loads(output)
        assert "levels" in parsed
        assert "excluded" in parsed

    def test_REQ_d00086_C_json_level_structure(self):
        """JSON level entries have expected fields."""
        graph = _make_graph()
        node = _add_requirement(graph, "REQ-p00001", "Test", level="prd")
        _set_rollup(node, total=3, covered=2, tested=1, validated=1)

        data = _collect_coverage(graph)
        output = _render(data, "json")
        parsed = json.loads(output)

        prd = parsed["levels"][0]
        assert prd["level"] == "PRD"
        assert prd["total"] == 1
        assert prd["total_assertions"] == 3
        assert prd["implemented_assertions"] == 2
        assert prd["validated_assertions"] == 1
        assert prd["passing_assertions"] == 1

    def test_REQ_d00086_C_json_excluded_counts(self):
        """JSON output includes excluded status counts."""
        graph = _build_mixed_graph()
        data = _collect_coverage(graph)
        output = _render(data, "json")
        parsed = json.loads(output)

        assert parsed["excluded"]["Draft"] == 1
        assert parsed["excluded"]["Deprecated"] == 1


# ===========================================================================
# Verifies: Output format - CSV
# ===========================================================================


class TestCsvFormat:
    """Validates REQ-d00086-C: CSV format output."""

    def test_REQ_d00086_C_csv_has_correct_headers(self):
        """CSV output has the expected column headers."""
        graph = _make_graph()
        data = _collect_coverage(graph)
        output = _render(data, "csv")

        reader = csv.reader(io.StringIO(output))
        headers = next(reader)

        expected_headers = [
            "Level",
            "Requirements",
            "Assertions",
            "Implemented",
            "Implemented %",
            "Validated",
            "Validated %",
            "Passing",
            "Passing %",
        ]
        assert headers == expected_headers

    def test_REQ_d00086_C_csv_row_count(self):
        """CSV has one header row plus one row per level."""
        graph = _build_mixed_graph()
        data = _collect_coverage(graph)
        output = _render(data, "csv")

        reader = csv.reader(io.StringIO(output))
        rows = list(reader)

        # 1 header + 3 levels (PRD, OPS, DEV)
        assert len(rows) == 4

    def test_REQ_d00086_C_csv_row_values(self):
        """CSV data rows contain correct level summary values."""
        graph = _make_graph()
        node = _add_requirement(graph, "REQ-p00001", "CSV Req", level="prd")
        _set_rollup(node, total=4, covered=3, tested=2, validated=1)

        data = _collect_coverage(graph)
        output = _render(data, "csv")

        reader = csv.reader(io.StringIO(output))
        _header = next(reader)
        row = next(reader)  # PRD row

        assert row[0] == "PRD"  # Level
        assert row[1] == "1"  # Requirements
        assert row[2] == "4"  # Assertions
        assert row[3] == "3"  # Implemented
        assert row[4] == "75.0"  # Implemented %
        assert row[5] == "2"  # Validated
        assert row[6] == "50.0"  # Validated %
        assert row[7] == "1"  # Passing
        assert row[8] == "25.0"  # Passing %

    def test_REQ_d00086_C_csv_parseable(self):
        """CSV output is parseable by Python csv module without errors."""
        graph = _build_mixed_graph()
        data = _collect_coverage(graph)
        output = _render(data, "csv")

        reader = csv.DictReader(io.StringIO(output))
        rows = list(reader)

        assert len(rows) == 3  # 3 levels
        for row in rows:
            int(row["Requirements"])
            int(row["Assertions"])
            int(row["Implemented"])
            float(row["Implemented %"])
            int(row["Validated"])
            float(row["Validated %"])
            int(row["Passing"])
            float(row["Passing %"])


# ===========================================================================
# Verifies: _render format dispatch
# ===========================================================================


class TestRenderDispatch:
    """Validates REQ-d00086-C: Support text, markdown, json, csv formats."""

    def test_REQ_d00086_C_render_text_default(self):
        """Unknown format falls back to text."""
        graph = _make_graph()
        data = _collect_coverage(graph)
        output = _render(data, "unknown")

        assert "Coverage Summary" in output
        assert output == _render(data, "text")


# ===========================================================================
# Verifies: _pct helper
# ===========================================================================


class TestPctHelper:
    """Validates REQ-d00086-B: Percentage calculation helper."""

    def test_REQ_d00086_B_pct_normal(self):
        """_pct computes correct percentage."""
        assert _pct(3, 10) == 30.0
        assert _pct(1, 3) == 33.3
        assert _pct(10, 10) == 100.0

    def test_REQ_d00086_B_pct_zero_denom(self):
        """_pct returns 0.0 when denominator is zero."""
        assert _pct(0, 0) == 0.0
        assert _pct(5, 0) == 0.0

    def test_REQ_d00086_B_pct_zero_num(self):
        """_pct returns 0.0 when numerator is zero."""
        assert _pct(0, 10) == 0.0
