"""Schema-driven configuration for the traceability tree.

This module provides dataclasses for configuring the tree structure,
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
from fnmatch import fnmatch
from typing import Any


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

    Defines how nodes relate to each other in the tree.

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
    """Configuration for tree validation rules.

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
class TreeSchema:
    """Complete schema for the traceability tree.

    TreeSchema defines the structure, relationships, and validation rules
    for the entire traceability tree. It can be loaded from configuration
    or created with defaults for backwards compatibility.

    Attributes:
        node_types: Dictionary of node type schemas by name.
        relationships: Dictionary of relationship schemas by name.
        parsers: List of parser configurations for multi-format sources.
        default_root_kind: Default node kind for root nodes.
        validation: Validation configuration.
    """

    node_types: dict[str, NodeTypeSchema] = field(default_factory=dict)
    relationships: dict[str, RelationshipSchema] = field(default_factory=dict)
    parsers: list[ParserConfig] = field(default_factory=list)
    default_root_kind: str = "requirement"
    validation: ValidationConfig = field(default_factory=ValidationConfig)

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
    def from_config(cls, config: dict[str, Any]) -> TreeSchema:
        """Parse schema from configuration dictionary.

        Args:
            config: Full configuration dictionary (from .elspais.toml).

        Returns:
            TreeSchema instance.
        """
        tree_config = config.get("tree", {})

        # Parse node types
        node_types: dict[str, NodeTypeSchema] = {}
        for name, node_config in tree_config.get("nodes", {}).items():
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
        for name, rel_config in tree_config.get("relationships", {}).items():
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
        for parser_list in tree_config.get("parsers", {}).values():
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
        validation_config = tree_config.get("validation", {})
        validation = ValidationConfig(
            orphan_check=validation_config.get("orphan_check", True),
            cycle_check=validation_config.get("cycle_check", True),
            broken_link_check=validation_config.get("broken_link_check", True),
            duplicate_id_check=validation_config.get("duplicate_id_check", True),
            assertion_coverage_check=validation_config.get("assertion_coverage_check", True),
            level_constraint_check=validation_config.get("level_constraint_check", True),
        )

        return cls(
            node_types=node_types,
            relationships=relationships,
            parsers=parsers,
            default_root_kind=tree_config.get("default_root_kind", "requirement"),
            validation=validation,
        )

    @classmethod
    def default(cls) -> TreeSchema:
        """Return default schema (backwards compatible with hardcoded behavior).

        Returns:
            TreeSchema with default configuration matching existing elspais behavior.
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
            },
            relationships={
                "implements": RelationshipSchema(
                    name="implements",
                    from_kind=["requirement"],
                    to_kind=["requirement"],
                    direction="up",
                    source_field="implements",
                    required_for_non_root=True,
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
        )

    def merge_with(self, other: TreeSchema) -> TreeSchema:
        """Merge another schema into this one.

        Other schema values override this schema's values where both are defined.

        Args:
            other: Schema to merge in.

        Returns:
            New merged TreeSchema.
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

        return TreeSchema(
            node_types=merged_node_types,
            relationships=merged_relationships,
            parsers=merged_parsers,
            default_root_kind=other.default_root_kind or self.default_root_kind,
            validation=other.validation,
        )
