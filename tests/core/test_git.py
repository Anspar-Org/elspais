# Validates REQ-p00004-A, REQ-p00004-B, REQ-p00004-D, REQ-p00004-E, REQ-p00004-F
"""Tests for Git Integration.

Validates:
- REQ-p00004-A: get_author_info SHALL retrieve author identity from git/gh
- REQ-p00004-B: Git change detection
- REQ-p00004-D: create_and_switch_branch SHALL create/switch branch with stash
- REQ-p00004-E: commit_and_push_spec_files SHALL commit spec files, refuse on main/master
- REQ-p00004-F: sync_branch SHALL fetch, merge remote, and rebase on main, aborting on conflict
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from elspais.utilities.git import (
    GitChangeInfo,
    MovedRequirement,
    commit_and_push_spec_files,
    create_and_switch_branch,
    detect_moved_requirements,
    filter_spec_files,
    get_author_info,
    get_changed_vs_branch,
    get_git_changes,
    get_modified_files,
    get_repo_root,
    get_req_locations_from_graph,
    git_status_summary,
    sync_branch,
    temporary_worktree,
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


class TestTemporaryWorktree:
    """Tests for temporary_worktree context manager."""

    def test_creates_and_cleans_up_worktree(self):
        """Creates worktree, yields path, cleans up on exit."""
        repo_root = get_repo_root()
        if repo_root is None:
            pytest.skip("Not in a git repository")

        worktree_path = None
        with temporary_worktree(repo_root, "HEAD") as path:
            worktree_path = path
            # Worktree should exist
            assert path.exists()
            # Should have .elspais.toml or other repo files
            assert (path / ".elspais.toml").exists() or (path / "spec").exists()

        # Worktree should be cleaned up
        assert worktree_path is not None
        assert not worktree_path.exists()

    def test_raises_on_invalid_ref(self):
        """Raises CalledProcessError for invalid git ref."""
        repo_root = get_repo_root()
        if repo_root is None:
            pytest.skip("Not in a git repository")

        with pytest.raises(subprocess.CalledProcessError):
            with temporary_worktree(repo_root, "nonexistent-ref-abc123"):
                pass


class TestGetReqLocationsFromGraph:
    """Tests for get_req_locations_from_graph function."""

    def test_returns_dict(self):
        """Returns dict mapping REQ IDs to paths."""
        repo_root = get_repo_root()
        if repo_root is None:
            pytest.skip("Not in a git repository")

        result = get_req_locations_from_graph(repo_root)

        assert isinstance(result, dict)
        # If there are any requirements, they should have string keys and values
        for req_id, path in result.items():
            assert isinstance(req_id, str)
            assert isinstance(path, str)

    def test_extracts_req_suffix(self):
        """Extracts just the suffix (e.g., 'd00001') from REQ IDs."""
        repo_root = get_repo_root()
        if repo_root is None:
            pytest.skip("Not in a git repository")

        result = get_req_locations_from_graph(repo_root)

        # If we have results, none should start with "REQ-"
        for req_id in result.keys():
            assert not req_id.startswith("REQ-"), f"Expected suffix only, got: {req_id}"


class TestGetAuthorInfo:
    """Tests for get_author_info.

    Validates REQ-p00004-A: get_author_info SHALL retrieve author
    identity from git config or gh CLI.
    """

    @patch("elspais.utilities.git.subprocess.run")
    def test_REQ_p00004_A_get_author_info_git_fallback(self, mock_run):
        """Git config returns name and email as id."""
        mock_run.side_effect = [
            MagicMock(stdout="Jane Doe\n", returncode=0),
            MagicMock(stdout="jane@example.org\n", returncode=0),
        ]

        result = get_author_info(id_source="git")

        assert result["name"] == "Jane Doe"
        assert result["id"] == "jane@example.org"

    @patch("elspais.utilities.git.subprocess.run")
    def test_REQ_p00004_A_get_author_info_raises_on_empty(self, mock_run):
        """Raises ValueError when git config returns empty values."""
        mock_run.side_effect = [
            MagicMock(stdout="\n", returncode=0),
            MagicMock(stdout="\n", returncode=0),
        ]

        with pytest.raises(ValueError):
            get_author_info(id_source="git")


class TestGitStatusSummary:
    """Tests for git_status_summary().

    Validates REQ-p00004-C: The tool SHALL provide a git status summary
    reporting current branch, main-branch detection, dirty spec files,
    and remote divergence state.
    """

    def test_REQ_p00004_C_clean_feature_branch(self, tmp_path):
        """On a clean feature branch with no remote divergence."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "checkout", "-b", "main"], cwd=tmp_path, capture_output=True, check=True
        )
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        (tmp_path / "spec").mkdir()
        (tmp_path / "spec" / "test.md").write_text("# REQ-p00001 Test\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True, check=True
        )
        subprocess.run(
            ["git", "checkout", "-b", "feature"], cwd=tmp_path, capture_output=True, check=True
        )

        result = git_status_summary(tmp_path, spec_dir="spec")

        assert result["branch"] == "feature"
        assert result["is_main"] is False
        assert result["dirty_spec_files"] == []
        assert result["local_ahead"] == 0
        assert result["remote_diverged"] is False
        assert result["fast_forward_possible"] is False
        assert result["main_diverged"] is False

    def test_REQ_p00004_C_main_branch_dirty_spec(self, tmp_path):
        """On main with modified spec files."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "checkout", "-b", "main"], cwd=tmp_path, capture_output=True, check=True
        )
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        (tmp_path / "spec").mkdir()
        (tmp_path / "spec" / "test.md").write_text("# REQ-p00001 Test\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True, check=True
        )
        # Dirty spec file
        (tmp_path / "spec" / "test.md").write_text("# REQ-p00001 Modified\n")

        result = git_status_summary(tmp_path, spec_dir="spec")

        assert result["branch"] == "main"
        assert result["is_main"] is True
        assert "spec/test.md" in result["dirty_spec_files"]

    def test_REQ_p00004_C_non_spec_dirty_excluded(self, tmp_path):
        """Dirty files outside spec/ are excluded from dirty_spec_files."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "checkout", "-b", "main"], cwd=tmp_path, capture_output=True, check=True
        )
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        (tmp_path / "spec").mkdir()
        (tmp_path / "spec" / "test.md").write_text("clean\n")
        (tmp_path / "other.txt").write_text("clean\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True, check=True
        )
        # Dirty non-spec file only
        (tmp_path / "other.txt").write_text("dirty\n")

        result = git_status_summary(tmp_path, spec_dir="spec")

        assert result["dirty_spec_files"] == []


