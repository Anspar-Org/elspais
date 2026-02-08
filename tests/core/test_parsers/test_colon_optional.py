"""Tests for colon-optional comment pattern parsing.

Verifies that build_comment_pattern() from reference_config.py accepts
both `# Implements: REQ-p00001` (colon present) and `# Implements REQ-p00001`
(colon absent) across all keyword types and comment styles.

This covers the change from ``:?\\s+`` in the pattern builder that makes
the colon after keywords optional while still requiring whitespace.
"""

import pytest

from elspais.utilities.patterns import PatternConfig
from elspais.utilities.reference_config import (
    ReferenceConfig,
    build_comment_pattern,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

# Standard HHT-like PatternConfig used across all tests
_HHT_PATTERN_CONFIG = PatternConfig.from_dict(
    {
        "prefix": "REQ",
        "types": {
            "prd": {"id": "p", "name": "PRD"},
            "ops": {"id": "o", "name": "OPS"},
            "dev": {"id": "d", "name": "DEV"},
        },
        "id_format": {"style": "numeric", "digits": 5},
    }
)

_DEFAULT_REF_CONFIG = ReferenceConfig()


@pytest.fixture
def pattern_config():
    return _HHT_PATTERN_CONFIG


@pytest.fixture
def ref_config():
    return _DEFAULT_REF_CONFIG


# ---------------------------------------------------------------------------
# 1. Colon present - Implements (existing behavior)
# ---------------------------------------------------------------------------


class TestColonPresentImplements:
    """Colon present with Implements keyword -- existing behaviour must not regress."""

    def test_colon_present_implements_hash_comment(self, pattern_config, ref_config):
        """# Implements: REQ-p00001 -- the classic pattern must still match."""
        pat = build_comment_pattern(pattern_config, ref_config, keyword_type="implements")
        m = pat.search("# Implements: REQ-p00001")
        assert m is not None
        assert "REQ-p00001" in m.group("refs")

    def test_colon_present_implements_slash_comment(self, pattern_config, ref_config):
        """// Implements: REQ-p00001 -- slash-slash style."""
        pat = build_comment_pattern(pattern_config, ref_config, keyword_type="implements")
        m = pat.search("// Implements: REQ-p00001")
        assert m is not None
        assert "REQ-p00001" in m.group("refs")

    def test_colon_present_implements_dash_comment(self, pattern_config, ref_config):
        """-- Implements: REQ-p00001 -- double-dash style."""
        pat = build_comment_pattern(pattern_config, ref_config, keyword_type="implements")
        m = pat.search("-- Implements: REQ-p00001")
        assert m is not None
        assert "REQ-p00001" in m.group("refs")


# ---------------------------------------------------------------------------
# 2. Colon absent - Implements (NEW behavior)
# ---------------------------------------------------------------------------


class TestColonAbsentImplements:
    """Colon absent with Implements keyword -- new optional-colon support."""

    def test_colon_absent_implements_hash_comment(self, pattern_config, ref_config):
        """# Implements REQ-p00001 -- colon omitted, space only."""
        pat = build_comment_pattern(pattern_config, ref_config, keyword_type="implements")
        m = pat.search("# Implements REQ-p00001")
        assert m is not None
        assert "REQ-p00001" in m.group("refs")

    def test_colon_absent_implements_slash_comment(self, pattern_config, ref_config):
        """// Implements REQ-p00001 -- colon omitted, slash-slash."""
        pat = build_comment_pattern(pattern_config, ref_config, keyword_type="implements")
        m = pat.search("// Implements REQ-p00001")
        assert m is not None
        assert "REQ-p00001" in m.group("refs")

    def test_colon_absent_implements_dash_comment(self, pattern_config, ref_config):
        """-- Implements REQ-p00001 -- colon omitted, double-dash."""
        pat = build_comment_pattern(pattern_config, ref_config, keyword_type="implements")
        m = pat.search("-- Implements REQ-p00001")
        assert m is not None
        assert "REQ-p00001" in m.group("refs")


# ---------------------------------------------------------------------------
# 3. Tests keyword with colon (NEW for TestParser, previously broken)
# ---------------------------------------------------------------------------


class TestColonPresentValidates:
    """Tests/Validates keywords with colon -- previously broken for TestParser."""

    def test_colon_present_tests_keyword(self, pattern_config, ref_config):
        """# Tests: REQ-p00001 -- colon present with 'Tests' keyword."""
        pat = build_comment_pattern(pattern_config, ref_config, keyword_type="validates")
        m = pat.search("# Tests: REQ-p00001")
        assert m is not None
        assert "REQ-p00001" in m.group("refs")

    def test_colon_present_validates_keyword(self, pattern_config, ref_config):
        """# Validates: REQ-p00001 -- colon present with 'Validates' keyword."""
        pat = build_comment_pattern(pattern_config, ref_config, keyword_type="validates")
        m = pat.search("# Validates: REQ-p00001")
        assert m is not None
        assert "REQ-p00001" in m.group("refs")


# ---------------------------------------------------------------------------
# 4. Tests keyword without colon (existing behavior)
# ---------------------------------------------------------------------------


class TestColonAbsentValidates:
    """Tests/Validates keywords without colon -- already worked."""

    def test_colon_absent_tests_keyword(self, pattern_config, ref_config):
        """# Tests REQ-p00001 -- colon absent (the way TestParser already worked)."""
        pat = build_comment_pattern(pattern_config, ref_config, keyword_type="validates")
        m = pat.search("# Tests REQ-p00001")
        assert m is not None
        assert "REQ-p00001" in m.group("refs")

    def test_colon_absent_validates_keyword(self, pattern_config, ref_config):
        """# Validates REQ-p00001 -- colon absent."""
        pat = build_comment_pattern(pattern_config, ref_config, keyword_type="validates")
        m = pat.search("# Validates REQ-p00001")
        assert m is not None
        assert "REQ-p00001" in m.group("refs")


# ---------------------------------------------------------------------------
# 5. Validates with // comment style, both colon variants
# ---------------------------------------------------------------------------


class TestSlashSlashValidates:
    """// Validates with and without colon."""

    def test_slash_validates_with_colon(self, pattern_config, ref_config):
        """// Validates: REQ-p00001 -- colon present."""
        pat = build_comment_pattern(pattern_config, ref_config, keyword_type="validates")
        m = pat.search("// Validates: REQ-p00001")
        assert m is not None
        assert "REQ-p00001" in m.group("refs")

    def test_slash_validates_without_colon(self, pattern_config, ref_config):
        """// Validates REQ-p00001 -- colon absent."""
        pat = build_comment_pattern(pattern_config, ref_config, keyword_type="validates")
        m = pat.search("// Validates REQ-p00001")
        assert m is not None
        assert "REQ-p00001" in m.group("refs")


# ---------------------------------------------------------------------------
# 6. Refines with -- comment style, both colon variants
# ---------------------------------------------------------------------------


class TestDoubleDashRefines:
    """-- Refines with and without colon."""

    def test_dash_refines_with_colon(self, pattern_config, ref_config):
        """-- Refines: REQ-p00001 -- colon present."""
        pat = build_comment_pattern(pattern_config, ref_config, keyword_type="refines")
        m = pat.search("-- Refines: REQ-p00001")
        assert m is not None
        assert "REQ-p00001" in m.group("refs")

    def test_dash_refines_without_colon(self, pattern_config, ref_config):
        """-- Refines REQ-p00001 -- colon absent."""
        pat = build_comment_pattern(pattern_config, ref_config, keyword_type="refines")
        m = pat.search("-- Refines REQ-p00001")
        assert m is not None
        assert "REQ-p00001" in m.group("refs")


# ---------------------------------------------------------------------------
# 7. No space = false positive guard
# ---------------------------------------------------------------------------


class TestFalsePositiveGuard:
    """No space between keyword and ID must NOT match."""

    def test_no_space_no_match_implements(self, pattern_config, ref_config):
        """#ImplementsREQ-p00001 -- must not match (no space)."""
        pat = build_comment_pattern(pattern_config, ref_config, keyword_type="implements")
        m = pat.search("#ImplementsREQ-p00001")
        assert m is None

    def test_no_space_no_match_validates(self, pattern_config, ref_config):
        """#TestsREQ-p00001 -- must not match (no space)."""
        pat = build_comment_pattern(pattern_config, ref_config, keyword_type="validates")
        m = pat.search("#TestsREQ-p00001")
        assert m is None

    def test_no_space_no_match_refines(self, pattern_config, ref_config):
        """#RefinesREQ-p00001 -- must not match (no space)."""
        pat = build_comment_pattern(pattern_config, ref_config, keyword_type="refines")
        m = pat.search("#RefinesREQ-p00001")
        assert m is None


# ---------------------------------------------------------------------------
# 8. Uppercase keywords
# ---------------------------------------------------------------------------


class TestUppercaseKeywords:
    """UPPERCASE keyword variants must match (case-insensitive by default)."""

    def test_uppercase_implements_with_colon(self, pattern_config, ref_config):
        """# IMPLEMENTS: REQ-p00001 -- uppercase keyword, colon present."""
        pat = build_comment_pattern(pattern_config, ref_config, keyword_type="implements")
        m = pat.search("# IMPLEMENTS: REQ-p00001")
        assert m is not None
        assert "REQ-p00001" in m.group("refs")

    def test_uppercase_implements_without_colon(self, pattern_config, ref_config):
        """# IMPLEMENTS REQ-p00001 -- uppercase keyword, colon absent."""
        pat = build_comment_pattern(pattern_config, ref_config, keyword_type="implements")
        m = pat.search("# IMPLEMENTS REQ-p00001")
        assert m is not None
        assert "REQ-p00001" in m.group("refs")

    def test_uppercase_tests_with_colon(self, pattern_config, ref_config):
        """# TESTS: REQ-p00001 -- uppercase keyword, colon present."""
        pat = build_comment_pattern(pattern_config, ref_config, keyword_type="validates")
        m = pat.search("# TESTS: REQ-p00001")
        assert m is not None
        assert "REQ-p00001" in m.group("refs")

    def test_uppercase_tests_without_colon(self, pattern_config, ref_config):
        """# TESTS REQ-p00001 -- uppercase keyword, colon absent."""
        pat = build_comment_pattern(pattern_config, ref_config, keyword_type="validates")
        m = pat.search("# TESTS REQ-p00001")
        assert m is not None
        assert "REQ-p00001" in m.group("refs")

    def test_uppercase_refines_with_colon(self, pattern_config, ref_config):
        """# REFINES: REQ-p00001 -- uppercase keyword, colon present."""
        pat = build_comment_pattern(pattern_config, ref_config, keyword_type="refines")
        m = pat.search("# REFINES: REQ-p00001")
        assert m is not None
        assert "REQ-p00001" in m.group("refs")

    def test_uppercase_refines_without_colon(self, pattern_config, ref_config):
        """# REFINES REQ-p00001 -- uppercase keyword, colon absent."""
        pat = build_comment_pattern(pattern_config, ref_config, keyword_type="refines")
        m = pat.search("# REFINES REQ-p00001")
        assert m is not None
        assert "REQ-p00001" in m.group("refs")


# ---------------------------------------------------------------------------
# 9. Multi-ref: comma-separated IDs, both colon variants
# ---------------------------------------------------------------------------


class TestMultiRefComma:
    """Comma-separated IDs with and without colon."""

    def test_multi_ref_with_colon(self, pattern_config, ref_config):
        """# Implements: REQ-p00001, REQ-p00002 -- multiple refs, colon present."""
        pat = build_comment_pattern(pattern_config, ref_config, keyword_type="implements")
        m = pat.search("# Implements: REQ-p00001, REQ-p00002")
        assert m is not None
        refs = m.group("refs")
        assert "REQ-p00001" in refs
        assert "REQ-p00002" in refs

    def test_multi_ref_without_colon(self, pattern_config, ref_config):
        """# Implements REQ-p00001, REQ-p00002 -- multiple refs, colon absent."""
        pat = build_comment_pattern(pattern_config, ref_config, keyword_type="implements")
        m = pat.search("# Implements REQ-p00001, REQ-p00002")
        assert m is not None
        refs = m.group("refs")
        assert "REQ-p00001" in refs
        assert "REQ-p00002" in refs

    def test_multi_ref_three_ids_with_colon(self, pattern_config, ref_config):
        """# Validates: REQ-p00001, REQ-p00002, REQ-d00003 -- three refs, colon."""
        pat = build_comment_pattern(pattern_config, ref_config, keyword_type="validates")
        m = pat.search("# Validates: REQ-p00001, REQ-p00002, REQ-d00003")
        assert m is not None
        refs = m.group("refs")
        assert "REQ-p00001" in refs
        assert "REQ-p00002" in refs
        assert "REQ-d00003" in refs

    def test_multi_ref_three_ids_without_colon(self, pattern_config, ref_config):
        """# Validates REQ-p00001, REQ-p00002, REQ-d00003 -- three refs, no colon."""
        pat = build_comment_pattern(pattern_config, ref_config, keyword_type="validates")
        m = pat.search("# Validates REQ-p00001, REQ-p00002, REQ-d00003")
        assert m is not None
        refs = m.group("refs")
        assert "REQ-p00001" in refs
        assert "REQ-p00002" in refs
        assert "REQ-d00003" in refs

    def test_multi_ref_with_assertion_labels(self, pattern_config, ref_config):
        """# Implements REQ-d00001-A, REQ-d00001-B -- assertion-level, no colon."""
        pat = build_comment_pattern(pattern_config, ref_config, keyword_type="implements")
        m = pat.search("# Implements REQ-d00001-A, REQ-d00001-B")
        assert m is not None
        refs = m.group("refs")
        assert "REQ-d00001-A" in refs
        assert "REQ-d00001-B" in refs
