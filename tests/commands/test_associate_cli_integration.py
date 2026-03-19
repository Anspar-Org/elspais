"""Integration test: CLI-based associate registration end-to-end.

Validates REQ-p00005-C: CLI-based configuration of associate paths.
Validates REQ-p00005-D: Auto-discovery of associate identity.
Validates REQ-p00005-E: Clear error for invalid associate paths.
"""

import tomlkit

from elspais.associates import get_associate_spec_directories


def _make_core_repo(tmp_path):
    """Create a minimal core repo with .elspais.toml."""
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / ".elspais.toml").write_text(
        'version = 3\n[project]\nname = "core"\n\n' '[scanning.spec]\ndirectories = ["spec"]\n'
    )
    (tmp_path / "spec").mkdir()
    return tmp_path


def _make_associate_repo(base, name, prefix):
    """Create a minimal associate repo."""
    repo = base / name
    repo.mkdir()
    (repo / ".elspais.toml").write_text(
        f'version = 3\n[project]\nname = "{name}"\nnamespace = "{prefix}"\n\n'
        f'[scanning.spec]\ndirectories = ["spec"]\n'
    )
    (repo / "spec").mkdir()
    return repo


def test_REQ_p00005_C_config_add_registers_associate(tmp_path, monkeypatch):
    """Full workflow: add named associate to config → get_associate_spec_directories finds it."""
    core = _make_core_repo(tmp_path / "core")
    assoc = _make_associate_repo(tmp_path, "callisto", "CAL")

    monkeypatch.chdir(core)

    # Write v3 named associate directly into config
    config_path = core / ".elspais.toml"
    config_doc = tomlkit.parse(config_path.read_text())
    config_doc.add("associates", tomlkit.table())
    config_doc["associates"].add("callisto", tomlkit.table())
    config_doc["associates"]["callisto"]["path"] = str(assoc)
    config_doc["associates"]["callisto"]["namespace"] = "CAL"
    config_path.write_text(tomlkit.dumps(config_doc))

    # Verify get_associate_spec_directories picks it up
    config = dict(config_doc)
    dirs, errors = get_associate_spec_directories(config, core)

    assert len(dirs) == 1
    assert dirs[0] == assoc / "spec"
    assert errors == []


def test_REQ_p00005_D_config_add_discovers_identity(tmp_path, monkeypatch):
    """Named associate + discovery reads associate's name and prefix."""
    core = _make_core_repo(tmp_path / "core")
    assoc = _make_associate_repo(tmp_path, "europa", "EUR")

    monkeypatch.chdir(core)

    # Write v3 named associate
    config_path = core / ".elspais.toml"
    config_doc = tomlkit.parse(config_path.read_text())
    config_doc.add("associates", tomlkit.table())
    config_doc["associates"].add("europa", tomlkit.table())
    config_doc["associates"]["europa"]["path"] = str(assoc)
    config_doc["associates"]["europa"]["namespace"] = "EUR"
    config_path.write_text(tomlkit.dumps(config_doc))

    # Load config and verify discovery works
    from elspais.associates import discover_associate_from_path

    result = discover_associate_from_path(assoc)

    from elspais.associates import Associate

    assert isinstance(result, Associate)
    assert result.name == "europa"
    assert result.code == "EUR"


def test_REQ_p00005_E_config_add_invalid_path_produces_error(tmp_path, monkeypatch):
    """Adding an invalid path errors on discovery."""
    core = _make_core_repo(tmp_path / "core")

    monkeypatch.chdir(core)

    # Write v3 named associate with non-existent path
    config = {
        "associates": {
            "broken": {"path": "/nonexistent/repo", "namespace": "BRK"},
        }
    }
    dirs, errors = get_associate_spec_directories(config, core)

    assert len(dirs) == 0
    assert len(errors) == 1
    assert "does not exist" in errors[0]
