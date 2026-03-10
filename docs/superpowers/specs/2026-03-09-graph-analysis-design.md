# Graph Analysis: Foundational Requirement Prioritization

**Date**: 2026-03-09
**Status**: Approved
**Command**: `elspais analysis`

## Problem

In a large requirements DAG, it's hard to know which requirements to work on first. The most "foundational" requirements -- those that affect the most other requirements -- should be prioritized, but naive metrics (descendant count) just echo tree depth. The root node always wins.

elspais uses a DAG (not a strict tree), so requirements can have multiple parents via `implements`/`refines` edges. This enables richer analysis than simple tree metrics.

## Goals

1. Rank requirements by foundational importance using multiple complementary metrics
2. Surface actionable work items (uncovered leaves) ranked by how foundational their ancestors are
3. Provide multiple analytical lenses: centrality, cross-cutting fan-in, uncovered dependents
4. Work as a read-only consumer of the existing `TraceGraph` -- no mutations, no new graph structures
5. Expose via CLI as `elspais analysis` with table and JSON output

## Non-Goals

- MCP tools (future, once analysis is validated)
- Viewer integration (future)
- Graph quality / structural issue detection (separate feature)
- Edge type cleanup tooling (separate task)
- Modifying `GraphNode`, `TraceGraph`, `GraphBuilder`, or any existing core files

## Architecture

### Module Placement

A single new module: `src/elspais/graph/analysis.py`

This mirrors how `annotators.py` works -- a module of pure functions that take a `TraceGraph` and return results. The difference: annotators mutate node metrics in-place, while analysis functions return ranked results without modifying the graph.

```text
src/elspais/graph/
  +-- GraphNode.py        # unchanged
  +-- builder.py          # unchanged
  +-- relations.py        # unchanged
  +-- metrics.py          # unchanged
  +-- annotators.py       # existing: coverage, git state
  +-- analysis.py         # NEW: centrality, fan-in, ranking
```

### CLI Command

New file: `src/elspais/commands/analysis.py`

## Data Structures

```python
@dataclass
class NodeScore:
    node_id: str
    label: str               # requirement title
    level: str               # PRD/OPS/DEV
    centrality: float        # PageRank-style score (0.0-1.0)
    descendant_count: int    # total transitive dependents
    fan_in_branches: int     # number of distinct root-level subtrees that depend on this
    uncovered_dependents: int  # leaf descendants with no coverage
    composite_score: float   # weighted combination for default ranking

@dataclass
class FoundationReport:
    ranked_nodes: list[NodeScore]      # all nodes, sorted by composite_score
    top_foundations: list[NodeScore]    # non-leaf nodes, top N
    actionable_leaves: list[NodeScore] # uncovered leaves ranked by parent importance
    graph_stats: dict                  # total nodes, edges, coverage summary
```

## Algorithms

### Centrality (PageRank-style)

Standard PageRank adapted for a DAG with reversed edge direction (parents are "important" because children point to them):

1. Initialize all included nodes with score `1/N`
2. Each iteration: each node distributes its score equally to its parents
3. Apply damping factor (0.85) -- 15% random jump prevents score pooling at roots
4. Converge after ~20-50 iterations (DAGs converge fast, no cycles)

No external dependencies. ~30 lines operating on `iter_parents()`.

### Fan-In Branch Count

For each node, find all transitive dependents (walk down via `iter_children()`), then trace each back up to its root ancestors. Count distinct roots.

This answers: "how many independent product areas depend on this node?"

Optimization: precompute a `node_id -> set[root_ids]` mapping in a single pass, then for any node, union the root sets of all descendants.

### Uncovered Dependents

Walk descendants, count leaves with `coverage_pct == 0` in their rollup metrics. Requires `annotate_coverage()` to have been run first (which the graph builder already does).

### Composite Score

Normalize each metric to 0.0-1.0 range across all nodes, then:

```text
composite = w1 * centrality + w2 * norm_fan_in + w3 * norm_uncovered
```

