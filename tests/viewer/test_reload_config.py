# Validates REQ-p00004-J, REQ-p00004-O
"""Tests for /api/reload and /api/revert config refresh and freshness state.

Validates:
- REQ-p00004-J: The tool SHALL re-read configuration from disk when reloading
  the graph, ensuring branch switches with different configurations produce
  correct rebuilds.
- REQ-p00004-O: When the tool reloads the graph from disk, the tool SHALL
  bring the change-detection state it holds for the reloaded content into
  agreement with that content, so that no subsequent staleness check reports
  change the completed reload has already absorbed.
"""

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from elspais.graph import GraphNode, NodeKind
from elspais.graph.builder import TraceGraph
from elspais.server.app import create_app
from elspais.server.state import AppState

_REAL_CONFIG = """\
version = 3

[project]
name = "test"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[levels.prd]
rank = 1
letter = "p"
implements = ["prd"]

[levels.ops]
rank = 2
letter = "o"
implements = ["ops", "prd"]

[levels.dev]
rank = 3
letter = "d"
implements = ["dev", "ops", "prd"]
"""

_REAL_SPEC = """\
### REQ-p00001: Reload Freshness Probe

**Level**: PRD | **Status**: Active

The system SHALL absorb its own reloads.

## Assertions

A. The system SHALL leave no staleness a completed reload already absorbed.

*End* *Reload Freshness Probe* | **Hash**: 00000000
"""


def _real_repo(tmp_path: Path) -> Path:
    """A repo with a parsable config and one real spec file on disk."""
    (tmp_path / ".elspais.toml").write_text(_REAL_CONFIG)
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    (spec_dir / "core.md").write_text(_REAL_SPEC)
    return spec_dir / "core.md"


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
        config_path.write_text(
            'version = 3\n[project]\nname = "test"\nnamespace = "REQ"\n'
            '[scanning.spec]\ndirectories = ["spec"]\n'
        )

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
            'version = 3\n[project]\nname = "test"\nnamespace = "REQ"\n'
            '[scanning.spec]\ndirectories = ["spec", "extra-specs"]\n'
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

        # Verify build_graph was called with the REFRESHED config (from disk).
        # Note: config files are part of the staleness mtime snapshot, so the
        # freshness middleware may rebuild once before /api/reload does —
        # every rebuild must use the refreshed config.
        assert captured_configs
        for refreshed in captured_configs:
            assert "extra-specs" in (
                refreshed.get("scanning", {}).get("spec", {}).get("directories", [])
            )

    def test_REQ_p00004_J_reload_includes_local_overlay(self, tmp_path, _minimal_graph):
        # Verifies: REQ-p00004-J
        """POST /api/reload re-reads config through the same overlay-aware
        path as AppState._rebuild(): a `.elspais.local.toml` alongside the
        base `.elspais.toml` must be merged into the reloaded config.
        """
        config_path = tmp_path / ".elspais.toml"
        config_path.write_text(
            'version = 3\n[project]\nname = "test"\nnamespace = "REQ"\n'
            '[scanning.spec]\ndirectories = ["spec"]\n'
        )

        initial_config = {"scanning": {"spec": {"directories": ["spec"]}}}
        state = AppState(
            graph=_minimal_graph,
            repo_root=tmp_path,
            config=initial_config,
        )
        app = create_app(state=state, mount_mcp=False)
        client = TestClient(app)

        # Developer-local overlay appears on disk after the server started
        (tmp_path / ".elspais.local.toml").write_text(
            '[scanning.spec]\ndirectories = ["spec", "local-only-specs"]\n'
        )

        captured_configs = []

        def fake_build_graph(**kwargs):
            captured_configs.append(kwargs.get("config"))
            return _minimal_graph

        with patch("elspais.graph.factory.build_graph", fake_build_graph):
            resp = client.post("/api/reload")

        data = resp.json()
        assert resp.status_code == 200, f"Reload failed: {data}"
        assert data["success"] is True

        # Every rebuild (middleware freshness pass or the reload handler)
        # must see the overlay-merged directories.
        assert captured_configs
        for refreshed in captured_configs:
            assert "local-only-specs" in (
                refreshed.get("scanning", {}).get("spec", {}).get("directories", [])
            )


