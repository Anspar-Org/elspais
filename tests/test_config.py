"""
Tests for elspais.config module.
"""

import pytest
from pathlib import Path


class TestConfigLoader:
    """Tests for configuration loading."""

    def test_load_config_from_file(self, hht_like_fixture):
        """Test loading configuration from .elspais.toml file."""
        from elspais.config.loader import load_config

        config = load_config(hht_like_fixture / ".elspais.toml")

        assert config["project"]["name"] == "hht-like-fixture"
        assert config["project"]["type"] == "core"
        assert config["directories"]["spec"] == "spec"

    def test_load_config_with_defaults(self, tmp_path):
        """Test loading minimal config merges with defaults."""
        from elspais.config.loader import load_config

        # Create minimal config
        config_file = tmp_path / ".elspais.toml"
        config_file.write_text('[project]\nname = "test"')

        config = load_config(config_file)

        # Should have merged with defaults
        assert config["project"]["name"] == "test"
        assert "directories" in config
        assert "patterns" in config

    def test_find_config_file(self, hht_like_fixture):
        """Test finding config file in directory."""
        from elspais.config.loader import find_config_file

        config_path = find_config_file(hht_like_fixture)
        assert config_path is not None
        assert config_path.name == ".elspais.toml"

    def test_find_config_file_not_found(self, tmp_path):
        """Test finding config file when none exists."""
        from elspais.config.loader import find_config_file

        config_path = find_config_file(tmp_path)
        assert config_path is None

    def test_find_config_in_parent(self, hht_like_fixture):
        """Test finding config file in parent directory."""
        from elspais.config.loader import find_config_file

        # Look from spec subdirectory
        spec_dir = hht_like_fixture / "spec"
        config_path = find_config_file(spec_dir)
        assert config_path is not None
        assert config_path.parent == hht_like_fixture


class TestConfigMerge:
    """Tests for configuration merging."""

    def test_merge_configs_override(self):
        """Test that user config overrides defaults."""
        from elspais.config.loader import merge_configs

        defaults = {
            "project": {"name": "default", "type": "core"},
            "directories": {"spec": "spec"},
        }
        user = {
            "project": {"name": "custom"},
        }

        merged = merge_configs(defaults, user)

        assert merged["project"]["name"] == "custom"
        assert merged["project"]["type"] == "core"  # From defaults
        assert merged["directories"]["spec"] == "spec"  # From defaults

    def test_merge_configs_deep(self):
        """Test deep merging of nested dictionaries."""
        from elspais.config.loader import merge_configs

        defaults = {
            "patterns": {
                "types": {"prd": {"id": "p", "level": 1}},
                "id_format": {"style": "numeric", "digits": 5},
            }
        }
        user = {
            "patterns": {
                "types": {"dev": {"id": "d", "level": 3}},
            }
        }

        merged = merge_configs(defaults, user)

        # Should have both types
        assert "prd" in merged["patterns"]["types"]
        assert "dev" in merged["patterns"]["types"]
        # id_format should be preserved from defaults
        assert merged["patterns"]["id_format"]["digits"] == 5


class TestDefaultConfig:
    """Tests for default configuration."""

    def test_default_config_structure(self):
        """Test default configuration has all required sections."""
        from elspais.config.defaults import DEFAULT_CONFIG

        assert "project" in DEFAULT_CONFIG
        assert "directories" in DEFAULT_CONFIG
        assert "patterns" in DEFAULT_CONFIG
        assert "rules" in DEFAULT_CONFIG
        assert "spec" in DEFAULT_CONFIG

    def test_default_patterns_hht_style(self):
        """Test default patterns match HHT-diary style."""
        from elspais.config.defaults import DEFAULT_CONFIG

        patterns = DEFAULT_CONFIG["patterns"]

        assert patterns["id_template"] == "{prefix}-{associated}{type}{id}"
        assert patterns["prefix"] == "REQ"
        assert "prd" in patterns["types"]
        assert "ops" in patterns["types"]
        assert "dev" in patterns["types"]

    def test_default_rules(self):
        """Test default validation rules."""
        from elspais.config.defaults import DEFAULT_CONFIG

        rules = DEFAULT_CONFIG["rules"]

        assert rules["hierarchy"]["allow_circular"] is False
        assert rules["format"]["require_hash"] is True


