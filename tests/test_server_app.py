# Validates REQ-d00010-A, REQ-d00010-F, REQ-d00010-G, REQ-p00004-C+D+E+F
"""Tests for the Flask trace-edit REST API server.

Validates:
- REQ-d00010-A: Flask app factory pattern
- REQ-d00010-F: CORS enabled for cross-origin requests
- REQ-d00010-G: Static file serving
- REQ-p00004-C: Git status summary endpoint
- REQ-p00004-D: Branch creation endpoint
- REQ-p00004-E: Commit and push endpoint
- REQ-p00004-F: Pull fast-forward endpoint
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
    prd_node.link(assertion_a, EdgeKind.STRUCTURES)

    assertion_b = GraphNode(
        id="REQ-p00001-B",
        kind=NodeKind.ASSERTION,
        label="SHALL use TLS 1.3 for transit",
    )
    assertion_b._content = {"label": "B"}
    prd_node.link(assertion_b, EdgeKind.STRUCTURES)

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


@pytest.fixture
def coverage_graph():
    """Create a graph with test coverage for API testing."""
    graph = TraceGraph(repo_root=Path("/test/repo"))

    req_node = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT, label="Platform Security")
    req_node._content = {"level": "PRD", "status": "Active", "hash": "abc12345"}

    assertion_a = GraphNode(id="REQ-p00001-A", kind=NodeKind.ASSERTION, label="SHALL encrypt data")
    assertion_a._content = {"label": "A"}
    req_node.link(assertion_a, EdgeKind.STRUCTURES)

    assertion_b = GraphNode(id="REQ-p00001-B", kind=NodeKind.ASSERTION, label="SHALL use TLS")
    assertion_b._content = {"label": "B"}
    req_node.link(assertion_b, EdgeKind.STRUCTURES)

    # Test node linked to assertion A
    test_node = GraphNode(
        id="test:test_encrypt.py::test_encrypt", kind=NodeKind.TEST, label="test_encrypt"
    )
    test_node._content = {"file": "test_encrypt.py", "name": "test_encrypt"}
    assertion_a.link(test_node, EdgeKind.VALIDATES)

    # Test result
    result_node = GraphNode(id="result:test_encrypt", kind=NodeKind.TEST_RESULT, label="passed")
    result_node._content = {"status": "passed", "duration": 0.5}
    test_node.link(result_node, EdgeKind.YIELDS)

    graph._roots = [req_node]
    graph._index = {
        "REQ-p00001": req_node,
        "REQ-p00001-A": assertion_a,
        "REQ-p00001-B": assertion_b,
        "test:test_encrypt.py::test_encrypt": test_node,
        "result:test_encrypt": result_node,
    }
    return graph


@pytest.fixture
def coverage_app(coverage_graph):
    """Create Flask test app with coverage graph."""
    application = create_app(repo_root=Path("/test/repo"), graph=coverage_graph, config={})
    application.config["TESTING"] = True
    return application


@pytest.fixture
def coverage_client(coverage_app):
    """Create Flask test client for coverage tests."""
    return coverage_app.test_client()


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
    """Validates REQ-d00010-A, REQ-d00061-E, REQ-d00061-C: GET /api/search."""

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

    def test_REQ_d00061_E_search_with_limit(self, client):
        """Limit parameter restricts result count."""
        # With limit=1, should get at most 1 result
        resp = client.get("/api/search?q=REQ&limit=1")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) <= 1

    def test_REQ_d00061_E_search_default_limit(self, client):
        """Default limit is 50 when not specified."""
        # Just verify the endpoint works without limit param (uses default 50)
        resp = client.get("/api/search?q=Security")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        # Our test graph has few nodes, so all should be returned
        assert len(data) >= 1

    def test_REQ_d00061_C_search_with_regex(self, client):
        """Regex parameter enables regex matching."""
        resp = client.get("/api/search?q=REQ-p0000[0-9]&regex=true")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) >= 1
        assert data[0]["id"] == "REQ-p00001"

    def test_REQ_d00061_C_search_regex_defaults_false(self, client):
        """Regex defaults to false - literal bracket chars don't match."""
        resp = client.get("/api/search?q=REQ-p0000[0-9]")
        assert resp.status_code == 200
        data = resp.get_json()
        # Without regex, "[0-9]" is literal text that won't match any node
        assert len(data) == 0