def _init_git_repo(tmp_path: Path) -> None:
    """Helper: init a git repo with one commit so branches can be created."""
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(["git", "checkout", "-b", "main"], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    (tmp_path / "README.md").write_text("init\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True, check=True)


class TestCreateAndSwitchBranch:
    """Tests for create_and_switch_branch().

    Validates REQ-p00004-D: The tool SHALL create and switch to a new git
    branch, using stash to preserve dirty working tree changes across the
    switch.
    """

    def test_REQ_p00004_D_clean_switch(self, tmp_path):
        """Creates branch and switches on a clean working tree."""
        _init_git_repo(tmp_path)

        result = create_and_switch_branch(tmp_path, "feature/test")

        assert result["success"] is True
        assert result["branch"] == "feature/test"
        # Verify we're on the new branch
        branch_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True,
        )
        assert branch_result.stdout.strip() == "feature/test"

    def test_REQ_p00004_D_dirty_stash_preserves_changes(self, tmp_path):
        """Dirty working tree changes are preserved across branch switch."""
        _init_git_repo(tmp_path)

        # Create a dirty file (tracked modification)
        (tmp_path / "README.md").write_text("modified\n")
        # Create an untracked file
        (tmp_path / "new_file.txt").write_text("untracked\n")

        result = create_and_switch_branch(tmp_path, "feature/dirty")

        assert result["success"] is True
        assert result["branch"] == "feature/dirty"
        # Verify changes survived the switch
        assert (tmp_path / "README.md").read_text() == "modified\n"
        assert (tmp_path / "new_file.txt").read_text() == "untracked\n"

    def test_REQ_p00004_D_invalid_branch_name(self, tmp_path):
        """Rejects invalid branch names."""
        _init_git_repo(tmp_path)

        result = create_and_switch_branch(tmp_path, "bad..name")

        assert result["success"] is False
        assert "invalid" in result["error"].lower() or "Invalid" in result["error"]

    def test_REQ_p00004_D_duplicate_branch_name(self, tmp_path):
        """Rejects a branch name that already exists."""
        _init_git_repo(tmp_path)

        # Create branch first time -- should succeed
        result1 = create_and_switch_branch(tmp_path, "feature/dup")
        assert result1["success"] is True

        # Switch back to main
        subprocess.run(["git", "checkout", "main"], cwd=tmp_path, capture_output=True, check=True)

        # Try to create same branch again -- should fail
        result2 = create_and_switch_branch(tmp_path, "feature/dup")
        assert result2["success"] is False
        assert "error" in result2


class TestCommitAndPushSpecFiles:
    """Tests for commit_and_push_spec_files().

    Validates REQ-p00004-E: The tool SHALL commit modified spec files and
    optionally push, refusing to operate on main/master branches.
    """

    def test_REQ_p00004_E_commit_dirty_spec_files(self, tmp_path):
        """Commits modified spec files on a feature branch."""
        _init_git_repo(tmp_path)
        (tmp_path / "spec").mkdir()
        (tmp_path / "spec" / "test.md").write_text("# REQ-p00001 Test\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "add spec"], cwd=tmp_path, capture_output=True, check=True
        )
        subprocess.run(
            ["git", "checkout", "-b", "feature"], cwd=tmp_path, capture_output=True, check=True
        )

        # Modify spec file
        (tmp_path / "spec" / "test.md").write_text("# REQ-p00001 Modified\n")

        result = commit_and_push_spec_files(tmp_path, "test commit", push=False)

        assert result["success"] is True
        assert "spec/test.md" in result["files_committed"]

        # Verify the commit was made
        log = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "test commit" in log.stdout

    def test_REQ_p00004_E_refuse_on_main(self, tmp_path):
        """Refuses to commit when on main branch."""
        _init_git_repo(tmp_path)
        (tmp_path / "spec").mkdir()
        (tmp_path / "spec" / "test.md").write_text("# REQ-p00001 Test\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "add spec"], cwd=tmp_path, capture_output=True, check=True
        )

        # Modify spec file while on main
        (tmp_path / "spec" / "test.md").write_text("# REQ-p00001 Modified\n")

        result = commit_and_push_spec_files(tmp_path, "test commit", push=False)

        assert result["success"] is False
        assert "main" in result["error"].lower() or "protected" in result["error"].lower()

    def test_REQ_p00004_E_nothing_to_commit(self, tmp_path):
        """Returns error when no dirty spec files exist."""
        _init_git_repo(tmp_path)
        (tmp_path / "spec").mkdir()
        (tmp_path / "spec" / "test.md").write_text("# REQ-p00001 Test\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "add spec"], cwd=tmp_path, capture_output=True, check=True
        )
        subprocess.run(
            ["git", "checkout", "-b", "feature"], cwd=tmp_path, capture_output=True, check=True
        )

        # No changes made -- nothing to commit
        result = commit_and_push_spec_files(tmp_path, "test commit", push=False)

        assert result["success"] is False
        assert "nothing" in result["error"].lower()

    def test_REQ_p00004_E_includes_untracked_spec_files(self, tmp_path):
        """Stages and commits untracked (new) spec files."""
        _init_git_repo(tmp_path)
        (tmp_path / "spec").mkdir()
        (tmp_path / "spec" / "existing.md").write_text("# REQ-p00001 Existing\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "add spec"], cwd=tmp_path, capture_output=True, check=True
        )
        subprocess.run(
            ["git", "checkout", "-b", "feature"], cwd=tmp_path, capture_output=True, check=True
        )

        # Create a new untracked spec file
        (tmp_path / "spec" / "new.md").write_text("# REQ-p00002 New\n")

        result = commit_and_push_spec_files(tmp_path, "add new spec", push=False)

        assert result["success"] is True
        assert "spec/new.md" in result["files_committed"]


def _init_bare_and_clones(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Create a bare remote and two clones for pull tests.

    Returns (bare_repo, clone_a, clone_b).
    """
    bare = tmp_path / "remote.git"
    bare.mkdir()
    subprocess.run(["git", "init", "--bare"], cwd=bare, capture_output=True, check=True)

    clone_a = tmp_path / "clone_a"
    subprocess.run(["git", "clone", str(bare), str(clone_a)], capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=clone_a,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=clone_a,
        capture_output=True,
        check=True,
    )
    # Create initial commit and push
    (clone_a / "README.md").write_text("init\n")
    subprocess.run(["git", "add", "."], cwd=clone_a, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=clone_a, capture_output=True, check=True)
    subprocess.run(
        ["git", "push", "-u", "origin", "main"],
        cwd=clone_a,
        capture_output=True,
        check=True,
    )

    clone_b = tmp_path / "clone_b"
    subprocess.run(["git", "clone", str(bare), str(clone_b)], capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=clone_b,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=clone_b,
        capture_output=True,
        check=True,
    )

    return bare, clone_a, clone_b


class TestPullFfOnly:
    """Tests for sync_branch().

    Validates REQ-p00004-F: The tool SHALL fetch, merge remote changes,
    and rebase on main — aborting on conflict.
    """

    def test_REQ_p00004_F_no_remote_already_up_to_date(self, tmp_path):
        """No remote configured returns success (nothing to sync)."""
        _init_git_repo(tmp_path)

        result = sync_branch(tmp_path)

        assert result["success"] is True
        assert result["actions"] == []

    def test_REQ_p00004_F_ff_pull_succeeds(self, tmp_path):
        """Fast-forward pull succeeds when remote has new commits."""
        _bare, clone_a, clone_b = _init_bare_and_clones(tmp_path)

        # Push a new commit from clone_a
        (clone_a / "new_file.txt").write_text("hello\n")
        subprocess.run(["git", "add", "."], cwd=clone_a, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "add file"],
            cwd=clone_a,
            capture_output=True,
            check=True,
        )
        subprocess.run(["git", "push"], cwd=clone_a, capture_output=True, check=True)

        # Pull from clone_b (should fast-forward)
        result = sync_branch(clone_b)

        assert result["success"] is True
        assert "message" in result
        # Verify the file arrived
        assert (clone_b / "new_file.txt").read_text() == "hello\n"

    def test_REQ_p00004_F_diverged_no_conflict_merges(self, tmp_path):
        """Diverged with no conflict succeeds via merge."""
        _bare, clone_a, clone_b = _init_bare_and_clones(tmp_path)

        # Push a commit from clone_a (different file)
        (clone_a / "file_a.txt").write_text("from a\n")
        subprocess.run(["git", "add", "."], cwd=clone_a, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "commit from a"],
            cwd=clone_a,
            capture_output=True,
            check=True,
        )
        subprocess.run(["git", "push"], cwd=clone_a, capture_output=True, check=True)

        # Make a local commit in clone_b (different file — no conflict)
        (clone_b / "file_b.txt").write_text("from b\n")
        subprocess.run(["git", "add", "."], cwd=clone_b, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "commit from b"],
            cwd=clone_b,
            capture_output=True,
            check=True,
        )

        result = sync_branch(clone_b)

        assert result["success"] is True
        assert any("Merged" in a or "Fast-forwarded" in a for a in result["actions"])
        # Both files present
        assert (clone_b / "file_a.txt").read_text() == "from a\n"
        assert (clone_b / "file_b.txt").read_text() == "from b\n"

    def test_REQ_p00004_F_diverged_with_conflict_aborts(self, tmp_path):
        """Diverged with conflict aborts merge cleanly."""
        _bare, clone_a, clone_b = _init_bare_and_clones(tmp_path)

        # Both edit the SAME file (README.md from init)
        (clone_a / "README.md").write_text("version A\n")
        subprocess.run(["git", "add", "."], cwd=clone_a, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "edit from a"],
            cwd=clone_a,
            capture_output=True,
            check=True,
        )
        subprocess.run(["git", "push"], cwd=clone_a, capture_output=True, check=True)

        (clone_b / "README.md").write_text("version B\n")
        subprocess.run(["git", "add", "."], cwd=clone_b, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "edit from b"],
            cwd=clone_b,
            capture_output=True,
            check=True,
        )

        result = sync_branch(clone_b)

        assert result["success"] is False
        assert "conflict" in result["error"].lower()
        # Working tree should be clean (merge aborted)
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=clone_b,
            capture_output=True,
            text=True,
        )
        assert status.stdout.strip() == ""
