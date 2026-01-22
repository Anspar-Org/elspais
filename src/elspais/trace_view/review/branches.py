#!/usr/bin/env python3
"""
Review Branch Management Module for trace_view

Handles git branch operations for the review system:
- Branch naming and parsing
- Branch creation, checkout, push, fetch
- Branch listing and discovery
- Conflict detection

Branch naming convention: reviews/{package_id}/{username}
- Package-first naming enables discovery of all branches for a package
- User-specific branches enable isolated work without merge conflicts

Implements:
    REQ-d00004: Review Git Audit Trail
    REQ-d00009: Git Branch Management
"""

import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

# =============================================================================
# Constants
# =============================================================================

REVIEW_BRANCH_PREFIX = "reviews/"


# =============================================================================
# Data Classes (REQ-d00009)
# =============================================================================


@dataclass
class BranchInfo:
    """
    Metadata about a review branch for CLI display.

    REQ-d00009: Branch info data class for listing and cleanup operations.
    """

    name: str  # Full branch name: reviews/{pkg}/{user}
    package_id: str  # Package identifier
    username: str  # User who owns the branch
    last_commit_date: datetime  # Date of last commit on branch
    is_current: bool  # True if this is the current branch
    has_remote: bool  # True if remote tracking branch exists
    is_merged: bool  # True if merged into main

    @property
    def age_days(self) -> int:
        """Calculate age in days from last commit."""
        now = datetime.now(timezone.utc)
        if self.last_commit_date.tzinfo is None:
            # Assume UTC if no timezone
            last = self.last_commit_date.replace(tzinfo=timezone.utc)
        else:
            last = self.last_commit_date
        delta = now - last
        return delta.days


# =============================================================================
# Branch Naming (REQ-d00009-A, B)
# =============================================================================


def get_review_branch_name(package_id: str, user: str) -> str:
    """
    Generate a review branch name from package and user.

    REQ-d00009-A: Review branches SHALL follow the naming convention
                     `reviews/{package_id}/{username}`.
    REQ-d00009-B: This function SHALL return the formatted branch name.

    Args:
        package_id: Review package identifier (e.g., 'default', 'q1-2025-review')
        user: Username

    Returns:
        Branch name in format: reviews/{package}/{user}

    Examples:
        >>> get_review_branch_name('default', 'alice')
        'reviews/default/alice'
        >>> get_review_branch_name('q1-review', 'bob')
        'reviews/q1-review/bob'
    """
    # Sanitize both package and user for git branch
    sanitized_package = _sanitize_branch_name(package_id)
    sanitized_user = _sanitize_branch_name(user)
    return f"{REVIEW_BRANCH_PREFIX}{sanitized_package}/{sanitized_user}"


def _sanitize_branch_name(name: str) -> str:
    """
    Sanitize a string for use in a git branch name.

    Replaces spaces with hyphens and removes invalid characters.
    """
    # Replace spaces with hyphens
    name = name.replace(" ", "-")
    # Remove invalid characters (keep alphanumeric, hyphen, underscore)
    name = re.sub(r"[^a-zA-Z0-9_-]", "", name)
    # Remove leading/trailing hyphens
    name = name.strip("-")
    # Convert to lowercase
    return name.lower()


# =============================================================================
# Branch Parsing (REQ-d00009-C, D)
# =============================================================================


def parse_review_branch_name(branch_name: str) -> Optional[Tuple[str, str]]:
    """
    Parse a review branch name into (package_id, user).

    REQ-d00009-C: This function SHALL extract and return a tuple of
                     `(package_id, username)` from a valid branch name.

    Args:
        branch_name: Full branch name

    Returns:
        Tuple of (package_id, user) or None if not a valid review branch

    Examples:
        >>> parse_review_branch_name('reviews/default/alice')
        ('default', 'alice')
        >>> parse_review_branch_name('reviews/q1-review/bob')
        ('q1-review', 'bob')
        >>> parse_review_branch_name('main')
        None
    """
    if not is_review_branch(branch_name):
        return None

    # Remove prefix
    remainder = branch_name[len(REVIEW_BRANCH_PREFIX) :]
    parts = remainder.split("/", 1)

    if len(parts) != 2 or not parts[0] or not parts[1]:
        return None

    # Returns (package_id, user)
    return (parts[0], parts[1])


