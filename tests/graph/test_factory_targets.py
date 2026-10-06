# Verifies: REQ-d00254-I
"""Tests for fresh-target threading in build_graph() and RESULT.carried tagging.

Verifies that build_graph(fresh_targets=...) tags each RESULT node with
`carried` (True when its target is NOT in the fresh set) and `target`
(the owning [[scanning.test.targets]] name), and stashes the fresh set on
the returned FederatedGraph as `render_fresh_targets` for the renderer.
"""

from pathlib import Path

from elspais.graph.GraphNode import NodeKind
from tests.core.graph_test_helpers import record_run

_SPEC = """\
### REQ-p00001: Test Req

**Level**: PRD | **Status**: Active

The system SHALL do something testable.

*End* *Test Req* | **Hash**: ________
"""

_JUNIT_TEMPLATE = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="tests" tests="1" failures="0">
    <testcase classname="tests.test_thing" name="test_{name}" time="0.01"/>
  </testsuite>
</testsuites>
"""


def _make_two_target_project(tmp_path: Path) -> Path:
    """Build an on-disk project with two [[scanning.test.targets]] entries.

    Each target ("a", "b") has its own results directory with a single
    passing JUnit XML file, recorded as a run of the tree, so build_graph()
    ingests two fresh RESULT nodes, one per target.
    """
    project = tmp_path / "project"
    (project / "spec").mkdir(parents=True)
    (project / "spec" / "reqs.md").write_text(_SPEC, encoding="utf-8")

    (project / ".elspais.toml").write_text(
        """\
version = 5

[project]
name = "two-target"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[scanning.test]
enabled = true

[[scanning.test.targets]]
name = "a"
reporter = "junit"
results = "TEST-*.xml"
match = "aggregate"

[[scanning.test.targets]]
name = "b"
reporter = "junit"
results = "TEST-*.xml"
match = "aggregate"
""",
        encoding="utf-8",
    )
    # Each target's results come from a run of this tree, so they are fresh.
    record_run(project, "a", {"TEST-a.xml": _JUNIT_TEMPLATE.format(name="a")})
    record_run(project, "b", {"TEST-b.xml": _JUNIT_TEMPLATE.format(name="b")})
    return project


# Verifies: REQ-d00254-I
def test_result_nodes_tagged_carried(tmp_path):
    from elspais.graph.factory import build_graph

    project = _make_two_target_project(tmp_path)
    graph = build_graph(
        config_path=project / ".elspais.toml",
        repo_root=project,
        scan_code=False,
        fresh_targets={"a"},
    )

    carried_by_target = {
        r.get_field("target"): r.get_field("carried") for r in graph.iter_by_kind(NodeKind.RESULT)
    }
    assert carried_by_target == {"a": False, "b": True}
    assert graph.render_fresh_targets == {"a"}


# Verifies: REQ-d00254-I
def test_result_nodes_not_carried_when_no_fresh_targets(tmp_path):
    """Absent --targets selector, results this tree produced are not carried."""
    from elspais.graph.factory import build_graph

    project = _make_two_target_project(tmp_path)
    graph = build_graph(
        config_path=project / ".elspais.toml",
        repo_root=project,
        scan_code=False,
    )

    carried_by_target = {
        r.get_field("target"): r.get_field("carried") for r in graph.iter_by_kind(NodeKind.RESULT)
    }
    assert carried_by_target == {"a": False, "b": False}
    assert graph.render_fresh_targets is None
