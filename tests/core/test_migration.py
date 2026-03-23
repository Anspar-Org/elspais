"""Tests for version-gated config migration."""

import copy


# Implements: REQ-d00212-A
def test_v1_patterns_migrated_to_v2():
    """Legacy [patterns] config should be migrated to [id-patterns]."""
    from elspais.config import _migrate_legacy_patterns

    v1_config = {
        "patterns": {
            "prefix": "PROJ",
            "types": {
                "prd": {"level": 1, "id": "p"},
                "ops": {"level": 2, "id": "o"},
            },
            "id_template": "{prefix}-{type}{id}",
            "id_format": {"style": "numeric", "digits": 5, "leading_zeros": True},
        },
    }

    result = _migrate_legacy_patterns(v1_config)
    assert "id-patterns" in result
    assert "levels" in result
    assert result["levels"]["prd"]["rank"] == 1


# Implements: REQ-d00207-B
def test_v2_config_skips_migration():
    """v2+ configs should not be migrated."""
    from elspais.config import _migrate_legacy_patterns

    v2_config = {"version": 2, "id-patterns": {"canonical": "custom"}}
    result = _migrate_legacy_patterns(v2_config)
    assert result["id-patterns"]["canonical"] == "custom"


# Implements: REQ-d00212-F
def test_migration_produces_valid_schema():
    """Migrated config must pass Pydantic validation."""
    from elspais.config import _merge_configs, _migrate_legacy_patterns, config_defaults
    from elspais.config.schema import ElspaisConfig

    v1_config = {
        "patterns": {
            "prefix": "TEST",
            "types": {
                "prd": {"level": 1, "id": "p"},
                "ops": {"level": 2, "id": "o"},
                "dev": {"level": 3, "id": "d"},
            },
            "id_template": "{prefix}-{type}{id}",
            "id_format": {"style": "numeric", "digits": 5, "leading_zeros": True},
        },
    }

    defaults = copy.deepcopy(config_defaults())
    # Remove version so migration treats this as a v1 config
    defaults.pop("version", None)
    merged = _merge_configs(defaults, v1_config)
    migrated = _migrate_legacy_patterns(merged)

    # Remove 'patterns' key (legacy, not in schema)
    migrated.pop("patterns", None)

    # Should validate cleanly
    config = ElspaisConfig.model_validate(migrated, by_alias=True)
    assert config.project.namespace == "TEST"
