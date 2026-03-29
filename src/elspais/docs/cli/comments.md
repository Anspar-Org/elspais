# COMMENTS

The comment system provides a review annotation layer for requirements, assertions, edges, and body sections. Comments are stored as append-only JSONL files alongside spec files and are displayed in the interactive viewer.

## Storage

Comment files live in `.elspais/comments/` under the repository root, mirroring the spec file structure:

```
.elspais/comments/
  spec/
    auth.md.json          # comments for spec/auth.md
    billing.md.json       # comments for spec/billing.md
```

Each file contains one JSON event per line (JSONL format). Events are append-only -- new comments, replies, resolves, and promotes are appended, never edited in-place.

## Event Types

| Event     | Description                                              |
|-----------|----------------------------------------------------------|
| `comment` | New top-level comment on an anchor                       |
| `reply`   | Reply to an existing comment (references `parent`)       |
| `resolve` | Marks a thread as resolved (references `target`)         |
| `promote` | Moves a comment to a new anchor after rename/deletion    |

## Anchors

Every comment targets an **anchor** -- a string identifying what it's attached to:

| Anchor Format            | Example                  | Target                |
|--------------------------|--------------------------|-----------------------|
| `NODE_ID`                | `REQ-p00001`             | Requirement card      |
| `NODE_ID#LABEL`          | `REQ-p00001#A`           | Assertion             |
| `NODE_ID#edge:TARGET`    | `REQ-p00001#edge:REQ-d00003` | Edge/relationship |
| `NODE_ID#section:NAME`   | `REQ-p00001#section:Rationale` | Body section     |

When a node or assertion is renamed, the system automatically updates comment anchors. When a node is deleted, comments are promoted to the nearest living ancestor or marked as orphaned.

## CLI Commands

### `elspais comments compact`

Rewrites JSONL files to remove noise:

- **Strips resolved threads** -- removes the original comment, all replies, and the resolve event
- **Collapses promote chains** -- when a comment is promoted multiple times, keeps only the final promote event

```
$ elspais comments compact
  spec/auth.md.json: 5 events removed
  spec/billing.md.json: 2 events removed
Compacted 2 file(s), 7 event(s) removed.
```

Run this periodically or before committing to keep comment files concise.

## Viewer Integration

When the viewer starts, it loads all comment JSONL files and populates the in-memory comment index. Comments appear as:

- **Margin indicators** -- speech bubble icons on card elements that have threads
- **Inline threads** -- click an indicator to expand the thread below the target element
- **Lost Comments card** -- a warning card at the top of the card stack showing orphaned comments

### Comment Mode

In Edit Mode, press **C** or click the speech bubble toolbar button to enter comment mode. Click any element with a `data-anchor` attribute to add a comment. The mode is one-shot: after placing one comment, it exits automatically.

### Reply and Resolve

In Edit Mode, expanded threads show **Reply** and **Resolve** buttons. Reply adds a nested response; Resolve dismisses the thread.

## API Endpoints

| Method | Path                      | Description                        |
|--------|---------------------------|------------------------------------|
| POST   | `/api/comment/add`        | Create a new comment               |
| POST   | `/api/comment/reply`      | Reply to an existing comment       |
| POST   | `/api/comment/resolve`    | Resolve (dismiss) a thread         |
| GET    | `/api/comments`           | Get threads for an anchor          |
| GET    | `/api/comments/card`      | Get all threads for a card (node)  |
| GET    | `/api/comments/orphaned`  | Get orphaned threads               |

Author identity is resolved server-side via `get_author_info` -- it is never supplied by the client.
