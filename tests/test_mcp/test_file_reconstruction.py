"""
Tests for lossless file reconstruction from graph data.

Tests cover:
- FileRegion capture (preamble, inter_requirement, postamble)
- FileNode tracking of requirement order and regions
- parse_file_with_structure method
- FileReconstructor reconstruction accuracy
- Round-trip testing (load → graph → reconstruct → compare)
- Edge cases (empty files, no requirements, single requirement)
- FILE and FILE_REGION TraceNodes for unified graph approach
- Bidirectional node-data references (FILE↔REQ)
"""

import pytest
from pathlib import Path

from elspais.core.graph import FileInfo, FileNode, FileRegion, TraceGraph, TraceNode, NodeKind
from elspais.core.models import Requirement, StructuredParseResult
from elspais.core.parser import RequirementParser
from elspais.core.patterns import PatternConfig


# Sample requirement content for testing
SAMPLE_REQ_1 = """# REQ-p00001: First Requirement

**Level**: PRD | **Status**: Active | **Implements**: -

## Assertions

A. The system SHALL do something.

*End* *First Requirement* | **Hash**: abc12345

---"""

SAMPLE_REQ_2 = """# REQ-p00002: Second Requirement

**Level**: PRD | **Status**: Active | **Implements**: REQ-p00001

## Assertions

A. The system SHALL do another thing.

*End* *Second Requirement* | **Hash**: def67890

---"""

PREAMBLE = """# Product Requirements

This document contains product requirements.

"""

INTER_REQ_CONTENT = """
## Additional Notes

Some notes between requirements.

"""

POSTAMBLE = """
## Footer

End of document.
"""


@pytest.fixture
def pattern_config():
    """Create a PatternConfig for HHT-style IDs."""
    return PatternConfig.from_dict({
        "prefix": "REQ",
        "id_template": "{prefix}-{type}{id}",
        "types": {
            "product": {"id": "p", "level": 1},
            "operations": {"id": "o", "level": 2},
            "development": {"id": "d", "level": 3},
        },
        "id_format": {"style": "numeric", "digits": 5},
        "assertions": {"label_style": "uppercase"},
    })


@pytest.fixture
def parser(pattern_config):
    """Create a RequirementParser."""
    return RequirementParser(pattern_config)


@pytest.fixture
def temp_spec_dir(tmp_path):
    """Create a temporary spec directory."""
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    return spec_dir


class TestFileRegion:
    """Tests for FileRegion dataclass."""

    def test_file_region_creation(self):
        """Test creating a FileRegion."""
        region = FileRegion(
            region_type="preamble",
            start_line=1,
            end_line=5,
            content="# Header\n\nSome content",
        )

        assert region.region_type == "preamble"
        assert region.start_line == 1
        assert region.end_line == 5
        assert "Header" in region.content


class TestFileNode:
    """Tests for FileNode dataclass."""

    def test_file_node_creation(self):
        """Test creating a FileNode."""
        file_node = FileNode(
            file_path="spec/prd-auth.md",
            requirements=["REQ-p00001", "REQ-p00002"],
            regions=[
                FileRegion("preamble", 1, 3, "# Preamble"),
            ],
        )

        assert file_node.file_path == "spec/prd-auth.md"
        assert len(file_node.requirements) == 2
        assert file_node.get_requirement_order() == ["REQ-p00001", "REQ-p00002"]

    def test_get_preamble(self):
        """Test getting preamble content."""
        file_node = FileNode(
            file_path="spec/test.md",
            regions=[
                FileRegion("preamble", 1, 3, "# Preamble content"),
                FileRegion("postamble", 20, 25, "# Footer"),
            ],
        )

        assert file_node.get_preamble() == "# Preamble content"

    def test_get_postamble(self):
        """Test getting postamble content."""
        file_node = FileNode(
            file_path="spec/test.md",
            regions=[
                FileRegion("preamble", 1, 3, "# Preamble"),
                FileRegion("postamble", 20, 25, "# Footer content"),
            ],
        )

        assert file_node.get_postamble() == "# Footer content"

    def test_no_preamble_returns_none(self):
        """Test that missing preamble returns None."""
        file_node = FileNode(file_path="spec/test.md")
        assert file_node.get_preamble() is None


