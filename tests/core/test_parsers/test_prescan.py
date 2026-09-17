"""Tests for prescan utility functions.

Exercises the standalone prescan module extracted from CodeParser and
TestParser.

The tests that bind a scanned test to its identity within its file and to
that test's line extent name REQ-d00254-K, which obliges exactly that, on
both the built-in and the external-record routes.

The tests at the foot of the file name REQ-d00254-D instead: what a citation
binds to decides the extent D attributes to it, so a citation walking past a
decorator or a class header -- or stopping at a member that is neither -- is
that assertion being met or missed.

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
    declaration_starts,
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

    # Verifies: REQ-d00254-K
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

    # Verifies: REQ-d00254-K
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

    # Verifies: REQ-d00254-K
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

    # Verifies: REQ-d00254-K
    def test_REQ_d00254_K_finds_module_level_test(self):
        """AST prescan finds module-level test functions."""
        source = "def test_foo():\n    assert True\n"
        lines = [(1, "def test_foo():"), (2, "    assert True")]
        line_context, all_test_funcs, first_def_line = ast_prescan(source, lines)
        assert len(all_test_funcs) == 1
        assert all_test_funcs[0][1] == "test_foo"
        assert all_test_funcs[0][2] is None  # no class

    # Verifies: REQ-d00254-K
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

    # Verifies: REQ-d00254-K
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

    # Verifies: REQ-d00254-K
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

    # Verifies: REQ-d00254-K
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

    # Verifies: REQ-d00254-K
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

    # Verifies: REQ-d00254-K
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

    # Verifies: REQ-d00254-K
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


# Verifies: REQ-d00254-K
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


# Verifies: REQ-d00254-K
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


# ---------------------------------------------------------------------------
# Declaration headers between a citation and its function
#
# REQ-d00254-D attributes a citation the lines of "the function it is written
# above".  Between the citation and that function an author may write lines
# that are part of the declaration rather than work of their own: a decorator,
# or the class the function is a method of.  Neither is the function, and
# neither stops the citation being written above it -- so the downward walk
# passes over them and binds at the function beyond.
#
# Reading such a line as the end of the search costs the citation its function
# outright: it then falls to D's second branch and attributes the executable
# lines FOLLOWING it, bounded by nothing nearer than the next citation or the
# end of the file, spilling across functions it says nothing about.
#
# A class is passed OVER, never bound TO.  D speaks of functions and never of
# classes, so a citation above a class binds to the first function inside it,
# and to nothing at all when the class opens with something else.
#
# Both routes through ``build_line_context`` answer the same way, and are
# exercised on identical sources.  They differ only in the END of the extent:
# the AST knows a function's real last line, while indent tracking carries the
# function across the blank lines below it, so the end is asserted as a bound
# rather than an equality.
# ---------------------------------------------------------------------------


# (language, whether the route knows a function's exact last line).  The AST
# does; indent tracking carries a function across the blank lines below it and
# so reports an end past the body, which is why only the AST route is held to
# an equality there.
CODE_ROUTES = [
    pytest.param(("python", True), id="ast"),  # build_line_context -> python_line_context
    pytest.param(("unknown", False), id="indent"),  # build_line_context -> indent tracking
]


def _later_line(source: str) -> int:
    """Line of the unrelated ``def later()`` every source below ends with.

    Its presence is what stops a negative assertion being vacuous: a citation
    reported as bound to nothing must be bound to nothing *while a function it
    could have walked on to exists below it*.
    """
    for ln, text in _numbered(source):
        if text.startswith("def later("):
            return ln
    raise AssertionError("source must end with an unrelated 'def later()'")


DECORATED = """\
# Implements: REQ-p00001-A
@app.route("/x")
def handler():
    return 1


def later():
    return 2
"""

STACKED_DECORATORS = """\
# Implements: REQ-p00001-A
@app.route("/x")
@requires_auth
@cache(seconds=30)
def handler():
    return 1


def later():
    return 2
"""

CITATION_BELOW_DECORATOR = """\
@app.route("/x")
# Implements: REQ-p00001-A
def handler():
    return 1


def later():
    return 2
"""

BARE_DEF = """\
# Implements: REQ-p00001-A
def handler():
    return 1


def later():
    return 2
"""

INSIDE_BODY = """\
def handler():
    # Implements: REQ-p00001-A
    return 1


def later():
    return 2
"""

CLASS_FIRST_MEMBER_IS_A_DEF = """\
# Implements: REQ-p00001-A
class Widget:
    def render(self):
        return 1


def later():
    return 2
"""

DECORATED_METHOD_IN_CLASS = """\
# Implements: REQ-p00001-A
class Widget:
    @property
    def render(self):
        return 1


def later():
    return 2
"""

# The three shapes a class may open with that are not a function.  Each has a
# ``def`` further down, so binding to nothing here is a statement about the
# member the walk met and not about the file running out of functions.
CLASS_OPENING_ON_AN_ENUM_MEMBER = """\
# Implements: REQ-p00001-A
class Color(Enum):
    RED = 1

    def label(self):
        return self.name


def later():
    return 2
"""

CLASS_OPENING_ON_A_FIELD = """\
# Implements: REQ-p00001-A
class Point:
    x: int = 0

    def shift(self):
        return self.x


def later():
    return 2
