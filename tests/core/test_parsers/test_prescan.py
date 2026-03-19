"""Tests for prescan utility functions.

Verifies the standalone prescan module extracted from CodeParser and TestParser.
"""

from elspais.graph.parsers.prescan import (
    ast_prescan,
    build_line_context,
    detect_language,
    external_prescan,
    text_prescan,
)


class TestDetectLanguage:
    """Tests for detect_language utility."""

    def test_REQ_d00082_I_python_extension(self):
        assert detect_language("foo/bar.py") == "python"

    def test_REQ_d00082_I_pyw_extension(self):
        assert detect_language("script.pyw") == "python"

    def test_REQ_d00082_I_js_extension(self):
        assert detect_language("app.js") == "js"

    def test_REQ_d00082_I_ts_extension(self):
        assert detect_language("app.ts") == "js"

    def test_REQ_d00082_I_tsx_extension(self):
        assert detect_language("component.tsx") == "js"

    def test_REQ_d00082_I_go_extension(self):
        assert detect_language("main.go") == "go"

    def test_REQ_d00082_I_rust_extension(self):
        assert detect_language("lib.rs") == "rust"

    def test_REQ_d00082_I_c_extension(self):
        assert detect_language("main.c") == "c"

    def test_REQ_d00082_I_java_extension(self):
        assert detect_language("App.java") == "c"

    def test_REQ_d00082_I_unknown_extension(self):
        assert detect_language("readme.txt") == "unknown"

    def test_REQ_d00082_I_no_extension(self):
        assert detect_language("Makefile") == "unknown"


class TestBuildLineContext:
    """Tests for build_line_context utility."""

    def test_REQ_d00082_I_python_function_context(self):
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

    def test_REQ_d00082_I_python_class_context(self):
        """Class context is tracked for Python files."""
        lines = [
            (1, "class MyClass:"),
            (2, "    def method(self):"),
            (3, "        pass"),
        ]
        ctx = build_line_context(lines, "python")
        assert ctx[2][1] == "MyClass"
        assert ctx[3][1] == "MyClass"

    def test_REQ_d00082_I_forward_looking_fixup(self):
        """Comment above a function gets the function's context."""
        lines = [
            (1, "# Implements: REQ-p00001"),
            (2, "def my_func():"),
            (3, "    pass"),
        ]
        ctx = build_line_context(lines, "python")
        # Line 1 (comment) should pick up my_func from forward-looking fixup
        assert ctx[1][0] == "my_func"

    def test_REQ_d00082_I_js_brace_scoping(self):
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

    def test_REQ_d00082_J_finds_test_functions(self):
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

    def test_REQ_d00082_J_finds_test_class(self):
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

    def test_REQ_d00082_J_line_context_maps_correctly(self):
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

    def test_REQ_d00082_J_finds_module_level_test(self):
        """AST prescan finds module-level test functions."""
        source = "def test_foo():\n    assert True\n"
        lines = [(1, "def test_foo():"), (2, "    assert True")]
        line_context, all_test_funcs, first_def_line = ast_prescan(source, lines)
        assert len(all_test_funcs) == 1
        assert all_test_funcs[0][1] == "test_foo"
        assert all_test_funcs[0][2] is None  # no class

    def test_REQ_d00082_J_finds_class_test(self):
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

    def test_REQ_d00082_J_builds_context_from_entries(self):
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
