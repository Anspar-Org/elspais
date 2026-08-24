"""Tests for prescan utility functions.

Exercises the standalone prescan module extracted from CodeParser and
TestParser.

The tests that bind a scanned test to its identity within its file and to
that test's line extent name REQ-d00254-K, which obliges exactly that, on
both the built-in and the external-record routes.

The rest are deliberately uncited.  Extension-to-language detection and
line-context tracking over ordinary (non-test) code answer to no assertion
in the estate, and the sentinel test pins the *absence* of extent on the
text route rather than its presence.  Naming an assertion they do not
establish would report coverage the estate has not earned.
"""

import pytest

from elspais.graph.parsers.prescan import (
    ast_prescan,
    build_line_context,
    detect_language,
    external_prescan,
    text_prescan,
)


class TestDetectLanguage:
    """Tests for detect_language utility."""

    def test_python_extension(self):
        assert detect_language("foo/bar.py") == "python"

    def test_pyw_extension(self):
        assert detect_language("script.pyw") == "python"

    def test_js_extension(self):
        assert detect_language("app.js") == "js"

    def test_ts_extension(self):
        assert detect_language("app.ts") == "js"

    def test_tsx_extension(self):
        assert detect_language("component.tsx") == "js"

    def test_go_extension(self):
        assert detect_language("main.go") == "go"

    def test_rust_extension(self):
        assert detect_language("lib.rs") == "rust"

    def test_clang_extension(self):
        assert detect_language("main.c") == "c"

    def test_java_extension(self):
        assert detect_language("App.java") == "c"

    def test_unknown_extension(self):
        assert detect_language("readme.txt") == "unknown"

    def test_no_extension(self):
        assert detect_language("Makefile") == "unknown"


class TestBuildLineContext:
    """Tests for build_line_context utility."""

    def test_python_function_context(self):
        """Function context is tracked for Python files."""
        lines = [
            (1, "def hello():"),
            (2, "    print('hi')"),
            (3, ""),
            (4, "def world():"),
            (5, "    print('world')"),
        ]
        ctx = build_line_context(lines, "python")
        assert ctx[1][0] == "hello"
        assert ctx[2][0] == "hello"
        assert ctx[4][0] == "world"
        assert ctx[5][0] == "world"

    def test_python_class_context(self):
        """Class context is tracked for Python files."""
        lines = [
            (1, "class MyClass:"),
            (2, "    def method(self):"),
            (3, "        pass"),
        ]
        ctx = build_line_context(lines, "python")
        assert ctx[2][1] == "MyClass"
        assert ctx[3][1] == "MyClass"

    def test_forward_looking_fixup(self):
        """Comment above a function gets the function's context."""
        lines = [
            (1, "# Implements: REQ-p00001"),
            (2, "def my_func():"),
            (3, "    pass"),
        ]
        ctx = build_line_context(lines, "python")
        # Line 1 (comment) should pick up my_func from forward-looking fixup
        assert ctx[1][0] == "my_func"

    def test_js_brace_scoping(self):
        """Brace-based scoping works for JS files."""
        lines = [
            (1, "function hello() {"),
            (2, "    console.log('hi');"),
            (3, "}"),
            (4, "function world() {"),
            (5, "    console.log('world');"),
            (6, "}"),
        ]
        ctx = build_line_context(lines, "js")
        assert ctx[1][0] == "hello"
        assert ctx[2][0] == "hello"
        assert ctx[4][0] == "world"
        assert ctx[5][0] == "world"