"""

CLASS_OPENING_ON_A_DOCSTRING = """\
# Implements: REQ-p00001-A
class Store:
    \"\"\"Holds things.\"\"\"

    def get(self):
        return None


def later():
    return 2
"""


# Verifies: REQ-d00254-D
@pytest.mark.parametrize("language", CODE_ROUTES)
@pytest.mark.parametrize(
    ("source", "citation_line", "func_name", "class_name", "func_line", "last_body_line"),
    [
        pytest.param(DECORATED, 1, "handler", None, 3, 4, id="decorated-def"),
        pytest.param(STACKED_DECORATORS, 1, "handler", None, 5, 6, id="stacked-decorators"),
        pytest.param(CLASS_FIRST_MEMBER_IS_A_DEF, 1, "render", "Widget", 3, 4, id="class-then-def"),
        pytest.param(
            DECORATED_METHOD_IN_CLASS, 1, "render", "Widget", 4, 5, id="class-then-decorated-def"
        ),
        # Regression guards: the three shapes that bound correctly before a
        # header was ever skipped, and must still bind identically.
        pytest.param(
            CITATION_BELOW_DECORATOR, 2, "handler", None, 3, 4, id="guard-below-last-decorator"
        ),
        pytest.param(BARE_DEF, 1, "handler", None, 2, 3, id="guard-above-bare-def"),
        pytest.param(INSIDE_BODY, 2, "handler", None, 1, 3, id="guard-inside-body"),
    ],
)
def test_REQ_d00254_D_a_citation_binds_past_the_headers_of_its_function(
    language, source, citation_line, func_name, class_name, func_line, last_body_line
):
    """A citation above a decorated or method definition binds to that function.

    The extent is asserted as well as the identity: a citation bound to a name
    but not to a range attributes nothing, and a citation bound to a range that
    runs past its function attributes code the function does not contain.
    """
    lang, exact_end = language
    context = build_line_context(_numbered(source), lang)
    name, cls, start, end = context[citation_line]

    assert (name, cls, start) == (func_name, class_name, func_line)
    if exact_end:
        assert end == last_body_line, (
            f"the AST knows {func_name} ends at line {last_body_line}, got {end}"
        )
    else:
        assert end >= last_body_line, (
            f"extent must reach the end of {func_name}'s body (line {last_body_line}), got {end}"
        )
    assert end < _later_line(source), (
        f"extent must stop before the unrelated function at line {_later_line(source)}, got {end}"
    )


# Verifies: REQ-d00254-D
@pytest.mark.parametrize("language", CODE_ROUTES)
@pytest.mark.parametrize(
    "source",
    [
        pytest.param(CLASS_OPENING_ON_AN_ENUM_MEMBER, id="enum-member"),
        pytest.param(CLASS_OPENING_ON_A_FIELD, id="annotated-field"),
        pytest.param(CLASS_OPENING_ON_A_DOCSTRING, id="docstring"),
    ],
)
def test_REQ_d00254_D_a_citation_above_a_class_binds_to_nothing_beyond_its_first_member(
    language, source
):
    """A class whose first member is not a function leaves the citation unbound.

    The class header is passed over, but what lies beyond it is a member that
    does work -- an enum member, a field, a docstring -- and that ends the
    search.  The citation must NOT walk on to the method below it, nor to the
    unrelated function at the foot of the file: binding a citation to a
    declaration it was not written above attributes evidence to code it says
    nothing about.
    """
    lang, _exact_end = language
    context = build_line_context(_numbered(source), lang)

    assert context[1] == (None, None, 0, 0), f"citation must stay unbound, got {context[1]}"

    # ...and the file does hold functions the walk could have reached, so the
    # assertion above is about the member met and not about an empty file.
    later = _later_line(source)
    assert context[later][0] == "later"


# ---------------------------------------------------------------------------
# Nested declarations: the narrower answer wins
#
# REQ-d00254-D attributes a citation the lines of "the function it is written
# above", and a citation inside a function may be written above a function
# too.  A nested declaration BEGINS below the citation, so the citation is
# written above it, and its extent is the narrower of the two answers.
#
# Binding to the enclosing function instead attributes to the cited
# requirement every nested declaration of its neighbour: the citation falls to
# D's second branch, where nothing nearer than the enclosing function's end
# bounds it, and the sibling defined below the cited one is credited to a
# requirement it implements no part of.
#
# The walk is what decides, so real code between the citation and the nested
# declaration ends it: such a citation speaks for the body it stands in,
# bounded by the function that holds it.  That is the line between reading the
# author's placement and over-reaching past it.
# ---------------------------------------------------------------------------


NESTED_DEF = """\
def outer():
    value = 1

    # Implements: REQ-p00001-A
    def inner():
        return value

    def sibling():
        return 2

    return inner


def later():
    return 3
"""

NESTED_DECORATED_DEF = """\
def outer():
    value = 1

    # Implements: REQ-p00001-A
    @functools.cache
    def inner():
        return value

    def sibling():
        return 2

    return inner


def later():
    return 3
"""

# The same file with the citation moved above work of its own.  The nested
# declaration is still below it, but no longer directly below it.
CODE_THEN_NESTED_DEF = """\
def outer():
    # Implements: REQ-p00001-A
    value = 1

    def inner():
        return value

    return inner


def later():
    return 3
