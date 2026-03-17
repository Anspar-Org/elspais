# Validates REQ-d00205-A, REQ-d00205-B, REQ-d00205-C, REQ-d00205-D
"""Tests for MCP server federation support.

Validates REQ-d00205: MCP server uses per-repo config from FederatedGraph
instead of a single global config for all operations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from elspais.config import ConfigLoader
from elspais.graph import GraphNode, NodeKind
from elspais.graph.builder import TraceGraph
from elspais.graph.federated import FederatedGraph, RepoEntry
from elspais.graph.relations import EdgeKind

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_config(**overrides: Any) -> ConfigLoader:
    """Create a ConfigLoader with specific project settings."""
    data: dict[str, Any] = {}
    for key, value in overrides.items():
        parts = key.split(".")
        d = data
        for part in parts[:-1]:
            d = d.setdefault(part, {})
        d[parts[-1]] = value
    return ConfigLoader.from_dict(data)


def _make_simple_graph(
    req_id: str, label: str, level: str, repo_root: Path | None = None
) -> TraceGraph:
    """Create a TraceGraph with a single requirement + assertion."""
    graph = TraceGraph(repo_root=repo_root or Path("/test/repo"))
    node = GraphNode(id=req_id, kind=NodeKind.REQUIREMENT, label=label)
    node._content = {"level": level, "status": "Active", "hash": "aabb1122"}
    assertion = GraphNode(id=f"{req_id}-A", kind=NodeKind.ASSERTION, label="SHALL do something")
    assertion._content = {"label": "A"}
    node.link(assertion, EdgeKind.STRUCTURES)
    graph._roots = [node]
    graph._index = {req_id: node, f"{req_id}-A": assertion}
    return graph


def _make_two_repo_federation(
    *,
    root_config: ConfigLoader | None = None,
    assoc_config: ConfigLoader | None = None,
    assoc_error: str | None = None,
) -> FederatedGraph:
    """Build a 2-repo FederatedGraph for testing.

    The root repo has REQ-p00001, the associate has REQ-a00001.
    """
    root_graph = _make_simple_graph("REQ-p00001", "Root Requirement", "PRD", Path("/repo/root"))
    root_cfg = root_config or _make_config(
        **{"project.name": "RootProject", "project.namespace": "ROOT"}
    )

    if assoc_error:
        assoc_entry = RepoEntry(
            name="associate",
            graph=None,
            config=None,
            repo_root=Path("/repo/associate"),
            git_origin="https://github.com/org/associate.git",
            error=assoc_error,
        )
    else:
        assoc_graph = _make_simple_graph(
            "REQ-a00001", "Associate Requirement", "OPS", Path("/repo/associate")
        )
        assoc_cfg = assoc_config or _make_config(
            **{"project.name": "AssocProject", "project.namespace": "ASSOC"}
        )
        assoc_entry = RepoEntry(
            name="associate",
            graph=assoc_graph,
            config=assoc_cfg,
            repo_root=Path("/repo/associate"),
            git_origin="https://github.com/org/associate.git",
        )

    root_entry = RepoEntry(
        name="root",
        graph=root_graph,
        config=root_cfg,
        repo_root=Path("/repo/root"),
    )
    return FederatedGraph([root_entry, assoc_entry], root_repo="root")


# ─────────────────────────────────────────────────────────────────────────────
# Tests: REQ-d00205-A — workspace info includes federation details
# ─────────────────────────────────────────────────────────────────────────────


class TestWorkspaceInfoFederation:
    """Validates REQ-d00205-A: get_workspace_info() includes federation details."""

    def test_REQ_d00205_A_workspace_info_includes_federation_repos(self):
        """get_workspace_info() with multi-repo graph includes federation section.

        Validates REQ-d00205-A: The default workspace info response includes
        a 'federation' section listing repo names, paths, and status.
        """
        pytest.importorskip("mcp")
        from elspais.mcp.server import _get_workspace_info

        fed = _make_two_repo_federation()
        root_cfg = fed._repos["root"].config
        config_dict = root_cfg._data if root_cfg else {}

        result = _get_workspace_info(
            Path("/repo/root"),
            config=config_dict,
            graph=fed,
            detail="default",
        )

        # The response must include a 'federation' section
        assert (
            "federation" in result
        ), "Workspace info must include a 'federation' section when graph has multiple repos"
        federation = result["federation"]

        # Must list repos with name, path, status fields
        assert "repos" in federation
        repos = federation["repos"]
        assert len(repos) >= 2

        repo_names = {r["name"] for r in repos}
        assert "root" in repo_names
        assert "associate" in repo_names

        for repo in repos:
            assert "name" in repo
            assert "path" in repo
            assert "status" in repo

    def test_REQ_d00205_A_workspace_info_federation_includes_error_state(self):
        """get_workspace_info() includes error state for unavailable repos.

        Validates REQ-d00205-A: Federation section includes error info
        for repos in error state.
        """
        pytest.importorskip("mcp")
        from elspais.mcp.server import _get_workspace_info

        fed = _make_two_repo_federation(assoc_error="Clone failed: repo not found")
        root_cfg = fed._repos["root"].config
        config_dict = root_cfg._data if root_cfg else {}

        result = _get_workspace_info(
            Path("/repo/root"),
            config=config_dict,
            graph=fed,
            detail="default",
        )

        assert "federation" in result
        repos = result["federation"]["repos"]
        assoc_repos = [r for r in repos if r["name"] == "associate"]
        assert len(assoc_repos) == 1

        assoc = assoc_repos[0]
        assert assoc["status"] == "error" or "error" in assoc
        # Error message should be present
        assert "error" in assoc or "error_message" in assoc
        error_msg = assoc.get("error") or assoc.get("error_message", "")
        assert "Clone failed" in str(error_msg)


# ─────────────────────────────────────────────────────────────────────────────
# Tests: REQ-d00205-B — refresh_graph syncs config
# ─────────────────────────────────────────────────────────────────────────────


class TestRefreshGraphSyncsConfig:
    """Validates REQ-d00205-B: refresh_graph() syncs _state config."""

    def test_REQ_d00205_B_refresh_graph_syncs_config_after_rebuild(self, tmp_path):
        """After non-path refresh, _state['config'] is synced from rebuilt graph.

        Validates REQ-d00205-B: When refresh_graph() is called WITHOUT a path
        argument, _state['config'] must still be updated from the rebuilt
        FederatedGraph's root repo config. Currently the handler only updates
        _state['config'] when a path is provided, leaving it stale otherwise.
        """
        pytest.importorskip("mcp")
        from elspais.mcp.server import _refresh_graph

        # Create a config that will change between builds
        config_file = tmp_path / ".elspais.toml"
        config_file.write_text('[project]\nname = "OriginalName"\nnamespace = "OG"\n')
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        # Change the config on disk before refresh
        config_file.write_text('[project]\nname = "UpdatedName"\nnamespace = "UP"\n')

        result, new_graph = _refresh_graph(tmp_path)
        assert result["success"] is True

        # The handler should sync _state["config"] from the rebuilt graph.
        # Verify the rebuilt graph carries the updated config.
        root_entry = next(new_graph.iter_repos())
        assert root_entry.config is not None

        # The result dict should include the new config so the handler
        # can sync _state["config"]. This is the missing feature.
        assert "config" in result, (
            "_refresh_graph() must return config in its result dict "
            "so the handler can sync _state['config'] after non-path rebuilds"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Tests: REQ-d00205-C — node-specific config
# ─────────────────────────────────────────────────────────────────────────────


class TestNodeSpecificConfig:
    """Validates REQ-d00205-C: Node-specific ops use per-repo config."""

    def test_REQ_d00205_C_normalize_targets_uses_graph_config(self):
        """_normalize_assertion_targets uses the target node's repo config.

        Validates REQ-d00205-C: When normalizing assertion targets for
        an edge mutation, the config should come from graph.config_for(node_id)
        rather than a global _state['config'].
        """
        pytest.importorskip("mcp")
        from elspais.mcp.server import _normalize_assertion_targets

        # Build a federation where root and associate have different configs
        # but matching namespace (REQ) so IdResolver can parse IDs
        root_cfg = _make_config(**{"project.name": "Root", "project.namespace": "REQ"})
        assoc_cfg = _make_config(**{"project.name": "Assoc", "project.namespace": "REQ"})
        fed = _make_two_repo_federation(root_config=root_cfg, assoc_config=assoc_cfg)

        from elspais.config import ConfigLoader

        # Get per-repo config via graph.config_for() — the correct pattern
        # Note: use REQ-p00001 (root node, type 'p') since 'a' isn't a valid type letter
        root_config_loader = fed.config_for("REQ-p00001")
        assert root_config_loader is not None
        root_config_dict = (
            root_config_loader._data
            if isinstance(root_config_loader, ConfigLoader)
            else root_config_loader
        )
        result = _normalize_assertion_targets(
            targets=["REQ-p00001-A"],
            target_id="REQ-p00001",
            config=root_config_dict,
        )
        # Should normalize "REQ-p00001-A" to just "A"
        assert "A" in result


# ─────────────────────────────────────────────────────────────────────────────
# Tests: REQ-d00205-D — global ops use root config
# ─────────────────────────────────────────────────────────────────────────────


class TestGlobalOpsUseRootConfig:
    """Validates REQ-d00205-D: Global ops use root repo config."""

    def test_REQ_d00205_D_workspace_info_uses_root_config(self):
        """get_workspace_info() extracts root config from graph for global ops.

        Validates REQ-d00205-D: When a FederatedGraph is provided,
        _get_workspace_info should be able to derive the root repo config
        from the graph itself (via iter_repos()), not require it to be
        passed separately. This ensures global ops always use the root config
        even when _state["config"] is stale.
        """
        pytest.importorskip("mcp")
        from elspais.mcp.server import _get_workspace_info

        root_cfg = _make_config(**{"project.name": "MainProject", "project.namespace": "MAIN"})
        assoc_cfg = _make_config(**{"project.name": "LibProject", "project.namespace": "LIB"})
        fed = _make_two_repo_federation(root_config=root_cfg, assoc_config=assoc_cfg)

        # Pass NO config — the function should derive it from the graph's
        # root repo. This tests that global ops can self-serve from the
        # FederatedGraph when config is not explicitly provided.
        result = _get_workspace_info(
            Path("/repo/root"),
            config=None,  # Should derive from graph's root repo
            graph=fed,
            detail="default",
        )

        # Project name and prefix must come from root config, not associate
        assert result["project_name"] == "MainProject"
        assert result["config_summary"]["prefix"] == "MAIN"
