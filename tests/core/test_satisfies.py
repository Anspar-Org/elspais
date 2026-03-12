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


class TestTemplateCoverage:
    """Per-instance template coverage computation.

    Validates REQ-d00069-I: Template coverage computation.
    """

    def test_REQ_d00069_I_basic_template_coverage(self):
        """Coverage computed for a simple template with 2 leaf assertions."""
        from tests.core.graph_test_helpers import build_graph, make_code_ref

        template = make_requirement(
            "REQ-p80001",
            title="Signature Standard",
            assertions=[
                {"label": "A", "text": "validate identity"},
                {"label": "B", "text": "two-factor auth"},
            ],
        )
        declaring = make_requirement(
            "REQ-p00044",
            title="Doc Mgmt",
            satisfies=["REQ-p80001"],
        )
        dev_req = make_requirement(
            "REQ-d00044",
            title="Auth Module",
            level="DEV",
            implements=["REQ-p00044"],
        )
        code = make_code_ref(
            ["REQ-d00044", "REQ-p80001-A"],
            source_path="src/auth.py",
        )

        graph = build_graph(template, declaring, dev_req, code)

        from elspais.graph.annotators import annotate_coverage

        annotate_coverage(graph)

        node = graph.find_by_id("REQ-p00044")
        sat_cov = node.get_metric("satisfies_coverage")
        assert sat_cov is not None
        assert "REQ-p80001" in sat_cov
        assert sat_cov["REQ-p80001"]["total"] == 2
        assert sat_cov["REQ-p80001"]["covered"] == 1
        assert sat_cov["REQ-p80001"]["missing"] == ["REQ-p80001-B"]

    def test_REQ_d00069_I_full_template_coverage(self):
        """100% coverage when all leaf assertions are covered."""
        from tests.core.graph_test_helpers import build_graph, make_code_ref

        template = make_requirement(
            "REQ-p80001",
            title="Template",
            assertions=[
                {"label": "A", "text": "first"},
                {"label": "B", "text": "second"},
            ],
        )
        declaring = make_requirement(
            "REQ-p00044",
            title="Subsystem",
            satisfies=["REQ-p80001"],
        )
        dev = make_requirement(
            "REQ-d00044",
            title="Impl",
            level="DEV",
            implements=["REQ-p00044"],
        )
        code_a = make_code_ref(
            ["REQ-d00044", "REQ-p80001-A"],
            source_path="src/a.py",
        )
        code_b = make_code_ref(
            ["REQ-d00044", "REQ-p80001-B"],
            source_path="src/b.py",
        )

        graph = build_graph(template, declaring, dev, code_a, code_b)

        from elspais.graph.annotators import annotate_coverage

        annotate_coverage(graph)

        node = graph.find_by_id("REQ-p00044")
        sat_cov = node.get_metric("satisfies_coverage")
        assert sat_cov["REQ-p80001"]["coverage_pct"] == 100.0
        assert sat_cov["REQ-p80001"]["missing"] == []


class TestChangeDetection:
    """Template hash changes flag SATISFIES declarations.

    Validates REQ-p00017: Change detection for SATISFIES edges.
    """

    def test_REQ_p00017_A_template_hash_change_flags_declaring_reqs(self):
        """When template hash changes, declaring reqs should be flagged."""
        from tests.core.graph_test_helpers import build_graph

        template = make_requirement(
            "REQ-p80001",
            title="Template",
            hash_value="aabbccdd",  # Stale hash
            assertions=[
                {"label": "A", "text": "obligation"},
            ],
        )
        declaring = make_requirement(
            "REQ-p00044",
            title="Subsystem",
            satisfies=["REQ-p80001"],
        )

        graph = build_graph(template, declaring)

        from elspais.commands.health import check_spec_hash_integrity

        result = check_spec_hash_integrity(graph)

        # Should have findings about the declaring req
        assert any(
            f.node_id == "REQ-p00044" and "REQ-p80001" in (f.related or []) for f in result.findings
        )


