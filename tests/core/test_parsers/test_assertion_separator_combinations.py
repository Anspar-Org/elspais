# Verifies: REQ-d00082-E
"""Regression: configured assertion separator/multi-separator combinations
must parse correctly end-to-end (CUR-1568 Task 13).

Root cause: ``build_multi_assertion_pattern()`` (graph/parsers/patterns.py)
hardcoded the boundary between a requirement ID and its first assertion
label to the "-"/"_" characters, completely ignoring the configured
``[id-patterns.assertions] separator``. Repos configuring a non-"-"/"_"
separator (e.g. "/") silently lost the assertion suffix when extracting
``Verifies:`` references from test files -- the multi-assertion pattern
match stopped right before the separator character, dropping the rest of
the reference and producing a blanket (whole-requirement) edge instead of
a targeted one.

This reproduces the bug through the real production pipeline
(``elspais.graph.factory.build_graph``) against an on-disk project, mirroring
the confirmed manual repro: one PRD with assertions A, B, C and one test
file with a single ``# Verifies: <ref>`` comment.

A field incident showed that journey ``Validates:`` references are the same
risk surface: under a non-"-"/"_" separator, a correctly-styled ref wires
assertion-targeted VALIDATES edges (REQ -> journey, per the ``Validates:``
field behavior specified in spec/requirements-spec.md), while
a ref that still uses "-" produces a hard broken reference carrying a
separator-config diagnostic (REQ-d00252-G). The tests below extend the same
separator/multi-separator matrix to cover that path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from elspais.graph.GraphNode import NodeKind
from elspais.graph.relations import EdgeKind

_SPEC = """\
# REQ-p-widget: Widget

The system provides widgets.

## Assertions

A. The system SHALL frob.

B. The system SHALL twiddle.

C. The system SHALL blort.

*End* *REQ-p-widget*
"""

_CONFIG_TEMPLATE = """\
version = 3

[project]
name = "septest"
namespace = "REQ"

[id-patterns]
canonical = "{{namespace}}-{{level.letter}}-{{component}}"

[id-patterns.component]
style = "kebab-case"

[id-patterns.assertions]
label_style = "uppercase"
separator = "{sep}"
multi_separator = "{multi}"

[levels.prd]
rank = 1
letter = "p"
implements = []

[scanning.test]
enabled = true
directories = ["tests"]

[scanning.journey]
directories = ["spec"]
"""

_JOURNEY_TEMPLATE = """\
# JNY-T-01: Test Journey

The user exercises the widget end to end.

Validates: {ref}