"""

# Two citations inside one function, each above work of its own.  Neither is
# written above a declaration, so both keep the function that encloses them.
TWO_CITATIONS_IN_ONE_FUNCTION = """\
def handler():
    # Implements: REQ-p00001-A
    first = 1
    # Implements: REQ-p00001-B
    second = 2
    return first + second


def later():
    return 3
"""


def _sibling_line(source: str) -> int:
    """Line of the ``def sibling()`` declared beside the cited nested function.

    The sibling is what makes the extent assertion a claim: an answer that
    reached it would credit the cited requirement with a function declared
    next to the one the author wrote about.
    """
    for ln, text in _numbered(source):
        if text.strip().startswith("def sibling("):
            return ln
    raise AssertionError("source must declare a 'def sibling()' beside the cited function")


# Verifies: REQ-d00254-D
@pytest.mark.parametrize("language", CODE_ROUTES)
@pytest.mark.parametrize(
    ("source", "citation_line", "func_line", "last_body_line"),
    [
        pytest.param(NESTED_DEF, 4, 5, 6, id="nested-def"),
        pytest.param(NESTED_DECORATED_DEF, 4, 6, 7, id="nested-decorated-def"),
    ],
)
def test_REQ_d00254_D_a_citation_above_a_nested_declaration_binds_to_that_declaration(
    language, source, citation_line, func_line, last_body_line
):
    """A citation directly above a nested ``def`` binds to the nested function.

    ``outer`` encloses the citation and ``inner`` begins below it, so both
    could answer; D names the one the citation is written above.  The extent is
    asserted with it, because an identity without a range attributes nothing
    and a range reaching ``sibling`` attributes a function the citation says
    nothing about.

    In the decorated case the binding still lands on ``inner`` -- the decorator
    is passed over, exactly as it is above a top-level function
    (``decorated-def``) -- and the extent begins at the ``def``, which is where
    the declaration's own line range begins.  Where the DECLARATION begins,
    decorator included, is a separate question, answered by
    ``declaration_starts`` below.
    """
    lang, exact_end = language
    context = build_line_context(_numbered(source), lang)
    name, cls, start, end = context[citation_line]

    assert (name, cls, start) == ("inner", None, func_line), (
        f"the citation is written above 'inner', got {(name, cls, start)}"
    )
    if exact_end:
        assert end == last_body_line, (
            f"the AST knows inner ends at line {last_body_line}, got {end}"
        )
    else:
        assert end >= last_body_line, (
            f"extent must reach the end of inner's body (line {last_body_line}), got {end}"
        )
    assert end < _sibling_line(source), (
        f"extent must stop before the sibling declared at line {_sibling_line(source)}, got {end}"
    )


# Verifies: REQ-d00254-D
@pytest.mark.parametrize("language", CODE_ROUTES)
def test_REQ_d00254_D_work_between_a_citation_and_a_nested_declaration_keeps_the_enclosing_one(
    language,
):
    """Real code below the citation ends the walk, so ``outer`` still answers.

    This is the bound on the case above: a citation is written above a nested
    declaration only when nothing that does work separates them.  ``value = 1``
    does, so the citation speaks for the body it stands in and ``inner`` --
    declared further down and never written about -- does not become the
    answer.

    Only the AST route is held to an equality on the end: indent tracking hands
    the context over to ``inner`` when its ``def`` is reached and reports a
    shorter end for ``outer``, which is the sentinel behaviour the file already
    records elsewhere.  The identity, and the absence of any spill past
    ``outer``, are asserted on both routes.
    """
    lang, exact_end = language
    context = build_line_context(_numbered(CODE_THEN_NESTED_DEF), lang)
    name, cls, start, end = context[2]

    assert (name, cls, start) == ("outer", None, 1), (
        f"the citation must stay with the function that holds it, got {(name, cls, start)}"
    )
    if exact_end:
        assert end == 8, f"the AST knows outer ends at line 8, got {end}"
    assert end < _later_line(CODE_THEN_NESTED_DEF), (
        "extent must stop before the unrelated function at line "
        f"{_later_line(CODE_THEN_NESTED_DEF)}, got {end}"
    )


# Verifies: REQ-d00254-D
@pytest.mark.parametrize("language", CODE_ROUTES)
@pytest.mark.parametrize(
    "citation_line",
    [pytest.param(2, id="first-citation"), pytest.param(4, id="second-citation")],
)
def test_REQ_d00254_D_two_citations_dividing_one_function_both_keep_it(language, citation_line):
    """Two citations inside one function are both bound to that function.

    Regression guard: offering every comment line to the downward walk must
    not move a citation that divides a body.  Each of these has work directly
    below it, so neither binds to a declaration, and the function that holds
    them bounds both -- which is what lets the extent rules give each one a
    different piece of the same body.
    """
    lang, exact_end = language
    context = build_line_context(_numbered(TWO_CITATIONS_IN_ONE_FUNCTION), lang)
    name, cls, start, end = context[citation_line]

    assert (name, cls, start) == ("handler", None, 1), (
        f"citation on line {citation_line} must stay with handler, got {(name, cls, start)}"
    )
    if exact_end:
        assert end == 6, f"the AST knows handler ends at line 6, got {end}"
    assert end < _later_line(TWO_CITATIONS_IN_ONE_FUNCTION)


# ---------------------------------------------------------------------------
# Declarations written under a compound statement
#
# REQ-d00254-D attributes a citation the lines of "the function it is written
# above", and nothing in that qualifies where the function is written.  A
# ``def`` under a module-level ``if`` -- the platform branch, the optional
# import, the ``TYPE_CHECKING`` block -- is a declaration like any other, so a
# citation directly above one is written above it and takes its extent.
#
# A walk that descended only into classes and functions would leave such a
# declaration with no extent at all, and the citation would fall to D's second
# branch: bounded by nothing nearer than the next citation or the next
# declaration, it would attribute lines of whatever merely encloses both.  That
# is the wrong attribution rather than a weaker one -- the requirement is
# credited with code declared beside the code it names, the reference resolves,
# and no check reports it.
#
# ``declaration_starts`` has always read these declarations (it walks the whole
# tree), so the extent and the bound are asserted together here: they are the
# two halves of one rule and a file where they disagree is a file where a
# citation is bounded at a line the extent says is inside its own function.
# ---------------------------------------------------------------------------


# A function declared under a module-level ``if``, with a sibling declared
# beside it under the same branch and an unrelated ``later`` below.
DEF_UNDER_A_MODULE_IF = """\
import sys

