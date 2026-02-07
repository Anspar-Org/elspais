# Validates REQ-p00050-A, REQ-p00050-C, REQ-p00050-D
# Validates REQ-o00050-A, REQ-o00050-B, REQ-o00050-C, REQ-o00050-D, REQ-o00050-E
"""Tests for Graph Builder - builds TraceGraph from parsed content."""

from pathlib import Path

import pytest

from elspais.graph import NodeKind
from elspais.graph.builder import GraphBuilder
from elspais.graph.parsers import ParsedContent
from elspais.graph.relations import EdgeKind
from tests.core.graph_test_helpers import (
    build_graph,
    children_string,
    incoming_edges_string,
    make_code_ref,
    make_journey,
    make_requirement,
    make_test_ref,
    make_test_result,
    outgoing_edges_string,
    parents_string,
)


@pytest.fixture
def sample_requirements():
    """Sample parsed requirement content."""
    return [
        ParsedContent(
            content_type="requirement",
            start_line=1,
            end_line=10,
            raw_text="...",
            parsed_data={
                "id": "REQ-p00001",
                "title": "User Auth",
                "level": "PRD",
                "status": "Active",
                "implements": [],
                "assertions": [
                    {"label": "A", "text": "Users can log in"},
                    {"label": "B", "text": "Users can reset password"},
                ],
            },
        ),
        ParsedContent(
            content_type="requirement",
            start_line=15,
            end_line=25,
            raw_text="...",
            parsed_data={
                "id": "REQ-o00001",
                "title": "Login Form",
                "level": "OPS",
                "status": "Active",
                "implements": ["REQ-p00001-A"],
                "assertions": [],
            },
        ),
    ]


class TestGraphBuilder:
    """Tests for GraphBuilder class."""

    def test_build_creates_nodes(self, sample_requirements):
        builder = GraphBuilder()

        for req in sample_requirements:
            builder.add_parsed_content(req)

        graph = builder.build()

        assert graph.find_by_id("REQ-p00001") is not None
        assert graph.find_by_id("REQ-o00001") is not None

    def test_build_creates_assertion_nodes(self, sample_requirements):
        builder = GraphBuilder()

        for req in sample_requirements:
            builder.add_parsed_content(req)

        graph = builder.build()

        assert graph.find_by_id("REQ-p00001-A") is not None
        assert graph.find_by_id("REQ-p00001-B") is not None

    def test_build_links_assertions_to_parent(self, sample_requirements):
        builder = GraphBuilder()

        for req in sample_requirements:
            builder.add_parsed_content(req)

        graph = builder.build()

        parent = graph.find_by_id("REQ-p00001")
        assertion_a = graph.find_by_id("REQ-p00001-A")

        assert "REQ-p00001-A" in children_string(parent)
        assert "REQ-p00001" in parents_string(assertion_a)

    def test_build_creates_implements_edges(self, sample_requirements):
        builder = GraphBuilder()

        for req in sample_requirements:
            builder.add_parsed_content(req)

        graph = builder.build()

        ops_req = graph.find_by_id("REQ-o00001")
        prd_req = graph.find_by_id("REQ-p00001")

        # OPS req should be child of parent REQ (not assertion node)
        # with assertion_targets indicating which assertions it implements
        assert "REQ-p00001" in parents_string(ops_req)

        # Verify the edge has assertion_targets set
        for edge in prd_req.iter_outgoing_edges():
            if edge.target.id == "REQ-o00001":
                assert edge.assertion_targets == ["A"]
                break
        else:
            pytest.fail("Expected edge from REQ-p00001 to REQ-o00001 not found")

    def test_roots_are_top_level_requirements(self, sample_requirements):
        builder = GraphBuilder()

        for req in sample_requirements:
            builder.add_parsed_content(req)

        graph = builder.build()

        assert graph.has_root("REQ-p00001")
        assert not graph.has_root("REQ-o00001")  # Has parent via implements


class TestTraceGraph:
    """Tests for TraceGraph container."""

    def test_find_by_id(self, sample_requirements):
        builder = GraphBuilder()
        for req in sample_requirements:
            builder.add_parsed_content(req)
        graph = builder.build()

        node = graph.find_by_id("REQ-p00001")

        assert node is not None
        assert node.id == "REQ-p00001"

    def test_find_by_id_not_found(self, sample_requirements):
        builder = GraphBuilder()
        for req in sample_requirements:
            builder.add_parsed_content(req)
        graph = builder.build()

        node = graph.find_by_id("NONEXISTENT")

        assert node is None

    def test_all_nodes_iterator(self, sample_requirements):
        builder = GraphBuilder()
        for req in sample_requirements:
            builder.add_parsed_content(req)
        graph = builder.build()

        all_nodes = list(graph.all_nodes())

        # 2 reqs + 2 assertions = 4 nodes exactly
        assert len(all_nodes) == 4

    def test_nodes_by_kind(self, sample_requirements):
        builder = GraphBuilder()
        for req in sample_requirements:
            builder.add_parsed_content(req)
        graph = builder.build()

        assertions = list(graph.nodes_by_kind(NodeKind.ASSERTION))

        assert len(assertions) == 2


