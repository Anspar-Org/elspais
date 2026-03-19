"""Integration tests for full Deserializer → MDparser → Graph pipeline."""

from elspais.config import find_config_file, load_config
from elspais.graph import NodeKind
from elspais.graph.builder import GraphBuilder
from elspais.graph.deserializer import DomainFile
from elspais.graph.parsers import ParserRegistry
from elspais.graph.parsers.comments import CommentsParser
from elspais.graph.parsers.remainder import RemainderParser
from elspais.graph.parsers.requirement import RequirementParser
from elspais.utilities.patterns import build_resolver


def _make_resolver(config):
    """Build IdResolver from loaded config."""
    return build_resolver(config)


def create_parser_registry(resolver) -> ParserRegistry:
    """Create a parser registry with all standard parsers."""
    registry = ParserRegistry()
    registry.register(CommentsParser())
    registry.register(RequirementParser(resolver))
    registry.register(RemainderParser())
    return registry


class TestFullPipeline:
    """Tests for the complete parsing pipeline."""

    def test_pipeline_parses_all_requirements(self, integration_spec_dir):
        """Verify all requirements are parsed from spec files."""
        # Load config
        config_path = find_config_file(integration_spec_dir)
        config = load_config(config_path)

        # Create pattern config
        resolver = _make_resolver(config)

        # Create parser registry
        registry = create_parser_registry(resolver)

        # Create deserializer for spec directory
        spec_dir = integration_spec_dir / "spec"
        deserializer = DomainFile(spec_dir, patterns=["*.md"])

        # Build graph
        builder = GraphBuilder(repo_root=integration_spec_dir)
        for content in deserializer.deserialize(registry):
            builder.add_parsed_content(content)

        graph = builder.build()

        # Verify all requirements were found
        assert graph.find_by_id("REQ-p00001") is not None
        assert graph.find_by_id("REQ-p00002") is not None
        assert graph.find_by_id("REQ-o00001") is not None
        assert graph.find_by_id("REQ-o00002") is not None
        assert graph.find_by_id("REQ-o00003") is not None
        assert graph.find_by_id("REQ-o00004") is not None

    def test_pipeline_creates_assertions(self, integration_spec_dir):
        """Verify assertions are created as child nodes."""
        config_path = find_config_file(integration_spec_dir)
        config = load_config(config_path)
        resolver = _make_resolver(config)
        registry = create_parser_registry(resolver)

        spec_dir = integration_spec_dir / "spec"
        deserializer = DomainFile(spec_dir, patterns=["*.md"])

        builder = GraphBuilder(repo_root=integration_spec_dir)
        for content in deserializer.deserialize(registry):
            builder.add_parsed_content(content)

        graph = builder.build()

        # REQ-p00001 should have 3 assertions
        p00001 = graph.find_by_id("REQ-p00001")
        assertions = [c for c in p00001.iter_children() if c.kind == NodeKind.ASSERTION]
        assert len(assertions) == 3

        # Verify assertion IDs
        assertion_ids = {a.id for a in assertions}
        assert "REQ-p00001-A" in assertion_ids
        assert "REQ-p00001-B" in assertion_ids
        assert "REQ-p00001-C" in assertion_ids

    def test_pipeline_links_implements(self, integration_spec_dir):
        """Verify implements relationships are properly linked."""
        config_path = find_config_file(integration_spec_dir)
        config = load_config(config_path)
        resolver = _make_resolver(config)
        registry = create_parser_registry(resolver)

        spec_dir = integration_spec_dir / "spec"
        deserializer = DomainFile(spec_dir, patterns=["*.md"])

        builder = GraphBuilder(repo_root=integration_spec_dir)
        for content in deserializer.deserialize(registry):
            builder.add_parsed_content(content)

        graph = builder.build()

        # REQ-o00001 implements REQ-p00001-A
        o00001 = graph.find_by_id("REQ-o00001")
        p00001 = graph.find_by_id("REQ-p00001")

        # OPS req should have parent requirement (not assertion node)
        # with assertion_targets indicating which assertions it implements
        assert o00001.has_parent(p00001)

        # Verify the edge has assertion_targets=['A']
        for edge in p00001.iter_outgoing_edges():
            if edge.target.id == "REQ-o00001":
                assert edge.assertion_targets == ["A"]
                break
        else:
            raise AssertionError("Expected edge from REQ-p00001 to REQ-o00001 not found")

    def test_pipeline_identifies_roots(self, integration_spec_dir):
        """Verify root nodes are correctly identified."""
        config_path = find_config_file(integration_spec_dir)
        config = load_config(config_path)
        resolver = _make_resolver(config)
        registry = create_parser_registry(resolver)

        spec_dir = integration_spec_dir / "spec"
        deserializer = DomainFile(spec_dir, patterns=["*.md"])

        builder = GraphBuilder(repo_root=integration_spec_dir)
        for content in deserializer.deserialize(registry):
            builder.add_parsed_content(content)

        graph = builder.build()

        # Only PRD requirements should be roots (no parents)
        assert graph.has_root("REQ-p00001")
        assert graph.has_root("REQ-p00002")

        # OPS requirements have parents, so not roots
        assert not graph.has_root("REQ-o00001")
        assert not graph.has_root("REQ-o00002")
        assert not graph.has_root("REQ-o00004")

    def test_pipeline_node_counts(self, integration_spec_dir):
        """Verify expected node counts by type."""
        config_path = find_config_file(integration_spec_dir)
        config = load_config(config_path)
        resolver = _make_resolver(config)
        registry = create_parser_registry(resolver)

        spec_dir = integration_spec_dir / "spec"
        deserializer = DomainFile(spec_dir, patterns=["*.md"])

        builder = GraphBuilder(repo_root=integration_spec_dir)
        for content in deserializer.deserialize(registry):
            builder.add_parsed_content(content)

        graph = builder.build()

        # Count by type
        requirements = list(graph.nodes_by_kind(NodeKind.REQUIREMENT))
        assertions = list(graph.nodes_by_kind(NodeKind.ASSERTION))

        # 2 PRD + 4 OPS = 6 requirements
        assert len(requirements) == 6

        # 3 assertions (REQ-p00001) + 2 assertions (REQ-p00002) = 5 assertions
        assert len(assertions) == 5


