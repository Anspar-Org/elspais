"""The viewer's payloads say which members read each term, and whose text it is.

Uses the viewer-term-scope fixture: APP declares LIB, APP defines *Role* and
LIB defines *Session*. APP reads both terms; LIB reads only its own.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from starlette.testclient import TestClient

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "viewer-term-scope"


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    from elspais.config import get_config
    from elspais.graph.factory import build_graph
    from elspais.server.app import create_app
    from elspais.server.state import AppState

    for member in ("app", "lib"):
        shutil.copytree(_FIXTURE / member, tmp_path / member)
    root = tmp_path / "app"
    config = get_config(None, root)
    graph = build_graph(config=config, repo_root=root)
    state = AppState(graph=graph, repo_root=root, config=config)
    return TestClient(create_app(state=state, mount_mcp=False))


# Verifies: REQ-d00239-E
def test_REQ_d00239_E_terms_list_names_the_members_reading_each_term(client: TestClient):
    terms = {t["key"]: t for t in client.get("/api/terms").json()}

    assert sorted(terms["role"]["read_in"]) == ["APP"]
    assert sorted(terms["session"]["read_in"]) == ["APP", "LIB"]


# Verifies: REQ-d00239-E
@pytest.mark.parametrize(
    ("node_id", "namespace"),
    [("APP-d00001", "APP"), ("LIB-d00001", "LIB"), ("APP-d00001-A", "APP")],
)
def test_REQ_d00239_E_node_payload_names_its_member(
    client: TestClient, node_id: str, namespace: str
):
    resp = client.get(f"/api/node/{node_id}")

    assert resp.status_code == 200, resp.text
    assert resp.json()["namespace"] == namespace


# Verifies: REQ-d00239-E
@pytest.mark.parametrize(("repo_name", "namespace"), [("app", "APP"), ("lib", "LIB")])
def test_REQ_d00239_E_file_content_names_the_member_holding_the_file(
    client: TestClient, repo_name: str, namespace: str
):
    resp = client.get(f"/api/file-content?path=spec/dev.md&repo_name={repo_name}")

    assert resp.status_code == 200, resp.text
    assert resp.json()["namespace"] == namespace