class TestTextPrescan:
    """Tests for text_prescan utility."""

    def test_REQ_d00254_K_finds_test_functions(self):
        """Text prescan identifies test_ functions."""
        lines = [
            (1, "import pytest"),
            (2, ""),
            (3, "def test_something():"),
            (4, "    assert True"),
            (5, ""),
            (6, "def test_another():"),
            (7, "    assert True"),
        ]
        line_context, all_test_funcs, first_def_line = text_prescan(lines)
        assert len(all_test_funcs) == 2
        assert all_test_funcs[0] == (3, "test_something", None)
        assert all_test_funcs[1] == (6, "test_another", None)
        assert first_def_line == 3

    def test_REQ_d00254_K_finds_test_class(self):
        """Text prescan identifies Test classes."""
        lines = [
            (1, "class TestFoo:"),
            (2, "    def test_bar(self):"),
            (3, "        assert True"),
        ]
        line_context, all_test_funcs, first_def_line = text_prescan(lines)
        assert len(all_test_funcs) == 1
        assert all_test_funcs[0] == (2, "test_bar", "TestFoo")
        assert first_def_line == 1

    def test_REQ_d00254_K_line_context_maps_correctly(self):
        """Line context maps each line to its enclosing function."""
        lines = [
            (1, "def test_one():"),
            (2, "    x = 1"),
            (3, "    assert x == 1"),
        ]
        line_context, _, _ = text_prescan(lines)
        assert line_context[1][0] == "test_one"
        assert line_context[2][0] == "test_one"
        assert line_context[3][0] == "test_one"


class TestAstPrescan:
    """Tests for ast_prescan utility."""

    def test_REQ_d00254_K_finds_module_level_test(self):
        """AST prescan finds module-level test functions."""
        source = "def test_foo():\n    assert True\n"
        lines = [(1, "def test_foo():"), (2, "    assert True")]
        line_context, all_test_funcs, first_def_line = ast_prescan(source, lines)
        assert len(all_test_funcs) == 1
        assert all_test_funcs[0][1] == "test_foo"
        assert all_test_funcs[0][2] is None  # no class

    def test_REQ_d00254_K_finds_class_test(self):
        """AST prescan finds test functions inside Test classes."""
        source = "class TestBar:\n    def test_baz(self):\n        pass\n"
        lines = [
            (1, "class TestBar:"),
            (2, "    def test_baz(self):"),
            (3, "        pass"),
        ]
        line_context, all_test_funcs, first_def_line = ast_prescan(source, lines)
        assert len(all_test_funcs) == 1
        assert all_test_funcs[0][1] == "test_baz"
        assert all_test_funcs[0][2] == "TestBar"


class TestExternalPrescan:
    """Tests for external_prescan utility."""

    def test_REQ_d00254_K_builds_context_from_entries(self):
        """External prescan builds line context from provided entries."""
        entries = [
            {"function": "test_alpha", "class": None, "line": 5},
            {"function": "test_beta", "class": "TestSuite", "line": 15},
        ]
        lines = [(i, f"line {i}") for i in range(1, 21)]
        line_context, all_test_funcs, first_def_line = external_prescan(entries, lines)
        assert first_def_line == 5
        assert len(all_test_funcs) == 2
        # Line 5 should be in test_alpha context
        assert line_context[5][0] == "test_alpha"
        # Line 15 should be in test_beta context
        assert line_context[15][0] == "test_beta"
        assert line_context[15][1] == "TestSuite"


