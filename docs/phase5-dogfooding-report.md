# Phase 5: MCP Dogfooding Report

## Overview

This document captures findings from using the MCP server to analyze and improve test traceability in the elspais codebase.

---

## 5.1 Test Traceability Analysis

### Current State

| Category | Count | Percentage |
|----------|-------|------------|
| Total tests | ~720 | 100% |
| Tests with REQ-assertion names | 38 | 5.3% |
| Tests with traditional names | ~680 | 94.7% |

**Files using REQ-pattern:** Only `tests/mcp/` (3 files)

### Test-Requirement Mappings Discovered

#### tests/core/test_annotators.py → REQ-d00050, REQ-d00051

| Test Name | Maps To | Assertion Text |
|-----------|---------|----------------|
| `test_annotates_uncommitted` | REQ-d00050-A | `annotate_git_state()` SHALL add git metrics |
| `test_annotates_untracked` | REQ-d00050-A | (same - additional coverage) |
| `test_annotates_branch_changed` | REQ-d00050-A | (same - additional coverage) |
| `test_annotates_moved` | REQ-d00050-A | (same - additional coverage) |
| `test_defaults_to_false` | REQ-d00050-A | (same - edge case) |
| `test_annotates_roadmap` | REQ-d00050-B | `annotate_display_info()` SHALL add display metrics |
| `test_annotates_not_roadmap` | REQ-d00050-B | (same) |
| `test_annotates_conflict` | REQ-d00050-B | (same) |
| `test_annotates_display_filename` | REQ-d00050-B | (same) |
| `test_annotates_repo_prefix` | REQ-d00050-B | (same) |
| `test_defaults_to_core_prefix` | REQ-d00050-B | (same) |
| `test_adds_implementation_files` | REQ-d00050-C | `annotate_implementation_files()` SHALL add refs |
| `test_appends_to_existing` | REQ-d00050-C | (same) |
| `test_skips_non_requirement_nodes` | REQ-d00050-D | Annotators SHALL only operate on REQUIREMENT nodes |
| `test_handles_assertion_id_format` | REQ-d00050-D | (same - edge case) |
| `test_counts_by_level` | REQ-d00051-A | `count_by_level()` returns counts by level |
| `test_counts_by_repo` | REQ-d00051-B | `count_by_repo()` returns counts by repo |
| `test_counts_total_files` | REQ-d00051-C | `count_implementation_files()` returns total |
| `test_collects_topics_from_filenames` | REQ-d00051-D | `collect_topics()` returns sorted topics |
| `test_full_coverage` | REQ-d00051-E | `get_implementation_status()` returns status |
| `test_partial_coverage` | REQ-d00051-E | (same) |
| `test_unimplemented` | REQ-d00051-E | (same) |
| `test_defaults_to_unimplemented` | REQ-d00051-E | (same) |
| `test_boundary_99_is_partial` | REQ-d00051-E | (same - boundary) |
| `test_boundary_1_is_partial` | REQ-d00051-E | (same - boundary) |

### Coverage Gaps Identified

| Assertion | Description | Test Coverage |
|-----------|-------------|---------------|
| REQ-d00050-E | Annotators SHALL be idempotent | ❌ Missing |
| REQ-d00051-F | Aggregates SHALL NOT duplicate iteration | ❌ Missing |

### Suggested Test Renames (Examples)

To improve traceability, tests could be renamed:

```python
# Before
def test_annotates_uncommitted(self):
    """Marks node as uncommitted when file is modified."""

# After
def test_REQ_d00050_A_annotates_uncommitted_when_modified(self):
    """REQ-d00050-A: annotate_git_state() adds git metrics."""
```

---

## 5.2 MCP Tool Ergonomic Issues

### Issues Discovered During Dogfooding

#### 1. No tool to find TEST nodes linked to requirements

**Problem:** There's no MCP tool to query "which tests validate this requirement?"

**Current workaround:** Must manually search test files with `grep` patterns.

**Suggested tool:**

```python
def get_test_coverage(req_id: str) -> dict:
    """Return TEST nodes that reference this requirement."""
    return {
        "requirement": req_id,
        "test_nodes": [...],  # TEST nodes with this req in targets
        "result_nodes": [...],  # TEST_RESULT nodes for those tests
        "coverage_gaps": [...]  # Assertions with no test coverage
    }
```

