# Verifies: REQ-d00085
"""Tests for check_spec_index_current health check."""

from pathlib import Path

from elspais.commands.health import check_spec_index_current
from elspais.graph.factory import build_graph


def _make_project(tmp_path: Path, index_content: str | None = None) -> tuple:
    """Create a project with config, spec, and optional INDEX.md.

    Returns (graph, spec_dirs).
    """
    config_path = tmp_path / ".elspais.toml"
    config_path.write_text(
        """[project]
name = "test-index"

[requirements]
spec_dirs = ["spec"]

[requirements.id_pattern]
prefix = "REQ"
separator = "-"
pattern = "REQ-[a-z]\\\\d{5}"
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

    graph = build_graph(
        spec_dirs=[spec_dir],
        config_path=config_path,
        repo_root=tmp_path,
        scan_code=False,
        scan_tests=False,
    )

    return graph, [spec_dir]


class TestIndexCurrent:
    """Integration tests for check_spec_index_current."""

    def test_REQ_d00085_index_up_to_date(self, tmp_path: Path):
        """Check passes when INDEX.md has all requirement IDs."""
        index_content = """\
# Requirements Index

| ID | Title |
|----|-------|
| REQ-p00001 | First Requirement |
| REQ-p00002 | Second Requirement |
"""
        graph, spec_dirs = _make_project(tmp_path, index_content)
        result = check_spec_index_current(graph, spec_dirs)

        assert result.passed is True
        assert result.name == "spec.index_current"
        assert "up to date" in result.message

    def test_REQ_d00085_index_missing_requirement(self, tmp_path: Path):
        """Check fails when INDEX.md is missing a requirement."""
        index_content = """\
# Requirements Index

| ID | Title |
|----|-------|
| REQ-p00001 | First Requirement |
"""
        graph, spec_dirs = _make_project(tmp_path, index_content)
        result = check_spec_index_current(graph, spec_dirs)

        assert result.passed is False
        assert "stale" in result.message
        assert "REQ-p00002" in result.details["missing_reqs"]

    def test_REQ_d00085_index_extra_requirement(self, tmp_path: Path):
        """Check fails when INDEX.md has an ID not in the graph."""
        index_content = """\
# Requirements Index

| ID | Title |
|----|-------|
| REQ-p00001 | First Requirement |
| REQ-p00002 | Second Requirement |
| REQ-p00099 | Ghost Requirement |
"""
        graph, spec_dirs = _make_project(tmp_path, index_content)
        result = check_spec_index_current(graph, spec_dirs)

        assert result.passed is False
        assert "stale" in result.message
        assert "REQ-p00099" in result.details["extra_reqs"]

    def test_REQ_d00085_no_index_passes(self, tmp_path: Path):
        """Check passes with info when no INDEX.md exists."""
        graph, spec_dirs = _make_project(tmp_path, index_content=None)
        result = check_spec_index_current(graph, spec_dirs)

        assert result.passed is True
        assert result.severity == "info"
        assert "No INDEX.md" in result.message
