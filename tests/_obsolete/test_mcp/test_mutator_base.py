"""
Tests for elspais.mcp.mutator module - SpecFileMutator base functionality.
"""

import pytest
from pathlib import Path

from elspais.mcp.mutator import SpecFileMutator, FileContent, RequirementLocation


class TestSpecFileMutatorInit:
    """Tests for SpecFileMutator initialization."""

    def test_init_with_working_dir(self, tmp_path):
        """Test creating mutator with working directory."""
        mutator = SpecFileMutator(tmp_path)

        assert mutator.working_dir == tmp_path
        assert mutator.pattern_config is not None
        assert mutator.validator is not None

    def test_init_with_pattern_config(self, tmp_path):
        """Test creating mutator with custom pattern config."""
        from elspais.core.patterns import PatternConfig

        config = PatternConfig.from_dict({"prefix": "TST"})
        mutator = SpecFileMutator(tmp_path, pattern_config=config)

        assert mutator.pattern_config.prefix == "TST"


class TestReadSpecFile:
    """Tests for _read_spec_file method."""

    def test_read_existing_file(self, tmp_path):
        """Test reading an existing spec file."""
        spec_file = tmp_path / "spec" / "test.md"
        spec_file.parent.mkdir(parents=True, exist_ok=True)
        spec_file.write_text("# REQ-p00001: Test\n\nBody content\n")

        mutator = SpecFileMutator(tmp_path)
        content = mutator._read_spec_file(spec_file)

        assert isinstance(content, FileContent)
        assert content.path == spec_file
        assert "REQ-p00001" in content.text
        assert len(content.lines) == 4

    def test_read_file_relative_path(self, tmp_path):
        """Test reading with relative path."""
        spec_file = tmp_path / "spec" / "test.md"
        spec_file.parent.mkdir(parents=True, exist_ok=True)
        spec_file.write_text("# REQ-p00001: Test\n")

        mutator = SpecFileMutator(tmp_path)
        content = mutator._read_spec_file(Path("spec/test.md"))

        assert content.path == spec_file

    def test_read_nonexistent_file(self, tmp_path):
        """Test reading a non-existent file raises error."""
        mutator = SpecFileMutator(tmp_path)

        with pytest.raises(FileNotFoundError):
            mutator._read_spec_file(tmp_path / "nonexistent.md")

    def test_read_file_outside_workspace(self, tmp_path):
        """Test reading file outside workspace raises error."""
        other_dir = tmp_path.parent / "other"
        other_dir.mkdir(parents=True, exist_ok=True)
        other_file = other_dir / "test.md"
        other_file.write_text("content")

        mutator = SpecFileMutator(tmp_path)

        with pytest.raises(ValueError, match="outside workspace"):
            mutator._read_spec_file(other_file)

    def test_read_file_preserves_empty_lines(self, tmp_path):
        """Test that empty lines are preserved in lines list."""
        spec_file = tmp_path / "test.md"
        spec_file.write_text("Line 1\n\nLine 3\n")

        mutator = SpecFileMutator(tmp_path)
        content = mutator._read_spec_file(spec_file)

        assert content.lines == ["Line 1", "", "Line 3", ""]


