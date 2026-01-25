"""
Tests for review position resolution.

Tests REQ-d00008: Position Resolution
"""

# =============================================================================
# Interface Tests (REQ-d00008-A)
# =============================================================================


# IMPLEMENTS: REQ-d00008-A
def test_resolve_position_interface():
    """resolve_position() SHALL resolve CommentPosition to document coordinates."""
    from elspais.trace_view.review.models import CommentPosition
    from elspais.trace_view.review.position import resolve_position

    content = """Line 1
Line 2
Line 3
Line 4
Line 5"""

    pos = CommentPosition.create_line("abcd1234", 3)

    resolved = resolve_position(pos, content, "abcd1234")

    assert resolved.lineNumber == 3
    assert resolved.originalPosition == pos


# =============================================================================
# Confidence Level Tests (REQ-d00008-B)
# =============================================================================


# IMPLEMENTS: REQ-d00008-B
def test_confidence_levels():
    """Resolution confidence levels SHALL be EXACT, APPROXIMATE, or UNANCHORED."""
    from elspais.trace_view.review.position import ResolutionConfidence

    assert ResolutionConfidence.EXACT.value == "exact"
    assert ResolutionConfidence.APPROXIMATE.value == "approximate"
    assert ResolutionConfidence.UNANCHORED.value == "unanchored"


# =============================================================================
# Hash Match Tests (REQ-d00008-C)
# =============================================================================


# IMPLEMENTS: REQ-d00008-C
def test_hash_match_exact():
    """When hash matches, resolution SHALL be EXACT using stored coordinates."""
    from elspais.trace_view.review.models import CommentPosition
    from elspais.trace_view.review.position import (
        ResolutionConfidence,
        resolve_position,
    )

    content = """Line 1
Line 2
Line 3"""

    # Hash matches
    pos = CommentPosition.create_line("match123", 2)
    resolved = resolve_position(pos, content, "match123")

    assert resolved.confidence == ResolutionConfidence.EXACT.value
    assert resolved.lineNumber == 2
    assert resolved.resolutionPath == "hash_match"


# =============================================================================
# Hash Mismatch Fallback Tests (REQ-d00008-D)
# =============================================================================


# IMPLEMENTS: REQ-d00008-D
def test_hash_mismatch_fallback():
    """When hash differs, fallback resolution SHALL yield APPROXIMATE confidence."""
    from elspais.trace_view.review.models import CommentPosition
    from elspais.trace_view.review.position import (
        ResolutionConfidence,
        resolve_position,
    )

    content = """Line 1
Line 2
Line 3"""

    # Hash doesn't match, but line number is valid
    pos = CommentPosition.create_line("oldHash1", 2)
    resolved = resolve_position(pos, content, "newHash2")

    assert resolved.confidence == ResolutionConfidence.APPROXIMATE.value
    assert "fallback" in resolved.resolutionPath


# =============================================================================
# Line Position Fallback Tests (REQ-d00008-E)
# =============================================================================


# IMPLEMENTS: REQ-d00008-E
def test_line_position_fallback():
    """For LINE positions with hash mismatch, SHALL search for fallbackContext."""
    from elspais.trace_view.review.models import CommentPosition
    from elspais.trace_view.review.position import (
        ResolutionConfidence,
        resolve_position,
    )

    content = """First line
the system SHALL authenticate users
Third line"""

    # Create position with context
    pos = CommentPosition.create_line(
        "oldHash1",
        line_number=100,  # Invalid line number
        context="system SHALL authenticate",  # But valid context
    )

    resolved = resolve_position(pos, content, "newHash2")

    # Should find via context
    assert resolved.confidence == ResolutionConfidence.APPROXIMATE.value
    assert resolved.resolutionPath == "fallback_context"
    assert resolved.lineNumber == 2


# =============================================================================
# Block Position Fallback Tests (REQ-d00008-F)
# =============================================================================


# IMPLEMENTS: REQ-d00008-F
def test_block_position_fallback():
    """For BLOCK positions with hash mismatch, SHALL search for context."""
    from elspais.trace_view.review.models import CommentPosition
    from elspais.trace_view.review.position import (
        ResolutionConfidence,
        resolve_position,
    )

    content = """Line 1
Line 2
Line 3
Line 4
Line 5"""

    # Block position with matching hash
    pos = CommentPosition.create_block("hash1234", 2, 4)
    resolved = resolve_position(pos, content, "hash1234")

    assert resolved.confidence == ResolutionConfidence.EXACT.value
    assert resolved.lineRange == (2, 4)