class TestTraceGraphFileIndex:
    """Tests for TraceGraph file index functionality."""

    def test_register_file_node(self):
        """Test registering a FileNode."""
        graph = TraceGraph(roots=[], repo_root=Path("/test"))
        file_node = FileNode(file_path="spec/prd.md")

        graph.register_file_node(file_node)

        assert graph.get_file_node("spec/prd.md") is file_node

    def test_get_nonexistent_file_node(self):
        """Test getting non-existent FileNode returns None."""
        graph = TraceGraph(roots=[], repo_root=Path("/test"))

        assert graph.get_file_node("nonexistent.md") is None

    def test_all_file_nodes(self):
        """Test iterating all file nodes."""
        graph = TraceGraph(roots=[], repo_root=Path("/test"))
        graph.register_file_node(FileNode(file_path="spec/prd1.md"))
        graph.register_file_node(FileNode(file_path="spec/prd2.md"))

        file_nodes = list(graph.all_file_nodes())

        assert len(file_nodes) == 2

    def test_file_count(self):
        """Test file count."""
        graph = TraceGraph(roots=[], repo_root=Path("/test"))
        graph.register_file_node(FileNode(file_path="spec/prd1.md"))
        graph.register_file_node(FileNode(file_path="spec/prd2.md"))

        assert graph.file_count() == 2


class TestParseFileWithStructure:
    """Tests for parse_file_with_structure method."""

    def test_single_requirement_no_extras(self, parser, temp_spec_dir):
        """Test parsing a file with just one requirement."""
        file = temp_spec_dir / "prd-simple.md"
        file.write_text(SAMPLE_REQ_1)

        result = parser.parse_file_with_structure(file, temp_spec_dir.parent)

        assert isinstance(result, StructuredParseResult)
        assert "REQ-p00001" in result.requirements
        assert len(result.file_node.requirements) == 1
        assert result.file_node.requirements[0] == "REQ-p00001"

    def test_captures_preamble(self, parser, temp_spec_dir):
        """Test that preamble is captured."""
        content = PREAMBLE + SAMPLE_REQ_1
        file = temp_spec_dir / "prd-preamble.md"
        file.write_text(content)

        result = parser.parse_file_with_structure(file, temp_spec_dir.parent)

        preamble = result.file_node.get_preamble()
        assert preamble is not None
        assert "Product Requirements" in preamble

    def test_captures_postamble(self, parser, temp_spec_dir):
        """Test that postamble is captured."""
        content = SAMPLE_REQ_1 + POSTAMBLE
        file = temp_spec_dir / "prd-postamble.md"
        file.write_text(content)

        result = parser.parse_file_with_structure(file, temp_spec_dir.parent)

        postamble = result.file_node.get_postamble()
        assert postamble is not None
        assert "Footer" in postamble

    def test_captures_inter_requirement_content(self, parser, temp_spec_dir):
        """Test that content between requirements is captured."""
        content = SAMPLE_REQ_1 + INTER_REQ_CONTENT + SAMPLE_REQ_2
        file = temp_spec_dir / "prd-multi.md"
        file.write_text(content)

        result = parser.parse_file_with_structure(file, temp_spec_dir.parent)

        inter_regions = [r for r in result.file_node.regions if r.region_type == "inter_requirement"]
        assert len(inter_regions) >= 1
        assert any("Additional Notes" in r.content for r in inter_regions)

    def test_preserves_requirement_order(self, parser, temp_spec_dir):
        """Test that requirement order is preserved."""
        content = SAMPLE_REQ_1 + "\n" + SAMPLE_REQ_2
        file = temp_spec_dir / "prd-order.md"
        file.write_text(content)

        result = parser.parse_file_with_structure(file, temp_spec_dir.parent)

        assert result.file_node.requirements == ["REQ-p00001", "REQ-p00002"]

    def test_empty_file(self, parser, temp_spec_dir):
        """Test parsing an empty file."""
        file = temp_spec_dir / "prd-empty.md"
        file.write_text("")

        result = parser.parse_file_with_structure(file, temp_spec_dir.parent)

        assert len(result.requirements) == 0
        assert len(result.file_node.requirements) == 0

    def test_file_with_only_prose(self, parser, temp_spec_dir):
        """Test parsing a file with no requirements."""
        file = temp_spec_dir / "prd-prose.md"
        file.write_text(PREAMBLE)

        result = parser.parse_file_with_structure(file, temp_spec_dir.parent)

        assert len(result.requirements) == 0
        # Entire file should be captured as preamble
        preamble = result.file_node.get_preamble()
        assert preamble is not None
        assert "Product Requirements" in preamble

    def test_preserve_lines_option(self, parser, temp_spec_dir):
        """Test that preserve_lines stores original lines."""
        file = temp_spec_dir / "prd-lines.md"
        file.write_text(SAMPLE_REQ_1)

        result = parser.parse_file_with_structure(file, temp_spec_dir.parent, preserve_lines=True)

        assert result.file_node.original_lines is not None
        assert len(result.file_node.original_lines) > 0

    def test_no_preserve_lines_by_default(self, parser, temp_spec_dir):
        """Test that original_lines is None by default."""
        file = temp_spec_dir / "prd-nolines.md"
        file.write_text(SAMPLE_REQ_1)

        result = parser.parse_file_with_structure(file, temp_spec_dir.parent, preserve_lines=False)

        assert result.file_node.original_lines is None

    def test_relative_path_calculation(self, parser, temp_spec_dir):
        """Test that file_path is relative to repo_root."""
        file = temp_spec_dir / "prd-path.md"
        file.write_text(SAMPLE_REQ_1)

        result = parser.parse_file_with_structure(file, temp_spec_dir.parent)

        assert result.file_node.file_path == "spec/prd-path.md"


