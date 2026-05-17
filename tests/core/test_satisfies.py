"""Tests for the Satisfies relationship feature.

Covers: REQ-p00014, REQ-d00069-G, REQ-d00069-H, REQ-d00069-I
"""

from elspais.graph.GraphNode import GraphNode, NodeKind
from elspais.graph.parsers.lark import GrammarFactory
from elspais.graph.parsers.lark.transformers.requirement import RequirementTransformer
from elspais.graph.relations import EdgeKind, Stereotype
from elspais.mcp.server import _serialize_node_generic
from elspais.utilities.patterns import IdPatternConfig, IdResolver
from tests.core.graph_test_helpers import build_graph, make_requirement


def _make_lark_pipeline():
    """Create Lark parser + transformer with default pattern config."""
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
    resolver = IdResolver(config)
    factory = GrammarFactory(resolver)
    lark_parser = factory.get_requirement_parser()
    transformer = RequirementTransformer(resolver)
    return lark_parser, transformer


def _parse_text(text: str):
    """Parse requirement text with Lark pipeline, return ParsedContent list."""
    lark_parser, transformer = _make_lark_pipeline()
    if not text.endswith("\n"):
        text += "\n"
    tree = lark_parser.parse(text)
    results = transformer.transform(tree)
    return [r for r in results if r.content_type == "requirement"]


class TestEdgeKindSatisfies:
    """EdgeKind.SATISFIES exists but does not contribute to coverage directly.

    Validates REQ-d00069-G: SATISFIES edge kind.
    Coverage flows through SATISFIES edges (like REFINES) but they do not
    directly contribute to coverage counts.
    """

    def test_REQ_d00069_G_satisfies_does_not_contribute_to_coverage(self):
        assert EdgeKind.SATISFIES.contributes_to_coverage() is False

    def test_REQ_d00069_G_refines_does_not_contribute(self):
        """Ensure REFINES still doesn't contribute (regression guard)."""
        assert EdgeKind.REFINES.contributes_to_coverage() is False

    def test_REQ_p00014_C_instance_does_not_contribute_to_coverage(self):
        """INSTANCE edges do not contribute to coverage (like SATISFIES/REFINES)."""
        assert EdgeKind.INSTANCE.contributes_to_coverage() is False


class TestStereotypeEnum:
    """Stereotype enum for node classification.

    Validates REQ-p00014-C: Stereotype enum classification.
    """

    def test_REQ_p00014_C_stereotype_default_is_concrete(self):
        """CONCRETE is the default (first member) of the Stereotype enum."""
        first_member = list(Stereotype)[0]
        assert first_member is Stereotype.CONCRETE


class TestParserSatisfies:
    """Lark parser extracts Satisfies: metadata.

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
        results = _parse_text(text)
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
        results = _parse_text(text)
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
        results = _parse_text(text)
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
        results = _parse_text(text)
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
        results = _parse_text(text)
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
        results = _parse_text(text)
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
            template=True,
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
            template=True,
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

        t1 = make_requirement("REQ-p80001", title="Template 1", template=True)
        t2 = make_requirement("REQ-p80010", title="Template 2", template=True)
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
            template=True,
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
            template=True,
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
            template=True,
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
            template=True,
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
            template=True,
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
            template=True,
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

    # CUR-1353 Phase 2 (single-REQ scope): the former
    # ``test_REQ_p00014_B_cloned_subtree_preserves_refines`` test exercised
    # multi-REQ template authoring (two REQs both marked **Template**, child
    # REFINES parent). The design spec at
    # docs/superpowers/specs/2026-05-15-cross-repo-template-design.md locks
    # single-REQ scope: a template is one REQ root plus its directly-attached
    # assertions, with no child REQs and no transitive REFINES descendants.
    # Inbound REFINES against any TEMPLATE is now a rule-8 error. The
    # behaviour the deleted test asserted is no longer reachable; see
    # tests/unit/graph/test_template_validation.py for the replacement
    # coverage.

    def test_REQ_p00014_B_multiple_satisfies_creates_separate_clones(self):
        """Multiple Satisfies: targets create separate clone subtrees."""
        t1 = make_requirement(
            "REQ-p80001",
            title="Template 1",
            template=True,
            assertions=[{"label": "A", "text": "t1 obligation"}],
        )
        t2 = make_requirement(
            "REQ-p80010",
            title="Template 2",
            template=True,
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
            template=True,
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


# CUR-1353 Phase 2: `TestFileBasedAttribution` (former REQ-p00014-D coverage)
# was removed alongside the `_attribute_template_refs` machinery. CODE that
# declares `Implements: <template-assertion>` now lands a direct IMPLEMENTS
# edge on the template assertion — no per-file redirection to instance clones.
# See tests/unit/graph/test_template_validation.py::TestImplementsTemplateIsLegal
# for the replacement coverage.


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
            template=True,
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
            template=True,
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
            template=True,
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
            template=True,
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
            template=True,
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
            template=True,
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
            template=True,
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
            template=True,
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
