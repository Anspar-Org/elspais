# Validates REQ-p00001-C, REQ-p00004-A
"""Tests for elspais hash update command.

Tests REQ-p00001-C: detect changes to requirements using content hashing.
Tests REQ-p00004-A: compute and verify content hashes for change detection.

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
    """Tests for update_hash_in_file() helper function.

    Validates REQ-p00004-A: compute and verify content hashes for change detection.
    """

    def test_REQ_p00004_A_updates_hash_in_file(self, git_repo_with_stale_hash):
        """Update a hash value in a spec file."""
        from elspais.mcp.file_mutations import update_hash_in_file

        spec_file = git_repo_with_stale_hash / "spec" / "requirements.md"

        result = update_hash_in_file(
            file_path=spec_file,
            req_id="REQ-p00001",
            new_hash="abcd1234",
        )

        assert result is None, f"Expected success (None), got error: {result}"

        # Verify the file was updated
        content = spec_file.read_text()
        assert "**Hash**: abcd1234" in content
        # Old hash should be gone
        assert "deadbeef" not in content

    def test_REQ_p00004_A_returns_error_when_req_not_found(self, git_repo_with_stale_hash):
        """Return descriptive error when requirement is not found in file."""
        from elspais.mcp.file_mutations import update_hash_in_file

        spec_file = git_repo_with_stale_hash / "spec" / "requirements.md"

        result = update_hash_in_file(
            file_path=spec_file,
            req_id="REQ-NONEXISTENT",
            new_hash="abcd1234",
        )

        assert result is not None
        assert "REQ-NONEXISTENT" in result
        assert "not found" in result

    def test_REQ_p00004_A_handles_different_title_formats(self, tmp_path):
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

        assert result is None, f"Expected success (None), got error: {result}"
        content = spec_file.read_text()
        assert "**Hash**: deadbeef" in content

    def test_REQ_p00004_A_returns_error_when_no_end_marker(self, tmp_path):
        """Return descriptive error when requirement has no End marker."""
        from elspais.mcp.file_mutations import update_hash_in_file

        spec_file = tmp_path / "test.md"
        spec_file.write_text(
            """# Test Spec

## REQ-p00001: Missing Footer

**Level**: PRD | **Status**: Active | **Implements**: -

A. The system SHALL do something.
"""
        )

        result = update_hash_in_file(
            file_path=spec_file,
            req_id="REQ-p00001",
            new_hash="abcd1234",
        )

        assert result is not None
        assert "REQ-p00001" in result
        assert "End marker" in result or "Hash" in result

    def test_REQ_p00004_A_returns_error_when_end_marker_belongs_to_other_req(self, tmp_path):
        """Return error when End marker is past the next requirement header."""
        from elspais.mcp.file_mutations import update_hash_in_file

        spec_file = tmp_path / "test.md"
        spec_file.write_text(
            """# Test Spec

## REQ-p00001: First Requirement

**Level**: PRD | **Status**: Active | **Implements**: -

A. The system SHALL do something.

## REQ-p00002: Second Requirement

**Level**: PRD | **Status**: Active | **Implements**: -

A. The system SHALL do something else.

*End* *Second Requirement* | **Hash**: deadbeef
"""
        )

        result = update_hash_in_file(
            file_path=spec_file,
            req_id="REQ-p00001",
            new_hash="abcd1234",
        )

        assert result is not None
        assert "REQ-p00001" in result
        assert "different requirement" in result

    @pytest.mark.parametrize(
        "placeholder",
        ["XXXXXXXX", "TODO", "________", "PLACEHOLDER", "TBD"],
        ids=["x-placeholder", "todo", "underscore", "placeholder-word", "tbd"],
    )
    def test_REQ_p00004_A_updates_placeholder_hashes(self, tmp_path, placeholder):
        """Placeholder hash values (XXXXXXXX, TODO, ________) are matched and replaced."""
        from elspais.mcp.file_mutations import update_hash_in_file

        spec_file = tmp_path / "test.md"
        spec_file.write_text(
            f"""# Test Spec

