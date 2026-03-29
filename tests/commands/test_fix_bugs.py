# Validates: REQ-p00004-A, REQ-p00002-C
"""Tests for fix command bugs with changelog enforcement.

Bug 1: Active REQ error message should explain why a changelog message
is required (hash_current enabled, Draft/Deprecated update without message).

Bug 3: Global fix mode should DEFER Active REQs with changelog enforcement
rather than silently fixing them.

Tests REQ-p00004-A: fix command error messaging for changelog enforcement
Tests REQ-p00002-C: validate --fix defers Active REQs needing changelog
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ─────────────────────────────────────────────────────────────────────────────

CONFIG_TOML = """\
version = 3

[project]
name = "test"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[changelog]
hash_current = true
"""

# Active requirement with assertions (so it has hashable content)
# but a WRONG stored hash to trigger a mismatch.
REQ_ACTIVE_WRONG_HASH = """\
# REQ-d00001: Active Requirement

**Level**: DEV | **Status**: Active | **Implements**: -

Some body text here.

## Assertions

A. The system shall do something important.

B. The system shall do something else.

*End* *Active Requirement* | **Hash**: deadbeef
---
"""


def _make_project(
    tmp_path: Path,
    req_content: str,
    config_toml: str = CONFIG_TOML,
    filename: str = "requirements.md",
) -> Path:
    """Create a minimal project with config and a single spec file."""
    config_path = tmp_path / ".elspais.toml"
    config_path.write_text(config_toml)

    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()

    req_file = spec_dir / filename
    req_file.write_text(req_content)

    return tmp_path


def _make_fix_args(
    project: Path,
    req_id: str,
    *,
    dry_run: bool = False,
    message: str | None = None,
) -> argparse.Namespace:
    """Build an argparse.Namespace matching what fix_cmd.run expects."""
    return argparse.Namespace(
        req_id=req_id,
        dry_run=dry_run,
        spec_dir=project / "spec",
        config=project / ".elspais.toml",
        verbose=False,
        quiet=False,
        message=message,
    )


def _make_validate_args(
    project: Path,
    *,
    fix: bool = False,
    dry_run: bool = False,
    json_output: bool = False,
) -> argparse.Namespace:
    """Build an argparse.Namespace matching what validate.run expects."""
    return argparse.Namespace(
        spec_dir=project / "spec",
        config=project / ".elspais.toml",
        fix=fix,
        dry_run=dry_run,
        skip_rule=None,
        json=json_output,
        quiet=False,
        export=False,
        mode="combined",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Bug 1: Active REQ error message doesn't explain why
# ─────────────────────────────────────────────────────────────────────────────


class TestFixActiveChangelogErrorMessage:
    """Tests for fix command error messaging with changelog enforcement.

    Validates REQ-p00004-A: fix command explains why a changelog message
    is required for Active requirements.
    """

    def test_REQ_p00004_A_error_mentions_hash_current(self, tmp_path, capsys):
        """When an Active requirement needs a hash update and no -m message
        is provided, the error should mention 'hash_current' to explain
        why a message is required.
        """
        project = _make_project(tmp_path, REQ_ACTIVE_WRONG_HASH)
        args = _make_fix_args(project, "REQ-d00001")

        from elspais.commands.fix_cmd import run

        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            result = run(args)
        finally:
            os.chdir(old_cwd)

        assert result == 1, "Should fail when no changelog message provided"

        captured = capsys.readouterr()
        assert (
            "hash_current" in captured.err
        ), f"Error should mention 'hash_current' config option, got: {captured.err!r}"

    def test_REQ_p00004_A_error_mentions_draft_deprecated(self, tmp_path, capsys):
        """When an Active requirement needs a hash update and no -m message
        is provided, the error should mention that Draft/Deprecated
        requirements update without a message.
        """
        project = _make_project(tmp_path, REQ_ACTIVE_WRONG_HASH)
        args = _make_fix_args(project, "REQ-d00001")

        from elspais.commands.fix_cmd import run

        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            result = run(args)
        finally:
            os.chdir(old_cwd)

        assert result == 1, "Should fail when no changelog message provided"

        captured = capsys.readouterr()
        assert (
            "Draft/Deprecated" in captured.err
        ), f"Error should mention 'Draft/Deprecated', got: {captured.err!r}"


# ─────────────────────────────────────────────────────────────────────────────
# Bug 3: Global fix mode defers Active REQs with changelog enforcement
# ─────────────────────────────────────────────────────────────────────────────


class TestValidateFixDefersActiveChangelog:
    """Tests for validate --fix deferring Active REQs needing changelog.

    Validates REQ-p00002-C: global fix mode defers Active requirements
    with hash mismatches when changelog enforcement is on.
    """

    def test_REQ_p00002_C_deferred_section_in_output(self, tmp_path, capsys):
        """When running validate with fix=True and an Active requirement
        has a hash mismatch with changelog enforcement, the output should
        show a DEFERRED section.
        """
        project = _make_project(tmp_path, REQ_ACTIVE_WRONG_HASH)
        args = _make_validate_args(project, fix=True)

        from elspais.commands.validate import run

        run(args)

        captured = capsys.readouterr()
        assert (
            "DEFERRED" in captured.err
        ), f"Output should contain 'DEFERRED' section, got stderr: {captured.err!r}"

    def test_REQ_p00002_C_deferred_shows_per_req_command(self, tmp_path, capsys):
        """The DEFERRED output should show per-REQ fix commands with -m flag."""
        project = _make_project(tmp_path, REQ_ACTIVE_WRONG_HASH)
        args = _make_validate_args(project, fix=True)

        from elspais.commands.validate import run

        run(args)

        captured = capsys.readouterr()
        assert (
            "elspais fix REQ-d00001 -m" in captured.err
        ), f"Output should show per-REQ fix command, got stderr: {captured.err!r}"

    def test_REQ_p00002_C_deferred_does_not_change_hash(self, tmp_path, capsys):
        """When a hash mismatch is deferred, the file should NOT be modified."""
        project = _make_project(tmp_path, REQ_ACTIVE_WRONG_HASH)
        args = _make_validate_args(project, fix=True)

        spec_file = project / "spec" / "requirements.md"
        original_content = spec_file.read_text()

        from elspais.commands.validate import run

        run(args)

        after_content = spec_file.read_text()
        assert (
            after_content == original_content
        ), "File should not be modified when hash fix is deferred"

    def test_REQ_p00002_C_deferred_in_json_output(self, tmp_path, capsys):
        """The JSON output should include a 'deferred' array with the
        deferred issue details.
        """
        import json
        from io import StringIO
        from unittest.mock import patch

        project = _make_project(tmp_path, REQ_ACTIVE_WRONG_HASH)
        args = _make_validate_args(project, fix=True, json_output=True)

        captured_stdout = StringIO()
        with patch("sys.stdout", captured_stdout):
            from elspais.commands.validate import run

            run(args)

        output = json.loads(captured_stdout.getvalue())
        assert "deferred" in output, "JSON output should have 'deferred' key"
        assert (
            len(output["deferred"]) >= 1
        ), f"Should have at least 1 deferred issue, got: {output['deferred']}"

        deferred_ids = [d["id"] for d in output["deferred"]]
        assert (
            "REQ-d00001" in deferred_ids
        ), f"REQ-d00001 should be in deferred list, got: {deferred_ids}"
