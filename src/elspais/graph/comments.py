"""Comment data models for the review system.

Comments are a parallel annotation layer on the graph, stored as
append-only JSONL files in .elspais/comments/. Models are frozen
(immutable) to match the append-only storage semantics.
"""

# Implements: REQ-d00226

from __future__ import annotations

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
