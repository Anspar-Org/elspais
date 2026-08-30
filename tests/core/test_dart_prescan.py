# tests/core/test_dart_prescan.py
# Verifies: REQ-d00254-G
"""dart_prescan detects test() boundaries by regex + brace matching so each
Dart test case becomes a line-anchored unit, without a Dart parser."""

from __future__ import annotations

import pytest

from elspais.graph.parsers.prescan import _match_brace_end, dart_prescan


def _lines(src: str) -> list[tuple[int, str]]:
    return [(i + 1, t) for i, t in enumerate(src.split("\n"))]


DART = """\
void main() {
  group('outer', () {
    // Verifies: REQ-p00001-A
    test('first does a thing', () {
      expect(1, 1);
    });

    test('second does another', () {
      // Verifies: REQ-p00001-B
      expect(2, 2);
    });
  });
}
"""


def test_comment_above_test_binds_to_that_test():
    lc, _funcs, _first = dart_prescan(_lines(DART))
    # The `// Verifies: A` on line 3 owns the test() starting line 4.
    fname, cname, fline, fend = lc[3]
    assert fname is None and cname is None
    assert fline == 4  # the `test('first ...` line


def test_comment_inside_test_binds_to_enclosing_test():
    lc, _funcs, _first = dart_prescan(_lines(DART))
    # `// Verifies: B` on line 9 is inside the second test() (lines 8..11).
    _f, _c, fline, _e = lc[9]
    assert fline == 8


def test_each_test_is_a_distinct_unit():
    _lc, funcs, _first = dart_prescan(_lines(DART))
    test_lines = sorted(f[0] for f in funcs)
    assert test_lines == [4, 8]


def test_brace_matched_end_lines():
    lc, _funcs, _first = dart_prescan(_lines(DART))
    # First test spans 4..6 (closing }); line 5 is inside it.
    assert lc[5][2] == 4
    assert lc[5][3] == 6


def test_runaway_span_is_bounded_by_next_test_start():
    # A test() whose braces never balance (e.g. brace hidden in a raw string)
    # must NOT swallow the following test; its span ends before the next start.
    src = """\
void main() {
  test('broken has a stray brace in a string r"{"', () {
    expect('{', '{');
  test('next test still distinct', () {
    expect(1, 1);
  });
}
"""
    lc, funcs, _first = dart_prescan(_lines(src))
    starts = sorted(f[0] for f in funcs)
    assert starts == [2, 4]  # both tests detected
    assert lc[2][3] <= 3  # first span capped before line 4


def test_clean_file_emits_no_warning(capsys):
    # Verifies: REQ-d00254-G
    # The well-formed DART fixture (all tests close cleanly) must NOT warn.
    dart_prescan(_lines(DART))
    assert "may be inaccurate" not in capsys.readouterr().err


def test_clamped_runaway_emits_warning(capsys):
    # Verifies: REQ-d00254-G
    # A test() whose braces never balance before the next test clamps -> warn.
    src = """\
void main() {
  test('broken has a stray brace in a string r"{"', () {
    expect('{', '{');
  test('next test still distinct', () {
    expect(1, 1);
  });
}
"""
    dart_prescan(_lines(src))
    assert "may be inaccurate" in capsys.readouterr().err


def test_inline_bracket_in_quote_that_closes_cleanly_does_not_warn(capsys):
    # Verifies: REQ-d00254-G
    # A bracket inside a quote on a single-line test that still finds a clean
    # close must NOT warn (this is the false-positive the old heuristic produced).
    src = """\
void main() {
  test('has { brace in quote', () { expect(1, 1); });
}
"""
    dart_prescan(_lines(src))
    assert "may be inaccurate" not in capsys.readouterr().err


