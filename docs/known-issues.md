# Known Issues

This document tracks known architectural issues and technical debt for future remediation.

---

## KI-001: TraceGraph God Object

**Status**: Deferred
**Identified**: 2026-01-30 (CUR-240 code review)
**Severity**: Medium (maintainability concern, not functional issue)

### Problem

The `TraceGraph` class in `src/elspais/graph/builder.py` exhibits the "God Object" anti-pattern:

| Metric | Value | Threshold |
|--------|-------|-----------|
| Lines of code | ~1,555 | > 500 |
| Public methods | 53+ | > 10 |

The class combines **five distinct responsibilities**:

1. **Graph structure management** - nodes, edges, indexing, traversal
2. **Mutation operations** - rename, update, add, delete for nodes/edges
3. **Undo infrastructure** - mutation log, undo methods, rollback
4. **Body text manipulation** - assertion text updates in requirements
5. **Hash computation** - content hashing after mutations

### Impact

- **Maintenance burden**: Changes require understanding the entire 1500+ line class
- **Testing complexity**: Hard to test mutation logic in isolation
- **Cognitive load**: New contributors must grok the whole class
- **Risk of regression**: Changes to one responsibility may affect others

### Recommended Refactoring

Extract responsibilities into module-private helper classes using **composition with delegation**:

```text
src/elspais/graph/builder.py
├── TraceGraph              # Core structure, queries, public API
├── _GraphMutator           # Node/edge mutation operations
├── _AssertionMutator       # Assertion-specific mutations
├── _MutationLog            # Undo infrastructure
└── _BodyTextEditor         # Body text manipulation
```

### Design Pattern: Module-Private Composition

```python
class TraceGraph:
    """Public API for graph operations."""

    def __init__(self):
        self._nodes = {}
        self._mutator = _GraphMutator(self)
        self._undo_log = _MutationLog()

    # Public API delegates to helpers
    def rename_node(self, old_id, new_id):
        return self._mutator.rename_node(old_id, new_id)


class _GraphMutator:
    """Module-private. Privileged access to TraceGraph internals.

    Note: This class accesses TraceGraph._nodes directly by design.
    They form a single logical unit within this module.
    """

    def __init__(self, graph: TraceGraph):
        self._graph = graph

    def rename_node(self, old_id: str, new_id: str):
        # Access to _graph._nodes is documented privileged access
        ...
```

### Encapsulation Considerations

The extracted classes require access to `TraceGraph` private members (`_nodes`, `_index`, etc.). This is handled via:

1. **Same module**: All classes remain in `builder.py`
2. **Documented privilege**: Docstrings explicitly state the access pattern
3. **Composition**: Helpers receive `TraceGraph` instance at construction
4. **Convention**: Underscore prefix signals module-private (not for external use)

This follows the existing pattern established by `GraphBuilder`, which already has documented privileged access to `GraphNode._content`.

### Implementation Approach

1. **Phase 1**: Extract `_MutationLog` (already somewhat separated)
2. **Phase 2**: Extract `_BodyTextEditor` (helper methods for body text)
3. **Phase 3**: Extract `_GraphMutator` (node/edge mutations)
4. **Phase 4**: Extract `_AssertionMutator` (assertion-specific mutations)

Each phase should:

- Preserve the public API (no breaking changes)
- Maintain all 896 tests passing
- Update docstrings to document privileged access

### Why Deferred

- **Risk**: Large refactoring with many downstream effects
- **Stability**: Current implementation is functional and tested
- **Priority**: Other features take precedence
- **Planning**: Requires careful interface design before execution

### References

- Code review: `~/archive/2026-01-30/MASTER_PLAN_codebase_review.md`
- Design principles: `AGENT_DESIGN_PRINCIPLES.md`
- Current implementation: `src/elspais/graph/builder.py:21-1556`

---

## Adding New Issues

Use this template:

```markdown
## KI-XXX: [Short Title]

**Status**: [Open | In Progress | Deferred | Resolved]
**Identified**: YYYY-MM-DD (ticket reference)
**Severity**: [High | Medium | Low]

### Problem
[Description of the issue]

### Impact
[Why this matters]

### Recommended Fix
[How to address it]

### References
[Links to relevant files, specs, or discussions]
```
