"""
Git state management for elspais.

Provides functions to query git status and detect changes to requirement files,
enabling detection of:
- Uncommitted changes to spec files
- New (untracked) requirement files
- Files changed vs main/master branch
- Moved requirements (comparing current location to committed state)
"""

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class GitChangeInfo:
    """Information about git changes to requirement files."""

    modified_files: Set[str] = field(default_factory=set)
    """Files with uncommitted modifications (staged or unstaged)."""

    untracked_files: Set[str] = field(default_factory=set)
    """New files not yet tracked by git."""

    branch_changed_files: Set[str] = field(default_factory=set)
    """Files changed between current branch and main/master."""

    committed_req_locations: Dict[str, str] = field(default_factory=dict)
    """REQ ID -> file path mapping from committed state (HEAD)."""

    @property
    def all_changed_files(self) -> Set[str]:
        """Get all files with any kind of change."""
        return self.modified_files | self.untracked_files | self.branch_changed_files

    @property
    def uncommitted_files(self) -> Set[str]:
        """Get all files with uncommitted changes (modified or untracked)."""
        return self.modified_files | self.untracked_files


@dataclass
class MovedRequirement:
    """Information about a requirement that was moved between files."""

    req_id: str
    """The requirement ID (e.g., 'd00001')."""

    old_path: str
    """Path in the committed state."""

    new_path: str
    """Path in the current working directory."""


def get_repo_root(start_path: Optional[Path] = None) -> Optional[Path]:
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


def get_modified_files(repo_root: Path) -> Tuple[Set[str], Set[str]]:
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
        modified_files: Set[str] = set()
        untracked_files: Set[str] = set()

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


def get_changed_vs_branch(
    repo_root: Path, base_branch: str = "main"
) -> Set[str]:
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
            changed_files: Set[str] = set()
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
    exclude_files: Optional[List[str]] = None,
) -> Dict[str, str]:
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

    req_locations: Dict[str, str] = {}
    # Pattern matches REQ headers with optional associated prefix
    req_pattern = re.compile(
        r"^#{1,6}\s+REQ-(?:[A-Z]{2,4}-)?([pod]\d{5}):", re.MULTILINE
    )

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
    exclude_files: Optional[List[str]] = None,
) -> Dict[str, str]:
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

    req_locations: Dict[str, str] = {}
    req_pattern = re.compile(
        r"^#{1,6}\s+REQ-(?:[A-Z]{2,4}-)?([pod]\d{5}):", re.MULTILINE
    )

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

        except (IOError, UnicodeDecodeError):
            continue

    return req_locations


def detect_moved_requirements(
    committed_locations: Dict[str, str],
    current_locations: Dict[str, str],
) -> List[MovedRequirement]:
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
    repo_root: Optional[Path] = None,
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


def filter_spec_files(files: Set[str], spec_dir: str = "spec") -> Set[str]:
    """Filter a set of files to only include spec directory files.

    Args:
        files: Set of file paths
        spec_dir: Spec directory prefix

    Returns:
        Set of files that are in the spec directory
    """
    prefix = f"{spec_dir}/"
    return {f for f in files if f.startswith(prefix) and f.endswith(".md")}
