"""
Tests for the edit command.
"""

import json
from pathlib import Path

import pytest


class TestModifyImplements:
    """Tests for modifying the Implements field."""

    def test_modify_implements_single_value(self, tmp_path: Path):
        """Test changing implements to a single value."""
        from elspais.commands.edit import modify_implements

        spec_file = tmp_path / "dev-core.md"
        spec_file.write_text("""
# REQ-d00001: Test Requirement

**Level**: DEV | **Status**: Active | **Implements**: p00001

Body text here.

*End* *Test Requirement* | **Hash**: test1234
---
""")

        result = modify_implements(spec_file, "REQ-d00001", ["p00002"])

        assert result["success"] is True
        assert result["old_implements"] == ["p00001"]
        assert result["new_implements"] == ["p00002"]

        # Verify file was updated
        content = spec_file.read_text()
        assert "**Implements**: p00002" in content
        assert "**Implements**: p00001" not in content

    def test_modify_implements_multiple_values(self, tmp_path: Path):
        """Test changing implements to multiple values."""
        from elspais.commands.edit import modify_implements

        spec_file = tmp_path / "dev-core.md"
        spec_file.write_text("""
# REQ-d00001: Test Requirement

**Level**: DEV | **Status**: Active | **Implements**: p00001

Body text here.

*End* *Test Requirement* | **Hash**: test1234
---
""")

        result = modify_implements(spec_file, "REQ-d00001", ["p00002", "p00003"])

        assert result["success"] is True
        content = spec_file.read_text()
        assert "**Implements**: p00002, p00003" in content

    def test_modify_implements_to_none(self, tmp_path: Path):
        """Test clearing implements (set to dash)."""
        from elspais.commands.edit import modify_implements

        spec_file = tmp_path / "dev-core.md"
        spec_file.write_text("""
# REQ-d00001: Test Requirement

**Level**: DEV | **Status**: Active | **Implements**: p00001

Body text here.

*End* *Test Requirement* | **Hash**: test1234
---
""")

        result = modify_implements(spec_file, "REQ-d00001", [])

        assert result["success"] is True
        content = spec_file.read_text()
        assert "**Implements**: -" in content

    def test_modify_implements_dry_run(self, tmp_path: Path):
        """Test dry run doesn't modify file."""
        from elspais.commands.edit import modify_implements

        spec_file = tmp_path / "dev-core.md"
        original = """
# REQ-d00001: Test Requirement

**Level**: DEV | **Status**: Active | **Implements**: p00001

Body text here.

*End* *Test Requirement* | **Hash**: test1234
---
"""
        spec_file.write_text(original)

        result = modify_implements(spec_file, "REQ-d00001", ["p00002"], dry_run=True)

        assert result["success"] is True
        assert result["dry_run"] is True
        # File should be unchanged
        assert spec_file.read_text() == original

    def test_modify_implements_req_not_found(self, tmp_path: Path):
        """Test error when requirement not found."""
        from elspais.commands.edit import modify_implements

        spec_file = tmp_path / "dev-core.md"
        spec_file.write_text("""
# REQ-d00001: Test Requirement

**Level**: DEV | **Status**: Active | **Implements**: p00001

Body text here.

*End* *Test Requirement* | **Hash**: test1234
---
""")

        result = modify_implements(spec_file, "REQ-d00099", ["p00002"])

        assert result["success"] is False
        assert "not found" in result["error"].lower()


class TestModifyStatus:
    """Tests for modifying the Status field."""

    def test_modify_status(self, tmp_path: Path):
        """Test changing status."""
        from elspais.commands.edit import modify_status

        spec_file = tmp_path / "dev-core.md"
        spec_file.write_text("""
# REQ-d00001: Test Requirement

**Level**: DEV | **Status**: Draft | **Implements**: p00001

Body text here.

*End* *Test Requirement* | **Hash**: test1234
---
""")

        result = modify_status(spec_file, "REQ-d00001", "Active")

        assert result["success"] is True
        assert result["old_status"] == "Draft"
        assert result["new_status"] == "Active"

        content = spec_file.read_text()
        assert "**Status**: Active" in content
        assert "**Status**: Draft" not in content

    def test_modify_status_dry_run(self, tmp_path: Path):
        """Test dry run doesn't modify file."""
        from elspais.commands.edit import modify_status

        spec_file = tmp_path / "dev-core.md"
        original = """
# REQ-d00001: Test Requirement

**Level**: DEV | **Status**: Draft | **Implements**: p00001

Body text here.

*End* *Test Requirement* | **Hash**: test1234
---
"""
        spec_file.write_text(original)

        result = modify_status(spec_file, "REQ-d00001", "Active", dry_run=True)

        assert result["success"] is True
        assert spec_file.read_text() == original


