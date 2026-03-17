# Task 1: Create RepoEntry and FederatedGraph with Read-Only Methods

**Branch**: claude/cross-cutting-requirements-2Zd0c
**Ticket**: CUR-1082
**Status**: In Progress

## Description

Create `src/elspais/graph/federated.py` with `RepoEntry` dataclass and `FederatedGraph` class
implementing all read-only TraceGraph methods. Include `from_single()` classmethod, `repo_for()`,
`config_for()`, `iter_repos()`. Each method has a strategy comment.

## Applicable Assertions

- REQ-d00200-A: RepoEntry dataclass fields
- REQ-d00200-B: from_single() classmethod
- REQ-d00200-C: All read-only methods with strategy comments
- REQ-d00200-D: by_id strategy delegation
- REQ-d00200-E: aggregate strategy combining results
- REQ-d00200-F: Skip error-state repos
- REQ-d00200-G: repo_for() and config_for()
- REQ-d00200-H: iter_repos()

## Baseline

- 2698 passed, 299 deselected in 35.64s

## Test Summary

Created `tests/core/test_federated.py` with 18 tests in `TestFederatedGraphReadOnly` class:
- REQ-d00200-A (2 tests): RepoEntry dataclass fields and optional defaults
- REQ-d00200-B (1 test): from_single creates federation of one
- REQ-d00200-C (1 test): is_reachable_to_requirement delegation
- REQ-d00200-D (2 tests): find_by_id and has_root by_id delegation
- REQ-d00200-E (8 tests): Aggregate methods (iter_roots, all_nodes, node_count, etc.)
- REQ-d00200-F (1 test): Aggregate methods skip error-state repos
- REQ-d00200-G (2 tests): repo_for and config_for lookups
- REQ-d00200-H (1 test): iter_repos yields all entries including errors

## Implementation Summary

Created `src/elspais/graph/federated.py`:
- `RepoEntry` dataclass with all fields per spec
- `FederatedGraph` class with:
  - `from_single()` classmethod for federation-of-one
  - `_ownership` dict built from sub-graph indexes
  - `_live_graphs()` helper that skips None graphs
  - All read-only methods with strategy comments
  - `repo_for()`, `config_for()`, `iter_repos()` for repo access

## Verification

- 18/18 FederatedGraph tests pass
- 2716 passed, 299 deselected (full suite)
- Lint clean (ruff)
