"""The test runner's guards must refuse what would corrupt a run.

`.githooks/` runs every test tier, and `tests/conftest.py` refuses a session
that would skip what it was asked to run. These tests drive the guards with
stand-in processes and stand-in directories: a worker count that is not a
positive whole number, a run recorded as in progress, a coverage shard whose
writer is gone, and an extra the session lacks. None of them runs a tier or
touches this checkout's own `.results/`.
"""

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests import conftest as tests_conftest

_REPO = Path(__file__).resolve().parent.parent
_HOOKS = _REPO / ".githooks"
_LIB = _HOOKS / "lib-tier-run.sh"


def _env(**overrides: str) -> dict[str, str]:
    """This process's environment without the runner's own knobs, plus overrides.

    COLUMNS is dropped too: an xdist worker exports one, and the guards' reading
    of a command line under a narrow COLUMNS has a test of its own below.
    """
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("ELSPAIS_TEST_WORKERS", tests_conftest.WITHOUT_ENV, "COLUMNS")
    }
    env.update(overrides)
    return env


def _lib(body: str, *args: str, **env: str) -> subprocess.CompletedProcess:
    """Run *body* in bash with lib-tier-run.sh sourced; *args* are its $1.."""
    return subprocess.run(
        ["bash", "-c", f'. "{_LIB}"; {body}', "_", *args],
        capture_output=True,
        text=True,
        env=_env(**env),
        timeout=60,
    )


