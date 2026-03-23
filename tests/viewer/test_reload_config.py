# Validates REQ-p00004-J
"""Tests for /api/reload config refresh.

Validates:
- REQ-p00004-J: The tool SHALL re-read configuration from disk when reloading
  the graph, ensuring branch switches with different configurations produce
  correct rebuilds.
"""

from pathlib import Path
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from elspais.graph import GraphNode, NodeKind
from elspais.graph.builder import TraceGraph
from elspais.server.app import create_app
from elspais.server.state import AppState


@pytest.fixture
def _minimal_graph():
    """Create a minimal TraceGraph for testing."""
    graph = TraceGraph(repo_root=Path("/test/repo"))
    node = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT, label="Test")
    node._content = {"level": "PRD", "status": "Active", "hash": "abc12345"}
    graph._roots = [node]
    graph._index = {"REQ-p00001": node}
    return graph


class TestReloadRefreshesConfig:
    """Validates REQ-p00004-J: /api/reload re-reads config from disk."""

    def test_REQ_p00004_J_reload_refreshes_config(self, tmp_path, _minimal_graph):
        """After modifying .elspais.toml on disk, POST /api/reload picks up
        the new config values.
        """
        # Write initial config
        config_path = tmp_path / ".elspais.toml"
        config_path.write_text('version = 3\n[scanning.spec]\ndirectories = ["spec"]\n')

        # Create the app with initial config and the tmp_path as working_dir
        initial_config = {"scanning": {"spec": {"directories": ["spec"]}}}
        state = AppState(
            graph=_minimal_graph,
            repo_root=tmp_path,
            config=initial_config,
        )
        app = create_app(state=state, mount_mcp=False)
        client = TestClient(app)

        # Modify config on disk -- add extra-specs directory
        config_path.write_text(
            'version = 3\n[scanning.spec]\ndirectories = ["spec", "extra-specs"]\n'
        )

        # Mock build_graph so we don't need real spec files.
        # We capture the config argument it receives to verify it was refreshed.
        captured_configs = []

        def fake_build_graph(**kwargs):
            captured_configs.append(kwargs.get("config"))
            return _minimal_graph

        with patch("elspais.graph.factory.build_graph", fake_build_graph):
            resp = client.post("/api/reload")

        data = resp.json()
        assert resp.status_code == 200, f"Reload failed: {data}"
        assert data["success"] is True

        # Verify build_graph was called with the REFRESHED config (from disk)
        assert len(captured_configs) == 1
        refreshed = captured_configs[0]
        assert "extra-specs" in refreshed.get("scanning", {}).get("spec", {}).get("directories", [])
