"""Tests for extract_comments() in term_scanner.

# Implements: REQ-d00236

Validates REQ-d00236-A+B+C+D+E+F+G: comment extraction from source
code across multiple language families.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from elspais.graph.GraphNode import NodeKind
from elspais.graph.term_scanner import extract_comments, scan_graph, scan_text_for_terms
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


def test_REQ_d00236_B_python_docstring_function():
    source = 'def foo():\n    """This is a docstring."""\n    pass\n'
    result = extract_comments(source, ".py")
    texts = [t for t, _ in result]
    assert any("This is a docstring" in t for t in texts)


def test_REQ_d00236_B_python_docstring_class():
    source = 'class Foo:\n    """Class docstring."""\n    pass\n'
    result = extract_comments(source, ".py")
    texts = [t for t, _ in result]
    assert any("Class docstring" in t for t in texts)


def test_REQ_d00236_B_python_docstring_module():
    source = '"""Module-level docstring."""\nimport os\n'
    result = extract_comments(source, ".py")
    texts = [t for t, _ in result]
    assert any("Module-level docstring" in t for t in texts)


def test_REQ_d00236_B_python_multiline_docstring():
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
    assert any("First line" in t and "Second paragraph" in t for t in texts)


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
# Implements: REQ-d00237
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
# Implements: REQ-d00238
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


def _mock_graph(nodes_by_kind):
    """Create a minimal mock TraceGraph."""
    graph = MagicMock()

    def iter_by_kind(kind):
        return iter(nodes_by_kind.get(kind, []))

    graph.iter_by_kind.side_effect = iter_by_kind
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


def test_REQ_d00238_C_code_comment_found():
    td = _make_td(("widget", True))
    file_node = _mock_file_node("src/main.py")
    file_node.get_field.side_effect = lambda k: {
        "relative_path": "src/main.py",
        "file_type": "CODE",
    }.get(k)
    code_node = _mock_node(
        NodeKind.CODE,
        "code:src/main.py:1",
        fields={"raw_text": "x = 1\n# widget handler\ny = 2\n"},
    )
    code_node.file_node.return_value = file_node
    graph = _mock_graph({NodeKind.CODE: [code_node]})

    scan_graph(td, graph, namespace="main")

    entry = td.lookup("widget")
    assert any(r.node_id == "code:src/main.py:1" for r in entry.references)


def test_REQ_d00238_C_code_non_comment_not_found():
    td = _make_td(("widget", True))
    file_node = _mock_file_node("src/main.py")
    file_node.get_field.side_effect = lambda k: {
        "relative_path": "src/main.py",
        "file_type": "CODE",
    }.get(k)
    code_node = _mock_node(
        NodeKind.CODE,
        "code:src/main.py:1",
        fields={"raw_text": "widget = 1\nresult = widget + 2\n"},
    )
    code_node.file_node.return_value = file_node
    graph = _mock_graph({NodeKind.CODE: [code_node]})

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
# Implements: REQ-d00239
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
