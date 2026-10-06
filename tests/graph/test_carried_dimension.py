# Verifies: REQ-d00254-I
"""Tests for `CoverageDimension.carried` propagation on the `verified` dimension.

Task 3 (RESULT.carried tagging) marks each RESULT node as carried (baseline,
not freshly run) or fresh based on `build_graph(fresh_targets=...)`. This
module verifies that the annotator rolls that provenance up into
`RollupMetrics.verified.carried`: True only when every verified signal for a
requirement came from a carried RESULT, False as soon as any signal is fresh.
Freshness is orthogonal to verdict -- a carried failing result still yields
`tier == "failing"`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from elspais.graph.aggregation import absolute_tier
from tests.core.graph_test_helpers import record_run

_SPEC = """\
# Requirements

---

### REQ-d00001: Req A

The system SHALL do A.

## Assertions

A. The system SHALL do A.

*End* *Req A*
---

### REQ-d00002: Req B

The system SHALL do B.

## Assertions

A. The system SHALL do B.

*End* *Req B*
---

### REQ-d00003: Req C

The system SHALL do C.

## Assertions

A. The system SHALL do C.

*End* *Req C*
---
"""

_CONFIG = """\
version = 5

[project]
name = "carried-dim"
namespace = "REQ"

[levels.dev]
rank = 1
letter = "d"
implements = ["dev"]

[id-patterns]
canonical = "{namespace}-{level.letter}{component}"

[id-patterns.component]
style = "numeric"
digits = 5
leading_zeros = true

[scanning.spec]
directories = ["spec"]

[scanning.test]
enabled = true
directories = ["tests"]
file_patterns = ["test_*.py"]

[[scanning.test.targets]]
name = "a"
reporter = "junit"
results = "results.xml"
match = "source"

[[scanning.test.targets]]
name = "b"
reporter = "junit"
results = "results.xml"
match = "source"

[rules.hierarchy]
allow_circular = false
allow_structural_orphans = true

[rules.format]
require_hash = false
require_assertions = false
require_status = false
"""

_RESULTS_A = """\
<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="suite-a" tests="1">
  <testcase name="test_a" classname="tests.test_a" time="0.01"/>
</testsuite>
"""

_RESULTS_B = """\
<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="suite-b" tests="2">
  <testcase name="test_b" classname="tests.test_b" time="0.01"/>
  <testcase name="test_c" classname="tests.test_c" time="0.01">
    <failure message="assertion failed">boom</failure>
  </testcase>
</testsuite>
"""


_PARENT = """
### REQ-d00010: Parent

The system SHALL do P.

## Assertions

A. The system SHALL do P.

*End* *Parent*
---
"""

_RESULTS_PARENT_IN_B = """\
<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="suite-b" tests="3">
  <testcase name="test_b" classname="tests.test_b" time="0.01"/>
  <testcase name="test_c" classname="tests.test_c" time="0.01">
    <failure message="assertion failed">boom</failure>
  </testcase>
  <testcase name="test_p" classname="tests.test_p" time="0.01"/>
