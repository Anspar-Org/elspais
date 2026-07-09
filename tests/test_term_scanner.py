"""Tests for extract_comments() in term_scanner.

# Implements: REQ-d00236

Validates REQ-d00236-A+B+C+D+E+F+G: comment extraction from source
code across multiple language families.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from elspais.graph.GraphNode import FileType, NodeKind
from elspais.graph.term_scanner import (
    _canonicalize_text,
    _is_embedded_in_compound,
    _terms_longest_first,
    extract_comments,
    scan_graph,
    scan_text_for_terms,
)
from elspais.graph.terms import TermDictionary, TermEntry, TermRef

# -- REQ-d00236-A: returns list of (comment_text, line_number) pairs -----------


def test_REQ_d00236_A_returns_list_of_tuples():
    source = "# a comment\nx = 1\n"
    result = extract_comments(source, ".py")
    assert isinstance(result, list)
    for item in result:
        assert isinstance(item, tuple)
        assert len(item) == 2
        text, lineno = item
        assert isinstance(text, str)
        assert isinstance(lineno, int)


def test_REQ_d00236_A_empty_source_returns_empty_list():
    result = extract_comments("", ".py")
    assert result == []


# -- REQ-d00236-B: Python files ------------------------------------------------


def test_REQ_d00236_B_python_hash_comments():
    source = "x = 1\n# first comment\ny = 2\n# second comment\n"
    result = extract_comments(source, ".py")
    texts = [(t, ln) for t, ln in result if "comment" in t]
    assert ("first comment", 2) in texts
    assert ("second comment", 4) in texts


def test_REQ_d00236_B_python_docstring_not_extracted():
    """Docstrings are NOT extracted — only # comments are scanned for term refs."""
    source = 'def foo():\n    """This is a docstring."""\n    pass\n'
    result = extract_comments(source, ".py")
    texts = [t for t, _ in result]
    assert not any("This is a docstring" in t for t in texts)

    source = 'class Foo:\n    """Class docstring."""\n    pass\n'
    result = extract_comments(source, ".py")
    texts = [t for t, _ in result]
    assert not any("Class docstring" in t for t in texts)

    source = '"""Module-level docstring."""\nimport os\n'
    result = extract_comments(source, ".py")
    texts = [t for t, _ in result]
    assert not any("Module-level docstring" in t for t in texts)

    source = (
        "def bar():\n"
        '    """First line.\n'
        "\n"
        "    Second paragraph.\n"
        '    """\n'
        "    pass\n"
    )
    result = extract_comments(source, ".py")
    texts = [t for t, _ in result]
    assert not any("First line" in t for t in texts)


def test_REQ_d00236_B_python_string_literal_not_extracted():
    source = (
        "x = 'not a comment'\n"
        'y = "also not a comment"\n'
        'z = """triple-quoted but assigned, not a docstring"""\n'
    )
    result = extract_comments(source, ".py")
    texts = [t for t, _ in result]
    assert not any("not a comment" in t for t in texts)
    assert not any("triple-quoted but assigned" in t for t in texts)


# -- REQ-d00236-C: Slash-comment languages -------------------------------------


def test_REQ_d00236_C_js_line_comment():
    source = "const x = 1;\n// a line comment\nconst y = 2;\n"
    result = extract_comments(source, ".js")
    assert ("a line comment", 2) in result


def test_REQ_d00236_C_js_block_comment():
    source = "const x = 1;\n/* block comment */\nconst y = 2;\n"
    result = extract_comments(source, ".js")
    texts = [t for t, _ in result]
    assert any("block comment" in t for t in texts)


def test_REQ_d00236_C_js_multiline_block_comment():
    source = (
        "const x = 1;\n" "/* first line\n" "   second line\n" "   third line */\n" "const y = 2;\n"
    )
    result = extract_comments(source, ".js")
    texts = [t for t, _ in result]
    assert any("first line" in t and "third line" in t for t in texts)


def test_REQ_d00236_C_go_line_comment():
    source = "package main\n// Go comment here\nfunc main() {}\n"
    result = extract_comments(source, ".go")
    assert ("Go comment here", 2) in result


def test_REQ_d00236_C_rust_line_comment():
    source = "fn main() {\n// Rust comment\n}\n"
    result = extract_comments(source, ".rs")
    assert ("Rust comment", 2) in result


# -- REQ-d00236-D: Hash-comment languages --------------------------------------


def test_REQ_d00236_D_ruby_hash_comment():
    source = "x = 1\n# Ruby comment\ny = 2\n"
    result = extract_comments(source, ".rb")
    assert ("Ruby comment", 2) in result


def test_REQ_d00236_D_yaml_hash_comment():
    source = "key: value\n# YAML comment\nother: thing\n"
    result = extract_comments(source, ".yaml")
    assert ("YAML comment", 2) in result


def test_REQ_d00236_D_yml_hash_comment():
    source = "# YML comment\nkey: value\n"
    result = extract_comments(source, ".yml")
    assert ("YML comment", 1) in result


# -- REQ-d00236-E: Dash-comment languages --------------------------------------


def test_REQ_d00236_E_sql_dash_comment():
    source = "SELECT 1;\n-- SQL comment\nSELECT 2;\n"
    result = extract_comments(source, ".sql")
    assert ("SQL comment", 2) in result