if sys.platform == "win32":
    # Implements: REQ-p00001-A
    def resolve():
        return "win"

    def sibling():
        return "posix"


def later():
    return 3
"""

# The same shape under a ``try``: the optional-dependency import, where the
# declaration that uses the dependency is written inside the branch that
# proved it importable.
DEF_UNDER_A_TRY = """\
try:
    import orjson

    # Implements: REQ-p00001-A
    def dumps(value):
        return orjson.dumps(value)

    def sibling():
        return None

except ImportError:
    orjson = None


def later():
    return 3
"""

# A method declared under an ``if`` inside a class.  The class encloses the
# compound statement, so the answer must still name it: a method reported
# without its class is a method that cannot be told from a free function of
# the same name elsewhere in the file.
METHOD_UNDER_AN_IF_IN_A_CLASS = """\
class Store:
    if TYPE_CHECKING:
        # Implements: REQ-p00001-A
        def keys(self):
            return ()

        def sibling(self):
            return ()

    def other(self):
        return 1


def later():
    return 3
"""

# A ``def`` under an ``if`` INSIDE a function -- the signal handler installed
# only when the server reloads.  This is the shape where a missed declaration
# mis-credits rather than merely under-credits: ``outer`` encloses the citation,
# so binding to it attributes ``outer``'s whole body, ``sibling`` included, to a
# requirement the six-line handler alone implements.
DEF_UNDER_AN_IF_IN_A_FUNCTION = """\
def outer(config):
    prepared = 1

    if config.reload:
        # Implements: REQ-p00001-A
        def handler(signum, frame):
            return prepared

        def sibling(signum, frame):
            return 0

        return handler

    return None


def later():
    return 3
"""

# The same file with the compound statement removed.  This is the regression
# guard: descending through an ``if`` must not change what a citation above an
# ordinary module-level ``def`` binds to.
DEF_AT_MODULE_LEVEL = """\
import sys

# Implements: REQ-p00001-A
def resolve():
    return "win"


def sibling():
    return "posix"


def later():
    return 3
"""


# Verifies: REQ-d00254-D
@pytest.mark.parametrize("language", CODE_ROUTES)
@pytest.mark.parametrize(
    ("source", "citation_line", "func_name", "class_name", "func_line", "last_body_line"),
    [
        pytest.param(DEF_UNDER_A_MODULE_IF, 4, "resolve", None, 5, 6, id="under-a-module-if"),
        pytest.param(DEF_UNDER_A_TRY, 4, "dumps", None, 5, 6, id="under-a-try"),
        pytest.param(
            METHOD_UNDER_AN_IF_IN_A_CLASS, 3, "keys", "Store", 4, 5, id="under-an-if-in-a-class"
        ),
        pytest.param(
            DEF_UNDER_AN_IF_IN_A_FUNCTION, 5, "handler", None, 6, 7, id="under-an-if-in-a-function"
        ),
        pytest.param(DEF_AT_MODULE_LEVEL, 3, "resolve", None, 4, 5, id="no-compound-statement"),
    ],
)
def test_REQ_d00254_D_a_citation_above_a_def_under_a_compound_statement_binds_to_that_def(
    language, source, citation_line, func_name, class_name, func_line, last_body_line
):
    """A ``def`` under an ``if`` or a ``try`` answers for the citation above it.

    The compound statement is not the function and does no work of the
    citation's own, so the declaration below it is what the citation is written
    above.  The extent is asserted with the identity, because a name without a
    range attributes nothing and a range reaching ``sibling`` -- declared beside
    the cited function under the same branch -- attributes a function the
    citation says nothing about.

    The class name is asserted in every case: under an ``if`` inside a class it
    must still be reported, and outside a class it must stay None rather than
    borrowing whatever declared last.

    The last case carries no compound statement at all, so the three above it
    are a statement about reaching a nested declaration rather than about the
    binding rule changing.
    """
    lang, exact_end = language
    lines = _numbered(source)
    context = build_line_context(lines, lang)
    name, cls, start, end = context[citation_line]

    assert (name, cls, start) == (func_name, class_name, func_line), (
        f"the citation is written above {func_name}, got {(name, cls, start)}"
    )
    if exact_end:
        assert end == last_body_line, (
            f"the AST knows {func_name} ends at line {last_body_line}, got {end}"
        )
    else:
        assert end >= last_body_line, (
            f"extent must reach the end of {func_name}'s body (line {last_body_line}), got {end}"
        )
    assert end < _sibling_line(source), (
        f"extent must stop before the sibling declared at line {_sibling_line(source)}, got {end}"
    )
    assert start in declaration_starts(lines, lang), (
        f"the bound and the extent must agree about what a declaration is: "
        f"{func_name} begins at line {start}, which declaration_starts does not report"
    )


# ---------------------------------------------------------------------------
# ``declaration_starts``: where the next function declaration BEGINS.
#
# REQ-d00254-D bounds a citation that no function encloses at the start of the
# next function declaration.  A decorator is part of the declaration written
# below it, so the declaration begins at the FIRST decorator line: reporting
# the ``def`` would leave a decorated function's decorator lines attributable
# to a citation written about something else entirely.
# ---------------------------------------------------------------------------


DECLARATIONS_WITH_DECORATORS = """\
VALUE = 1

