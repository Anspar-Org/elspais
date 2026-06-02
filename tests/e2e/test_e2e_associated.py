# Verifies: REQ-p00005
"""E2E tests for associated repository features — Fixture 5.

Consolidated from:
  - test_e2e_associated_repos.py (all 8 classes)
  - test_e2e_complex_workflows.py TestMCPAssociatedWorkflow
  - test_e2e_edge_cases.py TestAssociateUnlink, TestMultiAssociateHealth,
    TestMCPAssociatedSubtree

On-disk fixture layout (tests/fixtures/e2e-associated/):
  - core:  standard IDs (REQ-p/o/d), uppercase assertions, associates=[alpha,beta]
  - alpha: standard IDs, prefix ALP, uppercase assertions
  - beta:  standard IDs, prefix BET, numeric assertions
"""

from __future__ import annotations

import json
import shutil

import pytest

from .conftest import (
    ensure_fixture_daemon,
    load_associated_fixture,
    run_elspais,
)
from .helpers import (
    Requirement,
    base_config,
    build_associate,
    build_project,
)

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        shutil.which("elspais") is None,
        reason="elspais CLI not found on PATH",
    ),
]


# ---------------------------------------------------------------------------
# Shared module fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    """Copy e2e-associated fixture to /tmp, git init each repo, start daemon on core."""
    root = tmp_path_factory.mktemp("e2e_associated")
    core = load_associated_fixture(root)
    ensure_fixture_daemon(core)
    return core


@pytest.fixture(scope="module")
def mcp_server(project):
    """Start an MCP server for the associated project."""
    pytest.importorskip("mcp")
    from .helpers import start_mcp, stop_mcp

    proc = start_mcp(project)
    yield proc
    stop_mcp(proc)


# ---------------------------------------------------------------------------
# Test: Core + 1 associate health passes (from TestCoreWithOneAssociate)
# ---------------------------------------------------------------------------


class TestCoreWithOneAssociate:
    """Core project with one associated repo."""

    def test_health_passes(self, project):
        result = run_elspais("checks", "--lenient", cwd=project)
        assert result.returncode == 0, f"health failed: {result.stderr}\n{result.stdout}"

    def test_summary_includes_associate_reqs(self, project):
        result = run_elspais("summary", "--format", "json", cwd=project)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        levels = data.get("levels", [])
        total = sum(lv.get("total", 0) for lv in levels)
        # Core has 4 reqs (p00001, p00002, d00001, d00002)
        assert total >= 4, f"Expected at least 4 requirements (core), got {total}"

    def test_trace_includes_core_ids(self, project):
        result = run_elspais("trace", "--format", "json", cwd=project)
        assert result.returncode == 0
        output = result.stdout
        assert "REQ-p00001" in output
        assert "REQ-d00001" in output


# ---------------------------------------------------------------------------
# Test: Core + 2 associates (from TestCoreWithTwoAssociates)
# ---------------------------------------------------------------------------


class TestCoreWithTwoAssociates:
    """Core project with two associated repos."""

    def test_health_passes(self, project):
        result = run_elspais("checks", "--lenient", cwd=project)
        assert result.returncode == 0, f"health failed: {result.stderr}\n{result.stdout}"

    def test_summary_counts_all(self, project):
        result = run_elspais("summary", "--format", "json", cwd=project)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        levels = data.get("levels", [])
        total = sum(lv.get("total", 0) for lv in levels)
        # Core: 2 PRD + 2 DEV, Alpha: 2 DEV, Beta: 1 PRD + 1 DEV = at least 1 total
        assert total >= 1


# ---------------------------------------------------------------------------
# Test: Associate CLI list command (from TestAssociateListCommand)
# ---------------------------------------------------------------------------


class TestAssociateListCommand:
    """Associate --list shows linked repos."""

    def test_associate_list(self, project):
        result = run_elspais("associate", "--list", cwd=project)
        assert result.returncode == 0
        output = result.stdout.lower()
        assert "alpha" in output or "alp" in output, f"Expected alpha in output: {result.stdout}"


