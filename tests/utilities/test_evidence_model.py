# Verifies: REQ-d00322-C+E+M+N
"""Tests for the *Evidence Snapshot* model, its byte form and reading it back."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from elspais.utilities.evidence import (
    SNAPSHOT_FILES,
    TIMINGS_FILE,
    ResultLine,
    Snapshot,
    SnapshotUnreadable,
    Timing,
    load_snapshot,
    parse_facts,
    render_files,
)


def _line(target, file, line, name, outcome, runner=None, skip_reason=None):
    return ResultLine(
        target=target,
        file=file,
        line=line,
        name=name,
        runner=runner,
        outcome=outcome,
        skip_reason=skip_reason,
    )


def _snapshot(results=(), targets=(("t", "d1"),), facts=(), timings=(), report="# Report\n"):
    return Snapshot(
        results=tuple(results),
        tree="ab" * 32,
        targets=tuple(targets),
        facts=tuple(facts),
        elspais="0.0.0",
        timings=tuple(timings),
        report=report,
    )


def _write(directory: Path, files: dict[str, str]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        with open(directory / name, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
    return directory


# Verifies: REQ-d00322-C, REQ-d00322-E
def test_two_identical_runs_render_identical_bytes():
    a = _snapshot(results=[_line("t", "x_test.dart", 3, "n", "passed")] * 2)
    b = _snapshot(results=[_line("t", "x_test.dart", 3, "n", "passed")] * 2)
    fa, fb = render_files(a), render_files(b)
    assert {k: v for k, v in fa.items() if k != TIMINGS_FILE} == {
        k: v for k, v in fb.items() if k != TIMINGS_FILE
    }
    assert fa["results.jsonl"].count("\n") == 2


# Verifies: REQ-d00322-E
def test_bytes_do_not_depend_on_assembly_order():
    lines = [
        _line("t", "b_test.py", 9, "z", "failed"),
        _line("t", "a_test.py", None, "y", "skipped", skip_reason="tag"),
        _line("s", "a_test.py", 0, "x", "passed", runner="runner.dart"),
    ]
    a = _snapshot(
        results=lines,
        targets=[("t", "d1"), ("s", "d2")],
        facts=[("flutter", "3"), ("backends", "vm")],
    )
    b = _snapshot(
        results=list(reversed(lines)),
        targets=[("s", "d2"), ("t", "d1")],
        facts=[("backends", "vm"), ("flutter", "3")],
    )
    assert render_files(a) == render_files(b)


# Verifies: REQ-d00322-E
def test_an_unknown_line_sorts_before_line_zero():
    zero = _line("t", "a.py", 0, "n", "passed")
    unknown = _line("t", "a.py", None, "n", "passed")
    text = render_files(_snapshot(results=[zero, unknown]))["results.jsonl"]
    assert [json.loads(r).get("line") for r in text.splitlines()] == [None, 0]


# Verifies: REQ-d00322-C
def test_duplicate_results_are_kept_adjacent_and_read_back(tmp_path):
    """Review Focus 4: two runs of one test that agree are two lines."""
    dup = _line("t", "s_test.dart", 4, "scenario", "passed", runner="pg_test.dart")
    other = _line("t", "a_test.dart", 1, "a", "passed")
    files = render_files(_snapshot(results=[dup, other, dup]))
    rows = files["results.jsonl"].splitlines()
    assert len(rows) == 3
    assert rows[1] == rows[2]
    loaded = load_snapshot(_write(tmp_path / "ev", files))
    assert loaded.results.count(dup) == 2


# Verifies: REQ-d00322-C
def test_result_line_omits_absent_fields_and_holds_no_measurement():
    text = render_files(_snapshot(results=[_line("t", "a.py", None, "n", "passed")]))
    assert json.loads(text["results.jsonl"]) == {
        "file": "a.py",
        "name": "n",
        "outcome": "passed",
        "target": "t",
    }


# Verifies: REQ-d00322-C, REQ-d00322-M
def test_round_trip(tmp_path):
    snap = _snapshot(
        results=sorted(
            [
                _line("t", "a_test.py", 3, "n", "passed"),
                _line("t", "a_test.py", 3, "n", "passed"),
                _line("t", "b_test.py", None, "m", "skipped", skip_reason="no db"),
                _line("u", "c_test.dart", 7, "k", "failed", runner="vm_test.dart"),
            ],
            key=ResultLine.key,
        ),
        targets=[("t", "d1"), ("u", "d2")],
        facts=[("backends", "vm,postgres"), ("flutter", "3.44.7")],
        timings=[
            Timing("t", "a_test.py", 3, "n", None, 0.5, "throughput 12/s\n"),
            Timing("u", "c_test.dart", 7, "k", "vm_test.dart", 2, ""),
        ],
        report="# Traceability\n\nbody — \u00e9\n",
    )
    loaded = load_snapshot(_write(tmp_path / "ev", render_files(snap)))
    assert loaded == snap


# Verifies: REQ-d00322-M
def test_timings_are_optional_on_read(tmp_path):
    files = render_files(_snapshot(results=[_line("t", "a.py", 1, "n", "passed")]))
    del files[TIMINGS_FILE]
    assert load_snapshot(_write(tmp_path / "ev", files)).timings == ()


# Verifies: REQ-d00322-M
def test_timings_carry_duration_and_output_outside_the_compared_files():
    files = render_files(
        _snapshot(
            results=[_line("t", "a.py", 1, "n", "passed")],
            timings=[Timing("t", "a.py", 1, "n", None, 1.25, "printed")],
        )
    )
    for name in SNAPSHOT_FILES:
        assert "1.25" not in files[name]
        assert "printed" not in files[name]
    assert json.loads(files[TIMINGS_FILE])["duration"] == 1.25


# Verifies: REQ-d00322-N
def test_no_name_is_a_json_key_in_snapshot_json():
    snap = _snapshot(
        targets=[("api-secret-token", "f" * 64), ("unit", "e" * 64)],
        facts=[("password", "hunter2")],
    )
    meta = json.loads(render_files(snap)["snapshot.json"])

    def keys(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                yield k
                yield from keys(v)
        elif isinstance(obj, list):
            for v in obj:
                yield from keys(v)

    found = set(keys(meta))
    assert found == {"elspais", "facts", "targets", "tree", "digest", "target", "name", "value"}
    assert meta["targets"] == [
        {"digest": "f" * 64, "target": "api-secret-token"},
        {"digest": "e" * 64, "target": "unit"},
    ]


# Verifies: REQ-d00322-E
def test_every_file_ends_with_exactly_one_newline():
    files = render_files(
        _snapshot(
            results=[_line("t", "a.py", 1, "n", "passed")],
            timings=[Timing("t", "a.py", 1, "n", None, 1.0, "")],
            report="# no trailing newline",
        )
    )
    for name, text in files.items():
        assert text.endswith("\n") and not text.endswith("\n\n"), name
    assert render_files(_snapshot(report="x\n"))["TRACEABILITY.md"] == "x\n"


# Verifies: REQ-d00322-C
@pytest.mark.parametrize("missing", SNAPSHOT_FILES)
def test_a_missing_compared_file_refuses_naming_it(tmp_path, missing):
    """Review Focus 2: a partial snapshot is never an empty one."""
    files = render_files(_snapshot(results=[_line("t", "a.py", 1, "n", "passed")]))
    del files[missing]
    with pytest.raises(SnapshotUnreadable) as exc:
        load_snapshot(_write(tmp_path / "ev", files))
    assert exc.value.path.name == missing
    assert missing in str(exc.value)


# Verifies: REQ-d00322-C
def test_a_missing_directory_refuses(tmp_path):
    with pytest.raises(SnapshotUnreadable):
        load_snapshot(tmp_path / "absent")


# Verifies: REQ-d00322-C
@pytest.mark.parametrize(
    "bad",
    [
        "not json",
        "[1, 2]",
        "",
        '{"target":"t","file":"a.py","name":"n"}',
        '{"target":"t","file":"a.py","name":"n","outcome":"broken"}',
        '{"target":"t","file":"a.py","name":"n","outcome":"passed","duration":1}',
        '{"target":"t","file":"a.py","name":"n","outcome":"passed","line":"3"}',
        '{"target":"t","file":"a.py","name":"n","outcome":"passed","line":true}',
        '{"target":"t","target":"u","file":"a.py","name":"n","outcome":"passed"}',
        '{"target":7,"file":"a.py","name":"n","outcome":"passed"}',
    ],
    ids=[
        "not-json",
        "not-object",
        "blank",
        "no-outcome",
        "bad-outcome",
        "unknown-key",
        "line-not-int",
        "line-bool",
        "duplicate-key",
        "target-not-str",
    ],
)
def test_a_malformed_result_line_refuses_naming_file_and_line(tmp_path, bad):
    """Review Focus 2: the refusal names the file and the line."""
    good = '{"file":"a.py","name":"n","outcome":"passed","target":"t"}'
    files = render_files(_snapshot())
    files["results.jsonl"] = f"{good}\n{bad}\n{good}\n"
    with pytest.raises(SnapshotUnreadable) as exc:
        load_snapshot(_write(tmp_path / "ev", files))
    assert exc.value.path.name == "results.jsonl"
    assert exc.value.line == 2
    assert "results.jsonl:2" in str(exc.value)


# Verifies: REQ-d00322-M
def test_a_malformed_timing_line_refuses(tmp_path):
    files = render_files(_snapshot())
    files[TIMINGS_FILE] = '{"target":"t","file":"a.py","name":"n","output":""}\n'
    with pytest.raises(SnapshotUnreadable) as exc:
        load_snapshot(_write(tmp_path / "ev", files))
    assert exc.value.path.name == TIMINGS_FILE
    assert exc.value.line == 1


# Verifies: REQ-d00322-D, REQ-d00322-N
@pytest.mark.parametrize(
    "meta",
    [
        "[]",
        '{"elspais":"0","facts":[],"targets":[]}',
        '{"elspais":"0","facts":[],"targets":[],"tree":"x","extra":1}',
        '{"elspais":"0","facts":[],"targets":{"t":"d"},"tree":"x"}',
        '{"elspais":"0","facts":[],"targets":[{"target":"t"}],"tree":"x"}',
        '{"elspais":"0","facts":[{"name":"a","value":1}],"targets":[],"tree":"x"}',
        '{"elspais":"0","facts":[],"targets":[],"tree":5}',
    ],
    ids=[
        "not-object",
        "no-tree",
        "unknown-key",
        "targets-keyed-by-name",
        "target-without-digest",
        "fact-value-not-str",
        "tree-not-str",
    ],
)
def test_a_malformed_snapshot_json_refuses(tmp_path, meta):
    files = render_files(_snapshot())
    files["snapshot.json"] = meta + "\n"
    with pytest.raises(SnapshotUnreadable) as exc:
        load_snapshot(_write(tmp_path / "ev", files))
    assert exc.value.path.name == "snapshot.json"


# Verifies: REQ-d00322-D
def test_parse_facts_sorts_and_keeps_equals_in_values():
    assert parse_facts(["flutter=3.44.7", "backends=vm,postgres", "q=a=b"]) == (
        ("backends", "vm,postgres"),
        ("flutter", "3.44.7"),
        ("q", "a=b"),
    )


# Verifies: REQ-d00322-D
@pytest.mark.parametrize("pairs", [["a=1", "a=2"], ["novalue"], ["=1"]])
def test_parse_facts_refuses(pairs):
    with pytest.raises(ValueError):
        parse_facts(pairs)


# Verifies: REQ-d00322-C, REQ-d00322-M
@pytest.mark.parametrize("separator", ["\u2028", "\u2029", "\u0085"])
def test_a_value_holding_a_unicode_line_separator_round_trips(tmp_path, separator):
    """The writer keeps such a character raw, so only a line feed ends a line."""
    snap = _snapshot(
        results=[
            _line("t", "a_test.py", 3, f"x{separator}y", "skipped", skip_reason=f"r{separator}s"),
            _line("t", "a_test.py", 4, "after", "passed"),
        ],
        timings=[Timing("t", "a_test.py", 3, f"x{separator}y", None, 0.5, f"o{separator}p\n")],
    )
    files = render_files(snap)
    assert separator in files["results.jsonl"]
    assert load_snapshot(_write(tmp_path / "ev", files)) == snap
