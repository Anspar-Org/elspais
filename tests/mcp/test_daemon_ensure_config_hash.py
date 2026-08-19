# tests/mcp/test_daemon_ensure_config_hash.py
# Verifies: REQ-d00010, REQ-o00076-I+J

"""How a client decides whether the daemon it found is the daemon it wants.

``serving_difference()`` is the one authority for that question, and
``ensure_daemon`` acts on its answer: a daemon unlike the client is
replaced, unless replacing it would destroy work only that daemon holds,
in which case the difference is disclosed and served from instead.
"""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from elspais import __version__
from elspais.mcp.daemon import (
    ServingDifference,
    StopOutcome,
    compute_config_hash,
    daemon_has_unsaved_work,
    notify_serving_difference,
    serving_difference,
    write_daemon_json,
)
from elspais.mcp.executable import compute_executable_hash


def test_ensure_daemon_restarts_on_config_hash_mismatch(tmp_path: Path):
    """ensure_daemon should restart when config hash has changed."""
    daemon_dir = tmp_path / ".elspais"
    daemon_dir.mkdir()
    daemon_json = daemon_dir / "daemon.json"

    daemon_json.write_text(
        json.dumps(
            {
                "pid": os.getpid(),  # current process (alive)
                "port": 12345,
                "repo_root": str(tmp_path),
                "started_at": "2026-01-01T00:00:00",
                "version": "0.111.53",
                "config_hash": "stale_hash_value_",
            }
        )
    )

    # Create a config file so compute_config_hash returns a real hash
    config_path = tmp_path / ".elspais.toml"
    config_path.write_text('[project]\nname = "test"\n')

    stopped = []
    started = []

    def mock_stop(repo_root):
        stopped.append(repo_root)
        daemon_json.unlink(missing_ok=True)
        return StopOutcome.STOPPED

    def mock_start(repo_root, ttl_minutes=30, client_pid=None):
        started.append(repo_root)
        return 54321

    with (
        patch("elspais.mcp.daemon.stop_daemon", side_effect=mock_stop),
        patch("elspais.mcp.daemon.start_daemon", side_effect=mock_start),
        patch("elspais.__version__", "0.111.53"),
    ):
        from elspais.mcp.daemon import ensure_daemon

        port = ensure_daemon(tmp_path, ttl_minutes=30)

    assert port == 54321
    assert len(stopped) == 1  # old daemon was stopped
    assert len(started) == 1  # new daemon was started


def test_ensure_daemon_keeps_daemon_on_matching_hash(tmp_path: Path):
    """ensure_daemon should keep daemon when config hash matches."""
    daemon_dir = tmp_path / ".elspais"
    daemon_dir.mkdir()
    daemon_json = daemon_dir / "daemon.json"

    # Create config first to get the real hash
    config_path = tmp_path / ".elspais.toml"
    config_path.write_text('[project]\nname = "test"\n')

    from elspais.mcp.daemon import compute_config_hash

    real_hash = compute_config_hash(config_path)

    daemon_json.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "port": 12345,
                "repo_root": str(tmp_path),
                "started_at": "2026-01-01T00:00:00",
                "version": "0.111.53",
                "config_hash": real_hash,
            }
        )
    )

    with patch("elspais.__version__", "0.111.53"):
        from elspais.mcp.daemon import ensure_daemon

        port = ensure_daemon(tmp_path, ttl_minutes=30)

    assert port == 12345  # kept the existing daemon


def _project(tmp_path: Path) -> Path:
    """A working tree with a config, plus the daemon directory."""
    (tmp_path / ".elspais").mkdir(exist_ok=True)
    config_path = tmp_path / ".elspais.toml"
    config_path.write_text('[project]\nname = "test"\n')
    return config_path


def _agreeing_record(tmp_path: Path) -> dict:
    """A daemon record describing a daemon exactly like this client."""
    config_path = _project(tmp_path)
    return {
        "pid": os.getpid(),
        "port": 12345,
        "repo_root": str(tmp_path),
        "started_at": "2026-01-01T00:00:00",
        "version": __version__,
        "config_hash": compute_config_hash(config_path),
        "executable_hash": compute_executable_hash(),
    }


def test_REQ_o00076_I_agreement_is_not_a_difference(tmp_path: Path):
    """Validates REQ-o00076-I: a daemon like the client is left alone.

    Every field a difference could be read from agrees here. Reporting a
    difference anyway would restart a perfectly good daemon on the first
    command that met it, throwing away the warm graph the daemon exists
    to hold.
    """
    difference = serving_difference(_agreeing_record(tmp_path), tmp_path)

    assert difference.version is None
    assert difference.executable is False
    assert difference.config is False
    assert not difference
    assert difference.describe() == ""


