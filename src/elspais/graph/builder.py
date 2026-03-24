# Implements: REQ-p00050-A, REQ-p00050-D, REQ-p00061-B, REQ-p00061-C
# Implements: REQ-o00050-A, REQ-o00050-B, REQ-o00050-C, REQ-o00050-D, REQ-o00050-E
# Implements: REQ-d00071-A, REQ-d00071-B, REQ-d00071-C, REQ-d00071-D
# Implements: REQ-d00216-A+B+C+D+E+F
"""Graph Builder - Constructs TraceGraph from parsed content.

This module provides the builder pattern for constructing a complete
traceability graph from parsed content.
"""

from __future__ import annotations

import itertools
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from elspais.graph.GraphNode import GraphNode, NodeKind
from elspais.graph.mutations import BrokenReference, MutationEntry, MutationLog
from elspais.graph.parsers import ParsedContent
from elspais.graph.parsers.requirement import RequirementParser
from elspais.graph.relations import EdgeKind, Stereotype
from elspais.utilities.patterns import INSTANCE_SEPARATOR
from elspais.utilities.test_identity import build_test_id


def _chain_self_and_ancestors(node: GraphNode) -> Iterator[GraphNode]:
    """Yield node itself, then all its ancestors."""
    return itertools.chain([node], node.ancestors())


# Implements: REQ-d00071-C
# Default satellite kinds: children of these types don't count as "meaningful"
# for determining root vs orphan status. Configurable via [graph].satellite_kinds.
_DEFAULT_SATELLITE_KINDS = frozenset({NodeKind.ASSERTION, NodeKind.RESULT})

# Traceability edges: all edge kinds except structural (CONTAINS, STRUCTURES)
_STRUCTURAL_EDGE_KINDS = frozenset({EdgeKind.CONTAINS, EdgeKind.STRUCTURES})
_TRACEABILITY_EDGE_KINDS = frozenset(k for k in EdgeKind if k not in _STRUCTURAL_EDGE_KINDS)


