# Verifies: REQ-d00249-A
"""Schema validation for [[scanning.test.runners]]."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from elspais.config.schema import ElspaisConfig


def test_runners_default_is_empty_list():
    cfg = ElspaisConfig()
    assert cfg.scanning.test.runners == []


def test_runners_accepts_minimal_entry():
    cfg = ElspaisConfig.model_validate(
        {
            "scanning": {
                "test": {
                    "runners": [{"name": "py", "command": "pytest"}],
                }
            }
        }
    )
    assert len(cfg.scanning.test.runners) == 1
    assert cfg.scanning.test.runners[0].name == "py"
    assert cfg.scanning.test.runners[0].command == "pytest"
    assert cfg.scanning.test.runners[0].cwd == ""


def test_runners_accepts_cwd_override():
    cfg = ElspaisConfig.model_validate(
        {
            "scanning": {
                "test": {
                    "runners": [{"name": "flutter", "command": "flutter test", "cwd": "app"}],
                }
            }
        }
    )
    assert cfg.scanning.test.runners[0].cwd == "app"


def test_runners_rejects_unknown_field():
    with pytest.raises(ValidationError):
        ElspaisConfig.model_validate(
            {
                "scanning": {
                    "test": {
                        "runners": [{"name": "py", "command": "pytest", "shell": "bash"}],
                    }
                }
            }
        )


def test_runners_rejects_missing_command():
    with pytest.raises(ValidationError):
        ElspaisConfig.model_validate({"scanning": {"test": {"runners": [{"name": "py"}]}}})
