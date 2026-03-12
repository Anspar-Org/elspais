"""Tests for the Satisfies relationship feature.

Covers: REQ-p00014, REQ-d00069-G, REQ-d00069-H, REQ-d00069-I
"""

from elspais.graph.parsers import ParseContext
from elspais.graph.parsers.requirement import RequirementParser
from elspais.graph.relations import EdgeKind
from elspais.utilities.patterns import PatternConfig
from tests.core.graph_test_helpers import make_requirement


def _make_parser() -> RequirementParser:
    """Create a parser with default pattern config."""
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


class TestEdgeKindSatisfies:
    """EdgeKind.SATISFIES exists and contributes to coverage.

    Validates REQ-d00069-G: SATISFIES edge kind.
    """

    def test_REQ_d00069_G_satisfies_enum_value(self):
        assert EdgeKind.SATISFIES.value == "satisfies"

    def test_REQ_d00069_G_satisfies_contributes_to_coverage(self):
        assert EdgeKind.SATISFIES.contributes_to_coverage() is True

    def test_REQ_d00069_G_refines_does_not_contribute(self):
        """Ensure REFINES still doesn't contribute (regression guard)."""
        assert EdgeKind.REFINES.contributes_to_coverage() is False


class TestParserSatisfies:
    """RequirementParser extracts Satisfies: metadata.

    Validates REQ-d00069-H: Satisfies parsing.
    """

    def test_REQ_d00069_H_single_satisfies(self):
        text = (
            "## REQ-p00044: Document Management\n"
            "\n"
            "**Level**: PRD | **Status**: Active\n"
            "\n"
            "Satisfies: REQ-p80001\n"
            "\n"
            "*End* *Document Management* | **Hash**: 00000000\n"
        )
        lines = [(i + 1, line) for i, line in enumerate(text.split("\n"))]
        parser = _make_parser()
        ctx = ParseContext(file_path="spec/test.md")
        results = list(parser.claim_and_parse(lines, ctx))
        assert len(results) == 1
        assert results[0].parsed_data["satisfies"] == ["REQ-p80001"]

    def test_REQ_d00069_H_multiple_satisfies(self):
        text = (
            "## REQ-p00044: Document Management\n"
            "\n"
            "**Level**: PRD | **Status**: Active\n"
            "\n"
            "Satisfies: REQ-p80001, REQ-p80010\n"
            "\n"
            "*End* *Document Management* | **Hash**: 00000000\n"
        )
        lines = [(i + 1, line) for i, line in enumerate(text.split("\n"))]
        parser = _make_parser()
        ctx = ParseContext(file_path="spec/test.md")
        results = list(parser.claim_and_parse(lines, ctx))
        assert results[0].parsed_data["satisfies"] == ["REQ-p80001", "REQ-p80010"]

    def test_REQ_d00069_H_assertion_level_satisfies(self):
        text = (
            "## REQ-p00044: Document Management\n"
            "\n"
            "**Level**: PRD | **Status**: Active\n"
            "\n"
            "Satisfies: REQ-p80001-A\n"
            "\n"
            "*End* *Document Management* | **Hash**: 00000000\n"
        )
        lines = [(i + 1, line) for i, line in enumerate(text.split("\n"))]
        parser = _make_parser()
        ctx = ParseContext(file_path="spec/test.md")
        results = list(parser.claim_and_parse(lines, ctx))
        assert results[0].parsed_data["satisfies"] == ["REQ-p80001-A"]

    def test_REQ_d00069_H_no_satisfies(self):
        text = (
            "## REQ-p00001: Basic\n"
            "\n"
            "**Level**: PRD | **Status**: Active\n"
            "\n"
            "*End* *Basic* | **Hash**: 00000000\n"
        )
        lines = [(i + 1, line) for i, line in enumerate(text.split("\n"))]
        parser = _make_parser()
        ctx = ParseContext(file_path="spec/test.md")
        results = list(parser.claim_and_parse(lines, ctx))
        assert results[0].parsed_data["satisfies"] == []


class TestHelperSatisfies:
    """make_requirement helper supports satisfies parameter.

    Validates REQ-d00069-G: SATISFIES edge infrastructure.
    """

    def test_REQ_d00069_G_make_requirement_with_satisfies(self):
        req = make_requirement(
            "REQ-p00044",
            title="Doc Mgmt",
            satisfies=["REQ-p80001"],
        )
        assert req.parsed_data["satisfies"] == ["REQ-p80001"]

    def test_REQ_d00069_G_make_requirement_without_satisfies(self):
        req = make_requirement("REQ-p00001", title="Basic")
        assert req.parsed_data["satisfies"] == []
