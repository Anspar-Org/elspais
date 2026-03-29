# Comment / Review System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a comment/review system to the viewer that lets reviewers annotate requirements, assertions, body sections, and edges with threaded comments persisted as JSONL files in `.elspais/comments/`.

**Architecture:** Bottom-up — data models, JSONL I/O, promotion engine, graph integration, API endpoints, viewer UI. Comments are a parallel annotation layer on TraceGraph (like TermDictionary), stored outside the spec files, committed to git for auditability.

**Tech Stack:** Python stdlib (`json`, `pathlib`, `datetime`), existing `utilities/hasher.py` for hash computation, Starlette for API, Jinja2 templates for viewer.

**Spec:** `docs/superpowers/specs/2026-03-24-comment-review-system-design.md`
**Design:** `docs/design_comments.md`

---

## Prerequisites and Conventions

### Requirement Traceability

Before implementing, create requirements for the comment system using `mutate_add_requirement` via the elspais MCP. All test names **MUST** reference a specific assertion (e.g., `test_REQ_xxx_A_description`). The test names in this plan use descriptive names as placeholders — the implementer must map each test to the appropriate assertion ID before writing the test. See `AGENT_DESIGN_PRINCIPLES.md` for the naming convention.

### create_app Signature

The `create_app` function in `server/app.py` takes an `AppState` instance, not separate graph/root/config args. Test fixtures must construct `AppState` first:

```python
from elspais.server.state import AppState
state = AppState(graph=federated, repo_root=tmp_path, config={})
app = create_app(state)
```

### Encapsulation Rules

API endpoint handlers must NOT access internal fields (`_comment_index`, `_repos`, `_ownership`) directly. Instead:
- Use public query methods on FederatedGraph (`iter_comments`, `comment_count`, `has_comments`)
- Add a `repo_root_for(node_id) -> Path | None` public method to FederatedGraph for write routing
- Add public mutation methods to CommentIndex (`remove_anchor()`, `move_thread()`) for the promotion engine rather than accessing `_threads` directly
- The promotion engine in `comment_store.py` is an internal collaborator of CommentIndex — if it must access internals, keep it tightly coupled and document the relationship

### Line Numbers Are Approximate

Line references like "~line 67" are guidance, not exact. Always search for the method/field name rather than navigating by line number. Key methods to find by name:
- `_terms:` field in TraceGraph (insertion point for `_comment_index`)
- `def rename_node(self` in TraceGraph
- `def rename_assertion(self` in TraceGraph
- `def _merge_terms(self` in FederatedGraph (pattern for `_merge_comments`)

### Version Bumps

Bump patch version in `pyproject.toml` with every commit per project convention.

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `src/elspais/graph/comments.py` | Data models: `CommentEvent`, `CommentThread`, `CommentIndex` |
| `src/elspais/graph/comment_store.py` | JSONL I/O: read, append, assemble threads, promotion, compaction, ID generation |
| `tests/graph/test_comments.py` | Tests for data models |
| `tests/graph/test_comment_store.py` | Tests for JSONL I/O, thread assembly, promotion |
| `tests/graph/test_comment_integration.py` | Tests for TraceGraph/FederatedGraph integration |
| `tests/server/test_comment_api.py` | Tests for API endpoints |

### Modified Files

| File | Change |
|------|--------|
| `src/elspais/graph/builder.py` | Add `_comment_index` field (~line 67), 4 delegate methods, rename hooks in `rename_node()` (~line 920) and `rename_assertion()` (~line 1227) |
| `src/elspais/graph/federated.py` | Add comment routing methods, `_merge_comments()` in `__init__` (~line 173) |
| `src/elspais/server/app.py` | Register 6 comment routes (~lines 135-183) |
| `src/elspais/server/routes_api.py` | 6 endpoint handlers |
| `src/elspais/html/templates/partials/js/_card-stack.js.j2` | `data-anchor` attributes, margin column, inline thread rendering |
| `src/elspais/html/templates/partials/js/_edit-engine.js.j2` | Comment mode toggle (`C` key), one-shot flow |
| `pyproject.toml` | Version bump per commit |

---

## Task 1: CommentEvent and CommentThread Data Models

**Files:**
- Create: `src/elspais/graph/comments.py`
- Create: `tests/graph/test_comments.py`

- [ ] **Step 1: Write failing tests for CommentEvent**

```python
# tests/graph/test_comments.py
"""Tests for comment data models."""

from elspais.graph.comments import CommentEvent, CommentThread, CommentIndex


class TestCommentEvent:
    """Tests for CommentEvent frozen dataclass."""

    def test_create_comment_event(self):
        """A comment event stores all required fields."""
        evt = CommentEvent(
            event="comment",
            id="c-20260320-a3f1b2",
            anchor="REQ-p00001#A",
            author="Alice Smith",
            author_id="alice@co.org",
            date="2026-03-20",
            text="Should we support SAML?",
        )
        assert evt.event == "comment"
        assert evt.id == "c-20260320-a3f1b2"
        assert evt.anchor == "REQ-p00001#A"
        assert evt.text == "Should we support SAML?"

    def test_comment_event_is_frozen(self):
        """CommentEvent is immutable."""
        evt = CommentEvent(
            event="comment", id="c-20260320-a3f1b2",
            anchor="REQ-p00001", author="Alice", author_id="alice@co.org",
            date="2026-03-20", text="Hello",
        )
        import pytest
        with pytest.raises(AttributeError):
            evt.text = "Modified"

    def test_reply_event_fields(self):
        """Reply events have parent field."""
        evt = CommentEvent(
            event="reply", id="c-20260321-b4e2c3",
            anchor="REQ-p00001#A", author="Bob", author_id="bob@co.org",
            date="2026-03-21", text="Out of scope.",
            parent="c-20260320-a3f1b2",
        )
        assert evt.parent == "c-20260320-a3f1b2"

    def test_resolve_event_fields(self):
        """Resolve events have target and anchor, no text."""
        evt = CommentEvent(
            event="resolve", id="c-20260321-d6f4a5",
            anchor="REQ-p00001#A", author="Bob", author_id="bob@co.org",
            date="2026-03-21", target="c-20260320-a3f1b2",
        )
        assert evt.target == "c-20260320-a3f1b2"
        assert evt.text == ""

    def test_promote_event_fields(self):
        """Promote events have old/new anchor and reason."""
        evt = CommentEvent(
            event="promote", id="c-20260322-e7g5b6",
            anchor="REQ-p00001", author="system", author_id="system",
            date="2026-03-22", target="c-20260320-a3f1b2",
            old_anchor="REQ-p00001#D", new_anchor="REQ-p00001",
            reason="Assertion D deleted",
            from_file="spec/prd-auth.md.json",
        )
        assert evt.old_anchor == "REQ-p00001#D"
        assert evt.new_anchor == "REQ-p00001"

    def test_default_optional_fields(self):
        """Optional fields default to empty string."""
        evt = CommentEvent(
            event="comment", id="c-20260320-a3f1b2",
            anchor="REQ-p00001", author="Alice", author_id="alice@co.org",
            date="2026-03-20", text="Hello",
        )
        assert evt.parent == ""
        assert evt.target == ""
        assert evt.old_anchor == ""
        assert evt.new_anchor == ""
        assert evt.reason == ""
        assert evt.from_file == ""
```

- [ ] **Step 2: Run tests — expect ImportError**

Run: `pytest tests/graph/test_comments.py -v`
Expected: `ModuleNotFoundError: No module named 'elspais.graph.comments'`

- [ ] **Step 3: Write CommentEvent and CommentThread**

```python
# src/elspais/graph/comments.py
"""Comment data models for the review system.

Comments are a parallel annotation layer on the graph, stored as
append-only JSONL files in .elspais/comments/. Models are frozen
(immutable) to match the append-only storage semantics.
"""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CommentEvent:
    """A single event in a comment's lifecycle.

    All event types share the same structure. Fields unused by a given
    event type default to empty string.
    """

    event: str  # "comment" | "reply" | "resolve" | "promote"
    id: str  # c-YYYYMMDD-6hexchars
    anchor: str  # e.g. "REQ-p00001#A"
    author: str  # display name
    author_id: str  # email
    date: str  # YYYY-MM-DD
    text: str = ""  # empty for resolve/promote
    parent: str = ""  # reply only: parent comment id
    target: str = ""  # resolve/promote: target comment id
    old_anchor: str = ""  # promote only
    new_anchor: str = ""  # promote only
    reason: str = ""  # promote only
    from_file: str = ""  # promote only: source JSONL file


@dataclass
class CommentThread:
    """An assembled comment thread: root comment plus flat replies.

    The anchor may differ from root.anchor if the thread was promoted.
    """

    root: CommentEvent
    replies: list[CommentEvent] = field(default_factory=list)
    anchor: str = ""  # current anchor (may differ from root if promoted)
    resolved: bool = False
    promoted_from: str | None = None  # original anchor if promoted
    promotion_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.anchor:
            self.anchor = self.root.anchor
```

- [ ] **Step 4: Run tests — expect pass for CommentEvent tests**

Run: `pytest tests/graph/test_comments.py::TestCommentEvent -v`
Expected: all PASS

- [ ] **Step 5: Write failing tests for CommentThread**

Add to `tests/graph/test_comments.py`:

```python
class TestCommentThread:
    """Tests for CommentThread assembly."""

    def test_thread_defaults_anchor_from_root(self):
        """Thread anchor defaults to root event's anchor."""
        root = CommentEvent(
            event="comment", id="c-20260320-a3f1b2",
            anchor="REQ-p00001#A", author="Alice", author_id="alice@co.org",
            date="2026-03-20", text="Hello",
        )
        thread = CommentThread(root=root)
        assert thread.anchor == "REQ-p00001#A"
        assert thread.resolved is False
        assert thread.promoted_from is None
        assert thread.replies == []

    def test_thread_with_replies(self):
        """Thread holds flat chronological replies."""
        root = CommentEvent(
            event="comment", id="c-20260320-a3f1b2",
            anchor="REQ-p00001#A", author="Alice", author_id="alice@co.org",
            date="2026-03-20", text="Question",
        )
        reply = CommentEvent(
            event="reply", id="c-20260321-b4e2c3",
            anchor="REQ-p00001#A", author="Bob", author_id="bob@co.org",
            date="2026-03-21", text="Answer", parent="c-20260320-a3f1b2",
        )
        thread = CommentThread(root=root, replies=[reply])
        assert len(thread.replies) == 1
        assert thread.replies[0].author == "Bob"

    def test_promoted_thread(self):
        """Thread tracks promotion metadata."""
        root = CommentEvent(
            event="comment", id="c-20260320-a3f1b2",
            anchor="REQ-p00001#D", author="Alice", author_id="alice@co.org",
            date="2026-03-20", text="Too tight for prod",
        )
        thread = CommentThread(
            root=root, anchor="REQ-p00001",
            promoted_from="REQ-p00001#D",
            promotion_reason="Assertion D deleted",
        )
        assert thread.anchor == "REQ-p00001"
        assert thread.promoted_from == "REQ-p00001#D"
```

