"""Tests for core/tree_builder.py - Tree builder for traceability trees."""

from pathlib import Path

import pytest


class TestTraceTreeBuilder:
    """Tests for TraceTreeBuilder class."""

    @pytest.fixture
    def builder(self, tmp_path):
        """Create a builder for testing."""
        from elspais.core.tree_builder import TraceTreeBuilder

        return TraceTreeBuilder(repo_root=tmp_path)

    @pytest.fixture
    def sample_requirements(self):
        """Create sample requirements for testing."""
        from elspais.core.models import Assertion, Requirement

        return {
            "REQ-p00001": Requirement(
                id="REQ-p00001",
                title="User Authentication",
                level="PRD",
                status="Active",
                body="The system SHALL authenticate users.",
                implements=[],
                assertions=[
                    Assertion(label="A", text="SHALL verify credentials", is_placeholder=False),
                ],
                acceptance_criteria=[],
                rationale="Security requirement",
                hash="a1b2c3d4",
                file_path=Path("spec/prd-auth.md"),
                line_number=10,
            ),
            "REQ-o00001": Requirement(
                id="REQ-o00001",
                title="Deploy Authentication",
                level="OPS",
                status="Active",
                body="Deploy auth service.",
                implements=["p00001"],  # Implements PRD
                assertions=[],
                acceptance_criteria=[],
                rationale=None,
                hash="b2c3d4e5",
                file_path=Path("spec/ops-deploy.md"),
                line_number=5,
            ),
            "REQ-d00001": Requirement(
                id="REQ-d00001",
                title="Implement Login",
                level="DEV",
                status="Active",
                body="Implement login endpoint.",
                implements=["o00001"],  # Implements OPS
                assertions=[
                    Assertion(label="A", text="SHALL accept email/password", is_placeholder=False),
                    Assertion(label="B", text="SHALL return JWT token", is_placeholder=False),
                ],
                acceptance_criteria=[],
                rationale=None,
                hash="c3d4e5f6",
                file_path=Path("spec/dev-impl.md"),
                line_number=15,
            ),
        }

    def test_create_builder(self, builder, tmp_path):
        """Test creating a builder."""
        assert builder.repo_root == tmp_path
        assert builder.schema is not None

    def test_add_requirements(self, builder, sample_requirements):
        """Test adding requirements to the builder."""
        builder.add_requirements(sample_requirements)

        # Should have nodes for all requirements
        assert "REQ-p00001" in builder._nodes
        assert "REQ-o00001" in builder._nodes
        assert "REQ-d00001" in builder._nodes

        # Should have assertion nodes
        assert "REQ-p00001-A" in builder._nodes
        assert "REQ-d00001-A" in builder._nodes
        assert "REQ-d00001-B" in builder._nodes

    def test_build_tree(self, builder, sample_requirements):
        """Test building the tree."""
        builder.add_requirements(sample_requirements)
        tree = builder.build()

        # Tree should have one root (PRD requirement)
        assert len(tree.roots) == 1
        assert tree.roots[0].id == "REQ-p00001"

        # Root should have children
        root = tree.roots[0]
        assert len(root.children) >= 1  # At least the assertion

        # Find the OPS requirement in children
        ops_node = tree.find_by_id("REQ-o00001")
        assert ops_node is not None
        assert root in ops_node.parents

    def test_hierarchy_linking(self, builder, sample_requirements):
        """Test that hierarchy is properly linked."""
        builder.add_requirements(sample_requirements)
        tree = builder.build()

        prd_node = tree.find_by_id("REQ-p00001")
        ops_node = tree.find_by_id("REQ-o00001")
        dev_node = tree.find_by_id("REQ-d00001")

        assert prd_node is not None
        assert ops_node is not None
        assert dev_node is not None

        # Check parent-child relationships
        assert ops_node in prd_node.children
        assert prd_node in ops_node.parents

        assert dev_node in ops_node.children
        assert ops_node in dev_node.parents

    def test_assertions_as_children(self, builder, sample_requirements):
        """Test that assertions are children of requirements."""
        builder.add_requirements(sample_requirements)
        tree = builder.build()

        from elspais.core.tree import NodeKind

        dev_node = tree.find_by_id("REQ-d00001")
        assert dev_node is not None

        # Should have assertion children
        assertion_children = [c for c in dev_node.children if c.kind == NodeKind.ASSERTION]
        assert len(assertion_children) == 2

        # Check assertion content
        assertion_a = tree.find_by_id("REQ-d00001-A")
        assert assertion_a is not None
        assert assertion_a.assertion is not None
        assert "email/password" in assertion_a.assertion.text

    def test_add_test_nodes(self, builder, sample_requirements):
        """Test adding test nodes."""
        from elspais.core.tree import NodeKind, SourceLocation, TestReference, TraceNode

        builder.add_requirements(sample_requirements)

        # Create test node
        test_node = TraceNode(
            id="tests/test_auth.py:10:REQ-d00001",
            kind=NodeKind.TEST,
            label="test_login",
            source=SourceLocation(path="tests/test_auth.py", line=10),
            test_ref=TestReference(
                file_path="tests/test_auth.py",
                line=10,
                test_name="test_login",
                test_class="TestAuth",
            ),
        )
        test_node.metrics["_validates_targets"] = ["REQ-d00001"]

        builder.add_test_coverage([test_node])
        tree = builder.build()

        # Test node should be linked to requirement
        test = tree.find_by_id("tests/test_auth.py:10:REQ-d00001")
        assert test is not None

        dev_node = tree.find_by_id("REQ-d00001")
        assert test in dev_node.children or dev_node in test.parents

    def test_method_chaining(self, builder, sample_requirements):
        """Test that builder methods can be chained."""

        tree = builder.add_requirements(sample_requirements).add_nodes([]).build()

        assert tree is not None
        assert len(tree.roots) > 0


