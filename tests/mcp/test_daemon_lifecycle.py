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
