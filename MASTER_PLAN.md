# MASTER PLAN: Remediate Critical Code Review Findings

## Overview

Address the 7 CRITICAL issues identified during the systematic codebase review (ticket CUR-240).
Each phase addresses one critical finding with TDD approach.

## Critical Findings to Address

| # | Location | Issue | Phase |
|---|----------|-------|-------|
| 1 | builder.py:1860 | Direct `_parents` access | Phase 1 |
| 2 | builder.py (multiple) | Direct `_content` mutation | Phase 2 |
| 3 | health.py:147 | Imports private `_parse_toml` | Phase 3 |
| 4 | analyze.py:123-170 | Manual stats vs `count_by_level()` | Phase 4 |
| 5 | health.py:828-864 | Manual coverage vs `count_by_coverage()` | Phase 5 |
| 6 | code.py & test.py | Duplicated `_is_empty_comment()` | Phase 6 |
| 7 | builder.py | TraceGraph God Object | Deferred |

**Note**: Phase 7 (God Object refactor) is deferred - it's a significant architectural change requiring separate planning.

---

## Phase 1: Fix `_parents` Encapsulation Violation ✅

**File**: `src/elspais/graph/builder.py:1860`

### Problem

```python
if not node._parents and node.kind == NodeKind.REQUIREMENT
```

Direct access to private `_parents` attribute violates encapsulation.

### Solution

Replace with public API property `is_root`:

```python
if node.is_root and node.kind == NodeKind.REQUIREMENT
```

### Tasks

- [x] Find all occurrences of `node._parents` access (only 1 external violation found)
- [x] Replace with `node.is_root` property
- [x] Run tests to verify behavior unchanged (896 passed)

---

## Phase 2: Document GraphBuilder Privileged Access ✅

**File**: `src/elspais/graph/builder.py` (lines 687-691, 1102, 1622, 1639, 1687, 1749)

### Problem

Direct mutation of `node._content` throughout GraphBuilder methods.

### Solution Applied

1. Documented "friend class" pattern in GraphBuilder docstring
2. Added `get_all_content()` method to GraphNode for serialization
3. Updated serialize.py to use public API instead of direct `_content` access

### Tasks

- [x] Add docstring to GraphBuilder explaining privileged access pattern
- [x] Add `get_all_content()` method to GraphNode for controlled access
- [x] Update serialize.py to use public API (was also accessing `_content`)
- [x] All tests pass (896 passed)

---

## Phase 3: Fix Private `_parse_toml` Import ✅

**File**: `src/elspais/commands/health.py:147`

### Problem

```python
from elspais.config import _parse_toml  # Private function
```

Importing a private function from the config module.

### Solution

Used existing public API `parse_toml` (already exported in `__all__`):

```python
from elspais.config import parse_toml
```

### Tasks

- [x] Check if `parse_toml` (public) exists - YES, already exported
- [x] Update health.py to use public function
- [x] All tests pass (896 passed)

---

## Phase 4: Use `count_by_level()` in analyze.py ✅

**File**: `src/elspais/commands/analyze.py:123-170`

### Problem

Manual iteration to group requirements by level instead of using shared utility.

### Solution

Added new `group_by_level()` function to annotators.py (returns node lists, not just counts), then refactored analyze.py to use it:

```python
from elspais.graph.annotators import group_by_level

by_level = group_by_level(graph)
```

### Tasks

- [x] Added `group_by_level()` utility to annotators.py
- [x] Exported in `__all__`
- [x] Refactored analyze.py to use shared utility
- [x] All tests pass (896 passed)

---

## Phase 5: Use `count_by_coverage()` in health.py ✅

**File**: `src/elspais/commands/health.py:828-864`

### Problem

Manual coverage computation instead of using aggregate function.

### Solution

Created new `count_with_code_refs()` utility in annotators.py (existing `count_by_coverage()` tracks assertion-level coverage, not code reference coverage). Refactored health.py to use it:

```python
from elspais.graph.annotators import count_with_code_refs

coverage = count_with_code_refs(graph)
```

### Tasks

- [x] Added `count_with_code_refs()` utility to annotators.py
- [x] Exported in `__all__`
- [x] Refactored health.py to use shared utility
- [x] All tests pass (896 passed)

---

## Phase 6: Extract Duplicated `_is_empty_comment()` ✅

**Files**:

- `src/elspais/graph/parsers/code.py:214`
- `src/elspais/graph/parsers/test.py:306`

### Problem

Identical 18-line function duplicated in both parsers.

### Solution

Created `parsers/config_helpers.py` with shared `is_empty_comment()` function. Updated both parsers to use it.

### Tasks

- [x] Created `parsers/config_helpers.py` with shared function
- [x] Updated code.py to import and use shared function
- [x] Updated test.py to import and use shared function
- [x] Removed duplicate method definitions from both files
- [x] All tests pass (896 passed), linting passes

---

## Phase 7: TraceGraph God Object (DEFERRED)

**File**: `src/elspais/graph/builder.py:21-1556`

### Problem

TraceGraph has 1,555 lines and 53+ public methods, combining:

- Graph structure management
- Mutation operations
- Undo infrastructure
- Body text manipulation
- Hash computation

### Recommendation

This requires architectural planning as a separate effort:

1. Extract `GraphMutator` for mutation operations
2. Extract `RequirementBodyEditor` for body text manipulation
3. Keep core query/traversal methods in `TraceGraph`

**Status**: Deferred to future ticket

---

## Verification Checklist

After each phase:

- [ ] All tests pass (`pytest`)
- [ ] No lint errors (`ruff check`)
- [ ] Commit with `[CUR-240]` prefix

## Commit Template

```text
[CUR-240] refactor: [Phase description]

Addresses critical finding from codebase review:
- [What was fixed]
- [Why it matters]

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
```
