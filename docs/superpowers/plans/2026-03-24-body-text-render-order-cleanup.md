# Body Text Removal & Render Order Cleanup — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add explicit render_order metadata to STRUCTURES edges, then remove the redundant body_text field by computing all derived values from structured children.

**Architecture:** Two-phase cleanup. Phase 1 adds render_order to STRUCTURES edges (mirroring the existing CONTAINS edge pattern). Phase 2 removes body_text by replacing all reads with structured-children iteration, deletes the 4 regex body_text mutation helpers, removes the legacy RequirementParser, and relocates its shared regex constants.

**Tech Stack:** Python 3.10+, pytest, elspais graph internals.

**Spec:** `docs/superpowers/specs/2026-03-24-body-text-render-order-cleanup-design.md`

---

## File Map

### Phase 1 — render_order on STRUCTURES edges

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `src/elspais/graph/builder.py:2762-2764` | Assign render_order metadata when linking STRUCTURES edges |
| Modify | `src/elspais/graph/builder.py:1392` | Assign render_order in `mutate_add_assertion()` |
| Modify | `src/elspais/graph/render.py:121-139` | Sort STRUCTURES children by render_order in `_render_requirement()` |
| Modify | `src/elspais/server/routes_api.py:503` | Expose render_order for assertions in API |
| Test | `tests/core/test_render_protocol.py` | Existing render tests |
| Test | `tests/core/test_builder.py` | Existing builder tests |

### Phase 2 — Remove body_text + RequirementParser

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `src/elspais/graph/parsers/lark/transformers/requirement.py:223,795-811` | Remove `_extract_body_text()` and body_text from parsed_data |
| Modify | `src/elspais/graph/builder.py:2673` | Stop storing body_text in node content |
| Modify | `src/elspais/graph/builder.py:1177-1197` | `_compute_hash()` full-text mode: reconstruct from children |
| Modify | `src/elspais/graph/render.py:174-175` | Hash from children instead of body_text |
| Modify | `src/elspais/commands/validate.py:65-69` | `compute_hash_for_node()`: reconstruct from children |
| Modify | `src/elspais/commands/search_cmd.py:123-124` | Search body via structured children |
| Modify | `src/elspais/mcp/search.py:133-134` | `_get_field_text()`: iterate children |
| Modify | `src/elspais/mcp/server.py:373` | Remove body_text from `_node_to_dict()` |
| Modify | `src/elspais/mcp/server.py:671-674` | Regex field search via children |
| Modify | `src/elspais/mcp/server.py:1325` | Remove body from `_get_requirement()` |
| Delete | `src/elspais/graph/builder.py:1082-1175` | 4 body_text mutation helpers |
| Delete | `src/elspais/graph/builder.py:1277-1281,1338-1343,1394-1398,1483-1532` | Call sites of body_text helpers |
| Create | `src/elspais/graph/parsers/patterns.py` | Shared regex constants (relocated from RequirementParser) |
| Delete | `src/elspais/graph/parsers/requirement.py` | Legacy RequirementParser |
| Modify | `src/elspais/graph/factory.py:33,320` | Remove RequirementParser import and registration |
| Modify | `src/elspais/graph/builder.py:23,1080` | Import from patterns.py instead of RequirementParser |
| Modify | `src/elspais/utilities/spec_writer.py:204,218,281,295,375,389` | Import from patterns.py |

---

## Task 1: Add render_order to STRUCTURES edges during build

**Files:**
- Modify: `src/elspais/graph/builder.py:2762-2764`
- Test: `tests/core/test_builder.py`

- [ ] **Step 1: Write failing test — STRUCTURES edges carry render_order**

In `tests/core/test_builder.py`, add a test that builds a requirement with assertions and remainder sections, then verifies each STRUCTURES edge has render_order metadata in document order.

Use the `build_graph()` helper from `tests/core/graph_test_helpers.py` to build a graph from a fixture spec file that contains a requirement with assertions and remainder sections. Then verify STRUCTURES edges carry render_order metadata.

