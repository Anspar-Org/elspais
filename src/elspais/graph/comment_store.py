"""Comment JSONL I/O, thread assembly, promotion, and compaction.

Handles reading/writing JSONL comment files in .elspais/comments/.
All file I/O is isolated here -- comments.py contains only data models.
"""

# Implements: REQ-d00228
# Implements: REQ-d00229

from __future__ import annotations

import json
from datetime import date as date_type
from pathlib import Path
from typing import TYPE_CHECKING

from elspais.graph.comments import CommentEvent, CommentIndex, CommentThread
from elspais.graph.relations import EdgeKind
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
        a for a in list(index._threads.keys()) if a == old_id or a.startswith(old_prefix)
    ]

    for old_anchor in matching_anchors:
        # Compute new anchor
        if old_anchor == old_id:
            new_anchor = new_id
        else:
            fragment = old_anchor[len(old_id) :]  # includes the #
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


def compact_file(path: Path) -> int:
    """Rewrite a JSONL comment file, stripping resolved threads and collapsing promote chains.

    Resolved threads: all events belonging to a resolved thread (root comment,
    replies, and the resolve event itself) are removed entirely.

    Promote chains: when multiple promote events target the same comment,
    only the final (last) promote is kept.

    Returns the number of events removed.

    Implements: REQ-d00235-A
    """
    events = load_events(path)
    if not events:
        return 0

    original_count = len(events)

    # Identify resolved thread root IDs
    resolved_ids: set[str] = set()
    for evt in events:
        if evt.event == "resolve":
            if evt.target:
                resolved_ids.add(evt.target)

    # Collect IDs belonging to resolved threads (root + replies + resolve events)
    resolved_event_ids: set[str] = set()
    for evt in events:
        if evt.event == "comment" and evt.id in resolved_ids:
            resolved_event_ids.add(evt.id)
        elif evt.event == "reply" and evt.parent in resolved_ids:
            resolved_event_ids.add(evt.id)
        elif evt.event == "resolve" and evt.target in resolved_ids:
            resolved_event_ids.add(evt.id)

    # Strip resolved thread events
    kept = [e for e in events if e.id not in resolved_event_ids]

    # Collapse promote chains: for each target, keep only the last promote
    last_promote: dict[str, int] = {}  # target -> last index in kept list
    for i, evt in enumerate(kept):
        if evt.event == "promote" and evt.target:
            last_promote[evt.target] = i

    final_indices = set(last_promote.values())
    compacted = [
        e
        for i, e in enumerate(kept)
        if not (e.event == "promote" and e.target and i not in final_indices)
    ]

    removed = original_count - len(compacted)
    if removed > 0:
        # Rewrite the file
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for evt in compacted:
                f.write(json.dumps(_event_to_dict(evt), separators=(",", ":")) + "\n")

    return removed
