# Implements: REQ-d00220
"""Tests for defined terms phase 4: reference types, synonyms, change tracking."""

from pathlib import Path

from elspais.graph.builder import GraphBuilder
from elspais.graph.GraphNode import GraphNode, NodeKind
from elspais.graph.parsers import ParsedContent
from elspais.graph.terms import TermDictionary, TermEntry, TermRef


class TestTermEntryReferenceType:
    """Reference-type definitions have structured citation fields."""

    def test_default_entry_is_not_reference(self):
        entry = TermEntry(term="Audit Trail", definition="A record of events.")
        assert entry.is_reference is False
        assert entry.reference_fields == {}

    def test_reference_entry(self):
        entry = TermEntry(
            term="ISO/IEC 24760-1",
            definition="",
            is_reference=True,
            reference_fields={
                "title": "IT Security and Privacy",
                "version": "ISO/IEC 24760-1:2019",
                "effective_date": "2026-03-22",
                "url": "https://www.iso.org",
            },
        )
        assert entry.is_reference is True
        assert entry.reference_fields["version"] == "ISO/IEC 24760-1:2019"

    def test_entry_with_synonym(self):
        entry = TermEntry(
            term="Full Name",
            definition="A common name of the person.",
            reference_term="PII",
            reference_source="ISO/IEC 24760-1",
        )
        assert entry.reference_term == "PII"
        assert entry.reference_source == "ISO/IEC 24760-1"

    def test_entry_with_definition_hash(self):
        entry = TermEntry(term="Audit Trail", definition="A record of events.")
        assert entry.definition_hash == ""  # not computed yet


class TestTermDictionaryReferences:
    """TermDictionary.iter_references() yields only reference-type entries."""

    def test_iter_references(self):
        td = TermDictionary()
        td.add(TermEntry(term="Audit Trail", definition="A record."))
        td.add(TermEntry(term="ISO 27001", definition="", is_reference=True))
        td.add(TermEntry(term="NIST 800-53", definition="", is_reference=True))

        refs = list(td.iter_references())
        assert len(refs) == 2
        assert all(e.is_reference for e in refs)

    def test_iter_references_empty_when_none(self):
        td = TermDictionary()
        td.add(TermEntry(term="Audit Trail", definition="A record."))
        assert list(td.iter_references()) == []

    def test_lookup_by_synonym(self):
        td = TermDictionary()
        td.add(
            TermEntry(
                term="Full Name",
                definition="A common name.",
                reference_term="PII",
            )
        )
        entry = td.lookup_by_synonym("PII")
        assert entry is not None
        assert entry.term == "Full Name"

    def test_lookup_by_synonym_case_insensitive(self):
        td = TermDictionary()
        td.add(
            TermEntry(
                term="Full Name",
                definition="A common name.",
                reference_term="PII",
            )
        )
        assert td.lookup_by_synonym("pii") is not None

    def test_lookup_by_synonym_not_found(self):
        td = TermDictionary()
        td.add(TermEntry(term="Audit Trail", definition="A record."))
        assert td.lookup_by_synonym("nonexistent") is None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_definition_block(
    term: str,
    definition: str,
    line: int = 10,
    *,
    collection: bool = False,
    indexed: bool = True,
    is_reference: bool = False,
    reference_fields: dict[str, str] | None = None,
    reference_term: str = "",
    reference_source: str = "",
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
            "is_reference": is_reference,
            "reference_fields": reference_fields or {},
            "reference_term": reference_term,
            "reference_source": reference_source,
        },
    )


def _make_file_node(rel_path: str = "spec/glossary.md") -> GraphNode:
    """Create a FILE node for testing."""
    node = GraphNode(id=f"file:{rel_path}", kind=NodeKind.FILE)
    node.set_field("file_type", "SPEC")
    node.set_field("relative_path", rel_path)
    node.set_field("absolute_path", f"/test/repo/{rel_path}")
    node.set_field("repo", None)
    return node


# ---------------------------------------------------------------------------
# Task 2+3: Parser + Builder wiring
# ---------------------------------------------------------------------------