```python
# Implements: REQ-d00131-B
def test_structures_edges_carry_render_order():
    """STRUCTURES edges must carry render_order metadata like CONTAINS edges."""
    from tests.core.graph_test_helpers import build_graph, make_requirement
    from elspais.graph.relations import EdgeKind
    from elspais.graph.GraphNode import NodeKind

    # Build a graph with a requirement that has assertions + remainder
    graph = build_graph(make_requirement(
        req_id="REQ-t00001",
        title="Test Requirement",
        level="dev",
        status="Active",
        assertions=[("A", "First assertion"), ("B", "Second assertion")],
        body="Some preamble text.",
    ))

    # Find the requirement
    req = None
    for node in graph.iter_by_kind(NodeKind.REQUIREMENT):
        req = node
        break
    assert req is not None

    orders = []
    for edge in req.iter_outgoing_edges():
        if edge.kind == EdgeKind.STRUCTURES:
            assert "render_order" in edge.metadata, (
                f"STRUCTURES edge to {edge.target.id} missing render_order"
            )
            orders.append(edge.metadata["render_order"])

    assert len(orders) >= 2, "Need at least 2 STRUCTURES children"
    # Orders should be monotonically increasing (document order)
    assert orders == sorted(orders), f"render_order not in document order: {orders}"
```

**Note:** The exact helper usage depends on what `graph_test_helpers.py` provides. Read that file first and adapt the test to use whatever graph-building helpers are available. If `make_requirement` doesn't exist, use `build_graph()` with a `ParsedContent` object or build from a fixture spec file.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_builder.py::test_structures_edges_carry_render_order -v`
Expected: FAIL — `"render_order" in edge.metadata` assertion fails because STRUCTURES edges currently have no metadata.

- [ ] **Step 3: Implement — assign render_order during build**

In `src/elspais/graph/builder.py`, modify the STRUCTURES linking loop at line 2762-2764. After sorting `children_with_lines`, set render_order on each edge:

```python
# Add children in document order (sorted by line number)
children_with_lines.sort(key=lambda x: x[0])
for line_num, child_node in children_with_lines:
    edge = node.link(child_node, EdgeKind.STRUCTURES)
    edge.metadata = {"render_order": float(line_num)}
```

The key change: capture the return value of `link()` and set `edge.metadata`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_builder.py::test_structures_edges_carry_render_order -v`
Expected: PASS

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `pytest tests/ --tb=short -q`
Expected: All tests pass (the metadata addition is additive, shouldn't break anything).

---

## Task 2: Sort by render_order in `_render_requirement()`

**Files:**
- Modify: `src/elspais/graph/render.py:121-139`
- Test: `tests/core/test_render_protocol.py`

- [ ] **Step 1: Write failing test — render uses render_order not insertion order**

In `tests/core/test_render_protocol.py`, add a test that builds a requirement where STRUCTURES edges have render_order that differs from insertion order, then verifies the renderer respects render_order.

```python
# Implements: REQ-d00131-B
def test_render_requirement_sorts_by_render_order():
    """_render_requirement() must sort STRUCTURES children by render_order."""
    from elspais.graph.GraphNode import GraphNode, NodeKind
    from elspais.graph.relations import EdgeKind
    from elspais.graph.render import _render_requirement

    # Build a requirement with two assertions linked in reverse order
    req = GraphNode(id="REQ-t00001", kind=NodeKind.REQUIREMENT, label="Test Req")
    req._content = {"level": "dev", "status": "Active", "hash_mode": "normalized-text"}

    a_node = GraphNode(id="REQ-t00001-A", kind=NodeKind.ASSERTION, label="First assertion")
    a_node._content = {"label": "A"}

    b_node = GraphNode(id="REQ-t00001-B", kind=NodeKind.ASSERTION, label="Second assertion")
    b_node._content = {"label": "B"}

    # Link B first (insertion order: B, A), but give A lower render_order
    edge_b = req.link(b_node, EdgeKind.STRUCTURES)
    edge_b.metadata = {"render_order": 20.0}
    edge_a = req.link(a_node, EdgeKind.STRUCTURES)
    edge_a.metadata = {"render_order": 10.0}

    output = _render_requirement(req)
    lines = output.split("\n")
    assertion_lines = [l for l in lines if l and l[0].isalpha() and ". " in l]

    assert assertion_lines[0].startswith("A."), f"Expected A first, got: {assertion_lines}"
    assert assertion_lines[1].startswith("B."), f"Expected B second, got: {assertion_lines}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_render_protocol.py::test_render_requirement_sorts_by_render_order -v`
