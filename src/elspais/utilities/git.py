"""Git state management for elspais.

Provides functions to query git status and detect changes to requirement files,
enabling detection of:
- Uncommitted changes to spec files
- New (untracked) requirement files
- Files changed vs main/master branch
- Moved requirements (comparing current location to committed state)
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _clean_git_env() -> dict[str, str]:
    """Return environment with GIT_DIR/GIT_WORK_TREE removed.

    Use when running git commands with explicit cwd to prevent
    inherited git context from overriding the provided path.
    """
    env = os.environ.copy()
    env.pop("GIT_DIR", None)
    env.pop("GIT_WORK_TREE", None)
    return env


# Implements: REQ-p00004-B
@contextmanager
def temporary_worktree(repo_root: Path, ref: str = "HEAD") -> Iterator[Path]:
    """Create a temporary git worktree for a ref.

    Creates a detached worktree at the specified ref, yields its path,
    then cleans up the worktree automatically on exit.

    Usage:
        with temporary_worktree(repo_root, "HEAD") as worktree_path:
            committed_graph = build_graph(repo_root=worktree_path)
            # work with committed state...

    Args:
        repo_root: Path to the repository root.
        ref: Git ref to checkout (default: HEAD).

    Yields:
        Path to the temporary worktree.

    Raises:
        subprocess.CalledProcessError: If git worktree commands fail.
    """
    with tempfile.TemporaryDirectory() as tmp:
        worktree_path = Path(tmp) / "worktree"

        subprocess.run(
            ["git", "worktree", "add", "--detach", str(worktree_path), ref],
            cwd=repo_root,
            env=_clean_git_env(),
            capture_output=True,
            check=True,
        )

        try:
            yield worktree_path
        finally:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree_path)],
                cwd=repo_root,
                env=_clean_git_env(),
                capture_output=True,
            )


@dataclass
class GitChangeInfo:
    """Information about git changes to requirement files.

    Attributes:
        modified_files: Files with uncommitted modifications (staged or unstaged).
        untracked_files: New files not yet tracked by git.
        branch_changed_files: Files changed between current branch and main/master.
        committed_req_locations: REQ ID -> file path mapping from committed state (HEAD).
    """

    modified_files: set[str] = field(default_factory=set)
    untracked_files: set[str] = field(default_factory=set)
    branch_changed_files: set[str] = field(default_factory=set)
    committed_req_locations: dict[str, str] = field(default_factory=dict)

    @property
    def all_changed_files(self) -> set[str]:
        """Get all files with any kind of change."""
        return self.modified_files | self.untracked_files | self.branch_changed_files

    @property
    def uncommitted_files(self) -> set[str]:
        """Get all files with uncommitted changes (modified or untracked)."""
        return self.modified_files | self.untracked_files


@dataclass
class MovedRequirement:
    """Information about a requirement that was moved between files.

    Attributes:
        req_id: The requirement ID (e.g., 'd00001').
        old_path: Path in the committed state.
        new_path: Path in the current working directory.
    """

    req_id: str
    old_path: str
    new_path: str


# Implements: REQ-p00004-B
def get_repo_root(start_path: Path | None = None) -> Path | None:
    """Find the git repository root.

    Args:
        start_path: Path to start searching from (default: current directory)

    Returns:
        Path to repository root, or None if not in a git repository
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=start_path or Path.cwd(),
            env=_clean_git_env() if start_path else None,
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(result.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


# Implements: REQ-p00004-B
def get_modified_files(repo_root: Path) -> tuple[set[str], set[str]]:
    """Get sets of modified and untracked files according to git status.

    Args:
        repo_root: Path to repository root

    Returns:
        Tuple of (modified_files, untracked_files):
        - modified_files: Tracked files with changes (M, A, R, etc.)
        - untracked_files: New files not yet tracked (??)
    """
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=repo_root,
            env=_clean_git_env(),
            capture_output=True,
            text=True,
            check=True,
        )
        modified_files: set[str] = set()
        untracked_files: set[str] = set()

        for line in result.stdout.split("\n"):
            if line and len(line) >= 3:
                # Format: "XY filename" or "XY orig -> renamed"
                # XY = two-letter status (e.g., " M", "??", "A ", "R ")
                status_code = line[:2]
                file_path = line[3:].strip()

                # Handle renames: "orig -> new"
                if " -> " in file_path:
                    file_path = file_path.split(" -> ")[1]

                if file_path:
                    if status_code == "??":
                        untracked_files.add(file_path)
                    else:
                        modified_files.add(file_path)

        return modified_files, untracked_files
    except (subprocess.CalledProcessError, FileNotFoundError):
        return set(), set()


