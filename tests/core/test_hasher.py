# Validates: REQ-p00001-C, REQ-p00004-A
"""Tests for hasher.py - Content hashing utilities."""

import pytest

from elspais.utilities.hasher import (
    calculate_hash,
    clean_requirement_body,
    compute_normalized_hash,
    extract_hash_from_footer,
    normalize_assertion_text,
    verify_hash,
)


class TestCleanRequirementBody:
    """Tests for clean_requirement_body function."""

    def test_removes_trailing_blank_lines(self):
        content = "Line 1\nLine 2\n\n\n"
        cleaned = clean_requirement_body(content)
        assert cleaned == "Line 1\nLine 2"

    def test_preserves_internal_blank_lines(self):
        content = "Line 1\n\nLine 2"
        cleaned = clean_requirement_body(content)
        assert cleaned == "Line 1\n\nLine 2"

    def test_normalize_whitespace_removes_leading_blanks(self):
        content = "\n\nLine 1\nLine 2"
        cleaned = clean_requirement_body(content, normalize_whitespace=True)
        assert cleaned == "Line 1\nLine 2"

    def test_normalize_whitespace_collapses_multiple_blanks(self):
        content = "Line 1\n\n\n\nLine 2"
        cleaned = clean_requirement_body(content, normalize_whitespace=True)
        assert cleaned == "Line 1\n\nLine 2"


class TestCalculateHash:
    """Tests for calculate_hash function."""

    def test_default_sha256_8chars(self):
        content = "Test content"
        hash_val = calculate_hash(content)
        assert len(hash_val) == 8
        assert all(c in "0123456789abcdef" for c in hash_val)

    def test_custom_length(self):
        content = "Test content"
        hash_val = calculate_hash(content, length=16)
        assert len(hash_val) == 16

    def test_deterministic(self):
        content = "Test content"
        hash1 = calculate_hash(content)
        hash2 = calculate_hash(content)
        assert hash1 == hash2

    def test_different_content_different_hash(self):
        hash1 = calculate_hash("Content A")
        hash2 = calculate_hash("Content B")
        assert hash1 != hash2

    def test_sha1_algorithm(self):
        content = "Test content"
        hash_val = calculate_hash(content, algorithm="sha1")
        assert len(hash_val) == 8

    def test_md5_algorithm(self):
        content = "Test content"
        hash_val = calculate_hash(content, algorithm="md5")
        assert len(hash_val) == 8

    def test_invalid_algorithm_raises(self):
        with pytest.raises(ValueError, match="Unsupported hash algorithm"):
            calculate_hash("content", algorithm="invalid")


class TestVerifyHash:
    """Tests for verify_hash function."""

    def test_matching_hash_returns_true(self):
        content = "Test content"
        hash_val = calculate_hash(content)
        assert verify_hash(content, hash_val) is True

    def test_non_matching_hash_returns_false(self):
        content = "Test content"
        assert verify_hash(content, "00000000") is False

    def test_case_insensitive(self):
        content = "Test content"
        hash_val = calculate_hash(content)
        assert verify_hash(content, hash_val.upper()) is True


class TestExtractHashFromFooter:
    """Tests for extract_hash_from_footer function."""

    def test_extracts_hash(self):
        footer = "**Hash**: abc12345"
        assert extract_hash_from_footer(footer) == "abc12345"

    def test_extracts_hash_with_extra_text(self):
        footer = "Some text **Hash**: abc12345 more text"
        assert extract_hash_from_footer(footer) == "abc12345"

    def test_returns_none_when_no_hash(self):
        footer = "No hash here"
        assert extract_hash_from_footer(footer) is None

    def test_handles_uppercase_hash(self):
        footer = "**Hash**: ABC12345"
        assert extract_hash_from_footer(footer) == "ABC12345"


