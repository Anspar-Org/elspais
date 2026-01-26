"""Tests for hasher.py - Content hashing utilities."""

import pytest

from elspais.arch3.utilities.hasher import (
    calculate_hash,
    clean_requirement_body,
    extract_hash_from_footer,
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