class TestConfigValidation:
    """Tests for configuration validation."""

    def test_validate_config_valid(self, sample_config_dict):
        """Test validation passes for valid config."""
        from elspais.config.loader import validate_config

        errors = validate_config(sample_config_dict)
        assert len(errors) == 0

    def test_validate_config_missing_project(self):
        """Test validation fails when project section is missing."""
        from elspais.config.loader import validate_config

        config = {"directories": {"spec": "spec"}}
        errors = validate_config(config)
        assert len(errors) > 0
        assert any("project" in e.lower() for e in errors)

    def test_validate_config_invalid_type(self):
        """Test validation fails for invalid project type."""
        from elspais.config.loader import validate_config

        config = {"project": {"name": "test", "type": "invalid"}}
        errors = validate_config(config)
        assert len(errors) > 0
        assert any("type" in e.lower() for e in errors)


class TestEnvironmentOverrides:
    """Tests for environment variable configuration overrides."""

    def test_env_override_spec_dir(self, monkeypatch):
        """Test environment variable overrides spec directory."""
        from elspais.config.loader import apply_env_overrides

        monkeypatch.setenv("ELSPAIS_DIRECTORIES_SPEC", "requirements")

        config = {"directories": {"spec": "spec"}}
        config = apply_env_overrides(config)

        assert config["directories"]["spec"] == "requirements"

    def test_env_override_associated_prefix(self, monkeypatch):
        """Test environment variable overrides associated prefix."""
        from elspais.config.loader import apply_env_overrides

        monkeypatch.setenv("ELSPAIS_ASSOCIATED_PREFIX", "XYZ")

        config = {"associated": {"prefix": "CAL"}}
        config = apply_env_overrides(config)

        assert config["associated"]["prefix"] == "XYZ"


