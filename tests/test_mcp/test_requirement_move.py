"""
Tests for requirement move functionality in SpecFileMutator.

Tests cover:
- Moving requirements to different files (start, end, after positions)
- Creating new files when target doesn't exist
- Error handling (same file, missing req, missing after_id)
- Whitespace and format preservation
- MCP tool integration
"""

import pytest
from pathlib import Path

from elspais.mcp.mutator import SpecFileMutator, RequirementMove


# Sample requirement content for testing
SAMPLE_REQ_1 = """# REQ-p00001: First Requirement

**Level**: PRD | **Status**: Active

## Assertions

A. The system SHALL do something.

## Rationale

This is the first requirement.

*End* *First Requirement* | **Hash**: abc12345

---"""

SAMPLE_REQ_2 = """# REQ-p00002: Second Requirement

**Level**: PRD | **Status**: Active | **Implements**: REQ-p00001

## Assertions

A. The system SHALL do another thing.

*End* *Second Requirement* | **Hash**: def67890

---"""

SAMPLE_REQ_3 = """# REQ-p00003: Third Requirement

**Level**: PRD | **Status**: Active

## Assertions

A. The system SHALL do a third thing.

*End* *Third Requirement* | **Hash**: ghi11111

---"""


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


class TestMoveRequirementBasic:
    """Basic tests for move_requirement method."""

    def test_move_to_end_of_existing_file(self, tmp_path, mutator, temp_spec_dir):
        """Test moving requirement to end of another file."""
        # Create source file with one requirement
        source = temp_spec_dir / "source.md"
        source.write_text(SAMPLE_REQ_1)

        # Create target file with one requirement
        target = temp_spec_dir / "target.md"
        target.write_text(SAMPLE_REQ_2)

        result = mutator.move_requirement(
            req_id="REQ-p00001",
            source_file=source,
            target_file=target,
            position="end",
        )

        assert result.success
        assert result.req_id == "REQ-p00001"
        assert result.position == "end"
        assert "Moved REQ-p00001" in result.message

        # Verify source file no longer has the requirement
        source_content = source.read_text()
        assert "REQ-p00001" not in source_content

        # Verify target file has both requirements
        target_content = target.read_text()
        assert "REQ-p00001" in target_content
        assert "REQ-p00002" in target_content
        # REQ-p00002 should come before REQ-p00001
        assert target_content.find("REQ-p00002") < target_content.find("REQ-p00001")

    def test_move_to_start_of_existing_file(self, tmp_path, mutator, temp_spec_dir):
        """Test moving requirement to start of another file."""
        source = temp_spec_dir / "source.md"
        source.write_text(SAMPLE_REQ_1)

        target = temp_spec_dir / "target.md"
        target.write_text(SAMPLE_REQ_2)

        result = mutator.move_requirement(
            req_id="REQ-p00001",
            source_file=source,
            target_file=target,
            position="start",
        )

        assert result.success
        assert result.position == "start"

        target_content = target.read_text()
        # REQ-p00001 should come before REQ-p00002
        assert target_content.find("REQ-p00001") < target_content.find("REQ-p00002")

    def test_move_after_specific_requirement(self, tmp_path, mutator, temp_spec_dir):
        """Test moving requirement after a specific requirement."""
        source = temp_spec_dir / "source.md"
        source.write_text(SAMPLE_REQ_3)

        target = temp_spec_dir / "target.md"
        target.write_text(SAMPLE_REQ_1 + "\n" + SAMPLE_REQ_2)

        result = mutator.move_requirement(
            req_id="REQ-p00003",
            source_file=source,
            target_file=target,
            position="after",
            after_id="REQ-p00001",
        )

        assert result.success
        assert result.position == "after"
        assert result.after_id == "REQ-p00001"

        target_content = target.read_text()
        # Order should be: REQ-p00001, REQ-p00003, REQ-p00002
        pos1 = target_content.find("REQ-p00001")
        pos3 = target_content.find("REQ-p00003")
        pos2 = target_content.find("REQ-p00002")
        assert pos1 < pos3 < pos2

    def test_move_to_new_file(self, tmp_path, mutator, temp_spec_dir):
        """Test moving requirement creates new file if needed."""
        source = temp_spec_dir / "source.md"
        source.write_text(SAMPLE_REQ_1)

        target = temp_spec_dir / "new-file.md"
        assert not target.exists()

        result = mutator.move_requirement(
            req_id="REQ-p00001",
            source_file=source,
            target_file=target,
            position="end",
        )

        assert result.success
        assert target.exists()

        target_content = target.read_text()
        assert "REQ-p00001" in target_content
        assert "First Requirement" in target_content


