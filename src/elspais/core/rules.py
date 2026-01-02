"""
elspais.core.rules - Validation rule engine.

Provides configurable validation rules for requirement hierarchies,
format compliance, and traceability.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from elspais.core.models import Requirement
from elspais.core.patterns import PatternConfig, PatternValidator


class Severity(Enum):
    """Severity level for rule violations."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class RuleViolation:
    """
    Represents a rule violation found during validation.

    Attributes:
        rule_name: Name of the violated rule (e.g., "hierarchy.circular")
        requirement_id: ID of the requirement with the violation
        message: Human-readable description of the violation
        severity: Severity level
        location: File:line location string
    """

    rule_name: str
    requirement_id: str
    message: str
    severity: Severity
    location: str = ""

    def __str__(self) -> str:
        prefix = {
            Severity.ERROR: "❌ ERROR",
            Severity.WARNING: "⚠️ WARNING",
            Severity.INFO: "ℹ️ INFO",
        }.get(self.severity, "?")
        return (
            f"{prefix} [{self.rule_name}] {self.requirement_id}\n"
            f"   {self.message}\n   {self.location}"
        )


@dataclass
class HierarchyConfig:
    """Configuration for hierarchy validation rules."""

    allowed_implements: List[str] = field(default_factory=list)
    allow_circular: bool = False
    allow_orphans: bool = False
    max_depth: int = 5
    cross_repo_implements: bool = True

    # Parsed allowed relationships: source_type -> set of allowed target types
    _allowed_map: Dict[str, Set[str]] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        """Parse allowed_implements into a lookup map."""
        self._allowed_map = {}
        for rule in self.allowed_implements:
            # Parse "dev -> ops, prd"
            parts = rule.split("->")
            if len(parts) == 2:
                source = parts[0].strip().lower()
                targets = [t.strip().lower() for t in parts[1].split(",")]
                self._allowed_map[source] = set(targets)

    def can_implement(self, source_type: str, target_type: str) -> bool:
        """Check if source type can implement target type."""
        source = source_type.lower()
        target = target_type.lower()
        allowed = self._allowed_map.get(source, set())
        return target in allowed


@dataclass
class FormatConfig:
    """Configuration for format validation rules."""

    require_hash: bool = True
    require_rationale: bool = False
    require_status: bool = True
    allowed_statuses: List[str] = field(
        default_factory=lambda: ["Active", "Draft", "Deprecated", "Superseded"]
    )

    # Assertion format rules
    require_assertions: bool = True
    acceptance_criteria: str = "warn"  # "allow" | "warn" | "error"
    require_shall: bool = True
    labels_sequential: bool = True
    labels_unique: bool = True
    placeholder_values: List[str] = field(default_factory=lambda: [
        "obsolete", "removed", "deprecated", "N/A", "n/a", "-", "reserved"
    ])


@dataclass
class RulesConfig:
    """Complete configuration for all validation rules."""

    hierarchy: HierarchyConfig = field(default_factory=HierarchyConfig)
    format: FormatConfig = field(default_factory=FormatConfig)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RulesConfig":
        """Create RulesConfig from configuration dictionary."""
        hierarchy_data = data.get("hierarchy", {})
        format_data = data.get("format", {})

        hierarchy = HierarchyConfig(
            allowed_implements=hierarchy_data.get(
                "allowed_implements", ["dev -> ops, prd", "ops -> prd", "prd -> prd"]
            ),
            allow_circular=hierarchy_data.get("allow_circular", False),
            allow_orphans=hierarchy_data.get("allow_orphans", False),
            max_depth=hierarchy_data.get("max_depth", 5),
            cross_repo_implements=hierarchy_data.get("cross_repo_implements", True),
        )

        format_config = FormatConfig(
            require_hash=format_data.get("require_hash", True),
            require_rationale=format_data.get("require_rationale", False),
            require_status=format_data.get("require_status", True),
            allowed_statuses=format_data.get(
                "allowed_statuses", ["Active", "Draft", "Deprecated", "Superseded"]
            ),
            # Assertion rules
            require_assertions=format_data.get("require_assertions", True),
            acceptance_criteria=format_data.get("acceptance_criteria", "warn"),
            require_shall=format_data.get("require_shall", True),
            labels_sequential=format_data.get("labels_sequential", True),
            labels_unique=format_data.get("labels_unique", True),
            placeholder_values=format_data.get("placeholder_values", [
                "obsolete", "removed", "deprecated", "N/A", "n/a", "-", "reserved"
            ]),
        )

        return cls(hierarchy=hierarchy, format=format_config)


