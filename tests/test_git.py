"""Tests for git change detection functionality."""

import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from elspais.core.git import (
    GitChangeInfo,
    MovedRequirement,
    detect_moved_requirements,
    filter_spec_files,
    get_changed_vs_branch,
    get_committed_req_locations,
    get_current_req_locations,
    get_git_changes,
    get_modified_files,
    get_repo_root,
)


class TestGitChangeInfo:
    """Tests for GitChangeInfo dataclass."""

    def test_default_values(self):
        """Test default values are empty sets/dicts."""
        info = GitChangeInfo()
        assert info.modified_files == set()
        assert info.untracked_files == set()
        assert info.branch_changed_files == set()
        assert info.committed_req_locations == {}

    def test_all_changed_files(self):
        """Test all_changed_files combines all file sets."""
        info = GitChangeInfo(
            modified_files={"a.md", "b.md"},
            untracked_files={"c.md"},
            branch_changed_files={"a.md", "d.md"},
        )
        assert info.all_changed_files == {"a.md", "b.md", "c.md", "d.md"}

    def test_uncommitted_files(self):
        """Test uncommitted_files combines modified and untracked."""
        info = GitChangeInfo(
            modified_files={"a.md"},
            untracked_files={"b.md"},
        )
        assert info.uncommitted_files == {"a.md", "b.md"}


class TestMovedRequirement:
    """Tests for MovedRequirement dataclass."""

    def test_creation(self):
        """Test MovedRequirement creation."""
        moved = MovedRequirement(
            req_id="d00001",
            old_path="spec/dev-old.md",
            new_path="spec/dev-new.md",
        )
        assert moved.req_id == "d00001"
        assert moved.old_path == "spec/dev-old.md"
        assert moved.new_path == "spec/dev-new.md"


class TestDetectMovedRequirements:
    """Tests for detect_moved_requirements function."""

    def test_no_moves(self):
        """Test when no requirements are moved."""
        committed = {"d00001": "spec/dev.md"}
        current = {"d00001": "spec/dev.md"}
        assert detect_moved_requirements(committed, current) == []

    def test_detect_move(self):
        """Test detecting a moved requirement."""
        committed = {"d00001": "spec/dev.md"}
        current = {"d00001": "spec/roadmap/dev.md"}
        moved = detect_moved_requirements(committed, current)
        assert len(moved) == 1
        assert moved[0].req_id == "d00001"
        assert moved[0].old_path == "spec/dev.md"
        assert moved[0].new_path == "spec/roadmap/dev.md"

    def test_new_requirement_not_moved(self):
        """Test that new requirements are not considered moved."""
        committed = {}
        current = {"d00001": "spec/dev.md"}
        assert detect_moved_requirements(committed, current) == []

    def test_deleted_requirement_not_moved(self):
        """Test that deleted requirements are not considered moved."""
        committed = {"d00001": "spec/dev.md"}
        current = {}
        assert detect_moved_requirements(committed, current) == []


class TestFilterSpecFiles:
    """Tests for filter_spec_files function."""

    def test_filter_spec_files(self):
        """Test filtering to only spec files."""
        files = {
            "spec/dev.md",
            "spec/roadmap/prd.md",
            "src/main.py",
            "README.md",
            "spec/INDEX.md",
        }
        result = filter_spec_files(files)
        assert result == {"spec/dev.md", "spec/roadmap/prd.md", "spec/INDEX.md"}

    def test_custom_spec_dir(self):
        """Test filtering with custom spec directory."""
        files = {"requirements/dev.md", "spec/dev.md"}
        result = filter_spec_files(files, "requirements")
        assert result == {"requirements/dev.md"}

    def test_empty_input(self):
        """Test filtering empty set."""
        assert filter_spec_files(set()) == set()


