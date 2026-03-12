"""Tests for the Satisfies relationship feature.

Covers: REQ-p00014, REQ-d00069-G, REQ-d00069-H, REQ-d00069-I
"""

from elspais.graph.GraphNode import GraphNode, NodeKind
from elspais.graph.parsers import ParseContext
from elspais.graph.parsers.requirement import RequirementParser
from elspais.graph.relations import EdgeKind, Stereotype
from elspais.utilities.patterns import PatternConfig
from tests.core.graph_test_helpers import build_graph, make_requirement


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
    """EdgeKind.SATISFIES exists but does not contribute to coverage directly.

    Validates REQ-d00069-G: SATISFIES edge kind.
    Coverage flows through SATISFIES edges (like REFINES) but they do not
    directly contribute to coverage counts.
    """

    def test_REQ_d00069_G_satisfies_enum_value(self):
        assert EdgeKind.SATISFIES.value == "satisfies"

    def test_REQ_d00069_G_satisfies_does_not_contribute_to_coverage(self):
        assert EdgeKind.SATISFIES.contributes_to_coverage() is False

    def test_REQ_d00069_G_refines_does_not_contribute(self):
        """Ensure REFINES still doesn't contribute (regression guard)."""
        assert EdgeKind.REFINES.contributes_to_coverage() is False

    def test_REQ_p00014_C_instance_enum_value(self):
        """EdgeKind.INSTANCE has value 'instance'."""
        assert EdgeKind.INSTANCE.value == "instance"

    def test_REQ_p00014_C_instance_does_not_contribute_to_coverage(self):
        """INSTANCE edges do not contribute to coverage (like SATISFIES/REFINES)."""
        assert EdgeKind.INSTANCE.contributes_to_coverage() is False


class TestStereotypeEnum:
    """Stereotype enum for node classification.

    Validates REQ-p00014-C: Stereotype enum classification.
    """

    def test_REQ_p00014_C_stereotype_concrete_value(self):
        assert Stereotype.CONCRETE.value == "concrete"

    def test_REQ_p00014_C_stereotype_template_value(self):
        assert Stereotype.TEMPLATE.value == "template"

    def test_REQ_p00014_C_stereotype_instance_value(self):
        assert Stereotype.INSTANCE.value == "instance"

    def test_REQ_p00014_C_stereotype_default_is_concrete(self):
        """CONCRETE is the default (first member) of the Stereotype enum."""
        first_member = list(Stereotype)[0]
        assert first_member is Stereotype.CONCRETE


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

    def test_satisfies_bold_markdown_syntax(self):
        """Satisfies with **bold** markdown syntax should be parsed like Implements."""
        text = (
            "## REQ-p00043: Diary Mobile Application\n"
            "\n"
            "**Level**: PRD | **Status**: Draft | **Implements**: p00044-C\n"
            "**Satisfies**: p80001\n"
            "\n"
            "*End* *Diary Mobile Application* | **Hash**: 00000000\n"
        )
        lines = [(i + 1, line) for i, line in enumerate(text.split("\n"))]
        parser = _make_parser()
        ctx = ParseContext(file_path="spec/test.md")
        results = list(parser.claim_and_parse(lines, ctx))
        assert len(results) == 1
        assert results[0].parsed_data["satisfies"] == ["REQ-p80001"]

    def test_satisfies_bold_syntax_separate_line(self):
        """Satisfies with bold syntax on a separate line from Level/Status."""
        text = (
            "## REQ-p00043: Diary Mobile Application\n"
            "\n"
            "**Level**: PRD | **Status**: Draft | **Implements**: p00044-C\n"
            "\n"
            "**Satisfies**: p80001\n"
            "\n"
            "*End* *Diary Mobile Application* | **Hash**: 00000000\n"
        )
        lines = [(i + 1, line) for i, line in enumerate(text.split("\n"))]
        parser = _make_parser()
        ctx = ParseContext(file_path="spec/test.md")
        results = list(parser.claim_and_parse(lines, ctx))
        assert len(results) == 1
        assert results[0].parsed_data["satisfies"] == ["REQ-p80001"]

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
        """A Satisfies: declaration creates a SATISFIES edge from declaring to clone."""
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

        declaring_node = graph.find_by_id("REQ-p00044")
        assert declaring_node is not None

        satisfies_edges = list(declaring_node.iter_edges_by_kind(EdgeKind.SATISFIES))
        assert len(satisfies_edges) == 1
        assert satisfies_edges[0].target.id == "REQ-p00044::REQ-p80001"

    def test_REQ_d00069_G_satisfies_assertion_target(self):
        """Satisfies: REQ-p80001-A creates edge to cloned assertion subtree."""
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

        declaring_node = graph.find_by_id("REQ-p00044")
        satisfies_edges = list(declaring_node.iter_edges_by_kind(EdgeKind.SATISFIES))
        assert len(satisfies_edges) == 1
        # Assertion-level satisfies still clones the assertion's parent REQ
        assert satisfies_edges[0].target.id == "REQ-p00044::REQ-p80001-A"

    def test_REQ_d00069_G_multiple_satisfies(self):
        """Multiple Satisfies: targets create separate clone subtrees."""
        from tests.core.graph_test_helpers import build_graph

        t1 = make_requirement("REQ-p80001", title="Template 1")
        t2 = make_requirement("REQ-p80010", title="Template 2")
        declaring = make_requirement(
            "REQ-p00044",
            title="Subsystem",
            satisfies=["REQ-p80001", "REQ-p80010"],
        )
        graph = build_graph(t1, t2, declaring)

        declaring_node = graph.find_by_id("REQ-p00044")
        satisfies_edges = list(declaring_node.iter_edges_by_kind(EdgeKind.SATISFIES))
        assert len(satisfies_edges) == 2
        clone_ids = sorted(e.target.id for e in satisfies_edges)
        assert clone_ids == ["REQ-p00044::REQ-p80001", "REQ-p00044::REQ-p80010"]

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


