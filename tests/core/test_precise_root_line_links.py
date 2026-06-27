# Verifies: REQ-d00254-G
"""Precise RESULT->TEST linking via ``root_line`` / ``root_file`` fallback.

For ``testWidgets(...)`` tests the flutter ``--machine`` protocol reports
``test.line`` as the *framework wrapper* line (e.g.
``package:flutter_test/src/widget_tester.dart:174``), NOT the user's call
site.  The real call site is in ``test.root_line`` + ``test.root_url``.

This test file exercises the two-attempt resolver in ``build()``:
  1. Try ``(source_file, line)`` — primary path (must still win when it
     resolves, so the direct path is not broken by this change).
  2. If no match and ``root_line`` is set, try
     ``(root_file or source_file, root_line)`` — widget-test recovery.
  3. If still no match, fall back to every TEST in ``source_file``.
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
WRAPPER_LINE = 9999  # simulates framework wrapper line that won't match any TEST


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


def _sorted_tests(graph):
    """Return TEST nodes sorted by parse_line."""
    return sorted(graph.iter_by_kind(NodeKind.TEST), key=lambda n: n.get_field("parse_line"))


# ---------------------------------------------------------------------------
# Fixture: root_line resolves to test_a when line misses
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def graph_root_resolves_a(resolver):
    """Result with wrapper line + root_line=TEST_A_LINE must link to test_a only."""
    items = _dart_items(resolver)
    r = make_test_result(
        "r_root_a",
        source_file=DART_PATH,
        match="source",
        line=WRAPPER_LINE,
        root_line=TEST_A_LINE,
        root_file=DART_PATH,
    )
    return build_graph(_req(), *items, r)


@pytest.fixture(scope="module")
def graph_root_resolves_b(resolver):
    """Result with wrapper line + root_line=TEST_B_LINE must link to test_b only."""
    items = _dart_items(resolver)
    r = make_test_result(
        "r_root_b",
        source_file=DART_PATH,
        match="source",
        line=WRAPPER_LINE,
        root_line=TEST_B_LINE,
        root_file=DART_PATH,
    )
    return build_graph(_req(), *items, r)


@pytest.fixture(scope="module")
def graph_primary_wins(resolver):
    """When line matches directly, root_line must NOT change the target."""
    items = _dart_items(resolver)
    # line=TEST_A_LINE matches directly; root_line points at test_b -- must be ignored
    r = make_test_result(
        "r_primary",
        source_file=DART_PATH,
        match="source",
        line=TEST_A_LINE,
        root_line=TEST_B_LINE,
        root_file=DART_PATH,
    )
    return build_graph(_req(), *items, r)


@pytest.fixture(scope="module")
def graph_both_miss(resolver):
    """When both line and root_line miss, fall back to all tests in the file."""
    items = _dart_items(resolver)
    r = make_test_result(
        "r_both_miss",
        source_file=DART_PATH,
        match="source",
        line=WRAPPER_LINE,
        root_line=WRAPPER_LINE + 1,
        root_file=DART_PATH,
    )
    return build_graph(_req(), *items, r)


@pytest.fixture(scope="module")
def graph_root_no_file(resolver):
    """root_line set but root_file=None: use source_file as root file."""
    items = _dart_items(resolver)
    r = make_test_result(
        "r_root_no_file",
        source_file=DART_PATH,
        match="source",
        line=WRAPPER_LINE,
        root_line=TEST_A_LINE,
        root_file=None,
    )
    return build_graph(_req(), *items, r)


# ---------------------------------------------------------------------------
# Tests: root_line resolves to specific test
# ---------------------------------------------------------------------------


def test_root_line_resolves_to_test_a(graph_root_resolves_a):
    """Result with wrapper line but root_line=TEST_A_LINE links to test_a only."""
    tests = _sorted_tests(graph_root_resolves_a)
    assert len(tests) == 2, f"expected 2 TEST nodes, got {[t.id for t in tests]}"
    test_a, test_b = tests

    a_results = {c.id for c in test_a.iter_children() if c.kind == NodeKind.RESULT}
    b_results = {c.id for c in test_b.iter_children() if c.kind == NodeKind.RESULT}

    assert "r_root_a" in a_results, f"r_root_a should be in test_a children; got {a_results}"
    assert "r_root_a" not in b_results, f"r_root_a must NOT be in test_b children; got {b_results}"


def test_root_line_resolves_to_test_b(graph_root_resolves_b):
    """Result with wrapper line but root_line=TEST_B_LINE links to test_b only."""
    tests = _sorted_tests(graph_root_resolves_b)
    test_a, test_b = tests

    b_results = {c.id for c in test_b.iter_children() if c.kind == NodeKind.RESULT}
    a_results = {c.id for c in test_a.iter_children() if c.kind == NodeKind.RESULT}

    assert "r_root_b" in b_results, f"r_root_b should be in test_b children; got {b_results}"
    assert "r_root_b" not in a_results, f"r_root_b must NOT be in test_a children; got {a_results}"


def test_root_resolved_match_scope_is_test(graph_root_resolves_a):
    """Root-line-resolved result carries match_scope='test'."""
    r = graph_root_resolves_a.find_by_id("r_root_a")
    assert r is not None
    assert (
        r.get_field("match_scope") == "test"
    ), f"expected match_scope='test', got {r.get_field('match_scope')!r}"


def test_root_resolved_edge_kind_is_yields(graph_root_resolves_a):
    """The TEST->RESULT edge produced by root_line resolution is YIELDS."""
    tests = _sorted_tests(graph_root_resolves_a)
    test_a = tests[0]
    yields_ids = {e.target.id for e in test_a.iter_outgoing_edges() if e.kind == EdgeKind.YIELDS}
    assert "r_root_a" in yields_ids, f"Expected YIELDS edge to r_root_a; got {yields_ids}"


# ---------------------------------------------------------------------------
# Regression: primary (source_file, line) path still wins
# ---------------------------------------------------------------------------


def test_primary_line_wins_when_it_matches(graph_primary_wins):
    """When line matches directly, root_line must not redirect the link."""
    tests = _sorted_tests(graph_primary_wins)
    test_a, test_b = tests

    a_results = {c.id for c in test_a.iter_children() if c.kind == NodeKind.RESULT}
    b_results = {c.id for c in test_b.iter_children() if c.kind == NodeKind.RESULT}

    assert (
        "r_primary" in a_results
    ), f"r_primary (line=TEST_A_LINE) should link to test_a; got a={a_results} b={b_results}"
    assert (
        "r_primary" not in b_results
    ), "r_primary must NOT appear in test_b (root_line should be ignored when line matched)"


def test_primary_scope_is_test_when_direct_match(graph_primary_wins):
    """A directly-matched result still carries match_scope='test'."""
    r = graph_primary_wins.find_by_id("r_primary")
    assert r is not None
    assert r.get_field("match_scope") == "test"


# ---------------------------------------------------------------------------
# Tests: both line and root_line miss -> file fallback
# ---------------------------------------------------------------------------


def test_both_miss_falls_back_to_all_tests(graph_both_miss):
    """When both line and root_line don't match, fall back to all tests."""
    tests = list(graph_both_miss.iter_by_kind(NodeKind.TEST))
    assert len(tests) == 2
    for test_node in tests:
        result_ids = {c.id for c in test_node.iter_children() if c.kind == NodeKind.RESULT}
        assert (
            "r_both_miss" in result_ids
        ), f"r_both_miss should be in {test_node.id} children (fallback); got {result_ids}"


def test_both_miss_scope_is_file(graph_both_miss):
    """When both attempts fail, match_scope='file'."""
    r = graph_both_miss.find_by_id("r_both_miss")
    assert r is not None
    assert r.get_field("match_scope") == "file"


# ---------------------------------------------------------------------------
# Tests: root_line with no root_file -> uses source_file
# ---------------------------------------------------------------------------


def test_root_no_file_uses_source_file(graph_root_no_file):
    """root_line with root_file=None uses source_file as the fallback path."""
    tests = _sorted_tests(graph_root_no_file)
    test_a = tests[0]

    a_results = {c.id for c in test_a.iter_children() if c.kind == NodeKind.RESULT}
    assert (
        "r_root_no_file" in a_results
    ), f"r_root_no_file (root_file=None) should link test_a via source_file; got {a_results}"


def test_root_no_file_scope_is_test(graph_root_no_file):
    """root_line resolution via source_file (no root_file) still gives match_scope='test'."""
    r = graph_root_no_file.find_by_id("r_root_no_file")
    assert r is not None
    assert r.get_field("match_scope") == "test"
