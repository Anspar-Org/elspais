"""
Tests for recursive subdirectory parsing validation.

These tests verify that spec file discovery and parsing works correctly
for nested subdirectories (e.g., spec/regulations/fda/, spec/sub/sub/).

This validates issue 5.3 acceptance criteria:
- Files in spec/sub/ discovered and parsed
- Files in spec/sub/sub/ discovered and parsed
- File type patterns match at any depth
- skip_dirs excludes nested paths correctly
- Incremental refresh works for nested file changes
- Requirement IDs from nested files appear in graph
"""

import pytest
from pathlib import Path
import time

from elspais.core.parser import RequirementParser
from elspais.core.patterns import PatternConfig


# Sample requirement content for testing
def make_requirement(req_id: str, title: str = "Test Requirement", level: str = "PRD") -> str:
    return f"""# {req_id}: {title}

**Level**: {level} | **Status**: Active | **Implements**: -

## Assertions

A. The system SHALL do something.

*End* *{title}* | **Hash**: abc12345
---"""


@pytest.fixture
def temp_spec_dir(tmp_path):
    """Create a temporary spec directory with nested structure."""
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    return spec_dir


@pytest.fixture
def parser():
    """Create a RequirementParser with HHT-style config."""
    config = PatternConfig.from_dict({
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
    return RequirementParser(config)


class TestRecursiveDiscovery:
    """Tests for recursive file discovery in nested directories."""

    def test_files_in_spec_sub_discovered(self, temp_spec_dir, parser):
        """Test that files in spec/sub/ are discovered and parsed."""
        # Create nested directory
        sub_dir = temp_spec_dir / "sub"
        sub_dir.mkdir()

        # Create file in nested directory
        (sub_dir / "prd-nested.md").write_text(make_requirement("REQ-p00001", "Nested Requirement"))

        result = parser.parse_directory(temp_spec_dir, recursive=True)

        assert "REQ-p00001" in result.requirements
        assert result.requirements["REQ-p00001"].subdir == "sub"

    def test_files_in_spec_sub_sub_discovered(self, temp_spec_dir, parser):
        """Test that files in spec/sub/sub/ are discovered and parsed."""
        # Create deeply nested directory
        deep_dir = temp_spec_dir / "sub" / "sub"
        deep_dir.mkdir(parents=True)

        # Create file in deeply nested directory
        (deep_dir / "prd-deep.md").write_text(make_requirement("REQ-p00002", "Deep Requirement"))

        result = parser.parse_directory(temp_spec_dir, recursive=True)

        assert "REQ-p00002" in result.requirements
        assert result.requirements["REQ-p00002"].subdir == "sub/sub"

    def test_multiple_nesting_levels(self, temp_spec_dir, parser):
        """Test that files at multiple nesting levels are all discovered."""
        # Create structure:
        # spec/
        #   prd-root.md
        #   level1/
        #     prd-level1.md
        #     level2/
        #       prd-level2.md
        #       level3/
        #         prd-level3.md

        (temp_spec_dir / "prd-root.md").write_text(make_requirement("REQ-p00001", "Root"))

        level1 = temp_spec_dir / "level1"
        level1.mkdir()
        (level1 / "prd-level1.md").write_text(make_requirement("REQ-p00002", "Level1"))

        level2 = level1 / "level2"
        level2.mkdir()
        (level2 / "prd-level2.md").write_text(make_requirement("REQ-p00003", "Level2"))

        level3 = level2 / "level3"
        level3.mkdir()
        (level3 / "prd-level3.md").write_text(make_requirement("REQ-p00004", "Level3"))

        result = parser.parse_directory(temp_spec_dir, recursive=True)

        assert len(result.requirements) == 4
        assert "REQ-p00001" in result.requirements
        assert "REQ-p00002" in result.requirements
        assert "REQ-p00003" in result.requirements
        assert "REQ-p00004" in result.requirements

        # Verify subdirectory tracking
        assert result.requirements["REQ-p00001"].subdir == ""
        assert result.requirements["REQ-p00002"].subdir == "level1"
        assert result.requirements["REQ-p00003"].subdir == "level1/level2"
        assert result.requirements["REQ-p00004"].subdir == "level1/level2/level3"


class TestFilePatternMatching:
    """Tests for file pattern matching at any nesting depth."""

    def test_prd_pattern_matches_at_depth(self, temp_spec_dir, parser):
        """Test that prd-*.md pattern matches at any depth."""
        deep_dir = temp_spec_dir / "a" / "b" / "c"
        deep_dir.mkdir(parents=True)

        (deep_dir / "prd-deep.md").write_text(make_requirement("REQ-p00001"))

        result = parser.parse_directory(temp_spec_dir, patterns=["prd-*.md"], recursive=True)

        assert "REQ-p00001" in result.requirements

    def test_multiple_patterns_at_depth(self, temp_spec_dir, parser):
        """Test that multiple file patterns all match at any depth."""
        deep_dir = temp_spec_dir / "nested"
        deep_dir.mkdir()

        (deep_dir / "prd-feature.md").write_text(make_requirement("REQ-p00001", "PRD"))
        (deep_dir / "ops-deploy.md").write_text(make_requirement("REQ-o00001", "OPS"))
        (deep_dir / "dev-impl.md").write_text(make_requirement("REQ-d00001", "DEV"))

        result = parser.parse_directory(
            temp_spec_dir,
            patterns=["prd-*.md", "ops-*.md", "dev-*.md"],
            recursive=True
        )

        assert "REQ-p00001" in result.requirements
        assert "REQ-o00001" in result.requirements
        assert "REQ-d00001" in result.requirements

    def test_wildcard_pattern_matches_all_md(self, temp_spec_dir, parser):
        """Test that *.md pattern matches all markdown files at any depth."""
        (temp_spec_dir / "root.md").write_text(make_requirement("REQ-p00001", "Root"))

        nested = temp_spec_dir / "nested"
        nested.mkdir()
        (nested / "nested.md").write_text(make_requirement("REQ-p00002", "Nested"))

        result = parser.parse_directory(temp_spec_dir, patterns=["*.md"], recursive=True)

        assert "REQ-p00001" in result.requirements
        assert "REQ-p00002" in result.requirements


class TestSkipFilesInNestedPaths:
    """Tests for skip_files configuration with nested paths."""

    def test_skip_files_at_any_depth(self, temp_spec_dir, parser):
        """Test that skip_files works at any nesting depth."""
        deep_dir = temp_spec_dir / "deep"
        deep_dir.mkdir()

        (deep_dir / "prd-feature.md").write_text(make_requirement("REQ-p00001"))
        (deep_dir / "README.md").write_text("# This should be skipped")

        result = parser.parse_directory(
            temp_spec_dir,
            skip_files=["README.md"],
            recursive=True
        )

        assert "REQ-p00001" in result.requirements
        # README.md should not add any requirements (it's prose)

    def test_skip_files_multiple_depths(self, temp_spec_dir, parser):
        """Test skip_files works at multiple nesting depths."""
        # Create README.md at multiple levels
        (temp_spec_dir / "README.md").write_text("# Root readme")
        (temp_spec_dir / "prd-root.md").write_text(make_requirement("REQ-p00001"))

        sub = temp_spec_dir / "sub"
        sub.mkdir()
        (sub / "README.md").write_text("# Sub readme")
        (sub / "prd-sub.md").write_text(make_requirement("REQ-p00002"))

        result = parser.parse_directory(
            temp_spec_dir,
            skip_files=["README.md"],
            recursive=True
        )

        assert "REQ-p00001" in result.requirements
        assert "REQ-p00002" in result.requirements


# MCP Context Tests
try:
    import mcp
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False


@pytest.mark.skipif(not MCP_AVAILABLE, reason="MCP dependencies not installed")
class TestMCPContextNestedFiles:
    """Tests for MCP context handling of nested files."""

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

[patterns]
prefix = "REQ"
id_template = "{prefix}-{type}{id}"

[patterns.types.product]
id = "p"
level = 1

[patterns.types.operations]
id = "o"
level = 2

[patterns.types.development]
id = "d"
level = 3

[patterns.id_format]
style = "numeric"
digits = 5

[patterns.assertions]
label_style = "uppercase"
""")

        return WorkspaceContext.from_directory(tmp_path), tmp_path

    def test_nested_files_in_graph(self, mcp_context):
        """Test that requirement IDs from nested files appear in graph."""
        ctx, tmp_path = mcp_context
        spec_dir = tmp_path / "spec"

        # Create nested structure
        (spec_dir / "prd-root.md").write_text(make_requirement("REQ-p00001", "Root"))

        nested = spec_dir / "nested"
        nested.mkdir()
        (nested / "prd-nested.md").write_text(make_requirement("REQ-p00002", "Nested"))

        # Build graph (returns tuple of graph and validation)
        graph, _ = ctx.get_graph()

        # Both requirements should be in graph
        assert graph.find_by_id("REQ-p00001") is not None
        assert graph.find_by_id("REQ-p00002") is not None

    def test_incremental_refresh_nested_changes(self, mcp_context):
        """Test that incremental refresh works for nested file changes."""
        ctx, tmp_path = mcp_context
        spec_dir = tmp_path / "spec"

        # Create initial structure
        nested = spec_dir / "nested"
        nested.mkdir()
        nested_file = nested / "prd-nested.md"
        nested_file.write_text(make_requirement("REQ-p00001", "Original"))

        # Build initial graph (returns tuple)
        graph, _ = ctx.get_graph()
        node = graph.find_by_id("REQ-p00001")
        assert node is not None
        original_label = node.label

        # Modify nested file
        time.sleep(0.1)  # Ensure mtime changes
        nested_file.write_text(make_requirement("REQ-p00001", "Modified"))

        # Check staleness
        assert ctx.is_graph_stale()

        # Refresh (returns tuple)
        graph, _ = ctx.partial_refresh()

        # Verify update - label should contain the title
        new_node = graph.find_by_id("REQ-p00001")
        assert new_node is not None
        assert "Modified" in new_node.label

    def test_tracked_files_include_nested(self, mcp_context):
        """Test that TrackedFile registry includes nested paths."""
        ctx, tmp_path = mcp_context
        spec_dir = tmp_path / "spec"

        # Create nested structure
        (spec_dir / "prd-root.md").write_text(make_requirement("REQ-p00001"))

        deep = spec_dir / "a" / "b" / "c"
        deep.mkdir(parents=True)
        (deep / "prd-deep.md").write_text(make_requirement("REQ-p00002"))

        # Build graph
        ctx.get_graph()

        # Check tracked files
        tracked = ctx.get_tracked_files()

        # Should have both files tracked
        tracked_paths = [str(tf.path) for tf in tracked.values()]
        assert any("prd-root.md" in p for p in tracked_paths)
        assert any("prd-deep.md" in p for p in tracked_paths)

    def test_new_nested_file_detected(self, mcp_context):
        """Test that new files in nested directories are detected."""
        ctx, tmp_path = mcp_context
        spec_dir = tmp_path / "spec"

        # Create initial structure
        (spec_dir / "prd-root.md").write_text(make_requirement("REQ-p00001"))

        # Build initial graph (returns tuple)
        graph, _ = ctx.get_graph()
        # Count requirement nodes only (exclude assertion nodes)
        req_nodes = [n for n in graph.all_nodes() if n.id.startswith("REQ-") and "-" not in n.id[4:]]
        assert len(req_nodes) == 1

        # Add new file in nested directory
        nested = spec_dir / "nested"
        nested.mkdir()
        (nested / "prd-new.md").write_text(make_requirement("REQ-p00002"))

        # Should be stale
        assert ctx.is_graph_stale()

        # Refresh (returns tuple)
        graph, _ = ctx.partial_refresh()

        # Should now have both
        assert graph.find_by_id("REQ-p00001") is not None
        assert graph.find_by_id("REQ-p00002") is not None

    def test_deleted_nested_file_detected(self, mcp_context):
        """Test that deleted files in nested directories are detected."""
        ctx, tmp_path = mcp_context
        spec_dir = tmp_path / "spec"

        # Create nested structure
        nested = spec_dir / "nested"
        nested.mkdir()
        nested_file = nested / "prd-nested.md"
        nested_file.write_text(make_requirement("REQ-p00001"))

        # Build initial graph (returns tuple)
        graph, _ = ctx.get_graph()
        assert graph.find_by_id("REQ-p00001") is not None

        # Delete nested file
        nested_file.unlink()

        # Should be stale
        assert ctx.is_graph_stale()

        # Refresh (returns tuple)
        graph, _ = ctx.partial_refresh()

        # Should no longer have the requirement
        assert graph.find_by_id("REQ-p00001") is None


class TestSubdirTracking:
    """Tests for subdir attribute tracking in nested files."""

    def test_subdir_attribute_set_correctly(self, temp_spec_dir, parser):
        """Test that subdir attribute is set correctly for nested files."""
        # Create structure
        regulations = temp_spec_dir / "regulations"
        fda = regulations / "fda"
        fda.mkdir(parents=True)

        (fda / "prd-fda.md").write_text(make_requirement("REQ-p00001", "FDA Requirement"))

        result = parser.parse_directory(temp_spec_dir, recursive=True)

        assert result.requirements["REQ-p00001"].subdir == "regulations/fda"

    def test_root_file_has_empty_subdir(self, temp_spec_dir, parser):
        """Test that root-level files have empty subdir."""
        (temp_spec_dir / "prd-root.md").write_text(make_requirement("REQ-p00001"))

        result = parser.parse_directory(temp_spec_dir, recursive=True)

        assert result.requirements["REQ-p00001"].subdir == ""


class TestNonRecursiveForComparison:
    """Tests to verify non-recursive behavior for comparison."""

    def test_non_recursive_skips_nested(self, temp_spec_dir, parser):
        """Test that recursive=False skips nested directories."""
        (temp_spec_dir / "prd-root.md").write_text(make_requirement("REQ-p00001"))

        nested = temp_spec_dir / "nested"
        nested.mkdir()
        (nested / "prd-nested.md").write_text(make_requirement("REQ-p00002"))

        result = parser.parse_directory(temp_spec_dir, recursive=False)

        # Only root file should be found
        assert "REQ-p00001" in result.requirements
        assert "REQ-p00002" not in result.requirements

    def test_recursive_finds_nested(self, temp_spec_dir, parser):
        """Test that recursive=True finds nested directories."""
        (temp_spec_dir / "prd-root.md").write_text(make_requirement("REQ-p00001"))

        nested = temp_spec_dir / "nested"
        nested.mkdir()
        (nested / "prd-nested.md").write_text(make_requirement("REQ-p00002"))

        result = parser.parse_directory(temp_spec_dir, recursive=True)

        # Both files should be found
        assert "REQ-p00001" in result.requirements
        assert "REQ-p00002" in result.requirements
