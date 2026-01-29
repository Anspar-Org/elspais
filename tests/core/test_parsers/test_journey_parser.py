"""Tests for JourneyParser - Priority 60 user journey parser."""

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
