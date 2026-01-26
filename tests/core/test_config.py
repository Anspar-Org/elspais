"""Tests for Config Layer."""

import pytest
import tempfile
from pathlib import Path

from elspais.config import ConfigLoader, load_config, find_config_file


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
        loader = ConfigLoader.from_dict({
            "patterns": {
                "types": {
                    "prd": {"id": "p", "level": 1}
                }
            }
        })

        assert loader.get("patterns.types.prd.id") == "p"
        assert loader.get("patterns.types.prd.level") == 1


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_from_toml_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write("""\
[patterns]
prefix = "MYREQ"

[spec]
directories = ["specs"]
""")
            f.flush()

            config = load_config(Path(f.name))

            assert config.get("patterns.prefix") == "MYREQ"
            assert config.get("spec.directories") == ["specs"]

    def test_load_applies_defaults(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write("[patterns]\nprefix = \"REQ\"\n")
            f.flush()

            config = load_config(Path(f.name))

            # Should have default values merged in
            assert config.get("patterns.prefix") == "REQ"


class TestFindConfigFile:
    """Tests for find_config_file function."""

    def test_finds_config_in_current_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / ".elspais.toml"
            config_path.write_text("[patterns]\nprefix = \"REQ\"\n")

            found = find_config_file(Path(tmpdir))

            assert found == config_path

    def test_returns_none_when_not_found(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a .git marker to stop search
            (Path(tmpdir) / ".git").mkdir()

            found = find_config_file(Path(tmpdir))

            assert found is None
