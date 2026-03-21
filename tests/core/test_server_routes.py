# Implements: REQ-d00010-A
"""Tests for Starlette server routes using TestClient."""
from __future__ import annotations

from pathlib import Path

import pytest
from starlette.testclient import TestClient

_MINIMAL_CONFIG = """\
version = 3

[project]
name = "test-routes"

[levels.prd]
rank = 1
letter = "p"
implements = ["prd"]

[levels.ops]
rank = 2
letter = "o"
implements = ["ops", "prd"]

[levels.dev]
rank = 3
letter = "d"
implements = ["dev", "ops", "prd"]
"""

_SPEC_FILE = """\
# REQ-p00001
Test Requirement

Status: Active
Level: PRD

A. First assertion

*End* [abcd1234]
"""


@pytest.fixture
def elspais_project(tmp_path: Path):
    """Create a minimal elspais project in tmp_path."""
    (tmp_path / ".elspais.toml").write_text(_MINIMAL_CONFIG)
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    (spec_dir / "test.md").write_text(_SPEC_FILE)
    return tmp_path


@pytest.fixture
def app_state(elspais_project: Path):
    """Build an AppState from the minimal project."""
    from elspais.server.state import AppState

    return AppState.from_config(repo_root=elspais_project)


@pytest.fixture
def client(app_state) -> TestClient:
    """Create a Starlette TestClient (no MCP mount)."""
    from elspais.server.app import create_app

    app = create_app(state=app_state, mount_mcp=False)
    return TestClient(app)


class TestStatusEndpoint:
    """REQ-d00010-A: /api/status returns graph metadata."""

    def test_status_returns_node_counts(self, client: TestClient):
        """GET /api/status returns node_counts."""
        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "node_counts" in data

    def test_status_includes_repos(self, client: TestClient):
        """GET /api/status includes repos list."""
        resp = client.get("/api/status")
        data = resp.json()
        assert "repos" in data


class TestSearchEndpoint:
    """REQ-d00010-A: /api/search returns filtered results."""

    def test_search_with_query(self, client: TestClient):
        """GET /api/search?q=REQ returns results dict."""
        resp = client.get("/api/search?q=REQ")
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
        assert isinstance(data["results"], list)

    def test_search_empty_query(self, client: TestClient):
        """GET /api/search?q= returns empty results."""
        resp = client.get("/api/search?q=")
        assert resp.status_code == 200
        data = resp.json()
        assert data == {"results": []}


class TestMutateEndpoint:
    """REQ-d00010-A: mutation endpoints validate input."""

    def test_mutate_status_bad_node_id(self, client: TestClient):
        """POST /api/mutate/status with nonexistent node_id returns error."""
        resp = client.post(
            "/api/mutate/status",
            json={"node_id": "NONEXISTENT", "new_status": "Draft"},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert data["success"] is False

    def test_mutate_status_missing_fields(self, client: TestClient):
        """POST /api/mutate/status without required fields returns 400."""
        resp = client.post("/api/mutate/status", json={})
        assert resp.status_code == 400

    def test_mutate_title_missing_fields(self, client: TestClient):
        """POST /api/mutate/title without required fields returns 400."""
        resp = client.post("/api/mutate/title", json={})
        assert resp.status_code == 400


class TestIndexRoute:
    """REQ-d00010-A: / returns 200 (template or fallback)."""

    def test_index_returns_200(self, client: TestClient):
        """GET / returns 200."""
        resp = client.get("/")
        assert resp.status_code == 200


class TestDirtyEndpoint:
    """REQ-d00010-A: /api/dirty reports mutation state."""

    def test_dirty_clean_graph(self, client: TestClient):
        """GET /api/dirty returns dirty=false for clean graph."""
        resp = client.get("/api/dirty")
        assert resp.status_code == 200
        data = resp.json()
        assert data["dirty"] is False
        assert data["mutation_count"] == 0


class TestTreeData:
    """REQ-d00010-A: /api/tree-data returns requirement tree."""

    def test_tree_data_returns_list(self, client: TestClient):
        """GET /api/tree-data returns a list of rows."""
        resp = client.get("/api/tree-data")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)


class TestCheckFreshness:
    """REQ-p00006-A: /api/check-freshness detects stale files."""

    def test_check_freshness_returns_staleness(self, client: TestClient):
        """GET /api/check-freshness returns stale/pending info."""
        resp = client.get("/api/check-freshness")
        assert resp.status_code == 200
        data = resp.json()
        assert "stale" in data
        assert "has_pending_mutations" in data


class TestNoCacheMiddleware:
    """Middleware adds no-cache headers."""

    def test_no_cache_headers(self, client: TestClient):
        """Responses include Cache-Control: no-store."""
        resp = client.get("/api/status")
        assert "no-store" in resp.headers.get("cache-control", "")