class TestPrescanFuncEndLine:
    """Tests that prescan functions return 4-tuples with func_end_line."""

    def test_REQ_d00254_K_ast_prescan_returns_4_tuples(self):
        """ast_prescan line_context values are 4-tuples with func_end_line."""
        source = "def test_foo():\n    assert True\n\ndef test_bar():\n    x = 1\n    assert x\n"
        lines = [
            (1, "def test_foo():"),
            (2, "    assert True"),
            (3, ""),
            (4, "def test_bar():"),
            (5, "    x = 1"),
            (6, "    assert x"),
        ]
        line_context, _, _ = ast_prescan(source, lines)
        # Each value should be a 4-tuple
        for ln, val in line_context.items():
            assert len(val) == 4, f"line {ln}: expected 4-tuple, got {len(val)}-tuple"
        # Line 1 is inside test_foo (lines 1-2), func_end_line should be 2
        assert line_context[1] == ("test_foo", None, 1, 2)
        # Line 4 is inside test_bar (lines 4-6), func_end_line should be 6
        assert line_context[4] == ("test_bar", None, 4, 6)
        # Line 3 is outside any function
        assert line_context[3] == (None, None, 0, 0)

    def test_REQ_d00254_K_ast_prescan_class_method_end_line(self):
        """ast_prescan returns correct func_end_line for class methods."""
        source = "class TestBar:\n    def test_baz(self):\n        pass\n"
        lines = [
            (1, "class TestBar:"),
            (2, "    def test_baz(self):"),
            (3, "        pass"),
        ]
        line_context, _, _ = ast_prescan(source, lines)
        # Line 2 is inside test_baz, end line is 3
        assert line_context[2][3] == 3  # func_end_line
        assert line_context[2][:3] == ("test_baz", "TestBar", 2)

    def test_text_prescan_returns_4_tuples_with_sentinel(self):
        """text_prescan returns 4-tuples with func_end_line=0 as sentinel."""
        lines = [
            (1, "def test_one():"),
            (2, "    assert True"),
        ]
        line_context, _, _ = text_prescan(lines)
        for ln, val in line_context.items():
            assert len(val) == 4, f"line {ln}: expected 4-tuple, got {len(val)}-tuple"
        # func_end_line is 0 (sentinel) since text_prescan can't determine it
        assert line_context[1][3] == 0
        assert line_context[2][3] == 0

    def test_REQ_d00254_K_external_prescan_returns_4_tuples(self):
        """external_prescan returns 4-tuples with func_end_line."""
        entries = [
            {"function": "test_alpha", "class": None, "line": 5},
            {"function": "test_beta", "class": "TestSuite", "line": 15},
        ]
        lines = [(i, f"line {i}") for i in range(1, 21)]
        line_context, _, _ = external_prescan(entries, lines)
        for ln, val in line_context.items():
            assert len(val) == 4, f"line {ln}: expected 4-tuple, got {len(val)}-tuple"
        # test_alpha spans lines 5-14 (next func starts at 15)
        assert line_context[5][3] == 14  # func_end_line
        # test_beta spans lines 15-20 (end of file)
        assert line_context[15][3] == 20  # func_end_line

    def test_REQ_d00254_K_external_prescan_with_explicit_end_line(self):
        """external_prescan uses end_line from JSON entries when present."""
        entries = [
            {"function": "test_alpha", "class": None, "line": 5, "end_line": 10},
            {"function": "test_beta", "class": "TestSuite", "line": 15, "end_line": 18},
        ]
        lines = [(i, f"line {i}") for i in range(1, 21)]
        line_context, _, _ = external_prescan(entries, lines)
        # end_line from JSON should be used
        assert line_context[5][3] == 10
        assert line_context[15][3] == 18

    def test_REQ_d00254_K_ast_prescan_forward_fixup_4_tuple(self):
        """Forward-looking fixup in ast_prescan produces 4-tuples."""
        source = "# Implements: REQ-p00001\ndef test_foo():\n    assert True\n"
        lines = [
            (1, "# Implements: REQ-p00001"),
            (2, "def test_foo():"),
            (3, "    assert True"),
        ]
        line_context, _, _ = ast_prescan(source, lines)
        # Line 1 should get fixup from test_foo, and be a 4-tuple
        assert len(line_context[1]) == 4
        assert line_context[1][0] == "test_foo"
        assert line_context[1][3] == 3  # func_end_line of test_foo


# ---------------------------------------------------------------------------
# Forward binding, shared by every built-in route
#
# A comment carrying a citation describes the declaration below it.  The three
# built-in routes -- ast_prescan (Python), text_prescan (the fallback for every
# other language) and build_line_context (ordinary code) -- answer that the
# same way: walk down from the unowned comment while only further comments and
# blank lines are met, and bind at the first declaration reached.  The length
# of the comment block is not a bound on the search; the first line that is
# neither a comment nor a declaration is.
#
# These name REQ-d00254-K.  Binding a citation to the test it was written above
# is how that test's evidence reaches that test's identity and extent, and
# binding one to a declaration it was not written above would attribute
# evidence to a test it says nothing about.
# ---------------------------------------------------------------------------


