# Validates REQ-d00010-A, REQ-d00010-F, REQ-d00010-G
"""Tests for the Flask trace-edit REST API server.

Validates:
- REQ-d00010-A: Flask app factory pattern
- REQ-d00010-F: CORS enabled for cross-origin requests
- REQ-d00010-G: Static file serving
"""

from pathlib import Path

import pytest

from elspais.graph import GraphNode, NodeKind
from elspais.graph.builder import TraceGraph
from elspais.graph.relations import EdgeKind
from elspais.server.app import create_app

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def sample_graph():
    """Create a sample TraceGraph for testing."""
    graph = TraceGraph(repo_root=Path("/test/repo"))

    # Create PRD requirement with assertions
    prd_node = GraphNode(
        id="REQ-p00001",
        kind=NodeKind.REQUIREMENT,
        label="Platform Security",
    )
    prd_node._content = {
        "level": "PRD",
        "status": "Active",
        "hash": "abc12345",
        "body_text": "Security requirement body text",
    }

    # Add assertions
    assertion_a = GraphNode(
        id="REQ-p00001-A",
        kind=NodeKind.ASSERTION,
        label="SHALL encrypt all data at rest",
    )
    assertion_a._content = {"label": "A"}
    prd_node.add_child(assertion_a)

    assertion_b = GraphNode(
        id="REQ-p00001-B",
        kind=NodeKind.ASSERTION,
        label="SHALL use TLS 1.3 for transit",
    )
    assertion_b._content = {"label": "B"}
    prd_node.add_child(assertion_b)

    # Create OPS requirement that implements PRD
    ops_node = GraphNode(
        id="REQ-o00001",
        kind=NodeKind.REQUIREMENT,
        label="Database Encryption",
    )
    ops_node._content = {
        "level": "OPS",
        "status": "Active",
        "hash": "def67890",
    }

    # Link: ops implements prd
    prd_node.link(ops_node, EdgeKind.IMPLEMENTS)

    # Build graph manually (same pattern as MCP core tests)
    graph._roots = [prd_node]
    graph._index = {
        "REQ-p00001": prd_node,
        "REQ-p00001-A": assertion_a,
        "REQ-p00001-B": assertion_b,
        "REQ-o00001": ops_node,
    }

    return graph


@pytest.fixture
def app(sample_graph):
    """Create Flask test app."""
    application = create_app(
        repo_root=Path("/test/repo"),
        graph=sample_graph,
        config={},
    )
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    """Create Flask test client."""
    return app.test_client()


# ─────────────────────────────────────────────────────────────────────────────
# App Factory Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestAppFactory:
    """Validates REQ-d00010-A: Flask app factory pattern."""

    def test_REQ_d00010_A_create_app_returns_flask_instance(self, sample_graph):
        """App factory returns a Flask application."""
        from flask import Flask

        app = create_app(
            repo_root=Path("/test/repo"),
            graph=sample_graph,
            config={},
        )
        assert isinstance(app, Flask)

    def test_REQ_d00010_A_create_app_accepts_config(self, sample_graph):
        """App factory accepts repo_root, graph, and config arguments."""
        app = create_app(
            repo_root=Path("/another/repo"),
            graph=sample_graph,
            config={"project": {"name": "test"}},
        )
        assert app is not None


# ─────────────────────────────────────────────────────────────────────────────
# GET Endpoint Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestGetStatus:
    """Validates REQ-d00010-A: GET /api/status returns graph status."""

    def test_REQ_d00010_A_status_returns_json(self, client):
        """GET /api/status returns JSON with expected keys."""
        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "root_count" in data
        assert "node_counts" in data
        assert "total_nodes" in data

    def test_REQ_d00010_A_status_contains_node_counts(self, client):
        """Status response includes non-zero node counts."""
        resp = client.get("/api/status")
        data = resp.get_json()
        assert data["root_count"] >= 1
        assert data["total_nodes"] >= 1


