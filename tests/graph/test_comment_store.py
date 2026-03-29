"""Tests for comment JSONL I/O and thread assembly.

Validates REQ-d00228: Comment/review system storage layer.
"""

from pathlib import Path

from elspais.graph import GraphNode, NodeKind
from elspais.graph.builder import TraceGraph
from elspais.graph.comment_store import (
    append_event,
    assemble_threads,
    comment_file_for,
    compact_file,
    generate_comment_id,
    load_comment_index,
    load_events,
    parse_anchor,
    promote_orphaned_comments,
    update_anchors_on_rename,
    validate_anchor,
)
from elspais.graph.comments import CommentEvent, CommentIndex, CommentThread
from elspais.graph.relations import EdgeKind


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
    """Validates REQ-d00229-A: Anchor validation against live graph."""

    def test_REQ_d00229_A_valid_bare_node(self):
        graph = _build_simple_graph()
        assert validate_anchor("REQ-p00001", graph) is True

    def test_REQ_d00229_A_valid_assertion(self):
        graph = _build_simple_graph()
        assert validate_anchor("REQ-p00001#A", graph) is True

    def test_REQ_d00229_A_invalid_node(self):
        graph = _build_simple_graph()
        assert validate_anchor("REQ-p99999", graph) is False

    def test_REQ_d00229_A_invalid_assertion(self):
        graph = _build_simple_graph()
        assert validate_anchor("REQ-p00001#Z", graph) is False

    def test_REQ_d00229_A_valid_section(self):
        graph = _build_simple_graph()
        assert validate_anchor("REQ-p00001#section:Rationale", graph) is True

    def test_REQ_d00229_A_invalid_section(self):
        graph = _build_simple_graph()
        assert validate_anchor("REQ-p00001#section:Nonexistent", graph) is False

    def test_REQ_d00229_A_valid_edge(self):
        graph = _build_simple_graph()
        assert validate_anchor("REQ-p00001#edge:REQ-d00003", graph) is True

    def test_REQ_d00229_A_invalid_edge(self):
        graph = _build_simple_graph()
        assert validate_anchor("REQ-p00001#edge:REQ-d99999", graph) is False


