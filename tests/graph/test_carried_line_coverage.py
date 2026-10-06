"""Line coverage the current tree did not produce is carried.

A test target's line coverage is measured by the same run as its results, so
it is judged by the same fingerprint verdict: coverage written by a recorded
run of the tree is fresh, coverage with no fingerprint (or whose inputs changed
after the run) is stale. Every figure built only from stale coverage is marked
carried, and a report of it says why the coverage is stale.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from elspais.graph.GraphNode import NodeKind
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
"""

_CONFIG = """\
version = 5

[project]
name = "carried-lines"
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

[scanning.code]
directories = ["src"]

[scanning.test]
enabled = true
directories = ["tests"]
file_patterns = ["test_*.py"]

[[scanning.test.targets]]
name = "a"
reporter = "junit"
results = "results.xml"
match = "source"
coverage = "lcov.info"
credit_coverage = "tested"

[rules.hierarchy]
allow_circular = false
allow_structural_orphans = true

[rules.format]
require_hash = false
require_assertions = false
require_status = false
"""

_CODE = """\
# Implements: REQ-d00001-A
def thing():
    x = 1
    y = 2
    return x + y
"""

# Two of the function's three executable lines ran.
_LCOV = """\
SF:src/main.py
DA:3,1
DA:4,1
DA:5,0
end_of_record
"""

_RESULTS = """\
<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="suite-a" tests="1">
  <testcase name="test_thing" classname="tests.test_main" time="0.01"/>
</testsuite>
"""

_TEST = "# Verifies: REQ-d00001-A\ndef test_thing():\n    pass\n"

_NO_FINGERPRINT = "no fingerprint was recorded for its results"

STATES = ["fresh", "no-fingerprint", "input-changed"]

# A second target 'b' measuring a second file implementing the same assertion.
_TARGET_B = """
[[scanning.test.targets]]
name = "b"
reporter = "junit"
results = "results.xml"
match = "source"
coverage = "lcov.info"
credit_coverage = "tested"
"""

_LCOV_B = _LCOV.replace("src/main.py", "src/other.py")

_RESULTS_B = _RESULTS.replace("test_thing", "test_other").replace("test_main", "test_other")

_TEST_B = _TEST.replace("test_thing", "test_other")


def _make_project(tmp_path: Path, state: str) -> Path:
    """A project whose one target 'a' holds results and line coverage of src/main.py.

    The coverage is judged by its target's results (REQ-d00323-I), so the
    target reports results as well as coverage.

    ``fresh``: the coverage is written by a recorded run of the tree.
    ``no-fingerprint``: it is written with no Result Fingerprint.
    ``input-changed``: it is recorded, then an input of the run changes.
    ``mixed``: a second target 'b' measures src/other.py, which implements
    the same assertion; 'a' is recorded and 'b' has no fingerprint, so the
    requirement's lines come partly from fresh and partly from stale coverage.
    """
    project = tmp_path / "project"
    (project / "spec").mkdir(parents=True)
    (project / "spec" / "reqs.md").write_text(_SPEC, encoding="utf-8")
    (project / "src").mkdir()
    (project / "src" / "main.py").write_text(_CODE, encoding="utf-8")
    (project / "tests").mkdir()
    (project / "tests" / "test_main.py").write_text(_TEST, encoding="utf-8")
    config = _CONFIG
    if state == "mixed":
        (project / "src" / "other.py").write_text(_CODE, encoding="utf-8")
        (project / "tests" / "test_other.py").write_text(_TEST_B, encoding="utf-8")
        config = config.replace("\n[rules.hierarchy]", _TARGET_B + "\n[rules.hierarchy]")
    (project / ".elspais.toml").write_text(config, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)

    if state == "mixed":
        record_run(project, "a", {"results.xml": _RESULTS, "lcov.info": _LCOV})
        (project / ".results" / "b").mkdir(parents=True)
        (project / ".results" / "b" / "results.xml").write_text(_RESULTS_B, encoding="utf-8")
        (project / ".results" / "b" / "lcov.info").write_text(_LCOV_B, encoding="utf-8")
    elif state == "no-fingerprint":
        (project / ".results" / "a").mkdir(parents=True)
        (project / ".results" / "a" / "results.xml").write_text(_RESULTS, encoding="utf-8")
        (project / ".results" / "a" / "lcov.info").write_text(_LCOV, encoding="utf-8")
    else:
        record_run(project, "a", {"results.xml": _RESULTS, "lcov.info": _LCOV})
    if state == "input-changed":
        with (project / "spec" / "reqs.md").open("a", encoding="utf-8") as fh:
            fh.write("\nChanged after the run.\n")
    return project


def _build(project: Path):
    from elspais.graph.factory import build_graph

    return build_graph(config_path=project / ".elspais.toml", repo_root=project)


