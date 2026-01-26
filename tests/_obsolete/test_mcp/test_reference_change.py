"""Tests for reference type change functionality in MCP mutator."""

import pytest
from pathlib import Path
from textwrap import dedent
from typing import Any, Dict

from elspais.mcp.mutator import SpecFileMutator, ReferenceType, ReferenceChange

# Import MCP server only if available
try:
    from elspais.mcp.server import MCP_AVAILABLE
except ImportError:
    MCP_AVAILABLE = False


@pytest.fixture
def temp_spec_dir(tmp_path):
    """Create a temporary spec directory with test files."""
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    return spec_dir


@pytest.fixture
def mutator(tmp_path):
    """Create a SpecFileMutator instance."""
    return SpecFileMutator(working_dir=tmp_path)


class TestChangeReferenceTypeBasic:
    """Basic tests for changing reference types."""

    def test_change_implements_to_refines(self, tmp_path, mutator, temp_spec_dir):
        """Test changing a reference from Implements to Refines."""
        spec_file = temp_spec_dir / "dev.md"
        spec_file.write_text(dedent("""\
            # REQ-d00001: Dev Requirement

            **Level**: Dev | **Status**: Active | **Implements**: REQ-p00001

            ## Assertions

            A. The system SHALL do something.

            *End* *Dev Requirement* | **Hash**: abc123
            ---
        """))

        result = mutator.change_reference_type(
            source_id="REQ-d00001",
            target_id="REQ-p00001",
            new_type=ReferenceType.REFINES,
            file_path=spec_file,
        )

        assert result.success is True
        assert result.old_type == ReferenceType.IMPLEMENTS
        assert result.new_type == ReferenceType.REFINES
        assert "Refines" in result.message.lower() or "refines" in result.message

        # Verify file was updated
        content = spec_file.read_text()
        assert "**Refines**: REQ-p00001" in content
        assert "**Implements**: REQ-p00001" not in content

    def test_change_refines_to_implements(self, tmp_path, mutator, temp_spec_dir):
        """Test changing a reference from Refines to Implements."""
        spec_file = temp_spec_dir / "dev.md"
        spec_file.write_text(dedent("""\
            # REQ-d00001: Dev Requirement

            **Level**: Dev | **Status**: Active | **Refines**: REQ-p00001

            ## Assertions

            A. The system SHALL do something.

            *End* *Dev Requirement* | **Hash**: abc123
            ---
        """))

        result = mutator.change_reference_type(
            source_id="REQ-d00001",
            target_id="REQ-p00001",
            new_type=ReferenceType.IMPLEMENTS,
            file_path=spec_file,
        )

        assert result.success is True
        assert result.old_type == ReferenceType.REFINES
        assert result.new_type == ReferenceType.IMPLEMENTS

        # Verify file was updated
        content = spec_file.read_text()
        assert "**Implements**: REQ-p00001" in content
        assert "**Refines**: REQ-p00001" not in content

    def test_already_correct_type(self, tmp_path, mutator, temp_spec_dir):
        """Test that no change occurs when already the correct type."""
        spec_file = temp_spec_dir / "dev.md"
        original_content = dedent("""\
            # REQ-d00001: Dev Requirement

            **Level**: Dev | **Status**: Active | **Implements**: REQ-p00001

            ## Assertions

            A. The system SHALL do something.

            *End* *Dev Requirement* | **Hash**: abc123
            ---
        """)
        spec_file.write_text(original_content)

        result = mutator.change_reference_type(
            source_id="REQ-d00001",
            target_id="REQ-p00001",
            new_type=ReferenceType.IMPLEMENTS,
            file_path=spec_file,
        )

        assert result.success is True
        assert result.old_type == ReferenceType.IMPLEMENTS
        assert result.new_type == ReferenceType.IMPLEMENTS
        assert "already" in result.message.lower()


