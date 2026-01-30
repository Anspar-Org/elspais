"""Tests for elspais hash update command.

Tests REQ-p00001-C: detect changes to requirements using content hashing.

The hash update command updates requirement hashes in spec files:
- elspais hash update: Update all stale hashes
- elspais hash update REQ-xxx: Update specific requirement
- --dry-run: Show changes without applying
- --json: Machine-readable output
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
def git_repo_with_stale_hash(tmp_path):
    """Create a temporary git repository with a requirement that has a stale hash."""
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

    # Create a requirement file with STALE hashes
    # The hash is computed from assertion text, not from the full body
    # "A. The system SHALL validate input." hashes to something != deadbeef
    req_file = spec_dir / "requirements.md"
    req_file.write_text(
        """# Requirements

## REQ-p00001: Sample Requirement

**Level**: PRD | **Status**: Active | **Implements**: -

Some introductory text.

## Assertions

A. The system SHALL validate input.

*End* *Sample Requirement* | **Hash**: deadbeef

---

## REQ-p00002: Another Requirement

**Level**: PRD | **Status**: Active | **Implements**: -

More introductory text.

## Assertions

A. The system SHALL process data.

*End* *Another Requirement* | **Hash**: 00000000
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
# Test: update_hash_in_file helper
# ─────────────────────────────────────────────────────────────────────────────


class TestUpdateHashInFile:
    """Tests for update_hash_in_file() helper function."""

    def test_updates_hash_in_file(self, git_repo_with_stale_hash):
        """Update a hash value in a spec file."""
        from elspais.mcp.file_mutations import update_hash_in_file

        spec_file = git_repo_with_stale_hash / "spec" / "requirements.md"

        result = update_hash_in_file(
            file_path=spec_file,
            req_id="REQ-p00001",
            new_hash="abcd1234",
        )

        assert result is True

        # Verify the file was updated
        content = spec_file.read_text()
        assert "**Hash**: abcd1234" in content
        # Old hash should be gone
        assert "deadbeef" not in content

    def test_returns_false_when_req_not_found(self, git_repo_with_stale_hash):
        """Return False when requirement is not found in file."""
        from elspais.mcp.file_mutations import update_hash_in_file

        spec_file = git_repo_with_stale_hash / "spec" / "requirements.md"

        result = update_hash_in_file(
            file_path=spec_file,
            req_id="REQ-NONEXISTENT",
            new_hash="abcd1234",
        )

        assert result is False

    def test_handles_different_title_formats(self, tmp_path):
        """Handle various title formats in the End marker."""
        from elspais.mcp.file_mutations import update_hash_in_file

        spec_file = tmp_path / "test.md"
        spec_file.write_text(
            """# Test Spec

## REQ-d00001: My Complex Title Here

**Level**: DEV | **Status**: Active | **Implements**: -

Body content.

## Assertions

A. The system SHALL do something.

*End* *My Complex Title Here* | **Hash**: abcd1234
"""
        )

        result = update_hash_in_file(
            file_path=spec_file,
            req_id="REQ-d00001",
            new_hash="deadbeef",
        )

        assert result is True
        content = spec_file.read_text()
        assert "**Hash**: deadbeef" in content


# ─────────────────────────────────────────────────────────────────────────────
# Test: _update_hashes command implementation
# ─────────────────────────────────────────────────────────────────────────────


class TestUpdateHashesCommand:
    """Tests for the hash update command."""

    def test_dry_run_shows_changes_without_applying(self, git_repo_with_stale_hash, capsys):
        """--dry-run shows what would be changed but doesn't modify files."""
        import argparse

        from elspais.commands.hash_cmd import run

        args = argparse.Namespace(
            hash_action="update",
            spec_dir=git_repo_with_stale_hash / "spec",
            config=git_repo_with_stale_hash / ".elspais.toml",
            dry_run=True,
            req_id=None,
            json_output=False,
        )

        result = run(args)

        # Command should succeed
        assert result == 0

        # Verify output shows changes
        captured = capsys.readouterr()
        assert "REQ-p00001" in captured.out or "deadbeef" in captured.out

        # But file should NOT be modified
        spec_file = git_repo_with_stale_hash / "spec" / "requirements.md"
        content = spec_file.read_text()
        assert "deadbeef" in content  # Original hash still there

    def test_updates_all_stale_hashes(self, git_repo_with_stale_hash, capsys):
        """Update all stale hashes in spec files."""
        import argparse

        from elspais.commands.hash_cmd import run

        args = argparse.Namespace(
            hash_action="update",
            spec_dir=git_repo_with_stale_hash / "spec",
            config=git_repo_with_stale_hash / ".elspais.toml",
            dry_run=False,
            req_id=None,
            json_output=False,
        )

        result = run(args)

        assert result == 0

        # Verify hashes were updated
        spec_file = git_repo_with_stale_hash / "spec" / "requirements.md"
        content = spec_file.read_text()
        # Old hashes should be replaced
        assert "deadbeef" not in content
        assert "00000000" not in content

    def test_updates_specific_requirement(self, git_repo_with_stale_hash, capsys):
        """Update hash for a specific requirement only."""
        import argparse

        from elspais.commands.hash_cmd import run

        args = argparse.Namespace(
            hash_action="update",
            spec_dir=git_repo_with_stale_hash / "spec",
            config=git_repo_with_stale_hash / ".elspais.toml",
            dry_run=False,
            req_id="REQ-p00001",
            json_output=False,
        )

        result = run(args)

        assert result == 0

        # Verify only REQ-p00001's hash was updated
        spec_file = git_repo_with_stale_hash / "spec" / "requirements.md"
        content = spec_file.read_text()
        assert "deadbeef" not in content  # REQ-p00001 hash updated
        assert "00000000" in content  # REQ-p00002 hash NOT updated

    def test_verify_after_update_passes(self, git_repo_with_stale_hash):
        """After update, hash verify should pass."""
        import argparse

        from elspais.commands.hash_cmd import run

        # First update
        update_args = argparse.Namespace(
            hash_action="update",
            spec_dir=git_repo_with_stale_hash / "spec",
            config=git_repo_with_stale_hash / ".elspais.toml",
            dry_run=False,
            req_id=None,
            json_output=False,
        )
        run(update_args)

        # Then verify - should pass (return 0)
        verify_args = argparse.Namespace(
            hash_action="verify",
            spec_dir=git_repo_with_stale_hash / "spec",
            config=git_repo_with_stale_hash / ".elspais.toml",
            quiet=False,
        )
        result = run(verify_args)

        assert result == 0
