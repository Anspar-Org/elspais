"""Tests for path-based associate loading.

Validates REQ-p00005-C: CLI-based configuration of associate repository paths.
Validates REQ-p00005-E: Clear config error for invalid paths/configs.
"""

from pathlib import Path

from elspais.associates import get_associate_spec_directories


def _make_associate_repo(base: Path, name: str, prefix: str) -> Path:
    """Helper: create a minimal associated repo directory."""
    repo = base / name
    repo.mkdir()
    (repo / ".elspais.toml").write_text(
        f'[project]\nname = "{name}"\ntype = "associated"\n\n'
        f'[associated]\nprefix = "{prefix}"\n\n'
        f'[directories]\nspec = "spec"\n'
    )
    (repo / "spec").mkdir()
    return repo


def test_REQ_p00005_C_loads_associates_from_paths_config(tmp_path):
    """Registers associates via config['associates']['paths'] array."""
    repo = _make_associate_repo(tmp_path, "callisto", "CAL")

    config = {"associates": {"paths": [str(repo)]}}
    dirs = get_associate_spec_directories(config, tmp_path)

    assert len(dirs) == 1
    assert dirs[0] == repo / "spec"


def test_REQ_p00005_C_loads_multiple_associates(tmp_path):
    """Registers multiple associates from paths array."""
    repo1 = _make_associate_repo(tmp_path, "callisto", "CAL")
    repo2 = _make_associate_repo(tmp_path, "europa", "EUR")

    config = {"associates": {"paths": [str(repo1), str(repo2)]}}
    dirs = get_associate_spec_directories(config, tmp_path)

    assert len(dirs) == 2


def test_REQ_p00005_E_skips_invalid_path_in_array(tmp_path, capsys):
    """Skips invalid paths and continues with valid ones."""
    repo = _make_associate_repo(tmp_path, "callisto", "CAL")

    config = {"associates": {"paths": ["/nonexistent", str(repo)]}}
    dirs = get_associate_spec_directories(config, tmp_path)

    assert len(dirs) == 1
    captured = capsys.readouterr()
    assert "does not exist" in captured.err


def test_REQ_p00005_C_coexists_with_sponsors_config(tmp_path):
    """Path-based associates work alongside existing sponsors config."""
    repo = _make_associate_repo(tmp_path, "callisto", "CAL")

    # Config has both old sponsors section (empty) and new associates.paths
    config = {
        "sponsors": {},
        "associates": {"paths": [str(repo)]},
    }
    dirs = get_associate_spec_directories(config, tmp_path)

    assert len(dirs) == 1


def test_REQ_p00005_C_empty_paths_array(tmp_path):
    """Empty paths array returns no directories."""
    config = {"associates": {"paths": []}}
    dirs = get_associate_spec_directories(config, tmp_path)
    assert dirs == []


def test_REQ_p00005_E_skips_when_spec_dir_missing(tmp_path, capsys):
    """Reports error when associate repo exists but spec dir is missing."""
    repo = tmp_path / "no-spec"
    repo.mkdir()
    (repo / ".elspais.toml").write_text(
        '[project]\nname = "no-spec"\ntype = "associated"\n\n'
        '[associated]\nprefix = "NSP"\n\n'
        '[directories]\nspec = "spec"\n'
    )
    # Note: NOT creating spec/ directory

    config = {"associates": {"paths": [str(repo)]}}
    dirs = get_associate_spec_directories(config, tmp_path)

    assert len(dirs) == 0
