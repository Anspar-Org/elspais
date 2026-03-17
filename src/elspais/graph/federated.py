# Implements: REQ-d00200-A+B+C+D+E+F+G+H
"""FederatedGraph — wraps one or more TraceGraphs with per-repo config.

Provides a unified read-only API across multiple repository graphs,
delegating to the appropriate sub-graph based on node ownership.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from elspais.graph.GraphNode import GraphNode, NodeKind

if TYPE_CHECKING:
    from elspais.config import ConfigLoader
    from elspais.graph.builder import TraceGraph
    from elspais.graph.mutations import BrokenReference


# Implements: REQ-d00200-A
@dataclass
class RepoEntry:
    """A single repository's graph paired with its config.

    Attributes:
        name: Repository name (e.g. "root", "core", "module-a").
        graph: The repo's TraceGraph, or None if repo unavailable.
        config: The repo's ConfigLoader, or None if repo unavailable.
        repo_root: Expected local filesystem path.
        git_origin: Remote URL for clone assistance.
        error: Human-readable error message if repo is in error state.
    """

    name: str
    graph: TraceGraph | None
    config: ConfigLoader | None
    repo_root: Path
    git_origin: str | None = None
    error: str | None = None


class FederatedGraph:
    """Wraps one or more TraceGraph instances with per-repo config isolation.

    All consumers interact with FederatedGraph rather than TraceGraph directly.
    Each method documents its federation strategy:
    - by_id: look up owning graph via _ownership, delegate
    - aggregate: combine results from all graphs (skip None graphs)
    - special: custom logic
    """

    def __init__(
        self,
        repos: list[RepoEntry],
        root_repo: str | None = None,
    ) -> None:
        self._repos: dict[str, RepoEntry] = {r.name: r for r in repos}
        self._root_repo = root_repo or (repos[0].name if repos else "")
        # Build ownership map: node_id -> repo name
        self._ownership: dict[str, str] = {}
        for entry in repos:
            if entry.graph is not None:
                for node_id in entry.graph._index:
                    self._ownership[node_id] = entry.name

    # Implements: REQ-d00200-B
    @classmethod
    def from_single(
        cls,
        graph: TraceGraph,
        config: ConfigLoader | None,
        repo_root: Path,
    ) -> FederatedGraph:
        """Create a federation-of-one from a single TraceGraph.

        Args:
            graph: The single TraceGraph to wrap.
            config: Config for this repo.
            repo_root: Filesystem path to the repo root.

        Returns:
            A FederatedGraph wrapping a single repo.
        """
        entry = RepoEntry(
            name="root",
            graph=graph,
            config=config,
            repo_root=repo_root,
        )
        return cls([entry], root_repo="root")

    # ─────────────────────────────────────────────────────────────────────────
    # Repo Access
    # ─────────────────────────────────────────────────────────────────────────

    # Implements: REQ-d00200-G
    def repo_for(self, node_id: str) -> RepoEntry:
        """Return the RepoEntry for the graph owning node_id.

        # Strategy: by_id

        Raises:
            KeyError: If node_id is not found in any repo.
        """
        repo_name = self._ownership.get(node_id)
        if repo_name is None:
            raise KeyError(f"Node '{node_id}' not found in any repo")
        return self._repos[repo_name]

    # Implements: REQ-d00200-G
    def config_for(self, node_id: str) -> ConfigLoader | None:
        """Return the ConfigLoader for the repo owning node_id.

        # Strategy: by_id
        """
        return self.repo_for(node_id).config

    # Implements: REQ-d00200-H
    def iter_repos(self) -> Iterator[RepoEntry]:
        """Yield all RepoEntry objects including error-state repos.

        # Strategy: all
        """
        yield from self._repos.values()

    def _live_graphs(self) -> Iterator[tuple[str, TraceGraph]]:
        """Yield (name, graph) for repos with non-None graphs."""
        for entry in self._repos.values():
            if entry.graph is not None:
                yield entry.name, entry.graph

    # ─────────────────────────────────────────────────────────────────────────
    # Read-Only Methods
    # ─────────────────────────────────────────────────────────────────────────

    # Implements: REQ-d00200-D
    def find_by_id(self, node_id: str) -> GraphNode | None:
        """Find node by ID across all repos.

        # Strategy: by_id
        """
        repo_name = self._ownership.get(node_id)
        if repo_name is None:
            return None
        graph = self._repos[repo_name].graph
        if graph is None:
            return None
        return graph.find_by_id(node_id)

    # Implements: REQ-d00200-E
    def iter_roots(self, kind: NodeKind | None = None) -> Iterator[GraphNode]:
        """Iterate root nodes from all repos.

        # Strategy: aggregate
        """
        for _name, graph in self._live_graphs():
            yield from graph.iter_roots(kind)

    # Implements: REQ-d00200-E
    def all_nodes(self) -> Iterator[GraphNode]:
        """Iterate ALL nodes across all repos, including orphans.

        # Strategy: aggregate
        """
        for _name, graph in self._live_graphs():
            yield from graph.all_nodes()

    # Implements: REQ-d00200-E
    def all_connected_nodes(self, order: str = "pre") -> Iterator[GraphNode]:
        """Iterate nodes reachable from roots across all repos.

        # Strategy: aggregate
        """
        for _name, graph in self._live_graphs():
            yield from graph.all_connected_nodes(order)

    # Implements: REQ-d00200-E
    def nodes_by_kind(self, kind: NodeKind) -> Iterator[GraphNode]:
        """Get all nodes of a specific kind across all repos.

        # Strategy: aggregate
        """
        for _name, graph in self._live_graphs():
            yield from graph.nodes_by_kind(kind)

    # Implements: REQ-d00200-E
    def iter_by_kind(self, kind: NodeKind) -> Iterator[GraphNode]:
        """Iterate all nodes of a specific kind across all repos.

        # Strategy: aggregate
        """
        for _name, graph in self._live_graphs():
            yield from graph.iter_by_kind(kind)

    # Implements: REQ-d00200-E
    def node_count(self) -> int:
        """Return total number of nodes across all repos.

        # Strategy: aggregate
        """
        return sum(graph.node_count() for _name, graph in self._live_graphs())

    # Implements: REQ-d00200-E
    def root_count(self) -> int:
        """Return total number of root nodes across all repos.

        # Strategy: aggregate
        """
        return sum(graph.root_count() for _name, graph in self._live_graphs())

    # Implements: REQ-d00200-D
    def has_root(self, node_id: str) -> bool:
        """Check if a node ID is a root in any repo.

        # Strategy: by_id
        """
        repo_name = self._ownership.get(node_id)
        if repo_name is None:
            return False
        graph = self._repos[repo_name].graph
        if graph is None:
            return False
        return graph.has_root(node_id)

    # Implements: REQ-d00200-E
    def orphaned_nodes(self) -> Iterator[GraphNode]:
        """Iterate orphaned nodes across all repos.

        # Strategy: aggregate
        """
        for _name, graph in self._live_graphs():
            yield from graph.orphaned_nodes()

    # Implements: REQ-d00200-E
    def has_orphans(self) -> bool:
        """Check if any repo has orphaned nodes.

        # Strategy: aggregate
        """
        return any(graph.has_orphans() for _name, graph in self._live_graphs())

    # Implements: REQ-d00200-E
    def orphan_count(self) -> int:
        """Return total orphaned node count across all repos.

        # Strategy: aggregate
        """
        return sum(graph.orphan_count() for _name, graph in self._live_graphs())

    # Implements: REQ-d00200-E
    def broken_references(self) -> list[BrokenReference]:
        """Get all broken references across all repos.

        # Strategy: aggregate
        """
        result: list[BrokenReference] = []
        for _name, graph in self._live_graphs():
            result.extend(graph.broken_references())
        return result

    # Implements: REQ-d00200-E
    def has_broken_references(self) -> bool:
        """Check if any repo has broken references.

        # Strategy: aggregate
        """
        return any(graph.has_broken_references() for _name, graph in self._live_graphs())

    def is_reachable_to_requirement(self, node: GraphNode) -> bool:
        """Check if node can reach a REQUIREMENT via traceability edges.

        # Strategy: special — works via object references, crosses graph boundaries
        """
        # Delegate to the owning graph — traversal crosses boundaries naturally
        repo_name = self._ownership.get(node.id)
        if repo_name is None:
            return False
        graph = self._repos[repo_name].graph
        if graph is None:
            return False
        return graph.is_reachable_to_requirement(node)

    # Implements: REQ-d00200-E
    def iter_unlinked(self, kind: NodeKind) -> Iterator[GraphNode]:
        """Iterate unlinked nodes of given kind across all repos.

        # Strategy: aggregate
        """
        for _name, graph in self._live_graphs():
            yield from graph.iter_unlinked(kind)

    # Implements: REQ-d00200-E
    def iter_structural_orphans(self) -> Iterator[GraphNode]:
        """Iterate structurally orphaned nodes across all repos.

        # Strategy: aggregate
        """
        for _name, graph in self._live_graphs():
            yield from graph.iter_structural_orphans()

    # Implements: REQ-d00200-E
    def deleted_nodes(self) -> list[GraphNode]:
        """Get all deleted nodes across all repos.

        # Strategy: aggregate
        """
        result: list[GraphNode] = []
        for _name, graph in self._live_graphs():
            result.extend(graph.deleted_nodes())
        return result

    # Implements: REQ-d00200-E
    def has_deletions(self) -> bool:
        """Check if any repo has deleted nodes.

        # Strategy: aggregate
        """
        return any(graph.has_deletions() for _name, graph in self._live_graphs())