class TestBuilderContentTypes:
    """Tests for builder handling different content types."""

    def test_build_creates_journey_nodes(self):
        """Builder creates USER_JOURNEY nodes from journey content."""
        graph = build_graph(
            make_journey("UJ-001", title="Login Flow", actor="User", goal="Sign in"),
        )

        node = graph.find_by_id("UJ-001")
        assert node is not None
        assert node.kind == NodeKind.USER_JOURNEY
        assert node.get_label() == "Login Flow"

    def test_build_creates_code_ref_nodes(self):
        """Builder creates CODE nodes from code_ref content."""
        graph = build_graph(
            make_requirement("REQ-d00001", level="DEV"),
            make_code_ref(["REQ-d00001"], source_path="src/auth.py", start_line=10),
        )

        # Code ref creates a node linked to the requirement
        req = graph.find_by_id("REQ-d00001")
        assert "code:src/auth.py:10" in children_string(req)

        code_node = graph.find_by_id("code:src/auth.py:10")
        assert code_node is not None
        assert code_node.kind == NodeKind.CODE

    def test_build_creates_test_ref_nodes(self):
        """Builder creates TEST nodes from test_ref content."""
        graph = build_graph(
            make_requirement("REQ-d00001", level="DEV"),
            make_test_ref(["REQ-d00001"], source_path="tests/test_auth.py", start_line=5),
        )

        # Test ref creates a node linked to the requirement
        req = graph.find_by_id("REQ-d00001")
        assert "test:tests/test_auth.py:5" in children_string(req)

        test_node = graph.find_by_id("test:tests/test_auth.py:5")
        assert test_node is not None
        assert test_node.kind == NodeKind.TEST

    def test_build_creates_refines_edges(self):
        """Builder creates REFINES edges from refines references."""
        graph = build_graph(
            make_requirement("REQ-p00001", level="PRD"),
            make_requirement("REQ-p00002", level="PRD", refines=["REQ-p00001"]),
        )

        parent = graph.find_by_id("REQ-p00001")

        # Verify refines edge exists
        assert "REQ-p00002" in children_string(parent)
        assert "REQ-p00001->REQ-p00002:refines" in outgoing_edges_string(parent)

    def test_REQ_d00071_B_build_ignores_missing_targets(self):
        """REQ-d00071-B: Builder handles references to non-existent targets gracefully.

        Node with broken implements reference has no parent and no meaningful
        children, so it becomes an orphan under root vs orphan classification.
        """
        # This should not raise an error
        graph = build_graph(
            make_requirement("REQ-o00001", level="OPS", implements=["REQ-NONEXISTENT"]),
        )

        req = graph.find_by_id("REQ-o00001")
        assert req is not None
        # Node has no meaningful children → orphan, not root
        assert not graph.has_root("REQ-o00001")
        orphan_ids = {n.id for n in graph.orphaned_nodes()}
        assert "REQ-o00001" in orphan_ids

    def test_node_content_fields_accessible(self):
        """Node content fields are accessible via get_field()."""
        graph = build_graph(
            make_requirement(
                "REQ-p00001",
                title="Authentication",
                level="PRD",
                status="Active",
                hash_value="abc12345",
            ),
        )

        node = graph.find_by_id("REQ-p00001")

        # Content fields accessible via public API
        assert node.get_field("level") == "PRD"
        assert node.get_field("status") == "Active"
        assert node.get_field("hash") == "abc12345"
        # Convenience properties work too
        assert node.level == "PRD"
        assert node.status == "Active"
        assert node.hash == "abc12345"

    def test_test_result_linked_to_test(self):
        """TEST_RESULT nodes should be children of their parent TEST."""
        graph = build_graph(
            make_requirement("REQ-d00001", level="DEV"),
            make_test_ref(["REQ-d00001"], source_path="tests/test_module.py", start_line=1),
            make_test_result(
                "result-1",
                status="passed",
                test_id="test:tests/test_module.py:1",
            ),
        )

        test = graph.find_by_id("test:tests/test_module.py:1")
        assert test is not None

        children = list(test.iter_children())
        assert len(children) == 1
        assert children[0].id == "result-1"
        assert children[0].kind == NodeKind.TEST_RESULT

    def test_test_result_without_test_id_not_linked(self):
        """TEST_RESULT without test_id should not be linked to any parent."""
        graph = build_graph(
            make_test_result("orphan-result", status="passed", test_id=None),
        )

        result = graph.find_by_id("orphan-result")
        assert result is not None
        assert result.parent_count() == 0


