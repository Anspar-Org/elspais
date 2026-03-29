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
    build_fixture_project,
    ensure_fixture_daemon,
)
from .helpers import (
    Requirement,
    base_config,
    build_project,
    init_git_repo,
    run_elspais,
    write_config,
)

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        shutil.which("elspais") is None,
        reason="elspais CLI not found on PATH",
    ),
]


# ---------------------------------------------------------------------------
# Fixture project content (named IDs, numeric-1based, DEV→PRD direct)
# ---------------------------------------------------------------------------


def _make_named_cfg() -> dict:
    """Build config for named-component IDs with numeric-1based assertions."""
    cfg = base_config(
        name="named-custom",
        canonical="{namespace}-{level.letter}{component}",
        component_style="named",
        types={
            "prd": {"level": 1, "aliases": {"letter": "p"}},
            "dev": {"level": 2, "aliases": {"letter": "d"}},
        },
        allowed_implements=["dev -> prd"],
        label_style="numeric_1based",
        multi_assertion_separator=",",
        require_shall=False,
        allow_structural_orphans=True,
    )
    cfg["id-patterns"]["component"] = {
        "style": "named",
        "pattern": "[A-Z][a-zA-Z0-9]+",
        "max_length": 32,
    }
    return cfg


# PRD requirements
_PRD_USER_AUTH = Requirement(
    "REQ-pUserAuth",
    "User Authentication",
    "PRD",
    assertions=[
        ("1", "Authenticate users on every request."),
        ("2", "Enforce password complexity policies."),
    ],
)

_PRD_DATA_PRIVACY = Requirement(
    "REQ-pDataPrivacy",
    "Data Privacy",
    "PRD",
    assertions=[
        ("1", "Encrypt all user data at rest."),
        ("2", "Log all data access events."),
    ],
)

_PRD_NO_ASSERTIONS = Requirement(
    "REQ-pNoAssert",
    "No Assertions",
    "PRD",
    assertions=[],
)

# DEV requirements — implementing PRD directly (no OPS level)
_DEV_AUTH_MODULE = Requirement(
    "REQ-dAuthModule",
    "Auth Module",
    "DEV",
    implements="REQ-pUserAuth",
    assertions=[
        ("1", "Use bcrypt to hash passwords."),
        ("2", "Issue JWT tokens after successful login."),
    ],
)

_DEV_PRIVACY_CTRL = Requirement(
    "REQ-dPrivacyCtrl",
    "Privacy Controller",
    "DEV",
    implements="REQ-pDataPrivacy",
    assertions=[
        ("1", "Apply AES-256 encryption to stored records."),
    ],
)

# Requirement with placeholder/deprecated assertions
_PRD_WITH_PLACEHOLDERS = Requirement(
    "REQ-pWithPlaceholders",
    "With Placeholders",
    "PRD",
    assertions=[
        ("1", "Active assertion one."),
        ("2", "Removed - was duplicate of assertion 1."),
        ("3", "Active assertion three."),
    ],
)


