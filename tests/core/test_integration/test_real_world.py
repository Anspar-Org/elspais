"""Integration tests against real-world spec/ directory."""

import pytest
from pathlib import Path

from elspais.arch3.Graph import NodeKind
from elspais.arch3.Graph.builder import GraphBuilder, TraceGraph
from elspais.arch3.Graph.deserializer import DomainFile
from elspais.arch3.Graph.MDparser import ParserRegistry
from elspais.arch3.Graph.MDparser.comments import CommentsParser
from elspais.arch3.Graph.MDparser.remainder import RemainderParser
from elspais.arch3.Graph.MDparser.requirement import RequirementParser
from elspais.arch3.config import load_config, find_config_file
from elspais.arch3.utilities.patterns import PatternConfig


# Get repo root (3 levels up from this test file)
REPO_ROOT = Path(__file__).parent.parent.parent.parent
SPEC_DIR = REPO_ROOT / "spec"
CONFIG_FILE = REPO_ROOT / ".elspais.toml"


@pytest.fixture
def pattern_config():
    """Load pattern config from the real .elspais.toml."""
    if not CONFIG_FILE.exists():
        pytest.skip("No .elspais.toml found in repo root")

    config = load_config(CONFIG_FILE)
    patterns_data = config.get_raw().get("patterns", {})

    # Filter out broken inline table entries (parsed as strings by simple parser)
    # and keep only valid dict entries
    types_data = patterns_data.get("types", {})
    adapted_types = {}
    for key, value in types_data.items():
        if isinstance(value, dict):
            # Add 'name' field if not present
            if "name" not in value:
                value = dict(value)  # Make a copy
                value["name"] = key.upper()
            adapted_types[key] = value
    patterns_data["types"] = adapted_types

    return PatternConfig.from_dict(patterns_data)


@pytest.fixture
def parser_registry(pattern_config):
    """Create parser registry with all standard parsers."""
    registry = ParserRegistry()
    registry.register(CommentsParser())
    registry.register(RequirementParser(pattern_config))
    registry.register(RemainderParser())
    return registry


class TestRealWorldSpecs:
    """Tests against the actual spec/ directory."""

    def test_spec_directory_exists(self):
        """Verify spec directory exists for testing."""
        if not SPEC_DIR.exists():
            pytest.skip("No spec/ directory found")
        assert SPEC_DIR.is_dir()

    def test_can_parse_spec_files(self, parser_registry):
        """Verify parser can process real spec files."""
        if not SPEC_DIR.exists():
            pytest.skip("No spec/ directory found")

        deserializer = DomainFile(SPEC_DIR, patterns=["*.md"])
        results = list(deserializer.deserialize(parser_registry))

        # Should get some parsed content
        assert len(results) > 0

    def test_finds_prd_requirements(self, parser_registry):
        """Verify PRD requirements are found in real specs."""
        if not SPEC_DIR.exists():
            pytest.skip("No spec/ directory found")

        deserializer = DomainFile(SPEC_DIR, patterns=["*.md"])

        builder = GraphBuilder(repo_root=REPO_ROOT)
        for content in deserializer.deserialize(parser_registry):
            builder.add_parsed_content(content)

        graph = builder.build()

        # The real spec has REQ-p00001, REQ-p00002, etc.
        prd_reqs = [
            n for n in graph.nodes_by_kind(NodeKind.REQUIREMENT)
            if n.id.startswith("REQ-p")
        ]

        # Should find at least one PRD requirement
        assert len(prd_reqs) > 0

    def test_graph_has_roots(self, parser_registry):
        """Verify graph identifies root requirements."""
        if not SPEC_DIR.exists():
            pytest.skip("No spec/ directory found")

        deserializer = DomainFile(SPEC_DIR, patterns=["*.md"])

        builder = GraphBuilder(repo_root=REPO_ROOT)
        for content in deserializer.deserialize(parser_registry):
            builder.add_parsed_content(content)

        graph = builder.build()

        # Should have at least one root (top-level PRD req)
        assert len(graph.roots) > 0

    def test_assertions_are_created(self, parser_registry):
        """Verify assertions are extracted from requirements."""
        if not SPEC_DIR.exists():
            pytest.skip("No spec/ directory found")

        deserializer = DomainFile(SPEC_DIR, patterns=["*.md"])

        builder = GraphBuilder(repo_root=REPO_ROOT)
        for content in deserializer.deserialize(parser_registry):
            builder.add_parsed_content(content)

        graph = builder.build()

        assertions = list(graph.nodes_by_kind(NodeKind.ASSERTION))

        # Real specs have assertions (A, B, C, etc.)
        assert len(assertions) > 0

    def test_implements_relationships(self, parser_registry):
        """Verify implements relationships are parsed."""
        if not SPEC_DIR.exists():
            pytest.skip("No spec/ directory found")

        deserializer = DomainFile(SPEC_DIR, patterns=["*.md"])

        builder = GraphBuilder(repo_root=REPO_ROOT)
        for content in deserializer.deserialize(parser_registry):
            builder.add_parsed_content(content)

        graph = builder.build()

        # Count requirements with parents (i.e., they implement something)
        reqs_with_parents = [
            n for n in graph.nodes_by_kind(NodeKind.REQUIREMENT)
            if n.parents
        ]

        # Should have at least some hierarchical relationships
        # (e.g., REQ-p00002 implements REQ-p00001)
        assert len(reqs_with_parents) > 0
