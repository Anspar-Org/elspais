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

## [x] Phase 2: Consolidate trace.py Output Paths ✅

**Problem**: `run_trace_view()` is a separate code path that should use the unified graph architecture.

**Current state** (VERIFIED - Already Complete):
- `TraceViewGenerator._build_graph()` uses `TraceGraphBuilder` directly
- `HTMLGenerator` takes `TraceGraph` in constructor - no Dict intermediates
- `annotate_git_state()` and `annotate_display_info()` annotate `node.metrics`
- No Dict-based structures remain after graph building

**What was already in place**:
1. ✅ `TraceViewGenerator._build_graph()` builds graph via TraceGraphBuilder
2. ✅ `HTMLGenerator(graph=self._graph, ...)` - TraceGraph passed directly
3. ✅ No Dict-based intermediate structures after graph building
4. ✅ Git state annotation uses `node.metrics` via `annotate_git_state()`

**Files verified**:
- `src/elspais/trace_view/generators/base.py` - Uses TraceGraphBuilder
- `src/elspais/trace_view/html/generator.py` - Consumes TraceGraph directly
- `src/elspais/core/annotators.py` - Pure functions annotating node.metrics

**Verification**: ✅ All 1136 tests pass, `elspais trace --view` generates HTML correctly

---

## Master Plan Complete

All phases have been completed. The unified graph architecture is now fully in place:

1. **Phase 1**: Eliminated `reformat/hierarchy.py` - uses TraceGraph directly
2. **Phase 2**: Verified `run_trace_view()` already uses unified graph architecture

The codebase now uses `TraceGraph` as the single source of truth for all traceability operations.