def is_review_branch(branch_name: str) -> bool:
    """
    Check if a branch name is a valid review branch.

    REQ-d00009-D: This function SHALL return True only for branches
                     matching the `reviews/{package}/{user}` pattern.

    Args:
        branch_name: Branch name to check

    Returns:
        True if valid review branch format (reviews/{package}/{user})

    Examples:
        >>> is_review_branch('reviews/default/alice')
        True
        >>> is_review_branch('reviews/q1-review/bob')
        True
        >>> is_review_branch('main')
        False
        >>> is_review_branch('reviews/default')  # Missing user
        False
    """
    if not branch_name.startswith(REVIEW_BRANCH_PREFIX):
        return False

    remainder = branch_name[len(REVIEW_BRANCH_PREFIX) :]
    parts = remainder.split("/", 1)

    # Must have both package and user
    return len(parts) == 2 and bool(parts[0]) and bool(parts[1])


# =============================================================================
# Git Utilities
# =============================================================================


def _run_git(repo_root: Path, args: List[str], check: bool = False) -> subprocess.CompletedProcess:
    """
    Run a git command in the repository.

    Args:
        repo_root: Repository root path
        args: Git command arguments
        check: If True, raise on non-zero exit code

    Returns:
        CompletedProcess result
    """
    try:
        return subprocess.run(
            ["git"] + args, cwd=repo_root, capture_output=True, text=True, check=check
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        # Return a fake failed result
        return subprocess.CompletedProcess(
            args=["git"] + args, returncode=1, stdout="", stderr="Error running git"
        )


def get_current_branch(repo_root: Path) -> Optional[str]:
    """
    Get the current git branch name.

    Args:
        repo_root: Repository root path

    Returns:
        Branch name or None if not in a git repo
    """
    result = _run_git(repo_root, ["rev-parse", "--abbrev-ref", "HEAD"])
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def get_remote_name(repo_root: Path) -> Optional[str]:
    """
    Get the default remote name (usually 'origin').

    Args:
        repo_root: Repository root path

    Returns:
        Remote name or None if no remotes configured
    """
    result = _run_git(repo_root, ["remote"])
    if result.returncode != 0 or not result.stdout.strip():
        return None
    # Return first remote
    return result.stdout.strip().split("\n")[0]


# =============================================================================
# Git Audit Trail (REQ-d00004)
# =============================================================================


def get_head_commit_hash(repo_root: Path) -> Optional[str]:
    """
    Get the current HEAD commit hash (full 40 characters).

    REQ-d00004-A: Package SHALL record creationCommitHash when created.
    REQ-d00004-C: Package SHALL update lastReviewedCommitHash on each comment activity.

    Args:
        repo_root: Repository root path

    Returns:
        Full commit hash (40 chars) or None if not in a git repo
    """
    result = _run_git(repo_root, ["rev-parse", "HEAD"])
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def get_short_commit_hash(repo_root: Path, length: int = 7) -> Optional[str]:
    """
    Get the current HEAD commit hash (short version).

    Args:
        repo_root: Repository root path
        length: Length of short hash (default: 7)

    Returns:
        Short commit hash or None if not in a git repo
    """
    result = _run_git(repo_root, ["rev-parse", f"--short={length}", "HEAD"])
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def get_git_context(repo_root: Path) -> dict:
    """
    Get current git context (branch name and commit hash) for audit trail.

    REQ-d00004: Track git context for review packages.

    Args:
        repo_root: Repository root path

    Returns:
        Dictionary with 'branchName' and 'commitHash' keys (values may be None)
    """
    return {
        "branchName": get_current_branch(repo_root),
        "commitHash": get_head_commit_hash(repo_root),
    }


def commit_exists(repo_root: Path, commit_hash: str) -> bool:
    """
    Check if a commit exists in the repository.

    REQ-d00004-F: Commit tracking SHALL handle squash-merge scenarios gracefully.

    This is useful for checking if archived commit hashes still exist after
    squash-merge operations.

    Args:
        repo_root: Repository root path
        commit_hash: Commit hash to check (full or short)

    Returns:
        True if commit exists, False otherwise
    """
    result = _run_git(repo_root, ["cat-file", "-t", commit_hash])
    return result.returncode == 0 and result.stdout.strip() == "commit"


def branch_exists(repo_root: Path, branch_name: str) -> bool:
    """
    Check if a local branch exists.

    Args:
        repo_root: Repository root path
        branch_name: Branch name to check

    Returns:
        True if branch exists locally
    """
    result = _run_git(repo_root, ["rev-parse", "--verify", f"refs/heads/{branch_name}"])
    return result.returncode == 0


def remote_branch_exists(repo_root: Path, branch_name: str, remote: str = "origin") -> bool:
    """
    Check if a remote branch exists.

    Args:
        repo_root: Repository root path
        branch_name: Branch name to check
        remote: Remote name

    Returns:
        True if branch exists on remote
    """
    result = _run_git(repo_root, ["rev-parse", "--verify", f"refs/remotes/{remote}/{branch_name}"])
    return result.returncode == 0


# =============================================================================
# Branch Metadata (REQ-d00009 Service Layer)
# =============================================================================


def get_branch_last_commit_date(repo_root: Path, branch_name: str) -> Optional[datetime]:
    """
    Get the date of the last commit on a branch.

    REQ-d00009: Service layer function for CLI branch listing.

    Args:
        repo_root: Repository root path
        branch_name: Full branch name (e.g., 'reviews/default/alice')

    Returns:
        datetime of last commit in UTC, or None if branch doesn't exist

    Examples:
        >>> get_branch_last_commit_date(repo, 'reviews/default/alice')
        datetime.datetime(2025, 1, 8, 12, 30, 45, tzinfo=timezone.utc)
    """
    # Use git log to get the commit date in ISO format
    result = _run_git(repo_root, ["log", "-1", "--format=%cI", branch_name])
    if result.returncode != 0 or not result.stdout.strip():
        return None

    date_str = result.stdout.strip()
    try:
        # Parse ISO 8601 date format (e.g., 2025-01-08T12:30:45+00:00)
        dt = datetime.fromisoformat(date_str)
        # Ensure UTC timezone
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def is_branch_merged(repo_root: Path, branch_name: str, target_branch: str = "main") -> bool:
    """
    Check if a branch has been merged into the target branch.

    REQ-d00009: Service layer function for cleanup operations.

    Args:
        repo_root: Repository root path
        branch_name: Branch to check (e.g., 'reviews/default/alice')
        target_branch: Target branch to check against (default: 'main')

    Returns:
        True if branch_name is fully merged into target_branch

    Examples:
        >>> is_branch_merged(repo, 'reviews/default/alice')
        True  # alice's branch has been merged to main
        >>> is_branch_merged(repo, 'reviews/default/bob', 'develop')
        False  # bob's branch not merged to develop
    """
    # git branch --merged <target> lists branches merged into target
    result = _run_git(repo_root, ["branch", "--merged", target_branch])
    if result.returncode != 0:
        return False

    # Parse branch list and check if our branch is in it
    merged_branches = []
    for line in result.stdout.strip().split("\n"):
        branch = line.strip().lstrip("* ")
        if branch:
            merged_branches.append(branch)

    return branch_name in merged_branches


def has_unpushed_commits(repo_root: Path, branch_name: str, remote: str = "origin") -> bool:
    """
    Check if a branch has commits not pushed to remote.

    REQ-d00009: Safety check before branch deletion.

    Args:
        repo_root: Repository root path
        branch_name: Branch to check
        remote: Remote name (default: 'origin')

    Returns:
        True if branch has commits not on remote, or remote doesn't exist
    """
    # Check if remote branch exists
    if not remote_branch_exists(repo_root, branch_name, remote):
        # No remote tracking - consider it as "has unpushed"
        # (unless there's no remote at all)
        if get_remote_name(repo_root) is None:
            return False  # No remote configured, nothing to push
        return True  # Remote exists but branch not pushed

    # Compare local and remote
    result = _run_git(repo_root, ["rev-list", "--count", f"{remote}/{branch_name}..{branch_name}"])
    if result.returncode != 0:
        return True  # Assume unpushed if we can't check

    try:
        count = int(result.stdout.strip())
        return count > 0
    except ValueError:
        return True


def get_branch_info(repo_root: Path, branch_name: str) -> Optional[BranchInfo]:
    """
    Get detailed metadata about a review branch.

    REQ-d00009: Service layer function combining all branch metadata.

    Args:
        repo_root: Repository root path
        branch_name: Full branch name (e.g., 'reviews/default/alice')

    Returns:
        BranchInfo dataclass with all metadata, or None if not a valid review branch

    Examples:
        >>> info = get_branch_info(repo, 'reviews/default/alice')
        >>> info.package_id
        'default'
        >>> info.age_days
        3
    """
    # Must be a valid review branch
    parsed = parse_review_branch_name(branch_name)
    if parsed is None:
        return None

    package_id, username = parsed

    # Must exist locally
    if not branch_exists(repo_root, branch_name):
        return None

    # Get last commit date
    last_commit = get_branch_last_commit_date(repo_root, branch_name)
    if last_commit is None:
        # Branch exists but can't get commit date - use epoch
        last_commit = datetime(1970, 1, 1, tzinfo=timezone.utc)

    # Check if current branch
    current = get_current_branch(repo_root)
    is_current = current == branch_name

    # Check remote existence
    has_remote = remote_branch_exists(repo_root, branch_name)

    # Check if merged
    is_merged = is_branch_merged(repo_root, branch_name)

    return BranchInfo(
        name=branch_name,
        package_id=package_id,
        username=username,
        last_commit_date=last_commit,
        is_current=is_current,
        has_remote=has_remote,
        is_merged=is_merged,
    )


# =============================================================================
# Package Context (REQ-d00009-F)
# =============================================================================


def get_current_package_context(repo_root: Path) -> Tuple[Optional[str], Optional[str]]:
    """
    Get current (package_id, user) from branch name.

    REQ-d00009-F: This function SHALL return `(package_id, username)` when
                     on a review branch, or `(None, None)` otherwise.

    Args:
        repo_root: Repository root path

    Returns:
        Tuple of (package_id, user) or (None, None) if not on a review branch

    Examples:
        >>> get_current_package_context(repo)
        ('q1-review', 'alice')  # When on reviews/q1-review/alice
        >>> get_current_package_context(repo)
        (None, None)  # When on main branch
    """
    current_branch = get_current_branch(repo_root)
    if not current_branch:
        return (None, None)

    parsed = parse_review_branch_name(current_branch)
    if parsed:
        return parsed
    return (None, None)


# =============================================================================
# Branch Discovery (REQ-d00009-E)
# =============================================================================


def list_package_branches(repo_root: Path, package_id: str) -> List[str]:
    """
    List all local review branches for a specific package.

    REQ-d00009-E: This function SHALL return all branch names for a given
                     package across all users.

    Args:
        repo_root: Repository root path
        package_id: Package identifier (e.g., 'default', 'q1-review')

    Returns:
        List of branch names matching reviews/{package_id}/*

    Examples:
        >>> list_package_branches(repo, 'default')
        ['reviews/default/alice', 'reviews/default/bob']
    """
    sanitized_package = _sanitize_branch_name(package_id)
    pattern = f"{REVIEW_BRANCH_PREFIX}{sanitized_package}/*"
    return _list_branches_by_pattern(repo_root, pattern)


def _list_branches_by_pattern(repo_root: Path, pattern: str) -> List[str]:
    """
    List local branches matching a pattern.

    Args:
        repo_root: Repository root path
        pattern: Git branch pattern (e.g., 'reviews/default/*')

    Returns:
        List of matching branch names
    """
    result = _run_git(repo_root, ["branch", "--list", pattern])
    if result.returncode != 0:
        return []

    branches = []
    for line in result.stdout.strip().split("\n"):
        branch = line.strip().lstrip("* ")
        if branch and is_review_branch(branch):
            branches.append(branch)

    return branches


def list_local_review_branches(repo_root: Path, user: Optional[str] = None) -> List[str]:
    """
    List all local review branches.

    Args:
        repo_root: Repository root path
        user: Optional filter by username (matches second component of branch)

    Returns:
        List of branch names
    """
    result = _run_git(repo_root, ["branch", "--list", "reviews/*"])
    if result.returncode != 0:
        return []

    branches = []
    for line in result.stdout.strip().split("\n"):
        # Remove leading * and whitespace
        branch = line.strip().lstrip("* ")
        if branch and is_review_branch(branch):
            if user is None:
                branches.append(branch)
            else:
                parsed = parse_review_branch_name(branch)
                # User is second component: reviews/{package}/{user}
                if parsed and parsed[1] == user:
                    branches.append(branch)

    return branches


# =============================================================================
# Branch Operations
# =============================================================================


def create_review_branch(repo_root: Path, package_id: str, user: str) -> str:
    """
    Create a new review branch.

    Args:
        repo_root: Repository root path
        package_id: Review package identifier
        user: Username

    Returns:
        Created branch name (reviews/{package}/{user})

    Raises:
        ValueError: If branch already exists
        RuntimeError: If branch creation fails
    """
    branch_name = get_review_branch_name(package_id, user)

    if branch_exists(repo_root, branch_name):
        raise ValueError(f"Branch already exists: {branch_name}")

    result = _run_git(repo_root, ["branch", branch_name])
    if result.returncode != 0:
        raise RuntimeError(f"Failed to create branch: {result.stderr}")

    return branch_name


def checkout_review_branch(repo_root: Path, package_id: str, user: str) -> bool:
    """
    Checkout a review branch.

    Args:
        repo_root: Repository root path
        package_id: Review package identifier
        user: Username

    Returns:
        True if checkout succeeded, False if branch doesn't exist
    """
    branch_name = get_review_branch_name(package_id, user)

    if not branch_exists(repo_root, branch_name):
        return False

    result = _run_git(repo_root, ["checkout", branch_name])
    return result.returncode == 0


# =============================================================================
# Change Detection
# =============================================================================


def has_uncommitted_changes(repo_root: Path) -> bool:
    """
    Check if there are uncommitted changes.

    REQ-d00009-H: Part of conflict detection - detects local changes.

    Args:
        repo_root: Repository root path

    Returns:
        True if there are uncommitted changes (staged or unstaged)
    """
    result = _run_git(repo_root, ["status", "--porcelain"])
    return bool(result.stdout.strip())


def has_reviews_changes(repo_root: Path) -> bool:
    """
    Check if there are uncommitted changes in .reviews/ directory.

    Args:
        repo_root: Repository root path

    Returns:
        True if .reviews/ has uncommitted changes
    """
    reviews_dir = repo_root / ".reviews"
    if not reviews_dir.exists():
        return False

    result = _run_git(repo_root, ["status", "--porcelain", ".reviews/"])
    return bool(result.stdout.strip())


def has_conflicts(repo_root: Path) -> bool:
    """
    Check if there are merge conflicts in the repository.

    REQ-d00009-H: Branch operations SHALL detect and report conflicts.

    Args:
        repo_root: Repository root path

    Returns:
        True if there are unresolved merge conflicts
    """
    # Check for merge in progress
    git_dir = repo_root / ".git"
    if (git_dir / "MERGE_HEAD").exists():
        # Merge in progress, check for conflict markers
        result = _run_git(repo_root, ["diff", "--check"])
        return result.returncode != 0

    # Check for conflict markers in staged files
    result = _run_git(repo_root, ["diff", "--cached", "--check"])
    if result.returncode != 0:
        return True

    # Also check working tree
    result = _run_git(repo_root, ["diff", "--check"])
    return result.returncode != 0


# =============================================================================
# Commit and Push Operations (REQ-d00009-G)
# =============================================================================


def commit_reviews(repo_root: Path, message: str, user: str = "system") -> bool:
    """
    Commit changes to .reviews/ directory.

    Args:
        repo_root: Repository root path
        message: Commit message
        user: Username for commit attribution

    Returns:
        True if commit succeeded (or no changes to commit)
    """
    # Check if there are changes to commit
    if not has_reviews_changes(repo_root):
        return True  # No changes, success

    # Stage .reviews/ changes
    result = _run_git(repo_root, ["add", ".reviews/"])
    if result.returncode != 0:
        return False

    # Commit with message
    full_message = f"[review] {message}\n\nBy: {user}"
    result = _run_git(repo_root, ["commit", "-m", full_message])
    return result.returncode == 0


def commit_and_push_reviews(
    repo_root: Path, message: str, user: str = "system", remote: str = "origin"
) -> Tuple[bool, str]:
    """
    Commit changes to .reviews/ and push to remote.

    REQ-d00009-G: This function SHALL commit all changes in `.reviews/`
                     and push to the remote tracking branch.

    Args:
        repo_root: Repository root path
        message: Commit message describing the change
        user: Username for commit attribution
        remote: Remote name to push to

    Returns:
        Tuple of (success: bool, message: str)
    """
    # Check if there are changes
    if not has_reviews_changes(repo_root):
        return (True, "No changes to commit")

    # Stage .reviews/ changes
    result = _run_git(repo_root, ["add", ".reviews/"])
    if result.returncode != 0:
        return (False, f"Failed to stage changes: {result.stderr}")

    # Commit with message
    full_message = f"[review] {message}\n\nBy: {user}"
    result = _run_git(repo_root, ["commit", "-m", full_message])
    if result.returncode != 0:
        return (False, f"Failed to commit: {result.stderr}")

    # Check if remote exists
    if get_remote_name(repo_root) is None:
        return (True, "Committed locally (no remote configured)")

    # Push to remote
    current_branch = get_current_branch(repo_root)
    if current_branch:
        push_result = _run_git(repo_root, ["push", remote, current_branch])
        if push_result.returncode == 0:
            return (True, "Committed and pushed successfully")
        else:
            # Commit succeeded but push failed - still return success for commit
            return (True, f"Committed locally (push failed: {push_result.stderr})")

    return (True, "Committed locally")


# =============================================================================
# Fetch Operations (REQ-d00009-I)
# =============================================================================


def fetch_package_branches(repo_root: Path, package_id: str, remote: str = "origin") -> List[str]:
    """
    Fetch all remote branches for a package.

    REQ-d00009-I: This function SHALL fetch all remote branches for a
                     package to enable merge operations.

    Args:
        repo_root: Repository root path
        package_id: Package identifier
        remote: Remote name

    Returns:
        List of fetched branch names for the package
    """
    # Check if remote exists
    if get_remote_name(repo_root) is None:
        return []

    sanitized_package = _sanitize_branch_name(package_id)
    refspec = (
        f"refs/heads/{REVIEW_BRANCH_PREFIX}{sanitized_package}/*:"
        f"refs/remotes/{remote}/{REVIEW_BRANCH_PREFIX}{sanitized_package}/*"
    )

    # Fetch the specific package branches
    _run_git(repo_root, ["fetch", remote, refspec])

    # Even if fetch fails (e.g., no matching refs), list what we have
    branches = []
    list_result = _run_git(
        repo_root,
        ["branch", "-r", "--list", f"{remote}/{REVIEW_BRANCH_PREFIX}{sanitized_package}/*"],
    )

    if list_result.returncode == 0:
        for line in list_result.stdout.strip().split("\n"):
            branch = line.strip()
            if branch:
                branches.append(branch)

    return branches


def fetch_review_branches(repo_root: Path, remote: str = "origin") -> bool:
    """
    Fetch all review branches from remote.

    Args:
        repo_root: Repository root path
        remote: Remote name

    Returns:
        True if fetch succeeded
    """
    if get_remote_name(repo_root) is None:
        return False

    result = _run_git(repo_root, ["fetch", remote, "--prune"])
    return result.returncode == 0


# =============================================================================
# Branch Listing and Cleanup (REQ-d00009 CLI Service Layer)
# =============================================================================


@dataclass
class CleanupResult:
    """
    Result of a branch cleanup operation.

    REQ-d00009: Cleanup result for CLI feedback.
    """

    deleted_local: List[str]  # Branches deleted locally
    deleted_remote: List[str]  # Branches deleted from remote
    skipped_current: List[str]  # Skipped because current branch
    skipped_unpushed: List[str]  # Skipped because has unpushed commits
    skipped_unmerged: List[str]  # Skipped because not merged
    errors: List[Tuple[str, str]]  # (branch, error_message) pairs


def list_review_branches_with_info(
    repo_root: Path, package_id: Optional[str] = None, user: Optional[str] = None
) -> List[BranchInfo]:
    """
    List all review branches with their metadata.

    REQ-d00009: Service layer function for CLI --review-branches.

    Args:
        repo_root: Repository root path
        package_id: Optional filter by package ID
        user: Optional filter by username

    Returns:
        List of BranchInfo objects for matching branches

    Examples:
        >>> branches = list_review_branches_with_info(repo)
        >>> for b in branches:
        ...     print(f"{b.name}: {b.age_days}d old, merged={b.is_merged}")
    """
    # Get all review branches
    if package_id:
        branch_names = list_package_branches(repo_root, package_id)
    else:
        branch_names = list_local_review_branches(repo_root)

    # Filter by user if specified
    if user:
        filtered = []
        for name in branch_names:
            parsed = parse_review_branch_name(name)
            if parsed and parsed[1] == user:
                filtered.append(name)
        branch_names = filtered

    # Get info for each branch
    branches = []
    for name in branch_names:
        info = get_branch_info(repo_root, name)
        if info:
            branches.append(info)

    # Sort by last commit date (most recent first)
    branches.sort(key=lambda b: b.last_commit_date, reverse=True)

    return branches


def delete_review_branch(
    repo_root: Path,
    branch_name: str,
    delete_remote: bool = False,
    force: bool = False,
    remote: str = "origin",
) -> Tuple[bool, str]:
    """
    Delete a review branch with safety checks.

    REQ-d00009: Service layer function for CLI cleanup.

    Args:
        repo_root: Repository root path
        branch_name: Branch name to delete
        delete_remote: Also delete the remote branch
        force: Force deletion even if not merged
        remote: Remote name (default: 'origin')

    Returns:
        Tuple of (success: bool, message: str)

    Safety checks:
        - Never deletes current branch
        - Warns about unmerged branches (unless force=True)
        - Warns about unpushed commits (unless force=True)

    Examples:
        >>> success, msg = delete_review_branch(repo, 'reviews/default/alice')
        >>> if success:
        ...     print("Deleted!")
    """
    # Safety check: never delete current branch
    current = get_current_branch(repo_root)
    if current == branch_name:
        return (False, f"Cannot delete current branch: {branch_name}")

    # Safety check: verify it's a review branch
    if not is_review_branch(branch_name):
        return (False, f"Not a review branch: {branch_name}")

    # Safety check: verify branch exists
    if not branch_exists(repo_root, branch_name):
        return (False, f"Branch does not exist: {branch_name}")

    # Safety check: check for unpushed commits (unless force)
    if not force and has_unpushed_commits(repo_root, branch_name, remote):
        return (False, f"Branch has unpushed commits: {branch_name}")

    # Safety check: check if merged (unless force)
    if not force and not is_branch_merged(repo_root, branch_name):
        return (False, f"Branch is not merged into main: {branch_name}")

    # Delete local branch
    delete_flag = "-D" if force else "-d"
    result = _run_git(repo_root, ["branch", delete_flag, branch_name])
    if result.returncode != 0:
        return (False, f"Failed to delete local branch: {result.stderr}")

    # Delete remote branch if requested
    if delete_remote and remote_branch_exists(repo_root, branch_name, remote):
        result = _run_git(repo_root, ["push", remote, "--delete", branch_name])
        if result.returncode != 0:
            return (True, f"Deleted local branch, but failed to delete remote: {result.stderr}")
        return (True, f"Deleted local and remote branch: {branch_name}")

    return (True, f"Deleted local branch: {branch_name}")


def cleanup_review_branches(
    repo_root: Path,
    package_id: Optional[str] = None,
    max_age_days: Optional[int] = None,
    only_merged: bool = True,
    delete_remote: bool = False,
    dry_run: bool = False,
    remote: str = "origin",
) -> CleanupResult:
    """
    Delete review branches matching criteria.

    REQ-d00009: Service layer function for CLI --cleanup-reviews
    and --cleanup-stale-reviews.

    Args:
        repo_root: Repository root path
        package_id: Optional filter by package ID
        max_age_days: Only delete branches older than N days (stale cleanup)
        only_merged: Only delete branches merged into main (default: True)
        delete_remote: Also delete remote tracking branches
        dry_run: If True, don't actually delete, just return what would be deleted
        remote: Remote name (default: 'origin')

    Returns:
        CleanupResult with lists of deleted/skipped branches

    Examples:
        >>> result = cleanup_review_branches(repo, only_merged=True)
        >>> print(f"Deleted {len(result.deleted_local)} branches")

        >>> result = cleanup_review_branches(repo, max_age_days=30, dry_run=True)
        >>> print(f"Would delete {len(result.deleted_local)} branches")
    """
    result = CleanupResult(
        deleted_local=[],
        deleted_remote=[],
        skipped_current=[],
        skipped_unpushed=[],
        skipped_unmerged=[],
        errors=[],
    )

    # Get branches to consider
    branches = list_review_branches_with_info(repo_root, package_id=package_id)
    current = get_current_branch(repo_root)

    for branch in branches:
        # Skip current branch
        if branch.is_current or branch.name == current:
            result.skipped_current.append(branch.name)
            continue

        # Skip if not old enough (when max_age_days is set)
        if max_age_days is not None and branch.age_days < max_age_days:
            continue

        # Skip if only_merged and branch is not merged
        if only_merged and not branch.is_merged:
            result.skipped_unmerged.append(branch.name)
            continue

        # Skip if has unpushed commits (safety)
        if has_unpushed_commits(repo_root, branch.name, remote):
            result.skipped_unpushed.append(branch.name)
            continue

        # Delete the branch (or record for dry run)
        if dry_run:
            result.deleted_local.append(branch.name)
            if delete_remote and branch.has_remote:
                result.deleted_remote.append(branch.name)
        else:
            # Delete local branch
            delete_result = _run_git(repo_root, ["branch", "-d", branch.name])
            if delete_result.returncode == 0:
                result.deleted_local.append(branch.name)

                # Delete remote if requested
                if delete_remote and branch.has_remote:
                    remote_result = _run_git(repo_root, ["push", remote, "--delete", branch.name])
                    if remote_result.returncode == 0:
                        result.deleted_remote.append(branch.name)
                    else:
                        result.errors.append(
                            (branch.name, f"Failed to delete remote: {remote_result.stderr}")
                        )
            else:
                result.errors.append((branch.name, f"Failed to delete: {delete_result.stderr}"))

    return result
