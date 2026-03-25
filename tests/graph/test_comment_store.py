"""Tests for comment JSONL I/O and thread assembly.

Validates REQ-d00228: Comment/review system storage layer.
"""

from pathlib import Path

from elspais.graph.comment_store import (
    append_event,
    assemble_threads,
    comment_file_for,
    generate_comment_id,
    load_comment_index,
    load_events,
    parse_anchor,
)
from elspais.graph.comments import CommentEvent


class TestParseAnchor:
    """Validates REQ-d00228: Anchor string parsing."""

    def test_REQ_d00228_A_bare_requirement(self):
        assert parse_anchor("REQ-p00001") == ("REQ-p00001", None, None)

    def test_REQ_d00228_A_assertion_fragment(self):
        assert parse_anchor("REQ-p00001#A") == ("REQ-p00001", "assertion", "A")

    def test_REQ_d00228_A_section_fragment(self):
        assert parse_anchor("REQ-p00001#section:Rationale") == (
            "REQ-p00001",
            "section",
            "Rationale",
        )

    def test_REQ_d00228_A_edge_fragment(self):
        assert parse_anchor("REQ-p00001#edge:REQ-d00003") == (
            "REQ-p00001",
            "edge",
            "REQ-d00003",
        )

    def test_REQ_d00228_A_journey_bare(self):
        assert parse_anchor("JNY-001") == ("JNY-001", None, None)

    def test_REQ_d00228_A_journey_section(self):
        assert parse_anchor("JNY-001#section:Setup") == (
            "JNY-001",
            "section",
            "Setup",
        )

    def test_REQ_d00228_A_journey_edge(self):
        assert parse_anchor("JNY-001#edge:REQ-p00001") == (
            "JNY-001",
            "edge",
            "REQ-p00001",
        )


class TestGenerateCommentId:
    """Validates REQ-d00228: Comment ID generation."""

    def test_REQ_d00228_B_format(self):
        cid = generate_comment_id("REQ-p00001#A", "alice@co.org", "2026-03-20", "Hello")
        assert cid.startswith("c-20260320-")
        assert len(cid) == len("c-20260320-") + 6

    def test_REQ_d00228_B_deterministic(self):
        a = generate_comment_id("REQ-p00001#A", "alice@co.org", "2026-03-20", "Hello")
        b = generate_comment_id("REQ-p00001#A", "alice@co.org", "2026-03-20", "Hello")
        assert a == b

    def test_REQ_d00228_B_different_content(self):
        a = generate_comment_id("REQ-p00001#A", "alice@co.org", "2026-03-20", "Hello")
        b = generate_comment_id("REQ-p00001#A", "alice@co.org", "2026-03-20", "World")
        assert a != b


class TestCommentFileFor:
    """Validates REQ-d00228: JSONL file path resolution."""

    def test_REQ_d00228_E_spec_file(self):
        result = comment_file_for(Path("/repo"), "spec/prd-auth.md")
        assert result == Path("/repo/.elspais/comments/spec/prd-auth.md.json")

    def test_REQ_d00228_E_journey_file(self):
        result = comment_file_for(Path("/repo"), "journeys/onboarding.md")
        assert result == Path("/repo/.elspais/comments/journeys/onboarding.md.json")


class TestJsonlIO:
    """Validates REQ-d00228: JSONL file reading and writing."""

    def test_REQ_d00228_C_load_missing(self, tmp_path):
        """Loading a non-existent file returns empty list."""
        assert load_events(tmp_path / "nope.json") == []

    def test_REQ_d00228_C_append_and_load(self, tmp_path):
        """Append events then load them back."""
        path = tmp_path / "comments" / "spec.md.json"
        evt = CommentEvent(
            event="comment",
            id="c-20260320-a3f1b2",
            anchor="REQ-p00001#A",
            author="Alice",
            author_id="alice@co.org",
            date="2026-03-20",
            text="Hello",
        )
        append_event(path, evt)
        events = load_events(path)
        assert len(events) == 1
        assert events[0].id == "c-20260320-a3f1b2"
        assert events[0].text == "Hello"

    def test_REQ_d00228_C_creates_dirs(self, tmp_path):
        """append_event creates directories if needed."""
        path = tmp_path / "deep" / "nested" / "file.json"
        evt = CommentEvent(
            event="comment",
            id="c1",
            anchor="REQ-p00001",
            author="A",
            author_id="a@x",
            date="2026-03-20",
            text="Hi",
        )
        append_event(path, evt)
        assert path.exists()

    def test_REQ_d00228_C_multiple_appends(self, tmp_path):
        """Multiple appends produce multiple lines."""
        path = tmp_path / "test.json"
        for i in range(3):
            evt = CommentEvent(
                event="comment",
                id=f"c{i}",
                anchor="REQ-p00001",
                author="A",
                author_id="a@x",
                date="2026-03-20",
                text=f"msg{i}",
            )
            append_event(path, evt)
        events = load_events(path)
        assert len(events) == 3


