# tests/core/test_dart_prescan.py
# Verifies: REQ-d00254-G
"""dart_prescan detects test() boundaries by regex + brace matching so each
Dart test case becomes a line-anchored unit, without a Dart parser."""

from __future__ import annotations

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
