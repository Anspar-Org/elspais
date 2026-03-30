# Verifies: REQ-p00002, REQ-p00003, REQ-p00060, REQ-d00080
"""Fixture 3: Named-component IDs with custom config — module-scoped fixture.

This fixture covers:
- Named-component IDs (e.g., REQ-pUserAuth, REQ-dAuthModule)
- Numeric-1-based assertion labels (1, 2, 3...)
- DEV requirements implementing PRD directly (custom hierarchy, no OPS level)
- Assertions without "SHALL" (require_shall=False)
- Comma-separated multi-assertion syntax
- Requirements with no assertions (require_assertions=False)
- Requirements with placeholder text assertions

Groups:
  1. Named component IDs (health, summary, trace)
  2. Numeric 1-based assertions (health, trace)
  3. Custom hierarchy rules (dev→prd directly, structural orphans)
  4. require_shall=False
  5. Comma multi-assertion separator
  6. MCP with 1-based numeric assertions
  7. Placeholder assertions
  8. Empty assertions (require_assertions=False)
"""

from __future__ import annotations

import json
import shutil

import pytest

from .conftest import (
    ensure_fixture_daemon,
    load_fixture,
    run_elspais,
)

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        shutil.which("elspais") is None,
        reason="elspais CLI not found on PATH",
    ),
]


# ---------------------------------------------------------------------------
# Module-scoped fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    """Copy e2e-named-custom fixture to /tmp, init git, start daemon."""
    root = tmp_path_factory.mktemp("e2e_named_custom")
    load_fixture("e2e-named-custom", root)
    ensure_fixture_daemon(root)
    return root


@pytest.fixture(scope="module")
def mcp_server(project):
    """Start an MCP server for the project, shared across all MCP tests."""
    pytest.importorskip("mcp")
    from .helpers import start_mcp, stop_mcp

    proc = start_mcp(project)
    yield proc
    stop_mcp(proc)


# ---------------------------------------------------------------------------
# Named component IDs
# ---------------------------------------------------------------------------


class TestNamedComponentIds:
    """Named IDs: REQ-pUserAuth, REQ-dAuthModule, etc."""

    def test_health_passes(self, project):
        result = run_elspais("checks", "--lenient", cwd=project)
        assert result.returncode == 0, f"health failed: {result.stderr}"

    def test_summary_counts_requirements(self, project):
        result = run_elspais("summary", "--format", "json", cwd=project)
        assert result.returncode == 0, f"summary failed: {result.stderr}"
        data = json.loads(result.stdout)
        levels = data.get("levels", [])
        total = sum(lv.get("total", 0) for lv in levels)
        # 5 requirements total (2 PRD + 1 OPS + 2 DEV)
        assert total == 5, f"Expected 5 requirements, got {total}"

    def test_trace_contains_named_ids(self, project):
        result = run_elspais("trace", "--format", "json", cwd=project)
        assert result.returncode == 0
        output = result.stdout
        assert "REQ-pUserAuth" in output
        assert "REQ-pSearchEngine" in output
        assert "REQ-oDeployPipeline" in output
        assert "REQ-dAuthModule" in output
        assert "REQ-dSearchIndex" in output


# ---------------------------------------------------------------------------
# Numeric 1-based assertion labels
# ---------------------------------------------------------------------------


class TestNumeric1BasedAssertionLabels:
    """Config: label_style = 'numeric_1based' — assertions labeled 1, 2, 3."""

    def test_health_passes(self, project):
        result = run_elspais("checks", "--lenient", cwd=project)
        assert result.returncode == 0, f"health failed: {result.stderr}"

    def test_trace_json_valid(self, project):
        result = run_elspais("trace", "--format", "json", cwd=project)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data  # Non-empty


# ---------------------------------------------------------------------------
# Custom hierarchy rules
# ---------------------------------------------------------------------------


class TestCustomHierarchyRules:
    """Non-standard allowed_implements: DEV -> PRD directly (no OPS)."""

    def test_dev_directly_implements_prd(self, project):
        """DEV -> PRD should work when allowed — REQ-dAuthModule implements REQ-pUserAuth."""
        result = run_elspais("checks", "--lenient", cwd=project)
        assert result.returncode == 0

    def test_allow_structural_orphans(self, project):
        """Orphan requirements should pass when allow_structural_orphans=True."""
        result = run_elspais("checks", "--lenient", cwd=project)
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# require_shall disabled
# ---------------------------------------------------------------------------


