# Implements: REQ-int-d00003 (CLI Extension)
"""
elspais.commands.health - Diagnose configuration and repository health.

Provides comprehensive health checks for:
- Config: TOML syntax, required fields, valid paths
- Spec: File parsing, duplicate IDs, reference resolution
- Code: Code→REQ reference validation
- Tests: Test→REQ mapping validation
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator

if TYPE_CHECKING:
    from elspais.config import ConfigLoader
    from elspais.graph.builder import TraceGraph


@dataclass
class HealthCheck:
    """Result of a single health check."""

    name: str
    passed: bool
    message: str
    category: str  # config, spec, code, tests
    severity: str = "error"  # error, warning, info
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class HealthReport:
    """Aggregated health check results."""

    checks: list[HealthCheck] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for c in self.checks if c.passed)

    @property
    def failed(self) -> int:
        return sum(1 for c in self.checks if not c.passed and c.severity == "error")

    @property
    def warnings(self) -> int:
        return sum(1 for c in self.checks if not c.passed and c.severity == "warning")

    @property
    def is_healthy(self) -> bool:
        return self.failed == 0

    def add(self, check: HealthCheck) -> None:
        self.checks.append(check)

    def iter_by_category(self, category: str) -> Iterator[HealthCheck]:
        for check in self.checks:
            if check.category == category:
                yield check

    def to_dict(self) -> dict[str, Any]:
        return {
            "healthy": self.is_healthy,
            "summary": {
                "passed": self.passed,
                "failed": self.failed,
                "warnings": self.warnings,
            },
            "checks": [
                {
                    "name": c.name,
                    "passed": c.passed,
                    "message": c.message,
                    "category": c.category,
                    "severity": c.severity,
                    "details": c.details,
                }
                for c in self.checks
            ],
        }


# =============================================================================
# Config Checks
# =============================================================================


def check_config_exists(config_path: Path | None, start_path: Path) -> HealthCheck:
    """Check if config file exists and is accessible."""
    from elspais.config import find_config_file

    if config_path and config_path.exists():
        return HealthCheck(
            name="config.exists",
            passed=True,
            message=f"Config file found: {config_path}",
            category="config",
            details={"path": str(config_path)},
        )

    # Try auto-discovery
    found = find_config_file(start_path)
    if found:
        return HealthCheck(
            name="config.exists",
            passed=True,
            message=f"Config file found: {found}",
            category="config",
            details={"path": str(found)},
        )

    return HealthCheck(
        name="config.exists",
        passed=True,  # Using defaults is valid
        message="No config file found, using defaults",
        category="config",
        severity="info",
    )


def check_config_syntax(config_path: Path | None, start_path: Path) -> HealthCheck:
    """Check if config file has valid TOML syntax."""
    from elspais.config import find_config_file

    actual_path = (
        config_path if config_path and config_path.exists() else find_config_file(start_path)
    )

    if not actual_path:
        return HealthCheck(
            name="config.syntax",
            passed=True,
            message="No config file to validate (using defaults)",
            category="config",
            severity="info",
        )

    try:
        content = actual_path.read_text(encoding="utf-8")
        # Validate TOML syntax using the public parser
        from elspais.config import parse_toml

        parse_toml(content)
        return HealthCheck(
            name="config.syntax",
            passed=True,
            message="TOML syntax is valid",
            category="config",
        )
    except Exception as e:
        return HealthCheck(
            name="config.syntax",
            passed=False,
            message=f"TOML syntax error: {e}",
            category="config",
            details={"error": str(e), "path": str(actual_path)},
        )


def check_config_required_fields(config: ConfigLoader) -> HealthCheck:
    """Check that required configuration sections exist."""
    raw = config.get_raw()
    missing = []

    # Check for patterns section with types
    patterns = raw.get("patterns", {})
    if not patterns.get("types"):
        missing.append("patterns.types")

    # Check for spec directories
    spec = raw.get("spec", {})
    if not spec.get("directories"):
        missing.append("spec.directories")

    # Check for hierarchy rules
    rules = raw.get("rules", {})
    if not rules.get("hierarchy"):
        missing.append("rules.hierarchy")

    if missing:
        return HealthCheck(
            name="config.required_fields",
            passed=False,
            message=f"Missing required fields: {', '.join(missing)}",
            category="config",
            severity="warning",
            details={"missing": missing},
        )

    return HealthCheck(
        name="config.required_fields",
        passed=True,
        message="All required configuration fields present",
        category="config",
    )


def check_config_pattern_tokens(config: ConfigLoader) -> HealthCheck:
    """Validate that pattern template uses valid tokens."""
    template = config.get("patterns.id_template", "")
    valid_tokens = {"{prefix}", "{type}", "{id}", "{associated}"}

    # Find all tokens in template
    import re

    found_tokens = set(re.findall(r"\{[^}]+\}", template))

    invalid = found_tokens - valid_tokens
    if invalid:
        return HealthCheck(
            name="config.pattern_tokens",
            passed=False,
            message=f"Invalid pattern tokens: {', '.join(invalid)}",
            category="config",
            details={"invalid_tokens": list(invalid), "valid_tokens": list(valid_tokens)},
        )

    # Check that essential tokens are present
    required = {"{prefix}", "{id}"}
    missing = required - found_tokens
    if missing:
        return HealthCheck(
            name="config.pattern_tokens",
            passed=False,
            message=f"Missing required tokens: {', '.join(missing)}",
            category="config",
            severity="warning",
            details={"missing": list(missing)},
        )

    return HealthCheck(
        name="config.pattern_tokens",
        passed=True,
        message=f"Pattern template valid: {template}",
        category="config",
    )


def check_config_hierarchy_rules(config: ConfigLoader) -> HealthCheck:
    """Validate hierarchy rules are consistent."""
    hierarchy = config.get("rules.hierarchy", {})
    types = config.get("patterns.types", {})

    # Handle non-dict hierarchy (e.g., hierarchy = false)
    if not isinstance(hierarchy, dict):
        return HealthCheck(
            name="config.hierarchy_rules",
            passed=False,
            message=f"rules.hierarchy must be a dict, got {type(hierarchy).__name__}",
            category="config",
            severity="warning",
        )

    # Handle non-dict types
    if not isinstance(types, dict):
        return HealthCheck(
            name="config.hierarchy_rules",
            passed=False,
            message=f"patterns.types must be a dict, got {type(types).__name__}",
            category="config",
            severity="warning",
        )

    issues = []

    # Known non-level keys in rules.hierarchy (config options, not level definitions)
    non_level_keys = {"allowed_implements", "allow_circular", "allow_orphans", "allowed"}

    for level, allowed_parents in hierarchy.items():
        # Skip known config options that aren't level definitions
        if level in non_level_keys:
            continue

        # Check level exists in types
        if level not in types:
            issues.append(f"Rule for '{level}' but type not defined")
            continue

        # Handle non-list allowed_parents
        if not isinstance(allowed_parents, list):
            issues.append(
                f"Hierarchy rule for '{level}' must be a list, got {type(allowed_parents).__name__}"
            )
            continue

        # Check allowed parents exist
        for parent in allowed_parents:
            if parent not in types:
                issues.append(f"'{level}' can implement '{parent}' but '{parent}' type not defined")

    if issues:
        return HealthCheck(
            name="config.hierarchy_rules",
            passed=False,
            message=f"Hierarchy issues: {'; '.join(issues)}",
            category="config",
            severity="warning",
            details={"issues": issues},
        )

    return HealthCheck(
        name="config.hierarchy_rules",
        passed=True,
        message=f"Hierarchy rules valid ({len(hierarchy)} levels configured)",
        category="config",
    )


def check_config_paths_exist(config: ConfigLoader, start_path: Path) -> HealthCheck:
    """Check that configured directories exist."""
    spec_dirs = config.get("spec.directories", ["spec"])

    # Handle non-list spec_dirs
    if not isinstance(spec_dirs, list):
        return HealthCheck(
            name="config.paths_exist",
            passed=False,
            message=f"spec.directories must be a list, got {type(spec_dirs).__name__}",
            category="config",
            severity="warning",
        )

    missing = []
    found = []

    for spec_dir in spec_dirs:
        full_path = start_path / spec_dir
        if full_path.exists():
            found.append(str(spec_dir))
        else:
            missing.append(str(spec_dir))

    if missing:
        return HealthCheck(
            name="config.paths_exist",
            passed=False,
            message=f"Spec directories not found: {', '.join(missing)}",
            category="config",
            details={"missing": missing, "found": found},
        )

    return HealthCheck(
        name="config.paths_exist",
        passed=True,
        message=f"All spec directories exist ({len(found)} found)",
        category="config",
        details={"directories": found},
    )


def check_config_project_type(config: ConfigLoader) -> HealthCheck:
    """Validate project type configuration consistency.

    Checks that project.type matches the presence of [core] and [associated] sections.
    """
    from elspais.config import validate_project_config

    raw = config.get_raw()
    errors = validate_project_config(raw)

    if errors:
        return HealthCheck(
            name="config.project_type",
            passed=False,
            message=errors[0],  # First error as main message
            category="config",
            severity="warning",
            details={"errors": errors},
        )

    project_type = raw.get("project", {}).get("type")
    if project_type:
        return HealthCheck(
            name="config.project_type",
            passed=True,
            message=f"Project type '{project_type}' configuration is valid",
            category="config",
            details={"type": project_type},
        )

    return HealthCheck(
        name="config.project_type",
        passed=True,
        message="Project type not set (using defaults)",
        category="config",
        severity="info",
    )


def run_config_checks(
    config_path: Path | None, config: ConfigLoader, start_path: Path
) -> list[HealthCheck]:
    """Run all configuration health checks."""
    return [
        check_config_exists(config_path, start_path),
        check_config_syntax(config_path, start_path),
        check_config_required_fields(config),
        check_config_project_type(config),
        check_config_pattern_tokens(config),
        check_config_hierarchy_rules(config),
        check_config_paths_exist(config, start_path),
    ]


# =============================================================================
# Spec Checks
# =============================================================================


def check_spec_files_parseable(graph: TraceGraph) -> HealthCheck:
    """Check that all spec files were parsed without errors."""
    from elspais.graph import NodeKind

    # Count requirements found
    req_count = sum(1 for _ in graph.nodes_by_kind(NodeKind.REQUIREMENT))
    assertion_count = sum(1 for _ in graph.nodes_by_kind(NodeKind.ASSERTION))

    if req_count == 0:
        return HealthCheck(
            name="spec.parseable",
            passed=False,
            message="No requirements found in spec files",
            category="spec",
            severity="warning",
        )

    return HealthCheck(
        name="spec.parseable",
        passed=True,
        message=f"Parsed {req_count} requirements with {assertion_count} assertions",
        category="spec",
        details={"requirements": req_count, "assertions": assertion_count},
    )


def check_spec_no_duplicates(graph: TraceGraph) -> HealthCheck:
    """Check for duplicate requirement IDs."""
    from elspais.graph import NodeKind

    seen_ids: dict[str, list[str]] = {}

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        node_id = node.id
        source = node.get_field("source_file", "unknown")

        if node_id in seen_ids:
            seen_ids[node_id].append(source)
        else:
            seen_ids[node_id] = [source]

    duplicates = {k: v for k, v in seen_ids.items() if len(v) > 1}

    if duplicates:
        return HealthCheck(
            name="spec.no_duplicates",
            passed=False,
            message=f"Found {len(duplicates)} duplicate requirement IDs",
            category="spec",
            details={"duplicates": duplicates},
        )

    return HealthCheck(
        name="spec.no_duplicates",
        passed=True,
        message="No duplicate requirement IDs",
        category="spec",
    )


def check_spec_implements_resolve(graph: TraceGraph) -> HealthCheck:
    """Check that all Implements references resolve to valid requirements."""
    from elspais.graph import NodeKind

    unresolved = []

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        # Get implements field
        implements = node.get_field("implements", [])
        for ref in implements:
            # Try to find the referenced requirement
            target = graph.find_by_id(ref)
            if target is None:
                # Check if it's an assertion reference (e.g., REQ-xxx-A)
                if "-" in ref:
                    parts = ref.rsplit("-", 1)
                    if len(parts) == 2:
                        parent_id, assertion_label = parts
                        parent = graph.find_by_id(parent_id)
                        if parent is not None:
                            continue  # Assertion reference is valid
                unresolved.append({"from": node.id, "to": ref})

    if unresolved:
        return HealthCheck(
            name="spec.implements_resolve",
            passed=False,
            message=f"{len(unresolved)} unresolved Implements references",
            category="spec",
            severity="warning",
            details={"unresolved": unresolved[:10]},  # Limit to first 10
        )

    return HealthCheck(
        name="spec.implements_resolve",
        passed=True,
        message="All Implements references resolve",
        category="spec",
    )


def check_spec_refines_resolve(graph: TraceGraph) -> HealthCheck:
    """Check that all Refines references resolve to valid requirements."""
    from elspais.graph import NodeKind

    unresolved = []

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        refines = node.get_field("refines", [])
        for ref in refines:
            target = graph.find_by_id(ref)
            if target is None:
                # Check assertion reference
                if "-" in ref:
                    parts = ref.rsplit("-", 1)
                    if len(parts) == 2:
                        parent_id, _ = parts
                        parent = graph.find_by_id(parent_id)
                        if parent is not None:
                            continue
                unresolved.append({"from": node.id, "to": ref})

    if unresolved:
        return HealthCheck(
            name="spec.refines_resolve",
            passed=False,
            message=f"{len(unresolved)} unresolved Refines references",
            category="spec",
            severity="warning",
            details={"unresolved": unresolved[:10]},
        )

    return HealthCheck(
        name="spec.refines_resolve",
        passed=True,
        message="All Refines references resolve",
        category="spec",
    )


def _parse_hierarchy_rules(hierarchy: dict[str, Any]) -> dict[str, list[str]]:
    """Parse hierarchy rules from config.

    Expected format: { "dev": ["ops", "prd"], "prd": ["prd"] }

    Returns:
        Dict mapping child level -> list of allowed parent levels (lowercase)
    """
    result: dict[str, list[str]] = {}

    # Filter out non-level keys
    non_level_keys = {"allow_circular", "allow_orphans", "cross_repo_implements"}
    for key, value in hierarchy.items():
        if key in non_level_keys:
            continue
        if isinstance(value, list):
            result[key.lower()] = [v.lower() for v in value]

    return result


def check_spec_hierarchy_levels(graph: TraceGraph, config: ConfigLoader) -> HealthCheck:
    """Check that hierarchy levels follow configured rules."""
    from elspais.graph import NodeKind

    hierarchy = config.get("rules.hierarchy", {})
    types = config.get("patterns.types", {})
    strict_hierarchy = config.get("validation.strict_hierarchy", False)

    # Parse hierarchy rules
    allowed_parents_map = _parse_hierarchy_rules(hierarchy)

    # Build level lookup: type_id -> level_name (lowercase)
    # Note: level_lookup reserved for future strict hierarchy validation
    _ = {v["id"]: k for k, v in types.items()}

    violations = []

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        node_level = node.level.lower() if node.level else None
        if not node_level:
            continue

        allowed_parents = allowed_parents_map.get(node_level, [])

        for parent in node.iter_parents():
            if parent.kind != NodeKind.REQUIREMENT:
                continue
            parent_level = parent.level.lower() if parent.level else None
            if parent_level and parent_level not in allowed_parents:
                violations.append(
                    {
                        "child": node.id,
                        "child_level": node_level.upper(),
                        "parent": parent.id,
                        "parent_level": parent_level.upper(),
                    }
                )

    if violations:
        # Severity controlled by validation.strict_hierarchy config
        if strict_hierarchy:
            return HealthCheck(
                name="spec.hierarchy_levels",
                passed=False,
                message=f"{len(violations)} hierarchy level violations",
                category="spec",
                severity="warning",
                details={"violations": violations[:10]},
            )
        else:
            return HealthCheck(
                name="spec.hierarchy_levels",
                passed=True,  # Informational when not strict
                message=f"{len(violations)} hierarchy level deviations (strict_hierarchy=false)",
                category="spec",
                severity="info",
                details={
                    "violations": violations[:10],
                    "hint": "Set validation.strict_hierarchy=true to enforce",
                },
            )

    return HealthCheck(
        name="spec.hierarchy_levels",
        passed=True,
        message="All requirements follow hierarchy rules",
        category="spec",
    )


def check_spec_orphans(graph: TraceGraph) -> HealthCheck:
    """Check for orphaned nodes across all kinds.

    Uses graph.orphaned_nodes() which returns all parentless nodes
    that have no meaningful (non-satellite) children.
    """
    by_kind: dict[str, list[dict]] = {}

    for node in graph.orphaned_nodes():
        kind_name = node.kind.value
        if kind_name not in by_kind:
            by_kind[kind_name] = []
        entry: dict = {"id": node.id, "kind": kind_name}
        if node.level:
            entry["level"] = node.level
        by_kind[kind_name].append(entry)

    total = sum(len(nodes) for nodes in by_kind.values())

    if total:
        summary_parts = [f"{len(v)} {k}" for k, v in sorted(by_kind.items())]
        return HealthCheck(
            name="spec.orphans",
            passed=False,
            message=f"{total} orphaned nodes ({', '.join(summary_parts)})",
            category="spec",
            severity="warning",
            details={
                "by_kind": {k: v[:10] for k, v in by_kind.items()},
                "total": total,
            },
        )

    return HealthCheck(
        name="spec.orphans",
        passed=True,
        message="No orphaned nodes",
        category="spec",
    )


def check_spec_format_rules(graph: TraceGraph, config: ConfigLoader) -> HealthCheck:
    """Check that requirements comply with configured format rules."""
    from elspais.graph import NodeKind
    from elspais.validation.format import get_format_rules_config, validate_requirement_format

    rules = get_format_rules_config(config.get_raw())

    # Check if any rules are enabled
    rules_enabled = any(
        [
            rules.require_hash,
            rules.require_assertions,
            rules.require_rationale,
            rules.require_shall,
            rules.require_status,
            bool(rules.allowed_statuses),
            rules.labels_sequential,
            rules.labels_unique,
        ]
    )

    if not rules_enabled:
        return HealthCheck(
            name="spec.format_rules",
            passed=True,
            message="No format rules enabled (configure in [rules.format])",
            category="spec",
            severity="info",
        )

    all_violations = []
    req_count = 0

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        req_count += 1
        violations = validate_requirement_format(node, rules)
        all_violations.extend(violations)

    errors = [v for v in all_violations if v.severity == "error"]
    warnings = [v for v in all_violations if v.severity == "warning"]

    if errors:
        return HealthCheck(
            name="spec.format_rules",
            passed=False,
            message=f"{len(errors)} format error(s) in {req_count} requirements",
            category="spec",
            details={
                "errors": [
                    {"rule": v.rule, "message": v.message, "node": v.node_id} for v in errors
                ],
                "warnings": [
                    {"rule": v.rule, "message": v.message, "node": v.node_id} for v in warnings
                ],
            },
        )

    if warnings:
        return HealthCheck(
            name="spec.format_rules",
            passed=True,
            message=f"{req_count} requirements pass format rules ({len(warnings)} warning(s))",
            category="spec",
            severity="warning",
            details={
                "warnings": [
                    {"rule": v.rule, "message": v.message, "node": v.node_id} for v in warnings
                ],
            },
        )

    return HealthCheck(
        name="spec.format_rules",
        passed=True,
        message=f"{req_count} requirements pass all format rules",
        category="spec",
    )


def run_spec_checks(graph: TraceGraph, config: ConfigLoader) -> list[HealthCheck]:
    """Run all spec file health checks."""
    return [
        check_spec_files_parseable(graph),
        check_spec_no_duplicates(graph),
        check_spec_implements_resolve(graph),
        check_spec_refines_resolve(graph),
        check_spec_hierarchy_levels(graph, config),
        check_spec_orphans(graph),
        check_spec_format_rules(graph, config),
    ]


# =============================================================================
# Code Checks
# =============================================================================


def check_code_references_resolve(graph: TraceGraph) -> HealthCheck:
    """Check that code # Implements: references resolve to valid requirements."""
    from elspais.graph import NodeKind

    code_nodes = list(graph.nodes_by_kind(NodeKind.CODE))

    if not code_nodes:
        return HealthCheck(
            name="code.references_resolve",
            passed=True,
            message="No code references found (code scanning may be disabled)",
            category="code",
            severity="info",
        )

    unresolved = []
    resolved_count = 0

    for node in code_nodes:
        # CODE nodes reference requirements via parents
        has_valid_parent = False
        for parent in node.iter_parents():
            if parent.kind in (NodeKind.REQUIREMENT, NodeKind.ASSERTION):
                has_valid_parent = True
                resolved_count += 1
                break

        if not has_valid_parent:
            implements = node.get_field("implements", [])
            unresolved.append(
                {
                    "source": node.get_field("source_file", "unknown"),
                    "line": node.get_field("line", 0),
                    "references": implements,
                }
            )

    if unresolved:
        return HealthCheck(
            name="code.references_resolve",
            passed=False,
            message=f"{len(unresolved)} code references don't resolve to requirements",
            category="code",
            severity="warning",
            details={"unresolved": unresolved[:10], "resolved_count": resolved_count},
        )

    return HealthCheck(
        name="code.references_resolve",
        passed=True,
        message=f"All {resolved_count} code references resolve to requirements",
        category="code",
        details={"resolved_count": resolved_count},
    )


