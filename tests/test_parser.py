"""
Tests for elspais.core.parser module.
"""

import pytest
from pathlib import Path


class TestRequirementParser:
    """Tests for RequirementParser class."""

    def test_parse_single_requirement(self, sample_requirement_text):
        """Test parsing a single requirement from text."""
        from elspais.core.parser import RequirementParser
        from elspais.core.patterns import PatternConfig

        config = PatternConfig(
            id_template="{prefix}-{type}{id}",
            prefix="REQ",
            types={"prd": {"id": "p", "level": 1}},
            id_format={"style": "numeric", "digits": 5, "leading_zeros": True},
        )
        parser = RequirementParser(config)

        requirements = parser.parse_text(sample_requirement_text)

        assert len(requirements) == 1
        req = requirements["REQ-p00001"]
        assert req.id == "REQ-p00001"
        assert req.title == "Sample Requirement"
        assert req.status == "Active"
        assert req.hash == "test1234"
        assert len(req.acceptance_criteria) == 2

    def test_parse_file(self, hht_like_fixture):
        """Test parsing requirements from a file."""
        from elspais.core.parser import RequirementParser
        from elspais.core.patterns import PatternConfig
        from elspais.config.loader import load_config

        config_dict = load_config(hht_like_fixture / ".elspais.toml")
        pattern_config = PatternConfig.from_dict(config_dict["patterns"])
        parser = RequirementParser(pattern_config)

        prd_file = hht_like_fixture / "spec" / "prd-core.md"
        requirements = parser.parse_file(prd_file)

        assert len(requirements) == 3
        assert "REQ-p00001" in requirements
        assert "REQ-p00002" in requirements
        assert "REQ-p00003" in requirements

    def test_parse_directory(self, hht_like_fixture):
        """Test parsing all requirements from a directory."""
        from elspais.core.parser import RequirementParser
        from elspais.core.patterns import PatternConfig
        from elspais.config.loader import load_config

        config_dict = load_config(hht_like_fixture / ".elspais.toml")
        pattern_config = PatternConfig.from_dict(config_dict["patterns"])
        parser = RequirementParser(pattern_config)

        spec_dir = hht_like_fixture / "spec"
        requirements = parser.parse_directory(spec_dir)

        # Should have all PRD, OPS, and DEV requirements
        assert len(requirements) >= 8  # At least 3 PRD + 2 OPS + 3 DEV

    def test_parse_extracts_implements(self, hht_like_fixture):
        """Test parsing extracts Implements field correctly."""
        from elspais.core.parser import RequirementParser
        from elspais.core.patterns import PatternConfig
        from elspais.config.loader import load_config

        config_dict = load_config(hht_like_fixture / ".elspais.toml")
        pattern_config = PatternConfig.from_dict(config_dict["patterns"])
        parser = RequirementParser(pattern_config)

        dev_file = hht_like_fixture / "spec" / "dev-impl.md"
        requirements = parser.parse_file(dev_file)

        # REQ-d00001 implements p00001 and o00001
        req_d00001 = requirements.get("REQ-d00001")
        assert req_d00001 is not None
        assert "p00001" in req_d00001.implements
        assert "o00001" in req_d00001.implements

    def test_parse_extracts_acceptance_criteria(self, hht_like_fixture):
        """Test parsing extracts acceptance criteria correctly."""
        from elspais.core.parser import RequirementParser
        from elspais.core.patterns import PatternConfig
        from elspais.config.loader import load_config

        config_dict = load_config(hht_like_fixture / ".elspais.toml")
        pattern_config = PatternConfig.from_dict(config_dict["patterns"])
        parser = RequirementParser(pattern_config)

        prd_file = hht_like_fixture / "spec" / "prd-core.md"
        requirements = parser.parse_file(prd_file)

        req = requirements.get("REQ-p00001")
        assert req is not None
        assert len(req.acceptance_criteria) >= 1

    def test_parse_tracks_location(self, hht_like_fixture):
        """Test parsing tracks file path and line number."""
        from elspais.core.parser import RequirementParser
        from elspais.core.patterns import PatternConfig
        from elspais.config.loader import load_config

        config_dict = load_config(hht_like_fixture / ".elspais.toml")
        pattern_config = PatternConfig.from_dict(config_dict["patterns"])
        parser = RequirementParser(pattern_config)

        prd_file = hht_like_fixture / "spec" / "prd-core.md"
        requirements = parser.parse_file(prd_file)

        req = requirements.get("REQ-p00001")
        assert req is not None
        assert req.file_path is not None
        assert "prd-core.md" in str(req.file_path)
        assert req.line_number is not None
        assert req.line_number > 0


