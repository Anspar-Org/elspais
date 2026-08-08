# Verifies: REQ-p00080-B, REQ-p00080-C, REQ-p00080-D, REQ-p00080-E, REQ-p00080-F
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
from elspais.graph.federated import FederatedGraph
from elspais.graph.GraphNode import GraphNode, NodeKind
from elspais.graph.relations import EdgeKind
from elspais.pdf.assembler import MarkdownAssembler


def _wrap(graph: TraceGraph) -> FederatedGraph:
    """Wrap a bare ``TraceGraph`` as a federation-of-one for the assembler.

    The assembler reads ``self._graph.root_repo_name`` (no fallback) so
    every test must hand it a ``FederatedGraph``. We pass a minimal
    config with ``[project].name`` populated so ``from_single`` doesn't
    raise.
    """
    return FederatedGraph.from_single(
        graph, {"project": {"name": "test", "namespace": "REQ"}}, graph.repo_root
    )


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

_PRD_CHILD_MD = """\
# PRD Child Feature

Topics: child-feature

---

# REQ-p00002: Child Feature

**Level**: PRD | **Status**: Active | **Implements**: REQ-p00001

## Assertions

A. The system SHALL provide a child feature.

*End* *Child Feature* | **Hash**: fff66666

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

    from tests.core.graph_test_helpers import wire_file_parent

    # PRD requirement in prd-auth.md (root, depth 0)
    prd = GraphNode(
        id="REQ-p00001",
        kind=NodeKind.REQUIREMENT,
        label="Authentication",
    )
    prd._content = {
        "level": "PRD",
        "status": "Active",
        "hash": "aaa11111",
        "parse_line": 7,
        "parse_end_line": None,
    }
    wire_file_parent(prd, "spec/prd-auth.md", line=7, graph=graph)
    graph._index["REQ-p00001"] = prd
    graph._roots.append(prd)

    # Assertion child of PRD
    prd_assert = GraphNode(
        id="REQ-p00001-A",
        kind=NodeKind.ASSERTION,
        label="The tool SHALL authenticate users.",
    )
    prd_assert._content = {"label": "A", "parse_line": 19, "parse_end_line": None}
    graph._index["REQ-p00001-A"] = prd_assert
    prd.link(prd_assert, EdgeKind.STRUCTURES)

    # Rationale section child of PRD
    rationale = GraphNode(
        id="REQ-p00001:section:0",
        kind=NodeKind.REMAINDER,
        label="Rationale",
    )
    rationale._content = {
        "heading": "Rationale",
        "text": "Users need authentication.\n\nTopics: auth, security",
        "order": 0,
    }
    graph._index["REQ-p00001:section:0"] = rationale
    prd.link(rationale, EdgeKind.STRUCTURES)

    # DEV requirement in dev-login.md (child of PRD, depth 1)
    dev = GraphNode(
        id="REQ-d00001",
        kind=NodeKind.REQUIREMENT,
        label="Login Form",
    )
    dev._content = {
        "level": "DEV",
        "status": "Active",
        "hash": "bbb22222",
        "parse_line": 5,
        "parse_end_line": None,
    }
    wire_file_parent(dev, "spec/dev-login.md", line=5, graph=graph)
    graph._index["REQ-d00001"] = dev
    prd.link(dev, EdgeKind.STRUCTURES)

    # DEV assertion
    dev_assert = GraphNode(
        id="REQ-d00001-A",
        kind=NodeKind.ASSERTION,
        label="Login form SHALL validate email.",
    )
    dev_assert._content = {"label": "A", "parse_line": 13, "parse_end_line": None}
    graph._index["REQ-d00001-A"] = dev_assert
    dev.link(dev_assert, EdgeKind.STRUCTURES)

    # Second DEV requirement in dev-session.md (also depth 1)
    dev2 = GraphNode(
        id="REQ-d00002",
        kind=NodeKind.REQUIREMENT,
        label="Session Management",
    )
    dev2._content = {
        "level": "DEV",
        "status": "Active",
        "hash": "ccc33333",
        "parse_line": 5,
        "parse_end_line": None,
    }
    wire_file_parent(dev2, "spec/dev-session.md", line=5, graph=graph)
    graph._index["REQ-d00002"] = dev2
    prd.link(dev2, EdgeKind.STRUCTURES)

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
    )
    from tests.core.graph_test_helpers import wire_file_parent

    ops._content = {
        "level": "OPS",
        "status": "Active",
        "hash": "ddd44444",
        "parse_line": 5,
        "parse_end_line": None,
    }
    wire_file_parent(ops, "spec/ops-deploy.md", line=5, graph=graph)
    graph._index["REQ-o00001"] = ops
    prd = graph.find_by_id("REQ-p00001")
    prd.link(ops, EdgeKind.STRUCTURES)

    # Associated-repo PRD (root, depth 0) — detected by namespace pattern
    assoc = GraphNode(
        id="REQ-CAL-p00001",
        kind=NodeKind.REQUIREMENT,
        label="Callisto Auth",
    )
    assoc._content = {
        "level": "PRD",
        "status": "Active",
        "hash": "eee55555",
        "parse_line": 5,
        "parse_end_line": None,
    }
    wire_file_parent(assoc, "spec/assoc-prd.md", line=5, graph=graph)
    graph._index["REQ-CAL-p00001"] = assoc
    graph._roots.append(assoc)

    return graph


class TestFileGrouping:
    """Validates REQ-p00080-B: File grouping."""

    def test_REQ_p00080_B_groups_by_source_path(self):
        """Requirements from different files appear in different groups."""
        graph = _make_graph()
        asm = MarkdownAssembler(_wrap(graph))
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
        )
        from tests.core.graph_test_helpers import wire_file_parent

        node2._content = {
            "level": "PRD",
            "status": "Active",
            "parse_line": 50,
            "parse_end_line": None,
        }
        wire_file_parent(node2, "spec/prd-auth.md", line=50, graph=graph)
        graph._index["REQ-p00002"] = node2
        asm = MarkdownAssembler(_wrap(graph))
        groups = asm._group_by_file()
        nodes = groups["spec/prd-auth.md"]
        assert nodes[0].id == "REQ-p00001"
        assert nodes[1].id == "REQ-p00002"


class TestLevelPartitioning:
    """Validates REQ-p00080-B: Level partitioning."""

    def test_REQ_p00080_B_partitions_by_level(self):
        """Files are partitioned into PRD, OPS, DEV buckets."""
        graph = _make_graph()
        asm = MarkdownAssembler(_wrap(graph))
        groups = asm._group_by_file()
        buckets = asm._partition_by_level(groups)
        assert "spec/prd-auth.md" in buckets.get("PRD", [])
        assert "spec/dev-login.md" in buckets.get("DEV", [])
        assert "spec/dev-session.md" in buckets.get("DEV", [])

    def test_REQ_p00080_B_level_headings_in_output(self, tmp_path):
        """Assembled output contains level group headings."""
        graph = _make_graph(base_dir=tmp_path)
        asm = MarkdownAssembler(_wrap(graph))
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
        asm = MarkdownAssembler(_wrap(graph))
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
        asm = MarkdownAssembler(_wrap(graph))
        output = asm.assemble()
        assert output.count("\\newpage") >= 3  # At least PRD, DEV1, DEV2

    def test_REQ_p00080_E_requirement_heading_with_anchor(self, tmp_path):
        """Requirement headings include the ID as an anchor."""
        graph = _make_graph(base_dir=tmp_path)
        asm = MarkdownAssembler(_wrap(graph))
        output = asm.assemble()
        assert "### REQ-p00001: Authentication {#REQ-p00001}" in output

    def test_REQ_p00080_E_assertions_rendered(self, tmp_path):
        """Assertions appear under their parent requirement."""
        graph = _make_graph(base_dir=tmp_path)
        asm = MarkdownAssembler(_wrap(graph))
        output = asm.assemble()
        assert "A. The tool SHALL authenticate users." in output

    def test_REQ_p00080_E_sections_rendered(self, tmp_path):
        """Sub-sections within requirements render at #### level."""
        graph = _make_graph(base_dir=tmp_path)
        asm = MarkdownAssembler(_wrap(graph))
        output = asm.assemble()
        assert "#### Rationale" in output
        assert "Users need authentication." in output

    def test_REQ_p00080_E_file_heading_at_level_two(self, tmp_path):
        """File-level headings (before first requirement) render at ## level."""
        graph = _make_graph(base_dir=tmp_path)
        asm = MarkdownAssembler(_wrap(graph))
        output = asm.assemble()
        assert "## PRD Authentication" in output

    def test_REQ_p00080_E_footer_lines_present(self, tmp_path):
        """*End* footer lines are preserved in output."""
        graph = _make_graph(base_dir=tmp_path)
        asm = MarkdownAssembler(_wrap(graph))
        output = asm.assemble()
        assert "*End*" in output