def check_code_coverage(graph: TraceGraph) -> HealthCheck:
    """Check code coverage statistics."""
    from elspais.graph import NodeKind
    from elspais.graph.annotators import count_with_code_refs

    code_count = sum(1 for _ in graph.nodes_by_kind(NodeKind.CODE))
    coverage = count_with_code_refs(graph)

    return HealthCheck(
        name="code.coverage",
        passed=True,  # Informational only
        message=(
            f"{coverage['with_code_refs']}/{coverage['total_requirements']} requirements "
            f"have code references ({coverage['coverage_percent']}%)"
        ),
        category="code",
        severity="info",
        details={
            "code_nodes": code_count,
            "requirements_with_code": coverage["with_code_refs"],
            "total_requirements": coverage["total_requirements"],
            "coverage_percent": coverage["coverage_percent"],
        },
    )


def run_code_checks(graph: TraceGraph) -> list[HealthCheck]:
    """Run all code reference health checks."""
    return [
        check_code_references_resolve(graph),
        check_code_coverage(graph),
    ]


# =============================================================================
# Test Checks
# =============================================================================


def check_test_references_resolve(graph: TraceGraph) -> HealthCheck:
    """Check that test file REQ references resolve to valid requirements."""
    from elspais.graph import NodeKind

    test_nodes = list(graph.nodes_by_kind(NodeKind.TEST))

    if not test_nodes:
        return HealthCheck(
            name="tests.references_resolve",
            passed=True,
            message="No test references found (test scanning may be disabled)",
            category="tests",
            severity="info",
        )

    unresolved = []
    resolved_count = 0

    for node in test_nodes:
        has_valid_parent = False
        for parent in node.iter_parents():
            if parent.kind in (NodeKind.REQUIREMENT, NodeKind.ASSERTION):
                has_valid_parent = True
                resolved_count += 1
                break

        if not has_valid_parent:
            unresolved.append(
                {
                    "source": node.get_field("source_file", "unknown"),
                    "test_name": node.get_label() or node.id,
                }
            )

    if unresolved:
        return HealthCheck(
            name="tests.references_resolve",
            passed=False,
            message=f"{len(unresolved)} test references don't resolve to requirements",
            category="tests",
            severity="warning",
            details={"unresolved": unresolved[:10], "resolved_count": resolved_count},
        )

    return HealthCheck(
        name="tests.references_resolve",
        passed=True,
        message=f"All {resolved_count} test references resolve to requirements",
        category="tests",
        details={"resolved_count": resolved_count},
    )