Default weights: `0.4 / 0.3 / 0.3`. Configurable via CLI `--weights`.

### Actionable Leaves Ranking

For each leaf node with no coverage, sum the `composite_score` of all its ancestors. Higher sum = "this leaf serves more important foundations."

## Node Filtering

Default: include `REQUIREMENT` and `ASSERTION` nodes only.

- `TEST`, `TEST_RESULT`, `CODE`, `REMAINDER`, `USER_JOURNEY` excluded by default
- Assertions are included for uncovered-dependents counting but don't appear in ranked output directly; they feed into the `uncovered_dependents` count on their parent requirement
- Optional `--include-code` flag adds `CODE` nodes to the analysis
- Centrality computation follows edges only between included node kinds, creating a virtual subgraph without copying

## Function Signatures

```python
def analyze_centrality(
    graph: TraceGraph,
    include_kinds: set[NodeKind],
    damping: float = 0.85,
    max_iterations: int = 50,
    tolerance: float = 1e-6,
) -> dict[str, float]:
    """Return {node_id: centrality_score} for included nodes."""

def analyze_fan_in(
    graph: TraceGraph,
    include_kinds: set[NodeKind],
) -> dict[str, int]:
    """Return {node_id: distinct_root_count} for included nodes."""

def analyze_foundations(
    graph: TraceGraph,
    include_kinds: set[NodeKind] | None = None,  # defaults to {REQUIREMENT, ASSERTION}
    weights: tuple[float, float, float] = (0.4, 0.3, 0.3),
    top_n: int = 10,
) -> FoundationReport:
    """Full foundation analysis combining all metrics.

    Assertions are included in computation (for uncovered_dependents counting)
    but filtered from ranked output -- only REQUIREMENT nodes appear in results.
    Descendant counts are computed internally alongside the other metrics.
    Coverage is read via node.get_metric("coverage_pct", 0).
    """
```

## CLI Interface

```text
$ elspais analysis [PATH] [OPTIONS]

Options:
  --top N              Number of top results to show (default: 10)
  --weights W1,W2,W3   Centrality, fan-in, uncovered weights (default: 0.4,0.3,0.3)
  --include-code       Include CODE nodes in the analysis
  --show SECTION       Which section(s) to show: foundations, leaves, all (default: all)
  --format FORMAT      Output format: table, json (default: table)
  --level LEVEL        Filter results to a specific level: prd, ops, dev
```

### Example Output

```text
Foundation Analysis for hht_diary
=================================

Top Foundations:
  Rank  ID           Title                    Centrality  Fan-In  Uncovered  Score
  ----  -----------  -----------------------  ----------  ------  ---------  -----
    1   REQ-p00042   Audit Logging System         0.31       5        12     0.87
    2   REQ-p00018   Authentication Module         0.24       4         8     0.71
    3   REQ-p00033   Data Validation Layer         0.19       4         6     0.64

Most Impactful Work Items:
  Rank  ID           Title                    Serves                          Score
  ----  -----------  -----------------------  ------------------------------  -----
    1   REQ-d00087   Audit event serializer   Audit Logging (#1)              0.87
    2   REQ-d00091   Auth token refresh       Authentication (#2)             0.71
    3   REQ-d00055   Input sanitization       Data Validation (#3)            0.64
```

### JSON Output

`--format json` serializes the `FoundationReport` dataclass for programmatic consumption, enabling future MCP tool or viewer integration.

## Edge Treatment

All edge types (`IMPLEMENTS`, `REFINES`) are treated equally for importance analysis. Both represent real dependencies. The semantic difference (coverage contribution vs. detail refinement) matters for coverage tracking but not for structural importance.

## Dependencies

None beyond stdlib. The PageRank implementation is pure iteration over the existing graph iterator API.

## Future Directions

- **MCP tool**: `analyze_foundations()` exposed as an MCP tool once validated
- **Viewer integration**: highlight top-ranked nodes, sort hierarchy by score
- **Graph quality signals**: surface misplaced relationships, redundant edges
- **Trend tracking**: compare analysis results across commits/branches