class TestTestToRequirementLinking:
    """Tests for linking tests to requirements via test names."""

    def test_test_result_without_scanner_test_is_broken_ref(self):
        """TEST_RESULT with test_id but no scanner TEST node creates a broken reference."""
        graph = build_graph(
            make_test_result(
                "result-1",
                status="passed",
                test_id="test:TestAuth::test_login",
                name="test_login",
                classname="TestAuth",
            ),
        )

        # TEST node should NOT be auto-created
        test = graph.find_by_id("test:TestAuth::test_login")
        assert test is None

        # Result should exist but have broken reference to test_id
        result = graph.find_by_id("result-1")
        assert result is not None
        assert graph.has_broken_references()
        broken = [
            br for br in graph.broken_references() if br.target_id == "test:TestAuth::test_login"
        ]
        assert len(broken) == 1

    def test_test_with_req_in_name_validates_requirement(self):
        """Scanner-created TEST linked to REQ, with TEST_RESULT child."""
        graph = build_graph(
            make_requirement("REQ-d00001", level="DEV"),
            # Scanner-created TEST node
            make_test_ref(
                ["REQ-d00001"],
                source_path="tests/test_auth.py",
                function_name="test_REQ_d00001_login",
                class_name="TestAuth",
            ),
            make_test_result(
                "result-1",
                status="passed",
                test_id="test:tests/test_auth.py::TestAuth::test_REQ_d00001_login",
                name="test_REQ_d00001_login",
                classname="tests.test_auth.TestAuth",
            ),
            repo_root=Path("."),
        )

        # TEST node should exist and be child of REQ
        test = graph.find_by_id("test:tests/test_auth.py::TestAuth::test_REQ_d00001_login")
        assert test is not None

        # Test should be child of requirement via VALIDATES edge
        req = graph.find_by_id("REQ-d00001")
        assert req is not None
        assert "test:tests/test_auth.py::TestAuth::test_REQ_d00001_login" in children_string(req)

        # Result should be linked to TEST
        result = graph.find_by_id("result-1")
        assert result is not None
        assert "test:tests/test_auth.py::TestAuth::test_REQ_d00001_login" in parents_string(result)

    def test_test_with_assertion_in_name_validates_assertion(self):
        """Test with REQ-xxx-A in name creates VALIDATES edge with assertion_targets."""
        graph = build_graph(
            make_requirement(
                "REQ-p00001",
                level="PRD",
                assertions=[
                    {"label": "A", "text": "User can login"},
                    {"label": "B", "text": "User sees error on failure"},
                ],
            ),
            # Scanner-created TEST node with assertion reference
            make_test_ref(
                ["REQ-p00001-A"],
                source_path="tests/test_auth.py",
                function_name="test_REQ_p00001_A_login",
                class_name="TestAuth",
            ),
            make_test_result(
                "result-1",
                status="passed",
                test_id="test:tests/test_auth.py::TestAuth::test_REQ_p00001_A_login",
                name="test_REQ_p00001_A_login",
                classname="tests.test_auth.TestAuth",
            ),
            repo_root=Path("."),
        )

        # TEST node should exist
        test = graph.find_by_id("test:tests/test_auth.py::TestAuth::test_REQ_p00001_A_login")
        assert test is not None

        # Test should be linked to parent REQ with assertion_targets
        req = graph.find_by_id("REQ-p00001")
        assert "test:tests/test_auth.py::TestAuth::test_REQ_p00001_A_login" in children_string(req)

        # Verify edge has assertion_targets set
        for edge in req.iter_outgoing_edges():
            if edge.target.id == "test:tests/test_auth.py::TestAuth::test_REQ_p00001_A_login":
                assert edge.assertion_targets == ["A"]
                break
        else:
            pytest.fail("Expected edge with assertion_targets not found")

    def test_test_with_multiple_reqs_validates_all(self):
        """Scanner TEST with multiple REQ refs validates all requirements."""
        test_id = "test:tests/test_auth.py::TestAuth::test_REQ_d00001_REQ_d00002_combined"
        graph = build_graph(
            make_requirement("REQ-d00001", level="DEV"),
            make_requirement("REQ-d00002", level="DEV"),
            # Scanner-created TEST node referencing both REQs
            make_test_ref(
                ["REQ-d00001", "REQ-d00002"],
                source_path="tests/test_auth.py",
                function_name="test_REQ_d00001_REQ_d00002_combined",
                class_name="TestAuth",
            ),
            make_test_result(
                "result-1",
                status="passed",
                test_id=test_id,
                name="test_REQ_d00001_REQ_d00002_combined",
                classname="tests.test_auth.TestAuth",
            ),
            repo_root=Path("."),
        )

        test = graph.find_by_id(test_id)
        assert test is not None

        # Test should be child of both requirements
        req1 = graph.find_by_id("REQ-d00001")
        req2 = graph.find_by_id("REQ-d00002")
        assert test_id in children_string(req1)
        assert test_id in children_string(req2)

    def test_multiple_results_share_same_test_node(self):
        """Multiple TEST_RESULTs with same test_id share one scanner-created TEST node."""
        test_id = "test:tests/test_auth.py::TestAuth::test_REQ_d00001_login"
        graph = build_graph(
            make_requirement("REQ-d00001", level="DEV"),
            # Scanner-created TEST node
            make_test_ref(
                ["REQ-d00001"],
                source_path="tests/test_auth.py",
                function_name="test_REQ_d00001_login",
                class_name="TestAuth",
            ),
            make_test_result(
                "result-run1",
                status="passed",
                test_id=test_id,
                name="test_REQ_d00001_login",
                classname="tests.test_auth.TestAuth",
            ),
            make_test_result(
                "result-run2",
                status="failed",
                test_id=test_id,
                name="test_REQ_d00001_login",
                classname="tests.test_auth.TestAuth",
            ),
            repo_root=Path("."),
        )

        # Should be exactly one TEST node
        test_nodes = list(graph.nodes_by_kind(NodeKind.TEST))
        test_matching = [t for t in test_nodes if t.id == test_id]
        assert len(test_matching) == 1

        # Both results should be children of that TEST
        test = test_matching[0]
        children = children_string(test)
        assert "result-run1" in children
        assert "result-run2" in children

    def test_test_without_req_in_name_is_orphan(self):
        """Test result without matching scanner TEST creates broken reference."""
        graph = build_graph(
            make_requirement("REQ-d00001", level="DEV"),
            make_test_result(
                "result-1",
                status="passed",
                test_id="test:tests/test_misc.py::TestMisc::test_something_else",
                name="test_something_else",
                classname="tests.test_misc.TestMisc",
                validates=[],  # No REQ references
            ),
        )

        # No auto-created TEST node
        test = graph.find_by_id("test:tests/test_misc.py::TestMisc::test_something_else")
        assert test is None

        # Result exists, but its reference to test_id is broken
        result = graph.find_by_id("result-1")
        assert result is not None

        # Requirement should not have any test children
        req = graph.find_by_id("REQ-d00001")
        assert "test:" not in children_string(req)  # No test children at all


