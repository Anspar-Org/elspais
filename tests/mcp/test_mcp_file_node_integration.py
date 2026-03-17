# Validates REQ-d00133-A, REQ-d00133-B, REQ-d00133-C
# Validates REQ-d00133-D, REQ-d00133-E, REQ-d00133-F
"""Tests for MCP FILE node integration.

Tests REQ-d00133: MCP FILE Node Integration
- get_subtree from FILE root uses CONTAINS edges
- get_subtree from REQUIREMENT root uses domain edges
- _SUBTREE_KIND_DEFAULTS includes FILE entry
- search excludes FILE nodes
- get_graph_status includes FILE node counts
- Serialization produces correct file/line fields
"""

from pathlib import Path

import pytest

from elspais.graph import EdgeKind, GraphNode, NodeKind
from elspais.graph.builder import TraceGraph
from elspais.graph.GraphNode import FileType

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def file_node_graph():
    """Create a TraceGraph with FILE nodes for MCP integration tests.

    Structure:
        FILE: file:spec/requirements.md
          ├─ CONTAINS ─> REQ-p00001 "Platform Security" (PRD, Active)
          │    ├─ STRUCTURES ─> Assertion A: "SHALL encrypt data"
          │    └─ STRUCTURES ─> Assertion B: "SHALL use TLS"
          ├─ CONTAINS ─> REQ-o00010 "Security Ops" (OPS, Active, implements REQ-p00001)
          │    └─ STRUCTURES ─> Assertion C: "SHALL rotate keys"
          └─ CONTAINS ─> remainder:1 "Header text"

        FILE: file:spec/dev.md
          └─ CONTAINS ─> REQ-d00020 "Encryption Module" (DEV, Active, implements REQ-o00010)
               └─ STRUCTURES ─> Assertion D: "SHALL use AES-256"
    """
    graph = TraceGraph(repo_root=Path("/test/repo"))

    # --- FILE node for spec/requirements.md ---
    file1 = GraphNode(id="file:spec/requirements.md", kind=NodeKind.FILE, label="requirements.md")
    file1.set_field("file_type", FileType.SPEC)
    file1.set_field("relative_path", "spec/requirements.md")
    file1.set_field("absolute_path", "/test/repo/spec/requirements.md")
    file1.set_field("repo", None)

    # --- FILE node for spec/dev.md ---
    file2 = GraphNode(id="file:spec/dev.md", kind=NodeKind.FILE, label="dev.md")
    file2.set_field("file_type", FileType.SPEC)
    file2.set_field("relative_path", "spec/dev.md")
    file2.set_field("absolute_path", "/test/repo/spec/dev.md")
    file2.set_field("repo", None)

    # --- PRD requirement ---
    req_prd = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT, label="Platform Security")
    req_prd.set_field("level", "PRD")
    req_prd.set_field("status", "Active")
    req_prd.set_field("parse_line", 5)
    req_prd.set_field("keywords", ["security", "platform"])

    assertion_a = GraphNode(id="REQ-p00001-A", kind=NodeKind.ASSERTION, label="SHALL encrypt data")
    assertion_a.set_field("label", "A")
    assertion_a.set_field("parse_line", 10)

    assertion_b = GraphNode(id="REQ-p00001-B", kind=NodeKind.ASSERTION, label="SHALL use TLS")
    assertion_b.set_field("label", "B")
    assertion_b.set_field("parse_line", 12)

    # --- OPS requirement ---
    req_ops = GraphNode(id="REQ-o00010", kind=NodeKind.REQUIREMENT, label="Security Operations")
    req_ops.set_field("level", "OPS")
    req_ops.set_field("status", "Active")
    req_ops.set_field("parse_line", 20)
    req_ops.set_field("keywords", ["security", "operations"])

    assertion_c = GraphNode(id="REQ-o00010-C", kind=NodeKind.ASSERTION, label="SHALL rotate keys")
    assertion_c.set_field("label", "C")
    assertion_c.set_field("parse_line", 25)

    # --- DEV requirement ---
    req_dev = GraphNode(id="REQ-d00020", kind=NodeKind.REQUIREMENT, label="Encryption Module")
    req_dev.set_field("level", "DEV")
    req_dev.set_field("status", "Active")
    req_dev.set_field("parse_line", 3)
    req_dev.set_field("keywords", ["encryption", "module"])

    assertion_d = GraphNode(id="REQ-d00020-D", kind=NodeKind.ASSERTION, label="SHALL use AES-256")
    assertion_d.set_field("label", "D")
    assertion_d.set_field("parse_line", 8)

    # --- Remainder ---
    remainder = GraphNode(id="remainder:1", kind=NodeKind.REMAINDER, label="Header text")
    remainder.set_field("parse_line", 1)
    remainder.set_field("body_text", "# Spec Header\n\nSome intro text.")

    # --- Wire CONTAINS edges (FILE -> top-level nodes) ---
    file1.link(req_prd, EdgeKind.CONTAINS)
    file1.link(req_ops, EdgeKind.CONTAINS)
    file1.link(remainder, EdgeKind.CONTAINS)

    file2.link(req_dev, EdgeKind.CONTAINS)

    # --- Wire STRUCTURES edges (REQUIREMENT -> ASSERTION) ---
    req_prd.link(assertion_a, EdgeKind.STRUCTURES)
    req_prd.link(assertion_b, EdgeKind.STRUCTURES)
    req_ops.link(assertion_c, EdgeKind.STRUCTURES)
    req_dev.link(assertion_d, EdgeKind.STRUCTURES)

    # --- Wire domain edges (IMPLEMENTS) ---
    req_ops.link(req_prd, EdgeKind.IMPLEMENTS)
    req_dev.link(req_ops, EdgeKind.IMPLEMENTS)

    # --- Register all nodes ---
    for node in [
        file1,
        file2,
        req_prd,
        req_ops,
        req_dev,
        assertion_a,
        assertion_b,
        assertion_c,
        assertion_d,
        remainder,
    ]:
        graph._index[node.id] = node

    return graph


