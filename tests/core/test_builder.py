"""Tests for Graph Builder - builds TraceGraph from parsed content."""

import pytest

from elspais.graph import GraphNode, NodeKind, Edge, EdgeKind
from elspais.graph.builder import GraphBuilder, TraceGraph
from elspais.graph.parsers import ParsedContent
from tests.core.graph_test_helpers import (
    build_graph,
    children_string,
    make_code_ref,
    make_journey,
    make_requirement,
    make_test_ref,
    outgoing_edges_string,
    parents_string,
)


@pytest.fixture
def sample_requirements():
    """Sample parsed requirement content."""
    return [
        ParsedContent(
            content_type="requirement",
            start_line=1,
            end_line=10,
            raw_text="...",
            parsed_data={
                "id": "REQ-p00001",
                "title": "User Auth",
                "level": "PRD",
                "status": "Active",
                "implements": [],
                "assertions": [
                    {"label": "A", "text": "Users can log in"},
                    {"label": "B", "text": "Users can reset password"},
                ],
            },
        ),
        ParsedContent(
            content_type="requirement",
            start_line=15,
            end_line=25,
            raw_text="...",
            parsed_data={
                "id": "REQ-o00001",
                "title": "Login Form",
                "level": "OPS",
                "status": "Active",
                "implements": ["REQ-p00001-A"],
                "assertions": [],
            },
        ),
    ]


class TestGraphBuilder:
    """Tests for GraphBuilder class."""

    def test_build_creates_nodes(self, sample_requirements):
        builder = GraphBuilder()

        for req in sample_requirements:
            builder.add_parsed_content(req)

        graph = builder.build()

        assert graph.find_by_id("REQ-p00001") is not None
        assert graph.find_by_id("REQ-o00001") is not None

    def test_build_creates_assertion_nodes(self, sample_requirements):
        builder = GraphBuilder()

        for req in sample_requirements:
            builder.add_parsed_content(req)

        graph = builder.build()

        assert graph.find_by_id("REQ-p00001-A") is not None
        assert graph.find_by_id("REQ-p00001-B") is not None

    def test_build_links_assertions_to_parent(self, sample_requirements):
        builder = GraphBuilder()

        for req in sample_requirements:
            builder.add_parsed_content(req)

        graph = builder.build()

        parent = graph.find_by_id("REQ-p00001")
        assertion_a = graph.find_by_id("REQ-p00001-A")

        assert "REQ-p00001-A" in children_string(parent)
        assert "REQ-p00001" in parents_string(assertion_a)

    def test_build_creates_implements_edges(self, sample_requirements):
        builder = GraphBuilder()

        for req in sample_requirements:
            builder.add_parsed_content(req)

        graph = builder.build()

        ops_req = graph.find_by_id("REQ-o00001")
        prd_req = graph.find_by_id("REQ-p00001")

        # OPS req should be child of parent REQ (not assertion node)
        # with assertion_targets indicating which assertions it implements
        assert "REQ-p00001" in parents_string(ops_req)

        # Verify the edge has assertion_targets set
        for edge in prd_req.iter_outgoing_edges():
            if edge.target.id == "REQ-o00001":
                assert edge.assertion_targets == ["A"]
                break
        else:
            pytest.fail("Expected edge from REQ-p00001 to REQ-o00001 not found")

    def test_roots_are_top_level_requirements(self, sample_requirements):
        builder = GraphBuilder()

        for req in sample_requirements:
            builder.add_parsed_content(req)

        graph = builder.build()

        assert graph.has_root("REQ-p00001")
        assert not graph.has_root("REQ-o00001")  # Has parent via implements


