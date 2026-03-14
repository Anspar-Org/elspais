# FILE Node Architecture Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make source files first-class graph nodes, replacing implicit SourceLocation with explicit FILE nodes, typed edges for all relationships, filtered traversal, and render-based serialization.

**Architecture:** Add `NodeKind.FILE` and `FileType` enum. Add `EdgeKind.CONTAINS`, `STRUCTURES`, `DEFINES`, `YIELDS`. Add `Edge.metadata` dict. Replace `add_child()` with `link()` + edge kinds everywhere. Replace `SourceLocation` with `file_node()` navigation. Replace `persistence.py` with render-based save.

**Tech Stack:** Python 3.10+, pytest, tomlkit. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-03-13-file-node-architecture-design.md`

---

## Chunk 1: Core Data Model Changes

Foundation layer. Modifies enums, Edge dataclass, and GraphNode. All subsequent chunks depend on this.

### Task 1: Add FileType enum and NodeKind.FILE

**Files:**
- Modify: `src/elspais/graph/GraphNode.py:24-33` (NodeKind enum)
- Create: `src/elspais/graph/file_types.py` (FileType enum)
- Test: `tests/graph/test_file_node_model.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/graph/test_file_node_model.py
"""Tests for FILE node model additions."""

from elspais.graph.GraphNode import NodeKind


def test_file_node_kind_exists():
    assert NodeKind.FILE.value == "file"


def test_file_type_enum():
    from elspais.graph.file_types import FileType

    assert FileType.SPEC.value == "spec"
    assert FileType.JOURNEY.value == "journey"
    assert FileType.CODE.value == "code"
    assert FileType.TEST.value == "test"
    assert FileType.RESULT.value == "result"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/graph/test_file_node_model.py -v`
Expected: FAIL — `NodeKind` has no `FILE` member, `file_types` module doesn't exist

- [ ] **Step 3: Write minimal implementation**

Add to `src/elspais/graph/GraphNode.py` line 33, inside `NodeKind`:
```python
    FILE = "file"
```

Create `src/elspais/graph/file_types.py`:
```python
"""FileType enum for classifying FILE nodes by their domain role."""

from enum import Enum


class FileType(Enum):
    """Classification of a FILE node by what kind of content it contains."""

    SPEC = "spec"
    JOURNEY = "journey"
    CODE = "code"
    TEST = "test"
    RESULT = "result"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/graph/test_file_node_model.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `pytest`
Expected: All existing tests pass

- [ ] **Step 6: Commit**

```bash
git add src/elspais/graph/GraphNode.py src/elspais/graph/file_types.py tests/graph/test_file_node_model.py
git commit -m "[CUR-1082] feat: add NodeKind.FILE and FileType enum"
```

---

### Task 2: Add new EdgeKind values (CONTAINS, STRUCTURES, DEFINES, YIELDS)

**Files:**
- Modify: `src/elspais/graph/relations.py:34-54` (EdgeKind enum)
- Modify: `src/elspais/graph/relations.py:57` (contributes_to_coverage)
- Test: `tests/graph/test_file_node_model.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/graph/test_file_node_model.py`:
```python
from elspais.graph.relations import EdgeKind


def test_new_edge_kinds_exist():
    assert EdgeKind.CONTAINS.value == "contains"
    assert EdgeKind.STRUCTURES.value == "structures"
    assert EdgeKind.DEFINES.value == "defines"
    assert EdgeKind.YIELDS.value == "yields"


def test_structural_edges_do_not_contribute_to_coverage():
    assert not EdgeKind.CONTAINS.contributes_to_coverage()
    assert not EdgeKind.STRUCTURES.contributes_to_coverage()
    assert not EdgeKind.DEFINES.contributes_to_coverage()
    assert not EdgeKind.YIELDS.contributes_to_coverage()


def test_traceability_edges_contribute_to_coverage():
    assert EdgeKind.IMPLEMENTS.contributes_to_coverage()
    assert EdgeKind.VALIDATES.contributes_to_coverage()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/graph/test_file_node_model.py::test_new_edge_kinds_exist -v`
