"""Tests for the coverage record of a test target: reading, measuring, merging and writing it.

A target's coverage tool writes its measurement in one of the formats a
coverage reporter reads. That reading is keyed by repo-relative path, stamped
with the digest of each file it measured and the run that measured it, and
held as the target's coverage record. A record is merged with the coverage
retained from earlier runs, written as JSON, read back, and rendered as an
LCOV report.
"""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import types
from pathlib import Path

import pytest

from elspais.utilities.coverage import (
    RECORD_NAME,
    REPORT_NAME,
    CoverageUnreadable,
    FileCoverage,
    current,
    measure,
    merge,
    read_record,
    read_tool_coverage,
    render_lcov,
    write_record,
    write_report,
)
from elspais.utilities.fingerprint import file_digest, target_folder

_CONFIG: dict = {"scanning": {"test": {"output_root": ".results"}}}

# Three statements; the test runs lines 1 and 3 and never line 2.
_LIB = "def f():\n    return 1\nx = 1\n"

_RUN_1 = {"started_at": "2026-10-01T10:00:00Z", "commit": "aaaa"}
_RUN_2 = {"started_at": "2026-10-02T10:00:00Z", "commit": "bbbb"}
_RUN_3 = {"started_at": "2026-10-03T10:00:00Z", "commit": "cccc"}

_HAS_COVERAGE = importlib.util.find_spec("coverage") is not None


def _target(coverage: str = "lcov.info", coverage_format: str = "lcov", cwd: str = ""):
    return types.SimpleNamespace(
        name="t",
        coverage=coverage,
        coverage_format=coverage_format,
        cwd=cwd,
        coverage_origin="",
        results_origin="",
        reporter="",
    )


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "src" / "lib.py").write_text(_LIB, encoding="utf-8")
    return root


def _area(root: Path) -> Path:
    folder = target_folder(root, _CONFIG, "t")
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _write_lcov(root: Path, *sources: str, name: str = "lcov.info") -> Path:
    body = "".join(f"SF:{s}\nDA:1,1\nDA:2,0\nDA:3,1\nLF:3\nLH:2\nend_of_record\n" for s in sources)
    path = _area(root) / name
    path.write_text(body, encoding="utf-8")
    return path


def _write_coverage_json(root: Path) -> str:
    data = {
        "files": {
            "src/lib.py": {
                "executed_lines": [1, 3],
                "missing_lines": [2],
                "summary": {"num_statements": 3, "covered_lines": 2},
            }
        }
    }
    (_area(root) / "coverage.json").write_text(json.dumps(data), encoding="utf-8")
    return "coverage.json"


def _write_coverage_sqlite(root: Path) -> str:
    from coverage import CoverageData

    data = CoverageData(basename=str(_area(root) / ".coverage"))
    data.set_context("tests/test_lib.py::test_f|run")
    data.add_lines({str((root / "src" / "lib.py").resolve()): [1, 3]})
    data.write()
    return ".coverage"


def _write_lcov_of_lib(root: Path) -> str:
    return _write_lcov(root, "src/lib.py").name


_WRITERS = {
    "lcov": _write_lcov_of_lib,
    "coverage-json": _write_coverage_json,
    "coverage-sqlite": _write_coverage_sqlite,
}


# Verifies: REQ-d00254-F
@pytest.mark.parametrize(
    "fmt",
    [
        "lcov",
        "coverage-json",
        pytest.param(
            "coverage-sqlite",
            marks=pytest.mark.skipif(not _HAS_COVERAGE, reason="coverage is not importable"),
        ),
    ],
)
def test_the_tool_coverage_is_read_in_each_format_and_keyed_by_repo_relative_path(tmp_path, fmt):
    root = _repo(tmp_path)
    name = _WRITERS[fmt](root)

    reading = read_tool_coverage(root, _CONFIG, _target(coverage=name, coverage_format=fmt))

    assert set(reading) == {"src/lib.py"}
    assert reading["src/lib.py"]["line_coverage"] == {1: 1, 2: 0, 3: 1}
    assert reading["src/lib.py"]["executable_lines"] == 3


# Verifies: REQ-d00254-F
def test_an_absent_coverage_file_reads_as_no_coverage(tmp_path):
    root = _repo(tmp_path)

    assert read_tool_coverage(root, _CONFIG, _target()) == {}