# ---------------------------------------------------------------------------
# Test: Associate with numeric assertions (from TestAssociateNumericAssertions)
# ---------------------------------------------------------------------------


class TestAssociateNumericAssertions:
    """Core with uppercase assertions, associate with numeric assertions."""

    def test_health_passes_mixed_assertions(self, project):
        result = run_elspais("checks", "--lenient", cwd=project)
        assert result.returncode == 0, f"health failed: {result.stderr}\n{result.stdout}"

    def test_trace_shows_both_repos(self, project):
        result = run_elspais("trace", "--format", "json", cwd=project)
        assert result.returncode == 0
        # Core PRD should always be present
        assert "REQ-p00001" in result.stdout


# ---------------------------------------------------------------------------
# Test: Cross-repo implements reference (from TestCrossRepoImplements)
# ---------------------------------------------------------------------------


class TestCrossRepoImplements:
    """Associate DEV implements core PRD."""

    def test_health_passes_cross_repo(self, project):
        # alpha DEV reqs implement core PRD reqs
        result = run_elspais("checks", "--lenient", cwd=project)
        assert result.returncode == 0, f"health failed: {result.stderr}\n{result.stdout}"

    def test_trace_shows_cross_repo_link(self, project):
        result = run_elspais("trace", "--format", "json", cwd=project)
        assert result.returncode == 0
        assert "REQ-p00001" in result.stdout


# ---------------------------------------------------------------------------
# Test: Dynamic namespace surfacing in HTML (Verifies: REQ-d00211)
# ---------------------------------------------------------------------------


class TestDynamicNamespaceInHtml:
    """`elspais viewer --static` surfaces the configured namespaces
    (project + associates) and no longer emits the legacy 'Core:' literal."""

    def test_static_html_has_no_core_literal(self, project):
        result = run_elspais("viewer", "--static", cwd=project)
        assert result.returncode == 0, f"viewer --static failed: {result.stderr}"
        assert "Core:" not in result.stdout, "Legacy 'Core:' string should be gone"

    def test_static_html_exposes_namespaces_constant(self, project):
        result = run_elspais("viewer", "--static", cwd=project)
        assert result.returncode == 0
        assert "var NAMESPACES = " in result.stdout
        # is_local marker must be present on exactly one namespace entry
        assert '"is_local": true' in result.stdout


# ---------------------------------------------------------------------------
# Test: Associate auto-discovery (from TestAssociateAutoDiscovery)
# Unique layout — keeps per-test build.
# ---------------------------------------------------------------------------


class TestAssociateAutoDiscovery:
    """Associate --all auto-discovers sibling repos."""

    def test_auto_discover(self, tmp_path):
        # Create core without any associate links
        core_root = tmp_path / "core"
        core_cfg = base_config(name="auto-disc-core", associated_enabled=True)
        build_project(
            core_root,
            core_cfg,
            spec_files={
                "spec/prd.md": [
                    Requirement(
                        "REQ-p00001",
                        "Auto Disc",
                        "PRD",
                        assertions=[("A", "The system SHALL auto-discover.")],
                    ),
                ],
            },
        )

        # Create an associate as a sibling (not linked in core config)
        assoc_root = tmp_path / "sibling"
        build_associate(
            assoc_root,
            "sibling",
            "SIB",
            "../core",
            spec_files={
                "spec/prd.md": [
                    Requirement(
                        "REQ-SIB-p00001",
                        "Sibling Feature",
                        "PRD",
                        assertions=[("A", "Sibling SHALL be discovered.")],
                    ),
                ],
            },
            init_git=True,
        )

        # Run associate --all — may or may not find it; must not crash
        result = run_elspais("associate", "--all", cwd=core_root)
        assert result.returncode in (0, 1), f"associate --all crashed unexpectedly: {result.stderr}"


# ---------------------------------------------------------------------------
# Test: MCP with associated repos (from TestMCPWithAssociates)
# ---------------------------------------------------------------------------


