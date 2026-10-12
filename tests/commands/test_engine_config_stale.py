# Verifies: REQ-p00004-J, REQ-o00076-I+J
"""Tests that _engine's daemon-reuse path never silently serves stale config.

REQ-p00004-J: the tool SHALL re-read configuration from disk when reloading
the graph. A running daemon whose config_hash no longer matches the on-disk
config must be restarted (clean) or served with an explicit warning and
``config_stale`` source marker (unsaved mutations present).

Whether the daemon differs from the client at all is asked here through the
one authority in ``mcp/daemon.py`` (REQ-o00076-I), and a difference that is
served rather than resolved has to be said out loud (REQ-o00076-J).
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from elspais import __version__
from elspais.graph.parsers import parse_cache


@pytest.fixture(autouse=True)
def _parse_cache_on(monkeypatch):
    """Every test here asks about a client in the default parse-cache mode.

    A client asking for another mode never reaches a daemon (see the last
    test), so the variable the tier itself runs under must not decide these.
    """
    monkeypatch.delenv(parse_cache.ENV_VAR, raising=False)


def _make_project(tmp_path: Path) -> Path:
    config_path = tmp_path / ".elspais.toml"
    config_path.write_text('[project]\nname = "test"\n')
    return config_path


def _daemon_info(config_hash: str, port: int = 12345) -> dict:
    return {
        "pid": os.getpid(),
        "port": port,
        "repo_root": "unused",
        "started_at": "2026-01-01T00:00:00",
        "version": __version__,
        "config_hash": config_hash,
    }


def _run_try_daemon(tmp_path, info, try_port_fn, mutation_count=0):
    """Drive _try_daemon with a mocked daemon environment.

    The unsaved-work probe is a live HTTP call in ``mcp/daemon.py``, so it
    is stubbed at the function that makes it rather than at the transport;
    ``daemon_has_unsaved_work`` and the policy it feeds still run for real.
    """
    from elspais.commands._engine import _try_daemon

    stopped = []

    def mock_stop(repo_root):
        stopped.append(repo_root)
        return True

    started = []
    # Starting a daemon writes a fresh record, so what the record names
    # moves with the start; the stub moves it the same way.
    current = {"info": info}

    def mock_ensure(repo_root, ttl_minutes=None):
        started.append(repo_root)
        current["info"] = _daemon_info(config_hash="fresh", port=54321)
        return 54321

    probes = []

    def mock_count(daemon_info):
        probes.append(daemon_info)
        return mutation_count

    with (
        patch("elspais.config.find_git_root", return_value=tmp_path),
        patch("elspais.commands._daemon_client._try_server", side_effect=try_port_fn),
        patch("elspais.mcp.daemon.get_daemon_info", side_effect=lambda _root: current["info"]),
        patch("elspais.mcp.daemon.get_daemon_mutation_count", side_effect=mock_count),
        patch("elspais.mcp.daemon.stop_daemon", side_effect=mock_stop),
        patch("elspais.mcp.daemon.ensure_daemon", side_effect=mock_ensure),
    ):
        result = _try_daemon("/api/run/checks", {})

    return result, stopped, started, probes


def test_stale_config_clean_daemon_restarts(tmp_path: Path):
    """Config edited + no unsaved mutations: daemon restarted, not reused."""
    _make_project(tmp_path)
    info = _daemon_info(config_hash="stale_hash_value_")

    calls = []

    def try_port(record, endpoint, params, method):
        calls.append((record["port"], endpoint))
        return {"healthy": True}

    result, stopped, started, probes = _run_try_daemon(tmp_path, info, try_port, mutation_count=0)

    assert stopped == [tmp_path], "stale daemon must be stopped"
    assert started == [tmp_path], "a fresh daemon must be started"
    assert probes, "the restart decision must consult the unsaved-work probe"
    assert result is not None
    payload, source = result
    assert payload == {"healthy": True}
    # Served from the fresh daemon, not the stale one
    assert source["port"] == 54321
    assert "config_stale" not in source
    # The stale daemon was never asked to serve the actual endpoint
    assert (12345, "/api/run/checks") not in calls


def test_stale_config_dirty_daemon_warns_and_serves(tmp_path: Path, capsys):
    """Config edited + unsaved mutations: serve stale daemon but say so."""
    _make_project(tmp_path)
    info = _daemon_info(config_hash="stale_hash_value_")

    def try_port(record, endpoint, params, method):
        return {"healthy": True}

    result, stopped, started, _ = _run_try_daemon(tmp_path, info, try_port, mutation_count=2)

    assert stopped == []
    assert started == []
    assert result is not None
    payload, source = result
    assert payload == {"healthy": True}
    assert source["port"] == 12345
    assert source["config_stale"] is True
    err = capsys.readouterr().err
    assert "warning" in err.lower()
    assert "configuration" in err
    assert "unsaved" in err


def test_fresh_config_daemon_reused_without_restart(tmp_path: Path):
    """Matching config hash: daemon reused, no dirty probe, no restart."""
    config_path = _make_project(tmp_path)

    from elspais.mcp.daemon import compute_config_hash

    info = _daemon_info(config_hash=compute_config_hash(config_path))

    def try_port(record, endpoint, params, method):
        return {"healthy": True}

    result, stopped, started, probes = _run_try_daemon(tmp_path, info, try_port)

    assert stopped == []
    assert started == []
    assert result is not None
    payload, source = result
    assert payload == {"healthy": True}
    assert source["port"] == 12345
    assert "config_stale" not in source
    # Nothing differs, so the daemon is never asked whether it holds work.
    assert probes == []


# Verifies: REQ-d00331-E+F
@pytest.mark.parametrize("requested", ["0", "verify", "bogus"])
def test_a_client_asking_for_another_parse_cache_mode_is_not_served_by_a_daemon(
    tmp_path: Path, monkeypatch, requested
):
    """A serving process reads ELSPAIS_PARSE_CACHE from its own environment.

    A client that sets another mode -- or one naming no mode -- is answered by
    a local build reading the client's own setting: a running daemon is not
    asked, and none is started to keep that mode for later clients.
    """
    config_path = _make_project(tmp_path)

    from elspais.mcp.daemon import compute_config_hash

    info = _daemon_info(config_hash=compute_config_hash(config_path))
    asked = []

    def try_port(record, endpoint, params, method):
        asked.append(record["port"])
        return {"healthy": True}

    monkeypatch.setenv(parse_cache.ENV_VAR, requested)
    result, stopped, started, probes = _run_try_daemon(tmp_path, info, try_port)

    assert result is None
    assert asked == []
    assert started == []
    assert stopped == []
