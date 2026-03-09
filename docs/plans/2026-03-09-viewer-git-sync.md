# Viewer Git Sync Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add git commit/push workflow to the viewer so users can commit and push spec edits without leaving the browser.

**Architecture:** Four new git utility functions (`git_status_summary`, `create_and_switch_branch`, `commit_and_push_spec_files`, `pull_ff_only`) in `utilities/git.py`. Four new REST endpoints in `server/app.py`. Frontend: branch indicator next to Edit toggle, branch creation modal, push modal, `beforeunload` warning. All git operations are safe (no rebase, no merge, no force push).

**Tech Stack:** Python stdlib `subprocess` for git, Flask routes, vanilla JS (Jinja2 templates)

**Design doc:** `docs/plans/2026-03-09-viewer-git-sync-design.md`

---

## Task 1: Git Status Summary Function

**Files:**
- Modify: `src/elspais/utilities/git.py` (append after `get_current_branch`, ~line 433)
- Test: `tests/core/test_git.py`

**Step 1: Write the failing tests**

```python
# In tests/core/test_git.py — add at end of file

class TestGitStatusSummary:
    """Tests for git_status_summary()."""

    def test_clean_feature_branch(self, tmp_path):
        """On a clean feature branch with no remote divergence."""
        # Set up a git repo with a feature branch
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "main"], cwd=tmp_path, capture_output=True)
        (tmp_path / "spec").mkdir()
        (tmp_path / "spec" / "test.md").write_text("# REQ-p00001 Test\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "feature"], cwd=tmp_path, capture_output=True)

        from elspais.utilities.git import git_status_summary
        result = git_status_summary(tmp_path, spec_dir="spec")

        assert result["branch"] == "feature"
        assert result["is_main"] is False
        assert result["dirty_spec_files"] == []
        assert result["remote_diverged"] is False
        assert result["fast_forward_possible"] is False

    def test_main_branch_dirty_spec(self, tmp_path):
        """On main with modified spec files."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "main"], cwd=tmp_path, capture_output=True)
        (tmp_path / "spec").mkdir()
        (tmp_path / "spec" / "test.md").write_text("# REQ-p00001 Test\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)
        # Dirty spec file
        (tmp_path / "spec" / "test.md").write_text("# REQ-p00001 Modified\n")

        from elspais.utilities.git import git_status_summary
        result = git_status_summary(tmp_path, spec_dir="spec")

        assert result["branch"] == "main"
        assert result["is_main"] is True
        assert "spec/test.md" in result["dirty_spec_files"]

    def test_non_spec_dirty_files_excluded(self, tmp_path):
        """Dirty files outside spec/ are excluded from dirty_spec_files."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "main"], cwd=tmp_path, capture_output=True)
        (tmp_path / "spec").mkdir()
        (tmp_path / "spec" / "test.md").write_text("clean\n")
        (tmp_path / "other.txt").write_text("clean\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)
        # Dirty non-spec file only
        (tmp_path / "other.txt").write_text("dirty\n")

        from elspais.utilities.git import git_status_summary
        result = git_status_summary(tmp_path, spec_dir="spec")

        assert result["dirty_spec_files"] == []
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/core/test_git.py::TestGitStatusSummary -v`
Expected: FAIL with `ImportError: cannot import name 'git_status_summary'`

**Step 3: Write minimal implementation**

In `src/elspais/utilities/git.py`, after `get_current_branch()` (~line 433), add:

```python
def git_status_summary(
    repo_root: Path,
    spec_dir: str = "spec",
    main_branches: tuple[str, ...] = ("main", "master"),
) -> dict[str, Any]:
    """Get git status summary for the viewer UI.

    Returns a dict with:
        branch: Current branch name (or None if detached)
        is_main: Whether current branch is a main/protected branch
        dirty_spec_files: List of modified/untracked spec files (relative paths)
        remote_diverged: Whether the remote tracking branch has diverged
        fast_forward_possible: Whether a fast-forward pull is possible
    """
    branch = get_current_branch(repo_root)
    is_main = branch in main_branches if branch else False

    # Get dirty spec files
    modified, untracked = get_modified_files(repo_root)
    all_dirty = modified | untracked
    dirty_spec = sorted(f for f in all_dirty if f.startswith(f"{spec_dir}/"))

    # Check remote divergence
    remote_diverged = False
    fast_forward_possible = False
    if branch:
        try:
            # Fetch without modifying working tree
            subprocess.run(
                ["git", "fetch", "--quiet"],
                cwd=repo_root,
                env=_clean_git_env(),
                capture_output=True,
                timeout=10,
            )
            # Check if remote tracking branch exists and has diverged
            remote_ref = f"origin/{branch}"
            # Count commits: local ahead, remote ahead
            result = subprocess.run(
                ["git", "rev-list", "--left-right", "--count",
                 f"{branch}...{remote_ref}"],
                cwd=repo_root,
                env=_clean_git_env(),
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split()
                if len(parts) == 2:
                    local_ahead = int(parts[0])
                    remote_ahead = int(parts[1])
                    remote_diverged = remote_ahead > 0
                    fast_forward_possible = (
                        remote_ahead > 0 and local_ahead == 0
                    )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
                FileNotFoundError, ValueError):
            pass  # No remote or fetch failed — treat as not diverged

    return {
        "branch": branch,
        "is_main": is_main,
        "dirty_spec_files": dirty_spec,
        "remote_diverged": remote_diverged,
        "fast_forward_possible": fast_forward_possible,
    }
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/core/test_git.py::TestGitStatusSummary -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/elspais/utilities/git.py tests/core/test_git.py
git commit -m "[CUR-1081] feat: add git_status_summary for viewer branch awareness"
```