class TestBuilderReferenceTerms:
    """GraphBuilder populates reference-type fields on TermEntry."""

    def test_reference_definition_in_graph(self):
        builder = GraphBuilder(repo_root=Path("/test/repo"))
        content = _make_definition_block(
            "ISO/IEC 24760-1",
            "",
            is_reference=True,
            reference_fields={
                "title": "IT Security and Privacy",
                "version": "ISO/IEC 24760-1:2019",
                "url": "https://www.iso.org",
            },
        )
        builder.add_parsed_content(content)
        graph = builder.build()

        entry = graph._terms.lookup("ISO/IEC 24760-1")
        assert entry is not None
        assert entry.is_reference is True
        assert entry.reference_fields["title"] == "IT Security and Privacy"
        assert entry.reference_fields["version"] == "ISO/IEC 24760-1:2019"
        assert entry.reference_fields["url"] == "https://www.iso.org"

    def test_synonym_linked_in_graph(self):
        builder = GraphBuilder(repo_root=Path("/test/repo"))
        content = _make_definition_block(
            "Email Address",
            "A unique identifier for authentication.",
            reference_term="Registered Notification Address",
            reference_source="ISO/IEC 24760-1",
        )
        builder.add_parsed_content(content)
        graph = builder.build()

        entry = graph._terms.lookup("Email Address")
        assert entry is not None
        assert entry.reference_term == "Registered Notification Address"
        assert entry.reference_source == "ISO/IEC 24760-1"

    def test_reference_definition_full_pipeline(self, tmp_path):
        """Full pipeline: Lark parse -> transformer -> builder -> TermEntry."""
        from elspais.graph.factory import build_graph

        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        (spec_dir / "glossary.md").write_text(
            "ISO/IEC 24760-1\n"
            ": Reference\n"
            ": Title: IT Security and Privacy\n"
            ": Version: ISO/IEC 24760-1:2019\n"
            ": Effective Date: 2026-03-22\n"
            ": URL: <https://www.iso.org>\n"
        )
        (tmp_path / ".elspais.toml").write_text(
            "version = 4\n"
            "[levels.prd]\n"
            "rank = 1\n"
            'letter = "p"\n'
            'display_name = "PRD"\n'
            'implements = ["prd"]\n'
        )

        graph = build_graph(
            config_path=tmp_path / ".elspais.toml",
            spec_dirs=[spec_dir],
            repo_root=tmp_path,
        )

        entry = graph._terms.lookup("ISO/IEC 24760-1")
        assert entry is not None
        assert entry.is_reference is True
        assert entry.reference_fields["title"] == "IT Security and Privacy"
        assert entry.reference_fields["version"] == "ISO/IEC 24760-1:2019"
        assert entry.reference_fields["effective_date"] == "2026-03-22"
        assert entry.reference_fields["url"] == "https://www.iso.org"

    def test_synonym_full_pipeline(self, tmp_path):
        """Full pipeline: synonym metadata flows through."""
        from elspais.graph.factory import build_graph

        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        (spec_dir / "glossary.md").write_text(
            "Email Address\n"
            ": A unique technical identifier used for authentication.\n"
            ": Reference Term: __Registered Notification Address__\n"
            ": Reference Source: **ISO/IEC 24760-1**\n"
        )
        (tmp_path / ".elspais.toml").write_text(
            "version = 4\n"
            "[levels.prd]\n"
            "rank = 1\n"
            'letter = "p"\n'
            'display_name = "PRD"\n'
            'implements = ["prd"]\n'
        )

        graph = build_graph(
            config_path=tmp_path / ".elspais.toml",
            spec_dirs=[spec_dir],
            repo_root=tmp_path,
        )

        entry = graph._terms.lookup("Email Address")
        assert entry is not None
        assert entry.reference_term == "Registered Notification Address"
        assert entry.reference_source == "ISO/IEC 24760-1"
        assert entry.is_reference is False

    def test_non_reference_defaults_preserved(self):
        """Existing term entries keep default phase-4 fields."""
        builder = GraphBuilder(repo_root=Path("/test/repo"))
        content = _make_definition_block("Audit Trail", "A record of events.")
        builder.add_parsed_content(content)
        graph = builder.build()

        entry = graph._terms.lookup("Audit Trail")
        assert entry is not None
        assert entry.is_reference is False
        assert entry.reference_fields == {}
        assert entry.reference_term == ""
        assert entry.reference_source == ""


# ---------------------------------------------------------------------------
# Task 4: Glossary reference section
# ---------------------------------------------------------------------------


