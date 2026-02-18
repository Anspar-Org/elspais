# Implements: REQ-p00080-B, REQ-p00080-C, REQ-p00080-D, REQ-p00080-E, REQ-p00080-F
"""Tests for the MarkdownAssembler.

Validates:
- REQ-p00080-B: Level grouping and graph-depth ordering
- REQ-p00080-C: TOC generation via YAML metadata
- REQ-p00080-D: Topic index generation
- REQ-p00080-E: Page breaks before requirements
- REQ-p00080-F: Overview PDF filtering
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from elspais.graph.builder import TraceGraph
from elspais.graph.GraphNode import GraphNode, NodeKind, SourceLocation
from elspais.pdf.assembler import MarkdownAssembler

# ---------------------------------------------------------------------------
# Spec file content for on-disk test fixtures
# ---------------------------------------------------------------------------

_PRD_AUTH_MD = """\
# PRD Authentication

Topics: auth, security

---

# REQ-p00001: Authentication

**Level**: PRD | **Status**: Active | **Implements**: -

## Rationale

Users need authentication.

Topics: auth, security

## Assertions

A. The tool SHALL authenticate users.

*End* *Authentication* | **Hash**: aaa11111

---
"""

_DEV_LOGIN_MD = """\
# DEV Login

---

# REQ-d00001: Login Form

**Level**: DEV | **Status**: Active

## Assertions

A. Login form SHALL validate email.

*End* *Login Form* | **Hash**: bbb22222

---
"""

_DEV_SESSION_MD = """\
# DEV Session

---

# REQ-d00002: Session Management

**Level**: DEV | **Status**: Active

*End* *Session Management* | **Hash**: ccc33333

---
"""

_OPS_DEPLOY_MD = """\
# OPS Deployment

---

# REQ-o00001: Deployment Pipeline

**Level**: OPS | **Status**: Active | **Implements**: REQ-p00001

## Assertions

A. The system SHALL deploy via CI.

*End* *Deployment Pipeline* | **Hash**: ddd44444

---
"""

_ASSOC_PRD_MD = """\
# Associated Product

---

# REQ-CAL-p00001: Callisto Auth

**Level**: PRD | **Status**: Active | **Implements**: -

## Assertions

A. The associated system SHALL authenticate.

*End* *Callisto Auth* | **Hash**: eee55555