class TestChangeReferenceTypeMultipleRefs:
    """Tests for changing references when multiple refs exist."""

    def test_preserve_other_implements_refs(self, tmp_path, mutator, temp_spec_dir):
        """Test that other Implements references are preserved."""
        spec_file = temp_spec_dir / "dev.md"
        spec_file.write_text(dedent("""\
            # REQ-d00001: Dev Requirement

            **Level**: Dev | **Status**: Active | **Implements**: REQ-p00001, REQ-p00002, REQ-p00003

            ## Assertions

            A. The system SHALL do something.

            *End* *Dev Requirement* | **Hash**: abc123
            ---
        """))

        result = mutator.change_reference_type(
            source_id="REQ-d00001",
            target_id="REQ-p00002",
            new_type=ReferenceType.REFINES,
            file_path=spec_file,
        )

        assert result.success is True

        # Verify file was updated correctly
        content = spec_file.read_text()
        # REQ-p00001 and REQ-p00003 should still be in Implements
        assert "REQ-p00001" in content
        assert "REQ-p00003" in content
        # REQ-p00002 should now be in Refines
        assert "**Refines**: REQ-p00002" in content

    def test_add_to_existing_refines(self, tmp_path, mutator, temp_spec_dir):
        """Test adding to existing Refines field when changing type."""
        spec_file = temp_spec_dir / "dev.md"
        spec_file.write_text(dedent("""\
            # REQ-d00001: Dev Requirement

            **Level**: Dev | **Status**: Active | **Implements**: REQ-p00001 | **Refines**: REQ-p00099

            ## Assertions

            A. The system SHALL do something.

            *End* *Dev Requirement* | **Hash**: abc123
            ---
        """))

        result = mutator.change_reference_type(
            source_id="REQ-d00001",
            target_id="REQ-p00001",
            new_type=ReferenceType.REFINES,
            file_path=spec_file,
        )

        assert result.success is True

        # Verify file was updated correctly
        content = spec_file.read_text()
        # Both REQ-p00099 and REQ-p00001 should be in Refines
        assert "REQ-p00099" in content
        assert "REQ-p00001" in content
        # The Refines field should contain both
        refines_match = content.split("**Refines**:")[1].split("|")[0]
        assert "REQ-p00099" in refines_match
        assert "REQ-p00001" in refines_match

    def test_remove_empty_implements_field(self, tmp_path, mutator, temp_spec_dir):
        """Test that empty Implements field is removed when last ref is moved."""
        spec_file = temp_spec_dir / "dev.md"
        spec_file.write_text(dedent("""\
            # REQ-d00001: Dev Requirement

            **Level**: Dev | **Status**: Active | **Implements**: REQ-p00001

            ## Assertions

            A. The system SHALL do something.

            *End* *Dev Requirement* | **Hash**: abc123
            ---
        """))

        result = mutator.change_reference_type(
            source_id="REQ-d00001",
            target_id="REQ-p00001",
            new_type=ReferenceType.REFINES,
            file_path=spec_file,
        )

        assert result.success is True

        # Verify empty Implements field is removed
        content = spec_file.read_text()
        # Should not have "**Implements**: -" or empty Implements
        assert "**Implements**: -" not in content
        # Should have Refines with the ref
        assert "**Refines**: REQ-p00001" in content


class TestChangeReferenceTypeErrors:
    """Tests for error handling in reference type changes."""

    def test_requirement_not_found(self, tmp_path, mutator, temp_spec_dir):
        """Test error when source requirement doesn't exist in file."""
        spec_file = temp_spec_dir / "dev.md"
        spec_file.write_text(dedent("""\
            # REQ-d00001: Dev Requirement

            **Level**: Dev | **Status**: Active | **Implements**: REQ-p00001

            ## Assertions

            A. The system SHALL do something.

            *End* *Dev Requirement* | **Hash**: abc123
            ---
        """))

        result = mutator.change_reference_type(
            source_id="REQ-NONEXISTENT",
            target_id="REQ-p00001",
            new_type=ReferenceType.REFINES,
            file_path=spec_file,
        )

        assert result.success is False
        assert "not found" in result.message.lower()

    def test_reference_not_found(self, tmp_path, mutator, temp_spec_dir):
        """Test error when target reference doesn't exist in requirement."""
        spec_file = temp_spec_dir / "dev.md"
        spec_file.write_text(dedent("""\
            # REQ-d00001: Dev Requirement

            **Level**: Dev | **Status**: Active | **Implements**: REQ-p00001

            ## Assertions

            A. The system SHALL do something.

            *End* *Dev Requirement* | **Hash**: abc123
            ---
        """))

        result = mutator.change_reference_type(
            source_id="REQ-d00001",
            target_id="REQ-NOTREF",
            new_type=ReferenceType.REFINES,
            file_path=spec_file,
        )

        assert result.success is False
        assert "not found" in result.message.lower()

    def test_file_not_found(self, tmp_path, mutator):
        """Test error when spec file doesn't exist."""
        nonexistent = tmp_path / "spec" / "nonexistent.md"

        result = mutator.change_reference_type(
            source_id="REQ-d00001",
            target_id="REQ-p00001",
            new_type=ReferenceType.REFINES,
            file_path=nonexistent,
        )

        assert result.success is False
        assert "not found" in result.message.lower()

    def test_no_metadata_line(self, tmp_path, mutator, temp_spec_dir):
        """Test error when requirement has no metadata line."""
        spec_file = temp_spec_dir / "dev.md"
        spec_file.write_text(dedent("""\
            # REQ-d00001: Dev Requirement

            Some body content without metadata line.

            *End* *Dev Requirement* | **Hash**: abc123
            ---
        """))

        result = mutator.change_reference_type(
            source_id="REQ-d00001",
            target_id="REQ-p00001",
            new_type=ReferenceType.REFINES,
            file_path=spec_file,
        )

        assert result.success is False
        assert "metadata" in result.message.lower() or "not found" in result.message.lower()