class TestNADeclarations:
    """N/A assertions exclude template assertions from coverage.

    Validates REQ-p00016: N/A assertion handling.
    """

    def test_REQ_p00016_A_na_reduces_denominator(self):
        """N/A assertion excluded from coverage target."""
        from tests.core.graph_test_helpers import build_graph, make_code_ref

        template = make_requirement(
            "REQ-p80001",
            title="Template",
            assertions=[
                {"label": "A", "text": "required obligation"},
                {"label": "B", "text": "another obligation"},
                {"label": "C", "text": "optional obligation"},
            ],
        )
        declaring = make_requirement(
            "REQ-p00044",
            title="Subsystem",
            satisfies=["REQ-p80001"],
            assertions=[
                {"label": "A", "text": "own work"},
                {"label": "B", "text": "REQ-p80001-C SHALL be NOT APPLICABLE"},
            ],
        )
        dev = make_requirement(
            "REQ-d00044",
            title="Impl",
            level="DEV",
            implements=["REQ-p00044"],
        )
        code_a = make_code_ref(
            ["REQ-d00044", "REQ-p80001-A"],
            source_path="src/a.py",
        )
        code_b = make_code_ref(
            ["REQ-d00044", "REQ-p80001-B"],
            source_path="src/b.py",
        )

        graph = build_graph(template, declaring, dev, code_a, code_b)

        from elspais.graph.annotators import annotate_coverage

        annotate_coverage(graph)

        node = graph.find_by_id("REQ-p00044")
        sat_cov = node.get_metric("satisfies_coverage")
        assert sat_cov["REQ-p80001"]["total"] == 3
        assert sat_cov["REQ-p80001"]["na"] == 1
        assert sat_cov["REQ-p80001"]["covered"] == 2
        # coverage = 2 / (3 - 1) = 100%
        assert sat_cov["REQ-p80001"]["coverage_pct"] == 100.0

    def test_REQ_p00016_B_na_assertion_not_in_missing(self):
        """N/A assertions should not appear in missing list."""
        from tests.core.graph_test_helpers import build_graph, make_code_ref

        template = make_requirement(
            "REQ-p80001",
            title="Template",
            assertions=[
                {"label": "A", "text": "required"},
                {"label": "B", "text": "not applicable"},
            ],
        )
        declaring = make_requirement(
            "REQ-p00044",
            title="Subsystem",
            satisfies=["REQ-p80001"],
            assertions=[
                {"label": "A", "text": "REQ-p80001-B SHALL be NOT APPLICABLE"},
            ],
        )
        dev = make_requirement(
            "REQ-d00044",
            title="Impl",
            level="DEV",
            implements=["REQ-p00044"],
        )
        code = make_code_ref(
            ["REQ-d00044", "REQ-p80001-A"],
            source_path="src/a.py",
        )

        graph = build_graph(template, declaring, dev, code)

        from elspais.graph.annotators import annotate_coverage

        annotate_coverage(graph)

        node = graph.find_by_id("REQ-p00044")
        sat_cov = node.get_metric("satisfies_coverage")
        assert "REQ-p80001-B" not in sat_cov["REQ-p80001"]["missing"]

    def test_REQ_p00016_C_implements_na_assertion_produces_error(self):
        """Implements: reference to a N/A assertion produces error."""
        from tests.core.graph_test_helpers import build_graph, make_code_ref

        template = make_requirement(
            "REQ-p80001",
            title="Template",
            assertions=[
                {"label": "A", "text": "required"},
                {"label": "B", "text": "not needed"},
            ],
        )
        declaring = make_requirement(
            "REQ-p00044",
            title="Subsystem",
            satisfies=["REQ-p80001"],
            assertions=[
                {"label": "A", "text": "REQ-p80001-B SHALL be NOT APPLICABLE"},
            ],
        )
        dev = make_requirement(
            "REQ-d00044",
            title="Impl",
            level="DEV",
            implements=["REQ-p00044"],
        )
        # Code references the N/A assertion - this is an error
        code = make_code_ref(
            ["REQ-d00044", "REQ-p80001-B"],
            source_path="src/bad.py",
        )

        graph = build_graph(template, declaring, dev, code)

        from elspais.graph.annotators import annotate_coverage

        annotate_coverage(graph)

        node = graph.find_by_id("REQ-p00044")
        sat_cov = node.get_metric("satisfies_coverage")
        # B is N/A - should NOT count as covered
        assert sat_cov["REQ-p80001"]["covered"] == 0
        # Should have an error recorded
        na_errors = node.get_metric("satisfies_na_errors")
        assert na_errors is not None
        assert "REQ-p80001-B" in na_errors

    def test_REQ_d00069_I_hierarchical_template_coverage(self):
        """Template with sub-requirements: leaf assertions are the leaves."""
        from tests.core.graph_test_helpers import build_graph, make_code_ref

        template_root = make_requirement(
            "REQ-p80001",
            title="Template Root",
        )
        template_child = make_requirement(
            "REQ-o80001",
            title="Auth Reqs",
            level="OPS",
            refines=["REQ-p80001"],
            assertions=[
                {"label": "A", "text": "validate identity"},
                {"label": "B", "text": "two-factor"},
            ],
        )
        declaring = make_requirement(
            "REQ-p00044",
            title="Subsystem",
            satisfies=["REQ-p80001"],
        )
        dev = make_requirement(
            "REQ-d00044",
            title="Impl",
            level="DEV",
            implements=["REQ-p00044"],
        )
        code = make_code_ref(
            ["REQ-d00044", "REQ-o80001-A"],
            source_path="src/auth.py",
        )

        graph = build_graph(
            template_root,
            template_child,
            declaring,
            dev,
            code,
        )

        from elspais.graph.annotators import annotate_coverage

        annotate_coverage(graph)

        node = graph.find_by_id("REQ-p00044")
        sat_cov = node.get_metric("satisfies_coverage")
        assert sat_cov is not None
        assert "REQ-p80001" in sat_cov
        assert sat_cov["REQ-p80001"]["total"] == 2
        assert sat_cov["REQ-p80001"]["covered"] == 1

    def test_REQ_d00069_I_satisfies_coverage_stored_as_metric(self):
        """SATISFIES coverage is stored as a metric on the declaring node."""
        from tests.core.graph_test_helpers import build_graph, make_code_ref

        template = make_requirement(
            "REQ-p80001",
            title="Template",
            assertions=[
                {"label": "A", "text": "only one"},
            ],
        )
        declaring = make_requirement(
            "REQ-p00044",
            title="Subsystem",
            satisfies=["REQ-p80001"],
        )
        dev = make_requirement(
            "REQ-d00044",
            title="Impl",
            level="DEV",
            implements=["REQ-p00044"],
        )
        code = make_code_ref(
            ["REQ-d00044", "REQ-p80001-A"],
            source_path="src/a.py",
        )

        graph = build_graph(template, declaring, dev, code)

        from elspais.graph.annotators import annotate_coverage

        annotate_coverage(graph)

        node = graph.find_by_id("REQ-p00044")
        sat_cov = node.get_metric("satisfies_coverage")
        assert sat_cov["REQ-p80001"]["coverage_pct"] == 100.0


