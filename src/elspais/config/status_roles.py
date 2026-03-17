"""Status role classification for requirements.

Each status is assigned a role that determines how it behaves across
the tool: coverage metrics, analysis scoring, viewer filtering.

Roles:
- ACTIVE: Committed, normative. Counted in all metrics, shown by default.
- PROVISIONAL: In-progress toward active. Excluded from coverage, included in analysis.
- ASPIRATIONAL: Future/planning, may never happen. Excluded from coverage and analysis.
- RETIRED: Concluded, no longer relevant. Excluded from everything, hidden by default.
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class StatusRole(Enum):
    ACTIVE = "active"
    PROVISIONAL = "provisional"
    ASPIRATIONAL = "aspirational"
    RETIRED = "retired"


# Default classification matching historical hardcoded behavior
_DEFAULT_ROLES: dict[str, list[str]] = {
    "active": ["Active"],
    "provisional": ["Draft", "Proposed"],
    "aspirational": ["Roadmap", "Future", "Idea"],
    "retired": ["Deprecated", "Superseded", "Rejected"],
}


class StatusRolesConfig:
    """Maps status names to roles.

    Usage:
        cfg = StatusRolesConfig.default()
        cfg.role_of("Draft")  # StatusRole.PROVISIONAL
        cfg.is_excluded_from_coverage("Active")  # False
    """

    def __init__(self, mapping: dict[str, StatusRole]) -> None:
        # Store lowercase -> role for case-insensitive lookup
        self._mapping: dict[str, StatusRole] = {k.lower(): v for k, v in mapping.items()}
        # Store original case for set-building methods
        self._original_case: dict[str, str] = {k.lower(): k for k in mapping}

    @classmethod
    def default(cls) -> StatusRolesConfig:
        return cls.from_dict(_DEFAULT_ROLES)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StatusRolesConfig:
        """Parse from config dict like {"active": ["Active"], ...}."""
        mapping: dict[str, StatusRole] = {}
        for role_name, statuses in data.items():
            try:
                role = StatusRole(role_name)
            except ValueError:
                continue
            if isinstance(statuses, list):
                for s in statuses:
                    mapping[s] = role
        return cls(mapping)

    def role_of(self, status: str | None) -> StatusRole:
        """Get the role for a status. Unknown statuses default to ACTIVE."""
        if not status:
            return StatusRole.ACTIVE
        return self._mapping.get(status.lower(), StatusRole.ACTIVE)

    def is_excluded_from_coverage(self, status: str | None) -> bool:
        """PROVISIONAL, ASPIRATIONAL, and RETIRED are excluded from coverage."""
        role = self.role_of(status)
        return role in (StatusRole.PROVISIONAL, StatusRole.ASPIRATIONAL, StatusRole.RETIRED)

    def is_excluded_from_analysis(self, status: str | None) -> bool:
        """ASPIRATIONAL and RETIRED are excluded from analysis/scoring."""
        role = self.role_of(status)
        return role in (StatusRole.ASPIRATIONAL, StatusRole.RETIRED)

    def coverage_excluded_statuses(self) -> set[str]:
        """Return the set of original-case status names excluded from coverage."""
        result: set[str] = set()
        for name_lower, role in self._mapping.items():
            if role in (StatusRole.PROVISIONAL, StatusRole.ASPIRATIONAL, StatusRole.RETIRED):
                result.add(self._original_case.get(name_lower, name_lower.title()))
        return result

    def analysis_excluded_statuses(self) -> set[str]:
        """Return the set of original-case status names excluded from analysis."""
        result: set[str] = set()
        for name_lower, role in self._mapping.items():
            if role in (StatusRole.ASPIRATIONAL, StatusRole.RETIRED):
                result.add(self._original_case.get(name_lower, name_lower.title()))
        return result

    def default_hidden_statuses(self) -> set[str]:
        """Return status names hidden by default in viewer (retired only)."""
        result: set[str] = set()
        for name_lower, role in self._mapping.items():
            if role == StatusRole.RETIRED:
                result.add(self._original_case.get(name_lower, name_lower.title()))
        return result
