# Validates REQ-p00001-C, REQ-p00004-A
"""Tests for elspais fix command (hash update functionality).

Tests REQ-p00001-C: detect changes to requirements using content hashing.
Tests REQ-p00004-A: compute and verify content hashes for change detection.

The fix command updates requirement hashes in spec files:
- elspais fix: Fix all stale hashes (delegates to validate --fix)
- elspais fix REQ-xxx: Fix specific requirement hash
- --dry-run: Show changes without applying
"""

import os
import subprocess
from unittest.mock import patch

import pytest

_MOCK_AUTHOR = {"name": "Test User", "id": "test@test.org"}


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
version = 5

[project]
name = "test-project"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[changelog]
hash_current = false
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

    # Verifies: REQ-p00004-A
    def test_REQ_p00004_A_updates_hash_in_file(self, git_repo_with_stale_hash):
        """Update a hash value in a spec file."""
        from elspais.utilities.spec_writer import update_hash_in_file

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

    # Verifies: REQ-p00004-A
    def test_REQ_p00004_A_returns_error_when_req_not_found(self, git_repo_with_stale_hash):
        """Return descriptive error when requirement is not found in file."""
        from elspais.utilities.spec_writer import update_hash_in_file

        spec_file = git_repo_with_stale_hash / "spec" / "requirements.md"

        result = update_hash_in_file(
            file_path=spec_file,
            req_id="REQ-NONEXISTENT",
            new_hash="abcd1234",
        )

        assert result is not None
        assert "REQ-NONEXISTENT" in result
        assert "not found" in result

    # Verifies: REQ-p00004-A
    def test_REQ_p00004_A_handles_different_title_formats(self, tmp_path):
        """Handle various title formats in the End marker."""
        from elspais.utilities.spec_writer import update_hash_in_file

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

    # Verifies: REQ-p00004-A
    def test_REQ_p00004_A_returns_error_when_no_end_marker(self, tmp_path):
        """Return descriptive error when requirement has no End marker."""
        from elspais.utilities.spec_writer import update_hash_in_file

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

    # Verifies: REQ-p00004-A
    def test_REQ_p00004_A_returns_error_when_end_marker_belongs_to_other_req(self, tmp_path):
        """Return error when End marker is past the next requirement header."""
        from elspais.utilities.spec_writer import update_hash_in_file

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

    # Verifies: REQ-p00004-A
    @pytest.mark.parametrize(
        "placeholder",
        ["XXXXXXXX", "TODO", "________", "PLACEHOLDER", "TBD"],
        ids=["x-placeholder", "todo", "underscore", "placeholder-word", "tbd"],
    )
    def test_REQ_p00004_A_updates_placeholder_hashes(self, tmp_path, placeholder):
        """Placeholder hash values (XXXXXXXX, TODO, ________) are matched and replaced."""
        from elspais.utilities.spec_writer import update_hash_in_file

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
# Test: fix command implementation
# ─────────────────────────────────────────────────────────────────────────────


