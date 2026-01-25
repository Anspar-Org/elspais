# elspais: expected-broken-links 4
"""Tests for core/tree_builder.py - Tree builder for traceability trees."""

from pathlib import Path

import pytest


class TestTraceGraphBuilder:
    """Tests for TraceGraphBuilder class."""

    @pytest.fixture
    def builder(self, tmp_path):
        """Create a builder for testing."""
        from elspais.core.graph_builder import TraceGraphBuilder

        return TraceGraphBuilder(repo_root=tmp_path)

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

        from elspais.core.graph import NodeKind

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
        from elspais.core.graph import NodeKind, SourceLocation, TestReference, TraceNode

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
        from elspais.core.graph_builder import ValidationResult

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
        from elspais.core.graph_builder import TraceGraphBuilder

        builder = TraceGraphBuilder(repo_root=tmp_path)
        builder.add_requirements(cyclic_requirements)
        tree, result = builder.build_and_validate()

        assert result.is_valid is False
        assert len(result.errors) > 0
        assert any("Cycle" in e for e in result.errors)

    def test_validate_detects_broken_links(self, tmp_path):
        """Test that validation detects broken links."""
        from elspais.core.models import Requirement
        from elspais.core.graph_builder import TraceGraphBuilder

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

        builder = TraceGraphBuilder(repo_root=tmp_path)
        builder.add_requirements(requirements)
        tree, result = builder.build_and_validate()

        assert len(result.warnings) > 0
        assert any("Broken link" in w or "nonexistent" in w for w in result.warnings)


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_build_graph_from_requirements(self, tmp_path):
        """Test build_graph_from_requirements function."""
        from elspais.core.models import Requirement
        from elspais.core.graph_builder import build_graph_from_requirements

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

        tree = build_graph_from_requirements(requirements, tmp_path)

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
        from elspais.core.graph_builder import TraceGraphBuilder

        # Load requirements
        config_dict = load_config(hht_like_fixture / ".elspais.toml")
        pattern_config = PatternConfig.from_dict(config_dict.get("patterns", {}))
        parser = RequirementParser(pattern_config)
        requirements = parser.parse_directory(hht_like_fixture / "spec")

        # Build tree
        builder = TraceGraphBuilder(repo_root=hht_like_fixture)
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
        from elspais.core.graph import NodeKind
        from elspais.core.graph_builder import TraceGraphBuilder

        # Load requirements
        config_dict = load_config(hht_like_fixture / ".elspais.toml")
        pattern_config = PatternConfig.from_dict(config_dict.get("patterns", {}))
        parser = RequirementParser(pattern_config)
        requirements = parser.parse_directory(hht_like_fixture / "spec")

        # Build tree
        builder = TraceGraphBuilder(repo_root=hht_like_fixture)
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


