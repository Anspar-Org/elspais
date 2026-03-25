"""Comment JSONL I/O, thread assembly, promotion, and compaction.

Handles reading/writing JSONL comment files in .elspais/comments/.
All file I/O is isolated here -- comments.py contains only data models.
"""

# Implements: REQ-d00228

from __future__ import annotations

import json
from pathlib import Path

from elspais.graph.comments import CommentEvent, CommentIndex, CommentThread
from elspais.utilities.hasher import calculate_hash

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
        return (node_id, "section", fragment[len("section:") :])
    if fragment.startswith("edge:"):
        return (node_id, "edge", fragment[len("edge:") :])
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