# Verifies: REQ-d00254-F
def test_a_relative_path_is_read_from_the_working_directory_of_the_target(tmp_path):
    root = _repo(tmp_path)
    _write_lcov(root, "lib.py")

    reading = read_tool_coverage(root, _CONFIG, _target(cwd="src"))

    assert set(reading) == {"src/lib.py"}


# Verifies: REQ-d00254-F
def test_a_path_outside_the_repository_is_dropped(tmp_path):
    root = _repo(tmp_path)
    outside = tmp_path / "x.py"
    outside.write_text(_LIB, encoding="utf-8")
    _write_lcov(root, str(outside.resolve()), "../x.py", "src/lib.py")

    reading = read_tool_coverage(root, _CONFIG, _target())

    assert set(reading) == {"src/lib.py"}


# Verifies: REQ-d00254-F
@pytest.mark.parametrize(
    ("through", "expected"), [("directory", "link/lib.py"), ("root", "src/lib.py")]
)
def test_a_file_reached_through_a_symlink_is_keyed_by_its_repo_relative_path(
    tmp_path, through, expected
):
    real_root = _repo(tmp_path)
    if through == "directory":
        # A symlinked directory inside the repository leads to the file; the
        # path as written is already inside the repository.
        (real_root / "link").symlink_to(real_root / "src", target_is_directory=True)
        root, source = real_root, "link/lib.py"
    else:
        # The repository is reached through a symlink, and the tool recorded
        # the resolved absolute path.
        root = tmp_path / "alias"
        root.symlink_to(real_root, target_is_directory=True)
        source = str((real_root / "src" / "lib.py").resolve())
    _write_lcov(root, source)

    reading = read_tool_coverage(root, _CONFIG, _target())

    assert set(reading) == {expected}


# Verifies: REQ-d00333-J
def test_a_measurement_records_the_digest_of_each_file_and_the_run_that_measured_it(tmp_path):
    root = _repo(tmp_path)
    _write_lcov(root, "src/lib.py", "src/gone.py")

    record = measure(root, _CONFIG, _target(), _RUN_1)

    assert set(record) == {"src/lib.py", "src/gone.py"}
    entry = record["src/lib.py"]
    assert entry.hits == {1: 1, 2: 0, 3: 1}
    assert entry.executable == 3
    assert entry.digest == file_digest(root / "src" / "lib.py")
    assert entry.measured_in == (_RUN_1,)
    # A measured file that is not there is kept, with no content to describe.
    assert record["src/gone.py"].digest == ""
    assert set(current(record, root)) == {"src/lib.py"}


# Verifies: REQ-d00333-J
@pytest.mark.parametrize("change", ["edited", "deleted"])
def test_current_coverage_holds_only_files_unchanged_since_they_were_measured(tmp_path, change):
    root = _repo(tmp_path)
    (root / "src" / "other.py").write_text("y = 2\n", encoding="utf-8")
    record = {
        path: FileCoverage(
            hits={1: 1}, executable=1, digest=file_digest(root / path), measured_in=(_RUN_1,)
        )
        for path in ("src/lib.py", "src/other.py")
    }
    if change == "edited":
        (root / "src" / "other.py").write_text("y = 3\n", encoding="utf-8")
    else:
        (root / "src" / "other.py").unlink()

    assert current(record, root) == {"src/lib.py": record["src/lib.py"]}


# Verifies: REQ-d00334-A, REQ-d00333-J
@pytest.mark.parametrize(
    "b_digest",
    ["d-a", "d-b", ""],
    ids=["same-content", "other-content", "no-content"],
)
def test_merging_two_records_keeps_the_most_each_one_measured_of_one_content(b_digest):
    a = {
        "both.py": FileCoverage(
            hits={1: 1, 2: 0},
            executable=2,
            contexts={1: ("tests/test_a.py::test_a|run",)},
            digest="d-a",
            measured_in=(_RUN_1, _RUN_2),
        ),
        "only_a.py": FileCoverage(hits={1: 0}, executable=1, digest="d-oa"),
    }
    b = {
        "both.py": FileCoverage(
            hits={2: 3, 3: 0},
            executable=3,
            contexts={
                1: ("tests/test_b.py::test_b|run", "tests/test_a.py::test_a|run"),
                2: ("tests/test_b.py::test_b|run",),
            },
            digest=b_digest,
            measured_in=(_RUN_2, _RUN_3),
        ),
        "only_b.py": FileCoverage(hits={4: 1}, executable=1, digest="d-ob"),
    }

    merged = merge(a, b)

    assert set(merged) == {"both.py", "only_a.py", "only_b.py"}
    assert merged["only_a.py"] == a["only_a.py"]
    assert merged["only_b.py"] == b["only_b.py"]
    both = merged["both.py"]
    if b_digest != a["both.py"].digest:
        # Entries of two contents of one file describe no single content, so
        # the newer one stands alone; an entry with no content is another.
        assert both == b["both.py"]
        return
    assert both.hits == {1: 1, 2: 3, 3: 0}
    assert both.executable == 3
    assert {line: set(names) for line, names in both.contexts.items()} == {
        1: {"tests/test_a.py::test_a|run", "tests/test_b.py::test_b|run"},
        2: {"tests/test_b.py::test_b|run"},
    }
    assert all(len(names) == len(set(names)) for names in both.contexts.values())
    assert both.digest == "d-a"
    assert both.measured_in == (_RUN_1, _RUN_2, _RUN_3)