</testsuite>
"""


def _make_project(
    tmp_path: Path,
    *,
    refiner: str | None = None,
    parent_own_result: bool = False,
    unrecorded: frozenset[str] = frozenset(),
) -> Path:
    """Build an on-disk project with two targets, 'a' and 'b'.

    - REQ-d00001-A is verified only by target 'a' (test_a, passing).
    - REQ-d00002-A is verified only by target 'b' (test_b, passing).
    - REQ-d00003-A is verified only by target 'b' (test_c, FAILING) -- used to
      confirm carried-ness doesn't change verdict/tier.

    With ``refiner``, that requirement declares ``Refines: REQ-d00010-A`` and
    the parent REQ-d00010 is added, so the parent is credited through the
    refiner's results. With ``parent_own_result``, the parent also carries a
    passing test of its own in target 'b' (test_p).

    Each target's results are written as a recorded run of the tree, so they
    are fresh, except for a target named in ``unrecorded``: its results are
    written with no Result Fingerprint, so they are stale.
    """
    project = tmp_path / "project"
    (project / "spec").mkdir(parents=True)
    spec = _SPEC
    if refiner is not None:
        heading = next(line for line in spec.splitlines() if line.startswith(f"### {refiner}:"))
        spec = spec.replace(heading, f"{heading}\n\n**Refines**: REQ-d00010-A", 1) + _PARENT
    (project / "spec" / "reqs.md").write_text(spec, encoding="utf-8")

    (project / "tests").mkdir(parents=True)
    (project / "tests" / "test_a.py").write_text(
        "# Verifies: REQ-d00001-A\ndef test_a():\n    pass\n", encoding="utf-8"
    )
    (project / "tests" / "test_b.py").write_text(
        "# Verifies: REQ-d00002-A\ndef test_b():\n    pass\n", encoding="utf-8"
    )
    (project / "tests" / "test_c.py").write_text(
        "# Verifies: REQ-d00003-A\ndef test_c():\n    pass\n", encoding="utf-8"
    )

    if parent_own_result:
        (project / "tests" / "test_p.py").write_text(
            "# Verifies: REQ-d00010-A\ndef test_p():\n    pass\n", encoding="utf-8"
        )

    (project / ".elspais.toml").write_text(_CONFIG, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    results = {
        "a": _RESULTS_A,
        "b": _RESULTS_PARENT_IN_B if parent_own_result else _RESULTS_B,
    }
    for target, text in results.items():
        if target in unrecorded:
            (project / ".results" / target).mkdir(parents=True)
            (project / ".results" / target / "results.xml").write_text(text, encoding="utf-8")
        else:
            record_run(project, target, {"results.xml": text})
    return project


# Verifies: REQ-d00254-I
def test_verified_dimension_carried_flag(tmp_path):
    """REQ covered only by a carried target -> verified.carried True;
    covered only by a fresh target -> verified.carried False."""
    from elspais.graph.factory import build_graph

    project = _make_project(tmp_path)
    graph = build_graph(
        config_path=project / ".elspais.toml",
        repo_root=project,
        fresh_targets={"a"},
    )

    req_a = graph.find_by_id("REQ-d00001")
    req_b = graph.find_by_id("REQ-d00002")

    metrics_a = req_a.get_metric("rollup_metrics")
    metrics_b = req_b.get_metric("rollup_metrics")

    assert absolute_tier(metrics_a.verified, measure="total") == "full"
    assert metrics_a.verified.carried is False

    assert absolute_tier(metrics_b.verified, measure="total") == "full"
    assert metrics_b.verified.carried is True


# Verifies: REQ-d00254-I
def test_carried_failing_result_still_reports_failing_tier(tmp_path):
    """Carried is purely provenance: a carried FAILING result must still
    gate as tier=='failing', and is also reported as carried=True."""
    from elspais.graph.factory import build_graph

    project = _make_project(tmp_path)
    graph = build_graph(
        config_path=project / ".elspais.toml",
        repo_root=project,
        fresh_targets={"a"},
    )

    req_c = graph.find_by_id("REQ-d00003")
    metrics_c = req_c.get_metric("rollup_metrics")

    assert absolute_tier(metrics_c.verified, measure="total") == "failing"
    assert metrics_c.verified.carried is True


# Verifies: REQ-d00254-I
def test_verified_dimension_carried_defaults_false_without_fresh_targets(tmp_path):
    """Absent --targets selector (fresh_targets=None), results this tree
    produced are not carried, so verified.carried is False for every
    requirement."""
    from elspais.graph.factory import build_graph

    project = _make_project(tmp_path)
    graph = build_graph(
        config_path=project / ".elspais.toml",
        repo_root=project,
    )

    req_a = graph.find_by_id("REQ-d00001")
    req_b = graph.find_by_id("REQ-d00002")

    assert req_a.get_metric("rollup_metrics").verified.carried is False
    assert req_b.get_metric("rollup_metrics").verified.carried is False


def _build(project: Path, fresh_targets: set[str] | None):
    from elspais.graph.factory import build_graph

    return build_graph(
        config_path=project / ".elspais.toml",
        repo_root=project,
        fresh_targets=fresh_targets,
    )


# Verifies: REQ-d00323-A+C
@pytest.mark.parametrize(
    "fresh_targets",
    [
        pytest.param(set(), id="no-target-fresh"),
        pytest.param({"a"}, id="refiner-target-not-named"),
    ],
)
def test_a_parent_credited_only_through_a_carried_refiner_is_carried(
    tmp_path: Path, fresh_targets: set[str]
) -> None:
    """REQ-d00002 (target 'b') refines the parent, which has no results of its
    own; the conducted credit brings the refiner's carried provenance with it."""
    project = _make_project(tmp_path, refiner="REQ-d00002")

    verified = _build(project, fresh_targets).find_by_id("REQ-d00010")
    verified = verified.get_metric("rollup_metrics").verified

    assert verified.rolled_direct_by_label.get("A", 0.0) > 0
    assert not verified.immediate_direct_by_label
    assert verified.carried is True