class TestGraphNodeStereotype:
    """Validates REQ-p00014-C: GraphNode stereotype field.

    The system SHALL classify nodes using a Stereotype field:
    CONCRETE (default), TEMPLATE, or INSTANCE.
    """

    def test_REQ_p00014_C_default_stereotype_is_concrete(self):
        """A newly created GraphNode should default to Stereotype.CONCRETE."""
        node = GraphNode(id="TEST-001", kind=NodeKind.REQUIREMENT)
        assert node.get_field("stereotype") == Stereotype.CONCRETE

    def test_REQ_p00014_C_set_stereotype_template(self):
        """Setting stereotype to TEMPLATE should persist via get_field."""
        node = GraphNode(id="TEST-001", kind=NodeKind.REQUIREMENT)
        node.set_field("stereotype", Stereotype.TEMPLATE)
        assert node.get_field("stereotype") == Stereotype.TEMPLATE

    def test_REQ_p00014_C_set_stereotype_instance(self):
        """Setting stereotype to INSTANCE should persist via get_field."""
        node = GraphNode(id="TEST-001", kind=NodeKind.REQUIREMENT)
        node.set_field("stereotype", Stereotype.INSTANCE)
        assert node.get_field("stereotype") == Stereotype.INSTANCE

    def test_REQ_p00014_C_builder_sets_default_stereotype(self):
        """GraphNodes built via GraphBuilder should have CONCRETE stereotype."""
        req = make_requirement("REQ-p00001", title="Basic Requirement")
        graph = build_graph(req)
        node = graph.find_by_id("REQ-p00001")
        assert node is not None
        assert node.get_field("stereotype") == Stereotype.CONCRETE