def _two_file_record() -> dict:
    return {
        "src/lib.py": FileCoverage(
            hits={1: 2, 2: 0, 3: 1},
            executable=3,
            contexts={
                1: ("tests/test_a.py::test_a|run", "tests/test_b.py::test_b|run"),
                3: ("tests/test_b.py::test_b|run",),
            },
            digest="abc",
            measured_in=(_RUN_1, _RUN_2),
        ),
        "src/other.py": FileCoverage(
            hits={5: 1},
            executable=0,
            contexts={5: ("tests/test_a.py::test_a|run",)},
            digest="def",
            measured_in=(_RUN_2,),
            source_analysed=False,
        ),
    }


# Verifies: REQ-d00334-A
def test_a_written_record_reads_back_equal_and_names_each_context_once(tmp_path):
    record = _two_file_record()

    path = write_record(tmp_path, record)

    assert path == tmp_path / RECORD_NAME
    assert read_record(tmp_path) == record
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["version"] == 1
    table = data["contexts"]
    assert sorted(table) == ["tests/test_a.py::test_a|run", "tests/test_b.py::test_b|run"]
    stored = data["files"]["src/lib.py"]
    assert stored["hits"] == {"1": 2, "2": 0, "3": 1}
    assert all(isinstance(i, int) for ids in stored["contexts"].values() for i in ids)
    assert {line: [table[i] for i in ids] for line, ids in stored["contexts"].items()} == {
        "1": ["tests/test_a.py::test_a|run", "tests/test_b.py::test_b|run"],
        "3": ["tests/test_b.py::test_b|run"],
    }
    assert data["files"]["src/other.py"]["source_analysed"] is False


# Verifies: REQ-d00334-A
@pytest.mark.parametrize("writer", ["record", "report"])
def test_a_record_and_a_report_replace_the_previous_file_atomically(tmp_path, monkeypatch, writer):
    record = _two_file_record()
    destination = tmp_path / (RECORD_NAME if writer == "record" else REPORT_NAME)
    destination.write_text("previous", encoding="utf-8")
    real_replace = os.replace
    calls: list[tuple[Path, Path]] = []

    def recording_replace(src, dst, *args, **kwargs):
        calls.append((Path(src), Path(dst)))
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "replace", recording_replace)

    if writer == "record":
        written = write_record(tmp_path, record)
    else:
        written = write_report(destination, record)

    assert written == destination
    assert len(calls) == 1
    src, dst = calls[0]
    assert src.parent == tmp_path
    assert src.name != destination.name
    assert dst == destination
    assert sorted(p.name for p in tmp_path.iterdir()) == [destination.name]
    if writer == "report":
        assert destination.read_text(encoding="utf-8") == render_lcov(record)


# Verifies: REQ-d00334-A
def test_an_absent_record_reads_as_none(tmp_path):
    assert read_record(tmp_path) is None


# Verifies: REQ-d00334-A
@pytest.mark.parametrize(
    "content",
    ["{not json", json.dumps({"version": 2, "contexts": [], "files": {}})],
    ids=["bad-json", "other-version"],
)
def test_an_unreadable_record_is_refused_naming_the_remedy(tmp_path, content):
    (tmp_path / RECORD_NAME).write_text(content, encoding="utf-8")

    with pytest.raises(CoverageUnreadable, match="run the target again"):
        read_record(tmp_path)