def _assert_reason(reason: str, state: str) -> None:
    """The stated reason is the fingerprint verdict for *state*."""
    if state == "no-fingerprint":
        assert reason == _NO_FINGERPRINT
    else:
        assert reason.startswith("inputs changed since it ran:")
        assert "spec/reqs.md" in reason


@pytest.fixture(params=STATES)
def built(request, tmp_path):
    """``(state, project, graph)`` for each freshness of the coverage."""
    project = _make_project(tmp_path, request.param)
    return request.param, project, _build(project)


def _main_file(graph):
    return next(
        f
        for f in graph.iter_by_kind(NodeKind.FILE)
        if f.get_field("relative_path") == "src/main.py"
    )


# Verifies: REQ-d00323-I
def test_a_file_s_line_coverage_records_why_it_is_stale(built) -> None:
    """The FILE node carries the target's stale reason, or "" where fresh."""
    state, _, graph = built

    main = _main_file(graph)

    assert main.get_field("line_coverage")
    reason = main.get_field("line_coverage_stale_reason")
    if state == "fresh":
        assert reason == ""
    else:
        _assert_reason(reason, state)


# Verifies: REQ-d00323-I
def test_captured_output_is_not_judged_stale(tmp_path: Path) -> None:
    """A target whose output this invocation captured is its own run.

    Its coverage on disk carries no fingerprint, and is still read as fresh.
    """
    from elspais.graph.factory import build_graph

    project = _make_project(tmp_path, "no-fingerprint")
    graph = build_graph(
        config_path=project / ".elspais.toml",
        repo_root=project,
        captured_results={"a": _RESULTS},
    )

    main = _main_file(graph)
    assert main.get_field("line_coverage")
    assert main.get_field("line_coverage_stale_reason") == ""


# Verifies: REQ-d00323-I+J+K
def test_a_requirement_s_line_figures_are_carried_when_its_coverage_is_stale(built) -> None:
    state, _, graph = built
    stale = state != "fresh"

    metrics = graph.find_by_id("REQ-d00001").get_metric("rollup_metrics")

    assert metrics.code_tested.has_measurement
    assert (metrics.code_tested.covered_lines, metrics.code_tested.total_lines) == (2, 3)
    assert metrics.code_tested.carried is stale
    if stale:
        _assert_reason(metrics.code_tested.stale_reason, state)
    else:
        assert metrics.code_tested.stale_reason == ""
    # The Assertion credit taken from the same lines is carried with them.
    assert metrics.lcov_tested.covered == pytest.approx(2 / 3)
    assert metrics.lcov_tested.carried is stale


def _trace_row(graph) -> tuple[str, dict[str, str]]:
    """The markdown trace and the line cells of REQ-d00001's row."""
    from elspais.commands._requests import TraceRequest
    from elspais.commands.trace import render_trace
    from elspais.graph.held_config import held_config

    out = render_trace(
        graph,
        held_config(graph),
        TraceRequest(values=("id", "code_tested", "lcov_tested")),
        "markdown",
    )
    lines = out.splitlines()
    header = next(line for line in lines if line.startswith("| ID"))
    names = [h.strip() for h in header.strip("|").split("|")]
    row = next(line for line in lines if line.startswith("| REQ-d00001 "))
    cells = [c.strip() for c in row.strip("|").split("|")]
    return out, dict(zip(names, cells, strict=True))


# Verifies: REQ-d00323-J
def test_trace_marks_line_figures_from_stale_coverage_as_baseline(built) -> None:
    state, _, graph = built
    stale = state != "fresh"

    out, row = _trace_row(graph)

    assert row["Code Tested"].startswith("2/3")
    assert row["Code Tested"].endswith("(baseline)") is stale
    assert row["LCOV Tested"] not in ("", "n/a")
    assert row["LCOV Tested"].endswith("(baseline)") is stale
    assert ("results or line coverage the current tree did not produce (stale)" in out) is stale


_FOOTNOTE = "* line coverage from a run the current tree did not produce (stale)"


# Verifies: REQ-d00323-J
@pytest.mark.parametrize("fmt", ["text", "markdown"])
def test_summary_marks_a_line_figure_from_stale_coverage(built, fmt: str) -> None:
    from elspais.commands._requests import SummaryRequest
    from elspais.commands.summary import compute_summary, render_summary
    from elspais.graph.held_config import held_config

    state, _, graph = built
    stale = state != "fresh"
    config = held_config(graph)

    data = compute_summary(graph, config, SummaryRequest(values=("level", "code_tested")))
    out = render_summary(data, fmt, config)

    (row,) = [lv for lv in data["levels"] if lv.get("code_tested_measured")]
    assert row["code_tested_carried"] is stale
    figure = "2/3 (66.7%)"
    assert figure in out
    assert (f"{figure}*" in out) is stale
    assert (_FOOTNOTE in out) is stale


