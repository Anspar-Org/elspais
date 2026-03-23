# Implements: REQ-p00006-B
# Implements: REQ-o00051-A, REQ-o00051-B, REQ-o00051-C, REQ-o00051-D
# Implements: REQ-o00051-E, REQ-o00051-F
# Implements: REQ-d00050-A, REQ-d00050-B, REQ-d00050-C, REQ-d00050-D, REQ-d00050-E
# Implements: REQ-d00051-A, REQ-d00051-B, REQ-d00051-C, REQ-d00051-D
# Implements: REQ-d00051-E, REQ-d00051-F
# Implements: REQ-d00055-A, REQ-d00055-B, REQ-d00055-C, REQ-d00055-D, REQ-d00055-E
# Implements: REQ-d00069-A, REQ-d00069-B, REQ-d00069-D
# Implements: REQ-d00215-A+B+C+D+E
"""Node annotation functions for TraceGraph.

These are pure functions that annotate individual GraphNode instances.
The graph provides iterators (graph.all_nodes(), graph.nodes_by_kind()),
and the caller applies annotators to nodes as needed.

Usage:
    from elspais.graph.annotators import annotate_git_state, annotate_display_info
    from elspais.graph import NodeKind

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        annotate_git_state(node, git_info)
        annotate_display_info(node)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from elspais.config.schema import ElspaisConfig

_SCHEMA_FIELDS = {f.alias or name for name, f in ElspaisConfig.model_fields.items()} | set(
    ElspaisConfig.model_fields.keys()
)


def _validate_config(config: dict[str, Any]) -> ElspaisConfig:
    """Validate a config dict into ElspaisConfig, stripping non-schema keys."""
    filtered = {k: v for k, v in config.items() if k in _SCHEMA_FIELDS}
    assoc = filtered.get("associates")
    if isinstance(assoc, dict) and "paths" in assoc:
        filtered.pop("associates", None)
    return ElspaisConfig.model_validate(filtered)


# Implements: REQ-p00016
_NA_PATTERN = re.compile(
    r"([\w-]+-[A-Z0-9]+)\s+SHALL\s+be\s+NOT\s+APPLICABLE",
    re.IGNORECASE,
)

if TYPE_CHECKING:
    from elspais.graph import NodeKind
    from elspais.graph.federated import FederatedGraph
    from elspais.graph.GraphNode import GraphNode
    from elspais.graph.metrics import RollupMetrics
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

    # Implements: REQ-d00129-D
    # Get file path relative to repo via FILE parent node
    fn = node.file_node()
    file_path = fn.get_field("relative_path") if fn else ""

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

        # Check if requirement was moved by comparing its current file path
        # against the committed location. Uses the full canonical node ID as key,
        # matching the format produced by _extract_req_locations_from_graph().
        committed_path = git_info.committed_req_locations.get(node.id)
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

    # Implements: REQ-d00129-D
    # Get file path relative to repo via FILE parent node
    fn = node.file_node()
    file_path = fn.get_field("relative_path") if fn else ""

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


def annotate_graph_git_state(graph: FederatedGraph) -> None:
    """Annotate all requirement nodes in the graph with git state information.

    This is the single entry point for applying git annotations to a graph.
    It calls get_git_changes() to gather git info, then applies
    annotate_git_state() to each REQUIREMENT node.

    Idempotent: safe to call multiple times on the same graph.
    Fails silently when git is unavailable.

    Args:
        graph: The TraceGraph to annotate.
    """
    from elspais.graph import NodeKind

    repo_root = graph.repo_root
    if not repo_root:
        return

    try:
        from elspais.utilities.git import get_git_changes

        git_info = get_git_changes(repo_root)
    except Exception:
        return

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        annotate_git_state(node, git_info)


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


def count_by_level(
    graph: FederatedGraph,
    config: dict[str, Any] | None = None,
) -> dict[str, dict[str, int]]:
    """Count requirements by level, with and without excluded statuses.

    Args:
        graph: The TraceGraph to aggregate.
        config: Optional config dict. If provided, derives level keys from
                typed config levels and status roles.

    Returns:
        Dict with 'active' (excludes analysis-excluded statuses) and 'all'
        (includes all) counts by level.
    """
    from elspais.config.status_roles import StatusRolesConfig
    from elspais.graph import NodeKind

    # Derive level keys from config or use hardcoded defaults
    if config is not None:
        typed_config = _validate_config(config)
        level_keys = list(typed_config.levels.keys())
        status_roles_data = typed_config.rules.format.status_roles
        roles = (
            StatusRolesConfig.from_dict(status_roles_data)
            if status_roles_data
            else StatusRolesConfig.default()
        )
    else:
        level_keys = ["PRD", "OPS", "DEV"]
        roles = StatusRolesConfig.default()

    counts: dict[str, dict[str, int]] = {
        "active": dict.fromkeys(level_keys, 0),
        "all": dict.fromkeys(level_keys, 0),
    }
    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        level = node.get_field("level", "")
        status = node.get_field("status", "Active")
        if level:
            counts["all"][level] = counts["all"].get(level, 0) + 1
            if not roles.is_excluded_from_analysis(status):
                counts["active"][level] = counts["active"].get(level, 0) + 1
    return counts


def group_by_level(
    graph: FederatedGraph,
    config: dict[str, Any] | None = None,
) -> dict[str, list[GraphNode]]:
    """Group requirements by level.

    Args:
        graph: The TraceGraph to query.
        config: Optional config dict. If provided, derives level keys from
                typed config levels. Otherwise uses hardcoded defaults.

    Returns:
        Dict mapping level to list of requirement nodes, plus "other" for unrecognized.
    """
    from elspais.graph import NodeKind

    # Derive level keys from config or use hardcoded defaults
    if config is not None:
        typed_config = _validate_config(config)
        level_keys = list(typed_config.levels.keys())
    else:
        level_keys = ["PRD", "OPS", "DEV"]

    groups: dict[str, list[GraphNode]] = {k: [] for k in level_keys}
    groups["other"] = []

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        level = node.get_field("level") or ""
        if level in groups:
            groups[level].append(node)
        else:
            groups["other"].append(node)
    return groups


def count_by_repo(
    graph: FederatedGraph,
    config: dict[str, Any] | None = None,
) -> dict[str, dict[str, int]]:
    """Count requirements by repo prefix (CORE, CAL, TTN, etc.).

    Args:
        graph: The TraceGraph to aggregate.
        config: Optional config dict. If provided, derives status roles from
                typed config status roles.

    Returns:
        Dict mapping repo prefix to {'active': count, 'all': count}.
        CORE is used for core repo requirements (no prefix).
    """
    from elspais.config.status_roles import StatusRolesConfig
    from elspais.graph import NodeKind

    if config is not None:
        typed_config = _validate_config(config)
        status_roles_data = typed_config.rules.format.status_roles
        roles = (
            StatusRolesConfig.from_dict(status_roles_data)
            if status_roles_data
            else StatusRolesConfig.default()
        )
    else:
        roles = StatusRolesConfig.default()

    repo_counts: dict[str, dict[str, int]] = {}

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):

        prefix = node.get_metric("repo_prefix", "CORE")
        status = node.get_field("status", "Active")

        if prefix not in repo_counts:
            repo_counts[prefix] = {"active": 0, "all": 0}

        repo_counts[prefix]["all"] += 1
        if not roles.is_excluded_from_analysis(status):
            repo_counts[prefix]["active"] += 1

    return repo_counts


def count_implementation_files(graph: FederatedGraph) -> int:
    """Count total implementation files across all requirements.

    Args:
        graph: The TraceGraph to aggregate.

    Returns:
        Total count of implementation file references.
    """
    from elspais.graph import NodeKind

    total = 0
    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        impl_files = node.get_metric("implementation_files", [])
        total += len(impl_files)
    return total


def collect_topics(graph: FederatedGraph) -> list[str]:
    """Collect unique topics from requirement file names.

    Args:
        graph: The TraceGraph to scan.

    Returns:
        Sorted list of unique topic names extracted from file stems.
    """
    from elspais.graph import NodeKind

    all_topics: set[str] = set()
    # Implements: REQ-d00129-D
    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        fn = node.file_node()
        rel_path = fn.get_field("relative_path") if fn else None
        if rel_path:
            stem = Path(rel_path).stem
            topic = stem.split("-", 1)[1] if "-" in stem else stem
            all_topics.add(topic)
    return sorted(all_topics)


def get_implementation_status(node: GraphNode) -> str:
    """Get implementation status for a requirement node.

    Args:
        node: The GraphNode to check.

    Returns:
        'Full': referenced_pct >= 100
        'Partial': referenced_pct > 0
        'Unimplemented': referenced_pct == 0
    """
    rollup = node.get_metric("rollup_metrics")
    pct = rollup.implemented.indirect_pct if rollup else 0
    if pct >= 100:
        return "Full"
    elif pct > 0:
        return "Partial"
    else:
        return "Unimplemented"


def count_by_coverage(
    graph: FederatedGraph,
    exclude_status: set[str] | None = None,
) -> dict[str, int]:
    """Count requirements by coverage level.

    Args:
        graph: The TraceGraph to aggregate.
        exclude_status: Status values to exclude from both numerator and
            denominator (e.g. ``{"Draft"}``).

    Returns:
        Dict with 'total', 'full_coverage', 'partial_coverage', 'no_coverage' counts.
    """
    from elspais.graph import NodeKind

    counts: dict[str, int] = {
        "total": 0,
        "full_coverage": 0,
        "partial_coverage": 0,
        "no_coverage": 0,
    }

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if exclude_status and node.status in exclude_status:
            continue

        counts["total"] += 1
        rollup = node.get_metric("rollup_metrics")
        pct = rollup.implemented.indirect_pct if rollup else 0

        if pct >= 100:
            counts["full_coverage"] += 1
        elif pct > 0:
            counts["partial_coverage"] += 1
        else:
            counts["no_coverage"] += 1

    return counts


def count_with_code_refs(
    graph: FederatedGraph,
    exclude_status: set[str] | None = None,
) -> dict[str, int]:
    """Count requirements that have at least one CODE reference.

    A requirement has CODE coverage if:
    - It has a CODE child directly, OR
    - One of its ASSERTION children has a CODE child

    Args:
        graph: The TraceGraph to query.
        exclude_status: Status values to exclude from both numerator and
            denominator (e.g. ``{"Draft"}``).

    Returns:
        Dict with 'total_requirements', 'with_code_refs', 'coverage_percent'.
    """
    from elspais.graph import NodeKind

    # Build set of excluded requirement IDs
    excluded_ids: set[str] = set()
    if exclude_status:
        for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
            if node.status in exclude_status:
                excluded_ids.add(node.id)

    total = 0
    covered_req_ids: set[str] = set()

    for node in graph.nodes_by_kind(NodeKind.CODE):
        for parent in node.iter_parents():
            if parent.kind == NodeKind.REQUIREMENT and parent.id not in excluded_ids:
                covered_req_ids.add(parent.id)
            elif parent.kind == NodeKind.ASSERTION:
                # Get the parent requirement of the assertion
                for grandparent in parent.iter_parents():
                    if (
                        grandparent.kind == NodeKind.REQUIREMENT
                        and grandparent.id not in excluded_ids
                    ):
                        covered_req_ids.add(grandparent.id)

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if node.id not in excluded_ids:
            total += 1

    pct = (len(covered_req_ids) / total * 100) if total > 0 else 0.0
    return {
        "total_requirements": total,
        "with_code_refs": len(covered_req_ids),
        "coverage_percent": round(pct, 1),
    }


def count_code_coverage(graph: FederatedGraph) -> dict[str, int]:
    """Compute project-wide code coverage statistics.

    Returns dict with:
    - total_executable_lines: sum of executable_lines across FILE nodes
    - total_covered_lines: sum of lines where hit_count > 0 across FILE nodes
    - total_attributed_lines: sum of code_tested.total across all REQUIREMENT nodes
      (lines shared across REQs may be counted multiple times)
    """
    from elspais.graph import NodeKind

    total_executable = 0
    total_covered = 0

    for node in graph.iter_by_kind(NodeKind.FILE):
        executable = node.get_field("executable_lines")
        if executable:
            total_executable += executable
        line_coverage = node.get_field("line_coverage")
        if line_coverage:
            total_covered += sum(1 for hit in line_coverage.values() if hit > 0)

    total_attributed = 0
    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        rollup = node.get_metric("rollup_metrics")
        if rollup is not None:
            total_attributed += rollup.code_tested.total

    return {
        "total_executable_lines": total_executable,
        "total_covered_lines": total_covered,
        "total_attributed_lines": total_attributed,
    }


def count_by_git_status(graph: FederatedGraph) -> dict[str, int]:
    """Count requirements by git change status.

    Args:
        graph: The TraceGraph to aggregate.

    Returns:
        Dict with 'uncommitted' and 'branch_changed' counts.
    """
    from elspais.graph import NodeKind

    counts: dict[str, int] = {
        "uncommitted": 0,
        "branch_changed": 0,
    }

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):

        if node.get_metric("is_uncommitted", False):
            counts["uncommitted"] += 1
        if node.get_metric("is_branch_changed", False):
            counts["branch_changed"] += 1

    return counts


def _compute_coverage_from_source(
    req_node,
    assertion_labels: list,
    edge_kind,
    direct_source_type,
    inferred_source_type,
) -> tuple:
    """Walk req_node outgoing edges of edge_kind (e.g. VERIFIES->TEST or VALIDATES->JNY).

    Returns a tuple of:
    - contributions: list of CoverageContribution
    - source_nodes_with_targets: list of (source_node, assertion_targets_or_None)
      for downstream result lookup

    Implements: REQ-d00069-B
    """
    from elspais.graph.metrics import CoverageContribution

    contributions = []
    source_nodes = []

    for edge in req_node.iter_outgoing_edges():
        if edge.kind != edge_kind:
            continue
        target_node = edge.target
        if edge.assertion_targets:
            for label in edge.assertion_targets:
                if label in assertion_labels:
                    contributions.append(
                        CoverageContribution(
                            source_id=target_node.id,
                            source_type=direct_source_type,
                            assertion_label=label,
                        )
                    )
            source_nodes.append((target_node, list(edge.assertion_targets)))
        else:
            for label in assertion_labels:
                contributions.append(
                    CoverageContribution(
                        source_id=target_node.id,
                        source_type=inferred_source_type,
                        assertion_label=label,
                    )
                )
            source_nodes.append((target_node, None))

    return contributions, source_nodes


def _compute_code_tested(node: GraphNode, metrics: RollupMetrics) -> None:
    """Compute the code_tested dimension from line coverage data.

    Intersects implementation line ranges (from IMPLEMENTS edges to CODE nodes)
    with file-level line_coverage data to determine how many implementation
    lines are exercised by tests.

    Args:
        node: The REQUIREMENT node.
        metrics: The RollupMetrics to update (modifies code_tested in place).
    """
    from elspais.graph import NodeKind
    from elspais.graph.metrics import CoverageDimension
    from elspais.graph.relations import EdgeKind

    # Collect implementation lines: set of (relative_path, line_number)
    impl_lines: set[tuple[str, int]] = set()

    for edge in node.iter_outgoing_edges():
        if edge.kind != EdgeKind.IMPLEMENTS:
            continue
        target = edge.target
        if target.kind != NodeKind.CODE:
            continue

        impl_start = edge.metadata.get("impl_start_line")
        impl_end = edge.metadata.get("impl_end_line")
        if not impl_start:
            continue

        # Fallback: if impl_end is 0 or missing, use parse_end_line
        if not impl_end:
            impl_end = target.get_field("parse_end_line") or 0

        if not impl_end or impl_end < impl_start:
            continue

        # Find FILE ancestor of CODE node
        fn = target.file_node()
        if fn is None:
            continue
        rel_path = fn.get_field("relative_path")
        if not rel_path:
            continue

        for line_no in range(impl_start, impl_end + 1):
            impl_lines.add((rel_path, line_no))

    if not impl_lines:
        return

    # Group lines by file for efficient coverage lookup
    lines_by_file: dict[str, set[int]] = {}
    for rel_path, line_no in impl_lines:
        lines_by_file.setdefault(rel_path, set()).add(line_no)

    # Indirect coverage: check file-level line_coverage
    indirect_count = 0
    has_any_coverage = False

    for edge in node.iter_outgoing_edges():
        if edge.kind != EdgeKind.IMPLEMENTS:
            continue
        target = edge.target
        if target.kind != NodeKind.CODE:
            continue
        fn = target.file_node()
        if fn is None:
            continue
        rel_path = fn.get_field("relative_path")
        if not rel_path or rel_path not in lines_by_file:
            continue

        line_coverage = fn.get_field("line_coverage")
        if line_coverage is None:
            continue
        has_any_coverage = True
        break  # Just checking existence

    if has_any_coverage:
        # Build file_node cache for coverage lookup
        file_coverage: dict[str, dict[int, int]] = {}
        for edge in node.iter_outgoing_edges():
            if edge.kind != EdgeKind.IMPLEMENTS:
                continue
            target = edge.target
            if target.kind != NodeKind.CODE:
                continue
            fn = target.file_node()
            if fn is None:
                continue
            rel_path = fn.get_field("relative_path")
            if not rel_path or rel_path in file_coverage:
                continue
            lc = fn.get_field("line_coverage")
            if lc is not None:
                file_coverage[rel_path] = lc

        for rel_path, lines in lines_by_file.items():
            lc = file_coverage.get(rel_path)
            if lc is None:
                continue
            for line_no in lines:
                if lc.get(line_no, 0) > 0:
                    indirect_count += 1

    metrics.code_tested = CoverageDimension(
        total=len(impl_lines),
        direct=0,  # Direct requires per-test attribution (RESULT.covered_lines)
        indirect=indirect_count,
        has_failures=False,
    )


# Refines: REQ-p00061-A
def annotate_coverage(graph: FederatedGraph) -> None:
    """Compute and store coverage metrics for all requirement nodes.

    This function traverses the graph once to compute RollupMetrics for
    each REQUIREMENT node. Metrics are stored in node._metrics as:
    - "rollup_metrics": The full RollupMetrics object
    - "referenced_pct": Coverage percentage (for convenience)

    Coverage is determined by outgoing edges from REQUIREMENT nodes:
    - The builder links TEST/CODE/REQ as children of the parent REQ
    - Edges have assertion_targets when they target specific assertions
    - VERIFIES to TEST with assertion_targets → DIRECT coverage
    - IMPLEMENTS to CODE with assertion_targets → DIRECT coverage
    - IMPLEMENTS to CODE → VERIFIES to TEST → INDIRECT coverage (transitive)
    - IMPLEMENTS to REQ with assertion_targets → EXPLICIT coverage
    - IMPLEMENTS to REQ without assertion_targets → INFERRED coverage

    REFINES edges do NOT contribute to coverage (EdgeKind.contributes_to_coverage()).

    Test-specific metrics:
    - direct_tested: Assertions with TEST nodes (not CODE)
    - validated: Assertions with passing RESULTs
    - has_failures: Any RESULT is failed/error

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

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):

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
        tested_labels: set[str] = set()  # Assertions with targeted TEST coverage
        tested_indirect_labels: set[str] = set()  # Assertions with whole-req TEST coverage
        validated_labels: set[str] = set()  # Assertions with passing tests
        has_failures = False

        # Implements: REQ-d00069-B
        # Compute TEST (VERIFIES) coverage contributions via shared helper
        test_contribs, test_nodes_for_result_lookup = _compute_coverage_from_source(
            node,
            assertion_labels,
            EdgeKind.VERIFIES,
            CoverageSource.DIRECT,
            CoverageSource.INDIRECT,
        )
        for c in test_contribs:
            metrics.add_contribution(c)
            if c.source_type == CoverageSource.DIRECT:
                tested_labels.add(c.assertion_label)
            elif c.source_type == CoverageSource.INDIRECT:
                tested_indirect_labels.add(c.assertion_label)

        # Implements: REQ-d00069-A
        # Compute JNY (VALIDATES) UAT coverage contributions via shared helper
        jny_contribs, jny_nodes_for_result_lookup = _compute_coverage_from_source(
            node,
            assertion_labels,
            EdgeKind.VALIDATES,
            CoverageSource.UAT_EXPLICIT,
            CoverageSource.UAT_INFERRED,
        )
        for c in jny_contribs:
            metrics.add_contribution(c)

        # Check outgoing edges from this requirement
        # The builder links CODE/REQ as children of parent REQ with assertion_targets
        for edge in node.iter_outgoing_edges():
            if not edge.kind.contributes_to_coverage():
                # REFINES doesn't count
                continue

            target_node = edge.target
            target_kind = target_node.kind

            if target_kind == NodeKind.TEST:
                # TEST already handled via _compute_coverage_from_source above;
                # skip to avoid double-counting
                pass

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

                # Transitive: CODE → TEST → RESULT (indirect test coverage)
                # Check if this CODE node has TEST children via VERIFIES edges
                for code_edge in target_node.iter_outgoing_edges():
                    if (
                        code_edge.kind == EdgeKind.VERIFIES
                        and code_edge.target.kind == NodeKind.TEST
                    ):
                        transitive_test = code_edge.target
                        # Credit assertions the CODE implements with INDIRECT coverage
                        code_assertion_targets = edge.assertion_targets
                        if code_assertion_targets:
                            for label in code_assertion_targets:
                                if label in assertion_labels:
                                    metrics.add_contribution(
                                        CoverageContribution(
                                            source_id=transitive_test.id,
                                            source_type=CoverageSource.INDIRECT,
                                            assertion_label=label,
                                        )
                                    )
                        else:
                            # CODE without assertion targets → all assertions
                            for label in assertion_labels:
                                metrics.add_contribution(
                                    CoverageContribution(
                                        source_id=transitive_test.id,
                                        source_type=CoverageSource.INDIRECT,
                                        assertion_label=label,
                                    )
                                )

                        # Track for RESULT lookup (use CODE's assertion_targets)
                        test_nodes_for_result_lookup.append((transitive_test, None))

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

                # Implements: REQ-d00069-A
                # UAT roll-up: unconditional, mirrors automated EXPLICIT/INFERRED.
                # If a child REQ implements this parent, UAT coverage from any JNY
                # validating the child also propagates to this parent.
                if edge.assertion_targets:
                    for label in edge.assertion_targets:
                        if label in assertion_labels:
                            metrics.add_contribution(
                                CoverageContribution(
                                    source_id=target_node.id,
                                    source_type=CoverageSource.UAT_EXPLICIT,
                                    assertion_label=label,
                                )
                            )
                else:
                    for label in assertion_labels:
                        metrics.add_contribution(
                            CoverageContribution(
                                source_id=target_node.id,
                                source_type=CoverageSource.UAT_INFERRED,
                                assertion_label=label,
                            )
                        )

        # Process TEST children to find RESULT nodes
        validated_indirect_labels: set[str] = set()
        for test_node, assertion_targets in test_nodes_for_result_lookup:
            for result in test_node.iter_children():
                if result.kind == NodeKind.RESULT:
                    status = (result.get_field("status", "") or "").lower()
                    if status in ("passed", "pass", "success"):
                        if assertion_targets:
                            # Assertion-targeted test: mark specific assertions
                            for label in assertion_targets:
                                if label in assertion_labels:
                                    validated_labels.add(label)
                        else:
                            # Whole-req test: mark all assertions as indirect-validated
                            for label in assertion_labels:
                                validated_indirect_labels.add(label)
                    elif status in ("failed", "fail", "failure", "error"):
                        has_failures = True

        # Implements: REQ-d00069-A
        # Process JNY children to find RESULT nodes (UAT)
        uat_validated_direct_labels: set[str] = set()
        uat_validated_indirect_labels: set[str] = set()
        uat_has_failures = False
        for jny_node, assertion_targets in jny_nodes_for_result_lookup:
            for result in jny_node.iter_children():
                if result.kind == NodeKind.RESULT:
                    status = (result.get_field("status", "") or "").lower()
                    if status in ("passed", "pass", "success"):
                        if assertion_targets:
                            for label in assertion_targets:
                                if label in assertion_labels:
                                    uat_validated_direct_labels.add(label)
                        else:
                            for label in assertion_labels:
                                uat_validated_indirect_labels.add(label)
                    elif status in ("failed", "fail", "failure", "error"):
                        uat_has_failures = True

        # Finalize metrics (computes aggregate coverage counts + implemented/uat_coverage dims)
        metrics.finalize()

        # Populate the tested, verified, and uat_verified dimensions
        metrics.populate_test_dimensions(
            tested_direct_labels=tested_labels,
            tested_indirect_labels=tested_indirect_labels,
            verified_direct_labels=validated_labels,
            verified_indirect_labels=validated_indirect_labels,
            verified_failures=has_failures,
            uat_verified_direct_labels=uat_validated_direct_labels,
            uat_verified_indirect_labels=uat_validated_indirect_labels,
            uat_verified_failures=uat_has_failures,
        )

        # Compute code_tested dimension from coverage data
        _compute_code_tested(node, metrics)

        # Store in node metrics
        node.set_metric("rollup_metrics", metrics)


