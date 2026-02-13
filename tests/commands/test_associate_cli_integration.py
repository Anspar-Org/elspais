"""Integration test: CLI-based associate registration end-to-end.

Validates REQ-p00005-C: CLI-based configuration of associate paths.
Validates REQ-p00005-D: Auto-discovery of associate identity.
Validates REQ-p00005-E: Clear error for invalid associate paths.
"""

import argparse

import tomlkit

from elspais.associates import get_associate_spec_directories
from elspais.commands.config_cmd import cmd_add


def _make_core_repo(tmp_path):
    """Create a minimal core repo with .elspais.toml."""
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / ".elspais.toml").write_text(
        '[project]\nname = "core"\ntype = "core"\n\n' '[directories]\nspec = "spec"\n'
    )
    (tmp_path / "spec").mkdir()
    return tmp_path


def _make_associate_repo(base, name, prefix):
    """Create a minimal associate repo."""
    repo = base / name
    repo.mkdir()
    (repo / ".elspais.toml").write_text(
        f'[project]\nname = "{name}"\ntype = "associated"\n\n'
        f'[associated]\nprefix = "{prefix}"\n\n'
        f'[directories]\nspec = "spec"\n'
    )
    (repo / "spec").mkdir()
    return repo


def test_REQ_p00005_C_config_add_registers_associate(tmp_path, monkeypatch):
    """Full workflow: config add → get_associate_spec_directories finds it."""
    core = _make_core_repo(tmp_path / "core")
    assoc = _make_associate_repo(tmp_path, "callisto", "CAL")

    # Use config add to register the associate path
    monkeypatch.chdir(core)
    args = argparse.Namespace(
        key="associates.paths",
        value=str(assoc),
        config=core / ".elspais.toml",
        quiet=True,
    )
    rc = cmd_add(args)
    assert rc == 0

    # Verify the TOML was written correctly
    config_doc = tomlkit.parse((core / ".elspais.toml").read_text())
    assert str(assoc) in config_doc["associates"]["paths"]

    # Verify get_associate_spec_directories picks it up
    config = dict(config_doc)
    dirs, errors = get_associate_spec_directories(config, core)

    assert len(dirs) == 1
    assert dirs[0] == assoc / "spec"
    assert errors == []


def test_REQ_p00005_D_config_add_discovers_identity(tmp_path, monkeypatch):
    """Config add + discovery reads associate's name and prefix."""
    core = _make_core_repo(tmp_path / "core")
    assoc = _make_associate_repo(tmp_path, "europa", "EUR")

    monkeypatch.chdir(core)
    args = argparse.Namespace(
        key="associates.paths",
        value=str(assoc),
        config=core / ".elspais.toml",
        quiet=True,
    )
    cmd_add(args)

    # Load config and verify discovery works
    from elspais.associates import discover_associate_from_path

    config_doc = tomlkit.parse((core / ".elspais.toml").read_text())
    paths = config_doc["associates"]["paths"]
    result = discover_associate_from_path(paths[0])

    from elspais.associates import Associate

    assert isinstance(result, Associate)
    assert result.name == "europa"
    assert result.code == "EUR"


def test_REQ_p00005_E_config_add_invalid_path_produces_error(tmp_path, monkeypatch):
    """Adding an invalid path succeeds at config level but errors on discovery."""
    core = _make_core_repo(tmp_path / "core")

    monkeypatch.chdir(core)
    args = argparse.Namespace(
        key="associates.paths",
        value="/nonexistent/repo",
        config=core / ".elspais.toml",
        quiet=True,
    )
    rc = cmd_add(args)
    assert rc == 0  # config add itself succeeds

    # But discovery reports the error
    config_doc = tomlkit.parse((core / ".elspais.toml").read_text())
    config = dict(config_doc)
    dirs, errors = get_associate_spec_directories(config, core)

    assert len(dirs) == 0
    assert len(errors) == 1
    assert "does not exist" in errors[0]