class TestPromoteOrphanedComments:
    """Validates REQ-d00229-B: Orphaned comment promotion."""

    def test_REQ_d00229_B_valid_not_promoted(self, tmp_path):
        """Comments with valid anchors are left alone."""
        graph = _build_simple_graph()
        graph.repo_root = tmp_path
        idx = CommentIndex()
        thread = CommentThread(
            root=CommentEvent(
                event="comment",
                id="c1",
                anchor="REQ-p00001#A",
                author="Alice",
                author_id="alice@co.org",
                date="2026-03-20",
                text="OK",
            ),
        )
        idx.add_thread(thread, "spec/prd.md.json")
        events = promote_orphaned_comments(idx, graph, tmp_path)
        assert events == []
        assert idx.has_threads("REQ-p00001#A")

    def test_REQ_d00229_B_missing_assertion_promotes(self, tmp_path):
        """Comment on deleted assertion promotes to parent node."""
        graph = _build_simple_graph()
        graph.repo_root = tmp_path
        # Write the original comment file so promote can append
        f = tmp_path / ".elspais" / "comments" / "spec" / "prd.md.json"
        evt = CommentEvent(
            event="comment",
            id="c1",
            anchor="REQ-p00001#Z",
            author="Alice",
            author_id="alice@co.org",
            date="2026-03-20",
            text="Question about Z",
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

    def test_REQ_d00229_B_missing_node_orphaned(self, tmp_path):
        """Comment on deleted node with no ancestors becomes orphaned."""
        graph = _build_simple_graph()
        graph.repo_root = tmp_path
        f = tmp_path / ".elspais" / "comments" / "spec" / "prd.md.json"
        evt = CommentEvent(
            event="comment",
            id="c1",
            anchor="REQ-p99999",
            author="Alice",
            author_id="alice@co.org",
            date="2026-03-20",
            text="Where did this go?",
        )
        append_event(f, evt)
        idx = CommentIndex()
        idx.add_thread(CommentThread(root=evt), "spec/prd.md.json")
        events = promote_orphaned_comments(idx, graph, tmp_path)
        assert len(events) == 1
        assert list(idx.iter_orphaned())[0].root.id == "c1"


class TestUpdateAnchorsOnRename:
    """Validates REQ-d00229-C: Rename-triggered anchor updates."""

    def test_REQ_d00229_C_rename_updates_anchors(self, tmp_path):
        """Renaming a node updates all comment anchors referencing it."""
        idx = CommentIndex()
        evt = CommentEvent(
            event="comment",
            id="c1",
            anchor="REQ-p00001#A",
            author="Alice",
            author_id="alice@co.org",
            date="2026-03-20",
            text="Question",
        )
        idx.add_thread(CommentThread(root=evt), "spec/prd.md.json")
        # Also add a bare node comment
        evt2 = CommentEvent(
            event="comment",
            id="c2",
            anchor="REQ-p00001",
            author="Bob",
            author_id="bob@co.org",
            date="2026-03-21",
            text="Note",
        )
        idx.add_thread(CommentThread(root=evt2), "spec/prd.md.json")

        events = update_anchors_on_rename(idx, "REQ-p00001", "REQ-p00099", tmp_path)
        assert len(events) == 2
        assert idx.has_threads("REQ-p00099#A")
        assert idx.has_threads("REQ-p00099")
        assert not idx.has_threads("REQ-p00001#A")
        assert not idx.has_threads("REQ-p00001")


class TestCompactFile:
    """Validates REQ-d00235-A: compact_file strips resolved and collapses promotes."""

    def test_REQ_d00235_A_compact_removes_resolved(self, tmp_path):
        """Resolved thread (comment + resolve) is stripped; active comment survives."""
        path = tmp_path / "comments" / "spec.md.json"
        c1 = CommentEvent(
            event="comment",
            id="c1",
            anchor="REQ-p00001#A",
            author="Alice",
            author_id="a@x",
            date="2026-03-20",
            text="Q",
        )
        r1 = CommentEvent(
            event="resolve",
            id="r1",
            anchor="REQ-p00001#A",
            author="Bob",
            author_id="b@x",
            date="2026-03-21",
            target="c1",
        )
        c2 = CommentEvent(
            event="comment",
            id="c2",
            anchor="REQ-p00001#A",
            author="Carol",
            author_id="c@x",
            date="2026-03-22",
            text="Still open",
        )
        append_event(path, c1)
        append_event(path, r1)
        append_event(path, c2)

        removed = compact_file(path)
        assert removed == 2
        remaining = load_events(path)
        assert len(remaining) == 1
        assert remaining[0].id == "c2"

    def test_REQ_d00235_A_compact_collapses_promote_chains(self, tmp_path):
        """Multiple promotes for the same target collapse to keep only the final one."""
        path = tmp_path / "comments" / "spec.md.json"
        c1 = CommentEvent(
            event="comment",
            id="c1",
            anchor="REQ-p00001#D",
            author="Alice",
            author_id="a@x",
            date="2026-03-20",
            text="Q",
        )
        p1 = CommentEvent(
            event="promote",
            id="p1",
            anchor="REQ-p00001",
            author="system",
            author_id="system",
            date="2026-03-21",
            target="c1",
            old_anchor="REQ-p00001#D",
            new_anchor="REQ-p00001",
            reason="Assertion D deleted",
        )
        p2 = CommentEvent(
            event="promote",
            id="p2",
            anchor="REQ-p00002",
            author="system",
            author_id="system",
            date="2026-03-22",
            target="c1",
            old_anchor="REQ-p00001",
            new_anchor="REQ-p00002",
            reason="Node renamed",
        )
        append_event(path, c1)
        append_event(path, p1)
        append_event(path, p2)

        removed = compact_file(path)
        assert removed >= 1
        remaining = load_events(path)
        promotes = [e for e in remaining if e.event == "promote"]
        assert len(promotes) <= 1
        # The surviving promote should be the final one
        if promotes:
            assert promotes[0].id == "p2"

    def test_REQ_d00235_A_compact_empty_file(self, tmp_path):
        """compact_file on a non-existent path returns 0."""
        path = tmp_path / "nonexistent" / "comments.json"
        assert compact_file(path) == 0
