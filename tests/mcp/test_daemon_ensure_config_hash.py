# tests/mcp/test_daemon_ensure_config_hash.py
# Verifies: REQ-d00010

"""Tests that ensure_daemon restarts on config_hash mismatch."""

import json
from pathlib import Path
from unittest.mock import patch

from elspais.mcp.daemon import _daemon_json_path


def test_ensure_daemon_restarts_on_config_hash_mismatch(tmp_path: Path):
    """ensure_daemon should restart when config hash has changed."""
    daemon_dir = tmp_path / ".elspais"
    daemon_dir.mkdir()
    daemon_json = daemon_dir / "daemon.json"

    import os

    daemon_json.write_text(
        json.dumps(
            {
                "pid": os.getpid(),  # current process (alive)
                "port": 12345,
                "repo_root": str(tmp_path),
                "started_at": "2026-01-01T00:00:00",
                "version": "0.111.53",
                "config_hash": "stale_hash_value_",
            }
        )
    )

    # Create a config file so compute_config_hash returns a real hash
    config_path = tmp_path / ".elspais.toml"
    config_path.write_text('[project]\nname = "test"\n')

    stopped = []
    started = []

    def mock_stop(repo_root):
        stopped.append(repo_root)
        daemon_json.unlink(missing_ok=True)
        return True

    def mock_start(repo_root, ttl_minutes=30):
        started.append(repo_root)
        return 54321

    with (
        patch("elspais.mcp.daemon.stop_daemon", side_effect=mock_stop),
        patch("elspais.mcp.daemon.start_daemon", side_effect=mock_start),
        patch("elspais.__version__", "0.111.53"),
    ):
        from elspais.mcp.daemon import ensure_daemon

        port = ensure_daemon(tmp_path, ttl_minutes=30)

    assert port == 54321
    assert len(stopped) == 1  # old daemon was stopped
    assert len(started) == 1  # new daemon was started


def test_ensure_daemon_keeps_daemon_on_matching_hash(tmp_path: Path):
    """ensure_daemon should keep daemon when config hash matches."""
    daemon_dir = tmp_path / ".elspais"
    daemon_dir.mkdir()
    daemon_json = daemon_dir / "daemon.json"

    import os

    # Create config first to get the real hash
    config_path = tmp_path / ".elspais.toml"
    config_path.write_text('[project]\nname = "test"\n')

    from elspais.mcp.daemon import compute_config_hash

    real_hash = compute_config_hash(config_path)

    daemon_json.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "port": 12345,
                "repo_root": str(tmp_path),
                "started_at": "2026-01-01T00:00:00",
                "version": "0.111.53",
                "config_hash": real_hash,
            }
        )
    )

    with patch("elspais.__version__", "0.111.53"):
        from elspais.mcp.daemon import ensure_daemon

        port = ensure_daemon(tmp_path, ttl_minutes=30)

    assert port == 12345  # kept the existing daemon
