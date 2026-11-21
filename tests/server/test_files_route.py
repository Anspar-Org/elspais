"""``GET /api/files`` answers as ``compute_files`` does."""

from __future__ import annotations

import json
import os
import time

import pytest
from starlette.testclient import TestClient

from elspais.commands._requests import FilesRequest
from elspais.commands.files_cmd import compute_files
from elspais.server.app import create_app
from elspais.server.state import AppState

PATHS = [
    "database/schema.sql",
    "tests/test_auth.py",
    "spec/dev-impl.md",
    "traceability.md",
    "no/such/file.py",
]


@pytest.fixture(scope="module")
def client(canonical_federated_graph) -> TestClient:
    fg = canonical_federated_graph
    config = fg._repos[fg._root_repo].config
    repo_root = fg._repos[fg._root_repo].repo_root
    state = AppState(graph=fg, repo_root=repo_root, config=config)
    return TestClient(create_app(state, mount_mcp=False))


# Verifies: REQ-d00335-C
def test_the_route_answers_with_the_files_compute_files_gives(
    client, canonical_federated_graph, canonical_config
):
    response = client.get("/api/files", params={"paths": json.dumps(PATHS)})
    assert response.status_code == 200
    body = response.json()
    expected = compute_files(
        canonical_federated_graph,
        canonical_config,
        FilesRequest(paths=tuple(PATHS)),
        built_at=time.time(),
    )
    assert body["files"] == expected["files"]
    verifies = [link for link in body["files"][1]["links"] if link["kind"] == "verifies"]
    assert [link["id"] for link in verifies] == ["REQ-d00001-A", "REQ-d00001-B"]


# Verifies: REQ-d00335-A
@pytest.mark.parametrize(
    "paths",
    [
        pytest.param("src/a.py", id="not-json"),
        pytest.param('{"paths": ["src/a.py"]}', id="object"),
        pytest.param('"src/a.py"', id="string"),
        pytest.param('["src/a.py", 3]', id="non-string-item"),
    ],
)
def test_paths_that_are_not_a_json_array_of_strings_are_refused(client, paths):
    response = client.get("/api/files", params={"paths": paths})
    assert response.status_code == 400
    assert response.json()["error"]


# Verifies: REQ-p00015-E
def test_the_route_marks_a_file_its_held_back_graph_predates(tmp_path, monkeypatch):
    """A serving process holding unsaved changes does not rebuild, so the
    file written since its build is answered as not current and disclosed in
    ``graph_predates``; an untouched file stays current."""
    from elspais.graph.factory import build_graph
    from tests.e2e.helpers import base_config, build_project

    root = build_project(
        tmp_path / "project",
        base_config(name="files-route"),
        code_files={"src/edited.py": {}, "src/untouched.py": {}},
        init_git=False,
    )
    graph = build_graph(repo_root=root)
    state = AppState(graph=graph, repo_root=root, config=graph.root_config)
    client = TestClient(create_app(state, mount_mcp=False))
    # A pending mutation is what keeps the process from rebuilding over the change.
    monkeypatch.setattr(type(graph), "mutation_log", [object()], raising=False)

    later = time.time() + 5
    os.utime(root / "src" / "edited.py", (later, later))

    response = client.get(
        "/api/files",
        params={"paths": json.dumps(["src/edited.py", "src/untouched.py"])},
        headers={"X-Force-Fresh": "1"},
    )
    assert response.status_code == 200
    body = response.json()
    assert state.graph is graph
    edited, untouched = body["files"]
    assert edited["current"] is False
    assert untouched["current"] is True
    assert body["graph_predates"] == ["src/edited.py"]
