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
import subprocess
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

    # Init git repo with author config so get_author_info works in CI
    env = {**os.environ, "GIT_DIR": "", "GIT_WORK_TREE": ""}
    env.pop("GIT_DIR", None)
    env.pop("GIT_WORK_TREE", None)
    subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, env=env, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"], cwd=tmp_path, env=env, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"], cwd=tmp_path, env=env, capture_output=True
    )
    subprocess.run(["git", "add", "."], cwd=tmp_path, env=env, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, env=env, capture_output=True)

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


# ─────────────────────────────────────────────────────────────────────────────
# Bug 1: Active REQ error message doesn't explain why
# ─────────────────────────────────────────────────────────────────────────────


class TestFixActiveChangelogAutoMessage:
    """Tests for fix command auto-generated changelog with enforcement.

    Validates that auto-fixes generate changelog entries automatically
    when no -m flag is provided, rather than failing.
    """

    def test_REQ_p00004_A_autofix_generates_changelog(self, tmp_path, capsys):
        """When an Active requirement needs a hash update and no -m message
        is provided, the fix should succeed with an auto-generated reason.
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

        assert result == 0, "Auto-fix should succeed with auto-generated reason"

        spec_file = project / "spec" / "requirements.md"
        content = spec_file.read_text()
        assert "## Changelog" in content, "Changelog section should be added"
        assert "Auto-fix:" in content, "Auto-generated reason should be present"

    def test_REQ_p00004_A_explicit_message_overrides_autofix(self, tmp_path, capsys):
        """When -m is provided, it overrides the auto-generated reason."""
        project = _make_project(tmp_path, REQ_ACTIVE_WRONG_HASH)
        args = _make_fix_args(project, "REQ-d00001")
        args.message = "Manual update reason"

        from elspais.commands.fix_cmd import run

        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            result = run(args)
        finally:
            os.chdir(old_cwd)

        assert result == 0

        spec_file = project / "spec" / "requirements.md"
        content = spec_file.read_text()
        assert "Manual update reason" in content