class TestFDAStyleParsing:
    """Tests for FDA-style requirement parsing."""

    def test_parse_fda_style(self, fda_style_fixture):
        """Test parsing FDA-style IDs (PRD-00001)."""
        from elspais.core.parser import RequirementParser
        from elspais.core.patterns import PatternConfig
        from elspais.config.loader import load_config

        config_dict = load_config(fda_style_fixture / ".elspais.toml")
        pattern_config = PatternConfig.from_dict(config_dict["patterns"])
        parser = RequirementParser(pattern_config)

        prd_file = fda_style_fixture / "spec" / "prd-core.md"
        requirements = parser.parse_file(prd_file)

        assert "PRD-00001" in requirements
        assert "PRD-00002" in requirements


class TestJiraStyleParsing:
    """Tests for Jira-style requirement parsing."""

    def test_parse_jira_style(self, jira_style_fixture):
        """Test parsing Jira-style IDs (PROJ-123)."""
        from elspais.core.parser import RequirementParser
        from elspais.core.patterns import PatternConfig
        from elspais.config.loader import load_config

        config_dict = load_config(jira_style_fixture / ".elspais.toml")
        pattern_config = PatternConfig.from_dict(config_dict["patterns"])
        parser = RequirementParser(pattern_config)

        features_file = jira_style_fixture / "requirements" / "features.md"
        requirements = parser.parse_file(features_file)

        assert "PROJ-1" in requirements
        assert "PROJ-2" in requirements
        assert "PROJ-42" in requirements
        assert "PROJ-123" in requirements


class TestNamedStyleParsing:
    """Tests for named requirement parsing."""

    def test_parse_named_style(self, named_reqs_fixture):
        """Test parsing named IDs (REQ-UserAuth)."""
        from elspais.core.parser import RequirementParser
        from elspais.core.patterns import PatternConfig
        from elspais.config.loader import load_config

        config_dict = load_config(named_reqs_fixture / ".elspais.toml")
        pattern_config = PatternConfig.from_dict(config_dict["patterns"])
        parser = RequirementParser(pattern_config)

        features_file = named_reqs_fixture / "spec" / "features.md"
        requirements = parser.parse_file(features_file)

        assert "REQ-UserAuthentication" in requirements
        assert "REQ-DataExport" in requirements
        assert "REQ-AuditLog" in requirements


class TestAssociatedStyleParsing:
    """Tests for associated-style requirement parsing."""

    def test_parse_associated_style(self, associated_repo_fixture):
        """Test parsing associated IDs (REQ-CAL-d00001)."""
        from elspais.core.parser import RequirementParser
        from elspais.core.patterns import PatternConfig
        from elspais.config.loader import load_config

        config_dict = load_config(associated_repo_fixture / ".elspais.toml")
        pattern_config = PatternConfig.from_dict(config_dict["patterns"])
        parser = RequirementParser(pattern_config)

        spec_dir = associated_repo_fixture / "spec"
        requirements = parser.parse_directory(spec_dir)

        assert "REQ-CAL-p00001" in requirements
        assert "REQ-CAL-p00002" in requirements
        assert "REQ-CAL-d00001" in requirements


