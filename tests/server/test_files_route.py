"""``GET /api/files`` answers as ``compute_files`` does."""

from __future__ import annotations

import json
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