@dataclass
class TraceGraph:
    """Container for the complete traceability graph.

    Provides indexed access to all nodes and methods for graph-wide
    operations. Uses iterator-only API for traversal.

    Attributes:
        repo_root: Path to the repository root.
    """

    repo_root: Path = field(default_factory=Path.cwd)
    hash_mode: str = field(default="normalized-text")
    satellite_kinds: frozenset = field(default_factory=lambda: _DEFAULT_SATELLITE_KINDS)

    # Internal storage (prefixed) - excluded from constructor
    _roots: list[GraphNode] = field(default_factory=list, init=False)
    _index: dict[str, GraphNode] = field(default_factory=dict, init=False, repr=False)

    # Detection: orphans and broken references (populated at build time)
    _orphaned_ids: set[str] = field(default_factory=set, init=False)
    _broken_references: list[BrokenReference] = field(default_factory=list, init=False)

    # Mutation infrastructure
    _mutation_log: MutationLog = field(default_factory=MutationLog, init=False)
    _deleted_nodes: list[GraphNode] = field(default_factory=list, init=False)

    # Implements: REQ-d00130-A, REQ-d00130-B, REQ-d00130-C, REQ-d00130-D, REQ-d00130-F
    def iter_roots(self, kind: NodeKind | None = None) -> Iterator[GraphNode]:
        """Iterate root nodes, optionally filtered by NodeKind.

        Args:
            kind: If None, returns REQ + JOURNEY roots (current behavior,
                  excludes FILE nodes). If NodeKind.FILE, returns all FILE
                  nodes from _index. Otherwise, filters _roots by the
                  specified kind.

        Yields:
            GraphNode instances matching the filter criteria.
        """
        if kind is None:
            yield from self._roots
        elif kind == NodeKind.FILE:
            for node in self._index.values():
                if node.kind == NodeKind.FILE:
                    yield node
        else:
            for node in self._roots:
                if node.kind == kind:
                    yield node

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

    def all_nodes(self) -> Iterator[GraphNode]:
        """Iterate ALL nodes in graph, including orphans.

        Yields:
            All GraphNode instances in the graph.
        """
        yield from self._index.values()

    def all_connected_nodes(self, order: str = "pre") -> Iterator[GraphNode]:
        """Iterate nodes reachable from roots (excludes orphans).

        Args:
            order: Traversal order ("pre", "post", "level").

        Yields:
            GraphNode instances reachable from root nodes.
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

    # Implements: REQ-d00130-E
    def iter_by_kind(self, kind: NodeKind) -> Iterator[GraphNode]:
        """Iterate all nodes of a specific kind from the index.

        Equivalent to nodes_by_kind() but named consistently with the
        iterator-only API convention (iter_roots, iter_children, etc.).

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

    def clone(self) -> TraceGraph:
        """Create a deep copy of this graph.

        All nodes, edges, and relationships are cloned. The new graph
        is completely independent - mutations to one do not affect the other.

        Returns:
            A new TraceGraph with all data deep copied.
        """
        import copy

        return copy.deepcopy(self)

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
    # Reachability API
    # ─────────────────────────────────────────────────────────────────────────

    def is_reachable_to_requirement(self, node: GraphNode) -> bool:
        """Check if node is connected to any REQUIREMENT via traceability edges.

        Traverses ancestors excluding structural edges (CONTAINS, STRUCTURES).
        A node is "linked" if it can reach a REQUIREMENT through traceability
        edges like IMPLEMENTS, VERIFIES, YIELDS, etc.
        """
        for ancestor in node.ancestors(edge_kinds=_TRACEABILITY_EDGE_KINDS):
            if ancestor.kind == NodeKind.REQUIREMENT:
                return True
        return False

    def iter_unlinked(self, kind: NodeKind) -> Iterator[GraphNode]:
        """Iterate nodes of given kind that have a FILE parent but no requirement link.

        "Unlinked" means the node is structurally sound (has FILE parent via
        CONTAINS) but has no path to any REQUIREMENT through traceability edges.

        Args:
            kind: The NodeKind to check (typically TEST or CODE).

        Yields:
            Unlinked GraphNode instances.
        """
        for node in self.iter_by_kind(kind):
            # Must have a FILE parent (not a structural orphan)
            has_file_parent = any(
                p.kind == NodeKind.FILE for p in node.iter_parents(edge_kinds={EdgeKind.CONTAINS})
            )
            if has_file_parent and not self.is_reachable_to_requirement(node):
                yield node

    def iter_structural_orphans(self) -> Iterator[GraphNode]:
        """Iterate nodes that have no FILE ancestor.

        Structural orphans indicate build pipeline bugs — nodes that
        failed to wire into the file structure.
        Skips FILE nodes (they are files) and INSTANCE nodes (virtual, no file).

        Yields:
            Structurally orphaned GraphNode instances.
        """
        skip_kinds = {NodeKind.FILE}
        for node in self.all_nodes():
            if node.kind in skip_kinds:
                continue
            # INSTANCE nodes are virtual (no file) — skip
            stereotype = node.get_field("stereotype")
            if stereotype is not None and getattr(stereotype, "value", None) == "instance":
                continue
            if node.file_node() is None:
                yield node

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
        elif op == "change_edge_targets":
            self._undo_change_edge_targets(entry)
        elif op == "add_assertion":
            self._undo_add_assertion(entry)
        elif op == "delete_assertion":
            self._undo_delete_assertion(entry)
        elif op == "update_assertion":
            self._undo_update_assertion(entry)
        elif op == "rename_assertion":
            self._undo_rename_assertion(entry)
        elif op == "move_node_to_file":
            self._undo_move_node_to_file(entry)
        elif op == "rename_file":
            self._undo_rename_file(entry)
        elif op == "fix_broken_reference":
            self._undo_fix_broken_reference(entry)
        elif op in (
            "update_journey_field",
            "update_journey_section",
            "add_journey_section",
            "delete_journey_section",
            "reconstruct_journey_body",
        ):
            self._undo_journey_body_mutation(entry)
        elif op == "add_journey":
            self._undo_add_journey(entry)
        elif op == "delete_journey":
            self._undo_delete_journey(entry)
        # Unknown operations are silently ignored (forward compatibility)

    def _undo_rename_node(self, entry: MutationEntry) -> None:
        """Undo a node rename operation."""
        old_id = entry.before_state.get("id")
        new_id = entry.after_state.get("id")
        if old_id and new_id and new_id in self._index:
            node = self._index.pop(new_id)
            node.set_id(old_id)
            self._index[old_id] = node

    def _undo_update_title(self, entry: MutationEntry) -> None:
        """Undo a title update operation."""
        node_id = entry.target_id
        old_title = entry.before_state.get("title")
        if node_id in self._index and old_title is not None:
            self._index[node_id].set_label(old_title)

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
                parent.unlink(node)

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
        if entry.after_state.get("duplicate"):
            return  # No-op was recorded; nothing to undo
        source_id = entry.before_state.get("source_id")
        target_id = entry.before_state.get("target_id")
        was_orphan = entry.before_state.get("was_orphan", False)

        if source_id and target_id:
            # Check if this was a broken reference (never created actual edge)
            if entry.after_state.get("broken"):
                # Remove from broken references
                self._broken_references = [
                    br
                    for br in self._broken_references
                    if not (br.source_id == source_id and br.target_id == target_id)
                ]
            else:
                # Remove the specific edge that was added
                source = self._index.get(source_id)
                target = self._index.get(target_id)
                if source and target:
                    edge_kind_val = entry.after_state.get("edge_kind", "")
                    at = tuple(entry.after_state.get("assertion_targets", []))
                    for edge in list(target.iter_outgoing_edges()):
                        if (
                            edge.target.id == source_id
                            and edge.kind.value == edge_kind_val
                            and tuple(edge.assertion_targets) == at
                        ):
                            target.remove_edge(edge)
                            break

            # Restore orphan status
            if was_orphan and source_id in self._index:
                self._orphaned_ids.add(source_id)

    def _undo_delete_edge(self, entry: MutationEntry) -> None:
        """Undo a delete edge operation (restore the edge)."""
        source_id = entry.before_state.get("source_id")
        target_id = entry.before_state.get("target_id")
        edge_kind_str = entry.before_state.get("edge_kind")
        assertion_targets = entry.before_state.get("assertion_targets", [])
        became_orphan = entry.after_state.get("became_orphan", False)

        if source_id and target_id and edge_kind_str:
            source = self._index.get(source_id)
            target = self._index.get(target_id)
            if source and target:
                edge_kind = EdgeKind(edge_kind_str)
                target.link(source, edge_kind, assertion_targets or None)

                # Remove from orphans if it was marked orphan after deletion
                if became_orphan:
                    self._orphaned_ids.discard(source_id)

    def _undo_change_edge_kind(self, entry: MutationEntry) -> None:
        """Undo an edge kind change."""
        source_id = entry.before_state.get("source_id")
        target_id = entry.before_state.get("target_id")
        old_kind = entry.before_state.get("edge_kind")
        if source_id and target_id and old_kind:
            source = self._index.get(source_id)
            target = self._index.get(target_id)
            if source and target:
                # Find and update the edge (dataclass field, not _kind)
                for edge in source.iter_incoming_edges():
                    if edge.source.id == target_id:
                        edge.kind = EdgeKind(old_kind)
                        break

    def _undo_change_edge_targets(self, entry: MutationEntry) -> None:
        """Undo an edge assertion_targets change."""
        source_id = entry.before_state.get("source_id")
        target_id = entry.before_state.get("target_id")
        old_targets = entry.before_state.get("assertion_targets", [])
        if source_id and target_id:
            source = self._index.get(source_id)
            if source:
                for edge in source.iter_incoming_edges():
                    if edge.source.id == target_id and edge.kind in (
                        EdgeKind.IMPLEMENTS,
                        EdgeKind.REFINES,
                    ):
                        edge.assertion_targets.clear()
                        edge.assertion_targets.extend(old_targets)
                        break

    def _undo_move_node_to_file(self, entry: MutationEntry) -> None:
        """Undo a move_node_to_file operation."""
        node_id = entry.target_id
        old_file_id = entry.before_state.get("file_id")
        new_file_id = entry.after_state.get("file_id")
        old_metadata = entry.before_state.get("metadata", {})

        if node_id and old_file_id and new_file_id:
            node = self._index.get(node_id)
            old_file = self._index.get(old_file_id)
            new_file = self._index.get(new_file_id)

            if node and old_file and new_file:
                # Unlink from new file
                new_file.unlink(node)

                # Re-link to old file with original metadata
                edge = old_file.link(node, EdgeKind.CONTAINS)
                edge.metadata.update(old_metadata)

    def _undo_rename_file(self, entry: MutationEntry) -> None:
        """Undo a rename_file operation."""
        old_id = entry.before_state.get("id")
        new_id = entry.after_state.get("id")
        old_rel_path = entry.before_state.get("relative_path")
        old_abs_path = entry.before_state.get("absolute_path")

        if old_id and new_id and new_id in self._index:
            node = self._index.pop(new_id)
            node.set_id(old_id)
            self._index[old_id] = node

            if old_rel_path is not None:
                node.set_field("relative_path", old_rel_path)
            if old_abs_path is not None:
                node.set_field("absolute_path", old_abs_path)

    def _undo_fix_broken_reference(self, entry: MutationEntry) -> None:
        """Undo a fix broken reference operation."""
        source_id = entry.before_state.get("source_id")
        old_target_id = entry.before_state.get("old_target_id")
        new_target_id = entry.after_state.get("new_target_id")
        edge_kind_str = entry.before_state.get("edge_kind")
        was_orphan = entry.before_state.get("was_orphan", False)

        if source_id and old_target_id and new_target_id and edge_kind_str:
            source = self._index.get(source_id)

            # Check if the fix was successful (actual edge created)
            if entry.after_state.get("fixed"):
                # Remove the edge that was created
                new_target = self._index.get(new_target_id)
                if source and new_target:
                    new_target.unlink(source)
            else:
                # Remove from broken references (with new target)
                self._broken_references = [
                    br
                    for br in self._broken_references
                    if not (br.source_id == source_id and br.target_id == new_target_id)
                ]

            # Restore the original broken reference
            self._broken_references.append(
                BrokenReference(
                    source_id=source_id,
                    target_id=old_target_id,
                    edge_kind=edge_kind_str,
                )
            )

            # Restore orphan status
            if was_orphan and source_id in self._index:
                self._orphaned_ids.add(source_id)

    def _undo_add_assertion(self, entry: MutationEntry) -> None:
        """Undo an add assertion operation."""
        assertion_id = entry.target_id
        if assertion_id in self._index:
            node = self._index.pop(assertion_id)
            for parent in list(node.iter_parents()):
                parent.unlink(node)
                # Restore parent hash (even if None)
                if "parent_hash" in entry.before_state:
                    parent.set_field("hash", entry.before_state["parent_hash"])

    def _undo_delete_assertion(self, entry: MutationEntry) -> None:
        """Undo a delete assertion operation."""
        # First, undo any compaction renames in reverse order
        renames = entry.before_state.get("renames", [])
        for rename in reversed(renames):
            old_id = rename.get("old_id")
            new_id = rename.get("new_id")
            old_label = rename.get("old_label")
            new_label = rename.get("new_label")

            if new_id and new_id in self._index:
                node = self._index.pop(new_id)
                node.set_id(old_id)
                node.set_field("label", old_label)
                self._index[old_id] = node

                # Update edges back
                for edge_parent in self._index.values():
                    for edge in edge_parent.iter_outgoing_edges():
                        if new_label in edge.assertion_targets:
                            edge.assertion_targets.remove(new_label)
                            edge.assertion_targets.append(old_label)

        # Restore the deleted assertion
        node_id = entry.target_id
        for i, node in enumerate(self._deleted_nodes):
            if node.id == node_id:
                self._deleted_nodes.pop(i)
                # Restore original ID and label
                old_id = entry.before_state.get("id", node_id)
                old_label = entry.before_state.get("label")
                node.set_id(old_id)
                if old_label:
                    node.set_field("label", old_label)
                self._index[old_id] = node
                # Restore parent link
                parent_id = entry.before_state.get("parent_id")
                if parent_id and parent_id in self._index:
                    parent = self._index[parent_id]
                    parent.link(node, EdgeKind.STRUCTURES)
                    # Restore parent hash (even if None)
                    if "parent_hash" in entry.before_state:
                        parent.set_field("hash", entry.before_state["parent_hash"])
                break

    def _undo_update_assertion(self, entry: MutationEntry) -> None:
        """Undo an assertion text update."""
        node_id = entry.target_id
        old_text = entry.before_state.get("text")
        if node_id in self._index and old_text is not None:
            self._index[node_id].set_label(old_text)
            # Restore parent hash (even if None)
            parent_id = entry.before_state.get("parent_id")
            if parent_id and parent_id in self._index and "parent_hash" in entry.before_state:
                self._index[parent_id].set_field("hash", entry.before_state["parent_hash"])

    def _undo_rename_assertion(self, entry: MutationEntry) -> None:
        """Undo an assertion rename."""
        old_id = entry.before_state.get("id")
        new_id = entry.after_state.get("id")
        old_label = entry.before_state.get("label")
        new_label = entry.after_state.get("label")

        if old_id and new_id and new_id in self._index:
            node = self._index.pop(new_id)
            node.set_id(old_id)
            if old_label:
                node.set_field("label", old_label)
            self._index[old_id] = node

            # Update edges back
            if old_label and new_label:
                for edge_parent in self._index.values():
                    for edge in edge_parent.iter_outgoing_edges():
                        if new_label in edge.assertion_targets:
                            edge.assertion_targets.remove(new_label)
                            edge.assertion_targets.append(old_label)

            # Restore parent hash (even if None)
            parent_id = entry.before_state.get("parent_id")
            if parent_id and parent_id in self._index and "parent_hash" in entry.before_state:
                self._index[parent_id].set_field("hash", entry.before_state["parent_hash"])

    def _undo_journey_body_mutation(self, entry: MutationEntry) -> None:
        """Undo a journey field/section/body mutation by restoring body + fields."""
        node_id = entry.target_id
        if node_id not in self._index:
            return
        node = self._index[node_id]
        # Restore body
        old_body = entry.before_state.get("body")
        if old_body is not None:
            node.set_field("body", old_body)
        # Restore field if present (update_journey_field)
        field = entry.before_state.get("field")
        if field:
            old_value = entry.before_state.get("value")
            if field == "preamble":
                node.set_field("body_lines", old_value.splitlines() if old_value else [])
            else:
                node.set_field(field, old_value)
        # Restore section if present (update/delete section)
        old_name = entry.before_state.get("name")
        old_content = entry.before_state.get("content")
        op = entry.operation
        if op == "add_journey_section":
            # Remove the added section (last one matching after_state name)
            added_name = entry.after_state.get("name")
            sections = node.get_field("sections", [])
            for i in range(len(sections) - 1, -1, -1):
                if sections[i]["name"] == added_name:
                    sections.pop(i)
                    break
            node.set_field("sections", sections)
        elif op == "delete_journey_section" and old_name is not None:
            # Re-insert deleted section
            sections = node.get_field("sections", [])
            sections.append({"name": old_name, "content": old_content or ""})
            node.set_field("sections", sections)
        elif op == "update_journey_section" and old_name is not None:
            # Restore section name/content
            current_name = entry.after_state.get("name")
            sections = node.get_field("sections", [])
            for s in sections:
                if s["name"] == current_name:
                    s["name"] = old_name
                    if old_content is not None:
                        s["content"] = old_content
                    break
            node.set_field("sections", sections)

    def _undo_add_journey(self, entry: MutationEntry) -> None:
        """Undo an add journey operation (delete the added node)."""
        node_id = entry.target_id
        if node_id in self._index:
            node = self._index.pop(node_id)
            for parent in list(node.iter_parents()):
                parent.unlink(node)

    def _undo_delete_journey(self, entry: MutationEntry) -> None:
        """Undo a delete journey operation (restore the node)."""
        node_id = entry.target_id
        for i, node in enumerate(self._deleted_nodes):
            if node.id == node_id:
                self._deleted_nodes.pop(i)
                self._index[node_id] = node
                break

    # ─────────────────────────────────────────────────────────────────────────
    # Node Mutation API
    # ─────────────────────────────────────────────────────────────────────────

    def rename_node(self, old_id: str, new_id: str) -> MutationEntry:
        """Rename a node (e.g., REQ-p00001 -> REQ-p00002).

        Updates the node's ID, all edges pointing to/from this node,
        and assertion IDs if the node is a requirement.

        Args:
            old_id: Current node ID.
            new_id: New node ID.

        Returns:
            MutationEntry recording the operation.

        Raises:
            KeyError: If old_id is not found.
            ValueError: If new_id already exists.
        """
        if old_id not in self._index:
            raise KeyError(f"Node '{old_id}' not found")
        if new_id in self._index:
            raise ValueError(f"Node '{new_id}' already exists")

        node = self._index.pop(old_id)
        old_title = node.get_label()

        # Create mutation entry
        entry = MutationEntry(
            operation="rename_node",
            target_id=old_id,
            before_state={"id": old_id, "title": old_title},
            after_state={"id": new_id, "title": old_title},
        )

        # Update node ID
        node.set_id(new_id)
        self._index[new_id] = node

        # Update roots list if this was a root
        for _i, root in enumerate(self._roots):
            if root is node:
                break  # Root reference is same object, no update needed

        # Update orphaned_ids if this was an orphan
        if old_id in self._orphaned_ids:
            self._orphaned_ids.discard(old_id)
            self._orphaned_ids.add(new_id)

        # Update broken references that reference this node
        for i, br in enumerate(self._broken_references):
            if br.source_id == old_id:
                self._broken_references[i] = BrokenReference(
                    source_id=new_id,
                    target_id=br.target_id,
                    edge_kind=br.edge_kind,
                )
            elif br.target_id == old_id:
                self._broken_references[i] = BrokenReference(
                    source_id=br.source_id,
                    target_id=new_id,
                    edge_kind=br.edge_kind,
                )

        # If this is a requirement, rename its assertion children
        if node.kind == NodeKind.REQUIREMENT:
            for child in list(node.iter_children()):
                if child.kind == NodeKind.ASSERTION:
                    assertion_label = child.get_field("label", "")
                    if assertion_label:
                        old_assertion_id = f"{old_id}-{assertion_label}"
                        new_assertion_id = f"{new_id}-{assertion_label}"
                        if old_assertion_id in self._index:
                            self._index.pop(old_assertion_id)
                            child.set_id(new_assertion_id)
                            self._index[new_assertion_id] = child

        self._mutation_log.append(entry)
        return entry

    def update_title(self, node_id: str, new_title: str) -> MutationEntry:
        """Update requirement title. Does not affect hash.

        Args:
            node_id: The node ID to update.
            new_title: The new title.

        Returns:
            MutationEntry recording the operation.

        Raises:
            KeyError: If node_id is not found.
        """
        if node_id not in self._index:
            raise KeyError(f"Node '{node_id}' not found")

        node = self._index[node_id]
        old_title = node.get_label()

        entry = MutationEntry(
            operation="update_title",
            target_id=node_id,
            before_state={"title": old_title},
            after_state={"title": new_title},
        )

        node.set_label(new_title)
        self._mutation_log.append(entry)
        return entry

    def change_status(self, node_id: str, new_status: str) -> MutationEntry:
        """Change requirement status (e.g., Draft -> Active).

        Args:
            node_id: The node ID to update.
            new_status: The new status value.

        Returns:
            MutationEntry recording the operation.

        Raises:
            KeyError: If node_id is not found.
        """
        if node_id not in self._index:
            raise KeyError(f"Node '{node_id}' not found")

        node = self._index[node_id]
        old_status = node.get_field("status")

        entry = MutationEntry(
            operation="change_status",
            target_id=node_id,
            before_state={"status": old_status},
            after_state={"status": new_status},
        )

        node.set_field("status", new_status)
        self._mutation_log.append(entry)
        return entry

    def add_requirement(
        self,
        req_id: str,
        title: str,
        level: str,
        status: str = "Draft",
        parent_id: str | None = None,
        edge_kind: EdgeKind = EdgeKind.IMPLEMENTS,
    ) -> MutationEntry:
        """Add a new requirement node.

        Creates a node with the specified properties and optionally
        links it to a parent. Computes initial hash (empty body = specific hash).

        Args:
            req_id: The requirement ID (e.g., "REQ-p00001").
            title: The requirement title.
            level: The requirement level ("PRD", "OPS", "DEV").
            status: The requirement status (default "Draft").
            parent_id: Optional parent node ID to link to.
            edge_kind: Edge type for parent link (default IMPLEMENTS).

        Returns:
            MutationEntry recording the operation.

        Raises:
            ValueError: If req_id already exists.
            KeyError: If parent_id is specified but not found.
        """
        from elspais.utilities.hasher import calculate_hash

        if req_id in self._index:
            raise ValueError(f"Node '{req_id}' already exists")
        if parent_id and parent_id not in self._index:
            raise KeyError(f"Parent node '{parent_id}' not found")

        # Create the node
        node = GraphNode(
            id=req_id,
            kind=NodeKind.REQUIREMENT,
            label=title,
        )

        # Compute hash for empty body
        empty_hash = calculate_hash("")

        node._content = {
            "level": level,
            "status": status,
            "hash": empty_hash,
        }

        # Add to index
        self._index[req_id] = node

        # Build entry with before/after state
        entry = MutationEntry(
            operation="add_requirement",
            target_id=req_id,
            before_state={},  # Node didn't exist
            after_state={
                "id": req_id,
                "title": title,
                "level": level,
                "status": status,
                "hash": empty_hash,
                "parent_id": parent_id,
            },
        )

        # Link to parent if specified
        if parent_id:
            parent = self._index[parent_id]
            parent.link(node, edge_kind)
        else:
            # No parent - this is a root node
            self._roots.append(node)

        self._mutation_log.append(entry)
        return entry

    def delete_requirement(
        self,
        node_id: str,
        compact_assertions: bool = True,
    ) -> MutationEntry:
        """Delete a requirement.

        Removes the node from the index, moves it to _deleted_nodes for
        delta tracking, removes all edges to/from this node, and marks
        children as orphans.

        Args:
            node_id: The requirement ID to delete.
            compact_assertions: If True, sibling assertions are renumbered
                after deletion. (Currently not implemented - reserved for
                assertion deletion.)

        Returns:
            MutationEntry recording the operation.

        Raises:
            KeyError: If node_id is not found.
        """
        if node_id not in self._index:
            raise KeyError(f"Node '{node_id}' not found")

        node = self._index[node_id]
        was_root = node in self._roots

        # Record state before deletion
        _fn = node.file_node()
        source_path = _fn.get_field("relative_path") if _fn else None
        entry = MutationEntry(
            operation="delete_requirement",
            target_id=node_id,
            before_state={
                "id": node_id,
                "title": node.get_label(),
                "level": node.get_field("level"),
                "status": node.get_field("status"),
                "hash": node.get_field("hash"),
                "was_root": was_root,
                "parent_ids": [p.id for p in node.iter_parents()],
                "child_ids": [c.id for c in node.iter_children()],
                "source_path": source_path,
            },
            after_state={},  # Node deleted
        )

        # Remove from index
        self._index.pop(node_id)

        # Move to deleted_nodes for delta tracking
        self._deleted_nodes.append(node)

        # Remove from roots if present
        if was_root:
            self._roots = [r for r in self._roots if r.id != node_id]

        # Remove from orphaned_ids if present
        self._orphaned_ids.discard(node_id)

        # Disconnect from parents
        for parent in list(node.iter_parents()):
            parent.unlink(node)

        # Mark children as orphans (except assertions which go with the req)
        for child in list(node.iter_children()):
            if child.kind == NodeKind.ASSERTION:
                # Delete assertion children too
                if child.id in self._index:
                    self._index.pop(child.id)
                    self._deleted_nodes.append(child)
            else:
                # Non-assertion children become orphans
                node.unlink(child)
                self._orphaned_ids.add(child.id)

        self._mutation_log.append(entry)
        return entry

    # ─────────────────────────────────────────────────────────────────────────
    # Assertion Mutation API
    # ─────────────────────────────────────────────────────────────────────────

    # Assertion line pattern shared with RequirementParser
    _ASSERTION_LINE_RE = RequirementParser.ASSERTION_LINE_PATTERN

    def _update_assertion_in_body_text(self, body_text: str, label: str, new_text: str) -> str:
        """Update an assertion line in body_text.

        Args:
            body_text: The requirement body text.
            label: The assertion label (e.g., "A").
            new_text: The new assertion text.

        Returns:
            Updated body_text with the assertion modified.
        """
        pattern = re.compile(rf"^({re.escape(label)})\.\s+.*$", re.MULTILINE)
        return pattern.sub(rf"\1. {new_text}", body_text)

    def _add_assertion_to_body_text(self, body_text: str, label: str, text: str) -> str:
        """Add an assertion line to body_text.

        Inserts the assertion in sorted order within the assertions section.

        Args:
            body_text: The requirement body text.
            label: The assertion label (e.g., "C").
            text: The assertion text.

        Returns:
            Updated body_text with the new assertion added.
        """
        new_line = f"{label}. {text}"
        lines = body_text.split("\n")
        result_lines = []
        inserted = False

        for line in lines:
            match = self._ASSERTION_LINE_RE.match(line)
            if match and not inserted:
                existing_label = match.group(1)
                # Insert before this line if our label comes first
                if label < existing_label:
                    result_lines.append(new_line)
                    inserted = True
            result_lines.append(line)

        # If not inserted, append at end (either no assertions or comes last)
        if not inserted:
            # Check if there's an ## Assertions header to append after
            for i, line in enumerate(result_lines):
                if line.strip().lower() == "## assertions":
                    # Find next non-empty line or end of section
                    insert_pos = i + 1
                    while insert_pos < len(result_lines):
                        if result_lines[insert_pos].strip():
                            break
                        insert_pos += 1
                    # Find end of assertion block
                    while insert_pos < len(result_lines):
                        if not self._ASSERTION_LINE_RE.match(result_lines[insert_pos]):
                            break
                        insert_pos += 1
                    result_lines.insert(insert_pos, new_line)
                    inserted = True
                    break

            if not inserted:
                # No assertions section found, just append
                result_lines.append(new_line)

        return "\n".join(result_lines)

    def _delete_assertion_from_body_text(self, body_text: str, label: str) -> str:
        """Delete an assertion line from body_text.

        Args:
            body_text: The requirement body text.
            label: The assertion label to delete (e.g., "B").

        Returns:
            Updated body_text with the assertion removed.
        """
        pattern = re.compile(rf"^{re.escape(label)}\.\s+.*\n?", re.MULTILINE)
        return pattern.sub("", body_text)

    def _rename_assertion_in_body_text(self, body_text: str, old_label: str, new_label: str) -> str:
        """Rename an assertion label in body_text.

        Args:
            body_text: The requirement body text.
            old_label: The current assertion label (e.g., "A").
            new_label: The new assertion label (e.g., "D").

        Returns:
            Updated body_text with the assertion label changed.
        """
        pattern = re.compile(rf"^{re.escape(old_label)}(\.\s+.*)$", re.MULTILINE)
        return pattern.sub(rf"{new_label}\1", body_text)

    def _compute_hash(self, req_node: GraphNode) -> str:
        """Compute the expected hash for a requirement node without modifying it.

        Supports two modes (configurable via [validation].hash_mode):
        - full-text: hash every line between header and footer (body_text)
        - normalized-text: hash normalized assertion text only
        """
        from elspais.utilities.hasher import calculate_hash, compute_normalized_hash

        if self.hash_mode == "normalized-text":
            assertions = []
            for child in req_node.iter_children():
                if child.kind == NodeKind.ASSERTION:
                    label = child.get_field("label", "")
                    text = child.get_label() or ""
                    if label and text:
                        assertions.append((label, text))
            return compute_normalized_hash(assertions)
        else:
            body_text = req_node.get_field("body_text", "")
            return calculate_hash(body_text)

    def _recompute_requirement_hash(self, req_node: GraphNode) -> str:
        """Recompute and store the hash for a requirement node.

        Returns:
            The new hash value.
        """
        new_hash = self._compute_hash(req_node)
        req_node.set_field("hash", new_hash)
        return new_hash

    def rename_assertion(self, old_id: str, new_label: str) -> MutationEntry:
        """Rename assertion label (e.g., REQ-p00001-A -> REQ-p00001-D).

        Updates the assertion node ID, edges with assertion_targets,
        and recomputes the parent requirement hash.

        Args:
            old_id: Current assertion ID (e.g., "REQ-p00001-A").
            new_label: New assertion label (e.g., "D").

        Returns:
            MutationEntry recording the operation.

        Raises:
            KeyError: If old_id is not found.
            ValueError: If the node is not an assertion or new_id exists.
        """
        if old_id not in self._index:
            raise KeyError(f"Assertion '{old_id}' not found")

        node = self._index[old_id]
        if node.kind != NodeKind.ASSERTION:
            raise ValueError(f"Node '{old_id}' is not an assertion")

        # Get parent requirement
        parents = [p for p in node.iter_parents() if p.kind == NodeKind.REQUIREMENT]
        if not parents:
            raise ValueError(f"Assertion '{old_id}' has no parent requirement")
        parent = parents[0]

        # Compute new ID
        old_label = node.get_field("label", "")
        new_id = f"{parent.id}-{new_label}"

        if new_id in self._index:
            raise ValueError(f"Assertion '{new_id}' already exists")

        # Record before state
        old_hash = parent.get_field("hash")
        entry = MutationEntry(
            operation="rename_assertion",
            target_id=old_id,
            before_state={
                "id": old_id,
                "label": old_label,
                "parent_id": parent.id,
                "parent_hash": old_hash,
            },
            after_state={
                "id": new_id,
                "label": new_label,
            },
            affects_hash=True,
        )

        # Update assertion node
        self._index.pop(old_id)
        node.set_id(new_id)
        node.set_field("label", new_label)
        self._index[new_id] = node

        # Update edges with assertion_targets referencing old label
        for parent_node in self._index.values():
            for edge in parent_node.iter_outgoing_edges():
                if old_label in edge.assertion_targets:
                    edge.assertion_targets.remove(old_label)
                    edge.assertion_targets.append(new_label)

        # Update body_text to reflect renamed assertion
        body_text = parent.get_field("body_text", "")
        if body_text:
            new_body_text = self._rename_assertion_in_body_text(body_text, old_label, new_label)
            parent.set_field("body_text", new_body_text)

        # Recompute parent hash
        self._recompute_requirement_hash(parent)

        self._mutation_log.append(entry)
        return entry

    def update_assertion(self, assertion_id: str, new_text: str) -> MutationEntry:
        """Update assertion text.

        Recomputes the parent requirement hash.

        Args:
            assertion_id: The assertion ID to update.
            new_text: The new assertion text.

        Returns:
            MutationEntry recording the operation.

        Raises:
            KeyError: If assertion_id is not found.
            ValueError: If the node is not an assertion.
        """
        if assertion_id not in self._index:
            raise KeyError(f"Assertion '{assertion_id}' not found")

        node = self._index[assertion_id]
        if node.kind != NodeKind.ASSERTION:
            raise ValueError(f"Node '{assertion_id}' is not an assertion")

        # Get parent requirement
        parents = [p for p in node.iter_parents() if p.kind == NodeKind.REQUIREMENT]
        if not parents:
            raise ValueError(f"Assertion '{assertion_id}' has no parent requirement")
        parent = parents[0]

        old_text = node.get_label()
        old_hash = parent.get_field("hash")

        entry = MutationEntry(
            operation="update_assertion",
            target_id=assertion_id,
            before_state={
                "text": old_text,
                "parent_id": parent.id,
                "parent_hash": old_hash,
            },
            after_state={
                "text": new_text,
            },
            affects_hash=True,
        )

        # Update assertion text
        node.set_label(new_text)

        # Update body_text to reflect updated assertion
        label = node.get_field("label", "")
        body_text = parent.get_field("body_text", "")
        if body_text and label:
            new_body_text = self._update_assertion_in_body_text(body_text, label, new_text)
            parent.set_field("body_text", new_body_text)

        # Recompute parent hash
        self._recompute_requirement_hash(parent)

        self._mutation_log.append(entry)
        return entry

    def add_assertion(self, req_id: str, label: str, text: str) -> MutationEntry:
        """Add assertion to requirement.

        Creates an assertion node, links it as child of the requirement,
        and recomputes the requirement hash.

        Args:
            req_id: The parent requirement ID.
            label: The assertion label (e.g., "A", "B").
            text: The assertion text.

        Returns:
            MutationEntry recording the operation.

        Raises:
            KeyError: If req_id is not found.
            ValueError: If req_id is not a requirement or assertion exists.
        """
        if req_id not in self._index:
            raise KeyError(f"Requirement '{req_id}' not found")

        parent = self._index[req_id]
        if parent.kind != NodeKind.REQUIREMENT:
            raise ValueError(f"Node '{req_id}' is not a requirement")

        assertion_id = f"{req_id}-{label}"
        if assertion_id in self._index:
            raise ValueError(f"Assertion '{assertion_id}' already exists")

        old_hash = parent.get_field("hash")

        # Create assertion node
        assertion_node = GraphNode(
            id=assertion_id,
            kind=NodeKind.ASSERTION,
            label=text,
        )
        assertion_node._content = {"label": label}

        # Add to index and link to parent
        self._index[assertion_id] = assertion_node
        parent.link(assertion_node, EdgeKind.STRUCTURES)

        # Update body_text to include new assertion
        body_text = parent.get_field("body_text", "")
        if body_text:
            new_body_text = self._add_assertion_to_body_text(body_text, label, text)
            parent.set_field("body_text", new_body_text)

        # Recompute parent hash
        new_hash = self._recompute_requirement_hash(parent)

        entry = MutationEntry(
            operation="add_assertion",
            target_id=assertion_id,
            before_state={
                "parent_id": req_id,
                "parent_hash": old_hash,
            },
            after_state={
                "id": assertion_id,
                "label": label,
                "text": text,
                "parent_hash": new_hash,
            },
            affects_hash=True,
        )

        self._mutation_log.append(entry)
        return entry

    def delete_assertion(
        self,
        assertion_id: str,
        compact: bool = True,
    ) -> MutationEntry:
        """Delete assertion with optional compaction.

        If compact=True and deleting B from [A, B, C, D]:
        - C -> B, D -> C
        - Updates all edges referencing C, D
        - Recomputes parent hash

        Args:
            assertion_id: The assertion ID to delete.
            compact: If True, renumber subsequent assertions.

        Returns:
            MutationEntry recording the operation.

        Raises:
            KeyError: If assertion_id is not found.
            ValueError: If the node is not an assertion.
        """
        if assertion_id not in self._index:
            raise KeyError(f"Assertion '{assertion_id}' not found")

        node = self._index[assertion_id]
        if node.kind != NodeKind.ASSERTION:
            raise ValueError(f"Node '{assertion_id}' is not an assertion")

        # Get parent requirement
        parents = [p for p in node.iter_parents() if p.kind == NodeKind.REQUIREMENT]
        if not parents:
            raise ValueError(f"Assertion '{assertion_id}' has no parent requirement")
        parent = parents[0]

        old_label = node.get_field("label", "")
        old_text = node.get_label()
        old_hash = parent.get_field("hash")

        # Collect sibling assertions sorted by label
        siblings = []
        for child in parent.iter_children():
            if child.kind == NodeKind.ASSERTION:
                siblings.append((child.get_field("label", ""), child))
        siblings.sort(key=lambda x: x[0])

        # Track renames for undo (label_before -> label_after)
        renames: list[dict[str, str]] = []

        # Remove from index first
        self._index.pop(assertion_id)
        parent.unlink(node)
        self._deleted_nodes.append(node)

        # Remove edges referencing this assertion
        for parent_node in self._index.values():
            for edge in parent_node.iter_outgoing_edges():
                if old_label in edge.assertion_targets:
                    edge.assertion_targets.remove(old_label)

        # Update body_text to remove deleted assertion
        body_text = parent.get_field("body_text", "")
        if body_text:
            body_text = self._delete_assertion_from_body_text(body_text, old_label)

        # Compact if requested
        if compact:
            # Find assertions after the deleted one
            deleted_found = False
            for sib_label, sib_node in siblings:
                if sib_node is node:
                    deleted_found = True
                    continue
                if deleted_found and sib_node.id in self._index:
                    # This sibling needs to be renamed to previous letter
                    prev_label = chr(ord(sib_label) - 1)
                    old_sib_id = sib_node.id
                    new_sib_id = f"{parent.id}-{prev_label}"

                    renames.append(
                        {
                            "old_id": old_sib_id,
                            "new_id": new_sib_id,
                            "old_label": sib_label,
                            "new_label": prev_label,
                        }
                    )

                    # Update the node
                    self._index.pop(old_sib_id)
                    sib_node.set_id(new_sib_id)
                    sib_node.set_field("label", prev_label)
                    self._index[new_sib_id] = sib_node

                    # Update edges referencing this assertion
                    for edge_parent in self._index.values():
                        for edge in edge_parent.iter_outgoing_edges():
                            if sib_label in edge.assertion_targets:
                                edge.assertion_targets.remove(sib_label)
                                edge.assertion_targets.append(prev_label)

                    # Update body_text for this rename
                    if body_text:
                        body_text = self._rename_assertion_in_body_text(
                            body_text, sib_label, prev_label
                        )

        # Update parent's body_text field
        if parent.get_field("body_text", ""):
            parent.set_field("body_text", body_text)

        # Recompute parent hash
        new_hash = self._recompute_requirement_hash(parent)

        entry = MutationEntry(
            operation="delete_assertion",
            target_id=assertion_id,
            before_state={
                "id": assertion_id,
                "label": old_label,
                "text": old_text,
                "parent_id": parent.id,
                "parent_hash": old_hash,
                "compact": compact,
                "renames": renames,
            },
            after_state={
                "parent_hash": new_hash,
            },
            affects_hash=True,
        )

        self._mutation_log.append(entry)
        return entry

    # ─────────────────────────────────────────────────────────────────────────
    # Edge Mutation API
    # ─────────────────────────────────────────────────────────────────────────

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        edge_kind: EdgeKind,
        assertion_targets: list[str] | None = None,
        target_graph: TraceGraph | None = None,
    ) -> MutationEntry:
        """Add a new edge (reference).

        Creates a relationship from source to target. If target doesn't exist,
        adds to _broken_references instead of creating an edge.

        Args:
            source_id: The child/source node ID.
            target_id: The parent/target node ID.
            edge_kind: The type of relationship.
            assertion_targets: Optional assertion labels targeted.
            target_graph: Optional graph to look up target_id in. When
                provided, resolves cross-graph edges. Defaults to self.

        Returns:
            MutationEntry recording the operation.

        Raises:
            KeyError: If source_id is not found.
        """
        if source_id not in self._index:
            raise KeyError(f"Source node '{source_id}' not found")

        source = self._index[source_id]
        resolve_graph = target_graph or self
        target = resolve_graph._index.get(target_id)

        # Check if source was orphan before
        was_orphan = source_id in self._orphaned_ids

        entry = MutationEntry(
            operation="add_edge",
            target_id=source_id,
            before_state={
                "source_id": source_id,
                "target_id": target_id,
                "was_orphan": was_orphan,
            },
            after_state={
                "source_id": source_id,
                "target_id": target_id,
                "edge_kind": edge_kind.value,
                "assertion_targets": assertion_targets or [],
            },
        )

        if target:
            # Check for exact duplicate edge
            new_at = tuple(assertion_targets or [])
            for existing in target.iter_outgoing_edges():
                if (
                    existing.target.id == source_id
                    and existing.kind == edge_kind
                    and tuple(existing.assertion_targets) == new_at
                ):
                    entry.after_state["duplicate"] = True
                    self._mutation_log.append(entry)
                    return entry

            # Create the edge
            target.link(source, edge_kind, assertion_targets)

            # Source is no longer orphan (it now has a parent)
            self._orphaned_ids.discard(source_id)
        else:
            # Target doesn't exist - record as broken reference
            self._broken_references.append(
                BrokenReference(
                    source_id=source_id,
                    target_id=target_id,
                    edge_kind=edge_kind.value,
                )
            )
            entry.after_state["broken"] = True

        self._mutation_log.append(entry)
        return entry

    def change_edge_kind(
        self,
        source_id: str,
        target_id: str,
        new_kind: EdgeKind,
    ) -> MutationEntry:
        """Change edge type (e.g., IMPLEMENTS -> REFINES).

        Args:
            source_id: The child/source node ID.
            target_id: The parent/target node ID.
            new_kind: The new edge kind.

        Returns:
            MutationEntry recording the operation.

        Raises:
            KeyError: If source_id or target_id is not found.
            ValueError: If no edge exists between source and target.
        """
        if source_id not in self._index:
            raise KeyError(f"Source node '{source_id}' not found")
        if target_id not in self._index:
            raise KeyError(f"Target node '{target_id}' not found")

        source = self._index[source_id]
        # target_id already validated above, used in edge lookup below

        # Find the edge from target to source (target is parent, source is child)
        edge_to_update = None
        for edge in source.iter_incoming_edges():
            if edge.source.id == target_id:
                edge_to_update = edge
                break

        if edge_to_update is None:
            raise ValueError(f"No edge exists from '{target_id}' to '{source_id}'")

        old_kind = edge_to_update.kind

        entry = MutationEntry(
            operation="change_edge_kind",
            target_id=source_id,
            before_state={
                "source_id": source_id,
                "target_id": target_id,
                "edge_kind": old_kind.value,
                "assertion_targets": list(edge_to_update.assertion_targets),
            },
            after_state={
                "source_id": source_id,
                "target_id": target_id,
                "edge_kind": new_kind.value,
                "assertion_targets": list(edge_to_update.assertion_targets),
            },
        )

        # Update the edge kind directly (dataclass field, not _kind)
        edge_to_update.kind = new_kind

        self._mutation_log.append(entry)
        return entry

    # Implements: REQ-o00062-C
    def change_edge_targets(
        self,
        source_id: str,
        target_id: str,
        assertion_targets: list[str],
    ) -> MutationEntry:
        """Change assertion targets on an existing IMPLEMENTS/REFINES/VALIDATES edge.

        Args:
            source_id: The child/source node ID.
            target_id: The parent/target node ID.
            assertion_targets: New assertion target labels (empty list = whole-req).

        Returns:
            MutationEntry recording the operation.

        Raises:
            KeyError: If source_id or target_id is not found.
            ValueError: If no matching edge exists between source and target.
        """
        if source_id not in self._index:
            raise KeyError(f"Source node '{source_id}' not found")
        if target_id not in self._index:
            raise KeyError(f"Target node '{target_id}' not found")

        source = self._index[source_id]

        # Find the edge from target to source (target is parent, source is child)
        edge_to_update = None
        for edge in source.iter_incoming_edges():
            if edge.source.id == target_id and edge.kind in (
                EdgeKind.IMPLEMENTS,
                EdgeKind.REFINES,
                EdgeKind.VALIDATES,
            ):
                edge_to_update = edge
                break

        if edge_to_update is None:
            raise ValueError(
                f"No IMPLEMENTS/REFINES/VALIDATES edge exists from '{target_id}' to '{source_id}'"
            )

        old_targets = list(edge_to_update.assertion_targets)

        entry = MutationEntry(
            operation="change_edge_targets",
            target_id=source_id,
            before_state={
                "source_id": source_id,
                "target_id": target_id,
                "assertion_targets": old_targets,
            },
            after_state={
                "source_id": source_id,
                "target_id": target_id,
                "assertion_targets": list(assertion_targets),
            },
        )

        # Update assertion_targets in place
        edge_to_update.assertion_targets.clear()
        edge_to_update.assertion_targets.extend(assertion_targets)

        self._mutation_log.append(entry)
        return entry

    def delete_edge(self, source_id: str, target_id: str) -> MutationEntry:
        """Remove an edge.

        Removes the edge from target to source. If source has no other parents
        (except roots), it may become an orphan.

        Args:
            source_id: The child/source node ID.
            target_id: The parent/target node ID.

        Returns:
            MutationEntry recording the operation.

        Raises:
            KeyError: If source_id or target_id is not found.
            ValueError: If no edge exists between source and target.
        """
        if source_id not in self._index:
            raise KeyError(f"Source node '{source_id}' not found")
        if target_id not in self._index:
            raise KeyError(f"Target node '{target_id}' not found")

        source = self._index[source_id]
        target = self._index[target_id]

        # Find the edge from target to source
        edge_to_delete = None
        for edge in source.iter_incoming_edges():
            if edge.source.id == target_id:
                edge_to_delete = edge
                break

        if edge_to_delete is None:
            raise ValueError(f"No edge exists from '{target_id}' to '{source_id}'")

        entry = MutationEntry(
            operation="delete_edge",
            target_id=source_id,
            before_state={
                "source_id": source_id,
                "target_id": target_id,
                "edge_kind": edge_to_delete.kind.value,
                "assertion_targets": list(edge_to_delete.assertion_targets),
            },
            after_state={
                "source_id": source_id,
                "target_id": target_id,
            },
        )

        # Remove the specific edge (not all edges between these nodes)
        target.remove_edge(edge_to_delete)

        # Check if source is now orphaned (no parents, not a root)
        if source.parent_count() == 0 and not self.has_root(source_id):
            # Only requirements can be orphaned
            if source.kind == NodeKind.REQUIREMENT:
                self._orphaned_ids.add(source_id)
                entry.after_state["became_orphan"] = True

        self._mutation_log.append(entry)
        return entry

    # Implements: REQ-o00063
    def move_node_to_file(
        self,
        node_id: str,
        target_file_id: str,
    ) -> MutationEntry:
        """Move a content node from one FILE parent to another.

        Re-wires the CONTAINS edge from the current FILE parent to the
        target FILE node. ASSERTION and REMAINDER children follow via
        STRUCTURES edges automatically.

        Args:
            node_id: The node to move.
            target_file_id: The FILE node to move to.

        Returns:
            MutationEntry recording the operation.

        Raises:
            KeyError: If node_id or target_file_id is not found.
            ValueError: If target is not a FILE node, or node has no
                current FILE parent.
        """
        if node_id not in self._index:
            raise KeyError(f"Node '{node_id}' not found")
        if target_file_id not in self._index:
            raise KeyError(f"Target file '{target_file_id}' not found")

        node = self._index[node_id]
        target_file = self._index[target_file_id]

        if target_file.kind != NodeKind.FILE:
            raise ValueError(f"Target '{target_file_id}' is not a FILE node")

        # Find current FILE parent via CONTAINS edge
        current_file = node.file_node()
        if current_file is None:
            raise ValueError(f"Node '{node_id}' has no FILE parent")

        # Get current render_order from the CONTAINS edge
        old_render_order = 0.0
        old_metadata: dict = {}
        for edge in node.iter_incoming_edges():
            if edge.source is current_file and edge.kind == EdgeKind.CONTAINS:
                old_render_order = edge.metadata.get("render_order", 0.0)
                old_metadata = dict(edge.metadata)
                break

        entry = MutationEntry(
            operation="move_node_to_file",
            target_id=node_id,
            before_state={
                "file_id": current_file.id,
                "render_order": old_render_order,
                "metadata": old_metadata,
            },
            after_state={
                "file_id": target_file_id,
            },
        )

        # Unlink from current file
        current_file.unlink(node)

        # Compute render_order at end of target file's children
        max_order = -1.0
        for edge in target_file.iter_outgoing_edges():
            if edge.kind == EdgeKind.CONTAINS:
                order = edge.metadata.get("render_order", 0.0)
                if order > max_order:
                    max_order = order
        new_order = max_order + 1.0

        # Link to target file
        new_edge = target_file.link(node, EdgeKind.CONTAINS)
        new_edge.metadata["render_order"] = new_order

        entry.after_state["render_order"] = new_order

        self._mutation_log.append(entry)
        return entry

    # Implements: REQ-o00063
    def rename_file(
        self,
        file_id: str,
        new_relative_path: str,
        repo_root: Path | None = None,
    ) -> MutationEntry:
        """Rename a FILE node, updating its ID, index, and path fields.

        Args:
            file_id: The current FILE node ID (e.g. "file:spec/main.md").
            new_relative_path: New repo-relative path (e.g. "spec/renamed.md").
            repo_root: Optional repo root for computing absolute_path.

        Returns:
            MutationEntry recording the operation.

        Raises:
            KeyError: If file_id is not found.
            ValueError: If the node is not a FILE node.
        """
        if file_id not in self._index:
            raise KeyError(f"File node '{file_id}' not found")

        node = self._index[file_id]
        if node.kind != NodeKind.FILE:
            raise ValueError(f"Node '{file_id}' is not a FILE node")

        new_id = f"file:{new_relative_path}"
        old_relative_path = node.get_field("relative_path")
        old_absolute_path = node.get_field("absolute_path")

        entry = MutationEntry(
            operation="rename_file",
            target_id=file_id,
            before_state={
                "id": file_id,
                "relative_path": old_relative_path,
                "absolute_path": str(old_absolute_path) if old_absolute_path else None,
            },
            after_state={
                "id": new_id,
                "relative_path": new_relative_path,
            },
        )

        # Update index
        del self._index[file_id]
        node.set_id(new_id)
        self._index[new_id] = node

        # Update path fields
        node.set_field("relative_path", new_relative_path)
        if repo_root is not None:
            node.set_field("absolute_path", str(repo_root / new_relative_path))

        self._mutation_log.append(entry)
        return entry

    def fix_broken_reference(
        self,
        source_id: str,
        old_target_id: str,
        new_target_id: str,
    ) -> MutationEntry:
        """Fix a broken reference by changing its target.

        Finds a broken reference from source to old_target and attempts to
        redirect it to new_target. If new_target also doesn't exist, the
        reference remains broken (but with updated target).

        Args:
            source_id: The source node ID with the broken reference.
            old_target_id: The current (broken) target ID.
            new_target_id: The new target ID to point to.

        Returns:
            MutationEntry recording the operation.

        Raises:
            KeyError: If source_id is not found.
            ValueError: If no broken reference exists from source to old_target.
        """
        if source_id not in self._index:
            raise KeyError(f"Source node '{source_id}' not found")

        # Find the broken reference
        broken_ref = None
        broken_ref_index = None
        for i, br in enumerate(self._broken_references):
            if br.source_id == source_id and br.target_id == old_target_id:
                broken_ref = br
                broken_ref_index = i
                break

        if broken_ref is None:
            raise ValueError(f"No broken reference from '{source_id}' to '{old_target_id}'")

        source = self._index[source_id]
        new_target = self._index.get(new_target_id)
        edge_kind = EdgeKind(broken_ref.edge_kind)

        # Check if source was orphan before
        was_orphan = source_id in self._orphaned_ids

        entry = MutationEntry(
            operation="fix_broken_reference",
            target_id=source_id,
            before_state={
                "source_id": source_id,
                "old_target_id": old_target_id,
                "edge_kind": broken_ref.edge_kind,
                "was_orphan": was_orphan,
            },
            after_state={
                "source_id": source_id,
                "new_target_id": new_target_id,
                "edge_kind": broken_ref.edge_kind,
            },
        )

        # Remove the old broken reference
        self._broken_references.pop(broken_ref_index)

        if new_target:
            # Create valid edge
            new_target.link(source, edge_kind)

            # Source is no longer orphan
            self._orphaned_ids.discard(source_id)
            entry.after_state["fixed"] = True
        else:
            # New target also doesn't exist - remains broken
            self._broken_references.append(
                BrokenReference(
                    source_id=source_id,
                    target_id=new_target_id,
                    edge_kind=broken_ref.edge_kind,
                )
            )
            entry.after_state["still_broken"] = True

        self._mutation_log.append(entry)
        return entry

    # ─────────────────────────────────────────────────────────────────────────
    # Journey Mutation API
    # ─────────────────────────────────────────────────────────────────────────

    def _reconstruct_journey_body(self, node: GraphNode) -> str:
        """Rebuild body text from structured fields + live graph edges."""
        lines: list[str] = []
        lines.append(f"## {node.id}: {node.get_label()}")
        actor = node.get_field("actor")
        if actor:
            lines.append(f"**Actor**: {actor}")
        goal = node.get_field("goal")
        if goal:
            lines.append(f"**Goal**: {goal}")
        context = node.get_field("context")
        if context:
            lines.append(f"**Context**: {context}")
        # Validates references from live graph edges (REQ is parent of JNY)
        validates_refs: list[str] = []
        for edge in node.iter_incoming_edges():
            if edge.kind == EdgeKind.VALIDATES:
                validates_refs.append(edge.source.id)
        if validates_refs:
            lines.append(f"Validates: {', '.join(sorted(validates_refs))}")
        preamble = node.get_field("body_lines", [])
        if preamble:
            lines.append("")
            lines.extend(preamble)
        for section in node.get_field("sections", []):
            lines.append("")
            lines.append(f"## {section['name']}")
            lines.extend(section["content"].splitlines())
        lines.append("")
        lines.append(f"*End* *{node.id}*")
        return "\n".join(lines)

    def update_journey_field(self, node_id: str, field_name: str, value: str) -> MutationEntry:
        """Update a structured field on a USER_JOURNEY node and reconstruct body.

        Args:
            node_id: The journey node ID.
            field_name: One of 'actor', 'goal', 'context', 'preamble'.
            value: The new field value.

        Returns:
            MutationEntry recording the operation.

        Raises:
            KeyError: If node_id is not found.
            ValueError: If node is not a USER_JOURNEY or field_name is invalid.
        """
        if node_id not in self._index:
            raise KeyError(f"Node '{node_id}' not found")

        node = self._index[node_id]
        if node.kind != NodeKind.USER_JOURNEY:
            raise ValueError(f"Node '{node_id}' is not a user journey")

        valid_fields = ("actor", "goal", "context", "preamble")
        if field_name not in valid_fields:
            raise ValueError(f"Invalid field '{field_name}', must be one of {valid_fields}")

        old_body = node.get_field("body", "")

        if field_name == "preamble":
            old_value = "\n".join(node.get_field("body_lines", []))
            node.set_field("body_lines", value.splitlines() if value else [])
        else:
            old_value = node.get_field(field_name)
            node.set_field(field_name, value or None)

        new_body = self._reconstruct_journey_body(node)
        node.set_field("body", new_body)

        entry = MutationEntry(
            operation="update_journey_field",
            target_id=node_id,
            before_state={"field": field_name, "value": old_value, "body": old_body},
            after_state={"field": field_name, "value": value, "body": new_body},
        )
        self._mutation_log.append(entry)
        return entry

    def update_journey_section(
        self,
        node_id: str,
        section_name: str,
        new_name: str | None = None,
        new_content: str | None = None,
    ) -> MutationEntry:
        """Update a journey section by name.

        Args:
            node_id: The journey node ID.
            section_name: Name of the section to update.
            new_name: New section header name (None to keep current).
            new_content: New section content (None to keep current).

        Returns:
            MutationEntry recording the operation.

        Raises:
            KeyError: If node_id not found.
            ValueError: If not a journey or section not found.
        """
        if node_id not in self._index:
            raise KeyError(f"Node '{node_id}' not found")

        node = self._index[node_id]
        if node.kind != NodeKind.USER_JOURNEY:
            raise ValueError(f"Node '{node_id}' is not a user journey")

        sections = node.get_field("sections", [])
        target = None
        for s in sections:
            if s["name"] == section_name:
                target = s
                break
        if target is None:
            raise ValueError(f"Section '{section_name}' not found in {node_id}")

        old_body = node.get_field("body", "")
        old_name = target["name"]
        old_content = target["content"]

        if new_name is not None:
            target["name"] = new_name
        if new_content is not None:
            target["content"] = new_content

        new_body = self._reconstruct_journey_body(node)
        node.set_field("body", new_body)

        entry = MutationEntry(
            operation="update_journey_section",
            target_id=node_id,
            before_state={"name": old_name, "content": old_content, "body": old_body},
            after_state={
                "name": target["name"],
                "content": target["content"],
                "body": new_body,
            },
        )
        self._mutation_log.append(entry)
        return entry

    def add_journey_section(
        self,
        node_id: str,
        name: str,
        content: str = "",
    ) -> MutationEntry:
        """Append a new section to a journey.

        Args:
            node_id: The journey node ID.
            name: Section header name.
            content: Section content text.

        Returns:
            MutationEntry recording the operation.

        Raises:
            KeyError: If node_id not found.
            ValueError: If not a journey.
        """
        if node_id not in self._index:
            raise KeyError(f"Node '{node_id}' not found")

        node = self._index[node_id]
        if node.kind != NodeKind.USER_JOURNEY:
            raise ValueError(f"Node '{node_id}' is not a user journey")

        old_body = node.get_field("body", "")
        sections = node.get_field("sections", [])
        new_section = {"name": name, "content": content}
        sections.append(new_section)
        node.set_field("sections", sections)

        new_body = self._reconstruct_journey_body(node)
        node.set_field("body", new_body)

        entry = MutationEntry(
            operation="add_journey_section",
            target_id=node_id,
            before_state={"body": old_body},
            after_state={"name": name, "content": content, "body": new_body},
        )
        self._mutation_log.append(entry)
        return entry

    def delete_journey_section(
        self,
        node_id: str,
        section_name: str,
    ) -> MutationEntry:
        """Remove a section from a journey by name.

        Args:
            node_id: The journey node ID.
            section_name: Name of the section to delete.

        Returns:
            MutationEntry recording the operation.

        Raises:
            KeyError: If node_id not found.
            ValueError: If not a journey or section not found.
        """
        if node_id not in self._index:
            raise KeyError(f"Node '{node_id}' not found")

        node = self._index[node_id]
        if node.kind != NodeKind.USER_JOURNEY:
            raise ValueError(f"Node '{node_id}' is not a user journey")

        sections = node.get_field("sections", [])
        old_body = node.get_field("body", "")
        removed = None
        new_sections = []
        for s in sections:
            if s["name"] == section_name and removed is None:
                removed = s
            else:
                new_sections.append(s)

        if removed is None:
            raise ValueError(f"Section '{section_name}' not found in {node_id}")

        node.set_field("sections", new_sections)
        new_body = self._reconstruct_journey_body(node)
        node.set_field("body", new_body)

        entry = MutationEntry(
            operation="delete_journey_section",
            target_id=node_id,
            before_state={"name": removed["name"], "content": removed["content"], "body": old_body},
            after_state={"body": new_body},
        )
        self._mutation_log.append(entry)
        return entry

    def add_journey(
        self,
        journey_id: str,
        title: str,
        file_id: str,
    ) -> MutationEntry:
        """Create a new USER_JOURNEY node and wire it to a FILE node.

        Args:
            journey_id: The journey ID (e.g., "JNY-LOGIN-01").
            title: The journey title.
            file_id: The FILE node ID to contain this journey.

        Returns:
            MutationEntry recording the operation.

        Raises:
            ValueError: If journey_id already exists.
            KeyError: If file_id is not found.
        """
        if journey_id in self._index:
            raise ValueError(f"Node '{journey_id}' already exists")
        if file_id not in self._index:
            raise KeyError(f"File node '{file_id}' not found")

        file_node = self._index[file_id]
        if file_node.kind != NodeKind.FILE:
            raise ValueError(f"Node '{file_id}' is not a FILE node")

        node = GraphNode(
            id=journey_id,
            kind=NodeKind.USER_JOURNEY,
            label=title,
        )
        node._content = {
            "actor": None,
            "goal": None,
            "context": None,
            "body_lines": [],
            "sections": [],
            "body": f"## {journey_id}: {title}\n\n*End* *{journey_id}*",
            "parse_line": 0,
            "parse_end_line": 0,
        }

        self._index[journey_id] = node

        # Wire CONTAINS edge from file to journey
        # Compute render_order as max + 1 of existing children
        max_order = -1.0
        for edge in file_node.iter_outgoing_edges():
            if edge.kind == EdgeKind.CONTAINS:
                ro = edge.metadata.get("render_order", -1.0)
                if ro > max_order:
                    max_order = ro
        file_node.link(node, EdgeKind.CONTAINS)
        # Set render_order on the new edge
        for edge in file_node.iter_outgoing_edges():
            if edge.kind == EdgeKind.CONTAINS and edge.target is node:
                edge.metadata["render_order"] = max_order + 1.0
                break

        entry = MutationEntry(
            operation="add_journey",
            target_id=journey_id,
            before_state={},
            after_state={
                "id": journey_id,
                "title": title,
                "file_id": file_id,
            },
        )
        self._mutation_log.append(entry)
        return entry

    def delete_journey(self, node_id: str) -> MutationEntry:
        """Delete a USER_JOURNEY node.

        Removes the node from the index, disconnects all edges
        (CONTAINS from FILE, VALIDATES to REQs), and moves to
        _deleted_nodes for delta tracking.

        Args:
            node_id: The journey node ID to delete.

        Returns:
            MutationEntry recording the operation.

        Raises:
            KeyError: If node_id is not found.
            ValueError: If node is not a USER_JOURNEY.
        """
        if node_id not in self._index:
            raise KeyError(f"Node '{node_id}' not found")

        node = self._index[node_id]
        if node.kind != NodeKind.USER_JOURNEY:
            raise ValueError(f"Node '{node_id}' is not a user journey")

        was_root = node in self._roots

        # Record state before deletion
        _fn = node.file_node()
        source_path = _fn.get_field("relative_path") if _fn else None
        validates_ids = [
            e.source.id for e in node.iter_incoming_edges() if e.kind == EdgeKind.VALIDATES
        ]

        entry = MutationEntry(
            operation="delete_journey",
            target_id=node_id,
            before_state={
                "id": node_id,
                "title": node.get_label(),
                "body": node.get_field("body", ""),
                "actor": node.get_field("actor"),
                "goal": node.get_field("goal"),
                "was_root": was_root,
                "source_path": source_path,
                "validates_ids": validates_ids,
            },
            after_state={},
        )

        # Remove from index
        self._index.pop(node_id)
        self._deleted_nodes.append(node)

        # Remove from roots if present
        if was_root:
            self._roots = [r for r in self._roots if r.id != node_id]

        # Disconnect from parents (FILE node via CONTAINS)
        for parent in list(node.iter_parents()):
            parent.unlink(node)

        # Disconnect outgoing edges (VALIDATES)
        for child in list(node.iter_children()):
            node.unlink(child)

        self._mutation_log.append(entry)
        return entry

    def reconstruct_journey_body(self, node_id: str) -> MutationEntry:
        """Reconstruct a journey's body from its structured fields.

        Called after title or edge changes that affect the body text.

        Args:
            node_id: The journey node ID.

        Returns:
            MutationEntry recording the operation.

        Raises:
            KeyError: If node_id not found.
            ValueError: If not a journey.
        """
        if node_id not in self._index:
            raise KeyError(f"Node '{node_id}' not found")

        node = self._index[node_id]
        if node.kind != NodeKind.USER_JOURNEY:
            raise ValueError(f"Node '{node_id}' is not a user journey")

        old_body = node.get_field("body", "")
        new_body = self._reconstruct_journey_body(node)
        node.set_field("body", new_body)

        entry = MutationEntry(
            operation="reconstruct_journey_body",
            target_id=node_id,
            before_state={"body": old_body},
            after_state={"body": new_body},
        )
        self._mutation_log.append(entry)
        return entry