class TestChangeReferenceTypeFormats:
    """Tests for different metadata line formats."""

    def test_status_before_implements(self, tmp_path, mutator, temp_spec_dir):
        """Test format with Status before Implements."""
        spec_file = temp_spec_dir / "dev.md"
        spec_file.write_text(dedent("""\
            # REQ-d00001: Dev Requirement

            **Level**: Dev | **Status**: Active | **Implements**: REQ-p00001

            ## Assertions

            A. The system SHALL do something.

            *End* *Dev Requirement* | **Hash**: abc123
            ---
        """))

        result = mutator.change_reference_type(
            source_id="REQ-d00001",
            target_id="REQ-p00001",
            new_type=ReferenceType.REFINES,
            file_path=spec_file,
        )

        assert result.success is True
        content = spec_file.read_text()
        assert "**Refines**: REQ-p00001" in content
        # Status should still be present
        assert "**Status**: Active" in content

    def test_implements_before_status(self, tmp_path, mutator, temp_spec_dir):
        """Test format with Implements before Status."""
        spec_file = temp_spec_dir / "dev.md"
        spec_file.write_text(dedent("""\
            # REQ-d00001: Dev Requirement

            **Level**: Dev | **Implements**: REQ-p00001 | **Status**: Active

            ## Assertions

            A. The system SHALL do something.

            *End* *Dev Requirement* | **Hash**: abc123
            ---
        """))

        result = mutator.change_reference_type(
            source_id="REQ-d00001",
            target_id="REQ-p00001",
            new_type=ReferenceType.REFINES,
            file_path=spec_file,
        )

        assert result.success is True
        content = spec_file.read_text()
        assert "**Refines**: REQ-p00001" in content
        # Status should still be present
        assert "**Status**: Active" in content

    def test_assertion_specific_reference(self, tmp_path, mutator, temp_spec_dir):
        """Test changing assertion-specific reference (e.g., REQ-p00001-A)."""
        spec_file = temp_spec_dir / "dev.md"
        spec_file.write_text(dedent("""\
            # REQ-d00001: Dev Requirement

            **Level**: Dev | **Status**: Active | **Implements**: REQ-p00001-A

            ## Assertions

            A. The system SHALL do something.

            *End* *Dev Requirement* | **Hash**: abc123
            ---
        """))

        result = mutator.change_reference_type(
            source_id="REQ-d00001",
            target_id="REQ-p00001-A",
            new_type=ReferenceType.REFINES,
            file_path=spec_file,
        )

        assert result.success is True
        content = spec_file.read_text()
        assert "**Refines**: REQ-p00001-A" in content
        assert "**Implements**: REQ-p00001-A" not in content