def test_REQ_d00236_E_lua_dash_comment():
    source = "local x = 1\n-- Lua comment\nlocal y = 2\n"
    result = extract_comments(source, ".lua")
    assert ("Lua comment", 2) in result


# -- REQ-d00236-F: Markup languages --------------------------------------------


def test_REQ_d00236_F_html_comment():
    source = "<div>\n<!-- HTML comment -->\n</div>\n"
    result = extract_comments(source, ".html")
    texts = [t for t, _ in result]
    assert any("HTML comment" in t for t in texts)


def test_REQ_d00236_F_html_multiline_comment():
    source = "<div>\n" "<!-- first line\n" "     second line -->\n" "</div>\n"
    result = extract_comments(source, ".html")
    texts = [t for t, _ in result]
    assert any("first line" in t and "second line" in t for t in texts)


def test_REQ_d00236_F_xml_comment():
    source = '<?xml version="1.0"?>\n<!-- XML comment -->\n<root/>\n'
    result = extract_comments(source, ".xml")
    texts = [t for t, _ in result]
    assert any("XML comment" in t for t in texts)


# -- REQ-d00236-G: Unknown extensions ------------------------------------------


def test_REQ_d00236_G_unknown_extension_returns_empty():
    source = "some content\n# looks like a comment\n"
    result = extract_comments(source, ".xyz")
    assert result == []


def test_REQ_d00236_G_empty_extension_returns_empty():
    source = "some content\n"
    result = extract_comments(source, "")
    assert result == []


# =============================================================================
# scan_text_for_terms() tests
#
# Verifies: REQ-d00237
#
# Validates REQ-d00237-A+B+C+D+E: term scanning with marked, wrong-marking,
# and unmarked detection.
# =============================================================================


def _make_td(*terms: tuple[str, bool]) -> TermDictionary:
    """Helper: build a TermDictionary from (term, indexed) pairs."""
    td = TermDictionary()
    for term, indexed in terms:
        td.add(TermEntry(term=term, definition="def", indexed=indexed))
    return td


# -- REQ-d00237-A: returns list[TermRef] --------------------------------------


def test_REQ_d00237_A_returns_list_of_termref():
    td = _make_td(("widget", True))
    result = scan_text_for_terms("A widget is here.", td, node_id="REQ-001", namespace="main")
    assert isinstance(result, list)
    for item in result:
        assert isinstance(item, TermRef)


# -- REQ-d00237-B: marked detection -------------------------------------------


def test_REQ_d00237_B_single_star_marked():
    td = _make_td(("widget", True))
    result = scan_text_for_terms(
        "A *widget* is here.",
        td,
        node_id="REQ-001",
        namespace="main",
        markup_styles=["*", "**"],
    )
    marked = [r for r in result if r.marked]
    assert len(marked) == 1
    assert marked[0].wrong_marking == ""


def test_REQ_d00237_B_double_star_marked():
    td = _make_td(("widget", True))
    result = scan_text_for_terms(
        "A **widget** is here.",
        td,
        node_id="REQ-001",
        namespace="main",
        markup_styles=["*", "**"],
    )
    marked = [r for r in result if r.marked]
    assert len(marked) == 1
    assert marked[0].wrong_marking == ""


def test_REQ_d00237_B_case_insensitive_marked():
    td = _make_td(("widget", True))
    result = scan_text_for_terms(
        "A *Widget* is here.",
        td,
        node_id="REQ-001",
        namespace="main",
        markup_styles=["*"],
    )
    marked = [r for r in result if r.marked]
    assert len(marked) == 1
    assert marked[0].wrong_marking == ""


# -- REQ-d00237-C: wrong-marking detection ------------------------------------


def test_REQ_d00237_C_double_underscore_wrong_marking():
    td = _make_td(("widget", True))
    result = scan_text_for_terms(
        "A __widget__ is here.",
        td,
        node_id="REQ-001",
        namespace="main",
        markup_styles=["*", "**"],
    )
    wrong = [r for r in result if r.wrong_marking]
    assert len(wrong) == 1
    assert wrong[0].wrong_marking == "__"
    assert wrong[0].marked is False


def test_REQ_d00237_C_single_underscore_wrong_marking():
    td = _make_td(("widget", True))
    result = scan_text_for_terms(
        "A _widget_ is here.",
        td,
        node_id="REQ-001",
        namespace="main",
        markup_styles=["*", "**"],
    )
    wrong = [r for r in result if r.wrong_marking]
    assert len(wrong) == 1
    assert wrong[0].wrong_marking == "_"
    assert wrong[0].marked is False


def test_REQ_d00237_C_wrong_case_term_still_detected():
    # Guards the case-insensitive term pre-filter (CUR-1521)
    # Term defined lowercase "widget" but appears as "Widget" (capital W)
    # wrapped in a wrong-marking delimiter. The emphasis/word regexes use
    # re.IGNORECASE, so the case-insensitive pre-filter must not drop this.
    td = _make_td(("widget", True))
    result = scan_text_for_terms(
        "A _Widget_ is here.",
        td,
        node_id="REQ-001",
        namespace="main",
        markup_styles=["*", "**"],
    )
    wrong = [r for r in result if r.wrong_marking]
    assert len(wrong) == 1
    assert wrong[0].wrong_marking == "_"
    assert wrong[0].marked is False


