# Validates: REQ-d00200-A, REQ-d00200-B, REQ-d00200-C, REQ-d00200-D
# Validates: REQ-d00200-E, REQ-d00200-F, REQ-d00200-G, REQ-d00200-H
"""Tests for FederatedGraph read-only delegation.

Validates REQ-d00200: FederatedGraph wraps one or more TraceGraphs,
providing a unified read-only view across repositories.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from elspais.config import ConfigLoader
from elspais.graph.builder import TraceGraph
from elspais.graph.federated import FederatedGraph, RepoEntry
from elspais.graph.GraphNode import NodeKind
from tests.core.graph_test_helpers import (
    build_graph,
    make_code_ref,
    make_requirement,
    make_test_ref,
)

# === Fixtures ===


@pytest.fixture()
def simple_graph() -> TraceGraph:
    """Build a small graph with a PRD requirement and a DEV that implements it."""
    return build_graph(
        make_requirement("REQ-p00001", title="Parent PRD", level="PRD"),
        make_requirement(
            "REQ-d00001",
            title="Child DEV",
            level="DEV",
            implements=["REQ-p00001"],
            source_path="spec/dev.md",
        ),
        repo_root=Path("/repo/core"),
    )


@pytest.fixture()
def graph_with_code() -> TraceGraph:
    """Build a graph with a requirement, code ref, and test ref."""
    return build_graph(
        make_requirement("REQ-p00010", title="Feature", level="PRD"),
        make_code_ref(["REQ-p00010"], source_path="src/feature.py"),
        make_test_ref(["REQ-p00010"], source_path="tests/test_feature.py"),
        repo_root=Path("/repo/core"),
    )


@pytest.fixture()
def config() -> ConfigLoader:
    """Create a minimal ConfigLoader."""
    return ConfigLoader.from_dict({})


# === Tests ===


class TestFederatedGraphReadOnly:
    """Tests for FederatedGraph as a read-only wrapper around TraceGraph.

    Validates REQ-d00200-A: RepoEntry dataclass fields
    Validates REQ-d00200-B: from_single classmethod
    Validates REQ-d00200-C: is_reachable_to_requirement delegation
    Validates REQ-d00200-D: by_id delegation (find_by_id, has_root)
    Validates REQ-d00200-E: aggregate delegation (iter_roots, all_nodes, etc.)
    Validates REQ-d00200-F: error-state repos skipped in aggregation
    Validates REQ-d00200-G: repo_for and config_for lookups
    Validates REQ-d00200-H: iter_repos yields all entries including errors
    """

    def test_REQ_d00200_A_repo_entry_dataclass(self) -> None:
        """RepoEntry has all required fields with correct defaults."""
        entry = RepoEntry(
            name="core",
            graph=None,
            config=None,
            repo_root=Path("/repo/core"),
        )
        assert entry.name == "core"
        assert entry.graph is None
        assert entry.config is None
        assert entry.repo_root == Path("/repo/core")
        assert entry.git_origin is None
        assert entry.error is None

    def test_REQ_d00200_A_repo_entry_with_optional_fields(self) -> None:
        """RepoEntry accepts git_origin and error fields."""
        entry = RepoEntry(
            name="associated",
            graph=None,
            config=None,
            repo_root=Path("/repo/assoc"),
            git_origin="git@github.com:org/assoc.git",
            error="Config file not found",
        )
        assert entry.git_origin == "git@github.com:org/assoc.git"
        assert entry.error == "Config file not found"

    def test_REQ_d00200_B_from_single_creates_federation_of_one(
        self, simple_graph: TraceGraph, config: ConfigLoader
    ) -> None:
        """from_single wraps a single TraceGraph into a FederatedGraph."""
        fed = FederatedGraph.from_single(simple_graph, config, repo_root=Path("/repo/core"))
        # Should have exactly one repo entry
        repos = list(fed.iter_repos())
        assert len(repos) == 1
        assert repos[0].graph is simple_graph
        assert repos[0].config is config
        assert repos[0].repo_root == Path("/repo/core")

    def test_REQ_d00200_D_find_by_id_delegates(
        self, simple_graph: TraceGraph, config: ConfigLoader
    ) -> None:
        """find_by_id delegates to underlying TraceGraph, returns None for missing."""
        fed = FederatedGraph.from_single(simple_graph, config, repo_root=Path("/repo/core"))
        # Found
        node = fed.find_by_id("REQ-p00001")
        assert node is not None
        assert node.id == "REQ-p00001"

        # Missing
        assert fed.find_by_id("REQ-NONEXISTENT") is None

    def test_REQ_d00200_D_has_root_delegates(
        self, simple_graph: TraceGraph, config: ConfigLoader
    ) -> None:
        """has_root checks root status correctly."""
        fed = FederatedGraph.from_single(simple_graph, config, repo_root=Path("/repo/core"))
        # REQ-p00001 is a root (PRD with no parents)
        assert fed.has_root("REQ-p00001") is True
        # REQ-d00001 implements REQ-p00001 so is not a root
        assert fed.has_root("REQ-d00001") is False
        # Non-existent
        assert fed.has_root("REQ-MISSING") is False

    def test_REQ_d00200_E_iter_roots_aggregates(
        self, simple_graph: TraceGraph, config: ConfigLoader
    ) -> None:
        """iter_roots returns all roots from the underlying graph."""
        fed = FederatedGraph.from_single(simple_graph, config, repo_root=Path("/repo/core"))
        root_ids = {r.id for r in fed.iter_roots()}
        # simple_graph has REQ-p00001 as root (DEV implements it, so not root)
        assert "REQ-p00001" in root_ids

    def test_REQ_d00200_E_all_nodes_aggregates(
        self, simple_graph: TraceGraph, config: ConfigLoader
    ) -> None:
        """all_nodes yields all nodes from the underlying graph."""
        fed = FederatedGraph.from_single(simple_graph, config, repo_root=Path("/repo/core"))
        fed_ids = {n.id for n in fed.all_nodes()}
        graph_ids = {n.id for n in simple_graph.all_nodes()}
        assert fed_ids == graph_ids

    def test_REQ_d00200_E_node_count_aggregates(
        self, simple_graph: TraceGraph, config: ConfigLoader
    ) -> None:
        """node_count returns correct total from underlying graph."""
        fed = FederatedGraph.from_single(simple_graph, config, repo_root=Path("/repo/core"))
        assert fed.node_count() == simple_graph.node_count()

    def test_REQ_d00200_E_root_count_aggregates(
        self, simple_graph: TraceGraph, config: ConfigLoader
    ) -> None:
        """root_count returns correct total."""
        fed = FederatedGraph.from_single(simple_graph, config, repo_root=Path("/repo/core"))
        assert fed.root_count() == simple_graph.root_count()

    def test_REQ_d00200_E_iter_by_kind_aggregates(
        self, graph_with_code: TraceGraph, config: ConfigLoader
    ) -> None:
        """iter_by_kind filters by NodeKind correctly."""
        fed = FederatedGraph.from_single(graph_with_code, config, repo_root=Path("/repo/core"))
        # Check requirement nodes
        req_ids = {n.id for n in fed.iter_by_kind(NodeKind.REQUIREMENT)}
        graph_req_ids = {n.id for n in graph_with_code.iter_by_kind(NodeKind.REQUIREMENT)}
        assert req_ids == graph_req_ids

        # Check code nodes
        code_nodes = list(fed.iter_by_kind(NodeKind.CODE))
        graph_code = list(graph_with_code.iter_by_kind(NodeKind.CODE))
        assert len(code_nodes) == len(graph_code)

    def test_REQ_d00200_E_orphaned_nodes_aggregates(
        self, simple_graph: TraceGraph, config: ConfigLoader
    ) -> None:
        """orphaned_nodes works through FederatedGraph."""
        fed = FederatedGraph.from_single(simple_graph, config, repo_root=Path("/repo/core"))
        fed_orphans = {n.id for n in fed.orphaned_nodes()}
        graph_orphans = {n.id for n in simple_graph.orphaned_nodes()}
        assert fed_orphans == graph_orphans
        # Also check convenience methods
        assert fed.has_orphans() == simple_graph.has_orphans()
        assert fed.orphan_count() == simple_graph.orphan_count()

    def test_REQ_d00200_E_broken_references_aggregates(self, config: ConfigLoader) -> None:
        """broken_references combines lists from all repos."""
        # Build graph with a broken reference (implements non-existent ID)
        graph = build_graph(
            make_requirement(
                "REQ-d00099",
                title="Broken",
                level="DEV",
                implements=["REQ-p99999"],
            ),
            repo_root=Path("/repo/core"),
        )
        fed = FederatedGraph.from_single(graph, config, repo_root=Path("/repo/core"))
        fed_broken = fed.broken_references()
        graph_broken = graph.broken_references()
        assert len(fed_broken) == len(graph_broken)
        assert fed.has_broken_references() == graph.has_broken_references()

    def test_REQ_d00200_E_deleted_nodes_aggregates(
        self, simple_graph: TraceGraph, config: ConfigLoader
    ) -> None:
        """deleted_nodes combines lists from all repos."""
        fed = FederatedGraph.from_single(simple_graph, config, repo_root=Path("/repo/core"))
        assert fed.deleted_nodes() == simple_graph.deleted_nodes()
        assert fed.has_deletions() == simple_graph.has_deletions()

    def test_REQ_d00200_F_skips_error_state_repos(self) -> None:
        """Aggregate methods skip repos where graph is None (error state)."""
        # Build one working graph
        good_graph = build_graph(
            make_requirement("REQ-p00001", title="Good", level="PRD"),
            repo_root=Path("/repo/good"),
        )
        good_entry = RepoEntry(
            name="good",
            graph=good_graph,
            config=ConfigLoader.from_dict({}),
            repo_root=Path("/repo/good"),
        )
        error_entry = RepoEntry(
            name="broken",
            graph=None,
            config=None,
            repo_root=Path("/repo/broken"),
            error="Failed to load config",
        )
        fed = FederatedGraph([good_entry, error_entry])

        # Aggregations should only include the good graph
        assert fed.node_count() == good_graph.node_count()
        all_ids = {n.id for n in fed.all_nodes()}
        good_ids = {n.id for n in good_graph.all_nodes()}
        assert all_ids == good_ids

        # find_by_id should still work for good graph nodes
        assert fed.find_by_id("REQ-p00001") is not None

    def test_REQ_d00200_G_repo_for_returns_entry(
        self, simple_graph: TraceGraph, config: ConfigLoader
    ) -> None:
        """repo_for returns the RepoEntry owning a given node."""
        fed = FederatedGraph.from_single(simple_graph, config, repo_root=Path("/repo/core"))
        entry = fed.repo_for("REQ-p00001")
        assert entry is not None
        assert entry.graph is simple_graph
        assert entry.repo_root == Path("/repo/core")

    def test_REQ_d00200_G_config_for_returns_config(
        self, simple_graph: TraceGraph, config: ConfigLoader
    ) -> None:
        """config_for returns the ConfigLoader for the repo owning a node."""
        fed = FederatedGraph.from_single(simple_graph, config, repo_root=Path("/repo/core"))
        result = fed.config_for("REQ-p00001")
        assert result is config

    def test_REQ_d00200_H_iter_repos_yields_all(self) -> None:
        """iter_repos yields all entries, including error-state repos."""
        good_graph = build_graph(
            make_requirement("REQ-p00001", title="Good", level="PRD"),
            repo_root=Path("/repo/good"),
        )
        entries = [
            RepoEntry(
                name="good",
                graph=good_graph,
                config=ConfigLoader.from_dict({}),
                repo_root=Path("/repo/good"),
            ),
            RepoEntry(
                name="broken",
                graph=None,
                config=None,
                repo_root=Path("/repo/broken"),
                error="Load failed",
            ),
        ]
        fed = FederatedGraph(entries)

        repos = list(fed.iter_repos())
        assert len(repos) == 2
        names = {r.name for r in repos}
        assert names == {"good", "broken"}

    def test_REQ_d00200_C_is_reachable_to_requirement_works(
        self, graph_with_code: TraceGraph, config: ConfigLoader
    ) -> None:
        """is_reachable_to_requirement works through FederatedGraph."""
        fed = FederatedGraph.from_single(graph_with_code, config, repo_root=Path("/repo/core"))
        # Code ref should be reachable to a requirement
        code_nodes = list(fed.iter_by_kind(NodeKind.CODE))
        assert len(code_nodes) > 0
        for code_node in code_nodes:
            assert fed.is_reachable_to_requirement(code_node) is True

        # A root requirement has no traceability ancestors, so not "reachable"
        req_node = fed.find_by_id("REQ-p00010")
        assert req_node is not None
        assert fed.is_reachable_to_requirement(req_node) is False