- [ ] **Step 6: Run tests — expect pass**

Run: `pytest tests/graph/test_comments.py -v`
Expected: all PASS

- [ ] **Step 7: Bump version in pyproject.toml and commit**

```bash
# bump version 0.112.10 -> 0.112.11
git add src/elspais/graph/comments.py tests/graph/test_comments.py pyproject.toml
git commit -m "[CUR-1081] Add CommentEvent and CommentThread data models"
```

---

## Task 2: CommentIndex

**Files:**
- Modify: `src/elspais/graph/comments.py`
- Modify: `tests/graph/test_comments.py`

- [ ] **Step 1: Write failing tests for CommentIndex**

Add to `tests/graph/test_comments.py`:

```python
class TestCommentIndex:
    """Tests for CommentIndex in-memory index."""

    def _make_thread(self, anchor, comment_id="c-20260320-a3f1b2"):
        root = CommentEvent(
            event="comment", id=comment_id, anchor=anchor,
            author="Alice", author_id="alice@co.org",
            date="2026-03-20", text="A comment",
        )
        return CommentThread(root=root)

    def test_empty_index(self):
        idx = CommentIndex()
        assert idx.thread_count("REQ-p00001") == 0
        assert not idx.has_threads("REQ-p00001")
        assert list(idx.iter_threads("REQ-p00001")) == []

    def test_add_and_retrieve_thread(self):
        idx = CommentIndex()
        thread = self._make_thread("REQ-p00001#A")
        idx.add_thread(thread, source_file="spec/prd.md.json")
        assert idx.thread_count("REQ-p00001#A") == 1
        assert idx.has_threads("REQ-p00001#A")
        assert list(idx.iter_threads("REQ-p00001#A"))[0].root.text == "A comment"

    def test_iter_all_anchors_for_node(self):
        idx = CommentIndex()
        idx.add_thread(self._make_thread("REQ-p00001", "c1"), "f.json")
        idx.add_thread(self._make_thread("REQ-p00001#A", "c2"), "f.json")
        idx.add_thread(self._make_thread("REQ-p00001#section:Rationale", "c3"), "f.json")
        idx.add_thread(self._make_thread("REQ-p00002#A", "c4"), "f.json")
        anchors = sorted(idx.iter_all_anchors_for_node("REQ-p00001"))
        assert anchors == ["REQ-p00001", "REQ-p00001#A", "REQ-p00001#section:Rationale"]

    def test_orphaned_threads(self):
        idx = CommentIndex()
        thread = self._make_thread("REQ-deleted#A")
        idx.add_orphaned(thread)
        assert list(idx.iter_orphaned()) == [thread]

    def test_source_file_tracking(self):
        idx = CommentIndex()
        thread = self._make_thread("REQ-p00001#A")
        idx.add_thread(thread, source_file="spec/prd.md.json")
        assert idx.source_file_for("REQ-p00001#A") == "spec/prd.md.json"

    def test_merge_indexes(self):
        idx1 = CommentIndex()
        idx1.add_thread(self._make_thread("REQ-p00001#A", "c1"), "f1.json")
        idx2 = CommentIndex()
        idx2.add_thread(self._make_thread("REQ-d00001#B", "c2"), "f2.json")
        idx1.merge(idx2)
        assert idx1.has_threads("REQ-p00001#A")
        assert idx1.has_threads("REQ-d00001#B")
```

- [ ] **Step 2: Run tests — expect AttributeError (CommentIndex not implemented)**

Run: `pytest tests/graph/test_comments.py::TestCommentIndex -v`
Expected: FAIL

- [ ] **Step 3: Implement CommentIndex**

Add to `src/elspais/graph/comments.py`:

```python
class CommentIndex:
    """In-memory index of active comment threads, keyed by anchor.

    Follows the same pattern as TermDictionary — a simple dict-based
    index with iterator-only query API.
    """

    def __init__(self) -> None:
        self._threads: dict[str, list[CommentThread]] = {}
        self._orphaned: list[CommentThread] = []
        self._file_map: dict[str, str] = {}  # anchor -> source JSONL relative path

    def add_thread(self, thread: CommentThread, source_file: str) -> None:
        """Add a thread to the index."""
        anchor = thread.anchor
        if anchor not in self._threads:
            self._threads[anchor] = []
        self._threads[anchor].append(thread)
        if anchor not in self._file_map:
            self._file_map[anchor] = source_file

    def add_orphaned(self, thread: CommentThread) -> None:
        """Add an orphaned thread (no valid graph target)."""
        self._orphaned.append(thread)

    def iter_threads(self, anchor: str) -> Iterator[CommentThread]:
        """Yield threads for an anchor."""
        yield from self._threads.get(anchor, [])

    def thread_count(self, anchor: str) -> int:
        """Count threads for an anchor."""
        return len(self._threads.get(anchor, []))

    def has_threads(self, anchor: str) -> bool:
        """Check if any threads exist for an anchor."""
        return anchor in self._threads and len(self._threads[anchor]) > 0

    def iter_orphaned(self) -> Iterator[CommentThread]:
        """Yield orphaned threads."""
        yield from self._orphaned

    def iter_all_anchors_for_node(self, node_id: str) -> Iterator[str]:
        """Yield all anchors that start with node_id.

        Matches exact node_id and node_id#fragment patterns.
        Used by /api/comments/card to get all comments for a card.
        """
        prefix = node_id + "#"
        for anchor in self._threads:
            if anchor == node_id or anchor.startswith(prefix):
                yield anchor

    def source_file_for(self, anchor: str) -> str | None:
        """Return the JSONL source file path for an anchor."""
        return self._file_map.get(anchor)

    def merge(self, other: CommentIndex) -> None:
        """Merge another index into this one."""
        for anchor, threads in other._threads.items():
            if anchor not in self._threads:
                self._threads[anchor] = []
            self._threads[anchor].extend(threads)
        self._orphaned.extend(other._orphaned)
        for anchor, path in other._file_map.items():
            if anchor not in self._file_map:
                self._file_map[anchor] = path

    def __len__(self) -> int:
        return sum(len(ts) for ts in self._threads.values())
```

- [ ] **Step 4: Run tests — expect all pass**

Run: `pytest tests/graph/test_comments.py -v`
Expected: all PASS

- [ ] **Step 5: Bump version and commit**

```bash
git add src/elspais/graph/comments.py tests/graph/test_comments.py pyproject.toml
git commit -m "[CUR-1081] Add CommentIndex in-memory index"
```

---

## Task 3: JSONL I/O and Thread Assembly

**Files:**
- Create: `src/elspais/graph/comment_store.py`
- Create: `tests/graph/test_comment_store.py`

- [ ] **Step 1: Write failing tests for anchor parsing and ID generation**

```python
# tests/graph/test_comment_store.py
"""Tests for comment JSONL I/O and thread assembly."""

import json
from pathlib import Path

from elspais.graph.comment_store import (
    parse_anchor,
    generate_comment_id,
    comment_file_for,
)


class TestParseAnchor:
    """Tests for anchor string parsing."""

    def test_bare_requirement(self):
        assert parse_anchor("REQ-p00001") == ("REQ-p00001", None, None)

    def test_assertion_fragment(self):
        assert parse_anchor("REQ-p00001#A") == ("REQ-p00001", "assertion", "A")

    def test_section_fragment(self):
        assert parse_anchor("REQ-p00001#section:Rationale") == (
            "REQ-p00001", "section", "Rationale",
        )

    def test_edge_fragment(self):
        assert parse_anchor("REQ-p00001#edge:REQ-d00003") == (
            "REQ-p00001", "edge", "REQ-d00003",
        )

    def test_journey_bare(self):
        assert parse_anchor("JNY-001") == ("JNY-001", None, None)

    def test_journey_section(self):
        assert parse_anchor("JNY-001#section:Setup") == (
            "JNY-001", "section", "Setup",
        )

    def test_journey_edge(self):
        assert parse_anchor("JNY-001#edge:REQ-p00001") == (
            "JNY-001", "edge", "REQ-p00001",
        )


class TestGenerateCommentId:
    """Tests for comment ID generation."""

    def test_format(self):
        cid = generate_comment_id("REQ-p00001#A", "alice@co.org", "2026-03-20", "Hello")
        assert cid.startswith("c-20260320-")
        assert len(cid) == len("c-20260320-") + 6

    def test_deterministic(self):
        a = generate_comment_id("REQ-p00001#A", "alice@co.org", "2026-03-20", "Hello")
        b = generate_comment_id("REQ-p00001#A", "alice@co.org", "2026-03-20", "Hello")
        assert a == b

    def test_different_content_different_id(self):
        a = generate_comment_id("REQ-p00001#A", "alice@co.org", "2026-03-20", "Hello")
        b = generate_comment_id("REQ-p00001#A", "alice@co.org", "2026-03-20", "World")
        assert a != b


class TestCommentFileFor:
    """Tests for JSONL file path resolution."""

    def test_spec_file(self):
        result = comment_file_for(Path("/repo"), "spec/prd-auth.md")
        assert result == Path("/repo/.elspais/comments/spec/prd-auth.md.json")

    def test_journey_file(self):
        result = comment_file_for(Path("/repo"), "journeys/onboarding.md")
        assert result == Path("/repo/.elspais/comments/journeys/onboarding.md.json")
```

- [ ] **Step 2: Run tests — expect ImportError**

Run: `pytest tests/graph/test_comment_store.py::TestParseAnchor -v`
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement parse_anchor, generate_comment_id, comment_file_for**

```python
# src/elspais/graph/comment_store.py
"""Comment JSONL I/O, thread assembly, promotion, and compaction.

Handles reading/writing JSONL comment files in .elspais/comments/.
All file I/O is isolated here — comments.py contains only data models.
"""
from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

from elspais.graph.comments import CommentEvent, CommentIndex, CommentThread
from elspais.utilities.hasher import calculate_hash

if TYPE_CHECKING:
    from elspais.graph.builder import TraceGraph

ORPHANED_FILE = "_orphaned.json"


def comment_file_for(repo_root: Path, spec_relative_path: str) -> Path:
    """Map a spec file's relative path to its comment JSONL file.

    Example: spec/prd-auth.md -> {repo_root}/.elspais/comments/spec/prd-auth.md.json
    """
    return repo_root / ".elspais" / "comments" / f"{spec_relative_path}.json"


def parse_anchor(anchor: str) -> tuple[str, str | None, str | None]:
    """Parse an anchor string into (node_id, fragment_type, fragment_value).

    Fragment types:
    - None: bare node (e.g. REQ-p00001)
    - "assertion": assertion label (e.g. REQ-p00001#A)
    - "section": body section (e.g. REQ-p00001#section:Rationale)
    - "edge": edge target (e.g. REQ-p00001#edge:REQ-d00003)
    """
    if "#" not in anchor:
        return (anchor, None, None)
    node_id, fragment = anchor.split("#", 1)
    if fragment.startswith("section:"):
        return (node_id, "section", fragment[len("section:"):])
    if fragment.startswith("edge:"):
        return (node_id, "edge", fragment[len("edge:"):])
    # No prefix -> assertion label
    return (node_id, "assertion", fragment)


def generate_comment_id(anchor: str, author_id: str, date: str, text: str) -> str:
    """Generate a deterministic comment ID.

    Format: c-{YYYYMMDD}-{hash[:6]}
    Hash is computed via utilities/hasher.py per project convention.
    """
    content = anchor + author_id + date + text
    short_hash = calculate_hash(content, length=6)
    date_compact = date.replace("-", "")
    return f"c-{date_compact}-{short_hash}"
```

