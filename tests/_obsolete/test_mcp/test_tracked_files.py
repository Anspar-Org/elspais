"""
Tests for TrackedFile registry in elspais.mcp.context.

Tests file-to-node mapping for incremental graph updates.
"""

import time
from pathlib import Path

import pytest


class TestTrackedFileDataclass:
    """Tests for TrackedFile dataclass."""

    def test_tracked_file_creation(self):
        """Test creating TrackedFile with all fields."""
        from elspais.mcp.context import TrackedFile

        path = Path("/some/path.md")
        tf = TrackedFile(path=path, mtime=123.456, node_ids=["REQ-p00001", "REQ-p00001-A"])

        assert tf.path == path
        assert tf.mtime == 123.456
        assert tf.node_ids == ["REQ-p00001", "REQ-p00001-A"]

    def test_tracked_file_default_node_ids(self):
        """Test TrackedFile defaults to empty node_ids list."""
        from elspais.mcp.context import TrackedFile

        path = Path("/some/path.md")
        tf = TrackedFile(path=path, mtime=123.456)

        assert tf.node_ids == []


class TestGraphStateTrackedFiles:
    """Tests for GraphState tracked_files field."""

    def test_graph_state_has_tracked_files(self, hht_like_fixture):
        """Test GraphState contains tracked_files after build."""
        from elspais.mcp.context import WorkspaceContext, TrackedFile

        ctx = WorkspaceContext.from_directory(hht_like_fixture)
        graph, _ = ctx.get_graph()

        # Should have tracked files
        assert ctx._graph_state is not None
        assert len(ctx._graph_state.tracked_files) > 0

        # Each entry should be a TrackedFile
        for path, tf in ctx._graph_state.tracked_files.items():
            assert isinstance(path, Path)
            assert isinstance(tf, TrackedFile)
            assert tf.path == path
            assert tf.mtime > 0

    def test_graph_state_file_mtimes_property(self, hht_like_fixture):
        """Test file_mtimes property provides backward compatibility."""
        from elspais.mcp.context import WorkspaceContext

        ctx = WorkspaceContext.from_directory(hht_like_fixture)
        graph, _ = ctx.get_graph()

        # file_mtimes property should return Dict[Path, float]
        file_mtimes = ctx._graph_state.file_mtimes
        assert isinstance(file_mtimes, dict)

        for path, mtime in file_mtimes.items():
            assert isinstance(path, Path)
            assert isinstance(mtime, float)
            # Should match tracked_files
            assert mtime == ctx._graph_state.tracked_files[path].mtime


class TestTrackedFileNodeMapping:
    """Tests for file-to-node mapping."""

    def test_tracked_files_contain_node_ids(self, hht_like_fixture):
        """Test TrackedFile entries have node_ids populated."""
        from elspais.mcp.context import WorkspaceContext

        ctx = WorkspaceContext.from_directory(hht_like_fixture)
        graph, _ = ctx.get_graph()

        # At least one file should have nodes
        has_nodes = False
        for tf in ctx._graph_state.tracked_files.values():
            if tf.node_ids:
                has_nodes = True
                break

        assert has_nodes, "No tracked files have node_ids"

    def test_node_ids_match_graph_nodes(self, hht_like_fixture):
        """Test that node_ids in tracked files actually exist in graph."""
        from elspais.mcp.context import WorkspaceContext

        ctx = WorkspaceContext.from_directory(hht_like_fixture)
        graph, _ = ctx.get_graph()

        for tf in ctx._graph_state.tracked_files.values():
            for node_id in tf.node_ids:
                node = graph.find_by_id(node_id)
                assert node is not None, f"Node {node_id} from {tf.path} not in graph"

    def test_node_ids_source_matches_file(self, hht_like_fixture):
        """Test that node_ids are correctly attributed to their source file."""
        from elspais.mcp.context import WorkspaceContext

        ctx = WorkspaceContext.from_directory(hht_like_fixture)
        graph, _ = ctx.get_graph()

        for tracked_path, tf in ctx._graph_state.tracked_files.items():
            for node_id in tf.node_ids:
                node = graph.find_by_id(node_id)
                if node and node.source and node.source.path:
                    # Convert repo-relative path to absolute
                    node_abs_path = (ctx.working_dir / node.source.path).resolve()
                    assert node_abs_path == tracked_path, (
                        f"Node {node_id} source {node_abs_path} != tracked {tracked_path}"
                    )

    def test_all_nodes_tracked(self, hht_like_fixture):
        """Test that all graph nodes with source paths are tracked."""
        from elspais.mcp.context import WorkspaceContext

        ctx = WorkspaceContext.from_directory(hht_like_fixture)
        graph, _ = ctx.get_graph()

        # Collect all node_ids from tracked files
        tracked_node_ids = set()
        for tf in ctx._graph_state.tracked_files.values():
            tracked_node_ids.update(tf.node_ids)

        # Check all nodes with sources are tracked
        for node in graph.all_nodes():
            if node.source and node.source.path:
                abs_path = (ctx.working_dir / node.source.path).resolve()
                # Node should be tracked if its file is tracked
                if abs_path in ctx._graph_state.tracked_files:
                    assert node.id in tracked_node_ids, f"Node {node.id} not tracked"