# ─────────────────────────────────────────────────────────────────────────────
# Test: get_subtree from FILE root uses CONTAINS edges (REQ-d00133-A)
# ─────────────────────────────────────────────────────────────────────────────


class TestSubtreeFromFileNode:
    """Validates REQ-d00133-A: get_subtree from FILE walks CONTAINS edges."""

    def test_REQ_d00133_A_subtree_from_file_walks_contains(self, file_node_graph):
        """Starting from a FILE node, _collect_subtree should walk CONTAINS edges."""
        from elspais.mcp.server import _collect_subtree

        collected = _collect_subtree(file_node_graph, "file:spec/requirements.md")
        collected_ids = [node.id for node, _ in collected]

        # Should include the FILE node itself and its CONTAINS children
        assert "file:spec/requirements.md" in collected_ids
        assert "REQ-p00001" in collected_ids
        assert "REQ-o00010" in collected_ids
        assert "remainder:1" in collected_ids

        # Should NOT include nodes from other files
        assert "REQ-d00020" not in collected_ids
        # Should NOT include ASSERTION nodes (reached via STRUCTURES, not CONTAINS)
        # unless kind filter includes them
        assert "file:spec/dev.md" not in collected_ids

    def test_REQ_d00133_A_subtree_from_file_does_not_cross_to_domain(self, file_node_graph):
        """FILE subtree should not follow IMPLEMENTS edges to other requirements."""
        from elspais.mcp.server import _collect_subtree

        collected = _collect_subtree(file_node_graph, "file:spec/requirements.md")
        collected_ids = [node.id for node, _ in collected]

        # REQ-d00020 is in a different file, reachable only via IMPLEMENTS from REQ-o00010
        # FILE subtree should NOT follow IMPLEMENTS edges
        assert "REQ-d00020" not in collected_ids

    def test_REQ_d00133_A_get_subtree_markdown_from_file(self, file_node_graph):
        """get_subtree with markdown format from FILE root."""
        from elspais.mcp.server import _get_subtree

        result = _get_subtree(file_node_graph, root_id="file:spec/requirements.md")
        assert "error" not in result
        assert result["format"] == "markdown"
        assert "REQ-p00001" in result["content"]
        assert "REQ-o00010" in result["content"]

    def test_REQ_d00133_A_get_subtree_nested_from_file(self, file_node_graph):
        """get_subtree with nested format from FILE root."""
        from elspais.mcp.server import _get_subtree

        result = _get_subtree(file_node_graph, root_id="file:spec/requirements.md", format="nested")
        assert "error" not in result
        assert result["format"] == "nested"
        tree = result["tree"]
        assert tree["id"] == "file:spec/requirements.md"
        child_ids = [c["id"] for c in tree["children"]]
        assert "REQ-p00001" in child_ids
        assert "REQ-o00010" in child_ids