- [ ] **Step 4: Run tests — expect pass**

Run: `pytest tests/graph/test_comment_store.py -v`
Expected: all PASS

- [ ] **Step 5: Write failing tests for JSONL read/write and thread assembly**

Add to `tests/graph/test_comment_store.py`:

```python
from elspais.graph.comment_store import (
    load_events,
    append_event,
    assemble_threads,
    load_comment_index,
)
from elspais.graph.comments import CommentEvent, CommentThread


class TestJsonlIO:
    """Tests for JSONL file reading and writing."""

    def test_load_missing_file(self, tmp_path):
        """Loading a non-existent file returns empty list."""
        assert load_events(tmp_path / "nope.json") == []

    def test_append_and_load(self, tmp_path):
        """Append events then load them back."""
        path = tmp_path / "comments" / "spec.md.json"
        evt = CommentEvent(
            event="comment", id="c-20260320-a3f1b2",
            anchor="REQ-p00001#A", author="Alice", author_id="alice@co.org",
            date="2026-03-20", text="Hello",
        )
        append_event(path, evt)
        events = load_events(path)
        assert len(events) == 1
        assert events[0].id == "c-20260320-a3f1b2"
        assert events[0].text == "Hello"

    def test_append_creates_parent_dirs(self, tmp_path):
        """append_event creates directories if needed."""
        path = tmp_path / "deep" / "nested" / "file.json"
        evt = CommentEvent(
            event="comment", id="c1", anchor="REQ-p00001",
            author="A", author_id="a@x", date="2026-03-20", text="Hi",
        )
        append_event(path, evt)
        assert path.exists()

    def test_multiple_appends(self, tmp_path):
        """Multiple appends produce multiple lines."""
        path = tmp_path / "test.json"
        for i in range(3):
            evt = CommentEvent(
                event="comment", id=f"c{i}", anchor="REQ-p00001",
                author="A", author_id="a@x", date="2026-03-20", text=f"msg{i}",
            )
            append_event(path, evt)
        events = load_events(path)
        assert len(events) == 3


class TestAssembleThreads:
    """Tests for building CommentThread objects from raw events."""

    def test_single_comment(self):
        """One comment event produces one thread."""
        events = [
            CommentEvent(
                event="comment", id="c1", anchor="REQ-p00001#A",
                author="Alice", author_id="alice@co.org",
                date="2026-03-20", text="Question",
            ),
        ]
        threads = assemble_threads(events)
        assert len(threads) == 1
        assert threads[0].root.id == "c1"
        assert threads[0].resolved is False

    def test_comment_with_reply(self):
        """Reply attaches to parent thread."""
        events = [
            CommentEvent(
                event="comment", id="c1", anchor="REQ-p00001#A",
                author="Alice", author_id="alice@co.org",
                date="2026-03-20", text="Question",
            ),
            CommentEvent(
                event="reply", id="c2", anchor="REQ-p00001#A",
                author="Bob", author_id="bob@co.org",
                date="2026-03-21", text="Answer", parent="c1",
            ),
        ]
        threads = assemble_threads(events)
        assert len(threads) == 1
        assert len(threads[0].replies) == 1
        assert threads[0].replies[0].text == "Answer"

    def test_resolved_thread_excluded(self):
        """Resolved threads are filtered out."""
        events = [
            CommentEvent(
                event="comment", id="c1", anchor="REQ-p00001#A",
                author="Alice", author_id="alice@co.org",
                date="2026-03-20", text="Question",
            ),
            CommentEvent(
                event="resolve", id="r1", anchor="REQ-p00001#A",
                author="Bob", author_id="bob@co.org",
                date="2026-03-21", target="c1",
            ),
        ]
        threads = assemble_threads(events)
        assert len(threads) == 0

    def test_promoted_thread(self):
        """Promote event updates thread anchor and metadata."""
        events = [
            CommentEvent(
                event="comment", id="c1", anchor="REQ-p00001#D",
                author="Alice", author_id="alice@co.org",
                date="2026-03-20", text="Too tight",
            ),
            CommentEvent(
                event="promote", id="p1", anchor="REQ-p00001",
                author="system", author_id="system",
                date="2026-03-22", target="c1",
                old_anchor="REQ-p00001#D", new_anchor="REQ-p00001",
                reason="Assertion D deleted",
            ),
        ]
        threads = assemble_threads(events)
        assert len(threads) == 1
        assert threads[0].anchor == "REQ-p00001"
        assert threads[0].promoted_from == "REQ-p00001#D"
        assert threads[0].promotion_reason == "Assertion D deleted"

    def test_multiple_threads_same_anchor(self):
        """Multiple top-level comments on same anchor produce separate threads."""
        events = [
            CommentEvent(
                event="comment", id="c1", anchor="REQ-p00001#A",
                author="Alice", author_id="alice@co.org",
                date="2026-03-20", text="First",
            ),
            CommentEvent(
                event="comment", id="c2", anchor="REQ-p00001#A",
                author="Bob", author_id="bob@co.org",
                date="2026-03-21", text="Second",
            ),
        ]
        threads = assemble_threads(events)
        assert len(threads) == 2
```

- [ ] **Step 6: Run tests — expect ImportError for new functions**

Run: `pytest tests/graph/test_comment_store.py -v`
Expected: FAIL

- [ ] **Step 7: Implement load_events, append_event, assemble_threads**

Add to `src/elspais/graph/comment_store.py`:

```python
def _event_to_dict(event: CommentEvent) -> dict:
    """Serialize a CommentEvent to a dict, omitting empty optional fields."""
    d: dict = {
        "event": event.event,
        "id": event.id,
        "anchor": event.anchor,
        "author": event.author,
        "author_id": event.author_id,
        "date": event.date,
    }
    if event.text:
        d["text"] = event.text
    if event.parent:
        d["parent"] = event.parent
    if event.target:
        d["target"] = event.target
    if event.old_anchor:
        d["old_anchor"] = event.old_anchor
    if event.new_anchor:
        d["new_anchor"] = event.new_anchor
    if event.reason:
        d["reason"] = event.reason
    if event.from_file:
        d["from_file"] = event.from_file
    return d


def _dict_to_event(d: dict) -> CommentEvent:
    """Deserialize a dict to a CommentEvent."""
    return CommentEvent(
        event=d["event"],
        id=d["id"],
        anchor=d.get("anchor", ""),
        author=d.get("author", ""),
        author_id=d.get("author_id", ""),
        date=d.get("date", ""),
        text=d.get("text", ""),
        parent=d.get("parent", ""),
        target=d.get("target", ""),
        old_anchor=d.get("old_anchor", ""),
        new_anchor=d.get("new_anchor", ""),
        reason=d.get("reason", ""),
        from_file=d.get("from_file", ""),
    )


def load_events(path: Path) -> list[CommentEvent]:
    """Read all events from a JSONL file. Returns empty list if file missing."""
    if not path.exists():
        return []
    events = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(_dict_to_event(json.loads(line)))
    return events


def append_event(path: Path, event: CommentEvent) -> None:
    """Append a single event line to a JSONL file. Creates parent dirs if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(_event_to_dict(event), separators=(",", ":")) + "\n")


def assemble_threads(events: list[CommentEvent]) -> list[CommentThread]:
    """Build CommentThread objects from raw events.

    1. Collect top-level comments (event="comment")
    2. Attach replies by parent field
    3. Apply resolve events (mark resolved)
    4. Apply promote events (update anchor, record metadata)
    5. Filter out resolved threads
    """
    threads_by_id: dict[str, CommentThread] = {}
    resolved_ids: set[str] = set()

    # Pass 1: build threads from comment events
    for evt in events:
        if evt.event == "comment":
            threads_by_id[evt.id] = CommentThread(root=evt)

    # Pass 2: attach replies
    for evt in events:
        if evt.event == "reply" and evt.parent in threads_by_id:
            threads_by_id[evt.parent].replies.append(evt)

    # Pass 3: apply resolves
    for evt in events:
        if evt.event == "resolve" and evt.target in threads_by_id:
            resolved_ids.add(evt.target)

    # Pass 4: apply promotions
    for evt in events:
        if evt.event == "promote" and evt.target in threads_by_id:
            thread = threads_by_id[evt.target]
            thread.promoted_from = evt.old_anchor
            thread.promotion_reason = evt.reason
            thread.anchor = evt.new_anchor

    # Pass 5: filter resolved, return active threads
    return [t for t in threads_by_id.values() if t.root.id not in resolved_ids]
```

- [ ] **Step 8: Run tests — expect all pass**

Run: `pytest tests/graph/test_comment_store.py -v`
Expected: all PASS

- [ ] **Step 9: Write failing test for load_comment_index**

Add to `tests/graph/test_comment_store.py`:

```python
class TestLoadCommentIndex:
    """Tests for loading a full CommentIndex from disk."""

    def test_empty_repo(self, tmp_path):
        """No .elspais/comments dir returns empty index."""
        idx = load_comment_index(tmp_path)
        assert len(idx) == 0

    def test_loads_from_multiple_files(self, tmp_path):
        """Index aggregates threads from all JSONL files."""
        comments_dir = tmp_path / ".elspais" / "comments"
        f1 = comments_dir / "spec" / "prd.md.json"
        f2 = comments_dir / "spec" / "dev.md.json"
        evt1 = CommentEvent(
            event="comment", id="c1", anchor="REQ-p00001#A",
            author="Alice", author_id="alice@co.org",
            date="2026-03-20", text="Q1",
        )
        evt2 = CommentEvent(
            event="comment", id="c2", anchor="REQ-d00001#B",
            author="Bob", author_id="bob@co.org",
            date="2026-03-21", text="Q2",
        )
        append_event(f1, evt1)
        append_event(f2, evt2)
        idx = load_comment_index(tmp_path)
        assert idx.has_threads("REQ-p00001#A")
        assert idx.has_threads("REQ-d00001#B")
        assert len(idx) == 2
```

