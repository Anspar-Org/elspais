"""Tests for schema-driven init template generation.

Validates REQ-d00209: Schema-driven init template generation.

The generate_config() function should produce TOML from the ElspaisConfig
Pydantic model (schema walker), not from hardcoded template strings.
"""

from __future__ import annotations

import tomlkit

from elspais.commands.init import generate_config
from elspais.config.schema import ElspaisConfig


class TestCoreConfigValidation:
    """Validates REQ-d00209-A: generate_config("core") produces valid TOML."""

    def test_REQ_d00209_A_core_config_parses_as_toml(self) -> None:
        """Core config output must be valid TOML."""
        content = generate_config("core")
        parsed = tomlkit.parse(content)
        assert isinstance(parsed, dict)

    def test_REQ_d00209_A_core_config_validates_against_schema(self) -> None:
        """Core config must pass ElspaisConfig.model_validate() without error."""
        content = generate_config("core")
        parsed = tomlkit.parse(content)
        data = dict(parsed)
        # Should not raise ValidationError
        config = ElspaisConfig.model_validate(data)
        assert config.project.name is not None

    def test_REQ_d00209_A_core_config_project_name(self) -> None:
        """Core config must have a sensible project name."""
        content = generate_config("core")
        parsed = tomlkit.parse(content)
        data = dict(parsed)
        config = ElspaisConfig.model_validate(data)
        assert config.project.name is not None
        assert len(config.project.name) > 0

    def test_REQ_d00209_A_core_config_namespace(self) -> None:
        """Core config must set namespace to REQ."""
        content = generate_config("core")
        parsed = tomlkit.parse(content)
        data = dict(parsed)
        config = ElspaisConfig.model_validate(data)
        assert config.project.namespace == "REQ"

    def test_REQ_d00209_A_core_config_includes_version(self) -> None:
        """Core config must include the schema version field.

        The schema-driven generator should emit a top-level 'version' key
        matching the schema default. The current hardcoded template omits it.
        """
        content = generate_config("core")
        parsed = tomlkit.parse(content)
        assert "version" in parsed, "Generated core config must include top-level 'version' key"
        assert parsed["version"] == ElspaisConfig.model_fields["version"].default

    def test_REQ_d00209_A_core_config_round_trips_through_schema(self) -> None:
        """Core config parsed and re-serialized must still validate.

        This ensures no tomlkit type artifacts break validation.
        """
        content = generate_config("core")
        parsed = tomlkit.parse(content)
        config = ElspaisConfig.model_validate(dict(parsed))
        # Dump back and re-validate
        dumped = config.model_dump(by_alias=True)
        ElspaisConfig.model_validate(dumped)


class TestAssociatedConfigValidation:
    """Validates REQ-d00209-B: generate_config("associated") produces valid TOML."""

    def test_REQ_d00209_B_associated_config_parses_as_toml(self) -> None:
        """Associated config output must be valid TOML."""
        content = generate_config("associated", associated_prefix="TST")
        parsed = tomlkit.parse(content)
        assert isinstance(parsed, dict)

    def test_REQ_d00209_B_associated_config_validates_against_schema(self) -> None:
        """Associated config must pass ElspaisConfig.model_validate() without error."""
        content = generate_config("associated", associated_prefix="TST")
        parsed = tomlkit.parse(content)
        data = dict(parsed)
        # Should not raise ValidationError
        config = ElspaisConfig.model_validate(data)
        assert config.project.namespace == "TST"

    def test_REQ_d00209_B_associated_config_uses_prefix(self) -> None:
        """Associated config must incorporate the given prefix as namespace."""
        content = generate_config("associated", associated_prefix="ABC")
        parsed = tomlkit.parse(content)
        data = dict(parsed)
        config = ElspaisConfig.model_validate(data)
        assert config.project.namespace == "ABC"

    def test_REQ_d00209_B_associated_config_includes_version(self) -> None:
        """Associated config must include the schema version field.

        The schema-driven generator should emit a top-level 'version' key.
        The current hardcoded template omits it.
        """
        content = generate_config("associated", associated_prefix="TST")
        parsed = tomlkit.parse(content)
        assert (
            "version" in parsed
        ), "Generated associated config must include top-level 'version' key"

    def test_REQ_d00209_B_associated_different_prefixes(self) -> None:
        """Associated config must work with various prefix values."""
        for prefix in ("FOO", "X", "LONGPREFIX"):
            content = generate_config("associated", associated_prefix=prefix)
            parsed = tomlkit.parse(content)
            config = ElspaisConfig.model_validate(dict(parsed))
            assert config.project.namespace == prefix