# =============================================================================
# Keyword Extraction (Phase 4)
# =============================================================================
# These functions extract and search keywords from requirement text.
# Keywords are stored in node._content["keywords"] as a list of strings.


# Default stopwords - common words filtered from keywords.
# NOTE: Normative keywords (shall, must, should, may, required) are NOT included
# as they have semantic meaning for requirements (RFC 2119).
DEFAULT_STOPWORDS = frozenset(
    [
        # Articles and determiners
        "a",
        "an",
        "the",
        "this",
        "that",
        "these",
        "those",
        # Pronouns
        "i",
        "you",
        "he",
        "she",
        "it",
        "we",
        "they",
        "me",
        "him",
        "her",
        "us",
        "them",
        # Prepositions
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "up",
        "about",
        "into",
        "through",
        "during",
        "before",
        "after",
        "above",
        "below",
        "between",
        # Conjunctions
        "and",
        "or",
        "but",
        "nor",
        "so",
        "yet",
        "both",
        "either",
        "neither",
        # Auxiliary verbs (excluding normative: shall, must, should, may)
        "is",
        "am",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "having",
        "do",
        "does",
        "did",
        "doing",
        "will",
        "would",
        "could",
        "might",
        "can",
        # Common verbs
        "get",
        "got",
        "make",
        "made",
        "let",
        # Other common words
        "not",
        "if",
        "when",
        "where",
        "how",
        "what",
        "which",
        "who",
        "whom",
        "whose",
        "all",
        "each",
        "every",
        "any",
        "some",
        "no",
        "none",
        "other",
        "such",
        "only",
        "own",
        "same",
        "than",
        "too",
        "very",
    ]
)

