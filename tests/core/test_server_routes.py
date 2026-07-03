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
namespace = "REQ"

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


class TestTreeCoverageBucket:
    """REQ-d00258-E: /api/tree-data coverage field uses severity-aware tier bucket."""

    _SPEC_WITH_ASSERTIONS_HEADING = (
        "# REQ-p00001: Test Requirement\n"
        "\n"
        "**Level**: PRD | **Status**: Active\n"
        "\n"
        "Body text.\n"
        "\n"
        "## Assertions\n"
        "\n"
        "A. First assertion\n"
        "\n"
        "*End* *REQ-p00001*\n"
    )

    _CONFIG = (
        _MINIMAL_CONFIG
        + """
[scanning.code]
directories = ["src"]

[scanning.test]
enabled = true
directories = ["tests"]
file_patterns = ["test_*.py"]

[[scanning.test.targets]]
name = "junit"
reporter = "junit"
results = "results.xml"
match = "source"
"""
    )

    @pytest.fixture
    def full_indirect_client(self, tmp_path: Path) -> TestClient:
        """Project with full code+test+passing-result coverage but no UAT/journey.

        This yields a combined validation_color of "yellow-green" (severity.info,
        since uat_coverage/uat_verified default to "none" -> info severity when no
        journey references the requirement). Under the OLD combined_color-based
        bucketing (only exact "green" mapped to "full"), this landed as "none";
        the severity-aware tier bucket must classify it as "full".
        """
        from elspais.server.app import create_app
        from elspais.server.state import AppState

        (tmp_path / ".elspais.toml").write_text(self._CONFIG)
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        (spec_dir / "test.md").write_text(self._SPEC_WITH_ASSERTIONS_HEADING)

        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "impl.py").write_text("# Implements: REQ-p00001-A\ndef do_thing():\n    pass\n")

        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_a.py").write_text("# Verifies: REQ-p00001-A\ndef test_a():\n    pass\n")

        (tmp_path / "results.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<testsuite name="suite" tests="1">\n'
            '  <testcase name="test_a" classname="tests.test_a" time="0.1"/>\n'
            "</testsuite>\n"
        )

        state = AppState.from_config(repo_root=tmp_path)
        app = create_app(state=state, mount_mcp=False)
        return TestClient(app)

    # Verifies: REQ-d00258-E
    def test_tree_coverage_field_uses_tier_bucket(self, full_indirect_client: TestClient):
        """coverage field is drawn from combined_bucket, not a naive color check."""
        resp = full_indirect_client.get("/api/tree-data")
        assert resp.status_code == 200
        rows = resp.json()
        req_rows = [r for r in rows if r["kind"] == "requirement"]
        assert req_rows, "expected at least one requirement row"
        assert all(r["coverage"] in ("full", "partial", "none", "failing") for r in req_rows)

        row = next(r for r in req_rows if r["id"] == "REQ-p00001")
        assert row["validation_color"] == "yellow-green"
        # A full-indirect (yellow-green) requirement must bucket as "full", not "none".
        assert row["coverage"] == "full"


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

        subprocess.run(
            ["git", "init", "-b", "main", str(tmp_path)], capture_output=True, check=True
        )
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

    def test_resolve_host_repo(self, tmp_path):
        from unittest.mock import MagicMock

        from elspais.server.routes_git import _resolve_repo_root

        # Host repo is the first iter_repos() entry in a single-repo graph.
        host_entry = MagicMock()
        host_entry.name = "demo"
        host_entry.repo_root = tmp_path
        host_entry.config = {"project": {"name": "demo", "namespace": "REQ"}}
        host_entry.error = None
        host_entry.graph = MagicMock()
        state = MagicMock()
        state.repo_root = tmp_path
        state.config = {"project": {"name": "demo", "namespace": "REQ"}}
        state.graph.iter_repos.return_value = iter([host_entry])
        assert _resolve_repo_root(state, None) == tmp_path
        # Host is addressable by its configured [project].name.
        state.graph.iter_repos.return_value = iter([host_entry])
        assert _resolve_repo_root(state, "demo") == tmp_path

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

    def test_git_status_host_repo_param(self, client: TestClient):
        """GET /api/git/status?repo=<project.name> resolves to host repo root."""
        resp = client.get("/api/git/status?repo=test-routes")
        assert resp.status_code == 200
        data = resp.json()
        assert "is_detached" in data

    def test_git_status_detached_round_trip_singular_path(self, client: TestClient):
        """Singular-path enter_detached must be observable via /api/git/status.

        Regression: when the host repo's [project].name is e.g. 'test-routes',
        enter_detached keys state under 'test-routes' and the singular
        /api/git/status read must use the same key. Previously the status
        endpoint hardcoded 'root' and missed entries written under the
        project name.
        """
        state = client.app.state.app_state
        host_key = state.config["project"]["name"]
        state.enter_detached(host_key, branch="main", head_commit="deadbeef")
        try:
            resp = client.get("/api/git/status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["is_detached"] is True
            assert data["originating_branch"] == "main"
            assert data["originating_head"] == "deadbeef"
        finally:
            state.leave_detached(host_key)


class TestGitCommitsRepoParam:
    """REQ-p00004-I: /api/git/commits supports ?repo= param."""

    def test_git_commits_default_no_param(self, client: TestClient):
        """GET /api/git/commits without ?repo= returns 200 with a list."""
        resp = client.get("/api/git/commits")
        assert resp.status_code == 200
        data = resp.json()
        # list_commits returns a list directly
        assert isinstance(data, list)

    def test_git_commits_host_repo_param(self, client: TestClient):
        """GET /api/git/commits?repo=<project.name> resolves to host repo root."""
        resp = client.get("/api/git/commits?repo=test-routes")
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


# Verifies: REQ-d00200-G
class TestFileContent:
    """REQ-d00200-G: /api/file-content resolves files via node_id ownership.

    Covers CUR-1357: the endpoint accepts an optional ``node_id`` query
    parameter and, when supplied and known to the federated graph,
    resolves the file against that node's owning repo root via
    ``FederatedGraph.repo_root_for``. Unknown / missing ``node_id``
    falls back to ``state.repo_root``.
    """

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

    _ASSOC_SPEC = (
        "# REQ-p00099: Associate Requirement\n"
        "\n"
        "**Level**: PRD | **Status**: Active\n"
        "\n"
        "Associate body text — distinguishable from root.\n"
        "\n"
        "A. Assoc assertion\n"
        "\n"
        "*End* *REQ-p00099*\n"
    )

    _CORE_CONFIG_WITH_ASSOC = """\
version = 3

[project]
name = "core"
namespace = "REQ"

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

[associates.assoc]
path = "../assoc"
namespace = "REQ"
"""

    _ASSOC_CONFIG = """\
version = 3

[project]
name = "assoc"
namespace = "REQ"

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

    @pytest.fixture
    def root_only_client(self, tmp_path: Path):
        """Single-repo project with a parseable REQ-p00001. Returns (client, state)."""
        from elspais.server.app import create_app
        from elspais.server.state import AppState

        (tmp_path / ".elspais.toml").write_text(_MINIMAL_CONFIG)
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        (spec_dir / "test.md").write_text(self._VALID_SPEC)
        state = AppState.from_config(repo_root=tmp_path)
        return TestClient(create_app(state=state, mount_mcp=False)), state

    @pytest.fixture
    def federated_client(self, tmp_path: Path):
        """Two-repo federation: core + assoc. Returns (client, state, core_root, assoc_root).

        Uses the named ``[associates.assoc]`` format so ``_compute_allowed_roots``
        picks up the associate's root and the security guard allows reading from
        it.
        """
        from elspais.server.app import create_app
        from elspais.server.state import AppState

        core_root = tmp_path / "core"
        assoc_root = tmp_path / "assoc"
        core_root.mkdir()
        assoc_root.mkdir()

        (core_root / ".elspais.toml").write_text(self._CORE_CONFIG_WITH_ASSOC)
        (core_root / "spec").mkdir()
        (core_root / "spec" / "test.md").write_text(self._VALID_SPEC)

        (assoc_root / ".elspais.toml").write_text(self._ASSOC_CONFIG)
        (assoc_root / "spec").mkdir()
        (assoc_root / "spec" / "assoc.md").write_text(self._ASSOC_SPEC)

        state = AppState.from_config(repo_root=core_root)
        client = TestClient(create_app(state=state, mount_mcp=False))
        return client, state, core_root, assoc_root

    def test_file_content_path_only_baseline(self, root_only_client):
        """GET /api/file-content?path=spec/test.md returns 200 with file content."""
        client, _state = root_only_client
        resp = client.get("/api/file-content?path=spec/test.md")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "lines" in data
        # The first line of the spec file is the REQ heading.
        assert data["lines"][0].startswith("# REQ-p00001")

    def test_file_content_root_node_id_resolves(self, root_only_client):
        """node_id pointing at a root-repo node resolves to state.repo_root."""
        client, state = root_only_client
        node = state.graph.find_by_id("REQ-p00001")
        assert node is not None, "fixture must produce REQ-p00001"

        resp = client.get("/api/file-content?path=spec/test.md&node_id=REQ-p00001")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["lines"][0].startswith("# REQ-p00001")

    def test_file_content_unknown_node_id_falls_back(self, root_only_client):
        """Unknown node_id falls back to state.repo_root (graceful, not 500)."""
        client, _state = root_only_client
        resp = client.get("/api/file-content?path=spec/test.md&node_id=NONEXISTENT-ID")
        # path resolves under state.repo_root → 200
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["lines"][0].startswith("# REQ-p00001")

    def test_file_content_unknown_node_id_path_missing_is_404(self, root_only_client):
        """Unknown node_id + nonexistent path returns 404 (not 500)."""
        client, _state = root_only_client
        resp = client.get("/api/file-content?path=spec/does-not-exist.md&node_id=NONEXISTENT-ID")
        assert resp.status_code == 404

    def test_file_content_traversal_blocked(self, root_only_client):
        """Path-traversal outside allowed_roots returns 403."""
        client, _state = root_only_client
        resp = client.get("/api/file-content?path=../../../etc/passwd")
        assert resp.status_code == 403

    def test_file_content_missing_path_returns_400(self, root_only_client):
        """Missing path parameter returns 400."""
        client, _state = root_only_client
        resp = client.get("/api/file-content")
        assert resp.status_code == 400

    def test_file_content_associate_node_id_resolves_to_assoc_repo(self, federated_client):
        """node_id pointing at an associate-repo node reads from assoc_root.

        This is the core CUR-1357 behavior: ``state.repo_root`` is the
        core repo, but the file lives in the associate repo, and
        ``repo_root_for(node_id)`` redirects resolution to the associate.
        """
        client, state, _core_root, assoc_root = federated_client
        node = state.graph.find_by_id("REQ-p00099")
        assert node is not None, "federated fixture must produce REQ-p00099"
        assert state.graph.repo_root_for("REQ-p00099") == assoc_root.resolve()

        # Without node_id: server tries the core root first (file does not
        # exist there) and then falls back through state.allowed_roots,
        # finding the file in the associate. This covers the test/code
        # callers that have a raw file path but no graph node id.
        fallback = client.get("/api/file-content?path=spec/assoc.md")
        assert fallback.status_code == 200, fallback.text
        fallback_data = fallback.json()
        assert any("distinguishable from root" in line for line in fallback_data["lines"])

        # With node_id: server reads assoc/spec/assoc.md and returns its content.
        resp = client.get("/api/file-content?path=spec/assoc.md&node_id=REQ-p00099")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["lines"][0].startswith("# REQ-p00099")
        # Content distinguishable from the root repo's file.
        assert any("distinguishable from root" in line for line in data["lines"])

    # Verifies: REQ-d00200-G
    def test_file_content_repo_name_routes_to_associate(self, federated_client):
        """repo_name=assoc routes path resolution to the associate repo root.

        CUR-1357 Copilot feedback: ``node_id`` is unreliable for FILE node
        ids (they legitimately collide across federated repos). The
        ``repo_name`` query param is the canonical disambiguator —
        consumers that know the owning RepoEntry name can pass it to
        force strict resolution against that repo's root.
        """
        client, _state, _core_root, assoc_root = federated_client
        resp = client.get("/api/file-content?path=spec/assoc.md&repo_name=assoc")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        # Body distinguishable from the core repo's spec/test.md.
        assert data["lines"][0].startswith("# REQ-p00099")
        assert any("distinguishable from root" in line for line in data["lines"])
        # `abs_path` resolves to the associate's on-disk file so the
        # file-viewer's `vscode://` link targets the right location.
        assert data["abs_path"] == str((assoc_root / "spec" / "assoc.md").resolve())

    # Verifies: REQ-d00200-G
    def test_file_content_repo_name_overrides_node_id(self, federated_client):
        """When both repo_name and node_id are supplied, repo_name wins.

        The REQ-p00001 node lives in the core repo, but the caller
        explicitly says ``repo_name=assoc`` — the server must route to
        the associate and return its ``spec/assoc.md``, not the core's
        ``spec/test.md``.
        """
        client, state, _core_root, _assoc_root = federated_client
        # Sanity check: REQ-p00001 lives in the core repo (would otherwise
        # send us to the core repo's spec/assoc.md, which doesn't exist).
        assert state.graph.find_by_id("REQ-p00001") is not None

        resp = client.get("/api/file-content?path=spec/assoc.md&node_id=REQ-p00001&repo_name=assoc")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        # We got the associate's file, not anything from the core repo.
        assert data["lines"][0].startswith("# REQ-p00099")
        assert any("distinguishable from root" in line for line in data["lines"])

    # Verifies: REQ-d00200-G
    def test_file_content_repo_name_strict_no_fallback(self, tmp_path: Path):
        """repo_name disables the allowed_roots fallback (strict resolution).

        Setup: a file ``spec/shared.md`` exists in the *root* repo but
        NOT in the associate. Without ``repo_name`` the allowed_roots
        fallback finds it in root. With ``repo_name=assoc`` the server
        resolves strictly against the associate and returns 404.
        """
        from elspais.server.app import create_app
        from elspais.server.state import AppState

        core_root = tmp_path / "core"
        assoc_root = tmp_path / "assoc"
        core_root.mkdir()
        assoc_root.mkdir()

        (core_root / ".elspais.toml").write_text(self._CORE_CONFIG_WITH_ASSOC)
        (core_root / "spec").mkdir()
        # Core has both its own test.md and a "shared"-named file.
        (core_root / "spec" / "test.md").write_text(self._VALID_SPEC)
        (core_root / "spec" / "shared.md").write_text(self._VALID_SPEC)

        (assoc_root / ".elspais.toml").write_text(self._ASSOC_CONFIG)
        (assoc_root / "spec").mkdir()
        (assoc_root / "spec" / "assoc.md").write_text(self._ASSOC_SPEC)
        # Note: assoc has NO spec/shared.md — that file only exists in core.

        state = AppState.from_config(repo_root=core_root)
        client = TestClient(create_app(state=state, mount_mcp=False))

        # Without repo_name: the file is found via allowed_roots fallback
        # (core is the first allowed_root, so it resolves there).
        no_repo = client.get("/api/file-content?path=spec/shared.md")
        assert no_repo.status_code == 200, no_repo.text

        # With repo_name=assoc: strict mode, no fallback → 404 because
        # the file does not exist in the associate.
        strict = client.get("/api/file-content?path=spec/shared.md&repo_name=assoc")
        assert strict.status_code == 404, strict.text

    # Verifies: REQ-d00200-G
    def test_file_content_unknown_repo_name_falls_back(self, federated_client):
        """An unknown repo_name is handled gracefully — falls back to state.repo_root.

        When ``repo_name`` matches no RepoEntry, the loop in
        ``api_file_content`` leaves ``base_root`` as ``state.repo_root``
        and ``strict_root=False``, so resolution proceeds normally
        against the core repo (with allowed_roots fallback still
        enabled). Should never 500.
        """
        client, _state, _core_root, _assoc_root = federated_client
        # spec/test.md exists in the core repo (state.repo_root).
        resp = client.get("/api/file-content?path=spec/test.md&repo_name=nonexistent")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["lines"][0].startswith("# REQ-p00001")