def test_REQ_d00237_C_absent_term_yields_no_results():
    # Confirms the pre-filter skip path: a term genuinely absent from the
    # text (in any case) produces no references.
    td = _make_td(("widget", True))
    result = scan_text_for_terms(
        "A _gadget_ is here.",
        td,
        node_id="REQ-001",
        namespace="main",
        markup_styles=["*", "**"],
    )
    assert result == []


def test_REQ_d00237_C_star_not_in_markup_styles_is_wrong():
    """When '*' is NOT in markup_styles, *term* is wrong-marking."""
    td = _make_td(("widget", True))
    result = scan_text_for_terms(
        "A *widget* is here.",
        td,
        node_id="REQ-001",
        namespace="main",
        markup_styles=["**"],
    )
    wrong = [r for r in result if r.wrong_marking]
    assert len(wrong) == 1
    assert wrong[0].wrong_marking == "*"
    assert wrong[0].marked is False


# -- REQ-d00237-D: unmarked (plain text) scanning -----------------------------


def test_REQ_d00237_D_plain_text_unmarked():
    td = _make_td(("widget", True))
    result = scan_text_for_terms("A widget is here.", td, node_id="REQ-001", namespace="main")
    unmarked = [r for r in result if not r.marked and not r.wrong_marking]
    assert len(unmarked) == 1


def test_REQ_d00237_D_whole_word_no_partial_match():
    td = _make_td(("term", True))
    result = scan_text_for_terms(
        "terminology is different.", td, node_id="REQ-001", namespace="main"
    )
    assert len(result) == 0


def test_REQ_d00237_D_case_insensitive_plain():
    td = _make_td(("term", True))
    result = scan_text_for_terms("The TERM is defined.", td, node_id="REQ-001", namespace="main")
    unmarked = [r for r in result if not r.marked and not r.wrong_marking]
    assert len(unmarked) == 1


def test_REQ_d00237_D_no_double_counting():
    """Marked position should not also produce an unmarked match."""
    td = _make_td(("widget", True))
    result = scan_text_for_terms(
        "A *widget* is a widget.",
        td,
        node_id="REQ-001",
        namespace="main",
        markup_styles=["*"],
    )
    marked = [r for r in result if r.marked]
    unmarked = [r for r in result if not r.marked and not r.wrong_marking]
    assert len(marked) == 1
    assert len(unmarked) == 1  # only the second, plain occurrence


# -- REQ-d00237-E: non-indexed terms ------------------------------------------


def test_REQ_d00237_E_non_indexed_skips_unmarked():
    td = _make_td(("widget", False))
    result = scan_text_for_terms("A widget is here.", td, node_id="REQ-001", namespace="main")
    assert len(result) == 0


def test_REQ_d00237_E_non_indexed_still_detects_marked():
    td = _make_td(("widget", False))
    result = scan_text_for_terms(
        "A *widget* is here.",
        td,
        node_id="REQ-001",
        namespace="main",
        markup_styles=["*"],
    )
    marked = [r for r in result if r.marked]
    assert len(marked) == 1


# =============================================================================
# scan_graph() tests
#
# Verifies: REQ-d00238
#
# Validates REQ-d00238-A+B+C+D: graph-level term scanning populates
# TermEntry.references by walking graph nodes.
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


def _mock_file_node(relative_path, file_type="SPEC"):
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


# -- REQ-d00238-A: scan_graph populates TermEntry.references ------------------


def test_REQ_d00238_A_populates_references():
    td = _make_td(("widget", True))
    req_node = _mock_node(NodeKind.REQUIREMENT, "REQ-001", label="The widget spec")
    file_node = _mock_file_node("spec/reqs.md")
    req_node.file_node.return_value = file_node
    graph = _mock_graph({NodeKind.REQUIREMENT: [req_node]})

    scan_graph(td, graph, namespace="main")

    entry = td.lookup("widget")
    assert entry is not None
    assert len(entry.references) > 0


def test_REQ_d00238_A_no_match_leaves_references_empty():
    td = _make_td(("gadget", True))
    req_node = _mock_node(NodeKind.REQUIREMENT, "REQ-001", label="The widget spec")
    file_node = _mock_file_node("spec/reqs.md")
    req_node.file_node.return_value = file_node
    graph = _mock_graph({NodeKind.REQUIREMENT: [req_node]})

    scan_graph(td, graph, namespace="main")

    entry = td.lookup("gadget")
    assert entry is not None
    assert len(entry.references) == 0


# -- REQ-d00238-B: full-text node kinds ---------------------------------------


def test_REQ_d00238_B_requirement_label_scanned():
    td = _make_td(("widget", True))
    req_node = _mock_node(NodeKind.REQUIREMENT, "REQ-001", label="A widget requirement")
    file_node = _mock_file_node("spec/reqs.md")
    req_node.file_node.return_value = file_node
    graph = _mock_graph({NodeKind.REQUIREMENT: [req_node]})

    scan_graph(td, graph, namespace="main")

    entry = td.lookup("widget")
    assert any(r.node_id == "REQ-001" for r in entry.references)


def test_REQ_d00238_B_assertion_label_scanned():
    td = _make_td(("widget", True))
    assertion_node = _mock_node(NodeKind.ASSERTION, "REQ-001-A", label="The widget shall work")
    file_node = _mock_file_node("spec/reqs.md")
    assertion_node.file_node.return_value = file_node
    graph = _mock_graph({NodeKind.ASSERTION: [assertion_node]})

    scan_graph(td, graph, namespace="main")

    entry = td.lookup("widget")
    assert any(r.node_id == "REQ-001-A" for r in entry.references)


