"""Tests for core/tree_schema.py - Schema-driven tree configuration."""


# Validates: REQ-p00003-B
class TestNodeTypeSchema:
    """Tests for NodeTypeSchema dataclass."""

    def test_creation_minimal(self):
        """Test creating NodeTypeSchema with minimal fields."""
        from elspais.core.graph_schema import NodeTypeSchema

        schema = NodeTypeSchema(name="test")

        assert schema.name == "test"
        assert schema.id_pattern is None
        assert schema.source == "spec"
        assert schema.parser is None
        assert schema.extract_patterns == []
        assert schema.fields == []
        assert schema.has_assertions is False
        assert schema.is_root is False
        assert schema.label_template == "{id}"
        assert schema.color == "#808080"
        assert schema.colors == {}

    def test_creation_full(self):
        """Test creating NodeTypeSchema with all fields."""
        from elspais.core.graph_schema import NodeTypeSchema

        schema = NodeTypeSchema(
            name="requirement",
            id_pattern="REQ-{type}{id}",
            source="spec",
            parser="elspais.parsers.requirement",
            extract_patterns=["# Implements: {ref}"],
            fields=["title", "body", "status"],
            has_assertions=True,
            is_root=False,
            label_template="{id}: {title}",
            color="#4A90D9",
            colors={"active": "#27AE60"},
        )

        assert schema.name == "requirement"
        assert schema.id_pattern == "REQ-{type}{id}"
        assert schema.source == "spec"
        assert schema.parser == "elspais.parsers.requirement"
        assert schema.extract_patterns == ["# Implements: {ref}"]
        assert schema.fields == ["title", "body", "status"]
        assert schema.has_assertions is True
        assert schema.is_root is False
        assert schema.label_template == "{id}: {title}"
        assert schema.color == "#4A90D9"
        assert schema.colors == {"active": "#27AE60"}


# Validates: REQ-p00003-A
class TestParserConfig:
    """Tests for ParserConfig dataclass."""

    def test_creation(self):
        """Test creating ParserConfig."""
        from elspais.core.graph_schema import ParserConfig

        config = ParserConfig(
            parser="elspais.parsers.junit_xml",
            file_pattern="junit-*.xml",
            source="test_results",
        )

        assert config.parser == "elspais.parsers.junit_xml"
        assert config.file_pattern == "junit-*.xml"
        assert config.source == "test_results"


# Validates: REQ-p00003-B
class TestRelationshipSchema:
    """Tests for RelationshipSchema dataclass."""

    def test_creation_minimal(self):
        """Test creating RelationshipSchema with minimal fields."""
        from elspais.core.graph_schema import RelationshipSchema

        schema = RelationshipSchema(name="implements")

        assert schema.name == "implements"
        assert schema.from_kind == []
        assert schema.to_kind == []
        assert schema.direction == "up"
        assert schema.source_field is None
        assert schema.extract_from_content is False
        assert schema.required_for_non_root is False

    def test_creation_full(self):
        """Test creating RelationshipSchema with all fields."""
        from elspais.core.graph_schema import RelationshipSchema

        schema = RelationshipSchema(
            name="implements",
            from_kind=["requirement"],
            to_kind=["requirement"],
            direction="up",
            source_field="implements",
            extract_from_content=False,
            required_for_non_root=True,
        )

        assert schema.name == "implements"
        assert schema.from_kind == ["requirement"]
        assert schema.to_kind == ["requirement"]
        assert schema.direction == "up"
        assert schema.source_field == "implements"
        assert schema.required_for_non_root is True


# Validates: REQ-p00002-B
class TestValidationConfig:
    """Tests for ValidationConfig dataclass."""

    def test_defaults(self):
        """Test ValidationConfig default values."""
        from elspais.core.graph_schema import ValidationConfig

        config = ValidationConfig()

        assert config.orphan_check is True
        assert config.cycle_check is True
        assert config.broken_link_check is True
        assert config.duplicate_id_check is True
        assert config.assertion_coverage_check is True
        assert config.level_constraint_check is True

    def test_custom_values(self):
        """Test ValidationConfig with custom values."""
        from elspais.core.graph_schema import ValidationConfig

        config = ValidationConfig(
            orphan_check=False,
            cycle_check=True,
            broken_link_check=False,
        )

        assert config.orphan_check is False
        assert config.cycle_check is True
        assert config.broken_link_check is False


