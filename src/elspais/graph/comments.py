"""Comment data models for the review system.

Comments are a parallel annotation layer on the graph, stored as
append-only JSONL files in .elspais/comments/. Models are frozen
(immutable) to match the append-only storage semantics.
"""

# Implements: REQ-d00226
# Implements: REQ-d00227

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


class CommentIndex:
    """In-memory index of active comment threads, keyed by anchor.

    Follows the same pattern as TermDictionary -- a simple dict-based
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

    def find_thread(self, comment_id: str) -> tuple[str, CommentThread] | None:
        """Find a thread containing a comment by its ID.

        Searches root IDs and reply IDs. Returns (anchor, thread) or None.
        """
        for anchor, threads in self._threads.items():
            for thread in threads:
                if thread.root.id == comment_id:
                    return anchor, thread
                for reply in thread.replies:
                    if reply.id == comment_id:
                        return anchor, thread
        return None

    def remove_thread(self, comment_id: str) -> str | None:
        """Remove a thread by its root comment ID.

        Returns the anchor of the removed thread, or None if not found.
        """
        for anchor in list(self._threads):
            threads = self._threads[anchor]
            for i, thread in enumerate(threads):
                if thread.root.id == comment_id:
                    threads.pop(i)
                    if not threads:
                        del self._threads[anchor]
                    return anchor
        return None

    def __len__(self) -> int:
        return sum(len(ts) for ts in self._threads.values())
