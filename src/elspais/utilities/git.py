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


def _extract_req_locations_from_graph(graph: Any, repo_root: Path | None = None) -> dict[str, str]:
    """Extract REQ ID -> file path mapping from a TraceGraph.

    This is the graph-based replacement for the old regex-based extraction.
    Uses the same parsing logic that build_graph() uses.

    Args:
        graph: A TraceGraph instance.
        repo_root: Repository root for relativizing paths (uses graph.repo_root if None).

    Returns:
        Dict mapping REQ ID (just the suffix, e.g., 'd00001') to relative file path.
    """
    from elspais.graph.GraphNode import NodeKind

    req_locations: dict[str, str] = {}

    # Get repo_root for path relativization
    if repo_root is None:
        repo_root = getattr(graph, "repo_root", None)

    for node in graph.all_nodes():
        if node.kind == NodeKind.REQUIREMENT and node.source:
            # Extract just the suffix (e.g., 'd00001' from 'REQ-d00001')
            req_id = node.id
            if req_id.startswith("REQ-"):
                # Handle possible associated prefix like "REQ-CAL-d00001"
                parts = req_id[4:].split("-")
                if len(parts) >= 2 and len(parts[0]) > 1 and parts[0].isupper():
                    # Has associated prefix (e.g., "CAL-d00001"), use last part
                    req_id = parts[-1]
                else:
                    # No prefix, just use what's after "REQ-"
                    req_id = parts[-1]

            # Get source path and make it relative if needed
            source_path = node.source.path
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
        Dict mapping REQ ID (e.g., 'd00001') to relative file path.
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
    # Safety branch utilities (REQ-o00063)
    "get_current_branch",
    "create_safety_branch",
    "list_safety_branches",
    "restore_from_safety_branch",
    "delete_safety_branch",
]
