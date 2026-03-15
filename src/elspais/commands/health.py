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
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from elspais.config import ConfigLoader
    from elspais.graph.builder import TraceGraph
    from elspais.utilities.patterns import IdResolver


# Implements: REQ-d00085-I
@dataclass
class HealthFinding:
    """Individual finding within a health check, with optional source location."""

    message: str
    file_path: str | None = None
    line: int | None = None
    node_id: str | None = None
    related: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "file_path": self.file_path,
            "line": self.line,
            "node_id": self.node_id,
            "related": self.related,
        }


@dataclass
class HealthCheck:
    """Result of a single health check."""

    name: str
    passed: bool
    message: str
    category: str  # config, spec, code, tests
    severity: str = "error"  # error, warning, info
    details: dict[str, Any] = field(default_factory=dict)
    findings: list[HealthFinding] = field(default_factory=list)


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
        return self.failed == 0 and self.warnings == 0

    @property
    def is_healthy_lenient(self) -> bool:
        return self.failed == 0

    def add(self, check: HealthCheck) -> None:
        self.checks.append(check)

    def iter_by_category(self, category: str) -> Iterator[HealthCheck]:
        for check in self.checks:
            if check.category == category:
                yield check

    def to_dict(self, lenient: bool = False) -> dict[str, Any]:
        healthy = self.is_healthy_lenient if lenient else self.is_healthy
        return {
            "healthy": healthy,
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
                    "findings": [f.to_dict() for f in c.findings],
                }
                for c in self.checks
            ],
        }


# =============================================================================
# Config Checks (delegated to doctor module, lazy import to avoid circular dep)
# =============================================================================

_DOCTOR_NAMES = {
    "check_config_exists",
    "check_config_hierarchy_rules",
    "check_config_paths_exist",
    "check_config_pattern_tokens",
    "check_config_project_type",
    "check_config_required_fields",
    "check_config_syntax",
    "run_config_checks",
}


