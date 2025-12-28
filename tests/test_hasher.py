"""
Tests for elspais.core.hasher module.
"""

import pytest


class TestHashCalculation:
    """Tests for hash calculation functions."""

    def test_calculate_hash(self):
        """Test basic hash calculation."""
        from elspais.core.hasher import calculate_hash

        content = "The system SHALL authenticate users."
        hash_value = calculate_hash(content)

        assert len(hash_value) == 8  # Default length
        assert hash_value.isalnum()

    def test_calculate_hash_deterministic(self):
        """Test hash is deterministic for same content."""
        from elspais.core.hasher import calculate_hash

        content = "The system SHALL do something."
        hash1 = calculate_hash(content)
        hash2 = calculate_hash(content)

        assert hash1 == hash2

    def test_calculate_hash_different_content(self):
        """Test different content produces different hash."""
        from elspais.core.hasher import calculate_hash

        hash1 = calculate_hash("Content A")
        hash2 = calculate_hash("Content B")

        assert hash1 != hash2

    def test_calculate_hash_custom_length(self):
        """Test hash with custom length."""
        from elspais.core.hasher import calculate_hash

        content = "Test content"
        hash_16 = calculate_hash(content, length=16)
        hash_4 = calculate_hash(content, length=4)

        assert len(hash_16) == 16
        assert len(hash_4) == 4
        # Shorter hash should be prefix of longer
        assert hash_16.startswith(hash_4)

    def test_calculate_hash_trailing_lines_normalized(self):
        """Test hash ignores trailing blank lines (hht-diary compatible)."""
        from elspais.core.hasher import calculate_hash

        # Only trailing blank lines are removed - matches hht-diary behavior
        content1 = "The system SHALL do something."
        content2 = "The system SHALL do something.\n"  # Extra newline (removed)
        content3 = "The system SHALL do something.\n\n"  # Multiple trailing newlines (removed)
        content4 = "The system SHALL do something.\n\n\n"  # More trailing newlines (removed)

        hash1 = calculate_hash(content1)
        hash2 = calculate_hash(content2)
        hash3 = calculate_hash(content3)
        hash4 = calculate_hash(content4)

        # All should produce same hash - trailing blank lines are removed
        assert hash1 == hash2 == hash3 == hash4

    def test_calculate_hash_inline_whitespace_matters(self):
        """Test hash distinguishes inline whitespace (hht-diary compatible)."""
        from elspais.core.hasher import calculate_hash

        # Inline whitespace IS significant - not normalized
        content1 = "The system SHALL do something."
        content2 = "The system SHALL do something.  "  # Trailing spaces on line

        hash1 = calculate_hash(content1)
        hash2 = calculate_hash(content2)

        # Inline trailing spaces are significant - different hashes
        assert hash1 != hash2


class TestHashVerification:
    """Tests for hash verification functions."""

    def test_verify_hash_valid(self):
        """Test verification passes for correct hash."""
        from elspais.core.hasher import calculate_hash, verify_hash

        content = "The system SHALL authenticate."
        correct_hash = calculate_hash(content)

        assert verify_hash(content, correct_hash) is True

    def test_verify_hash_invalid(self):
        """Test verification fails for incorrect hash."""
        from elspais.core.hasher import verify_hash

        content = "The system SHALL authenticate."
        wrong_hash = "WRONGHSH"

        assert verify_hash(content, wrong_hash) is False

    def test_verify_hash_modified_content(self):
        """Test verification fails when content is modified."""
        from elspais.core.hasher import calculate_hash, verify_hash

        original_content = "The system SHALL authenticate."
        original_hash = calculate_hash(original_content)

        modified_content = "The system SHALL authenticate users."

        assert verify_hash(modified_content, original_hash) is False