# Verifies: REQ-d00081-D+E+G
class TestMultiAssertionPipelineExpansion:
    """Integration tests for multi-assertion expansion in the full pipeline.

    Validates REQ-d00081-D: Spec files using multi-assertion syntax expand into
    individual edges.
    Validates REQ-d00081-E: Code comments using multi-assertion syntax also expand
    (proving centralization).
    Validates REQ-d00081-G: When separator is empty/disabled, no expansion occurs.
    """

    def _build_graph(self, root_dir, multi_assertion_separator="+", include_code=False):
        """Helper to build a graph from the fixture directory.

        Args:
            root_dir: Root directory containing spec/ and optionally src/.
            multi_assertion_separator: Separator for multi-assertion expansion.
            include_code: Whether to also parse code files from src/.

        Returns:
            Built TraceGraph.
        """
        config_path = find_config_file(root_dir)
        config = load_config(config_path)
        resolver = _make_resolver(config)

        # Registry for spec files
        spec_registry = create_parser_registry(resolver)

        # Parse spec files
        spec_dir = root_dir / "spec"
        spec_deserializer = DomainFile(spec_dir, patterns=["*.md"])

        builder = GraphBuilder(
            repo_root=root_dir,
            multi_assertion_separator=multi_assertion_separator,
        )
        for content in spec_deserializer.deserialize(spec_registry):
            builder.add_parsed_content(content)

        # Optionally parse code files via Lark FileDispatcher
        if include_code:
            from elspais.graph.parsers.lark import FileDispatcher

            dispatcher = FileDispatcher(resolver)
            code_dir = root_dir / "src"
            for py_file in sorted(code_dir.rglob("*.py")):
                text = py_file.read_text(encoding="utf-8")
                for parsed in dispatcher.dispatch_code(text, str(py_file)):
                    builder.add_parsed_content(parsed)

        return builder.build()

    def test_REQ_d00081_D_spec_multi_assertion_expands_to_individual_edges(
        self, multi_assertion_spec_dir
    ):
        """Multi-assertion syntax in spec Implements expands to individual edges.

        REQ-o00001 uses 'Implements: REQ-p00001-A+B+C' which should create
        three separate edges targeting assertions A, B, and C.
        """
        graph = self._build_graph(multi_assertion_spec_dir)

        # The OPS requirement should exist
        o00001 = graph.find_by_id("REQ-o00001")
        assert o00001 is not None, "REQ-o00001 should be in the graph"

        # The PRD requirement and its assertions should exist
        p00001 = graph.find_by_id("REQ-p00001")
        assert p00001 is not None

        for label in ("A", "B", "C"):
            assertion = graph.find_by_id(f"REQ-p00001-{label}")
            assert assertion is not None, f"Assertion REQ-p00001-{label} should exist"

        # REQ-o00001 should be linked under REQ-p00001 (parent)
        assert o00001.has_parent(p00001), "REQ-o00001 should have REQ-p00001 as parent"

        # Collect all assertion targets across edges from p00001 to o00001.
        # Each expanded assertion creates a separate edge with one target.
        all_targets = []
        for edge in p00001.iter_outgoing_edges():
            if edge.target.id == "REQ-o00001":
                all_targets.extend(edge.assertion_targets)
        assert len(all_targets) > 0, "Expected edges from REQ-p00001 to REQ-o00001"
        assert sorted(all_targets) == [
            "A",
            "B",
            "C",
        ], f"Expected assertion_targets ['A', 'B', 'C'], got {sorted(all_targets)}"

    def test_REQ_d00081_E_code_refs_resolve_through_same_builder(self, multi_assertion_spec_dir):
        """Code references resolve through the same builder as spec references.

        Both spec multi-assertion expansion (REQ-p00001-A+B+C in OPS) and
        code assertion references (# Implements: REQ-p00001-A, REQ-p00001-B)
        are processed by the same GraphBuilder.build(), proving centralization.
        The code file uses comma-separated assertion refs which the code parser
        captures individually; the builder resolves them to assertion nodes.
        """
        graph = self._build_graph(multi_assertion_spec_dir, include_code=True)

        # Find CODE nodes
        code_nodes = list(graph.nodes_by_kind(NodeKind.CODE))
        assert len(code_nodes) >= 1, "Should have at least one CODE node"

        # The code node should be linked to the parent requirement
        code_node = code_nodes[0]
        p00001 = graph.find_by_id("REQ-p00001")
        assert p00001 is not None

        # Code node should be a child of p00001 (via assertion target resolution)
        assert code_node.has_parent(
            p00001
        ), "CODE node should have REQ-p00001 as parent via assertion resolution"

        # Collect assertion targets across all edges from p00001 to the code node.
        # Both assertions A and B should be resolved from the code references.
        all_targets = []
        for edge in p00001.iter_outgoing_edges():
            if edge.target.id == code_node.id:
                all_targets.extend(edge.assertion_targets)
        assert len(all_targets) > 0, f"Expected edges from REQ-p00001 to CODE node {code_node.id}"
        assert sorted(all_targets) == [
            "A",
            "B",
        ], f"Expected assertion_targets ['A', 'B'], got {sorted(all_targets)}"

        # Verify spec multi-assertion expansion also worked in the same graph.
        # This proves both parser types share the same builder pipeline.
        o00001 = graph.find_by_id("REQ-o00001")
        assert o00001 is not None
        assert o00001.has_parent(p00001)
        spec_targets = []
        for edge in p00001.iter_outgoing_edges():
            if edge.target.id == "REQ-o00001":
                spec_targets.extend(edge.assertion_targets)
        assert sorted(spec_targets) == [
            "A",
            "B",
            "C",
        ], f"Spec multi-assertion should also expand, got {sorted(spec_targets)}"

    def test_REQ_d00081_G_empty_separator_disables_expansion(self, multi_assertion_spec_dir):
        """When multi_assertion_separator is empty, no expansion occurs.

        With separator disabled, 'REQ-p00001-A+B+C' is treated as a single
        literal reference ID which will not resolve to any known node,
        resulting in a broken reference.
        """
        graph = self._build_graph(multi_assertion_spec_dir, multi_assertion_separator="")

        # REQ-o00001 should exist but NOT be linked to REQ-p00001
        # because the literal ID "REQ-p00001-A+B+C" doesn't match any node
        o00001 = graph.find_by_id("REQ-o00001")
        assert o00001 is not None

        p00001 = graph.find_by_id("REQ-p00001")
        assert p00001 is not None

        # With no expansion, the literal "REQ-p00001-A+B+C" won't match
        # any node, so o00001 should NOT be a child of p00001
        assert not o00001.has_parent(
            p00001
        ), "With empty separator, multi-assertion should NOT expand"

        # The broken reference should be recorded
        broken = graph.broken_references()
        literal_targets = [br.target_id for br in broken]
        assert "REQ-p00001-A+B+C" in literal_targets, (
            f"Expected broken reference for literal 'REQ-p00001-A+B+C', " f"got {literal_targets}"
        )