def test_REQ_d00238_B_remainder_text_scanned():
    td = _make_td(("widget", True))
    remainder_node = _mock_node(
        NodeKind.REMAINDER,
        "REQ-001:remainder:1",
        fields={"text": "This describes the widget behavior.", "content_type": "prose"},
    )
    file_node = _mock_file_node("spec/reqs.md")
    remainder_node.file_node.return_value = file_node
    graph = _mock_graph({NodeKind.REMAINDER: [remainder_node]})

    scan_graph(td, graph, namespace="main")

    entry = td.lookup("widget")
    assert any(r.node_id == "REQ-001:remainder:1" for r in entry.references)


def test_REQ_d00238_B_remainder_definition_block_skipped():
    td = _make_td(("widget", True))
    remainder_node = _mock_node(
        NodeKind.REMAINDER,
        "REQ-001:remainder:1",
        fields={"text": "widget: a small device", "content_type": "definition_block"},
    )
    file_node = _mock_file_node("spec/reqs.md")
    remainder_node.file_node.return_value = file_node
    graph = _mock_graph({NodeKind.REMAINDER: [remainder_node]})

    scan_graph(td, graph, namespace="main")

    entry = td.lookup("widget")
    assert len(entry.references) == 0


def test_REQ_d00238_B_user_journey_body_scanned():
    td = _make_td(("widget", True))
    journey_node = _mock_node(
        NodeKind.USER_JOURNEY,
        "JNY-001",
        fields={"body": "User interacts with the widget panel."},
    )
    file_node = _mock_file_node("spec/journeys.md")
    journey_node.file_node.return_value = file_node
    graph = _mock_graph({NodeKind.USER_JOURNEY: [journey_node]})

    scan_graph(td, graph, namespace="main")

    entry = td.lookup("widget")
    assert any(r.node_id == "JNY-001" for r in entry.references)


# -- REQ-d00238-C: CODE and TEST nodes use comment extraction only ------------


def test_REQ_d00238_C_code_comment_found(tmp_path):
    td = _make_td(("widget", True))
    # Write a real Python file so extract_comments can tokenize/parse it
    py_file = tmp_path / "main.py"
    py_file.write_text("x = 1\n# widget handler\ny = 2\n")
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
    assert any(r.node_id == "file:src/main.py" for r in entry.references)
    # Line number should be 2 (the comment line)
    assert entry.references[0].line == 2


def test_REQ_d00238_C_code_non_comment_not_found(tmp_path):
    td = _make_td(("widget", True))
    py_file = tmp_path / "main.py"
    py_file.write_text("widget = 1\nresult = widget + 2\n")
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
    assert len(entry.references) == 0


# -- REQ-d00238-D: exclude_files glob patterns --------------------------------


def test_REQ_d00238_D_excluded_file_skipped():
    td = _make_td(("widget", True))
    file_node = _mock_file_node("docs/glossary.md")
    req_node = _mock_node(NodeKind.REQUIREMENT, "REQ-G01", label="The widget glossary")
    req_node.file_node.return_value = file_node
    graph = _mock_graph({NodeKind.REQUIREMENT: [req_node]})

    scan_graph(td, graph, namespace="main", exclude_files=["docs/glossary*"])

    entry = td.lookup("widget")
    assert len(entry.references) == 0


def test_REQ_d00238_D_non_excluded_file_not_skipped():
    td = _make_td(("widget", True))
    file_node = _mock_file_node("spec/reqs.md")
    req_node = _mock_node(NodeKind.REQUIREMENT, "REQ-001", label="The widget spec")
    req_node.file_node.return_value = file_node
    graph = _mock_graph({NodeKind.REQUIREMENT: [req_node]})

    scan_graph(td, graph, namespace="main", exclude_files=["docs/glossary*"])

    entry = td.lookup("widget")
    assert len(entry.references) > 0


# =============================================================================
# FederatedGraph._scan_terms() tests
#
# Verifies: REQ-d00239
#
# Validates REQ-d00239-A+B: federated term scanning runs across all repos
# using merged TermDictionary with per-repo config isolation.
# =============================================================================


# -- REQ-d00239-A: Cross-repo resolution using merged TermDictionary ----------


def test_REQ_d00239_A_cross_repo_term_resolution():
    """Term defined in repo A is found in repo B's requirement text."""
    # Build a merged TermDictionary with "widget" (defined in repo A)
    td = _make_td(("widget", True))

    # Repo B has a requirement mentioning "widget"
    req_node = _mock_node(NodeKind.REQUIREMENT, "REQ-B01", label="The widget controller")
    file_node = _mock_file_node("spec/controllers.md")
    req_node.file_node.return_value = file_node
    graph_b = _mock_graph({NodeKind.REQUIREMENT: [req_node]})

    # Simulate what _scan_terms does: call scan_graph with merged dict
    scan_graph(td, graph_b, namespace="repo-b")

    entry = td.lookup("widget")
    assert entry is not None
    refs = entry.references
    assert len(refs) == 1
    assert refs[0].node_id == "REQ-B01"
    assert refs[0].namespace == "repo-b"