class TestGetDirectories:
    """Tests for get_directories function."""

    def test_get_directories_string(self, tmp_path):
        """Test get_directories with single string config."""
        from elspais.config.loader import get_directories

        # Create directory
        (tmp_path / "spec").mkdir()

        config = {"directories": {"spec": "spec"}}
        result = get_directories(config, "spec", base_path=tmp_path)

        assert len(result) == 1
        assert result[0] == tmp_path / "spec"

    def test_get_directories_list(self, tmp_path):
        """Test get_directories with list config."""
        from elspais.config.loader import get_directories

        # Create directories
        (tmp_path / "spec").mkdir()
        (tmp_path / "spec" / "roadmap").mkdir()

        config = {"directories": {"spec": ["spec", "spec/roadmap"]}}
        result = get_directories(config, "spec", base_path=tmp_path)

        assert len(result) == 2
        assert tmp_path / "spec" in result
        assert tmp_path / "spec" / "roadmap" in result

    def test_get_directories_recursive(self, tmp_path):
        """Test get_directories with recursive=True."""
        from elspais.config.loader import get_directories

        # Create nested directory structure
        (tmp_path / "apps").mkdir()
        (tmp_path / "apps" / "mobile").mkdir()
        (tmp_path / "apps" / "mobile" / "lib").mkdir()
        (tmp_path / "apps" / "web").mkdir()

        config = {"directories": {"code": "apps"}}
        result = get_directories(config, "code", base_path=tmp_path, recursive=True)

        assert len(result) == 4  # apps, apps/mobile, apps/mobile/lib, apps/web
        assert tmp_path / "apps" in result
        assert tmp_path / "apps" / "mobile" in result
        assert tmp_path / "apps" / "mobile" / "lib" in result
        assert tmp_path / "apps" / "web" in result

    def test_get_directories_recursive_with_ignore(self, tmp_path):
        """Test get_directories with recursive=True respects ignore list."""
        from elspais.config.loader import get_directories

        # Create nested directory structure with ignored dirs
        (tmp_path / "apps").mkdir()
        (tmp_path / "apps" / "mobile").mkdir()
        (tmp_path / "apps" / "mobile" / "node_modules").mkdir()
        (tmp_path / "apps" / "mobile" / "node_modules" / "package").mkdir()
        (tmp_path / "apps" / ".git").mkdir()
        (tmp_path / "apps" / "web").mkdir()

        config = {
            "directories": {
                "code": "apps",
                "ignore": ["node_modules", ".git"],
            }
        }
        result = get_directories(config, "code", base_path=tmp_path, recursive=True)

        # Should include: apps, apps/mobile, apps/web
        # Should NOT include: node_modules, .git, or anything under them
        assert tmp_path / "apps" in result
        assert tmp_path / "apps" / "mobile" in result
        assert tmp_path / "apps" / "web" in result
        assert tmp_path / "apps" / "mobile" / "node_modules" not in result
        assert tmp_path / "apps" / "mobile" / "node_modules" / "package" not in result
        assert tmp_path / "apps" / ".git" not in result

    def test_get_directories_multiple_roots_recursive(self, tmp_path):
        """Test get_directories with multiple roots and recursive."""
        from elspais.config.loader import get_directories

        # Create multiple directory trees
        (tmp_path / "apps").mkdir()
        (tmp_path / "apps" / "mobile").mkdir()
        (tmp_path / "packages").mkdir()
        (tmp_path / "packages" / "core").mkdir()

        config = {"directories": {"code": ["apps", "packages"]}}
        result = get_directories(config, "code", base_path=tmp_path, recursive=True)

        assert tmp_path / "apps" in result
        assert tmp_path / "apps" / "mobile" in result
        assert tmp_path / "packages" in result
        assert tmp_path / "packages" / "core" in result

    def test_get_code_directories_convenience(self, tmp_path):
        """Test get_code_directories convenience function."""
        from elspais.config.loader import get_code_directories

        # Create directory structure
        (tmp_path / "apps").mkdir()
        (tmp_path / "apps" / "mobile").mkdir()
        (tmp_path / "packages").mkdir()

        config = {"directories": {"code": ["apps", "packages"]}}
        result = get_code_directories(config, base_path=tmp_path)

        assert tmp_path / "apps" in result
        assert tmp_path / "apps" / "mobile" in result
        assert tmp_path / "packages" in result

    def test_get_spec_directories_not_recursive(self, tmp_path):
        """Test get_spec_directories is NOT recursive by default."""
        from elspais.config.loader import get_spec_directories

        # Create nested directory structure
        (tmp_path / "spec").mkdir()
        (tmp_path / "spec" / "subdir").mkdir()

        config = {"directories": {"spec": "spec"}}
        result = get_spec_directories(None, config, base_path=tmp_path)

        # Should only include spec, NOT spec/subdir
        assert len(result) == 1
        assert tmp_path / "spec" in result
        assert tmp_path / "spec" / "subdir" not in result