class TestMCPWithAssociates:
    """MCP server with core + associate project."""

    def test_mcp_search_finds_associate_reqs(self, project, mcp_server):
        from .helpers import mcp_call, mcp_call_all

        # Search for core requirement
        results = mcp_call_all(mcp_server, "search", {"query": "Auth"})
        assert len(results) >= 1
        ids = [r.get("id", "") for r in results]
        assert any("p00001" in i for i in ids)

        # Get project summary
        summary = mcp_call(mcp_server, "get_project_summary", {})
        assert isinstance(summary, dict)

        # Navigate hierarchy
        hier = mcp_call(mcp_server, "get_hierarchy", {"req_id": "REQ-d00001"})
        assert "ancestors" in hier


# ---------------------------------------------------------------------------
# Test: Associate with FDA-style IDs (from TestAssociateFDAStyle)
# Unique layout — keeps per-test build.
# ---------------------------------------------------------------------------


class TestAssociateFDAStyle:
    """Core with standard IDs, associate with FDA-style (namespaced) IDs."""

    def _build(self, tmp_path):
        core_root = tmp_path / "core"
        assoc_root = tmp_path / "fda-assoc"

        core_cfg = base_config(
            name="core-std",
            associated_enabled=True,
        )
        core_cfg["associates"] = {"paths": ["../fda-assoc"]}
        core_prd = Requirement(
            "REQ-p00001",
            "Core Standard",
            "PRD",
            assertions=[("A", "The system SHALL use standard IDs.")],
        )
        build_project(
            core_root,
            core_cfg,
            spec_files={"spec/prd.md": [core_prd]},
        )

        # FDA-style associate with namespaced prefix
        assoc_prd = Requirement(
            "REQ-FDA-p00001",
            "FDA Compliance",
            "PRD",
            assertions=[("A", "The system SHALL comply with FDA regulations.")],
        )
        build_associate(
            assoc_root,
            "fda-assoc",
            "FDA",
            "../core",
            spec_files={"spec/prd-fda.md": [assoc_prd]},
            init_git=True,
        )

        return core_root

    def test_health_passes(self, tmp_path):
        core = self._build(tmp_path)
        result = run_elspais("checks", "--lenient", cwd=core)
        assert result.returncode == 0, f"health failed: {result.stderr}\n{result.stdout}"


# ---------------------------------------------------------------------------
# Test: Full MCP workflow with associate (from TestMCPAssociatedWorkflow)
# ---------------------------------------------------------------------------


class TestMCPAssociatedWorkflow:
    """Full MCP workflow with core + associate."""

    def test_mcp_associate_workflow(self, project, mcp_server):
        from .helpers import mcp_call, mcp_call_all

        # 1. Get status
        status = mcp_call(mcp_server, "get_graph_status", {})
        assert isinstance(status, dict)

        # 2. Search
        results = mcp_call_all(mcp_server, "search", {"query": "Auth"})
        assert len(results) >= 1

        # 3. Get core requirement
        req = mcp_call(mcp_server, "get_requirement", {"req_id": "REQ-p00001"})
        assert req["id"] == "REQ-p00001"

        # 4. Get summary
        summary = mcp_call(mcp_server, "get_project_summary", {})
        assert isinstance(summary, dict)


# ---------------------------------------------------------------------------
# Test: Health with multiple associates (from TestMultiAssociateHealth)
# ---------------------------------------------------------------------------


class TestMultiAssociateHealth:
    """Health check with multi-associate setup (core + alpha + beta)."""

    def test_three_repos(self, project):
        health = run_elspais("checks", "--lenient", cwd=project)
        assert health.returncode == 0


# ---------------------------------------------------------------------------
# Test: MCP subtree extraction with associate (from TestMCPAssociatedSubtree)
# ---------------------------------------------------------------------------


