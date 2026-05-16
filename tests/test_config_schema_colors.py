"""Schema validation for optional color fields on levels, namespaces, statuses."""

# Verifies: REQ-d00212-A, REQ-d00212-J, REQ-d00212-K

from __future__ import annotations

import pytest
from pydantic import ValidationError

from elspais.config.schema import ElspaisConfig


def test_color_fields_default_to_none():
    cfg = ElspaisConfig()
    assert cfg.project.color is None
    assert cfg.levels["prd"].color is None
    assert cfg.statuses == {}


def test_project_color_accepts_hex():
    cfg = ElspaisConfig.model_validate({"project": {"color": "#1b3a5c"}})
    assert cfg.project.color == "#1b3a5c"


def test_level_color_accepts_hex():
    cfg = ElspaisConfig.model_validate(
        {"levels": {"gui": {"rank": 4, "letter": "g", "implements": ["gui"], "color": "#7c3aed"}}}
    )
    assert cfg.levels["gui"].color == "#7c3aed"


def test_associate_color_accepts_hex():
    cfg = ElspaisConfig.model_validate(
        {"associates": {"diary": {"path": ".", "namespace": "DIARY", "color": "#fed321"}}}
    )
    assert cfg.associates["diary"].color == "#fed321"


def test_statuses_table_optional_color():
    cfg = ElspaisConfig.model_validate({"statuses": {"Active": {"color": "#198754"}, "Legacy": {}}})
    assert cfg.statuses["Active"].color == "#198754"
    assert cfg.statuses["Legacy"].color is None


@pytest.mark.parametrize("bad", ["red", "#abc", "#abcdefg", "123abc", "", "#GGHHII"])
def test_color_rejects_invalid_hex(bad):
    with pytest.raises(ValidationError):
        ElspaisConfig.model_validate({"project": {"color": bad}})


def test_uppercase_hex_accepted():
    cfg = ElspaisConfig.model_validate({"project": {"color": "#1B3A5C"}})
    assert cfg.project.color == "#1B3A5C"


def test_statuses_dict_rejects_unknown_field():
    with pytest.raises(ValidationError):
        ElspaisConfig.model_validate({"statuses": {"Active": {"color": "#198754", "extra": "no"}}})
