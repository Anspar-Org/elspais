"""Tests for RequirementParser - Priority 50 requirement block parser."""

import pytest

from elspais.graph.parsers import ParseContext
from elspais.graph.parsers.requirement import RequirementParser


@pytest.fixture
def parser(hht_resolver):
    """Create a RequirementParser with default HHT-style config."""
    return RequirementParser(hht_resolver)


class TestRequirementParserPriority:
    """Tests for RequirementParser priority."""

    # Implements: REQ-d00054-A
    def test_priority_is_50(self, parser):
        assert parser.priority == 50


class TestRequirementParserBasic:
    """Tests for basic requirement parsing."""

    # Implements: REQ-p00002-A
    def test_claims_simple_requirement(self, parser):
        lines = [
            (1, "# REQ-p00001: User Authentication"),
            (2, ""),
            (3, "**Level**: PRD | **Status**: Active"),
            (4, ""),
            (5, "Users SHALL be able to log in."),
            (6, ""),
            (7, "*End* *REQ-p00001*"),
        ]
        ctx = ParseContext(file_path="spec/prd.md")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        assert results[0].content_type == "requirement"
        assert results[0].start_line == 1
        assert results[0].end_line == 7
        assert results[0].parsed_data["id"] == "REQ-p00001"
        assert results[0].parsed_data["title"] == "User Authentication"

    # Implements: REQ-p00002-A
    def test_claims_requirement_with_assertions(self, parser):
        lines = [
            (1, "## REQ-p00001: User Authentication"),
            (2, "**Level**: PRD | **Status**: Active"),
            (3, ""),
            (4, "## Assertions"),
            (5, ""),
            (6, "A. Users SHALL log in with email/password."),
            (7, "B. Users SHALL be able to reset password."),
            (8, ""),
            (9, "*End* *REQ-p00001*"),
        ]
        ctx = ParseContext(file_path="spec/prd.md")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        assertions = results[0].parsed_data.get("assertions", [])
        assert len(assertions) == 2
        assert assertions[0]["label"] == "A"
        assert assertions[1]["label"] == "B"

    # Implements: REQ-p00002-A
    def test_claims_multiple_requirements(self, parser):
        lines = [
            (1, "## REQ-p00001: First Req"),
            (2, "**Status**: Active"),
            (3, "Body text."),
            (4, "*End* *REQ-p00001*"),
            (5, "---"),
            (6, "## REQ-p00002: Second Req"),
            (7, "**Status**: Active"),
            (8, "More body."),
            (9, "*End* *REQ-p00002*"),
        ]
        ctx = ParseContext(file_path="spec/prd.md")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 2
        assert results[0].parsed_data["id"] == "REQ-p00001"
        assert results[1].parsed_data["id"] == "REQ-p00002"

    # Implements: REQ-p00002-A
    def test_parses_implements_field(self, parser):
        lines = [
            (1, "## REQ-o00001: Impl Req"),
            (2, "**Level**: OPS | **Implements**: REQ-p00001 | **Status**: Active"),
            (3, "Body."),
            (4, "*End* *REQ-o00001*"),
        ]
        ctx = ParseContext(file_path="spec/ops.md")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        assert results[0].parsed_data["implements"] == ["REQ-p00001"]

    # Implements: REQ-p00002-A
    def test_parses_implements_shorthand_format(self, parser):
        """Test that shorthand references (without REQ- prefix) are normalized."""
        lines = [
            (1, "## REQ-d00001: Dev Req"),
            (2, "**Level**: Dev | **Status**: Draft | **Implements**: o00001, o00002"),
            (3, "Body."),
            (4, "*End* *REQ-d00001*"),
        ]
        ctx = ParseContext(file_path="spec/dev.md")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        # Shorthand "o00001" should be normalized to "REQ-o00001"
        assert results[0].parsed_data["implements"] == ["REQ-o00001", "REQ-o00002"]

    # Implements: REQ-p00002-A
    def test_parses_refines_field(self, parser):
        lines = [
            (1, "## REQ-p00002: Refining Req"),
            (2, "**Level**: PRD | **Refines**: REQ-p00001 | **Status**: Active"),
            (3, "Body."),
            (4, "*End* *REQ-p00002*"),
        ]
        ctx = ParseContext(file_path="spec/prd.md")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        assert results[0].parsed_data["refines"] == ["REQ-p00001"]

    # Implements: REQ-p00002-C
    def test_extracts_hash(self, parser):
        lines = [
            (1, "## REQ-p00001: Hashed Req"),
            (2, "**Status**: Active"),
            (3, "Body."),
            (4, "*End* *REQ-p00001* | **Hash**: abc12345"),
        ]
        ctx = ParseContext(file_path="spec/prd.md")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        assert results[0].parsed_data["hash"] == "abc12345"