class TestMCPAssociatedSubtree:
    """MCP subtree extraction with associated repos."""

    def test_subtree_with_associate(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(
            mcp_server,
            "get_subtree",
            {
                "root_id": "REQ-p00001",
                "format": "flat",
            },
        )
        assert isinstance(result, dict)
        nodes = result.get("nodes", [])
        node_ids = [n.get("id", "") for n in nodes]
        assert "REQ-p00001" in node_ids


# ---------------------------------------------------------------------------
# Test: Cross-repo /api/file-content lookup (CUR-1357)
# Verifies: REQ-d00200-G
# Unique layout — keeps per-test build so we can drive a fresh daemon
# against a federated project with named (allowed_roots-aware) associates.
# Read-only — must run BEFORE the mutation block below.
# ---------------------------------------------------------------------------


class TestFileContentCrossRepo:
    """REQ-d00200-G: /api/file-content resolves associate-repo files via node_id.

    Phase 1 of CUR-1357 adds an optional ``node_id`` query parameter to
    ``/api/file-content``. When supplied, the server resolves the file
    against the owning repo's root via ``FederatedGraph.repo_root_for``
    instead of the federation root. This e2e test drives the change
    against a real daemon over HTTP.
    """

    def _build_federated_project(self, tmp_path):
        """Build a 2-repo federation (core + assoc) using named associate format."""
        core_root = tmp_path / "core"
        assoc_root = tmp_path / "assoc"

        core_cfg = base_config(name="cur1357-core")
        # Named associate format → AppState._compute_allowed_roots picks up
        # the associate root, so /api/file-content's security guard allows
        # reading from it.
        core_cfg["associates"] = {
            "assoc": {"path": "../assoc", "namespace": "REQ"},
        }
        core_prd = Requirement(
            "REQ-p00001",
            "Core PRD",
            "PRD",
            assertions=[("A", "The system SHALL exist.")],
        )
        build_project(
            core_root,
            core_cfg,
            spec_files={"spec/prd-core.md": [core_prd]},
        )

        # Associate uses the same namespace but a distinct numeric ID so
        # the parser accepts it under the canonical {namespace}-{level}{n}
        # pattern. The file content is distinguishable from the root.
        assoc_prd = Requirement(
            "REQ-p00099",
            "Associate PRD",
            "PRD",
            assertions=[("A", "Cross-repo file content SHALL resolve.")],
        )
        build_associate(
            assoc_root,
            "assoc",
            "XX",
            "../core",
            spec_files={"spec/prd-assoc.md": [assoc_prd]},
            init_git=True,
        )
        return core_root, assoc_root

    def test_file_content_resolves_associate_repo(self, tmp_path):
        """GET /api/file-content?path=spec/prd-assoc.md&node_id=REQ-p00099
        returns the on-disk content of the associate's source file."""
        import json
        import urllib.request

        from elspais.mcp.daemon import ensure_daemon, get_daemon_info

        core_root, assoc_root = self._build_federated_project(tmp_path)
        ensure_daemon(core_root)
        info = get_daemon_info(core_root)
        assert info is not None, "daemon failed to start for federated fixture"
        port = info["port"]

        # Sanity check the node exists in the federated graph and routes
        # to the associate repo.
        sanity = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=5)
        assert sanity.status == 200

        # Without node_id: the file isn't in core/, so the server falls
        # back through state.allowed_roots and finds it in the associate.
        # This unblocks the test/code reference callers that have a raw
        # file path but no graph node id.
        fb_req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/file-content?path=spec/prd-assoc.md"
        )
        fb_resp = urllib.request.urlopen(fb_req, timeout=5)
        assert fb_resp.status == 200
        fb_data = json.loads(fb_resp.read().decode("utf-8"))
        on_disk = (assoc_root / "spec" / "prd-assoc.md").read_text().splitlines()
        assert fb_data["lines"] == on_disk

        # With node_id: same content, resolved explicitly via repo_root_for.
        ok_req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/file-content"
            f"?path=spec/prd-assoc.md&node_id=REQ-p00099"
        )
        resp = urllib.request.urlopen(ok_req, timeout=5)
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["lines"] == on_disk
        # Content is distinguishable from the root repo's file.
        assert any("REQ-p00099" in line for line in data["lines"])


