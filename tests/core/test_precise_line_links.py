# Verifies: REQ-d00254-G
"""Precise RESULT->TEST linking by (file, line): a result carrying ``line=L``
resolves to ONLY the TEST node whose ``parse_line`` equals L (not all tests in
the file).  A result with ``line=None`` (or a line that matches no TEST) falls
back to every TEST in the file -- the existing file-granular behaviour.

This tests the Task-3 extension to the precise resolver in ``build()``:
  * ``tests_by_file_line[(rel_path, parse_line)]`` for O(1) single-test lookup.
  * ``precise_scope`` field: "test" for a line-resolved link, "file" for fallback.
"""
from __future__ import annotations

import pytest

from elspais.graph.GraphNode import NodeKind
from elspais.graph.parsers.lark import FileDispatcher
from elspais.graph.relations import EdgeKind
from elspais.utilities.patterns import IdPatternConfig, IdResolver
from tests.core.graph_test_helpers import (
    MockSourceContext,
    build_graph,
    make_requirement,
    make_test_result,
)

# ---------------------------------------------------------------------------
# Shared Dart file -- two test() calls at known lines
# ---------------------------------------------------------------------------

DART_FILE = """\
void main() {
  // Verifies: REQ-p00001-A
  test('alpha test', () {
    expect(1, 1);
  });

  // Verifies: REQ-p00001-B
  test('beta test', () {
    expect(2, 2);
  });
}
"""

#   1: void main() {
#   2:   // Verifies: REQ-p00001-A
#   3:   test('alpha test', () {    <-- TEST_A_LINE
#   4:     expect(1, 1);
#   5:   });
#   6: (empty)
#   7:   // Verifies: REQ-p00001-B
#   8:   test('beta test', () {     <-- TEST_B_LINE
#   9:     expect(2, 2);
#  10:   });
#  11: }
DART_PATH = "test/widget_test.dart"
TEST_A_LINE = 3
TEST_B_LINE = 8


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def resolver():
    config = IdPatternConfig.from_dict(
        {
            "project": {"namespace": "REQ"},
            "id-patterns": {
                "canonical": "{namespace}-{type.letter}{component}",
                "aliases": {"short": "{type.letter}{component}"},
                "types": {
                    "prd": {"level": 1, "aliases": {"letter": "p"}},
                    "ops": {"level": 2, "aliases": {"letter": "o"}},
                    "dev": {"level": 3, "aliases": {"letter": "d"}},
                },
                "component": {"style": "numeric", "digits": 5, "leading_zeros": True},
                "assertions": {"label_style": "uppercase", "max_count": 26},
            },
        }
    )
    return IdResolver(config)


def _dart_items(resolver):
    """Parse DART_FILE through the real dispatch_test pipeline."""
    dispatcher = FileDispatcher(resolver)
    items = dispatcher.dispatch_test(DART_FILE, file_path=DART_PATH)
    for item in items:
        item.source_context = MockSourceContext(DART_PATH)
    return items


def _req():
    return make_requirement(
        "REQ-p00001",
        assertions=[
            {"label": "A", "text": "SHALL alpha"},
            {"label": "B", "text": "SHALL beta"},
        ],
    )


@pytest.fixture(scope="module")
def graph_line_matched(resolver):
    """Two precise results carrying line=TEST_A_LINE and line=TEST_B_LINE."""
    items = _dart_items(resolver)
    r1 = make_test_result("r1", source_file=DART_PATH, match="precise", line=TEST_A_LINE)
    r2 = make_test_result("r2", source_file=DART_PATH, match="precise", line=TEST_B_LINE)
    return build_graph(_req(), *items, r1, r2)


@pytest.fixture(scope="module")
def graph_fallback(resolver):
    """One precise result with line=None -- must fall back to all tests in file."""
    items = _dart_items(resolver)
    r3 = make_test_result("r3", source_file=DART_PATH, match="precise", line=None)
    return build_graph(_req(), *items, r3)


@pytest.fixture(scope="module")
def graph_nonmatch_line(resolver):
    """One precise result whose line does not match any TEST parse_line."""
    items = _dart_items(resolver)
    r4 = make_test_result("r4", source_file=DART_PATH, match="precise", line=9999)
    return build_graph(_req(), *items, r4)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sorted_tests(graph):
    """Return TEST nodes sorted by parse_line."""
    return sorted(graph.iter_by_kind(NodeKind.TEST), key=lambda n: n.get_field("parse_line"))


# ---------------------------------------------------------------------------
# Tests: line-resolved linking
# ---------------------------------------------------------------------------