def check_test_results(graph: TraceGraph) -> HealthCheck:
    """Check test result status from JUnit/pytest output."""
    from elspais.graph import NodeKind

    result_nodes = list(graph.nodes_by_kind(NodeKind.TEST_RESULT))

    if not result_nodes:
        return HealthCheck(
            name="tests.results",
            passed=True,
            message="No test results found (result scanning may be disabled)",
            category="tests",
            severity="info",
        )

    passed = 0
    failed = 0
    skipped = 0

    for node in result_nodes:
        status = node.get_field("status", "unknown")
        if status == "passed":
            passed += 1
        elif status == "failed":
            failed += 1
        elif status == "skipped":
            skipped += 1

    total = passed + failed + skipped
    pass_rate = (passed / total * 100) if total > 0 else 0

    if failed > 0:
        return HealthCheck(
            name="tests.results",
            passed=False,
            message=(
                f"Test failures: {passed} passed, {failed} failed, "
                f"{skipped} skipped ({pass_rate:.1f}% pass rate)"
            ),
            category="tests",
            severity="warning",
            details={
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "pass_rate": round(pass_rate, 1),
            },
        )

    return HealthCheck(
        name="tests.results",
        passed=True,
        message=f"All tests passing: {passed} passed, {skipped} skipped",
        category="tests",
        details={
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "pass_rate": round(pass_rate, 1),
        },
    )


