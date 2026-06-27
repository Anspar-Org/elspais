# Verifies: REQ-d00254-G
"""Per-test crediting for line-resolved precise results.

A precise RESULT carrying ``match_scope = "test"`` (line resolved to a
specific Dart test() call) credits only ITS own assertion-targets: the
passing result credits its assertions; the failing result flags only its own
test without dragging down unrelated assertions.

A precise RESULT carrying ``match_scope = "file"`` keeps the existing
file-level semantics: any failure in the file flags the whole file and
withholds credit from all assertions (regression guard).
"""
from __future__ import annotations

import pytest

from elspais.graph.annotators import CoverageCreditConfig, annotate_coverage
from elspais.graph.parsers.lark import FileDispatcher
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

# Line numbers in DART_FILE (1-indexed):
#   1: void main() {
#   2:   // Verifies: REQ-p00001-A
#   3:   test('alpha test', () {   <-- TEST_A_LINE
#   4:     expect(1, 1);
#   5:   });
#   6: (blank)
#   7:   // Verifies: REQ-p00001-B
#   8:   test('beta test', () {    <-- TEST_B_LINE
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
def graph_per_test_credit(resolver):
    """test-A passes (match_scope=test), test-B fails (match_scope=test).

    r_pass is line-resolved to test-A; r_fail is line-resolved to test-B.
    After annotate_coverage, A should be credited (test-A passed) while
    B should NOT be credited, and has_failures should be True (test-B failed).
    """
    items = _dart_items(resolver)
    r_pass = make_test_result(
        "r_pass",
        status="passed",
        source_file=DART_PATH,
        match="source",
        line=TEST_A_LINE,
    )
    r_fail = make_test_result(
        "r_fail",
        status="failed",
        source_file=DART_PATH,
        match="source",
        line=TEST_B_LINE,
    )
    g = build_graph(_req(), *items, r_pass, r_fail)
    annotate_coverage(g, CoverageCreditConfig())
    return g


@pytest.fixture(scope="module")
def graph_file_scope_fallback(resolver):
    """Both results use match_scope=file (line=None -> fallback to all tests).

    Mixed pass+fail: file-level semantics apply -- any failure withholds
    credit from all assertions and flags has_failures.
    """
    items = _dart_items(resolver)
    r_pass = make_test_result(
        "r_pass2",
        status="passed",
        source_file=DART_PATH,
        match="source",
        line=None,
    )
    r_fail = make_test_result(
        "r_fail2",
        status="failed",
        source_file=DART_PATH,
        match="source",
        line=None,
    )
    g = build_graph(_req(), *items, r_pass, r_fail)
    annotate_coverage(g, CoverageCreditConfig())
    return g


# ---------------------------------------------------------------------------
# Main tests: per-test crediting for match_scope="test"
# ---------------------------------------------------------------------------


def test_per_test_pass_credits_only_its_assertions(graph_per_test_credit):
    """Assertion A is credited because test-A (match_scope='test') passed,
    even though test-B failed."""
    m = graph_per_test_credit.find_by_id("REQ-p00001").get_metric("rollup_metrics")
    assert (
        m.verified.direct_pct_by_label.get("A", 0.0) == 1.0
    ), "A should be credited since r_pass (match_scope='test') passed for test-A"


def test_per_test_fail_does_not_credit_its_own_assertion(graph_per_test_credit):
    """Assertion B is NOT credited because test-B (match_scope='test') failed."""
    m = graph_per_test_credit.find_by_id("REQ-p00001").get_metric("rollup_metrics")
    assert (
        m.verified.direct_pct_by_label.get("B", 0.0) == 0.0
    ), "B should not be credited since r_fail (match_scope='test') failed for test-B"


def test_per_test_failure_sets_has_failures(graph_per_test_credit):
    """has_failures is True because test-B failed."""
    m = graph_per_test_credit.find_by_id("REQ-p00001").get_metric("rollup_metrics")
    assert m.verified.has_failures is True


def test_per_test_match_scope_is_test_for_line_resolved_results(graph_per_test_credit):
    """Both line-resolved results carry match_scope='test'."""
    r_pass = graph_per_test_credit.find_by_id("r_pass")
    r_fail = graph_per_test_credit.find_by_id("r_fail")
    assert r_pass is not None
    assert r_fail is not None
    assert (
        r_pass.get_field("match_scope") == "test"
    ), f"r_pass should have match_scope='test', got {r_pass.get_field('match_scope')!r}"
    assert (
        r_fail.get_field("match_scope") == "test"
    ), f"r_fail should have match_scope='test', got {r_fail.get_field('match_scope')!r}"


# ---------------------------------------------------------------------------
# Regression: file-scope fallback semantics are preserved
# ---------------------------------------------------------------------------


def test_file_scope_any_fail_withholds_all_credit(graph_file_scope_fallback):
    """match_scope='file' results (line=None fallback): any failure in the
    file withholds credit from all assertions and sets has_failures.

    This guards the semantics of test_edges_do_not_change_file_level_metric_semantics
    in test_precise_result_links.py."""
    m = graph_file_scope_fallback.find_by_id("REQ-p00001").get_metric("rollup_metrics")
    assert m.verified.has_failures is True
    assert (
        m.verified.direct_pct_by_label.get("A", 0.0) == 0.0
    ), "A should NOT be credited when the file-scope result set contains a failure"
    assert (
        m.verified.direct_pct_by_label.get("B", 0.0) == 0.0
    ), "B should NOT be credited when the file-scope result set contains a failure"


def test_file_scope_match_scope_is_file_for_null_line(graph_file_scope_fallback):
    """Results with line=None carry match_scope='file'."""
    r_pass = graph_file_scope_fallback.find_by_id("r_pass2")
    r_fail = graph_file_scope_fallback.find_by_id("r_fail2")
    assert r_pass is not None
    assert r_fail is not None
    assert (
        r_pass.get_field("match_scope") == "file"
    ), f"r_pass2 should have match_scope='file', got {r_pass.get_field('match_scope')!r}"
    assert (
        r_fail.get_field("match_scope") == "file"
    ), f"r_fail2 should have match_scope='file', got {r_fail.get_field('match_scope')!r}"
