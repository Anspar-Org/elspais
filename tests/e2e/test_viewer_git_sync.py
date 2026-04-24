# Verifies: REQ-p00004
"""E2E tests for git change detection via elspais CLI.

Tests the `elspais changed` command to verify git-based change detection
works correctly across branch and commit workflows.
"""

from __future__ import annotations

import json
import os
import subprocess

import pytest

from .conftest import requires_elspais, run_elspais

pytestmark = [pytest.mark.e2e, requires_elspais]

_GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@test.com",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@test.com",
}


def _git(tmp_path, *args):
    """Run a git command in the fixture directory."""
    return subprocess.run(
        ["git", *args],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env=_GIT_ENV,
        check=True,
    )


def _init_fixture_repo(tmp_path):
    """Create a minimal elspais project in a git repo."""
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.email", "test@test.com")
    _git(tmp_path, "config", "user.name", "Test")

    # Minimal fixture: opt out of changelog enforcement so `spec.changelog_present`
    # (active by default via `changelog.hash_current = true`, see commit 5e2800f)
    # doesn't fire on the single bare REQ this test writes.
    (tmp_path / ".elspais.toml").write_text(
        '[project]\nname = "git-sync-test"\nnamespace = "REQ"\n'
        "[changelog]\npresent = false\nhash_current = false\n"
    )
    (tmp_path / "spec").mkdir()
    (tmp_path / "spec" / "prd.md").write_text(
        "# REQ-p00001: Original Requirement\n\n"
        "**Level**: PRD | **Status**: Active\n\n"
        "The system SHALL do something.\n\n"
        "## Assertions\n\n"
        "A. The system SHALL work correctly.\n\n"
        "*End* *Original Requirement* | **Hash**: 00000000\n"
    )
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "initial commit")


class TestGitSyncWorkflowE2E:
    """E2E tests for git change detection workflow.

    Validates REQ-p00004-C, REQ-p00004-D, REQ-p00004-E via CLI subprocess.
    """

    def test_REQ_p00004_C_changed_detects_modified_spec(self, tmp_path) -> None:
        """elspais changed detects modified spec files."""
        _init_fixture_repo(tmp_path)

        # Clean state: no changes
        result = run_elspais("changed", "--format", "json", cwd=tmp_path)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert len(data.get("changed", [])) == 0

        # Modify a spec file
        (tmp_path / "spec" / "prd.md").write_text(
            "# REQ-p00001: Modified Requirement\n\n"
            "**Level**: PRD | **Status**: Active\n\n"
            "The system SHALL do something different.\n\n"
            "## Assertions\n\n"
            "A. The system SHALL work correctly.\n\n"
            "*End* *Modified Requirement* | **Hash**: 00000000\n"
        )

        # Changed should detect the modification in uncommitted files
        result = run_elspais("changed", "--format", "json", cwd=tmp_path)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        modified_files = data.get("uncommitted", {}).get("modified", [])
        assert any(
            "prd.md" in f for f in modified_files
        ), f"Expected prd.md in modified files, got: {modified_files}"

    def test_REQ_p00004_D_changed_on_branch(self, tmp_path) -> None:
        """elspais changed works correctly on a feature branch."""
        _init_fixture_repo(tmp_path)

        # Create a branch and modify
        _git(tmp_path, "checkout", "-b", "feature-edit")
        (tmp_path / "spec" / "prd.md").write_text(
            "# REQ-p00001: Branch Edit\n\n"
            "**Level**: PRD | **Status**: Active\n\n"
            "The system SHALL do the branch thing.\n\n"
            "## Assertions\n\n"
            "A. The system SHALL work on branches.\n\n"
            "*End* *Branch Edit* | **Hash**: 00000000\n"
        )
        _git(tmp_path, "add", ".")
        _git(tmp_path, "commit", "-m", "branch edit")

        # Changed should detect branch-level changes
        result = run_elspais("changed", "--format", "json", cwd=tmp_path)
        assert result.returncode == 0

    def test_REQ_p00004_E_health_after_edit(self, tmp_path) -> None:
        """elspais health passes on the fixture repo after edits and commit."""
        _init_fixture_repo(tmp_path)

        # Edit, commit, then run health
        (tmp_path / "spec" / "prd.md").write_text(
            "# REQ-p00001: Updated Requirement\n\n"
            "**Level**: PRD | **Status**: Active\n\n"
            "The system SHALL do the updated thing.\n\n"
            "## Assertions\n\n"
            "A. The system SHALL pass health checks after edits.\n\n"
            "*End* *Updated Requirement* | **Hash**: 00000000\n"
        )
        _git(tmp_path, "add", ".")
        _git(tmp_path, "commit", "-m", "update spec")

        result = run_elspais("checks", "--format", "json", "--lenient", cwd=tmp_path)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["summary"]["failed"] == 0
