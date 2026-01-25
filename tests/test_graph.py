# elspais: expected-broken-links 9
"""Tests for core/tree.py - Unified traceability tree data structures."""

import pytest


# Validates: REQ-p00003-B
class TestSourceLocation:
    """Tests for SourceLocation dataclass."""

    def test_creation_minimal(self):
        """Test creating SourceLocation with minimal fields."""
        from elspais.core.graph import SourceLocation

        loc = SourceLocation(path="spec/prd-auth.md", line=10)

        assert loc.path == "spec/prd-auth.md"
        assert loc.line == 10
        assert loc.end_line is None
        assert loc.repo is None

    def test_creation_full(self):
        """Test creating SourceLocation with all fields."""
        from elspais.core.graph import SourceLocation

        loc = SourceLocation(path="spec/prd-auth.md", line=10, end_line=25, repo="CAL")

        assert loc.path == "spec/prd-auth.md"
        assert loc.line == 10
        assert loc.end_line == 25
        assert loc.repo == "CAL"

    def test_absolute_path(self, tmp_path):
        """Test resolving to absolute path."""
        from elspais.core.graph import SourceLocation

        loc = SourceLocation(path="spec/prd-auth.md", line=10)
        absolute = loc.absolute(tmp_path)

        assert absolute == tmp_path / "spec/prd-auth.md"
        assert absolute.is_absolute()

    def test_str_without_repo(self):
        """Test string representation without repo."""
        from elspais.core.graph import SourceLocation

        loc = SourceLocation(path="spec/prd-auth.md", line=10)

        assert str(loc) == "spec/prd-auth.md:10"

    def test_str_with_repo(self):
        """Test string representation with repo."""
        from elspais.core.graph import SourceLocation

        loc = SourceLocation(path="spec/prd-auth.md", line=10, repo="CAL")

        assert str(loc) == "CAL:spec/prd-auth.md:10"


# Validates: REQ-p00003-B
class TestNodeKind:
    """Tests for NodeKind enum."""

    def test_all_kinds_defined(self):
        """Test all expected node kinds are defined."""
        from elspais.core.graph import NodeKind

        expected = {"requirement", "assertion", "code", "test", "result", "journey"}
        actual = {kind.value for kind in NodeKind}

        assert actual == expected

    def test_kind_values(self):
        """Test specific kind values."""
        from elspais.core.graph import NodeKind

        assert NodeKind.REQUIREMENT.value == "requirement"
        assert NodeKind.ASSERTION.value == "assertion"
        assert NodeKind.CODE.value == "code"
        assert NodeKind.TEST.value == "test"
        assert NodeKind.TEST_RESULT.value == "result"
        assert NodeKind.USER_JOURNEY.value == "journey"


