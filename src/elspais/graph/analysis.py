# Implements: REQ-d00124
"""Graph analysis — foundational requirement prioritization.

Read-only analytical functions that operate on a TraceGraph to rank
requirements by foundational importance. Does not modify the graph.

Three complementary metrics:
- PageRank centrality (cross-cutting importance)
- Fan-in branch count (distinct root subtrees depending on a node)
- Uncovered dependents (leaf nodes with zero coverage)
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import TYPE_CHECKING

from elspais.graph.GraphNode import GraphNode, NodeKind

if TYPE_CHECKING:
    from elspais.graph.builder import TraceGraph


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class NodeScore:
    """Score for a single requirement node."""

    node_id: str
    label: str
    level: str
    centrality: float
    descendant_count: int
    fan_in_branches: int
    uncovered_dependents: int
    composite_score: float


@dataclass
class FoundationReport:
    """Full analysis report."""

    ranked_nodes: list[NodeScore]
    top_foundations: list[NodeScore]
    actionable_leaves: list[NodeScore]
    graph_stats: dict


# ---------------------------------------------------------------------------
# Default node kinds
# ---------------------------------------------------------------------------

_DEFAULT_KINDS: frozenset[NodeKind] = frozenset({NodeKind.REQUIREMENT, NodeKind.ASSERTION})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _collect_included(graph: TraceGraph, include_kinds: set[NodeKind]) -> dict[str, GraphNode]:
    """Collect included nodes as {id: node} dict, avoiding redundant lookups."""
    result: dict[str, GraphNode] = {}
    for kind in include_kinds:
        for node in graph.nodes_by_kind(kind):
            result[node.id] = node
    return result


# ---------------------------------------------------------------------------
# Centrality (PageRank-style)
# ---------------------------------------------------------------------------


def analyze_centrality(
    graph: TraceGraph,
    include_kinds: set[NodeKind],
    damping: float = 0.85,
    max_iterations: int = 50,
    tolerance: float = 1e-6,
) -> dict[str, float]:
    """Return {node_id: centrality_score} for included nodes.

    Uses PageRank with reversed edges: children distribute score to parents.
    Nodes with many children pointing to them score higher.
    """
    included = _collect_included(graph, include_kinds)
    included_ids = list(included.keys())
    n = len(included_ids)
    if n == 0:
        return {}
    if n == 1:
        return {included_ids[0]: 1.0}

    # Build parent map (only among included nodes)
    parent_map: dict[str, list[str]] = defaultdict(list)
    for nid, node in included.items():
        for parent in node.iter_parents():
            if parent.id in included:
                parent_map[nid].append(parent.id)

    # Initialize scores
    scores: dict[str, float] = dict.fromkeys(included_ids, 1.0 / n)
    teleport = (1.0 - damping) / n

    for _ in range(max_iterations):
        # Each node distributes its score to its parents
        new_scores = dict.fromkeys(included_ids, teleport)
        for nid in included_ids:
            parents = parent_map.get(nid, [])
            if parents:
                share = damping * scores[nid] / len(parents)
                for pid in parents:
                    new_scores[pid] += share
            # Dangling nodes (no parents = roots): redistribute evenly
            if not parents:
                share = damping * scores[nid] / n
                for other in included_ids:
                    new_scores[other] += share

        # Check convergence
        diff = sum(abs(new_scores[nid] - scores[nid]) for nid in included_ids)
        scores = new_scores
        if diff < tolerance:
            break

    return scores


# ---------------------------------------------------------------------------
# Fan-in branch count
# ---------------------------------------------------------------------------


def analyze_fan_in(
    graph: TraceGraph,
    include_kinds: set[NodeKind],
) -> dict[str, int]:
    """Return {node_id: parent_count} for included nodes.

    Counts distinct direct parents (among included kinds) for each node.
    Nodes with multiple parents are cross-cutting — they serve multiple
    independent areas of the requirement graph.
    """
    included = _collect_included(graph, include_kinds)
    result: dict[str, int] = {}
    included_set = set(included.keys())

    for nid, node in included.items():
        count = sum(1 for p in node.iter_parents() if p.id in included_set)
        # Roots have 0 parents but are still "in 1 branch" (their own)
        result[nid] = max(count, 1) if node.kind == NodeKind.REQUIREMENT else count

    return result


# ---------------------------------------------------------------------------
# Uncovered dependents
# ---------------------------------------------------------------------------


def _count_uncovered_descendants(
    graph: TraceGraph,
    node_id: str,
    included_set: set[str],
) -> int:
    """Count leaf descendants (in included_set) with zero coverage."""
    count = 0
    visited: set[str] = set()
    queue: deque[str] = deque([node_id])

    while queue:
        nid = queue.popleft()
        if nid in visited:
            continue
        visited.add(nid)
        node = graph.find_by_id(nid)
        if node is None:
            continue

        # Check if this is a leaf among included nodes
        included_children = [c for c in node.iter_children() if c.id in included_set]

        if not included_children and nid != node_id:
            # Leaf node — check coverage
            coverage = node.get_metric("coverage_pct", 0)
            if coverage == 0:
                count += 1
        else:
            for child in included_children:
                if child.id not in visited:
                    queue.append(child.id)

    return count


# ---------------------------------------------------------------------------
# Descendant count
# ---------------------------------------------------------------------------


def _count_descendants(
    graph: TraceGraph,
    node_id: str,
    included_set: set[str],
) -> int:
    """Count all transitive descendants of node_id among included_set."""
    count = 0
    visited: set[str] = set()
    queue: deque[str] = deque([node_id])

    while queue:
        nid = queue.popleft()
        if nid in visited:
            continue
        visited.add(nid)
        if nid != node_id:
            count += 1
        node = graph.find_by_id(nid)
        if node is None:
            continue
        for child in node.iter_children():
            if child.id in included_set and child.id not in visited:
                queue.append(child.id)

    return count


# ---------------------------------------------------------------------------
# Foundation analysis (combines all metrics)
# ---------------------------------------------------------------------------


def _normalize(values: dict[str, float]) -> dict[str, float]:
    """Normalize values to 0.0-1.0 range."""
    if not values:
        return {}
    max_val = max(values.values())
    if max_val == 0:
        return dict.fromkeys(values, 0.0)
    return {k: v / max_val for k, v in values.items()}


def analyze_foundations(
    graph: TraceGraph,
    include_kinds: set[NodeKind] | None = None,
    weights: tuple[float, float, float] = (0.4, 0.3, 0.3),
    top_n: int = 10,
) -> FoundationReport:
    """Full foundation analysis combining all metrics.

    Assertions are included in computation (for uncovered_dependents counting)
    but filtered from ranked output -- only REQUIREMENT nodes appear in results.
    Descendant counts are computed internally alongside the other metrics.
    Coverage is read via node.get_metric("coverage_pct", 0).
    """
    if include_kinds is None:
        include_kinds = set(_DEFAULT_KINDS)

    # Precompute included nodes once
    included = _collect_included(graph, include_kinds)
    included_set = set(included.keys())

    # Compute individual metrics
    centrality = analyze_centrality(graph, include_kinds)
    fan_in = analyze_fan_in(graph, include_kinds)

    # Compute uncovered dependents and descendant counts per requirement
    uncovered: dict[str, int] = {}
    descendants: dict[str, int] = {}
    req_nodes: dict[str, GraphNode] = {}
    for nid, node in included.items():
        if node.kind == NodeKind.REQUIREMENT:
            req_nodes[nid] = node
            uncovered[nid] = _count_uncovered_descendants(graph, nid, included_set)
            descendants[nid] = _count_descendants(graph, nid, included_set)

    # Normalize metrics for composite scoring
    norm_centrality = _normalize({k: v for k, v in centrality.items() if k in req_nodes})
    norm_fan_in = _normalize({k: float(v) for k, v in fan_in.items() if k in req_nodes})
    norm_uncovered = _normalize({k: float(v) for k, v in uncovered.items()})

    w_c, w_f, w_u = weights

    # Build NodeScore for each requirement node
    scored: list[NodeScore] = []
    for nid, node in req_nodes.items():
        composite = (
            w_c * norm_centrality.get(nid, 0.0)
            + w_f * norm_fan_in.get(nid, 0.0)
            + w_u * norm_uncovered.get(nid, 0.0)
        )
        scored.append(
            NodeScore(
                node_id=nid,
                label=node.get_label(),
                level=node.level or "",
                centrality=centrality.get(nid, 0.0),
                descendant_count=descendants.get(nid, 0),
                fan_in_branches=fan_in.get(nid, 0),
                uncovered_dependents=uncovered.get(nid, 0),
                composite_score=composite,
            )
        )

    # Sort by composite score descending
    scored.sort(key=lambda s: s.composite_score, reverse=True)

    # Split into foundations (non-leaf) and actionable leaves
    top_foundations: list[NodeScore] = []
    actionable_leaves: list[NodeScore] = []

    for ns in scored:
        node = req_nodes.get(ns.node_id)
        if node is None:
            continue
        has_included_children = any(c.id in included_set for c in node.iter_children())
        if has_included_children:
            top_foundations.append(ns)
        elif ns.uncovered_dependents > 0 or node.get_metric("coverage_pct", 0) == 0:
            actionable_leaves.append(ns)

    # Re-rank actionable leaves by sum of ancestor composite scores
    composite_by_id = {ns.node_id: ns.composite_score for ns in scored}
    leaf_importance: list[tuple[NodeScore, float]] = []
    for ns in actionable_leaves:
        node = req_nodes.get(ns.node_id)
        if node is None:
            continue
        ancestor_sum = 0.0
        visited: set[str] = set()
        queue: deque[str] = deque()
        for p in node.iter_parents():
            if p.id in composite_by_id:
                queue.append(p.id)
        while queue:
            pid = queue.popleft()
            if pid in visited:
                continue
            visited.add(pid)
            ancestor_sum += composite_by_id.get(pid, 0.0)
            pnode = graph.find_by_id(pid)
            if pnode is not None:
                for gp in pnode.iter_parents():
                    if gp.id in composite_by_id and gp.id not in visited:
                        queue.append(gp.id)
        leaf_importance.append((ns, ancestor_sum))

    leaf_importance.sort(key=lambda x: x[1], reverse=True)
    actionable_leaves = [ns for ns, _ in leaf_importance]

    # Apply top_n limits
    top_foundations = top_foundations[:top_n]
    actionable_leaves = actionable_leaves[:top_n]

    # Graph stats
    graph_stats = {
        "total_nodes": graph.node_count(),
        "included_nodes": len(included_set),
        "requirement_nodes": len(scored),
    }

    return FoundationReport(
        ranked_nodes=scored,
        top_foundations=top_foundations,
        actionable_leaves=actionable_leaves,
        graph_stats=graph_stats,
    )