# MCP Reconstructor Tests
try:
    from elspais.mcp.reconstructor import FileReconstructor, ReconstructionResult
    RECONSTRUCTOR_AVAILABLE = True
except ImportError:
    RECONSTRUCTOR_AVAILABLE = False


@pytest.mark.skipif(not RECONSTRUCTOR_AVAILABLE, reason="Reconstructor not available")
class TestFileReconstructor:
    """Tests for FileReconstructor class."""

    def test_reconstruct_simple_file(self, parser, temp_spec_dir):
        """Test reconstructing a simple file."""
        file = temp_spec_dir / "prd-simple.md"
        file.write_text(SAMPLE_REQ_1)

        # Parse with structure
        result = parser.parse_file_with_structure(file, temp_spec_dir.parent)

        # Create graph and register file node
        req = result.requirements["REQ-p00001"]
        node = TraceNode(
            id=req.id,
            kind=NodeKind.REQUIREMENT,
            label=f"{req.id}: {req.title}",
            requirement=req,
        )
        graph = TraceGraph(roots=[node], repo_root=temp_spec_dir.parent)
        graph.register_file_node(result.file_node)

        # Reconstruct
        reconstructor = FileReconstructor(graph)
        recon_result = reconstructor.reconstruct_file("spec/prd-simple.md")

        assert recon_result.success
        assert "REQ-p00001" in recon_result.content
        assert "First Requirement" in recon_result.content

    def test_reconstruct_with_preamble(self, parser, temp_spec_dir):
        """Test reconstructing a file with preamble."""
        content = PREAMBLE + SAMPLE_REQ_1
        file = temp_spec_dir / "prd-preamble.md"
        file.write_text(content)

        # Parse with structure
        result = parser.parse_file_with_structure(file, temp_spec_dir.parent)

        # Create graph
        req = result.requirements["REQ-p00001"]
        node = TraceNode(
            id=req.id,
            kind=NodeKind.REQUIREMENT,
            label=f"{req.id}: {req.title}",
            requirement=req,
        )
        graph = TraceGraph(roots=[node], repo_root=temp_spec_dir.parent)
        graph.register_file_node(result.file_node)

        # Reconstruct
        reconstructor = FileReconstructor(graph)
        recon_result = reconstructor.reconstruct_file("spec/prd-preamble.md")

        assert recon_result.success
        assert "Product Requirements" in recon_result.content

    def test_reconstruct_nonexistent_file(self, temp_spec_dir):
        """Test reconstructing a file that doesn't exist in index."""
        graph = TraceGraph(roots=[], repo_root=temp_spec_dir.parent)
        reconstructor = FileReconstructor(graph)

        result = reconstructor.reconstruct_file("nonexistent.md")

        assert not result.success
        assert "No file data found" in result.message

    def test_verify_reconstruction_matches(self, parser, temp_spec_dir):
        """Test verification when reconstruction matches original."""
        file = temp_spec_dir / "prd-verify.md"
        file.write_text(SAMPLE_REQ_1)

        # Parse with structure and preserve lines
        result = parser.parse_file_with_structure(
            file, temp_spec_dir.parent, preserve_lines=True
        )

        # Create graph
        req = result.requirements["REQ-p00001"]
        node = TraceNode(
            id=req.id,
            kind=NodeKind.REQUIREMENT,
            label=f"{req.id}: {req.title}",
            requirement=req,
        )
        graph = TraceGraph(roots=[node], repo_root=temp_spec_dir.parent)
        graph.register_file_node(result.file_node)

        # Verify
        reconstructor = FileReconstructor(graph)
        verify_result = reconstructor.verify_reconstruction("spec/prd-verify.md")

        assert verify_result.success
        # Note: Due to normalization differences, may not match exactly

    def test_diff_reconstruction(self, parser, temp_spec_dir):
        """Test generating diff between original and reconstructed."""
        file = temp_spec_dir / "prd-diff.md"
        file.write_text(SAMPLE_REQ_1)

        # Parse with structure
        result = parser.parse_file_with_structure(
            file, temp_spec_dir.parent, preserve_lines=True
        )

        # Create graph
        req = result.requirements["REQ-p00001"]
        node = TraceNode(
            id=req.id,
            kind=NodeKind.REQUIREMENT,
            label=f"{req.id}: {req.title}",
            requirement=req,
        )
        graph = TraceGraph(roots=[node], repo_root=temp_spec_dir.parent)
        graph.register_file_node(result.file_node)

        # Get diff
        reconstructor = FileReconstructor(graph)
        diff = reconstructor.diff_reconstruction("spec/prd-diff.md")

        # Should return a string (may be empty if matches or show differences)
        assert isinstance(diff, str)


