# MASTER PLAN — Unified Root vs Orphan Classification

**Branch**: `feature/CUR-514-viewtrace-port`
**Ticket**: CUR-240
**CURRENT_ASSERTIONS**: REQ-d00071-A, REQ-d00071-B, REQ-d00071-C, REQ-d00071-D

## Goal

Fix root identification so it distinguishes between **roots** (parentless nodes WITH meaningful children) and **orphans** (parentless nodes WITHOUT meaningful children). Currently all parentless REQUIREMENTs and all USER_JOURNEYs are unconditionally roots, even when disconnected.

## Model

- **Root** = parentless node WITH one or more meaningful children (anchors a subgraph)
- **Orphan** = parentless node WITHOUT meaningful children (disconnected/floating)
- **Satellite kinds** (ASSERTION, TEST_RESULT) = don't count as "meaningful children" — they're metadata, not graph structure

Examples:
- PRD with only assertions but no OPS/DEV implementations -> **orphan**
- TEST with only TEST_RESULT children but no requirement link -> **orphan**
- PRD with OPS children -> **root**
- TEST linked to a requirement -> not parentless, so neither root nor orphan

## Phase 1: Core builder changes

### Step 1: Define satellite kinds constant

**File**: `src/elspais/graph/builder.py` — module level near imports

```python
# Satellite kinds: children of these types don't count as "meaningful"
# for determining root vs orphan status
_SATELLITE_KINDS = frozenset({NodeKind.ASSERTION, NodeKind.TEST_RESULT})
```

- [x] Add `_SATELLITE_KINDS` constant

### Step 2: Rewrite root identification in `build()`

**File**: `src/elspais/graph/builder.py` — `build()` method (lines ~1926-1940)

Replace the current kind-specific root logic:
```python
# OLD: All parentless REQs + all journeys are roots
roots = [node for node in self._nodes.values()
         if node.is_root and node.kind == NodeKind.REQUIREMENT]
roots.extend(node for node in self._nodes.values()
             if node.kind == NodeKind.USER_JOURNEY)
root_ids = {r.id for r in roots}
orphaned_ids = self._orphan_candidates - root_ids
```

With unified logic:
```python
# Roots: parentless candidates with at least one meaningful child
roots = []
root_ids = set()
for node_id in self._orphan_candidates:
    node = self._nodes.get(node_id)
    if node and any(c.kind not in _SATELLITE_KINDS for c in node.iter_children()):
        roots.append(node)
        root_ids.add(node_id)

orphaned_ids = self._orphan_candidates - root_ids
```

- [x] Replace root identification block in `build()`

### Step 3: Track USER_JOURNEY as orphan candidate

**File**: `src/elspais/graph/builder.py` — `_add_journey()` (~line 1709)

Add `self._orphan_candidates.add(journey_id)` after node creation. Currently journeys are unconditionally roots; now they follow the same rule.

- [x] Add orphan candidate tracking for journeys

## Phase 2: CLI command cleanup

### Step 4: Remove domain-level REQUIREMENT check from analyze.py

**File**: `src/elspais/commands/analyze.py` — `_analyze_orphans()`

Remove the domain-level "non-PRD without parent requirements" loop (lines ~105-115). Under the new model, `graph.orphaned_nodes()` already catches these. The hierarchy issue (OPS without parent PRD but with children) is covered by `check_spec_hierarchy()` in health.py.

- [x] Remove domain-level REQUIREMENT loop from `_analyze_orphans()`

### Step 5: Same cleanup in health.py

**File**: `src/elspais/commands/health.py` — `check_spec_orphans()`

Remove the domain-level REQUIREMENT loop (lines ~667-673). Use only `graph.orphaned_nodes()`.

- [x] Remove domain-level REQUIREMENT loop from `check_spec_orphans()`

## Phase 3: Test updates

### Step 6: Fix tests with hardcoded root counts

Tests that will break and need updating:

| File | Test | Current Expectation | Fix |
|------|------|-------------------|-----|
| `tests/core/test_detection.py:50` | `test_no_orphans_when_all_linked` | `has_orphans() == False` | Add implementation children to make PRD a root |
| `tests/core/test_detection.py:63` | `test_orphan_without_implements` | `root_count() == 2` | Adjust — standalone REQs without children are now orphans |
| `tests/core/test_detection.py:78` | broken ref test | `root_count() == 2` | Adjust — broken-linked child is now orphan |
| `tests/core/test_builder.py:592` | `test_requirement_roots_not_orphans` | Both REQs not orphans | Both are now orphans (no meaningful children) |
| `tests/core/test_node_mutations.py:367` | `add_requirement_becomes_root` | `root_count() + 1` | New req without children is orphan, not root |
| `tests/mcp/test_mcp_core.py:143` | `returns_root_count` | `root_count == 1` | Depends on fixture — may need child REQ |
| `tests/core/test_serialize.py:149` | serialize metadata | `root_count == 1` | Depends on fixture — may need child REQ |

Strategy: Where possible, enrich fixtures to have meaningful children (more realistic). Where impractical, adjust expected values.

- [x] Fix `tests/core/test_detection.py` (~2 tests: orphan_without_implements, orphan_with_broken_reference)
- [x] Fix `tests/core/test_builder.py` (`test_requirement_roots_not_orphans` → orphan, `test_build_ignores_missing_targets`)
- [x] Fix `tests/core/test_node_mutations.py` (`build_simple_graph` enriched with child)
- [x] Fix `tests/core/test_integration/test_pipeline.py` (enriched fixture with REQ-o00004)
- [x] `tests/mcp/test_mcp_core.py` and `tests/core/test_serialize.py` — no changes needed (already passing)

### Step 7: New tests for unified classification

**File**: `tests/core/test_builder.py` — update `TestGeneralizedOrphanDetection`

| Test | Verifies |
|------|----------|
| `test_req_with_only_assertions_is_orphan` | PRD + assertions but no implementations = orphan |
| `test_req_with_child_req_is_root` | PRD implementing OPS = root |
| `test_test_with_only_results_is_orphan` | TEST + TEST_RESULT children but no REQ link = orphan |
| `test_journey_with_no_children_is_orphan` | Standalone USER_JOURNEY = orphan |
| `test_journey_with_req_children_is_root` | USER_JOURNEY linked to REQ = root |

- [x] Write new classification tests (use sub-agent) — 5 new tests added

## Files to Modify

| File | Change |
|------|--------|
| `src/elspais/graph/builder.py` | `_SATELLITE_KINDS` constant, rewrite root identification, track journeys |
| `src/elspais/commands/analyze.py` | Remove domain-level REQUIREMENT loop |
| `src/elspais/commands/health.py` | Remove domain-level REQUIREMENT loop |
| `tests/core/test_builder.py` | Update `TestGeneralizedOrphanDetection`, fix `test_requirement_roots_not_orphans` |
| `tests/core/test_detection.py` | Fix 3 tests with hardcoded root counts |
| `tests/core/test_node_mutations.py` | Fix `add_requirement_becomes_root` test |
| `tests/mcp/test_mcp_core.py` | Fix root count test |
| `tests/core/test_serialize.py` | Fix hardcoded root counts |

## Verification

1. `python -m pytest tests/ -x -q` — all tests pass
2. Real repo verification: orphans include PRDs without implementations
3. MCP `get_orphaned_nodes()` returns orphans grouped by kind
4. MCP `get_graph_status()` root_count reflects only nodes with meaningful children

## Archive

- [ ] Mark phase complete in MASTER_PLAN.md
- [ ] Archive completed plan: `mv MASTER_PLAN.md ~/archive/YYYY-MM-DD/MASTER_PLANx.md`
- [ ] Promote next plan: `mv MASTER_PLAN[lowest].md MASTER_PLAN.md`
- **CLEAR**: Reset checkboxes for next phase