class TestGetTrackedFiles:
    """Tests for get_tracked_files method."""

    def test_get_tracked_files_returns_dict(self, hht_like_fixture):
        """Test get_tracked_files returns TrackedFile dict."""
        from elspais.mcp.context import WorkspaceContext, TrackedFile

        ctx = WorkspaceContext.from_directory(hht_like_fixture)
        ctx.get_graph()  # Build graph first

        tracked = ctx.get_tracked_files()

        assert isinstance(tracked, dict)
        for path, tf in tracked.items():
            assert isinstance(path, Path)
            assert isinstance(tf, TrackedFile)

    def test_get_tracked_files_empty_before_build(self, hht_like_fixture):
        """Test get_tracked_files returns empty dict before graph build."""
        from elspais.mcp.context import WorkspaceContext

        ctx = WorkspaceContext.from_directory(hht_like_fixture)

        # Should return empty dict, not None
        tracked = ctx.get_tracked_files()
        assert tracked == {}


class TestGetNodesForFile:
    """Tests for get_nodes_for_file method."""

    def test_get_nodes_for_existing_file(self, hht_like_fixture):
        """Test get_nodes_for_file returns node IDs for tracked file."""
        from elspais.mcp.context import WorkspaceContext

        ctx = WorkspaceContext.from_directory(hht_like_fixture)
        ctx.get_graph()

        # Find a file with nodes
        for path, tf in ctx._graph_state.tracked_files.items():
            if tf.node_ids:
                nodes = ctx.get_nodes_for_file(path)
                assert nodes == tf.node_ids
                break

    def test_get_nodes_for_nonexistent_file(self, hht_like_fixture):
        """Test get_nodes_for_file returns empty list for unknown file."""
        from elspais.mcp.context import WorkspaceContext

        ctx = WorkspaceContext.from_directory(hht_like_fixture)
        ctx.get_graph()

        nodes = ctx.get_nodes_for_file(Path("/nonexistent/path.md"))
        assert nodes == []

    def test_get_nodes_for_file_before_build(self, hht_like_fixture):
        """Test get_nodes_for_file returns empty list before graph build."""
        from elspais.mcp.context import WorkspaceContext

        ctx = WorkspaceContext.from_directory(hht_like_fixture)

        nodes = ctx.get_nodes_for_file(hht_like_fixture / "spec" / "prd.md")
        assert nodes == []