# Implements: REQ-p00004-B
def get_changed_vs_branch(repo_root: Path, base_branch: str = "main") -> set[str]:
    """Get set of files changed between current branch and base branch.

    Args:
        repo_root: Path to repository root
        base_branch: Name of base branch (default: 'main')

    Returns:
        Set of file paths changed vs base branch
    """
    # Try local branch first, then remote
    for branch_ref in [base_branch, f"origin/{base_branch}"]:
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", f"{branch_ref}...HEAD"],
                cwd=repo_root,
                env=_clean_git_env(),
                capture_output=True,
                text=True,
                check=True,
            )
            changed_files: set[str] = set()
            for line in result.stdout.split("\n"):
                if line.strip():
                    changed_files.add(line.strip())
            return changed_files
        except subprocess.CalledProcessError:
            continue
        except FileNotFoundError:
            return set()

    return set()


# Implements: REQ-p00004-B
def _extract_req_locations_from_graph(graph: Any, repo_root: Path | None = None) -> dict[str, str]:
    """Extract REQ ID -> file path mapping from a TraceGraph.

    This is the graph-based replacement for the old regex-based extraction.
    Uses the same parsing logic that build_graph() uses.

    Args:
        graph: A TraceGraph instance.
        repo_root: Repository root for relativizing paths (uses graph.repo_root if None).

    Returns:
        Dict mapping full canonical REQ ID (e.g., 'REQ-d00001') to relative file path.
    """
    from elspais.graph.GraphNode import NodeKind

    req_locations: dict[str, str] = {}

    # Get repo_root for path relativization
    if repo_root is None:
        repo_root = getattr(graph, "repo_root", None)

    # Implements: REQ-d00129-D
    for node in graph.all_nodes():
        if node.kind == NodeKind.REQUIREMENT:
            fn = node.file_node()
            if not fn:
                continue
            # Use the full canonical node ID as the key.
            # This avoids hardcoded prefix stripping and works with any
            # namespace/type pattern configured via [id-patterns].
            req_id = node.id

            # Get source path from FILE node and make it relative if needed
            source_path = fn.get_field("relative_path") or ""
            if repo_root:
                try:
                    # If path is absolute, make it relative to repo_root
                    path_obj = Path(source_path)
                    if path_obj.is_absolute():
                        source_path = str(path_obj.relative_to(repo_root))
                except ValueError:
                    # Path is not relative to repo_root, keep as-is
                    pass

            req_locations[req_id] = source_path

    return req_locations


# Implements: REQ-p00004-B
def get_req_locations_from_graph(
    repo_root: Path,
    scan_sponsors: bool = False,
) -> dict[str, str]:
    """Get REQ ID -> file path mapping from a graph built at the given path.

    This is the graph-based approach that uses build_graph() to parse
    requirements using the project's configuration.

    Args:
        repo_root: Path to repository root (or worktree path).
        scan_sponsors: Whether to include sponsor/associated repos.

    Returns:
        Dict mapping full canonical REQ ID (e.g., 'REQ-d00001') to relative file path.
    """
    from elspais.graph.factory import build_graph

    # Build graph with minimal scanning (we only need requirements)
    graph = build_graph(
        repo_root=repo_root,
        scan_code=False,
        scan_tests=False,
        scan_sponsors=scan_sponsors,
    )

    return _extract_req_locations_from_graph(graph, repo_root)


