"""
Tests for parser resilience - handling malformed input gracefully.

Uses TDD approach: these tests are written first, then implementation follows.
"""

import pytest
from pathlib import Path
from textwrap import dedent

from elspais.core.parser import RequirementParser
from elspais.core.patterns import PatternConfig
from elspais.core.models import ParseResult, ParseWarning
from elspais.config.defaults import DEFAULT_CONFIG


@pytest.fixture
def parser():
    """Create a parser with HHT-style config."""
    config = PatternConfig.from_dict(DEFAULT_CONFIG["patterns"])
    return RequirementParser(config)


class TestParseResult:
    """Tests for the new ParseResult API."""

    def test_parse_text_returns_parse_result(self, parser):
        """parse_text should return a ParseResult object."""
        text = dedent("""\
            # REQ-d00001: Test Feature

            **Level**: Dev | **Status**: Active

            Body content here.

            *End* *Test Feature* | **Hash**: abc12345
        """)

        result = parser.parse_text(text)

        assert isinstance(result, ParseResult), (
            f"Expected ParseResult, got {type(result).__name__}"
        )

    def test_parse_result_has_requirements(self, parser):
        """ParseResult should have requirements dict."""
        text = dedent("""\
            # REQ-d00001: Test Feature

            **Level**: Dev | **Status**: Active

            Body content.

            *End* *Test Feature* | **Hash**: abc12345
        """)

        result = parser.parse_text(text)

        assert hasattr(result, 'requirements')
        assert "REQ-d00001" in result.requirements

    def test_parse_result_has_warnings(self, parser):
        """ParseResult should have warnings list."""
        text = dedent("""\
            # REQ-d00001: Test Feature

            **Level**: Dev | **Status**: Active

            Body content.

            *End* *Test Feature* | **Hash**: abc12345
        """)

        result = parser.parse_text(text)

        assert hasattr(result, 'warnings')
        assert isinstance(result.warnings, list)

    def test_parse_result_subscript_access(self, parser):
        """ParseResult should support dict-like access."""
        text = dedent("""\
            # REQ-d00001: Test Feature

            **Level**: Dev | **Status**: Active

            Body content.

            *End* *Test Feature* | **Hash**: abc12345
        """)

        result = parser.parse_text(text)

        # Should work like result.requirements["REQ-d00001"]
        req = result["REQ-d00001"]
        assert req.title == "Test Feature"

    def test_parse_result_contains(self, parser):
        """ParseResult should support 'in' operator."""
        text = dedent("""\
            # REQ-d00001: Test Feature

            **Level**: Dev | **Status**: Active

            Body content.

            *End* *Test Feature* | **Hash**: abc12345
        """)

        result = parser.parse_text(text)

        assert "REQ-d00001" in result
        assert "REQ-d99999" not in result

    def test_parse_result_len(self, parser):
        """ParseResult should support len()."""
        text = dedent("""\
            # REQ-d00001: First

            **Level**: Dev | **Status**: Active

            First body.

            *End* *First* | **Hash**: 11111111
            ---

            # REQ-d00002: Second

            **Level**: Dev | **Status**: Active

            Second body.

            *End* *Second* | **Hash**: 22222222
        """)

        result = parser.parse_text(text)

        assert len(result) == 2


class TestParseWarning:
    """Tests for ParseWarning dataclass."""

    def test_parse_warning_has_required_fields(self):
        """ParseWarning should have requirement_id and message."""
        warning = ParseWarning(
            requirement_id="REQ-d00001",
            message="Test warning message",
        )

        assert warning.requirement_id == "REQ-d00001"
        assert warning.message == "Test warning message"

    def test_parse_warning_has_optional_location(self):
        """ParseWarning should support optional file_path and line_number."""
        warning = ParseWarning(
            requirement_id="REQ-d00001",
            message="Test warning",
            file_path=Path("/test/file.md"),
            line_number=42,
        )

        assert warning.file_path == Path("/test/file.md")
        assert warning.line_number == 42


class TestBodyExtraction:
    """Tests for body extraction resilience."""

    def test_body_extracted_with_metadata(self, parser):
        """Body should be extracted correctly when metadata is present."""
        text = dedent("""\
            # REQ-d00001: Test Feature

            **Level**: Dev | **Status**: Active

            This is the body content.
            It has multiple lines.

            *End* *Test Feature* | **Hash**: abc12345
        """)

        result = parser.parse_text(text)
        req = result["REQ-d00001"]

        assert "This is the body content" in req.body
        assert "multiple lines" in req.body

    def test_body_extracted_without_metadata(self, parser):
        """Body should be extracted even when Level/Status line is missing."""
        text = dedent("""\
            # REQ-d00001: Test Feature

            This is the body content without metadata.
            It should still be captured.

            *End* *Test Feature* | **Hash**: abc12345
        """)

        result = parser.parse_text(text)
        req = result["REQ-d00001"]

        assert "body content without metadata" in req.body, (
            f"Body should contain content even without metadata. Got: '{req.body}'"
        )

    def test_body_extracted_with_only_assertions(self, parser):
        """Body should include assertions section when no other metadata."""
        text = dedent("""\
            # REQ-d00001: Test Feature

            ## Assertions

            A. The system SHALL do something.
            B. The system SHALL do another thing.

            *End* *Test Feature* | **Hash**: abc12345
        """)

        result = parser.parse_text(text)
        req = result["REQ-d00001"]

        assert "Assertions" in req.body or len(req.assertions) > 0, (
            f"Should capture assertions content. Body: '{req.body}', Assertions: {req.assertions}"
        )


