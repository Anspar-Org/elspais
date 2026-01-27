# MASTER_PLAN.md

This file contains a prioritized queue of enhancement issues for iterative implementation.

---

## Issue 1: Test Quality Improvements

**Goal**: Implement recommendations from test quality assessment to improve coverage, eliminate trivial tests, strengthen assertions, and ensure full black-box compliance.

### Summary of Issues by Priority

| Priority | Issue | Count |
|----------|-------|-------|
| High | Black-box violations (`_content`, `_metrics`, `_index` access) | 7+ |
| High | Missing node type coverage (`TEST_RESULT`, `TODO`) | 2 |
| High | Missing edge type coverage (`ADDRESSES`, `CONTAINS`) | 2 |
| Medium | Missing test scenarios | 40+ |
| Medium | Weak assertions (substring, `>=` instead of exact) | 15+ |
| Low | Trivial tests (verify assignment worked) | 14+ |
| Low | Missing helper functions | 5+ |

### Files to Modify

| File | Changes |
|------|---------|
| `tests/core/graph_test_helpers.py` | Add factories, `build_graph()`, validation |
| `tests/core/conftest.py` | Add missing fixtures |
| `tests/core/test_graph_node.py` | Consolidate enum tests, add coverage |
| `tests/core/test_relations.py` | Remove trivial tests, add edge cases |
| `tests/core/test_builder.py` | Add content types, strengthen assertions |
| `tests/core/test_serialize.py` | Fix black-box violation, add scenarios |
| `tests/core/test_annotators.py` | Fix 6+ black-box violations, add edge cases |

---

### [x] Phase 1: Enhance Test Helpers (COMPLETED)

**File**: `tests/core/graph_test_helpers.py`

1. ✅ Added missing factories:
   - `make_test_result(result_id, status, test_id, duration)` - creates TEST_RESULT nodes
   - `make_remainder(remainder_id, text, source_path, start_line)` - creates TODO/remainder nodes

2. ✅ Added convenience builder:
   ```python
   def build_graph(*contents: ParsedContent, repo_root: Path | None = None) -> TraceGraph
   ```

3. ✅ Added validation to `make_requirement`:
   ```python
   VALID_LEVELS = {"PRD", "OPS", "DEV"}
   if level not in VALID_LEVELS:
       raise ValueError(f"Invalid level '{level}'")
   ```

4. ✅ Added missing string helpers:
   - `descendants_string(node)` - sorted IDs excluding self
   - `edges_by_kind_string(node, kind)` - filtered edges
   - `metrics_string(node, *keys)` - key=value pairs

**Also modified**:
- `src/elspais/graph/builder.py` - Added `_add_test_result()` and `_add_remainder()` handlers
- `tests/core/test_html/test_generator.py` - Fixed black-box violation in `sample_graph` fixture

---

### [ ] Phase 2: Enhance Fixtures

**File**: `tests/core/conftest.py`

Add fixtures:
- `builder()` - Fresh GraphBuilder instance
- `graph_with_assertions()` - Requirement with A, B, C assertions
- `comprehensive_graph()` - Requirements + code refs + test refs
- `git_modified_files()` - GitChangeInfo with modified files
- `git_untracked_files()` - GitChangeInfo with untracked files

---

### [ ] Phase 3: Fix test_graph_node.py

**File**: `tests/core/test_graph_node.py`

1. **Consolidate enum tests**: Replace 7 `TestNodeKind` tests with single `test_all_node_kinds_exist`

2. **Add missing coverage**:
   - `test_uuid_is_unique_per_node`
   - `test_set_and_get_field`
   - `test_set_and_get_metric`
   - `test_walk_invalid_order_raises`
   - `test_ancestors_empty_for_root`
   - `test_find_returns_empty_when_no_match`

---

### [ ] Phase 4: Fix test_relations.py

**File**: `tests/core/test_relations.py`

1. **Consolidate enum tests**: Replace 5 `TestEdgeKind` tests with single `test_all_edge_kinds_exist`

2. **Add edge case tests**:
   - `test_edge_inequality_different_assertion_targets`
   - `test_edge_equality_with_non_edge`

3. **Strengthen assertions**: Use exact equality instead of substring contains

---

### [ ] Phase 5: Fix test_builder.py

**File**: `tests/core/test_builder.py`

1. **Add missing content type tests**:
   - `test_build_creates_journey_nodes`
   - `test_build_creates_code_ref_nodes`
   - `test_build_creates_test_ref_nodes`
   - `test_build_creates_refines_edges`
   - `test_build_ignores_missing_targets`
   - `test_node_content_fields_accessible`

2. **Strengthen assertions**: Change `>= 4` to `== 4` in `test_all_nodes_iterator`

---

### [ ] Phase 6: Fix test_serialize.py

**File**: `tests/core/test_serialize.py`

1. **Fix black-box violation**: Change `node._metrics = {...}` to `node.set_metric()`

2. **Fix weak assertion**: Remove OR condition in `test_csv_handles_commas`

3. **Add missing coverage**:
   - `test_serialize_node_with_parents`
   - `test_serialize_node_with_edges`
   - `test_serialize_empty_graph`
   - `test_csv_handles_quotes`

---

### [ ] Phase 7: Fix test_annotators.py

**File**: `tests/core/test_annotators.py`

1. **Fix all black-box violations** (6+ instances):
   - Replace `node._content = {...}` with `node.set_field()`
   - Replace `node._metrics = {...}` with `node.set_metric()`
   - Replace `graph._index = {...}` with `build_graph()`

2. **Add missing edge cases**:
   - `test_annotate_git_state_handles_assertion_ids`
   - `test_get_implementation_status_boundary_99`
   - `test_get_implementation_status_boundary_1`

3. **Strengthen assertions**: Verify actual content, not just length

---

## Verification

After completing all phases:

```bash
# Run all core tests
pytest tests/core/ -v

# Verify no black-box violations
grep -r "node\._content\s*=" tests/core/ --include="*.py"
grep -r "node\._metrics\s*=" tests/core/ --include="*.py"
grep -r "graph\._index\s*=" tests/core/ --include="*.py"
grep -r "graph\._roots\s*=" tests/core/ --include="*.py"

# Should return no matches
```

---

## Execution Order

1. Phase 1 - Enhance helpers (enables cleaner tests)
2. Phase 2 - Enhance fixtures (reduces boilerplate)
3. Phase 7 - Fix annotators (most black-box violations)
4. Phase 6 - Fix serialize (1 black-box violation)
5. Phase 3 - Fix graph_node (consolidate enums, add coverage)
6. Phase 4 - Fix relations (consolidate enums, add edge cases)
7. Phase 5 - Fix builder (add content type coverage)