def test_REQ_o00076_I_version_difference_reported_alone(tmp_path: Path):
    """Validates REQ-o00076-I: a moved version is reported on its own.

    A client asks one question and gets three separable answers, because
    the remedies differ: a configuration that moved is answered by a
    rebuild and a program that moved is not. A version difference that
    dragged the other two along with it would send a client looking for
    causes that are not there.
    """
    info = _agreeing_record(tmp_path)
    info["version"] = "0.0.1-not-ours"

    difference = serving_difference(info, tmp_path)

    assert difference.version == "0.0.1-not-ours"
    assert difference.executable is False
    assert difference.config is False
    assert difference


def test_REQ_o00076_I_executable_difference_reported_alone(tmp_path: Path):
    """Validates REQ-o00076-I: a reinstalled program is its own difference.

    Between version bumps the recorded version cannot tell a client that
    the daemon is running different code, which for a tree the tool is
    installed from is the ordinary case: editing a source file reinstalls
    the program beneath every daemon serving it. The digest of the
    installed package is what notices, and it notices while the version
    and the configuration both still agree.
    """
    info = _agreeing_record(tmp_path)
    info["executable_hash"] = "0" * 16

    difference = serving_difference(info, tmp_path)

    assert difference.executable is True
    assert difference.version is None
    assert difference.config is False
    assert difference


def test_REQ_o00076_I_config_difference_reported_alone(tmp_path: Path):
    """Validates REQ-o00076-I: an edited configuration is its own difference.

    The daemon holds a graph built from the configuration it started with,
    so a configuration edited since is a daemon answering from inputs the
    client is not using -- while the program it runs is still the client's.
    """
    info = _agreeing_record(tmp_path)
    (tmp_path / ".elspais.toml").write_text('[project]\nname = "renamed"\n')

    difference = serving_difference(info, tmp_path)

    assert difference.config is True
    assert difference.version is None
    assert difference.executable is False
    assert difference


def test_REQ_o00076_I_absent_executable_hash_is_not_a_difference(tmp_path: Path):
    """Validates REQ-o00076-I: an unrecorded program identity is not a mismatch.

    A daemon started by an older elspais records no program digest at all.
    Reading that absence as "differs from mine" would restart every such
    daemon on the first command that met it, which is exactly the daemon
    most likely to be holding a long-lived session's work.
    """
    info = _agreeing_record(tmp_path)
    del info["executable_hash"]

    difference = serving_difference(info, tmp_path)

    assert difference.executable is False
    assert not difference


def test_REQ_o00076_I_no_record_is_no_difference(tmp_path: Path):
    """Validates REQ-o00076-I: nothing serving means nothing to differ from.

    A caller with no daemon record must not be told the daemon differs,
    or it would take the disclose-and-serve branch with nothing to serve
    from.
    """
    _project(tmp_path)

    assert not serving_difference(None, tmp_path)
    assert not serving_difference({}, tmp_path)


@pytest.mark.parametrize(
    "difference,expected",
    [
        (ServingDifference("0.0.1-not-ours", False, False), ["0.0.1-not-ours"]),
        (ServingDifference(None, True, False), ["installation"]),
        (ServingDifference(None, False, True), ["configuration"]),
        (
            ServingDifference("0.0.1-not-ours", True, True),
            ["0.0.1-not-ours", "installation", "configuration"],
        ),
    ],
)
def test_REQ_o00076_J_describe_names_each_difference(difference, expected):
    """Validates REQ-o00076-J: the disclosure names what actually differs.

    A client told only that "something differs" cannot judge what the
    answers it is about to receive are worth. Each difference it carries
    has to reach the words, and a difference it does not carry must not:
    naming a configuration change that did not happen sends the reader
    hunting through a config file that is fine.
    """
    described = difference.describe()

    for fragment in expected:
        assert fragment in described
    for absent in {"0.0.1-not-ours", "installation", "configuration"} - set(expected):
        assert absent not in described


def test_REQ_o00076_J_bool_is_true_only_when_something_differs():
    """Validates REQ-o00076-J: each field alone is enough to disclose.

    The truth value is what both call sites branch on. A field it failed
    to consider would be a difference served in silence -- the precise
    outcome J exists to prevent.
    """
    assert not ServingDifference(None, False, False)
    assert ServingDifference("0.0.1-not-ours", False, False)
    assert ServingDifference(None, True, False)
    assert ServingDifference(None, False, True)


