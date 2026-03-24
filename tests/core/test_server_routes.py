# Verifies: REQ-d00010-A
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


class TestTreeDataGitMetrics:
    """REQ-d00010-A: /api/tree-data reads git state from node metrics."""

    _VALID_SPEC = (
        "# REQ-p00001: Test Requirement\n"
        "\n"
        "**Level**: PRD | **Status**: Active\n"
        "\n"
        "Body text.\n"
        "\n"
        "A. First assertion\n"
        "\n"
        "*End* *REQ-p00001*\n"
    )

    @pytest.fixture
    def git_metric_client(self, tmp_path: Path):
        """Build a project with a parseable requirement and return (client, state)."""
        import subprocess

        from elspais.server.app import create_app
        from elspais.server.state import AppState

        subprocess.run(["git", "init", str(tmp_path)], capture_output=True, check=True)
        (tmp_path / ".elspais.toml").write_text(_MINIMAL_CONFIG)
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        (spec_dir / "test.md").write_text(self._VALID_SPEC)

        state = AppState.from_config(repo_root=tmp_path)
        app = create_app(state=state, mount_mcp=False)
        return TestClient(app), state

    def test_tree_data_reflects_git_metrics(self, git_metric_client):
        """is_changed and is_uncommitted are read from node metrics, not fields."""
        client, state = git_metric_client
        node = state.graph.find_by_id("REQ-p00001")
        assert node is not None, "fixture should produce REQ-p00001"

        node.set_metric("is_branch_changed", True)
        node.set_metric("is_uncommitted", True)

        resp = client.get("/api/tree-data")
        assert resp.status_code == 200
        rows = resp.json()

        req_row = next((r for r in rows if r["id"] == "REQ-p00001"), None)
        assert req_row is not None, "REQ-p00001 should appear in tree-data"
        assert req_row["is_changed"] is True
        assert req_row["is_uncommitted"] is True


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


class TestResolveRepoRoot:
    """REQ-d00201-A: Resolve repo root from app state."""

    def test_resolve_root_repo(self, tmp_path):
        from unittest.mock import MagicMock

        from elspais.server.routes_git import _resolve_repo_root

        state = MagicMock()
        state.repo_root = tmp_path
        state.graph = MagicMock(spec=[])  # No iter_repos
        assert _resolve_repo_root(state, None) == tmp_path
        assert _resolve_repo_root(state, "root") == tmp_path

    def test_resolve_named_repo(self, tmp_path):
        from unittest.mock import MagicMock

        from elspais.server.routes_git import _resolve_repo_root

        assoc_root = tmp_path / "assoc"
        assoc_root.mkdir()
        entry = MagicMock()
        entry.name = "core"
        entry.repo_root = assoc_root
        entry.config = {}
        entry.error = None
        entry.graph = MagicMock()
        state = MagicMock()
        state.repo_root = tmp_path
        state.graph.iter_repos.return_value = iter([entry])
        assert _resolve_repo_root(state, "core") == assoc_root

    def test_resolve_unknown_raises(self, tmp_path):
        from unittest.mock import MagicMock

        from elspais.server.routes_git import _resolve_repo_root

        state = MagicMock()
        state.repo_root = tmp_path
        state.graph.iter_repos.return_value = iter([])
        with pytest.raises(ValueError, match="Unknown repo"):
            _resolve_repo_root(state, "nonexistent")


class TestRepoStatus:
    """REQ-p00004-I: Bulk repo status for multi-repo support."""

    def test_repo_status_returns_list(self, client: TestClient):
        """GET /api/git/repo-status returns per-repo status."""
        resp = client.get("/api/git/repo-status")
        assert resp.status_code == 200
        data = resp.json()
        assert "repos" in data
        assert isinstance(data["repos"], list)
        assert len(data["repos"]) >= 1
        repo = data["repos"][0]
        assert "name" in repo
        assert "branch" in repo

    def test_repo_status_has_protected_branches(self, client: TestClient):
        """GET /api/git/repo-status includes protected_branches list."""
        resp = client.get("/api/git/repo-status")
        data = resp.json()
        assert "protected_branches" in data
        assert isinstance(data["protected_branches"], list)


class TestMonorepoEligible:
    """REQ-p00004-I: Monorepo eligibility check endpoint."""

    def test_monorepo_eligible_returns_status(self, client: TestClient):
        """GET /api/git/monorepo-eligible returns eligible + reasons."""
        resp = client.get("/api/git/monorepo-eligible")
        assert resp.status_code == 200
        data = resp.json()
        assert "eligible" in data
        assert "reasons" in data
        assert isinstance(data["reasons"], list)

    def test_monorepo_eligible_boolean_field(self, client: TestClient):
        """eligible field is a boolean value."""
        resp = client.get("/api/git/monorepo-eligible")
        data = resp.json()
        assert isinstance(data["eligible"], bool)


class TestGitStatusRepoParam:
    """REQ-p00004-C: /api/git/status supports ?repo= param."""

    def test_git_status_default_no_param(self, client: TestClient):
        """GET /api/git/status without ?repo= works as before."""
        resp = client.get("/api/git/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "is_detached" in data

    def test_git_status_root_param(self, client: TestClient):
        """GET /api/git/status?repo=root resolves to main repo root."""
        resp = client.get("/api/git/status?repo=root")
        assert resp.status_code == 200
        data = resp.json()
        assert "is_detached" in data


class TestGitCommitsRepoParam:
    """REQ-p00004-I: /api/git/commits supports ?repo= param."""

    def test_git_commits_default_no_param(self, client: TestClient):
        """GET /api/git/commits without ?repo= returns 200 with a list."""
        resp = client.get("/api/git/commits")
        assert resp.status_code == 200
        data = resp.json()
        # list_commits returns a list directly
        assert isinstance(data, list)

    def test_git_commits_root_param(self, client: TestClient):
        """GET /api/git/commits?repo=root resolves to main repo root."""
        resp = client.get("/api/git/commits?repo=root")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)


class TestGitBranchMonorepo:
    """REQ-p00004-D: /api/git/branch supports monorepo mode."""

    def test_branch_no_name_returns_400(self, client: TestClient):
        """POST /api/git/branch without name returns 400."""
        resp = client.post("/api/git/branch", json={})
        assert resp.status_code == 400
        data = resp.json()
        assert data["success"] is False

    def test_branch_monorepo_false_single_repo(self, client: TestClient):
        """POST /api/git/branch with monorepo=false uses single-repo path."""
        # This will fail git ops on the tmp dir (not a git repo), but the
        # endpoint should not crash — it returns a 400 with error info.
        resp = client.post("/api/git/branch", json={"name": "test-branch", "monorepo": False})
        # 200 (success) or 400 (git failure) — either is acceptable
        assert resp.status_code in (200, 400)
        data = resp.json()
        assert "success" in data
