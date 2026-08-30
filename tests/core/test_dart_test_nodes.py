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

from elspais.config.schema import ElspaisConfig
from elspais.graph.GraphNode import NodeKind
from elspais.graph.parsers.lark import FileDispatcher
from elspais.graph.relations import EdgeKind
from elspais.utilities.patterns import IdPatternConfig, IdResolver
from tests.core.graph_test_helpers import MockSourceContext, build_graph, make_requirement


def _validated(config: dict) -> dict:
    """Return ``config`` after checking a configuration file could hold it.

    ``IdPatternConfig.from_dict`` takes a raw dictionary and never consults the
    config schema, so a fixture built here could describe a repository no
    ``.elspais.toml`` can produce -- and pin grammar behaviour no user can
    reach. Every fixture is therefore validated the way a file on disk is,
    before any resolver is built from it.
    """
    ElspaisConfig.model_validate(config)
    return config


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
        _validated(
            {
                "project": {"namespace": "REQ"},
                "levels": {
                    "prd": {"rank": 1, "letter": "p", "implements": ["prd"]},
                    "ops": {"rank": 2, "letter": "o", "implements": ["ops", "prd"]},
                    "dev": {"rank": 3, "letter": "d", "implements": ["dev", "ops", "prd"]},
                },
                "id-patterns": {
                    "canonical": "{namespace}-{level.letter}{component}",
                    "aliases": {"short": "{level.letter}{component}"},
                    "component": {"style": "numeric", "digits": 5, "leading_zeros": True},
                    "assertions": {"label_style": "uppercase", "max_count": 26},
                },
            }
        )
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

    assert tests[0].get_field("parse_line") == TEST_A_LINE, (
        f"Test A: expected parse_line={TEST_A_LINE}, got {tests[0].get_field('parse_line')}"
    )
    assert tests[1].get_field("parse_line") == TEST_B_LINE, (
        f"Test B: expected parse_line={TEST_B_LINE}, got {tests[1].get_field('parse_line')}"
    )


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

    assert a_targets == ["A"], (
        f"Test A (parse_line={test_a.get_field('parse_line')}) should VERIFIES [A], got {a_targets}"
    )
    assert b_targets == ["B"], (
        f"Test B (parse_line={test_b.get_field('parse_line')}) should VERIFIES [B], got {b_targets}"
    )


# ---------------------------------------------------------------------------
# Regression: text_prescan zero-sentinel must not collapse line-based TEST ids
#
# For non-Python, non-Dart test files (e.g. .js), text_prescan stores
# function_line=0 when a // Verifies: comment sits outside any detected
# function.  Before the fix, data.get("function_line", content.start_line)
# returns 0 (not the comment line), so ALL such refs collapse to
# make_test_id(source_id, 0) — a single TEST node at line 0.
# After the fix, the else branch uses `func_line or content.start_line` so
# each ref is anchored at its own comment line.
# ---------------------------------------------------------------------------

# A JS file with two top-level // Verifies: comments outside any function.
#
#   1: // Verifies: REQ-p00001-A    <-- JS_LINE_A
#   2: (empty)
#   3: // Verifies: REQ-p00001-B    <-- JS_LINE_B
JS_FILE = """\
// Verifies: REQ-p00001-A

// Verifies: REQ-p00001-B
"""

JS_PATH = "tests/widget_test.js"
JS_LINE_A = 1  # line number of first // Verifies: comment
JS_LINE_B = 3  # line number of second // Verifies: comment


@pytest.fixture(scope="module")
def js_graph(resolver):
    """Graph built from JS_FILE through the actual dispatch_test pipeline.

    text_prescan is used (not dart_prescan) because the file extension is .js.
    Both // Verifies: comments are outside any detected function, so
    text_prescan stores function_line=0 for every line.
    """
    dispatcher = FileDispatcher(resolver)
    items = dispatcher.dispatch_test(JS_FILE, file_path=JS_PATH)
    for item in items:
        item.source_context = MockSourceContext(JS_PATH)

    req = make_requirement(
        "REQ-p00001",
        assertions=[
            {"label": "A", "text": "SHALL alpha"},
            {"label": "B", "text": "SHALL beta"},
        ],
    )
    return build_graph(req, *items)