class TestMoveRequirementErrors:
    """Error handling tests."""

    def test_source_requirement_not_found(self, tmp_path, mutator, temp_spec_dir):
        """Test error when source requirement doesn't exist."""
        source = temp_spec_dir / "source.md"
        source.write_text(SAMPLE_REQ_1)

        target = temp_spec_dir / "target.md"
        target.write_text(SAMPLE_REQ_2)

        result = mutator.move_requirement(
            req_id="REQ-nonexistent",
            source_file=source,
            target_file=target,
            position="end",
        )

        assert not result.success
        assert "not found" in result.message

    def test_after_id_not_found_in_target(self, tmp_path, mutator, temp_spec_dir):
        """Test error when after_id doesn't exist in target file."""
        source = temp_spec_dir / "source.md"
        source.write_text(SAMPLE_REQ_1)

        target = temp_spec_dir / "target.md"
        target.write_text(SAMPLE_REQ_2)

        result = mutator.move_requirement(
            req_id="REQ-p00001",
            source_file=source,
            target_file=target,
            position="after",
            after_id="REQ-nonexistent",
        )

        assert not result.success
        assert "not found" in result.message.lower()

    def test_same_source_and_target(self, tmp_path, mutator, temp_spec_dir):
        """Test error when source and target are the same file."""
        source = temp_spec_dir / "source.md"
        source.write_text(SAMPLE_REQ_1 + "\n" + SAMPLE_REQ_2)

        result = mutator.move_requirement(
            req_id="REQ-p00001",
            source_file=source,
            target_file=source,
            position="end",
        )

        assert not result.success
        assert "same" in result.message.lower()

    def test_invalid_position(self, tmp_path, mutator, temp_spec_dir):
        """Test error for invalid position value."""
        source = temp_spec_dir / "source.md"
        source.write_text(SAMPLE_REQ_1)

        target = temp_spec_dir / "target.md"
        target.write_text(SAMPLE_REQ_2)

        result = mutator.move_requirement(
            req_id="REQ-p00001",
            source_file=source,
            target_file=target,
            position="invalid",
        )

        assert not result.success
        assert "invalid" in result.message.lower()

    def test_after_position_without_after_id(self, tmp_path, mutator, temp_spec_dir):
        """Test error when position='after' but no after_id."""
        source = temp_spec_dir / "source.md"
        source.write_text(SAMPLE_REQ_1)

        target = temp_spec_dir / "target.md"
        target.write_text(SAMPLE_REQ_2)

        result = mutator.move_requirement(
            req_id="REQ-p00001",
            source_file=source,
            target_file=target,
            position="after",
            after_id=None,
        )

        assert not result.success
        assert "after_id" in result.message.lower()

    def test_source_file_not_found(self, tmp_path, mutator, temp_spec_dir):
        """Test error when source file doesn't exist."""
        source = temp_spec_dir / "nonexistent.md"
        target = temp_spec_dir / "target.md"
        target.write_text(SAMPLE_REQ_2)

        result = mutator.move_requirement(
            req_id="REQ-p00001",
            source_file=source,
            target_file=target,
            position="end",
        )

        assert not result.success
        assert "not found" in result.message.lower()


