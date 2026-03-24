# Verifies: REQ-d00222-A+B+C
"""Tests for TermDictionary integration with TraceGraph and GraphBuilder.

Validates REQ-d00222-A+B+C: TraceGraph._terms field, GraphBuilder definition_block
handling, and defined_in ancestor resolution.
"""

from pathlib import Path

from elspais.graph import NodeKind
from elspais.graph.builder import GraphBuilder, TraceGraph
from elspais.graph.GraphNode import GraphNode
from elspais.graph.parsers import ParsedContent
from elspais.graph.terms import TermDictionary


def _make_definition_block(
    term: str,
    definition: str,
    line: int = 10,
    *,
    collection: bool = False,
    indexed: bool = True,
) -> ParsedContent:
    """Create a definition_block ParsedContent for testing."""
    return ParsedContent(
        content_type="definition_block",
        start_line=line,
        end_line=line + 2,
        raw_text=f"{term}\n: {definition}",
        parsed_data={
            "term": term,
            "definition": definition,
            "collection": collection,
            "indexed": indexed,
            "line": line,
        },
    )


def _make_file_node(rel_path: str = "spec/test.md") -> GraphNode:
    """Create a FILE node for testing."""
    node = GraphNode(id=f"file:{rel_path}", kind=NodeKind.FILE)
    node.set_field("file_type", "SPEC")
    node.set_field("relative_path", rel_path)
    node.set_field("absolute_path", f"/test/repo/{rel_path}")
    node.set_field("repo", None)
    return node


def _make_requirement_content(
    req_id: str = "REQ-p00001",
    title: str = "Test Requirement",
    level: str = "PRD",
) -> ParsedContent:
    """Create a requirement ParsedContent for testing."""
    return ParsedContent(
        content_type="requirement",
        start_line=1,
        end_line=8,
        raw_text="...",
        parsed_data={
            "id": req_id,
            "title": title,
            "level": level,
            "status": "Active",
            "implements": [],
            "assertions": [],
        },
    )


class TestTermsIntegration:
    """Tests for TermDictionary integration into TraceGraph and GraphBuilder.

    Validates REQ-d00222-A+B+C:
    - A: TraceGraph._terms field and GraphBuilder definition_block handling
    - B: defined_in ancestor resolution
    - C: FederatedGraph merge (deferred)
    """

    # --- REQ-d00222-A tests ---

    def test_REQ_d00222_A_tracegraph_has_terms(self):
        """TraceGraph() has _terms attribute of type TermDictionary."""
        graph = TraceGraph(repo_root=Path("."))
        assert hasattr(graph, "_terms"), "TraceGraph must have _terms attribute"
        assert isinstance(graph._terms, TermDictionary), (
            f"_terms must be TermDictionary, got {type(graph._terms)}"
        )

    def test_REQ_d00222_A_builder_creates_remainder_for_definition(self):
        """GraphBuilder.add_parsed_content with content_type='definition_block'
        creates a REMAINDER node with content_type='definition_block' field."""
        builder = GraphBuilder(repo_root=Path("/test/repo"))
        content = _make_definition_block("Electronic Record", "Any combination of text")

        builder.add_parsed_content(content)
        graph = builder.build()

        # Find the REMAINDER node created for the definition
        remainder_nodes = list(graph.iter_by_kind(NodeKind.REMAINDER))
        assert len(remainder_nodes) >= 1, (
            "Expected at least one REMAINDER node for definition_block"
        )

        # At least one should have content_type="definition_block"
        def_nodes = [
            n for n in remainder_nodes
            if n.get_field("content_type") == "definition_block"
        ]
        assert len(def_nodes) == 1, (
            f"Expected exactly one REMAINDER with content_type='definition_block', "
            f"found {len(def_nodes)}"
        )

    def test_REQ_d00222_A_builder_populates_terms(self):
        """After building, the graph's _terms contains the defined term."""
        builder = GraphBuilder(repo_root=Path("/test/repo"))
        content = _make_definition_block("Electronic Record", "Any combination of text")

        builder.add_parsed_content(content)
        graph = builder.build()

        entry = graph._terms.lookup("Electronic Record")
        assert entry is not None, "Term 'Electronic Record' should be in _terms"
        assert entry.term == "Electronic Record"
        assert entry.definition == "Any combination of text"

    def test_REQ_d00222_A_collection_flag_preserved(self):
        """A definition_block with collection=True has that flag in _terms."""
        builder = GraphBuilder(repo_root=Path("/test/repo"))
        content = _make_definition_block(
            "Validation Activity",
            "An activity that validates something",
            collection=True,
        )

        builder.add_parsed_content(content)
        graph = builder.build()

        entry = graph._terms.lookup("Validation Activity")
        assert entry is not None, "Term should be in _terms"
        assert entry.collection is True, "collection flag should be True"

    # --- REQ-d00222-B tests ---

    def test_REQ_d00222_B_defined_in_points_to_file(self):
        """For file-level definitions, defined_in is the FILE node ID."""
        builder = GraphBuilder(repo_root=Path("/test/repo"))
        file_node = _make_file_node("spec/glossary.md")
        builder.register_file_node(file_node)

        content = _make_definition_block("Audit Trail", "A chronological record", line=5)
        builder.add_parsed_content(content, file_node=file_node)
        graph = builder.build()

        entry = graph._terms.lookup("Audit Trail")
        assert entry is not None, "Term should be in _terms"
        assert entry.defined_in == "file:spec/glossary.md", (
            f"defined_in should be FILE node ID, got '{entry.defined_in}'"
        )

    def test_REQ_d00222_B_defined_in_points_to_requirement(self):
        """For requirement-level definitions, defined_in is the requirement ID."""
        builder = GraphBuilder(repo_root=Path("/test/repo"))
        file_node = _make_file_node("spec/reqs.md")
        builder.register_file_node(file_node)

        # Add a requirement that contains definitions in its parsed_data
        req_content = ParsedContent(
            content_type="requirement",
            start_line=1,
            end_line=12,
            raw_text="...",
            parsed_data={
                "id": "REQ-p00001",
                "title": "Glossary Requirement",
                "level": "PRD",
                "status": "Active",
                "implements": [],
                "assertions": [],
                "definitions": [
                    {
                        "term": "Electronic Signature",
                        "definition": "A computer data compilation",
                        "collection": False,
                        "indexed": True,
                        "line": 5,
                    }
                ],
            },
        )
        builder.add_parsed_content(req_content, file_node=file_node)
        graph = builder.build()

        entry = graph._terms.lookup("Electronic Signature")
        assert entry is not None, "Term should be in _terms"
        assert entry.defined_in == "REQ-p00001", (
            f"defined_in should be requirement ID, got '{entry.defined_in}'"
        )
