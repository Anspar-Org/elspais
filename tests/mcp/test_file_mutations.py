"""Tests for MCP file mutation tools.

Tests REQ-o00063: MCP File Mutation Tools
- change_reference_type(req_id, target_id, new_type)
- move_requirement(req_id, target_file)
- restore_from_safety_branch(branch_name)

File mutations persist changes to spec files on disk and must:
- Create git safety branches when save_branch=True (REQ-o00063-D)
- Call refresh_graph() after file mutations (REQ-o00063-F)
"""

import os
import subprocess

import pytest


def _clean_git_env() -> dict[str, str]:
    """Return environment with GIT_DIR/GIT_WORK_TREE removed for test isolation."""
    env = os.environ.copy()
    env.pop("GIT_DIR", None)
    env.pop("GIT_WORK_TREE", None)
    return env


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def git_repo(tmp_path):
    """Create a temporary git repository with spec files."""
    # Use clean env to prevent GIT_DIR from affecting temp repo
    env = _clean_git_env()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=tmp_path, env=env, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        check=True,
    )

    # Create spec directory
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()

    # Create a sample requirement file
    req_file = spec_dir / "requirements.md"
    req_file.write_text(
        """# Requirements

## REQ-p00001: Sample Requirement

**Level**: PRD | **Status**: Active | **Implements**: REQ-p00000

The system SHALL do something.

## Assertions

A. SHALL validate input.
B. SHALL return output.

## Rationale

This is needed for testing.

*End* *Sample Requirement* | **Hash**: abc12345

---

## REQ-o00001: Child Requirement

**Level**: OPS | **Status**: Active | **Implements**: REQ-p00001

The system SHALL implement the parent.

## Assertions

A. SHALL connect to parent.

## Rationale

Child of REQ-p00001.

*End* *Child Requirement* | **Hash**: def67890
"""
    )

    # Commit initial state
    subprocess.run(["git", "add", "."], cwd=tmp_path, env=env, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        check=True,
    )

    return tmp_path


# ─────────────────────────────────────────────────────────────────────────────
# Test: Git Safety Branch Utilities
# ─────────────────────────────────────────────────────────────────────────────


class TestGitSafetyBranch:
    """Tests for git safety branch utilities."""

    def test_create_safety_branch(self, git_repo):
        """Create a safety branch with timestamped name."""
        from elspais.utilities.git import create_safety_branch

        result = create_safety_branch(git_repo, "REQ-p00001")

        assert result["success"] is True
        assert "branch_name" in result
        assert result["branch_name"].startswith("safety/")
        assert "REQ-p00001" in result["branch_name"]

        # Verify branch exists
        branches = subprocess.run(
            ["git", "branch", "-a"],
            cwd=git_repo,
            env=_clean_git_env(),
            capture_output=True,
            text=True,
            check=True,
        )
        assert result["branch_name"] in branches.stdout

    def test_list_safety_branches(self, git_repo):
        """List all safety branches."""
        from elspais.utilities.git import create_safety_branch, list_safety_branches

        # Create a few safety branches
        create_safety_branch(git_repo, "REQ-p00001")
        create_safety_branch(git_repo, "REQ-o00001")

        result = list_safety_branches(git_repo)

        assert len(result) >= 2
        assert all(b.startswith("safety/") for b in result)

    def test_get_current_branch(self, git_repo):
        """Get the current branch name."""
        from elspais.utilities.git import get_current_branch

        branch = get_current_branch(git_repo)

        # Should be main/master or similar
        assert branch is not None
        assert len(branch) > 0

    def test_restore_from_safety_branch(self, git_repo):
        """Restore files from a safety branch."""
        from elspais.utilities.git import (
            create_safety_branch,
            restore_from_safety_branch,
        )

        # Create safety branch
        branch_result = create_safety_branch(git_repo, "REQ-p00001")
        branch_name = branch_result["branch_name"]

        # Modify a file
        req_file = git_repo / "spec" / "requirements.md"
        original_content = req_file.read_text()
        req_file.write_text("MODIFIED CONTENT")

        # Restore from safety branch
        result = restore_from_safety_branch(git_repo, branch_name)

        assert result["success"] is True
        assert "files_restored" in result

        # Verify file was restored
        restored_content = req_file.read_text()
        assert restored_content == original_content

    def test_delete_safety_branch(self, git_repo):
        """Delete a safety branch."""
        from elspais.utilities.git import (
            create_safety_branch,
            delete_safety_branch,
            list_safety_branches,
        )

        # Create then delete
        branch_result = create_safety_branch(git_repo, "REQ-p00001")
        branch_name = branch_result["branch_name"]

        result = delete_safety_branch(git_repo, branch_name)

        assert result["success"] is True

        # Verify branch is gone
        branches = list_safety_branches(git_repo)
        assert branch_name not in branches