---
"""


def _make_graph(base_dir: Path | None = None) -> TraceGraph:
    """Build a test graph with PRD and DEV requirements.

    If base_dir is provided, creates spec files on disk and sets repo_root
    so that _render_file() can read them.
    """
    graph = TraceGraph()

    if base_dir is not None:
        graph.repo_root = base_dir
        spec_dir = base_dir / "spec"
        spec_dir.mkdir(parents=True, exist_ok=True)
        (spec_dir / "prd-auth.md").write_text(_PRD_AUTH_MD, encoding="utf-8")
        (spec_dir / "dev-login.md").write_text(_DEV_LOGIN_MD, encoding="utf-8")
        (spec_dir / "dev-session.md").write_text(_DEV_SESSION_MD, encoding="utf-8")

    # PRD requirement in prd-auth.md (root, depth 0)
    prd = GraphNode(
        id="REQ-p00001",
        kind=NodeKind.REQUIREMENT,
        label="Authentication",
        source=SourceLocation(path="spec/prd-auth.md", line=7),
    )
    prd._content = {
        "level": "PRD",
        "status": "Active",
        "hash": "aaa11111",
    }
    graph._index["REQ-p00001"] = prd
    graph._roots.append(prd)

    # Assertion child of PRD
    prd_assert = GraphNode(
        id="REQ-p00001-A",
        kind=NodeKind.ASSERTION,
        label="The tool SHALL authenticate users.",
        source=SourceLocation(path="spec/prd-auth.md", line=19),
    )
    prd_assert._content = {"label": "A"}
    graph._index["REQ-p00001-A"] = prd_assert
    prd.add_child(prd_assert)

    # Rationale section child of PRD
    rationale = GraphNode(
        id="REQ-p00001:section:0",
        kind=NodeKind.REMAINDER,
        label="Rationale",
        source=SourceLocation(path="spec/prd-auth.md", line=12),
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
        source=SourceLocation(path="spec/dev-login.md", line=5),
    )
    dev._content = {
        "level": "DEV",
        "status": "Active",
        "hash": "bbb22222",
    }
    graph._index["REQ-d00001"] = dev
    prd.add_child(dev)

    # DEV assertion
    dev_assert = GraphNode(
        id="REQ-d00001-A",
        kind=NodeKind.ASSERTION,
        label="Login form SHALL validate email.",
        source=SourceLocation(path="spec/dev-login.md", line=13),
    )
    dev_assert._content = {"label": "A"}
    graph._index["REQ-d00001-A"] = dev_assert
    dev.add_child(dev_assert)

    # Second DEV requirement in dev-session.md (also depth 1)
    dev2 = GraphNode(
        id="REQ-d00002",
        kind=NodeKind.REQUIREMENT,
        label="Session Management",
        source=SourceLocation(path="spec/dev-session.md", line=5),
    )
    dev2._content = {
        "level": "DEV",
        "status": "Active",
        "hash": "ccc33333",
    }
    graph._index["REQ-d00002"] = dev2
    prd.add_child(dev2)

    return graph


def _make_overview_graph(base_dir: Path | None = None) -> TraceGraph:
    """Build a test graph with PRD, OPS, DEV, and associated-repo PRD."""
    graph = _make_graph(base_dir)

    if base_dir is not None:
        spec_dir = base_dir / "spec"
        (spec_dir / "ops-deploy.md").write_text(_OPS_DEPLOY_MD, encoding="utf-8")
        (spec_dir / "assoc-prd.md").write_text(_ASSOC_PRD_MD, encoding="utf-8")

    # OPS requirement (depth 1, child of PRD root)
    ops = GraphNode(
        id="REQ-o00001",
        kind=NodeKind.REQUIREMENT,
        label="Deployment Pipeline",
        source=SourceLocation(path="spec/ops-deploy.md", line=5),
    )
    ops._content = {"level": "OPS", "status": "Active", "hash": "ddd44444"}
    graph._index["REQ-o00001"] = ops
    prd = graph.find_by_id("REQ-p00001")
    prd.add_child(ops)

    # Associated-repo PRD (root, depth 0) — detected by PatternValidator
    assoc = GraphNode(
        id="REQ-CAL-p00001",
        kind=NodeKind.REQUIREMENT,
        label="Callisto Auth",
        source=SourceLocation(path="spec/assoc-prd.md", line=5),
    )
    assoc._content = {"level": "PRD", "status": "Active", "hash": "eee55555"}
    graph._index["REQ-CAL-p00001"] = assoc
    graph._roots.append(assoc)

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

    def test_REQ_p00080_B_level_headings_in_output(self, tmp_path):
        """Assembled output contains level group headings."""
        graph = _make_graph(base_dir=tmp_path)
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
    """Validates REQ-p00080-E: Page breaks and heading structure."""

    def test_REQ_p00080_E_page_break_before_requirement(self, tmp_path):
        """Each requirement is preceded by \\newpage."""
        graph = _make_graph(base_dir=tmp_path)
        asm = MarkdownAssembler(graph)
        output = asm.assemble()
        assert output.count("\\newpage") >= 3  # At least PRD, DEV1, DEV2

    def test_REQ_p00080_E_requirement_heading_with_anchor(self, tmp_path):
        """Requirement headings include the ID as an anchor."""
        graph = _make_graph(base_dir=tmp_path)
        asm = MarkdownAssembler(graph)
        output = asm.assemble()
        assert "### REQ-p00001: Authentication {#REQ-p00001}" in output

    def test_REQ_p00080_E_assertions_rendered(self, tmp_path):
        """Assertions appear under their parent requirement."""
        graph = _make_graph(base_dir=tmp_path)
        asm = MarkdownAssembler(graph)
        output = asm.assemble()
        assert "A. The tool SHALL authenticate users." in output

    def test_REQ_p00080_E_sections_rendered(self, tmp_path):
        """Sub-sections within requirements render at #### level."""
        graph = _make_graph(base_dir=tmp_path)
        asm = MarkdownAssembler(graph)
        output = asm.assemble()
        assert "#### Rationale" in output
        assert "Users need authentication." in output

    def test_REQ_p00080_E_file_heading_at_level_two(self, tmp_path):
        """File-level headings (before first requirement) render at ## level."""
        graph = _make_graph(base_dir=tmp_path)
        asm = MarkdownAssembler(graph)
        output = asm.assemble()
        assert "## PRD Authentication" in output

    def test_REQ_p00080_E_footer_lines_present(self, tmp_path):
        """*End* footer lines are preserved in output."""
        graph = _make_graph(base_dir=tmp_path)
        asm = MarkdownAssembler(graph)
        output = asm.assemble()
        assert "*End*" in output


