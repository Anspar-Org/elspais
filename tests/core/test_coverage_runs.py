"""Tests for the coverage a finished run records and reports.

Each test creates a small project on disk whose targets declare an LCOV
coverage file, starts a run of a target, writes the coverage file into the
target's output area as its tool would, and finishes the run. The finish
records the target's line coverage, renders the target's report, and renders
the report for the repository from every target's record.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from elspais.commands.test_runner import run_configured_targets
from elspais.config import validate_config
from elspais.utilities import coverage as cov
from elspais.utilities.coverage import (
    RECORD_NAME,
    REPORT_NAME,
    CoverageUnreadable,
    FileCoverage,
    current,
    read_record,
    write_record,
)
from elspais.utilities.fingerprint import (
    file_digest,
    finish_run,
    output_root,
    start_run,
    target_folder,
)

_LIB = "def f():\n    return 1\nx = 1\n"
_OTHER = "y = 2\n"

_EARLIER_RUN = {"commit": "aaaa", "root": "/elsewhere", "started_at": "2026-10-01T10:00:00Z"}


def _target(name: str = "t", **extra) -> dict:
    return {
        "name": name,
        "reporter": "junit",
        "results": "junit.xml",
        "coverage": "lcov.info",
        "coverage_format": "lcov",
        **extra,
    }


def _config(*targets: dict) -> dict:
    return {
        "project": {"name": "coverage", "namespace": "REQ"},
        "scanning": {
            "test": {
                "enabled": True,
                "output_root": ".results",
                "targets": list(targets) or [_target()],
            }
        },
    }


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "src" / "lib.py").write_text(_LIB, encoding="utf-8")
    (root / "src" / "other.py").write_text(_OTHER, encoding="utf-8")
    return root


def _lcov(folder: Path, hits: dict[str, dict[int, int]]) -> None:
    body = ""
    for source, lines in hits.items():
        body += f"SF:{source}\n"
        body += "".join(f"DA:{n},{c}\n" for n, c in sorted(lines.items()))
        body += f"LF:{len(lines)}\nLH:{sum(1 for c in lines.values() if c)}\nend_of_record\n"
    (folder / "lcov.info").write_text(body, encoding="utf-8")


def _run(root: Path, config: dict, name: str = "t", hits=None, **finish) -> dict:
    folder = start_run(root, config, name)
    if hits is not None:
        _lcov(folder, hits)
    return finish_run(root, config, name, **finish)


def _report(path: Path) -> dict[str, dict[int, int]]:
    """An LCOV report read as its DA counts per source file."""
    files: dict[str, dict[int, int]] = {}
    source = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("SF:"):
            source = line[3:]
            files[source] = {}
        elif line.startswith("DA:"):
            n, c = line[3:].split(",")[:2]
            files[source][int(n)] = int(c)
    return files


def _carried(root: Path) -> dict[str, FileCoverage]:
    return {
        "src/other.py": FileCoverage(
            hits={1: 4},
            executable=1,
            digest=file_digest(root / "src" / "other.py"),
            measured_in=(_EARLIER_RUN,),
        )
    }


# Verifies: REQ-d00334-A
def test_a_finished_run_records_its_coverage_and_reports_it_in_the_target_area(tmp_path):
    root = _repo(tmp_path)
    config = _config()

    _run(root, config, hits={"src/lib.py": {1: 1, 2: 0, 3: 1}})

    area = target_folder(root, config, "t")
    assert (area / RECORD_NAME).is_file()
    assert (area / REPORT_NAME).is_file()
    assert _report(area / REPORT_NAME) == {"src/lib.py": {1: 1, 2: 0, 3: 1}}
    assert read_record(area)["src/lib.py"].hits == {1: 1, 2: 0, 3: 1}


# Verifies: REQ-d00334-B
def test_a_finished_run_reports_the_coverage_of_the_repository_at_the_output_root(tmp_path):
    root = _repo(tmp_path)
    config = _config()

    _run(root, config, hits={"src/lib.py": {1: 1, 2: 0, 3: 1}})

    combined = output_root(root, config) / REPORT_NAME
    assert combined.is_file()
    assert _report(combined) == {"src/lib.py": {1: 1, 2: 0, 3: 1}}


# Verifies: REQ-d00334-A, REQ-d00333-J
def test_a_run_carrying_coverage_records_it_beside_what_the_run_measured(tmp_path):
    root = _repo(tmp_path)
    config = _config()
    carried = _carried(root)

    _run(root, config, hits={"src/lib.py": {1: 1, 2: 0, 3: 1}}, carried_coverage=carried)

    area = target_folder(root, config, "t")
    record = read_record(area)
    assert set(record) == {"src/lib.py", "src/other.py"}
    assert record["src/other.py"].measured_in == (_EARLIER_RUN,)
    assert set(_report(area / REPORT_NAME)) == {"src/lib.py", "src/other.py"}


# Verifies: REQ-d00334-A, REQ-d00333-J
def test_a_whole_run_records_only_the_coverage_it_measured(tmp_path):
    root = _repo(tmp_path)
    config = _config()
    _run(root, config, hits={"src/other.py": {1: 4}})

    _run(root, config, hits={"src/lib.py": {1: 1, 2: 0, 3: 1}}, carried_coverage=None)

    area = target_folder(root, config, "t")
    assert set(read_record(area)) == {"src/lib.py"}
    assert set(_report(area / REPORT_NAME)) == {"src/lib.py"}


# Verifies: REQ-d00334-A, REQ-d00333-J
def test_a_run_that_measured_nothing_records_exactly_the_coverage_it_carried(tmp_path):
    root = _repo(tmp_path)
    config = _config()
    carried = _carried(root)

    _run(root, config, spawned=False, carried_coverage=carried)

    area = target_folder(root, config, "t")
    assert read_record(area) == current(carried, root)
    assert _report(area / REPORT_NAME) == {"src/other.py": {1: 4}}


# Verifies: REQ-d00334-A, REQ-d00333-J
def test_the_coverage_carried_from_an_area_is_its_record_still_describing_the_tree(tmp_path):
    root = _repo(tmp_path)
    config = _config()
    typed = validate_config(config)
    target = typed.scanning.test.targets[0]
    area = target_folder(root, config, "t")
    area.mkdir(parents=True)

    assert cov.carried_entries(root, typed, target) == {}

    record = {
        rel: FileCoverage(hits={1: 1}, executable=1, digest=file_digest(root / rel))
        for rel in ("src/lib.py", "src/other.py")
    }
    write_record(area, record)
    (root / "src" / "other.py").write_text("y = 3\n", encoding="utf-8")

    assert cov.carried_entries(root, typed, target) == {"src/lib.py": record["src/lib.py"]}


# Verifies: REQ-d00334-B
def test_two_targets_measuring_one_file_are_reported_apart_and_together(tmp_path):
    root = _repo(tmp_path)
    config = _config(_target("one"), _target("two"))

    _run(root, config, "one", hits={"src/lib.py": {1: 3, 2: 0, 3: 1}})
    _run(root, config, "two", hits={"src/lib.py": {1: 1, 2: 2, 3: 0}})

    one = _report(target_folder(root, config, "one") / REPORT_NAME)
    two = _report(target_folder(root, config, "two") / REPORT_NAME)
    combined = _report(output_root(root, config) / REPORT_NAME)
    assert one == {"src/lib.py": {1: 3, 2: 0, 3: 1}}
    assert two == {"src/lib.py": {1: 1, 2: 2, 3: 0}}
    assert combined == {"src/lib.py": {1: 3, 2: 2, 3: 1}}


# Verifies: REQ-d00334-B
def test_two_targets_finishing_together_are_both_in_the_repository_report(tmp_path):
    root = _repo(tmp_path)
    config = _config(_target("one"), _target("two"))
    hits = {"one": {"src/lib.py": {1: 1}}, "two": {"src/other.py": {1: 1}}}
    for name, measured in hits.items():
        _lcov(start_run(root, config, name), measured)
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def finish(name: str) -> None:
        try:
            barrier.wait()
            finish_run(root, config, name)
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=finish, args=(name,)) for name in hits]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    combined = _report(output_root(root, config) / REPORT_NAME)
    assert set(combined) == {"src/lib.py", "src/other.py"}


def _unreadable(*_args, **_kwargs):
    raise CoverageUnreadable("the coverage file cannot be read")


# Verifies: REQ-d00334-A
def test_a_coverage_file_that_cannot_be_read_is_a_fault_of_the_run(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    config = _config()
    monkeypatch.setattr(cov, "read_tool_coverage", _unreadable)

    fingerprint = _run(root, config, hits={"src/lib.py": {1: 1}})

    assert fingerprint["finished_at"]
    faults = fingerprint.get("run_faults") or []
    assert any(f.startswith("coverage:") for f in faults), faults
    assert not (target_folder(root, config, "t") / RECORD_NAME).exists()


# Verifies: REQ-d00334-A
def test_a_run_whose_coverage_cannot_be_read_fails(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    config = _config(_target(command="true"))
    monkeypatch.setattr(cov, "read_tool_coverage", _unreadable)

    (result,) = run_configured_targets(validate_config(config), root)

    assert result.returncode != 0
    assert not result.succeeded


@pytest.fixture(autouse=True)
def _no_probe_cache():
    from elspais.utilities.fingerprint import forget_probes

    forget_probes()
    yield
    forget_probes()
