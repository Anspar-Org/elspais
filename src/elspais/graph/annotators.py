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

import functools
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from elspais.config.schema import ElspaisConfig
from elspais.utilities.test_identity import build_test_id_from_nodeid

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


# Implements: REQ-d00254-A+B+F
@dataclass(frozen=True)
class CoverageCreditConfig:
    """CUR-1533 crediting config, derived from [[scanning.test.targets]]."""

    app_dirs: tuple[str, ...] = ()
    unmatched_credit: str = "off"  # "off" | "verified"
    coverage_dirs: tuple[str, ...] = ()
    assertion_credit: str = "off"  # "off" | "tested" | "verified"
    min_coverage_fraction: float = 0.0


# Implements: REQ-d00254-A
def _match_app_dir(path: str | None, app_dirs: tuple[str, ...]) -> str | None:
    """Return the app dir whose segments appear deepest in ``path``.

    Matches each app dir as a contiguous run of path segments; when several
    match, the one starting at the greatest segment index wins (tiebreak:
    longer dir string). Returns None when nothing matches.
    """
    if not path:
        return None
    segs = [s for s in path.replace("\\", "/").split("/") if s]
    best: str | None = None
    best_key: tuple[int, int] = (-1, -1)
    for d in app_dirs:
        dparts = [s for s in d.strip("/").replace("\\", "/").split("/") if s]
        if not dparts:
            continue
        for i in range(len(segs) - len(dparts) + 1):
            if segs[i : i + len(dparts)] == dparts:
                key = (i, len(d))
                if key > best_key:
                    best_key = key
                    best = d
                break
    return best


# Implements: REQ-d00254-A
def _compute_app_status(graph, app_dirs: tuple[str, ...]) -> dict[str, str]:
    """Map app dir -> 'green'|'red' from RESULT node statuses (CUR-1533)."""
    from elspais.graph import NodeKind

    failed_by_app: dict[str, bool] = {}
    for r in graph.nodes_by_kind(NodeKind.RESULT):
        app = _match_app_dir(r.get_field("source_path"), app_dirs)
        if app is None:
            continue
        status = (r.get_field("status") or "").lower()
        is_fail = status in ("failed", "fail", "failure", "error")
        failed_by_app[app] = failed_by_app.get(app, False) or is_fail
    return {app: ("red" if failed else "green") for app, failed in failed_by_app.items()}


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
    config: dict | None = None,
) -> dict[str, int]:
    """Count requirements by coverage level.

    Args:
        graph: The TraceGraph to aggregate.
        config: Project config; coverage inclusion is gated by
            ``status_expects_implementation`` via ``tier_buckets`` (REQ-d00258-C).

    Returns:
        Dict with 'total', 'full_coverage', 'partial_coverage', 'no_coverage' counts.

    Note:
        Thin delegate to `graph.aggregation.tier_buckets()` (REQ-d00258-C),
        kept here for API compatibility. `failing` folds into `no_coverage`
        below only because the legacy dict has three buckets and the
        "implemented" dimension never sets `has_failures`, so `b.failing`
        is always 0 for this dimension -- the fold is a no-op guard.
    """
    from elspais.graph.aggregation import tier_buckets

    b = tier_buckets(graph, "implemented", config=config)
    return {
        "total": b.total,
        "full_coverage": b.full,
        "partial_coverage": b.partial,
        "no_coverage": b.missing + b.failing,
    }


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


# Implements: REQ-d00258-G
def _failing_targets(targets: list[str] | None, assertion_labels: list[str]) -> set[str]:
    """Labels a failing verified/UAT signal is attributed to (REQ-d00258-G).

    An assertion-targeted failure blames only its named labels (scoped to the
    requirement's own assertions); a blanket/whole-requirement failure blames
    every assertion, since it genuinely exercises them all. This mirrors the
    scoping the ``has_failures`` bookkeeping already uses, but keeps the blame
    per-assertion so a non-failing sibling is not reddened.
    """
    if targets:
        return {t for t in targets if t in assertion_labels}
    return set(assertion_labels)


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


def _compute_code_tested(
    node: GraphNode, metrics: RollupMetrics, region_cache: dict | None = None
) -> None:
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

        if impl_end == impl_start:
            owned = _block_region_lines(fn, region_cache if region_cache is not None else {}).get(
                impl_start, set()
            )
            for line_no in owned:
                impl_lines.add((rel_path, line_no))
        else:
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

    # Implements: REQ-d00254-G
    # Per-test attribution (coverage.py dynamic contexts, CUR-1568): a line
    # counts as DIRECT when one of its recorded contexts belongs to a test
    # that VERIFIES this requirement. Context string format (pytest-cov
    # `--cov-context=test`): "path::Class::func|run" or "path::func|run"
    # (also "|setup"/"|teardown" for fixture-phase execution). Only "|run"
    # contexts credit direct attribution -- setup/teardown fixture execution
    # is not evidence the *test itself* exercised the line, so those phases
    # are deliberately excluded rather than treated as equivalent to "|run".
    direct_count = _direct_context_count(node, lines_by_file)

    metrics.code_tested = CoverageDimension(
        total=len(impl_lines),
        direct=direct_count,
        indirect=indirect_count,
        has_failures=False,
    )


