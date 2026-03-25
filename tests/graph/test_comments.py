"""Tests for comment data models.

Validates REQ-d00226: CommentEvent and CommentThread data models.
"""

import pytest

from elspais.graph.comments import CommentEvent, CommentThread


class TestCommentEvent:
    """Validates REQ-d00226: CommentEvent frozen dataclass fields and immutability."""

    def test_REQ_d00226_A_create_comment_event(self):
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

    def test_REQ_d00226_A_frozen_immutability(self):
        """CommentEvent is immutable."""
        evt = CommentEvent(
            event="comment",
            id="c-20260320-a3f1b2",
            anchor="REQ-p00001",
            author="Alice",
            author_id="alice@co.org",
            date="2026-03-20",
            text="Hello",
        )
        with pytest.raises(AttributeError):
            evt.text = "Modified"

    def test_REQ_d00226_A_reply_event_fields(self):
        """Reply events have parent field."""
        evt = CommentEvent(
            event="reply",
            id="c-20260321-b4e2c3",
            anchor="REQ-p00001#A",
            author="Bob",
            author_id="bob@co.org",
            date="2026-03-21",
            text="Out of scope.",
            parent="c-20260320-a3f1b2",
        )
        assert evt.parent == "c-20260320-a3f1b2"

    def test_REQ_d00226_A_resolve_event_fields(self):
        """Resolve events have target and anchor, no text."""
        evt = CommentEvent(
            event="resolve",
            id="c-20260321-d6f4a5",
            anchor="REQ-p00001#A",
            author="Bob",
            author_id="bob@co.org",
            date="2026-03-21",
            target="c-20260320-a3f1b2",
        )
        assert evt.target == "c-20260320-a3f1b2"
        assert evt.text == ""

    def test_REQ_d00226_A_promote_event_fields(self):
        """Promote events have old/new anchor and reason."""
        evt = CommentEvent(
            event="promote",
            id="c-20260322-e7g5b6",
            anchor="REQ-p00001",
            author="system",
            author_id="system",
            date="2026-03-22",
            target="c-20260320-a3f1b2",
            old_anchor="REQ-p00001#D",
            new_anchor="REQ-p00001",
            reason="Assertion D deleted",
            from_file="spec/prd-auth.md.json",
        )
        assert evt.old_anchor == "REQ-p00001#D"
        assert evt.new_anchor == "REQ-p00001"

    def test_REQ_d00226_B_default_optional_fields(self):
        """Optional fields default to empty string."""
        evt = CommentEvent(
            event="comment",
            id="c-20260320-a3f1b2",
            anchor="REQ-p00001",
            author="Alice",
            author_id="alice@co.org",
            date="2026-03-20",
            text="Hello",
        )
        assert evt.parent == ""
        assert evt.target == ""
        assert evt.old_anchor == ""
        assert evt.new_anchor == ""
        assert evt.reason == ""
        assert evt.from_file == ""


class TestCommentThread:
    """Validates REQ-d00226: CommentThread assembly and defaults."""

    def test_REQ_d00226_D_thread_defaults_anchor(self):
        """Thread anchor defaults to root event's anchor."""
        root = CommentEvent(
            event="comment",
            id="c-20260320-a3f1b2",
            anchor="REQ-p00001#A",
            author="Alice",
            author_id="alice@co.org",
            date="2026-03-20",
            text="Hello",
        )
        thread = CommentThread(root=root)
        assert thread.anchor == "REQ-p00001#A"
        assert thread.resolved is False
        assert thread.promoted_from is None
        assert thread.replies == []

    def test_REQ_d00226_C_thread_with_replies(self):
        """Thread holds flat chronological replies."""
        root = CommentEvent(
            event="comment",
            id="c-20260320-a3f1b2",
            anchor="REQ-p00001#A",
            author="Alice",
            author_id="alice@co.org",
            date="2026-03-20",
            text="Question",
        )
        reply = CommentEvent(
            event="reply",
            id="c-20260321-b4e2c3",
            anchor="REQ-p00001#A",
            author="Bob",
            author_id="bob@co.org",
            date="2026-03-21",
            text="Answer",
            parent="c-20260320-a3f1b2",
        )
        thread = CommentThread(root=root, replies=[reply])
        assert len(thread.replies) == 1
        assert thread.replies[0].author == "Bob"

    def test_REQ_d00226_C_promoted_thread(self):
        """Thread tracks promotion metadata."""
        root = CommentEvent(
            event="comment",
            id="c-20260320-a3f1b2",
            anchor="REQ-p00001#D",
            author="Alice",
            author_id="alice@co.org",
            date="2026-03-20",
            text="Too tight for prod",
        )
        thread = CommentThread(
            root=root,
            anchor="REQ-p00001",
            promoted_from="REQ-p00001#D",
            promotion_reason="Assertion D deleted",
        )
        assert thread.anchor == "REQ-p00001"
        assert thread.promoted_from == "REQ-p00001#D"