class TestContentCleaning:
    """Tests for content cleaning before hashing."""

    def test_clean_requirement_body(self):
        """Test cleaning requirement body for hashing (hht-diary compatible)."""
        from elspais.core.hasher import clean_requirement_body

        # With trailing blank lines
        dirty = """
        The system SHALL do something.

        **Acceptance Criteria**:
        - Item 1
        - Item 2

        """

        clean = clean_requirement_body(dirty)

        # Only trailing blank lines are removed (hht-diary behavior)
        # Leading content and indentation are preserved
        assert clean.startswith("\n")  # Leading newline preserved
        assert "        The system" in clean  # Indentation preserved
        assert not clean.endswith("\n")  # Trailing blank lines removed
        assert clean.endswith("- Item 2")

    def test_clean_preserves_content(self):
        """Test cleaning preserves meaningful content."""
        from elspais.core.hasher import clean_requirement_body

        content = "The system SHALL authenticate users."
        clean = clean_requirement_body(content)

        assert "SHALL" in clean
        assert "authenticate" in clean
        assert "users" in clean

    def test_hash_ignores_trailing_blank_lines(self):
        """Test hash ignores trailing blank lines (hht-diary compatible)."""
        from elspais.core.hasher import calculate_hash

        # Only trailing blank lines are normalized
        format1 = "The system SHALL do X.\n\n**Criteria**:\n- A\n- B"
        format2 = "The system SHALL do X.\n\n**Criteria**:\n- A\n- B\n"
        format3 = "The system SHALL do X.\n\n**Criteria**:\n- A\n- B\n\n\n"

        hash1 = calculate_hash(format1)
        hash2 = calculate_hash(format2)
        hash3 = calculate_hash(format3)

        # Trailing blank lines don't affect hash
        assert hash1 == hash2 == hash3

    def test_hash_distinguishes_inline_formatting(self):
        """Test hash distinguishes inline whitespace (hht-diary compatible)."""
        from elspais.core.hasher import calculate_hash

        # Inline whitespace IS significant
        format1 = "The system SHALL do X.\n\n**Criteria**:\n- A\n- B"
        format2 = "The system SHALL do X.  \n\n**Criteria**:\n- A\n- B"  # Extra spaces

        hash1 = calculate_hash(format1)
        hash2 = calculate_hash(format2)

        # Inline spaces are significant - different hashes
        assert hash1 != hash2


class TestNormalizeWhitespaceOption:
    """Tests for the normalize_whitespace configuration option."""

    def test_normalize_whitespace_off_preserves_indentation(self):
        """Test default mode preserves indentation."""
        from elspais.core.hasher import clean_requirement_body

        content = "    indented line\n        more indented"
        clean = clean_requirement_body(content, normalize_whitespace=False)

        assert clean == "    indented line\n        more indented"

    def test_normalize_whitespace_on_strips_trailing_spaces(self):
        """Test normalize mode strips trailing spaces from lines."""
        from elspais.core.hasher import clean_requirement_body

        content = "line with spaces   \nanother line  "
        clean = clean_requirement_body(content, normalize_whitespace=True)

        assert "   " not in clean
        assert clean == "line with spaces\nanother line"

    def test_normalize_whitespace_on_collapses_blank_lines(self):
        """Test normalize mode collapses multiple blank lines."""
        from elspais.core.hasher import clean_requirement_body

        content = "line 1\n\n\n\nline 2"
        clean = clean_requirement_body(content, normalize_whitespace=True)

        assert clean == "line 1\n\nline 2"

    def test_normalize_whitespace_on_removes_leading_blanks(self):
        """Test normalize mode removes leading blank lines."""
        from elspais.core.hasher import clean_requirement_body

        content = "\n\n\nactual content"
        clean = clean_requirement_body(content, normalize_whitespace=True)

        assert clean == "actual content"

    def test_hash_with_normalize_whitespace_ignores_formatting(self):
        """Test hash with normalization ignores whitespace differences."""
        from elspais.core.hasher import calculate_hash

        # These should produce the same hash when normalized
        format1 = "The system SHALL do X.\n\n**Criteria**:\n- A\n- B"
        format2 = "The system SHALL do X.  \n\n**Criteria**:\n- A\n- B\n"
        format3 = "\n\nThe system SHALL do X.\n\n\n\n**Criteria**:\n- A\n- B\n\n\n"

        hash1 = calculate_hash(format1, normalize_whitespace=True)
        hash2 = calculate_hash(format2, normalize_whitespace=True)
        hash3 = calculate_hash(format3, normalize_whitespace=True)

        assert hash1 == hash2 == hash3

    def test_hash_default_vs_normalized_differs(self):
        """Test that default mode and normalized mode produce different hashes."""
        from elspais.core.hasher import calculate_hash

        content = "  indented\n\n\nmultiple blanks  "

        hash_default = calculate_hash(content, normalize_whitespace=False)
        hash_normalized = calculate_hash(content, normalize_whitespace=True)

        # Should differ because default preserves formatting
        assert hash_default != hash_normalized

    def test_verify_hash_with_normalize_whitespace(self):
        """Test verify_hash respects normalize_whitespace option."""
        from elspais.core.hasher import calculate_hash, verify_hash

        original = "  content  "
        hash_normalized = calculate_hash(original, normalize_whitespace=True)

        # Should verify with same setting
        assert verify_hash(original, hash_normalized, normalize_whitespace=True)

        # Should fail with different setting
        assert not verify_hash(original, hash_normalized, normalize_whitespace=False)