# Validates: REQ-p00003-A, REQ-p00003-B
class TestGraphSchema:
    """Tests for GraphSchema dataclass."""

    def test_default_schema(self):
        """Test creating default schema."""
        from elspais.core.graph_schema import GraphSchema

        schema = GraphSchema.default()

        # Check node types
        assert "requirement" in schema.node_types
        assert "user_journey" in schema.node_types
        assert "code" in schema.node_types
        assert "test" in schema.node_types
        assert "test_result" in schema.node_types

        # Check relationships
        assert "implements" in schema.relationships
        assert "addresses" in schema.relationships
        assert "validates" in schema.relationships

        # Check default parsers
        assert len(schema.parsers) == 2

        # Check default root kind
        assert schema.default_root_kind == "requirement"

    def test_get_node_type(self):
        """Test getting node type by name."""
        from elspais.core.graph_schema import GraphSchema

        schema = GraphSchema.default()

        req_type = schema.get_node_type("requirement")
        assert req_type is not None
        assert req_type.name == "requirement"
        assert req_type.has_assertions is True

        unknown = schema.get_node_type("unknown")
        assert unknown is None

    def test_get_relationship(self):
        """Test getting relationship by name."""
        from elspais.core.graph_schema import GraphSchema

        schema = GraphSchema.default()

        implements = schema.get_relationship("implements")
        assert implements is not None
        assert implements.name == "implements"
        assert implements.direction == "up"

        unknown = schema.get_relationship("unknown")
        assert unknown is None

    def test_get_parsers_for_source(self):
        """Test getting parsers for a source type."""
        from elspais.core.graph_schema import GraphSchema

        schema = GraphSchema.default()

        result_parsers = schema.get_parsers_for_source("test_results")
        assert len(result_parsers) == 2

        spec_parsers = schema.get_parsers_for_source("spec")
        assert len(spec_parsers) == 0

    def test_find_parser_for_file(self):
        """Test finding parser for a specific file."""
        from elspais.core.graph_schema import GraphSchema

        schema = GraphSchema.default()

        junit_parser = schema.find_parser_for_file("junit-report.xml", "test_results")
        assert junit_parser is not None
        assert "junit" in junit_parser.parser

        pytest_parser = schema.find_parser_for_file("pytest-results.json", "test_results")
        assert pytest_parser is not None
        assert "pytest" in pytest_parser.parser

        no_parser = schema.find_parser_for_file("unknown.txt", "test_results")
        assert no_parser is None

    def test_validate_parser_patterns_no_overlap(self):
        """Test validation passes when no patterns overlap."""
        from elspais.core.graph_schema import GraphSchema

        schema = GraphSchema.default()
        errors = schema.validate_parser_patterns()

        # Default schema should have no overlapping patterns
        assert len(errors) == 0

    def test_validate_parser_patterns_with_overlap(self):
        """Test validation detects overlapping patterns."""
        from elspais.core.graph_schema import ParserConfig, GraphSchema

        schema = GraphSchema(
            parsers=[
                ParserConfig(parser="p1", file_pattern="*.xml", source="test_results"),
                ParserConfig(parser="p2", file_pattern="junit-*.xml", source="test_results"),
            ]
        )

        errors = schema.validate_parser_patterns()

        # Should detect potential overlap between *.xml and junit-*.xml
        assert len(errors) > 0
        assert "overlapping" in errors[0].lower()

    def test_from_config_empty(self):
        """Test parsing empty config."""
        from elspais.core.graph_schema import GraphSchema

        schema = GraphSchema.from_config({})

        assert schema.node_types == {}
        assert schema.relationships == {}
        assert schema.parsers == []
        assert schema.default_root_kind == "requirement"

    def test_from_config_with_nodes(self):
        """Test parsing config with node types."""
        from elspais.core.graph_schema import GraphSchema

        config = {
            "tree": {
                "nodes": {
                    "risk": {
                        "id_pattern": "RISK-{category}-{id}",
                        "fields": ["title", "severity", "likelihood"],
                        "label_template": "{id}: {title}",
                        "color": "#E74C3C",
                    }
                }
            }
        }

        schema = GraphSchema.from_config(config)

        assert "risk" in schema.node_types
        risk = schema.node_types["risk"]
        assert risk.id_pattern == "RISK-{category}-{id}"
        assert "severity" in risk.fields
        assert risk.color == "#E74C3C"

    def test_from_config_with_relationships(self):
        """Test parsing config with relationships."""
        from elspais.core.graph_schema import GraphSchema

        config = {
            "tree": {
                "relationships": {
                    "mitigates": {
                        "from_kind": "requirement",  # String, should be normalized to list
                        "to_kind": ["risk"],
                        "direction": "up",
                        "source_field": "mitigates",
                    }
                }
            }
        }

        schema = GraphSchema.from_config(config)

        assert "mitigates" in schema.relationships
        mitigates = schema.relationships["mitigates"]
        assert mitigates.from_kind == ["requirement"]  # Normalized to list
        assert mitigates.to_kind == ["risk"]
        assert mitigates.direction == "up"
        assert mitigates.source_field == "mitigates"

    def test_from_config_with_validation(self):
        """Test parsing config with validation settings."""
        from elspais.core.graph_schema import GraphSchema

        config = {
            "tree": {
                "validation": {
                    "orphan_check": False,
                    "cycle_check": True,
                    "broken_link_check": False,
                }
            }
        }

        schema = GraphSchema.from_config(config)

        assert schema.validation.orphan_check is False
        assert schema.validation.cycle_check is True
        assert schema.validation.broken_link_check is False

    def test_merge_with(self):
        """Test merging two schemas."""
        from elspais.core.graph_schema import NodeTypeSchema, RelationshipSchema, GraphSchema

        base = GraphSchema.default()

        extension = GraphSchema(
            node_types={
                "risk": NodeTypeSchema(
                    name="risk",
                    id_pattern="RISK-{id}",
                    color="#E74C3C",
                )
            },
            relationships={
                "mitigates": RelationshipSchema(
                    name="mitigates",
                    from_kind=["requirement"],
                    to_kind=["risk"],
                )
            },
        )

        merged = base.merge_with(extension)

        # Should have all original node types plus new one
        assert "requirement" in merged.node_types
        assert "risk" in merged.node_types

        # Should have all original relationships plus new one
        assert "implements" in merged.relationships
        assert "mitigates" in merged.relationships


