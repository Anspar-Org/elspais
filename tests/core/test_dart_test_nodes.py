# Verifies: REQ-d00254-G
"""Integration: .dart test files parsed through the full parse->build pipeline
produce one TEST node per test() call, anchored at the test() line.

Exercises the two-part fix for CUR-1533 Task 2:
  a) dispatch_test routes .dart files to dart_prescan (not text_prescan).
  b) The builder's line-based-id else branch keys on func_line (the test()
     call-site line) rather than content.start_line (the comment line).

The test uses a 2-test Dart file where each test() is preceded by a distinct
// Verifies: comment.  Before the fix both TEST nodes have parse_line on the
comment line; after the fix they land on the test() call line.
"""
from __future__ import annotations

import pytest

from elspais.graph.GraphNode import NodeKind
from elspais.graph.parsers.lark import FileDispatcher
from elspais.graph.relations import EdgeKind
from elspais.utilities.patterns import IdPatternConfig, IdResolver
from tests.core.graph_test_helpers import MockSourceContext, build_graph, make_requirement

# ---------------------------------------------------------------------------
# Dart file under test
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

# Line numbers (1-indexed) for the two test() call sites:
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


@pytest.fixture(scope="module")
def dart_graph(resolver):
    """Graph built from DART_FILE through the actual dispatch_test pipeline."""
    dispatcher = FileDispatcher(resolver)
    items = dispatcher.dispatch_test(DART_FILE, file_path=DART_PATH)
    # Attach source_context so build_graph can create the FILE node.
    for item in items:
        item.source_context = MockSourceContext(DART_PATH)

    req = make_requirement(
        "REQ-p00001",
        assertions=[
            {"label": "A", "text": "SHALL alpha"},
            {"label": "B", "text": "SHALL beta"},
        ],
    )
    return build_graph(req, *items)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_dart_yields_two_test_nodes(dart_graph):
    """Parsing a .dart file with two test() calls produces exactly two TEST nodes."""
    tests = list(dart_graph.iter_by_kind(NodeKind.TEST))
    ids = [t.id for t in tests]
    assert len(tests) == 2, f"expected 2 TEST nodes, got {len(tests)}: {ids}"


def test_dart_test_node_parse_line_equals_test_call_line(dart_graph):
    """parse_line of each TEST node equals the test() call-site line, not the comment line."""
    tests = sorted(dart_graph.iter_by_kind(NodeKind.TEST), key=lambda n: n.get_field("parse_line"))
    assert len(tests) == 2, f"need 2 TEST nodes to check parse_lines, got {len(tests)}"

    assert (
        tests[0].get_field("parse_line") == TEST_A_LINE
    ), f"Test A: expected parse_line={TEST_A_LINE}, got {tests[0].get_field('parse_line')}"
    assert (
        tests[1].get_field("parse_line") == TEST_B_LINE
    ), f"Test B: expected parse_line={TEST_B_LINE}, got {tests[1].get_field('parse_line')}"


def test_dart_each_test_verifies_only_its_own_assertion(dart_graph):
    """A test() preceded by // Verifies: REQ-p00001-A VERIFIES only assertion A, not B."""
    tests = sorted(dart_graph.iter_by_kind(NodeKind.TEST), key=lambda n: n.get_field("parse_line"))
    assert len(tests) == 2, f"need 2 TEST nodes, got {len(tests)}"
    test_a, test_b = tests[0], tests[1]

    req = dart_graph.find_by_id("REQ-p00001")
    assert req is not None, "REQ-p00001 not found in graph"

    def assertion_targets_for(test_node):
        """Return the assertion_targets labels from all VERIFIES edges pointing to test_node."""
        targets = []
        for edge in req.iter_outgoing_edges():
            if edge.kind == EdgeKind.VERIFIES and edge.target is test_node:
                targets.extend(edge.assertion_targets)
        return sorted(targets)

    a_targets = assertion_targets_for(test_a)
    b_targets = assertion_targets_for(test_b)

    assert a_targets == [
        "A"
    ], f"Test A (parse_line={test_a.get_field('parse_line')}) should VERIFIES [A], got {a_targets}"
    assert b_targets == [
        "B"
    ], f"Test B (parse_line={test_b.get_field('parse_line')}) should VERIFIES [B], got {b_targets}"
