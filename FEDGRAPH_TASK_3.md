# Task 3: Make build_graph() Return FederatedGraph and Fix All Consumers

**Branch**: claude/cross-cutting-requirements-2Zd0c
**Ticket**: CUR-1082
**Status**: In Progress

## Description

Modify build_graph() to wrap result in FederatedGraph.from_single(). Export from
`graph/__init__.py`. Update test helper. Fix all consumers (type hints, internal access).

## Baseline

- 2728 passed, 299 deselected in 34.78s

## Implementation Summary

1. Modified `factory.py`: build_graph() wraps result in FederatedGraph.from_single()
2. Added `FederatedGraph.empty()` classmethod for error fallbacks
3. Added `repo_root`, `hash_mode`, `satellite_kinds` convenience properties
4. Exported FederatedGraph from `graph/__init__.py`
5. Updated 14 source files: TraceGraph type hints -> FederatedGraph
   - 11 TYPE_CHECKING imports (analysis, annotators, link_suggest, test_code_linker,
     render, serialize, summary, trace, index, health, generator)
   - 3 runtime imports (server/app, mcp/server, pdf/assembler)
6. Fixed server/app.py: g._mutation_log -> g.mutation_log
7. Fixed mcp/server.py: TraceGraph() fallback -> FederatedGraph.empty()
8. Fixed 1 test: _orphaned_ids access -> public orphaned_nodes() API

## Verification

- 2728 passed, 299 deselected (full suite)
- Lint clean (ruff)
- Doc sync passes
