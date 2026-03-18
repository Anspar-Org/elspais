"""Tests for JourneyParser - Priority 60 user journey parser.

Validates REQ-o00050-C: TraceGraphBuilder SHALL handle all relationship
linking including validates.
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


class TestJourneyParserValidates:
    """Tests for JourneyParser Validates: field parsing.

    Validates REQ-o00050-C: TraceGraphBuilder SHALL handle all relationship
    linking including validates.
    """

    def test_REQ_o00050_C_validates_multiple_refs(self):
        """Journey with Validates: REQ-p00012, REQ-d00042 parses both refs."""
        parser = JourneyParser()
        lines = [
            (1, "## JNY-Dev-01: Development Workflow"),
            (2, ""),
            (3, "**Actor**: Developer"),
            (4, "**Goal**: Implement a feature"),
            (5, "Validates: REQ-p00012, REQ-d00042"),
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
        validates = results[0].parsed_data["validates"]
        assert len(validates) == 2
        assert "REQ-p00012" in validates
        assert "REQ-d00042" in validates

    def test_REQ_o00050_C_no_validates_line_empty_list(self):
        """Journey without Validates: line has empty validates list."""
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
        validates = results[0].parsed_data["validates"]
        assert validates == []

    def test_REQ_o00050_C_single_validates(self):
        """Journey with single Validates: REQ-p00012 parses one ref."""
        parser = JourneyParser()
        lines = [
            (1, "## JNY-Dev-03: Single Validates Journey"),
            (2, ""),
            (3, "**Actor**: Developer"),
            (4, "**Goal**: Implement feature"),
            (5, "Validates: REQ-p00012"),
            (6, ""),
            (7, "### Steps"),
            (8, "1. Do work"),
            (9, ""),
            (10, "*End* *JNY-Dev-03*"),
        ]
        ctx = ParseContext(file_path="spec/journeys.md")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        validates = results[0].parsed_data["validates"]
        assert len(validates) == 1
        assert validates[0] == "REQ-p00012"

    def test_REQ_o00050_C_validates_whitespace_padded(self):
        """Journey with whitespace-padded refs in Validates: line."""
        parser = JourneyParser()
        lines = [
            (1, "## JNY-Dev-04: Whitespace Journey"),
            (2, ""),
            (3, "**Actor**: Developer"),
            (4, "**Goal**: Test whitespace"),
            (5, "Validates:   REQ-p00012 ,  REQ-d00042  , REQ-o00005  "),
            (6, ""),
            (7, "### Steps"),
            (8, "1. Verify parsing"),
            (9, ""),
            (10, "*End* *JNY-Dev-04*"),
        ]
        ctx = ParseContext(file_path="spec/journeys.md")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        validates = results[0].parsed_data["validates"]
        assert len(validates) == 3
        assert "REQ-p00012" in validates
        assert "REQ-d00042" in validates
        assert "REQ-o00005" in validates
        # Verify no leading/trailing whitespace on parsed refs
        for val in validates:
            assert val == val.strip()


def test_journey_parser_REQ_validates_field():
    """JourneyParser extracts Validates: field into parsed_data['validates'].

    Validates REQ-d00069-A: journey parser supports validates field.
    """
    from elspais.graph.parsers.journey import JourneyParser

    parser = JourneyParser()
    lines_text = """\
## JNY-TST-001: Test Journey
**Actor**: Tester
**Goal**: Verify something
Validates: REQ-p00001, REQ-p00002
*End* *JNY-TST-001*
"""
    lines = [(i + 1, line) for i, line in enumerate(lines_text.splitlines())]
    results = list(parser.claim_and_parse(lines, context=None))
    assert len(results) == 1
    data = results[0].parsed_data
    assert "validates" in data
    assert "addresses" not in data
    assert data["validates"] == ["REQ-p00001", "REQ-p00002"]