def check_test_coverage(graph: TraceGraph) -> HealthCheck:
    """Check test coverage statistics."""
    from elspais.graph import NodeKind

    test_count = sum(1 for _ in graph.nodes_by_kind(NodeKind.TEST))
    req_count = sum(1 for _ in graph.nodes_by_kind(NodeKind.REQUIREMENT))

    # Count requirements with at least one TEST child
    covered_reqs = set()
    for node in graph.nodes_by_kind(NodeKind.TEST):
        for parent in node.iter_parents():
            if parent.kind == NodeKind.REQUIREMENT:
                covered_reqs.add(parent.id)
            elif parent.kind == NodeKind.ASSERTION:
                for grandparent in parent.iter_parents():
                    if grandparent.kind == NodeKind.REQUIREMENT:
                        covered_reqs.add(grandparent.id)

    coverage_pct = (len(covered_reqs) / req_count * 100) if req_count > 0 else 0

    return HealthCheck(
        name="tests.coverage",
        passed=True,  # Informational only
        message=(
            f"{len(covered_reqs)}/{req_count} requirements "
            f"have test references ({coverage_pct:.1f}%)"
        ),
        category="tests",
        severity="info",
        details={
            "test_nodes": test_count,
            "requirements_with_tests": len(covered_reqs),
            "total_requirements": req_count,
            "coverage_percent": round(coverage_pct, 1),
        },
    )