# Implements: REQ-p00004-B
def detect_moved_requirements(
    committed_locations: dict[str, str],
    current_locations: dict[str, str],
) -> list[MovedRequirement]:
    """Detect requirements that have been moved between files.

    Args:
        committed_locations: REQ ID -> path mapping from committed state
        current_locations: REQ ID -> path mapping from current state

    Returns:
        List of MovedRequirement objects for requirements whose location changed
    """
    moved = []
    for req_id, old_path in committed_locations.items():
        if req_id in current_locations:
            new_path = current_locations[req_id]
            if old_path != new_path:
                moved.append(
                    MovedRequirement(
                        req_id=req_id,
                        old_path=old_path,
                        new_path=new_path,
                    )
                )
    return moved


# Implements: REQ-p00004-B
def get_git_changes(
    repo_root: Path | None = None,
    spec_dir: str = "spec",
    base_branch: str = "main",
    base_ref: str = "HEAD",
) -> GitChangeInfo:
    """Get comprehensive git change information for requirement files.

    This is the main entry point for git change detection. It gathers:
    - Modified files (uncommitted changes to tracked files)
    - Untracked files (new files not yet in git)
    - Branch changed files (files changed vs main/master)
    - Committed REQ locations (for move detection via graph-based comparison)

    Uses git worktree + build_graph() to properly parse committed state,
    respecting project configuration rather than hardcoded regex patterns.

    Args:
        repo_root: Path to repository root (auto-detected if None)
        spec_dir: Spec directory relative to repo root (deprecated, ignored)
        base_branch: Base branch for comparison (default: 'main')
        base_ref: Git ref for committed state comparison (default: 'HEAD')

    Returns:
        GitChangeInfo with all change information
    """
    if repo_root is None:
        repo_root = get_repo_root()
        if repo_root is None:
            return GitChangeInfo()

    modified, untracked = get_modified_files(repo_root)
    branch_changed = get_changed_vs_branch(repo_root, base_branch)

    # Get committed locations using graph-based approach via git worktree
    committed_locations: dict[str, str] = {}
    try:
        with temporary_worktree(repo_root, base_ref) as worktree_path:
            committed_locations = get_req_locations_from_graph(worktree_path)
    except subprocess.CalledProcessError:
        # Worktree creation failed (e.g., no commits yet), fall back to empty
        pass

    return GitChangeInfo(
        modified_files=modified,
        untracked_files=untracked,
        branch_changed_files=branch_changed,
        committed_req_locations=committed_locations,
    )


# Implements: REQ-p00004-B
def filter_spec_files(files: set[str], spec_dir: str = "spec") -> set[str]:
    """Filter a set of files to only include spec directory files.

    Args:
        files: Set of file paths
        spec_dir: Spec directory prefix

    Returns:
        Set of files that are in the spec directory
    """
    prefix = f"{spec_dir}/"
    return {f for f in files if f.startswith(prefix) and f.endswith(".md")}


# ─────────────────────────────────────────────────────────────────────────────
# Safety Branch Utilities (REQ-o00063)
# ─────────────────────────────────────────────────────────────────────────────


# Implements: REQ-o00063-D
def get_current_branch(repo_root: Path) -> str | None:
    """Get the name of the current git branch.

    Args:
        repo_root: Path to repository root

    Returns:
        Branch name, or None if not on a branch (detached HEAD)
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_root,
            env=_clean_git_env(),
            capture_output=True,
            text=True,
            check=True,
        )
        branch = result.stdout.strip()
        return branch if branch != "HEAD" else None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


# Implements: REQ-d00128-C
def get_current_commit(repo_root: Path) -> str | None:
    """Get the current git commit hash (short form).

    Args:
        repo_root: Path to repository root

    Returns:
        Short commit hash, or None if not in a git repo
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root,
            env=_clean_git_env(),
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip() or None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


