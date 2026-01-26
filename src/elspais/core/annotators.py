"""Node annotation functions for TraceGraph.

These are pure functions that annotate individual TraceNode instances.
The graph provides the iterator (graph.all_nodes()), and the caller
applies annotators to nodes as needed.

Usage:
    from elspais.core.annotators import annotate_git_state, annotate_display_info
    from elspais.core.graph import NodeKind

    for node in graph.all_nodes():
        if node.kind == NodeKind.REQUIREMENT:
            annotate_git_state(node, git_info)
            annotate_display_info(node)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from elspais.core.git import GitChangeInfo
    from elspais.core.graph import TraceNode


def annotate_git_state(node: TraceNode, git_info: GitChangeInfo | None) -> None:
    """Annotate a node with git state information.

    This is a pure function that mutates node.metrics in place.
    Only operates on REQUIREMENT nodes.

    Git metrics added to node.metrics:
    - is_uncommitted: True if file has uncommitted changes
    - is_untracked: True if file is not tracked by git (new file)
    - is_branch_changed: True if file differs from main branch
    - is_moved: True if requirement moved from a different file
    - is_modified: True if file is modified (but tracked)
    - is_new: True if in an untracked file (convenience alias)

    Args:
        node: The node to annotate.
        git_info: Git change information, or None if git unavailable.
    """
    from elspais.core.graph import NodeKind

    if node.kind != NodeKind.REQUIREMENT:
        return

    req = node.requirement
    if not req:
        return

    # Get file path relative to repo
    file_path = node.source.path if node.source else ""

    # Default all git states to False
    is_uncommitted = False
    is_untracked = False
    is_branch_changed = False
    is_moved = False
    is_modified = False

    if git_info:
        # Check if file has uncommitted changes
        is_untracked = file_path in git_info.untracked_files
        is_modified = file_path in git_info.modified_files
        is_uncommitted = is_untracked or is_modified

        # Check if file changed vs main branch
        is_branch_changed = file_path in git_info.branch_changed_files

        # Check if requirement was moved
        # Short ID used in committed_req_locations (e.g., 'd00001')
        short_id = req.id.split("-")[-1] if "-" in req.id else req.id
        committed_path = git_info.committed_req_locations.get(short_id)
        if committed_path and committed_path != file_path:
            is_moved = True

    # is_new means it's in an untracked file (truly new, not moved)
    is_new = is_untracked

    # Annotate node metrics
    node.metrics["is_uncommitted"] = is_uncommitted
    node.metrics["is_untracked"] = is_untracked
    node.metrics["is_branch_changed"] = is_branch_changed
    node.metrics["is_moved"] = is_moved
    node.metrics["is_modified"] = is_modified
    node.metrics["is_new"] = is_new


def annotate_display_info(node: TraceNode) -> None:
    """Annotate a node with display-friendly information.

    This is a pure function that mutates node.metrics in place.
    Only operates on REQUIREMENT nodes.

    Display metrics added to node.metrics:
    - is_roadmap: True if in spec/roadmap/ directory
    - is_conflict: True if has duplicate ID conflict
    - conflict_with: ID of conflicting requirement (if conflict)
    - display_filename: Filename stem for display
    - file_name: Full filename
    - repo_prefix: Repo prefix for multi-repo setups (e.g., "CORE", "CAL")
    - external_spec_path: Path for associated repo specs

    Args:
        node: The node to annotate.
    """
    from elspais.core.graph import NodeKind

    if node.kind != NodeKind.REQUIREMENT:
        return

    req = node.requirement
    if not req:
        return

    # Get file path relative to repo
    file_path = node.source.path if node.source else ""

    # Roadmap detection from path
    is_roadmap = "roadmap" in file_path.lower()
    node.metrics["is_roadmap"] = is_roadmap

    # Conflict detection from requirement
    is_conflict = getattr(req, "is_conflict", False)
    conflict_with = getattr(req, "conflict_with", None)
    node.metrics["is_conflict"] = is_conflict
    if conflict_with:
        node.metrics["conflict_with"] = conflict_with

    # Store display-friendly file info
    if req.file_path:
        node.metrics["display_filename"] = req.file_path.stem
        node.metrics["file_name"] = req.file_path.name
    else:
        node.metrics["display_filename"] = ""
        node.metrics["file_name"] = ""

    # Repo prefix for multi-repo setups
    repo_prefix = getattr(req, "repo_prefix", None)
    node.metrics["repo_prefix"] = repo_prefix or "CORE"

    # External spec path for associated repos
    external_spec_path = getattr(req, "external_spec_path", None)
    if external_spec_path:
        node.metrics["external_spec_path"] = str(external_spec_path)


def annotate_implementation_files(
    node: TraceNode,
    implementation_files: list[tuple[str, int]],
) -> None:
    """Annotate a node with implementation file references.

    Args:
        node: The node to annotate.
        implementation_files: List of (file_path, line_number) tuples.
    """
    from elspais.core.graph import NodeKind

    if node.kind != NodeKind.REQUIREMENT:
        return

    # Store implementation files in metrics
    existing = node.metrics.get("implementation_files", [])
    existing.extend(implementation_files)
    node.metrics["implementation_files"] = existing


# =============================================================================
# Graph Aggregate Functions
# =============================================================================
# These functions compute aggregate statistics from an annotated graph.
# They follow the composable pattern: take a graph, return computed values.


if TYPE_CHECKING:
    from elspais.core.graph import TraceGraph


def count_by_level(graph: TraceGraph) -> dict[str, dict[str, int]]:
    """Count requirements by level, with and without deprecated.

    Args:
        graph: The TraceGraph to aggregate.

    Returns:
        Dict with 'active' (excludes Deprecated) and 'all' (includes Deprecated) counts
        by level (PRD, OPS, DEV).
    """
    from elspais.core.graph import NodeKind

    counts = {
        "active": {"PRD": 0, "OPS": 0, "DEV": 0},
        "all": {"PRD": 0, "OPS": 0, "DEV": 0},
    }
    for node in graph.all_nodes():
        if node.kind != NodeKind.REQUIREMENT:
            continue
        req = node.requirement
        if not req:
            continue
        level = req.level
        counts["all"][level] = counts["all"].get(level, 0) + 1
        if req.status != "Deprecated":
            counts["active"][level] = counts["active"].get(level, 0) + 1
    return counts


def count_by_repo(graph: TraceGraph) -> dict[str, dict[str, int]]:
    """Count requirements by repo prefix (CORE, CAL, TTN, etc.).

    Args:
        graph: The TraceGraph to aggregate.

    Returns:
        Dict mapping repo prefix to {'active': count, 'all': count}.
        CORE is used for core repo requirements (no prefix).
    """
    from elspais.core.graph import NodeKind

    repo_counts: dict[str, dict[str, int]] = {}

    for node in graph.all_nodes():
        if node.kind != NodeKind.REQUIREMENT:
            continue
        req = node.requirement
        if not req:
            continue

        prefix = node.metrics.get("repo_prefix", "CORE")

        if prefix not in repo_counts:
            repo_counts[prefix] = {"active": 0, "all": 0}

        repo_counts[prefix]["all"] += 1
        if req.status != "Deprecated":
            repo_counts[prefix]["active"] += 1

    return repo_counts


def count_implementation_files(graph: TraceGraph) -> int:
    """Count total implementation files across all requirements.

    Args:
        graph: The TraceGraph to aggregate.

    Returns:
        Total count of implementation file references.
    """
    from elspais.core.graph import NodeKind

    total = 0
    for node in graph.all_nodes():
        if node.kind != NodeKind.REQUIREMENT:
            continue
        impl_files = node.metrics.get("implementation_files", [])
        total += len(impl_files)
    return total


def collect_topics(graph: TraceGraph) -> list[str]:
    """Collect unique topics from requirement file names.

    Args:
        graph: The TraceGraph to scan.

    Returns:
        Sorted list of unique topic names extracted from file stems.
    """
    from elspais.core.graph import NodeKind

    all_topics: set[str] = set()
    for node in graph.all_nodes():
        if node.kind != NodeKind.REQUIREMENT:
            continue
        req = node.requirement
        if req and req.file_path:
            topic = (
                req.file_path.stem.split("-", 1)[1]
                if "-" in req.file_path.stem
                else req.file_path.stem
            )
            all_topics.add(topic)
    return sorted(all_topics)


def get_implementation_status(node: TraceNode) -> str:
    """Get implementation status for a requirement node.

    Args:
        node: The TraceNode to check.

    Returns:
        'Full': coverage_pct >= 100
        'Partial': coverage_pct > 0
        'Unimplemented': coverage_pct == 0
    """
    coverage_pct = node.metrics.get("coverage_pct", 0)
    if coverage_pct >= 100:
        return "Full"
    elif coverage_pct > 0:
        return "Partial"
    else:
        return "Unimplemented"
