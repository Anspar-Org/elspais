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
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from elspais.config.schema import ElspaisConfig
from elspais.config.status_roles import StatusRole
from elspais.graph.aggregation import EvidenceResult
from elspais.graph.reference_faults import FaultClass, FaultCode
from elspais.utilities.findings import (
    NO_KNOWN_REMEDY,
    REGISTRY,
    REPORTED_SEVERITIES,
    Severity,
    is_registered,
    remedy_for,
    severity_for,
)

if TYPE_CHECKING:
    from elspais.graph.federated import FederatedGraph
    from elspais.graph.GraphNode import GraphNode
    from elspais.utilities.patterns import IdResolver


def _validate_config(config: dict[str, Any]) -> ElspaisConfig:
    """Validate a config dict into ElspaisConfig (see config.validate_config)."""
    from elspais.config import validate_config

    return validate_config(config)


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
    # The diagnostic codes the finding reached, as a field rather than only as
    # text inside `message`, so a reader can select on one (`checks --code`)
    # and a structured format can carry it as a value.
    codes: list[str] = field(default_factory=list)

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
        if self.codes:
            d["codes"] = list(self.codes)
        return d

    def location(self) -> str | None:
        """Where the finding is about, as `path:line` -- or None where it has none."""
        if not self.file_path:
            return None
        return f"{self.file_path}:{self.line}" if self.line is not None else self.file_path


@dataclass
class HealthCheck:
    """Result of a single health check."""

    name: str
    passed: bool
    message: str
    category: str  # config, spec, code, tests
    severity: str = "error"  # one of REPORTED_SEVERITIES
    details: dict[str, Any] = field(default_factory=dict)
    findings: list[HealthFinding] = field(default_factory=list)
    # The action that resolves what this check reports. Left empty by every
    # caller: it is resolved from the one registry below, so a finding carries
    # its remedy into every format rather than into the one whose renderer
    # remembered to consult a table (REQ-d00285-B+C).
    remedy: str = ""

    # Implements: REQ-d00212-U, REQ-d00285-D, REQ-d00285-B
    def __post_init__(self) -> None:
        # A severity outside the vocabulary matched none of the branches that
        # count a check, so the check was neither failed, warned nor skipped
        # and the run reported healthy. Refusing it here is what makes that
        # fall-through impossible rather than merely unlikely. `off` is a
        # configuration value, not a reported one: a check resolving to it is
        # emitted as a skipped `info` check (see `skipped_check`).
        if self.severity not in REPORTED_SEVERITIES:
            raise ValueError(
                f"{self.name}: {self.severity!r} is not a severity a check can be "
                f"reported at. Reported severities: {', '.join(REPORTED_SEVERITIES)}."
            )
        if not self.remedy:
            # A name outside the registry has no remedy anyone recorded, and
            # saying so is the obligation. Every name the tool itself reports
            # under is registered -- that is what `severity_for` enforces at
            # the point each check is built.
            self.remedy = remedy_for(self.name) if is_registered(self.name) else NO_KNOWN_REMEDY


# Implements: REQ-d00285-G
def skipped_check(name: str, condition: str) -> HealthCheck:
    """The check a project has turned off: what was withheld, and why.

    A condition detected and dropped in silence is indistinguishable from one
    never detected, so the skip is reported as a check of its own rather than
    an absence.
    """
    return HealthCheck(
        name=name,
        passed=True,
        message=f"{condition} not reported (severity=off)",
        category=REGISTRY[name].category,
        severity="info",
        details={"skipped": True, "reason": "severity=off"},
    )


@dataclass
class HealthReport:
    """Aggregated health check results."""

    checks: list[HealthCheck] = field(default_factory=list)

    # The four counts below PARTITION the checks: every check carries one of
    # `REPORTED_SEVERITIES` (a `HealthCheck` cannot be built carrying anything
    # else), and each severity lands in exactly one count -- info in `skipped`,
    # warning and error in `passed` or in `warnings`/`failed` by outcome. A
    # value counted nowhere is what let a mistyped severity report healthy.

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
                    "remedy": c.remedy,
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


def check_spec_files_parseable(
    graph: FederatedGraph, config: dict[str, Any] | None = None
) -> HealthCheck:
    """Check that all spec files were parsed without errors."""
    severity = severity_for("spec.parseable", config)
    if severity == Severity.OFF:
        return skipped_check("spec.parseable", "Spec files that produced no requirements")

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
            severity=severity,
        )

    return HealthCheck(
        name="spec.parseable",
        passed=True,
        message=f"Parsed {req_count} requirements with {assertion_count} assertions",
        category="spec",
        details={"requirements": req_count, "assertions": assertion_count},
    )


def check_spec_no_duplicates(
    graph: FederatedGraph, config: dict[str, Any] | None = None
) -> HealthCheck:
    """Check for cross-file duplicate requirement IDs.

    Reads the build-time collision record from the graph, since by the time
    this check runs the in-memory node index has already disambiguated
    subsequent occurrences with synthetic IDs. The collision record preserves
    every source file that defined each canonical ID.
    """
    severity = severity_for("spec.no_duplicates", config)
    if severity == Severity.OFF:
        return skipped_check("spec.no_duplicates", "Duplicate requirement identifiers")

    duplicates = graph.duplicate_req_ids()

    if duplicates:
        findings = [
            HealthFinding(
                message=f"Duplicate ID {req_id} in {', '.join(files)}",
                file_path=files[0] if files else None,
                node_id=req_id,
            )
            for req_id, files in duplicates.items()
        ]
        return HealthCheck(
            name="spec.no_duplicates",
            passed=False,
            message=f"Found {len(duplicates)} duplicate requirement IDs",
            category="spec",
            severity=severity,
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
    graph: FederatedGraph,
    resolver: IdResolver | None = None,
    config: dict[str, Any] | None = None,
) -> HealthCheck:
    """Check that all Implements references resolve to valid requirements."""
    severity = severity_for("spec.implements_resolve", config)
    if severity == Severity.OFF:
        return skipped_check("spec.implements_resolve", "Implements references that do not resolve")

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
                # Splitting a reference needs the grammar that admits it;
                # guessing the boundary character finds whichever one the
                # component itself contains and names a different parent.
                split = resolver.split_assertion_ref(ref) if resolver else None
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
            severity=severity,
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
    graph: FederatedGraph,
    resolver: IdResolver | None = None,
    config: dict[str, Any] | None = None,
) -> HealthCheck:
    """Check that all Refines references resolve to valid requirements."""
    severity = severity_for("spec.refines_resolve", config)
    if severity == Severity.OFF:
        return skipped_check("spec.refines_resolve", "Refines references that do not resolve")

    from elspais.graph import NodeKind

    unresolved = []

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        refines = node.get_field("refines", [])
        for ref in refines:
            target = graph.find_by_id(ref)
            if target is None:
                # Check assertion reference
                # Splitting a reference needs the grammar that admits it;
                # guessing the boundary character finds whichever one the
                # component itself contains and names a different parent.
                split = resolver.split_assertion_ref(ref) if resolver else None
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
            severity=severity,
            details={"unresolved": unresolved[:10]},
            findings=findings,
        )

    return HealthCheck(
        name="spec.refines_resolve",
        passed=True,
        message="All Refines references resolve",
        category="spec",
    )


# Implements: REQ-p00014-E
def check_spec_satisfies_resolve(
    graph: FederatedGraph,
    resolver: IdResolver | None = None,
    config: dict[str, Any] | None = None,
) -> HealthCheck:
    """Check that all Satisfies references resolve to valid requirements or assertions."""
    severity = severity_for("spec.satisfies_resolve", config)
    if severity == Severity.OFF:
        return skipped_check("spec.satisfies_resolve", "Satisfies references that do not resolve")

    from elspais.graph import NodeKind

    unresolved = []

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        satisfies = node.get_field("satisfies", [])
        for ref in satisfies:
            target = graph.find_by_id(ref)
            if target is None:
                # Check assertion reference
                # Splitting a reference needs the grammar that admits it;
                # guessing the boundary character finds whichever one the
                # component itself contains and names a different parent.
                split = resolver.split_assertion_ref(ref) if resolver else None
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
            name="spec.satisfies_resolve",
            passed=False,
            message=f"{len(unresolved)} unresolved Satisfies references",
            category="spec",
            severity=severity,
            details={"unresolved": unresolved[:10]},
            findings=findings,
        )

    return HealthCheck(
        name="spec.satisfies_resolve",
        passed=True,
        message="All Satisfies references resolve",
        category="spec",
    )


# Implements: REQ-d00085-I
def check_spec_needs_rewrite(
    graph: FederatedGraph, config: dict[str, Any] | None = None
) -> HealthCheck:
    """Check for requirements that would change the file on next save.

    A requirement is marked parse_dirty at build time when any condition is
    detected that means the in-memory state differs from the file on disk:
    - duplicate_refs: same REQ ID appears more than once in Implements/Refines
    - stale_hash: stored hash does not match the computed hash
    """
    severity = severity_for("spec.needs_rewrite", config)
    if severity == Severity.OFF:
        return skipped_check("spec.needs_rewrite", "Requirements whose stored text is out of date")

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
            severity=severity,
            details={"count": len(findings)},
            findings=findings,
        )

    return HealthCheck(
        name="spec.needs_rewrite",
        passed=True,
        message="No requirements need rewriting",
        category="spec",
    )


# Implements: REQ-d00250-F
def check_unfixable_issues(
    graph: FederatedGraph, config: dict[str, Any] | None = None
) -> HealthCheck:
    """Check for requirements with issues that ``--fix`` cannot resolve.

    Currently reports:
    - ``section_header_depth_unfixable``: a requirement at H6 has section
      blocks (Assertions/Changelog/named) that would need to live at H7
      to be canonical, which markdown does not support.
    """
    severity = severity_for("spec.unfixable_issues", config)
    if severity == Severity.OFF:
        return skipped_check("spec.unfixable_issues", "Issues fix cannot repair")

    from elspais.graph import NodeKind

    findings: list[HealthFinding] = []
    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        reasons = node.get_field("parse_unfixable_reasons") or []
        if not reasons:
            continue
        fn = node.file_node()
        file_path = fn.get_field("relative_path") if fn is not None else None
        findings.append(
            HealthFinding(
                message=f"Cannot auto-fix: {', '.join(reasons)}",
                node_id=node.id,
                file_path=file_path,
                line=node.get_field("parse_line"),
            )
        )

    if findings:
        return HealthCheck(
            name="spec.unfixable_issues",
            passed=False,
            message=f"{len(findings)} requirement(s) have unfixable issues",
            category="spec",
            severity=severity,
            details={"count": len(findings)},
            findings=findings,
        )

    return HealthCheck(
        name="spec.unfixable_issues",
        passed=True,
        message="No unfixable issues",
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


# Implements: REQ-d00281-D
def check_spec_undefined_levels(graph: FederatedGraph, config: dict[str, Any]) -> HealthCheck:
    """Report requirements carrying a level this configuration does not define.

    Such a requirement is counted and grouped like any other (REQ-d00281-A+C) --
    it is real work somebody owes, and dropping it would flatter every figure it
    would have lowered. What it cannot do is pass silently: a level the
    configuration never names is as likely a misspelling, or a level deleted
    while its requirements remained, as it is a deliberate federated difference,
    and the report is the only place an author would find out.
    """
    severity = severity_for("spec.undefined_levels", config)
    if severity == Severity.OFF:
        return skipped_check(
            "spec.undefined_levels", "Requirements at a level the configuration does not define"
        )

    from elspais.graph import NodeKind

    typed_config = _validate_config(config)
    defined = {k.lower() for k in typed_config.levels}

    findings: list[HealthFinding] = []
    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        level = (node.level or "").strip()
        if level and level.lower() not in defined:
            findings.append(
                HealthFinding(
                    message=(
                        f"{node.id} carries level '{level}', "
                        "which this configuration does not define"
                    ),
                    node_id=node.id,
                )
            )

    if findings:
        return HealthCheck(
            name="spec.undefined_levels",
            passed=True,
            message=(
                f"{len(findings)} requirement(s) carry a level this configuration does not define"
            ),
            category="spec",
            severity=severity,
            findings=findings,
        )
    return HealthCheck(
        name="spec.undefined_levels",
        passed=True,
        message="Every requirement carries a level this configuration defines",
        category="spec",
        severity="info",
    )


def check_spec_hierarchy_levels(graph: FederatedGraph, config: dict[str, Any]) -> HealthCheck:
    """Check that hierarchy levels follow configured rules."""
    severity = severity_for("spec.hierarchy_levels", config)
    if severity == Severity.OFF:
        return skipped_check(
            "spec.hierarchy_levels", "Implements references that cross the level hierarchy"
        )

    from elspais.graph import NodeKind
    from elspais.graph.relations import EdgeKind

    typed_config = _validate_config(config)
    levels = typed_config.levels
    strict_hierarchy = typed_config.validation.strict_hierarchy

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

        seen_parents: set[str] = set()
        for edge in node.iter_incoming_edges():
            # INTEGRATES is a cross-repo integration edge (consumer -> library),
            # not a level-hierarchy relationship: the library requirement lives
            # in a separate repo's hierarchy and may sit at any level, so a
            # low-level consumer integrating a higher-level library requirement
            # is legitimate, not a deviation. Excluding it keeps the level check
            # from flagging a spurious deviation on the library node. (REQ-d00252-D)
            if edge.kind == EdgeKind.INTEGRATES:
                continue
            parent = edge.source
            if parent.id in seen_parents:
                continue
            seen_parents.add(parent.id)
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
                    f"{v['child']} ({v['child_level']}) -> {v['parent']} ({v['parent_level']})"
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
                severity=severity,
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
    graph: FederatedGraph,
    allow_structural_orphans: bool = False,
    config: dict[str, Any] | None = None,
) -> HealthCheck:
    """Check for nodes without a FILE ancestor (build pipeline bugs)."""
    severity = severity_for("spec.structural_orphans", config)
    if severity == Severity.OFF:
        return skipped_check("spec.structural_orphans", "Nodes with no file to belong to")

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
            severity=severity,
            details={"by_kind": {k: v[:10] for k, v in orphans_by_kind.items()}, "total": total},
            findings=findings,
        )

    return HealthCheck(
        name="spec.structural_orphans",
        passed=True,
        message="No structural orphans",
        category="spec",
    )


def _fault_location(
    graph: FederatedGraph, source_id: str, line: int | None
) -> tuple[str | None, int | None]:
    """The file path and line a fault's ``source_id`` names.

    A fault anchored to a CODE/TEST node reads its file through
    ``file_node()`` and its line through ``parse_line``. A fault anchored
    directly to a FILE node (an empty reference list, a trailing separator,
    a comment citing a requirement without declaring one -- no CODE/TEST
    node exists for those lines) reads its own
    ``relative_path``, and its line has nowhere to live but the fault
    itself, so *line* (threaded from ``ReferenceFault.line``) wins whenever
    it is set (REQ-d00252-K).
    """
    from elspais.graph import NodeKind

    node = graph.find_by_id(source_id)
    if node is None:
        return None, line
    file_n = node if node.kind == NodeKind.FILE else node.file_node()
    file_path = file_n.get_field("relative_path") if file_n else None
    resolved_line = line if line is not None else node.get_field("parse_line")
    return file_path, resolved_line


