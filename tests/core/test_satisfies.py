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


class TestBuilderSatisfiesEdge:
    """GraphBuilder creates SATISFIES edges from parsed satisfies data.

    Validates REQ-d00069-G: SATISFIES edge resolution.
    """

    def test_REQ_d00069_G_satisfies_creates_edge(self):
        """A Satisfies: declaration creates a SATISFIES edge to the template."""
        from tests.core.graph_test_helpers import build_graph

        template = make_requirement(
            "REQ-p80001",
            title="Electronic Signature Standard",
            assertions=[
                {"label": "A", "text": "validate signer identity"},
                {"label": "B", "text": "two-factor for high-risk"},
            ],
        )
        declaring = make_requirement(
            "REQ-p00044",
            title="Document Management",
            satisfies=["REQ-p80001"],
        )
        graph = build_graph(template, declaring)

        template_node = graph.find_by_id("REQ-p80001")
        assert template_node is not None

        satisfies_edges = list(template_node.iter_edges_by_kind(EdgeKind.SATISFIES))
        assert len(satisfies_edges) == 1
        assert satisfies_edges[0].target.id == "REQ-p00044"

    def test_REQ_d00069_G_satisfies_assertion_target(self):
        """Satisfies: REQ-p80001-A creates edge with assertion_targets."""
        from tests.core.graph_test_helpers import build_graph

        template = make_requirement(
            "REQ-p80001",
            title="Template",
            assertions=[
                {"label": "A", "text": "first obligation"},
                {"label": "B", "text": "second obligation"},
            ],
        )
        declaring = make_requirement(
            "REQ-p00044",
            title="Subsystem",
            satisfies=["REQ-p80001-A"],
        )
        graph = build_graph(template, declaring)

        template_node = graph.find_by_id("REQ-p80001")
        satisfies_edges = list(template_node.iter_edges_by_kind(EdgeKind.SATISFIES))
        assert len(satisfies_edges) == 1
        assert satisfies_edges[0].assertion_targets == ["A"]

    def test_REQ_d00069_G_multiple_satisfies(self):
        """Multiple Satisfies: targets create separate edges."""
        from tests.core.graph_test_helpers import build_graph

        t1 = make_requirement("REQ-p80001", title="Template 1")
        t2 = make_requirement("REQ-p80010", title="Template 2")
        declaring = make_requirement(
            "REQ-p00044",
            title="Subsystem",
            satisfies=["REQ-p80001", "REQ-p80010"],
        )
        graph = build_graph(t1, t2, declaring)

        t1_node = graph.find_by_id("REQ-p80001")
        t2_node = graph.find_by_id("REQ-p80010")
        assert len(list(t1_node.iter_edges_by_kind(EdgeKind.SATISFIES))) == 1
        assert len(list(t2_node.iter_edges_by_kind(EdgeKind.SATISFIES))) == 1

    def test_REQ_d00069_G_satisfies_broken_reference(self):
        """Satisfies: to nonexistent target records a broken reference."""
        from tests.core.graph_test_helpers import build_graph

        declaring = make_requirement(
            "REQ-p00044",
            title="Subsystem",
            satisfies=["REQ-p99999"],
        )
        graph = build_graph(declaring)

        broken = graph.broken_references()
        assert any(br.target_id == "REQ-p99999" for br in broken)