Expected: FAIL — B appears before A because current code uses insertion order.

- [ ] **Step 3: Implement — sort STRUCTURES children by render_order**

In `src/elspais/graph/render.py`, replace the direct iteration at line 127 with render_order-sorted iteration. Model after `render_file()` at lines 240-249:

```python
    # Collect STRUCTURES children with render_order for sorting
    children_with_order: list[tuple[float, GraphNode]] = []
    for edge in node.iter_outgoing_edges():
        if edge.kind == EdgeKind.STRUCTURES:
            order = edge.metadata.get("render_order", 0.0)
            children_with_order.append((order, edge.target))

    # Fall back to insertion order if no render_order metadata
    if children_with_order:
        children_with_order.sort(key=lambda x: x[0])
        ordered_children = [child for _, child in children_with_order]
    else:
        ordered_children = list(node.iter_children(edge_kinds={EdgeKind.STRUCTURES}))

    for child in ordered_children:
```

Update the comment at line 121-122 to reflect the new sorting strategy.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_render_protocol.py::test_render_requirement_sorts_by_render_order -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ --tb=short -q`
Expected: All pass — existing tests should still work because render_order matches original line-number insertion order from the builder.

---

## Task 3: Assign render_order in `mutate_add_assertion()`

**Files:**
- Modify: `src/elspais/graph/builder.py:1392`
- Test: `tests/core/test_builder.py`

- [ ] **Step 1: Write failing test — new assertion gets render_order**

Build a graph using the same approach as Task 1, then call `add_assertion()` (the public mutation method on TraceGraph).

```python
# Implements: REQ-d00131-B
def test_add_assertion_sets_render_order():
    """add_assertion() must set render_order on the new STRUCTURES edge."""
    from tests.core.graph_test_helpers import build_graph, make_requirement
    from elspais.graph.relations import EdgeKind
    from elspais.graph.GraphNode import NodeKind

    graph = build_graph(make_requirement(
        req_id="REQ-t00001",
        title="Test Requirement",
        level="dev",
        status="Active",
        assertions=[("A", "First assertion")],
    ))

    req = next(graph.iter_by_kind(NodeKind.REQUIREMENT))

    # Get max existing render_order
    max_order = 0.0
    for edge in req.iter_outgoing_edges():
        if edge.kind == EdgeKind.STRUCTURES:
            max_order = max(max_order, edge.metadata.get("render_order", 0.0))

    new_label = "ZZ"
    graph.add_assertion(req.id, new_label, "Test assertion text")

    # Find the new assertion's STRUCTURES edge
    new_edge = None
    for edge in req.iter_outgoing_edges():
        if edge.kind == EdgeKind.STRUCTURES and edge.target.id.endswith(f"-{new_label}"):
            new_edge = edge
            break

    assert new_edge is not None, "New assertion edge not found"
    assert "render_order" in new_edge.metadata, "Missing render_order on new assertion"
    assert new_edge.metadata["render_order"] > max_order, (
        "New assertion render_order should be after existing children"
    )
```

**Note:** Same caveat as Task 1 — adapt the graph-building approach to match available helpers. The method name is `add_assertion()` on TraceGraph, NOT `mutate_add_assertion()`.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_builder.py::test_mutate_add_assertion_sets_render_order -v`
Expected: FAIL — no render_order on the new edge.

- [ ] **Step 3: Implement — set render_order in mutate_add_assertion**

In `src/elspais/graph/builder.py` at line 1392, capture the edge and set render_order:

```python
        # Add to index and link to parent
        self._index[assertion_id] = assertion_node
        edge = parent.link(assertion_node, EdgeKind.STRUCTURES)

        # Assign render_order after existing children
        max_order = 0.0
        for e in parent.iter_outgoing_edges():
            if e.kind == EdgeKind.STRUCTURES and e is not edge:
                max_order = max(max_order, e.metadata.get("render_order", 0.0))
        edge.metadata = {"render_order": max_order + 1.0}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_builder.py::test_mutate_add_assertion_sets_render_order -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ --tb=short -q`
Expected: All pass.

---

## Task 4: Expose render_order in API

**Files:**
- Modify: `src/elspais/server/routes_api.py:503`

- [ ] **Step 1: Modify API to include render_order with assertions**

In `src/elspais/server/routes_api.py` at line 503, change the assertion serialization to include render_order. Instead of `sorted(assertions)`, return assertions with their render_order so the viewer can sort by document order instead of alphabetical:

Read the current assertion collection code (around lines 85-90 and 503) to understand the exact data shape, then modify to return `[{"label": "A", "render_order": 10.0}, ...]` or keep the flat sorted list but sort by render_order instead of alphabetical. Prefer the simpler approach — just change the sort key.

The simplest change: when collecting assertions, also collect render_order, then sort by render_order instead of label:

```python
# Where assertions are collected (around line 85-90), capture render_order:
assertion_data: list[tuple[float, str]] = []
for edge in node.iter_outgoing_edges():
    if edge.kind == EdgeKind.STRUCTURES and edge.target.kind == NodeKind.ASSERTION:
        label = edge.target.get_field("label", "")
        order = edge.metadata.get("render_order", 0.0)
        if label:
            assertion_data.append((order, label))
assertion_data.sort()  # Sort by render_order (first element)
assertions = [label for _, label in assertion_data]
```

- [ ] **Step 2: Run full test suite**

Run: `pytest tests/ --tb=short -q`
Expected: All pass.

---

## Task 5: Phase 1 commit

- [ ] **Step 1: Bump version**

In `pyproject.toml`, change `version = "0.112.3"` to `version = "0.112.4"` (or whatever the current version is — check before editing).

- [ ] **Step 2: Commit**

```bash
git add src/elspais/graph/builder.py src/elspais/graph/render.py \
  src/elspais/server/routes_api.py \
  tests/core/test_builder.py tests/core/test_render_protocol.py \
  pyproject.toml
git commit -m "$(cat <<'EOF'
Add render_order metadata to STRUCTURES edges

STRUCTURES edges (REQ->ASSERTION, REQ->REMAINDER) now carry explicit
render_order metadata, matching the CONTAINS edge pattern. The renderer
sorts by render_order instead of relying on insertion order. Mutations
assign render_order to new edges.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Create `parsers/patterns.py` with shared regex constants

**Files:**
- Create: `src/elspais/graph/parsers/patterns.py`
- Reference: `src/elspais/graph/parsers/requirement.py:41-53`

- [ ] **Step 1: Read the 4 constants from RequirementParser**

Read `src/elspais/graph/parsers/requirement.py` lines 41-53 to get the exact regex definitions.

- [ ] **Step 2: Create patterns.py**

```python
# Implements: REQ-d00131-B
"""Shared regex patterns for requirement parsing.

These patterns are used by the Lark transformer, builder, and spec_writer.
Relocated from the legacy RequirementParser class.
"""
from __future__ import annotations

import re

ALT_STATUS_PATTERN = re.compile(r"\*\*Status\*\*:\s*(?P<status>\w+)")
IMPLEMENTS_PATTERN = re.compile(r"\*\*Implements\*\*:\s*(?P<implements>[^|\n]+)")
REFINES_PATTERN = re.compile(r"\*\*Refines\*\*:\s*(?P<refines>[^|\n]+)")
ASSERTION_LINE_PATTERN = re.compile(r"^\s*([A-Z0-9]+)\.\s+(.+)$", re.MULTILINE)
```

- [ ] **Step 3: Update builder.py imports**

In `src/elspais/graph/builder.py`:

Remove line 23: `from elspais.graph.parsers.requirement import RequirementParser`

Add: `from elspais.graph.parsers.patterns import ASSERTION_LINE_PATTERN`

Replace line 1080: `_ASSERTION_LINE_RE = RequirementParser.ASSERTION_LINE_PATTERN`
With: `_ASSERTION_LINE_RE = ASSERTION_LINE_PATTERN`

- [ ] **Step 4: Update spec_writer.py imports**

In `src/elspais/utilities/spec_writer.py`, there are 3 lazy imports (lines 204, 281, 375). Replace each:

```python
# Line 204: Replace
#   from elspais.graph.parsers.requirement import RequirementParser
# With:
    from elspais.graph.parsers.patterns import IMPLEMENTS_PATTERN