class TestGlossaryReferenceSection:
    """Glossary output includes a References section for reference-type terms."""

    def test_glossary_separates_references(self):
        from elspais.commands.glossary_cmd import generate_glossary

        td = TermDictionary()
        td.add(
            TermEntry(
                term="Audit Trail",
                definition="A record of events.",
                namespace="main",
                defined_in="REQ-p00001",
            )
        )
        td.add(
            TermEntry(
                term="ISO/IEC 24760-1",
                definition="",
                is_reference=True,
                namespace="main",
                defined_in="glossary.md",
                reference_fields={
                    "title": "IT Security and Privacy",
                    "version": "ISO/IEC 24760-1:2019",
                    "url": "https://www.iso.org",
                },
            )
        )

        output = generate_glossary(td)
        # Regular terms in the main Glossary section
        assert "## A" in output
        assert "**Audit Trail**" in output
        # Reference section appears after main glossary
        assert "# References" in output
        assert "**ISO/IEC 24760-1**" in output
        assert "IT Security and Privacy" in output
        assert "ISO/IEC 24760-1:2019" in output

    def test_glossary_shows_synonym_link(self):
        from elspais.commands.glossary_cmd import generate_glossary

        td = TermDictionary()
        td.add(
            TermEntry(
                term="Email Address",
                definition="A unique identifier for authentication.",
                reference_term="Registered Notification Address",
                reference_source="ISO/IEC 24760-1",
                namespace="main",
                defined_in="REQ-p00001",
            )
        )

        output = generate_glossary(td)
        assert "Registered Notification Address" in output
        assert "ISO/IEC 24760-1" in output

    def test_glossary_json_includes_reference_fields(self):
        import json

        from elspais.commands.glossary_cmd import generate_glossary

        td = TermDictionary()
        td.add(
            TermEntry(
                term="ISO 27001",
                definition="",
                is_reference=True,
                namespace="main",
                defined_in="glossary.md",
                reference_fields={"title": "Information Security", "version": "2022"},
            )
        )

        output = generate_glossary(td, format="json")
        data = json.loads(output)
        assert data[0]["is_reference"] is True
        assert data[0]["reference_fields"]["title"] == "Information Security"

    def test_glossary_no_references_section_when_none(self):
        from elspais.commands.glossary_cmd import generate_glossary

        td = TermDictionary()
        td.add(
            TermEntry(
                term="Audit Trail",
                definition="A record.",
                namespace="main",
                defined_in="REQ-p00001",
            )
        )

        output = generate_glossary(td)
        assert "# References" not in output


# ---------------------------------------------------------------------------
# Task 5: MCP tool logic
# ---------------------------------------------------------------------------


