# Implements: REQ-d00252
"""Tests for cross-graph Integrates: edge wiring during federation.

Validates REQ-d00252-C, REQ-d00252-D, REQ-d00252-E: a consumer requirement
declares ``Integrates: <associate REQ id>`` to say its implementation is
provided by a requirement in a configured associate (external library) repo.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from elspais.config import get_config
from elspais.graph.factory import build_graph
from elspais.graph.metrics import direct_coverage_for
from elspais.graph.relations import EdgeKind
from elspais.graph.render import render_node

FIX = Path(__file__).parents[2] / "fixtures" / "e2e-integrates"


def _federate(app_root: Path):
    """Build a FederatedGraph rooted at ``app_root``."""
    return build_graph(
        config=get_config(None, app_root),
        repo_root=app_root,
        scan_code=False,
        scan_tests=False,
    )


def _copy_full(tmp_path: Path) -> Path:
    """Copy the whole fixture (app + library) to tmp; return the app root."""
    dest = tmp_path / "proj"
    shutil.copytree(FIX, dest)
    return dest / "app"


def _copy_app_only(tmp_path: Path) -> Path:
    """Copy only the app/ tree to tmp so ``../library`` does not exist."""
    dest = tmp_path / "proj"
    (dest).mkdir(parents=True)
    shutil.copytree(FIX / "app", dest / "app")
    return dest / "app"


def _outgoing_integrates(node):
    return [e for e in node.iter_outgoing_edges() if e.kind == EdgeKind.INTEGRATES]


class TestIntegratesWiresEdge:
    """Validates REQ-d00252-D: wire an INTEGRATES edge from consumer to library."""

    def test_REQ_d00252_D_integrates_wires_cross_graph_edge(self, tmp_path):
        app_root = _copy_full(tmp_path)
        fed = _federate(app_root)
        app_req = fed._repos["app"].graph._index["APP-d00001"]
        edges = _outgoing_integrates(app_req)
        assert len(edges) == 1
        assert edges[0].target.id == "LIB-d00007"

    def test_REQ_d00252_D_consumer_requirement_is_implemented(self, tmp_path):
        app_root = _copy_full(tmp_path)
        fed = _federate(app_root)
        app_req = fed._repos["app"].graph._index["APP-d00001"]
        assert direct_coverage_for(app_req) >= 1

    def test_REQ_d00252_D_library_node_unmodified(self, tmp_path):
        app_root = _copy_full(tmp_path)
        fed = _federate(app_root)
        lib_req = fed._repos["library"].graph._index["LIB-d00007"]
        assert "APP-d00001" not in render_node(lib_req)


class TestIntegratesUnresolved:
    """Validates REQ-d00252-E: unresolved targets are soft or hard per claim."""

    def test_REQ_d00252_E_absent_associate_is_soft(self, tmp_path):
        # Copy only app/ so ../library does not exist: associate soft-fails.
        app_root = _copy_app_only(tmp_path)
        fed = _federate(app_root)  # must not raise
        brs = fed._repos["app"].graph._broken_references
        matches = [b for b in brs if b.target_id == "LIB-d00007"]
        assert len(matches) == 1
        assert matches[0].presumed_foreign is True

    def test_REQ_d00252_E_configured_but_missing_is_hard(self, tmp_path):
        app_root = _copy_full(tmp_path)
        spec = app_root / "spec" / "dev-app.md"
        spec.write_text(
            spec.read_text().replace("**Integrates**: LIB-d00007", "**Integrates**: LIB-d99999")
        )
        fed = _federate(app_root)
        brs = fed._repos["app"].graph._broken_references
        matches = [b for b in brs if b.target_id == "LIB-d99999"]
        assert len(matches) == 1
        assert matches[0].presumed_foreign is False


class TestIntegratesSameRepo:
    """Validates REQ-d00252-C: a same-repo target is an external-only violation."""

    def test_REQ_d00252_C_same_repo_target_is_error(self, tmp_path):
        # Add a second app REQ and point Integrates at it (same repo).
        app_root = _copy_full(tmp_path)
        spec = app_root / "spec" / "dev-app.md"
        text = spec.read_text().replace("**Integrates**: LIB-d00007", "**Integrates**: APP-d00002")
        text += (
            "\n\n# APP-d00002: Local helper\n\n"
            "**Level**: dev | **Status**: Active | **Implements**: -\n\n"
            "A locally-provided helper.\n\n"
            "## Assertions\n\n"
            "A. The helper SHALL exist.\n\n"
            "*End* *Local helper* | **Hash**: 00000000\n"
        )
        spec.write_text(text)
        fed = _federate(app_root)
        app_req = fed._repos["app"].graph._index["APP-d00001"]
        # No INTEGRATES edge created for a same-repo target.
        assert _outgoing_integrates(app_req) == []
        brs = fed._repos["app"].graph._broken_references
        matches = [b for b in brs if b.target_id == "APP-d00002"]
        assert len(matches) == 1