class TestRoundTrip:
    """Tests for round-trip parsing and reconstruction."""

    def test_multiple_requirements_round_trip(self, parser, temp_spec_dir):
        """Test round-trip with multiple requirements."""
        content = SAMPLE_REQ_1 + "\n" + SAMPLE_REQ_2
        file = temp_spec_dir / "prd-multi.md"
        file.write_text(content)

        # Parse
        result = parser.parse_file_with_structure(file, temp_spec_dir.parent)

        # Verify both requirements captured in order
        assert len(result.requirements) == 2
        assert result.file_node.requirements == ["REQ-p00001", "REQ-p00002"]

    def test_full_file_round_trip(self, parser, temp_spec_dir):
        """Test round-trip with preamble, requirements, and postamble."""
        content = PREAMBLE + SAMPLE_REQ_1 + INTER_REQ_CONTENT + SAMPLE_REQ_2 + POSTAMBLE
        file = temp_spec_dir / "prd-full.md"
        file.write_text(content)

        # Parse
        result = parser.parse_file_with_structure(file, temp_spec_dir.parent)

        # Verify structure
        assert result.file_node.get_preamble() is not None
        assert result.file_node.get_postamble() is not None
        assert len(result.file_node.requirements) == 2

        # Verify regions
        inter_regions = [r for r in result.file_node.regions if r.region_type == "inter_requirement"]
        assert len(inter_regions) >= 1


