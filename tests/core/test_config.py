"""Tests for Config Layer."""

import tempfile
from pathlib import Path

from elspais.config import ConfigLoader, find_config_file, find_git_root, load_config


class TestConfigLoader:
    """Tests for ConfigLoader class."""

    def test_load_from_dict(self):
        data = {
            "patterns": {"prefix": "REQ"},
            "spec": {"directories": ["spec"]},
        }
        loader = ConfigLoader.from_dict(data)

        assert loader.get("patterns.prefix") == "REQ"
        assert loader.get("spec.directories") == ["spec"]

    def test_get_with_default(self):
        loader = ConfigLoader.from_dict({})

        result = loader.get("nonexistent.key", default="fallback")

        assert result == "fallback"

    def test_get_nested_key(self):
        loader = ConfigLoader.from_dict({"patterns": {"types": {"prd": {"id": "p", "level": 1}}}})

        assert loader.get("patterns.types.prd.id") == "p"
        assert loader.get("patterns.types.prd.level") == 1


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

            assert config.get("patterns.prefix") == "MYREQ"
            assert config.get("spec.directories") == ["specs"]

    def test_load_applies_defaults(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write('[patterns]\nprefix = "REQ"\n')
            f.flush()

            config = load_config(Path(f.name))

            # Should have default values merged in
            assert config.get("patterns.prefix") == "REQ"


class TestLocalConfigOverride:
    """Tests for .elspais.local.toml deep-merge support."""

    def test_local_toml_merges_over_base(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / ".elspais.toml"
            base.write_text('[patterns]\nprefix = "REQ"\n')

            local = Path(tmpdir) / ".elspais.local.toml"
            local.write_text('[associates]\npaths = ["/home/dev/other-repo"]\n')

            config = load_config(base)

            assert config.get("patterns.prefix") == "REQ"
            assert config.get("associates.paths") == ["/home/dev/other-repo"]

    def test_local_toml_overrides_base_values(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / ".elspais.toml"
            base.write_text('[patterns]\nprefix = "REQ"\n')

            local = Path(tmpdir) / ".elspais.local.toml"
            local.write_text('[patterns]\nprefix = "LOCAL"\n')

            config = load_config(base)

            assert config.get("patterns.prefix") == "LOCAL"

    def test_missing_local_toml_is_silently_ignored(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write('[patterns]\nprefix = "REQ"\n')
            f.flush()

            config = load_config(Path(f.name))

            assert config.get("patterns.prefix") == "REQ"

    def test_local_toml_deep_merges_nested_sections(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / ".elspais.toml"
            base.write_text('[spec]\ndirectories = ["spec"]\npatterns = ["*.md"]\n')

            local = Path(tmpdir) / ".elspais.local.toml"
            local.write_text('[spec]\ndirectories = ["spec", "extra-specs"]\n')

            config = load_config(base)

            assert config.get("spec.directories") == ["spec", "extra-specs"]
            # patterns should remain from base (deep-merge preserves siblings)
            assert config.get("spec.patterns") == ["*.md"]


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
