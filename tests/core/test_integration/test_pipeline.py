"""Integration tests for full Deserializer → MDparser → Graph pipeline."""

from elspais.config import find_config_file, load_config
from elspais.graph import NodeKind
from elspais.graph.builder import GraphBuilder
from elspais.graph.deserializer import DomainFile
from elspais.graph.parsers import ParserRegistry
from elspais.graph.parsers.comments import CommentsParser
from elspais.graph.parsers.remainder import RemainderParser
from elspais.graph.parsers.requirement import RequirementParser
from elspais.utilities.patterns import PatternConfig


def create_parser_registry(pattern_config: PatternConfig) -> ParserRegistry:
    """Create a parser registry with all standard parsers."""
    registry = ParserRegistry()
    registry.register(CommentsParser())
    registry.register(RequirementParser(pattern_config))
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
        pattern_config = PatternConfig.from_dict(config.get_raw()["patterns"])

        # Create parser registry
        registry = create_parser_registry(pattern_config)

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
        pattern_config = PatternConfig.from_dict(config.get_raw()["patterns"])
        registry = create_parser_registry(pattern_config)

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
        pattern_config = PatternConfig.from_dict(config.get_raw()["patterns"])
        registry = create_parser_registry(pattern_config)

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
        pattern_config = PatternConfig.from_dict(config.get_raw()["patterns"])
        registry = create_parser_registry(pattern_config)

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
        pattern_config = PatternConfig.from_dict(config.get_raw()["patterns"])
        registry = create_parser_registry(pattern_config)

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
