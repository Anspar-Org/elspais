# Implements: REQ-int-d00004 (Model Adapter)
"""
elspais.trace_view.models - Data models for trace-view.

Provides TraceViewRequirement which wraps core Requirement with:
- Git state tracking (uncommitted, modified, moved)
- Test coverage information
- Implementation file references
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from elspais.core.models import Requirement as CoreRequirement


@dataclass
class TestInfo:
    """Represents test coverage for a requirement.

    Attributes:
        test_count: Number of automated tests
        manual_test_count: Number of manual tests
        test_status: Status ('not_tested', 'passed', 'failed', 'error', 'skipped')
        test_details: List of test result details
        notes: Additional notes about testing
    """

    test_count: int = 0
    manual_test_count: int = 0
    test_status: str = "not_tested"
    test_details: List[Dict] = field(default_factory=list)
    notes: str = ""


@dataclass
class GitChangeInfo:
    """Container for git change state.

    Injected into TraceViewRequirement rather than using a global singleton.
    This allows for better testing and explicit dependency management.

    Attributes:
        uncommitted_files: Set of spec-relative paths with uncommitted changes
        untracked_files: Set of spec-relative paths that are untracked (new)
        branch_changed_files: Set of spec-relative paths changed vs main branch
        committed_req_locations: Map of requirement ID to committed file path
    """

    uncommitted_files: Set[str] = field(default_factory=set)
    untracked_files: Set[str] = field(default_factory=set)
    branch_changed_files: Set[str] = field(default_factory=set)
    committed_req_locations: Dict[str, str] = field(default_factory=dict)


@dataclass
class TraceViewRequirement:
    """Requirement enriched with trace-view data.

    Wraps a core Requirement and adds:
    - Git state properties (is_uncommitted, is_branch_changed, is_moved)
    - Test coverage information
    - Implementation file references

    Implements: REQ-int-d00004-A (wraps elspais.core.models.Requirement)
    Implements: REQ-int-d00004-B (git state injected, not global)
    Implements: REQ-int-d00004-C (implementation files stored per-requirement)
    """

    core: CoreRequirement
    test_info: Optional[TestInfo] = None
    implementation_files: List[Tuple[str, int]] = field(default_factory=list)
    git_info: Optional[GitChangeInfo] = None
    external_spec_path: Optional[str] = None

    # --- Delegated core properties ---

    @property
    def id(self) -> str:
        """Requirement ID without REQ- prefix for display."""
        return self.core.id.replace("REQ-", "")

    @property
    def full_id(self) -> str:
        """Full requirement ID including REQ- prefix."""
        return self.core.id

    @property
    def title(self) -> str:
        return self.core.title

    @property
    def level(self) -> str:
        """Level normalized to uppercase (PRD, OPS, DEV)."""
        return self.core.level.upper()

    @property
    def status(self) -> str:
        return self.core.status

    @property
    def implements(self) -> List[str]:
        return self.core.implements

    @property
    def file_path(self) -> Path:
        return self.core.file_path or Path("unknown")

    @property
    def line_number(self) -> int:
        return self.core.line_number or 0

    @property
    def hash(self) -> str:
        return self.core.hash or ""

    @property
    def body(self) -> str:
        return self.core.body

    @property
    def rationale(self) -> str:
        return self.core.rationale or ""

    @property
    def is_roadmap(self) -> bool:
        return self.core.is_roadmap

    @property
    def is_conflict(self) -> bool:
        return self.core.is_conflict

    @property
    def conflict_with(self) -> str:
        return self.core.conflict_with

    @property
    def subdir(self) -> str:
        return self.core.subdir

    # --- Computed properties ---

    @property
    def repo_prefix(self) -> Optional[str]:
        """Extract repo prefix from ID (e.g., 'CAL-d00005' → 'CAL').

        Associated repo requirements have format PREFIX-{level}{number}.
        Core repo requirements have format {level}{number} (returns None).
        """
        import re

        # Match: optional prefix (uppercase letters), then level (p/o/d) and 5 digits
        match = re.match(r"^([A-Z]+-)?([pod]\d{5})$", self.id, re.IGNORECASE)
        if match and match.group(1):
            return match.group(1).rstrip("-")
        return None

    @property
    def display_filename(self) -> str:
        """Get displayable filename with repo prefix for external repos.

        Returns 'CAL/filename.md' for external repos, 'filename.md' for core.
        """
        prefix = self.repo_prefix
        if prefix:
            return f"{prefix}/{self.file_path.name}"
        return self.file_path.name

    # --- Git state properties ---

    def _get_spec_relative_path(self) -> str:
        """Get the spec-relative path for this requirement's file."""
        if self.is_roadmap:
            return f"spec/roadmap/{self.file_path.name}"
        if self.subdir:
            return f"spec/{self.subdir}/{self.file_path.name}"
        return f"spec/{self.file_path.name}"

    def _is_in_untracked_file(self) -> bool:
        """Check if requirement is in an untracked (new) file."""
        if not self.git_info:
            return False
        rel_path = self._get_spec_relative_path()
        return rel_path in self.git_info.untracked_files

    def _check_modified_in_fileset(self, file_set: Set[str]) -> bool:
        """Check if requirement is modified based on a set of changed files."""
        if not self.git_info:
            return False

        rel_path = self._get_spec_relative_path()

        # Check if file is untracked (new) - all REQs in new files are considered modified
        if rel_path in self.git_info.untracked_files:
            return True

        # Check if file is in the modified set
        return rel_path in file_set

    @property
    def is_uncommitted(self) -> bool:
        """Check if requirement has uncommitted changes."""
        if not self.git_info:
            return False
        return self._check_modified_in_fileset(self.git_info.uncommitted_files)

    @property
    def is_branch_changed(self) -> bool:
        """Check if requirement changed vs main branch."""
        if not self.git_info:
            return False
        return self._check_modified_in_fileset(self.git_info.branch_changed_files)

    @property
    def is_new(self) -> bool:
        """Check if requirement is in a new (untracked) file."""
        return self._is_in_untracked_file()

    @property
    def is_modified(self) -> bool:
        """Check if requirement has modified content but is not in a new file."""
        if self._is_in_untracked_file():
            return False  # New files are "new", not "modified"
        return self.is_uncommitted

    @property
    def is_moved(self) -> bool:
        """Check if requirement was moved from a different file.

        A requirement is considered moved if:
        - It exists in the committed state in a different file, OR
        - It's in a new file but has a non-TBD hash (suggesting it was copied/moved)
        """
        if not self.git_info:
            return False

        current_path = self._get_spec_relative_path()
        committed_path = self.git_info.committed_req_locations.get(self.id)

        if committed_path is not None:
            # REQ existed in committed state - check if path changed
            return committed_path != current_path

        # REQ doesn't exist in committed state
        # If it's in a new file but has a real hash, it was likely moved/copied
        if self._is_in_untracked_file() and self.hash and self.hash != "TBD":
            return True

        return False

    # --- Factory methods ---

    @classmethod
    def from_core(
        cls,
        core_req: CoreRequirement,
        git_info: Optional[GitChangeInfo] = None,
    ) -> "TraceViewRequirement":
        """Create TraceViewRequirement from core Requirement.

        Args:
            core_req: The core Requirement to wrap
            git_info: Optional git change state (inject for testability)

        Returns:
            TraceViewRequirement instance
        """
        # Detect external repo paths (absolute paths)
        external_spec_path = None
        if core_req.file_path and core_req.file_path.is_absolute():
            external_spec_path = str(core_req.file_path)

        return cls(
            core=core_req,
            git_info=git_info,
            external_spec_path=external_spec_path,
        )

    @classmethod
    def from_dict(
        cls,
        req_id: str,
        data: Dict,
        git_info: Optional[GitChangeInfo] = None,
    ) -> "TraceViewRequirement":
        """Create TraceViewRequirement from elspais validate --json output.

        This provides backward compatibility with code that expects to create
        requirements from JSON data.

        Args:
            req_id: Full requirement ID (e.g., 'REQ-d00027')
            data: Dict from elspais JSON output
            git_info: Optional git change state

        Returns:
            TraceViewRequirement instance
        """
        # Map level to uppercase for consistency
        level_map = {
            "PRD": "PRD",
            "Ops": "OPS",
            "Dev": "DEV",
            "prd": "PRD",
            "ops": "OPS",
            "dev": "DEV",
        }
        level = data.get("level", "")
        subdir = data.get("subdir", "")

        # Create core requirement
        file_path_str = data.get("filePath", data.get("file", ""))
        file_path = Path(file_path_str) if file_path_str else None

        core_req = CoreRequirement(
            id=req_id,
            title=data.get("title", ""),
            level=level_map.get(level, level.upper()),
            status=data.get("status", "Active"),
            body=data.get("body", ""),
            implements=data.get("implements", []),
            rationale=data.get("rationale"),
            hash=data.get("hash"),
            file_path=file_path,
            line_number=data.get("line", 0),
            subdir=subdir,
            is_conflict=data.get("isConflict", False),
            conflict_with=data.get("conflictWith", "") or "",
        )

        # Create trace-view requirement
        tv_req = cls.from_core(core_req, git_info=git_info)

        # Add test info if provided
        test_count = data.get("test_count", 0)
        if test_count > 0:
            test_passed = data.get("test_passed", 0)
            test_status = "passed" if test_passed == test_count else "failed"
            tv_req.test_info = TestInfo(
                test_count=test_count,
                manual_test_count=0,
                test_status=test_status,
                test_details=data.get("test_result_files", []),
                notes="",
            )

        return tv_req


# Backward compatibility aliases
Requirement = TraceViewRequirement
TraceabilityRequirement = TraceViewRequirement
