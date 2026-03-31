"""Tests for the Pydantic config schema."""

import pytest


# Verifies: REQ-d00207-A
def test_default_config_preserves_legacy_values():
    """ElspaisConfig defaults must preserve all DEFAULT_CONFIG values."""
    from elspais.config import config_defaults
    from elspais.config.schema import ElspaisConfig

    config = ElspaisConfig()
    dumped = config.model_dump(by_alias=True)

    def _check_subset(legacy: dict, schema: dict, path: str = "") -> list[str]:
        errors = []
        for k, v in legacy.items():
            full = f"{path}.{k}" if path else k
            if k not in schema:
                errors.append(f"Missing key: {full}")
            elif isinstance(v, dict) and isinstance(schema[k], dict):
                errors.extend(_check_subset(v, schema[k], full))
            elif schema[k] != v:
                errors.append(f"Value mismatch at {full}: {v!r} != {schema[k]!r}")
        return errors

    errors = _check_subset(config_defaults(), dumped)
    assert not errors, "Schema/legacy mismatches:\n" + "\n".join(errors)


# Verifies: REQ-d00212-F
def test_unknown_key_rejected():
    """Unknown keys in TOML must raise ValidationError."""
    from pydantic import ValidationError

    from elspais.config.schema import ElspaisConfig

    with pytest.raises(ValidationError, match="extra_forbidden"):
        ElspaisConfig.model_validate({"bogus_key": "value"})


# Verifies: REQ-d00212-C
def test_unknown_nested_key_rejected():
    """Unknown nested keys must raise ValidationError with field path."""
    from pydantic import ValidationError

    from elspais.config.schema import ElspaisConfig

    with pytest.raises(ValidationError, match="scanning"):
        ElspaisConfig.model_validate({"scanning": {"bogus_nested": True}})


# Verifies: REQ-d00212-G
def test_hyphenated_keys_accepted():
    """TOML hyphenated keys (e.g. 'id-patterns') accepted via aliases."""
    from elspais.config.schema import ElspaisConfig

    config = ElspaisConfig.model_validate(
        {"id-patterns": {"canonical": "CUSTOM-{type.letter}{component}"}},
    )
    assert config.id_patterns.canonical == "CUSTOM-{type.letter}{component}"


# Verifies: REQ-d00212-F
def test_type_mismatch_rejected():
    """Wrong types must raise ValidationError."""
    from pydantic import ValidationError

    from elspais.config.schema import ElspaisConfig

    with pytest.raises(ValidationError):
        ElspaisConfig.model_validate({"version": "not-an-int"})


# Verifies: REQ-d00212-F
def test_unknown_top_level_key_rejected():
    """Unknown top-level keys like 'core' must fail."""
    from pydantic import ValidationError

    from elspais.config.schema import ElspaisConfig

    with pytest.raises(ValidationError, match="extra_forbidden"):
        ElspaisConfig.model_validate(
            {
                "core": {"path": "../core"},
            }
        )


# Verifies: REQ-d00212-J
def test_project_namespace_accepted():
    """project.namespace is a valid field."""
    from elspais.config.schema import ElspaisConfig

    config = ElspaisConfig.model_validate(
        {
            "project": {"namespace": "MYNS"},
        }
    )
    assert config.project.namespace == "MYNS"


# Verifies: REQ-d00212-F
def test_status_roles_custom_values():
    """status_roles with custom values should validate."""
    from elspais.config.schema import ElspaisConfig

    config = ElspaisConfig.model_validate(
        {
            "rules": {
                "format": {
                    "status_roles": {"active": ["Active"], "provisional": ["Draft"]},
                },
            },
        }
    )
    assert config.rules.format.status_roles == {
        "active": ["Active"],
        "provisional": ["Draft"],
    }


class TestProtectedBranches:
    """REQ-d00207-A: Config schema supports protected_branches."""

    def test_default_protected_branches(self):
        """RulesConfig has default protected_branches."""
        from elspais.config.schema import RulesConfig

        rules = RulesConfig()
        assert rules.protected_branches == ["main", "master"]

    def test_custom_protected_branches(self):
        """RulesConfig accepts custom protected_branches with globs."""
        from elspais.config.schema import RulesConfig

        rules = RulesConfig(protected_branches=["main", "release/*"])
        assert rules.protected_branches == ["main", "release/*"]

    def test_config_version_is_4(self):
        """ElspaisConfig version bumped to 4."""
        from elspais.config.schema import ElspaisConfig

        cfg = ElspaisConfig()
        assert cfg.version == 4
