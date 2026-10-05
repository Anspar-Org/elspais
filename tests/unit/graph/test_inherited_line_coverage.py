"""Line coverage of a requirement read from either end of a federation.

A platform repository owns a requirement, the code implementing it, and an
LCOV run measuring that code. A sponsor repository names the platform as an
associate. Which of the two the federation is assembled from must not change
what the platform requirement's line coverage reads.
"""

from __future__ import annotations

import csv
import io

import pytest

from elspais.commands._requests import TraceRequest
from elspais.commands.trace import render_trace
from elspais.graph.factory import build_graph
from elspais.graph.held_config import held_config
from tests.federation_repos import _git, make_repo

PLAT_TOML = """version = 5

[project]
name = "plat"
namespace = "PLAT"

[scanning.spec]
directories = ["spec"]

[scanning.code]
directories = ["src"]

[scanning.test]
enabled = true
directories = ["tests"]

[[scanning.test.targets]]
name = "unit"
reporter = "lcov"
coverage = "lcov.info"
credit_coverage = "tested"
"""

SPON_TOML = """version = 5

[project]
name = "spon"
namespace = "SPON"

[scanning.spec]
directories = ["spec"]

[associates.plat]
path = "../plat"
namespace = "PLAT"
"""

PLAT_SPEC = """# PLAT-p00001: Platform thing

**Level**: PRD | **Status**: Active | **Implements**: -

The platform.

## Assertions

A. The platform SHALL do the thing.

*End* *Platform thing* | **Hash**: ________
"""

SPON_SPEC = """# SPON-p00001: Sponsor thing

**Level**: PRD | **Status**: Active | **Implements**: PLAT-p00001

The sponsor.

## Assertions

A. The sponsor SHALL do the thing.

*End* *Sponsor thing* | **Hash**: ________
"""

PLAT_CODE = """# Implements: PLAT-p00001-A
def thing():
    x = 1
    y = 2
    return x + y
"""

# Two of the function's three executable lines ran.
PLAT_LCOV = """SF:src/thing.py
DA:3,1
DA:4,1
DA:5,0
end_of_record
"""


@pytest.fixture(scope="module")
def roots(tmp_path_factory):
    """A platform repo carrying measured code, and a sponsor naming it."""
    base = tmp_path_factory.mktemp("inherited")
    plat = make_repo(base, "plat", namespace="PLAT", config_text=PLAT_TOML)
    (plat / "spec" / "reqs.md").write_text(PLAT_SPEC, encoding="utf-8")
    (plat / "src").mkdir()
    (plat / "src" / "thing.py").write_text(PLAT_CODE, encoding="utf-8")
    (plat / ".results" / "unit").mkdir(parents=True)
    (plat / ".results" / "unit" / "lcov.info").write_text(PLAT_LCOV, encoding="utf-8")
    _git(plat, "add", "-A")
    _git(plat, "commit", "-m", "code")

    spon = make_repo(base, "spon", namespace="SPON", config_text=SPON_TOML)
    (spon / "spec" / "reqs.md").write_text(SPON_SPEC, encoding="utf-8")
    _git(spon, "add", "-A")
    _git(spon, "commit", "-m", "spec")
    return {"platform": plat, "sponsor": spon}


@pytest.fixture(scope="module")
def graphs(roots):
    return {name: build_graph(repo_root=root) for name, root in roots.items()}


def _line_figures(graph):
    metrics = graph.find_by_id("PLAT-p00001").get_metric("rollup_metrics")
    line = metrics.code_tested
    lcov = metrics.lcov_tested
    return {
        "code_tested": (line.has_measurement, line.covered_lines, line.total_lines),
        "lcov_tested": (lcov.covered, lcov.total_by_label),
    }


def _trace_row(graph):
    out = render_trace(
        graph,
        held_config(graph),
        TraceRequest(values=("id", "code_tested", "lcov_tested")),
        "csv",
    )
    rows = {row["ID"]: row for row in csv.DictReader(io.StringIO(out))}
    return rows["PLAT-p00001"]


# Verifies: REQ-d00269-A
def test_platform_line_coverage_is_measured_from_either_root(graphs):
    """The platform requirement's line coverage is a real measurement --
    two of three lines -- whichever repository the federation is built from."""
    for name, graph in graphs.items():
        line = graph.find_by_id("PLAT-p00001").get_metric("rollup_metrics").code_tested
        assert line.has_measurement, name
        assert (line.covered_lines, line.total_lines) == (2, 3), name


# Verifies: REQ-d00269-A
def test_platform_line_coverage_does_not_depend_on_the_root(graphs):
    """The metrics read from the sponsor root equal those read from the
    platform root, for both line-coverage-derived values."""
    from_platform = _line_figures(graphs["platform"])
    assert from_platform["code_tested"] == (True, 2, 3)
    # LCOV credit is proportional to the lines covered: two of three.
    assert from_platform["lcov_tested"] == (
        pytest.approx(2 / 3),
        {"A": pytest.approx(2 / 3)},
    )
    assert _line_figures(graphs["sponsor"]) == from_platform


# Verifies: REQ-d00269-A
def test_trace_row_for_platform_requirement_is_the_same_from_either_root(graphs):
    """The trace report states the same line-coverage cells for the inherited
    row as for the platform's own row, and both cells are measured."""
    from_platform = _trace_row(graphs["platform"])
    from_sponsor = _trace_row(graphs["sponsor"])
    assert from_platform["Code Tested"].startswith("2/3")
    assert from_platform["LCOV Tested"] not in ("", "n/a")
    assert from_sponsor == from_platform
