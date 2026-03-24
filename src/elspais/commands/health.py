# Implements: REQ-d00080-A+B+C+E
# Implements: REQ-d00218-A+B+C
# Implements: REQ-d00219-A+B+C+D
"""
elspais.commands.health - Requirements traceability verification.

Verifies traceability completeness for:
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

from elspais.config.schema import ElspaisConfig
from elspais.config.status_roles import StatusRole

if TYPE_CHECKING:
    from elspais.graph.federated import FederatedGraph
    from elspais.utilities.patterns import IdResolver

_SCHEMA_FIELDS = {f.alias or name for name, f in ElspaisConfig.model_fields.items()} | set(
    ElspaisConfig.model_fields.keys()
)


def _validate_config(config: dict[str, Any]) -> ElspaisConfig:
    """Validate a config dict into ElspaisConfig, stripping non-schema keys."""
    filtered = {k: v for k, v in config.items() if k in _SCHEMA_FIELDS}
    assoc = filtered.get("associates")
    if isinstance(assoc, dict) and "paths" in assoc:
        filtered.pop("associates", None)
    return ElspaisConfig.model_validate(filtered)


# Implements: REQ-d00085-I, REQ-d00204-D
@dataclass
class HealthFinding:
    """Individual finding within a health check, with optional source location."""

    message: str
    file_path: str | None = None
    line: int | None = None
    node_id: str | None = None
    related: list[str] = field(default_factory=list)
    repo: str | None = None
    retired: bool = False

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "message": self.message,
            "file_path": self.file_path,
            "line": self.line,
            "node_id": self.node_id,
            "related": self.related,
            "repo": self.repo,
        }
        if self.retired:
            d["retired"] = True
        return d


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
    def skipped(self) -> int:
        return sum(1 for c in self.checks if c.severity == "info")

    @property
    def passed(self) -> int:
        return sum(1 for c in self.checks if c.passed and c.severity != "info")

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
                "skipped": self.skipped,
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


def check_spec_files_parseable(graph: FederatedGraph) -> HealthCheck:
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


def check_spec_no_duplicates(graph: FederatedGraph) -> HealthCheck:
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
    graph: FederatedGraph, resolver: IdResolver | None = None
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
    graph: FederatedGraph, resolver: IdResolver | None = None
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


# Implements: REQ-d00085-I
def check_spec_needs_rewrite(graph: FederatedGraph) -> HealthCheck:
    """Check for requirements that would change the file on next save.

    A requirement is marked parse_dirty at build time when any condition is
    detected that means the in-memory state differs from the file on disk:
    - duplicate_refs: same REQ ID appears more than once in Implements/Refines
    - stale_hash: stored hash does not match the computed hash
    """
    from elspais.graph import NodeKind

    findings: list[HealthFinding] = []

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if node.get_field("parse_dirty"):
            fn = node.file_node()
            file_path = fn.get_field("relative_path") if fn is not None else None
            reasons = node.get_field("parse_dirty_reasons") or []
            findings.append(
                HealthFinding(
                    message=f"Will be rewritten on next save: {', '.join(reasons)}",
                    node_id=node.id,
                    file_path=file_path,
                    line=node.get_field("parse_line"),
                )
            )

    if findings:
        return HealthCheck(
            name="spec.needs_rewrite",
            passed=False,
            message=f"{len(findings)} requirement(s) will be rewritten on next save",
            category="spec",
            severity="warning",
            details={"count": len(findings)},
            findings=findings,
        )

    return HealthCheck(
        name="spec.needs_rewrite",
        passed=True,
        message="No requirements need rewriting",
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
        if key in non_level_keys or value is None:
            continue
        if isinstance(value, list):
            result[key.lower()] = [v.lower() for v in value]

    return result


def check_spec_hierarchy_levels(graph: FederatedGraph, config: dict[str, Any]) -> HealthCheck:
    """Check that hierarchy levels follow configured rules."""
    from elspais.graph import NodeKind

    typed_config = _validate_config(config)
    levels = typed_config.levels
    strict_hierarchy = typed_config.validation.strict_hierarchy or False

    # Parse hierarchy rules from levels config
    allowed_parents_map = {
        name.lower(): [p.lower() for p in level.implements] for name, level in levels.items()
    }

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
    graph: FederatedGraph, allow_structural_orphans: bool = False
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


# Implements: REQ-d00204-E
def check_broken_references(graph: FederatedGraph, config=None) -> HealthCheck:
    """Check for edges targeting non-existent nodes.

    Distinguishes within-repo broken references (error severity) from
    cross-repo references where the target repo is in error state
    (warning severity with clone assistance info).

    When validation.allow_unresolved_cross_repo is True, broken references
    whose target ID uses a different namespace prefix than the current repo
    are silently suppressed.
    """
    broken = graph.broken_references()

    suppressed_count = 0
    if config is not None:
        _tc = _validate_config(config)
        _allow_unresolved = _tc.validation.allow_unresolved_cross_repo if _tc else False
    else:
        _allow_unresolved = False
    if _allow_unresolved:
        local_broken = [br for br in broken if not br.presumed_foreign]
        suppressed_count = len(broken) - len(local_broken)
        broken = local_broken

    if broken:
        # Identify error-state repos and collect all known node IDs
        error_repos = {entry.name for entry in graph.iter_repos() if entry.graph is None}
        # All node IDs owned by live repos — if a target isn't here and
        # error-state repos exist, it might belong to a missing repo
        owned_ids = set(graph._ownership.keys()) if hasattr(graph, "_ownership") else set()

        within_repo_findings = []
        cross_repo_findings = []

        for br in broken:
            try:
                source_entry = graph.repo_for(br.source_id)
                repo_name = source_entry.name
            except KeyError:
                repo_name = None

            finding = HealthFinding(
                message=f"Broken reference: {br.source_id} -> {br.target_id} ({br.edge_kind})",
                node_id=br.source_id,
                repo=repo_name,
            )

            # Only classify as cross-repo if the target is genuinely
            # unresolvable AND error-state repos exist that might contain it.
            # A target that isn't in any live repo's ownership map could
            # plausibly belong to a missing repo.
            target_in_live_repo = br.target_id in owned_ids
            if error_repos and not target_in_live_repo:
                cross_repo_findings.append(finding)
            else:
                within_repo_findings.append(finding)

        all_findings = within_repo_findings + cross_repo_findings

        # Severity: error if any within-repo broken refs, warning if only cross-repo
        if within_repo_findings:
            severity = "error"
            msg_parts = [f"{len(within_repo_findings)} broken reference(s)"]
            if cross_repo_findings:
                msg_parts.append(
                    f"{len(cross_repo_findings)} possibly due to missing repo(s): "
                    + ", ".join(sorted(error_repos))
                )
            message = "; ".join(msg_parts)
        else:
            severity = "warning"
            message = (
                f"{len(cross_repo_findings)} broken reference(s), "
                f"possibly due to missing repo(s): {', '.join(sorted(error_repos))}"
            )

        return HealthCheck(
            name="spec.broken_references",
            passed=False,
            message=message,
            category="spec",
            severity=severity,
            details={
                "count": len(broken),
                "within_repo": len(within_repo_findings),
                "cross_repo": len(cross_repo_findings),
                "error_repos": sorted(error_repos),
                "references": [
                    {"source": br.source_id, "target": br.target_id, "kind": br.edge_kind}
                    for br in broken[:20]
                ],
            },
            findings=all_findings,
        )

    message = "No broken references"
    if suppressed_count:
        message += f" ({suppressed_count} cross-repo suppressed)"
    return HealthCheck(
        name="spec.broken_references",
        passed=True,
        message=message,
        category="spec",
    )


def check_spec_format_rules(
    graph: FederatedGraph, config: dict[str, Any], resolver: IdResolver | None = None
) -> HealthCheck:
    """Check that requirements comply with configured format rules."""
    from elspais.graph import NodeKind
    from elspais.graph.GraphNode import GraphNode
    from elspais.validation.format import get_format_rules_config, validate_requirement_format

    rules = get_format_rules_config(config)

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
    node_map: dict[str, GraphNode] = {}
    req_count = 0

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        req_count += 1
        node_map[node.id] = node
        violations = validate_requirement_format(node, rules, resolver=resolver)
        all_violations.extend(violations)

    errors = [v for v in all_violations if v.severity == "error"]
    warnings = [v for v in all_violations if v.severity == "warning"]

    all_findings = []
    for v in all_violations:
        vnode = node_map.get(v.node_id)
        fp = None
        ln = None
        repo = None
        if vnode is not None:
            fn = vnode.file_node()
            if fn is not None:
                fp = fn.get_field("relative_path")
                repo = fn.get_field("repo")
            ln = vnode.get_field("parse_line")
        all_findings.append(
            HealthFinding(
                message=f"{v.rule}: {v.message}",
                node_id=v.node_id,
                file_path=fp,
                line=ln,
                repo=repo,
            )
        )

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


# Implements: REQ-d00204
def check_spec_no_assertions(graph: FederatedGraph, config: dict[str, Any]) -> HealthCheck:
    """Flag requirements that have zero assertions (not testable)."""
    from elspais.graph import NodeKind
    from elspais.graph.relations import EdgeKind

    severity = "warning"
    typed = _validate_config(config)
    if typed.rules.format.no_assertions_severity in ("info", "warning", "error"):
        severity = typed.rules.format.no_assertions_severity

    findings: list[HealthFinding] = []
    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        has_assertion = any(
            child.kind == NodeKind.ASSERTION
            for child in node.iter_children(edge_kinds={EdgeKind.STRUCTURES})
        )
        if not has_assertion:
            fn = node.file_node()
            findings.append(
                HealthFinding(
                    message=f"{node.id}: No assertions — not testable",
                    node_id=node.id,
                    file_path=fn.get_field("relative_path") if fn else None,
                    line=node.get_field("parse_line"),
                )
            )

    if findings:
        return HealthCheck(
            name="spec.no_assertions",
            passed=False,
            message=f"{len(findings)} requirement(s) have no assertions (not testable)",
            category="spec",
            severity=severity,
            findings=findings,
        )
    return HealthCheck(
        name="spec.no_assertions",
        passed=True,
        message="All requirements have at least one assertion",
        category="spec",
    )


# Implements: REQ-p00004
def check_spec_hash_integrity(graph: FederatedGraph) -> HealthCheck:
    """Flag Satisfies-linked requirements for review when their template has a stale hash.

    Stale hash detection happens at build time (parse_dirty_reasons contains
    "stale_hash"). This check adds the Satisfies annotation: when a template
    requirement is stale, any requirement that Satisfies it needs review.
    """
    from elspais.graph import NodeKind
    from elspais.graph.relations import EdgeKind

    findings: list[HealthFinding] = []
    mismatches = []

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        reasons = node.get_field("parse_dirty_reasons") or []
        if "stale_hash" not in reasons:
            continue
        stored = node.hash
        mismatches.append({"id": node.id, "stored": stored})
        for edge in node.iter_incoming_edges():
            if edge.kind == EdgeKind.INSTANCE:
                clone = edge.source
                for parent in clone.iter_parents():
                    for parent_edge in parent.iter_outgoing_edges():
                        if parent_edge.kind == EdgeKind.SATISFIES and parent_edge.target is clone:
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
            details={"mismatches": mismatches},
            findings=findings,
        )

    has_satisfies = any(
        edge.kind == EdgeKind.SATISFIES
        for node in graph.nodes_by_kind(NodeKind.REQUIREMENT)
        for edge in node.iter_outgoing_edges()
    )
    message = (
        "All template hashes up to date" if has_satisfies else "No Satisfies: templates in use"
    )
    return HealthCheck(
        name="spec.hash_integrity",
        passed=True,
        message=message,
        category="spec",
        severity="info",
    )


def check_spec_changelog_present(graph: FederatedGraph, config: dict[str, Any]) -> HealthCheck:
    """Check that all Active requirements have at least one changelog entry."""
    from elspais.graph import NodeKind

    typed_config = _validate_config(config)
    require_present = typed_config.changelog.present
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


def check_spec_changelog_current(graph: FederatedGraph, config: dict[str, Any]) -> HealthCheck:
    """Check that Active requirements' changelog hashes match stored hashes."""
    from elspais.graph import NodeKind

    typed_config = _validate_config(config)
    changelog_enforce = typed_config.changelog.hash_current
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


