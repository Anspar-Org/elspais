# Validates REQ-o00050-C
"""Tests for INDEX.md JNY section in index command.

Validates REQ-o00050-C: TraceGraphBuilder SHALL handle all relationship
linking including validates.
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
    linking including validates.
    """

    def test_REQ_o00050_C_regenerate_includes_jny_section(self, tmp_path):
        """Regenerated INDEX.md includes User Journeys subsection."""
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        graph = build_graph(
            make_requirement(
                "REQ-p00012",
                level="PRD",
                title="Auth Feature",
                source_path=str(spec_dir / "reqs.md"),
            ),
            make_journey(
                "JNY-Dev-01",
                title="Dev Workflow",
                actor="Developer",
                goal="Implement feature",
                validates=["REQ-p00012"],
                source_path=str(spec_dir / "journeys.md"),
            ),
        )
        args = argparse.Namespace(git_root=tmp_path)

        result = _regenerate_index(graph, [spec_dir], args)

        assert result == 0
        index_content = (spec_dir / "INDEX.md").read_text()
        assert "## User Journeys" in index_content

    def test_REQ_o00050_C_regenerate_jny_has_expected_columns(self, tmp_path):
        """Regenerated INDEX.md JNY table includes ID, Title, Actor, File columns."""
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        graph = build_graph(
            make_requirement(
                "REQ-p00012",
                level="PRD",
                title="Auth Feature",
                source_path=str(spec_dir / "reqs.md"),
            ),
            make_journey(
                "JNY-Dev-01",
                title="Dev Workflow",
                actor="Developer",
                goal="Implement feature",
                validates=["REQ-p00012"],
                source_path=str(spec_dir / "journeys.md"),
            ),
        )
        args = argparse.Namespace(git_root=tmp_path)

        _regenerate_index(graph, [spec_dir], args)

        index_content = (spec_dir / "INDEX.md").read_text()
        header_lines = [
            line for line in index_content.split("\n") if line.startswith("|") and "Actor" in line
        ]
        assert len(header_lines) >= 1
        header = header_lines[0]
        for col in ("ID", "Title", "Actor", "File"):
            assert col in header
        assert "Addresses" not in header
        assert "JNY-Dev-01" in index_content

    def test_REQ_o00050_C_regenerate_jny_row_has_actor_and_file(self, tmp_path):
        """Regenerated INDEX.md JNY row includes actor and file columns."""
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        graph = build_graph(
            make_requirement(
                "REQ-p00012",
                level="PRD",
                title="Auth",
                source_path=str(spec_dir / "reqs.md"),
            ),
            make_journey(
                "JNY-Dev-01",
                title="Multi Addr",
                actor="Developer",
                goal="Test",
                validates=["REQ-p00012"],
                source_path=str(spec_dir / "journeys.md"),
            ),
        )
        args = argparse.Namespace(git_root=tmp_path)

        _regenerate_index(graph, [spec_dir], args)

        index_content = (spec_dir / "INDEX.md").read_text()
        jny_lines = [line for line in index_content.split("\n") if "JNY-Dev-01" in line]
        assert len(jny_lines) == 1
        jny_row = jny_lines[0]
        assert "Developer" in jny_row
        assert "journeys.md" in jny_row

    def test_REQ_o00050_C_regenerate_no_jny_skips_section(self, tmp_path):
        """Regenerated INDEX.md omits JNY section when no journeys exist."""
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        graph = build_graph(
            make_requirement(
                "REQ-p00001",
                level="PRD",
                title="Some Req",
                source_path=str(spec_dir / "reqs.md"),
            ),
        )
        args = argparse.Namespace(git_root=tmp_path)

        _regenerate_index(graph, [spec_dir], args)

        index_content = (spec_dir / "INDEX.md").read_text()
        assert "## User Journeys" not in index_content


class TestIndexValidateJNY:
    """Tests for _validate_index JNY ID checking.

    Validates REQ-o00050-C: TraceGraphBuilder SHALL handle all relationship
    linking including validates.
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
        (spec_dir / "INDEX.md").write_text(
            "# Requirements Index\n\n"
            "## Product Requirements (PRD)\n\n"
            "| ID | Title | File | Hash |\n"
            "|---|---|---|---|\n"
            "| REQ-p00001 | Req | spec/test.md | |\n"
        )

        args = argparse.Namespace()
        result = _validate_index(graph, [spec_dir], args)

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
        (spec_dir / "INDEX.md").write_text(
            "# Requirements Index\n\n"
            "## Product Requirements (PRD)\n\n"
            "| ID | Title | File | Hash |\n"
            "|---|---|---|---|\n"
            "| REQ-p00001 | Req | spec/test.md | |\n\n"
            "## User Journeys (JNY)\n\n"
            "| ID | Title | Actor | File |\n"
            "|---|---|---|---|\n"
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
        (spec_dir / "INDEX.md").write_text(
            "# Requirements Index\n\n"
            "## Product Requirements (PRD)\n\n"
            "| ID | Title | File | Hash |\n"
            "|---|---|---|---|\n"
            "| REQ-p00001 | Req | spec/test.md | |\n\n"
            "## User Journeys (JNY)\n\n"
            "| ID | Title | Actor | File |\n"
            "|---|---|---|---|\n"
            "| JNY-Ghost-01 | Ghost Journey | Ghost | spec/journeys.md | |\n"
        )

        args = argparse.Namespace()
        result = _validate_index(graph, [spec_dir], args)

        assert result == 1