---

## Task 2: Branch Creation Function

**Files:**
- Modify: `src/elspais/utilities/git.py` (append after `git_status_summary`)
- Test: `tests/core/test_git.py`

**Step 1: Write the failing tests**

```python
# In tests/core/test_git.py

class TestCreateAndSwitchBranch:
    """Tests for create_and_switch_branch()."""

    def test_switch_from_main_clean(self, tmp_path):
        """Create branch from clean main."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "main"], cwd=tmp_path, capture_output=True)
        (tmp_path / "file.txt").write_text("content\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)

        from elspais.utilities.git import create_and_switch_branch, get_current_branch
        result = create_and_switch_branch(tmp_path, "my-feature")

        assert result["success"] is True
        assert result["branch"] == "my-feature"
        assert get_current_branch(tmp_path) == "my-feature"

    def test_switch_from_main_dirty_preserves_changes(self, tmp_path):
        """Dirty working tree is preserved on new branch via stash."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "main"], cwd=tmp_path, capture_output=True)
        (tmp_path / "spec").mkdir()
        (tmp_path / "spec" / "test.md").write_text("original\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)
        # Dirty the file
        (tmp_path / "spec" / "test.md").write_text("modified\n")

        from elspais.utilities.git import create_and_switch_branch, get_current_branch
        result = create_and_switch_branch(tmp_path, "my-feature")

        assert result["success"] is True
        assert get_current_branch(tmp_path) == "my-feature"
        # Changes preserved
        assert (tmp_path / "spec" / "test.md").read_text() == "modified\n"
        # Main is clean (changes moved to new branch)

    def test_invalid_branch_name(self, tmp_path):
        """Invalid branch name returns error."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "main"], cwd=tmp_path, capture_output=True)
        (tmp_path / "file.txt").write_text("content\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)

        from elspais.utilities.git import create_and_switch_branch
        result = create_and_switch_branch(tmp_path, "bad branch name!!")

        assert result["success"] is False
        assert "error" in result

    def test_duplicate_branch_name(self, tmp_path):
        """Branch that already exists returns error."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "main"], cwd=tmp_path, capture_output=True)
        (tmp_path / "file.txt").write_text("content\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "branch", "existing"], cwd=tmp_path, capture_output=True)

        from elspais.utilities.git import create_and_switch_branch
        result = create_and_switch_branch(tmp_path, "existing")

        assert result["success"] is False
        assert "error" in result
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/core/test_git.py::TestCreateAndSwitchBranch -v`
Expected: FAIL with ImportError

**Step 3: Write minimal implementation**

```python
def create_and_switch_branch(
    repo_root: Path,
    branch_name: str,
) -> dict[str, Any]:
    """Create a new branch and switch to it, preserving working tree changes.

    If the working tree is dirty, uses git stash to carry changes to the new branch.

    Args:
        repo_root: Path to repository root
        branch_name: Name for the new branch

    Returns:
        Dict with 'success', 'branch', and optional 'error'
    """
    env = _clean_git_env()

    # Check if working tree is dirty
    modified, untracked = get_modified_files(repo_root)
    has_changes = bool(modified or untracked)

    try:
        # Stash changes if dirty (include untracked)
        if has_changes:
            subprocess.run(
                ["git", "stash", "push", "--include-untracked", "-m",
                 f"elspais: switching to {branch_name}"],
                cwd=repo_root, env=env, capture_output=True, text=True, check=True,
            )

        # Create and switch to new branch
        result = subprocess.run(
            ["git", "checkout", "-b", branch_name],
            cwd=repo_root, env=env, capture_output=True, text=True,
        )
        if result.returncode != 0:
            # Restore stash if branch creation failed
            if has_changes:
                subprocess.run(
                    ["git", "stash", "pop"],
                    cwd=repo_root, env=env, capture_output=True,
                )
            return {"success": False, "error": result.stderr.strip()}

        # Pop stash on new branch
        if has_changes:
            subprocess.run(
                ["git", "stash", "pop"],
                cwd=repo_root, env=env, capture_output=True, text=True, check=True,
            )

        return {"success": True, "branch": branch_name}
    except subprocess.CalledProcessError as e:
        return {"success": False, "error": f"Git error: {e.stderr}"}
    except FileNotFoundError:
        return {"success": False, "error": "git not found"}
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/core/test_git.py::TestCreateAndSwitchBranch -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/elspais/utilities/git.py tests/core/test_git.py
git commit -m "[CUR-1081] feat: add create_and_switch_branch for viewer git sync"
```

---

## Task 3: Commit-and-Push Function

**Files:**
- Modify: `src/elspais/utilities/git.py`
- Test: `tests/core/test_git.py`

**Step 1: Write the failing tests**