class TestMoveRequirementWhitespace:
    """Whitespace and formatting tests."""

    def test_preserves_requirement_content(self, tmp_path, mutator, temp_spec_dir):
        """Test that requirement content is preserved exactly."""
        source = temp_spec_dir / "source.md"
        source.write_text(SAMPLE_REQ_1)

        target = temp_spec_dir / "target.md"
        target.write_text("")

        result = mutator.move_requirement(
            req_id="REQ-p00001",
            source_file=source,
            target_file=target,
            position="end",
        )

        assert result.success

        target_content = target.read_text()
        # Core content should be preserved
        assert "First Requirement" in target_content
        assert "The system SHALL do something." in target_content
        assert "This is the first requirement." in target_content
        assert "abc12345" in target_content

    def test_adds_separator_if_missing(self, tmp_path, mutator, temp_spec_dir):
        """Test that --- separator is added if not present."""
        # Requirement without trailing separator
        req_no_sep = """# REQ-p00001: First Requirement

**Level**: PRD | **Status**: Active

## Assertions

A. The system SHALL do something.

*End* *First Requirement* | **Hash**: abc12345"""

        source = temp_spec_dir / "source.md"
        source.write_text(req_no_sep)

        target = temp_spec_dir / "target.md"
        target.write_text("")

        result = mutator.move_requirement(
            req_id="REQ-p00001",
            source_file=source,
            target_file=target,
            position="end",
        )

        assert result.success

        target_content = target.read_text()
        assert "---" in target_content

    def test_preserves_file_preamble(self, tmp_path, mutator, temp_spec_dir):
        """Test that preamble text in target file is preserved."""
        preamble = "# Spec File\n\nThis file contains requirements.\n\n"
        source = temp_spec_dir / "source.md"
        source.write_text(SAMPLE_REQ_1)

        target = temp_spec_dir / "target.md"
        target.write_text(preamble + SAMPLE_REQ_2)

        result = mutator.move_requirement(
            req_id="REQ-p00001",
            source_file=source,
            target_file=target,
            position="start",
        )

        assert result.success

        target_content = target.read_text()
        # Preamble should be preserved
        assert "# Spec File" in target_content
        assert "This file contains requirements." in target_content

    def test_cleans_up_source_whitespace(self, tmp_path, mutator, temp_spec_dir):
        """Test that source file doesn't have excess blank lines."""
        source = temp_spec_dir / "source.md"
        source.write_text(SAMPLE_REQ_1 + "\n" + SAMPLE_REQ_2)

        target = temp_spec_dir / "target.md"
        target.write_text("")

        result = mutator.move_requirement(
            req_id="REQ-p00001",
            source_file=source,
            target_file=target,
            position="end",
        )

        assert result.success

        source_content = source.read_text()
        # Should not have excessive blank lines
        assert "\n\n\n\n" not in source_content


class TestMoveRequirementPreservesContent:
    """Content preservation tests."""

    def test_preserves_other_requirements_in_source(self, tmp_path, mutator, temp_spec_dir):
        """Test that other requirements in source file are preserved."""
        source = temp_spec_dir / "source.md"
        source.write_text(SAMPLE_REQ_1 + "\n" + SAMPLE_REQ_2)

        target = temp_spec_dir / "target.md"
        target.write_text("")

        result = mutator.move_requirement(
            req_id="REQ-p00001",
            source_file=source,
            target_file=target,
            position="end",
        )

        assert result.success

        source_content = source.read_text()
        # Check that REQ-p00001's header (the requirement itself) is gone
        # but REQ-p00002's reference to it (Implements: REQ-p00001) remains
        assert "# REQ-p00001:" not in source_content
        assert "First Requirement" not in source_content
        assert "REQ-p00002" in source_content
        assert "Second Requirement" in source_content

    def test_preserves_other_requirements_in_target(self, tmp_path, mutator, temp_spec_dir):
        """Test that other requirements in target file are preserved."""
        source = temp_spec_dir / "source.md"
        source.write_text(SAMPLE_REQ_1)

        target = temp_spec_dir / "target.md"
        target.write_text(SAMPLE_REQ_2)

        result = mutator.move_requirement(
            req_id="REQ-p00001",
            source_file=source,
            target_file=target,
            position="end",
        )

        assert result.success

        target_content = target.read_text()
        assert "REQ-p00001" in target_content
        assert "REQ-p00002" in target_content
        assert "Second Requirement" in target_content

    def test_preserves_assertions_and_rationale(self, tmp_path, mutator, temp_spec_dir):
        """Test that assertions and rationale are preserved in move."""
        source = temp_spec_dir / "source.md"
        source.write_text(SAMPLE_REQ_1)

        target = temp_spec_dir / "target.md"
        target.write_text("")

        result = mutator.move_requirement(
            req_id="REQ-p00001",
            source_file=source,
            target_file=target,
            position="end",
        )

        assert result.success

        target_content = target.read_text()
        assert "## Assertions" in target_content
        assert "The system SHALL do something." in target_content
        assert "## Rationale" in target_content
        assert "This is the first requirement." in target_content

    def test_preserves_hash(self, tmp_path, mutator, temp_spec_dir):
        """Test that hash is preserved in the end marker."""
        source = temp_spec_dir / "source.md"
        source.write_text(SAMPLE_REQ_1)

        target = temp_spec_dir / "target.md"
        target.write_text("")

        result = mutator.move_requirement(
            req_id="REQ-p00001",
            source_file=source,
            target_file=target,
            position="end",
        )

        assert result.success

        target_content = target.read_text()
        assert "abc12345" in target_content


