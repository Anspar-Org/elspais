# Viewer Edit Improvements — Design

**Date:** 2026-03-08
**Branch:** exemplar
**Ticket:** CUR-1081

## Problem

The viewer's edit mode lacks visual affordances (no pencil icons), allows editing the REQ ID
(which would break references), has no UI for managing relationships (implements/refines) despite
the backend API existing, and no UI for deleting assertions or requirements.

## Design

### 1. Split REQ ID from Title

Render requirement headings as two spans:
- `<span class="req-id">REQ-p00001</span>` — non-editable, visually muted
- `<span contentEditable class="req-title">Title text</span>` — editable

Only the title span triggers the `POST /api/mutate/title` endpoint. The ID is never sent as
part of the update.

### 2. Pencil Icons for Editable Fields

Small pencil icon appears on hover next to editable fields (title, assertion text). Clicking
the pencil focuses the contentEditable element. This is a cosmetic affordance — direct
click/focus on the text still works.

### 3. Relationship Inline Editor

Below each requirement's assertions section, display current relationships:

```text
Implements: REQ-o00063 — Operational Requirements [x]
Refines: REQ-p00001-A — CLI validation [x]
[+ Add relationship]
```

Each relationship row shows:
- Type label (Implements/Refines) — clickable to toggle type
- Target ID and title (requirement or assertion level)
- Delete [x] button

"Add relationship" expands an inline form:
- **Type dropdown:** Implements / Refines
- **Searchable requirement dropdown:** type-ahead input filtering via `/api/search?q=...`,
  showing `ID — Title` in results. Debounced at 300ms.
- **Assertion selector (optional):** once a requirement is selected, a second dropdown
  lists its assertions (fetched via `/api/node/<req_id>`). User can pick a specific
  assertion for assertion-level linking, or leave blank for requirement-level.
- Add button submits to `POST /api/mutate/edge`

### 4. Delete Assertion

Small trash icon on hover next to each assertion. Clicking shows a confirmation prompt
("Delete assertion REQ-p00001-A?"). Confirmed deletion calls the existing assertion
delete mutation.

### 5. Delete Requirement

Trash icon in the requirement header area (near the status dropdown). Clicking shows a
confirmation dialog: "Delete REQ-p00001 and all its assertions? This cannot be undone
without reverting." Confirmed deletion calls the existing requirement delete mutation
and removes the node from the UI.

### 6. Searchable Requirement Dropdown Component

Reusable UI component used by the relationship editor:
- Text input with dropdown list overlay
- Fetches candidates from `/api/search?q=<typed text>` (endpoint already exists)
- Shows `ID — Title` per result
- Debounced input (300ms)
- Keyboard navigation (arrow keys, Enter to select, Escape to close)
- Used for both the requirement picker and could be reused for future features

## Backend Status

All required backend APIs already exist:
- `POST /api/mutate/edge` — add/delete/change edge
- `POST /api/mutate/assertion/add` — add assertion
- `POST /api/mutate/title` — update title
- `POST /api/mutate/status` — change status
- `GET /api/search` — search requirements
- `GET /api/node/<id>` — get requirement details (assertions)
- `POST /api/mutate/undo` — undo last mutation
- `POST /api/save` — persist to disk
- `POST /api/revert` — discard mutations

No new backend endpoints are needed. All work is in the Jinja2 templates and
JavaScript edit engine.

## Out of Scope

- Requirement ID renaming (too many cross-reference implications)
- Drag-and-drop relationship reordering
- Bulk operations