class TestParserEdgeCases:
    """Tests for parser edge cases."""

    def test_parse_empty_file(self, tmp_path):
        """Test parsing empty file returns empty dict."""
        from elspais.core.parser import RequirementParser
        from elspais.core.patterns import PatternConfig

        config = PatternConfig(
            id_template="{prefix}-{type}{id}",
            prefix="REQ",
            types={"prd": {"id": "p", "level": 1}},
            id_format={"style": "numeric", "digits": 5},
        )
        parser = RequirementParser(config)

        empty_file = tmp_path / "empty.md"
        empty_file.write_text("")

        requirements = parser.parse_file(empty_file)
        assert len(requirements) == 0

    def test_parse_file_no_requirements(self, tmp_path):
        """Test parsing file with no requirements."""
        from elspais.core.parser import RequirementParser
        from elspais.core.patterns import PatternConfig

        config = PatternConfig(
            id_template="{prefix}-{type}{id}",
            prefix="REQ",
            types={"prd": {"id": "p", "level": 1}},
            id_format={"style": "numeric", "digits": 5},
        )
        parser = RequirementParser(config)

        no_reqs_file = tmp_path / "no-reqs.md"
        no_reqs_file.write_text("# Just a heading\n\nSome text without requirements.")

        requirements = parser.parse_file(no_reqs_file)
        assert len(requirements) == 0

    def test_parse_handles_malformed_requirement(self, tmp_path):
        """Test parser handles malformed requirements gracefully."""
        from elspais.core.parser import RequirementParser
        from elspais.core.patterns import PatternConfig

        config = PatternConfig(
            id_template="{prefix}-{type}{id}",
            prefix="REQ",
            types={"prd": {"id": "p", "level": 1}},
            id_format={"style": "numeric", "digits": 5, "leading_zeros": True},
        )
        parser = RequirementParser(config)

        malformed_file = tmp_path / "malformed.md"
        malformed_file.write_text("""
### REQ-p00001: Missing End Marker

Some body text without proper end marker.

### REQ-p00002: Valid Requirement

**Level**: PRD | **Status**: Active

Body text.

**Acceptance Criteria**:
- Criterion

*End* *Valid Requirement* | **Hash**: valid123
---
""")

        # Should still parse valid requirements
        requirements = parser.parse_file(malformed_file)
        assert "REQ-p00002" in requirements


