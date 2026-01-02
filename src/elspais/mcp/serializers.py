"""
elspais.mcp.serializers - JSON serialization for MCP responses.

Provides functions to serialize elspais data models to JSON-compatible dicts.
"""

from typing import Any, Dict, List

from elspais.core.models import Assertion, ContentRule, Requirement
from elspais.core.rules import RuleViolation


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