def run_test_checks(graph: TraceGraph) -> list[HealthCheck]:
    """Run all test file health checks."""
    return [
        check_test_references_resolve(graph),
        check_test_results(graph),
        check_test_coverage(graph),
    ]


# =============================================================================
# Main Command
# =============================================================================


def run(args: argparse.Namespace) -> int:
    """Run the health command.

    Performs comprehensive health checks on the elspais configuration
    and repository structure.
    """
    from elspais.config import ConfigLoader, get_config
    from elspais.graph.factory import build_graph

    spec_dir = getattr(args, "spec_dir", None)
    config_path = getattr(args, "config", None)
    start_path = Path.cwd()

    report = HealthReport()

    # Determine which checks to run
    run_all = not any(
        [
            getattr(args, "config_only", False),
            getattr(args, "spec_only", False),
            getattr(args, "code_only", False),
            getattr(args, "tests_only", False),
        ]
    )

    run_config = run_all or getattr(args, "config_only", False)
    run_spec = run_all or getattr(args, "spec_only", False)
    run_code = run_all or getattr(args, "code_only", False)
    run_tests = run_all or getattr(args, "tests_only", False)

    # Config checks can run without building the graph
    config = None
    if run_config:
        try:
            config_dict = get_config(config_path, start_path=start_path)
            config = ConfigLoader.from_dict(config_dict)
            for check in run_config_checks(config_path, config, start_path):
                report.add(check)
        except Exception as e:
            report.add(
                HealthCheck(
                    name="config.load",
                    passed=False,
                    message=f"Failed to load config: {e}",
                    category="config",
                )
            )
            # Can't continue without config
            if not run_all:
                return _output_report(report, args)

    # Build graph for other checks
    graph = None
    if run_spec or run_code or run_tests:
        try:
            graph = build_graph(
                spec_dirs=[spec_dir] if spec_dir else None,
                config_path=config_path,
            )
            if config is None:
                config_dict = get_config(config_path, start_path=start_path)
                config = ConfigLoader.from_dict(config_dict)
        except Exception as e:
            report.add(
                HealthCheck(
                    name="graph.build",
                    passed=False,
                    message=f"Failed to build graph: {e}",
                    category="spec",
                )
            )
            return _output_report(report, args)

    # Spec checks
    if run_spec and graph and config:
        for check in run_spec_checks(graph, config):
            report.add(check)

    # Code checks
    if run_code and graph:
        for check in run_code_checks(graph):
            report.add(check)

    # Test checks
    if run_tests and graph:
        for check in run_test_checks(graph):
            report.add(check)

    return _output_report(report, args)