class TestMultipleSpecDirectories:
    """Tests for parsing requirements from multiple spec directories."""

    def test_parse_directories_with_string(self, tmp_path):
        """Test parse_directories accepts a string."""
        from elspais.core.parser import RequirementParser
        from elspais.core.patterns import PatternConfig

        config = PatternConfig(
            id_template="{prefix}-{type}{id}",
            prefix="REQ",
            types={"prd": {"id": "p", "level": 1}},
            id_format={"style": "numeric", "digits": 5, "leading_zeros": True},
        )
        parser = RequirementParser(config)

        # Create spec directory
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        req_file = spec_dir / "reqs.md"
        req_file.write_text("""
# REQ-p00001: Test Requirement

**Level**: PRD | **Status**: Active

Body text.

**Acceptance Criteria**:
- Criterion

*End* *Test Requirement* | **Hash**: test1234
---
""")

        requirements = parser.parse_directories("spec", base_path=tmp_path)
        assert len(requirements) == 1
        assert "REQ-p00001" in requirements

    def test_parse_directories_with_list(self, tmp_path):
        """Test parse_directories accepts a list of directories."""
        from elspais.core.parser import RequirementParser
        from elspais.core.patterns import PatternConfig

        config = PatternConfig(
            id_template="{prefix}-{type}{id}",
            prefix="REQ",
            types={"prd": {"id": "p", "level": 1}},
            id_format={"style": "numeric", "digits": 5, "leading_zeros": True},
        )
        parser = RequirementParser(config)

        # Create first spec directory
        spec_dir1 = tmp_path / "spec"
        spec_dir1.mkdir()
        req_file1 = spec_dir1 / "reqs.md"
        req_file1.write_text("""
# REQ-p00001: First Requirement

**Level**: PRD | **Status**: Active

Body text.

*End* *First Requirement* | **Hash**: test1234
---
""")

        # Create second spec directory (subdirectory)
        spec_dir2 = tmp_path / "spec" / "roadmap"
        spec_dir2.mkdir()
        req_file2 = spec_dir2 / "roadmap-reqs.md"
        req_file2.write_text("""
# REQ-p00002: Second Requirement

**Level**: PRD | **Status**: Draft

Body text.

*End* *Second Requirement* | **Hash**: test5678
---
""")

        # Parse both directories
        requirements = parser.parse_directories(
            ["spec", "spec/roadmap"],
            base_path=tmp_path
        )
        assert len(requirements) == 2
        assert "REQ-p00001" in requirements
        assert "REQ-p00002" in requirements

    def test_parse_directories_skips_nonexistent(self, tmp_path):
        """Test parse_directories skips non-existent directories."""
        from elspais.core.parser import RequirementParser
        from elspais.core.patterns import PatternConfig

        config = PatternConfig(
            id_template="{prefix}-{type}{id}",
            prefix="REQ",
            types={"prd": {"id": "p", "level": 1}},
            id_format={"style": "numeric", "digits": 5, "leading_zeros": True},
        )
        parser = RequirementParser(config)

        # Create only one spec directory
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        req_file = spec_dir / "reqs.md"
        req_file.write_text("""
# REQ-p00001: Test Requirement

**Level**: PRD | **Status**: Active

Body text.

*End* *Test Requirement* | **Hash**: test1234
---
""")

        # Parse with one existing and one non-existent directory
        requirements = parser.parse_directories(
            ["spec", "nonexistent/path"],
            base_path=tmp_path
        )
        assert len(requirements) == 1
        assert "REQ-p00001" in requirements

    def test_parse_directories_does_not_recurse(self, tmp_path):
        """Test parse_directories does NOT recursively search subdirectories."""
        from elspais.core.parser import RequirementParser
        from elspais.core.patterns import PatternConfig

        config = PatternConfig(
            id_template="{prefix}-{type}{id}",
            prefix="REQ",
            types={"prd": {"id": "p", "level": 1}},
            id_format={"style": "numeric", "digits": 5, "leading_zeros": True},
        )
        parser = RequirementParser(config)

        # Create spec directory
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        req_file = spec_dir / "reqs.md"
        req_file.write_text("""
# REQ-p00001: Top Level Requirement

**Level**: PRD | **Status**: Active

Body text.

*End* *Top Level Requirement* | **Hash**: test1234
---
""")

        # Create subdirectory with another requirement
        sub_dir = spec_dir / "subdir"
        sub_dir.mkdir()
        sub_req_file = sub_dir / "sub-reqs.md"
        sub_req_file.write_text("""
# REQ-p00002: Sub Directory Requirement

**Level**: PRD | **Status**: Active

Body text.

*End* *Sub Directory Requirement* | **Hash**: test5678
---
""")

        # Parse only the top-level spec directory
        requirements = parser.parse_directories("spec", base_path=tmp_path)

        # Should only find the top-level requirement, not the subdirectory one
        assert len(requirements) == 1
        assert "REQ-p00001" in requirements
        assert "REQ-p00002" not in requirements

    def test_parse_directories_with_skip_files(self, tmp_path):
        """Test parse_directories respects skip_files in all directories."""
        from elspais.core.parser import RequirementParser
        from elspais.core.patterns import PatternConfig

        config = PatternConfig(
            id_template="{prefix}-{type}{id}",
            prefix="REQ",
            types={"prd": {"id": "p", "level": 1}},
            id_format={"style": "numeric", "digits": 5, "leading_zeros": True},
        )
        parser = RequirementParser(config)

        # Create first spec directory
        spec_dir1 = tmp_path / "spec"
        spec_dir1.mkdir()
        req_file1 = spec_dir1 / "reqs.md"
        req_file1.write_text("""
# REQ-p00001: First Requirement

**Level**: PRD | **Status**: Active

Body text.

*End* *First Requirement* | **Hash**: test1234
---
""")
        skip_file1 = spec_dir1 / "README.md"
        skip_file1.write_text("""
# REQ-p00099: Should Be Skipped

**Level**: PRD | **Status**: Active

This should not be parsed.

*End* *Should Be Skipped* | **Hash**: skip1234
---
""")

        # Create second spec directory
        spec_dir2 = tmp_path / "spec" / "roadmap"
        spec_dir2.mkdir()
        req_file2 = spec_dir2 / "roadmap-reqs.md"
        req_file2.write_text("""
# REQ-p00002: Second Requirement

**Level**: PRD | **Status**: Draft

Body text.

*End* *Second Requirement* | **Hash**: test5678
---
""")

        # Parse both directories with skip_files
        requirements = parser.parse_directories(
            ["spec", "spec/roadmap"],
            base_path=tmp_path,
            skip_files=["README.md"]
        )
        assert len(requirements) == 2
        assert "REQ-p00001" in requirements
        assert "REQ-p00002" in requirements
        assert "REQ-p00099" not in requirements