# Line 218: Replace
#   impl_match = RequirementParser.IMPLEMENTS_PATTERN.search(search_region)
# With:
    impl_match = IMPLEMENTS_PATTERN.search(search_region)
```

Same pattern for REFINES_PATTERN (line 281/295) and ALT_STATUS_PATTERN (line 375/389).

- [ ] **Step 5: Remove RequirementParser from factory.py**

In `src/elspais/graph/factory.py`:
- Remove line 33: `from elspais.graph.parsers.requirement import RequirementParser`
- Remove line 320: `registry.register(RequirementParser(resolver))`

- [ ] **Step 6: Run full test suite**

Run: `pytest tests/ --tb=short -q`
Expected: All pass. If any test directly imports RequirementParser from requirement.py, update it.

**Do NOT delete `parsers/requirement.py` yet** — that happens in Task 10 after all body_text references are removed.

---

## Task 7: Extract `reconstruct_body_text()` helper

**Files:**
- Modify: `src/elspais/graph/render.py` (add helper near top)
- Test: `tests/core/test_render_protocol.py`

This helper will be used by all 3 hash sites and 3 search sites to reconstruct body text from structured children. Define it once, use everywhere.

- [ ] **Step 1: Write failing test**

```python
# Implements: REQ-d00131-B
def test_reconstruct_body_text_from_children():
    """reconstruct_body_text() should produce text from STRUCTURES children."""
    from elspais.graph.GraphNode import GraphNode, NodeKind
    from elspais.graph.relations import EdgeKind
    from elspais.graph.render import reconstruct_body_text

    req = GraphNode(id="REQ-t00001", kind=NodeKind.REQUIREMENT, label="Test")
    req._content = {"level": "dev", "status": "Active"}

    # Add a preamble remainder
    preamble = GraphNode(id="rem-preamble", kind=NodeKind.REMAINDER, label="")
    preamble._content = {"heading": "preamble", "text": "Some preamble text."}
    edge_p = req.link(preamble, EdgeKind.STRUCTURES)
    edge_p.metadata = {"render_order": 1.0}

    # Add assertions
    a_node = GraphNode(id="REQ-t00001-A", kind=NodeKind.ASSERTION, label="First thing")
    a_node._content = {"label": "A"}
    edge_a = req.link(a_node, EdgeKind.STRUCTURES)
    edge_a.metadata = {"render_order": 2.0}

    b_node = GraphNode(id="REQ-t00001-B", kind=NodeKind.ASSERTION, label="Second thing")
    b_node._content = {"label": "B"}
    edge_b = req.link(b_node, EdgeKind.STRUCTURES)
    edge_b.metadata = {"render_order": 3.0}

    body = reconstruct_body_text(req)
    assert "Some preamble text." in body
    assert "A. First thing" in body
    assert "B. Second thing" in body
    # A should appear before B (render_order)
    assert body.index("A. First thing") < body.index("B. Second thing")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_render_protocol.py::test_reconstruct_body_text_from_children -v`
Expected: FAIL — `reconstruct_body_text` does not exist yet.

- [ ] **Step 3: Implement `reconstruct_body_text()`**

In `src/elspais/graph/render.py`, add near the top (after imports):

```python
def reconstruct_body_text(node: GraphNode) -> str:
    """Reconstruct body text from STRUCTURES children in render_order.

    Used for full-text hash computation and search. Produces text equivalent
    to what was previously stored in the body_text field.

    Args:
        node: A REQUIREMENT node.

    Returns:
        Concatenated text of all ASSERTION and REMAINDER children.
    """
    # EdgeKind is already imported at module level in render.py

    # Collect children with render_order
    children_with_order: list[tuple[float, GraphNode]] = []
    for edge in node.iter_outgoing_edges():
        if edge.kind == EdgeKind.STRUCTURES:
            order = edge.metadata.get("render_order", 0.0)
            children_with_order.append((order, edge.target))
    children_with_order.sort(key=lambda x: x[0])

    parts: list[str] = []
    for _, child in children_with_order:
        if child.kind == NodeKind.ASSERTION:
            label = child.get_field("label") or ""
            text = child.get_label() or ""
            parts.append(f"{label}. {text}")
        elif child.kind == NodeKind.REMAINDER:
            text = child.get_field("text") or ""
            if text:
                parts.append(text)

    return "\n".join(parts)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_render_protocol.py::test_reconstruct_body_text_from_children -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ --tb=short -q`
Expected: All pass.

---

## Task 8: Replace body_text in hash computation

**Files:**
- Modify: `src/elspais/graph/render.py:174-175`
- Modify: `src/elspais/graph/builder.py:1177-1197`
- Modify: `src/elspais/commands/validate.py:65-69`
- Test: `tests/core/test_render_protocol.py`

- [ ] **Step 1: Write failing test — full-text hash uses structured children**

```python
# Implements: REQ-d00131-B
def test_fulltext_hash_from_structured_children():
    """Full-text hash mode should compute from structured children, not body_text."""
    from elspais.graph.GraphNode import GraphNode, NodeKind
    from elspais.graph.relations import EdgeKind
    from elspais.graph.render import _render_requirement

    req = GraphNode(id="REQ-t00001", kind=NodeKind.REQUIREMENT, label="Test")
    req._content = {
        "level": "dev",
        "status": "Active",
        "hash_mode": "full-text",
        # NO body_text field — hash must work without it
    }

    a_node = GraphNode(id="REQ-t00001-A", kind=NodeKind.ASSERTION, label="Must do X")
    a_node._content = {"label": "A"}
    edge_a = req.link(a_node, EdgeKind.STRUCTURES)
    edge_a.metadata = {"render_order": 1.0}

    output = _render_requirement(req)
    # Should contain a real hash, not hash of empty string
    assert "*End*" in output
    # Hash of empty string would be "e3b0c442" — we should NOT get that
    assert "e3b0c442" not in output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_render_protocol.py::test_fulltext_hash_from_structured_children -v`
Expected: FAIL — current code reads `body_text` which is None, hashes empty string, gets `e3b0c442`.

- [ ] **Step 3: Replace body_text reads in all 3 hash sites**

**In `src/elspais/graph/render.py` (line 174-175):**

```python
    # Compute hash using configured mode (DRY: utilities/hasher.py)
    hash_mode = node.get_field("hash_mode") or "normalized-text"
    if hash_mode == "full-text":
        body = reconstruct_body_text(node)
        hash_val = calculate_hash(body)
    else:
        hash_val = compute_normalized_hash(assertions)
