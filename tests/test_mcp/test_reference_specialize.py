"""
Tests for reference specialization in elspais.mcp.mutator.

Tests the specialize_reference() method that converts REQ→REQ references
to REQ→Assertion references using multi-assertion syntax.
"""

import pytest
from pathlib import Path

from elspais.mcp.mutator import GraphMutator, ReferenceSpecialization


class TestBuildMultiAssertionRef:
    """Tests for the _build_multi_assertion_ref helper."""

    def test_single_assertion(self, tmp_path):
        """Test building reference with single assertion."""
        mutator = GraphMutator(tmp_path)
        result = mutator._build_multi_assertion_ref("REQ-p00001", ["A"])
        assert result == "REQ-p00001-A"

    def test_multiple_assertions(self, tmp_path):
        """Test building reference with multiple assertions."""
        mutator = GraphMutator(tmp_path)
        result = mutator._build_multi_assertion_ref("REQ-p00001", ["A", "B", "C"])
        assert result == "REQ-p00001-A-B-C"

    def test_empty_assertions(self, tmp_path):
        """Test building reference with no assertions returns original."""
        mutator = GraphMutator(tmp_path)
        result = mutator._build_multi_assertion_ref("REQ-p00001", [])
        assert result == "REQ-p00001"

    def test_numeric_assertions(self, tmp_path):
        """Test building reference with numeric assertions."""
        mutator = GraphMutator(tmp_path)
        result = mutator._build_multi_assertion_ref("REQ-p00001", ["01", "02"])
        assert result == "REQ-p00001-01-02"


class TestSpecializeReference:
    """Tests for specialize_reference method."""

    def create_spec_file(self, path: Path, content: str) -> Path:
        """Helper to create a spec file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def test_specialize_implements_single_assertion(self, tmp_path):
        """Test specializing Implements reference to single assertion."""
        spec_file = tmp_path / "spec" / "dev.md"
        self.create_spec_file(
            spec_file,
            """# REQ-d00001: Dev Requirement

**Level**: Dev | **Status**: Active | **Implements**: REQ-p00001

## Assertions

A. The system SHALL do something.

*End* *Dev Requirement* | **Hash**: abcd1234
""",
        )

        mutator = GraphMutator(tmp_path)
        result = mutator.specialize_reference(
            source_id="REQ-d00001",
            target_id="REQ-p00001",
            assertions=["A"],
            file_path=spec_file,
        )

        assert result.success
        assert result.old_reference == "REQ-p00001"
        assert result.new_reference == "REQ-p00001-A"

        # Verify file was updated
        content = spec_file.read_text()
        assert "**Implements**: REQ-p00001-A" in content
        assert "**Implements**: REQ-p00001" not in content.replace("REQ-p00001-A", "")

    def test_specialize_implements_multiple_assertions(self, tmp_path):
        """Test specializing Implements reference to multiple assertions."""
        spec_file = tmp_path / "spec" / "dev.md"
        self.create_spec_file(
            spec_file,
            """# REQ-d00001: Dev Requirement

**Level**: Dev | **Status**: Active | **Implements**: REQ-p00001

## Assertions

A. The system SHALL do something.

*End* *Dev Requirement* | **Hash**: abcd1234
""",
        )

        mutator = GraphMutator(tmp_path)
        result = mutator.specialize_reference(
            source_id="REQ-d00001",
            target_id="REQ-p00001",
            assertions=["A", "B", "C"],
            file_path=spec_file,
        )

        assert result.success
        assert result.new_reference == "REQ-p00001-A-B-C"

        content = spec_file.read_text()
        assert "**Implements**: REQ-p00001-A-B-C" in content

    def test_specialize_refines_reference(self, tmp_path):
        """Test specializing Refines reference."""
        spec_file = tmp_path / "spec" / "dev.md"
        self.create_spec_file(
            spec_file,
            """# REQ-d00001: Dev Requirement

**Level**: Dev | **Status**: Active | **Refines**: REQ-p00001

## Assertions

A. The system SHALL do something.

*End* *Dev Requirement* | **Hash**: abcd1234
""",
        )

        mutator = GraphMutator(tmp_path)
        result = mutator.specialize_reference(
            source_id="REQ-d00001",
            target_id="REQ-p00001",
            assertions=["B"],
            file_path=spec_file,
        )

        assert result.success
        assert result.new_reference == "REQ-p00001-B"

        content = spec_file.read_text()
        assert "**Refines**: REQ-p00001-B" in content

    def test_specialize_preserves_other_references(self, tmp_path):
        """Test that specialization preserves other references."""
        spec_file = tmp_path / "spec" / "dev.md"
        self.create_spec_file(
            spec_file,
            """# REQ-d00001: Dev Requirement

**Level**: Dev | **Status**: Active | **Implements**: REQ-p00001, REQ-p00002

## Assertions

A. The system SHALL do something.

