# Implements: REQ-d00126
"""Tests for FILE node data model additions (Task 1).

Validates REQ-d00126-A: NodeKind.FILE
Validates REQ-d00126-B: FileType enum
Validates REQ-d00126-C: EdgeKind STRUCTURES, DEFINES, YIELDS
Validates REQ-d00126-D: New edge kinds do not contribute to coverage
Validates REQ-d00126-E: Edge.metadata excluded from __eq__/__hash__
"""

from elspais.graph import GraphNode, NodeKind
from elspais.graph.relations import Edge, EdgeKind


class TestNodeKindFile:
    """Validates REQ-d00126-A: NodeKind.FILE exists with value 'file'."""

    def test_REQ_d00126_A_file_kind_exists(self):
        """NodeKind.FILE enum member exists."""
        assert hasattr(NodeKind, "FILE")

    def test_REQ_d00126_A_file_kind_value(self):
        """NodeKind.FILE has string value 'file'."""
        assert NodeKind.FILE.value == "file"

    def test_REQ_d00126_A_file_node_creation(self):
        """A GraphNode can be created with kind=NodeKind.FILE."""
        node = GraphNode(id="file:spec/prd.md", kind=NodeKind.FILE, label="prd.md")
        assert node.kind == NodeKind.FILE
        assert node.id == "file:spec/prd.md"
        assert node.get_label() == "prd.md"


class TestFileTypeEnum:
    """Validates REQ-d00126-B: FileType enum with SPEC, JOURNEY, CODE, TEST, RESULT."""

    def test_REQ_d00126_B_filetype_importable(self):
        """FileType can be imported from graph module."""
        from elspais.graph.GraphNode import FileType

        assert FileType is not None

    def test_REQ_d00126_B_filetype_values(self):
        """FileType has all required enum members."""
        from elspais.graph.GraphNode import FileType

        expected = {"SPEC", "JOURNEY", "CODE", "TEST", "RESULT"}
        actual = {member.name for member in FileType}
        assert expected == actual, f"Missing members: {expected - actual}"

    def test_REQ_d00126_B_filetype_string_values(self):
        """FileType members have lowercase string values."""
        from elspais.graph.GraphNode import FileType

        assert FileType.SPEC.value == "spec"
        assert FileType.JOURNEY.value == "journey"
        assert FileType.CODE.value == "code"
        assert FileType.TEST.value == "test"
        assert FileType.RESULT.value == "result"


class TestEdgeKindFileAware:
    """Validates REQ-d00126-C: EdgeKind includes STRUCTURES, DEFINES, YIELDS."""

    def test_REQ_d00126_C_structures_exists(self):
        """EdgeKind.STRUCTURES enum member exists."""
        assert hasattr(EdgeKind, "STRUCTURES")
        assert EdgeKind.STRUCTURES.value == "structures"

    def test_REQ_d00126_C_defines_exists(self):
        """EdgeKind.DEFINES enum member exists."""
        assert hasattr(EdgeKind, "DEFINES")
        assert EdgeKind.DEFINES.value == "defines"

    def test_REQ_d00126_C_yields_exists(self):
        """EdgeKind.YIELDS enum member exists."""
        assert hasattr(EdgeKind, "YIELDS")
        assert EdgeKind.YIELDS.value == "yields"


class TestEdgeKindCoverage:
    """Validates REQ-d00126-D: STRUCTURES, DEFINES, YIELDS do not contribute to coverage."""

    def test_REQ_d00126_D_structures_no_coverage(self):
        """STRUCTURES edges do not contribute to coverage."""
        assert EdgeKind.STRUCTURES.contributes_to_coverage() is False

    def test_REQ_d00126_D_defines_no_coverage(self):
        """DEFINES edges do not contribute to coverage."""
        assert EdgeKind.DEFINES.contributes_to_coverage() is False

    def test_REQ_d00126_D_yields_no_coverage(self):
        """YIELDS edges do not contribute to coverage."""
        assert EdgeKind.YIELDS.contributes_to_coverage() is False

    def test_REQ_d00126_D_contains_still_no_coverage(self):
        """CONTAINS edges still do not contribute to coverage (regression check)."""
        assert EdgeKind.CONTAINS.contributes_to_coverage() is False

    def test_REQ_d00126_D_implements_still_coverage(self):
        """IMPLEMENTS edges still contribute to coverage (regression check)."""
        assert EdgeKind.IMPLEMENTS.contributes_to_coverage() is True

    def test_REQ_d00126_D_validates_still_coverage(self):
        """VALIDATES edges still contribute to coverage (regression check)."""
        assert EdgeKind.VALIDATES.contributes_to_coverage() is True


