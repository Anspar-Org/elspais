"""Scheduling test targets: concurrent runs, shared resources, and stale-only runs.

Every stub command here is a real subprocess running ``_STUB``. A stub records
its evidence -- monotonic start and end stamps, rendezvous markers, its lines of
output -- inside its own output area (``$ELSPAIS_TARGET_OUTPUT``), which is
outside every target's inputs, or in a file outside the repository. Each
assertion reads that evidence; no assertion reads a wall clock.
"""

from __future__ import annotations

import argparse
import os
import re
import signal
import subprocess
import sys
import time
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
#   hold SECONDS [LOCK [PARTNER]]
#                        stay running for SECONDS; with LOCK, hold an exclusive
#                        lock file for that time and record a violation if it
#                        is already held; with PARTNER, record arrival after
#                        trying the lock and stop early once PARTNER arrives
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
    if len(rest) > 2:
        (out / "here").write_text("1")
        theirs = out.parent / rest[2] / "here"
        deadline = time.monotonic() + float(rest[0])
        while not theirs.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
    else:
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
    the same evidence then records an overlap, so the evidence can see one.

    Each stub holds the lock until its partner arrives, bounded by the hold
    time. Under the scheduler the partner cannot arrive, so a short bound
    keeps the run quick; with the rule removed the two always meet, however
    slowly the second one starts, so a long bound costs nothing."""
    if not resources_honoured:
        monkeypatch.setattr(test_runner, "_resource_keys", lambda target: frozenset())
    lock = tmp_path / "db.lock"
    hold = "0.4" if resources_honoured else "10"
    cfg = _cfg(
        [
            _target("a", stub("hold", hold, str(lock), "b"), resources=["db"]),
            _target("b", stub("hold", hold, str(lock), "a"), resources=["DB"]),
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


# Verifies: REQ-d00314-K
def test_a_target_ends_when_its_command_exits_though_a_background_process_holds_its_output(
    repo, tmp_path, monkeypatch, capfd
):
    """The command leaves a sleeper in the background holding its stdout and
    stderr. The run reports the target when the command exits, not when the
    sleeper does; the sleeper is killed afterwards so it does not linger."""
    monkeypatch.setattr(test_runner, "_DRAIN_SECONDS", 0.2)
    pid_file = tmp_path / "sleeper.pid"
    sleeper = f"import os, time; open(r'{pid_file}', 'w').write(str(os.getpid())); time.sleep(20)"
    cfg = _cfg(
        [_target("bg", f'"{sys.executable}" -c "{sleeper}" & echo started')],
        concurrency=2,
    )

    try:
        began = time.monotonic()
        results, _ = run_configured_targets(cfg, repo)
        elapsed = time.monotonic() - began
    finally:
        deadline = time.monotonic() + 5
        while not pid_file.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        if pid_file.exists() and pid_file.read_text():
            try:
                os.kill(int(pid_file.read_text()), signal.SIGTERM)
            except ProcessLookupError:
                pass
    out, err = capfd.readouterr()

    assert elapsed < 15, f"the run waited {elapsed:.1f}s for the background process"
    assert [(r.name, r.returncode) for r in results] == [("bg", 0)]
    assert "[bg] started" in out.splitlines()
    assert re.search(rf"^<<< bg: passed {_TALLY}$", err, re.M)
    record = read_record(target_folder(repo, cfg, "bg"))
    assert record is not None and record.get("finished_at")


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


def _project(
    tmp_path: Path, monkeypatch, *targets: str, extra: str = "", test_extra: str = ""
) -> Path:
    """A git repository declaring *targets*, made the working directory.

    *test_extra* is written into ``[scanning.test]``. ``cli_ttl = 0`` keeps
    every command in this process rather than starting a daemon."""
    root = tmp_path / "project"
    (root / "spec").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / "spec" / "requirements.md").write_text(_SPEC, encoding="utf-8")
    (root / ".elspais.toml").write_text(
        'version = 5\ncli_ttl = 0\n\n[project]\nname = "runs"\nnamespace = "REQ"\n\n'
        '[scanning.spec]\ndirectories = ["spec"]\n\n'
        "[changelog]\nhash_current = false\n\n"
        f"{extra}\n"
        f"[scanning.test]\nenabled = true\n{test_extra}\n" + "\n".join(targets),
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


# ---------------------------------------------------------------------------
# The record of the targets a run executed
# ---------------------------------------------------------------------------


def _last_run(repo: Path, cfg) -> dict:
    import json

    from elspais.utilities.fingerprint import last_run_path

    return json.loads(last_run_path(repo, cfg).read_text(encoding="utf-8"))


# Verifies: REQ-d00316-A+B+C
def test_a_run_records_the_targets_it_executed_beside_the_output_areas(repo, stub):
    from elspais.utilities.fingerprint import LAST_RUN_NAME, last_run_path, output_root

    names = ("c", "a", "b")
    cfg = _cfg([_target(n, stub("hold", "0")) for n in names])

    results, _ = run_configured_targets(cfg, repo, only={"c", "a"})

    assert sorted(r.name for r in results) == ["a", "c"]
    path = last_run_path(repo, cfg)
    assert path == output_root(repo, cfg) / LAST_RUN_NAME
    record = _last_run(repo, cfg)
    assert record["version"] == 1
    assert record["executed"] == ["a", "c"]
    assert isinstance(record["finished_at"], str) and record["finished_at"]
    for name in names:
        folder = target_folder(repo, cfg, name)
        assert folder not in path.parents and folder != path.parent


# Verifies: REQ-d00316-D
def test_a_record_replaces_the_record_of_every_earlier_run(repo, stub):
    cfg = _cfg([_target(n, stub("hold", "0")) for n in ("a", "b", "c")])

    run_configured_targets(cfg, repo)
    assert _last_run(repo, cfg)["executed"] == ["a", "b", "c"]

    run_configured_targets(cfg, repo, only={"b"})
    assert _last_run(repo, cfg)["executed"] == ["b"]


# Verifies: REQ-d00316-A
def test_a_target_refused_before_its_run_began_is_not_recorded(repo, stub):
    cfg = _cfg([_target("outside", stub("hold", "0"), cwd=".."), _target("b", stub("hold", "0"))])

    results, _ = run_configured_targets(cfg, repo)

    by_name = {r.name: r for r in results}
    assert by_name["outside"].started is False
    assert by_name["b"].started is True
    assert _last_run(repo, cfg)["executed"] == ["b"]


# Verifies: REQ-d00316-A
def test_under_fail_fast_a_target_never_started_is_not_recorded(repo, stub):
    """`a` fails and was executed, so it is recorded; `b` never starts."""
    cfg = _cfg([_target("a", stub("fail", "1")), _target("b", stub("hold", "0"))])

    results, _ = run_configured_targets(cfg, repo, fail_fast=True)

    assert [(r.name, r.returncode) for r in results] == [("a", 1)]
    assert _last_run(repo, cfg)["executed"] == ["a"]


# Verifies: REQ-d00316-A
def test_a_stale_only_run_executing_nothing_records_no_target(tmp_path, monkeypatch, stub):
    from elspais.cli import main

    root = _project(tmp_path, monkeypatch, _toml_target("a", stub("junit", "pass"), inputs="a"))
    (root / "a").mkdir()
    (root / "a" / "input.txt").write_text("one\n")
    assert main(["test"]) == 0
    assert _last_run(root, _config(root))["executed"] == ["a"]

    assert main(["test", "--stale-only"]) == 0

    assert _last_run(root, _config(root))["executed"] == []


def _recorded(tmp_path, monkeypatch, recorded: list[str] | None) -> dict:
    """A config dict declaring targets a, b, c whose last run executed *recorded*.

    ``None`` leaves no record. The git root is pinned to *tmp_path*, where the
    record is read from."""
    from elspais.config import validate_config
    from elspais.utilities.fingerprint import write_last_run

    config = {
        "version": 5,
        "scanning": {
            "test": {
                "enabled": True,
                "targets": [
                    {"name": n, "command": "true", "reporter": "junit"} for n in ("a", "b", "c")
                ],
            }
        },
    }
    monkeypatch.setattr("elspais.config.find_git_root", lambda *a, **k: tmp_path)
    if recorded is not None:
        write_last_run(tmp_path, validate_config(config), recorded)
    return config


# Verifies: REQ-d00316-E
@pytest.mark.parametrize(
    "named,recorded,fresh",
    [
        (["last-run"], ["a"], {"a"}),
        (["Last-Run"], ["a", "c"], {"a", "c"}),
        (["last-run", "b"], ["a"], {"a", "b"}),
    ],
    ids=["alone", "any-case", "with-a-target"],
)
def test_a_reading_run_names_the_targets_of_the_last_run(
    tmp_path, monkeypatch, named, recorded, fresh
):
    from elspais.commands._targets import resolve_fresh_targets

    config = _recorded(tmp_path, monkeypatch, recorded)

    assert resolve_fresh_targets(argparse.Namespace(targets=named), config) == fresh


# Verifies: REQ-d00316-H
def test_a_last_run_that_executed_nothing_selects_no_target(tmp_path, monkeypatch):
    """No target fresh: every result is carried. ``None`` would mean the opposite."""
    from elspais.commands._targets import resolve_fresh_targets

    config = _recorded(tmp_path, monkeypatch, [])

    assert resolve_fresh_targets(argparse.Namespace(targets=["last-run"]), config) == set()


# Verifies: REQ-d00316-F
@pytest.mark.parametrize(
    "content",
    [
        None,
        "not json",
        "[]",
        '{"version": 2, "executed": ["a"]}',
        '{"version": 1, "executed": "a"}',
        '{"version": 1, "executed": [1]}',
    ],
    ids=["absent", "not-json", "not-an-object", "wrong-version", "not-a-list", "not-names"],
)
def test_naming_the_last_run_without_a_readable_record_is_refused(tmp_path, monkeypatch, content):
    from elspais.commands._targets import resolve_fresh_targets
    from elspais.config import validate_config
    from elspais.utilities.fingerprint import last_run_path

    config = _recorded(tmp_path, monkeypatch, None)
    path = last_run_path(tmp_path, validate_config(config))
    if content is not None:
        path.parent.mkdir(parents=True)
        path.write_text(content)

    with pytest.raises(ValueError) as caught:
        resolve_fresh_targets(argparse.Namespace(targets=["last-run"]), config)

    message = str(caught.value)
    assert str(path) in message
    assert "elspais test" in message


# Verifies: REQ-d00316-F
def test_a_selection_not_naming_the_last_run_reads_no_record(tmp_path, monkeypatch):
    from elspais.commands._targets import resolve_fresh_targets

    config = _recorded(tmp_path, monkeypatch, None)

    assert resolve_fresh_targets(argparse.Namespace(targets=["a"]), config) == {"a"}


# Verifies: REQ-d00316-G
def test_a_record_naming_an_unconfigured_target_is_refused_naming_it(tmp_path, monkeypatch):
    from elspais.commands._targets import resolve_fresh_targets

    config = _recorded(tmp_path, monkeypatch, ["a", "retired"])

    with pytest.raises(ValueError) as caught:
        resolve_fresh_targets(argparse.Namespace(targets=["last-run"]), config)

    message = str(caught.value)
    assert "retired" in message
    assert "a, b, c" in message


# Verifies: REQ-d00316-E
def test_summary_reads_the_last_run_as_the_targets_named_by_hand(
    tmp_path, monkeypatch, stub, capsys
):
    from elspais.cli import main

    _project(
        tmp_path,
        monkeypatch,
        *(_toml_target(n, stub("junit", "pass")) for n in ("a", "b", "c")),
    )
    assert main(["test"]) == 0
    assert main(["test", "--targets", "a"]) == 0
    capsys.readouterr()

    assert main(["summary", "--targets", "last-run"]) == 0
    from_record = capsys.readouterr().out
    assert main(["summary", "--targets", "a"]) == 0
    by_hand = capsys.readouterr().out

    assert "2/3 test results from previous runs" in from_record
    assert from_record == by_hand


# Verifies: REQ-d00316-I
@pytest.mark.parametrize(
    "argv,flag",
    [
        (["test", "--targets", "last-run"], "--targets"),
        (["checks", "--run-tests", "--targets", "last-run"], "--targets"),
        (["checks", "--expect", "last-run"], "--expect"),
    ],
    ids=["test", "checks-run-tests", "checks-expect"],
)
def test_a_run_asking_about_itself_refuses_the_last_run(
    tmp_path, monkeypatch, stub, capsys, argv, flag
):
    from elspais.cli import main

    _project(tmp_path, monkeypatch, _toml_target("a", stub("junit", "pass")))
    assert main(["test"]) == 0
    log = tmp_path / "runs.log"
    monkeypatch.setenv("STUB_LOG", str(log))
    capsys.readouterr()

    assert main(argv) == 2

    err = capsys.readouterr().err
    assert f"{flag} last-run names the targets an earlier run executed" in err
    assert not log.exists(), "a target ran"


# Verifies: REQ-d00316-I
def test_expected_targets_refuse_the_last_run(tmp_path, monkeypatch):
    from elspais.commands._targets import resolve_expected_targets

    config = _recorded(tmp_path, monkeypatch, ["a"])

    with pytest.raises(ValueError, match="--expect last-run"):
        resolve_expected_targets(config, ["a", "last-run"])


# Verifies: REQ-d00316-E
@pytest.mark.parametrize(
    "settings",
    [
        {"groups": {"last-run": "the last run"}},
        {"targets": [TestTargetConfig(name="last-run")]},
        {"targets": [TestTargetConfig(name="a", groups=["Last-Run"])]},
    ],
    ids=["declared-group", "target-name", "claimed-group"],
)
def test_no_project_name_can_mean_the_last_run(settings):
    with pytest.raises(ValidationError, match="(?i)last-run"):
        TestScanningConfig(**settings)


# ---------------------------------------------------------------------------
# A run's own maximum of simultaneous targets
# ---------------------------------------------------------------------------


def _test_args(**overrides) -> argparse.Namespace:
    base = {"targets": None, "config": None, "stale_only": False, "fail_fast": False}
    base.update(overrides)
    return argparse.Namespace(**base)


# Verifies: REQ-d00314-O
def test_a_run_raises_the_maximum_the_project_sets(tmp_path, monkeypatch, stub):
    """Each stub passes only if it meets the other while both run."""
    from elspais.commands import test_cmd

    _project(
        tmp_path,
        monkeypatch,
        _toml_target("a", stub("meet", "b")),
        _toml_target("b", stub("meet", "a")),
        test_extra="concurrency = 1",
    )

    assert test_cmd.run(_test_args(concurrency=2)) == 0


# Verifies: REQ-d00314-O
def test_a_run_lowers_the_maximum_the_project_sets(tmp_path, monkeypatch, stub, capfd):
    from elspais.commands import test_cmd

    names = ("zeta", "alpha")
    root = _project(
        tmp_path,
        monkeypatch,
        *(_toml_target(n, stub("say", n.upper(), "2", "0")) for n in names),
        test_extra="concurrency = 2",
    )
    order = tmp_path / "order.log"
    monkeypatch.setenv("STUB_LOG", str(order))

    assert test_cmd.run(_test_args(concurrency=1)) == 0

    out, err = capfd.readouterr()
    assert order.read_text().splitlines() == list(names)
    cfg = _config(root)
    first, second = (_interval(root, cfg, n) for n in names)
    assert first[1] <= second[0]
    assert "ZETA-OUT-0" in out.splitlines()
    assert "] " not in "".join(line for line in (out + err).splitlines() if "-OUT-" in line)


# Verifies: REQ-d00314-P
@pytest.mark.parametrize("value", [0, -1])
@pytest.mark.parametrize("surface", ["test", "checks"])
def test_a_run_maximum_below_one_is_refused_before_any_target_runs(
    tmp_path, monkeypatch, stub, capsys, value, surface
):
    from elspais.commands import test_cmd

    _project(tmp_path, monkeypatch, _toml_target("a", stub("junit", "pass")))
    log = tmp_path / "runs.log"
    monkeypatch.setenv("STUB_LOG", str(log))

    if surface == "test":
        rc = test_cmd.run(_test_args(concurrency=value))
    else:
        rc = health.run(_checks_args(stale_only=False, concurrency=value))

    assert rc == 2
    assert f"--concurrency {value} must be" in capsys.readouterr().err
    assert not log.exists(), "a target ran"


# Verifies: REQ-d00314-P
def test_the_command_line_refuses_a_maximum_of_zero(tmp_path, monkeypatch, stub, capsys):
    from elspais.cli import main

    _project(tmp_path, monkeypatch, _toml_target("a", stub("junit", "pass")))
    log = tmp_path / "runs.log"
    monkeypatch.setenv("STUB_LOG", str(log))

    assert main(["test", "--concurrency", "0"]) == 2

    assert "--concurrency 0 must be" in capsys.readouterr().err
    assert not log.exists(), "a target ran"


# Verifies: REQ-d00314-P
def test_the_runner_refuses_a_maximum_below_one(repo, stub):
    from elspais.utilities.fingerprint import last_run_path

    cfg = _cfg([_target("a", stub("hold", "0"))], concurrency=2)

    with pytest.raises(ValueError, match="--concurrency 0 must be"):
        run_configured_targets(cfg, repo, concurrency=0)

    assert not target_folder(repo, cfg, "a").exists()
    assert not last_run_path(repo, cfg).exists()


# Verifies: REQ-d00314-O
def test_checks_refuses_concurrency_without_run_tests(tmp_path, monkeypatch, stub, capsys):
    from elspais.cli import main

    _project(tmp_path, monkeypatch, _toml_target("a", stub("junit", "pass")))

    assert main(["checks", "--concurrency", "2"]) == 2

    err = capsys.readouterr().err
    assert "--concurrency chooses what --run-tests executes" in err
    assert "Add --run-tests" in err
