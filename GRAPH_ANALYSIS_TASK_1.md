# Task 1: Create graph/analysis.py — data structures and algorithms

## Description

Create `src/elspais/graph/analysis.py` with PageRank centrality, fan-in branch count, uncovered dependents, composite scoring, and foundation report generation.

## Spec

`docs/superpowers/specs/2026-03-09-graph-analysis-design.md`

## APPLICABLE_ASSERTIONS

- REQ-d00124-A: PageRank centrality with damping factor and convergence
- REQ-d00124-B: Fan-in branch counts (distinct root subtrees)
- REQ-d00124-C: Uncovered dependent counts (leaf reqs with zero coverage)
- REQ-d00124-D: Composite score with normalizable weights
- REQ-d00124-E: Node filtering by NodeKind, assertions in computation but not output
- REQ-d00124-F: Actionable leaves ranked by ancestor composite scores

## Tests

- 16 tests in `tests/core/test_graph/test_analysis.py`
- All 6 assertions covered: centrality (4), fan-in (2), uncovered (2), composite (2), filtering (3), leaves (3)

## Implementation

- `src/elspais/graph/analysis.py`: NodeScore, FoundationReport, analyze_centrality, analyze_fan_in, analyze_foundations
- Uses `nodes_by_kind()` and `find_by_id()` per AGENT_DESIGN_PRINCIPLES
- Fan-in BFS traverses through all node kinds to avoid missing cross-kind paths
- Code reviewed and bugs fixed before commit

## Verification

- 16/16 tests pass
- Full suite: 2338 passed, 74 deselected