```

**In `src/elspais/graph/builder.py` `_compute_hash()` (line 1177-1197):**

```python
    def _compute_hash(self, req_node: GraphNode) -> str:
        """Compute hash for a requirement node."""
        from elspais.graph.render import reconstruct_body_text

        if self.hash_mode == "normalized-text":
            assertions = []
            for child in req_node.iter_children(edge_kinds={EdgeKind.STRUCTURES}):
                if child.kind == NodeKind.ASSERTION:
                    label = child.get_field("label") or ""
                    text = child.get_label() or ""
                    if label and text:
                        assertions.append((label, text))
            return compute_normalized_hash(assertions)
        else:
            body = reconstruct_body_text(req_node)
            return calculate_hash(body)
```

**In `src/elspais/commands/validate.py` `compute_hash_for_node()` (line 65-69):**

```python
    else:
        from elspais.graph.render import reconstruct_body_text

        body = reconstruct_body_text(node)
        if not body:
            return None
        return calculate_hash(body)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_render_protocol.py::test_fulltext_hash_from_structured_children -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ --tb=short -q`
Expected: All pass (hash values may change for full-text mode fixtures — investigate and update if needed).

---

## Task 9: Replace body_text in search

**Files:**
- Modify: `src/elspais/commands/search_cmd.py:123-124`
- Modify: `src/elspais/mcp/search.py:133-134`
- Modify: `src/elspais/mcp/server.py:671-674`
- Test: `tests/core/test_render_protocol.py`

- [ ] **Step 1: Write failing test — search body via structured children**

```python
# Implements: REQ-d00131-B
def test_search_body_uses_structured_children():
    """Search 'body' field should find text in REMAINDER and ASSERTION children."""
    from elspais.graph.GraphNode import GraphNode, NodeKind
    from elspais.graph.relations import EdgeKind
    from elspais.mcp.search import _get_field_text

    req = GraphNode(id="REQ-t00001", kind=NodeKind.REQUIREMENT, label="Test")
    req._content = {"level": "dev", "status": "Active"}
    # NO body_text field

    preamble = GraphNode(id="rem-preamble", kind=NodeKind.REMAINDER, label="")
    preamble._content = {"heading": "preamble", "text": "unique_search_term_xyz"}
    edge_p = req.link(preamble, EdgeKind.STRUCTURES)
    edge_p.metadata = {"render_order": 1.0}

    result = _get_field_text(req, "body")
    assert "unique_search_term_xyz" in result
