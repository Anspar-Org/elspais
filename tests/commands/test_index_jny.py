# Validates REQ-o00050-C
"""Tests for INDEX.md JNY section in index command.

Validates REQ-o00050-C: TraceGraphBuilder SHALL handle all relationship
linking including addresses.
"""

import argparse

from elspais.commands.index import _regenerate_index, _validate_index
from tests.core.graph_test_helpers import (
    build_graph,
    make_journey,
    make_requirement,
)


class TestIndexRegenerateJNY:
    """Tests for _regenerate_index JNY section output.

    Validates REQ-o00050-C: TraceGraphBuilder SHALL handle all relationship
    linking including addresses.
    """

    def test_REQ_o00050_C_regenerate_includes_jny_section(self, tmp_path):
        """Regenerated INDEX.md includes User Journeys (JNY) section."""
        graph = build_graph(
            make_requirement("REQ-p00012", level="PRD", title="Auth Feature"),
            make_journey(
                "JNY-Dev-01",
                title="Dev Workflow",
                actor="Developer",
                goal="Implement feature",
                addresses=["REQ-p00012"],
            ),
        )

        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        args = argparse.Namespace()

        result = _regenerate_index(graph, [spec_dir], args)

        assert result == 0
        index_content = (spec_dir / "INDEX.md").read_text()
        assert "## User Journeys (JNY)" in index_content

    def test_REQ_o00050_C_regenerate_jny_has_addresses_column(self, tmp_path):
        """Regenerated INDEX.md JNY table includes Addresses column."""
        graph = build_graph(
            make_requirement("REQ-p00012", level="PRD", title="Auth Feature"),
            make_journey(
                "JNY-Dev-01",
                title="Dev Workflow",
                actor="Developer",
                goal="Implement feature",
                addresses=["REQ-p00012"],
            ),
        )

        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        args = argparse.Namespace()

        _regenerate_index(graph, [spec_dir], args)

        index_content = (spec_dir / "INDEX.md").read_text()
        # Table header includes Addresses column
        assert "| ID | Title | Actor | File | Addresses |" in index_content
        # JNY row includes the addressed REQ
        assert "JNY-Dev-01" in index_content
        assert "REQ-p00012" in index_content

    def test_REQ_o00050_C_regenerate_jny_multiple_addresses(self, tmp_path):
        """Regenerated INDEX.md shows multiple addresses comma-separated."""
        graph = build_graph(
            make_requirement("REQ-p00012", level="PRD", title="Auth"),
            make_requirement("REQ-d00042", level="DEV", title="Login"),
            make_journey(
                "JNY-Dev-01",
                title="Multi Addr",
                actor="Developer",
                goal="Test",
                addresses=["REQ-p00012", "REQ-d00042"],
            ),
        )

        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        args = argparse.Namespace()

        _regenerate_index(graph, [spec_dir], args)

        index_content = (spec_dir / "INDEX.md").read_text()
        # Both addresses should appear in the row
        # Find the JNY row
        jny_lines = [line for line in index_content.split("\n") if "JNY-Dev-01" in line]
        assert len(jny_lines) == 1
        jny_row = jny_lines[0]
        assert "REQ-d00042" in jny_row
        assert "REQ-p00012" in jny_row

    def test_REQ_o00050_C_regenerate_no_jny_skips_section(self, tmp_path):
        """Regenerated INDEX.md omits JNY section when no journeys exist."""
        graph = build_graph(
            make_requirement("REQ-p00001", level="PRD", title="Some Req"),
        )

        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        args = argparse.Namespace()

        _regenerate_index(graph, [spec_dir], args)

        index_content = (spec_dir / "INDEX.md").read_text()
        assert "## User Journeys (JNY)" not in index_content


class TestIndexValidateJNY:
    """Tests for _validate_index JNY ID checking.

    Validates REQ-o00050-C: TraceGraphBuilder SHALL handle all relationship
    linking including addresses.
    """

    def test_REQ_o00050_C_validate_detects_missing_jny(self, tmp_path):
        """Validate detects JNY IDs in graph but missing from INDEX.md."""
        graph = build_graph(
            make_requirement("REQ-p00001", level="PRD", title="Req"),
            make_journey(
                "JNY-Dev-01",
                title="Dev Workflow",
                actor="Developer",
                goal="Test",
            ),
        )

        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        # Create INDEX.md with only requirements, no journeys
        (spec_dir / "INDEX.md").write_text(
            "# Requirements Index\n\n"
            "## Product Requirements (PRD)\n\n"
            "| ID | Title | File | Hash |\n"
            "|---|---|---|---|\n"
            "| REQ-p00001 | Req | spec/test.md | |\n"
        )

        args = argparse.Namespace()
        result = _validate_index(graph, [spec_dir], args)

        # Should return 1 indicating issues found
        assert result == 1

    def test_REQ_o00050_C_validate_passes_with_all_jnys(self, tmp_path):
        """Validate passes when all JNY IDs are present in INDEX.md."""
        graph = build_graph(
            make_requirement("REQ-p00001", level="PRD", title="Req"),
            make_journey(
                "JNY-Dev-01",
                title="Dev Workflow",
                actor="Developer",
                goal="Test",
            ),
        )

        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        # Create INDEX.md with both requirements and journeys
        (spec_dir / "INDEX.md").write_text(
            "# Requirements Index\n\n"
            "## Product Requirements (PRD)\n\n"
            "| ID | Title | File | Hash |\n"
            "|---|---|---|---|\n"
            "| REQ-p00001 | Req | spec/test.md | |\n\n"
            "## User Journeys (JNY)\n\n"
            "| ID | Title | Actor | File | Addresses |\n"
            "|---|---|---|---|---|\n"
            "| JNY-Dev-01 | Dev Workflow | Developer | spec/journeys.md | |\n"
        )

        args = argparse.Namespace()
        result = _validate_index(graph, [spec_dir], args)

        assert result == 0

    def test_REQ_o00050_C_validate_detects_extra_jny(self, tmp_path):
        """Validate detects JNY IDs in INDEX.md but not in graph."""
        graph = build_graph(
            make_requirement("REQ-p00001", level="PRD", title="Req"),
        )

        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        # Create INDEX.md with a JNY that doesn't exist in the graph
        (spec_dir / "INDEX.md").write_text(
            "# Requirements Index\n\n"
            "## Product Requirements (PRD)\n\n"
            "| ID | Title | File | Hash |\n"
            "|---|---|---|---|\n"
            "| REQ-p00001 | Req | spec/test.md | |\n\n"
            "## User Journeys (JNY)\n\n"
            "| ID | Title | Actor | File | Addresses |\n"
            "|---|---|---|---|---|\n"
            "| JNY-Ghost-01 | Ghost Journey | Ghost | spec/journeys.md | |\n"
        )

        args = argparse.Namespace()
        result = _validate_index(graph, [spec_dir], args)

        # Should return 1 indicating issues found
        assert result == 1
