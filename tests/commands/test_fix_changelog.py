# Verifies: REQ-p00004-A
"""Tests for fix command changelog enforcement.

Tests REQ-p00004-A: When fixing Active requirements, a changelog entry
is required. Draft requirements can be fixed silently.
"""

import argparse
import os
from pathlib import Path
from unittest.mock import patch

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

ACTIVE_REQ_STALE_HASH = """\
# REQ-d00001: Test Req

**Level**: DEV | **Status**: Active | **Implements**: -

## Assertions

A. The system SHALL do X.

*End* *Test Req* | **Hash**: 00000000
---
"""

DRAFT_REQ_STALE_HASH = """\
# REQ-d00002: Draft Req

**Level**: DEV | **Status**: Draft | **Implements**: -

## Assertions

A. The system SHALL do Y.

*End* *Draft Req* | **Hash**: 00000000
---
"""

CONFIG_TOML = """\
version = 3

[project]
name = "test"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[changelog]
hash_current = true
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


MOCK_AUTHOR = {"name": "Test User", "id": "test@test.org"}


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestFixChangelog:
    """Tests for changelog enforcement during fix.

    Validates REQ-p00004-A: fix command requires changelog entries for
    Active requirements and silently updates Draft requirements.
    """

    @patch("sys.stdin")
    @patch("elspais.utilities.git.get_author_info", return_value=MOCK_AUTHOR)
    def test_REQ_p00004_A_fix_active_req_requires_message(
        self, mock_author, mock_stdin, tmp_path: Path
    ):
        """Fix an Active req with stale hash but no -m flag and non-interactive
        stdin should fail and NOT update the file.

        Validates REQ-p00004-A: changelog message is mandatory for Active reqs.
        """
        mock_stdin.isatty.return_value = False

        project = _make_project(tmp_path, ACTIVE_REQ_STALE_HASH)
        args = _make_fix_args(project, "REQ-d00001", message=None)

        from elspais.commands.fix_cmd import run

        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            result = run(args)
        finally:
            os.chdir(old_cwd)

        # Should fail — no changelog message provided
        assert result != 0

        # File should NOT be modified
        spec_file = project / "spec" / "requirements.md"
        content = spec_file.read_text()
        assert "00000000" in content, "Hash should remain unchanged when message is missing"

    @patch("elspais.utilities.git.get_author_info", return_value=MOCK_AUTHOR)
    def test_REQ_p00004_A_fix_active_req_with_message(self, mock_author, tmp_path: Path):
        """Fix an Active req with stale hash and -m "reason" should update
        hash AND add changelog entry with the message.

        Validates REQ-p00004-A: changelog entry is recorded on hash update.
        """
        project = _make_project(tmp_path, ACTIVE_REQ_STALE_HASH)
        args = _make_fix_args(project, "REQ-d00001", message="Updated assertion wording")

        from elspais.commands.fix_cmd import run

        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            result = run(args)
        finally:
            os.chdir(old_cwd)

        assert result == 0

        spec_file = project / "spec" / "requirements.md"
        content = spec_file.read_text()

        # Hash should be updated (no longer the dummy value)
        assert "00000000" not in content, "Stale hash should have been replaced"

        # Changelog section should exist with the message
        assert "## Changelog" in content
        assert "Updated assertion wording" in content
        assert "Test User" in content

    @patch("elspais.utilities.git.get_author_info", return_value=MOCK_AUTHOR)
    def test_REQ_p00004_A_fix_draft_req_no_message_needed(self, mock_author, tmp_path: Path):
        """Fix a Draft req with stale hash should update hash silently
        without requiring a message.

        Validates REQ-p00004-A: Draft reqs bypass changelog enforcement.
        """
        project = _make_project(tmp_path, DRAFT_REQ_STALE_HASH)
        args = _make_fix_args(project, "REQ-d00002", message=None)

        from elspais.commands.fix_cmd import run

        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            result = run(args)
        finally:
            os.chdir(old_cwd)

        assert result == 0

        spec_file = project / "spec" / "requirements.md"
        content = spec_file.read_text()

        # Hash should be updated
        assert "00000000" not in content, "Stale hash should have been replaced"

        # No changelog section should be added for Draft reqs
        assert "## Changelog" not in content

    @patch("elspais.utilities.git.get_author_info", return_value=MOCK_AUTHOR)
    def test_REQ_p00004_A_fix_adds_missing_changelog_section(self, mock_author, tmp_path: Path):
        """Fix an Active req whose hash is correct but has no ## Changelog
        section should add the section.

        Validates REQ-p00004-A: missing Changelog section is auto-added.
        """
        # We need an Active req with a CORRECT hash but no Changelog section.
        # First, create the req with a dummy hash and fix it to get the real hash,
        # then use that content (without Changelog) for the actual test.
        #
        # Strategy: build a req, compute its correct hash, write it back,
        # then call fix which should detect missing Changelog section.

        # Step 1: Create project and compute the correct hash
        project = _make_project(tmp_path, ACTIVE_REQ_STALE_HASH)

        from elspais.commands.validate import compute_hash_for_node
        from elspais.graph import NodeKind
        from elspais.graph.factory import build_graph

        graph = build_graph(
            spec_dirs=[project / "spec"],
            config_path=project / ".elspais.toml",
            repo_root=project,
            scan_code=False,
            scan_tests=False,
        )

        hash_mode = getattr(graph, "hash_mode", "full-text")
        node = next(n for n in graph.nodes_by_kind(NodeKind.REQUIREMENT) if n.id == "REQ-d00001")
        correct_hash = compute_hash_for_node(node, hash_mode)

        # Step 2: Write the req with the correct hash but NO Changelog section
        active_req_correct_hash = f"""\
# REQ-d00001: Test Req

**Level**: DEV | **Status**: Active | **Implements**: -

## Assertions

A. The system SHALL do X.

*End* *Test Req* | **Hash**: {correct_hash}
---
"""
        spec_file = project / "spec" / "requirements.md"
        spec_file.write_text(active_req_correct_hash)

        # Step 3: Run fix — hash is correct, but Changelog section is missing
        args = _make_fix_args(project, "REQ-d00001", message=None)

        from elspais.commands.fix_cmd import run

        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            result = run(args)
        finally:
            os.chdir(old_cwd)

        assert result == 0

        content = spec_file.read_text()

        # Changelog section should have been added
        assert "## Changelog" in content
        assert "Adding missing Changelog section" in content

        # Hash should remain correct (not changed)
        assert correct_hash in content
