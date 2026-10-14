"""Tests for the coverage a finished run records and reports.

Each test creates a small project on disk whose targets declare an LCOV
coverage file, starts a run of a target, writes the coverage file into the
target's output area as its tool would, and finishes the run. The finish
records the target's line coverage, renders the target's report, and renders
the report for the repository from every target's record.
"""

from __future__ import annotations

import sys
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
    read_fingerprint,
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


# Verifies: REQ-d00333-J
def test_a_file_edited_while_the_run_ran_is_reported_by_neither_report(tmp_path):
    root = _repo(tmp_path)
    config = _config()
    carried = {
        "src/lib.py": FileCoverage(
            hits={1: 4},
            executable=3,
            digest=file_digest(root / "src" / "lib.py"),
            measured_in=(_EARLIER_RUN,),
        )
    }
    _lcov(start_run(root, config, "t"), {"src/lib.py": {1: 1, 2: 0, 3: 1}})
    (root / "src" / "lib.py").write_text(_LIB + "z = 3\n", encoding="utf-8")

    finish_run(root, config, "t", carried_coverage=carried)

    area = target_folder(root, config, "t")
    record = read_record(area) or {}
    # The measurement describes no single content of the file, so the
    # record holds no entry of this run for it.
    assert "src/lib.py" not in record or record["src/lib.py"].measured_in == (_EARLIER_RUN,)
    assert "src/lib.py" not in _report(area / REPORT_NAME)
    assert "src/lib.py" not in _report(output_root(root, config) / REPORT_NAME)


# Verifies: REQ-d00333-J
def test_the_measurement_leaves_out_an_input_that_changed_since_the_run_started(tmp_path):
    root = _repo(tmp_path)
    config = _config()
    _lcov(start_run(root, config, "t"), {"src/lib.py": {1: 1}, "src/other.py": {1: 1}})
    (root / "src" / "lib.py").write_text(_LIB + "z = 3\n", encoding="utf-8")

    fingerprint = finish_run(root, config, "t")

    assert "src/lib.py" in fingerprint["changed_during_run"]
    assert set(read_record(target_folder(root, config, "t"))) == {"src/other.py"}


