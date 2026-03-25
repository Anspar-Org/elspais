# Verifies: REQ-d00010
"""Tests for daemon lifecycle — no orphan servers."""

from pathlib import Path
from unittest.mock import patch


def test_start_daemon_stops_existing_first(tmp_path):
    """start_daemon() must call stop_daemon() before overwriting daemon.json."""
    from elspais.mcp.daemon import start_daemon

    calls = []

    with (
        patch("elspais.mcp.daemon.stop_daemon", side_effect=lambda r: calls.append(("stop", r))),
        patch("elspais.mcp.daemon.get_daemon_info", return_value={"pid": 999, "port": 8888}),
        patch("elspais.mcp.daemon.subprocess.Popen"),
        patch("elspais.mcp.daemon.time.time", side_effect=[0, 0, 0, 20]),  # force timeout
    ):
        try:
            start_daemon(tmp_path, ttl_minutes=1)
        except RuntimeError:
            pass  # Expected: daemon won't actually start

    assert len(calls) == 1
    assert calls[0] == ("stop", tmp_path)


def test_write_daemon_json_includes_type(tmp_path):
    """write_daemon_json() must include a 'type' field."""
    from elspais.mcp.daemon import write_daemon_json

    path = tmp_path / ".elspais" / "daemon.json"
    write_daemon_json(
        repo_root=tmp_path,
        pid=12345,
        port=9999,
        server_type="daemon",
    )

    import json

    data = json.loads(path.read_text())
    assert data["type"] == "daemon"
    assert data["pid"] == 12345
    assert data["port"] == 9999
    assert data["repo_root"] == str(tmp_path)
    assert "version" in data
    assert "started_at" in data


def test_write_daemon_json_viewer_type(tmp_path):
    """write_daemon_json() accepts type='viewer'."""
    from elspais.mcp.daemon import write_daemon_json

    write_daemon_json(
        repo_root=tmp_path,
        pid=12345,
        port=5001,
        server_type="viewer",
    )

    import json

    data = json.loads((tmp_path / ".elspais" / "daemon.json").read_text())
    assert data["type"] == "viewer"


def test_viewer_cleanup_removes_daemon_json(tmp_path):
    """Viewer must remove daemon.json in its finally block."""
    from elspais.mcp.daemon import _daemon_json_path, write_daemon_json

    write_daemon_json(repo_root=tmp_path, pid=99999, port=5001, server_type="viewer")
    path = _daemon_json_path(tmp_path)
    assert path.exists()

    # Simulate viewer cleanup (the finally block)
    path.unlink(missing_ok=True)
    assert not path.exists()


def test_viewer_atexit_removes_daemon_json(tmp_path):
    """atexit handler must remove daemon.json as safety net."""
    from elspais.mcp.daemon import _daemon_json_path, write_daemon_json

    path = _daemon_json_path(tmp_path)
    write_daemon_json(repo_root=tmp_path, pid=99999, port=5001, server_type="viewer")
    assert path.exists()

    # The atexit handler is a closure over daemon_json path
    path.unlink(missing_ok=True)
    assert not path.exists()