def check_spec_changelog_format(graph: FederatedGraph, config: dict[str, Any]) -> HealthCheck:
    """Validate changelog entry fields per config requirements."""
    from elspais.graph import NodeKind

    typed_config = _validate_config(config)
    changelog_enforce = typed_config.changelog.hash_current
    if not changelog_enforce:
        return HealthCheck(
            name="spec.changelog_format",
            passed=True,
            message="Changelog enforcement disabled",
            category="spec",
            severity="info",
        )

    require_reason = typed_config.changelog.require.reason
    require_author_name = typed_config.changelog.require.author_name
    require_author_id = typed_config.changelog.require.author_id
    require_change_order = typed_config.changelog.require.change_order

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
    graph: FederatedGraph,
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


def _annotate_findings(check: HealthCheck, repo_name: str) -> HealthCheck:
    """Annotate all findings in a HealthCheck with the source repo name."""
    for finding in check.findings:
        finding.repo = repo_name
    return check


def _downgrade_retired_findings(
    checks: list[HealthCheck],
    retired_ids: set[str],
) -> list[HealthCheck]:
    """Downgrade health checks whose failures come only from retired requirements.

    For each failing check, mark findings whose node_id is a retired requirement.
    If ALL findings in a check are retired, downgrade the check to info severity
    so it doesn't count against the health score. The findings are preserved for
    the detailed report.
    """
    for check in checks:
        if check.passed or not check.findings:
            continue

        # Mark individual findings for retired nodes
        has_active = False
        for finding in check.findings:
            if finding.node_id and finding.node_id in retired_ids:
                finding.retired = True
            else:
                has_active = True

        # If all findings are retired, downgrade the entire check
        if not has_active:
            check.passed = True
            check.severity = "info"
            check.message = f"[retired only] {check.message}"

    return checks


