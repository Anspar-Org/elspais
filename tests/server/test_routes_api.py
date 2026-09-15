# Verifies: REQ-d00282-F, REQ-o00062-O
"""Tests for the /api/run/* and /api/search routes.

No test exercised these routes before this file. The four value-reading
reports (summary, trace, gaps, analysis) refuse an unoffered ``values``
selection with an identical 400 body, produced by ONE shared translator
(``_request_or_400`` in ``routes_api.py``) rather than four hand-written
try/except blocks -- which is exactly how ``/api/run/gaps`` once answered
500 where its siblings answered 400 (a guard written per-route is a guard a
route can be written without). ``/api/run/checks`` and ``/api/search`` read
no value selection and are deliberately NOT behind that helper; they are
covered here too so a regression on either path would not be invisible.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from elspais.server.app import create_app
from elspais.server.state import AppState


@pytest.fixture(scope="module")
def client(canonical_federated_graph) -> TestClient:
    fg = canonical_federated_graph
    config = fg._repos[fg._root_repo].config
    repo_root = fg._repos[fg._root_repo].repo_root
    state = AppState(graph=fg, repo_root=repo_root, config=config)
    return TestClient(create_app(state, mount_mcp=False))


# ---------------------------------------------------------------------------
# The four value-reading reports: identical 400 refusal for an unoffered
# value, and a normal 200 for a request that asks for nothing unoffered.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "endpoint",
    ("/api/run/summary", "/api/run/trace", "/api/run/gaps", "/api/run/analysis"),
)
def test_a_value_a_report_does_not_offer_is_a_bad_request_not_a_crash(client, endpoint):
    """Every report that has values to select among refuses an unoffered name
    the same way. `gaps` returned 500 because its route alone carried no
    guard, which is what a guard written once per route costs."""
    response = client.get(endpoint, params={"values": "no_such_value"})
    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "unoffered_values"
    assert "message" in body


@pytest.mark.parametrize(
    "endpoint",
    ("/api/run/summary", "/api/run/trace", "/api/run/gaps", "/api/run/analysis"),
)
def test_a_request_with_no_unoffered_value_still_returns_the_report(client, endpoint):
    """The guard refuses only an unoffered value; a plain request still
    produces the report it always did."""
    response = client.get(endpoint)
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, (dict, list))


# ---------------------------------------------------------------------------
# The two routes deliberately NOT behind the helper: they read no value
# selection, so a regression there would not show up in the tests above.
# ---------------------------------------------------------------------------


def test_run_checks_still_answers_normally(client):
    response = client.get("/api/run/checks")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, dict)


def test_search_still_answers_normally(client):
    response = client.get("/api/search", params={"q": "REQ"})
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, dict)