class TestChangeReferenceTypePreservesContent:
    """Tests verifying content preservation."""

    def test_preserves_surrounding_content(self, tmp_path, mutator, temp_spec_dir):
        """Test that content before and after requirement is preserved."""
        spec_file = temp_spec_dir / "dev.md"
        spec_file.write_text(dedent("""\
            # Some preamble

            This is some intro text.

            # REQ-d00001: Dev Requirement

            **Level**: Dev | **Status**: Active | **Implements**: REQ-p00001

            ## Assertions

            A. The system SHALL do something.

            *End* *Dev Requirement* | **Hash**: abc123
            ---

            # REQ-d00002: Another Requirement

            **Level**: Dev | **Status**: Active | **Implements**: REQ-p00002

            ## Assertions

            A. The system SHALL do something else.

            *End* *Another Requirement* | **Hash**: def456
            ---
        """))

        result = mutator.change_reference_type(
            source_id="REQ-d00001",
            target_id="REQ-p00001",
            new_type=ReferenceType.REFINES,
            file_path=spec_file,
        )

        assert result.success is True
        content = spec_file.read_text()

        # Preamble preserved
        assert "# Some preamble" in content
        assert "This is some intro text." in content

        # Other requirement preserved
        assert "REQ-d00002" in content
        assert "**Implements**: REQ-p00002" in content

    def test_preserves_assertions_and_rationale(self, tmp_path, mutator, temp_spec_dir):
        """Test that assertions and rationale are preserved."""
        spec_file = temp_spec_dir / "dev.md"
        spec_file.write_text(dedent("""\
            # REQ-d00001: Dev Requirement

            **Level**: Dev | **Status**: Active | **Implements**: REQ-p00001

            ## Assertions

            A. The system SHALL do something specific.
            B. The system SHALL NOT do bad things.

            ## Rationale

            This is why we need this requirement.

            *End* *Dev Requirement* | **Hash**: abc123
            ---
        """))

        result = mutator.change_reference_type(
            source_id="REQ-d00001",
            target_id="REQ-p00001",
            new_type=ReferenceType.REFINES,
            file_path=spec_file,
        )

        assert result.success is True
        content = spec_file.read_text()

        # Assertions preserved
        assert "A. The system SHALL do something specific." in content
        assert "B. The system SHALL NOT do bad things." in content

        # Rationale preserved
        assert "## Rationale" in content
        assert "This is why we need this requirement." in content

    def test_preserves_hash(self, tmp_path, mutator, temp_spec_dir):
        """Test that hash is preserved in the end marker."""
        spec_file = temp_spec_dir / "dev.md"
        spec_file.write_text(dedent("""\
            # REQ-d00001: Dev Requirement

            **Level**: Dev | **Status**: Active | **Implements**: REQ-p00001

            ## Assertions

            A. The system SHALL do something.

            *End* *Dev Requirement* | **Hash**: abc123
            ---
        """))

        result = mutator.change_reference_type(
            source_id="REQ-d00001",
            target_id="REQ-p00001",
            new_type=ReferenceType.REFINES,
            file_path=spec_file,
        )

        assert result.success is True
        content = spec_file.read_text()
        assert "**Hash**: abc123" in content


