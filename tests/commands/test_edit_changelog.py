# Validates: REQ-p00004-A
"""Tests for edit command Draft->Active changelog entry.

When ``elspais edit --status Active`` is applied to a Draft requirement,
a changelog entry with reason "First approved version" must be added.
"""

import argparse
import os
from pathlib import Path
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

DRAFT_REQ = """\
# REQ-d00001: Test Req

**Level**: DEV | **Status**: Draft | **Implements**: -

## Assertions

A. The system SHALL do X.

*End* *Test Req* | **Hash**: 00000000
---
"""

ACTIVE_REQ = """\
# REQ-d00002: Active Req

**Level**: DEV | **Status**: Active | **Implements**: -

## Assertions

A. The system SHALL do Y.

*End* *Active Req* | **Hash**: 00000000
---
"""

CONFIG_TOML = """\
[project]
name = "test"

[patterns]
prefix = "REQ"

[changelog]
enforce = true
"""

MOCK_AUTHOR = {"name": "Test User", "id": "test@test.org"}


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


def _make_edit_args(
    project: Path,
    req_id: str,
    *,
    status: str | None = None,
    dry_run: bool = False,
) -> argparse.Namespace:
    """Build an argparse.Namespace matching what edit.run expects."""
    return argparse.Namespace(
        req_id=req_id,
        status=status,
        implements=None,
        move_to=None,
        dry_run=dry_run,
        spec_dir=project / "spec",
        config=project / ".elspais.toml",
        from_json=None,
        validate_refs=False,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEditChangelog:
    """Tests for changelog entry when transitioning Draft -> Active.

    Validates REQ-p00004-A: edit --status Active on a Draft requirement
    adds a changelog entry with "First approved version".
    """

    @patch("elspais.utilities.git.get_author_info", return_value=MOCK_AUTHOR)
    def test_REQ_p00004_A_edit_draft_to_active_adds_changelog(self, mock_author, tmp_path: Path):
        """Changing status from Draft to Active must add a ## Changelog
        section with "First approved version" entry.

        Validates REQ-p00004-A.
        """
        project = _make_project(tmp_path, DRAFT_REQ)
        args = _make_edit_args(project, "REQ-d00001", status="Active")

        from elspais.commands.edit import run

        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            result = run(args)
        finally:
            os.chdir(old_cwd)

        assert result == 0

        spec_file = project / "spec" / "requirements.md"
        content = spec_file.read_text()

        # Status should have been changed
        assert "**Status**: Active" in content

        # Changelog section must exist with the initial entry
        assert "## Changelog" in content, "Draft->Active transition must add a ## Changelog section"
        assert "First approved version" in content, (
            "Draft->Active changelog entry must contain " "'First approved version'"
        )

    @patch("elspais.utilities.git.get_author_info", return_value=MOCK_AUTHOR)
    def test_REQ_p00004_A_edit_active_to_active_no_changelog(self, mock_author, tmp_path: Path):
        """Changing status Active->Active is a no-op; no changelog
        should be added.

        Validates REQ-p00004-A.
        """
        project = _make_project(tmp_path, ACTIVE_REQ)
        args = _make_edit_args(project, "REQ-d00002", status="Active")

        from elspais.commands.edit import run

        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            result = run(args)
        finally:
            os.chdir(old_cwd)

        assert result == 0

        spec_file = project / "spec" / "requirements.md"
        content = spec_file.read_text()

        # No changelog should be added for a no-op status change
        assert "## Changelog" not in content

    @patch("elspais.utilities.git.get_author_info", return_value=MOCK_AUTHOR)
    def test_REQ_p00004_A_edit_draft_to_draft_no_changelog(self, mock_author, tmp_path: Path):
        """Changing status Draft->Draft is a no-op; no changelog
        should be added.

        Validates REQ-p00004-A.
        """
        project = _make_project(tmp_path, DRAFT_REQ)
        args = _make_edit_args(project, "REQ-d00001", status="Draft")

        from elspais.commands.edit import run

        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            result = run(args)
        finally:
            os.chdir(old_cwd)

        assert result == 0

        spec_file = project / "spec" / "requirements.md"
        content = spec_file.read_text()

        # No changelog should be added for a no-op status change
        assert "## Changelog" not in content