# Validates: REQ-p00003-A, REQ-p00003-B
class TestGraphSchemaIntegration:
    """Integration tests for GraphSchema with real config files."""

    def test_from_fixture_config(self, hht_like_fixture):
        """Test loading schema from fixture config."""
        from elspais.config.loader import load_config
        from elspais.core.graph_schema import GraphSchema

        config = load_config(hht_like_fixture / ".elspais.toml")

        # Create schema - if no tree config, use defaults
        if "tree" in config:
            schema = GraphSchema.from_config(config)
        else:
            schema = GraphSchema.default()

        # Default schema should work
        assert schema.default_root_kind == "requirement"
        assert "requirement" in schema.node_types or len(schema.node_types) == 0

    def test_default_schema_node_properties(self):
        """Test default schema has correct node properties."""
        from elspais.core.graph_schema import GraphSchema

        schema = GraphSchema.default()

        # Requirement should have assertions
        req = schema.get_node_type("requirement")
        assert req is not None
        assert req.has_assertions is True
        assert req.is_root is False

        # User journey should be root
        journey = schema.get_node_type("user_journey")
        assert journey is not None
        assert journey.is_root is True

        # Test should not be root
        test = schema.get_node_type("test")
        assert test is not None
        assert test.is_root is False

    def test_default_schema_relationship_properties(self):
        """Test default schema has correct relationship properties."""
        from elspais.core.graph_schema import GraphSchema

        schema = GraphSchema.default()

        # Implements is required for non-root
        implements = schema.get_relationship("implements")
        assert implements is not None
        assert implements.required_for_non_root is True
        assert implements.direction == "up"

        # Validates extracts from content
        validates = schema.get_relationship("validates")
        assert validates is not None
        assert validates.extract_from_content is True
