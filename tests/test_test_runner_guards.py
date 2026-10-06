"""The test runner's guards must refuse what would corrupt a run.

`.githooks/` runs every test tier, and `tests/conftest.py` refuses a session
that would skip what it was asked to run. These tests drive the guards with
stand-in processes and stand-in directories: a worker count that is not a
positive whole number, a run recorded as in progress, a coverage shard whose
writer is gone, and an extra the session lacks. None of them runs a tier or
touches this checkout's own `.results/`.
"""

import os
import signal
import subprocess
import sys
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


# ---------------------------------------------------------------------------
# tier_execute_foreground
# ---------------------------------------------------------------------------


def _foreground(state: Path, root: Path, *cmd: str) -> subprocess.CompletedProcess:
    return _lib(
        'tier_execute_foreground "$@"; exit $?',
        str(state),
        str(root),
        "sample",
        *cmd,
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
