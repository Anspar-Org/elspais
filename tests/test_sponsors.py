"""
Tests for sponsor/associated repository configuration loading.
"""

import pytest
from pathlib import Path
from textwrap import dedent
import tempfile

from elspais.sponsors import (
    Sponsor,
    SponsorsConfig,
    parse_yaml,
    load_sponsors_config,
    resolve_sponsor_spec_dir,
    get_sponsor_spec_directories,
    _parse_sponsors_yaml,
)


# Validates: REQ-p00005-A
class TestParseYaml:
    """Tests for the simple YAML parser."""

    def test_parse_simple_key_value(self):
        """Parse simple key-value pairs."""
        yaml = dedent("""\
            name: test
            enabled: true
            count: 42
        """)
        result = parse_yaml(yaml)

        assert result.get("name") == "test"
        assert result.get("enabled") is True
        assert result.get("count") == 42

    def test_parse_quoted_strings(self):
        """Parse quoted strings."""
        yaml = dedent("""\
            path: "some/path/here"
            other: 'single quoted'
        """)
        result = parse_yaml(yaml)

        assert result.get("path") == "some/path/here"
        assert result.get("other") == "single quoted"

    def test_parse_comments(self):
        """Comments should be ignored."""
        yaml = dedent("""\
            # This is a comment
            name: test
            # Another comment
            enabled: true
        """)
        result = parse_yaml(yaml)

        assert result.get("name") == "test"
        assert result.get("enabled") is True

    def test_parse_empty_lines(self):
        """Empty lines should be handled."""
        yaml = dedent("""\
            name: test

            enabled: true
        """)
        result = parse_yaml(yaml)

        assert result.get("name") == "test"
        assert result.get("enabled") is True


# Validates: REQ-p00005-A
class TestParseSponsorsYaml:
    """Tests for sponsors-specific YAML parsing."""

    def test_parse_sponsors_list(self):
        """Parse sponsors list under local section."""
        yaml = dedent("""\
            sponsors:
              local:
                - name: callisto
                  code: CAL
                  enabled: true
                  path: sponsor/callisto
                  spec_path: spec
        """)
        result = _parse_sponsors_yaml(yaml)

        assert "sponsors" in result
        assert "local" in result["sponsors"]
        assert len(result["sponsors"]["local"]) == 1

        sponsor = result["sponsors"]["local"][0]
        assert sponsor["name"] == "callisto"
        assert sponsor["code"] == "CAL"
        assert sponsor["enabled"] is True
        assert sponsor["path"] == "sponsor/callisto"
        assert sponsor["spec_path"] == "spec"

    def test_parse_multiple_sponsors(self):
        """Parse multiple sponsors."""
        yaml = dedent("""\
            sponsors:
              local:
                - name: callisto
                  code: CAL
                  enabled: true
                - name: europa
                  code: EUR
                  enabled: false
        """)
        result = _parse_sponsors_yaml(yaml)

        sponsors = result["sponsors"]["local"]
        assert len(sponsors) == 2
        assert sponsors[0]["name"] == "callisto"
        assert sponsors[1]["name"] == "europa"
        assert sponsors[1]["enabled"] is False

    def test_parse_local_overrides(self):
        """Parse local override format."""
        yaml = dedent("""\
            sponsors:
              callisto:
                local_path: ../../../callisto
        """)
        result = _parse_sponsors_yaml(yaml)

        assert "sponsors" in result
        assert "callisto" in result["sponsors"]
        assert result["sponsors"]["callisto"]["local_path"] == "../../../callisto"


# Validates: REQ-p00005-A
class TestSponsor:
    """Tests for Sponsor dataclass."""

    def test_sponsor_defaults(self):
        """Sponsor should have sensible defaults."""
        sponsor = Sponsor(name="test", code="TST")

        assert sponsor.name == "test"
        assert sponsor.code == "TST"
        assert sponsor.enabled is True
        assert sponsor.path == ""
        assert sponsor.spec_path == "spec"
        assert sponsor.local_path is None

    def test_sponsor_custom_values(self):
        """Sponsor should accept custom values."""
        sponsor = Sponsor(
            name="callisto",
            code="CAL",
            enabled=False,
            path="sponsor/callisto",
            spec_path="requirements",
            local_path="/external/callisto",
        )

        assert sponsor.name == "callisto"
        assert sponsor.code == "CAL"
        assert sponsor.enabled is False
        assert sponsor.path == "sponsor/callisto"
        assert sponsor.spec_path == "requirements"
        assert sponsor.local_path == "/external/callisto"