# ─────────────────────────────────────────────────────────────────────────────
# Test: get_subtree from REQUIREMENT root uses domain edges (REQ-d00133-B)
# ─────────────────────────────────────────────────────────────────────────────


class TestSubtreeFromRequirementNode:
    """Validates REQ-d00133-B: get_subtree from REQUIREMENT walks domain edges."""

    def test_REQ_d00133_B_subtree_from_req_walks_domain_edges(self, file_node_graph):
        """Starting from a REQUIREMENT, _collect_subtree should walk domain edges."""
        from elspais.mcp.server import _collect_subtree

        collected = _collect_subtree(file_node_graph, "REQ-p00001")
        collected_ids = [node.id for node, _ in collected]

        # Should include the requirement and its assertions
        assert "REQ-p00001" in collected_ids
        assert "REQ-p00001-A" in collected_ids
        assert "REQ-p00001-B" in collected_ids

        # Should NOT include FILE nodes
        assert "file:spec/requirements.md" not in collected_ids
        assert "file:spec/dev.md" not in collected_ids

    def test_REQ_d00133_B_subtree_from_req_excludes_file_nodes(self, file_node_graph):
        """REQUIREMENT subtree should not include FILE nodes."""
        from elspais.mcp.server import _collect_subtree

        collected = _collect_subtree(file_node_graph, "REQ-p00001")
        file_nodes = [node for node, _ in collected if node.kind == NodeKind.FILE]
        assert len(file_nodes) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Test: _SUBTREE_KIND_DEFAULTS includes FILE entry (REQ-d00133-C)
# ─────────────────────────────────────────────────────────────────────────────


class TestSubtreeKindDefaults:
    """Validates REQ-d00133-C: _SUBTREE_KIND_DEFAULTS includes FILE."""

    def test_REQ_d00133_C_file_entry_in_subtree_defaults(self):
        """_SUBTREE_KIND_DEFAULTS should have a NodeKind.FILE entry."""
        from elspais.mcp.server import _SUBTREE_KIND_DEFAULTS

        assert NodeKind.FILE in _SUBTREE_KIND_DEFAULTS
        defaults = _SUBTREE_KIND_DEFAULTS[NodeKind.FILE]
        # Should include REQUIREMENT and REMAINDER for file contents
        assert NodeKind.REQUIREMENT in defaults
        assert NodeKind.REMAINDER in defaults


# ─────────────────────────────────────────────────────────────────────────────
# Test: search excludes FILE nodes (REQ-d00133-D)
# ─────────────────────────────────────────────────────────────────────────────


