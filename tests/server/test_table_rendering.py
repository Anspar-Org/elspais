# Verifies: REQ-d00010
"""Server-rendered HTML smoke tests for the viewer pipe-table renderer.

Validates REQ-d00010: GET / serves a viewer page whose script + style
blocks contain the pipe-table extraction/reinsertion functions and the
`.md-table` full-grid CSS rules.

The functions and CSS rules live in two Jinja partials:
    - src/elspais/html/templates/partials/js/_md-table.js.j2
    - src/elspais/html/templates/partials/css/_md-tables.css.j2
Both are included from trace_unified.html.j2; these tests prove the
wiring is in place by string-matching their distinctive identifiers.
"""

from __future__ import annotations

from pathlib import Path

from starlette.testclient import TestClient

from elspais.config import config_defaults
from elspais.graph import GraphNode, NodeKind
from elspais.graph.builder import TraceGraph
from elspais.graph.federated import FederatedGraph, RepoEntry
from elspais.server.app import create_app
from elspais.server.state import AppState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app(tmp_path: Path) -> TestClient:
    """Create a test app with a minimal (single FILE) graph."""
    graph = TraceGraph(repo_root=tmp_path)

    file_node = GraphNode(id="file:spec/example.md", kind=NodeKind.FILE)
    file_node.set_field("relative_path", "spec/example.md")
    file_node.set_field("absolute_path", str(tmp_path / "spec" / "example.md"))

    graph._index["file:spec/example.md"] = file_node
    graph._roots.append(file_node)

    repos = [RepoEntry(name="root", graph=graph, config={}, repo_root=tmp_path)]
    federated = FederatedGraph(repos)

    state = AppState(graph=federated, repo_root=tmp_path, config=config_defaults())
    app = create_app(state=state, mount_mcp=False)
    return TestClient(app)


# ---------------------------------------------------------------------------
# TestTableRenderingPartialsWired (REQ-d00010)
# ---------------------------------------------------------------------------


class TestTableRenderingPartialsWired:
    """Validates REQ-d00010: pipe-table JS + CSS partials are included in
    the server-rendered viewer HTML."""

    def test_REQ_d00010_extractMdTables_function_included(self, tmp_path: Path) -> None:
        """GET '/' HTML contains the extractMdTables function name,
        proving _md-table.js.j2 was included in the <script> block."""
        client = _make_app(tmp_path)
        resp = client.get("/")
        assert resp.status_code == 200
        html = resp.text
        assert (
            "extractMdTables" in html
        ), "Expected 'extractMdTables' function name in the rendered viewer HTML"

    def test_REQ_d00010_reinsertMdTables_function_included(self, tmp_path: Path) -> None:
        """GET '/' HTML contains the reinsertMdTables function name,
        proving the JS partial is fully embedded (not truncated)."""
        client = _make_app(tmp_path)
        resp = client.get("/")
        assert resp.status_code == 200
        html = resp.text
        assert (
            "reinsertMdTables" in html
        ), "Expected 'reinsertMdTables' function name in the rendered viewer HTML"

    def test_REQ_d00010_md_table_css_selector_and_border_collapse(self, tmp_path: Path) -> None:
        """GET '/' HTML contains the .md-table CSS selector and
        'border-collapse: collapse' rule, proving _md-tables.css.j2 was
        included in the <style> block."""
        client = _make_app(tmp_path)
        resp = client.get("/")
        assert resp.status_code == 200
        html = resp.text
        assert ".md-table" in html, "Expected '.md-table' CSS selector in the rendered viewer HTML"
        assert (
            "border-collapse: collapse" in html
        ), "Expected 'border-collapse: collapse' rule in the rendered viewer HTML"

    def test_REQ_d00010_md_table_full_grid_border_rule(self, tmp_path: Path) -> None:
        """GET '/' HTML contains the full-grid border rule on <th>/<td>
        cells: a 1px solid border in the expected hex colour."""
        client = _make_app(tmp_path)
        resp = client.get("/")
        assert resp.status_code == 200
        html = resp.text
        assert "1px solid #ced4da" in html, (
            "Expected '1px solid #ced4da' border rule on .md-table cells "
            "in the rendered viewer HTML"
        )
