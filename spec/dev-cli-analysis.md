# CLI Analysis Command

## REQ-d00124: Graph Analysis Engine

**Level**: DEV | **Status**: Draft | **Implements**: REQ-p00003

The `analysis` module SHALL provide read-only analytical functions that operate on a `TraceGraph` to rank requirements by foundational importance. The module SHALL NOT modify the graph or create parallel data structures.

## Assertions

A. The module SHALL compute PageRank-style centrality scores for requirement nodes by iterating on reversed edges (children distribute score to parents) with a configurable damping factor, converging within a tolerance threshold.

B. The module SHALL compute fan-in as the count of distinct direct parents (among included node kinds) for each node, identifying cross-cutting requirements that serve multiple independent areas.

C. The module SHALL compute uncovered dependent counts by walking descendants and counting leaf requirements with zero coverage.

D. The module SHALL produce a composite score by normalizing each metric to 0.0-1.0 and applying configurable weights (default 0.4 centrality, 0.3 fan-in, 0.3 uncovered).

E. The module SHALL filter nodes by `NodeKind`, defaulting to REQUIREMENT and ASSERTION, with ASSERTION nodes included in computation but excluded from ranked output.

F. The module SHALL rank actionable leaf nodes by summing the composite scores of their ancestors, surfacing the most impactful uncovered work items.

## Rationale

In a large requirements DAG, naive metrics like descendant count always favor the root node. PageRank centrality naturally handles DAGs and rewards cross-cutting dependencies. Combined with fan-in (how many independent areas depend on a node) and coverage gaps, this enables evidence-based prioritization of foundational work.

*End* *Graph Analysis Engine* | **Hash**: 00000000

---

## REQ-d00125: Analysis CLI Command

**Level**: DEV | **Status**: Draft | **Implements**: REQ-p00003

The `elspais analysis` command SHALL invoke the graph analysis engine and render ranked results in table or JSON format.

## Assertions

A. The command SHALL accept `--top N` to limit the number of results displayed (default 10).

B. The command SHALL accept `--weights W1,W2,W3` to configure the composite score weights.

C. The command SHALL accept `--format table|json` to select output format, defaulting to table.

D. The command SHALL accept `--show foundations|leaves|all` to select which sections to display, defaulting to all.

E. The command SHALL accept `--level prd|ops|dev` to filter results by requirement level.

F. The command SHALL accept `--include-code` to include CODE nodes in the analysis.

G. The table output SHALL display columns for Rank, ID, Title, Centrality, Fan-In, Uncovered, and Score.

H. The JSON output SHALL serialize the full `FoundationReport` structure.

## Rationale

A CLI command provides immediate visibility into which requirements are most foundational, enabling project planning without requiring MCP or viewer integration.

*End* *Analysis CLI Command* | **Hash**: 00000000
