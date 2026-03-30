"""Tests for elspais fix command.

Tests REQ-p00002: Requirements Validation with auto-fix capability.

The fix command auto-fixes:
- Missing hash: Compute and insert
- Outdated hash: Recompute from body
- Missing Status: Add default "Active"

Non-fixable issues (reported only):
- Broken references to non-existent requirements
- Orphaned requirements (no parent)
"""

import os
import subprocess

import pytest


def _clean_git_env() -> dict[str, str]:
    """Return environment with GIT_DIR/GIT_WORK_TREE removed for test isolation."""
    env = os.environ.copy()
    env.pop("GIT_DIR", None)
    env.pop("GIT_WORK_TREE", None)
    return env


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def git_repo_with_issues(tmp_path):
    """Create a temporary git repository with requirements that have fixable issues."""
    env = _clean_git_env()

    # Initialize git repo
    subprocess.run(
        ["git", "init", "-b", "main"], cwd=tmp_path, env=env, capture_output=True, check=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        check=True,
    )

    # Create spec directory
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()

    # Create elspais config
    config_file = tmp_path / ".elspais.toml"
    config_file.write_text(
        """
version = 3

[project]
name = "test-project"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[changelog]
hash_current = false
"""
    )

    # Create requirements with various issues:
    # 1. REQ-p00001: Stale hash (needs update)
    # 2. REQ-p00002: Stale hash (different value, also needs update)
    req_file = spec_dir / "requirements.md"
    req_file.write_text(
        """# Requirements

## REQ-p00001: Requirement With Stale Hash

**Level**: PRD | **Status**: Active | **Implements**: -

Some intro text.

## Assertions

A. The system SHALL validate input.

*End* *Requirement With Stale Hash* | **Hash**: deadbeef

---

## REQ-p00002: Another Stale Hash

**Level**: PRD | **Status**: Active | **Implements**: -

Some intro text.

## Assertions

A. The system SHALL process output.

*End* *Another Stale Hash* | **Hash**: cafebabe

---
"""
    )

    # Commit initial state
    subprocess.run(["git", "add", "."], cwd=tmp_path, env=env, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        check=True,
    )

    return tmp_path


# ─────────────────────────────────────────────────────────────────────────────
# Test: fix --dry-run
# ─────────────────────────────────────────────────────────────────────────────


class TestValidateFixDryRun:
    """Tests for fix --dry-run mode.

    Validates REQ-p00002-C: verify content hashes match requirement body text.
    """

    def test_REQ_p00002_C_dry_run_shows_fixable_issues(self, git_repo_with_issues, capsys):
        """--dry-run shows what would be fixed without modifying files."""
        import argparse

        from elspais.commands.fix_cmd import run

        args = argparse.Namespace(
            req_id=None,
            dry_run=True,
            spec_dir=git_repo_with_issues / "spec",
            config=git_repo_with_issues / ".elspais.toml",
            quiet=False,
            verbose=False,
            mode="combined",
        )

        result = run(args)

        # Dry-run always returns 0 (issues shown but not an error)
        assert result == 0

        captured = capsys.readouterr()
        # Should mention at least one issue that would be fixed
        assert "Would fix" in captured.out or "hash" in captured.out.lower()

        # But file should NOT be modified
        spec_file = git_repo_with_issues / "spec" / "requirements.md"
        content = spec_file.read_text()
        assert "deadbeef" in content  # Stale hash should still be there


# ─────────────────────────────────────────────────────────────────────────────
# Test: fix (actual fixes)
# ─────────────────────────────────────────────────────────────────────────────


class TestValidateFix:
    """Tests for fix mode.

    Validates REQ-p00002-C: verify content hashes match requirement body text.
    """

    def test_REQ_p00002_C_fix_updates_stale_hashes(self, git_repo_with_issues, capsys):
        """Validates REQ-p00002-C: fix updates stale hashes in spec files."""
        import argparse

        from elspais.commands.fix_cmd import run

        args = argparse.Namespace(
            req_id=None,
            dry_run=False,
            spec_dir=git_repo_with_issues / "spec",
            config=git_repo_with_issues / ".elspais.toml",
            quiet=False,
            verbose=False,
            mode="combined",
        )

        result = run(args)

        assert result == 0

        # Verify hash was updated
        spec_file = git_repo_with_issues / "spec" / "requirements.md"
        content = spec_file.read_text()
        assert "deadbeef" not in content  # Stale hash should be replaced


# ─────────────────────────────────────────────────────────────────────────────
# Test: add_status_to_file helper
# ─────────────────────────────────────────────────────────────────────────────


class TestAddStatusToFile:
    """Tests for add_status_to_file() helper function.

    Validates REQ-p00002-A: validate requirement format against configurable patterns.
    """

    def test_REQ_p00002_A_adds_status_when_missing(self, tmp_path):
        """Add Status field to requirement that's missing it."""
        from elspais.mcp.file_mutations import add_status_to_file

        spec_file = tmp_path / "test.md"
        spec_file.write_text(
            """# Test Spec

## REQ-d00001: Missing Status

**Level**: DEV | **Implements**: -

## Assertions

A. The system SHALL do something.

*End* *Missing Status* | **Hash**: abcd1234
"""
        )

        result = add_status_to_file(
            file_path=spec_file,
            req_id="REQ-d00001",
            status="Active",
        )

        assert result is None, f"Expected success (None), got error: {result}"
        content = spec_file.read_text()
        assert "**Status**: Active" in content

    def test_REQ_p00002_A_returns_error_when_status_exists(self, tmp_path):
        """Return error string when Status already exists."""
        from elspais.mcp.file_mutations import add_status_to_file

        spec_file = tmp_path / "test.md"
        spec_file.write_text(
            """# Test Spec

## REQ-d00001: Has Status

**Level**: DEV | **Status**: Draft | **Implements**: -

## Assertions

A. The system SHALL do something.

*End* *Has Status* | **Hash**: abcd1234
"""
        )

        result = add_status_to_file(
            file_path=spec_file,
            req_id="REQ-d00001",
            status="Active",
        )

        # Should return error string - status already exists
        assert result is not None
        assert "REQ-d00001" in result
        assert "Status" in result
        content = spec_file.read_text()
        # Original status should be unchanged
        assert "**Status**: Draft" in content