def test_REQ_o00076_J_notification_reaches_stderr(capsys):
    """Validates REQ-o00076-J: the disclosure goes where it cannot corrupt output.

    A client is being handed answers from something unlike itself, so it
    has to be told; but many clients pipe this tool's stdout, and a
    warning mixed into that stream would corrupt the very answers it is
    warning about.
    """
    notify_serving_difference(ServingDifference(None, True, True), "is holding unsaved changes")

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "installation" in captured.err
    assert "configuration" in captured.err
    assert "is holding unsaved changes" in captured.err


def test_REQ_o00076_J_nothing_is_said_when_nothing_differs(capsys):
    """Validates REQ-o00076-J: no difference, no disclosure.

    The obligation is to disclose a difference, not to narrate the check.
    A warning printed on the ordinary path would train every reader to
    ignore the one that matters.
    """
    notify_serving_difference(ServingDifference(None, False, False), "is holding unsaved changes")

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_REQ_o00076_I_written_record_carries_the_program_identity(tmp_path: Path):
    """Validates REQ-o00076-I: a daemon records which program it is running.

    The comparison a client makes has nothing to compare against unless
    the daemon wrote down what it started as, and the digest has to be of
    the installed package rather than any stand-in -- otherwise a client
    running a different installation reads as identical.
    """
    _project(tmp_path)

    daemon_json = write_daemon_json(tmp_path, pid=os.getpid(), port=12345)
    record = json.loads(daemon_json.read_text())

    assert record["executable_hash"]
    assert record["executable_hash"] == compute_executable_hash()
    # A record this client just wrote describes this client.
    assert not serving_difference(record, tmp_path)


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self) -> bytes:
        return self._payload


@pytest.mark.parametrize(
    "payload,expected",
    [
        (b'{"dirty": true, "mutation_count": 2}', True),
        (b'{"dirty": false, "mutation_count": 0}', False),
    ],
)
def test_REQ_o00076_J_unsaved_work_follows_the_reported_count(payload, expected):
    """Validates REQ-o00076-J: only real pending work buys a daemon its life.

    This answer decides whether a differing daemon is replaced or served
    from and disclosed. A daemon holding nothing must be replaced, since
    disclosing a difference that could simply have been removed leaves
    every client on the wrong program for no gain.
    """
    with patch("elspais.mcp.daemon.urlopen", return_value=_FakeResponse(payload)):
        assert daemon_has_unsaved_work({"port": 12345}) is expected


def test_REQ_o00076_J_unreachable_daemon_holds_nothing():
    """Validates REQ-o00076-J: an unanswerable count is not treated as work.

    A daemon nothing can reach is one that stopping will find already
    gone, so reading silence as "it holds work" would pin a client to a
    dead record forever -- disclosing a difference it could have resolved
    and never getting a current daemon.
    """
    from urllib.error import URLError

    with patch("elspais.mcp.daemon.urlopen", side_effect=URLError("refused")):
        assert daemon_has_unsaved_work({"port": 12345}) is False


def test_REQ_o00076_J_ensure_daemon_keeps_a_differing_daemon_holding_work(tmp_path: Path, capsys):
    """Validates REQ-o00076-J: work outranks the program that holds it.

    Restarting here would force an unasked save of somebody's in-progress
    session and lose it outright if that save failed. Answers from an
    older program are recoverable; unwritten work is not -- so the daemon
    serves and the client is told what is serving it.
    """
    config_path = _project(tmp_path)
    daemon_json = tmp_path / ".elspais" / "daemon.json"
    daemon_json.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "port": 12345,
                "repo_root": str(tmp_path),
                "started_at": "2026-01-01T00:00:00",
                "version": __version__,
                "config_hash": compute_config_hash(config_path),
                "executable_hash": "0" * 16,
            }
        )
    )

    stopped = []
    started = []

    def mock_stop(repo_root, **kwargs):
        stopped.append(repo_root)
        return StopOutcome.STOPPED

    def mock_start(repo_root, ttl_minutes=30, client_pid=None):
        started.append(repo_root)
        return 54321

    with (
        patch("elspais.mcp.daemon.stop_daemon", side_effect=mock_stop),
        patch("elspais.mcp.daemon.start_daemon", side_effect=mock_start),
        patch("elspais.mcp.daemon.get_daemon_mutation_count", return_value=2),
        patch("elspais.mcp.daemon.ensure_client_registered", return_value=True),
    ):
        from elspais.mcp.daemon import ensure_daemon

        port = ensure_daemon(tmp_path, ttl_minutes=30)

    assert port == 12345, "the daemon holding the work must be the one served from"
    assert stopped == []
    assert started == []
    err = capsys.readouterr().err
    assert "installation" in err
    assert "unsaved changes" in err
