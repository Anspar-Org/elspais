"""Tests for Graph Builder - builds TraceGraph from parsed content."""

import pytest

from elspais.graph import GraphNode, NodeKind, Edge, EdgeKind
from elspais.graph.builder import GraphBuilder, TraceGraph
from elspais.graph.parsers import ParsedContent
from tests.core.graph_test_helpers import children_string, parents_string


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

        # OPS req should implement assertion A
        assert "REQ-p00001-A" in parents_string(ops_req)

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

        # 2 reqs + 2 assertions = 4 nodes minimum
        assert len(all_nodes) >= 4

    def test_nodes_by_kind(self, sample_requirements):
        builder = GraphBuilder()
        for req in sample_requirements:
            builder.add_parsed_content(req)
        graph = builder.build()

        assertions = list(graph.nodes_by_kind(NodeKind.ASSERTION))

        assert len(assertions) == 2
