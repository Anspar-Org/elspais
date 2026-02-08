"""Tests for TOML parser replacement (tomlkit).

Validates that the tomlkit-based TOML parser correctly handles edge cases
that the previous custom parser failed on: multi-line arrays, comma-containing
strings, inline comments on numeric values, and round-trip preservation.

Validates REQ-p00002-A:
    The tool SHALL validate requirement format against configurable patterns
    and rules.
"""

from pathlib import Path

import pytest
import tomlkit

from elspais.config import parse_toml, parse_toml_document

# ---------------------------------------------------------------------------
# Fixture directory discovery
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

# Directories known to contain .elspais.toml files
FIXTURE_DIRS_WITH_TOML = [
    d for d in sorted(FIXTURES_DIR.iterdir()) if d.is_dir() and (d / ".elspais.toml").exists()
]


class TestTomlParserBugFixes:
    """Regression tests for bugs fixed by the tomlkit migration.

    Validates REQ-p00002-A:
        The custom parser collapsed multi-line arrays, mis-split
        comma-containing strings, and failed on inline comments.
    """

    def test_REQ_p00002_A_multiline_array_parsing(self):
        """Multi-line arrays must parse to a proper list, not the string '['."""
        toml_content = """\
[rules.hierarchy]
allowed_implements = [
    "dev -> ops, prd",
    "ops -> prd",
]
"""
        result = parse_toml(toml_content)

        allowed = result["rules"]["hierarchy"]["allowed_implements"]
        assert isinstance(
            allowed, list
        ), f"Expected list, got {type(allowed).__name__}: {allowed!r}"
        assert allowed == ["dev -> ops, prd", "ops -> prd"]

    def test_REQ_p00002_A_comma_in_string_array(self):
        """Arrays with comma-containing strings must not be split on commas."""
        toml_content = """\
values = ["hello, world", "foo, bar"]
"""
        result = parse_toml(toml_content)

        assert result["values"] == ["hello, world", "foo, bar"]
        assert len(result["values"]) == 2

    def test_REQ_p00002_A_inline_comment_numeric(self):
        """Numeric values with inline comments must parse correctly."""
        toml_content = """\
[patterns.id_format]
digits = 0  # Variable length
leading_zeros = false
"""
        result = parse_toml(toml_content)

        assert result["patterns"]["id_format"]["digits"] == 0
        assert isinstance(result["patterns"]["id_format"]["digits"], int)
        assert result["patterns"]["id_format"]["leading_zeros"] is False


class TestTomlRoundTrip:
    """Tests for round-trip editing that preserves comments and formatting.

    Validates REQ-p00002-A:
        Configuration files must survive load-modify-save cycles without
        losing comments or corrupting structure.
    """

    def test_REQ_p00002_A_roundtrip_preserves_comments(self):
        """Loading and dumping a TOML document must preserve comments."""
        toml_content = """\
# Project configuration
[project]
name = "test-project"  # inline comment

[patterns]
prefix = "REQ"  # The prefix for all requirement IDs

# Hierarchy rules
[rules.hierarchy]
allowed_implements = [
    "dev -> ops, prd",
    "ops -> prd",
]
"""
        doc = parse_toml_document(toml_content)
        output = tomlkit.dumps(doc)

        # All comments must survive the round-trip
        assert "# Project configuration" in output
        assert "# inline comment" in output
        assert "# The prefix for all requirement IDs" in output
        assert "# Hierarchy rules" in output

        # Values must also survive
        assert doc["project"]["name"] == "test-project"
        assert doc["patterns"]["prefix"] == "REQ"

    def test_REQ_p00002_A_config_add_roundtrip(self, tmp_path):
        """Simulate the config-add flow: load, modify, save, reload."""
        toml_file = tmp_path / ".elspais.toml"
        original_content = """\
# Main configuration
[project]
name = "my-project"

[rules.hierarchy]
allowed_implements = [
    "dev -> ops, prd",
    "ops -> prd",
]
allow_circular = false  # Safety check

[patterns.id_format]
digits = 5  # Five digit IDs
"""
        toml_file.write_text(original_content)

        # Step 1: Load the document (preserving formatting)
        doc = parse_toml_document(toml_file.read_text())

        # Step 2: Modify a value
        doc["project"]["name"] = "my-project-updated"

        # Step 3: Write back
        toml_file.write_text(tomlkit.dumps(doc))

        # Step 4: Reload and verify
        reloaded = parse_toml(toml_file.read_text())

        # Modified value persisted
        assert reloaded["project"]["name"] == "my-project-updated"

        # Multi-line array survived
        allowed = reloaded["rules"]["hierarchy"]["allowed_implements"]
        assert isinstance(allowed, list)
        assert allowed == ["dev -> ops, prd", "ops -> prd"]

        # Other values survived
        assert reloaded["rules"]["hierarchy"]["allow_circular"] is False
        assert reloaded["patterns"]["id_format"]["digits"] == 5

        # Comments survived in the raw text
        raw = toml_file.read_text()
        assert "# Main configuration" in raw
        assert "# Safety check" in raw
        assert "# Five digit IDs" in raw


class TestTomlParserEdgeCases:
    """Tests for additional TOML parsing edge cases.

    Validates REQ-p00002-A:
        The parser must handle empty configs, inline tables, and all
        standard TOML constructs used by elspais configuration files.
    """

    def test_REQ_p00002_A_empty_config(self):
        """Parsing an empty string must return an empty dict."""
        result = parse_toml("")

        assert isinstance(result, dict)
        assert len(result) == 0

    def test_REQ_p00002_A_inline_table_parsing(self):
        """Inline tables used for type definitions must parse correctly."""
        toml_content = """\
[patterns.types]
prd = { id = "p", name = "Product Requirement", level = 1 }
ops = { id = "o", name = "Operations Requirement", level = 2 }
dev = { id = "d", name = "Development Requirement", level = 3 }
"""
        result = parse_toml(toml_content)
        types = result["patterns"]["types"]

        assert types["prd"]["id"] == "p"
        assert types["prd"]["name"] == "Product Requirement"
        assert types["prd"]["level"] == 1

        assert types["ops"]["id"] == "o"
        assert types["ops"]["level"] == 2

        assert types["dev"]["id"] == "d"
        assert types["dev"]["level"] == 3


class TestFixtureTomlFiles:
    """Tests that all fixture .elspais.toml files parse without error.

    Validates REQ-p00002-A:
        Every fixture configuration file must be valid TOML and produce
        a non-empty dictionary.
    """

    @pytest.mark.parametrize(
        "fixture_dir",
        FIXTURE_DIRS_WITH_TOML,
        ids=[d.name for d in FIXTURE_DIRS_WITH_TOML],
    )
    def test_REQ_p00002_A_fixture_toml_parses(self, fixture_dir):
        """Each fixture .elspais.toml must parse to a non-empty dict."""
        toml_path = fixture_dir / ".elspais.toml"
        content = toml_path.read_text()

        result = parse_toml(content)

        assert isinstance(result, dict), f"Expected dict, got {type(result).__name__}"
        assert len(result) > 0, f"Parsed config from {fixture_dir.name} is empty"
