# Verifies: REQ-p00004-A
"""Tests for fix command INDEX.md regeneration."""

import re
from pathlib import Path


def _make_project(tmp_path: Path, index_content: str | None = None) -> Path:
    """Create a project with config, spec, and optional INDEX.md."""
    config_path = tmp_path / ".elspais.toml"
    config_path.write_text(
        """version = 3

[project]
name = "test-fix-index"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]
"""
    )

    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()

    req_file = spec_dir / "requirements.md"
    req_file.write_text(
        """# REQ-p00001: First Requirement

**Level**: PRD | **Status**: Active

## Assertions

A. The system SHALL do something.

*End* *First Requirement* | **Hash**: abcd1234

# REQ-p00002: Second Requirement

**Level**: PRD | **Status**: Active

## Assertions

A. The system SHALL do another thing.

*End* *Second Requirement* | **Hash**: efgh5678
"""
    )

    if index_content is not None:
        (spec_dir / "INDEX.md").write_text(index_content)

    return tmp_path


class TestFixIndex:
    """Integration tests for fix command INDEX.md regeneration."""

    def test_REQ_p00004_A_fix_regenerates_stale_index(self, tmp_path: Path):
        """Fix regenerates INDEX.md when it's missing requirements."""
        import argparse
        import os

        project = _make_project(
            tmp_path,
            index_content="| REQ-p00001 | First |\n",
        )

        from elspais.commands.fix_cmd import _fix_index

        args = argparse.Namespace(
            spec_dir=None,
            config=project / ".elspais.toml",
            git_root=project,
        )

        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            _fix_index(args, dry_run=False)
        finally:
            os.chdir(old_cwd)

        index_path = project / "spec" / "INDEX.md"
        content = index_path.read_text()
        ids = set(re.findall(r"REQ-p\d{5}", content))
        assert "REQ-p00001" in ids
        assert "REQ-p00002" in ids

    def test_REQ_p00004_A_fix_dry_run_no_modify(self, tmp_path: Path):
        """Fix with --dry-run doesn't modify INDEX.md."""
        import argparse
        import os

        original_content = "| REQ-p00001 | First |\n"
        project = _make_project(tmp_path, index_content=original_content)

        from elspais.commands.fix_cmd import _fix_index

        args = argparse.Namespace(
            spec_dir=None,
            config=project / ".elspais.toml",
            git_root=project,
        )

        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            _fix_index(args, dry_run=True)
        finally:
            os.chdir(old_cwd)

        index_path = project / "spec" / "INDEX.md"
        assert index_path.read_text() == original_content

    def test_REQ_p00004_A_fix_creates_missing_index(self, tmp_path: Path):
        """Fix creates INDEX.md when it doesn't exist."""
        import argparse
        import os

        project = _make_project(tmp_path, index_content=None)

        from elspais.commands.fix_cmd import _fix_index

        args = argparse.Namespace(
            spec_dir=None,
            config=project / ".elspais.toml",
            git_root=project,
        )

        index_path = project / "spec" / "INDEX.md"
        assert not index_path.exists()

        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            _fix_index(args, dry_run=False)
        finally:
            os.chdir(old_cwd)

        assert index_path.exists()
        content = index_path.read_text()
        ids = set(re.findall(r"REQ-p\d{5}", content))
        assert "REQ-p00001" in ids
        assert "REQ-p00002" in ids