class TestYAMLMetadata:
    """Validates REQ-p00080-C: YAML metadata for TOC."""

    def test_REQ_p00080_C_yaml_header_present(self, tmp_path):
        """Output starts with YAML metadata block."""
        graph = _make_graph(base_dir=tmp_path)
        asm = MarkdownAssembler(_wrap(graph), title="Test Doc")
        output = asm.assemble()
        assert output.startswith("---\n")
        assert 'title: "Test Doc"' in output
        assert "toc: true" in output

    def test_REQ_p00080_C_toc_depth(self, tmp_path):
        """YAML metadata includes toc-depth."""
        graph = _make_graph(base_dir=tmp_path)
        asm = MarkdownAssembler(_wrap(graph))
        output = asm.assemble()
        assert "toc-depth: 2" in output


class TestTopicIndex:
    """Validates REQ-p00080-D: Topic index generation."""

    def test_REQ_p00080_D_topics_from_filename(self):
        """Topics are extracted from filenames stripping level prefix."""
        asm = MarkdownAssembler(_wrap(_make_graph()))
        topics = asm._topics_from_filename("spec/prd-pdf-generation.md")
        assert topics == ["pdf", "generation"]

    def test_REQ_p00080_D_topics_from_filename_numeric(self):
        """Numeric prefixes are stripped."""
        asm = MarkdownAssembler(_wrap(_make_graph()))
        topics = asm._topics_from_filename("spec/07-graph-architecture.md")
        assert topics == ["graph", "architecture"]

    def test_REQ_p00080_D_topics_from_remainder(self):
        """Topics are extracted from REMAINDER nodes with Topics: line."""
        graph = _make_graph()
        asm = MarkdownAssembler(_wrap(graph))
        prd = graph.find_by_id("REQ-p00001")
        topics = asm._topics_from_requirement_remainders(prd)
        assert "auth" in topics
        assert "security" in topics

    def test_REQ_p00080_D_topics_from_file(self, tmp_path):
        """Topics are extracted from pre-requirement Topics: lines in files."""
        graph = _make_graph(base_dir=tmp_path)
        asm = MarkdownAssembler(_wrap(graph))
        topics = asm._topics_from_file("spec/prd-auth.md")
        assert "auth" in topics
        assert "security" in topics

    def test_REQ_p00080_D_index_rendered_with_links(self, tmp_path):
        """Topic index entries contain hyperlinks to requirements."""
        graph = _make_graph(base_dir=tmp_path)
        asm = MarkdownAssembler(_wrap(graph))
        output = asm.assemble()
        assert "# Topic Index" in output
        assert "[REQ-p00001](#REQ-p00001)" in output

    def test_REQ_p00080_D_index_alphabetized(self, tmp_path):
        """Topic index is alphabetized."""
        graph = _make_graph(base_dir=tmp_path)
        asm = MarkdownAssembler(_wrap(graph))
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
        asm = MarkdownAssembler(_wrap(graph), overview=True)
        output = asm.assemble()
        assert "# Product Requirements" in output
        assert "# Operations Requirements" not in output
        assert "# Development Requirements" not in output

    def test_REQ_p00080_F_includes_associated_prd(self, tmp_path):
        """Overview mode includes PRD from associated repos."""
        graph = _make_overview_graph(base_dir=tmp_path)
        asm = MarkdownAssembler(_wrap(graph), overview=True)
        output = asm.assemble()
        assert "Callisto Auth" in output

    def test_REQ_p00080_F_max_depth_filters_core(self, tmp_path):
        """max_depth excludes core PRD files whose min depth >= threshold."""
        graph = _make_overview_graph(base_dir=tmp_path)
        # Add a depth-1 core PRD in a separate file
        spec_dir = tmp_path / "spec"
        (spec_dir / "prd-child.md").write_text(_PRD_CHILD_MD, encoding="utf-8")
        prd2 = GraphNode(
            id="REQ-p00002",
            kind=NodeKind.REQUIREMENT,
            label="Child Feature",
        )
        from tests.core.graph_test_helpers import wire_file_parent

        prd2._content = {
            "level": "PRD",
            "status": "Active",
            "hash": "fff66666",
            "parse_line": 7,
            "parse_end_line": None,
        }
        wire_file_parent(prd2, "spec/prd-child.md", line=7, graph=graph)
        graph._index["REQ-p00002"] = prd2
        prd = graph.find_by_id("REQ-p00001")
        prd.link(prd2, EdgeKind.STRUCTURES)

        # max_depth=1 means only depth 0
        asm = MarkdownAssembler(_wrap(graph), overview=True, max_depth=1)
        output = asm.assemble()
        # Root PRD (depth 0) included
        assert "Authentication" in output
        # Depth-1 core PRD in separate file excluded
        assert "Child Feature" not in output
        # Associated PRD included (no depth limit on associates)
        assert "Callisto Auth" in output

    def test_REQ_p00080_F_default_title(self, tmp_path):
        """Overview mode uses 'Product Requirements Overview' as default title."""
        graph = _make_overview_graph(base_dir=tmp_path)
        asm = MarkdownAssembler(_wrap(graph), overview=True)
        output = asm.assemble()
        assert 'title: "Product Requirements Overview"' in output

    def test_REQ_p00080_F_custom_title_overrides(self, tmp_path):
        """Explicit title overrides the overview default."""
        graph = _make_overview_graph(base_dir=tmp_path)
        asm = MarkdownAssembler(_wrap(graph), title="My Custom", overview=True)
        output = asm.assemble()
        assert 'title: "My Custom"' in output

    def test_REQ_p00080_F_topic_index_excludes_non_prd(self, tmp_path):
        """Topic index in overview mode only references rendered PRD files."""
        graph = _make_overview_graph(base_dir=tmp_path)
        asm = MarkdownAssembler(_wrap(graph), overview=True)
        output = asm.assemble()
        # Topic index should not reference OPS or DEV requirements
        assert "REQ-o00001" not in output
        assert "REQ-d00001" not in output
        assert "REQ-d00002" not in output

    def test_REQ_p00080_F_non_overview_unchanged(self, tmp_path):
        """Without overview flag, all levels still appear."""
        graph = _make_overview_graph(base_dir=tmp_path)
        asm = MarkdownAssembler(_wrap(graph))
        output = asm.assemble()
        assert "# Product Requirements" in output
        assert "# Operations Requirements" in output
        assert "# Development Requirements" in output


# ---------------------------------------------------------------------------
# Cross-repo (federated) spec content for Phase 3
# ---------------------------------------------------------------------------

_ROOT_PRD_MD = """\
# PRD Root Product

Topics: root-topic

---

# REQ-p00001: Root Product Vision

**Level**: PRD | **Status**: Active | **Implements**: -

## Assertions

A. The root product SHALL define top-level goals.

*End* *Root Product Vision* | **Hash**: 11111111

---
"""

_ASSOC_PRD_FED_MD = """\
# Associate Product Spec

Topics: associate-topic

---

# REQ-p00099: Associate Capability

**Level**: PRD | **Status**: Active | **Implements**: -

## Assertions

A. The associate component SHALL expose a federation hook.

*End* *Associate Capability* | **Hash**: 99999999

---
"""