class TestRequirementParserEdgeCases:
    """Edge cases for requirement parsing."""

    # Implements: REQ-p00002-A
    def test_no_requirements_returns_empty(self, parser):
        lines = [
            (1, "# Some Header"),
            (2, "Just prose text."),
            (3, "No requirements here."),
        ]
        ctx = ParseContext(file_path="test.md")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 0

    # Implements: REQ-p00002-A
    def test_invalid_id_not_claimed(self, parser):
        lines = [
            (1, "## INVALID-001: Bad Format"),
            (2, "This should not be claimed."),
        ]
        ctx = ParseContext(file_path="test.md")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 0

    # Implements: REQ-p00002-A
    def test_requirement_without_end_marker(self, parser):
        lines = [
            (1, "## REQ-p00001: No End Marker"),
            (2, "**Status**: Active"),
            (3, "Body text without end."),
        ]
        ctx = ParseContext(file_path="spec/prd.md")

        results = list(parser.claim_and_parse(lines, ctx))

        # Should still claim - next req or EOF ends it
        assert len(results) == 1
        assert results[0].end_line == 3

    # Implements: REQ-d00081-D
    def test_passes_through_multi_assertion_syntax(self, parser):
        """Multi-assertion expansion now happens in builder, not parser."""
        lines = [
            (1, "## REQ-o00001: Multi-Assertion"),
            (2, "**Implements**: REQ-p00001-A+B+C | **Status**: Active"),
            (3, "Body."),
            (4, "*End* *REQ-o00001*"),
        ]
        ctx = ParseContext(file_path="spec/ops.md")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        # Parser passes through as-is; builder expands later
        implements = results[0].parsed_data["implements"]
        assert "REQ-p00001-A+B+C" in implements


class TestRoundTripLineNumbers:
    """Tests for round-trip fidelity: line numbers on assertions and sections."""

    # Implements: REQ-d00128-E
    def test_assertions_include_line_numbers(self, parser):
        """Assertions should include their absolute line number."""
        lines = [
            (10, "## REQ-p00001: Test Req"),
            (11, "**Level**: PRD | **Status**: Active"),
            (12, ""),
            (13, "## Assertions"),
            (14, ""),
            (15, "A. SHALL do first thing."),
            (16, "B. SHALL do second thing."),
            (17, ""),
            (18, "*End* *REQ-p00001*"),
        ]
        ctx = ParseContext(file_path="spec/prd.md")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        assertions = results[0].parsed_data["assertions"]
        assert len(assertions) == 2
        assert assertions[0]["label"] == "A"
        assert assertions[0]["line"] == 15
        assert assertions[1]["label"] == "B"
        assert assertions[1]["line"] == 16

    # Implements: REQ-d00128-E
    def test_sections_include_line_numbers(self, parser):
        """Non-normative sections should include their line number."""
        lines = [
            (20, "## REQ-p00002: Sectioned Req"),
            (21, "**Level**: PRD | **Status**: Active"),
            (22, ""),
            (23, "Some preamble text here."),
            (24, ""),
            (25, "## Rationale"),
            (26, ""),
            (27, "This is why we need it."),
            (28, ""),
            (29, "## Assertions"),
            (30, ""),
            (31, "A. SHALL exist."),
            (32, ""),
            (33, "*End* *REQ-p00002*"),
        ]
        ctx = ParseContext(file_path="spec/prd.md")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        sections = results[0].parsed_data["sections"]
        # Should have preamble and Rationale (Assertions excluded)
        headings = [s["heading"] for s in sections]
        assert "preamble" in headings
        assert "Rationale" in headings
        # Each section has a line number
        for section in sections:
            assert "line" in section
            assert isinstance(section["line"], int)

    # Implements: REQ-d00128-E
    def test_assertion_line_zero_when_start_line_zero(self, parser):
        """When start_line is 0 (default), lines should be relative offsets."""
        lines = [
            (0, "## REQ-p00001: Zero-based"),
            (1, "**Level**: PRD | **Status**: Active"),
            (2, ""),
            (3, "## Assertions"),
            (4, ""),
            (5, "A. SHALL test."),
            (6, ""),
            (7, "*End* *REQ-p00001*"),
        ]
        ctx = ParseContext(file_path="spec/prd.md")

        results = list(parser.claim_and_parse(lines, ctx))

        assertions = results[0].parsed_data["assertions"]
        assert assertions[0]["line"] == 5