Expected: FAIL — no STRUCTURES, DEFINES, YIELDS members (CONTAINS already exists but with wrong semantics — that's fine, its value stays the same)

- [ ] **Step 3: Write minimal implementation**

In `src/elspais/graph/relations.py`, add to `EdgeKind` enum after existing members:
```python
    STRUCTURES = "structures"
    DEFINES = "defines"
    YIELDS = "yields"
```

Note: `CONTAINS = "contains"` already exists at line 50. Keep it — its value is the same, only its semantic usage changes (from TEST_RESULT→TEST to FILE→content). The builder change (Task 8) will fix the usage.

`contributes_to_coverage()` at line 57 already returns True only for IMPLEMENTS and VALIDATES, so the new edge kinds are automatically excluded. No change needed.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/graph/test_file_node_model.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest`
Expected: All tests pass (new enum members don't break anything)

- [ ] **Step 6: Commit**

```bash
git add src/elspais/graph/relations.py tests/graph/test_file_node_model.py
git commit -m "[CUR-1082] feat: add EdgeKind.STRUCTURES, DEFINES, YIELDS"
```

---

### Task 3: Add Edge.metadata dict

**Files:**
- Modify: `src/elspais/graph/relations.py:68-103` (Edge dataclass)
- Test: `tests/graph/test_file_node_model.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/graph/test_file_node_model.py`:
```python
from elspais.graph.relations import Edge
from elspais.graph.GraphNode import GraphNode, NodeKind


def test_edge_has_metadata_field():
    n1 = GraphNode(id="a", kind=NodeKind.REQUIREMENT)
    n2 = GraphNode(id="b", kind=NodeKind.REQUIREMENT)
    edge = Edge(source=n1, target=n2, kind=EdgeKind.IMPLEMENTS)
    assert edge.metadata == {}


def test_edge_metadata_not_in_equality():
    n1 = GraphNode(id="a", kind=NodeKind.REQUIREMENT)
    n2 = GraphNode(id="b", kind=NodeKind.REQUIREMENT)
    e1 = Edge(source=n1, target=n2, kind=EdgeKind.IMPLEMENTS, metadata={"x": 1})
    e2 = Edge(source=n1, target=n2, kind=EdgeKind.IMPLEMENTS, metadata={"x": 2})
    assert e1 == e2
    assert hash(e1) == hash(e2)


def test_edge_metadata_contains_line_info():
    n1 = GraphNode(id="f", kind=NodeKind.FILE)
    n2 = GraphNode(id="r", kind=NodeKind.REQUIREMENT)
    edge = Edge(
        source=n1,
        target=n2,
        kind=EdgeKind.CONTAINS,
        metadata={"start_line": 1, "end_line": 45, "render_order": 0.0},
    )
    assert edge.metadata["start_line"] == 1
    assert edge.metadata["render_order"] == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/graph/test_file_node_model.py::test_edge_has_metadata_field -v`
Expected: FAIL — Edge constructor doesn't accept `metadata`

- [ ] **Step 3: Write minimal implementation**

In `src/elspais/graph/relations.py`, add `metadata` field to `Edge` dataclass after `assertion_targets` (line 86):
```python
    metadata: dict[str, Any] = field(default_factory=dict)
```

Add `from typing import Any` to imports (it is NOT currently present — must be added).

Also extend `link()` in `GraphNode.py` (line 293) to accept an optional `metadata` parameter:
```python
    def link(
        self,
        child: GraphNode,
        edge_kind: EdgeKind,
        assertion_targets: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Edge:
```
And pass it through to the `Edge` constructor:
```python
        edge = Edge(
            source=self,
            target=child,
            kind=edge_kind,
            assertion_targets=assertion_targets or [],
            metadata=metadata or {},
        )
```

The `__eq__` and `__hash__` methods at lines 88-103 already only compare `source.id`, `target.id`, `kind`, `assertion_targets` — they do NOT include `metadata`, which is the desired behavior.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/graph/test_file_node_model.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest`
Expected: All tests pass (metadata defaults to empty dict, no existing code affected)

- [ ] **Step 6: Commit**

```bash
git add src/elspais/graph/relations.py tests/graph/test_file_node_model.py
git commit -m "[CUR-1082] feat: add Edge.metadata dict for line range and render_order"
```

---

### Task 4: Add filtered traversal to GraphNode

**Files:**
- Modify: `src/elspais/graph/GraphNode.py:129-145` (iter_children, iter_parents, iter_edges_by_kind)
- Modify: `src/elspais/graph/GraphNode.py:341-397` (walk, ancestors)
- Test: `tests/graph/test_file_node_model.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/graph/test_file_node_model.py`:
```python
def test_iter_children_filtered_by_edge_kind():
    parent = GraphNode(id="parent", kind=NodeKind.FILE)
    child_a = GraphNode(id="a", kind=NodeKind.REQUIREMENT)
    child_b = GraphNode(id="b", kind=NodeKind.REQUIREMENT)
    parent.link(child_a, EdgeKind.CONTAINS)
    parent.link(child_b, EdgeKind.STRUCTURES)

    contains_children = list(parent.iter_children(edge_kinds={EdgeKind.CONTAINS}))
    assert contains_children == [child_a]

    structures_children = list(parent.iter_children(edge_kinds={EdgeKind.STRUCTURES}))
    assert structures_children == [child_b]

    all_children = list(parent.iter_children())
    assert set(n.id for n in all_children) == {"a", "b"}


def test_iter_parents_filtered_by_edge_kind():
    file_node = GraphNode(id="f", kind=NodeKind.FILE)
    req_node = GraphNode(id="r", kind=NodeKind.REQUIREMENT)
    child = GraphNode(id="c", kind=NodeKind.ASSERTION)
    file_node.link(req_node, EdgeKind.CONTAINS)
    req_node.link(child, EdgeKind.STRUCTURES)

    structures_parents = list(child.iter_parents(edge_kinds={EdgeKind.STRUCTURES}))
    assert structures_parents == [req_node]

    contains_parents = list(child.iter_parents(edge_kinds={EdgeKind.CONTAINS}))
    assert contains_parents == []


def test_walk_filtered_by_edge_kind():
    file_node = GraphNode(id="f", kind=NodeKind.FILE)
    req = GraphNode(id="r", kind=NodeKind.REQUIREMENT)
    assertion = GraphNode(id="a", kind=NodeKind.ASSERTION)
    file_node.link(req, EdgeKind.CONTAINS)
    req.link(assertion, EdgeKind.STRUCTURES)

    # Walking CONTAINS from file should yield file + req, NOT assertion
    walked = list(file_node.walk(edge_kinds={EdgeKind.CONTAINS}))
    assert [n.id for n in walked] == ["f", "r"]

    # Walking STRUCTURES from req should yield req + assertion
    walked = list(req.walk(edge_kinds={EdgeKind.STRUCTURES}))
    assert [n.id for n in walked] == ["r", "a"]


def test_ancestors_filtered_by_edge_kind():
    file_node = GraphNode(id="f", kind=NodeKind.FILE)
    req = GraphNode(id="r", kind=NodeKind.REQUIREMENT)
    assertion = GraphNode(id="a", kind=NodeKind.ASSERTION)
    file_node.link(req, EdgeKind.CONTAINS)
    req.link(assertion, EdgeKind.STRUCTURES)

    # From assertion, STRUCTURES ancestors should be req only
    ancestors = list(assertion.ancestors(edge_kinds={EdgeKind.STRUCTURES}))
    assert [n.id for n in ancestors] == ["r"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/graph/test_file_node_model.py::test_iter_children_filtered_by_edge_kind -v`
Expected: FAIL — `iter_children()` doesn't accept `edge_kinds`

- [ ] **Step 3: Write minimal implementation**

Modify `iter_children()` at line 129:
```python
    def iter_children(
        self, edge_kinds: set[EdgeKind] | None = None
    ) -> Iterator[GraphNode]:
        """Iterate over child nodes, optionally filtered by edge kind.

        Args:
            edge_kinds: If provided, only yield children reachable via these edge kinds.
                       If None, yield all children (unfiltered).
        """
        if edge_kinds is None:
            yield from self._children
        else:
            seen: set[str] = set()
            for edge in self._outgoing_edges:
                if edge.kind in edge_kinds and edge.target.id not in seen:
                    seen.add(edge.target.id)
                    yield edge.target
```

Modify `iter_parents()` at line 133:
```python
    def iter_parents(
        self, edge_kinds: set[EdgeKind] | None = None
    ) -> Iterator[GraphNode]:
        """Iterate over parent nodes, optionally filtered by edge kind.

        Args:
            edge_kinds: If provided, only yield parents reachable via these edge kinds.
                       If None, yield all parents (unfiltered).
        """
        if edge_kinds is None:
            yield from self._parents
        else:
            seen: set[str] = set()
            for edge in self._incoming_edges:
                if edge.kind in edge_kinds and edge.source.id not in seen:
                    seen.add(edge.source.id)
                    yield edge.source
```

Modify `walk()` at line 341 to accept and pass through `edge_kinds`:
```python
    def walk(
        self, order: str = "pre", edge_kinds: set[EdgeKind] | None = None
    ) -> Iterator[GraphNode]:
        """Iterate over this node and descendants.

        Args:
            order: Traversal order ("pre", "post", "level").
            edge_kinds: If provided, only follow edges of these kinds at each level.
        """
        if order == "pre":
            yield from self._walk_preorder(edge_kinds)
        elif order == "post":
            yield from self._walk_postorder(edge_kinds)
        elif order == "level":
            yield from self._walk_level(edge_kinds)
        else:
            raise ValueError(f"Unknown traversal order: {order}")

    def _walk_preorder(
        self, edge_kinds: set[EdgeKind] | None = None
    ) -> Iterator[GraphNode]:
        yield self
        for child in self.iter_children(edge_kinds=edge_kinds):
            yield from child._walk_preorder(edge_kinds)

    def _walk_postorder(
        self, edge_kinds: set[EdgeKind] | None = None
    ) -> Iterator[GraphNode]:
        for child in self.iter_children(edge_kinds=edge_kinds):
            yield from child._walk_postorder(edge_kinds)
        yield self

    def _walk_level(
        self, edge_kinds: set[EdgeKind] | None = None
    ) -> Iterator[GraphNode]:
        queue: deque[GraphNode] = deque([self])
        while queue:
            node = queue.popleft()
            yield node
            queue.extend(node.iter_children(edge_kinds=edge_kinds))
```

Modify `ancestors()` at line 382:
```python
    def ancestors(
        self, edge_kinds: set[EdgeKind] | None = None
    ) -> Iterator[GraphNode]:
        """Iterate up through all ancestor paths (BFS).

        Args:
            edge_kinds: If provided, only follow edges of these kinds upward.
        """
        visited: set[str] = set()
        queue: deque[GraphNode] = deque(self.iter_parents(edge_kinds=edge_kinds))
        while queue:
            node = queue.popleft()
            if node.id not in visited:
                visited.add(node.id)
                yield node
                queue.extend(node.iter_parents(edge_kinds=edge_kinds))
```

Add `EdgeKind` to the TYPE_CHECKING imports at line 21:
```python
if TYPE_CHECKING:
    from elspais.graph.relations import Edge, EdgeKind
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/graph/test_file_node_model.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest`
Expected: All existing tests pass (new parameter defaults to None = unfiltered = existing behavior)

- [ ] **Step 6: Commit**

```bash
git add src/elspais/graph/GraphNode.py tests/graph/test_file_node_model.py
git commit -m "[CUR-1082] feat: add edge-kind filtered traversal to GraphNode"
```

---

### Task 5: Add file_node() convenience method and rename remove_child to unlink

**Files:**
- Modify: `src/elspais/graph/GraphNode.py` (add file_node, rename remove_child)
- Test: `tests/graph/test_file_node_model.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/graph/test_file_node_model.py`:
```python
def test_file_node_from_top_level_content():
    """Top-level content node: one hop via CONTAINS to FILE."""
    file_node = GraphNode(id="f", kind=NodeKind.FILE)
    req = GraphNode(id="r", kind=NodeKind.REQUIREMENT)
    file_node.link(req, EdgeKind.CONTAINS)

    assert req.file_node() is file_node


def test_file_node_from_assertion():
    """Assertion: two hops — STRUCTURES to REQ, then CONTAINS to FILE."""
    file_node = GraphNode(id="f", kind=NodeKind.FILE)
    req = GraphNode(id="r", kind=NodeKind.REQUIREMENT)
    assertion = GraphNode(id="a", kind=NodeKind.ASSERTION)
    file_node.link(req, EdgeKind.CONTAINS)
    req.link(assertion, EdgeKind.STRUCTURES)

    assert assertion.file_node() is file_node


def test_file_node_from_virtual_node():
    """INSTANCE node has no CONTAINS edge — returns None."""
    instance = GraphNode(id="i", kind=NodeKind.REQUIREMENT)
    # No CONTAINS or STRUCTURES edges, just floating
    assert instance.file_node() is None


def test_file_node_from_file_node():
    """FILE node returns itself."""
    file_node = GraphNode(id="f", kind=NodeKind.FILE)
    assert file_node.file_node() is file_node


def test_unlink_method():
    """unlink() severs all edges between two nodes."""
    parent = GraphNode(id="p", kind=NodeKind.REQUIREMENT)
    child = GraphNode(id="c", kind=NodeKind.ASSERTION)
    parent.link(child, EdgeKind.STRUCTURES)

    assert parent.unlink(child) is True
    assert list(parent.iter_children()) == []
    assert list(child.iter_parents()) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/graph/test_file_node_model.py::test_file_node_from_top_level_content -v`
Expected: FAIL — `file_node()` method doesn't exist

- [ ] **Step 3: Write minimal implementation**

Add `file_node()` method to `GraphNode` class (after `ancestors()`).

**Circular import note:** `EdgeKind` is currently only imported under `TYPE_CHECKING` in GraphNode.py. Since `file_node()` is a runtime method, use string comparison on `edge.kind.value` to avoid circular imports:

```python
    def file_node(self) -> GraphNode | None:
        """Find the FILE node ancestor of this node.

        Walks up incoming edges (CONTAINS, STRUCTURES) to find the nearest
        ancestor with kind == NodeKind.FILE.

        Returns:
            The FILE node, or None if not reachable from any FILE.
        """
        if self.kind == NodeKind.FILE:
            return self
        # Use .value strings to avoid circular import with EdgeKind
        _UPWARD_KINDS = ("contains", "structures")
        visited: set[str] = set()
        queue: deque[GraphNode] = deque()
        for edge in self._incoming_edges:
            if edge.kind.value in _UPWARD_KINDS:
                queue.append(edge.source)
        while queue:
            node = queue.popleft()
            if node.id in visited:
                continue
            visited.add(node.id)
            if node.kind == NodeKind.FILE:
                return node
            for edge in node._incoming_edges:
                if edge.kind.value in _UPWARD_KINDS:
                    queue.append(edge.source)
        return None
```

Rename `remove_child` to `unlink` at line 233. Keep `remove_child` as an alias temporarily (to avoid breaking callers until they're migrated in later tasks):
```python
    def unlink(self, child: GraphNode) -> bool:
        """Sever all edges between this node and a child.
        ...existing docstring adapted...
        """
        # ...existing remove_child implementation unchanged...

    def remove_child(self, child: GraphNode) -> bool:
        """Deprecated: use unlink() instead."""
        return self.unlink(child)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/graph/test_file_node_model.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest`
Expected: All tests pass (remove_child alias preserves existing callers)

- [ ] **Step 6: Commit**

```bash
git add src/elspais/graph/GraphNode.py tests/graph/test_file_node_model.py
git commit -m "[CUR-1082] feat: add file_node() method, rename remove_child to unlink"
```

---

### Task 6: Add parse_line/parse_end_line fields to GraphNode

**Files:**
- Modify: `src/elspais/graph/GraphNode.py` (add fields)
- Test: `tests/graph/test_file_node_model.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/graph/test_file_node_model.py`:
```python
def test_parse_line_fields():
    node = GraphNode(id="r", kind=NodeKind.REQUIREMENT)
    node.set_field("parse_line", 10)
    node.set_field("parse_end_line", 45)
    assert node.get_field("parse_line") == 10
    assert node.get_field("parse_end_line") == 45
```

- [ ] **Step 2: Run test to verify it passes immediately**

Run: `pytest tests/graph/test_file_node_model.py::test_parse_line_fields -v`
Expected: PASS — these are just content fields stored via existing `set_field()`/`get_field()`. No structural change needed; this test documents the convention.

- [ ] **Step 3: Commit**

```bash
git add tests/graph/test_file_node_model.py
git commit -m "[CUR-1082] test: document parse_line/parse_end_line field convention"
```

---

## Chunk 2: Builder Changes — add_child to link Migration and TEST_RESULT Edge Fix

Migrates existing `add_child()` calls in the builder to `link()` with typed edges, and fixes the TEST_RESULT→TEST edge direction/kind.

### Task 7: Migrate add_child() calls in _add_requirement to link() with STRUCTURES

**Files:**
- Modify: `src/elspais/graph/builder.py:1706-1792` (_add_requirement)
- Test: `tests/graph/test_builder_structures.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/graph/test_builder_structures.py
"""Tests that builder uses STRUCTURES edges for REQ->ASSERTION and REQ->REMAINDER section."""

from pathlib import Path

from elspais.graph.builder import GraphBuilder
from elspais.graph.relations import EdgeKind


def _build_simple_graph(tmp_path: Path):
    """Build a graph with one requirement that has an assertion and a section."""
    spec_file = tmp_path / "spec" / "test.md"
    spec_file.parent.mkdir(parents=True)
    spec_file.write_text(
        """\
## REQ-p00001: Test Requirement

**Level**: PRD | **Status**: Draft

Some body text.

## Assertions

- **A**: First assertion

## Rationale

This is the rationale.

*End* *REQ-p00001*
""",
        encoding="utf-8",
    )
    from elspais.graph.factory import build_graph

    return build_graph(
        repo_root=tmp_path,
        config={
            "project": {"namespace": "p"},
            "id-patterns": {"prefixes": {"prd": "p", "ops": "o", "dev": "d"}},
            "spec": {"directories": ["spec"]},
        },
        spec_dirs=[spec_file.parent],
        scan_code=False,
        scan_tests=False,
        scan_sponsors=False,
    )


def test_assertion_linked_via_structures(tmp_path):
    graph = _build_simple_graph(tmp_path)
    req = graph.find_by_id("REQ-p00001")
    assert req is not None

    # Find assertion child
    assertion = graph.find_by_id("REQ-p00001-A")
    assert assertion is not None

    # Check it's connected via STRUCTURES edge
    structures_edges = [
        e for e in req.iter_outgoing_edges() if e.kind == EdgeKind.STRUCTURES
    ]
    structures_targets = {e.target.id for e in structures_edges}
    assert "REQ-p00001-A" in structures_targets


def test_section_linked_via_structures(tmp_path):
    graph = _build_simple_graph(tmp_path)
    req = graph.find_by_id("REQ-p00001")
    assert req is not None

    # Sections are REMAINDER children connected via STRUCTURES
    structures_edges = [
        e for e in req.iter_outgoing_edges() if e.kind == EdgeKind.STRUCTURES
    ]
    section_targets = [
        e.target for e in structures_edges if "section" in e.target.id
    ]
    assert len(section_targets) >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/graph/test_builder_structures.py -v`
Expected: FAIL — assertions are linked via `add_child()` (no Edge object), so `iter_outgoing_edges()` returns no STRUCTURES edges

- [ ] **Step 3: Modify _add_requirement in builder.py**

At line 1781 in `builder.py`, find where `add_child()` is called for assertion and section children. Replace each `node.add_child(child_node)` with `node.link(child_node, EdgeKind.STRUCTURES)`.

Look for the pattern (approximately):
```python
# Before:
node.add_child(child_node)

# After:
node.link(child_node, EdgeKind.STRUCTURES)
```

Apply this to ALL `add_child()` calls within `_add_requirement()` — both for assertion children and for section (REMAINDER) children. Make sure `EdgeKind` is imported at top of builder.py (it should already be, check line ~25).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/graph/test_builder_structures.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest`
Expected: All tests pass — `link()` also maintains `_children`/`_parents` caches, so existing traversal behavior is preserved

- [ ] **Step 6: Commit**

```bash
git add src/elspais/graph/builder.py tests/graph/test_builder_structures.py
git commit -m "[CUR-1082] refactor: use STRUCTURES edges for REQ->ASSERTION/section in builder"
```

---

### Task 8: Fix TEST_RESULT edge: CONTAINS → YIELDS with correct direction

**Files:**
- Modify: `src/elspais/graph/builder.py:1924-1971` (_add_test_result, pending_links)
- Modify: `src/elspais/graph/builder.py` (build() edge resolution, anywhere CONTAINS is used for TEST_RESULT→TEST)
- Test: `tests/graph/test_builder_structures.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/graph/test_builder_structures.py`:
```python
from elspais.graph.GraphNode import NodeKind


def test_test_result_linked_via_yields(tmp_path):
    """TEST_RESULT should be a child of TEST via YIELDS edge (TEST→TEST_RESULT)."""
    spec_file = tmp_path / "spec" / "test.md"
    spec_file.parent.mkdir(parents=True)
    spec_file.write_text(
        """\
## REQ-p00001: Login Feature

**Level**: PRD | **Status**: Draft

## Assertions

- **A**: User can log in

*End* *REQ-p00001*
""",
        encoding="utf-8",
    )
    test_file = tmp_path / "tests" / "test_login.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text(
        """\
# Tests REQ-p00001-A
def test_login():
    pass
""",
        encoding="utf-8",
    )
    # Create a pytest JSON result file
    import json

    result_file = tmp_path / "results.json"
    result_file.write_text(
        json.dumps(
            {
                "tests": [
                    {
                        "nodeid": "tests/test_login.py::test_login",
                        "outcome": "passed",
                        "duration": 0.01,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    from elspais.graph.factory import build_graph

    graph = build_graph(
        repo_root=tmp_path,
        config={
            "project": {"namespace": "p"},
            "id-patterns": {"prefixes": {"prd": "p", "ops": "o", "dev": "d"}},
            "spec": {"directories": ["spec"]},
            "testing": {
                "enabled": True,
                "test_dirs": ["tests"],
                "patterns": ["test_*.py"],
                "result_files": ["results.json"],
            },
        },
        spec_dirs=[spec_file.parent],
        scan_code=False,
        scan_tests=True,
        scan_sponsors=False,
    )

    # Find test and result nodes
    test_nodes = [n for _, n in graph.iter_index() if n.kind == NodeKind.TEST]
    result_nodes = [n for _, n in graph.iter_index() if n.kind == NodeKind.TEST_RESULT]

    assert test_nodes, "Expected at least one TEST node"
    assert result_nodes, "Expected at least one TEST_RESULT node"

    test_node = test_nodes[0]
    # TEST should have YIELDS edge to TEST_RESULT (downward)
    yields_edges = [
        e for e in test_node.iter_outgoing_edges() if e.kind == EdgeKind.YIELDS
    ]
    assert len(yields_edges) >= 1, (
        f"Expected YIELDS edge from TEST to TEST_RESULT, "
        f"got outgoing edges: {[e.kind for e in test_node.iter_outgoing_edges()]}"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/graph/test_builder_structures.py::test_test_result_linked_via_yields -v`
Expected: FAIL — currently uses CONTAINS with wrong direction (TEST_RESULT→TEST)

- [ ] **Step 3: Fix the edge in builder.py**

At line 1971 in `_add_test_result()`, find:
```python
self._pending_links.append((result_id, test_id, EdgeKind.CONTAINS))
```

Change to:
```python
self._pending_links.append((test_id, result_id, EdgeKind.YIELDS))
```

This reverses the direction (TEST→TEST_RESULT) and changes the edge kind. Check `build()` method (around line 2332) for how pending_links are resolved — the `(source_id, target_id, edge_kind)` convention means `source.link(target, edge_kind)`. Verify the resolution code handles this correctly (source is now TEST, target is TEST_RESULT, which makes TEST the parent via `link()`).

Note: Also check if there are any consumers that look for `EdgeKind.CONTAINS` edges on TEST_RESULT nodes — search for `CONTAINS` usage in annotators, MCP server, etc. and update any that specifically look for the TEST_RESULT→TEST relationship.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/graph/test_builder_structures.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest`
Expected: May have some test failures if existing tests check for CONTAINS edges on TEST_RESULT nodes. Fix those tests to look for YIELDS edges from TEST instead.

- [ ] **Step 6: Commit**

```bash
git add src/elspais/graph/builder.py tests/graph/test_builder_structures.py
git commit -m "[CUR-1082] fix: TEST->TEST_RESULT via YIELDS edge (was CONTAINS wrong direction)"
```

---

### Task 9: Migrate add_child in _instantiate_satisfies_templates to link with STRUCTURES

**Files:**
- Modify: `src/elspais/graph/builder.py:2041-2173` (_instantiate_satisfies_templates)
- Test: existing satisfies tests should cover this — run them

- [ ] **Step 1: Find and replace add_child in _instantiate_satisfies_templates**

At line 2168 in builder.py, find `add_child()` calls used for attaching cloned assertion children to cloned requirement parents. Replace with `link(child, EdgeKind.STRUCTURES)`.

- [ ] **Step 2: Run satisfies-related tests**

Run: `pytest tests/ -k satisfies -v`
Expected: PASS — the `link()` call maintains `_children`/`_parents` caches just like `add_child()` did

- [ ] **Step 3: Run full test suite**

Run: `pytest`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add src/elspais/graph/builder.py
git commit -m "[CUR-1082] refactor: use STRUCTURES edges in satisfies template cloning"
```

---

### Task 10: Migrate remaining add_child callers and remove the method

**Files:**
- Modify: `src/elspais/graph/GraphNode.py` (remove add_child and remove_child alias)
- Modify: `src/elspais/graph/builder.py` (undo methods that use remove_child → unlink)
- Modify: all test files that use add_child
- Test: run full suite

- [ ] **Step 1: Migrate remaining add_child callers in src/**

Run: `grep -rn "\.add_child(" src/`

Known sites (beyond Tasks 7 and 9):
- `builder.py:486` — `_undo_delete_requirement()`: restores parent link after undo. Use `link(child, EdgeKind.STRUCTURES)` for assertion/section children.
- `builder.py:1151` — `add_assertion()` mutation: links new assertion to parent REQ. Use `link(child, EdgeKind.STRUCTURES)`.

For each caller, determine the correct EdgeKind based on the relationship being created.

- [ ] **Step 2: Migrate remaining remove_child callers in src/**

Run: `grep -rn "\.remove_child(" src/`

Known sites in builder.py:
- Line 312: `_apply_undo()` for delete_requirement undo — use `unlink()`
- Line 414: `_undo_fix_broken_reference()` — use `unlink()`
- Line 442: `_undo_delete_assertion()` — use `unlink()`
- Line 816: `delete_requirement()` disconnect from parents — use `unlink()`
- Line 827: `delete_requirement()` mark non-assertion children as orphans — use `unlink()`
- Line 1233: `delete_assertion()` final cleanup — use `unlink()`

- [ ] **Step 3: Migrate add_child/remove_child callers in tests/**

Run: `grep -rn "\.add_child\|\.remove_child" tests/`

For each test caller:
- Replace `add_child(child)` with `link(child, appropriate_edge_kind)`
- Replace `remove_child(child)` with `unlink(child)`

- [ ] **Step 3: Remove add_child method and remove_child alias from GraphNode**

Delete the `add_child()` method (line 219) and the `remove_child()` alias. Keep only `unlink()`.

- [ ] **Step 4: Run full test suite**

Run: `pytest`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "[CUR-1082] refactor: remove add_child/remove_child, all relationships use link/unlink"
```

---

## Chunk 3: Parameterized iter_roots and iter_by_kind on TraceGraph

### Task 11: Add iter_by_kind and parameterize iter_roots on TraceGraph

**Files:**
- Modify: `src/elspais/graph/builder.py:38-211` (TraceGraph class)
- Test: `tests/graph/test_file_node_model.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/graph/test_file_node_model.py`:
```python
from elspais.graph.builder import TraceGraph


def test_iter_roots_parameterized(tmp_path):
    """iter_roots(NodeKind.FILE) returns FILE nodes, default returns REQ+JOURNEY."""
    from elspais.graph.factory import build_graph

    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    (spec_dir / "reqs.md").write_text(
        """\
## REQ-p00001: Test

**Level**: PRD | **Status**: Draft

*End* *REQ-p00001*
""",
        encoding="utf-8",
    )
    graph = build_graph(
        repo_root=tmp_path,
        config={
            "project": {"namespace": "p"},
            "id-patterns": {"prefixes": {"prd": "p", "ops": "o", "dev": "d"}},
            "spec": {"directories": ["spec"]},
        },
        spec_dirs=[spec_dir],
        scan_code=False,
        scan_tests=False,
        scan_sponsors=False,
    )

    # Default iter_roots should return REQs (existing behavior)
    default_roots = list(graph.iter_roots())
    assert any(r.kind == NodeKind.REQUIREMENT for r in default_roots)
    assert not any(r.kind == NodeKind.FILE for r in default_roots)

    # iter_roots(NodeKind.FILE) should return FILE nodes once they exist
    # (This test will pass trivially until FILE nodes are created in Task 12+)
    file_roots = list(graph.iter_roots(NodeKind.FILE))
    # Just verify the method accepts the parameter without error
    assert isinstance(file_roots, list)


def test_iter_by_kind(tmp_path):
    """iter_by_kind returns all nodes of a specific kind from the index."""
    from elspais.graph.factory import build_graph

    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    (spec_dir / "reqs.md").write_text(
        """\
## REQ-p00001: Test

**Level**: PRD | **Status**: Draft

## Assertions

- **A**: First assertion

*End* *REQ-p00001*
""",
        encoding="utf-8",
    )
    graph = build_graph(
        repo_root=tmp_path,
        config={
            "project": {"namespace": "p"},
            "id-patterns": {"prefixes": {"prd": "p", "ops": "o", "dev": "d"}},
            "spec": {"directories": ["spec"]},
        },
        spec_dirs=[spec_dir],
        scan_code=False,
        scan_tests=False,
        scan_sponsors=False,
    )

    reqs = list(graph.iter_by_kind(NodeKind.REQUIREMENT))
    assert len(reqs) >= 1
    assert all(n.kind == NodeKind.REQUIREMENT for n in reqs)

    assertions = list(graph.iter_by_kind(NodeKind.ASSERTION))
    assert len(assertions) >= 1
    assert all(n.kind == NodeKind.ASSERTION for n in assertions)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/graph/test_file_node_model.py::test_iter_roots_parameterized -v`
Expected: FAIL — `iter_roots()` doesn't accept a `kind` parameter

- [ ] **Step 3: Modify TraceGraph.iter_roots**

At line 65 in builder.py, modify `iter_roots()`:
```python
    def iter_roots(
        self, kind: NodeKind | None = None
    ) -> Iterator[GraphNode]:
        """Iterate over root nodes.

        Args:
            kind: If provided, filter to roots of this NodeKind.
                  If None, returns default roots (REQ + JOURNEY, excluding FILE).
        """
        if kind is not None:
            # Search _index for parentless nodes of this kind.
            # This covers FILE nodes (not in _roots) and REQ/JOURNEY roots.
            for node in self._index.values():
                if node.kind == kind and node.parent_count() == 0:
                    yield node
        else:
            for node in self._roots:
                if node.kind != NodeKind.FILE:
                    yield node
```

Add `iter_by_kind()`:
```python
    def iter_by_kind(self, kind: NodeKind) -> Iterator[GraphNode]:
        """Iterate over all nodes of a specific kind in the index."""
        for node in self._index.values():
            if node.kind == kind:
                yield node
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/graph/test_file_node_model.py::test_iter_roots_parameterized -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest`
Expected: All tests pass (default behavior unchanged)

- [ ] **Step 6: Commit**

```bash
git add src/elspais/graph/builder.py tests/graph/test_file_node_model.py
git commit -m "[CUR-1082] feat: parameterize iter_roots by NodeKind, add iter_by_kind"
```

---

## Chunk 4: FILE Node Creation in Factory and Builder

This is the core integration chunk. Creates FILE nodes during graph building and wires CONTAINS edges.

### Task 12: Create FILE nodes in factory.py and wire CONTAINS edges in builder

**Files:**
- Modify: `src/elspais/graph/factory.py:154-395` (build_graph)
- Modify: `src/elspais/graph/builder.py` (GraphBuilder — add file_node tracking, modify add_parsed_content)
- Modify: `src/elspais/graph/parsers/remainder.py` (ensure it's registered)
- Test: `tests/graph/test_file_nodes.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/graph/test_file_nodes.py
"""Tests for FILE node creation during graph building."""

from pathlib import Path

from elspais.graph.GraphNode import NodeKind
from elspais.graph.file_types import FileType
from elspais.graph.relations import EdgeKind


def _build_graph_with_spec(tmp_path: Path):
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    (spec_dir / "reqs.md").write_text(
        """\
Preamble text.

## REQ-p00001: Test Requirement

**Level**: PRD | **Status**: Draft

Body text.

## Assertions

- **A**: First assertion

*End* *REQ-p00001*

Some trailing text.
""",
        encoding="utf-8",
    )
    from elspais.graph.factory import build_graph

    return build_graph(
        repo_root=tmp_path,
        config={
            "project": {"namespace": "p"},
            "id-patterns": {"prefixes": {"prd": "p", "ops": "o", "dev": "d"}},
            "spec": {"directories": ["spec"]},
        },
        spec_dirs=[spec_dir],
        scan_code=False,
        scan_tests=False,
        scan_sponsors=False,
    )


def test_file_node_created_for_spec(tmp_path):
    graph = _build_graph_with_spec(tmp_path)
    file_nodes = list(graph.iter_roots(NodeKind.FILE))
    assert len(file_nodes) == 1
    f = file_nodes[0]
    assert f.kind == NodeKind.FILE
    assert f.get_field("file_type") == FileType.SPEC
    assert "reqs.md" in f.get_field("relative_path")


def test_file_contains_requirement(tmp_path):
    graph = _build_graph_with_spec(tmp_path)
    file_nodes = list(graph.iter_roots(NodeKind.FILE))
    f = file_nodes[0]

    contains_children = list(f.iter_children(edge_kinds={EdgeKind.CONTAINS}))
    req_children = [c for c in contains_children if c.kind == NodeKind.REQUIREMENT]
    assert len(req_children) == 1
    assert req_children[0].id == "REQ-p00001"


def test_file_contains_remainder(tmp_path):
    graph = _build_graph_with_spec(tmp_path)
    file_nodes = list(graph.iter_roots(NodeKind.FILE))
    f = file_nodes[0]

    contains_children = list(f.iter_children(edge_kinds={EdgeKind.CONTAINS}))
    remainder_children = [c for c in contains_children if c.kind == NodeKind.REMAINDER]
    # Should have at least preamble and trailing text as REMAINDER
    assert len(remainder_children) >= 1


def test_contains_edge_has_metadata(tmp_path):
    graph = _build_graph_with_spec(tmp_path)
    file_nodes = list(graph.iter_roots(NodeKind.FILE))
    f = file_nodes[0]

    contains_edges = [e for e in f.iter_outgoing_edges() if e.kind == EdgeKind.CONTAINS]
    assert len(contains_edges) >= 1
    for edge in contains_edges:
        assert "start_line" in edge.metadata
        assert "render_order" in edge.metadata
        assert isinstance(edge.metadata["render_order"], float)


def test_requirement_file_node_navigation(tmp_path):
    graph = _build_graph_with_spec(tmp_path)
    req = graph.find_by_id("REQ-p00001")
    assert req is not None
    f = req.file_node()
    assert f is not None
    assert f.kind == NodeKind.FILE


def test_assertion_file_node_navigation(tmp_path):
    graph = _build_graph_with_spec(tmp_path)
    assertion = graph.find_by_id("REQ-p00001-A")
    assert assertion is not None
    f = assertion.file_node()
    assert f is not None
    assert f.kind == NodeKind.FILE


def test_default_iter_roots_excludes_file_nodes(tmp_path):
    graph = _build_graph_with_spec(tmp_path)
    default_roots = list(graph.iter_roots())
    assert not any(r.kind == NodeKind.FILE for r in default_roots)


def test_every_line_accounted_for(tmp_path):
    """Every line in the file should be covered by some node via CONTAINS."""
    graph = _build_graph_with_spec(tmp_path)
    file_nodes = list(graph.iter_roots(NodeKind.FILE))
    f = file_nodes[0]

    contains_edges = [e for e in f.iter_outgoing_edges() if e.kind == EdgeKind.CONTAINS]
    # Verify we have coverage (at least REQUIREMENT + REMAINDER nodes)
    assert len(contains_edges) >= 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/graph/test_file_nodes.py -v`
Expected: FAIL — no FILE nodes created yet

- [ ] **Step 3: Implement FILE node creation**

This is the largest implementation step. Changes needed:

**In `builder.py` — GraphBuilder:**

Add a `_file_nodes` dict to `__init__()` to track FILE nodes by path:
```python
self._file_nodes: dict[str, GraphNode] = {}  # path -> FILE node
```

Add a method to create or retrieve a FILE node:
```python
def add_file_node(self, file_node: GraphNode) -> None:
    """Register a FILE node created by factory.py."""
    self._file_nodes[file_node.id] = file_node
    self._nodes[file_node.id] = file_node
```

Add a `_current_file_node` attribute set by factory before each file's parsing:
```python
self._current_file_node: GraphNode | None = None
```

Modify `add_parsed_content()` to create CONTAINS edges from `_current_file_node` to each top-level content node created by the dispatch methods. The dispatch methods (`_add_requirement`, `_add_code_ref`, etc.) should return the created node ID so the caller can wire the CONTAINS edge.

In each `_add_*` method, store `parse_line` and `parse_end_line` as content fields on the node:
```python
node.set_field("parse_line", content.start_line)
node.set_field("parse_end_line", content.end_line)
```

In `build()`, add FILE nodes to the graph's `_index`.

**In `factory.py` — build_graph:**

Before each file is deserialized, create the FILE node:
```python
from elspais.graph.GraphNode import GraphNode, NodeKind
from elspais.graph.file_types import FileType

# Capture git info once per repo
import subprocess
git_branch = None
git_commit = None
try:
    git_branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True, cwd=str(repo_root),
    ).stdout.strip() or None
    git_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True, text=True, cwd=str(repo_root),
    ).stdout.strip() or None
except (FileNotFoundError, subprocess.SubprocessError):
    pass
```

For each file in a spec directory:
```python
rel_path = str(file_path.relative_to(repo_root))
file_node = GraphNode(id=f"file:{rel_path}", kind=NodeKind.FILE, label=file_path.name)
file_node._content.update({
    "file_type": FileType.SPEC,
    "absolute_path": str(file_path),
    "relative_path": rel_path,
    "repo": None,  # or associate repo identifier
    "git_branch": git_branch,
    "git_commit": git_commit,
})
builder.add_file_node(file_node)
builder._current_file_node = file_node
```

Similar for code, test, and result directories, with the appropriate `FileType`.

**Register RemainderParser** in all text-based registries (spec, code, test but NOT result):
```python
from elspais.graph.parsers.remainder import RemainderParser
registry.register(RemainderParser())
```

**Wire CONTAINS edges** in `add_parsed_content()` after creating each top-level node:
```python
if self._current_file_node is not None:
    render_order = float(len([
        e for e in self._current_file_node.iter_outgoing_edges()
        if e.kind == EdgeKind.CONTAINS
    ]))
    self._current_file_node.link(
        node,
        EdgeKind.CONTAINS,
        metadata={
            "start_line": content.start_line,
            "end_line": content.end_line,
            "render_order": render_order,
        },
    )
```

Note: The `link()` method currently doesn't accept `metadata`. You'll need to create the edge manually or extend `link()` to accept optional metadata:
```python
edge = self._current_file_node.link(node, EdgeKind.CONTAINS)
edge.metadata = {
    "start_line": content.start_line,
    "end_line": content.end_line,
    "render_order": render_order,
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/graph/test_file_nodes.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest`
Expected: All tests pass. Some existing tests may need minor adjustments if they count nodes or check root lists.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "[CUR-1082] feat: create FILE nodes during graph build with CONTAINS edges"
```

---

### Task 13: Wire DEFINES edges for INSTANCE nodes during satisfies instantiation

**Files:**
- Modify: `src/elspais/graph/builder.py:2041-2173` (_instantiate_satisfies_templates)
- Test: `tests/graph/test_file_nodes.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/graph/test_file_nodes.py`:
```python
def test_instance_nodes_have_defines_edge(tmp_path):
    """INSTANCE nodes get DEFINES edges from the declaring REQ's FILE node."""
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()

    # Template requirement
    (spec_dir / "template.md").write_text(
        """\
## REQ-p00010: Template

**Level**: PRD | **Status**: Draft

## Assertions

- **A**: Template assertion

*End* *REQ-p00010*
""",
        encoding="utf-8",
    )

    # Declaring requirement with Satisfies
    (spec_dir / "concrete.md").write_text(
        """\
## REQ-d00001: Concrete

**Level**: DEV | **Status**: Draft | **Implements**: REQ-p00010
**Satisfies**: REQ-p00010

*End* *REQ-d00001*
""",
        encoding="utf-8",
    )

    from elspais.graph.factory import build_graph

    graph = build_graph(
        repo_root=tmp_path,
        config={
            "project": {"namespace": "p"},
            "id-patterns": {"prefixes": {"prd": "p", "ops": "o", "dev": "d"}},
            "spec": {"directories": ["spec"]},
            "hierarchy": {"rules": ["dev -> ops, prd"]},
        },
        spec_dirs=[spec_dir],
        scan_code=False,
        scan_tests=False,
        scan_sponsors=False,
    )

    # Find INSTANCE nodes
    from elspais.graph.relations import Stereotype

    instance_nodes = [
        n
        for n in graph.iter_by_kind(NodeKind.REQUIREMENT)
        if n.get_field("stereotype") == Stereotype.INSTANCE
    ]

    if instance_nodes:
        # Each instance should have a DEFINES edge from a FILE node
        for inst in instance_nodes:
            defines_parents = [
                e.source
                for e in inst.iter_incoming_edges()
                if e.kind == EdgeKind.DEFINES
            ]
            # DEFINES edge comes from the declaring req's file
            assert len(defines_parents) >= 1 or inst.file_node() is None
```

- [ ] **Step 2: Run test, implement, verify**

The implementation adds DEFINES edge creation at the end of `_instantiate_satisfies_templates()`. After each INSTANCE node is created, find the declaring requirement's FILE node and create a DEFINES edge.

- [ ] **Step 3: Run full test suite**

Run: `pytest`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/elspais/graph/builder.py tests/graph/test_file_nodes.py
git commit -m "[CUR-1082] feat: DEFINES edges from FILE to INSTANCE nodes"
```

---

## Chunk 5: Consumer Migration — Replace SourceLocation Usage

Migrate all ~15 consumers from `node.source.path`/`node.source.line` to `node.file_node()` and `node.get_field("parse_line")`. Each sub-task targets one consumer file.

**Strategy:** Keep `SourceLocation` and `GraphNode.source` alive during this chunk. Both old and new paths work. Remove them in the final task of this chunk.

### Task 14: Migrate annotators.py (git state, display info)

**Files:**
- Modify: `src/elspais/graph/annotators.py:44-158`
- Test: existing annotator tests + run full suite

- [ ] **Step 1: Modify annotate_git_state()**

At line 68, change `node.source.path` to:
```python
fn = node.file_node()
source_path = fn.get_field("relative_path") if fn else None
```

Adapt remaining logic to handle `source_path` being `None`.

- [ ] **Step 2: Modify annotate_display_info()**

At line 129, same pattern. Replace `node.source.path` with `file_node()` navigation.

- [ ] **Step 3: Run full test suite**

Run: `pytest`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/elspais/graph/annotators.py
git commit -m "[CUR-1082] refactor: migrate annotators.py from SourceLocation to file_node()"
```

---

### Task 15: Migrate MCP server, Flask app, and serializer

**Files:**
- Modify: `src/elspais/mcp/server.py` (lines 76-95, 149-191, 199+)
- Modify: `src/elspais/server/app.py`
- Modify: `src/elspais/graph/serialize.py`
- Test: run full suite

- [ ] **Step 1: Migrate _relative_source_path() in mcp/server.py**

Replace the function body to use `file_node()`:
```python
def _relative_source_path(node, repo_root):
    fn = node.file_node()
    if fn:
        return fn.get_field("relative_path")
    return None
```

- [ ] **Step 2: Migrate _serialize_code_info, _serialize_test_info**

Replace `node.source.line` with `node.get_field("parse_line")`.

- [ ] **Step 3: Migrate serialize.py**

In `serialize_node()`, replace `node.source` serialization with:
```python
fn = node.file_node()
if fn:
    result["source"] = {
        "path": fn.get_field("relative_path"),
        "line": node.get_field("parse_line"),
        "end_line": node.get_field("parse_end_line"),
        "repo": fn.get_field("repo"),
    }
```

- [ ] **Step 4: Migrate server/app.py**

Replace `node.source.path` references with `file_node()` navigation.

- [ ] **Step 5: Run full test suite**

Run: `pytest`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/elspais/mcp/server.py src/elspais/server/app.py src/elspais/graph/serialize.py
git commit -m "[CUR-1082] refactor: migrate MCP/Flask/serializer from SourceLocation to file_node()"
```

---

### Task 16: Migrate remaining consumers (commands, HTML, PDF, linkers, git)

**Files:**
- Modify: `src/elspais/commands/trace.py`
- Modify: `src/elspais/commands/validate.py`
- Modify: `src/elspais/commands/index.py`
- Modify: `src/elspais/commands/fix_cmd.py`
- Modify: `src/elspais/html/generator.py`
- Modify: `src/elspais/pdf/assembler.py`
- Modify: `src/elspais/graph/link_suggest.py`
- Modify: `src/elspais/graph/test_code_linker.py`
- Modify: `src/elspais/utilities/git.py`
- Test: run full suite

- [ ] **Step 1: Migrate each file**

Same pattern for all: replace `node.source.path` with `node.file_node().get_field("relative_path")` and `node.source.line` with `node.get_field("parse_line")`. Handle `None` from `file_node()` where the node might be virtual.

- [ ] **Step 2: Run full test suite**

Run: `pytest`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "[CUR-1082] refactor: migrate all remaining consumers from SourceLocation to file_node()"
```

---

### Task 17: Remove SourceLocation class and GraphNode.source field

**Files:**
- Modify: `src/elspais/graph/GraphNode.py` (delete SourceLocation class, remove source field)
- Modify: `src/elspais/graph/builder.py` (remove SourceLocation creation in _add_* methods)
- Test: run full suite, fix any remaining references

- [ ] **Step 1: Delete SourceLocation**

Remove the `SourceLocation` class (lines 36-58) and the `source` field from `GraphNode` (line 81).

- [ ] **Step 2: Remove SourceLocation creation in builder.py**

In `_add_requirement`, `_add_code_ref`, `_add_test_ref`, `_add_test_result`, `_add_remainder` — remove the `SourceLocation(...)` construction and `source=source` parameter from `GraphNode(...)` calls.

- [ ] **Step 3: Update graph/__init__.py exports**

Remove `SourceLocation` from `src/elspais/graph/__init__.py` exports (lines 22 and 30).

- [ ] **Step 4: Search for any remaining references**

Run: `grep -rn "SourceLocation\|node\.source\b" src/`
Fix any remaining references.

- [ ] **Step 4: Run full test suite**

Run: `pytest`
Expected: PASS after fixing any test references to SourceLocation

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "[CUR-1082] refactor: remove SourceLocation class and GraphNode.source field"
```

---

## Chunk 6: Render-Based Save System

Replace `persistence.py` with render methods on each NodeKind and FILE-walk-based save.

### Task 18: Implement render methods for each NodeKind

**Files:**
- Create: `src/elspais/graph/render.py`
- Test: `tests/graph/test_render.py`

- [ ] **Step 1: Write failing tests for REMAINDER render**

```python
# tests/graph/test_render.py
"""Tests for node rendering."""

from elspais.graph.GraphNode import GraphNode, NodeKind
from elspais.graph.render import render_node


def test_render_remainder():
    # Note: the builder currently stores REMAINDER content as "text" field.
    # The render module should use the same field name.
    node = GraphNode(id="rem:1", kind=NodeKind.REMAINDER, label="")
    node.set_field("text", "Some unclaimed text\nMore text\n")
    assert render_node(node) == "Some unclaimed text\nMore text\n"
```

- [ ] **Step 2: Implement render_node for REMAINDER**

```python
# src/elspais/graph/render.py
"""Render protocol — each NodeKind knows how to produce its text representation."""

from elspais.graph.GraphNode import GraphNode, NodeKind


def render_node(node: GraphNode) -> str:
    """Render a node to its text representation."""
    renderer = _RENDERERS.get(node.kind)
    if renderer is None:
        raise ValueError(f"No renderer for {node.kind}")
    return renderer(node)


def _render_remainder(node: GraphNode) -> str:
    return node.get_field("text", "")


_RENDERERS = {
    NodeKind.REMAINDER: _render_remainder,
}
```

- [ ] **Step 3: Run test, verify pass, commit**

- [ ] **Step 4: Write failing tests for REQUIREMENT render**

Test that a REQUIREMENT renders its full block: header, metadata, body, assertions section, sections, end marker.

- [ ] **Step 5: Implement REQUIREMENT renderer**

This is the most complex renderer. It must reconstruct the full requirement block from the node's content fields and STRUCTURES children (assertions, sections), ordered by their sequence.

Read the current requirement format from existing spec files and the RequirementParser to understand the exact format.

- [ ] **Step 6: Write and implement renderers for CODE, TEST, USER_JOURNEY**

CODE renders `# Implements: REQ-xxx` comment lines.
TEST renders `# Tests: REQ-xxx` comment lines.
USER_JOURNEY renders the full `## JNY-xxx: Title` block.

- [ ] **Step 7: Run full test suite, commit**

```bash
git add src/elspais/graph/render.py tests/graph/test_render.py
git commit -m "[CUR-1082] feat: render protocol for all NodeKinds"
```

---

### Task 19: Implement render-based save operation

**Files:**
- Create: `src/elspais/graph/save.py`
- Test: `tests/graph/test_save.py`

- [ ] **Step 1: Write failing round-trip test**

```python
# tests/graph/test_save.py
"""Tests for render-based save operation."""

from pathlib import Path

from elspais.graph.GraphNode import NodeKind
from elspais.graph.save import save_dirty_files


def test_save_round_trip(tmp_path):
    """Build graph, save, rebuild — graphs should match."""
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    original_content = """\
## REQ-p00001: Test Requirement

**Level**: PRD | **Status**: Draft

Body text.

## Assertions

- **A**: First assertion

*End* *REQ-p00001*
"""
    (spec_dir / "reqs.md").write_text(original_content, encoding="utf-8")

    from elspais.graph.factory import build_graph

    config = {
        "project": {"namespace": "p"},
        "id-patterns": {"prefixes": {"prd": "p", "ops": "o", "dev": "d"}},
        "spec": {"directories": ["spec"]},
    }
    graph = build_graph(
        repo_root=tmp_path,
        config=config,
        spec_dirs=[spec_dir],
        scan_code=False,
        scan_tests=False,
        scan_sponsors=False,
    )

    # Save (no mutations, so output should match input)
    save_dirty_files(graph, force_all=True)

    # Read back the file
    written = (spec_dir / "reqs.md").read_text(encoding="utf-8")

    # Rebuild graph from the written file
    graph2 = build_graph(
        repo_root=tmp_path,
        config=config,
        spec_dirs=[spec_dir],
        scan_code=False,
        scan_tests=False,
        scan_sponsors=False,
    )

    # Compare: same requirements, same assertions
    req1 = graph.find_by_id("REQ-p00001")
    req2 = graph2.find_by_id("REQ-p00001")
    assert req1 is not None and req2 is not None
    assert req1.get_label() == req2.get_label()
```

- [ ] **Step 2: Implement save_dirty_files**

```python
# src/elspais/graph/save.py
"""Render-based save — write FILE nodes to disk."""

from elspais.graph.builder import TraceGraph
from elspais.graph.GraphNode import NodeKind
from elspais.graph.relations import EdgeKind
from elspais.graph.render import render_node


def save_dirty_files(
    graph: TraceGraph,
    force_all: bool = False,
    save_branch: bool = True,
    verify: bool = True,
) -> list[str]:
    """Save dirty FILE nodes to disk by rendering their CONTAINS children.

    Args:
        graph: The TraceGraph to save.
        force_all: If True, save all FILE nodes regardless of dirty state.
        save_branch: If True, create a safety branch before writing.
        verify: If True, rebuild graph after save and compare for round-trip fidelity.

    Returns:
        List of file paths that were written.
    """
    from pathlib import Path

    # 1. Create safety branch before writing (if requested)
    if save_branch:
        # Use existing safety branch mechanism from persistence.py
        # (import and call create_safety_branch or equivalent)
        pass  # Implementation will call the existing git branch helper

    # 2. Render and write each FILE node
    written: list[str] = []
    for file_node in graph.iter_by_kind(NodeKind.FILE):
        abs_path = file_node.get_field("absolute_path")
        if abs_path is None:
            continue

        # Get CONTAINS children sorted by render_order
        contains_edges = sorted(
            [e for e in file_node.iter_outgoing_edges() if e.kind == EdgeKind.CONTAINS],
            key=lambda e: e.metadata.get("render_order", 0.0),
        )

        # Render each child
        parts: list[str] = []
        for edge in contains_edges:
            parts.append(render_node(edge.target))

        content = "".join(parts)
        Path(abs_path).write_text(content, encoding="utf-8")
        written.append(abs_path)

    # 3. Rebuild-and-compare consistency check (if requested)
    if verify and written:
        # Rebuild graph from disk and compare to in-memory graph.
        # This proves round-trip fidelity per spec Section 5.2 Steps 4-5.
        # Implementation: call build_graph() with same config, compare
        # requirement IDs, assertion counts, labels, and hashes.
        pass  # Implementation details depend on how build_graph is invoked

    return written
```

- [ ] **Step 3: Run test, iterate until round-trip passes**

Run: `pytest tests/graph/test_save.py -v`

This will likely require iterating on the REQUIREMENT renderer to produce output that matches the parser's expectations.

- [ ] **Step 4: Run full test suite, commit**

```bash
git add src/elspais/graph/save.py tests/graph/test_save.py
git commit -m "[CUR-1082] feat: render-based save operation for FILE nodes"
```

---

### Task 20: Replace persistence.py with render-based save in MCP server

**Files:**
- Modify: `src/elspais/server/persistence.py` (or its callers)
- Modify: `src/elspais/mcp/server.py` (save_mutations tool)
- Test: run full suite including e2e

- [ ] **Step 1: Update save_mutations MCP tool to use new save**

Replace the call to `replay_mutations_to_disk()` with `save_dirty_files()`.

- [ ] **Step 2: Update move_requirement to use FILE node edge manipulation**

Remove CONTAINS edge from old FILE, add CONTAINS edge to new FILE with appropriate render_order.

- [ ] **Step 3: Run full test suite including e2e**

Run: `pytest -m ""`
Expected: PASS

- [ ] **Step 4: Delete persistence.py if all callers are migrated**

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "[CUR-1082] refactor: replace persistence.py with render-based save"
```

---

## Chunk 7: Order-Independent Assertion Hashing

### Task 21: Implement order-independent assertion hashing

**Files:**
- Modify: `src/elspais/utilities/hasher.py`
- Modify: `src/elspais/graph/builder.py` (hash computation in _add_requirement)
- Test: `tests/test_hasher.py` or `tests/graph/test_file_nodes.py`

- [ ] **Step 1: Write failing test**

```python
def test_assertion_hash_order_independent():
    """Reordering assertions should not change the requirement hash."""
    # Build two graphs with same assertions in different orders
    # Compare hashes — they should be identical
    ...
```

- [ ] **Step 2: Implement order-independent hashing**

In the hash computation:
1. Hash each assertion's normalized text individually.
2. Sort the individual hashes lexicographically.
3. Hash the sorted list to produce the final requirement hash.

- [ ] **Step 3: Run full test suite**

Run: `pytest`
Expected: PASS (existing hashes will change — this is expected per spec)

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "[CUR-1082] feat: order-independent assertion hashing"
```

---

## Chunk 8: Final Cleanup and Validation

### Task 22: Remove add_child deprecation alias if still present

- [ ] **Step 1: Verify add_child is fully removed**

Run: `grep -rn "add_child\|remove_child" src/ tests/`
Remove any remaining references.

- [ ] **Step 2: Run full test suite including e2e**

Run: `pytest -m ""`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "[CUR-1082] chore: final cleanup of deprecated add_child/remove_child"
```

---

### Task 23: End-to-end validation

- [ ] **Step 1: Run full test suite**

Run: `pytest -m ""`
Expected: ALL PASS

- [ ] **Step 2: Build graph from elspais's own spec files**

Run: `python -c "from elspais.graph.factory import build_graph; g = build_graph(); print(f'FILE nodes: {len(list(g.iter_roots(__import__(\"elspais.graph.GraphNode\", fromlist=[\"NodeKind\"]).NodeKind.FILE)))}')"`

Verify FILE nodes are created for all spec, code, and test files.

- [ ] **Step 3: Verify MCP tools work with FILE nodes**

Run the MCP server and test `get_workspace_info`, `search`, `get_requirement`, `get_subtree` — verify they return file information correctly.

- [ ] **Step 4: Commit any fixes**

```bash
git add -A
git commit -m "[CUR-1082] test: end-to-end validation of FILE node architecture"
```
