# Design: Editable REMAINDER/Section Blocks in REQ Card

**Date:** 2026-03-24
**Status:** Draft
**Branch:** graph-cleanup

## Problem

REMAINDER nodes (preamble, named sections like "## Rationale", sub-headings) are rendered as read-only collapsible blocks in the requirement card. Users cannot edit section text, rename headings, add new sections, or delete existing ones from the viewer.

## Scope

Add full CRUD for REMAINDER nodes in the requirement card, matching the existing patterns for assertion editing (blur-save) and journey section editing (add/delete buttons).

**Excluded:** `definition_block` REMAINDER nodes (those with `content_type=definition_block`) are excluded from mutation. These carry structured term/definition data from the TermDictionary pipeline and must not be edited as plain text. The backend validates this and rejects mutations on definition_block nodes. The frontend hides edit controls for them.

## Backend — TraceGraph Mutation Methods

Three new methods on TraceGraph in `builder.py`, following the journey section pattern (`update_journey_section`, `add_journey_section`, `delete_journey_section`):

### `update_remainder(node_id, text=None, heading=None)`

Updates the text and/or heading of an existing REMAINDER node.

- Validates node exists and is `NodeKind.REMAINDER`
- Rejects if `content_type == "definition_block"`
- Updates `text` field if provided
- Updates `heading` field if provided (preamble heading stays "preamble" — frontend doesn't expose heading input for preamble)
- Finds parent requirement via STRUCTURES edge
- Marks parent dirty, recomputes hash
- Records `MutationEntry` with before/after state for undo
- Undo dispatch: `_undo_update_remainder()` restores original text/heading fields

### `add_remainder(req_id, heading, text)`

Creates a new REMAINDER node linked to the requirement.

- Validates parent exists and is `NodeKind.REQUIREMENT`
- Generates REMAINDER node ID using `{req_id}:section:m{counter}` format (the `m` prefix distinguishes mutation-created nodes from parse-created ones, avoiding ID collisions on rebuild; counter is max existing + 1)
- Creates `GraphNode` with `kind=NodeKind.REMAINDER`, sets `heading` and `text` fields
- **render_order computed on backend:** max existing STRUCTURES edge render_order + 1.0 (same pattern as `add_assertion`)
- Links to parent via `EdgeKind.STRUCTURES` with computed render_order in edge metadata
- Adds to index
- Marks parent dirty, recomputes hash
- Records `MutationEntry` for undo
- Undo dispatch: `_undo_add_remainder()` removes node and unlinks

### `delete_remainder(node_id)`

Removes a REMAINDER node.

- Validates node exists and is `NodeKind.REMAINDER`
- Rejects if `content_type == "definition_block"`
- Finds parent via STRUCTURES edge
- Unlinks from parent, removes from index
- Marks parent dirty, recomputes hash
- Records `MutationEntry` with full before state (including render_order) for undo
- Undo dispatch: `_undo_delete_remainder()` re-creates node, re-links with original render_order

All three methods support undo via the existing mutation log pattern. The undo dispatch table in `builder.py` (~line 387) must be extended with three new operation names (`update_remainder`, `add_remainder`, `delete_remainder`) mapping to their `_undo_*` methods.

## API Endpoints

Three new POST endpoints in `routes_api.py`, following `/api/mutate/*` conventions:

### `POST /api/mutate/remainder`

```json
{"node_id": "...", "text": "new text", "heading": "new heading"}
```

Calls `update_remainder()`. Both `text` and `heading` are optional (at least one required).

### `POST /api/mutate/remainder/add`

```json
{"req_id": "REQ-...", "heading": "New Section", "text": ""}
```

Calls `add_remainder()`. The backend computes render_order (max existing + 1.0).

### `POST /api/mutate/remainder/delete`

```json
{"node_id": "..."}
```

Calls `delete_remainder()`.

### API Response Enhancement

Add `render_order` to REMAINDER children in the node detail response (`mcp/server.py` ~line 282-291):

```python
{
    "kind": "remainder",
    "id": child.id,
    "heading": child.get_field("heading"),
    "text": child.get_field("text"),
    "line": child.get_field("parse_line"),
    "render_order": render_order_from_edge,
}
```

This requires changing the serialization loop from `node.iter_children()` to `node.iter_outgoing_edges(edge_kinds={EdgeKind.STRUCTURES})` so that edge metadata (render_order) is accessible alongside each child node. Also add render_order to ASSERTION children in the same loop.

## Frontend — Card Rendering and Edit Mode

### REMAINDER section rendering (`_card-stack.js.j2`)

Modify `buildRemainderHtml()` to support edit mode:

- **Edit mode on, named section:** Heading becomes `<input>` with `onblur="onRemainderHeadingBlur(this)"`, `data-node-id`, `data-original`. Content becomes `<textarea>` with `onblur="onRemainderTextBlur(this)"`, same data attributes.
- **Edit mode on, preamble:** No heading input (heading is always "preamble"). Content becomes `<textarea>` with blur handler.
- **Edit mode on:** Each section gets a delete button (trash icon), same style as journey section delete.
- **Edit mode off:** Render as today (collapsible, markdown-rendered, read-only).

### Sort by render_order

The complete view in `_card-stack.js.j2` currently sorts interleaved assertions and remainders by `r.line || 0`. Change this to sort by `r.render_order || 0` so that mutation-created sections (which have no parse_line) appear in the correct position.

### Add section button

An "+ Section" button rendered after the last section/assertion block when edit mode is on. Clicking:
1. Calls `POST /api/mutate/remainder/add` with `heading="New Section"`, `text=""`
2. Backend computes render_order (appends at end)
3. Refreshes card on success

### Blur handlers (`_edit-engine.js.j2`)

Four new functions following the existing pattern (compare `data-original`, dirty class, mutate call, refresh):

- `onRemainderTextBlur(el)` — `POST /api/mutate/remainder` with `{node_id, text}`
- `onRemainderHeadingBlur(el)` — `POST /api/mutate/remainder` with `{node_id, heading}`
- `onRemainderDelete(nodeId)` — confirmation prompt, then `POST /api/mutate/remainder/delete`
- `onRemainderAdd(reqId)` — `POST /api/mutate/remainder/add` with default heading/text

All handlers call `refreshAllOpenCards()` and `loadTreeData()` on success, and show toast notifications on error.

## Testing

### Backend (unit tests in `tests/core/`)

- `update_remainder()`: updates text, updates heading, marks parent dirty, recomputes hash, undo restores original
- `add_remainder()`: creates node with correct render_order, links to parent, undo removes it
- `delete_remainder()`: removes node, undo restores it with original render_order
- Preamble editing: update_remainder works on preamble nodes (heading="preamble")

### API (integration tests)

- Each endpoint returns success with valid input
- Card data reflects changes after mutation
- Invalid node_id / req_id returns appropriate error

### No browser tests

Follows the existing pattern — assertion/journey editing does not have Playwright coverage.

## Commit Plan

- **Commit 1:** Backend mutations + API endpoints + API render_order enhancement + tests
- **Commit 2:** Frontend edit mode for REMAINDER sections
