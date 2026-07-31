# Verifies: REQ-p00004-J
"""Tests that _engine's daemon-reuse path never silently serves stale config.

REQ-p00004-J: the tool SHALL re-read configuration from disk when reloading
the graph. A running daemon whose config_hash no longer matches the on-disk
config must be restarted (clean) or served with an explicit warning and
``config_stale`` source marker (unsaved mutations present).
"""

import os
from pathlib import Path
from unittest.mock import patch

from elspais import __version__


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


def _run_try_daemon(tmp_path, info, try_port_fn):
    """Drive _try_daemon with a mocked daemon environment."""
    from elspais.commands._engine import _try_daemon

    stopped = []

    def mock_stop(repo_root):
        stopped.append(repo_root)
        return True

    started = []

    def mock_ensure(repo_root, ttl_minutes=None):
        started.append(repo_root)
        return 54321

    with (
        patch("elspais.config.find_git_root", return_value=tmp_path),
        patch("elspais.commands._daemon_client._get_daemon_port", return_value=info["port"]),
        patch("elspais.commands._daemon_client._try_port", side_effect=try_port_fn),
        patch("elspais.mcp.daemon.get_daemon_info", return_value=info),
        patch("elspais.mcp.daemon.stop_daemon", side_effect=mock_stop),
        patch("elspais.mcp.daemon.ensure_daemon", side_effect=mock_ensure),
    ):
        result = _try_daemon("/api/run/checks", {})

    return result, stopped, started


def test_stale_config_clean_daemon_restarts(tmp_path: Path):
    """Config edited + no unsaved mutations: daemon restarted, not reused."""
    _make_project(tmp_path)
    info = _daemon_info(config_hash="stale_hash_value_")

    calls = []

    def try_port(port, endpoint, params, method):
        calls.append((port, endpoint))
        if endpoint == "/api/dirty":
            return {"dirty": False}
        return {"healthy": True}

    result, stopped, started = _run_try_daemon(tmp_path, info, try_port)

    assert stopped == [tmp_path], "stale daemon must be stopped"
    assert started == [tmp_path], "a fresh daemon must be started"
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

    def try_port(port, endpoint, params, method):
        if endpoint == "/api/dirty":
            return {"dirty": True, "mutation_count": 2}
        return {"healthy": True}

    result, stopped, started = _run_try_daemon(tmp_path, info, try_port)

    assert stopped == []
    assert started == []
    assert result is not None
    payload, source = result
    assert payload == {"healthy": True}
    assert source["config_stale"] is True
    err = capsys.readouterr().err
    assert "Warning" in err
    assert "configuration" in err


def test_fresh_config_daemon_reused_without_restart(tmp_path: Path):
    """Matching config hash: daemon reused, no dirty probe, no restart."""
    config_path = _make_project(tmp_path)

    from elspais.mcp.daemon import compute_config_hash

    info = _daemon_info(config_hash=compute_config_hash(config_path))

    calls = []

    def try_port(port, endpoint, params, method):
        calls.append(endpoint)
        return {"healthy": True}

    result, stopped, started = _run_try_daemon(tmp_path, info, try_port)

    assert stopped == []
    assert started == []
    assert result is not None
    payload, source = result
    assert payload == {"healthy": True}
    assert source["port"] == 12345
    assert "config_stale" not in source
    assert "/api/dirty" not in calls
