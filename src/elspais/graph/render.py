# Implements: REQ-d00131-A, REQ-d00131-B, REQ-d00131-C, REQ-d00131-D
# Implements: REQ-d00131-E, REQ-d00131-F, REQ-d00131-G, REQ-d00131-H
# Implements: REQ-d00131-I, REQ-d00131-J
# Implements: REQ-d00132-A, REQ-d00132-E, REQ-d00132-F
"""Render Protocol - Serialize graph nodes back to text.

Each domain NodeKind has a render function that produces its text
representation. Walking a FILE node's CONTAINS children in render_order
and concatenating their rendered output produces the file's content.

The render_save() function persists dirty FILE nodes to disk by rendering
their CONTAINS children, replacing the old persistence.py text surgery.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from elspais.graph.GraphNode import GraphNode, NodeKind
from elspais.graph.relations import EdgeKind
from elspais.utilities.hasher import compute_normalized_hash

if TYPE_CHECKING:
    from elspais.graph.federated import FederatedGraph


def render_node(node: GraphNode) -> str:
    """Render a graph node back to its text representation.

    Dispatches to the appropriate renderer based on NodeKind.

    Args:
        node: The graph node to render.

    Returns:
        The text representation of the node.

    Raises:
        ValueError: If the node kind cannot be rendered independently
            (ASSERTION, TEST_RESULT).
    """
    # Implements: REQ-d00131-A
    kind = node.kind

    if kind == NodeKind.REQUIREMENT:
        return _render_requirement(node)
    elif kind == NodeKind.ASSERTION:
        # Implements: REQ-d00131-C
        raise ValueError(
            "ASSERTION nodes are rendered by their parent REQUIREMENT, "
            "not independently. Use render_node() on the parent REQUIREMENT."
        )
    elif kind == NodeKind.REMAINDER:
        return _render_remainder(node)
    elif kind == NodeKind.USER_JOURNEY:
        return _render_journey(node)
    elif kind == NodeKind.CODE:
        return _render_code(node)
    elif kind == NodeKind.TEST:
        return _render_test(node)
    elif kind == NodeKind.TEST_RESULT:
        # Implements: REQ-d00131-H
        raise ValueError("TEST_RESULT nodes are read-only and cannot be rendered back to disk.")
    elif kind == NodeKind.FILE:
        return render_file(node)
    else:
        raise ValueError(f"Unknown NodeKind: {kind}")


# Implements: REQ-d00131-B
def _render_requirement(node: GraphNode) -> str:
    """Render a REQUIREMENT node to its full text block.

    Produces:
    - Header line: ## REQ-xxx: Title
    - Metadata line: **Level**: X | **Status**: Y | **Implements**: Z
    - Preamble body text (from STRUCTURES REMAINDER children with heading="preamble")
    - ## Assertions heading + assertion lines (from STRUCTURES ASSERTION children)
    - Non-normative sections (from STRUCTURES REMAINDER children)
    - *End* marker with hash
    - --- separator
    """
    req_id = node.id
    title = node.get_label()
    level = node.get_field("level") or "Unknown"
    status = node.get_field("status") or "Unknown"

    # Implements: REQ-d00132-F
    # Derive implements refs from live graph edges, falling back to stored field
    implements_refs = _derive_implements_refs(node)
    refines_refs = _derive_refines_refs(node)
    satisfies_refs = node.get_field("satisfies_refs") or []

    lines: list[str] = []

    # Header (preserve original heading level)
    heading_prefix = "#" * (node.get_field("heading_level") or 2)
    lines.append(f"{heading_prefix} {req_id}: {title}")
    lines.append("")

    # Metadata line
    meta_parts = [f"**Level**: {level}", f"**Status**: {status}"]
    if implements_refs:
        impl_str = ", ".join(implements_refs)
        meta_parts.append(f"**Implements**: {impl_str}")
    else:
        meta_parts.append("**Implements**: -")
    lines.append(" | ".join(meta_parts))

    # Refines line (if present)
    if refines_refs:
        refines_str = ", ".join(refines_refs)
        lines.append(f"**Refines**: {refines_str}")

    # Satisfies line (if present)
    if satisfies_refs:
        sat_str = ", ".join(satisfies_refs)
        lines.append(f"Satisfies: {sat_str}")

    # Walk STRUCTURES children in document order (insertion order preserves
    # line-number sorting done during build). Collect assertions for hashing
    # while rendering sections in their original order.
    assertions: list[tuple[str, str]] = []
    in_assertions = False

    for child in node.iter_children(edge_kinds={EdgeKind.STRUCTURES}):
        if child.kind == NodeKind.ASSERTION:
            label = child.get_field("label") or ""
            text = child.get_label()
            assertions.append((label, text))
            if not in_assertions:
                if lines and lines[-1] != "":
                    lines.append("")
                lines.append("## Assertions")
                lines.append("")
                in_assertions = True
            lines.append(f"{label}. {text}")
            lines.append("")
        elif child.kind == NodeKind.REMAINDER:
            in_assertions = False
            heading = child.get_field("heading") or "preamble"
            content = child.get_field("text") or ""
            if heading == "preamble":
                if content:
                    lines.append("")
                    lines.append(content)
            else:
                # Ensure blank line before heading (unless previous line is
                # already blank, e.g. after the last assertion)
                if lines and lines[-1] != "":
                    lines.append("")
                lines.append(f"## {heading}")
                lines.append("")
                lines.append(content)
                lines.append("")

    # Compute hash using canonical hasher (DRY: utilities/hasher.py)
    hash_val = compute_normalized_hash(assertions)

    # End marker (separator is a REMAINDER node, not part of the requirement)
    lines.append(f"*End* *{title}* | **Hash**: {hash_val}")

    return "\n".join(lines)


# Implements: REQ-d00131-D
def _render_remainder(node: GraphNode) -> str:
    """Render a REMAINDER node back to its raw text.

    Returns the stored text verbatim, preserving all whitespace.
    """
    return node.get_field("text") or ""


# Implements: REQ-d00131-E
def _render_journey(node: GraphNode) -> str:
    """Render a USER_JOURNEY node back to its full block.

    Returns the stored body text which contains the complete journey block.
    """
    return node.get_field("body") or ""


# Implements: REQ-d00131-F
def _render_code(node: GraphNode) -> str:
    """Render a CODE node back to its comment line(s).

    Returns the raw text of the # Implements: comment line(s).
    """
    return node.get_field("raw_text") or ""


# Implements: REQ-d00131-G
def _render_test(node: GraphNode) -> str:
    """Render a TEST node back to its comment line(s).

    Returns the raw text of the # Tests: / # Validates: comment line(s).
    """
    return node.get_field("raw_text") or ""


# Implements: REQ-d00131-I
def render_file(node: GraphNode) -> str:
    """Render a FILE node by walking its CONTAINS children.

    Walks CONTAINS children sorted by render_order edge metadata,
    calls render_node on each, and concatenates the results.

    Args:
        node: A FILE node.

    Returns:
        The complete file content as a string.
    """
    if node.kind != NodeKind.FILE:
        raise ValueError(f"render_file() requires a FILE node, got {node.kind}")

    # Collect CONTAINS children with their render_order
    children_with_order: list[tuple[float, GraphNode]] = []

    for edge in node.iter_outgoing_edges():
        if edge.kind == EdgeKind.CONTAINS:
            order = edge.metadata.get("render_order", 0.0)
            children_with_order.append((order, edge.target))

    if not children_with_order:
        return ""

    # Sort by render_order
    children_with_order.sort(key=lambda x: x[0])

    # Render each child and concatenate
    parts: list[str] = []
    for _order, child in children_with_order:
        rendered = render_node(child)
        if rendered:
            parts.append(rendered)

    return "\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────
# Edge-derived reference lists (REQ-d00132-F)
# ─────────────────────────────────────────────────────────────────────────


def _derive_implements_refs(node: GraphNode) -> list[str]:
    """Derive the implements reference list from live graph edges.

    Walks incoming IMPLEMENTS edges where the source is a REQUIREMENT,
    producing the list of parent IDs. Falls back to stored
    ``implements_refs`` field when no edges are found (e.g., nodes
    created by mutations that haven't been wired yet).

    Returns:
        Sorted list of implements reference IDs.
    """
    refs: set[str] = set()
    for edge in node.iter_incoming_edges():
        if edge.kind == EdgeKind.IMPLEMENTS and edge.source.kind == NodeKind.REQUIREMENT:
            if edge.assertion_targets:
                for label in edge.assertion_targets:
                    refs.add(f"{edge.source.id}-{label}")
            else:
                refs.add(edge.source.id)

    if refs:
        return sorted(refs)

    # Fallback to stored field
    stored = node.get_field("implements_refs")
    return list(stored) if stored else []


def _derive_refines_refs(node: GraphNode) -> list[str]:
    """Derive the refines reference list from live graph edges.

    Same as ``_derive_implements_refs`` but for REFINES edges.

    Returns:
        Sorted list of refines reference IDs.
    """
    refs: set[str] = set()
    for edge in node.iter_incoming_edges():
        if edge.kind == EdgeKind.REFINES and edge.source.kind == NodeKind.REQUIREMENT:
            if edge.assertion_targets:
                for label in edge.assertion_targets:
                    refs.add(f"{edge.source.id}-{label}")
            else:
                refs.add(edge.source.id)

    if refs:
        return sorted(refs)

    # Fallback to stored field
    stored = node.get_field("refines_refs")
    return list(stored) if stored else []


# ─────────────────────────────────────────────────────────────────────────
# Render-based save (REQ-d00132-A)
# ─────────────────────────────────────────────────────────────────────────


def _find_dirty_files(graph: FederatedGraph, resolver: Any | None = None) -> set[str]:
    """Identify FILE node IDs whose subtree has pending mutations.

    Walks the mutation log and for each mutated node, finds its FILE
    ancestor. Returns the set of FILE node IDs that need re-rendering.

    Handles deleted nodes by looking up parent requirement IDs from
    the mutation entry's before_state.

    Args:
        graph: The traceability graph with pending mutations.

    Returns:
        Set of FILE node IDs that contain mutated content.
    """
    dirty_file_ids: set[str] = set()

    def _mark_node_file(node_id: str) -> None:
        """Find the FILE ancestor of a node and mark it dirty."""
        node = graph.find_by_id(node_id)
        if node is None:
            return
        if node.kind == NodeKind.FILE:
            dirty_file_ids.add(node.id)
        else:
            fn = node.file_node()
            if fn is not None:
                dirty_file_ids.add(fn.id)

    for entry in graph.mutation_log.iter_entries():
        target_id = entry.target_id

        # Try to find the node directly
        _mark_node_file(target_id)

        # For operations that reference source_id (edges, refs)
        for key in ("source_id",):
            ref_id = entry.before_state.get(key) or entry.after_state.get(key, "")
            if ref_id:
                _mark_node_file(ref_id)

        # For assertion mutations, find the parent requirement's file
        if entry.operation in (
            "add_assertion",
            "delete_assertion",
            "update_assertion",
            "rename_assertion",
        ):
            parent_id = entry.before_state.get("parent_id") or entry.after_state.get(
                "parent_id", ""
            )
            if parent_id:
                _mark_node_file(parent_id)
            else:
                # Derive parent from assertion ID (REQ-xxx-A -> REQ-xxx)
                split = resolver.split_assertion_ref(target_id) if resolver else None
                if split is None and "-" in target_id:
                    parts = target_id.rsplit("-", 1)
                    if len(parts) == 2:
                        split = (parts[0], parts[1])
                if split:
                    _mark_node_file(split[0])

        # For add_requirement, the target file is the parent's file
        if entry.operation == "add_requirement":
            parent_id = entry.after_state.get("parent_id")
            if parent_id:
                _mark_node_file(parent_id)

        # For delete_requirement, use the stored source_path
        if entry.operation == "delete_requirement":
            source_path = entry.before_state.get("source_path")
            if source_path:
                file_id = f"file:{source_path}"
                if graph.find_by_id(file_id) is not None:
                    dirty_file_ids.add(file_id)
            # Also try parent IDs from before_state
            for pid in entry.before_state.get("parent_ids", []):
                _mark_node_file(pid)

        # For rename_node, both old and new locations
        if entry.operation == "rename_node":
            new_id = entry.after_state.get("id", "")
            if new_id:
                _mark_node_file(new_id)

        # For change_status, update_title - node should still exist
        if entry.operation in ("change_status", "update_title"):
            _mark_node_file(target_id)

        # For edge mutations - mark the source requirement
        if entry.operation in (
            "add_edge",
            "delete_edge",
            "change_edge_kind",
            "change_edge_targets",
        ):
            source_id = entry.before_state.get("source_id") or entry.after_state.get(
                "source_id", ""
            )
            if source_id:
                _mark_node_file(source_id)

        # For move_node_to_file - mark both old and new file
        if entry.operation == "move_node_to_file":
            old_file = entry.before_state.get("file_id", "")
            new_file = entry.after_state.get("file_id", "")
            if old_file:
                dirty_file_ids.add(old_file)
            if new_file:
                dirty_file_ids.add(new_file)

        # For rename_file - mark the new file ID (old ID no longer exists)
        if entry.operation == "rename_file":
            new_file_id = entry.after_state.get("id", "")
            if new_file_id:
                dirty_file_ids.add(new_file_id)

    return dirty_file_ids


# Implements: REQ-d00132-A, REQ-d00132-C
def render_save(
    graph: FederatedGraph,
    repo_root: Path,
    consistency_check: bool = False,
    rebuild_fn: Any | None = None,
    resolver: Any | None = None,
) -> dict[str, Any]:
    """Persist dirty FILE nodes to disk by rendering their CONTAINS children.

    Identifies FILE nodes with pending mutations, renders each one's
    content by walking CONTAINS children in render_order, and writes
    the result to disk.

    Args:
        graph: The traceability graph with pending mutations.
        repo_root: Repository root path for resolving relative paths.
        consistency_check: If True, rebuild graph from disk after save and
            compare to pre-save state. Requires rebuild_fn.
        rebuild_fn: Callable that rebuilds a TraceGraph from disk, returning
            (result_dict, TraceGraph). Required when consistency_check=True.

    Returns:
        Dict with:
        - success: bool
        - saved_count: number of files written
        - files_modified: list of modified file paths
        - errors: list of error messages (if any)
        - skipped: list of skipped descriptions
        - consistency: dict with check results (when consistency_check=True)
    """
    errors: list[str] = []
    files_modified: set[str] = set()
    skipped: list[str] = []
    saved_count = 0

    # Ensure new requirements are wired to FILE nodes before rendering
    _wire_new_requirements_to_files(graph)

    # Find dirty FILE nodes
    dirty_file_ids = _find_dirty_files(graph, resolver=resolver)

    if not dirty_file_ids:
        # No dirty files — clear log and return
        graph.mutation_log.clear()
        return {
            "success": True,
            "saved_count": 0,
            "files_modified": [],
            "conflicts": [],
            "errors": [],
            "skipped": ["No dirty files to save"],
        }

    # Handle file renames on disk before rendering
    for entry in graph.mutation_log.iter_entries():
        if entry.operation == "rename_file":
            old_rel = entry.before_state.get("relative_path", "")
            new_rel = entry.after_state.get("relative_path", "")
            if old_rel and new_rel:
                old_path = repo_root / old_rel
                new_path = repo_root / new_rel
                if old_path.exists() and not new_path.exists():
                    new_path.parent.mkdir(parents=True, exist_ok=True)
                    old_path.rename(new_path)

    # Render and write each dirty FILE
    for file_id in sorted(dirty_file_ids):
        file_node = graph.find_by_id(file_id)
        if file_node is None or file_node.kind != NodeKind.FILE:
            skipped.append(f"{file_id}: FILE node not found")
            continue

        rel_path = file_node.get_field("relative_path")
        if not rel_path:
            skipped.append(f"{file_id}: no relative_path")
            continue

        abs_path = Path(rel_path)
        if not abs_path.is_absolute():
            abs_path = repo_root / rel_path

        try:
            content = render_file(file_node)
            # Ensure file ends with newline
            if content and not content.endswith("\n"):
                content += "\n"
            abs_path.write_text(content, encoding="utf-8")
            files_modified.add(str(abs_path))
            saved_count += 1
        except Exception as e:
            errors.append(f"{file_id}: {e}")

    # Implements: REQ-d00132-E
    # Clear mutation log after successful save
    if not errors:
        graph.mutation_log.clear()

    result: dict[str, Any] = {
        "success": len(errors) == 0,
        "saved_count": saved_count,
        "files_modified": sorted(files_modified),
        "conflicts": [],
        "errors": errors,
        "skipped": skipped,
    }

    # Implements: REQ-d00132-C
    # Consistency check: rebuild graph from disk and compare
    if consistency_check and not errors and rebuild_fn is not None and saved_count > 0:
        consistency = _run_consistency_check(graph, rebuild_fn)
        result["consistency"] = consistency
        if not consistency.get("consistent", True):
            result["errors"].append(
                f"Consistency check failed: {consistency.get('details', 'unknown')}"
            )
            result["success"] = False

    return result


def _run_consistency_check(
    original_graph: FederatedGraph,
    rebuild_fn: Any,
) -> dict[str, Any]:
    """Run consistency check by rebuilding graph from disk and comparing.

    Rebuilds the graph from the files on disk and compares requirement IDs,
    assertion IDs, titles, statuses, and edge relationships to the in-memory
    graph.

    Args:
        original_graph: The in-memory graph after mutations.
        rebuild_fn: Callable returning (result_dict, TraceGraph).

    Returns:
        Dict with:
        - consistent: bool
        - details: str (if inconsistent)
        - checked: int (number of nodes compared)
    """
    # Implements: REQ-d00132-C
    try:
        rebuild_result, new_graph = rebuild_fn()
    except Exception as e:
        return {"consistent": False, "details": f"Rebuild failed: {e}", "checked": 0}

    if new_graph is None:
        return {"consistent": False, "details": "Rebuild returned None graph", "checked": 0}

    # Compare requirement nodes
    mismatches: list[str] = []
    checked = 0

    for node in original_graph.nodes_by_kind(NodeKind.REQUIREMENT):
        checked += 1
        new_node = new_graph.find_by_id(node.id)
        if new_node is None:
            mismatches.append(f"Missing node: {node.id}")
            continue

        # Compare title
        if node.get_label() != new_node.get_label():
            mismatches.append(f"{node.id} title: '{node.get_label()}' vs '{new_node.get_label()}'")

        # Compare status
        old_status = node.get_field("status")
        new_status = new_node.get_field("status")
        if old_status != new_status:
            mismatches.append(f"{node.id} status: '{old_status}' vs '{new_status}'")

        # Compare level
        old_level = node.get_field("level")
        new_level = new_node.get_field("level")
        if old_level != new_level:
            mismatches.append(f"{node.id} level: '{old_level}' vs '{new_level}'")

    # Compare assertion nodes
    for node in original_graph.nodes_by_kind(NodeKind.ASSERTION):
        checked += 1
        new_node = new_graph.find_by_id(node.id)
        if new_node is None:
            mismatches.append(f"Missing assertion: {node.id}")
            continue

        if node.get_label() != new_node.get_label():
            mismatches.append(f"{node.id} text: '{node.get_label()}' vs '{new_node.get_label()}'")

    if mismatches:
        details = "; ".join(mismatches[:10])
        if len(mismatches) > 10:
            details += f" ... and {len(mismatches) - 10} more"
        return {"consistent": False, "details": details, "checked": checked}

    return {"consistent": True, "checked": checked}


def _wire_new_requirements_to_files(graph: FederatedGraph) -> None:
    """Wire newly added requirements to their parent's FILE node.

    When add_requirement creates a new node, it links to a parent via
    IMPLEMENTS/REFINES but doesn't create a CONTAINS edge from a FILE.
    This function finds such orphaned requirements and wires them to
    the parent's FILE node.

    Args:
        graph: The traceability graph.
    """
    for entry in graph.mutation_log.iter_entries():
        if entry.operation != "add_requirement":
            continue

        req_id = entry.after_state.get("id", entry.target_id)
        node = graph.find_by_id(req_id)
        if node is None:
            continue

        # Check if already wired to a FILE via CONTAINS
        has_contains_from_file = False
        for edge in node.iter_incoming_edges():
            if edge.kind == EdgeKind.CONTAINS and edge.source.kind == NodeKind.FILE:
                has_contains_from_file = True
                break
        if has_contains_from_file:
            continue

        # Find parent's FILE node
        parent_id = entry.after_state.get("parent_id")
        if not parent_id:
            continue

        parent = graph.find_by_id(parent_id)
        if parent is None:
            continue

        fn = parent.file_node()
        if fn is None:
            continue

        # Wire CONTAINS edge with render_order after last existing child
        max_order = -1.0
        for edge in fn.iter_outgoing_edges():
            if edge.kind == EdgeKind.CONTAINS:
                order = edge.metadata.get("render_order", 0.0)
                if order > max_order:
                    max_order = order

        edge = fn.link(node, EdgeKind.CONTAINS)
        edge.metadata = {
            "render_order": max_order + 1.0,
        }
