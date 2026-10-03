"""Scheduling test targets: concurrent runs, shared resources, and stale-only runs.

Every stub command here is a real subprocess running ``_STUB``. A stub records
its evidence -- monotonic start and end stamps, rendezvous markers, its lines of
output -- inside its own output area (``$ELSPAIS_TARGET_OUTPUT``), which is
outside every target's inputs, or in a file outside the repository. Each
assertion reads that evidence; no assertion reads a wall clock.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from elspais.commands import health, test_runner
from elspais.commands.test_runner import not_fresh_targets, run_configured_targets
from elspais.config.schema import (
    ElspaisConfig,
    ScanningConfig,
    TestScanningConfig,
    TestTargetConfig,
)
from elspais.utilities.fingerprint import judge, read_record, start_run, target_folder

# Modes (argv[1]):
#   hold SECONDS [LOCK]  stay running for SECONDS; with LOCK, hold an exclusive
#                        lock file for that time and record a violation if it
#                        is already held
#   meet PARTNER         record arrival, then wait (bounded) for PARTNER's
#                        arrival; exit 0 only if PARTNER arrived
#   say TOKEN N CODE [PARTNER]
#                        optionally meet PARTNER, then write N lines to stdout
#                        and N to stderr, interleaved with short pauses
#   fail CODE            exit with CODE at once
#   junit pass|fail      write a junit artifact with a per-run token
# Every mode stamps `start` and `end` in its output area, and appends the
# target's name to $STUB_LOG when that is set.
_STUB = r"""
import os, pathlib, sys, time, uuid

mode, rest = sys.argv[1], sys.argv[2:]
out = pathlib.Path(os.environ["ELSPAIS_TARGET_OUTPUT"])
name = out.name


def stamp(label):
    (out / label).write_text(str(time.monotonic_ns()))


def meet(partner):
    (out / "here").write_text("1")
    theirs = out.parent / partner / "here"
    deadline = time.monotonic() + 10
    while not theirs.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    return theirs.exists()


stamp("start")
log = os.environ.get("STUB_LOG")
if log:
    with open(log, "a") as fh:
        fh.write(name + "\n")
code = 0
if mode == "hold":
    lock = rest[1] if len(rest) > 1 else None
    held = False
    if lock:
        try:
            os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            held = True
        except FileExistsError:
            (out / "violation").write_text("lock already held")
    time.sleep(float(rest[0]))
    if held:
        os.unlink(lock)
elif mode == "meet":
    code = 0 if meet(rest[0]) else 1
elif mode == "say":
    token, count, code = rest[0], int(rest[1]), int(rest[2])
    if len(rest) > 3 and not meet(rest[3]):
        code = 99
    for i in range(count):
        print(f"{token}-OUT-{i}", flush=True)
        print(f"{token}-ERR-{i}", file=sys.stderr, flush=True)
        time.sleep(0.03)
elif mode == "fail":
    code = int(rest[0])
elif mode == "junit":
    failure = '<failure message="boom"/>' if rest[0] == "fail" else ""
    (out / "junit.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f'<testsuites><testsuite name="t" tests="1" failures="{1 if failure else 0}" '
        f'id="{uuid.uuid4()}"><testcase classname="tests.test_thing" name="test_thing" '
        f'time="0.01">{failure}</testcase></testsuite></testsuites>\n'
    )
