"""
Tests for elspais.mcp.context graph functionality.

Tests GraphState caching, staleness detection, and graph building.
"""

import time
from pathlib import Path

import pytest


class TestGraphState:
    """Tests for GraphState dataclass."""

    def test_graph_state_creation(self, hht_like_fixture):
        """Test creating GraphState via context."""
        from elspais.mcp.context import WorkspaceContext

        ctx = WorkspaceContext.from_directory(hht_like_fixture)
        graph, validation = ctx.get_graph()

        # Should have created a GraphState
        assert ctx._graph_state is not None
        assert ctx._graph_state.graph is graph
        assert ctx._graph_state.validation is validation
        assert ctx._graph_state.built_at > 0
        assert len(ctx._graph_state.file_mtimes) > 0


class TestGetGraph:
    """Tests for get_graph method."""

    def test_get_graph_returns_graph(self, hht_like_fixture):
        """Test get_graph returns a valid graph."""
        from elspais.mcp.context import WorkspaceContext
        from elspais.core.graph import TraceGraph
        from elspais.core.graph_builder import ValidationResult

        ctx = WorkspaceContext.from_directory(hht_like_fixture)
        graph, validation = ctx.get_graph()

        assert isinstance(graph, TraceGraph)
        assert isinstance(validation, ValidationResult)
        assert graph.node_count() > 0

    def test_get_graph_caches_result(self, hht_like_fixture):
        """Test that get_graph returns cached result on second call."""
        from elspais.mcp.context import WorkspaceContext

        ctx = WorkspaceContext.from_directory(hht_like_fixture)
        graph1, _ = ctx.get_graph()
        graph2, _ = ctx.get_graph()

        assert graph1 is graph2  # Same object (cached)

    def test_get_graph_force_refresh(self, hht_like_fixture):
        """Test force_refresh=True rebuilds graph."""
        from elspais.mcp.context import WorkspaceContext

        ctx = WorkspaceContext.from_directory(hht_like_fixture)
        graph1, _ = ctx.get_graph()
        graph2, _ = ctx.get_graph(force_refresh=True)

        assert graph1 is not graph2  # Different objects

    def test_get_graph_contains_requirements(self, hht_like_fixture):
        """Test graph contains requirement nodes."""
        from elspais.mcp.context import WorkspaceContext
        from elspais.core.graph import NodeKind

        ctx = WorkspaceContext.from_directory(hht_like_fixture)
        graph, _ = ctx.get_graph()

        # Should have requirement nodes
        req_nodes = list(graph.nodes_by_kind(NodeKind.REQUIREMENT))
        assert len(req_nodes) > 0

        # Should be able to find REQ-p00001
        node = graph.find_by_id("REQ-p00001")
        assert node is not None
        assert node.kind == NodeKind.REQUIREMENT


class TestIsGraphStale:
    """Tests for is_graph_stale method."""

    def test_is_stale_no_graph(self, hht_like_fixture):
        """Test is_stale returns True when no graph exists."""
        from elspais.mcp.context import WorkspaceContext

        ctx = WorkspaceContext.from_directory(hht_like_fixture)

        assert ctx.is_graph_stale() is True

    def test_is_stale_fresh_graph(self, hht_like_fixture):
        """Test is_stale returns False for fresh graph."""
        from elspais.mcp.context import WorkspaceContext

        ctx = WorkspaceContext.from_directory(hht_like_fixture)
        ctx.get_graph()  # Build graph

        assert ctx.is_graph_stale() is False

    def test_is_stale_modified_file(self, tmp_path):
        """Test is_stale returns True when file modified."""
        from elspais.mcp.context import WorkspaceContext

        # Create minimal project
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        config_file = tmp_path / ".elspais.toml"
        config_file.write_text("""
[project]
name = "test"
""")

        req_file = spec_dir / "requirements.md"
        req_file.write_text("""
# REQ-p00001: Test Requirement

**Level**: PRD | **Status**: Active

The system SHALL work.

*End* *Test Requirement* | **Hash**: a1b2c3d4
""")

        ctx = WorkspaceContext.from_directory(tmp_path)
        ctx.get_graph()  # Build graph

        # Should not be stale initially
        assert ctx.is_graph_stale() is False

        # Wait a tiny bit and touch file
        time.sleep(0.01)
        req_file.write_text("""
# REQ-p00001: Test Requirement Modified

**Level**: PRD | **Status**: Active

The system SHALL work better.

*End* *Test Requirement Modified* | **Hash**: d4c3b2a1
""")

        # Now should be stale
        assert ctx.is_graph_stale() is True

    def test_is_stale_new_file(self, tmp_path):
        """Test is_stale returns True when new file added."""
        from elspais.mcp.context import WorkspaceContext

        # Create minimal project
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        config_file = tmp_path / ".elspais.toml"
        config_file.write_text("""
[project]
name = "test"
""")

        req_file = spec_dir / "requirements.md"
        req_file.write_text("""
# REQ-p00001: Test Requirement

**Level**: PRD | **Status**: Active

The system SHALL work.

*End* *Test Requirement* | **Hash**: a1b2c3d4
""")

        ctx = WorkspaceContext.from_directory(tmp_path)
        ctx.get_graph()  # Build graph

        # Should not be stale initially
        assert ctx.is_graph_stale() is False

        # Add new file
        new_file = spec_dir / "new-requirements.md"
        new_file.write_text("""
# REQ-p00002: Another Requirement

**Level**: PRD | **Status**: Active

Another system requirement.

*End* *Another Requirement* | **Hash**: 12345678
""")

        # Now should be stale
        assert ctx.is_graph_stale() is True

    def test_is_stale_deleted_file(self, tmp_path):
        """Test is_stale returns True when file deleted."""
        from elspais.mcp.context import WorkspaceContext

        # Create minimal project
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        config_file = tmp_path / ".elspais.toml"
        config_file.write_text("""
[project]
name = "test"
""")

        req_file = spec_dir / "requirements.md"
        req_file.write_text("""
# REQ-p00001: Test Requirement

**Level**: PRD | **Status**: Active

The system SHALL work.

*End* *Test Requirement* | **Hash**: a1b2c3d4
""")

        ctx = WorkspaceContext.from_directory(tmp_path)
        ctx.get_graph()  # Build graph

        # Should not be stale initially
        assert ctx.is_graph_stale() is False

        # Delete file
        req_file.unlink()

        # Now should be stale
        assert ctx.is_graph_stale() is True