```python
# In tests/core/test_git.py

class TestCommitAndPushSpecFiles:
    """Tests for commit_and_push_spec_files()."""

    def test_commit_dirty_spec_files(self, tmp_path):
        """Commits all modified spec files with the given message."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "feature"], cwd=tmp_path, capture_output=True)
        (tmp_path / "spec").mkdir()
        (tmp_path / "spec" / "test.md").write_text("original\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)
        # Modify spec file
        (tmp_path / "spec" / "test.md").write_text("modified\n")

        from elspais.utilities.git import commit_and_push_spec_files
        result = commit_and_push_spec_files(
            tmp_path, message="test commit", spec_dir="spec", push=False,
        )

        assert result["success"] is True
        assert "spec/test.md" in result["files_committed"]
        # Verify commit happened
        log = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=tmp_path, capture_output=True, text=True,
        )
        assert "test commit" in log.stdout

    def test_refuses_on_main(self, tmp_path):
        """Refuses to commit when on main branch."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "main"], cwd=tmp_path, capture_output=True)
        (tmp_path / "spec").mkdir()
        (tmp_path / "spec" / "test.md").write_text("content\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)
        (tmp_path / "spec" / "test.md").write_text("dirty\n")

        from elspais.utilities.git import commit_and_push_spec_files
        result = commit_and_push_spec_files(
            tmp_path, message="bad commit", spec_dir="spec", push=False,
        )

        assert result["success"] is False
        assert "main" in result["error"].lower()

    def test_nothing_to_commit(self, tmp_path):
        """Returns error when no spec files are dirty."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "feature"], cwd=tmp_path, capture_output=True)
        (tmp_path / "spec").mkdir()
        (tmp_path / "spec" / "test.md").write_text("content\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)

        from elspais.utilities.git import commit_and_push_spec_files
        result = commit_and_push_spec_files(
            tmp_path, message="empty", spec_dir="spec", push=False,
        )

        assert result["success"] is False
        assert "nothing" in result["error"].lower()

    def test_includes_new_untracked_spec_files(self, tmp_path):
        """New (untracked) spec files are also committed."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "feature"], cwd=tmp_path, capture_output=True)
        (tmp_path / "spec").mkdir()
        (tmp_path / "spec" / "existing.md").write_text("content\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)
        # Add new untracked spec file
        (tmp_path / "spec" / "new.md").write_text("# REQ-p00002 New\n")

        from elspais.utilities.git import commit_and_push_spec_files
        result = commit_and_push_spec_files(
            tmp_path, message="add new", spec_dir="spec", push=False,
        )

        assert result["success"] is True
        assert "spec/new.md" in result["files_committed"]
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/core/test_git.py::TestCommitAndPushSpecFiles -v`
Expected: FAIL with ImportError

**Step 3: Write minimal implementation**

```python
def commit_and_push_spec_files(
    repo_root: Path,
    message: str,
    spec_dir: str = "spec",
    push: bool = True,
    main_branches: tuple[str, ...] = ("main", "master"),
) -> dict[str, Any]:
    """Stage all modified spec files, commit, and optionally push.

    Refuses to commit on main/master branches.

    Args:
        repo_root: Path to repository root
        message: Commit message
        spec_dir: Spec directory name (default: "spec")
        push: Whether to push after committing (default: True)
        main_branches: Branch names that cannot be committed to

    Returns:
        Dict with 'success', 'files_committed', and optional 'error'
    """
    env = _clean_git_env()
    branch = get_current_branch(repo_root)

    if branch in main_branches:
        return {"success": False, "error": f"Cannot commit to {branch}"}

    # Find dirty spec files
    modified, untracked = get_modified_files(repo_root)
    all_dirty = modified | untracked
    spec_files = sorted(f for f in all_dirty if f.startswith(f"{spec_dir}/"))

    if not spec_files:
        return {"success": False, "error": "Nothing to commit: no modified spec files"}

    try:
        # Stage spec files
        subprocess.run(
            ["git", "add", "--"] + spec_files,
            cwd=repo_root, env=env, capture_output=True, text=True, check=True,
        )

        # Commit
        subprocess.run(
            ["git", "commit", "-m", message],
            cwd=repo_root, env=env, capture_output=True, text=True, check=True,
        )

        # Push
        if push:
            result = subprocess.run(
                ["git", "push", "-u", "origin", branch],
                cwd=repo_root, env=env, capture_output=True, text=True,
            )
            if result.returncode != 0:
                return {
                    "success": True,
                    "files_committed": spec_files,
                    "push_error": result.stderr.strip(),
                }

        return {"success": True, "files_committed": spec_files}
    except subprocess.CalledProcessError as e:
        return {"success": False, "error": f"Git error: {e.stderr}"}
    except FileNotFoundError:
        return {"success": False, "error": "git not found"}
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/core/test_git.py::TestCommitAndPushSpecFiles -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/elspais/utilities/git.py tests/core/test_git.py
git commit -m "[CUR-1081] feat: add commit_and_push_spec_files for viewer git sync"
```

---

## Task 4: Pull Fast-Forward-Only Function

**Files:**
- Modify: `src/elspais/utilities/git.py`
- Test: `tests/core/test_git.py`

**Step 1: Write the failing tests**

