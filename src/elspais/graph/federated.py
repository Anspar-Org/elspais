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
from typing import TYPE_CHECKING, Any

from elspais.graph.GraphNode import (
    STRUCTURAL_ID_PREFIXES,
    FileType,
    GraphNode,
    NodeKind,
)
from elspais.graph.mutations import BrokenReference, MutationEntry
from elspais.graph.relations import EdgeKind

if TYPE_CHECKING:
    from elspais.graph.builder import TraceGraph
    from elspais.graph.comments import CommentThread
    from elspais.graph.terms import TermDictionary
    from elspais.utilities.patterns import IdResolver


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
        name: Repository name. For the host repo, the value of
            ``[project].name`` from the config (``load_config()`` rejects
            empty/missing names at the TOML boundary; ``config_defaults()``
            provides ``"example"`` for the fresh-directory / no-config-file
            path). For associates, the key under ``[associates]``.
        graph: The repo's TraceGraph, or None if repo unavailable.
        config: The repo's config dict, or None if repo unavailable.
        repo_root: Expected local filesystem path.
        git_origin: Remote URL for clone assistance.
        error: Human-readable error message if repo is in error state.
    """

    name: str
    graph: TraceGraph | None
    config: dict[str, Any] | None
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
        # Invariant: every RepoEntry must carry a non-empty ``name`` and
        # ``repo_root``. When the backing config declares a ``[project]``
        # section, that section must carry non-empty ``name`` and
        # ``namespace`` — the three identifiers (host-side handle,
        # display name, REQ-id prefix) are distinct and downstream
        # consumers (term cards, file routing, viewer namespace labels,
        # render save) assume all three are present. The ``[project]``
        # presence check is permissive on empty ``config={}`` so isolated
        # unit tests that wire a TraceGraph straight into a RepoEntry
        # don't need to fabricate a full config dict; production callers
        # always go through ``load_config()`` which produces a populated
        # ``[project]`` block.
        for r in repos:
            if not r.name or not str(r.name).strip():
                raise FederationError(
                    "RepoEntry.name must be non-empty (this is the host-side "
                    "handle: [project].name for the host, the [associates.<key>] "
                    "key for an associate)"
                )
            if r.repo_root is None or str(r.repo_root) == "":
                raise FederationError(f"RepoEntry({r.name!r}).repo_root must be set")
            if r.config and "project" in r.config:
                project = r.config["project"] or {}
                if not project.get("name") or not str(project["name"]).strip():
                    raise FederationError(
                        f"RepoEntry({r.name!r}).config is missing non-empty "
                        f"[project].name; load_config() should enforce this "
                        f"at the TOML boundary"
                    )
                if not project.get("namespace") or not str(project["namespace"]).strip():
                    raise FederationError(
                        f"RepoEntry({r.name!r}).config is missing non-empty "
                        f"[project].namespace; load_config() should enforce "
                        f"this at the TOML boundary"
                    )

        self._repos: dict[str, RepoEntry] = {r.name: r for r in repos}
        self._root_repo = root_repo or (repos[0].name if repos else "")
        # Build ownership map: node_id -> repo name
        # Detect ID conflicts across repos (skip FILE/REMAINDER nodes which
        # naturally have same relative paths across repos)
        self._ownership: dict[str, str] = {}
        for entry in repos:
            if entry.graph is not None:
                for node_id in entry.graph._index:
                    if node_id in self._ownership:
                        # FILE and REMAINDER nodes may share relative paths
                        if node_id.startswith(STRUCTURAL_ID_PREFIXES):
                            continue
                        existing_repo = self._ownership[node_id]
                        raise FederationError(
                            f"ID conflict: '{node_id}' exists in both "
                            f"'{existing_repo}' and '{entry.name}'"
                        )
                    self._ownership[node_id] = entry.name
        # Cache of per-repo IdResolvers, populated on first access by
        # ``_resolver_for``.  Cross-repo ownership / canonicalisation
        # probes hit this cache instead of rebuilding the resolver on
        # every call.  Lazy so repos with ``config is None`` (error
        # state) and repos never probed pay no cost.
        self._resolver_cache: dict[str, IdResolver] = {}
        # Wire cross-graph edges after ownership is established.
        #
        # Federation passes:
        #   - _wire_cross_graph_edges is gated on multi-repo (it's a no-op
        #     for single-repo since there are no foreign repos to wire to).
        #   - _instantiate_cross_repo_satisfies runs unconditionally because
        #     a single-repo build can still produce SATISFIES broken-refs
        #     whose target is unknown to any associate (single-repo author
        #     wrote Satisfies: against a foreign namespace they haven't
        #     declared as an associate). Phase 4's missing-associate
        #     diagnostic needs to fire in that case.
        #   - _detect_satisfies_cycles also runs unconditionally; cycles can
        #     in principle exist inside a single repo via in-repo Satisfies
        #     chains, though Phase-2 validation usually prevents that.
        if len([e for e in repos if e.graph is not None]) > 1:
            self._wire_cross_graph_edges()
        # Implements: REQ-p00014-H
        self._instantiate_cross_repo_satisfies()
        # Implements: REQ-d00252
        self._wire_integrates_edges()
        # Implements: REQ-p00014-J
        self._detect_satisfies_cycles()
        self._annotate_presumed_foreign_refs()
        # Implements: REQ-d00201-B
        self._federated_log = FederatedMutationLog()
        self._federated_log._bind_repos(self._repos)
        # Implements: REQ-d00222-C
        self._merge_terms()
        # Implements: REQ-d00239-A
        self._scan_terms()

    # ─────────────────────────────────────────────────────────────────────────
    # Terms Federation
    # ─────────────────────────────────────────────────────────────────────────

    # Implements: REQ-d00222-C
    def _merge_terms(self) -> None:
        """Merge per-repo _terms into a single federated TermDictionary.

        Each TermEntry is (re-)stamped with this federation's view of the
        owning repo's name. An associate's TraceGraph reaches us already
        carrying a ``repo_name`` from its inner ``FederatedGraph.from_single``
        build (stamped from ``[project].name``); the host calls that same
        repo something else in ``[associates]`` (e.g. the dict key
        ``hht_diary``), and only the host-side name resolves via
        ``iter_repos()`` for ``/api/file-content``. We overwrite
        unconditionally so the term card's ``repo_name`` always matches
        ``RepoEntry.name``.
        """
        from elspais.graph.terms import TermDictionary

        merged = TermDictionary()
        self._term_duplicates: list[tuple] = []
        for entry in self._repos.values():
            if entry.graph is not None:
                for term_entry in entry.graph._terms.iter_all():
                    term_entry.repo_name = entry.name
                dupes = merged.merge(entry.graph._terms)
                self._term_duplicates.extend(dupes)
        self._terms = merged

    # Implements: REQ-d00239-A, REQ-d00239-B
    def _scan_terms(self) -> None:
        """Run term scanner across all repos using the merged dictionary.

        Uses per-repo config for markup_styles and exclude_files so that
        cross-repo term references resolve correctly.  Always canonicalizes
        term forms in spec node text and marks affected files dirty so that
        ``render_save`` produces canonical output.

        ``TermRef.namespace`` carries the REQ-id prefix (e.g. ``DIARY``)
        of the repo each reference was found in, NOT the host-side
        ``RepoEntry.name``. The two are distinct identifiers (see
        ``__init__`` invariant check); the API surfaces this value to the
        viewer as the term's namespace label, so the REQ-prefix is what
        callers expect.
        """
        from elspais.graph.term_scanner import scan_graph

        self._unmatched_emphasis: list[dict] = []
        for entry in self._repos.values():
            if entry.graph is None:
                continue
            config = entry.config or {}
            terms_cfg = config.get("terms", {})
            req_namespace = config.get("project", {}).get("namespace", "") or entry.name
            unmatched = scan_graph(
                self._terms,
                entry.graph,
                namespace=req_namespace,
                markup_styles=terms_cfg.get("markup_styles"),
                exclude_files=terms_cfg.get("exclude_files"),
                canonicalize=True,
            )
            if unmatched:
                self._unmatched_emphasis.extend(unmatched)

    # ─────────────────────────────────────────────────────────────────────────
    # Comment Routing (Implements: REQ-d00230-B)
    # ─────────────────────────────────────────────────────────────────────────

    def iter_comments(self, anchor: str) -> Iterator[CommentThread]:
        """Yield comment threads for an anchor, routed to owning repo."""
        from elspais.graph.comment_store import parse_anchor

        node_id = parse_anchor(anchor)[0]
        repo_name = self._ownership.get(node_id)
        if repo_name:
            entry = self._repos.get(repo_name)
            if entry and entry.graph:
                yield from entry.graph.iter_comments(anchor)

    def comment_count(self, anchor: str) -> int:
        """Count comment threads for an anchor."""
        from elspais.graph.comment_store import parse_anchor

        node_id = parse_anchor(anchor)[0]
        repo_name = self._ownership.get(node_id)
        if repo_name:
            entry = self._repos.get(repo_name)
            if entry and entry.graph:
                return entry.graph.comment_count(anchor)
        return 0

    def has_comments(self, anchor: str) -> bool:
        """Check if any comment threads exist for an anchor."""
        return self.comment_count(anchor) > 0

    def iter_orphaned_comments(self) -> Iterator[CommentThread]:
        """Yield orphaned comments aggregated across all repos."""
        for entry in self._repos.values():
            if entry.graph:
                yield from entry.graph.iter_orphaned_comments()

    def add_comment_thread(self, node_id: str, thread: CommentThread, source_file: str) -> None:
        """Add a comment thread to the correct repo's in-memory index."""
        repo_name = self._ownership.get(node_id)
        if repo_name:
            entry = self._repos.get(repo_name)
            if entry and entry.graph:
                entry.graph.add_comment_thread(thread, source_file)

    def find_comment_thread(self, comment_id: str) -> tuple[str, CommentThread] | None:
        """Find a thread by comment ID across all repos."""
        for entry in self._repos.values():
            if entry.graph:
                result = entry.graph.find_comment_thread(comment_id)
                if result:
                    return result
        return None

    def remove_comment_thread(self, comment_id: str) -> str | None:
        """Remove a thread by comment ID from the correct repo's index."""
        for entry in self._repos.values():
            if entry.graph:
                anchor = entry.graph.remove_comment_thread(comment_id)
                if anchor:
                    return anchor
        return None

    def iter_comments_for_card(self, node_id: str) -> Iterator[tuple[str, list[CommentThread]]]:
        """Yield (anchor, threads) for all anchors belonging to a node."""
        repo_name = self._ownership.get(node_id)
        if repo_name:
            entry = self._repos.get(repo_name)
            if entry and entry.graph:
                yield from entry.graph.iter_comments_for_card(node_id)

    def load_comments(self) -> None:
        """Load comment indexes for all repos and run promotion.

        Called at viewer startup and on graph refresh.
        """
        from elspais.graph.comment_store import (
            load_comment_index,
            promote_orphaned_comments,
        )

        for entry in self._repos.values():
            if entry.graph:
                idx = load_comment_index(entry.repo_root)
                promote_orphaned_comments(idx, entry.graph, entry.repo_root)
                entry.graph._comment_index = idx

    def comment_source_file(self, anchor: str) -> str | None:
        """Return the JSONL source file path for an anchor."""
        from elspais.graph.comment_store import parse_anchor

        node_id = parse_anchor(anchor)[0]
        repo_name = self._ownership.get(node_id)
        if repo_name:
            entry = self._repos.get(repo_name)
            if entry and entry.graph:
                return entry.graph.comment_source_file(anchor)
        return None

    # ─────────────────────────────────────────────────────────────────────────
    # Term Access Properties
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def terms(self) -> TermDictionary:
        """Read-only access to the merged term dictionary."""
        return self._terms

    @property
    def term_duplicates(self) -> list[tuple]:
        """Read-only access to cross-repo term duplicates."""
        return self._term_duplicates

    @property
    def unmatched_emphasis(self) -> list[dict]:
        """Read-only access to emphasis tokens not matching any defined term."""
        return getattr(self, "_unmatched_emphasis", [])

    # ─────────────────────────────────────────────────────────────────────────
    # Root Repo Convenience Properties
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def root_repo_name(self) -> str:
        """Return the host (root) repo's name as used in RepoEntry/index."""
        return self._root_repo

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
    def empty(cls, *, name: str) -> FederatedGraph:
        """Create an empty FederatedGraph with no repos.

        Used as an error-fallback when graph construction fails. The caller
        must pass an explicit ``name`` sentinel (e.g. ``"<unconfigured>"``)
        so the degraded state is visible at the call site rather than hidden
        behind a default.
        """
        from elspais.graph.builder import TraceGraph

        entry = RepoEntry(
            name=name,
            graph=TraceGraph(),
            config=None,
            repo_root=Path("."),
        )
        return cls([entry], root_repo=name)

    # Implements: REQ-d00200-B
    @classmethod
    def from_single(
        cls,
        graph: TraceGraph,
        config: dict[str, Any],
        repo_root: Path,
    ) -> FederatedGraph:
        """Create a federation-of-one from a single TraceGraph.

        Args:
            graph: The single TraceGraph to wrap.
            config: Config for this repo. Must have ``[project].name`` set
                — ``load_config()`` enforces this at the boundary, so any
                ``KeyError`` here indicates a caller bug, not a missing-
                config user error.
            repo_root: Filesystem path to the repo root.

        Returns:
            A FederatedGraph wrapping a single repo.
        """
        host_name = config["project"]["name"]
        entry = RepoEntry(
            name=host_name,
            graph=graph,
            config=config,
            repo_root=repo_root,
        )
        return cls([entry], root_repo=host_name)

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

    # Implements: REQ-d00230-D
    def repo_root_for(self, node_id: str) -> Path | None:
        """Return the repo root Path for a node, or None if not found.

        Used for write routing (e.g., determining where to write comment JSONL).
        """
        repo_name = self._ownership.get(node_id)
        if repo_name is None:
            return None
        return self._repos[repo_name].repo_root

    # Implements: REQ-d00200-G
    def config_for(self, node_id: str) -> dict[str, Any] | None:
        """Return the config dict for the repo owning node_id.

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

    def duplicate_req_ids(self) -> dict[str, list[str]]:
        """Aggregate cross-file duplicate REQ IDs across all repos.

        # Strategy: aggregate
        """
        result: dict[str, list[str]] = {}
        for _name, graph in self._live_graphs():
            for canonical, sources in graph.duplicate_req_ids().items():
                result.setdefault(canonical, []).extend(sources)
        return result

    def has_duplicate_req_ids(self) -> bool:
        """Check if any repo has cross-file duplicate REQ IDs.

        # Strategy: aggregate
        """
        return any(graph.has_duplicate_req_ids() for _name, graph in self._live_graphs())

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

    def add_changelog_entry(self, node_id: str, changelog_entry: dict[str, str]) -> MutationEntry:
        """Add a changelog entry to a requirement.

        # Strategy: by_id
        """
        repo_name = self._ownership[node_id]
        result = self._graph_for(node_id).add_changelog_entry(node_id, changelog_entry)
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
        tg = self._graph_for(req_id)
        result = tg.add_assertion(req_id, label, text)
        # New assertion gets ownership — derive ID from the same TraceGraph
        # convention so federated lookup and graph index agree.
        assertion_id = tg.make_assertion_id(req_id, label)
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
    # Journey Mutations
    # ─────────────────────────────────────────────────────────────────────────

    def update_journey_field(
        self,
        node_id: str,
        field_name: str,
        value: str,
    ) -> MutationEntry:
        """Update a structured field on a USER_JOURNEY node.

        # Strategy: by_id
        """
        repo_name = self._ownership[node_id]
        result = self._graph_for(node_id).update_journey_field(node_id, field_name, value)
        self._record_mutation(repo_name, result)
        return result

    def update_journey_section(
        self,
        node_id: str,
        section_name: str,
        new_name: str | None = None,
        new_content: str | None = None,
    ) -> MutationEntry:
        """Update a journey section by name.

        # Strategy: by_id
        """
        repo_name = self._ownership[node_id]
        result = self._graph_for(node_id).update_journey_section(
            node_id,
            section_name,
            new_name,
            new_content,
        )
        self._record_mutation(repo_name, result)
        return result

    def add_journey_section(
        self,
        node_id: str,
        name: str,
        content: str = "",
    ) -> MutationEntry:
        """Append a new section to a journey.

        # Strategy: by_id
        """
        repo_name = self._ownership[node_id]
        result = self._graph_for(node_id).add_journey_section(node_id, name, content)
        self._record_mutation(repo_name, result)
        return result

    def delete_journey_section(
        self,
        node_id: str,
        section_name: str,
    ) -> MutationEntry:
        """Remove a section from a journey by name.

        # Strategy: by_id
        """
        repo_name = self._ownership[node_id]
        result = self._graph_for(node_id).delete_journey_section(node_id, section_name)
        self._record_mutation(repo_name, result)
        return result

    def add_journey(
        self,
        journey_id: str,
        title: str,
        file_id: str,
        target_repo: str | None = None,
    ) -> MutationEntry:
        """Create a new USER_JOURNEY node.

        # Strategy: special — target_repo specifies destination
        """
        repo_name = target_repo or self._root_repo
        entry = self._repos.get(repo_name)
        if entry is None or entry.graph is None:
            raise KeyError(f"Repo '{repo_name}' not found or unavailable")
        result = entry.graph.add_journey(journey_id, title, file_id)
        self._ownership[journey_id] = repo_name
        self._record_mutation(repo_name, result)
        return result

    def delete_journey(self, node_id: str) -> MutationEntry:
        """Delete a USER_JOURNEY node. Removes from ownership.

        # Strategy: by_id
        """
        repo_name = self._ownership[node_id]
        result = self._graph_for(node_id).delete_journey(node_id)
        del self._ownership[node_id]
        self._record_mutation(repo_name, result)
        return result

    def reconstruct_journey_body(self, node_id: str) -> MutationEntry:
        """Reconstruct journey body from structured fields.

        # Strategy: by_id
        """
        repo_name = self._ownership[node_id]
        result = self._graph_for(node_id).reconstruct_journey_body(node_id)
        self._record_mutation(repo_name, result)
        return result

    def update_remainder(
        self,
        node_id: str,
        text: str | None = None,
        heading: str | None = None,
    ) -> MutationEntry:
        """Update text and/or heading of a REMAINDER node.

        # Strategy: by_id
        """
        repo_name = self._ownership[node_id]
        result = self._graph_for(node_id).update_remainder(node_id, text=text, heading=heading)
        self._record_mutation(repo_name, result)
        return result

    # ─────────────────────────────────────────────────────────────────────────
    # Special Mutations
    # ─────────────────────────────────────────────────────────────────────────

    def add_file_node(
        self,
        absolute_path: Path,
        file_type: FileType,
        target_repo: str | None = None,
        git_branch: str | None = None,
        git_commit: str | None = None,
    ) -> MutationEntry:
        """Add a new FILE node to a specific sub-graph.

        # Strategy: special — target_repo specifies destination

        Delegates to the sub-graph's ``add_file_node``, which in turn uses
        ``factory.create_file_node`` so the produced node is identical to
        what a rebuild would yield. Updates ownership so subsequent by_id
        lookups route to the correct sub-graph.
        """
        repo_name = target_repo or self._root_repo
        entry = self._repos.get(repo_name)
        if entry is None or entry.graph is None:
            raise KeyError(f"Repo '{repo_name}' not found or unavailable")
        result = entry.graph.add_file_node(
            absolute_path,
            entry.repo_root,
            file_type,
            repo=None if repo_name == self._root_repo else repo_name,
            git_branch=git_branch,
            git_commit=git_commit,
        )
        self._ownership[result.target_id] = repo_name
        self._record_mutation(repo_name, result)
        return result

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

    # Edge kinds that establish content-level parent relationships
    _CONTENT_EDGE_KINDS = frozenset(
        {
            EdgeKind.IMPLEMENTS,
            EdgeKind.REFINES,
            EdgeKind.VERIFIES,
            EdgeKind.VALIDATES,
            EdgeKind.YIELDS,
        }
    )

    def _wire_cross_graph_edges(self) -> None:
        """Wire cross-graph edges by resolving broken references across repos.

        For each sub-graph's broken references, check if the target_id exists
        in another sub-graph. If found, create the edge using target_graph
        parameter and remove the broken reference. After wiring, demote any
        source nodes from _roots that now have content-level parent edges.
        """
        # Track source node IDs that got wired via content edges, keyed by repo
        wired_sources: dict[str, set[str]] = {}

        for source_entry in self._repos.values():
            if source_entry.graph is None:
                continue
            resolved: list[int] = []  # indices to remove
            for i, br in enumerate(source_entry.graph._broken_references):
                # SATISFIES is handled by _instantiate_cross_repo_satisfies,
                # which clones the template subtree instead of wiring a
                # direct cross-graph edge.  Skip it here so the broken-ref
                # survives for the Phase-A pass to consume.
                # Implements: REQ-p00014-H
                if br.edge_kind == EdgeKind.SATISFIES.value:
                    continue
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
                        if EdgeKind(br.edge_kind) in self._CONTENT_EDGE_KINDS:
                            wired_sources.setdefault(source_entry.name, set()).add(br.source_id)
            # Remove resolved broken references (reverse to preserve indices)
            for idx in reversed(resolved):
                source_entry.graph._broken_references.pop(idx)

        # Demote wired source nodes from _roots — they now have parent edges
        for repo_name, source_ids in wired_sources.items():
            graph = self._repos[repo_name].graph
            if graph is not None:
                graph._roots = [r for r in graph._roots if r.id not in source_ids]

    def _resolver_for(self, entry: RepoEntry) -> IdResolver | None:
        """Return the cached ``IdResolver`` for ``entry``'s repo.

        Builds and memoises the resolver on first access. Returns
        ``None`` when the repo has no config (error-state repos can't
        be probed). Used by every federation pass that needs ID-format
        tolerance: ``_claim_for``, ``_instantiate_cross_repo_satisfies``,
        and ``_annotate_presumed_foreign_refs``.
        """
        if entry.config is None:
            return None
        cached = self._resolver_cache.get(entry.name)
        if cached is None:
            from elspais.utilities.patterns import build_resolver

            cached = build_resolver(entry.config)
            self._resolver_cache[entry.name] = cached
        return cached

    # Implements: REQ-p00014-H
    def _claim_for(self, target_id: str) -> tuple[str, str] | None:
        """Ask each associated repo's resolver whether it claims ``target_id``.

        Returns ``(repo_name, canonical_id_in_that_repo)`` or ``None``.

        Probes in declaration order; first claimant wins.  Cold-path
        fallback for when exact-match ``_ownership`` lookup misses
        (e.g.  ID written in a non-canonical form like uppercase or
        different padding).
        """
        for entry in self._repos.values():
            if entry.graph is None:
                continue
            resolver = self._resolver_for(entry)
            if resolver is None:
                continue
            if not resolver.is_local_id(target_id):
                continue
            parsed = resolver.parse(target_id)
            if parsed is None:
                continue
            canonical = resolver.render_canonical(parsed)
            if canonical in entry.graph._index:
                return entry.name, canonical
        return None

    # Implements: REQ-p00014-H
    def _instantiate_cross_repo_satisfies(self) -> None:
        """Phase A: clone cross-repo Satisfies templates into declaring repos.

        For each per-repo broken-ref with ``edge_kind == SATISFIES`` whose
        target lives in another federated repo, clone the template REQ
        plus its directly-attached assertions into the declaring repo's
        ``_nodes`` / ``_index`` with composite IDs (``declaring::original``),
        wire intra-graph SATISFIES + STRUCTURES + DEFINES edges, and wire
        cross-graph INSTANCE edges back to the template originals.

        Single-REQ scope (CUR-1353 Phase 2): only the template root REQ
        and its STRUCTURES-children-that-are-assertions are cloned.
        Templates may not have descendant REQs (rule 8).
        """
        from elspais.graph.GraphNode import GraphNode
        from elspais.graph.relations import Stereotype
        from elspais.utilities.patterns import INSTANCE_SEPARATOR

        for source_entry in self._repos.values():
            if source_entry.graph is None:
                continue
            resolver = self._resolver_for(source_entry)
            resolved_indices: list[int] = []

            for i, br in enumerate(source_entry.graph._broken_references):
                if br.edge_kind != EdgeKind.SATISFIES.value:
                    continue

                # Resolve the target's owning repo.  Try exact-match
                # ownership lookup first, then fall back to per-repo
                # IdResolver probing for ID-format tolerance.
                target_repo_name = self._ownership.get(br.target_id)
                target_id_canonical = br.target_id
                if target_repo_name is None:
                    claim = self._claim_for(br.target_id)
                    if claim is not None:
                        target_repo_name, target_id_canonical = claim
                if target_repo_name is None:
                    # Missing-associate: no associated repo claims this
                    # target ID. Emit a typed diagnostic naming the
                    # currently-available associates so the author knows
                    # what IS declared (and what's missing).
                    # Implements: REQ-p00014-J
                    available = sorted(
                        name for name in self._repos.keys() if name != source_entry.name
                    )
                    available_str = (
                        f"Available associates: {', '.join(available)}. "
                        if available
                        else "No associates declared. "
                    )
                    new_br = BrokenReference(
                        source_id=br.source_id,
                        target_id=br.target_id,
                        edge_kind=br.edge_kind,
                        presumed_foreign=True,
                        diagnostic=(
                            f"{br.source_id} satisfies {br.target_id}; "
                            f"no associated repo claims this ID. "
                            f"{available_str}"
                            f"If {br.target_id} lives in a repo not yet declared, "
                            f"add `[associates.<repo>]` to .elspais.toml."
                        ),
                    )
                    source_entry.graph._broken_references[i] = new_br
                    continue
                if target_repo_name == source_entry.name:
                    # In-repo (already handled by the per-repo builder).
                    continue

                target_entry = self._repos[target_repo_name]
                if target_entry.graph is None:
                    continue
                template_node = target_entry.graph._index.get(target_id_canonical)
                if template_node is None:
                    continue
                if template_node.get_field("stereotype") != Stereotype.TEMPLATE:
                    # Target exists but isn't marked **Template**.  Leave
                    # the broken-ref in place; downstream validation will
                    # attach a rule-1 diagnostic.
                    continue

                declaring_node = source_entry.graph._index.get(br.source_id)
                if declaring_node is None:
                    continue

                # CUR-1353 Phase 2: single-REQ scope.  A template is the
                # one REQ root plus its directly-attached assertions
                # (STRUCTURES children).  Do not walk further.
                template_nodes: list[GraphNode] = [template_node]
                for child in template_node.iter_children(edge_kinds={EdgeKind.STRUCTURES}):
                    if child.kind == NodeKind.ASSERTION:
                        template_nodes.append(child)

                clone_map: dict[str, GraphNode] = {}
                for orig in template_nodes:
                    clone_id = (
                        resolver.build_instance_id(br.source_id, orig.id)
                        if resolver is not None
                        else f"{br.source_id}{INSTANCE_SEPARATOR}{orig.id}"
                    )
                    clone = GraphNode(
                        id=clone_id,
                        kind=orig.kind,
                        label=orig.get_label(),
                    )
                    for key, value in orig.get_all_content().items():
                        if key != "stereotype":
                            clone.set_field(key, value)
                    clone.set_field("stereotype", Stereotype.INSTANCE)
                    # Implements: REQ-p00014-K
                    # Record the template's owning repo so viewers can show
                    # "Template defined in <repo>" provenance without needing
                    # to walk the cross-graph INSTANCE edge.
                    clone.set_field("template_repo", target_repo_name)
                    # Source files live in foreign repo; do NOT copy parse_line.
                    clone.set_field("parse_line", None)
                    clone.set_field("parse_end_line", None)

                    source_entry.graph._index[clone_id] = clone
                    self._ownership[clone_id] = source_entry.name
                    clone_map[orig.id] = clone

                    # Cross-graph INSTANCE edge: clone -> template original.
                    # Use .link() directly so the edge crosses repo
                    # boundaries (TraceGraph.add_edge with target_graph
                    # would place the edge on target.link(source), which
                    # would invert the direction we want here).
                    clone.link(orig, EdgeKind.INSTANCE)

                # Intra-graph STRUCTURES edges: cloned REQ -> cloned assertions.
                #
                # Note: unlike the in-repo path in builder.py
                # (`_instantiate_satisfies_templates`), we DO NOT generically copy
                # `orig.iter_outgoing_edges()` here. Under the Phase-2 single-REQ
                # scope, the only outgoing edges from a template REQ are
                # STRUCTURES edges to its directly-attached assertions, and the
                # cloned assertions themselves have no outgoing edges between
                # cloned nodes. The parent-loop below is therefore sufficient.
                # If a future phase widens the template scope (e.g. allow
                # cloned cross-REQ refinements or assertion-to-assertion edges),
                # this omission must be revisited to avoid losing those edges --
                # or, conversely, re-introducing the generic outgoing-edge pass
                # without removing this loop would double-link STRUCTURES.
                for orig in template_nodes:
                    if orig.kind != NodeKind.ASSERTION:
                        continue
                    clone_assertion = clone_map[orig.id]
                    for parent in orig.iter_parents():
                        parent_clone = clone_map.get(parent.id)
                        if parent_clone is not None:
                            parent_clone.link(clone_assertion, EdgeKind.STRUCTURES)

                # Intra-graph SATISFIES edge: declaring REQ -> cloned root.
                cloned_root = clone_map.get(template_node.id)
                if cloned_root is not None:
                    declaring_node.link(cloned_root, EdgeKind.SATISFIES)

                # Intra-graph DEFINES edges: declaring FILE -> every clone.
                declaring_file = declaring_node.file_node()
                if declaring_file is not None:
                    for clone in clone_map.values():
                        declaring_file.link(clone, EdgeKind.DEFINES)

                resolved_indices.append(i)

            for idx in reversed(resolved_indices):
                source_entry.graph._broken_references.pop(idx)

    # Implements: REQ-d00252
    def _wire_integrates_edges(self) -> None:
        """Wire top-down ``Integrates:`` refs into reverse INTEGRATES edges.

        For each REQUIREMENT carrying ``integrates_refs``, resolve the target
        to its owning associate and wire a cross-graph INTEGRATES edge so the
        declaring (consumer) requirement becomes the PARENT and the library
        node the CHILD — the consumer thus counts as implemented while the
        library's own source files stay untouched (REQ-d00252-D).

        External-only enforcement: if the target resolves to the SAME repo as
        the declaring requirement, record a broken reference instead
        (REQ-d00252-C). If the target can't be resolved, record a hard broken
        reference when a configured associate claims the target's ID format but
        lacks the ID, or a soft ``presumed_foreign`` broken reference when no
        associate claims the format (REQ-d00252-E).

        Runs unconditionally (even single-repo), so an unresolved Integrates in
        a one-repo build still surfaces a presumed-foreign broken reference.
        """
        from elspais.graph.GraphNode import NodeKind

        for source_entry in self._repos.values():
            if source_entry.graph is None:
                continue
            for req in list(source_entry.graph.iter_by_kind(NodeKind.REQUIREMENT)):
                for raw in req.get_field("integrates_refs") or []:
                    # v1 is whole-REQ: strip any library-side assertion suffix
                    # (e.g. ``LIB-d00007-A`` -> ``LIB-d00007``) for resolution.
                    parts = raw.split("-")
                    target_id = "-".join(parts[:3]) if len(parts) > 3 else raw
                    self._wire_one_integrates(source_entry, req.id, target_id)

    # Implements: REQ-d00252
    def _wire_one_integrates(
        self,
        source_entry: RepoEntry,
        source_id: str,
        target_id: str,
    ) -> None:
        """Resolve and wire one ``Integrates:`` target (helper for above)."""
        owner = self._ownership.get(target_id)
        canonical = target_id
        if owner is None:
            claim = self._claim_for(target_id)
            if claim is not None:
                owner, canonical = claim

        # Resolved to a foreign associate: wire the reverse INTEGRATES edge.
        # consumer (source_id) = PARENT, library node (canonical) = CHILD.
        if owner is not None and owner != source_entry.name:
            target_entry = self._repos[owner]
            if target_entry.graph is not None and canonical in target_entry.graph._index:
                target_entry.graph.add_edge(
                    canonical,  # source_id (child, local to library graph)
                    source_id,  # target_id (parent, resolved in consumer graph)
                    EdgeKind.INTEGRATES,
                    target_graph=source_entry.graph,
                )
                return

        # Same-repo target: external-only violation (REQ-d00252-C).
        if owner == source_entry.name:
            source_entry.graph._broken_references.append(
                BrokenReference(
                    source_id=source_id,
                    target_id=target_id,
                    edge_kind=EdgeKind.INTEGRATES.value,
                    diagnostic=(
                        f"{source_id} integrates {target_id}, but {target_id} is in the "
                        f"same repository; Integrates must target an external associate."
                    ),
                )
            )
            return

        # Unresolved: hard if a configured associate claims the ID format but
        # lacks the ID, soft presumed-foreign otherwise (REQ-d00252-E).
        claimed = False
        for entry in self._repos.values():
            if entry.graph is None or entry.name == source_entry.name:
                continue
            resolver = self._resolver_for(entry)
            if resolver is not None and resolver.is_local_id(target_id):
                claimed = True
                break
        source_entry.graph._broken_references.append(
            BrokenReference(
                source_id=source_id,
                target_id=target_id,
                edge_kind=EdgeKind.INTEGRATES.value,
                presumed_foreign=not claimed,
                diagnostic=(
                    f"{source_id} integrates {target_id}: a configured associate "
                    f"claims this ID format but is missing the ID."
                    if claimed
                    else f"{source_id} integrates {target_id}: no configured associate "
                    f"claims this ID."
                ),
            )
        )

    # Implements: REQ-p00014-J
    def _detect_satisfies_cycles(self) -> None:
        """Detect Satisfies cycles via DFS over SATISFIES + INSTANCE edges.

        A cycle exists when walking SATISFIES (declaring -> clone) then
        INSTANCE (clone -> template) then any outbound SATISFIES from
        that template eventually returns to a node already on the path.

        Emits one typed ``BrokenReference`` per build (with ``cycle`` in
        its diagnostic) on the owning repo of the first node in the
        detected cycle, then returns. Reporting one cycle per build keeps
        the output legible; once the author breaks the first cycle,
        subsequent builds reveal any remaining ones.

        Implementation notes:
        - Three-colour DFS (WHITE/GRAY/BLACK) prevents infinite recursion
          and revisits.
        - INSTANCE edges are only traversed from INSTANCE-stereotype
          nodes (the cloned roots/assertions), preserving the
          "satisfies-then-resolves" semantics.
        - Iterates ``_index`` from each live repo so cycles spanning
          multiple repos are reachable regardless of where DFS starts.
        """
        from elspais.graph.relations import Stereotype

        WHITE, GRAY, BLACK = 0, 1, 2
        colour: dict[str, int] = {}
        on_path: list[str] = []

        def dfs(node: GraphNode) -> list[str] | None:
            existing = colour.get(node.id, WHITE)
            if existing == GRAY:
                idx = on_path.index(node.id)
                return on_path[idx:] + [node.id]
            if existing == BLACK:
                return None
            colour[node.id] = GRAY
            on_path.append(node.id)
            stereotype = node.get_field("stereotype")
            is_instance = stereotype is not None and stereotype == Stereotype.INSTANCE
            for edge in node.iter_outgoing_edges():
                if edge.kind == EdgeKind.SATISFIES:
                    cycle = dfs(edge.target)
                    if cycle:
                        return cycle
                elif edge.kind == EdgeKind.INSTANCE and is_instance:
                    cycle = dfs(edge.target)
                    if cycle:
                        return cycle
            on_path.pop()
            colour[node.id] = BLACK
            return None

        for entry in self._repos.values():
            if entry.graph is None:
                continue
            for node_id, node in list(entry.graph._index.items()):
                if node.kind != NodeKind.REQUIREMENT:
                    continue
                if colour.get(node_id, WHITE) != WHITE:
                    continue
                cycle = dfs(node)
                if cycle:
                    # Emit a typed broken-ref on the originating repo.
                    entry.graph._broken_references.append(
                        BrokenReference(
                            source_id=cycle[0],
                            target_id=cycle[-1],
                            edge_kind=EdgeKind.SATISFIES.value,
                            diagnostic=(f"Satisfies cycle detected: {' -> '.join(cycle)}"),
                        )
                    )
                    return  # one cycle per build to keep output sane

    def _annotate_presumed_foreign_refs(self) -> None:
        """Mark remaining broken references whose target doesn't match the source repo's ID pattern.

        Called after _wire_cross_graph_edges(). Any broken ref whose target_id
        cannot be parsed by the source repo's IdResolver is presumed to belong
        to a foreign repo (different namespace/format) and is replaced with a
        BrokenReference with presumed_foreign=True.

        Skipped for repos with no config (annotation requires pattern knowledge).

        Refs that already carry a ``diagnostic`` are left untouched: an earlier
        federation pass (e.g. cross-repo Satisfies, or Integrates resolution in
        ``_wire_integrates_edges``) made a deliberate hard/soft determination
        that this generic pattern check must not silently override.
        """
        for source_entry in self._repos.values():
            if source_entry.graph is None:
                continue
            resolver = self._resolver_for(source_entry)
            if resolver is None:
                continue
            refs = source_entry.graph._broken_references
            for i, br in enumerate(refs):
                if br.diagnostic:
                    continue
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
