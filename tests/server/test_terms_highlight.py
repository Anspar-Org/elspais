# Verifies: REQ-d00245-A+B
"""Tests for inline term highlighting in the viewer.

Validates REQ-d00245-A: simpleMarkdown(text, true) wraps defined terms in
    span.defined-term with data-term-key and data-tip.
Validates REQ-d00245-B: Click handler on card-stack-body for .defined-term,
    hover tooltip, no annotation in term cards.
"""

from __future__ import annotations

from pathlib import Path

from starlette.testclient import TestClient

from elspais.config import config_defaults
from elspais.graph import GraphNode, NodeKind
from elspais.graph.builder import TraceGraph
from elspais.graph.federated import FederatedGraph, RepoEntry
from elspais.graph.terms import TermDictionary, TermEntry
from elspais.server.app import create_app
from elspais.server.state import AppState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app(tmp_path: Path) -> TestClient:
    """Create a test app with a minimal graph and a term dictionary."""
    graph = TraceGraph(repo_root=tmp_path)

    file_node = GraphNode(id="file:spec/glossary.md", kind=NodeKind.FILE)
    file_node.set_field("relative_path", "spec/glossary.md")
    file_node.set_field("absolute_path", str(tmp_path / "spec" / "glossary.md"))

    graph._index["file:spec/glossary.md"] = file_node
    graph._roots.append(file_node)

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
            references=[],
        )
    )
    federated._terms = terms

    state = AppState(graph=federated, repo_root=tmp_path, config=config_defaults())
    app = create_app(state=state, mount_mcp=False)
    return TestClient(app)


# ---------------------------------------------------------------------------
# TestTermHighlightJs (REQ-d00245-A, REQ-d00245-B)
# ---------------------------------------------------------------------------


class TestTermHighlightJs:
    """Validates REQ-d00245-A and REQ-d00245-B: inline term highlighting JS
    is present in the rendered HTML."""

    def test_REQ_d00245_A_simpleMarkdown_accepts_annotateTerms(self, tmp_path: Path) -> None:
        """GET '/' HTML contains simpleMarkdown function with annotateTerms parameter."""
        client = _make_app(tmp_path)
        resp = client.get("/")
        assert resp.status_code == 200
        html = resp.text
        assert (
            "simpleMarkdown(text, annotateTerms)" in html
            or "function simpleMarkdown(text, annotateTerms)" in html
        ), "Expected simpleMarkdown function signature with annotateTerms parameter"

    def test_REQ_d00245_A_termsRegex_built_from_lookup(self, tmp_path: Path) -> None:
        """GET '/' HTML contains termsRegex — the cached regex for term matching."""
        client = _make_app(tmp_path)
        resp = client.get("/")
        assert resp.status_code == 200
        html = resp.text
        assert "termsRegex" in html, (
            "Expected 'termsRegex' in the rendered HTML " "(cached regex built from termsLookup)"
        )

    def test_REQ_d00245_A_defined_term_class_in_js(self, tmp_path: Path) -> None:
        """GET '/' HTML contains 'defined-term' class reference used for annotated spans."""
        client = _make_app(tmp_path)
        resp = client.get("/")
        assert resp.status_code == 200
        html = resp.text
        assert (
            "defined-term" in html
        ), "Expected 'defined-term' CSS class reference in the rendered HTML"

    def test_REQ_d00245_B_delegated_click_handler(self, tmp_path: Path) -> None:
        """GET '/' HTML contains a delegated click handler for .defined-term
        on card-stack-body."""
        client = _make_app(tmp_path)
        resp = client.get("/")
        assert resp.status_code == 200
        html = resp.text
        # The delegation pattern: getElementById('card-stack-body') + addEventListener('click', ...)
        assert (
            "card-stack-body" in html
        ), "Expected 'card-stack-body' element reference in the rendered HTML"
        # Check that the click handler references .defined-term via closest()
        assert (
            ".defined-term" in html
            or "closest('.defined-term')" in html
            or 'closest(".defined-term")' in html
        ), "Expected delegated click handler referencing '.defined-term'"

    def test_REQ_d00245_B_no_annotation_in_term_cards(self, tmp_path: Path) -> None:
        """GET '/' HTML shows buildTermCardHtml calls simpleMarkdown WITHOUT
        passing true for annotateTerms (term definitions should not annotate
        other terms within themselves)."""
        client = _make_app(tmp_path)
        resp = client.get("/")
        assert resp.status_code == 200
        html = resp.text
        # buildTermCardHtml must exist
        assert (
            "buildTermCardHtml" in html
        ), "Expected buildTermCardHtml function in the rendered HTML"
        # Inside buildTermCardHtml, simpleMarkdown is called for the definition.
        # It must NOT pass true as the second argument.
        # The actual call is: simpleMarkdown(data.definition || '')
        # (no second arg, so annotateTerms is undefined/falsy)
        assert (
            "simpleMarkdown(data.definition" in html
        ), "Expected simpleMarkdown call for term definition in buildTermCardHtml"
        # Ensure it does NOT pass true for term definitions
        assert (
            "simpleMarkdown(data.definition || '', true)" not in html
        ), "Term definition rendering must NOT pass true for annotateTerms"
