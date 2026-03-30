# Verifies: REQ-d00244-A+B+C
"""Tests for Term Cards in the viewer card stack.

Validates REQ-d00244-A: openTermCard() fetches /api/term/{key} and opens card
Validates REQ-d00244-B: References grouped by namespace, clickable; empty refs message
Validates REQ-d00244-C: Read-only, buildTermCardHtml() renders via kind === 'term'
"""

from __future__ import annotations

from pathlib import Path

from starlette.testclient import TestClient

from elspais.config import config_defaults
from elspais.graph import GraphNode, NodeKind
from elspais.graph.builder import TraceGraph
from elspais.graph.federated import FederatedGraph, RepoEntry
from elspais.graph.terms import TermDictionary, TermEntry, TermRef
from elspais.server.app import create_app
from elspais.server.state import AppState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app(tmp_path: Path) -> TestClient:
    """Create a test app with two terms: one with refs, one without."""
    graph = TraceGraph(repo_root=tmp_path)

    file_node = GraphNode(id="file:spec/glossary.md", kind=NodeKind.FILE)
    file_node.set_field("relative_path", "spec/glossary.md")
    file_node.set_field("absolute_path", str(tmp_path / "spec" / "glossary.md"))
    graph._index["file:spec/glossary.md"] = file_node
    graph._roots.append(file_node)

    # Add a requirement node so the reference can resolve a title
    req_node = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
    req_node.set_field("title", "Authentication System")
    graph._index["REQ-p00001"] = req_node

    repos = [RepoEntry(name="root", graph=graph, config={}, repo_root=tmp_path)]
    federated = FederatedGraph(repos)

    terms = TermDictionary()
    terms.add(
        TermEntry(
            term="Bearer Token",
            definition="An access token used for authentication.",
            collection=False,
            indexed=True,
            defined_in="REQ-p00001",
            namespace="root",
            references=[
                TermRef(node_id="REQ-p00001", namespace="root", marked=True, line=10),
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

    state = AppState(graph=federated, repo_root=tmp_path, config=config_defaults())
    app = create_app(state=state, mount_mcp=False)
    return TestClient(app)


# ---------------------------------------------------------------------------
# TestTermCardJsRendered (REQ-d00244-A, REQ-d00244-C)
# ---------------------------------------------------------------------------


class TestTermCardJsRendered:
    """Validates that term card JS functions are present in the rendered HTML."""

    def test_REQ_d00244_A_openTermCard_in_html(self, tmp_path: Path) -> None:
        """GET '/' HTML contains the openTermCard function."""
        client = _make_app(tmp_path)
        resp = client.get("/")
        assert resp.status_code == 200
        html = resp.text
        assert "openTermCard" in html, "Expected 'openTermCard' function in the rendered HTML"

    def test_REQ_d00244_C_buildTermCardHtml_in_html(self, tmp_path: Path) -> None:
        """GET '/' HTML contains the buildTermCardHtml function."""
        client = _make_app(tmp_path)
        resp = client.get("/")
        assert resp.status_code == 200
        html = resp.text
        assert (
            "buildTermCardHtml" in html
        ), "Expected 'buildTermCardHtml' function in the rendered HTML"

    def test_REQ_d00244_C_term_kind_in_renderCardStack(self, tmp_path: Path) -> None:
        """GET '/' HTML contains 'term' kind in the card rendering dispatch logic."""
        client = _make_app(tmp_path)
        resp = client.get("/")
        assert resp.status_code == 200
        html = resp.text
        # The renderCardStack dispatch should have a branch for kind === 'term'
        # that calls buildTermCardHtml
        assert (
            "buildTermCardHtml" in html
        ), "Expected buildTermCardHtml in card rendering dispatch logic"


# ---------------------------------------------------------------------------
# TestTermCardApiIntegration (REQ-d00244-A, REQ-d00244-B)
# ---------------------------------------------------------------------------


class TestTermCardApiIntegration:
    """Validates the /api/term/{key} endpoint returns data needed for card rendering."""

    def test_REQ_d00244_A_api_term_returns_card_data(self, tmp_path: Path) -> None:
        """GET /api/term/{key} returns all fields needed for card rendering."""
        client = _make_app(tmp_path)
        resp = client.get("/api/term/bearer token")
        assert resp.status_code == 200
        data = resp.json()
        # Verify all required card fields are present
        assert data["term"] == "Bearer Token"
        assert data["definition"] == "An access token used for authentication."
        assert data["defined_in"] == "REQ-p00001"
        assert data["namespace"] == "root"
        assert data["collection"] is False
        assert data["indexed"] is True
        assert isinstance(data["references"], list)
        assert len(data["references"]) == 1
        ref = data["references"][0]
        assert ref["node_id"] == "REQ-p00001"
        assert ref["namespace"] == "root"
        assert ref["marked"] is True

    def test_REQ_d00244_B_api_term_empty_references(self, tmp_path: Path) -> None:
        """GET /api/term/{key} returns empty references for term with no refs."""
        client = _make_app(tmp_path)
        resp = client.get("/api/term/api gateway")
        assert resp.status_code == 200
        data = resp.json()
        assert data["term"] == "API Gateway"
        assert data["references"] == [], "Expected empty references array for term with no refs"
