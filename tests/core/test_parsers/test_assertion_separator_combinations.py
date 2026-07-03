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
"""

from __future__ import annotations

from pathlib import Path

import pytest

from elspais.graph.GraphNode import NodeKind

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
"""


def _make_project(tmp_path: Path, sep: str, multi: str, ref: str) -> Path:
    """Build a minimal on-disk project: one REQ with assertions A/B/C and
    one test file with a single ``# Verifies: <ref>`` comment."""
    project = tmp_path / "project"
    (project / "spec").mkdir(parents=True)
    (project / "spec" / "prd.md").write_text(_SPEC, encoding="utf-8")

    (project / "tests").mkdir(parents=True)
    (project / "tests" / "test_widget.py").write_text(
        f"# Verifies: {ref}\ndef test_widget():\n    assert True\n",
        encoding="utf-8",
    )

    (project / ".elspais.toml").write_text(
        _CONFIG_TEMPLATE.format(sep=sep, multi=multi),
        encoding="utf-8",
    )
    return project


@pytest.mark.parametrize(
    "sep,multi,ref,expected_labels",
    [
        ("-", "+", "REQ-p-widget-A+C", ["A", "C"]),
        ("/", "+", "REQ-p-widget/A+C", ["A", "C"]),  # currently drops suffix
        ("/", "/", "REQ-p-widget/A/C", ["A", "C"]),
        (":", "+", "REQ-p-widget:A+C", ["A", "C"]),
        ("-", ",", "REQ-p-widget-A,C", ["A", "C"]),
    ],
)
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