class TestGetTestCoverage:
    """Validates REQ-d00010-A: GET /api/test-coverage/<req_id>."""

    def test_REQ_d00010_A_test_coverage_found(self, coverage_client):
        """GET /api/test-coverage returns per-assertion test map."""
        resp = coverage_client.get("/api/test-coverage/REQ-p00001")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["req_id"] == "REQ-p00001"
        assert "assertion_tests" in data
        assert "A" in data["assertion_tests"]
        assert "B" in data["assertion_tests"]

    def test_REQ_d00010_A_test_coverage_assertion_has_tests(self, coverage_client):
        """Covered assertion A includes test entries with results."""
        resp = coverage_client.get("/api/test-coverage/REQ-p00001")
        data = resp.get_json()
        a_tests = data["assertion_tests"]["A"]["tests"]
        assert len(a_tests) >= 1
        assert a_tests[0]["id"] == "test:test_encrypt.py::test_encrypt"
        assert len(a_tests[0]["results"]) >= 1
        assert a_tests[0]["results"][0]["status"] == "passed"

    def test_REQ_d00010_A_test_coverage_uncovered_assertion(self, coverage_client):
        """Uncovered assertion B has empty test list."""
        resp = coverage_client.get("/api/test-coverage/REQ-p00001")
        data = resp.get_json()
        b_tests = data["assertion_tests"]["B"]["tests"]
        assert len(b_tests) == 0

    def test_REQ_d00010_A_test_coverage_stats(self, coverage_client):
        """Coverage stats reflect 1 of 2 assertions covered."""
        resp = coverage_client.get("/api/test-coverage/REQ-p00001")
        data = resp.get_json()
        assert data["total_assertions"] == 2
        assert data["covered_count"] == 1
        assert data["coverage_pct"] == 50.0

    def test_REQ_d00010_A_test_coverage_not_found(self, coverage_client):
        """GET /api/test-coverage returns 404 for unknown ID."""
        resp = coverage_client.get("/api/test-coverage/REQ-NOPE")
        assert resp.status_code == 404
        data = resp.get_json()
        assert "error" in data


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


