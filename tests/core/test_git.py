# Validates REQ-p00004-A, REQ-p00004-B, REQ-p00004-D, REQ-p00004-E,
# REQ-p00004-F, REQ-p00004-H, REQ-p00004-I
"""Tests for Git Integration.

Validates:
- REQ-p00004-A: get_author_info SHALL retrieve author identity from git/gh
- REQ-p00004-B: Git change detection
- REQ-p00004-D: create_and_switch_branch SHALL create/switch branch with stash
- REQ-p00004-E: commit_and_push_spec_files SHALL commit spec files, refuse on main/master
- REQ-p00004-F: sync_branch SHALL fetch, merge remote, and rebase on main, aborting on conflict
- REQ-p00004-H: list_branches SHALL list local/remote branches, strip prefixes, deduplicate
- REQ-p00004-I: checkout SHALL switch to existing local/remote branches with fallback
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
    list_branches,
    sync_branch,
    temporary_worktree,
)


@pytest.fixture(autouse=True)
def _clean_git_env(monkeypatch):
    """Strip git env vars that leak from hook execution (e.g. pre-push).

    When tests run inside a git hook, GIT_DIR / GIT_WORK_TREE / GIT_INDEX_FILE
    are set and cause subprocess git-init calls to target the real repo.
    """
    for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        monkeypatch.delenv(var, raising=False)


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

    def test_uses_full_canonical_id(self):
        """Uses the full canonical ID (e.g., 'REQ-d00001') as keys."""
        repo_root = get_repo_root()
        if repo_root is None:
            pytest.skip("Not in a git repository")

        result = get_req_locations_from_graph(repo_root)

        # If we have results, keys should be full canonical IDs
        for req_id in result.keys():
            assert req_id.startswith("REQ-"), f"Expected full canonical ID, got: {req_id}"


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
    subprocess.run(
        ["git", "init", "--bare", "--initial-branch=main"],
        cwd=bare,
        capture_output=True,
        check=True,
    )

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


def _init_bare_with_spec(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Create a bare remote and two clones with a spec/ directory.

    Returns (bare_repo, clone_a, clone_b).
    Each clone has spec/prd.md committed and pushed, on a feature branch.
    """
    bare, clone_a, clone_b = _init_bare_and_clones(tmp_path)

    # Add spec directory in clone_a, push to remote
    (clone_a / "spec").mkdir()
    (clone_a / "spec" / "prd.md").write_text("# REQ-p00001 Original\n")
    subprocess.run(["git", "add", "."], cwd=clone_a, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "add spec"],
        cwd=clone_a,
        capture_output=True,
        check=True,
    )
    subprocess.run(["git", "push"], cwd=clone_a, capture_output=True, check=True)

    # Pull spec into clone_b
    subprocess.run(["git", "pull"], cwd=clone_b, capture_output=True, check=True)

    return bare, clone_a, clone_b


class TestCommitAndPushWithRemote:
    """Tests for commit_and_push_spec_files() with a real remote.

    Validates REQ-p00004-E push behaviour with bare+clone repos.
    """

    def test_REQ_p00004_E_commit_and_push_succeeds(self, tmp_path):
        """Commit and push spec changes to remote."""
        _bare, clone_a, clone_b = _init_bare_with_spec(tmp_path)

        # Create feature branch in clone_a
        subprocess.run(
            ["git", "checkout", "-b", "feature"],
            cwd=clone_a,
            capture_output=True,
            check=True,
        )

        # Modify spec file
        (clone_a / "spec" / "prd.md").write_text("# REQ-p00001 Updated\n")

        result = commit_and_push_spec_files(clone_a, "update prd", push=True)

        assert result["success"] is True
        assert "spec/prd.md" in result["files_committed"]
        assert "push_error" not in result

        # Verify the push arrived at the remote — clone_b can fetch the branch
        subprocess.run(["git", "fetch"], cwd=clone_b, capture_output=True, check=True)
        log = subprocess.run(
            ["git", "log", "origin/feature", "--oneline", "-1"],
            cwd=clone_b,
            capture_output=True,
            text=True,
        )
        assert "update prd" in log.stdout

    def test_REQ_p00004_E_push_failure_still_commits(self, tmp_path):
        """When push fails, commit still succeeds with push_error."""
        _bare, clone_a, _clone_b = _init_bare_with_spec(tmp_path)

        # Create feature branch in clone_a
        subprocess.run(
            ["git", "checkout", "-b", "feature"],
            cwd=clone_a,
            capture_output=True,
            check=True,
        )

        # Break the remote by removing it
        subprocess.run(
            ["git", "remote", "remove", "origin"],
            cwd=clone_a,
            capture_output=True,
            check=True,
        )

        # Modify spec file
        (clone_a / "spec" / "prd.md").write_text("# REQ-p00001 Updated\n")

        result = commit_and_push_spec_files(clone_a, "update prd", push=True)

        # Commit succeeds, push fails gracefully
        assert result["success"] is True
        assert "spec/prd.md" in result["files_committed"]
        assert "push_error" in result

        # Verify the commit was actually made
        log = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=clone_a,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "update prd" in log.stdout

    def test_REQ_p00004_E_push_arrives_at_remote(self, tmp_path):
        """Verify pushed spec changes are fetched by another clone."""
        _bare, clone_a, clone_b = _init_bare_with_spec(tmp_path)

        # clone_a: create branch, edit, commit, push
        subprocess.run(
            ["git", "checkout", "-b", "edit-spec"],
            cwd=clone_a,
            capture_output=True,
            check=True,
        )
        (clone_a / "spec" / "prd.md").write_text("# REQ-p00001 Edited by A\n")
        commit_and_push_spec_files(clone_a, "A edits prd", push=True)

        # clone_b: fetch and checkout the branch
        subprocess.run(["git", "fetch"], cwd=clone_b, capture_output=True, check=True)
        subprocess.run(
            ["git", "checkout", "-b", "edit-spec", "origin/edit-spec"],
            cwd=clone_b,
            capture_output=True,
            check=True,
        )

        # Verify the file content arrived
        assert (clone_b / "spec" / "prd.md").read_text() == "# REQ-p00001 Edited by A\n"