# Implements: REQ-d00269-F, REQ-p00019-J, REQ-p00019-K
_REFERENCE_CHECKS: tuple[tuple[FaultClass, str, str], ...] = (
    (FaultClass.MALFORMED, "references.malformed", "does not read as a reference"),
    (
        FaultClass.UNKNOWN_NAMESPACE,
        "references.unknown_namespace",
        "no configured repository claims this identifier",
    ),
    (
        FaultClass.UNKNOWN_REQUIREMENT,
        "references.unknown_requirement",
        "claimed, but no such requirement exists",
    ),
    (
        FaultClass.UNKNOWN_ASSERTION,
        "references.unknown_assertion",
        "the requirement exists, but not that label",
    ),
    # The class covers every reference that read and resolved and whose
    # relationship is nonetheless refused -- a keyword the file kind may not
    # use, and a target the list names more than once.  The description says
    # only what is true of both; which one it was is the finding's code
    # (REQ-p00019-J, REQ-d00252-K).
    (
        FaultClass.FORBIDDEN,
        "references.forbidden",
        "resolve, but the relationship they declare is refused",
    ),
)


# Implements: REQ-d00204-E
# The two classes an unreadable repository can actually account for. A
# reference REACHES one of these by failing to find its target, which a
# missing repository explains. The other three refute the explanation on
# their own terms: MALFORMED identified no target at all, and FORBIDDEN and
# UNKNOWN_ASSERTION both resolved theirs -- so the repository owning it
# demonstrably loaded. Naming a missing repository beside any of those would
# be prose naming a cause the finding does not have, which is the defect the
# whole classification exists to remove (REQ-p00019-J, REQ-d00252-K).
_CLASSES_A_MISSING_REPO_EXPLAINS = frozenset(
    {FaultClass.UNKNOWN_NAMESPACE, FaultClass.UNKNOWN_REQUIREMENT}
)


def _unavailable_repos(graph: FederatedGraph) -> list[dict[str, str]]:
    """The configured repositories that could not be loaded, with where each
    one lives and why it failed.

    A reader who cannot resolve a reference because a repository is missing
    needs to know how to obtain it, and that belongs in the report whatever
    severity the project has chosen for the class -- severity follows the
    class a reference reached, this follows from the federation's state.

    Which reports it belongs on is decided by the caller, and REQ-d00204-E
    scopes it: the obligation attaches to a reference that fails *because*
    the repository owning its target is in an error state.
    """
    out: list[dict[str, str]] = []
    for entry in graph.iter_repos():
        if entry.graph is not None:
            continue
        out.append(
            {
                "name": entry.name,
                "path": str(entry.repo_root) if entry.repo_root else "",
                "error": entry.error or "",
            }
        )
    return sorted(out, key=lambda r: r["name"])


# Implements: REQ-d00275-A
def check_reference_class(
    graph: FederatedGraph,
    config: dict[str, Any] | None,
    fault_class: FaultClass,
    name: str,
    description: str,
) -> HealthCheck:
    """Report the faults of one class, under a description true of each.

    A fault belongs to exactly one class -- the furthest stage reading it
    reached -- so a finding appears under one check and a count of findings
    is a count of distinct facts (REQ-p00019-K).
    """
    severity = severity_for(name, config)
    if severity == Severity.OFF:
        return skipped_check(name, f"References that {description}")

    faults = [f for f in graph.broken_references() if f.fault_class is fault_class]
    unavailable = (
        _unavailable_repos(graph) if fault_class in _CLASSES_A_MISSING_REPO_EXPLAINS else []
    )
    if not faults:
        return HealthCheck(
            name=name,
            passed=True,
            message=f"No references that {description}",
            category="references",
            severity=severity,
        )
    findings = []
    for f in faults:
        codes = " ".join(c for c in f.codes if c != FaultCode.SYNTAX_ERROR)
        detail = f" [{codes}]" if codes else ""
        try:
            repo_name = graph.repo_for(f.source_id).name
        except KeyError:
            repo_name = None
        file_path, line = _fault_location(graph, f.source_id, f.line)
        findings.append(
            HealthFinding(
                message=(
                    f"{f.source_id} -> {f.target_id} ({f.edge_kind}) "
                    f"-- {f.diagnostic or description}{detail}"
                ),
                node_id=f.source_id,
                repo=repo_name,
                file_path=file_path,
                line=line,
                codes=list(f.codes),
            )
        )
    # Implements: REQ-d00204-E
    message = f"{len(faults)} reference(s): {description}"
    if unavailable:
        obtain = "; ".join(
            f"{r['name']} at {r['path']}" + (f" ({r['error']})" if r["error"] else "")
            for r in unavailable
        )
        message += f" -- a target may belong to a repository that could not be read: {obtain}"
    return HealthCheck(
        name=name,
        passed=False,
        message=message,
        category="references",
        severity=severity,
        details={
            "count": len(faults),
            "unavailable_repos": unavailable,
            "references": [
                {
                    "source": f.source_id,
                    "target": f.target_id,
                    "kind": f.edge_kind,
                    "codes": list(f.codes),
                }
                for f in faults[:20]
            ],
        },
        findings=findings,
    )


# Implements: REQ-d00272-G
def check_reference_keyword_form(
    graph: FederatedGraph, config: dict[str, Any] | None
) -> HealthCheck:
    """Report a keyword written in a non-canonical form.

    A style finding never costs the edge its keyword introduces -- it is
    reported under its own rule, at its own severity, so it can never join a
    bucket that counts references that failed to bind.
    """
    severity = severity_for("references.keyword_form", config)
    if severity == Severity.OFF:
        return skipped_check("references.keyword_form", "Keywords written in a non-canonical form")

    findings_raw = graph.style_findings()
    if not findings_raw:
        return HealthCheck(
            name="references.keyword_form",
            passed=True,
            message="No keywords written in a non-canonical form",
            category="references",
            severity=severity,
        )
    findings = []
    for sf in findings_raw:
        try:
            repo_name = graph.repo_for(sf.source_id).name
        except KeyError:
            repo_name = None
        file_path, line = _fault_location(graph, sf.source_id, sf.line)
        findings.append(
            HealthFinding(
                message=f"{sf.source_id}: {sf.code} -- keyword written in a non-canonical form",
                node_id=sf.source_id,
                repo=repo_name,
                file_path=file_path,
                line=line,
            )
        )
    return HealthCheck(
        name="references.keyword_form",
        passed=False,
        message=f"{len(findings_raw)} keyword(s) written in a non-canonical form",
        category="references",
        severity=severity,
        details={"count": len(findings_raw)},
        findings=findings,
    )


# Implements: REQ-d00272-N
def check_reference_identifier_form(
    graph: FederatedGraph, config: dict[str, Any] | None
) -> HealthCheck:
    """Report a reference spelled in a form other than the canonical one.

    The referent counterpart of ``references.keyword_form``, and it withholds
    just as little: a spelling the configuration admits produces the
    relationship it names, and that it is not the canonical spelling is a
    fact about the file rather than a reason to refuse an edge.  So it is
    reported under its own rule and can never join a check that counts
    references that failed to bind.
    """
    severity = severity_for("references.identifier_form", config)
    if severity == Severity.OFF:
        return skipped_check(
            "references.identifier_form", "References spelled in a non-canonical form"
        )

    findings_raw = graph.identifier_form_findings()
    if not findings_raw:
        return HealthCheck(
            name="references.identifier_form",
            passed=True,
            message="No references spelled in a non-canonical form",
            category="references",
            severity=severity,
        )
    findings = []
    for f in findings_raw:
        try:
            repo_name = graph.repo_for(f.source_id).name
        except KeyError:
            repo_name = None
        file_path, line = _fault_location(graph, f.source_id, f.line)
        codes = " ".join(c for c in f.codes if c != FaultCode.NON_CANONICAL_SPELLING)
        detail = f" [{codes}]" if codes else ""
        findings.append(
            HealthFinding(
                message=(
                    f"{f.text} -- spelled in a form the configuration admits but "
                    f"is not the canonical one; the relationship it names still "
                    f"holds{detail}"
                ),
                node_id=f.source_id,
                repo=repo_name,
                file_path=file_path,
                line=line,
                codes=list(f.codes),
            )
        )
    return HealthCheck(
        name="references.identifier_form",
        passed=False,
        message=f"{len(findings_raw)} reference(s) spelled in a non-canonical form",
        category="references",
        severity=severity,
        details={"count": len(findings_raw)},
        findings=findings,
    )


# Implements: REQ-d00272-O
def check_reference_undeclared(graph: FederatedGraph, config: dict[str, Any] | None) -> HealthCheck:
    """Report a comment that cites an identifier without declaring anything.

    Nothing about such a comment is malformed, so reporting it as a
    malformed reference would be wrong twice: it would name a defect its
    author does not have, and the useful message is not that something is
    broken but that saying it with a keyword would make it count.  No
    relationship is produced from it -- an informal citation is evidence of
    intent, and inferring an edge from intent is the failure the whole
    vocabulary exists to prevent.
    """
    severity = severity_for("references.undeclared", config)
    if severity == Severity.OFF:
        return skipped_check("references.undeclared", "References naming no configured repository")

    cites = graph.undeclared_relationships()
    if not cites:
        return HealthCheck(
            name="references.undeclared",
            passed=True,
            message="No comments cite a requirement without declaring a relationship",
            category="references",
            severity=severity,
        )
    findings = []
    for c in cites:
        try:
            repo_name = graph.repo_for(c.source_id).name
        except KeyError:
            repo_name = None
        file_path, line = _fault_location(graph, c.source_id, c.line)
        findings.append(
            HealthFinding(
                message=(
                    f"{c.text} -- a relationship appears to be intended and is not "
                    "declared; introduce the identifier with a Traceability keyword "
                    "(e.g. `Implements:` or `Verifies:`) for it to count"
                ),
                node_id=c.source_id,
                repo=repo_name,
                file_path=file_path,
                line=line,
            )
        )
    return HealthCheck(
        name="references.undeclared",
        passed=False,
        message=(f"{len(cites)} comment(s) cite a requirement without declaring a relationship"),
        category="references",
        severity=severity,
        details={"count": len(cites)},
        findings=findings,
    )


def check_spec_format_rules(
    graph: FederatedGraph, config: dict[str, Any], resolver: IdResolver | None = None
) -> HealthCheck:
    """Check that requirements comply with configured format rules."""
    severity = severity_for("spec.format_rules", config)
    if severity == Severity.OFF:
        return skipped_check("spec.format_rules", "Requirements that break a format rule")

    from elspais.graph import NodeKind
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
            bool(rules.allowed_statuses),  # always populated from status_roles
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
            severity=severity,
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

    severity = severity_for("spec.no_assertions", config)
    if severity == Severity.OFF:
        return skipped_check("spec.no_assertions", "Requirements with no assertions")

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
        severity=severity,
    )


