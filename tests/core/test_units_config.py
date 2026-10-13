"""Tests for a test target's `units` table and a probe's `affects_retention` setting."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from elspais.config.schema import TestTargetConfig
from elspais.utilities.fingerprint import configuration_digest

_DECLARED = {"dependencies": {"source": "declared"}}


def _target(**extra) -> TestTargetConfig:
    fields = {"name": "unit", "reporter": "junit", "results": "junit.xml"}
    fields.update(extra)
    return TestTargetConfig(**fields)


# Verifies: REQ-d00333-C, REQ-d00249-O
def test_a_target_declares_units_and_the_source_of_their_evidence():
    target = _target(command="pytest {selection}", units=_DECLARED)
    assert target.units is not None
    assert target.units.source_name() == "declared"
    assert target.units.receives == "placeholder"


# Verifies: REQ-d00249-O
def test_a_command_reading_the_selection_file_needs_no_placeholder():
    target = _target(command="pytest", units={**_DECLARED, "receives": "file"})
    assert target.units.receives == "file"


# Verifies: REQ-d00249-O
@pytest.mark.parametrize(
    ("fields", "says"),
    [
        ({"command": "pytest {selection}"}, "only a target declaring units replaces"),
        ({"command": "pytest", "units": _DECLARED}, "does not hold it"),
        (
            {"command": "pytest {selection}", "units": {**_DECLARED, "receives": "file"}},
            "would reach the shell",
        ),
        ({"units": _DECLARED}, "need a command"),
        ({"command": "pytest {selection}", "units": {**_DECLARED, "receives": "argv"}}, "receives"),
        (
            {"command": "pytest {selection}", "units": _DECLARED, "results": ""},
            "need a results pattern",
        ),
        (
            {"command": "pytest {selection}", "units": _DECLARED, "file_results": True},
            "file_results",
        ),
    ],
)
def test_a_selection_no_command_can_receive_is_refused(fields, says):
    with pytest.raises(ValidationError) as caught:
        _target(**fields)
    assert says in str(caught.value)


# Verifies: REQ-d00333-C
@pytest.mark.parametrize(
    ("fields", "says"),
    [
        ({"units": {"dependencies": {}}}, "needs a source"),
        ({"units": {"dependencies": {"source": "imports:cobol"}}}, "no dependency source named"),
        (
            {"units": {"dependencies": {"source": "declared", "command": "x"}}},
            "does not suit the 'declared' source",
        ),
        ({"units": {"dependencies": {"source": "command"}}}, "does not suit the 'command'"),
        (
            {"units": {"dependencies": {"source": "command", "command": "deps"}}},
            "set units.observes",
        ),
    ],
)
def test_a_units_table_the_run_cannot_honour_is_refused(fields, says):
    base = {"command": "pytest {selection}", "units": _DECLARED}
    base.update(fields)
    with pytest.raises(ValidationError) as caught:
        _target(**base)
    assert says in str(caught.value)


# Verifies: REQ-d00333-C
def test_a_command_source_with_declared_observes_is_admitted():
    target = _target(
        command="pytest {selection}",
        units={
            "dependencies": {"source": "command", "command": "tools/deps"},
            "observes": {"directories": ["lib", "test"]},
        },
    )
    assert target.units.source_settings().command == "tools/deps"


# Verifies: REQ-d00312-A
@pytest.mark.parametrize("field", ["results", "coverage"])
def test_a_results_or_coverage_path_naming_an_elspais_file_is_refused(field):
    with pytest.raises(ValidationError) as caught:
        _target(**{field: ".elspais-retained.jsonl"})
    assert "names a file elspais writes" in str(caught.value)


# Verifies: REQ-d00333-K, REQ-d00311-R
def test_retention_settings_leave_the_configuration_digest_unchanged():
    plain = _target(
        command="pytest {selection}",
        units=_DECLARED,
        environment_probes=[{"name": "py", "command": "python -V"}],
    )
    marked = _target(
        command="pytest {selection}",
        units={"dependencies": {"source": "command", "command": "tools/deps"}, "observes": {}},
        environment_probes=[{"name": "py", "command": "python -V", "affects_retention": False}],
    )
    assert configuration_digest(plain) == configuration_digest(marked)
    other = _target(
        command="pytest {selection}",
        units=_DECLARED,
        environment_probes=[{"name": "py", "command": "python3 -V"}],
    )
    assert configuration_digest(plain) != configuration_digest(other)


# Verifies: REQ-d00311-R
def test_the_selection_a_whole_run_executes_is_part_of_the_configuration_digest():
    plain = _target(command="pytest {selection}", units=_DECLARED)
    changed = _target(command="pytest {selection}", units={**_DECLARED, "full_selection": "tests"})
    assert configuration_digest(plain) != configuration_digest(changed)


# Verifies: REQ-d00333-C
def test_a_units_table_selects_the_test_files_its_command_executes():
    target = _target(
        command="pytest {selection}",
        units={**_DECLARED, "tests": {"directories": ["tests"], "file_patterns": ["test_*.py"]}},
    )
    assert target.units.tests.directories == ["tests"]
    assert target.units.tests.file_patterns == ["test_*.py"]
    with pytest.raises(ValidationError) as caught:
        _target(
            command="pytest {selection}",
            units={**_DECLARED, "tests": {"directories": ["tests"], "patterns": ["*.py"]}},
        )
    assert "units.tests.patterns" in str(caught.value)


# Verifies: REQ-d00311-R
def test_the_test_files_a_units_target_selects_are_part_of_the_configuration_digest():
    plain = _target(command="pytest {selection}", units=_DECLARED)
    selected = _target(
        command="pytest {selection}",
        units={**_DECLARED, "tests": {"file_patterns": ["test_*.py"]}},
    )
    assert configuration_digest(plain) != configuration_digest(selected)
