# Comment / Review System — Implementation Spec

Supersedes: `spec/roadmap/review-system.md`
Source design: `docs/design_comments.md`

## Approach

Bottom-up (Approach A): data models, file I/O, promotion, graph integration, API, viewer UI. Each layer independently testable, each phase one commit.

---

## 1. Data Models

New file: `src/elspais/graph/comments.py`

### CommentEvent

```python
@dataclass(frozen=True)
class CommentEvent:
    event: str           # "comment" | "reply" | "resolve" | "promote"
    id: str              # c-YYYYMMDD-6hexchars
    anchor: str          # e.g. "REQ-p00001#A"
    author: str          # display name
    author_id: str       # email
    date: str            # YYYY-MM-DD
    text: str = ""       # empty for resolve/promote
    parent: str = ""     # reply only: parent comment id
    target: str = ""     # resolve/promote: target comment id
    old_anchor: str = "" # promote only
    new_anchor: str = "" # promote only
    reason: str = ""     # promote only
    from_file: str = ""  # promote only: source JSONL file
```

Frozen (immutable) — matches append-only JSONL model. Note: `anchor` is present on all event types for efficient index building (the design doc only lists it as required for `comment` and `reply`, but having it on `resolve` events avoids back-reference lookups during thread assembly).

### CommentThread

```python
@dataclass
class CommentThread:
    root: CommentEvent
    replies: list[CommentEvent]  # flat, chronological
    anchor: str                  # current anchor (may differ from root if promoted)
    resolved: bool
    promoted_from: str | None    # original anchor if promoted
    promotion_reason: str | None
```

### CommentIndex

```python
class CommentIndex:
    _threads: dict[str, list[CommentThread]]  # anchor -> threads
    _orphaned: list[CommentThread]            # no valid ancestor
    _file_map: dict[str, Path]                # anchor -> source JSONL file

    def iter_threads(self, anchor: str) -> Iterator[CommentThread]: ...
    def thread_count(self, anchor: str) -> int: ...
    def has_threads(self, anchor: str) -> bool: ...
    def iter_orphaned(self) -> Iterator[CommentThread]: ...
    def iter_all_anchors_for_node(self, node_id: str) -> Iterator[str]: ...
```

`iter_all_anchors_for_node()` returns all anchors prefixed with a node ID (e.g. all `REQ-p00001#*` anchors), supporting the per-card comment query.

### Comment ID Generation

Format: `c-{YYYYMMDD}-{sha256(anchor+author_id+date+text)[:6]}`

Delegates to `utilities/hasher.py` (`calculate_hash` or a thin wrapper) per the project rule that all hash computation lives in that module. Content-based hash avoids collisions across concurrent branches.

---

## 2. JSONL File I/O

New file: `src/elspais/graph/comment_store.py`

Separated from models to isolate I/O.

### File Path Resolution

```python
def comment_file_for(repo_root: Path, spec_relative_path: str) -> Path:
    # spec/prd-auth.md -> {repo_root}/.elspais/comments/spec/prd-auth.md.json
    return repo_root / ".elspais" / "comments" / f"{spec_relative_path}.json"

ORPHANED_FILE = "_orphaned.json"
```

Directory structure mirrors repo structure.

### Functions

- `load_events(path: Path) -> list[CommentEvent]` — Read all events from JSONL. Returns empty list if file missing.
- `append_event(path: Path, event: CommentEvent) -> None` — Append single event line. Creates parent dirs if needed.
- `assemble_threads(events: list[CommentEvent]) -> list[CommentThread]` — Pure function: group by root, attach replies, apply resolve/promote events, filter resolved.
- `compact_file(path: Path) -> int` — Rewrite JSONL: strip resolved, collapse promote chains. Returns events removed.
- `generate_comment_id(anchor, author_id, date, text) -> str` — ID generation per format above.
- `load_comment_index(repo_root: Path) -> CommentIndex` — Glob `.elspais/comments/**/*.json`, load + assemble per file, populate index.

---

## 3. Promotion Engine

Lives in `comment_store.py`.

### Core Function

```python
def promote_orphaned_comments(
    index: CommentIndex,
    graph: TraceGraph,
    repo_root: Path,
) -> list[CommentEvent]:
```

Called at graph build time (after TraceGraph is constructed). For each unresolved thread:

1. Parse anchor into (node_id, fragment_type, fragment_value)
2. Validate anchor target exists in graph
3. If invalid, walk up hierarchy for nearest living ancestor:
   - Fragment missing but node exists: promote to node (drop fragment)
   - Node missing: walk parents to find first living ancestor
   - No ancestor: move to `_orphaned.json` (stays in same repo)
