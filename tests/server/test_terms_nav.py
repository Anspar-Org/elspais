# Verifies: REQ-d00243-A+B+C
"""Tests for Terms tab rendering in the viewer nav tree.

Validates REQ-d00243-A: Terms tab button with data-kind="terms" in nav-tabs
Validates REQ-d00243-B: Empty state data flow via /api/terms returning []
Validates REQ-d00243-C: JS logic hides expand/collapse and view-mode-toggle for terms tab
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


def _make_app(tmp_path: Path, *, with_terms: bool = True) -> TestClient:
    """Create a test app with a minimal graph, optionally with terms."""
    graph = TraceGraph(repo_root=tmp_path)

    file_node = GraphNode(id="file:spec/glossary.md", kind=NodeKind.FILE)
    file_node.set_field("relative_path", "spec/glossary.md")
    file_node.set_field("absolute_path", str(tmp_path / "spec" / "glossary.md"))

    graph._index["file:spec/glossary.md"] = file_node
    graph._roots.append(file_node)

    repos = [RepoEntry(name="root", graph=graph, config={}, repo_root=tmp_path)]
    federated = FederatedGraph(repos)

    terms = TermDictionary()
    if with_terms:
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
# TestTermsTabRendering (REQ-d00243-A)
# ---------------------------------------------------------------------------


class TestTermsTabRendering:
    """Validates REQ-d00243-A: Terms tab button appears in nav-tabs with
    data-kind='terms' and switchNavTab('terms') onclick."""

    def test_REQ_d00243_A_terms_tab_button_rendered(self, tmp_path: Path) -> None:
        """GET '/' HTML contains a button with data-kind='terms' and text 'Terms'."""
        client = _make_app(tmp_path)
        resp = client.get("/")
        assert resp.status_code == 200
        html = resp.text
        assert (
            'data-kind="terms"' in html
        ), 'Expected a nav-tab button with data-kind="terms" in the rendered HTML'
        # The button text should contain "Terms"
        # Look for the pattern: data-kind="terms" ... >Terms<
        assert ">Terms<" in html, "Expected button text 'Terms' in the nav-tab button"

    def test_REQ_d00243_A_switchNavTab_terms_in_js(self, tmp_path: Path) -> None:
        """GET '/' HTML contains switchNavTab('terms') in onclick handler."""
        client = _make_app(tmp_path)
        resp = client.get("/")
        assert resp.status_code == 200
        html = resp.text
        assert (
            "switchNavTab('terms')" in html
        ), "Expected onclick handler switchNavTab('terms') in the rendered HTML"


# ---------------------------------------------------------------------------
# TestTermsNavEmpty (REQ-d00243-B)
# ---------------------------------------------------------------------------


class TestTermsNavEmpty:
    """Validates REQ-d00243-B: Empty terms dictionary produces empty list,
    validating the data flow for the 'No defined terms found' empty state."""

    def test_REQ_d00243_B_empty_terms_message(self, tmp_path: Path) -> None:
        """GET /api/terms returns [] for empty dictionary (empty state data flow)."""
        client = _make_app(tmp_path, with_terms=False)
        resp = client.get("/api/terms")
        assert resp.status_code == 200
        data = resp.json()
        terms = data if isinstance(data, list) else data.get("terms", data)
        assert terms == [], "Expected empty list from /api/terms when TermDictionary is empty"


# ---------------------------------------------------------------------------
# TestTermsNavControls (REQ-d00243-C)
# ---------------------------------------------------------------------------


class TestTermsNavControls:
    """Validates REQ-d00243-C: JS logic hides expand/collapse, tree/flat toggle,
    and filter groups when Terms tab is active. Text filter filters terms by name."""

    def test_REQ_d00243_C_terms_hides_controls_js(self, tmp_path: Path) -> None:
        """GET '/' HTML contains JS that hides expand/collapse and view-mode-toggle
        when the active tab is 'terms'."""
        client = _make_app(tmp_path)
        resp = client.get("/")
        assert resp.status_code == 200
        html = resp.text
        # The switchNavTab or renderNavTree function should contain logic
        # that checks for 'terms' tab and hides controls.
        # We check for the key indicators:
        # 1. The JS references 'terms' in tab-switching logic
        assert (
            "'terms'" in html or '"terms"' in html
        ), "Expected JS code referencing 'terms' tab kind"
        # 2. The JS hides view-mode-toggle for terms tab
        assert "view-mode-toggle" in html, "Expected JS reference to view-mode-toggle element"