def _make_federated_overview_graph(tmp_path: Path):
    """Build a two-repo FederatedGraph with root + associate PRDs on disk.

    Returns:
        Tuple of (FederatedGraph, root_dir, assoc_dir) for assertion convenience.
    """
    from elspais.graph.federated import FederatedGraph, RepoEntry
    from tests.core.graph_test_helpers import wire_file_parent

    # --- Root repo on disk ---
    root_dir = tmp_path / "root"
    (root_dir / "spec").mkdir(parents=True)
    (root_dir / "spec" / "prd-root.md").write_text(_ROOT_PRD_MD, encoding="utf-8")

    root_graph = TraceGraph(repo_root=root_dir)
    root_req = GraphNode(
        id="REQ-p00001",
        kind=NodeKind.REQUIREMENT,
        label="Root Product Vision",
    )
    root_req._content = {
        "level": "PRD",
        "status": "Active",
        "hash": "11111111",
        "parse_line": 7,
        "parse_end_line": None,
    }
    wire_file_parent(root_req, "spec/prd-root.md", line=7, graph=root_graph)
    root_graph._index["REQ-p00001"] = root_req
    root_graph._roots.append(root_req)

    root_assert = GraphNode(
        id="REQ-p00001-A",
        kind=NodeKind.ASSERTION,
        label="The root product SHALL define top-level goals.",
    )
    root_assert._content = {"label": "A", "parse_line": 13, "parse_end_line": None}
    root_graph._index["REQ-p00001-A"] = root_assert
    root_req.link(root_assert, EdgeKind.STRUCTURES)

    # --- Associate repo on disk ---
    assoc_dir = tmp_path / "assoc"
    (assoc_dir / "spec").mkdir(parents=True)
    (assoc_dir / "spec" / "prd-assoc.md").write_text(_ASSOC_PRD_FED_MD, encoding="utf-8")

    assoc_graph = TraceGraph(repo_root=assoc_dir)
    assoc_req = GraphNode(
        id="REQ-p00099",
        kind=NodeKind.REQUIREMENT,
        label="Associate Capability",
    )
    assoc_req._content = {
        "level": "PRD",
        "status": "Active",
        "hash": "99999999",
        "parse_line": 7,
        "parse_end_line": None,
    }
    wire_file_parent(assoc_req, "spec/prd-assoc.md", line=7, graph=assoc_graph)
    assoc_graph._index["REQ-p00099"] = assoc_req
    assoc_graph._roots.append(assoc_req)

    assoc_assert = GraphNode(
        id="REQ-p00099-A",
        kind=NodeKind.ASSERTION,
        label="The associate component SHALL expose a federation hook.",
    )
    assoc_assert._content = {"label": "A", "parse_line": 13, "parse_end_line": None}
    assoc_graph._index["REQ-p00099-A"] = assoc_assert
    assoc_req.link(assoc_assert, EdgeKind.STRUCTURES)

    # --- Federate ---
    root_entry = RepoEntry(name="root", graph=root_graph, config={}, repo_root=root_dir)
    assoc_entry = RepoEntry(name="assoc", graph=assoc_graph, config={}, repo_root=assoc_dir)
    fed = FederatedGraph([root_entry, assoc_entry], root_repo="root")
    return fed, root_dir, assoc_dir


class TestCrossRepoRendering:
    """Validates Phase 3: PDF cross-repo content rendering + Topic Index annotation.

    Verifies that when a PDF is assembled from a FederatedGraph with associate
    repos, the associate spec content is read from the associate's on-disk
    location (REQ-p00080-C) and Topic Index entries for associate requirements
    carry a [repo_name] prefix (REQ-p00080-D).
    """

    # Verifies: REQ-p00080-C
    def test_REQ_p00080_C_assemble_embeds_associate_content(self, tmp_path):
        """assemble() reads and emits the associate file body, not just root."""
        fed, _root_dir, _assoc_dir = _make_federated_overview_graph(tmp_path)
        asm = MarkdownAssembler(fed)
        output = asm.assemble()

        # The associate file's heading and assertion text must appear in
        # the assembled document. Before Phase 3 these were silently
        # dropped because _resolve_path only searched the root repo.
        assert "Associate Capability" in output
        assert "The associate component SHALL expose a federation hook." in output
        # The root content is still present.
        assert "Root Product Vision" in output

    # Verifies: REQ-p00080-C
    def test_REQ_p00080_C_resolve_path_returns_associate_path(self, tmp_path):
        """_resolve_path honours owning_repo_root when supplied."""
        fed, _root_dir, assoc_dir = _make_federated_overview_graph(tmp_path)
        asm = MarkdownAssembler(fed)

        resolved = asm._resolve_path("spec/prd-assoc.md", owning_repo_root=assoc_dir)
        assert resolved is not None
        assert resolved == assoc_dir / "spec" / "prd-assoc.md"
        assert resolved.exists()

    # Verifies: REQ-p00080-C
    def test_REQ_p00080_C_resolve_path_iter_repos_fallback(self, tmp_path):
        """_resolve_path falls back via iter_repos() when no owner is given.

        Cross-repo files must still resolve for callers that did not pass
        an explicit ``owning_repo_root`` (e.g. preamble-style global text).
        """
        fed, _root_dir, assoc_dir = _make_federated_overview_graph(tmp_path)
        asm = MarkdownAssembler(fed)

        # No owning_repo_root, file is not in root repo — must be found
        # by iterating federated repos.
        resolved = asm._resolve_path("spec/prd-assoc.md")
        assert resolved is not None
        assert resolved == assoc_dir / "spec" / "prd-assoc.md"
        assert resolved.exists()

    # Verifies: REQ-p00080-D
    def test_REQ_p00080_D_topic_index_prefixes_associate_entries(self, tmp_path):
        """Topic Index annotates associate refs with [<repo_name>] prefix."""
        fed, _root_dir, _assoc_dir = _make_federated_overview_graph(tmp_path)
        asm = MarkdownAssembler(fed)
        output = asm.assemble()

        # Locate the Topic Index section.
        assert "# Topic Index" in output
        index_start = output.index("# Topic Index")
        index_section = output[index_start:]

        # Associate requirement must carry [assoc] prefix.
        assert "[assoc] [REQ-p00099](#REQ-p00099)" in index_section
        # Root requirement must NOT carry a [root] prefix (it appears bare).
        assert "[root] [REQ-p00001]" not in index_section
        assert "[REQ-p00001](#REQ-p00001)" in index_section

    # Verifies: REQ-p00080-C
    def test_REQ_p00080_C_render_file_with_owning_root_emits_content(self, tmp_path):
        """_render_file with owning_repo_root reads the associate file body."""
        fed, _root_dir, assoc_dir = _make_federated_overview_graph(tmp_path)
        asm = MarkdownAssembler(fed)

        lines = asm._render_file("spec/prd-assoc.md", owning_repo_root=assoc_dir)
        # Non-empty — file was located and read.
        assert lines, "expected non-empty render for associate file"
        joined = "\n".join(lines)
        # File heading rendered as ## section heading.
        assert "## Associate Product Spec" in joined
        # Requirement heading rendered as ### with anchor.
        assert "### REQ-p00099: Associate Capability {#REQ-p00099}" in joined
        # Assertion body preserved.
        assert "The associate component SHALL expose a federation hook." in joined


# ---------------------------------------------------------------------------
# Image path resolution (TOOL-31 / TOOL-32)
# ---------------------------------------------------------------------------


def _image_asm(tmp_path: Path) -> tuple[MarkdownAssembler, Path]:
    """Assembler over an on-disk single-repo root for image-path tests."""
    root_dir = tmp_path / "root"
    root_dir.mkdir(parents=True, exist_ok=True)
    graph = TraceGraph(repo_root=root_dir)
    return MarkdownAssembler(_wrap(graph)), root_dir