def test_js_zero_sentinel_yields_two_test_nodes(js_graph):
    """text_prescan zero-sentinel: two top-level // Verifies: produce two distinct TEST nodes."""
    tests = list(js_graph.iter_by_kind(NodeKind.TEST))
    ids = [t.id for t in tests]
    assert len(tests) == 2, (
        f"expected 2 TEST nodes (one per // Verifies: comment), got {len(tests)}: {ids}\n"
        f"BUG: func_line=0 sentinel collapsed both refs to the same make_test_id"
    )


def test_js_zero_sentinel_parse_lines_match_comment_lines(js_graph):
    """text_prescan zero-sentinel: each TEST node anchored at its own comment line, not line 0."""
    tests = sorted(js_graph.iter_by_kind(NodeKind.TEST), key=lambda n: n.get_field("parse_line"))
    assert len(tests) == 2, f"need 2 TEST nodes, got {len(tests)}"

    assert tests[0].get_field("parse_line") == JS_LINE_A, (
        f"Test A: expected parse_line={JS_LINE_A} (comment line), "
        f"got {tests[0].get_field('parse_line')} — line 0 means zero-sentinel collapsed them"
    )
    assert tests[1].get_field("parse_line") == JS_LINE_B, (
        f"Test B: expected parse_line={JS_LINE_B} (comment line), "
        f"got {tests[1].get_field('parse_line')}"
    )


# ---------------------------------------------------------------------------
# Integration: a citation separated from its test() by a block of prose
#
# The binding rule has no line limit, so the TEST node lands on the test() call
# site however long the comment block above it is.  When the binding was
# limited to a five-line forward window this citation reached nothing, and the
# builder anchored the TEST node at the COMMENT's own line -- a node no result
# recorded at the test's real line can ever match (REQ-d00254-G), so the
# assertion read as tested and never as passing.
# ---------------------------------------------------------------------------

#   1: void main() {
#   2:   // Verifies: REQ-p00001-A
#   3..7: prose
#   8:   test('alpha test', () {   <-- LONG_TEST_LINE, six lines below the citation
LONG_COMMENT_DART = """\
void main() {
  // Verifies: REQ-p00001-A
  // The alpha path is described at length here, because the length of a
  // comment block says nothing about what that block describes.  The
  // citation above names the test that follows it whether the author
  // wrote one line of prose in between or a dozen, and the reader who
  // wrote the dozen did not thereby mean a different test.
  test('alpha test', () {
    expect(1, 1);
  });
}
"""

LONG_COMMENT_PATH = "test/long_comment_test.dart"
LONG_TEST_LINE = 8


@pytest.fixture(scope="module")
def long_comment_graph(resolver):
    """Graph built from LONG_COMMENT_DART through the actual dispatch_test pipeline."""
    dispatcher = FileDispatcher(resolver)
    items = dispatcher.dispatch_test(LONG_COMMENT_DART, file_path=LONG_COMMENT_PATH)
    for item in items:
        item.source_context = MockSourceContext(LONG_COMMENT_PATH)

    req = make_requirement(
        "REQ-p00001",
        assertions=[
            {"label": "A", "text": "SHALL alpha"},
            {"label": "B", "text": "SHALL beta"},
        ],
    )
    return build_graph(req, *items)


def test_citation_above_a_prose_block_anchors_on_the_test_call_line(long_comment_graph):
    # Verifies: REQ-d00254-K
    """One TEST node, anchored at the test() call site rather than the citation line."""
    tests = list(long_comment_graph.iter_by_kind(NodeKind.TEST))
    assert len(tests) == 1, f"expected 1 TEST node, got {len(tests)}: {[t.id for t in tests]}"
    assert tests[0].get_field("parse_line") == LONG_TEST_LINE, (
        f"expected parse_line={LONG_TEST_LINE} (the test() line), "
        f"got {tests[0].get_field('parse_line')} — a citation that reaches no test is "
        f"anchored at its own comment line, where no result can ever match it"
    )


def test_citation_above_a_prose_block_still_verifies_its_assertion(long_comment_graph):
    # Verifies: REQ-d00254-K
    """The test anchored at the test() line carries the assertion the citation named."""
    req = long_comment_graph.find_by_id("REQ-p00001")
    assert req is not None, "REQ-p00001 not found in graph"
    tests = list(long_comment_graph.iter_by_kind(NodeKind.TEST))
    assert len(tests) == 1, f"need 1 TEST node, got {len(tests)}"

    targets = sorted(
        label
        for edge in req.iter_outgoing_edges()
        if edge.kind == EdgeKind.VERIFIES and edge.target is tests[0]
        for label in edge.assertion_targets
    )
    assert targets == ["A"]