class TestAssembleThreads:
    """Validates REQ-d00228: Thread assembly from raw events."""

    def test_REQ_d00228_D_single_comment(self):
        """One comment event produces one thread."""
        events = [
            CommentEvent(
                event="comment",
                id="c1",
                anchor="REQ-p00001#A",
                author="Alice",
                author_id="alice@co.org",
                date="2026-03-20",
                text="Question",
            ),
        ]
        threads = assemble_threads(events)
        assert len(threads) == 1
        assert threads[0].root.id == "c1"
        assert threads[0].resolved is False

    def test_REQ_d00228_D_reply(self):
        """Reply attaches to parent thread."""
        events = [
            CommentEvent(
                event="comment",
                id="c1",
                anchor="REQ-p00001#A",
                author="Alice",
                author_id="alice@co.org",
                date="2026-03-20",
                text="Question",
            ),
            CommentEvent(
                event="reply",
                id="c2",
                anchor="REQ-p00001#A",
                author="Bob",
                author_id="bob@co.org",
                date="2026-03-21",
                text="Answer",
                parent="c1",
            ),
        ]
        threads = assemble_threads(events)
        assert len(threads) == 1
        assert len(threads[0].replies) == 1
        assert threads[0].replies[0].text == "Answer"

    def test_REQ_d00228_D_resolved_excluded(self):
        """Resolved threads are filtered out."""
        events = [
            CommentEvent(
                event="comment",
                id="c1",
                anchor="REQ-p00001#A",
                author="Alice",
                author_id="alice@co.org",
                date="2026-03-20",
                text="Question",
            ),
            CommentEvent(
                event="resolve",
                id="r1",
                anchor="REQ-p00001#A",
                author="Bob",
                author_id="bob@co.org",
                date="2026-03-21",
                target="c1",
            ),
        ]
        threads = assemble_threads(events)
        assert len(threads) == 0

    def test_REQ_d00228_D_promoted(self):
        """Promote event updates thread anchor and metadata."""
        events = [
            CommentEvent(
                event="comment",
                id="c1",
                anchor="REQ-p00001#D",
                author="Alice",
                author_id="alice@co.org",
                date="2026-03-20",
                text="Too tight",
            ),
            CommentEvent(
                event="promote",
                id="p1",
                anchor="REQ-p00001",
                author="system",
                author_id="system",
                date="2026-03-22",
                target="c1",
                old_anchor="REQ-p00001#D",
                new_anchor="REQ-p00001",
                reason="Assertion D deleted",
            ),
        ]
        threads = assemble_threads(events)
        assert len(threads) == 1
        assert threads[0].anchor == "REQ-p00001"
        assert threads[0].promoted_from == "REQ-p00001#D"
        assert threads[0].promotion_reason == "Assertion D deleted"

    def test_REQ_d00228_D_multiple_threads(self):
        """Multiple top-level comments on same anchor produce separate threads."""
        events = [
            CommentEvent(
                event="comment",
                id="c1",
                anchor="REQ-p00001#A",
                author="Alice",
                author_id="alice@co.org",
                date="2026-03-20",
                text="First",
            ),
            CommentEvent(
                event="comment",
                id="c2",
                anchor="REQ-p00001#A",
                author="Bob",
                author_id="bob@co.org",
                date="2026-03-21",
                text="Second",
            ),
        ]
        threads = assemble_threads(events)
        assert len(threads) == 2


class TestLoadCommentIndex:
    """Validates REQ-d00228: Loading full CommentIndex from disk."""

    def test_REQ_d00228_C_empty_repo(self, tmp_path):
        """No .elspais/comments dir returns empty index."""
        idx = load_comment_index(tmp_path)
        assert len(idx) == 0

    def test_REQ_d00228_C_multiple_files(self, tmp_path):
        """Index aggregates threads from all JSONL files."""
        comments_dir = tmp_path / ".elspais" / "comments"
        f1 = comments_dir / "spec" / "prd.md.json"
        f2 = comments_dir / "spec" / "dev.md.json"
        evt1 = CommentEvent(
            event="comment",
            id="c1",
            anchor="REQ-p00001#A",
            author="Alice",
            author_id="alice@co.org",
            date="2026-03-20",
            text="Q1",
        )
        evt2 = CommentEvent(
            event="comment",
            id="c2",
            anchor="REQ-d00001#B",
            author="Bob",
            author_id="bob@co.org",
            date="2026-03-21",
            text="Q2",
        )
        append_event(f1, evt1)
        append_event(f2, evt2)
        idx = load_comment_index(tmp_path)
        assert idx.has_threads("REQ-p00001#A")
        assert idx.has_threads("REQ-d00001#B")
        assert len(idx) == 2