# Validates: REQ-p00005-A
class TestLoadSponsorsConfig:
    """Tests for loading sponsor configuration."""

    def test_load_empty_config(self):
        """Empty config should return empty sponsors list."""
        config = {}
        result = load_sponsors_config(config)

        assert isinstance(result, SponsorsConfig)
        assert len(result.sponsors) == 0

    def test_load_no_config_file(self):
        """Missing config file should return empty sponsors."""
        config = {"sponsors": {"config_file": "nonexistent.yml"}}
        result = load_sponsors_config(config)

        assert len(result.sponsors) == 0

    def test_load_with_config_file(self):
        """Should load sponsors from config file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create config structure
            config_dir = tmppath / ".github" / "config"
            config_dir.mkdir(parents=True)

            sponsors_yaml = config_dir / "sponsors.yml"
            sponsors_yaml.write_text(dedent("""\
                sponsors:
                  local:
                    - name: callisto
                      code: CAL
                      enabled: true
                      path: sponsor/callisto
                      spec_path: spec
            """))

            config = {
                "sponsors": {
                    "config_file": ".github/config/sponsors.yml",
                    "local_dir": "sponsor",
                }
            }

            result = load_sponsors_config(config, base_path=tmppath)

            assert len(result.sponsors) == 1
            assert result.sponsors[0].name == "callisto"
            assert result.sponsors[0].code == "CAL"

    def test_load_with_local_overrides(self):
        """Should apply local path overrides."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create config structure
            config_dir = tmppath / ".github" / "config"
            config_dir.mkdir(parents=True)

            # Main config
            sponsors_yaml = config_dir / "sponsors.yml"
            sponsors_yaml.write_text(dedent("""\
                sponsors:
                  local:
                    - name: callisto
                      code: CAL
                      enabled: true
                      path: sponsor/callisto
                      spec_path: spec
            """))

            # Local override
            local_yaml = config_dir / "sponsors.local.yml"
            local_yaml.write_text(dedent("""\
                sponsors:
                  callisto:
                    local_path: ../external/callisto
            """))

            config = {
                "sponsors": {
                    "config_file": ".github/config/sponsors.yml",
                    "local_dir": "sponsor",
                }
            }

            result = load_sponsors_config(config, base_path=tmppath)

            assert len(result.sponsors) == 1
            assert result.sponsors[0].local_path == "../external/callisto"


# Validates: REQ-p00005-A
class TestResolveSponsorSpecDir:
    """Tests for resolving sponsor spec directories."""

    def test_resolve_disabled_sponsor(self):
        """Disabled sponsors should return None."""
        sponsor = Sponsor(name="test", code="TST", enabled=False)
        config = SponsorsConfig()

        result = resolve_sponsor_spec_dir(sponsor, config)

        assert result is None

    def test_resolve_with_local_path(self):
        """Should prefer local_path when set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create spec directory
            spec_dir = tmppath / "external" / "spec"
            spec_dir.mkdir(parents=True)

            sponsor = Sponsor(
                name="test",
                code="TST",
                local_path=str(tmppath / "external"),
                spec_path="spec",
            )
            config = SponsorsConfig()

            result = resolve_sponsor_spec_dir(sponsor, config, base_path=tmppath)

            assert result == spec_dir

    def test_resolve_with_default_path(self):
        """Should use path when local_path not set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create spec directory
            spec_dir = tmppath / "sponsor" / "callisto" / "spec"
            spec_dir.mkdir(parents=True)

            sponsor = Sponsor(
                name="callisto",
                code="CAL",
                path="sponsor/callisto",
                spec_path="spec",
            )
            config = SponsorsConfig()

            result = resolve_sponsor_spec_dir(sponsor, config, base_path=tmppath)

            assert result == spec_dir

    def test_resolve_with_local_dir(self):
        """Should try local_dir/name/spec_path as fallback."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create spec directory using local_dir convention
            spec_dir = tmppath / "sponsors" / "callisto" / "spec"
            spec_dir.mkdir(parents=True)

            sponsor = Sponsor(
                name="callisto",
                code="CAL",
                spec_path="spec",
            )
            config = SponsorsConfig(local_dir="sponsors")

            result = resolve_sponsor_spec_dir(sponsor, config, base_path=tmppath)

            assert result == spec_dir

    def test_resolve_nonexistent_returns_none(self):
        """Should return None when spec dir doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            sponsor = Sponsor(
                name="callisto",
                code="CAL",
                path="sponsor/callisto",
            )
            config = SponsorsConfig()

            result = resolve_sponsor_spec_dir(sponsor, config, base_path=tmppath)

            assert result is None