class TestNoReferenceValues:
    """Tests for no_reference_values feature."""

    def test_dash_is_no_reference(self, tmp_path):
        """Test that '-' in Implements is treated as no reference."""
        from elspais.core.parser import RequirementParser
        from elspais.core.patterns import PatternConfig

        config = PatternConfig(
            id_template="{prefix}-{type}{id}",
            prefix="REQ",
            types={"prd": {"id": "p", "level": 1}},
            id_format={"style": "numeric", "digits": 5, "leading_zeros": True},
        )
        parser = RequirementParser(config)

        req_file = tmp_path / "req.md"
        req_file.write_text("""
# REQ-p00001: No Reference Requirement

**Level**: PRD | **Implements**: - | **Status**: Active

Body text.

**Acceptance Criteria**:
- Criterion

*End* *No Reference Requirement* | **Hash**: test1234
---
""")

        requirements = parser.parse_file(req_file)
        assert "REQ-p00001" in requirements
        assert requirements["REQ-p00001"].implements == []

    def test_null_is_no_reference(self, tmp_path):
        """Test that 'null' in Implements is treated as no reference."""
        from elspais.core.parser import RequirementParser
        from elspais.core.patterns import PatternConfig

        config = PatternConfig(
            id_template="{prefix}-{type}{id}",
            prefix="REQ",
            types={"prd": {"id": "p", "level": 1}},
            id_format={"style": "numeric", "digits": 5, "leading_zeros": True},
        )
        parser = RequirementParser(config)

        req_file = tmp_path / "req.md"
        req_file.write_text("""
# REQ-p00001: Null Reference Requirement

**Level**: PRD | **Implements**: null | **Status**: Active

Body text.

**Acceptance Criteria**:
- Criterion

*End* *Null Reference Requirement* | **Hash**: test1234
---
""")

        requirements = parser.parse_file(req_file)
        assert "REQ-p00001" in requirements
        assert requirements["REQ-p00001"].implements == []

    def test_custom_no_reference_values(self, tmp_path):
        """Test custom no_reference_values configuration."""
        from elspais.core.parser import RequirementParser
        from elspais.core.patterns import PatternConfig

        config = PatternConfig(
            id_template="{prefix}-{type}{id}",
            prefix="REQ",
            types={"prd": {"id": "p", "level": 1}},
            id_format={"style": "numeric", "digits": 5, "leading_zeros": True},
        )
        # Custom no-reference values
        parser = RequirementParser(config, no_reference_values=["NONE", "N/A", "-"])

        req_file = tmp_path / "req.md"
        req_file.write_text("""
# REQ-p00001: Custom No Reference

**Level**: PRD | **Implements**: NONE | **Status**: Active

Body text.

**Acceptance Criteria**:
- Criterion

*End* *Custom No Reference* | **Hash**: test1234
---
""")

        requirements = parser.parse_file(req_file)
        assert "REQ-p00001" in requirements
        assert requirements["REQ-p00001"].implements == []

    def test_valid_reference_not_treated_as_no_reference(self, tmp_path):
        """Test that valid references are not treated as no-reference."""
        from elspais.core.parser import RequirementParser
        from elspais.core.patterns import PatternConfig

        config = PatternConfig(
            id_template="{prefix}-{type}{id}",
            prefix="REQ",
            types={
                "prd": {"id": "p", "level": 1},
                "dev": {"id": "d", "level": 3},
            },
            id_format={"style": "numeric", "digits": 5, "leading_zeros": True},
        )
        parser = RequirementParser(config)

        req_file = tmp_path / "req.md"
        req_file.write_text("""
# REQ-d00001: Dev Requirement

**Level**: Dev | **Implements**: p00001 | **Status**: Active

Body text.

**Acceptance Criteria**:
- Criterion

*End* *Dev Requirement* | **Hash**: test1234
---
""")

        requirements = parser.parse_file(req_file)
        assert "REQ-d00001" in requirements
        assert requirements["REQ-d00001"].implements == ["p00001"]


