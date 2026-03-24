# Verifies: REQ-d00210
"""Tests for docs drift detection in elspais doctor.

Validates REQ-d00210-A: doctor includes docs.config_drift health check
Validates REQ-d00210-B: reports undocumented and stale sections
Validates REQ-d00210-C: passes when all documented, fails otherwise
"""
from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from elspais.commands.health import HealthCheck

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# The schema sections we expect check_docs_drift to use (alias names,
# excluding conditional sections: associates).
# "version" is a top-level scalar, not a table, but should be included.
EXPECTED_SCHEMA_SECTIONS = {
    "version",
    "project",
    "id-patterns",
    "levels",
    "scanning",
    "rules",
    "keywords",
    "validation",
    "changelog",
    "terms",
    "output",
    "stats",
    "cli_ttl",
}


def _make_docs_with_sections(tmp_path: Path, sections: set[str]) -> Path:
    """Create a minimal configuration.md with TOML code blocks for given sections."""
    blocks = "\n".join(f"[{s}]" for s in sorted(sections))
    content = dedent(
        f"""\
        # Configuration Reference

        ```toml
        {blocks}
        ```
    """
    )
    docs_path = tmp_path / "configuration.md"
    docs_path.write_text(content, encoding="utf-8")
    return docs_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDocsDriftBasic:
    """Validates REQ-d00210-A: doctor includes docs.config_drift health check."""

    def test_REQ_d00210_A_returns_health_check(self, tmp_path: Path) -> None:
        """check_docs_drift returns a HealthCheck with correct name and category."""
        from elspais.commands.doctor import check_docs_drift

        docs_path = _make_docs_with_sections(tmp_path, EXPECTED_SCHEMA_SECTIONS)
        result = check_docs_drift(docs_path)

        assert isinstance(result, HealthCheck)
        assert result.name == "docs.config_drift"
        assert result.category == "docs"

    def test_REQ_d00210_A_function_is_importable(self) -> None:
        """check_docs_drift is importable from elspais.commands.doctor."""
        from elspais.commands.doctor import check_docs_drift

        assert callable(check_docs_drift)


class TestDocsDriftPassFail:
    """Validates REQ-d00210-C: passes when all documented, fails otherwise."""

    def test_REQ_d00210_C_pass_when_all_sections_documented(self, tmp_path: Path) -> None:
        """Returns passed=True when docs file has all schema sections."""
        from elspais.commands.doctor import check_docs_drift

        docs_path = _make_docs_with_sections(tmp_path, EXPECTED_SCHEMA_SECTIONS)
        result = check_docs_drift(docs_path)

        assert result.passed is True

    def test_REQ_d00210_C_fail_when_sections_missing(self, tmp_path: Path) -> None:
        """Returns passed=False when docs file is missing schema sections."""
        from elspais.commands.doctor import check_docs_drift

        # Remove a few sections from the docs
        incomplete = EXPECTED_SCHEMA_SECTIONS - {"output", "changelog", "validation"}
        docs_path = _make_docs_with_sections(tmp_path, incomplete)
        result = check_docs_drift(docs_path)

        assert result.passed is False

    def test_REQ_d00210_C_fail_when_stale_sections_present(self, tmp_path: Path) -> None:
        """Returns passed=False when docs has sections not in schema."""
        from elspais.commands.doctor import check_docs_drift

        extra = EXPECTED_SCHEMA_SECTIONS | {"hooks", "index"}
        docs_path = _make_docs_with_sections(tmp_path, extra)
        result = check_docs_drift(docs_path)

        assert result.passed is False

    def test_REQ_d00210_C_docs_file_missing(self, tmp_path: Path) -> None:
        """Handles missing docs file gracefully (passed=False or severity=info)."""
        from elspais.commands.doctor import check_docs_drift

        missing_path = tmp_path / "nonexistent.md"
        result = check_docs_drift(missing_path)

        assert isinstance(result, HealthCheck)
        assert result.name == "docs.config_drift"
        # Either fails or reports as info-severity skip
        assert not result.passed or result.severity == "info"


