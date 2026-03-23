"""Tests for the Satisfies relationship feature.

Covers: REQ-p00014, REQ-d00069-G, REQ-d00069-H, REQ-d00069-I
"""

from elspais.graph.GraphNode import GraphNode, NodeKind
from elspais.graph.parsers import ParseContext
from elspais.graph.parsers.requirement import RequirementParser
from elspais.graph.relations import EdgeKind, Stereotype
from elspais.mcp.server import _serialize_node_generic
from elspais.utilities.patterns import IdPatternConfig, IdResolver
from tests.core.graph_test_helpers import build_graph, make_code_ref, make_requirement


def _make_parser() -> RequirementParser:
    """Create a parser with default pattern config."""
    config = IdPatternConfig.from_dict(
        {
            "project": {"namespace": "REQ"},
            "id-patterns": {
                "canonical": "{namespace}-{type.letter}{component}",
                "aliases": {"short": "{type.letter}{component}"},
                "types": {
                    "prd": {"level": 1, "aliases": {"letter": "p"}},
                    "ops": {"level": 2, "aliases": {"letter": "o"}},
                    "dev": {"level": 3, "aliases": {"letter": "d"}},
                },
                "component": {"style": "numeric", "digits": 5, "leading_zeros": True},
            },
        }
    )
    return RequirementParser(IdResolver(config))


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

    # Implements: REQ-p00014-A
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

    # Implements: REQ-p00014-A
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

    Validates REQ-p00004-G: Change detection for SATISFIES edges.
    """

    def test_REQ_p00004_G_template_hash_change_flags_declaring_reqs(self):
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
        # After SourceLocation removal, cloned nodes copy parse_line fields
        assert clone.get_field("parse_line") == original.get_field("parse_line")


class TestFileBasedAttribution:
    """Validates REQ-p00014-D: File-based attribution algorithm.

    When code has `# Implements: REQ-o80001-A` targeting a TEMPLATE assertion,
    the builder should redirect it to the correct INSTANCE clone by looking at
    other `Implements:` references in the same source file that target CONCRETE
    nodes, walking up to find the declaring requirement with a Satisfies: match.
    """

    def test_REQ_p00014_D_template_ref_redirected_to_instance(self):
        """Code ref to a template assertion in a file with a concrete sibling
        should be redirected to the instance clone.

        Setup:
        - Template REQ-p80001 with child REQ-o80001 (refines) with assertion A
        - Declaring REQ-p00044 with satisfies=["REQ-p80001"]
        - Code ref line 1 in src/auth.py: implements REQ-p00044 (concrete)
        - Code ref line 5 in src/auth.py: implements REQ-o80001-A (template)

        After build, the code node for line 5 should be a child of the instance
        clone REQ-p00044::REQ-o80001, NOT the template original REQ-o80001.
        """
        template_root = make_requirement(
            "REQ-p80001",
            title="Electronic Signature Standard",
            assertions=[{"label": "A", "text": "root obligation"}],
        )
        template_child = make_requirement(
            "REQ-o80001",
            title="Signature Ops",
            level="OPS",
            refines=["REQ-p80001"],
            assertions=[{"label": "A", "text": "validate signer"}],
        )
        declaring = make_requirement(
            "REQ-p00044",
            title="Document Management",
            satisfies=["REQ-p80001"],
        )

        # Code refs in same file — concrete sibling + template target
        code_concrete = make_code_ref(
            implements=["REQ-p00044"],
            source_path="src/auth.py",
            start_line=1,
        )
        code_template = make_code_ref(
            implements=["REQ-o80001-A"],
            source_path="src/auth.py",
            start_line=5,
        )

        graph = build_graph(
            template_root,
            template_child,
            declaring,
            code_concrete,
            code_template,
        )

        # The instance clone of the child should exist
        instance_child = graph.find_by_id("REQ-p00044::REQ-o80001")
        assert instance_child is not None, "Instance clone REQ-p00044::REQ-o80001 should exist"

        # The code node for line 5 should be a child of the instance clone,
        # NOT the template original
        code_node_id = "code:src/auth.py:5"
        code_node = graph.find_by_id(code_node_id)
        assert code_node is not None, f"Code node {code_node_id} should exist"

        # Check parents: code node should be parented under the instance clone
        parent_ids = {p.id for p in code_node.iter_parents()}
        assert "REQ-p00044::REQ-o80001" in parent_ids, (
            f"Code node should be child of instance clone, " f"but parents are: {parent_ids}"
        )

        # Template original should NOT have the code node as a child
        template_original = graph.find_by_id("REQ-o80001")
        template_child_ids = {c.id for c in template_original.iter_children()}
        assert (
            code_node_id not in template_child_ids
        ), "Template original should NOT have the code node as a child"

    def test_REQ_p00014_D_no_attribution_without_concrete_sibling(self):
        """Code ref to a template assertion with NO concrete sibling in the
        same file should not be linked to the template original.

        Without a concrete sibling, the builder cannot determine which instance
        to attribute the reference to. It should become a broken reference or
        remain unlinked from the template.
        """
        template_root = make_requirement(
            "REQ-p80001",
            title="Electronic Signature Standard",
            assertions=[{"label": "A", "text": "root obligation"}],
        )
        template_child = make_requirement(
            "REQ-o80001",
            title="Signature Ops",
            level="OPS",
            refines=["REQ-p80001"],
            assertions=[{"label": "A", "text": "validate signer"}],
        )
        declaring = make_requirement(
            "REQ-p00044",
            title="Document Management",
            satisfies=["REQ-p80001"],
        )

        # Only a template target — no concrete sibling in same file
        code_orphan = make_code_ref(
            implements=["REQ-o80001-A"],
            source_path="src/orphan.py",
            start_line=1,
        )

        graph = build_graph(
            template_root,
            template_child,
            declaring,
            code_orphan,
        )

        code_node_id = "code:src/orphan.py:1"

        # Template original should NOT have the code node as a child
        # (it's a TEMPLATE node — direct linking is forbidden)
        template_original = graph.find_by_id("REQ-o80001")
        template_child_ids = {c.id for c in template_original.iter_children()}
        assert code_node_id not in template_child_ids, (
            "Template original should NOT have code ref as child "
            "when no concrete sibling exists for attribution"
        )

        # Should appear as a broken reference or warning
        broken = graph.broken_references()
        broken_target_ids = {br.target_id for br in broken}
        # The ref to REQ-o80001-A should be broken (unresolvable without context)
        assert "REQ-o80001-A" in broken_target_ids, (
            f"Template ref without concrete sibling should be broken, "
            f"but broken refs are: {broken_target_ids}"
        )

    def test_REQ_p00014_D_multiple_templates_attributed_independently(self):
        """Multiple template refs in the same file should each be redirected
        to the correct instance clone independently.

        Setup:
        - Two templates: REQ-p80001 (child REQ-o80001) and REQ-p80010 (child REQ-o80010)
        - REQ-p00044 satisfies both
        - Code refs in same file: concrete to REQ-p00044, template to both
        """
        t1_root = make_requirement(
            "REQ-p80001",
            title="Template 1",
            assertions=[{"label": "A", "text": "t1 obligation"}],
        )
        t1_child = make_requirement(
            "REQ-o80001",
            title="Template 1 Ops",
            level="OPS",
            refines=["REQ-p80001"],
            assertions=[{"label": "A", "text": "t1 child obligation"}],
        )
        t2_root = make_requirement(
            "REQ-p80010",
            title="Template 2",
            assertions=[{"label": "A", "text": "t2 obligation"}],
        )
        t2_child = make_requirement(
            "REQ-o80010",
            title="Template 2 Ops",
            level="OPS",
            refines=["REQ-p80010"],
            assertions=[{"label": "A", "text": "t2 child obligation"}],
        )
        declaring = make_requirement(
            "REQ-p00044",
            title="Document Management",
            satisfies=["REQ-p80001", "REQ-p80010"],
        )

        # All code refs in same file
        code_concrete = make_code_ref(
            implements=["REQ-p00044"],
            source_path="src/multi.py",
            start_line=1,
        )
        code_t1 = make_code_ref(
            implements=["REQ-o80001-A"],
            source_path="src/multi.py",
            start_line=10,
        )
        code_t2 = make_code_ref(
            implements=["REQ-o80010-A"],
            source_path="src/multi.py",
            start_line=20,
        )

        graph = build_graph(
            t1_root,
            t1_child,
            t2_root,
            t2_child,
            declaring,
            code_concrete,
            code_t1,
            code_t2,
        )

        # Both instance clones should exist
        instance_1 = graph.find_by_id("REQ-p00044::REQ-o80001")
        instance_2 = graph.find_by_id("REQ-p00044::REQ-o80010")
        assert instance_1 is not None, "Instance clone for template 1 child should exist"
        assert instance_2 is not None, "Instance clone for template 2 child should exist"

        # Code node for t1 (line 10) should be child of instance clone 1
        code_t1_node = graph.find_by_id("code:src/multi.py:10")
        assert code_t1_node is not None
        t1_parent_ids = {p.id for p in code_t1_node.iter_parents()}
        assert "REQ-p00044::REQ-o80001" in t1_parent_ids, (
            f"Code ref to t1 template should be child of instance clone 1, "
            f"but parents are: {t1_parent_ids}"
        )

        # Code node for t2 (line 20) should be child of instance clone 2
        code_t2_node = graph.find_by_id("code:src/multi.py:20")
        assert code_t2_node is not None
        t2_parent_ids = {p.id for p in code_t2_node.iter_parents()}
        assert "REQ-p00044::REQ-o80010" in t2_parent_ids, (
            f"Code ref to t2 template should be child of instance clone 2, "
            f"but parents are: {t2_parent_ids}"
        )


class TestMCPStereotypeSerialization:
    """Validates REQ-p00014-C: Stereotype field in MCP serialization.

    The _serialize_node_generic() function should include the stereotype
    value in the properties dict for REQUIREMENT nodes.
    """

    def test_REQ_p00014_C_serialized_stereotype_concrete(self):
        """A simple requirement serializes with stereotype == 'concrete'."""
        req = make_requirement("REQ-p00001", title="Basic Requirement")
        graph = build_graph(req)
        node = graph.find_by_id("REQ-p00001")
        assert node is not None

        result = _serialize_node_generic(node, graph)
        assert result["properties"]["stereotype"] == "concrete"

    def test_REQ_p00014_C_serialized_stereotype_template(self):
        """A template requirement serializes with stereotype == 'template'."""
        template = make_requirement(
            "REQ-p80001",
            title="Electronic Signature Standard",
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

        template_node = graph.find_by_id("REQ-p80001")
        assert template_node is not None

        result = _serialize_node_generic(template_node, graph)
        assert result["properties"]["stereotype"] == "template"

    def test_REQ_p00014_C_serialized_stereotype_instance(self):
        """An instance clone serializes with stereotype == 'instance'."""
        template = make_requirement(
            "REQ-p80001",
            title="Electronic Signature Standard",
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

        instance_node = graph.find_by_id("REQ-p00044::REQ-p80001")
        assert instance_node is not None

        result = _serialize_node_generic(instance_node, graph)
        assert result["properties"]["stereotype"] == "instance"


class TestSatisfiesFileNodeEdges:
    """DEFINES edges from declaring FILE to INSTANCE nodes.

    Validates REQ-d00128-J: Template instantiation creates DEFINES edges.
    Validates REQ-d00128-K: INSTANCE nodes have no CONTAINS edges.
    Validates REQ-d00128-L: file_node() returns None for INSTANCE nodes.
    """

    def test_REQ_d00128_J_defines_edge_from_file_to_instance_root(self):
        """Declaring FILE node has DEFINES edge to cloned root INSTANCE node."""
        template = make_requirement(
            "REQ-p80001",
            title="Electronic Signature Standard",
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

        declaring_node = graph.find_by_id("REQ-p00044")
        file_node = declaring_node.file_node()
        assert file_node is not None, "Declaring req must have a FILE parent"

        clone_root = graph.find_by_id("REQ-p00044::REQ-p80001")
        assert clone_root is not None

        # FILE node should have DEFINES edge to clone root
        defines_targets = {e.target.id for e in file_node.iter_edges_by_kind(EdgeKind.DEFINES)}
        assert clone_root.id in defines_targets, (
            f"FILE should have DEFINES edge to instance root; " f"got targets: {defines_targets}"
        )

    def test_REQ_d00128_J_defines_edge_from_file_to_instance_assertions(self):
        """Declaring FILE node has DEFINES edges to cloned assertion INSTANCE nodes."""
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
        file_node = declaring_node.file_node()
        assert file_node is not None

        defines_targets = {e.target.id for e in file_node.iter_edges_by_kind(EdgeKind.DEFINES)}
        assert "REQ-p00044::REQ-p80001" in defines_targets
        assert "REQ-p00044::REQ-p80001-A" in defines_targets
        assert "REQ-p00044::REQ-p80001-B" in defines_targets

    def test_REQ_d00128_J_defines_edge_multiple_satisfies(self):
        """Each declaring FILE gets DEFINES edges to its own INSTANCE nodes."""
        template = make_requirement(
            "REQ-p80001",
            title="Electronic Signature Standard",
            assertions=[{"label": "A", "text": "validate signer identity"}],
        )
        declaring1 = make_requirement(
            "REQ-p00044",
            title="Document Management",
            satisfies=["REQ-p80001"],
            source_path="spec/doc-mgmt.md",
        )
        declaring2 = make_requirement(
            "REQ-p00045",
            title="User Management",
            satisfies=["REQ-p80001"],
            source_path="spec/user-mgmt.md",
        )
        graph = build_graph(template, declaring1, declaring2)

        # File for declaring1 should define declaring1's instances
        decl1 = graph.find_by_id("REQ-p00044")
        file1 = decl1.file_node()
        defines1 = {e.target.id for e in file1.iter_edges_by_kind(EdgeKind.DEFINES)}
        assert "REQ-p00044::REQ-p80001" in defines1
        assert "REQ-p00044::REQ-p80001-A" in defines1

        # File for declaring2 should define declaring2's instances
        decl2 = graph.find_by_id("REQ-p00045")
        file2 = decl2.file_node()
        defines2 = {e.target.id for e in file2.iter_edges_by_kind(EdgeKind.DEFINES)}
        assert "REQ-p00045::REQ-p80001" in defines2
        assert "REQ-p00045::REQ-p80001-A" in defines2

    def test_REQ_d00128_K_instance_nodes_no_contains_edges(self):
        """INSTANCE nodes have no incoming CONTAINS edges."""
        template = make_requirement(
            "REQ-p80001",
            title="Electronic Signature Standard",
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

        clone_root = graph.find_by_id("REQ-p00044::REQ-p80001")
        clone_a = graph.find_by_id("REQ-p00044::REQ-p80001-A")

        for node in [clone_root, clone_a]:
            contains_edges = [e for e in node.iter_incoming_edges() if e.kind == EdgeKind.CONTAINS]
            assert len(contains_edges) == 0, (
                f"INSTANCE node {node.id} should have no CONTAINS edges, "
                f"got {len(contains_edges)}"
            )

    def test_REQ_d00128_L_file_node_returns_none_for_instance(self):
        """file_node() returns None for INSTANCE nodes."""
        template = make_requirement(
            "REQ-p80001",
            title="Electronic Signature Standard",
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

        clone_root = graph.find_by_id("REQ-p00044::REQ-p80001")
        clone_a = graph.find_by_id("REQ-p00044::REQ-p80001-A")

        assert clone_root.file_node() is None, "file_node() should return None for INSTANCE root"
        assert clone_a.file_node() is None, "file_node() should return None for INSTANCE assertion"

    def test_REQ_d00128_L_instance_original_has_file_node(self):
        """Original template node still has a FILE via file_node()."""
        template = make_requirement(
            "REQ-p80001",
            title="Electronic Signature Standard",
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

        # Navigate from INSTANCE to original via INSTANCE edge
        clone_root = graph.find_by_id("REQ-p00044::REQ-p80001")
        instance_edges = list(clone_root.iter_edges_by_kind(EdgeKind.INSTANCE))
        assert len(instance_edges) == 1
        original = instance_edges[0].target
        assert original.file_node() is not None, "Original template node should have a FILE parent"