class TestGeneratedSections:
    """Validates REQ-d00209-C: Generated TOML includes all expected sections."""

    # These are sections that a schema-driven generator MUST emit for core.
    CORE_EXPECTED_SECTIONS = [
        "project",
        "id-patterns",
        "levels",
        "scanning",
        "rules",
        "changelog",
    ]

    # Schema-complete: all sections the schema defines that should appear
    # (excluding optional associates which is project-type dependent)
    CORE_SCHEMA_COMPLETE_SECTIONS = [
        "version",
        "project",
        "id-patterns",
        "levels",
        "scanning",
        "rules",
        "changelog",
        "keywords",
        "validation",
        "output",
    ]

    ASSOCIATED_EXPECTED_SECTIONS = [
        "project",
        "id-patterns",
        "levels",
        "scanning",
        "rules",
    ]

    def test_REQ_d00209_C_core_has_all_sections(self) -> None:
        """Core config must include all standard sections."""
        content = generate_config("core")
        parsed = tomlkit.parse(content)
        for section in self.CORE_EXPECTED_SECTIONS:
            assert section in parsed, f"Missing section: [{section}]"

    def test_REQ_d00209_C_core_is_schema_complete(self) -> None:
        """Core config must include ALL schema-defined sections.

        A schema-driven generator should emit every section the Pydantic model
        defines, not just a hand-picked subset.
        """
        content = generate_config("core")
        parsed = tomlkit.parse(content)
        missing = [s for s in self.CORE_SCHEMA_COMPLETE_SECTIONS if s not in parsed]
        assert not missing, f"Core config missing schema sections: {missing}"

    def test_REQ_d00209_C_associated_has_all_sections(self) -> None:
        """Associated config must include all required sections."""
        content = generate_config("associated", associated_prefix="TST")
        parsed = tomlkit.parse(content)
        for section in self.ASSOCIATED_EXPECTED_SECTIONS:
            assert section in parsed, f"Missing section: [{section}]"

    def test_REQ_d00209_C_associated_is_schema_complete(self) -> None:
        """Associated config should include schema-defined sections.

        A schema-driven generator should emit most sections for associated
        repos too, not just the minimal set.
        """
        content = generate_config("associated", associated_prefix="TST")
        parsed = tomlkit.parse(content)
        # At minimum, associated should have these beyond the basics
        expected_extra = ["scanning"]
        missing = [s for s in expected_extra if s not in parsed]
        assert not missing, f"Associated config missing sections: {missing}"

    def test_REQ_d00209_C_core_has_levels(self) -> None:
        """Core config must define levels for dev, ops, prd."""
        content = generate_config("core")
        parsed = tomlkit.parse(content)
        data = dict(parsed)
        config = ElspaisConfig.model_validate(data)
        assert "prd" in config.levels
        assert "ops" in config.levels
        assert "dev" in config.levels

    def test_REQ_d00209_C_core_has_id_patterns(self) -> None:
        """Core config must define id-patterns section."""
        content = generate_config("core")
        parsed = tomlkit.parse(content)
        data = dict(parsed)
        config = ElspaisConfig.model_validate(data)
        assert config.id_patterns.canonical is not None

    def test_REQ_d00209_C_core_emits_all_non_optional_fields(self) -> None:
        """Core config must emit every field that has a non-None default."""
        content = generate_config("core")
        parsed = tomlkit.parse(content)
        config = ElspaisConfig.model_validate(dict(parsed))
        # Spot-check fields that were previously missing
        assert config.validation.hash_mode == "normalized-text"
        assert config.keywords.min_length == 3
        assert config.changelog.hash_current is True
        assert config.scanning.test.reference_keyword == "Verifies"

    def test_REQ_d00209_C_core_emits_top_level_scalars(self) -> None:
        """Core config must emit cli_ttl and stats fields."""
        content = generate_config("core")
        assert "cli_ttl" in content, "cli_ttl must appear in generated config"
        # stats is optional, should appear as comment
        assert "stats" in content, "stats must appear (as comment) in generated config"