class TestGetRequirement:
    """Validates REQ-d00010-A: GET /api/requirement/<req_id>."""

    def test_REQ_d00010_A_requirement_found(self, client):
        """GET /api/requirement returns full requirement data."""
        resp = client.get("/api/requirement/REQ-p00001")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["id"] == "REQ-p00001"
        assert data["title"] == "Platform Security"
        assert data["kind"] == "requirement"
        assert data["properties"]["level"] == "PRD"
        assert data["properties"]["status"] == "Active"
        assert "children" in data

    def test_REQ_d00010_A_requirement_not_found(self, client):
        """GET /api/requirement returns 404 for unknown ID."""
        resp = client.get("/api/requirement/REQ-NOPE")
        assert resp.status_code == 404
        data = resp.get_json()
        assert "error" in data

    def test_REQ_d00010_A_requirement_includes_assertions(self, client):
        """Requirement response includes assertion children."""
        resp = client.get("/api/requirement/REQ-p00001")
        data = resp.get_json()
        assertions = [c for c in data["children"] if c["kind"] == "assertion"]
        assert len(assertions) == 2
        labels = {a["label"] for a in assertions}
        assert labels == {"A", "B"}


class TestGetHierarchy:
    """Validates REQ-d00010-A: GET /api/hierarchy/<req_id>."""

    def test_REQ_d00010_A_hierarchy_found(self, client):
        """GET /api/hierarchy returns ancestors and children."""
        resp = client.get("/api/hierarchy/REQ-p00001")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["id"] == "REQ-p00001"
        assert "ancestors" in data
        assert "children" in data

    def test_REQ_d00010_A_hierarchy_shows_children(self, client):
        """Hierarchy for PRD includes OPS child."""
        resp = client.get("/api/hierarchy/REQ-p00001")
        data = resp.get_json()
        child_ids = [c["id"] for c in data["children"]]
        assert "REQ-o00001" in child_ids

    def test_REQ_d00010_A_hierarchy_not_found(self, client):
        """GET /api/hierarchy returns 404 for unknown ID."""
        resp = client.get("/api/hierarchy/REQ-NOPE")
        assert resp.status_code == 404


class TestGetSearch:
    """Validates REQ-d00010-A: GET /api/search."""

    def test_REQ_d00010_A_search_by_query(self, client):
        """GET /api/search?q=Security returns matching results."""
        resp = client.get("/api/search?q=Security")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["id"] == "REQ-p00001"

    def test_REQ_d00010_A_search_empty_query(self, client):
        """Empty query returns empty list."""
        resp = client.get("/api/search?q=")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data == []

    def test_REQ_d00010_A_search_no_results(self, client):
        """Non-matching query returns empty list."""
        resp = client.get("/api/search?q=zzzznonexistent")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data == []

    def test_REQ_d00010_A_search_with_field(self, client):
        """Search with field parameter narrows results."""
        resp = client.get("/api/search?q=REQ-p00001&field=id")
        data = resp.get_json()
        assert len(data) >= 1


class TestGetTreeData:
    """Validates REQ-d00010-A: GET /api/tree-data."""

    def test_REQ_d00010_A_tree_data_returns_list(self, client):
        """Tree data endpoint returns flat list of rows."""
        resp = client.get("/api/tree-data")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_REQ_d00010_A_tree_data_row_structure(self, client):
        """Each tree row has expected keys."""
        resp = client.get("/api/tree-data")
        data = resp.get_json()
        row = data[0]
        assert "id" in row
        assert "title" in row
        assert "level" in row
        assert "depth" in row
        assert "has_children" in row
        assert "assertions" in row

    def test_REQ_d00010_A_tree_data_hierarchy(self, client):
        """Tree data includes parent-child relationships."""
        resp = client.get("/api/tree-data")
        data = resp.get_json()
        # Root node at depth 0
        roots = [r for r in data if r["depth"] == 0]
        assert len(roots) >= 1
        assert roots[0]["parent_id"] is None
        # Child at depth 1 with parent_id set
        children = [r for r in data if r["depth"] == 1]
        if children:
            assert children[0]["parent_id"] is not None


