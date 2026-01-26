"""Tests for RequirementParser - Priority 50 requirement block parser."""

import pytest

from elspais.graph.parsers import ParseContext
from elspais.graph.parsers.requirement import RequirementParser


@pytest.fixture
def parser():
    """Create a RequirementParser with default HHT-style config."""
    from elspais.utilities.patterns import PatternConfig

    config = PatternConfig(
        id_template="{prefix}-{type}{id}",
        prefix="REQ",
        types={
            "prd": {"id": "p", "name": "PRD", "level": 1},
            "ops": {"id": "o", "name": "OPS", "level": 2},
            "dev": {"id": "d", "name": "DEV", "level": 3},
        },
        id_format={"style": "numeric", "digits": 5, "leading_zeros": True},
    )
    return RequirementParser(config)


class TestRequirementParserPriority:
    """Tests for RequirementParser priority."""

    def test_priority_is_50(self, parser):
        assert parser.priority == 50


class TestRequirementParserBasic:
    """Tests for basic requirement parsing."""

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

    def test_no_requirements_returns_empty(self, parser):
        lines = [
            (1, "# Some Header"),
            (2, "Just prose text."),
            (3, "No requirements here."),
        ]
        ctx = ParseContext(file_path="test.md")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 0

    def test_invalid_id_not_claimed(self, parser):
        lines = [
            (1, "## INVALID-001: Bad Format"),
            (2, "This should not be claimed."),
        ]
        ctx = ParseContext(file_path="test.md")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 0

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

    def test_expands_multi_assertion_syntax(self, parser):
        lines = [
            (1, "## REQ-o00001: Multi-Assertion"),
            (2, "**Implements**: REQ-p00001-A-B-C | **Status**: Active"),
            (3, "Body."),
            (4, "*End* *REQ-o00001*"),
        ]
        ctx = ParseContext(file_path="spec/ops.md")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        # Multi-assertion should be expanded
        implements = results[0].parsed_data["implements"]
        assert "REQ-p00001-A" in implements
        assert "REQ-p00001-B" in implements
        assert "REQ-p00001-C" in implements