@app.route("/x")
@requires_auth
def handler():
    return 1


def later():
    return 2
"""


# Verifies: REQ-d00254-D
@pytest.mark.parametrize("language", CODE_ROUTES)
def test_REQ_d00254_D_a_declaration_begins_at_its_first_decorator(language):
    """A stacked-decorator function is reported at its first decorator line.

    Line 5 -- the ``def`` -- is deliberately NOT in the answer: a bound placed
    there admits lines 3 and 4 to whatever citation stands above, which is the
    decorated half of the defect this bound closes.  ``later`` is reported at
    its own ``def`` because it has no decorators, which is what says the walk
    back is over decorators rather than over any line above a ``def``.
    """
    lang, _exact_end = language

    assert declaration_starts(_numbered(DECLARATIONS_WITH_DECORATORS), lang) == [3, 9], (
        "a declaration begins at its first decorator, never at its 'def'"
    )


# A nested decorated declaration, with the enclosing function's own start above
# it and an undecorated sibling below.
NESTED_DECLARATIONS_WITH_A_DECORATOR = """\
def outer():
    @functools.cache
    def inner():
        return 1

    def sibling():
        return 2

    return inner


def later():
    return 3
"""


# Verifies: REQ-d00254-D
@pytest.mark.parametrize("language", CODE_ROUTES)
def test_REQ_d00254_D_a_nested_declaration_begins_at_its_first_decorator(language):
    """A nested declaration is reported, and reported at its decorator line.

    A nested ``def`` is a declaration like any other, so the bound a citation
    at module level stops at counts it: line 2, not line 3.  ``sibling`` and
    the enclosing ``outer`` are reported at their own ``def`` lines, which is
    what says the walk back is over decorators and not over whatever line
    happens to sit above a ``def``.
    """
    lang, _exact_end = language

    assert declaration_starts(_numbered(NESTED_DECLARATIONS_WITH_A_DECORATOR), lang) == [
        1,
        2,
        6,
        12,
    ], "a nested declaration begins at its first decorator, never at its 'def'"


# ---------------------------------------------------------------------------
# Dart and Go: recognising a declaration in a brace language
#
# REQ-d00254-D attributes a citation the lines of "the function it is written
# above".  Knowing which function that is means recognising a declaration by
# sight, and in a type-first brace language that is harder than in Python:
# there is no ``def`` and no ``fn``.  ``Widget build(BuildContext c) {`` and
# ``return Column(`` have the same shape, and so do ``String get title =>``
# and a field initialised from a ternary.
#
# Both halves of that matter, so both are asserted here.  A shape that IS a
# declaration must bind, or the citation falls to D's second branch and
# attributes the executable lines following it, bounded by nothing nearer than
# the next citation -- spilling across members it says nothing about.  A shape
# that is NOT a declaration must not bind, because a citation bound to a call
# attributes that call's argument lines to the requirement and, in brace
# scoping, sets a brace floor that ends the real enclosing member early.
#
# The extents are asserted as equalities, unlike the indent route above: brace
# scoping knows where a member's ``}`` is, so an end past the body or short of
# it is a defect rather than a known limitation.  The one exception is called
# out where it arises.
#
# The sources are real shapes, taken or modelled from the Cure-HHT diary estate
# (app_lock_controller.dart, recording_draft_store.dart, app_config.dart,
# db_tracing.dart, diary_originated_events.dart, role_selection_screen.dart,
# checkchars.go, main.go) with the citations rewritten to this repository's
# identifiers.
# ---------------------------------------------------------------------------


def _brace_later_line(source: str) -> int:
    """Line of the unrelated declaration named ``later`` each source ends with.

    The same job ``_later_line`` does for the Python sources: an extent that
    reached this line would credit the cited requirement with a member declared
    beside the one the author wrote about, and a citation reported as bound to
    nothing must be bound to nothing *while a declaration it could have walked
    on to exists below it*.
    """
    for ln, text in _numbered(source):
        if "later(" in text:
            return ln
    raise AssertionError("source must end with an unrelated declaration named 'later'")


# A method with an ordinary return type, inside a class, with a widget tree in
# its body.  ``return Column(`` and ``const SizedBox(height: 8)`` are the shapes
# a declaration pattern must refuse; the constructor on line 2 is the shape it
# must accept.
DART_METHOD_WITH_RETURN_TYPE = """\
class RoleSelectionScreen extends StatelessWidget {
  const RoleSelectionScreen({super.key});

