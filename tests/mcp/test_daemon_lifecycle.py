# Verifies: REQ-d00010, REQ-o00076-K
"""Tests for daemon lifecycle — no orphan servers, and a stable address.

A daemon is replaced often: on a config change, on an idle expiry, on a
developer restarting it. The record naming the process currently serving
a tree is removed when none is, so it cannot also be what tells a client
where the tree is reached — the address has to outlive there being
nothing to reach. These tests cover the separate record that holds it.
"""

import json
from unittest.mock import patch

import pytest


def test_start_daemon_stops_existing_first(tmp_path):
    """start_daemon() must call stop_daemon() before overwriting daemon.json."""
    from elspais.mcp.daemon import start_daemon

    calls = []

    with (
        patch("elspais.mcp.daemon.stop_daemon", side_effect=lambda r: calls.append(("stop", r))),
        patch("elspais.mcp.daemon.get_daemon_info", return_value={"pid": 999, "port": 8888}),
        patch("elspais.mcp.daemon.subprocess.Popen"),
        patch("elspais.mcp.daemon.time.time", side_effect=[0, 0, 0, 20]),  # force timeout
    ):
        try:
            start_daemon(tmp_path, ttl_minutes=1)
        except RuntimeError:
            pass  # Expected: daemon won't actually start

    assert len(calls) == 1
    assert calls[0] == ("stop", tmp_path)


def test_write_daemon_json_includes_type(tmp_path):
    """write_daemon_json() must include a 'type' field."""
    from elspais.mcp.daemon import write_daemon_json

    path = tmp_path / ".elspais" / "daemon.json"
    write_daemon_json(
        repo_root=tmp_path,
        pid=12345,
        port=9999,
        server_type="daemon",
    )

    import json

    data = json.loads(path.read_text())
    assert data["type"] == "daemon"
    assert data["pid"] == 12345
    assert data["port"] == 9999
    assert data["repo_root"] == str(tmp_path)
    assert "version" in data
    assert "started_at" in data


def test_write_daemon_json_viewer_type(tmp_path):
    """write_daemon_json() accepts type='viewer'."""
    from elspais.mcp.daemon import write_daemon_json

    write_daemon_json(
        repo_root=tmp_path,
        pid=12345,
        port=5001,
        server_type="viewer",
    )

    import json

    data = json.loads((tmp_path / ".elspais" / "daemon.json").read_text())
    assert data["type"] == "viewer"


def test_viewer_cleanup_removes_daemon_json(tmp_path):
    """Viewer must remove daemon.json in its finally block."""
    from elspais.mcp.daemon import _daemon_json_path, write_daemon_json

    write_daemon_json(repo_root=tmp_path, pid=99999, port=5001, server_type="viewer")
    path = _daemon_json_path(tmp_path)
    assert path.exists()

    # Simulate viewer cleanup (the finally block)
    path.unlink(missing_ok=True)
    assert not path.exists()


def test_viewer_atexit_removes_daemon_json(tmp_path):
    """atexit handler must remove daemon.json as safety net."""
    from elspais.mcp.daemon import _daemon_json_path, write_daemon_json

    path = _daemon_json_path(tmp_path)
    write_daemon_json(repo_root=tmp_path, pid=99999, port=5001, server_type="viewer")
    assert path.exists()

    # The atexit handler is a closure over daemon_json path
    path.unlink(missing_ok=True)
    assert not path.exists()


# ---------------------------------------------------------------------------
# The address a working tree is reached at (REQ-o00076-K)
# ---------------------------------------------------------------------------


# Verifies: REQ-o00076-K
def test_REQ_o00076_K_reserved_port_round_trips_the_recorded_address(tmp_path):
    """Validates REQ-o00076-K: the address survives replacement only if it
    is written down somewhere a later process reads it back. A client that
    resolved the address once holds it for the rest of its session, so the
    next daemon has to be able to learn where its predecessor answered and
    ask for the same place.
    """
    from elspais.mcp.daemon import reserve_port, reserved_port

    assert reserved_port(tmp_path) is None

    reserve_port(tmp_path, 45678)

    assert reserved_port(tmp_path) == 45678