class TestDuplicateIds:
    """Tests for duplicate ID detection."""

    def test_duplicate_id_keeps_first(self, parser):
        """When duplicate IDs exist, keep the first occurrence."""
        text = dedent("""\
            # REQ-d00001: First Occurrence

            **Level**: Dev | **Status**: Active

            First body content.

            *End* *First Occurrence* | **Hash**: 11111111
            ---

            # REQ-d00001: Second Occurrence

            **Level**: Dev | **Status**: Draft

            Second body content.

            *End* *Second Occurrence* | **Hash**: 22222222
        """)

        result = parser.parse_text(text)

        # Should keep first occurrence
        req = result["REQ-d00001"]
        assert req.title == "First Occurrence", (
            f"Should keep first occurrence. Got title: '{req.title}'"
        )
        assert "First body" in req.body

    def test_duplicate_id_generates_warning(self, parser):
        """When duplicate IDs exist, generate a warning."""
        text = dedent("""\
            # REQ-d00001: First Occurrence

            **Level**: Dev | **Status**: Active

            First body.

            *End* *First Occurrence* | **Hash**: 11111111
            ---

            # REQ-d00001: Second Occurrence

            **Level**: Dev | **Status**: Draft

            Second body.

            *End* *Second Occurrence* | **Hash**: 22222222
        """)

        result = parser.parse_text(text)

        # Should have a warning about duplicate
        assert len(result.warnings) > 0, "Should have warning for duplicate ID"

        duplicate_warnings = [w for w in result.warnings if "duplicate" in w.message.lower()]
        assert len(duplicate_warnings) > 0, (
            f"Should have warning mentioning 'duplicate'. Warnings: {result.warnings}"
        )


class TestImplementsValidation:
    """Tests for implements reference validation."""

    def test_valid_implements_accepted(self, parser):
        """Valid implements references should be accepted without warning."""
        text = dedent("""\
            # REQ-d00001: Test Feature

            **Level**: Dev | **Status**: Active | **Implements**: REQ-p00001

            Body content.

            *End* *Test Feature* | **Hash**: abc12345
        """)

        result = parser.parse_text(text)
        req = result["REQ-d00001"]

        # REQ-p00001 is valid format, should be in implements
        assert "REQ-p00001" in req.implements or "p00001" in req.implements

    def test_invalid_implements_generates_warning(self, parser):
        """Invalid implements references should generate warnings."""
        text = dedent("""\
            # REQ-d00001: Test Feature

            **Level**: Dev | **Status**: Active | **Implements**: INVALID-REF, REQ-p00001

            Body content.

            *End* *Test Feature* | **Hash**: abc12345
        """)

        result = parser.parse_text(text)

        # Should have warning about invalid reference
        invalid_warnings = [
            w for w in result.warnings
            if "invalid" in w.message.lower() or "INVALID-REF" in w.message
        ]
        assert len(invalid_warnings) > 0, (
            f"Should warn about invalid implements ref. Warnings: {result.warnings}"
        )


class TestAssertionLabels:
    """Tests for assertion label validation."""

    def test_valid_assertion_labels_accepted(self, parser):
        """Valid assertion labels (A-Z) should be accepted."""
        text = dedent("""\
            # REQ-d00001: Test Feature

            **Level**: Dev | **Status**: Active

            ## Assertions

            A. The system SHALL do something.
            B. The system SHALL do another thing.

            *End* *Test Feature* | **Hash**: abc12345
        """)

        result = parser.parse_text(text)
        req = result["REQ-d00001"]

        assert len(req.assertions) == 2
        assert req.assertions[0].label == "A"
        assert req.assertions[1].label == "B"

    def test_invalid_assertion_labels_generate_warning(self, parser):
        """Invalid assertion labels should generate warnings.

        Default config expects uppercase A-Z labels.
        Numeric labels like '01' should generate a warning.
        """
        text = dedent("""\
            # REQ-d00001: Test Feature

            **Level**: Dev | **Status**: Active

            ## Assertions

            01. The system SHALL do something.
            02. The system SHALL do another thing.

            *End* *Test Feature* | **Hash**: abc12345
        """)

        result = parser.parse_text(text)

        # Should have warnings about label format
        label_warnings = [
            w for w in result.warnings
            if "label" in w.message.lower() or "assertion" in w.message.lower()
        ]
        assert len(label_warnings) > 0, (
            f"Should warn about invalid assertion labels. Warnings: {result.warnings}"
        )