# Verifies: REQ-d00323-B+C
@pytest.mark.parametrize(
    "fresh_targets",
    [
        pytest.param({"b"}, id="refiner-target-alone"),
        pytest.param({"a", "b"}, id="every-target"),
    ],
)
def test_a_parent_credited_through_a_fresh_refiner_is_not_carried(
    tmp_path: Path, fresh_targets: set[str]
) -> None:
    """The refiner's target ran fresh, so the conducted figure is fresh."""
    project = _make_project(tmp_path, refiner="REQ-d00002")

    verified = _build(project, fresh_targets).find_by_id("REQ-d00010")
    verified = verified.get_metric("rollup_metrics").verified

    assert verified.rolled_direct_by_label.get("A", 0.0) > 0
    assert verified.carried is False


# Verifies: REQ-d00323-A+B+C
@pytest.mark.parametrize(
    ("fresh_targets", "carried"),
    [
        # Own result (b) carried, refiner (a) fresh: one fresh vote is enough.
        pytest.param({"a"}, False, id="own-carried-refiner-fresh"),
        # Own result (b) fresh, refiner (a) carried.
        pytest.param({"b"}, False, id="own-fresh-refiner-carried"),
        # Both carried: every contribution is old evidence.
        pytest.param(set(), True, id="both-carried"),
    ],
)
def test_a_parent_with_its_own_result_and_a_refiner_is_carried_only_when_both_are(
    tmp_path: Path, fresh_targets: set[str], carried: bool
) -> None:
    """The parent's own result and the conducted one both vote."""
    project = _make_project(tmp_path, refiner="REQ-d00001", parent_own_result=True)

    verified = _build(project, fresh_targets).find_by_id("REQ-d00010")
    verified = verified.get_metric("rollup_metrics").verified

    assert verified.immediate_direct_by_label.get("A", 0.0) > 0
    assert verified.rolled_direct_by_label.get("A", 0.0) > 0
    assert verified.carried is carried


# Verifies: REQ-d00323-B+C
def test_no_parent_is_carried_without_a_fresh_target_selection(tmp_path: Path) -> None:
    """With no selection, results this tree produced are not carried,
    conducted credit included."""
    project = _make_project(tmp_path, refiner="REQ-d00002")

    verified = _build(project, None).find_by_id("REQ-d00010")
    verified = verified.get_metric("rollup_metrics").verified

    assert verified.rolled_direct_by_label.get("A", 0.0) > 0
    assert verified.carried is False


def _passing_cell(markdown: str, req_id: str) -> str:
    """The 'Passing' cell of the trace row for *req_id*."""
    lines = markdown.splitlines()
    header = next(line for line in lines if line.startswith("| ID"))
    column = [h.strip() for h in header.strip("|").split("|")].index("Passing")
    row = next(line for line in lines if line.startswith(f"| {req_id} "))
    return [c.strip() for c in row.strip("|").split("|")][column]


# Verifies: REQ-d00323-A+B+C
@pytest.mark.parametrize(
    ("targets", "marked"),
    [
        pytest.param(["none"], True, id="targets-none"),
        pytest.param(["b"], False, id="refiner-target-fresh"),
    ],
)
def test_trace_marks_a_parent_credited_by_carried_refiner_results_as_baseline(
    tmp_path: Path, monkeypatch, capsys, targets: list[str], marked: bool
) -> None:
    """`trace --targets none` shows the conducted figure with `(baseline)`."""
    import argparse

    from elspais.commands import trace

    project = _make_project(tmp_path, refiner="REQ-d00002")
    monkeypatch.chdir(project)
    args = argparse.Namespace(
        targets=targets,
        format="markdown",
        config=project / ".elspais.toml",
        spec_dir=None,
        preset=None,
        body=False,
        show_assertions=False,
        show_tests=False,
        dimension="",
        output=None,
    )

    trace.run(args)

    cell = _passing_cell(capsys.readouterr().out, "REQ-d00010")
    assert cell.startswith("1/1 (100%)")
    assert ("(baseline)" in cell) is marked


_NO_FINGERPRINT = "no fingerprint was recorded for its results"


def _results_by_target(graph) -> dict[str, set[tuple[bool, str]]]:
    """Each target's RESULT nodes as ``{target: {(carried, stale_reason)}}``."""
    from elspais.graph.GraphNode import NodeKind

    found: dict[str, set[tuple[bool, str]]] = {}
    for node in graph.iter_by_kind(NodeKind.RESULT):
        found.setdefault(node.get_field("target"), set()).add(
            (bool(node.get_field("carried")), node.get_field("stale_reason"))
        )
    return found


def _stale_project(tmp_path: Path, how: str) -> Path:
    """A project whose target 'b' holds stale results, made stale *how*."""
    if how == "no-fingerprint":
        return _make_project(tmp_path, unrecorded=frozenset({"b"}))
    project = _make_project(tmp_path)
    with (project / "tests" / "test_b.py").open("a", encoding="utf-8") as fh:
        fh.write("# changed after the run\n")
    return project


