# Design: Comment / Review System

## Purpose

Allow reviewers to annotate requirements, assertions, relationships, and body sections
with threaded comments during the review process. Comments are persisted through git,
providing an auditable record of review activity alongside specification changes.

## Scope

- Viewer-only feature (future: CLI `checks` integration)
- Edit Mode required (comments are git-committed artifacts)
- Flat reply threads, per-target anchoring
- Append-only event storage in JSONL files

---

## UX: Comment Mode

### Entry and Exit

- **Keyboard shortcut**: Press `C` while in Edit Mode
- **Toolbar button**: Speech bubble icon next to the Edit Mode toggle, enabled only in Edit Mode
- **Toast on entry**: "Click any element to add a comment. Press Esc to cancel."
- **Exit**: Auto-exits after one comment is submitted. Also exits on `Esc` or clicking
  the toolbar button again.

Comment Mode is **one-shot**: enter, click target, type comment, submit, exit.

### Cursor and Hover

- Cursor changes to a speech bubble icon when hovering valid targets
- Valid targets get a subtle blue highlight on hover (distinct from Edit Mode's orange)
- Non-target areas show default cursor

### Comment Targets and Anchor Format

Each commentable element has a stable, human-readable **anchor** derived from the graph:

| Target                  | Anchor format                        | Card mode      |
|-------------------------|--------------------------------------|----------------|
| Whole requirement       | `REQ-p00001`                         | Both           |
| Assertion               | `REQ-p00001#A`                       | Both           |
| Body section            | `REQ-p00001#section:Rationale`       | Complete only  |
| Edge (any kind)         | `REQ-p00001#edge:REQ-d00003`         | Both           |
| Whole journey           | `JNY-001`                            | Both           |
| Journey section         | `JNY-001#section:Setup`              | Complete only  |
| Validates edge          | `JNY-001#edge:REQ-p00001`            | Both           |

Edge anchors do not encode edge kind. A comment on an edge is likely about
changing its type, so the anchor survives kind changes.

---

## UX: Inline Threads

### Placement

Comment threads render **inline**, directly below the target element, pushing
content down (like GitHub PR inline comments).

```text
  A: The system shall authenticate users via OAuth2      [speech bubble] 2
  +-----------------------------------------------------+
  | Alice Smith (alice@co.org) . 2026-03-20              |
  | Should we support SAML as well?            [Resolve] |
  |                                                      |
  | Bob Jones (bob@co.org) . 2026-03-21                  |
  | Out of scope for v1. Add to backlog.       [Resolve] |
  |                                                      |
  | [Reply...]                                           |
  +------------------------------------------------------+
  B: Sessions expire after 30 minutes of inactivity
```

### Thread Display Rules

- Flat list, chronological (newest at bottom)
- Author format: `Name (email) . YYYY-MM-DD` — matches CHANGELOG entry pattern
- Author identity from `get_author_info()` (same as changelog: `gh` primary, `git` fallback,
  controlled by `[changelog].id_source` config)
- `[Resolve]` button per comment, visible only in Edit Mode
- `[Reply...]` textarea at bottom, visible only in Edit Mode
- Outside Edit Mode: threads are read-only (expand/collapse only)

### Resolved Comments

Resolved comments **disappear** from the UI entirely. They remain in git history
and can be seen by viewing a prior commit. No "show resolved" toggle.

---

## UX: Margin Column

### Layout

A narrow gutter on the right edge of every card, always visible regardless of mode.

```text
  +-- REQ-p00001 -- Authentication -- [compact v] -- [X] --+  margin
  | Level: DEV    Status: Active                            |    |
  |                                                         |    |
  | Implements: REQ-o00012                                  |  [speech bubble]
  |                                                         |    |
  | A: The system shall authenticate users via OAuth2       |  [speech bubble] 2
  | B: Sessions expire after 30 minutes of inactivity       |    |
  | C: Failed login attempts locked after 5 tries           |  [speech bubble]
  |                                                         |    |
  +-- ... ------------------------------------------------- +    |
```

### Margin Icon States

| State                         | Icon                        | Behavior on click          |
|-------------------------------|-----------------------------|----------------------------|
| No comments on element        | (empty)                     | —                          |
| Has unresolved comments       | Speech bubble (with count)  | Expand/collapse thread     |
| New comment being entered     | Speech bubble pulsing       | —                          |

Count badge shown when thread has >1 comment (e.g. speech bubble with "3").

---

## UX: Promoted (Orphaned) Comments

When a comment's target is deleted from the graph, the comment is **promoted**
up the hierarchy to the nearest living ancestor.

### Display

Promoted comments show their original context:

```text
  [warning icon] Originally on Assertion D (deleted)
  Alice Smith (alice@co.org) . 2026-03-20
  This tolerance seems too tight for production.           [Resolve]
```

### Lost Comments Card

If no ancestor exists (root requirement was deleted), comments move to a
global **Lost Comments** card:

```text
  +-- Lost Comments (2) -------------------------------------------+
  | [warning icon] These comments have no valid target in the graph |
  |                                                                 |
  | Originally on REQ-p00001 (deleted)                              |
  | Alice Smith (alice@co.org) . 2026-03-20                         |
  | This entire requirement needs legal review.           [Resolve] |
  |                                                                 |
  | Originally on JNY-003#section:Setup (deleted)                   |
  | Bob Jones (bob@co.org) . 2026-03-22                             |
  | Setup steps are missing prerequisites.                [Resolve] |
  +-- ... --------------------------------------------------------- +
```

This card appears in the card column only when orphaned comments exist.

---

## UX: Compact / Complete Card Toggle

### Motivation

Body `##` sections (Rationale, Description, Notes, etc.) are not currently
displayed in cards. The Complete view makes them visible and commentable.

### Location

Global toggle in the **card column header**, applies to all open cards:

```text
  +-- 3 cards open ------ [Compact v] ------ [+REQ] [+JNY] --------+
```

- **Compact** (default): Current card layout (metadata, relationships, assertions)
- **Complete**: Adds body `##` sections as collapsible blocks between metadata and assertions

Persisted in the UI state cookie (`elspais_trace_state`).

---

## Storage: Append-Only JSONL Files

### File Organization

One comment file per source file, stored in `.elspais/comments/`, named by
appending `.json` to the source file's repo-relative path:

```text
spec/prd-auth.md           ->  .elspais/comments/spec/prd-auth.md.json
spec/dev-data.md           ->  .elspais/comments/spec/dev-data.md.json
journeys/onboarding.md     ->  .elspais/comments/journeys/onboarding.md.json
src/auth.dart              ->  .elspais/comments/src/auth.dart.json
                               .elspais/comments/_orphaned.json
```

The directory structure mirrors the repo structure. `_orphaned.json` holds
comments whose targets (and all ancestors) have been deleted.

### Event Schema

Each line in a `.json` file is one event:

```json
{"event":"comment","id":"c-20260320-a3f1b2","anchor":"REQ-p00001#A","author":"Alice Smith","author_id":"alice@co.org","date":"2026-03-20","text":"Should we support SAML?"}
{"event":"reply","id":"c-20260321-b4e2c3","parent":"c-20260320-a3f1b2","anchor":"REQ-p00001#A","author":"Bob Jones","author_id":"bob@co.org","date":"2026-03-21","text":"Out of scope for v1."}
{"event":"resolve","id":"c-20260321-d6f4a5","target":"c-20260320-a3f1b2","author":"Bob Jones","author_id":"bob@co.org","date":"2026-03-21"}
{"event":"promote","id":"c-20260322-e7g5b6","target":"c-20260320-a3f1b2","old_anchor":"REQ-p00001#D","new_anchor":"REQ-p00001","reason":"Assertion D deleted","from_file":"spec/prd-auth.md.json"}
```

### Event Types

| Event     | Required fields                                          | Meaning                                      |
|-----------|----------------------------------------------------------|----------------------------------------------|
| `comment` | id, anchor, author, author_id, date, text                | New top-level comment on a target             |
| `reply`   | id, parent, anchor, author, author_id, date, text        | Reply to an existing comment                  |
| `resolve` | id, target, author, author_id, date                      | Marks a comment and its replies as resolved   |
| `promote` | id, target, old_anchor, new_anchor, reason, from_file    | Re-anchors a comment due to target deletion   |

### Comment ID Generation

Format: `c-{YYYYMMDD}-{short_hash}`

Where `short_hash` is the first 6 characters of SHA-256 of
`anchor + author_id + date + text`. This avoids collisions across concurrent
branches (different content produces different hashes) and is grep-friendly.

---

## Pipeline Integration

### Comment Writes: Immediate to Disk

Comments bypass the mutation/save pipeline entirely. They are **not** graph
mutations — they don't dirty FILE nodes or change requirement content.

```text
User adds/replies/resolves comment in viewer
  -> POST /api/comment/{action}
  -> Append event to in-memory CommentIndex
  -> Append event line to the correct .json file on disk
  -> Done (no save_mutations() needed)
```

This matches the mental model: "I said something" is immediate, not draft state.

The mutation undo system (`undo_last_mutation`) does **not** apply to comments.
Comments have their own `resolve` event for reversal.

### Promotion: At Graph Build Time

When the graph is rebuilt (startup, `refresh_graph()`):

1. Build TraceGraph as usual
2. Load all `.elspais/comments/*.json` files
3. For each unresolved comment anchor:
   - If anchor exists in current graph: index it normally
   - If anchor is missing: walk up the hierarchy to find nearest living ancestor
     - If ancestor found: append `promote` event to source file, re-index under new anchor
     - If no ancestor found: append `promote` event, move to `_orphaned.json`
4. Attach `CommentIndex` to `TraceGraph`

### Anchor Updates on Rename

When `mutate_rename_node` or `mutate_rename_assertion` is called, the comment
system scans for anchors with the old ID prefix and updates them. This happens
as part of the rename mutation, not at build time — the rename operation
appends `promote` events with `reason: "Renamed from X to Y"`.

---

## Graph Integration

### CommentIndex on TraceGraph

`CommentIndex` is a field on `TraceGraph`, built during graph load:

```python
class TraceGraph:
    _comment_index: CommentIndex

    def iter_comments(self, anchor: str) -> Iterator[CommentThread]: ...
    def comment_count(self, anchor: str) -> int: ...
    def has_comments(self, anchor: str) -> bool: ...
    def iter_orphaned_comments(self) -> Iterator[CommentThread]: ...
```

Read-only query API. All writes go through the viewer API endpoints,
which append to JSONL files and update the in-memory index.

### CommentThread Model

```python
@dataclass
class CommentThread:
    root: CommentEvent          # The top-level comment
    replies: list[CommentEvent] # Flat list, chronological
    anchor: str                 # Current anchor (may differ from root.anchor if promoted)
    resolved: bool
    promoted_from: str | None   # Original anchor if promoted
    promotion_reason: str | None
```

---

## Viewer API Endpoints

| Endpoint                 | Method | Payload / Params                    | Effect                               |
|--------------------------|--------|-------------------------------------|--------------------------------------|
| `/api/comment/add`       | POST   | `{anchor, text}`                    | Append `comment` event               |
| `/api/comment/reply`     | POST   | `{parent_id, text}`                 | Append `reply` event                 |
| `/api/comment/resolve`   | POST   | `{comment_id}`                      | Append `resolve` event               |
| `/api/comments`          | GET    | `?anchor=REQ-p00001#A`              | Return thread for anchor             |
| `/api/comments/card`     | GET    | `?node_id=REQ-p00001`              | All comments for a card (all anchors with that node prefix) |
| `/api/comments/orphaned` | GET    | —                                   | Return orphaned comments             |

Author fields are auto-populated server-side via `get_author_info()`.

---

## Compaction

Over time, comment files grow with resolved and promoted events. A CLI command
provides optional cleanup:

```bash
elspais comments compact
```

This rewrites comment files:
- Strips resolved threads entirely (preserved in git history)
- Collapses promote chains (keeps only final anchor)
- Outputs a clean JSONL file

Manual operation only, never automatic.

---

## Future: Checks Integration

A future `elspais checks` integration would report:
- N unresolved comments (informational)
- M orphaned comments with no valid target (warning)

This is out of scope for the initial implementation.