# =============================================================================
# Term Checks
# =============================================================================


# Implements: REQ-d00223-A
def check_term_duplicates(
    duplicates: list[tuple],
    severity: str = "error",
) -> HealthCheck:
    """Check for duplicate term definitions."""
    if severity == "off":
        return HealthCheck(
            name="terms.duplicates",
            passed=True,
            message="Duplicate term check skipped (severity=off)",
            category="terms",
            severity="info",
        )

    if not duplicates:
        return HealthCheck(
            name="terms.duplicates",
            passed=True,
            message="No duplicate term definitions",
            category="terms",
            severity=severity,
        )

    findings = []
    for existing, incoming in duplicates:
        findings.append(
            HealthFinding(
                message=(
                    f"Duplicate definition of '{existing.term}': "
                    f"{existing.defined_in}:{existing.defined_at_line} "
                    f"and {incoming.defined_in}:{incoming.defined_at_line}"
                ),
                node_id=existing.defined_in,
                line=existing.defined_at_line,
            )
        )

    return HealthCheck(
        name="terms.duplicates",
        passed=False,
        message=f"{len(duplicates)} duplicate term definition(s)",
        category="terms",
        severity=severity,
        findings=findings,
    )


# Implements: REQ-d00223-B
def check_undefined_terms(
    undefined: list[dict],
    severity: str = "warning",
) -> HealthCheck:
    """Check for *token*/**token** references without a matching definition."""
    if severity == "off":
        return HealthCheck(
            name="terms.undefined",
            passed=True,
            message="Undefined term check skipped (severity=off)",
            category="terms",
            severity="info",
        )

    if not undefined:
        return HealthCheck(
            name="terms.undefined",
            passed=True,
            message="No undefined term references",
            category="terms",
            severity=severity,
        )

    findings = []
    for item in undefined:
        findings.append(
            HealthFinding(
                message=f"Possible undefined term '{item['token']}' in {item['node_id']}",
                node_id=item.get("node_id"),
                line=item.get("line"),
            )
        )

    return HealthCheck(
        name="terms.undefined",
        passed=False,
        message=f"{len(undefined)} possible undefined term(s)",
        category="terms",
        severity=severity,
        findings=findings,
    )


# Implements: REQ-d00223-C
def check_unmarked_usage(
    unmarked: list[dict],
    severity: str = "warning",
) -> HealthCheck:
    """Check for indexed terms used in prose without *...* or **...** markup."""
    if severity == "off":
        return HealthCheck(
            name="terms.unmarked",
            passed=True,
            message="Unmarked usage check skipped (severity=off)",
            category="terms",
            severity="info",
        )

    if not unmarked:
        return HealthCheck(
            name="terms.unmarked",
            passed=True,
            message="No unmarked term usage",
            category="terms",
            severity=severity,
        )

    findings = []
    for item in unmarked:
        findings.append(
            HealthFinding(
                message=f"Unmarked usage of '{item['term']}' in {item['node_id']}",
                node_id=item.get("node_id"),
                line=item.get("line"),
            )
        )

    return HealthCheck(
        name="terms.unmarked",
        passed=False,
        message=f"{len(unmarked)} unmarked term usage(s)",
        category="terms",
        severity=severity,
        findings=findings,
    )


