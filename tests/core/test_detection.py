# Validates REQ-p00002-B
# elspais: expected-broken-links 1
"""Tests for TraceGraph detection capabilities (orphans, broken references)."""
from __future__ import annotations

from elspais.graph import BrokenReference
from elspais.graph.builder import GraphBuilder
from elspais.graph.parsers import ParsedContent
from tests.fixtures import fake_reqs


def make_req(
    req_id: str,
    title: str = "Test",
    level: str = "PRD",
    implements: list[str] | None = None,
    refines: list[str] | None = None,
    assertions: list[dict] | None = None,
    start_line: int = 1,
    end_line: int = 5,
) -> ParsedContent:
    """Helper to create a requirement ParsedContent."""
    return ParsedContent(
        content_type="requirement",
        parsed_data={
            "id": req_id,
            "title": title,
            "level": level,
            "status": "Active",
            "assertions": assertions or [],
            "implements": implements or [],
            "refines": refines or [],
        },
        start_line=start_line,
        end_line=end_line,
        raw_text=f"## {req_id}: {title}",
    )


class TestOrphanDetection:
    """Tests for orphaned node detection."""

    def test_no_orphans_when_all_linked(self):
        """Requirements with valid implements links are not orphans."""
        builder = GraphBuilder()
        builder.add_parsed_content(make_req("REQ-p00001", "Parent", "PRD"))
        builder.add_parsed_content(
            make_req("REQ-o00001", "Child", "OPS", implements=["REQ-p00001"])
        )

        graph = builder.build()

        assert not graph.has_orphans()
        assert graph.orphan_count() == 0
        assert list(graph.orphaned_nodes()) == []

    def test_REQ_d00071_B_parentless_reqs_are_roots(self):
        """REQ-d00071-B: Parentless requirements are always roots, even without children."""
        builder = GraphBuilder()
        builder.add_parsed_content(make_req("REQ-p00001", "Parent", "PRD"))
        builder.add_parsed_content(make_req("REQ-o00001", "Standalone OPS", "OPS"))

        graph = builder.build()

        # Both are parentless REQUIREMENT nodes → roots
        assert graph.root_count() == 2
        assert graph.orphan_count() == 0

    def test_REQ_d00071_B_broken_ref_req_is_still_root(self):
        """REQ-d00071-B: Requirement with broken implements is still a root."""
        builder = GraphBuilder()
        builder.add_parsed_content(make_req("REQ-p00001", "Parent", "PRD"))
        builder.add_parsed_content(
            make_req(
                "REQ-o00001", "Broken child", "OPS", implements=[fake_reqs.FAKE_NONEXISTENT_REQ]
            )
        )

        graph = builder.build()

        # Child tried to link but target doesn't exist
        assert graph.has_broken_references()
        # Both parentless REQs are roots (broken ref doesn't establish a parent)
        assert graph.root_count() == 2
        assert graph.orphan_count() == 0


class TestBrokenReferenceDetection:
    """Tests for broken reference detection."""

    def test_no_broken_refs_valid_graph(self):
        """Valid graph has no broken references."""
        builder = GraphBuilder()
        builder.add_parsed_content(make_req("REQ-p00001", "Parent", "PRD"))
        builder.add_parsed_content(
            make_req("REQ-o00001", "Child", "OPS", implements=["REQ-p00001"])
        )

        graph = builder.build()

        assert not graph.has_broken_references()
        assert graph.broken_references() == []

    def test_broken_ref_implements(self):
        """Broken implements reference is detected."""
        builder = GraphBuilder()
        builder.add_parsed_content(
            make_req("REQ-o00001", "Broken", "OPS", implements=[fake_reqs.FAKE_NONEXISTENT_REQ])
        )

        graph = builder.build()

        assert graph.has_broken_references()
        broken = graph.broken_references()
        assert len(broken) == 1
        assert broken[0].source_id == "REQ-o00001"
        assert broken[0].target_id == fake_reqs.FAKE_NONEXISTENT_REQ
        assert broken[0].edge_kind == "implements"

    def test_broken_ref_refines(self):
        """Broken refines reference is detected."""
        builder = GraphBuilder()
        builder.add_parsed_content(
            make_req(
                "REQ-o00001", "Broken refines", "OPS", refines=[fake_reqs.FAKE_NONEXISTENT_REQ]
            )
        )

        graph = builder.build()

        assert graph.has_broken_references()
        broken = graph.broken_references()
        assert len(broken) == 1
        assert broken[0].edge_kind == "refines"

    def test_multiple_broken_refs(self):
        """Multiple broken references are all detected."""
        builder = GraphBuilder()
        builder.add_parsed_content(
            make_req("REQ-o00001", "First", "OPS", implements=["REQ-MISSING1"])
        )
        builder.add_parsed_content(
            make_req("REQ-o00002", "Second", "OPS", implements=["REQ-MISSING2"])
        )

        graph = builder.build()

        assert graph.has_broken_references()
        broken = graph.broken_references()
        assert len(broken) == 2
        target_ids = {b.target_id for b in broken}
        assert target_ids == {"REQ-MISSING1", "REQ-MISSING2"}

    def test_broken_ref_str(self):
        """BrokenReference has readable string representation."""
        ref = BrokenReference(
            source_id="REQ-o00001",
            target_id="REQ-MISSING",
            edge_kind="implements",
        )
        s = str(ref)
        assert "REQ-o00001" in s
        assert "REQ-MISSING" in s
        assert "implements" in s
        assert "missing" in s


