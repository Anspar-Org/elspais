# Verifies: REQ-d00010

"""Tests that _engine.call injects graph_source metadata."""

from unittest.mock import patch

import pytest


def test_engine_call_local_includes_graph_source():
    """Local fallback should tag result with graph_source='local'."""
    from elspais.commands._engine import call
    from elspais.commands._requests import ChecksRequest

    def fake_compute(graph, config, request):
        return {"healthy": True, "checks": []}

    with patch(
        "elspais.commands._engine._ensure_local_graph",
        return_value=(object(), {}),
    ):
        result = call("/api/run/checks", ChecksRequest(), fake_compute, skip_daemon=True)

    assert "graph_source" in result
    assert result["graph_source"]["type"] == "local"


def test_engine_call_daemon_includes_graph_source():
    """Daemon path should tag result with graph_source including port."""
    from elspais.commands._engine import call
    from elspais.commands._requests import ChecksRequest

    daemon_result = {"healthy": True, "checks": []}

    with patch(
        "elspais.commands._engine._try_daemon",
        return_value=(daemon_result, {"type": "daemon", "port": 35121}),
    ):
        result = call("/api/run/checks", ChecksRequest(), lambda g, c, r: {}, skip_daemon=False)

    assert "graph_source" in result
    assert result["graph_source"]["type"] == "daemon"
    assert result["graph_source"]["port"] == 35121


def test_engine_call_viewer_includes_graph_source():
    """Viewer path should tag result with graph_source type='viewer'."""
    from elspais.commands._engine import call
    from elspais.commands._requests import ChecksRequest

    viewer_result = {"healthy": True, "checks": []}

    # Viewer now goes through daemon.json like everything else —
    # the type comes from daemon.json "type" field
    with patch(
        "elspais.commands._engine._try_daemon",
        return_value=(viewer_result, {"type": "viewer", "port": 5001}),
    ):
        result = call("/api/run/checks", ChecksRequest(), lambda g, c, r: {}, skip_daemon=False)

    assert result["graph_source"]["type"] == "viewer"


# Verifies: REQ-d00313-C
def test_a_daemon_answer_from_a_graph_behind_the_disk_says_so(capsys):
    """The files the serving graph predates move into graph_source, where the
    answer's own content is untouched, and the reader is told on stderr."""
    from elspais.commands._engine import call
    from elspais.commands._requests import ChecksRequest

    daemon_result = {
        "healthy": True,
        "checks": [],
        "graph_predates": ["spec/prd.md", ".results/unit/junit.xml"],
    }

    with patch(
        "elspais.commands._engine._try_daemon",
        return_value=(daemon_result, {"type": "daemon", "port": 35121}),
    ):
        result = call("/api/run/checks", ChecksRequest(), lambda g, c, r: {}, skip_daemon=False)

    assert "graph_predates" not in result
    assert result["graph_source"]["graph_predates"] == [
        "spec/prd.md",
        ".results/unit/junit.xml",
    ]
    err = capsys.readouterr().err
    assert "spec/prd.md" in err
    assert ".results/unit/junit.xml" in err


# Verifies: REQ-d00313-C
def test_a_daemon_answer_from_a_current_graph_discloses_nothing(capsys):
    from elspais.commands._engine import call
    from elspais.commands._requests import ChecksRequest

    with patch(
        "elspais.commands._engine._try_daemon",
        return_value=({"healthy": True, "checks": []}, {"type": "daemon", "port": 35121}),
    ):
        result = call("/api/run/checks", ChecksRequest(), lambda g, c, r: {}, skip_daemon=False)

    assert "graph_predates" not in result["graph_source"]
    assert capsys.readouterr().err == ""


# Verifies: REQ-d00313-C
@pytest.mark.parametrize(
    "predates,shown",
    [(["spec/prd.md", "spec/ops.md"], True), ([], False)],
    ids=["graph-behind", "graph-current"],
)
def test_the_reports_source_line_counts_the_files_the_graph_predates(predates, shown):
    from elspais.commands.health import _format_graph_source

    line = _format_graph_source({"type": "daemon", "port": 35121, "graph_predates": predates})

    assert ("graph predates 2 changed file(s)" in line) is shown


_PROJECT_CONFIG = """\
version = 5
cli_ttl = 0

[project]
name = "{name}"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]
"""

_PROJECT_SPEC = """\
# {req_id}: {title}

**Level**: PRD | **Status**: Active

The body of the requirement.

## Assertions

A. The system SHALL do something.

*End* *{title}* | **Hash**: abcd1234
"""


def _make_project(root, name, req_id, title):
    root.mkdir()
    (root / ".elspais.toml").write_text(_PROJECT_CONFIG.format(name=name))
    (root / "spec").mkdir()
    (root / "spec" / "requirements.md").write_text(_PROJECT_SPEC.format(req_id=req_id, title=title))
    return root


# Verifies: REQ-o00075-C
def test_the_local_graph_is_kept_only_for_the_directory_it_was_built_from(tmp_path, monkeypatch):
    """A process asking from a second project is answered from that project's
    graph, never from the graph cached for the first."""
    from elspais.commands import _engine

    project_a = _make_project(tmp_path / "a", "project-a", "REQ-p00001", "Project A")
    project_b = _make_project(tmp_path / "b", "project-b", "REQ-p00002", "Project B")
    monkeypatch.setattr(_engine, "_local_graph", None)
    monkeypatch.setattr(_engine, "_local_config", None)
    monkeypatch.setattr(_engine, "_local_dir", None)

    monkeypatch.chdir(project_a)
    graph_a, _ = _engine._ensure_local_graph()
    assert graph_a.find_by_id("REQ-p00001") is not None

    monkeypatch.chdir(project_b)
    graph_b, _ = _engine._ensure_local_graph()

    assert graph_b.find_by_id("REQ-p00002") is not None
    assert graph_b.find_by_id("REQ-p00001") is None

    again, _ = _engine._ensure_local_graph()
    assert again is graph_b