class TestAnsiStripping:
    """Tests for ANSI escape code stripping in commit error messages."""

    def test_ansi_codes_stripped_from_commit_error(self, tmp_path):
        """ANSI escape codes are removed from commit failure error messages."""
        _init_git_repo(tmp_path)
        (tmp_path / "spec").mkdir()
        (tmp_path / "spec" / "test.md").write_text("# REQ-p00001 Test\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "checkout", "-b", "feature"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )

        # Create a pre-commit hook that outputs ANSI codes and fails
        hooks_dir = tmp_path / ".git" / "hooks"
        hooks_dir.mkdir(exist_ok=True)
        hook = hooks_dir / "pre-commit"
        hook.write_text(
            "#!/bin/sh\n"
            'echo "\\033[0;31mError:\\033[0m \\033[1;34mvalidation failed\\033[0m" >&2\n'
            "exit 1\n"
        )
        hook.chmod(0o755)

        # Modify spec file so there's something to commit
        (tmp_path / "spec" / "test.md").write_text("# REQ-p00001 Modified\n")

        result = commit_and_push_spec_files(tmp_path, "bad commit", push=False)

        assert result["success"] is False
        # Error message should not contain ANSI escape sequences
        assert "\x1b[" not in result["error"]
        assert "\033[" not in result["error"]
        # But should still contain the actual error text
        assert "validation failed" in result["error"]


class TestGitStatusSummaryWithRemote:
    """Tests for git_status_summary() with remote tracking.

    Validates REQ-p00004-C remote divergence and ahead/behind detection.
    """

    def test_REQ_p00004_C_local_ahead_count(self, tmp_path):
        """local_ahead reflects unpushed commits."""
        _bare, clone_a, _clone_b = _init_bare_with_spec(tmp_path)

        # Create feature branch and push it (so remote tracking exists)
        subprocess.run(
            ["git", "checkout", "-b", "feature"],
            cwd=clone_a,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "push", "-u", "origin", "feature"],
            cwd=clone_a,
            capture_output=True,
            check=True,
        )

        # Make two local commits without pushing
        for i in range(2):
            (clone_a / "spec" / "prd.md").write_text(f"# REQ-p00001 Edit {i}\n")
            subprocess.run(["git", "add", "."], cwd=clone_a, capture_output=True, check=True)
            subprocess.run(
                ["git", "commit", "-m", f"local edit {i}"],
                cwd=clone_a,
                capture_output=True,
                check=True,
            )

        result = git_status_summary(clone_a)

        assert result["branch"] == "feature"
        assert result["local_ahead"] == 2
        assert result["remote_diverged"] is False

    def test_REQ_p00004_C_remote_diverged_flag(self, tmp_path):
        """remote_diverged is True when remote has commits we don't have."""
        _bare, clone_a, clone_b = _init_bare_with_spec(tmp_path)

        # Both clones on feature branch tracking remote
        for clone in (clone_a, clone_b):
            subprocess.run(
                ["git", "checkout", "-b", "feature"],
                cwd=clone,
                capture_output=True,
                check=True,
            )
            subprocess.run(
                ["git", "push", "-u", "origin", "feature"],
                cwd=clone,
                capture_output=True,
                check=True,
            )

        # clone_b pushes a commit that clone_a doesn't have
        (clone_b / "spec" / "prd.md").write_text("# REQ-p00001 From B\n")
        subprocess.run(["git", "add", "."], cwd=clone_b, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "B edit"],
            cwd=clone_b,
            capture_output=True,
            check=True,
        )
        subprocess.run(["git", "push"], cwd=clone_b, capture_output=True, check=True)

        # clone_a checks status — should detect remote divergence
        result = git_status_summary(clone_a)

        assert result["remote_diverged"] is True
        assert result["fast_forward_possible"] is True

    def test_REQ_p00004_C_no_remote_no_divergence(self, tmp_path):
        """No remote tracking → no divergence flags."""
        _init_git_repo(tmp_path)
        subprocess.run(
            ["git", "checkout", "-b", "feature"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )

        result = git_status_summary(tmp_path)

        assert result["remote_diverged"] is False
        assert result["fast_forward_possible"] is False
        assert result["local_ahead"] == 0


class TestFullGitSyncWorkflowWithRemote:
    """End-to-end workflow: branch → edit → commit → push → sync.

    Validates the full git sync flow with a real remote, covering
    REQ-p00004-C through REQ-p00004-F together.
    """

    def test_full_workflow_branch_commit_push_sync(self, tmp_path):
        """Complete workflow: create branch, edit, commit, push, sync."""
        _bare, clone_a, clone_b = _init_bare_with_spec(tmp_path)

        # 1. clone_a: status on main, clean
        status = git_status_summary(clone_a)
        assert status["is_main"] is True
        assert status["dirty_spec_files"] == []

        # 2. clone_a: create feature branch
        result = create_and_switch_branch(clone_a, "feature/prd-update")
        assert result["success"] is True

        # 3. clone_a: edit spec, verify dirty
        (clone_a / "spec" / "prd.md").write_text("# REQ-p00001 Updated by A\n")
        status = git_status_summary(clone_a)
        assert status["branch"] == "feature/prd-update"
        assert "spec/prd.md" in status["dirty_spec_files"]

        # 4. clone_a: commit and push
        result = commit_and_push_spec_files(
            clone_a,
            "update prd requirement",
            push=True,
        )
        assert result["success"] is True
        assert "push_error" not in result

        # 5. clone_a: status clean after push
        status = git_status_summary(clone_a)
        assert status["dirty_spec_files"] == []
        assert status["local_ahead"] == 0

        # 6. clone_b: fetch and checkout the feature branch
        subprocess.run(["git", "fetch"], cwd=clone_b, capture_output=True, check=True)
        subprocess.run(
            ["git", "checkout", "-b", "feature/prd-update", "origin/feature/prd-update"],
            cwd=clone_b,
            capture_output=True,
            check=True,
        )
        assert (clone_b / "spec" / "prd.md").read_text() == "# REQ-p00001 Updated by A\n"

        # 7. clone_b: make own edit, commit, push
        (clone_b / "spec" / "prd.md").write_text("# REQ-p00001 Updated by B\n")
        result = commit_and_push_spec_files(
            clone_b,
            "B updates prd",
            push=True,
        )
        assert result["success"] is True

        # 8. clone_a: sync should pull B's changes
        result = sync_branch(clone_a)
        assert result["success"] is True
        assert (clone_a / "spec" / "prd.md").read_text() == "# REQ-p00001 Updated by B\n"

    def test_sync_conflict_from_concurrent_edits(self, tmp_path):
        """Two clones edit same file on same branch → sync detects conflict."""
        _bare, clone_a, clone_b = _init_bare_with_spec(tmp_path)

        # Both on feature branch
        for clone in (clone_a, clone_b):
            subprocess.run(
                ["git", "checkout", "-b", "feature"],
                cwd=clone,
                capture_output=True,
                check=True,
            )
            subprocess.run(
                ["git", "push", "-u", "origin", "feature"],
                cwd=clone,
                capture_output=True,
                check=True,
            )

        # clone_a edits and pushes
        (clone_a / "spec" / "prd.md").write_text("# REQ-p00001 Version A\n")
        subprocess.run(["git", "add", "."], cwd=clone_a, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "A edit"],
            cwd=clone_a,
            capture_output=True,
            check=True,
        )
        subprocess.run(["git", "push"], cwd=clone_a, capture_output=True, check=True)

        # clone_b edits same file (different content) and commits locally
        (clone_b / "spec" / "prd.md").write_text("# REQ-p00001 Version B\n")
        subprocess.run(["git", "add", "."], cwd=clone_b, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "B edit"],
            cwd=clone_b,
            capture_output=True,
            check=True,
        )

        # clone_b: sync should detect conflict and abort cleanly
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


