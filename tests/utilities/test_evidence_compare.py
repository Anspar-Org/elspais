# Verifies: REQ-d00322-H, REQ-d00322-M
"""Comparing a committed *Evidence Snapshot* with one derived from a new run."""

from __future__ import annotations

import dataclasses
from pathlib import Path

from elspais.utilities.evidence import (
    Difference,
    ResultLine,
    Snapshot,
    Timing,
    compare,
    load_snapshot,
    render_files,
)

_REPORT = "# Traceability Matrix\n\n| ID |\n|----|"


def _line(outcome: str = "passed", *, runner: str | None = "test/a_test.dart", line: int = 3):
    return ResultLine(
        target="flutter",
        file="test/shared.dart",
        line=line,
        name="boots",
        runner=runner,
        outcome=outcome,
    )


def _snapshot(*results: ResultLine, **changes) -> Snapshot:
    base = Snapshot(
        results=results,
        tree="t" * 64,
        targets=(("flutter", "d" * 64),),
        facts=(("backends", "vm"),),
        elspais="0.0.0",
        timings=(),
        report=_REPORT,
    )
    return dataclasses.replace(base, **changes)


def _committed(tmp_path: Path, snapshot: Snapshot) -> Snapshot:
    """The snapshot as a reader of the committed files holds it."""
    for name, text in render_files(snapshot).items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    return load_snapshot(tmp_path)


# Verifies: REQ-d00322-H
def test_a_committed_snapshot_agrees_with_the_run_it_was_written_from(tmp_path):
    current = _snapshot(_line(), _line(runner="test/b_test.dart"))

    assert compare(_committed(tmp_path, current), current) == []


# Verifies: REQ-d00322-H
def test_a_changed_outcome_names_the_test_and_both_outcomes(tmp_path):
    committed = _committed(tmp_path, _snapshot(_line("passed")))

    assert compare(committed, _snapshot(_line("failed"))) == [
        Difference(
            "outcome",
            "target flutter: test/shared.dart:3 boots (test/a_test.dart): passed -> failed",
        )
    ]


# Verifies: REQ-d00322-H
def test_a_run_present_on_one_side_only_is_counted_not_merged(tmp_path):
    """Review Focus 4: two identical runs are two runs, so losing one is a difference."""
    twice = _snapshot(_line(), _line())
    once = _snapshot(_line())

    assert compare(twice, once) == [
        Difference(
            "only_committed", "target flutter: test/shared.dart:3 boots (test/a_test.dart): passed"
        )
    ]
    assert compare(once, twice) == [
        Difference(
            "only_current", "target flutter: test/shared.dart:3 boots (test/a_test.dart): passed"
        )
    ]


# Verifies: REQ-d00322-H
def test_a_run_that_changed_beside_one_that_did_not_is_one_outcome_difference():
    committed = _snapshot(_line("passed"), _line("passed"))
    current = _snapshot(_line("passed"), _line("failed"))

    assert [d.kind for d in compare(committed, current)] == ["outcome"]


# Verifies: REQ-d00322-H
def test_a_test_known_by_another_place_is_on_one_side_only():
    committed = _snapshot(_line(line=3))
    current = _snapshot(_line(line=4))

    assert [d.kind for d in compare(committed, current)] == ["only_committed", "only_current"]


# Verifies: REQ-d00322-H
def test_a_different_tree_is_reported():
    differences = compare(_snapshot(), _snapshot(tree="u" * 64))

    assert [d.kind for d in differences] == ["tree"]
    assert "u" * 64 in differences[0].detail


# Verifies: REQ-d00322-H
def test_a_different_fact_is_reported_by_name():
    differences = compare(
        _snapshot(), _snapshot(facts=(("backends", "other"), ("flutter", "3.44.7")))
    )

    assert differences == [
        Difference("fact", "backends: 'vm' -> 'other'"),
        Difference("fact", "flutter: absent -> '3.44.7'"),
    ]


# Verifies: REQ-d00322-H
def test_a_targets_input_digest_that_differs_is_reported():
    differences = compare(_snapshot(), _snapshot(targets=(("flutter", "e" * 64),)))

    assert [(d.kind, d.detail.split(":")[0]) for d in differences] == [("target", "flutter")]


# Verifies: REQ-d00322-H
def test_a_different_report_is_reported():
    differences = compare(_snapshot(), _snapshot(report=_REPORT + "\nmore"))

    assert [d.kind for d in differences] == ["report"]


# Verifies: REQ-d00322-M
def test_durations_and_printed_output_are_never_compared():
    timing = Timing(
        target="flutter",
        file="test/shared.dart",
        line=3,
        name="boots",
        runner="test/a_test.dart",
        duration=1.5,
        output="ratio 0.9x",
    )
    slower = dataclasses.replace(timing, duration=9.0, output="ratio 0.2x")

    assert (
        compare(_snapshot(_line(), timings=(timing,)), _snapshot(_line(), timings=(slower,))) == []
    )


# Verifies: REQ-d00322-H
def test_differences_are_ordered_by_kind_then_detail():
    committed = _snapshot(_line("passed"), tree="t" * 64)
    current = _snapshot(_line("failed"), tree="u" * 64, facts=())

    assert [d.kind for d in compare(committed, current)] == ["fact", "outcome", "tree"]
