"""
elspais.mcp.serializers - JSON serialization for MCP responses.

Provides functions to serialize elspais data models to JSON-compatible dicts.

Uses GraphNode from the traceability graph module.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from elspais.graph import GraphNode, NodeKind
from elspais.graph.builder import TraceGraph

if TYPE_CHECKING:
    from elspais.mcp.context import WorkspaceContext


def serialize_requirement(req: Requirement) -> Dict[str, Any]:
    """
    Serialize a Requirement to a JSON-compatible dict.

    Args:
        req: Requirement to serialize

    Returns:
        Dict suitable for JSON serialization
    """
    return {
        "id": req.id,
        "title": req.title,
        "level": req.level,
        "status": req.status,
        "body": req.body,
        "implements": req.implements,
        "refines": req.refines,
        "assertions": [serialize_assertion(a) for a in req.assertions],
        "rationale": req.rationale,
        "hash": req.hash,
        "file_path": str(req.file_path) if req.file_path else None,
        "line_number": req.line_number,
        "subdir": req.subdir,
        "type_code": req.type_code,
    }


def serialize_requirement_summary(req: Requirement) -> Dict[str, Any]:
    """
    Serialize requirement summary (lighter weight, for listings).

    Args:
        req: Requirement to serialize

    Returns:
        Dict with summary fields only
    """
    return {
        "id": req.id,
        "title": req.title,
        "level": req.level,
        "status": req.status,
        "implements": req.implements,
        "refines": req.refines,
        "assertion_count": len(req.assertions),
    }


def serialize_assertion(assertion: Assertion) -> Dict[str, Any]:
    """
    Serialize an Assertion to a JSON-compatible dict.

    Args:
        assertion: Assertion to serialize

    Returns:
        Dict suitable for JSON serialization
    """
    return {
        "label": assertion.label,
        "text": assertion.text,
        "is_placeholder": assertion.is_placeholder,
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
    req: Requirement,
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
        req: Requirement to serialize
        context: WorkspaceContext for graph access
        include_full_text: If True, include full_text from file

    Returns:
        Dict suitable for JSON serialization and AI processing
    """
    result: Dict[str, Any] = {
        "id": req.id,
        "title": req.title,
        "level": req.level,
        "status": req.status,
        "type_code": req.type_code,
    }

    # Get the graph node for metrics and relationships
    graph, _ = context.get_graph()
    node = graph.find_by_id(req.id)

    # Source location
    if req.file_path:
        result["file_path"] = str(req.file_path)
        result["line_number"] = req.line_number

        # Get line range from mutator if we need full text
        if include_full_text:
            full_text = _get_requirement_full_text(req, context)
            if full_text:
                result["full_text"] = full_text

                # Calculate line range
                if req.line_number:
                    line_count = full_text.count("\n") + 1
                    result["line_range"] = [req.line_number, req.line_number + line_count - 1]

    # Source info from graph node (if available)
    if node and node.source:
        result["source"] = {
            "path": node.source.path,
            "line": node.source.line,
            "end_line": node.source.end_line,
        }

    # Assertions with coverage info
    assertions_info = _serialize_assertions_with_coverage(req, node)
    result["assertions"] = assertions_info

    # Relationships
    result["implements"] = req.implements
    result["refines"] = req.refines

    # Implemented_by - find children that implement this requirement
    if node:
        implemented_by = _get_implementing_children(node)
        result["implemented_by"] = implemented_by
        result["refined_by"] = []  # Not currently tracked in reverse

    # Metrics from graph node
    if node and node.metrics:
        metrics = node.metrics
        result["metrics"] = {
            "total_assertions": metrics.get("total_assertions", len(req.assertions)),
            "covered_assertions": metrics.get("covered_assertions", 0),
            "coverage_pct": metrics.get("coverage_pct", 0.0),
            "direct_covered": metrics.get("direct_covered", 0),
            "explicit_covered": metrics.get("explicit_covered", 0),
            "inferred_covered": metrics.get("inferred_covered", 0),
            "total_tests": metrics.get("total_tests", 0),
            "passed_tests": metrics.get("passed_tests", 0),
            "pass_rate_pct": metrics.get("pass_rate_pct", 0.0),
        }
    else:
        result["metrics"] = {
            "total_assertions": len(req.assertions),
            "covered_assertions": 0,
            "coverage_pct": 0.0,
        }

    # Body and rationale
    result["body"] = req.body
    result["rationale"] = req.rationale

    # Hash for change detection
    result["hash"] = req.hash

    # Metadata
    result["subdir"] = req.subdir
    result["tags"] = req.tags
    result["is_conflict"] = req.is_conflict
    if req.is_conflict:
        result["conflict_with"] = req.conflict_with

    return result


def _get_requirement_full_text(
    req: Requirement,
    context: "WorkspaceContext",
) -> Optional[str]:
    """
    Get the full requirement text from its source file.

    Args:
        req: Requirement with file_path
        context: WorkspaceContext for mutator access

    Returns:
        Full requirement text or None if not accessible
    """
    if not req.file_path:
        return None

    try:
        from elspais.mcp.mutator import SpecFileMutator

        mutator = SpecFileMutator(context.working_dir)
        content = mutator._read_spec_file(Path(req.file_path))
        location = mutator._find_requirement_lines(content, req.id)

        if location:
            return mutator.get_requirement_text(content, location)
    except (FileNotFoundError, ValueError):
        pass

    return None


def _serialize_assertions_with_coverage(
    req: Requirement,
    node: Optional[GraphNode],
) -> List[Dict[str, Any]]:
    """
    Serialize assertions with coverage information from graph.

    Args:
        req: Requirement containing assertions
        node: GraphNode for the requirement (may be None)

    Returns:
        List of assertion dicts with coverage info
    """
    assertions_info = []

    # Build a map of assertion coverage from graph
    assertion_coverage: Dict[str, Dict[str, Any]] = {}
    if node:
        for child in node.children:
            if child.kind == NodeKind.ASSERTION:
                # Extract assertion label from ID (e.g., "REQ-p00001-A" -> "A")
                label = child.id.rsplit("-", 1)[-1] if "-" in child.id else child.id
                contributions = child.metrics.get("_coverage_contributions", [])
                covered = len(contributions) > 0
                source_type = None
                if contributions:
                    first = contributions[0]
                    if hasattr(first, "source_type"):
                        source_type = (
                            first.source_type.value
                            if hasattr(first.source_type, "value")
                            else str(first.source_type)
                        )
                assertion_coverage[label] = {
                    "covered": covered,
                    "coverage_source": source_type,
                }

    # Serialize each assertion
    for assertion in req.assertions:
        info: Dict[str, Any] = {
            "label": assertion.label,
            "text": assertion.text,
            "is_placeholder": assertion.is_placeholder,
        }

        # Add coverage info if available
        coverage = assertion_coverage.get(assertion.label, {})
        info["covered"] = coverage.get("covered", False)
        if coverage.get("coverage_source"):
            info["coverage_source"] = coverage["coverage_source"]

        assertions_info.append(info)

    return assertions_info


def _get_implementing_children(node: GraphNode) -> List[str]:
    """
    Get IDs of requirement children that implement this node.

    Args:
        node: GraphNode to find implementers for

    Returns:
        List of requirement IDs that implement this node
    """
    implementers = []
    for child in node.children:
        if child.kind == NodeKind.REQUIREMENT:
            implementers.append(child.id)
    return implementers