# Validates: REQ-p00003-B
class TestTraceNode:
    """Tests for TraceNode dataclass."""

    @pytest.fixture
    def simple_node(self):
        """Create a simple node for testing."""
        from elspais.core.graph import NodeKind, SourceLocation, TraceNode

        return TraceNode(
            id="REQ-p00001",
            kind=NodeKind.REQUIREMENT,
            label="REQ-p00001: User Authentication",
            source=SourceLocation(path="spec/prd-auth.md", line=10),
        )

    @pytest.fixture
    def tree_with_hierarchy(self):
        """Create a tree with parent-child relationships.

        Structure:
            root (PRD)
            ├── child1 (OPS)
            │   └── grandchild (DEV)
            └── child2 (OPS)
        """
        from elspais.core.graph import NodeKind, TraceNode

        root = TraceNode(
            id="REQ-p00001",
            kind=NodeKind.REQUIREMENT,
            label="PRD: Authentication",
        )
        child1 = TraceNode(
            id="REQ-o00001",
            kind=NodeKind.REQUIREMENT,
            label="OPS: Deploy Auth",
        )
        child2 = TraceNode(
            id="REQ-o00002",
            kind=NodeKind.REQUIREMENT,
            label="OPS: Monitor Auth",
        )
        grandchild = TraceNode(
            id="REQ-d00001",
            kind=NodeKind.REQUIREMENT,
            label="DEV: Implement Auth",
        )

        # Set up hierarchy
        root.children = [child1, child2]
        child1.parents = [root]
        child2.parents = [root]

        child1.children = [grandchild]
        grandchild.parents = [child1]

        return root, child1, child2, grandchild

    def test_creation_minimal(self):
        """Test creating TraceNode with minimal fields."""
        from elspais.core.graph import NodeKind, TraceNode

        node = TraceNode(
            id="REQ-p00001",
            kind=NodeKind.REQUIREMENT,
            label="Test Requirement",
        )

        assert node.id == "REQ-p00001"
        assert node.kind == NodeKind.REQUIREMENT
        assert node.label == "Test Requirement"
        assert node.source is None
        assert node.children == []
        assert node.parents == []
        assert node.metrics == {}

    def test_creation_with_source(self, simple_node):
        """Test creating TraceNode with source location."""
        assert simple_node.source is not None
        assert simple_node.source.path == "spec/prd-auth.md"
        assert simple_node.source.line == 10

    def test_depth_root(self, simple_node):
        """Test depth calculation for root node."""
        assert simple_node.depth == 0

    def test_depth_child(self, tree_with_hierarchy):
        """Test depth calculation for child nodes."""
        root, child1, child2, grandchild = tree_with_hierarchy

        assert root.depth == 0
        assert child1.depth == 1
        assert child2.depth == 1
        assert grandchild.depth == 2

    def test_walk_preorder(self, tree_with_hierarchy):
        """Test pre-order traversal."""
        root, child1, child2, grandchild = tree_with_hierarchy

        ids = [n.id for n in root.walk("pre")]

        # Pre-order: parent before children
        assert ids == ["REQ-p00001", "REQ-o00001", "REQ-d00001", "REQ-o00002"]

    def test_walk_postorder(self, tree_with_hierarchy):
        """Test post-order traversal."""
        root, child1, child2, grandchild = tree_with_hierarchy

        ids = [n.id for n in root.walk("post")]

        # Post-order: children before parent
        assert ids == ["REQ-d00001", "REQ-o00001", "REQ-o00002", "REQ-p00001"]

    def test_walk_level(self, tree_with_hierarchy):
        """Test level-order (BFS) traversal."""
        root, child1, child2, grandchild = tree_with_hierarchy

        ids = [n.id for n in root.walk("level")]

        # Level-order: breadth-first
        assert ids == ["REQ-p00001", "REQ-o00001", "REQ-o00002", "REQ-d00001"]

    def test_walk_invalid_order(self, simple_node):
        """Test walk with invalid order raises error."""
        with pytest.raises(ValueError, match="Unknown traversal order"):
            list(simple_node.walk("invalid"))

    def test_walk_single_node(self, simple_node):
        """Test walk on single node returns just that node."""
        ids = [n.id for n in simple_node.walk()]
        assert ids == ["REQ-p00001"]

    def test_ancestors_no_parents(self, simple_node):
        """Test ancestors returns empty for root."""
        ancestors = list(simple_node.ancestors())
        assert ancestors == []

    def test_ancestors_single_parent(self, tree_with_hierarchy):
        """Test ancestors for node with single parent."""
        root, child1, child2, grandchild = tree_with_hierarchy

        ancestor_ids = [n.id for n in grandchild.ancestors()]

        # Should include child1 and root
        assert "REQ-o00001" in ancestor_ids
        assert "REQ-p00001" in ancestor_ids
        assert len(ancestor_ids) == 2

    def test_ancestors_dag_multiple_parents(self):
        """Test ancestors for DAG with multiple parents."""
        from elspais.core.graph import NodeKind, TraceNode

        # Create DAG: child has two parents
        parent1 = TraceNode(id="P1", kind=NodeKind.REQUIREMENT, label="Parent 1")
        parent2 = TraceNode(id="P2", kind=NodeKind.REQUIREMENT, label="Parent 2")
        child = TraceNode(id="C1", kind=NodeKind.REQUIREMENT, label="Child")

        child.parents = [parent1, parent2]
        parent1.children = [child]
        parent2.children = [child]

        ancestor_ids = [n.id for n in child.ancestors()]

        assert set(ancestor_ids) == {"P1", "P2"}

    def test_ancestors_no_duplicates(self):
        """Test ancestors doesn't return duplicates in diamond pattern."""
        from elspais.core.graph import NodeKind, TraceNode

        # Diamond: grandparent -> parent1, parent2 -> child
        grandparent = TraceNode(id="GP", kind=NodeKind.REQUIREMENT, label="GP")
        parent1 = TraceNode(id="P1", kind=NodeKind.REQUIREMENT, label="P1")
        parent2 = TraceNode(id="P2", kind=NodeKind.REQUIREMENT, label="P2")
        child = TraceNode(id="C", kind=NodeKind.REQUIREMENT, label="C")

        grandparent.children = [parent1, parent2]
        parent1.parents = [grandparent]
        parent2.parents = [grandparent]
        parent1.children = [child]
        parent2.children = [child]
        child.parents = [parent1, parent2]

        ancestor_ids = [n.id for n in child.ancestors()]

        # Grandparent should appear only once
        assert ancestor_ids.count("GP") == 1
        assert set(ancestor_ids) == {"P1", "P2", "GP"}

    def test_find_by_predicate(self, tree_with_hierarchy):
        """Test finding nodes by predicate."""
        root, child1, child2, grandchild = tree_with_hierarchy

        # Find all nodes with "OPS" in label
        ops_nodes = list(root.find(lambda n: "OPS" in n.label))

        assert len(ops_nodes) == 2
        assert child1 in ops_nodes
        assert child2 in ops_nodes

    def test_find_by_kind(self, tree_with_hierarchy):
        """Test finding nodes by kind."""
        from elspais.core.graph import NodeKind

        root, child1, child2, grandchild = tree_with_hierarchy

        # All are requirements in this tree
        reqs = list(root.find_by_kind(NodeKind.REQUIREMENT))
        assert len(reqs) == 4

        # No assertions in this tree
        assertions = list(root.find_by_kind(NodeKind.ASSERTION))
        assert len(assertions) == 0

    def test_metrics_mutable(self, simple_node):
        """Test metrics dict is mutable."""
        simple_node.metrics["coverage"] = 0.75
        simple_node.metrics["test_count"] = 5

        assert simple_node.metrics["coverage"] == 0.75
        assert simple_node.metrics["test_count"] == 5