# Implements: REQ-d00204-A, REQ-d00204-B, REQ-d00204-F
def run_spec_checks(
    graph: FederatedGraph,
    config: dict[str, Any],
    spec_dirs: list[Path] | None = None,
) -> list[HealthCheck]:
    """Run all spec file health checks.

    Non-config-sensitive checks run once on the full FederatedGraph.
    Config-sensitive checks run per-repo using each repo's own config,
    with results annotated by repo name.

    Findings for retired requirements (Deprecated, Superseded, Rejected)
    are preserved in the detailed report but do not count as errors
    for health scoring.
    """
    from elspais.config import get_status_roles
    from elspais.graph import NodeKind as NK
    from elspais.graph.federated import FederatedGraph as FG

    # Build the set of retired requirement IDs for post-processing
    roles = get_status_roles(config)
    retired_ids: set[str] = set()
    for node in graph.nodes_by_kind(NK.REQUIREMENT):
        if roles.role_of(node.status) == StatusRole.RETIRED:
            retired_ids.add(node.id)

    # --- Non-config-sensitive checks: run once on full federation ---
    checks: list[HealthCheck] = [
        check_spec_files_parseable(graph),
        check_spec_no_duplicates(graph),
        check_broken_references(graph, config),
        check_spec_hash_integrity(graph),
    ]

    # --- Config-sensitive checks: run per-repo ---
    for entry in graph.iter_repos():
        if entry.graph is None or entry.config is None:
            continue
        from elspais.utilities.patterns import build_resolver

        repo_config = entry.config
        repo_graph = FG.from_single(entry.graph, repo_config, entry.repo_root)
        repo_resolver = build_resolver(repo_config)

        checks.append(
            _annotate_findings(
                check_spec_implements_resolve(repo_graph, resolver=repo_resolver),
                entry.name,
            )
        )
        checks.append(
            _annotate_findings(
                check_spec_refines_resolve(repo_graph, resolver=repo_resolver),
                entry.name,
            )
        )
        checks.append(
            _annotate_findings(
                check_spec_needs_rewrite(repo_graph),
                entry.name,
            )
        )
        checks.append(
            _annotate_findings(
                check_spec_hierarchy_levels(repo_graph, repo_config),
                entry.name,
            )
        )
        _typed_repo = _validate_config(repo_config)
        _allow_so = (
            _typed_repo.rules.hierarchy.allow_structural_orphans
            if _typed_repo.rules.hierarchy.allow_structural_orphans is not None
            else (_typed_repo.rules.hierarchy.allow_orphans or False)
        )
        checks.append(
            _annotate_findings(
                check_structural_orphans(
                    repo_graph,
                    allow_structural_orphans=_allow_so,
                ),
                entry.name,
            )
        )
        checks.append(
            _annotate_findings(
                check_spec_format_rules(repo_graph, repo_config, resolver=repo_resolver),
                entry.name,
            )
        )
        checks.append(
            _annotate_findings(
                check_spec_no_assertions(repo_graph, repo_config),
                entry.name,
            )
        )
        checks.append(
            _annotate_findings(
                check_spec_changelog_present(repo_graph, repo_config),
                entry.name,
            )
        )
        checks.append(
            _annotate_findings(
                check_spec_changelog_current(repo_graph, repo_config),
                entry.name,
            )
        )
        checks.append(
            _annotate_findings(
                check_spec_changelog_format(repo_graph, repo_config),
                entry.name,
            )
        )

    if spec_dirs:
        checks.append(check_spec_index_current(graph, spec_dirs))

    # Post-process: downgrade checks that only have findings for retired REQs
    if retired_ids:
        _downgrade_retired_findings(checks, retired_ids)

    return checks


# =============================================================================
# Code Checks
# =============================================================================


def _resolve_exclude_status(
    args: argparse.Namespace,
    config: dict[str, Any] | None = None,
) -> set[str]:
    """Compute the set of statuses to exclude from coverage.

    If --status is provided, add those statuses to the normally-included set
    (e.g. --status Draft includes both Active and Draft). Without --status,
    use status_roles config to determine exclusions.
    """
    from elspais.config import get_status_roles

    roles = get_status_roles(config or {})
    include_raw: list[str] | None = getattr(args, "status", None)
    if not include_raw:
        return roles.coverage_excluded_statuses()
    # --status flag: add these statuses to the normally-included set
    extra = {s.title() for s in include_raw}
    default_excluded = roles.coverage_excluded_statuses()
    return default_excluded - extra