@functools.lru_cache(maxsize=4096)
def _normalize_run_context(ctx: str) -> str | None:
    """Return the canonical TEST node id for a coverage.py context string.

    Returns None when the context should not credit direct attribution:
    the empty/global context (code executed outside any test), or a
    "|setup"/"|teardown" fixture-phase context (see CUR-1568 decision above
    -- only "|run" contexts count). Reuses ``build_test_id_from_nodeid`` (the
    canonical pytest-nodeid normalizer) rather than re-parsing nodeids here.

    Pure str -> str|None mapping over a small alphabet of context strings
    (one per test x phase) reused across many lines/requirements in a single
    annotation pass, so it is memoized with ``lru_cache`` (CUR-1568).
    """
    nodeid, sep, phase = ctx.rpartition("|")
    if not sep or phase != "run" or not nodeid:
        return None
    return build_test_id_from_nodeid(nodeid)


def _direct_context_count(node: GraphNode, lines_by_file: dict[str, set[int]]) -> int:
    """Count implementation lines directly attributed to a verifying test.

    Collects the TEST node ids reachable via this requirement's outgoing
    VERIFIES edges, then checks each implementation line's recorded
    ``line_contexts`` (set on the FILE node by coverage.json ingestion) for a
    context that normalizes to one of those TEST ids.
    """
    from elspais.graph import NodeKind
    from elspais.graph.relations import EdgeKind

    verifying_test_ids: set[str] = set()
    for edge in node.iter_outgoing_edges():
        if edge.kind != EdgeKind.VERIFIES:
            continue
        target = edge.target
        if target.kind != NodeKind.TEST:
            continue
        verifying_test_ids.add(target.id)

    if not verifying_test_ids:
        return 0

    # Collect line_contexts per file from this requirement's IMPLEMENTS edges
    # (same traversal shape as the line_coverage lookup above).
    file_contexts: dict[str, dict[int, list[str]]] = {}
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
        if not rel_path or rel_path in file_contexts:
            continue
        ctxs = fn.get_field("line_contexts")
        if ctxs:
            file_contexts[rel_path] = ctxs

    if not file_contexts:
        return 0

    direct_count = 0
    for rel_path, lines in lines_by_file.items():
        ctxs = file_contexts.get(rel_path)
        if not ctxs:
            continue
        for line_no in lines:
            line_ctx_ids = {
                _normalize_run_context(c) for c in ctxs.get(line_no, []) if isinstance(c, str)
            }
            line_ctx_ids.discard(None)
            if line_ctx_ids & verifying_test_ids:
                direct_count += 1

    return direct_count


def _under_dirs(rel_path: str, dirs: tuple[str, ...]) -> bool:
    """True if rel_path is within one of dirs. '.' (or empty dirs) matches all."""
    if not dirs or "." in dirs:
        return True
    return _match_app_dir(rel_path, dirs) is not None


# Implements: REQ-d00254-D
def _block_region_lines(file_node, cache: dict) -> dict:
    """Map each // Implements: marker line in a CODE file to the executable
    lines its *block* owns (CUR-1533 block-scoped attribution).

    A block is a run of marker lines with no executable (line_coverage) line
    strictly between consecutive markers; it owns the executable lines after
    its last marker up to the next block's first marker (or EOF). For languages
    without function detection (e.g. Dart) this lets a file-/block-scoped marker
    credit the code it precedes. Cached per FILE id for one annotate_coverage run.
    """
    from elspais.graph.GraphNode import NodeKind
    from elspais.graph.relations import EdgeKind

    fid = file_node.id
    if fid in cache:
        return cache[fid]
    result: dict[int, set[int]] = {}
    lc = file_node.get_field("line_coverage")
    if lc:
        markers = sorted(
            c.get_field("parse_line")
            for c in file_node.iter_children(edge_kinds={EdgeKind.CONTAINS})
            if c.kind == NodeKind.CODE
            and c.get_field("parse_line")
            and (c.get_field("parse_end_line") in (None, c.get_field("parse_line")))
        )
        cov = sorted(lc.keys())
        if markers:
            blocks: list[list[int]] = [[markers[0]]]
            for m in markers[1:]:
                prev = blocks[-1][-1]
                if any(prev < L < m for L in cov):
                    blocks.append([m])
                else:
                    blocks[-1].append(m)
            for i, blk in enumerate(blocks):
                last = blk[-1]
                nxt = blocks[i + 1][0] if i + 1 < len(blocks) else None
                owned = {L for L in cov if L > last and (nxt is None or L < nxt)}
                for m in blk:
                    result[m] = owned
    cache[fid] = result
    return result