class TestConfigCommand:
    """Tests for config command."""

    def test_config_show(self, hht_like_fixture, capsys):
        """Test config show command."""
        import argparse
        import os
        from elspais.commands.config_cmd import run

        # Change to fixture dir
        original_cwd = os.getcwd()
        try:
            os.chdir(hht_like_fixture)
            args = argparse.Namespace(
                config=None,
                config_action="show",
                section=None,
                json=False,
                quiet=False,
            )
            result = run(args)
            assert result == 0

            captured = capsys.readouterr()
            assert "[project]" in captured.out
            assert "hht-like-fixture" in captured.out
        finally:
            os.chdir(original_cwd)

    def test_config_get(self, hht_like_fixture, capsys):
        """Test config get command."""
        import argparse
        import os
        from elspais.commands.config_cmd import run

        original_cwd = os.getcwd()
        try:
            os.chdir(hht_like_fixture)
            args = argparse.Namespace(
                config=None,
                config_action="get",
                key="project.name",
                json=False,
                quiet=False,
            )
            result = run(args)
            assert result == 0

            captured = capsys.readouterr()
            assert "hht-like-fixture" in captured.out
        finally:
            os.chdir(original_cwd)

    def test_config_get_nested(self, hht_like_fixture, capsys):
        """Test config get command with nested key."""
        import argparse
        import os
        from elspais.commands.config_cmd import run

        original_cwd = os.getcwd()
        try:
            os.chdir(hht_like_fixture)
            args = argparse.Namespace(
                config=None,
                config_action="get",
                key="patterns.prefix",
                json=False,
                quiet=False,
            )
            result = run(args)
            assert result == 0

            captured = capsys.readouterr()
            assert "REQ" in captured.out
        finally:
            os.chdir(original_cwd)

    def test_config_get_missing_key(self, hht_like_fixture, capsys):
        """Test config get command with missing key."""
        import argparse
        import os
        from elspais.commands.config_cmd import run

        original_cwd = os.getcwd()
        try:
            os.chdir(hht_like_fixture)
            args = argparse.Namespace(
                config=None,
                config_action="get",
                key="nonexistent.key",
                json=False,
                quiet=False,
            )
            result = run(args)
            assert result == 1

            captured = capsys.readouterr()
            assert "not found" in captured.err
        finally:
            os.chdir(original_cwd)

    def test_config_set(self, tmp_path, capsys):
        """Test config set command."""
        import argparse
        import os
        from elspais.commands.config_cmd import run
        from elspais.config.loader import load_config

        # Create minimal config
        config_file = tmp_path / ".elspais.toml"
        config_file.write_text('[project]\nname = "test"')

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)

            # Set a value
            args = argparse.Namespace(
                config=None,
                config_action="set",
                key="project.name",
                value="new-name",
                quiet=False,
            )
            result = run(args)
            assert result == 0

            # Verify it was set
            config = load_config(config_file)
            assert config["project"]["name"] == "new-name"
        finally:
            os.chdir(original_cwd)

    def test_config_set_nested(self, tmp_path, capsys):
        """Test config set command with nested key."""
        import argparse
        import os
        from elspais.commands.config_cmd import run
        from elspais.config.loader import load_config

        # Create minimal config
        config_file = tmp_path / ".elspais.toml"
        config_file.write_text('[project]\nname = "test"')

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)

            # Set a nested value
            args = argparse.Namespace(
                config=None,
                config_action="set",
                key="patterns.prefix",
                value="PRD",
                quiet=False,
            )
            result = run(args)
            assert result == 0

            # Verify it was set
            config = load_config(config_file)
            assert config["patterns"]["prefix"] == "PRD"
        finally:
            os.chdir(original_cwd)

    def test_config_set_boolean(self, tmp_path, capsys):
        """Test config set command with boolean value."""
        import argparse
        import os
        from elspais.commands.config_cmd import run
        from elspais.config.loader import load_config

        # Create minimal config
        config_file = tmp_path / ".elspais.toml"
        config_file.write_text('[project]\nname = "test"')

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)

            # Set a boolean value
            args = argparse.Namespace(
                config=None,
                config_action="set",
                key="rules.format.require_hash",
                value="false",
                quiet=False,
            )
            result = run(args)
            assert result == 0

            # Verify it was set
            config = load_config(config_file)
            assert config["rules"]["format"]["require_hash"] is False
        finally:
            os.chdir(original_cwd)

    def test_config_add_to_array(self, tmp_path, capsys):
        """Test config add command."""
        import argparse
        import os
        from elspais.commands.config_cmd import run
        from elspais.config.loader import load_config

        # Create config with array
        config_file = tmp_path / ".elspais.toml"
        config_file.write_text('[directories]\ncode = ["src", "lib"]')

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)

            # Add to array
            args = argparse.Namespace(
                config=None,
                config_action="add",
                key="directories.code",
                value="apps",
                quiet=False,
            )
            result = run(args)
            assert result == 0

            # Verify it was added
            config = load_config(config_file)
            assert "apps" in config["directories"]["code"]
            assert "src" in config["directories"]["code"]
            assert "lib" in config["directories"]["code"]
        finally:
            os.chdir(original_cwd)

    def test_config_remove_from_array(self, tmp_path, capsys):
        """Test config remove command."""
        import argparse
        import os
        from elspais.commands.config_cmd import run
        from elspais.config.loader import load_config

        # Create config with array
        config_file = tmp_path / ".elspais.toml"
        config_file.write_text('[directories]\ncode = ["src", "lib", "apps"]')

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)

            # Remove from array
            args = argparse.Namespace(
                config=None,
                config_action="remove",
                key="directories.code",
                value="lib",
                quiet=False,
            )
            result = run(args)
            assert result == 0

            # Verify it was removed
            config = load_config(config_file)
            assert "lib" not in config["directories"]["code"]
            assert "src" in config["directories"]["code"]
            assert "apps" in config["directories"]["code"]
        finally:
            os.chdir(original_cwd)

    def test_config_unset(self, tmp_path, capsys):
        """Test config unset command."""
        import argparse
        import os
        from elspais.commands.config_cmd import run, _load_user_config

        # Create config
        config_file = tmp_path / ".elspais.toml"
        config_file.write_text('[project]\nname = "test"\ntype = "core"')

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)

            # Unset a key
            args = argparse.Namespace(
                config=None,
                config_action="unset",
                key="project.type",
                quiet=False,
            )
            result = run(args)
            assert result == 0

            # Verify it was removed from user config
            user_config = _load_user_config(config_file)
            assert "type" not in user_config.get("project", {})
        finally:
            os.chdir(original_cwd)

    def test_config_path(self, hht_like_fixture, capsys):
        """Test config path command."""
        import argparse
        import os
        from elspais.commands.config_cmd import run

        original_cwd = os.getcwd()
        try:
            os.chdir(hht_like_fixture)
            args = argparse.Namespace(
                config=None,
                config_action="path",
                quiet=False,
            )
            result = run(args)
            assert result == 0

            captured = capsys.readouterr()
            assert ".elspais.toml" in captured.out
        finally:
            os.chdir(original_cwd)

    def test_config_show_section(self, hht_like_fixture, capsys):
        """Test config show with section filter."""
        import argparse
        import os
        from elspais.commands.config_cmd import run

        original_cwd = os.getcwd()
        try:
            os.chdir(hht_like_fixture)
            args = argparse.Namespace(
                config=None,
                config_action="show",
                section="patterns",
                json=False,
                quiet=False,
            )
            result = run(args)
            assert result == 0

            captured = capsys.readouterr()
            assert "prefix" in captured.out
            assert "REQ" in captured.out
        finally:
            os.chdir(original_cwd)