# Validates: REQ-p00005-A, REQ-p00005-B
class TestGetSponsorSpecDirectories:
    """Tests for getting all sponsor spec directories."""

    def test_get_no_sponsors(self):
        """Should return empty list when no sponsors configured."""
        config = {}
        result = get_sponsor_spec_directories(config)

        assert result == []

    def test_get_sponsor_directories(self):
        """Should return all existing sponsor spec directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create config structure
            config_dir = tmppath / ".github" / "config"
            config_dir.mkdir(parents=True)

            # Create sponsor spec directories
            callisto_spec = tmppath / "sponsor" / "callisto" / "spec"
            callisto_spec.mkdir(parents=True)

            europa_spec = tmppath / "sponsor" / "europa" / "spec"
            europa_spec.mkdir(parents=True)

            sponsors_yaml = config_dir / "sponsors.yml"
            sponsors_yaml.write_text(dedent("""\
                sponsors:
                  local:
                    - name: callisto
                      code: CAL
                      enabled: true
                      path: sponsor/callisto
                      spec_path: spec
                    - name: europa
                      code: EUR
                      enabled: true
                      path: sponsor/europa
                      spec_path: spec
            """))

            config = {
                "sponsors": {
                    "config_file": ".github/config/sponsors.yml",
                    "local_dir": "sponsor",
                }
            }

            result = get_sponsor_spec_directories(config, base_path=tmppath)

            assert len(result) == 2
            assert callisto_spec in result
            assert europa_spec in result

    def test_get_skips_disabled_sponsors(self):
        """Should skip disabled sponsors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create config structure
            config_dir = tmppath / ".github" / "config"
            config_dir.mkdir(parents=True)

            # Create sponsor spec directories
            callisto_spec = tmppath / "sponsor" / "callisto" / "spec"
            callisto_spec.mkdir(parents=True)

            europa_spec = tmppath / "sponsor" / "europa" / "spec"
            europa_spec.mkdir(parents=True)

            sponsors_yaml = config_dir / "sponsors.yml"
            sponsors_yaml.write_text(dedent("""\
                sponsors:
                  local:
                    - name: callisto
                      code: CAL
                      enabled: true
                      path: sponsor/callisto
                      spec_path: spec
                    - name: europa
                      code: EUR
                      enabled: false
                      path: sponsor/europa
                      spec_path: spec
            """))

            config = {
                "sponsors": {
                    "config_file": ".github/config/sponsors.yml",
                    "local_dir": "sponsor",
                }
            }

            result = get_sponsor_spec_directories(config, base_path=tmppath)

            assert len(result) == 1
            assert callisto_spec in result
            assert europa_spec not in result

    def test_get_skips_nonexistent_directories(self):
        """Should skip sponsors with nonexistent spec directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create config structure
            config_dir = tmppath / ".github" / "config"
            config_dir.mkdir(parents=True)

            # Create only callisto spec directory (not europa)
            callisto_spec = tmppath / "sponsor" / "callisto" / "spec"
            callisto_spec.mkdir(parents=True)

            sponsors_yaml = config_dir / "sponsors.yml"
            sponsors_yaml.write_text(dedent("""\
                sponsors:
                  local:
                    - name: callisto
                      code: CAL
                      enabled: true
                      path: sponsor/callisto
                      spec_path: spec
                    - name: europa
                      code: EUR
                      enabled: true
                      path: sponsor/europa
                      spec_path: spec
            """))

            config = {
                "sponsors": {
                    "config_file": ".github/config/sponsors.yml",
                    "local_dir": "sponsor",
                }
            }

            result = get_sponsor_spec_directories(config, base_path=tmppath)

            assert len(result) == 1
            assert callisto_spec in result