class TestWriteSpecFile:
    """Tests for _write_spec_file method."""

    def test_write_new_file(self, tmp_path):
        """Test writing a new spec file."""
        spec_file = tmp_path / "spec" / "new.md"

        mutator = SpecFileMutator(tmp_path)
        mutator._write_spec_file(spec_file, "# REQ-p00001: New Requirement\n")

        assert spec_file.exists()
        assert spec_file.read_text() == "# REQ-p00001: New Requirement\n"

    def test_write_creates_parent_dirs(self, tmp_path):
        """Test that writing creates parent directories."""
        spec_file = tmp_path / "spec" / "subdir" / "deep" / "test.md"

        mutator = SpecFileMutator(tmp_path)
        mutator._write_spec_file(spec_file, "content")

        assert spec_file.exists()

    def test_write_overwrites_existing(self, tmp_path):
        """Test that writing overwrites existing content."""
        spec_file = tmp_path / "test.md"
        spec_file.write_text("old content")

        mutator = SpecFileMutator(tmp_path)
        mutator._write_spec_file(spec_file, "new content")

        assert spec_file.read_text() == "new content"

    def test_write_file_outside_workspace(self, tmp_path):
        """Test writing file outside workspace raises error."""
        other_file = tmp_path.parent / "other.md"

        mutator = SpecFileMutator(tmp_path)

        with pytest.raises(ValueError, match="outside workspace"):
            mutator._write_spec_file(other_file, "content")

    def test_write_relative_path(self, tmp_path):
        """Test writing with relative path."""
        mutator = SpecFileMutator(tmp_path)
        mutator._write_spec_file(Path("spec/test.md"), "content")

        assert (tmp_path / "spec" / "test.md").read_text() == "content"

    def test_write_preserves_encoding(self, tmp_path):
        """Test that UTF-8 encoding is preserved."""
        spec_file = tmp_path / "test.md"
        content = "# REQ-p00001: Unicode Test 日本語\n"

        mutator = SpecFileMutator(tmp_path)
        mutator._write_spec_file(spec_file, content)

        assert spec_file.read_text(encoding="utf-8") == content


class TestFindRequirementLines:
    """Tests for _find_requirement_lines method."""

    def test_find_single_requirement(self, tmp_path):
        """Test finding a single requirement in file."""
        content = """# REQ-p00001: Test Requirement

**Level**: Prd | **Status**: Active

## Assertions

A. The system SHALL do something.

*End* *Test Requirement* | **Hash**: a1b2c3d4
---
"""
        spec_file = tmp_path / "test.md"
        spec_file.write_text(content)

        mutator = SpecFileMutator(tmp_path)
        file_content = mutator._read_spec_file(spec_file)
        location = mutator._find_requirement_lines(file_content, "REQ-p00001")

        assert location is not None
        assert location.start_line == 1
        assert location.end_line == 10  # Includes separator (line 10), not trailing empty line
        assert location.has_end_marker is True
        assert location.has_separator is True
        assert "REQ-p00001" in location.header_line

    def test_find_requirement_without_end_marker(self, tmp_path):
        """Test finding requirement without end marker."""
        content = """# REQ-p00001: Test Requirement

**Level**: Prd | **Status**: Active

Body text only.

# REQ-p00002: Next Requirement

**Level**: Prd | **Status**: Active
"""
        spec_file = tmp_path / "test.md"
        spec_file.write_text(content)

        mutator = SpecFileMutator(tmp_path)
        file_content = mutator._read_spec_file(spec_file)
        location = mutator._find_requirement_lines(file_content, "REQ-p00001")

        assert location is not None
        assert location.start_line == 1
        assert location.end_line == 6  # Lines before next requirement (excludes next header)
        assert location.has_end_marker is False
        assert location.has_separator is False

    def test_find_second_requirement(self, tmp_path):
        """Test finding second requirement in file."""
        content = """# REQ-p00001: First Requirement

**Level**: Prd | **Status**: Active

*End* *First Requirement* | **Hash**: a1b2c3d4
---

# REQ-p00002: Second Requirement

**Level**: Prd | **Status**: Active

*End* *Second Requirement* | **Hash**: b2c3d4e5
---
"""
        spec_file = tmp_path / "test.md"
        spec_file.write_text(content)

        mutator = SpecFileMutator(tmp_path)
        file_content = mutator._read_spec_file(spec_file)
        location = mutator._find_requirement_lines(file_content, "REQ-p00002")

        assert location is not None
        assert location.start_line == 8
        assert "REQ-p00002" in location.header_line
        assert location.has_end_marker is True

    def test_find_nonexistent_requirement(self, tmp_path):
        """Test finding non-existent requirement returns None."""
        content = """# REQ-p00001: Only Requirement

**Level**: Prd | **Status**: Active
"""
        spec_file = tmp_path / "test.md"
        spec_file.write_text(content)

        mutator = SpecFileMutator(tmp_path)
        file_content = mutator._read_spec_file(spec_file)
        location = mutator._find_requirement_lines(file_content, "REQ-p99999")

        assert location is None

    def test_find_requirement_at_end_of_file(self, tmp_path):
        """Test finding requirement at end of file without trailing newline."""
        content = """# REQ-p00001: Test Requirement

**Level**: Prd | **Status**: Active

Body content."""
        spec_file = tmp_path / "test.md"
        spec_file.write_text(content)

        mutator = SpecFileMutator(tmp_path)
        file_content = mutator._read_spec_file(spec_file)
        location = mutator._find_requirement_lines(file_content, "REQ-p00001")

        assert location is not None
        assert location.start_line == 1
        assert location.has_end_marker is False

    def test_find_requirement_with_assertions(self, tmp_path):
        """Test finding requirement with assertions section."""
        content = """# REQ-d00001: Implementation

**Level**: Dev | **Status**: Active | **Implements**: REQ-p00001

## Assertions

A. The implementation SHALL use bcrypt.
B. The implementation SHALL NOT store plaintext.
C. Removed - was duplicate.

## Rationale

Security best practices.

*End* *Implementation* | **Hash**: c3d4e5f6
---
"""
        spec_file = tmp_path / "test.md"
        spec_file.write_text(content)

        mutator = SpecFileMutator(tmp_path)
        file_content = mutator._read_spec_file(spec_file)
        location = mutator._find_requirement_lines(file_content, "REQ-d00001")

        assert location is not None
        assert location.start_line == 1
        assert location.has_end_marker is True