# Verifies: REQ-d00323-J+K
def test_the_line_coverage_check_says_why_its_coverage_is_stale(built) -> None:
    from elspais.commands.health import check_line_coverage
    from elspais.graph.held_config import held_config

    state, _, graph = built
    stale = state != "fresh"

    check = check_line_coverage(graph, held_config(graph))

    assert check.details["carried"] is stale
    if stale:
        reason = check.details["stale_reason"]
        _assert_reason(reason, state)
        assert (
            f"all from stale line coverage the current tree did not produce ({reason})"
            in check.message
        )
    else:
        assert "stale_reason" not in check.details
        assert "stale" not in check.message


# Verifies: REQ-d00323-K
def test_line_coverage_credit_says_why_its_coverage_is_stale(built) -> None:
    from elspais.commands.health import check_dimension_coverage
    from elspais.graph.held_config import held_config

    state, _, graph = built

    check = check_dimension_coverage(graph, "lcov_tested", config=held_config(graph))

    assert "1/1 REQs covered" in check.message
    if state == "fresh":
        assert "stale" not in check.message
    else:
        prefix = "credited from stale line coverage ("
        assert prefix in check.message
        reason = check.message.split(prefix, 1)[1]
        _assert_reason(reason[: reason.index(")")], state)


# Verifies: REQ-d00323-J+K
def test_figures_with_fresh_and_stale_coverage_are_not_carried_and_say_why(
    tmp_path: Path,
) -> None:
    """Only a figure EVERY contributing coverage of which is carried is marked.

    One fresh measurement keeps the figure unmarked, and the report still
    states why the stale part is stale.
    """
    from elspais.commands._requests import SummaryRequest
    from elspais.commands.health import check_line_coverage
    from elspais.commands.summary import compute_summary, render_summary
    from elspais.graph.held_config import held_config

    graph = _build(_make_project(tmp_path, "mixed"))
    config = held_config(graph)

    files = {
        f.get_field("relative_path"): f.get_field("line_coverage_stale_reason")
        for f in graph.iter_by_kind(NodeKind.FILE)
        if f.get_field("line_coverage")
    }
    assert files == {"src/main.py": "", "src/other.py": _NO_FINGERPRINT}

    metrics = graph.find_by_id("REQ-d00001").get_metric("rollup_metrics")
    assert (metrics.code_tested.covered_lines, metrics.code_tested.total_lines) == (4, 6)
    assert metrics.code_tested.carried is False
    assert metrics.code_tested.stale_reason == _NO_FINGERPRINT
    assert metrics.lcov_tested.covered > 0
    assert metrics.lcov_tested.carried is False

    out, row = _trace_row(graph)
    assert row["Code Tested"].startswith("4/6")
    assert "(baseline)" not in row["Code Tested"]
    assert "(baseline)" not in row["LCOV Tested"]
    assert "line coverage the current tree did not produce" not in out

    data = compute_summary(graph, config, SummaryRequest(values=("level", "code_tested")))
    (level,) = [lv for lv in data["levels"] if lv.get("code_tested_measured")]
    assert level["code_tested_carried"] is False
    text = render_summary(data, "text", config)
    assert "4/6 (66.7%)" in text
    assert "4/6 (66.7%)*" not in text
    assert _FOOTNOTE not in text

    check = check_line_coverage(graph, config)
    assert check.details["carried"] is False
    assert check.details["stale_reason"] == _NO_FINGERPRINT
    assert (
        f"some from stale line coverage the current tree did not produce ({_NO_FINGERPRINT})"
        in check.message
    )


# Verifies: REQ-d00323-I
@pytest.mark.parametrize("recorded", [True, False], ids=["fingerprinted", "no-fingerprint"])
def test_a_coverage_only_target_is_judged_like_any_other(tmp_path: Path, recorded: bool) -> None:
    """A target declaring coverage and no results still has its run judged.

    Its coverage is fresh when a recorded run of the tree wrote it, and stale
    when no fingerprint was recorded.
    """
    project = tmp_path / "project"
    (project / "spec").mkdir(parents=True)
    (project / "spec" / "reqs.md").write_text(_SPEC, encoding="utf-8")
    (project / "src").mkdir()
    (project / "src" / "main.py").write_text(_CODE, encoding="utf-8")
    (project / "tests").mkdir()
    config = _CONFIG.replace('reporter = "junit"\nresults = "results.xml"\nmatch = "source"\n', "")
    assert "results =" not in config
    (project / ".elspais.toml").write_text(config, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    if recorded:
        record_run(project, "a", {"lcov.info": _LCOV})
    else:
        (project / ".results" / "a").mkdir(parents=True)
        (project / ".results" / "a" / "lcov.info").write_text(_LCOV, encoding="utf-8")

    graph = _build(project)

    main = _main_file(graph)
    assert main.get_field("line_coverage")
    expected = "" if recorded else _NO_FINGERPRINT
    assert main.get_field("line_coverage_stale_reason") == expected
    code_tested = graph.find_by_id("REQ-d00001").get_metric("rollup_metrics").code_tested
    assert code_tested.has_measurement
    assert code_tested.carried is not recorded
    assert code_tested.stale_reason == expected
