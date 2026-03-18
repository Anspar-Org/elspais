# Implements: REQ-d00200-A+B+C+D+E+F+G+H
# Implements: REQ-d00201-A+B+C+D+E+F+G
"""FederatedGraph — wraps one or more TraceGraphs with per-repo config.

Provides a unified API across multiple repository graphs,
delegating to the appropriate sub-graph based on node ownership.
"""

from __future__ import annotations

import copy
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from elspais.graph.GraphNode import GraphNode, NodeKind
from elspais.graph.mutations import MutationEntry
from elspais.graph.relations import EdgeKind

if TYPE_CHECKING:
    from elspais.config import ConfigLoader
    from elspais.graph.builder import TraceGraph
    from elspais.graph.mutations import BrokenReference


# Implements: REQ-d00201-B
@dataclass
class FederatedMutationPointer:
    """Lightweight entry in the federated mutation log.

    Points to a sub-graph's mutation by repo name and mutation ID.
    """

    repo_name: str
    mutation_id: str


class FederatedMutationLog:
    """Unified mutation log across all repos in a federation.

    Stores lightweight pointers to sub-graph mutations. The iter_entries()
    method follows pointers to yield full MutationEntry objects from sub-graphs,
    maintaining compatibility with existing consumers.
    """

    def __init__(self) -> None:
        self._pointers: list[FederatedMutationPointer] = []
        self._repos: dict[str, RepoEntry] = {}

    def _bind_repos(self, repos: dict[str, RepoEntry]) -> None:
        """Bind repo lookup for resolving pointers."""
        self._repos = repos

    def record(self, repo_name: str, mutation_id: str) -> None:
        """Record a mutation pointer."""
        self._pointers.append(FederatedMutationPointer(repo_name, mutation_id))

    def pop(self) -> FederatedMutationPointer | None:
        """Remove and return the most recent pointer."""
        return self._pointers.pop() if self._pointers else None

    def iter_entries(self) -> Iterator[MutationEntry]:
        """Yield full MutationEntry objects from sub-graphs in federated order.

        Compatible with existing MutationLog.iter_entries() consumers.
        """
        for ptr in self._pointers:
            entry = self._repos.get(ptr.repo_name)
            if entry and entry.graph:
                found = entry.graph.mutation_log.find_by_id(ptr.mutation_id)
                if found:
                    yield found

    def entries_since(self, mutation_id: str) -> list[FederatedMutationPointer]:
        """Get all pointers since (and including) a specific mutation."""
        for i, ptr in enumerate(self._pointers):
            if ptr.mutation_id == mutation_id:
                return list(self._pointers[i:])
        raise ValueError(f"Mutation {mutation_id} not found in federated log")

    def find_by_id(self, mutation_id: str) -> MutationEntry | None:
        """Find a mutation entry by ID across all repos."""
        for ptr in self._pointers:
            if ptr.mutation_id == mutation_id:
                entry = self._repos.get(ptr.repo_name)
                if entry and entry.graph:
                    return entry.graph.mutation_log.find_by_id(mutation_id)
        return None

    def clear(self) -> None:
        """Clear all pointers and sub-graph logs."""
        self._pointers.clear()
        for entry in self._repos.values():
            if entry.graph:
                entry.graph.mutation_log.clear()

    def __len__(self) -> int:
        return len(self._pointers)