class TestImagePathResolution:
    """Validates REQ-p00080-H: relative image refs survive the /tmp pandoc hop.

    render_pdf() writes assembled markdown to a temp file in /tmp/, so any
    image reference left relative resolves to nothing and the image is
    silently dropped from the PDF (TOOL-31). The assembler must rewrite
    relative raster/vector refs to absolute paths anchored at the source
    file's directory in the file's owning repo.
    """

    # Verifies: REQ-p00080-H
    def test_REQ_p00080_H_relative_image_resolved_against_source_dir(self, tmp_path):
        """A ref relative to a spec subdirectory becomes absolute."""
        asm, root = _image_asm(tmp_path)
        (root / "spec" / "sub" / "images").mkdir(parents=True)
        img = root / "spec" / "sub" / "images" / "a.png"
        img.write_bytes(b"\x89PNG")
        (root / "spec" / "sub" / "x.md").write_text(
            "# Sub Spec\n\n![diagram](images/a.png)\n", encoding="utf-8"
        )

        joined = "\n".join(asm._render_file("spec/sub/x.md"))
        assert f"![diagram]({img.resolve()})" in joined
        assert "![diagram](images/a.png)" not in joined

    # Verifies: REQ-p00080-H
    def test_REQ_p00080_H_parent_relative_image_resolved(self, tmp_path):
        """A ../docs/... ref (the TOOL-31 repro) resolves to the repo's docs tree."""
        asm, root = _image_asm(tmp_path)
        (root / "spec").mkdir()
        (root / "docs" / "urs-extracted-images").mkdir(parents=True)
        img = root / "docs" / "urs-extracted-images" / "image-01.png"
        img.write_bytes(b"\x89PNG")
        (root / "spec" / "prd-x.md").write_text(
            "# X\n\n![shot](../docs/urs-extracted-images/image-01.png)\n",
            encoding="utf-8",
        )

        joined = "\n".join(asm._render_file("spec/prd-x.md"))
        assert f"![shot]({img.resolve()})" in joined

    # Verifies: REQ-p00080-H
    def test_REQ_p00080_H_image_title_preserved(self, tmp_path):
        """An optional quoted title survives the rewrite."""
        asm, root = _image_asm(tmp_path)
        (root / "spec").mkdir()
        img = root / "spec" / "b.jpg"
        img.write_bytes(b"\xff\xd8")
        (root / "spec" / "y.md").write_text('# Y\n\n![b](b.jpg "caption text")\n', encoding="utf-8")

        joined = "\n".join(asm._render_file("spec/y.md"))
        assert f'![b]({img.resolve()} "caption text")' in joined

    # Verifies: REQ-p00080-H, REQ-p00080-I
    def test_REQ_p00080_H_unresolved_and_external_refs_unchanged(self, tmp_path):
        """Missing files and URLs are left as-is (resource-path fallback).

        Leaving the markdown untouched is correct -- pandoc still gets a
        shot via ``--resource-path``. What is NOT correct is staying
        silent about it (REQ-p00080-I): the missing ref must be recorded
        as a diagnostic while the URL must not.
        """
        asm, root = _image_asm(tmp_path)
        (root / "spec").mkdir()
        (root / "spec" / "z.md").write_text(
            "# Z\n\n![gone](missing/nope.png)\n\n" "![web](https://example.com/pic.png)\n",
            encoding="utf-8",
        )

        joined = "\n".join(asm._render_file("spec/z.md"))
        assert "![gone](missing/nope.png)" in joined
        assert "![web](https://example.com/pic.png)" in joined

        # The unresolvable ref is reported; the URL is not a failure.
        refs = [d.reference for d in asm.iter_diagnostics()]
        assert "missing/nope.png" in refs
        assert not any("example.com" in r for r in refs)

    # Verifies: REQ-p00080-H
    def test_REQ_p00080_H_associate_image_resolves_through_owning_repo(self, tmp_path):
        """Federated composition (TOOL-32): an associate-owned file's image
        must resolve against the ASSOCIATE repo root, not the root repo's."""
        fed, root_dir, assoc_dir = _make_federated_overview_graph(tmp_path)
        # Same relative path exists in BOTH repos; the associate's copy
        # must win for the associate-owned file.
        for repo in (root_dir, assoc_dir):
            (repo / "spec" / "img").mkdir(parents=True, exist_ok=True)
            (repo / "spec" / "img" / "d.png").write_bytes(b"\x89PNG")
        assoc_md = assoc_dir / "spec" / "prd-assoc.md"
        assoc_md.write_text(
            assoc_md.read_text(encoding="utf-8") + "\n![d](img/d.png)\n",
            encoding="utf-8",
        )

        asm = MarkdownAssembler(fed)
        output = asm.assemble()
        assoc_img = (assoc_dir / "spec" / "img" / "d.png").resolve()
        assert f"![d]({assoc_img})" in output
        root_img = (root_dir / "spec" / "img" / "d.png").resolve()
        assert f"![d]({root_img})" not in output


# ---------------------------------------------------------------------------
# Unresolvable-asset diagnostics (REQ-p00080-I)
# ---------------------------------------------------------------------------


class TestUnresolvableAssetDiagnostics:
    """Validates REQ-p00080-I: an image or diagram reference that cannot be
    located in any repository of the compiled graph is reported with the
    reference as written, the declaring spec file, and the locations searched.

    An image the compiler cannot place vanishes from the PDF leaving the
    surrounding prose intact, so the compiled document reads as complete.
    Recording the reference is what lets the caller say otherwise.
    """

    # Verifies: REQ-p00080-I
    def test_REQ_p00080_I_unresolvable_image_is_reported(self, tmp_path):
        """One unresolvable ref yields exactly one diagnostic carrying the
        reference as written, the declaring file, and the searched paths.
        """
        asm, root = _image_asm(tmp_path)
        (root / "spec").mkdir()
        (root / "spec" / "z.md").write_text(
            "# Z\n\n![gone](missing/nope.png)\n",
            encoding="utf-8",
        )

        asm._render_file("spec/z.md")

        diags = list(asm.iter_diagnostics())
        assert len(diags) == 1, f"expected exactly one diagnostic, got {diags!r}"
        assert asm.diagnostic_count() == 1
        diag = diags[0]
        assert diag.kind == "image"
        assert diag.reference == "missing/nope.png"
        assert diag.source_file == "spec/z.md"
        assert diag.searched, "diagnostic must record the locations searched"
        expected = str((root / "spec" / "missing" / "nope.png").resolve())
        assert (
            expected in diag.searched
        ), f"source-directory candidate {expected!r} missing from {diag.searched!r}"

    # Verifies: REQ-p00080-I
    def test_REQ_p00080_I_url_reference_is_not_reported(self, tmp_path):
        """A remote (http/https) ref is not a local resolution failure."""
        asm, root = _image_asm(tmp_path)
        (root / "spec").mkdir()
        (root / "spec" / "u.md").write_text(
            "# U\n\n![web](https://example.com/pic.png)\n",
            encoding="utf-8",
        )

        asm._render_file("spec/u.md")

        assert asm.diagnostic_count() == 0
        assert list(asm.iter_diagnostics()) == []

    # Verifies: REQ-p00080-I
    def test_REQ_p00080_I_resolvable_image_produces_no_diagnostic(self, tmp_path):
        """A ref that resolves normally must not be reported (no false positive)."""
        asm, root = _image_asm(tmp_path)
        (root / "spec" / "images").mkdir(parents=True)
        (root / "spec" / "images" / "ok.png").write_bytes(b"\x89PNG")
        (root / "spec" / "ok.md").write_text(
            "# OK\n\n![fine](images/ok.png)\n",
            encoding="utf-8",
        )

        joined = "\n".join(asm._render_file("spec/ok.md"))

        img = (root / "spec" / "images" / "ok.png").resolve()
        assert f"![fine]({img})" in joined
        assert asm.diagnostic_count() == 0

    # Verifies: REQ-p00080-I
    def test_REQ_p00080_I_resource_root_hit_produces_no_diagnostic(self, tmp_path):
        """A ref reachable only via a resource root is NOT a failure.

        ``deep/e.png`` lives at ``<root>/spec/deep/e.png``. It is neither
        under the source file's directory (``spec/sub/``) nor under the
        anchor repo root, so the two-candidate rewrite logic gives up --
        but pandoc WILL find it, because ``<root>/spec`` is on
        ``--resource-path``. Reporting it would be a false alarm.
        """
        asm, root = _image_asm(tmp_path)
        (root / "spec" / "sub").mkdir(parents=True)
        (root / "spec" / "deep").mkdir(parents=True)
        (root / "spec" / "deep" / "e.png").write_bytes(b"\x89PNG")
        (root / "spec" / "sub" / "x.md").write_text(
            "# Sub\n\n![depth](deep/e.png)\n",
            encoding="utf-8",
        )

        joined = "\n".join(asm._render_file("spec/sub/x.md"))

        # Left for pandoc's --resource-path to resolve, as REQ-p00080-H allows.
        assert "![depth](deep/e.png)" in joined
        assert asm.diagnostic_count() == 0, (
            f"resource-root-reachable ref must not be reported: "
            f"{[d.reference for d in asm.iter_diagnostics()]}"
        )

    # Verifies: REQ-p00080-I
    def test_REQ_p00080_I_unresolvable_mermaid_diagram_is_reported(self, tmp_path):
        """An unresolvable .mmd reference is reported with kind 'diagram'.

        A diagram whose source cannot be located leaves the document with
        nothing in its place, so the reference is named rather than
        dropped.
        """
        asm, root = _image_asm(tmp_path)
        (root / "spec").mkdir()
        (root / "spec" / "d.md").write_text(
            "# D\n\n![flow](missing/flow.mmd)\n",
            encoding="utf-8",
        )

        asm._render_file("spec/d.md")

        diags = list(asm.iter_diagnostics())
        assert len(diags) == 1, f"expected exactly one diagnostic, got {diags!r}"
        diag = diags[0]
        assert diag.kind == "diagram"
        assert diag.reference == "missing/flow.mmd"
        assert diag.source_file == "spec/d.md"
        assert diag.searched

    # Verifies: REQ-p00080-I
    def test_REQ_p00080_I_diagnostic_format_is_actionable(self):
        """format() surfaces the reference, the declaring file, and a
        searched location in one human-readable block.
        """
        from elspais.pdf.assembler import AssemblyDiagnostic

        diag = AssemblyDiagnostic(
            kind="image",
            reference="missing/nope.png",
            source_file="spec/z.md",
            repo="root",
            searched=("/repo/spec/missing/nope.png", "/repo/missing/nope.png"),
            cause="File not found in any searched location.",
            remedy="Add the file or correct the reference.",
        )

        text = diag.format()
        assert "missing/nope.png" in text
        assert "spec/z.md" in text
        assert "/repo/spec/missing/nope.png" in text