def _numbered(source: str) -> list[tuple[int, str]]:
    return [(i + 1, text) for i, text in enumerate(source.rstrip("\n").split("\n"))]


def _via_ast(source: str):
    line_context, _funcs, _first = ast_prescan(source, _numbered(source))
    return line_context


def _via_text(source: str):
    line_context, _funcs, _first = text_prescan(_numbered(source))
    return line_context


def _via_line_context(source: str):
    return build_line_context(_numbered(source), "python")


ROUTES = [
    pytest.param(_via_ast, id="ast_prescan"),
    pytest.param(_via_text, id="text_prescan"),
    pytest.param(_via_line_context, id="build_line_context"),
]


# A citation six lines above its declaration, and a second citation two lines
# above it.  Both name the same test and both must bind to it.
#   1: # Verifies: REQ-p00001-A   <- reachable by no five-line window
#   6: # Verifies: REQ-p00001-B
#   7: def test_alpha():
LONG_PROSE = """\
# Verifies: REQ-p00001-A
# The test below is described at length because the shape of a comment
# block says nothing about what it describes: a citation may sit above
# six lines of prose or above one, and it describes the same
# declaration either way.
# Verifies: REQ-p00001-B
def test_alpha():
    assert True
"""

# A citation written one line above its declaration -- the ordinary shape, kept
# beside the long one so the pair distinguishes "no window" from "a window".
SHORT_PROSE = """\
# Verifies: REQ-p00001-A
def test_alpha():
    assert True
"""

# A file header, a blank line, and then an import.  The import is neither a
# comment nor a declaration, so it ends the search: the header describes the
# file and must not claim the first test in it.
#   1: # Copyright 2026 Example.
#   2: # Verifies: REQ-p00001-A
#   4: import pytest
#   7: def test_alpha():
HEADER_THEN_IMPORT = """\
# Copyright 2026 Example.
# Verifies: REQ-p00001-A

import pytest


def test_alpha():
    assert True
"""

# The same header with the import removed: only blank lines stand between it
# and the declaration, so it does bind.  This is what makes the case above a
# statement about the import rather than about the distance.
HEADER_NO_IMPORT = """\
# Copyright 2026 Example.
# Verifies: REQ-p00001-A


def test_alpha():
    assert True
"""


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize(
    ("source", "comment_line", "declaration_line"),
    [
        pytest.param(LONG_PROSE, 1, 7, id="citation-above-five-prose-lines"),
        pytest.param(LONG_PROSE, 6, 7, id="second-citation-above-same-test"),
        pytest.param(SHORT_PROSE, 1, 2, id="citation-directly-above"),
        pytest.param(HEADER_NO_IMPORT, 2, 5, id="header-reaching-declaration-over-blanks"),
    ],
)
def test_REQ_d00254_K_comment_binds_to_first_declaration_below(
    route, source, comment_line, declaration_line
):
    """A citation is attributed to the declaration below it, at any distance."""
    line_context = route(source)
    func_name, _class_name, func_line, _end = line_context[comment_line]
    assert func_name == "test_alpha"
    assert func_line == declaration_line


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize(
    "comment_line",
    [pytest.param(1, id="header-first-line"), pytest.param(2, id="header-citation-line")],
)
def test_REQ_d00254_K_comment_does_not_bind_across_a_non_comment_line(route, comment_line):
    """A header separated from the first declaration by an import binds to nothing."""
    line_context = route(HEADER_THEN_IMPORT)
    func_name, _class_name, func_line, _end = line_context[comment_line]
    assert func_name is None
    assert func_line == 0
