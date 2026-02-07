"""Tests for JourneyParser - Priority 60 user journey parser.

Validates REQ-o00050-C: TraceGraphBuilder SHALL handle all relationship
linking including addresses.
"""

from elspais.graph.parsers import ParseContext
from elspais.graph.parsers.journey import JourneyParser


class TestJourneyParserPriority:
    """Tests for JourneyParser priority."""

    def test_priority_is_60(self):
        parser = JourneyParser()
        assert parser.priority == 60


class TestJourneyParserBasic:
    """Tests for basic journey parsing."""

    def test_claims_simple_journey(self):
        parser = JourneyParser()
        lines = [
            (1, "## JNY-Spec-Author-01: Creating Requirements"),
            (2, ""),
            (3, "**Actor**: Spec Author"),
            (4, "**Goal**: Create new requirements"),
            (5, ""),
            (6, "### Steps"),
            (7, "1. Open spec file"),
            (8, "2. Add requirement header"),
            (9, "3. Save file"),
            (10, ""),
            (11, "*End* *JNY-Spec-Author-01*"),
        ]
        ctx = ParseContext(file_path="spec/journeys.md")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        assert results[0].content_type == "journey"
        assert results[0].parsed_data["id"] == "JNY-Spec-Author-01"
        assert results[0].parsed_data["actor"] == "Spec Author"

    def test_no_journeys_returns_empty(self):
        parser = JourneyParser()
        lines = [
            (1, "# Regular Header"),
            (2, "Regular text."),
        ]
        ctx = ParseContext(file_path="test.md")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 0


class TestJourneyParserAddresses:
    """Tests for JourneyParser Addresses: field parsing.

    Validates REQ-o00050-C: TraceGraphBuilder SHALL handle all relationship
    linking including addresses.
    """

    def test_REQ_o00050_C_addresses_multiple_refs(self):
        """Journey with Addresses: REQ-p00012, REQ-d00042 parses both refs."""
        parser = JourneyParser()
        lines = [
            (1, "## JNY-Dev-01: Development Workflow"),
            (2, ""),
            (3, "**Actor**: Developer"),
            (4, "**Goal**: Implement a feature"),
            (5, "Addresses: REQ-p00012, REQ-d00042"),
            (6, ""),
            (7, "### Steps"),
            (8, "1. Read requirements"),
            (9, "2. Write code"),
            (10, ""),
            (11, "*End* *JNY-Dev-01*"),
        ]
        ctx = ParseContext(file_path="spec/journeys.md")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        addresses = results[0].parsed_data["addresses"]
        assert len(addresses) == 2
        assert "REQ-p00012" in addresses
        assert "REQ-d00042" in addresses

    def test_REQ_o00050_C_no_addresses_line_empty_list(self):
        """Journey without Addresses: line has empty addresses list."""
        parser = JourneyParser()
        lines = [
            (1, "## JNY-Dev-02: Simple Journey"),
            (2, ""),
            (3, "**Actor**: Developer"),
            (4, "**Goal**: Do something"),
            (5, ""),
            (6, "### Steps"),
            (7, "1. Step one"),
            (8, ""),
            (9, "*End* *JNY-Dev-02*"),
        ]
        ctx = ParseContext(file_path="spec/journeys.md")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        addresses = results[0].parsed_data["addresses"]
        assert addresses == []

    def test_REQ_o00050_C_single_address(self):
        """Journey with single Addresses: REQ-p00012 parses one ref."""
        parser = JourneyParser()
        lines = [
            (1, "## JNY-Dev-03: Single Address Journey"),
            (2, ""),
            (3, "**Actor**: Developer"),
            (4, "**Goal**: Implement feature"),
            (5, "Addresses: REQ-p00012"),
            (6, ""),
            (7, "### Steps"),
            (8, "1. Do work"),
            (9, ""),
            (10, "*End* *JNY-Dev-03*"),
        ]
        ctx = ParseContext(file_path="spec/journeys.md")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        addresses = results[0].parsed_data["addresses"]
        assert len(addresses) == 1
        assert addresses[0] == "REQ-p00012"

    def test_REQ_o00050_C_addresses_whitespace_padded(self):
        """Journey with whitespace-padded refs in Addresses: line."""
        parser = JourneyParser()
        lines = [
            (1, "## JNY-Dev-04: Whitespace Journey"),
            (2, ""),
            (3, "**Actor**: Developer"),
            (4, "**Goal**: Test whitespace"),
            (5, "Addresses:   REQ-p00012 ,  REQ-d00042  , REQ-o00005  "),
            (6, ""),
            (7, "### Steps"),
            (8, "1. Verify parsing"),
            (9, ""),
            (10, "*End* *JNY-Dev-04*"),
        ]
        ctx = ParseContext(file_path="spec/journeys.md")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        addresses = results[0].parsed_data["addresses"]
        assert len(addresses) == 3
        assert "REQ-p00012" in addresses
        assert "REQ-d00042" in addresses
        assert "REQ-o00005" in addresses
        # Verify no leading/trailing whitespace on parsed refs
        for addr in addresses:
            assert addr == addr.strip()
