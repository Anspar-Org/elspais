# MASTER_PLAN.md - elspais Enhancement Queue

This file contains a prioritized queue of enhancement issues. See CLAUDE.md for workflow.

---

## Bugs

- [ ] trace --view: Version shows "v1" instead of actual elspais version (e.g., 0.26.0)
  - Template should pull version from package metadata
  - Check `pyproject.toml` version and pass to Jinja2 template

- [ ] trace --view: Files filter toggle doesn't show files in tree hierarchy
  - Files are not graph nodes, so filter doesn't work as expected
  - Consider: Replace "Files" with "Tests" filter and show tests in tree instead

- [ ] trace --view: Assoc (Associated) toggle is broken
  - Should have same look/operation as PRD/OPS/DEV toggles
  - Currently makes ALL REQs disappear (even though 16 associated REQs exist in hht_diary)

- [ ] trace --view: Core toggle doesn't work
  - Should filter to show only core requirements

- [ ] trace --view: State persistence with cookies
  - Should save/restore: toggle states (on/off), tree collapse/expand state
  - Basically capture entire GUI state for session continuity

---

## Quick Wins

- [x] elspais should check if it is in a git repo and always run as if in the root
  - Already implemented: `find_git_root()` in `config/__init__.py` (see CLAUDE.md 7b)

- [ ] trace --view: Simplify assertion display to show only REQ A → REQ B relationships
  - Currently shows duplicate entries if REQ A implements multiple assertions in REQ B
  - Should collapse to single relationship with assertion badges

---

## User Journeys GUI Improvements

- [ ] User journeys need a better trace --view GUI
  - [ ] Group journeys by topic / name / file / actor
  - [ ] Improve journey card layout and searchability

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

## [ ] Phase 1: Detection (Build-Time Capture)

### 1.1 Orphaned Nodes
Track nodes that never receive a parent during graph construction.

**GraphBuilder tracking:**
```python
# In __init__:
self._orphan_candidates: set[str] = set()

# When adding any node to self._nodes:
self._orphan_candidates.add(node_id)

# When linking (child gets a parent) in build():
self._orphan_candidates.discard(child_id)
```

**TraceGraph API:**
```python
_orphaned_ids: set[str] = field(default_factory=set, init=False)

def orphaned_nodes(self) -> Iterator[GraphNode]: ...
def has_orphans(self) -> bool: ...
def orphan_count(self) -> int: ...
```

### 1.2 Broken References
Track failed link resolutions during `build()`.

**New dataclass (in mutations.py):**
```python
@dataclass
class BrokenReference:
    source_id: str        # Node containing the reference
    target_id: str        # ID that doesn't exist
    edge_kind: str        # "implements", "refines", or "validates"
```

**TraceGraph API:**
```python
_broken_references: list[BrokenReference] = field(default_factory=list, init=False)

def broken_references(self) -> list[BrokenReference]: ...
def has_broken_references(self) -> bool: ...
```

**Verification:**
```bash
pytest tests/ && python -c "
from elspais.graph.factory import build_graph
graph = build_graph()
print(f'Orphans: {graph.orphan_count()}')
print(f'Broken refs: {len(graph.broken_references())}')
"
```

---

## [ ] Phase 2: Mutation Infrastructure

### 2.1 Mutation Log
All mutations append to a persistent log for auditing and undo.

```python
@dataclass
class MutationEntry:
    """Single mutation operation record."""
    id: str                    # Unique mutation ID (uuid4)
    timestamp: datetime        # When mutation occurred
    operation: str             # Operation type (e.g., "rename_node", "add_edge")
    target_id: str             # Primary target of mutation
    before_state: dict[str, Any]   # State before mutation (for undo)
    after_state: dict[str, Any]    # State after mutation
    affects_hash: bool         # Whether this mutation affects content hash

class MutationLog:
    """Append-only mutation history."""
    _entries: list[MutationEntry]

    def append(self, entry: MutationEntry) -> None: ...
    def iter_entries(self) -> Iterator[MutationEntry]: ...
    def undo_last(self) -> MutationEntry | None: ...
    def undo_to(self, mutation_id: str) -> list[MutationEntry]: ...
```

### 2.2 Deleted Nodes Tracking
Deleted nodes become orphans in a special "deleted" list for delta reporting.

```python
_deleted_nodes: list[GraphNode] = field(default_factory=list, init=False)

def deleted_nodes(self) -> list[GraphNode]: ...
def has_deletions(self) -> bool: ...
```

### 2.3 Hash Recomputation Rules
| Operation | Affects Hash |
|-----------|-------------|
| Rename node ID | No |
| Update title | No |
| Update assertion text | **Yes** |
| Add/delete assertion | **Yes** |
| Change status | No |
| Add/change/delete edge | No |

### 2.4 Undo Implementation
```python
def undo_mutation(self, entry: MutationEntry) -> None:
    """Reverse a mutation using its before_state."""
    # Dispatch based on entry.operation
    # Restore node/edge state from entry.before_state
    # Recalculate orphans/broken refs
    # DO NOT log undo as new mutation (or mark as "undo" type)
```

**Verification:**
```bash
pytest tests/test_mutations.py
```

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