class TestSubdirParsing:
    """Tests for parsing requirements with subdir tracking."""

    def test_parse_file_with_subdir(self, tmp_path):
        """Test parsing a file with explicit subdir parameter."""
        from elspais.core.parser import RequirementParser
        from elspais.core.patterns import PatternConfig

        config = PatternConfig(
            id_template="{prefix}-{type}{id}",
            prefix="REQ",
            types={"prd": {"id": "p", "level": 1}},
            id_format={"style": "numeric", "digits": 5, "leading_zeros": True},
        )
        parser = RequirementParser(config)

        # Create roadmap directory
        roadmap_dir = tmp_path / "spec" / "roadmap"
        roadmap_dir.mkdir(parents=True)
        req_file = roadmap_dir / "roadmap-reqs.md"
        req_file.write_text("""
# REQ-p00001: Future Feature

**Level**: PRD | **Status**: Draft

Body text.

*End* *Future Feature* | **Hash**: test1234
---
""")

        requirements = parser.parse_file(req_file, subdir="roadmap")
        req = requirements["REQ-p00001"]
        assert req.subdir == "roadmap"
        assert req.is_roadmap is True

    def test_parse_file_no_subdir(self, tmp_path):
        """Test parsing a file without subdir parameter defaults to empty."""
        from elspais.core.parser import RequirementParser
        from elspais.core.patterns import PatternConfig

        config = PatternConfig(
            id_template="{prefix}-{type}{id}",
            prefix="REQ",
            types={"prd": {"id": "p", "level": 1}},
            id_format={"style": "numeric", "digits": 5, "leading_zeros": True},
        )
        parser = RequirementParser(config)

        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        req_file = spec_dir / "prd-core.md"
        req_file.write_text("""
# REQ-p00001: Core Feature

**Level**: PRD | **Status**: Active

Body text.

*End* *Core Feature* | **Hash**: test1234
---
""")

        requirements = parser.parse_file(req_file)
        req = requirements["REQ-p00001"]
        assert req.subdir == ""
        assert req.is_roadmap is False

    def test_parse_directory_with_subdirs_auto_detects(self, tmp_path):
        """Test parse_directory_with_subdirs auto-detects subdir from path."""
        from elspais.core.parser import RequirementParser
        from elspais.core.patterns import PatternConfig

        config = PatternConfig(
            id_template="{prefix}-{type}{id}",
            prefix="REQ",
            types={"prd": {"id": "p", "level": 1}},
            id_format={"style": "numeric", "digits": 5, "leading_zeros": True},
        )
        parser = RequirementParser(config)

        # Create spec directory structure
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        # Root spec file
        root_req = spec_dir / "prd-core.md"
        root_req.write_text("""
# REQ-p00001: Core Feature

**Level**: PRD | **Status**: Active

Body text.

*End* *Core Feature* | **Hash**: test1234
---
""")

        # Roadmap subdirectory
        roadmap_dir = spec_dir / "roadmap"
        roadmap_dir.mkdir()
        roadmap_req = roadmap_dir / "prd-roadmap.md"
        roadmap_req.write_text("""
# REQ-p00002: Future Feature

**Level**: PRD | **Status**: Draft

Body text.

*End* *Future Feature* | **Hash**: test5678
---
""")

        # Parse with subdirs
        requirements = parser.parse_directory_with_subdirs(
            spec_dir,
            subdirs=["roadmap"]
        )

        # Check root requirement
        assert "REQ-p00001" in requirements
        assert requirements["REQ-p00001"].subdir == ""
        assert requirements["REQ-p00001"].is_roadmap is False

        # Check roadmap requirement
        assert "REQ-p00002" in requirements
        assert requirements["REQ-p00002"].subdir == "roadmap"
        assert requirements["REQ-p00002"].is_roadmap is True

    def test_parse_directory_with_subdirs_multiple(self, tmp_path):
        """Test parse_directory_with_subdirs with multiple subdirs."""
        from elspais.core.parser import RequirementParser
        from elspais.core.patterns import PatternConfig

        config = PatternConfig(
            id_template="{prefix}-{type}{id}",
            prefix="REQ",
            types={"prd": {"id": "p", "level": 1}},
            id_format={"style": "numeric", "digits": 5, "leading_zeros": True},
        )
        parser = RequirementParser(config)

        # Create spec directory structure
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        # Root spec file
        (spec_dir / "prd-core.md").write_text("""
# REQ-p00001: Core Feature

**Level**: PRD | **Status**: Active

Body text.

*End* *Core Feature* | **Hash**: test1234
---
""")

        # Roadmap subdirectory
        (spec_dir / "roadmap").mkdir()
        (spec_dir / "roadmap" / "prd-roadmap.md").write_text("""
# REQ-p00002: Future Feature

**Level**: PRD | **Status**: Draft

Body text.

*End* *Future Feature* | **Hash**: test5678
---
""")

        # Archive subdirectory
        (spec_dir / "archive").mkdir()
        (spec_dir / "archive" / "prd-old.md").write_text("""
# REQ-p00003: Archived Feature

**Level**: PRD | **Status**: Deprecated

Body text.

*End* *Archived Feature* | **Hash**: testabcd
---
""")

        # Parse with multiple subdirs
        requirements = parser.parse_directory_with_subdirs(
            spec_dir,
            subdirs=["roadmap", "archive"]
        )

        assert len(requirements) == 3
        assert requirements["REQ-p00001"].subdir == ""
        assert requirements["REQ-p00002"].subdir == "roadmap"
        assert requirements["REQ-p00003"].subdir == "archive"


