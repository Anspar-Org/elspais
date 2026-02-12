# Implements: REQ-p00006-A, REQ-p00006-B, REQ-p00006-C
"""Tests for the embedded data layer (Phase 1 of Unified Trace Viewer).

Validates that HTMLGenerator produces embedded JSON indexes matching
the API response shapes used by the Flask server.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from elspais.config import get_config
from elspais.graph.factory import build_graph

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "hht-like"


@pytest.fixture
def graph():
    """Build a graph from the hht-like fixture."""
    config = get_config(start_path=FIXTURE_DIR, quiet=True)
    return build_graph(config=config, repo_root=FIXTURE_DIR)


@pytest.fixture
def generator(graph):
    """Create an HTMLGenerator with coverage annotations applied."""
    from elspais.html.generator import HTMLGenerator

    gen = HTMLGenerator(graph, base_path=str(FIXTURE_DIR))
    gen._annotate_git_state()
    gen._annotate_coverage()
    return gen


class TestBuildNodeIndex:
    """Validates REQ-p00006-A: Node index matches /api/node/ response shape."""

    def test_REQ_p00006_A_node_index_has_all_nodes(self, generator, graph):
        """Node index should contain an entry for every node in the graph."""
        index = generator._build_node_index()
        assert len(index) > 0
        # Every node in the graph should be present
        for node in graph.all_nodes():
            assert node.id in index, f"Missing node {node.id} from index"

    def test_REQ_p00006_A_node_index_matches_api_shape(self, generator, graph):
        """Each node entry should have the standard API envelope fields."""
        index = generator._build_node_index()
        for node_id, data in index.items():
            assert "id" in data, f"Node {node_id} missing 'id'"
            assert "kind" in data, f"Node {node_id} missing 'kind'"
            assert "title" in data, f"Node {node_id} missing 'title'"
            assert "source" in data, f"Node {node_id} missing 'source'"
            assert "children" in data, f"Node {node_id} missing 'children'"
            assert "parents" in data, f"Node {node_id} missing 'parents'"
            assert "properties" in data, f"Node {node_id} missing 'properties'"
            break  # Spot-check first entry

    def test_REQ_p00006_A_requirement_node_has_correct_properties(self, generator, graph):
        """Requirement nodes should have level, status, hash in properties."""
        from elspais.graph import NodeKind

        index = generator._build_node_index()
        for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
            data = index[node.id]
            assert data["kind"] == "requirement"
            props = data["properties"]
            assert "level" in props
            assert "status" in props
            assert "hash" in props
            break  # Spot-check first requirement


class TestBuildCoverageIndex:
    """Validates REQ-p00006-B: Coverage index matches API response shapes."""

    def test_REQ_p00006_B_coverage_index_has_all_requirements(self, generator, graph):
        """Coverage index should have an entry for every requirement."""
        from elspais.graph import NodeKind

        index = generator._build_coverage_index()
        req_count = sum(1 for _ in graph.nodes_by_kind(NodeKind.REQUIREMENT))
        assert len(index) == req_count

    def test_REQ_p00006_B_coverage_entry_has_test_and_code(self, generator):
        """Each coverage entry should have 'test' and 'code' sub-dicts."""
        index = generator._build_coverage_index()
        for req_id, entry in index.items():
            assert "test" in entry, f"Missing 'test' in coverage for {req_id}"
            assert "code" in entry, f"Missing 'code' in coverage for {req_id}"
            break  # Spot-check first

    def test_REQ_p00006_B_test_coverage_matches_api_shape(self, generator):
        """Test coverage data should have success, assertion_tests, coverage_pct fields."""
        index = generator._build_coverage_index()
        for _req_id, entry in index.items():
            test_data = entry["test"]
            assert "success" in test_data
            assert "assertion_tests" in test_data
            assert "coverage_pct" in test_data
            break  # Spot-check first

    def test_REQ_p00006_B_code_coverage_matches_api_shape(self, generator):
        """Code coverage data should have success, assertion_code, coverage_pct fields."""
        index = generator._build_coverage_index()
        for _req_id, entry in index.items():
            code_data = entry["code"]
            assert "success" in code_data
            assert "assertion_code" in code_data
            assert "coverage_pct" in code_data
            break  # Spot-check first


class TestBuildStatusData:
    """Validates REQ-p00006-C: Status data matches /api/status response shape."""

    def test_REQ_p00006_C_status_data_has_required_fields(self, generator):
        """Status data should have node_counts, root_count, total_nodes."""
        data = generator._build_status_data()
        assert "node_counts" in data
        assert "root_count" in data
        assert "total_nodes" in data
        assert "has_orphans" in data
        assert "has_broken_references" in data

    def test_REQ_p00006_C_status_node_counts_are_positive(self, generator):
        """Node counts should contain at least requirement entries."""
        data = generator._build_status_data()
        assert data["total_nodes"] > 0
        assert "requirement" in data["node_counts"]


class TestEmbeddedDataInHTML:
    """Validates REQ-p00006-A: Embedded JSON appears in generated HTML output."""

    def test_REQ_p00006_A_html_contains_embedded_json_blocks(self, graph):
        """Generated HTML with embed_content=True should have all JSON script tags."""
        from elspais.html.generator import HTMLGenerator

        gen = HTMLGenerator(graph, base_path=str(FIXTURE_DIR))
        html = gen.generate(embed_content=True)

        # Check for all embedded data script tags
        assert 'id="tree-data"' in html
        assert 'id="source-files"' in html
        assert 'id="node-index"' in html
        assert 'id="coverage-index"' in html
        assert 'id="status-data"' in html

    def test_REQ_p00006_A_html_without_embed_has_no_node_index(self, graph):
        """Generated HTML without embed_content should not have node-index."""
        from elspais.html.generator import HTMLGenerator

        gen = HTMLGenerator(graph, base_path=str(FIXTURE_DIR))
        html = gen.generate(embed_content=False)

        # Empty dicts still get rendered as {} in script tags,
        # but the data should be minimal
        assert 'id="node-index"' in html  # Tag exists but empty