4. Append promote event to source JSONL file
5. Update CommentIndex in-place

Returns list of promote events appended.

### Anchor Parsing

```python
def parse_anchor(anchor: str) -> tuple[str, str | None, str | None]:
    # (node_id, fragment_type, fragment_value)
    # REQ-p00001        -> ('REQ-p00001', None, None)
    # REQ-p00001#A      -> ('REQ-p00001', 'assertion', 'A')
    # REQ-p00001#section:Rationale -> ('REQ-p00001', 'section', 'Rationale')
    # REQ-p00001#edge:REQ-d00003   -> ('REQ-p00001', 'edge', 'REQ-d00003')
    # JNY-001           -> ('JNY-001', None, None)
    # JNY-001#section:Setup        -> ('JNY-001', 'section', 'Setup')
    # JNY-001#edge:REQ-p00001      -> ('JNY-001', 'edge', 'REQ-p00001')
```

Assertion fragment detection: if the fragment after `#` has no `:` prefix, it's an assertion label.

### Anchor Validation

```python
def validate_anchor(anchor: str, graph: TraceGraph) -> bool:
```

Uses existing graph API: `find_by_id()`, `iter_children(edge_kinds={STRUCTURES})`, `iter_outgoing_edges()`, `get_field('sections')`.

### Rename Hook

```python
def update_anchors_on_rename(
    index: CommentIndex,
    old_id: str,
    new_id: str,
    repo_root: Path,
) -> list[CommentEvent]:
```

Called from `TraceGraph.rename_node()` and `TraceGraph.rename_assertion()` in `builder.py` after the rename succeeds (~2 lines added per method). Note: the `mutate_rename_*` names exist only as MCP tool wrappers in `mcp/server.py`. Appends promote events with `reason="Renamed from X to Y"`.

---

## 4. TraceGraph & FederatedGraph Integration

### TraceGraph

New annotation field and read-only delegates in `graph/builder.py`. This is a deliberate, minimal extension — `_comment_index` is a parallel annotation layer (like `_terms`), not a structural change to the graph topology. It follows existing conventions: prefixed private field, iterator-only query API, no graph-building logic.

```python
_comment_index: CommentIndex = field(default_factory=CommentIndex, init=False)

def iter_comments(self, anchor: str) -> Iterator[CommentThread]: ...
def comment_count(self, anchor: str) -> int: ...
def has_comments(self, anchor: str) -> bool: ...
def iter_orphaned_comments(self) -> Iterator[CommentThread]: ...
```

Pure delegation to `_comment_index`. No logic in these methods.

### FederatedGraph

Routes via `_ownership` map (same pattern as mutations and terms):

```python
def iter_comments(self, anchor: str) -> Iterator[CommentThread]:
    node_id = parse_anchor(anchor)[0]
    repo_name = self._ownership.get(node_id)
    # delegate to owning repo's TraceGraph

def comment_count(self, anchor: str) -> int: ...
def has_comments(self, anchor: str) -> bool: ...

def iter_orphaned_comments(self) -> Iterator[CommentThread]:
    # Aggregate across all repos for display convenience
    # Orphans remain stored in their original repo's _orphaned.json
```

### Loading

Per-repo, after graph build:

```python
comment_index = load_comment_index(entry.repo_root)
promote_orphaned_comments(comment_index, entry.graph, entry.repo_root)
entry.graph._comment_index = comment_index
```

Comments are loaded at graph build time when running the viewer (startup and `refresh_graph()`), but skipped entirely for CLI validation commands. The distinction is viewer vs. CLI, not lazy vs. eager.

### Write Routing

API layer resolves owning repo via `_ownership`, then appends to that repo's `.elspais/comments/` directory.

---

## 5. API Endpoints

Added to `server/routes_api.py`. Follow existing handler pattern: async handlers, `request.app.state.app_state`, JSON responses.

### Write Endpoints

| Endpoint | Method | Payload | Effect |
|---|---|---|---|
| `/api/comment/add` | POST | `{anchor, text}` | Append `comment` event |
| `/api/comment/reply` | POST | `{parent_id, text}` | Append `reply` event |
| `/api/comment/resolve` | POST | `{comment_id}` | Append `resolve` event |

- Author resolved server-side via `get_author_info()` using `[changelog].id_source` config
- Returns created event so UI can update without re-fetch
- Invalid anchor: 404. Missing text: 400.

### Read Endpoints

