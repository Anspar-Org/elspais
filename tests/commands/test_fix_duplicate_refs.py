# Verifies: REQ-p00004-A
"""Tests for fix command duplicate Implements/Refines ref deduplication."""

import argparse
import os
from pathlib import Path

SPEC_WITH_DUPLICATE_REFINES = """\
## REQ-p00001: Title

**Level**: PRD | **Status**: Draft | **Implements**: -
**Refines**: REQ-p00002
**Refines**: REQ-p00002

## Assertions

A. The system SHALL do something.

*End* *Title* | **Hash**: abcd1234
---
## REQ-p00002: Parent

**Level**: PRD | **Status**: Draft | **Implements**: -

## Assertions

A. The system SHALL allow it.

*End* *Parent* | **Hash**: 00000000
"""

CONFIG_TOML = """\
[project]
name = "test-fix-duplicate-refs"

[requirements]
spec_dirs = ["spec"]

[requirements.id_pattern]
prefix = "REQ"
separator = "-"
pattern = "REQ-[a-z]\\\\d{5}"

[changelog]
hash_current = false
"""


def _make_project(tmp_path: Path) -> Path:
    """Create a project with a spec file containing duplicate Refines refs."""
    config_path = tmp_path / ".elspais.toml"
    config_path.write_text(CONFIG_TOML)

    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()

    req_file = spec_dir / "requirements.md"
    req_file.write_text(SPEC_WITH_DUPLICATE_REFINES)

    return tmp_path


# Verifies: REQ-p00004-A
def test_fix_rewrites_file_with_duplicate_refines(tmp_path):
    """fix command rewrites files with duplicate Refines refs, leaving one clean line."""
    project = _make_project(tmp_path)

    args = argparse.Namespace(
        req_id=None,
        dry_run=False,
        spec_dir=None,
        config=project / ".elspais.toml",
        canonical_root=None,
        git_root=project,
        verbose=False,
        quiet=False,
        message=None,
    )

    from elspais.commands import fix_cmd

    old_cwd = os.getcwd()
    os.chdir(project)
    try:
        fix_cmd.run(args)
    finally:
        os.chdir(old_cwd)

    spec_file = project / "spec" / "requirements.md"
    content = spec_file.read_text()

    refines_lines = [line for line in content.splitlines() if "**Refines**:" in line]
    assert (
        len(refines_lines) == 1
    ), f"Expected exactly one **Refines**: line, got {len(refines_lines)}: {refines_lines}"
    assert (
        "REQ-p00002" in refines_lines[0]
    ), f"Expected **Refines**: REQ-p00002 but got: {refines_lines[0]}"
