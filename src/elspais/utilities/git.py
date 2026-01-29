"""Git state management for elspais.

Provides functions to query git status and detect changes to requirement files,
enabling detection of:
- Uncommitted changes to spec files
- New (untracked) requirement files
- Files changed vs main/master branch
- Moved requirements (comparing current location to committed state)
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


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


def get_committed_req_locations(
    repo_root: Path,
    spec_dir: str = "spec",
    exclude_files: list[str] | None = None,
) -> dict[str, str]:
    """Get REQ ID -> file path mapping from committed state (HEAD).

    This allows detection of moved requirements by comparing current location
    to where the REQ was in the last commit.

    Args:
        repo_root: Path to repository root
        spec_dir: Spec directory relative to repo root
        exclude_files: Files to exclude (default: INDEX.md, README.md)

    Returns:
        Dict mapping REQ ID (e.g., 'd00001') to relative file path
    """
    if exclude_files is None:
        exclude_files = ["INDEX.md", "README.md", "requirements-format.md"]

    req_locations: dict[str, str] = {}
    # Pattern matches REQ headers with optional associated prefix
    req_pattern = re.compile(r"^#{1,6}\s+REQ-(?:[A-Z]{2,4}-)?([pod]\d{5}):", re.MULTILINE)

    try:
        # Get list of spec files in committed state
        result = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", "HEAD", f"{spec_dir}/"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )

        for file_path in result.stdout.strip().split("\n"):
            if not file_path.endswith(".md"):
                continue
            if any(skip in file_path for skip in exclude_files):
                continue

            # Get file content from committed state
            try:
                content_result = subprocess.run(
                    ["git", "show", f"HEAD:{file_path}"],
                    cwd=repo_root,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                content = content_result.stdout

                # Find all REQ IDs in this file
                for match in req_pattern.finditer(content):
                    req_id = match.group(1)
                    req_locations[req_id] = file_path

            except subprocess.CalledProcessError:
                # File might not exist in HEAD (new file)
                continue

    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    return req_locations


def get_current_req_locations(
    repo_root: Path,
    spec_dir: str = "spec",
    exclude_files: list[str] | None = None,
) -> dict[str, str]:
    """Get REQ ID -> file path mapping from current working directory.

    Args:
        repo_root: Path to repository root
        spec_dir: Spec directory relative to repo root
        exclude_files: Files to exclude (default: INDEX.md, README.md)

    Returns:
        Dict mapping REQ ID (e.g., 'd00001') to relative file path
    """
    if exclude_files is None:
        exclude_files = ["INDEX.md", "README.md", "requirements-format.md"]

    req_locations: dict[str, str] = {}
    req_pattern = re.compile(r"^#{1,6}\s+REQ-(?:[A-Z]{2,4}-)?([pod]\d{5}):", re.MULTILINE)

    spec_path = repo_root / spec_dir
    if not spec_path.exists():
        return req_locations

    for md_file in spec_path.rglob("*.md"):
        if any(skip in md_file.name for skip in exclude_files):
            continue

        try:
            content = md_file.read_text(encoding="utf-8")
            rel_path = str(md_file.relative_to(repo_root))

            for match in req_pattern.finditer(content):
                req_id = match.group(1)
                req_locations[req_id] = rel_path

        except (OSError, UnicodeDecodeError):
            continue

    return req_locations


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
) -> GitChangeInfo:
    """Get comprehensive git change information for requirement files.

    This is the main entry point for git change detection. It gathers:
    - Modified files (uncommitted changes to tracked files)
    - Untracked files (new files not yet in git)
    - Branch changed files (files changed vs main/master)
    - Committed REQ locations (for move detection)

    Args:
        repo_root: Path to repository root (auto-detected if None)
        spec_dir: Spec directory relative to repo root
        base_branch: Base branch for comparison (default: 'main')

    Returns:
        GitChangeInfo with all change information
    """
    if repo_root is None:
        repo_root = get_repo_root()
        if repo_root is None:
            return GitChangeInfo()

    modified, untracked = get_modified_files(repo_root)
    branch_changed = get_changed_vs_branch(repo_root, base_branch)
    committed_locations = get_committed_req_locations(repo_root, spec_dir)

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
            capture_output=True,
            text=True,
            check=True,
        )

        # Get list of restored files
        status_result = subprocess.run(
            ["git", "diff", "--name-only", "--cached"],
            cwd=repo_root,
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
    "get_committed_req_locations",
    "get_current_req_locations",
    "detect_moved_requirements",
    "get_git_changes",
    "filter_spec_files",
    # Safety branch utilities (REQ-o00063)
    "get_current_branch",
    "create_safety_branch",
    "list_safety_branches",
    "restore_from_safety_branch",
    "delete_safety_branch",
]