def _output_report(report: HealthReport, args: argparse.Namespace) -> int:
    """Output the health report in the requested format."""
    if getattr(args, "json", False):
        print(json.dumps(report.to_dict(), indent=2))
    else:
        _print_text_report(report, verbose=getattr(args, "verbose", False))

    return 0 if report.is_healthy else 1


def _print_text_report(report: HealthReport, verbose: bool = False) -> None:
    """Print human-readable health report."""
    categories = ["config", "spec", "code", "tests"]

    for category in categories:
        checks = list(report.iter_by_category(category))
        if not checks:
            continue

        # Category header
        passed = sum(1 for c in checks if c.passed)
        total = len(checks)
        status = "✓" if passed == total else "✗"
        print(f"\n{status} {category.upper()} ({passed}/{total} checks passed)")
        print("-" * 40)

        for check in checks:
            if check.passed:
                icon = "✓"
            elif check.severity == "warning":
                icon = "⚠"
            else:
                icon = "✗"

            print(f"  {icon} {check.name}: {check.message}")

            # Show details in verbose mode
            if verbose and check.details:
                for key, value in check.details.items():
                    if isinstance(value, list) and len(value) > 3:
                        print(f"      {key}: {value[:3]} ... ({len(value)} total)")
                    else:
                        print(f"      {key}: {value}")

    # Summary
    print()
    print("=" * 40)
    if report.is_healthy:
        print(f"✓ HEALTHY: {report.passed} checks passed")
    else:
        print(f"✗ UNHEALTHY: {report.failed} errors, {report.warnings} warnings")
    print("=" * 40)