- [ ] **Step 10: Implement load_comment_index**

Add to `src/elspais/graph/comment_store.py`:

```python
def load_comment_index(repo_root: Path) -> CommentIndex:
    """Load all comment files into a CommentIndex.

    Globs .elspais/comments/**/*.json, loads and assembles each file,
    populates the index with active (unresolved) threads.
    """
    index = CommentIndex()
    comments_dir = repo_root / ".elspais" / "comments"
    if not comments_dir.exists():
        return index

    for json_file in sorted(comments_dir.rglob("*.json")):
        relative = str(json_file.relative_to(comments_dir))
        events = load_events(json_file)
        threads = assemble_threads(events)
        for thread in threads:
            if relative == ORPHANED_FILE:
                index.add_orphaned(thread)
            else:
                index.add_thread(thread, source_file=relative)
    return index
```

- [ ] **Step 11: Run all tests — expect pass**

Run: `pytest tests/graph/test_comment_store.py -v`
Expected: all PASS

- [ ] **Step 12: Bump version and commit**

```bash
git add src/elspais/graph/comment_store.py tests/graph/test_comment_store.py pyproject.toml
git commit -m "[CUR-1081] Add JSONL I/O, thread assembly, and comment index loading"
```

---

## Task 4: Promotion Engine

**Files:**
- Modify: `src/elspais/graph/comment_store.py`
- Modify: `tests/graph/test_comment_store.py`

- [ ] **Step 1: Write failing tests for validate_anchor**

Add to `tests/graph/test_comment_store.py`:

```python
from elspais.graph.comment_store import validate_anchor
from elspais.graph.builder import TraceGraph
from elspais.graph import GraphNode, NodeKind
from elspais.graph.relations import EdgeKind


def _build_simple_graph():
    """Build a minimal graph with one requirement and assertions."""
    graph = TraceGraph()
    req = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
    req.set_field("title", "Auth")
    assertion_a = GraphNode(id="REQ-p00001-A", kind=NodeKind.ASSERTION)
    assertion_a.set_field("label", "A")
    req.link(assertion_a, EdgeKind.STRUCTURES)
    # Add a section
    req.set_field("sections", {"Rationale": "Because security"})
    # Add an edge target
    target = GraphNode(id="REQ-d00003", kind=NodeKind.REQUIREMENT)
    req.link(target, EdgeKind.IMPLEMENTS)
    graph._index["REQ-p00001"] = req
    graph._index["REQ-p00001-A"] = assertion_a
    graph._index["REQ-d00003"] = target
    return graph


class TestValidateAnchor:
    """Tests for anchor validation against graph."""

    def test_valid_bare_node(self):
        graph = _build_simple_graph()
        assert validate_anchor("REQ-p00001", graph) is True

    def test_valid_assertion(self):
        graph = _build_simple_graph()
        assert validate_anchor("REQ-p00001#A", graph) is True

    def test_invalid_node(self):
        graph = _build_simple_graph()
        assert validate_anchor("REQ-p99999", graph) is False

    def test_invalid_assertion(self):
        graph = _build_simple_graph()
        assert validate_anchor("REQ-p00001#Z", graph) is False

    def test_valid_section(self):
        graph = _build_simple_graph()
        assert validate_anchor("REQ-p00001#section:Rationale", graph) is True

    def test_invalid_section(self):
        graph = _build_simple_graph()
        assert validate_anchor("REQ-p00001#section:Nonexistent", graph) is False

    def test_valid_edge(self):
        graph = _build_simple_graph()
        assert validate_anchor("REQ-p00001#edge:REQ-d00003", graph) is True

    def test_invalid_edge(self):
        graph = _build_simple_graph()
        assert validate_anchor("REQ-p00001#edge:REQ-d99999", graph) is False
```

- [ ] **Step 2: Run tests — expect ImportError**

Run: `pytest tests/graph/test_comment_store.py::TestValidateAnchor -v`
Expected: FAIL

- [ ] **Step 3: Implement validate_anchor**

Add to `src/elspais/graph/comment_store.py`:

```python
from elspais.graph.relations import EdgeKind

_STRUCTURAL_EDGE_KINDS = frozenset({EdgeKind.STRUCTURES})


def validate_anchor(anchor: str, graph: TraceGraph) -> bool:
    """Check if an anchor's target exists in the current graph.

    Uses existing graph API: find_by_id, iter_children, iter_outgoing_edges.
    """
    node_id, frag_type, frag_value = parse_anchor(anchor)
    node = graph.find_by_id(node_id)
    if node is None:
        return False
    if frag_type is None:
        return True
    if frag_type == "assertion":
        for child in node.iter_children(edge_kinds=_STRUCTURAL_EDGE_KINDS):
            if child.get_field("label") == frag_value:
                return True
        return False
    if frag_type == "section":
        sections = node.get_field("sections", {})
        return frag_value in sections
    if frag_type == "edge":
        for edge in node.iter_outgoing_edges():
            if edge.target.id == frag_value:
                return True
        return False
    return False
```

- [ ] **Step 4: Run tests — expect pass**

Run: `pytest tests/graph/test_comment_store.py::TestValidateAnchor -v`
Expected: all PASS

- [ ] **Step 5: Write failing tests for promote_orphaned_comments**

Add to `tests/graph/test_comment_store.py`:

```python
from elspais.graph.comment_store import promote_orphaned_comments


class TestPromoteOrphanedComments:
    """Tests for promotion at graph build time."""

    def test_valid_anchor_not_promoted(self, tmp_path):
        """Comments with valid anchors are left alone."""
        graph = _build_simple_graph()
        graph.repo_root = tmp_path
        idx = CommentIndex()
        thread = CommentThread(
            root=CommentEvent(
                event="comment", id="c1", anchor="REQ-p00001#A",
                author="Alice", author_id="alice@co.org",
                date="2026-03-20", text="OK",
            ),
        )
        idx.add_thread(thread, "spec/prd.md.json")
        events = promote_orphaned_comments(idx, graph, tmp_path)
        assert events == []
        assert idx.has_threads("REQ-p00001#A")

    def test_missing_assertion_promotes_to_node(self, tmp_path):
        """Comment on deleted assertion promotes to parent node."""
        graph = _build_simple_graph()
        graph.repo_root = tmp_path
        # Write the original comment file so promote can append
        f = tmp_path / ".elspais" / "comments" / "spec" / "prd.md.json"
        evt = CommentEvent(
            event="comment", id="c1", anchor="REQ-p00001#Z",
            author="Alice", author_id="alice@co.org",
            date="2026-03-20", text="Question about Z",
        )
        append_event(f, evt)
        idx = CommentIndex()
        idx.add_thread(CommentThread(root=evt), "spec/prd.md.json")
        events = promote_orphaned_comments(idx, graph, tmp_path)
        assert len(events) == 1
        assert events[0].event == "promote"
        assert events[0].new_anchor == "REQ-p00001"
        # Thread should now be under the node anchor
        assert idx.has_threads("REQ-p00001")

    def test_missing_node_becomes_orphaned(self, tmp_path):
        """Comment on deleted node with no ancestors becomes orphaned."""
        graph = _build_simple_graph()
        graph.repo_root = tmp_path
        f = tmp_path / ".elspais" / "comments" / "spec" / "prd.md.json"
        evt = CommentEvent(
            event="comment", id="c1", anchor="REQ-p99999",
            author="Alice", author_id="alice@co.org",
            date="2026-03-20", text="Where did this go?",
        )
        append_event(f, evt)
        idx = CommentIndex()
        idx.add_thread(CommentThread(root=evt), "spec/prd.md.json")
        events = promote_orphaned_comments(idx, graph, tmp_path)
        assert len(events) == 1
        assert list(idx.iter_orphaned())[0].root.id == "c1"
```

- [ ] **Step 6: Run tests — expect FAIL**

Run: `pytest tests/graph/test_comment_store.py::TestPromoteOrphanedComments -v`

- [ ] **Step 7: Implement promote_orphaned_comments**

Add to `src/elspais/graph/comment_store.py`:

```python
from datetime import date as date_type


def promote_orphaned_comments(
    index: CommentIndex,
    graph: TraceGraph,
    repo_root: Path,
) -> list[CommentEvent]:
    """Check all indexed anchors against the live graph. Promote stale ones.

    For each unresolved thread whose anchor is invalid:
    1. Drop fragment -> check if node exists (promote to node)
    2. Walk parents -> find nearest living ancestor
    3. No ancestor -> move to _orphaned.json

    Returns list of promote events appended to disk.
    """
    promote_events: list[CommentEvent] = []
    today = date_type.today().isoformat()
    comments_dir = repo_root / ".elspais" / "comments"

    # Snapshot anchors to avoid mutating dict during iteration
    anchors_to_check = list(index._threads.keys())

    for anchor in anchors_to_check:
        if validate_anchor(anchor, graph):
            continue

        threads = list(index._threads.pop(anchor, []))
        node_id, frag_type, _frag_value = parse_anchor(anchor)
        source_file = index._file_map.pop(anchor, None)

        # Try promoting to bare node (drop fragment)
        new_anchor = None
        reason = ""
        if frag_type is not None and graph.find_by_id(node_id) is not None:
            new_anchor = node_id
            reason = f"{frag_type} deleted from {node_id}"
        else:
            # Walk parents to find nearest living ancestor
            node = graph.find_by_id(node_id)
            if node is not None:
                for parent in node.ancestors():
                    if parent.kind.value in ("requirement", "user_journey"):
                        new_anchor = parent.id
                        reason = f"Node {node_id} unreachable, promoted to {parent.id}"
                        break

        for thread in threads:
            if new_anchor:
                evt = CommentEvent(
                    event="promote",
                    id=generate_comment_id(anchor, "system", today, new_anchor),
                    anchor=new_anchor,
                    author="system",
                    author_id="system",
                    date=today,
                    target=thread.root.id,
                    old_anchor=anchor,
                    new_anchor=new_anchor,
                    reason=reason,
                    from_file=source_file or "",
                )
                thread.promoted_from = anchor
                thread.promotion_reason = reason
                thread.anchor = new_anchor
                index.add_thread(thread, source_file or "")
                # Append to source JSONL file
                if source_file:
                    append_event(comments_dir / source_file, evt)
                promote_events.append(evt)
            else:
                # No ancestor found -> orphan
                evt = CommentEvent(
                    event="promote",
                    id=generate_comment_id(anchor, "system", today, "_orphaned"),
                    anchor="",
                    author="system",
                    author_id="system",
                    date=today,
                    target=thread.root.id,
                    old_anchor=anchor,
                    new_anchor="",
                    reason=f"No living ancestor for {anchor}",
                    from_file=source_file or "",
                )
                thread.promoted_from = anchor
                thread.promotion_reason = evt.reason
                index.add_orphaned(thread)
                append_event(comments_dir / ORPHANED_FILE, evt)
                promote_events.append(evt)

    return promote_events
```

