# Graph Diff Viewer — Design Spec

**Date**: 2026-03-21
**Status**: Draft

## Problem

The elspais viewer has no way to compare requirements between two commits. The existing "Changed" and "Uncommitted" filters only show git-level file changes — they don't reveal what actually changed at the requirement, assertion, or relationship level. Users reviewing a branch need to see exactly which requirements were added, removed, or modified, and what specific fields changed.

## Solution

Augment the viewer's diff mode to compare two FederatedGraphs built from different commits on the same repo. The "current" graph is annotated with diff metadata computed against a "base" graph, following the existing annotation pattern (`annotate_graph_git_state()`). The viewer renders diff information inline: current values in their normal position, base values as red text shadows beneath.

## Scope

**In scope:**
- Diff engine comparing two TraceGraphs by node ID
- Requirement-level diffs: added, removed, modified, moved
- Field-level diffs: title, status, level, hash, links (Implements/Refines/Satisfies)
- Assertion-level diffs: added, removed, modified text, renamed labels
- Ghost nodes for removed requirements in the tree
- Tree row background tinting (yellow/green/red/blue)
- "Diff" filter button in toolbar
- Card rendering with inline diff annotations

**Out of scope:**
- GUI commit picker and orchestration (assume the caller provides two built `TraceGraph` instances)
- Body text diffing (hash change is sufficient signal)
- Coverage metric diffs (recomputed fresh, not a persisted field)
- FILE/REMAINDER node diffs
- New API endpoints (diff data embedded in existing JSON payload)

**Caller contract:** The diff engine receives two `TraceGraph` objects — it does not know or care how they were built. The caller is responsible for building the base graph (e.g. via `temporary_worktree()` + `build_graph()`) and passing both graphs to `compute_diff()`. This keeps the diff module decoupled from git, CLI, and MCP concerns.

## Architecture

### New Module: `src/elspais/graph/diff.py`

Sits alongside `analysis.py` and `annotators.py`. Contains the diff computation (pure read-only comparison) and an annotation function that stamps metrics onto nodes. The annotation function also injects ghost nodes for removed requirements — this is the only structural mutation and is documented below.

### Data Flow

```text
+------------------+     +------------------+
| build_graph()    |     | build_graph()    |
| (current commit) |     | (base commit via |
|                  |     |  temp worktree)  |
+--------+---------+     +--------+---------+
         |                         |
         v                         v
   current: TraceGraph       base: TraceGraph
         |                         |
         +----------+--------------+
                    |
                    v
         compute_diff(current, base)
                    |
                    v
              DiffResult
                    |
                    v
         annotate_diff(current, diff_result)
                    |
                    v
         current graph with diff metrics
                    |
                    v
         HTMLGenerator._build_tree_rows()
                    |
                    v
         JSON payload -> Viewer JS
```

### Public API

#### `compute_diff(current: TraceGraph, base: TraceGraph) -> DiffResult`

Walks both graphs by node ID. For each node:
- In current only → `NodeDiff(status="added")`
- In base only → `NodeDiff(status="removed")` with snapshot of base fields
- In both → compare fields, edges, assertions → `NodeDiff(status="modified")` if any differ, else skip

**Field comparison:**
- Scalar fields (title, status, level): equality check
- Hash: equality check (implies body change)
- Edges: compare sets of target IDs per EdgeKind (IMPLEMENTS, REFINES, SATISFIES)
- Assertions: match by label, compare text. Unmatched labels = added/removed. Renamed labels detected by matching text content across unmatched pairs.

**Move detection:** Same ID in both graphs but different parent (via CONTAINS/STRUCTURES edges) → `status="moved"`. Move and modify are not mutually exclusive: a moved node that also has field changes gets `status="modified"` with an additional `diff_moved_from` field recording the base parent ID. The tree row uses yellow (modified) tint — move-only nodes (no field changes) use blue.

#### `annotate_diff(graph: TraceGraph, diff: DiffResult)`

Stamps metrics on each affected node via `node.set_metric()`:

| Metric | Type | Description |
|--------|------|-------------|
| `diff_status` | `str \| None` | `"added"`, `"removed"`, `"modified"`, `"moved"` |
| `diff_fields` | `dict[str, FieldDiff]` | Per-field `{"base": old, "current": new}` |
| `diff_links` | `dict[str, list[str]]` | `{"added": [...], "removed": [...]}` per edge kind |
| `diff_assertions` | `list[AssertionDiff]` | Per-assertion `{id, status, base_text, current_text}` |

**Ghost nodes:** For removed requirements, creates a minimal `GraphNode` with:
- `kind=REQUIREMENT`, base node's ID, title, level, status, assertions
- Metrics (via `set_metric()`): `diff_status="removed"`, `is_ghost=True`
- Registered in graph's `_index` via `graph._index[ghost.id] = ghost` (privileged access, same pattern as GraphBuilder)
- Wired to base parent via `parent.link(ghost, EdgeKind.CONTAINS)` if that parent exists in current graph
- If parent is also removed, ghost is added to `graph._roots` as an orphan root
- Ghost nodes appear in `iter_by_kind(NodeKind.REQUIREMENT)` and `find_by_id()` (via index)
- `render_save()` skips FILE nodes whose CONTAINS children are all ghosts; individual ghost nodes are never rendered (they have no FILE ancestor in the current graph)

