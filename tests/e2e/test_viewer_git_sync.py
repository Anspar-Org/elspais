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

    Validates REQ-p00004-B and REQ-p00004-E via CLI subprocess.
    """

    # Verifies: REQ-p00004-B
    def test_REQ_p00004_B_changed_detects_uncommitted_edit(self, tmp_path) -> None:
        """elspais changed reports an uncommitted edit to an Assertion."""
        _init_fixture_repo(tmp_path)

        # Clean state: no changes
        result = run_elspais("changed", "--format", "json", cwd=tmp_path)
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert data["verifiable"] is True
        assert data["changes"] == []

        # Edit the Assertion, leaving it uncommitted
        (tmp_path / "spec" / "prd.md").write_text(
            "# REQ-p00001: Original Requirement\n\n"
            "**Level**: PRD | **Status**: Active\n\n"
            "The system SHALL do something.\n\n"
            "## Assertions\n\n"
            "A. The system SHALL work correctly and quickly.\n\n"
            "*End* *Original Requirement* | **Hash**: 00000000\n"
        )

        result = run_elspais("changed", "--format", "json", cwd=tmp_path)
        assert result.returncode == 0, result.stderr
        ids = {change["id"] for change in json.loads(result.stdout)["changes"]}
        assert ids == {"REQ-p00001", "REQ-p00001-A"}

    # Verifies: REQ-p00004-B
    def test_REQ_p00004_B_changed_on_branch(self, tmp_path) -> None:
        """elspais changed reports an Assertion edit committed on a feature branch."""
        _init_fixture_repo(tmp_path)

        # Create a branch and commit an Assertion edit
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

        result = run_elspais("changed", "--format", "json", cwd=tmp_path)
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert data["base"]["branch"] == "main"
        assert data["base"]["commit"] == _git(tmp_path, "rev-parse", "main").stdout.strip()
        assert "REQ-p00001-A" in {change["id"] for change in data["changes"]}

    # Verifies: REQ-p00004-E
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
