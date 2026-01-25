"""
Tests for file deletion workflow in SpecFileMutator.

Tests cover:
- Analyzing files for deletion readiness
- Detecting remaining requirements
- Extracting non-requirement content
- Deleting empty files
- Force deletion with warnings
- MCP tool integration
"""

import pytest
from pathlib import Path

from elspais.mcp.mutator import (
    SpecFileMutator,
    FileDeletionAnalysis,
    FileDeletionResult,
)


# Sample requirement content for testing
SAMPLE_REQ_1 = """# REQ-p00001: First Requirement

**Level**: PRD | **Status**: Active

## Assertions

A. The system SHALL do something.

*End* *First Requirement* | **Hash**: abc12345

---"""

SAMPLE_REQ_2 = """# REQ-p00002: Second Requirement

**Level**: PRD | **Status**: Active

## Assertions

A. The system SHALL do another thing.

*End* *Second Requirement* | **Hash**: def67890

---"""

PREAMBLE_CONTENT = """# Spec File Title

This is a preamble that describes the file contents.
It should be preserved if the file is emptied.

"""

NON_REQ_FOOTER = """

## Additional Notes

These are additional notes at the end of the file.
"""


@pytest.fixture
def temp_spec_dir(tmp_path):
    """Create a temporary spec directory with sample files."""
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    return spec_dir


@pytest.fixture
def mutator(tmp_path):
    """Create a SpecFileMutator for the temp directory."""
    return SpecFileMutator(tmp_path)


class TestAnalyzeFileForDeletion:
    """Tests for analyze_file_for_deletion method."""

    def test_empty_file_can_be_deleted(self, tmp_path, mutator, temp_spec_dir):
        """Test that an empty file can be deleted."""
        file = temp_spec_dir / "empty.md"
        file.write_text("")

        result = mutator.analyze_file_for_deletion(file)

        assert result.can_delete
        assert len(result.remaining_requirements) == 0
        assert not result.has_non_requirement_content

    def test_file_with_only_whitespace(self, tmp_path, mutator, temp_spec_dir):
        """Test that a file with only whitespace can be deleted."""
        file = temp_spec_dir / "whitespace.md"
        file.write_text("   \n\n  \n")

        result = mutator.analyze_file_for_deletion(file)

        assert result.can_delete
        assert len(result.remaining_requirements) == 0

    def test_file_with_requirement_cannot_be_deleted(self, tmp_path, mutator, temp_spec_dir):
        """Test that a file with requirements cannot be deleted."""
        file = temp_spec_dir / "with-req.md"
        file.write_text(SAMPLE_REQ_1)

        result = mutator.analyze_file_for_deletion(file)

        assert not result.can_delete
        assert "REQ-p00001" in result.remaining_requirements
        assert len(result.remaining_requirements) == 1
        assert "requirement" in result.message.lower()

    def test_file_with_multiple_requirements(self, tmp_path, mutator, temp_spec_dir):
        """Test detection of multiple requirements."""
        file = temp_spec_dir / "multi-req.md"
        file.write_text(SAMPLE_REQ_1 + "\n" + SAMPLE_REQ_2)

        result = mutator.analyze_file_for_deletion(file)

        assert not result.can_delete
        assert len(result.remaining_requirements) == 2
        assert "REQ-p00001" in result.remaining_requirements
        assert "REQ-p00002" in result.remaining_requirements

    def test_detects_non_requirement_content_preamble(self, tmp_path, mutator, temp_spec_dir):
        """Test detection of non-requirement content before requirements."""
        file = temp_spec_dir / "with-preamble.md"
        file.write_text(PREAMBLE_CONTENT + SAMPLE_REQ_1)

        result = mutator.analyze_file_for_deletion(file)

        assert not result.can_delete  # Has requirement
        assert result.has_non_requirement_content
        assert "Spec File Title" in result.non_requirement_content

    def test_detects_non_requirement_content_footer(self, tmp_path, mutator, temp_spec_dir):
        """Test detection of non-requirement content after requirements."""
        file = temp_spec_dir / "with-footer.md"
        file.write_text(SAMPLE_REQ_1 + NON_REQ_FOOTER)

        result = mutator.analyze_file_for_deletion(file)

        assert not result.can_delete  # Has requirement
        assert result.has_non_requirement_content
        assert "Additional Notes" in result.non_requirement_content

    def test_only_non_requirement_content(self, tmp_path, mutator, temp_spec_dir):
        """Test file with only non-requirement content."""
        file = temp_spec_dir / "non-req-only.md"
        file.write_text(PREAMBLE_CONTENT)

        result = mutator.analyze_file_for_deletion(file)

        assert result.can_delete  # No requirements
        assert len(result.remaining_requirements) == 0
        assert result.has_non_requirement_content
        assert "content that should be preserved" in result.message.lower()

    def test_file_not_found(self, tmp_path, mutator, temp_spec_dir):
        """Test handling of non-existent file."""
        file = temp_spec_dir / "nonexistent.md"

        result = mutator.analyze_file_for_deletion(file)

        assert not result.can_delete
        assert "not found" in result.message.lower()


