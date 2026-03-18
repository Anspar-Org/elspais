# Verifies: REQ-d00200-A, REQ-d00200-B, REQ-d00200-C, REQ-d00200-D
# Verifies: REQ-d00200-E, REQ-d00200-F, REQ-d00200-G, REQ-d00200-H
"""Tests for FederatedGraph read-only delegation.

Validates REQ-d00200: FederatedGraph wraps one or more TraceGraphs,
providing a unified read-only view across repositories.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from elspais.config import config_defaults
from elspais.graph.builder import TraceGraph
from elspais.graph.federated import FederatedGraph, RepoEntry
from elspais.graph.GraphNode import NodeKind
from elspais.graph.mutations import MutationEntry
from elspais.graph.relations import EdgeKind
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
def config() -> dict:
    """Create a minimal config dict."""
    return config_defaults()


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
        self, simple_graph: TraceGraph, config: dict
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
        self, simple_graph: TraceGraph, config: dict
    ) -> None:
        """find_by_id delegates to underlying TraceGraph, returns None for missing."""
        fed = FederatedGraph.from_single(simple_graph, config, repo_root=Path("/repo/core"))
        # Found
        node = fed.find_by_id("REQ-p00001")
        assert node is not None
        assert node.id == "REQ-p00001"

        # Missing
        assert fed.find_by_id("REQ-NONEXISTENT") is None

    def test_REQ_d00200_D_has_root_delegates(self, simple_graph: TraceGraph, config: dict) -> None:
        """has_root checks root status correctly."""
        fed = FederatedGraph.from_single(simple_graph, config, repo_root=Path("/repo/core"))
        # REQ-p00001 is a root (PRD with no parents)
        assert fed.has_root("REQ-p00001") is True
        # REQ-d00001 implements REQ-p00001 so is not a root
        assert fed.has_root("REQ-d00001") is False
        # Non-existent
        assert fed.has_root("REQ-MISSING") is False

    def test_REQ_d00200_E_iter_roots_aggregates(
        self, simple_graph: TraceGraph, config: dict
    ) -> None:
        """iter_roots returns all roots from the underlying graph."""
        fed = FederatedGraph.from_single(simple_graph, config, repo_root=Path("/repo/core"))
        root_ids = {r.id for r in fed.iter_roots()}
        # simple_graph has REQ-p00001 as root (DEV implements it, so not root)
        assert "REQ-p00001" in root_ids

    def test_REQ_d00200_E_all_nodes_aggregates(
        self, simple_graph: TraceGraph, config: dict
    ) -> None:
        """all_nodes yields all nodes from the underlying graph."""
        fed = FederatedGraph.from_single(simple_graph, config, repo_root=Path("/repo/core"))
        fed_ids = {n.id for n in fed.all_nodes()}
        graph_ids = {n.id for n in simple_graph.all_nodes()}
        assert fed_ids == graph_ids

    def test_REQ_d00200_E_node_count_aggregates(
        self, simple_graph: TraceGraph, config: dict
    ) -> None:
        """node_count returns correct total from underlying graph."""
        fed = FederatedGraph.from_single(simple_graph, config, repo_root=Path("/repo/core"))
        assert fed.node_count() == simple_graph.node_count()

    def test_REQ_d00200_E_root_count_aggregates(
        self, simple_graph: TraceGraph, config: dict
    ) -> None:
        """root_count returns correct total."""
        fed = FederatedGraph.from_single(simple_graph, config, repo_root=Path("/repo/core"))
        assert fed.root_count() == simple_graph.root_count()

    def test_REQ_d00200_E_iter_by_kind_aggregates(
        self, graph_with_code: TraceGraph, config: dict
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
        self, simple_graph: TraceGraph, config: dict
    ) -> None:
        """orphaned_nodes works through FederatedGraph."""
        fed = FederatedGraph.from_single(simple_graph, config, repo_root=Path("/repo/core"))
        fed_orphans = {n.id for n in fed.orphaned_nodes()}
        graph_orphans = {n.id for n in simple_graph.orphaned_nodes()}
        assert fed_orphans == graph_orphans
        # Also check convenience methods
        assert fed.has_orphans() == simple_graph.has_orphans()
        assert fed.orphan_count() == simple_graph.orphan_count()

    def test_REQ_d00200_E_broken_references_aggregates(self, config: dict) -> None:
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
        self, simple_graph: TraceGraph, config: dict
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
            config=config_defaults(),
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
        self, simple_graph: TraceGraph, config: dict
    ) -> None:
        """repo_for returns the RepoEntry owning a given node."""
        fed = FederatedGraph.from_single(simple_graph, config, repo_root=Path("/repo/core"))
        entry = fed.repo_for("REQ-p00001")
        assert entry is not None
        assert entry.graph is simple_graph
        assert entry.repo_root == Path("/repo/core")

    def test_REQ_d00200_G_config_for_returns_config(
        self, simple_graph: TraceGraph, config: dict
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
                config=config_defaults(),
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
        self, graph_with_code: TraceGraph, config: dict
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


# === Mutation Tests ===


class TestFederatedGraphMutations:
    """Tests for FederatedGraph mutation delegation.

    Validates REQ-d00201-A: by_id mutations delegate to correct sub-graph
    Validates REQ-d00201-B: unified mutation log records entries
    Validates REQ-d00201-C: undo delegates to correct sub-graph
    Validates REQ-d00201-D: add_requirement with target_repo
    Validates REQ-d00201-E: cross-graph edge mutations
    Validates REQ-d00201-F: mutation_log iter_entries yields MutationEntry
    Validates REQ-d00201-G: clone creates independent copy
    """

    @pytest.fixture()
    def fed_with_graph(self) -> FederatedGraph:
        """Create a FederatedGraph with a PRD and DEV requirement."""
        graph = build_graph(
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
        config = config_defaults()
        return FederatedGraph.from_single(graph, config, repo_root=Path("/repo/core"))

    @pytest.fixture()
    def fed_with_unlinked(self) -> FederatedGraph:
        """Create a FederatedGraph with a requirement and unlinked code node."""
        graph = build_graph(
            make_requirement("REQ-p00010", title="Feature", level="PRD"),
            make_requirement(
                "REQ-d00010",
                title="Dev Feature",
                level="DEV",
                source_path="spec/dev.md",
            ),
            make_code_ref(["REQ-p00010"], source_path="src/feature.py"),
            repo_root=Path("/repo/core"),
        )
        config = config_defaults()
        return FederatedGraph.from_single(graph, config, repo_root=Path("/repo/core"))

    def test_REQ_d00201_A_rename_node_delegates_and_updates_ownership(
        self, fed_with_graph: FederatedGraph
    ) -> None:
        """rename_node delegates to sub-graph and updates _ownership map."""
        fed = fed_with_graph
        # Rename REQ-d00001 -> REQ-d00099
        fed.rename_node("REQ-d00001", "REQ-d00099")

        # Old ID should not be found
        assert fed.find_by_id("REQ-d00001") is None
        # New ID should be found
        node = fed.find_by_id("REQ-d00099")
        assert node is not None
        assert node.id == "REQ-d00099"
        # repo_for should work with new ID
        entry = fed.repo_for("REQ-d00099")
        assert entry.name == "root"

    def test_REQ_d00201_A_update_title_delegates(self, fed_with_graph: FederatedGraph) -> None:
        """update_title delegates to sub-graph, node label changes."""
        fed = fed_with_graph
        fed.update_title("REQ-p00001", "Updated Title")

        node = fed.find_by_id("REQ-p00001")
        assert node is not None
        assert node.get_label() == "Updated Title"

    def test_REQ_d00201_A_change_status_delegates(self, fed_with_graph: FederatedGraph) -> None:
        """change_status delegates to sub-graph, status field changes."""
        fed = fed_with_graph
        fed.change_status("REQ-p00001", "Deprecated")

        node = fed.find_by_id("REQ-p00001")
        assert node is not None
        assert node.get_field("status") == "Deprecated"

    def test_REQ_d00201_A_delete_requirement_removes_ownership(
        self, fed_with_graph: FederatedGraph
    ) -> None:
        """delete_requirement removes node from graph and ownership map."""
        fed = fed_with_graph
        fed.delete_requirement("REQ-d00001")

        assert fed.find_by_id("REQ-d00001") is None

    def test_REQ_d00201_B_mutation_log_records_entries(
        self, fed_with_graph: FederatedGraph
    ) -> None:
        """After a mutation, mutation_log.iter_entries() yields entries."""
        fed = fed_with_graph
        fed.update_title("REQ-p00001", "New Title")

        entries = list(fed.mutation_log.iter_entries())
        assert len(entries) >= 1
        # Most recent entry should be about the title update
        last = entries[-1]
        assert last.operation == "update_title"
        assert last.target_id == "REQ-p00001"

    def test_REQ_d00201_C_undo_last_delegates_to_subgraph(
        self, fed_with_graph: FederatedGraph
    ) -> None:
        """undo_last reverts the most recent mutation via the correct sub-graph."""
        fed = fed_with_graph
        original_title = fed.find_by_id("REQ-p00001").get_label()
        fed.update_title("REQ-p00001", "Temporary Title")
        assert fed.find_by_id("REQ-p00001").get_label() == "Temporary Title"

        fed.undo_last()
        assert fed.find_by_id("REQ-p00001").get_label() == original_title

    def test_REQ_d00201_C_undo_to_reverts_multiple(self, fed_with_graph: FederatedGraph) -> None:
        """undo_to reverts all mutations back to (and including) the specified one."""
        fed = fed_with_graph
        original_title = fed.find_by_id("REQ-p00001").get_label()

        # First mutation
        fed.update_title("REQ-p00001", "Title A")
        entries = list(fed.mutation_log.iter_entries())
        first_mutation_id = entries[-1].id

        # Second mutation
        fed.update_title("REQ-p00001", "Title B")
        assert fed.find_by_id("REQ-p00001").get_label() == "Title B"

        # Undo back to the first mutation (both should revert)
        fed.undo_to(first_mutation_id)
        assert fed.find_by_id("REQ-p00001").get_label() == original_title

    def test_REQ_d00201_D_add_requirement_to_root_repo(
        self, fed_with_graph: FederatedGraph
    ) -> None:
        """add_requirement without target_repo adds to root repo."""
        fed = fed_with_graph
        fed.add_requirement("REQ-d00050", "New Requirement", level="DEV")

        node = fed.find_by_id("REQ-d00050")
        assert node is not None
        assert node.get_label() == "New Requirement"
        # Should be in root repo
        entry = fed.repo_for("REQ-d00050")
        assert entry.name == "root"

    def test_REQ_d00201_E_add_edge_within_same_repo(
        self, fed_with_unlinked: FederatedGraph
    ) -> None:
        """add_edge creates an edge between two nodes in the same repo."""
        fed = fed_with_unlinked
        # REQ-d00010 exists but has no implements edge — add one
        fed.add_edge("REQ-d00010", "REQ-p00010", EdgeKind.IMPLEMENTS)

        # Verify the edge exists by checking the node's parents
        node = fed.find_by_id("REQ-d00010")
        assert node is not None
        parent_ids = {p.id for p in node.iter_parents(edge_kinds={EdgeKind.IMPLEMENTS})}
        assert "REQ-p00010" in parent_ids

    def test_REQ_d00201_E_delete_edge_delegates(self, fed_with_graph: FederatedGraph) -> None:
        """delete_edge removes an existing edge via delegation."""
        fed = fed_with_graph
        # REQ-d00001 implements REQ-p00001 — delete that edge
        fed.delete_edge("REQ-d00001", "REQ-p00001")

        node = fed.find_by_id("REQ-d00001")
        assert node is not None
        parent_ids = {p.id for p in node.iter_parents(edge_kinds={EdgeKind.IMPLEMENTS})}
        assert "REQ-p00001" not in parent_ids

    def test_REQ_d00201_F_mutation_log_iter_entries_compatible(
        self, fed_with_graph: FederatedGraph
    ) -> None:
        """iter_entries yields MutationEntry objects with expected fields."""
        fed = fed_with_graph
        fed.update_title("REQ-p00001", "Check Entry Type")

        entries = list(fed.mutation_log.iter_entries())
        assert len(entries) >= 1
        for entry in entries:
            assert isinstance(entry, MutationEntry)
            assert hasattr(entry, "id")
            assert hasattr(entry, "operation")
            assert hasattr(entry, "target_id")
            assert hasattr(entry, "timestamp")

    def test_REQ_d00201_G_clone_creates_independent_copy(
        self, fed_with_graph: FederatedGraph
    ) -> None:
        """clone() creates an independent copy; mutations on clone don't affect original."""
        fed = fed_with_graph
        original_title = fed.find_by_id("REQ-p00001").get_label()

        cloned = fed.clone()
        cloned.update_title("REQ-p00001", "Cloned Title")

        # Clone should have new title
        assert cloned.find_by_id("REQ-p00001").get_label() == "Cloned Title"
        # Original should be unchanged
        assert fed.find_by_id("REQ-p00001").get_label() == original_title