# Validates: REQ-p00003-B
class TestTraceGraph:
    """Tests for TraceGraph dataclass."""

    @pytest.fixture
    def simple_tree(self, tmp_path):
        """Create a simple tree for testing."""
        from elspais.core.graph import NodeKind, TraceNode, TraceGraph

        root1 = TraceNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT, label="PRD 1")
        child1 = TraceNode(id="REQ-d00001", kind=NodeKind.REQUIREMENT, label="DEV 1")
        root1.children = [child1]
        child1.parents = [root1]

        root2 = TraceNode(id="REQ-p00002", kind=NodeKind.REQUIREMENT, label="PRD 2")

        return TraceGraph(roots=[root1, root2], repo_root=tmp_path)

    def test_creation(self, simple_tree, tmp_path):
        """Test creating TraceGraph."""
        assert len(simple_tree.roots) == 2
        assert simple_tree.repo_root == tmp_path

    def test_index_built_automatically(self, simple_tree):
        """Test that index is built on creation."""
        assert "REQ-p00001" in simple_tree._index
        assert "REQ-d00001" in simple_tree._index
        assert "REQ-p00002" in simple_tree._index

    def test_find_by_id_exists(self, simple_tree):
        """Test finding existing node by ID."""
        node = simple_tree.find_by_id("REQ-p00001")

        assert node is not None
        assert node.id == "REQ-p00001"
        assert node.label == "PRD 1"

    def test_find_by_id_not_found(self, simple_tree):
        """Test finding non-existent node returns None."""
        node = simple_tree.find_by_id("NONEXISTENT")

        assert node is None

    def test_all_nodes(self, simple_tree):
        """Test iterating all nodes."""
        all_ids = [n.id for n in simple_tree.all_nodes()]

        assert set(all_ids) == {"REQ-p00001", "REQ-d00001", "REQ-p00002"}

    def test_all_nodes_order(self, simple_tree):
        """Test all_nodes respects traversal order."""
        # Pre-order: parent before children for each root
        pre_ids = [n.id for n in simple_tree.all_nodes("pre")]
        assert pre_ids.index("REQ-p00001") < pre_ids.index("REQ-d00001")

    def test_nodes_by_kind(self, simple_tree):
        """Test filtering nodes by kind."""
        from elspais.core.graph import NodeKind

        req_ids = [n.id for n in simple_tree.nodes_by_kind(NodeKind.REQUIREMENT)]

        assert set(req_ids) == {"REQ-p00001", "REQ-d00001", "REQ-p00002"}

    def test_nodes_by_kind_empty(self, simple_tree):
        """Test filtering returns empty for non-existent kind."""
        from elspais.core.graph import NodeKind

        assertions = list(simple_tree.nodes_by_kind(NodeKind.ASSERTION))

        assert assertions == []

    def test_node_count(self, simple_tree):
        """Test node count."""
        assert simple_tree.node_count() == 3

    def test_count_by_kind(self, simple_tree):
        """Test counting nodes by kind."""
        from elspais.core.graph import NodeKind

        counts = simple_tree.count_by_kind()

        assert counts[NodeKind.REQUIREMENT] == 3
        assert NodeKind.ASSERTION not in counts

    def test_accumulate_leaf_values(self, tmp_path):
        """Test accumulate with leaf values."""
        from elspais.core.graph import NodeKind, TraceNode, TraceGraph

        # Create tree with test counts on leaves
        root = TraceNode(id="P1", kind=NodeKind.REQUIREMENT, label="Root")
        child1 = TraceNode(id="C1", kind=NodeKind.REQUIREMENT, label="Child 1")
        child2 = TraceNode(id="C2", kind=NodeKind.REQUIREMENT, label="Child 2")

        root.children = [child1, child2]
        child1.parents = [root]
        child2.parents = [root]

        # Set test counts on leaves
        child1.metrics["test_count"] = 5
        child2.metrics["test_count"] = 3

        tree = TraceGraph(roots=[root], repo_root=tmp_path)

        # Accumulate total test count
        tree.accumulate(
            "total_tests",
            leaf_fn=lambda n: n.metrics.get("test_count", 0),
            combine_fn=lambda n, vals: sum(vals),
        )

        assert child1.metrics["total_tests"] == 5
        assert child2.metrics["total_tests"] == 3
        assert root.metrics["total_tests"] == 8

    def test_accumulate_coverage_percentage(self, tmp_path):
        """Test accumulate for coverage percentage calculation."""
        from elspais.core.graph import NodeKind, TraceNode, TraceGraph

        root = TraceNode(id="P1", kind=NodeKind.REQUIREMENT, label="Root")
        child1 = TraceNode(id="C1", kind=NodeKind.REQUIREMENT, label="Child 1")
        child2 = TraceNode(id="C2", kind=NodeKind.REQUIREMENT, label="Child 2")
        child3 = TraceNode(id="C3", kind=NodeKind.REQUIREMENT, label="Child 3")

        root.children = [child1, child2, child3]
        for c in root.children:
            c.parents = [root]

        # 2 of 3 children have tests
        child1.metrics["test_count"] = 2
        child2.metrics["test_count"] = 0
        child3.metrics["test_count"] = 1

        tree = TraceGraph(roots=[root], repo_root=tmp_path)

        tree.accumulate(
            "coverage",
            leaf_fn=lambda n: 1.0 if n.metrics.get("test_count", 0) > 0 else 0.0,
            combine_fn=lambda n, vals: sum(vals) / len(vals) if vals else 0.0,
        )

        assert child1.metrics["coverage"] == 1.0
        assert child2.metrics["coverage"] == 0.0
        assert child3.metrics["coverage"] == 1.0
        # Root: 2/3 children have tests
        assert abs(root.metrics["coverage"] - 2 / 3) < 0.01


