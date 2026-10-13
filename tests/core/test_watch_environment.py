"""Tests for a served graph noticing a changed environment when a request asks for it."""

from __future__ import annotations

from pathlib import Path

import pytest

from elspais.server.watch import environment_changes, watch_set
from elspais.utilities.fingerprint import forget_probes, judge, probe_digests

_CONFIG = """\
version = 5

[project]
name = "env"
namespace = "REQ"

[scanning.test]
enabled = true

[[scanning.test.targets]]
name = "unit"
reporter = "junit"
results = "junit.xml"
environment_probes = [{ name = "tool", command = "printenv TOOL_VERSION" }]
"""


def _repo(tmp_path: Path) -> Path:
    """A repository holding one recorded run of its target, so a judgement probes."""
    from elspais.config import get_config
    from elspais.utilities.fingerprint import finish_run, start_run

    (tmp_path / ".elspais.toml").write_text(_CONFIG, encoding="utf-8")
    config = get_config(start_path=tmp_path)
    folder = start_run(tmp_path, config, "unit")
    (folder / "junit.xml").write_text('<testsuite name="s" tests="0"/>\n', encoding="utf-8")
    finish_run(tmp_path, config, "unit")
    forget_probes()
    return tmp_path


@pytest.fixture(autouse=True)
def _probes(monkeypatch):
    monkeypatch.setenv("TOOL_VERSION", "1")
    forget_probes()
    yield
    forget_probes()


def _members(root: Path):
    from elspais.config import get_config

    return [(root, get_config(start_path=root))]


# Verifies: REQ-d00311-R
def test_a_changed_probe_is_named_and_an_unchanged_one_is_not(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    members = _members(root)
    judge(root, members[0][1], "unit")
    recorded = probe_digests()
    watch = watch_set(members)

    assert environment_changes(watch, recorded) == ([], recorded)
    monkeypatch.setenv("TOOL_VERSION", "2")
    changes, measured = environment_changes(watch, recorded)
    assert changes == ["target unit: environment probe 'tool' changed"]
    assert measured != recorded


# Verifies: REQ-d00311-R
def test_the_watch_keys_each_probe_as_the_judgement_recorded_it(tmp_path):
    root = _repo(tmp_path)
    members = _members(root)
    judge(root, members[0][1], "unit")
    assert {w.probe.key for w in watch_set(members).probes} == set(probe_digests())


# Verifies: REQ-d00311-R
def test_a_probe_the_build_never_ran_is_not_watched(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    watch = watch_set(_members(root))
    monkeypatch.setenv("TOOL_VERSION", "2")
    assert environment_changes(watch, {}) == ([], {})


def _state(root: Path):
    from elspais.server.state import AppState

    return AppState.from_config(repo_root=root)


# Verifies: REQ-d00311-R
def test_a_changed_environment_rebuilds_with_the_digests_just_measured(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    state = _state(root)
    rebuilt: list = []
    monkeypatch.setattr(state, "_rebuild", lambda probes=None: rebuilt.append(probes))
    monkeypatch.setenv("TOOL_VERSION", "2")

    state._last_stale_check = 0
    assert state.ensure_fresh() is False, "a request that probes nothing rebuilds nothing"
    assert rebuilt == []

    probed = state.probe_environment()
    assert probed is not None
    assert state.ensure_fresh(probed) is True
    assert rebuilt == [probed[1]]


# Verifies: REQ-d00311-R
def test_the_environment_is_probed_at_most_once_per_minimum_age(tmp_path, monkeypatch):
    from elspais.server import state as state_module

    root = _repo(tmp_path)
    state = _state(root)
    assert state.probe_environment() is not None
    assert state.probe_environment() is None
    assert state.probe_environment(force=True) is not None, "a client asking for a fresh answer"
    monkeypatch.setattr(state_module, "PROBE_MIN_AGE", 0.0)
    assert state.probe_environment() is not None


# Verifies: REQ-d00311-R, REQ-d00313-C
def test_a_changed_environment_held_back_by_pending_work_is_disclosed_until_it_changes_back(
    tmp_path, monkeypatch
):
    from elspais.server import state as state_module
    from elspais.server.watch import graph_predates

    root = _repo(tmp_path)
    state = _state(root)
    monkeypatch.setattr(state_module, "PROBE_MIN_AGE", 0.0)
    monkeypatch.setattr(type(state.graph), "mutation_log", [object()], raising=False)
    monkeypatch.setenv("TOOL_VERSION", "2")

    assert state.ensure_fresh(state.probe_environment()) is False
    assert "target unit: environment probe 'tool' changed" in graph_predates(state.shared)

    monkeypatch.setenv("TOOL_VERSION", "1")
    assert state.ensure_fresh(state.probe_environment()) is False
    assert graph_predates(state.shared) == []


# Verifies: REQ-d00311-R
@pytest.mark.parametrize(
    ("method", "path", "probes"),
    [
        ("GET", "/api/run/checks", True),
        ("GET", "/api/export/checks", True),
        ("POST", "/mcp", True),
        ("GET", "/mcp", False),
        ("GET", "/api/dirty", False),
        ("GET", "/api/check-freshness", False),
        ("GET", "/api/search", False),
    ],
)
@pytest.mark.parametrize("prefix", ["", "/elspais"])
def test_only_a_request_whose_answer_depends_on_freshness_probes(method, path, probes, prefix):
    from starlette.requests import Request

    from elspais.server.middleware import AutoRefreshMiddleware

    middleware = AutoRefreshMiddleware(app=None, base_path=prefix)
    request = Request({"type": "http", "method": method, "path": prefix + path, "headers": []})
    assert middleware._asks_freshness(request) is probes


# Verifies: REQ-d00311-R
def test_a_rebuild_takes_the_digests_a_probe_just_measured_instead_of_probing_again(tmp_path):
    from elspais.mcp.shared_state import rebuild_shared_graph

    root = _repo(tmp_path)
    state = _state(root)
    (key,) = {w.probe.key for w in state._watch.probes}

    result = rebuild_shared_graph(state.shared, probes={key: "measured-just-now"})

    assert result["success"]
    assert probe_digests()[key] == "measured-just-now"
