"""Tests for the one Dart lexical reader shared by the test prescan and the imports:dart source."""

from __future__ import annotations

import pytest

from elspais.graph.parsers.dart_lexer import (
    DartLexError,
    code_brackets,
    dart_literal,
    dart_string,
    skip_balanced,
    skip_trivia,
)
from elspais.graph.parsers.prescan import _match_brace_end, dart_test_names


def _lines(src: str) -> list[tuple[int, str]]:
    return [(i + 1, t) for i, t in enumerate(src.split("\n"))]


# Verifies: REQ-d00333-C
@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("'a.dart'", "a.dart"),
        ('"a.dart"', "a.dart"),
        ("r'a\\b'", "a\\b"),
        ("'''\nline'''", "line"),
        ("'tab\\there'", "tab\there"),
        ("'\\x41\\u0042\\u{43}'", "ABC"),
    ],
)
def test_a_literal_reads_to_its_value(text, value):
    assert dart_literal(text, 0) == (value, len(text))


# Verifies: REQ-d00333-C
@pytest.mark.parametrize("text", ["'a$b'", "'a${b}'", "'open", "'\nx'", "x'a'", "'\\x4'"])
def test_a_literal_that_interpolates_does_not_close_or_does_not_start_reads_nothing(text):
    assert dart_literal(text, 0) is None


# Verifies: REQ-d00333-C
def test_adjacent_literals_are_joined_into_one_string():
    text = "'package:a/'\n  \"b.dart\" r'c';"
    assert dart_string(text, 0) == ("package:a/b.dartc", text.index(";"))
    assert dart_string("x", 0) is None


# Verifies: REQ-d00333-C
def test_trivia_skips_white_space_line_comments_and_nested_block_comments():
    text = "  // import 'a.dart';\n/// doc\n/* outer /* inner */ still */ code"
    assert text[skip_trivia(text, 0, "//") :] == "code"


# Verifies: REQ-d00333-C
def test_trivia_reads_the_line_marker_it_is_given():
    text = "# not a comment in Dart\ncode"
    assert skip_trivia(text, 0, "//") == 0
    assert text[skip_trivia(text, 0, "#") :] == "code"


# Verifies: REQ-d00333-C
def test_a_block_comment_that_does_not_close_is_refused_where_it_opens():
    with pytest.raises(DartLexError) as caught:
        skip_trivia("x /* /* */", 2, "//")
    assert caught.value.offset == 2


# Verifies: REQ-d00333-C
def test_balanced_brackets_skip_strings_comments_and_interpolations():
    text = "(')' /* ) */ \"${ '}' + f(\")\") }\" [1]) tail"
    assert text[skip_balanced(text, 0, "//") :] == " tail"
    text = "<Map<String, List<int>>>()"
    assert text[skip_balanced(text, 0, "//") :] == "()"


# Verifies: REQ-d00333-C
def test_an_unbalanced_bracket_is_refused():
    with pytest.raises(DartLexError):
        skip_balanced("(a, 'b'", 0, "//")
    with pytest.raises(DartLexError):
        skip_balanced("('a\n')", 0, "//")


# Verifies: REQ-d00332-A
def test_code_brackets_are_only_those_outside_comments_and_strings():
    text = "f(/* ( */ '(' \"${g(')')}\" // )\n r'['){}"
    assert [c for _at, c in code_brackets(text, 0, "//")] == ["(", ")", "{", "}"]


# Verifies: REQ-d00332-A
def test_code_brackets_end_a_single_line_string_at_its_line():
    text = "f('open\n) {}"
    assert [c for _at, c in code_brackets(text, 0, "//")] == ["(", ")", "{", "}"]


# Verifies: REQ-d00332-A
def test_a_test_span_closes_after_a_nested_block_comment_holding_a_brace():
    src = "test('a', () {\n  /* outer /* inner */ } still a comment */\n  x();\n});\nlater();"
    assert _match_brace_end(_lines(src), 0) == (4, True)


# Verifies: REQ-d00332-A
def test_a_test_span_closes_after_an_interpolation_holding_a_brace_and_a_quote():
    src = 'test(\'a\', () {\n  print("${ "}" }");\n  x();\n});\nlater();'
    assert _match_brace_end(_lines(src), 0) == (4, True)


# Verifies: REQ-d00332-A
def test_a_span_is_clamped_at_the_next_test_and_runs_to_the_end_unbalanced():
    lines = _lines("test('a', () {\n  x();\ntest('b', () {\n})")
    assert _match_brace_end(lines, 0, stop_line=3) == (2, False)
    assert _match_brace_end(_lines("test('a', () {\n  x();"), 0) == (2, False)


# Verifies: REQ-d00284-H
def test_a_test_name_is_read_from_adjacent_literals_through_the_shared_reader():
    src = "void main() {\n  test('first ' \"second\", () {});\n  test('a$b', () {});\n}"
    assert dart_test_names(_lines(src)) == {2: "first second"}