@pytest.fixture
def spawn():
    """Start a process in a session of its own; every one is ended on teardown."""
    started: list[subprocess.Popen] = []

    def _spawn(argv: list[str]) -> subprocess.Popen:
        proc = subprocess.Popen(
            argv,
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        started.append(proc)
        return proc

    yield _spawn

    for proc in started:
        if proc.poll() is None:
            # The group, not the pid: a `bash run.sh` waits on a child sleep
            # that terminating bash alone would leave running.
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        proc.wait(timeout=10)


def _dead_pid() -> int:
    proc = subprocess.Popen(["true"])
    proc.wait(timeout=10)
    return proc.pid


def _fake_run(state: Path, spawn) -> subprocess.Popen:
    """A run in progress in *state*: a live `bash <state>/run.sh` named by its pid file."""
    state.mkdir(parents=True, exist_ok=True)
    (state / "run.sh").write_text("#!/bin/bash\nsleep 30\n")
    proc = spawn(["bash", str(state / "run.sh")])
    (state / "pid").write_text(f"{proc.pid}\n")
    return proc


# ---------------------------------------------------------------------------
# test-workers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("value", "printed"), [("4", "4"), ("04", None)])
def test_test_workers_accepts_a_positive_whole_number(value, printed):
    result = subprocess.run(
        ["bash", str(_HOOKS / "test-workers")],
        capture_output=True,
        text=True,
        env=_env(ELSPAIS_TEST_WORKERS=value),
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    if printed is not None:
        assert result.stdout.strip() == printed


@pytest.mark.parametrize("value", ["0", "00", "-1", "abc", " 3", "2.5"])
def test_test_workers_refuses_anything_else_naming_the_variable(value):
    result = subprocess.run(
        ["bash", str(_HOOKS / "test-workers")],
        capture_output=True,
        text=True,
        env=_env(ELSPAIS_TEST_WORKERS=value),
        timeout=30,
    )
    assert result.returncode == 2
    assert "ELSPAIS_TEST_WORKERS" in result.stderr
    assert result.stdout == ""


def test_test_workers_unset_prints_a_positive_count():
    result = subprocess.run(
        ["bash", str(_HOOKS / "test-workers")],
        capture_output=True,
        text=True,
        env=_env(),
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().isdigit()
    assert int(result.stdout.strip()) >= 1


# ---------------------------------------------------------------------------
# tier_run_alive
# ---------------------------------------------------------------------------


def _alive(state: Path) -> bool:
    return _lib('tier_run_alive "$1"', str(state)).returncode == 0


def test_a_state_directory_with_no_pid_is_not_alive(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    assert _alive(state) is False


def test_a_dead_pid_is_not_alive(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    (state / "pid").write_text(f"{_dead_pid()}\n")
    assert _alive(state) is False


def test_a_live_pid_running_something_else_is_not_alive(tmp_path, spawn):
    """A pid reused by an unrelated process names a run that ended."""
    state = tmp_path / "state"
    state.mkdir()
    (state / "run.sh").write_text("#!/bin/bash\nsleep 30\n")
    other = spawn(["sleep", "30"])
    (state / "pid").write_text(f"{other.pid}\n")
    assert _alive(state) is False


def test_a_live_pid_running_this_directorys_run_script_is_alive(tmp_path, spawn):
    state = tmp_path / "state"
    _fake_run(state, spawn)
    assert _alive(state) is True


# ---------------------------------------------------------------------------
# tier_sweep_dead_coverage_shards
# ---------------------------------------------------------------------------


def _shard(root: Path, pid: int) -> Path:
    path = root / f".coverage.testhost.pid{pid}.X123456x"
    path.write_text("")
    return path


def test_the_sweep_removes_abandoned_shards_and_keeps_a_live_writers(tmp_path, spawn):
    dead = _shard(tmp_path, _dead_pid())
    reused = _shard(tmp_path, spawn(["sleep", "30"]).pid)
    writer = spawn([sys.executable, "-c", "import time; time.sleep(30)"])
    live = _shard(tmp_path, writer.pid)

    result = _lib('tier_sweep_dead_coverage_shards "$1"', str(tmp_path))

    assert result.returncode == 0, result.stderr
    assert not dead.exists(), "a shard whose writer is dead survived the sweep"
    assert not reused.exists(), "a shard whose pid now runs a non-python process survived"
    assert live.exists(), "the shard of a live python process was swept"
    # The sweep reports on stderr only: its caller's stdout carries an exit code.
    assert result.stdout == ""


# ---------------------------------------------------------------------------
# A narrow terminal
# ---------------------------------------------------------------------------


def test_a_live_run_is_alive_under_a_narrow_columns(tmp_path, spawn):
    """`ps` cuts a command line to COLUMNS where one is exported, and a run's
    command line is a long path: cut short, it no longer names its run.sh."""
    state = tmp_path / "state"
    _fake_run(state, spawn)
    assert _lib('tier_run_alive "$1"', str(state), COLUMNS="10").returncode == 0


def test_a_live_python_writers_shard_survives_a_narrow_columns(tmp_path, spawn):
    writer = spawn([sys.executable, "-c", "import time; time.sleep(30)"])
    live = _shard(tmp_path, writer.pid)

    result = _lib('tier_sweep_dead_coverage_shards "$1"', str(tmp_path), COLUMNS="10")

    assert result.returncode == 0, result.stderr
    assert live.exists(), "the shard of a live python process was swept"


def test_pid_args_prints_a_live_processs_whole_command_line(tmp_path, spawn):
    """Read where no exported COLUMNS can cut it short."""
    state = tmp_path / "state"
    proc = _fake_run(state, spawn)

    result = _lib('tier_pid_args "$1"', str(proc.pid), COLUMNS="10")

    assert result.returncode == 0, result.stderr
    assert str(state / "run.sh") in result.stdout


# ---------------------------------------------------------------------------
# A process whose command line nothing can read
# ---------------------------------------------------------------------------

_UNSHARE = shutil.which("unshare")


def _proc_can_be_hidden() -> bool:
    """Whether a private mount namespace can cover /proc here."""
    if _UNSHARE is None:
        return False
    probe = subprocess.run(
        [
            _UNSHARE,
            "--user",
            "--map-root-user",
            "--mount",
            "bash",
            "-c",
            "mount -t tmpfs none /proc && ! [ -r /proc/self/cmdline ]",
        ],
        capture_output=True,
        timeout=30,
    )
    return probe.returncode == 0


_needs_hidden_proc = pytest.mark.skipif(
    not _proc_can_be_hidden(),
    reason="no unprivileged mount namespace in which /proc can be covered",
)


def _lib_unreadable(tmp_path: Path, body: str, *args: str) -> subprocess.CompletedProcess:
    """Run *body* with the lib sourced where no command line can be read.

    /proc is covered by an empty tmpfs, and PATH holds only the tools the lib
    needs besides `ps`, so neither source of a command line is available.
    Liveness still answers: `kill -0` asks the kernel, not /proc.
    """
    tools = tmp_path / "tools"
    tools.mkdir(exist_ok=True)
    for name in ("cat", "sed", "rm", "tr"):
        found = shutil.which(name)
        assert found is not None, name
        link = tools / name
        if not link.exists():
            link.symlink_to(found)
    assert shutil.which("ps", path=str(tools)) is None
    script = f'mount -t tmpfs none /proc || exit 99; export PATH="{tools}"; . "{_LIB}"; {body}'
    return subprocess.run(
        [_UNSHARE, "--user", "--map-root-user", "--mount", shutil.which("bash"), "-c", script]
        + ["_", *args],
        capture_output=True,
        text=True,
        env=_env(),
        timeout=60,
    )


@_needs_hidden_proc
def test_pid_args_fails_where_no_command_line_can_be_read(tmp_path, spawn):
    other = spawn(["sleep", "30"])

    result = _lib_unreadable(tmp_path, 'tier_pid_args "$1"', str(other.pid))

    assert result.returncode == 1, result.stderr
    assert result.stdout == ""


@_needs_hidden_proc
def test_a_live_pid_whose_command_line_cannot_be_read_is_alive(tmp_path, spawn):
    """Unreadable is not "something else": the run is judged on liveness alone."""
    state = tmp_path / "state"
    state.mkdir()
    (state / "pid").write_text(f"{spawn(['sleep', '30']).pid}\n")

    result = _lib_unreadable(tmp_path, 'tier_run_alive "$1"', str(state))

    assert result.returncode == 0, result.stderr


@_needs_hidden_proc
def test_the_sweep_keeps_a_shard_whose_live_writer_cannot_be_read(tmp_path, spawn):
    root = tmp_path / "root"
    root.mkdir()
    live = _shard(root, spawn(["sleep", "30"]).pid)
    dead = _shard(root, _dead_pid())

    result = _lib_unreadable(tmp_path, 'tier_sweep_dead_coverage_shards "$1"', str(root))

    assert result.returncode == 0, result.stderr
    assert live.exists(), "the shard of a live process was swept on an unreadable command line"
    assert not dead.exists(), "a shard whose writer is dead survived the sweep"


# ---------------------------------------------------------------------------
# tier_start / tier_wait / tier_tail_until
# ---------------------------------------------------------------------------


def test_tier_start_survives_a_signal_to_its_callers_process_group(tmp_path):
    """The detached run's process group must differ from its caller's.

    `tier_start` backgrounds the run under bash job control (`set -m`) so it
    lands in a process group of its own; a signal to the CALLER's process
    group must not reach it. A driver script calls `tier_start`, reports its
    own pgid and the detached run's pgid, then idles; the test kills the
    driver's whole process group from the outside (as `spawn`'s teardown
    does) and checks the detached run still finishes -- by writing a marker a
    half-killed run never would.
    """
    state = tmp_path / "state"
    root = tmp_path / "root"
    root.mkdir()
    marker = tmp_path / "marker"
    out = tmp_path / "driver-out"
    driver = tmp_path / "driver.sh"
    driver.write_text(
        f"""#!/bin/bash
. "{_LIB}"
tier_start {state!s} k1 {root!s} "" bash -c 'sleep 1; touch {marker!s}'
_dpid=$(cat {state!s}/pid)
printf 'detached_pgid=%s\\n' "$(ps -o pgid= -p "$_dpid" | tr -d ' ')" > {out!s}
printf 'driver_pgid=%s\\n' "$(ps -o pgid= -p $$ | tr -d ' ')" >> {out!s}
sleep 30
"""
    )

    proc = subprocess.Popen(
        ["bash", str(driver)],
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(100):
            if out.exists() and out.read_text().count("\n") >= 2:
                break
            time.sleep(0.1)
        lines = dict(line.split("=", 1) for line in out.read_text().splitlines())
        detached_pgid = lines["detached_pgid"]
        driver_pgid = lines["driver_pgid"]
        assert detached_pgid != driver_pgid, "the detached run shares its driver's process group"

        driver_group = os.getpgid(proc.pid)
        os.killpg(driver_group, signal.SIGTERM)
        proc.wait(timeout=10)

        time.sleep(1.5)
        assert marker.exists(), "the detached run died with the driver it outlives by design"
    finally:
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait(timeout=10)
        # The detached run's own process group may still hold a sleeping
        # `bash run.sh`; it exits on its own once the marker is written, and
        # nothing in this test depends on reaping it further.


def test_tier_wait_relays_growing_output_in_order_and_returns_promptly(tmp_path):
    """`tier_wait` must tail a run's log as it grows and stop soon after the
    run's pid exits, echoing the run's own exit code on stdout."""
    state = tmp_path / "state"
    root = tmp_path / "root"
    root.mkdir()

    start = time.monotonic()
    result = _lib(
        'tier_start "$1" k1 "$2" "" '
        "bash -c 'echo line-one; sleep 0.3; echo line-two; sleep 0.3; echo line-three; exit 7'; "
        'tier_wait "$1"',
        str(state),
        str(root),
    )
    elapsed = time.monotonic() - start

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "7"
    stderr_lines = [line for line in result.stderr.splitlines() if line.strip()]
    assert stderr_lines == ["line-one", "line-two", "line-three"]
    assert elapsed < 5, "tier_wait took suspiciously long to notice the run had exited"


# ---------------------------------------------------------------------------
# tier_require
# ---------------------------------------------------------------------------

_REQUIRED_TOOLS = ("cat", "sed", "rm", "tr", "mkdir", "kill", "ps", "bash", "sleep", "true")


def _tools_dir_without(tmp_path: Path, missing: str) -> Path:
    """A PATH holding every tool the library needs except *missing*."""
    tools = tmp_path / "tools"
    tools.mkdir(exist_ok=True)
    for name in _REQUIRED_TOOLS:
        if name == missing:
            continue
        found = shutil.which(name)
        assert found is not None, name
        link = tools / name
        if not link.exists():
            link.symlink_to(found)
    assert shutil.which(missing, path=str(tools)) is None
    return tools


def test_tier_require_names_the_missing_command(tmp_path):
    tools = _tools_dir_without(tmp_path, "tail")

    result = _lib('tier_require "$1"', "tail", PATH=str(tools))

    assert result.returncode == 1
    assert "'tail'" in result.stderr
    assert "test runner requires" in result.stderr
    assert result.stdout == ""


def test_tier_execute_echoes_1_and_returns_0_where_tail_is_missing(tmp_path):
    """tier_execute's calling convention: failure is echoed, not returned."""
    state = tmp_path / "state"
    root = tmp_path / "root"
    root.mkdir()
    tools = _tools_dir_without(tmp_path, "tail")

    result = _lib(
        'tier_execute "$1" "$2" "$3" sample "" true',
        str(state),
        "some-key",
        str(root),
        PATH=str(tools),
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "1"
    assert "'tail'" in result.stderr
    assert "test runner requires" in result.stderr
    # The check happens before tier_prepare: nothing was ever started.
    assert not state.exists()


def test_tier_execute_foreground_returns_1_directly_where_tail_is_missing(tmp_path):
    """tier_execute_foreground's ordinary-shell convention: 1 is returned."""
    state = tmp_path / "state"
    root = tmp_path / "root"
    root.mkdir()
    tools = _tools_dir_without(tmp_path, "tail")

    result = _foreground(state, root, "true", PATH=str(tools))

    assert result.returncode == 1
    assert "'tail'" in result.stderr
    assert "test runner requires" in result.stderr
    assert not state.exists()


# ---------------------------------------------------------------------------
# tier_execute
# ---------------------------------------------------------------------------


def test_a_hook_run_refuses_while_another_run_is_in_progress(tmp_path, spawn):
    """A run under another key may be one a person started from a terminal."""
    state = tmp_path / "state"
    root = tmp_path / "root"
    root.mkdir()
    _fake_run(state, spawn)

    result = _lib(
        'tier_execute "$1" "$2" "$3" sample "" true',
        str(state),
        "a-key-no-run-holds",
        str(root),
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "1"
    assert "another sample run is in progress" in result.stderr
    assert "started from a terminal" in result.stderr
    assert str(state / "log") in result.stderr
    assert (state / "run.sh").read_text() == "#!/bin/bash\nsleep 30\n"


# ---------------------------------------------------------------------------
# tier_execute_foreground
# ---------------------------------------------------------------------------


def _foreground(state: Path, root: Path, *cmd: str, **env: str) -> subprocess.CompletedProcess:
    return _lib(
        'tier_execute_foreground "$@"; exit $?',
        str(state),
        str(root),
        "sample",
        *cmd,
        **env,
    )


def test_the_foreground_run_refuses_while_a_run_is_in_progress(tmp_path, spawn):
    state = tmp_path / "state"
    root = tmp_path / "root"
    root.mkdir()
    _fake_run(state, spawn)

    result = _foreground(state, root, "true")

    assert result.returncode == 1
    assert "in progress" in result.stderr
    assert str(state / "log") in result.stderr
    # The occupying run's record is left as it was.
    assert (state / "run.sh").read_text() == "#!/bin/bash\nsleep 30\n"


def test_the_foreground_run_returns_the_commands_exit_code_and_keeps_its_log(tmp_path):
    state = tmp_path / "state"
    root = tmp_path / "root"
    root.mkdir()

    result = _foreground(state, root, "bash", "-c", "echo output-of-the-run; exit 3")

    assert result.returncode == 3, result.stderr
    assert (state / "rc").read_text().strip() == "3"
    assert "output-of-the-run" in (state / "log").read_text()
    assert "output-of-the-run" in result.stdout


# ---------------------------------------------------------------------------
# run-target
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def checkout_copy(tmp_path_factory) -> Path:
    """A private copy of this checkout, so no state directory here is touched."""
    from tests.e2e.conftest import private_tree

    copy = private_tree(tmp_path_factory.mktemp("runner-copy"))
    toplevel = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=copy,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return Path(toplevel)


@pytest.mark.parametrize(
    ("target", "state_dir"),
    [
        ("elspais-unit", "run-unit"),
        ("elspais-e2e", "run-e2e"),
        ("elspais-browser", "run-elspais-browser"),
    ],
)
def test_run_target_refuses_while_its_state_directory_holds_a_live_run(
    checkout_copy, spawn, target, state_dir
):
    state = checkout_copy / ".results" / state_dir
    _fake_run(state, spawn)

    # The copy has no venv: run-target falls back to PATH for this tree's tools.
    env = _env(PATH=f"{_REPO / '.venv' / 'bin'}:{os.environ.get('PATH', '')}")
    result = subprocess.run(
        ["bash", str(checkout_copy / ".githooks" / "run-target"), target, "true"],
        cwd=checkout_copy,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )

    assert result.returncode != 0
    assert "in progress" in result.stderr
    assert str(state / "log") in result.stderr


# ---------------------------------------------------------------------------
# conftest: extras a session lacks
# ---------------------------------------------------------------------------

_UNIT_EXPR = "not e2e and not browser and not stress"
_E2E_EXPR = "e2e and not serial"


@pytest.fixture
def clean_guard_env(monkeypatch):
    """No declared exemptions and no xdist worker identity, whatever the tier set."""
    monkeypatch.delenv(tests_conftest.WITHOUT_ENV, raising=False)
    monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)
    monkeypatch.setattr(tests_conftest, "_importable", lambda module: True)
    monkeypatch.setattr(tests_conftest, "_chromium_refusal", lambda: None)
    return monkeypatch


def test_declared_without_reads_a_comma_list(clean_guard_env):
    clean_guard_env.setenv(tests_conftest.WITHOUT_ENV, "mcp, browser")
    assert tests_conftest._declared_without() == {"mcp", "browser"}


def test_declared_without_refuses_a_name_it_cannot_mean(clean_guard_env):
    clean_guard_env.setenv(tests_conftest.WITHOUT_ENV, "foo")
    with pytest.raises(pytest.UsageError) as excinfo:
        tests_conftest._declared_without()
    message = str(excinfo.value)
    assert "foo" in message
    assert "browser" in message
    assert "mcp" in message


def test_a_missing_mcp_refuses_every_session(clean_guard_env):
    clean_guard_env.setattr(tests_conftest, "_importable", lambda module: module != "mcp")

    refusal = tests_conftest._missing_extras_refusal(_UNIT_EXPR)

    assert refusal is not None
    assert "mcp" in refusal
    assert "make setup" in refusal
    assert tests_conftest.WITHOUT_ENV in refusal


def test_a_missing_mcp_is_accepted_when_declared(clean_guard_env):
    clean_guard_env.setattr(tests_conftest, "_importable", lambda module: module != "mcp")
    clean_guard_env.setenv(tests_conftest.WITHOUT_ENV, "mcp")

    assert tests_conftest._missing_extras_refusal(_UNIT_EXPR) is None


@pytest.mark.parametrize("markexpr", [_E2E_EXPR, "browser"])
def test_a_missing_chromium_refuses_a_session_selecting_browser_tests(clean_guard_env, markexpr):
    clean_guard_env.setattr(
        tests_conftest, "_chromium_refusal", lambda: "playwright's chromium is not installed"
    )

    refusal = tests_conftest._missing_extras_refusal(markexpr)

    assert refusal is not None
    assert "browser" in refusal
    assert "chromium" in refusal


def test_a_missing_chromium_does_not_refuse_a_session_selecting_none(clean_guard_env):
    def _probe():
        raise AssertionError("the chromium probe ran for a session selecting no browser test")

    clean_guard_env.setattr(tests_conftest, "_chromium_refusal", _probe)

    assert tests_conftest._missing_extras_refusal(_UNIT_EXPR) is None


def test_a_missing_chromium_is_accepted_when_declared(clean_guard_env):
    clean_guard_env.setattr(
        tests_conftest, "_chromium_refusal", lambda: "playwright's chromium is not installed"
    )
    clean_guard_env.setenv(tests_conftest.WITHOUT_ENV, "browser")

    assert tests_conftest._missing_extras_refusal(_E2E_EXPR) is None


def test_an_xdist_worker_does_not_probe_chromium(clean_guard_env):
    def _probe():
        raise AssertionError("an xdist worker probed for chromium")

    clean_guard_env.setattr(tests_conftest, "_chromium_refusal", _probe)
    clean_guard_env.setenv("PYTEST_XDIST_WORKER", "gw0")

    assert tests_conftest._missing_extras_refusal(_E2E_EXPR) is None


@pytest.mark.parametrize(
    ("markexpr", "names", "expected"),
    [
        (_E2E_EXPR, {"e2e", "browser"}, True),
        (_E2E_EXPR, {"browser"}, False),
        (_UNIT_EXPR, {"e2e", "browser"}, False),
        ("browser", {"browser"}, True),
        ("e2e and serial", {"e2e", "browser"}, False),
    ],
)
def test_selects_marker_set_truth_table(markexpr, names, expected):
    assert tests_conftest._selects_marker_set(markexpr, frozenset(names)) is expected


# ---------------------------------------------------------------------------
# conftest: a bare `python` an e2e fixture target runs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("markexpr", "python", "refused"),
    [
        (_E2E_EXPR, None, True),
        (_E2E_EXPR, "/usr/bin/python", False),
        (_UNIT_EXPR, None, False),
    ],
    ids=["e2e-without-python", "e2e-with-python", "unit-without-python"],
)
def test_bare_python_refusal(monkeypatch, markexpr, python, refused):
    monkeypatch.setattr("shutil.which", lambda name, *a, **k: python if name == "python" else None)

    refusal = tests_conftest._bare_python_refusal(markexpr)

    if not refused:
        assert refusal is None
        return
    assert refusal is not None
    assert "PATH" in refusal
    assert ".venv/bin" in refusal
    assert "make setup" not in refusal
