# Implements: REQ-int-d00003 (MCP Server)
"""
elspais.mcp.serializers - JSON serialization for MCP responses.

Provides functions to serialize GraphNode objects to JSON-compatible dicts.

Uses GraphNode from the traceability graph module.
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from elspais.content_rules import ContentRule
from elspais.graph import GraphNode, NodeKind
from elspais.graph.builder import TraceGraph

if TYPE_CHECKING:
    from elspais.graph.mutations import BrokenReference, MutationEntry
    from elspais.mcp.context import WorkspaceContext


class Severity(Enum):
    """Validation rule severity levels."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class RuleViolation:
    """A validation rule violation."""

    rule_name: str
    requirement_id: str
    message: str
    severity: Severity
    location: Optional[str] = None


def serialize_requirement(node: GraphNode) -> Dict[str, Any]:
    """
    Serialize a requirement GraphNode to a JSON-compatible dict.

    Args:
        node: GraphNode of kind REQUIREMENT

    Returns:
        Dict suitable for JSON serialization
    """
    # Get implements/refines from parent relationships
    implements = []
    for parent in node.iter_parents():
        if parent.kind == NodeKind.REQUIREMENT:
            implements.append(parent.id)

    # Get assertions from children
    assertions = []
    for child in node.iter_children():
        if child.kind == NodeKind.ASSERTION:
            assertions.append(serialize_assertion(child))

    return {
        "id": node.id,
        "title": node.get_label(),
        "level": node.level,
        "status": node.status,
        "body": node.get_field("body", ""),
        "implements": implements,
        "refines": [],
        "assertions": assertions,
        "rationale": node.get_field("rationale", ""),
        "hash": node.hash,
        "file_path": node.source.path if node.source else None,
        "line_number": node.source.line if node.source else None,
        "subdir": node.get_field("subdir", ""),
        "type_code": node.get_field("type_code", ""),
    }


def serialize_requirement_summary(node: GraphNode) -> Dict[str, Any]:
    """
    Serialize requirement summary (lighter weight, for listings).

    Args:
        node: GraphNode of kind REQUIREMENT

    Returns:
        Dict with summary fields only
    """
    implements = []
    for parent in node.iter_parents():
        if parent.kind == NodeKind.REQUIREMENT:
            implements.append(parent.id)

    assertion_count = sum(1 for c in node.iter_children() if c.kind == NodeKind.ASSERTION)

    return {
        "id": node.id,
        "title": node.get_label(),
        "level": node.level,
        "status": node.status,
        "implements": implements,
        "refines": [],
        "assertion_count": assertion_count,
    }


def serialize_assertion(node: GraphNode) -> Dict[str, Any]:
    """
    Serialize an assertion GraphNode to a JSON-compatible dict.

    Args:
        node: GraphNode of kind ASSERTION

    Returns:
        Dict suitable for JSON serialization
    """
    return {
        "label": node.get_label(),
        "text": node.get_field("text", ""),
        "is_placeholder": node.get_field("is_placeholder", False),
    }


def serialize_violation(violation: RuleViolation) -> Dict[str, Any]:
    """
    Serialize a RuleViolation to a JSON-compatible dict.

    Args:
        violation: RuleViolation to serialize

    Returns:
        Dict suitable for JSON serialization
    """
    return {
        "rule_name": violation.rule_name,
        "requirement_id": violation.requirement_id,
        "message": violation.message,
        "severity": violation.severity.value,
        "location": violation.location,
    }


def serialize_content_rule(rule: ContentRule) -> Dict[str, Any]:
    """
    Serialize a ContentRule to a JSON-compatible dict.

    Args:
        rule: ContentRule to serialize

    Returns:
        Dict suitable for JSON serialization
    """
    return {
        "file_path": str(rule.file_path),
        "title": rule.title,
        "content": rule.content,
        "type": rule.type,
        "applies_to": rule.applies_to,
    }


