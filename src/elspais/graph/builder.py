# Implements: REQ-p00050-A, REQ-p00050-D, REQ-p00061-B, REQ-p00061-C
# Implements: REQ-o00050-A, REQ-o00050-B, REQ-o00050-C, REQ-o00050-D, REQ-o00050-E
# Implements: REQ-d00071-A, REQ-d00071-B, REQ-d00071-C, REQ-d00071-D
# Implements: REQ-d00216-A+B+C+D+E+F
"""Graph Builder - Constructs TraceGraph from parsed content.

This module provides the builder pattern for constructing a complete
traceability graph from parsed content.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from elspais.graph.comment_store import update_anchors_on_rename
from elspais.graph.comments import CommentIndex, CommentThread
from elspais.graph.edge_sets import (
    TRACEABILITY_EDGE_KINDS as _TRACEABILITY_EDGE_KINDS,
)
from elspais.graph.GraphNode import (
    FileType,
    GraphNode,
    NodeKind,
    make_code_id,
    make_definition_id,
    make_file_id,
    make_remainder_id,
    make_step_id,
    make_test_id,
    parse_structural_id,
)
from elspais.graph.mutations import MutationEntry, MutationLog
from elspais.graph.parsers import ParsedContent
from elspais.graph.reference_faults import (
    FaultClass,
    IdentifierFormFinding,
    ReferenceFault,
    StyleFinding,
    UndeclaredRelationship,
    reader_refused,
)
from elspais.graph.relations import EdgeKind, Stereotype
from elspais.graph.render import format_definition_block, render_end_marker
from elspais.graph.terms import TermDictionary, TermEntry, compute_definition_hash
from elspais.utilities.patterns import INSTANCE_SEPARATOR, GrammarUnavailable
from elspais.utilities.test_identity import build_test_id


def _canonicalize_list_spacing(text: str) -> str:
    """Insert blank lines before list items that follow non-blank, non-list lines.

    Pandoc requires a blank line before the first list item.
    Returns the text with canonical spacing (unchanged if already correct).
    """
    lines = text.split("\n")
    result: list[str] = []
    for i, line in enumerate(lines):
        if (
            line.lstrip().startswith("- ")
            and i > 0
            and result
            and result[-1].strip()
            and not result[-1].lstrip().startswith("- ")
        ):
            result.append("")
        result.append(line)
    return "\n".join(result)


# Implements: REQ-d00071-C
# Default satellite kinds: children of these types don't count as "meaningful"
# for determining root vs orphan status. Configurable via [graph].satellite_kinds.
_DEFAULT_SATELLITE_KINDS = frozenset({NodeKind.ASSERTION, NodeKind.RESULT})


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

    # The identifier grammar of the repository this graph holds, carried
    # down from the builder that produced it. Read through the ``resolver``
    # property, never directly: spelling an identifier without it means
    # spelling it under some other repository's grammar.
    _resolver: Any | None = field(default=None, repr=False)

    # The namespace of the repository this graph holds, carried down from
    # the builder that produced it. Read through the ``namespace``
    # property, never directly: a graph assembled by hand has neither this
    # nor a resolver, and must refuse rather than answer emptily.
    _namespace: str = field(default="", repr=False)

    @property
    def namespace(self) -> str:
        """The namespace this repository's identifiers are written in.

        Preferred from the configured resolver, which is the one authority
        for the identifier grammar, and otherwise the namespace the builder
        was given — a builder cannot be constructed without one, so a graph
        it produced can always answer.

        Raises:
            ValueError: The graph was assembled without either, and so
                cannot say which repository it holds. There is no empty
                answer: a caller asking this is about to identify a node,
                and an id naming no repository resolves against nothing.
        """
        namespace = (
            getattr(getattr(self._resolver, "config", None), "namespace", "") or self._namespace
        )
        if not namespace:
            raise ValueError(
                "This graph names no namespace and cannot say which repository "
                "it holds; a node identified by source location needs one."
            )
        return namespace

    @property
    def resolver(self) -> Any:
        """The identifier grammar this repository's identifiers are written in.

        Raises:
            GrammarUnavailable: The graph was assembled without one. A caller
                asking for it is about to spell an identifier, and there is no
                neutral spelling: the boundary characters are configuration,
                so guessing them writes a reference that reads back as a
                different requirement, or as none.
        """
        if self._resolver is None:
            raise GrammarUnavailable(
                "This graph carries no identifier grammar, so it cannot spell "
                "an identifier: the characters bounding a component from its "
                "assertion labels are configuration, not constants."
            )
        return self._resolver

    # Internal storage (prefixed) - excluded from constructor
    _roots: list[GraphNode] = field(default_factory=list, init=False)
    _index: dict[str, GraphNode] = field(default_factory=dict, init=False, repr=False)

    # Detection: orphans and broken references (populated at build time)
    _orphaned_ids: set[str] = field(default_factory=set, init=False)
    _broken_references: list[ReferenceFault] = field(default_factory=list, init=False)
    # Implements: REQ-d00272-G
    # Keyword-form findings (non-canonical case/spacing/emphasis) -- never
    # cost the edge their keyword introduces, so kept apart from
    # _broken_references rather than joining a bucket that counts
    # references that failed to bind.
    _style_findings: list[StyleFinding] = field(default_factory=list, init=False, repr=False)
    # Implements: REQ-d00272-O
    # Identifiers opening a comment no keyword introduces -- an intended
    # relationship that was never declared, and so not a failed reference.
    _undeclared_relationships: list[UndeclaredRelationship] = field(
        default_factory=list, init=False, repr=False
    )
    # Implements: REQ-d00272-N
    # References the configuration admits but did not spell canonically --
    # each produced its relationship, so kept apart from _broken_references.
    _identifier_form_findings: list[IdentifierFormFinding] = field(
        default_factory=list, init=False, repr=False
    )
    # Detection: duplicate REQ IDs across files (populated at build time).
    # Maps canonical REQ ID -> ordered list of source paths defining it.
    _duplicate_req_ids: dict[str, list[str]] = field(default_factory=dict, init=False, repr=False)

    # Implements: REQ-d00222-A
    _terms: TermDictionary = field(default_factory=TermDictionary, init=False)

    # Implements: REQ-d00230-A
    _comment_index: CommentIndex = field(default_factory=CommentIndex, init=False)

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

    # Implements: REQ-p00014-R
    def _resolution_class(self, target_id: str) -> FaultClass:
        """Which class an item that read but did not resolve reached.

        A label that names no assertion of a requirement that exists is a
        different finding from a requirement nothing holds: the first is
        always the author's, the second may be a sibling that has not
        authored it yet.  Reporting the later class than the reference
        reached would describe a defect the author does not have.
        """
        if self._resolver is not None:
            split = self._resolver.split_assertion_ref(target_id)
            if split is not None and self.find_by_id(split[0]) is not None:
                return FaultClass.UNKNOWN_ASSERTION
        return FaultClass.UNKNOWN_REQUIREMENT

    def make_assertion_id(self, req_id: str, label: str) -> str:
        """Compose an assertion node ID using the configured separator.

        Internal IDs are spelled in the same canonical form a reader would
        write (e.g. ``EVS-PRD-foo/A`` when ``separator="/"``), so a node's
        id and a citation of it are the same string.
        """
        return self.resolver.make_assertion_id(req_id, label)

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

    def broken_references(self) -> list[ReferenceFault]:
        """Get all broken references detected during build.

        Broken references occur when a node references a target ID
        that doesn't exist in the graph.

        Returns:
            List of ReferenceFault instances.
        """
        return list(self._broken_references)

    def has_broken_references(self) -> bool:
        """Check if the graph has broken references."""
        return len(self._broken_references) > 0

    # Implements: REQ-d00272-G
    def style_findings(self) -> list[StyleFinding]:
        """Get all keyword-form style findings detected during build."""
        return list(self._style_findings)

    # Implements: REQ-d00272-O
    def undeclared_relationships(self) -> list[UndeclaredRelationship]:
        """Get every comment that cites an identifier without declaring one."""
        return list(self._undeclared_relationships)

    # Implements: REQ-d00272-N
    def identifier_form_findings(self) -> list[IdentifierFormFinding]:
        """Get every reference spelled in a non-canonical admitted form."""
        return list(self._identifier_form_findings)

    def duplicate_req_ids(self) -> dict[str, list[str]]:
        """Return cross-file duplicate REQ IDs detected at build time.

        Maps the canonical REQ ID (the first occurrence's real ID) to the
        ordered list of source file paths that defined it. Subsequent
        occurrences are present in the graph under synthetic IDs of the form
        ``<canonical>#<file-stem>`` and carry ``is_duplicate=True`` in their
        content fields.
        """
        return {k: list(v) for k, v in self._duplicate_req_ids.items()}

    def has_duplicate_req_ids(self) -> bool:
        """Check if the graph has any cross-file duplicate REQ IDs."""
        return len(self._duplicate_req_ids) > 0

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
    def terms(self) -> TermDictionary:
        """Read-only access to the term dictionary."""
        return self._terms

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
        elif op == "set_stereotype":
            self._undo_set_stereotype(entry)
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
        elif op == "add_file_node":
            self._undo_add_file_node(entry)
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
        elif op == "update_remainder":
            self._undo_update_remainder(entry)
        elif op == "add_remainder":
            self._undo_add_remainder(entry)
        elif op == "delete_remainder":
            self._undo_delete_remainder(entry)
        elif op == "add_changelog_entry":
            self._undo_add_changelog_entry(entry)
        # Unknown operations are silently ignored (forward compatibility)

    def _retarget_broken_refs(self, old_id: str, new_id: str) -> None:
        """Rewrite broken references (and their leftovers) after a rename.

        Handles the renamed node as broken-ref source, as exact target, and
        as the base of assertion-suffixed targets (``old_id-<label>``, the
        form partial multi-assertion leftovers take). All ReferenceFault
        fields (diagnostic, presumed_foreign) are preserved. When a target
        changes, the source node's stored leftover field is kept in sync so
        the render agrees with the broken-reference report (REQ-d00132-G).
        """
        suffix_prefix = old_id + "-"
        for i, br in enumerate(self._broken_references):
            new_source = new_id if br.source_id == old_id else br.source_id
            if br.target_id == old_id:
                new_target = new_id
            elif br.target_id.startswith(suffix_prefix):
                new_target = new_id + br.target_id[len(old_id) :]
            else:
                new_target = br.target_id
            if (new_source, new_target) == (br.source_id, br.target_id):
                continue
            self._broken_references[i] = replace(br, source_id=new_source, target_id=new_target)
            if new_target != br.target_id:
                source_node = self._index.get(new_source)
                ref_kind = EdgeKind(br.edge_kind)
                self._remove_leftover_ref(source_node, ref_kind, br.target_id)
                self._add_leftover_ref(source_node, ref_kind, new_target)

    def _undo_rename_node(self, entry: MutationEntry) -> None:
        """Undo a node rename operation."""
        old_id = entry.before_state.get("id")
        new_id = entry.after_state.get("id")
        if old_id and new_id and new_id in self._index:
            node = self._index.pop(new_id)
            node.set_id(old_id)
            self._index[old_id] = node

        # Reverse assertion/step child-id cascade recorded during rename_node.
        for old_child_id, new_child_id in entry.after_state.get("child_ids_renamed", []):
            child = self._index.pop(new_child_id, None)
            if child is not None:
                child.set_id(old_child_id)
                self._index[old_child_id] = child

        # Reverse the broken-reference/leftover retargeting done by rename_node.
        if old_id and new_id:
            self._retarget_broken_refs(new_id, old_id)
        self._restore_journey_bodies(entry)

    def _undo_update_title(self, entry: MutationEntry) -> None:
        """Undo a title update operation."""
        node_id = entry.target_id
        old_title = entry.before_state.get("title")
        if node_id in self._index and old_title is not None:
            self._index[node_id].set_label(old_title)
            self._restore_journey_bodies(entry)

    def _undo_change_status(self, entry: MutationEntry) -> None:
        """Undo a status change operation."""
        node_id = entry.target_id
        old_status = entry.before_state.get("status")
        if node_id in self._index and old_status is not None:
            self._index[node_id].set_field("status", old_status)

    def _undo_set_stereotype(self, entry: MutationEntry) -> None:
        """Undo a set_stereotype operation (node + assertion children)."""
        node = self._index.get(entry.target_id)
        old = entry.before_state.get("stereotype")
        if node is not None and old is not None:
            node.set_field("stereotype", Stereotype(old))
        for child_id, child_old in entry.before_state.get("assertion_stereotypes", {}).items():
            child = self._index.get(child_id)
            if child is not None:
                child.set_field("stereotype", Stereotype(child_old))

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

    @staticmethod
    def _restore_edge_attrs(edge: Any, metadata: dict, targets: list[str]) -> None:
        """Reapply captured metadata and assertion targets to a replayed edge.

        assertion_targets is a first-class Edge attribute, not metadata.
        Dropping it silently downgrades assertion-scoped references to blanket
        whole-requirement ones. Implements: REQ-o00062-P
        """
        if edge is None:
            return
        if metadata:
            edge.metadata.update(metadata)
        if targets:
            edge.assertion_targets.clear()
            edge.assertion_targets.extend(targets)

    def _undo_delete_requirement(self, entry: MutationEntry) -> None:
        """Undo a delete requirement, restoring the node AND its attachment.

        Restoring index membership alone leaves the requirement orphaned:
        with no CONTAINS edge from its FILE it renders into no file, so a
        "successful" undo would still lose it on the next save. Both edge
        directions, assertion children, orphan bookkeeping, and root
        membership are restored too. Implements: REQ-o00062-P
        """
        node_id = entry.target_id
        node = None
        for i, deleted in enumerate(self._deleted_nodes):
            if deleted.id == node_id:
                node = self._deleted_nodes.pop(i)
                self._index[node_id] = node
                break
        if node is None:
            return

        # Restore assertion children popped alongside the node
        for child_id in entry.before_state.get("assertion_child_ids", []):
            for i, deleted in enumerate(self._deleted_nodes):
                if deleted.id == child_id:
                    self._index[child_id] = self._deleted_nodes.pop(i)
                    break

        # Replay both edge directions with their metadata and targets
        for parent_id, kind, metadata, targets in entry.before_state.get("parent_edges", []):
            parent = self._index.get(parent_id)
            if parent is not None:
                self._restore_edge_attrs(parent.link(node, EdgeKind(kind)), metadata, targets)
        for child_id, kind, metadata, targets in entry.before_state.get("child_edges", []):
            child = self._index.get(child_id)
            if child is not None:
                self._restore_edge_attrs(node.link(child, EdgeKind(kind)), metadata, targets)

        # Children orphaned by the deletion are attached again
        for child_id in entry.before_state.get("orphaned_child_ids", []):
            self._orphaned_ids.discard(child_id)

        # Restore as root if it was one
        if entry.before_state.get("was_root") and not any(r.id == node_id for r in self._roots):
            self._roots.append(node)

        # Restore broken references retired with the node (REQ-d00132-G)
        for br_dict in entry.before_state.get("purged_broken_refs", []):
            self._broken_references.append(ReferenceFault(**br_dict))

    # Stored ref fields hold UNRESOLVED leftovers only (REQ-d00132-F/G):
    # build() strips refs that became edges, and the mutation paths below
    # keep the leftovers in sync so the render (derived-from-edges UNION
    # leftovers) always reflects the graph.
    _LEFTOVER_REF_FIELDS = {
        EdgeKind.IMPLEMENTS: "implements_refs",
        EdgeKind.REFINES: "refines_refs",
    }

    def _add_leftover_ref(self, node: GraphNode | None, edge_kind: EdgeKind, ref: str) -> None:
        """Record an unresolved reference so it keeps rendering.

        Implements: REQ-d00132-G
        """
        field = self._LEFTOVER_REF_FIELDS.get(edge_kind)
        if node is None or field is None or node.kind != NodeKind.REQUIREMENT:
            return
        stored = list(node.get_field(field) or [])
        if ref not in stored:
            stored.append(ref)
            node.set_field(field, stored)

    def _remove_leftover_ref(self, node: GraphNode | None, edge_kind: EdgeKind, ref: str) -> None:
        """Drop an unresolved reference that has been resolved or undone.

        Implements: REQ-d00132-G
        """
        field = self._LEFTOVER_REF_FIELDS.get(edge_kind)
        if node is None or field is None or node.kind != NodeKind.REQUIREMENT:
            return
        stored = list(node.get_field(field) or [])
        if ref in stored:
            stored.remove(ref)
            node.set_field(field, stored)

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
                kind_val = entry.after_state.get("edge_kind", "")
                if kind_val:
                    self._remove_leftover_ref(
                        self._index.get(source_id), EdgeKind(kind_val), target_id
                    )
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
                    self._restore_journey_bodies(entry)

            # Restore orphan status
            if was_orphan and source_id in self._index:
                self._orphaned_ids.add(source_id)

    def _undo_delete_edge(self, entry: MutationEntry) -> None:
        """Undo a delete edge operation (restore the edge)."""
        source_id = entry.before_state.get("source_id")
        target_id = entry.before_state.get("target_id")
        edge_kind_str = entry.before_state.get("edge_kind")
        assertion_targets = entry.before_state.get("assertion_targets", [])
        old_metadata = entry.before_state.get("metadata", {})
        became_orphan = entry.after_state.get("became_orphan", False)

        if source_id and target_id and edge_kind_str:
            source = self._index.get(source_id)
            target = self._index.get(target_id)
            if source and target:
                edge_kind = EdgeKind(edge_kind_str)
                edge = target.link(source, edge_kind, assertion_targets or None)
                edge.metadata.update(old_metadata)
                self._restore_journey_bodies(entry)

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
                self._restore_journey_bodies(entry)

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
                        EdgeKind.VALIDATES,
                    ):
                        edge.assertion_targets.clear()
                        edge.assertion_targets.extend(old_targets)
                        break
                self._restore_journey_bodies(entry)

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
                    self._restore_journey_bodies(entry)
            else:
                # Remove from broken references (with new target)
                self._broken_references = [
                    br
                    for br in self._broken_references
                    if not (br.source_id == source_id and br.target_id == new_target_id)
                ]
                self._remove_leftover_ref(source, EdgeKind(edge_kind_str), new_target_id)

            # Restore the original broken reference and its leftover (REQ-d00132-G)
            self._broken_references.append(
                ReferenceFault(
                    source_id=source_id,
                    target_id=old_target_id,
                    edge_kind=edge_kind_str,
                    fault_class=self._resolution_class(old_target_id),
                )
            )
            self._add_leftover_ref(source, EdgeKind(edge_kind_str), old_target_id)

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
                    edge = parent.link(node, EdgeKind.STRUCTURES)
                    edge.metadata["render_order"] = entry.before_state.get("render_order", 0.0)
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

    # Implements: REQ-o00062-P
    def _undo_delete_journey(self, entry: MutationEntry) -> None:
        """Undo a delete journey operation, restoring the node AND its edges.

        Restoring index membership alone leaves the journey orphaned: with no
        CONTAINS edge from its FILE it belongs to no file and renders nowhere,
        so a "successful" undo would still lose it on the next save. Root
        membership and both edge directions are restored too.
        """
        node_id = entry.target_id
        node = None
        for i, deleted in enumerate(self._deleted_nodes):
            if deleted.id == node_id:
                node = self._deleted_nodes.pop(i)
                self._index[node_id] = node
                break
        if node is None:
            return

        for parent_id, kind, metadata, targets in entry.before_state.get("parent_edges", []):
            parent = self._index.get(parent_id)
            if parent is None:
                continue
            self._restore_edge_attrs(parent.link(node, EdgeKind(kind)), metadata, targets)

        for child_id, kind, metadata, targets in entry.before_state.get("child_edges", []):
            child = self._index.get(child_id)
            if child is None:
                continue
            self._restore_edge_attrs(node.link(child, EdgeKind(kind)), metadata, targets)

        if entry.before_state.get("was_root") and not any(r.id == node_id for r in self._roots):
            self._roots.append(node)

    def _undo_update_remainder(self, entry: MutationEntry) -> None:
        """Undo an update_remainder by restoring original text/heading."""
        node_id = entry.target_id
        if node_id not in self._index:
            return
        node = self._index[node_id]
        old_text = entry.before_state.get("text")
        old_heading = entry.before_state.get("heading")
        if old_text is not None:
            node.set_field("text", old_text)
        if old_heading is not None:
            node.set_field("heading", old_heading)
            node._label = old_heading
        parent_id = entry.before_state.get("parent_id")
        if parent_id and parent_id in self._index and "parent_hash" in entry.before_state:
            self._index[parent_id].set_field("hash", entry.before_state["parent_hash"])

    def _undo_add_remainder(self, entry: MutationEntry) -> None:
        """Undo an add_remainder by removing the created node."""
        node_id = entry.target_id
        if node_id not in self._index:
            return
        node = self._index.pop(node_id)
        for parent in list(node.iter_parents()):
            parent.unlink(node)
        parent_id = entry.before_state.get("parent_id")
        if parent_id and parent_id in self._index and "parent_hash" in entry.before_state:
            self._index[parent_id].set_field("hash", entry.before_state["parent_hash"])

    def _undo_delete_remainder(self, entry: MutationEntry) -> None:
        """Undo a delete_remainder by re-creating and re-linking the node."""
        node_id = entry.target_id
        parent_id = entry.before_state.get("parent_id")
        if not parent_id or parent_id not in self._index:
            return
        parent = self._index[parent_id]
        heading = entry.before_state.get("heading", "")
        text = entry.before_state.get("text", "")
        render_order = entry.before_state.get("render_order", 0.0)

        node = GraphNode(id=node_id, kind=NodeKind.REMAINDER, label=heading)
        node._content = {
            "heading": heading,
            "text": text,
            "order": entry.before_state.get("order", 0),
            "parse_line": entry.before_state.get("parse_line"),
            "parse_end_line": None,
        }
        self._index[node_id] = node
        parent.link(node, EdgeKind.STRUCTURES)
        for edge in parent.iter_outgoing_edges():
            if edge.kind == EdgeKind.STRUCTURES and edge.target is node:
                edge.metadata["render_order"] = render_order
                break
        if "parent_hash" in entry.before_state:
            parent.set_field("hash", entry.before_state["parent_hash"])

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
            before_state={
                "id": old_id,
                "title": old_title,
                "journey_bodies": self._journey_bodies_snapshot(node),
            },
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

        # Update broken references (and their rendered leftovers) that
        # reference this node
        self._retarget_broken_refs(old_id, new_id)

        # Collect child ID pairs for undo support (assertions and steps).
        child_ids_renamed: list[tuple[str, str]] = []

        # If this is a requirement, rename its assertion children
        if node.kind == NodeKind.REQUIREMENT:
            for child in list(node.iter_children()):
                if child.kind == NodeKind.ASSERTION:
                    assertion_label = child.get_field("label", "")
                    if assertion_label:
                        # The old id is the child's own, not a recomposition of
                        # it: composing under the wrong separator would miss the
                        # index entry and leave the assertion named for the
                        # requirement's former id.
                        old_assertion_id = child.id
                        new_assertion_id = self.make_assertion_id(new_id, assertion_label)
                        if old_assertion_id in self._index:
                            self._index.pop(old_assertion_id)
                            child.set_id(new_assertion_id)
                            self._index[new_assertion_id] = child
                            child_ids_renamed.append((old_assertion_id, new_assertion_id))

        # If this is a journey, cascade the rename to all STEP children.
        # Step IDs are "<journey_id>/N"; renaming the journey requires
        # updating both the _index keys and the node .id fields so that
        # find_by_id() and graph queries return the correct nodes.
        # Verifies: REQ-d00256
        if node.kind == NodeKind.USER_JOURNEY:
            for child in list(node.iter_children(edge_kinds={EdgeKind.STRUCTURES})):
                if child.kind == NodeKind.STEP:
                    old_step_id = child.id
                    if old_step_id.startswith(old_id + "/"):
                        step_suffix = old_step_id[len(old_id) :]  # "/N"
                        new_step_id = new_id + step_suffix
                        if old_step_id in self._index:
                            self._index.pop(old_step_id)
                            child.set_id(new_step_id)
                            self._index[new_step_id] = child
                            child_ids_renamed.append((old_step_id, new_step_id))

        # Store cascaded pairs so _undo_rename_node can reverse them.
        entry.after_state["child_ids_renamed"] = child_ids_renamed

        # Implements: REQ-d00230-C
        update_anchors_on_rename(self._comment_index, old_id, new_id, self.repo_root)

        # Implements: REQ-p00017-B
        # A journey's cached body embeds its own ID in the header line, and
        # the identifiers it validates in its metadata. Both are references
        # held in the graph to the former identifier, and a journey renders
        # from that cache -- so reconciling only the renamed node would leave
        # every journey citing it naming a requirement that no longer exists.
        cited_by = self._journeys_validating(node)
        self._reconcile_journey_bodies(node, *cited_by)
        # The reconciled journeys are named on the entry because the save
        # path derives which files to rewrite from the mutation log. A
        # journey corrected only in memory is a journey whose file still
        # holds the old identifier, which is the state B forbids.
        if cited_by:
            entry.after_state["journeys_reconciled"] = [j.id for j in cited_by]

        self._mutation_log.append(entry)
        return entry

    @staticmethod
    def _journeys_validating(node: GraphNode) -> list[GraphNode]:
        """The journeys whose metadata cites *node* or one of its assertions.

        A VALIDATES edge runs from the requirement to the journey, so the
        journeys are reached by walking out of the cited node -- and out of
        its assertions too, since a journey may name an assertion rather
        than the whole requirement.
        """
        cited: list[GraphNode] = []
        seen: set[int] = set()
        sources = [node, *node.iter_children(edge_kinds={EdgeKind.STRUCTURES})]
        for source in sources:
            for edge in source.iter_edges_by_kind(EdgeKind.VALIDATES):
                journey = edge.target
                if journey.kind == NodeKind.USER_JOURNEY and id(journey) not in seen:
                    seen.add(id(journey))
                    cited.append(journey)
        return cited

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
            before_state={
                "title": old_title,
                "journey_bodies": self._journey_bodies_snapshot(node),
            },
            after_state={"title": new_title},
        )

        node.set_label(new_title)
        self._reconcile_journey_bodies(node)
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

    # Implements: REQ-p00014-E
    def set_stereotype(self, node_id: str, is_template: bool) -> MutationEntry:
        """Set or clear a requirement's ``**Template**`` marker.

        Mirrors the author-declaration path (see ``_add_requirement``): the
        node AND its assertion children are stamped TEMPLATE together (or
        restored to CONCRETE), so a toggled template renders identically to
        a parsed one. INSTANCE nodes are read-only synthetic content and
        cannot be (un)templated.

        Args:
            node_id: The requirement node ID to update.
            is_template: True stamps TEMPLATE; False restores CONCRETE.

        Returns:
            MutationEntry recording the operation (per-assertion prior
            stereotypes are captured in before_state for undo).

        Raises:
            KeyError: If node_id is not found.
            ValueError: If the node is not a requirement, or is an INSTANCE.
        """
        if node_id not in self._index:
            raise KeyError(f"Node '{node_id}' not found")

        node = self._index[node_id]
        if node.kind != NodeKind.REQUIREMENT:
            raise ValueError(f"'{node_id}' is not a requirement")

        old = node.get_field("stereotype") or Stereotype.CONCRETE
        if old == Stereotype.INSTANCE:
            raise ValueError(
                f"'{node_id}' is an instance (read-only synthetic content); "
                "it cannot be marked or unmarked as a template"
            )
        new = Stereotype.TEMPLATE if is_template else Stereotype.CONCRETE

        assertion_before: dict[str, str] = {}
        for child in node.iter_children():
            if child.kind == NodeKind.ASSERTION:
                cs = child.get_field("stereotype") or Stereotype.CONCRETE
                assertion_before[child.id] = cs.value if isinstance(cs, Stereotype) else str(cs)

        entry = MutationEntry(
            operation="set_stereotype",
            target_id=node_id,
            before_state={
                "stereotype": old.value if isinstance(old, Stereotype) else str(old),
                "assertion_stereotypes": assertion_before,
            },
            after_state={"stereotype": new.value},
        )

        node.set_field("stereotype", new)
        for child in node.iter_children():
            if child.kind == NodeKind.ASSERTION:
                child.set_field("stereotype", new)

        self._mutation_log.append(entry)
        return entry

    def add_changelog_entry(
        self,
        node_id: str,
        changelog_entry: dict[str, str],
    ) -> MutationEntry:
        """Add a changelog entry to a requirement.

        Creates the changelog list if it doesn't exist.  Prepends the entry
        (newest first).

        Args:
            node_id: The requirement node ID.
            changelog_entry: Dict with keys: date, hash, change_order,
                author_name, author_id, reason.

        Returns:
            MutationEntry recording the operation.

        Raises:
            KeyError: If node_id is not found.
            ValueError: If node is not a REQUIREMENT.
        """
        if node_id not in self._index:
            raise KeyError(f"Node '{node_id}' not found")

        node = self._index[node_id]
        if node.kind != NodeKind.REQUIREMENT:
            raise ValueError(f"Node '{node_id}' is not a requirement")

        old_changelog = list(node.get_field("changelog") or [])
        new_changelog = [changelog_entry] + old_changelog

        entry = MutationEntry(
            operation="add_changelog_entry",
            target_id=node_id,
            before_state={"changelog": old_changelog},
            after_state={"changelog": new_changelog, "entry": changelog_entry},
        )

        node.set_field("changelog", new_changelog)
        self._mutation_log.append(entry)
        return entry

    def _undo_add_changelog_entry(self, entry: MutationEntry) -> None:
        """Undo an add_changelog_entry operation."""
        node_id = entry.target_id
        if node_id in self._index:
            self._index[node_id].set_field("changelog", entry.before_state.get("changelog", []))

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

        # Record state before deletion. The FILE node's id is recorded
        # alongside its path: a path alone does not say which repository
        # holds the file, so a replay that rebuilt the id from the path
        # could name a different repository's file of the same name.
        _fn = node.file_node()
        source_path = _fn.get_field("relative_path") if _fn else None
        source_file_id = _fn.id if _fn else None
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
                "source_file_id": source_file_id,
                # Implements: REQ-o00062-P
                # Full edge capture so undo reattaches the requirement rather
                # than restoring an orphan that renders into no file.
                "parent_edges": [
                    (e.source.id, e.kind.value, dict(e.metadata), list(e.assertion_targets or []))
                    for e in node.iter_incoming_edges()
                ],
                "child_edges": [
                    (e.target.id, e.kind.value, dict(e.metadata), list(e.assertion_targets or []))
                    for e in node.iter_outgoing_edges()
                ],
                "assertion_child_ids": [
                    c.id for c in node.iter_children() if c.kind == NodeKind.ASSERTION
                ],
            },
            after_state={},  # Node deleted
        )

        # Remove from index
        self._index.pop(node_id)

        # Retire broken references sourced from the deleted node — a node
        # that no longer exists has no references to report as broken.
        # Recorded for undo restoration. Implements: REQ-d00132-G
        purged_broken = [br for br in self._broken_references if br.source_id == node_id]
        if purged_broken:
            self._broken_references = [
                br for br in self._broken_references if br.source_id != node_id
            ]
            entry.before_state["purged_broken_refs"] = [asdict(br) for br in purged_broken]

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
        orphaned_children: list[str] = []
        for child in list(node.iter_children()):
            if child.kind == NodeKind.ASSERTION:
                # Delete assertion children too. Sever the edge so undo can
                # replay the captured child_edges without duplicating it.
                if child.id in self._index:
                    self._index.pop(child.id)
                    self._deleted_nodes.append(child)
                node.unlink(child)
            else:
                # Non-assertion children become orphans
                node.unlink(child)
                self._orphaned_ids.add(child.id)
                orphaned_children.append(child.id)
        entry.before_state["orphaned_child_ids"] = orphaned_children

        self._mutation_log.append(entry)
        return entry

    # ─────────────────────────────────────────────────────────────────────────
    # Assertion Mutation API
    # ─────────────────────────────────────────────────────────────────────────

    def _recompute_requirement_hash(self, req_node: GraphNode) -> str:
        """Recompute and store the hash for a requirement node.

        Delegates to the canonical ``compute_hash_for_node``. Falls back to
        ``"N/A"`` when no hashable content exists (matches existing
        render-side convention for empty requirements).

        Returns:
            The new hash value.
        """
        from elspais.graph.render import compute_hash_for_node

        new_hash = compute_hash_for_node(req_node, self.hash_mode) or "N/A"
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

        # Recompute parent hash
        self._recompute_requirement_hash(parent)

        # Implements: REQ-d00230-C
        old_anchor = f"{parent.id}#{old_label}"
        new_anchor = f"{parent.id}#{new_label}"
        update_anchors_on_rename(self._comment_index, old_anchor, new_anchor, self.repo_root)

        # Implements: REQ-p00017-B
        # A journey naming this assertion holds the old label in its cached
        # body, which is what it renders from. B covers an *Assertion*'s
        # identifier as squarely as a requirement's, so the citing journeys
        # are reconciled and named on the entry for the save path to find.
        cited_by = self._journeys_validating(parent)
        if cited_by:
            self._reconcile_journey_bodies(*cited_by)
            entry.after_state["journeys_reconciled"] = [j.id for j in cited_by]

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

        # Recompute parent hash
        self._recompute_requirement_hash(parent)

        self._mutation_log.append(entry)
        return entry

    # Implements: REQ-o00062-S
    def _next_assertion_label(self, parent: GraphNode) -> str:
        """The label following ``parent``'s last assertion in its series.

        Returns the first label in the series when the requirement has no
        assertions yet. Raises ValueError when the series is exhausted --
        a requirement that has run out of labels is one to split, not one
        to label outside its own alphabet (REQ-o00062-S).
        """
        resolver = self.resolver

        highest = -1
        for child in parent.iter_children(edge_kinds={EdgeKind.STRUCTURES}):
            if child.kind != NodeKind.ASSERTION:
                continue
            try:
                highest = max(
                    highest, resolver.parse_assertion_label_index(child.get_field("label", ""))
                )
            except ValueError:
                # A label outside the series is reported by the parser
                # (REQ-d00268-A); it must not decide where the next one lands.
                continue
        try:
            return resolver.format_assertion_label(highest + 1)
        except ValueError as exc:
            raise ValueError(
                f"Requirement '{parent.id}' has no assertion label left "
                f"in the configured series; split the requirement ({exc})"
            ) from exc

    @staticmethod
    def _order_after_assertions(parent: GraphNode, new_edge: Any) -> float:
        """A render_order placing ``new_edge`` after the last assertion.

        Falls between the last assertion and whatever follows it, so a
        trailing Rationale stays trailing. With no assertions yet, sits
        after the requirement's first child -- the preamble -- so the block
        opens ahead of the closing prose rather than beyond it.
        """
        last_assertion = None
        following = None
        for edge in parent.iter_outgoing_edges():
            if edge.kind != EdgeKind.STRUCTURES or edge is new_edge:
                continue
            order = edge.metadata.get("render_order", 0.0)
            if edge.target.kind == NodeKind.ASSERTION:
                if last_assertion is None or order > last_assertion:
                    last_assertion = order
        if last_assertion is None:
            # No assertions yet: land just past the first child.
            orders = sorted(
                e.metadata.get("render_order", 0.0)
                for e in parent.iter_outgoing_edges()
                if e.kind == EdgeKind.STRUCTURES and e is not new_edge
            )
            if not orders:
                return 0.0
            last_assertion = orders[0]
        for edge in parent.iter_outgoing_edges():
            if edge.kind != EdgeKind.STRUCTURES or edge is new_edge:
                continue
            order = edge.metadata.get("render_order", 0.0)
            if order > last_assertion and (following is None or order < following):
                following = order
        if following is None:
            return last_assertion + 1.0
        return (last_assertion + following) / 2.0

    # Implements: REQ-o00062-R
    def add_assertion(self, req_id: str, text: str) -> MutationEntry:
        """Add an assertion to a requirement, after its existing assertions.

        The label is not the caller's to choose (REQ-o00062-R): it follows
        the last existing assertion's label in the configured series, so the
        label order and the rendered order cannot disagree. The assigned
        label is reported on the returned entry.

        Args:
            req_id: The parent requirement ID.
            text: The assertion text.

        Returns:
            MutationEntry recording the operation. ``after_state["label"]``
            carries the label that was assigned.

        Raises:
            KeyError: If req_id is not found.
            ValueError: If req_id is not a requirement, or the label series
                is exhausted (REQ-o00062-S).
        """
        if req_id not in self._index:
            raise KeyError(f"Requirement '{req_id}' not found")

        parent = self._index[req_id]
        if parent.kind != NodeKind.REQUIREMENT:
            raise ValueError(f"Node '{req_id}' is not a requirement")

        label = self._next_assertion_label(parent)
        assertion_id = self.make_assertion_id(req_id, label)
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
        edge = parent.link(assertion_node, EdgeKind.STRUCTURES)

        # Sit after the last existing assertion, not the last child: a
        # requirement usually ends in prose, and an assertion rendered past
        # it opens a second Assertions block that the parser cannot read
        # back (REQ-o00062-R).
        edge.metadata = {"render_order": self._order_after_assertions(parent, edge)}

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

        # The edge carries the assertion's position in the rendered requirement;
        # without it the undo re-links at the default 0.0 and the assertion
        # reappears ahead of everything else.
        old_render_order = 0.0
        for edge in parent.iter_outgoing_edges():
            if edge.kind == EdgeKind.STRUCTURES and edge.target is node:
                old_render_order = edge.metadata.get("render_order", 0.0)
                break

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
                "render_order": old_render_order,
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
                "journey_bodies": self._journey_bodies_snapshot(source, target),
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
            self._reconcile_journey_bodies(source, target)
        else:
            # Target doesn't exist - record as broken reference
            self._broken_references.append(
                ReferenceFault(
                    source_id=source_id,
                    target_id=target_id,
                    edge_kind=edge_kind.value,
                    fault_class=self._resolution_class(target_id),
                )
            )
            entry.after_state["broken"] = True
            # The unresolved ref must still render (REQ-d00132-G)
            self._add_leftover_ref(source, edge_kind, target_id)

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
                "journey_bodies": self._journey_bodies_snapshot(source, self._index.get(target_id)),
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
        self._reconcile_journey_bodies(source, self._index.get(target_id))

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
                "journey_bodies": self._journey_bodies_snapshot(source, self._index.get(target_id)),
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
        self._reconcile_journey_bodies(source, self._index.get(target_id))

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
                # Structural edges carry render_order, which places the child in
                # its parent's rendered text; a bare re-link would lose it.
                "metadata": dict(edge_to_delete.metadata),
                "journey_bodies": self._journey_bodies_snapshot(source, target),
            },
            after_state={
                "source_id": source_id,
                "target_id": target_id,
            },
        )

        # Remove the specific edge (not all edges between these nodes)
        target.remove_edge(edge_to_delete)
        self._reconcile_journey_bodies(source, target)

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

    def add_file_node(
        self,
        absolute_path: Path,
        repo_root: Path,
        file_type: FileType,
        repo: str | None = None,
        git_branch: str | None = None,
        git_commit: str | None = None,
    ) -> MutationEntry:
        """Add a new FILE node for a file that has just been created on disk.

        The node is built via ``graph.factory.create_file_node`` so it
        matches what a full rebuild would produce — same fields, same id,
        same FileType handling. Consumers see the new FILE node on their
        next read of the graph (no separate notification channel); the
        MutationEntry is for undo and save-persistence accounting.

        Args:
            absolute_path: Path to the file on disk.
            repo_root: Repository root for computing the relative path.
            file_type: FileType classification (SPEC / CODE / TEST / etc.).
            repo: Repository identifier (None for the main project).
            git_branch: Current git branch (captured once per repo).
            git_commit: Current git commit (captured once per repo).

        Returns:
            MutationEntry recording the operation.

        Raises:
            ValueError: If a FILE node with this id already exists.
        """
        # Import here to avoid a circular import between builder and factory.
        from elspais.graph.factory import create_file_node

        # Named rather than positional: the namespace sits between the file
        # type and the repo, and a positional call that predates it lands
        # every later argument one slot early without changing arity.
        node = create_file_node(
            absolute_path,
            repo_root,
            file_type,
            self.namespace,
            repo=repo,
            git_branch=git_branch,
            git_commit=git_commit,
        )
        if node.id in self._index:
            raise ValueError(f"FILE node '{node.id}' already exists")

        self._index[node.id] = node
        self._roots.append(node)

        entry = MutationEntry(
            operation="add_file_node",
            target_id=node.id,
            before_state={},  # Node didn't exist
            after_state={
                "id": node.id,
                "relative_path": node.get_field("relative_path"),
                "absolute_path": node.get_field("absolute_path"),
                "file_type": file_type.value,
                "repo": repo,
            },
        )
        self._mutation_log.append(entry)
        return entry

    def _undo_add_file_node(self, entry: MutationEntry) -> None:
        """Undo an add_file_node operation (remove the FILE node)."""
        node_id = entry.target_id
        node = self._index.pop(node_id, None)
        if node is None:
            return
        self._roots = [r for r in self._roots if r.id != node_id]
        # FILE nodes added via add_file_node have no incoming edges
        # (they're freshly created roots), but belt-and-suspenders: unlink
        # anything that snuck in.
        for parent in list(node.iter_parents()):
            parent.unlink(node)
        for child in list(node.iter_children()):
            node.unlink(child)

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

        # A rename moves a file within its repository, never between
        # repositories, so the new id is written in the same namespace the
        # old one names.
        new_id = make_file_id(parse_structural_id(file_id)[1], new_relative_path)
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
                "journey_bodies": self._journey_bodies_snapshot(source, new_target),
            },
            after_state={
                "source_id": source_id,
                "new_target_id": new_target_id,
                "edge_kind": broken_ref.edge_kind,
            },
        )

        # Remove the old broken reference and its rendered leftover (REQ-d00132-G)
        self._broken_references.pop(broken_ref_index)
        self._remove_leftover_ref(source, edge_kind, old_target_id)

        if new_target:
            # Create valid edge
            new_target.link(source, edge_kind)
            self._reconcile_journey_bodies(source, new_target)

            # Source is no longer orphan
            self._orphaned_ids.discard(source_id)
            entry.after_state["fixed"] = True
        else:
            # New target also doesn't exist - remains broken
            self._broken_references.append(
                ReferenceFault(
                    source_id=source_id,
                    target_id=new_target_id,
                    edge_kind=broken_ref.edge_kind,
                    fault_class=self._resolution_class(new_target_id),
                )
            )
            self._add_leftover_ref(source, edge_kind, new_target_id)
            entry.after_state["still_broken"] = True

        self._mutation_log.append(entry)
        return entry

    # ─────────────────────────────────────────────────────────────────────────
    # Journey Mutation API
    # ─────────────────────────────────────────────────────────────────────────

    def _reconstruct_journey_body(self, node: GraphNode) -> str:
        """Rebuild body text from structured fields + live graph edges."""
        lines: list[str] = []
        # The depth the author wrote, not a fixed one: a journey carries its
        # heading level like a requirement does, and re-rendering it at some
        # other depth alters a file in a way nothing asked for.
        depth = "#" * (node.get_field("heading_level") or 2)
        lines.append(f"{depth} {node.id}: {node.get_label()}")
        actor = node.get_field("actor")
        if actor:
            lines.append(f"**Actor**: {actor}")
        goal = node.get_field("goal")
        if goal:
            lines.append(f"**Goal**: {goal}")
        context = node.get_field("context")
        if context:
            lines.append(f"**Context**: {context}")
        # Validates references from live graph edges (REQ is parent of JNY).
        # Aggregate assertion targets per source so `Validates: REQ-x-A+B`
        # round-trips instead of degrading to duplicate whole-req refs
        # (mirrors _derive_refs_for_edge_kind in graph/render.py).
        by_source: dict[str, tuple[bool, set[str]]] = {}
        for edge in node.iter_incoming_edges():
            if edge.kind != EdgeKind.VALIDATES:
                continue
            whole, labels = by_source.get(edge.source.id, (False, set()))
            if edge.assertion_targets:
                labels.update(edge.assertion_targets)
            else:
                whole = True
            by_source[edge.source.id] = (whole, labels)
        validates_refs: list[str] = []
        for src in sorted(by_source):
            whole, labels = by_source[src]
            if whole or not labels:
                validates_refs.append(src)
            if labels:
                # Implements: REQ-p00014-U
                # The separators are the owning repository's, not constants:
                # a journey citing an assertion writes the same boundary
                # characters a spec file's metadata line writes.
                validates_refs.append(self.resolver.make_assertion_ref(src, sorted(labels)))
        if validates_refs:
            lines.append(f"Validates: {', '.join(validates_refs)}")
        preamble = node.get_field("body_lines", [])
        if preamble:
            lines.append("")
            lines.extend(preamble)
        for section in node.get_field("sections", []):
            lines.append("")
            section_depth = "#" * (section.get("heading_level") or 2)
            lines.append(f"{section_depth} {section['name']}")
            lines.extend(section["content"].splitlines())
        lines.append("")
        # A journey closes on its title, as a requirement does. The
        # identifier form is still read -- it is what the tool used to emit,
        # so it is in files already -- but one form is written, or a file
        # saved twice would alternate between them.
        lines.append(render_end_marker(node.get_label(), None))
        return "\n".join(lines)

    def _journey_bodies_snapshot(self, *nodes: GraphNode | None) -> dict[str, str]:
        """Capture the exact cached body of any USER_JOURNEY among *nodes*.

        Stored in a mutation's before_state so undo restores the journey's
        body byte-for-byte; forward reconciliation canonicalizes, so
        re-reconstructing on undo would not round-trip the original text.
        """
        return {
            node.id: node.get_field("body")
            for node in nodes
            if node is not None and node.kind == NodeKind.USER_JOURNEY
        }

    def _restore_journey_bodies(self, entry: MutationEntry) -> None:
        """Restore journey bodies captured by _journey_bodies_snapshot."""
        for node_id, body in (entry.before_state.get("journey_bodies") or {}).items():
            node = self._index.get(node_id)
            if node is not None:
                node.set_field("body", body)

    def _reconcile_journey_bodies(self, *nodes: GraphNode | None) -> None:
        """Refresh the cached body of any USER_JOURNEY among *nodes*.

        Journeys render — and derive their concurrency version — from the
        cached ``body`` field, so every mutation that changes their ID,
        title, or VALIDATES edges must fold the live state back into that
        cache. Otherwise the mutation reports success while the render (and
        the version token) silently keeps the pre-mutation text.
        Implements: REQ-d00131-L, REQ-o00062-K
        """
        for node in nodes:
            if node is not None and node.kind == NodeKind.USER_JOURNEY:
                node.set_field("body", self._reconstruct_journey_body(node))

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

    # ── REMAINDER section mutations ──

    def update_remainder(
        self,
        node_id: str,
        text: str | None = None,
        heading: str | None = None,
    ) -> MutationEntry:
        """Update text and/or heading of an existing REMAINDER node.

        Args:
            node_id: The REMAINDER node ID.
            text: New text content (None to keep current).
            heading: New heading (None to keep current).

        Returns:
            MutationEntry recording the operation.

        Raises:
            KeyError: If node_id not found.
            ValueError: If not a REMAINDER or is a definition_block.
        """
        if node_id not in self._index:
            raise KeyError(f"Node '{node_id}' not found")

        node = self._index[node_id]
        if node.kind != NodeKind.REMAINDER:
            raise ValueError(f"Node '{node_id}' is not a REMAINDER")
        if node.get_field("content_type") == "definition_block":
            raise ValueError(f"Cannot edit definition_block node '{node_id}'")

        if text is None and heading is None:
            raise ValueError("At least one of text or heading must be provided")

        parents = [p for p in node.iter_parents() if p.kind == NodeKind.REQUIREMENT]
        if not parents:
            raise ValueError(f"REMAINDER '{node_id}' has no parent requirement")
        parent = parents[0]

        old_text = node.get_field("text", "")
        old_heading = node.get_field("heading", "")
        old_hash = parent.get_field("hash")

        if text is not None:
            node.set_field("text", text)
        if heading is not None:
            node.set_field("heading", heading)
            node._label = heading

        new_hash = self._recompute_requirement_hash(parent)

        entry = MutationEntry(
            operation="update_remainder",
            target_id=node_id,
            before_state={
                "text": old_text,
                "heading": old_heading,
                "parent_id": parent.id,
                "parent_hash": old_hash,
            },
            after_state={
                "text": node.get_field("text", ""),
                "heading": node.get_field("heading", ""),
                "parent_hash": new_hash,
            },
            affects_hash=True,
        )
        self._mutation_log.append(entry)
        return entry

    def add_remainder(
        self,
        req_id: str,
        heading: str,
        text: str,
    ) -> MutationEntry:
        """Create a new REMAINDER node linked to a requirement.

        Args:
            req_id: The parent requirement ID.
            heading: Section heading.
            text: Section text content.

        Returns:
            MutationEntry recording the operation.

        Raises:
            KeyError: If req_id not found.
            ValueError: If req_id is not a requirement.
        """
        if req_id not in self._index:
            raise KeyError(f"Requirement '{req_id}' not found")

        parent = self._index[req_id]
        if parent.kind != NodeKind.REQUIREMENT:
            raise ValueError(f"Node '{req_id}' is not a requirement")

        old_hash = parent.get_field("hash")

        # Generate unique section ID with m-prefix for mutation-created nodes
        max_counter = -1
        for child in parent.iter_children(edge_kinds={EdgeKind.STRUCTURES}):
            if child.kind == NodeKind.REMAINDER and ":section:m" in child.id:
                suffix = child.id.rsplit(":section:m", 1)[-1]
                try:
                    max_counter = max(max_counter, int(suffix))
                except ValueError:
                    pass
        section_id = f"{req_id}:section:m{max_counter + 1}"

        # Compute render_order as max existing STRUCTURES edge render_order + 1.0
        max_order = -1.0
        for edge in parent.iter_outgoing_edges():
            if edge.kind == EdgeKind.STRUCTURES:
                ro = edge.metadata.get("render_order", -1.0)
                if ro > max_order:
                    max_order = ro
        if max_order < 0:
            max_order = float(
                sum(1 for _ in parent.iter_children(edge_kinds={EdgeKind.STRUCTURES}))
            )
        render_order = max_order + 1.0

        section_node = GraphNode(
            id=section_id,
            kind=NodeKind.REMAINDER,
            label=heading,
        )
        section_node._content = {
            "heading": heading,
            "text": text,
            "order": int(render_order),
            "parse_line": None,
            "parse_end_line": None,
        }

        self._index[section_id] = section_node
        parent.link(section_node, EdgeKind.STRUCTURES)
        for edge in parent.iter_outgoing_edges():
            if edge.kind == EdgeKind.STRUCTURES and edge.target is section_node:
                edge.metadata["render_order"] = render_order
                break

        new_hash = self._recompute_requirement_hash(parent)

        entry = MutationEntry(
            operation="add_remainder",
            target_id=section_id,
            before_state={
                "parent_id": req_id,
                "parent_hash": old_hash,
            },
            after_state={
                "id": section_id,
                "heading": heading,
                "text": text,
                "render_order": render_order,
                "parent_hash": new_hash,
            },
            affects_hash=True,
        )
        self._mutation_log.append(entry)
        return entry

    def delete_remainder(
        self,
        node_id: str,
    ) -> MutationEntry:
        """Remove a REMAINDER node from its parent requirement.

        Args:
            node_id: The REMAINDER node ID.

        Returns:
            MutationEntry recording the operation.

        Raises:
            KeyError: If node_id not found.
            ValueError: If not a REMAINDER or is a definition_block.
        """
        if node_id not in self._index:
            raise KeyError(f"Node '{node_id}' not found")

        node = self._index[node_id]
        if node.kind != NodeKind.REMAINDER:
            raise ValueError(f"Node '{node_id}' is not a REMAINDER")
        if node.get_field("content_type") == "definition_block":
            raise ValueError(f"Cannot delete definition_block node '{node_id}'")

        parents = [p for p in node.iter_parents() if p.kind == NodeKind.REQUIREMENT]
        if not parents:
            raise ValueError(f"REMAINDER '{node_id}' has no parent requirement")
        parent = parents[0]

        old_hash = parent.get_field("hash")
        old_text = node.get_field("text", "")
        old_heading = node.get_field("heading", "")
        old_order = node.get_field("order", 0)
        old_parse_line = node.get_field("parse_line")

        old_render_order = 0.0
        for edge in parent.iter_outgoing_edges():
            if edge.kind == EdgeKind.STRUCTURES and edge.target is node:
                old_render_order = edge.metadata.get("render_order", 0.0)
                break

        parent.unlink(node)
        del self._index[node_id]

        new_hash = self._recompute_requirement_hash(parent)

        entry = MutationEntry(
            operation="delete_remainder",
            target_id=node_id,
            before_state={
                "parent_id": parent.id,
                "parent_hash": old_hash,
                "text": old_text,
                "heading": old_heading,
                "order": old_order,
                "parse_line": old_parse_line,
                "render_order": old_render_order,
            },
            after_state={
                "parent_hash": new_hash,
            },
            affects_hash=True,
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
            "body": f"## {journey_id}: {title}\n\n{render_end_marker(journey_id, None)}",
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
                # Implements: REQ-o00062-P
                # Full edge capture so undo can reattach the journey rather
                # than restoring an orphan that renders into no file.
                "parent_edges": [
                    (e.source.id, e.kind.value, dict(e.metadata), list(e.assertion_targets or []))
                    for e in node.iter_incoming_edges()
                ],
                "child_edges": [
                    (e.target.id, e.kind.value, dict(e.metadata), list(e.assertion_targets or []))
                    for e in node.iter_outgoing_edges()
                ],
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

    # ─────────────────────────────────────────────────────────────────────────
    # Comment Delegates (Implements: REQ-d00230-A)
    # ─────────────────────────────────────────────────────────────────────────

    def iter_comments(self, anchor: str) -> Iterator[CommentThread]:
        """Yield comment threads for an anchor."""
        return self._comment_index.iter_threads(anchor)

    def comment_count(self, anchor: str) -> int:
        """Count comment threads for an anchor."""
        return self._comment_index.thread_count(anchor)

    def has_comments(self, anchor: str) -> bool:
        """Check if any comment threads exist for an anchor."""
        return self._comment_index.has_threads(anchor)

    def iter_orphaned_comments(self) -> Iterator[CommentThread]:
        """Yield orphaned comment threads."""
        return self._comment_index.iter_orphaned()

    def add_comment_thread(self, thread: CommentThread, source_file: str) -> None:
        """Add a comment thread to the in-memory index."""
        self._comment_index.add_thread(thread, source_file)

    def find_comment_thread(self, comment_id: str) -> tuple[str, CommentThread] | None:
        """Find a thread containing a comment by its ID.

        Returns (anchor, thread) or None if not found.
        """
        return self._comment_index.find_thread(comment_id)

    def remove_comment_thread(self, comment_id: str) -> str | None:
        """Remove a thread by its root comment ID from the in-memory index.

        Returns the anchor of the removed thread, or None if not found.
        """
        return self._comment_index.remove_thread(comment_id)

    def iter_comments_for_card(self, node_id: str) -> Iterator[tuple[str, list[CommentThread]]]:
        """Yield (anchor, threads) pairs for all anchors belonging to a node."""
        for anchor in self._comment_index.iter_all_anchors_for_node(node_id):
            threads = list(self._comment_index.iter_threads(anchor))
            if threads:
                yield anchor, threads

    def comment_source_file(self, anchor: str) -> str | None:
        """Return the JSONL source file path for an anchor."""
        return self._comment_index.source_file_for(anchor)


class GraphBuilder:
    """Builder for constructing TraceGraph from parsed content.

    Usage:
        builder = GraphBuilder(namespace="REQ")
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

    # Implements: REQ-d00222-D
    def __init__(
        self,
        *,
        namespace: str,
        repo_root: Path | None = None,
        hash_mode: str = "normalized-text",
        satellite_kinds: list[str] | None = None,
        resolver: Any,
        project_name: str = "",
        link_results_to_tests: bool = True,
    ) -> None:
        """Initialize the graph builder.

        Args:
            repo_root: Repository root path.
            hash_mode: Hash calculation mode ("full-text" or "normalized-text").
            satellite_kinds: NodeKind values (e.g. ["assertion", "result"])
                that don't count as meaningful children for root/orphan
                classification. Defaults to ASSERTION and RESULT.
            resolver: The identifier grammar of the repository being built.
                Required: every identifier this builder composes — assertion
                ids, expanded multi-assertion references — is spelled with
                the boundary characters this grammar declares, and there is
                no neutral spelling to fall back on. Its namespace must be
                the one passed here; the two describe the same repository.
            namespace: The namespace of the repository whose content this
                graph holds. Required and non-empty: nodes identified by
                source location name their repository, so a graph that
                cannot say which repository it is holding cannot identify
                what is in it. Also attributes ``TermEntry.namespace``.
            project_name: Human-readable repo/project name (from
                ``[project].name`` in config). Used to tag in-repo
                INSTANCE clones with ``template_repo`` so the viewer's
                provenance affordance fires uniformly for both in-repo
                and cross-repo INSTANCE nodes (CUR-1353 Phase 11).
            link_results_to_tests: When True (default), a RESULT node
                with a ``test_id`` queues a YIELDS pending link to the
                matching TEST node; an unresolved target becomes a broken
                reference.  Set to False for aggregate/lcov
                result-crediting mode (e.g. Dart/Flutter): RESULT nodes
                are still created and feed ``_compute_app_status``, but
                no per-test YIELDS link is created so unmatched test_ids
                never produce broken references.
        """
        self.repo_root = repo_root or Path.cwd()
        self.hash_mode = hash_mode
        if not namespace:
            raise ValueError(
                "GraphBuilder requires the namespace of the repository whose "
                "content it holds: its nodes name that repository in their ids."
            )
        self._namespace = namespace
        if resolver is None:
            raise GrammarUnavailable(
                "GraphBuilder requires the identifier grammar of the repository "
                "whose content it holds: it composes identifiers, and the "
                "characters that bound their parts are configuration."
            )
        resolver_namespace = getattr(getattr(resolver, "config", None), "namespace", "")
        if resolver_namespace != namespace:
            raise ValueError(
                f"GraphBuilder was given the grammar of {resolver_namespace!r} to "
                f"build {namespace!r}. A grammar governs its own repository's "
                f"identifiers alone, so the two name one repository or neither."
            )
        self._project_name = project_name
        self._link_results_to_tests = link_results_to_tests
        self._resolver = resolver
        if satellite_kinds is not None:
            self.satellite_kinds = frozenset(NodeKind(s) for s in satellite_kinds)
        else:
            self.satellite_kinds = _DEFAULT_SATELLITE_KINDS
        self._nodes: dict[str, GraphNode] = {}
        # The fourth element is the verdict dict Task 3's reader attached to
        # the raw item that named this target (empty when the surface that
        # queued the link carries none), consulted only if the target turns
        # out missing when links are resolved.
        self._pending_links: list[
            tuple[str, str, EdgeKind, dict[tuple[str, str], tuple[FaultClass, tuple[str, ...]]]]
        ] = []
        # Implements: REQ-d00254-G
        # Source RESULT->TEST links for test_id-less reporters (e.g. flutter-
        # machine), matched by real source-file path + test() source line rather
        # than test_id. Tuple: (result_id, source_file, line, root_file,
        # root_line); resolved at build() time once every TEST node and its FILE
        # parent exist -- trying (source_file, line) first, then falling back to
        # (root_file or source_file, root_line) for testWidgets() results whose
        # test.line is a framework wrapper, then to every TEST in the file.
        self._pending_source_result_links: list[
            tuple[str, str, int | None, str | None, int | None]
        ] = []
        # Implements: REQ-d00222-A
        self._pending_terms: list[tuple[str, dict]] = []  # (node_id, parsed_data)
        # Implements: REQ-p00014-B
        # (declaring_id, template_id, the verdict dict its reference list carried)
        self._satisfies_links: list[
            tuple[str, str, dict[tuple[str, str], tuple[FaultClass, tuple[str, ...]]]]
        ] = []
        # Detection: broken references
        self._broken_references: list[ReferenceFault] = []
        # Implements: REQ-d00272-G
        self._style_findings: list[StyleFinding] = []
        # Implements: REQ-d00272-O
        self._undeclared_relationships: list[UndeclaredRelationship] = []
        # Implements: REQ-d00272-N
        self._identifier_form_findings: list[IdentifierFormFinding] = []
        # Detection: duplicate REQ IDs across files. Maps the canonical (real)
        # requirement ID -> ordered list of source paths that defined it. First
        # occurrence keeps the real ID; subsequent occurrences get a synthetic
        # ID (see _add_requirement) but their source paths are recorded here.
        self._duplicate_req_ids: dict[str, list[str]] = {}

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
                code_id = make_code_id(source_id, content.start_line)
                node = self._nodes.get(code_id)
                if node:
                    self._wire_contains_edge(file_node, node, content)
        elif content.content_type == "test_ref":
            self._add_test_ref(content)
            if file_node is not None:
                # Find the test node that was just created.  Mirror the ID
                # computation in _add_test_ref exactly so we find the right
                # node when function_line differs from start_line (e.g. Dart
                # prescan anchors to the test() call line, not the comment).
                data = content.parsed_data
                source_ctx = getattr(content, "source_context", None)
                source_id = source_ctx.source_id if source_ctx else "test"
                func_name = data.get("function_name")
                class_name = data.get("class_name")
                if func_name:
                    rel_path = self._to_relative_path(source_id)
                    test_id = build_test_id(rel_path, func_name, class_name)
                else:
                    func_line = data.get("function_line", content.start_line)
                    anchor_line = func_line or content.start_line
                    test_id = make_test_id(source_id, anchor_line)
                node = self._nodes.get(test_id)
                if node:
                    self._wire_contains_edge(file_node, node, content)
        elif content.content_type == "test_result":
            self._add_test_result(content)
            if file_node is not None:
                node = self._nodes.get(content.parsed_data.get("id", ""))
                if node:
                    self._wire_contains_edge(file_node, node, content)
        elif content.content_type == "definition_block":
            # Implements: REQ-d00222-A
            self._add_definition_block(content)
            if file_node is not None:
                data = content.parsed_data
                source_ctx = getattr(content, "source_context", None)
                source_path = source_ctx.source_id if source_ctx else ""
                rel_source = self._to_relative_path(source_path) if source_path else source_path
                remainder_id = data.get("id") or make_definition_id(
                    self._namespace, rel_source, content.start_line
                )
                node = self._nodes.get(remainder_id)
                if node:
                    self._wire_contains_edge(file_node, node, content)
        elif content.content_type == "remainder":
            self._add_remainder(content)
            # Wire CONTAINS from FILE to file-level REMAINDER
            if file_node is not None:
                data = content.parsed_data
                source_ctx = getattr(content, "source_context", None)
                source_path = source_ctx.source_id if source_ctx else ""
                rel_source = self._to_relative_path(source_path) if source_path else source_path
                remainder_id = data.get("id") or make_remainder_id(
                    self._namespace, rel_source, content.start_line
                )
                node = self._nodes.get(remainder_id)
                if node:
                    self._wire_contains_edge(file_node, node, content)
        elif content.content_type == "reference_fault":
            # Implements: REQ-d00269-H, REQ-p00019-A
            # No node is created and no CONTAINS edge wired -- the physical
            # line already round-trips via the remainder gatherer. The FILE
            # node is the only anchor available for a fault with no CODE/TEST
            # node of its own (an empty reference list, a trailing separator).
            data = content.parsed_data
            source_id = file_node.id if file_node is not None else data.get("source_id", "")
            self._broken_references.append(
                ReferenceFault(
                    source_id=source_id,
                    target_id=data["raw"],
                    edge_kind=data.get("edge_kind") or "",
                    fault_class=data["fault_class"],
                    codes=data["codes"],
                    line=content.start_line,
                )
            )
        elif content.content_type == "style_finding":
            # Implements: REQ-d00272-G
            data = content.parsed_data
            source_id = file_node.id if file_node is not None else data.get("source_id", "")
            self._style_findings.append(
                StyleFinding(source_id=source_id, code=data["code"], line=content.start_line)
            )
        elif content.content_type == "identifier_form_finding":
            # Implements: REQ-d00272-N
            # The relationship was produced; only its spelling is reported,
            # so this joins no bucket that counts references that failed.
            data = content.parsed_data
            source_id = file_node.id if file_node is not None else data.get("source_id", "")
            self._identifier_form_findings.append(
                IdentifierFormFinding(
                    source_id=source_id,
                    text=data["text"],
                    codes=tuple(data["codes"]),
                    line=content.start_line,
                )
            )
        elif content.content_type == "undeclared_relationship":
            # Implements: REQ-d00272-O
            # No node, no edge: reading an informal citation as a
            # declaration is exactly the inference this vocabulary exists
            # to refuse.  The FILE node anchors it, since the line
            # declared nothing that could carry it.
            data = content.parsed_data
            source_id = file_node.id if file_node is not None else data.get("source_id", "")
            self._undeclared_relationships.append(
                UndeclaredRelationship(
                    source_id=source_id, text=data["text"], line=content.start_line
                )
            )

    def _add_requirement(self, content: ParsedContent) -> None:
        """Add a requirement node and its assertions."""
        data = content.parsed_data
        req_id = data["id"]

        # Cross-file REQ ID collision: when the same canonical ID is defined in
        # two source files, the first definition keeps the real ID and any
        # subsequent definition gets a synthetic ID like ``REQ-X#<file-stem>``.
        # The ``#`` is invalid in all canonical component styles (numeric,
        # camelCase, PascalCase, snake_case, kebab-case), so the synthetic ID
        # cannot collide with a real ID. Both nodes carry their own content,
        # assertions, and parent edges; nothing is merged.
        source_ctx = getattr(content, "source_context", None)
        source_path_raw = source_ctx.source_id if source_ctx else ""
        source_path_rel = self._to_relative_path(source_path_raw) if source_path_raw else ""
        canonical_id = req_id
        is_duplicate_occurrence = False
        if req_id in self._nodes:
            is_duplicate_occurrence = True
            file_stem = Path(source_path_rel).stem if source_path_rel else "dup"
            synthetic_id = f"{req_id}#{file_stem}"
            n = 2
            while synthetic_id in self._nodes:
                synthetic_id = f"{req_id}#{file_stem}__{n}"
                n += 1
            # Guard against a configured ID resolver (e.g. a permissive
            # `component.style = "regex"` pattern) that would accept the
            # synthetic form as a real canonical ID. If that ever happened, a
            # later human-authored ID could collide with the synthetic and
            # disguise itself as a duplicate. Refuse to build with a clear
            # message rather than silently producing wrong duplicate reports.
            if self._resolver.is_valid(synthetic_id):
                raise ValueError(
                    f"Cannot disambiguate duplicate REQ ID {canonical_id!r}: "
                    f"the configured ID resolver accepts the synthetic form "
                    f"{synthetic_id!r} as a real ID. Tighten the configured "
                    f"`component.style` pattern so it cannot match a '#' "
                    f"character, or resolve the source-file collision."
                )
            data["id"] = synthetic_id
            req_id = synthetic_id

        if is_duplicate_occurrence:
            entry = self._duplicate_req_ids.setdefault(canonical_id, [])
            if not entry:
                first_node = self._nodes.get(canonical_id)
                first_source = first_node.get_field("source_file", "") if first_node else ""
                if first_source:
                    entry.append(first_source)
            if source_path_rel:
                entry.append(source_path_rel)

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
            "changelog": data.get("changelog", []),
            "stereotype": Stereotype.CONCRETE,
            "parse_line": content.start_line,
            "parse_end_line": content.end_line,
            # Store reference lists for render protocol
            "implements_refs": data.get("implements", []),
            "refines_refs": data.get("refines", []),
            "satisfies_refs": data.get("satisfies", []),
            # Implements: REQ-d00252
            "integrates_refs": data.get("integrates", []),
            # Implements: REQ-d00272-K
            # The raw items the reader refused. They stay in
            # ``integrates_refs`` so rendering returns the author's own text
            # unchanged, and are named here so the federation pass wires no
            # relationship for an item whose verdict already withheld one.
            "integrates_refused": sorted(
                {
                    raw
                    for (kw, raw), verdict in (data.get("reference_verdicts") or {}).items()
                    if kw == EdgeKind.INTEGRATES.value and reader_refused(verdict)
                }
            ),
            "heading_level": data.get("heading_level", 2),
            "assertions_heading_level": data.get("assertions_heading_level"),
            "changelog_heading_level": data.get("changelog_heading_level"),
            "hash_mode": self.hash_mode,
            # Track source file path so a subsequent collision can record where
            # this (first) definition came from.
            "source_file": source_path_rel,
        }
        if is_duplicate_occurrence:
            node._content["is_duplicate"] = True
            node._content["original_id"] = canonical_id
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
            assertion_id = self._resolver.make_assertion_id(req_id, assertion["label"])
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
        _has_list_spacing_fix = False
        for idx, section in enumerate(data.get("sections", [])):
            section_id = f"{req_id}:section:{idx}"
            section_line = section.get("line", content.start_line)
            section_text = section["content"]
            canonical_text = _canonicalize_list_spacing(section_text)
            if canonical_text != section_text:
                _has_list_spacing_fix = True
                section_text = canonical_text
            section_node = GraphNode(
                id=section_id,
                kind=NodeKind.REMAINDER,
                label=section["heading"],
            )
            section_node._content = {
                "heading": section["heading"],
                "text": section_text,
                "order": idx,
                "parse_line": section_line,
                "parse_end_line": None,
                "content_line": section.get("content_line", section_line),
            }
            # Preserve heading style for assertion sub-headings (* ** _ hash)
            if "heading_style" in section:
                section_node._content["heading_style"] = section["heading_style"]
            # Preserve heading_level for section depth canonicalization (REQ-d00250-A)
            if "heading_level" in section:
                section_node._content["heading_level"] = section["heading_level"]
            self._nodes[section_id] = section_node
            children_with_lines.append((section_line, section_node))

        # Implements: REQ-d00222-A
        # Create REMAINDER children from definition blocks in requirement preamble/sections
        for def_idx, defn in enumerate(data.get("definitions", [])):
            def_id = f"{req_id}:def:{def_idx}"
            def_line = defn.get("line", content.start_line)
            def_node = GraphNode(
                id=def_id,
                kind=NodeKind.REMAINDER,
                label=defn.get("term", ""),
            )
            def_node._content = {
                "text": format_definition_block(defn),
                "content_type": "definition_block",
                "term": defn.get("term", ""),
                "definition": defn.get("definition", ""),
                "collection": defn.get("collection", False),
                "indexed": defn.get("indexed", True),
                "parse_line": def_line,
                "parse_end_line": None,
            }
            self._nodes[def_id] = def_node
            children_with_lines.append((def_line, def_node))
            self._pending_terms.append((def_id, defn))

        # Add children in document order (sorted by line number)
        # Implements: REQ-d00128-F
        children_with_lines.sort(key=lambda x: x[0])
        for line_num, child_node in children_with_lines:
            edge = node.link(child_node, EdgeKind.STRUCTURES)
            edge.metadata = {"render_order": float(line_num)}

        # Mark node dirty for any condition that would change the file on save
        parse_dirty_reasons: list[str] = []
        if data.get("has_redundant_refs"):
            parse_dirty_reasons.append("duplicate_refs")
        # Check for consecutive assertions without blank-line separators
        assertions_data = data.get("assertions", [])
        if len(assertions_data) >= 2:
            for i in range(len(assertions_data) - 1):
                a_line = assertions_data[i].get("line", 0)
                a_lines = len(assertions_data[i].get("text", "").split("\n"))
                b_line = assertions_data[i + 1].get("line", 0)
                if b_line <= a_line + a_lines:
                    parse_dirty_reasons.append("assertion_spacing")
                    break
        if _has_list_spacing_fix:
            parse_dirty_reasons.append("list_spacing")
        stored_hash = data.get("hash")
        if stored_hash:
            from elspais.graph.render import compute_hash_for_node

            computed = compute_hash_for_node(node, self.hash_mode)
            if computed and stored_hash != computed:
                parse_dirty_reasons.append("stale_hash")

        # Section header depth validation
        # Implements: REQ-d00250-B, REQ-d00250-C
        req_depth = data.get("heading_level", 2)
        min_child_depth = req_depth + 1
        has_section_block = False
        section_too_shallow = False

        # Assertions block
        assertions_d = data.get("assertions_heading_level")
        if assertions_d is not None:
            has_section_block = True
            if assertions_d < min_child_depth:
                section_too_shallow = True

        # Changelog block
        changelog_d = data.get("changelog_heading_level")
        if changelog_d is not None:
            has_section_block = True
            if changelog_d < min_child_depth:
                section_too_shallow = True

        # Named sections and hash sub-headings (entries in data["sections"])
        # Note: preamble has no header so it isn't included in `sections` from
        # the transformer with a meaningful heading_level — but its dict has
        # heading="preamble"; skip it defensively.
        effective_assertions_depth = (
            min(max(assertions_d, min_child_depth), 6)
            if assertions_d is not None
            else min(min_child_depth, 6)
        )
        for sec in data.get("sections", []):
            if sec.get("heading") == "preamble":
                continue
            sec_style = sec.get("heading_style")
            sec_d = sec.get("heading_level")
            if sec_d is None:
                continue
            if sec_style is None:
                # Named section directly under the requirement.
                has_section_block = True
                if sec_d < min_child_depth:
                    section_too_shallow = True
            elif sec_style == "hash":
                # Hash sub-heading inside the assertion block; parent is the
                # (effective) assertions header.
                if sec_d < effective_assertions_depth + 1:
                    section_too_shallow = True

        # H6 ceiling: if req+1 would exceed 6 AND the req has any section
        # block, the situation is unfixable.
        unfixable = has_section_block and min_child_depth > 6

        if section_too_shallow and not unfixable:
            parse_dirty_reasons.append("section_header_depth")

        if parse_dirty_reasons:
            node._content["parse_dirty"] = True
            node._content["parse_dirty_reasons"] = parse_dirty_reasons

        if unfixable:
            existing = node._content.get("parse_unfixable_reasons", [])
            node._content["parse_unfixable_reasons"] = existing + ["section_header_depth_unfixable"]

        # Queue implements/refines links for later resolution. The verdict
        # dict Task 3's reader carried for this requirement's reference
        # lists rides along, so a malformed or duplicated item is classified
        # the same way here as in a code or test annotation (REQ-d00272-K).
        req_verdicts = data.get("reference_verdicts") or {}
        for impl_ref in data.get("implements", []):
            self._pending_links.append((req_id, impl_ref, EdgeKind.IMPLEMENTS, req_verdicts))

        for refine_ref in data.get("refines", []):
            self._pending_links.append((req_id, refine_ref, EdgeKind.REFINES, req_verdicts))

        # Implements: REQ-p00014-B, REQ-d00272-K
        # The verdict its item carried rides along exactly as it does for
        # Implements and Refines: a Satisfies target reads through the one
        # reader, so a malformed or repeated item is classified the same way
        # here as under any other keyword.
        for sat_ref in data.get("satisfies", []):
            self._satisfies_links.append((req_id, sat_ref, req_verdicts))

        # Implements: REQ-d00252, REQ-d00272-K
        # An Integrates item the reader refused is reported here, under the
        # class the reader reached. Its target is resolved by the federation
        # pass rather than by pending-link resolution, so without this the
        # refusal reaches no surface at all.
        for (kw, raw), verdict in req_verdicts.items():
            if kw != EdgeKind.INTEGRATES.value or not reader_refused(verdict):
                continue
            fault_class, codes = verdict
            self._broken_references.append(
                ReferenceFault(
                    source_id=req_id,
                    target_id=raw,
                    edge_kind=EdgeKind.INTEGRATES.value,
                    fault_class=fault_class,
                    codes=codes,
                )
            )

        # Implements: REQ-p00014-E
        # Author-declared TEMPLATE marker: stamp the REQ and its assertions
        # so the parser-only Stereotype is correct before subtree-cloning runs.
        if data.get("template"):
            node.set_field("stereotype", Stereotype.TEMPLATE)
            for _line_num, child_node in children_with_lines:
                if child_node.kind == NodeKind.ASSERTION:
                    child_node.set_field("stereotype", Stereotype.TEMPLATE)

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
            # The depth the journey was authored at. The parser reads it; a
            # node that did not carry it is re-rendered at a fixed depth, so
            # saving a journey moved its heading.
            "heading_level": data.get("heading_level"),
            "parse_line": content.start_line,
            "parse_end_line": content.end_line,
        }
        self._nodes[journey_id] = node

        # Implements: REQ-d00256-A
        # Create one STEP node per numbered step in the ## Steps section,
        # linked from the journey via STRUCTURES edges (read-only; never rendered).
        step_children: list[tuple[int, GraphNode]] = []
        for step in data.get("steps", []):
            step_id = make_step_id(journey_id, step["n"])
            step_node = GraphNode(
                id=step_id,
                kind=NodeKind.STEP,
                label=step["text"],
            )
            step_node._content = {
                "n": step["n"],
                "label": str(step["n"]),
                "parse_line": step["line"],
                "parse_end_line": None,
            }
            self._nodes[step_id] = step_node
            step_children.append((step["line"], step_node))

        step_children.sort(key=lambda x: x[0])
        for line_num, step_node in step_children:
            edge = node.link(step_node, EdgeKind.STRUCTURES)
            edge.metadata = {"render_order": float(line_num)}

        # Queue validates links for later resolution. Same verdict-threading
        # as a requirement's Implements/Refines (REQ-d00272-K): a journey's
        # Validates: is read through the same reader, so it is classified
        # the same way.
        jny_verdicts = data.get("reference_verdicts") or {}
        for addr_ref in data.get("validates", []):
            self._pending_links.append((journey_id, addr_ref, EdgeKind.VALIDATES, jny_verdicts))

        # Implements: REQ-p00014-V, REQ-p00014-R
        # A declaration outside the metadata produced no relationship. Saying
        # so is the whole point of refusing to read it: a journey that
        # validates less than its author wrote must not look like a journey
        # that validated everything.
        for section_name, declared in data.get("misplaced_validates", []):
            where = f'section "{section_name}"' if section_name else "a section"
            self._broken_references.append(
                ReferenceFault(
                    source_id=journey_id,
                    target_id=declared,
                    edge_kind="validates",
                    fault_class=FaultClass.FORBIDDEN,
                    diagnostic=(
                        f"declared in {where} rather than in the journey's "
                        f"metadata, so it validates nothing. Move the "
                        f"declaration up to the metadata, beside Actor and Goal."
                    ),
                )
            )

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

        all_refs = [(ref, EdgeKind.IMPLEMENTS) for ref in data.get("implements", [])] + [
            (ref, EdgeKind.VERIFIES) for ref in data.get("verifies", [])
        ]
        forbidden = data.get("forbidden") or []
        verdicts = data.get("reference_verdicts") or {}

        def _ensure_code_node() -> str:
            code_id = make_code_id(source_id, content.start_line)
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
            return code_id

        for ref, edge_kind in all_refs:
            code_id = _ensure_code_node()
            self._pending_links.append((code_id, ref, edge_kind, verdicts))

        # Implements: REQ-d00272-J
        # A keyword a code file may not use is read, not passed over: the
        # relationship it would have declared is refused and reported,
        # anchored to the same CODE node an admitted keyword would use.
        if forbidden:
            code_id = _ensure_code_node()
            self._broken_references.extend(
                self._forbidden_keyword_faults(
                    code_id,
                    data.get("forbidden_keyword", ""),
                    forbidden,
                    verdicts,
                    "code",
                )
            )

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
            # Fallback: line-based ID keyed on the owning unit's line when a
            # prescan supplied one (e.g. Dart test() call line), else the ref line.
            # func_line==0 is text_prescan's "no function context" sentinel;
            # in that case fall back to the comment's own line so each ref
            # gets a distinct id (the pre-843a571d behaviour).
            anchor_line = func_line or content.start_line
            test_id = make_test_id(source_id, anchor_line)
            label = f"Test at {source_id}:{anchor_line}"
            source_line = anchor_line

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
            self._nodes[test_id] = node

        verdicts = data.get("reference_verdicts") or {}
        for val_ref in data.get("verifies", []):
            self._pending_links.append((test_id, val_ref, EdgeKind.VERIFIES, verdicts))

        # Implements: REQ-d00272-J
        # A keyword a test file may not use (anything but Verifies) is read,
        # not passed over: the relationship it would have declared is
        # refused and reported.  No function context is attached here even
        # when one is available -- doing so would mark the function's line
        # "emitted" and suppress the third-pass unlinked-test fallback that
        # gives the actual test function its file-default Verifies.
        forbidden = data.get("forbidden") or []
        if forbidden:
            self._broken_references.extend(
                self._forbidden_keyword_faults(
                    test_id,
                    data.get("forbidden_keyword", ""),
                    forbidden,
                    verdicts,
                    "test",
                )
            )

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

        source_ctx = getattr(content, "source_context", None)
        source_path = data.get("source_path") or (source_ctx.source_id if source_ctx else None)

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
            "source_path": source_path,
            "source_file": data.get("source_file") or source_path,
            "match": data.get("match", "aggregate"),
            "line": data.get("line"),
            "root_line": data.get("root_line"),
            "root_file": data.get("root_file"),
            # Implements: REQ-d00254-I
            "carried": data.get("carried", False),
            "target": data.get("target"),
            # Results-file provenance: where this result was RECORDED
            # (e.g. junit.xml path + <testcase> line), distinct from
            # source_path/source_file which name the test's source.
            "result_file": data.get("result_file"),
            "result_line": data.get("result_line"),
        }
        self._nodes[result_id] = node

        # Queue edge to parent TEST node if test_id is provided.
        # In aggregate result-crediting mode (link_results_to_tests=False)
        # the RESULT node exists to feed _compute_app_status but no
        # per-test YIELDS link is created -- unmatched test_ids must not
        # become broken references (applies only when default link mode is
        # enabled).
        if test_id and self._link_results_to_tests and data.get("match") != "aggregate":
            # Implements: REQ-d00127-E
            self._pending_links.append((result_id, test_id, EdgeKind.YIELDS, {}))
        elif data.get("match") == "source" and self._link_results_to_tests:
            # Implements: REQ-d00254-G
            # Source-matching reporters (e.g. flutter-machine) emit no test_id;
            # they match RESULT->TEST by real source-file path + test() source
            # line. Queue (result_id, source_file, line) resolved once all
            # TEST/FILE nodes exist (see build()): line-precise when it
            # resolves, file-granular fallback otherwise.
            source_file = node.get_field("source_file")
            if source_file:
                self._pending_source_result_links.append(
                    (
                        result_id,
                        source_file,
                        data.get("line"),
                        data.get("root_file"),
                        data.get("root_line"),
                    )
                )

    # Implements: REQ-d00222-A
    def _add_definition_block(self, content: ParsedContent) -> None:
        """Add a definition block as a REMAINDER node with content_type field."""
        data = content.parsed_data
        source_ctx = getattr(content, "source_context", None)
        source_path = source_ctx.source_id if source_ctx else ""

        rel_source = self._to_relative_path(source_path) if source_path else source_path
        remainder_id = data.get("id") or make_definition_id(
            self._namespace, rel_source, content.start_line
        )
        text = content.raw_text or ""

        node = GraphNode(
            id=remainder_id,
            kind=NodeKind.REMAINDER,
            label=data.get("term", text[:50]),
        )
        node._content = {
            "text": text,
            "content_type": "definition_block",
            "term": data.get("term", ""),
            "definition": data.get("definition", ""),
            "collection": data.get("collection", False),
            "indexed": data.get("indexed", True),
            "parse_line": content.start_line,
            "parse_end_line": content.end_line,
        }
        self._nodes[remainder_id] = node
        self._pending_terms.append((remainder_id, data))

    def _add_remainder(self, content: ParsedContent) -> None:
        """Add a remainder/unclaimed content node."""
        data = content.parsed_data
        source_ctx = getattr(content, "source_context", None)
        source_path = source_ctx.source_id if source_ctx else ""

        # Use provided ID or generate from source location (repo-relative to
        # keep generated artifacts stable across worktrees).
        rel_source = self._to_relative_path(source_path) if source_path else source_path
        remainder_id = data.get("id") or make_remainder_id(
            self._namespace, rel_source, content.start_line
        )
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

    # Implements: REQ-d00128-D, REQ-d00128-E
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
        """Expand a multi-assertion reference into its individual references.

        REQ-p00001-A+B+C -> [REQ-p00001-A, REQ-p00001-B, REQ-p00001-C]

        Which characters divide a component from its first label, and one
        label from the next, is the repository's grammar to say — reading
        them off the string instead would find whichever of them the
        component happens to contain.
        """
        parsed = self._resolver.parse(target_id)
        if parsed is None or len(parsed.assertions) <= 1:
            return [target_id]
        return [self._resolver.render_canonical(e) for e in self._resolver.expand(parsed)]

    # Implements: REQ-p00014-R
    def _resolution_class(self, target_id: str) -> FaultClass:
        """Which class an item that read but did not resolve reached.

        A label that names no assertion of a requirement that exists is a
        different finding from a requirement nothing holds: the first is
        always the author's, the second may be a sibling that has not
        authored it yet.  Reporting the later class than the reference
        reached would describe a defect the author does not have.
        """
        split = self._resolver.split_assertion_ref(target_id)
        if split is not None and split[0] in self._nodes:
            return FaultClass.UNKNOWN_ASSERTION
        return FaultClass.UNKNOWN_REQUIREMENT

    # Implements: REQ-d00252-K
    def _fault_verdict(
        self,
        target_id: str,
        keyword: str,
        verdicts: dict[tuple[str, str], tuple[FaultClass, tuple[str, ...]]],
    ) -> tuple[FaultClass, tuple[str, ...]]:
        """The class and codes for *target_id*, from its parsed verdict or
        resolution.

        A verdict Task 3's reader carried (grammar-level: the item never
        matched any member's identifier) always wins when present; an item
        that matched but names a node this graph does not hold falls back to
        ``_resolution_class``, since no grammar-level verdict exists for it
        (REQ-d00269-G reads a multi-assertion item's expanded labels
        individually, and only the whole item's raw text is ever a verdict
        key).

        No prose accompanies either answer. A cause is named by the code, the
        file and the line the reference was written on, and that code's
        documented meaning (REQ-d00252-K); all three reach every surface, so
        a sentence guessing at a separator mismatch would only add a fourth
        naming that the input does not determine -- and, on the fallback
        path, would name a defect an item that parsed perfectly and is simply
        absent does not have.
        """
        if (keyword, target_id) in verdicts:
            return verdicts[(keyword, target_id)]
        return self._resolution_class(target_id), ()

    # Implements: REQ-d00272-A, REQ-d00272-J
    def _forbidden_keyword_faults(
        self,
        source_id: str,
        keyword: str,
        targets: list[str],
        verdicts: dict[tuple[str, str], tuple[FaultClass, tuple[str, ...]]],
        file_kind: str,
    ) -> list[ReferenceFault]:
        """The faults a keyword *file_kind* may not use produces for *targets*.

        ``FORBIDDEN`` is the last stage of reading, and an item only arrives
        there by having read: the keyword refuses a relationship the item
        successfully named.  An item that never read stopped earlier and
        carries its own verdict, which is reported instead -- stamping the
        refusal on it would report a later stage than reading reached
        (REQ-d00272-A) and describe it as resolving, which it did not.

        The verdict is looked up against the item as written, before any
        multi-*Assertion* expansion: the reader keys a verdict by the whole
        item's raw text, and an expanded label is not that key.
        """
        faults: list[ReferenceFault] = []
        for raw_target in targets:
            if (keyword, raw_target) in verdicts:
                fault_class, codes = verdicts[(keyword, raw_target)]
                faults.append(
                    ReferenceFault(
                        source_id=source_id,
                        target_id=raw_target,
                        edge_kind=keyword,
                        fault_class=fault_class,
                        codes=codes,
                    )
                )
                continue
            for expanded in self._expand_multi_assertion(raw_target):
                faults.append(
                    ReferenceFault(
                        source_id=source_id,
                        target_id=expanded,
                        edge_kind=keyword,
                        fault_class=FaultClass.FORBIDDEN,
                        diagnostic=(
                            f"'{keyword.capitalize()}:' is not a valid keyword in "
                            f"a {file_kind} file; the declaration is refused."
                        ),
                    )
                )
        return faults

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
        # Implements: REQ-d00272-K
        # An item its reader already refused never reaches template lookup:
        # its verdict decided it binds nothing, and finding the node anyway
        # would return the relationship the verdict withheld. It is reported
        # under the class the reader reached, not the resolution-stage one.
        #
        # One entry per refused ITEM, not per (declaring, target) pair: the
        # commonest reason an item is refused is that it repeats a sibling,
        # and every instance of a repeat is reported. Keyed by the pair, the
        # instances would collapse into the one report that keeping the first
        # instance already produces -- the silence this assertion exists to
        # remove.
        refused_items: list[tuple[str, str, FaultClass, tuple[str, ...]]] = []
        for declaring_id, template_id, verdicts in self._satisfies_links:
            refused = verdicts.get((EdgeKind.SATISFIES.value, template_id))
            if reader_refused(refused):
                assert refused is not None
                refused_items.append((declaring_id, template_id, refused[0], refused[1]))
                continue
            # Handle assertion-level satisfies: strip assertion suffix to find root
            # but keep the full ref for later use
            template_roots.setdefault(template_id, []).append(declaring_id)

        for declaring_id, template_id, fault_class, codes in refused_items:
            self._broken_references.append(
                ReferenceFault(
                    source_id=declaring_id,
                    target_id=template_id,
                    edge_kind=EdgeKind.SATISFIES.value,
                    fault_class=fault_class,
                    codes=codes,
                )
            )

        # CUR-1353 Phase 2 (single-REQ scope): a template is one REQ root plus
        # its directly-attached assertions. We do NOT pre-resolve REFINES into
        # templates — any such inbound REFINES is invalid (rule 8) and will be
        # rejected when pending links are resolved later in ``build()``.

        # Sub-pass 1: Validate template-marker on each Satisfies target.
        # Implements: REQ-p00014-F, REQ-p00014-G
        # Composite targets (containing INSTANCE_SEPARATOR) are deferred to
        # sub-pass 2 — their INSTANCE may be cloned by a sibling satisfier
        # later in this same call.
        for template_id in list(template_roots.keys()):
            template_node = self._nodes.get(template_id)
            if not template_node:
                if INSTANCE_SEPARATOR in template_id:
                    # Defer to sub-pass 2; the INSTANCE may yet be cloned.
                    continue
                # Genuinely missing — record a plain broken-ref and skip clone.
                for declaring_id in template_roots[template_id]:
                    self._broken_references.append(
                        ReferenceFault(
                            source_id=declaring_id,
                            target_id=template_id,
                            edge_kind=EdgeKind.SATISFIES.value,
                            fault_class=self._resolution_class(template_id),
                        )
                    )
                template_roots[template_id] = []
                continue
            stereotype = template_node.get_field("stereotype")
            if stereotype != Stereotype.TEMPLATE:
                # Rule 1 (CUR-1353): Satisfies target exists but is not marked
                # **Template**. Emit a typed diagnostic and skip cloning so
                # we don't manufacture an INSTANCE subtree against a concrete
                # node.
                for declaring_id in template_roots[template_id]:
                    self._broken_references.append(
                        ReferenceFault(
                            source_id=declaring_id,
                            target_id=template_id,
                            edge_kind=EdgeKind.SATISFIES.value,
                            fault_class=FaultClass.FORBIDDEN,
                            diagnostic=(
                                f"{template_id} is not marked **Template**; "
                                f"mark {template_id} with **Template** if it's "
                                f"intended to be satisfiable."
                            ),
                        )
                    )
                template_roots[template_id] = []

        # Sub-pass 2: Clone & link. Skip any satisfies-link whose template was
        # rejected in sub-pass 1 (template_roots[t] emptied).
        cloneable_links = [(d, t) for d, t, _v in self._satisfies_links if template_roots.get(t)]
        for declaring_id, template_id in cloneable_links:
            template_node = self._nodes.get(template_id)
            declaring_node = self._nodes.get(declaring_id)
            if not template_node or not declaring_node:
                # Composite that still doesn't resolve after cloning passes —
                # genuinely broken.
                if not template_node and INSTANCE_SEPARATOR in template_id:
                    self._broken_references.append(
                        ReferenceFault(
                            source_id=declaring_id,
                            target_id=template_id,
                            edge_kind=EdgeKind.SATISFIES.value,
                            fault_class=self._resolution_class(template_id),
                        )
                    )
                continue
            # Rule 2 (CUR-1353): chained instantiation. The composite target
            # resolved to an INSTANCE node (typically cloned earlier in this
            # very loop by a sibling satisfier). Refuse to clone again.
            if template_node.get_field("stereotype") == Stereotype.INSTANCE:
                self._broken_references.append(
                    ReferenceFault(
                        source_id=declaring_id,
                        target_id=template_id,
                        edge_kind=EdgeKind.SATISFIES.value,
                        fault_class=FaultClass.FORBIDDEN,
                        diagnostic=(
                            "Chained instantiation is not supported. "
                            "Satisfy the original template directly."
                        ),
                    )
                )
                continue
            # Defensive: a composite that resolves to a non-TEMPLATE non-
            # INSTANCE node would have been blanked in sub-pass 1 for the
            # non-composite case. For composites this is still possible —
            # emit rule-1 diagnostic.
            if template_node.get_field("stereotype") != Stereotype.TEMPLATE:
                self._broken_references.append(
                    ReferenceFault(
                        source_id=declaring_id,
                        target_id=template_id,
                        edge_kind=EdgeKind.SATISFIES.value,
                        fault_class=FaultClass.FORBIDDEN,
                        diagnostic=(
                            f"{template_id} is not marked **Template**; "
                            f"mark {template_id} with **Template** if it's "
                            f"intended to be satisfiable."
                        ),
                    )
                )
                continue

            # CUR-1353 Phase 2: single-REQ scope. A template is one REQ root
            # plus its directly-attached assertions (STRUCTURES children).
            # No transitive walk -- child REQs cannot be part of the template
            # (rule 8 forbids inbound REFINES against a template).
            template_nodes: list[GraphNode] = [template_node]
            for child in template_node.iter_children(edge_kinds={EdgeKind.STRUCTURES}):
                if child.kind == NodeKind.ASSERTION:
                    template_nodes.append(child)

            # Map original IDs to cloned nodes
            clone_map: dict[str, GraphNode] = {}

            for orig in template_nodes:
                clone_id = self._resolver.build_instance_id(declaring_id, orig.id)
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
                # CUR-1353 Phase 11: tag in-repo clones with the current
                # repo's project name so the viewer's provenance row fires
                # uniformly for all INSTANCE nodes (cross-repo and in-repo
                # alike). The cross-repo path sets this in
                # FederatedGraph._instantiate_cross_repo_satisfies; without
                # this branch the viewer would silently skip the row for
                # in-repo Satisfies clones.
                if self._project_name:
                    clone.set_field("template_repo", self._project_name)
                # Implements: REQ-d00129-C
                # Copy parse_line fields from the original.
                if orig.get_field("parse_line") is not None:
                    clone.set_field("parse_line", orig.get_field("parse_line"))
                if orig.get_field("parse_end_line") is not None:
                    clone.set_field("parse_end_line", orig.get_field("parse_end_line"))

                self._nodes[clone_id] = clone
                clone_map[orig.id] = clone

                # INSTANCE edge from clone to original
                clone.link(orig, EdgeKind.INSTANCE)

            # Implements: REQ-d00128-K
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

            # Implements: REQ-d00128-J
            # DEFINES edges run from the declaring FILE to the INSTANCE nodes.
            declaring_file = declaring_node.file_node()
            if declaring_file:
                for clone in clone_map.values():
                    declaring_file.link(clone, EdgeKind.DEFINES)

    # Implements: REQ-p00014-G
    def _validate_template_marker_consistency(self) -> None:
        """Validate template-marker rules that need full graph context.

        Phase 2 of CUR-1353: walk the graph after link resolution and emit
        typed ``ReferenceFault`` diagnostics for templates that violate
        the static validation matrix.

        Rule 7: A REQ marked ``**Template**`` may not declare behavioural
        claims (``Implements:`` or ``Refines:`` metadata) targeting ANY
        node. Templates are single-REQ scope -- they are pure specs with
        no descendants, so any outbound behavioural metadata is invalid.

        We use the parsed-and-stored ``implements_refs`` / ``refines_refs``
        on each TEMPLATE REQ to identify the original declarations.

        Rule 3/4/5/6/8 are detected in the link-resolution loop where we
        have access to the would-be edge before it lands; they do not need
        a post-pass.
        """
        for node_id, node in list(self._nodes.items()):
            if node.kind != NodeKind.REQUIREMENT:
                continue
            if node.get_field("stereotype") != Stereotype.TEMPLATE:
                continue
            # Rule 7: a template declared behavioural metadata.
            for ref_id in node.get_field("implements_refs") or []:
                self._emit_template_metadata_diagnostic(node_id, ref_id, EdgeKind.IMPLEMENTS)
            for ref_id in node.get_field("refines_refs") or []:
                self._emit_template_metadata_diagnostic(node_id, ref_id, EdgeKind.REFINES)

    def _emit_template_metadata_diagnostic(
        self, template_id: str, ref_id: str, edge_kind: EdgeKind
    ) -> None:
        """Emit rule-7 broken-ref for any behavioural metadata on a TEMPLATE.

        Single-REQ scope (CUR-1353): templates are pure specs with no
        descendants, so any outbound Implements/Refines is invalid --
        including targeting another template.
        """
        # Expand multi-assertion refs (e.g. REQ-X-A+B+C) to base targets.
        for expanded in self._expand_multi_assertion(ref_id):
            self._broken_references.append(
                ReferenceFault(
                    source_id=template_id,
                    target_id=expanded,
                    edge_kind=edge_kind.value,
                    fault_class=FaultClass.FORBIDDEN,
                    diagnostic=(
                        f"Templates are pure specs; remove "
                        f"behavioural-claim metadata or remove the "
                        f"**Template** flag on {template_id}."
                    ),
                )
            )

    # Implements: REQ-d00254-G, REQ-d00256
    def _step_scope_tests(self, result_node: GraphNode, source_file: str) -> list[GraphNode]:
        """Resolve a source-matched RESULT to its step's verifying TEST(s).

        A journey-step testcase name embeds the step id (``<journey>/N``,
        e.g. ``… › JNY-ENROLL-01/1: reach …``). When exactly one distinct
        step id is present and resolves to a STEP node, return that step's
        VERIFIES targets (TEST nodes) whose FILE matches the result's
        ``source_file`` — the precise binding that makes each step show only
        its own result. Returns [] when no unambiguous step binding exists
        (caller falls through to location/file scope).
        """
        from elspais.graph.parsers.patterns import JOURNEY_REF_PATTERN

        text = f"{result_node.get_field('classname') or ''} {result_node.get_field('name') or ''}"
        step_ids = {ref for ref in JOURNEY_REF_PATTERN.findall(text) if "/" in ref}
        if len(step_ids) != 1:
            return []
        step = self._nodes.get(next(iter(step_ids)))
        if step is None or step.kind is not NodeKind.STEP:
            return []
        tests: list[GraphNode] = []
        for edge in step.iter_edges_by_kind(EdgeKind.VERIFIES):
            test_node = edge.target  # target = the verifying test
            if test_node.kind is not NodeKind.TEST:
                continue
            file_node = test_node.file_node()
            rel = file_node.get_field("relative_path") if file_node else None
            if rel == source_file:
                tests.append(test_node)
        return tests

    def build(self) -> TraceGraph:
        """Build the final TraceGraph.

        Resolves all pending links and identifies root nodes.
        Also detects orphaned nodes and broken references.

        Returns:
            Complete TraceGraph with detection data populated.
        """
        # Phase 2: Instantiate templates before resolving links
        self._instantiate_satisfies_templates()

        # Expand multi-assertion references before resolving. Salvage
        # reaches inside a multi-assertion item the same as anywhere else
        # (REQ-d00269-G): each label is resolved on its own, so A+Z binds A
        # and reports only Z. But a verdict keyed on the item's whole raw
        # text (REQ-d00269-G: only the raw item is ever a verdict key) is
        # not only present when nothing about it matched at all --
        # DUPLICATE_ITEM is a verdict on an item that matched perfectly
        # (REQ-d00272-K), and ``_resolver.parse()`` succeeds on it, same as
        # any other duplicate. Expanding a verdicted item would scatter that
        # verdict across labels the reader never computed one for and lose
        # it entirely -- the expanded labels don't match the raw-text
        # verdict key, so they would fall through to ordinary node lookup
        # and bind. A verdicted item is therefore kept whole, unexpanded, so
        # its one verdict resolves to one link that reports (or refuses to
        # bind) the item exactly as the reader classified it.
        expanded_links: list[
            tuple[str, str, EdgeKind, dict[tuple[str, str], tuple[FaultClass, tuple[str, ...]]]]
        ] = []
        for source_id, target_id, edge_kind, verdicts in self._pending_links:
            if (edge_kind.value, target_id) in verdicts:
                expanded_links.append((source_id, target_id, edge_kind, verdicts))
                continue
            for resolved_target in self._expand_multi_assertion(target_id):
                expanded_links.append((source_id, resolved_target, edge_kind, verdicts))

        # Resolve pending links. Track which (source, target, kind) refs
        # actually became edges so the stored ref fields can be re-scoped to
        # unresolved leftovers afterwards (REQ-d00132-F, REQ-d00132-G).
        resolved_refs: set[tuple[str, str, str]] = set()
        for source_id, target_id, edge_kind, verdicts in expanded_links:
            source = self._nodes.get(source_id)
            # A verdict Task 3's reader carried for this raw item (an
            # unmatched item's grammar-level class, or a repeated target's
            # DUPLICATE_ITEM) already answers whether it may bind -- and the
            # answer is always no. Node lookup must not override that: a
            # duplicate's raw text is a real reference's own spelling (that
            # is what makes it a duplicate rather than a typo), so
            # ``self._nodes.get(target_id)`` finds the real node and would
            # bind it were this check skipped (REQ-d00272-K).
            target = (
                None if (edge_kind.value, target_id) in verdicts else self._nodes.get(target_id)
            )

            if source and target:
                # Implements: REQ-p00014-G
                # CUR-1353 Phase 2 validation matrix: reject invalid edge
                # combinations BEFORE creating the edge so the graph never
                # contains structurally-inconsistent traceability.
                target_stereotype = target.get_field("stereotype")
                if edge_kind == EdgeKind.REFINES and target_stereotype == Stereotype.TEMPLATE:
                    # Rules 3 and 8 describe the same illegal edge from two
                    # perspectives (source: "don't refine templates"; target:
                    # "templates have no descendants"). Emit a SINGLE broken-ref
                    # so one mistake reads as one error — and name the remedy
                    # (Satisfies:) plainly, since the bare "(refines)" line plus a
                    # passing refines_resolve check is what misleads authors.
                    self._broken_references.append(
                        ReferenceFault(
                            source_id=source_id,
                            target_id=target_id,
                            edge_kind=edge_kind.value,
                            fault_class=FaultClass.FORBIDDEN,
                            diagnostic=(
                                f"{target_id} is a Template: target it with "
                                f"Satisfies:, not Refines:. To add detail, "
                                f"Satisfies: the template and Refines: a "
                                f"concrete REQ in your own repo."
                            ),
                        )
                    )
                    continue
                if edge_kind == EdgeKind.REFINES and target_stereotype == Stereotype.INSTANCE:
                    # Rule 4: refining instance content is not supported.
                    self._broken_references.append(
                        ReferenceFault(
                            source_id=source_id,
                            target_id=target_id,
                            edge_kind=edge_kind.value,
                            fault_class=FaultClass.FORBIDDEN,
                            diagnostic=(
                                "Refining instance content is not supported. "
                                "Instance subtrees are read-only synthetic "
                                "content with no canonical on-disk identifier. "
                                "To add detail, Satisfies: the template AND "
                                "Refines: a concrete REQ in your own repo."
                            ),
                        )
                    )
                    continue
                if edge_kind == EdgeKind.IMPLEMENTS and target_stereotype == Stereotype.INSTANCE:
                    # Rule 5: composite IDs are not authoring syntax.
                    self._broken_references.append(
                        ReferenceFault(
                            source_id=source_id,
                            target_id=target_id,
                            edge_kind=edge_kind.value,
                            fault_class=FaultClass.FORBIDDEN,
                            diagnostic=(
                                "Instance assertions have no canonical "
                                "on-disk identifier; target the template "
                                "assertion directly or add a concrete "
                                "assertion to your satisfier."
                            ),
                        )
                    )
                    continue
                if edge_kind == EdgeKind.VERIFIES and target_stereotype == Stereotype.INSTANCE:
                    # Rule 6: same reasoning as rule 5, TEST source.
                    self._broken_references.append(
                        ReferenceFault(
                            source_id=source_id,
                            target_id=target_id,
                            edge_kind=edge_kind.value,
                            fault_class=FaultClass.FORBIDDEN,
                            diagnostic=(
                                "Instance assertions have no canonical "
                                "on-disk identifier; target the template "
                                "assertion directly or add a concrete "
                                "assertion to your satisfier."
                            ),
                        )
                    )
                    continue
                if edge_kind in (EdgeKind.IMPLEMENTS, EdgeKind.REFINES) and target.kind in (
                    NodeKind.USER_JOURNEY,
                    NodeKind.STEP,
                ):
                    # Journeys and steps are verification targets only; rejecting
                    # Implements/Refines here prevents invalid traceability edges.
                    self._broken_references.append(
                        ReferenceFault(
                            source_id=source_id,
                            target_id=target_id,
                            edge_kind=edge_kind.value,
                            fault_class=FaultClass.FORBIDDEN,
                            diagnostic=(
                                "Journeys and steps are only valid as "
                                "`Verifies:` targets, not Implements/Refines."
                            ),
                        )
                    )
                    continue

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

                resolved_refs.add((source_id, target_id, edge_kind.value))

                # Store implementation line range on IMPLEMENTS/VERIFIES edges
                if edge_kind in (EdgeKind.IMPLEMENTS, EdgeKind.VERIFIES):
                    impl_start = source.get_field("function_line") or source.get_field("parse_line")
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
                # Broken reference: target doesn't exist. Consult the
                # verdict Task 3's reader carried for this item first; only
                # an item no grammar accounted for has one, so a target that
                # matched but names no node here falls back to the
                # resolution-stage decision (REQ-p00014-R).
                fault_class, codes = self._fault_verdict(target_id, edge_kind.value, verdicts)
                self._broken_references.append(
                    ReferenceFault(
                        source_id=source_id,
                        target_id=target_id,
                        edge_kind=edge_kind.value,
                        fault_class=fault_class,
                        codes=codes,
                    )
                )

        # Implements: REQ-d00254-G
        # Resolve source RESULT->TEST links. These reporters (e.g. flutter-
        # machine) carry no test_id, so each result is wired by source path,
        # most-precise scope first:
        #   step-scope: the testcase name embeds a journey-step id
        #     (``<journey>/N``); bind to the TEST(s) that VERIFIES that STEP
        #     in the same source file, match_scope="step". Needs no line attr.
        #   test-scope: the single TEST at (source_file, line),
        #     match_scope="test" (per-test crediting).
        #   file-scope: fall back to every TEST sharing the file,
        #     match_scope="file" (the file-level all-pass/any-fail crediting
        #     the annotator's source_file_index applies).
        # An unmatched file links nothing (no broken reference, unlike test_id
        # resolution). Done before orphan/root classification so RESULT nodes
        # count as YIELDS-parented, exactly like test_id-based YIELDS edges.
        if self._pending_source_result_links:
            tests_by_file: dict[str, list[GraphNode]] = {}
            tests_by_file_line: dict[tuple[str, int], GraphNode] = {}
            for candidate in self._nodes.values():
                if candidate.kind is not NodeKind.TEST:
                    continue
                file_node = candidate.file_node()
                rel = file_node.get_field("relative_path") if file_node else None
                if not rel:
                    continue
                tests_by_file.setdefault(rel, []).append(candidate)
                pl = candidate.get_field("parse_line")
                if pl:
                    tests_by_file_line[(rel, pl)] = candidate
            for (
                result_id,
                source_file,
                line,
                root_file,
                root_line,
            ) in self._pending_source_result_links:
                result_node = self._nodes.get(result_id)
                if result_node is None:
                    continue
                # Attempt 0: step-scope match via the step id embedded in the
                # testcase name (REQ-d00254-G / REQ-d00256).
                step_tests = self._step_scope_tests(result_node, source_file)
                if step_tests:
                    for test_node in step_tests:
                        test_node.link(result_node, EdgeKind.YIELDS)
                    result_node.set_field("match_scope", "step")
                    continue
                # Attempt 1: primary (source_file, line) match
                target = tests_by_file_line.get((source_file, line)) if line is not None else None
                if target is None and root_line is not None:
                    # Attempt 2: root fallback for testWidgets() whose test.line
                    # is a framework wrapper line (REQ-d00254-G).
                    target = tests_by_file_line.get((root_file or source_file, root_line))
                if target is not None:
                    target.link(result_node, EdgeKind.YIELDS)
                    result_node.set_field("match_scope", "test")
                else:
                    for test_node in tests_by_file.get(source_file, ()):
                        test_node.link(result_node, EdgeKind.YIELDS)
                    result_node.set_field("match_scope", "file")

        # Phase 2.5 (CUR-1353): Validate template-marker consistency over the
        # fully-resolved graph. Catches rules that need post-link context
        # (currently rule 7: template REQs declaring behavioural metadata).
        self._validate_template_marker_consistency()

        # Implements: REQ-d00132-F, REQ-d00132-G
        # Re-scope the stored implements/refines fields to unresolved
        # leftovers only. Refs that became edges are stripped — the render
        # derives them from the live edges, so edge mutations (including
        # deleting the LAST edge of a kind) are reflected in the output.
        # Refs that never resolved stay stored so a rewrite cannot silently
        # delete an author's broken reference. Multi-assertion refs keep
        # only their unresolved expansions. Must run AFTER
        # _validate_template_marker_consistency(), which reads the raw
        # parsed fields.
        for node in self._nodes.values():
            if node.kind != NodeKind.REQUIREMENT:
                continue
            for ref_kind, field_name in (
                (EdgeKind.IMPLEMENTS, "implements_refs"),
                (EdgeKind.REFINES, "refines_refs"),
            ):
                stored_refs = node.get_field(field_name)
                if not stored_refs:
                    continue
                leftovers = [
                    expanded
                    for ref in stored_refs
                    for expanded in self._expand_multi_assertion(ref)
                    if (node.id, expanded, ref_kind.value) not in resolved_refs
                ]
                node.set_field(field_name, leftovers)

        # Implements: REQ-d00071-A, REQ-d00071-B
        # Compute orphan candidates from graph structure instead of tracking
        # incrementally. A content node (not FILE, REMAINDER, ASSERTION) is an
        # orphan candidate if it has no content-level parent edges — i.e. no
        # incoming IMPLEMENTS, REFINES, VERIFIES, VALIDATES, or YIELDS edges.
        # CONTAINS edges (from FILE nodes) don't count as content-level links.
        # Roots: parentless REQUIREMENTs (always), or other parentless nodes
        #        with at least one meaningful (non-satellite) child.
        # Orphans: parentless non-REQUIREMENT nodes without meaningful children.
        # Implements: REQ-d00128-I
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
            _resolver=self._resolver,
            _namespace=self._namespace,
        )
        graph._roots = roots
        graph._index = dict(self._nodes)
        graph._orphaned_ids = orphaned_ids
        graph._broken_references = list(self._broken_references)
        graph._style_findings = list(self._style_findings)
        graph._undeclared_relationships = list(self._undeclared_relationships)
        graph._identifier_form_findings = list(self._identifier_form_findings)
        graph._duplicate_req_ids = {k: list(v) for k, v in self._duplicate_req_ids.items()}

        # Implements: REQ-d00222-A, REQ-d00222-B
        # Populate _terms from pending definition data, resolving defined_in
        for node_id, data in self._pending_terms:
            node = self._nodes.get(node_id)
            if not node:
                continue
            # Resolve defined_in: walk up to nearest REQUIREMENT or FILE ancestor
            defined_in = ""
            if node:
                for ancestor in node.ancestors():
                    if ancestor.kind == NodeKind.REQUIREMENT:
                        defined_in = ancestor.id
                        break
                    if ancestor.kind == NodeKind.FILE:
                        defined_in = ancestor.id
                        break
            ref_fields = data.get("reference_fields", {})
            entry = TermEntry(
                term=data.get("term", ""),
                definition=data.get("definition", ""),
                collection=data.get("collection", False),
                indexed=data.get("indexed", True),
                defined_in=defined_in,
                defined_at_line=data.get("line", 0),
                namespace=self._namespace,
                is_reference=data.get("is_reference", False),
                reference_fields=ref_fields,
                reference_term=data.get("reference_term", ""),
                reference_source=data.get("reference_source", ""),
                definition_hash=compute_definition_hash(
                    data.get("definition", ""),
                    reference_fields=ref_fields or None,
                ),
            )
            graph._terms.add(entry)

        return graph