class TestPreambleMetadataStripping:
    """Tests that metadata lines are fully stripped from the preamble section.

    Validates REQ-p00002-A: preamble REMAINDER must not contain any metadata
    lines that are already parsed into structured fields (Level, Status,
    Implements, Refines, Satisfies).
    """

    # Implements: REQ-p00002-A
    def test_refines_line_stripped_from_preamble(self, parser):
        # Verifies: REQ-p00002-A
        """Validates that **Refines**: metadata line is not included in preamble section.

        Regression test: _flush_section must strip **Refines**: just like
        **Level**: and **Implements**: lines, to prevent preamble REMAINDER from
        bleeding into rendered output.
        """
        lines = [
            (1, "## REQ-p00001: Title"),
            (2, "**Level**: PRD | **Status**: Active"),
            (3, "**Refines**: REQ-p00002"),
            (4, ""),
            (5, "*End* *Title*"),
        ]
        ctx = ParseContext(file_path="spec/test.md")
        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        sections = results[0].parsed_data["sections"]
        preamble = next((s for s in sections if s["heading"] == "preamble"), None)
        # Preamble should be absent or empty - not contain the Refines line
        if preamble is not None:
            assert "**Refines**" not in preamble["content"]

    # Implements: REQ-p00002-A
    def test_multiple_refines_lines_all_stripped_from_preamble(self, parser):
        # Verifies: REQ-p00002-A
        """All **Refines**: lines in body are stripped from preamble - no matter how many."""
        lines = [
            (1, "## REQ-p00001: Title"),
            (2, "**Level**: PRD | **Status**: Active"),
            (3, "**Refines**: REQ-p00002"),
            (4, ""),
            (5, "**Refines**: REQ-p00002"),
            (6, ""),
            (7, "*End* *Title*"),
        ]
        ctx = ParseContext(file_path="spec/test.md")
        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        sections = results[0].parsed_data["sections"]
        preamble = next((s for s in sections if s["heading"] == "preamble"), None)
        if preamble is not None:
            assert "**Refines**" not in preamble["content"]