class TestTomlSerializer:
    """Tests for TOML serialization."""

    def test_serialize_simple_values(self):
        """Test serialization of simple values."""
        from elspais.commands.config_cmd import serialize_toml

        config = {
            "name": "test",
            "count": 42,
            "enabled": True,
            "ratio": 3.14,
        }
        result = serialize_toml(config)

        assert 'name = "test"' in result
        assert "count = 42" in result
        assert "enabled = true" in result
        assert "ratio = 3.14" in result

    def test_serialize_array(self):
        """Test serialization of arrays."""
        from elspais.commands.config_cmd import serialize_toml

        config = {
            "items": ["a", "b", "c"],
        }
        result = serialize_toml(config)

        assert 'items = ["a", "b", "c"]' in result

    def test_serialize_nested_table(self):
        """Test serialization of nested tables."""
        from elspais.commands.config_cmd import serialize_toml

        # Large nested table should use section format
        config = {
            "project": {
                "name": "test",
                "version": 1,
                "description": "A test project",
                "author": "Test Author",
                "license": "MIT",
            },
        }
        result = serialize_toml(config)

        assert "[project]" in result
        assert 'name = "test"' in result
        assert "version = 1" in result

    def test_serialize_inline_table(self):
        """Test serialization of inline tables."""
        from elspais.commands.config_cmd import serialize_toml

        config = {
            "prd": {"id": "p", "level": 1},
        }
        result = serialize_toml(config)

        # Small tables should be inline
        assert "prd = {" in result
        assert 'id = "p"' in result

    def test_serialize_roundtrip(self, tmp_path):
        """Test that serialized config can be parsed back."""
        from elspais.commands.config_cmd import serialize_toml
        from elspais.config.loader import parse_toml

        original = {
            "project": {"name": "test", "type": "core"},
            "directories": {"spec": "spec", "code": ["src", "lib"]},
            "rules": {
                "format": {"require_hash": True},
            },
        }

        serialized = serialize_toml(original)
        parsed = parse_toml(serialized)

        assert parsed["project"]["name"] == "test"
        assert parsed["project"]["type"] == "core"
        assert parsed["directories"]["spec"] == "spec"
        assert "src" in parsed["directories"]["code"]
        assert parsed["rules"]["format"]["require_hash"] is True
