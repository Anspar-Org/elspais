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

from pathlib import Path

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
version = 3

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
results = "results-a/results.xml"
match = "source"

[[scanning.test.targets]]
name = "b"
reporter = "junit"
results = "results-b/results.xml"
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


def _make_project(tmp_path: Path) -> Path:
    """Build an on-disk project with two targets ('a' fresh, 'b' carried).

    - REQ-d00001-A is verified only by target 'a' (test_a, passing).
    - REQ-d00002-A is verified only by target 'b' (test_b, passing).
    - REQ-d00003-A is verified only by target 'b' (test_c, FAILING) -- used to
      confirm carried-ness doesn't change verdict/tier.
    """
    project = tmp_path / "project"
    (project / "spec").mkdir(parents=True)
    (project / "spec" / "reqs.md").write_text(_SPEC, encoding="utf-8")

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

    (project / "results-a").mkdir(parents=True)
    (project / "results-a" / "results.xml").write_text(_RESULTS_A, encoding="utf-8")
    (project / "results-b").mkdir(parents=True)
    (project / "results-b" / "results.xml").write_text(_RESULTS_B, encoding="utf-8")

    (project / ".elspais.toml").write_text(_CONFIG, encoding="utf-8")
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

    assert metrics_a.verified.tier == "full"
    assert metrics_a.verified.carried is False

    assert metrics_b.verified.tier == "full"
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

    assert metrics_c.verified.tier == "failing"
    assert metrics_c.verified.carried is True


# Verifies: REQ-d00254-I
def test_verified_dimension_carried_defaults_false_without_fresh_targets(tmp_path):
    """Absent --targets selector (fresh_targets=None): nothing is carried,
    so verified.carried is False for every requirement."""
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