class TestDocsDriftDetails:
    """Validates REQ-d00210-B: reports undocumented and stale sections."""

    def test_REQ_d00210_B_undocumented_sections_listed(self, tmp_path: Path) -> None:
        """Details include 'undocumented' key listing sections in schema but not docs."""
        from elspais.commands.doctor import check_docs_drift

        missing = {"output", "changelog", "validation"}
        incomplete = EXPECTED_SCHEMA_SECTIONS - missing
        docs_path = _make_docs_with_sections(tmp_path, incomplete)
        result = check_docs_drift(docs_path)

        assert result.passed is False
        assert "undocumented" in result.details
        undocumented = set(result.details["undocumented"])
        assert missing <= undocumented, f"Expected {missing} in undocumented, got {undocumented}"

    def test_REQ_d00210_B_stale_sections_listed(self, tmp_path: Path) -> None:
        """Details include 'stale' key listing sections in docs but not schema."""
        from elspais.commands.doctor import check_docs_drift

        stale = {"hooks", "index"}
        extra = EXPECTED_SCHEMA_SECTIONS | stale
        docs_path = _make_docs_with_sections(tmp_path, extra)
        result = check_docs_drift(docs_path)

        assert result.passed is False
        assert "stale" in result.details
        stale_found = set(result.details["stale"])
        assert stale <= stale_found, f"Expected {stale} in stale, got {stale_found}"

    def test_REQ_d00210_B_both_undocumented_and_stale(self, tmp_path: Path) -> None:
        """When both undocumented and stale exist, both are reported."""
        from elspais.commands.doctor import check_docs_drift

        # Remove 'output', add 'hooks'
        sections = (EXPECTED_SCHEMA_SECTIONS - {"output"}) | {"hooks"}
        docs_path = _make_docs_with_sections(tmp_path, sections)
        result = check_docs_drift(docs_path)

        assert result.passed is False
        assert "undocumented" in result.details
        assert "stale" in result.details
        assert "output" in result.details["undocumented"]
        assert "hooks" in result.details["stale"]

    def test_REQ_d00210_B_no_drift_has_empty_or_absent_details(self, tmp_path: Path) -> None:
        """When no drift, details should not have undocumented/stale or they're empty."""
        from elspais.commands.doctor import check_docs_drift

        docs_path = _make_docs_with_sections(tmp_path, EXPECTED_SCHEMA_SECTIONS)
        result = check_docs_drift(docs_path)

        assert result.passed is True
        # Either no details or empty lists
        if "undocumented" in result.details:
            assert result.details["undocumented"] == []
        if "stale" in result.details:
            assert result.details["stale"] == []


class TestDocsDriftRealFile:
    """Validates REQ-d00210-B: detects actual drift in the real docs/configuration.md."""

    def test_REQ_d00210_B_real_configuration_md_in_sync(self) -> None:
        """The real docs/configuration.md should be in sync with schema."""
        from elspais.commands.doctor import check_docs_drift

        real_docs = Path(__file__).resolve().parents[2] / "docs" / "configuration.md"
        if not real_docs.exists():
            pytest.skip("docs/configuration.md not found in repo")

        result = check_docs_drift(real_docs)

        assert result.passed is True, f"Docs drift detected: {result.message}"


class TestDocsDriftExcludesConditional:
    """Validates REQ-d00210-B: conditional sections are excluded from comparison."""

    def test_REQ_d00210_B_associates_not_required(self, tmp_path: Path) -> None:
        """'associates' section should not be required in docs."""
        from elspais.commands.doctor import check_docs_drift

        # Docs have all required sections but NOT associates
        docs_path = _make_docs_with_sections(tmp_path, EXPECTED_SCHEMA_SECTIONS)
        result = check_docs_drift(docs_path)

        assert result.passed is True
        # If undocumented is present, it should not contain excluded sections
        if "undocumented" in result.details:
            for excluded in ("associates",):
                assert excluded not in result.details["undocumented"]

    def test_REQ_d00210_B_sub_sections_not_counted_as_top_level(self, tmp_path: Path) -> None:
        """Sub-table headers like [rules.hierarchy] should not be treated as top-level."""
        from elspais.commands.doctor import check_docs_drift

        # Include a sub-section in docs that shouldn't be flagged as stale
        sections_with_sub = EXPECTED_SCHEMA_SECTIONS | {"rules.hierarchy", "rules.naming"}
        docs_path = _make_docs_with_sections(tmp_path, sections_with_sub)
        result = check_docs_drift(docs_path)

        # Sub-sections should not appear as stale top-level sections
        if "stale" in result.details:
            stale = result.details["stale"]
            assert "rules.hierarchy" not in stale
            assert "rules.naming" not in stale
