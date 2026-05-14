# Verifies: REQ-p00004-A, REQ-d00231-E
"""Tests that ``elspais fix`` fails loudly when changelog author cannot be
resolved for an Active requirement.

Validates REQ-p00004-A: changelog entries are required for Active
requirements and must record author identity. Validates REQ-d00231-E:
author identity is resolved server-side via ``changelog.id_source``.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.commands.test_fix_changelog import (
    ACTIVE_REQ_STALE_HASH,
    DRAFT_REQ_STALE_HASH,
    _make_fix_args,
    _make_project,
)


def _patch_resolver_raising(missing: list[str]):
    """Patch ``resolve_changelog_author`` to raise the given missing fields."""
    from elspais.utilities.changelog_author import AuthorResolutionError

    return patch(
        "elspais.utilities.changelog_author.resolve_changelog_author",
        side_effect=AuthorResolutionError(missing=missing),
    )


class TestFixFailsWhenAuthorMissing:
    """Fix command must abort (exit 1) before any file write when changelog
    enforcement is on, an Active req needs a changelog entry, and author
    info cannot be resolved.
    """

    def test_fix_active_req_exits_1_when_author_unresolvable(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ):
        project = _make_project(tmp_path, ACTIVE_REQ_STALE_HASH)
        spec_file = project / "spec" / "requirements.md"
        before = spec_file.read_text()

        args = _make_fix_args(project, "REQ-d00001", message="some reason")

        from elspais.commands.fix_cmd import run

        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            with _patch_resolver_raising(["author_name", "author_id"]):
                result = run(args)
        finally:
            os.chdir(old_cwd)

        assert result == 1, "fix must exit 1 when author cannot be resolved"

        after = spec_file.read_text()
        assert after == before, "fix must not write to disk on author failure"

        captured = capsys.readouterr()
        assert "author_name" in captured.err, (
            "stderr should name the missing field. " f"stderr was: {captured.err!r}"
        )

    @patch(
        "elspais.utilities.git.get_author_info",
        return_value={"name": "Test User", "id": "t@t.org"},
    )
    def test_fix_passes_through_when_enforcement_off(self, _mock_author, tmp_path: Path):
        """If ``hash_current = false`` the fix command must not consult the
        author resolver at all -- failures there must not block the fix.
        """
        # Build a project with hash_current = false
        config_path = tmp_path / ".elspais.toml"
        config_path.write_text(
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
            "hash_current = false\n"
        )
        (tmp_path / "spec").mkdir()
        spec_file = tmp_path / "spec" / "requirements.md"
        spec_file.write_text(ACTIVE_REQ_STALE_HASH)

        args = _make_fix_args(tmp_path, "REQ-d00001", message=None)

        from elspais.commands.fix_cmd import run

        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            with _patch_resolver_raising(["author_name", "author_id"]):
                result = run(args)
        finally:
            os.chdir(old_cwd)

        assert result == 0, "fix should succeed when hash_current is false"

        content = spec_file.read_text()
        assert "00000000" not in content, "Stale hash should have been fixed"

    @patch(
        "elspais.utilities.git.get_author_info",
        return_value={"name": "Test User", "id": "t@t.org"},
    )
    def test_fix_skips_author_check_when_no_active_needs_entry(self, _mock_author, tmp_path: Path):
        """If only Draft reqs need fixing, author resolution must not be
        attempted -- Draft changes don't need changelog entries.
        """
        project = _make_project(tmp_path, DRAFT_REQ_STALE_HASH)
        spec_file = project / "spec" / "requirements.md"

        args = _make_fix_args(project, "REQ-d00002", message=None)

        from elspais.commands.fix_cmd import run

        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            with _patch_resolver_raising(["author_name", "author_id"]):
                result = run(args)
        finally:
            os.chdir(old_cwd)

        assert result == 0, (
            "fix should succeed for Draft-only changes even if author lookup " "would fail"
        )

        content = spec_file.read_text()
        assert "00000000" not in content, "Draft hash should have been fixed"

    def test_fix_succeeds_when_only_unrequired_field_missing(self, tmp_path: Path):
        """When ``author_name`` is not required and only the name is empty,
        resolve_changelog_author returns ``{"name": "", "id": "..."}`` and
        fix should complete normally.
        """
        # Build a project with author_name not required
        config_path = tmp_path / ".elspais.toml"
        config_path.write_text(
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
            "\n"
            "[changelog.require]\n"
            "author_name = false\n"
            "author_id = true\n"
        )
        (tmp_path / "spec").mkdir()
        spec_file = tmp_path / "spec" / "requirements.md"
        spec_file.write_text(ACTIVE_REQ_STALE_HASH)

        args = _make_fix_args(tmp_path, "REQ-d00001", message="reasonable")

        from elspais.commands.fix_cmd import run

        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            # The resolver is patched to return name="" and id present, just
            # as the real helper would when author_name is not required and
            # git config user.name is empty.
            with patch(
                "elspais.utilities.changelog_author.resolve_changelog_author",
                return_value={"name": "", "id": "real@example.com"},
            ):
                result = run(args)
        finally:
            os.chdir(old_cwd)

        assert result == 0, "fix should succeed when only un-required field is empty"

        content = spec_file.read_text()
        assert "## Changelog" in content
        assert "real@example.com" in content


# Silence unused-arg warning for argparse import at module level
_ = argparse  # pragma: no cover