- [ ] **Step 8: Run tests — expect pass**

Run: `pytest tests/graph/test_comment_store.py -v`
Expected: all PASS

- [ ] **Step 9: Write failing test for update_anchors_on_rename**

Add to `tests/graph/test_comment_store.py`:

```python
from elspais.graph.comment_store import update_anchors_on_rename


class TestUpdateAnchorsOnRename:
    """Tests for anchor updates when nodes are renamed."""

    def test_rename_updates_anchors(self, tmp_path):
        """Renaming a node updates all comment anchors referencing it."""
        idx = CommentIndex()
        evt = CommentEvent(
            event="comment", id="c1", anchor="REQ-p00001#A",
            author="Alice", author_id="alice@co.org",
            date="2026-03-20", text="Question",
        )
        idx.add_thread(CommentThread(root=evt), "spec/prd.md.json")
        # Also add a bare node comment
        evt2 = CommentEvent(
            event="comment", id="c2", anchor="REQ-p00001",
            author="Bob", author_id="bob@co.org",
            date="2026-03-21", text="Note",
        )
        idx.add_thread(CommentThread(root=evt2), "spec/prd.md.json")

        events = update_anchors_on_rename(idx, "REQ-p00001", "REQ-p00099", tmp_path)
        assert len(events) == 2
        assert idx.has_threads("REQ-p00099#A")
        assert idx.has_threads("REQ-p00099")
        assert not idx.has_threads("REQ-p00001#A")
        assert not idx.has_threads("REQ-p00001")
```

- [ ] **Step 10: Implement update_anchors_on_rename**

Add to `src/elspais/graph/comment_store.py`:

```python
def update_anchors_on_rename(
    index: CommentIndex,
    old_id: str,
    new_id: str,
    repo_root: Path,
) -> list[CommentEvent]:
    """Update anchors when a node or assertion is renamed.

    Scans index for anchors containing old_id, emits promote events
    with reason 'Renamed from X to Y', updates index in-place.
    """
    promote_events: list[CommentEvent] = []
    today = date_type.today().isoformat()
    comments_dir = repo_root / ".elspais" / "comments"

    # Find all anchors that reference the old ID
    old_prefix = old_id + "#"
    matching_anchors = [
        a for a in list(index._threads.keys())
        if a == old_id or a.startswith(old_prefix)
    ]

    for old_anchor in matching_anchors:
        # Compute new anchor
        if old_anchor == old_id:
            new_anchor = new_id
        else:
            fragment = old_anchor[len(old_id):]  # includes the #
            new_anchor = new_id + fragment

        threads = list(index._threads.pop(old_anchor, []))
        source_file = index._file_map.pop(old_anchor, None)
        reason = f"Renamed from {old_id} to {new_id}"

        for thread in threads:
            evt = CommentEvent(
                event="promote",
                id=generate_comment_id(old_anchor, "system", today, new_anchor),
                anchor=new_anchor,
                author="system",
                author_id="system",
                date=today,
                target=thread.root.id,
                old_anchor=old_anchor,
                new_anchor=new_anchor,
                reason=reason,
                from_file=source_file or "",
            )
            thread.promoted_from = old_anchor
            thread.promotion_reason = reason
            thread.anchor = new_anchor
            index.add_thread(thread, source_file or "")
            if source_file:
                append_event(comments_dir / source_file, evt)
            promote_events.append(evt)

    return promote_events
```

- [ ] **Step 11: Run all tests — expect pass**

Run: `pytest tests/graph/test_comment_store.py -v`
Expected: all PASS

- [ ] **Step 12: Bump version and commit**

```bash
git add src/elspais/graph/comment_store.py tests/graph/test_comment_store.py pyproject.toml
git commit -m "[CUR-1081] Add promotion engine and anchor rename hooks"
```

---

## Task 5: TraceGraph and FederatedGraph Integration

**Files:**
- Modify: `src/elspais/graph/builder.py` (~lines 67, 920, 1227)
- Modify: `src/elspais/graph/federated.py` (~line 173)
- Create: `tests/graph/test_comment_integration.py`

- [ ] **Step 1: Write failing tests for TraceGraph comment methods**

```python
# tests/graph/test_comment_integration.py
"""Tests for comment integration with TraceGraph and FederatedGraph."""

from elspais.graph.builder import TraceGraph
from elspais.graph.comments import CommentEvent, CommentIndex, CommentThread


class TestTraceGraphComments:
    """Tests for comment methods on TraceGraph."""

    def _make_thread(self, anchor, cid="c1"):
        root = CommentEvent(
            event="comment", id=cid, anchor=anchor,
            author="Alice", author_id="alice@co.org",
            date="2026-03-20", text="Hello",
        )
        return CommentThread(root=root)

    def test_empty_graph_has_no_comments(self):
        graph = TraceGraph()
        assert graph.comment_count("REQ-p00001") == 0
        assert not graph.has_comments("REQ-p00001")
        assert list(graph.iter_comments("REQ-p00001")) == []
        assert list(graph.iter_orphaned_comments()) == []

    def test_graph_with_comment_index(self):
        graph = TraceGraph()
        idx = CommentIndex()
        idx.add_thread(self._make_thread("REQ-p00001#A"), "f.json")
        graph._comment_index = idx
        assert graph.comment_count("REQ-p00001#A") == 1
        assert graph.has_comments("REQ-p00001#A")
        threads = list(graph.iter_comments("REQ-p00001#A"))
        assert len(threads) == 1

    def test_orphaned_comments(self):
        graph = TraceGraph()
        idx = CommentIndex()
        thread = self._make_thread("REQ-deleted")
        idx.add_orphaned(thread)
        graph._comment_index = idx
        orphaned = list(graph.iter_orphaned_comments())
        assert len(orphaned) == 1
```

- [ ] **Step 2: Run tests — expect AttributeError**

Run: `pytest tests/graph/test_comment_integration.py::TestTraceGraphComments -v`
Expected: FAIL (no `_comment_index` field, no methods)

- [ ] **Step 3: Add _comment_index field and delegate methods to TraceGraph**

In `src/elspais/graph/builder.py`:

1. Add import at top: `from elspais.graph.comments import CommentIndex, CommentThread`
2. Add field after `_terms` (~line 67):
   ```python
   _comment_index: CommentIndex = field(default_factory=CommentIndex, init=False)
   ```
3. Add delegate methods (group them together, after the terms-related methods):
   ```python
   def iter_comments(self, anchor: str) -> Iterator[CommentThread]:
       """Yield comment threads for an anchor."""
       return self._comment_index.iter_threads(anchor)

   def comment_count(self, anchor: str) -> int:
       """Count comment threads for an anchor."""
       return self._comment_index.thread_count(anchor)

   def has_comments(self, anchor: str) -> bool:
       """Check if any comment threads exist for an anchor."""
       return self._comment_index.has_threads(anchor)

   def iter_orphaned_comments(self) -> Iterator[CommentThread]:
       """Yield orphaned comment threads."""
       return self._comment_index.iter_orphaned()
   ```

- [ ] **Step 4: Run tests — expect pass**

Run: `pytest tests/graph/test_comment_integration.py::TestTraceGraphComments -v`
Expected: all PASS

- [ ] **Step 5: Write failing tests for FederatedGraph comment routing**

Add to `tests/graph/test_comment_integration.py`:

```python
from pathlib import Path
from elspais.graph.federated import FederatedGraph, RepoEntry


class TestFederatedGraphComments:
    """Tests for comment routing in FederatedGraph."""

    def _make_thread(self, anchor, cid="c1"):
        root = CommentEvent(
            event="comment", id=cid, anchor=anchor,
            author="Alice", author_id="alice@co.org",
            date="2026-03-20", text="Hello",
        )
        return CommentThread(root=root)

    def _build_federated(self):
        """Build a FederatedGraph with two repos, each with comment indexes."""
        from elspais.graph import GraphNode, NodeKind

        g1 = TraceGraph()
        req1 = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        g1._index["REQ-p00001"] = req1
        g1._roots.append(req1)
        idx1 = CommentIndex()
        idx1.add_thread(self._make_thread("REQ-p00001#A", "c1"), "f1.json")
        orphan = self._make_thread("REQ-deleted", "c3")
        idx1.add_orphaned(orphan)
        g1._comment_index = idx1

        g2 = TraceGraph()
        req2 = GraphNode(id="REQ-d00001", kind=NodeKind.REQUIREMENT)
        g2._index["REQ-d00001"] = req2
        g2._roots.append(req2)
        idx2 = CommentIndex()
        idx2.add_thread(self._make_thread("REQ-d00001#B", "c2"), "f2.json")
        g2._comment_index = idx2

        repos = [
            RepoEntry(name="root", graph=g1, config={}, repo_root=Path("/r1")),
            RepoEntry(name="dev", graph=g2, config={}, repo_root=Path("/r2")),
        ]
        return FederatedGraph(repos)

    def test_routes_to_correct_repo(self):
        fg = self._build_federated()
        assert fg.comment_count("REQ-p00001#A") == 1
        assert fg.comment_count("REQ-d00001#B") == 1

    def test_unknown_anchor_returns_zero(self):
        fg = self._build_federated()
        assert fg.comment_count("REQ-p99999#A") == 0

    def test_orphaned_aggregates_across_repos(self):
        fg = self._build_federated()
        orphaned = list(fg.iter_orphaned_comments())
        assert len(orphaned) == 1
        assert orphaned[0].root.id == "c3"

    def test_has_comments(self):
        fg = self._build_federated()
        assert fg.has_comments("REQ-p00001#A")
        assert not fg.has_comments("REQ-p00001#Z")
```

- [ ] **Step 6: Run tests — expect AttributeError**

Run: `pytest tests/graph/test_comment_integration.py::TestFederatedGraphComments -v`
Expected: FAIL

- [ ] **Step 7: Add comment methods to FederatedGraph**

In `src/elspais/graph/federated.py`:

1. Add import: `from elspais.graph.comments import CommentIndex, CommentThread`
2. Add import: `from elspais.graph.comment_store import parse_anchor`
3. Add comment routing methods (follow the terms pattern):

```python
def iter_comments(self, anchor: str) -> Iterator[CommentThread]:
    """Yield comment threads for an anchor, routed to owning repo."""
    node_id = parse_anchor(anchor)[0]
    repo_name = self._ownership.get(node_id)
    if repo_name:
        entry = self._repos.get(repo_name)
        if entry and entry.graph:
            yield from entry.graph.iter_comments(anchor)

def comment_count(self, anchor: str) -> int:
    """Count comment threads for an anchor."""
    node_id = parse_anchor(anchor)[0]
    repo_name = self._ownership.get(node_id)
    if repo_name:
        entry = self._repos.get(repo_name)
        if entry and entry.graph:
            return entry.graph.comment_count(anchor)
    return 0

def has_comments(self, anchor: str) -> bool:
    """Check if any comment threads exist for an anchor."""
    return self.comment_count(anchor) > 0

def iter_orphaned_comments(self) -> Iterator[CommentThread]:
    """Yield orphaned comments aggregated across all repos.

    Orphans remain stored in their original repo's _orphaned.json.
    """
    for entry in self._repos.values():
        if entry.graph:
            yield from entry.graph.iter_orphaned_comments()
```