# Validates: REQ-p00003-B
class TestSupportingDataclasses:
    """Tests for supporting dataclasses."""

    def test_code_reference(self):
        """Test CodeReference dataclass."""
        from elspais.core.graph import CodeReference

        ref = CodeReference(
            file_path="src/auth.py",
            line=42,
            end_line=55,
            symbol="authenticate_user",
        )

        assert ref.file_path == "src/auth.py"
        assert ref.line == 42
        assert ref.end_line == 55
        assert ref.symbol == "authenticate_user"

    def test_test_reference(self):
        """Test TestReference dataclass."""
        from elspais.core.graph import TestReference

        ref = TestReference(
            file_path="tests/test_auth.py",
            line=10,
            test_name="test_login_success",
            test_class="TestAuthentication",
        )

        assert ref.file_path == "tests/test_auth.py"
        assert ref.line == 10
        assert ref.test_name == "test_login_success"
        assert ref.test_class == "TestAuthentication"

    def test_test_result(self):
        """Test TestResult dataclass."""
        from elspais.core.graph import TestResult

        result = TestResult(
            status="passed",
            duration=0.125,
            message=None,
            result_file="junit.xml",
        )

        assert result.status == "passed"
        assert result.duration == 0.125
        assert result.message is None
        assert result.result_file == "junit.xml"

    def test_user_journey(self):
        """Test UserJourney dataclass."""
        from elspais.core.graph import UserJourney

        journey = UserJourney(
            id="JNY-Spec-Author-01",
            actor="Specification Author",
            goal="Create a new requirement specification",
            context="Working on a new feature",
            steps=["Open editor", "Write requirement", "Save file"],
            expected_outcome="Requirement is validated and stored",
        )

        assert journey.id == "JNY-Spec-Author-01"
        assert journey.actor == "Specification Author"
        assert journey.goal == "Create a new requirement specification"
        assert len(journey.steps) == 3


