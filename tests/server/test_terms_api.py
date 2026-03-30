# Verifies: REQ-d00242-A+B+C
"""Tests for terms API endpoints (/api/terms, /api/term/{key})."""

from __future__ import annotations

from pathlib import Path

from starlette.testclient import TestClient

from elspais.graph import GraphNode, NodeKind
from elspais.graph.builder import TraceGraph
from elspais.graph.federated import FederatedGraph, RepoEntry
from elspais.graph.relations import EdgeKind
from elspais.graph.terms import TermDictionary, TermEntry, TermRef
from elspais.server.app import create_app
from elspais.server.state import AppState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

LONG_DEFINITION = (
    "This is a very long definition that exceeds one hundred and fifty characters "
    "in order to test that the API correctly truncates the definition_short field "
    "and appends an ellipsis suffix to indicate truncation occurred."
)
assert len(LONG_DEFINITION) > 150  # sanity check


def _make_app(tmp_path: Path) -> TestClient:
    """Create a test app with a graph containing terms."""
    graph = TraceGraph(repo_root=tmp_path)

    # Create a FILE node
    file_node = GraphNode(id="file:spec/glossary.md", kind=NodeKind.FILE)
    file_node.set_field("relative_path", "spec/glossary.md")
    file_node.set_field("absolute_path", str(tmp_path / "spec" / "glossary.md"))

    # Create a requirement node (for node_title resolution)
    req = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
    req.set_field("title", "Authentication Module")
    file_node.link(req, EdgeKind.CONTAINS)

    graph._index["file:spec/glossary.md"] = file_node
    graph._index["REQ-p00001"] = req
    graph._roots.append(file_node)

    # Build federated graph
    repos = [RepoEntry(name="root", graph=graph, config={}, repo_root=tmp_path)]
    federated = FederatedGraph(repos)

    # Populate terms dictionary
    terms = TermDictionary()
    terms.add(
        TermEntry(
            term="Bearer Token",
            definition=LONG_DEFINITION,
            collection=True,
            indexed=True,
            defined_in="REQ-p00001",
            namespace="root",
            references=[
                TermRef(node_id="REQ-p00001", namespace="root", marked=True, line=10),
                TermRef(node_id="REQ-p00001", namespace="root", marked=False, line=25),
            ],
        )
    )
    terms.add(
        TermEntry(
            term="API Gateway",
            definition="A server that acts as a single entry point.",
            collection=False,
            indexed=True,
            defined_in="REQ-p00001",
            namespace="root",
            references=[],
        )
    )
    federated._terms = terms

    state = AppState(graph=federated, repo_root=tmp_path, config={})
    app = create_app(state=state, mount_mcp=False)
    return TestClient(app)


# ---------------------------------------------------------------------------
# TestTermsListEndpoint (REQ-d00242-A)
# ---------------------------------------------------------------------------