# Verifies: REQ-o00076-K
@pytest.mark.parametrize(
    "payload",
    [
        pytest.param("not json at all", id="unparseable"),
        pytest.param(json.dumps({"port": "45678"}), id="non-integer"),
        pytest.param(json.dumps({"port": 0}), id="zero"),
        pytest.param(json.dumps({"port": 70000}), id="out-of-range"),
        pytest.param(json.dumps({}), id="absent"),
    ],
)
def test_REQ_o00076_K_unusable_record_reads_as_no_reservation(tmp_path, payload):
    """Validates REQ-o00076-K: a record that cannot name an address must
    read as no address rather than as a bad one. Everything downstream
    hands what it reads to the daemon as the port to bind, and a truthy
    nonsense value would be passed straight through — a tree that would
    have been served on any free port instead fails to be served at all,
    which is a worse outcome than losing the reservation.
    """
    from elspais.mcp.daemon import _port_record_path, reserved_port

    path = _port_record_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload)

    assert reserved_port(tmp_path) is None


# Verifies: REQ-o00076-K, REQ-o00076-E
def test_REQ_o00076_K_address_outlives_the_record_of_what_is_serving(tmp_path):
    """Validates REQ-o00076-K: the address is a different fact from the
    process currently serving, and holding them apart is what lets a tree
    be reached in the same place after serving has stopped and begun
    again. daemon.json is removed whenever nothing serves the tree
    (REQ-o00076-E), so an address kept inside it would be destroyed by the
    ordinary act of shutting the daemon down — exactly when a client that
    resolved it once still needs it to be true.
    """
    from elspais.mcp.daemon import (
        _daemon_json_path,
        _port_record_path,
        reserve_port,
        reserved_port,
        write_daemon_json,
    )

    write_daemon_json(repo_root=tmp_path, pid=99999, port=45678, server_type="daemon")
    reserve_port(tmp_path, 45678)

    daemon_json = _daemon_json_path(tmp_path)
    assert _port_record_path(tmp_path) != daemon_json

    daemon_json.unlink()

    assert reserved_port(tmp_path) == 45678


# Verifies: REQ-o00076-K
def test_REQ_o00076_K_unwritable_reservation_warns_instead_of_failing(tmp_path, capsys):
    """Validates REQ-o00076-K: a tree whose reservation cannot be written
    still gets served. Losing the stable address is a degradation — a
    client that resolved it once may have to resolve it again — while
    raising here would turn it into a tree that cannot be served at all.
    The warning is what keeps the degradation visible rather than silent.
    """
    from elspais.mcp.daemon import reserve_port, reserved_port

    # `.elspais` occupied by a file, so the directory cannot be created.
    (tmp_path / ".elspais").write_text("not a directory")

    reserve_port(tmp_path, 45678)

    assert "warning" in capsys.readouterr().err.lower()
    assert reserved_port(tmp_path) is None


# Verifies: REQ-o00076-K
@pytest.mark.parametrize(
    ("reservation", "expected"),
    [
        pytest.param(45678, "45678", id="reserved"),
        pytest.param(None, "0", id="never-served"),
    ],
)
def test_REQ_o00076_K_start_daemon_asks_for_the_reserved_address(tmp_path, reservation, expected):
    """Validates REQ-o00076-K: recording the address is only half of it —
    the replacement process has to actually ask for it, or the client that
    held the old address still finds nothing there. A tree that has never
    been served has no address to preserve and asks for any free port, so
    the reservation is a request rather than a requirement.
    """
    from elspais.mcp.daemon import reserve_port, start_daemon

    if reservation is not None:
        reserve_port(tmp_path, reservation)

    with (
        patch("elspais.mcp.daemon.subprocess.Popen") as popen,
        patch("elspais.mcp.daemon.time.time", side_effect=[0, 0, 0, 20]),
    ):
        with pytest.raises(RuntimeError):
            start_daemon(tmp_path, ttl_minutes=1)

    argv = popen.call_args[0][0]
    assert argv[argv.index("--port") + 1] == expected