# Alias for backward compatibility
STOPWORDS = DEFAULT_STOPWORDS


@dataclass
class KeywordsConfig:
    """Configuration for keyword extraction."""

    stopwords: frozenset[str]
    min_length: int = 3

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KeywordsConfig:
        """Create config from dictionary.

        Args:
            data: Dict with optional 'stopwords' list and 'min_length' int.

        Returns:
            KeywordsConfig instance.
        """
        stopwords_list = data.get("stopwords")
        if stopwords_list is not None:
            stopwords = frozenset(stopwords_list)
        else:
            stopwords = DEFAULT_STOPWORDS

        return cls(
            stopwords=stopwords,
            min_length=data.get("min_length", 3),
        )


def extract_keywords(
    text: str,
    config: KeywordsConfig | None = None,
) -> list[str]:
    """Extract keywords from text.

    Extracts meaningful words by:
    - Lowercasing all text
    - Removing punctuation (except hyphens within words)
    - Filtering stopwords
    - Filtering words shorter than min_length
    - Deduplicating results

    Args:
        text: Input text to extract keywords from.
        config: Optional KeywordsConfig for custom stopwords/min_length.

    Returns:
        List of unique keywords in lowercase.
    """
    import re

    if not text:
        return []

    # Use provided config or defaults
    cfg = config or KeywordsConfig(stopwords=DEFAULT_STOPWORDS, min_length=3)

    # Lowercase and split into words
    text = text.lower()

    # Replace punctuation (except hyphens between letters) with spaces
    # Keep alphanumeric and hyphens
    text = re.sub(r"[^\w\s-]", " ", text)

    # Split on whitespace
    words = text.split()

    # Filter and deduplicate
    seen: set[str] = set()
    keywords: list[str] = []

    for word in words:
        # Strip leading/trailing hyphens
        word = word.strip("-")

        # Skip short words
        if len(word) < cfg.min_length:
            continue

        # Skip stopwords
        if word in cfg.stopwords:
            continue

        # Deduplicate
        if word not in seen:
            seen.add(word)
            keywords.append(word)

    return keywords