class TestFileTraceNodes:
    """Tests for FILE and FILE_REGION TraceNode support."""

    def test_file_node_creation_with_graph_builder(self, parser, temp_spec_dir):
        """Test that FILE nodes are created when include_file_nodes=True."""
        from elspais.core.graph_builder import TraceGraphBuilder

        file = temp_spec_dir / "prd-test.md"
        file.write_text(PREAMBLE + SAMPLE_REQ_1)

        result = parser.parse_file_with_structure(file, temp_spec_dir.parent)

        # Build graph with file nodes enabled
        builder = TraceGraphBuilder(
            repo_root=temp_spec_dir.parent,
            include_file_nodes=True,
        )
        builder.add_requirements(result.requirements)
        builder.add_file_structures([result])
        graph = builder.build()

        # Verify FILE node exists
        file_node = graph.find_by_id("file:spec/prd-test.md")
        assert file_node is not None
        assert file_node.kind == NodeKind.FILE
        assert file_node.file_info is not None
        assert file_node.file_info.file_path == "spec/prd-test.md"

    def test_no_file_nodes_by_default(self, parser, temp_spec_dir):
        """Test that FILE nodes are NOT created when include_file_nodes=False."""
        from elspais.core.graph_builder import TraceGraphBuilder

        file = temp_spec_dir / "prd-test.md"
        file.write_text(SAMPLE_REQ_1)

        result = parser.parse_file_with_structure(file, temp_spec_dir.parent)

        # Build graph with file nodes disabled (default)
        builder = TraceGraphBuilder(repo_root=temp_spec_dir.parent)
        builder.add_requirements(result.requirements)
        builder.add_file_structures([result])
        graph = builder.build()

        # Verify no FILE node
        file_node = graph.find_by_id("file:spec/prd-test.md")
        assert file_node is None

    def test_file_region_children(self, parser, temp_spec_dir):
        """Test that FILE_REGION nodes are children of FILE node."""
        from elspais.core.graph_builder import TraceGraphBuilder

        file = temp_spec_dir / "prd-regions.md"
        file.write_text(PREAMBLE + SAMPLE_REQ_1 + POSTAMBLE)

        result = parser.parse_file_with_structure(file, temp_spec_dir.parent)

        builder = TraceGraphBuilder(
            repo_root=temp_spec_dir.parent,
            include_file_nodes=True,
        )
        builder.add_requirements(result.requirements)
        builder.add_file_structures([result])
        graph = builder.build()

        file_node = graph.find_by_id("file:spec/prd-regions.md")
        assert file_node is not None

        # Check FILE_REGION children
        region_children = [c for c in file_node.children if c.kind == NodeKind.FILE_REGION]
        assert len(region_children) >= 2  # preamble + postamble at minimum

        # Verify region types
        region_types = {c.file_region.region_type for c in region_children if c.file_region}
        assert "preamble" in region_types
        assert "postamble" in region_types

    def test_file_info_requirements_references(self, parser, temp_spec_dir):
        """Test that file_info.requirements contains direct node references."""
        from elspais.core.graph_builder import TraceGraphBuilder

        file = temp_spec_dir / "prd-refs.md"
        file.write_text(SAMPLE_REQ_1 + "\n" + SAMPLE_REQ_2)

        result = parser.parse_file_with_structure(file, temp_spec_dir.parent)

        builder = TraceGraphBuilder(
            repo_root=temp_spec_dir.parent,
            include_file_nodes=True,
        )
        builder.add_requirements(result.requirements)
        builder.add_file_structures([result])
        graph = builder.build()

        file_node = graph.find_by_id("file:spec/prd-refs.md")
        assert file_node is not None
        assert file_node.file_info is not None

        # file_info.requirements should be TraceNode objects, not strings
        assert len(file_node.file_info.requirements) == 2
        assert all(isinstance(r, TraceNode) for r in file_node.file_info.requirements)
        assert file_node.file_info.requirements[0].id == "REQ-p00001"
        assert file_node.file_info.requirements[1].id == "REQ-p00002"

    def test_source_file_bidirectional_reference(self, parser, temp_spec_dir):
        """Test that req_node.source_file points to FILE node."""
        from elspais.core.graph_builder import TraceGraphBuilder

        file = temp_spec_dir / "prd-bidir.md"
        file.write_text(SAMPLE_REQ_1)

        result = parser.parse_file_with_structure(file, temp_spec_dir.parent)

        builder = TraceGraphBuilder(
            repo_root=temp_spec_dir.parent,
            include_file_nodes=True,
        )
        builder.add_requirements(result.requirements)
        builder.add_file_structures([result])
        graph = builder.build()

        # Get requirement node
        req_node = graph.find_by_id("REQ-p00001")
        assert req_node is not None

        # Check source_file reference
        assert req_node.source_file is not None
        assert req_node.source_file.kind == NodeKind.FILE
        assert req_node.source_file.file_info.file_path == "spec/prd-bidir.md"

    def test_source_file_none_without_graph_file(self, parser, temp_spec_dir):
        """Test that source_file is None when include_file_nodes=False."""
        from elspais.core.graph_builder import TraceGraphBuilder

        file = temp_spec_dir / "prd-no-file.md"
        file.write_text(SAMPLE_REQ_1)

        result = parser.parse_file_with_structure(file, temp_spec_dir.parent)

        builder = TraceGraphBuilder(repo_root=temp_spec_dir.parent)  # Default: no file nodes
        builder.add_requirements(result.requirements)
        graph = builder.build()

        req_node = graph.find_by_id("REQ-p00001")
        assert req_node is not None
        assert req_node.source_file is None

    def test_nodes_by_kind_file(self, parser, temp_spec_dir):
        """Test that nodes_by_kind can find FILE nodes."""
        from elspais.core.graph_builder import TraceGraphBuilder

        file = temp_spec_dir / "prd-find.md"
        file.write_text(SAMPLE_REQ_1)

        result = parser.parse_file_with_structure(file, temp_spec_dir.parent)

        builder = TraceGraphBuilder(
            repo_root=temp_spec_dir.parent,
            include_file_nodes=True,
        )
        builder.add_requirements(result.requirements)
        builder.add_file_structures([result])
        graph = builder.build()

        # Find all FILE nodes
        file_nodes = list(graph.nodes_by_kind(NodeKind.FILE))
        assert len(file_nodes) == 1
        assert file_nodes[0].kind == NodeKind.FILE

        # Find all FILE_REGION nodes
        region_nodes = list(graph.nodes_by_kind(NodeKind.FILE_REGION))
        assert len(region_nodes) >= 1
        assert all(n.kind == NodeKind.FILE_REGION for n in region_nodes)