# Verifies: REQ-d00334-A
def test_a_finished_fingerprint_is_written_only_after_the_coverage_record(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    config = _config()
    area = target_folder(root, config, "t")
    real_write_record = cov.write_record
    seen: list[str] = []

    def observing_write_record(folder, record, diagnostics=None):
        seen.append(str((read_fingerprint(area) or {}).get("finished_at") or ""))
        return real_write_record(folder, record, diagnostics)

    monkeypatch.setattr(cov, "write_record", observing_write_record)

    _run(root, config, hits={"src/lib.py": {1: 1}})

    assert seen == [""], "the fingerprint showed the run finished before its record existed"
    assert read_fingerprint(area)["finished_at"]


# Verifies: REQ-d00334-A
def test_no_finished_fingerprint_lacks_the_coverage_fault_of_its_run(tmp_path, monkeypatch):
    from elspais.utilities import fingerprint as fp

    root = _repo(tmp_path)
    config = _config()
    monkeypatch.setattr(cov, "read_tool_coverage", _unreadable)
    real_write = fp._write_fingerprint
    written: list[dict] = []

    def observing_write(folder, fingerprint):
        written.append(dict(fingerprint))
        return real_write(folder, fingerprint)

    monkeypatch.setattr(fp, "_write_fingerprint", observing_write)

    final = _run(root, config, hits={"src/lib.py": {1: 1}})

    assert any(str(f).startswith("coverage:") for f in final.get("run_faults") or [])
    finished = [w for w in written if w.get("finished_at")]
    assert finished
    for snapshot in finished:
        faults = snapshot.get("run_faults") or []
        assert any(str(f).startswith("coverage:") for f in faults), snapshot


# Verifies: REQ-d00334-B
def test_the_repository_report_is_written_where_no_file_lock_module_exists(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    config = _config()
    monkeypatch.setitem(sys.modules, "fcntl", None)

    fingerprint = _run(root, config, hits={"src/lib.py": {1: 1}})

    assert fingerprint["finished_at"]
    assert _report(output_root(root, config) / REPORT_NAME) == {"src/lib.py": {1: 1}}


# Verifies: REQ-d00334-B
def test_an_unexpected_failure_measuring_coverage_is_a_fault_of_the_run(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    config = _config()

    def failing_measure(*_args, **_kwargs):
        raise KeyError("x")

    monkeypatch.setattr(cov, "measure", failing_measure)

    fingerprint = _run(root, config, hits={"src/lib.py": {1: 1}})

    faults = fingerprint.get("run_faults") or []
    assert any(str(f).startswith("coverage:") for f in faults), faults


# Verifies: REQ-d00333-J
def test_a_previous_coverage_record_that_cannot_be_read_makes_the_run_whole(tmp_path, monkeypatch):
    from elspais.utilities.fingerprint import forget_probes
    from tests.core.test_retention_runs import _area as _units_area
    from tests.core.test_retention_runs import _coverage_project, _test_file
    from tests.core.test_retention_runs import _run as _units_run

    monkeypatch.setenv("RUNNER_LOG", str(tmp_path / "runner.log"))
    monkeypatch.setenv("TOOL_VERSION", "1")
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    forget_probes()
    root, config = _coverage_project(tmp_path, monkeypatch)
    first, _ = _units_run(root, config)
    assert first.plan.whole
    (_units_area(root, config) / RECORD_NAME).write_text("{not json", encoding="utf-8")
    (root / "tests" / "test_a.py").write_text(_test_file("a", "assert 1"), encoding="utf-8")

    second, _ = _units_run(root, config)

    assert second.plan.whole
    assert "coverage record" in second.plan.whole_reason


_SPEC = """# REQ-d00001: Module

**Level**: DEV | **Status**: Active | **Implements**: -

## Assertions

A. The module SHALL work.

*End* *Module* | **Hash**: 00000000
"""


# Verifies: REQ-d00327-I
def test_coverage_measuring_only_files_outside_the_repository_is_an_ingestion_fault(tmp_path):
    import tomlkit

    from elspais.graph.factory import build_graph
    from elspais.graph.parsers.results.registry import get_reporter

    root = _repo(tmp_path)
    (root / "spec").mkdir()
    (root / "spec" / "dev.md").write_text(_SPEC, encoding="utf-8")
    config = _config()
    config["version"] = 5
    config["scanning"]["spec"] = {"directories": ["spec"]}
    config["scanning"]["code"] = {"directories": ["src"]}
    (root / ".elspais.toml").write_text(tomlkit.dumps(config), encoding="utf-8")
    folder = start_run(root, config, "t")
    (folder / "lcov.info").write_text(
        "SF:../outside.py\nDA:1,1\nend_of_record\nSF:/elsewhere/x.py\nDA:1,1\nend_of_record\n",
        encoding="utf-8",
    )
    finish_run(root, config, "t")

    graph = build_graph(config=config, repo_root=root)

    faults = [f for f in graph.ingestion_faults() if f.stage == "coverage" and f.target == "t"]
    assert len(faults) == 1, faults
    origin = get_reporter("lcov").path_origin
    assert origin in faults[0].cause
    assert "../outside.py" in faults[0].cause or "/elsewhere/x.py" in faults[0].cause


# Verifies: REQ-d00334-B
def test_the_repository_report_does_not_read_back_the_record_just_written(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    config = _config()
    area = target_folder(root, config, "t").resolve()
    real_read_record = cov.read_record
    reads: dict[Path, int] = {}

    def counting_read_record(folder):
        key = Path(folder).resolve()
        reads[key] = reads.get(key, 0) + 1
        return real_read_record(folder)

    folder = start_run(root, config, "t")
    _lcov(folder, {"src/lib.py": {1: 1}})
    monkeypatch.setattr(cov, "read_record", counting_read_record)

    finish_run(root, config, "t")

    assert reads.get(area, 0) == 0, reads
    assert _report(output_root(root, config) / REPORT_NAME) == {"src/lib.py": {1: 1}}
