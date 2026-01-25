"""
elspais.mcp.git_safety - Git safety utilities for graph mutations.

Provides utilities for creating safety branches before risky operations,
checking for uncommitted changes, and restoring from branches.
"""

import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple


@dataclass
class GitStatus:
    """
    Status of the git repository.

    Attributes:
        has_uncommitted: True if there are uncommitted changes
        staged_files: List of staged file paths
        modified_files: List of modified (unstaged) file paths
        untracked_files: List of untracked file paths
        current_branch: Name of the current branch
        error: Error message if git commands failed
    """

    has_uncommitted: bool = False
    staged_files: List[str] = None
    modified_files: List[str] = None
    untracked_files: List[str] = None
    current_branch: Optional[str] = None
    error: Optional[str] = None

    def __post_init__(self):
        if self.staged_files is None:
            self.staged_files = []
        if self.modified_files is None:
            self.modified_files = []
        if self.untracked_files is None:
            self.untracked_files = []


@dataclass
class SafetyBranchResult:
    """
    Result of creating a safety branch.

    Attributes:
        success: True if branch was created successfully
        branch_name: Name of the created branch (None if failed)
        message: Description of the result
        stashed: True if changes were stashed
        stash_name: Name/message of the stash if created
    """

    success: bool
    branch_name: Optional[str]
    message: str
    stashed: bool = False
    stash_name: Optional[str] = None