class TestReloadAbsorbsChangeDetectionState:
    """Validates REQ-p00004-O: an explicit reload brings the change-detection
    state it holds into agreement with the content it just reloaded.

    The freshness middleware and the reload route both rebuild from the same
    files. If the reload does not re-snapshot what it read, the very next
    request sees the change the reload already absorbed and rebuilds a second
    time -- the same disk read done twice, and a `build_time` that moves for
    a graph nobody changed.
    """

    def test_REQ_p00004_O_reload_leaves_no_redundant_rebuild(self, tmp_path):
        """After POST /api/reload absorbs a disk change, the next freshness
        check must not find that same change still outstanding."""
        spec_file = _real_repo(tmp_path)
        state = AppState.from_config(repo_root=tmp_path)
        client = TestClient(create_app(state=state, mount_mcp=False))

        # The change the reload is going to absorb.
        time.sleep(0.05)
        spec_file.write_text(_REAL_SPEC.replace("SHALL absorb", "SHALL always absorb"))

        # Hold the freshness middleware off this request: the rebuild under
        # test is the reload route's, not a middleware pass that happens to
        # repair the snapshot as a side effect.
        state._last_stale_check = time.time()
        resp = client.post("/api/reload", json={"if_tip_mutation_id": ""})
        assert resp.status_code == 200, resp.json()
        assert resp.json()["success"] is True

        build_time_after_reload = state.build_time

        # Next request's freshness pass, nothing having changed since.
        state._last_stale_check = 0.0
        rebuilt = state.ensure_fresh()

        assert rebuilt is False, (
            "the freshness check after a completed reload reported the change "
            "the reload already absorbed, and rebuilt a second time"
        )
        assert (
            state.build_time == build_time_after_reload
        ), "build_time moved after the reload with nothing changed on disk"

    def test_REQ_p00004_O_reload_syncs_daemon_config_hash(self, tmp_path):
        """A reload that re-read an edited config must leave daemon.json's
        config_hash agreeing with that config, without waiting for a later
        request to repair it."""
        from elspais.mcp.daemon import compute_config_hash

        _real_repo(tmp_path)
        state = AppState.from_config(repo_root=tmp_path)
        client = TestClient(create_app(state=state, mount_mcp=False))

        config_path = tmp_path / ".elspais.toml"
        daemon_json = tmp_path / ".elspais" / "daemon.json"
        daemon_json.parent.mkdir(parents=True, exist_ok=True)
        daemon_json.write_text(
            json.dumps(
                {
                    "pid": 1,
                    "port": 5000,
                    "repo_root": str(tmp_path),
                    "started_at": "2026-01-01T00:00:00",
                    "version": "0.0.0",
                    "config_hash": compute_config_hash(config_path),
                    "type": "viewer",
                }
            )
        )

        # Config edited on disk after the daemon registered itself.
        time.sleep(0.05)
        config_path.write_text(_REAL_CONFIG.replace('name = "test"', 'name = "renamed-on-disk"'))
        stale_hash = json.loads(daemon_json.read_text())["config_hash"]
        assert stale_hash != compute_config_hash(
            config_path
        ), "fixture must present a genuinely stale recorded config hash"

        state._last_stale_check = time.time()  # keep the middleware out of it
        resp = client.post("/api/reload", json={"if_tip_mutation_id": ""})
        assert resp.status_code == 200, resp.json()
        assert resp.json()["success"] is True

        # No further request served.
        assert json.loads(daemon_json.read_text())["config_hash"] == compute_config_hash(
            config_path
        ), "daemon.json still records the config the reload replaced"


class TestRevertRereadsConfig:
    """Validates REQ-p00004-J: POST /api/revert reloads the graph from disk,
    and so must re-read configuration from disk like every other reload
    surface -- a revert taken after a branch switch otherwise rebuilds
    against the configuration of the branch that was left.
    """

    def test_REQ_p00004_J_revert_records_the_on_disk_config(self, tmp_path):
        """After a revert, the config the server holds is the one on disk."""
        _real_repo(tmp_path)
        state = AppState.from_config(repo_root=tmp_path)
        client = TestClient(create_app(state=state, mount_mcp=False))
        assert state.config["project"]["name"] == "test"

        time.sleep(0.05)
        (tmp_path / ".elspais.toml").write_text(
            _REAL_CONFIG.replace('name = "test"', 'name = "renamed-on-disk"')
        )

        state._last_stale_check = time.time()  # keep the middleware out of it
        resp = client.post("/api/revert", json={"if_tip_mutation_id": ""})
        assert resp.status_code == 200, resp.json()
        assert resp.json()["success"] is True

        assert (
            state.config["project"]["name"] == "renamed-on-disk"
        ), "revert rebuilt from the held config instead of re-reading disk"

    def test_REQ_p00004_J_revert_builds_from_the_on_disk_config(self, tmp_path):
        """The graph the revert installs is built from the on-disk config,
        not from the config the server was holding."""
        _real_repo(tmp_path)
        state = AppState.from_config(repo_root=tmp_path)
        client = TestClient(create_app(state=state, mount_mcp=False))

        time.sleep(0.05)
        (tmp_path / ".elspais.toml").write_text(
            _REAL_CONFIG.replace('directories = ["spec"]', 'directories = ["spec", "extra-specs"]')
        )

        from elspais.graph.factory import build_graph as real_build_graph

        captured_configs = []

        def fake_build_graph(**kwargs):
            captured_configs.append(kwargs.get("config"))
            return real_build_graph(**kwargs)

        state._last_stale_check = time.time()  # keep the middleware out of it
        with patch("elspais.graph.factory.build_graph", fake_build_graph):
            resp = client.post("/api/revert", json={"if_tip_mutation_id": ""})

        assert resp.status_code == 200, resp.json()
        assert captured_configs, "revert never built a graph"
        for used in captured_configs:
            assert "extra-specs" in (
                (used or {}).get("scanning", {}).get("spec", {}).get("directories", [])
            ), "revert built the graph from a config it did not re-read from disk"


class TestRevertAbsorbsChangeDetectionState:
    """Validates REQ-p00004-O: POST /api/revert is a reload from disk and must
    absorb the change detection state for what it read, like every other
    reload surface."""

    def test_REQ_p00004_O_revert_leaves_no_redundant_rebuild(self, tmp_path):
        spec_file = _real_repo(tmp_path)
        state = AppState.from_config(repo_root=tmp_path)
        client = TestClient(create_app(state=state, mount_mcp=False))

        time.sleep(0.05)
        spec_file.write_text(_REAL_SPEC.replace("SHALL absorb", "SHALL always absorb"))

        state._last_stale_check = time.time()  # keep the middleware out of it
        resp = client.post("/api/revert", json={"if_tip_mutation_id": ""})
        assert resp.status_code == 200, resp.json()
        build_time_after_revert = state.build_time

        state._last_stale_check = 0.0
        rebuilt = state.ensure_fresh()

        assert rebuilt is False, (
            "the freshness check after a completed revert reported the change "
            "the revert already absorbed, and rebuilt a second time"
        )
        assert state.build_time == build_time_after_revert