def _excluded_note(
    graph: FederatedGraph,
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


def check_dimension_coverage(
    graph: FederatedGraph,
    dimension: str,
    exclude_status: set[str] | None = None,
    config: dict[str, Any] | None = None,
) -> HealthCheck:
    """Check coverage for one of the 5 CoverageDimension dimensions.

    Reports both requirement-level (any coverage) and assertion-level
    (direct/indirect percentages) metrics.

    Args:
        graph: The graph to check.
        dimension: One of 'implemented', 'tested', 'verified',
                   'uat_coverage', 'uat_verified'.
        exclude_status: Statuses to exclude from counts.
        config: Project config dict.
    """
    from elspais.graph import NodeKind

    if exclude_status is None:
        from elspais.config import get_status_roles

        exclude_status = get_status_roles(config or {}).coverage_excluded_statuses()

    dim_labels = {
        "implemented": ("Implemented", "code"),
        "tested": ("Tested", "tests"),
        "verified": ("Verified", "tests"),
        "uat_coverage": ("Validated", "uat"),
        "uat_verified": ("Accepted", "uat"),
        "code_tested": ("Code Tested (line coverage)", "code"),
    }
    label, category = dim_labels.get(dimension, (dimension, "code"))

    req_count = 0
    req_with_any = 0  # REQs where dim.indirect > 0
    req_with_direct = 0  # REQs where dim.direct > 0
    total_assertions = 0
    direct_assertions = 0
    indirect_assertions = 0
    has_any_failures = False

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if node.status in exclude_status:
            continue
        req_count += 1
        metrics = node.get_metric("rollup_metrics")
        if metrics is None:
            continue
        dim = getattr(metrics, dimension, None)
        if dim is None:
            continue
        total_assertions += dim.total
        direct_assertions += dim.direct
        indirect_assertions += dim.indirect
        if dim.indirect > 0:
            req_with_any += 1
        if dim.direct > 0:
            req_with_direct += 1
        if dim.has_failures:
            has_any_failures = True

    req_pct = (req_with_any / req_count * 100) if req_count > 0 else 0
    direct_pct = (direct_assertions / total_assertions * 100) if total_assertions > 0 else 0
    indirect_pct = (indirect_assertions / total_assertions * 100) if total_assertions > 0 else 0
    note = _excluded_note(graph, exclude_status)

    # Build message showing both levels
    msg_parts = [
        f"{label}: {req_with_any}/{req_count} REQs ({req_pct:.0f}%)",
        f"{direct_assertions}/{total_assertions} assertions direct ({direct_pct:.0f}%)",
    ]
    if indirect_assertions != direct_assertions:
        msg_parts.append(f"{indirect_assertions} indirect ({indirect_pct:.0f}%)")
    if has_any_failures:
        msg_parts.append("FAILURES DETECTED")
    message = ", ".join(msg_parts) + note

    return HealthCheck(
        name=f"{category}.{dimension}",
        passed=not has_any_failures,
        message=message,
        category=category,
        severity="error" if has_any_failures else "info",
        details={
            "dimension": dimension,
            "reqs_with_any_coverage": req_with_any,
            "reqs_with_direct_coverage": req_with_direct,
            "total_requirements": req_count,
            "req_coverage_percent": round(req_pct, 1),
            "total_assertions": total_assertions,
            "direct_assertions": direct_assertions,
            "indirect_assertions": indirect_assertions,
            "direct_pct": round(direct_pct, 1),
            "indirect_pct": round(indirect_pct, 1),
            "has_failures": has_any_failures,
        },
    )


def check_code_coverage(
    graph: FederatedGraph,
    exclude_status: set[str] | None = None,
    config: dict[str, Any] | None = None,
) -> HealthCheck:
    """Check code coverage — delegates to dimension check for 'implemented'."""
    return check_dimension_coverage(
        graph, "implemented", exclude_status=exclude_status, config=config
    )


def check_unlinked_code(graph: FederatedGraph) -> HealthCheck:
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


def run_code_checks(
    graph: FederatedGraph,
    exclude_status: set[str] | None = None,
    config: dict[str, Any] | None = None,
) -> list[HealthCheck]:
    """Run all code reference health checks."""
    from elspais.graph import NodeKind

    checks = [
        check_code_coverage(graph, exclude_status=exclude_status),
        check_unlinked_code(graph),
    ]

    # Add code_tested dimension only when line coverage data is present
    has_coverage = any(
        (m := node.get_metric("rollup_metrics")) is not None and m.code_tested.total > 0
        for node in graph.nodes_by_kind(NodeKind.REQUIREMENT)
    )
    if has_coverage:
        checks.append(
            check_dimension_coverage(
                graph, "code_tested", exclude_status=exclude_status, config=config
            )
        )

    return checks


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
    if config:
        _tc = _validate_config(config)
        meta_file = _tc.scanning.result.run_meta_file
    else:
        meta_file = ""
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


def check_test_results(graph: FederatedGraph, config: dict | None = None) -> HealthCheck:
    """Check test result status from JUnit/pytest output."""
    from elspais.graph import NodeKind

    result_nodes = list(graph.nodes_by_kind(NodeKind.RESULT))
    run_meta = _read_run_meta(config)
    deselected = run_meta["deselected_count"]

    if not result_nodes:
        # Check if result scanning is actually configured
        if config:
            _tc = _validate_config(config)
            result_files = _tc.scanning.result.file_patterns
        else:
            result_files = []
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
    graph: FederatedGraph,
    exclude_status: set[str] | None = None,
    config: dict[str, Any] | None = None,
) -> HealthCheck:
    """Check test coverage — delegates to dimension check for 'tested'."""
    return check_dimension_coverage(graph, "tested", exclude_status=exclude_status, config=config)


def check_uat_coverage(
    graph: FederatedGraph,
    exclude_status: set[str] | None = None,
    config: dict[str, Any] | None = None,
) -> HealthCheck:
    """Check UAT coverage — delegates to dimension check for 'uat_coverage'."""
    return check_dimension_coverage(
        graph, "uat_coverage", exclude_status=exclude_status, config=config
    )


def check_unlinked_tests(graph: FederatedGraph) -> HealthCheck:
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