def test_line_matched_result_links_only_own_test(graph_line_matched):
    """r1 (line=TEST_A_LINE) links to test_a only; r2 (line=TEST_B_LINE) to test_b only."""
    tests = _sorted_tests(graph_line_matched)
    assert len(tests) == 2, f"expected 2 TEST nodes, got {[t.id for t in tests]}"
    test_a, test_b = tests[0], tests[1]

    a_result_ids = {c.id for c in test_a.iter_children() if c.kind == NodeKind.RESULT}
    b_result_ids = {c.id for c in test_b.iter_children() if c.kind == NodeKind.RESULT}

    la = test_a.get_field("parse_line")
    lb = test_b.get_field("parse_line")
    assert a_result_ids == {
        "r1"
    }, f"test_a (parse_line={la}) should link only r1, got {a_result_ids}"
    assert b_result_ids == {
        "r2"
    }, f"test_b (parse_line={lb}) should link only r2, got {b_result_ids}"


def test_line_matched_result_not_in_other_test(graph_line_matched):
    """r1 must NOT appear as a child of test_b, and vice versa."""
    tests = _sorted_tests(graph_line_matched)
    test_a, test_b = tests[0], tests[1]

    b_result_ids = {c.id for c in test_b.iter_children() if c.kind == NodeKind.RESULT}
    a_result_ids = {c.id for c in test_a.iter_children() if c.kind == NodeKind.RESULT}

    assert "r1" not in b_result_ids, "r1 must not be a child of test_b"
    assert "r2" not in a_result_ids, "r2 must not be a child of test_a"


def test_precise_scope_is_test_for_line_resolved(graph_line_matched):
    """Line-resolved precise results carry precise_scope='test'."""
    r1 = graph_line_matched.find_by_id("r1")
    r2 = graph_line_matched.find_by_id("r2")
    assert r1 is not None
    assert r2 is not None
    assert (
        r1.get_field("precise_scope") == "test"
    ), f"r1 precise_scope should be 'test', got {r1.get_field('precise_scope')!r}"
    assert (
        r2.get_field("precise_scope") == "test"
    ), f"r2 precise_scope should be 'test', got {r2.get_field('precise_scope')!r}"


def test_line_matched_edge_kind_is_yields(graph_line_matched):
    """The RESULT->TEST edge is EdgeKind.YIELDS, same as test_id-based linking."""
    tests = _sorted_tests(graph_line_matched)
    test_a = tests[0]
    yields_targets = {
        e.target.id for e in test_a.iter_outgoing_edges() if e.kind == EdgeKind.YIELDS
    }
    assert "r1" in yields_targets, f"Expected r1 in YIELDS edges of test_a, got {yields_targets}"


# ---------------------------------------------------------------------------
# Tests: line=None fallback
# ---------------------------------------------------------------------------


def test_null_line_falls_back_to_all_tests(graph_fallback):
    """A precise result with line=None links to every TEST in the file."""
    tests = list(graph_fallback.iter_by_kind(NodeKind.TEST))
    assert len(tests) == 2, f"expected 2 TEST nodes, got {len(tests)}"
    for test_node in tests:
        result_ids = {c.id for c in test_node.iter_children() if c.kind == NodeKind.RESULT}
        assert (
            "r3" in result_ids
        ), f"r3 should be a child of {test_node.id} (fallback), got {result_ids}"


def test_precise_scope_is_file_for_null_line(graph_fallback):
    """A fallback precise result (line=None) carries precise_scope='file'."""
    r3 = graph_fallback.find_by_id("r3")
    assert r3 is not None
    assert (
        r3.get_field("precise_scope") == "file"
    ), f"r3 precise_scope should be 'file', got {r3.get_field('precise_scope')!r}"


# ---------------------------------------------------------------------------
# Tests: non-matching line fallback
# ---------------------------------------------------------------------------


def test_nonmatch_line_falls_back_to_all_tests(graph_nonmatch_line):
    """A precise result whose line matches no TEST parse_line falls back to all tests."""
    tests = list(graph_nonmatch_line.iter_by_kind(NodeKind.TEST))
    assert len(tests) == 2, f"expected 2 TEST nodes, got {len(tests)}"
    for test_node in tests:
        result_ids = {c.id for c in test_node.iter_children() if c.kind == NodeKind.RESULT}
        assert (
            "r4" in result_ids
        ), f"r4 should be a child of {test_node.id} (line-mismatch fallback), got {result_ids}"


def test_precise_scope_is_file_for_nonmatch_line(graph_nonmatch_line):
    """A precise result with a non-matching line carries precise_scope='file'."""
    r4 = graph_nonmatch_line.find_by_id("r4")
    assert r4 is not None
    assert (
        r4.get_field("precise_scope") == "file"
    ), f"r4 precise_scope should be 'file', got {r4.get_field('precise_scope')!r}"
