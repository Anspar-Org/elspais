# Design: Complete Card View Toggle

## Purpose

Requirement and journey cards currently show a compact view: metadata, relationships,
assertions. Body `##` sections (Rationale, Description, Notes, etc.) are not displayed.

The Complete view makes these sections visible in cards, giving reviewers full context
without switching to the file viewer.

## Dependency

This feature is a **prerequisite** for the Comment / Review System (see
`design_comments.md`), which needs body sections as comment targets. However, the
Complete view is independently useful and can ship first.

---

## UX

### Toggle Location

Global toggle in the **card column header**, between the card count and the action buttons:

```text
+-- 3 cards open ------ [Compact v] ------ [+REQ] [+JNY] --+
```

Dropdown or toggle with two states:

- **Compact** (default): Current card layout
- **Complete**: Current layout + body `##` sections

Applies to **all open cards** simultaneously. Persisted in the UI state cookie
(`elspais_trace_state`).

### Card Layout: Compact (unchanged)

```text
+-- REQ-p00001 -- Authentication -------------------- [X] --+
| Level: DEV    Status: Active    Hash: a1b2c3d4             |
|                                                             |
| Implements: REQ-o00012                                      |
|                                                             |
| [IMPLEMENTED] [TESTED] [VERIFIED]                           |
| A: The system shall authenticate users via OAuth2           |
| B: Sessions expire after 30 minutes of inactivity           |
| C: Failed login attempts locked after 5 tries               |
+-------------------------------------------------------------+
```

### Card Layout: Complete

```text
+-- REQ-p00001 -- Authentication -------------------- [X] --+
| Level: DEV    Status: Active    Hash: a1b2c3d4             |
|                                                             |
| Implements: REQ-o00012                                      |
|                                                             |
| ## Description                                         [-] |
| The authentication subsystem provides identity              |
| verification for all user-facing endpoints.                 |
|                                                             |
| ## Rationale                                           [-] |
| Required by SOC2 compliance framework and                   |
| customer contractual obligations.                           |
|                                                             |
| [IMPLEMENTED] [TESTED] [VERIFIED]                           |
| A: The system shall authenticate users via OAuth2           |
| B: Sessions expire after 30 minutes of inactivity           |
| C: Failed login attempts locked after 5 tries               |
+-------------------------------------------------------------+
```

Body sections appear **between relationships and assertions**, matching the
order they appear in the spec file.

### Section Rendering

- Each `##` section is a collapsible block with its heading as the toggle
- `[-]` / `[+]` collapse toggle per section (independent of the global compact/complete toggle)
- Content rendered as plain text (no markdown rendering — keeps it simple and consistent
  with how assertion text is displayed)
- In Edit Mode: section headings and content become editable (same pattern as
  journey section editing — `contentEditable` / textarea, blur-triggered mutation)
- Sections appear in the order defined by `render_order` from the graph's
  STRUCTURES edges

### Section Data Source

Body sections are already in the graph as REMAINDER nodes connected to
requirements via STRUCTURES edges. The data is there — it just needs to be
included in the card API response and rendered.

---

## API Changes

### GET /api/requirement/{id}

Add a `sections` field to the response when the card requests complete view:

```json
{
  "id": "REQ-p00001",
  "title": "Authentication",
  "sections": [
    {
      "heading": "Description",
      "content": "The authentication subsystem provides...",
      "render_order": 1.0,
      "node_id": "remainder:REQ-p00001:Description"
    },
    {
      "heading": "Rationale",
      "content": "Required by SOC2 compliance...",
      "render_order": 2.0,
      "node_id": "remainder:REQ-p00001:Rationale"
    }
  ]
}
```

Two options for when to include sections:

- **Option A**: Always include `sections` in the response; the JS decides whether to render
  based on the toggle state. Simpler server-side.
- **Option B**: Query parameter `?view=complete` controls inclusion. Saves bandwidth on
  compact view.

Recommendation: **Option A**. The section data is small relative to the rest of the
card payload, and it avoids re-fetching when the user toggles view mode.

### Edit Mode Mutations

Body section editing reuses the existing pattern. Sections are REMAINDER nodes,
so mutations would be:

| Endpoint                      | Payload                                | Effect                     |
|-------------------------------|----------------------------------------|----------------------------|
| `/api/mutate/section/content` | `{node_id, new_content}`               | Update section body text   |
| `/api/mutate/section/heading` | `{node_id, new_heading}`               | Rename section heading     |
| `/api/mutate/section/add`     | `{req_id, heading, content}`           | Add new section            |
| `/api/mutate/section/delete`  | `{node_id, confirm: true}`             | Delete section             |

These follow the same mutation/save pipeline as other graph mutations
(in-memory until `save_mutations()` is called).

---

## JS Implementation Sketch

### State

```javascript
// In editState (or viewState):
editState.cardView = 'compact';  // or 'complete'
```

Read from cookie on load, written to cookie on toggle.

### Toggle Handler

```javascript
function toggleCardView() {
    editState.cardView = editState.cardView === 'compact' ? 'complete' : 'compact';
    saveCookie();
    // Re-render all open cards — sections are already in cached card data
    editState.openCards.forEach(function(card) {
        renderCardSections(card);
    });
}
```

### Section Rendering

```javascript
function renderCardSections(card) {
    var container = document.getElementById('sections-' + card.data.id);
    if (editState.cardView === 'compact') {
        container.style.display = 'none';
        return;
    }
    container.style.display = '';
    // Render each section as collapsible block
    card.data.sections.forEach(function(sec) {
        // heading toggle + content div
        // In edit mode: contentEditable on heading, textarea on content
    });
}
```

The sections container is always present in the DOM (populated when the card
opens), just hidden in compact mode. Toggling is instant — no API call needed.

---

## Scope Boundary

This feature covers:
- Global compact/complete toggle in card column header
- Rendering body `##` sections in cards
- Per-section collapse/expand
- Section editing in Edit Mode (heading, content, add, delete)

Out of scope (handled by comment system):
- Comment targets on sections
- Margin column / annotation gutter