class TestMcpTermToolLogic:
    """Term tool logic (unit tests, no MCP client needed)."""

    def test_get_terms_returns_summary(self):
        from elspais.mcp.server import _get_terms_logic

        td = TermDictionary()
        td.add(TermEntry(term="Audit Trail", definition="A record.", namespace="main"))
        td.add(TermEntry(term="ISO 27001", definition="", is_reference=True, namespace="main"))

        result = _get_terms_logic(td)
        assert len(result["terms"]) == 2
        assert result["reference_count"] == 1
        assert result["glossary_count"] == 1
        assert result["total"] == 2

    def test_get_terms_filter_reference(self):
        from elspais.mcp.server import _get_terms_logic

        td = TermDictionary()
        td.add(TermEntry(term="Audit Trail", definition="A record."))
        td.add(TermEntry(term="ISO 27001", definition="", is_reference=True))

        result = _get_terms_logic(td, kind="reference")
        assert result["total"] == 1
        assert result["terms"][0]["term"] == "ISO 27001"

    def test_get_terms_filter_glossary(self):
        from elspais.mcp.server import _get_terms_logic

        td = TermDictionary()
        td.add(TermEntry(term="Audit Trail", definition="A record."))
        td.add(TermEntry(term="ISO 27001", definition="", is_reference=True))

        result = _get_terms_logic(td, kind="glossary")
        assert result["total"] == 1
        assert result["terms"][0]["term"] == "Audit Trail"

    def test_get_term_detail(self):
        from elspais.mcp.server import _get_term_detail_logic

        td = TermDictionary()
        entry = TermEntry(
            term="Audit Trail",
            definition="A record.",
            namespace="main",
            defined_in="REQ-p00001",
            references=[TermRef(node_id="REQ-d00045", namespace="main", marked=True, line=12)],
        )
        td.add(entry)

        result = _get_term_detail_logic(td, "Audit Trail")
        assert result["term"] == "Audit Trail"
        assert len(result["references"]) == 1
        assert result["references"][0]["node_id"] == "REQ-d00045"

    def test_get_term_detail_not_found(self):
        from elspais.mcp.server import _get_term_detail_logic

        td = TermDictionary()
        result = _get_term_detail_logic(td, "nonexistent")
        assert "error" in result

    def test_search_terms_by_definition(self):
        from elspais.mcp.server import _search_terms_logic

        td = TermDictionary()
        td.add(
            TermEntry(
                term="Audit Trail",
                definition="A chronological record of system activities.",
            )
        )
        td.add(TermEntry(term="User ID", definition="Unique identifier for a user."))

        result = _search_terms_logic(td, "chronological")
        assert len(result) == 1
        assert result[0]["term"] == "Audit Trail"

    def test_search_terms_by_name(self):
        from elspais.mcp.server import _search_terms_logic

        td = TermDictionary()
        td.add(TermEntry(term="Audit Trail", definition="A record."))
        td.add(TermEntry(term="User ID", definition="An identifier."))

        result = _search_terms_logic(td, "audit")
        assert len(result) == 1
        assert result[0]["term"] == "Audit Trail"
        assert result[0]["score"] == 100

    def test_search_terms_reference_fields(self):
        from elspais.mcp.server import _search_terms_logic

        td = TermDictionary()
        td.add(
            TermEntry(
                term="ISO 27001",
                definition="",
                is_reference=True,
                reference_fields={"title": "Information Security Management"},
            )
        )

        result = _search_terms_logic(td, "security management")
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Task 6: Definition change tracking (hashing)
# ---------------------------------------------------------------------------


class TestDefinitionChangeTracking:
    """Definitions are hashed for change detection."""

    def test_compute_definition_hash(self):
        from elspais.graph.terms import compute_definition_hash

        h = compute_definition_hash("A chronological record of system activities.")
        assert len(h) == 8
        assert h.isalnum()

    def test_same_definition_same_hash(self):
        from elspais.graph.terms import compute_definition_hash

        h1 = compute_definition_hash("A record.")
        h2 = compute_definition_hash("A record.")
        assert h1 == h2

    def test_different_definition_different_hash(self):
        from elspais.graph.terms import compute_definition_hash

        h1 = compute_definition_hash("A record.")
        h2 = compute_definition_hash("A different record.")
        assert h1 != h2

    def test_reference_fields_affect_hash(self):
        from elspais.graph.terms import compute_definition_hash

        h1 = compute_definition_hash("", reference_fields={"url": "https://a.com"})
        h2 = compute_definition_hash("", reference_fields={"url": "https://b.com"})
        assert h1 != h2

    def test_compute_definition_hash_canonicalizes_trailing_whitespace(self):
        """Trailing whitespace on a line does not flip the hash."""
        from elspais.graph.terms import compute_definition_hash

        assert compute_definition_hash("foo   \nbar") == compute_definition_hash("foo\nbar")

    def test_compute_definition_hash_collapses_blank_line_runs(self):
        """Runs of blank lines collapse to a single blank line for hashing."""
        from elspais.graph.terms import compute_definition_hash

        assert compute_definition_hash("foo\n\n\n\nbar") == compute_definition_hash("foo\n\nbar")

    def test_compute_definition_hash_strips_outer_whitespace(self):
        """Leading/trailing blank lines on the block are stripped before hashing."""
        from elspais.graph.terms import compute_definition_hash

        assert compute_definition_hash("\n\nfoo\n\n") == compute_definition_hash("foo")

    def test_compute_definition_hash_preserves_internal_content(self):
        """Intra-line whitespace runs are NOT collapsed — semantic differences preserved."""
        from elspais.graph.terms import compute_definition_hash

        # Two spaces vs one space inside a line must produce different hashes.
        assert compute_definition_hash("foo bar") != compute_definition_hash("foo  bar")

    def test_builder_populates_definition_hash(self):
        builder = GraphBuilder(repo_root=Path("/test/repo"))
        content = _make_definition_block("Audit Trail", "A chronological record.")
        builder.add_parsed_content(content)
        graph = builder.build()

        entry = graph._terms.lookup("Audit Trail")
        assert entry is not None
        assert entry.definition_hash != ""
        assert len(entry.definition_hash) == 8

    def test_builder_reference_hash_includes_fields(self):
        builder = GraphBuilder(repo_root=Path("/test/repo"))
        content = _make_definition_block(
            "ISO 27001",
            "",
            is_reference=True,
            reference_fields={"title": "Info Security", "version": "2022"},
        )
        builder.add_parsed_content(content)
        graph = builder.build()

        entry = graph._terms.lookup("ISO 27001")
        assert entry is not None
        assert entry.definition_hash != ""
        # Verify reference_fields contribute to hash
        from elspais.graph.terms import compute_definition_hash

        expected = compute_definition_hash(
            "", reference_fields={"title": "Info Security", "version": "2022"}
        )
        assert entry.definition_hash == expected


