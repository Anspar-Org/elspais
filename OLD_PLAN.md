# OLD_PLAN.md - Completed Enhancement Phases

This file contains completed phases moved from MASTER_PLAN.md for historical reference.

---

## User Journeys GUI Improvements (Completed 2026-01-28)

- [x] User journeys need a better trace --view GUI
  - [x] Group journeys by topic / name / file / actor
    - Added "Group by" dropdown in journey toolbar (None, Descriptor, Actor, File)
    - Implemented collapsible group sections with expand/collapse state
    - Groups are sorted alphabetically with "(none)" at the end
  - [x] Improve journey card layout and searchability
    - Extended JourneyItem with `descriptor` (extracted from JNY-{descriptor}-{number}) and `file` fields
    - Added Topic and Source metadata to journey cards
    - Search now includes descriptor and file fields
    - Journey state persists to cookie (groupBy, search, collapsed groups)
    - Added compact card variant for grouped view with truncated descriptions

**Files Modified:**
- `src/elspais/html/generator.py`: Extended JourneyItem dataclass, updated _collect_journeys()
- `src/elspais/html/templates/trace_view.html.j2`: Added CSS for groups, grouping controls, JavaScript for dynamic regrouping

---

## Phase 1: Detection (Build-Time Capture) (Completed 2026-01-28)

- [x] Orphaned Nodes Detection
  - Added `_orphan_candidates: set[str]` to GraphBuilder
  - Tracks nodes added, discards when linked during build()
  - TraceGraph API: `orphaned_nodes()`, `has_orphans()`, `orphan_count()`

- [x] Broken References Detection
  - Created `BrokenReference` dataclass in `mutations.py`
  - Captures failed link resolutions during build()
  - TraceGraph API: `broken_references()`, `has_broken_references()`

- [x] Tests: 12 new tests in `tests/core/test_detection.py`

**Files Created:**
- `src/elspais/graph/mutations.py`: BrokenReference dataclass

**Files Modified:**
- `src/elspais/graph/builder.py`: Added detection tracking to GraphBuilder and TraceGraph
- `src/elspais/graph/__init__.py`: Export BrokenReference

---

## Phase 2: Mutation Infrastructure (Completed 2026-01-28)

- [x] MutationEntry dataclass
  - Records operation, target_id, before_state, after_state
  - Auto-generated UUID and timestamp
  - affects_hash flag for hash-sensitive operations

- [x] MutationLog class
  - Append-only history with iteration
  - find_by_id(), entries_since(), pop(), clear()
  - last() for most recent entry

- [x] TraceGraph mutation infrastructure
  - _mutation_log: MutationLog for tracking all mutations
  - _deleted_nodes: list for soft-delete tracking
  - deleted_nodes(), has_deletions() API

- [x] Undo implementation
  - undo_last(): Undo most recent mutation
  - undo_to(mutation_id): Batch undo to specific point
  - _apply_undo() dispatcher for all mutation types

- [x] Tests: 18 new tests in `tests/core/test_mutations.py`

**Files Modified:**
- `src/elspais/graph/mutations.py`: Added MutationEntry, MutationLog
- `src/elspais/graph/builder.py`: Added mutation infrastructure and undo methods to TraceGraph
- `src/elspais/graph/__init__.py`: Export MutationEntry, MutationLog

---

## Phase 3: Node Mutations (Completed 2026-01-28)

- [x] `rename_node(old_id, new_id)` - Renames node and assertion children, updates index
- [x] `update_title(node_id, new_title)` - Updates requirement title
- [x] `change_status(node_id, new_status)` - Changes requirement status
- [x] `add_requirement(req_id, title, level, status, parent_id, edge_kind)` - Creates new requirement
- [x] `delete_requirement(node_id, compact_assertions)` - Deletes requirement, preserves for undo

- [x] Tests: 36 new tests in `tests/core/test_node_mutations.py`

**Files Modified:**
- `src/elspais/graph/GraphNode.py`: Added `set_id()`, `remove_child()` methods
- `src/elspais/graph/builder.py`: Added 5 node mutation methods to TraceGraph
- `CLAUDE.md`: Added Node Mutation API documentation (item 20)

---

## Phase 4: Assertion Mutations (Completed 2026-01-28)

- [x] `rename_assertion(old_id, new_label)` - Renames assertion, updates edges with assertion_targets
- [x] `update_assertion(assertion_id, new_text)` - Updates text, recomputes parent hash
- [x] `add_assertion(req_id, label, text)` - Creates new assertion linked to parent
- [x] `delete_assertion(assertion_id, compact)` - Deletes with optional label compaction

- [x] Tests: 41 new tests in `tests/core/test_assertion_mutations.py`

**Files Modified:**
- `src/elspais/graph/builder.py`: Added 4 assertion mutation methods + `_recompute_requirement_hash()`
- `CLAUDE.md`: Added Assertion Mutation API documentation (item 21)

---

## Phase 5: Edge Mutations (Completed 2026-01-28)

- [x] `add_edge(source_id, target_id, edge_kind, assertion_targets)` - Creates edge or broken ref
- [x] `change_edge_kind(source_id, target_id, new_kind)` - Changes IMPLEMENTS ↔ REFINES
- [x] `delete_edge(source_id, target_id)` - Removes edge, updates orphan tracking
- [x] `fix_broken_reference(source_id, old_target, new_target)` - Repairs broken refs

- [x] Tests: 38 new tests in `tests/core/test_edge_mutations.py`

**Files Modified:**
- `src/elspais/graph/builder.py`: Added 4 edge mutation methods with full undo support
- `CLAUDE.md`: Added Edge Mutation API documentation (item 22)
