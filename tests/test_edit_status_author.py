# Verifies: REQ-o00063-A, REQ-d00231-E
"""Tests for the ``elspais edit --status Active`` Draft -> Active transition
when changelog author identity cannot be resolved.

Validates REQ-o00063-A (status mutations are atomic and visible) and
REQ-d00231-E (author identity resolved server-side, never silently dropped).
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from unittest.mock import patch

DRAFT_REQ = """\
# REQ-d00001: Draft Req

**Level**: DEV | **Status**: Draft | **Implements**: -

## Assertions

A. The system SHALL do X.

*End* *Draft Req* | **Hash**: 1c0aac79
---
"""


def _make_project(tmp_path: Path) -> Path:
    """Create a minimal project with a single Draft req."""
    (tmp_path / ".elspais.toml").write_text(
        "version = 3\n"
        "\n"
        "[project]\n"
        'name = "test"\n'
        'namespace = "REQ"\n'
        "\n"
        "[scanning.spec]\n"
        'directories = ["spec"]\n'
        "\n"
        "[changelog]\n"
        "hash_current = true\n"
    )
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    spec_file = spec_dir / "requirements.md"
    spec_file.write_text(DRAFT_REQ)
    return tmp_path


def _make_edit_args(project: Path, req_id: str, status: str) -> argparse.Namespace:
    return argparse.Namespace(
        req_id=req_id,
        status=status,
        implements=None,
        move_to=None,
        spec_dir=project / "spec",
        config=project / ".elspais.toml",
        dry_run=False,
        validate_refs=False,
        from_json=None,
    )


class TestDraftActiveTransitionRequiresAuthor:
    """Draft -> Active status transition must refuse to flip status when
    the changelog author cannot be resolved -- the changelog entry that
    records the activation cannot be written without author identity.
    """

    def test_draft_to_active_refused_when_author_unresolvable(self, tmp_path: Path):
        from elspais.utilities.changelog_author import AuthorResolutionError

        project = _make_project(tmp_path)
        spec_file = project / "spec" / "requirements.md"

        args = _make_edit_args(project, "REQ-d00001", status="Active")

        from elspais.commands.edit import run

        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            with patch(
                "elspais.utilities.changelog_author.resolve_changelog_author",
                side_effect=AuthorResolutionError(missing=["author_name"]),
            ):
                result = run(args)
        finally:
            os.chdir(old_cwd)

        assert result == 1, "edit must exit 1 when author resolution fails"

        # Status must NOT have flipped on disk.
        content = spec_file.read_text()
        assert "**Status**: Draft" in content, (
            "Status should remain Draft when changelog author cannot be "
            f"resolved. File content was:\n{content}"
        )
        assert "**Status**: Active" not in content

    def test_draft_to_active_proceeds_when_author_resolvable(self, tmp_path: Path):
        project = _make_project(tmp_path)
        spec_file = project / "spec" / "requirements.md"

        args = _make_edit_args(project, "REQ-d00001", status="Active")

        from elspais.commands.edit import run

        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            with patch(
                "elspais.utilities.changelog_author.resolve_changelog_author",
                return_value={"name": "Tester", "id": "t@t.com"},
            ):
                result = run(args)
        finally:
            os.chdir(old_cwd)

        assert result == 0, "edit should succeed when author is resolvable"

        content = spec_file.read_text()
        assert "**Status**: Active" in content
        assert "Changelog" in content, (
            "An initial changelog entry should have been added on Draft -> Active. "
            f"File content was:\n{content}"
        )
        assert "Tester" in content