# ---------------------------------------------------------------------------
# Task 7: Wire health checks + undefined scanner + follow-ups
# ---------------------------------------------------------------------------


class TestFindUnmatchedEmphasis:
    """find_unmatched_emphasis() detects emphasis tokens not in dictionary."""

    def test_detects_unknown_emphasis(self):
        from elspais.graph.term_scanner import find_unmatched_emphasis

        td = TermDictionary()
        td.add(TermEntry(term="Audit Trail", definition="A record."))

        text = "This **Flowchart** shows the *Audit Trail* flow."
        result = find_unmatched_emphasis(text, td, "REQ-p00001", "main", markup_styles=["*", "**"])
        # "Flowchart" is not in the dictionary, "Audit Trail" is
        assert len(result) == 1
        assert result[0]["token"] == "Flowchart"
        assert result[0]["delimiter"] == "**"

    def test_known_terms_not_reported(self):
        from elspais.graph.term_scanner import find_unmatched_emphasis

        td = TermDictionary()
        td.add(TermEntry(term="Audit Trail", definition="A record."))

        text = "The **Audit Trail** is important."
        result = find_unmatched_emphasis(text, td, "REQ-p00001", "main", markup_styles=["**"])
        assert len(result) == 0

    def test_synonyms_not_reported(self):
        from elspais.graph.term_scanner import find_unmatched_emphasis

        td = TermDictionary()
        td.add(TermEntry(term="Email", definition="An address.", reference_term="PII"))

        text = "Handle **PII** carefully."
        result = find_unmatched_emphasis(text, td, "REQ-p00001", "main", markup_styles=["**"])
        assert len(result) == 0

    def test_empty_text(self):
        from elspais.graph.term_scanner import find_unmatched_emphasis

        td = TermDictionary()
        result = find_unmatched_emphasis("", td, "REQ-p00001", "main")
        assert result == []


class TestWiredTermHealthChecks:
    """run_term_checks extracts data from graph for undefined and unmarked checks."""

    def test_unmarked_usage_detected(self):
        from elspais.commands.health import check_unmarked_usage

        unmarked_data = [
            {
                "term": "Audit Trail",
                "node_id": "REQ-d00045",
                "line": 12,
            },
        ]
        result = check_unmarked_usage(unmarked_data, severity="warning")
        assert not result.passed
        assert len(result.findings) == 1

    def test_undefined_term_detected(self):
        from elspais.commands.health import check_undefined_terms

        undefined_data = [
            {
                "token": "Flowchart",
                "node_id": "REQ-p00003",
                "line": 47,
                "delimiter": "**",
                "namespace": "main",
            },
        ]
        result = check_undefined_terms(undefined_data, severity="warning")
        assert not result.passed
        assert len(result.findings) == 1

    def test_run_term_checks_extracts_unmarked(self):
        from unittest.mock import MagicMock

        from elspais.commands.health import run_term_checks

        td = TermDictionary()
        entry = TermEntry(
            term="Audit Trail",
            definition="A record of events for audit purposes.",
            references=[
                TermRef(
                    node_id="REQ-d00045",
                    namespace="main",
                    marked=False,
                    line=12,
                    surface_form="audit trail",
                    delimiter="",
                ),
            ],
        )
        td.add(entry)

        graph = MagicMock()
        graph.terms = td
        graph.term_duplicates = []
        graph.unmatched_emphasis = []

        results = run_term_checks(graph)
        unmarked_check = next(r for r in results if r.name == "terms.unmarked")
        assert not unmarked_check.passed
        assert len(unmarked_check.findings) >= 1

    def test_run_term_checks_extracts_undefined(self):
        from unittest.mock import MagicMock

        from elspais.commands.health import run_term_checks

        td = TermDictionary()
        td.add(TermEntry(term="Audit Trail", definition="A record of events for audit purposes."))

        graph = MagicMock()
        graph.terms = td
        graph.term_duplicates = []
        graph.unmatched_emphasis = [
            {
                "token": "Flowchart",
                "node_id": "REQ-p00003",
                "line": 47,
                "delimiter": "**",
                "namespace": "main",
            }
        ]

        results = run_term_checks(graph)
        undefined_check = next(r for r in results if r.name == "terms.undefined")
        assert not undefined_check.passed
        assert len(undefined_check.findings) == 1


