"""Tests for the [federation] config table.

Implements: REQ-d00253-A
"""

from elspais.config.schema import ElspaisConfig, FederationConfig


def test_federation_defaults_are_false():
    cfg = ElspaisConfig()
    assert cfg.federation.write_associates is False
    assert cfg.federation.index_associates is False


def test_federation_parses_from_dict():
    cfg = ElspaisConfig.model_validate(
        {"federation": {"write_associates": True, "index_associates": True}}
    )
    assert cfg.federation.write_associates is True
    assert cfg.federation.index_associates is True


def test_federation_dump_structure():
    dumped = ElspaisConfig().model_dump(by_alias=True)
    assert dumped["federation"] == {
        "write_associates": False,
        "index_associates": False,
    }


def test_federation_rejects_unknown_field():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        FederationConfig(bogus=True)