class TestUpdateHashesCommand:
    """Tests for the fix command.

    Validates REQ-p00001-C: detect changes to requirements using content hashing.
    """

    # Verifies: REQ-p00001-C
    def test_REQ_p00001_C_dry_run_shows_changes(self, git_repo_with_stale_hash, capsys):
        """--dry-run shows what would be changed but doesn't modify files."""
        import argparse

        from elspais.commands.fix_cmd import run

        args = argparse.Namespace(
            req_id=None,
            dry_run=True,
            spec_dir=git_repo_with_stale_hash / "spec",
            config=git_repo_with_stale_hash / ".elspais.toml",
            quiet=False,
            verbose=False,
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

    # Verifies: REQ-p00001-C
    def test_REQ_p00001_C_updates_all_stale_hashes(self, git_repo_with_stale_hash, capsys):
        """Update all stale hashes in spec files."""
        import argparse

        from elspais.commands.fix_cmd import run

        args = argparse.Namespace(
            req_id=None,
            dry_run=False,
            spec_dir=git_repo_with_stale_hash / "spec",
            config=git_repo_with_stale_hash / ".elspais.toml",
            quiet=False,
            verbose=False,
        )

        result = run(args)

        assert result == 0

        # Verify hashes were updated
        spec_file = git_repo_with_stale_hash / "spec" / "requirements.md"
        content = spec_file.read_text()
        # Old hashes should be replaced
        assert "deadbeef" not in content
        assert "00000000" not in content

    # Verifies: REQ-p00001-C, REQ-d00330-C
    @patch("elspais.utilities.git.get_author_info", return_value=_MOCK_AUTHOR)
    def test_REQ_p00001_C_updates_specific_requirement(
        self, mock_author, git_repo_with_stale_hash, capsys
    ):
        """Update hash for a specific requirement only."""
        import argparse

        from elspais.commands.fix_cmd import run

        args = argparse.Namespace(
            req_id="REQ-p00001",
            dry_run=False,
            spec_dir=git_repo_with_stale_hash / "spec",
            config=git_repo_with_stale_hash / ".elspais.toml",
            message="Hash update",
        )

        result = run(args)

        assert result == 0

        # The named requirement is fixed and its neighbour is left as written.
        spec_file = git_repo_with_stale_hash / "spec" / "requirements.md"
        content = spec_file.read_text()
        assert "deadbeef" not in content  # REQ-p00001 stale hash replaced
        assert "00000000" in content  # REQ-p00002 is not the named requirement


# ─────────────────────────────────────────────────────────────────────────────
# Test: Hash covers the Assertions alone, not the requirement's prose
# ─────────────────────────────────────────────────────────────────────────────


_PROSE_CONFIG = """
version = 5

[project]
name = "test"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[changelog]
hash_current = false
"""

_ASSERTION_TEXT = "The system SHALL do something."


def _prose_spec(intro: str, rationale: str, stored_hash: str) -> str:
    """One requirement with the given intro prose and Rationale section."""
    return f"""# Requirements

## REQ-p00001: Test Requirement

**Level**: PRD | **Status**: Active | **Implements**: -

{intro}

## Assertions

A. {_ASSERTION_TEXT}

## Rationale

{rationale}

*End* *Test Requirement* | **Hash**: {stored_hash}
"""


class TestHashIgnoresProse:
    """`elspais fix` writes the digest of the Assertions alone, so editing a
    requirement's intro prose or Rationale leaves its stored hash in place."""

    @staticmethod
    def _fix_args(project):
        import argparse

        return argparse.Namespace(
            req_id=None,
            dry_run=False,
            spec_dir=project / "spec",
            config=project / ".elspais.toml",
            quiet=False,
            verbose=False,
        )

    # Verifies: REQ-d00131-S
    def test_REQ_d00131_S_prose_edit_leaves_hash_unmoved(self, tmp_path):
        """After a prose-only edit, fix keeps the hash and finds nothing to fix."""
        from elspais.commands.fix_cmd import _detect_fixable, run
        from elspais.graph import NodeKind
        from elspais.graph.factory import build_graph
        from elspais.utilities.hasher import compute_normalized_hash

        env = _clean_git_env()
        for cmd in (
            ["git", "init", "-b", "main"],
            ["git", "config", "user.email", "test@test.com"],
            ["git", "config", "user.name", "Test"],
        ):
            subprocess.run(cmd, cwd=tmp_path, env=env, capture_output=True, check=True)

        (tmp_path / ".elspais.toml").write_text(_PROSE_CONFIG)
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        spec_file = spec_dir / "requirements.md"
        spec_file.write_text(_prose_spec("Version ONE intro.", "Reason one.", "00000000"))
        subprocess.run(["git", "add", "."], cwd=tmp_path, env=env, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "init"], cwd=tmp_path, env=env, capture_output=True, check=True
        )

        assertion_hash = compute_normalized_hash([("A", _ASSERTION_TEXT)])
        run(self._fix_args(tmp_path))
        assert f"**Hash**: {assertion_hash}" in spec_file.read_text()

        # Rewrite the intro and the Rationale; the Assertion is untouched.
        spec_file.write_text(
            _prose_spec("Version TWO intro - CHANGED!", "A wholly new reason.", assertion_hash)
        )

        graph = build_graph(
            spec_dirs=[spec_dir],
            config_path=tmp_path / ".elspais.toml",
            repo_root=tmp_path,
            scan_code=False,
            scan_tests=False,
        )
        node = next(n for n in graph.nodes_by_kind(NodeKind.REQUIREMENT) if n.id == "REQ-p00001")
        assert "hash_mismatch" not in _detect_fixable(node, changelog_enforce=False)

        run(self._fix_args(tmp_path))
        content = spec_file.read_text()
        assert "Version TWO intro - CHANGED!" in content
        assert f"**Hash**: {assertion_hash}" in content, (
            f"A prose-only edit must not move the hash from {assertion_hash}; got:\n{content}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Test: Validate hint output
# ─────────────────────────────────────────────────────────────────────────────