### Data Types

```python
@dataclass
class FieldDiff:
    base: Any
    current: Any

@dataclass
class AssertionDiff:
    assertion_id: str
    label: str
    status: str  # "added", "removed", "modified"
    base_text: str | None
    current_text: str | None

@dataclass
class LinkDiff:
    edge_kind: str  # "IMPLEMENTS", "REFINES", "SATISFIES"
    added: list[str]
    removed: list[str]

@dataclass
class NodeDiff:
    node_id: str
    status: str  # "added", "removed", "modified", "moved"
    fields: dict[str, FieldDiff]
    links: list[LinkDiff]
    assertions: list[AssertionDiff]
    base_parent_id: str | None  # for ghost node placement

@dataclass
class DiffResult:
    node_diffs: dict[str, NodeDiff]
    # Summary counts derived via properties, not stored
```

## Viewer Changes

### TreeRow Extension (`src/elspais/html/generator.py`)

Add 4 fields to `TreeRow` dataclass:

```python
diff_status: str | None = None
diff_fields: dict | None = None
diff_links: dict | None = None
diff_assertions: list | None = None
```

Populated from node metrics during `_build_tree_rows()`, same pattern as `is_changed`/`is_uncommitted`.

### Navigation Tree (`_nav-tree.js.j2`)

Row rendering checks `row.diff_status` and applies CSS class:

| `diff_status` | CSS class | Background | Left border |
|---------------|-----------|------------|-------------|
| `"modified"` | `diff-modified` | `rgba(234, 179, 8, 0.12)` | `#eab308` (yellow) |
| `"added"` | `diff-added` | `rgba(34, 197, 94, 0.12)` | `#22c55e` (green) |
| `"removed"` | `diff-removed` | `rgba(239, 68, 68, 0.12)` | `#ef4444` (red) |
| `"moved"` | `diff-moved` | `rgba(59, 130, 246, 0.12)` | `#3b82f6` (blue) |

### Toolbar (`_toolbar.html.j2`)

New "Diff" filter button alongside existing Uncommitted/Changed buttons. When active, hides rows where `diff_status` is null. Shows count badge: "Diff (7)".

### Card Rendering (`_card-stack.js.j2`)

**Changed scalar fields** (title, status, hash, level):
- Current value: normal position, normal styling (unchanged)
- Base value: red text (`#f87171`) below the current value, smaller font size

**Changed links** (Implements/Refines/Satisfies):
- Unchanged links: normal rendering
- Added links: green text (`#4ade80`) with `+` prefix
- Removed links: red text (`#f87171`) with `-` prefix

**Changed assertions:**
- Modified: current text in normal position; base text in red below
- Added: green label with `+` marker, normal text
- Removed: red label with `-` marker, red text

**Design rules:**
- No background colors on diff text
- No strikethrough
- No dimming/grey — base values are red
- Current values completely untouched
- Unchanged fields show no diff annotation

## Files Modified

| File | Change |
|------|--------|
| `src/elspais/graph/diff.py` | **New** — diff engine and annotation |
| `src/elspais/html/generator.py` | TreeRow fields, `_build_tree_rows()` population |
| `src/elspais/html/templates/_nav-tree.js.j2` | Diff CSS classes, row rendering |
| `src/elspais/html/templates/_nav-tree.css.j2` | Diff background/border styles |
| `src/elspais/html/templates/_toolbar.html.j2` | Diff filter button |
| `src/elspais/html/templates/_card-stack.js.j2` | Inline diff rendering |
| `src/elspais/html/templates/_card-stack.css.j2` | Red text, green/red link styles |
| `src/elspais/graph/render.py` | Skip ghost nodes in `render_save()` |
| `tests/core/test_diff.py` | **New** — unit tests for diff engine |
| `tests/core/test_html/test_diff_rendering.py` | **New** — viewer diff rendering tests |

## Testing Strategy

**Unit tests** (`test_diff.py`):
- Two identical graphs → empty DiffResult
- Added node → detected as added
- Removed node → detected as removed, ghost created
- Modified field (title, status, hash) → field diff captured
- Added/removed edge → link diff captured
- Added/removed/modified assertion → assertion diff captured
- Move detection → same ID, different parent
- Ghost node wiring → placed under correct parent
- Ghost node with removed parent → becomes orphan

**Viewer tests** (`test_diff_rendering.py`):
- TreeRow population from diff metrics
- Diff filter hides unchanged rows
- Card renders base values in red below current

**Manual verification:**
1. Build graph from current branch
2. Build graph from base commit via `temporary_worktree()`
3. Run `compute_diff()` + `annotate_diff()`
4. Generate HTML and verify visual output matches mockups