  /// Renders the role picker.
  // Implements: REQ-p00001-A
  Widget build(BuildContext context) {
    return Column(
      children: const [SizedBox(height: 8)],
    );
  }

  Widget later(BuildContext context) {
    return const SizedBox();
  }
}
"""

# Two async methods, one returning ``Future<void>`` and one a nullable generic.
# The generic return type is what the type pattern has to read without letting
# its match run past the line.
DART_FUTURE_METHODS = """\
class RecordingDraftStore {
  String get _draftKey => 'recording_draft_v1';

  /// Durably persists [draft], replacing any previous snapshot.
  // Implements: REQ-p00001-A
  Future<void> save(RecordingDraft draft) async {
    final prefs = await _getPrefs();
    await prefs.setString(_draftKey, jsonEncode(draft.toJson()));
  }

  /// The surviving draft, or null when none exists.
  // Implements: REQ-p00001-B
  Future<RecordingDraft?> load() async {
    final raw = (await _getPrefs()).getString(_draftKey);
    if (raw == null) return null;
    return RecordingDraft.fromJson(jsonDecode(raw));
  }

  Future<void> later() async {
    await (await _getPrefs()).remove(_draftKey);
  }
}
"""

# A getter with a body.  ``get`` sits where a function's name would, so a
# pattern that read this as a function would name it ``get`` and stop at the
# wrong word -- and the ``if (...) {`` inside is a statement with a
# declaration's shape.
DART_GETTER_WITH_A_BODY = """\
class AppConfig {
  static const String _diaryApiBaseOverride = '';

  /// API base URL - derived from the active EnvProfile.
  // Implements: REQ-p00001-A
  static String get apiBase {
    if (testApiBaseOverride != null) {
      return testApiBaseOverride!;
    }
    return _diaryApiBaseOverride;
  }

  static String later() => 'x';
}
"""

# A getter whose arrow body the formatter split over three lines.
DART_GETTER_WITH_AN_ARROW = """\
class AppLockController extends ChangeNotifier {
  bool needsDeviceLock = false;

  /// The gate to render.
  // Implements: REQ-p00001-A
  AppLockGateState get gateState => needsDeviceLock
      ? AppLockGateState.deviceLockRequired
      : AppLockGateState.none;

  Future<void> later() async {
    notifyListeners();
  }
}
"""

# A top-level function: no class encloses it, so the class name in the answer
# must stay None rather than borrowing whatever declared last.
DART_TOP_LEVEL_FUNCTION = """\
import 'dart:convert';

/// Redacts values from a SQL statement before it reaches a trace span.
// Implements: REQ-p00001-A
String sanitizeSql(String sql) {
  var sanitized = sql.replaceAll(RegExp(r"'[^']*'"), "'?'");
  return sanitized;
}

void later() {
  print('x');
}
"""

# A citation above a class header binds to the class's first method, exactly as
# it does in Python: D speaks of functions and never of classes, so the header
# is passed over and the member beyond it answers.
DART_CLASS_FIRST_METHOD = """\
// Implements: REQ-p00001-A
class RecordingDraftStore {
  Future<void> save(RecordingDraft draft) async {
    await _prefs.setString(_draftKey, jsonEncode(draft.toJson()));
  }

  Future<void> clear() async {
    await _prefs.remove(_draftKey);
  }
}

void later() {
  print('x');
}
"""

# The shape left DELIBERATELY unbound: a const constructor invocation inside a
# list literal.  ``SharedEventType(`` is a call, and nothing in it tells it from
# a formatter-split constructor declaration -- so it is refused, and the
# citation falls to D's second branch, which attributes the entry's own lines
# and stops at the next declaration.  Binding here would name the citation's
# function ``SharedEventType`` and, worse, set a brace floor inside a list
# literal.
DART_CALL_SHAPED_LIST_ENTRY = """\
const List<SharedEventType> diaryOriginatedEventTypes = <SharedEventType>[
  // Implements: REQ-p00001-A
  SharedEventType(
    origin: EventOrigin.mobile,
    definition: EntryTypeDefinition(
      id: 'epistaxis_event',
      registeredVersion: 1,
    ),
  ),
];