stamp("end")
sys.exit(code)
"""


@pytest.fixture
def stub(tmp_path: Path):
    """Return a function spelling a stub command; the stub lives outside the repository."""
    path = tmp_path / "stub.py"
    path.write_text(_STUB)

    def command(*argv: str) -> str:
        return " ".join([f'"{sys.executable}"', f'"{path}"', *argv])

    return command


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    return root


def _cfg(targets: list[TestTargetConfig], **test_settings) -> ElspaisConfig:
    return ElspaisConfig(
        scanning=ScanningConfig(test=TestScanningConfig(targets=targets, **test_settings))
    )


def _target(name: str, command: str, reporter: str = "junit", **kw) -> TestTargetConfig:
    return TestTargetConfig(name=name, command=command, reporter=reporter, **kw)


def _interval(repo: Path, cfg: ElspaisConfig, name: str) -> tuple[int, int]:
    folder = target_folder(repo, cfg, name)
    return int((folder / "start").read_text()), int((folder / "end").read_text())


def _most_at_once(intervals: list[tuple[int, int]]) -> int:
    return max(sum(1 for s, e in intervals if s <= start < e) for start, _ in intervals)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


# Verifies: REQ-d00314-A
@pytest.mark.parametrize("value", [0, -1])
def test_a_maximum_below_one_is_refused(value):
    with pytest.raises(ValidationError, match=rf"concurrency {value} must be .* 1 or more"):
        TestScanningConfig(concurrency=value)


# Verifies: REQ-d00314-A+B
def test_a_project_sets_the_maximum_and_one_is_used_where_it_sets_none():
    from elspais.config import validate_config

    unset = validate_config({"version": 5, "scanning": {"test": {"enabled": True}}})
    set_to_three = validate_config(
        {"version": 5, "scanning": {"test": {"enabled": True, "concurrency": 3}}}
    )

    assert unset.scanning.test.concurrency == 1
    assert set_to_three.scanning.test.concurrency == 3


# Verifies: REQ-d00314-G
def test_a_target_naming_an_undeclared_resource_is_refused_naming_both():
    with pytest.raises(ValidationError) as caught:
        TestScanningConfig(
            resources={"db": "the local postgres"},
            targets=[_target("unit", "true", resources=["emulator"])],
        )
    message = str(caught.value)
    assert '"unit"' in message
    assert '"emulator"' in message
    assert "Declared resources: db" in message


# Verifies: REQ-d00314-E
@pytest.mark.parametrize("description", ["", "   "])
def test_a_resource_declared_without_a_description_is_refused(description):
    with pytest.raises(ValidationError, match='shared resource "db" must have a description'):
        TestScanningConfig(resources={"db": description})


# Verifies: REQ-d00314-E
def test_two_resources_differing_only_in_case_are_refused():
    with pytest.raises(ValidationError, match="differ only in case or spacing"):
        TestScanningConfig(resources={"db": "one database", "DB": "another"})


# Verifies: REQ-d00314-E+F
def test_a_target_names_a_declared_resource_in_any_case():
    test = TestScanningConfig(
        resources={"db": "the local postgres"},
        targets=[_target("unit", "true", resources=["DB"])],
    )
    assert test.targets[0].resources == ["DB"]


# ---------------------------------------------------------------------------
# Which targets overlap
# ---------------------------------------------------------------------------


# Verifies: REQ-d00314-H
@pytest.mark.parametrize("resources_honoured", [True, False], ids=["scheduler", "ignored"])
def test_targets_naming_a_common_resource_never_overlap(
    repo, stub, tmp_path, monkeypatch, resources_honoured
):
    """The `ignored` case removes the resource rule from the scheduler and shows
    the same evidence then records an overlap, so the evidence can see one."""
    if not resources_honoured:
        monkeypatch.setattr(test_runner, "_resource_keys", lambda target: frozenset())
    lock = tmp_path / "db.lock"
    cfg = _cfg(
        [
            _target("a", stub("hold", "0.4", str(lock)), resources=["db"]),
            _target("b", stub("hold", "0.4", str(lock)), resources=["DB"]),
        ],
        concurrency=2,
        resources={"db": "the local postgres"},
    )

    results, _ = run_configured_targets(cfg, repo)

    assert [r.returncode for r in results] == [0, 0]
    (a_start, a_end), (b_start, b_end) = _interval(repo, cfg, "a"), _interval(repo, cfg, "b")
    disjoint = a_end <= b_start or b_end <= a_start
    violated = any((target_folder(repo, cfg, n) / "violation").exists() for n in ("a", "b"))
    if resources_honoured:
        assert disjoint, "two targets naming one resource ran at the same time"
        assert not violated
    else:
        assert not disjoint and violated, "the evidence did not record the overlap"


# Verifies: REQ-d00314-I
def test_unrelated_targets_run_at_the_same_time(repo, stub):
    """Each stub passes only if it meets the other while both run."""
    cfg = _cfg(
        [_target("a", stub("meet", "b")), _target("b", stub("meet", "a"))],
        concurrency=2,
    )

    results, _ = run_configured_targets(cfg, repo)

    assert [(r.name, r.returncode) for r in results] == [("a", 0), ("b", 0)]


# Verifies: REQ-d00314-H+I
def test_a_target_waiting_for_a_resource_does_not_hold_back_the_next(repo, stub, tmp_path):
    """b waits for the resource a holds; c, declared after b, meets a while a runs."""
    cfg = _cfg(
        [
            _target("a", stub("meet", "c"), resources=["db"]),
            _target("b", stub("hold", "0", str(tmp_path / "db.lock")), resources=["db"]),
            _target("c", stub("meet", "a")),
        ],
        concurrency=2,
        resources={"db": "the local postgres"},
    )

    results, _ = run_configured_targets(cfg, repo)

    assert [(r.name, r.returncode) for r in results] == [("a", 0), ("b", 0), ("c", 0)]
    assert _interval(repo, cfg, "a")[1] <= _interval(repo, cfg, "b")[0]


# Verifies: REQ-d00314-A
def test_no_more_targets_run_at_once_than_the_maximum(repo, stub):
    cfg = _cfg(
        [_target(n, stub("hold", "0.4")) for n in ("a", "b", "c")],
        concurrency=2,
    )

    results, _ = run_configured_targets(cfg, repo)

    assert [r.returncode for r in results] == [0, 0, 0]
    intervals = [_interval(repo, cfg, n) for n in ("a", "b", "c")]
    assert _most_at_once(intervals) == 2


# ---------------------------------------------------------------------------
# Reading a concurrent run
# ---------------------------------------------------------------------------


_TALLY = r"\(\d+\.\ds\)"


# Verifies: REQ-d00314-J+K+L
def test_a_concurrent_run_attributes_every_line_and_keeps_captures_apart(repo, stub, capsys):
    cfg = _cfg(
        [
            _target("alpha", stub("say", "ALPHA", "5", "0", "beta"), reporter="flutter-machine"),
            _target("beta", stub("say", "BETA", "5", "3", "alpha"), reporter="flutter-machine"),
            _target("gamma", stub("say", "GAMMA", "3", "0")),
        ],
        concurrency=3,
    )

    results, captured = run_configured_targets(cfg, repo)
    out, err = capsys.readouterr()

    assert [(r.name, r.returncode) for r in results] == [("alpha", 0), ("beta", 3), ("gamma", 0)]
    # A stdout-channel target's stdout is echoed to stderr; a file-channel
    # target's stdout to stdout; every stderr line to stderr.
    expected = {
        "alpha": (5, err, err),
        "beta": (5, err, err),
        "gamma": (3, out, err),
    }
    for name, (count, stdout_stream, stderr_stream) in expected.items():
        token = name.upper()
        for i in range(count):
            assert stdout_stream.splitlines().count(f"[{name}] {token}-OUT-{i}") == 1
            assert stderr_stream.splitlines().count(f"[{name}] {token}-ERR-{i}") == 1
        for line in (out + err).splitlines():
            if f"{token}-" in line:
                assert line.startswith(f"[{name}] "), f"unattributed line: {line!r}"

    # The two stdout-channel targets really did write at the same time.
    lines = err.splitlines()
    alpha_at = [i for i, line in enumerate(lines) if "ALPHA-OUT" in line]
    beta_at = [i for i, line in enumerate(lines) if "BETA-OUT" in line]
    assert beta_at[0] < alpha_at[-1] and alpha_at[0] < beta_at[-1]

    # Each capture holds its own target's stdout alone, unprefixed.
    assert captured["alpha"] == "".join(f"ALPHA-OUT-{i}\n" for i in range(5))
    assert captured["beta"] == "".join(f"BETA-OUT-{i}\n" for i in range(5))
    assert "gamma" not in captured

    assert re.search(rf"^<<< alpha: passed {_TALLY}$", err, re.M)
    assert re.search(rf"^<<< beta: FAILED \(exit 3\) {_TALLY}$", err, re.M)
    assert re.search(rf"^<<< gamma: passed {_TALLY}$", err, re.M)


# Verifies: REQ-d00314-B+C+D
def test_without_a_maximum_targets_run_one_at_a_time_in_order_unmarked(
    repo, stub, tmp_path, monkeypatch, capfd
):
    order = tmp_path / "order.log"
    monkeypatch.setenv("STUB_LOG", str(order))
    names = ("zeta", "alpha", "mid")
    cfg = _cfg([_target(n, stub("say", n.upper(), "2", "0")) for n in names])

    results, _ = run_configured_targets(cfg, repo)
    out, err = capfd.readouterr()

    assert [r.name for r in results] == list(names)
    assert order.read_text().splitlines() == list(names)
    intervals = [_interval(repo, cfg, n) for n in names]
    assert all(intervals[i][1] <= intervals[i + 1][0] for i in range(len(names) - 1))
    for name in names:
        token = name.upper()
        assert out.splitlines().count(f"{token}-OUT-0") == 1
        assert err.splitlines().count(f"{token}-ERR-0") == 1
    assert "] " not in "".join(line for line in (out + err).splitlines() if "-OUT-" in line)


# Verifies: REQ-d00314-M+N
def test_fail_fast_starts_nothing_more_and_lets_running_targets_finish(repo, stub):
    cfg = _cfg(
        [
            _target("a", stub("fail", "1")),
            _target("b", stub("hold", "0.5")),
            _target("c", stub("hold", "0")),
        ],
        concurrency=2,
    )

    results, _ = run_configured_targets(cfg, repo, fail_fast=True)

    assert [(r.name, r.returncode) for r in results] == [("a", 1), ("b", 0)]
    assert not target_folder(repo, cfg, "c").exists(), "a target started after the failure"
    # b was running when a failed, and finished afterwards with its end recorded.
    assert _interval(repo, cfg, "b")[1] > _interval(repo, cfg, "a")[1]
    assert read_record(target_folder(repo, cfg, "b"))["finished_at"]


# ---------------------------------------------------------------------------
# Stale-only runs
# ---------------------------------------------------------------------------

_SPEC = """\
# Requirements