class TestDeleteSpecFile:
    """Tests for delete_spec_file method."""

    def test_delete_empty_file(self, tmp_path, mutator, temp_spec_dir):
        """Test deleting an empty file."""
        file = temp_spec_dir / "empty.md"
        file.write_text("")

        result = mutator.delete_spec_file(file)

        assert result.success
        assert not file.exists()

    def test_refuse_delete_with_requirements(self, tmp_path, mutator, temp_spec_dir):
        """Test that deletion is refused when requirements exist."""
        file = temp_spec_dir / "with-req.md"
        file.write_text(SAMPLE_REQ_1)

        result = mutator.delete_spec_file(file)

        assert not result.success
        assert file.exists()  # File should not be deleted
        assert "cannot delete" in result.message.lower()

    def test_force_delete_with_requirements(self, tmp_path, mutator, temp_spec_dir):
        """Test force deletion with remaining requirements."""
        file = temp_spec_dir / "with-req.md"
        file.write_text(SAMPLE_REQ_1)

        result = mutator.delete_spec_file(file, force=True)

        assert result.success
        assert not file.exists()
        assert "forced" in result.message.lower()
        assert "lost" in result.message.lower()

    def test_extract_content_before_deletion(self, tmp_path, mutator, temp_spec_dir):
        """Test extracting non-requirement content before deletion."""
        file = temp_spec_dir / "with-content.md"
        file.write_text(PREAMBLE_CONTENT)

        target = temp_spec_dir / "extracted.md"

        result = mutator.delete_spec_file(file, extract_content_to=target)

        assert result.success
        assert not file.exists()
        assert target.exists()
        assert result.content_extracted
        assert "Spec File Title" in target.read_text()

    def test_extract_content_not_needed_for_empty(self, tmp_path, mutator, temp_spec_dir):
        """Test that extraction is skipped for empty files."""
        file = temp_spec_dir / "empty.md"
        file.write_text("")

        target = temp_spec_dir / "extracted.md"

        result = mutator.delete_spec_file(file, extract_content_to=target)

        assert result.success
        assert not file.exists()
        assert not result.content_extracted
        assert not target.exists()  # No content to extract

    def test_delete_file_outside_workspace(self, tmp_path, mutator, temp_spec_dir):
        """Test that files outside workspace cannot be deleted."""
        # Create file outside workspace
        outside = tmp_path.parent / "outside.md"
        outside.write_text("")

        result = mutator.delete_spec_file(outside)

        assert not result.success
        assert "outside" in result.message.lower()


class TestFindAllRequirements:
    """Tests for _find_all_requirements helper method."""

    def test_finds_single_requirement(self, tmp_path, mutator, temp_spec_dir):
        """Test finding a single requirement."""
        file = temp_spec_dir / "single.md"
        file.write_text(SAMPLE_REQ_1)

        content = mutator._read_spec_file(file)
        locations = mutator._find_all_requirements(content)

        assert len(locations) == 1
        assert "REQ-p00001" in locations[0].header_line

    def test_finds_multiple_requirements(self, tmp_path, mutator, temp_spec_dir):
        """Test finding multiple requirements."""
        file = temp_spec_dir / "multi.md"
        file.write_text(SAMPLE_REQ_1 + "\n" + SAMPLE_REQ_2)

        content = mutator._read_spec_file(file)
        locations = mutator._find_all_requirements(content)

        assert len(locations) == 2

    def test_empty_file_returns_empty_list(self, tmp_path, mutator, temp_spec_dir):
        """Test that empty file returns no requirements."""
        file = temp_spec_dir / "empty.md"
        file.write_text("")

        content = mutator._read_spec_file(file)
        locations = mutator._find_all_requirements(content)

        assert len(locations) == 0