class TestRelationshipTypeValidation:
    """Tests for relationship type constraint validation.

    The graph schema defines valid source/target types for relationships:
    - implements: from_kind=["requirement"], to_kind=["requirement"]
    - validates:  from_kind=["test", "code"], to_kind=["requirement", "assertion"]
    - addresses:  from_kind=["requirement"], to_kind=["user_journey"]
    - produces:   from_kind=["test"], to_kind=["test_result"]

    These tests verify that the graph builder validates these constraints
    and produces warnings when invalid relationships are created.
    """

    @pytest.fixture
    def builder(self, tmp_path):
        """Create a builder for testing."""
        from elspais.core.graph_builder import TraceGraphBuilder

        return TraceGraphBuilder(repo_root=tmp_path)

    @pytest.fixture
    def prd_requirement(self):
        """Create a PRD requirement for testing."""
        from elspais.core.models import Requirement

        return Requirement(
            id="REQ-p00001",
            title="User Authentication",
            level="PRD",
            status="Active",
            body="The system SHALL authenticate users.",
            implements=[],
            assertions=[],
            acceptance_criteria=[],
        )

    @pytest.fixture
    def dev_requirement(self):
        """Create a DEV requirement that implements the PRD."""
        from elspais.core.models import Requirement

        return Requirement(
            id="REQ-d00001",
            title="Implement Login",
            level="DEV",
            status="Active",
            body="Implement login endpoint.",
            implements=["REQ-p00001"],  # Valid: requirement implements requirement
            assertions=[],
            acceptance_criteria=[],
        )

    def test_valid_implements_relationship(self, builder, prd_requirement, dev_requirement):
        """Test valid implements: requirement -> requirement.

        This is the standard hierarchy relationship where a DEV requirement
        implements a PRD requirement. This should produce NO validation warnings.
        """
        requirements = {
            "REQ-p00001": prd_requirement,
            "REQ-d00001": dev_requirement,
        }

        builder.add_requirements(requirements)
        graph, result = builder.build_and_validate()

        # Should have no type constraint warnings
        type_warnings = [
            w for w in result.warnings
            if "Invalid relationship" in w or "Invalid target" in w
        ]
        assert len(type_warnings) == 0, f"Unexpected type warnings: {type_warnings}"

        # Verify the relationship was created
        dev_node = graph.find_by_id("REQ-d00001")
        prd_node = graph.find_by_id("REQ-p00001")
        assert dev_node is not None
        assert prd_node is not None
        assert prd_node in dev_node.parents

    def test_invalid_implements_from_test(self, builder, prd_requirement):
        """Test invalid implements: test cannot implement requirement.

        Tests should use 'validates' not 'implements' to link to requirements.
        A test node using 'implements' should produce a validation warning.
        """
        from elspais.core.graph import NodeKind, SourceLocation, TestReference, TraceNode

        # Add the requirement first
        requirements = {"REQ-p00001": prd_requirement}
        builder.add_requirements(requirements)

        # Create a test node that incorrectly uses "implements" instead of "validates"
        test_node = TraceNode(
            id="test_auth::test_login",
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
        # Queue an "implements" relationship from test -> requirement (invalid!)
        builder._pending_links.append((test_node.id, "REQ-p00001", "implements"))
        builder._nodes[test_node.id] = test_node

        graph, result = builder.build_and_validate()

        # Should have a warning about invalid from_kind
        type_warnings = [
            w for w in result.warnings
            if "Invalid relationship" in w and "test" in w.lower()
        ]
        assert len(type_warnings) > 0, (
            f"Expected warning about test using 'implements'. "
            f"Warnings: {result.warnings}"
        )

    def test_valid_validates_from_test(self, builder, prd_requirement):
        """Test valid validates: test -> requirement.

        Tests validating requirements is the correct relationship type.
        This should produce NO validation warnings.
        """
        from elspais.core.graph import NodeKind, SourceLocation, TestReference, TraceNode

        # Add the requirement first
        requirements = {"REQ-p00001": prd_requirement}
        builder.add_requirements(requirements)

        # Create a test node that correctly uses "validates"
        test_node = TraceNode(
            id="test_auth::test_login",
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
        test_node.metrics["_validates_targets"] = ["REQ-p00001"]

        builder.add_test_coverage([test_node])
        graph, result = builder.build_and_validate()

        # Should have no type constraint warnings
        type_warnings = [
            w for w in result.warnings
            if "Invalid relationship" in w or "Invalid target" in w
        ]
        assert len(type_warnings) == 0, f"Unexpected type warnings: {type_warnings}"

        # Verify the relationship was created
        test = graph.find_by_id("test_auth::test_login")
        prd_node = graph.find_by_id("REQ-p00001")
        assert test is not None
        assert prd_node is not None
        # Test should have requirement as parent (validates is "up" direction)
        assert prd_node in test.parents

    def test_valid_validates_from_code(self, builder, prd_requirement):
        """Test valid validates: code -> requirement.

        Code references (via # Implements: comments) validating requirements
        is a valid relationship type. This should produce NO validation warnings.
        """
        from elspais.core.graph import CodeReference, NodeKind, SourceLocation, TraceNode

        # Add the requirement first
        requirements = {"REQ-p00001": prd_requirement}
        builder.add_requirements(requirements)

        # Create a code reference node that validates a requirement
        code_node = TraceNode(
            id="src/auth.py:25:login",
            kind=NodeKind.CODE,
            label="login()",
            source=SourceLocation(path="src/auth.py", line=25),
            code_ref=CodeReference(
                file_path="src/auth.py",
                line=25,
                symbol="login",
            ),
        )
        code_node.metrics["_validates_targets"] = ["REQ-p00001"]

        builder.add_code_references([code_node])
        graph, result = builder.build_and_validate()

        # Should have no type constraint warnings
        type_warnings = [
            w for w in result.warnings
            if "Invalid relationship" in w or "Invalid target" in w
        ]
        assert len(type_warnings) == 0, f"Unexpected type warnings: {type_warnings}"

    def test_valid_validates_assertion(self, builder):
        """Test valid validates: test -> assertion.

        Tests can validate specific assertions (e.g., REQ-d00001-A).
        This should produce NO validation warnings.
        """
        from elspais.core.graph import NodeKind, SourceLocation, TestReference, TraceNode
        from elspais.core.models import Assertion, Requirement

        # Create requirement with assertion
        req = Requirement(
            id="REQ-d00001",
            title="Login Implementation",
            level="DEV",
            status="Active",
            body="Implement login.",
            implements=[],
            assertions=[
                Assertion(label="A", text="SHALL accept credentials", is_placeholder=False),
            ],
            acceptance_criteria=[],
        )
        builder.add_requirements({"REQ-d00001": req})

        # Create a test node that validates the assertion
        test_node = TraceNode(
            id="test_auth::test_credentials",
            kind=NodeKind.TEST,
            label="test_credentials",
            source=SourceLocation(path="tests/test_auth.py", line=20),
            test_ref=TestReference(
                file_path="tests/test_auth.py",
                line=20,
                test_name="test_credentials",
                test_class="TestAuth",
            ),
        )
        test_node.metrics["_validates_targets"] = ["REQ-d00001-A"]

        builder.add_test_coverage([test_node])
        graph, result = builder.build_and_validate()

        # Should have no type constraint warnings
        type_warnings = [
            w for w in result.warnings
            if "Invalid relationship" in w or "Invalid target" in w
        ]
        assert len(type_warnings) == 0, f"Unexpected type warnings: {type_warnings}"

        # Verify the relationship was created to the assertion
        test = graph.find_by_id("test_auth::test_credentials")
        assertion_node = graph.find_by_id("REQ-d00001-A")
        assert test is not None
        assert assertion_node is not None
        assert assertion_node in test.parents

    def test_invalid_validates_target_user_journey(self, builder):
        """Test invalid validates: cannot target user_journey.

        The validates relationship can only target requirement or assertion nodes,
        not user_journey nodes. This should produce a validation warning.
        """
        from elspais.core.graph import NodeKind, SourceLocation, TestReference, TraceNode, UserJourney

        # Create a user journey
        journey_node = TraceNode(
            id="JNY-Auth-01",
            kind=NodeKind.USER_JOURNEY,
            label="JNY-Auth-01: User Login",
            source=SourceLocation(path="spec/journeys/auth.md", line=1),
            journey=UserJourney(
                id="JNY-Auth-01",
                actor="End User",
                goal="Login to system",
                steps=["Navigate to login", "Enter credentials", "Click submit"],
            ),
        )
        builder.add_user_journeys({"JNY-Auth-01": journey_node})

        # Create a test node that incorrectly tries to validate a user journey
        test_node = TraceNode(
            id="test_auth::test_journey",
            kind=NodeKind.TEST,
            label="test_journey",
            source=SourceLocation(path="tests/test_auth.py", line=30),
            test_ref=TestReference(
                file_path="tests/test_auth.py",
                line=30,
                test_name="test_journey",
                test_class="TestAuth",
            ),
        )
        test_node.metrics["_validates_targets"] = ["JNY-Auth-01"]

        builder.add_test_coverage([test_node])
        graph, result = builder.build_and_validate()

        # Should have a warning about invalid target kind
        type_warnings = [
            w for w in result.warnings
            if "Invalid target" in w and "journey" in w.lower()
        ]
        assert len(type_warnings) > 0, (
            f"Expected warning about validates targeting user_journey. "
            f"Warnings: {result.warnings}"
        )

    def test_invalid_implements_target_assertion(self, builder, prd_requirement):
        """Test invalid implements: requirement cannot implement assertion.

        The implements relationship should only target other requirements,
        not assertions. Attempting to implement an assertion should produce
        a validation warning.
        """
        from elspais.core.models import Assertion, Requirement

        # Create a requirement with an assertion
        dev_req = Requirement(
            id="REQ-d00001",
            title="Dev Req",
            level="DEV",
            status="Active",
            body="",
            implements=["REQ-p00001-A"],  # Invalid: trying to implement an assertion
            assertions=[],
            acceptance_criteria=[],
        )

        # Create the PRD with an assertion
        prd_with_assertion = Requirement(
            id="REQ-p00001",
            title="PRD Req",
            level="PRD",
            status="Active",
            body="",
            implements=[],
            assertions=[
                Assertion(label="A", text="SHALL do something", is_placeholder=False),
            ],
            acceptance_criteria=[],
        )

        requirements = {
            "REQ-p00001": prd_with_assertion,
            "REQ-d00001": dev_req,
        }
        builder.add_requirements(requirements)
        graph, result = builder.build_and_validate()

        # Should have a warning about invalid target kind
        type_warnings = [
            w for w in result.warnings
            if "Invalid target" in w and "assertion" in w.lower()
        ]
        assert len(type_warnings) > 0, (
            f"Expected warning about implements targeting assertion. "
            f"Warnings: {result.warnings}"
        )

    def test_relationship_validation_in_build_and_validate(self, builder, prd_requirement):
        """Test that validation warnings appear in ValidationResult.

        This is an integration test to verify the full flow:
        1. Create invalid relationships
        2. Call build_and_validate()
        3. ValidationResult.warnings contains type constraint messages
        """
        from elspais.core.graph import NodeKind, SourceLocation, TestReference, TraceNode

        # Add requirement
        requirements = {"REQ-p00001": prd_requirement}
        builder.add_requirements(requirements)

        # Create test with invalid "implements" relationship
        test_node = TraceNode(
            id="test_invalid",
            kind=NodeKind.TEST,
            label="test_invalid",
            source=SourceLocation(path="tests/test.py", line=1),
            test_ref=TestReference(
                file_path="tests/test.py",
                line=1,
                test_name="test_invalid",
            ),
        )
        builder._nodes[test_node.id] = test_node
        builder._pending_links.append((test_node.id, "REQ-p00001", "implements"))

        graph, result = builder.build_and_validate()

        # Verify ValidationResult structure
        assert hasattr(result, "is_valid")
        assert hasattr(result, "errors")
        assert hasattr(result, "warnings")
        assert hasattr(result, "info")

        # Should have type constraint warning
        all_messages = result.errors + result.warnings
        type_messages = [
            m for m in all_messages
            if "Invalid relationship" in m or "Invalid target" in m
        ]
        assert len(type_messages) > 0, (
            f"Expected type constraint message in ValidationResult. "
            f"Errors: {result.errors}, Warnings: {result.warnings}"
        )

    def test_multiple_invalid_relationships(self, builder):
        """Test multiple invalid relationships produce multiple warnings.

        When there are several type constraint violations, each should
        produce its own warning message.
        """
        from elspais.core.graph import NodeKind, SourceLocation, TestReference, TraceNode, UserJourney
        from elspais.core.models import Requirement

        # Create requirement and journey
        req = Requirement(
            id="REQ-p00001",
            title="Test Req",
            level="PRD",
            status="Active",
            body="",
            implements=[],
            assertions=[],
            acceptance_criteria=[],
        )
        builder.add_requirements({"REQ-p00001": req})

        journey_node = TraceNode(
            id="JNY-Test-01",
            kind=NodeKind.USER_JOURNEY,
            label="JNY-Test-01",
            source=SourceLocation(path="spec/journeys.md", line=1),
            journey=UserJourney(
                id="JNY-Test-01",
                actor="User",
                goal="Test",
            ),
        )
        builder.add_user_journeys({"JNY-Test-01": journey_node})

        # Create two test nodes with different invalid relationships
        test1 = TraceNode(
            id="test1",
            kind=NodeKind.TEST,
            label="test1",
            source=SourceLocation(path="tests/test.py", line=1),
            test_ref=TestReference(file_path="tests/test.py", line=1, test_name="test1"),
        )
        test2 = TraceNode(
            id="test2",
            kind=NodeKind.TEST,
            label="test2",
            source=SourceLocation(path="tests/test.py", line=10),
            test_ref=TestReference(file_path="tests/test.py", line=10, test_name="test2"),
        )

        builder._nodes[test1.id] = test1
        builder._nodes[test2.id] = test2

        # test1 uses invalid "implements" (wrong from_kind)
        builder._pending_links.append((test1.id, "REQ-p00001", "implements"))
        # test2 validates a journey (wrong to_kind)
        builder._pending_links.append((test2.id, "JNY-Test-01", "validates"))

        graph, result = builder.build_and_validate()

        # Count type constraint warnings
        type_warnings = [
            w for w in result.warnings
            if "Invalid relationship" in w or "Invalid target" in w
        ]

        # Should have at least 2 warnings (one for each invalid relationship)
        assert len(type_warnings) >= 2, (
            f"Expected at least 2 type constraint warnings. "
            f"Got {len(type_warnings)}: {type_warnings}"
        )