```

Run: `pytest tests/core/test_render_protocol.py::test_search_body_uses_structured_children -v`
Expected: FAIL — current `_get_field_text` reads `body_text` which is None, returns empty string.

- [ ] **Step 2: Replace in search_cmd.py**

At line 123-124, replace:

```python
        elif f == "body":
            text = node.get_field("body_text", "")
```

With:

```python
        elif f == "body":
            from elspais.graph.render import reconstruct_body_text
            text = reconstruct_body_text(node) if node.kind == NodeKind.REQUIREMENT else ""
```

- [ ] **Step 2: Replace in mcp/search.py**

At line 133-134, replace:

```python
    if field_name == "body":
        return node.get_field("body_text", "")
```

With:

```python
    if field_name == "body":
        from elspais.graph.render import reconstruct_body_text
        return reconstruct_body_text(node) if node.kind == NodeKind.REQUIREMENT else ""
```

- [ ] **Step 3: Replace in mcp/server.py regex field search**

At line 671-674, replace:

```python
    if field in ("body", "all"):
        body = node.get_field("body_text", "")
        if body and compiled_pattern.search(body):
            return True
```

With:

```python
    if field in ("body", "all"):
        from elspais.graph.render import reconstruct_body_text
        if node.kind == NodeKind.REQUIREMENT:
            body = reconstruct_body_text(node)
            if body and compiled_pattern.search(body):
                return True
```

- [ ] **Step 4: Drop body_text from API serialization**

In `src/elspais/mcp/server.py`:
- Line 373: Remove `"body_text": node.get_field("body_text"),` from the `properties` dict.
- Line 1325: Remove `"body": node.get_field("body_text"),` from the response dict.

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ --tb=short -q`
Expected: All pass.

---

## Task 10: Delete body_text mutation helpers and stop storing body_text

**Files:**
- Modify: `src/elspais/graph/builder.py` (multiple locations)
- Modify: `src/elspais/graph/parsers/lark/transformers/requirement.py:223,795-811`
- Delete: `src/elspais/graph/parsers/requirement.py`
- Test: `tests/core/test_builder.py`

- [ ] **Step 1: Write failing test — body_text field is absent after build**

```python
# Implements: REQ-d00131-B
def test_body_text_not_stored_after_build():
    """After Phase 2, body_text must not be stored in node content."""
    from tests.core.graph_test_helpers import build_graph, make_requirement
    from elspais.graph.GraphNode import NodeKind

    graph = build_graph(make_requirement(
        req_id="REQ-t00001",
        title="Test",
        level="dev",
        status="Active",
        assertions=[("A", "First assertion")],
        body="Preamble text.",
    ))

    req = next(graph.iter_by_kind(NodeKind.REQUIREMENT))
    assert req.get_field("body_text") is None, (
        "body_text should not be stored — use reconstruct_body_text() instead"
    )
```