class TestGetRequirementText:
    """Tests for get_requirement_text method."""

    def test_get_full_requirement_text(self, tmp_path):
        """Test extracting full requirement text."""
        content = """# REQ-p00001: Test Requirement

**Level**: Prd | **Status**: Active

## Assertions

A. The system SHALL do something.

*End* *Test Requirement* | **Hash**: a1b2c3d4
---
"""
        spec_file = tmp_path / "test.md"
        spec_file.write_text(content)

        mutator = SpecFileMutator(tmp_path)
        file_content = mutator._read_spec_file(spec_file)
        location = mutator._find_requirement_lines(file_content, "REQ-p00001")
        text = mutator.get_requirement_text(file_content, location)

        assert "# REQ-p00001: Test Requirement" in text
        assert "**Level**: Prd" in text
        assert "A. The system SHALL do something." in text
        assert "*End* *Test Requirement*" in text
        assert "---" in text

    def test_get_requirement_between_others(self, tmp_path):
        """Test extracting requirement from middle of file."""
        content = """# REQ-p00001: First

**Level**: Prd | **Status**: Active

*End* *First* | **Hash**: a1b2c3d4
---

# REQ-p00002: Second

**Level**: Prd | **Status**: Active

*End* *Second* | **Hash**: b2c3d4e5
---

# REQ-p00003: Third

**Level**: Prd | **Status**: Active

*End* *Third* | **Hash**: c3d4e5f6
---
"""
        spec_file = tmp_path / "test.md"
        spec_file.write_text(content)

        mutator = SpecFileMutator(tmp_path)
        file_content = mutator._read_spec_file(spec_file)
        location = mutator._find_requirement_lines(file_content, "REQ-p00002")
        text = mutator.get_requirement_text(file_content, location)

        assert "# REQ-p00002: Second" in text
        assert "# REQ-p00001" not in text
        assert "# REQ-p00003" not in text