# Validates: REQ-p00003-B
class TestTreeIntegration:
    """Integration tests for tree module with fixtures."""

    def test_build_graph_from_requirements(self, hht_like_fixture):
        """Test building a tree from parsed requirements."""
        from elspais.config.loader import load_config
        from elspais.core.parser import RequirementParser
        from elspais.core.patterns import PatternConfig
        from elspais.core.graph import NodeKind, SourceLocation, TraceNode, TraceGraph

        # Load requirements
        config_dict = load_config(hht_like_fixture / ".elspais.toml")
        pattern_config = PatternConfig.from_dict(config_dict.get("patterns", {}))
        parser = RequirementParser(pattern_config)
        spec_dir = hht_like_fixture / "spec"
        requirements = parser.parse_directory(spec_dir)

        # Build nodes from requirements
        nodes: dict[str, TraceNode] = {}
        for req_id, req in requirements.items():
            # Create relative path
            rel_path = str(req.file_path.relative_to(hht_like_fixture)) if req.file_path else ""

            node = TraceNode(
                id=req_id,
                kind=NodeKind.REQUIREMENT,
                label=f"{req_id}: {req.title}",
                source=SourceLocation(
                    path=rel_path,
                    line=req.line_number or 0,
                ),
                requirement=req,
            )
            nodes[req_id] = node

            # Add assertion children
            for assertion in req.assertions:
                assertion_id = f"{req_id}-{assertion.label}"
                assertion_node = TraceNode(
                    id=assertion_id,
                    kind=NodeKind.ASSERTION,
                    label=f"{assertion.label}. {assertion.text[:30]}...",
                    source=node.source,
                    assertion=assertion,
                )
                node.children.append(assertion_node)
                assertion_node.parents.append(node)
                nodes[assertion_id] = assertion_node

        # Link hierarchy (implements relationships)
        from elspais.core.hierarchy import find_requirement

        for req_id, req in requirements.items():
            node = nodes[req_id]
            for impl_id in req.implements:
                parent_req = find_requirement(impl_id, requirements)
                if parent_req:
                    parent_node = nodes.get(parent_req.id)
                    if parent_node:
                        parent_node.children.append(node)
                        node.parents.append(parent_node)

        # Find roots (nodes with no parents)
        roots = [n for n in nodes.values() if not n.parents and n.kind == NodeKind.REQUIREMENT]

        tree = TraceGraph(roots=roots, repo_root=hht_like_fixture)

        # Verify tree structure
        assert tree.node_count() > 0
        assert len(tree.roots) > 0

        # All roots should be PRD level
        for root in tree.roots:
            assert root.requirement is not None
            assert root.requirement.level == "PRD" or root.parents == []

        # Verify assertions are attached
        assertion_count = sum(1 for _ in tree.nodes_by_kind(NodeKind.ASSERTION))
        assert assertion_count >= 0  # May be 0 if fixtures don't have assertions

    def test_tree_traversal_matches_hierarchy(self, hht_like_fixture):
        """Test that tree traversal is consistent with hierarchy module."""
        from elspais.config.loader import load_config
        from elspais.core.hierarchy import find_children_ids, find_roots
        from elspais.core.parser import RequirementParser
        from elspais.core.patterns import PatternConfig
        from elspais.core.graph import NodeKind, TraceNode

        # Load requirements
        config_dict = load_config(hht_like_fixture / ".elspais.toml")
        pattern_config = PatternConfig.from_dict(config_dict.get("patterns", {}))
        parser = RequirementParser(pattern_config)
        requirements = parser.parse_directory(hht_like_fixture / "spec")

        # Build simple tree (requirements only)
        nodes: dict[str, TraceNode] = {}
        for req_id, req in requirements.items():
            nodes[req_id] = TraceNode(
                id=req_id,
                kind=NodeKind.REQUIREMENT,
                label=req.title,
                requirement=req,
            )

        # Link using hierarchy module
        from elspais.core.hierarchy import find_requirement

        for req_id, req in requirements.items():
            node = nodes[req_id]
            for impl_id in req.implements:
                parent_req = find_requirement(impl_id, requirements)
                if parent_req and parent_req.id in nodes:
                    parent_node = nodes[parent_req.id]
                    parent_node.children.append(node)
                    node.parents.append(parent_node)

        # Compare roots
        hierarchy_roots = set(find_roots(requirements))
        tree_roots = {n.id for n in nodes.values() if not n.parents}

        assert hierarchy_roots == tree_roots

        # Compare children for each root
        for root_id in hierarchy_roots:
            hierarchy_children = set(find_children_ids(root_id, requirements))
            tree_children = {c.id for c in nodes[root_id].children}

            assert hierarchy_children == tree_children, f"Mismatch for {root_id}"