# Verifies: REQ-d00323-F
@pytest.mark.parametrize("fresh_targets", [None, {"a", "b"}], ids=["no-selection", "every-target"])
def test_results_a_run_of_this_tree_produced_are_not_carried(
    tmp_path: Path, fresh_targets: set[str] | None
) -> None:
    graph = _build(_make_project(tmp_path), fresh_targets)

    assert _results_by_target(graph) == {"a": {(False, "")}, "b": {(False, "")}}


# Verifies: REQ-d00323-F
@pytest.mark.parametrize("fresh_targets", [None, {"a", "b"}], ids=["no-selection", "every-target"])
@pytest.mark.parametrize("how", ["no-fingerprint", "input-changed"])
def test_results_the_current_tree_did_not_produce_are_carried_whatever_was_selected(
    tmp_path: Path, how: str, fresh_targets: set[str] | None
) -> None:
    """Staleness carries a target's results even where the run names it fresh."""
    graph = _build(_stale_project(tmp_path, how), fresh_targets)

    results = _results_by_target(graph)
    reasons = {reason for _, reason in results["b"]}
    assert {carried for carried, _ in results["b"]} == {True}
    (reason,) = reasons
    if how == "no-fingerprint":
        assert reason == _NO_FINGERPRINT
        # Target 'a' was recorded and nothing changed since: it stays fresh.
        assert results["a"] == {(False, "")}
    else:
        assert reason.startswith("inputs changed since it ran:")
        assert "tests/test_b.py" in reason
    verified = graph.find_by_id("REQ-d00002").get_metric("rollup_metrics").verified
    assert verified.carried is True


# Verifies: REQ-d00323-F
def test_trace_marks_stale_results_as_baseline_on_a_run_that_selected_nothing(
    tmp_path: Path,
) -> None:
    from elspais.commands.trace import format_markdown

    graph = _build(_make_project(tmp_path, unrecorded=frozenset({"b"})), None)
    out = "\n".join(format_markdown(graph))

    assert "(baseline)" in _passing_cell(out, "REQ-d00002")
    assert "(baseline)" not in _passing_cell(out, "REQ-d00001")
    assert "> Legend:" in out
    assert "results the current tree did not produce (stale)" in out


# Verifies: REQ-d00323-F
def test_output_this_invocation_captured_is_not_judged_stale(tmp_path: Path) -> None:
    """A target whose output was captured is its own run, whatever the disk holds.

    Target 'b' has results on disk with no fingerprint, which would be stale
    if read from there; its captured output is read instead.
    """
    from elspais.graph.factory import build_graph

    project = _make_project(tmp_path, unrecorded=frozenset({"b"}))
    graph = build_graph(
        config_path=project / ".elspais.toml",
        repo_root=project,
        captured_results={"b": _RESULTS_B},
    )

    assert _results_by_target(graph)["b"] == {(False, "")}


def _health_inputs(tmp_path: Path, stale: bool):
    from elspais.config import get_config

    project = _make_project(tmp_path, unrecorded=frozenset({"b"}) if stale else frozenset())
    return _build(project, None), get_config(project / ".elspais.toml")


# Verifies: REQ-d00323-G
@pytest.mark.parametrize("stale", [True, False], ids=["stale", "fresh"])
def test_a_failure_from_stale_results_fails_and_says_why(tmp_path: Path, stale: bool) -> None:
    """A stale failure still fails at its severity, and names the reason."""
    from elspais.commands.health import check_test_results

    graph, config = _health_inputs(tmp_path, stale)

    check = check_test_results(graph, config)

    assert check.passed is False
    assert check.severity == "warning"
    (finding,) = [f for f in check.findings if "test_c" in f.message]
    if stale:
        assert f"(stale results: {_NO_FINGERPRINT})" in finding.message
        assert "1 of the failures are from stale results" in check.message
        assert check.details["stale_failed"] == 1
    else:
        assert "stale" not in finding.message
        assert "stale" not in check.message
        assert check.details["stale_failed"] == 0


# Verifies: REQ-d00323-G
@pytest.mark.parametrize("stale", [True, False], ids=["stale", "fresh"])
def test_the_passing_dimension_says_its_failures_include_stale_results(
    tmp_path: Path, stale: bool
) -> None:
    from elspais.commands.health import check_dimension_coverage

    graph, config = _health_inputs(tmp_path, stale)

    check = check_dimension_coverage(graph, "verified", config=config)

    assert "FAILURES DETECTED" in check.message
    assert ("stale results the current tree did not produce" in check.message) is stale