```python
# In tests/core/test_git.py

class TestPullFfOnly:
    """Tests for pull_ff_only()."""

    def test_no_remote_returns_error(self, tmp_path):
        """No remote configured returns informative error."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "feature"], cwd=tmp_path, capture_output=True)
        (tmp_path / "f.txt").write_text("x\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)

        from elspais.utilities.git import pull_ff_only
        result = pull_ff_only(tmp_path)

        assert result["success"] is False

    def test_ff_pull_succeeds(self, tmp_path):
        """Fast-forward pull works when remote is ahead."""
        # Set up bare remote + clone
        bare = tmp_path / "bare.git"
        subprocess.run(["git", "init", "--bare", str(bare)], capture_output=True)
        clone = tmp_path / "clone"
        subprocess.run(["git", "clone", str(bare), str(clone)], capture_output=True)
        subprocess.run(["git", "checkout", "-b", "feature"], cwd=clone, capture_output=True)
        (clone / "f.txt").write_text("v1\n")
        subprocess.run(["git", "add", "."], cwd=clone, capture_output=True)
        subprocess.run(["git", "commit", "-m", "v1"], cwd=clone, capture_output=True)
        subprocess.run(["git", "push", "-u", "origin", "feature"], cwd=clone, capture_output=True)

        # Create second clone, push a commit
        clone2 = tmp_path / "clone2"
        subprocess.run(["git", "clone", str(bare), str(clone2)], capture_output=True)
        subprocess.run(["git", "checkout", "feature"], cwd=clone2, capture_output=True)
        (clone2 / "f.txt").write_text("v2\n")
        subprocess.run(["git", "add", "."], cwd=clone2, capture_output=True)
        subprocess.run(["git", "commit", "-m", "v2"], cwd=clone2, capture_output=True)
        subprocess.run(["git", "push"], cwd=clone2, capture_output=True)

        # Pull in original clone
        from elspais.utilities.git import pull_ff_only
        result = pull_ff_only(clone)

        assert result["success"] is True
        assert (clone / "f.txt").read_text() == "v2\n"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/core/test_git.py::TestPullFfOnly -v`
Expected: FAIL with ImportError

**Step 3: Write minimal implementation**

```python
def pull_ff_only(
    repo_root: Path,
) -> dict[str, Any]:
    """Pull from remote using fast-forward only.

    If fast-forward is not possible, the pull is aborted and an error is returned.
    Elspais never rebases or merges — conflicts must be resolved externally.

    Args:
        repo_root: Path to repository root

    Returns:
        Dict with 'success' and optional 'reason'
    """
    env = _clean_git_env()

    try:
        subprocess.run(
            ["git", "fetch"],
            cwd=repo_root, env=env, capture_output=True, text=True,
            check=True, timeout=15,
        )
        result = subprocess.run(
            ["git", "merge", "--ff-only"],
            cwd=repo_root, env=env, capture_output=True, text=True,
        )
        if result.returncode != 0:
            return {
                "success": False,
                "reason": "Cannot fast-forward — resolve differences outside elspais",
            }
        return {"success": True}
    except subprocess.TimeoutExpired:
        return {"success": False, "reason": "Fetch timed out"}
    except subprocess.CalledProcessError as e:
        return {"success": False, "reason": f"Git error: {e.stderr.strip()}"}
    except FileNotFoundError:
        return {"success": False, "reason": "git not found"}
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/core/test_git.py::TestPullFfOnly -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/elspais/utilities/git.py tests/core/test_git.py
git commit -m "[CUR-1081] feat: add pull_ff_only for viewer git sync"
```

---

## Task 5: Flask Git Endpoints

**Files:**
- Modify: `src/elspais/server/app.py` (add after persistence endpoints, ~line 740)
- Test: `tests/test_server_app.py`

**Step 1: Write the failing tests**

```python
# In tests/test_server_app.py — add new test class

class TestGitEndpoints:
    """Tests for /api/git/* endpoints."""

    def test_git_status_returns_branch_info(self, client, tmp_repo):
        """GET /api/git/status returns branch and dirty files."""
        resp = client.get("/api/git/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "branch" in data
        assert "is_main" in data
        assert "dirty_spec_files" in data
        assert "remote_diverged" in data
        assert "fast_forward_possible" in data

    def test_git_branch_creates_branch(self, client, tmp_repo):
        """POST /api/git/branch creates a new branch."""
        resp = client.post("/api/git/branch", json={"name": "test-branch"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["branch"] == "test-branch"

    def test_git_branch_missing_name(self, client, tmp_repo):
        """POST /api/git/branch without name returns 400."""
        resp = client.post("/api/git/branch", json={})
        assert resp.status_code == 400

    def test_git_push_on_main_refused(self, client, tmp_repo):
        """POST /api/git/push on main is refused."""
        # Ensure we're on main for this test
        resp = client.post("/api/git/push", json={"message": "test"})
        # Depends on test setup — if on main, should fail
        data = resp.get_json()
        if data.get("error") and "main" in data["error"].lower():
            assert resp.status_code == 403

    def test_git_pull_no_remote(self, client, tmp_repo):
        """POST /api/git/pull with no remote returns error."""
        resp = client.post("/api/git/pull")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is False
```

