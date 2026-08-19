# Verifies: REQ-o00074-I+J+K, REQ-p00083-A+B+D+G+H, REQ-o00062-O
"""Stopping the daemon: the work is accounted for, and writes are refused.

Two halves of one decision. A process that decides to stop must first do
something with the changes it holds, and must then stop accepting more.
Both halves belong to one routine (``finalize_shutdown``) that every stop
path runs -- the client-liveness deadline, the idle timeout, and the
fall-through after the server stops serving, which is where an external
signal lands -- so the guarantee is a property of the process rather than
of whichever exit somebody remembered to write a save into.

A daemon that has decided to terminate keeps a live HTTP stack and live
MCP worker threads until the drain finishes. A mutation accepted in that
window is guarded, applied, acknowledged to its writer -- and then dies
with the process. That is the accepted-then-dropped write the version
guards exist to make impossible, and it is exactly what REQ-p00083-A's
"persist rather than discard" would otherwise be undone by: the daemon
saves what it holds and then swallows whatever arrives next.

Refusal is therefore raised inside the same critical section that takes
the decision, on BOTH surfaces -- and with the same body, because
REQ-o00062-O's parity claim is about preconditions and rejection shape,
not merely about which routes exist. Within that section it is raised
*after* the save rather than before it: the check is taken under the same
lock either way, so raising it early buys nothing, and raising it late
leaves a failed save recoverable by a client that can still ask for one.

The suite lives here rather than in test_mcp_http_parity.py because its
fixtures bind ``working_dir`` to the shared ``hht-like`` fixture
directory; these tests need a throwaway project they can plant daemon
state into and let a refused write fail to touch.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from elspais.graph import render

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
HHT_LIKE = FIXTURES_DIR / "hht-like"

REQ = "REQ-d00003"

# The exact keys ``_guard_shutdown`` puts on a rejection. Asserted as a set
# so a surface that hand-rolls a slimmer body is caught.
REFUSAL_KEYS = {"success", "code", "error", "hint"}


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A throwaway copy of the hht-like fixture, per test."""
    dest = tmp_path / "project"
    shutil.copytree(HHT_LIKE, dest)
    return dest


@pytest.fixture
def app_state(project: Path):
    from elspais.server.state import AppState

    return AppState.from_config(repo_root=project)


@pytest.fixture
def client(app_state) -> TestClient:
    from elspais.server.app import create_app

    return TestClient(create_app(state=app_state, mount_mcp=False))


@pytest.fixture
def tools(app_state, project: Path):
    """MCP tool closures over the SAME holder the HTTP app serves.

    Sharing the holder is the point: one ``begin_shutdown()`` has to be
    the same decision on both surfaces, which cannot be asserted across
    two states.
    """
    pytest.importorskip("mcp")
    from elspais.mcp.server import create_server

    server = create_server(app_state.graph, working_dir=project, shared_state=app_state.shared)
    return {name: tool.fn for name, tool in server._tool_manager._tools.items()}


def _version(app_state, node_id: str) -> str:
    node = app_state.graph.find_by_id(node_id)
    assert node is not None, f"fixture node {node_id!r} missing"
    return render.node_version(node)


def _spec_file(app_state, project: Path, node_id: str) -> Path:
    """The on-disk file the node renders into."""
    node = app_state.graph.find_by_id(node_id)
    assert node is not None, f"fixture node {node_id!r} missing"
    file_node = node.file_node()
    assert file_node is not None, f"{node_id} has no FILE ancestor"
    return project / file_node.get_field("relative_path")


