# Implements: REQ-p00080-B, REQ-p00080-C, REQ-p00080-D, REQ-p00080-E
"""Tests for the MarkdownAssembler.

Validates:
- REQ-p00080-B: Level grouping and graph-depth ordering
- REQ-p00080-C: TOC generation via YAML metadata
- REQ-p00080-D: Topic index generation
- REQ-p00080-E: Page breaks before requirements
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from elspais.graph.builder import TraceGraph
from elspais.graph.GraphNode import GraphNode, NodeKind, SourceLocation
from elspais.pdf.assembler import MarkdownAssembler


def _make_graph() -> TraceGraph:
    """Build a test graph with PRD and DEV requirements."""
    graph = TraceGraph()

    # PRD requirement in prd-auth.md (root, depth 0)
    prd = GraphNode(
        id="REQ-p00001",
        kind=NodeKind.REQUIREMENT,
        label="Authentication",
        source=SourceLocation(path="spec/prd-auth.md", line=1),
    )
    prd._content = {"level": "PRD", "status": "Active", "hash": "aaa11111", "body_text": ""}
    graph._index["REQ-p00001"] = prd
    graph._roots.append(prd)

    # Assertion child of PRD
    prd_assert = GraphNode(
        id="REQ-p00001-A",
        kind=NodeKind.ASSERTION,
        label="The tool SHALL authenticate users.",
        source=SourceLocation(path="spec/prd-auth.md", line=10),
    )
    prd_assert._content = {"label": "A"}
    graph._index["REQ-p00001-A"] = prd_assert
    prd.add_child(prd_assert)

    # Rationale section child of PRD
    rationale = GraphNode(
        id="REQ-p00001:section:0",
        kind=NodeKind.REMAINDER,
        label="Rationale",
        source=SourceLocation(path="spec/prd-auth.md", line=5),
    )
    rationale._content = {
        "heading": "Rationale",
        "text": "Users need authentication.\n\nTopics: auth, security",
        "order": 0,
    }
    graph._index["REQ-p00001:section:0"] = rationale
    prd.add_child(rationale)

    # DEV requirement in dev-login.md (child of PRD, depth 1)
    dev = GraphNode(
        id="REQ-d00001",
        kind=NodeKind.REQUIREMENT,
        label="Login Form",
        source=SourceLocation(path="spec/dev-login.md", line=1),
    )
    dev._content = {"level": "DEV", "status": "Active", "hash": "bbb22222", "body_text": ""}
    graph._index["REQ-d00001"] = dev
    prd.add_child(dev)

    # DEV assertion
    dev_assert = GraphNode(
        id="REQ-d00001-A",
        kind=NodeKind.ASSERTION,
        label="Login form SHALL validate email.",
        source=SourceLocation(path="spec/dev-login.md", line=10),
    )
    dev_assert._content = {"label": "A"}
    graph._index["REQ-d00001-A"] = dev_assert
    dev.add_child(dev_assert)

    # Second DEV requirement in dev-session.md (also depth 1)
    dev2 = GraphNode(
        id="REQ-d00002",
        kind=NodeKind.REQUIREMENT,
        label="Session Management",
        source=SourceLocation(path="spec/dev-session.md", line=1),
    )
    dev2._content = {"level": "DEV", "status": "Active", "hash": "ccc33333", "body_text": ""}
    graph._index["REQ-d00002"] = dev2
    prd.add_child(dev2)

    return graph


class TestFileGrouping:
    """Validates REQ-p00080-B: File grouping."""

    def test_REQ_p00080_B_groups_by_source_path(self):
        """Requirements from different files appear in different groups."""
        graph = _make_graph()
        asm = MarkdownAssembler(graph)
        groups = asm._group_by_file()
        assert "spec/prd-auth.md" in groups
        assert "spec/dev-login.md" in groups
        assert "spec/dev-session.md" in groups

    def test_REQ_p00080_B_document_order_within_file(self):
        """Requirements within a file are ordered by source line."""
        graph = _make_graph()
        # Add second req to same file with higher line
        node2 = GraphNode(
            id="REQ-p00002",
            kind=NodeKind.REQUIREMENT,
            label="Second PRD",
            source=SourceLocation(path="spec/prd-auth.md", line=50),
        )
        node2._content = {"level": "PRD", "status": "Active"}
        graph._index["REQ-p00002"] = node2
        asm = MarkdownAssembler(graph)
        groups = asm._group_by_file()
        nodes = groups["spec/prd-auth.md"]
        assert nodes[0].id == "REQ-p00001"
        assert nodes[1].id == "REQ-p00002"


class TestLevelPartitioning:
    """Validates REQ-p00080-B: Level partitioning."""

    def test_REQ_p00080_B_partitions_by_level(self):
        """Files are partitioned into PRD, OPS, DEV buckets."""
        graph = _make_graph()
        asm = MarkdownAssembler(graph)
        groups = asm._group_by_file()
        buckets = asm._partition_by_level(groups)
        assert "spec/prd-auth.md" in buckets.get("PRD", [])
        assert "spec/dev-login.md" in buckets.get("DEV", [])
        assert "spec/dev-session.md" in buckets.get("DEV", [])

    def test_REQ_p00080_B_level_headings_in_output(self):
        """Assembled output contains level group headings."""
        graph = _make_graph()
        asm = MarkdownAssembler(graph)
        output = asm.assemble()
        assert "# Product Requirements" in output
        assert "# Development Requirements" in output


class TestGraphDepthOrdering:
    """Validates REQ-p00080-B: Graph-depth ordering."""

    def test_REQ_p00080_B_root_depth_is_zero(self):
        """Root nodes have depth 0."""
        graph = _make_graph()
        prd = graph.find_by_id("REQ-p00001")
        assert MarkdownAssembler._node_depth(prd) == 0

    def test_REQ_p00080_B_child_depth_is_one(self):
        """Direct children of root have depth 1."""
        graph = _make_graph()
        dev = graph.find_by_id("REQ-d00001")
        assert MarkdownAssembler._node_depth(dev) == 1

    def test_REQ_p00080_B_files_sorted_by_depth(self):
        """Files within a level group are sorted by min graph depth."""
        graph = _make_graph()
        asm = MarkdownAssembler(graph)
        groups = asm._group_by_file()
        dev_files = ["spec/dev-login.md", "spec/dev-session.md"]
        sorted_files = asm._sort_files_by_depth(dev_files, groups)
        # Both are depth 1, so alphabetical tiebreaker
        assert sorted_files == ["spec/dev-login.md", "spec/dev-session.md"]


class TestRequirementRendering:
    """Validates REQ-p00080-E: Page breaks before requirements."""

    def test_REQ_p00080_E_page_break_before_requirement(self):
        """Each requirement is preceded by \\newpage."""
        graph = _make_graph()
        asm = MarkdownAssembler(graph)
        output = asm.assemble()
        # Count newpage directives - should be one per requirement
        assert output.count("\\newpage") >= 3  # At least PRD, DEV1, DEV2

    def test_REQ_p00080_E_requirement_heading_with_anchor(self):
        """Requirement headings include the ID as an anchor."""
        graph = _make_graph()
        asm = MarkdownAssembler(graph)
        output = asm.assemble()
        assert "### REQ-p00001: Authentication {#REQ-p00001}" in output

    def test_REQ_p00080_E_assertions_rendered(self):
        """Assertions appear under their parent requirement."""
        graph = _make_graph()
        asm = MarkdownAssembler(graph)
        output = asm.assemble()
        assert "A. The tool SHALL authenticate users." in output

    def test_REQ_p00080_E_sections_rendered(self):
        """REMAINDER sections appear with their headings."""
        graph = _make_graph()
        asm = MarkdownAssembler(graph)
        output = asm.assemble()
        assert "#### Rationale" in output
        assert "Users need authentication." in output


class TestYAMLMetadata:
    """Validates REQ-p00080-C: YAML metadata for TOC."""

    def test_REQ_p00080_C_yaml_header_present(self):
        """Output starts with YAML metadata block."""
        graph = _make_graph()
        asm = MarkdownAssembler(graph, title="Test Doc")
        output = asm.assemble()
        assert output.startswith("---\n")
        assert 'title: "Test Doc"' in output
        assert "toc: true" in output

    def test_REQ_p00080_C_toc_depth(self):
        """YAML metadata includes toc-depth."""
        graph = _make_graph()
        asm = MarkdownAssembler(graph)
        output = asm.assemble()
        assert "toc-depth: 3" in output


class TestTopicIndex:
    """Validates REQ-p00080-D: Topic index generation."""

    def test_REQ_p00080_D_topics_from_filename(self):
        """Topics are extracted from filenames stripping level prefix."""
        topics = MarkdownAssembler._topics_from_filename("spec/prd-pdf-generation.md")
        assert topics == ["pdf", "generation"]

    def test_REQ_p00080_D_topics_from_filename_numeric(self):
        """Numeric prefixes are stripped."""
        topics = MarkdownAssembler._topics_from_filename("spec/07-graph-architecture.md")
        assert topics == ["graph", "architecture"]

    def test_REQ_p00080_D_topics_from_remainder(self):
        """Topics are extracted from REMAINDER nodes with Topics: line."""
        graph = _make_graph()
        asm = MarkdownAssembler(graph)
        prd = graph.find_by_id("REQ-p00001")
        topics = asm._topics_from_requirement_remainders(prd)
        assert "auth" in topics
        assert "security" in topics

    def test_REQ_p00080_D_index_rendered_with_links(self):
        """Topic index entries contain hyperlinks to requirements."""
        graph = _make_graph()
        asm = MarkdownAssembler(graph)
        output = asm.assemble()
        assert "# Topic Index" in output
        # Check for hyperlink format
        assert "[REQ-p00001](#REQ-p00001)" in output

    def test_REQ_p00080_D_index_alphabetized(self):
        """Topic index is alphabetized."""
        graph = _make_graph()
        asm = MarkdownAssembler(graph)
        groups = asm._group_by_file()
        index_lines = asm._build_topic_index(groups)
        # Filter to topic lines only (bold entries)
        topic_lines = [line for line in index_lines if line.startswith("**")]
        topics = [line.split("**")[1] for line in topic_lines]
        assert topics == sorted(topics, key=str.lower)
