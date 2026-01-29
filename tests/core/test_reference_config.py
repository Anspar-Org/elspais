"""Tests for unified reference configuration.

Tests REQ-p00001 (unified reference configuration)
"""

from pathlib import Path

import pytest

from elspais.utilities.patterns import PatternConfig
from elspais.utilities.reference_config import (
    ReferenceConfig,
    ReferenceOverride,
    ReferenceResolver,
    build_block_header_pattern,
    build_block_ref_pattern,
    build_comment_pattern,
    build_id_pattern,
    extract_ids_from_text,
    normalize_extracted_id,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def default_ref_config() -> ReferenceConfig:
    """Default reference configuration."""
    return ReferenceConfig()


@pytest.fixture
def default_pattern_config() -> PatternConfig:
    """Default pattern configuration for testing."""
    return PatternConfig.from_dict(
        {
            "prefix": "REQ",
            "types": {
                "prd": {"id": "p", "name": "PRD", "level": 1},
                "ops": {"id": "o", "name": "OPS", "level": 2},
                "dev": {"id": "d", "name": "DEV", "level": 3},
            },
            "id_format": {"style": "numeric", "digits": 5},
            "assertions": {"label_style": "uppercase"},
        }
    )


@pytest.fixture
def base_path(tmp_path: Path) -> Path:
    """Base path for file matching tests."""
    return tmp_path


# =============================================================================
# ReferenceConfig Tests
# =============================================================================


class TestReferenceConfig:
    """Tests for ReferenceConfig dataclass."""

    def test_REQ_p00001_A_default_values(self) -> None:
        """Test ReferenceConfig has correct defaults."""
        config = ReferenceConfig()

        assert config.separators == ["-", "_"]
        assert config.case_sensitive is False
        assert config.prefix_optional is False
        assert config.comment_styles == ["#", "//", "--"]
        assert "implements" in config.keywords
        assert "validates" in config.keywords
        assert "refines" in config.keywords

    def test_REQ_p00001_B_from_dict_full(self) -> None:
        """Test ReferenceConfig.from_dict with all values."""
        data = {
            "separators": ["_"],
            "case_sensitive": True,
            "prefix_optional": True,
            "comment_styles": ["//"],
            "keywords": {
                "implements": ["IMPL"],
                "validates": ["TEST"],
            },
        }

        config = ReferenceConfig.from_dict(data)

        assert config.separators == ["_"]
        assert config.case_sensitive is True
        assert config.prefix_optional is True
        assert config.comment_styles == ["//"]
        assert config.keywords["implements"] == ["IMPL"]

    def test_REQ_p00001_C_from_dict_partial(self) -> None:
        """Test ReferenceConfig.from_dict with partial values uses defaults."""
        data = {"separators": ["_"]}

        config = ReferenceConfig.from_dict(data)

        assert config.separators == ["_"]
        assert config.case_sensitive is False  # default
        assert config.prefix_optional is False  # default

    def test_REQ_p00001_D_from_dict_empty(self) -> None:
        """Test ReferenceConfig.from_dict with empty dict uses all defaults."""
        config = ReferenceConfig.from_dict({})

        assert config.separators == ["-", "_"]
        assert config.case_sensitive is False

    def test_REQ_p00001_E_merge_with_full_override(self) -> None:
        """Test merge_with applies all override values."""
        base = ReferenceConfig()
        override = ReferenceOverride(
            match="*.py",
            separators=["_"],
            case_sensitive=True,
            prefix_optional=True,
            comment_styles=["#"],
            keywords={"implements": ["IMPL"]},
        )

        merged = base.merge_with(override)

        assert merged.separators == ["_"]
        assert merged.case_sensitive is True
        assert merged.prefix_optional is True
        assert merged.comment_styles == ["#"]
        assert merged.keywords["implements"] == ["IMPL"]
        # Original keywords should be preserved
        assert "validates" in merged.keywords

    def test_REQ_p00001_F_merge_with_partial_override(self) -> None:
        """Test merge_with only applies non-None values."""
        base = ReferenceConfig()
        override = ReferenceOverride(
            match="*.py",
            separators=["_"],
            # Other values are None
        )

        merged = base.merge_with(override)

        assert merged.separators == ["_"]
        assert merged.case_sensitive is False  # From base
        assert merged.prefix_optional is False  # From base
        assert merged.comment_styles == ["#", "//", "--"]  # From base


# =============================================================================
# ReferenceOverride Tests
# =============================================================================


class TestReferenceOverride:
    """Tests for ReferenceOverride dataclass."""

    def test_REQ_p00001_A_from_dict_minimal(self) -> None:
        """Test ReferenceOverride.from_dict with only match."""
        data = {"match": "*.py"}

        override = ReferenceOverride.from_dict(data)

        assert override.match == "*.py"
        assert override.separators is None
        assert override.case_sensitive is None

    def test_REQ_p00001_B_from_dict_full(self) -> None:
        """Test ReferenceOverride.from_dict with all values."""
        data = {
            "match": "tests/**",
            "separators": ["_"],
            "case_sensitive": True,
            "prefix_optional": True,
            "comment_styles": ["#"],
            "keywords": {"validates": ["TEST"]},
        }

        override = ReferenceOverride.from_dict(data)

        assert override.match == "tests/**"
        assert override.separators == ["_"]
        assert override.case_sensitive is True

    def test_REQ_p00001_C_from_dict_missing_match_raises(self) -> None:
        """Test ReferenceOverride.from_dict raises without match."""
        with pytest.raises(ValueError, match="requires 'match'"):
            ReferenceOverride.from_dict({"separators": ["_"]})

    def test_REQ_p00001_D_applies_to_simple_glob(self, base_path: Path) -> None:
        """Test applies_to with simple *.py pattern."""
        override = ReferenceOverride(match="*.py")
        py_file = base_path / "test_example.py"
        js_file = base_path / "app.js"

        assert override.applies_to(py_file, base_path) is True
        assert override.applies_to(js_file, base_path) is False

    def test_REQ_p00001_E_applies_to_nested_file(self, base_path: Path) -> None:
        """Test applies_to matches files in subdirectories with *.py."""
        override = ReferenceOverride(match="*.py")
        nested_py = base_path / "src" / "module" / "file.py"

        # *.py should match just the filename
        assert override.applies_to(nested_py, base_path) is True

    def test_REQ_p00001_F_applies_to_directory_pattern(self, base_path: Path) -> None:
        """Test applies_to with tests/** pattern."""
        override = ReferenceOverride(match="tests/**")
        test_file = base_path / "tests" / "test_example.py"
        src_file = base_path / "src" / "module.py"

        assert override.applies_to(test_file, base_path) is True
        assert override.applies_to(src_file, base_path) is False

    def test_REQ_p00001_G_applies_to_nested_directory(self, base_path: Path) -> None:
        """Test applies_to with nested tests/**/fixtures pattern."""
        override = ReferenceOverride(match="tests/**/fixtures/*.json")
        fixture_file = base_path / "tests" / "unit" / "fixtures" / "data.json"
        other_file = base_path / "tests" / "unit" / "test.py"

        assert override.applies_to(fixture_file, base_path) is True
        assert override.applies_to(other_file, base_path) is False

    def test_REQ_p00001_H_applies_to_anywhere_pattern(self, base_path: Path) -> None:
        """Test applies_to with **/conftest.py pattern."""
        override = ReferenceOverride(match="**/conftest.py")
        root_conftest = base_path / "conftest.py"
        nested_conftest = base_path / "tests" / "unit" / "conftest.py"
        other_file = base_path / "tests" / "test.py"

        assert override.applies_to(root_conftest, base_path) is True
        assert override.applies_to(nested_conftest, base_path) is True
        assert override.applies_to(other_file, base_path) is False


# =============================================================================
# ReferenceResolver Tests
# =============================================================================


class TestReferenceResolver:
    """Tests for ReferenceResolver class."""

    def test_REQ_p00001_A_resolve_no_overrides(
        self, default_ref_config: ReferenceConfig, base_path: Path
    ) -> None:
        """Test resolve returns defaults when no overrides match."""
        resolver = ReferenceResolver(default_ref_config, [])
        file_path = base_path / "src" / "module.py"

        result = resolver.resolve(file_path, base_path)

        assert result.separators == default_ref_config.separators
        assert result.case_sensitive == default_ref_config.case_sensitive

    def test_REQ_p00001_B_resolve_single_override(
        self, default_ref_config: ReferenceConfig, base_path: Path
    ) -> None:
        """Test resolve applies single matching override."""
        override = ReferenceOverride(match="*.py", separators=["_"])
        resolver = ReferenceResolver(default_ref_config, [override])
        py_file = base_path / "module.py"
        js_file = base_path / "app.js"

        py_result = resolver.resolve(py_file, base_path)
        js_result = resolver.resolve(js_file, base_path)

        assert py_result.separators == ["_"]
        assert js_result.separators == ["-", "_"]  # default

    def test_REQ_p00001_C_resolve_multiple_overrides_order(
        self, default_ref_config: ReferenceConfig, base_path: Path
    ) -> None:
        """Test resolve applies overrides in order (later wins)."""
        override1 = ReferenceOverride(match="*.py", separators=["_"])
        override2 = ReferenceOverride(match="tests/**", case_sensitive=True)
        resolver = ReferenceResolver(default_ref_config, [override1, override2])

        test_py = base_path / "tests" / "test_example.py"
        result = resolver.resolve(test_py, base_path)

        # Both overrides should apply
        assert result.separators == ["_"]  # from override1
        assert result.case_sensitive is True  # from override2

    def test_REQ_p00001_D_from_config(self) -> None:
        """Test ReferenceResolver.from_config creates resolver correctly."""
        config = {
            "defaults": {
                "separators": ["-"],
                "case_sensitive": True,
            },
            "overrides": [
                {"match": "*.py", "separators": ["_"]},
                {"match": "tests/**", "prefix_optional": True},
            ],
        }

        resolver = ReferenceResolver.from_config(config)

        assert resolver.defaults.separators == ["-"]
        assert resolver.defaults.case_sensitive is True
        assert len(resolver.overrides) == 2
        assert resolver.overrides[0].match == "*.py"

    def test_REQ_p00001_E_from_config_empty(self) -> None:
        """Test ReferenceResolver.from_config with empty config."""
        resolver = ReferenceResolver.from_config({})

        # Should have default defaults
        assert resolver.defaults.separators == ["-", "_"]
        assert len(resolver.overrides) == 0


# =============================================================================
# Pattern Builder Tests
# =============================================================================


class TestBuildIdPattern:
    """Tests for build_id_pattern function."""

    def test_REQ_p00001_A_basic_pattern(
        self, default_pattern_config: PatternConfig, default_ref_config: ReferenceConfig
    ) -> None:
        """Test basic ID pattern matches standard IDs."""
        pattern = build_id_pattern(default_pattern_config, default_ref_config)

        # Should match standard IDs
        assert pattern.search("REQ-p00001")
        assert pattern.search("REQ-d00002")
        assert pattern.search("REQ-o00003")

    def test_REQ_p00001_B_pattern_with_assertion(
        self, default_pattern_config: PatternConfig, default_ref_config: ReferenceConfig
    ) -> None:
        """Test ID pattern matches IDs with assertion suffix."""
        pattern = build_id_pattern(default_pattern_config, default_ref_config)

        match = pattern.search("REQ-p00001-A")
        assert match
        assert match.group("assertion") == "A"

    def test_REQ_p00001_C_case_insensitive(
        self, default_pattern_config: PatternConfig, default_ref_config: ReferenceConfig
    ) -> None:
        """Test pattern is case-insensitive by default."""
        pattern = build_id_pattern(default_pattern_config, default_ref_config)

        assert pattern.search("REQ-p00001")
        assert pattern.search("req-p00001")
        assert pattern.search("Req-P00001")

    def test_REQ_p00001_D_case_sensitive(self, default_pattern_config: PatternConfig) -> None:
        """Test pattern respects case_sensitive setting."""
        ref_config = ReferenceConfig(case_sensitive=True)
        pattern = build_id_pattern(default_pattern_config, ref_config)

        assert pattern.search("REQ-p00001")
        assert not pattern.search("req-p00001")

    def test_REQ_p00001_E_underscore_separator(self, default_pattern_config: PatternConfig) -> None:
        """Test pattern matches underscore separator."""
        ref_config = ReferenceConfig(separators=["_"])
        pattern = build_id_pattern(default_pattern_config, ref_config)

        assert pattern.search("REQ_p00001")
        assert not pattern.search("REQ-p00001")

    def test_REQ_p00001_F_both_separators(
        self, default_pattern_config: PatternConfig, default_ref_config: ReferenceConfig
    ) -> None:
        """Test pattern matches both dash and underscore."""
        pattern = build_id_pattern(default_pattern_config, default_ref_config)

        assert pattern.search("REQ-p00001")
        assert pattern.search("REQ_p00001")

    def test_REQ_p00001_G_extracts_components(
        self, default_pattern_config: PatternConfig, default_ref_config: ReferenceConfig
    ) -> None:
        """Test pattern captures ID components."""
        pattern = build_id_pattern(default_pattern_config, default_ref_config)

        match = pattern.search("REQ-p00001-B")
        assert match
        assert match.group("type") == "p"
        assert match.group("number") == "00001"
        assert match.group("assertion") == "B"


class TestBuildCommentPattern:
    """Tests for build_comment_pattern function."""

    def test_REQ_p00001_A_implements_comment(
        self, default_pattern_config: PatternConfig, default_ref_config: ReferenceConfig
    ) -> None:
        """Test pattern matches # Implements: comment."""
        pattern = build_comment_pattern(default_pattern_config, default_ref_config, "implements")

        match = pattern.search("# Implements: REQ-p00001")
        assert match
        assert "REQ-p00001" in match.group("refs")

    def test_REQ_p00001_B_validates_comment(
        self, default_pattern_config: PatternConfig, default_ref_config: ReferenceConfig
    ) -> None:
        """Test pattern matches # Validates: comment."""
        pattern = build_comment_pattern(default_pattern_config, default_ref_config, "validates")

        assert pattern.search("# Validates: REQ-p00001")
        assert pattern.search("# Tests: REQ-p00001")

    def test_REQ_p00001_C_multiple_refs(
        self, default_pattern_config: PatternConfig, default_ref_config: ReferenceConfig
    ) -> None:
        """Test pattern captures multiple comma-separated refs."""
        pattern = build_comment_pattern(default_pattern_config, default_ref_config, "implements")

        match = pattern.search("# Implements: REQ-p00001, REQ-p00002")
        assert match
        refs = match.group("refs")
        assert "REQ-p00001" in refs
        assert "REQ-p00002" in refs

    def test_REQ_p00001_D_different_comment_styles(
        self, default_pattern_config: PatternConfig, default_ref_config: ReferenceConfig
    ) -> None:
        """Test pattern matches different comment styles."""
        pattern = build_comment_pattern(default_pattern_config, default_ref_config, "implements")

        assert pattern.search("# Implements: REQ-p00001")
        assert pattern.search("// Implements: REQ-p00001")
        assert pattern.search("-- Implements: REQ-p00001")

    def test_REQ_p00001_E_limited_comment_styles(
        self, default_pattern_config: PatternConfig
    ) -> None:
        """Test pattern respects configured comment styles."""
        ref_config = ReferenceConfig(comment_styles=["//"])
        pattern = build_comment_pattern(default_pattern_config, ref_config, "implements")

        assert pattern.search("// Implements: REQ-p00001")
        assert not pattern.search("# Implements: REQ-p00001")


class TestBuildBlockHeaderPattern:
    """Tests for build_block_header_pattern function."""

    def test_REQ_p00001_A_implements_header(self, default_ref_config: ReferenceConfig) -> None:
        """Test pattern matches IMPLEMENTS REQUIREMENTS: header."""
        pattern = build_block_header_pattern(default_ref_config, "implements")

        assert pattern.search("# IMPLEMENTS REQUIREMENTS:")
        assert pattern.search("// Implements Requirements")
        assert pattern.search("-- IMPLEMENTS REQUIREMENT:")

    def test_REQ_p00001_B_validates_header(self, default_ref_config: ReferenceConfig) -> None:
        """Test pattern matches TESTS REQUIREMENTS: header."""
        pattern = build_block_header_pattern(default_ref_config, "validates")

        assert pattern.search("# TESTS REQUIREMENTS:")
        assert pattern.search("// Tests Requirements")
        assert pattern.search("# VALIDATES REQUIREMENTS:")


class TestBuildBlockRefPattern:
    """Tests for build_block_ref_pattern function."""

    def test_REQ_p00001_A_block_ref(
        self, default_pattern_config: PatternConfig, default_ref_config: ReferenceConfig
    ) -> None:
        """Test pattern matches block reference line."""
        pattern = build_block_ref_pattern(default_pattern_config, default_ref_config)

        match = pattern.search("#   REQ-p00001")
        assert match
        assert match.group("ref") == "REQ-p00001"

    def test_REQ_p00001_B_block_ref_with_assertion(
        self, default_pattern_config: PatternConfig, default_ref_config: ReferenceConfig
    ) -> None:
        """Test pattern matches block reference with assertion."""
        pattern = build_block_ref_pattern(default_pattern_config, default_ref_config)

        match = pattern.search("//  REQ-p00001-A")
        assert match
        assert "REQ-p00001-A" in match.group("ref")


class TestExtractIdsFromText:
    """Tests for extract_ids_from_text function."""

    def test_REQ_p00001_A_single_id(
        self, default_pattern_config: PatternConfig, default_ref_config: ReferenceConfig
    ) -> None:
        """Test extracts single ID from text."""
        text = "This implements REQ-p00001 requirement"

        ids = extract_ids_from_text(text, default_pattern_config, default_ref_config)

        assert len(ids) == 1
        assert "REQ-p00001" in ids[0]

    def test_REQ_p00001_B_multiple_ids(
        self, default_pattern_config: PatternConfig, default_ref_config: ReferenceConfig
    ) -> None:
        """Test extracts multiple IDs from text."""
        text = "Implements REQ-p00001 and REQ-p00002-A"

        ids = extract_ids_from_text(text, default_pattern_config, default_ref_config)

        assert len(ids) == 2

    def test_REQ_p00001_C_no_ids(
        self, default_pattern_config: PatternConfig, default_ref_config: ReferenceConfig
    ) -> None:
        """Test returns empty list when no IDs found."""
        text = "This is just regular text"

        ids = extract_ids_from_text(text, default_pattern_config, default_ref_config)

        assert ids == []


class TestNormalizeExtractedId:
    """Tests for normalize_extracted_id function."""

    def test_REQ_p00001_A_basic_normalization(
        self, default_pattern_config: PatternConfig, default_ref_config: ReferenceConfig
    ) -> None:
        """Test normalizes ID to canonical format."""
        pattern = build_id_pattern(default_pattern_config, default_ref_config)
        match = pattern.search("REQ_p00001")

        normalized = normalize_extracted_id(match, default_pattern_config, default_ref_config)

        assert normalized == "REQ-p00001"

    def test_REQ_p00001_B_with_assertion(
        self, default_pattern_config: PatternConfig, default_ref_config: ReferenceConfig
    ) -> None:
        """Test normalizes ID with assertion."""
        pattern = build_id_pattern(default_pattern_config, default_ref_config)
        match = pattern.search("REQ_p00001_a")

        normalized = normalize_extracted_id(match, default_pattern_config, default_ref_config)

        assert normalized == "REQ-p00001-A"
