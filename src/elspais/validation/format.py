"""Format validation - Validate requirement format against configurable rules.

Validates requirements against rules defined in [rules.format] config section:
- require_hash: Check hash exists in footer
- require_assertions: Check at least one assertion exists
- require_rationale: Check rationale section exists
- require_shall: Check "shall" keyword in assertion text
- require_status: Check status field in metadata
- allowed_statuses: List of valid status values
- labels_sequential: Check assertion labels are sequential (A,B,C not A,C,E)
- labels_unique: Check no duplicate assertion labels
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from elspais.graph import GraphNode


@dataclass
class FormatRulesConfig:
    """Configuration for format validation rules.

    All rules default to False (disabled) for backwards compatibility.
    Enable rules explicitly in [rules.format] config section.
    """

    require_hash: bool = False
    require_assertions: bool = False
    require_rationale: bool = False
    require_shall: bool = False
    require_status: bool = False
    allowed_statuses: list[str] = field(default_factory=list)
    labels_sequential: bool = False
    labels_unique: bool = True  # Default True - duplicates are usually errors

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FormatRulesConfig":
        """Create FormatRulesConfig from configuration dictionary.

        Args:
            data: Dictionary from [rules.format] config section

        Returns:
            FormatRulesConfig instance
        """
        return cls(
            require_hash=data.get("require_hash", False),
            require_assertions=data.get("require_assertions", False),
            require_rationale=data.get("require_rationale", False),
            require_shall=data.get("require_shall", False),
            require_status=data.get("require_status", False),
            allowed_statuses=data.get("allowed_statuses", []),
            labels_sequential=data.get("labels_sequential", False),
            labels_unique=data.get("labels_unique", True),
        )


@dataclass
class FormatViolation:
    """A format rule violation found during validation.

    Attributes:
        rule: The rule that was violated
        message: Human-readable description of the violation
        severity: "error" or "warning"
        node_id: ID of the requirement node with the violation
        details: Additional context about the violation
    """

    rule: str
    message: str
    severity: str = "error"
    node_id: str = ""
    details: dict[str, Any] = field(default_factory=dict)


def validate_requirement_format(
    node: "GraphNode",
    rules: FormatRulesConfig,
) -> list[FormatViolation]:
    """Validate a requirement node against format rules.

    Args:
        node: The requirement GraphNode to validate
        rules: Format rules configuration

    Returns:
        List of FormatViolation objects (empty if valid)
    """
    from elspais.graph import NodeKind

    violations: list[FormatViolation] = []

    # Only validate requirement nodes
    if node.kind != NodeKind.REQUIREMENT:
        return violations

    node_id = node.id

    # Rule: require_hash
    if rules.require_hash:
        hash_value = node.hash  # Use convenience property
        if not hash_value or hash_value == "00000000":
            violations.append(
                FormatViolation(
                    rule="require_hash",
                    message=f"{node_id}: Missing or placeholder hash value",
                    node_id=node_id,
                    details={"current_hash": hash_value},
                )
            )

    # Rule: require_assertions
    if rules.require_assertions:
        # Count assertion children
        assertion_count = sum(
            1
            for child in node.iter_children()
            if child.kind == NodeKind.ASSERTION
        )
        if assertion_count == 0:
            violations.append(
                FormatViolation(
                    rule="require_assertions",
                    message=f"{node_id}: No assertions defined",
                    node_id=node_id,
                )
            )

    # Rule: require_rationale
    if rules.require_rationale:
        rationale = node.get_field("rationale", "")
        if not rationale or not rationale.strip():
            violations.append(
                FormatViolation(
                    rule="require_rationale",
                    message=f"{node_id}: Missing rationale section",
                    node_id=node_id,
                )
            )

    # Rule: require_shall
    if rules.require_shall:
        # Check assertions for SHALL keyword
        assertions_without_shall = []
        for child in node.iter_children():
            if child.kind == NodeKind.ASSERTION:
                assertion_text = child.get_field("text", "") or child.get_label()
                if "shall" not in assertion_text.lower():
                    assertions_without_shall.append(child.get_label())

        if assertions_without_shall:
            violations.append(
                FormatViolation(
                    rule="require_shall",
                    message=f"{node_id}: Assertions missing 'SHALL' keyword: {', '.join(assertions_without_shall)}",
                    node_id=node_id,
                    details={"assertions": assertions_without_shall},
                )
            )

    # Rule: require_status
    if rules.require_status:
        status = node.status  # Use convenience property
        if not status:
            violations.append(
                FormatViolation(
                    rule="require_status",
                    message=f"{node_id}: Missing status field",
                    node_id=node_id,
                )
            )

    # Rule: allowed_statuses
    if rules.allowed_statuses:
        status = node.status  # Use convenience property
        if status and status not in rules.allowed_statuses:
            violations.append(
                FormatViolation(
                    rule="allowed_statuses",
                    message=f"{node_id}: Invalid status '{status}' (allowed: {', '.join(rules.allowed_statuses)})",
                    node_id=node_id,
                    details={"current": status, "allowed": rules.allowed_statuses},
                )
            )

    # Collect assertion labels for sequential and unique checks
    assertion_labels: list[str] = []
    for child in node.iter_children():
        if child.kind == NodeKind.ASSERTION:
            # Extract label from assertion ID (e.g., "REQ-p00001-A" -> "A")
            label = child.get_field("label")
            if not label and "-" in child.id:
                label = child.id.split("-")[-1]
            if label:
                assertion_labels.append(label)

    # Rule: labels_unique
    if rules.labels_unique and assertion_labels:
        seen = set()
        duplicates = []
        for label in assertion_labels:
            if label in seen:
                duplicates.append(label)
            seen.add(label)

        if duplicates:
            violations.append(
                FormatViolation(
                    rule="labels_unique",
                    message=f"{node_id}: Duplicate assertion labels: {', '.join(set(duplicates))}",
                    node_id=node_id,
                    details={"duplicates": list(set(duplicates))},
                )
            )

    # Rule: labels_sequential
    if rules.labels_sequential and assertion_labels:
        # Check if uppercase letter labels are sequential
        uppercase_labels = [l for l in assertion_labels if len(l) == 1 and l.isupper()]
        if uppercase_labels:
            sorted_labels = sorted(set(uppercase_labels))
            expected_next = "A"
            gaps = []

            for label in sorted_labels:
                if label != expected_next:
                    gaps.append(f"expected {expected_next}, found {label}")
                    break
                expected_next = chr(ord(expected_next) + 1)

            if gaps:
                violations.append(
                    FormatViolation(
                        rule="labels_sequential",
                        message=f"{node_id}: Non-sequential assertion labels ({gaps[0]})",
                        node_id=node_id,
                        severity="warning",  # Less severe - sometimes intentional
                        details={"labels": uppercase_labels, "gaps": gaps},
                    )
                )

    return violations


def get_format_rules_config(config: dict[str, Any]) -> FormatRulesConfig:
    """Get FormatRulesConfig from configuration dictionary.

    Args:
        config: Full configuration dictionary from get_config()

    Returns:
        FormatRulesConfig instance from [rules.format] section
    """
    rules_data = config.get("rules", {}).get("format", {})
    return FormatRulesConfig.from_dict(rules_data)