---

### REQ-d00001: Thing

**Level**: dev | **Status**: Active

## Assertions

A. The system SHALL do the thing.

*End* *Thing*
---
"""


def _toml_target(name: str, command: str, inputs: str | None = None) -> str:
    lines = [
        "[[scanning.test.targets]]",
        f'name = "{name}"',
        'reporter = "junit"',
        'results = "junit.xml"',
        f"command = '''{command}'''",
    ]
    if inputs is not None:
        lines.append(f'inputs = {{ directories = ["{inputs}"] }}')
    return "\n".join(lines) + "\n"


def _project(tmp_path: Path, monkeypatch, *targets: str, extra: str = "") -> Path:
    """A git repository declaring *targets*, made the working directory."""
    root = tmp_path / "project"
    (root / "spec").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / "spec" / "requirements.md").write_text(_SPEC, encoding="utf-8")
    (root / ".elspais.toml").write_text(
        'version = 5\n\n[project]\nname = "runs"\nnamespace = "REQ"\n\n'
        '[scanning.spec]\ndirectories = ["spec"]\n\n'
        "[changelog]\nhash_current = false\n\n"
        f"{extra}\n"
        "[scanning.test]\nenabled = true\n\n" + "\n".join(targets),
        encoding="utf-8",
    )
    monkeypatch.chdir(root)
    return root


def _config(root: Path):
    from elspais.config import load_config, validate_config

    return validate_config(load_config(root / ".elspais.toml"))


def _token(root: Path, name: str) -> str:
    return (root / ".results" / name / "junit.xml").read_text()


def _four_states(tmp_path, monkeypatch, stub) -> Path:
    """One target in each freshness state: fresh, stale, absent and running."""
    from elspais.cli import main

    names = ("fresh", "stale", "absent", "running")
    root = _project(
        tmp_path,
        monkeypatch,
        *(_toml_target(n, stub("junit", "pass"), inputs=n) for n in names),
    )
    for name in names:
        (root / name).mkdir()
        (root / name / "input.txt").write_text("one\n")
    assert main(["test", "--targets", "fresh", "stale", "running"]) == 0
    (root / "stale" / "input.txt").write_text("two\n")
    start_run(root, _config(root), "running")
    return root


# Verifies: REQ-d00315-C+D+E
def test_only_fresh_results_are_carried(tmp_path, monkeypatch, stub):
    root = _four_states(tmp_path, monkeypatch, stub)
    config = _config(root)

    states = {n: judge(root, config, n).state for n in ("fresh", "stale", "absent", "running")}
    execute, carry = not_fresh_targets(config, root, None)

    assert states == {"fresh": "fresh", "stale": "stale", "absent": "absent", "running": "running"}
    assert execute == {n for n, state in states.items() if state != "fresh"}
    assert carry == {"fresh"}


# Verifies: REQ-d00315-A+B+F+H
def test_a_stale_only_run_executes_exactly_the_targets_not_fresh(
    tmp_path, monkeypatch, stub, capsys
):
    from elspais.cli import main

    root = _four_states(tmp_path, monkeypatch, stub)
    carried_token = _token(root, "fresh")
    log = tmp_path / "runs.log"
    monkeypatch.setenv("STUB_LOG", str(log))
    capsys.readouterr()

    assert main(["test", "--stale-only"]) == 0

    out, err = capsys.readouterr()
    assert sorted(log.read_text().splitlines()) == ["absent", "running", "stale"]
    assert _token(root, "fresh") == carried_token, "the fresh target's results were replaced"
    assert judge(root, _config(root), "fresh").state == "fresh"
    assert "stale-only: executing absent, running, stale; carrying fresh results of fresh" in err
    assert "3 target(s) passed" in out


# Verifies: REQ-d00315-G+H
def test_a_stale_only_run_with_everything_fresh_executes_nothing_and_passes(
    tmp_path, monkeypatch, stub, capsys
):
    from elspais.cli import main

    root = _project(tmp_path, monkeypatch, _toml_target("a", stub("junit", "pass"), inputs="a"))
    (root / "a").mkdir()
    (root / "a" / "input.txt").write_text("one\n")
    assert main(["test"]) == 0
    log = tmp_path / "runs.log"
    monkeypatch.setenv("STUB_LOG", str(log))
    capsys.readouterr()

    assert main(["test", "--stale-only"]) == 0

    out, err = capsys.readouterr()
    assert not log.exists(), "a fresh target was executed"
    assert "no target executed" in out
    assert "stale-only: executing none; carrying fresh results of a" in err


def _fresh_and_stale(tmp_path, monkeypatch, stub, *extra_names: str) -> Path:
    """Targets `fresh` and `stale` (and *extra_names*, all stale) with run results."""
    from elspais.cli import main

    names = ("fresh", "stale", *extra_names)
    root = _project(
        tmp_path,
        monkeypatch,
        *(_toml_target(n, stub("junit", "pass"), inputs=n) for n in names),
    )
    for name in names:
        (root / name).mkdir()
        (root / name / "input.txt").write_text("one\n")
    assert main(["test"]) == 0
    for name in names[1:]:
        (root / name / "input.txt").write_text("two\n")
    return root


# Verifies: REQ-d00283-I
def test_naming_a_fresh_target_without_stale_only_executes_it(tmp_path, monkeypatch, stub, capsys):
    from elspais.cli import main

    root = _fresh_and_stale(tmp_path, monkeypatch, stub)
    assert judge(root, _config(root), "fresh").state == "fresh"
    log = tmp_path / "runs.log"
    monkeypatch.setenv("STUB_LOG", str(log))

    assert main(["test", "--targets", "fresh"]) == 0

    assert log.read_text().splitlines() == ["fresh"]


# Verifies: REQ-d00315-A+B
def test_stale_only_narrows_within_the_named_targets(tmp_path, monkeypatch, stub, capsys):
    from elspais.cli import main

    _fresh_and_stale(tmp_path, monkeypatch, stub, "other")
    log = tmp_path / "runs.log"
    monkeypatch.setenv("STUB_LOG", str(log))
    capsys.readouterr()

    assert main(["test", "--stale-only", "--targets", "fresh", "stale"]) == 0

    assert log.read_text().splitlines() == ["stale"]
    assert "stale-only: executing stale; carrying fresh results of fresh" in (
        capsys.readouterr().err
    )


# ---------------------------------------------------------------------------
# `elspais checks --run-tests --stale-only`
# ---------------------------------------------------------------------------


# Verifies: REQ-d00315-I
@pytest.mark.parametrize(
    "flags,named",
    [
        (["--stale-only"], "--stale-only chooses"),
        (["--fail-fast", "--stale-only"], "--fail-fast and --stale-only choose"),
        (
            ["--targets", "a", "--fail-fast", "--stale-only"],
            "--targets, --fail-fast and --stale-only choose",
        ),
    ],
    ids=["alone", "with-fail-fast", "with-targets-and-fail-fast"],
)
def test_checks_refuses_stale_only_without_run_tests(
    tmp_path, monkeypatch, stub, capsys, flags, named
):
    from elspais.cli import main

    log = tmp_path / "runs.log"
    monkeypatch.setenv("STUB_LOG", str(log))
    _project(tmp_path, monkeypatch, _toml_target("a", stub("junit", "pass")))

    assert main(["checks", *flags]) == 2

    err = capsys.readouterr().err
    assert named in err
    assert "Add --run-tests" in err
    assert not log.exists()


_TEST_FILE = "# Verifies: REQ-d00001-A\ndef test_thing():\n    pass\n"

# The test cites an assertion nothing implements; that finding is not under test.
_NO_UNCREDITED = '[rules.coverage]\nuncredited_evidence = "off"\n'


# Verifies: REQ-d00315-F, REQ-d00254-I
@pytest.mark.parametrize("outcome,exit_code", [("pass", 0), ("fail", 1)])
def test_a_carried_failing_result_still_fails_the_checks(
    tmp_path, monkeypatch, stub, capsys, outcome, exit_code
):
    from elspais.cli import main

    root = _project(
        tmp_path,
        monkeypatch,
        _toml_target("unit", stub("junit", outcome)),
        extra=_NO_UNCREDITED,
    )
    (root / "tests").mkdir()
    (root / "tests" / "test_thing.py").write_text(_TEST_FILE)
    # The target records its results; its own exit status is 0 either way.
    assert main(["test"]) == 0
    assert judge(root, _config(root), "unit").state == "fresh"
    log = tmp_path / "runs.log"
    monkeypatch.setenv("STUB_LOG", str(log))
    capsys.readouterr()

    assert main(["checks", "--lenient", "--run-tests", "--stale-only"]) == exit_code

    out, err = capsys.readouterr()
    assert not log.exists(), "the fresh target was executed rather than carried"
    assert "stale-only: executing none; carrying fresh results of unit" in err
    verified = next(line for line in out.splitlines() if "tests.verified" in line)
    assert ("FAILURES DETECTED" in verified) is (outcome == "fail")


def _checks_args(**overrides) -> argparse.Namespace:
    base = {
        "run_tests": True,
        "fail_fast": False,
        "stale_only": True,
        "targets": None,
        "expect": None,
        "config": None,
        "format": "text",
        "lenient": True,
        "quiet": False,
        "verbose": False,
        "include_passing_details": False,
        "spec_only": False,
        "code_only": False,
        "tests_only": False,
        "terms_only": False,
        "spec_dir": None,
        "status": None,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


# Verifies: REQ-d00315-B+F, REQ-d00254-I
def test_checks_marks_only_the_executed_targets_fresh_and_expects_every_selected(
    tmp_path, monkeypatch, stub, capsys
):
    _fresh_and_stale(tmp_path, monkeypatch, stub)
    seen: list = []

    def _local(args, request):
        seen.append((args, request))
        return {"healthy": True, "checks": []}

    monkeypatch.setattr(health, "_run_local_checks", _local)
    log = tmp_path / "runs.log"
    monkeypatch.setenv("STUB_LOG", str(log))

    assert health.run(_checks_args()) == 0

    ((args, request),) = seen
    assert log.read_text().splitlines() == ["stale"]
    assert args._fresh_targets == {"stale"}
    assert set(request.expected_targets) == {"REQ:fresh", "REQ:stale"}