class TestResourceRoots:
    """Validates REQ-p00080-C: the assembler owns the single ordered,
    de-duplicated set of pandoc resource roots (each repo's root plus its
    spec/ directory), so the pdf command has no reason to rebuild its own.
    """

    # Verifies: REQ-p00080-C
    def test_REQ_p00080_C_resource_roots_cover_every_repo_in_order(self, tmp_path):
        """Federated: root repo's pair precedes the associate's, no dupes."""
        fed, root_dir, assoc_dir = _make_federated_overview_graph(tmp_path)
        asm = MarkdownAssembler(fed)

        roots = asm.resource_roots()

        assert [Path(p) for p in roots] == [
            root_dir.resolve(),
            (root_dir / "spec").resolve(),
            assoc_dir.resolve(),
            (assoc_dir / "spec").resolve(),
        ]
        assert len(roots) == len(set(roots)), f"duplicate resource roots: {roots!r}"


# ---------------------------------------------------------------------------
# Unreadable owning-repo source file (REQ-p00080-J)
# ---------------------------------------------------------------------------


class TestUnreadableSourceFileDiagnostics:
    """Validates REQ-p00080-J: when a requirement's source file cannot be read
    from its owning repository, the compiler reports the omitted file and the
    repository it was expected in, instead of emitting the document as though
    that content never existed.

    A path that resolves nowhere contributes no content, so an entire
    repository's requirements, assertions and rationale can leave the compiled
    document. Reporting the omission is what separates that from the
    silent-omission anti-pattern REQ-p00019 prohibits and REQ-p00080's
    instance of it concretizes.

    The file-level omission is reported through the same channel as the
    asset-level one (``iter_diagnostics``), with ``kind == "source-file"``
    and an empty ``source_file`` — the omitted thing *is* the file.
    """

    # Verifies: REQ-p00080-J
    def test_REQ_p00080_J_unresolvable_source_file_is_reported(self, tmp_path):
        """A path that exists nowhere renders nothing AND is reported once."""
        asm, root = _image_asm(tmp_path)
        (root / "spec").mkdir()

        lines = asm._render_file("spec/prd-absent.md")

        assert lines == [], "an unreadable file must contribute no content"
        diags = list(asm.iter_diagnostics())
        assert len(diags) == 1, f"expected exactly one diagnostic, got {diags!r}"
        assert asm.diagnostic_count() == 1
        diag = diags[0]
        assert diag.kind == "source-file"
        assert diag.reference == "spec/prd-absent.md"
        assert diag.source_file == "", "the omitted thing IS the file"
        # _wrap() names the federation-of-one from [project].name.
        assert diag.repo == "test"
        assert diag.searched, "diagnostic must record the locations searched"
        assert any(
            "spec/prd-absent.md" in location for location in diag.searched
        ), f"no candidate location names the missing file: {diag.searched!r}"
        assert diag.cause, "diagnostic must state why the file could not be read"
        assert diag.remedy, "diagnostic must state the action available"

    # Verifies: REQ-p00080-J
    def test_REQ_p00080_J_associate_file_reports_owning_repository(self, tmp_path):
        """The reported repo is the ASSOCIATE's, not the root repo's.

        Ownership comes from the federation's ownership map (the repo root
        the file was anchored to), never from the FILE node's ``repo``
        field, which is ``None`` for build-time associate FILE nodes.
        """
        fed, root_dir, assoc_dir = _make_federated_overview_graph(tmp_path)
        asm = MarkdownAssembler(fed)

        lines = asm._render_file("spec/prd-gone.md", owning_repo_root=assoc_dir)

        assert lines == []
        diags = list(asm.iter_diagnostics())
        assert len(diags) == 1, f"expected exactly one diagnostic, got {diags!r}"
        diag = diags[0]
        assert diag.kind == "source-file"
        assert diag.reference == "spec/prd-gone.md"
        assert diag.source_file == ""
        assert diag.repo == "assoc", (
            f"the file was expected in the associate repo, but the diagnostic "
            f"names {diag.repo!r}"
        )
        assert any(
            str(assoc_dir) in location for location in diag.searched
        ), f"associate repo root missing from searched locations: {diag.searched!r}"

    # Verifies: REQ-p00080-J
    def test_REQ_p00080_J_missing_file_reported_once(self, tmp_path):
        """A file missed by both the render pass and the Topic Index pass
        is reported exactly once, not once per pass.

        ``assemble()`` reaches the same path twice: ``_render_file`` for the
        body and ``_topics_from_file`` for the index. The dedupe key is
        (kind, reference, declaring file), so the second miss must fold
        into the first.
        """
        fed, _root_dir, assoc_dir = _make_federated_overview_graph(tmp_path)
        # The graph knows about the requirement; the file is gone from disk.
        (assoc_dir / "spec" / "prd-assoc.md").unlink()

        asm = MarkdownAssembler(fed)
        asm.assemble()

        source_file_diags = [d for d in asm.iter_diagnostics() if d.kind == "source-file"]
        assert len(source_file_diags) == 1, (
            f"expected one source-file diagnostic for one missing file, got "
            f"{source_file_diags!r}"
        )
        assert source_file_diags[0].reference == "spec/prd-assoc.md"
        assert source_file_diags[0].repo == "assoc"

    # Verifies: REQ-p00080-J
    def test_REQ_p00080_J_resolvable_file_produces_no_diagnostic(self, tmp_path):
        """Regression guard: a file that reads normally is never reported."""
        fed, _root_dir, assoc_dir = _make_federated_overview_graph(tmp_path)
        asm = MarkdownAssembler(fed)

        lines = asm._render_file("spec/prd-assoc.md", owning_repo_root=assoc_dir)

        assert lines, "expected the associate file to render"
        assert asm.diagnostic_count() == 0, (
            f"a readable file must not be reported: "
            f"{[d.reference for d in asm.iter_diagnostics()]}"
        )

    # Verifies: REQ-p00080-J
    def test_REQ_p00080_J_missing_repo_is_reported_and_document_degrades(self, tmp_path):
        """A whole associate repo going missing is reported AND the root
        repo's content still renders.

        The document is degraded, not aborted: dropping the associate's
        section must not cost the reader the root repo's requirements too.
        """
        import shutil as _shutil

        fed, _root_dir, assoc_dir = _make_federated_overview_graph(tmp_path)
        _shutil.rmtree(assoc_dir)

        asm = MarkdownAssembler(fed)
        output = asm.assemble()

        # Reported.
        source_file_diags = [d for d in asm.iter_diagnostics() if d.kind == "source-file"]
        assert source_file_diags, "the vanished repo's file was omitted without a word"
        assert any(d.reference == "spec/prd-assoc.md" for d in source_file_diags), (
            f"the omitted file was not named: " f"{[d.reference for d in source_file_diags]}"
        )
        assert any(d.repo == "assoc" for d in source_file_diags), (
            f"the repository the file was expected in was not named: "
            f"{[d.repo for d in source_file_diags]}"
        )

        # Degraded, not aborted.
        assert "Root Product Vision" in output
        assert "The root product SHALL define top-level goals." in output

    # Verifies: REQ-p00080-J
    def test_REQ_p00080_J_healthy_project_reports_nothing(self, canonical_federated_graph):
        """No false positives against a real project's spec files.

        The hht-like fixture is a real, complete spec estate on disk; every
        file the graph names must be readable, so a full assemble() must
        record nothing at all.
        """
        asm = MarkdownAssembler(canonical_federated_graph)
        asm.assemble()

        assert asm.diagnostic_count() == 0, (
            f"healthy project reported omissions: "
            f"{[(d.kind, d.reference) for d in asm.iter_diagnostics()]}"
        )


class TestCrossRepoTopicIndexInAssembledDocument:
    """Validates REQ-p00080-D: a topic drawing entries from more than one
    repository renders them on one index line, with the associate's entry
    annotated and the host repo's entry left bare.

    ``TestCrossRepoRendering`` proves the annotation exists somewhere in the
    Topic Index; this proves the two repos' entries actually meet on the same
    line of the fully assembled document, which is what makes the annotation
    legible to a reader scanning one topic.
    """

    # Verifies: REQ-p00080-D
    def test_REQ_p00080_D_shared_topic_line_carries_both_repos(self, tmp_path):
        fed, root_dir, assoc_dir = _make_federated_overview_graph(tmp_path)
        # Give both repos' spec files a topic in common.
        for path, existing in (
            (root_dir / "spec" / "prd-root.md", "Topics: root-topic"),
            (assoc_dir / "spec" / "prd-assoc.md", "Topics: associate-topic"),
        ):
            path.write_text(
                path.read_text(encoding="utf-8").replace(existing, f"{existing}, shared-topic"),
                encoding="utf-8",
            )

        asm = MarkdownAssembler(fed)
        output = asm.assemble()

        shared_lines = [ln for ln in output.split("\n") if ln.startswith("**shared-topic**")]
        assert len(shared_lines) == 1, f"expected one shared-topic index line: {shared_lines!r}"
        line = shared_lines[0]
        assert (
            "[assoc] [REQ-p00099](#REQ-p00099)" in line
        ), f"associate entry not annotated on the shared line: {line!r}"
        assert "[REQ-p00001](#REQ-p00001)" in line, f"host entry missing: {line!r}"
        assert (
            "[root] [REQ-p00001]" not in line
        ), f"host repo entry must render bare, not annotated: {line!r}"


