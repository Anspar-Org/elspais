# Verifies: REQ-o00074-I, REQ-o00074-K, REQ-o00062-O
"""Writes are refused once the process has decided to stop.

A daemon that has decided to terminate keeps a live HTTP stack and live
MCP worker threads until the drain finishes. A mutation accepted in that
window is guarded, applied, acknowledged to its writer -- and then dies
with the process. That is the accepted-then-dropped write the version
guards exist to make impossible, and it is exactly what REQ-o00074-I's
"persist rather than discard" would otherwise be undone by: the daemon
saves what it holds and then swallows whatever arrives next.

Refusal is therefore raised at the moment of the decision, inside the
same critical section that takes it, on BOTH surfaces -- and with the
same body, because REQ-o00062-O's parity claim is about preconditions
and rejection shape, not merely about which routes exist.

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


class TestShutdownFlagIsRaisedByEveryStopPath:
    """Validates REQ-o00074-I: the decision to stop raises the write-refusal
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

    def test_REQ_o00074_I_idle_timeout_raises_the_flag_before_signalling(self, monkeypatch):
        """The TTL path stops the process too, and its drain is no safer."""
        from elspais.mcp.shared_state import SharedServerState
        from elspais.server.middleware import TTLMiddleware

        signals: list[int] = []
        monkeypatch.setattr(
            "elspais.server.middleware.os.kill",
            lambda pid, sig: signals.append(sig),
        )

        shared = SharedServerState()
        mw = TTLMiddleware(app=lambda *a: None, ttl_minutes=60)
        mw._timer.cancel()
        mw._shared = shared

        mw._exit()

        assert shared.is_shutting_down is True, "TTL exit left writes acceptable during the drain"
        assert signals, "TTL exit never signalled the process"


class TestBothSurfacesRefuseWritesAfterTheDecision:
    """Validates REQ-o00074-I and REQ-o00062-O: once the process has decided to
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
        assert (
            app_state.graph.find_by_id(REQ).get_field("title") != "Written during the drain"
        ), "a refused write reached the node"

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
    """Validates REQ-o00062-O: the refusal is a property of the shared write
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
            assert (
                result.get("code") == "server_shutting_down"
            ), f"{name} did not refuse a write after the shutdown decision: {result}"

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
