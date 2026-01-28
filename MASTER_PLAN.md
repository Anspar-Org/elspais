# MASTER_PLAN.md - elspais Enhancement Queue

This file contains a prioritized queue of enhancement issues. See CLAUDE.md for workflow.

---

## Bugs

- [x] trace --view: Assoc (Associated) toggle is broken
  - Fixed: Changed from "SHOW ONLY" to "HIDE" semantic (consistent with PRD/OPS/DEV)
  - Now clicking Assoc badge hides associated requirements

- [x] trace --view: Core toggle doesn't work
  - Fixed: Added Core filter with HIDE semantic
  - Clicking Core badge now hides core (non-associated) requirements
  - Added CSS active state styling for consistency

- [x] trace --view: State persistence with cookies
  - Fixed: Now saves/restores tree collapse/expand state via collapsedNodes array in cookie
  - Fixed initialization order to check for saved state before applying defaults
  - All GUI state now persists: filters, toggles, dropdowns, tabs, and tree state

- [x] GraphNode.label encapsulation incomplete
  - Fixed: Refactored all `.label` usages to `get_label()` and `.label =` to `set_label()`
  - Updated: mcp/server.py (11), mcp/serializers.py (5), mcp/context.py (1), html/generator.py (4), validation/format.py (2)
  - Updated test files: test_builder.py, test_mutations.py, test_graph_node.py
  - All 494 tests pass

---

## Quick Wins

- [x] elspais should check if it is in a git repo and always run as if in the root
  - Already implemented: `find_git_root()` in `config/__init__.py` (see CLAUDE.md 7b)

- [x] CLI implementation audit: Check all CLI arguments are fully implemented
  - Found and removed 19 dead arguments across 3 commands:
    - validate: 5 dead args (--fix, --core-repo, --tests, --no-tests, --mode)
    - trace: 5 dead args (--port, --mode, --sponsor, --graph, --depth)
    - reformat-with-claude: 8 dead args (entire command not implemented - simplified to stub)
  - Kept properly-stubbed features (trace --edit-mode, --review-mode, --server)

- [x] CLI argument consistency: Standardize argument format
  - CLI was already consistent with standard conventions (--flags for options, no -- for subcommands)
  - Fixed: `--report` now uses `choices=["minimal", "standard", "full"]` for tab completion
  - The `{minimal,standard,full}` is now shown in help and enables shell autocomplete

- [x] trace --view: Simplify assertion display to show only REQ A → REQ B relationships
  - Fixed: Aggregate assertion targets per child before building tree rows
  - Now shows single entry with combined badges [A][B][C] instead of duplicates

---

---

## TraceGraph Detection and Mutation API

### Summary
Augment `TraceGraph` with:
1. **Detection** - Orphaned nodes and broken references (captured at build time)
2. **Mutation API** - Full CRUD operations with undo support and mutation logging

### Key Files
- `src/elspais/graph/builder.py` - TraceGraph and GraphBuilder classes (mutations added here)
- `src/elspais/graph/GraphNode.py` - GraphNode class (for understanding structure)
- `src/elspais/graph/mutations.py` - NEW: MutationEntry, MutationLog, BrokenReference dataclasses

### Design Decision
**Mutations live on TraceGraph directly** - `graph.rename_node()`, `graph.add_edge()`, etc.
This provides the simplest API while keeping all graph state in one place.

---

---

---

## [x] Quick Fix: Encapsulate `label` attribute

**COMPLETE** - All files now use accessor methods.

- [x] `GraphNode._label` renamed, `get_label()`/`set_label()` methods added
- [x] Refactored ~25 usages across 8 files to use accessor methods

---

## [ ] Phase 3: Node Mutations

### 3.1 Rename Node
Change a requirement's ID while maintaining all edges.

```python
def rename_node(self, old_id: str, new_id: str) -> MutationEntry:
    """Rename a node (e.g., REQ-p00001 → REQ-p00002).

    - Updates node.id
    - Updates all edges pointing to/from this node
    - Updates assertion IDs if requirement (REQ-p00001-A → REQ-p00002-A)
    - Logs mutation with before/after state
    """
```

### 3.2 Update Title
```python
def update_title(self, node_id: str, new_title: str) -> MutationEntry:
    """Update requirement title. Does not affect hash."""
```

### 3.3 Change Status
```python
def change_status(self, node_id: str, new_status: str) -> MutationEntry:
    """Change requirement status (e.g., Draft → Active)."""
```

