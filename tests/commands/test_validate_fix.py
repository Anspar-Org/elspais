"""Tests for elspais validate --fix command.

Tests REQ-p00002: Requirements Validation with auto-fix capability.

The validate --fix command auto-fixes:
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
    subprocess.run(["git", "init"], cwd=tmp_path, env=env, capture_output=True, check=True)
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
[project]
name = "test-project"

[patterns]
prefix = "REQ"
"""
    )

    # Create requirements with various issues:
    # 1. REQ-p00001: Stale hash (needs update)
    # 2. REQ-p00002: Missing hash (needs insert)
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

## REQ-p00002: Requirement Missing Hash

**Level**: PRD | **Status**: Active | **Implements**: -

Some intro text.

## Assertions

A. The system SHALL process output.

*End* *Requirement Missing Hash*

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
# Test: validate --fix --dry-run
# ─────────────────────────────────────────────────────────────────────────────


class TestValidateFixDryRun:
    """Tests for validate --fix --dry-run mode."""

    def test_dry_run_shows_fixable_issues(self, git_repo_with_issues, capsys):
        """--dry-run shows what would be fixed without modifying files."""
        import argparse

        from elspais.commands.validate import run

        args = argparse.Namespace(
            spec_dir=git_repo_with_issues / "spec",
            config=git_repo_with_issues / ".elspais.toml",
            fix=True,
            dry_run=True,
            skip_rule=None,
            json=False,
            quiet=False,
        )

        result = run(args)

        # Should report success (no errors, just warnings/fixable issues)
        assert result == 0

        captured = capsys.readouterr()
        # Should mention at least one issue that would be fixed
        assert "Would fix" in captured.out or "hash" in captured.out.lower()

        # But file should NOT be modified
        spec_file = git_repo_with_issues / "spec" / "requirements.md"
        content = spec_file.read_text()
        assert "deadbeef" in content  # Stale hash should still be there


# ─────────────────────────────────────────────────────────────────────────────
# Test: validate --fix (actual fixes)
# ─────────────────────────────────────────────────────────────────────────────


class TestValidateFix:
    """Tests for validate --fix mode."""

    def test_fix_updates_stale_hashes(self, git_repo_with_issues, capsys):
        """--fix updates stale hashes in spec files."""
        import argparse

        from elspais.commands.validate import run

        args = argparse.Namespace(
            spec_dir=git_repo_with_issues / "spec",
            config=git_repo_with_issues / ".elspais.toml",
            fix=True,
            dry_run=False,
            skip_rule=None,
            json=False,
            quiet=False,
        )

        result = run(args)

        assert result == 0

        # Verify hash was updated
        spec_file = git_repo_with_issues / "spec" / "requirements.md"
        content = spec_file.read_text()
        assert "deadbeef" not in content  # Stale hash should be replaced

    def test_after_fix_validation_passes(self, git_repo_with_issues, capsys):
        """After --fix, regular validation should pass (for fixable issues)."""
        import argparse

        from elspais.commands.validate import run

        # First fix
        fix_args = argparse.Namespace(
            spec_dir=git_repo_with_issues / "spec",
            config=git_repo_with_issues / ".elspais.toml",
            fix=True,
            dry_run=False,
            skip_rule=None,
            json=False,
            quiet=False,
        )
        run(fix_args)

        # Clear captured output
        capsys.readouterr()

        # Then validate without fix
        validate_args = argparse.Namespace(
            spec_dir=git_repo_with_issues / "spec",
            config=git_repo_with_issues / ".elspais.toml",
            fix=False,
            dry_run=False,
            skip_rule=None,
            json=False,
            quiet=False,
        )
        run(validate_args)

        # Should pass (no hash-related errors)
        captured = capsys.readouterr()
        # After fix, hash.mismatch issues should be gone
        assert "hash.mismatch" not in captured.err


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