# Implements: REQ-p00004
def check_spec_hash_integrity(
    graph: FederatedGraph, config: dict[str, Any] | None = None
) -> HealthCheck:
    """Flag Satisfies-linked requirements for review when their template has a stale hash.

    Stale hash detection happens at build time (parse_dirty_reasons contains
    "stale_hash"). This check adds the Satisfies annotation: when a template
    requirement is stale, any requirement that Satisfies it needs review.
    """
    severity = severity_for("spec.hash_integrity", config)
    if severity == Severity.OFF:
        return skipped_check("spec.hash_integrity", "Requirements whose stored hash does not match")

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
            severity=severity,
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
    """Check that all Active requirements have at least one changelog entry.

    Active whenever `changelog.present` is set OR `changelog.hash_current` is set.
    The latter matches `elspais fix`, which adds missing entries when hash
    tracking is enabled — keeping the check aligned with fix behavior.
    """
    severity = severity_for("spec.changelog_present", config)
    if severity == Severity.OFF:
        return skipped_check("spec.changelog_present", "Requirements with no changelog")

    from elspais.graph import NodeKind

    typed_config = _validate_config(config)
    require_present = typed_config.changelog.present or typed_config.changelog.hash_current
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
            severity=severity,
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
    severity = severity_for("spec.changelog_current", config)
    if severity == Severity.OFF:
        return skipped_check(
            "spec.changelog_current", "Changelogs that do not record the current hash"
        )

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
            severity=severity,
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
    severity = severity_for("spec.changelog_format", config)
    if severity == Severity.OFF:
        return skipped_check("spec.changelog_format", "Changelog entries that do not read")

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
            message=(f"{len(violations)} changelog entry/entries missing required fields"),
            category="spec",
            severity=severity,
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
    config: dict[str, Any] | None = None,
) -> HealthCheck:
    """Check that INDEX.md is byte-identical to what 'elspais fix' would produce."""
    severity = severity_for("spec.index_current", config)
    if severity == Severity.OFF:
        return skipped_check("spec.index_current", "A generated index that is out of date")

    from elspais.commands.index import _build_index_content, _indexed_node_ids
    from elspais.graph import NodeKind

    include_assoc = (config or {}).get("federation", {}).get("index_associates", False)

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
            message="No INDEX.md found (run 'elspais fix' to create one)",
            category="spec",
            severity="info",
        )

    _expected_path, expected, req_count, jny_count = _build_index_content(
        graph, spec_dirs, include_associates=include_assoc
    )
    actual = index_path.read_text(encoding="utf-8")

    if actual == expected:
        total = req_count + jny_count
        return HealthCheck(
            name="spec.index_current",
            passed=True,
            message=f"INDEX.md is up to date ({total} entries)",
            category="spec",
        )

    # Byte-level mismatch — still provide the legacy ID-diff breakdown for context.
    import re

    # Both grammars come from where they are defined: the repository's own
    # configuration for requirement identifiers, the canonical pattern for
    # journeys. Spelled here, this breakdown would recognise a different set
    # of identifiers than the index it is comparing against was generated
    # from, and would report every requirement missing under any namespace
    # other than the one written into the pattern.
    from elspais.config import config_defaults
    from elspais.graph.parsers.patterns import JOURNEY_REF_PATTERN
    from elspais.utilities.patterns import build_resolver

    # An empty config is not the default configuration -- it has no levels,
    # so its grammar matches no identifier at all.
    _identifier = build_resolver(config or config_defaults()).grammar().identifier
    index_req_ids = set(re.findall(_identifier, actual))
    index_jny_ids = set(JOURNEY_REF_PATTERN.findall(actual))
    graph_req_ids = _indexed_node_ids(graph, NodeKind.REQUIREMENT, include_assoc)
    graph_jny_ids = _indexed_node_ids(graph, NodeKind.USER_JOURNEY, include_assoc)

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
    if not issues:
        issues.append("content differs (titles, order, hashes, or formatting)")

    return HealthCheck(
        name="spec.index_current",
        passed=False,
        message=f"INDEX.md is stale: {', '.join(issues)}",
        category="spec",
        severity=severity,
        details={
            "missing_reqs": sorted(missing_reqs),
            "extra_reqs": sorted(extra_reqs),
            "missing_jnys": sorted(missing_jnys),
            "extra_jnys": sorted(extra_jnys),
        },
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


# Implements: REQ-d00223-A, REQ-d00223-D
def check_term_duplicates(
    duplicates: list[tuple],
    severity: str | None = None,
    config: dict[str, Any] | None = None,
) -> HealthCheck:
    """Check for duplicate term definitions."""
    severity = severity or severity_for("terms.duplicates", config)
    if severity == Severity.OFF:
        return skipped_check("terms.duplicates", "Terms defined more than once")

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


# Implements: REQ-d00223-B, REQ-d00223-D
def check_undefined_terms(
    undefined: list[dict],
    severity: str | None = None,
    config: dict[str, Any] | None = None,
) -> HealthCheck:
    """Check for *token*/**token** references without a matching definition."""
    severity = severity or severity_for("terms.undefined", config)
    if severity == Severity.OFF:
        return skipped_check("terms.undefined", "Marked terms with no definition")

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


# Implements: REQ-d00223-C, REQ-d00223-D
def check_unmarked_usage(
    unmarked: list[dict],
    severity: str | None = None,
    config: dict[str, Any] | None = None,
) -> HealthCheck:
    """Check for indexed terms used in prose without *...* or **...** markup."""
    severity = severity or severity_for("terms.unmarked", config)
    if severity == Severity.OFF:
        return skipped_check("terms.unmarked", "Defined terms used without markup")

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
        # Implements: REQ-d00223-F
        wrong = item.get("wrong_marking", "")
        if wrong:
            msg = f"Wrong markup for '{item['term']}' (uses {wrong}) in {item['node_id']}"
        else:
            msg = f"Unmarked usage of '{item['term']}' in {item['node_id']}"
        findings.append(
            HealthFinding(
                message=msg,
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


# Implements: REQ-d00240-A
def check_term_unused(
    entries: list,
    severity: str | None = None,
    config: dict[str, Any] | None = None,
) -> HealthCheck:
    """Check for defined terms with zero references."""
    severity = severity or severity_for("terms.unused", config)
    if severity == Severity.OFF:
        return skipped_check("terms.unused", "Defined terms nothing uses")

    findings = []
    for entry in entries:
        if not entry.references:
            findings.append(
                HealthFinding(
                    message=(
                        f"Unused defined term '{entry.term}' "
                        f"(defined in {entry.defined_in}:{entry.defined_at_line})"
                    ),
                    node_id=entry.defined_in,
                    line=entry.defined_at_line,
                )
            )

    if not findings:
        return HealthCheck(
            name="terms.unused",
            passed=True,
            message="No unused defined terms",
            category="terms",
            severity=severity,
        )

    return HealthCheck(
        name="terms.unused",
        passed=False,
        message=f"{len(findings)} unused defined term(s)",
        category="terms",
        severity=severity,
        findings=findings,
    )


_MIN_DEFINITION_LENGTH = 10


# Implements: REQ-d00240-B
def check_term_bad_definition(
    entries: list,
    severity: str | None = None,
    config: dict[str, Any] | None = None,
) -> HealthCheck:
    """Check for terms with blank or trivially short definitions."""
    severity = severity or severity_for("terms.bad_definition", config)
    if severity == Severity.OFF:
        return skipped_check("terms.bad_definition", "Definitions that do not read")

    findings = []
    for entry in entries:
        # Reference-type terms store structured metadata (Title, Version,
        # URL, ...) instead of prose; an empty prose definition is expected.
        if getattr(entry, "is_reference", False):
            continue
        stripped = entry.definition.strip() if entry.definition else ""
        if len(stripped) < _MIN_DEFINITION_LENGTH:
            findings.append(
                HealthFinding(
                    message=(
                        f"Term '{entry.term}' has empty/trivial definition "
                        f"({entry.defined_in}:{entry.defined_at_line})"
                    ),
                    node_id=entry.defined_in,
                    line=entry.defined_at_line,
                )
            )

    if not findings:
        return HealthCheck(
            name="terms.bad_definition",
            passed=True,
            message="No bad term definitions",
            category="terms",
            severity=severity,
        )

    return HealthCheck(
        name="terms.bad_definition",
        passed=False,
        message=f"{len(findings)} bad term definition(s)",
        category="terms",
        severity=severity,
        findings=findings,
    )


# Implements: REQ-d00240-C
def check_term_collection_empty(
    entries: list,
    severity: str | None = None,
    config: dict[str, Any] | None = None,
) -> HealthCheck:
    """Check for collection terms with zero references."""
    severity = severity or severity_for("terms.collection_empty", config)
    if severity == Severity.OFF:
        return skipped_check("terms.collection_empty", "Term collections with nothing in them")

    findings = []
    for entry in entries:
        if entry.collection and not entry.references:
            findings.append(
                HealthFinding(
                    message=(
                        f"Collection term '{entry.term}' has no references "
                        f"({entry.defined_in}:{entry.defined_at_line})"
                    ),
                    node_id=entry.defined_in,
                    line=entry.defined_at_line,
                )
            )

    if not findings:
        return HealthCheck(
            name="terms.collection_empty",
            passed=True,
            message="No empty collection terms",
            category="terms",
            severity=severity,
        )

    return HealthCheck(
        name="terms.collection_empty",
        passed=False,
        message=f"{len(findings)} empty collection term(s)",
        category="terms",
        severity=severity,
        findings=findings,
    )


def check_term_canonical_form(
    entries: list,
    severity: str | None = None,
    config: dict[str, Any] | None = None,
) -> HealthCheck:
    """Check that term references use canonical form (correct markup + casing)."""
    severity = severity or severity_for("terms.canonical_form", config)
    if severity == Severity.OFF:
        return skipped_check("terms.canonical_form", "Terms written in a non-canonical form")

    findings = []
    for entry in entries:
        canonical = entry.term
        for ref in entry.references:
            if not ref.surface_form:
                continue
            if ref.is_canonical(canonical):
                continue
            # Implements: REQ-d00237-F
            # Embedded-in-identifier occurrences are
            # references, not non-canonical prose; leave them untouched.
            if ref.embedded:
                continue
            # Non-canonical: wrong casing, wrong/missing markup, or both
            reasons = []
            if ref.surface_form != canonical:
                reasons.append(f"'{ref.surface_form}' should be '{canonical}'")
            if not ref.marked:
                if ref.wrong_marking:
                    reasons.append(f"uses '{ref.wrong_marking}' markup")
                else:
                    reasons.append("unmarked")
            detail = "; ".join(reasons)
            findings.append(
                HealthFinding(
                    message=f"Non-canonical term ref: {detail} ({ref.node_id}:{ref.line})",
                    node_id=ref.node_id,
                    line=ref.line,
                )
            )

    if not findings:
        return HealthCheck(
            name="terms.canonical_form",
            passed=True,
            message="All term references use canonical form",
            category="terms",
            severity=severity,
        )

    return HealthCheck(
        name="terms.canonical_form",
        passed=False,
        message=f"{len(findings)} non-canonical term reference(s)",
        category="terms",
        severity=severity,
        findings=findings,
    )


# Implements: REQ-d00223-E, REQ-d00240-D
def run_term_checks(
    graph: FederatedGraph, config: dict[str, Any] | None = None
) -> list[HealthCheck]:
    """Run all term health checks."""
    # Extract data from graph
    duplicates = getattr(graph, "term_duplicates", [])
    terms = getattr(graph, "terms", None)
    entries = list(terms.iter_all()) if terms else []

    # Undefined terms: emphasis-wrapped tokens not matching any definition
    undefined: list[dict] = getattr(graph, "unmatched_emphasis", [])

    # Unmarked usage: known terms used as plain text without emphasis
    unmarked: list[dict] = []
    for entry in entries:
        for ref in entry.references:
            # Implements: REQ-d00237-F
            # Occurrences embedded in a compound
            # identifier (e.g. a REQ-ID) are references, not unmarked-emphasis
            # violations.
            if ref.embedded:
                continue
            if not ref.marked and not ref.wrong_marking and not ref.delimiter:
                unmarked.append(
                    {
                        "term": entry.term,
                        "node_id": ref.node_id,
                        "line": ref.line,
                    }
                )

    return [
        check_term_duplicates(duplicates, config=config),
        check_undefined_terms(undefined, config=config),
        check_unmarked_usage(unmarked, config=config),
        check_term_unused(entries, config=config),
        check_term_bad_definition(entries, config=config),
        check_term_collection_empty(entries, config=config),
        check_term_canonical_form(entries, config=config),
    ]


# Implements: REQ-d00202-A+D+I, REQ-d00203-C
def check_associate_paths(
    config: dict[str, Any],
    repo_root: Path,
) -> HealthCheck:
    """Validate that every federated repository loads and contains spec files.

    The subject is the whole federation, not only the repositories this
    one names: a repository reached through an associate's own
    declarations contributes to the same graph, so its problems are this
    project's problems and have to be visible from here.
    """
    severity = severity_for("config.associate_paths", config)
    if severity == Severity.OFF:
        return skipped_check("config.associate_paths", "Associate repositories that cannot be read")

    from elspais.associates import discover_associate_from_path
    from elspais.graph.federation_plan import plan_federation_or_error

    plan, plan_error = plan_federation_or_error(config, repo_root)
    if plan_error is not None:
        return HealthCheck(
            name="config.associate_paths",
            passed=False,
            message="Federation membership could not be resolved",
            category="spec",
            severity=severity,
            findings=[HealthFinding(message=plan_error)],
        )

    members = plan[1:]
    if not members:
        return HealthCheck(
            name="config.associate_paths",
            passed=True,
            message="No associates configured",
            category="spec",
            severity="info",
        )

    findings: list[HealthFinding] = []
    for member in members:
        via = " -> ".join(member.declaration_path)
        if member.error is not None:
            findings.append(
                HealthFinding(
                    message=f"Associate '{member.name}' (declared via {via}): {member.error}",
                    node_id=member.name,
                )
            )
            continue

        # The planner answers whether a configuration could be loaded for
        # this directory; it does not answer whether the directory is
        # itself an elspais repository, which is what discovery decides.
        disc_result = discover_associate_from_path(member.repo_root)
        if isinstance(disc_result, str):
            findings.append(
                HealthFinding(
                    message=(
                        f"Associate '{member.name}' (declared via {via}) "
                        f"is misconfigured: {disc_result}"
                    ),
                    node_id=member.name,
                )
            )
            continue

        assoc_spec_dir = member.repo_root / disc_result.spec_path
        if not assoc_spec_dir.exists() or not any(assoc_spec_dir.glob("*.md")):
            findings.append(
                HealthFinding(
                    message=(
                        f"Associate '{member.name}' (declared via {via}) has no spec files"
                        f" in {disc_result.spec_path}"
                    ),
                    node_id=member.name,
                )
            )

    if findings:
        return HealthCheck(
            name="config.associate_paths",
            passed=False,
            message=f"{len(findings)} associate path issue(s)",
            category="spec",
            severity=severity,
            findings=findings,
        )
    return HealthCheck(
        name="config.associate_paths",
        passed=True,
        message=f"All {len(members)} federated repository path(s) valid",
        category="spec",
    )


# Implements: REQ-d00204-G
def check_no_cycles(graph: FederatedGraph, config: dict[str, Any] | None = None) -> HealthCheck:
    """Detect cycles in the requirement traceability graph.

    A cycle (a requirement reachable as its own descendant through the
    REQUIREMENT-to-REQUIREMENT edges that downstream tree/coverage walks
    follow) crashes those walks with unbounded recursion. Surface it here as
    a clear diagnostic instead. Uses an iterative colored DFS so cycle
    detection itself can never blow the stack.
    """
    severity = severity_for("spec.no_cycles", config)
    if severity == Severity.OFF:
        return skipped_check("spec.no_cycles", "Cycles in the requirement hierarchy")

    from elspais.graph import NodeKind

    def req_children(node: GraphNode) -> list[GraphNode]:
        return [c for c in node.iter_children() if c.kind == NodeKind.REQUIREMENT]

    WHITE, GREY, BLACK = 0, 1, 2
    color: dict[str, int] = {}
    findings: list[HealthFinding] = []
    seen_cycles: set[frozenset[str]] = set()

    for start in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if color.get(start.id, WHITE) != WHITE:
            continue
        # Iterative DFS. path holds the current grey chain; path_pos maps a
        # node id to its index in path so a back-edge can name the cycle.
        path: list[GraphNode] = [start]
        path_pos: dict[str, int] = {start.id: 0}
        color[start.id] = GREY
        stack: list[tuple[GraphNode, Iterator[GraphNode]]] = [(start, iter(req_children(start)))]
        while stack:
            node, children = stack[-1]
            descended = False
            for child in children:
                cstate = color.get(child.id, WHITE)
                if cstate == WHITE:
                    color[child.id] = GREY
                    path_pos[child.id] = len(path)
                    path.append(child)
                    stack.append((child, iter(req_children(child))))
                    descended = True
                    break
                if cstate == GREY:
                    # Back-edge: child..node on the current path form a cycle.
                    cycle_ids = [n.id for n in path[path_pos[child.id] :]]
                    key = frozenset(cycle_ids)
                    if key not in seen_cycles:
                        seen_cycles.add(key)
                        loop = " -> ".join([*cycle_ids, child.id])
                        findings.append(
                            HealthFinding(
                                message=f"Requirement cycle: {loop}",
                                node_id=child.id,
                                related=cycle_ids,
                            )
                        )
            if not descended:
                color[node.id] = BLACK
                path_pos.pop(node.id, None)
                path.pop()
                stack.pop()

    if findings:
        return HealthCheck(
            name="spec.no_cycles",
            passed=False,
            message=f"Found {len(findings)} requirement cycle(s)",
            category="spec",
            severity=severity,
            details={"cycle_count": len(findings)},
            findings=findings,
        )
    return HealthCheck(
        name="spec.no_cycles",
        passed=True,
        message="No requirement cycles",
        category="spec",
    )


def check_no_requirements(
    graph: FederatedGraph, config: dict[str, Any] | None = None
) -> HealthCheck:
    """Flag when no requirements are found — likely a config issue."""
    severity = severity_for("config.no_requirements", config)
    if severity == Severity.OFF:
        return skipped_check("config.no_requirements", "A project with no requirements")

    from elspais.graph import NodeKind

    req_count = sum(1 for _ in graph.nodes_by_kind(NodeKind.REQUIREMENT))
    if req_count == 0:
        return HealthCheck(
            name="config.no_requirements",
            passed=False,
            message=(
                "No requirements found. Check that spec directories"
                " contain valid requirement files."
            ),
            category="spec",
            severity=severity,
        )
    return HealthCheck(
        name="config.no_requirements",
        passed=True,
        message=f"Found {req_count} requirements",
        category="spec",
    )


# The settings the invoking repository governs for the whole federation
# (REQ-d00275-A): how a finding is judged, scored and reported. Deliberately
# not every setting under [rules] -- hierarchy and format state the rules a
# repository's own content is authored by, and those stay with that repository
# (REQ-d00204-A). Status roles sit under [rules.format] but decide how a
# requirement's status is read when reporting, so they are governed.
_GOVERNED_SETTING_ROOTS: tuple[str, ...] = (
    "rules.coverage",
    "rules.references",
    # The severity of every check that carries no named setting of its own.
    # It decides how loudly a finding is reported, which is the same question
    # the two roots above answer for the checks that do have one.
    "rules.severity",
    "rules.format.status_roles",
)


def _flatten_settings(value: Any, prefix: str) -> dict[str, Any]:
    """Dotted-key view of a config subtree, for comparing two of them.

    An empty table is a leaf, not an absence. A setting whose value is a table
    of entries is answered by "no entries" as surely as by any other value, and
    dropping it would let one side of a comparison read as unset when it is in
    fact what the run judges by.
    """
    if not isinstance(value, dict) or not value:
        return {prefix: value}
    flat: dict[str, Any] = {}
    for key, sub in value.items():
        flat.update(_flatten_settings(sub, f"{prefix}.{key}" if prefix else str(key)))
    return flat


def _governed_settings(config: dict[str, Any] | None) -> dict[str, Any]:
    """The governed settings a config holds, as dotted keys.

    Filters whatever mapping it is given; it does not fill anything in. A
    config loaded from disk arrives with the schema defaults already merged,
    so a member that declared no governed setting still carries the values it
    would have judged by, which is what the disclosure is about -- a member
    silently relying on a default the invoking project overrode would have
    reported differently on its own, and that is worth being told.
    """
    if not config:
        return {}
    flat = _flatten_settings(config, "")
    return {
        key: val
        for key, val in flat.items()
        if any(key == root or key.startswith(f"{root}.") for root in _GOVERNED_SETTING_ROOTS)
    }


# Implements: REQ-d00275-D
def check_governed_rule_divergence(
    graph: FederatedGraph, config: dict[str, Any] | None = None
) -> HealthCheck:
    """Disclose where a member configured a governed setting differently.

    The invoking repository's configuration governs how findings are judged
    and reported across the federation, which means a member is being measured
    by rules its maintainer did not choose. Where the two differ, that member's
    own repository would have reported something else, and a finding silenced
    by the invoking configuration is otherwise indistinguishable from a finding
    that was never there.

    A member reaches a differing value two ways -- by declaring it, or by
    never declaring it and keeping a default the invoking project overrode.
    Both are disclosed, because both mean the member's own run would report
    something else, which is the thing worth knowing. Neither is reported as a
    choice the member's maintainer made.

    Never a failure: differing configurations are what federated repositories
    legitimately do, so this reports and does not judge (REQ-d00275-D).
    """
    severity = severity_for("config.governed_rules", config)
    if severity == Severity.OFF:
        return skipped_check(
            "config.governed_rules", "Associate rules that diverge from this project's"
        )

    invoking = _governed_settings(config)
    findings: list[HealthFinding] = []
    for entry in graph.iter_repos():
        if entry.config is None or entry.config == config:
            continue
        member = _governed_settings(entry.config)
        for key in sorted(set(invoking) | set(member)):
            if key not in member:
                continue
            theirs = member[key]
            if key not in invoking:
                mine = "no value"
            else:
                mine = repr(invoking[key])
                if invoking[key] == theirs:
                    continue
            # "would judge by", not "sets": a config arrives with defaults
            # merged, so a member reaching this value by never declaring it is
            # indistinguishable here from one that wrote it down. What is true
            # of both is the value the member would have judged by.
            findings.append(
                HealthFinding(
                    message=(
                        f"{entry.name} would judge {key} by {theirs!r}; this run judges "
                        f"by {mine}, configured here"
                    ),
                    repo=entry.name,
                )
            )
    if not findings:
        return HealthCheck(
            name="config.governed_rules",
            passed=True,
            message="No federated member configures a governed rule differently",
            category="spec",
            severity="info",
        )
    repos = sorted({f.repo for f in findings if f.repo})
    return HealthCheck(
        name="config.governed_rules",
        passed=True,
        message=(
            f"{len(findings)} governed setting(s) across {len(repos)} member(s) differ "
            "from the configuration this run judges by"
        ),
        category="spec",
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
    # Determine repo_root from the first repo entry
    _repo_root = Path.cwd()
    for _entry in graph.iter_repos():
        if _entry.repo_root:
            _repo_root = _entry.repo_root
            break

    checks: list[HealthCheck] = [
        check_no_requirements(graph, config),
        check_governed_rule_divergence(graph, config),
        check_associate_paths(config, _repo_root),
        check_spec_files_parseable(graph, config),
        check_spec_no_duplicates(graph, config),
        *[
            check_reference_class(graph, config, fault_class, name, description)
            for fault_class, name, description in _REFERENCE_CHECKS
        ],
        check_reference_keyword_form(graph, config),
        check_reference_identifier_form(graph, config),
        check_reference_undeclared(graph, config),
        check_spec_hash_integrity(graph, config),
        check_no_cycles(graph, config),
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
                check_spec_implements_resolve(
                    repo_graph, resolver=repo_resolver, config=repo_config
                ),
                entry.name,
            )
        )
        checks.append(
            _annotate_findings(
                check_spec_refines_resolve(repo_graph, resolver=repo_resolver, config=repo_config),
                entry.name,
            )
        )
        checks.append(
            _annotate_findings(
                check_spec_satisfies_resolve(
                    repo_graph, resolver=repo_resolver, config=repo_config
                ),
                entry.name,
            )
        )
        checks.append(
            _annotate_findings(
                check_spec_needs_rewrite(repo_graph, repo_config),
                entry.name,
            )
        )
        checks.append(
            _annotate_findings(
                check_unfixable_issues(repo_graph, repo_config),
                entry.name,
            )
        )
        checks.append(
            _annotate_findings(
                check_spec_hierarchy_levels(repo_graph, repo_config),
                entry.name,
            )
        )
        checks.append(
            _annotate_findings(
                check_spec_undefined_levels(repo_graph, repo_config),
                entry.name,
            )
        )
        _typed_repo = _validate_config(repo_config)
        _allow_so = _typed_repo.rules.hierarchy.allow_structural_orphans
        checks.append(
            _annotate_findings(
                check_structural_orphans(
                    repo_graph,
                    allow_structural_orphans=_allow_so,
                    config=repo_config,
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
        checks.append(check_spec_index_current(graph, spec_dirs, config=config))

    # Post-process: downgrade checks that only have findings for retired REQs
    if retired_ids:
        _downgrade_retired_findings(checks, retired_ids)

    return checks


# =============================================================================
# Code Checks
# =============================================================================


def _status_flags(args: argparse.Namespace) -> set[str]:
    """Title-cased set of statuses named via ``--treat-active`` (empty when unset)."""
    raw: list[str] | None = getattr(args, "treat_active", None)
    return {s.title() for s in raw} if raw else set()


def _config_with_status_overlay(
    config: dict[str, Any] | None,
    status_flags: set[str],
) -> dict[str, Any] | None:
    """Config overlay forcing ``expects_implementation=True`` for --treat-active names.

    ``--treat-active Draft`` makes Draft count toward coverage (the documented
    capability, ``docs/cli/checks.md``). Rather than a second coverage-inclusion
    predicate, ``--treat-active`` is expressed as a per-call CONFIG overlay so the ONE
    resolver (``status_expects_implementation``) drives both the dimension
    COUNTS (``aggregate_dimension``) and the excluded-NOTE from the same source
    -- they can no longer disagree (REQ-d00258-C).

    Empty ``status_flags`` returns ``config`` unchanged (byte-identical default
    behaviour). Otherwise a shallow copy whose ``statuses`` table gains
    ``expects_implementation=True`` for each named status, preserving any other
    per-status fields (and composing with an existing
    ``[statuses.<S>].expects_implementation``). The input config is never
    mutated.
    """
    if not status_flags:
        return config
    overlaid = dict(config or {})
    statuses = dict(overlaid.get("statuses") or {})
    # Merge into an existing entry (case-insensitively) rather than shadowing it
    # with a second, differently-cased key that the resolver might reach first.
    existing_by_lower = {k.lower(): k for k in statuses if isinstance(k, str)}
    for flag in status_flags:
        key = existing_by_lower.get(flag.lower(), flag)
        entry = dict(statuses.get(key) or {})
        entry["expects_implementation"] = True
        statuses[key] = entry
    overlaid["statuses"] = statuses
    return overlaid


def _resolve_exclude_status(
    args: argparse.Namespace,
    config: dict[str, Any] | None = None,
) -> set[str]:
    """Statuses treated as coverage-EXCLUDED for the reference-status checks.

    This drives ``_check_status_references`` (retired/provisional/aspirational
    reference flagging): ``--treat-active Draft`` promotes Draft to active-like, so it
    is removed from this set and Draft references stop being flagged. Coverage
    COUNTS and the excluded-note no longer read this set -- they route through
    ``_config_with_status_overlay`` + ``status_expects_implementation`` so a
    single resolver keeps them consistent (REQ-d00258-C). Without ``--treat-active``,
    the role system supplies the default exclusion set.
    """
    from elspais.config import get_status_roles

    roles = get_status_roles(config or {})
    default_excluded = roles.coverage_excluded_statuses()
    return default_excluded - _status_flags(args)


def _excluded_note(
    graph: FederatedGraph,
    config: dict[str, Any] | None = None,
) -> str:
    """Note listing requirements EXCLUDED from coverage counts.

    A status is 'excluded' iff it does NOT expect implementation under the given
    config -- the SAME resolver (``status_expects_implementation``) that gates
    ``aggregate_dimension``'s counts (REQ-d00258-C). Passing the ``--treat-active``
    overlay here keeps the note and the counts in agreement: a status promoted
    by ``--treat-active`` (or by ``[statuses.<S>].expects_implementation``) is counted
    and therefore NOT listed as excluded.
    """
    from elspais.config import status_expects_implementation
    from elspais.graph import NodeKind

    counts: dict[str, int] = {}
    for n in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if n.status and not status_expects_implementation(config or {}, n.status):
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
    level_filter: Any = None,
    message_suffix: str = "",
) -> HealthCheck:
    """Check coverage for one of the 5 CoverageDimension dimensions.

    Reports the requirement-level count and the assertion-level figures, each
    naming the measure it is on (REQ-d00258-A). The headline is the
    per-*Assertion* total (REQ-d00069-N) -- each *Assertion* counted once at
    the greatest of its four measures -- and the four measures behind it are
    listed under the ONE shared vocabulary (``MEASURE_WORDS``), the same words
    `summary`, `trace` and the viewer render. The immediate direct measure
    ("cited by name here") is named first because it is what the gap surfaces
    answer on (REQ-d00258-M), so a reader can see why this check reports
    coverage while `gaps` still lists work.

    The measures are NOT nested and are not described as though they were: an
    *Assertion* can carry credit on several of them, which is why the total is
    a per-*Assertion* maximum rather than their sum. Each label therefore says
    what its own figure counts and claims no ordering against its neighbours.

    Args:
        graph: The graph to check.
        dimension: One of 'implemented', 'tested', 'verified',
                   'uat_coverage', 'uat_verified'.
        exclude_status: Vestigial; coverage inclusion is now gated entirely by
            ``config`` (the ``--treat-active`` overlay) via
            ``status_expects_implementation`` (REQ-d00258-C). Retained only for
            call-site signature stability.
        config: Project config dict (the ``--treat-active`` overlay when applicable).
        level_filter: Optional predicate ``(level) -> bool`` limiting which
            requirement levels are counted (see ``aggregate_dimension``).
        message_suffix: Optional clarifying text appended to the message.
    """
    from elspais.graph.aggregation import (
        MEASURE_WORDS,
        WORK_LIST_MEASURE,
        aggregate_dimension,
    )
    from elspais.graph.metrics import fmt_assertion_count

    dim_labels = {
        "implemented": ("Implemented", "code"),
        "tested": ("Tested", "tests"),
        "verified": ("Passing", "tests"),
        "uat_coverage": ("UAT Covered", "uat"),
        "uat_verified": ("UAT Passed", "uat"),
        "lcov_tested": ("Coverage-Verified (lcov)", "tests"),
    }
    label, category = dim_labels.get(dimension, (dimension, "code"))
    check_name = f"{category}.{dimension}"
    severity = severity_for(check_name, config)
    if severity == Severity.OFF:
        return skipped_check(check_name, f"{label} coverage failures")

    # REQ-d00258-C: whole-graph per-dimension sums + per-REQ counts (incl. the
    # REQ-d00252-F INTEGRATES exception) come from the single shared
    # aggregation module -- not a second re-implementation of the walk here.
    agg = aggregate_dimension(graph, dimension, config=config, level_filter=level_filter)
    req_count = agg.req_count
    req_with_any = agg.req_with_any  # REQs covered on the per-Assertion total
    req_with_direct = agg.req_with_direct  # REQs with immediate-direct coverage
    total_assertions = agg.total
    has_any_failures = agg.has_failures

    # Implements: REQ-d00258-A, REQ-d00069-L, REQ-d00069-N
    # The headline is the per-*Assertion* total -- the greatest of the four
    # measures per *Assertion*, so each *Assertion* is counted once however
    # many ways it is covered -- and the four measures behind it are reported
    # with it, so a reader is never shown a figure without the evidence that
    # produced it. Every figure is read from the shared aggregation rather
    # than recomputed here.
    total_covered = agg.total_covered
    measures = {
        "immediate_direct": agg.immediate_direct,
        "immediate_indirect": agg.immediate_indirect,
        "rolled_direct": agg.rolled_direct,
        "rolled_indirect": agg.rolled_indirect,
    }
    # The immediate direct measure is also the one the work-listing surfaces
    # answer on (REQ-d00258-M), so it is named first below.
    cited_assertions = measures[WORK_LIST_MEASURE]

    def _pct(value: float) -> float:
        return (value / total_assertions * 100) if total_assertions > 0 else 0.0

    req_pct = (req_with_any / req_count * 100) if req_count > 0 else 0
    cited_pct = _pct(cited_assertions)
    total_pct = _pct(total_covered)
    # REQ-d00258-C: note and counts read the SAME config (the --treat-active overlay),
    # so a promoted status is counted AND absent from the excluded-note.
    note = _excluded_note(graph, config=config)

    # Implements: REQ-d00258-A
    # Every figure says which evidence it counts, in the ONE shared vocabulary
    # (MEASURE_WORDS) the CLI summary and the viewer render, so a reader who
    # meets two surfaces meets the same words for the same quantities. The
    # requirement count is on the same total reading as the headline -- a
    # requirement is counted once any of its measures is above zero.
    msg_parts = [
        f"{label}: {req_with_any}/{req_count} REQs covered on any measure ({req_pct:.0f}%)",
        f"{fmt_assertion_count(total_covered)}/{total_assertions} assertions"
        f" covered in total ({total_pct:.0f}%)",
    ]
    # The immediate direct measure is ALWAYS shown, zero included: it is what
    # the gap surfaces answer on (REQ-d00258-M), so a zero here is exactly the
    # fact that explains why `gaps` lists work this check counts as covered.
    # The other three are shown only when they carry something.
    measure_parts = [
        f"{fmt_assertion_count(value)}/{total_assertions} {MEASURE_WORDS[name]}"
        f" ({_pct(value):.0f}%)"
        for name, value in measures.items()
        if name == WORK_LIST_MEASURE or value > 1e-9
    ]
    # The measures are independent readings of the same assertions, not parts
    # of the total: each is counted over ALL assertions, they overlap freely,
    # and they neither sum nor nest inside the total (which takes the greatest
    # per *Assertion*). "of which" claimed a partition none of that supports,
    # so the figures are introduced as the separate readings they are.
    msg_parts.append("by measure: " + ", ".join(measure_parts))
    # Implements: REQ-d00258-O
    if dimension == "tested" and (agg.tested_passed + agg.tested_failed + agg.tested_awaiting):
        msg_parts.append(
            f"{fmt_assertion_count(agg.tested_passed)} passed / "
            f"{fmt_assertion_count(agg.tested_failed)} failed / "
            f"{fmt_assertion_count(agg.tested_awaiting)} awaiting a result"
        )
    if has_any_failures:
        msg_parts.append("FAILURES DETECTED")
    message = ", ".join(msg_parts) + note + message_suffix

    return HealthCheck(
        name=check_name,
        passed=not has_any_failures,
        message=message,
        category=category,
        # A dimension with failures is what the configured severity is about;
        # with none there is nothing to report at that severity.
        severity=severity if has_any_failures else "info",
        details={
            "dimension": dimension,
            "reqs_with_any_coverage": req_with_any,
            "reqs_with_direct_coverage": req_with_direct,
            "total_requirements": req_count,
            "req_coverage_percent": round(req_pct, 1),
            "total_assertions": total_assertions,
            # Implements: REQ-d00258-A
            "cited_assertions": round(cited_assertions, 3),
            "cited_pct": round(cited_pct, 1),
            "total_covered": round(total_covered, 3),
            "total_pct": round(total_pct, 1),
            **{name: round(value, 3) for name, value in measures.items()},
            "tested_passed": agg.tested_passed,
            "tested_failed": agg.tested_failed,
            "tested_awaiting": agg.tested_awaiting,
            "has_failures": has_any_failures,
        },
    )


# Implements: REQ-d00254-B, REQ-d00258-E
def check_line_coverage(graph, config=None, level_filter=None) -> HealthCheck:
    """INFO: how much of the attributed implementation a test run executed.

    Reported in LINES, and deliberately not through the assertion-coverage
    check: line coverage measures the code, assertion coverage measures the
    *Traceability*, and putting them through one function would invite the two
    counts to be read as the same kind of number (REQ-d00254-B).

    Nothing is reported that the ingested data cannot answer. Where no coverage
    run was ingested at all there is no covered figure to give, and "0/N lines
    covered" would read as "the tests reached none of this". Where coverage
    arrives aggregate-only there is no context to attribute a line to a test,
    and a zero would read as "no test exercises this" rather than "the question
    was not asked" (REQ-d00258-E).
    """
    severity = severity_for("code.code_tested", config)
    if severity == Severity.OFF:
        return skipped_check("code.code_tested", "Line coverage")

    from elspais.graph.aggregation import aggregate_line_coverage

    agg = aggregate_line_coverage(graph, config=config, level_filter=level_filter)
    covered_pct = (agg.covered_lines / agg.total_lines * 100) if agg.total_lines else 0.0

    details: dict[str, object] = {
        "dimension": "code_tested",
        "total_lines": agg.total_lines,
        "has_measurement": agg.has_measurement,
        "has_contexts": agg.has_contexts,
        "total_requirements": agg.req_count,
    }
    # Implements: REQ-d00258-E
    # An unmeasured estate and a measured-but-unexecuted one are opposite
    # facts, so they are reported in different words rather than through the
    # same zero.
    if not agg.has_measurement:
        return HealthCheck(
            name="code.code_tested",
            passed=True,
            message=(
                f"Code Tested (line coverage): no line-coverage data ingested for"
                f" {agg.total_lines} attributed implementation lines"
                f" across {agg.req_count} REQs" + _excluded_note(graph, config=config)
            ),
            category="code",
            severity="info",
            details=details,
        )

    msg_parts = [
        f"Code Tested (line coverage): {agg.req_with_covered}/{agg.req_count}"
        f" REQs with covered implementation lines",
        f"{agg.covered_lines:.0f}/{agg.total_lines} lines covered ({covered_pct:.0f}%)",
    ]
    details.update(
        {
            "covered_lines": round(agg.covered_lines, 3),
            "covered_pct": round(covered_pct, 1),
            "reqs_with_covered_lines": agg.req_with_covered,
        }
    )
    if agg.has_attribution:
        attributed_pct = (agg.attributed_lines / agg.total_lines * 100) if agg.total_lines else 0.0
        msg_parts.append(
            f"{agg.attributed_lines:.0f}/{agg.total_lines} attributed to a"
            f" verifying test ({attributed_pct:.0f}%)"
        )
        details["attributed_lines"] = round(agg.attributed_lines, 3)
        details["attributed_pct"] = round(attributed_pct, 1)
    else:
        msg_parts.append("per-test attribution not available from this coverage data")

    return HealthCheck(
        name="code.code_tested",
        passed=True,
        message=", ".join(msg_parts) + _excluded_note(graph, config=config),
        category="code",
        severity="info",
        details=details,
    )


def check_whole_req_only_coverage(graph, config=None) -> HealthCheck:
    """INFO: assertions whose IMPLEMENTED coverage is whole-requirement-only.

    Under REQ-d00069-B/J a blanket `Implements:`/`Refines:` fully credits every
    assertion on the indirect measures. That is intended, but it must be VISIBLE:
    this reports how load-bearing the blanket references are so a team can see
    how much green rests on whole-requirement evidence. INFO severity -- never
    fails the build. (REQ-d00258.)
    """
    severity = severity_for("code.whole_req_only_coverage", config)
    if severity == Severity.OFF:
        return skipped_check(
            "code.whole_req_only_coverage", "Coverage resting on whole-requirement evidence"
        )

    from elspais.graph import NodeKind
    from elspais.graph.aggregation import WORK_LIST_MEASURE, measure_by_label

    findings: list[HealthFinding] = []
    total = 0
    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        rollup = node.get_metric("rollup_metrics")
        if rollup is None:
            continue
        dim = rollup.implemented
        # Evidence ATTACHED to this requirement, on both immediate measures
        # (REQ-d00069-L): an *Assertion* relies on whole-requirement evidence
        # when the blanket citation reaches further than any citation naming
        # it. Conducted coverage is a different fact and is not counted here --
        # the message says "whole-requirement evidence", and it must be true.
        immediate_direct = measure_by_label(dim, WORK_LIST_MEASURE)
        n = sum(
            1
            for lbl, ind in measure_by_label(dim, "immediate_indirect").items()
            if ind > immediate_direct.get(lbl, 0.0) + 1e-9
        )
        if n:
            total += n
            findings.append(
                HealthFinding(
                    message=(
                        f"{node.id}: {n} assertion(s) rely on whole-requirement "
                        f"evidence for Implemented coverage"
                    ),
                    node_id=node.id,
                )
            )
    return HealthCheck(
        name="code.whole_req_only_coverage",
        passed=True,
        message=(
            f"{total} assertion(s) across {len(findings)} requirement(s) rely "
            f"on whole-requirement evidence for Implemented coverage"
        ),
        category="code",
        severity=severity,
        findings=findings,
    )


# The display word for each end of a chain, so a finding reads in the
# vocabulary REQ-d00258-K permits, for every surface, rather than in dimension
# field names.
_DIMENSION_WORD: dict[str, str] = {
    "implemented": "Implemented",
    "tested": "Tested",
    "verified": "Passing",
    "uat_coverage": "UAT Covered",
    "uat_verified": "UAT Passed",
}

# Implements: REQ-d00274-D
# Evidence that only names an *Assertion*, against evidence that also carries a
# verdict for it. A test aimed where nothing is implemented, one that passed
# there, and one that failed there are three different things, and an author
# reading the report should not have to work out which one they have.
#
# The 'verified' row reads the same in all three states: its evidence is
# credited from a declaration rather than from a result node of its own, so no
# verdict is ever attached to the finding.
_UNCREDITED_EVIDENCE_WORD: dict[str, dict[EvidenceResult, str]] = {
    "tested": {
        EvidenceResult.NONE: "A test names",
        EvidenceResult.PASSED: "A passing test names",
        EvidenceResult.FAILED: "A failing test names",
    },
    "verified": {
        EvidenceResult.NONE: "Passing evidence names",
        EvidenceResult.PASSED: "Passing evidence names",
        EvidenceResult.FAILED: "Passing evidence names",
    },
    "uat_verified": {
        EvidenceResult.NONE: "A journey result names",
        EvidenceResult.PASSED: "A passing journey names",
        EvidenceResult.FAILED: "A failing journey names",
    },
}

# What the denominator leaving something out means, in the reader's terms: for
# one *Assertion*, and for a requirement none of whose assertions it counts.
_UNCREDITED_DENOMINATOR_WORD: dict[str, tuple[str, str]] = {
    "implemented": ("nothing implements", "nothing implements any of its assertions"),
    "tested": ("no test covers", "no test covers any of its assertions"),
    "uat_coverage": ("no journey validates", "no journey validates any of its assertions"),
}


# Implements: REQ-d00274-A, REQ-d00274-C, REQ-d00274-D, REQ-d00274-F
def check_uncredited_evidence(
    graph: FederatedGraph, config: dict[str, Any] | None = None
) -> HealthCheck:
    """Report evidence that names an *Assertion* its dimension does not count.

    Coverage dimensions are chained, so a test naming an *Assertion* nothing
    implements contributes to no answer the tool gives: the figures are
    computed without it and, until this check, nothing said it was there.
    An error by default, because the condition has only two explanations and
    both are defects -- a missing ``Implements:`` reference, or a test aimed at
    an *Assertion* it does not exercise.
    """
    from elspais.graph.aggregation import iter_uncredited_evidence

    severity = severity_for("tests.uncredited_evidence", config)
    if severity == Severity.OFF:
        return skipped_check("tests.uncredited_evidence", "Evidence that credits no coverage")

    items = iter_uncredited_evidence(graph, config)
    if not items:
        return HealthCheck(
            name="tests.uncredited_evidence",
            passed=True,
            message="No coverage evidence that credits nothing",
            category="tests",
            severity=severity,
        )

    findings = []
    for item in items:
        word = _DIMENSION_WORD.get(item.dimension, item.dimension)
        # A source is the annotation the author wrote. Line-coverage credit is
        # written nowhere, so the finding carries no location rather than the
        # requirement's own file, which is not where the evidence lives.
        # Where a verdict is what the finding reports, it is reported at the
        # test that returned it: the wording and the location must name the
        # same test, or a reader is sent to a passing test to be shown a
        # failure (REQ-p00019-J).
        located_at = item.result_source_id or (item.source_ids[0] if item.source_ids else None)
        if located_at:
            file_path, line = _fault_location(graph, located_at, None)
        else:
            file_path, line = None, None
        evidence = _UNCREDITED_EVIDENCE_WORD[item.dimension][item.result]
        one, none_of = _UNCREDITED_DENOMINATOR_WORD[item.denominator]
        if item.assertion_label is None:
            clause = (
                f"{item.requirement_id} ({len(item.labels)} assertion(s): "
                f"{', '.join(item.labels)}), and {none_of}"
            )
        else:
            clause = f"{item.requirement_id}-{item.assertion_label}, which {one}"
        findings.append(
            HealthFinding(
                message=(f"{evidence} {clause}, so it credits no {word} figure"),
                node_id=item.requirement_id,
                file_path=file_path,
                line=line,
            )
        )
    return HealthCheck(
        name="tests.uncredited_evidence",
        passed=False,
        message=(f"{len(items)} piece(s) of coverage evidence reach no coverage figure"),
        category="tests",
        severity=severity,
        details={"count": len(items)},
        findings=findings,
    )


# Implements: REQ-d00276-A, REQ-d00276-B, REQ-d00276-C, REQ-d00276-D
def check_external_tests(
    graph: FederatedGraph, config: dict[str, Any] | None = None
) -> HealthCheck:
    """Report the tests that reach no requirement, by what they returned.

    Coverage answers for requirements, so a test belonging to none is absent
    from every figure -- it runs, it passes or fails, and nothing says so. The
    two states are different problems: a failing test outside the estate is
    usually a defect in the test, and cannot be found through any requirement
    because it hangs off none; a passing one is work the estate cannot see.

    Read-only with respect to coverage: this reports a population the figures
    are not measuring, and does not move them (REQ-d00276-A).
    """
    from elspais.graph import NodeKind as NK
    from elspais.graph.aggregation import EvidenceResult, _evidence_result

    severity = severity_for("tests.external", config)
    if severity == Severity.OFF:
        return skipped_check("tests.external", "Tests that reach no requirement")

    passed: list[GraphNode] = []
    failed: list[GraphNode] = []
    awaiting: list[GraphNode] = []
    for test in graph.iter_unlinked(NK.TEST):
        verdict, _ = _evidence_result(graph, (test.id,))
        if verdict is EvidenceResult.FAILED:
            failed.append(test)
        elif verdict is EvidenceResult.PASSED:
            passed.append(test)
        else:
            awaiting.append(test)

    total = len(passed) + len(failed) + len(awaiting)
    if total == 0:
        return HealthCheck(
            name="tests.external",
            passed=True,
            message="Every test reaches a requirement",
            category="tests",
            severity="info",
        )

    # A failing test is what the configured severity is about; a passing or
    # unrun one outside the estate is disclosed, never failed on (REQ-d00276-C).
    findings = []
    for verdict_word, nodes in (
        ("failed", failed),
        ("passed", passed),
        ("awaiting a result", awaiting),
    ):
        for test in nodes:
            file_path, line = _fault_location(graph, test.id, None)
            findings.append(
                HealthFinding(
                    message=(
                        f"{test.get_label() or test.id} ({verdict_word}) reaches no requirement"
                    ),
                    node_id=test.id,
                    file_path=file_path,
                    line=line,
                )
            )
    return HealthCheck(
        name="tests.external",
        passed=not failed,
        message=(
            f"{total} test(s) reach no requirement: "
            f"{len(passed)} passed, {len(failed)} failed, {len(awaiting)} awaiting a result"
        ),
        category="tests",
        severity=severity if failed else "info",
        details={
            "passed": len(passed),
            "failed": len(failed),
            "awaiting_result": len(awaiting),
        },
        findings=findings,
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


def check_unlinked_code(graph: FederatedGraph, config: dict[str, Any] | None = None) -> HealthCheck:
    """Check for code files with no traceability markers.

    Finds FILE nodes of type CODE that were scanned but contain no
    CODE child nodes (i.e. no Implements: or Verifies: comments found).
    """
    severity = severity_for("code.unlinked", config)
    if severity == Severity.OFF:
        return skipped_check("code.unlinked", "Code nodes reaching no requirement")

    from elspais.graph import NodeKind
    from elspais.graph.GraphNode import FileType
    from elspais.graph.relations import EdgeKind

    unlinked_files = []
    for file_node in graph.iter_roots(NodeKind.FILE):
        if file_node.get_field("file_type") != FileType.CODE:
            continue
        has_code_child = any(
            child.kind == NodeKind.CODE
            for child in file_node.iter_children(edge_kinds={EdgeKind.CONTAINS})
        )
        if not has_code_child:
            unlinked_files.append(file_node.get_field("relative_path") or file_node.id)

    if unlinked_files:
        findings = [
            HealthFinding(
                message=f"No traceability markers: {f}",
                file_path=f,
            )
            for f in sorted(unlinked_files)
        ]
        return HealthCheck(
            name="code.unlinked",
            passed=False,
            message=f"{len(unlinked_files)} code file(s) with no traceability markers",
            category="code",
            severity=severity,
            details={"count": len(unlinked_files), "files": sorted(unlinked_files)[:20]},
            findings=findings,
        )

    return HealthCheck(
        name="code.unlinked",
        passed=True,
        message="All code files have traceability markers",
        category="code",
    )


def _check_status_references(
    graph: FederatedGraph,
    source_kind: Any,  # NodeKind enum value
    role: StatusRole,
    severity: str | None = None,
    exclude_status: set[str] | None = None,
    config: dict[str, Any] | None = None,
) -> HealthCheck:
    """Check for source nodes referencing requirements of a given status role.

    When --status promotes a status to active-like, it's removed from
    exclude_status. We mirror that: statuses NOT in exclude_status are
    treated as active and skip this check.

    Args:
        graph: The federated traceability graph.
        source_kind: NodeKind.CODE or NodeKind.TEST.
        role: The StatusRole to flag (RETIRED, PROVISIONAL, ASPIRATIONAL).
        severity: An explicit severity, overriding the configured one.
        exclude_status: Statuses currently excluded from coverage.
        config: The project configuration, which decides the severity.
    """
    from elspais.config import get_status_roles
    from elspais.graph import NodeKind
    from elspais.graph.edge_sets import REACHABILITY_TRACEABILITY_EDGES

    roles_cfg = get_status_roles({})
    category = "code" if source_kind == NodeKind.CODE else "tests"
    check_name = f"{category}.{role.value}_references"
    severity = severity or severity_for(check_name, config)
    if severity == Severity.OFF:
        return skipped_check(check_name, f"{category} references to {role.value} requirements")

    _TRACEABILITY_EDGES = REACHABILITY_TRACEABILITY_EDGES

    findings: list[HealthFinding] = []
    for node in graph.nodes_by_kind(source_kind):
        # Edge direction: REQ/ASSERTION -> CODE/TEST (parent links child)
        # So from CODE/TEST, look at incoming edges (parents)
        for parent in node.iter_parents(edge_kinds=_TRACEABILITY_EDGES):
            # Walk to the requirement (parent may be an assertion)
            req = parent
            if req.kind == NodeKind.ASSERTION:
                for p in req.iter_parents():
                    if p.kind == NodeKind.REQUIREMENT:
                        req = p
                        break
            if req.kind != NodeKind.REQUIREMENT:
                continue
            req_status = req.status
            # If this status was promoted by --treat-active, skip it
            if exclude_status and req_status and req_status not in exclude_status:
                continue
            if roles_cfg.role_of(req_status) != role:
                continue
            fn = node.file_node()
            findings.append(
                HealthFinding(
                    message=(
                        f"{node.id} references {req.id} (status={req_status}, role={role.value})"
                    ),
                    file_path=fn.get_field("relative_path") if fn else None,
                    line=node.get_field("parse_line"),
                    node_id=node.id,
                )
            )

    role_label = role.value
    if findings:
        return HealthCheck(
            name=check_name,
            passed=False,
            message=f"{len(findings)} {category} reference(s) to {role_label} requirements",
            category=category,
            severity=severity,
            findings=findings,
        )

    return HealthCheck(
        name=check_name,
        passed=True,
        message=f"No {category} references to {role_label} requirements",
        category=category,
    )


# Implements: REQ-d00241-A, REQ-d00241-E
def check_no_traceability(
    unlinked_files: list[str],
    severity: str | None = None,
    faulted_files: frozenset[str] | set[str] = frozenset(),
    config: dict[str, Any] | None = None,
) -> HealthCheck:
    """Check for code files with no traceability markers.

    Test files are deliberately excluded -- ``tests.unlinked``
    (``check_unlinked_tests``) already reports marker-less test files;
    including them here too would double-report the same file.

    A file whose markers produced no relationship carries markers, and
    saying it carries none sends its author to add what is already there.
    Those files are reported by the reference checks, which name what is
    actually wrong with them, and are excluded here (*faulted_files*: the
    set of file paths appearing as the ``source_id`` of any
    ``ReferenceFault``).
    """
    unlinked_files = [f for f in unlinked_files if f not in faulted_files]
    severity = severity or severity_for("code.no_traceability", config)
    if severity == Severity.OFF:
        return skipped_check("code.no_traceability", "Code files carrying no traceability marker")

    if not unlinked_files:
        return HealthCheck(
            name="code.no_traceability",
            passed=True,
            message="All code files have traceability markers",
            category="code",
            severity=severity,
        )

    findings = [
        HealthFinding(
            message=f"No traceability markers in {path}",
        )
        for path in unlinked_files
    ]

    return HealthCheck(
        name="code.no_traceability",
        passed=False,
        message=f"{len(unlinked_files)} file(s) without traceability markers",
        category="code",
        severity=severity,
        findings=findings,
    )


def run_code_checks(
    graph: FederatedGraph,
    exclude_status: set[str] | None = None,
    config: dict[str, Any] | None = None,
) -> list[HealthCheck]:
    """Run all code reference health checks."""
    from elspais.graph import NodeKind

    checks = [
        check_code_coverage(graph, exclude_status=exclude_status, config=config),
        check_unlinked_code(graph, config),
        _check_status_references(
            graph, NodeKind.CODE, StatusRole.RETIRED, exclude_status=exclude_status, config=config
        ),
        _check_status_references(
            graph,
            NodeKind.CODE,
            StatusRole.PROVISIONAL,
            exclude_status=exclude_status,
            config=config,
        ),
        _check_status_references(
            graph,
            NodeKind.CODE,
            StatusRole.ASPIRATIONAL,
            exclude_status=exclude_status,
            config=config,
        ),
        check_whole_req_only_coverage(graph, config),
    ]

    # Add line coverage only when line coverage data is present
    has_coverage = any(
        (m := node.get_metric("rollup_metrics")) is not None and m.code_tested.total_lines > 0
        for node in graph.nodes_by_kind(NodeKind.REQUIREMENT)
    )
    if has_coverage:
        checks.append(check_line_coverage(graph, config=config))

    # Implements: REQ-d00241-B, REQ-d00241-C
    unlinked_files = []
    for node in graph.iter_unlinked(NodeKind.CODE):
        file_n = node.file_node()
        if file_n:
            rel = file_n.get_field("relative_path")
            if rel:
                unlinked_files.append(rel)
    # Implements: REQ-d00241-E
    faulted_files = {
        path
        for f in graph.broken_references()
        if (path := _fault_location(graph, f.source_id, f.line)[0]) is not None
    }
    checks.append(check_no_traceability(unlinked_files, faulted_files=faulted_files, config=config))

    return checks


def run_checks(graph: FederatedGraph, config: dict[str, Any] | None = None) -> list[HealthCheck]:
    """Run the spec and code health checks together, as a flat list.

    A thin combiner over ``run_spec_checks``/``run_code_checks`` for callers
    that want both families from one call without resolving spec
    directories themselves.
    """
    checks = list(run_spec_checks(graph, config or {}))
    checks.extend(run_code_checks(graph, config=config))
    return checks


# =============================================================================
# Test Checks
# =============================================================================


def _read_run_meta(config: dict | None) -> dict:
    """Return test-run metadata defaults.

    The run-metadata sidecar config source was removed in the greenfield
    target-driven rework; this now always returns the defaults.
    """
    return {"deselected_count": 0, "runner": ""}


def _collect_file_mtimes(
    graph: FederatedGraph,
    file_types: set,
) -> list[float]:
    """Collect on-disk mtimes for FILE nodes of the given types.

    Files missing from disk are silently skipped.
    """
    from elspais.graph import NodeKind

    mtimes: list[float] = []
    for node in graph.nodes_by_kind(NodeKind.FILE):
        ft = node.get_field("file_type", None)
        if ft not in file_types:
            continue
        abs_path = node.get_field("absolute_path", None)
        if not abs_path:
            continue
        try:
            mtimes.append(Path(abs_path).stat().st_mtime)
        except OSError:
            continue
    return mtimes


# Implements: REQ-d00275-C
def _configured_test_targets(graph: FederatedGraph, config: dict | None) -> list[tuple[str, Any]]:
    """``(repo name, target)`` for every federation member configuring one.

    Where its test results live is a fact about a repository, not a rule the
    invoking project gets to answer on its behalf: reading only the invoking
    config describes a federation whose associate configures targets as having
    none, and sends the reader looking for a missing configuration instead of
    missing results. Over a lone repository this reads that repository's own
    config, so the answer is unchanged.

    The invoking config is one of those members and is counted once, through
    whichever it is. It is read separately only when the federation does not
    hold it -- no member declares it, or no member carries a config at all.
    """
    targets: list[tuple[str, Any]] = []
    held = False
    for entry in graph.iter_repos():
        if entry.config is None:
            continue
        held = held or entry.config == config
        member = _validate_config(entry.config)
        targets.extend((entry.name, t) for t in member.scanning.test.targets)
    if config and not held:
        targets.extend(("", t) for t in _validate_config(config).scanning.test.targets)
    return targets


def check_test_results(graph: FederatedGraph, config: dict | None = None) -> HealthCheck:
    """Check test result status from JUnit/pytest output.

    Returns one of:
    - ``tests.results`` severity=info, passed=True -- no patterns configured.
    - ``tests.results`` severity=warning, passed=False -- patterns configured
      but no matching files on disk. Flips exit code unless ``--lenient``.
    - ``tests.results`` severity=warning, passed=False -- some tests failed.
    - ``tests.results`` severity=info, passed=True -- all tests passing.

    Staleness is reported as a separate :func:`check_test_results_stale` check
    so consumers can key off the ``tests.results_stale`` name.
    """
    severity = severity_for("tests.results", config)
    if severity == Severity.OFF:
        return skipped_check("tests.results", "Test results that failed or are absent")

    from elspais.graph import NodeKind

    result_nodes = list(graph.nodes_by_kind(NodeKind.RESULT))
    run_meta = _read_run_meta(config)
    deselected = run_meta["deselected_count"]

    if not result_nodes:
        targets = _configured_test_targets(graph, config)
        if not targets:
            return HealthCheck(
                name="tests.results",
                passed=True,
                message="No test targets configured",
                category="tests",
                severity="info",
            )
        repos = sorted({name for name, _ in targets if name})
        where = f" across {len(repos)} repositories" if len(repos) > 1 else ""
        return HealthCheck(
            name="tests.results",
            passed=False,
            message=(
                f"Test targets configured ({len(targets)}){where} but no results ingested. "
                "Run `elspais checks --run-tests` or refresh manually."
            ),
            category="tests",
            severity=severity,
        )

    # Tally
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
            severity=severity,
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
        severity="info",
        details={
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "deselected": deselected,
            "pass_rate": round(pass_rate, 1),
        },
    )


def check_test_results_stale(
    graph: FederatedGraph, config: dict[str, Any] | None = None
) -> HealthCheck:
    """Emit ``tests.results_stale`` warning when result mtimes lag source mtimes.

    Returns:
        ``tests.results_stale`` severity=info, passed=True -- results are
        fresh or no result files exist (a missing-results report is the job
        of :func:`check_test_results`).

        ``tests.results_stale`` severity=warning, passed=False -- oldest
        result file mtime is earlier than the newest scanned spec/code/test
        file mtime. Flips exit code unless ``--lenient``.
    """
    severity = severity_for("tests.results_stale", config)
    if severity == Severity.OFF:
        return skipped_check("tests.results_stale", "Test results older than the code they cover")

    from datetime import datetime

    from elspais.graph.GraphNode import FileType

    result_mtimes = _collect_file_mtimes(graph, {FileType.RESULT})
    source_mtimes = _collect_file_mtimes(graph, {FileType.SPEC, FileType.CODE, FileType.TEST})

    if not result_mtimes or not source_mtimes:
        return HealthCheck(
            name="tests.results_stale",
            passed=True,
            message="Result freshness not evaluated (no results or no scanned sources)",
            category="tests",
            severity="info",
        )

    if min(result_mtimes) >= max(source_mtimes):
        return HealthCheck(
            name="tests.results_stale",
            passed=True,
            message="Test results are up to date",
            category="tests",
            severity="info",
        )

    oldest_result = datetime.fromtimestamp(min(result_mtimes)).isoformat(timespec="seconds")
    newest_source = datetime.fromtimestamp(max(source_mtimes)).isoformat(timespec="seconds")
    return HealthCheck(
        name="tests.results_stale",
        passed=False,
        message=(
            f"Test results are stale -- oldest result mtime {oldest_result} "
            f"is earlier than newest scanned source mtime {newest_source}. "
            f"Re-run with `elspais checks --run-tests` to refresh."
        ),
        category="tests",
        severity=severity,
    )


def check_test_coverage(
    graph: FederatedGraph,
    exclude_status: set[str] | None = None,
    config: dict[str, Any] | None = None,
) -> HealthCheck:
    """Check test coverage — delegates to dimension check for 'tested'."""
    return check_dimension_coverage(graph, "tested", exclude_status=exclude_status, config=config)


# Implements: REQ-d00258-F
def check_uat_coverage(
    graph: FederatedGraph,
    exclude_status: set[str] | None = None,
    config: dict[str, Any] | None = None,
) -> HealthCheck:
    """Check UAT coverage — delegates to dimension check for 'uat_coverage'.

    Only requirements whose level ``expects_validation`` are considered:
    non-expecting levels (the default) contribute to neither numerator nor
    denominator. When no level expects validation the check passes trivially
    (nothing to validate).
    """
    from elspais.config import level_expects_validation

    if severity_for("uat.uat_coverage", config) == Severity.OFF:
        return skipped_check("uat.uat_coverage", "UAT Covered coverage failures")

    cfg = config or {}
    levels = cfg.get("levels") if isinstance(cfg, dict) else None
    any_expects = isinstance(levels, dict) and any(
        level_expects_validation(cfg, key) for key in levels
    )
    if not any_expects:
        return HealthCheck(
            name="uat.uat_coverage",
            passed=True,
            message="UAT Covered: no levels expect validation (expects_validation)",
            category="uat",
            severity="info",
            details={"dimension": "uat_coverage", "expects_validation_levels": 0},
        )

    def level_filter(level: str | None) -> bool:
        return level_expects_validation(cfg, level)

    check = check_dimension_coverage(
        graph,
        "uat_coverage",
        exclude_status=exclude_status,
        config=config,
        level_filter=level_filter,
        message_suffix=" (expects_validation levels only)",
    )

    # An expects_validation requirement lacking UAT coverage is a real gap:
    # collect those reqs as findings and fail the check (REQ-d00258-F). The
    # dimension sums come from check_dimension_coverage; this only identifies
    # WHICH reqs are uncovered (no re-implementation of the sum walk).
    from elspais.config import status_expects_implementation
    from elspais.graph import NodeKind
    from elspais.graph.aggregation import work_verdict
    from elspais.graph.relations import EdgeKind

    # REQ-d00258-C: the uncovered-findings walk gates on the SAME coverage
    # inclusion resolver as ``aggregate_dimension`` above, so the sums and the
    # findings list stay consistent (both count a status iff it expects
    # implementation). Behavior-preserving for default config.
    uncovered: list[HealthFinding] = []
    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if not status_expects_implementation(cfg, node.status) or not level_filter(node.level):
            continue
        rollup = node.get_metric("rollup_metrics")
        # Implements: REQ-d00258-C, REQ-d00258-M
        # The verdict is ``work_verdict``, the same one ``gaps unvalidated``
        # reaches, so the two cannot disagree about a requirement: a blanket
        # journey used to satisfy this check while gaps listed the assertions
        # it named none of.
        labels = [
            child.get_field("label", "")
            for child in node.iter_children(edge_kinds={EdgeKind.STRUCTURES})
            if child.kind == NodeKind.ASSERTION
        ]
        verdict = work_verdict(rollup, "uat_coverage", labels)
        if not verdict.attached:
            uncovered.append(
                HealthFinding(
                    message=(
                        f"{node.id}: no journey names this requirement or any of "
                        f"its assertions -- UAT coverage conducted from a refining "
                        f"requirement is not validation of this one "
                        f"(level expects_validation)"
                    ),
                    node_id=node.id,
                )
            )
        elif verdict.needs_work:
            named = ", ".join(sorted(verdict.uncovered))
            uncovered.append(
                HealthFinding(
                    message=(
                        f"{node.id}: a journey names this requirement but not "
                        f"assertion(s) {named} (level expects_validation)"
                    ),
                    node_id=node.id,
                )
            )

    # A dimension the project turned off reports nothing, and an uncovered
    # expects_validation requirement is one of the things it turned off: the
    # skip stands rather than being overwritten here.
    if uncovered and not check.details.get("skipped"):
        check.passed = False
        # The severity of a SECOND condition reported under this check's name:
        # an expects_validation requirement a journey names without naming its
        # assertions. It is not the dimension's own failure severity, so it is
        # not the one `severity_for` resolves -- separating the two conditions
        # into two names is what REQ-d00285-F asks for and is not yet done.
        check.severity = "warning"
        check.findings = uncovered
        check.details["uncovered_expects_validation"] = [f.node_id for f in uncovered]
    return check


# Implements: REQ-d00241-D
def check_unlinked_tests(
    graph: FederatedGraph, config: dict[str, Any] | None = None
) -> HealthCheck:
    """Check for test files with no traceability markers.

    Flags FILE nodes of type TEST that either contain no TEST child
    nodes at all, or contain TEST children none of which link to any
    requirement. The second condition is essential: the parser emits a
    TEST node for every discovered test function whether or not it
    carries a Verifies: marker, so a fully marker-less test file still
    has TEST children. Files with at least one linked test are not
    flagged (partial marking is not "unlinked").
    """
    severity = severity_for("tests.unlinked", config)
    if severity == Severity.OFF:
        return skipped_check("tests.unlinked", "Test nodes reaching no requirement")

    from elspais.graph import NodeKind
    from elspais.graph.GraphNode import FileType
    from elspais.graph.relations import EdgeKind

    unlinked_files = []
    for file_node in graph.iter_roots(NodeKind.FILE):
        if file_node.get_field("file_type") != FileType.TEST:
            continue
        has_linked_test = any(
            graph.is_reachable_to_requirement(child)
            for child in file_node.iter_children(edge_kinds={EdgeKind.CONTAINS})
            if child.kind == NodeKind.TEST
        )
        if not has_linked_test:
            unlinked_files.append(file_node.get_field("relative_path") or file_node.id)

    if unlinked_files:
        findings = [
            HealthFinding(
                message=f"No traceability markers: {f}",
                file_path=f,
            )
            for f in sorted(unlinked_files)
        ]
        return HealthCheck(
            name="tests.unlinked",
            passed=False,
            message=f"{len(unlinked_files)} test file(s) with no traceability markers",
            category="tests",
            severity=severity,
            details={"count": len(unlinked_files), "files": sorted(unlinked_files)[:20]},
            findings=findings,
        )

    return HealthCheck(
        name="tests.unlinked",
        passed=True,
        message="All test files have traceability markers",
        category="tests",
    )


def check_uat_results(graph: FederatedGraph, config: dict[str, Any] | None = None) -> HealthCheck:
    """Check UAT results from a journey results CSV file.

    Expects a CSV file with columns: journey_id, status (pass/fail/skip).
    The file path is configured via scanning.journey.results_file in .elspais.toml,
    defaulting to 'uat-results.csv' in the repository root.
    """
    severity = severity_for("uat.results", config)
    if severity == Severity.OFF:
        return skipped_check("uat.results", "Journey results that failed or are absent")

    cfg = config or {}
    journey_cfg = cfg.get("scanning", {}).get("journey", {})
    results_file = journey_cfg.get("results_file", "uat-results.csv")

    results_path = Path(results_file)
    if not results_path.is_absolute():
        # Relative to the repository being checked, which the graph knows.
        # This used to read a `_git_root` key out of the configuration --
        # a key no configuration file can carry and only a test ever wrote,
        # so in use the branch never ran and the path resolved against the
        # working directory instead of the repository.
        repo_root = getattr(graph, "repo_root", None)
        if repo_root:
            results_path = Path(repo_root) / results_path
        elif not results_path.exists():
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
            severity=severity,
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
            severity=severity,
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


# Implements: REQ-d00284-C
def check_unmatched_results(
    graph: FederatedGraph, config: dict[str, Any] | None = None
) -> HealthCheck:
    """Report results that matched no test.

    A result matching nothing is not an error where it happens: the parse
    succeeded, the file was read, and the only trace is a coverage figure lower
    than expected. Saying whether a result's recorded name picked out no test
    or more than one tells an author which problem they have -- a name pointing
    at a file that is not there, or two files sharing one name.
    """
    severity = severity_for("tests.unmatched_results", config)
    if severity == Severity.OFF:
        return skipped_check("tests.unmatched_results", "Results matching no known test")

    from elspais.graph import EdgeKind, NodeKind

    findings = []
    for result in graph.nodes_by_kind(NodeKind.RESULT):
        # A YIELDS edge is built as ``test.link(result)``, so the test is the
        # RESULT's parent: a result that matched a test has one.
        if any(True for _ in result.iter_parents(edge_kinds={EdgeKind.YIELDS})):
            continue
        if result.get_field("match") == "aggregate":
            continue  # an aggregate result names no test and never matches one
        target = result.get_field("target") or "?"
        recorded = result.get_field("classname") or result.get_field("name") or result.id
        candidates = result.get_field("name_candidates") or []
        if candidates:
            detail = f"matched {len(candidates)} tests: {', '.join(candidates)}"
        else:
            detail = "matched no test"
        findings.append(
            HealthFinding(
                message=(f"target {target!r}: result named {recorded!r} {detail}"),
                node_id=result.id,
                file_path=result.get_field("result_file"),
                line=result.get_field("result_line"),
                related=list(candidates),
            )
        )

    if not findings:
        return HealthCheck(
            name="tests.unmatched_results",
            passed=True,
            message="Every ingested result matched a test",
            category="tests",
            severity=severity,
        )
    return HealthCheck(
        name="tests.unmatched_results",
        passed=False,
        message=f"{len(findings)} ingested result(s) matched no test",
        category="tests",
        severity=severity,
        details={"count": len(findings)},
        findings=findings,
    )


def run_test_checks(
    graph: FederatedGraph,
    exclude_status: set[str] | None = None,
    config: dict | None = None,
) -> list[HealthCheck]:
    """Run all test file health checks."""
    from elspais.graph import NodeKind

    return [
        check_test_coverage(graph, exclude_status=exclude_status, config=config),
        check_dimension_coverage(graph, "verified", exclude_status=exclude_status, config=config),
        check_uncredited_evidence(graph, config),
        check_unlinked_tests(graph, config),
        check_external_tests(graph, config),
        check_test_results(graph, config=config),
        check_test_results_stale(graph, config),
        check_unmatched_results(graph, config),
        _check_status_references(
            graph, NodeKind.TEST, StatusRole.RETIRED, exclude_status=exclude_status, config=config
        ),
        _check_status_references(
            graph,
            NodeKind.TEST,
            StatusRole.PROVISIONAL,
            exclude_status=exclude_status,
            config=config,
        ),
        _check_status_references(
            graph,
            NodeKind.TEST,
            StatusRole.ASPIRATIONAL,
            exclude_status=exclude_status,
            config=config,
        ),
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
        # REQ-d00258-C: --treat-active becomes a coverage-config overlay so
        # dimension counts AND the excluded-note agree (both read this overlay).
        cov_config = _config_with_status_overlay(raw_config, _status_flags(args))
        for check in run_code_checks(graph, exclude_status=exclude_status, config=cov_config):
            report.add(check)
        for check in run_test_checks(graph, exclude_status=exclude_status, config=cov_config):
            report.add(check)
        for check in run_uat_checks(graph, exclude_status=exclude_status, config=cov_config):
            report.add(check)
        for check in run_term_checks(graph, config=raw_config):
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
    terms_only = params.get("terms_only", "false") == "true"
    lenient = params.get("lenient", "false") == "true"

    report = HealthReport()
    run_all = not any([spec_only, code_only, tests_only, terms_only])

    # Build a minimal args namespace for _resolve_exclude_status
    fake_args = argparse.Namespace()
    treat_str = params.get("treat_active", None)
    fake_args.treat_active = treat_str.split(",") if treat_str else None
    exclude_status = _resolve_exclude_status(fake_args, config=config)
    # REQ-d00258-C: --treat-active overlay drives coverage counts + note consistently.
    cov_config = _config_with_status_overlay(config, _status_flags(fake_args))

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
        for check in run_code_checks(graph, exclude_status=exclude_status, config=cov_config):
            report.add(check)

    # Test checks
    if run_all or tests_only:
        for check in run_test_checks(graph, exclude_status=exclude_status, config=cov_config):
            report.add(check)

    # UAT checks
    if run_all or tests_only:
        for check in run_uat_checks(graph, exclude_status=exclude_status, config=cov_config):
            report.add(check)

    # Term checks
    if run_all or terms_only:
        for check in run_term_checks(graph, config=config):
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
                codes=f.get("codes", []),
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
                remedy=c.get("remedy", ""),
            )
        )
    return report


def run(args: argparse.Namespace) -> int:
    """Run the health command.

    If --run-tests is set, execute configured targets first, then proceed
    to checks. With --fail-fast, a failing target skips the checks pass
    entirely. Final exit code is non-zero if any target failed OR any
    check failed.
    """
    from elspais.commands import _engine
    from elspais.commands.test_runner import run_configured_targets
    from elspais.config import find_git_root, get_config

    # A narrowing naming something the vocabulary does not admit selects
    # nothing while looking like it selected something, so it is refused
    # before the run rather than reported as a clean report (REQ-d00282-F).
    unadmitted = FindingFilter.from_args(args).unadmitted()
    if unadmitted:
        for problem in unadmitted:
            print(f"error: {problem}", file=sys.stderr)
        return 2

    run_tests = getattr(args, "run_tests", False)
    fail_fast = getattr(args, "fail_fast", False)

    runner_failed = False
    skip_due_to_fail_fast = False

    if run_tests:
        config_path = getattr(args, "config", None)
        try:
            cfg_dict = get_config(config_path, start_path=Path.cwd())
        except Exception as exc:
            print(f"error: failed to load config: {exc}", file=sys.stderr)
            return 2
        # _validate_config is defined in this module (health.py near line 35).
        cfg = _validate_config(cfg_dict)
        selected = getattr(args, "targets", None)
        target_names = {t.name for t in cfg.scanning.test.targets}
        if selected:
            unknown = sorted(set(selected) - target_names)
            if unknown:
                print(
                    f"error: unknown --targets: {', '.join(unknown)}. "
                    f"Configured targets: {', '.join(sorted(target_names))}.",
                    file=sys.stderr,
                )
                return 2
        # Implements: REQ-d00283-D+E+H+I
        # One authority resolves both selectors; None means every configured
        # target, which is what keeps a project declaring no groups rendering
        # exactly as it did before (REQ-d00254-J).
        from elspais.config import selected_targets

        try:
            only = selected_targets(cfg, selected or None, getattr(args, "groups", None) or None)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        commandful = [
            t for t in cfg.scanning.test.targets if t.command and (only is None or t.name in only)
        ]
        if not commandful:
            print(
                "error: --run-tests requires at least one "
                "[[scanning.test.targets]] entry with a command field "
                "(within the selected --targets/--groups when given; a run "
                "naming neither executes the `default` group). "
                "See docs/cli/test-targets.md for configuration examples.",
                file=sys.stderr,
            )
            return 2
        repo_root = find_git_root() or Path.cwd()
        results, captured_map = run_configured_targets(
            cfg, repo_root, fail_fast=fail_fast, only=only
        )
        runner_failed = any(r.returncode != 0 for r in results)
        args._captured_results = captured_map
        # Implements: REQ-d00254-I
        args._fresh_targets = only
        if fail_fast and runner_failed:
            skip_due_to_fail_fast = True

    if skip_due_to_fail_fast:
        print(
            "\nfail-fast: skipping checks due to runner failure.",
            file=sys.stderr,
        )
        return 1

    # Build params from args
    params: dict[str, str] = {}
    if getattr(args, "spec_only", False):
        params["spec_only"] = "true"
    if getattr(args, "code_only", False):
        params["code_only"] = "true"
    if getattr(args, "tests_only", False):
        params["tests_only"] = "true"
    if getattr(args, "terms_only", False):
        params["terms_only"] = "true"
    if getattr(args, "lenient", False):
        params["lenient"] = "true"
    treat_active = getattr(args, "treat_active", None)
    if treat_active:
        params["treat_active"] = ",".join(treat_active)

    spec_dir = getattr(args, "spec_dir", None)
    # Force fresh build when runners just produced new result files.
    skip_daemon = bool(spec_dir) or run_tests

    if skip_daemon:
        data = _run_local_checks(args, params)
    else:
        data = _engine.call(
            "/api/run/checks",
            params,
            compute_checks,
            config_path=getattr(args, "config", None),
        )

    healthy = data.get("healthy", False)
    graph_source = _format_graph_source(data.get("graph_source"))
    report = _report_from_dict(data)
    print(_format_report(report, args, graph_source=graph_source))
    checks_exit = 0 if healthy else 1
    return 1 if (runner_failed or checks_exit != 0) else 0


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
    captured = getattr(args, "_captured_results", None)
    fresh_targets = getattr(args, "_fresh_targets", None)

    report = HealthReport()

    run_all = not any(
        [
            params.get("spec_only") == "true",
            params.get("code_only") == "true",
            params.get("tests_only") == "true",
            params.get("terms_only") == "true",
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
            captured_results=captured,
            fresh_targets=fresh_targets,
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


# Implements: REQ-d00285-C+G
@dataclass(frozen=True)
class FindingFilter:
    """A narrowing of a report over the fields every finding carries.

    Values named for one field are alternatives and values named for
    different fields are conditions met at once -- the same reading a scope
    over requirements takes (REQ-d00278-E+D), so a reader who has narrowed one
    report knows how to narrow the other.

    `severities` and `categories` select CHECKS: severity and category are
    properties of the check a finding belongs to, and a check they exclude is
    withheld whole. `codes` and `paths` select FINDINGS within the checks that
    survive, and a check left holding none of them is withheld with them. The
    flag spelling `paths` is read from is `--file`: `--path` already names the
    repository root a run works from.
    """

    severities: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()
    codes: tuple[str, ...] = ()
    paths: tuple[str, ...] = ()

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> FindingFilter:
        def _get(name: str) -> tuple[str, ...]:
            value = getattr(args, name, None)
            return tuple(value) if value else ()

        return cls(
            severities=_get("severity"),
            categories=_get("category"),
            codes=_get("code"),
            paths=_get("file"),
        )

    @property
    def active(self) -> bool:
        return bool(self.severities or self.categories or self.codes or self.paths)

    @property
    def narrows_findings(self) -> bool:
        """Whether the filter selects among findings rather than among checks.

        A reader who named a code or a path asked for those findings by name,
        so they are rendered whether or not the report as a whole is verbose.
        """
        return bool(self.codes or self.paths)

    def unadmitted(self) -> list[str]:
        """The names this filter uses that the report's vocabulary does not admit.

        Severities and categories are the tool's own vocabulary, identical in
        every project, so a name among them that does not resolve is a mistake
        rather than a difference -- and a report narrowed by a name that
        selects nothing looks exactly like a report with nothing to say
        (REQ-d00282-F). Codes and paths are values the estate carries rather
        than a fixed list, so they are not judged here.
        """
        problems = []
        for value in self.severities:
            if value not in REPORTED_SEVERITIES:
                problems.append(
                    f"--severity {value}: not a severity. "
                    f"Severities: {', '.join(REPORTED_SEVERITIES)}."
                )
        for value in self.categories:
            if value not in REPORT_CATEGORIES:
                problems.append(
                    f"--category {value}: not a category. "
                    f"Categories: {', '.join(REPORT_CATEGORIES)}."
                )
        return problems

    def matches_check(self, check: HealthCheck) -> bool:
        if self.severities and check.severity not in self.severities:
            return False
        if self.categories and check.category not in self.categories:
            return False
        return True

    def matches_finding(self, finding: HealthFinding) -> bool:
        from fnmatch import fnmatch

        if self.codes and not any(c in self.codes for c in finding.codes):
            return False
        if self.paths:
            path = finding.file_path or ""
            if not any(fnmatch(path, pattern) for pattern in self.paths):
                return False
        return True

    def describe(self) -> str:
        """The filter as the flags that produced it, for echoing back."""
        parts: list[str] = []
        for flag, values in (
            ("--severity", self.severities),
            ("--category", self.categories),
            ("--code", self.codes),
            ("--file", self.paths),
        ):
            if values:
                parts.append(f"{flag} {' '.join(values)}")
        return " ".join(parts)


@dataclass(frozen=True)
class _FilterOutcome:
    """A narrowed report, and what the narrowing withheld."""

    report: HealthReport
    checks_shown: int
    checks_total: int
    findings_shown: int
    findings_total: int
    filter: FindingFilter

    def disclosure(self) -> str | None:
        if not self.filter.active:
            return None
        return (
            f"Filtered by {self.filter.describe()}: showing "
            f"{self.checks_shown} of {self.checks_total} checks, "
            f"{self.findings_shown} of {self.findings_total} findings."
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": list(self.filter.severities),
            "category": list(self.filter.categories),
            "code": list(self.filter.codes),
            "file": list(self.filter.paths),
            "checks_shown": self.checks_shown,
            "checks_total": self.checks_total,
            "findings_shown": self.findings_shown,
            "findings_total": self.findings_total,
        }


# Implements: REQ-d00285-G
def apply_finding_filter(report: HealthReport, filt: FindingFilter) -> _FilterOutcome:
    """Narrow a report to the checks and findings a filter admits.

    The verdict is NOT recomputed from what survives: a reader narrowing a
    report is choosing what to look at, never what the run found, and an exit
    code that moved with the filter would let a narrowing pass a run that
    failed.
    """
    checks_total = len(report.checks)
    findings_total = sum(len(c.findings) for c in report.checks)
    if not filt.active:
        return _FilterOutcome(
            report=report,
            checks_shown=checks_total,
            checks_total=checks_total,
            findings_shown=findings_total,
            findings_total=findings_total,
            filter=filt,
        )

    narrowed = HealthReport()
    findings_shown = 0
    for check in report.checks:
        if not filt.matches_check(check):
            continue
        kept = [f for f in check.findings if filt.matches_finding(f)]
        if filt.narrows_findings and not kept:
            continue
        findings_shown += len(kept)
        narrowed.add(
            HealthCheck(
                name=check.name,
                passed=check.passed,
                message=check.message,
                category=check.category,
                severity=check.severity,
                details=check.details,
                findings=kept,
                remedy=check.remedy,
            )
        )
    return _FilterOutcome(
        report=narrowed,
        checks_shown=len(narrowed.checks),
        checks_total=checks_total,
        findings_shown=findings_shown,
        findings_total=findings_total,
        filter=filt,
    )


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

    # The narrowing is applied once, here, so every format renders the same
    # narrowed report (REQ-d00285-C) and no renderer has to know a filter
    # exists. The verdict is still the whole run's -- see `apply_finding_filter`.
    outcome = apply_finding_filter(report, FindingFilter.from_args(args))
    whole_run = report
    report = outcome.report
    disclosure = outcome.disclosure()
    # A reader who named a code or a path asked for those findings by name.
    show_findings = verbose or outcome.filter.narrows_findings

    # Build active flags summary from args
    flag_parts: list[str] = []
    treat_active_list = getattr(args, "treat_active", None)
    if treat_active_list:
        flag_parts.append("--treat-active " + " ".join(treat_active_list))
    if getattr(args, "lenient", False):
        flag_parts.append("--lenient")
    if getattr(args, "spec_only", False):
        flag_parts.append("--spec")
    if getattr(args, "code_only", False):
        flag_parts.append("--code-checks")
    if getattr(args, "tests_only", False):
        flag_parts.append("--tests")
    if getattr(args, "terms_only", False):
        flag_parts.append("--terms")
    if outcome.filter.active:
        flag_parts.append(outcome.filter.describe())
    active_flags = ", ".join(flag_parts) if flag_parts else None

    from elspais.utilities.report_meta import report_metadata

    meta = report_metadata()

    if fmt == "json":
        d = report.to_dict(lenient=lenient)
        d["meta"] = meta
        if outcome.filter.active:
            # The verdict and its counts are the whole run's; only the checks
            # listed are narrowed, and the filter block says by how much.
            verdict = whole_run.to_dict(lenient=lenient)
            d["healthy"] = verdict["healthy"]
            d["summary"] = verdict["summary"]
            d["filter"] = outcome.to_dict()
        return json.dumps(d, indent=2)
    elif fmt == "markdown":
        data = _build_report_data(
            report,
            verbose=show_findings,
            include_passing_details=include_passing,
            disclosure=disclosure,
            verdict_report=whole_run,
        )
        data.graph_source = graph_source
        data.active_flags = active_flags
        data.meta = meta
        return _render_markdown(data)
    elif fmt == "junit":
        return _render_junit(report, include_passing_details=include_passing)
    elif fmt == "sarif":
        return _render_sarif(report, verdict=whole_run)
    else:
        if quiet:
            return _build_summary_line(whole_run)
        data = _build_report_data(
            report,
            verbose=show_findings,
            include_passing_details=include_passing,
            disclosure=disclosure,
            verdict_report=whole_run,
        )
        data.graph_source = graph_source
        data.active_flags = active_flags
        data.meta = meta
        return _render_text(data)


# =============================================================================
# Report Data Intermediate Representation
# =============================================================================


@dataclass
class _CheckLine:
    """Pre-computed display data for a single health check."""

    icon: str  # "\u2713", "\u2717", "\u26a0", "~"
    name: str
    message: str
    severity: str = "error"
    remedy: str = NO_KNOWN_REMEDY
    # The check's own findings, carried into the line so text and markdown
    # render what json and sarif have always carried (REQ-d00285-C). Empty
    # where the report is not being asked for detail.
    findings: list[HealthFinding] = field(default_factory=list)
    # Whether this line stands for a check a reader should act on -- which is
    # what decides whether its remedy is worth stating.
    actionable: bool = False


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
    verbose: bool = False
    # What a narrowing withheld, where the report was narrowed. A report that
    # showed a reader some of what it found and did not say so is one they
    # cannot tell from a clean run (REQ-d00285-G).
    disclosure: str | None = None


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

    category_flags = {
        "spec": "--spec",
        "references": "--spec",
        "code": "--code-checks",
        "tests": "--tests",
        "config": "",
        "terms": "--terms",
    }
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
            f"Run 'elspais checks{scope} --format json -o health.json' for machine-readable output."
        )


# The categories a check can report under, in the order the report renders
# them. One list, so a `--category` a reader types is judged against the same
# vocabulary the sections are built from.
REPORT_CATEGORIES: tuple[str, ...] = (
    "config",
    "spec",
    "references",
    "code",
    "tests",
    "uat",
    "terms",
    "docs",
    "environment",
)


def _ordered_categories(report: HealthReport) -> list[str]:
    """The categories to render, in report order, with none left out.

    A renderer walking a literal list drops every check reporting under a
    category nobody added to it -- and drops it in silence, since the summary
    counts it either way. Categories the report holds but the list does not
    are rendered after the ones it does.
    """
    seen = {c.category for c in report.checks}
    ordered = [c for c in REPORT_CATEGORIES if c in seen]
    ordered.extend(sorted(seen - set(REPORT_CATEGORIES)))
    return ordered


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
        return f"{report.passed}/{counted} checks passed, {report.warnings} warnings{skip_suffix}"
    else:
        return f"UNHEALTHY: {report.failed} errors, {report.warnings} warnings{skip_suffix}"


# Implements: REQ-d00085-K+M, REQ-d00285-A+B+C
def _build_report_data(
    report: HealthReport,
    verbose: bool = False,
    include_passing_details: bool = False,
    disclosure: str | None = None,
    verdict_report: HealthReport | None = None,
) -> _ReportData:
    """Build the intermediate representation for rendering a health report.

    Extracts all stat computation logic: category icon selection, pass/fail/skip
    counting (excluding info-severity from pass/total), check icon selection,
    summary line, and hint string.

    Args:
        report: The checks to render.
        verbose: Expand all available detail -- which means each failing
            check's findings, with the location and the remedy each carries.
            The default stays as terse as it was: one line per check.
        include_passing_details: Also render the findings of checks that
            passed. Separate from `verbose` because they are separate requests
            (REQ-d00085-K against REQ-d00085-M): a reader asking for the
            detail of what is wrong is not asking for the detail of what is
            right.
        disclosure: What a narrowing withheld, where the report was narrowed.
        verdict_report: The report the summary line and the hint speak for.
            Defaults to `report`, and differs from it only where the report
            was narrowed: the verdict is the whole run's, so a reader who
            filtered down to one category is still told what the run found.
    """
    categories = _ordered_categories(report)
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
            # What decides whether a check's findings need a request of their
            # own is whether the check PASSED, not how loud it is: an
            # info-severity check that reported a condition has findings a
            # reader came for, while a passing check's are noise until asked
            # for (REQ-d00085-M). `actionable` is a narrower question again --
            # whether the reader is being asked to do something about it --
            # and it decides only the follow-up table.
            if check.passed:
                shown = check.findings if include_passing_details else []
            else:
                shown = check.findings if verbose else []
            actionable = not check.passed and check.severity in ("error", "warning")
            check_lines.append(
                _CheckLine(
                    icon=c_icon,
                    name=check.name,
                    message=check.message,
                    severity=check.severity,
                    remedy=check.remedy,
                    findings=list(shown),
                    actionable=actionable,
                )
            )

        sections.append(
            _SectionData(
                name=category.upper(),
                icon=icon,
                stats=", ".join(parts),
                checks=check_lines,
            )
        )

    verdict = verdict_report if verdict_report is not None else report
    summary_line = _build_summary_line(verdict)
    is_healthy = verdict.is_healthy
    hint = _build_hint(verdict, verbose) if not is_healthy else None

    return _ReportData(
        sections=sections,
        summary_line=summary_line,
        is_healthy=is_healthy,
        hint=hint,
        verbose=verbose,
        disclosure=disclosure,
    )


# Implements: REQ-d00285-A+B+C
def _finding_text_lines(finding: HealthFinding, indent: str) -> list[str]:
    """One finding, as the lines that carry what it is about and where it is.

    The location leads because it is what a reader acts on: a finding they
    cannot place costs them the search the tool already performed
    (REQ-d00285-A). What the finding names -- the node, the repository that
    owns it, the things it relates to -- follows on a line of its own, and is
    omitted entirely where the finding names none of them.
    """
    location = finding.location()
    if location:
        head = f"{indent}- {location}: {finding.message}"
    else:
        head = f"{indent}- {finding.message}"
    lines = [head]
    attrs: list[str] = []
    if finding.node_id:
        attrs.append(f"node={finding.node_id}")
    if finding.repo:
        attrs.append(f"repo={finding.repo}")
    if finding.codes:
        attrs.append(f"codes={' '.join(finding.codes)}")
    if finding.related:
        attrs.append(f"related={', '.join(finding.related)}")
    if attrs:
        lines.append(f"{indent}  {' '.join(attrs)}")
    return lines


def _render_text(data: _ReportData) -> str:
    """Render _ReportData as plain text checklist."""
    lines: list[str] = []
    for section in data.sections:
        lines.append(f"\n{section.icon} {section.name} ({section.stats})")
        lines.append("-" * 40)
        for check in section.checks:
            lines.append(f"  {check.icon} {check.name}: {check.message}")
            if check.findings:
                lines.append(f"      remedy: {check.remedy}")
            for finding in check.findings:
                lines.extend(_finding_text_lines(finding, "      "))

    # The follow-up table is what carries each failing check's remedy when the
    # report is terse. Where the findings are rendered, each check has already
    # named its own remedy above and the table would only repeat it.
    followups = (
        []
        if data.verbose
        else [
            (check.name, check.remedy)
            for section in data.sections
            for check in section.checks
            if check.actionable
        ]
    )

    lines.append("")
    lines.append("=" * 40)
    lines.append(data.summary_line)
    if data.disclosure:
        lines.append(data.disclosure)
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
    if data.hint:
        lines.append(data.hint)
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
            if check.findings:
                # A command is code and reads as code; "no command resolves
                # this" is a sentence and would read as one if it were not.
                spelled = check.remedy if check.remedy == NO_KNOWN_REMEDY else f"`{check.remedy}`"
                lines.append(f"  - remedy: {spelled}")
            for finding in check.findings:
                location = finding.location()
                head = f"`{location}`: {finding.message}" if location else finding.message
                lines.append(f"  - {head}")
                attrs: list[str] = []
                if finding.node_id:
                    attrs.append(f"node={finding.node_id}")
                if finding.repo:
                    attrs.append(f"repo={finding.repo}")
                if finding.codes:
                    attrs.append(f"codes={' '.join(finding.codes)}")
                if finding.related:
                    attrs.append(f"related={', '.join(finding.related)}")
                if attrs:
                    lines.append(f"    - {' '.join(attrs)}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(data.summary_line)
    if data.disclosure:
        lines.append("")
        lines.append(data.disclosure)
    if data.hint:
        lines.append("")
        lines.append(data.hint)

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
    categories = _ordered_categories(report)

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
                # The remedy and the findings travel here too, so a report
                # filed to CI names what a report read on a terminal names.
                # Implements: REQ-d00285-A+B+C
                body = _failure_body(check)
                if check.severity == "error":
                    failure = ET.SubElement(tc, "failure", message=check.message)
                    failure.text = body
                elif check.severity == "warning":
                    sys_err = ET.SubElement(tc, "system-err")
                    sys_err.text = f"WARNING: {check.message}\n{body}"
            elif check.passed and include_passing_details and check.findings:
                sys_out = ET.SubElement(tc, "system-out")
                finding_lines = [f.message for f in check.findings]
                sys_out.text = "\n".join(finding_lines)

    return ET.tostring(testsuites, encoding="unicode", xml_declaration=True)


def _failure_body(check: HealthCheck) -> str:
    """The body of a failing check: its remedy, its findings, then its details."""
    parts: list[str] = [f"remedy: {check.remedy}"]
    for finding in check.findings:
        parts.extend(_finding_text_lines(finding, ""))
    if check.details:
        parts.append(_format_details(check.details))
    return "\n".join(parts)


def _format_details(details: dict[str, Any]) -> str:
    """Format check details dict as readable text for XML bodies."""
    parts = []
    for key, value in details.items():
        if isinstance(value, list):
            parts.append(f"{key}: {', '.join(str(v) for v in value)}")
        else:
            parts.append(f"{key}: {value}")
    return "\n".join(parts)


def _finding_properties(check: HealthCheck, finding: HealthFinding) -> dict[str, Any]:
    """The values a finding carries beyond its message and its location."""
    props: dict[str, Any] = {"remedy": check.remedy}
    if finding.node_id:
        props["nodeId"] = finding.node_id
    if finding.repo:
        props["repo"] = finding.repo
    if finding.codes:
        props["codes"] = list(finding.codes)
    if finding.related:
        props["related"] = list(finding.related)
    return props


# Implements: REQ-d00085-J
def _render_sarif(report: HealthReport, verdict: HealthReport | None = None) -> str:
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
                    # The action that resolves the condition, stated where a
                    # SARIF consumer looks for it.
                    # Implements: REQ-d00285-B
                    "help": {"text": check.remedy},
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
                    "properties": _finding_properties(check, finding),
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
                    "properties": {"remedy": check.remedy},
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
                    # The run's counts, not the narrowed view's -- a filtered
                    # report states what the run found and lists a subset.
                    "passed": (verdict or report).passed,
                    "failed": (verdict or report).failed,
                    "warnings": (verdict or report).warnings,
                },
            }
        ],
    }

    return json.dumps(sarif, indent=2)