class TestEdgeMetadata:
    """Validates REQ-d00126-E: Edge.metadata field excluded from __eq__/__hash__."""

    def test_REQ_d00126_E_metadata_default_empty(self):
        """Edge metadata defaults to empty dict."""
        source = GraphNode(id="file:a.md", kind=NodeKind.REQUIREMENT)
        target = GraphNode(id="REQ-001", kind=NodeKind.REQUIREMENT)
        edge = Edge(source=source, target=target, kind=EdgeKind.CONTAINS)
        assert edge.metadata == {}

    def test_REQ_d00126_E_metadata_can_be_set(self):
        """Edge metadata can be provided at construction."""
        source = GraphNode(id="file:a.md", kind=NodeKind.REQUIREMENT)
        target = GraphNode(id="REQ-001", kind=NodeKind.REQUIREMENT)
        meta = {"start_line": 10, "end_line": 25, "render_order": 1.0}
        edge = Edge(source=source, target=target, kind=EdgeKind.CONTAINS, metadata=meta)
        assert edge.metadata == {"start_line": 10, "end_line": 25, "render_order": 1.0}

    def test_REQ_d00126_E_metadata_excluded_from_eq(self):
        """Two edges with same source/target/kind but different metadata are equal."""
        source = GraphNode(id="file:a.md", kind=NodeKind.REQUIREMENT)
        target = GraphNode(id="REQ-001", kind=NodeKind.REQUIREMENT)
        edge1 = Edge(
            source=source,
            target=target,
            kind=EdgeKind.CONTAINS,
            metadata={"start_line": 1},
        )
        edge2 = Edge(
            source=source,
            target=target,
            kind=EdgeKind.CONTAINS,
            metadata={"start_line": 99},
        )
        assert edge1 == edge2

    def test_REQ_d00126_E_metadata_excluded_from_hash(self):
        """Two edges with same identity but different metadata have same hash."""
        source = GraphNode(id="file:a.md", kind=NodeKind.REQUIREMENT)
        target = GraphNode(id="REQ-001", kind=NodeKind.REQUIREMENT)
        edge1 = Edge(
            source=source,
            target=target,
            kind=EdgeKind.CONTAINS,
            metadata={"render_order": 0.0},
        )
        edge2 = Edge(
            source=source,
            target=target,
            kind=EdgeKind.CONTAINS,
            metadata={"render_order": 5.0},
        )
        assert hash(edge1) == hash(edge2)

    def test_REQ_d00126_E_metadata_mutable(self):
        """Edge metadata is mutable after creation."""
        source = GraphNode(id="file:a.md", kind=NodeKind.REQUIREMENT)
        target = GraphNode(id="REQ-001", kind=NodeKind.REQUIREMENT)
        edge = Edge(source=source, target=target, kind=EdgeKind.CONTAINS)
        edge.metadata["render_order"] = 3.5
        assert edge.metadata["render_order"] == 3.5

    def test_REQ_d00126_E_metadata_not_shared_between_instances(self):
        """Each Edge gets its own metadata dict (not shared via mutable default)."""
        source = GraphNode(id="file:a.md", kind=NodeKind.REQUIREMENT)
        target = GraphNode(id="REQ-001", kind=NodeKind.REQUIREMENT)
        edge1 = Edge(source=source, target=target, kind=EdgeKind.CONTAINS)
        edge2 = Edge(source=source, target=target, kind=EdgeKind.CONTAINS)
        edge1.metadata["key"] = "value"
        assert "key" not in edge2.metadata
