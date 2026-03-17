# Task 4: ID Conflict Detection and Cross-Graph Edge Wiring

**Branch**: claude/cross-cutting-requirements-2Zd0c
**Ticket**: CUR-1082
**Status**: In Progress

## Description

Detect duplicate IDs across repos (hard error). Wire cross-graph edges by
resolving broken references across sub-graphs. Add target_graph parameter
to TraceGraph.add_edge() for cross-graph resolution.

## Baseline

- 2739 passed, 299 deselected
