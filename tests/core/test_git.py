"""Tests for Git Integration."""

import pytest
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

from elspais.utilities.git import (
    GitChangeInfo,
    MovedRequirement,
    get_repo_root,
    get_modified_files,
    get_changed_vs_branch,
    detect_moved_requirements,
    get_git_changes,
    filter_spec_files,
)


class TestGitChangeInfo:
    """Tests for GitChangeInfo dataclass."""

    def test_create_empty(self):
        """Empty GitChangeInfo has empty sets."""
        info = GitChangeInfo()

        assert info.modified_files == set()
        assert info.untracked_files == set()
        assert info.branch_changed_files == set()
        assert info.committed_req_locations == {}

    def test_all_changed_files(self):
        """all_changed_files returns union of all file sets."""
        info = GitChangeInfo(
            modified_files={"a.md"},
            untracked_files={"b.md"},
            branch_changed_files={"c.md"},
        )

        assert info.all_changed_files == {"a.md", "b.md", "c.md"}

    def test_uncommitted_files(self):
        """uncommitted_files returns modified and untracked."""
        info = GitChangeInfo(
            modified_files={"a.md"},
            untracked_files={"b.md"},
            branch_changed_files={"c.md"},
        )

        assert info.uncommitted_files == {"a.md", "b.md"}


class TestMovedRequirement:
    """Tests for MovedRequirement dataclass."""

    def test_create(self):
        """Create MovedRequirement with all fields."""
        moved = MovedRequirement(
            req_id="d00001",
            old_path="spec/old.md",
            new_path="spec/new.md",
        )

        assert moved.req_id == "d00001"
        assert moved.old_path == "spec/old.md"
        assert moved.new_path == "spec/new.md"


class TestGetRepoRoot:
    """Tests for get_repo_root function."""

    def test_returns_path_in_git_repo(self):
        """Returns Path object when in a git repo."""
        # We're running in a git repo
        result = get_repo_root()

        assert result is not None
        assert isinstance(result, Path)
        assert (result / ".git").exists()

    def test_returns_none_when_not_in_repo(self, tmp_path):
        """Returns None when not in a git repository."""
        result = get_repo_root(tmp_path)

        assert result is None


class TestGetModifiedFiles:
    """Tests for get_modified_files function."""

    def test_returns_tuples(self):
        """Returns tuple of two sets."""
        # Use current repo
        repo_root = get_repo_root()
        if repo_root is None:
            pytest.skip("Not in a git repository")

        modified, untracked = get_modified_files(repo_root)

        assert isinstance(modified, set)
        assert isinstance(untracked, set)

    @patch("elspais.utilities.git.subprocess.run")
    def test_parses_porcelain_output(self, mock_run):
        """Correctly parses git status porcelain output."""
        mock_run.return_value = MagicMock(
            stdout=" M modified.md\n?? untracked.md\nA  added.md\n",
            returncode=0,
        )

        modified, untracked = get_modified_files(Path("/fake"))

        assert "modified.md" in modified
        assert "added.md" in modified
        assert "untracked.md" in untracked
        assert "untracked.md" not in modified

    @patch("elspais.utilities.git.subprocess.run")
    def test_handles_renames(self, mock_run):
        """Handles rename format: 'old.md -> new.md'."""
        mock_run.return_value = MagicMock(
            stdout="R  old.md -> new.md\n",
            returncode=0,
        )

        modified, untracked = get_modified_files(Path("/fake"))

        assert "new.md" in modified
        assert "old.md" not in modified


class TestGetChangedVsBranch:
    """Tests for get_changed_vs_branch function."""

    @patch("elspais.utilities.git.subprocess.run")
    def test_returns_changed_files(self, mock_run):
        """Returns set of files changed vs branch."""
        mock_run.return_value = MagicMock(
            stdout="spec/prd.md\nspec/ops.md\n",
            returncode=0,
        )

        changed = get_changed_vs_branch(Path("/fake"), "main")

        assert changed == {"spec/prd.md", "spec/ops.md"}

    @patch("elspais.utilities.git.subprocess.run")
    def test_tries_origin_fallback(self, mock_run):
        """Falls back to origin/main if main doesn't exist."""
        # First call fails (local main doesn't exist)
        # Second call succeeds (origin/main exists)
        mock_run.side_effect = [
            subprocess.CalledProcessError(1, "git"),
            MagicMock(stdout="spec/file.md\n", returncode=0),
        ]

        changed = get_changed_vs_branch(Path("/fake"), "main")

        assert changed == {"spec/file.md"}
        assert mock_run.call_count == 2


class TestDetectMovedRequirements:
    """Tests for detect_moved_requirements function."""

    def test_detects_moved_requirement(self):
        """Detects when a requirement moved files."""
        committed = {"d00001": "spec/old.md"}
        current = {"d00001": "spec/new.md"}

        moved = detect_moved_requirements(committed, current)

        assert len(moved) == 1
        assert moved[0].req_id == "d00001"
        assert moved[0].old_path == "spec/old.md"
        assert moved[0].new_path == "spec/new.md"

    def test_no_move_when_same_location(self):
        """Returns empty when requirement is in same location."""
        committed = {"d00001": "spec/file.md"}
        current = {"d00001": "spec/file.md"}

        moved = detect_moved_requirements(committed, current)

        assert moved == []

    def test_ignores_new_requirements(self):
        """Ignores requirements that exist only in current state."""
        committed = {}
        current = {"d00001": "spec/new.md"}

        moved = detect_moved_requirements(committed, current)

        assert moved == []

    def test_ignores_deleted_requirements(self):
        """Ignores requirements that exist only in committed state."""
        committed = {"d00001": "spec/old.md"}
        current = {}

        moved = detect_moved_requirements(committed, current)

        assert moved == []


class TestFilterSpecFiles:
    """Tests for filter_spec_files function."""

    def test_filters_to_spec_directory(self):
        """Only includes files in spec directory."""
        files = {"spec/prd.md", "src/main.py", "README.md", "spec/ops.md"}

        result = filter_spec_files(files)

        assert result == {"spec/prd.md", "spec/ops.md"}

    def test_only_includes_markdown(self):
        """Only includes .md files."""
        files = {"spec/prd.md", "spec/config.toml", "spec/data.json"}

        result = filter_spec_files(files)

        assert result == {"spec/prd.md"}

    def test_custom_spec_dir(self):
        """Supports custom spec directory."""
        files = {"specs/prd.md", "spec/ops.md", "docs/readme.md"}

        result = filter_spec_files(files, spec_dir="specs")

        assert result == {"specs/prd.md"}


class TestGetGitChanges:
    """Tests for get_git_changes function."""

    def test_returns_git_change_info(self):
        """Returns GitChangeInfo object."""
        repo_root = get_repo_root()
        if repo_root is None:
            pytest.skip("Not in a git repository")

        result = get_git_changes(repo_root)

        assert isinstance(result, GitChangeInfo)

    def test_returns_empty_when_not_in_repo(self, tmp_path):
        """Returns empty GitChangeInfo when not in a git repo."""
        result = get_git_changes(tmp_path)

        assert result.modified_files == set()
        assert result.untracked_files == set()