class TestGetStaleFiles:
    """Tests for get_stale_files method."""

    def test_get_stale_files_empty_when_fresh(self, hht_like_fixture):
        """Test get_stale_files returns empty list for fresh graph."""
        from elspais.mcp.context import WorkspaceContext

        ctx = WorkspaceContext.from_directory(hht_like_fixture)
        ctx.get_graph()  # Build graph

        stale = ctx.get_stale_files()
        assert stale == []

    def test_get_stale_files_modified(self, tmp_path):
        """Test get_stale_files identifies modified file."""
        from elspais.mcp.context import WorkspaceContext

        # Create minimal project
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        config_file = tmp_path / ".elspais.toml"
        config_file.write_text("""
[project]
name = "test"
""")

        req_file = spec_dir / "requirements.md"
        req_file.write_text("""
# REQ-p00001: Test Requirement

**Level**: PRD | **Status**: Active

The system SHALL work.

*End* *Test Requirement* | **Hash**: a1b2c3d4
""")

        ctx = WorkspaceContext.from_directory(tmp_path)
        ctx.get_graph()  # Build graph

        # Modify file
        time.sleep(0.01)
        req_file.write_text("""
# REQ-p00001: Modified

**Level**: PRD | **Status**: Active

Modified text.

*End* *Modified* | **Hash**: d4c3b2a1
""")

        stale = ctx.get_stale_files()
        assert len(stale) == 1
        assert stale[0] == req_file.resolve()


class TestGetGraphBuiltAt:
    """Tests for get_graph_built_at method."""

    def test_built_at_none_initially(self, hht_like_fixture):
        """Test built_at is None before graph is built."""
        from elspais.mcp.context import WorkspaceContext

        ctx = WorkspaceContext.from_directory(hht_like_fixture)

        assert ctx.get_graph_built_at() is None

    def test_built_at_after_build(self, hht_like_fixture):
        """Test built_at returns timestamp after graph built."""
        from elspais.mcp.context import WorkspaceContext

        ctx = WorkspaceContext.from_directory(hht_like_fixture)
        before = time.time()
        ctx.get_graph()
        after = time.time()

        built_at = ctx.get_graph_built_at()
        assert built_at is not None
        assert before <= built_at <= after


class TestInvalidateCache:
    """Tests for invalidate_cache with graph state."""

    def test_invalidate_clears_graph(self, hht_like_fixture):
        """Test invalidate_cache clears graph state."""
        from elspais.mcp.context import WorkspaceContext

        ctx = WorkspaceContext.from_directory(hht_like_fixture)
        ctx.get_graph()  # Build graph

        assert ctx._graph_state is not None

        ctx.invalidate_cache()

        assert ctx._graph_state is None
        assert ctx._requirements_cache is None


class TestGraphAutoRefresh:
    """Tests for automatic graph refresh on stale detection."""

    def test_get_graph_refreshes_when_stale(self, tmp_path):
        """Test get_graph automatically refreshes when stale."""
        from elspais.mcp.context import WorkspaceContext

        # Create minimal project
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        config_file = tmp_path / ".elspais.toml"
        config_file.write_text("""
[project]
name = "test"
""")

        req_file = spec_dir / "requirements.md"
        req_file.write_text("""
# REQ-p00001: Test Requirement

**Level**: PRD | **Status**: Active

The system SHALL work.

*End* *Test Requirement* | **Hash**: a1b2c3d4
""")

        ctx = WorkspaceContext.from_directory(tmp_path)
        graph1, _ = ctx.get_graph()

        # Verify initial graph
        node = graph1.find_by_id("REQ-p00001")
        assert node is not None
        assert "Test Requirement" in node.label

        # Modify file
        time.sleep(0.01)
        req_file.write_text("""
# REQ-p00001: Updated Requirement

**Level**: PRD | **Status**: Active

Updated text.

*End* *Updated Requirement* | **Hash**: d4c3b2a1
""")

        # Get graph again - should detect staleness and refresh
        graph2, _ = ctx.get_graph()

        # Should be a new graph object
        assert graph1 is not graph2

        # Should have updated content
        node = graph2.find_by_id("REQ-p00001")
        assert node is not None
        assert "Updated Requirement" in node.label