# Implements: REQ-d00254-B
def _compute_lcov_tested(
    node, metrics, credit, app_status, region_cache: dict | None = None
) -> None:
    """Credit the lcov_tested dimension from covered // Implements: lines (CUR-1533)."""
    from elspais.graph import NodeKind
    from elspais.graph.metrics import CoverageDimension
    from elspais.graph.relations import EdgeKind

    if credit.assertion_credit == "off":
        return

    labels = [
        c.get_field("label", "")
        for c in node.iter_children()
        if c.kind == NodeKind.ASSERTION and c.get_field("label", "")
    ]
    if not labels:
        return

    direct_lines: dict[str, set[tuple[str, int]]] = {}
    blanket_lines: set[tuple[str, int]] = set()
    file_cov: dict[str, dict[int, int]] = {}
    file_app: dict[str, str | None] = {}

    for edge in node.iter_outgoing_edges():
        if edge.kind != EdgeKind.IMPLEMENTS:
            continue
        target = edge.target
        if target.kind != NodeKind.CODE:
            continue
        start = edge.metadata.get("impl_start_line")
        end = edge.metadata.get("impl_end_line")
        if not start:
            continue
        if not end:
            end = target.get_field("parse_end_line") or 0
        if not end or end < start:
            continue
        fn = target.file_node()
        if fn is None:
            continue
        rel = fn.get_field("relative_path")
        if not rel or not _under_dirs(rel, credit.coverage_dirs):
            continue
        lc = fn.get_field("line_coverage")
        if lc is None:
            continue
        file_cov.setdefault(rel, lc)
        file_app.setdefault(rel, _match_app_dir(rel, credit.app_dirs))
        if end == start:
            owned = _block_region_lines(fn, region_cache if region_cache is not None else {}).get(
                start, set()
            )
            rng = {(rel, ln) for ln in owned}
        else:
            rng = {(rel, ln) for ln in range(start, end + 1)}
        if edge.assertion_targets:
            for lbl in edge.assertion_targets:
                if lbl in labels:
                    direct_lines.setdefault(lbl, set()).update(rng)
        else:
            blanket_lines.update(rng)

    if not direct_lines and not blanket_lines:
        return

    def frac(lines: set[tuple[str, int]]) -> float:
        if not lines:
            return 0.0
        covered = sum(1 for (rel, ln) in lines if file_cov.get(rel, {}).get(ln, 0) > 0)
        return covered / len(lines)

    direct_pct: dict[str, float] = {}
    for lbl, lines in direct_lines.items():
        f = frac(lines)
        if f > 0 and f >= credit.min_coverage_fraction:
            direct_pct[lbl] = f

    indirect_pct: dict[str, float] = dict(direct_pct)
    if blanket_lines:
        bf = frac(blanket_lines)
        if bf > 0 and bf >= credit.min_coverage_fraction:
            for lbl in labels:
                indirect_pct.setdefault(lbl, bf)

    if not indirect_pct:
        return

    has_failures = False
    if credit.assertion_credit == "verified":
        apps = {file_app.get(rel) for rel in file_cov}
        has_failures = any(app_status.get(a) == "red" for a in apps if a)

    # A red app is a whole-application failure signal, so it attributes to every
    # lcov-credited assertion (there is no per-assertion granularity in app
    # status); an assertion with no lcov credit stays unblamed (REQ-d00258-G).
    failing_labels = set(indirect_pct) if has_failures else set()

    metrics.lcov_tested = CoverageDimension(
        total=len(labels),
        direct=sum(direct_pct.values()),
        indirect=sum(indirect_pct.values()),
        has_failures=has_failures,
        failing_labels=failing_labels,
        direct_labels=set(direct_pct),
        indirect_labels=set(indirect_pct),
        direct_pct_by_label=dict(direct_pct),
        indirect_pct_by_label=dict(indirect_pct),
    )