class TestGeneralizedOrphanDetection:
    """Tests for orphan detection across all node kinds.

    Validates REQ-d00071-A: Root = parentless with meaningful children.
    Validates REQ-d00071-B: Orphan = parentless with no meaningful children.
    Validates REQ-d00071-C: Satellite kinds (ASSERTION, TEST_RESULT) don't count.
    Validates REQ-d00071-D: Journey nodes follow same root/orphan rules.

    Validates that TEST, TEST_RESULT, and CODE nodes are tracked as
    orphan candidates, alongside the existing REQUIREMENT orphan detection.
    """

    def test_test_with_broken_validates_is_orphan(self):
        """TEST referencing non-existent REQ is an orphan."""
        graph = build_graph(
            make_test_ref(
                validates=["REQ-nonexistent"],
                source_path="tests/test_foo.py",
                function_name="test_something",
            ),
        )

        orphans = list(graph.orphaned_nodes())
        orphan_ids = {n.id for n in orphans}
        assert any(n.kind == NodeKind.TEST for n in orphans)
        assert "test:tests/test_foo.py::test_something" in orphan_ids

    def test_test_with_valid_validates_not_orphan(self):
        """TEST with resolved VALIDATES link is not an orphan."""
        graph = build_graph(
            make_requirement("REQ-d00001", level="DEV"),
            make_test_ref(
                validates=["REQ-d00001"],
                source_path="tests/test_foo.py",
                function_name="test_something",
            ),
        )

        orphan_ids = {n.id for n in graph.orphaned_nodes()}
        assert "test:tests/test_foo.py::test_something" not in orphan_ids

    def test_result_without_parent_test_is_orphan(self):
        """TEST_RESULT whose CONTAINS target doesn't exist is an orphan + broken ref."""
        graph = build_graph(
            make_test_result(
                "result-orphan",
                status="passed",
                test_id="test:nonexistent::test_func",
                name="test_func",
            ),
        )

        orphans = list(graph.orphaned_nodes())
        orphan_ids = {n.id for n in orphans}
        assert "result-orphan" in orphan_ids
        assert any(n.kind == NodeKind.TEST_RESULT for n in orphans)

        # Also a broken reference
        assert graph.has_broken_references()
        broken_targets = {br.target_id for br in graph.broken_references()}
        assert "test:nonexistent::test_func" in broken_targets

    def test_result_without_test_id_is_orphan(self):
        """TEST_RESULT with no test_id is an orphan (no link possible)."""
        graph = build_graph(
            make_test_result("result-no-parent", status="passed", test_id=None),
        )

        orphan_ids = {n.id for n in graph.orphaned_nodes()}
        assert "result-no-parent" in orphan_ids

    def test_code_with_broken_implements_is_orphan(self):
        """CODE referencing non-existent REQ is an orphan."""
        graph = build_graph(
            make_code_ref(
                implements=["REQ-nonexistent"],
                source_path="src/module.py",
            ),
        )

        orphans = list(graph.orphaned_nodes())
        orphan_ids = {n.id for n in orphans}
        assert any(n.kind == NodeKind.CODE for n in orphans)
        assert "code:src/module.py:1" in orphan_ids

    def test_REQ_d00071_B_requirement_without_children_is_orphan(self):
        """REQ-d00071-B: Parentless REQUIREMENT nodes without meaningful children are orphans.

        Under root vs orphan classification, a parentless node must have at
        least one non-satellite child (not ASSERTION or TEST_RESULT) to qualify
        as a root. Nodes with no children at all are classified as orphans.
        """
        graph = build_graph(
            make_requirement("REQ-p00001", level="PRD"),
            make_requirement("REQ-o00001", level="OPS"),  # No implements, no children
        )

        orphan_ids = {n.id for n in graph.orphaned_nodes()}
        assert "REQ-p00001" in orphan_ids  # No children → orphan
        assert "REQ-o00001" in orphan_ids  # No children → orphan

    def test_result_linked_to_existing_test_not_orphan(self):
        """TEST_RESULT with resolved CONTAINS edge is not an orphan."""
        graph = build_graph(
            make_requirement("REQ-d00001", level="DEV"),
            make_test_ref(
                validates=["REQ-d00001"],
                source_path="tests/test_module.py",
                function_name="test_func",
            ),
            make_test_result(
                "result-linked",
                status="passed",
                test_id="test:tests/test_module.py::test_func",
                name="test_func",
            ),
        )

        orphan_ids = {n.id for n in graph.orphaned_nodes()}
        assert "result-linked" not in orphan_ids

    def test_REQ_d00071_C_req_with_only_assertions_is_orphan(self):
        """REQ-d00071-C: Requirement with only ASSERTION children is an orphan.

        Assertions are satellite kinds and don't count as meaningful children.
        A parentless requirement whose only children are assertions should be
        classified as an orphan, not a root.
        """
        graph = build_graph(
            make_requirement(
                "REQ-p00001",
                level="PRD",
                assertions=[
                    {"label": "A", "text": "First assertion"},
                    {"label": "B", "text": "Second assertion"},
                ],
            ),
        )

        # REQ-p00001 has assertion children but they are satellite kind
        req = graph.find_by_id("REQ-p00001")
        assert req is not None
        # Assertions exist as children
        child_kinds = {c.kind for c in req.iter_children()}
        assert NodeKind.ASSERTION in child_kinds

        # But requirement is still an orphan (assertions don't count)
        orphan_ids = {n.id for n in graph.orphaned_nodes()}
        assert "REQ-p00001" in orphan_ids

        # And NOT a root
        root_ids = {n.id for n in graph.iter_roots()}
        assert "REQ-p00001" not in root_ids

    def test_REQ_d00071_A_req_with_child_req_is_root(self):
        """REQ-d00071-A: Requirement with a child requirement is a root.

        A parentless PRD requirement that has an OPS child implementing it
        should be classified as a root (the OPS child is a meaningful,
        non-satellite child).
        """
        graph = build_graph(
            make_requirement("REQ-p00001", level="PRD"),
            make_requirement("REQ-o00001", level="OPS", implements=["REQ-p00001"]),
        )

        # PRD has a meaningful child (OPS requirement)
        root_ids = {n.id for n in graph.iter_roots()}
        assert "REQ-p00001" in root_ids

        # PRD is NOT an orphan
        orphan_ids = {n.id for n in graph.orphaned_nodes()}
        assert "REQ-p00001" not in orphan_ids

    def test_REQ_d00071_C_test_with_only_results_is_orphan(self):
        """REQ-d00071-C: TEST node with only TEST_RESULT children is an orphan.

        TEST_RESULT is a satellite kind. A TEST node that has no validates
        link to a requirement (so it's parentless) but has TEST_RESULT
        children should still be classified as an orphan.
        """
        graph = build_graph(
            # Create a TEST node with no validates (no parent link)
            make_test_ref(
                validates=[],
                source_path="tests/test_standalone.py",
                function_name="test_standalone_func",
            ),
            # Create a TEST_RESULT that links to the TEST via CONTAINS
            make_test_result(
                "result-standalone",
                status="passed",
                test_id="test:tests/test_standalone.py::test_standalone_func",
                name="test_standalone_func",
            ),
        )

        test_node = graph.find_by_id("test:tests/test_standalone.py::test_standalone_func")
        assert test_node is not None
        assert test_node.kind == NodeKind.TEST

        # TEST_RESULT is a child of the TEST
        child_kinds = {c.kind for c in test_node.iter_children()}
        assert NodeKind.TEST_RESULT in child_kinds

        # But TEST is still an orphan (TEST_RESULT is satellite)
        orphan_ids = {n.id for n in graph.orphaned_nodes()}
        assert "test:tests/test_standalone.py::test_standalone_func" in orphan_ids

        # And NOT a root
        root_ids = {n.id for n in graph.iter_roots()}
        assert "test:tests/test_standalone.py::test_standalone_func" not in root_ids

    def test_REQ_d00071_D_journey_with_no_children_is_orphan(self):
        """REQ-d00071-D: Standalone USER_JOURNEY with no children is an orphan.

        A journey node that has no children at all should be classified as
        an orphan under the unified root/orphan classification rules.
        """
        graph = build_graph(
            make_journey("UJ-001", title="Login Flow", actor="User", goal="Sign in"),
        )

        journey = graph.find_by_id("UJ-001")
        assert journey is not None
        assert journey.kind == NodeKind.USER_JOURNEY

        # No children at all
        assert journey.child_count() == 0

        # Journey is an orphan
        orphan_ids = {n.id for n in graph.orphaned_nodes()}
        assert "UJ-001" in orphan_ids

        # And NOT a root
        root_ids = {n.id for n in graph.iter_roots()}
        assert "UJ-001" not in root_ids

    def test_REQ_d00071_D_journey_with_req_children_is_root(self):
        """REQ-d00071-D: Journey with a requirement child is a root.

        A USER_JOURNEY that has a REQUIREMENT implementing it should be
        classified as a root (the requirement child is non-satellite/meaningful).
        """
        graph = build_graph(
            make_journey("UJ-001", title="Login Flow", actor="User", goal="Sign in"),
            make_requirement(
                "REQ-o00001",
                level="OPS",
                implements=["UJ-001"],
            ),
        )

        journey = graph.find_by_id("UJ-001")
        assert journey is not None
        assert journey.kind == NodeKind.USER_JOURNEY

        # Journey has a meaningful child (requirement)
        assert journey.child_count() > 0
        child_kinds = {c.kind for c in journey.iter_children()}
        assert NodeKind.REQUIREMENT in child_kinds

        # Journey is a root
        root_ids = {n.id for n in graph.iter_roots()}
        assert "UJ-001" in root_ids

        # And NOT an orphan
        orphan_ids = {n.id for n in graph.orphaned_nodes()}
        assert "UJ-001" not in orphan_ids

    def test_REQ_d00071_C_custom_satellite_kinds_override(self):
        """REQ-d00071-C: Custom satellite_kinds adds CODE as satellite.

        When satellite_kinds includes 'code', a PRD with only a CODE child
        should be classified as an orphan (CODE is satellite), not a root.
        """
        builder = GraphBuilder(satellite_kinds=["assertion", "result", "code"])
        builder.add_parsed_content(
            make_requirement("REQ-p00001", level="PRD"),
        )
        builder.add_parsed_content(
            make_code_ref(
                implements=["REQ-p00001"],
                source_path="src/auth.py",
            ),
        )
        graph = builder.build()

        req = graph.find_by_id("REQ-p00001")
        assert req is not None
        # CODE is a child
        child_kinds = {c.kind for c in req.iter_children()}
        assert NodeKind.CODE in child_kinds

        # But with CODE as satellite, PRD is an orphan
        orphan_ids = {n.id for n in graph.orphaned_nodes()}
        assert "REQ-p00001" in orphan_ids

        # And NOT a root
        root_ids = {n.id for n in graph.iter_roots()}
        assert "REQ-p00001" not in root_ids

    def test_REQ_d00071_C_default_satellite_kinds_unchanged(self):
        """REQ-d00071-C: Default satellite_kinds matches original behavior.

        When no satellite_kinds parameter is passed, the builder defaults
        to ASSERTION and TEST_RESULT as satellite kinds. A PRD with only
        assertion children should be classified as an orphan.
        """
        builder = GraphBuilder()
        builder.add_parsed_content(
            make_requirement(
                "REQ-p00001",
                level="PRD",
                assertions=[
                    {"label": "A", "text": "First assertion"},
                    {"label": "B", "text": "Second assertion"},
                ],
            ),
        )
        graph = builder.build()

        req = graph.find_by_id("REQ-p00001")
        assert req is not None
        # Assertions exist as children
        child_kinds = {c.kind for c in req.iter_children()}
        assert NodeKind.ASSERTION in child_kinds

        # Assertions are satellite by default, so PRD is orphan
        orphan_ids = {n.id for n in graph.orphaned_nodes()}
        assert "REQ-p00001" in orphan_ids

        # And NOT a root
        root_ids = {n.id for n in graph.iter_roots()}
        assert "REQ-p00001" not in root_ids

    def test_REQ_d00071_C_invalid_satellite_kind_raises_error(self):
        """REQ-d00071-C: Invalid satellite kind string raises ValueError.

        Passing an unrecognized string to satellite_kinds should raise
        a ValueError when NodeKind tries to parse it.
        """
        with pytest.raises(ValueError):
            GraphBuilder(satellite_kinds=["bogus"])