# ---------------------------------------------------------------------------
# Task 8: diff_terms()
# ---------------------------------------------------------------------------


class TestDiffTerms:
    """Compare two TermDictionaries for changes."""

    def test_detects_changed(self):
        from elspais.graph.terms import diff_terms

        old_td = TermDictionary()
        old_td.add(
            TermEntry(term="Audit Trail", definition="A record.", definition_hash="abcd1234")
        )

        new_td = TermDictionary()
        new_td.add(
            TermEntry(
                term="Audit Trail", definition="A revised record.", definition_hash="efgh5678"
            )
        )

        changes = diff_terms(old_td, new_td)
        assert len(changes["changed"]) == 1
        assert changes["changed"][0]["term"] == "Audit Trail"
        assert changes["changed"][0]["old_hash"] == "abcd1234"
        assert changes["changed"][0]["new_hash"] == "efgh5678"

    def test_detects_added(self):
        from elspais.graph.terms import diff_terms

        old_td = TermDictionary()
        new_td = TermDictionary()
        new_td.add(TermEntry(term="New Term", definition="A new one.", definition_hash="abcd1234"))

        changes = diff_terms(old_td, new_td)
        assert len(changes["added"]) == 1
        assert changes["added"][0]["term"] == "New Term"

    def test_detects_removed(self):
        from elspais.graph.terms import diff_terms

        old_td = TermDictionary()
        old_td.add(TermEntry(term="Old Term", definition="Gone.", definition_hash="abcd1234"))
        new_td = TermDictionary()

        changes = diff_terms(old_td, new_td)
        assert len(changes["removed"]) == 1
        assert changes["removed"][0]["term"] == "Old Term"

    def test_no_changes(self):
        from elspais.graph.terms import diff_terms

        old_td = TermDictionary()
        old_td.add(TermEntry(term="Same", definition="Same.", definition_hash="abcd1234"))
        new_td = TermDictionary()
        new_td.add(TermEntry(term="Same", definition="Same.", definition_hash="abcd1234"))

        changes = diff_terms(old_td, new_td)
        assert changes == {"added": [], "removed": [], "changed": []}


# ---------------------------------------------------------------------------
# Task 9: MCP dirty flag
# ---------------------------------------------------------------------------


class TestMcpTermDirtyFlag:
    """MCP graph status reports term dirty state."""

    def test_has_dirty_terms_false_when_clean(self):
        from unittest.mock import MagicMock

        from elspais.mcp.server import _has_dirty_terms

        graph = MagicMock()
        graph.nodes_by_kind.return_value = iter([])

        assert _has_dirty_terms(graph) is False

    def test_has_dirty_terms_true_when_dirty(self):
        from unittest.mock import MagicMock

        from elspais.mcp.server import _has_dirty_terms

        node = MagicMock()
        node.get_field.side_effect = lambda f: {
            "content_type": "definition_block",
            "parse_dirty": True,
        }.get(f)

        graph = MagicMock()
        graph.nodes_by_kind.return_value = iter([node])

        assert _has_dirty_terms(graph) is True

    def test_graph_status_includes_terms_dirty(self):
        from unittest.mock import MagicMock

        from elspais.mcp.server import _get_graph_status

        graph = MagicMock()
        graph.root_count.return_value = 0
        graph.node_count.return_value = 0
        graph.has_orphans.return_value = False
        graph.has_broken_references.return_value = False
        graph.nodes_by_kind.return_value = iter([])

        status = _get_graph_status(graph)
        assert "terms_dirty" in status
        assert status["terms_dirty"] is False