void later() {
  print('x');
}
"""


# Verifies: REQ-d00254-D
@pytest.mark.parametrize(
    ("source", "citation_line", "func_name", "class_name", "func_line", "last_body_line"),
    [
        pytest.param(
            DART_METHOD_WITH_RETURN_TYPE,
            5,
            "build",
            "RoleSelectionScreen",
            6,
            9,
            id="method-with-a-return-type",
        ),
        pytest.param(
            DART_FUTURE_METHODS, 5, "save", "RecordingDraftStore", 6, 8, id="future-void-async"
        ),
        pytest.param(
            DART_FUTURE_METHODS,
            12,
            "load",
            "RecordingDraftStore",
            13,
            16,
            id="future-nullable-generic-async",
        ),
        pytest.param(
            DART_GETTER_WITH_A_BODY, 5, "apiBase", "AppConfig", 6, 10, id="getter-with-a-body"
        ),
        # The arrow getter's body runs to line 8 and the recorded end is 6.
        # ``None`` says the end is deliberately not asserted: a signature the
        # formatter split leaves the declaration line closing at the depth it
        # opened at, so the extent collapses to that line.  That under-credits
        # the getter by two lines; it never over-credits, and it is a separate
        # defect from the binding this test is about.  Asserting the wrong end
        # here would pin the defect in place.
        pytest.param(
            DART_GETTER_WITH_AN_ARROW,
            5,
            "gateState",
            "AppLockController",
            6,
            None,
            id="getter-with-an-arrow",
        ),
        pytest.param(
            DART_TOP_LEVEL_FUNCTION, 4, "sanitizeSql", None, 5, 7, id="top-level-function"
        ),
        pytest.param(
            DART_CLASS_FIRST_METHOD,
            1,
            "save",
            "RecordingDraftStore",
            3,
            4,
            id="class-then-first-method",
        ),
    ],
)
def test_REQ_d00254_D_a_dart_citation_binds_to_the_declaration_below_it(
    source, citation_line, func_name, class_name, func_line, last_body_line
):
    """Each Dart declaration shape is recognised, and bounds what it attributes.

    Before these patterns existed ``.dart`` fell through to the Python
    fallback, so every shape here was invisible: the citation was bound to
    nothing and attributed the executable lines following it as far as the next
    citation.  The identity and the extent are asserted together, because a
    citation bound to a name but not to a range attributes nothing, and a range
    running past its member attributes code that member does not contain.
    """
    context = build_line_context(_numbered(source), "dart")
    name, cls, start, end = context[citation_line]

    assert (name, cls, start) == (func_name, class_name, func_line), (
        f"the citation is written above {func_name}, got {(name, cls, start)}"
    )
    if last_body_line is not None:
        assert end == last_body_line, (
            f"brace scoping knows {func_name} ends at line {last_body_line}, got {end}"
        )
    assert end < _brace_later_line(source), (
        f"extent must stop before the declaration at line {_brace_later_line(source)}, got {end}"
    )


# Verifies: REQ-d00254-D
def test_REQ_d00254_D_a_dart_citation_above_a_call_shaped_line_stays_unbound():
    """A const constructor invocation is not a declaration and binds nothing.

    Two surfaces read the same patterns and both must refuse the line: the
    context builder leaves the citation unbound, and ``declaration_starts``
    does not report line 3 as a declaration -- so a citation above the list
    would not be cut short there either.  ``later`` IS bound, which is what
    says the walk had somewhere to go and the refusal is about the shape it
    met rather than about the file running out of declarations.
    """
    lines = _numbered(DART_CALL_SHAPED_LIST_ENTRY)
    context = build_line_context(lines, "dart")

    assert context[2] == (None, None, 0, 0), f"citation must stay unbound, got {context[2]}"
    assert 3 not in declaration_starts(lines, "dart"), (
        "'SharedEventType(' is a call; reporting it as a declaration would bound a "
        "citation above it at a line no function begins on"
    )

    later = _brace_later_line(DART_CALL_SHAPED_LIST_ENTRY)
    assert context[later][0] == "later"


# A package-level function, a method with a pointer receiver, and a function
# with a type-parameter list.  Transcribed from checkchars.go / main.go, with
# the generic added: Go 1.18 admits one anywhere a function is declared.
GO_DECLARATIONS = """\
package main

// Implements: REQ-p00001-A
func checkCharsFor(input, sponsorKey string) string {
\th := hmac.New(sha256.New, []byte(sponsorKey))
\treturn string([]byte{charset[h.Sum(nil)[0]%28]})
}

// Implements: REQ-p00001-B
func (r *resolver) verify(code string) bool {
\tif len(code) != 10 {
\t\treturn false
\t}
\treturn true
}

// Implements: REQ-p00001-C
func mapKeys[K comparable, V any](m map[K]V) []K {
\tout := make([]K, 0, len(m))
\treturn out
}

func later() int {
\treturn 2
}
"""


# Verifies: REQ-d00254-D
@pytest.mark.parametrize(
    ("citation_line", "func_name", "func_line", "last_body_line"),
    [
        pytest.param(3, "checkCharsFor", 4, 6, id="package-level-func"),
        pytest.param(9, "verify", 10, 14, id="method-with-a-pointer-receiver"),
        pytest.param(17, "mapKeys", 18, 20, id="generic-func"),
    ],
)
def test_REQ_d00254_D_a_go_citation_binds_to_the_func_below_it(
    citation_line, func_name, func_line, last_body_line
):
    """A citation above a Go ``func`` binds to it, whatever its declaration shape.

    A receiver and a type-parameter list are both written between ``func`` and
    the parameter list, and neither is work of the citation's own -- so neither
    changes what the citation is written above.  Both forms are recognised: the
    receiver is matched between ``func`` and the name, the type-parameter list
    between the name and the parameter list.

    Go has no class construct here, so the class name is None in every case: a
    name borrowed from a ``type ... struct`` above would attribute the method
    to a type it is not declared on.
    """
    context = build_line_context(_numbered(GO_DECLARATIONS), "go")
    name, cls, start, end = context[citation_line]

    assert (name, cls, start) == (func_name, None, func_line), (
        f"the citation is written above {func_name}, got {(name, cls, start)}"
    )
    assert end == last_body_line, (
        f"brace scoping knows {func_name} ends at line {last_body_line}, got {end}"
    )
    assert end < _brace_later_line(GO_DECLARATIONS), (
        f"extent must stop before the func at line {_brace_later_line(GO_DECLARATIONS)}, got {end}"
    )


# Two generic funcs whose type-parameter lists nest: ``~[]E`` holds a bracket
# inside the list, and ``~map[K][]V`` holds two.  A list is read to a bounded
# depth, so these stand for the shapes real generic Go is written in -- the
# constraint that names a slice of the second parameter, and the one that names
# a map of slices.  Beyond that bound a declaration is simply not seen, and the
# citation falls to REQ-d00254-D's second branch: a weaker attribution, never a
# wrong one.
GO_NESTED_TYPE_PARAMS = """\
package main