class TestHealthCoverageGaps:
    """Health command reports template coverage gaps.

    Validates REQ-p00015-E: Health reporting for template coverage.
    """

    def test_REQ_p00015_E_coverage_gap_reported(self):
        """Incomplete template coverage produces a health finding."""
        from tests.core.graph_test_helpers import build_graph

        template = make_requirement(
            "REQ-p80001",
            title="Template",
            assertions=[
                {"label": "A", "text": "first"},
                {"label": "B", "text": "second"},
            ],
        )
        declaring = make_requirement(
            "REQ-p00044",
            title="Subsystem",
            satisfies=["REQ-p80001"],
        )

        graph = build_graph(template, declaring)

        from elspais.graph.annotators import annotate_coverage

        annotate_coverage(graph)

        from elspais.commands.health import check_template_coverage

        result = check_template_coverage(graph)

        assert not result.passed
        assert any("REQ-p00044" in f.message or f.node_id == "REQ-p00044" for f in result.findings)
        assert any("REQ-p80001" in f.message for f in result.findings)

    def test_REQ_p00015_E_full_coverage_passes(self):
        """Complete template coverage produces a passing health check."""
        from tests.core.graph_test_helpers import build_graph, make_code_ref

        template = make_requirement(
            "REQ-p80001",
            title="Template",
            assertions=[
                {"label": "A", "text": "only one"},
            ],
        )
        declaring = make_requirement(
            "REQ-p00044",
            title="Subsystem",
            satisfies=["REQ-p80001"],
        )
        dev = make_requirement(
            "REQ-d00044",
            title="Impl",
            level="DEV",
            implements=["REQ-p00044"],
        )
        code = make_code_ref(
            ["REQ-d00044", "REQ-p80001-A"],
            source_path="src/a.py",
        )

        graph = build_graph(template, declaring, dev, code)

        from elspais.graph.annotators import annotate_coverage

        annotate_coverage(graph)

        from elspais.commands.health import check_template_coverage

        result = check_template_coverage(graph)
        assert result.passed
