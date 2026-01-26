# Master Plan: Graph Architecture Cleanup

This file tracks remaining cleanup work for the unified graph architecture. After each `/clear`, Claude should read this file and continue with the next incomplete issue.

**Branch:** feature/CUR-514-viewtrace-port

## Workflow

1. **Pick next issue**: Find the first `[ ]` (incomplete) phase below
2. **Refine into plan**: Analyze the codebase and create detailed implementation steps
3. **Implement**: Execute the plan, writing code and tests
4. **Verify**: Run tests, ensure the feature works
5. **Mark complete**: Change `[ ]` to `[x]` for the phase
6. **Commit**: Create a git commit for the changes
7. **Clear context**: Run `/clear` to free up context
8. **Resume**: After clear, read this file and continue with next phase

---

## [x] Phase 1: Eliminate reformat/hierarchy.py ✅

**Problem**: `reformat/hierarchy.py` duplicates graph traversal logic that now exists in TraceGraph.

**Solution implemented**:
1. Updated `transformer.py` to use `TraceNode` instead of `RequirementNode`
2. Updated `reformat_cmd.py` to build TraceGraph directly via `TraceGraphBuilder`
3. Added `_traverse_requirements()` helper using BFS on `node.children`
4. Removed `RequirementNode`, `get_all_requirements`, `traverse_top_down` exports from `__init__.py`
5. DELETED `src/elspais/reformat/hierarchy.py`

**Files modified**:
- `src/elspais/reformat/transformer.py` - Uses `TraceNode` type hints
- `src/elspais/reformat/__init__.py` - Removed hierarchy exports
- `src/elspais/commands/reformat_cmd.py` - Uses TraceGraph directly
- `tests/test_trace_view/test_integration.py` - Updated import test

**Verification**: ✅ All 1136 tests pass

---

## [ ] Phase 2: Consolidate trace.py Output Paths

**Problem**: `run_trace_view()` is a separate code path that should use the unified graph architecture.

**Current state**:
- `run_trace_view()` (line 263) - Separate code path for `--view` flag
- Graph-based path handles `--graph` flag

**Migration approach**:
1. Have `run_trace_view()` build graph via TraceGraphBuilder
2. Pass TraceGraph to HTMLGenerator (already done)
3. Remove any remaining Dict-based intermediate structures
4. Ensure git state annotation uses graph's `node.metrics`

**Files to modify**:
- `src/elspais/commands/trace.py`

**Verification**:
- `pytest` - All tests pass
- `elspais trace --view` - Generates same HTML output
- `elspais trace --view --embed-content` - Works with git state
- Verify no Dict-based intermediate structures remain in trace.py
