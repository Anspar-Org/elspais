# tests/core/test_dart_prescan.py
# Verifies: REQ-d00254-G
"""dart_prescan detects test() boundaries by regex + brace matching so each
Dart test case becomes a line-anchored unit, without a Dart parser."""
from __future__ import annotations

from elspais.graph.parsers.prescan import dart_prescan


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


def test_brackets_in_quotes_emit_warning(capsys):
    src = """\
void main() {
  test('has { brace in quote', () { expect(1, 1); });
}
"""
    dart_prescan(_lines(src))
    err = capsys.readouterr().err
    assert "may be inaccurate" in err