def test_REQ_d00239_A_multiple_repos_accumulate_references():
    """References from multiple repos accumulate in the merged dictionary."""
    td = _make_td(("widget", True))

    # Repo A has a requirement mentioning "widget"
    req_a = _mock_node(NodeKind.REQUIREMENT, "REQ-A01", label="Widget design spec")
    file_a = _mock_file_node("spec/design.md")
    req_a.file_node.return_value = file_a
    graph_a = _mock_graph({NodeKind.REQUIREMENT: [req_a]})

    # Repo B also has a requirement mentioning "widget"
    req_b = _mock_node(NodeKind.REQUIREMENT, "REQ-B01", label="Widget integration test")
    file_b = _mock_file_node("spec/integration.md")
    req_b.file_node.return_value = file_b
    graph_b = _mock_graph({NodeKind.REQUIREMENT: [req_b]})

    # Scan both repos sequentially (as _scan_terms would)
    scan_graph(td, graph_a, namespace="repo-a")
    scan_graph(td, graph_b, namespace="repo-b")

    entry = td.lookup("widget")
    assert len(entry.references) == 2
    namespaces = {r.namespace for r in entry.references}
    assert namespaces == {"repo-a", "repo-b"}


def test_REQ_d00239_A_scan_terms_method_exists_and_calls_scan_graph():
    """FederatedGraph._scan_terms() exists and invokes scan_graph per repo."""
    from pathlib import Path
    from unittest.mock import patch

    from elspais.graph.federated import FederatedGraph, RepoEntry
    from elspais.graph.terms import TermDictionary

    # _scan_terms must exist on FederatedGraph
    assert hasattr(
        FederatedGraph, "_scan_terms"
    ), "FederatedGraph._scan_terms() method does not exist yet"

    # Build minimal RepoEntry mocks
    graph_a = _mock_graph({})
    graph_b = _mock_graph({})
    graph_a._terms = TermDictionary()
    graph_b._terms = TermDictionary()
    graph_a._index = {}
    graph_b._index = {}

    entry_a = RepoEntry(
        name="repo-a",
        graph=graph_a,
        config={"terms": {"markup_styles": ["*"]}},
        repo_root=Path("/tmp/repo-a"),
    )
    entry_b = RepoEntry(
        name="repo-b",
        graph=graph_b,
        config={"terms": {"markup_styles": ["**"]}},
        repo_root=Path("/tmp/repo-b"),
    )

    with patch("elspais.graph.term_scanner.scan_graph") as mock_scan:
        fg = FederatedGraph(repos=[entry_a, entry_b])
        # _scan_terms should have been called during __init__
        fg._scan_terms()

        assert mock_scan.call_count >= 2
        call_namespaces = {
            call.kwargs.get("namespace") or call.args[2] for call in mock_scan.call_args_list
        }
        assert "repo-a" in call_namespaces
        assert "repo-b" in call_namespaces


# -- REQ-d00239-B: Per-repo config for markup_styles and exclude_files --------


def test_REQ_d00239_B_per_repo_markup_styles():
    """Each repo's scan uses its own markup_styles config."""
    td = _make_td(("widget", True))

    # Repo A config allows '*' markup -> *widget* is correctly marked
    req_a = _mock_node(NodeKind.REQUIREMENT, "REQ-A01", label="A *widget* spec")
    file_a = _mock_file_node("spec/reqs.md")
    req_a.file_node.return_value = file_a
    graph_a = _mock_graph({NodeKind.REQUIREMENT: [req_a]})

    # Repo B config only allows '**' markup -> *widget* is wrong marking
    req_b = _mock_node(NodeKind.REQUIREMENT, "REQ-B01", label="A *widget* spec")
    file_b = _mock_file_node("spec/reqs.md")
    req_b.file_node.return_value = file_b
    graph_b = _mock_graph({NodeKind.REQUIREMENT: [req_b]})

    # Scan repo A with its config (markup_styles=["*"])
    scan_graph(td, graph_a, namespace="repo-a", markup_styles=["*"])
    # Scan repo B with its config (markup_styles=["**"])
    scan_graph(td, graph_b, namespace="repo-b", markup_styles=["**"])

    entry = td.lookup("widget")
    refs_a = [r for r in entry.references if r.namespace == "repo-a"]
    refs_b = [r for r in entry.references if r.namespace == "repo-b"]

    # Repo A: '*' is in its markup_styles -> marked=True, no wrong_marking
    assert len(refs_a) == 1
    assert refs_a[0].marked is True
    assert refs_a[0].wrong_marking == ""

    # Repo B: '*' is NOT in its markup_styles -> wrong_marking="*"
    assert len(refs_b) == 1
    assert refs_b[0].wrong_marking == "*"
    assert refs_b[0].marked is False