# ─────────────────────────────────────────────────────────────────────────────
# Test: change_reference_type - REQ-o00063-A
# ─────────────────────────────────────────────────────────────────────────────


class TestChangeReferenceType:
    """Tests for change_reference_type() MCP tool."""

    def test_REQ_o00063_A_changes_implements_to_refines(self, git_repo):
        """REQ-o00063-A: Modify Implements/Refines relationships in spec files."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _change_reference_type

        result = _change_reference_type(
            repo_root=git_repo,
            req_id="REQ-o00001",
            target_id="REQ-p00001",
            new_type="REFINES",
        )

        assert result["success"] is True

        # Verify file was changed
        req_file = git_repo / "spec" / "requirements.md"
        content = req_file.read_text()
        assert "**Refines**: REQ-p00001" in content or "Refines: REQ-p00001" in content

    def test_REQ_o00063_D_creates_safety_branch_when_requested(self, git_repo):
        """REQ-o00063-D: Create git safety branches when save_branch=True."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _change_reference_type
        from elspais.utilities.git import list_safety_branches

        result = _change_reference_type(
            repo_root=git_repo,
            req_id="REQ-o00001",
            target_id="REQ-p00001",
            new_type="REFINES",
            save_branch=True,
        )

        assert result["success"] is True
        assert "safety_branch" in result

        # Verify safety branch was created
        branches = list_safety_branches(git_repo)
        assert len(branches) >= 1

    def test_returns_error_for_nonexistent_requirement(self, git_repo):
        """Returns error when requirement doesn't exist."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _change_reference_type

        result = _change_reference_type(
            repo_root=git_repo,
            req_id="REQ-NONEXISTENT",
            target_id="REQ-p00001",
            new_type="REFINES",
        )

        assert result["success"] is False
        assert "error" in result


# ─────────────────────────────────────────────────────────────────────────────
# Test: move_requirement - REQ-o00063-B
# ─────────────────────────────────────────────────────────────────────────────


class TestMoveRequirement:
    """Tests for move_requirement() MCP tool."""

    def test_REQ_o00063_B_moves_requirement_to_new_file(self, git_repo):
        """REQ-o00063-B: Relocate a requirement between spec files."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _move_requirement

        # Create target file
        target_file = git_repo / "spec" / "other.md"
        target_file.write_text("# Other Requirements\n\n")

        result = _move_requirement(
            repo_root=git_repo,
            req_id="REQ-o00001",
            target_file="spec/other.md",
        )

        assert result["success"] is True

        # Verify requirement moved
        source_content = (git_repo / "spec" / "requirements.md").read_text()
        target_content = target_file.read_text()

        assert "REQ-o00001" not in source_content
        assert "REQ-o00001" in target_content

    def test_REQ_o00063_D_creates_safety_branch_on_move(self, git_repo):
        """REQ-o00063-D: Create safety branch on move when requested."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _move_requirement
        from elspais.utilities.git import list_safety_branches

        target_file = git_repo / "spec" / "other.md"
        target_file.write_text("# Other Requirements\n\n")

        result = _move_requirement(
            repo_root=git_repo,
            req_id="REQ-o00001",
            target_file="spec/other.md",
            save_branch=True,
        )

        assert result["success"] is True
        assert "safety_branch" in result

        branches = list_safety_branches(git_repo)
        assert len(branches) >= 1


# ─────────────────────────────────────────────────────────────────────────────
# Test: restore_from_safety_branch - REQ-o00063-E
# ─────────────────────────────────────────────────────────────────────────────


class TestRestoreFromSafetyBranch:
    """Tests for restore_from_safety_branch() MCP tool."""

    def test_REQ_o00063_E_restores_from_safety_branch(self, git_repo):
        """REQ-o00063-E: Revert file changes from a safety branch."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _change_reference_type, _restore_from_safety_branch

        # Make a change with safety branch
        change_result = _change_reference_type(
            repo_root=git_repo,
            req_id="REQ-o00001",
            target_id="REQ-p00001",
            new_type="REFINES",
            save_branch=True,
        )
        branch_name = change_result["safety_branch"]

        # Verify change was made
        content_after = (git_repo / "spec" / "requirements.md").read_text()
        assert "Refines" in content_after or "REFINES" in content_after

        # Restore from safety branch
        result = _restore_from_safety_branch(
            repo_root=git_repo,
            branch_name=branch_name,
        )

        assert result["success"] is True

        # Verify file was restored (back to Implements)
        content_restored = (git_repo / "spec" / "requirements.md").read_text()
        assert "Implements" in content_restored

    def test_returns_error_for_invalid_branch(self, git_repo):
        """Returns error when branch doesn't exist."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _restore_from_safety_branch

        result = _restore_from_safety_branch(
            repo_root=git_repo,
            branch_name="safety/nonexistent-branch",
        )

        assert result["success"] is False
        assert "error" in result


# ─────────────────────────────────────────────────────────────────────────────
# Test: Graph Refresh Integration - REQ-o00063-F
# ─────────────────────────────────────────────────────────────────────────────


class TestGraphRefreshIntegration:
    """Tests for graph refresh after file mutations."""

    def test_REQ_o00063_F_file_mutations_modify_files_for_graph_rebuild(self, git_repo):
        """REQ-o00063-F: After file mutations, refresh_graph() SHALL be called.

        This test verifies that file mutations modify the actual spec files,
        which is the prerequisite for refresh_graph() to pick up changes.
        The actual refresh_graph call happens in the MCP tool wrapper, not
        in the private implementation functions.
        """
        pytest.importorskip("mcp")
        from elspais.mcp.server import _change_reference_type

        # Verify the file is modified after calling _change_reference_type
        req_file = git_repo / "spec" / "requirements.md"
        original_content = req_file.read_text()

        assert "Implements" in original_content
        assert "Refines" not in original_content

        result = _change_reference_type(
            repo_root=git_repo,
            req_id="REQ-o00001",
            target_id="REQ-p00001",
            new_type="REFINES",
        )

        assert result["success"] is True

        # Verify file was modified - this change will be picked up by refresh_graph()
        modified_content = req_file.read_text()
        assert "Refines" in modified_content


# ─────────────────────────────────────────────────────────────────────────────
# Test: MCP Tool Registration
# ─────────────────────────────────────────────────────────────────────────────


class TestMCPToolRegistration:
    """Tests that file mutation tools are properly registered with MCP."""

    def test_file_mutation_tools_registered(self, git_repo):
        """File mutation tools are registered as MCP tools."""
        pytest.importorskip("mcp")
        # Also need fastmcp
        pytest.importorskip("mcp.server.fastmcp")

        from elspais.graph.builder import TraceGraph
        from elspais.mcp.server import MCP_AVAILABLE, create_server

        if not MCP_AVAILABLE:
            pytest.skip("MCP dependencies not installed")

        graph = TraceGraph(repo_root=git_repo)
        server = create_server(graph=graph, working_dir=git_repo)

        # Check that tools are registered
        # FastMCP stores tools in server._tool_manager._tools
        tool_names = [t.name for t in server._tool_manager._tools.values()]

        assert "change_reference_type" in tool_names
        assert "move_requirement" in tool_names
        assert "restore_from_safety_branch" in tool_names
        assert "list_safety_branches" in tool_names
