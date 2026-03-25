"""Tests for comment data models.

Validates REQ-d00226: CommentEvent and CommentThread data models.
"""

import pytest

from elspais.graph.comments import CommentEvent, CommentIndex, CommentThread


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


class TestCommentIndex:
    """Validates REQ-d00227: CommentIndex in-memory index."""

    def _make_thread(self, anchor, comment_id="c-20260320-a3f1b2"):
        root = CommentEvent(
            event="comment",
            id=comment_id,
            anchor=anchor,
            author="Alice",
            author_id="alice@co.org",
            date="2026-03-20",
            text="A comment",
        )
        return CommentThread(root=root)

    def test_REQ_d00227_A_empty_index(self):
        """Empty index returns zero counts and empty iterators."""
        idx = CommentIndex()
        assert idx.thread_count("REQ-p00001") == 0
        assert not idx.has_threads("REQ-p00001")
        assert list(idx.iter_threads("REQ-p00001")) == []

    def test_REQ_d00227_A_add_and_retrieve(self):
        """Add a thread and retrieve it by anchor."""
        idx = CommentIndex()
        thread = self._make_thread("REQ-p00001#A")
        idx.add_thread(thread, source_file="spec/prd.md.json")
        assert idx.thread_count("REQ-p00001#A") == 1
        assert idx.has_threads("REQ-p00001#A")
        assert list(idx.iter_threads("REQ-p00001#A"))[0].root.text == "A comment"

    def test_REQ_d00227_A_len(self):
        """__len__ returns total thread count across all anchors."""
        idx = CommentIndex()
        assert len(idx) == 0
        idx.add_thread(self._make_thread("REQ-p00001#A", "c1"), "f.json")
        assert len(idx) == 1
        idx.add_thread(self._make_thread("REQ-p00001#B", "c2"), "f.json")
        assert len(idx) == 2
        idx.add_thread(self._make_thread("REQ-p00001#A", "c3"), "f.json")
        assert len(idx) == 3

    def test_REQ_d00227_B_iter_all_anchors_for_node(self):
        """iter_all_anchors_for_node matches exact node_id and node_id#fragment patterns."""
        idx = CommentIndex()
        idx.add_thread(self._make_thread("REQ-p00001", "c1"), "f.json")
        idx.add_thread(self._make_thread("REQ-p00001#A", "c2"), "f.json")
        idx.add_thread(self._make_thread("REQ-p00001#section:Rationale", "c3"), "f.json")
        idx.add_thread(self._make_thread("REQ-p00002#A", "c4"), "f.json")
        anchors = sorted(idx.iter_all_anchors_for_node("REQ-p00001"))
        assert anchors == [
            "REQ-p00001",
            "REQ-p00001#A",
            "REQ-p00001#section:Rationale",
        ]

    def test_REQ_d00227_A_orphaned_threads(self):
        """Orphaned threads are stored and retrievable."""
        idx = CommentIndex()
        thread = self._make_thread("REQ-deleted#A")
        idx.add_orphaned(thread)
        assert list(idx.iter_orphaned()) == [thread]

    def test_REQ_d00227_A_source_file_tracking(self):
        """source_file_for returns the file a thread's anchor was loaded from."""
        idx = CommentIndex()
        thread = self._make_thread("REQ-p00001#A")
        idx.add_thread(thread, source_file="spec/prd.md.json")
        assert idx.source_file_for("REQ-p00001#A") == "spec/prd.md.json"

    def test_REQ_d00227_C_merge_indexes(self):
        """Merging indexes combines threads from both, following TermDictionary pattern."""
        idx1 = CommentIndex()
        idx1.add_thread(self._make_thread("REQ-p00001#A", "c1"), "f1.json")
        idx2 = CommentIndex()
        idx2.add_thread(self._make_thread("REQ-d00001#B", "c2"), "f2.json")
        idx1.merge(idx2)
        assert idx1.has_threads("REQ-p00001#A")
        assert idx1.has_threads("REQ-d00001#B")