def _apply_title(client, app_state, title: str) -> None:
    """Apply one in-memory mutation through the ordinary write route."""
    resp = client.post(
        "/api/mutate/title",
        json={"node_id": REQ, "new_title": title, "if_version": _version(app_state, REQ)},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["success"] is True


class TestShutdownFlagIsRaisedByEveryStopPath:
    """Validates REQ-p00083-G: the decision to stop raises the write-refusal
    flag before the signal that starts the drain, whichever path takes it.
    """

    def test_REQ_o00074_I_flag_starts_down_and_is_irreversible(self):
        from elspais.mcp.shared_state import SharedServerState

        state = SharedServerState()
        assert state.is_shutting_down is False

        state.begin_shutdown()
        assert state.is_shutting_down is True
        state.begin_shutdown()  # idempotent, and there is no way back
        assert state.is_shutting_down is True

    def test_REQ_o00074_I_idle_timeout_raises_the_flag_before_it_ends(self, monkeypatch):
        """The TTL path stops the process too, and a write arriving after it
        has decided to stop is refused rather than taken down with it."""
        from elspais.mcp.shared_state import SharedServerState
        from elspais.server.middleware import TTLMiddleware

        codes: list[object] = []
        monkeypatch.setattr("elspais.server.middleware.os._exit", codes.append)
        monkeypatch.setattr(
            "elspais.server.middleware.os.kill",
            lambda pid, sig: codes.append(f"signal:{sig}"),
        )

        shared = SharedServerState()
        mw = TTLMiddleware(app=lambda *a: None, ttl_minutes=60, shared=shared)
        mw._timer.cancel()

        mw._exit()

        assert shared.is_shutting_down is True, "TTL exit left writes acceptable during the drain"
        assert codes == [0], f"TTL exit never ended the process: {codes}"


class TestBothSurfacesRefuseWritesAfterTheDecision:
    """Validates REQ-p00083-G and REQ-o00062-O: once the process has decided to
    stop, a mutation is refused rather than accepted into a drain that will
    discard it -- and the two surfaces refuse it identically.
    """

    def test_REQ_o00074_I_mcp_refuses_a_write_and_changes_nothing(self, app_state, tools):
        version = _version(app_state, REQ)
        before = len(app_state.graph.mutation_log)

        app_state.shared.begin_shutdown()
        result = tools["mutate_update_title"](
            node_id=REQ, new_title="Written during the drain", if_version=version
        )

        assert result["success"] is False
        assert result["code"] == "server_shutting_down"
        assert set(result) == REFUSAL_KEYS, f"refusal body drifted: {sorted(result)}"
        assert len(app_state.graph.mutation_log) == before, "a refused write reached the log"
        assert app_state.graph.find_by_id(REQ).get_field("title") != "Written during the drain", (
            "a refused write reached the node"
        )

    def test_REQ_o00074_I_http_refuses_a_write_with_409(self, app_state, client):
        version = _version(app_state, REQ)
        before = len(app_state.graph.mutation_log)

        app_state.shared.begin_shutdown()
        resp = client.post(
            "/api/mutate/title",
            json={"node_id": REQ, "new_title": "Written during the drain", "if_version": version},
        )

        assert resp.status_code == 409
        assert resp.json()["code"] == "server_shutting_down"
        assert len(app_state.graph.mutation_log) == before, "a refused write reached the log"

    def test_REQ_o00062_O_the_two_refusals_are_the_same_body(self, app_state, client, tools):
        """Byte-identical, not merely both-4xx: a caller handling one surface's
        rejection must handle the other's with the same code path."""
        version = _version(app_state, REQ)

        app_state.shared.begin_shutdown()
        mcp_body = tools["mutate_update_title"](
            node_id=REQ, new_title="Written during the drain", if_version=version
        )
        resp = client.post(
            "/api/mutate/title",
            json={"node_id": REQ, "new_title": "Written during the drain", "if_version": version},
        )

        assert resp.status_code == 409
        assert resp.json() == mcp_body, (
            "the HTTP and MCP surfaces refuse a shutdown-time write differently: "
            f"{resp.json()} vs {mcp_body}"
        )

    def test_REQ_o00074_I_refusal_precedes_the_version_check(self, app_state, client, tools):
        """A caller holding a stale token still learns the real reason nothing
        happened -- the shutdown, not a conflict it could retry out of."""
        app_state.shared.begin_shutdown()
        stale = "0" * 16

        mcp_body = tools["mutate_update_title"](
            node_id=REQ, new_title="stale and late", if_version=stale
        )
        resp = client.post(
            "/api/mutate/title",
            json={"node_id": REQ, "new_title": "stale and late", "if_version": stale},
        )

        assert mcp_body["code"] == "server_shutting_down"
        assert resp.json()["code"] == "server_shutting_down"

    @pytest.mark.parametrize(
        "route",
        ["/api/save", "/api/revert", "/api/reload"],
    )
    def test_REQ_o00074_I_history_routes_are_refused_too(self, app_state, client, route):
        """Persisting and discarding every writer's pending work are writes."""
        app_state.shared.begin_shutdown()

        resp = client.post(route, json={"if_tip_mutation_id": ""})

        assert resp.status_code == 409
        assert resp.json()["code"] == "server_shutting_down"

    def test_REQ_o00074_I_reads_still_answer_during_the_drain(self, app_state, client, tools):
        """The refusal is scoped to writes: a client still gets an answer about
        what it is losing, which is what the disclosure is for."""
        app_state.shared.begin_shutdown()

        resp = client.get("/api/dirty")
        assert resp.status_code == 200

        status = tools["get_graph_status"]()
        assert "code" not in status
        assert status["total_nodes"] > 0

    def test_REQ_o00074_I_writes_are_accepted_before_the_decision(self, app_state, client, tools):
        """The control: without the flag, the same two calls succeed. Otherwise
        every assertion above would pass against a surface that refuses always.
        """
        resp = client.post(
            "/api/mutate/title",
            json={
                "node_id": REQ,
                "new_title": "Written while serving",
                "if_version": _version(app_state, REQ),
            },
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["success"] is True

        mcp_body = tools["mutate_update_title"](
            node_id=REQ,
            new_title="Written while serving over MCP",
            if_version=_version(app_state, REQ),
        )
        assert mcp_body["success"] is True


class TestEveryWriteSurfaceTakesTheGuard:
    """Validates REQ-o00062-O, REQ-p00083-G: the refusal is a property of the shared write
    critical section, not of the handful of routes somebody remembered. Both
    surfaces reach it through one helper pair, so a new write tool or route
    that joins the lock joins the refusal with it.
    """

    def test_REQ_o00062_O_the_locked_wrapper_checks_the_flag(self, app_state, tools):
        """A sample across unrelated MCP write tools, not one lucky tool."""
        app_state.shared.begin_shutdown()

        calls = {
            "mutate_change_status": {"node_id": REQ, "new_status": "Draft", "if_version": "x"},
            "mutate_add_requirement": {"req_id": "REQ-d09999", "title": "T", "level": "DEV"},
            "save_mutations": {"if_tip_mutation_id": ""},
            "undo_last_mutation": {"if_mutation_id": ""},
        }
        for name, kwargs in calls.items():
            result = tools[name](**kwargs)
            assert result.get("code") == "server_shutting_down", (
                f"{name} did not refuse a write after the shutdown decision: {result}"
            )

    def test_REQ_o00062_O_guard_reports_nothing_when_the_server_is_serving(self, app_state):
        from elspais.mcp.server import _guard_shutdown

        assert _guard_shutdown(app_state.shared) is None
        assert _guard_shutdown(None) is None

        app_state.shared.begin_shutdown()
        rejection = _guard_shutdown(app_state.shared)
        assert rejection is not None
        assert set(rejection) == REFUSAL_KEYS
        assert rejection["success"] is False
        assert rejection["code"] == "server_shutting_down"
        # The hint has to tell the caller its work is intact and how to
        # get it applied; a bare code leaves it guessing whether to retry.
        assert "Nothing was changed" in rejection["hint"]


# ---------------------------------------------------------------------------
# One routine accounts for the work, whatever prompted the stop
# ---------------------------------------------------------------------------


class TestOneRoutineAccountsForTheWorkOnEveryStopPath:
    """Validates REQ-o00074-I, REQ-p00083-A, REQ-p00083-C: a daemon that stops
    while holding unsaved changes persists them rather than discarding them,
    whatever prompted it to stop, and
    records that it saved them itself, when, how many, and what triggered it.

    The stop paths differ only in what they pass as the trigger. They all reach
    ``finalize_shutdown``, so the guarantee is a property of the process rather
    than of the one exit somebody thought to write a save into: the
    client-liveness deadline, the idle timeout, and the fall-through after the
    server stops serving, which is where an external signal lands.
    """

    # Verifies: REQ-p00083-A, REQ-p00083-C
    def test_REQ_o00074_I_pending_work_reaches_disk_and_is_recorded(
        self, app_state, client, project
    ):
        from elspais.mcp.daemon import read_automatic_save
        from elspais.mcp.shared_state import finalize_shutdown

        spec = _spec_file(app_state, project, REQ)
        title = "Persisted by the stopping daemon"
        _apply_title(client, app_state, title)
        assert title not in spec.read_text(), "the mutation reached disk before the stop"

        outcome = finalize_shutdown(app_state.shared, trigger="the idle timeout expired")

        assert outcome["success"] is True, outcome
        assert outcome["finalized"] is True
        assert outcome["pending"] >= 1
        assert outcome["saved"] is True
        assert title in spec.read_text(), "the daemon stopped holding work it never wrote"

        record = read_automatic_save(project)
        assert record is not None, "the daemon saved but left no record of having done so"
        assert record["saved_by"] == "daemon"
        assert record["trigger"] == "the idle timeout expired"
        assert record["mutation_count"] == outcome["pending"]

    # Verifies: REQ-p00083-A, REQ-p00083-G
    def test_REQ_o00074_I_the_refusal_flag_is_raised_only_once_the_work_is_safe(
        self, app_state, client, monkeypatch
    ):
        """Raised last, not first. A failed save must leave the process able to
        accept a client's own save, which a flag raised up front would forbid.
        """
        from elspais.mcp import shared_state

        real = shared_state.persist_pending
        seen: list[bool] = []

        def _watching(state, *args, **kwargs):
            seen.append(state.is_shutting_down)
            return real(state, *args, **kwargs)

        monkeypatch.setattr(shared_state, "persist_pending", _watching)
        _apply_title(client, app_state, "Written before the stop")

        outcome = shared_state.finalize_shutdown(app_state.shared, trigger="t")

        assert outcome["saved"] is True, outcome
        assert seen == [False], f"the flag was already up when the save ran: {seen}"
        assert app_state.shared.is_shutting_down is True, "the stop never refused later writes"

    # Verifies: REQ-p00083-A, REQ-p00083-C
    def test_REQ_o00074_I_repeat_stop_does_not_save_a_second_time(
        self, app_state, client, monkeypatch
    ):
        """Two stop paths can run in one process -- the watchdog decides to stop
        and then the post-serve fall-through runs. The second must not re-save,
        which would overwrite the record with a count of zero."""
        from elspais.mcp import shared_state
        from elspais.mcp.daemon import read_automatic_save

        real = shared_state.persist_pending
        calls: list[str] = []

        def _counting(state, *args, **kwargs):
            calls.append(kwargs.get("trigger", ""))
            return real(state, *args, **kwargs)

        monkeypatch.setattr(shared_state, "persist_pending", _counting)
        _apply_title(client, app_state, "Written before the stop")

        first = shared_state.finalize_shutdown(app_state.shared, trigger="the first trigger")
        second = shared_state.finalize_shutdown(app_state.shared, trigger="the second trigger")

        assert first["finalized"] is True
        assert second["finalized"] is False, "a repeat stop reported itself as the one that acted"
        assert second["saved"] is False
        assert calls == ["the first trigger"], f"the work was saved more than once: {calls}"
        assert read_automatic_save(app_state.shared["working_dir"])["trigger"] == (
            "the first trigger"
        ), "the repeat stop rewrote the record of the save that actually happened"

    # Verifies: REQ-p00083-A, REQ-p00083-G
    def test_REQ_o00074_I_an_external_signal_saves_even_though_the_flag_is_up(
        self, app_state, client, project
    ):
        """The external-stop path in full: the signal handler raises the refusal
        flag on the event loop (it cannot take the write lock there without
        hanging), and the save happens afterwards on the main thread. A routine
        that treated a raised flag as "already handled" would drop every
        signalled daemon's work."""
        from elspais.mcp.shared_state import finalize_shutdown

        spec = _spec_file(app_state, project, REQ)
        title = "Held when the signal arrived"
        _apply_title(client, app_state, title)

        app_state.shared.begin_shutdown()  # what handle_exit does, and all it does
        assert app_state.shared.is_shutting_down is True
        assert app_state.shared.shutdown_finalized is False, (
            "raising the refusal flag was mistaken for having accounted for the work"
        )

        outcome = finalize_shutdown(app_state.shared, trigger="the server stopped serving requests")

        assert outcome["saved"] is True, outcome
        assert title in spec.read_text(), "a signalled daemon discarded the work it held"

    # Verifies: REQ-p00083-A, REQ-p00083-C
    def test_REQ_o00074_I_stopping_with_nothing_pending_writes_no_record(self, app_state, project):
        """A stop is not itself a save. With nothing pending there is nothing to
        write and nothing to disclose, so the next client is told about no save
        that never happened."""
        from elspais.mcp.shared_state import finalize_shutdown

        record_path = project / ".elspais" / "automatic-save.json"
        assert not record_path.exists()

        outcome = finalize_shutdown(app_state.shared, trigger="the idle timeout expired")

        assert outcome["success"] is True
        assert outcome["pending"] == 0
        assert outcome["saved"] is False, "a stop with nothing pending performed a save"
        assert not record_path.exists(), (
            "a stop that saved nothing announced a save to the next client"
        )

    # Verifies: REQ-p00083-H
    def test_REQ_o00074_J_stopping_with_nothing_pending_retires_no_record(self, app_state, project):
        """A record from an earlier automatic save survives a stop that saved
        nothing. Only a save a client asked for retires one, because that is the
        event which makes what the record describes no longer stand."""
        from elspais.mcp.daemon import record_automatic_save
        from elspais.mcp.shared_state import finalize_shutdown

        record_automatic_save(project, mutation_count=7, files_written=2, trigger="an earlier stop")
        record_path = project / ".elspais" / "automatic-save.json"
        before = record_path.read_bytes()

        outcome = finalize_shutdown(app_state.shared, trigger="the server stopped serving requests")

        assert outcome["saved"] is False
        assert record_path.read_bytes() == before, (
            "a stop that saved nothing rewrote or retired a record it did not supersede"
        )


class TestAFailedStopKeepsTheWorkAndTheProcess:
    """Validates REQ-p00083-D: a stop whose save fails keeps the work rather than
    dropping it, leaves the process usable so a client can still save through it,
    and is retried by the next stop path rather than treated as done.
    """

    # Verifies: REQ-p00083-D
    def test_REQ_o00074_K_failed_save_leaves_the_work_reachable_and_retries(
        self, app_state, client, project, monkeypatch
    ):
        from elspais.mcp import shared_state

        spec = _spec_file(app_state, project, REQ)
        title = "Survives a failed stop"
        _apply_title(client, app_state, title)
        pending_before = len(app_state.graph.mutation_log.tail(0))

        real = shared_state.persist_pending
        monkeypatch.setattr(
            shared_state,
            "persist_pending",
            lambda *a, **k: {"success": False, "error": "read-only file system"},
        )

        failed = shared_state.finalize_shutdown(
            app_state.shared, trigger="the idle timeout expired"
        )

        assert failed["success"] is False
        assert failed["finalized"] is False
        assert "read-only file system" in failed["error"]
        assert app_state.shared.is_shutting_down is False, (
            "a failed save refused the client saves that were the way out of it"
        )
        assert app_state.shared.shutdown_finalized is False
        assert len(app_state.graph.mutation_log.tail(0)) == pending_before, (
            "a failed save dropped the work it could not write"
        )
        assert title not in spec.read_text()

        # The next stop path tries again, and succeeds.
        monkeypatch.setattr(shared_state, "persist_pending", real)
        retried = shared_state.finalize_shutdown(
            app_state.shared, trigger="the server stopped serving requests"
        )

        assert retried["success"] is True, retried
        assert retried["saved"] is True
        assert title in spec.read_text(), "the retry never wrote the work it retained"
        assert app_state.shared.is_shutting_down is True


class TestIdleTimeoutStopsThroughTheSameRoutine:
    """Validates REQ-p00083-A and REQ-p00083-D: the idle timeout is a stop like
    any other. An agent that applies a change and then reasons for half an hour
    sends no requests the whole time, so this is the common way a daemon holding
    unsaved work stops -- it persists before it ends, and declines to stop at
    all if it could not.
    """

    @pytest.fixture
    def exits(self, monkeypatch):
        """Capture the exit instead of ending the pytest process.

        Also captures any signal the daemon sends itself: a stop the daemon
        decided on has no supervisor waiting on a drain, so signalling itself
        into one would only be a longer way to the same place -- through a
        drain a held-open client can stall indefinitely.
        """
        codes: list[int] = []
        monkeypatch.setattr("elspais.server.middleware.os._exit", codes.append)
        monkeypatch.setattr(
            "elspais.server.middleware.os.kill",
            lambda pid, sig: codes.append(f"signal:{sig}"),
        )
        return codes

    @pytest.fixture
    def middleware(self, app_state):
        from elspais.server.middleware import TTLMiddleware

        mw = TTLMiddleware(app=lambda *a: None, ttl_minutes=60, shared=app_state.shared)
        yield mw
        if mw._timer is not None:
            mw._timer.cancel()

    # Verifies: REQ-p00083-A
    def test_REQ_o00074_I_idle_timeout_persists_before_it_ends_the_process(
        self, app_state, client, project, middleware, exits
    ):
        from elspais.mcp.daemon import read_automatic_save

        spec = _spec_file(app_state, project, REQ)
        title = "Applied, then the client went quiet"
        _apply_title(client, app_state, title)

        middleware._exit()

        assert title in spec.read_text(), "the idle timeout stopped a daemon holding unsaved work"
        record = read_automatic_save(project)
        assert record is not None
        assert record["trigger"] == "the idle timeout expired", (
            f"the idle timeout did not record what triggered it: {record}"
        )
        assert app_state.shared.is_shutting_down is True
        assert exits == [0], f"the idle timeout did not end the process directly: {exits}"

    # Verifies: REQ-p00083-D
    def test_REQ_o00074_K_idle_timeout_that_cannot_save_waits_instead_of_stopping(
        self, app_state, client, project, middleware, exits, monkeypatch
    ):
        from elspais.mcp import shared_state

        spec = _spec_file(app_state, project, REQ)
        title = "Applied, and the disk said no"
        _apply_title(client, app_state, title)
        monkeypatch.setattr(
            shared_state,
            "persist_pending",
            lambda *a, **k: {"success": False, "error": "disk full"},
        )
        armed = middleware._timer

        middleware._exit()

        assert exits == [], "the daemon ended itself while still holding unwritten work"
        assert app_state.shared.is_shutting_down is False
        assert title not in spec.read_text()
        assert not (project / ".elspais" / "automatic-save.json").exists()
        assert middleware._timer is not armed, "the timer was not restarted, so nothing retries"
        assert middleware._timer.is_alive()


class _RecordedTimer:
    """Stands in for the timer that signals the process, and never fires.

    ``api_shutdown`` schedules its own SIGTERM. In these tests the process it
    would signal is the test runner, so the scheduling is recorded and stopped
    here -- and recorded rather than merely stopped, because "a stop was
    actually set in motion" is half of what several of these tests assert.
    """

    scheduled: list[float] = []

    def __init__(self, interval, function, *args, **kwargs):
        self.interval = interval
        self.function = function
        self.daemon = False

    def start(self) -> None:
        type(self).scheduled.append(self.interval)

    def cancel(self) -> None:  # pragma: no cover - never reached
        pass


@pytest.fixture
def stop_is_not_carried_out(monkeypatch):
    """Let the route decide to stop without the test runner being killed."""
    import threading

    _RecordedTimer.scheduled = []
    monkeypatch.setattr(threading, "Timer", _RecordedTimer)
    return _RecordedTimer


def _tip(client) -> str:
    """The mutation-log tip as a caller reads it before asking for anything."""
    resp = client.get("/api/dirty")
    assert resp.status_code == 200, resp.text
    return resp.json()["tip"] or ""


class TestAnInstructedDiscardIsHonoured:
    """Validates REQ-p00083-B: preservation is what happens when nobody has
    said what the work is worth. An operator who says "throw it away" has
    supplied the statement that was missing, and the work is dropped.

    The instruction covers the changes that existed when it was given and no
    others: a change applied since the caller read the tip is reported rather
    than swept into a discard nobody asked for it to cover.
    """

    def test_REQ_o00074_I_the_instructed_discard_keeps_the_work_off_disk(
        self, app_state, client, project, stop_is_not_carried_out
    ):
        from elspais.mcp.daemon import read_automatic_save

        spec = _spec_file(app_state, project, REQ)
        before = spec.read_bytes()
        title = "Thrown away at the operator's instruction"
        _apply_title(client, app_state, title)

        resp = client.post(
            "/api/shutdown",
            json={"discard_changes": True, "if_tip_mutation_id": _tip(client)},
        )

        assert resp.status_code == 200, resp.text
        payload = resp.json()
        assert payload["discarded"] is True, payload
        assert payload["saved"] is False, "the discard was overridden and the work written anyway"
        assert spec.read_bytes() == before, (
            "the work the operator said to throw away reached disk anyway"
        )
        assert read_automatic_save(project) is None, (
            "a save that never happened was announced to the next client"
        )
        assert stop_is_not_carried_out.scheduled, "the process was not actually going to stop"

    def test_REQ_o00074_I_stopping_without_the_instruction_still_saves(
        self, app_state, client, project, stop_is_not_carried_out
    ):
        """The negative half, and the hole this closed: a stop request carrying
        no instruction is not an instruction to discard. Nobody has said what
        the work is worth, so it is written and the save is disclosed."""
        from elspais.mcp.daemon import read_automatic_save

        spec = _spec_file(app_state, project, REQ)
        title = "Written by an ordinary stop"
        _apply_title(client, app_state, title)
        assert title not in spec.read_text()

        resp = client.post("/api/shutdown")

        assert resp.status_code == 200, resp.text
        payload = resp.json()
        assert payload["saved"] is True, payload
        assert payload["discarded"] is False
        assert title in spec.read_text(), (
            "an ordinary stop destroyed the work the process was holding"
        )
        record = read_automatic_save(project)
        assert record is not None, "the process saved without saying it had"
        assert record["saved_by"] == "daemon"
        assert record["mutation_count"] == payload["pending"]

    def test_REQ_o00074_I_the_discard_covers_only_the_changes_it_named(
        self, app_state, client, project, stop_is_not_carried_out
    ):
        """A writer applied a change between the operator reading the tip and
        the instruction arriving. That change was never in view of whoever gave
        the instruction, so the whole request is refused: it is not destroyed,
        it is not written, and the process stays up holding it."""
        spec = _spec_file(app_state, project, REQ)
        before = spec.read_bytes()

        stale_tip = _tip(client)  # read before anything was pending
        title = "Applied after the operator looked"
        _apply_title(client, app_state, title)

        resp = client.post(
            "/api/shutdown",
            json={"discard_changes": True, "if_tip_mutation_id": stale_tip},
        )

        assert resp.status_code == 409, f"{resp.status_code}: {resp.text}"
        payload = resp.json()
        assert payload["code"] == "mutation_log_conflict"
        assert payload["current_tip"] == _tip(client)
        assert [entry["id"] for entry in payload["unseen"]] == [_tip(client)]

        assert app_state.shared.is_shutting_down is False, (
            "a refused stop request stopped the process anyway"
        )
        assert app_state.shared.shutdown_finalized is False
        assert stop_is_not_carried_out.scheduled == [], "a refused stop was set in motion"
        assert len(app_state.graph.mutation_log) == 1, "the refused discard ran anyway"
        assert app_state.graph.find_by_id(REQ).get_label() == title
        assert spec.read_bytes() == before, "the refused request wrote to disk"

    def test_REQ_o00074_I_refused_discard_can_be_retried_once_the_tip_is_read(
        self, app_state, client, project, stop_is_not_carried_out
    ):
        """The refusal is a conflict, so the documented recipe has to work:
        re-read the tip, look at what arrived, and ask again."""
        _apply_title(client, app_state, "Applied after the operator looked")
        assert (
            client.post(
                "/api/shutdown", json={"discard_changes": True, "if_tip_mutation_id": ""}
            ).status_code
            == 409
        )

        resp = client.post(
            "/api/shutdown",
            json={"discard_changes": True, "if_tip_mutation_id": _tip(client)},
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["discarded"] is True