> **Note to implementer:** The test fixtures (`client`, `tmp_repo`) should match the existing patterns in `tests/test_server_app.py`. Read that file first and adapt fixture names accordingly.

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_server_app.py::TestGitEndpoints -v`
Expected: FAIL (404 — routes don't exist yet)

**Step 3: Write minimal implementation**

In `src/elspais/server/app.py`, add after the persistence endpoints section (~line 740):

```python
    # ─────────────────────────────────────────────────────────────────
    # Git sync endpoints
    # ─────────────────────────────────────────────────────────────────

    @app.route("/api/git/status")
    def api_git_status():
        """GET /api/git/status - Branch info and dirty spec files."""
        from elspais.utilities.git import git_status_summary

        spec_dir = _state["config"].get("spec", {}).get("directories", ["spec"])[0]
        result = git_status_summary(_state["working_dir"], spec_dir=spec_dir)
        return jsonify(result)

    @app.route("/api/git/branch", methods=["POST"])
    def api_git_branch():
        """POST /api/git/branch - Create and switch to a new branch."""
        from elspais.utilities.git import create_and_switch_branch

        data = request.get_json(force=True)
        name = data.get("name", "").strip()
        if not name:
            return jsonify({"success": False, "error": "Branch name required"}), 400

        result = create_and_switch_branch(_state["working_dir"], name)
        status_code = 200 if result.get("success") else 400
        return jsonify(result), status_code

    @app.route("/api/git/push", methods=["POST"])
    def api_git_push():
        """POST /api/git/push - Stage spec files, commit, and push."""
        from elspais.utilities.git import commit_and_push_spec_files

        data = request.get_json(force=True)
        message = data.get("message", "").strip()
        if not message:
            return jsonify({"success": False, "error": "Commit message required"}), 400

        spec_dir = _state["config"].get("spec", {}).get("directories", ["spec"])[0]
        result = commit_and_push_spec_files(
            _state["working_dir"], message=message, spec_dir=spec_dir,
        )
        if not result.get("success") and "cannot commit" in result.get("error", "").lower():
            return jsonify(result), 403
        status_code = 200 if result.get("success") else 400
        return jsonify(result), status_code

    @app.route("/api/git/pull", methods=["POST"])
    def api_git_pull():
        """POST /api/git/pull - Fast-forward pull only."""
        from elspais.utilities.git import pull_ff_only

        result = pull_ff_only(_state["working_dir"])
        return jsonify(result)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_server_app.py::TestGitEndpoints -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/elspais/server/app.py tests/test_server_app.py
git commit -m "[CUR-1081] feat: add /api/git/* endpoints for viewer git sync"
```

---

## Task 6: Branch Indicator in Header

**Files:**
- Modify: `src/elspais/html/templates/partials/_header.html.j2` (lines 36-54)
- Modify: `src/elspais/html/templates/partials/css/_edit-mode.css.j2`
- Modify: `src/elspais/html/templates/partials/js/_edit-engine.js.j2`

**Step 1: Add branch badge HTML**

In `_header.html.j2`, insert before the `edit-toggle` button (before line 37):

```html
<span class="branch-badge" id="branch-badge" title="Current git branch">
    <span class="branch-status-dot" id="branch-status-dot"></span>
    <span id="branch-name">...</span>
    <button class="branch-refresh-btn hidden" id="branch-refresh-btn"
            onclick="doGitPull()" title="Pull latest changes">&#x21bb;</button>
    <span class="branch-warning hidden" id="branch-warning" title="Remote has diverged; merge conflicts possible later">!</span>