class TestFindInsertionPoint:
    """Tests for _find_insertion_point helper method."""

    def test_start_with_existing_requirement(self, tmp_path, mutator, temp_spec_dir):
        """Test finding start position with existing requirement."""
        file = temp_spec_dir / "test.md"
        file.write_text(SAMPLE_REQ_1)

        content = mutator._read_spec_file(file)
        idx, prefix = mutator._find_insertion_point(content, "start")

        # Should insert before the first requirement header
        assert idx == 0
        assert prefix == ""

    def test_start_with_preamble(self, tmp_path, mutator, temp_spec_dir):
        """Test finding start position with preamble before requirements."""
        file = temp_spec_dir / "test.md"
        file.write_text("# Title\n\nPreamble text.\n\n" + SAMPLE_REQ_1)

        content = mutator._read_spec_file(file)
        idx, prefix = mutator._find_insertion_point(content, "start")

        # Should insert before the first requirement header (line 4, 0-indexed)
        assert idx == 4

    def test_end_position(self, tmp_path, mutator, temp_spec_dir):
        """Test finding end position."""
        file = temp_spec_dir / "test.md"
        file.write_text(SAMPLE_REQ_1)

        content = mutator._read_spec_file(file)
        idx, prefix = mutator._find_insertion_point(content, "end")

        # Should insert after the last content line
        assert idx > 0
        assert prefix == "\n"

    def test_after_position(self, tmp_path, mutator, temp_spec_dir):
        """Test finding after position."""
        file = temp_spec_dir / "test.md"
        file.write_text(SAMPLE_REQ_1 + "\n" + SAMPLE_REQ_2)

        content = mutator._read_spec_file(file)
        idx, prefix = mutator._find_insertion_point(content, "after", "REQ-p00001")

        # Should insert after REQ-p00001
        # Find where REQ-p00002 starts to verify we're before it
        req2_start = None
        for i, line in enumerate(content.lines):
            if "REQ-p00002" in line:
                req2_start = i
                break

        assert req2_start is not None
        assert idx <= req2_start

    def test_after_with_invalid_id(self, tmp_path, mutator, temp_spec_dir):
        """Test after position with invalid ID raises ValueError."""
        file = temp_spec_dir / "test.md"
        file.write_text(SAMPLE_REQ_1)

        content = mutator._read_spec_file(file)

        with pytest.raises(ValueError, match="not found"):
            mutator._find_insertion_point(content, "after", "REQ-nonexistent")

    def test_empty_file(self, tmp_path, mutator, temp_spec_dir):
        """Test finding position in empty file."""
        file = temp_spec_dir / "test.md"
        file.write_text("")

        content = mutator._read_spec_file(file)
        idx, prefix = mutator._find_insertion_point(content, "end")

        assert idx == 0


class TestNormalizeRequirementForInsertion:
    """Tests for _normalize_requirement_for_insertion helper method."""

    def test_adds_separator_if_missing(self, tmp_path, mutator):
        """Test that separator is added if missing."""
        req_text = "# REQ-p00001: Title\n\n*End* *Title*"
        result = mutator._normalize_requirement_for_insertion(req_text)

        assert result.endswith("---")

    def test_preserves_existing_separator(self, tmp_path, mutator):
        """Test that existing separator is kept."""
        req_text = "# REQ-p00001: Title\n\n*End* *Title*\n\n---"
        result = mutator._normalize_requirement_for_insertion(req_text)

        assert result.endswith("---")
        # Should not have double separators
        assert "---\n\n---" not in result

    def test_strips_leading_whitespace(self, tmp_path, mutator):
        """Test that leading whitespace is stripped."""
        req_text = "\n\n  # REQ-p00001: Title\n\n*End* *Title*\n\n---"
        result = mutator._normalize_requirement_for_insertion(req_text)

        assert result.startswith("#")


class TestRemoveRequirementFromContent:
    """Tests for _remove_requirement_from_content helper method."""

    def test_removes_requirement(self, tmp_path, mutator, temp_spec_dir):
        """Test that requirement is removed from content."""
        file = temp_spec_dir / "test.md"
        file.write_text(SAMPLE_REQ_1)

        content = mutator._read_spec_file(file)
        location = mutator._find_requirement_lines(content, "REQ-p00001")

        result = mutator._remove_requirement_from_content(content, location)

        assert "REQ-p00001" not in result
        assert "First Requirement" not in result

    def test_preserves_other_requirements(self, tmp_path, mutator, temp_spec_dir):
        """Test that other requirements are preserved."""
        file = temp_spec_dir / "test.md"
        file.write_text(SAMPLE_REQ_1 + "\n" + SAMPLE_REQ_2)

        content = mutator._read_spec_file(file)
        location = mutator._find_requirement_lines(content, "REQ-p00001")

        result = mutator._remove_requirement_from_content(content, location)

        # Check that REQ-p00001's header (the requirement itself) is gone
        # but REQ-p00002's reference to it (Implements: REQ-p00001) remains
        assert "# REQ-p00001:" not in result
        assert "First Requirement" not in result
        assert "REQ-p00002" in result
        assert "Second Requirement" in result

    def test_cleans_up_whitespace(self, tmp_path, mutator, temp_spec_dir):
        """Test that excess whitespace is cleaned up."""
        file = temp_spec_dir / "test.md"
        file.write_text(SAMPLE_REQ_1 + "\n\n\n" + SAMPLE_REQ_2)

        content = mutator._read_spec_file(file)
        location = mutator._find_requirement_lines(content, "REQ-p00001")

        result = mutator._remove_requirement_from_content(content, location)

        # Should not have more than 2 consecutive newlines
        assert "\n\n\n\n" not in result