class TestGetDirty:
    """Validates REQ-d00010-A: GET /api/dirty."""

    def test_REQ_d00010_A_dirty_clean_graph(self, client):
        """Clean graph reports not dirty."""
        resp = client.get("/api/dirty")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["dirty"] is False
        assert data["mutation_count"] == 0

    def test_REQ_d00010_A_dirty_after_mutation(self, client):
        """Graph reports dirty after a mutation."""
        # Perform a mutation
        client.post(
            "/api/mutate/status",
            json={"node_id": "REQ-p00001", "new_status": "Draft"},
        )
        resp = client.get("/api/dirty")
        data = resp.get_json()
        assert data["dirty"] is True
        assert data["mutation_count"] >= 1


class TestGetIndex:
    """Validates REQ-d00010-A: GET / serves template."""

    def test_REQ_d00010_A_index_returns_200(self, client):
        """GET / returns 200 even if template is missing."""
        resp = client.get("/")
        assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# POST Mutation Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestMutateStatus:
    """Validates REQ-d00010-A: POST /api/mutate/status."""

    def test_REQ_d00010_A_change_status_success(self, client):
        """POST /api/mutate/status changes requirement status."""
        resp = client.post(
            "/api/mutate/status",
            json={"node_id": "REQ-p00001", "new_status": "Draft"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "mutation" in data

    def test_REQ_d00010_A_change_status_missing_params(self, client):
        """Missing parameters return 400."""
        resp = client.post(
            "/api/mutate/status",
            json={"node_id": "REQ-p00001"},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["success"] is False

    def test_REQ_d00010_A_change_status_invalid_node(self, client):
        """Non-existent node returns error."""
        resp = client.post(
            "/api/mutate/status",
            json={"node_id": "REQ-NOPE", "new_status": "Draft"},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["success"] is False


class TestMutateTitle:
    """Validates REQ-d00010-A: POST /api/mutate/title."""

    def test_REQ_d00010_A_update_title_success(self, client):
        """POST /api/mutate/title updates requirement title."""
        resp = client.post(
            "/api/mutate/title",
            json={"node_id": "REQ-p00001", "new_title": "Updated Security"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

    def test_REQ_d00010_A_update_title_missing_params(self, client):
        """Missing parameters return 400."""
        resp = client.post(
            "/api/mutate/title",
            json={"node_id": "REQ-p00001"},
        )
        assert resp.status_code == 400


class TestMutateAssertion:
    """Validates REQ-d00010-A: POST /api/mutate/assertion."""

    def test_REQ_d00010_A_update_assertion_success(self, client):
        """POST /api/mutate/assertion updates assertion text."""
        resp = client.post(
            "/api/mutate/assertion",
            json={
                "assertion_id": "REQ-p00001-A",
                "new_text": "SHALL encrypt using AES-256",
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

    def test_REQ_d00010_A_update_assertion_missing_params(self, client):
        """Missing parameters return 400."""
        resp = client.post(
            "/api/mutate/assertion",
            json={"assertion_id": "REQ-p00001-A"},
        )
        assert resp.status_code == 400


class TestMutateAssertionAdd:
    """Validates REQ-d00010-A: POST /api/mutate/assertion/add."""

    def test_REQ_d00010_A_add_assertion_success(self, client):
        """POST /api/mutate/assertion/add creates new assertion."""
        resp = client.post(
            "/api/mutate/assertion/add",
            json={
                "req_id": "REQ-p00001",
                "label": "C",
                "text": "SHALL audit all access",
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

    def test_REQ_d00010_A_add_assertion_missing_params(self, client):
        """Missing parameters return 400."""
        resp = client.post(
            "/api/mutate/assertion/add",
            json={"req_id": "REQ-p00001", "label": "C"},
        )
        assert resp.status_code == 400


class TestMutateEdge:
    """Validates REQ-d00010-A: POST /api/mutate/edge."""

    def test_REQ_d00010_A_edge_add(self, client, sample_graph):
        """Add edge action creates new edge."""
        # First add a DEV requirement to create edge to
        sample_graph.add_requirement(
            req_id="REQ-d00001",
            title="Encryption Module",
            level="DEV",
        )
        resp = client.post(
            "/api/mutate/edge",
            json={
                "action": "add",
                "source_id": "REQ-d00001",
                "target_id": "REQ-o00001",
                "edge_kind": "IMPLEMENTS",
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

    def test_REQ_d00010_A_edge_change_kind(self, client):
        """Change edge kind action modifies existing edge."""
        resp = client.post(
            "/api/mutate/edge",
            json={
                "action": "change_kind",
                "source_id": "REQ-o00001",
                "target_id": "REQ-p00001",
                "new_kind": "REFINES",
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

    def test_REQ_d00010_A_edge_delete(self, client):
        """Delete edge action removes edge."""
        resp = client.post(
            "/api/mutate/edge",
            json={
                "action": "delete",
                "source_id": "REQ-o00001",
                "target_id": "REQ-p00001",
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

    def test_REQ_d00010_A_edge_unknown_action(self, client):
        """Unknown action returns 400."""
        resp = client.post(
            "/api/mutate/edge",
            json={
                "action": "explode",
                "source_id": "REQ-o00001",
                "target_id": "REQ-p00001",
            },
        )
        assert resp.status_code == 400

    def test_REQ_d00010_A_edge_missing_action(self, client):
        """Missing action returns 400."""
        resp = client.post(
            "/api/mutate/edge",
            json={
                "source_id": "REQ-o00001",
                "target_id": "REQ-p00001",
            },
        )
        assert resp.status_code == 400

    def test_REQ_d00010_A_edge_missing_ids(self, client):
        """Missing source/target IDs returns 400."""
        resp = client.post(
            "/api/mutate/edge",
            json={"action": "add"},
        )
        assert resp.status_code == 400


class TestMutateUndo:
    """Validates REQ-d00010-A: POST /api/mutate/undo."""

    def test_REQ_d00010_A_undo_with_no_mutations(self, client):
        """Undo with no mutations returns error."""
        resp = client.post("/api/mutate/undo")
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["success"] is False

    def test_REQ_d00010_A_undo_after_mutation(self, client):
        """Undo after mutation reverses it."""
        # Perform a mutation
        client.post(
            "/api/mutate/status",
            json={"node_id": "REQ-p00001", "new_status": "Draft"},
        )
        # Undo it
        resp = client.post("/api/mutate/undo")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Persistence Stub Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestPersistenceEndpoints:
    """Validates REQ-d00010-A: Persistence endpoints (save, revert, reload)."""

    def test_REQ_d00010_A_save_empty_log_succeeds(self, client):
        """POST /api/save with no pending mutations returns success."""
        resp = client.post("/api/save")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["saved_count"] == 0

    def test_REQ_d00010_A_revert_returns_result(self, client):
        """POST /api/revert attempts graph rebuild."""
        resp = client.post("/api/revert")
        # May succeed or fail depending on config; either way returns JSON
        data = resp.get_json()
        assert "success" in data

    def test_REQ_d00010_A_reload_returns_result(self, client):
        """POST /api/reload attempts graph rebuild."""
        resp = client.post("/api/reload")
        # May succeed or fail depending on config; either way returns JSON
        data = resp.get_json()
        assert "success" in data


# ─────────────────────────────────────────────────────────────────────────────
# File Content API Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestGetFileContent:
    """Validates REQ-p00006-A: /api/file-content with syntax highlighting."""

    def test_REQ_p00006_A_file_content_returns_highlighted_lines(self, tmp_path):
        """API returns highlighted_lines and language for a Python file."""
        graph = TraceGraph(repo_root=tmp_path)
        app = create_app(repo_root=tmp_path, graph=graph, config={})
        app.config["TESTING"] = True

        py_file = tmp_path / "example.py"
        py_file.write_text("def foo():\n    return 42\n")

        with app.test_client() as c:
            resp = c.get("/api/file-content?path=example.py")
            assert resp.status_code == 200
            data = resp.get_json()
            assert "highlighted_lines" in data
            assert "language" in data
            assert "lines" in data
            assert data["language"] == "python"
            # highlighted_lines should contain Pygments spans
            assert any("<span" in line for line in data["highlighted_lines"])
            # plain lines should be raw text
            assert data["lines"][0] == "def foo():"

    def test_REQ_p00006_A_file_content_mutation_tracking(self, tmp_path):
        """API still returns mutation tracking alongside highlighting."""
        graph = TraceGraph(repo_root=tmp_path)
        app = create_app(repo_root=tmp_path, graph=graph, config={})
        app.config["TESTING"] = True

        md_file = tmp_path / "README.md"
        md_file.write_text("# Hello\n\nWorld\n")

        with app.test_client() as c:
            resp = c.get("/api/file-content?path=README.md")
            assert resp.status_code == 200
            data = resp.get_json()
            assert "has_pending_mutations" in data
            assert "pending_mutation_count" in data
            assert "affected_nodes" in data
            assert "mtime" in data
            assert data["has_pending_mutations"] is False

    def test_REQ_p00006_A_file_content_missing_path(self, client):
        """Missing path parameter returns 400."""
        resp = client.get("/api/file-content")
        assert resp.status_code == 400

    def test_REQ_p00006_A_file_content_not_found(self, client):
        """Non-existent file returns 404."""
        resp = client.get("/api/file-content?path=nonexistent.py")
        assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# CORS Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestCors:
    """Validates REQ-d00010-F: CORS enabled for cross-origin requests."""

    def test_REQ_d00010_F_cors_headers_present(self, client):
        """Response includes CORS Access-Control-Allow-Origin header."""
        resp = client.get("/api/status", headers={"Origin": "http://localhost:3000"})
        assert resp.status_code == 200
        # flask-cors adds Access-Control-Allow-Origin header
        assert "Access-Control-Allow-Origin" in resp.headers

    def test_REQ_d00010_F_cors_preflight(self, client):
        """OPTIONS preflight request returns CORS headers."""
        resp = client.options(
            "/api/status",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code == 200
        assert "Access-Control-Allow-Origin" in resp.headers


# ─────────────────────────────────────────────────────────────────────────────
# Generic Node API Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestGetNode:
    """Validates REQ-d00010-A: GET /api/node/<node_id> generic endpoint."""

    def test_REQ_d00010_A_node_requirement(self, client):
        """Fetch a requirement node, verify kind and properties."""
        resp = client.get("/api/node/REQ-p00001")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["id"] == "REQ-p00001"
        assert data["kind"] == "requirement"
        assert data["properties"]["level"] == "PRD"
        assert data["properties"]["status"] == "Active"

    def test_REQ_d00010_A_node_not_found(self, client):
        """Verify 404 for a non-existent node ID."""
        resp = client.get("/api/node/NONEXISTENT-ID")
        assert resp.status_code == 404
        data = resp.get_json()
        assert "error" in data

    def test_REQ_d00010_A_node_assertion(self, client):
        """Fetch an assertion node, verify kind and label property."""
        resp = client.get("/api/node/REQ-p00001-A")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["id"] == "REQ-p00001-A"
        assert data["kind"] == "assertion"
        assert data["properties"]["label"] == "A"

    def test_REQ_d00010_A_node_common_envelope(self, client):
        """Verify all common envelope fields are present in node response."""
        resp = client.get("/api/node/REQ-p00001")
        assert resp.status_code == 200
        data = resp.get_json()
        expected_keys = {
            "id",
            "kind",
            "title",
            "source",
            "keywords",
            "parents",
            "children",
            "links",
            "properties",
        }
        assert expected_keys.issubset(set(data.keys()))

    def test_REQ_d00010_A_node_journey(self, client, sample_graph):
        """Fetch a USER_JOURNEY node, verify kind and actor property."""
        journey = GraphNode(
            id="JNY-Login-01", kind=NodeKind.USER_JOURNEY, label="User Login Journey"
        )
        journey._content = {"actor": "End User", "goal": "Log into the system"}
        sample_graph._index["JNY-Login-01"] = journey

        resp = client.get("/api/node/JNY-Login-01")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["id"] == "JNY-Login-01"
        assert data["kind"] == "journey"
        assert data["properties"]["actor"] == "End User"
        assert data["properties"]["goal"] == "Log into the system"


# ─────────────────────────────────────────────────────────────────────────────
# Query Endpoint Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestApiQuery:
    """Validates REQ-d00010-A: GET /api/query combined filter endpoint."""

    def test_REQ_d00010_A_query_by_kind(self, client):
        """Filter by kind=requirement returns only requirement nodes."""
        resp = client.get("/api/query?kind=requirement")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["count"] >= 1
        for result in data["results"]:
            assert result["kind"] == "requirement"

    def test_REQ_d00010_A_query_by_level(self, client):
        """Filter by kind=requirement&level=PRD returns only PRD requirements."""
        resp = client.get("/api/query?kind=requirement&level=PRD")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["count"] >= 1
        for result in data["results"]:
            assert result["kind"] == "requirement"
            assert result["level"] == "PRD"

    def test_REQ_d00010_A_query_empty(self, client):
        """Non-existent level filter returns empty results."""
        resp = client.get("/api/query?kind=requirement&level=NONEXISTENT")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["count"] == 0
        assert data["results"] == []

    def test_REQ_d00010_A_query_limit(self, client):
        """Limit parameter restricts result count."""
        resp = client.get("/api/query?kind=requirement&limit=1")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["results"]) <= 1

    def test_REQ_d00010_A_query_no_params(self, client):
        """No query params returns all nodes in the graph."""
        resp = client.get("/api/query")
        assert resp.status_code == 200
        data = resp.get_json()
        # Graph has at least 4 nodes: 2 requirements + 2 assertions
        assert data["count"] >= 4


# ─────────────────────────────────────────────────────────────────────────────
# Tree Data Journey Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestTreeDataJourneys:
    """Validates REQ-d00010-A: Journey nodes in tree-data endpoint."""

    def test_REQ_d00010_A_tree_data_includes_journeys(self, client, sample_graph):
        """Journey nodes appear in tree-data with kind=journey and is_journey=True."""
        journey = GraphNode(id="JNY-Browse-01", kind=NodeKind.USER_JOURNEY, label="Browse Catalog")
        journey._content = {"actor": "Shopper", "goal": "Find products"}
        sample_graph._index["JNY-Browse-01"] = journey

        resp = client.get("/api/tree-data")
        assert resp.status_code == 200
        data = resp.get_json()

        journey_rows = [r for r in data if r.get("id") == "JNY-Browse-01"]
        assert len(journey_rows) == 1

        row = journey_rows[0]
        assert row["kind"] == "journey"
        assert row["is_journey"] is True
        assert row["title"] == "Browse Catalog"
        assert row["actor"] == "Shopper"
        assert row["goal"] == "Find products"


# ─────────────────────────────────────────────────────────────────────────────
# CLI Wiring Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestCLIWiring:
    """Validates REQ-d00010-A: CLI --server and --edit-mode wiring."""

    def test_REQ_d00010_A_review_mode_still_not_implemented(self):
        """--review-mode still returns error code 1."""
        import argparse

        from elspais.commands.trace import run

        args = argparse.Namespace(
            review_mode=True,
            edit_mode=False,
            server=False,
            view=False,
            graph_json=False,
            format="markdown",
            report=None,
            output=None,
            spec_dir=None,
            config=None,
            quiet=True,
            embed_content=False,
        )
        result = run(args)
        assert result == 1

    def test_REQ_d00010_A_server_flag_calls_run_server(self):
        """--server flag delegates to _run_server."""
        import argparse
        from unittest.mock import patch

        from elspais.commands.trace import run

        args = argparse.Namespace(
            review_mode=False,
            edit_mode=False,
            server=True,
            view=False,
            graph_json=False,
            format="markdown",
            report=None,
            output=None,
            spec_dir=None,
            config=None,
            quiet=True,
            embed_content=False,
        )
        with patch("elspais.commands.trace._run_server", return_value=0) as mock:
            result = run(args)
            assert result == 0
            mock.assert_called_once_with(args, open_browser=False)

    def test_REQ_d00010_A_edit_mode_flag_calls_run_server_with_browser(self):
        """--edit-mode flag delegates to _run_server with open_browser=True."""
        import argparse
        from unittest.mock import patch

        from elspais.commands.trace import run

        args = argparse.Namespace(
            review_mode=False,
            edit_mode=True,
            server=False,
            view=False,
            graph_json=False,
            format="markdown",
            report=None,
            output=None,
            spec_dir=None,
            config=None,
            quiet=True,
            embed_content=False,
        )
        with patch("elspais.commands.trace._run_server", return_value=0) as mock:
            result = run(args)
            assert result == 0
            mock.assert_called_once_with(args, open_browser=True)
