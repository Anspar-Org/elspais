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

    def test_build_ignores_missing_targets(self):
        """Builder handles references to non-existent targets gracefully."""
        # This should not raise an error
        graph = build_graph(
            make_requirement("REQ-o00001", level="OPS", implements=["REQ-NONEXISTENT"]),
        )

        req = graph.find_by_id("REQ-o00001")
        assert req is not None
        # Node should be a root since its parent doesn't exist
        assert graph.has_root("REQ-o00001")

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

    def test_REQ_o00050_C_journey_is_root_node(self):
        """JNY nodes are included as root nodes in the graph."""
        graph = build_graph(
            make_journey(
                "JNY-Dev-04",
                title="Root Journey",
                actor="Developer",
                goal="Verify root status",
            ),
        )

        assert graph.has_root("JNY-Dev-04")
