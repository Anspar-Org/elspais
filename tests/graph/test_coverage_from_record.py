"""The build reads a target's line coverage from its coverage record alone.

A finished run reads the test tool's coverage file once and keeps it in the
target's coverage record. The graph build, its faults and the served graph's
watch then answer from the record; the tool's own file is an input of the
run, not of the build.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from elspais.graph.GraphNode import NodeKind
from tests.coverage_helpers import finish_coverage_area

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
name = "coverage-record"
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
coverage = "lcov.info"
coverage_format = "lcov"

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

_LCOV = """\
SF:src/main.py
DA:3,1
DA:4,1
DA:5,0
end_of_record
"""

_OLDER_RUN = {
    "commit": "0123456789abcdef0123",
    "root": "/elsewhere/checkout",
    "started_at": "2026-01-01T00:00:00Z",
}


def _project(tmp_path: Path) -> Path:
    """A repository with one coverage target 'a' and two code files."""
    project = tmp_path / "project"
    (project / "spec").mkdir(parents=True)
    (project / "spec" / "reqs.md").write_text(_SPEC, encoding="utf-8")
    (project / "src").mkdir()
    (project / "src" / "main.py").write_text(_CODE, encoding="utf-8")
    (project / "src" / "other.py").write_text(_CODE, encoding="utf-8")
    (project / "tests").mkdir()
    (project / ".elspais.toml").write_text(_CONFIG, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    return project


def _config(project: Path) -> dict:
    from elspais.config import load_config

    return load_config(project / ".elspais.toml")


def _area(project: Path) -> Path:
    return project / ".results" / "a"


def _write_tool_coverage(project: Path, text: str = _LCOV) -> Path:
    """Write the tool's coverage file into the area, as the test tool does."""
    path = _area(project) / "lcov.info"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _recorded_run(project: Path, carried=None) -> None:
    """One recorded run of 'a' measuring src/main.py, so the target judges fresh."""
    from elspais.utilities.fingerprint import finish_run, start_run

    config = _config(project)
    start_run(project, config, "a")
    _write_tool_coverage(project)
    finish_run(project, config, "a", carried_coverage=carried)


def _build(project: Path, **kwargs):
    from elspais.graph.factory import build_graph

    return build_graph(config_path=project / ".elspais.toml", repo_root=project, **kwargs)


def _file(graph, rel: str):
    return next(f for f in graph.iter_by_kind(NodeKind.FILE) if f.get_field("relative_path") == rel)


# Verifies: REQ-d00334-A
def test_the_build_reads_line_coverage_from_the_record_alone(tmp_path: Path) -> None:
    """Coverage recorded from the tool's file survives the file's removal."""
    project = _project(tmp_path)
    tool_file = _write_tool_coverage(project)
    finish_coverage_area(project, _config(project), "a")
    tool_file.unlink()

    graph = _build(project)

    assert _file(graph, "src/main.py").get_field("line_coverage") == {3: 1, 4: 1, 5: 0}


# Verifies: REQ-d00334-A
def test_an_area_with_a_tool_file_and_no_record_is_a_fault(tmp_path: Path) -> None:
    """The build does not read the tool's file; the area's missing record is reported."""
    project = _project(tmp_path)
    _write_tool_coverage(project)

    graph = _build(project)

    faults = [f for f in graph.ingestion_faults() if f.target == "a"]
    assert len(faults) == 1
    assert "run the target again" in faults[0].cause
    assert not _file(graph, "src/main.py").get_field("line_coverage")


# Verifies: REQ-d00254-F
def test_hit_counts_reach_the_graph_unreduced(tmp_path: Path) -> None:
    project = _project(tmp_path)
    tool_file = _write_tool_coverage(project, "SF:src/main.py\nDA:3,7\nend_of_record\n")
    finish_coverage_area(project, _config(project), "a")
    tool_file.unlink()

    graph = _build(project)

    assert _file(graph, "src/main.py").get_field("line_coverage") == {3: 7}


# Verifies: REQ-d00323-Q
@pytest.mark.parametrize(
    ("fresh_targets", "fresh"),
    [({"other"}, False), (None, True)],
    ids=["not-executed", "executed"],
)
def test_coverage_of_a_target_the_run_did_not_execute_is_carried(
    tmp_path: Path, fresh_targets, fresh: bool
) -> None:
    project = _project(tmp_path)
    _recorded_run(project)

    graph = _build(project, fresh_targets=fresh_targets)

    main = _file(graph, "src/main.py")
    assert main.get_field("line_coverage")
    assert main.get_field("line_coverage_fresh") is fresh
    if fresh:
        assert main.get_field("line_coverage_stale_reason") == ""
    else:
        assert main.get_field("line_coverage_stale_reason")


# Verifies: REQ-d00333-L
def test_coverage_carried_from_an_earlier_run_names_that_run(tmp_path: Path) -> None:
    """An entry the latest run did not measure is not fresh, and names its run."""
    from elspais.utilities.coverage import FileCoverage
    from elspais.utilities.fingerprint import describe_run, file_digest

    project = _project(tmp_path)
    carried = {
        "src/other.py": FileCoverage(
            hits={3: 1, 4: 1, 5: 0},
            executable=3,
            digest=file_digest(project / "src" / "other.py"),
            measured_in=(_OLDER_RUN,),
        )
    }
    _recorded_run(project, carried=carried)

    graph = _build(project)

    other = _file(graph, "src/other.py")
    assert other.get_field("line_coverage") == {3: 1, 4: 1, 5: 0}
    assert other.get_field("line_coverage_fresh") is False
    reason = other.get_field("line_coverage_stale_reason")
    assert "the run of" in reason
    assert describe_run(_OLDER_RUN) in reason
    # The file the latest run measured is its own.
    assert _file(graph, "src/main.py").get_field("line_coverage_fresh") is True


# Verifies: REQ-d00285-G
def test_a_diagnostic_in_the_record_is_an_ingestion_fault(tmp_path: Path) -> None:
    from elspais.utilities.coverage import write_record

    project = _project(tmp_path)
    write_record(
        _area(project),
        {},
        diagnostics=[
            {"path": ".results/a/lcov.info", "cause": "bad DA line", "line": 3, "partial": True}
        ],
    )

    graph = _build(project)

    faults = [f for f in graph.ingestion_faults() if f.stage == "coverage"]
    assert [(f.target, f.cause, f.line) for f in faults] == [("a", "bad DA line", 3)]


def _touched(path: Path) -> None:
    stat = path.stat()
    os.utime(path, (stat.st_atime + 100, stat.st_mtime + 100))


# Verifies: REQ-d00313-B
@pytest.mark.parametrize(
    ("name", "counts"),
    [(".elspais-coverage.json", True), ("lcov.info", False)],
    ids=["record", "tool-file"],
)
def test_the_watch_counts_the_record_and_not_the_tool_file(
    tmp_path: Path, name: str, counts: bool
) -> None:
    from elspais.server.watch import changed_files, snapshot, watch_set

    project = _project(tmp_path)
    _recorded_run(project)
    assert (_area(project) / ".elspais-coverage.json").is_file()
    watch = watch_set([(project, _config(project))])
    recorded = snapshot(watch)

    _touched(_area(project) / name)

    changed = [p.name for p in changed_files(watch, recorded)]
    assert (name in changed) is counts
    assert changed == ([name] if counts else [])
