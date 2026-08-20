# Validates REQ-d00205-A, REQ-d00205-B, REQ-d00205-C, REQ-d00205-D
"""Tests for MCP server federation support.

Validates REQ-d00205: MCP server uses per-repo config from FederatedGraph
instead of a single global config for all operations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from elspais.config import _merge_configs, config_defaults
from elspais.graph import GraphNode, NodeKind
from elspais.graph.builder import TraceGraph
from elspais.graph.federated import FederatedGraph, RepoEntry
from elspais.graph.relations import EdgeKind
from tests.federation_repos import make_repo

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_config(**overrides: Any) -> dict[str, Any]:
    """Create a config dict with specific project settings."""
    data: dict[str, Any] = {}
    for key, value in overrides.items():
        parts = key.split(".")
        d = data
        for part in parts[:-1]:
            d = d.setdefault(part, {})
        d[parts[-1]] = value
    return _merge_configs(config_defaults(), data)


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
    root_config: dict[str, Any] | None = None,
    assoc_config: dict[str, Any] | None = None,
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
# Verifies: REQ-d00205-A
# Workspace info includes federation details.
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
        config_dict = fed._repos["root"].config or {}

        result = _get_workspace_info(
            Path("/repo/root"),
            config=config_dict,
            graph=fed,
            detail="default",
        )

        # The response must include a 'federation' section
        assert "federation" in result, (
            "Workspace info must include a 'federation' section when graph has multiple repos"
        )
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
        config_dict = fed._repos["root"].config or {}

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
# Verifies: REQ-d00205-B
# refresh_graph syncs config.
# ─────────────────────────────────────────────────────────────────────────────


class TestRefreshGraphSyncsConfig:
    """Validates REQ-d00205-B: refresh_graph() syncs _state config."""

    def test_REQ_d00205_B_refresh_graph_syncs_config_after_rebuild(self, tmp_path):
        """A rebuild publishes the rebuilt graph's root repo config.

        Validates REQ-d00205-B: a refresh that is not given a path must still
        leave the holder's config equal to the rebuilt FederatedGraph's root
        repo config, so every surface reading through the holder sees what was
        just loaded from disk rather than a stale copy.
        """
        pytest.importorskip("mcp")
        from elspais.mcp.shared_state import SharedServerState, rebuild_shared_graph

        # Create a config that will change between builds
        config_file = tmp_path / ".elspais.toml"
        config_file.write_text('[project]\nname = "OriginalName"\nnamespace = "OG"\n')
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        # Change the config on disk before refresh
        config_file.write_text('[project]\nname = "UpdatedName"\nnamespace = "UP"\n')

        state = SharedServerState({"working_dir": tmp_path})
        result = rebuild_shared_graph(state)
        assert result["success"] is True

        # The rebuilt graph carries the updated config.
        new_graph = state["graph"]
        root_entry = next(new_graph.iter_repos())
        assert root_entry.config is not None
        assert root_entry.config.get("project", {}).get("name") == "UpdatedName"

        # The holder's config IS that root repo config, not merely reported.
        assert result["config"] is not None
        assert state["config"] is result["config"]
        assert state["config"] is root_entry.config


# ─────────────────────────────────────────────────────────────────────────────
# Verifies: REQ-d00205-C
# Node-specific config.
# ─────────────────────────────────────────────────────────────────────────────


class TestNodeSpecificConfig:
    """Validates REQ-d00205-C: Node-specific ops use per-repo config."""

    # Verifies: REQ-d00205-C
    def test_REQ_d00205_C_normalize_targets_uses_graph_config(self):
        """_mutate_add_edge normalizes targets under the OWNING repo's config.

        Validates REQ-d00205-C: no config is passed to _mutate_add_edge --
        production must resolve graph.config_for(target_id) itself. The
        target lives in an ASSOCIATE repo whose namespace (ASSOC) the root
        config (ROOT) cannot parse, so a regression to the global/root
        config leaves the raw full assertion id on the edge and the test
        fails.
        """
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_add_edge
        from elspais.utilities.patterns import build_resolver

        root_cfg = _make_config(**{"project.name": "Root", "project.namespace": "ROOT"})
        assoc_cfg = _make_config(**{"project.name": "Assoc", "project.namespace": "ASSOC"})

        # This is what makes the test discriminating: the root grammar
        # cannot read the associate's assertion id at all, so only the
        # associate's own config can produce the bare label.
        assert build_resolver(root_cfg).parse("ASSOC-o00001-A") is None
        assert build_resolver(assoc_cfg).parse("ASSOC-o00001-A") is not None

        root_graph = _make_simple_graph(
            "ROOT-p00001", "Root Requirement", "PRD", Path("/repo/root")
        )
        assoc_graph = _make_simple_graph(
            "ASSOC-o00001", "Associate Target", "OPS", Path("/repo/associate")
        )
        # A second associate-owned node to be the edge source. Indexed
        # BEFORE the FederatedGraph is built -- ownership is snapshotted
        # at construction.
        source = GraphNode(id="ASSOC-d00001", kind=NodeKind.REQUIREMENT, label="Associate Source")
        source._content = {"level": "DEV", "status": "Active", "hash": "ccdd3344"}
        assoc_graph._index["ASSOC-d00001"] = source

        fed = FederatedGraph(
            [
                RepoEntry(
                    name="root",
                    graph=root_graph,
                    config=root_cfg,
                    repo_root=Path("/repo/root"),
                ),
                RepoEntry(
                    name="associate",
                    graph=assoc_graph,
                    config=assoc_cfg,
                    repo_root=Path("/repo/associate"),
                    git_origin="https://github.com/org/associate.git",
                ),
            ],
            root_repo="root",
        )

        result = _mutate_add_edge(
            fed,
            source_id="ASSOC-d00001",
            target_id="ASSOC-o00001",
            edge_kind="IMPLEMENTS",
            assertion_targets=["ASSOC-o00001-A"],
        )

        assert result["success"] is True
        target = fed.find_by_id("ASSOC-o00001")
        edges = [
            e
            for e in target.iter_outgoing_edges()
            if e.kind == EdgeKind.IMPLEMENTS and e.target.id == "ASSOC-d00001"
        ]
        assert len(edges) == 1
        # Normalized to the bare label under the ASSOCIATE's grammar.
        assert edges[0].assertion_targets == ["A"]


# ─────────────────────────────────────────────────────────────────────────────
# Verifies: REQ-d00205-D
# Global ops use root config.
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


# ─────────────────────────────────────────────────────────────────────────────
# Verifies: REQ-d00202-D, REQ-d00203-B
# One federation, one member list.
# ─────────────────────────────────────────────────────────────────────────────


class TestWorkspaceInfoAssociatesAgreeWithFederation:
    """One tool, one membership answer, whether or not a graph is in hand."""

    def test_associates_and_federation_repos_agree(self):
        """The associates block is the federation's repos less the root.

        Verifies: REQ-d00202-D
        """
        pytest.importorskip("mcp")
        from elspais.mcp.server import _get_workspace_info

        root_graph = _make_simple_graph("REQ-p00001", "Root", "PRD", Path("/repo/root"))
        entries = [
            RepoEntry(name="root", graph=root_graph, config=_make_config(), repo_root=Path("/r")),
            RepoEntry(
                name="direct",
                graph=_make_simple_graph("REQ-a00001", "Direct", "OPS", Path("/repo/direct")),
                config=_make_config(),
                repo_root=Path("/repo/direct"),
            ),
            RepoEntry(
                name="transitive",
                graph=_make_simple_graph("REQ-b00001", "Transitive", "OPS", Path("/repo/deep")),
                config=_make_config(),
                repo_root=Path("/repo/deep"),
            ),
        ]
        fed = FederatedGraph(entries, root_repo="root")

        result = _get_workspace_info(
            Path("/r"), config=_make_config(), graph=fed, detail="worktree"
        )

        associates = result["associates"]
        names = {a["name"] for a in associates["associates"]}
        assert names == {"direct", "transitive"}
        assert associates["count"] == len(result["federation"]["repos"]) - 1
        assert {a["path"] for a in associates["associates"]} == {"/repo/direct", "/repo/deep"}

    def test_associates_without_graph_include_transitive_members(self, tmp_path: Path):
        """Without a graph, membership still comes from the whole federation.

        Verifies: REQ-d00203-B
        """
        pytest.importorskip("mcp")
        from elspais.config import get_config
        from elspais.mcp.server import _get_workspace_info

        make_repo(tmp_path, "leaf", namespace="LEAF", req_id="LEAF-d00001")
        make_repo(
            tmp_path,
            "mid",
            namespace="MID",
            associates={"leaf": "../leaf"},
            associate_namespaces={"leaf": "LEAF"},
            req_id="MID-d00001",
        )
        root = make_repo(
            tmp_path,
            "root",
            namespace="ROOT",
            associates={"mid": "../mid"},
            associate_namespaces={"mid": "MID"},
            req_id="ROOT-d00001",
        )

        config = get_config(config_path=root / ".elspais.toml", quiet=True)
        result = _get_workspace_info(root, config=config, graph=None, detail="worktree")

        associates = result["associates"]
        assert {a["name"] for a in associates["associates"]} == {"mid", "leaf"}
        assert associates["count"] == 2
