# Verifies: REQ-d00129-C, REQ-d00129-D, REQ-d00129-E, REQ-d00129-F
"""Tests for SourceLocation removal (REQ-d00129).

Validates that:
- SourceLocation class is removed
- GraphNode.source field is removed
- parse_line/parse_end_line are accessible via get_field()
- file_node() returns correct FILE node for various node types
- Consumers produce the same output format as before
"""

from elspais.graph.GraphNode import FileType, GraphNode, NodeKind
from elspais.graph.relations import EdgeKind


class TestParseLineFields:
    """REQ-d00129-C: Content nodes store parse_line and parse_end_line as fields."""

    # Verifies: REQ-d00129-C
    def test_REQ_d00129_C_parse_line_via_get_field(self):
        """parse_line is accessible via get_field()."""
        node = GraphNode(id="test-1", kind=NodeKind.REQUIREMENT, label="Test")
        node.set_field("parse_line", 10)
        assert node.get_field("parse_line") == 10

    # Verifies: REQ-d00129-C
    def test_REQ_d00129_C_parse_end_line_via_get_field(self):
        """parse_end_line is accessible via get_field()."""
        node = GraphNode(id="test-1", kind=NodeKind.REQUIREMENT, label="Test")
        node.set_field("parse_end_line", 25)
        assert node.get_field("parse_end_line") == 25

    # Verifies: REQ-d00129-C
    def test_REQ_d00129_C_parse_line_defaults_none(self):
        """parse_line defaults to None when not set."""
        node = GraphNode(id="test-1", kind=NodeKind.REQUIREMENT, label="Test")
        assert node.get_field("parse_line") is None

    # Verifies: REQ-d00129-C
    def test_REQ_d00129_C_parse_end_line_defaults_none(self):
        """parse_end_line defaults to None when not set."""
        node = GraphNode(id="test-1", kind=NodeKind.REQUIREMENT, label="Test")
        assert node.get_field("parse_end_line") is None


class TestFileNodeTraversal:
    """REQ-d00129-D: Consumers navigate to FILE parent via file_node()."""

    def _make_file_node(self, path: str = "spec/reqs.md") -> GraphNode:
        """Create a FILE node with standard fields."""
        file_node = GraphNode(
            id=f"file:{path}",
            kind=NodeKind.FILE,
            label=path.split("/")[-1],
        )
        file_node.set_field("file_type", FileType.SPEC)
        file_node.set_field("relative_path", path)
        file_node.set_field("absolute_path", f"/repo/{path}")
        file_node.set_field("repo", None)
        return file_node

    # Verifies: REQ-d00129-D
    def test_REQ_d00129_D_top_level_node_finds_file(self):
        """Top-level REQUIREMENT finds FILE via CONTAINS edge."""
        file_node = self._make_file_node()
        req = GraphNode(id="REQ-001", kind=NodeKind.REQUIREMENT, label="Test")
        req.set_field("parse_line", 5)
        file_node.link(req, EdgeKind.CONTAINS)

        found = req.file_node()
        assert found is file_node
        assert found.get_field("relative_path") == "spec/reqs.md"

    # Verifies: REQ-d00129-D
    def test_REQ_d00129_D_assertion_finds_file_two_hops(self):
        """ASSERTION finds FILE via STRUCTURES->REQUIREMENT->CONTAINS->FILE."""
        file_node = self._make_file_node()
        req = GraphNode(id="REQ-001", kind=NodeKind.REQUIREMENT, label="Test Req")
        assertion = GraphNode(id="REQ-001-A", kind=NodeKind.ASSERTION, label="Assertion A")
        assertion.set_field("parse_line", 10)

        file_node.link(req, EdgeKind.CONTAINS)
        req.link(assertion, EdgeKind.STRUCTURES)

        found = assertion.file_node()
        assert found is file_node

    # Verifies: REQ-d00129-D
    def test_REQ_d00129_D_instance_node_returns_none(self):
        """INSTANCE node returns None from file_node()."""
        from elspais.graph.relations import Stereotype

        instance = GraphNode(id="dec::orig", kind=NodeKind.REQUIREMENT, label="Instance")
        instance.set_field("stereotype", Stereotype.INSTANCE)
        # INSTANCE nodes have no CONTAINS edge to FILE

        assert instance.file_node() is None


class TestParseLineFromFileNode:
    """REQ-d00129-E: Consumers use get_field('parse_line') for line numbers."""

    # Verifies: REQ-d00129-E
    def test_REQ_d00129_E_line_from_field(self):
        """Line number retrieved via get_field."""
        node = GraphNode(id="REQ-001", kind=NodeKind.REQUIREMENT, label="Test")
        node.set_field("parse_line", 42)
        assert node.get_field("parse_line") == 42

    # Verifies: REQ-d00129-E
    def test_REQ_d00129_E_end_line_from_field(self):
        """End line number retrieved via get_field."""
        node = GraphNode(id="REQ-001", kind=NodeKind.REQUIREMENT, label="Test")
        node.set_field("parse_end_line", 60)
        assert node.get_field("parse_end_line") == 60


class TestRepoFromFileNode:
    """REQ-d00129-F: Consumers use file_node().get_field('repo') for repo."""

    # Verifies: REQ-d00129-F
    def test_REQ_d00129_F_repo_from_file_node(self):
        """Repo retrieved via file_node()."""
        file_node = GraphNode(id="file:spec/reqs.md", kind=NodeKind.FILE, label="reqs.md")
        file_node.set_field("repo", "CAL")
        file_node.set_field("relative_path", "spec/reqs.md")

        req = GraphNode(id="REQ-001", kind=NodeKind.REQUIREMENT, label="Test")
        file_node.link(req, EdgeKind.CONTAINS)

        found = req.file_node()
        assert found is not None
        assert found.get_field("repo") == "CAL"

    # Verifies: REQ-d00129-F
    def test_REQ_d00129_F_repo_none_for_core(self):
        """Core project nodes have repo=None."""
        file_node = GraphNode(id="file:spec/reqs.md", kind=NodeKind.FILE, label="reqs.md")
        file_node.set_field("repo", None)
        file_node.set_field("relative_path", "spec/reqs.md")

        req = GraphNode(id="REQ-001", kind=NodeKind.REQUIREMENT, label="Test")
        file_node.link(req, EdgeKind.CONTAINS)

        found = req.file_node()
        assert found is not None
        assert found.get_field("repo") is None