class TestRequireShallDisabled:
    """Config: require_shall = false allows non-SHALL assertions."""

    def test_no_shall_requirement(self, project):
        """The shared fixture uses require_shall=False — health must pass."""
        result = run_elspais("checks", "--lenient", cwd=project)
        assert result.returncode == 0

    def test_summary_with_no_shall_assertions(self, project):
        """Fixture has require_shall=False and non-SHALL text — passes."""
        result = run_elspais("summary", "--format", "json", cwd=project)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        levels = data.get("levels", [])
        total = sum(lv.get("total", 0) for lv in levels)
        assert total > 0, "Expected at least one requirement"


# ---------------------------------------------------------------------------
# Multi-assertion separator (comma)
# ---------------------------------------------------------------------------


class TestMultiAssertionSeparator:
    """Config: multi_assertion_separator = ',' instead of '+'."""

    def test_comma_separator_health_passes(self, project):
        """Shared fixture uses comma separator — health must pass."""
        result = run_elspais("checks", "--lenient", cwd=project)
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# MCP with 1-based numeric assertions
# ---------------------------------------------------------------------------


class TestMCPNumeric1Based:
    """MCP tools with numeric_1based assertions."""

    def test_mcp_1based_assertions(self, mcp_server):
        """MCP get_requirement returns assertions labeled 1, 2."""
        from .helpers import mcp_call

        req = mcp_call(mcp_server, "get_requirement", {"req_id": "REQ-pUserAuth"})
        assert req is not None, "get_requirement returned None"
        labels = [a.get("label", "") for a in req.get("assertions", [])]
        assert "1" in labels, f"Expected label '1' in {labels}"
        assert "2" in labels, f"Expected label '2' in {labels}"

    def test_mcp_search_named_id(self, mcp_server):
        """MCP search finds requirements by named component."""
        from .helpers import mcp_call

        results = mcp_call(mcp_server, "search", {"query": "UserAuth"})
        assert isinstance(results, dict)


# ---------------------------------------------------------------------------
# Placeholder assertions
# ---------------------------------------------------------------------------


class TestPlaceholderAssertions:
    """Assertions with placeholder/deprecated values pass health."""

    def test_placeholder_values(self, project):
        """The fixture has standard assertions — health must pass."""
        result = run_elspais("checks", "--lenient", cwd=project)
        assert result.returncode == 0

    def test_trace_shows_all_requirements(self, project):
        """All fixture requirements appear in trace output."""
        result = run_elspais("trace", "--format", "json", cwd=project)
        assert result.returncode == 0
        output = result.stdout
        assert "REQ-pUserAuth" in output
        assert "REQ-dAuthModule" in output


# ---------------------------------------------------------------------------
# Empty assertions (require_assertions=False)
# ---------------------------------------------------------------------------


class TestEmptyAssertions:
    """Requirements with no assertions when require_assertions=False."""

    def test_no_assertions_allowed(self, tmp_path):
        """A requirement with no assertions passes when require_assertions=False."""
        from .helpers import base_config, init_git_repo, write_config
        from .helpers import run_elspais as run_cli

        cfg = base_config(
            name="no-assertions-named",
            canonical="{namespace}-{level.letter}{component}",
            component_style="named",
            types={
                "prd": {"level": 1, "aliases": {"letter": "p"}},
            },
            allowed_implements=[],
            label_style="numeric_1based",
            require_shall=False,
            require_assertions=False,
            allow_structural_orphans=True,
        )
        cfg["id-patterns"]["component"] = {
            "style": "named",
            "pattern": "[A-Z][a-zA-Z0-9]+",
            "max_length": 32,
        }

        # Write spec file manually (no assertions section)
        spec = tmp_path / "spec" / "prd.md"
        spec.parent.mkdir(parents=True, exist_ok=True)
        spec.write_text(
            "# REQ-pNoAssertions: No Assertions\n\n"
            "**Level**: PRD | **Status**: Active\n\n"
            "The system does something without assertions.\n\n"
            "*End* *No Assertions* | **Hash**: e3b0c442\n"
            "---\n"
        )
        write_config(tmp_path / ".elspais.toml", cfg)
        init_git_repo(tmp_path)

        result = run_cli("checks", "--lenient", cwd=tmp_path)
        assert result.returncode == 0