class FederationError(Exception):
    """Error raised for federation configuration issues.

    Examples: transitive associates, ID conflicts across repos.
    """


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
        # Detect ID conflicts across repos (skip FILE/REMAINDER nodes which
        # naturally have same relative paths across repos)
        self._ownership: dict[str, str] = {}
        _structural_prefixes = ("file:", "remainder:")
        for entry in repos:
            if entry.graph is not None:
                for node_id in entry.graph._index:
                    if node_id in self._ownership:
                        # FILE and REMAINDER nodes may share relative paths
                        if any(node_id.startswith(p) for p in _structural_prefixes):
                            continue
                        existing_repo = self._ownership[node_id]
                        raise FederationError(
                            f"ID conflict: '{node_id}' exists in both "
                            f"'{existing_repo}' and '{entry.name}'"
                        )
                    self._ownership[node_id] = entry.name
        # Wire cross-graph edges after ownership is established
        if len([e for e in repos if e.graph is not None]) > 1:
            self._wire_cross_graph_edges()
        self._annotate_presumed_foreign_refs()
        # Implements: REQ-d00201-B
        self._federated_log = FederatedMutationLog()
        self._federated_log._bind_repos(self._repos)

    # ─────────────────────────────────────────────────────────────────────────
    # Root Repo Convenience Properties
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def repo_root(self) -> Path:
        """Return the root repo's filesystem path."""
        return self._repos[self._root_repo].repo_root

    @property
    def hash_mode(self) -> str:
        """Return the root repo's hash mode."""
        graph = self._repos[self._root_repo].graph
        return graph.hash_mode if graph else "normalized-text"

    @property
    def satellite_kinds(self) -> frozenset:
        """Return the root repo's satellite kinds."""
        graph = self._repos[self._root_repo].graph
        if graph:
            return graph.satellite_kinds
        from elspais.graph.builder import _DEFAULT_SATELLITE_KINDS

        return _DEFAULT_SATELLITE_KINDS

    @classmethod
    def empty(cls) -> FederatedGraph:
        """Create an empty FederatedGraph with no repos.

        Used as an error fallback when graph construction fails.
        """
        from elspais.graph.builder import TraceGraph

        entry = RepoEntry(
            name="root",
            graph=TraceGraph(),
            config=None,
            repo_root=Path("."),
        )
        return cls([entry], root_repo="root")

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

    # ─────────────────────────────────────────────────────────────────────────
    # Mutation Infrastructure
    # ─────────────────────────────────────────────────────────────────────────

    # Implements: REQ-d00201-F
    @property
    def mutation_log(self) -> FederatedMutationLog:
        """Access the unified mutation log across all repos.

        Returns a FederatedMutationLog whose iter_entries() yields full
        MutationEntry objects from sub-graphs in federated order.
        """
        return self._federated_log

    def _graph_for(self, node_id: str) -> TraceGraph:
        """Get the sub-graph owning node_id. Raises KeyError if not found."""
        repo_name = self._ownership.get(node_id)
        if repo_name is None:
            raise KeyError(f"Node '{node_id}' not found in any repo")
        graph = self._repos[repo_name].graph
        if graph is None:
            raise KeyError(f"Repo '{repo_name}' has no graph (error state)")
        return graph

    def _record_mutation(self, repo_name: str, entry: MutationEntry) -> None:
        """Record a mutation in the federated log."""
        self._federated_log.record(repo_name, entry.id)

    # ─────────────────────────────────────────────────────────────────────────
    # by_id Mutation Methods
    # ─────────────────────────────────────────────────────────────────────────

    # Implements: REQ-d00201-A
    def rename_node(self, old_id: str, new_id: str) -> MutationEntry:
        """Rename a node. Updates ownership mapping.

        # Strategy: by_id
        """
        repo_name = self._ownership[old_id]
        graph = self._graph_for(old_id)
        result = graph.rename_node(old_id, new_id)
        # Update ownership: remove old, add new
        del self._ownership[old_id]
        self._ownership[new_id] = repo_name
        # Assertion children also get renamed — update their ownership
        node = graph.find_by_id(new_id)
        if node and node.kind == NodeKind.REQUIREMENT:
            for child in node.iter_children():
                if child.kind == NodeKind.ASSERTION:
                    self._ownership[child.id] = repo_name
                    # Remove old assertion ID if present
                    old_assertion_id = child.id.replace(new_id, old_id)
                    self._ownership.pop(old_assertion_id, None)
        self._record_mutation(repo_name, result)
        return result

    # Implements: REQ-d00201-A
    def update_title(self, node_id: str, new_title: str) -> MutationEntry:
        """Update requirement title.

        # Strategy: by_id
        """
        repo_name = self._ownership[node_id]
        result = self._graph_for(node_id).update_title(node_id, new_title)
        self._record_mutation(repo_name, result)
        return result

    # Implements: REQ-d00201-A
    def change_status(self, node_id: str, new_status: str) -> MutationEntry:
        """Change requirement status.

        # Strategy: by_id
        """
        repo_name = self._ownership[node_id]
        result = self._graph_for(node_id).change_status(node_id, new_status)
        self._record_mutation(repo_name, result)
        return result

    # Implements: REQ-d00201-A
    def delete_requirement(self, node_id: str, compact_assertions: bool = True) -> MutationEntry:
        """Delete a requirement. Removes from ownership.

        # Strategy: by_id
        """
        repo_name = self._ownership[node_id]
        graph = self._graph_for(node_id)
        # Collect assertion IDs before deletion
        node = graph.find_by_id(node_id)
        assertion_ids = []
        if node:
            assertion_ids = [c.id for c in node.iter_children() if c.kind == NodeKind.ASSERTION]
        result = graph.delete_requirement(node_id, compact_assertions)
        # Remove from ownership
        self._ownership.pop(node_id, None)
        for aid in assertion_ids:
            self._ownership.pop(aid, None)
        self._record_mutation(repo_name, result)
        return result

    # Implements: REQ-d00201-A
    def add_assertion(self, req_id: str, label: str, text: str) -> MutationEntry:
        """Add an assertion to a requirement.

        # Strategy: by_id
        """
        repo_name = self._ownership[req_id]
        result = self._graph_for(req_id).add_assertion(req_id, label, text)
        # New assertion gets ownership
        assertion_id = f"{req_id}-{label}"
        self._ownership[assertion_id] = repo_name
        self._record_mutation(repo_name, result)
        return result

    # Implements: REQ-d00201-A
    def delete_assertion(
        self,
        assertion_id: str,
        compact: bool = True,
        compact_style: str = "letter",
    ) -> MutationEntry:
        """Delete an assertion.

        # Strategy: by_id
        """
        repo_name = self._ownership[assertion_id]
        result = self._graph_for(assertion_id).delete_assertion(assertion_id, compact)
        self._ownership.pop(assertion_id, None)
        self._record_mutation(repo_name, result)
        return result

    # Implements: REQ-d00201-A
    def update_assertion(self, assertion_id: str, new_text: str) -> MutationEntry:
        """Update assertion text.

        # Strategy: by_id
        """
        repo_name = self._ownership[assertion_id]
        result = self._graph_for(assertion_id).update_assertion(assertion_id, new_text)
        self._record_mutation(repo_name, result)
        return result

    # Implements: REQ-d00201-A
    def rename_assertion(self, old_id: str, new_label: str) -> MutationEntry:
        """Rename an assertion label.

        # Strategy: by_id
        """
        repo_name = self._ownership[old_id]
        result = self._graph_for(old_id).rename_assertion(old_id, new_label)
        # Update ownership with new ID
        new_id = result.after_state.get("id", old_id)
        if new_id != old_id:
            self._ownership.pop(old_id, None)
            self._ownership[new_id] = repo_name
        self._record_mutation(repo_name, result)
        return result

    # Implements: REQ-d00201-A
    def rename_file(
        self,
        file_id: str,
        new_relative_path: str,
        repo_root: Path | None = None,
    ) -> MutationEntry:
        """Rename a FILE node.

        # Strategy: by_id
        """
        repo_name = self._ownership[file_id]
        graph = self._graph_for(file_id)
        result = graph.rename_file(file_id, new_relative_path, repo_root)
        # Update ownership with new file ID
        new_id = result.after_state.get("id", file_id)
        if new_id != file_id:
            self._ownership.pop(file_id, None)
            self._ownership[new_id] = repo_name
        self._record_mutation(repo_name, result)
        return result

    # Implements: REQ-d00201-A
    def fix_broken_reference(
        self,
        source_id: str,
        old_target_id: str,
        new_target_id: str,
    ) -> MutationEntry:
        """Fix a broken reference by redirecting to a valid target.

        # Strategy: by_id
        """
        repo_name = self._ownership[source_id]
        result = self._graph_for(source_id).fix_broken_reference(
            source_id, old_target_id, new_target_id
        )
        self._record_mutation(repo_name, result)
        return result

    # ─────────────────────────────────────────────────────────────────────────
    # Cross-Graph Mutation Methods
    # ─────────────────────────────────────────────────────────────────────────

    # Implements: REQ-d00201-E
    def add_edge(
        self,
        source_id: str,
        target_id: str,
        edge_kind: EdgeKind,
        assertion_targets: list[str] | None = None,
    ) -> MutationEntry:
        """Add an edge. Source and target may be in different repos.

        # Strategy: cross-graph
        """
        repo_name = self._ownership[source_id]
        graph = self._graph_for(source_id)
        result = graph.add_edge(source_id, target_id, edge_kind, assertion_targets)
        self._record_mutation(repo_name, result)
        return result

    # Implements: REQ-d00201-E
    def delete_edge(self, source_id: str, target_id: str) -> MutationEntry:
        """Delete an edge.

        # Strategy: cross-graph
        """
        repo_name = self._ownership[source_id]
        result = self._graph_for(source_id).delete_edge(source_id, target_id)
        self._record_mutation(repo_name, result)
        return result

    # Implements: REQ-d00201-E
    def change_edge_kind(
        self,
        source_id: str,
        target_id: str,
        new_kind: EdgeKind,
    ) -> MutationEntry:
        """Change edge type.

        # Strategy: cross-graph
        """
        repo_name = self._ownership[source_id]
        result = self._graph_for(source_id).change_edge_kind(source_id, target_id, new_kind)
        self._record_mutation(repo_name, result)
        return result

    # Implements: REQ-d00201-E
    def change_edge_targets(
        self,
        source_id: str,
        target_id: str,
        assertion_targets: list[str],
    ) -> MutationEntry:
        """Change assertion targets on an edge.

        # Strategy: cross-graph
        """
        repo_name = self._ownership[source_id]
        result = self._graph_for(source_id).change_edge_targets(
            source_id, target_id, assertion_targets
        )
        self._record_mutation(repo_name, result)
        return result

    # Implements: REQ-d00201-E
    def move_node_to_file(self, node_id: str, target_file_id: str) -> MutationEntry:
        """Move a node to a different FILE.

        # Strategy: cross-graph
        """
        repo_name = self._ownership[node_id]
        result = self._graph_for(node_id).move_node_to_file(node_id, target_file_id)
        self._record_mutation(repo_name, result)
        return result

    # ─────────────────────────────────────────────────────────────────────────
    # Special Mutations
    # ─────────────────────────────────────────────────────────────────────────

    # Implements: REQ-d00201-D
    def add_requirement(
        self,
        req_id: str,
        title: str,
        level: str,
        status: str = "Draft",
        parent_id: str | None = None,
        edge_kind: EdgeKind = EdgeKind.IMPLEMENTS,
        target_repo: str | None = None,
    ) -> MutationEntry:
        """Add a new requirement to a specific repo.

        # Strategy: special — target_repo specifies destination
        """
        repo_name = target_repo or self._root_repo
        entry = self._repos.get(repo_name)
        if entry is None or entry.graph is None:
            raise KeyError(f"Repo '{repo_name}' not found or unavailable")
        result = entry.graph.add_requirement(req_id, title, level, status, parent_id, edge_kind)
        self._ownership[req_id] = repo_name
        self._record_mutation(repo_name, result)
        return result

    # Implements: REQ-d00201-G
    def clone(self) -> FederatedGraph:
        """Create a deep copy of this federated graph.

        # Strategy: special — deep copy all sub-graphs independently
        """
        return copy.deepcopy(self)

    # ─────────────────────────────────────────────────────────────────────────
    # Cross-Graph Edge Wiring
    # ─────────────────────────────────────────────────────────────────────────

    def _wire_cross_graph_edges(self) -> None:
        """Wire cross-graph edges by resolving broken references across repos.

        For each sub-graph's broken references, check if the target_id exists
        in another sub-graph. If found, create the edge using target_graph
        parameter and remove the broken reference.
        """
        for source_entry in self._repos.values():
            if source_entry.graph is None:
                continue
            resolved: list[int] = []  # indices to remove
            for i, br in enumerate(source_entry.graph._broken_references):
                target_repo_name = self._ownership.get(br.target_id)
                if target_repo_name and target_repo_name != source_entry.name:
                    target_entry = self._repos[target_repo_name]
                    if target_entry.graph is not None:
                        # Wire the cross-graph edge
                        source_entry.graph.add_edge(
                            br.source_id,
                            br.target_id,
                            EdgeKind(br.edge_kind),
                            target_graph=target_entry.graph,
                        )
                        resolved.append(i)
            # Remove resolved broken references (reverse to preserve indices)
            for idx in reversed(resolved):
                source_entry.graph._broken_references.pop(idx)

    def _annotate_presumed_foreign_refs(self) -> None:
        """Mark remaining broken references whose target doesn't match the source repo's ID pattern.

        Called after _wire_cross_graph_edges(). Any broken ref whose target_id
        cannot be parsed by the source repo's IdResolver is presumed to belong
        to a foreign repo (different namespace/format) and is replaced with a
        BrokenReference with presumed_foreign=True.

        Skipped for repos with no config (annotation requires pattern knowledge).
        """
        from elspais.graph.mutations import BrokenReference
        from elspais.utilities.patterns import build_resolver

        for source_entry in self._repos.values():
            if source_entry.graph is None or source_entry.config is None:
                continue
            resolver = build_resolver(source_entry.config.get_raw())
            refs = source_entry.graph._broken_references
            for i, br in enumerate(refs):
                if not br.presumed_foreign and not resolver.is_local_id(br.target_id):
                    refs[i] = BrokenReference(
                        source_id=br.source_id,
                        target_id=br.target_id,
                        edge_kind=br.edge_kind,
                        presumed_foreign=True,
                    )

    # ─────────────────────────────────────────────────────────────────────────
    # Undo Operations
    # ─────────────────────────────────────────────────────────────────────────

    # Implements: REQ-d00201-C
    def undo_last(self) -> MutationEntry | None:
        """Undo the most recent mutation across all repos.

        Reads the federated log to identify which repo was last mutated,
        then delegates undo to that sub-graph.
        """
        ptr = self._federated_log.pop()
        if ptr is None:
            return None
        entry = self._repos.get(ptr.repo_name)
        if entry and entry.graph:
            result = entry.graph.undo_last()
            if result:
                # Reverse any ownership changes
                self._rebuild_ownership()
            return result
        return None

    # Implements: REQ-d00201-C
    def undo_to(self, mutation_id: str) -> list[MutationEntry]:
        """Undo all mutations back to (and including) a specific mutation.

        Reads the federated log and delegates undo to the correct sub-graphs.
        """
        pointers = self._federated_log.entries_since(mutation_id)
        undone: list[MutationEntry] = []
        # Undo in reverse order
        for _ in range(len(pointers)):
            result = self.undo_last()
            if result:
                undone.append(result)
        return undone

    def _rebuild_ownership(self) -> None:
        """Rebuild the ownership map from all sub-graph indexes."""
        self._ownership.clear()
        for entry in self._repos.values():
            if entry.graph is not None:
                for node_id in entry.graph._index:
                    self._ownership[node_id] = entry.name