Run: `pytest tests/core/test_builder.py::test_body_text_not_stored_after_build -v`
Expected: FAIL — body_text is still being stored by the builder at line 2673.

- [ ] **Step 2: Delete the 4 body_text helper methods**

In `src/elspais/graph/builder.py`, delete these methods entirely:
- `_update_assertion_in_body_text()` (lines 1082-1094)
- `_add_assertion_to_body_text()` (lines 1096-1148)
- `_delete_assertion_from_body_text()` (lines 1150-1161)
- `_rename_assertion_in_body_text()` (lines 1163-1175)

- [ ] **Step 3: Remove body_text helper call sites in mutations**

In `src/elspais/graph/builder.py`, remove all blocks that call these helpers:
- `mutate_rename_assertion()`: lines 1277-1281 (rename in body_text)
- `mutate_update_assertion()`: lines 1338-1343 (update in body_text)
- `mutate_add_assertion()`: lines 1394-1398 (add to body_text)
- `mutate_delete_assertion()`: lines 1483-1532 (delete + rename siblings in body_text)

For `mutate_delete_assertion()`, be careful: lines 1524-1530 rename sibling assertions in body_text during relabeling. The relabeling of actual assertion node IDs/labels must be preserved — only remove the body_text string manipulation.

- [ ] **Step 4: Stop storing body_text in node content**

In `src/elspais/graph/builder.py` at line 2673, remove:
```python
            "body_text": data.get("body_text", ""),  # For hash computation
```

- [ ] **Step 5: Remove _extract_body_text from Lark transformer**

In `src/elspais/graph/parsers/lark/transformers/requirement.py`:
- Remove the call at line 223: `body_text = self._extract_body_text(raw_text)`
- Remove `body_text` from parsed_data dict (around line 252)
- Delete the `_extract_body_text()` method (lines 795-811)

- [ ] **Step 6: Delete RequirementParser**

Delete the file: `src/elspais/graph/parsers/requirement.py`

- [ ] **Step 7: Run full test suite**

Run: `pytest tests/ --tb=short -q`
Expected: All pass. The test from Step 1 should now pass (body_text no longer stored). If any test directly references `body_text` or `RequirementParser`, update it.

- [ ] **Step 8: Run E2E tests**

Run: `pytest -m e2e --tb=short -q`
Expected: All pass.

---

## Task 11: Phase 2 commit

- [ ] **Step 1: Bump version**

In `pyproject.toml`, increment the patch version.

- [ ] **Step 2: Commit**

```bash
git add -A
git commit -m "$(cat <<'EOF'
Remove body_text field and legacy RequirementParser

body_text was a redundant flat string duplicating structured ASSERTION
and REMAINDER children. All consumers (hash, search, API) now use
reconstruct_body_text() which walks STRUCTURES children in render_order.
Deleted 4 regex body_text mutation helpers. Removed RequirementParser
registration (Lark parser is sole parser). Shared regex constants
relocated to parsers/patterns.py.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: Update KNOWN_ISSUES.md

- [ ] **Step 1: Mark both items as done**

In `KNOWN_ISSUES.md`, change:
- `[ ] graph: add render_order to STRUCTURES edges` → `[x] graph: add render_order to STRUCTURES edges`
- `[ ] refactor: remove body_text field from requirement nodes` → `[x] refactor: remove body_text field from requirement nodes`

Add resolution notes:
- render_order: "Fixed: STRUCTURES edges carry render_order metadata; renderer sorts by it; mutations maintain it"
- body_text: "Fixed: body_text removed; reconstruct_body_text() computes from children; RequirementParser deleted, patterns relocated to parsers/patterns.py"

- [ ] **Step 2: Amend commit**

```bash
git add KNOWN_ISSUES.md
git commit --amend --no-edit
```