class TestCanonicalTestIds:
    """Tests for canonical TEST node ID generation from test_ref content."""

    def test_REQ_d00054_A_canonical_id_with_function_name(self):
        """Canonical ID uses :: separator with function name, no class."""
        graph = build_graph(
            make_requirement("REQ-d00001", level="DEV"),
            make_test_ref(
                ["REQ-d00001"],
                source_path="tests/test_auth.py",
                start_line=5,
                function_name="test_REQ_d00001_validates",
            ),
            repo_root=Path("."),
        )

        test_node = graph.find_by_id("test:tests/test_auth.py::test_REQ_d00001_validates")
        assert test_node is not None
        assert test_node.kind == NodeKind.TEST

        req = graph.find_by_id("REQ-d00001")
        assert "test:tests/test_auth.py::test_REQ_d00001_validates" in children_string(req)

    def test_REQ_d00054_A_canonical_id_with_class_and_function(self):
        """Canonical ID includes ClassName when class_name is provided."""
        graph = build_graph(
            make_requirement("REQ-d00001", level="DEV"),
            make_test_ref(
                ["REQ-d00001"],
                source_path="tests/test_auth.py",
                start_line=10,
                function_name="test_REQ_d00001_login",
                class_name="TestAuth",
            ),
            repo_root=Path("."),
        )

        test_node = graph.find_by_id("test:tests/test_auth.py::TestAuth::test_REQ_d00001_login")
        assert test_node is not None
        assert test_node.kind == NodeKind.TEST

        req = graph.find_by_id("REQ-d00001")
        assert "test:tests/test_auth.py::TestAuth::test_REQ_d00001_login" in children_string(req)

    def test_REQ_d00054_A_fallback_to_line_based_id(self):
        """Without function_name, falls back to line-based ID."""
        graph = build_graph(
            make_requirement("REQ-d00001", level="DEV"),
            make_test_ref(
                ["REQ-d00001"],
                source_path="tests/test_auth.py",
                start_line=5,
            ),
            repo_root=Path("."),
        )

        test_node = graph.find_by_id("test:tests/test_auth.py:5")
        assert test_node is not None
        assert test_node.kind == NodeKind.TEST

        req = graph.find_by_id("REQ-d00001")
        assert "test:tests/test_auth.py:5" in children_string(req)

    def test_REQ_d00054_A_canonical_id_deduplicates(self):
        """Two test_refs with same function/path but different validates create one TEST node."""
        graph = build_graph(
            make_requirement("REQ-d00001", level="DEV"),
            make_requirement("REQ-d00002", level="DEV"),
            make_test_ref(
                ["REQ-d00001"],
                source_path="tests/test_auth.py",
                start_line=5,
                function_name="test_REQ_d00001_REQ_d00002_combined",
            ),
            make_test_ref(
                ["REQ-d00002"],
                source_path="tests/test_auth.py",
                start_line=5,
                function_name="test_REQ_d00001_REQ_d00002_combined",
            ),
            repo_root=Path("."),
        )

        # Only one TEST node should exist for this canonical ID
        test_nodes = [
            n
            for n in graph.nodes_by_kind(NodeKind.TEST)
            if n.id == "test:tests/test_auth.py::test_REQ_d00001_REQ_d00002_combined"
        ]
        assert len(test_nodes) == 1

        # The single TEST node should validate both requirements
        req1 = graph.find_by_id("REQ-d00001")
        req2 = graph.find_by_id("REQ-d00002")
        assert "test:tests/test_auth.py::test_REQ_d00001_REQ_d00002_combined" in children_string(
            req1
        )
        assert "test:tests/test_auth.py::test_REQ_d00001_REQ_d00002_combined" in children_string(
            req2
        )

    def test_REQ_d00054_A_canonical_id_relative_to_repo_root(self):
        """Absolute source_path is converted to relative using repo_root."""
        graph = build_graph(
            make_requirement("REQ-d00001", level="DEV"),
            make_test_ref(
                ["REQ-d00001"],
                source_path="/home/user/project/tests/test_auth.py",
                start_line=10,
                function_name="test_REQ_d00001_validates",
            ),
            repo_root=Path("/home/user/project"),
        )

        # The canonical ID should use the relative path
        test_node = graph.find_by_id("test:tests/test_auth.py::test_REQ_d00001_validates")
        assert test_node is not None
        assert test_node.kind == NodeKind.TEST

        req = graph.find_by_id("REQ-d00001")
        assert "test:tests/test_auth.py::test_REQ_d00001_validates" in children_string(req)


