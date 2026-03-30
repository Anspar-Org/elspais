# Verifies: REQ-d00222-A+B+C+D, REQ-d00220-E
# Implements: REQ-d00237, REQ-d00238, REQ-d00240
"""Tests for TermDictionary integration with TraceGraph and GraphBuilder.

Validates REQ-d00222-A+B+C: TraceGraph._terms field, GraphBuilder definition_block
handling, and defined_in ancestor resolution.
Validates REQ-d00220-E: TermRef.wrong_marking field.
Validates REQ-d00237+d00238+d00240: Full pipeline definitions -> scan -> health checks.
"""

from pathlib import Path
from unittest.mock import MagicMock

from elspais.commands.health import (
    HealthCheck,
    check_term_unused,
    check_unmarked_usage,
    run_term_checks,
)
from elspais.graph import NodeKind
from elspais.graph.builder import GraphBuilder, TraceGraph
from elspais.graph.GraphNode import FileType, GraphNode
from elspais.graph.parsers import ParsedContent
from elspais.graph.term_scanner import scan_graph
from elspais.graph.terms import TermDictionary, TermEntry, TermRef


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
        assert isinstance(
            graph._terms, TermDictionary
        ), f"_terms must be TermDictionary, got {type(graph._terms)}"

    def test_REQ_d00222_A_builder_creates_remainder_for_definition(self):
        """GraphBuilder.add_parsed_content with content_type='definition_block'
        creates a REMAINDER node with content_type='definition_block' field."""
        builder = GraphBuilder(repo_root=Path("/test/repo"))
        content = _make_definition_block("Electronic Record", "Any combination of text")

        builder.add_parsed_content(content)
        graph = builder.build()

        # Find the REMAINDER node created for the definition
        remainder_nodes = list(graph.iter_by_kind(NodeKind.REMAINDER))
        assert (
            len(remainder_nodes) >= 1
        ), "Expected at least one REMAINDER node for definition_block"

        # At least one should have content_type="definition_block"
        def_nodes = [
            n for n in remainder_nodes if n.get_field("content_type") == "definition_block"
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
        assert (
            entry.defined_in == "file:spec/glossary.md"
        ), f"defined_in should be FILE node ID, got '{entry.defined_in}'"

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
        assert (
            entry.defined_in == "REQ-p00001"
        ), f"defined_in should be requirement ID, got '{entry.defined_in}'"


class TestTermRefWrongMarking:
    """Validates REQ-d00220-E: TermRef.wrong_marking field."""

    def test_REQ_d00220_E_wrong_marking_defaults_empty(self) -> None:
        """TermRef.wrong_marking defaults to empty string."""
        ref = TermRef(node_id="REQ-p00001", namespace="CORE", marked=True, line=10)
        assert ref.wrong_marking == ""

    def test_REQ_d00220_E_wrong_marking_records_delimiter(self) -> None:
        """TermRef.wrong_marking records the incorrect delimiter used."""
        ref = TermRef(
            node_id="REQ-p00001",
            namespace="CORE",
            marked=False,
            line=10,
            wrong_marking="__",
        )
        assert ref.wrong_marking == "__"
        assert ref.marked is False

    def test_REQ_d00220_E_wrong_marking_with_marked_false(self) -> None:
        """When wrong_marking is set, marked should be False."""
        ref = TermRef(
            node_id="REQ-p00001",
            namespace="CORE",
            marked=False,
            line=42,
            wrong_marking="~~",
        )
        assert ref.marked is False
        assert ref.wrong_marking == "~~"


class TestBuilderNamespaceOnTermEntry:
    """Validates REQ-d00222-D: GraphBuilder sets TermEntry.namespace during build.

    GraphBuilder SHALL accept a `namespace` parameter and set
    `TermEntry.namespace` from it during term creation.
    """

    def test_REQ_d00222_D_builder_accepts_namespace_param(self) -> None:
        """GraphBuilder.__init__ accepts a namespace keyword argument."""
        builder = GraphBuilder(repo_root=Path("/test/repo"), namespace="MYREPO")
        # If we get here without TypeError, the parameter is accepted.
        assert builder is not None

    def test_REQ_d00222_D_default_namespace_is_empty(self) -> None:
        """GraphBuilder with no namespace arg produces terms with empty namespace."""
        builder = GraphBuilder(repo_root=Path("/test/repo"))
        file_node = _make_file_node("spec/glossary.md")
        builder.register_file_node(file_node)

        content = _make_definition_block("Audit Trail", "A chronological record", line=5)
        builder.add_parsed_content(content, file_node=file_node)
        graph = builder.build()

        entry = graph._terms.lookup("Audit Trail")
        assert entry is not None, "Term should exist in _terms"
        assert (
            entry.namespace == ""
        ), f"Default namespace should be empty string, got '{entry.namespace}'"

    def test_REQ_d00222_D_namespace_set_on_file_level_definition(self) -> None:
        """File-level definition_block gets namespace from GraphBuilder."""
        builder = GraphBuilder(repo_root=Path("/test/repo"), namespace="MYREPO")
        file_node = _make_file_node("spec/glossary.md")
        builder.register_file_node(file_node)

        content = _make_definition_block("Electronic Record", "Any combination of text", line=10)
        builder.add_parsed_content(content, file_node=file_node)
        graph = builder.build()

        entry = graph._terms.lookup("Electronic Record")
        assert entry is not None, "Term should exist in _terms"
        assert (
            entry.namespace == "MYREPO"
        ), f"TermEntry.namespace should be 'MYREPO', got '{entry.namespace}'"

    def test_REQ_d00222_D_namespace_set_on_requirement_level_definition(self) -> None:
        """Requirement-level definitions also get namespace from GraphBuilder."""
        builder = GraphBuilder(repo_root=Path("/test/repo"), namespace="PARTNER")
        file_node = _make_file_node("spec/reqs.md")
        builder.register_file_node(file_node)

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
        assert entry is not None, "Term should exist in _terms"
        assert (
            entry.namespace == "PARTNER"
        ), f"TermEntry.namespace should be 'PARTNER', got '{entry.namespace}'"


# =============================================================================
# Full pipeline integration: definitions -> scan -> health checks
#
# Implements: REQ-d00237, REQ-d00238, REQ-d00240
# =============================================================================


def _mock_node(kind, node_id, label="", fields=None):
    """Create a minimal mock graph node."""
    node = MagicMock()
    node.kind = kind
    node.id = node_id
    node.get_label.return_value = label
    _fields = fields or {}
    node.get_field.side_effect = lambda k: _fields.get(k)
    node.file_node.return_value = None
    return node


def _mock_file_node_simple(relative_path, file_type="SPEC"):
    """Create a minimal mock FILE node."""
    return _mock_node(
        NodeKind.FILE,
        f"file:{relative_path}",
        fields={"relative_path": relative_path, "file_type": file_type},
    )


def _mock_graph(nodes_by_kind, file_roots=None):
    """Create a minimal mock TraceGraph."""
    graph = MagicMock()

    def iter_by_kind(kind):
        return iter(nodes_by_kind.get(kind, []))

    def iter_roots(kind=None):
        roots = file_roots or []
        if kind is not None:
            return iter(r for r in roots if r.kind == kind)
        return iter(roots)

    graph.iter_by_kind.side_effect = iter_by_kind
    graph.iter_roots.side_effect = iter_roots
    return graph


class _FakeGraph:
    """Minimal stand-in for FederatedGraph with term-related attributes."""

    def __init__(
        self,
        terms: TermDictionary | None = None,
        term_duplicates: list[tuple] | None = None,
    ) -> None:
        self._terms = terms or TermDictionary()
        self._term_duplicates = term_duplicates or []


# Implements: REQ-d00238-A
def test_REQ_d00238_A_full_pipeline_definitions_to_health_checks():
    """Integration: definitions -> scan_graph -> extract unmarked -> health check."""
    # 1. Create term dictionary with a defined term
    td = TermDictionary()
    td.add(
        TermEntry(
            term="Widget",
            definition="A small interactive UI component.",
            indexed=True,
            defined_in="REQ-p00001",
            defined_at_line=5,
            namespace="main",
        )
    )

    # 2. Create mock graph nodes with text containing term references:
    #    - *Widget* (marked correctly)
    #    - Widget (unmarked plain text)
    #    - __Widget__ (wrong marking)
    file_node = _mock_file_node_simple("spec/requirements.md")

    req_marked = _mock_node(
        NodeKind.REQUIREMENT,
        "REQ-d00010",
        label="The *Widget* shall render within 100ms",
    )
    req_marked.file_node.return_value = file_node

    req_unmarked = _mock_node(
        NodeKind.REQUIREMENT,
        "REQ-d00020",
        label="Each Widget must have a unique identifier",
    )
    req_unmarked.file_node.return_value = file_node

    req_wrong = _mock_node(
        NodeKind.REQUIREMENT,
        "REQ-d00030",
        label="The __Widget__ state shall be persisted",
    )
    req_wrong.file_node.return_value = file_node

    graph = _mock_graph(
        {
            NodeKind.REQUIREMENT: [req_marked, req_unmarked, req_wrong],
        }
    )

    # 3. Scan graph with markup_styles=["*"]
    scan_graph(td, graph, namespace="main", markup_styles=["*"])

    # 4. Verify references populated
    entry = td.lookup("widget")
    assert entry is not None
    assert (
        len(entry.references) >= 3
    ), f"Expected at least 3 references, got {len(entry.references)}"

    # Verify marked reference
    marked_refs = [r for r in entry.references if r.marked]
    assert len(marked_refs) >= 1
    assert any(r.node_id == "REQ-d00010" for r in marked_refs)

    # Verify unmarked reference (plain text, no wrong_marking)
    plain_unmarked = [r for r in entry.references if not r.marked and not r.wrong_marking]
    assert len(plain_unmarked) >= 1
    assert any(r.node_id == "REQ-d00020" for r in plain_unmarked)

    # Verify wrong-marking reference
    wrong_refs = [r for r in entry.references if r.wrong_marking]
    assert len(wrong_refs) >= 1
    assert any(r.node_id == "REQ-d00030" and r.wrong_marking == "__" for r in wrong_refs)

    # 5. Extract unmarked data for health checks (plain + wrong-marking)
    unmarked_data = []
    for ref in entry.references:
        if not ref.marked:
            item = {
                "term": entry.term,
                "node_id": ref.node_id,
                "line": ref.line,
            }
            if ref.wrong_marking:
                item["wrong_marking"] = ref.wrong_marking
            unmarked_data.append(item)

    # 6. Run health check and verify failure
    result = check_unmarked_usage(unmarked_data)
    assert isinstance(result, HealthCheck)
    assert result.passed is False
    assert result.name == "terms.unmarked"
    assert len(result.findings) >= 2  # at least plain unmarked + wrong marking

    # Verify distinct messages for wrong-marking vs plain unmarked
    wrong_findings = [f for f in result.findings if "Wrong markup" in f.message]
    plain_findings = [f for f in result.findings if "Unmarked usage" in f.message]
    assert len(wrong_findings) >= 1, "Expected wrong-marking finding"
    assert len(plain_findings) >= 1, "Expected plain unmarked finding"


# Implements: REQ-d00237-D
def test_REQ_d00237_D_scan_detects_no_false_positives_for_partial_matches():
    """Integration: partial word matches are not flagged."""
    td = TermDictionary()
    td.add(
        TermEntry(
            term="Term",
            definition="A word with a specific meaning.",
            indexed=True,
            defined_in="REQ-p00001",
            namespace="main",
        )
    )

    file_node = _mock_file_node_simple("spec/requirements.md")
    req_node = _mock_node(
        NodeKind.REQUIREMENT,
        "REQ-d00050",
        label="The terminology used must be consistent",
    )
    req_node.file_node.return_value = file_node

    graph = _mock_graph({NodeKind.REQUIREMENT: [req_node]})
    scan_graph(td, graph, namespace="main")

    entry = td.lookup("term")
    assert entry is not None
    assert (
        len(entry.references) == 0
    ), "Partial match 'terminology' should not produce a reference for 'term'"


# Implements: REQ-d00240-A
def test_REQ_d00240_A_unused_term_detected_after_scan():
    """Integration: a defined term with zero scan hits triggers unused check."""
    td = TermDictionary()
    td.add(
        TermEntry(
            term="Gadget",
            definition="A standalone hardware device.",
            indexed=True,
            defined_in="REQ-p00002",
            defined_at_line=10,
            namespace="main",
        )
    )

    # Graph has a requirement that does NOT mention "Gadget"
    file_node = _mock_file_node_simple("spec/requirements.md")
    req_node = _mock_node(
        NodeKind.REQUIREMENT,
        "REQ-d00060",
        label="The system shall support multiple display modes",
    )
    req_node.file_node.return_value = file_node

    graph = _mock_graph({NodeKind.REQUIREMENT: [req_node]})
    scan_graph(td, graph, namespace="main")

    entry = td.lookup("gadget")
    assert entry is not None
    assert len(entry.references) == 0

    # Run unused term check
    result = check_term_unused(list(td.iter_all()))
    assert isinstance(result, HealthCheck)
    assert result.name == "terms.unused"
    assert result.passed is False
    assert len(result.findings) == 1
    assert "Gadget" in result.findings[0].message


# Implements: REQ-d00238-A
def test_REQ_d00238_A_multiple_terms_scanned_independently():
    """Integration: multiple terms are tracked independently in one scan."""
    td = TermDictionary()
    td.add(
        TermEntry(
            term="Widget",
            definition="A small interactive UI component.",
            indexed=True,
            defined_in="REQ-p00001",
            namespace="main",
        )
    )
    td.add(
        TermEntry(
            term="Gadget",
            definition="A standalone hardware device.",
            indexed=True,
            defined_in="REQ-p00002",
            namespace="main",
        )
    )

    file_node = _mock_file_node_simple("spec/requirements.md")

    # One node mentions both terms
    req_both = _mock_node(
        NodeKind.REQUIREMENT,
        "REQ-d00070",
        label="The *Widget* connects to the Gadget",
    )
    req_both.file_node.return_value = file_node

    # Another node mentions only Widget
    req_widget = _mock_node(
        NodeKind.REQUIREMENT,
        "REQ-d00071",
        label="The Widget provides status updates",
    )
    req_widget.file_node.return_value = file_node

    graph = _mock_graph(
        {
            NodeKind.REQUIREMENT: [req_both, req_widget],
        }
    )
    scan_graph(td, graph, namespace="main", markup_styles=["*"])

    widget = td.lookup("widget")
    gadget = td.lookup("gadget")

    # Widget: marked in REQ-d00070, unmarked in REQ-d00071
    assert len(widget.references) >= 2
    assert any(r.node_id == "REQ-d00070" and r.marked for r in widget.references)
    assert any(r.node_id == "REQ-d00071" and not r.marked for r in widget.references)

    # Gadget: unmarked in REQ-d00070 only
    assert len(gadget.references) >= 1
    assert any(r.node_id == "REQ-d00070" and not r.marked for r in gadget.references)


# Implements: REQ-d00240-A
def test_REQ_d00240_A_run_term_checks_aggregator_with_populated_terms():
    """Integration: run_term_checks with a populated TermDictionary."""
    td = TermDictionary()
    # One used term
    used = TermEntry(
        term="Widget",
        definition="A small interactive UI component.",
        indexed=True,
        defined_in="REQ-p00001",
        namespace="main",
        references=[
            TermRef(node_id="REQ-d00010", namespace="main", marked=True, line=5),
        ],
    )
    td.add(used)

    # One unused term
    unused_entry = TermEntry(
        term="Gadget",
        definition="A standalone hardware device.",
        indexed=True,
        defined_in="REQ-p00002",
        namespace="main",
        references=[],
    )
    td.add(unused_entry)

    config = {
        "terms": {
            "severity": {
                "duplicate": "error",
                "undefined": "warning",
                "unmarked": "warning",
                "unused": "warning",
                "bad_definition": "error",
                "collection_empty": "warning",
            },
        },
    }
    fake_graph = _FakeGraph(terms=td)

    result = run_term_checks(fake_graph, config)

    assert isinstance(result, list)
    assert len(result) == 6

    # The unused check should fail (Gadget has no references)
    unused_check = [c for c in result if c.name == "terms.unused"]
    assert len(unused_check) == 1
    assert unused_check[0].passed is False
    assert any("Gadget" in f.message for f in unused_check[0].findings)

    # The bad_definition check should pass (both have adequate definitions)
    bad_def_check = [c for c in result if c.name == "terms.bad_definition"]
    assert len(bad_def_check) == 1
    assert bad_def_check[0].passed is True


# Implements: REQ-d00238-B
def test_REQ_d00238_B_code_comments_only_in_pipeline(tmp_path):
    """Integration: CODE nodes only scan comments, not identifiers."""
    td = TermDictionary()
    td.add(
        TermEntry(
            term="Widget",
            definition="A small interactive UI component.",
            indexed=True,
            defined_in="REQ-p00001",
            namespace="main",
        )
    )

    # Write a real Python file so extract_comments can tokenize/parse it
    py_file = tmp_path / "main.py"
    py_file.write_text("widget = create()\n# The Widget handles rendering\n")
    file_node = _mock_node(
        NodeKind.FILE,
        "file:src/main.py",
        fields={
            "relative_path": "src/main.py",
            "absolute_path": str(py_file),
            "file_type": FileType.CODE,
        },
    )

    graph = _mock_graph({}, file_roots=[file_node])
    scan_graph(td, graph, namespace="main")

    entry = td.lookup("widget")
    assert entry is not None
    # Should find reference from comment only, not from code identifier
    assert len(entry.references) == 1
    assert entry.references[0].node_id == "file:src/main.py"
    # The reference is from a comment (plain text), so unmarked
    assert entry.references[0].marked is False
