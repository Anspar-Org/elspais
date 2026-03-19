# Verifies: REQ-d00085
"""Tests that health check functions populate findings with structured data.

Validates REQ-d00085-I: Each check function should produce HealthFinding instances
with appropriate message, node_id, file_path, and line fields when issues are detected.
"""

from __future__ import annotations

from pathlib import Path

from elspais.commands.health import (
    HealthFinding,
    check_broken_references,
    check_spec_format_rules,
    check_spec_hierarchy_levels,
    check_spec_implements_resolve,
    check_spec_no_duplicates,
    check_spec_refines_resolve,
    check_test_results,
)
from elspais.config import _merge_configs, config_defaults, get_config
from elspais.graph.builder import TraceGraph
from elspais.graph.factory import build_graph
from elspais.graph.GraphNode import GraphNode, NodeKind


def _load_config(config_path: Path) -> dict:
    raw = get_config(config_path)
    return _merge_configs(config_defaults(), raw)


def _make_config(tmp_path: Path) -> Path:
    """Create a minimal .elspais.toml config and return its path."""
    config_path = tmp_path / ".elspais.toml"
    config_path.write_text(
        """version = 3

[project]
name = "test"

[scanning.spec]
directories = ["spec"]
"""
    )
    return config_path


def _build(tmp_path: Path, config_path: Path, **kwargs):
    """Build a graph with common defaults."""
    defaults = {
        "spec_dirs": [tmp_path / "spec"],
        "config_path": config_path,
        "repo_root": tmp_path,
        "scan_code": False,
        "scan_tests": False,
    }
    defaults.update(kwargs)
    return build_graph(**defaults)


class TestCheckSpecNoDuplicatesFindings:
    """Findings should identify each duplicate requirement with node_id and file_path."""

    def test_REQ_d00085_I_duplicates_have_findings(self, tmp_path: Path) -> None:
        # The graph builder deduplicates by ID (dict keyed by ID), so we
        # construct the graph manually with two nodes sharing the same .id
        # but stored under different index keys.
        graph = TraceGraph()
        node_a = GraphNode(
            id="REQ-p00001",
            kind=NodeKind.REQUIREMENT,
            label="First Copy",
        )
        node_a.set_field("source_file", "spec/file_a.md")
        node_b = GraphNode(
            id="REQ-p00001",
            kind=NodeKind.REQUIREMENT,
            label="Second Copy",
        )
        node_b.set_field("source_file", "spec/file_b.md")
        # Store under different keys so both survive in the index
        graph._index["REQ-p00001__dup1"] = node_a
        graph._index["REQ-p00001__dup2"] = node_b

        check = check_spec_no_duplicates(graph)

        assert not check.passed, "Expected check to fail with duplicate IDs"
        assert len(check.findings) > 0, "Expected findings for duplicates"
        finding = check.findings[0]
        assert isinstance(finding, HealthFinding)
        assert finding.node_id is not None, "Finding should have node_id"
        assert "REQ-p00001" in (finding.node_id or "")


class TestCheckSpecImplementsResolveFindings:
    """Findings should identify each unresolved implements reference."""

    def test_REQ_d00085_I_unresolved_implements_have_findings(self, tmp_path: Path) -> None:
        # The builder stores implements as pending edge links, not as a node
        # field. The check function reads node.get_field("implements", []),
        # so we construct the graph manually with the field set directly.
        graph = TraceGraph()
        node = GraphNode(
            id="REQ-d00001",
            kind=NodeKind.REQUIREMENT,
            label="Dev Requirement",
        )
        node.set_field("level", "DEV")
        node.set_field("status", "Active")
        node.set_field("implements", ["REQ-p99999"])
        graph._index["REQ-d00001"] = node

        check = check_spec_implements_resolve(graph)

        assert not check.passed, "Expected check to fail with unresolved implements"
        assert len(check.findings) > 0, "Expected findings for unresolved implements"
        finding = check.findings[0]
        assert isinstance(finding, HealthFinding)
        assert finding.node_id is not None, "Finding should have node_id (the 'from' req)"
        assert "REQ-d00001" in (finding.node_id or "")
        assert finding.message, "Finding should have a message"