class TestModifyImplementsEdgeCases:
    """Edge case tests for modify_implements."""

    def test_modify_implements_field_missing(self, tmp_path: Path):
        """Test error when Implements field is missing."""
        from elspais.commands.edit import modify_implements

        spec_file = tmp_path / "dev-core.md"
        spec_file.write_text("""
# REQ-d00001: No Implements Field

**Level**: DEV | **Status**: Active

Body text here.

*End* *No Implements Field* | **Hash**: test1234
---
""")

        result = modify_implements(spec_file, "REQ-d00001", ["p00002"])

        assert result["success"] is False
        assert "Implements" in result["error"]


class TestModifyStatusEdgeCases:
    """Edge case tests for modify_status."""

    def test_modify_status_field_missing(self, tmp_path: Path):
        """Test error when Status field is missing."""
        from elspais.commands.edit import modify_status

        spec_file = tmp_path / "dev-core.md"
        spec_file.write_text("""
# REQ-d00001: No Status Field

**Level**: DEV | **Implements**: p00001

Body text here.

*End* *No Status Field* | **Hash**: test1234
---
""")

        result = modify_status(spec_file, "REQ-d00001", "Active")

        assert result["success"] is False
        assert "Status" in result["error"]


class TestMoveRequirement:
    """Tests for moving requirements between files."""

    def test_move_requirement(self, tmp_path: Path):
        """Test moving a requirement to another file."""
        from elspais.commands.edit import move_requirement

        source_file = tmp_path / "dev-core.md"
        source_file.write_text("""
# REQ-d00001: First Requirement

**Level**: DEV | **Status**: Active | **Implements**: p00001

First body.

*End* *First Requirement* | **Hash**: test1234
---

# REQ-d00002: Second Requirement

**Level**: DEV | **Status**: Active | **Implements**: p00001

Second body.

*End* *Second Requirement* | **Hash**: test5678
---
""")

        dest_file = tmp_path / "dev-features.md"
        dest_file.write_text("""
# REQ-d00010: Existing Requirement

**Level**: DEV | **Status**: Active | **Implements**: p00002

Existing body.

*End* *Existing Requirement* | **Hash**: existabc
---
""")

        result = move_requirement(source_file, dest_file, "REQ-d00001")

        assert result["success"] is True

        # Check source file no longer has the requirement
        source_content = source_file.read_text()
        assert "REQ-d00001" not in source_content
        assert "REQ-d00002" in source_content

        # Check destination file has the requirement
        dest_content = dest_file.read_text()
        assert "REQ-d00001" in dest_content
        assert "First body" in dest_content
        assert "REQ-d00010" in dest_content

    def test_move_requirement_dry_run(self, tmp_path: Path):
        """Test dry run doesn't modify files."""
        from elspais.commands.edit import move_requirement

        source_file = tmp_path / "dev-core.md"
        source_original = """
# REQ-d00001: Test Requirement

**Level**: DEV | **Status**: Active | **Implements**: p00001

Body text.

*End* *Test Requirement* | **Hash**: test1234
---
"""
        source_file.write_text(source_original)

        dest_file = tmp_path / "dev-features.md"
        dest_original = ""
        dest_file.write_text(dest_original)

        result = move_requirement(source_file, dest_file, "REQ-d00001", dry_run=True)

        assert result["success"] is True
        assert result["dry_run"] is True
        assert source_file.read_text() == source_original
        assert dest_file.read_text() == dest_original

    def test_move_requirement_creates_dest_file(self, tmp_path: Path):
        """Test move creates destination file if it doesn't exist."""
        from elspais.commands.edit import move_requirement

        source_file = tmp_path / "dev-core.md"
        source_file.write_text("""
# REQ-d00001: Test Requirement

**Level**: DEV | **Status**: Active | **Implements**: p00001

Body text.

*End* *Test Requirement* | **Hash**: test1234
---
""")

        dest_file = tmp_path / "new-file.md"
        assert not dest_file.exists()

        result = move_requirement(source_file, dest_file, "REQ-d00001")

        assert result["success"] is True
        assert dest_file.exists()
        assert "REQ-d00001" in dest_file.read_text()

    def test_move_requirement_source_becomes_empty(self, tmp_path: Path):
        """Test move when source file becomes empty after move."""
        from elspais.commands.edit import move_requirement

        source_file = tmp_path / "dev-core.md"
        source_file.write_text("""
# REQ-d00001: Only Requirement

**Level**: DEV | **Status**: Active | **Implements**: p00001

Body text.

*End* *Only Requirement* | **Hash**: test1234
---
""")

        dest_file = tmp_path / "dev-features.md"
        dest_file.write_text("")

        result = move_requirement(source_file, dest_file, "REQ-d00001")

        assert result["success"] is True
        assert result.get("source_empty") is True
        # Source should be effectively empty
        assert source_file.read_text().strip() == ""

    def test_move_requirement_not_found(self, tmp_path: Path):
        """Test error when requirement not found in source."""
        from elspais.commands.edit import move_requirement

        source_file = tmp_path / "dev-core.md"
        source_file.write_text("""
# REQ-d00001: Existing Requirement

**Level**: DEV | **Status**: Active | **Implements**: p00001

Body text.

*End* *Existing Requirement* | **Hash**: test1234
---
""")

        dest_file = tmp_path / "dev-features.md"
        dest_file.write_text("")

        result = move_requirement(source_file, dest_file, "REQ-d00099")

        assert result["success"] is False
        assert "not found" in result["error"].lower()


