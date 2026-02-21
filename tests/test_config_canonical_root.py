"""Tests for find_canonical_root() in config module.

Validates REQ-p00005-F: Canonical root detection for worktree-aware
repository resolution.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

from elspais.config import find_canonical_root, find_git_root


class TestFindCanonicalRoot:
    """Validates REQ-p00005-F: find_canonical_root returns the main repo root.

    For normal repos (.git is a directory), returns same as find_git_root().
    For worktrees (.git is a file), resolves the main repo root via
    git rev-parse --git-common-dir.
    """

    def test_REQ_p00005_F_normal_repo_returns_git_root(self, tmp_path: Path):
        """Normal repo with .git directory returns same as find_git_root()."""
        # Set up a normal git repo structure: .git is a directory
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        result = find_canonical_root(tmp_path)

        assert result == tmp_path
        assert result == find_git_root(tmp_path)

    def test_REQ_p00005_F_worktree_returns_main_repo_root(self, tmp_path: Path, monkeypatch):
        """Worktree (.git is a file) resolves to the main repo root."""
        # Set up worktree structure: .git is a file pointing to main repo
        worktree_dir = tmp_path / "worktree"
        worktree_dir.mkdir()
        git_file = worktree_dir / ".git"
        git_file.write_text("gitdir: /main-repo/.git/worktrees/my-worktree")

        # The main repo root we expect
        main_repo = tmp_path / "main-repo"
        main_repo.mkdir()
        main_git_dir = main_repo / ".git"
        main_git_dir.mkdir()

        # Mock subprocess.run to return the main repo's .git directory
        def mock_subprocess_run(cmd, *, capture_output, text, cwd):
            assert cmd == ["git", "rev-parse", "--git-common-dir"]
            assert cwd == worktree_dir
            return SimpleNamespace(
                returncode=0,
                stdout=str(main_git_dir) + "\n",
                stderr="",
            )

        monkeypatch.setattr(subprocess, "run", mock_subprocess_run)

        result = find_canonical_root(worktree_dir)

        assert result == main_repo

    def test_REQ_p00005_F_fallback_on_git_command_failure(self, tmp_path: Path, monkeypatch):
        """When git command fails in a worktree, falls back to git_root."""
        # Set up worktree structure: .git is a file
        git_file = tmp_path / ".git"
        git_file.write_text("gitdir: /some/path/.git/worktrees/wt")

        def mock_subprocess_run(cmd, *, capture_output, text, cwd):
            return SimpleNamespace(
                returncode=128,
                stdout="",
                stderr="fatal: not a git repository",
            )

        monkeypatch.setattr(subprocess, "run", mock_subprocess_run)

        result = find_canonical_root(tmp_path)

        # Falls back to the git_root (the worktree dir itself)
        assert result == tmp_path

    def test_REQ_p00005_F_none_when_not_in_git_repo(self, tmp_path: Path):
        """Returns None when not inside any git repository."""
        # tmp_path has no .git at all
        result = find_canonical_root(tmp_path)

        assert result is None

    def test_REQ_p00005_F_relative_common_dir_resolved(self, tmp_path: Path, monkeypatch):
        """Relative common_dir path is resolved relative to git_root."""
        # Set up worktree structure
        worktree_dir = tmp_path / "worktrees" / "feature-x"
        worktree_dir.mkdir(parents=True)
        git_file = worktree_dir / ".git"
        git_file.write_text("gitdir: ../../.git/worktrees/feature-x")

        # The main repo is at tmp_path (two levels up from worktree)
        main_git_dir = tmp_path / ".git"
        main_git_dir.mkdir()

        # Git returns a relative path: "../../.git"
        def mock_subprocess_run(cmd, *, capture_output, text, cwd):
            assert cmd == ["git", "rev-parse", "--git-common-dir"]
            return SimpleNamespace(
                returncode=0,
                stdout="../../.git\n",
                stderr="",
            )

        monkeypatch.setattr(subprocess, "run", mock_subprocess_run)

        result = find_canonical_root(worktree_dir)

        # Should resolve ../../.git relative to worktree_dir, then .parent
        # worktree_dir / "../../.git" resolves to tmp_path/.git
        # .parent of that is tmp_path
        assert result == tmp_path

    def test_REQ_p00005_F_oserror_falls_back_to_git_root(self, tmp_path: Path, monkeypatch):
        """OSError from subprocess falls back to git_root."""
        git_file = tmp_path / ".git"
        git_file.write_text("gitdir: /some/path")

        def mock_subprocess_run(cmd, *, capture_output, text, cwd):
            raise OSError("git not found")

        monkeypatch.setattr(subprocess, "run", mock_subprocess_run)

        result = find_canonical_root(tmp_path)

        assert result == tmp_path

    def test_REQ_p00005_F_subprocess_error_falls_back_to_git_root(
        self, tmp_path: Path, monkeypatch
    ):
        """SubprocessError from subprocess falls back to git_root."""
        git_file = tmp_path / ".git"
        git_file.write_text("gitdir: /some/path")

        def mock_subprocess_run(cmd, *, capture_output, text, cwd):
            raise subprocess.SubprocessError("something went wrong")

        monkeypatch.setattr(subprocess, "run", mock_subprocess_run)

        result = find_canonical_root(tmp_path)

        assert result == tmp_path

    def test_REQ_p00005_F_absolute_common_dir_used_directly(self, tmp_path: Path, monkeypatch):
        """Absolute common_dir path is used directly without resolution."""
        worktree_dir = tmp_path / "wt"
        worktree_dir.mkdir()
        git_file = worktree_dir / ".git"
        git_file.write_text("gitdir: /main/.git/worktrees/wt")

        main_repo = tmp_path / "main-repo"
        main_repo.mkdir()
        main_git = main_repo / ".git"
        main_git.mkdir()

        def mock_subprocess_run(cmd, *, capture_output, text, cwd):
            return SimpleNamespace(
                returncode=0,
                stdout=str(main_git) + "\n",
                stderr="",
            )

        monkeypatch.setattr(subprocess, "run", mock_subprocess_run)

        result = find_canonical_root(worktree_dir)

        assert result == main_repo
