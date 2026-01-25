"""Schema-driven configuration for the traceability graph.

This module provides dataclasses for configuring the graph structure,
allowing custom node types, relationships, parsers, and validation rules
to be defined via .elspais.toml configuration.

The schema system enables:
- Adding new node types without code changes (e.g., RISK, COMPLIANCE, EPIC)
- Defining custom relationships (implements, addresses, validates, mitigates, etc.)
- Specifying parsing patterns for each node/relationship type
- Setting validation rules
- Custom parsers for specialized formats
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from fnmatch import fnmatch
from typing import Any


class CoverageSource(Enum):
    """Source type for coverage metrics.

    Tracks where coverage originates for accuracy assessment:
    - DIRECT: Test directly validates assertion (high confidence)
    - EXPLICIT: Child implements specific assertion(s) (high confidence)
    - INFERRED: Child implements parent REQ, claims all assertions (review)
    """

    DIRECT = "direct"  # Test → Assertion
    EXPLICIT = "explicit"  # REQ implements REQ-xxx-A (assertion-level)
    INFERRED = "inferred"  # REQ implements REQ (full REQ)


@dataclass
class CoverageContribution:
    """A coverage contribution to an assertion from a child node.

    Coverage is tracked at the assertion level. Each assertion accumulates
    a list of contributions from tests and child requirements. The graph
    consumer decides how to interpret/aggregate multiple contributions.

    Attributes:
        source_id: ID of contributing node (test ID or child REQ ID).
        source_type: Type of contribution (direct/explicit/inferred).
        coverage_value: For tests, 1.0. For REQs, the child's own coverage_pct/100.
        relationship: The relationship type that created this link (validates/implements/refines).
    """

    source_id: str
    source_type: CoverageSource
    coverage_value: float  # 0.0 to 1.0
    relationship: str = ""  # "validates", "implements", "refines"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "source_id": self.source_id,
            "source_type": self.source_type.value,
            "coverage_value": self.coverage_value,
            "relationship": self.relationship,
        }


@dataclass
class RollupMetrics:
    """Metrics accumulated from children to parents.

    All counts are computed via post-order traversal, where each
    parent's count is the sum of its children's counts (unless excluded).

    Attributes:
        total_assertions: Count of assertion nodes in subtree.
        covered_assertions: Total assertions with any coverage source.
        direct_covered: Assertions with direct test coverage (Test → Assertion).
        explicit_covered: Assertions covered via explicit implements (REQ→Assertion).
        inferred_covered: Assertions covered via REQ→REQ implements (strict mode).
        total_tests: Count of test nodes in subtree.
        passed_tests: Tests with status "passed".
        failed_tests: Tests with status "failed".
        skipped_tests: Tests with status "skipped".
        total_code_refs: Count of code reference nodes in subtree.
        coverage_pct: Percentage of covered assertions (0.0-100.0).
        pass_rate_pct: Percentage of passed tests (0.0-100.0).
    """

    total_assertions: int = 0
    covered_assertions: int = 0
    direct_covered: int = 0  # Test → Assertion
    explicit_covered: int = 0  # REQ implements REQ-xxx-A
    inferred_covered: int = 0  # REQ implements REQ (strict mode only)
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    skipped_tests: int = 0
    total_code_refs: int = 0
    coverage_pct: float = 0.0
    pass_rate_pct: float = 0.0


@dataclass
class MetricsConfig:
    """Configuration for metrics calculations.

    Attributes:
        exclude_status: Statuses to exclude from roll-up calculations.
        count_placeholder_assertions: Whether to count placeholder assertions.
        strict_mode: If True, REQ→REQ implements claims full satisfaction (coverage rollup).
                    If False (default), REQ→REQ implements treated as refines (no rollup).
                    Code→REQ and Test→REQ always use implements semantics regardless.
    """

    exclude_status: list[str] = field(
        default_factory=lambda: ["Deprecated", "Superseded", "Draft"]
    )
    count_placeholder_assertions: bool = False
    strict_mode: bool = False  # Default: REQ→REQ implements treated as refines


@dataclass
class ReportSchema:
    """Schema defining report content and layout.

    Attributes:
        name: Report identifier (e.g., "minimal", "standard", "full").
        description: Human-readable description.
        include_fields: List of requirement fields to include.
        include_metrics: Whether to include RollupMetrics columns.
        metric_fields: Which metric fields to display (if include_metrics=True).
        include_children: Whether to expand child nodes in output.
        max_depth: Maximum hierarchy depth to display (None = unlimited).
        sort_by: Field to sort by ("id", "coverage_pct", "pass_rate_pct").
        sort_descending: Sort direction.
        filters: Optional filters (e.g., {"status": ["Active", "Draft"]}).
    """

    name: str
    description: str = ""
    include_fields: list[str] = field(
        default_factory=lambda: ["id", "title", "status"]
    )
    include_metrics: bool = False
    metric_fields: list[str] = field(default_factory=list)
    include_children: bool = True
    max_depth: int | None = None
    sort_by: str = "id"
    sort_descending: bool = False
    filters: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def defaults(cls) -> dict[str, ReportSchema]:
        """Return built-in report presets.

        Returns:
            Dictionary of preset name to ReportSchema.
        """
        return {
            "minimal": cls(
                name="minimal",
                description="Basic requirement listing",
                include_fields=["id", "title", "status"],
                include_metrics=False,
                include_children=False,
                max_depth=1,
            ),
            "standard": cls(
                name="standard",
                description="Standard report with coverage",
                include_fields=["id", "title", "status", "level", "implements"],
                include_metrics=True,
                metric_fields=[
                    "total_assertions",
                    "covered_assertions",
                    "direct_covered",
                    "explicit_covered",
                    "inferred_covered",
                    "coverage_pct",
                ],
                include_children=True,
            ),
            "full": cls(
                name="full",
                description="Full report with all metrics",
                include_fields=[
                    "id",
                    "title",
                    "status",
                    "level",
                    "implements",
                    "addresses",
                    "hash",
                ],
                include_metrics=True,
                metric_fields=[
                    "total_assertions",
                    "covered_assertions",
                    "direct_covered",
                    "explicit_covered",
                    "inferred_covered",
                    "total_tests",
                    "passed_tests",
                    "failed_tests",
                    "skipped_tests",
                    "total_code_refs",
                    "coverage_pct",
                    "pass_rate_pct",
                ],
                include_children=True,
            ),
        }


@dataclass
class NodeTypeSchema:
    """Schema for a node type.

    Defines how nodes of this type are identified, parsed, and displayed.

    Attributes:
        name: Internal name for this node type (e.g., "requirement").
        id_pattern: ID pattern using template tokens (e.g., "REQ-{type}{id}").
        source: Source type - one of "spec", "code", "test", "test_results".
        parser: Custom parser module path; None = use built-in.
        extract_patterns: Patterns for extracting references from content.
        fields: List of expected fields for this node type.
        has_assertions: Whether this node type can have assertion children.
        is_root: Whether this type is always treated as a root node.
        label_template: Template for display label.
        color: Default color for display (hex).
        colors: Status-based colors (e.g., {"passed": "#27AE60"}).
    """

    name: str
    id_pattern: str | None = None
    source: str = "spec"
    parser: str | None = None
    extract_patterns: list[str] = field(default_factory=list)
    fields: list[str] = field(default_factory=list)
    has_assertions: bool = False
    is_root: bool = False
    label_template: str = "{id}"
    color: str = "#808080"
    colors: dict[str, str] = field(default_factory=dict)


@dataclass
class ParserConfig:
    """Configuration for a parser (for sources with multiple formats).

    Attributes:
        parser: Module path (e.g., "elspais.parsers.junit_xml").
        file_pattern: Glob pattern (e.g., "junit-*.xml").
        source: Which source type this parser handles.
    """

    parser: str
    file_pattern: str
    source: str


@dataclass
class RelationshipSchema:
    """Schema for a relationship type.

    Defines how nodes relate to each other in the graph.

    Attributes:
        name: Relationship name (e.g., "implements").
        from_kind: Source node types that can have this relationship.
        to_kind: Target node types for this relationship.
        direction: "up" (child declares parent) or "down" (parent declares child).
        source_field: Field containing target IDs (e.g., "implements").
        extract_from_content: Whether to extract from file content.
        required_for_non_root: Whether non-root nodes must have this relationship.
        attach_during_parse: Whether targets are attached during parsing.
    """

    name: str
    from_kind: list[str] = field(default_factory=list)
    to_kind: list[str] = field(default_factory=list)
    direction: str = "up"
    source_field: str | None = None
    extract_from_content: bool = False
    required_for_non_root: bool = False
    attach_during_parse: bool = False


@dataclass
class ValidationConfig:
    """Configuration for graph validation rules.

    Attributes:
        orphan_check: Whether to check for orphaned non-root nodes.
        cycle_check: Whether to detect circular dependencies.
        broken_link_check: Whether to warn on references to non-existent IDs.
        duplicate_id_check: Whether to flag duplicate IDs.
        assertion_coverage_check: Whether to report assertions without tests.
        level_constraint_check: Whether to enforce hierarchy levels.
    """

    orphan_check: bool = True
    cycle_check: bool = True
    broken_link_check: bool = True
    duplicate_id_check: bool = True
    assertion_coverage_check: bool = True
    level_constraint_check: bool = True


@dataclass
class GraphSchema:
    """Complete schema for the traceability graph.

    GraphSchema defines the structure, relationships, and validation rules
    for the entire traceability graph. It can be loaded from configuration
    or created with defaults for backwards compatibility.

    Attributes:
        node_types: Dictionary of node type schemas by name.
        relationships: Dictionary of relationship schemas by name.
        parsers: List of parser configurations for multi-format sources.
        default_root_kind: Default node kind for root nodes.
        validation: Validation configuration.
        reports: Dictionary of report schemas by name.
        metrics_config: Configuration for metrics calculations.
    """

    node_types: dict[str, NodeTypeSchema] = field(default_factory=dict)
    relationships: dict[str, RelationshipSchema] = field(default_factory=dict)
    parsers: list[ParserConfig] = field(default_factory=list)
    default_root_kind: str = "requirement"
    validation: ValidationConfig = field(default_factory=ValidationConfig)
    reports: dict[str, ReportSchema] = field(default_factory=dict)
    metrics_config: MetricsConfig = field(default_factory=MetricsConfig)

    def get_node_type(self, name: str) -> NodeTypeSchema | None:
        """Get node type schema by name.

        Args:
            name: Node type name.

        Returns:
            NodeTypeSchema if found, None otherwise.
        """
        return self.node_types.get(name)

    def get_relationship(self, name: str) -> RelationshipSchema | None:
        """Get relationship schema by name.

        Args:
            name: Relationship name.

        Returns:
            RelationshipSchema if found, None otherwise.
        """
        return self.relationships.get(name)

    def get_parsers_for_source(self, source: str) -> list[ParserConfig]:
        """Get all parsers for a source type.

        Args:
            source: Source type (e.g., "test_results").

        Returns:
            List of ParserConfig for the source.
        """
        return [p for p in self.parsers if p.source == source]

    def find_parser_for_file(self, file_path: str, source: str) -> ParserConfig | None:
        """Find the parser config for a specific file.

        Args:
            file_path: Path to the file (filename only or full path).
            source: Source type to filter parsers.

        Returns:
            Matching ParserConfig, or None if no match.
        """
        # Get just the filename for matching
        filename = file_path.split("/")[-1] if "/" in file_path else file_path

        for parser in self.get_parsers_for_source(source):
            if fnmatch(filename, parser.file_pattern):
                return parser
        return None

    def validate_parser_patterns(self) -> list[str]:
        """Check for overlapping parser patterns.

        Returns:
            List of error messages for overlapping patterns.
        """
        errors: list[str] = []
        by_source: dict[str, list[ParserConfig]] = {}

        for pc in self.parsers:
            by_source.setdefault(pc.source, []).append(pc)

        for source, configs in by_source.items():
            patterns = [c.file_pattern for c in configs]

            # Simple overlap detection: check if patterns could match same files
            # This is a heuristic - exact overlap detection would require more complex logic
            for i, p1 in enumerate(patterns):
                for _j, p2 in enumerate(patterns[i + 1 :], start=i + 1):
                    # If one pattern could be a subset of another
                    if self._patterns_overlap(p1, p2):
                        errors.append(
                            f"Potentially overlapping patterns for source '{source}': "
                            f"'{p1}' and '{p2}'"
                        )

        return errors

    def _patterns_overlap(self, p1: str, p2: str) -> bool:
        """Check if two glob patterns might overlap.

        This is a heuristic check - not exhaustive.
        """
        # Identical patterns definitely overlap
        if p1 == p2:
            return True

        # If one is more specific than the other, check if they could match same files
        # e.g., "*.xml" and "junit-*.xml" could overlap
        if "*" in p1 and "*" in p2:
            # Get the fixed parts
            p1_base = p1.replace("*", "")
            p2_base = p2.replace("*", "")

            # If one base is contained in the other, they might overlap
            if p1_base in p2_base or p2_base in p1_base:
                return True

        return False

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> GraphSchema:
        """Parse schema from configuration dictionary.

        Args:
            config: Full configuration dictionary (from .elspais.toml).

        Returns:
            GraphSchema instance.
        """
        # Support both [graph] (new) and [tree] (legacy) config keys
        graph_config = config.get("graph", config.get("tree", {}))

        # Parse node types
        node_types: dict[str, NodeTypeSchema] = {}
        for name, node_config in graph_config.get("nodes", {}).items():
            # Extract fields that need special handling
            nc = dict(node_config)
            node_types[name] = NodeTypeSchema(
                name=name,
                id_pattern=nc.get("id_pattern"),
                source=nc.get("source", "spec"),
                parser=nc.get("parser"),
                extract_patterns=nc.get("extract_patterns", []),
                fields=nc.get("fields", []),
                has_assertions=nc.get("has_assertions", False),
                is_root=nc.get("is_root", False),
                label_template=nc.get("label_template", "{id}"),
                color=nc.get("color", "#808080"),
                colors=nc.get("colors", {}),
            )

        # Parse relationships
        relationships: dict[str, RelationshipSchema] = {}
        for name, rel_config in graph_config.get("relationships", {}).items():
            rc = dict(rel_config)

            # Normalize from_kind/to_kind to lists
            from_kind = rc.get("from_kind", [])
            if isinstance(from_kind, str):
                from_kind = [from_kind]
            to_kind = rc.get("to_kind", [])
            if isinstance(to_kind, str):
                to_kind = [to_kind]

            relationships[name] = RelationshipSchema(
                name=name,
                from_kind=from_kind,
                to_kind=to_kind,
                direction=rc.get("direction", "up"),
                source_field=rc.get("source_field"),
                extract_from_content=rc.get("extract_from_content", False),
                required_for_non_root=rc.get("required_for_non_root", False),
                attach_during_parse=rc.get("attach_during_parse", False),
            )

        # Parse parsers list
        parsers: list[ParserConfig] = []
        for parser_list in graph_config.get("parsers", {}).values():
            if isinstance(parser_list, list):
                for pc in parser_list:
                    if isinstance(pc, dict):
                        parsers.append(
                            ParserConfig(
                                parser=pc.get("parser", ""),
                                file_pattern=pc.get("file_pattern", ""),
                                source=pc.get("source", ""),
                            )
                        )
            elif isinstance(parser_list, dict):
                parsers.append(
                    ParserConfig(
                        parser=parser_list.get("parser", ""),
                        file_pattern=parser_list.get("file_pattern", ""),
                        source=parser_list.get("source", ""),
                    )
                )

        # Parse validation config
        validation_config = graph_config.get("validation", {})
        validation = ValidationConfig(
            orphan_check=validation_config.get("orphan_check", True),
            cycle_check=validation_config.get("cycle_check", True),
            broken_link_check=validation_config.get("broken_link_check", True),
            duplicate_id_check=validation_config.get("duplicate_id_check", True),
            assertion_coverage_check=validation_config.get("assertion_coverage_check", True),
            level_constraint_check=validation_config.get("level_constraint_check", True),
        )

        # Parse report schemas from [trace.reports.*]
        reports: dict[str, ReportSchema] = {}
        trace_config = config.get("trace", {})
        reports_config = trace_config.get("reports", {})
        for name, report_dict in reports_config.items():
            reports[name] = ReportSchema(
                name=name,
                description=report_dict.get("description", ""),
                include_fields=report_dict.get("fields", ["id", "title", "status"]),
                include_metrics=report_dict.get("include_metrics", False),
                metric_fields=report_dict.get("metric_fields", []),
                include_children=report_dict.get("include_children", True),
                max_depth=report_dict.get("max_depth"),
                sort_by=report_dict.get("sort_by", "id"),
                sort_descending=report_dict.get("sort_descending", False),
                filters=report_dict.get("filters", {}),
            )

        # Add default presets if not overridden
        for preset_name, preset in ReportSchema.defaults().items():
            if preset_name not in reports:
                reports[preset_name] = preset

        # Parse metrics config from [rules.metrics]
        rules_config = config.get("rules", {})
        metrics_dict = rules_config.get("metrics", {})
        metrics_config = MetricsConfig(
            exclude_status=metrics_dict.get(
                "exclude_status", ["Deprecated", "Superseded", "Draft"]
            ),
            count_placeholder_assertions=metrics_dict.get(
                "count_placeholder_assertions", False
            ),
            strict_mode=metrics_dict.get("strict_mode", False),
        )

        return cls(
            node_types=node_types,
            relationships=relationships,
            parsers=parsers,
            default_root_kind=graph_config.get("default_root_kind", "requirement"),
            validation=validation,
            reports=reports,
            metrics_config=metrics_config,
        )

    @classmethod
    def default(cls) -> GraphSchema:
        """Return default schema (backwards compatible with hardcoded behavior).

        Returns:
            GraphSchema with default configuration matching existing elspais behavior.
        """
        return cls(
            node_types={
                "requirement": NodeTypeSchema(
                    name="requirement",
                    id_pattern="REQ-{type}{id}",
                    source="spec",
                    fields=[
                        "title",
                        "body",
                        "rationale",
                        "status",
                        "level",
                        "implements",
                        "addresses",
                    ],
                    has_assertions=True,
                    label_template="{id}: {title}",
                    color="#4A90D9",
                ),
                "user_journey": NodeTypeSchema(
                    name="user_journey",
                    id_pattern="JNY-{descriptor}-{number}",
                    source="spec",
                    fields=["actor", "goal", "context", "steps", "expected_outcome"],
                    is_root=True,
                    label_template="{id}: {goal}",
                    color="#9B59B6",
                ),
                "code": NodeTypeSchema(
                    name="code",
                    source="code",
                    extract_patterns=[
                        "# Implements: {ref}",
                        "// Implements: {ref}",
                        "/* Implements: {ref} */",
                    ],
                    fields=["file_path", "line", "symbol"],
                    label_template="{symbol} ({file_path}:{line})",
                    color="#27AE60",
                ),
                "test": NodeTypeSchema(
                    name="test",
                    source="test",
                    extract_patterns=[
                        "REQ-{type}{id}",
                        "REQ-{type}{id}-{label}",
                    ],
                    fields=["file_path", "line", "test_name", "test_class"],
                    label_template="{test_class}::{test_name}",
                    color="#E74C3C",
                ),
                "test_result": NodeTypeSchema(
                    name="test_result",
                    source="test_results",
                    fields=["status", "duration", "message"],
                    label_template="{status}: {duration}ms",
                    colors={
                        "passed": "#27AE60",
                        "failed": "#E74C3C",
                        "skipped": "#F39C12",
                    },
                ),
                "file": NodeTypeSchema(
                    name="file",
                    source="spec",
                    fields=["file_path", "requirements"],
                    is_root=True,  # FILE nodes are always roots (no parents)
                    label_template="{file_path}",
                    color="#95A5A6",  # Gray for files
                ),
                "file_region": NodeTypeSchema(
                    name="file_region",
                    source="spec",
                    fields=["region_type", "start_line", "end_line", "content"],
                    is_root=False,  # FILE_REGION has FILE parent
                    label_template="{region_type} ({start_line}-{end_line})",
                    color="#BDC3C7",  # Light gray for regions
                ),
            },
            relationships={
                "implements": RelationshipSchema(
                    name="implements",
                    from_kind=["requirement"],
                    to_kind=["requirement", "assertion"],
                    direction="up",
                    source_field="implements",
                    required_for_non_root=True,
                ),
                "refines": RelationshipSchema(
                    name="refines",
                    from_kind=["requirement"],
                    to_kind=["requirement", "assertion"],
                    direction="up",
                    source_field="refines",
                    required_for_non_root=False,  # refines doesn't require parent
                ),
                "addresses": RelationshipSchema(
                    name="addresses",
                    from_kind=["requirement"],
                    to_kind=["user_journey"],
                    direction="up",
                    source_field="addresses",
                ),
                "validates": RelationshipSchema(
                    name="validates",
                    from_kind=["test", "code"],
                    to_kind=["requirement", "assertion"],
                    direction="up",
                    extract_from_content=True,
                ),
                "produces": RelationshipSchema(
                    name="produces",
                    from_kind=["test"],
                    to_kind=["test_result"],
                    direction="down",
                    attach_during_parse=True,
                ),
                "contains": RelationshipSchema(
                    name="contains",
                    from_kind=["file"],
                    to_kind=["file_region"],
                    direction="down",
                    required_for_non_root=False,
                ),
            },
            parsers=[
                ParserConfig(
                    parser="elspais.parsers.junit_xml",
                    file_pattern="junit-*.xml",
                    source="test_results",
                ),
                ParserConfig(
                    parser="elspais.parsers.pytest_json",
                    file_pattern="pytest-*.json",
                    source="test_results",
                ),
            ],
            validation=ValidationConfig(
                orphan_check=True,
                cycle_check=True,
                broken_link_check=True,
                duplicate_id_check=True,
                assertion_coverage_check=True,
                level_constraint_check=True,
            ),
            reports=ReportSchema.defaults(),
            metrics_config=MetricsConfig(),
        )

    def merge_with(self, other: GraphSchema) -> GraphSchema:
        """Merge another schema into this one.

        Other schema values override this schema's values where both are defined.

        Args:
            other: Schema to merge in.

        Returns:
            New merged GraphSchema.
        """
        merged_node_types = dict(self.node_types)
        merged_node_types.update(other.node_types)

        merged_relationships = dict(self.relationships)
        merged_relationships.update(other.relationships)

        merged_parsers = list(self.parsers)
        for parser in other.parsers:
            # Avoid duplicate parsers
            if parser not in merged_parsers:
                merged_parsers.append(parser)

        merged_reports = dict(self.reports)
        merged_reports.update(other.reports)

        return GraphSchema(
            node_types=merged_node_types,
            relationships=merged_relationships,
            parsers=merged_parsers,
            default_root_kind=other.default_root_kind or self.default_root_kind,
            validation=other.validation,
            reports=merged_reports,
            metrics_config=other.metrics_config,
        )


# Backwards compatibility alias (deprecated)
TreeSchema = GraphSchema