class TestSearchExcludesFileNodes:
    """Validates REQ-d00133-D: search does not return FILE nodes."""

    def test_REQ_d00133_D_search_excludes_file_nodes(self, file_node_graph):
        """_search should not return FILE nodes even if query matches."""
        from elspais.mcp.server import _search

        # Search for something that would match a FILE node's path
        results = _search(file_node_graph, "requirements")
        result_ids = [r["id"] for r in results]

        # Should NOT include FILE nodes
        for rid in result_ids:
            assert not rid.startswith("file:")

    def test_REQ_d00133_D_search_returns_requirements_only(self, file_node_graph):
        """_search should only return REQUIREMENT nodes."""
        from elspais.mcp.server import _search

        results = _search(file_node_graph, "security")
        assert len(results) > 0
        # All results should be requirements
        for result in results:
            node = file_node_graph.find_by_id(result["id"])
            assert node is not None
            assert node.kind == NodeKind.REQUIREMENT


# ─────────────────────────────────────────────────────────────────────────────
# Test: get_graph_status includes FILE counts (REQ-d00133-E)
# ─────────────────────────────────────────────────────────────────────────────


class TestGraphStatusIncludesFileNodes:
    """Validates REQ-d00133-E: get_graph_status includes FILE node counts."""

    def test_REQ_d00133_E_graph_status_reports_file_count(self, file_node_graph):
        """_get_graph_status should include 'file' in node_counts."""
        from elspais.mcp.server import _get_graph_status

        status = _get_graph_status(file_node_graph)
        assert "node_counts" in status
        assert "file" in status["node_counts"]
        assert status["node_counts"]["file"] == 2


# ─────────────────────────────────────────────────────────────────────────────
# Test: Serialization produces correct file/line fields (REQ-d00133-F)
# ─────────────────────────────────────────────────────────────────────────────


class TestSerializationFileLineFields:
    """Validates REQ-d00133-F: MCP serialization produces correct file/line."""

    def test_REQ_d00133_F_serialize_test_info_file_line(self, file_node_graph):
        """_serialize_test_info should show correct file/line from FILE parent."""
        from elspais.mcp.server import _serialize_test_info

        # Create a TEST node with a FILE parent
        test_node = GraphNode(id="test:test_encrypt", kind=NodeKind.TEST, label="test_encrypt")
        test_node.set_field("parse_line", 42)
        test_node.set_field("name", "test_encrypt")

        file_test = GraphNode(
            id="file:tests/test_security.py", kind=NodeKind.FILE, label="test_security.py"
        )
        file_test.set_field("relative_path", "tests/test_security.py")
        file_test.set_field("file_type", FileType.TEST)
        file_test.link(test_node, EdgeKind.CONTAINS)

        # Register in graph
        file_node_graph._index[test_node.id] = test_node
        file_node_graph._index[file_test.id] = file_test

        result = _serialize_test_info(test_node, file_node_graph)
        assert result["file"] == "tests/test_security.py"
        assert result["line"] == 42

    def test_REQ_d00133_F_serialize_code_info_file_line(self, file_node_graph):
        """_serialize_code_info should show correct file/line from FILE parent."""
        from elspais.mcp.server import _serialize_code_info

        # Create a CODE node with a FILE parent
        code_node = GraphNode(id="code:encrypt_fn", kind=NodeKind.CODE, label="encrypt_fn")
        code_node.set_field("parse_line", 99)

        file_code = GraphNode(id="file:src/encrypt.py", kind=NodeKind.FILE, label="encrypt.py")
        file_code.set_field("relative_path", "src/encrypt.py")
        file_code.set_field("file_type", FileType.CODE)
        file_code.link(code_node, EdgeKind.CONTAINS)

        file_node_graph._index[code_node.id] = code_node
        file_node_graph._index[file_code.id] = file_code

        result = _serialize_code_info(code_node, file_node_graph)
        assert result["file"] == "src/encrypt.py"
        assert result["line"] == 99

    def test_REQ_d00133_F_relative_source_path_from_file_node(self, file_node_graph):
        """_relative_source_path should navigate to FILE parent correctly."""
        from elspais.mcp.server import _relative_source_path

        req_node = file_node_graph.find_by_id("REQ-p00001")
        assert req_node is not None
        path = _relative_source_path(req_node, file_node_graph)
        assert path == "spec/requirements.md"