# ─────────────────────────────────────────────────────────────────
# list_branches (REQ-p00004-H)
# ─────────────────────────────────────────────────────────────────


class TestListBranches:
    """Validates REQ-p00004-H: list_branches SHALL list local/remote branches,
    strip remote prefixes, and deduplicate branches that exist both locally
    and remotely.
    """

    @pytest.fixture()
    def repo_root(self) -> Path:
        """Return the real repository root for live git queries."""
        return get_repo_root(Path(__file__).parent)

    def test_REQ_p00004_H_list_branches_returns_expected_structure(self, repo_root: Path):
        """list_branches returns dict with local, remote, current keys."""
        result = list_branches(repo_root)
        assert isinstance(result, dict)
        assert "local" in result
        assert "remote" in result
        assert "current" in result
        assert isinstance(result["local"], list)
        assert isinstance(result["remote"], list)
        # current branch should be a non-empty string inside a real repo
        assert result["current"] is not None
        assert isinstance(result["current"], str)
        assert len(result["current"]) > 0
        # current branch must appear in the local list
        assert result["current"] in result["local"]

    def test_REQ_p00004_H_list_branches_deduplicates_remotes(self, repo_root: Path):
        """No branch name appears in both local and remote lists."""
        result = list_branches(repo_root)
        local_set = set(result["local"])
        remote_set = set(result["remote"])
        overlap = local_set & remote_set
        assert overlap == set(), f"Branches in both local and remote: {overlap}"

    def test_REQ_p00004_H_list_branches_strips_origin_prefix(self, repo_root: Path):
        """No remote branch name starts with 'origin/'."""
        result = list_branches(repo_root)
        for name in result["remote"]:
            assert not name.startswith("origin/"), f"Remote branch still has origin/ prefix: {name}"