def annotate_keywords(
    graph: FederatedGraph,
    config: KeywordsConfig | None = None,
) -> None:
    """Extract and store keywords for all nodes with text content.

    Keywords are extracted based on node kind:
    - REQUIREMENT: title + child assertion text
    - ASSERTION: SHALL statement (label)
    - USER_JOURNEY: title + actor + goal + description
    - REMAINDER: label + raw_text
    - Others (CODE, TEST, RESULT): label only

    Keywords are stored in node._content["keywords"] as a list.

    Args:
        graph: The TraceGraph to annotate.
        config: Optional KeywordsConfig for custom stopwords/min_length.
    """
    from elspais.graph import NodeKind

    for node in graph.all_nodes():
        text_parts: list[str] = []

        # Get label (all nodes have this)
        label = node.get_label()
        if label:
            text_parts.append(label)

        # Add kind-specific text
        if node.kind == NodeKind.REQUIREMENT:
            # Include child assertion text
            for child in node.iter_children():
                if child.kind == NodeKind.ASSERTION:
                    child_text = child.get_label()
                    if child_text:
                        text_parts.append(child_text)

        elif node.kind == NodeKind.USER_JOURNEY:
            # Include actor, goal, description
            for field in ["actor", "goal", "description"]:
                value = node.get_field(field)
                if value:
                    text_parts.append(value)

        elif node.kind == NodeKind.REMAINDER:
            # Include raw text
            raw = node.get_field("raw_text")
            if raw:
                text_parts.append(raw)

        # Extract and store keywords
        combined_text = " ".join(text_parts)
        keywords = extract_keywords(combined_text, config)
        node.set_field("keywords", keywords)