class TestStaleTrackedFiles:
    """Tests for get_stale_tracked_files method."""

    def test_get_stale_tracked_files_empty_when_fresh(self, hht_like_fixture):
        """Test get_stale_tracked_files returns empty list for fresh graph."""
        from elspais.mcp.context import WorkspaceContext

        ctx = WorkspaceContext.from_directory(hht_like_fixture)
        ctx.get_graph()

        stale = ctx.get_stale_tracked_files()
        assert stale == []

    def test_get_stale_tracked_files_returns_modified(self, hht_like_fixture, tmp_path):
        """Test get_stale_tracked_files returns TrackedFile for modified file."""
        from elspais.mcp.context import WorkspaceContext, TrackedFile
        import shutil

        # Copy fixture to tmp_path for modification
        test_dir = tmp_path / "test_repo"
        shutil.copytree(hht_like_fixture, test_dir)

        ctx = WorkspaceContext.from_directory(test_dir)
        ctx.get_graph()

        # Find a file to modify
        spec_file = None
        for path, tf in ctx._graph_state.tracked_files.items():
            if tf.node_ids:
                spec_file = path
                break

        if spec_file is None:
            pytest.skip("No spec files with nodes found")

        # Wait and modify the file
        time.sleep(0.01)
        spec_file.write_text(spec_file.read_text() + "\n<!-- modified -->")

        # Should now be stale
        stale = ctx.get_stale_tracked_files()
        assert len(stale) > 0
        assert any(tf.path == spec_file for tf in stale)
        # Should be TrackedFile instances
        assert all(isinstance(tf, TrackedFile) for tf in stale)

    def test_get_stale_tracked_files_includes_node_ids(self, hht_like_fixture, tmp_path):
        """Test stale TrackedFile includes the node_ids from that file."""
        from elspais.mcp.context import WorkspaceContext
        import shutil

        # Copy fixture to tmp_path for modification
        test_dir = tmp_path / "test_repo"
        shutil.copytree(hht_like_fixture, test_dir)

        ctx = WorkspaceContext.from_directory(test_dir)
        ctx.get_graph()

        # Find a file with nodes to modify
        spec_file = None
        expected_node_ids = []
        for path, tf in ctx._graph_state.tracked_files.items():
            if tf.node_ids:
                spec_file = path
                expected_node_ids = tf.node_ids.copy()
                break

        if not expected_node_ids:
            pytest.skip("No spec files with nodes found")

        # Wait and modify the file
        time.sleep(0.01)
        spec_file.write_text(spec_file.read_text() + "\n<!-- modified -->")

        # Get stale files
        stale = ctx.get_stale_tracked_files()
        stale_tf = next(tf for tf in stale if tf.path == spec_file)

        # Should still have the node_ids from before modification
        assert stale_tf.node_ids == expected_node_ids

    def test_get_stale_tracked_files_before_build(self, hht_like_fixture):
        """Test get_stale_tracked_files returns empty list before build."""
        from elspais.mcp.context import WorkspaceContext

        ctx = WorkspaceContext.from_directory(hht_like_fixture)

        stale = ctx.get_stale_tracked_files()
        assert stale == []


class TestIncrementalUpdateScenarios:
    """Integration tests for incremental update scenarios."""

    def test_single_file_change_identifies_affected_nodes(self, hht_like_fixture, tmp_path):
        """Test that changing one file identifies only nodes from that file."""
        from elspais.mcp.context import WorkspaceContext
        import shutil

        # Copy fixture to tmp_path
        test_dir = tmp_path / "test_repo"
        shutil.copytree(hht_like_fixture, test_dir)

        ctx = WorkspaceContext.from_directory(test_dir)
        ctx.get_graph()

        # Get all node_ids before
        all_node_ids = set()
        for tf in ctx._graph_state.tracked_files.values():
            all_node_ids.update(tf.node_ids)

        # Find a file to modify
        modified_file = None
        modified_node_ids = set()
        for path, tf in ctx._graph_state.tracked_files.items():
            if tf.node_ids:
                modified_file = path
                modified_node_ids = set(tf.node_ids)
                break

        if not modified_node_ids:
            pytest.skip("No spec files with nodes found")

        # Modify the file
        time.sleep(0.01)
        modified_file.write_text(modified_file.read_text() + "\n<!-- modified -->")

        # Get affected nodes
        stale = ctx.get_stale_tracked_files()
        affected_node_ids = set()
        for tf in stale:
            affected_node_ids.update(tf.node_ids)

        # Should only affect nodes from the modified file
        assert affected_node_ids == modified_node_ids
        # Should not affect all nodes
        assert affected_node_ids != all_node_ids or len(all_node_ids) == len(modified_node_ids)
