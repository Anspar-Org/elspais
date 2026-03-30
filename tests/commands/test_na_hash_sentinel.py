# Verifies: REQ-p00004-A, REQ-p00002-C
"""Tests for N/A hash sentinel feature.

When a requirement has no hashable content (e.g., normalized-text mode
with no assertions), the system should use "N/A" as a sentinel hash
value rather than silently skipping validation.

Tests REQ-p00004-A: fix command handles N/A hash sentinel
Tests REQ-p00002-C: validate detects hash issues with N/A sentinel
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ─────────────────────────────────────────────────────────────────────────────

# Config uses normalized-text hash mode (default) so a requirement
# without assertions produces computed_hash=None.
CONFIG_TOML = """\
version = 3

[project]
name = "test"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]
"""

# Requirement WITH a stored hash but NO assertions.
# In normalized-text mode, compute_hash_for_node() returns None for this.
REQ_NO_ASSERTIONS_WITH_HASH = """\
# REQ-d00001: No Assertions Req

**Level**: DEV | **Status**: Draft | **Implements**: -

Some body text but no assertions section.

*End* *No Assertions Req* | **Hash**: deadbeef
---
"""

# Same requirement but with stored hash already set to "N/A".
REQ_NO_ASSERTIONS_NA_HASH = """\
# REQ-d00001: No Assertions Req

**Level**: DEV | **Status**: Draft | **Implements**: -

Some body text but no assertions section.

*End* *No Assertions Req* | **Hash**: N/A
---
"""

# Requirement with NO hash and NO assertions (mild warning case).
REQ_NO_ASSERTIONS_NO_HASH = """\
# REQ-d00001: No Assertions Req

**Level**: DEV | **Status**: Draft | **Implements**: -

Some body text but no assertions section.

*End* *No Assertions Req*
---
"""


def _make_project(
    tmp_path: Path,
    req_content: str,
    filename: str = "requirements.md",
) -> Path:
    """Create a minimal project with config and a single spec file."""
    config_path = tmp_path / ".elspais.toml"
    config_path.write_text(CONFIG_TOML)

    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()

    req_file = spec_dir / filename
    req_file.write_text(req_content)

    return tmp_path


def _make_fix_args(
    project: Path,
    req_id: str,
    *,
    dry_run: bool = False,
    message: str | None = None,
) -> argparse.Namespace:
    """Build an argparse.Namespace matching what fix_cmd.run expects."""
    return argparse.Namespace(
        req_id=req_id,
        dry_run=dry_run,
        spec_dir=project / "spec",
        config=project / ".elspais.toml",
        verbose=False,
        quiet=False,
        message=message,
    )


def _build_graph(project: Path):
    """Build a graph for the test project."""
    from elspais.graph.factory import build_graph

    return build_graph(
        spec_dirs=[project / "spec"],
        config_path=project / ".elspais.toml",
        repo_root=project,
        scan_code=False,
        scan_tests=False,
    )


def _find_node(graph, req_id: str):
    """Find a requirement node by ID."""
    from elspais.graph import NodeKind

    for n in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if n.id == req_id:
            return n
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Tests: validate.py — N/A hash detection
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# Tests: fix_cmd._fix_single — N/A hash update
# ─────────────────────────────────────────────────────────────────────────────


class TestFixSingleNAHash:
    """Tests for fix_cmd._fix_single() handling N/A hash sentinel.

    Validates REQ-p00002-C: fix updates hash to N/A when no hashable content.
    Validates REQ-p00004-A: fix single-requirement mode handles N/A.
    """

    def test_REQ_p00002_C_fix_single_updates_to_na(self, tmp_path, capsys):
        """When a requirement has a stored hash but no hashable content,
        fix should update the stored hash to "N/A".
        """
        project = _make_project(tmp_path, REQ_NO_ASSERTIONS_WITH_HASH)
        args = _make_fix_args(project, "REQ-d00001")

        from elspais.commands.fix_cmd import run

        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            result = run(args)
        finally:
            os.chdir(old_cwd)

        assert result == 0

        # The hash in the file should now be "N/A"
        spec_file = project / "spec" / "requirements.md"
        content = spec_file.read_text()
        assert "deadbeef" not in content, "Old hash should be replaced"
        assert "N/A" in content, "Hash should be updated to N/A"

    def test_REQ_p00002_C_fix_single_na_already_current(self, tmp_path, capsys):
        """When stored hash is already "N/A" and there's no hashable content,
        fix should report "already up to date" and not modify the file.
        """
        project = _make_project(tmp_path, REQ_NO_ASSERTIONS_NA_HASH)
        args = _make_fix_args(project, "REQ-d00001")

        from elspais.commands.fix_cmd import run

        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            result = run(args)
        finally:
            os.chdir(old_cwd)

        assert result == 0

        captured = capsys.readouterr()
        assert (
            "already up to date" in captured.out.lower()
        ), f"Expected 'already up to date' message, got: {captured.out!r}"

        # File should be unchanged
        spec_file = project / "spec" / "requirements.md"
        content = spec_file.read_text()
        assert "N/A" in content, "N/A hash should remain"


# ─────────────────────────────────────────────────────────────────────────────
# Tests: compute_hash_for_node location
# ─────────────────────────────────────────────────────────────────────────────


class TestREQ_d00131_J_compute_hash_in_render:
    """Validates REQ-d00131-J: compute_hash_for_node lives in graph.render."""

    def test_REQ_d00131_J_importable_from_render(self):
        """compute_hash_for_node should be importable from elspais.graph.render."""
        from elspais.graph.render import compute_hash_for_node

        assert callable(compute_hash_for_node)