- [ ] **Step 8: Run all integration tests — expect pass**

Run: `pytest tests/graph/test_comment_integration.py -v`
Expected: all PASS

- [ ] **Step 9: Add rename hooks to TraceGraph**

In `src/elspais/graph/builder.py`:

1. Add import: `from elspais.graph.comment_store import update_anchors_on_rename`
2. In `rename_node()` (~line 920, before `return entry`), add:
   ```python
   # Update comment anchors referencing the old ID
   if self._comment_index is not None:
       update_anchors_on_rename(self._comment_index, old_id, new_id, self.repo_root)
   ```
3. In `rename_assertion()` (~line 1227, before `return entry`), add the same pattern using the old/new assertion ID.

- [ ] **Step 10: Run full test suite to verify no regressions**

Run: `pytest tests/ -x -q`
Expected: all PASS

- [ ] **Step 11: Bump version and commit**

```bash
git add src/elspais/graph/builder.py src/elspais/graph/federated.py tests/graph/test_comment_integration.py pyproject.toml
git commit -m "[CUR-1081] Integrate CommentIndex into TraceGraph and FederatedGraph"
```

---

## Task 6: API Endpoints

**Files:**
- Modify: `src/elspais/server/routes_api.py`
- Modify: `src/elspais/server/app.py` (~lines 135-183)
- Create: `tests/server/test_comment_api.py`

- [ ] **Step 1: Write failing tests for comment API endpoints**

```python
# tests/server/test_comment_api.py
"""Tests for comment API endpoints."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from elspais.graph import GraphNode, NodeKind
from elspais.graph.builder import TraceGraph
from elspais.graph.comments import CommentEvent, CommentIndex, CommentThread
from elspais.graph.federated import FederatedGraph, RepoEntry


def _make_app(tmp_path):
    """Create a test app with a simple graph and comment index."""
    from elspais.server.app import create_app

    graph = TraceGraph(repo_root=tmp_path)
    req = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
    req.set_field("title", "Auth")
    assertion_a = GraphNode(id="REQ-p00001-A", kind=NodeKind.ASSERTION)
    assertion_a.set_field("label", "A")
    from elspais.graph.relations import EdgeKind
    req.link(assertion_a, EdgeKind.STRUCTURES)
    graph._index["REQ-p00001"] = req
    graph._index["REQ-p00001-A"] = assertion_a
    graph._roots.append(req)

    repos = [RepoEntry(name="root", graph=graph, config={}, repo_root=tmp_path)]
    federated = FederatedGraph(repos)

    app = create_app(federated, repo_root=tmp_path, config={})
    return app, tmp_path


class TestCommentAddEndpoint:
    """Tests for POST /api/comment/add."""

    def test_add_comment(self, tmp_path):
        app, root = _make_app(tmp_path)
        client = TestClient(app)
        with patch("elspais.server.routes_api.get_author_info") as mock_author:
            mock_author.return_value = {"name": "Alice Smith", "id": "alice@co.org"}
            resp = client.post("/api/comment/add", json={
                "anchor": "REQ-p00001#A",
                "text": "Should we support SAML?",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["comment"]["anchor"] == "REQ-p00001#A"
        assert data["comment"]["author"] == "Alice Smith"

    def test_add_comment_missing_text(self, tmp_path):
        app, root = _make_app(tmp_path)
        client = TestClient(app)
        resp = client.post("/api/comment/add", json={"anchor": "REQ-p00001#A"})
        assert resp.status_code == 400


class TestCommentReplyEndpoint:
    """Tests for POST /api/comment/reply."""

    def test_reply_to_comment(self, tmp_path):
        app, root = _make_app(tmp_path)
        client = TestClient(app)
        with patch("elspais.server.routes_api.get_author_info") as mock_author:
            mock_author.return_value = {"name": "Alice", "id": "alice@co.org"}
            # First add a comment
            resp1 = client.post("/api/comment/add", json={
                "anchor": "REQ-p00001#A", "text": "Question",
            })
            comment_id = resp1.json()["comment"]["id"]
            # Then reply
            mock_author.return_value = {"name": "Bob", "id": "bob@co.org"}
            resp2 = client.post("/api/comment/reply", json={
                "parent_id": comment_id, "text": "Answer",
            })
        assert resp2.status_code == 200
        assert resp2.json()["comment"]["parent"] == comment_id


class TestCommentResolveEndpoint:
    """Tests for POST /api/comment/resolve."""

    def test_resolve_comment(self, tmp_path):
        app, root = _make_app(tmp_path)
        client = TestClient(app)
        with patch("elspais.server.routes_api.get_author_info") as mock_author:
            mock_author.return_value = {"name": "Alice", "id": "alice@co.org"}
            resp1 = client.post("/api/comment/add", json={
                "anchor": "REQ-p00001#A", "text": "Question",
            })
            comment_id = resp1.json()["comment"]["id"]
            resp2 = client.post("/api/comment/resolve", json={
                "comment_id": comment_id,
            })
        assert resp2.status_code == 200
        assert resp2.json()["success"] is True


class TestCommentReadEndpoints:
    """Tests for GET /api/comments and /api/comments/card."""

    def test_get_comments_by_anchor(self, tmp_path):
        app, root = _make_app(tmp_path)
        client = TestClient(app)
        with patch("elspais.server.routes_api.get_author_info") as mock_author:
            mock_author.return_value = {"name": "Alice", "id": "alice@co.org"}
            client.post("/api/comment/add", json={
                "anchor": "REQ-p00001#A", "text": "Question",
            })
        resp = client.get("/api/comments?anchor=REQ-p00001%23A")
        assert resp.status_code == 200
        assert len(resp.json()["threads"]) == 1

    def test_get_comments_for_card(self, tmp_path):
        app, root = _make_app(tmp_path)
        client = TestClient(app)
        with patch("elspais.server.routes_api.get_author_info") as mock_author:
            mock_author.return_value = {"name": "Alice", "id": "alice@co.org"}
            client.post("/api/comment/add", json={
                "anchor": "REQ-p00001#A", "text": "Q1",
            })
            client.post("/api/comment/add", json={
                "anchor": "REQ-p00001", "text": "Q2",
            })
        resp = client.get("/api/comments/card?node_id=REQ-p00001")
        assert resp.status_code == 200
        threads = resp.json()["threads"]
        assert "REQ-p00001#A" in threads
        assert "REQ-p00001" in threads
```

- [ ] **Step 2: Run tests — expect failures (routes not registered)**

Run: `pytest tests/server/test_comment_api.py -v`
Expected: FAIL (404s)

- [ ] **Step 3: Implement API endpoint handlers**

Add to `src/elspais/server/routes_api.py`:

```python
# Add imports at top
from datetime import date as date_type
from elspais.graph.comment_store import (
    append_event,
    comment_file_for,
    generate_comment_id,
    parse_anchor,
)
from elspais.graph.comments import CommentEvent, CommentThread
from elspais.utilities.git import get_author_info


def _thread_to_dict(thread: CommentThread) -> dict:
    """Serialize a CommentThread for JSON response."""
    return {
        "root": {
            "id": thread.root.id,
            "anchor": thread.root.anchor,
            "author": thread.root.author,
            "author_id": thread.root.author_id,
            "date": thread.root.date,
            "text": thread.root.text,
        },
        "replies": [
            {
                "id": r.id, "anchor": r.anchor, "author": r.author,
                "author_id": r.author_id, "date": r.date, "text": r.text,
                "parent": r.parent,
            }
            for r in thread.replies
        ],
        "anchor": thread.anchor,
        "resolved": thread.resolved,
        "promoted_from": thread.promoted_from,
        "promotion_reason": thread.promotion_reason,
    }


async def api_comment_add(request: Request) -> JSONResponse:
    """POST /api/comment/add — add a new comment."""
    state = _st(request)
    payload = await request.json()
    anchor = payload.get("anchor", "")
    text = payload.get("text", "")
    if not text:
        return JSONResponse({"success": False, "error": "text required"}, status_code=400)
    if not anchor:
        return JSONResponse({"success": False, "error": "anchor required"}, status_code=400)

    try:
        author_info = get_author_info(
            state.config.get("changelog", {}).get("id_source", "gh")
        )
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

    today = date_type.today().isoformat()
    comment_id = generate_comment_id(anchor, author_info["id"], today, text)
    evt = CommentEvent(
        event="comment", id=comment_id, anchor=anchor,
        author=author_info["name"], author_id=author_info["id"],
        date=today, text=text,
    )

    # Resolve source file from anchor -> node -> file node
    node_id = parse_anchor(anchor)[0]
    graph = state.graph
    node = graph.find_by_id(node_id)
    if node is None:
        return JSONResponse({"success": False, "error": f"node {node_id} not found"}, status_code=404)

    file_node = node.file_node()
    if file_node:
        rel_path = file_node.get_field("relative_path", "")
    else:
        rel_path = node_id  # fallback

    jsonl_path = comment_file_for(state.repo_root, rel_path)
    append_event(jsonl_path, evt)

    # Update in-memory index
    from elspais.graph.comments import CommentThread
    thread = CommentThread(root=evt)
    source_rel = str(jsonl_path.relative_to(state.repo_root / ".elspais" / "comments"))

    # Route to correct sub-graph's comment index
    if hasattr(graph, '_repos'):
        # FederatedGraph
        repo_name = graph._ownership.get(node_id)
        if repo_name and graph._repos[repo_name].graph:
            graph._repos[repo_name].graph._comment_index.add_thread(thread, source_rel)
    else:
        graph._comment_index.add_thread(thread, source_rel)

    return JSONResponse({
        "success": True,
        "comment": {
            "id": evt.id, "anchor": evt.anchor,
            "author": evt.author, "author_id": evt.author_id,
            "date": evt.date, "text": evt.text,
        },
    })


async def api_comment_reply(request: Request) -> JSONResponse:
    """POST /api/comment/reply — reply to an existing comment."""
    state = _st(request)
    payload = await request.json()
    parent_id = payload.get("parent_id", "")
    text = payload.get("text", "")
    if not text:
        return JSONResponse({"success": False, "error": "text required"}, status_code=400)
    if not parent_id:
        return JSONResponse({"success": False, "error": "parent_id required"}, status_code=400)

    # Find parent thread to get anchor and source file
    graph = state.graph
    parent_anchor = None
    source_rel = None

    # Search all comment indexes for the parent
    def _find_parent(comment_index):
        for anchor_key in list(comment_index._threads.keys()):
            for thread in comment_index.iter_threads(anchor_key):
                if thread.root.id == parent_id:
                    return thread.anchor, comment_index.source_file_for(anchor_key)
                for reply in thread.replies:
                    if reply.id == parent_id:
                        return thread.anchor, comment_index.source_file_for(anchor_key)
        return None, None

    if hasattr(graph, '_repos'):
        for entry in graph._repos.values():
            if entry.graph:
                parent_anchor, source_rel = _find_parent(entry.graph._comment_index)
                if parent_anchor:
                    break
    else:
        parent_anchor, source_rel = _find_parent(graph._comment_index)

    if not parent_anchor:
        return JSONResponse({"success": False, "error": "parent not found"}, status_code=404)

    try:
        author_info = get_author_info(
            state.config.get("changelog", {}).get("id_source", "gh")
        )
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

    today = date_type.today().isoformat()
    reply_id = generate_comment_id(parent_anchor, author_info["id"], today, text)
    evt = CommentEvent(
        event="reply", id=reply_id, anchor=parent_anchor,
        author=author_info["name"], author_id=author_info["id"],
        date=today, text=text, parent=parent_id,
    )

    # Append to the same JSONL file as the parent
    node_id = parse_anchor(parent_anchor)[0]
    node = graph.find_by_id(node_id)
    file_node = node.file_node() if node else None
    rel_path = file_node.get_field("relative_path", "") if file_node else node_id
    jsonl_path = comment_file_for(state.repo_root, rel_path)
    append_event(jsonl_path, evt)

    # Update in-memory index — find the thread and add reply
    def _add_reply(comment_index):
        for thread in comment_index.iter_threads(parent_anchor):
            if thread.root.id == parent_id:
                thread.replies.append(evt)
                return True
        return False

    if hasattr(graph, '_repos'):
        for entry in graph._repos.values():
            if entry.graph and _add_reply(entry.graph._comment_index):
                break
    else:
        _add_reply(graph._comment_index)

    return JSONResponse({
        "success": True,
        "comment": {
            "id": evt.id, "anchor": evt.anchor,
            "author": evt.author, "author_id": evt.author_id,
            "date": evt.date, "text": evt.text, "parent": evt.parent,
        },
    })


async def api_comment_resolve(request: Request) -> JSONResponse:
    """POST /api/comment/resolve — resolve a comment."""
    state = _st(request)
    payload = await request.json()
    comment_id = payload.get("comment_id", "")
    if not comment_id:
        return JSONResponse({"success": False, "error": "comment_id required"}, status_code=400)

    graph = state.graph

    try:
        author_info = get_author_info(
            state.config.get("changelog", {}).get("id_source", "gh")
        )
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

    today = date_type.today().isoformat()

    # Find and resolve the thread
    found_anchor = None

    def _find_and_resolve(comment_index):
        nonlocal found_anchor
        for anchor_key in list(comment_index._threads.keys()):
            threads = comment_index._threads.get(anchor_key, [])
            for i, thread in enumerate(threads):
                if thread.root.id == comment_id:
                    found_anchor = thread.anchor
                    threads.pop(i)
                    return True
        return False

    if hasattr(graph, '_repos'):
        for entry in graph._repos.values():
            if entry.graph and _find_and_resolve(entry.graph._comment_index):
                break
    else:
        _find_and_resolve(graph._comment_index)

    if not found_anchor:
        return JSONResponse({"success": False, "error": "comment not found"}, status_code=404)

    resolve_id = generate_comment_id(found_anchor, author_info["id"], today, "resolve")
    evt = CommentEvent(
        event="resolve", id=resolve_id, anchor=found_anchor,
        author=author_info["name"], author_id=author_info["id"],
        date=today, target=comment_id,
    )

    node_id = parse_anchor(found_anchor)[0]
    node = graph.find_by_id(node_id)
    file_node = node.file_node() if node else None
    rel_path = file_node.get_field("relative_path", "") if file_node else node_id
    jsonl_path = comment_file_for(state.repo_root, rel_path)
    append_event(jsonl_path, evt)

    return JSONResponse({"success": True})


async def api_get_comments(request: Request) -> JSONResponse:
    """GET /api/comments?anchor=... — get threads for an anchor."""
    state = _st(request)
    anchor = request.query_params.get("anchor", "")
    if not anchor:
        return JSONResponse({"success": False, "error": "anchor required"}, status_code=400)

    threads = list(state.graph.iter_comments(anchor))
    return JSONResponse({
        "success": True,
        "threads": [_thread_to_dict(t) for t in threads],
    })


async def api_get_comments_card(request: Request) -> JSONResponse:
    """GET /api/comments/card?node_id=... — all comments for a card."""
    state = _st(request)
    node_id = request.query_params.get("node_id", "")
    if not node_id:
        return JSONResponse({"success": False, "error": "node_id required"}, status_code=400)

    graph = state.graph
    result: dict[str, list] = {}

    # Collect from all repos
    def _collect(comment_index):
        for anchor in comment_index.iter_all_anchors_for_node(node_id):
            threads = list(comment_index.iter_threads(anchor))
            if threads:
                result[anchor] = [_thread_to_dict(t) for t in threads]

    if hasattr(graph, '_repos'):
        repo_name = graph._ownership.get(node_id)
        if repo_name:
            entry = graph._repos.get(repo_name)
            if entry and entry.graph:
                _collect(entry.graph._comment_index)
    else:
        _collect(graph._comment_index)

    return JSONResponse({"success": True, "threads": result})


async def api_get_comments_orphaned(request: Request) -> JSONResponse:
    """GET /api/comments/orphaned — all orphaned comments."""
    state = _st(request)
    orphaned = list(state.graph.iter_orphaned_comments())
    return JSONResponse({
        "success": True,
        "threads": [_thread_to_dict(t) for t in orphaned],
    })
```

- [ ] **Step 4: Register routes in app.py**

In `src/elspais/server/app.py`, add to the routes list (~lines 135-183):

```python
# Comment endpoints (read)
Route("/api/comments", api_get_comments),
Route("/api/comments/card", api_get_comments_card),
Route("/api/comments/orphaned", api_get_comments_orphaned),
# Comment endpoints (write)
Route("/api/comment/add", api_comment_add, methods=["POST"]),
Route("/api/comment/reply", api_comment_reply, methods=["POST"]),
Route("/api/comment/resolve", api_comment_resolve, methods=["POST"]),
```

Add the corresponding imports from `routes_api`.

- [ ] **Step 5: Run API tests — expect pass**

Run: `pytest tests/server/test_comment_api.py -v`
Expected: all PASS (may need adjustments to `create_app` call signature — check actual params)

- [ ] **Step 6: Run full test suite to verify no regressions**

Run: `pytest tests/ -x -q`
Expected: all PASS

- [ ] **Step 7: Bump version and commit**

```bash
git add src/elspais/server/routes_api.py src/elspais/server/app.py tests/server/test_comment_api.py pyproject.toml
git commit -m "[CUR-1081] Add comment API endpoints (add/reply/resolve/query)"
```

---

## Task 7: Viewer UI — data-anchor Attributes and Margin Column

**Files:**
- Modify: `src/elspais/html/templates/partials/js/_card-stack.js.j2`
- Modify: CSS files for comment styling

This task adds `data-anchor` attributes to all commentable elements and renders the margin column with comment indicators. The exact line numbers and DOM structure depend on the current state of `_card-stack.js.j2` after PR 57 merge — read the file before implementing.

- [ ] **Step 1: Read _card-stack.js.j2 to identify exact insertion points**

Read the card rendering functions to find:
- Card header: where to add `data-anchor="REQ-p00001"`
- Assertion rows: where to add `data-anchor="REQ-p00001#A"` (existing `data-assertion-id` is nearby)
- Edge rows: where to add `data-anchor="REQ-p00001#edge:REQ-d00003"`
- Body sections: where to add `data-anchor="REQ-p00001#section:Name"`

- [ ] **Step 2: Add data-anchor attributes to card header**

In `buildCardHtml()`, add `data-anchor` to the card wrapper div:
```javascript
h += '<div class="req-card" data-anchor="' + nodeId + '">';
```

- [ ] **Step 3: Add data-anchor to assertion rows**

In `buildAssertionHtml()`, add to the wrapper:
```javascript
h += '<div class="card-assertion-wrapper" data-anchor="' + nodeId + '#' + label + '"';
```

- [ ] **Step 4: Add data-anchor to edge rows**

In edge rendering section, add:
```javascript
h += '<div class="card-edge-row" data-anchor="' + nodeId + '#edge:' + targetId + '"';
```

- [ ] **Step 5: Add data-anchor to body section elements**

Body sections already render in Complete mode. Add:
```javascript
h += '<div class="card-section" data-anchor="' + nodeId + '#section:' + sectionName + '"';
```

- [ ] **Step 6: Add data-anchor to journey cards**

Same pattern for `buildJourneyCardHtml()`.

- [ ] **Step 7: Add margin column HTML**

After each commentable element, render a margin cell:
```javascript
function marginCell(anchor, commentData) {
    var count = commentData[anchor] ? commentData[anchor].length : 0;
    if (count === 0) return '<div class="comment-margin"></div>';
    var badge = count > 1 ? '<span class="comment-badge">' + count + '</span>' : '';
    return '<div class="comment-margin has-comments" onclick="toggleCommentThread(\'' +
        anchor + '\')">' +
        '<svg class="comment-icon">...</svg>' + badge + '</div>';
}
```

- [ ] **Step 8: Fetch comment data when card opens**

In the card open handler, fetch `/api/comments/card?node_id=...`:
```javascript
function loadCardComments(nodeId) {
    apiFetch('/api/comments/card?node_id=' + encodeURIComponent(nodeId))
        .then(function(data) {
            if (data.success) {
                cardCommentData[nodeId] = data.threads;
                renderMarginIndicators(nodeId, data.threads);
            }
        });
}
```

- [ ] **Step 9: Add CSS for margin column and comment indicators**

Add styles for `.comment-margin`, `.comment-icon`, `.comment-badge`, `.has-comments`.

- [ ] **Step 10: Test margin column manually in viewer**

Start the viewer, open a card, verify margin column renders correctly.

- [ ] **Step 11: Bump version and commit**

```bash
git add src/elspais/html/templates/ pyproject.toml
git commit -m "[CUR-1081] Add data-anchor attributes and comment margin column"
```

---

## Task 8: Viewer UI — Inline Threads and Comment Mode

**Files:**
- Modify: `src/elspais/html/templates/partials/js/_card-stack.js.j2`
- Modify: `src/elspais/html/templates/partials/js/_edit-engine.js.j2`
- Modify: CSS files

- [ ] **Step 1: Implement inline thread rendering**

Add function to render a thread below its target element:
```javascript
function renderCommentThread(anchor, threads) {
    // Build thread HTML: author line, text, resolve button, reply textarea
    // Insert as sibling after the element with matching data-anchor
}
```