# Implements: REQ-d00255, REQ-d00256
@dataclass
class JourneyVerification:
    """Roll-up of a journey's UAT verification verdict.

    ``STEP : JOURNEY :: ASSERTION : REQUIREMENT``. A journey is verified by
    rolling up its steps' verifying tests (or, when it has no addressable
    steps, its own whole-journey verifying tests).

    Attributes:
        tier: One of "full", "partial", "failing", "missing". Mirrors the
            unified coverage-tier vocabulary (REQ-d00258).
        failing_steps: Labels (e.g. "step-2") of steps with a failing test.
        fully_verified: True iff every unit is verified with no failures;
            the journey's Validates targets may be credited.
        has_failures: True iff any verifying test failed.
        verified_steps: Count of steps verified (>=1 pass, 0 fail).
        total_steps: Count of addressable steps (0 for a whole-journey unit).
    """

    tier: str = "missing"
    failing_steps: list[str] = field(default_factory=list)
    fully_verified: bool = False
    has_failures: bool = False
    verified_steps: int = 0
    total_steps: int = 0

    @property
    def fraction(self) -> float:
        """Verified-step ratio in [0, 1] used to credit ``uat_verified``.

        A fully-verified journey credits full (1.0); a partial journey (some
        steps verified, none failing) credits its verified/total step ratio
        (e.g. 5 of 7 -> ~0.71 -> a partial standing / yellow); an unverified
        journey credits none (0.0). This proportional crediting is what lets a
        partially-verified journey read as "partial" rather than "missing"
        (REQ-d00255-C). Whole-journey (stepless) units have no ratio, so they
        credit full only when ``fully_verified`` (else 0.0).
        """
        # Implements: REQ-d00255-C
        if self.fully_verified:
            return 1.0
        if self.total_steps > 0:
            return self.verified_steps / self.total_steps
        return 0.0

    @property
    def verdict(self) -> str:
        """Simple display verdict for this journey.

        Returns:
            'fail'       if any verifying test failed.
            'pass'       if the journey is fully verified (all steps pass).
            'partial'    if some steps pass but not all.
            'unverified' if no verifying tests are recorded.
        """
        # Implements: REQ-d00255, REQ-d00256
        if self.has_failures:
            return "fail"
        if self.fully_verified:
            return "pass"
        if self.tier == "partial":
            return "partial"
        return "unverified"


_UAT_PASS = ("passed", "pass", "success")
_UAT_FAIL = ("failed", "fail", "failure", "error")


# Implements: REQ-d00255, REQ-d00256
def _node_verifying_status(node) -> tuple[bool, bool]:
    """Return ``(passed, failed)`` over the tests this node directly VERIFIES.

    Reads ``node``'s OUTGOING VERIFIES edges (node -> test) and each test's
    RESULT children (RESULT is a child of TEST via YIELDS). Classifies pass/fail
    with the same status vocabulary the automated TEST loop uses. Works for both
    a STEP (its step-scoped tests) and a JOURNEY (its whole-journey tests).
    """
    from elspais.graph.GraphNode import NodeKind
    from elspais.graph.relations import EdgeKind

    passed = failed = False
    for edge in node.iter_edges_by_kind(EdgeKind.VERIFIES):
        test_node = edge.target  # target = the verifying test
        for result in test_node.iter_children():
            if result.kind != NodeKind.RESULT:
                continue
            status = (result.get_field("status", "") or "").lower()
            if status in _UAT_PASS:
                passed = True
            elif status in _UAT_FAIL:
                failed = True
    return passed, failed


# Implements: REQ-d00255, REQ-d00256
def annotate_journey_verification(graph: FederatedGraph) -> None:
    """Roll each journey's verifying tests up into a ``JourneyVerification``.

    ``STEP : JOURNEY :: ASSERTION : REQUIREMENT``. A step is verified iff it has
    >=1 passing and 0 failing verifying tests. The journey rolls its steps up
    with the standard tier convention; a journey with no addressable steps uses
    its whole-journey verifying tests as a single implicit unit. The verdict is
    stored as the ``journey_verification`` node metric, which the per-REQ UAT
    consumer in :func:`annotate_coverage` reads to populate ``uat_verified``.
    """
    from elspais.graph.GraphNode import NodeKind
    from elspais.graph.relations import EdgeKind

    for journey in graph.iter_by_kind(NodeKind.USER_JOURNEY):
        steps = [
            c
            for c in journey.iter_children(edge_kinds={EdgeKind.STRUCTURES})
            if c.kind == NodeKind.STEP
        ]
        # Whole-journey tests (journey -> test) count toward every step.
        bpass, bfail = _node_verifying_status(journey)
        v = JourneyVerification()
        if steps:
            verified = 0
            for step in steps:
                label = step.get_field("label")  # "step-N"
                spass, sfail = _node_verifying_status(step)
                passed, failed = (spass or bpass), (sfail or bfail)
                status = "fail" if (sfail or bfail) else "pass" if (spass or bpass) else "untested"
                step.set_metric("step_status", status)
                if failed:
                    v.failing_steps.append(label)
                    v.has_failures = True
                elif passed:
                    verified += 1
                # else: untested step -> contributes to partial
            v.verified_steps = verified
            v.total_steps = len(steps)
            if v.has_failures:
                v.tier = "failing"
            elif verified == len(steps):
                v.tier = "full"
                v.fully_verified = True
            elif verified > 0:
                v.tier = "partial"
            else:
                v.tier = "missing"
        else:
            # Phase 2: no addressable steps -> the journey is one unit.
            if bfail:
                v.tier, v.has_failures = "failing", True
            elif bpass:
                v.tier, v.fully_verified = "full", True
            else:
                v.tier = "missing"
        journey.set_metric("journey_verification", v)