## REQ-p00001: Placeholder Test

**Level**: PRD | **Status**: Active | **Implements**: -

A. The system SHALL do something.

*End* *Placeholder Test* | **Hash**: {placeholder}
"""
        )

        result = update_hash_in_file(
            file_path=spec_file,
            req_id="REQ-p00001",
            new_hash="abcd1234",
        )

        assert result is None, f"Expected success replacing '{placeholder}', got error: {result}"
        content = spec_file.read_text()
        assert "**Hash**: abcd1234" in content
        assert placeholder not in content


# ─────────────────────────────────────────────────────────────────────────────
# Test: _update_hashes command implementation
# ─────────────────────────────────────────────────────────────────────────────


class TestUpdateHashesCommand:
    """Tests for the hash update command.

    Validates REQ-p00001-C: detect changes to requirements using content hashing.
    """

    def test_REQ_p00001_C_dry_run_shows_changes(self, git_repo_with_stale_hash, capsys):
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

    def test_REQ_p00001_C_updates_all_stale_hashes(self, git_repo_with_stale_hash, capsys):
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

    def test_REQ_p00001_C_updates_specific_requirement(self, git_repo_with_stale_hash, capsys):
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

    def test_REQ_p00001_C_verify_after_update_passes(self, git_repo_with_stale_hash):
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


# ─────────────────────────────────────────────────────────────────────────────
# Test: Hash computed from raw body text (per spec)
# ─────────────────────────────────────────────────────────────────────────────


class TestHashComputedFromRawBody:
    """Tests that full-text mode hash is computed from raw body text per spec.

    Per spec/requirements-spec.md (full-text mode):
    > The hash SHALL be calculated from:
    > - every line AFTER the Header line
    > - every line BEFORE the Footer line

    These tests explicitly set hash_mode = "full-text" since the default is
    now "normalized-text". In full-text mode, the hash includes ALL body
    content (metadata, intro text, assertions).
    """

    def test_REQ_p00004_A_hash_includes_intro_text(self, tmp_path):
        """In full-text mode, hash should change when intro text changes.

        This test verifies the full-text hash is computed from raw body text,
        not just from assertion text. Requires explicit hash_mode = "full-text".
        """
        import subprocess

        from elspais.utilities.hasher import calculate_hash

        env = os.environ.copy()
        env.pop("GIT_DIR", None)
        env.pop("GIT_WORK_TREE", None)

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

        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        config = tmp_path / ".elspais.toml"
        config.write_text(
            """
[project]
name = "test"

[patterns]
prefix = "REQ"

[validation]
hash_mode = "full-text"
"""
        )

        # The body text is everything AFTER header and BEFORE footer:
        # This includes metadata line, blank lines, intro text, assertions section
        body_text = """
**Level**: PRD | **Status**: Active | **Implements**: -

This is IMPORTANT intro text that should be included in hash.

## Assertions

A. The system SHALL do something.
"""
        # Compute expected hash from body text (stripped of leading/trailing whitespace)
        expected_hash = calculate_hash(body_text.strip())

        spec_file = spec_dir / "requirements.md"
        spec_file.write_text(
            f"""# Requirements