- [ ] **Step 2: Implement reply submission**

Wire the `[Reply...]` textarea to POST `/api/comment/reply` and append the new reply to the DOM.

- [ ] **Step 3: Implement resolve button**

Wire `[Resolve]` button to POST `/api/comment/resolve` and remove the thread from DOM.

- [ ] **Step 4: Implement comment mode toggle**

In `_edit-engine.js.j2`, add:
```javascript
var commentModeActive = false;

function toggleCommentMode() {
    if (!editState.enabled) return;
    commentModeActive = !commentModeActive;
    if (commentModeActive) {
        document.body.classList.add('comment-mode');
        showToast('Click any element to add a comment. Press Esc to cancel.');
    } else {
        document.body.classList.remove('comment-mode');
    }
}
```

- [ ] **Step 5: Add C keyboard shortcut**

Add keydown listener for `C` key (only when edit mode is active, no input focused):
```javascript
document.addEventListener('keydown', function(e) {
    if (e.key === 'c' && editState.enabled && !isInputFocused()) {
        toggleCommentMode();
    }
});
```

- [ ] **Step 6: Implement one-shot click handler**

When comment mode is active and user clicks a `[data-anchor]` element:
```javascript
document.addEventListener('click', function(e) {
    if (!commentModeActive) return;
    var target = e.target.closest('[data-anchor]');
    if (!target) return;
    e.preventDefault();
    var anchor = target.getAttribute('data-anchor');
    showCommentInput(anchor, target);
    commentModeActive = false;
    document.body.classList.remove('comment-mode');
});
```

- [ ] **Step 7: Implement comment input form**

Show a textarea below the clicked element, with Submit/Cancel buttons:
```javascript
function showCommentInput(anchor, afterElement) {
    // Create textarea + buttons
    // On submit: POST /api/comment/add, render new thread, update margin
    // On cancel or Esc: remove input
}
```

- [ ] **Step 8: Add toolbar button for comment mode**

Add speech bubble icon button next to Edit Mode toggle, enabled only in Edit Mode.

- [ ] **Step 9: Add CSS for comment mode hover and threads**

- `.comment-mode [data-anchor]:hover` — blue highlight
- `.comment-mode` — cursor: comment icon
- `.comment-thread` — thread container styling
- `.comment-author` — author line styling
- `.comment-text` — comment body
- Edit-mode-only visibility for resolve/reply controls

- [ ] **Step 10: Test comment mode manually**

Start viewer, enter Edit Mode, press C, click an assertion, type a comment, submit. Verify it appears inline with margin indicator.

- [ ] **Step 11: Bump version and commit**

```bash
git add src/elspais/html/templates/ pyproject.toml
git commit -m "[CUR-1081] Add inline comment threads and comment mode"
```

---

## Task 9: Lost Comments Card

**Files:**
- Modify: `src/elspais/html/templates/partials/js/_card-stack.js.j2`

- [ ] **Step 1: Fetch orphaned comments on page load**

```javascript
function loadOrphanedComments() {
    apiFetch('/api/comments/orphaned').then(function(data) {
        if (data.success && data.threads.length > 0) {
            renderLostCommentsCard(data.threads);
        }
    });
}
```

- [ ] **Step 2: Render Lost Comments card**

Build a special card at the top of the card column showing orphaned threads with their original context.

- [ ] **Step 3: Test with orphaned comments**

Manually create a comment on an assertion, delete the assertion, rebuild graph, verify the comment appears in Lost Comments card.

- [ ] **Step 4: Bump version and commit**

```bash
git add src/elspais/html/templates/ pyproject.toml
git commit -m "[CUR-1081] Add Lost Comments card for orphaned comments"
```

---

## Task 10: Compaction CLI Command

**Files:**
- Create: `src/elspais/commands/comments.py`
- Modify: CLI registration (wherever commands are registered)
- Modify: `tests/` (add compaction test)

- [ ] **Step 1: Write failing test for compact_file**

Add to `tests/graph/test_comment_store.py`:

```python
from elspais.graph.comment_store import compact_file


class TestCompactFile:
    """Tests for JSONL compaction."""

    def test_compact_removes_resolved(self, tmp_path):
        path = tmp_path / "test.json"
        append_event(path, CommentEvent(
            event="comment", id="c1", anchor="REQ-p00001#A",
            author="Alice", author_id="a@x", date="2026-03-20", text="Q",
        ))
        append_event(path, CommentEvent(
            event="resolve", id="r1", anchor="REQ-p00001#A",
            author="Bob", author_id="b@x", date="2026-03-21", target="c1",
        ))
        append_event(path, CommentEvent(
            event="comment", id="c2", anchor="REQ-p00001#B",
            author="Alice", author_id="a@x", date="2026-03-22", text="Active",
        ))
        removed = compact_file(path)
        assert removed == 2  # c1 comment + r1 resolve
        events = load_events(path)
        assert len(events) == 1
        assert events[0].id == "c2"

    def test_compact_collapses_promote_chains(self, tmp_path):
        path = tmp_path / "test.json"
        append_event(path, CommentEvent(
            event="comment", id="c1", anchor="REQ-p00001#D",
            author="Alice", author_id="a@x", date="2026-03-20", text="Q",
        ))
        append_event(path, CommentEvent(
            event="promote", id="p1", anchor="REQ-p00001",
            author="system", author_id="system", date="2026-03-21",
            target="c1", old_anchor="REQ-p00001#D", new_anchor="REQ-p00001",
            reason="D deleted",
        ))
        append_event(path, CommentEvent(
            event="promote", id="p2", anchor="REQ-p00002",
            author="system", author_id="system", date="2026-03-22",
            target="c1", old_anchor="REQ-p00001", new_anchor="REQ-p00002",
            reason="REQ-p00001 deleted",
        ))
        removed = compact_file(path)
        assert removed >= 1  # at least one intermediate promote removed
        events = load_events(path)
        # Should have: original comment (with updated anchor) + final promote
        promote_events = [e for e in events if e.event == "promote"]
        assert len(promote_events) <= 1
```

- [ ] **Step 2: Implement compact_file**

Add to `src/elspais/graph/comment_store.py`:

```python
def compact_file(path: Path) -> int:
    """Rewrite a JSONL file: strip resolved threads, collapse promote chains.

    Returns number of events removed.
    """
    if not path.exists():
        return 0

    events = load_events(path)
    original_count = len(events)

    # Find resolved comment IDs
    resolved_ids: set[str] = set()
    for evt in events:
        if evt.event == "resolve":
            resolved_ids.add(evt.target)

    # Find final promote target for each comment (collapse chains)
    final_anchor: dict[str, str] = {}  # comment_id -> final anchor
    final_promote: dict[str, CommentEvent] = {}  # comment_id -> final promote event
    for evt in events:
        if evt.event == "promote":
            final_anchor[evt.target] = evt.new_anchor
            final_promote[evt.target] = evt

    # Build compacted event list
    compacted: list[CommentEvent] = []
    seen_comments: set[str] = set()
    for evt in events:
        if evt.event == "comment":
            if evt.id in resolved_ids:
                continue  # skip resolved
            seen_comments.add(evt.id)
            compacted.append(evt)
        elif evt.event == "reply":
            if evt.parent in resolved_ids:
                continue  # skip replies to resolved
            compacted.append(evt)
        elif evt.event == "resolve":
            continue  # strip all resolve events
        elif evt.event == "promote":
            # Keep only the final promote for each comment
            if evt.target in final_promote and final_promote[evt.target].id == evt.id:
                compacted.append(evt)
            # Otherwise skip intermediate promotes

    # Write back
    removed = original_count - len(compacted)
    if removed > 0:
        with open(path, "w", encoding="utf-8") as f:
            for evt in compacted:
                f.write(json.dumps(_event_to_dict(evt), separators=(",", ":")) + "\n")

    return removed
```

- [ ] **Step 3: Run tests — expect pass**

Run: `pytest tests/graph/test_comment_store.py::TestCompactFile -v`
Expected: all PASS

- [ ] **Step 4: Create CLI command**

Create `src/elspais/commands/comments.py` with a `compact` subcommand that globs `.elspais/comments/**/*.json` and calls `compact_file()` on each, reporting totals.

- [ ] **Step 5: Register command and test manually**

Run: `elspais comments compact` and verify output.

- [ ] **Step 6: Bump version and commit**

```bash
git add src/elspais/graph/comment_store.py src/elspais/commands/comments.py tests/graph/test_comment_store.py pyproject.toml
git commit -m "[CUR-1081] Add comment compaction CLI and compact_file implementation"
```

---

## Task 11: Comment Loading in Viewer Startup

**Files:**
- Modify: `src/elspais/server/state.py` or viewer startup path
- Modify: `src/elspais/graph/comment_store.py` (if needed)

- [ ] **Step 1: Identify where the graph is loaded for the viewer**

Read the viewer startup code to find where `FederatedGraph` is constructed and passed to `AppState`. This is where `load_comment_index` + `promote_orphaned_comments` should be called per-repo.

- [ ] **Step 2: Add comment loading after graph build**

For each repo in the federated graph:
```python
from elspais.graph.comment_store import load_comment_index, promote_orphaned_comments

for entry in federated._repos.values():
    if entry.graph:
        idx = load_comment_index(entry.repo_root)
        promote_orphaned_comments(idx, entry.graph, entry.repo_root)
        entry.graph._comment_index = idx
```

- [ ] **Step 3: Verify comment loading on graph refresh**

The viewer's reload/refresh path should also re-load comments. Verify that the reload handler rebuilds comment indexes.

- [ ] **Step 4: Test end-to-end**

Start viewer, manually create a `.elspais/comments/` file, refresh, verify comments appear.

- [ ] **Step 5: Bump version and commit**

```bash
git add src/elspais/server/ pyproject.toml
git commit -m "[CUR-1081] Load comment index at viewer startup and refresh"
```

---

## Task 12: Documentation and Cleanup

**Files:**
- Modify: `docs/cli/` (add comments doc)
- Modify: `CLAUDE.md` (document comment system architecture)
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Create docs/cli/comments.md**

Document the `elspais comments compact` command and the `.elspais/comments/` directory structure.

- [ ] **Step 2: Update CLAUDE.md**

Add a section documenting:
- CommentIndex as annotation layer on TraceGraph
- JSONL storage in `.elspais/comments/`
- Comment API endpoints
- Promotion engine behavior

- [ ] **Step 3: Update CHANGELOG.md**

Add entry for the comment/review system feature.

- [ ] **Step 4: Run full test suite**

Run: `pytest -m "" tests/`
Expected: all PASS (unit + e2e)

- [ ] **Step 5: Bump version and commit**

```bash
git add docs/ CLAUDE.md CHANGELOG.md pyproject.toml
git commit -m "[CUR-1081] Add comment system documentation"
```
