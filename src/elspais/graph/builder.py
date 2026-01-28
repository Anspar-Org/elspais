"""Graph Builder - Constructs TraceGraph from parsed content.

This module provides the builder pattern for constructing a complete
traceability graph from parsed content.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from elspais.graph.GraphNode import GraphNode, NodeKind, SourceLocation
from elspais.graph.relations import Edge, EdgeKind
from elspais.graph.parsers import ParsedContent
from elspais.graph.mutations import BrokenReference, MutationEntry, MutationLog


@dataclass
class TraceGraph:
    """Container for the complete traceability graph.

    Provides indexed access to all nodes and methods for graph-wide
    operations. Uses iterator-only API for traversal.

    Attributes:
        repo_root: Path to the repository root.
    """

    repo_root: Path = field(default_factory=Path.cwd)

    # Internal storage (prefixed) - excluded from constructor
    _roots: list[GraphNode] = field(default_factory=list, init=False)
    _index: dict[str, GraphNode] = field(default_factory=dict, init=False, repr=False)

    # Detection: orphans and broken references (populated at build time)
    _orphaned_ids: set[str] = field(default_factory=set, init=False)
    _broken_references: list[BrokenReference] = field(default_factory=list, init=False)

    # Mutation infrastructure
    _mutation_log: MutationLog = field(default_factory=MutationLog, init=False)
    _deleted_nodes: list[GraphNode] = field(default_factory=list, init=False)

    def iter_roots(self) -> Iterator[GraphNode]:
        """Iterate root nodes."""
        yield from self._roots

    def root_count(self) -> int:
        """Return number of root nodes."""
        return len(self._roots)

    def has_root(self, node_id: str) -> bool:
        """Check if a node ID is a root."""
        return any(r.id == node_id for r in self._roots)

    def find_by_id(self, node_id: str) -> GraphNode | None:
        """Find node by ID.

        Args:
            node_id: The node ID to find.

        Returns:
            The matching GraphNode, or None if not found.
        """
        return self._index.get(node_id)

    def all_nodes(self, order: str = "pre") -> Iterator[GraphNode]:
        """Iterate all nodes in graph.

        Args:
            order: Traversal order ("pre", "post", "level").

        Yields:
            All GraphNode instances in the graph.
        """
        for root in self._roots:
            yield from root.walk(order)

    def nodes_by_kind(self, kind: NodeKind) -> Iterator[GraphNode]:
        """Get all nodes of a specific kind.

        Args:
            kind: The NodeKind to filter by.

        Yields:
            GraphNode instances of the specified kind.
        """
        for node in self._index.values():
            if node.kind == kind:
                yield node

    def node_count(self) -> int:
        """Return total number of nodes in the graph."""
        return len(self._index)

    # ─────────────────────────────────────────────────────────────────────────
    # Detection API: Orphans and Broken References
    # ─────────────────────────────────────────────────────────────────────────

    def orphaned_nodes(self) -> Iterator[GraphNode]:
        """Iterate over orphaned nodes (nodes without parents).

        Orphans are nodes that were never linked to a parent during
        graph construction. This excludes root nodes which are intentionally
        parentless.

        Yields:
            GraphNode instances that are orphaned.
        """
        for node_id in self._orphaned_ids:
            node = self._index.get(node_id)
            if node:
                yield node

    def has_orphans(self) -> bool:
        """Check if the graph has orphaned nodes."""
        return len(self._orphaned_ids) > 0

    def orphan_count(self) -> int:
        """Return the number of orphaned nodes."""
        return len(self._orphaned_ids)

    def broken_references(self) -> list[BrokenReference]:
        """Get all broken references detected during build.

        Broken references occur when a node references a target ID
        that doesn't exist in the graph.

        Returns:
            List of BrokenReference instances.
        """
        return list(self._broken_references)

    def has_broken_references(self) -> bool:
        """Check if the graph has broken references."""
        return len(self._broken_references) > 0

    # ─────────────────────────────────────────────────────────────────────────
    # Mutation Infrastructure
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def mutation_log(self) -> MutationLog:
        """Access the mutation log for this graph."""
        return self._mutation_log

    def deleted_nodes(self) -> list[GraphNode]:
        """Get all nodes that have been deleted from this graph.

        Deleted nodes are preserved for delta reporting and undo operations.

        Returns:
            List of deleted GraphNode instances.
        """
        return list(self._deleted_nodes)

    def has_deletions(self) -> bool:
        """Check if any nodes have been deleted."""
        return len(self._deleted_nodes) > 0

    def undo_last(self) -> MutationEntry | None:
        """Undo the most recent mutation.

        Reverses the last mutation using its before_state and removes
        it from the mutation log.

        Returns:
            The undone MutationEntry, or None if log is empty.
        """
        entry = self._mutation_log.pop()
        if entry:
            self._apply_undo(entry)
        return entry

    def undo_to(self, mutation_id: str) -> list[MutationEntry]:
        """Undo all mutations back to (and including) a specific mutation.

        Args:
            mutation_id: The mutation ID to undo back to.

        Returns:
            List of undone MutationEntry instances in reverse order.

        Raises:
            ValueError: If the mutation_id is not found.
        """
        # Find all entries from the target to the end
        entries_to_undo = self._mutation_log.entries_since(mutation_id)
        undone: list[MutationEntry] = []

        # Undo in reverse order (most recent first)
        for _ in range(len(entries_to_undo)):
            entry = self._mutation_log.pop()
            if entry:
                self._apply_undo(entry)
                undone.append(entry)

        return undone

    def _apply_undo(self, entry: MutationEntry) -> None:
        """Apply an undo operation based on mutation type.

        Restores the graph state from entry.before_state.

        Args:
            entry: The mutation entry to reverse.
        """
        op = entry.operation

        if op == "rename_node":
            self._undo_rename_node(entry)
        elif op == "update_title":
            self._undo_update_title(entry)
        elif op == "change_status":
            self._undo_change_status(entry)
        elif op == "add_requirement":
            self._undo_add_requirement(entry)
        elif op == "delete_requirement":
            self._undo_delete_requirement(entry)
        elif op == "add_edge":
            self._undo_add_edge(entry)
        elif op == "delete_edge":
            self._undo_delete_edge(entry)
        elif op == "change_edge_kind":
            self._undo_change_edge_kind(entry)
        elif op == "add_assertion":
            self._undo_add_assertion(entry)
        elif op == "delete_assertion":
            self._undo_delete_assertion(entry)
        elif op == "update_assertion":
            self._undo_update_assertion(entry)
        elif op == "rename_assertion":
            self._undo_rename_assertion(entry)
        # Unknown operations are silently ignored (forward compatibility)

    def _undo_rename_node(self, entry: MutationEntry) -> None:
        """Undo a node rename operation."""
        old_id = entry.before_state.get("id")
        new_id = entry.after_state.get("id")
        if old_id and new_id and new_id in self._index:
            node = self._index.pop(new_id)
            node._id = old_id
            self._index[old_id] = node

    def _undo_update_title(self, entry: MutationEntry) -> None:
        """Undo a title update operation."""
        node_id = entry.target_id
        old_title = entry.before_state.get("title")
        if node_id in self._index and old_title is not None:
            self._index[node_id].label = old_title

    def _undo_change_status(self, entry: MutationEntry) -> None:
        """Undo a status change operation."""
        node_id = entry.target_id
        old_status = entry.before_state.get("status")
        if node_id in self._index and old_status is not None:
            self._index[node_id].set_field("status", old_status)

    def _undo_add_requirement(self, entry: MutationEntry) -> None:
        """Undo an add requirement operation (delete the added node)."""
        node_id = entry.target_id
        if node_id in self._index:
            node = self._index.pop(node_id)
            # Remove from roots if present
            self._roots = [r for r in self._roots if r.id != node_id]
            # Remove edges
            for parent in list(node.iter_parents()):
                parent.remove_child(node)

    def _undo_delete_requirement(self, entry: MutationEntry) -> None:
        """Undo a delete requirement operation (restore the node)."""
        # Find and restore from deleted_nodes
        node_id = entry.target_id
        for i, node in enumerate(self._deleted_nodes):
            if node.id == node_id:
                self._deleted_nodes.pop(i)
                self._index[node_id] = node
                # Restore as root if it was one
                if entry.before_state.get("was_root"):
                    self._roots.append(node)
                break

    def _undo_add_edge(self, entry: MutationEntry) -> None:
        """Undo an add edge operation."""
        source_id = entry.before_state.get("source_id")
        target_id = entry.before_state.get("target_id")
        if source_id and target_id:
            source = self._index.get(source_id)
            target = self._index.get(target_id)
            if source and target:
                target.remove_child(source)

    def _undo_delete_edge(self, entry: MutationEntry) -> None:
        """Undo a delete edge operation (restore the edge)."""
        source_id = entry.before_state.get("source_id")
        target_id = entry.before_state.get("target_id")
        edge_kind_str = entry.before_state.get("edge_kind")
        if source_id and target_id and edge_kind_str:
            source = self._index.get(source_id)
            target = self._index.get(target_id)
            if source and target:
                edge_kind = EdgeKind(edge_kind_str)
                target.link(source, edge_kind)

    def _undo_change_edge_kind(self, entry: MutationEntry) -> None:
        """Undo an edge kind change."""
        source_id = entry.before_state.get("source_id")
        target_id = entry.before_state.get("target_id")
        old_kind = entry.before_state.get("edge_kind")
        if source_id and target_id and old_kind:
            source = self._index.get(source_id)
            target = self._index.get(target_id)
            if source and target:
                # Find and update the edge
                for edge in source.iter_incoming_edges():
                    if edge.source.id == target_id:
                        edge._kind = EdgeKind(old_kind)
                        break

    def _undo_add_assertion(self, entry: MutationEntry) -> None:
        """Undo an add assertion operation."""
        assertion_id = entry.target_id
        if assertion_id in self._index:
            node = self._index.pop(assertion_id)
            for parent in list(node.iter_parents()):
                parent.remove_child(node)

    def _undo_delete_assertion(self, entry: MutationEntry) -> None:
        """Undo a delete assertion operation."""
        # Similar to undo_delete_requirement
        node_id = entry.target_id
        for i, node in enumerate(self._deleted_nodes):
            if node.id == node_id:
                self._deleted_nodes.pop(i)
                self._index[node_id] = node
                # Restore parent link
                parent_id = entry.before_state.get("parent_id")
                if parent_id and parent_id in self._index:
                    self._index[parent_id].add_child(node)
                break

    def _undo_update_assertion(self, entry: MutationEntry) -> None:
        """Undo an assertion text update."""
        node_id = entry.target_id
        old_text = entry.before_state.get("text")
        if node_id in self._index and old_text is not None:
            self._index[node_id].label = old_text

    def _undo_rename_assertion(self, entry: MutationEntry) -> None:
        """Undo an assertion rename."""
        old_id = entry.before_state.get("id")
        new_id = entry.after_state.get("id")
        if old_id and new_id and new_id in self._index:
            node = self._index.pop(new_id)
            node._id = old_id
            self._index[old_id] = node


class GraphBuilder:
    """Builder for constructing TraceGraph from parsed content.

    Usage:
        builder = GraphBuilder()
        for content in parsed_contents:
            builder.add_parsed_content(content)
        graph = builder.build()
    """

    def __init__(self, repo_root: Path | None = None) -> None:
        """Initialize the graph builder.

        Args:
            repo_root: Repository root path.
        """
        self.repo_root = repo_root or Path.cwd()
        self._nodes: dict[str, GraphNode] = {}
        self._pending_links: list[tuple[str, str, EdgeKind]] = []
        # Detection: track orphan candidates and broken references
        self._orphan_candidates: set[str] = set()
        self._broken_references: list[BrokenReference] = []

    def add_parsed_content(self, content: ParsedContent) -> None:
        """Add parsed content to the graph.

        Args:
            content: Parsed content from a parser.
        """
        if content.content_type == "requirement":
            self._add_requirement(content)
        elif content.content_type == "journey":
            self._add_journey(content)
        elif content.content_type == "code_ref":
            self._add_code_ref(content)
        elif content.content_type == "test_ref":
            self._add_test_ref(content)
        elif content.content_type == "test_result":
            self._add_test_result(content)
        elif content.content_type == "remainder":
            self._add_remainder(content)

    def _add_requirement(self, content: ParsedContent) -> None:
        """Add a requirement node and its assertions."""
        data = content.parsed_data
        req_id = data["id"]

        # Get source path from context if available
        source_ctx = getattr(content, "source_context", None)
        source_path = source_ctx.source_id if source_ctx else ""

        # Create requirement node
        source = SourceLocation(
            path=source_path,
            line=content.start_line,
            end_line=content.end_line,
        )

        node = GraphNode(
            id=req_id,
            kind=NodeKind.REQUIREMENT,
            label=data.get("title", ""),
            source=source,
        )
        node._content = {
            "level": data.get("level"),
            "status": data.get("status"),
            "hash": data.get("hash"),
        }
        self._nodes[req_id] = node
        self._orphan_candidates.add(req_id)  # Track as potential orphan

        # Create assertion nodes
        for assertion in data.get("assertions", []):
            assertion_id = f"{req_id}-{assertion['label']}"
            assertion_node = GraphNode(
                id=assertion_id,
                kind=NodeKind.ASSERTION,
                label=assertion["text"],
            )
            assertion_node._content = {"label": assertion["label"]}
            self._nodes[assertion_id] = assertion_node

            # Link assertion to parent requirement
            node.add_child(assertion_node)

        # Queue implements/refines links for later resolution
        for impl_ref in data.get("implements", []):
            self._pending_links.append((req_id, impl_ref, EdgeKind.IMPLEMENTS))

        for refine_ref in data.get("refines", []):
            self._pending_links.append((req_id, refine_ref, EdgeKind.REFINES))

    def _add_journey(self, content: ParsedContent) -> None:
        """Add a user journey node."""
        data = content.parsed_data
        journey_id = data["id"]

        node = GraphNode(
            id=journey_id,
            kind=NodeKind.USER_JOURNEY,
            label=data.get("title", ""),
        )
        node._content = {
            "actor": data.get("actor"),
            "goal": data.get("goal"),
        }
        self._nodes[journey_id] = node

    def _add_code_ref(self, content: ParsedContent) -> None:
        """Add code reference nodes."""
        data = content.parsed_data
        source_ctx = getattr(content, "source_context", None)
        source_id = source_ctx.source_id if source_ctx else "code"

        for impl_ref in data.get("implements", []):
            code_id = f"code:{source_id}:{content.start_line}"
            if code_id not in self._nodes:
                node = GraphNode(
                    id=code_id,
                    kind=NodeKind.CODE,
                    label=f"Code at {source_id}:{content.start_line}",
                )
                self._nodes[code_id] = node

            self._pending_links.append((code_id, impl_ref, EdgeKind.IMPLEMENTS))

    def _add_test_ref(self, content: ParsedContent) -> None:
        """Add test reference nodes."""
        data = content.parsed_data
        source_ctx = getattr(content, "source_context", None)
        source_id = source_ctx.source_id if source_ctx else "test"

        for val_ref in data.get("validates", []):
            test_id = f"test:{source_id}:{content.start_line}"
            if test_id not in self._nodes:
                node = GraphNode(
                    id=test_id,
                    kind=NodeKind.TEST,
                    label=f"Test at {source_id}:{content.start_line}",
                )
                self._nodes[test_id] = node

            self._pending_links.append((test_id, val_ref, EdgeKind.VALIDATES))

    def _add_test_result(self, content: ParsedContent) -> None:
        """Add a test result node."""
        data = content.parsed_data
        result_id = data["id"]
        source_ctx = getattr(content, "source_context", None)
        source_path = source_ctx.source_id if source_ctx else ""

        node = GraphNode(
            id=result_id,
            kind=NodeKind.TEST_RESULT,
            label=f"{data.get('status', 'unknown')}: {result_id}",
            source=SourceLocation(
                path=source_path,
                line=content.start_line,
                end_line=content.end_line,
            ),
        )
        node._content = {
            "status": data.get("status"),
            "test_id": data.get("test_id"),
            "duration": data.get("duration"),
        }
        self._nodes[result_id] = node

    def _add_remainder(self, content: ParsedContent) -> None:
        """Add a remainder/unclaimed content node."""
        data = content.parsed_data
        source_ctx = getattr(content, "source_context", None)
        source_path = source_ctx.source_id if source_ctx else ""

        # Use provided ID or generate from source location
        remainder_id = data.get("id") or f"rem:{source_path}:{content.start_line}"
        text = data.get("text", content.raw_text or "")

        node = GraphNode(
            id=remainder_id,
            kind=NodeKind.REMAINDER,
            label=text[:50] + "..." if len(text) > 50 else text,
            source=SourceLocation(
                path=source_path,
                line=content.start_line,
                end_line=content.end_line,
            ),
        )
        node._content = {"text": text}
        self._nodes[remainder_id] = node

    def build(self) -> TraceGraph:
        """Build the final TraceGraph.

        Resolves all pending links and identifies root nodes.
        Also detects orphaned nodes and broken references.

        Returns:
            Complete TraceGraph with detection data populated.
        """
        # Resolve pending links
        for source_id, target_id, edge_kind in self._pending_links:
            source = self._nodes.get(source_id)
            target = self._nodes.get(target_id)

            if source and target:
                # Node is being linked to a parent - no longer orphan candidate
                self._orphan_candidates.discard(source_id)

                # If target is an assertion, link from its parent requirement
                # with assertion_targets set, so the child appears under the
                # parent REQ (not the assertion node) with assertion badges
                if target.kind == NodeKind.ASSERTION:
                    # Find the parent requirement of this assertion
                    parent_reqs = [
                        p for p in target.iter_parents()
                        if p.kind == NodeKind.REQUIREMENT
                    ]
                    if parent_reqs:
                        parent_req = parent_reqs[0]
                        assertion_label = target.get_field("label", "")
                        parent_req.link(
                            source,
                            edge_kind,
                            assertion_targets=[assertion_label] if assertion_label else None,
                        )
                    else:
                        # Fallback: link directly if no parent found
                        target.link(source, edge_kind)
                else:
                    # Link target as parent of source (implements relationship)
                    target.link(source, edge_kind)
            elif source and not target:
                # Broken reference: target doesn't exist
                self._broken_references.append(
                    BrokenReference(
                        source_id=source_id,
                        target_id=target_id,
                        edge_kind=edge_kind.value,
                    )
                )

        # Identify roots (nodes with no parents)
        roots = [
            node for node in self._nodes.values()
            if not node._parents and node.kind == NodeKind.REQUIREMENT
        ]

        # Also include journeys as roots
        roots.extend(
            node for node in self._nodes.values()
            if node.kind == NodeKind.USER_JOURNEY
        )

        # Root nodes are not orphans - they're intentionally parentless
        root_ids = {r.id for r in roots}

        # Final orphan set: candidates that aren't roots
        orphaned_ids = self._orphan_candidates - root_ids

        graph = TraceGraph(repo_root=self.repo_root)
        graph._roots = roots
        graph._index = dict(self._nodes)
        graph._orphaned_ids = orphaned_ids
        graph._broken_references = list(self._broken_references)
        return graph