def test_REQ_d00239_B_per_repo_exclude_files():
    """Each repo's scan uses its own exclude_files config."""
    td = _make_td(("widget", True))

    # Both repos have a requirement in docs/glossary.md
    req_a = _mock_node(NodeKind.REQUIREMENT, "REQ-A01", label="Widget glossary entry")
    file_a = _mock_file_node("docs/glossary.md")
    req_a.file_node.return_value = file_a
    graph_a = _mock_graph({NodeKind.REQUIREMENT: [req_a]})

    req_b = _mock_node(NodeKind.REQUIREMENT, "REQ-B01", label="Widget glossary entry")
    file_b = _mock_file_node("docs/glossary.md")
    req_b.file_node.return_value = file_b
    graph_b = _mock_graph({NodeKind.REQUIREMENT: [req_b]})

    # Repo A excludes glossary files; repo B does not
    scan_graph(td, graph_a, namespace="repo-a", exclude_files=["docs/glossary*"])
    scan_graph(td, graph_b, namespace="repo-b", exclude_files=[])

    entry = td.lookup("widget")
    refs_a = [r for r in entry.references if r.namespace == "repo-a"]
    refs_b = [r for r in entry.references if r.namespace == "repo-b"]

    # Repo A: glossary excluded -> no references
    assert len(refs_a) == 0
    # Repo B: glossary not excluded -> reference found
    assert len(refs_b) == 1


def test_REQ_d00239_B_scan_terms_passes_per_repo_config():
    """_scan_terms passes each repo's terms config to scan_graph."""
    from pathlib import Path
    from unittest.mock import patch

    from elspais.graph.federated import FederatedGraph, RepoEntry
    from elspais.graph.terms import TermDictionary

    # _scan_terms must exist on FederatedGraph
    assert hasattr(
        FederatedGraph, "_scan_terms"
    ), "FederatedGraph._scan_terms() method does not exist yet"

    graph_a = _mock_graph({})
    graph_a._terms = TermDictionary()
    graph_a._index = {}

    graph_b = _mock_graph({})
    graph_b._terms = TermDictionary()
    graph_b._index = {}

    entry_a = RepoEntry(
        name="repo-a",
        graph=graph_a,
        config={"terms": {"markup_styles": ["*"], "exclude_files": ["docs/*"]}},
        repo_root=Path("/tmp/repo-a"),
    )
    entry_b = RepoEntry(
        name="repo-b",
        graph=graph_b,
        config={"terms": {"markup_styles": ["**"], "exclude_files": []}},
        repo_root=Path("/tmp/repo-b"),
    )

    with patch("elspais.graph.term_scanner.scan_graph") as mock_scan:
        fg = FederatedGraph(repos=[entry_a, entry_b])
        fg._scan_terms()

        # Find the call for each repo
        calls_by_ns = {}
        for call in mock_scan.call_args_list:
            ns = call.kwargs.get("namespace") or call.args[2]
            calls_by_ns[ns] = call

        assert "repo-a" in calls_by_ns
        assert "repo-b" in calls_by_ns

        # Repo A should get markup_styles=["*"] and exclude_files=["docs/*"]
        call_a = calls_by_ns["repo-a"]
        assert call_a.kwargs.get("markup_styles") == ["*"]
        assert call_a.kwargs.get("exclude_files") == ["docs/*"]

        # Repo B should get markup_styles=["**"] and exclude_files=[]
        call_b = calls_by_ns["repo-b"]
        assert call_b.kwargs.get("markup_styles") == ["**"]
        assert call_b.kwargs.get("exclude_files") == []


# -- REQ-d00237-D: auto-marker skips terms inside outer emphasis spans -------
# Without this guard, a term occurrence inside a longer **bold phrase**
# gets wrapped again, producing `****term**...**` which pandoc renders
# as literal asterisks.


def _td_with_term(term: str) -> TermDictionary:
    td = TermDictionary()
    td.add(
        TermEntry(
            term=term,
            definition=f"A {term}.",
            namespace="test",
            defined_in="REQ-p00001",
        )
    )
    return td


def test_REQ_d00237_D_skip_term_inside_outer_bold_phrase():
    """A defined term that appears inside a longer **bold ...** phrase
    must NOT be re-wrapped — the outer emphasis already satisfies the
    convention. Re-wrapping produces `****term** ...**` literal text."""
    td = _td_with_term("Diary")
    text = "The **Diary Start Day** is configurable."
    result, _ = _canonicalize_text(text, td, "**", {"*", "**"})
    assert result == text, f"term inside outer bold should be left alone, got: {result!r}"


def test_REQ_d00237_D_skip_term_inside_outer_italic_phrase():
    """Same rule applies to single-asterisk italic spans."""
    td = _td_with_term("Diary")
    text = "The *Diary Start Day* is configurable."
    result, _ = _canonicalize_text(text, td, "**", {"*", "**"})
    assert result == text


def test_REQ_d00237_D_wrap_term_outside_emphasis_unchanged():
    """Verifies the guard doesn't over-correct — plain occurrences of
    the term in non-emphasis prose are still auto-marked."""
    td = _td_with_term("Diary")
    text = "Open the Diary."
    result, _ = _canonicalize_text(text, td, "**", {"*", "**"})
    assert result == "Open the **Diary**."


def test_REQ_d00237_D_canonical_bold_term_left_alone():
    """A term that IS the entire bold phrase (canonical form) must
    still be recognized as canonical and not double-wrapped."""
    td = _td_with_term("Participant")
    text = "Define **Participant** here."
    result, _ = _canonicalize_text(text, td, "**", {"*", "**"})
    assert result == text


# =============================================================================
# REQ-d00237-F: terms embedded in compound identifiers
#
# A whole-word (\b) match that is a proper part of a larger compound token
# (e.g. a requirement ID like CAL-PRD-portal-Session-configuration) is still
# recorded as a reference but is NOT free-standing prose: it is flagged
# embedded=True so it is neither auto-marked nor reported as a violation.
# =============================================================================