# =============================================================================
# Word Position Occurrence Tests (REQ-d00008-G)
# =============================================================================


# IMPLEMENTS: REQ-d00008-G
def test_word_position_occurrence():
    """For WORD positions, SHALL find the Nth occurrence based on keywordOccurrence."""
    from elspais.trace_view.review.models import CommentPosition
    from elspais.trace_view.review.position import (
        ResolutionConfidence,
        resolve_position,
    )

    content = """First SHALL
Second SHALL
Third SHALL"""

    # Find the second occurrence of "SHALL"
    pos = CommentPosition.create_word("hash1234", "SHALL", occurrence=2)
    resolved = resolve_position(pos, content, "hash1234")

    assert resolved.confidence == ResolutionConfidence.EXACT.value
    assert resolved.matchedText == "SHALL"
    assert resolved.lineNumber == 2  # Second line


def test_word_position_first_occurrence():
    """Word position with occurrence=1 should find first occurrence."""
    from elspais.trace_view.review.models import CommentPosition
    from elspais.trace_view.review.position import resolve_position

    content = "The system SHALL validate. Another SHALL exists."

    pos = CommentPosition.create_word("hash1234", "SHALL", occurrence=1)
    resolved = resolve_position(pos, content, "hash1234")

    assert resolved.matchedText == "SHALL"
    # Character offset should be at first SHALL
    assert resolved.charRange[0] == content.find("SHALL")


# =============================================================================
# General Position Tests (REQ-d00008-H)
# =============================================================================


# IMPLEMENTS: REQ-d00008-H
def test_general_position_exact():
    """GENERAL positions SHALL always resolve with EXACT confidence."""
    from elspais.trace_view.review.models import CommentPosition
    from elspais.trace_view.review.position import (
        ResolutionConfidence,
        resolve_position,
    )

    content = """Multi
line
content"""

    # General position - even with hash mismatch, should be EXACT
    pos = CommentPosition.create_general("oldHash1")
    resolved = resolve_position(pos, content, "newHash2")

    # GENERAL is always EXACT since it applies to the whole REQ
    assert resolved.confidence == ResolutionConfidence.EXACT.value
    assert resolved.lineRange == (1, 3)  # Covers entire content


# =============================================================================
# Resolution Path Tests (REQ-d00008-I)
# =============================================================================


# IMPLEMENTS: REQ-d00008-I
def test_resolution_path_tracking():
    """ResolvedPosition SHALL include resolutionPath describing fallback strategy."""
    from elspais.trace_view.review.models import CommentPosition
    from elspais.trace_view.review.position import resolve_position

    content = "Line 1\nLine 2\nLine 3"

    # Hash match path
    pos1 = CommentPosition.create_line("match123", 2)
    resolved1 = resolve_position(pos1, content, "match123")
    assert resolved1.resolutionPath == "hash_match"

    # Fallback line number path
    pos2 = CommentPosition.create_line("oldHash1", 2)
    resolved2 = resolve_position(pos2, content, "newHash2")
    assert "fallback" in resolved2.resolutionPath

    # Context fallback path
    pos3 = CommentPosition.create_line("oldHash1", 999, context="Line 2")
    resolved3 = resolve_position(pos3, content, "newHash2")
    assert resolved3.resolutionPath == "fallback_context"


# =============================================================================
# Unanchored Fallback Tests (REQ-d00008-J)
# =============================================================================


# IMPLEMENTS: REQ-d00008-J
def test_unanchored_fallback():
    """When no fallback succeeds, SHALL resolve as UNANCHORED."""
    from elspais.trace_view.review.models import CommentPosition
    from elspais.trace_view.review.position import (
        ResolutionConfidence,
        resolve_position,
    )

    content = "Line 1\nLine 2\nLine 3"

    # Create position with invalid line and no matching context
    pos = CommentPosition.create_line(
        "oldHash1", line_number=999, context="nonexistent context"  # Invalid  # Won't match
    )

    resolved = resolve_position(pos, content, "newHash2")

    assert resolved.confidence == ResolutionConfidence.UNANCHORED.value
    assert resolved.resolutionPath == "fallback_exhausted"
    # Original position should be preserved
    assert resolved.originalPosition == pos


# =============================================================================
# Helper Function Tests
# =============================================================================