### 3.4 Add Requirement
```python
def add_requirement(
    self,
    req_id: str,
    title: str,
    level: str,
    status: str = "Draft",
    parent_id: str | None = None,
    edge_kind: EdgeKind = EdgeKind.IMPLEMENTS,
) -> MutationEntry:
    """Add a new requirement node.

    - Creates node with specified properties
    - Optionally links to parent
    - Computes initial hash (empty body = specific hash)
    """
```

### 3.5 Delete Requirement
```python
def delete_requirement(self, node_id: str, compact_assertions: bool = True) -> MutationEntry:
    """Delete a requirement.

    - Removes from _index
    - Moves to _deleted_nodes for delta tracking
    - Removes all edges to/from this node
    - Children become orphans (added to _orphaned_ids)
    - If compact_assertions=True, sibling assertions are renumbered
    """
```

**Verification:**
```bash
pytest tests/test_node_mutations.py
```

---

## [ ] Phase 4: Assertion Mutations

### 4.1 Rename Assertion
```python
def rename_assertion(self, old_id: str, new_label: str) -> MutationEntry:
    """Rename assertion label (e.g., REQ-p00001-A → REQ-p00001-D).

    - Updates assertion node ID
    - Updates edges with assertion_targets
    - Recomputes parent requirement hash
    """
```

### 4.2 Update Assertion Text
```python
def update_assertion(self, assertion_id: str, new_text: str) -> MutationEntry:
    """Update assertion text. Recomputes parent hash."""
```

### 4.3 Add Assertion
```python
def add_assertion(self, req_id: str, label: str, text: str) -> MutationEntry:
    """Add assertion to requirement.

    - Creates assertion node
    - Links as child of requirement
    - Recomputes requirement hash
    """
```

### 4.4 Delete Assertion
```python
def delete_assertion(self, assertion_id: str, compact: bool = True) -> MutationEntry:
    """Delete assertion with optional compaction.

    If compact=True and deleting B from [A, B, C, D]:
    - C → B, D → C
    - Updates all edges referencing C, D
    - Recomputes parent hash
    """
```

**Verification:**
```bash
pytest tests/test_assertion_mutations.py
```

---

## [ ] Phase 5: Edge Mutations

### 5.1 Add Edge
```python
def add_edge(
    self,
    source_id: str,
    target_id: str,
    edge_kind: EdgeKind,
    assertion_targets: list[str] | None = None,
) -> MutationEntry:
    """Add a new edge (reference).

    - Validates both nodes exist
    - If target doesn't exist, adds to _broken_references instead
    - Updates _orphaned_ids (source may no longer be orphan)
    """
```

### 5.2 Change Edge Kind
```python
def change_edge_kind(
    self,
    source_id: str,
    target_id: str,
    new_kind: EdgeKind,
) -> MutationEntry:
    """Change edge type (e.g., IMPLEMENTS → REFINES)."""
```

### 5.3 Delete Edge
```python
def delete_edge(self, source_id: str, target_id: str) -> MutationEntry:
    """Remove an edge.

    - Source may become orphan (add to _orphaned_ids)
    """
```

### 5.4 Fix Broken Reference
```python
def fix_broken_reference(
    self,
    source_id: str,
    old_target_id: str,
    new_target_id: str,
) -> MutationEntry:
    """Fix a broken reference by changing its target.

    - Removes from _broken_references
    - Creates valid edge to new_target_id
    - If new_target_id also doesn't exist, remains broken
    """
```

**Verification:**
```bash
pytest tests/test_edge_mutations.py
```

---

## Invariant Maintenance

Every mutation must:
1. **Log** - Append MutationEntry with before/after state
2. **Orphans** - Update `_orphaned_ids` if parent relationships change
3. **Broken refs** - Update `_broken_references` if edges are added/removed
4. **Hash** - Recompute if assertion text changes
5. **Index** - Keep `_index` consistent with actual nodes

---

## Integration Test

```bash
cd /path/to/hht_diary && python -c "
from elspais.graph.factory import build_graph
graph = build_graph()

# Detection
print(f'Orphans: {graph.orphan_count()}')
print(f'Broken refs: {len(graph.broken_references())}')

# Mutation
entry = graph.rename_node('REQ-p00001', 'REQ-p00099')
print(f'Renamed: {entry.before_state} -> {entry.after_state}')

# Undo
graph.undo_mutation(entry)
assert graph.find_by_id('REQ-p00001') is not None
"
```

---

## [ ] MCP Mutator Capabilities

Add mutation operations to the MCP server to allow AI-driven requirement management:
- Expose TraceGraph mutation methods via MCP tools
- Enable AI to create, rename, move, and delete requirements
- Support undo/redo for AI-initiated changes
- Add safety checks and confirmation prompts for destructive operations