class TestYAMLMetadata:
    """Validates REQ-p00080-C: YAML metadata for TOC."""

    def test_REQ_p00080_C_yaml_header_present(self, tmp_path):
        """Output starts with YAML metadata block."""
        graph = _make_graph(base_dir=tmp_path)
        asm = MarkdownAssembler(graph, title="Test Doc")
        output = asm.assemble()
        assert output.startswith("---\n")
        assert 'title: "Test Doc"' in output
        assert "toc: true" in output

    def test_REQ_p00080_C_toc_depth(self, tmp_path):
        """YAML metadata includes toc-depth."""
        graph = _make_graph(base_dir=tmp_path)
        asm = MarkdownAssembler(graph)
        output = asm.assemble()
        assert "toc-depth: 2" in output


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

    def test_REQ_p00080_D_topics_from_file(self, tmp_path):
        """Topics are extracted from pre-requirement Topics: lines in files."""
        graph = _make_graph(base_dir=tmp_path)
        asm = MarkdownAssembler(graph)
        topics = asm._topics_from_file("spec/prd-auth.md")
        assert "auth" in topics
        assert "security" in topics

    def test_REQ_p00080_D_index_rendered_with_links(self, tmp_path):
        """Topic index entries contain hyperlinks to requirements."""
        graph = _make_graph(base_dir=tmp_path)
        asm = MarkdownAssembler(graph)
        output = asm.assemble()
        assert "# Topic Index" in output
        assert "[REQ-p00001](#REQ-p00001)" in output

    def test_REQ_p00080_D_index_alphabetized(self, tmp_path):
        """Topic index is alphabetized."""
        graph = _make_graph(base_dir=tmp_path)
        asm = MarkdownAssembler(graph)
        groups = asm._group_by_file()
        index_lines = asm._build_topic_index(groups)
        topic_lines = [line for line in index_lines if line.startswith("**")]
        topics = [line.split("**")[1] for line in topic_lines]
        assert topics == sorted(topics, key=str.lower)


class TestOverviewMode:
    """Validates REQ-p00080-F: Overview PDF filtering."""

    def test_REQ_p00080_F_excludes_ops_and_dev(self, tmp_path):
        """Overview mode only includes PRD-level sections."""
        graph = _make_overview_graph(base_dir=tmp_path)
        asm = MarkdownAssembler(graph, overview=True)
        output = asm.assemble()
        assert "# Product Requirements" in output
        assert "# Operational Requirements" not in output
        assert "# Development Requirements" not in output

    def test_REQ_p00080_F_includes_associated_prd(self, tmp_path):
        """Overview mode includes PRD from associated repos."""
        graph = _make_overview_graph(base_dir=tmp_path)
        asm = MarkdownAssembler(graph, overview=True)
        output = asm.assemble()
        assert "Callisto Auth" in output

    def test_REQ_p00080_F_max_depth_filters_core(self, tmp_path):
        """max_depth limits core PRD files by graph depth."""
        graph = _make_overview_graph(base_dir=tmp_path)
        # Add a depth-1 core PRD to test filtering
        prd2 = GraphNode(
            id="REQ-p00002",
            kind=NodeKind.REQUIREMENT,
            label="Child PRD",
            source=SourceLocation(path="spec/prd-auth.md", line=50),
        )
        prd2._content = {"level": "PRD", "status": "Active"}
        graph._index["REQ-p00002"] = prd2
        prd = graph.find_by_id("REQ-p00001")
        prd.add_child(prd2)

        # max_depth=1 means only depth 0
        asm = MarkdownAssembler(graph, overview=True, max_depth=1)
        output = asm.assemble()
        # Root PRD (depth 0) included
        assert "Authentication" in output
        # Associated PRD included (no depth limit on associates)
        assert "Callisto Auth" in output

    def test_REQ_p00080_F_default_title(self, tmp_path):
        """Overview mode uses 'Product Requirements Overview' as default title."""
        graph = _make_overview_graph(base_dir=tmp_path)
        asm = MarkdownAssembler(graph, overview=True)
        output = asm.assemble()
        assert 'title: "Product Requirements Overview"' in output

    def test_REQ_p00080_F_custom_title_overrides(self, tmp_path):
        """Explicit title overrides the overview default."""
        graph = _make_overview_graph(base_dir=tmp_path)
        asm = MarkdownAssembler(graph, title="My Custom", overview=True)
        output = asm.assemble()
        assert 'title: "My Custom"' in output

    def test_REQ_p00080_F_non_overview_unchanged(self, tmp_path):
        """Without overview flag, all levels still appear."""
        graph = _make_overview_graph(base_dir=tmp_path)
        asm = MarkdownAssembler(graph)
        output = asm.assemble()
        assert "# Product Requirements" in output
        assert "# Operational Requirements" in output
        assert "# Development Requirements" in output