class TestReplaceRequirementText:
    """Tests for replace_requirement_text method."""

    def test_replace_requirement_content(self, tmp_path):
        """Test replacing requirement text in file."""
        original = """# REQ-p00001: Original Title

**Level**: Prd | **Status**: Active

Original body.

*End* *Original Title* | **Hash**: a1b2c3d4
---
"""
        spec_file = tmp_path / "test.md"
        spec_file.write_text(original)

        mutator = SpecFileMutator(tmp_path)
        file_content = mutator._read_spec_file(spec_file)
        location = mutator._find_requirement_lines(file_content, "REQ-p00001")

        new_req = """# REQ-p00001: Updated Title

**Level**: Prd | **Status**: Active

Updated body.

*End* *Updated Title* | **Hash**: newha5h1
---"""

        new_content = mutator.replace_requirement_text(file_content, location, new_req)

        assert "# REQ-p00001: Updated Title" in new_content
        assert "Updated body." in new_content
        assert "Original Title" not in new_content

    def test_replace_preserves_surrounding_content(self, tmp_path):
        """Test that replacement preserves content before and after."""
        original = """# Header comment

Some preamble text.

# REQ-p00001: Middle Requirement

**Level**: Prd | **Status**: Active

*End* *Middle Requirement* | **Hash**: a1b2c3d4
---

# REQ-p00002: After Requirement

**Level**: Prd | **Status**: Active

*End* *After Requirement* | **Hash**: b2c3d4e5
---

Footer content.
"""
        spec_file = tmp_path / "test.md"
        spec_file.write_text(original)

        mutator = SpecFileMutator(tmp_path)
        file_content = mutator._read_spec_file(spec_file)
        location = mutator._find_requirement_lines(file_content, "REQ-p00001")

        new_req = """# REQ-p00001: Replaced

**Level**: Prd | **Status**: Active

*End* *Replaced* | **Hash**: newha5h1
---"""

        new_content = mutator.replace_requirement_text(file_content, location, new_req)

        # Preamble preserved
        assert "# Header comment" in new_content
        assert "Some preamble text." in new_content

        # Replacement applied
        assert "# REQ-p00001: Replaced" in new_content
        assert "Middle Requirement" not in new_content

        # Following content preserved
        assert "# REQ-p00002: After Requirement" in new_content
        assert "Footer content." in new_content

    def test_replace_changes_line_count(self, tmp_path):
        """Test replacement can change line count."""
        original = """# REQ-p00001: Short

**Level**: Prd | **Status**: Active

*End* *Short* | **Hash**: a1b2c3d4
---
"""
        spec_file = tmp_path / "test.md"
        spec_file.write_text(original)

        mutator = SpecFileMutator(tmp_path)
        file_content = mutator._read_spec_file(spec_file)
        location = mutator._find_requirement_lines(file_content, "REQ-p00001")

        new_req = """# REQ-p00001: Longer

**Level**: Prd | **Status**: Active

## Assertions

A. New assertion one.
B. New assertion two.
C. New assertion three.

## Rationale

Added more content.

*End* *Longer* | **Hash**: newha5h1
---"""

        new_content = mutator.replace_requirement_text(file_content, location, new_req)

        assert len(new_content.split("\n")) > len(original.split("\n"))
        assert "A. New assertion one." in new_content


class TestIntegration:
    """Integration tests for mutator workflow."""

    def test_read_modify_write_roundtrip(self, tmp_path):
        """Test complete read-modify-write workflow."""
        original = """# REQ-p00001: Test Requirement

**Level**: Prd | **Status**: Active

## Assertions

A. The system SHALL do something.

*End* *Test Requirement* | **Hash**: a1b2c3d4
---
"""
        spec_file = tmp_path / "spec" / "test.md"
        spec_file.parent.mkdir(parents=True, exist_ok=True)
        spec_file.write_text(original)

        mutator = SpecFileMutator(tmp_path)

        # Read
        content = mutator._read_spec_file(spec_file)

        # Find
        location = mutator._find_requirement_lines(content, "REQ-p00001")
        assert location is not None

        # Modify
        new_req = """# REQ-p00001: Test Requirement

**Level**: Prd | **Status**: Draft

## Assertions

A. The system SHALL do something.
B. The system SHALL do another thing.

*End* *Test Requirement* | **Hash**: newha5h1
---"""

        new_content = mutator.replace_requirement_text(content, location, new_req)

        # Write
        mutator._write_spec_file(spec_file, new_content)

        # Verify
        result = spec_file.read_text()
        assert "**Status**: Draft" in result
        assert "B. The system SHALL do another thing." in result