def test_string_literal_brackets_do_not_break_span(capsys):
    # A JSON-ish string literal with an unbalanced bracket inside it must NOT
    # unbalance the brace count: the test closes cleanly at its own `});`, the
    # span is correct, and no warning fires. (Old code clamped here.)
    src = """\
void main() {
  test('returns json', () async {
    expect(body, 'starts with { but no close in string');
  });
  test('next test', () {
    expect(1, 1);
  });
}
"""
    lc, funcs, _first = dart_prescan(_lines(src))
    starts = sorted(f[0] for f in funcs)
    assert starts == [2, 5]
    # first test span ends at its own `});` (line 4), NOT clamped to line 4-before-5
    assert lc[3][2] == 2 and lc[3][3] == 4
    assert "may be inaccurate" not in capsys.readouterr().err


def test_double_slash_inside_string_is_not_a_comment(capsys):
    # A URL like 'http://x/me' must NOT be treated as a // line comment (which
    # would strip the closing brackets and unbalance the span).
    src = """\
void main() {
  test('hits a url', () async {
    final req = Request('GET', Uri.parse('http://x/me'));
    expect(req, isNotNull);
  });
  test('next', () {
    expect(1, 1);
  });
}
"""
    lc, funcs, _first = dart_prescan(_lines(src))
    starts = sorted(f[0] for f in funcs)
    assert starts == [2, 6]
    assert lc[3][3] == 5  # first test closes at its own `});` (line 5), not clamped
    assert "may be inaccurate" not in capsys.readouterr().err


def test_multiline_string_does_not_break_balance(capsys):
    # Verifies: REQ-d00254-G
    # Reduced from the real-world regression in
    # apps/sponsor-portal/portal_server_evs/test/seed_config_test.dart: a
    # triple-quoted heredoc string spans several lines and its embedded JSON
    # braces/brackets must not be counted as Dart code brackets, and must not
    # cause the first test's span to be clamped by the second test's start.
    src = """\
void main() {
  test('parses users + assignments with all scope encodings', () {
    final seed = parseSeedUsers('''
{
  "users": [
    { "role": "SystemOperator", "scope": { "class": "tier", "wildcard": true } }
  ]
}
''');
    expect(seed.entries, hasLength(4));
  });
  test('second test', () {
    expect(1, 1);
  });
}
"""
    lc, funcs, _first = dart_prescan(_lines(src))
    starts = sorted(f[0] for f in funcs)
    assert starts == [2, 12]
    # line 5 is inside the heredoc, owned by the first test (2), not corrupted
    # by the embedded braces
    assert lc[5][2] == 2
    # first test closes at its own `});` (line 11), not clamped by the second
    # test's start (line 12)
    assert lc[5][3] == 11
    assert "may be inaccurate" not in capsys.readouterr().err


def test_raw_string_single_backslash_is_not_an_escape(capsys):
    # Verifies: REQ-d00254-G
    # Reduced from the real-world regression in
    # apps/common-dart/canonical_json_jcs/test/canonical_json_test.dart line
    # 98: `r'\\'` is a RAW string containing one literal backslash -- the
    # backslash does NOT escape the closing quote. A scanner that applies
    # normal escape rules inside raw strings mis-finds the string boundary,
    # corrupting the bracket count for the rest of the line and clamping (or
    # miscounting) the test's span.
    src = """\
void main() {
  test('JSON special escapes', () {
    expect(canonicalize(r'\\'), r'"\\\\"');
  });
  test('next test', () {
    expect(1, 1);
  });
}
"""
    lc, funcs, _first = dart_prescan(_lines(src))
    starts = sorted(f[0] for f in funcs)
    assert starts == [2, 5]
    # first test closes at its own `});` (line 4), not clamped to the second
    # test's start (line 5)
    assert lc[3][3] == 4
    assert "may be inaccurate" not in capsys.readouterr().err


def test_span_never_inverts():
    # Verifies: REQ-d00254-G
    # A clamped span must never produce end < start (the observed regression:
    # a TEST node with parse_line=56, parse_end_line=53). Exercise the clamp
    # path in _match_brace_end directly with an adversarial stop_line equal to
    # the span's own start line -- without the max() guard this computes
    # `stop_line - 1`, one line BEFORE the start.
    lines = [(56, "  test('adversarial', () {"), (57, "    expect(1, 1);")]
    end, accurate = _match_brace_end(lines, 0, stop_line=56)
    assert end >= lines[0][0]
    assert accurate is False


