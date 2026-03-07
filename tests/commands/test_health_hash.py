# Validates: REQ-d00085
"""Tests for check_spec_hash_integrity health check."""

from pathlib import Path

from elspais.commands.health import check_spec_hash_integrity
from elspais.graph.factory import build_graph
from elspais.utilities.hasher import compute_normalized_hash


def _make_config(tmp_path: Path) -> Path:
    config = tmp_path / ".elspais.toml"
    config.write_text(
        """[project]
name = "test-hash"

[requirements]
spec_dirs = ["spec"]

[requirements.id_pattern]
prefix = "REQ"
separator = "-"
pattern = "REQ-[a-z]\\\\d{5}"
"""
    )
    return config


def _build(tmp_path: Path, config_path: Path) -> object:
    return build_graph(
        spec_dirs=[tmp_path / "spec"],
        config_path=config_path,
        repo_root=tmp_path,
        scan_code=False,
        scan_tests=False,
        scan_sponsors=False,
    )


class TestHashIntegrity:
    """Integration tests for check_spec_hash_integrity."""

    def test_REQ_d00085_hash_correct_passes(self, tmp_path: Path):
        """Check passes when stored hash matches computed hash."""
        config_path = _make_config(tmp_path)
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        # Compute the correct hash for the assertions
        correct_hash = compute_normalized_hash([("A", "The system SHALL work.")])

        req_file = spec_dir / "requirements.md"
        req_file.write_text(
            f"""# REQ-p00001: Hash Test

**Level**: PRD | **Status**: Active

## Assertions

A. The system SHALL work.

*End* *Hash Test* | **Hash**: {correct_hash}
"""
        )

        graph = _build(tmp_path, config_path)
        result = check_spec_hash_integrity(graph)

        assert result.passed is True
        assert result.name == "spec.hash_integrity"
        assert "up to date" in result.message

    def test_REQ_d00085_hash_mismatch_fails(self, tmp_path: Path):
        """Check fails when stored hash doesn't match computed hash."""
        config_path = _make_config(tmp_path)
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        req_file = spec_dir / "requirements.md"
        req_file.write_text(
            """# REQ-p00001: Hash Test

**Level**: PRD | **Status**: Active

## Assertions

A. The system SHALL work.

*End* *Hash Test* | **Hash**: deadbeef
"""
        )

        graph = _build(tmp_path, config_path)
        result = check_spec_hash_integrity(graph)

        assert result.passed is False
        assert result.name == "spec.hash_integrity"
        assert "stale" in result.message
        assert result.details["mismatches"][0]["id"] == "REQ-p00001"
        assert result.details["mismatches"][0]["stored"] == "deadbeef"

    def test_REQ_d00085_no_hash_skipped(self, tmp_path: Path):
        """Requirements without hashes are not flagged as failures."""
        config_path = _make_config(tmp_path)
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        req_file = spec_dir / "requirements.md"
        req_file.write_text(
            """# REQ-p00001: No Hash

**Level**: PRD | **Status**: Active

## Assertions

A. The system SHALL work.

*End* *No Hash*
"""
        )

        graph = _build(tmp_path, config_path)
        result = check_spec_hash_integrity(graph)

        assert result.passed is True
        assert result.severity == "info"

    def test_REQ_d00085_empty_graph_passes(self, tmp_path: Path):
        """Empty graph (no requirements) passes."""
        config_path = _make_config(tmp_path)
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        # Empty spec file
        (spec_dir / "requirements.md").write_text("# No requirements here\n")

        graph = _build(tmp_path, config_path)
        result = check_spec_hash_integrity(graph)

        assert result.passed is True
        assert result.severity == "info"