// Implements: REQ-p00001-A
func Filter[S ~[]E, E any](s S, keep func(E) bool) S {
\tout := s[:0]
\treturn out
}

// Implements: REQ-p00001-B
func Index[M ~map[K][]V, K comparable, V any](m M) []K {
\tkeys := make([]K, 0, len(m))
\treturn keys
}

func later() int {
\treturn 2
}
"""

# The two generic shapes that are NOT declarations.  ``type Set[T comparable]
# struct {`` declares a type, and ``mapKeys[string, int](m)`` instantiates and
# calls one -- both carry a name followed by a bracketed list, which is the
# whole of what the widened pattern looks for after ``func``.  Reading either as
# a func declaration is the wrong attribution the widening must not buy: the
# citation above the type would be bound to ``Set``, and the one above the call
# would be bound to ``mapKeys`` and, in brace scoping, set a brace floor inside
# ``collect`` that ends the real enclosing func early -- so every citation below
# it in that func loses its bound too.
GO_GENERIC_NON_DECLARATIONS = """\
package main

// Implements: REQ-p00001-A
type Set[T comparable] struct {
\tmembers map[T]struct{}
}

func collect(m map[string]int) []string {
\t// Implements: REQ-p00001-B
\tmapKeys[string, int](m)
\treturn nil
}

func later() int {
\treturn 2
}
"""


# Verifies: REQ-d00254-D
@pytest.mark.parametrize(
    ("citation_line", "func_name", "func_line", "last_body_line"),
    [
        pytest.param(3, "Filter", 4, 6, id="constraint-naming-a-slice"),
        pytest.param(9, "Index", 10, 12, id="constraint-naming-a-map-of-slices"),
    ],
)
def test_REQ_d00254_D_a_go_citation_binds_past_a_nested_type_parameter_list(
    citation_line, func_name, func_line, last_body_line
):
    """A type-parameter list holding brackets of its own still leaves the func visible.

    The list sits between the name and the parameter list and is no work of the
    citation's own, so a bracket written inside it cannot decide what the
    citation is written above.  The extent is asserted with the identity: an
    end short of the body under-credits the func, and one reaching ``later``
    credits a func declared beside the one the author wrote about.
    """
    context = build_line_context(_numbered(GO_NESTED_TYPE_PARAMS), "go")
    name, cls, start, end = context[citation_line]

    assert (name, cls, start) == (func_name, None, func_line), (
        f"the citation is written above {func_name}, got {(name, cls, start)}"
    )
    assert end == last_body_line, (
        f"brace scoping knows {func_name} ends at line {last_body_line}, got {end}"
    )
    assert end < _brace_later_line(GO_NESTED_TYPE_PARAMS), (
        f"extent must stop before the func at line "
        f"{_brace_later_line(GO_NESTED_TYPE_PARAMS)}, got {end}"
    )


# Verifies: REQ-d00254-D
@pytest.mark.parametrize(
    ("citation_line", "declaration_line", "bound_to", "shape"),
    [
        pytest.param(3, 4, None, "type Set[T comparable] struct {", id="generic-type"),
        pytest.param(9, 10, "collect", "mapKeys[string, int](m)", id="generic-call-site"),
    ],
)
def test_REQ_d00254_D_a_go_generic_type_or_call_is_not_a_func_declaration(
    citation_line, declaration_line, bound_to, shape
):
    """A name followed by a bracketed list is only a declaration after ``func``.

    Both surfaces reading the Go patterns must refuse the line.  The context
    builder must not bind the citation to it -- the generic type leaves the
    citation bound to nothing, and the citation inside ``collect`` keeps the
    func that encloses it -- and ``declaration_starts`` must not report the
    line, or a citation above it would be cut short at a line no func begins
    on.  ``later`` IS reported and bound, which is what says the refusal is
    about the shape met rather than about the file running out of funcs.
    """
    lines = _numbered(GO_GENERIC_NON_DECLARATIONS)
    context = build_line_context(lines, "go")
    starts = declaration_starts(lines, "go")

    assert context[citation_line][0] == bound_to, (
        f"{shape!r} is not a func declaration, so the citation above it must be "
        f"bound to {bound_to}, got {context[citation_line]}"
    )
    assert declaration_line not in starts, (
        f"{shape!r} declares no func; reporting line {declaration_line} as a "
        f"declaration would bound a citation above it at a line no func begins on"
    )

    later = _brace_later_line(GO_GENERIC_NON_DECLARATIONS)
    assert later in starts and context[later][0] == "later"