class TestAssertionParsing:
    """Tests for parsing assertion-based requirements."""

    def test_parse_assertions_section(self, tmp_path):
        """Test parsing requirements with ## Assertions section."""
        from elspais.core.parser import RequirementParser
        from elspais.core.patterns import PatternConfig

        config = PatternConfig(
            id_template="{prefix}-{type}{id}",
            prefix="REQ",
            types={"prd": {"id": "p", "level": 1}},
            id_format={"style": "numeric", "digits": 5, "leading_zeros": True},
        )
        parser = RequirementParser(config)

        req_file = tmp_path / "req.md"
        req_file.write_text("""
# REQ-p00001: User Authentication

**Level**: PRD | **Status**: Active | **Implements**: -

## Assertions

A. The system SHALL provide secure user authentication.
B. The system SHALL support email and password login.
C. The system SHALL NOT allow unauthenticated access.

*End* *User Authentication* | **Hash**: test1234
---
""")

        requirements = parser.parse_file(req_file)
        assert "REQ-p00001" in requirements
        req = requirements["REQ-p00001"]

        assert len(req.assertions) == 3
        assert req.assertions[0].label == "A"
        assert "secure user authentication" in req.assertions[0].text
        assert req.assertions[1].label == "B"
        assert req.assertions[2].label == "C"
        assert "SHALL NOT" in req.assertions[2].text

    def test_parse_assertions_with_placeholder(self, tmp_path):
        """Test parsing assertions with placeholder values."""
        from elspais.core.parser import RequirementParser
        from elspais.core.patterns import PatternConfig

        config = PatternConfig(
            id_template="{prefix}-{type}{id}",
            prefix="REQ",
            types={"dev": {"id": "d", "level": 3}},
            id_format={"style": "numeric", "digits": 5, "leading_zeros": True},
        )
        parser = RequirementParser(config)

        req_file = tmp_path / "req.md"
        req_file.write_text("""
# REQ-d00001: Implementation Detail

**Level**: Dev | **Status**: Active | **Implements**: p00001

## Assertions

A. The implementation SHALL use bcrypt.
B. Removed - was duplicate of A.
C. The implementation SHALL NOT store plaintext.

*End* *Implementation Detail* | **Hash**: test1234
---
""")

        requirements = parser.parse_file(req_file)
        req = requirements["REQ-d00001"]

        assert len(req.assertions) == 3
        assert req.assertions[0].is_placeholder is False
        assert req.assertions[1].is_placeholder is True
        assert req.assertions[2].is_placeholder is False

    def test_parse_assertions_fixture(self, assertions_fixture):
        """Test parsing assertions from fixture directory."""
        from elspais.core.parser import RequirementParser
        from elspais.core.patterns import PatternConfig

        config = PatternConfig(
            id_template="{prefix}-{type}{id}",
            prefix="REQ",
            types={
                "prd": {"id": "p", "level": 1},
                "dev": {"id": "d", "level": 3},
            },
            id_format={"style": "numeric", "digits": 5, "leading_zeros": True},
        )
        parser = RequirementParser(config)

        spec_dir = assertions_fixture / "spec"
        requirements = parser.parse_directory(spec_dir)

        # Check PRD requirements
        assert "REQ-p00001" in requirements
        assert len(requirements["REQ-p00001"].assertions) == 3

        # Check DEV requirements
        assert "REQ-d00001" in requirements
        assert len(requirements["REQ-d00001"].assertions) == 3

    def test_parse_mixed_format(self, tmp_path):
        """Test parsing requirements with both Acceptance Criteria and Assertions."""
        from elspais.core.parser import RequirementParser
        from elspais.core.patterns import PatternConfig

        config = PatternConfig(
            id_template="{prefix}-{type}{id}",
            prefix="REQ",
            types={"prd": {"id": "p", "level": 1}},
            id_format={"style": "numeric", "digits": 5, "leading_zeros": True},
        )
        parser = RequirementParser(config)

        req_file = tmp_path / "req.md"
        req_file.write_text("""
# REQ-p00001: Mixed Format

**Level**: PRD | **Status**: Active | **Implements**: -

## Assertions

A. The system SHALL do something.

**Acceptance Criteria**:
- Old style criterion

*End* *Mixed Format* | **Hash**: test1234
---
""")

        requirements = parser.parse_file(req_file)
        req = requirements["REQ-p00001"]

        # Both should be parsed
        assert len(req.assertions) == 1
        assert len(req.acceptance_criteria) == 1