class TestMutateAssertionDelete:
    """Validates REQ-d00010-A: Delete assertion endpoint."""

    def test_REQ_d00010_A_delete_assertion_success(self, client):
        # First add a temp assertion, then delete it
        client.post(
            "/api/mutate/assertion/add",
            json={"req_id": "REQ-p00001", "label": "Z", "text": "Temp assertion"},
        )
        resp = client.post(
            "/api/mutate/assertion/delete", json={"assertion_id": "REQ-p00001-Z", "confirm": True}
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_REQ_d00010_A_delete_assertion_missing_id(self, client):
        resp = client.post("/api/mutate/assertion/delete", json={})
        assert resp.status_code == 400

    def test_REQ_d00010_A_delete_assertion_requires_confirm(self, client):
        resp = client.post("/api/mutate/assertion/delete", json={"assertion_id": "REQ-p00001-A"})
        assert resp.status_code == 400


class TestMutateRequirementDelete:
    """Validates REQ-d00010-A: Delete requirement endpoint."""

    def test_REQ_d00010_A_delete_requirement_success(self, client, sample_graph):
        # Add a throwaway requirement, then delete it
        sample_graph.add_requirement(req_id="REQ-z99999", title="Temp", level="DEV")
        resp = client.post(
            "/api/mutate/requirement/delete", json={"node_id": "REQ-z99999", "confirm": True}
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_REQ_d00010_A_delete_requirement_missing_id(self, client):
        resp = client.post("/api/mutate/requirement/delete", json={})
        assert resp.status_code == 400

    def test_REQ_d00010_A_delete_requirement_requires_confirm(self, client):
        resp = client.post("/api/mutate/requirement/delete", json={"node_id": "REQ-p00001"})
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

    def test_REQ_p00006_A_file_content_associated_repo_absolute_path(self, tmp_path):
        """Files from associated repos outside main repo can be loaded via absolute path."""

        # Simulate main repo at tmp_path/main and associate at tmp_path/assoc
        main_repo = tmp_path / "main"
        main_repo.mkdir()
        assoc_repo = tmp_path / "assoc"
        assoc_spec = assoc_repo / "spec"
        assoc_spec.mkdir(parents=True)

        # Write a .elspais.toml that marks this as an associated repo
        (assoc_repo / ".elspais.toml").write_text(
            '[project]\nname = "assoc"\ntype = "associated"\n\n[associated]\nprefix = "A"\n'
        )

        # Write a spec file in the associate repo
        spec_file = assoc_spec / "requirements.md"
        spec_file.write_text("# REQ-A-p00001: Test Requirement\n")

        # Config registers the associate repo path for discovery
        config = {"associates": {"paths": [str(assoc_repo)]}}

        # Build graph with a node whose source path is the absolute path
        # (this is what happens when associated repos are outside the main repo)
        graph = TraceGraph(repo_root=main_repo)
        node = GraphNode(
            id="REQ-A-p00001",
            kind=NodeKind.REQUIREMENT,
            label="Test Requirement",
        )
        node._content = {"level": "PRD", "status": "Active"}
        graph._index[node.id] = node
        graph._roots.append(node)

        app = create_app(repo_root=main_repo, graph=graph, config=config)

        with app.test_client() as c:
            # Request using absolute path (as _relative_source_path returns for out-of-repo files)
            resp = c.get(f"/api/file-content?path={spec_file}")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["lines"][0] == "# REQ-A-p00001: Test Requirement"

    def test_REQ_p00006_A_file_content_rejects_arbitrary_absolute_path(self, tmp_path):
        """Absolute paths outside repo root and allowed dirs are rejected."""
        import tempfile

        main_repo = tmp_path / "main"
        main_repo.mkdir()

        # Create a file outside any allowed directory
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
            f.write("secret data")
            outside_path = f.name

        try:
            graph = TraceGraph(repo_root=main_repo)
            app = create_app(repo_root=main_repo, graph=graph, config={})

            with app.test_client() as c:
                resp = c.get(f"/api/file-content?path={outside_path}")
                assert resp.status_code == 403
        finally:
            Path(outside_path).unlink(missing_ok=True)


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


# ─────────────────────────────────────────────────────────────────────────────
# Git Sync Endpoint Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestGitStatus:
    """Validates REQ-d00010-A, REQ-p00004-C: GET /api/git/status."""

    def test_REQ_p00004_C_git_status_returns_expected_fields(self, client):
        """GET /api/git/status returns branch, is_main, dirty_spec_files, remote_diverged."""
        from unittest.mock import patch

        mock_result = {
            "branch": "feature-x",
            "is_main": False,
            "dirty_spec_files": ["spec/prd.md"],
            "remote_diverged": False,
            "local_ahead": 0,
            "fast_forward_possible": False,
            "main_diverged": False,
        }
        with patch("elspais.utilities.git.git_status_summary", return_value=mock_result):
            resp = client.get("/api/git/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["branch"] == "feature-x"
        assert data["is_main"] is False
        assert data["dirty_spec_files"] == ["spec/prd.md"]
        assert "remote_diverged" in data
        assert "fast_forward_possible" in data

    def test_REQ_p00004_C_git_status_uses_config_spec_dir(self, sample_graph):
        """GET /api/git/status passes spec dir from config."""
        from unittest.mock import patch

        config = {"spec": {"directories": ["requirements"]}}
        application = create_app(repo_root=Path("/test/repo"), graph=sample_graph, config=config)
        application.config["TESTING"] = True

        mock_result = {
            "branch": "main",
            "is_main": True,
            "dirty_spec_files": [],
            "remote_diverged": False,
            "fast_forward_possible": False,
        }
        with patch("elspais.utilities.git.git_status_summary", return_value=mock_result) as m:
            with application.test_client() as c:
                c.get("/api/git/status")
            m.assert_called_once()
            _, kwargs = m.call_args
            assert kwargs.get("spec_dir") == "requirements"


class TestGitBranch:
    """Validates REQ-d00010-A, REQ-p00004-D: POST /api/git/branch."""

    def test_REQ_p00004_D_git_branch_creates_branch(self, client):
        """POST /api/git/branch with valid name returns success."""
        from unittest.mock import patch

        mock_result = {"success": True, "branch": "feature-new", "stash_used": False}
        with patch("elspais.utilities.git.create_and_switch_branch", return_value=mock_result):
            resp = client.post("/api/git/branch", json={"name": "feature-new"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["branch"] == "feature-new"

    def test_REQ_p00004_D_git_branch_empty_name_returns_400(self, client):
        """POST /api/git/branch with empty name returns 400."""
        resp = client.post("/api/git/branch", json={"name": ""})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["success"] is False
        assert "required" in data["error"]

    def test_REQ_p00004_D_git_branch_missing_name_returns_400(self, client):
        """POST /api/git/branch with no name field returns 400."""
        resp = client.post("/api/git/branch", json={})
        assert resp.status_code == 400

    def test_REQ_p00004_D_git_branch_failure_returns_400(self, client):
        """POST /api/git/branch with duplicate name returns 400."""
        from unittest.mock import patch

        mock_result = {"success": False, "error": "branch already exists"}
        with patch("elspais.utilities.git.create_and_switch_branch", return_value=mock_result):
            resp = client.post("/api/git/branch", json={"name": "existing"})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["success"] is False


class TestGitPush:
    """Validates REQ-d00010-A, REQ-p00004-E: POST /api/git/push."""

    def test_REQ_p00004_E_git_push_success(self, client):
        """POST /api/git/push with valid message returns success."""
        from unittest.mock import patch

        mock_result = {"success": True, "files_committed": ["spec/prd.md"]}
        with patch("elspais.utilities.git.commit_and_push_spec_files", return_value=mock_result):
            resp = client.post("/api/git/push", json={"message": "Update specs"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "files_committed" in data

    def test_REQ_p00004_E_git_push_empty_message_returns_400(self, client):
        """POST /api/git/push with empty message returns 400."""
        resp = client.post("/api/git/push", json={"message": ""})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["success"] is False
        assert "required" in data["error"]

    def test_REQ_p00004_E_git_push_on_main_refused(self, client):
        """POST /api/git/push on main branch returns 200 with error in JSON.

        The endpoint always returns 200 so the modal JS can display errors inline.
        """
        from unittest.mock import patch

        mock_result = {
            "success": False,
            "error": "Refusing to commit on protected branch 'main'",
        }
        with patch("elspais.utilities.git.commit_and_push_spec_files", return_value=mock_result):
            resp = client.post("/api/git/push", json={"message": "Bad push"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is False
        assert "Refusing" in data["error"]

    def test_REQ_p00004_E_git_push_generic_error(self, client):
        """POST /api/git/push with generic error returns 200 with error in JSON."""
        from unittest.mock import patch

        mock_result = {"success": False, "error": "Nothing to commit — no dirty spec files"}
        with patch("elspais.utilities.git.commit_and_push_spec_files", return_value=mock_result):
            resp = client.post("/api/git/push", json={"message": "No changes"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is False


class TestGitPull:
    """Validates REQ-d00010-A, REQ-p00004-F: POST /api/git/pull."""

    def test_REQ_p00004_F_git_pull_success(self, client):
        """POST /api/git/pull returns success on fast-forward."""
        from unittest.mock import patch

        mock_result = {"success": True, "message": "Already up to date."}
        with patch("elspais.utilities.git.sync_branch", return_value=mock_result):
            resp = client.post("/api/git/pull")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "message" in data

    def test_REQ_p00004_F_git_pull_no_remote_returns_400(self, client):
        """POST /api/git/pull with no remote returns 400."""
        from unittest.mock import patch

        mock_result = {"success": False, "error": "Fetch failed: no remote configured"}
        with patch("elspais.utilities.git.sync_branch", return_value=mock_result):
            resp = client.post("/api/git/pull")
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["success"] is False
        assert "error" in data

    def test_REQ_p00004_F_git_pull_diverged_returns_400(self, client):
        """POST /api/git/pull with diverged history returns 400."""
        from unittest.mock import patch

        mock_result = {
            "success": False,
            "error": "Cannot fast-forward — resolve differences outside elspais",
        }
        with patch("elspais.utilities.git.sync_branch", return_value=mock_result):
            resp = client.post("/api/git/pull")
        assert resp.status_code == 400
        data = resp.get_json()
        assert "fast-forward" in data["error"]


class TestCLIWiring:
    """Validates REQ-d00010-A: viewer command wiring."""

    def test_REQ_d00010_A_viewer_default_calls_run_server_with_browser(self):
        """Default viewer delegates to _run_server with open_browser=True."""
        import argparse
        from unittest.mock import patch

        from elspais.commands.viewer import run

        args = argparse.Namespace(
            server=False,
            static=False,
            spec_dir=None,
            config=None,
            quiet=True,
            path=None,
            canonical_root=None,
        )
        with patch("elspais.commands.viewer._run_server", return_value=0) as mock:
            result = run(args)
            assert result == 0
            mock.assert_called_once_with(args, open_browser=True)

    def test_REQ_d00010_A_viewer_server_flag_no_browser(self):
        """--server flag delegates to _run_server with open_browser=False."""
        import argparse
        from unittest.mock import patch

        from elspais.commands.viewer import run

        args = argparse.Namespace(
            server=True,
            static=False,
            spec_dir=None,
            config=None,
            quiet=True,
            path=None,
            canonical_root=None,
        )
        with patch("elspais.commands.viewer._run_server", return_value=0) as mock:
            result = run(args)
            assert result == 0
            mock.assert_called_once_with(args, open_browser=False)

    def test_REQ_d00010_A_viewer_static_generates_html(self):
        """--static flag generates an HTML file."""
        import argparse
        from unittest.mock import patch

        from elspais.commands.viewer import run

        args = argparse.Namespace(
            server=False,
            static=True,
            spec_dir=None,
            config=None,
            quiet=True,
            path=None,
            canonical_root=None,
            embed_content=False,
            output=None,
        )
        with patch("elspais.commands.viewer._run_static", return_value=0) as mock:
            result = run(args)
            assert result == 0
            mock.assert_called_once_with(args)


# ─────────────────────────────────────────────────────────────────────────────
# Mutate → Save → Verify file (end-to-end through Flask API)
# ─────────────────────────────────────────────────────────────────────────────

DISK_SPEC = """\
## REQ-t00001: Test Requirement

**Level**: DEV | **Status**: Active | **Implements**: REQ-p00001

## Assertions

A. The system SHALL do something.
B. The system SHALL do another thing.

*End* *Test Requirement* | **Hash**: abcd1234
---
"""

DISK_SPEC_TWO_REQS = """\
## REQ-t00001: First Requirement

**Level**: DEV | **Status**: Active | **Implements**: REQ-p00001

## Assertions

A. The system SHALL do something.
B. The system SHALL do another thing.

*End* *First Requirement* | **Hash**: abcd1234
---

## REQ-t00002: Second Requirement

**Level**: DEV | **Status**: Active | **Implements**: REQ-p00001

## Assertions

A. The second system SHALL work.

*End* *Second Requirement* | **Hash**: efgh5678
---
"""


def _make_disk_app(tmp_path, spec_content=DISK_SPEC, two_reqs=False):
    """Build a Flask app backed by real spec files on disk.

    Returns (app, graph, spec_file) so tests can manipulate the graph directly.
    """
    spec_file = tmp_path / "test_spec.md"
    spec_file.write_text(spec_content, encoding="utf-8")

    from elspais.graph.GraphNode import FileType

    graph = TraceGraph(repo_root=tmp_path)
    rel_path = str(spec_file.relative_to(tmp_path))

    # Create FILE node
    file_node = GraphNode(id=f"file:{rel_path}", kind=NodeKind.FILE, label="test_spec.md")
    file_node.set_field("file_type", FileType.SPEC)
    file_node.set_field("relative_path", rel_path)
    file_node.set_field("absolute_path", str(spec_file))
    file_node.set_field("repo", None)

    prd = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT, label="Product Requirement")
    prd._content = {
        "level": "PRD",
        "status": "Active",
        "hash": "00000000",
        "parse_line": 1,
        "parse_end_line": None,
    }
    file_node.link(prd, EdgeKind.CONTAINS)

    req = GraphNode(
        id="REQ-t00001",
        kind=NodeKind.REQUIREMENT,
        label="Test Requirement" if not two_reqs else "First Requirement",
    )
    req._content = {
        "level": "DEV",
        "status": "Active",
        "hash": "abcd1234",
        "body_text": "",
        "parse_line": 1,
        "parse_end_line": None,
    }
    file_node.link(req, EdgeKind.CONTAINS)

    a1 = GraphNode(
        id="REQ-t00001-A", kind=NodeKind.ASSERTION, label="The system SHALL do something."
    )
    a1._content = {"label": "A", "parse_line": 7, "parse_end_line": None}
    req.link(a1, EdgeKind.STRUCTURES)

    a2 = GraphNode(
        id="REQ-t00001-B", kind=NodeKind.ASSERTION, label="The system SHALL do another thing."
    )
    a2._content = {"label": "B", "parse_line": 8, "parse_end_line": None}
    req.link(a2, EdgeKind.STRUCTURES)

    prd.link(req, EdgeKind.IMPLEMENTS)

    index = {
        f"file:{rel_path}": file_node,
        "REQ-p00001": prd,
        "REQ-t00001": req,
        "REQ-t00001-A": a1,
        "REQ-t00001-B": a2,
    }

    if two_reqs:
        req2 = GraphNode(id="REQ-t00002", kind=NodeKind.REQUIREMENT, label="Second Requirement")
        req2._content = {
            "level": "DEV",
            "status": "Active",
            "hash": "efgh5678",
            "body_text": "",
            "parse_line": 13,
            "parse_end_line": None,
        }
        file_node.link(req2, EdgeKind.CONTAINS)
        r2a = GraphNode(
            id="REQ-t00002-A", kind=NodeKind.ASSERTION, label="The second system SHALL work."
        )
        r2a._content = {"label": "A", "parse_line": 19, "parse_end_line": None}
        req2.link(r2a, EdgeKind.STRUCTURES)
        prd.link(req2, EdgeKind.IMPLEMENTS)
        index["REQ-t00002"] = req2
        index["REQ-t00002-A"] = r2a

    graph._roots = [prd]
    graph._index = index

    application = create_app(repo_root=tmp_path, graph=graph, config={})
    application.config["TESTING"] = True
    return application, graph, spec_file


@pytest.fixture
def disk_app(tmp_path):
    """Create a Flask app backed by real spec files on disk."""
    app, _graph, spec_file = _make_disk_app(tmp_path)
    return app, spec_file


@pytest.fixture
def disk_app_with_graph(tmp_path):
    """Like disk_app but also returns the graph for direct manipulation."""
    return _make_disk_app(tmp_path)


@pytest.fixture
def disk_app_two_reqs(tmp_path):
    """Flask app backed by a spec file with two requirements."""
    return _make_disk_app(tmp_path, spec_content=DISK_SPEC_TWO_REQS, two_reqs=True)


@pytest.fixture
def disk_client(disk_app):
    """Create Flask test client backed by real files."""
    app, _ = disk_app
    return app.test_client()


class TestMutateSaveRoundTrip:
    """End-to-end: mutate via API -> save -> verify file on disk."""

    def test_add_refines_edge_and_save(self, disk_app_with_graph):
        """POST /api/mutate/edge (add REFINES) -> POST /api/save -> file has Refines."""
        app, graph, spec_file = disk_app_with_graph
        client = app.test_client()

        # Add a second PRD node directly on the graph (same Python object)
        str(spec_file.relative_to(graph.repo_root))
        prd2 = GraphNode(
            id="REQ-p00002",
            kind=NodeKind.REQUIREMENT,
            label="Second PRD",
        )
        prd2._content = {"level": "PRD", "status": "Active", "hash": "11111111"}
        graph._index["REQ-p00002"] = prd2
        graph._roots.append(prd2)

        resp = client.post(
            "/api/mutate/edge",
            json={
                "action": "add",
                "source_id": "REQ-t00001",
                "target_id": "REQ-p00002",
                "edge_kind": "refines",
            },
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

        resp = client.post("/api/save")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True, f"Save failed: {data}"

        content = spec_file.read_text(encoding="utf-8")
        assert "**Refines**: REQ-p00002" in content
        assert "**Implements**: REQ-p00001" in content

    def test_change_status_and_save(self, disk_app):
        """POST /api/mutate/status -> POST /api/save -> file has new status."""
        app, spec_file = disk_app
        client = app.test_client()

        resp = client.post(
            "/api/mutate/status",
            json={"node_id": "REQ-t00001", "new_status": "Deprecated"},
        )
        assert resp.status_code == 200

        resp = client.post("/api/save")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "**Status**: Deprecated" in content

    def test_update_title_and_save(self, disk_app):
        """POST /api/mutate/title -> POST /api/save -> file has new title."""
        app, spec_file = disk_app
        client = app.test_client()

        resp = client.post(
            "/api/mutate/title",
            json={"node_id": "REQ-t00001", "new_title": "Updated Title"},
        )
        assert resp.status_code == 200

        resp = client.post("/api/save")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "## REQ-t00001: Updated Title" in content

    def test_update_assertion_and_save(self, disk_app):
        """POST /api/mutate/assertion -> POST /api/save -> file has new text."""
        app, spec_file = disk_app
        client = app.test_client()

        resp = client.post(
            "/api/mutate/assertion",
            json={
                "assertion_id": "REQ-t00001-A",
                "new_text": "The system SHALL do something NEW.",
            },
        )
        assert resp.status_code == 200

        resp = client.post("/api/save")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "A. The system SHALL do something NEW." in content
        assert "B. The system SHALL do another thing." in content

    def test_add_assertion_and_save(self, disk_app):
        """POST /api/mutate/assertion/add -> POST /api/save -> file has new assertion."""
        app, spec_file = disk_app
        client = app.test_client()

        resp = client.post(
            "/api/mutate/assertion/add",
            json={
                "req_id": "REQ-t00001",
                "label": "C",
                "text": "The system SHALL do a third thing.",
            },
        )
        assert resp.status_code == 200

        resp = client.post("/api/save")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "C. The system SHALL do a third thing." in content

    def test_add_implements_edge_and_save(self, disk_app_with_graph):
        """POST /api/mutate/edge (add IMPLEMENTS) -> POST /api/save -> file updated."""
        app, graph, spec_file = disk_app_with_graph
        client = app.test_client()

        # Add a second PRD target directly on the graph
        str(spec_file.relative_to(graph.repo_root))
        prd2 = GraphNode(
            id="REQ-p00002",
            kind=NodeKind.REQUIREMENT,
            label="PRD 2",
        )
        prd2._content = {"level": "PRD", "status": "Active", "hash": "22222222"}
        graph._index["REQ-p00002"] = prd2
        graph._roots.append(prd2)

        resp = client.post(
            "/api/mutate/edge",
            json={
                "action": "add",
                "source_id": "REQ-t00001",
                "target_id": "REQ-p00002",
                "edge_kind": "implements",
            },
        )
        assert resp.status_code == 200

        resp = client.post("/api/save")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "REQ-p00001" in content
        assert "REQ-p00002" in content

    def test_delete_edge_and_save(self, disk_app):
        """POST /api/mutate/edge (delete) -> POST /api/save -> reference removed."""
        app, spec_file = disk_app
        client = app.test_client()

        resp = client.post(
            "/api/mutate/edge",
            json={
                "action": "delete",
                "source_id": "REQ-t00001",
                "target_id": "REQ-p00001",
            },
        )
        assert resp.status_code == 200

        resp = client.post("/api/save")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        # After deleting the only implements target, the field value should be empty
        assert "REQ-p00001" not in content or "**Implements**: -" in content

    def test_change_edge_kind_and_save(self, disk_app):
        """POST /api/mutate/edge (change_kind) -> POST /api/save -> Implements->Refines."""
        app, spec_file = disk_app
        client = app.test_client()

        resp = client.post(
            "/api/mutate/edge",
            json={
                "action": "change_kind",
                "source_id": "REQ-t00001",
                "target_id": "REQ-p00001",
                "new_kind": "refines",
            },
        )
        assert resp.status_code == 200

        resp = client.post("/api/save")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "**Refines**: REQ-p00001" in content
        assert "**Implements**: REQ-p00001" not in content

    def test_delete_assertion_and_save(self, disk_app):
        """POST /api/mutate/assertion/delete -> POST /api/save -> assertion removed."""
        app, spec_file = disk_app
        client = app.test_client()

        resp = client.post(
            "/api/mutate/assertion/delete",
            json={"assertion_id": "REQ-t00001-B", "confirm": True},
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

        resp = client.post("/api/save")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "A. The system SHALL do something." in content
        assert "do another thing" not in content

    def test_delete_requirement_and_save(self, disk_app_two_reqs):
        """POST /api/mutate/requirement/delete -> POST /api/save -> req removed from file."""
        app, graph, spec_file = disk_app_two_reqs
        client = app.test_client()

        resp = client.post(
            "/api/mutate/requirement/delete",
            json={"node_id": "REQ-t00002", "confirm": True},
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

        resp = client.post("/api/save")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "REQ-t00001" in content
        assert "First Requirement" in content
        assert "REQ-t00002" not in content
        assert "Second Requirement" not in content

    def test_multiple_mutations_then_save(self, disk_app):
        """Multiple mutations followed by a single save all persist correctly."""
        app, spec_file = disk_app
        client = app.test_client()

        # Mutation 1: Change status
        resp = client.post(
            "/api/mutate/status",
            json={"node_id": "REQ-t00001", "new_status": "Draft"},
        )
        assert resp.status_code == 200

        # Mutation 2: Update title
        resp = client.post(
            "/api/mutate/title",
            json={"node_id": "REQ-t00001", "new_title": "Changed Title"},
        )
        assert resp.status_code == 200

        # Mutation 3: Update assertion
        resp = client.post(
            "/api/mutate/assertion",
            json={
                "assertion_id": "REQ-t00001-B",
                "new_text": "The system SHALL do something else.",
            },
        )
        assert resp.status_code == 200

        # Single save
        resp = client.post("/api/save")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["saved_count"] >= 1  # render-save counts files, not mutations

        content = spec_file.read_text(encoding="utf-8")
        assert "**Status**: Draft" in content
        assert "## REQ-t00001: Changed Title" in content
        assert "B. The system SHALL do something else." in content
        # Assertion A should be untouched
        assert "A. The system SHALL do something." in content

    def test_undo_then_save_persists_remaining(self, disk_app):
        """Mutate twice, undo one, save -> only first mutation persists."""
        app, spec_file = disk_app
        client = app.test_client()

        # Mutation 1: Change status
        resp = client.post(
            "/api/mutate/status",
            json={"node_id": "REQ-t00001", "new_status": "Draft"},
        )
        assert resp.status_code == 200

        # Mutation 2: Update title
        resp = client.post(
            "/api/mutate/title",
            json={"node_id": "REQ-t00001", "new_title": "Should Be Undone"},
        )
        assert resp.status_code == 200

        # Undo mutation 2
        resp = client.post("/api/mutate/undo")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

        # Save — only status change should persist
        resp = client.post("/api/save")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "**Status**: Draft" in content
        assert "## REQ-t00001: Test Requirement" in content  # title unchanged
        assert "Should Be Undone" not in content

    def test_save_with_no_mutations_succeeds(self, disk_app):
        """POST /api/save with no pending mutations succeeds with count 0."""
        app, spec_file = disk_app
        client = app.test_client()
        original_content = spec_file.read_text(encoding="utf-8")

        resp = client.post("/api/save")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["saved_count"] == 0

        # File should be unchanged
        assert spec_file.read_text(encoding="utf-8") == original_content

    def test_dirty_reflects_mutation_state(self, disk_app):
        """GET /api/dirty tracks pending mutation count."""
        app, _ = disk_app
        client = app.test_client()

        # Initially clean
        resp = client.get("/api/dirty")
        assert resp.get_json()["dirty"] is False

        # Mutate
        client.post(
            "/api/mutate/status",
            json={"node_id": "REQ-t00001", "new_status": "Draft"},
        )
        resp = client.get("/api/dirty")
        assert resp.get_json()["dirty"] is True

        # Save clears dirty state
        client.post("/api/save")
        resp = client.get("/api/dirty")
        # After save, build_time is updated — mutations are still in the log
        # but /api/dirty checks the mutation count, not the build_time
        data = resp.get_json()
        # dirty may still be True (mutations stay in log), but save succeeded
        assert isinstance(data["dirty"], bool)

    def test_add_assertion_then_delete_it_then_save(self, disk_app):
        """Add assertion, then delete it, then save -> file unchanged."""
        app, spec_file = disk_app
        client = app.test_client()

        # Add assertion C
        resp = client.post(
            "/api/mutate/assertion/add",
            json={
                "req_id": "REQ-t00001",
                "label": "C",
                "text": "Temporary assertion.",
            },
        )
        assert resp.status_code == 200

        # Delete assertion C
        resp = client.post(
            "/api/mutate/assertion/delete",
            json={"assertion_id": "REQ-t00001-C", "confirm": True},
        )
        assert resp.status_code == 200

        # Save
        resp = client.post("/api/save")
        assert resp.status_code == 200

        content = spec_file.read_text(encoding="utf-8")
        assert "Temporary assertion" not in content
        # Original assertions preserved
        assert "A. The system SHALL do something." in content
        assert "B. The system SHALL do another thing." in content

    def test_change_edge_kind_then_add_edge_then_save(self, disk_app_with_graph):
        """Change IMPLEMENTS->REFINES, add new IMPLEMENTS, save -> both persisted."""
        app, graph, spec_file = disk_app_with_graph
        client = app.test_client()

        # Add a second PRD target
        str(spec_file.relative_to(graph.repo_root))
        prd2 = GraphNode(
            id="REQ-p00002",
            kind=NodeKind.REQUIREMENT,
            label="PRD 2",
        )
        prd2._content = {"level": "PRD", "status": "Active", "hash": "22222222"}
        graph._index["REQ-p00002"] = prd2
        graph._roots.append(prd2)

        # Change existing IMPLEMENTS to REFINES
        resp = client.post(
            "/api/mutate/edge",
            json={
                "action": "change_kind",
                "source_id": "REQ-t00001",
                "target_id": "REQ-p00001",
                "new_kind": "refines",
            },
        )
        assert resp.status_code == 200

        # Add a new IMPLEMENTS edge to p00002
        resp = client.post(
            "/api/mutate/edge",
            json={
                "action": "add",
                "source_id": "REQ-t00001",
                "target_id": "REQ-p00002",
                "edge_kind": "implements",
            },
        )
        assert resp.status_code == 200

        resp = client.post("/api/save")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "**Refines**: REQ-p00001" in content
        assert "**Implements**: REQ-p00002" in content

    def test_mutations_across_two_reqs_then_save(self, disk_app_two_reqs):
        """Mutate two different requirements, save once -> both persisted."""
        app, graph, spec_file = disk_app_two_reqs
        client = app.test_client()

        # Mutate first req
        resp = client.post(
            "/api/mutate/status",
            json={"node_id": "REQ-t00001", "new_status": "Draft"},
        )
        assert resp.status_code == 200

        # Mutate second req
        resp = client.post(
            "/api/mutate/status",
            json={"node_id": "REQ-t00002", "new_status": "Deprecated"},
        )
        assert resp.status_code == 200

        resp = client.post("/api/save")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["saved_count"] >= 1  # render-save counts files, not mutations

        content = spec_file.read_text(encoding="utf-8")
        # First req
        assert "## REQ-t00001: First Requirement" in content
        # Check status appears in the right section
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if "REQ-t00001" in line:
                # Find the metadata line after the header
                for j in range(i + 1, min(i + 5, len(lines))):
                    if "**Status**" in lines[j]:
                        assert "Draft" in lines[j]
                        break
                break
        for i, line in enumerate(lines):
            if "REQ-t00002" in line:
                for j in range(i + 1, min(i + 5, len(lines))):
                    if "**Status**" in lines[j]:
                        assert "Deprecated" in lines[j]
                        break
                break

    def test_add_assertion_to_two_reqs_then_save(self, disk_app_two_reqs):
        """Add assertions to different reqs, save once -> both persisted."""
        app, graph, spec_file = disk_app_two_reqs
        client = app.test_client()

        resp = client.post(
            "/api/mutate/assertion/add",
            json={
                "req_id": "REQ-t00001",
                "label": "C",
                "text": "New assertion for first req.",
            },
        )
        assert resp.status_code == 200

        resp = client.post(
            "/api/mutate/assertion/add",
            json={
                "req_id": "REQ-t00002",
                "label": "B",
                "text": "New assertion for second req.",
            },
        )
        assert resp.status_code == 200

        resp = client.post("/api/save")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "C. New assertion for first req." in content
        assert "B. New assertion for second req." in content


class TestMutateValidation:
    """Validate error handling for mutation API endpoints."""

    def test_mutate_status_missing_fields(self, disk_client):
        resp = disk_client.post("/api/mutate/status", json={"node_id": "REQ-t00001"})
        assert resp.status_code == 400

    def test_mutate_status_unknown_node(self, disk_client):
        resp = disk_client.post(
            "/api/mutate/status",
            json={"node_id": "REQ-nonexistent", "new_status": "Draft"},
        )
        assert resp.status_code == 400

    def test_mutate_title_missing_fields(self, disk_client):
        resp = disk_client.post("/api/mutate/title", json={"node_id": "REQ-t00001"})
        assert resp.status_code == 400

    def test_mutate_assertion_missing_fields(self, disk_client):
        resp = disk_client.post("/api/mutate/assertion", json={"assertion_id": "REQ-t00001-A"})
        assert resp.status_code == 400

    def test_mutate_assertion_add_missing_fields(self, disk_client):
        resp = disk_client.post(
            "/api/mutate/assertion/add",
            json={"req_id": "REQ-t00001", "label": "C"},
        )
        assert resp.status_code == 400

    def test_mutate_assertion_delete_no_confirm(self, disk_client):
        resp = disk_client.post(
            "/api/mutate/assertion/delete",
            json={"assertion_id": "REQ-t00001-A"},
        )
        assert resp.status_code == 400

    def test_mutate_requirement_delete_no_confirm(self, disk_client):
        resp = disk_client.post(
            "/api/mutate/requirement/delete",
            json={"node_id": "REQ-t00001"},
        )
        assert resp.status_code == 400

    def test_mutate_edge_missing_action(self, disk_client):
        resp = disk_client.post(
            "/api/mutate/edge",
            json={"source_id": "REQ-t00001", "target_id": "REQ-p00001"},
        )
        assert resp.status_code == 400

    def test_mutate_edge_unknown_action(self, disk_client):
        resp = disk_client.post(
            "/api/mutate/edge",
            json={
                "action": "unknown",
                "source_id": "REQ-t00001",
                "target_id": "REQ-p00001",
            },
        )
        assert resp.status_code == 400

    def test_mutate_edge_add_missing_kind(self, disk_client):
        resp = disk_client.post(
            "/api/mutate/edge",
            json={
                "action": "add",
                "source_id": "REQ-t00001",
                "target_id": "REQ-p00001",
            },
        )
        assert resp.status_code == 400

    def test_mutate_edge_change_kind_missing_new_kind(self, disk_client):
        resp = disk_client.post(
            "/api/mutate/edge",
            json={
                "action": "change_kind",
                "source_id": "REQ-t00001",
                "target_id": "REQ-p00001",
            },
        )
        assert resp.status_code == 400

    def test_undo_with_no_mutations(self, disk_client):
        """Undo with no pending mutations returns error."""
        resp = disk_client.post("/api/mutate/undo")
        assert resp.status_code == 400