class TestCodeAndTestOrphans:
    """Tests for code and test node orphan detection."""

    def test_code_ref_to_nonexistent_req(self):
        """Code reference to non-existent requirement creates broken ref."""
        builder = GraphBuilder()

        class SourceCtx:
            source_id = "src/main.py"

        code_content = ParsedContent(
            content_type="code_ref",
            parsed_data={"implements": [fake_reqs.FAKE_NONEXISTENT_REQ]},
            start_line=42,
            end_line=42,
            raw_text=fake_reqs.CODE_RAW_TEXT_NONEXISTENT,
        )
        code_content.source_context = SourceCtx()
        builder.add_parsed_content(code_content)

        graph = builder.build()

        assert graph.has_broken_references()
        broken = graph.broken_references()
        assert len(broken) == 1
        assert broken[0].target_id == fake_reqs.FAKE_NONEXISTENT_REQ
        assert broken[0].edge_kind == "implements"

    def test_test_ref_to_nonexistent_req(self):
        """Test reference to non-existent requirement creates broken ref."""
        builder = GraphBuilder()

        class SourceCtx:
            source_id = "tests/test_main.py"

        test_content = ParsedContent(
            content_type="test_ref",
            parsed_data={"validates": [fake_reqs.FAKE_NONEXISTENT_REQ]},
            start_line=100,
            end_line=100,
            raw_text=fake_reqs.TEST_RAW_TEXT_NONEXISTENT,
        )
        test_content.source_context = SourceCtx()
        builder.add_parsed_content(test_content)

        graph = builder.build()

        assert graph.has_broken_references()
        broken = graph.broken_references()
        assert len(broken) == 1
        assert broken[0].target_id == fake_reqs.FAKE_NONEXISTENT_REQ
        assert broken[0].edge_kind == "validates"


class TestIntegration:
    """Integration tests for detection with real-world scenarios."""

    def test_mixed_valid_and_broken(self):
        """Graph with both valid links and broken references."""
        builder = GraphBuilder()
        builder.add_parsed_content(make_req("REQ-p00001", "Valid Parent", "PRD"))
        builder.add_parsed_content(
            make_req("REQ-o00001", "Valid Child", "OPS", implements=["REQ-p00001"])
        )
        builder.add_parsed_content(
            make_req(
                "REQ-o00002", "Broken Child", "OPS", implements=[fake_reqs.FAKE_NONEXISTENT_REQ]
            )
        )

        graph = builder.build()

        # Should have one broken reference
        assert graph.has_broken_references()
        assert len(graph.broken_references()) == 1

        # Valid child should be linked
        valid_node = graph.find_by_id("REQ-o00001")
        assert valid_node is not None
        assert valid_node.parent_count() == 1

        # Broken child should have no parent
        broken_node = graph.find_by_id("REQ-o00002")
        assert broken_node is not None
        assert broken_node.parent_count() == 0

    def test_real_graph_detection(self):
        """Test detection with a realistic graph structure."""
        from elspais.graph.factory import build_graph

        graph = build_graph()

        # These methods should work on a real graph
        orphan_count = graph.orphan_count()
        broken_refs = graph.broken_references()

        # Results may vary by repo state, but methods should work
        assert isinstance(orphan_count, int)
        assert isinstance(broken_refs, list)
        for ref in broken_refs:
            assert isinstance(ref, BrokenReference)