class TestExtractNonRequirementContent:
    """Tests for _extract_non_requirement_content helper method."""

    def test_extracts_preamble(self, tmp_path, mutator, temp_spec_dir):
        """Test extracting preamble content."""
        file = temp_spec_dir / "preamble.md"
        file.write_text(PREAMBLE_CONTENT + SAMPLE_REQ_1)

        content = mutator._read_spec_file(file)
        locations = mutator._find_all_requirements(content)
        non_req = mutator._extract_non_requirement_content(content, locations)

        assert "Spec File Title" in non_req
        assert "REQ-p00001" not in non_req

    def test_extracts_footer(self, tmp_path, mutator, temp_spec_dir):
        """Test extracting footer content."""
        file = temp_spec_dir / "footer.md"
        file.write_text(SAMPLE_REQ_1 + NON_REQ_FOOTER)

        content = mutator._read_spec_file(file)
        locations = mutator._find_all_requirements(content)
        non_req = mutator._extract_non_requirement_content(content, locations)

        assert "Additional Notes" in non_req
        assert "REQ-p00001" not in non_req

    def test_no_locations_returns_full_content(self, tmp_path, mutator, temp_spec_dir):
        """Test that no requirements means entire file is non-requirement content."""
        file = temp_spec_dir / "no-req.md"
        file.write_text(PREAMBLE_CONTENT)

        content = mutator._read_spec_file(file)
        non_req = mutator._extract_non_requirement_content(content, [])

        assert "Spec File Title" in non_req


# MCP Tool Tests
try:
    import mcp

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False


@pytest.mark.skipif(not MCP_AVAILABLE, reason="MCP dependencies not installed")
class TestFileDeletionMCPTools:
    """Tests for the file deletion MCP tools."""

    @pytest.fixture
    def mcp_context(self, tmp_path):
        """Create MCP context for testing."""
        from elspais.mcp.context import WorkspaceContext

        # Create spec directory with config
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        config_file = tmp_path / ".elspais.toml"
        config_file.write_text("""
[project]
name = "test"

[directories]
spec = ["spec"]
""")

        ctx = WorkspaceContext(working_dir=tmp_path)
        return ctx

    def test_prepare_file_deletion_tool(self, tmp_path, mcp_context):
        """Test prepare_file_deletion MCP tool."""
        spec_dir = tmp_path / "spec"
        file = spec_dir / "test.md"
        file.write_text(SAMPLE_REQ_1)

        from elspais.mcp.mutator import SpecFileMutator

        mutator = SpecFileMutator(tmp_path)
        result = mutator.analyze_file_for_deletion(file)

        assert not result.can_delete
        assert "REQ-p00001" in result.remaining_requirements

    def test_delete_spec_file_tool_empty(self, tmp_path, mcp_context):
        """Test delete_spec_file MCP tool with empty file."""
        spec_dir = tmp_path / "spec"
        file = spec_dir / "empty.md"
        file.write_text("")

        from elspais.mcp.mutator import SpecFileMutator

        mutator = SpecFileMutator(tmp_path)
        result = mutator.delete_spec_file(file)

        assert result.success
        assert not file.exists()

    def test_delete_spec_file_tool_refuses_with_reqs(self, tmp_path, mcp_context):
        """Test delete_spec_file MCP tool refuses when requirements exist."""
        spec_dir = tmp_path / "spec"
        file = spec_dir / "with-req.md"
        file.write_text(SAMPLE_REQ_1)

        from elspais.mcp.mutator import SpecFileMutator

        mutator = SpecFileMutator(tmp_path)
        result = mutator.delete_spec_file(file)

        assert not result.success
        assert file.exists()

    def test_delete_with_content_extraction(self, tmp_path, mcp_context):
        """Test delete with content extraction."""
        spec_dir = tmp_path / "spec"
        file = spec_dir / "with-content.md"
        file.write_text(PREAMBLE_CONTENT)
        target = spec_dir / "extracted.md"

        from elspais.mcp.mutator import SpecFileMutator

        mutator = SpecFileMutator(tmp_path)
        result = mutator.delete_spec_file(file, extract_content_to=target)

        assert result.success
        assert result.content_extracted
        assert target.exists()