class TestTemplateInstantiation:
    """Validates REQ-p00014-B, REQ-p00014-C, REQ-d00069-H: Template subtree cloning.

    When a requirement declares Satisfies: REQ-xxx, the builder should:
    1. Mark the template and its descendants as TEMPLATE
    2. Clone the template subtree with composite IDs (declaring_id::original_id)
    3. Mark clones as INSTANCE with INSTANCE edges back to originals
    4. Create SATISFIES edge from declaring req to cloned root
    5. Preserve internal edges (REFINES) within the cloned subtree
    """

    def test_REQ_p00014_B_satisfies_clones_template_root(self):
        """Satisfies: REQ-p80001 should create a cloned instance node."""
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

        clone = graph.find_by_id("REQ-p00044::REQ-p80001")
        assert clone is not None, "Cloned template root should exist in graph"
        assert clone.get_field("stereotype") == Stereotype.INSTANCE

    def test_REQ_p00014_B_satisfies_edge_from_declaring_to_clone(self):
        """Declaring req should have outgoing SATISFIES edge to the cloned root."""
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

        declaring_node = graph.find_by_id("REQ-p00044")
        satisfies_edges = list(declaring_node.iter_edges_by_kind(EdgeKind.SATISFIES))
        assert len(satisfies_edges) == 1
        assert satisfies_edges[0].target.id == "REQ-p00044::REQ-p80001"

    def test_REQ_p00014_C_instance_edge_from_clone_to_original(self):
        """Cloned root should have outgoing INSTANCE edge to original template."""
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

        clone = graph.find_by_id("REQ-p00044::REQ-p80001")
        instance_edges = list(clone.iter_edges_by_kind(EdgeKind.INSTANCE))
        assert len(instance_edges) == 1
        assert instance_edges[0].target.id == "REQ-p80001"

    def test_REQ_p00014_B_cloned_assertions_exist(self):
        """Template assertions should be cloned with composite IDs."""
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

        clone_a = graph.find_by_id("REQ-p00044::REQ-p80001-A")
        clone_b = graph.find_by_id("REQ-p00044::REQ-p80001-B")
        assert clone_a is not None, "Cloned assertion A should exist"
        assert clone_b is not None, "Cloned assertion B should exist"

        # Cloned assertions should be children of the cloned root
        clone_root = graph.find_by_id("REQ-p00044::REQ-p80001")
        child_ids = {c.id for c in clone_root.iter_children()}
        assert "REQ-p00044::REQ-p80001-A" in child_ids
        assert "REQ-p00044::REQ-p80001-B" in child_ids

    def test_REQ_p00014_B_template_marked_as_template(self):
        """Original template and its assertions should be marked TEMPLATE."""
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
        assert template_node.get_field("stereotype") == Stereotype.TEMPLATE

        assertion_a = graph.find_by_id("REQ-p80001-A")
        assert assertion_a.get_field("stereotype") == Stereotype.TEMPLATE

    def test_REQ_p00014_B_cloned_subtree_preserves_refines(self):
        """Cloned subtree should preserve REFINES edges between cloned nodes."""
        template_root = make_requirement(
            "REQ-p80001",
            title="Electronic Signature Standard",
            assertions=[
                {"label": "A", "text": "root assertion"},
            ],
        )
        template_child = make_requirement(
            "REQ-o80001",
            title="Signature Ops",
            level="OPS",
            refines=["REQ-p80001"],
            assertions=[
                {"label": "A", "text": "child assertion"},
            ],
        )
        declaring = make_requirement(
            "REQ-p00044",
            title="Document Management",
            satisfies=["REQ-p80001"],
        )
        graph = build_graph(template_root, template_child, declaring)

        # Cloned child should exist
        cloned_child = graph.find_by_id("REQ-p00044::REQ-o80001")
        assert cloned_child is not None, "Cloned child REQ should exist"

        # Cloned root should have outgoing REFINES edge to cloned child
        # (builder resolves target.link(source, REFINES) -> parent has outgoing REFINES to child)
        cloned_root = graph.find_by_id("REQ-p00044::REQ-p80001")
        refines_edges = list(cloned_root.iter_edges_by_kind(EdgeKind.REFINES))
        refines_targets = {e.target.id for e in refines_edges}
        assert "REQ-p00044::REQ-o80001" in refines_targets

    def test_REQ_p00014_B_multiple_satisfies_creates_separate_clones(self):
        """Multiple Satisfies: targets create separate clone subtrees."""
        t1 = make_requirement(
            "REQ-p80001",
            title="Template 1",
            assertions=[{"label": "A", "text": "t1 obligation"}],
        )
        t2 = make_requirement(
            "REQ-p80010",
            title="Template 2",
            assertions=[{"label": "A", "text": "t2 obligation"}],
        )
        declaring = make_requirement(
            "REQ-p00044",
            title="Document Management",
            satisfies=["REQ-p80001", "REQ-p80010"],
        )
        graph = build_graph(t1, t2, declaring)

        clone1 = graph.find_by_id("REQ-p00044::REQ-p80001")
        clone2 = graph.find_by_id("REQ-p00044::REQ-p80010")
        assert clone1 is not None, "Clone of template 1 should exist"
        assert clone2 is not None, "Clone of template 2 should exist"

    def test_REQ_d00069_H_cloned_source_location_preserved(self):
        """Cloned nodes should preserve the source location of the original."""
        template = make_requirement(
            "REQ-p80001",
            title="Electronic Signature Standard",
            source_path="spec/template.md",
            start_line=5,
            end_line=20,
            assertions=[
                {"label": "A", "text": "validate signer identity"},
            ],
        )
        declaring = make_requirement(
            "REQ-p00044",
            title="Document Management",
            satisfies=["REQ-p80001"],
        )
        graph = build_graph(template, declaring)

        original = graph.find_by_id("REQ-p80001")
        clone = graph.find_by_id("REQ-p00044::REQ-p80001")
        assert clone is not None, "Cloned node should exist"
        assert clone.source is not None, "Cloned node should have source location"
        assert clone.source.path == original.source.path
        assert clone.source.line == original.source.line
