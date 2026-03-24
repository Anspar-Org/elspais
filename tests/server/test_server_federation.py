# Verifies: REQ-d00206-A+B+C
"""Tests for server federation endpoints (/api/repos, /api/status repos field)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from starlette.testclient import TestClient

from elspais.graph import GraphNode, NodeKind
from elspais.graph.builder import TraceGraph
from elspais.graph.federated import FederatedGraph, RepoEntry
from elspais.server.app import create_app
from elspais.server.state import AppState

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_graph(
    repo_root: Path, node_id: str = "REQ-p00001", label: str = "Test Req"
) -> TraceGraph:
    """Create a minimal TraceGraph with one requirement."""
    graph = TraceGraph(repo_root=repo_root)
    node = GraphNode(id=node_id, kind=NodeKind.REQUIREMENT, label=label)
    node._content = {"level": "PRD", "status": "Active", "hash": "abc12345"}
    graph._roots = [node]
    graph._index = {node_id: node}
    return graph


def _make_federated_multi() -> FederatedGraph:
    """Create a multi-repo FederatedGraph with root + associate."""
    root_graph = _make_graph(Path("/test/root"), "REQ-p00001", "Root Req")
    assoc_graph = _make_graph(Path("/test/associate"), "REQ-a00001", "Assoc Req")

    root_entry = RepoEntry(
        name="root",
        graph=root_graph,
        config=None,
        repo_root=Path("/test/root"),
        git_origin="https://github.com/org/root.git",
    )
    assoc_entry = RepoEntry(
        name="associate",
        graph=assoc_graph,
        config=None,
        repo_root=Path("/test/associate"),
        git_origin="https://github.com/org/associate.git",
    )
    return FederatedGraph([root_entry, assoc_entry])


def _make_client(fed: FederatedGraph) -> TestClient:
    """Create a Starlette TestClient from a FederatedGraph."""
    state = AppState(
        graph=fed,
        repo_root=Path("/test/root"),
        config={},
    )
    app = create_app(state=state, mount_mcp=False)
    return TestClient(app)


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestApiRepos:
    """Validates REQ-d00206-A: GET /api/repos returns federated repo list."""

    def test_REQ_d00206_A_api_repos_returns_federation_info(self):
        """GET /api/repos returns repos list with name, path, status fields."""
        fed = _make_federated_multi()
        client = _make_client(fed)

        response = client.get("/api/repos")
        assert response.status_code == 200

        data = response.json()
        assert "repos" in data
        repos = data["repos"]
        assert len(repos) == 2

        # Check required fields present on each repo
        names = {r["name"] for r in repos}
        assert "root" in names
        assert "associate" in names

        for repo in repos:
            assert "name" in repo
            assert "path" in repo
            assert "status" in repo
            assert repo["status"] == "ok"
            assert "git_origin" in repo

    def test_REQ_d00206_A_api_repos_includes_error_state(self):
        """GET /api/repos shows error for repos with graph=None."""
        root_graph = _make_graph(Path("/test/root"), "REQ-p00001", "Root Req")
        root_entry = RepoEntry(
            name="root",
            graph=root_graph,
            config=None,
            repo_root=Path("/test/root"),
        )
        error_entry = RepoEntry(
            name="missing-repo",
            graph=None,
            config=None,
            repo_root=Path("/test/missing"),
            git_origin="https://github.com/org/missing.git",
            error="Repository not found at /test/missing",
        )
        fed = FederatedGraph([root_entry, error_entry])
        client = _make_client(fed)

        response = client.get("/api/repos")
        data = response.json()
        repos = data["repos"]

        error_repo = next(r for r in repos if r["name"] == "missing-repo")
        assert error_repo["status"] == "error"
        assert "error" in error_repo
        assert "not found" in error_repo["error"]

        ok_repo = next(r for r in repos if r["name"] == "root")
        assert ok_repo["status"] == "ok"
        assert "error" not in ok_repo


class TestApiReposStaleness:
    """Validates REQ-d00206-B: GET /api/repos includes staleness info."""

    def test_REQ_d00206_B_api_repos_includes_staleness(self):
        """GET /api/repos includes staleness field for repos with git_origin."""
        fed = _make_federated_multi()
        client = _make_client(fed)

        mock_summary = {
            "branch": "main",
            "remote_diverged": True,
            "fast_forward_possible": True,
        }

        with patch("elspais.utilities.git.git_status_summary", return_value=mock_summary):
            response = client.get("/api/repos")

        data = response.json()
        repos = data["repos"]

        for repo in repos:
            assert "staleness" in repo, f"Repo '{repo['name']}' missing staleness"
            staleness = repo["staleness"]
            assert staleness["branch"] == "main"
            assert staleness["remote_diverged"] is True
            assert staleness["fast_forward_possible"] is True

    def test_REQ_d00206_B_api_repos_no_staleness_without_git_origin(self):
        """Repos without git_origin should not have staleness field."""
        root_graph = _make_graph(Path("/test/root"), "REQ-p00001", "Root Req")
        entry = RepoEntry(
            name="root",
            graph=root_graph,
            config=None,
            repo_root=Path("/test/root"),
            git_origin=None,  # No origin
        )
        fed = FederatedGraph([entry])
        client = _make_client(fed)

        response = client.get("/api/repos")
        data = response.json()
        repo = data["repos"][0]
        assert "staleness" not in repo


class TestApiStatusRepos:
    """Validates REQ-d00206-C: GET /api/status includes repos field."""

    def test_REQ_d00206_C_api_status_includes_repos(self):
        """GET /api/status response contains repos array with federation info."""
        fed = _make_federated_multi()
        client = _make_client(fed)

        response = client.get("/api/status")
        assert response.status_code == 200

        data = response.json()
        assert "repos" in data
        repos = data["repos"]
        assert len(repos) == 2

        names = {r["name"] for r in repos}
        assert "root" in names
        assert "associate" in names

        for repo in repos:
            assert "name" in repo
            assert "path" in repo
            assert "status" in repo

    def test_REQ_d00206_C_api_status_single_repo(self):
        """GET /api/status with single-repo federation has one repos entry."""
        graph = _make_graph(Path("/test/repo"), "REQ-p00001", "Test Req")
        fed = FederatedGraph.from_single(graph, config=None, repo_root=Path("/test/repo"))
        client = _make_client(fed)

        response = client.get("/api/status")
        data = response.json()

        assert "repos" in data
        assert len(data["repos"]) == 1
        assert data["repos"][0]["name"] == "root"
        assert data["repos"][0]["status"] == "ok"
