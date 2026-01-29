"""Node annotation functions for TraceGraph.

These are pure functions that annotate individual GraphNode instances.
The graph provides the iterator (graph.all_nodes()), and the caller
applies annotators to nodes as needed.

Usage:
    from elspais.graph.annotators import annotate_git_state, annotate_display_info
    from elspais.graph import NodeKind

    for node in graph.all_nodes():
        if node.kind == NodeKind.REQUIREMENT:
            annotate_git_state(node, git_info)
            annotate_display_info(node)
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from elspais.graph.GraphNode import GraphNode
    from elspais.graph.builder import TraceGraph
    from elspais.utilities.git import GitChangeInfo


def annotate_git_state(node: GraphNode, git_info: GitChangeInfo | None) -> None:
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
    from elspais.graph import NodeKind

    if node.kind != NodeKind.REQUIREMENT:
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
        # Extract short ID from node ID (e.g., 'p00001' from 'REQ-p00001')
        req_id = node.id
        if "-" in req_id:
            short_id = req_id.rsplit("-", 1)[-1]
            # Handle assertion IDs like REQ-p00001-A
            if len(short_id) == 1 and short_id.isalpha():
                # This is an assertion, get the parent ID
                parts = req_id.split("-")
                if len(parts) >= 2:
                    short_id = parts[-2]
        else:
            short_id = req_id

        committed_path = git_info.committed_req_locations.get(short_id)
        if committed_path and committed_path != file_path:
            is_moved = True

    # is_new means it's in an untracked file (truly new, not moved)
    is_new = is_untracked

    # Annotate node metrics
    node.set_metric("is_uncommitted", is_uncommitted)
    node.set_metric("is_untracked", is_untracked)
    node.set_metric("is_branch_changed", is_branch_changed)
    node.set_metric("is_moved", is_moved)
    node.set_metric("is_modified", is_modified)
    node.set_metric("is_new", is_new)


def annotate_display_info(node: GraphNode) -> None:
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
    from elspais.graph import NodeKind

    if node.kind != NodeKind.REQUIREMENT:
        return

    # Get file path relative to repo
    file_path = node.source.path if node.source else ""

    # Roadmap detection from path
    is_roadmap = "roadmap" in file_path.lower()
    node.set_metric("is_roadmap", is_roadmap)

    # Conflict detection from content
    is_conflict = node.get_field("is_conflict", False)
    conflict_with = node.get_field("conflict_with")
    node.set_metric("is_conflict", is_conflict)
    if conflict_with:
        node.set_metric("conflict_with", conflict_with)

    # Store display-friendly file info
    if file_path:
        path = Path(file_path)
        node.set_metric("display_filename", path.stem)
        node.set_metric("file_name", path.name)
    else:
        node.set_metric("display_filename", "")
        node.set_metric("file_name", "")

    # Repo prefix for multi-repo setups
    repo_prefix = node.get_field("repo_prefix")
    node.set_metric("repo_prefix", repo_prefix or "CORE")

    # External spec path for associated repos
    external_spec_path = node.get_field("external_spec_path")
    if external_spec_path:
        node.set_metric("external_spec_path", str(external_spec_path))


def annotate_implementation_files(
    node: GraphNode,
    implementation_files: list[tuple[str, int]],
) -> None:
    """Annotate a node with implementation file references.

    Args:
        node: The node to annotate.
        implementation_files: List of (file_path, line_number) tuples.
    """
    from elspais.graph import NodeKind

    if node.kind != NodeKind.REQUIREMENT:
        return

    # Store implementation files in metrics
    existing = node.get_metric("implementation_files", [])
    existing.extend(implementation_files)
    node.set_metric("implementation_files", existing)


# =============================================================================
# Graph Aggregate Functions
# =============================================================================
# These functions compute aggregate statistics from an annotated graph.
# They follow the composable pattern: take a graph, return computed values.


def count_by_level(graph: TraceGraph) -> dict[str, dict[str, int]]:
    """Count requirements by level, with and without deprecated.

    Args:
        graph: The TraceGraph to aggregate.

    Returns:
        Dict with 'active' (excludes Deprecated) and 'all' (includes Deprecated) counts
        by level (PRD, OPS, DEV).
    """
    from elspais.graph import NodeKind

    counts: dict[str, dict[str, int]] = {
        "active": {"PRD": 0, "OPS": 0, "DEV": 0},
        "all": {"PRD": 0, "OPS": 0, "DEV": 0},
    }
    for node in graph._index.values():
        if node.kind != NodeKind.REQUIREMENT:
            continue
        level = node.get_field("level", "")
        status = node.get_field("status", "Active")
        if level:
            counts["all"][level] = counts["all"].get(level, 0) + 1
            if status != "Deprecated":
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
    from elspais.graph import NodeKind

    repo_counts: dict[str, dict[str, int]] = {}

    for node in graph._index.values():
        if node.kind != NodeKind.REQUIREMENT:
            continue

        prefix = node.get_metric("repo_prefix", "CORE")
        status = node.get_field("status", "Active")

        if prefix not in repo_counts:
            repo_counts[prefix] = {"active": 0, "all": 0}

        repo_counts[prefix]["all"] += 1
        if status != "Deprecated":
            repo_counts[prefix]["active"] += 1

    return repo_counts


def count_implementation_files(graph: TraceGraph) -> int:
    """Count total implementation files across all requirements.

    Args:
        graph: The TraceGraph to aggregate.

    Returns:
        Total count of implementation file references.
    """
    from elspais.graph import NodeKind

    total = 0
    for node in graph._index.values():
        if node.kind != NodeKind.REQUIREMENT:
            continue
        impl_files = node.get_metric("implementation_files", [])
        total += len(impl_files)
    return total


def collect_topics(graph: TraceGraph) -> list[str]:
    """Collect unique topics from requirement file names.

    Args:
        graph: The TraceGraph to scan.

    Returns:
        Sorted list of unique topic names extracted from file stems.
    """
    from elspais.graph import NodeKind

    all_topics: set[str] = set()
    for node in graph._index.values():
        if node.kind != NodeKind.REQUIREMENT:
            continue
        if node.source and node.source.path:
            stem = Path(node.source.path).stem
            topic = stem.split("-", 1)[1] if "-" in stem else stem
            all_topics.add(topic)
    return sorted(all_topics)


def get_implementation_status(node: GraphNode) -> str:
    """Get implementation status for a requirement node.

    Args:
        node: The GraphNode to check.

    Returns:
        'Full': coverage_pct >= 100
        'Partial': coverage_pct > 0
        'Unimplemented': coverage_pct == 0
    """
    coverage_pct = node.get_metric("coverage_pct", 0)
    if coverage_pct >= 100:
        return "Full"
    elif coverage_pct > 0:
        return "Partial"
    else:
        return "Unimplemented"


def annotate_coverage(graph: TraceGraph) -> None:
    """Compute and store coverage metrics for all requirement nodes.

    This function traverses the graph once to compute RollupMetrics for
    each REQUIREMENT node. Metrics are stored in node._metrics as:
    - "rollup_metrics": The full RollupMetrics object
    - "coverage_pct": Coverage percentage (for convenience)

    Coverage is determined by outgoing edges from REQUIREMENT nodes:
    - The builder links TEST/CODE/REQ as children of the parent REQ
    - Edges have assertion_targets when they target specific assertions
    - VALIDATES to TEST with assertion_targets → DIRECT coverage
    - IMPLEMENTS to CODE with assertion_targets → DIRECT coverage
    - IMPLEMENTS to REQ with assertion_targets → EXPLICIT coverage
    - IMPLEMENTS to REQ without assertion_targets → INFERRED coverage

    REFINES edges do NOT contribute to coverage (EdgeKind.contributes_to_coverage()).

    Test-specific metrics:
    - direct_tested: Assertions with TEST nodes (not CODE)
    - validated: Assertions with passing TEST_RESULTs
    - has_failures: Any TEST_RESULT is failed/error

    Args:
        graph: The TraceGraph to annotate.
    """
    from elspais.graph import NodeKind
    from elspais.graph.metrics import (
        CoverageContribution,
        CoverageSource,
        RollupMetrics,
    )
    from elspais.graph.relations import EdgeKind

    for node in graph._index.values():
        if node.kind != NodeKind.REQUIREMENT:
            continue

        metrics = RollupMetrics()

        # Collect assertion children
        assertion_labels: list[str] = []

        for child in node.iter_children():
            if child.kind == NodeKind.ASSERTION:
                label = child.get_field("label", "")
                if label:
                    assertion_labels.append(label)

        metrics.total_assertions = len(assertion_labels)

        # Track TEST-specific metrics
        tested_labels: set[str] = set()  # Assertions with TEST coverage
        validated_labels: set[str] = set()  # Assertions with passing tests
        has_failures = False
        test_nodes_for_result_lookup: list[tuple[GraphNode, list[str] | None]] = []

        # Check outgoing edges from this requirement
        # The builder links TEST/CODE/REQ as children of parent REQ with assertion_targets
        for edge in node.iter_outgoing_edges():
            if not edge.kind.contributes_to_coverage():
                # REFINES doesn't count
                continue

            target_node = edge.target
            target_kind = target_node.kind

            if target_kind == NodeKind.TEST:
                # TEST validates assertion(s) → DIRECT coverage
                if edge.assertion_targets:
                    for label in edge.assertion_targets:
                        if label in assertion_labels:
                            metrics.add_contribution(
                                CoverageContribution(
                                    source_id=target_node.id,
                                    source_type=CoverageSource.DIRECT,
                                    assertion_label=label,
                                )
                            )
                            tested_labels.add(label)

                # Track this TEST node for result lookup later
                test_nodes_for_result_lookup.append((target_node, edge.assertion_targets))

            elif target_kind == NodeKind.CODE:
                # CODE implements assertion(s) → DIRECT coverage
                if edge.assertion_targets:
                    for label in edge.assertion_targets:
                        if label in assertion_labels:
                            metrics.add_contribution(
                                CoverageContribution(
                                    source_id=target_node.id,
                                    source_type=CoverageSource.DIRECT,
                                    assertion_label=label,
                                )
                            )

            elif target_kind == NodeKind.REQUIREMENT:
                # Child REQ implements this REQ
                if edge.assertion_targets:
                    # Explicit: REQ implements specific assertions
                    for label in edge.assertion_targets:
                        if label in assertion_labels:
                            metrics.add_contribution(
                                CoverageContribution(
                                    source_id=target_node.id,
                                    source_type=CoverageSource.EXPLICIT,
                                    assertion_label=label,
                                )
                            )
                else:
                    # Inferred: REQ implements parent REQ (all assertions)
                    for label in assertion_labels:
                        metrics.add_contribution(
                            CoverageContribution(
                                source_id=target_node.id,
                                source_type=CoverageSource.INFERRED,
                                assertion_label=label,
                            )
                        )

        # Process TEST children to find TEST_RESULT nodes
        for test_node, assertion_targets in test_nodes_for_result_lookup:
            for result in test_node.iter_children():
                if result.kind == NodeKind.TEST_RESULT:
                    status = (result.get_field("status", "") or "").lower()
                    if status in ("passed", "pass", "success"):
                        # Mark assertions as validated by passing tests
                        for label in assertion_targets or []:
                            if label in assertion_labels:
                                validated_labels.add(label)
                    elif status in ("failed", "fail", "failure", "error"):
                        has_failures = True

        # Set test-specific metrics before finalize
        metrics.direct_tested = len(tested_labels)
        metrics.validated = len(validated_labels)
        metrics.has_failures = has_failures

        # Finalize metrics (computes aggregate coverage counts)
        metrics.finalize()

        # Store in node metrics
        node.set_metric("rollup_metrics", metrics)
        node.set_metric("coverage_pct", metrics.coverage_pct)


__all__ = [
    "annotate_git_state",
    "annotate_display_info",
    "annotate_implementation_files",
    "count_by_level",
    "count_by_repo",
    "count_implementation_files",
    "collect_topics",
    "get_implementation_status",
    "annotate_coverage",
]
