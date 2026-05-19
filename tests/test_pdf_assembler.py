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
