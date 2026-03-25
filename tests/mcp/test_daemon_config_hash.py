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
    config_path.write_text('[project]\nname = "test"\n')

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
    config_path.write_text('[project]\nname = "test"\n')

    assoc_dir = tmp_path / "assoc"
    assoc_dir.mkdir()
    assoc_config = assoc_dir / ".elspais.toml"
    assoc_config.write_text('[project]\nnamespace = "FOO"\n')

    local_path = tmp_path / ".elspais.local.toml"
    local_path.write_text(f'[associates.foo]\npath = "{assoc_dir}"\nnamespace = "FOO"\n')

    h1 = compute_config_hash(config_path)

    # Change associate config
    assoc_config.write_text('[project]\nnamespace = "BAR"\n')
    h2 = compute_config_hash(config_path)
    assert h1 != h2
