"""Tests for the per-unit retention judgement, the Unit Ledger, and the earlier run it reads."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from elspais.graph.dependencies import Evidence
from elspais.utilities.evidence import ResultLine
from elspais.utilities.fingerprint import Freshness
from elspais.utilities.retention import (
    NO_EVIDENCE_REASON,
    RETAINED_REASON,
    Ledger,
    UnitEntry,
    judge_units,
    ledger_refusal,
    read_ledger,
    units_digest,
    write_ledger,
)

_RUN = {"commit": "abc", "root": "/ci/work", "started_at": "2026-10-11T09:14:00+00:00"}
_A, _B = "tests/a_test.py", "tests/b_test.py"


def _entry(unit: str, outcome: str = "passed", **observed: str) -> UnitEntry:
    line = ResultLine(target="t", file=unit, line=3, name="x", runner=None, outcome=outcome)
    recorded = {unit: "d-" + unit, **{k.replace("__", "/"): v for k, v in observed.items()}}
    return UnitEntry(
        unit=unit, executed_in=dict(_RUN), outcome=outcome, observed=recorded, results=(line,)
    )


def _ledger(*entries: UnitEntry) -> Ledger:
    return Ledger(
        target="t",
        units_digest="u",
        source="declared",
        written_by=dict(_RUN),
        units={e.unit: e for e in entries},
    )


def _manifest(**extra: str) -> dict[str, str]:
    return {_A: "d-" + _A, _B: "d-" + _B, "src/lib.py": "lib", "/environment/py": "p", **extra}


_OBSERVED = frozenset({_A, _B})
_DECLARED = Evidence(files={_A: frozenset({_A}), _B: frozenset({_B})})


# Verifies: REQ-d00333-B
def test_a_unit_whose_evidence_is_unchanged_is_retained():
    judgement = judge_units(
        (_A, _B), _ledger(_entry(_A), _entry(_B)), _manifest(), _manifest(), _OBSERVED, _DECLARED
    )
    assert judgement.selected == {}
    assert set(judgement.retained) == {_A, _B}
    assert judgement.retained[_A].retained_reason == RETAINED_REASON
    assert judgement.retained[_A].executed_in == _RUN


# Verifies: REQ-d00333-B
def test_a_changed_observed_file_executes_only_the_units_that_reach_it():
    current = _manifest(**{_A: "changed"})
    judgement = judge_units(
        (_A, _B), _ledger(_entry(_A), _entry(_B)), _manifest(), current, _OBSERVED, _DECLARED
    )
    assert set(judgement.selected) == {_A}
    assert _A in judgement.selected[_A]
    assert set(judgement.retained) == {_B}


# Verifies: REQ-d00333-B
def test_a_changed_unobserved_input_executes_every_unit_naming_it():
    current = _manifest(**{"src/lib.py": "new"})
    judgement = judge_units(
        (_A, _B), _ledger(_entry(_A), _entry(_B)), _manifest(), current, _OBSERVED, _DECLARED
    )
    assert set(judgement.selected) == {_A, _B}
    assert "src/lib.py changed" in judgement.selected[_A]


# Verifies: REQ-d00333-B, REQ-d00311-R
def test_a_changed_environment_executes_every_unit():
    current = _manifest(**{"/environment/py": "q"})
    judgement = judge_units((_A,), _ledger(_entry(_A)), _manifest(), current, _OBSERVED, _DECLARED)
    assert "environment probe 'py' changed" in judgement.selected[_A]


# Verifies: REQ-d00333-K
def test_a_probe_declared_to_leave_retention_unaffected_executes_nothing():
    current = _manifest(**{"/environment/py": "q"})
    judgement = judge_units(
        (_A,),
        _ledger(_entry(_A)),
        _manifest(),
        current,
        _OBSERVED,
        _DECLARED,
        frozenset({"/environment/py"}),
    )
    assert set(judgement.retained) == {_A}


# Verifies: REQ-d00333-G
@pytest.mark.parametrize("outcome", ["failed", "no-result"])
def test_a_unit_whose_last_execution_did_not_pass_or_skip_executes(outcome):
    judgement = judge_units(
        (_A,), _ledger(_entry(_A, outcome)), _manifest(), _manifest(), _OBSERVED, _DECLARED
    )
    assert set(judgement.selected) == {_A}


# Verifies: REQ-d00333-G
def test_a_skipped_unit_is_retained():
    judgement = judge_units(
        (_A,), _ledger(_entry(_A, "skipped")), _manifest(), _manifest(), _OBSERVED, _DECLARED
    )
    assert set(judgement.retained) == {_A}


# Verifies: REQ-d00333-B
def test_a_test_file_the_ledger_does_not_hold_executes():
    judgement = judge_units(
        (_A, _B), _ledger(_entry(_A)), _manifest(), _manifest(), _OBSERVED, _DECLARED
    )
    assert judgement.selected == {_B: "a new test file"}


# Verifies: REQ-d00333-B
def test_an_observed_file_newly_reached_without_a_recorded_digest_counts_as_changed():
    evidence = Evidence(files={_A: frozenset({_A, "lib/helper.py"})})
    observed = _OBSERVED | {"lib/helper.py"}
    current = _manifest(**{"lib/helper.py": "h"})
    judgement = judge_units((_A,), _ledger(_entry(_A)), current, current, observed, evidence)
    assert "lib/helper.py" in judgement.selected[_A]


# Verifies: REQ-d00333-B
def test_a_file_outside_the_inputs_that_a_unit_reaches_always_counts_as_changed():
    evidence = Evidence(files={_A: frozenset({_A, "vendor/x.py"})})
    judgement = judge_units(
        (_A,), _ledger(_entry(_A)), _manifest(), _manifest(), _OBSERVED, evidence
    )
    assert "vendor/x.py" in judgement.selected[_A]


# Verifies: REQ-d00333-B
def test_an_unobserved_input_a_unit_reaches_is_judged_with_the_other_unobserved_inputs():
    evidence = Evidence(files={_A: frozenset({_A, "src/lib.py"})})
    judgement = judge_units(
        (_A,), _ledger(_entry(_A)), _manifest(), _manifest(), _OBSERVED, evidence
    )
    assert set(judgement.retained) == {_A}


# Verifies: REQ-d00333-B
def test_a_deleted_observed_file_executes_only_the_units_that_reached_it():
    entry_a = _entry(_A, **{"tests__gone_test.py": "g"})
    last = _manifest(**{"tests/gone_test.py": "g"})
    judgement = judge_units(
        (_A, _B), _ledger(entry_a, _entry(_B)), last, _manifest(), _OBSERVED, _DECLARED
    )
    assert set(judgement.selected) == {_A}
    assert set(judgement.retained) == {_B}


# Verifies: REQ-d00333-B
def test_a_ledger_reads_back_as_it_was_written(tmp_path):
    ledger = _ledger(_entry(_A), _entry(_B, "skipped"))
    write_ledger(tmp_path, ledger)
    assert read_ledger(tmp_path) == ledger


# Verifies: REQ-d00333-B
@pytest.mark.parametrize("text", ["", "not json", '{"version": 2}', '{"version": 1, "units": []}'])
def test_a_ledger_that_cannot_be_read_reads_as_none(tmp_path, text):
    (tmp_path / ".elspais-units.json").write_text(text, encoding="utf-8")
    assert read_ledger(tmp_path) is None


def _target(units: dict | None = None):
    return SimpleNamespace(
        units=SimpleNamespace(model_dump=lambda mode: units or {"dependencies": {"source": "d"}})
    )


def _verdict(**fingerprint) -> Freshness:
    recorded = {**_RUN, "finished_at": "2026-10-11T09:20:00+00:00", "manifest": {}}
    recorded.update(fingerprint)
    return Freshness(target="t", state="stale", reason="changed", fingerprint=recorded)


# Verifies: REQ-d00333-E
@pytest.mark.parametrize(
    ("verdict", "says"),
    [
        (Freshness(target="t", state="absent"), "no earlier run"),
        (Freshness(target="t", state="running"), "in progress"),
        (_verdict(finished_at=""), "recorded no end"),
        (_verdict(changed_during_run=["src/lib.py"]), "changed while it ran"),
        (_verdict(started_at="2026-10-12T00:00:00+00:00"), "another run"),
    ],
)
def test_an_earlier_run_that_cannot_be_retained_from_is_refused_naming_why(verdict, says):
    target = _target()
    ledger = Ledger("t", units_digest(target), "declared", dict(_RUN), {})
    assert says in ledger_refusal(ledger, verdict, target, "declared")


# Verifies: REQ-d00333-E
def test_a_ledger_of_another_units_table_or_source_is_refused():
    target = _target()
    ledger = Ledger("t", "other", "declared", dict(_RUN), {})
    assert "units table changed" in ledger_refusal(ledger, _verdict(), target, "declared")
    ledger = Ledger("t", units_digest(target), "command", dict(_RUN), {})
    assert "dependency source changed" in ledger_refusal(ledger, _verdict(), target, "declared")
    ledger = Ledger("t", units_digest(target), "declared", dict(_RUN), {})
    assert ledger_refusal(ledger, _verdict(), target, "declared") == ""


# Verifies: REQ-d00333-B
def test_a_test_file_outside_the_observed_set_is_retained_while_unchanged():
    evidence = Evidence(files={_A: frozenset({_A, "lib/a.py"})})
    observed = frozenset({"lib/a.py"})
    current = _manifest(**{"lib/a.py": "a"})
    entry = _entry(_A, **{"lib__a.py": "a"})

    judgement = judge_units((_A,), _ledger(entry), current, current, observed, evidence)
    assert set(judgement.retained) == {_A}

    changed = dict(current, **{_A: "edited"})
    judgement = judge_units((_A,), _ledger(entry), current, changed, observed, evidence)
    assert _A in judgement.selected[_A]


# Verifies: REQ-d00333-B
def test_a_unit_its_source_gives_no_evidence_for_executes_though_its_own_file_is_unchanged():
    # The source observes lib/a.py, which unit A reached when it last
    # executed, and leaves A out of its answer now. A change to lib/a.py
    # would then reach no unit, so a unit without evidence executes.
    observed = frozenset({"lib/a.py"})
    recorded = _manifest(**{"lib/a.py": "a"})
    changed = dict(recorded, **{"lib/a.py": "edited"})
    entry = _entry(_A, **{"lib__a.py": "a"})
    for current in (recorded, changed):
        judgement = judge_units(
            (_A,), _ledger(entry), recorded, current, observed, Evidence(files={})
        )
        assert judgement.selected == {_A: NO_EVIDENCE_REASON}
        assert judgement.retained == {}


# Verifies: REQ-d00333-B
def test_a_ledger_result_line_of_the_wrong_shape_makes_the_ledger_unreadable(
    tmp_path,
):
    write_ledger(tmp_path, _ledger(_entry(_A)))
    path = tmp_path / ".elspais-units.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["units"][0]["results"][0]["runner"] = 7
    path.write_text(json.dumps(data), encoding="utf-8")
    assert read_ledger(tmp_path) is None