# MCP Tool Tests
try:
    import mcp

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False


@pytest.mark.skipif(not MCP_AVAILABLE, reason="MCP dependencies not installed")
class TestMoveRequirementMCPTool:
    """Tests for the move_requirement MCP tool."""

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

    def test_mcp_tool_move_to_end(self, tmp_path, mcp_context):
        """Test MCP tool moves requirement to end of file."""
        spec_dir = tmp_path / "spec"

        source = spec_dir / "source.md"
        source.write_text(SAMPLE_REQ_1)

        target = spec_dir / "target.md"
        target.write_text(SAMPLE_REQ_2)

        # Refresh context to pick up requirements
        mcp_context._requirements_cache = None

        from elspais.mcp.mutator import SpecFileMutator

        mutator = SpecFileMutator(tmp_path)
        result = mutator.move_requirement(
            req_id="REQ-p00001",
            source_file=source,
            target_file=target,
            position="end",
        )

        assert result.success

    def test_mcp_tool_move_to_start(self, tmp_path, mcp_context):
        """Test MCP tool moves requirement to start of file."""
        spec_dir = tmp_path / "spec"

        source = spec_dir / "source.md"
        source.write_text(SAMPLE_REQ_1)

        target = spec_dir / "target.md"
        target.write_text(SAMPLE_REQ_2)

        from elspais.mcp.mutator import SpecFileMutator

        mutator = SpecFileMutator(tmp_path)
        result = mutator.move_requirement(
            req_id="REQ-p00001",
            source_file=source,
            target_file=target,
            position="start",
        )

        assert result.success

        target_content = target.read_text()
        # REQ-p00001 should come first
        assert target_content.find("REQ-p00001") < target_content.find("REQ-p00002")

    def test_mcp_tool_move_after(self, tmp_path, mcp_context):
        """Test MCP tool moves requirement after specific ID."""
        spec_dir = tmp_path / "spec"

        source = spec_dir / "source.md"
        source.write_text(SAMPLE_REQ_3)

        target = spec_dir / "target.md"
        target.write_text(SAMPLE_REQ_1 + "\n" + SAMPLE_REQ_2)

        from elspais.mcp.mutator import SpecFileMutator

        mutator = SpecFileMutator(tmp_path)
        result = mutator.move_requirement(
            req_id="REQ-p00003",
            source_file=source,
            target_file=target,
            position="after",
            after_id="REQ-p00001",
        )

        assert result.success
        assert result.after_id == "REQ-p00001"

    def test_mcp_tool_creates_new_file(self, tmp_path, mcp_context):
        """Test MCP tool creates target file if needed."""
        spec_dir = tmp_path / "spec"

        source = spec_dir / "source.md"
        source.write_text(SAMPLE_REQ_1)

        target = spec_dir / "new-file.md"
        assert not target.exists()

        from elspais.mcp.mutator import SpecFileMutator

        mutator = SpecFileMutator(tmp_path)
        result = mutator.move_requirement(
            req_id="REQ-p00001",
            source_file=source,
            target_file=target,
            position="end",
        )

        assert result.success
        assert target.exists()

    def test_mcp_tool_same_file_error(self, tmp_path, mcp_context):
        """Test MCP tool rejects same source and target file."""
        spec_dir = tmp_path / "spec"

        source = spec_dir / "source.md"
        source.write_text(SAMPLE_REQ_1 + "\n" + SAMPLE_REQ_2)

        from elspais.mcp.mutator import SpecFileMutator

        mutator = SpecFileMutator(tmp_path)
        result = mutator.move_requirement(
            req_id="REQ-p00001",
            source_file=source,
            target_file=source,
            position="end",
        )

        assert not result.success
        assert "same" in result.message.lower()