# Implements: REQ-p00061-A
def annotate_coverage(graph: FederatedGraph, credit: CoverageCreditConfig | None = None) -> None:
    """Compute and store coverage metrics for all requirement nodes.

    This function traverses the graph once to compute RollupMetrics for
    each REQUIREMENT node. Metrics are stored in node._metrics as:
    - "rollup_metrics": The full RollupMetrics object
    - "referenced_pct": Coverage percentage (for convenience)

    Coverage is determined by outgoing edges from REQUIREMENT nodes:
    - The builder links TEST/CODE/REQ as children of the parent REQ
    - Edges have assertion_targets when they target specific assertions
    - VERIFIES to TEST with assertion_targets → TEST_DIRECT (feeds `tested`)
    - VERIFIES to TEST without assertion_targets → TEST_INDIRECT (feeds `tested`)
      NOTE: test Verifies evidence feeds `tested`, NOT `implemented`
      (REQ-d00084-D).
    - IMPLEMENTS to CODE with assertion_targets → DIRECT coverage (implemented)
    - IMPLEMENTS to CODE → VERIFIES to TEST → INDIRECT coverage (transitive)
    - IMPLEMENTS to REQ with assertion_targets → EXPLICIT coverage
    - IMPLEMENTS to REQ without assertion_targets → INFERRED coverage

    REFINES edges add no coverage by themselves, but a second pass
    (_conduct_refines_coverage) conducts each refining requirement's own
    coverage upward into the targeted parent *Assertion* (REQ-d00069-J).

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

    if credit is None:
        credit = CoverageCreditConfig()
    app_status = _compute_app_status(graph, credit.app_dirs) if credit.app_dirs else {}
    region_cache: dict = {}

    # Build a per-file index of RESULT nodes with match=="source" (Task 5).
    # Maps repo-relative source_file -> list of status strings (lowercased).
    # Exclude per-test-resolved results (match_scope=="test"): those credit
    # inline (below) rather than via file-level all-pass/any-fail semantics.
    #
    # source_file_carried (CUR-1557) is a parallel map recording whether
    # EVERY contributing RESULT for that source file was carried (baseline).
    # It's file-granular (not per-status) since source_file_index itself only
    # retains status strings, not node identity; a file with a mix of
    # carried/fresh results is treated as NOT fully carried (safe default:
    # under-claim "carried" rather than mislabel fresh coverage as baseline).
    source_file_index: dict[str, list[str]] = {}
    _source_file_carried_flags: dict[str, list[bool]] = {}
    for r in graph.nodes_by_kind(NodeKind.RESULT):
        if (r.get_field("match") or "") == "source" and r.get_field("match_scope") != "test":
            sf = r.get_field("source_file")
            if sf:
                source_file_index.setdefault(sf, []).append((r.get_field("status") or "").lower())
                _source_file_carried_flags.setdefault(sf, []).append(bool(r.get_field("carried")))
    source_file_carried: dict[str, bool] = {
        sf: all(flags) for sf, flags in _source_file_carried_flags.items()
    }

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
        # REQ-d00258-G: per-assertion failure attribution. has_failures is the
        # requirement-wide flag (drives the requirement badge); this set records
        # WHICH assertions actually failed, so a partial sibling covered by a
        # different (non-failing) test does not inherit the red standing.
        verified_failing_labels: set[str] = set()

        # Implements: REQ-d00069-B, REQ-d00084-D
        # Compute TEST (VERIFIES) coverage contributions via shared helper.
        # These use dedicated TEST_* sources so they feed only the `tested`
        # dimension -- a test that Verifies an assertion is NOT evidence the
        # assertion is *implemented* (REQ-d00084-D). Using CoverageSource.DIRECT
        # here previously leaked test coverage into `implemented`.
        test_contribs, test_nodes_for_result_lookup = _compute_coverage_from_source(
            node,
            assertion_labels,
            EdgeKind.VERIFIES,
            CoverageSource.TEST_DIRECT,
            CoverageSource.TEST_INDIRECT,
        )
        for c in test_contribs:
            metrics.add_contribution(c)
            if c.source_type == CoverageSource.TEST_DIRECT:
                tested_labels.add(c.assertion_label)
            elif c.source_type == CoverageSource.TEST_INDIRECT:
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
                # REFINES is handled by the second pass (_conduct_refines_coverage),
                # which conducts the refining requirement's coverage upward.
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
        # CUR-1557: track whether every verified signal (pass credit or
        # failure flag, across all three credit paths below) came from a
        # carried (baseline) RESULT. verified_saw_signal stays False if this
        # requirement got no verified signal at all -- populate_test_dimensions
        # should then leave verified.carried at its default (False), not claim
        # baseline for coverage that doesn't exist.
        verified_saw_signal = False
        verified_all_carried = True
        for test_node, assertion_targets in test_nodes_for_result_lookup:
            saw_result = False
            for result in test_node.iter_children():
                if result.kind != NodeKind.RESULT:
                    continue
                # Implements: REQ-d00254-G
                # Skip inline only for FILE-scope source-match results (credited
                # via source_file_index below: all-pass credits / any-fail flags
                # the whole file). Per-test-resolved source results
                # (match_scope=="test") credit inline like test_id results:
                # their pass credits their assertions; their fail flags only
                # their own test.
                if (
                    (result.get_field("match") or "") == "source"
                    and not result.get_field("test_id")
                    and result.get_field("match_scope") != "test"
                ):
                    continue
                saw_result = True
                status = (result.get_field("status", "") or "").lower()
                if status in ("passed", "pass", "success"):
                    if assertion_targets:
                        for label in assertion_targets:
                            if label in assertion_labels:
                                validated_labels.add(label)
                    else:
                        for label in assertion_labels:
                            validated_indirect_labels.add(label)
                    verified_saw_signal = True
                    if not (result.get_field("carried") or False):
                        verified_all_carried = False
                elif status in ("failed", "fail", "failure", "error"):
                    has_failures = True
                    verified_failing_labels |= _failing_targets(assertion_targets, assertion_labels)
                    verified_saw_signal = True
                    if not (result.get_field("carried") or False):
                        verified_all_carried = False
            if not saw_result:
                fn = test_node.file_node()
                rel = fn.get_field("relative_path") if fn else None
                # Implements: REQ-d00254-G
                # Source-match file-granular path: match RESULT nodes by source_file.
                if rel and rel in source_file_index:
                    statuses = source_file_index[rel]
                    if any(s in ("failed", "fail", "failure", "error") for s in statuses):
                        has_failures = True
                        verified_failing_labels |= _failing_targets(
                            assertion_targets, assertion_labels
                        )
                        verified_saw_signal = True
                        if not source_file_carried.get(rel, False):
                            verified_all_carried = False
                    elif any(
                        s in ("passed", "pass", "success") for s in statuses
                    ):  # >=1 passed, none failed
                        if assertion_targets:
                            for label in assertion_targets:
                                if label in assertion_labels:
                                    validated_labels.add(label)
                        else:
                            for label in assertion_labels:
                                validated_indirect_labels.add(label)
                        verified_saw_signal = True
                        if not source_file_carried.get(rel, False):
                            verified_all_carried = False
                elif credit.unmatched_credit == "verified":
                    # Aggregate app-green path: derived from per-app green/red
                    # status, not a specific RESULT node, so carried-ness can't
                    # be recovered precisely here. Per the safe-ambiguity rule
                    # (CUR-1557), default this signal to fresh rather than risk
                    # mislabeling fresh coverage as "(baseline)".
                    app = _match_app_dir(rel, credit.app_dirs)
                    st = app_status.get(app) if app else None
                    if st == "green":
                        if assertion_targets:
                            for label in assertion_targets:
                                if label in assertion_labels:
                                    validated_labels.add(label)
                        else:
                            for label in assertion_labels:
                                validated_indirect_labels.add(label)
                        verified_saw_signal = True
                        verified_all_carried = False
                    elif st == "red":
                        has_failures = True
                        verified_failing_labels |= _failing_targets(
                            assertion_targets, assertion_labels
                        )
                        verified_saw_signal = True
                        verified_all_carried = False

        # Implements: REQ-d00069-A, REQ-d00255-C, REQ-d00256
        # UAT roll-up: source each validating journey's verdict from its
        # journey_verification metric (computed by annotate_journey_verification,
        # which rolls each journey's STEP/whole-journey verifying tests up). The
        # direct/indirect split still depends on whether Validates: named
        # assertions. Crediting is PROPORTIONAL to the journey's verification
        # (REQ-d00255-C): a fully-verified journey credits full (1.0); a
        # partially-verified journey with no failing step credits its
        # verified-step ratio (e.g. 5 of 7 -> ~0.71), which makes the named
        # assertions read "partial" (yellow) rather than "missing"; a journey
        # with any failing step contributes only a failure signal (-> red); an
        # unverified journey credits none (-> missing). Per-label fractions are
        # combined across journeys by max (a failure by any journey still flags
        # has_failures), mirroring how uat_coverage distinguishes blanket vs
        # assertion-targeted Validates.
        uat_direct_pct: dict[str, float] = {}
        uat_indirect_pct: dict[str, float] = {}
        uat_has_failures = False
        # REQ-d00258-G: per-assertion UAT failure attribution. A failing journey
        # legitimately blames every assertion THAT journey validates (its
        # assertion_targets, or all labels when it validates the whole REQ); the
        # bug being fixed is a DIFFERENT, non-failing journey's assertions
        # inheriting this red.
        uat_failing_labels: set[str] = set()
        for jny_node, assertion_targets in jny_nodes_for_result_lookup:
            v = jny_node.get_metric("journey_verification")
            if v is None:
                continue
            if v.has_failures:
                uat_has_failures = True
                uat_failing_labels |= _failing_targets(assertion_targets, assertion_labels)
                continue
            frac = v.fraction  # 1.0 full, verified/total for partial, 0 none
            if frac <= 0:
                continue  # unverified journey credits nothing
            if assertion_targets:
                for label in assertion_targets:
                    if label in assertion_labels:
                        uat_direct_pct[label] = max(uat_direct_pct.get(label, 0.0), frac)
            else:
                for label in assertion_labels:
                    uat_indirect_pct[label] = max(uat_indirect_pct.get(label, 0.0), frac)

        # Finalize metrics (computes aggregate coverage counts + implemented/uat_coverage dims)
        metrics.finalize()

        # Populate the tested, verified, and uat_verified dimensions
        metrics.populate_test_dimensions(
            tested_direct_labels=tested_labels,
            tested_indirect_labels=tested_indirect_labels,
            verified_direct_labels=validated_labels,
            verified_indirect_labels=validated_indirect_labels,
            verified_failures=has_failures,
            verified_carried=(verified_saw_signal and verified_all_carried),
            uat_verified_direct_pct=uat_direct_pct,
            uat_verified_indirect_pct=uat_indirect_pct,
            uat_verified_failures=uat_has_failures,
            verified_failing_labels=verified_failing_labels,
            uat_verified_failing_labels=uat_failing_labels,
        )

        # Compute code_tested dimension from coverage data
        _compute_code_tested(node, metrics, region_cache)
        _compute_lcov_tested(node, metrics, credit, app_status, region_cache)

        # Store in node metrics
        node.set_metric("rollup_metrics", metrics)

    # Implements: REQ-d00069-J
    # Second pass: conduct child coverage upward across REFINES edges so that a
    # parent *Assertion* refined by (partially) covered requirements inherits a
    # fractional share of that coverage.
    _conduct_refines_coverage(graph)


# Implements: REQ-d00069-J
# Dimensions that propagate upward across REFINES edges. ``code_tested`` is
# line-based (total == lines, not assertions) and is intentionally excluded.
_PROPAGATING_DIMENSIONS = (
    "implemented",
    "tested",
    "verified",
    "uat_coverage",
    "uat_verified",
)


# Implements: REQ-d00069-J
def _conduct_refines_coverage(graph: FederatedGraph) -> None:
    """Propagate child coverage up REFINES edges into parent assertions.

    A `Refines:` edge is stored outgoing from the *refined* requirement to its
    refining requirement, carrying ``assertion_targets`` that name which of the
    refined requirement's assertions are refined (empty == whole-requirement /
    blanket). A path edge adds no coverage by itself; instead each refining
    requirement contributes its own rolled-up coverage as one equal-weight
    incoming edge to the targeted parent *Assertion* (REQ-d00069-J).

    Per assertion A of requirement R (with N assertions), for each dimension and
    each strictness ``mode`` ("direct" = assertion-targeted only, "indirect" =
    also whole-requirement):

    - direct contributors = (1.0 if A has local direct leaf evidence) plus
      ``coverage(child)`` for every assertion-targeted REFINES edge naming A.
      If any direct contributor exists, A's value is their mean and indirect
      credit is ignored for A (REQ-d00069-J: only the *Assertion* with direct
      coverage forgoes indirect credit -- its siblings still accrue it).
    - else (A has no direct contributor), indirect mode credits A with the
      stronger of:
        * 1.0, if A has local whole-requirement leaf evidence (a whole-req test
          genuinely exercises every assertion); or
        * ``(1/N) * mean(coverage(child))`` over whole-requirement (blanket)
          REFINES edges. A blanket Refines names no assertion, so it is worth
          only one assertion's share (1/N) of its refining requirement's
          coverage -- averaged across blanket edges so a requirement refined by
          many whole-req children is not credited beyond one assertion's worth.

    ``coverage(child)`` is the child requirement's mean assertion coverage in
    the same dimension/mode, computed recursively (memoized, with a visited
    guard so an unexpected cycle degrades to 0 rather than recursing forever).
    """
    from elspais.graph import NodeKind

    reqs = list(graph.nodes_by_kind(NodeKind.REQUIREMENT))

    # Snapshot per-requirement assertion labels and local (pre-conduction) leaf
    # evidence so the recursion reads immutable input while we overwrite dims.
    labels_by_req: dict[str, list[str]] = {}
    # Snapshot the local per-label FRACTIONS (not just label membership) so
    # conduction preserves fractional local evidence. Most dimensions have
    # all-or-nothing local evidence (1.0), but uat_verified is fractional
    # (a partially-verified journey credits its verified-step ratio,
    # REQ-d00255-C); snapping it back to 1.0 here would discard that partial.
    local_evidence: dict[str, dict[str, tuple[dict[str, float], dict[str, float]]]] = {}
    for req in reqs:
        metrics = req.get_metric("rollup_metrics")
        if metrics is None:
            continue
        labels = [
            child.get_field("label", "")
            for child in req.iter_children()
            if child.kind == NodeKind.ASSERTION and child.get_field("label", "")
        ]
        labels_by_req[req.id] = labels
        ev: dict[str, tuple[dict[str, float], dict[str, float]]] = {}
        for dim_name in _PROPAGATING_DIMENSIONS:
            dim = getattr(metrics, dim_name)
            ev[dim_name] = (dict(dim.direct_pct_by_label), dict(dim.indirect_pct_by_label))
        local_evidence[req.id] = ev

    memo: dict[tuple[str, str, str], float] = {}

    def assertion_fraction(
        req: GraphNode,
        label: str,
        dim_name: str,
        mode: str,
        visiting: frozenset[str],
    ) -> float:
        direct_pct_local, indirect_pct_local = local_evidence[req.id][dim_name]
        direct_vals: list[float] = []
        local_direct = direct_pct_local.get(label, 0.0)
        if local_direct > 0:
            direct_vals.append(local_direct)
        blanket_refines_vals: list[float] = []
        for edge in req.iter_outgoing_edges():
            if not edge.kind.conducts_coverage():
                continue
            if edge.assertion_targets:
                if label in edge.assertion_targets:
                    direct_vals.append(req_coverage(edge.target, dim_name, mode, visiting))
            else:
                blanket_refines_vals.append(req_coverage(edge.target, dim_name, mode, visiting))

        if direct_vals:
            return sum(direct_vals) / len(direct_vals)
        if mode == "indirect":
            candidates: list[float] = []
            local_indirect = indirect_pct_local.get(label, 0.0)
            if local_indirect > 0:
                # Local whole-requirement leaf evidence (a whole-req test/code/
                # journey) exercises every assertion -> its own local fraction
                # (1.0 for all-or-nothing dims; the journey's verified-step
                # ratio for a partial uat_verified, REQ-d00255-C).
                candidates.append(local_indirect)
            if blanket_refines_vals:
                # A whole-requirement Refines names no assertion, so it is worth
                # only one assertion's share (1/N) of the refining requirement's
                # coverage, averaged across all such blanket edges.
                n_assertions = len(labels_by_req.get(req.id) or ()) or 1
                avg = sum(blanket_refines_vals) / len(blanket_refines_vals)
                candidates.append(avg / n_assertions)
            if candidates:
                return max(candidates)
        return 0.0

    def req_coverage(req: GraphNode, dim_name: str, mode: str, visiting: frozenset[str]) -> float:
        key = (dim_name, mode, req.id)
        cached = memo.get(key)
        if cached is not None:
            return cached
        if req.id in visiting:
            return 0.0  # cycle guard -- valid graphs are DAGs (CUR-1521)
        labels = labels_by_req.get(req.id)
        if not labels:
            memo[key] = 0.0
            return 0.0
        inner = visiting | {req.id}
        total = sum(assertion_fraction(req, lbl, dim_name, mode, inner) for lbl in labels)
        value = total / len(labels)
        memo[key] = value
        return value

    eps = 1e-9
    for req in reqs:
        metrics = req.get_metric("rollup_metrics")
        if metrics is None:
            continue
        labels = labels_by_req.get(req.id, [])
        if not labels:
            continue
        for dim_name in _PROPAGATING_DIMENSIONS:
            dim = getattr(metrics, dim_name)
            direct_pct = {
                lbl: assertion_fraction(req, lbl, dim_name, "direct", frozenset()) for lbl in labels
            }
            indirect_pct = {
                lbl: assertion_fraction(req, lbl, dim_name, "indirect", frozenset())
                for lbl in labels
            }
            dim.direct_pct_by_label = direct_pct
            dim.indirect_pct_by_label = indirect_pct
            dim.direct = sum(direct_pct.values())
            dim.indirect = sum(indirect_pct.values())
            dim.direct_labels = {lbl for lbl, v in direct_pct.items() if v > eps}
            dim.indirect_labels = {lbl for lbl, v in indirect_pct.items() if v > eps}


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
    "annotate_journey_verification",
    "JourneyVerification",
    # Keyword extraction
    "DEFAULT_STOPWORDS",
    "STOPWORDS",
    "KeywordsConfig",
    "extract_keywords",
    "annotate_keywords",
    "find_by_keywords",
    "collect_all_keywords",
]
