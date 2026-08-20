# Verifies: REQ-d00254-G
"""Per-test crediting for line-resolved source results.

A source RESULT carrying ``match_scope = "test"`` (line resolved to a
specific Dart test() call) credits only ITS own assertion-targets: the
passing result credits its assertions; the failing result flags only its own
test without dragging down unrelated assertions.

A source RESULT that resolves no further than its file carries
``match_scope = "file"``: it names every test written there and so names none
of them, and contributes no verdict in either direction.
"""

from __future__ import annotations

import pytest

from elspais.config.schema import ElspaisConfig
from elspais.graph.annotators import CoverageCreditConfig, annotate_coverage
from elspais.graph.parsers.lark import FileDispatcher
from elspais.utilities.patterns import IdPatternConfig, IdResolver
from tests.core.graph_test_helpers import (
    MockSourceContext,
    build_graph,
    make_requirement,
    make_test_result,
)


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

    Mixed pass+fail, and neither result resolved to a test: no verdict reaches
    either assertion.
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
    assert m.verified.total_by_label.get("A", 0.0) == 1.0, (
        "A should be credited since r_pass (match_scope='test') passed for test-A"
    )


def test_per_test_fail_does_not_credit_its_own_assertion(graph_per_test_credit):
    """Assertion B is NOT credited because test-B (match_scope='test') failed."""
    m = graph_per_test_credit.find_by_id("REQ-p00001").get_metric("rollup_metrics")
    assert m.verified.total_by_label.get("B", 0.0) == 0.0, (
        "B should not be credited since r_fail (match_scope='test') failed for test-B"
    )


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
    assert r_pass.get_field("match_scope") == "test", (
        f"r_pass should have match_scope='test', got {r_pass.get_field('match_scope')!r}"
    )
    assert r_fail.get_field("match_scope") == "test", (
        f"r_fail should have match_scope='test', got {r_fail.get_field('match_scope')!r}"
    )


# ---------------------------------------------------------------------------
# A result that stopped at the file names no test
# ---------------------------------------------------------------------------


# Verifies: REQ-d00254-A
def test_file_scope_results_carry_no_verdict(graph_file_scope_fallback):
    """match_scope='file' results (line=None fallback) credit nothing and
    flag nothing.

    A failing result in the file is not evidence against an assertion the
    failing test never named, and a passing one beside it is not evidence for
    it either. Both assertions are tested and awaiting a result."""
    m = graph_file_scope_fallback.find_by_id("REQ-p00001").get_metric("rollup_metrics")
    # The `Verifies:` linkage is live for both assertions...
    assert m.tested.total_by_label.get("A") == 1.0
    assert m.tested.total_by_label.get("B") == 1.0
    # ...and the results reached neither of them.
    assert m.verified.has_failures is False
    assert m.verified.failing_labels == set()
    assert m.verified.total_by_label.get("A", 0.0) == 0.0
    assert m.verified.total_by_label.get("B", 0.0) == 0.0


def test_file_scope_match_scope_is_file_for_null_line(graph_file_scope_fallback):
    """Results with line=None carry match_scope='file'."""
    r_pass = graph_file_scope_fallback.find_by_id("r_pass2")
    r_fail = graph_file_scope_fallback.find_by_id("r_fail2")
    assert r_pass is not None
    assert r_fail is not None
    assert r_pass.get_field("match_scope") == "file", (
        f"r_pass2 should have match_scope='file', got {r_pass.get_field('match_scope')!r}"
    )
    assert r_fail.get_field("match_scope") == "file", (
        f"r_fail2 should have match_scope='file', got {r_fail.get_field('match_scope')!r}"
    )