def test_find_line_in_text():
    """Test line finding helper function."""
    from elspais.trace_view.review.position import find_line_in_text

    content = "Line 1\nLine 2\nLine 3"

    # Find line 2
    result = find_line_in_text(content, 2)
    assert result is not None
    start, end = result
    assert content[start:end] == "Line 2"

    # Line 1
    result = find_line_in_text(content, 1)
    assert result is not None
    assert content[result[0] : result[1]] == "Line 1"

    # Line 3
    result = find_line_in_text(content, 3)
    assert result is not None
    assert content[result[0] : result[1]] == "Line 3"

    # Invalid line
    result = find_line_in_text(content, 99)
    assert result is None


def test_find_context_in_text():
    """Test context finding helper function."""
    from elspais.trace_view.review.position import find_context_in_text

    content = "The system SHALL validate input."

    result = find_context_in_text(content, "SHALL validate")
    assert result is not None
    start, end = result
    assert content[start:end] == "SHALL validate"

    # Not found
    result = find_context_in_text(content, "nonexistent")
    assert result is None


def test_find_keyword_occurrence():
    """Test keyword occurrence finding."""
    from elspais.trace_view.review.position import find_keyword_occurrence

    content = "SHALL do A. SHALL do B. SHALL do C."

    # First occurrence
    result = find_keyword_occurrence(content, "SHALL", 1)
    assert result is not None
    assert result[0] == 0

    # Second occurrence
    result = find_keyword_occurrence(content, "SHALL", 2)
    assert result is not None
    assert content[result[0] : result[1]] == "SHALL"

    # Third occurrence
    result = find_keyword_occurrence(content, "SHALL", 3)
    assert result is not None

    # Fourth occurrence - doesn't exist
    result = find_keyword_occurrence(content, "SHALL", 4)
    assert result is None


def test_get_line_number_from_char_offset():
    """Test character offset to line number conversion."""
    from elspais.trace_view.review.position import get_line_number_from_char_offset

    content = "Line 1\nLine 2\nLine 3"

    # Beginning of content
    assert get_line_number_from_char_offset(content, 0) == 1

    # In line 1
    assert get_line_number_from_char_offset(content, 3) == 1

    # In line 2 (after first newline at index 6)
    assert get_line_number_from_char_offset(content, 8) == 2

    # In line 3
    assert get_line_number_from_char_offset(content, 15) == 3


def test_get_total_lines():
    """Test total line counting."""
    from elspais.trace_view.review.position import get_total_lines

    assert get_total_lines("") == 0
    assert get_total_lines("one line") == 1
    assert get_total_lines("line1\nline2") == 2
    assert get_total_lines("line1\nline2\nline3") == 3


def test_empty_content_handling():
    """Test position resolution with empty content."""
    from elspais.trace_view.review.models import CommentPosition
    from elspais.trace_view.review.position import (
        ResolutionConfidence,
        resolve_position,
    )

    pos = CommentPosition.create_line("hash1234", 1)

    resolved = resolve_position(pos, "", "hash1234")

    assert resolved.confidence == ResolutionConfidence.UNANCHORED.value


def test_resolved_position_to_dict():
    """Test ResolvedPosition serialization."""
    from elspais.trace_view.review.models import CommentPosition
    from elspais.trace_view.review.position import ResolvedPosition

    original = CommentPosition.create_line("hash1234", 5)

    resolved = ResolvedPosition(
        type="line",
        confidence="exact",
        lineNumber=5,
        lineRange=(5, 5),
        charRange=(10, 20),
        matchedText="test line",
        originalPosition=original,
        resolutionPath="hash_match",
    )

    d = resolved.to_dict()

    assert d["type"] == "line"
    assert d["confidence"] == "exact"
    assert d["lineNumber"] == 5
    assert d["lineRange"] == [5, 5]
    assert d["charRange"] == [10, 20]
    assert d["resolutionPath"] == "hash_match"
    assert "originalPosition" in d


def test_resolved_position_from_dict():
    """Test ResolvedPosition deserialization."""
    from elspais.trace_view.review.position import ResolvedPosition

    data = {
        "type": "line",
        "confidence": "exact",
        "lineNumber": 5,
        "lineRange": [5, 5],
        "charRange": [10, 20],
        "matchedText": "test",
        "originalPosition": {
            "type": "line",
            "hashWhenCreated": "hash1234",
            "lineNumber": 5,
        },
        "resolutionPath": "hash_match",
    }

    resolved = ResolvedPosition.from_dict(data)

    assert resolved.type == "line"
    assert resolved.confidence == "exact"
    assert resolved.lineNumber == 5
    assert resolved.lineRange == (5, 5)
    assert resolved.charRange == (10, 20)