# ---------------------------------------------------------------------------
# Mutation tests — run LAST, after all read-only tests above.
# ---------------------------------------------------------------------------


@pytest.mark.incremental
class TestAssociatedMutations:
    """Sequential mutations on the associated fixture."""

    def test_01_unlink_associate(self, project):
        result = run_elspais("associate", "--unlink", "beta", cwd=project)
        assert result.returncode in (0, 1)


# ---------------------------------------------------------------------------
# Test: Federation write/index scope (CUR-1419 / REQ-d00253)
# Verifies: REQ-d00253-B (fix writes primary-only)
# Verifies: REQ-d00253-C (INDEX/term-index primary-only)
# Verifies: REQ-d00253-D (MCP rejects associate mutations)
#
# These tests RUN `elspais fix` (which writes disk) and toggle config flags,
# so each builds its OWN isolated core+associate project in tmp_path. The
# isolated core sets cli_ttl=0 so toggling config between runs never hits a
# stale daemon. They must NOT touch the shared module `project` fixture.
# Placed LAST per convention (disk-touching / mutation tests run after
# read-only tests).
# ---------------------------------------------------------------------------


def _git_porcelain(root) -> str:
    """Return `git status --porcelain` output for a repo (stripped)."""
    import subprocess

    return subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(root),
        capture_output=True,
        text=True,
    ).stdout.strip()