class TestChangelogParsing:
    """Changelog entry extraction from requirement body text.

    Validates REQ-p00002-A: The parser extracts structured changelog entries
    from a ## Changelog section in requirement markdown.
    """

    REQUIREMENT_WITH_CHANGELOG = [
        (1, "# REQ-d00001: Test Requirement"),
        (2, ""),
        (3, "**Level**: DEV | **Status**: Active | **Implements**: -"),
        (4, ""),
        (5, "## Assertions"),
        (6, ""),
        (7, "A. The system SHALL do something."),
        (8, ""),
        (9, "## Changelog"),
        (10, ""),
        (
            11,
            "- 2026-03-06 | abcdef12 | CUR-1234 | Alice (a@b.org) | Refined A",
        ),
        (
            12,
            "- 2026-02-15 | bf63eda5 | CUR-1200 | Bob (b@b.org) | First version",
        ),
        (13, ""),
        (14, "*End* *Test Requirement* | **Hash**: abcdef12"),
    ]

    REQUIREMENT_WITHOUT_CHANGELOG = [
        (1, "# REQ-d00001: Test Requirement"),
        (2, ""),
        (3, "**Level**: DEV | **Status**: Active | **Implements**: -"),
        (4, ""),
        (5, "## Assertions"),
        (6, ""),
        (7, "A. The system SHALL do something."),
        (8, ""),
        (9, "*End* *Test Requirement* | **Hash**: abcdef12"),
    ]

    # Implements: REQ-p00002-A
    def test_REQ_p00002_A_parses_changelog_entries(self, parser):
        """A requirement with ## Changelog should have parsed changelog entries."""
        ctx = ParseContext(file_path="spec/dev.md")

        results = list(parser.claim_and_parse(self.REQUIREMENT_WITH_CHANGELOG, ctx))

        assert len(results) == 1
        parsed = results[0].parsed_data
        assert "changelog" in parsed
        changelog = parsed["changelog"]
        assert isinstance(changelog, list)
        assert len(changelog) >= 1

        entry = changelog[0]
        assert "date" in entry
        assert "hash" in entry
        assert "change_order" in entry
        assert "author_name" in entry
        assert "author_id" in entry
        assert "reason" in entry

        assert entry["date"] == "2026-03-06"
        assert entry["hash"] == "abcdef12"
        assert entry["change_order"] == "CUR-1234"
        assert entry["author_name"] == "Alice"
        assert entry["author_id"] == "a@b.org"
        assert entry["reason"] == "Refined A"

    # Implements: REQ-p00002-A
    def test_REQ_p00002_A_changelog_empty_when_no_section(self, parser):
        """A requirement without ## Changelog should have changelog: []."""
        ctx = ParseContext(file_path="spec/dev.md")

        results = list(parser.claim_and_parse(self.REQUIREMENT_WITHOUT_CHANGELOG, ctx))

        assert len(results) == 1
        parsed = results[0].parsed_data
        assert "changelog" in parsed
        assert parsed["changelog"] == []

    # Implements: REQ-p00002-A
    def test_REQ_p00002_A_changelog_multiple_entries(self, parser):
        """Multiple changelog entries are parsed in order (newest first)."""
        ctx = ParseContext(file_path="spec/dev.md")

        results = list(parser.claim_and_parse(self.REQUIREMENT_WITH_CHANGELOG, ctx))

        assert len(results) == 1
        changelog = results[0].parsed_data["changelog"]
        assert len(changelog) == 2

        # First entry (newest)
        assert changelog[0]["date"] == "2026-03-06"
        assert changelog[0]["hash"] == "abcdef12"
        assert changelog[0]["change_order"] == "CUR-1234"
        assert changelog[0]["author_name"] == "Alice"
        assert changelog[0]["author_id"] == "a@b.org"
        assert changelog[0]["reason"] == "Refined A"

        # Second entry (older)
        assert changelog[1]["date"] == "2026-02-15"
        assert changelog[1]["hash"] == "bf63eda5"
        assert changelog[1]["change_order"] == "CUR-1200"
        assert changelog[1]["author_name"] == "Bob"
        assert changelog[1]["author_id"] == "b@b.org"
        assert changelog[1]["reason"] == "First version"

    # Implements: REQ-p00002-A
    def test_REQ_p00002_A_changelog_excluded_from_sections(self, parser):
        """The ## Changelog section should NOT appear in parsed_data['sections']."""
        ctx = ParseContext(file_path="spec/dev.md")

        results = list(parser.claim_and_parse(self.REQUIREMENT_WITH_CHANGELOG, ctx))

        assert len(results) == 1
        sections = results[0].parsed_data.get("sections", [])
        section_headings = [s["heading"] for s in sections]
        assert "Changelog" not in section_headings


