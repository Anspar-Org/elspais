"""Tests for associate auto-discovery from repo config.

Validates REQ-p00005-D: Discover associate identity from target repo's config.
Validates REQ-p00005-E: Clear config error for invalid paths/configs.
"""

from elspais.associates import Associate, discover_associate_from_path


def test_REQ_p00005_D_discovers_associate_from_valid_repo(tmp_path):
    """Discovers namespace, name, spec_path from associated repo's .elspais.toml."""
    repo = tmp_path / "callisto"
    repo.mkdir()
    (repo / ".elspais.toml").write_text(
        '[project]\nname = "callisto"\nnamespace = "CAL"\n\n'
        '[scanning.spec]\ndirectories = ["spec"]\n'
    )
    (repo / "spec").mkdir()

    result = discover_associate_from_path(repo)
    assert isinstance(result, Associate)
    assert result.name == "callisto"
    assert result.code == "CAL"
    assert result.spec_path == "spec"
    assert result.path == str(repo)


def test_REQ_p00005_E_error_when_path_does_not_exist(tmp_path):
    """Reports error for non-existent path."""
    result = discover_associate_from_path(tmp_path / "nonexistent")
    assert isinstance(result, str)
    assert "does not exist" in result


def test_REQ_p00005_E_error_when_no_toml(tmp_path):
    """Reports error when path exists but has no .elspais.toml."""
    repo = tmp_path / "bare"
    repo.mkdir()
    result = discover_associate_from_path(repo)
    assert isinstance(result, str)
    assert ".elspais.toml" in result


def test_REQ_p00005_D_defaults_spec_path_to_spec(tmp_path):
    """Uses 'spec' as default spec_path when scanning.spec.directories is not set."""
    repo = tmp_path / "minimal"
    repo.mkdir()
    (repo / ".elspais.toml").write_text('[project]\nname = "minimal"\nnamespace = "MIN"\n')
    result = discover_associate_from_path(repo)
    assert isinstance(result, Associate)
    assert result.spec_path == "spec"