# Skip MCP tool tests if MCP not available
@pytest.mark.skipif(not MCP_AVAILABLE, reason="MCP dependencies not installed")
class TestChangeReferenceTypeMCPTool:
    """Tests for the change_reference_type MCP tool."""

    def test_mcp_tool_change_implements_to_refines(self, tmp_path):
        """Test MCP tool changes Implements to Refines."""
        from elspais.mcp.server import create_server

        # Create minimal project
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        config_file = tmp_path / ".elspais.toml"
        config_file.write_text("""
[project]
name = "test"
""")

        req_file = spec_dir / "requirements.md"
        req_file.write_text(dedent("""\
            # REQ-p00001: Parent Requirement

            **Level**: PRD | **Status**: Active

            ## Assertions

            A. Parent assertion.

            *End* *Parent Requirement* | **Hash**: p1hash
            ---

            # REQ-d00001: Child Requirement

            **Level**: Dev | **Status**: Active | **Implements**: REQ-p00001

            ## Assertions

            A. Child assertion.

            *End* *Child Requirement* | **Hash**: c1hash
            ---
        """))

        mcp = create_server(tmp_path)
        result = _call_tool(
            mcp,
            "change_reference_type",
            source_id="REQ-d00001",
            target_id="REQ-p00001",
            new_type="refines",
        )

        assert result["success"] is True
        assert result["old_type"] == "implements"
        assert result["new_type"] == "refines"

        # Verify file was updated
        content = req_file.read_text()
        assert "**Refines**: REQ-p00001" in content
        assert "**Implements**: REQ-p00001" not in content

    def test_mcp_tool_change_refines_to_implements(self, tmp_path):
        """Test MCP tool changes Refines to Implements."""
        from elspais.mcp.server import create_server

        # Create minimal project
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        config_file = tmp_path / ".elspais.toml"
        config_file.write_text("""
[project]
name = "test"
""")

        req_file = spec_dir / "requirements.md"
        req_file.write_text(dedent("""\
            # REQ-p00001: Parent Requirement

            **Level**: PRD | **Status**: Active

            ## Assertions

            A. Parent assertion.

            *End* *Parent Requirement* | **Hash**: p1hash
            ---

            # REQ-d00001: Child Requirement

            **Level**: Dev | **Status**: Active | **Refines**: REQ-p00001

            ## Assertions

            A. Child assertion.

            *End* *Child Requirement* | **Hash**: c1hash
            ---
        """))

        mcp = create_server(tmp_path)
        result = _call_tool(
            mcp,
            "change_reference_type",
            source_id="REQ-d00001",
            target_id="REQ-p00001",
            new_type="implements",
        )

        assert result["success"] is True
        assert result["old_type"] == "refines"
        assert result["new_type"] == "implements"

        # Verify file was updated
        content = req_file.read_text()
        assert "**Implements**: REQ-p00001" in content
        assert "**Refines**: REQ-p00001" not in content

    def test_mcp_tool_invalid_type(self, tmp_path):
        """Test MCP tool rejects invalid reference type."""
        from elspais.mcp.server import create_server

        # Create minimal project
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        config_file = tmp_path / ".elspais.toml"
        config_file.write_text("""
[project]
name = "test"
""")

        req_file = spec_dir / "requirements.md"
        req_file.write_text(dedent("""\
            # REQ-d00001: Child Requirement

            **Level**: Dev | **Status**: Active | **Implements**: REQ-p00001

            ## Assertions

            A. Child assertion.

            *End* *Child Requirement* | **Hash**: c1hash
            ---
        """))

        mcp = create_server(tmp_path)
        result = _call_tool(
            mcp,
            "change_reference_type",
            source_id="REQ-d00001",
            target_id="REQ-p00001",
            new_type="invalid",
        )

        assert result["success"] is False
        assert "error" in result
        assert "invalid" in result["error"].lower()

    def test_mcp_tool_source_not_found(self, tmp_path):
        """Test MCP tool handles missing source requirement."""
        from elspais.mcp.server import create_server

        # Create minimal project
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        config_file = tmp_path / ".elspais.toml"
        config_file.write_text("""
[project]
name = "test"
""")

        req_file = spec_dir / "requirements.md"
        req_file.write_text(dedent("""\
            # REQ-d00001: Child Requirement

            **Level**: Dev | **Status**: Active | **Implements**: REQ-p00001

            ## Assertions

            A. Child assertion.

            *End* *Child Requirement* | **Hash**: c1hash
            ---
        """))

        mcp = create_server(tmp_path)
        result = _call_tool(
            mcp,
            "change_reference_type",
            source_id="REQ-NONEXISTENT",
            target_id="REQ-p00001",
            new_type="refines",
        )

        assert result["success"] is False
        assert "error" in result
        assert "not found" in result["error"].lower()

    def test_mcp_tool_invalidates_cache(self, tmp_path):
        """Test MCP tool invalidates requirements and graph cache."""
        from elspais.mcp.server import create_server

        # Create minimal project
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        config_file = tmp_path / ".elspais.toml"
        config_file.write_text("""
[project]
name = "test"
""")

        req_file = spec_dir / "requirements.md"
        req_file.write_text(dedent("""\
            # REQ-p00001: Parent Requirement

            **Level**: PRD | **Status**: Active

            ## Assertions

            A. Parent assertion.

            *End* *Parent Requirement* | **Hash**: p1hash
            ---

            # REQ-d00001: Child Requirement

            **Level**: Dev | **Status**: Active | **Implements**: REQ-p00001

            ## Assertions

            A. Child assertion.

            *End* *Child Requirement* | **Hash**: c1hash
            ---
        """))

        mcp = create_server(tmp_path)

        # First, get requirements to populate cache
        req_before = _call_tool(mcp, "get_requirement", req_id="REQ-d00001")
        assert "REQ-p00001" in req_before.get("implements", [])

        # Change reference type
        result = _call_tool(
            mcp,
            "change_reference_type",
            source_id="REQ-d00001",
            target_id="REQ-p00001",
            new_type="refines",
        )
        assert result["success"] is True

        # Get requirements again - should reflect the change
        req_after = _call_tool(mcp, "get_requirement", req_id="REQ-d00001")
        assert "REQ-p00001" in req_after.get("refines", [])
        assert "REQ-p00001" not in req_after.get("implements", [])


def _call_tool(mcp: Any, tool_name: str, **kwargs) -> Dict[str, Any]:
    """
    Helper to call an MCP tool by name.

    FastMCP stores tools as functions that can be accessed via the
    _tool_manager. We iterate to find the matching tool.
    """
    # Access the tool manager
    if hasattr(mcp, "_tool_manager"):
        # FastMCP stores tools in _tool_manager._tools dict
        tools = mcp._tool_manager._tools
        if tool_name in tools:
            tool = tools[tool_name]
            return tool.fn(**kwargs)

    # Fallback for older FastMCP versions
    if hasattr(mcp, "tools"):
        for tool in mcp.tools:
            if tool.name == tool_name:
                return tool.fn(**kwargs)

    raise ValueError(f"Tool {tool_name} not found")