class TestAddressesEdges:
    """Tests for ADDRESSES edge creation in GraphBuilder.

    Validates REQ-o00050-C: TraceGraphBuilder SHALL handle all relationship
    linking including addresses.
    """

    def test_REQ_o00050_C_journey_addresses_creates_edge(self):
        """JNY with Addresses: REQ-p00012 creates ADDRESSES edge to REQ node."""
        graph = build_graph(
            make_requirement("REQ-p00012", level="PRD", title="Product Requirement"),
            make_journey(
                "JNY-Dev-01",
                title="Dev Workflow",
                actor="Developer",
                goal="Implement feature",
                addresses=["REQ-p00012"],
            ),
        )

        jny_node = graph.find_by_id("JNY-Dev-01")
        req_node = graph.find_by_id("REQ-p00012")

        assert jny_node is not None
        assert req_node is not None

        # The REQ node becomes the parent via target.link(source, edge_kind),
        # so the JNY node has incoming ADDRESSES edges
        edges = incoming_edges_string(jny_node)
        assert "REQ-p00012->JNY-Dev-01:addresses" in edges

        # Verify edge kind is ADDRESSES
        found_addresses_edge = False
        for edge in jny_node.iter_incoming_edges():
            if edge.source.id == "REQ-p00012" and edge.kind == EdgeKind.ADDRESSES:
                found_addresses_edge = True
                break
        assert found_addresses_edge, "Expected ADDRESSES edge from REQ-p00012 to JNY-Dev-01"

    def test_REQ_o00050_C_journey_addresses_missing_target_broken_ref(self):
        """JNY with Addresses: REQ-NONEXIST records broken reference."""
        graph = build_graph(
            make_journey(
                "JNY-Dev-02",
                title="Broken Ref Journey",
                actor="Developer",
                goal="Test broken ref",
                addresses=["REQ-NONEXIST"],
            ),
        )

        jny_node = graph.find_by_id("JNY-Dev-02")
        assert jny_node is not None

        # Should have no incoming edges since target doesn't exist
        assert jny_node.parent_count() == 0

        # Should have a broken reference recorded
        assert graph.has_broken_references()
        broken = [
            br
            for br in graph.broken_references()
            if br.source_id == "JNY-Dev-02" and br.target_id == "REQ-NONEXIST"
        ]
        assert len(broken) == 1
        assert broken[0].edge_kind == "addresses"

    def test_REQ_o00050_C_journey_addresses_multiple_targets(self):
        """JNY with multiple Addresses creates edges to all targets."""
        graph = build_graph(
            make_requirement("REQ-p00012", level="PRD"),
            make_requirement("REQ-d00042", level="DEV"),
            make_journey(
                "JNY-Dev-03",
                title="Multi Address Journey",
                actor="Developer",
                goal="Test multiple addresses",
                addresses=["REQ-p00012", "REQ-d00042"],
            ),
        )

        jny_node = graph.find_by_id("JNY-Dev-03")
        assert jny_node is not None

        edges = incoming_edges_string(jny_node)
        assert "REQ-d00042->JNY-Dev-03:addresses" in edges
        assert "REQ-p00012->JNY-Dev-03:addresses" in edges

    def test_REQ_o00050_C_journey_is_orphan_without_children(self):
        """JNY nodes without meaningful children are orphans (REQ-d00071)."""
        graph = build_graph(
            make_journey(
                "JNY-Dev-04",
                title="Orphan Journey",
                actor="Developer",
                goal="Verify orphan status",
            ),
        )

        # Under unified root/orphan classification (REQ-d00071),
        # parentless nodes need meaningful children to be roots
        assert not graph.has_root("JNY-Dev-04")
        assert graph.find_by_id("JNY-Dev-04") is not None