#### 2. No tool to find assertions without test coverage

**Problem:** Can't easily identify which assertions lack test validation.

**Current workaround:** Must manually compare assertion lists to TEST node targets.

**Suggested tool:**

```python
def get_uncovered_assertions(req_id: str = None) -> list:
    """Return assertions that have no TEST node references."""
```

#### 3. Search results don't include assertion details

**Problem:** `search()` returns requirement summaries but not their assertions.

**Improvement:** Add optional `include_assertions=True` parameter.

#### 4. No bulk update capability for test traceability

**Problem:** To improve test names, must manually edit each test file.

**Suggested feature:** Tool to suggest test renames based on requirement mapping.

### API Ergonomic Notes

| Tool | Issue | Severity |
|------|-------|----------|
| `search()` | Results truncated at 50 by default; had to increase limit | Low |
| `get_requirement()` | Works well; returns assertions properly | ✅ Good |
| `get_hierarchy()` | Useful for understanding relationships | ✅ Good |
| `get_graph_status()` | Helpful for quick overview | ✅ Good |

---

## 5.3 Traceability Improvement Verification

### Before/After Comparison

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Total nodes in graph | 346 | 398 | +52 |
| TEST nodes | 36 | 75 | +39 |
| TEST_RESULT nodes | 17 | 30 | +13 |
| Tests with REQ names | 38 | 43 | +5 |

### Tests Added with REQ-Assertion Names

| Test Name | Assertion |
|-----------|-----------|
| `test_REQ_d00050_E_git_state_is_idempotent` | REQ-d00050-E |
| `test_REQ_d00050_E_display_info_is_idempotent` | REQ-d00050-E |
| `test_REQ_d00051_F_count_by_level_uses_all_nodes` | REQ-d00051-F |
| `test_REQ_d00051_F_count_by_repo_uses_all_nodes` | REQ-d00051-F |
| `test_REQ_d00051_F_collect_topics_uses_all_nodes` | REQ-d00051-F |

### Verification Results

✅ **REQ-d00050** now has test children linked via assertion E (idempotency)
✅ **REQ-d00051** now has test children linked via assertion F (no duplicate iteration)
✅ Graph refresh correctly detects TEST nodes from pytest name patterns
✅ JUnit XML results create TEST_RESULT nodes that link to tests

### Verification Steps Completed

1. ✅ Added 5 new tests following REQ-assertion naming pattern
2. ✅ Ran pytest to generate JUnit XML test results
3. ✅ Refreshed graph with `mcp__elspais__refresh_graph(full=True)`
4. ✅ Verified requirements show new test children via `mcp__elspais__get_requirement()`
5. ✅ Node counts confirm increased TEST and TEST_RESULT nodes

---

## Recommendations

### High Priority

1. **Add `get_test_coverage()` tool** - Essential for understanding test-requirement relationships
2. **Add `get_uncovered_assertions()` tool** - Critical for identifying coverage gaps

### Medium Priority

1. **Enhance `search()` with assertion inclusion** - Reduces tool calls needed
2. **Add bulk test rename suggestions** - Automate traceability improvement

### Low Priority

1. **Add coverage visualization to trace view** - Already partially implemented
2. **Document test naming conventions** - Help new contributors follow patterns

---

## Next Steps

1. ✅ Document test-requirement mappings
2. ✅ Identify MCP tool gaps
3. ✅ Add missing tests for REQ-d00050-E and REQ-d00051-F
4. ✅ Rename sample tests to demonstrate pattern (added 5 new tests with REQ naming)
5. ✅ Verify trace view reflects improved coverage

## Lessons Learned

1. **REQ-naming pattern works**: Tests named `test_REQ_{id}_{assertion}_description` are automatically linked
2. **JUnit XML integration**: Pytest's `--junit-xml` output creates TEST_RESULT nodes
3. **MCP tools effective for analysis**: `get_requirement()`, `search()`, and `get_graph_status()` enabled discovery
4. **Coverage gap discovery**: Using the graph revealed assertions without test coverage
5. **Documentation value**: Creating this report helped crystallize findings and recommendations