def serialize_node_full(
    node: GraphNode,
    context: "WorkspaceContext",
    include_full_text: bool = True,
) -> Dict[str, Any]:
    """
    Serialize a requirement node with full context for AI transformation.

    This provides a comprehensive JSON representation including:
    - Full requirement text from file
    - All assertions with coverage info from graph
    - Metrics from graph node
    - Relationships (implements, implemented_by, refines, refined_by)
    - Source location with line range

    Args:
        node: GraphNode of kind REQUIREMENT
        context: WorkspaceContext for graph access
        include_full_text: If True, include full_text from file

    Returns:
        Dict suitable for JSON serialization and AI processing
    """
    result: Dict[str, Any] = {
        "id": node.id,
        "title": node.get_label(),
        "level": node.level,
        "status": node.status,
        "type_code": node.get_field("type_code", ""),
    }

    # Source location
    if node.source:
        result["file_path"] = node.source.path
        result["line_number"] = node.source.line
        result["source"] = {
            "path": node.source.path,
            "line": node.source.line,
            "end_line": node.source.end_line,
        }

        # Get full text from file if requested
        if include_full_text and node.source.path:
            full_text = _get_node_full_text(node, context)
            if full_text:
                result["full_text"] = full_text
                line_count = full_text.count("\n") + 1
                result["line_range"] = [node.source.line, node.source.line + line_count - 1]

    # Assertions with coverage info
    assertions_info = _serialize_assertions_with_coverage(node)
    result["assertions"] = assertions_info

    # Relationships - implements (parents)
    implements = []
    for parent in node.iter_parents():
        if parent.kind == NodeKind.REQUIREMENT:
            implements.append(parent.id)
    result["implements"] = implements
    result["refines"] = []

    # Implemented_by (children)
    implemented_by = []
    for child in node.iter_children():
        if child.kind == NodeKind.REQUIREMENT:
            implemented_by.append(child.id)
    result["implemented_by"] = implemented_by
    result["refined_by"] = []

    # Metrics from graph node
    result["metrics"] = {
        "total_assertions": sum(1 for c in node.iter_children() if c.kind == NodeKind.ASSERTION),
        "covered_assertions": node.get_metric("covered_assertions", 0),
        "coverage_pct": node.get_metric("coverage_pct", 0.0),
        "direct_covered": node.get_metric("direct_covered", 0),
        "explicit_covered": node.get_metric("explicit_covered", 0),
        "inferred_covered": node.get_metric("inferred_covered", 0),
        "total_tests": node.get_metric("total_tests", 0),
        "passed_tests": node.get_metric("passed_tests", 0),
        "pass_rate_pct": node.get_metric("pass_rate_pct", 0.0),
    }

    # Body and rationale
    result["body"] = node.get_field("body", "")
    result["rationale"] = node.get_field("rationale", "")

    # Hash for change detection
    result["hash"] = node.hash

    # Metadata
    result["subdir"] = node.get_field("subdir", "")
    result["tags"] = node.get_field("tags", [])
    result["is_conflict"] = node.get_field("is_conflict", False)
    if result["is_conflict"]:
        result["conflict_with"] = node.get_field("conflict_with", "")

    return result


def _get_node_full_text(
    node: GraphNode,
    context: "WorkspaceContext",
) -> Optional[str]:
    """
    Get the full requirement text from its source file.

    Args:
        node: GraphNode with source location
        context: WorkspaceContext for file access

    Returns:
        Full requirement text or None if not accessible
    """
    if not node.source or not node.source.path:
        return None

    try:
        from elspais.mcp.mutator import SpecFileMutator

        mutator = SpecFileMutator(context.working_dir)
        content = mutator._read_spec_file(Path(node.source.path))
        location = mutator._find_requirement_lines(content, node.id)

        if location:
            return mutator.get_requirement_text(content, location)
    except (FileNotFoundError, ValueError, AttributeError):
        pass

    return None


def _serialize_assertions_with_coverage(node: GraphNode) -> List[Dict[str, Any]]:
    """
    Serialize assertions with coverage information from graph.

    Args:
        node: GraphNode for the requirement

    Returns:
        List of assertion dicts with coverage info
    """
    assertions_info = []

    for child in node.iter_children():
        if child.kind != NodeKind.ASSERTION:
            continue

        info: Dict[str, Any] = {
            "label": child.get_label(),
            "text": child.get_field("text", ""),
            "is_placeholder": child.get_field("is_placeholder", False),
        }

        # Add coverage info
        contributions = child.get_metric("_coverage_contributions", [])
        info["covered"] = len(contributions) > 0
        if contributions:
            first = contributions[0]
            if hasattr(first, "source_type"):
                info["coverage_source"] = (
                    first.source_type.value
                    if hasattr(first.source_type, "value")
                    else str(first.source_type)
                )

        assertions_info.append(info)

    return assertions_info


def serialize_mutation_entry(entry: "MutationEntry") -> Dict[str, Any]:
    """
    Serialize a MutationEntry to a JSON-compatible dict.

    Args:
        entry: MutationEntry to serialize

    Returns:
        Dict suitable for JSON serialization
    """
    from elspais.graph.mutations import MutationEntry

    return {
        "id": entry.id,
        "timestamp": entry.timestamp.isoformat(),
        "operation": entry.operation,
        "target_id": entry.target_id,
        "before_state": entry.before_state,
        "after_state": entry.after_state,
        "affects_hash": entry.affects_hash,
    }


def serialize_broken_reference(ref: "BrokenReference") -> Dict[str, Any]:
    """
    Serialize a BrokenReference to a JSON-compatible dict.

    Args:
        ref: BrokenReference to serialize

    Returns:
        Dict suitable for JSON serialization
    """
    from elspais.graph.mutations import BrokenReference

    return {
        "source_id": ref.source_id,
        "target_id": ref.target_id,
        "edge_kind": ref.edge_kind,
    }


__all__ = [
    "Severity",
    "RuleViolation",
    "serialize_assertion",
    "serialize_broken_reference",
    "serialize_content_rule",
    "serialize_mutation_entry",
    "serialize_node_full",
    "serialize_requirement",
    "serialize_requirement_summary",
    "serialize_violation",
]