class TestNormalizeAssertionText:
    """Tests for normalize_assertion_text function (normalized-text hash mode)."""

    def test_hash_mode_trailing_whitespace_stripped(self):
        """Trailing whitespace is stripped from assertion text."""
        result = normalize_assertion_text("A", "text   ")
        assert result == "A. text"

    def test_hash_mode_multiline_collapsed(self):
        """Multiline text is collapsed into a single line."""
        result = normalize_assertion_text("A", "text\nacross lines")
        assert result == "A. text across lines"

    def test_hash_mode_multiple_spaces_collapsed(self):
        """Multiple internal spaces are collapsed to a single space."""
        result = normalize_assertion_text("A", "text  with   spaces")
        assert result == "A. text with spaces"

    def test_hash_mode_crlf_normalized(self):
        """Windows-style \\r\\n line endings are normalized."""
        result = normalize_assertion_text("A", "text\r\nmore")
        assert result == "A. text more"

    def test_hash_mode_combined_normalizations(self):
        """All normalizations apply simultaneously."""
        result = normalize_assertion_text("A", "text  \r\nacross   lines\n  trailing   ")
        assert result == "A. text across lines trailing"

    def test_hash_mode_label_included(self):
        """Label is prefixed as 'LABEL. text' format."""
        result = normalize_assertion_text("A", "foo")
        assert result == "A. foo"

    def test_hash_mode_label_with_number(self):
        """Numeric labels work correctly."""
        result = normalize_assertion_text("A1", "some text")
        assert result == "A1. some text"

    def test_hash_mode_leading_whitespace_stripped(self):
        """Leading whitespace is stripped from assertion text."""
        result = normalize_assertion_text("A", "   leading spaces")
        assert result == "A. leading spaces"

    def test_hash_mode_bare_cr_normalized(self):
        """Bare \\r (old Mac style) line endings are normalized."""
        result = normalize_assertion_text("A", "text\rmore")
        assert result == "A. text more"


class TestComputeNormalizedHash:
    """Tests for compute_normalized_hash function (normalized-text hash mode)."""

    def test_hash_mode_returns_8_char_hex(self):
        """Returns an 8-character hexadecimal hash string."""
        result = compute_normalized_hash([("A", "The system SHALL validate.")])
        assert len(result) == 8
        assert all(c in "0123456789abcdef" for c in result)

    def test_hash_mode_same_content_same_hash(self):
        """Identical assertion content produces identical hashes."""
        assertions = [("A", "The system SHALL validate.")]
        hash1 = compute_normalized_hash(assertions)
        hash2 = compute_normalized_hash(assertions)
        assert hash1 == hash2

    def test_hash_mode_different_content_different_hash(self):
        """Different assertion text produces different hashes."""
        hash1 = compute_normalized_hash([("A", "The system SHALL validate.")])
        hash2 = compute_normalized_hash([("A", "The system SHALL reject.")])
        assert hash1 != hash2

    def test_hash_mode_order_matters(self):
        """Assertion order affects the hash: [A, B] != [B, A]."""
        hash1 = compute_normalized_hash(
            [
                ("A", "First assertion."),
                ("B", "Second assertion."),
            ]
        )
        hash2 = compute_normalized_hash(
            [
                ("B", "Second assertion."),
                ("A", "First assertion."),
            ]
        )
        assert hash1 != hash2

    def test_hash_mode_case_sensitive(self):
        """Hash is case sensitive: 'SHALL' != 'shall'."""
        hash1 = compute_normalized_hash([("A", "The system SHALL validate.")])
        hash2 = compute_normalized_hash([("A", "The system shall validate.")])
        assert hash1 != hash2

    def test_hash_mode_invariant_over_trailing_whitespace(self):
        """Trailing whitespace does not affect the hash."""
        hash1 = compute_normalized_hash([("A", "The system SHALL validate.")])
        hash2 = compute_normalized_hash([("A", "The system SHALL validate.   ")])
        assert hash1 == hash2

    def test_hash_mode_invariant_over_multiline_vs_single_line(self):
        """Multiline and single-line versions of the same text produce same hash."""
        hash1 = compute_normalized_hash([("A", "The system SHALL\nvalidate input.")])
        hash2 = compute_normalized_hash([("A", "The system SHALL validate input.")])
        assert hash1 == hash2

    def test_hash_mode_invariant_over_multiple_spaces(self):
        """Multiple internal spaces do not affect the hash."""
        hash1 = compute_normalized_hash([("A", "The system  SHALL   validate.")])
        hash2 = compute_normalized_hash([("A", "The system SHALL validate.")])
        assert hash1 == hash2

    def test_hash_mode_empty_assertions_returns_valid_hash(self):
        """Empty assertions list returns a valid hash (hash of empty string)."""
        result = compute_normalized_hash([])
        assert len(result) == 8
        assert all(c in "0123456789abcdef" for c in result)
        # Should be the hash of an empty string
        expected = calculate_hash("")
        assert result == expected

    def test_hash_mode_multiple_assertions(self):
        """Multiple assertions produce a deterministic hash."""
        assertions = [
            ("A", "First assertion."),
            ("B", "Second assertion."),
            ("C", "Third assertion."),
        ]
        hash1 = compute_normalized_hash(assertions)
        hash2 = compute_normalized_hash(assertions)
        assert hash1 == hash2

    def test_hash_mode_custom_length(self):
        """Custom hash length is respected."""
        result = compute_normalized_hash(
            [("A", "text")],
            length=16,
        )
        assert len(result) == 16