# ---------------------------------------------------------------------------
# Forward binding: an unowned comment binds to the first declaration below it,
# walking down while it meets only further comments and blank lines.  There is
# no line limit -- the length of a comment block says nothing about what it
# describes -- so the guard against a file header claiming the first
# declaration in the file is the first line that is neither.
# ---------------------------------------------------------------------------

# A citation seven lines above its test(): further than any five-line window
# could reach, and followed by a second citation two lines above it.  Both name
# the same test, and both must bind to it.
LONG_PROSE_DART = """\
void main() {
  group('seed config', () {
    // Verifies: REQ-p00001-A
    // The seed parser reads a document holding users and assignments,
    // and the encoding of a scope varies by role, so this case walks
    // every encoding the fixture holds rather than asserting one of
    // them and trusting the rest to follow.
    // Verifies: REQ-p00001-B
    // (the second citation names the assertion about assignments)
    test('parses users and assignments', () {
      expect(1, 1);
    });
  });
}
"""

# A citation describing a whole group, written directly above the group() that
# opens it.  It belongs to the group, not to the first test() inside it.
GROUP_CITATION_DART = """\
void main() {
  // Verifies: REQ-p00001-C
  group('the whole area', () {
    test('a', () {
      expect(1, 1);
    });
  });
}
"""

# A file header, a blank line, and then an import: the import is neither a
# comment nor a declaration, so it ends the search and the header binds to
# nothing further down the file.
HEADER_THEN_IMPORT_DART = """\
// Copyright 2026 Example.
// Verifies: REQ-p00001-D

import 'package:test/test.dart';

group('everything', () {
  test('a', () {
    expect(1, 1);
  });
});
"""

# The same header with the import taken out: nothing but blank lines stands
# between it and the group(), so it does bind.  This is what makes the case
# above a statement about the import rather than about the distance.
HEADER_NO_IMPORT_DART = """\
// Copyright 2026 Example.
// Verifies: REQ-p00001-D


group('everything', () {
  test('a', () {
    expect(1, 1);
  });
});
"""


@pytest.mark.parametrize(
    ("source", "comment_line", "expected_owner_start"),
    [
        pytest.param(LONG_PROSE_DART, 3, 10, id="citation-above-six-prose-lines"),
        pytest.param(LONG_PROSE_DART, 8, 10, id="second-citation-above-same-test"),
        pytest.param(GROUP_CITATION_DART, 2, 3, id="citation-above-group"),
        pytest.param(HEADER_NO_IMPORT_DART, 2, 5, id="header-reaching-group-over-blanks"),
    ],
)
def test_comment_binds_to_first_declaration_below(source, comment_line, expected_owner_start):
    # Verifies: REQ-d00254-K
    # Attribution binds a scanned test to its own identity and extent; a
    # citation written above a test is attributed to that test, however much
    # prose sits between them, and a citation above a group() is attributed to
    # the group rather than falling through to the first test inside it.
    lc, _funcs, _first = dart_prescan(_lines(source))
    assert lc[comment_line][2] == expected_owner_start


@pytest.mark.parametrize(
    ("source", "comment_line"),
    [
        pytest.param(HEADER_THEN_IMPORT_DART, 1, id="header-first-line"),
        pytest.param(HEADER_THEN_IMPORT_DART, 2, id="header-citation-line"),
    ],
)
def test_comment_does_not_bind_across_a_non_comment_line(source, comment_line):
    # Verifies: REQ-d00254-K
    # The negative space of per-test attribution: a file header separated from
    # the first declaration by an import describes the file, not that
    # declaration, and binding it there would attribute a citation to a test it
    # says nothing about.
    lc, _funcs, _first = dart_prescan(_lines(source))
    assert lc[comment_line][2] == 0
