"""Tests for post-save rebuild verification.

Validates REQ-d00131-B: after fix + rebuild, graph has no dirty nodes.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from elspais.graph import NodeKind
from elspais.graph.factory import build_graph

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ─────────────────────────────────────────────────────────────────────────────

CONFIG_TOML = """\
version = 3

[project]
name = "test"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]
"""

REQ_WRONG_HASH = """\
## REQ-d00001: Test Requirement

**Level**: dev | **Status**: Active | **Implements**: -

Body text here.

## Assertions

A. First assertion

B. Second assertion

*End* *Test Requirement* | **Hash**: deadbeef
---
"""


def _make_project(
    tmp_path: Path,
    spec_content: str,
    config: str = CONFIG_TOML,
    filename: str = "test.md",
) -> Path:
    """Create a minimal project with config and a single spec file."""
    config_path = tmp_path / ".elspais.toml"
    config_path.write_text(config)
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    (spec_dir / filename).write_text(spec_content)
    return tmp_path


def _make_fix_args(
    project: Path,
    *,
    req_id: str | None = None,
    dry_run: bool = False,
    message: str | None = None,
) -> argparse.Namespace:
    """Build an argparse.Namespace matching what fix_cmd.run expects."""
    return argparse.Namespace(
        req_id=req_id,
        dry_run=dry_run,
        spec_dir=project / "spec",
        config=project / ".elspais.toml",
        quiet=False,
        verbose=False,
        message=message,
        git_root=project,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestREQ_d00131_B_post_save_rebuild:
    """Validates REQ-d00131-B: post-save rebuild produces clean graph."""

    def test_REQ_d00131_B_rebuild_after_fix_has_no_dirty_nodes(self, tmp_path):
        """After fix + rebuild, _detect_fixable returns empty for all reqs."""
        from elspais.commands.fix_cmd import _detect_fixable, run

        project = _make_project(tmp_path, REQ_WRONG_HASH)
        args = _make_fix_args(project)
        run(args)

        # Rebuild from disk
        graph = build_graph(
            spec_dirs=[project / "spec"],
            config_path=project / ".elspais.toml",
            repo_root=project,
            scan_code=False,
            scan_tests=False,
        )
        hash_mode = getattr(graph, "hash_mode", "full-text")

        # All requirements should be clean
        for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
            reasons = _detect_fixable(node, hash_mode, changelog_enforce=False)
            assert reasons == [], f"{node.id} still has fixable issues after fix: {reasons}"

    def test_REQ_d00131_B_rebuild_after_fix_mixed_issues(self, tmp_path):
        """Fix on file with assertion spacing + wrong hash -> clean rebuild."""
        from elspais.commands.fix_cmd import _detect_fixable, run

        # Wrong hash AND consecutive assertions (no blank line between them)
        spec = """\
## REQ-d00001: Mixed Issues

**Level**: dev | **Status**: Active | **Implements**: -

Body text.

## Assertions

A. First assertion
B. Second assertion

*End* *Mixed Issues* | **Hash**: deadbeef
---
"""
        project = _make_project(tmp_path, spec)
        args = _make_fix_args(project)
        run(args)

        graph = build_graph(
            spec_dirs=[project / "spec"],
            config_path=project / ".elspais.toml",
            repo_root=project,
            scan_code=False,
            scan_tests=False,
        )
        hash_mode = getattr(graph, "hash_mode", "full-text")

        for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
            reasons = _detect_fixable(node, hash_mode, changelog_enforce=False)
            assert reasons == [], f"{node.id} still dirty after fix: {reasons}"