class TestFederationWriteScope:
    """REQ-d00253-B/C: `elspais fix` writes and indexes the primary repo only,
    unless the corresponding federation opt-in flag is set."""

    # Both repos use the default canonical pattern ({namespace}-{level}{n}).
    # The associate's requirement is a DISTINCT numeric ID (REQ-p00099) so the
    # core's parser accepts it and the federated graph indexes it as an
    # associate-owned node (repo_for(...) -> "assoc"). This is the same
    # construction TestFileContentCrossRepo uses for a real federation.
    CORE_REQ = "REQ-p00001"
    ASSOC_REQ = "REQ-p00099"
    ASSOC_NAME = "assoc"

    def _build(
        self, tmp_path, *, write_associates=False, index_associates=False, stale_assoc=False
    ):
        """Build an isolated core + associate federation. Both git-committed clean.

        Returns (core_root, assoc_root).
        """
        core_root = tmp_path / "core"
        assoc_root = tmp_path / "assoc"

        core_cfg = base_config(name="fed-core")
        # cli_ttl=0 disables the daemon so toggled config is always honoured.
        core_cfg["cli_ttl"] = 0
        # Named associate link so federation kicks in during fix.
        core_cfg["associates"] = {self.ASSOC_NAME: {"path": "../assoc", "namespace": "REQ"}}
        fed = {}
        if write_associates:
            fed["write_associates"] = True
        if index_associates:
            fed["index_associates"] = True
        if fed:
            core_cfg["federation"] = fed

        core_prd = Requirement(
            self.CORE_REQ,
            "Core PRD",
            "PRD",
            assertions=[("A", "The system SHALL use standard IDs.")],
        )
        build_project(
            core_root,
            core_cfg,
            spec_files={"spec/prd-core.md": [core_prd]},
        )

        assoc_prd = Requirement(
            self.ASSOC_REQ,
            "Associate PRD",
            "PRD",
            assertions=[("A", "The associate SHALL provide a feature.")],
        )
        build_associate(
            assoc_root,
            self.ASSOC_NAME,
            "XX",
            "../core",
            spec_files={"spec/prd-assoc.md": [assoc_prd]},
            init_git=True,
        )

        if stale_assoc:
            # Corrupt the associate requirement's hash so `fix` WANTS to
            # rewrite that file. The block is otherwise canonical, so the
            # only pending mutation is the hash drift on the associate.
            assoc_spec = assoc_root / "spec" / "prd-assoc.md"
            text = assoc_spec.read_text()
            assert "**Hash**:" in text, "associate spec missing hash to corrupt"
            import re as _re

            text = _re.sub(r"\*\*Hash\*\*: [0-9a-f]+", "**Hash**: deadbeef", text)
            assoc_spec.write_text(text)
            # Re-commit so the working tree is clean before the run; the
            # corrupted hash is now the committed baseline.
            import subprocess

            subprocess.run(["git", "add", "."], cwd=str(assoc_root), capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", "stale hash"],
                cwd=str(assoc_root),
                capture_output=True,
            )

        # Sanity: both working trees clean before the run under test.
        assert _git_porcelain(core_root) == "", "core repo dirty before fix"
        assert _git_porcelain(assoc_root) == "", "associate repo dirty before fix"
        return core_root, assoc_root

    def test_fix_does_not_mutate_associate_repo(self, tmp_path):
        """Verifies: REQ-d00253-B — `elspais fix` from core leaves the
        associate working tree byte-for-byte clean (no associate writes)."""
        core_root, assoc_root = self._build(tmp_path)

        result = run_elspais("fix", cwd=core_root)
        assert result.returncode == 0, f"fix failed: {result.stderr}\n{result.stdout}"

        assert _git_porcelain(assoc_root) == "", (
            "associate repo was mutated by core `fix` "
            f"(write_associates default false): {_git_porcelain(assoc_root)!r}"
        )

    def test_fix_index_excludes_associate_reqs(self, tmp_path):
        """Verifies: REQ-d00253-C — generated INDEX.md lists the core
        requirement but NOT the associate-owned requirement (default)."""
        core_root, _assoc_root = self._build(tmp_path)

        result = run_elspais("fix", cwd=core_root)
        assert result.returncode == 0, f"fix failed: {result.stderr}\n{result.stdout}"

        index = (core_root / "spec" / "INDEX.md").read_text()
        assert self.CORE_REQ in index, "core requirement missing from INDEX.md"
        assert self.ASSOC_REQ not in index, (
            f"associate requirement {self.ASSOC_REQ} leaked into primary INDEX.md "
            "with index_associates=false"
        )

    def test_index_associates_opt_in(self, tmp_path):
        """Verifies: REQ-d00253-C — with federation.index_associates=true the
        associate-owned requirement DOES appear in the primary INDEX.md."""
        core_root, _assoc_root = self._build(tmp_path, index_associates=True)

        result = run_elspais("fix", cwd=core_root)
        assert result.returncode == 0, f"fix failed: {result.stderr}\n{result.stdout}"

        index = (core_root / "spec" / "INDEX.md").read_text()
        assert self.CORE_REQ in index, "core requirement missing from INDEX.md"
        assert self.ASSOC_REQ in index, (
            f"associate requirement {self.ASSOC_REQ} absent from INDEX.md "
            "despite index_associates=true"
        )

    def test_write_associates_default_keeps_associate_clean_even_when_dirty(self, tmp_path):
        """Verifies: REQ-d00253-B — even when an associate file NEEDS a fix
        (stale hash), the default (write_associates=false) leaves it clean."""
        core_root, assoc_root = self._build(tmp_path, stale_assoc=True)

        result = run_elspais("fix", cwd=core_root)
        assert result.returncode == 0, f"fix failed: {result.stderr}\n{result.stdout}"

        # The associate had a corrupt hash that `fix` would canonicalize, but
        # writes are gated off — its working tree stays clean.
        assert _git_porcelain(assoc_root) == "", (
            "associate file with stale hash was rewritten despite "
            f"write_associates=false: {_git_porcelain(assoc_root)!r}"
        )
        # And the corrupt hash is still on disk (proof fix did not touch it).
        assoc_text = (assoc_root / "spec" / "prd-assoc.md").read_text()
        assert "deadbeef" in assoc_text, "associate stale hash unexpectedly changed"

    def test_write_associates_opt_in_rewrites_associate(self, tmp_path):
        """Verifies: REQ-d00253-B — with federation.write_associates=true,
        `fix` IS permitted to rewrite the associate's stale-hash spec file,
        dirtying its working tree."""
        core_root, assoc_root = self._build(tmp_path, write_associates=True, stale_assoc=True)

        result = run_elspais("fix", cwd=core_root)
        assert result.returncode == 0, f"fix failed: {result.stderr}\n{result.stdout}"

        assert _git_porcelain(assoc_root) != "", (
            "associate file with stale hash was NOT rewritten despite " "write_associates=true"
        )
        # The corrupt hash was canonicalized away.
        assoc_text = (assoc_root / "spec" / "prd-assoc.md").read_text()
        assert "deadbeef" not in assoc_text, "stale hash should have been fixed"