class RuleEngine:
    """
    Validates requirements against configured rules.
    """

    def __init__(
        self,
        config: RulesConfig,
        pattern_config: Optional[PatternConfig] = None,
    ):
        """
        Initialize rule engine.

        Args:
            config: Rules configuration
            pattern_config: Optional pattern configuration for assertion label validation
        """
        self.config = config
        self.pattern_config = pattern_config
        self.pattern_validator = (
            PatternValidator(pattern_config) if pattern_config else None
        )

    def validate(self, requirements: Dict[str, Requirement]) -> List[RuleViolation]:
        """
        Validate all requirements against configured rules.

        Args:
            requirements: Dictionary of requirement ID -> Requirement

        Returns:
            List of RuleViolation objects
        """
        violations = []

        # Run all validation rules
        violations.extend(self._check_hierarchy(requirements))
        violations.extend(self._check_format(requirements))
        violations.extend(self._check_circular(requirements))
        violations.extend(self._check_orphans(requirements))

        return violations

    def _check_hierarchy(self, requirements: Dict[str, Requirement]) -> List[RuleViolation]:
        """Check hierarchy rules (allowed implements)."""
        violations = []

        for req_id, req in requirements.items():
            source_type = self._get_type_from_level(req.level)

            for impl_id in req.implements:
                # Find the target requirement
                target_req = self._find_requirement(impl_id, requirements)
                if target_req is None:
                    # Target not found - this is a broken link, not hierarchy violation
                    continue

                target_type = self._get_type_from_level(target_req.level)

                # Check if this relationship is allowed
                if not self.config.hierarchy.can_implement(source_type, target_type):
                    msg = (
                        f"{source_type.upper()} cannot implement "
                        f"{target_type.upper()} ({impl_id})"
                    )
                    violations.append(
                        RuleViolation(
                            rule_name="hierarchy.implements",
                            requirement_id=req_id,
                            message=msg,
                            severity=Severity.ERROR,
                            location=req.location(),
                        )
                    )

        return violations

    def _check_circular(self, requirements: Dict[str, Requirement]) -> List[RuleViolation]:
        """Check for circular dependencies."""
        if self.config.hierarchy.allow_circular:
            return []

        violations: List[RuleViolation] = []
        visited: Set[str] = set()
        path: List[str] = []

        def dfs(req_id: str) -> Optional[List[str]]:
            """Depth-first search for cycles."""
            if req_id in path:
                # Found a cycle
                cycle_start = path.index(req_id)
                return path[cycle_start:] + [req_id]

            if req_id in visited:
                return None

            visited.add(req_id)
            path.append(req_id)

            req = requirements.get(req_id)
            if req:
                for impl_id in req.implements:
                    # Resolve to full ID if needed
                    full_id = self._resolve_id(impl_id, requirements)
                    if full_id and full_id in requirements:
                        cycle = dfs(full_id)
                        if cycle:
                            return cycle

            path.pop()
            return None

        # Check each requirement for cycles
        for req_id in requirements:
            visited.clear()
            path.clear()
            cycle = dfs(req_id)
            if cycle:
                cycle_str = " -> ".join(cycle)
                violations.append(
                    RuleViolation(
                        rule_name="hierarchy.circular",
                        requirement_id=req_id,
                        message=f"Circular dependency detected: {cycle_str}",
                        severity=Severity.ERROR,
                        location=requirements[req_id].location(),
                    )
                )
                break  # Report only first cycle found

        return violations

    def _check_orphans(self, requirements: Dict[str, Requirement]) -> List[RuleViolation]:
        """Check for orphaned requirements (DEV/OPS without implements)."""
        if self.config.hierarchy.allow_orphans:
            return []

        violations = []

        for req_id, req in requirements.items():
            # Skip root level (PRD)
            if req.level.upper() in ["PRD", "PRODUCT"]:
                continue

            # DEV/OPS should implement something
            if not req.implements:
                violations.append(
                    RuleViolation(
                        rule_name="hierarchy.orphan",
                        requirement_id=req_id,
                        message=f"{req.level} requirement has no Implements reference",
                        severity=Severity.WARNING,
                        location=req.location(),
                    )
                )

        return violations

    def _check_format(self, requirements: Dict[str, Requirement]) -> List[RuleViolation]:
        """Check format rules (hash, rationale, assertions, acceptance criteria)."""
        violations = []

        for req_id, req in requirements.items():
            # Check hash
            if self.config.format.require_hash and not req.hash:
                violations.append(
                    RuleViolation(
                        rule_name="format.require_hash",
                        requirement_id=req_id,
                        message="Missing hash footer",
                        severity=Severity.ERROR,
                        location=req.location(),
                    )
                )

            # Check rationale
            if self.config.format.require_rationale and not req.rationale:
                violations.append(
                    RuleViolation(
                        rule_name="format.require_rationale",
                        requirement_id=req_id,
                        message="Missing Rationale section",
                        severity=Severity.WARNING,
                        location=req.location(),
                    )
                )

            # Check assertions (new format)
            violations.extend(self._check_assertions(req_id, req))

            # Check acceptance criteria (legacy format)
            acceptance_mode = self.config.format.acceptance_criteria
            if req.acceptance_criteria:
                if acceptance_mode == "error":
                    violations.append(
                        RuleViolation(
                            rule_name="format.acceptance_criteria",
                            requirement_id=req_id,
                            message="Acceptance Criteria not allowed; use Assertions",
                            severity=Severity.ERROR,
                            location=req.location(),
                        )
                    )
                elif acceptance_mode == "warn":
                    violations.append(
                        RuleViolation(
                            rule_name="format.acceptance_criteria",
                            requirement_id=req_id,
                            message="Acceptance Criteria deprecated; use Assertions",
                            severity=Severity.WARNING,
                            location=req.location(),
                        )
                    )
                # "allow" mode: no violation

            # Check status
            if self.config.format.require_status:
                if req.status not in self.config.format.allowed_statuses:
                    allowed = self.config.format.allowed_statuses
                    violations.append(
                        RuleViolation(
                            rule_name="format.status_valid",
                            requirement_id=req_id,
                            message=f"Invalid status '{req.status}'. Allowed: {allowed}",
                            severity=Severity.ERROR,
                            location=req.location(),
                        )
                    )

        return violations

    def _check_assertions(
        self, req_id: str, req: Requirement
    ) -> List[RuleViolation]:
        """Check assertion-specific validation rules."""
        violations = []

        # Check if assertions are required
        if self.config.format.require_assertions and not req.assertions:
            violations.append(
                RuleViolation(
                    rule_name="format.require_assertions",
                    requirement_id=req_id,
                    message="Missing Assertions section",
                    severity=Severity.ERROR,
                    location=req.location(),
                )
            )
            return violations  # No point checking other assertion rules

        if not req.assertions:
            return violations

        # Extract labels and check for duplicates
        labels = [a.label for a in req.assertions]

        # Check labels are unique
        if self.config.format.labels_unique:
            seen = set()
            for label in labels:
                if label in seen:
                    violations.append(
                        RuleViolation(
                            rule_name="format.labels_unique",
                            requirement_id=req_id,
                            message=f"Duplicate assertion label: {label}",
                            severity=Severity.ERROR,
                            location=req.location(),
                        )
                    )
                seen.add(label)

        # Check labels are sequential
        if self.config.format.labels_sequential and self.pattern_validator:
            expected_labels = []
            for i in range(len(labels)):
                expected_labels.append(
                    self.pattern_validator.format_assertion_label(i)
                )
            if labels != expected_labels:
                msg = f"Labels not sequential: {labels} (expected {expected_labels})"
                violations.append(
                    RuleViolation(
                        rule_name="format.labels_sequential",
                        requirement_id=req_id,
                        message=msg,
                        severity=Severity.ERROR,
                        location=req.location(),
                    )
                )

        # Check SHALL/SHALL NOT language (skip placeholders)
        if self.config.format.require_shall:
            for assertion in req.assertions:
                if assertion.is_placeholder:
                    continue
                if "SHALL" not in assertion.text.upper():
                    text_preview = assertion.text[:40]
                    msg = f"Assertion {assertion.label} missing SHALL: {text_preview}..."
                    violations.append(
                        RuleViolation(
                            rule_name="format.require_shall",
                            requirement_id=req_id,
                            message=msg,
                            severity=Severity.WARNING,
                            location=req.location(),
                        )
                    )

        # Validate assertion labels against configured pattern
        if self.pattern_validator:
            for assertion in req.assertions:
                if not self.pattern_validator.is_valid_assertion_label(assertion.label):
                    violations.append(
                        RuleViolation(
                            rule_name="format.assertion_label",
                            requirement_id=req_id,
                            message=f"Invalid assertion label format: {assertion.label}",
                            severity=Severity.ERROR,
                            location=req.location(),
                        )
                    )

        return violations

    def _get_type_from_level(self, level: str) -> str:
        """Map level name to type code."""
        level_map = {
            "PRD": "prd",
            "PRODUCT": "prd",
            "OPS": "ops",
            "OPERATIONS": "ops",
            "DEV": "dev",
            "DEVELOPMENT": "dev",
        }
        return level_map.get(level.upper(), level.lower())

    def _find_requirement(
        self, impl_id: str, requirements: Dict[str, Requirement]
    ) -> Optional[Requirement]:
        """Find a requirement by ID (handles partial IDs)."""
        # Try exact match first
        if impl_id in requirements:
            return requirements[impl_id]

        # Try to find by suffix (e.g., "p00001" matches "REQ-p00001")
        for req_id, req in requirements.items():
            if req_id.endswith(impl_id) or req_id.endswith(f"-{impl_id}"):
                return req

        return None

    def _resolve_id(self, impl_id: str, requirements: Dict[str, Requirement]) -> Optional[str]:
        """Resolve a partial ID to a full ID."""
        if impl_id in requirements:
            return impl_id

        for req_id in requirements:
            if req_id.endswith(impl_id) or req_id.endswith(f"-{impl_id}"):
                return req_id

        return None
