# Verifies: REQ-d00010

"""Tests that _engine.call injects graph_source metadata."""

from unittest.mock import patch


def test_engine_call_local_includes_graph_source():
    """Local fallback should tag result with graph_source='local'."""
    from elspais.commands._engine import call

    def fake_compute(graph, config, params):
        return {"healthy": True, "checks": []}

    with patch(
        "elspais.commands._engine._ensure_local_graph",
        return_value=(object(), {}),
    ):
        result = call("/api/run/checks", {}, fake_compute, skip_daemon=True)

    assert "graph_source" in result
    assert result["graph_source"]["type"] == "local"


def test_engine_call_daemon_includes_graph_source():
    """Daemon path should tag result with graph_source including port."""
    from elspais.commands._engine import call

    daemon_result = {"healthy": True, "checks": []}

    # _try_daemon returns (result_dict, source_info_dict)
    with patch(
        "elspais.commands._engine._try_daemon",
        return_value=(daemon_result, {"type": "daemon", "port": 35121}),
    ):
        result = call(
            "/api/run/checks", {}, lambda g, c, p: {}, skip_daemon=False
        )

    assert "graph_source" in result
    assert result["graph_source"]["type"] == "daemon"
    assert result["graph_source"]["port"] == 35121


def test_engine_call_viewer_includes_graph_source():
    """Viewer path should tag result with graph_source type='viewer'."""
    from elspais.commands._engine import call

    viewer_result = {"healthy": True, "checks": []}

    with patch(
        "elspais.commands._engine._try_daemon",
        return_value=(viewer_result, {"type": "viewer", "port": 5001}),
    ):
        result = call(
            "/api/run/checks", {}, lambda g, c, p: {}, skip_daemon=False
        )

    assert result["graph_source"]["type"] == "viewer"