def _offsets(text: str, term: str) -> tuple[int, int]:
    """Return (start, end) of *term* within *text* via str.find."""
    start = text.find(term)
    assert start != -1, f"{term!r} not found in {text!r}"
    return start, start + len(term)


# -- REQ-d00237-F: the _is_embedded_in_compound predicate ---------------------


def test_REQ_d00237_F_embedded_predicate_true_for_compound_ids():
    """A term that is one sub-token of a larger compound identifier is
    embedded — the surrounding non-whitespace token has other alnum chars."""
    for compound in (
        "CAL-PRD-portal-Session-configuration",
        "Session-based",
        "path/Session/config",
    ):
        start, end = _offsets(compound, "Session")
        assert (
            _is_embedded_in_compound(compound, start, end) is True
        ), f"{compound!r} should be embedded"


def test_REQ_d00237_F_embedded_predicate_false_for_free_standing_prose():
    """Free-standing prose occurrences (with optional trailing punctuation
    or wrapping parens) are NOT embedded."""
    for text in (
        "The Session expired",
        "End of Session.",
        "(Session)",
        "Start Session here",
    ):
        start, end = _offsets(text, "Session")
        assert (
            _is_embedded_in_compound(text, start, end) is False
        ), f"{text!r} should NOT be embedded"


# -- REQ-d00237-F: scan_text_for_terms flags embedded refs but keeps them -----


def test_REQ_d00237_F_scan_flags_embedded_compound_id_but_records_it():
    """A term inside a hyphenated compound ID yields a TermRef with
    embedded=True that IS present in the result and in entry.references
    (the index still counts it)."""
    td = _make_td(("Session", True))
    text = "Configure CAL-PRD-portal-Session-configuration now."
    result = scan_text_for_terms(text, td, node_id="REQ-001", namespace="main")

    assert len(result) == 1
    assert result[0].embedded is True
    # Still recorded on the entry so the index counts the reference.
    entry = td.lookup("Session")
    assert entry is not None
    assert len(entry.references) == 1
    assert entry.references[0].embedded is True


def test_REQ_d00237_F_scan_free_standing_prose_is_not_embedded():
    """A free-standing prose occurrence yields embedded=False — contrast
    with the compound-ID case so the flag is meaningfully set."""
    td = _make_td(("Session", True))
    result = scan_text_for_terms("The Session expired.", td, node_id="REQ-001", namespace="main")

    assert len(result) == 1
    assert result[0].embedded is False


# -- REQ-d00237-F: canonicalization skips embedded refs -----------------------


def test_REQ_d00237_F_canonicalize_skips_term_in_compound_id():
    """The auto-marker must NOT wrap a term that is a sub-token of a
    compound identifier — the ID is returned unchanged with no replacement."""
    td = _td_with_term("Session")
    text = "Configure CAL-PRD-portal-Session-configuration now."
    result, repls = _canonicalize_text(text, td, "*", {"*", "**"})

    assert result == text, f"compound ID should be left unchanged, got: {result!r}"
    assert repls == []


def test_REQ_d00237_F_canonicalize_still_marks_free_standing_term():
    """Sanity contrast: a free-standing occurrence of the SAME term IS
    still auto-marked — embedding didn't disable marking entirely."""
    td = _td_with_term("Session")
    text = "The Session expired."
    result, repls = _canonicalize_text(text, td, "*", {"*", "**"})

    assert result == "The *Session* expired."
    assert repls == [("Session", "*Session*")]


# =============================================================================
# REQ-d00237-G: leftmost-longest (maximal munch) nested-defined-term handling
#
# When one defined term's text contains another (e.g. "Sponsor Portal" contains
# "Sponsor"), matching is leftmost-longest and INDEPENDENT of the order the
# terms were defined/inserted. Both scan_text_for_terms and _canonicalize_text
# iterate terms longest-first (_terms_longest_first) and claim matched spans so
# a shorter nested term does not also match inside a longer one. The shorter
# term still matches where it stands alone.
#
# These tests are parametrized over BOTH insertion orders; under the old
# order-dependent logic the [Sponsor, Sponsor Portal] order produced a spurious
# unmarked "Sponsor" ref and canonicalized to "The *Sponsor* Portal is here.".
# =============================================================================


def _td_nested(*terms: str, indexed: bool = True) -> TermDictionary:
    """Build a TermDictionary inserting *terms* in the given order."""
    td = TermDictionary()
    for term in terms:
        td.add(
            TermEntry(
                term=term,
                definition=f"A {term}.",
                namespace="test",
                defined_in="REQ-p00001",
                indexed=indexed,
            )
        )
    return td


# Both insertion orders of the nested pair. The first order is the one that
# regressed before the fix; both must now yield identical outcomes.
_NESTED_ORDERS = [
    pytest.param(("Sponsor", "Sponsor Portal"), id="inner-first"),
    pytest.param(("Sponsor Portal", "Sponsor"), id="compound-first"),
]


# -- REQ-d00237-G: _terms_longest_first ordering ------------------------------


def test_REQ_d00237_G_terms_longest_first_descending_length():
    """_terms_longest_first orders entries by descending term length,
    breaking ties deterministically on the term string."""
    # "Beta" and "Acme" are a length tie -> alphabetical break ("Acme" first).
    td = _td_nested("Sponsor", "Sponsor Portal Admin", "Sponsor Portal", "Beta", "Acme")
    ordered = [e.term for e in _terms_longest_first(td)]

    assert ordered == [
        "Sponsor Portal Admin",  # 20 chars
        "Sponsor Portal",  # 14 chars
        "Sponsor",  # 7 chars
        "Acme",  # 4 chars, tie -> alphabetical
        "Beta",  # 4 chars
    ]