class TestValidationResult:
    """Tests for ValidationResult."""

    def test_defaults(self):
        """Test default values."""
        from elspais.core.tree_builder import ValidationResult

        result = ValidationResult()

        assert result.is_valid is True
        assert result.errors == []
        assert result.warnings == []


class TestTreeValidation:
    """Tests for tree validation."""

    @pytest.fixture
    def cyclic_requirements(self):
        """Create requirements with a cycle."""
        from elspais.core.models import Requirement

        return {
            "REQ-p00001": Requirement(
                id="REQ-p00001",
                title="Req A",
                level="PRD",
                status="Active",
                body="",
                implements=["p00002"],  # Cycle: A -> B
                assertions=[],
                acceptance_criteria=[],
            ),
            "REQ-p00002": Requirement(
                id="REQ-p00002",
                title="Req B",
                level="PRD",
                status="Active",
                body="",
                implements=["p00001"],  # Cycle: B -> A
                assertions=[],
                acceptance_criteria=[],
            ),
        }

    def test_validate_detects_cycles(self, cyclic_requirements, tmp_path):
        """Test that validation detects cycles."""
        from elspais.core.tree_builder import TraceTreeBuilder

        builder = TraceTreeBuilder(repo_root=tmp_path)
        builder.add_requirements(cyclic_requirements)
        tree, result = builder.build_and_validate()

        assert result.is_valid is False
        assert len(result.errors) > 0
        assert any("Cycle" in e for e in result.errors)

    def test_validate_detects_broken_links(self, tmp_path):
        """Test that validation detects broken links."""
        from elspais.core.models import Requirement
        from elspais.core.tree_builder import TraceTreeBuilder

        requirements = {
            "REQ-d00001": Requirement(
                id="REQ-d00001",
                title="Dev Req",
                level="DEV",
                status="Active",
                body="",
                implements=["nonexistent"],  # Broken link
                assertions=[],
                acceptance_criteria=[],
            ),
        }

        builder = TraceTreeBuilder(repo_root=tmp_path)
        builder.add_requirements(requirements)
        tree, result = builder.build_and_validate()

        assert len(result.warnings) > 0
        assert any("Broken link" in w or "nonexistent" in w for w in result.warnings)


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_build_tree_from_requirements(self, tmp_path):
        """Test build_tree_from_requirements function."""
        from elspais.core.models import Requirement
        from elspais.core.tree_builder import build_tree_from_requirements

        requirements = {
            "REQ-p00001": Requirement(
                id="REQ-p00001",
                title="Test Req",
                level="PRD",
                status="Active",
                body="",
                implements=[],
                assertions=[],
                acceptance_criteria=[],
            ),
        }

        tree = build_tree_from_requirements(requirements, tmp_path)

        assert tree is not None
        assert len(tree.roots) == 1
        assert tree.roots[0].id == "REQ-p00001"


class TestTreeBuilderIntegration:
    """Integration tests with fixtures."""

    def test_build_from_hht_fixture(self, hht_like_fixture):
        """Test building tree from HHT-like fixture."""
        from elspais.config.loader import load_config
        from elspais.core.parser import RequirementParser
        from elspais.core.patterns import PatternConfig
        from elspais.core.tree_builder import TraceTreeBuilder

        # Load requirements
        config_dict = load_config(hht_like_fixture / ".elspais.toml")
        pattern_config = PatternConfig.from_dict(config_dict.get("patterns", {}))
        parser = RequirementParser(pattern_config)
        requirements = parser.parse_directory(hht_like_fixture / "spec")

        # Build tree
        builder = TraceTreeBuilder(repo_root=hht_like_fixture)
        builder.add_requirements(requirements)
        tree = builder.build()

        # Verify tree structure
        assert tree is not None
        assert len(tree.roots) > 0

        # All roots should be PRD level or have no parents
        for root in tree.roots:
            if root.requirement:
                assert root.requirement.level == "PRD" or not root.parents

    def test_tree_matches_hierarchy_functions(self, hht_like_fixture):
        """Test that tree matches hierarchy module functions."""
        from elspais.config.loader import load_config
        from elspais.core.hierarchy import find_children_ids, find_roots
        from elspais.core.parser import RequirementParser
        from elspais.core.patterns import PatternConfig
        from elspais.core.tree import NodeKind
        from elspais.core.tree_builder import TraceTreeBuilder

        # Load requirements
        config_dict = load_config(hht_like_fixture / ".elspais.toml")
        pattern_config = PatternConfig.from_dict(config_dict.get("patterns", {}))
        parser = RequirementParser(pattern_config)
        requirements = parser.parse_directory(hht_like_fixture / "spec")

        # Build tree
        builder = TraceTreeBuilder(repo_root=hht_like_fixture)
        builder.add_requirements(requirements)
        tree = builder.build()

        # Compare roots
        hierarchy_roots = set(find_roots(requirements))
        tree_root_ids = {r.id for r in tree.roots if r.kind == NodeKind.REQUIREMENT}

        assert hierarchy_roots == tree_root_ids

        # Compare children for each root
        for root_id in hierarchy_roots:
            hierarchy_children = set(find_children_ids(root_id, requirements))
            tree_node = tree.find_by_id(root_id)
            if tree_node:
                tree_children = {c.id for c in tree_node.children if c.kind == NodeKind.REQUIREMENT}
                assert hierarchy_children == tree_children