</span>
```

**Step 2: Add branch badge CSS**

In `_edit-mode.css.j2`, append:

```css
/* ── Branch badge ────────────────────────────────────────────── */
.branch-badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.85em;
    font-family: monospace;
    background: var(--bg-secondary, #f0f0f0);
    border: 1px solid var(--border-color, #ccc);
    margin-right: 8px;
}
.branch-status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--color-neutral, #888);
}
.branch-status-dot.green { background: #22c55e; }
.branch-status-dot.blue  { background: #3b82f6; }
.branch-status-dot.red   { background: #ef4444; }
.branch-refresh-btn {
    background: none;
    border: none;
    cursor: pointer;
    font-size: 1em;
    padding: 0 2px;
    color: var(--text-secondary, #666);
}
.branch-refresh-btn:hover { color: var(--text-primary, #333); }
.branch-warning {
    color: #ef4444;
    font-weight: bold;
    font-size: 1.1em;
}
```

**Step 3: Add branch status polling JS**

In `_edit-engine.js.j2`, add after the existing `refreshDirtyCount` function:

```javascript
/* ── Branch status ───────────────────────────────────────── */
async function refreshBranchStatus() {
    var data = await apiFetch('/api/git/status');
    if (!data) return;

    var dot = document.getElementById('branch-status-dot');
    var nameEl = document.getElementById('branch-name');
    var refreshBtn = document.getElementById('branch-refresh-btn');
    var warningEl = document.getElementById('branch-warning');

    nameEl.textContent = data.branch || 'detached';

    // Color logic
    dot.className = 'branch-status-dot';
    if (data.is_main) {
        dot.classList.add('red');
    } else if (data.dirty_spec_files.length > 0) {
        dot.classList.add('blue');
    } else {
        dot.classList.add('green');
    }

    // Refresh icon: show when remote has new commits
    refreshBtn.classList.toggle('hidden', !data.remote_diverged || !data.fast_forward_possible);

    // Warning icon: show when diverged and NOT fast-forwardable
    warningEl.classList.toggle('hidden', !data.remote_diverged || data.fast_forward_possible);

    return data;
}

async function doGitPull() {
    var result = await apiFetch('/api/git/pull', {method: 'POST'});
    if (result && result.success) {
        showToast('Pulled latest changes', 'success');
        refreshBranchStatus();
    } else {
        showToast(result.reason || 'Pull failed', 'error');
    }
}

// Poll branch status on load and every 60s
refreshBranchStatus();
setInterval(refreshBranchStatus, 60000);
```

**Step 4: Test manually**

Run: `elspais viewer` and verify:
- Branch badge appears next to Edit toggle
- Shows current branch name with colored dot
- Dot is red on main, green/blue on feature branches

**Step 5: Commit**

```bash
git add src/elspais/html/templates/partials/_header.html.j2 \
       src/elspais/html/templates/partials/css/_edit-mode.css.j2 \
       src/elspais/html/templates/partials/js/_edit-engine.js.j2
git commit -m "[CUR-1081] feat: add branch indicator badge to viewer header"
```

---

## Task 7: Branch Creation Modal

**Files:**
- Modify: `src/elspais/html/templates/partials/js/_edit-engine.js.j2`
- Modify: `src/elspais/html/templates/partials/css/_edit-mode.css.j2`

**Step 1: Add modal HTML (injected via JS)**

In `_edit-engine.js.j2`, add a function that creates and shows the branch modal:

```javascript
/* ── Branch creation modal ───────────────────────────────── */
function showBranchModal(reason, callback) {
    // Remove existing modal if any
    var old = document.getElementById('branch-modal-overlay');
    if (old) old.remove();

    var overlay = document.createElement('div');
    overlay.id = 'branch-modal-overlay';
    overlay.className = 'modal-overlay';
    overlay.innerHTML =
        '<div class="modal-dialog">' +
            '<div class="modal-title">' + reason + '</div>' +
            '<label class="modal-label">Branch name:</label>' +
            '<input type="text" class="modal-input" id="branch-name-input" ' +
                'placeholder="my-feature-branch" autocomplete="off">' +
            '<div class="modal-error hidden" id="branch-modal-error"></div>' +
            '<div class="modal-actions">' +
                '<button class="btn btn-primary" id="branch-modal-create">Create Branch</button>' +
                '<button class="btn" id="branch-modal-cancel">Cancel</button>' +
            '</div>' +
        '</div>';
    document.body.appendChild(overlay);

    var input = document.getElementById('branch-name-input');
    var errorEl = document.getElementById('branch-modal-error');
    input.focus();

    function doCreate() {
        var name = input.value.trim();
        if (!name) {
            errorEl.textContent = 'Branch name is required';
            errorEl.classList.remove('hidden');
            return;
        }
        apiFetch('/api/git/branch', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name: name}),
        }).then(function(result) {
            if (result && result.success) {
                overlay.remove();
                showToast('Switched to branch: ' + name, 'success');
                refreshBranchStatus();
                if (callback) callback();
            } else {
                errorEl.textContent = result.error || 'Failed to create branch';
                errorEl.classList.remove('hidden');
            }
        });
    }

    document.getElementById('branch-modal-create').onclick = doCreate;
    document.getElementById('branch-modal-cancel').onclick = function() {
        overlay.remove();
    };
    input.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') doCreate();
        if (e.key === 'Escape') overlay.remove();
    });
}
```

**Step 2: Add modal CSS**

In `_edit-mode.css.j2`, append:

```css
/* ── Modal overlay ───────────────────────────────────────── */
.modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 10000;
}
.modal-dialog {
    background: var(--bg-primary, #fff);
    border-radius: 8px;
    padding: 24px;
    min-width: 360px;
    max-width: 480px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.2);
}
.modal-title {
    font-size: 1.1em;
    font-weight: 600;
    margin-bottom: 16px;
}
.modal-label {
    display: block;
    font-size: 0.9em;
    margin-bottom: 4px;
    color: var(--text-secondary, #666);
}
.modal-input {
    width: 100%;
    padding: 8px;
    border: 1px solid var(--border-color, #ccc);
    border-radius: 4px;
    font-family: monospace;
    font-size: 0.95em;
    box-sizing: border-box;
}
.modal-input:focus { outline: 2px solid var(--color-primary, #3b82f6); }
.modal-error {
    color: #ef4444;
    font-size: 0.85em;
    margin-top: 8px;
}
.modal-actions {
    display: flex;
    gap: 8px;
    margin-top: 16px;
    justify-content: flex-end;
}
```

**Step 3: Wire modal into load-time and edit-toggle guardrails**

In `_edit-engine.js.j2`, modify the initialization code (runs after DOM ready):

```javascript
// On load: check if on main with dirty spec files
refreshBranchStatus().then(function(data) {
    if (!data) return;
    if (data.is_main && data.dirty_spec_files.length > 0) {
        showBranchModal(
            'You have local spec changes on main. Enter a branch name to continue editing.',
            null
        );
    }
});
```

Modify `toggleEditMode()` to guard against main:

```javascript
function toggleEditMode() {
    if (!editState.enabled) {
        // Turning ON — check if on main
        apiFetch('/api/git/status').then(function(data) {
            if (data && data.is_main) {
                showBranchModal(
                    'Cannot edit on main. Enter a branch name to enable editing.',
                    function() {
                        editState.enabled = true;
                        document.body.classList.add('edit-mode');
                        document.getElementById('edit-toggle').classList.toggle('active', true);
                        document.querySelectorAll('.card-assertion-text').forEach(function(el) {
                            el.contentEditable = 'true';
                        });
                        saveState();
                    }
                );
                return;
            }
            // Not on main — toggle normally
            editState.enabled = true;
            document.body.classList.add('edit-mode');
            document.getElementById('edit-toggle').classList.toggle('active', true);
            document.querySelectorAll('.card-assertion-text').forEach(function(el) {
                el.contentEditable = 'true';
            });
            saveState();
        });
    } else {
        // Turning OFF — always allowed
        editState.enabled = false;
        document.body.classList.remove('edit-mode');
        document.getElementById('edit-toggle').classList.toggle('active', false);
        document.querySelectorAll('.card-assertion-text').forEach(function(el) {
            el.contentEditable = 'false';
        });
        saveState();
    }
}
```

**Step 4: Test manually**

Run: `elspais viewer` on main branch:
- With dirty spec files: modal appears on load
- Without: toggling Edit shows modal
- After entering branch name: switches branch, edit mode activates

**Step 5: Commit**

```bash
git add src/elspais/html/templates/partials/js/_edit-engine.js.j2 \
       src/elspais/html/templates/partials/css/_edit-mode.css.j2
git commit -m "[CUR-1081] feat: add branch creation modal with main-branch guardrail"
```

---

## Task 8: Push Modal

**Files:**
- Modify: `src/elspais/html/templates/partials/_header.html.j2`
- Modify: `src/elspais/html/templates/partials/js/_edit-engine.js.j2`

**Step 1: Add Push button to header**

In `_header.html.j2`, after the Revert button (after line 53), add:

```html
<button class="btn btn-success" id="btn-push" onclick="showPushModal()" disabled
        title="Commit and push spec changes">
    Push
</button>
```

**Step 2: Add push modal JS**

In `_edit-engine.js.j2`, add:

```javascript
/* ── Push modal ──────────────────────────────────────────── */
function showPushModal() {
    apiFetch('/api/git/status').then(function(data) {
        if (!data || data.is_main) return;

        var files = data.dirty_spec_files;

        var old = document.getElementById('branch-modal-overlay');
        if (old) old.remove();

        var fileListHtml = files.length > 0
            ? files.map(function(f) { return '<div class="modal-file">' + f + '</div>'; }).join('')
            : '<div class="modal-file muted">No modified spec files</div>';

        var overlay = document.createElement('div');
        overlay.id = 'branch-modal-overlay';
        overlay.className = 'modal-overlay';
        overlay.innerHTML =
            '<div class="modal-dialog">' +
                '<div class="modal-title">Commit &amp; Push</div>' +
                '<div class="modal-label">Branch: <strong>' + data.branch + '</strong></div>' +
                '<div class="modal-label" style="margin-top:12px">Modified spec files:</div>' +
                '<div class="modal-file-list">' + fileListHtml + '</div>' +
                '<label class="modal-label" style="margin-top:12px">Commit message:</label>' +
                '<input type="text" class="modal-input" id="push-message-input" ' +
                    'placeholder="Update requirements" autocomplete="off">' +
                '<div class="modal-error hidden" id="push-modal-error"></div>' +
                '<div class="modal-actions">' +
                    '<button class="btn btn-primary" id="push-modal-confirm"' +
                    (files.length === 0 ? ' disabled' : '') + '>Push</button>' +
                    '<button class="btn" id="push-modal-cancel">Cancel</button>' +
                '</div>' +
            '</div>';
        document.body.appendChild(overlay);

        var input = document.getElementById('push-message-input');
        var errorEl = document.getElementById('push-modal-error');
        input.focus();

        function doPush() {
            var msg = input.value.trim();
            if (!msg) {
                errorEl.textContent = 'Commit message is required';
                errorEl.classList.remove('hidden');
                return;
            }
            // Save mutations to disk first, then push
            apiFetch('/api/save', {method: 'POST'}).then(function(saveResult) {
                if (saveResult && !saveResult.success) {
                    errorEl.textContent = 'Save failed: ' + (saveResult.error || 'unknown');
                    errorEl.classList.remove('hidden');
                    return;
                }
                return apiFetch('/api/git/push', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({message: msg}),
                });
            }).then(function(result) {
                if (!result) return;
                if (result.success) {
                    overlay.remove();
                    var toast = 'Pushed ' + (result.files_committed || []).length + ' file(s)';
                    if (result.push_error) {
                        toast += ' (commit OK, push failed: ' + result.push_error + ')';
                        showToast(toast, 'warning');
                    } else {
                        showToast(toast, 'success');
                    }
                    refreshBranchStatus();
                    refreshDirtyCount();
                } else {
                    errorEl.textContent = result.error || 'Push failed';
                    errorEl.classList.remove('hidden');
                }
            });
        }

        document.getElementById('push-modal-confirm').onclick = doPush;
        document.getElementById('push-modal-cancel').onclick = function() {
            overlay.remove();
        };
        input.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') doPush();
            if (e.key === 'Escape') overlay.remove();
        });
    });
}
```

**Step 3: Add push button enable/disable logic**

In the `refreshBranchStatus()` function, add at the end (before `return data`):

```javascript
    // Push button: enabled when not on main AND dirty spec files exist
    var pushBtn = document.getElementById('btn-push');
    if (pushBtn) {
        pushBtn.disabled = data.is_main || data.dirty_spec_files.length === 0;
    }
```

**Step 4: Add file list CSS**

In `_edit-mode.css.j2`, append:

```css
/* ── Push modal file list ────────────────────────────────── */
.modal-file-list {
    max-height: 120px;
    overflow-y: auto;
    border: 1px solid var(--border-color, #ccc);
    border-radius: 4px;
    padding: 4px;
}
.modal-file {
    font-family: monospace;
    font-size: 0.85em;
    padding: 2px 6px;
}
.modal-file.muted { color: var(--text-secondary, #999); }

/* ── Push button (success variant) ───────────────────────── */
.btn-success {
    background: #22c55e;
    color: #fff;
    border: none;
}
.btn-success:hover:not(:disabled) { background: #16a34a; }
.btn-success:disabled { opacity: 0.5; cursor: not-allowed; }
```

**Step 5: Test manually**

Run: `elspais viewer` on a feature branch, make edits, click Push:
- Modal shows branch, files, message field
- Saves to disk, commits, pushes
- Badge turns green after push

**Step 6: Commit**

```bash
git add src/elspais/html/templates/partials/_header.html.j2 \
       src/elspais/html/templates/partials/js/_edit-engine.js.j2 \
       src/elspais/html/templates/partials/css/_edit-mode.css.j2
git commit -m "[CUR-1081] feat: add push modal for commit-and-push workflow"
```

---

## Task 9: Unsaved Changes Warning

**Files:**
- Modify: `src/elspais/html/templates/partials/js/_edit-engine.js.j2`

**Step 1: Add beforeunload handler**

In `_edit-engine.js.j2`, add near the initialization section:

```javascript
/* ── Unsaved changes warning ─────────────────────────────── */
window.addEventListener('beforeunload', function(e) {
    // Check pending mutations
    var dirtyBadge = document.getElementById('unsaved-badge');
    var hasMutations = dirtyBadge && !dirtyBadge.classList.contains('hidden') &&
                       parseInt(dirtyBadge.textContent, 10) > 0;

    // Check uncommitted spec files (from last branch status poll)
    var dot = document.getElementById('branch-status-dot');
    var hasUncommitted = dot && dot.classList.contains('blue');

    if (hasMutations || hasUncommitted) {
        e.preventDefault();
        // Modern browsers ignore custom messages but require returnValue
        e.returnValue = '';
    }
});
```

**Step 2: Test manually**

1. Open viewer, make an edit (don't save) -> close tab -> browser warns
2. Save to disk but don't push (blue dot) -> close tab -> browser warns
3. Push successfully (green dot, no mutations) -> close tab -> no warning

**Step 3: Commit**

```bash
git add src/elspais/html/templates/partials/js/_edit-engine.js.j2
git commit -m "[CUR-1081] feat: add unsaved changes warning on window close"
```

---

## Task 10: Integration Test

**Files:**
- Create: `tests/e2e/test_viewer_git_sync.py`

**Step 1: Write e2e test**

```python
"""E2E tests for viewer git sync feature."""
import subprocess

import pytest

from elspais.utilities.git import (
    commit_and_push_spec_files,
    create_and_switch_branch,
    git_status_summary,
    pull_ff_only,
)


@pytest.mark.e2e
class TestViewerGitSyncWorkflow:
    """Full workflow: main -> create branch -> edit -> commit -> push."""

    def test_full_workflow_no_remote(self, tmp_path):
        """Complete flow without a remote (push skipped)."""
        # Init repo on main
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "main"], cwd=tmp_path, capture_output=True)
        (tmp_path / "spec").mkdir()
        (tmp_path / "spec" / "prd.md").write_text("# REQ-p00001 Original\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=tmp_path, capture_output=True,
            env={**__import__("os").environ, "GIT_AUTHOR_NAME": "Test",
                 "GIT_AUTHOR_EMAIL": "test@test.com",
                 "GIT_COMMITTER_NAME": "Test",
                 "GIT_COMMITTER_EMAIL": "test@test.com"},
        )

        # Step 1: Status shows main + clean
        status = git_status_summary(tmp_path)
        assert status["is_main"] is True
        assert status["dirty_spec_files"] == []

        # Step 2: Dirty a spec file (simulates external edit before viewer)
        (tmp_path / "spec" / "prd.md").write_text("# REQ-p00001 Modified\n")
        status = git_status_summary(tmp_path)
        assert status["dirty_spec_files"] == ["spec/prd.md"]

        # Step 3: Create branch (carries dirty files)
        result = create_and_switch_branch(tmp_path, "edit-prd")
        assert result["success"] is True
        assert (tmp_path / "spec" / "prd.md").read_text() == "# REQ-p00001 Modified\n"

        # Step 4: Verify branch switched
        status = git_status_summary(tmp_path)
        assert status["branch"] == "edit-prd"
        assert status["is_main"] is False

        # Step 5: Commit (no push — no remote)
        result = commit_and_push_spec_files(
            tmp_path, message="Update PRD", push=False,
        )
        assert result["success"] is True
        assert "spec/prd.md" in result["files_committed"]

        # Step 6: Status is clean after commit
        status = git_status_summary(tmp_path)
        assert status["dirty_spec_files"] == []
```

**Step 2: Run test**

Run: `pytest tests/e2e/test_viewer_git_sync.py -v -m e2e`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/e2e/test_viewer_git_sync.py
git commit -m "[CUR-1081] test: add e2e test for viewer git sync workflow"
```

---

## Task 11: Update KNOWN_ISSUES.md

**Files:**
- Modify: `KNOWN_ISSUES.md`

**Step 1: Mark the issue as done**

Change:
```
[ ] Viwer Git Push
```
To:
```
[x] Viewer Git Push
```

**Step 2: Commit**

```bash
git add KNOWN_ISSUES.md
git commit -m "[CUR-1081] docs: mark Viewer Git Push as complete in KNOWN_ISSUES"
```