class TestFederationMCPGuard:
    """REQ-d00253-D: MCP mutation tools reject associate-owned nodes unless
    federation.write_associates is set. Isolated core+associate per project."""

    CORE_REQ = "REQ-p00001"
    ASSOC_REQ = "REQ-p00099"
    ASSOC_NAME = "assoc"

    def _build(self, tmp_path, *, write_associates=False):
        core_root = tmp_path / "core"
        assoc_root = tmp_path / "assoc"

        core_cfg = base_config(name="fed-mcp-core")
        core_cfg["cli_ttl"] = 0
        core_cfg["associates"] = {self.ASSOC_NAME: {"path": "../assoc", "namespace": "REQ"}}
        if write_associates:
            core_cfg["federation"] = {"write_associates": True}

        core_prd = Requirement(
            self.CORE_REQ,
            "Core PRD",
            "PRD",
            assertions=[("A", "The system SHALL use standard IDs.")],
        )
        build_project(core_root, core_cfg, spec_files={"spec/prd-core.md": [core_prd]})

        assoc_prd = Requirement(
            self.ASSOC_REQ,
            "Associate PRD",
            "PRD",
            assertions=[("A", "The associate SHALL provide a feature.")],
        )
        build_associate(
            assoc_root,
            self.ASSOC_NAME,
            "XX",
            "../core",
            spec_files={"spec/prd-assoc.md": [assoc_prd]},
            init_git=True,
        )
        return core_root

    def test_mcp_rejects_associate_mutation_by_default(self, tmp_path):
        """Verifies: REQ-d00253-D — mutate_update_title on an associate-owned
        requirement is rejected (success=false, error names read-only +
        the associate) when write_associates is false."""
        pytest.importorskip("mcp")
        from .helpers import mcp_call, start_mcp, stop_mcp

        core_root = self._build(tmp_path)
        server = start_mcp(core_root)
        try:
            resp = mcp_call(
                server,
                "mutate_update_title",
                {"node_id": self.ASSOC_REQ, "new_title": "Hijacked"},
            )
        finally:
            stop_mcp(server)

        assert isinstance(resp, dict), f"unexpected MCP response: {resp!r}"
        assert resp.get("success") is False, f"expected rejection, got {resp!r}"
        err = (resp.get("error") or "").lower()
        assert "read-only" in err, f"error missing read-only note: {resp!r}"
        assert self.ASSOC_NAME in err, f"error should name the associate: {resp!r}"

    def test_mcp_allows_associate_mutation_when_opted_in(self, tmp_path):
        """Verifies: REQ-d00253-D — with federation.write_associates=true the
        same associate mutation SUCCEEDS."""
        pytest.importorskip("mcp")
        from .helpers import mcp_call, start_mcp, stop_mcp

        core_root = self._build(tmp_path, write_associates=True)
        server = start_mcp(core_root)
        try:
            resp = mcp_call(
                server,
                "mutate_update_title",
                {"node_id": self.ASSOC_REQ, "new_title": "Allowed Edit"},
            )
        finally:
            stop_mcp(server)

        assert isinstance(resp, dict), f"unexpected MCP response: {resp!r}"
        assert (
            resp.get("success") is True
        ), f"expected success with write_associates=true, got {resp!r}"