def __getattr__(name: str):  # noqa: N807
    """Lazy import of config check functions from doctor module."""
    if name in _DOCTOR_NAMES:
        from elspais.commands import doctor  # noqa: E402

        return getattr(doctor, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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
        findings = [
            HealthFinding(
                message=f"Duplicate ID {req_id} in {', '.join(files)}",
                file_path=files[0],
                node_id=req_id,
            )
            for req_id, files in duplicates.items()
        ]
        return HealthCheck(
            name="spec.no_duplicates",
            passed=False,
            message=f"Found {len(duplicates)} duplicate requirement IDs",
            category="spec",
            details={"duplicates": duplicates},
            findings=findings,
        )

    return HealthCheck(
        name="spec.no_duplicates",
        passed=True,
        message="No duplicate requirement IDs",
        category="spec",
    )


def check_spec_implements_resolve(
    graph: TraceGraph, resolver: IdResolver | None = None
) -> HealthCheck:
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
                split = resolver.split_assertion_ref(ref) if resolver else None
                if split is None and "-" in ref:
                    parts = ref.rsplit("-", 1)
                    if len(parts) == 2:
                        split = (parts[0], parts[1])
                if split is not None:
                    parent = graph.find_by_id(split[0])
                    if parent is not None:
                        continue  # Assertion reference is valid
                unresolved.append({"from": node.id, "to": ref})

    if unresolved:
        findings = [
            HealthFinding(
                message=f"Unresolved: {u['from']} -> {u['to']}",
                node_id=u["from"],
                related=[u["to"]],
            )
            for u in unresolved
        ]
        return HealthCheck(
            name="spec.implements_resolve",
            passed=False,
            message=f"{len(unresolved)} unresolved Implements references",
            category="spec",
            severity="warning",
            details={"unresolved": unresolved[:10]},
            findings=findings,
        )

    return HealthCheck(
        name="spec.implements_resolve",
        passed=True,
        message="All Implements references resolve",
        category="spec",
    )


def check_spec_refines_resolve(
    graph: TraceGraph, resolver: IdResolver | None = None
) -> HealthCheck:
    """Check that all Refines references resolve to valid requirements."""
    from elspais.graph import NodeKind

    unresolved = []

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        refines = node.get_field("refines", [])
        for ref in refines:
            target = graph.find_by_id(ref)
            if target is None:
                # Check assertion reference
                split = resolver.split_assertion_ref(ref) if resolver else None
                if split is None and "-" in ref:
                    parts = ref.rsplit("-", 1)
                    if len(parts) == 2:
                        split = (parts[0], parts[1])
                if split is not None:
                    parent = graph.find_by_id(split[0])
                    if parent is not None:
                        continue
                unresolved.append({"from": node.id, "to": ref})

    if unresolved:
        findings = [
            HealthFinding(
                message=f"Unresolved: {u['from']} -> {u['to']}",
                node_id=u["from"],
                related=[u["to"]],
            )
            for u in unresolved
        ]
        return HealthCheck(
            name="spec.refines_resolve",
            passed=False,
            message=f"{len(unresolved)} unresolved Refines references",
            category="spec",
            severity="warning",
            details={"unresolved": unresolved[:10]},
            findings=findings,
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
    non_level_keys = {
        "allow_circular",
        "allow_orphans",
        "allow_structural_orphans",
        "cross_repo_implements",
    }
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
    types = config.get("id-patterns.types", {})
    strict_hierarchy = config.get("validation.strict_hierarchy", False)

    # Parse hierarchy rules
    allowed_parents_map = _parse_hierarchy_rules(hierarchy)

    # Build level lookup from id-patterns types
    # Note: level_lookup reserved for future strict hierarchy validation
    _ = {k: k for k in types}

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
        findings = [
            HealthFinding(
                message=(
                    f"{v['child']} ({v['child_level']}) -> " f"{v['parent']} ({v['parent_level']})"
                ),
                node_id=v["child"],
                related=[v["parent"]],
            )
            for v in violations
        ]
        # Severity controlled by validation.strict_hierarchy config
        if strict_hierarchy:
            return HealthCheck(
                name="spec.hierarchy_levels",
                passed=False,
                message=f"{len(violations)} hierarchy level violations",
                category="spec",
                severity="warning",
                details={"violations": violations[:10]},
                findings=findings,
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
                findings=findings,
            )

    return HealthCheck(
        name="spec.hierarchy_levels",
        passed=True,
        message="All requirements follow hierarchy rules",
        category="spec",
    )


def check_structural_orphans(
    graph: TraceGraph, allow_structural_orphans: bool = False
) -> HealthCheck:
    """Check for nodes without a FILE ancestor (build pipeline bugs)."""
    if allow_structural_orphans:
        return HealthCheck(
            name="spec.structural_orphans",
            passed=True,
            message="Structural orphan check skipped (allow_structural_orphans=true)",
            category="spec",
        )

    orphans_by_kind: dict[str, list[dict]] = {}
    for node in graph.iter_structural_orphans():
        kind_name = node.kind.value
        if kind_name not in orphans_by_kind:
            orphans_by_kind[kind_name] = []
        entry: dict = {"id": node.id, "kind": kind_name}
        if node.level:
            entry["level"] = node.level
        orphans_by_kind[kind_name].append(entry)

    total = sum(len(v) for v in orphans_by_kind.values())
    if total:
        summary_parts = [f"{len(v)} {k}" for k, v in sorted(orphans_by_kind.items())]
        findings = [
            HealthFinding(
                message=f"Structural orphan: {e['id']} ({e['kind']})",
                node_id=e["id"],
            )
            for entries in orphans_by_kind.values()
            for e in entries
        ]
        return HealthCheck(
            name="spec.structural_orphans",
            passed=False,
            message=f"{total} structural orphans ({', '.join(summary_parts)})",
            category="spec",
            severity="error",
            details={"by_kind": {k: v[:10] for k, v in orphans_by_kind.items()}, "total": total},
            findings=findings,
        )

    return HealthCheck(
        name="spec.structural_orphans",
        passed=True,
        message="No structural orphans",
        category="spec",
    )


def check_broken_references(graph: TraceGraph) -> HealthCheck:
    """Check for edges targeting non-existent nodes."""
    broken = graph.broken_references()

    if broken:
        findings = [
            HealthFinding(
                message=f"Broken reference: {br.source_id} -> {br.target_id} ({br.edge_kind})",
                node_id=br.source_id,
            )
            for br in broken
        ]
        return HealthCheck(
            name="spec.broken_references",
            passed=False,
            message=f"{len(broken)} broken references",
            category="spec",
            severity="warning",
            details={
                "count": len(broken),
                "references": [
                    {"source": br.source_id, "target": br.target_id, "kind": br.edge_kind}
                    for br in broken[:20]
                ],
            },
            findings=findings,
        )

    return HealthCheck(
        name="spec.broken_references",
        passed=True,
        message="No broken references",
        category="spec",
    )


def check_spec_format_rules(
    graph: TraceGraph, config: ConfigLoader, resolver: IdResolver | None = None
) -> HealthCheck:
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
        violations = validate_requirement_format(node, rules, resolver=resolver)
        all_violations.extend(violations)

    errors = [v for v in all_violations if v.severity == "error"]
    warnings = [v for v in all_violations if v.severity == "warning"]

    all_findings = [
        HealthFinding(
            message=f"{v.rule}: {v.message}",
            node_id=v.node_id,
        )
        for v in all_violations
    ]

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
            findings=all_findings,
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
            findings=all_findings,
        )

    return HealthCheck(
        name="spec.format_rules",
        passed=True,
        message=f"{req_count} requirements pass all format rules",
        category="spec",
    )


# Implements: REQ-p00004
def check_spec_hash_integrity(graph: TraceGraph) -> HealthCheck:
    """Check that stored requirement hashes match computed hashes."""
    from elspais.commands.validate import compute_hash_for_node
    from elspais.graph import NodeKind

    mismatches = []
    findings: list[HealthFinding] = []
    checked = 0

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        stored = node.hash
        if not stored:
            continue
        checked += 1
        computed = compute_hash_for_node(node, graph.hash_mode)
        if computed and stored != computed:
            mismatches.append({"id": node.id, "stored": stored, "computed": computed})
            # Flag requirements that Satisfy this template for review
            # Instance clones have incoming INSTANCE edges from template
            from elspais.graph.relations import EdgeKind

            for edge in node.iter_incoming_edges():
                if edge.kind == EdgeKind.INSTANCE:
                    # edge.source is the clone, find the declaring req
                    # by looking for the clone's parent with SATISFIES edge
                    clone = edge.source
                    for parent in clone.iter_parents():
                        for parent_edge in parent.iter_outgoing_edges():
                            if (
                                parent_edge.kind == EdgeKind.SATISFIES
                                and parent_edge.target is clone
                            ):
                                findings.append(
                                    HealthFinding(
                                        message=(
                                            f"Template {node.id} content changed;"
                                            f" review {parent.id}"
                                            f" (Satisfies: {node.id})"
                                        ),
                                        node_id=parent.id,
                                        related=[node.id],
                                    )
                                )

    if not checked:
        return HealthCheck(
            name="spec.hash_integrity",
            passed=True,
            message="No requirements with hashes to check",
            category="spec",
            severity="info",
        )

    if mismatches:
        ids = [m["id"] for m in mismatches]
        return HealthCheck(
            name="spec.hash_integrity",
            passed=False,
            message=(
                f"{len(mismatches)} requirement(s) have stale hashes: "
                f"{', '.join(ids[:5])}" + (f" (+{len(ids) - 5} more)" if len(ids) > 5 else "")
            ),
            category="spec",
            severity="warning",
            details={"mismatches": mismatches, "checked": checked},
            findings=findings,
        )

    return HealthCheck(
        name="spec.hash_integrity",
        passed=True,
        message=f"All {checked} requirement hashes are up to date",
        category="spec",
    )


def check_spec_changelog_present(graph: TraceGraph, config: ConfigLoader) -> HealthCheck:
    """Check that all Active requirements have at least one changelog entry."""
    from elspais.graph import NodeKind

    require_present = config.get("changelog.require_present", False)
    if not require_present:
        return HealthCheck(
            name="spec.changelog_present",
            passed=True,
            message="Changelog presence check disabled",
            category="spec",
            severity="info",
        )

    missing = []
    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if (node.status or "").lower() != "active":
            continue
        changelog = node.get_field("changelog", [])
        if not changelog:
            missing.append(node.id)

    if missing:
        findings = [
            HealthFinding(
                message=f"Active requirement {req_id} has no changelog entry",
                node_id=req_id,
            )
            for req_id in missing
        ]
        return HealthCheck(
            name="spec.changelog_present",
            passed=False,
            message=(
                f"{len(missing)} Active requirement(s) missing changelog"
                f" entries: {', '.join(missing[:5])}"
                + (f" ... and {len(missing) - 5} more" if len(missing) > 5 else "")
            ),
            category="spec",
            details={"missing": missing},
            findings=findings,
        )

    return HealthCheck(
        name="spec.changelog_present",
        passed=True,
        message="All Active requirements have changelog entries",
        category="spec",
    )


def check_spec_changelog_current(graph: TraceGraph, config: ConfigLoader) -> HealthCheck:
    """Check that Active requirements' changelog hashes match stored hashes."""
    from elspais.graph import NodeKind

    changelog_enforce = config.get("changelog.enforce", True)
    if not changelog_enforce:
        return HealthCheck(
            name="spec.changelog_current",
            passed=True,
            message="Changelog enforcement disabled",
            category="spec",
            severity="info",
        )

    mismatches = []

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if (node.status or "").lower() != "active":
            continue
        changelog = node.get_field("changelog", [])
        if not changelog:
            continue
        # Most recent entry is first in the list
        latest_hash = changelog[0].get("hash", "")
        stored_hash = node.hash or ""
        if latest_hash and stored_hash and latest_hash != stored_hash:
            mismatches.append(
                {
                    "id": node.id,
                    "stored": stored_hash,
                    "changelog_hash": latest_hash,
                }
            )

    if mismatches:
        ids = [m["id"] for m in mismatches]
        return HealthCheck(
            name="spec.changelog_current",
            passed=False,
            message=(
                f"{len(mismatches)} Active requirement(s) have stale"
                f" changelog entries: {', '.join(ids[:5])}"
            ),
            category="spec",
            severity="error",
            details={"mismatches": mismatches},
        )

    return HealthCheck(
        name="spec.changelog_current",
        passed=True,
        message="All Active requirement changelog entries are current",
        category="spec",
    )


def check_spec_changelog_format(graph: TraceGraph, config: ConfigLoader) -> HealthCheck:
    """Validate changelog entry fields per config requirements."""
    from elspais.graph import NodeKind

    changelog_enforce = config.get("changelog.enforce", True)
    if not changelog_enforce:
        return HealthCheck(
            name="spec.changelog_format",
            passed=True,
            message="Changelog enforcement disabled",
            category="spec",
            severity="info",
        )

    require_reason = config.get("changelog.require_reason", True)
    require_author_name = config.get("changelog.require_author_name", True)
    require_author_id = config.get("changelog.require_author_id", True)
    require_change_order = config.get("changelog.require_change_order", False)

    violations = []

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if (node.status or "").lower() != "active":
            continue
        changelog = node.get_field("changelog", [])
        for entry in changelog:
            missing = []
            if require_reason and (not entry.get("reason") or entry["reason"] == "-"):
                missing.append("reason")
            if require_author_name and (
                not entry.get("author_name") or entry["author_name"] == "-"
            ):
                missing.append("author_name")
            if require_author_id and (not entry.get("author_id") or entry["author_id"] == "-"):
                missing.append("author_id")
            if require_change_order and (
                not entry.get("change_order") or entry["change_order"] == "-"
            ):
                missing.append("change_order")
            if missing:
                violations.append(
                    {
                        "id": node.id,
                        "entry_date": entry.get("date", "?"),
                        "missing_fields": missing,
                    }
                )

    if violations:
        return HealthCheck(
            name="spec.changelog_format",
            passed=False,
            message=(f"{len(violations)} changelog entry/entries" f" missing required fields"),
            category="spec",
            severity="error",
            details={"violations": violations[:10]},
        )

    return HealthCheck(
        name="spec.changelog_format",
        passed=True,
        message="All changelog entries have required fields",
        category="spec",
    )


def check_spec_index_current(
    graph: TraceGraph,
    spec_dirs: list[Path],
) -> HealthCheck:
    """Check that INDEX.md is up to date with current requirements."""
    import re

    from elspais.graph import NodeKind

    # Find INDEX.md
    index_path = None
    for spec_dir in spec_dirs:
        candidate = spec_dir / "INDEX.md"
        if candidate.exists():
            index_path = candidate
            break

    if not index_path:
        return HealthCheck(
            name="spec.index_current",
            passed=True,
            message="No INDEX.md found (run 'elspais index regenerate' to create one)",
            category="spec",
            severity="info",
        )

    content = index_path.read_text()
    index_req_ids = set(re.findall(r"REQ-[a-z0-9-]+", content, re.IGNORECASE))
    index_jny_ids = set(re.findall(r"JNY-[A-Za-z0-9-]+", content))

    graph_req_ids = {n.id for n in graph.nodes_by_kind(NodeKind.REQUIREMENT)}
    graph_jny_ids = {n.id for n in graph.nodes_by_kind(NodeKind.USER_JOURNEY)}

    missing_reqs = graph_req_ids - index_req_ids
    extra_reqs = index_req_ids - graph_req_ids
    missing_jnys = graph_jny_ids - index_jny_ids
    extra_jnys = index_jny_ids - graph_jny_ids

    issues = []
    if missing_reqs:
        issues.append(f"{len(missing_reqs)} missing requirement(s)")
    if extra_reqs:
        issues.append(f"{len(extra_reqs)} extra requirement(s)")
    if missing_jnys:
        issues.append(f"{len(missing_jnys)} missing journey(s)")
    if extra_jnys:
        issues.append(f"{len(extra_jnys)} extra journey(s)")

    if issues:
        return HealthCheck(
            name="spec.index_current",
            passed=False,
            message=f"INDEX.md is stale: {', '.join(issues)}",
            category="spec",
            severity="warning",
            details={
                "missing_reqs": sorted(missing_reqs),
                "extra_reqs": sorted(extra_reqs),
                "missing_jnys": sorted(missing_jnys),
                "extra_jnys": sorted(extra_jnys),
            },
        )

    total = len(graph_req_ids) + len(graph_jny_ids)
    return HealthCheck(
        name="spec.index_current",
        passed=True,
        message=f"INDEX.md is up to date ({total} entries)",
        category="spec",
    )


def run_spec_checks(
    graph: TraceGraph,
    config: ConfigLoader,
    spec_dirs: list[Path] | None = None,
) -> list[HealthCheck]:
    """Run all spec file health checks."""
    from elspais.utilities.patterns import build_resolver

    resolver = build_resolver(config._data)
    checks = [
        check_spec_files_parseable(graph),
        check_spec_no_duplicates(graph),
        check_spec_implements_resolve(graph, resolver=resolver),
        check_spec_refines_resolve(graph, resolver=resolver),
        check_spec_hierarchy_levels(graph, config),
        check_structural_orphans(
            graph,
            allow_structural_orphans=config.get(
                "rules.hierarchy.allow_structural_orphans",
                config.get("rules.hierarchy.allow_orphans", False),
            ),
        ),
        check_broken_references(graph),
        check_spec_format_rules(graph, config, resolver=resolver),
        check_spec_hash_integrity(graph),
        check_spec_changelog_present(graph, config),
        check_spec_changelog_current(graph, config),
        check_spec_changelog_format(graph, config),
    ]
    if spec_dirs:
        checks.append(check_spec_index_current(graph, spec_dirs))
    return checks


# =============================================================================
# Code Checks
# =============================================================================


def _resolve_exclude_status(
    args: argparse.Namespace,
    config: dict[str, Any] | None = None,
) -> set[str]:
    """Compute the set of statuses to exclude from coverage.

    If --status is provided, include only those statuses (case-insensitive).
    Otherwise, use status_roles config to determine exclusions.
    """
    from elspais.config import get_status_roles

    roles = get_status_roles(config or {})
    include_raw: list[str] | None = getattr(args, "status", None)
    if not include_raw:
        return roles.coverage_excluded_statuses()
    # --status flag: include only listed statuses, exclude all others
    included = {s.title() for s in include_raw}
    all_known = roles.coverage_excluded_statuses() | set(roles._original_case.values())
    return all_known - included


def _excluded_note(
    graph: TraceGraph,
    exclude_status: set[str] | None = None,
    config: dict[str, Any] | None = None,
) -> str:
    """Build a note about excluded requirements."""
    from elspais.graph import NodeKind

    if exclude_status is None:
        from elspais.config import get_status_roles

        exclude_status = get_status_roles(config or {}).coverage_excluded_statuses()
    counts: dict[str, int] = {}
    for n in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if n.status in exclude_status:
            counts[n.status] = counts.get(n.status, 0) + 1
    if not counts:
        return ""
    parts = [f"{v} {k.lower()}" for k, v in sorted(counts.items())]
    return f" [{', '.join(parts)} excluded]"


def check_code_coverage(
    graph: TraceGraph,
    exclude_status: set[str] | None = None,
    config: dict[str, Any] | None = None,
) -> HealthCheck:
    """Check code coverage statistics."""
    from elspais.graph import NodeKind
    from elspais.graph.annotators import count_with_code_refs

    if exclude_status is None:
        from elspais.config import get_status_roles

        exclude_status = get_status_roles(config or {}).coverage_excluded_statuses()
    code_count = sum(1 for _ in graph.nodes_by_kind(NodeKind.CODE))
    coverage = count_with_code_refs(graph, exclude_status=exclude_status)
    note = _excluded_note(graph, exclude_status)

    return HealthCheck(
        name="code.coverage",
        passed=True,  # Informational only
        message=(
            f"{coverage['with_code_refs']}/{coverage['total_requirements']} requirements "
            f"have code references ({coverage['coverage_percent']}%){note}"
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


def check_unlinked_code(graph: TraceGraph) -> HealthCheck:
    """Check for CODE nodes not linked to any requirement."""
    from elspais.graph import NodeKind

    unlinked = []
    for node in graph.iter_unlinked(NodeKind.CODE):
        file_n = node.file_node()
        unlinked.append(
            {
                "id": node.id,
                "file": file_n.get_field("relative_path") if file_n else "unknown",
                "line": node.get_field("parse_line"),
            }
        )

    if unlinked:
        findings = [
            HealthFinding(
                message=f"Unlinked code: {u['id']}",
                file_path=u["file"],
                line=u["line"],
                node_id=u["id"],
            )
            for u in unlinked
        ]
        return HealthCheck(
            name="code.unlinked",
            passed=False,
            message=f"{len(unlinked)} code references not linked to any requirement",
            category="code",
            severity="info",
            details={"count": len(unlinked), "unlinked": [u["id"] for u in unlinked[:20]]},
            findings=findings,
        )

    return HealthCheck(
        name="code.unlinked",
        passed=True,
        message="All code references linked to requirements",
        category="code",
    )


def run_code_checks(graph: TraceGraph, exclude_status: set[str] | None = None) -> list[HealthCheck]:
    """Run all code reference health checks."""
    return [
        check_code_coverage(graph, exclude_status=exclude_status),
        check_unlinked_code(graph),
    ]


# =============================================================================
# Test Checks
# =============================================================================


def _read_run_meta(config: dict | None) -> dict:
    """Read test-run metadata sidecar (deselected counts, runner info).

    Returns a dict with at least {"deselected_count": 0, "runner": ""}.
    The sidecar JSON format is test-runner agnostic — any runner can produce it.
    """
    import json
    from pathlib import Path

    defaults = {"deselected_count": 0, "runner": ""}
    meta_file = (config or {}).get("testing", {}).get("run_meta_file", "")
    if not meta_file:
        return defaults
    meta_path = Path(meta_file)
    if not meta_path.exists():
        return defaults
    try:
        data = json.loads(meta_path.read_text())
        return {
            "deselected_count": data.get("deselected_count", 0),
            "runner": data.get("runner", ""),
        }
    except (json.JSONDecodeError, OSError):
        return defaults


def check_test_results(graph: TraceGraph, config: dict | None = None) -> HealthCheck:
    """Check test result status from JUnit/pytest output."""
    from elspais.graph import NodeKind

    result_nodes = list(graph.nodes_by_kind(NodeKind.TEST_RESULT))
    run_meta = _read_run_meta(config)
    deselected = run_meta["deselected_count"]

    if not result_nodes:
        # Check if result scanning is actually configured
        result_files = (config or {}).get("testing", {}).get("result_files", [])
        if not result_files:
            message = "No result files configured"
        else:
            message = (
                f"No test results found ({len(result_files)} result path(s) configured but empty)"
            )
        return HealthCheck(
            name="tests.results",
            passed=True,
            message=message,
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
    deselected_suffix = f", {deselected} deselected" if deselected else ""

    if failed > 0:
        findings = [
            HealthFinding(
                message=f"Failed: {node.get_label() or node.id}",
                node_id=node.id,
                file_path=node.get_field("source_file", None),
            )
            for node in result_nodes
            if node.get_field("status", "unknown") == "failed"
        ]
        return HealthCheck(
            name="tests.results",
            passed=False,
            message=(
                f"Test failures: {passed} passed, {failed} failed, "
                f"{skipped} skipped{deselected_suffix} ({pass_rate:.1f}% pass rate)"
            ),
            category="tests",
            severity="warning",
            details={
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "deselected": deselected,
                "pass_rate": round(pass_rate, 1),
            },
            findings=findings,
        )

    return HealthCheck(
        name="tests.results",
        passed=True,
        message=f"All tests passing: {passed} passed, {skipped} skipped{deselected_suffix}",
        category="tests",
        details={
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "deselected": deselected,
            "pass_rate": round(pass_rate, 1),
        },
    )


def check_test_coverage(
    graph: TraceGraph,
    exclude_status: set[str] | None = None,
    config: dict[str, Any] | None = None,
) -> HealthCheck:
    """Check test coverage statistics."""
    from elspais.graph import NodeKind

    if exclude_status is None:
        from elspais.config import get_status_roles

        exclude_status = get_status_roles(config or {}).coverage_excluded_statuses()
    test_count = sum(1 for _ in graph.nodes_by_kind(NodeKind.TEST))
    req_count = sum(
        1 for n in graph.nodes_by_kind(NodeKind.REQUIREMENT) if n.status not in exclude_status
    )

    # Count requirements with at least one TEST child
    covered_reqs = set()
    for node in graph.nodes_by_kind(NodeKind.TEST):
        for parent in node.iter_parents():
            if parent.kind == NodeKind.REQUIREMENT and parent.status not in exclude_status:
                covered_reqs.add(parent.id)
            elif parent.kind == NodeKind.ASSERTION:
                for grandparent in parent.iter_parents():
                    if (
                        grandparent.kind == NodeKind.REQUIREMENT
                        and grandparent.status not in exclude_status
                    ):
                        covered_reqs.add(grandparent.id)

    coverage_pct = (len(covered_reqs) / req_count * 100) if req_count > 0 else 0
    note = _excluded_note(graph, exclude_status)

    return HealthCheck(
        name="tests.coverage",
        passed=True,  # Informational only
        message=(
            f"{len(covered_reqs)}/{req_count} requirements "
            f"have test references ({coverage_pct:.1f}%){note}"
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


def check_unlinked_tests(graph: TraceGraph) -> HealthCheck:
    """Check for TEST nodes not linked to any requirement."""
    from elspais.graph import NodeKind

    unlinked = []
    for node in graph.iter_unlinked(NodeKind.TEST):
        file_n = node.file_node()
        unlinked.append(
            {
                "id": node.id,
                "file": file_n.get_field("relative_path") if file_n else "unknown",
                "line": node.get_field("parse_line"),
            }
        )

    if unlinked:
        findings = [
            HealthFinding(
                message=f"Unlinked test: {u['id']}",
                file_path=u["file"],
                line=u["line"],
                node_id=u["id"],
            )
            for u in unlinked
        ]
        return HealthCheck(
            name="tests.unlinked",
            passed=False,
            message=f"{len(unlinked)} tests not linked to any requirement",
            category="tests",
            severity="info",
            details={"count": len(unlinked), "unlinked": [u["id"] for u in unlinked[:20]]},
            findings=findings,
        )

    return HealthCheck(
        name="tests.unlinked",
        passed=True,
        message="All tests linked to requirements",
        category="tests",
    )


def run_test_checks(
    graph: TraceGraph, exclude_status: set[str] | None = None, config: dict | None = None
) -> list[HealthCheck]:
    """Run all test file health checks."""
    return [
        check_test_results(graph, config=config),
        check_test_coverage(graph, exclude_status=exclude_status),
        check_unlinked_tests(graph),
    ]


# =============================================================================
# Composable Section API
# =============================================================================


# Implements: REQ-d00085-A
def render_section(
    graph: TraceGraph | None,
    config: ConfigLoader | None,
    args: argparse.Namespace,
) -> tuple[str, int]:
    """Render health as a composed report section.

    Returns (formatted_output, exit_code).
    """
    report = HealthReport()
    config_path = getattr(args, "config", None)

    if config:
        from elspais.commands.doctor import run_config_checks as _run_config_checks

        for check in _run_config_checks(config_path, config, Path.cwd()):
            report.add(check)

    if graph and config:
        from elspais.config import get_spec_directories

        spec_dir = getattr(args, "spec_dir", None)
        resolved_spec_dirs = get_spec_directories(spec_dir, config.get_raw())
        for check in run_spec_checks(graph, config, spec_dirs=resolved_spec_dirs):
            report.add(check)
    if graph:
        raw_config = config.get_raw() if config else {}
        exclude_status = _resolve_exclude_status(args, config=raw_config)
        for check in run_code_checks(graph, exclude_status=exclude_status):
            report.add(check)
        for check in run_test_checks(graph, exclude_status=exclude_status, config=raw_config):
            report.add(check)

    output = _format_report(report, args)
    lenient = getattr(args, "lenient", False)
    healthy = report.is_healthy_lenient if lenient else report.is_healthy
    return output, 0 if healthy else 1


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
            getattr(args, "spec_only", False),
            getattr(args, "code_only", False),
            getattr(args, "tests_only", False),
        ]
    )

    run_config = run_all
    run_spec = run_all or getattr(args, "spec_only", False)
    run_code = run_all or getattr(args, "code_only", False)
    run_tests = run_all or getattr(args, "tests_only", False)

    # Config checks can run without building the graph
    config = None
    if run_config:
        try:
            from elspais.commands.doctor import run_config_checks as _run_config_checks

            config_dict = get_config(config_path, start_path=start_path)
            config = ConfigLoader.from_dict(config_dict)
            for check in _run_config_checks(config_path, config, start_path):
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
            canonical_root = getattr(args, "canonical_root", None)
            graph = build_graph(
                spec_dirs=[spec_dir] if spec_dir else None,
                config_path=config_path,
                canonical_root=canonical_root,
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
        from elspais.config import get_spec_directories

        config_dict = config.get_raw()
        resolved_spec_dirs = get_spec_directories(spec_dir, config_dict)
        for check in run_spec_checks(graph, config, spec_dirs=resolved_spec_dirs):
            report.add(check)

    # Code checks
    raw_config = config.get_raw() if config else {}
    exclude_status = _resolve_exclude_status(args, config=raw_config)
    if run_code and graph:
        for check in run_code_checks(graph, exclude_status=exclude_status):
            report.add(check)

    # Test checks
    if run_tests and graph:
        for check in run_test_checks(graph, exclude_status=exclude_status, config=raw_config):
            report.add(check)

    return _output_report(report, args)


def _format_report(report: HealthReport, args: argparse.Namespace) -> str:
    """Format the health report as a string."""
    import io
    from contextlib import redirect_stdout

    fmt = getattr(args, "format", "text") or "text"
    lenient = getattr(args, "lenient", False)
    quiet = getattr(args, "quiet", False)
    verbose = getattr(args, "verbose", False)
    include_passing = getattr(args, "include_passing_details", False)

    if fmt == "json":
        return json.dumps(report.to_dict(lenient=lenient), indent=2)
    elif fmt == "markdown":
        return _render_markdown(report, include_passing_details=include_passing)
    elif fmt == "junit":
        return _render_junit(report, include_passing_details=include_passing)
    elif fmt == "sarif":
        return _render_sarif(report)
    else:
        buf = io.StringIO()
        with redirect_stdout(buf):
            if quiet:
                _print_quiet_report(report)
            else:
                _print_text_report(
                    report,
                    verbose=verbose,
                    include_passing_details=include_passing,
                )
        return buf.getvalue().rstrip("\n")


def _output_report(report: HealthReport, args: argparse.Namespace) -> int:
    """Output the health report in the requested format."""
    print(_format_report(report, args))

    lenient = getattr(args, "lenient", False)
    healthy = report.is_healthy_lenient if lenient else report.is_healthy
    return 0 if healthy else 1


def _print_text_report(
    report: HealthReport,
    verbose: bool = False,
    include_passing_details: bool = False,
) -> None:
    """Print human-readable health report."""
    categories = ["config", "spec", "code", "tests"]

    for category in categories:
        checks = list(report.iter_by_category(category))
        if not checks:
            continue

        # Category header
        passed = sum(1 for c in checks if c.passed)
        total = len(checks)
        has_errors = any(not c.passed and c.severity == "error" for c in checks)
        has_warnings = any(not c.passed and c.severity == "warning" for c in checks)
        if passed == total:
            status = "✓"
        elif has_errors:
            status = "✗"
        else:
            status = "⚠"
        warn_suffix = ""
        if has_warnings and not has_errors:
            warn_count = sum(1 for c in checks if not c.passed and c.severity == "warning")
            warn_suffix = f", {warn_count} warnings"
        print(f"\n{status} {category.upper()} ({passed}/{total} checks passed{warn_suffix})")
        print("-" * 40)

        for check in checks:
            if check.passed:
                icon = "✓"
            elif check.severity == "warning":
                icon = "⚠"
            else:
                icon = "✗"

            print(f"  {icon} {check.name}: {check.message}")

            # Show details in verbose mode (skip passing unless include flag set)
            show_details = verbose and check.details
            if show_details and check.passed and not include_passing_details:
                show_details = False
            if show_details:
                for key, value in check.details.items():
                    if isinstance(value, list) and len(value) > 3:
                        print(f"      {key}: {value[:3]} ... ({len(value)} total)")
                    else:
                        print(f"      {key}: {value}")

    # Summary
    print()
    print("=" * 40)
    _print_summary_line(report)
    print("=" * 40)


def _print_summary_line(report: HealthReport) -> None:
    """Print a single summary line."""
    total = report.passed + report.failed + report.warnings
    if report.failed == 0 and report.warnings == 0:
        print(f"HEALTHY: {total}/{total} checks passed")
    elif report.failed == 0:
        print(f"{report.passed}/{total} checks passed," f" {report.warnings} warnings")
    else:
        print(f"UNHEALTHY: {report.failed} errors," f" {report.warnings} warnings")


def _print_quiet_report(report: HealthReport) -> None:
    """Print summary line only (for -q/--quiet)."""
    _print_summary_line(report)


# Implements: REQ-d00085-E
def _render_markdown(
    report: HealthReport,
    include_passing_details: bool = False,
) -> str:
    """Render health report as markdown."""
    lines = []
    lines.append("# Health Report")
    lines.append("")

    categories = ["config", "spec", "code", "tests"]
    for category in categories:
        checks = list(report.iter_by_category(category))
        if not checks:
            continue

        passed = sum(1 for c in checks if c.passed)
        total = len(checks)
        has_errors = any(not c.passed and c.severity == "error" for c in checks)
        if passed == total:
            status = "pass"
        elif has_errors:
            status = "FAIL"
        else:
            status = "WARN"
        lines.append(f"## {category.upper()} ({passed}/{total} {status})")
        lines.append("")
        lines.append("| Check | Status | Message |")
        lines.append("|-------|--------|---------|")
        for check in checks:
            if check.passed:
                icon = "PASS"
            elif check.severity == "warning":
                icon = "WARN"
            else:
                icon = "FAIL"
            lines.append(f"| {check.name} | {icon} | {check.message} |")

            # Include findings detail for passing checks if requested
            if check.passed and include_passing_details and check.findings:
                lines.append("")
                lines.append("<details>")
                lines.append(f"<summary>{check.name} details</summary>")
                lines.append("")
                for finding in check.findings:
                    loc = ""
                    if finding.file_path:
                        loc = f"{finding.file_path}"
                        if finding.line is not None:
                            loc += f":{finding.line}"
                        loc += ": "
                    lines.append(f"- {loc}{finding.message}")
                lines.append("")
                lines.append("</details>")
        lines.append("")

    # Summary
    total = report.passed + report.failed + report.warnings
    if report.failed == 0 and report.warnings == 0:
        lines.append(f"**HEALTHY**: {total}/{total} checks passed")
    elif report.failed == 0:
        lines.append(f"**{report.passed}/{total}** checks passed," f" {report.warnings} warnings")
    else:
        lines.append(f"**UNHEALTHY**: {report.failed} errors," f" {report.warnings} warnings")

    return "\n".join(lines)


# Implements: REQ-d00085-H
def _render_junit(
    report: HealthReport,
    include_passing_details: bool = False,
) -> str:
    """Render health report as JUnit XML.

    Maps categories to <testsuite> elements, checks to <testcase> elements.
    Failed checks with severity=error become <failure>, severity=warning become
    <system-err> with WARNING prefix, and severity=info become <system-out>.
    """
    import xml.etree.ElementTree as ET

    testsuites = ET.Element("testsuites")
    categories = ["config", "spec", "code", "tests"]

    for category in categories:
        checks = list(report.iter_by_category(category))
        if not checks:
            continue

        failures = sum(1 for c in checks if not c.passed and c.severity == "error")
        suite = ET.SubElement(
            testsuites,
            "testsuite",
            name=category,
            tests=str(len(checks)),
            failures=str(failures),
            errors="0",
        )

        for check in checks:
            tc = ET.SubElement(
                suite,
                "testcase",
                name=check.name,
                classname=f"elspais.health.{category}",
            )

            if check.severity == "info":
                sys_out = ET.SubElement(tc, "system-out")
                sys_out.text = check.message
            elif not check.passed:
                if check.severity == "error":
                    failure = ET.SubElement(tc, "failure", message=check.message)
                    if check.details:
                        failure.text = _format_details(check.details)
                elif check.severity == "warning":
                    sys_err = ET.SubElement(tc, "system-err")
                    sys_err.text = f"WARNING: {check.message}"
            elif check.passed and include_passing_details and check.findings:
                sys_out = ET.SubElement(tc, "system-out")
                finding_lines = [f.message for f in check.findings]
                sys_out.text = "\n".join(finding_lines)

    return ET.tostring(testsuites, encoding="unicode", xml_declaration=True)


def _format_details(details: dict[str, Any]) -> str:
    """Format check details dict as readable text for XML bodies."""
    parts = []
    for key, value in details.items():
        if isinstance(value, list):
            parts.append(f"{key}: {', '.join(str(v) for v in value)}")
        else:
            parts.append(f"{key}: {value}")
    return "\n".join(parts)


# Implements: REQ-d00085-J
def _render_sarif(report: HealthReport) -> str:
    """Render health report as SARIF v2.1.0 JSON.

    One reportingDescriptor per unique failing check name, one result per
    HealthFinding with physical locations. Passing checks are omitted.
    Coverage stats go in run.properties.
    """
    _SARIF_SEVERITY = {"error": "error", "warning": "warning", "info": "note"}

    rules: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    rule_index_map: dict[str, int] = {}

    for check in report.checks:
        if check.passed:
            continue

        # Register rule if not yet seen
        if check.name not in rule_index_map:
            rule_index_map[check.name] = len(rules)
            rules.append(
                {
                    "id": check.name,
                    "shortDescription": {"text": check.message},
                }
            )

        idx = rule_index_map[check.name]
        level = _SARIF_SEVERITY.get(check.severity, "warning")

        if check.findings:
            for finding in check.findings:
                result: dict[str, Any] = {
                    "ruleId": check.name,
                    "ruleIndex": idx,
                    "level": level,
                    "message": {"text": finding.message},
                }
                if finding.file_path:
                    loc: dict[str, Any] = {
                        "artifactLocation": {"uri": finding.file_path},
                    }
                    if finding.line is not None:
                        loc["region"] = {"startLine": finding.line}
                    result["locations"] = [{"physicalLocation": loc}]
                results.append(result)
        else:
            # Failing check with no findings — emit one result from check message
            results.append(
                {
                    "ruleId": check.name,
                    "ruleIndex": idx,
                    "level": level,
                    "message": {"text": check.message},
                }
            )

    sarif = {
        "$schema": (
            "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/main/"
            "sarif-2.1/schema/sarif-schema-2.1.0.json"
        ),
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "elspais",
                        "rules": rules,
                    },
                },
                "results": results,
                "properties": {
                    "passed": report.passed,
                    "failed": report.failed,
                    "warnings": report.warnings,
                },
            }
        ],
    }

    return json.dumps(sarif, indent=2)