def test_REQ_d00237_G_terms_longest_first_order_independent():
    """The ordering is independent of insertion order — inserting the
    same terms reversed yields the same longest-first sequence."""
    forward = [e.term for e in _terms_longest_first(_td_nested("Sponsor", "Sponsor Portal"))]
    reverse = [e.term for e in _terms_longest_first(_td_nested("Sponsor Portal", "Sponsor"))]

    assert forward == reverse == ["Sponsor Portal", "Sponsor"]


# -- REQ-d00237-G: scan plain compound — only the longer term matches ----------


@pytest.mark.parametrize("order", _NESTED_ORDERS)
def test_REQ_d00237_G_scan_plain_compound_only_longest(order):
    """A plain "Sponsor Portal" yields exactly one unmarked "Sponsor Portal"
    ref and NO separate "Sponsor" ref, regardless of insertion order."""
    td = _td_nested(*order)
    result = scan_text_for_terms(
        "The Sponsor Portal is here.", td, node_id="REQ-001", namespace="main"
    )

    surfaces = [r.surface_form for r in result]
    assert surfaces == ["Sponsor Portal"]
    assert result[0].marked is False
    assert result[0].wrong_marking == ""
    # The inner term must NOT also be recorded inside the claimed compound span.
    assert "Sponsor" not in surfaces


@pytest.mark.parametrize("order", _NESTED_ORDERS)
def test_REQ_d00237_G_scan_marked_compound_only_longest(order):
    """A marked "*Sponsor Portal*" yields exactly one marked "Sponsor Portal"
    ref and no spurious unmarked "Sponsor", in either insertion order."""
    td = _td_nested(*order)
    result = scan_text_for_terms(
        "The *Sponsor Portal* is here.",
        td,
        node_id="REQ-001",
        namespace="main",
        markup_styles=["*", "**"],
    )

    assert len(result) == 1
    assert result[0].surface_form == "Sponsor Portal"
    assert result[0].marked is True
    assert result[0].wrong_marking == ""


@pytest.mark.parametrize("order", _NESTED_ORDERS)
def test_REQ_d00237_G_scan_standalone_inner_still_matches(order):
    """The shorter nested term still matches where it appears on its own
    (no enclosing compound), independent of insertion order."""
    td = _td_nested(*order)
    result = scan_text_for_terms(
        "The Sponsor approved it.", td, node_id="REQ-001", namespace="main"
    )

    assert len(result) == 1
    assert result[0].surface_form == "Sponsor"
    assert result[0].marked is False
    assert result[0].wrong_marking == ""


@pytest.mark.parametrize("order", _NESTED_ORDERS)
def test_REQ_d00237_G_scan_mixed_compound_and_standalone(order):
    """Text with BOTH a compound usage and a separate standalone inner usage
    yields one "Sponsor Portal" ref AND one standalone "Sponsor" ref —
    the inner term is claimed inside the compound but free elsewhere."""
    td = _td_nested(*order)
    result = scan_text_for_terms(
        "The Sponsor Portal is run by the Sponsor.",
        td,
        node_id="REQ-001",
        namespace="main",
    )

    surfaces = sorted(r.surface_form for r in result)
    assert surfaces == ["Sponsor", "Sponsor Portal"]
    # Exactly one of each — no double-counting of the inner term in the compound.
    assert surfaces.count("Sponsor") == 1
    assert surfaces.count("Sponsor Portal") == 1


# -- REQ-d00237-G: canonicalization wraps the compound as a whole --------------


@pytest.mark.parametrize("order", _NESTED_ORDERS)
def test_REQ_d00237_G_canonicalize_wraps_compound_as_whole(order):
    """_canonicalize_text wraps the full compound "Sponsor Portal" rather
    than its inner "Sponsor" — same result in either insertion order.
    Under the old order-dependent logic, [Sponsor, Sponsor Portal] produced
    "The *Sponsor* Portal is here." instead."""
    td = _td_nested(*order)
    result, repls = _canonicalize_text("The Sponsor Portal is here.", td, "*", {"*", "**"})

    assert result == "The *Sponsor Portal* is here."
    assert repls == [("Sponsor Portal", "*Sponsor Portal*")]


# -- REQ-d00237-G: three-level nest — longest wins -----------------------------


@pytest.mark.parametrize(
    "order",
    [
        pytest.param(("Sponsor", "Sponsor Portal", "Sponsor Portal Admin"), id="shortest-first"),
        pytest.param(("Sponsor Portal Admin", "Sponsor Portal", "Sponsor"), id="longest-first"),
    ],
)
def test_REQ_d00237_G_three_level_nest_longest_wins(order):
    """With three nested terms, the longest enclosing term claims the span;
    the two shorter terms do not separately match inside it."""
    td = _td_nested(*order)
    result = scan_text_for_terms(
        "Contact the Sponsor Portal Admin today.",
        td,
        node_id="REQ-001",
        namespace="main",
    )

    surfaces = [r.surface_form for r in result]
    assert surfaces == ["Sponsor Portal Admin"]