class TestTraceGraph:
    """Tests for TraceGraph container."""

    def test_find_by_id(self, sample_requirements):
        builder = GraphBuilder()
        for req in sample_requirements:
            builder.add_parsed_content(req)
        graph = builder.build()

        node = graph.find_by_id("REQ-p00001")

        assert node is not None
        assert node.id == "REQ-p00001"

    def test_find_by_id_not_found(self, sample_requirements):
        builder = GraphBuilder()
        for req in sample_requirements:
            builder.add_parsed_content(req)
        graph = builder.build()

        node = graph.find_by_id("NONEXISTENT")

        assert node is None

    def test_all_nodes_iterator(self, sample_requirements):
        builder = GraphBuilder()
        for req in sample_requirements:
            builder.add_parsed_content(req)
        graph = builder.build()

        all_nodes = list(graph.all_nodes())

        # 2 reqs + 2 assertions = 4 nodes exactly
        assert len(all_nodes) == 4

    def test_nodes_by_kind(self, sample_requirements):
        builder = GraphBuilder()
        for req in sample_requirements:
            builder.add_parsed_content(req)
        graph = builder.build()

        assertions = list(graph.nodes_by_kind(NodeKind.ASSERTION))

        assert len(assertions) == 2


class TestBuilderContentTypes:
    """Tests for builder handling different content types."""

    def test_build_creates_journey_nodes(self):
        """Builder creates USER_JOURNEY nodes from journey content."""
        graph = build_graph(
            make_journey("UJ-001", title="Login Flow", actor="User", goal="Sign in"),
        )

        node = graph.find_by_id("UJ-001")
        assert node is not None
        assert node.kind == NodeKind.USER_JOURNEY
        assert node.label == "Login Flow"

    def test_build_creates_code_ref_nodes(self):
        """Builder creates CODE nodes from code_ref content."""
        graph = build_graph(
            make_requirement("REQ-d00001", level="DEV"),
            make_code_ref(["REQ-d00001"], source_path="src/auth.py", start_line=10),
        )

        # Code ref creates a node linked to the requirement
        req = graph.find_by_id("REQ-d00001")
        assert "code:src/auth.py:10" in children_string(req)

        code_node = graph.find_by_id("code:src/auth.py:10")
        assert code_node is not None
        assert code_node.kind == NodeKind.CODE

    def test_build_creates_test_ref_nodes(self):
        """Builder creates TEST nodes from test_ref content."""
        graph = build_graph(
            make_requirement("REQ-d00001", level="DEV"),
            make_test_ref(["REQ-d00001"], source_path="tests/test_auth.py", start_line=5),
        )

        # Test ref creates a node linked to the requirement
        req = graph.find_by_id("REQ-d00001")
        assert "test:tests/test_auth.py:5" in children_string(req)

        test_node = graph.find_by_id("test:tests/test_auth.py:5")
        assert test_node is not None
        assert test_node.kind == NodeKind.TEST

    def test_build_creates_refines_edges(self):
        """Builder creates REFINES edges from refines references."""
        graph = build_graph(
            make_requirement("REQ-p00001", level="PRD"),
            make_requirement("REQ-p00002", level="PRD", refines=["REQ-p00001"]),
        )

        parent = graph.find_by_id("REQ-p00001")
        child = graph.find_by_id("REQ-p00002")

        # Verify refines edge exists
        assert "REQ-p00002" in children_string(parent)
        assert "REQ-p00001->REQ-p00002:refines" in outgoing_edges_string(parent)

    def test_build_ignores_missing_targets(self):
        """Builder handles references to non-existent targets gracefully."""
        # This should not raise an error
        graph = build_graph(
            make_requirement("REQ-o00001", level="OPS", implements=["REQ-NONEXISTENT"]),
        )

        req = graph.find_by_id("REQ-o00001")
        assert req is not None
        # Node should be a root since its parent doesn't exist
        assert graph.has_root("REQ-o00001")

    def test_node_content_fields_accessible(self):
        """Node content fields are accessible via get_field()."""
        graph = build_graph(
            make_requirement(
                "REQ-p00001",
                title="Authentication",
                level="PRD",
                status="Active",
                hash_value="abc12345",
            ),
        )

        node = graph.find_by_id("REQ-p00001")

        # Content fields accessible via public API
        assert node.get_field("level") == "PRD"
        assert node.get_field("status") == "Active"
        assert node.get_field("hash") == "abc12345"
        # Convenience properties work too
        assert node.level == "PRD"
        assert node.status == "Active"
        assert node.hash == "abc12345"