# ---------------------------------------------------------------------------
# Percent-encoded references (REQ-p00080-I)
# ---------------------------------------------------------------------------


class TestPercentEncodedImageReferences:
    """Validates REQ-p00080-I: a URL-encoded image reference is judged on the
    file the encoding actually names, so the report never accuses a reference
    pandoc places without difficulty.

    Markdown authors percent-encode the characters that would otherwise break
    an inline link, spaces above all. Pandoc decodes the reference before
    fetching, so ``img/with%20space.png`` reaches ``img/with space.png`` on
    disk and the image lands in the PDF. A resolver that probes the encoded
    spelling verbatim finds nothing, and a report built on that probe names a
    reference that was never omitted -- an accusation the reader cannot act
    on, because the remedy it suggests is already satisfied.
    """

    # Verifies: REQ-p00080-I
    def test_REQ_p00080_I_percent_encoded_reference_resolves_to_decoded_file(self, tmp_path):
        """A ``%20`` reference whose decoded file exists is rewritten to that
        file's absolute path and reported as nothing at all.
        """
        asm, root = _image_asm(tmp_path)
        (root / "spec" / "img").mkdir(parents=True)
        img = root / "spec" / "img" / "with space.png"
        img.write_bytes(b"\x89PNG")
        (root / "spec" / "x.md").write_text(
            "# X\n\n![x](img/with%20space.png)\n",
            encoding="utf-8",
        )

        joined = "\n".join(asm._render_file("spec/x.md"))

        assert f"![x]({img.resolve()})" in joined, (
            f"the decoded file exists on disk but the reference was not "
            f"rewritten to it: {joined!r}"
        )
        assert asm.diagnostic_count() == 0, (
            f"a reference pandoc resolves without difficulty was reported as "
            f"omitted: {[d.reference for d in asm.iter_diagnostics()]}"
        )

    # Verifies: REQ-p00080-I
    def test_REQ_p00080_I_percent_encoded_reference_missing_reports_as_written(self, tmp_path):
        """Decoding is for the probe only: when the decoded file is absent too,
        the diagnostic still quotes the reference the author wrote, because
        that is the string they must find in the spec to correct it.
        """
        asm, root = _image_asm(tmp_path)
        (root / "spec").mkdir()
        (root / "spec" / "x.md").write_text(
            "# X\n\n![x](img/no%20such.png)\n",
            encoding="utf-8",
        )

        asm._render_file("spec/x.md")

        diags = list(asm.iter_diagnostics())
        assert len(diags) == 1, f"expected exactly one diagnostic, got {diags!r}"
        assert diags[0].kind == "image"
        assert diags[0].reference == "img/no%20such.png", (
            f"the diagnostic must quote the reference as written in the spec, "
            f"not its decoded form: {diags[0].reference!r}"
        )
        assert diags[0].source_file == "spec/x.md"


# ---------------------------------------------------------------------------
# Fenced code blocks (REQ-p00080-I)
# ---------------------------------------------------------------------------


class TestFencedCodeBlockReferences:
    """Validates REQ-p00080-I: an image reference inside a fenced code block is
    a sample of markdown, not a reference the document ever intended to place.

    A fenced block reproduces source text verbatim for the reader. Treating
    its contents as live references costs twice: an unresolvable sample earns
    a diagnostic for content that was never omitted, and a resolvable one gets
    rewritten to an absolute path, so the reader is shown a path from the
    author's machine in place of the line they were meant to copy. Both are
    failures of the same obligation -- what the compiler reports and renders
    must correspond to what it actually did.

    Indented (four-space) code blocks carry the same exemption; they are
    covered by ``TestIndentedCodeBlockReferences``.
    """

    # Verifies: REQ-p00080-I
    def test_REQ_p00080_I_unresolvable_reference_in_fence_is_not_reported(self, tmp_path):
        """A sample naming a file that does not exist is neither reported nor
        altered -- the fenced line survives byte-for-byte.
        """
        asm, root = _image_asm(tmp_path)
        (root / "spec").mkdir()
        sample = "![example](path/to/your-image.png)"
        (root / "spec" / "doc.md").write_text(
            f"# Doc\n\nEmbed an image like this:\n\n```markdown\n{sample}\n```\n",
            encoding="utf-8",
        )

        joined = "\n".join(asm._render_file("spec/doc.md"))

        assert asm.diagnostic_count() == 0, (
            f"a markdown sample inside a fence was reported as an omitted "
            f"reference: {[d.reference for d in asm.iter_diagnostics()]}"
        )
        assert sample in joined.split("\n"), (
            f"the fenced sample line must survive verbatim; rendered output " f"was {joined!r}"
        )

    # Verifies: REQ-p00080-I
    def test_REQ_p00080_I_fence_suppresses_rewrite_while_prose_still_rewrites(self, tmp_path):
        """The same reference is rewritten in prose and left alone in a fence.

        Both halves are asserted together so that fence tracking cannot be
        satisfied by simply not rewriting anything.
        """
        asm, root = _image_asm(tmp_path)
        (root / "spec" / "img").mkdir(parents=True)
        img = root / "spec" / "img" / "real.png"
        img.write_bytes(b"\x89PNG")
        (root / "spec" / "doc.md").write_text(
            "# Doc\n"
            "\n"
            "![real](img/real.png)\n"
            "\n"
            "```markdown\n"
            "![real](img/real.png)\n"
            "```\n",
            encoding="utf-8",
        )

        lines = asm._render_file("spec/doc.md")

        assert f"![real]({img.resolve()})" in lines, (
            f"the prose reference must still be rewritten to an absolute " f"path: {lines!r}"
        )
        assert "![real](img/real.png)" in lines, (
            f"the fenced sample must keep the relative path the author wrote: " f"{lines!r}"
        )
        assert asm.diagnostic_count() == 0

    # Verifies: REQ-p00080-I
    def test_REQ_p00080_I_tilde_fence_behaves_like_backtick_fence(self, tmp_path):
        """``~~~`` opens and closes a fence exactly as ``` does."""
        asm, root = _image_asm(tmp_path)
        (root / "spec").mkdir()
        sample = "![example](path/to/your-image.png)"
        (root / "spec" / "doc.md").write_text(
            f"# Doc\n\n~~~markdown\n{sample}\n~~~\n\n![gone](also/missing.png)\n",
            encoding="utf-8",
        )

        joined = "\n".join(asm._render_file("spec/doc.md"))

        refs = [d.reference for d in asm.iter_diagnostics()]
        assert "path/to/your-image.png" not in refs, (
            f"a reference inside a ~~~ fence was reported as omitted: " f"{refs!r}"
        )
        assert "also/missing.png" in refs, (
            f"the fence must close at the second ~~~ so the prose reference "
            f"after it is still judged: {refs!r}"
        )
        assert sample in joined.split("\n"), f"the fenced sample line was altered: {joined!r}"


# ---------------------------------------------------------------------------
# Absolute image references (REQ-p00080-I)
# ---------------------------------------------------------------------------