def check_uat_results(graph: FederatedGraph, config: dict[str, Any] | None = None) -> HealthCheck:
    """Check UAT results from a journey results CSV file.

    Expects a CSV file with columns: journey_id, status (pass/fail/skip).
    The file path is configured via scanning.journey.results_file in .elspais.toml,
    defaulting to 'uat-results.csv' in the repository root.
    """
    cfg = config or {}
    journey_cfg = cfg.get("scanning", {}).get("journey", {})
    results_file = journey_cfg.get("results_file", "uat-results.csv")

    results_path = Path(results_file)
    if not results_path.is_absolute():
        git_root = cfg.get("_git_root")
        if git_root:
            results_path = Path(git_root) / results_path
        elif not results_path.exists():
            # Try cwd
            results_path = Path.cwd() / results_file

    if not results_path.exists():
        return HealthCheck(
            name="uat.results",
            passed=True,
            message=f"No UAT results file found ({results_file})",
            category="uat",
            severity="info",
        )

    import csv

    passed = 0
    failed = 0
    skipped = 0
    failures: list[str] = []

    try:
        with open(results_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                jid = row.get("journey_id", row.get("id", "")).strip()
                status = row.get("status", "").strip().lower()
                if status in ("pass", "passed"):
                    passed += 1
                elif status in ("fail", "failed"):
                    failed += 1
                    failures.append(jid)
                elif status in ("skip", "skipped"):
                    skipped += 1
    except Exception as e:
        return HealthCheck(
            name="uat.results",
            passed=False,
            message=f"Error reading UAT results: {e}",
            category="uat",
            severity="warning",
        )

    total = passed + failed + skipped
    if total == 0:
        return HealthCheck(
            name="uat.results",
            passed=True,
            message=f"UAT results file is empty ({results_file})",
            category="uat",
            severity="info",
        )

    pass_rate = (passed / total * 100) if total > 0 else 0

    if failed > 0:
        findings = [HealthFinding(message=f"Failed: {jid}", node_id=jid) for jid in failures]
        return HealthCheck(
            name="uat.results",
            passed=False,
            message=(
                f"UAT failures: {passed} passed, {failed} failed, "
                f"{skipped} skipped ({pass_rate:.1f}% pass rate)"
            ),
            category="uat",
            severity="warning",
            details={
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "pass_rate": round(pass_rate, 1),
            },
            findings=findings,
        )

    return HealthCheck(
        name="uat.results",
        passed=True,
        message=f"All UAT passing: {passed} passed, {skipped} skipped",
        category="uat",
        details={
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "pass_rate": round(pass_rate, 1),
        },
    )


def run_test_checks(
    graph: FederatedGraph, exclude_status: set[str] | None = None, config: dict | None = None
) -> list[HealthCheck]:
    """Run all test file health checks."""
    return [
        check_test_coverage(graph, exclude_status=exclude_status, config=config),
        check_dimension_coverage(graph, "verified", exclude_status=exclude_status, config=config),
        check_unlinked_tests(graph),
        check_test_results(graph, config=config),
    ]


def run_uat_checks(
    graph: FederatedGraph, exclude_status: set[str] | None = None, config: dict | None = None
) -> list[HealthCheck]:
    """Run all UAT (User Acceptance Test) health checks."""
    return [
        check_uat_coverage(graph, exclude_status=exclude_status, config=config),
        check_dimension_coverage(
            graph, "uat_verified", exclude_status=exclude_status, config=config
        ),
        check_uat_results(graph, config=config),
    ]


# =============================================================================
# Composable Section API
# =============================================================================


# Implements: REQ-d00085-A
def render_section(
    graph: FederatedGraph | None,
    config: dict[str, Any] | None,
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
        resolved_spec_dirs = get_spec_directories(spec_dir, config)
        for check in run_spec_checks(graph, config, spec_dirs=resolved_spec_dirs):
            report.add(check)
    if graph:
        raw_config = config if config else {}
        exclude_status = _resolve_exclude_status(args, config=raw_config)
        for check in run_code_checks(graph, exclude_status=exclude_status, config=raw_config):
            report.add(check)
        for check in run_test_checks(graph, exclude_status=exclude_status, config=raw_config):
            report.add(check)
        for check in run_uat_checks(graph, exclude_status=exclude_status, config=raw_config):
            report.add(check)

    output = _format_report(report, args)
    lenient = getattr(args, "lenient", False)
    healthy = report.is_healthy_lenient if lenient else report.is_healthy
    return output, 0 if healthy else 1


# =============================================================================
# Main Command
# =============================================================================


def compute_checks(
    graph: FederatedGraph,
    config: dict[str, Any],
    params: dict[str, str],
) -> dict[str, Any]:
    """Compute health checks for engine.call.  Returns HealthReport.to_dict()."""
    import argparse

    spec_only = params.get("spec_only", "false") == "true"
    code_only = params.get("code_only", "false") == "true"
    tests_only = params.get("tests_only", "false") == "true"
    lenient = params.get("lenient", "false") == "true"

    report = HealthReport()
    run_all = not any([spec_only, code_only, tests_only])

    # Build a minimal args namespace for _resolve_exclude_status
    fake_args = argparse.Namespace()
    status_str = params.get("status", None)
    fake_args.status = status_str.split(",") if status_str else None

    exclude_status = _resolve_exclude_status(fake_args, config=config)

    # Config checks
    if run_all:
        try:
            from elspais.commands.doctor import run_config_checks as _run_config_checks
            from elspais.config import find_git_root

            repo_root = find_git_root() or Path.cwd()
            config_path = repo_root / ".elspais.toml"
            for check in _run_config_checks(
                config_path if config_path.exists() else None,
                config,
                repo_root,
            ):
                report.add(check)
        except Exception:
            pass

    # Spec checks
    if run_all or spec_only:
        from elspais.config import get_spec_directories

        spec_dirs = get_spec_directories(None, config)
        for check in run_spec_checks(graph, config, spec_dirs=spec_dirs):
            report.add(check)

    # Code checks
    if run_all or code_only:
        for check in run_code_checks(graph, exclude_status=exclude_status, config=config):
            report.add(check)

    # Test checks
    if run_all or tests_only:
        for check in run_test_checks(graph, exclude_status=exclude_status, config=config):
            report.add(check)

    # UAT checks
    if run_all or tests_only:
        for check in run_uat_checks(graph, exclude_status=exclude_status, config=config):
            report.add(check)

    return report.to_dict(lenient=lenient)


def _report_from_dict(data: dict[str, Any]) -> HealthReport:
    """Reconstruct a HealthReport from a to_dict() JSON dict."""
    report = HealthReport()
    for c in data.get("checks", []):
        findings = [
            HealthFinding(
                message=f.get("message", ""),
                file_path=f.get("file_path"),
                line=f.get("line"),
                node_id=f.get("node_id"),
                related=f.get("related", []),
                repo=f.get("repo"),
                retired=f.get("retired", False),
            )
            for f in c.get("findings", [])
        ]
        report.add(
            HealthCheck(
                name=c["name"],
                passed=c["passed"],
                message=c["message"],
                category=c["category"],
                severity=c.get("severity", "error"),
                details=c.get("details", {}),
                findings=findings,
            )
        )
    return report


def run(args: argparse.Namespace) -> int:
    """Run the health command.

    Uses engine.call for daemon-vs-local, then renders the report.
    """
    from elspais.commands import _engine

    # Build params from args
    params: dict[str, str] = {}
    if getattr(args, "spec_only", False):
        params["spec_only"] = "true"
    if getattr(args, "code_only", False):
        params["code_only"] = "true"
    if getattr(args, "tests_only", False):
        params["tests_only"] = "true"
    if getattr(args, "lenient", False):
        params["lenient"] = "true"
    status_filter = getattr(args, "status", None)
    if status_filter:
        params["status"] = ",".join(status_filter)

    spec_dir = getattr(args, "spec_dir", None)
    skip_daemon = bool(spec_dir)

    if skip_daemon:
        # Custom spec_dir: build graph directly with the requested dirs,
        # preserving the original error-handling for config/graph failures.
        data = _run_local_checks(args, params)
    else:
        data = _engine.call(
            "/api/run/checks",
            params,
            compute_checks,
            config_path=getattr(args, "config", None),
        )

    # The dict already has the correct "healthy" flag (lenient-aware).
    # Use it for exit code; reconstruct report only for rendering.
    healthy = data.get("healthy", False)
    graph_source = _format_graph_source(data.get("graph_source"))
    report = _report_from_dict(data)
    print(_format_report(report, args, graph_source=graph_source))
    return 0 if healthy else 1


def _run_local_checks(args: argparse.Namespace, params: dict[str, str]) -> dict[str, Any]:
    """Build graph from args and run checks locally.

    Handles spec_dir, config_path and graceful error recovery
    for config-load and graph-build failures.
    """
    from elspais.config import get_config
    from elspais.graph.factory import build_graph

    spec_dir = getattr(args, "spec_dir", None)
    config_path = getattr(args, "config", None)
    start_path = Path.cwd()
    lenient = params.get("lenient", "false") == "true"

    report = HealthReport()

    run_all = not any(
        [
            params.get("spec_only") == "true",
            params.get("code_only") == "true",
            params.get("tests_only") == "true",
        ]
    )

    # Config checks can run without building the graph
    config = None
    if run_all:
        try:
            config = get_config(config_path, start_path=start_path)
        except Exception as e:
            report.add(
                HealthCheck(
                    name="config.load",
                    passed=False,
                    message=f"Failed to load config: {e}",
                    category="config",
                )
            )

    # Build graph
    graph = None
    try:
        graph = build_graph(
            spec_dirs=[spec_dir] if spec_dir else None,
            config_path=config_path,
        )
        if config is None:
            config = get_config(config_path, start_path=start_path)
    except Exception as e:
        report.add(
            HealthCheck(
                name="graph.build",
                passed=False,
                message=f"Failed to build graph: {e}",
                category="spec",
            )
        )
        return report.to_dict(lenient=lenient)

    if graph is not None and config is not None:
        # Delegate to compute_checks for the actual check logic
        return compute_checks(graph, config, params)

    return report.to_dict(lenient=lenient)


def _format_graph_source(source: dict | None) -> str | None:
    """Format graph_source metadata as a human-readable string."""
    if source is None:
        return None
    source_type = source.get("type", "unknown")
    if source_type == "local":
        return None  # Local builds need no annotation
    if source_type == "daemon":
        parts = [f"daemon (port {source.get('port', '?')}"]
        started = source.get("started_at")
        if started:
            parts[0] += f", started {started}"
        parts[0] += ")"
        return parts[0]
    if source_type == "viewer":
        return f"viewer (port {source.get('port', '?')})"
    return source_type


def _format_report(
    report: HealthReport,
    args: argparse.Namespace,
    graph_source: str | None = None,
) -> str:
    """Format the health report as a string."""
    fmt = getattr(args, "format", "text") or "text"
    lenient = getattr(args, "lenient", False)
    quiet = getattr(args, "quiet", False)
    verbose = getattr(args, "verbose", False)
    include_passing = getattr(args, "include_passing_details", False)

    # Build active flags summary from args
    flag_parts: list[str] = []
    status_list = getattr(args, "status", None)
    if status_list:
        flag_parts.append("--status " + " ".join(status_list))
    if getattr(args, "lenient", False):
        flag_parts.append("--lenient")
    if getattr(args, "spec_only", False):
        flag_parts.append("--spec")
    if getattr(args, "code_only", False):
        flag_parts.append("--code")
    if getattr(args, "tests_only", False):
        flag_parts.append("--tests")
    active_flags = ", ".join(flag_parts) if flag_parts else None

    from elspais.utilities.report_meta import report_metadata

    meta = report_metadata()

    if fmt == "json":
        d = report.to_dict(lenient=lenient)
        d["meta"] = meta
        return json.dumps(d, indent=2)
    elif fmt == "markdown":
        data = _build_report_data(report)
        data.graph_source = graph_source
        data.active_flags = active_flags
        data.meta = meta
        return _render_markdown(data)
    elif fmt == "junit":
        return _render_junit(report, include_passing_details=include_passing)
    elif fmt == "sarif":
        return _render_sarif(report)
    else:
        if quiet:
            return _build_report_data(report, verbose=verbose).summary_line
        data = _build_report_data(report, verbose=verbose)
        data.graph_source = graph_source
        data.active_flags = active_flags
        data.meta = meta
        return _render_text(data)


# =============================================================================
# Report Data Intermediate Representation
# =============================================================================


# Maps check names to the follow-up command a user should run.
_FOLLOWUP_COMMANDS: dict[str, str] = {
    "spec.hash_integrity": "elspais fix",
    "spec.needs_rewrite": "elspais fix",
    "spec.format_rules": "elspais checks --spec --format json",
    "spec.no_assertions": "elspais gaps",
    "spec.index_current": "elspais fix",
    "spec.no_duplicates": "elspais checks --spec --format json",
    "spec.implements_resolve": "elspais broken",
    "spec.refines_resolve": "elspais broken",
    "spec.broken_references": "elspais broken",
    "spec.structural_orphans": "elspais checks --spec --format json",
    "spec.hierarchy_levels": "elspais checks --spec --format json",
    "spec.changelog_present": "elspais fix",
    "spec.changelog_current": "elspais fix -m 'Update changelog'",
    "spec.changelog_format": "elspais checks --spec --format json",
    "code.unlinked": "elspais unlinked",
    "tests.unlinked": "elspais unlinked",
    "tests.results": "elspais failing",
    "uat.results": "elspais failing",
}


@dataclass
class _CheckLine:
    """Pre-computed display data for a single health check."""

    icon: str  # "\u2713", "\u2717", "\u26a0", "~"
    name: str
    message: str
    followup: str | None = None


@dataclass
class _SectionData:
    """Pre-computed display data for a health check category."""

    name: str  # "CONFIG", "SPEC", etc.
    icon: str  # "\u2713", "\u2717", "\u26a0"
    stats: str  # "3 passed, 1 failed" or "3 passed, 1 failed, 1 skipped"
    checks: list[_CheckLine]


@dataclass
class _ReportData:
    """Pre-computed display data for an entire health report."""

    sections: list[_SectionData]
    summary_line: str
    is_healthy: bool
    hint: str | None
    graph_source: str | None = None
    active_flags: str | None = None
    meta: dict[str, str] | None = None


def _build_hint(report: HealthReport, already_verbose: bool) -> str | None:
    """Build a hint string about how to get more details on failures.

    Returns None if no categories have failures. Uses 'elspais checks'
    (the renamed command).
    """
    failed_categories: set[str] = set()
    for check in report.checks:
        if not check.passed and check.severity in ("error", "warning"):
            failed_categories.add(check.category)

    if not failed_categories:
        return None

    category_flags = {"spec": "--spec", "code": "--code", "tests": "--tests", "config": ""}
    if len(failed_categories) == 1:
        cat = next(iter(failed_categories))
        flag = category_flags.get(cat, "")
        scope = f" {flag}" if flag else ""
    else:
        scope = ""

    if not already_verbose:
        return (
            f"Run 'elspais -v checks{scope}' for details,\n"
            f" or 'elspais checks{scope} --format json -o health.json'"
            f" for machine-readable output."
        )
    else:
        return (
            f"Run 'elspais checks{scope} --format json -o health.json'"
            f" for machine-readable output."
        )


def _build_summary_line(report: HealthReport) -> str:
    """Build the summary line string (matches _print_summary_line logic)."""
    counted = len(report.checks) - report.skipped
    skip_suffix = f", {report.skipped} skipped" if report.skipped else ""
    if report.failed == 0 and report.warnings == 0 and report.passed == counted:
        if report.skipped:
            return f"HEALTHY: {counted}/{counted} checks passed{skip_suffix}"
        else:
            return f"HEALTHY: {counted}/{counted} checks passed"
    elif report.failed == 0 and report.warnings == 0:
        return f"{report.passed}/{counted} checks passed{skip_suffix}"
    elif report.failed == 0:
        return (
            f"{report.passed}/{counted} checks passed," f" {report.warnings} warnings{skip_suffix}"
        )
    else:
        return f"UNHEALTHY: {report.failed} errors, {report.warnings} warnings{skip_suffix}"


def _build_report_data(report: HealthReport, verbose: bool = False) -> _ReportData:
    """Build the intermediate representation for rendering a health report.

    Extracts all stat computation logic: category icon selection, pass/fail/skip
    counting (excluding info-severity from pass/total), check icon selection,
    summary line, and hint string.
    """
    categories = ["config", "spec", "code", "tests", "uat"]
    sections: list[_SectionData] = []

    for category in categories:
        checks = list(report.iter_by_category(category))
        if not checks:
            continue

        skipped = sum(1 for c in checks if c.severity == "info")
        passed = sum(1 for c in checks if c.passed and c.severity != "info")
        total = len(checks) - skipped
        has_errors = any(not c.passed and c.severity == "error" for c in checks)
        failed = sum(1 for c in checks if not c.passed and c.severity in ("error", "warning"))

        if passed == total:
            icon = "\u2713"
        elif has_errors:
            icon = "\u2717"
        else:
            icon = "\u26a0"

        parts = [f"{passed} passed", f"{failed} failed"]
        if skipped:
            parts.append(f"{skipped} skipped")

        check_lines: list[_CheckLine] = []
        for check in checks:
            if check.severity == "info":
                c_icon = "~"
            elif check.passed:
                c_icon = "\u2713"
            elif check.severity == "warning":
                c_icon = "\u26a0"
            else:
                c_icon = "\u2717"
            followup = None
            if not check.passed or check.severity == "warning":
                followup = _FOLLOWUP_COMMANDS.get(check.name)
            check_lines.append(
                _CheckLine(icon=c_icon, name=check.name, message=check.message, followup=followup)
            )

        sections.append(
            _SectionData(
                name=category.upper(),
                icon=icon,
                stats=", ".join(parts),
                checks=check_lines,
            )
        )

    summary_line = _build_summary_line(report)
    is_healthy = report.is_healthy
    hint = _build_hint(report, verbose) if not is_healthy else None

    return _ReportData(
        sections=sections,
        summary_line=summary_line,
        is_healthy=is_healthy,
        hint=hint,
    )


def _render_text(data: _ReportData) -> str:
    """Render _ReportData as plain text checklist."""
    lines: list[str] = []
    for section in data.sections:
        lines.append(f"\n{section.icon} {section.name} ({section.stats})")
        lines.append("-" * 40)
        for check in section.checks:
            lines.append(f"  {check.icon} {check.name}: {check.message}")

    # Collect follow-up commands for failing/warning checks
    followups = [
        (check.name, check.followup)
        for section in data.sections
        for check in section.checks
        if check.followup
    ]

    lines.append("")
    lines.append("=" * 40)
    lines.append(data.summary_line)
    if data.active_flags:
        lines.append(f"Flags: {data.active_flags}")
    if data.meta:
        from elspais.utilities.report_meta import format_meta_line

        meta_line = format_meta_line(data.meta)
        if data.graph_source:
            meta_line = meta_line[:-1] + f", via {data.graph_source})"
        lines.append(meta_line)
    elif data.graph_source:
        lines.append(f"(via {data.graph_source})")
    if followups:
        lines.append("")
        lines.append("Follow-up:")
        max_name = max(len(name) for name, _ in followups)
        for name, cmd in followups:
            lines.append(f"  {name:<{max_name}}  {cmd}")
    lines.append("=" * 40)
    return "\n".join(lines)


def _print_text_report(
    report: HealthReport,
    verbose: bool = False,
    include_passing_details: bool = False,
) -> None:
    """Print human-readable health report (legacy wrapper)."""
    data = _build_report_data(report, verbose=verbose)
    print(_render_text(data))


# Implements: REQ-d00085-E
def _render_markdown(data: _ReportData) -> str:
    """Render _ReportData as markdown checklist."""
    lines: list[str] = []

    for i, section in enumerate(data.sections):
        if i > 0:
            lines.append("---")
            lines.append("")
        lines.append(f"## {section.icon} {section.name} ({section.stats})")
        lines.append("")
        for check in section.checks:
            if check.icon == "~":
                lines.append(f"- [ ] ~ {check.name}: {check.message}")
            elif check.icon == "\u2713":
                lines.append(f"- [x] {check.name}: {check.message}")
            else:
                lines.append(f"- [ ] {check.name}: {check.message}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(data.summary_line)

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
    categories = ["config", "spec", "code", "tests", "uat"]

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
