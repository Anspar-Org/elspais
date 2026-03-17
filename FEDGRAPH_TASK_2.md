# Task 2: Add Mutation Methods and target_graph Parameter

**Branch**: claude/cross-cutting-requirements-2Zd0c
**Ticket**: CUR-1082
**Status**: In Progress

## Description

Add mutation methods to FederatedGraph that delegate to the owning sub-graph.
Implement unified mutation log with lightweight pointers. Add undo support.
Add `target_graph` parameter to `TraceGraph.add_edge()` for cross-graph wiring.

## Applicable Assertions

- REQ-d00201-A: by_id mutation delegation with ownership update
- REQ-d00201-B: unified mutation log with repo pointers
- REQ-d00201-C: undo_last/undo_to delegation
- REQ-d00201-D: add_requirement with target_repo
- REQ-d00201-E: cross-graph mutations
- REQ-d00201-F: mutation_log property compatibility
- REQ-d00201-G: clone() federation-aware

## Baseline

- 2716 passed, 299 deselected in 35.11s

## Test Summary

Added `TestFederatedGraphMutations` class with 12 tests to `tests/core/test_federated.py`:
- REQ-d00201-A (4 tests): rename_node, update_title, change_status, delete_requirement
- REQ-d00201-B (1 test): mutation_log records entries
- REQ-d00201-C (2 tests): undo_last, undo_to delegation
- REQ-d00201-D (1 test): add_requirement to root repo
- REQ-d00201-E (2 tests): add_edge, delete_edge
- REQ-d00201-F (1 test): mutation_log iter_entries compatibility
- REQ-d00201-G (1 test): clone independence

## Implementation Summary

Extended `src/elspais/graph/federated.py` with:
- `FederatedMutationPointer` dataclass for lightweight log entries
- `FederatedMutationLog` class with iter_entries(), clear(), pop(), entries_since()
- All by_id mutation methods delegating to owning sub-graph with ownership updates
- All cross-graph mutation methods (add_edge, delete_edge, change_edge_kind, etc.)
- add_requirement with target_repo parameter
- clone() via copy.deepcopy
- undo_last/undo_to reading federated log and delegating to correct sub-graph
- _rebuild_ownership() for undo consistency

Note: target_graph parameter on TraceGraph.add_edge() deferred — not needed for
federation-of-one. Cross-graph edge wiring will add it in Chunk 2.

## Verification

- 30/30 FederatedGraph tests pass
- 2728 passed, 299 deselected (full suite)
- Lint clean (ruff)
