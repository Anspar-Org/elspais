# tests/mcp/test_daemon_config_hash.py
# Verifies: REQ-d00010

"""Tests for config hash computation in daemon lifecycle."""

from pathlib import Path

from elspais.mcp.daemon import compute_config_hash


def test_compute_config_hash_deterministic(tmp_path: Path):
    """Same config content produces same hash."""
    config_path = tmp_path / ".elspais.toml"
    config_path.write_text('[project]\nname = "test"\nnamespace = "REQ"\n')

    h1 = compute_config_hash(config_path)
    h2 = compute_config_hash(config_path)
    assert h1 == h2
    assert len(h1) == 16  # 8-byte hex


def test_compute_config_hash_includes_local(tmp_path: Path):
    """Hash changes when .elspais.local.toml is added."""
    config_path = tmp_path / ".elspais.toml"
    config_path.write_text('[project]\nname = "test"\nnamespace = "REQ"\n')

    h_without = compute_config_hash(config_path)

    local_path = tmp_path / ".elspais.local.toml"
    local_path.write_text('[associates.foo]\npath = "/tmp/foo"\nnamespace = "FOO"\n')

    h_with = compute_config_hash(config_path)
    assert h_without != h_with


def test_compute_config_hash_changes_on_edit(tmp_path: Path):
    """Hash changes when config content changes."""
    config_path = tmp_path / ".elspais.toml"
    config_path.write_text('[project]\nname = "test"\nnamespace = "REQ"\n')
    h1 = compute_config_hash(config_path)

    config_path.write_text('[project]\nname = "test"\nnamespace = "CAL"\n')
    h2 = compute_config_hash(config_path)
    assert h1 != h2


def test_compute_config_hash_includes_associate_configs(tmp_path: Path):
    """Hash includes associate repo configs when [associates] present."""
    config_path = tmp_path / ".elspais.toml"
    config_path.write_text('[project]\nname = "test"\nnamespace = "REQ"\n')

    assoc_dir = tmp_path / "assoc"
    assoc_dir.mkdir()
    assoc_config = assoc_dir / ".elspais.toml"
    assoc_config.write_text('[project]\nname = "assoc"\nnamespace = "FOO"\n')

    local_path = tmp_path / ".elspais.local.toml"
    local_path.write_text(f'[associates.foo]\npath = "{assoc_dir}"\nnamespace = "FOO"\n')

    h1 = compute_config_hash(config_path)

    # Change associate config
    assoc_config.write_text('[project]\nname = "assoc"\nnamespace = "BAR"\n')
    h2 = compute_config_hash(config_path)
    assert h1 != h2


def test_refresh_daemon_config_hash_updates_stored_hash(tmp_path: Path):
    """A server that re-read config can sync daemon.json's config_hash.

    Verifies: REQ-p00004-J
    """
    import json
    import os

    from elspais.mcp.daemon import refresh_daemon_config_hash

    config_path = tmp_path / ".elspais.toml"
    config_path.write_text('[project]\nname = "test"\n')

    daemon_dir = tmp_path / ".elspais"
    daemon_dir.mkdir()
    daemon_json = daemon_dir / "daemon.json"
    daemon_json.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "port": 12345,
                "repo_root": str(tmp_path),
                "started_at": "2026-01-01T00:00:00",
                "version": "0.0.0",
                "config_hash": "stale_hash_value_",
                "type": "daemon",
            }
        )
    )

    refresh_daemon_config_hash(tmp_path)

    info = json.loads(daemon_json.read_text())
    assert info["config_hash"] == compute_config_hash(config_path)
    # Other fields survive the rewrite
    assert info["port"] == 12345
    assert info["type"] == "daemon"