*End* *JNY-T-01*
"""


def _make_project(
    tmp_path: Path,
    sep: str,
    multi: str,
    ref: str,
    journey_ref: str | None = None,
) -> Path:
    """Build a minimal on-disk project: one REQ with assertions A/B/C and
    one test file with a single ``# Verifies: <ref>`` comment.

    When ``journey_ref`` is given, also writes a journey file
    (``JNY-T-01``) whose ``Validates:`` line carries that ref, so tests can
    exercise the journey ``Validates:`` wiring path alongside (or instead
    of) the CODE/TEST ``Verifies:`` path.
    """
    project = tmp_path / "project"
    (project / "spec").mkdir(parents=True)
    (project / "spec" / "prd.md").write_text(_SPEC, encoding="utf-8")

    (project / "tests").mkdir(parents=True)
    (project / "tests" / "test_widget.py").write_text(
        f"# Verifies: {ref}\ndef test_widget():\n    assert True\n",
        encoding="utf-8",
    )

    if journey_ref is not None:
        (project / "spec" / "journeys.md").write_text(
            _JOURNEY_TEMPLATE.format(ref=journey_ref),
            encoding="utf-8",
        )

    (project / ".elspais.toml").write_text(
        _CONFIG_TEMPLATE.format(sep=sep, multi=multi),
        encoding="utf-8",
    )
    return project


# Shared matrix of (separator, multi_separator, ref, expected assertion
# labels) reused by the CODE/TEST ``Verifies:`` test below and the journey
# ``Validates:`` tests further down.
_SEPARATOR_COMBINATIONS = [
    ("-", "+", "REQ-p-widget-A+C", ["A", "C"]),
    ("/", "+", "REQ-p-widget/A+C", ["A", "C"]),  # currently drops suffix
    ("/", "/", "REQ-p-widget/A/C", ["A", "C"]),
    (":", "+", "REQ-p-widget:A+C", ["A", "C"]),
    ("-", ",", "REQ-p-widget-A,C", ["A", "C"]),
]


@pytest.mark.parametrize("sep,multi,ref,expected_labels", _SEPARATOR_COMBINATIONS)
def test_separator_combinations_parse_targeted_refs(sep, multi, ref, expected_labels, tmp_path):
    """A `Verifies:` ref using the *configured* separator/multi-separator
    must produce VERIFIES edges carrying exactly the referenced assertion
    labels -- never an empty (blanket) assertion_targets list."""
    from elspais.graph.factory import build_graph

    project = _make_project(tmp_path, sep, multi, ref)
    graph = build_graph(
        config_path=project / ".elspais.toml",
        repo_root=project,
        scan_code=False,
    )

    widget = graph.find_by_id("REQ-p-widget")
    assert widget is not None, "REQ-p-widget should be in the graph"

    test_nodes = list(graph.iter_by_kind(NodeKind.TEST))
    assert len(test_nodes) == 1, f"Expected exactly one TEST node, got {len(test_nodes)}"
    test_node = test_nodes[0]

    all_targets: list[str] = []
    for edge in widget.iter_outgoing_edges():
        if edge.target.id == test_node.id:
            all_targets.extend(edge.assertion_targets)

    assert all_targets, (
        f"Expected VERIFIES edge(s) from REQ-p-widget to the test with "
        f"non-empty assertion_targets for ref {ref!r} (sep={sep!r}, "
        f"multi={multi!r}); got a blanket edge with empty assertion_targets "
        f"instead (the assertion suffix was dropped during extraction)."
    )
    assert sorted(all_targets) == sorted(
        expected_labels
    ), f"Expected assertion_targets {expected_labels}, got {sorted(all_targets)}"


# Verifies: REQ-d00082-E
@pytest.mark.parametrize("sep,multi,ref,expected_labels", _SEPARATOR_COMBINATIONS)
def test_journey_validates_across_separator_combinations(
    sep, multi, ref, expected_labels, tmp_path
):
    """A `Validates:` ref using the *configured* separator/multi-separator must
    produce assertion-targeted VALIDATES edges (REQ -> journey, per the
    ``Validates:`` field behavior specified in spec/requirements-spec.md)
    carrying exactly the referenced assertion labels, with
    ``rollup_metrics.uat_coverage.direct_labels`` matching.

    Note (multi=","): ``JourneyParser`` splits a ``Validates:`` line on a
    literal "," to support multiple whole-journey targets on one line
    (pre-existing since CUR-1082, unrelated to CUR-1568's separator config
    bug). That split runs before assertion-multi-separator expansion, so a
    "," *multi_separator* collides with the journey's own list syntax: only
    the first label survives as a targeted edge and the rest is left as a
    broken reference. This is pinned below rather than papered over.
    """
    from elspais.graph.factory import build_graph

    project = _make_project(tmp_path, sep, multi, ref, journey_ref=ref)
    graph = build_graph(
        config_path=project / ".elspais.toml",
        repo_root=project,
        scan_code=False,
    )

    widget = graph.find_by_id("REQ-p-widget")
    assert widget is not None, "REQ-p-widget should be in the graph"

    jny = graph.find_by_id("JNY-T-01")
    assert jny is not None, "JNY-T-01 should be in the graph"

    validates_targets: list[str] = []
    for edge in widget.iter_outgoing_edges():
        if edge.kind == EdgeKind.VALIDATES and edge.target.id == jny.id:
            validates_targets.extend(edge.assertion_targets)

    rollup = widget.get_metric("rollup_metrics")

    if multi == ",":
        assert sorted(validates_targets) == ["A"], (
            f"Expected only the first label ('A') to survive the "
            f"pre-existing comma-list collision, got {sorted(validates_targets)}"
        )
        assert rollup.uat_coverage.direct_labels == {"A"}
        journey_broken = [br for br in graph.broken_references() if br.source_id == jny.id]
        assert any(
            br.target_id == "C" for br in journey_broken
        ), f"Expected 'C' to remain a broken reference from {jny.id}, got {journey_broken}"
    else:
        assert sorted(validates_targets) == sorted(expected_labels), (
            f"Expected VALIDATES assertion_targets {expected_labels} for ref "
            f"{ref!r} (sep={sep!r}, multi={multi!r}), got {sorted(validates_targets)}"
        )
        assert rollup.uat_coverage.direct_labels == set(expected_labels)


# Verifies: REQ-d00082-E, REQ-d00252-G
def test_journey_dash_style_ref_under_slash_config_is_hard_broken(tmp_path):
    """A journey `Validates:` ref that still uses "-" when the project is
    configured with a "/" separator must remain a hard broken reference
    naming the journey as source, NOT be presumed foreign (no associates are
    configured -- REQ-d00252-G guard 1), and carry the separator-config
    diagnostic (REQ-d00252-G guard 2)."""
    from elspais.graph.factory import build_graph

    sep, multi = "/", "+"
    correctly_styled_ref = "REQ-p-widget/A+C"
    dash_style_ref = "REQ-p-widget-A+C"

    project = _make_project(tmp_path, sep, multi, correctly_styled_ref, journey_ref=dash_style_ref)
    graph = build_graph(
        config_path=project / ".elspais.toml",
        repo_root=project,
        scan_code=False,
    )

    jny = graph.find_by_id("JNY-T-01")
    assert jny is not None, "JNY-T-01 should be in the graph"

    journey_broken = [br for br in graph.broken_references() if br.source_id == jny.id]
    assert (
        len(journey_broken) == 1
    ), f"Expected exactly one broken ref from {jny.id}, got {journey_broken}"
    br = journey_broken[0]

    assert br.target_id == dash_style_ref
    assert br.edge_kind == "validates"
    assert br.presumed_foreign is False, (
        "No associates are configured, so the generic presumed-foreign guard "
        "(REQ-d00252-G guard 1) must leave this a hard broken reference."
    )
    assert (
        "[id-patterns.assertions] separator/multi_separator" in br.diagnostic
    ), f"Expected a separator-config diagnostic (REQ-d00252-G guard 2), got {br.diagnostic!r}"