| Endpoint | Method | Params | Returns |
|---|---|---|---|
| `/api/comments` | GET | `?anchor=REQ-p00001#A` | Thread(s) for anchor |
| `/api/comments/card` | GET | `?node_id=REQ-p00001` | All threads grouped by anchor |
| `/api/comments/orphaned` | GET | — | Orphaned threads across all repos |

`/api/comments/card` groups threads by anchor — the UI needs to place each thread under its target element.

No pagination — comment volumes per card expected to be small. Compaction keeps files manageable.

---

## 6. Viewer UI

### Margin Column

Narrow gutter on the right edge of every card, always visible.

- Each commentable element gets a corresponding margin cell
- Speech bubble icon + count badge when `comment_count > 0`
- Click toggles inline thread open/closed
- Data fetched via `/api/comments/card?node_id=...` when card opens (single request)

### Inline Threads

Expand below target element, pushing content down (not overlay).

- Flat list, chronological (newest at bottom)
- Author format: `Name (email) . YYYY-MM-DD`
- `[Resolve]` button per comment — visible only in Edit Mode
- `[Reply...]` textarea at bottom — visible only in Edit Mode
- Outside Edit Mode: read-only expand/collapse
- Resolved threads disappear entirely (in git history only)

### Comment Mode

One-shot, entered via `C` key or toolbar button (Edit Mode required).

- Toast: "Click any element to add a comment. Press Esc to cancel."
- Cursor: speech bubble on valid targets, blue highlight on hover
- Valid targets identified by `data-anchor` attribute on DOM elements
- Submit: POST, insert thread in DOM, update margin, exit mode
- Esc or toolbar button: cancel and exit

### data-anchor Attributes

Every commentable element gets `data-anchor="..."` during card rendering:

- Card header: `data-anchor="REQ-p00001"` or `data-anchor="JNY-001"`
- Assertion row: `data-anchor="REQ-p00001#A"`
- Body section (existing elements): `data-anchor="REQ-p00001#section:Rationale"` or `data-anchor="JNY-001#section:Setup"`
- Edge row: `data-anchor="REQ-p00001#edge:REQ-d00003"` or `data-anchor="JNY-001#edge:REQ-p00001"`

### Lost Comments Card

Rendered at top of card column when orphaned comments exist.

- Fetched via `/api/comments/orphaned` on page load / graph refresh
- Shows `"Originally on {old_anchor} (deleted)"` context per thread
- `[Resolve]` available in Edit Mode

### Existing Infrastructure Leveraged

- Body `##` sections: already rendered in Complete view — just need `data-anchor` attributes
- Compact/Complete toggle: already implemented — no changes needed

---

## 7. Compaction CLI

```bash
elspais comments compact
```

Rewrites comment files:
- Strips resolved threads entirely
- Collapses promote chains (keeps only final anchor)
- Outputs clean JSONL

Manual operation only, never automatic.

---

## Non-Goals (Explicit)

- No `elspais checks` integration (future)
- No WebSocket/SSE — single-user review workflow
- No cross-repo comment migration
- No "show resolved" toggle — resolved comments are in git history only
- Thread expand/collapse state is ephemeral (not persisted)

---

## New Files

| File | Purpose |
|---|---|
| `src/elspais/graph/comments.py` | CommentEvent, CommentThread, CommentIndex |
| `src/elspais/graph/comment_store.py` | JSONL I/O, thread assembly, promotion, compaction |

## Modified Files

| File | Change |
|---|---|
| `src/elspais/graph/builder.py` | Add `_comment_index` field, 4 delegate methods; ~2 lines in `rename_node()` and `rename_assertion()` to call comment anchor rename hook |
| `src/elspais/graph/federated.py` | Add comment routing + orphan aggregation methods |
| `src/elspais/server/app.py` | Register 6 new routes |
| `src/elspais/server/routes_api.py` | 6 endpoint handlers |
| `html/templates/partials/js/_card-stack.js.j2` | `data-anchor` attrs, margin column, inline threads |
| `html/templates/partials/js/_edit-engine.js.j2` | Comment mode toggle, one-shot flow |
| `html/templates/partials/css/` | Comment thread styles, margin column styles |

## Dependencies

No new dependencies. Uses stdlib `json`, `pathlib`, `datetime`. Hash computation delegates to `utilities/hasher.py`.

## Git Tracking

`.elspais/comments/` must be committed to git (not in `.gitignore`). Comments are auditable artifacts — the design doc states they are "persisted through git, providing an auditable record of review activity alongside specification changes."