class TestCheckSpecRefinesResolveFindings:
    """Findings should identify each unresolved refines reference."""

    def test_REQ_d00085_I_unresolved_refines_have_findings(self, tmp_path: Path) -> None:
        # Same issue as implements: the builder stores refines as pending
        # edge links, not as a node field. Construct manually.
        graph = TraceGraph()
        node = GraphNode(
            id="REQ-d00002",
            kind=NodeKind.REQUIREMENT,
            label="Dev Refines",
        )
        node.set_field("level", "DEV")
        node.set_field("status", "Active")
        node.set_field("refines", ["REQ-p88888"])
        graph._index["REQ-d00002"] = node

        check = check_spec_refines_resolve(graph)

        assert not check.passed, "Expected check to fail with unresolved refines"
        assert len(check.findings) > 0, "Expected findings for unresolved refines"
        finding = check.findings[0]
        assert isinstance(finding, HealthFinding)
        assert finding.node_id is not None, "Finding should have node_id"
        assert "REQ-d00002" in (finding.node_id or "")
        assert finding.message, "Finding should have a message"


class TestCheckSpecHierarchyLevelsFindings:
    """Findings should identify each hierarchy level violation."""

    def test_REQ_d00085_I_hierarchy_violations_have_findings(self, tmp_path: Path) -> None:
        config_path = tmp_path / ".elspais.toml"
        config_path.write_text(
            """version = 3

[project]
name = "test"

[scanning.spec]
directories = ["spec"]

[validation]
strict_hierarchy = true

[levels.prd]
rank = 1
letter = "p"
implements = []

[levels.ops]
rank = 2
letter = "o"
implements = ["prd"]

[levels.dev]
rank = 3
letter = "d"
implements = ["ops", "prd"]
"""
        )

        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        # PRD implementing PRD is a violation (prd has no allowed parents)
        (spec_dir / "reqs.md").write_text(
            """# REQ-p00001: Parent PRD

**Level**: PRD | **Status**: Active

## Assertions

A. The system SHALL exist.

*End* *Parent PRD* | **Hash**: eeee5555

# REQ-p00002: Child PRD

**Level**: PRD | **Status**: Active
**Implements**: REQ-p00001

## Assertions

A. The system SHALL also exist.

*End* *Child PRD* | **Hash**: ffff6666
"""
        )

        graph = _build(tmp_path, config_path)
        config = _load_config(config_path)
        check = check_spec_hierarchy_levels(graph, config)

        assert not check.passed, "Expected check to fail with hierarchy violations"
        assert len(check.findings) > 0, "Expected findings for hierarchy violations"
        finding = check.findings[0]
        assert isinstance(finding, HealthFinding)
        assert finding.node_id is not None, "Finding should have node_id"


class TestCheckBrokenReferencesFindings:
    """Findings should identify each broken reference."""

    def test_REQ_d00085_I_broken_refs_have_findings(self, tmp_path: Path) -> None:
        config_path = tmp_path / ".elspais.toml"
        config_path.write_text(
            """version = 3

[project]
name = "test"

[scanning.spec]
directories = ["spec"]

[scanning.code]
directories = ["src"]
"""
        )
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        (spec_dir / "reqs.md").write_text(
            """# REQ-p00001: Real Requirement

**Level**: PRD | **Status**: Active

## Assertions

A. The system SHALL exist.

*End* *Real Requirement* | **Hash**: gggg7777
"""
        )

        # Create a code file referencing a non-existent requirement to create broken ref
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "orphan.py").write_text(
            """# Implements: REQ-d99999
def orphan_func():
    pass
"""
        )

        graph = _build(tmp_path, config_path, scan_code=True)
        check = check_broken_references(graph)

        assert not check.passed, "Expected check to fail with broken references"
        assert len(check.findings) > 0, "Expected findings for broken references"
        finding = check.findings[0]
        assert isinstance(finding, HealthFinding)
        assert finding.node_id is not None, "Finding should have node_id"