*End* *Dev Requirement* | **Hash**: abcd1234
""",
        )

        mutator = GraphMutator(tmp_path)
        result = mutator.specialize_reference(
            source_id="REQ-d00001",
            target_id="REQ-p00001",
            assertions=["A"],
            file_path=spec_file,
        )

        assert result.success

        content = spec_file.read_text()
        assert "REQ-p00001-A" in content
        assert "REQ-p00002" in content

    def test_specialize_not_found_source(self, tmp_path):
        """Test error when source requirement not found."""
        spec_file = tmp_path / "spec" / "dev.md"
        self.create_spec_file(
            spec_file,
            """# REQ-d00001: Dev Requirement

**Level**: Dev | **Status**: Active | **Implements**: REQ-p00001

*End* *Dev Requirement* | **Hash**: abcd1234
""",
        )

        mutator = GraphMutator(tmp_path)
        result = mutator.specialize_reference(
            source_id="REQ-d99999",
            target_id="REQ-p00001",
            assertions=["A"],
            file_path=spec_file,
        )

        assert not result.success
        assert "not found" in result.message.lower()

    def test_specialize_not_found_target(self, tmp_path):
        """Test error when target reference not found."""
        spec_file = tmp_path / "spec" / "dev.md"
        self.create_spec_file(
            spec_file,
            """# REQ-d00001: Dev Requirement

**Level**: Dev | **Status**: Active | **Implements**: REQ-p00001

*End* *Dev Requirement* | **Hash**: abcd1234
""",
        )

        mutator = GraphMutator(tmp_path)
        result = mutator.specialize_reference(
            source_id="REQ-d00001",
            target_id="REQ-p99999",  # Not in the file
            assertions=["A"],
            file_path=spec_file,
        )

        assert not result.success
        assert "not found" in result.message.lower()

    def test_specialize_empty_assertions(self, tmp_path):
        """Test error when no assertions specified."""
        spec_file = tmp_path / "spec" / "dev.md"
        self.create_spec_file(
            spec_file,
            """# REQ-d00001: Dev Requirement

**Level**: Dev | **Status**: Active | **Implements**: REQ-p00001

*End* *Dev Requirement* | **Hash**: abcd1234
""",
        )

        mutator = GraphMutator(tmp_path)
        result = mutator.specialize_reference(
            source_id="REQ-d00001",
            target_id="REQ-p00001",
            assertions=[],
            file_path=spec_file,
        )

        assert not result.success
        assert "no assertions" in result.message.lower()

    def test_specialize_invalid_assertion_label(self, tmp_path):
        """Test error for invalid assertion labels."""
        spec_file = tmp_path / "spec" / "dev.md"
        self.create_spec_file(
            spec_file,
            """# REQ-d00001: Dev Requirement

**Level**: Dev | **Status**: Active | **Implements**: REQ-p00001

*End* *Dev Requirement* | **Hash**: abcd1234
""",
        )

        mutator = GraphMutator(tmp_path)
        result = mutator.specialize_reference(
            source_id="REQ-d00001",
            target_id="REQ-p00001",
            assertions=["invalid"],  # Should be single uppercase letter or 1-2 digits
            file_path=spec_file,
        )

        assert not result.success
        assert "invalid assertion label" in result.message.lower()

    def test_specialize_file_not_found(self, tmp_path):
        """Test error when file doesn't exist."""
        mutator = GraphMutator(tmp_path)
        result = mutator.specialize_reference(
            source_id="REQ-d00001",
            target_id="REQ-p00001",
            assertions=["A"],
            file_path=tmp_path / "nonexistent.md",
        )

        assert not result.success
        assert "not found" in result.message.lower()

    def test_specialize_numeric_assertions(self, tmp_path):
        """Test specialization with numeric assertion labels."""
        spec_file = tmp_path / "spec" / "dev.md"
        self.create_spec_file(
            spec_file,
            """# REQ-d00001: Dev Requirement

**Level**: Dev | **Status**: Active | **Implements**: REQ-p00001

## Assertions

01. The system SHALL do something.

*End* *Dev Requirement* | **Hash**: abcd1234
""",
        )

        mutator = GraphMutator(tmp_path)
        result = mutator.specialize_reference(
            source_id="REQ-d00001",
            target_id="REQ-p00001",
            assertions=["01", "02"],
            file_path=spec_file,
        )

        assert result.success
        assert result.new_reference == "REQ-p00001-01-02"


class TestSpecializeReferenceResult:
    """Tests for ReferenceSpecialization dataclass."""

    def test_success_result(self):
        """Test creating a success result."""
        result = ReferenceSpecialization(
            success=True,
            source_id="REQ-d00001",
            target_id="REQ-p00001",
            assertions=["A", "B"],
            old_reference="REQ-p00001",
            new_reference="REQ-p00001-A-B",
            file_path=Path("/test/spec.md"),
            message="Specialized successfully",
        )

        assert result.success
        assert result.assertions == ["A", "B"]
        assert result.old_reference == "REQ-p00001"
        assert result.new_reference == "REQ-p00001-A-B"

    def test_failure_result(self):
        """Test creating a failure result."""
        result = ReferenceSpecialization(
            success=False,
            source_id="REQ-d00001",
            target_id="REQ-p00001",
            assertions=["A"],
            old_reference="REQ-p00001",
            new_reference="",
            file_path=None,
            message="Error occurred",
        )

        assert not result.success
        assert result.new_reference == ""
