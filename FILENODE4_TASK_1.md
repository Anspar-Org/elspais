# Task 1: Satisfies/Template Instantiation Updates

**Branch**: claude/cross-cutting-requirements-2Zd0c
**Ticket**: CUR-1082
**Status**: Complete

## Objective

Template instantiation creates DEFINES edges from declaring FILE to INSTANCE nodes. Cloned subtrees use STRUCTURES edges internally. `file_node()` returns None for INSTANCE nodes.

## APPLICABLE_ASSERTIONS

- **REQ-d00128-J**: Template instantiation SHALL create DEFINES edges from declaring requirement's FILE node to each INSTANCE node
- **REQ-d00128-K**: INSTANCE nodes SHALL NOT have CONTAINS edges
- **REQ-d00128-L**: `file_node()` SHALL return None for INSTANCE nodes
- **REQ-p00014-B**: Cloned subtree uses STRUCTURES edges internally (already implemented, verify preserved)
- **REQ-d00127-D**: `file_node()` returns None if no FILE ancestor (general case)

## Key Files

- `src/elspais/graph/builder.py` -- `_instantiate_satisfies_templates()`
- `src/elspais/graph/GraphNode.py` -- `file_node()`
- `spec/07-graph-architecture.md` -- assertions J, K, L added to REQ-d00128
- `tests/core/test_satisfies.py` -- 6 new tests in TestSatisfiesFileNodeEdges

## Baseline

- 2570 tests passing before changes

## Tests Added

- `test_REQ_d00128_J_defines_edge_from_file_to_instance_root` -- DEFINES edge from FILE to cloned root
- `test_REQ_d00128_J_defines_edge_from_file_to_instance_assertions` -- DEFINES edges to cloned assertions
- `test_REQ_d00128_J_defines_edge_multiple_satisfies` -- Each declaring FILE gets its own DEFINES edges
- `test_REQ_d00128_K_instance_nodes_no_contains_edges` -- INSTANCE nodes have no CONTAINS edges
- `test_REQ_d00128_L_file_node_returns_none_for_instance` -- file_node() returns None for INSTANCE nodes
- `test_REQ_d00128_L_instance_original_has_file_node` -- Original template node still reachable via INSTANCE edge

## Implementation Summary

1. **builder.py** `_instantiate_satisfies_templates()`: After creating SATISFIES edge, find the declaring FILE via `declaring_node.file_node()` and create DEFINES edges from it to all cloned INSTANCE nodes.
2. **GraphNode.py** `file_node()`: Added early return of None when the node's stereotype is INSTANCE (checked via `get_field("stereotype")` with `getattr` to avoid circular import of Stereotype enum).

## Verification

- 2576 tests passing (2570 + 6 new), 94 deselected
- Lint clean (ruff)
- Doc sync tests pass (68 tests)