class TestCheckSpecFormatRulesFindings:
    """Findings should identify each format violation."""

    def test_REQ_d00085_I_format_violations_have_findings(self, tmp_path: Path) -> None:
        config_path = tmp_path / ".elspais.toml"
        config_path.write_text(
            """version = 3

[project]
name = "test"

[scanning.spec]
directories = ["spec"]

[rules.format]
require_hash = true
require_assertions = true
"""
        )

        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        # Requirement with no hash and no assertions triggers format violations
        (spec_dir / "reqs.md").write_text(
            """# REQ-p00010: No Hash No Assertions

**Level**: PRD | **Status**: Active

This requirement has no assertions section and no hash.

*End* *No Hash No Assertions*
"""
        )

        graph = _build(tmp_path, config_path)
        config = _load_config(config_path)
        check = check_spec_format_rules(graph, config)

        assert not check.passed, "Expected check to fail with format violations"
        assert len(check.findings) > 0, "Expected findings for format violations"
        finding = check.findings[0]
        assert isinstance(finding, HealthFinding)
        assert finding.node_id is not None, "Finding should have node_id"
        assert "REQ-p00010" in (finding.node_id or "")


class TestCheckTestResultsFindings:
    """Findings should identify test failures."""

    def test_REQ_d00085_I_test_failures_have_findings(self, tmp_path: Path) -> None:
        config_path = tmp_path / ".elspais.toml"
        config_path.write_text(
            """version = 3

[project]
name = "test"

[scanning.spec]
directories = ["spec"]

[scanning.test]
enabled = true
directories = ["tests"]

[scanning.result]
file_patterns = ["results/junit.xml"]
"""
        )

        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        (spec_dir / "reqs.md").write_text(
            """# REQ-p00001: Real Requirement

**Level**: PRD | **Status**: Active

## Assertions

A. The system SHALL do something.

*End* *Real Requirement* | **Hash**: jjjj0000
"""
        )

        # Create a JUnit XML with a failed test
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        (results_dir / "junit.xml").write_text(
            """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="tests" tests="2" failures="1">
    <testcase classname="tests.test_thing" name="test_REQ_p00001_pass" time="0.01"/>
    <testcase classname="tests.test_thing" name="test_REQ_p00001_fail" time="0.02">
      <failure message="AssertionError">assert False</failure>
    </testcase>
  </testsuite>
</testsuites>
"""
        )

        graph = _build(tmp_path, config_path, scan_tests=True)
        check = check_test_results(graph)

        assert not check.passed, "Expected check to fail with test failures"
        assert len(check.findings) > 0, "Expected findings for test failures"
        finding = check.findings[0]
        assert isinstance(finding, HealthFinding)
        assert finding.message, "Finding should have a message"