class TestAbsoluteImageReferences:
    """Validates REQ-p00080-I: an absolute image path that does not exist is
    reported by the compiler, before the typesetter dies on it.

    An absolute reference needs no resolution, so the assembler passes it
    through untouched -- and pandoc then aborts the whole compile on a file it
    cannot open, naming the path and nothing else. The reader is left with no
    document, no declaring spec file, and no remedy. Probing the path costs
    one stat call and turns that dead end into the same actionable report
    every other unresolvable reference gets.
    """

    # Verifies: REQ-p00080-I
    def test_REQ_p00080_I_missing_absolute_path_is_reported(self, tmp_path):
        """A nonexistent absolute reference yields one diagnostic naming the
        declaring spec file and stating that the path is absolute and absent.
        """
        asm, root = _image_asm(tmp_path)
        (root / "spec").mkdir()
        absent = tmp_path / "nowhere" / "abs.png"
        (root / "spec" / "a.md").write_text(
            f"# A\n\n![abs]({absent})\n",
            encoding="utf-8",
        )

        asm._render_file("spec/a.md")

        diags = list(asm.iter_diagnostics())
        assert len(diags) == 1, f"expected exactly one diagnostic, got {diags!r}"
        diag = diags[0]
        assert diag.kind == "image"
        assert diag.reference == str(absent)
        assert diag.source_file == "spec/a.md", (
            f"the declaring spec file is the one thing pandoc's own abort "
            f"cannot supply: {diag.source_file!r}"
        )
        assert "absolute" in diag.cause.lower(), (
            f"the cause must say the path is absolute, so the reader knows "
            f"no search would have helped: {diag.cause!r}"
        )
        assert diag.remedy

    # Verifies: REQ-p00080-I
    def test_REQ_p00080_I_existing_absolute_path_is_left_alone(self, tmp_path):
        """An absolute reference that resolves is neither rewritten nor
        reported (no false positive).
        """
        asm, root = _image_asm(tmp_path)
        (root / "spec").mkdir()
        present = tmp_path / "elsewhere" / "abs.png"
        present.parent.mkdir(parents=True)
        present.write_bytes(b"\x89PNG")
        (root / "spec" / "a.md").write_text(
            f"# A\n\n![abs]({present})\n",
            encoding="utf-8",
        )

        joined = "\n".join(asm._render_file("spec/a.md"))

        assert f"![abs]({present})" in joined
        assert asm.diagnostic_count() == 0, (
            f"an absolute reference that exists must not be reported: "
            f"{[d.reference for d in asm.iter_diagnostics()]}"
        )

    # Verifies: REQ-p00080-I
    def test_REQ_p00080_I_file_url_reference_is_not_reported(self, tmp_path):
        """Regression guard: a ``file://`` reference is a URL, not a local
        path the assembler is entitled to judge.
        """
        asm, root = _image_asm(tmp_path)
        (root / "spec").mkdir()
        (root / "spec" / "a.md").write_text(
            "# A\n\n![f](file:///opt/assets/pic.png)\n",
            encoding="utf-8",
        )

        joined = "\n".join(asm._render_file("spec/a.md"))

        assert "![f](file:///opt/assets/pic.png)" in joined
        assert asm.diagnostic_count() == 0, (
            f"a URL reference must never be reported as a missing local file: "
            f"{[d.reference for d in asm.iter_diagnostics()]}"
        )


# ---------------------------------------------------------------------------
# Unloadable associate repository (REQ-p00080-J)
# ---------------------------------------------------------------------------


def _fed_with_unloadable_associate(tmp_path: Path):
    """Federation whose associate never loaded: no graph, no directory.

    This is the shape a misconfigured ``[associates.<name>] path`` produces --
    the entry survives federation so the name is still known, but it carries
    no graph and its configured root is not on disk.
    """
    from elspais.graph.federated import FederatedGraph, RepoEntry

    fed, root_dir, assoc_dir = _make_federated_overview_graph(tmp_path)
    missing_root = tmp_path / "nowhere"
    entries = []
    for entry in fed.iter_repos():
        if entry.name == "assoc":
            entries.append(RepoEntry(name="assoc", graph=None, config=None, repo_root=missing_root))
        else:
            entries.append(entry)
    return FederatedGraph(entries, root_repo="root"), root_dir, missing_root


class TestUnloadableRepositoryDiagnostics:
    """Validates REQ-p00080-J: a configured repository that never loaded is
    reported, rather than silently subtracting every requirement it owns.

    A repository whose configured path does not resolve contributes no graph,
    so nothing downstream ever names one of its files -- the file-level report
    cannot fire, and the document simply comes out without that repository's
    section. The reader has no way to tell that from a project that legitimately
    has one fewer repository. The omission is a whole repository, so it is
    disclosed as one, naming the repository and the path that was expected to
    hold it.
    """

    # Verifies: REQ-p00080-J
    def test_REQ_p00080_J_unloadable_repository_is_reported(self, tmp_path):
        """One unloadable associate yields exactly one repository diagnostic
        naming the repo and the configured root, and the root repo's content
        still renders.
        """
        fed, _root_dir, missing_root = _fed_with_unloadable_associate(tmp_path)

        asm = MarkdownAssembler(fed)
        output = asm.assemble()

        repo_diags = [d for d in asm.iter_diagnostics() if d.kind == "repository"]
        assert len(repo_diags) == 1, (
            f"expected exactly one repository diagnostic, got "
            f"{[(d.kind, d.reference) for d in asm.iter_diagnostics()]}"
        )
        diag = repo_diags[0]
        assert diag.reference == "assoc"
        assert diag.source_file == "", "the omitted thing IS the repository"
        assert diag.repo == "assoc"
        assert any(
            str(missing_root) in location for location in diag.searched
        ), f"the configured root is missing from the searched locations: {diag.searched!r}"
        assert diag.cause, "the diagnostic must state why the repository is absent"
        assert "associate" in diag.remedy.lower(), (
            f"the remedy must point at the associate configuration, which is "
            f"where the wrong path lives: {diag.remedy!r}"
        )

        # Degraded, not aborted.
        assert "Root Product Vision" in output

    # Verifies: REQ-p00080-J
    def test_REQ_p00080_J_healthy_federation_reports_no_repository(self, tmp_path):
        """Regression guard: every repo loading normally reports nothing."""
        fed, _root_dir, _assoc_dir = _make_federated_overview_graph(tmp_path)

        asm = MarkdownAssembler(fed)
        asm.assemble()

        repo_diags = [d for d in asm.iter_diagnostics() if d.kind == "repository"]
        assert repo_diags == [], (
            f"a healthy federation must report no missing repository: "
            f"{[d.reference for d in repo_diags]}"
        )


# ---------------------------------------------------------------------------
# Unterminated fenced code blocks (REQ-p00080-I)
# ---------------------------------------------------------------------------


class TestUnterminatedCodeFenceDiagnostics:
    """Validates REQ-p00080-I: a spec file whose code fence is never closed is
    reported, because from the opening fence onward the compiler stops
    analysing the file and can no longer say what it did or did not place.

    Fence tracking makes every line after an unclosed ``` pass through
    untouched to end of file: the ``*End*`` footer, later requirement
    headings, and every image reference in the runaway region are neither
    processed nor judged. The document still compiles, so nothing downstream
    notices — headings inside the region simply reappear as numbered sections
    and references there are never checked. A region the compiler cannot
    analyse is exactly the thing it must name rather than pass over in
    silence.
    """

    # Verifies: REQ-p00080-I
    def test_REQ_p00080_I_unterminated_fence_is_reported(self, tmp_path):
        """A file opening a fence it never closes yields exactly one
        ``code-fence`` diagnostic naming that file, and still renders.
        """
        asm, root = _image_asm(tmp_path)
        (root / "spec").mkdir()
        (root / "spec" / "doc.md").write_text(
            "# Doc\n"
            "\n"
            "Prose before the sample.\n"
            "\n"
            "```markdown\n"
            "a sample line\n"
            "\n"
            "PROSE AFTER THE RUNAWAY FENCE\n",
            encoding="utf-8",
        )

        joined = "\n".join(asm._render_file("spec/doc.md"))

        fence_diags = [d for d in asm.iter_diagnostics() if d.kind == "code-fence"]
        assert len(fence_diags) == 1, (
            f"an unterminated fence must be reported exactly once; "
            f"diagnostics were {[(d.kind, d.reference) for d in asm.iter_diagnostics()]}"
        )
        diag = fence_diags[0]
        assert diag.reference == "spec/doc.md", (
            f"the diagnostic must name the spec file holding the unclosed "
            f"fence: {diag.reference!r}"
        )
        assert (
            diag.source_file == "spec/doc.md"
        ), f"the declaring file is the same file: {diag.source_file!r}"
        assert diag.cause, "the diagnostic must state why the region is unanalysable"
        assert diag.remedy, "the diagnostic must state the action available"

        # Degraded, not aborted: the file still renders.
        assert (
            "PROSE AFTER THE RUNAWAY FENCE" in joined
        ), f"an unterminated fence must not cost the rest of the file: {joined!r}"

    # Verifies: REQ-p00080-I
    def test_REQ_p00080_I_balanced_fences_report_nothing(self, tmp_path):
        """Regression guard: a file whose fences all close is not reported."""
        asm, root = _image_asm(tmp_path)
        (root / "spec").mkdir()
        (root / "spec" / "doc.md").write_text(
            "# Doc\n"
            "\n"
            "```markdown\n"
            "first sample\n"
            "```\n"
            "\n"
            "Between the samples.\n"
            "\n"
            "~~~text\n"
            "second sample\n"
            "~~~\n",
            encoding="utf-8",
        )

        asm._render_file("spec/doc.md")

        fence_diags = [d for d in asm.iter_diagnostics() if d.kind == "code-fence"]
        assert fence_diags == [], (
            f"a file whose fences are all closed must report nothing: "
            f"{[d.reference for d in fence_diags]}"
        )

    # Verifies: REQ-p00080-I
    def test_REQ_p00080_I_unterminated_tilde_fence_is_reported(self, tmp_path):
        """``~~~`` left open is reported exactly as ``` left open is."""
        asm, root = _image_asm(tmp_path)
        (root / "spec").mkdir()
        (root / "spec" / "doc.md").write_text(
            "# Doc\n"
            "\n"
            "Prose before the sample.\n"
            "\n"
            "~~~text\n"
            "a sample line\n"
            "\n"
            "PROSE AFTER THE RUNAWAY FENCE\n",
            encoding="utf-8",
        )

        joined = "\n".join(asm._render_file("spec/doc.md"))

        fence_diags = [d for d in asm.iter_diagnostics() if d.kind == "code-fence"]
        assert len(fence_diags) == 1, (
            f"an unterminated ~~~ fence must be reported exactly once; "
            f"diagnostics were {[(d.kind, d.reference) for d in asm.iter_diagnostics()]}"
        )
        assert fence_diags[0].reference == "spec/doc.md"
        assert "PROSE AFTER THE RUNAWAY FENCE" in joined