class TestFindRequirementInFiles:
    """Tests for finding requirements across files."""

    def test_find_requirement_in_files(self, tmp_path: Path):
        """Test finding a requirement in spec files."""
        from elspais.commands.edit import find_requirement_in_files

        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        (spec_dir / "prd-core.md").write_text("""
# REQ-p00001: PRD Requirement

**Level**: PRD | **Status**: Active

PRD body.

*End* *PRD Requirement* | **Hash**: prd12345
---
""")

        (spec_dir / "dev-core.md").write_text("""
# REQ-d00001: DEV Requirement

**Level**: DEV | **Status**: Active | **Implements**: p00001

DEV body.

*End* *DEV Requirement* | **Hash**: dev12345
---
""")

        result = find_requirement_in_files(spec_dir, "REQ-d00001")

        assert result is not None
        assert result["file_path"] == spec_dir / "dev-core.md"
        assert result["req_id"] == "REQ-d00001"

    def test_find_requirement_not_found(self, tmp_path: Path):
        """Test when requirement doesn't exist."""
        from elspais.commands.edit import find_requirement_in_files

        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        (spec_dir / "dev-core.md").write_text("""
# REQ-d00001: DEV Requirement

**Level**: DEV | **Status**: Active | **Implements**: p00001

DEV body.

*End* *DEV Requirement* | **Hash**: dev12345
---
""")

        result = find_requirement_in_files(spec_dir, "REQ-d00099")

        assert result is None