class TestCheckSpecNoDuplicateRefinesFindings:
    """Findings should identify requirements with redundant refs detected at parse time.

    Validates REQ-d00085-I: check_spec_needs_rewrite must produce HealthFinding
    instances with node_id when a requirement has parse_dirty=True (set by the builder
    when has_redundant_refs was True in parsed_data).
    """

    def test_REQ_d00085_I_duplicate_refines_have_findings(self, tmp_path: Path) -> None:
        # Verifies: REQ-d00085-I
        """A requirement with parse_dirty=True should produce a finding.

        parse_dirty is set by the builder when the parser detected duplicate refs
        (has_redundant_refs=True in parsed_data). The check reads parse_dirty instead
        of counting **Refines**: occurrences in body_text, since multiple Refines lines
        are now valid — only true duplicate refs should be flagged.
        """
        from elspais.commands.health import check_spec_needs_rewrite

        graph = TraceGraph()
        node = GraphNode(
            id="REQ-p00001",
            kind=NodeKind.REQUIREMENT,
            label="Corrupted Requirement",
        )
        # Simulate what the builder sets when has_redundant_refs=True
        node.set_field("parse_dirty", True)
        node.set_field("body_text", "**Refines**: REQ-p00002\n\n**Refines**: REQ-p00002")
        node.set_field("level", "PRD")
        node.set_field("status", "Active")
        graph._index["REQ-p00001"] = node

        check = check_spec_needs_rewrite(graph)

        assert not check.passed, "Expected check to fail with parse_dirty=True"
        assert len(check.findings) > 0, "Expected findings for parse_dirty requirement"
        finding = check.findings[0]
        assert isinstance(finding, HealthFinding)
        assert finding.node_id is not None, "Finding should have node_id"
        assert "REQ-p00001" in (finding.node_id or "")
        assert finding.message, "Finding should have a message"

    def test_REQ_d00085_I_single_refines_passes(self, tmp_path: Path) -> None:
        # Verifies: REQ-d00085-I
        """A requirement with a single distinct **Refines**: line (parse_dirty not set) passes."""
        from elspais.commands.health import check_spec_needs_rewrite

        graph = TraceGraph()
        node = GraphNode(
            id="REQ-p00002",
            kind=NodeKind.REQUIREMENT,
            label="Single Refines Requirement",
        )
        # parse_dirty is NOT set — no redundant refs were detected
        node.set_field("body_text", "**Refines**: REQ-p00001")
        node.set_field("level", "PRD")
        node.set_field("status", "Active")
        graph._index["REQ-p00002"] = node

        check = check_spec_needs_rewrite(graph)

        assert check.passed, "Expected check to pass when parse_dirty is not set"
        assert len(check.findings) == 0, "Expected no findings when parse_dirty is absent"

    def test_REQ_d00085_I_no_refines_passes(self, tmp_path: Path) -> None:
        # Verifies: REQ-d00085-I
        """A requirement with no parse_dirty should pass the check."""
        from elspais.commands.health import check_spec_needs_rewrite

        graph = TraceGraph()
        node = GraphNode(
            id="REQ-p00003",
            kind=NodeKind.REQUIREMENT,
            label="No Refines Requirement",
        )
        # parse_dirty is NOT set
        node.set_field("body_text", "This requirement has no Refines metadata.")
        node.set_field("level", "PRD")
        node.set_field("status", "Active")
        graph._index["REQ-p00003"] = node

        check = check_spec_needs_rewrite(graph)

        assert check.passed, "Expected check to pass when parse_dirty is not set"
        assert len(check.findings) == 0, "Expected no findings when parse_dirty is absent"

    def test_REQ_d00085_I_multiple_refines_without_duplicates_passes(self, tmp_path: Path) -> None:
        # Verifies: REQ-d00085-I
        """Multiple distinct **Refines**: lines (parse_dirty not set) should pass the check.

        This confirms the new behaviour: multiple Refines lines are valid as long as
        no duplicate refs were detected (parse_dirty remains unset).
        """
        from elspais.commands.health import check_spec_needs_rewrite

        graph = TraceGraph()
        node = GraphNode(
            id="REQ-p00004",
            kind=NodeKind.REQUIREMENT,
            label="Multi Refines No Duplicates",
        )
        # Two distinct Refines lines — parse_dirty is NOT set because no duplicates
        node.set_field("body_text", "**Refines**: REQ-p00001\n\n**Refines**: REQ-p00002")
        node.set_field("level", "PRD")
        node.set_field("status", "Active")
        # parse_dirty deliberately not set
        graph._index["REQ-p00004"] = node

        check = check_spec_needs_rewrite(graph)

        assert check.passed, (
            "Expected check to pass when multiple distinct Refines lines exist "
            "but parse_dirty is not set"
        )
        assert len(check.findings) == 0
