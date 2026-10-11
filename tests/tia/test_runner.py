"""Matching pytest node ids to JUnit records, and the TIA-vs-full comparison."""

from __future__ import annotations

import pytest

from tools.tia.calibrate import compare_runs
from tools.tia.runner import junit_summary, nodeid_to_junit_key

# (nodeid, xunit1 classname, name, child element or "")
CASES = [
    ("tests/test_core.py::test_add", "tests.test_core", "test_add", ""),
    (
        "tests/test_core.py::test_mul",
        "tests.test_core",
        "test_mul",
        '<failure message="assert 6 == 5">boom</failure>',
    ),
    ("tests/test_core.py::TestBox::test_get", "tests.test_core.TestBox", "test_get", ""),
    (
        "tests/sub/test_deep.py::TestOuter::TestInner::test_p[a-b]",
        "tests.sub.test_deep.TestOuter.TestInner",
        "test_p[a-b]",
        '<skipped message="later"/>',
    ),
    (
        "tests/test_err.py::test_broken",
        "tests.test_err",
        "test_broken",
        '<error message="fixture">err</error>',
    ),
]


def write_junit(path, cases) -> str:
    rows = []
    for nodeid, classname, name, child in cases:
        file = nodeid.split("::", 1)[0]
        rows.append(
            f'<testcase classname="{classname}" name="{name}" file="{file}" '
            f'line="1" time="0.5">{child}</testcase>'
        )
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<testsuites><testsuite name="pytest" '
        f'tests="{len(rows)}">' + "".join(rows) + "</testsuite></testsuites>\n",
        encoding="utf-8",
    )
    return str(path)


@pytest.fixture
def full_junit(tmp_path):
    return write_junit(tmp_path / "full.xml", CASES)


def test_nodeid_key_matches_junit_summary_key(full_junit):
    summary = junit_summary(full_junit)
    assert summary["present"]
    assert set(summary["cases"]) == {nodeid_to_junit_key(n) for n, *_ in CASES}


@pytest.mark.parametrize(
    "nodeid, outcome",
    [
        ("tests/test_core.py::test_add", "passed"),
        ("tests/test_core.py::test_mul", "failed"),
        ("tests/sub/test_deep.py::TestOuter::TestInner::test_p[a-b]", "skipped"),
        ("tests/test_err.py::test_broken", "error"),
    ],
)
def test_junit_outcomes(full_junit, nodeid, outcome):
    assert junit_summary(full_junit)["cases"][nodeid_to_junit_key(nodeid)]["outcome"] == outcome


def test_missing_junit_is_reported_absent(tmp_path):
    assert junit_summary(str(tmp_path / "none.xml")) == {"present": False}


def _manifest(mode, selected):
    return {"selection_mode": mode, "tests": [{"test": n, "reasons": []} for n in selected]}


def test_unselected_full_run_failure_is_missed(full_junit):
    report = compare_runs(
        _manifest(
            "test-impact", ["tests/test_core.py::test_add", "tests/test_err.py::test_broken"]
        ),
        full_junit,
    )
    assert report["missed_failures"] == [nodeid_to_junit_key("tests/test_core.py::test_mul")]
    assert report["verdict"] == "MISSED FAILURES"
    assert report["full_failures"] == sorted(
        nodeid_to_junit_key(n)
        for n in ("tests/test_core.py::test_mul", "tests/test_err.py::test_broken")
    )


def test_selected_failures_are_not_missed(full_junit):
    report = compare_runs(
        _manifest(
            "test-impact", ["tests/test_core.py::test_mul", "tests/test_err.py::test_broken"]
        ),
        full_junit,
    )
    assert report["missed_failures"] == []
    assert report["verdict"] == "no missed failures"


def test_full_selection_misses_nothing(full_junit):
    report = compare_runs(_manifest("full", []), full_junit)
    assert report["missed_failures"] == []
    assert report["selected_tests"] == len(CASES)


def test_tia_run_outcomes_are_compared(full_junit, tmp_path):
    # the TIA run saw test_add fail where the full run passed it
    tia_cases = [list(c) for c in CASES[:1]]
    tia_cases[0][3] = '<failure message="x">x</failure>'
    tia_junit = write_junit(tmp_path / "tia.xml", tia_cases)
    m = _manifest("test-impact", ["tests/test_core.py::test_add"])
    m["run"] = {"junit": tia_junit}
    report = compare_runs(m, full_junit)
    assert report["outcome_disagreements"] == [nodeid_to_junit_key(CASES[0][0])]
    assert report["tia_failures"] == [nodeid_to_junit_key(CASES[0][0])]