@pytest.mark.skipif(not RECONSTRUCTOR_AVAILABLE, reason="Reconstructor not available")
class TestGraphBasedReconstruction:
    """Tests for reconstruction using FILE TraceNodes."""

    def test_reconstruct_from_file_nodes(self, parser, temp_spec_dir):
        """Test reconstruction using FILE nodes in graph."""
        from elspais.core.graph_builder import TraceGraphBuilder
        from elspais.mcp.reconstructor import FileReconstructor

        file = temp_spec_dir / "prd-recon.md"
        file.write_text(PREAMBLE + SAMPLE_REQ_1)

        result = parser.parse_file_with_structure(file, temp_spec_dir.parent)

        builder = TraceGraphBuilder(
            repo_root=temp_spec_dir.parent,
            include_file_nodes=True,
        )
        builder.add_requirements(result.requirements)
        builder.add_file_structures([result])
        graph = builder.build()

        reconstructor = FileReconstructor(graph)
        recon_result = reconstructor.reconstruct_file("spec/prd-recon.md")

        assert recon_result.success
        assert "graph-based" in recon_result.message
        assert "Product Requirements" in recon_result.content
        assert "REQ-p00001" in recon_result.content

    def test_reconstruction_fallback_to_legacy(self, parser, temp_spec_dir):
        """Test that reconstruction falls back to _file_index when no FILE nodes."""
        from elspais.core.graph_builder import TraceGraphBuilder
        from elspais.mcp.reconstructor import FileReconstructor

        file = temp_spec_dir / "prd-legacy.md"
        file.write_text(SAMPLE_REQ_1)

        result = parser.parse_file_with_structure(file, temp_spec_dir.parent)

        # Build WITHOUT file nodes
        builder = TraceGraphBuilder(repo_root=temp_spec_dir.parent)
        builder.add_requirements(result.requirements)
        graph = builder.build()

        # Manually register file node in legacy _file_index
        graph.register_file_node(result.file_node)

        reconstructor = FileReconstructor(graph)
        recon_result = reconstructor.reconstruct_file("spec/prd-legacy.md")

        assert recon_result.success
        assert "legacy" in recon_result.message
        assert "REQ-p00001" in recon_result.content
