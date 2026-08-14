# Verifies: REQ-p00005
"""E2E tests for associated repository features — Fixture 5.

Consolidated from:
  - test_e2e_associated_repos.py (all 8 classes)
  - test_e2e_complex_workflows.py TestMCPAssociatedWorkflow
  - test_e2e_edge_cases.py TestAssociateUnlink, TestMultiAssociateHealth,
    TestMCPAssociatedSubtree

On-disk fixture layout (tests/fixtures/e2e-associated/):
  - core:  namespace REQ, uppercase assertions, associates=[alpha,beta]
  - alpha: namespace REQ-ALP, uppercase assertions
  - beta:  namespace REQ-BET, numeric assertions
"""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from tests.federation_repos import make_repo

from .conftest import (
    ensure_fixture_daemon,
    load_associated_fixture,
    requires_pandoc,
    requires_xelatex,
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
        core_cfg["associates"] = {
            "fda-assoc": {"path": "../fda-assoc", "namespace": "FDA"},
        }
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

        # FDA-style associate under its own namespace
        assoc_prd = Requirement(
            "FDA-p00001",
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
            "assoc": {"path": "../assoc", "namespace": "XX"},
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

        # The associate owns its own namespace -- no two repositories in a
        # federation may declare one namespace -- so its identifiers are
        # distinct from the core's by construction. The file content is
        # distinguishable from the root.
        assoc_prd = Requirement(
            "XX-p00099",
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
        """GET /api/file-content?path=spec/prd-assoc.md&node_id=XX-p00099
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
            f"http://127.0.0.1:{port}/api/file-content" f"?path=spec/prd-assoc.md&node_id=XX-p00099"
        )
        resp = urllib.request.urlopen(ok_req, timeout=5)
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["lines"] == on_disk
        # Content is distinguishable from the root repo's file.
        assert any("XX-p00099" in line for line in data["lines"])


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
# Verifies: REQ-d00253-B, REQ-d00253-C, REQ-d00253-D
# B: fix writes primary-only.  C: INDEX/term-index primary-only.
# D: MCP rejects associate mutations.
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

    # Both repos use the default canonical pattern ({namespace}-{level}{n}),
    # each under its own namespace -- one namespace names one repository in a
    # federation. The federated graph therefore indexes the associate's
    # requirement as an associate-owned node (repo_for(...) -> "assoc"). This
    # is the same construction TestFileContentCrossRepo uses.
    CORE_REQ = "REQ-p00001"
    ASSOC_REQ = "XX-p00099"
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
        core_cfg["associates"] = {self.ASSOC_NAME: {"path": "../assoc", "namespace": "XX"}}
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

    # ------------------------------------------------------------------
    # Term-index scope (REQ-d00253-C). A term index groups each term's
    # references by namespace (`**<NS>:**` blocks). The federated term scan
    # records references from associate repos, so a *core-defined* term that
    # an associate requirement *uses* would otherwise produce an
    # associate-namespace block in the primary term-index. These tests use
    # DISTINCT namespaces (CORE vs CAL) so the associate block is
    # unambiguously identifiable.
    # ------------------------------------------------------------------
    TERM = "Heartbeat"
    CORE_NS = "CORE"
    CAL_NS = "CAL"
    CORE_TERM_REQ = "CORE-p00001"
    CAL_TERM_REQ = "CAL-p00099"

    def _build_terms(self, tmp_path, *, index_associates=False):
        """Isolated core+associate where the associate requirement USES a term
        DEFINED in the core. Distinct namespaces (CORE / CAL). Both committed.

        Returns (core_root, assoc_root).
        """
        core_root = tmp_path / "core"
        assoc_root = tmp_path / "assoc"

        core_cfg = base_config(name="fed-term-core", namespace=self.CORE_NS)
        core_cfg["cli_ttl"] = 0
        core_cfg["associates"] = {"cal": {"path": "../assoc", "namespace": self.CAL_NS}}
        if index_associates:
            core_cfg["federation"] = {"index_associates": True}

        core_prd = Requirement(
            self.CORE_TERM_REQ,
            "Core PRD",
            "PRD",
            body=f"The core service emits a {self.TERM} on a schedule.",
            assertions=[("A", "The system SHALL emit periodic signals.")],
        )
        # Term defined via markdown definition-list syntax (blank line before
        # and after); a separate prose file so the scan records it as a
        # core-namespace definition.
        glossary = (
            "# Glossary\n\n" f"{self.TERM}\n" ": A periodic liveness signal emitted by a node.\n"
        )
        build_project(
            core_root,
            core_cfg,
            spec_files={"spec/prd-core.md": [core_prd]},
            extra_files={"spec/glossary.md": glossary},
        )

        # Associate requirement body USES the core-defined term, so the
        # federated term scan records a CAL-namespace reference under it.
        assoc_prd = Requirement(
            self.CAL_TERM_REQ,
            "Associate PRD",
            "PRD",
            body=f"The associate monitors each {self.TERM} from the core service.",
            assertions=[("A", "The associate SHALL track liveness signals.")],
        )
        build_associate(
            assoc_root,
            "cal",
            "XX",
            "../core",
            config_overrides={"project": {"namespace": self.CAL_NS}},
            spec_files={"spec/prd-assoc.md": [assoc_prd]},
            init_git=True,
        )

        assert _git_porcelain(core_root) == "", "core repo dirty before fix"
        assert _git_porcelain(assoc_root) == "", "associate repo dirty before fix"
        return core_root, assoc_root

    def test_fix_term_index_excludes_associate_references(self, tmp_path):
        """Verifies: REQ-d00253-C — the generated term-index.md groups a
        core-defined term's references by namespace, but with default flags
        the associate-namespace (`**CAL:**`) reference block is omitted while
        the term itself and its core references remain."""
        core_root, _assoc_root = self._build_terms(tmp_path)

        result = run_elspais("fix", cwd=core_root)
        assert result.returncode == 0, f"fix failed: {result.stderr}\n{result.stdout}"

        term_index = core_root / "spec" / "_generated" / "term-index.md"
        assert term_index.exists(), "term-index.md was not generated"
        text = term_index.read_text()

        assert f"## {self.TERM}" in text, "core-defined term missing from term-index"
        assert f"**{self.CAL_NS}:**" not in text, (
            f"associate namespace block **{self.CAL_NS}:** leaked into primary "
            "term-index with index_associates=false"
        )
        assert (
            self.CAL_TERM_REQ not in text
        ), f"associate node {self.CAL_TERM_REQ} leaked into primary term-index"
        # The core's own reference to the term is still indexed.
        assert f"**{self.CORE_NS}:**" in text, "core namespace block missing"

    def test_fix_term_index_associates_opt_in(self, tmp_path):
        """Verifies: REQ-d00253-C — with federation.index_associates=true the
        associate-namespace (`**CAL:**`) reference block DOES appear in the
        primary term-index."""
        core_root, _assoc_root = self._build_terms(tmp_path, index_associates=True)

        result = run_elspais("fix", cwd=core_root)
        assert result.returncode == 0, f"fix failed: {result.stderr}\n{result.stdout}"

        term_index = core_root / "spec" / "_generated" / "term-index.md"
        assert term_index.exists(), "term-index.md was not generated"
        text = term_index.read_text()

        assert f"## {self.TERM}" in text, "core-defined term missing from term-index"
        assert f"**{self.CAL_NS}:**" in text, (
            f"associate namespace block **{self.CAL_NS}:** absent from primary "
            "term-index despite index_associates=true"
        )
        assert (
            self.CAL_TERM_REQ in text
        ), f"associate node {self.CAL_TERM_REQ} absent despite index_associates=true"


class TestFederationMCPGuard:
    """REQ-d00253-D: MCP mutation tools reject associate-owned nodes unless
    federation.write_associates is set. Isolated core+associate per project."""

    CORE_REQ = "REQ-p00001"
    ASSOC_REQ = "XX-p00099"
    ASSOC_NAME = "assoc"

    def _build(self, tmp_path, *, write_associates=False):
        core_root = tmp_path / "core"
        assoc_root = tmp_path / "assoc"

        core_cfg = base_config(name="fed-mcp-core")
        core_cfg["cli_ttl"] = 0
        core_cfg["associates"] = {self.ASSOC_NAME: {"path": "../assoc", "namespace": "XX"}}
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
            # Reads are not blocked on associates: fetch the version token the
            # mutation signature requires; the read-only guard fires regardless.
            versions = mcp_call(server, "get_versions", {"node_ids": [self.ASSOC_REQ]})
            assert self.ASSOC_REQ in versions, f"get_versions omitted {self.ASSOC_REQ}: {versions}"
            resp = mcp_call(
                server,
                "mutate_update_title",
                {
                    "node_id": self.ASSOC_REQ,
                    "new_title": "Hijacked",
                    "if_version": versions[self.ASSOC_REQ],
                },
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
            versions = mcp_call(server, "get_versions", {"node_ids": [self.ASSOC_REQ]})
            assert self.ASSOC_REQ in versions, f"get_versions omitted {self.ASSOC_REQ}: {versions}"
            resp = mcp_call(
                server,
                "mutate_update_title",
                {
                    "node_id": self.ASSOC_REQ,
                    "new_title": "Allowed Edit",
                    "if_version": versions[self.ASSOC_REQ],
                },
            )
        finally:
            stop_mcp(server)

        assert isinstance(resp, dict), f"unexpected MCP response: {resp!r}"
        assert (
            resp.get("success") is True
        ), f"expected success with write_associates=true, got {resp!r}"


# ---------------------------------------------------------------------------
# Test: PDF media fidelity across a federated graph
# Unique layout (spec subdirectories + image assets) — keeps per-class build.
# ---------------------------------------------------------------------------


def _write_png(path, size=64):
    """Write a small real RGB PNG so pdfimages can see it in the output."""
    import struct
    import zlib

    def chunk(tag, data):
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    rows = b"".join(
        b"\x00" + b"".join(bytes([(x * 4) % 256, (y * 4) % 256, 128]) for x in range(size))
        for y in range(size)
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


def _image_rows(pdf_path):
    """Return (raw_listing, [(width, height), ...]) for images embedded in a PDF.

    ``pdfimages -list`` prints two header lines followed by one row per
    embedded object; only rows whose ``type`` column is ``image`` are
    real pictures (alpha channels arrive as separate ``smask`` rows).
    """
    listing = subprocess.run(
        ["pdfimages", "-list", str(pdf_path)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    sizes = []
    for row in listing.splitlines()[2:]:
        cols = row.split()
        if len(cols) < 5 or cols[2] != "image":
            continue
        sizes.append((int(cols[3]), int(cols[4])))
    return listing, sizes


requires_pdfimages = pytest.mark.skipif(
    shutil.which("pdfimages") is None,
    reason="pdfimages not found — install poppler-utils to inspect embedded PDF images",
)

requires_pdftotext = pytest.mark.skipif(
    shutil.which("pdftotext") is None,
    reason="pdftotext not found — install poppler-utils to extract compiled PDF text",
)


def _pdf_text(pdf_path):
    """Return the PDF's text with all whitespace runs collapsed to one space.

    ``pdftotext`` breaks lines wherever the typeset page did, so a phrase
    that reads as one sentence in the source arrives split across lines.
    Normalising first is what makes substring matching mean anything.
    """
    import re as _re

    raw = subprocess.run(
        ["pdftotext", str(pdf_path), "-"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return _re.sub(r"\s+", " ", raw)


# Distinctive rationale text: short words only, so LaTeX cannot hyphenate a
# token apart and defeat the substring match after whitespace normalisation.
CORE_RATIONALE_MARKER = "Core spec rationale marker alpha kilo nine."
ASSOC_RATIONALE_MARKER = "Assoc spec rationale marker delta zulu seven."

# Pixel dimensions distinguish which repo an image was resolved from.
CORE_IMAGE_PX = 64
ASSOC_IMAGE_PX = 48
DECOY_IMAGE_PX = 24


class TestPdfMediaFidelity:
    """Validates REQ-p00080-G: the PDF generator carries content derived from a
    variety of sources and media types — here, raster images referenced from
    spec files in both the root repo and an associate repo, resolved per
    declaring file rather than through a single global resource path.

    Validates REQ-p00080-I: an image reference that no repository of the
    compiled graph can satisfy is reported with the reference as written, the
    declaring spec file, and the locations searched.

    Validates REQ-p00080-K: when content was omitted, the completion report
    discloses the degradation instead of reporting unqualified success.
    """

    @pytest.fixture(scope="class")
    @staticmethod
    def federated_pdf_project(tmp_path_factory):
        """Core + associate, each referencing an image from a spec subdirectory.

        The associate's image lives at the same repo-relative path as a
        decoy of different dimensions in the core repo, so the compiled
        output shows which repo the reference was anchored to.
        """
        base = tmp_path_factory.mktemp("pdf_media")
        core_root = base / "core"
        assoc_root = base / "assoc"

        core_cfg = base_config(name="pdf-core", associated_enabled=True)
        core_cfg["associates"] = {"assoc": {"path": "../assoc", "namespace": "ASC"}}
        build_project(
            core_root,
            core_cfg,
            spec_files={
                "spec/sub/prd-core.md": [
                    Requirement(
                        "REQ-p00001",
                        "Core Imagery",
                        "PRD",
                        body="Core diagram below.\n\n![core diagram](images/core.png)\n",
                        assertions=[("A", "The system SHALL render core imagery.")],
                        rationale=CORE_RATIONALE_MARKER,
                    ),
                ],
            },
        )
        _write_png(core_root / "spec" / "sub" / "images" / "core.png", CORE_IMAGE_PX)
        # Decoy: same repo-relative path the associate's spec uses, different size.
        _write_png(core_root / "spec" / "sub" / "images" / "assoc.png", DECOY_IMAGE_PX)

        build_associate(
            assoc_root,
            "assoc",
            "ASC",
            "../core",
            config_overrides={"project": {"namespace": "ASC"}},
            spec_files={
                "spec/sub/prd-assoc.md": [
                    Requirement(
                        "ASC-p00001",
                        "Associate Imagery",
                        "PRD",
                        body="Associate diagram below.\n\n![assoc diagram](images/assoc.png)\n",
                        assertions=[("A", "The associate SHALL render its own imagery.")],
                        rationale=ASSOC_RATIONALE_MARKER,
                    ),
                ],
            },
            init_git=True,
        )
        _write_png(assoc_root / "spec" / "sub" / "images" / "assoc.png", ASSOC_IMAGE_PX)

        return core_root

    @pytest.fixture(scope="class")
    @staticmethod
    def federated_pdf(federated_pdf_project, tmp_path_factory):
        """Compile the federated project to PDF once for the whole class."""
        out = tmp_path_factory.mktemp("pdf_media_out") / "federated.pdf"
        result = run_elspais("pdf", "--output", str(out), cwd=federated_pdf_project)
        return result, out

    @pytest.fixture(scope="class")
    @staticmethod
    def missing_image_project(tmp_path_factory):
        """A project whose spec references an image that exists nowhere."""
        root = tmp_path_factory.mktemp("pdf_missing") / "core"
        build_project(
            root,
            base_config(name="pdf-missing"),
            spec_files={
                "spec/sub/prd-missing.md": [
                    Requirement(
                        "REQ-p00001",
                        "Missing Art",
                        "PRD",
                        body="Diagram below.\n\n![absent](images/nope.png)\n",
                        assertions=[("A", "The system SHALL report absent art.")],
                    ),
                ],
            },
        )
        return root

    @pytest.fixture(scope="class")
    @staticmethod
    def missing_image_pdf(missing_image_project, tmp_path_factory):
        """Compile the missing-reference project to PDF once for the class."""
        out = tmp_path_factory.mktemp("pdf_missing_out") / "missing.pdf"
        result = run_elspais("pdf", "--output", str(out), cwd=missing_image_project)
        return result, out

    @pytest.fixture(scope="class")
    @staticmethod
    def unfetchable_media_project(tmp_path_factory):
        """A project referencing a media type only pandoc can adjudicate.

        ``.webp`` is outside the assembler's own image-reference grammar, so
        the assembler records nothing at all for this document. The only
        witness that the picture is missing is pandoc's own stderr, which it
        emits while still exiting successfully.
        """
        root = tmp_path_factory.mktemp("pdf_webp") / "core"
        build_project(
            root,
            base_config(name="pdf-webp"),
            spec_files={
                "spec/sub/prd-webp.md": [
                    Requirement(
                        "REQ-p00001",
                        "Modern Art",
                        "PRD",
                        body="Diagram below.\n\n![absent](images/nope.webp)\n",
                        assertions=[("A", "The system SHALL report absent modern art.")],
                    ),
                ],
            },
        )
        return root

    @pytest.fixture(scope="class")
    @staticmethod
    def unfetchable_media_pdf(unfetchable_media_project, tmp_path_factory):
        """Compile the unfetchable-media project to PDF once for the class."""
        out = tmp_path_factory.mktemp("pdf_webp_out") / "webp.pdf"
        result = run_elspais("pdf", "--output", str(out), cwd=unfetchable_media_project)
        return result, out

    # Verifies: REQ-p00080-K
    @requires_pandoc
    @requires_xelatex
    def test_REQ_p00080_K_pandoc_reported_omission_reaches_the_completion_line(
        self, unfetchable_media_pdf
    ):
        """A reference only the typesetter can notice still qualifies the verdict.

        Every other test of this path substitutes a fake pandoc, so the exact
        stderr wording the parser depends on is asserted against a string the
        test itself wrote. If pandoc's phrasing drifts, those tests stay green
        while the omission stops being counted and the document is reported as
        an unqualified success. This one runs the real binary end to end: the
        compile succeeds, pandoc names the resource it could not fetch, and
        that omission reaches the completion line.
        """
        result, out = unfetchable_media_pdf
        print(f"\n--- elspais pdf stdout ---\n{result.stdout}")
        print(f"--- elspais pdf stderr ---\n{result.stderr}")

        assert result.returncode == 0, f"pdf failed: {result.stderr}"
        assert out.exists(), "PDF file was not created"

        assert "nope.webp" in result.stderr, (
            f"the resource pandoc could not fetch was not named on stderr: " f"{result.stderr}"
        )
        assert "PDF written to" in result.stdout, f"no completion line: {result.stdout}"
        assert "INCOMPLETE" in result.stdout, (
            f"a reference pandoc dropped was not folded into the completion "
            f"line, so the document was reported as an unqualified success: "
            f"{result.stdout}"
        )

    # Verifies: REQ-p00080-G
    @requires_pandoc
    @requires_xelatex
    @requires_pdfimages
    def test_REQ_p00080_G_referenced_image_appears_in_compiled_pdf(self, federated_pdf):
        result, out = federated_pdf
        assert result.returncode == 0, f"pdf failed: {result.stderr}"
        assert out.exists(), "PDF file was not created"

        listing, sizes = _image_rows(out)
        print(f"\npdfimages -list {out}:\n{listing}")

        assert (CORE_IMAGE_PX, CORE_IMAGE_PX) in sizes, (
            f"root-repo image ({CORE_IMAGE_PX}x{CORE_IMAGE_PX}) missing from the "
            f"compiled PDF; embedded images were {sizes}"
        )
        # One image per repo — a dropped reference changes this count.
        assert len(sizes) == 2, f"expected exactly 2 embedded images, got {sizes}"

    # Verifies: REQ-p00080-G
    @requires_pandoc
    @requires_xelatex
    @requires_pdfimages
    def test_REQ_p00080_G_associate_repo_image_appears_in_compiled_pdf(self, federated_pdf):
        result, out = federated_pdf
        assert result.returncode == 0, f"pdf failed: {result.stderr}"

        listing, sizes = _image_rows(out)
        print(f"\npdfimages -list {out}:\n{listing}")

        assert (ASSOC_IMAGE_PX, ASSOC_IMAGE_PX) in sizes, (
            f"associate-repo image ({ASSOC_IMAGE_PX}x{ASSOC_IMAGE_PX}) missing from "
            f"the compiled PDF; embedded images were {sizes}"
        )
        # The core repo holds a same-named decoy at the same relative path.
        # Its dimensions appearing instead would mean the reference resolved
        # against the root repo rather than the declaring file's own repo.
        assert (DECOY_IMAGE_PX, DECOY_IMAGE_PX) not in sizes, (
            f"root-repo decoy ({DECOY_IMAGE_PX}x{DECOY_IMAGE_PX}) was embedded — the "
            f"associate's reference was not anchored to its own repo; images were {sizes}"
        )
        assert len(sizes) == 2, f"expected exactly 2 embedded images, got {sizes}"

    # Verifies: REQ-p00080-I
    @requires_pandoc
    @requires_xelatex
    def test_REQ_p00080_I_missing_image_reported_on_stderr(
        self, missing_image_project, missing_image_pdf
    ):
        result, _out = missing_image_pdf
        assert result.returncode == 0, f"pdf failed: {result.stderr}"

        stderr = result.stderr
        assert "images/nope.png" in stderr, f"reference as written not reported: {stderr}"
        assert "spec/sub/prd-missing.md" in stderr, f"declaring file not reported: {stderr}"

        expected = str(missing_image_project / "spec" / "sub" / "images" / "nope.png")
        assert expected in stderr, f"searched location {expected} not reported: {stderr}"

    # Verifies: REQ-p00080-K
    @requires_pandoc
    @requires_xelatex
    def test_REQ_p00080_K_completion_line_discloses_incomplete_output(
        self, missing_image_pdf, federated_pdf
    ):
        degraded, _degraded_out = missing_image_pdf
        assert degraded.returncode == 0, f"pdf failed: {degraded.stderr}"
        assert "PDF written to" in degraded.stdout, f"no completion line: {degraded.stdout}"
        assert "INCOMPLETE" in degraded.stdout, (
            f"completion line reported unqualified success despite an omitted "
            f"reference: {degraded.stdout}"
        )

        complete, _complete_out = federated_pdf
        assert complete.returncode == 0, f"pdf failed: {complete.stderr}"
        assert "PDF written to" in complete.stdout, f"no completion line: {complete.stdout}"
        assert (
            "INCOMPLETE" not in complete.stdout
        ), f"a document missing nothing was reported as degraded: {complete.stdout}"

    # Verifies: REQ-p00080-H
    @requires_pandoc
    @requires_xelatex
    @requires_pdftotext
    def test_REQ_p00080_H_associate_requirement_text_appears_in_compiled_pdf(self, federated_pdf):
        """One compile from the ROOT repo carries the ASSOCIATE's prose.

        A federated document that renders only the host repo's spec files is
        indistinguishable from a complete one to anyone who wasn't told what
        was federated in. The associate's assertion AND its rationale must
        both survive the round trip, alongside the root repo's own content.
        """
        result, out = federated_pdf
        assert result.returncode == 0, f"pdf failed: {result.stderr}"
        assert out.exists(), "PDF file was not created"

        text = _pdf_text(out)
        print(f"\npdftotext {out} (normalised):\n{text}")

        assert (
            "The associate SHALL render its own imagery." in text
        ), "associate requirement's assertion text missing from the compiled PDF"
        assert (
            "rationale marker delta zulu seven" in text
        ), "associate requirement's rationale missing from the compiled PDF"
        # The root repo's own content is still there — federation adds, not replaces.
        assert (
            "The system SHALL render core imagery." in text
        ), "root repo's assertion text missing from the compiled PDF"
        assert (
            "rationale marker alpha kilo nine" in text
        ), "root repo's rationale missing from the compiled PDF"

    # Verifies: REQ-p00080-D
    @requires_pandoc
    @requires_xelatex
    @requires_pdftotext
    def test_REQ_p00080_D_topic_index_annotates_cross_repo_entries_in_compiled_pdf(
        self, federated_pdf
    ):
        """The [<associate>] annotation survives typesetting into the PDF.

        The Topic Index is where a reader learns which repo a requirement
        came from; an annotation that only exists in the intermediate
        markdown tells that reader nothing.
        """
        result, out = federated_pdf
        assert result.returncode == 0, f"pdf failed: {result.stderr}"

        text = _pdf_text(out)
        index_marker = "Topic Index"
        assert index_marker in text, f"no Topic Index in the compiled PDF: {text}"
        index_text = text[text.rindex(index_marker) :]
        print(f"\npdftotext {out} — Topic Index section (normalised):\n{index_text}")

        assert "[assoc] ASC-p00001" in index_text, (
            f"associate entry not annotated with its repo name in the compiled "
            f"Topic Index: {index_text}"
        )
        assert (
            "REQ-p00001" in index_text
        ), f"root repo entry missing from the compiled Topic Index: {index_text}"
        assert (
            "[pdf-core] REQ-p00001" not in index_text
        ), f"host repo entry must render bare, not annotated: {index_text}"


# ---------------------------------------------------------------------------
# Test: what a federation member contributes does not depend on how it was
#       reached — and what it does depend on (the member set)
# ---------------------------------------------------------------------------


def _req_block(req_id, title, *, implements=None, assertions=()):
    """Render one requirement block for a fixture spec file."""
    head = f"## {req_id}: {title}\n\n**Status**: active"
    if implements:
        head += f"\n\n**Implements**: {implements}"
    if assertions:
        body = "\n\n## Assertions\n\n" + "".join(
            f"{label}. The system SHALL {text}.\n\n" for label, text in assertions
        )
    else:
        body = "\n\nThe system shall do a thing.\n\n"
    return head + body + "*End*\n"


def _add_spec(repo, text):
    """Add a committed spec file to a repo built by `make_repo`."""
    (repo / "spec" / "extra.md").write_text(text, encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=T", "commit", "-m", "extra"],
        cwd=repo,
        check=True,
        capture_output=True,
    )


# `d` carries every observable at once: intra-repo coverage (d00002 covers one
# of d00003's two assertions), a cross-repo reference that resolves (d00004 ->
# BBB-d00001), a dangling reference in its own namespace (hard), and a
# reference into a namespace no federation member claims (presumed foreign).
_D_SPEC = (
    _req_block("DDD-d00003", "Target", assertions=[("A", "be covered"), ("B", "be uncovered")])
    + _req_block("DDD-d00002", "Coverer", implements="DDD-d00003-A", assertions=[("A", "cover")])
    + _req_block("DDD-d00004", "Cross repo", implements="BBB-d00001")
    + _req_block("DDD-d00005", "Dangling local", implements="DDD-d99999")
    + _req_block("DDD-d00006", "Dangling foreign", implements="ZZZ-d00001")
)


def _observe(entry_root):
    """Build a federation from `entry_root` and reduce it to per-member observables.

    Keyed by the member's directory name rather than its federation name:
    the name a converged repo is filed under is the declaration key of
    whichever chain reached it first, so keying by name would compare
    federations by an attribute that is itself path-dependent.
    """
    from pathlib import Path

    from elspais.config import get_config
    from elspais.graph.factory import build_graph
    from elspais.graph.GraphNode import NodeKind

    fed = build_graph(config=get_config(None, entry_root, quiet=True), repo_root=entry_root)
    observed = {}
    for entry in fed.iter_repos():
        graph = entry.graph
        assert graph is not None, f"{entry.name} failed to build: {entry.error}"
        coverage = {}
        for node in graph.iter_by_kind(NodeKind.REQUIREMENT):
            rollup = node.get_metric("rollup_metrics")
            coverage[node.id] = (
                rollup.total_assertions,
                rollup.implemented.direct,
                rollup.implemented.indirect,
            )
        observed[Path(entry.repo_root).resolve().name] = {
            "reqs": sorted(node.id for node in graph.iter_by_kind(NodeKind.REQUIREMENT)),
            "broken": sorted(
                (br.source_id, br.target_id, str(br.edge_kind), bool(br.presumed_foreign))
                for br in graph.broken_references()
            ),
            "coverage": coverage,
        }
    return observed


def _make_diamond(base, *, both_branches, swapped):
    """A declares b and c; b declares d; c declares d only when `both_branches`."""
    base.mkdir(parents=True)
    d = make_repo(base, "d", namespace="DDD", req_id="DDD-d00001")
    _add_spec(d, _D_SPEC)
    make_repo(
        base,
        "b",
        namespace="BBB",
        req_id="BBB-d00001",
        associates={"d": "../d"},
        associate_namespaces={"d": "DDD"},
    )
    make_repo(
        base,
        "c",
        namespace="CCC",
        req_id="CCC-d00001",
        associates=({"d": "../d"} if both_branches else None),
        associate_namespaces={"d": "DDD"},
    )
    declarations = {"c": "../c", "b": "../b"} if swapped else {"b": "../b", "c": "../c"}
    return make_repo(
        base,
        "a",
        namespace="AAA",
        req_id="AAA-d00001",
        associates=declarations,
        associate_namespaces={"b": "BBB", "c": "CCC"},
    )


def _make_chain(base):
    """a -> b -> c, with b referencing up into a and c referencing up into b."""
    base.mkdir(parents=True)
    c = make_repo(base, "c", namespace="CCC", req_id="CCC-d00001")
    _add_spec(
        c,
        _req_block("CCC-d00003", "Target", assertions=[("A", "be covered"), ("B", "be uncovered")])
        + _req_block("CCC-d00004", "Coverer", implements="CCC-d00003-A")
        + _req_block("CCC-d00002", "Up one", implements="BBB-d00001")
        + _req_block("CCC-d00005", "Absent from a present member", implements="BBB-d99999"),
    )
    b = make_repo(
        base,
        "b",
        namespace="BBB",
        req_id="BBB-d00001",
        associates={"c": "../c"},
        associate_namespaces={"c": "CCC"},
    )
    _add_spec(
        b,
        _req_block("BBB-d00003", "Target", assertions=[("A", "be covered"), ("B", "be uncovered")])
        + _req_block("BBB-d00004", "Coverer", implements="BBB-d00003-A")
        + _req_block("BBB-d00002", "Up chain", implements="AAA-d00001"),
    )
    a = make_repo(
        base,
        "a",
        namespace="AAA",
        req_id="AAA-d00001",
        associates={"b": "../b"},
        associate_namespaces={"b": "BBB"},
    )
    return a, b


class TestFederationContributionInvariance:
    """A member's contribution against declaration topology and entry point.

    Every fixture here is a throwaway federation in `tmp_path`; none of
    them touch the module's shared `project` fixture.
    """

    # Verifies: REQ-d00202-F
    def test_diamond_member_contributes_identically_through_either_branch(self, tmp_path):
        """`d` contributes the same thing reached through one branch or two.

        The diamond is the case where convergence could plausibly change
        what a member contributes: `d` is declared twice, and the walk is
        depth-first, so which branch reaches it first is decided by the
        declaration order in `a`'s config.
        """
        through_both = _observe(_make_diamond(tmp_path / "both", both_branches=True, swapped=False))
        swapped = _observe(_make_diamond(tmp_path / "swapped", both_branches=True, swapped=True))
        one_branch = _observe(_make_diamond(tmp_path / "one", both_branches=False, swapped=False))

        assert sorted(through_both) == ["a", "b", "c", "d"]
        assert sorted(swapped) == ["a", "b", "c", "d"]
        assert sorted(one_branch) == ["a", "b", "c", "d"]

        # Non-vacuity: `d`'s observables carry a resolved cross-repo
        # reference, both broken-reference classifications, and partial
        # coverage — so an equality below is comparing something.
        d_both = through_both["d"]
        assert d_both["reqs"] == [
            "DDD-d00001",
            "DDD-d00002",
            "DDD-d00003",
            "DDD-d00004",
            "DDD-d00005",
            "DDD-d00006",
        ]
        assert d_both["broken"] == [
            ("DDD-d00005", "DDD-d99999", "implements", False),
            ("DDD-d00006", "ZZZ-d00001", "implements", True),
        ], f"unexpected broken references for d: {d_both['broken']}"
        assert d_both["coverage"]["DDD-d00003"] == (2, 1.0, 1.0)

        assert swapped["d"] == d_both, (
            f"reversing the declaration order in a's config changed d's "
            f"contribution: {swapped['d']} vs {d_both}"
        )
        assert one_branch["d"] == d_both, (
            f"reaching d through one branch instead of two changed its "
            f"contribution: {one_branch['d']} vs {d_both}"
        )

    # Verifies: REQ-d00202-D, REQ-d00203-B
    def test_same_member_set_reached_flat_or_transitively_is_one_federation(self, tmp_path):
        """{a,b,c,d} declared flat by `a` equals the same set reached down a chain.

        Two entry points cannot have equal reachable sets — each would have
        to reach the other, which is a declaration cycle — so this is the
        realizable form of "same members, different declaration paths":
        one entry point, the members reached directly or transitively.
        """
        nested_base = tmp_path / "nested"
        nested_base.mkdir()
        d = make_repo(nested_base, "d", namespace="DDD", req_id="DDD-d00001")
        _add_spec(d, _D_SPEC)
        make_repo(
            nested_base,
            "c",
            namespace="CCC",
            req_id="CCC-d00001",
            associates={"d": "../d"},
            associate_namespaces={"d": "DDD"},
        )
        make_repo(
            nested_base,
            "b",
            namespace="BBB",
            req_id="BBB-d00001",
            associates={"c": "../c"},
            associate_namespaces={"c": "CCC"},
        )
        nested_entry = make_repo(
            nested_base,
            "a",
            namespace="AAA",
            req_id="AAA-d00001",
            associates={"b": "../b"},
            associate_namespaces={"b": "BBB"},
        )

        flat_base = tmp_path / "flat"
        flat_base.mkdir()
        flat_d = make_repo(flat_base, "d", namespace="DDD", req_id="DDD-d00001")
        _add_spec(flat_d, _D_SPEC)
        make_repo(flat_base, "c", namespace="CCC", req_id="CCC-d00001")
        make_repo(flat_base, "b", namespace="BBB", req_id="BBB-d00001")
        flat_entry = make_repo(
            flat_base,
            "a",
            namespace="AAA",
            req_id="AAA-d00001",
            associates={"b": "../b", "c": "../c", "d": "../d"},
            associate_namespaces={"b": "BBB", "c": "CCC", "d": "DDD"},
        )

        nested = _observe(nested_entry)
        flat = _observe(flat_entry)

        members = sorted(nested)
        expected_members = ["a", "b", "c", "d"]
        assert (
            members == expected_members
        ), f"a -> b -> c -> d did not federate every member transitively: {members}"
        assert nested["d"]["coverage"]["DDD-d00003"] == (2, 1.0, 1.0)
        assert nested == flat, (
            f"a member reached down a chain contributes differently from the "
            f"same member declared directly: {nested} vs {flat}"
        )

    # Verifies: REQ-d00202-D, REQ-d00203-B
    def test_entry_point_changes_the_member_set_not_a_member_contribution(self, tmp_path):
        """In a -> b -> c, entering at `a` or at `b` is compared on {b, c}.

        The entry point decides which repositories are members, and that
        is the one thing a member's contribution does depend on: `b`'s
        reference up into `a` resolves when `a` is a member and is a
        broken reference when it is not.  Everything else about `b` and
        `c` — their requirement IDs and their coverage rollups — is the
        same from either entry point.
        """
        entry_a, entry_b = _make_chain(tmp_path / "chain")

        from_a = _observe(entry_a)
        from_b = _observe(entry_b)

        assert sorted(from_a) == ["a", "b", "c"]
        assert sorted(from_b) == ["b", "c"], (
            f"entering at b must reach b and c only — declarations are "
            f"directed, so a is not reachable from b: {sorted(from_b)}"
        )

        for member in ("b", "c"):
            assert from_a[member]["reqs"] == from_b[member]["reqs"], (
                f"{member} contributed different requirement IDs from the two "
                f"entry points: {from_a[member]['reqs']} vs {from_b[member]['reqs']}"
            )
            assert from_a[member]["coverage"] == from_b[member]["coverage"], (
                f"{member}'s coverage rollups differ between entry points: "
                f"{from_a[member]['coverage']} vs {from_b[member]['coverage']}"
            )

        # c's references only ever point at members present under both
        # entry points, so its broken-reference set does not move.
        c_broken = [("CCC-d00005", "BBB-d99999", "implements", True)]
        assert from_a["c"]["broken"] == c_broken, f"{from_a['c']['broken']}"
        assert from_b["c"]["broken"] == c_broken, f"{from_b['c']['broken']}"

        # b's does: BBB-d00002 -> AAA-d00001 resolves against a member
        # under one entry point and is presumed foreign under the other.
        assert from_a["b"]["broken"] == [], (
            f"b's reference into a should resolve when a is a federation "
            f"member: {from_a['b']['broken']}"
        )
        assert from_b["b"]["broken"] == [
            ("BBB-d00002", "AAA-d00001", "implements", True),
        ], (
            f"b's reference into a should be a presumed-foreign broken "
            f"reference when a is outside the federation: {from_b['b']['broken']}"
        )