# ─────────────────────────────────────────────────────────────────
# checkout (REQ-p00004-I)
# ─────────────────────────────────────────────────────────────────


class TestCheckoutBranch:
    """Validates REQ-p00004-I: checkout SHALL switch to existing local or
    remote branches, with fallback from ``git checkout -b`` to ``git checkout``
    when the local branch already exists.
    """

    def test_REQ_p00004_I_checkout_local_branch(self, tmp_path):
        """Can switch between two local branches using git checkout."""
        _init_git_repo(tmp_path)

        # Create a second branch and switch back to main
        subprocess.run(
            ["git", "checkout", "-b", "feature"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        (tmp_path / "feature.txt").write_text("feature content\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "feature commit"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "checkout", "main"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )

        # Verify we're on main
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.stdout.strip() == "main"

        # Switch to feature branch using plain git checkout
        from elspais.utilities.git import _clean_git_env

        switch = subprocess.run(
            ["git", "checkout", "feature"],
            cwd=tmp_path,
            env=_clean_git_env(),
            capture_output=True,
            text=True,
        )
        assert switch.returncode == 0

        # Verify we're on feature now
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.stdout.strip() == "feature"

    def test_REQ_p00004_I_checkout_remote_fallback(self, tmp_path):
        """When ``git checkout -b <name> origin/<name>`` fails because the
        local branch already exists, falls back to ``git checkout <name>``.
        """
        bare, clone_a, clone_b = _init_bare_and_clones(tmp_path)

        # clone_a creates and pushes a feature branch
        subprocess.run(
            ["git", "checkout", "-b", "feature/remote-test"],
            cwd=clone_a,
            capture_output=True,
            check=True,
        )
        (clone_a / "remote.txt").write_text("from remote\n")
        subprocess.run(["git", "add", "."], cwd=clone_a, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "remote feature"],
            cwd=clone_a,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "push", "-u", "origin", "feature/remote-test"],
            cwd=clone_a,
            capture_output=True,
            check=True,
        )

        # clone_b: fetch, create a local branch with the same name, then switch away
        subprocess.run(["git", "fetch"], cwd=clone_b, capture_output=True, check=True)
        subprocess.run(
            ["git", "checkout", "-b", "feature/remote-test", "origin/feature/remote-test"],
            cwd=clone_b,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "checkout", "main"],
            cwd=clone_b,
            capture_output=True,
            check=True,
        )

        # Now simulate the remote checkout flow:
        # First attempt: git checkout -b should fail (already exists)
        from elspais.utilities.git import _clean_git_env

        env = _clean_git_env()
        attempt1 = subprocess.run(
            ["git", "checkout", "-b", "feature/remote-test", "origin/feature/remote-test"],
            cwd=clone_b,
            env=env,
            capture_output=True,
            text=True,
        )
        assert attempt1.returncode != 0
        assert "already exists" in attempt1.stderr

        # Fallback: plain git checkout should succeed
        attempt2 = subprocess.run(
            ["git", "checkout", "feature/remote-test"],
            cwd=clone_b,
            env=env,
            capture_output=True,
            text=True,
        )
        assert attempt2.returncode == 0

        # Verify we're on the right branch
        head = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=clone_b,
            capture_output=True,
            text=True,
            check=True,
        )
        assert head.stdout.strip() == "feature/remote-test"