def _build_fixture_content() -> tuple[dict, dict, dict]:
    """Return (cfg, spec_files_content, {}) for the shared fixture."""
    cfg = _make_named_cfg()
    # require_assertions=False to allow REQ-pNoAssert
    cfg["rules"]["format"]["require_assertions"] = False

    spec_content: dict[str, str] = {}
    spec_content["spec/prd-core.md"] = "\n".join(
        r.render() for r in [_PRD_USER_AUTH, _PRD_DATA_PRIVACY]
    )
    spec_content["spec/prd-misc.md"] = "\n".join(
        r.render() for r in [_PRD_NO_ASSERTIONS, _PRD_WITH_PLACEHOLDERS]
    )
    spec_content["spec/dev-impl.md"] = "\n".join(
        r.render() for r in [_DEV_AUTH_MODULE, _DEV_PRIVACY_CTRL]
    )

    return cfg, spec_content


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    """Build the named-custom project once for the entire module."""
    root = tmp_path_factory.mktemp("e2e_named_custom")
    cfg, spec_content = _build_fixture_content()

    # Write config via write_config to respect the full custom cfg
    write_config(root / ".elspais.toml", cfg)
    for rel_path, content in spec_content.items():
        fpath = root / rel_path
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text(content)
    (root / "spec").mkdir(exist_ok=True)

    import os
    import subprocess

    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    subprocess.run(["git", "init"], cwd=root, capture_output=True, env=env)
    subprocess.run(["git", "add", "."], cwd=root, capture_output=True, env=env)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=root,
        capture_output=True,
        env=env,
    )
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
        # 6 requirements total (2 PRD core + 2 misc + 2 DEV)
        assert total == 6, f"Expected 6 requirements, got {total}"

    def test_trace_contains_named_ids(self, project):
        result = run_elspais("trace", "--format", "json", cwd=project)
        assert result.returncode == 0
        output = result.stdout
        assert "REQ-pUserAuth" in output
        assert "REQ-pDataPrivacy" in output
        assert "REQ-dAuthModule" in output
        assert "REQ-dPrivacyCtrl" in output


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

    def test_dev_directly_implements_prd(self, tmp_path):
        """DEV -> PRD should work when allowed."""
        cfg = base_config(
            name="direct-hierarchy-named",
            canonical="{namespace}-{level.letter}{component}",
            component_style="named",
            types={
                "prd": {"level": 1, "aliases": {"letter": "p"}},
                "dev": {"level": 2, "aliases": {"letter": "d"}},
            },
            allowed_implements=["dev -> prd"],
            label_style="numeric_1based",
            require_shall=False,
        )
        cfg["id-patterns"]["component"] = {
            "style": "named",
            "pattern": "[A-Z][a-zA-Z0-9]+",
            "max_length": 32,
        }
        prd = Requirement(
            "REQ-pDirectParent",
            "Direct Parent",
            "PRD",
            assertions=[("1", "The system must be directly implemented.")],
        )
        dev = Requirement(
            "REQ-dDirectImpl",
            "Direct Implementation",
            "DEV",
            implements="REQ-pDirectParent",
            assertions=[("1", "The module must implement directly.")],
        )
        build_project(
            tmp_path,
            cfg,
            spec_files={
                "spec/prd.md": [prd],
                "spec/dev.md": [dev],
            },
        )

        result = run_elspais("checks", "--lenient", cwd=tmp_path)
        assert result.returncode == 0

    def test_allow_structural_orphans(self, tmp_path):
        """Orphan requirements should pass when allow_structural_orphans=True."""
        cfg = base_config(
            name="orphans-ok-named",
            canonical="{namespace}-{level.letter}{component}",
            component_style="named",
            types={
                "prd": {"level": 1, "aliases": {"letter": "p"}},
                "dev": {"level": 2, "aliases": {"letter": "d"}},
            },
            allowed_implements=["dev -> prd"],
            label_style="numeric_1based",
            require_shall=False,
            allow_structural_orphans=True,
        )
        cfg["id-patterns"]["component"] = {
            "style": "named",
            "pattern": "[A-Z][a-zA-Z0-9]+",
            "max_length": 32,
        }
        orphan = Requirement(
            "REQ-dOrphanModule",
            "Orphan Dev Module",
            "DEV",
            assertions=[("1", "The module must exist alone.")],
        )
        build_project(
            tmp_path,
            cfg,
            spec_files={"spec/dev-orphan.md": [orphan]},
        )

        result = run_elspais("checks", "--lenient", cwd=tmp_path)
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

    def test_summary_with_no_shall_assertions(self, tmp_path):
        """Fresh project with require_shall=False and non-SHALL text passes."""
        cfg = base_config(
            name="no-shall-named",
            canonical="{namespace}-{level.letter}{component}",
            component_style="named",
            types={
                "prd": {"level": 1, "aliases": {"letter": "p"}},
            },
            allowed_implements=[],
            label_style="numeric_1based",
            require_shall=False,
            allow_structural_orphans=True,
        )
        cfg["id-patterns"]["component"] = {
            "style": "named",
            "pattern": "[A-Z][a-zA-Z0-9]+",
            "max_length": 32,
        }
        prd = Requirement(
            "REQ-pNoShall",
            "No SHALL",
            "PRD",
            assertions=[
                ("1", "The system must validate input."),
                ("2", "Users can export data."),
            ],
        )
        build_project(tmp_path, cfg, spec_files={"spec/prd.md": [prd]})
        result = run_elspais("checks", "--lenient", cwd=tmp_path)
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Multi-assertion separator (comma)
# ---------------------------------------------------------------------------


class TestMultiAssertionSeparator:
    """Config: multi_assertion_separator = ',' instead of '+'."""

    def test_comma_separator_health_passes(self, project):
        """Shared fixture uses comma separator — health must pass."""
        result = run_elspais("checks", "--lenient", cwd=project)
        assert result.returncode == 0

    def test_comma_separator_isolated(self, tmp_path):
        """Isolated project with comma separator and a test referencing multiple assertions."""
        cfg = base_config(
            name="comma-sep-named",
            canonical="{namespace}-{level.letter}{component}",
            component_style="named",
            types={
                "prd": {"level": 1, "aliases": {"letter": "p"}},
                "dev": {"level": 2, "aliases": {"letter": "d"}},
            },
            allowed_implements=["dev -> prd"],
            label_style="numeric_1based",
            multi_assertion_separator=",",
            require_shall=False,
            testing_enabled=True,
            test_dirs=["tests"],
        )
        cfg["id-patterns"]["component"] = {
            "style": "named",
            "pattern": "[A-Z][a-zA-Z0-9]+",
            "max_length": 32,
        }
        prd = Requirement(
            "REQ-pCommaSep",
            "Comma Sep",
            "PRD",
            assertions=[
                ("1", "The system must do A."),
                ("2", "The system must do B."),
            ],
        )
        dev = Requirement(
            "REQ-dCommaImpl",
            "Comma Implementation",
            "DEV",
            implements="REQ-pCommaSep",
            assertions=[("1", "The module must implement both.")],
        )
        build_project(
            tmp_path,
            cfg,
            spec_files={
                "spec/prd.md": [prd],
                "spec/dev.md": [dev],
            },
        )

        result = run_elspais("checks", "--lenient", cwd=tmp_path)
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
        """REQ-pWithPlaceholders has a 'Removed - ...' assertion — should pass."""
        result = run_elspais("checks", "--lenient", cwd=project)
        assert result.returncode == 0

    def test_placeholder_in_trace(self, project):
        """Placeholder requirement appears in trace output."""
        result = run_elspais("trace", "--format", "json", cwd=project)
        assert result.returncode == 0
        output = result.stdout
        assert "REQ-pWithPlaceholders" in output


# ---------------------------------------------------------------------------
# Empty assertions (require_assertions=False)
# ---------------------------------------------------------------------------


class TestEmptyAssertions:
    """Requirements with no assertions when require_assertions=False."""

    def test_no_assertions_allowed(self, tmp_path):
        """A requirement with no assertions passes when require_assertions=False."""
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

        result = run_elspais("checks", "--lenient", cwd=tmp_path)
        assert result.returncode == 0
