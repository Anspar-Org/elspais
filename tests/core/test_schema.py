"""Tests for the Pydantic config schema."""

import pytest


def test_default_config_preserves_legacy_values():
    """ElspaisConfig defaults must preserve all DEFAULT_CONFIG values."""
    from elspais.config import DEFAULT_CONFIG
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

    errors = _check_subset(DEFAULT_CONFIG, dumped)
    assert not errors, "Schema/legacy mismatches:\n" + "\n".join(errors)


def test_unknown_key_rejected():
    """Unknown keys in TOML must raise ValidationError."""
    from pydantic import ValidationError

    from elspais.config.schema import ElspaisConfig

    with pytest.raises(ValidationError, match="extra_forbidden"):
        ElspaisConfig.model_validate({"bogus_key": "value"})


def test_unknown_nested_key_rejected():
    """Unknown nested keys must raise ValidationError with field path."""
    from pydantic import ValidationError

    from elspais.config.schema import ElspaisConfig

    with pytest.raises(ValidationError, match="spec"):
        ElspaisConfig.model_validate({"spec": {"bogus_nested": True}})


def test_hyphenated_keys_accepted():
    """TOML hyphenated keys (e.g. 'id-patterns') accepted via aliases."""
    from elspais.config.schema import ElspaisConfig

    config = ElspaisConfig.model_validate(
        {"id-patterns": {"canonical": "CUSTOM-{type.letter}{component}"}},
    )
    assert config.id_patterns.canonical == "CUSTOM-{type.letter}{component}"


def test_type_mismatch_rejected():
    """Wrong types must raise ValidationError."""
    from pydantic import ValidationError

    from elspais.config.schema import ElspaisConfig

    with pytest.raises(ValidationError):
        ElspaisConfig.model_validate({"version": "not-an-int"})


def test_associated_requires_core():
    """project.type='associated' without [core] must fail."""
    from pydantic import ValidationError

    from elspais.config.schema import ElspaisConfig

    with pytest.raises(ValidationError, match="core"):
        ElspaisConfig.model_validate(
            {
                "project": {"type": "associated"},
            }
        )


def test_associated_with_core_passes():
    """project.type='associated' with [core] must pass."""
    from elspais.config.schema import ElspaisConfig

    config = ElspaisConfig.model_validate(
        {
            "project": {"type": "associated"},
            "core": {"path": "../core"},
        }
    )
    assert config.core is not None
    assert config.core.path == "../core"


def test_status_roles_reference_allowed_statuses():
    """status_roles referencing known statuses should work."""
    from elspais.config.schema import ElspaisConfig

    config = ElspaisConfig.model_validate(
        {
            "rules": {
                "format": {
                    "allowed_statuses": ["Active", "Draft"],
                    "status_roles": {"active": ["Active"], "provisional": ["Draft"]},
                },
            },
        }
    )
    assert config.rules.format.allowed_statuses == ["Active", "Draft"]