class GraphBuilder:
    """Builder for constructing TraceGraph from parsed content.

    Usage:
        builder = GraphBuilder()
        for content in parsed_contents:
            builder.add_parsed_content(content)
        graph = builder.build()

    Note on Privileged Access:
        GraphBuilder directly accesses GraphNode._content during construction.
        This is intentional - as the construction layer, GraphBuilder has
        "friend class" privileges to efficiently build node content without
        the overhead of set_field() calls. This pattern is acceptable because:
        1. GraphBuilder is the ONLY external class with this access
        2. Access occurs only during initial construction
        3. Post-construction, all access should use get_field()/set_field()
    """

    def __init__(
        self,
        repo_root: Path | None = None,
        hash_mode: str = "normalized-text",
        satellite_kinds: list[str] | None = None,
        multi_assertion_separator: str = "+",
        resolver: Any | None = None,
    ) -> None:
        """Initialize the graph builder.

        Args:
            repo_root: Repository root path.
            hash_mode: Hash calculation mode ("full-text" or "normalized-text").
            satellite_kinds: NodeKind values (e.g. ["assertion", "result"])
                that don't count as meaningful children for root/orphan
                classification. Defaults to ASSERTION and RESULT.
            multi_assertion_separator: Character joining multiple assertion
                labels in compact references (e.g. "+" for REQ-x-A+B+C).
                Empty string disables expansion.
            resolver: IdResolver instance for multi-assertion expansion.
                When provided, uses resolver.parse()/expand()/render_canonical()
                instead of string splitting.
        """
        self.repo_root = repo_root or Path.cwd()
        self.hash_mode = hash_mode
        self._multi_assertion_separator = multi_assertion_separator
        self._resolver = resolver
        if satellite_kinds is not None:
            self.satellite_kinds = frozenset(NodeKind(s) for s in satellite_kinds)
        else:
            self.satellite_kinds = _DEFAULT_SATELLITE_KINDS
        self._nodes: dict[str, GraphNode] = {}
        self._pending_links: list[tuple[str, str, EdgeKind]] = []
        # Implements: REQ-p00014-B
        self._satisfies_links: list[tuple[str, str]] = []  # (declaring_id, template_id)
        # Detection: broken references
        self._broken_references: list[BrokenReference] = []

    # Implements: REQ-d00128-D
    def register_file_node(self, file_node: GraphNode) -> None:
        """Register a FILE node in the builder's node index.

        FILE nodes are created by factory.py and registered here so they
        appear in the final graph index. They are NOT added to orphan
        candidates — FILE nodes are always parentless but not orphans.

        Args:
            file_node: A GraphNode with kind == NodeKind.FILE.
        """
        self._nodes[file_node.id] = file_node

    def _to_relative_path(self, source_id: str) -> str:
        """Convert an absolute source path to a relative path.

        Args:
            source_id: Absolute or relative file path.

        Returns:
            Path relative to repo_root, or the original path if not under repo_root.
        """
        try:
            return str(Path(source_id).relative_to(self.repo_root))
        except ValueError:
            return source_id

    # Implements: REQ-d00128-D
    def add_parsed_content(
        self, content: ParsedContent, file_node: GraphNode | None = None
    ) -> None:
        """Add parsed content to the graph.

        Args:
            content: Parsed content from a parser.
            file_node: Optional FILE node to wire CONTAINS edges from.
        """
        if content.content_type == "requirement":
            self._add_requirement(content)
            # Wire CONTAINS from FILE to REQUIREMENT (top-level)
            if file_node is not None:
                node = self._nodes.get(content.parsed_data.get("id", ""))
                if node:
                    self._wire_contains_edge(file_node, node, content)
        elif content.content_type == "journey":
            self._add_journey(content)
            if file_node is not None:
                node = self._nodes.get(content.parsed_data.get("id", ""))
                if node:
                    self._wire_contains_edge(file_node, node, content)
        elif content.content_type == "code_ref":
            self._add_code_ref(content)
            if file_node is not None:
                source_ctx = getattr(content, "source_context", None)
                source_id = source_ctx.source_id if source_ctx else "code"
                code_id = f"code:{source_id}:{content.start_line}"
                node = self._nodes.get(code_id)
                if node:
                    self._wire_contains_edge(file_node, node, content)
        elif content.content_type == "test_ref":
            self._add_test_ref(content)
            if file_node is not None:
                # Find the test node that was just created
                data = content.parsed_data
                source_ctx = getattr(content, "source_context", None)
                source_id = source_ctx.source_id if source_ctx else "test"
                func_name = data.get("function_name")
                class_name = data.get("class_name")
                if func_name:
                    rel_path = self._to_relative_path(source_id)
                    test_id = build_test_id(rel_path, func_name, class_name)
                else:
                    test_id = f"test:{source_id}:{content.start_line}"
                node = self._nodes.get(test_id)
                if node:
                    self._wire_contains_edge(file_node, node, content)
        elif content.content_type == "test_result":
            self._add_test_result(content)
            if file_node is not None:
                node = self._nodes.get(content.parsed_data.get("id", ""))
                if node:
                    self._wire_contains_edge(file_node, node, content)
        elif content.content_type == "remainder":
            self._add_remainder(content)
            # Wire CONTAINS from FILE to file-level REMAINDER
            if file_node is not None:
                data = content.parsed_data
                source_ctx = getattr(content, "source_context", None)
                source_path = source_ctx.source_id if source_ctx else ""
                remainder_id = data.get("id") or f"rem:{source_path}:{content.start_line}"
                node = self._nodes.get(remainder_id)
                if node:
                    self._wire_contains_edge(file_node, node, content)

    def _add_requirement(self, content: ParsedContent) -> None:
        """Add a requirement node and its assertions."""
        data = content.parsed_data
        req_id = data["id"]

        # Implements: REQ-d00129-A, REQ-d00129-B
        # Create requirement node
        node = GraphNode(
            id=req_id,
            kind=NodeKind.REQUIREMENT,
            label=data.get("title", ""),
        )
        # Implements: REQ-p00014-C
        # Implements: REQ-d00129-C
        # Implements: REQ-d00131-B
        node._content = {
            "level": data.get("level"),
            "status": data.get("status"),
            "hash": data.get("hash"),
            "body_text": data.get("body_text", ""),  # For hash computation
            "changelog": data.get("changelog", []),
            "stereotype": Stereotype.CONCRETE,
            "parse_line": content.start_line,
            "parse_end_line": content.end_line,
            # Store reference lists for render protocol
            "implements_refs": data.get("implements", []),
            "refines_refs": data.get("refines", []),
            "satisfies_refs": data.get("satisfies", []),
            "heading_level": data.get("heading_level", 2),
            "hash_mode": self.hash_mode,
        }
        # Extract rationale from sections for format validation (require_rationale)
        for section in data.get("sections", []):
            if section.get("heading", "").lower() == "rationale":
                node._content["rationale"] = section.get("content", "")
                break
        self._nodes[req_id] = node

        # Collect all children (assertions + sections) with line numbers,
        # then add in document order so iter_children() yields document order.
        children_with_lines: list[tuple[int, GraphNode]] = []

        # Create assertion nodes
        for assertion in data.get("assertions", []):
            assertion_id = f"{req_id}-{assertion['label']}"
            assertion_line = assertion.get("line", content.start_line)
            assertion_node = GraphNode(
                id=assertion_id,
                kind=NodeKind.ASSERTION,
                label=assertion["text"],
            )
            assertion_node._content = {
                "label": assertion["label"],
                "parse_line": assertion_line,
                "parse_end_line": None,
            }
            self._nodes[assertion_id] = assertion_node
            children_with_lines.append((assertion_line, assertion_node))

        # Create REMAINDER child nodes from non-normative sections
        # Each section (preamble, Rationale, Notes, etc.) becomes its own node
        # so that the requirement can be reconstructed from the graph.
        for idx, section in enumerate(data.get("sections", [])):
            section_id = f"{req_id}:section:{idx}"
            section_line = section.get("line", content.start_line)
            section_node = GraphNode(
                id=section_id,
                kind=NodeKind.REMAINDER,
                label=section["heading"],
            )
            section_node._content = {
                "heading": section["heading"],
                "text": section["content"],
                "order": idx,
                "parse_line": section_line,
                "parse_end_line": None,
            }
            # Preserve heading style for assertion sub-headings (* ** _)
            if "heading_style" in section:
                section_node._content["heading_style"] = section["heading_style"]
            self._nodes[section_id] = section_node
            children_with_lines.append((section_line, section_node))

        # Add children in document order (sorted by line number)
        children_with_lines.sort(key=lambda x: x[0])
        for _line, child_node in children_with_lines:
            node.link(child_node, EdgeKind.STRUCTURES)

        # Mark node dirty for any condition that would change the file on save
        parse_dirty_reasons: list[str] = []
        if data.get("has_redundant_refs"):
            parse_dirty_reasons.append("duplicate_refs")
        stored_hash = data.get("hash")
        if stored_hash:
            from elspais.commands.validate import compute_hash_for_node

            computed = compute_hash_for_node(node, self.hash_mode)
            if computed and stored_hash != computed:
                parse_dirty_reasons.append("stale_hash")
        if parse_dirty_reasons:
            node._content["parse_dirty"] = True
            node._content["parse_dirty_reasons"] = parse_dirty_reasons

        # Queue implements/refines links for later resolution
        for impl_ref in data.get("implements", []):
            self._pending_links.append((req_id, impl_ref, EdgeKind.IMPLEMENTS))

        for refine_ref in data.get("refines", []):
            self._pending_links.append((req_id, refine_ref, EdgeKind.REFINES))

        # Implements: REQ-p00014-B
        for sat_ref in data.get("satisfies", []):
            self._satisfies_links.append((req_id, sat_ref))

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
            "context": data.get("context"),
            "body": content.raw_text,
            "body_lines": data.get("body_lines", []),
            "sections": data.get("sections", []),
            "parse_line": content.start_line,
            "parse_end_line": content.end_line,
        }
        self._nodes[journey_id] = node

        # Queue validates links for later resolution
        for addr_ref in data.get("validates", []):
            self._pending_links.append((journey_id, addr_ref, EdgeKind.VALIDATES))

    def _add_code_ref(self, content: ParsedContent) -> None:
        """Add code reference nodes.

        Stores function_name and class_name from the parser's pre-scan
        context on each CODE node. This metadata enables TEST→CODE
        linking by function name matching.
        """
        data = content.parsed_data
        source_ctx = getattr(content, "source_context", None)
        source_id = source_ctx.source_id if source_ctx else "code"

        func_name = data.get("function_name")
        class_name = data.get("class_name")
        func_line = data.get("function_line", content.start_line)

        # Build a descriptive label that includes function context
        if func_name and class_name:
            label = f"Code: {class_name}.{func_name} at {source_id}:{content.start_line}"
        elif func_name:
            label = f"Code: {func_name} at {source_id}:{content.start_line}"
        else:
            label = f"Code at {source_id}:{content.start_line}"

        all_refs = [
            (ref, EdgeKind.IMPLEMENTS) for ref in data.get("implements", [])
        ] + [
            (ref, EdgeKind.VERIFIES) for ref in data.get("verifies", [])
        ]
        for ref, edge_kind in all_refs:
            code_id = f"code:{source_id}:{content.start_line}"
            if code_id not in self._nodes:
                node = GraphNode(
                    id=code_id,
                    kind=NodeKind.CODE,
                    label=label,
                )
                # Implements: REQ-d00129-C
                node.set_field("parse_line", content.start_line)
                node.set_field("parse_end_line", content.end_line)
                # Implements: REQ-d00131-F
                # Store raw comment text for render protocol
                node.set_field("raw_text", content.raw_text)
                # Store function context for TEST→CODE linking
                if func_name:
                    node.set_field("function_name", func_name)
                if class_name:
                    node.set_field("class_name", class_name)
                if func_line:
                    node.set_field("function_line", func_line)
                func_end_line = data.get("function_end_line", 0)
                if func_end_line:
                    node.set_field("function_end_line", func_end_line)
                self._nodes[code_id] = node

            self._pending_links.append((code_id, ref, edge_kind))

    def _add_test_ref(self, content: ParsedContent) -> None:
        """Add test reference nodes.

        Uses canonical test IDs when function/class context is available
        from the parser. Falls back to line-based IDs for references
        outside of functions.
        """
        data = content.parsed_data
        source_ctx = getattr(content, "source_context", None)
        source_id = source_ctx.source_id if source_ctx else "test"

        # Compute relative path for canonical IDs
        func_name = data.get("function_name")
        class_name = data.get("class_name")
        func_line = data.get("function_line", content.start_line)

        if func_name:
            # Canonical ID: test:relative_path::ClassName::function_name
            rel_path = self._to_relative_path(source_id)
            test_id = build_test_id(rel_path, func_name, class_name)
            label = f"{class_name}::{func_name}" if class_name else func_name
            source_line = func_line
        else:
            # Fallback: line-based ID for refs outside functions
            test_id = f"test:{source_id}:{content.start_line}"
            label = f"Test at {source_id}:{content.start_line}"
            source_line = content.start_line

        if test_id not in self._nodes:
            node = GraphNode(
                id=test_id,
                kind=NodeKind.TEST,
                label=label,
            )
            # Implements: REQ-d00129-C
            node.set_field("parse_line", source_line)
            node.set_field("parse_end_line", content.end_line)
            # Implements: REQ-d00131-G
            # Store raw comment text for render protocol
            node.set_field("raw_text", content.raw_text)
            expected_broken = data.get("expected_broken_count", 0)
            if expected_broken > 0:
                node.set_metric("_expected_broken_count", expected_broken)
            self._nodes[test_id] = node

        for val_ref in data.get("verifies", []):
            self._pending_links.append((test_id, val_ref, EdgeKind.VERIFIES))

    def _add_test_result(self, content: ParsedContent) -> None:
        """Add a test result node.

        Creates a RESULT node and queues a YIELDS edge to the
        referenced TEST node (via test_id). Does NOT auto-create TEST
        nodes — if test_id doesn't exist at link resolution time, it
        becomes a broken reference (same as Implements: REQ-nonexistent).

        TEST nodes are created by the TestParser scanning actual test files.
        """
        data = content.parsed_data
        result_id = data["id"]
        test_id = data.get("test_id")  # e.g., "test:path::Class::func"
        # Create a readable label from test name and class
        test_name = data.get("name", "")
        classname = data.get("classname", "")
        # Extract just the class name from dotted path
        # e.g., "TestGraphBuilder" from "tests.core.test_builder.TestGraphBuilder"
        short_class = classname.split(".")[-1] if classname else ""
        label = f"{short_class}::{test_name}" if short_class else test_name

        node = GraphNode(
            id=result_id,
            kind=NodeKind.RESULT,
            label=label,
        )
        node._content = {
            "status": data.get("status"),
            "test_id": test_id,
            "duration": data.get("duration"),
            "name": test_name,
            "classname": classname,
            "message": data.get("message"),
            "parse_line": content.start_line,
            "parse_end_line": content.end_line,
        }
        self._nodes[result_id] = node

        # Queue edge to parent TEST node if test_id is provided
        if test_id:
            # Implements: REQ-d00127-E
            self._pending_links.append((result_id, test_id, EdgeKind.YIELDS))

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
        )
        node._content = {
            "text": text,
            "parse_line": content.start_line,
            "parse_end_line": content.end_line,
        }
        self._nodes[remainder_id] = node

    # Implements: REQ-d00128-D
    def _wire_contains_edge(
        self, file_node: GraphNode, content_node: GraphNode, content: ParsedContent
    ) -> None:
        """Wire a CONTAINS edge from a FILE node to a top-level content node.

        Sets edge metadata with start_line, end_line, and render_order.
        Uses start_line as render_order so that elements are rendered in
        their original file position regardless of parser execution order.

        Args:
            file_node: The FILE parent node.
            content_node: The content node to link.
            content: The parsed content (for line range info).
        """
        edge = file_node.link(content_node, EdgeKind.CONTAINS)
        edge.metadata = {
            "start_line": content.start_line,
            "end_line": content.end_line,
            "render_order": float(content.start_line),
        }

    # Implements: REQ-d00081-D+E+G
    def _expand_multi_assertion(self, target_id: str) -> list[str]:
        """Expand multi-assertion reference using IdResolver or configured separator.

        REQ-p00001-A+B+C -> [REQ-p00001-A, REQ-p00001-B, REQ-p00001-C]

        When a resolver is available, delegates to resolver.parse()/expand()/
        render_canonical(). Falls back to string splitting when no resolver
        is set.
        """
        # Use IdResolver when available
        if self._resolver is not None:
            parsed = self._resolver.parse(target_id)
            if parsed is None or len(parsed.assertions) <= 1:
                return [target_id]
            expanded = self._resolver.expand(parsed)
            return [self._resolver.render_canonical(e) for e in expanded]

        # Fallback: string-based splitting
        sep = self._multi_assertion_separator
        if not sep or sep not in target_id:
            return [target_id]

        parts = target_id.split(sep)
        base = parts[0]
        if not parts[1:]:
            return [target_id]

        # Find the last ID separator (- or _) to split off the first label
        last_sep_idx = max(base.rfind("-"), base.rfind("_"))
        if last_sep_idx < 0:
            return [target_id]

        base_req = base[:last_sep_idx]
        id_sep = base[last_sep_idx]
        first_label = base[last_sep_idx + 1 :]

        result = [f"{base_req}{id_sep}{first_label}"]
        for label in parts[1:]:
            if label:
                result.append(f"{base_req}{id_sep}{label}")

        return result

    # Implements: REQ-p00014-B, REQ-p00014-C, REQ-d00069-H
    def _instantiate_satisfies_templates(self) -> None:
        """Clone template subtrees for each Satisfies declaration.

        Sub-pass 1: Mark template nodes as stereotype=TEMPLATE.
        Sub-pass 2: Clone subtrees with composite IDs and INSTANCE edges.
        """
        if not self._satisfies_links:
            return

        # Collect all template roots first (a template may be referenced
        # by multiple declaring reqs)
        template_roots: dict[str, list[str]] = {}  # template_id -> [declaring_ids]
        for declaring_id, template_id in self._satisfies_links:
            # Handle assertion-level satisfies: strip assertion suffix to find root
            # but keep the full ref for later use
            template_roots.setdefault(template_id, []).append(declaring_id)

        # Pre-resolve REFINES edges that target template nodes so walk()
        # can traverse the full template subtree before cloning.
        template_ids = set(template_roots.keys())
        remaining_links: list[tuple[str, str, EdgeKind]] = []
        for source_id, target_id, edge_kind in self._pending_links:
            if edge_kind == EdgeKind.REFINES and target_id in template_ids:
                source = self._nodes.get(source_id)
                target = self._nodes.get(target_id)
                if source and target:
                    target.link(source, edge_kind)
                    # Also resolve further REFINES links to these children
                    template_ids.add(source_id)
                else:
                    remaining_links.append((source_id, target_id, edge_kind))
            else:
                remaining_links.append((source_id, target_id, edge_kind))
        # Second pass for REFINES targeting newly added template members
        final_links: list[tuple[str, str, EdgeKind]] = []
        for source_id, target_id, edge_kind in remaining_links:
            if edge_kind == EdgeKind.REFINES and target_id in template_ids:
                source = self._nodes.get(source_id)
                target = self._nodes.get(target_id)
                if source and target:
                    target.link(source, edge_kind)
                    template_ids.add(source_id)
                else:
                    final_links.append((source_id, target_id, edge_kind))
            else:
                final_links.append((source_id, target_id, edge_kind))
        self._pending_links = final_links

        # Sub-pass 1: Mark templates
        for template_id in template_roots:
            template_node = self._nodes.get(template_id)
            if not template_node:
                # Broken reference — record it
                for declaring_id in template_roots[template_id]:
                    self._broken_references.append(
                        BrokenReference(
                            source_id=declaring_id,
                            target_id=template_id,
                            edge_kind=EdgeKind.SATISFIES.value,
                        )
                    )
                continue
            # Mark template root and all descendants
            for node in template_node.walk():
                node.set_field("stereotype", Stereotype.TEMPLATE)

        # Sub-pass 2: Clone & link
        for declaring_id, template_id in self._satisfies_links:
            template_node = self._nodes.get(template_id)
            declaring_node = self._nodes.get(declaring_id)
            if not template_node or not declaring_node:
                continue

            # Collect template subtree nodes (REQs and assertions only)
            template_nodes: list[GraphNode] = []
            for node in template_node.walk():
                if node.kind in (NodeKind.REQUIREMENT, NodeKind.ASSERTION):
                    template_nodes.append(node)

            # Map original IDs to cloned nodes
            clone_map: dict[str, GraphNode] = {}

            for orig in template_nodes:
                clone_id = (
                    self._resolver.build_instance_id(declaring_id, orig.id)
                    if self._resolver
                    else f"{declaring_id}{INSTANCE_SEPARATOR}{orig.id}"
                )
                clone = GraphNode(
                    id=clone_id,
                    kind=orig.kind,
                    label=orig.get_label(),
                )
                # Copy content fields and set INSTANCE stereotype
                for key, value in orig.get_all_content().items():
                    if key != "stereotype":
                        clone.set_field(key, value)
                clone.set_field("stereotype", Stereotype.INSTANCE)
                # Implements: REQ-d00129-C -- copy parse_line fields from original
                if orig.get_field("parse_line") is not None:
                    clone.set_field("parse_line", orig.get_field("parse_line"))
                if orig.get_field("parse_end_line") is not None:
                    clone.set_field("parse_end_line", orig.get_field("parse_end_line"))

                self._nodes[clone_id] = clone
                clone_map[orig.id] = clone

                # INSTANCE edge from clone to original
                clone.link(orig, EdgeKind.INSTANCE)

            # Recreate internal edges in cloned subtree
            for orig in template_nodes:
                clone = clone_map.get(orig.id)
                if not clone:
                    continue
                for edge in orig.iter_outgoing_edges():
                    target_clone = clone_map.get(edge.target.id)
                    if target_clone:
                        clone.link(target_clone, edge.kind)

            # Recreate parent-child relationships for assertions
            for orig in template_nodes:
                if orig.kind == NodeKind.ASSERTION:
                    clone = clone_map[orig.id]
                    for parent in orig.iter_parents():
                        parent_clone = clone_map.get(parent.id)
                        if parent_clone:
                            parent_clone.link(clone, EdgeKind.STRUCTURES)

            # SATISFIES edge from declaring REQ to cloned root
            cloned_root = clone_map.get(template_id)
            if cloned_root:
                declaring_node.link(cloned_root, EdgeKind.SATISFIES)

            # Implements: REQ-d00128-J -- DEFINES edges from declaring FILE to INSTANCE nodes
            declaring_file = declaring_node.file_node()
            if declaring_file:
                for clone in clone_map.values():
                    declaring_file.link(clone, EdgeKind.DEFINES)

    # Implements: REQ-p00014-D
    def _attribute_template_refs(
        self,
        links: list[tuple[str, str, EdgeKind]],
    ) -> list[tuple[str, str, EdgeKind]]:
        """Redirect Implements: refs targeting TEMPLATE nodes to instance clones.

        For each link targeting a TEMPLATE node:
        1. Find the template root (walk up REFINES edges)
        2. Find sibling Implements: refs in the same source file targeting CONCRETE nodes
        3. Walk each concrete target's ancestors to find a SATISFIES declaration
           matching the template root
        4. First match wins — redirect to instance clone ID

        Returns:
            Updated link list with template refs redirected.
        """
        if not self._satisfies_links:
            return links

        # Implements: REQ-d00129-D -- Build file -> source_ids index from nodes
        file_to_sources: dict[str, set[str]] = {}
        for node_id, node in self._nodes.items():
            fn = node.file_node()
            if fn:
                rp = fn.get_field("relative_path") or ""
                if rp:
                    file_to_sources.setdefault(rp, set()).add(node_id)

        # Build source_id -> file index from link source nodes
        source_file_map: dict[str, str] = {}
        for source_id, _, _ in links:
            node = self._nodes.get(source_id)
            if node:
                fn = node.file_node()
                if fn:
                    rp = fn.get_field("relative_path") or ""
                    if rp:
                        source_file_map[source_id] = rp

        # Group links by source file
        file_links: dict[str, list[int]] = {}  # file -> list of indices
        for idx, (source_id, _, _) in enumerate(links):
            file_path = source_file_map.get(source_id)
            if file_path:
                file_links.setdefault(file_path, []).append(idx)

        # Find template root for a given node (walk up REFINES edges)
        def find_template_root(node: GraphNode) -> GraphNode:
            current = node
            # Walk up through parents connected by REFINES
            while True:
                found_parent = False
                for edge in current.iter_incoming_edges():
                    if edge.kind == EdgeKind.REFINES:
                        current = edge.source
                        found_parent = True
                        break
                if not found_parent:
                    break
            return current

        result = list(links)

        for _file_path, indices in file_links.items():
            # Separate template and concrete targets in this file
            template_indices: list[int] = []
            concrete_targets: list[str] = []

            for idx in indices:
                _, target_id, _ = result[idx]
                target = self._nodes.get(target_id)
                if target and target.get_field("stereotype") == Stereotype.TEMPLATE:
                    template_indices.append(idx)
                elif target and target.get_field("stereotype") != Stereotype.TEMPLATE:
                    concrete_targets.append(target_id)

            if not template_indices:
                continue

            for idx in template_indices:
                source_id, target_id, edge_kind = result[idx]
                target = self._nodes.get(target_id)
                if not target:
                    continue

                # Find which template root this target belongs to
                # For assertions, find parent REQ first, then walk up
                if target.kind == NodeKind.ASSERTION:
                    parent_reqs = [
                        p for p in target.iter_parents() if p.kind == NodeKind.REQUIREMENT
                    ]
                    template_root = find_template_root(parent_reqs[0]) if parent_reqs else target
                else:
                    template_root = find_template_root(target)

                # Find attribution through concrete siblings
                attributed = False
                for concrete_id in concrete_targets:
                    concrete = self._nodes.get(concrete_id)
                    if not concrete:
                        continue
                    # Walk up concrete target and its ancestors to find SATISFIES
                    # matching the template root
                    for ancestor in _chain_self_and_ancestors(concrete):
                        for edge in ancestor.iter_outgoing_edges():
                            if edge.kind == EdgeKind.SATISFIES:
                                # Check if this SATISFIES clone's INSTANCE edge
                                # points to our template root
                                clone = edge.target
                                for inst_edge in clone.iter_outgoing_edges():
                                    if (
                                        inst_edge.kind == EdgeKind.INSTANCE
                                        and inst_edge.target.id == template_root.id
                                    ):
                                        # Found it! Redirect to instance ID
                                        instance_id = (
                                            self._resolver.build_instance_id(ancestor.id, target_id)
                                            if self._resolver
                                            else f"{ancestor.id}{INSTANCE_SEPARATOR}{target_id}"
                                        )
                                        if self._nodes.get(instance_id):
                                            result[idx] = (source_id, instance_id, edge_kind)
                                            attributed = True
                                            break
                                if attributed:
                                    break
                        if attributed:
                            break
                    if attributed:
                        break

                if not attributed:
                    # No attribution found — record as broken reference
                    self._broken_references.append(
                        BrokenReference(
                            source_id=source_id,
                            target_id=target_id,
                            edge_kind=edge_kind.value,
                        )
                    )
                    # Remove the link so it doesn't create an edge to the template
                    result[idx] = (source_id, f"__unattributed__{target_id}", edge_kind)

        return result

    def build(self) -> TraceGraph:
        """Build the final TraceGraph.

        Resolves all pending links and identifies root nodes.
        Also detects orphaned nodes and broken references.

        Returns:
            Complete TraceGraph with detection data populated.
        """
        # Phase 2: Instantiate templates before resolving links
        self._instantiate_satisfies_templates()

        # Expand multi-assertion references before resolving
        expanded_links: list[tuple[str, str, EdgeKind]] = []
        for source_id, target_id, edge_kind in self._pending_links:
            for resolved_target in self._expand_multi_assertion(target_id):
                expanded_links.append((source_id, resolved_target, edge_kind))

        # Implements: REQ-p00014-D
        # Phase 3: File-based attribution for template references
        expanded_links = self._attribute_template_refs(expanded_links)

        # Resolve pending links
        for source_id, target_id, edge_kind in expanded_links:
            source = self._nodes.get(source_id)
            target = self._nodes.get(target_id)

            if source and target:
                # If target is an assertion, link from its parent requirement
                # with assertion_targets set, so the child appears under the
                # parent REQ (not the assertion node) with assertion badges
                if target.kind == NodeKind.ASSERTION:
                    # Find the parent requirement of this assertion
                    parent_reqs = [
                        p for p in target.iter_parents() if p.kind == NodeKind.REQUIREMENT
                    ]
                    if parent_reqs:
                        parent_req = parent_reqs[0]
                        assertion_label = target.get_field("label", "")
                        edge = parent_req.link(
                            source,
                            edge_kind,
                            assertion_targets=[assertion_label] if assertion_label else None,
                        )
                    else:
                        # Fallback: link directly if no parent found
                        edge = target.link(source, edge_kind)
                else:
                    # Link target as parent of source (implements relationship)
                    edge = target.link(source, edge_kind)

                # Store implementation line range on IMPLEMENTS/VERIFIES edges
                if edge_kind in (EdgeKind.IMPLEMENTS, EdgeKind.VERIFIES):
                    impl_start = (
                        source.get_field("function_line")
                        or source.get_field("parse_line")
                    )
                    impl_end = (
                        source.get_field("function_end_line")
                        or source.get_field("parse_end_line")
                        or 0
                    )
                    if impl_start:
                        edge.metadata["impl_start_line"] = impl_start
                    if impl_end:
                        edge.metadata["impl_end_line"] = impl_end
            elif source and not target:
                # Broken reference: target doesn't exist
                self._broken_references.append(
                    BrokenReference(
                        source_id=source_id,
                        target_id=target_id,
                        edge_kind=edge_kind.value,
                    )
                )

        # Populate _expected_broken_targets from nodes with the marker
        for br in self._broken_references:
            source = self._nodes.get(br.source_id)
            if source and source.get_metric("_expected_broken_count"):
                remaining = source.get_metric("_expected_broken_count")
                targets = source.get_metric("_expected_broken_targets") or []
                if len(targets) < remaining:
                    targets.append(br.target_id)
                    source.set_metric("_expected_broken_targets", targets)

        # Implements: REQ-d00071-A, REQ-d00071-B
        # Compute orphan candidates from graph structure instead of tracking
        # incrementally. A content node (not FILE, REMAINDER, ASSERTION) is an
        # orphan candidate if it has no content-level parent edges — i.e. no
        # incoming IMPLEMENTS, REFINES, VERIFIES, VALIDATES, or YIELDS edges.
        # CONTAINS edges (from FILE nodes) don't count as content-level links.
        # Roots: parentless REQUIREMENTs (always), or other parentless nodes
        #        with at least one meaningful (non-satellite) child.
        # Orphans: parentless non-REQUIREMENT nodes without meaningful children.
        _non_candidate_kinds = {NodeKind.FILE, NodeKind.REMAINDER, NodeKind.ASSERTION}
        _content_edge_kinds = {
            EdgeKind.IMPLEMENTS,
            EdgeKind.REFINES,
            EdgeKind.VERIFIES,
            EdgeKind.VALIDATES,
            EdgeKind.YIELDS,
        }
        roots = []
        root_ids = set()
        orphaned_ids: set[str] = set()
        for node_id, node in self._nodes.items():
            if node.kind in _non_candidate_kinds:
                continue
            # Check if node has any content-level parent edge
            has_content_parent = any(
                edge.kind in _content_edge_kinds for edge in node.iter_incoming_edges()
            )
            if has_content_parent:
                continue
            # Parentless (content-wise) node — classify as root or orphan
            if node.kind == NodeKind.REQUIREMENT or any(
                c.kind not in self.satellite_kinds for c in node.iter_children()
            ):
                roots.append(node)
                root_ids.add(node_id)
            else:
                orphaned_ids.add(node_id)

        graph = TraceGraph(
            repo_root=self.repo_root,
            hash_mode=self.hash_mode,
            satellite_kinds=self.satellite_kinds,
        )
        graph._roots = roots
        graph._index = dict(self._nodes)
        graph._orphaned_ids = orphaned_ids
        graph._broken_references = list(self._broken_references)
        return graph