class TestGeneratedComments:
    """Validates REQ-d00209-D: Generated TOML includes human-readable comments."""

    def test_REQ_d00209_D_core_config_has_comments(self) -> None:
        """Core config must contain comment lines for every field."""
        content = generate_config("core")
        comment_lines = [line for line in content.splitlines() if line.strip().startswith("#")]
        # With per-field comments, expect at least one comment per schema field
        assert (
            len(comment_lines) >= 40
        ), f"Expected at least 40 comment lines (per-field), got {len(comment_lines)}"

    def test_REQ_d00209_D_associated_config_has_comments(self) -> None:
        """Associated config must contain comment lines."""
        content = generate_config("associated", associated_prefix="TST")
        comment_lines = [line for line in content.splitlines() if line.strip().startswith("#")]
        assert (
            len(comment_lines) >= 3
        ), f"Expected at least 3 comment lines, got {len(comment_lines)}"

    def test_REQ_d00209_D_core_comments_describe_sections(self) -> None:
        """Core config comments should include descriptive text, not just markers."""
        content = generate_config("core")
        # Check that comments contain actual words (not just empty # lines)
        descriptive_comments = [
            line
            for line in content.splitlines()
            if line.strip().startswith("#") and len(line.strip()) > 2
        ]
        assert (
            len(descriptive_comments) >= 3
        ), f"Expected at least 3 descriptive comments, got {len(descriptive_comments)}"

    def test_REQ_d00209_D_no_commented_out_fields(self) -> None:
        """All schema fields appear as real values, none commented out."""
        content = generate_config("core")
        parsed = tomlkit.parse(content)
        config = ElspaisConfig.model_validate(dict(parsed))
        # Fields that were previously None-default are now explicit
        assert config.id_patterns.component.pattern == ""
        assert config.id_patterns.component.max_length == 0
        assert config.id_patterns.assertions.zero_pad is False
        assert config.validation.hash_algorithm == "sha256"
        assert config.validation.hash_length == 8
        assert config.validation.strict_hierarchy is False

    def test_REQ_d00209_D_section_comments_present(self) -> None:
        """Each major section should have a preceding comment explaining it.

        A schema-driven generator should emit a comment before each section
        describing its purpose, derived from the Pydantic field descriptions
        or model docstrings.
        """
        content = generate_config("core")
        lines = content.splitlines()
        sections_with_comments = 0
        for i, line in enumerate(lines):
            if line.startswith("[") and not line.startswith("[["):
                # Check if prior non-blank line is a comment
                for j in range(i - 1, max(i - 3, -1), -1):
                    if lines[j].strip().startswith("#"):
                        sections_with_comments += 1
                        break
                    elif lines[j].strip():
                        break

        # Count total top-level sections (not sub-tables like [rules.hierarchy])
        total_sections = sum(
            1
            for line in lines
            if line.startswith("[") and not line.startswith("[[") and "." not in line.split("]")[0]
        )
        # At least half the sections should have comments
        assert (
            sections_with_comments >= total_sections // 2
        ), f"Only {sections_with_comments}/{total_sections} sections have comments"


class TestTermsConfigInTemplate:
    """Validates REQ-d00212-L: Init template reflects nested terms config."""

    def test_REQ_d00212_L_terms_severity_nested_in_template(self) -> None:
        """Init template generates [terms.severity] sub-table."""
        content = generate_config("core")
        assert "[terms.severity]" in content

    def test_REQ_d00212_L_terms_markup_styles_in_template(self) -> None:
        """Init template includes markup_styles field."""
        content = generate_config("core")
        assert "markup_styles" in content

    def test_REQ_d00212_L_terms_exclude_files_in_template(self) -> None:
        """Init template includes exclude_files field."""
        content = generate_config("core")
        assert "exclude_files" in content

    def test_REQ_d00212_L_no_flat_severity_in_template(self) -> None:
        """Init template does NOT contain old flat severity keys."""
        content = generate_config("core")
        assert "duplicate_severity" not in content
        assert "undefined_severity" not in content
        assert "unmarked_severity" not in content

    def test_REQ_d00212_L_terms_severity_has_all_fields(self) -> None:
        """Init template [terms.severity] has all 6 severity fields."""
        content = generate_config("core")
        parsed = tomlkit.parse(content)
        severity = parsed["terms"]["severity"]
        assert severity["duplicate"] == "error"
        assert severity["undefined"] == "warning"
        assert severity["unmarked"] == "warning"
        assert severity["unused"] == "warning"
        assert severity["bad_definition"] == "error"
        assert severity["collection_empty"] == "warning"