# Verifies: REQ-d00334-A
@pytest.mark.parametrize(
    ("record", "expected"),
    [
        (
            {
                "src/b.py": FileCoverage(hits={3: 0, 1: 2}, executable=2),
                "src/a.py": FileCoverage(hits={2: 1}, executable=1),
            },
            "SF:src/a.py\nDA:2,1\nLF:1\nLH:1\nend_of_record\n"
            "SF:src/b.py\nDA:1,2\nDA:3,0\nLF:2\nLH:1\nend_of_record\n",
        ),
        ({}, ""),
    ],
    ids=["two-files", "empty"],
)
def test_a_record_renders_as_lcov_sorted_by_path_and_line(record, expected):
    assert render_lcov(record) == expected


# Verifies: REQ-d00334-A
@pytest.mark.parametrize("writer", ["record", "report"])
def test_a_record_and_a_report_carry_an_ordinary_files_permissions(tmp_path, writer):
    record = _two_file_record()
    probe = tmp_path / "probe"
    with open(probe, "w", encoding="utf-8") as fh:
        fh.write("probe")
    expected = stat.S_IMODE(os.stat(probe).st_mode)

    if writer == "record":
        written = write_record(tmp_path, record)
    else:
        written = write_report(tmp_path / REPORT_NAME, record)

    assert oct(stat.S_IMODE(os.stat(written).st_mode)) == oct(expected)


# Verifies: REQ-d00333-J
def test_merging_entries_of_two_contents_of_one_file_keeps_the_newer_alone():
    a = {"lib.py": FileCoverage(hits={1: 5}, executable=1, digest="d1", measured_in=(_RUN_1,))}
    b = {"lib.py": FileCoverage(hits={2: 1}, executable=1, digest="d2", measured_in=(_RUN_2,))}

    merged = merge(a, b)["lib.py"]

    assert merged.hits == {2: 1}
    assert merged.digest == "d2"


def _absolute_lcov(root: Path) -> str:
    return _write_lcov(
        root, str((root / "src" / "lib.py").resolve()), str((root / "src" / "gone.py").resolve())
    ).name


def _absolute_sqlite(root: Path) -> str:
    from coverage import CoverageData

    data = CoverageData(basename=str(_area(root) / ".coverage"))
    data.add_lines(
        {
            str((root / "src" / "lib.py").resolve()): [1, 3],
            str((root / "src" / "gone.py").resolve()): [1],
        }
    )
    data.write()
    return ".coverage"


# Verifies: REQ-d00334-A
@pytest.mark.parametrize(
    "fmt",
    [
        "lcov",
        pytest.param(
            "coverage-sqlite",
            marks=pytest.mark.skipif(not _HAS_COVERAGE, reason="coverage is not importable"),
        ),
    ],
)
def test_a_written_record_holds_no_absolute_path_of_a_file_found_in_the_repository(tmp_path, fmt):
    root = _repo(tmp_path)
    name = (_absolute_lcov if fmt == "lcov" else _absolute_sqlite)(root)
    record = measure(root, _CONFIG, _target(coverage=name, coverage_format=fmt), _RUN_1)

    files = json.loads(write_record(tmp_path, record).read_text(encoding="utf-8"))["files"]

    found = files["src/lib.py"]
    assert not os.path.isabs(found.get("recorded", "")), found
    # A file the measurement names and the tree lacks keeps the path as recorded.
    assert files["src/gone.py"]["digest"] == ""
    assert "recorded" in files["src/gone.py"]


# Verifies: REQ-d00334-A
def test_a_report_written_under_a_restrictive_umask_carries_that_umask(tmp_path):
    previous = os.umask(0o077)
    try:
        written = write_report(tmp_path / REPORT_NAME, _two_file_record())
    finally:
        os.umask(previous)

    assert oct(stat.S_IMODE(os.stat(written).st_mode)) == oct(0o600)


# Verifies: REQ-d00334-A
def test_a_write_that_fails_leaves_no_temporary_file_and_raises(tmp_path, monkeypatch):
    destination = tmp_path / REPORT_NAME
    destination.write_text("previous", encoding="utf-8")

    def failing_replace(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", failing_replace)

    with pytest.raises(OSError, match="disk full"):
        write_report(destination, _two_file_record())

    assert sorted(p.name for p in tmp_path.iterdir()) == [destination.name]
    assert destination.read_text(encoding="utf-8") == "previous"