class TestAdditiveMetadataCollection:
    """Tests that multiple **Implements**: and **Refines**: lines are merged additively.

    Validates: REQ-p00002-A
    """

    # Implements: REQ-p00002-A
    def test_multiple_implements_lines_are_additive(self, parser):
        # Verifies: REQ-p00002-A
        """Two distinct **Implements**: lines are merged into one list."""
        lines = [
            (1, "## REQ-p00001: Title"),
            (2, "**Level**: PRD | **Status**: Active | **Implements**: REQ-p00002"),
            (3, "**Implements**: REQ-p00003"),
            (4, ""),
            (5, "*End* *Title*"),
        ]
        ctx = ParseContext(file_path="spec/test.md")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        assert set(results[0].parsed_data["implements"]) == {"REQ-p00002", "REQ-p00003"}
        assert results[0].parsed_data.get("has_redundant_refs") is not True

    # Implements: REQ-p00002-A
    def test_multiple_refines_lines_are_additive(self, parser):
        # Verifies: REQ-p00002-A
        """Two distinct **Refines**: lines are merged into one list."""
        lines = [
            (1, "## REQ-p00001: Title"),
            (2, "**Level**: PRD | **Status**: Active"),
            (3, "**Refines**: REQ-p00002"),
            (4, "**Refines**: REQ-p00003"),
            (5, ""),
            (6, "*End* *Title*"),
        ]
        ctx = ParseContext(file_path="spec/test.md")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        assert set(results[0].parsed_data["refines"]) == {"REQ-p00002", "REQ-p00003"}
        assert results[0].parsed_data.get("has_redundant_refs") is not True

    # Implements: REQ-p00002-A
    def test_duplicate_implements_ref_sets_has_redundant_refs(self, parser):
        # Verifies: REQ-p00002-A
        """Same REQ ID appearing in two **Implements**: lines sets has_redundant_refs."""
        lines = [
            (1, "## REQ-p00001: Title"),
            (2, "**Level**: PRD | **Status**: Active | **Implements**: REQ-p00002"),
            (3, "**Implements**: REQ-p00002"),
            (4, ""),
            (5, "*End* *Title*"),
        ]
        ctx = ParseContext(file_path="spec/test.md")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        implements = results[0].parsed_data["implements"]
        assert "REQ-p00002" in implements
        assert implements.count("REQ-p00002") == 1  # deduplicated
        assert results[0].parsed_data["has_redundant_refs"] is True

    # Implements: REQ-p00002-A
    def test_duplicate_refines_ref_sets_has_redundant_refs(self, parser):
        # Verifies: REQ-p00002-A
        """Same REQ ID appearing in two **Refines**: lines sets has_redundant_refs."""
        lines = [
            (1, "## REQ-p00001: Title"),
            (2, "**Level**: PRD | **Status**: Active"),
            (3, "**Refines**: REQ-p00002"),
            (4, "**Refines**: REQ-p00002"),
            (5, ""),
            (6, "*End* *Title*"),
        ]
        ctx = ParseContext(file_path="spec/test.md")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        refines = results[0].parsed_data["refines"]
        assert refines.count("REQ-p00002") == 1  # deduplicated
        assert results[0].parsed_data["has_redundant_refs"] is True

    # Implements: REQ-p00002-A
    def test_no_redundant_refs_when_all_distinct(self, parser):
        # Verifies: REQ-p00002-A
        """has_redundant_refs is False/absent when all refs are unique."""
        lines = [
            (1, "## REQ-p00001: Title"),
            (2, "**Level**: PRD | **Status**: Active | **Implements**: REQ-p00002"),
            (3, "**Implements**: REQ-p00003"),
            (4, "**Refines**: REQ-p00004"),
            (5, ""),
            (6, "*End* *Title*"),
        ]
        ctx = ParseContext(file_path="spec/test.md")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        assert not results[0].parsed_data.get("has_redundant_refs")