class TestTermsListEndpoint:
    """Validates REQ-d00242-A: GET /api/terms returns sorted term list with
    summary fields."""

    def test_REQ_d00242_A_returns_sorted_terms(self, tmp_path: Path) -> None:
        """GET /api/terms returns terms sorted alphabetically by term name."""
        client = _make_app(tmp_path)
        resp = client.get("/api/terms")
        assert resp.status_code == 200
        data = resp.json()
        terms = data if isinstance(data, list) else data.get("terms", data)
        assert len(terms) == 2
        # "API Gateway" before "Bearer Token" alphabetically
        assert terms[0]["term"] == "API Gateway"
        assert terms[1]["term"] == "Bearer Token"

    def test_REQ_d00242_A_term_fields(self, tmp_path: Path) -> None:
        """Each term object has all required summary fields."""
        client = _make_app(tmp_path)
        resp = client.get("/api/terms")
        assert resp.status_code == 200
        data = resp.json()
        terms = data if isinstance(data, list) else data.get("terms", data)
        required_fields = {
            "term",
            "key",
            "definition_short",
            "defined_in",
            "namespace",
            "collection",
            "indexed",
            "ref_count",
        }
        for t in terms:
            missing = required_fields - set(t.keys())
            assert not missing, f"Missing fields: {missing}"

    def test_REQ_d00242_A_definition_short_truncated(self, tmp_path: Path) -> None:
        """definition_short is truncated to 150 chars with '...' suffix for long defs."""
        client = _make_app(tmp_path)
        resp = client.get("/api/terms")
        assert resp.status_code == 200
        data = resp.json()
        terms = data if isinstance(data, list) else data.get("terms", data)
        # Find "Bearer Token" which has LONG_DEFINITION
        bearer = next(t for t in terms if t["term"] == "Bearer Token")
        assert len(bearer["definition_short"]) <= 153  # 150 + "..."
        assert bearer["definition_short"].endswith("...")
        # "API Gateway" has a short definition -- not truncated
        api_gw = next(t for t in terms if t["term"] == "API Gateway")
        assert api_gw["definition_short"] == "A server that acts as a single entry point."

    def test_REQ_d00242_A_ref_count(self, tmp_path: Path) -> None:
        """ref_count matches number of references for each term."""
        client = _make_app(tmp_path)
        resp = client.get("/api/terms")
        assert resp.status_code == 200
        data = resp.json()
        terms = data if isinstance(data, list) else data.get("terms", data)
        bearer = next(t for t in terms if t["term"] == "Bearer Token")
        assert bearer["ref_count"] == 2
        api_gw = next(t for t in terms if t["term"] == "API Gateway")
        assert api_gw["ref_count"] == 0

    def test_REQ_d00242_A_empty_dictionary(self, tmp_path: Path) -> None:
        """Empty TermDictionary returns []."""
        graph = TraceGraph(repo_root=tmp_path)
        repos = [RepoEntry(name="root", graph=graph, config={}, repo_root=tmp_path)]
        federated = FederatedGraph(repos)
        federated._terms = TermDictionary()
        state = AppState(graph=federated, repo_root=tmp_path, config={})
        app = create_app(state=state, mount_mcp=False)
        client = TestClient(app)
        resp = client.get("/api/terms")
        assert resp.status_code == 200
        data = resp.json()
        terms = data if isinstance(data, list) else data.get("terms", data)
        assert terms == []


# ---------------------------------------------------------------------------
# TestTermDetailEndpoint (REQ-d00242-B)
# ---------------------------------------------------------------------------


class TestTermDetailEndpoint:
    """Validates REQ-d00242-B: GET /api/term/{term_key} returns full detail
    with definition, references, and resolved node_title."""

    def test_REQ_d00242_B_returns_full_detail(self, tmp_path: Path) -> None:
        """GET /api/term/{key} returns full term with all fields."""
        client = _make_app(tmp_path)
        resp = client.get("/api/term/bearer token")
        assert resp.status_code == 200
        data = resp.json()
        assert data["term"] == "Bearer Token"
        assert data["definition"] == LONG_DEFINITION
        assert data["defined_in"] == "REQ-p00001"
        assert data["namespace"] == "root"
        assert data["collection"] is True
        assert data["indexed"] is True
        assert isinstance(data["references"], list)
        assert len(data["references"]) == 2

    def test_REQ_d00242_B_references_include_node_title(self, tmp_path: Path) -> None:
        """Each reference has node_title resolved from the graph."""
        client = _make_app(tmp_path)
        resp = client.get("/api/term/bearer token")
        assert resp.status_code == 200
        data = resp.json()
        for ref in data["references"]:
            assert "node_title" in ref
            # REQ-p00001 has title "Authentication Module"
            assert ref["node_title"] == "Authentication Module"

    def test_REQ_d00242_B_reference_fields(self, tmp_path: Path) -> None:
        """Each reference has all required fields."""
        client = _make_app(tmp_path)
        resp = client.get("/api/term/bearer token")
        assert resp.status_code == 200
        data = resp.json()
        required_fields = {"node_id", "node_title", "namespace", "marked", "line"}
        for ref in data["references"]:
            missing = required_fields - set(ref.keys())
            assert not missing, f"Missing ref fields: {missing}"


# ---------------------------------------------------------------------------
# TestTermNotFound (REQ-d00242-C)
# ---------------------------------------------------------------------------


class TestTermNotFound:
    """Validates REQ-d00242-C: GET /api/term/{nonexistent} returns 404."""

    def test_REQ_d00242_C_nonexistent_returns_404(self, tmp_path: Path) -> None:
        """GET /api/term/nonexistent returns 404."""
        client = _make_app(tmp_path)
        resp = client.get("/api/term/nonexistent")
        assert resp.status_code == 404