class TestValidateImplementsReferences:
    """Tests for validating implements references."""

    def test_batch_edit_validates_implements_refs(self, tmp_path: Path):
        """Test that batch edit can validate implements references exist."""
        from elspais.commands.edit import batch_edit

        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        (spec_dir / "prd-core.md").write_text("""
# REQ-p00001: PRD Requirement

**Level**: PRD | **Status**: Active | **Implements**: -

PRD body.

*End* *PRD Requirement* | **Hash**: prd12345
---
""")

        (spec_dir / "dev-core.md").write_text("""
# REQ-d00001: DEV Requirement

**Level**: DEV | **Status**: Active | **Implements**: p00001

DEV body.

*End* *DEV Requirement* | **Hash**: dev12345
---
""")

        # Valid reference - should succeed
        changes_valid = [
            {"req_id": "REQ-d00001", "implements": ["p00001"]},
        ]
        results = batch_edit(spec_dir, changes_valid, validate_refs=True)
        assert results[0]["success"] is True

        # Invalid reference - should fail when validate_refs=True
        changes_invalid = [
            {"req_id": "REQ-d00001", "implements": ["p99999"]},
        ]
        results = batch_edit(spec_dir, changes_invalid, validate_refs=True)
        assert results[0]["success"] is False
        assert "invalid" in results[0]["error"].lower() or "not found" in results[0]["error"].lower()

    def test_batch_edit_no_validation_by_default(self, tmp_path: Path):
        """Test that batch edit doesn't validate by default."""
        from elspais.commands.edit import batch_edit

        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        (spec_dir / "dev-core.md").write_text("""
# REQ-d00001: DEV Requirement

**Level**: DEV | **Status**: Active | **Implements**: p00001

DEV body.

*End* *DEV Requirement* | **Hash**: dev12345
---
""")

        # Invalid reference - should succeed when validate_refs=False (default)
        changes = [
            {"req_id": "REQ-d00001", "implements": ["p99999"]},
        ]
        results = batch_edit(spec_dir, changes)  # validate_refs defaults to False
        assert results[0]["success"] is True


class TestBatchEdit:
    """Tests for batch editing from JSON."""

    def test_batch_edit_from_json(self, tmp_path: Path):
        """Test batch editing multiple requirements."""
        from elspais.commands.edit import batch_edit

        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        (spec_dir / "dev-core.md").write_text("""
# REQ-d00001: First Requirement

**Level**: DEV | **Status**: Draft | **Implements**: p00001

First body.

*End* *First Requirement* | **Hash**: test1234
---

# REQ-d00002: Second Requirement

**Level**: DEV | **Status**: Draft | **Implements**: p00001

Second body.

*End* *Second Requirement* | **Hash**: test5678
---
""")

        changes = [
            {"req_id": "REQ-d00001", "implements": ["p00002"]},
            {"req_id": "REQ-d00002", "status": "Active"},
        ]

        results = batch_edit(spec_dir, changes)

        assert len(results) == 2
        assert all(r["success"] for r in results)

        content = (spec_dir / "dev-core.md").read_text()
        assert "**Implements**: p00002" in content
        assert "**Status**: Active" in content

    def test_batch_edit_with_move(self, tmp_path: Path):
        """Test batch edit including move operation."""
        from elspais.commands.edit import batch_edit

        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        (spec_dir / "dev-core.md").write_text("""
# REQ-d00001: Movable Requirement

**Level**: DEV | **Status**: Active | **Implements**: p00001

Body text.

*End* *Movable Requirement* | **Hash**: test1234
---
""")

        (spec_dir / "dev-features.md").write_text("")

        changes = [
            {"req_id": "REQ-d00001", "move_to": "dev-features.md"},
        ]

        results = batch_edit(spec_dir, changes)

        assert len(results) == 1
        assert results[0]["success"] is True

        # Verify move happened
        assert "REQ-d00001" not in (spec_dir / "dev-core.md").read_text()
        assert "REQ-d00001" in (spec_dir / "dev-features.md").read_text()

    def test_batch_edit_dry_run(self, tmp_path: Path):
        """Test batch edit dry run."""
        from elspais.commands.edit import batch_edit

        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        original = """
# REQ-d00001: Test Requirement

**Level**: DEV | **Status**: Draft | **Implements**: p00001

Body text.

*End* *Test Requirement* | **Hash**: test1234
---
"""
        (spec_dir / "dev-core.md").write_text(original)

        changes = [
            {"req_id": "REQ-d00001", "status": "Active"},
        ]

        results = batch_edit(spec_dir, changes, dry_run=True)

        assert len(results) == 1
        assert results[0]["success"] is True
        assert results[0]["dry_run"] is True
        # File unchanged
        assert (spec_dir / "dev-core.md").read_text() == original