# ---------------------------------------------------------------------------
# Indented code blocks (REQ-p00080-I)
# ---------------------------------------------------------------------------


class TestIndentedCodeBlockReferences:
    """Validates REQ-p00080-I: an image reference inside a four-space indented
    code block is a sample of markdown, not a reference the document ever
    intended to place, and must be neither rewritten nor reported.

    CommonMark gives indented blocks the same verbatim standing as fenced
    ones, and pandoc typesets them the same way — it never tries to fetch
    anything named inside one. Treating them as live references costs twice,
    exactly as it does for fences: a sample naming a file that does not exist
    earns a report of an omission that never happened, and a sample naming one
    that does exist is rewritten to an absolute path from the author's
    machine, so the line the reader was meant to copy is not the line they are
    shown.

    The boundary matters as much as the exemption. A block begins only on a
    4+-space line following a blank line, runs through blank lines, and ends
    at the first non-blank line indented less than four; a 4-space
    continuation under a list item is list content, not code. Suppressing more
    than that would silence genuine omissions in ordinary prose, which is the
    same failure in the other direction.
    """

    # Verifies: REQ-p00080-I
    def test_REQ_p00080_I_missing_reference_in_indented_block_is_not_reported(self, tmp_path):
        """A sample naming a file that does not exist is neither reported nor
        altered -- the indented line survives byte-for-byte.
        """
        asm, root = _image_asm(tmp_path)
        (root / "spec").mkdir()
        sample = "    ![example](path/to/your-image.png)"
        (root / "spec" / "doc.md").write_text(
            f"# Doc\n\nEmbed an image like this:\n\n{sample}\n",
            encoding="utf-8",
        )

        lines = asm._render_file("spec/doc.md")

        assert asm.diagnostic_count() == 0, (
            f"a markdown sample inside an indented code block was reported as "
            f"an omitted reference: {[d.reference for d in asm.iter_diagnostics()]}"
        )
        assert sample in lines, (
            f"the indented sample line must survive verbatim; rendered output " f"was {lines!r}"
        )

    # Verifies: REQ-p00080-I
    def test_REQ_p00080_I_indent_suppresses_rewrite_while_prose_still_rewrites(self, tmp_path):
        """The same resolving reference is rewritten in prose and left alone in
        an indented block.

        Both halves are asserted together so that indent detection cannot be
        satisfied by simply not rewriting anything.
        """
        asm, root = _image_asm(tmp_path)
        (root / "spec" / "img").mkdir(parents=True)
        img = root / "spec" / "img" / "real.png"
        img.write_bytes(b"\x89PNG")
        (root / "spec" / "doc.md").write_text(
            "# Doc\n"
            "\n"
            "![real](img/real.png)\n"
            "\n"
            "Write it like this:\n"
            "\n"
            "    ![real](img/real.png)\n",
            encoding="utf-8",
        )

        lines = asm._render_file("spec/doc.md")

        assert f"![real]({img.resolve()})" in lines, (
            f"the prose reference must still be rewritten to an absolute " f"path: {lines!r}"
        )
        assert "    ![real](img/real.png)" in lines, (
            f"the indented sample must keep the relative path the author " f"wrote: {lines!r}"
        )
        assert asm.diagnostic_count() == 0

    # Verifies: REQ-p00080-I
    def test_REQ_p00080_I_tab_indented_block_behaves_like_four_spaces(self, tmp_path):
        """A tab opens an indented block exactly as four spaces do."""
        asm, root = _image_asm(tmp_path)
        (root / "spec").mkdir()
        sample = "\t![example](path/to/your-image.png)"
        (root / "spec" / "doc.md").write_text(
            f"# Doc\n\nEmbed an image like this:\n\n{sample}\n",
            encoding="utf-8",
        )

        lines = asm._render_file("spec/doc.md")

        assert asm.diagnostic_count() == 0, (
            f"a markdown sample inside a tab-indented code block was reported "
            f"as an omitted reference: {[d.reference for d in asm.iter_diagnostics()]}"
        )
        assert sample in lines, f"the tab-indented sample line must survive verbatim: {lines!r}"

    # Verifies: REQ-p00080-I
    def test_REQ_p00080_I_reference_after_indented_block_is_still_reported(self, tmp_path):
        """The block ends at the first unindented line, so a genuine omission
        after it is still judged.

        Blank lines inside the block do not end it; the unindented prose line
        does. Without this, "recognise indented blocks" could be satisfied by
        suppressing everything after the first indent -- silencing every real
        omission in the remainder of the file.
        """
        asm, root = _image_asm(tmp_path)
        (root / "spec").mkdir()
        (root / "spec" / "doc.md").write_text(
            "# Doc\n"
            "\n"
            "Write it like this:\n"
            "\n"
            "    ![one](missing/one.png)\n"
            "\n"
            "    ![two](missing/two.png)\n"
            "\n"
            "![three](missing/three.png)\n",
            encoding="utf-8",
        )

        asm._render_file("spec/doc.md")

        refs = [d.reference for d in asm.iter_diagnostics()]
        assert (
            "missing/one.png" not in refs
        ), f"a reference inside the indented block was reported: {refs!r}"
        assert "missing/two.png" not in refs, (
            f"the indented block must continue across a blank line, so the "
            f"second sample is still inside it: {refs!r}"
        )
        assert "missing/three.png" in refs, (
            f"the indented block must end at the first unindented line, so "
            f"the prose reference after it is still judged: {refs!r}"
        )

    # Verifies: REQ-p00080-I
    def test_REQ_p00080_I_list_continuation_is_not_treated_as_code(self, tmp_path):
        """A 4-space continuation under a ``- `` item is list content.

        Under a list item whose content indent is two columns, four spaces is
        an ordinary continuation paragraph, not a code block. A reference
        there is live, and an omission there is a real one.
        """
        asm, root = _image_asm(tmp_path)
        (root / "spec").mkdir()
        (root / "spec" / "doc.md").write_text(
            "# Doc\n" "\n" "- first item\n" "\n" "    ![gone](missing/list.png)\n",
            encoding="utf-8",
        )

        asm._render_file("spec/doc.md")

        refs = [d.reference for d in asm.iter_diagnostics()]
        assert "missing/list.png" in refs, (
            f"a reference in a list-item continuation is live content, not a "
            f"code sample, and its omission must still be reported: {refs!r}"
        )

    # Verifies: REQ-p00080-I
    def test_REQ_p00080_I_indented_paragraph_continuation_is_not_code(self, tmp_path):
        """An indented line that does not follow a blank line continues the
        paragraph and is not a code block.

        CommonMark forbids an indented code block from interrupting a
        paragraph, so this reference is ordinary prose and a real omission.
        """
        asm, root = _image_asm(tmp_path)
        (root / "spec").mkdir()
        (root / "spec" / "doc.md").write_text(
            "# Doc\n"
            "\n"
            "This sentence runs on to the next line\n"
            "    ![gone](missing/lazy.png)\n",
            encoding="utf-8",
        )

        asm._render_file("spec/doc.md")

        refs = [d.reference for d in asm.iter_diagnostics()]
        assert "missing/lazy.png" in refs, (
            f"an indented line continuing a paragraph is prose, not a code "
            f"block, and its omission must still be reported: {refs!r}"
        )