class TestGetModifiedFiles:
    """Tests for get_modified_files function."""

    def test_parse_porcelain_output(self):
        """Test parsing git status porcelain output."""
        mock_output = " M spec/dev.md\n?? spec/new.md\nA  spec/added.md\n"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=mock_output, returncode=0)
            modified, untracked = get_modified_files(Path("/repo"))

        assert "spec/dev.md" in modified
        assert "spec/added.md" in modified
        assert "spec/new.md" in untracked

    def test_handle_renames(self):
        """Test handling renamed files in porcelain output."""
        mock_output = "R  old.md -> new.md\n"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=mock_output, returncode=0)
            modified, untracked = get_modified_files(Path("/repo"))

        assert "new.md" in modified

    def test_git_not_available(self):
        """Test handling when git is not available."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            modified, untracked = get_modified_files(Path("/repo"))

        assert modified == set()
        assert untracked == set()


class TestGetChangedVsBranch:
    """Tests for get_changed_vs_branch function."""

    def test_get_changed_files(self):
        """Test getting files changed vs branch."""
        mock_output = "spec/dev.md\nspec/prd.md\n"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=mock_output, returncode=0)
            changed = get_changed_vs_branch(Path("/repo"), "main")

        assert changed == {"spec/dev.md", "spec/prd.md"}

    def test_fallback_to_origin(self):
        """Test fallback to origin/main when local branch fails."""
        mock_output = "spec/dev.md\n"

        def mock_run_impl(cmd, **kwargs):
            if "main...HEAD" in cmd:
                raise subprocess.CalledProcessError(1, cmd)
            return MagicMock(stdout=mock_output, returncode=0)

        with patch("subprocess.run", side_effect=mock_run_impl):
            changed = get_changed_vs_branch(Path("/repo"), "main")

        assert changed == {"spec/dev.md"}


class TestGetCurrentReqLocations:
    """Tests for get_current_req_locations function."""

    def test_find_requirements(self):
        """Test finding requirements in current working directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            spec_dir = repo_root / "spec"
            spec_dir.mkdir()

            # Create a requirement file
            (spec_dir / "dev.md").write_text(
                "# REQ-d00001: Test Requirement\n\nContent here.\n"
            )

            locations = get_current_req_locations(repo_root)
            assert locations == {"d00001": "spec/dev.md"}

    def test_excludes_index_files(self):
        """Test that INDEX.md and README.md are excluded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            spec_dir = repo_root / "spec"
            spec_dir.mkdir()

            (spec_dir / "INDEX.md").write_text("# REQ-d00001: In Index\n")
            (spec_dir / "README.md").write_text("# REQ-d00002: In Readme\n")
            (spec_dir / "dev.md").write_text("# REQ-d00003: Real Req\n")

            locations = get_current_req_locations(repo_root)
            assert "d00001" not in locations
            assert "d00002" not in locations
            assert "d00003" in locations

    def test_handles_associated_prefix(self):
        """Test that requirements with associated prefix are found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            spec_dir = repo_root / "spec"
            spec_dir.mkdir()

            (spec_dir / "dev.md").write_text(
                "# REQ-CAL-d00001: Associated Requirement\n"
            )

            locations = get_current_req_locations(repo_root)
            assert locations == {"d00001": "spec/dev.md"}


class TestGetGitChanges:
    """Tests for get_git_changes function."""

    def test_combines_all_info(self):
        """Test that get_git_changes combines all git info."""
        with patch("elspais.core.git.get_repo_root") as mock_root:
            mock_root.return_value = Path("/repo")

            with patch("elspais.core.git.get_modified_files") as mock_modified:
                mock_modified.return_value = ({"spec/mod.md"}, {"spec/new.md"})

                with patch("elspais.core.git.get_changed_vs_branch") as mock_branch:
                    mock_branch.return_value = {"spec/branch.md"}

                    with patch("elspais.core.git.get_committed_req_locations") as mock_locs:
                        mock_locs.return_value = {"d00001": "spec/dev.md"}

                        changes = get_git_changes()

        assert changes.modified_files == {"spec/mod.md"}
        assert changes.untracked_files == {"spec/new.md"}
        assert changes.branch_changed_files == {"spec/branch.md"}
        assert changes.committed_req_locations == {"d00001": "spec/dev.md"}

    def test_returns_empty_when_not_in_repo(self):
        """Test returns empty GitChangeInfo when not in a git repo."""
        with patch("elspais.core.git.get_repo_root") as mock_root:
            mock_root.return_value = None
            changes = get_git_changes()

        assert changes.modified_files == set()
        assert changes.untracked_files == set()


class TestGetRepoRoot:
    """Tests for get_repo_root function."""

    def test_returns_path_in_repo(self):
        """Test returns Path when in a git repository."""
        mock_output = "/home/user/repo\n"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=mock_output, returncode=0)
            root = get_repo_root()

        assert root == Path("/home/user/repo")

    def test_returns_none_when_not_in_repo(self):
        """Test returns None when not in a git repository."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(128, "git")
            root = get_repo_root()

        assert root is None