# Implements: REQ-p00004-C
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
    prefix = f"{spec_dir}/"
    dirty_spec = sorted(f for f in all_dirty if f.startswith(prefix))

    # Check remote divergence
    remote_diverged = False
    fast_forward_possible = False
    main_diverged = False
    local_ahead_count = 0
    env = _clean_git_env()
    if branch:
        try:
            # Fetch without modifying working tree
            subprocess.run(
                ["git", "fetch", "--quiet"],
                cwd=repo_root,
                env=env,
                capture_output=True,
                timeout=10,
            )
            # Check if remote tracking branch has diverged from local
            remote_ref = f"origin/{branch}"
            result = subprocess.run(
                ["git", "rev-list", "--left-right", "--count", f"{branch}...{remote_ref}"],
                cwd=repo_root,
                env=env,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split()
                if len(parts) == 2:
                    local_ahead = int(parts[0])
                    remote_ahead = int(parts[1])
                    local_ahead_count = local_ahead
                    remote_diverged = remote_ahead > 0
                    fast_forward_possible = remote_ahead > 0 and local_ahead == 0

            # Check if main has diverged since branch point (informational)
            if not is_main:
                for main_name in main_branches:
                    remote_main = f"origin/{main_name}"
                    # Find merge-base between this branch and remote main
                    mb = subprocess.run(
                        ["git", "merge-base", branch, remote_main],
                        cwd=repo_root,
                        env=env,
                        capture_output=True,
                        text=True,
                    )
                    if mb.returncode != 0:
                        continue
                    merge_base = mb.stdout.strip()
                    # Check if remote main has moved past the merge-base
                    tip = subprocess.run(
                        ["git", "rev-parse", remote_main],
                        cwd=repo_root,
                        env=env,
                        capture_output=True,
                        text=True,
                    )
                    if tip.returncode == 0 and tip.stdout.strip() != merge_base:
                        main_diverged = True
                    break  # Only check the first matching main branch
        except (
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
            FileNotFoundError,
            ValueError,
        ):
            pass  # No remote or fetch failed — treat as not diverged

    return {
        "branch": branch,
        "is_main": is_main,
        "dirty_spec_files": dirty_spec,
        "local_ahead": local_ahead_count,
        "remote_diverged": remote_diverged,
        "fast_forward_possible": fast_forward_possible,
        "main_diverged": main_diverged,
    }


# Implements: REQ-p00004-D
def create_and_switch_branch(
    repo_root: Path,
    branch_name: str,
) -> dict[str, Any]:
    """Create a new git branch and switch to it, preserving dirty working tree.

    If the working tree has uncommitted changes, they are stashed before the
    branch switch and popped on the new branch.  If branch creation fails and
    changes were stashed, the stash is popped to restore the original state.

    Args:
        repo_root: Path to repository root.
        branch_name: Name for the new branch.

    Returns:
        Dict with ``success`` (bool) and either ``branch`` (str) or ``error`` (str).
    """
    # Validate branch name
    if not branch_name or not branch_name.strip():
        return {"success": False, "error": "Branch name must not be empty"}

    # git check-ref-format to validate
    try:
        subprocess.run(
            ["git", "check-ref-format", "--branch", branch_name],
            cwd=repo_root,
            env=_clean_git_env(),
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        return {"success": False, "error": f"Invalid branch name: {branch_name}"}
    except FileNotFoundError:
        return {"success": False, "error": "git not found"}

    # Check if dirty
    modified, untracked = get_modified_files(repo_root)
    is_dirty = bool(modified or untracked)

    # Stash if dirty
    if is_dirty:
        try:
            subprocess.run(
                [
                    "git",
                    "stash",
                    "push",
                    "--include-untracked",
                    "-m",
                    f"elspais: switching to {branch_name}",
                ],
                cwd=repo_root,
                env=_clean_git_env(),
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            return {"success": False, "error": f"Failed to stash changes: {e.stderr}"}
        except FileNotFoundError:
            return {"success": False, "error": "git not found"}

    # Create and switch to the new branch
    try:
        subprocess.run(
            ["git", "checkout", "-b", branch_name],
            cwd=repo_root,
            env=_clean_git_env(),
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        # Restore stash if we stashed
        if is_dirty:
            subprocess.run(
                ["git", "stash", "pop"],
                cwd=repo_root,
                env=_clean_git_env(),
                capture_output=True,
            )
        return {"success": False, "error": f"Failed to create branch: {e.stderr}"}
    except FileNotFoundError:
        if is_dirty:
            subprocess.run(
                ["git", "stash", "pop"],
                cwd=repo_root,
                env=_clean_git_env(),
                capture_output=True,
            )
        return {"success": False, "error": "git not found"}

    # Pop stash on new branch
    if is_dirty:
        try:
            subprocess.run(
                ["git", "stash", "pop"],
                cwd=repo_root,
                env=_clean_git_env(),
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            return {
                "success": True,
                "branch": branch_name,
                "warning": f"Branch created but stash pop failed: {e.stderr}",
            }

    return {"success": True, "branch": branch_name}


# Implements: REQ-p00004-E
def commit_and_push_spec_files(
    repo_root: Path,
    message: str,
    spec_dir: str = "spec",
    push: bool = True,
    main_branches: tuple[str, ...] = ("main", "master"),
) -> dict[str, Any]:
    """Stage all modified spec files, commit with message, and optionally push.

    Refuses to operate on main/master (or other protected) branches.

    Args:
        repo_root: Path to repository root.
        message: Commit message.
        spec_dir: Spec directory relative to repo root (default: ``"spec"``).
        push: Whether to push after committing (default: ``True``).
        main_branches: Branch names considered protected.

    Returns:
        Dict with ``success`` (bool), and either ``files_committed`` (list[str])
        or ``error`` (str).  If push fails the commit is still reported as
        successful with a ``push_error`` field.
    """
    # Refuse on protected branches
    branch = get_current_branch(repo_root)
    if branch in main_branches:
        return {
            "success": False,
            "error": f"Refusing to commit on protected branch '{branch}'",
        }

    # Find dirty spec files (modified + untracked)
    modified, untracked = get_modified_files(repo_root)
    all_dirty = modified | untracked
    prefix = f"{spec_dir}/"
    dirty_spec = sorted(f for f in all_dirty if f.startswith(prefix))

    if not dirty_spec:
        return {"success": False, "error": "Nothing to commit — no dirty spec files"}

    # Stage spec files
    try:
        subprocess.run(
            ["git", "add", "--"] + dirty_spec,
            cwd=repo_root,
            env=_clean_git_env(),
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        return {"success": False, "error": f"Failed to stage files: {e.stderr}"}
    except FileNotFoundError:
        return {"success": False, "error": "git not found"}

    # Commit
    try:
        subprocess.run(
            ["git", "commit", "-m", message],
            cwd=repo_root,
            env=_clean_git_env(),
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        import re as _re

        clean = _re.sub(r"\x1b\[[0-9;]*m", "", e.stderr or "").strip()
        return {"success": False, "error": f"Failed to commit: {clean}"}
    except FileNotFoundError:
        return {"success": False, "error": "git not found"}

    result: dict[str, Any] = {
        "success": True,
        "files_committed": dirty_spec,
    }

    # Optionally push (non-fatal if push fails)
    if push and branch:
        try:
            subprocess.run(
                ["git", "push", "-u", "origin", branch],
                cwd=repo_root,
                env=_clean_git_env(),
                capture_output=True,
                text=True,
                check=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            err_msg = e.stderr if hasattr(e, "stderr") else str(e)
            result["push_error"] = f"Commit succeeded but push failed: {err_msg}"

    return result


# Implements: REQ-p00004-F
def sync_branch(
    repo_root: Path,
    main_branches: tuple[str, ...] = ("main", "master"),
) -> dict[str, Any]:
    """Sync the current branch with its remote and with main.

    Performs up to two safe operations:

    1. **Merge remote tracking branch** — if ``origin/<branch>`` is ahead,
       attempt ``git merge --ff-only``.  If that fails (diverged), try
       ``git merge --no-edit`` and abort on conflict.
    2. **Rebase on updated main** — if ``origin/main`` has moved past the
       merge-base, attempt ``git rebase origin/main`` and abort on conflict.

    Both operations abort cleanly if conflicts are detected — the working
    tree is always left in a usable state.

    Args:
        repo_root: Path to repository root.
        main_branches: Branch names to try rebasing onto.

    Returns:
        Dict with ``success`` (bool), ``actions`` (list of descriptions),
        and optional ``error`` (str).
    """
    env = _clean_git_env()
    actions: list[str] = []
    branch = get_current_branch(repo_root)

    if not branch:
        return {"success": False, "error": "Not on a branch (detached HEAD)"}

    # 1. Fetch
    try:
        subprocess.run(
            ["git", "fetch"],
            cwd=repo_root,
            env=env,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Fetch timed out", "actions": actions}
    except subprocess.CalledProcessError as e:
        return {
            "success": False,
            "error": f"Fetch failed: {(e.stderr or '').strip()}",
            "actions": actions,
        }
    except FileNotFoundError:
        return {"success": False, "error": "git not found", "actions": actions}

    # 2. Merge remote tracking branch if ahead
    remote_ref = f"origin/{branch}"
    try:
        rev = subprocess.run(
            ["git", "rev-list", "--left-right", "--count", f"{branch}...{remote_ref}"],
            cwd=repo_root,
            env=env,
            capture_output=True,
            text=True,
        )
        if rev.returncode == 0:
            parts = rev.stdout.strip().split()
            if len(parts) == 2:
                remote_ahead = int(parts[1])
                if remote_ahead > 0:
                    # Try ff-only first
                    ff = subprocess.run(
                        ["git", "merge", "--ff-only", remote_ref],
                        cwd=repo_root,
                        env=env,
                        capture_output=True,
                        text=True,
                    )
                    if ff.returncode == 0:
                        actions.append(f"Fast-forwarded from {remote_ref}")
                    else:
                        # Try regular merge (auto-resolve)
                        mg = subprocess.run(
                            ["git", "merge", "--no-edit", remote_ref],
                            cwd=repo_root,
                            env=env,
                            capture_output=True,
                            text=True,
                        )
                        if mg.returncode == 0:
                            actions.append(f"Merged {remote_ref}")
                        else:
                            # Conflict — abort
                            subprocess.run(
                                ["git", "merge", "--abort"],
                                cwd=repo_root,
                                env=env,
                                capture_output=True,
                            )
                            return {
                                "success": False,
                                "error": f"Merge conflict with {remote_ref} — aborted",
                                "actions": actions,
                            }
    except (subprocess.CalledProcessError, ValueError):
        pass  # No remote tracking branch — skip merge step

    # 3. Rebase on updated main if diverged
    if branch not in main_branches:
        for main_name in main_branches:
            remote_main = f"origin/{main_name}"
            try:
                mb = subprocess.run(
                    ["git", "merge-base", branch, remote_main],
                    cwd=repo_root,
                    env=env,
                    capture_output=True,
                    text=True,
                )
                if mb.returncode != 0:
                    continue
                merge_base = mb.stdout.strip()
                tip = subprocess.run(
                    ["git", "rev-parse", remote_main],
                    cwd=repo_root,
                    env=env,
                    capture_output=True,
                    text=True,
                )
                if tip.returncode != 0 or tip.stdout.strip() == merge_base:
                    break  # Main hasn't moved — nothing to do

                # Main has moved — try rebase
                rb = subprocess.run(
                    ["git", "rebase", remote_main],
                    cwd=repo_root,
                    env=env,
                    capture_output=True,
                    text=True,
                )
                if rb.returncode == 0:
                    actions.append(f"Rebased on {remote_main}")
                else:
                    # Conflict — abort
                    subprocess.run(
                        ["git", "rebase", "--abort"],
                        cwd=repo_root,
                        env=env,
                        capture_output=True,
                    )
                    return {
                        "success": False,
                        "error": f"Rebase conflict on {remote_main} — aborted",
                        "actions": actions,
                    }
                break
            except (subprocess.CalledProcessError, ValueError):
                continue

    if not actions:
        return {"success": True, "message": "Already up to date", "actions": actions}

    return {"success": True, "message": "; ".join(actions), "actions": actions}


# Implements: REQ-o00063-D
def create_safety_branch(
    repo_root: Path,
    req_id: str,
) -> dict[str, Any]:
    """Create a safety branch with timestamped name before file mutations.

    Safety branches allow reverting file mutations by preserving the pre-mutation
    state of spec files.

    Args:
        repo_root: Path to repository root
        req_id: Requirement ID being modified (used in branch name)

    Returns:
        Dict with 'success', 'branch_name', and optional 'error'
    """
    from datetime import datetime

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    branch_name = f"safety/{req_id}-{timestamp}"

    try:
        # Create the branch at current HEAD
        subprocess.run(
            ["git", "branch", branch_name],
            cwd=repo_root,
            env=_clean_git_env(),
            capture_output=True,
            text=True,
            check=True,
        )
        return {"success": True, "branch_name": branch_name}
    except subprocess.CalledProcessError as e:
        return {"success": False, "error": f"Failed to create branch: {e.stderr}"}
    except FileNotFoundError:
        return {"success": False, "error": "git not found"}


# Implements: REQ-o00063-D
def list_safety_branches(repo_root: Path) -> list[str]:
    """List all safety branches in the repository.

    Args:
        repo_root: Path to repository root

    Returns:
        List of branch names starting with 'safety/'
    """
    try:
        result = subprocess.run(
            ["git", "branch", "--list", "safety/*"],
            cwd=repo_root,
            env=_clean_git_env(),
            capture_output=True,
            text=True,
            check=True,
        )
        branches = []
        for line in result.stdout.strip().split("\n"):
            if line:
                # Remove leading '* ' or '  ' from branch name
                branch = line.strip().lstrip("* ")
                if branch:
                    branches.append(branch)
        return branches
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []


# Implements: REQ-o00063-E
def restore_from_safety_branch(
    repo_root: Path,
    branch_name: str,
    spec_dir: str = "spec",
) -> dict[str, Any]:
    """Restore spec files from a safety branch.

    This checks out the spec directory from the safety branch, effectively
    reverting any file mutations made after the safety branch was created.

    Args:
        repo_root: Path to repository root
        branch_name: Name of the safety branch to restore from
        spec_dir: Spec directory relative to repo root

    Returns:
        Dict with 'success', 'files_restored', and optional 'error'
    """
    # Verify branch exists
    branches = list_safety_branches(repo_root)
    if branch_name not in branches:
        return {"success": False, "error": f"Branch '{branch_name}' not found"}

    try:
        # Checkout spec directory from safety branch
        subprocess.run(
            ["git", "checkout", branch_name, "--", f"{spec_dir}/"],
            cwd=repo_root,
            env=_clean_git_env(),
            capture_output=True,
            text=True,
            check=True,
        )

        # Get list of restored files
        status_result = subprocess.run(
            ["git", "diff", "--name-only", "--cached"],
            cwd=repo_root,
            env=_clean_git_env(),
            capture_output=True,
            text=True,
            check=True,
        )
        files_restored = [
            f for f in status_result.stdout.strip().split("\n") if f.startswith(spec_dir)
        ]

        # Reset staging area (we only want working directory changes)
        subprocess.run(
            ["git", "reset", "HEAD", f"{spec_dir}/"],
            cwd=repo_root,
            env=_clean_git_env(),
            capture_output=True,
            check=True,
        )

        return {"success": True, "files_restored": files_restored}
    except subprocess.CalledProcessError as e:
        return {"success": False, "error": f"Failed to restore: {e.stderr}"}
    except FileNotFoundError:
        return {"success": False, "error": "git not found"}


# Implements: REQ-o00063-D
def delete_safety_branch(
    repo_root: Path,
    branch_name: str,
) -> dict[str, Any]:
    """Delete a safety branch.

    Args:
        repo_root: Path to repository root
        branch_name: Name of the branch to delete

    Returns:
        Dict with 'success' and optional 'error'
    """
    # Only allow deleting safety branches
    if not branch_name.startswith("safety/"):
        return {"success": False, "error": "Can only delete safety/ branches"}

    try:
        subprocess.run(
            ["git", "branch", "-D", branch_name],
            cwd=repo_root,
            env=_clean_git_env(),
            capture_output=True,
            text=True,
            check=True,
        )
        return {"success": True}
    except subprocess.CalledProcessError as e:
        return {"success": False, "error": f"Failed to delete branch: {e.stderr}"}
    except FileNotFoundError:
        return {"success": False, "error": "git not found"}


# ─────────────────────────────────────────────────────────────────────────────
# Author Identity Resolution
# ─────────────────────────────────────────────────────────────────────────────


def get_author_info(id_source: str = "gh") -> dict[str, str]:
    """Resolve author name and identity for changelog entries.

    Args:
        id_source: Identity source — "gh" (GitHub CLI, falls back to git)
                   or "git" (git config only).

    Returns:
        Dict with "name" and "id" keys.

    Raises:
        ValueError: If required author info is unavailable or empty.
    """
    if id_source == "gh":
        try:
            import json as _json

            result = subprocess.run(
                ["gh", "api", "user"],
                capture_output=True,
                text=True,
                check=True,
            )
            data = _json.loads(result.stdout)
            name = data.get("name") or ""
            email = data.get("email") or ""
            if name and email:
                return {"name": name, "id": email}
        except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
            pass
        # Fall through to git fallback

    # Git config fallback
    name = _git_config("user.name")
    email = _git_config("user.email")

    if not name:
        raise ValueError("Author name not available from git config user.name")
    if not email:
        raise ValueError("Author ID not available from git config user.email")

    return {"name": name, "id": email}


def _git_config(key: str) -> str:
    """Read a git config value."""
    try:
        result = subprocess.run(
            ["git", "config", key],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


__all__ = [
    "GitChangeInfo",
    "MovedRequirement",
    "get_repo_root",
    "get_modified_files",
    "get_changed_vs_branch",
    "detect_moved_requirements",
    "get_git_changes",
    "filter_spec_files",
    # Graph-based location extraction
    "temporary_worktree",
    "get_req_locations_from_graph",
    # Git status summary (REQ-p00004-C)
    "git_status_summary",
    # Branch creation (REQ-p00004-D)
    "create_and_switch_branch",
    # Commit and push (REQ-p00004-E)
    "commit_and_push_spec_files",
    # Pull fast-forward (REQ-p00004-F)
    "sync_branch",
    # Safety branch utilities (REQ-o00063)
    "get_current_branch",
    "create_safety_branch",
    "list_safety_branches",
    "restore_from_safety_branch",
    "delete_safety_branch",
    # Author identity
    "get_author_info",
]
