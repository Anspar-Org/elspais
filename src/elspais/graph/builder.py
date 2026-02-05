# Implements: REQ-o00050-A, REQ-o00050-B, REQ-o00050-C, REQ-o00050-D, REQ-o00050-E
# Implements: REQ-d00053-A, REQ-d00053-B
"""Graph Builder - Constructs TraceGraph from parsed content.

This module provides the builder pattern for constructing a complete
traceability graph from parsed content.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from elspais.graph.GraphNode import GraphNode, NodeKind, SourceLocation
from elspais.graph.mutations import BrokenReference, MutationEntry, MutationLog
from elspais.graph.parsers import ParsedContent
from elspais.graph.parsers.requirement import RequirementParser
from elspais.graph.relations import EdgeKind


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
        elif op == "fix_broken_reference":
            self._undo_fix_broken_reference(entry)
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
                # Remove actual edge
                source = self._index.get(source_id)
                target = self._index.get(target_id)
                if source and target:
                    target.remove_child(source)

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
                    new_target.remove_child(source)
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
                parent.remove_child(node)
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
                    parent.add_child(node)
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
            parent.remove_child(node)

        # Mark children as orphans (except assertions which go with the req)
        for child in list(node.iter_children()):
            if child.kind == NodeKind.ASSERTION:
                # Delete assertion children too
                if child.id in self._index:
                    self._index.pop(child.id)
                    self._deleted_nodes.append(child)
            else:
                # Non-assertion children become orphans
                node.remove_child(child)
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

    def _recompute_requirement_hash(self, req_node: GraphNode) -> str:
        """Recompute hash for a requirement.

        Supports two modes (configurable via [validation].hash_mode):
        - full-text: hash every line between header and footer (body_text)
        - normalized-text: hash normalized assertion text only

        Args:
            req_node: The requirement node to recompute hash for.

        Returns:
            The new hash value.
        """
        from elspais.utilities.hasher import calculate_hash, compute_normalized_hash

        if self.hash_mode == "normalized-text":
            # Collect assertions in physical order from child nodes
            assertions = []
            for child in req_node.iter_children():
                if child.kind == NodeKind.ASSERTION:
                    label = child.get_field("label", "")
                    text = child.get_label() or ""
                    if label and text:
                        assertions.append((label, text))
            new_hash = compute_normalized_hash(assertions)
        else:
            # full-text mode: hash body_text (per original spec)
            body_text = req_node.get_field("body_text", "")
            new_hash = calculate_hash(body_text)

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
        parent.add_child(assertion_node)

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
        parent.remove_child(node)
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
    ) -> MutationEntry:
        """Add a new edge (reference).

        Creates a relationship from source to target. If target doesn't exist,
        adds to _broken_references instead of creating an edge.

        Args:
            source_id: The child/source node ID.
            target_id: The parent/target node ID.
            edge_kind: The type of relationship.
            assertion_targets: Optional assertion labels targeted.

        Returns:
            MutationEntry recording the operation.

        Raises:
            KeyError: If source_id is not found.
        """
        if source_id not in self._index:
            raise KeyError(f"Source node '{source_id}' not found")

        source = self._index[source_id]
        target = self._index.get(target_id)

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

        # Remove the edge (parent removes child)
        target.remove_child(source)

        # Check if source is now orphaned (no parents, not a root)
        if source.parent_count() == 0 and not self.has_root(source_id):
            # Only requirements can be orphaned
            if source.kind == NodeKind.REQUIREMENT:
                self._orphaned_ids.add(source_id)
                entry.after_state["became_orphan"] = True

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

    def __init__(self, repo_root: Path | None = None, hash_mode: str = "normalized-text") -> None:
        """Initialize the graph builder.

        Args:
            repo_root: Repository root path.
            hash_mode: Hash calculation mode ("full-text" or "normalized-text").
        """
        self.repo_root = repo_root or Path.cwd()
        self.hash_mode = hash_mode
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
            "body_text": data.get("body_text", ""),  # For hash computation
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
                    source=SourceLocation(
                        path=source_id,
                        line=content.start_line,
                        end_line=content.end_line,
                    ),
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
                    source=SourceLocation(
                        path=source_id,
                        line=content.start_line,
                        end_line=content.end_line,
                    ),
                )
                self._nodes[test_id] = node

            self._pending_links.append((test_id, val_ref, EdgeKind.VALIDATES))

    def _add_test_result(self, content: ParsedContent) -> None:
        """Add a test result node.

        If the result has a test_id, auto-creates a TEST node if needed.
        If validates list is present (extracted from test name), creates
        VALIDATES edges from TEST to requirements/assertions.
        """
        data = content.parsed_data
        result_id = data["id"]
        test_id = data.get("test_id")  # e.g., "test:classname::test_name"
        validates = data.get("validates", [])  # REQs extracted from test name
        source_ctx = getattr(content, "source_context", None)
        source_path = source_ctx.source_id if source_ctx else ""

        # Create a readable label from test name and class
        test_name = data.get("name", "")
        classname = data.get("classname", "")
        # Extract just the class name from dotted path
        # e.g., "TestGraphBuilder" from "tests.core.test_builder.TestGraphBuilder"
        short_class = classname.split(".")[-1] if classname else ""
        label = f"{short_class}::{test_name}" if short_class else test_name

        # Auto-create TEST node if test_id provided and doesn't exist yet
        if test_id and test_id not in self._nodes:
            test_node = GraphNode(
                id=test_id,
                kind=NodeKind.TEST,
                label=label,
                source=SourceLocation(
                    path=source_path,
                    line=content.start_line,
                    end_line=content.end_line,
                ),
            )
            test_node._content = {
                "classname": classname,
                "name": test_name,
                "from_results": True,  # Indicates this TEST was auto-created
            }
            self._nodes[test_id] = test_node

            # Queue VALIDATES edges from TEST → REQ/Assertion based on validates list
            for req_id in validates:
                self._pending_links.append((test_id, req_id, EdgeKind.VALIDATES))

        node = GraphNode(
            id=result_id,
            kind=NodeKind.TEST_RESULT,
            label=label,
            source=SourceLocation(
                path=source_path,
                line=content.start_line,
                end_line=content.end_line,
            ),
        )
        node._content = {
            "status": data.get("status"),
            "test_id": test_id,
            "duration": data.get("duration"),
            "name": test_name,
            "classname": classname,
            "message": data.get("message"),
        }
        self._nodes[result_id] = node

        # Queue edge to parent TEST node if test_id is provided
        if test_id:
            self._pending_links.append((result_id, test_id, EdgeKind.CONTAINS))

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
                        p for p in target.iter_parents() if p.kind == NodeKind.REQUIREMENT
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
            node
            for node in self._nodes.values()
            if node.is_root and node.kind == NodeKind.REQUIREMENT
        ]

        # Also include journeys as roots
        roots.extend(node for node in self._nodes.values() if node.kind == NodeKind.USER_JOURNEY)

        # Root nodes are not orphans - they're intentionally parentless
        root_ids = {r.id for r in roots}

        # Final orphan set: candidates that aren't roots
        orphaned_ids = self._orphan_candidates - root_ids

        graph = TraceGraph(repo_root=self.repo_root, hash_mode=self.hash_mode)
        graph._roots = roots
        graph._index = dict(self._nodes)
        graph._orphaned_ids = orphaned_ids
        graph._broken_references = list(self._broken_references)
        return graph
