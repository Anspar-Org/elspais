"""Tests for Config Layer."""

import tempfile
from pathlib import Path

import pytest

from elspais.config import config_defaults, find_config_file, find_git_root, load_config


class TestConfigDefaults:
    """Tests for config_defaults() function (replaces ConfigLoader.from_dict)."""

    def test_load_from_dict_merges_with_defaults(self):
        from elspais.config import _merge_configs

        data = {
            "patterns": {"prefix": "REQ"},
            "spec": {"directories": ["spec"]},
        }
        merged = _merge_configs(config_defaults(), data)

        assert merged["patterns"]["prefix"] == "REQ"
        assert merged["spec"]["directories"] == ["spec"]

    def test_get_with_default(self):
        defaults = config_defaults()

        result = defaults.get("nonexistent_key", "fallback")

        assert result == "fallback"

    def test_get_nested_key(self):
        from elspais.config import _merge_configs

        data = {"patterns": {"types": {"prd": {"id": "p", "level": 1}}}}
        merged = _merge_configs(config_defaults(), data)

        assert merged["patterns"]["types"]["prd"]["id"] == "p"
        assert merged["patterns"]["types"]["prd"]["level"] == 1


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_from_toml_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write(
                """\
[patterns]
prefix = "MYREQ"

[spec]
directories = ["specs"]
"""
            )
            f.flush()

            config = load_config(Path(f.name))

            assert config["patterns"]["prefix"] == "MYREQ"
            assert config["spec"]["directories"] == ["specs"]

    def test_load_applies_defaults(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write('[patterns]\nprefix = "REQ"\n')
            f.flush()

            config = load_config(Path(f.name))

            # Should have the explicitly-set value
            assert config["patterns"]["prefix"] == "REQ"
            # Should also have default values NOT in the toml file
            assert config.get("testing", {}).get("enabled") is False
            assert config["spec"]["directories"] == ["spec"]


class TestLocalConfigOverride:
    """Tests for .elspais.local.toml deep-merge support."""

    def test_local_toml_merges_over_base(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / ".elspais.toml"
            base.write_text('[patterns]\nprefix = "REQ"\n')

            local = Path(tmpdir) / ".elspais.local.toml"
            local.write_text('[associates]\npaths = ["/home/dev/other-repo"]\n')

            config = load_config(base)

            assert config["patterns"]["prefix"] == "REQ"
            assert config["associates"]["paths"] == ["/home/dev/other-repo"]

    def test_local_toml_overrides_base_values(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / ".elspais.toml"
            base.write_text('[patterns]\nprefix = "REQ"\n')

            local = Path(tmpdir) / ".elspais.local.toml"
            local.write_text('[patterns]\nprefix = "LOCAL"\n')

            config = load_config(base)

            assert config["patterns"]["prefix"] == "LOCAL"

    def test_missing_local_toml_is_silently_ignored(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write('[patterns]\nprefix = "REQ"\n')
            f.flush()

            config = load_config(Path(f.name))

            assert config["patterns"]["prefix"] == "REQ"

    def test_local_toml_deep_merges_nested_sections(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / ".elspais.toml"
            base.write_text('[spec]\ndirectories = ["spec"]\npatterns = ["*.md"]\n')

            local = Path(tmpdir) / ".elspais.local.toml"
            local.write_text('[spec]\ndirectories = ["spec", "extra-specs"]\n')

            config = load_config(base)

            assert config["spec"]["directories"] == ["spec", "extra-specs"]
            # patterns should remain from base (deep-merge preserves siblings)
            assert config["spec"]["patterns"] == ["*.md"]


class TestFindConfigFile:
    """Tests for find_config_file function."""

    def test_finds_config_in_current_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / ".elspais.toml"
            config_path.write_text('[patterns]\nprefix = "REQ"\n')

            found = find_config_file(Path(tmpdir))

            assert found.resolve() == config_path.resolve()

    def test_returns_none_when_not_found(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a .git marker to stop search
            (Path(tmpdir) / ".git").mkdir()

            found = find_config_file(Path(tmpdir))

            assert found is None


class TestFindGitRoot:
    """Tests for find_git_root function."""

    def test_finds_git_root_in_current_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            git_dir = Path(tmpdir) / ".git"
            git_dir.mkdir()

            root = find_git_root(Path(tmpdir))

            assert root.resolve() == Path(tmpdir).resolve()

    def test_finds_git_root_from_subdirectory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            git_dir = Path(tmpdir) / ".git"
            git_dir.mkdir()

            subdir = Path(tmpdir) / "src" / "deep" / "nested"
            subdir.mkdir(parents=True)

            root = find_git_root(subdir)

            assert root.resolve() == Path(tmpdir).resolve()

    def test_returns_none_when_not_in_repo(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # No .git directory

            root = find_git_root(Path(tmpdir))

            assert root is None

    def test_handles_git_worktree_file(self):
        """Git worktrees use a .git file pointing to the actual gitdir."""
        with tempfile.TemporaryDirectory() as tmpdir:
            git_file = Path(tmpdir) / ".git"
            # Worktrees have a .git file (not directory) with gitdir pointer
            git_file.write_text("gitdir: /some/path/.git/worktrees/name")

            root = find_git_root(Path(tmpdir))

            # Should still recognize this as a git root
            assert root.resolve() == Path(tmpdir).resolve()

    def test_defaults_to_cwd(self):
        # Should not raise when called without arguments
        # (will find actual git root of test repo)
        root = find_git_root()
        # We're in a git repo, so should find something
        assert root is not None


class TestPydanticShim:
    """Tests for Pydantic schema validation in load_config()."""

    def test_load_config_validates_schema(self, tmp_path):
        """load_config() should validate against Pydantic schema."""
        config_path = tmp_path / ".elspais.toml"
        config_path.write_text('version = 2\n[project]\nnamespace = "TEST"\n')

        config = load_config(config_path)
        assert config["project"]["namespace"] == "TEST"

    def test_load_config_rejects_unknown_key(self, tmp_path):
        """load_config() should reject unknown TOML keys."""
        config_path = tmp_path / ".elspais.toml"
        config_path.write_text('version = 2\nbogus_key = "oops"\n')

        with pytest.raises(ValueError):
            load_config(config_path)


class TestChangelogConfig:
    """Validates REQ-p00002-A: Changelog configuration defaults and overrides."""

    def test_REQ_p00002_A_changelog_defaults_present(self):
        """config_defaults() includes changelog section with all expected keys."""
        config = config_defaults()
        changelog = config.get("changelog")
        assert changelog is not None
        assert isinstance(changelog, dict)
        for key in (
            "hash_current",
            "id_source",
            "date_format",
        ):
            assert key in changelog, f"Missing key: {key}"
        assert "require" in changelog
        for rkey in ("change_order", "reason"):
            assert rkey in changelog["require"], f"Missing require key: {rkey}"

    def test_REQ_p00002_A_changelog_defaults_values(self):
        """Verify default values for changelog configuration."""
        config = config_defaults()
        assert config["changelog"]["hash_current"] is True
        assert config["changelog"]["id_source"] == "gh"
        assert config["changelog"]["date_format"] == "iso"
        assert config["changelog"]["require"]["change_order"] is False
        assert config["changelog"]["require"]["reason"] is True

    def test_REQ_p00002_A_changelog_user_override(self):
        """User config overrides changelog defaults."""
        from elspais.config import _merge_configs

        config = _merge_configs(config_defaults(), {"changelog": {"hash_current": False}})
        assert config["changelog"]["hash_current"] is False
        # Non-overridden defaults should still be present
        assert config["changelog"]["id_source"] == "gh"
        assert config["changelog"]["require"]["reason"] is True