## REQ-p00001: Test Requirement
{body_text}
*End* *Test Requirement* | **Hash**: 00000000
"""
        )

        subprocess.run(["git", "add", "."], cwd=tmp_path, env=env, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            check=True,
        )

        # Run hash update
        import argparse

        from elspais.commands.hash_cmd import run

        args = argparse.Namespace(
            hash_action="update",
            spec_dir=spec_dir,
            config=config,
            dry_run=False,
            req_id=None,
            json_output=False,
        )
        run(args)

        # Verify hash matches expected (computed from full body, not just assertions)
        content = spec_file.read_text()
        assert f"**Hash**: {expected_hash}" in content, (
            f"Expected hash {expected_hash} computed from full body text, "
            f"but got different hash in content:\n{content}"
        )

    def test_REQ_p00004_A_hash_changes_when_intro_changes(self, tmp_path):
        """In full-text mode, changing intro text should change the hash.

        If hash was computed only from assertions, changing intro text
        would NOT change the hash - this test ensures it does in full-text mode.
        Requires explicit hash_mode = "full-text".
        """
        import subprocess

        from elspais.utilities.hasher import calculate_hash

        env = os.environ.copy()
        env.pop("GIT_DIR", None)
        env.pop("GIT_WORK_TREE", None)

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

        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        config = tmp_path / ".elspais.toml"
        config.write_text(
            """
[project]
name = "test"

[patterns]
prefix = "REQ"

[validation]
hash_mode = "full-text"
"""
        )

        # Two different body texts with SAME assertions but DIFFERENT intro
        body_v1 = """
**Level**: PRD | **Status**: Active | **Implements**: -

Version ONE intro text.

## Assertions

A. The system SHALL do something.
"""
        body_v2 = """
**Level**: PRD | **Status**: Active | **Implements**: -

Version TWO intro text - CHANGED!

## Assertions

A. The system SHALL do something.
"""

        # Compute expected hashes
        hash_v1 = calculate_hash(body_v1.strip())
        hash_v2 = calculate_hash(body_v2.strip())

        # They should be different since intro text changed
        assert hash_v1 != hash_v2, "Sanity check: different body text should produce different hash"

        # Create spec file with v1 content
        spec_file = spec_dir / "requirements.md"
        spec_file.write_text(
            f"""# Requirements

## REQ-p00001: Test Requirement
{body_v1}
*End* *Test Requirement* | **Hash**: 00000000
"""
        )

        subprocess.run(["git", "add", "."], cwd=tmp_path, env=env, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            check=True,
        )

        # Run hash update to get correct hash for v1
        import argparse

        from elspais.commands.hash_cmd import run

        args = argparse.Namespace(
            hash_action="update",
            spec_dir=spec_dir,
            config=config,
            dry_run=False,
            req_id=None,
            json_output=False,
        )
        run(args)

        # Check hash matches v1
        content = spec_file.read_text()
        assert (
            f"**Hash**: {hash_v1}" in content
        ), f"After update, hash should be {hash_v1} (computed from v1 body)"

        # Now change to v2 (same assertions, different intro)
        spec_file.write_text(
            f"""# Requirements

## REQ-p00001: Test Requirement
{body_v2}
*End* *Test Requirement* | **Hash**: {hash_v1}
"""
        )

        # Run hash update again
        run(args)

        # Hash should have CHANGED because intro text changed
        content = spec_file.read_text()
        assert f"**Hash**: {hash_v2}" in content, (
            f"Hash should change to {hash_v2} when intro text changes, "
            f"even if assertions are the same. Got:\n{content}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Test: Verify hint and warning output
# ─────────────────────────────────────────────────────────────────────────────


class TestHashCommandOutput:
    """Tests for hash command user-facing output messages.

    Validates REQ-p00001-C: detect changes to requirements using content hashing.
    """

    def test_REQ_p00001_C_verify_shows_run_update_hint(self, git_repo_with_stale_hash, capsys):
        """hash verify shows 'run hash update' hint when mismatches found."""
        import argparse

        from elspais.commands.hash_cmd import run

        args = argparse.Namespace(
            hash_action="verify",
            spec_dir=git_repo_with_stale_hash / "spec",
            config=git_repo_with_stale_hash / ".elspais.toml",
            quiet=False,
        )

        result = run(args)

        # Should fail (mismatches exist)
        assert result == 1

        captured = capsys.readouterr()
        assert "hash update" in captured.err.lower() or "hash update" in captured.out.lower()
