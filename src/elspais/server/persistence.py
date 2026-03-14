# Implements: REQ-o00063-A, REQ-o00063-F, REQ-o00063-G, REQ-o00063-H, REQ-o00063-I
"""Persistence layer — replay in-memory mutations to spec files on disk.

Walks the graph's mutation log and calls the appropriate spec_writer
function for each mutation entry.  Supports all mutation types:

- **change_status**, **update_title** — surgical field replacement
- **update_assertion**, **add_assertion** — assertion text changes
- **delete_assertion**, **rename_assertion** — assertion structural changes
- **add_edge**, **delete_edge** — coalesced: reads current implements/refines
  lists from the live graph and writes once per affected requirement
- **change_edge_kind** — Implements ↔ Refines conversion
- **fix_broken_reference** — redirects a broken ref to a new target
- **rename_node** — renames header + all references across spec files
- **add_requirement** — appends a new requirement block to parent's file
- **delete_requirement** — removes a requirement block from its source file

Undo operations are correctly in-memory only; the disk always reflects
the post-undo graph state.

Public API
----------
- ``replay_mutations_to_disk`` — persist pending mutations
- ``check_for_external_changes`` — detect external edits since build time
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from elspais.graph.builder import TraceGraph
from elspais.graph.GraphNode import NodeKind
from elspais.graph.relations import EdgeKind
from elspais.utilities.spec_writer import (
    add_assertion_to_file,
    add_requirement_to_file,
    delete_assertion_from_file,
    delete_requirement_from_file,
    fix_reference_in_file,
    modify_assertion_text,
    modify_implements,
    modify_refines,
    modify_status,
    modify_title,
    rename_assertion_in_file,
    rename_references_in_file,
    rename_requirement_id,
)


def _get_source_path(graph: TraceGraph, node_id: str, repo_root: Path) -> Path | None:
    """Resolve the spec file path for a node.

    Looks up the node in the graph and returns its source file as an
    absolute path.  Returns None when the node cannot be found or has
    no source location.

    Args:
        graph: The traceability graph.
        node_id: Node ID to look up.
        repo_root: Repository root for resolving relative paths.

    Returns:
        Absolute Path to the spec file, or None.
    """
    # Implements: REQ-d00129-D
    node = graph.find_by_id(node_id)
    if node is None:
        return None
    _fn = node.file_node()
    if _fn is None:
        return None
    source_path = _fn.get_field("relative_path")
    if not source_path:
        return None
    p = Path(source_path)
    if p.is_absolute():
        return p
    return repo_root / p


def _get_req_id_from_assertion_id(assertion_id: str) -> tuple[str, str]:
    """Split an assertion ID into (req_id, label).

    Example: "REQ-p00001-A" -> ("REQ-p00001", "A")

    Args:
        assertion_id: Full assertion ID.

    Returns:
        Tuple of (requirement_id, label).
    """
    # Assertion IDs are formatted as REQ-xxx-LABEL where LABEL is the
    # last hyphen-separated component.
    parts = assertion_id.rsplit("-", 1)
    return parts[0], parts[1]


def _get_current_implements_list(graph: TraceGraph, req_id: str) -> list[str]:
    """Build the current implements list for a requirement from graph state.

    Reads all incoming edges to find parent requirements connected via
    IMPLEMENTS edges. Reconstructs assertion-qualified IDs when
    assertion_targets are present (e.g., REQ-p00001 with targets ["A"]
    becomes REQ-p00001-A).

    Args:
        graph: The traceability graph.
        req_id: Requirement ID to inspect.

    Returns:
        Sorted deduplicated list of parent reference IDs.
    """
    node = graph.find_by_id(req_id)
    if node is None:
        return []

    refs: set[str] = set()
    for edge in node.iter_incoming_edges():
        if edge.kind == EdgeKind.IMPLEMENTS and edge.source.kind == NodeKind.REQUIREMENT:
            if edge.assertion_targets:
                for label in edge.assertion_targets:
                    refs.add(f"{edge.source.id}-{label}")
            else:
                refs.add(edge.source.id)
    return sorted(refs)


def _get_current_refines_list(graph: TraceGraph, req_id: str) -> list[str]:
    """Build the current refines list for a requirement from graph state.

    Same as ``_get_current_implements_list`` but for REFINES edges.

    Args:
        graph: The traceability graph.
        req_id: Requirement ID to inspect.

    Returns:
        Sorted deduplicated list of parent reference IDs connected via REFINES.
    """
    node = graph.find_by_id(req_id)
    if node is None:
        return []

    refs: set[str] = set()
    for edge in node.iter_incoming_edges():
        if edge.kind == EdgeKind.REFINES and edge.source.kind == NodeKind.REQUIREMENT:
            if edge.assertion_targets:
                for label in edge.assertion_targets:
                    refs.add(f"{edge.source.id}-{label}")
            else:
                refs.add(edge.source.id)
    return sorted(refs)


def check_for_external_changes(
    graph: TraceGraph,
    repo_root: Path,
    build_time: float,
) -> list[str]:
    """Return spec files modified since build_time.

    Compares file mtime against build_time to detect external edits
    that would conflict with replaying mutations.

    Args:
        graph: The traceability graph.
        repo_root: Repository root path.
        build_time: Unix timestamp of the graph build.

    Returns:
        List of relative file paths that have been modified externally.
    """
    changed: list[str] = []
    seen: set[str] = set()

    # Implements: REQ-d00129-D
    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        _fn = node.file_node()
        if _fn is None:
            continue
        rel_path = _fn.get_field("relative_path") or ""
        if not rel_path:
            continue
        if rel_path in seen:
            continue
        seen.add(rel_path)

        abs_path = Path(rel_path)
        if not abs_path.is_absolute():
            abs_path = repo_root / rel_path

        if abs_path.exists():
            try:
                mtime = os.path.getmtime(abs_path)
                if mtime > build_time:
                    changed.append(rel_path)
            except OSError:
                pass

    return changed


def replay_mutations_to_disk(
    graph: TraceGraph,
    repo_root: Path,
    build_time: float | None = None,
) -> dict[str, Any]:
    """Walk the mutation log and replay each entry to spec files via spec_writer.

    For edge mutations (add_edge, delete_edge), instead of replaying
    incrementally, we build the FULL current implements list from the
    live graph state and write it once per affected requirement.

    Args:
        graph: The traceability graph with pending mutations.
        repo_root: Repository root path.
        build_time: Optional build timestamp for conflict detection.

    Returns:
        Dict with:
        - success: bool
        - saved_count: number of mutations replayed
        - files_modified: list of modified file paths
        - conflicts: list of externally modified files (if any)
        - errors: list of error messages (if any)
        - skipped: list of skipped mutation descriptions
    """
    errors: list[str] = []
    files_modified: set[str] = set()
    skipped: list[str] = []
    saved_count = 0

    # Check for external changes if build_time provided
    if build_time is not None:
        conflicts = check_for_external_changes(graph, repo_root, build_time)
        if conflicts:
            return {
                "success": False,
                "saved_count": 0,
                "files_modified": [],
                "conflicts": conflicts,
                "errors": [
                    f"External changes detected in {len(conflicts)} file(s). "
                    "Save aborted to prevent data loss."
                ],
                "skipped": [],
            }

    # Track which requirements need their implements list written
    # (coalescing edge mutations).
    edge_affected_reqs: set[str] = set()

    # Walk entries in chronological order
    for entry in graph.mutation_log.iter_entries():
        op = entry.operation

        if op == "change_status":
            node_id = entry.target_id
            new_status = entry.after_state.get("status") or entry.after_state.get("new_status", "")
            file_path = _get_source_path(graph, node_id, repo_root)
            if file_path is None:
                skipped.append(f"change_status({node_id}): no source file")
                continue
            result = modify_status(file_path, node_id, new_status)
            if result.get("success"):
                files_modified.add(str(file_path))
                saved_count += 1
            elif result.get("no_change"):
                saved_count += 1
            else:
                errors.append(f"change_status({node_id}): {result.get('error', 'unknown error')}")

        elif op == "update_title":
            node_id = entry.target_id
            new_title = entry.after_state.get("title") or entry.after_state.get("new_title", "")
            file_path = _get_source_path(graph, node_id, repo_root)
            if file_path is None:
                skipped.append(f"update_title({node_id}): no source file")
                continue
            result = modify_title(file_path, node_id, new_title)
            if result.get("success"):
                files_modified.add(str(file_path))
                saved_count += 1
            elif result.get("no_change"):
                saved_count += 1
            else:
                errors.append(f"update_title({node_id}): {result.get('error', 'unknown error')}")

        elif op == "update_assertion":
            assertion_id = entry.target_id
            new_text = entry.after_state.get("text") or entry.after_state.get("new_text", "")
            req_id, label = _get_req_id_from_assertion_id(assertion_id)
            file_path = _get_source_path(graph, req_id, repo_root)
            if file_path is None:
                skipped.append(f"update_assertion({assertion_id}): no source file")
                continue
            result = modify_assertion_text(file_path, req_id, label, new_text)
            if result.get("success"):
                files_modified.add(str(file_path))
                saved_count += 1
            elif result.get("no_change"):
                saved_count += 1
            else:
                errors.append(
                    f"update_assertion({assertion_id}): {result.get('error', 'unknown error')}"
                )

        elif op == "add_assertion":
            assertion_id = entry.target_id
            label = entry.after_state.get("label", "")
            text = entry.after_state.get("text", "")
            req_id = entry.before_state.get("parent_id") or entry.after_state.get("parent_id", "")
            if not req_id:
                req_id, _ = _get_req_id_from_assertion_id(assertion_id)
            file_path = _get_source_path(graph, req_id, repo_root)
            if file_path is None:
                skipped.append(f"add_assertion({assertion_id}): no source file")
                continue
            result = add_assertion_to_file(file_path, req_id, label, text)
            if result.get("success"):
                files_modified.add(str(file_path))
                saved_count += 1
            else:
                errors.append(
                    f"add_assertion({assertion_id}): {result.get('error', 'unknown error')}"
                )

        elif op in ("add_edge", "delete_edge"):
            # Coalesce: just track the affected requirement for bulk write later
            source_id = entry.before_state.get("source_id") or entry.after_state.get(
                "source_id", ""
            )
            if source_id:
                edge_affected_reqs.add(source_id)
            saved_count += 1

        elif op == "change_edge_kind":
            # Coalesce with add_edge/delete_edge: the live graph already
            # reflects the new edge kind, so writing the full implements +
            # refines lists will produce the correct result.  This avoids
            # ordering conflicts when change_edge_kind and add_edge both
            # affect the same requirement in a single save batch.
            source_id = entry.before_state.get("source_id") or entry.after_state.get(
                "source_id", ""
            )
            if source_id:
                edge_affected_reqs.add(source_id)
            saved_count += 1

        elif op == "delete_assertion":
            assertion_id = entry.target_id
            label = entry.before_state.get("label", "")
            req_id = entry.before_state.get("parent_id", "")
            renames = entry.before_state.get("renames")
            if not req_id:
                req_id, _ = _get_req_id_from_assertion_id(assertion_id)
            file_path = _get_source_path(graph, req_id, repo_root)
            if file_path is None:
                skipped.append(f"delete_assertion({assertion_id}): no source file")
                continue
            result = delete_assertion_from_file(file_path, req_id, label, renames=renames)
            if result.get("success"):
                files_modified.add(str(file_path))
                saved_count += 1
            else:
                errors.append(
                    f"delete_assertion({assertion_id}): {result.get('error', 'unknown error')}"
                )

        elif op == "rename_assertion":
            assertion_id = entry.target_id
            old_label = entry.before_state.get("label", "")
            new_label = entry.after_state.get("label", "")
            req_id = entry.before_state.get("parent_id", "")
            if not req_id:
                req_id, _ = _get_req_id_from_assertion_id(assertion_id)
            file_path = _get_source_path(graph, req_id, repo_root)
            if file_path is None:
                skipped.append(f"rename_assertion({assertion_id}): no source file")
                continue
            result = rename_assertion_in_file(file_path, req_id, old_label, new_label)
            if result.get("success"):
                files_modified.add(str(file_path))
                saved_count += 1
            elif result.get("no_change"):
                saved_count += 1
            else:
                errors.append(
                    f"rename_assertion({assertion_id}): {result.get('error', 'unknown error')}"
                )

        elif op == "fix_broken_reference":
            source_id = entry.before_state.get("source_id", "")
            old_target_id = entry.before_state.get("old_target_id", "")
            new_target_id = entry.after_state.get("new_target_id", "")
            file_path = _get_source_path(graph, source_id, repo_root)
            if file_path is None:
                skipped.append(f"fix_broken_reference({source_id}): no source file")
                continue
            result = fix_reference_in_file(file_path, source_id, old_target_id, new_target_id)
            if result.get("success"):
                files_modified.add(str(file_path))
                saved_count += 1
            else:
                errors.append(
                    f"fix_broken_reference({source_id}): {result.get('error', 'unknown error')}"
                )

        elif op == "rename_node":
            old_id = entry.before_state.get("id", "")
            new_id = entry.after_state.get("id", "")
            # The node now has new_id in memory
            file_path = _get_source_path(graph, new_id, repo_root)
            if file_path is None:
                skipped.append(f"rename_node({old_id}): no source file")
                continue
            # Rename the header in the source file
            result = rename_requirement_id(file_path, old_id, new_id)
            if result.get("success"):
                files_modified.add(str(file_path))
                saved_count += 1
            else:
                errors.append(f"rename_node({old_id}): {result.get('error', 'unknown error')}")
                continue
            # Update references in all spec files that point to old_id
            # (including the source file itself, which may contain other
            # reqs that reference the renamed ID)
            seen_files: set[str] = set()
            for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
                _fn = node.file_node()
                if _fn is None or not _fn.get_field("relative_path"):
                    continue
                ref_path = _get_source_path(graph, node.id, repo_root)
                if ref_path is None or str(ref_path) in seen_files:
                    continue
                seen_files.add(str(ref_path))
                ref_result = rename_references_in_file(ref_path, old_id, new_id)
                if ref_result.get("success") and not ref_result.get("no_change"):
                    files_modified.add(str(ref_path))

        elif op == "add_requirement":
            req_id = entry.after_state.get("id", "")
            title = entry.after_state.get("title", "")
            level = entry.after_state.get("level", "DEV")
            status = entry.after_state.get("status", "Draft")
            hash_value = entry.after_state.get("hash", "00000000")
            parent_id = entry.after_state.get("parent_id")
            # Determine target file: use parent's file if available
            if parent_id:
                file_path = _get_source_path(graph, parent_id, repo_root)
            else:
                file_path = None
            if file_path is None:
                skipped.append(
                    f"add_requirement({req_id}): no target file "
                    "(specify parent_id to use parent's file)"
                )
                continue
            # Build implements list from parent linkage
            implements = [parent_id] if parent_id else []
            result = add_requirement_to_file(
                file_path, req_id, title, level, status, implements, hash_value
            )
            if result.get("success"):
                files_modified.add(str(file_path))
                saved_count += 1
            else:
                errors.append(f"add_requirement({req_id}): {result.get('error', 'unknown error')}")

        elif op == "delete_requirement":
            node_id = entry.target_id
            source_path = entry.before_state.get("source_path")
            if not source_path:
                skipped.append(f"delete_requirement({node_id}): no source file in mutation state")
                continue
            p = Path(source_path)
            if not p.is_absolute():
                p = repo_root / p
            if not p.exists():
                skipped.append(f"delete_requirement({node_id}): source file does not exist")
                continue
            result = delete_requirement_from_file(p, node_id)
            if result.get("success"):
                files_modified.add(str(p))
                saved_count += 1
            else:
                errors.append(
                    f"delete_requirement({node_id}): {result.get('error', 'unknown error')}"
                )

        else:
            skipped.append(f"{op}({entry.target_id}): not yet supported for disk persistence")

    # Write coalesced edge mutations: full implements + refines list per affected requirement
    for req_id in edge_affected_reqs:
        file_path = _get_source_path(graph, req_id, repo_root)
        if file_path is None:
            skipped.append(f"edge_coalesce({req_id}): no source file")
            continue

        # Coalesce IMPLEMENTS edges
        implements_list = _get_current_implements_list(graph, req_id)
        result = modify_implements(file_path, req_id, implements_list)
        if result.get("success"):
            if not result.get("no_change"):
                files_modified.add(str(file_path))
        else:
            errors.append(
                f"edge_coalesce_implements({req_id}): {result.get('error', 'unknown error')}"
            )

        # Coalesce REFINES edges
        refines_list = _get_current_refines_list(graph, req_id)
        result = modify_refines(file_path, req_id, refines_list)
        if result.get("success"):
            if not result.get("no_change"):
                files_modified.add(str(file_path))
        else:
            errors.append(
                f"edge_coalesce_refines({req_id}): {result.get('error', 'unknown error')}"
            )

    # Clear mutation log after successful save
    if not errors:
        graph.mutation_log.clear()

    return {
        "success": len(errors) == 0,
        "saved_count": saved_count,
        "files_modified": sorted(files_modified),
        "conflicts": [],
        "errors": errors,
        "skipped": skipped,
    }