class GitSafetyManager:
    """
    Manages git safety operations for graph mutations.

    Provides methods to create safety branches, check repository status,
    and restore from branches. Used by AITransformer and other mutation
    tools to ensure changes can be rolled back.

    Attributes:
        working_dir: Root directory of the git repository
    """

    BRANCH_PREFIX = "elspais-safety"

    def __init__(self, working_dir: Path):
        """
        Initialize the git safety manager.

        Args:
            working_dir: Root directory of the git repository
        """
        self.working_dir = working_dir.resolve()

    def get_status(self) -> GitStatus:
        """
        Get the current git repository status.

        Returns:
            GitStatus with repository information
        """
        try:
            # Get current branch
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=self.working_dir,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                return GitStatus(error=f"Not a git repository: {result.stderr.strip()}")

            current_branch = result.stdout.strip()

            # Get status
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.working_dir,
                capture_output=True,
                text=True,
            )

            staged = []
            modified = []
            untracked = []

            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                status = line[:2]
                filepath = line[3:]

                # Index status (first char)
                if status[0] in "MADRC":
                    staged.append(filepath)

                # Working tree status (second char)
                if status[1] in "MD":
                    modified.append(filepath)
                elif status == "??":
                    untracked.append(filepath)

            has_uncommitted = bool(staged or modified)

            return GitStatus(
                has_uncommitted=has_uncommitted,
                staged_files=staged,
                modified_files=modified,
                untracked_files=untracked,
                current_branch=current_branch,
            )

        except FileNotFoundError:
            return GitStatus(error="Git not found in PATH")
        except Exception as e:
            return GitStatus(error=str(e))

    def create_safety_branch(
        self,
        operation_name: str,
        node_ids: Optional[List[str]] = None,
        stash_if_dirty: bool = True,
    ) -> SafetyBranchResult:
        """
        Create a safety branch before a risky operation.

        Creates a branch from the current HEAD that can be used to
        restore the repository state if the operation fails or needs
        to be undone.

        If there are uncommitted changes and stash_if_dirty is True,
        they will be stashed before creating the branch.

        Args:
            operation_name: Name of the operation (used in branch name)
            node_ids: Optional list of node IDs being modified
            stash_if_dirty: If True, stash uncommitted changes

        Returns:
            SafetyBranchResult with the operation result
        """
        status = self.get_status()
        if status.error:
            return SafetyBranchResult(
                success=False,
                branch_name=None,
                message=f"Git error: {status.error}",
            )

        stashed = False
        stash_name = None

        # Handle uncommitted changes
        if status.has_uncommitted:
            if stash_if_dirty:
                stash_name = f"elspais-{operation_name}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
                result = subprocess.run(
                    ["git", "stash", "push", "-m", stash_name],
                    cwd=self.working_dir,
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    return SafetyBranchResult(
                        success=False,
                        branch_name=None,
                        message=f"Failed to stash changes: {result.stderr.strip()}",
                    )
                stashed = True
            else:
                return SafetyBranchResult(
                    success=False,
                    branch_name=None,
                    message="Uncommitted changes exist. Commit or stash them first.",
                )

        # Generate branch name
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        safe_op_name = operation_name.replace(" ", "-").replace("/", "-")[:30]
        node_suffix = ""
        if node_ids and len(node_ids) == 1:
            # Include single node ID in branch name
            safe_node = node_ids[0].replace("/", "-")[:20]
            node_suffix = f"-{safe_node}"
        elif node_ids:
            node_suffix = f"-{len(node_ids)}-nodes"

        branch_name = f"{self.BRANCH_PREFIX}/{safe_op_name}{node_suffix}-{timestamp}"

        # Create the branch
        result = subprocess.run(
            ["git", "branch", branch_name],
            cwd=self.working_dir,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            # Restore stash if we stashed
            if stashed:
                subprocess.run(
                    ["git", "stash", "pop"],
                    cwd=self.working_dir,
                    capture_output=True,
                )
            return SafetyBranchResult(
                success=False,
                branch_name=None,
                message=f"Failed to create branch: {result.stderr.strip()}",
            )

        return SafetyBranchResult(
            success=True,
            branch_name=branch_name,
            message=f"Created safety branch: {branch_name}",
            stashed=stashed,
            stash_name=stash_name,
        )

    def restore_from_branch(
        self,
        branch_name: str,
        restore_stash: bool = True,
    ) -> Tuple[bool, str]:
        """
        Restore the repository to the state of a safety branch.

        This does a hard reset to the branch, discarding all changes
        made since the branch was created.

        Args:
            branch_name: Name of the safety branch to restore from
            restore_stash: If True, look for and restore associated stash

        Returns:
            Tuple of (success, message)
        """
        # Check if branch exists
        result = subprocess.run(
            ["git", "rev-parse", "--verify", branch_name],
            cwd=self.working_dir,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return False, f"Branch not found: {branch_name}"

        # Hard reset to branch
        result = subprocess.run(
            ["git", "reset", "--hard", branch_name],
            cwd=self.working_dir,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return False, f"Failed to reset: {result.stderr.strip()}"

        # Restore stash if requested
        if restore_stash:
            # Look for stash with matching timestamp pattern
            stash_result = self._restore_matching_stash(branch_name)
            if stash_result:
                return True, f"Restored to {branch_name} and applied stash"

        return True, f"Restored to {branch_name}"

    def _restore_matching_stash(self, branch_name: str) -> bool:
        """
        Try to restore a stash that matches the branch timestamp.

        Args:
            branch_name: Branch name to extract timestamp from

        Returns:
            True if a stash was restored
        """
        # Extract timestamp from branch name
        parts = branch_name.split("-")
        if len(parts) < 2:
            return False

        timestamp = parts[-1]  # Last part should be timestamp

        # List stashes
        result = subprocess.run(
            ["git", "stash", "list"],
            cwd=self.working_dir,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return False

        # Find matching stash
        for line in result.stdout.strip().split("\n"):
            if f"elspais-" in line and timestamp in line:
                # Extract stash reference (stash@{N})
                stash_ref = line.split(":")[0]
                subprocess.run(
                    ["git", "stash", "pop", stash_ref],
                    cwd=self.working_dir,
                    capture_output=True,
                )
                return True

        return False

    def list_safety_branches(self) -> List[str]:
        """
        List all safety branches created by elspais.

        Returns:
            List of branch names
        """
        result = subprocess.run(
            ["git", "branch", "--list", f"{self.BRANCH_PREFIX}/*"],
            cwd=self.working_dir,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return []

        branches = []
        for line in result.stdout.strip().split("\n"):
            branch = line.strip().lstrip("* ")
            if branch:
                branches.append(branch)

        return branches

    def delete_safety_branch(self, branch_name: str) -> Tuple[bool, str]:
        """
        Delete a safety branch.

        Args:
            branch_name: Name of the branch to delete

        Returns:
            Tuple of (success, message)
        """
        if not branch_name.startswith(self.BRANCH_PREFIX):
            return False, "Not a safety branch"

        result = subprocess.run(
            ["git", "branch", "-D", branch_name],
            cwd=self.working_dir,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return False, f"Failed to delete: {result.stderr.strip()}"

        return True, f"Deleted branch: {branch_name}"

    def cleanup_old_branches(self, older_than_days: int = 7) -> List[str]:
        """
        Delete safety branches older than specified days.

        Args:
            older_than_days: Delete branches older than this many days

        Returns:
            List of deleted branch names
        """
        branches = self.list_safety_branches()
        deleted = []
        now = datetime.now()

        for branch in branches:
            # Extract timestamp from branch name
            parts = branch.split("-")
            if len(parts) < 2:
                continue

            try:
                timestamp_str = parts[-1]
                # Parse timestamp (YYYYMMDD-HHMMSS format)
                if len(timestamp_str) == 6:  # Just HHMMSS
                    date_str = parts[-2]
                    timestamp_str = f"{date_str}{timestamp_str}"

                branch_date = datetime.strptime(timestamp_str, "%Y%m%d%H%M%S")
                age = (now - branch_date).days

                if age > older_than_days:
                    success, _ = self.delete_safety_branch(branch)
                    if success:
                        deleted.append(branch)
            except (ValueError, IndexError):
                # Skip branches with unparseable timestamps
                continue

        return deleted