def find_by_keywords(
    graph: FederatedGraph,
    keywords: list[str],
    match_all: bool = True,
    kind: NodeKind | None = None,
) -> list[GraphNode]:
    """Find nodes containing specified keywords.

    Args:
        graph: The TraceGraph to search.
        keywords: List of keywords to search for.
        match_all: If True, node must contain ALL keywords (AND).
                   If False, node must contain ANY keyword (OR).
        kind: NodeKind to filter by, or None to search all nodes.

    Returns:
        List of matching GraphNode objects.
    """
    # Normalize search keywords to lowercase
    search_keywords = {k.lower() for k in keywords}

    results: list[GraphNode] = []

    # Choose iterator based on kind parameter
    if kind is not None:
        nodes = graph.nodes_by_kind(kind)
    else:
        nodes = graph.all_nodes()

    for node in nodes:
        node_keywords = set(node.get_field("keywords", []))

        if match_all:
            # All keywords must be present
            if search_keywords.issubset(node_keywords):
                results.append(node)
        else:
            # Any keyword must be present
            if search_keywords & node_keywords:
                results.append(node)

    return results


def collect_all_keywords(
    graph: FederatedGraph,
    kind: NodeKind | None = None,
) -> list[str]:
    """Collect all unique keywords from annotated nodes.

    Args:
        graph: The TraceGraph to scan.
        kind: NodeKind to filter by, or None to collect from all nodes.

    Returns:
        Sorted list of all unique keywords across matching nodes.
    """
    all_keywords: set[str] = set()

    # Choose iterator based on kind parameter
    if kind is not None:
        nodes = graph.nodes_by_kind(kind)
    else:
        nodes = graph.all_nodes()

    for node in nodes:
        node_keywords = node.get_field("keywords", [])
        all_keywords.update(node_keywords)

    return sorted(all_keywords)


__all__ = [
    "annotate_git_state",
    "annotate_graph_git_state",
    "annotate_display_info",
    "annotate_implementation_files",
    "count_by_level",
    "group_by_level",
    "count_by_repo",
    "count_by_coverage",
    "count_code_coverage",
    "count_with_code_refs",
    "count_by_git_status",
    "count_implementation_files",
    "collect_topics",
    "get_implementation_status",
    "annotate_coverage",
    # Keyword extraction
    "DEFAULT_STOPWORDS",
    "STOPWORDS",
    "KeywordsConfig",
    "extract_keywords",
    "annotate_keywords",
    "find_by_keywords",
    "collect_all_keywords",
]
