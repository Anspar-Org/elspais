"""
Tests for elspais.mcp.git_safety module.
"""

import pytest
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch


class TestGitStatus:
    """Tests for GitStatus dataclass."""

    def test_git_status_defaults(self):
        """Test GitStatus default values."""
        from elspais.mcp.git_safety import GitStatus

        status = GitStatus()
        assert status.has_uncommitted is False
        assert status.staged_files == []
        assert status.modified_files == []
        assert status.untracked_files == []
        assert status.current_branch is None
        assert status.error is None

    def test_git_status_with_error(self):
        """Test GitStatus with error."""
        from elspais.mcp.git_safety import GitStatus

        status = GitStatus(error="Not a git repository")
        assert status.error == "Not a git repository"


class TestSafetyBranchResult:
    """Tests for SafetyBranchResult dataclass."""

    def test_safety_branch_success(self):
        """Test successful branch result."""
        from elspais.mcp.git_safety import SafetyBranchResult

        result = SafetyBranchResult(
            success=True,
            branch_name="elspais-safety/test-20240125",
            message="Created branch",
        )
        assert result.success is True
        assert result.branch_name is not None

    def test_safety_branch_with_stash(self):
        """Test branch result with stash."""
        from elspais.mcp.git_safety import SafetyBranchResult

        result = SafetyBranchResult(
            success=True,
            branch_name="elspais-safety/test-20240125",
            message="Created branch",
            stashed=True,
            stash_name="elspais-test-20240125",
        )
        assert result.stashed is True
        assert result.stash_name is not None


class TestGitSafetyManager:
    """Tests for GitSafetyManager."""

    @pytest.fixture
    def manager(self, tmp_path):
        """Create a GitSafetyManager for testing."""
        from elspais.mcp.git_safety import GitSafetyManager

        return GitSafetyManager(tmp_path)

    def test_get_status_not_git_repo(self, manager):
        """Test get_status on non-git directory."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=128,
                stdout="",
                stderr="fatal: not a git repository",
            )

            status = manager.get_status()
            assert status.error is not None
            assert "Not a git repository" in status.error

    def test_get_status_clean(self, manager):
        """Test get_status with clean repo."""
        with patch("subprocess.run") as mock_run:
            # First call: get current branch
            # Second call: get status
            mock_run.side_effect = [
                Mock(returncode=0, stdout="main\n", stderr=""),
                Mock(returncode=0, stdout="", stderr=""),
            ]

            status = manager.get_status()
            assert status.error is None
            assert status.current_branch == "main"
            assert status.has_uncommitted is False

    def test_get_status_with_changes(self, manager):
        """Test get_status with uncommitted changes."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                Mock(returncode=0, stdout="feature\n", stderr=""),
                Mock(returncode=0, stdout="M  staged.txt\n M modified.txt\n?? untracked.txt\n", stderr=""),
            ]

            status = manager.get_status()
            assert status.has_uncommitted is True
            assert "staged.txt" in status.staged_files
            assert "modified.txt" in status.modified_files
            assert "untracked.txt" in status.untracked_files

    def test_create_safety_branch_success(self, manager):
        """Test creating a safety branch."""
        with patch("subprocess.run") as mock_run:
            # Status call (branch + status)
            # Branch creation call
            mock_run.side_effect = [
                Mock(returncode=0, stdout="main\n", stderr=""),
                Mock(returncode=0, stdout="", stderr=""),
                Mock(returncode=0, stdout="", stderr=""),
            ]

            result = manager.create_safety_branch("ai-transform", ["REQ-p00001"])

            assert result.success is True
            assert result.branch_name is not None
            assert "elspais-safety" in result.branch_name
            assert "ai-transform" in result.branch_name

    def test_create_safety_branch_with_dirty_repo(self, manager):
        """Test creating a branch when repo has changes."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                Mock(returncode=0, stdout="main\n", stderr=""),
                Mock(returncode=0, stdout="M  dirty.txt\n", stderr=""),
                Mock(returncode=0, stdout="", stderr=""),  # stash
                Mock(returncode=0, stdout="", stderr=""),  # branch
            ]

            result = manager.create_safety_branch(
                "ai-transform",
                stash_if_dirty=True,
            )

            assert result.success is True
            assert result.stashed is True

    def test_create_safety_branch_dirty_no_stash(self, manager):
        """Test branch creation fails when dirty and stash disabled."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                Mock(returncode=0, stdout="main\n", stderr=""),
                Mock(returncode=0, stdout="M  dirty.txt\n", stderr=""),
            ]

            result = manager.create_safety_branch(
                "ai-transform",
                stash_if_dirty=False,
            )

            assert result.success is False
            assert "Uncommitted changes" in result.message

    def test_restore_from_branch_success(self, manager):
        """Test restoring from a safety branch."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                Mock(returncode=0, stdout="abc123\n", stderr=""),  # verify branch
                Mock(returncode=0, stdout="", stderr=""),  # reset
                Mock(returncode=0, stdout="", stderr=""),  # stash list (for _restore_matching_stash)
            ]

            success, message = manager.restore_from_branch(
                "elspais-safety/test-branch"
            )

            assert success is True

    def test_restore_from_branch_not_found(self, manager):
        """Test restoring from non-existent branch."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=128,
                stdout="",
                stderr="fatal: not a valid object",
            )

            success, message = manager.restore_from_branch(
                "elspais-safety/nonexistent"
            )

            assert success is False
            assert "not found" in message

    def test_list_safety_branches(self, manager):
        """Test listing safety branches."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="  elspais-safety/branch1\n  elspais-safety/branch2\n",
                stderr="",
            )

            branches = manager.list_safety_branches()

            assert len(branches) == 2
            assert "elspais-safety/branch1" in branches
            assert "elspais-safety/branch2" in branches

    def test_delete_safety_branch_success(self, manager):
        """Test deleting a safety branch."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

            success, message = manager.delete_safety_branch(
                "elspais-safety/old-branch"
            )

            assert success is True

    def test_delete_safety_branch_wrong_prefix(self, manager):
        """Test that non-safety branches can't be deleted."""
        success, message = manager.delete_safety_branch("main")

        assert success is False
        assert "Not a safety branch" in message

    def test_branch_prefix(self, manager):
        """Test the branch prefix constant."""
        from elspais.mcp.git_safety import GitSafetyManager

        assert GitSafetyManager.BRANCH_PREFIX == "elspais-safety"
