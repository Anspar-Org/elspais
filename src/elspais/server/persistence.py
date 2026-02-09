# Implements: REQ-o00063-A, REQ-o00063-F, REQ-o00063-G, REQ-o00063-H, REQ-o00063-I
"""Persistence layer — replay in-memory mutations to spec files on disk.

Walks the graph's mutation log and calls the appropriate spec_writer
function for each mutation entry. Edge mutations are coalesced: instead
of replaying incremental add/delete operations, we read the *current*
implements list from the live graph and write it once per affected
requirement.

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
    change_reference_type,
    modify_assertion_text,
    modify_implements,
    modify_status,
    modify_title,
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
    node = graph.find_by_id(node_id)
    if node is None or node.source is None:
        return None
    source_path = node.source.path
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
    IMPLEMENTS edges.

    Args:
        graph: The traceability graph.
        req_id: Requirement ID to inspect.

    Returns:
        Sorted list of parent requirement IDs linked via IMPLEMENTS.
    """
    node = graph.find_by_id(req_id)
    if node is None:
        return []

    implements: list[str] = []
    for edge in node.iter_incoming_edges():
        if edge.kind == EdgeKind.IMPLEMENTS and edge.source.kind == NodeKind.REQUIREMENT:
            implements.append(edge.source.id)
    return sorted(implements)


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

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if node.source is None or not node.source.path:
            continue
        rel_path = node.source.path
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
            # This changes IMPLEMENTS <-> REFINES; use change_reference_type
            source_id = entry.before_state.get("source_id") or entry.after_state.get(
                "source_id", ""
            )
            target_id = entry.before_state.get("target_id") or entry.after_state.get(
                "target_id", ""
            )
            new_kind = entry.after_state.get("edge_kind", "")
            file_path = _get_source_path(graph, source_id, repo_root)
            if file_path is None:
                skipped.append(f"change_edge_kind({source_id}): no source file")
                continue
            # Capitalize for spec_writer: "implements" -> "IMPLEMENTS"
            new_type = new_kind.upper() if new_kind else "IMPLEMENTS"
            result = change_reference_type(file_path, source_id, target_id, new_type)
            if result.get("success"):
                files_modified.add(str(file_path))
                saved_count += 1
            else:
                errors.append(
                    f"change_edge_kind({source_id}->{target_id}): "
                    f"{result.get('error', 'unknown error')}"
                )

        else:
            # Operations that don't map to file changes (rename_node,
            # add_requirement, delete_requirement, rename_assertion,
            # delete_assertion, fix_broken_reference) are skipped because
            # they require more complex file mutations not yet supported.
            skipped.append(f"{op}({entry.target_id}): not yet supported for disk persistence")

    # Write coalesced edge mutations: full implements list per affected requirement
    for req_id in edge_affected_reqs:
        file_path = _get_source_path(graph, req_id, repo_root)
        if file_path is None:
            skipped.append(f"edge_coalesce({req_id}): no source file")
            continue
        implements_list = _get_current_implements_list(graph, req_id)
        result = modify_implements(file_path, req_id, implements_list)
        if result.get("success"):
            files_modified.add(str(file_path))
        elif not result.get("no_change"):
            errors.append(f"edge_coalesce({req_id}): {result.get('error', 'unknown error')}")

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
