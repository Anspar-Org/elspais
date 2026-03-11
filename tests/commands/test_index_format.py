# Validates REQ-d00052-G
"""Tests for INDEX.md table formatting and column alignment.

Validates REQ-d00052-G: _format_table produces padded markdown tables
where columns are aligned, and _regenerate_index uses aligned tables.
"""

import argparse

from elspais.commands.index import (
    _classify_node,
    _format_table,
    _regenerate_index,
    _resolve_spec_dir_info,
)
from elspais.graph import NodeKind
from tests.core.graph_test_helpers import (
    build_graph,
    make_journey,
    make_requirement,
)


class TestFormatTable:
    """Tests for _format_table column alignment.

    Validates REQ-d00052-G: _format_table SHALL produce padded markdown
    tables with aligned columns.
    """

    def test_REQ_d00052_G_header_cells_are_padded_to_column_width(self):
        """Header cells are left-padded to the widest value in each column."""
        headers = ["ID", "Title"]
        rows = [["REQ-p00001", "Short"]]

        result = _format_table(headers, rows)

        header_line = result[0]
        assert "| ID         |" in header_line
        assert "| Title |" in header_line

    def test_REQ_d00052_G_separator_dashes_match_column_widths(self):
        """Separator row uses dashes matching each column's computed width."""
        headers = ["ID", "Name"]
        rows = [["REQ-p00001", "My Requirement"]]

        result = _format_table(headers, rows)

        separator = result[1]
        assert "| " + "-" * 10 + " |" in separator or "----------" in separator
        assert "-" * 14 in separator

    def test_REQ_d00052_G_row_cells_are_padded_to_column_width(self):
        """Data row cells are left-padded to the widest value in each column."""
        headers = ["ID", "Title"]
        rows = [
            ["REQ-p00001", "Short"],
            ["REQ-d00002", "A Much Longer Title Here"],
        ]

        result = _format_table(headers, rows)

        row_line = result[2]
        assert "| Short                    |" in row_line

    def test_REQ_d00052_G_single_row_table(self):
        """A single-row table produces 3 lines: header, separator, data."""
        headers = ["A", "B"]
        rows = [["x", "y"]]

        result = _format_table(headers, rows)

        assert len(result) == 3

    def test_REQ_d00052_G_multiple_rows_produce_correct_line_count(self):
        """Table with N rows produces N+2 lines (header + separator + N rows)."""
        headers = ["Col1", "Col2"]
        rows = [["a", "b"], ["c", "d"], ["e", "f"]]

        result = _format_table(headers, rows)

        assert len(result) == 5

    def test_REQ_d00052_G_pipes_aligned_across_all_lines(self):
        """All pipe characters are vertically aligned across header, separator, and rows."""
        headers = ["ID", "Title", "Hash"]
        rows = [
            ["REQ-p00001", "Requirements Management Tool", "bf63eda5"],
            ["REQ-o00002", "Ops", "abc12345"],
        ]

        result = _format_table(headers, rows)

        lengths = [len(line) for line in result]
        assert len(set(lengths)) == 1, f"Lines have different lengths: {lengths}"

    def test_REQ_d00052_G_empty_cell_values_padded(self):
        """Empty cell values are padded with spaces to column width."""
        headers = ["ID", "Hash"]
        rows = [["REQ-p00001", ""], ["REQ-d00002", "abcd1234"]]

        result = _format_table(headers, rows)

        first_data = result[2]
        assert "|          |" in first_data or "| " + " " * 8 + " |" in first_data

    def test_REQ_d00052_G_header_wider_than_data(self):
        """When header is wider than all data cells, column uses header width."""
        headers = ["Very Long Header", "X"]
        rows = [["short", "y"]]

        result = _format_table(headers, rows)

        data_line = result[2]
        assert "| short            |" in data_line

    def test_REQ_d00052_G_exact_format_matches_spec(self):
        """Output matches the exact format from the specification example."""
        headers = ["ID", "Title", "File", "Hash"]
        rows = [["REQ-p00001", "Requirements Management Tool", "prd-elspais.md", "bf63eda5"]]

        result = _format_table(headers, rows)

        expected = [
            "| ID         | Title                        " "| File           | Hash     |",
            "| ---------- | ---------------------------- " "| -------------- | -------- |",
            "| REQ-p00001 | Requirements Management Tool " "| prd-elspais.md | bf63eda5 |",
        ]
        assert result == expected


class TestResolveSpecDirInfo:
    """Tests for _resolve_spec_dir_info."""

    def test_with_config(self, tmp_path):
        """Info uses project name and level config from .elspais.toml."""
        (tmp_path / ".elspais.toml").write_text(
            '[project]\nname = "my-project"\n\n'
            "[patterns.types]\n"
            'prd = { id = "p", name = "PRD", level = 1 }\n'
            'dev = { id = "d", name = "DEV", level = 3 }\n'
        )
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        info = _resolve_spec_dir_info(spec_dir)

        assert info.label == "my-project/spec"
        assert info.level_order["prd"] == 1
        assert info.level_order["dev"] == 3
        assert info.level_names["prd"] == "PRD"

    def test_no_config_falls_back(self, tmp_path):
        """Without .elspais.toml, falls back to empty level info."""
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        info = _resolve_spec_dir_info(spec_dir)

        assert info.label == f"{tmp_path.name}/spec"
        assert info.level_order == {}
        assert info.level_names == {}


class TestClassifyNode:
    """Tests for _classify_node."""

    def test_matches_correct_spec_dir(self, tmp_path):
        """Node is classified to the spec dir containing its source."""
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        graph = build_graph(
            make_requirement("REQ-p00001", level="PRD", source_path=str(spec_dir / "file.md")),
        )
        node = next(graph.nodes_by_kind(NodeKind.REQUIREMENT))

        result = _classify_node(node, [spec_dir])

        assert result == spec_dir

    def test_no_source_returns_none(self, tmp_path):
        """Node with no source path returns None."""
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        graph = build_graph(
            make_requirement("REQ-p00001", level="PRD", source_path=""),
        )
        node = next(graph.nodes_by_kind(NodeKind.REQUIREMENT))

        result = _classify_node(node, [spec_dir])

        assert result is None


class TestRegenerateIndexAlignment:
    """Tests for _regenerate_index table alignment.

    Validates REQ-d00052-G: _regenerate_index SHALL produce INDEX.md
    with properly padded and aligned markdown tables.
    """

    def _find_table_lines(self, content: str) -> list[str]:
        """Extract all table lines from content."""
        return [line for line in content.split("\n") if line.startswith("|")]

    def _find_section_table(self, content: str, heading: str) -> list[str]:
        """Extract table lines from a specific section."""
        lines = content.split("\n")
        in_section = False
        table_lines = []
        for line in lines:
            if heading in line:
                in_section = True
                continue
            if in_section and line.startswith("## "):
                break
            if in_section and line.startswith("|"):
                table_lines.append(line)
        return table_lines

    def test_REQ_d00052_G_regenerated_tables_have_aligned_columns(self, tmp_path):
        """Regenerated INDEX.md tables have aligned columns (all pipes line up)."""
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        graph = build_graph(
            make_requirement(
                "REQ-p00001",
                level="PRD",
                title="Short",
                source_path=str(spec_dir / "file.md"),
            ),
            make_requirement(
                "REQ-p00002",
                level="PRD",
                title="A Much Longer Requirement Title",
                source_path=str(spec_dir / "file.md"),
            ),
        )
        args = argparse.Namespace(git_root=tmp_path)

        _regenerate_index(graph, [spec_dir], args)

        content = (spec_dir / "INDEX.md").read_text()
        table_lines = self._find_table_lines(content)

        assert len(table_lines) >= 3
        lengths = {len(line) for line in table_lines}
        assert len(lengths) == 1, f"Table lines have unequal lengths: {lengths}"

    def test_REQ_d00052_G_regenerated_separator_uses_dashes(self, tmp_path):
        """Regenerated INDEX.md separator row uses dashes matching column widths."""
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        graph = build_graph(
            make_requirement(
                "REQ-p00001",
                level="PRD",
                title="Title",
                source_path=str(spec_dir / "file.md"),
            ),
        )
        args = argparse.Namespace(git_root=tmp_path)

        _regenerate_index(graph, [spec_dir], args)

        content = (spec_dir / "INDEX.md").read_text()
        separator = None
        for line in content.split("\n"):
            if line.startswith("|") and set(line) <= {"|", "-", " "}:
                separator = line
                break

        assert separator is not None
        assert "---|---" not in separator

    def test_REQ_d00052_G_jny_table_also_aligned(self, tmp_path):
        """JNY section table is also properly aligned with padded columns."""
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
                title="Developer Onboarding Workflow",
                actor="Developer",
                goal="Get started",
                addresses=["REQ-p00012"],
                source_path=str(spec_dir / "journeys.md"),
            ),
        )
        args = argparse.Namespace(git_root=tmp_path)

        _regenerate_index(graph, [spec_dir], args)

        content = (spec_dir / "INDEX.md").read_text()
        jny_table = self._find_section_table(content, "## User Journeys")

        assert len(jny_table) >= 3
        lengths = {len(line) for line in jny_table}
        assert len(lengths) == 1, f"JNY table lines have unequal lengths: {lengths}"

    def test_REQ_d00052_G_regenerated_content_still_has_correct_data(self, tmp_path):
        """Aligned tables still contain the correct requirement data."""
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        graph = build_graph(
            make_requirement(
                "REQ-p00001",
                level="PRD",
                title="Requirements Management Tool",
                hash_value="bf63eda5",
                source_path=str(spec_dir / "file.md"),
            ),
        )
        args = argparse.Namespace(git_root=tmp_path)

        _regenerate_index(graph, [spec_dir], args)

        content = (spec_dir / "INDEX.md").read_text()
        assert "REQ-p00001" in content
        assert "Requirements Management Tool" in content
        assert "bf63eda5" in content

    def test_REQ_d00052_G_levels_sorted_by_dependency_order(self, tmp_path):
        """Level sections appear in dependency order (PRD before DEV)."""
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        (tmp_path / ".elspais.toml").write_text(
            '[project]\nname = "test"\n\n'
            "[patterns.types]\n"
            'PRD = { id = "p", name = "PRD", level = 1 }\n'
            'DEV = { id = "d", name = "DEV", level = 3 }\n'
        )
        graph = build_graph(
            make_requirement(
                "REQ-d00001",
                level="DEV",
                title="Dev Req",
                source_path=str(spec_dir / "file.md"),
            ),
            make_requirement(
                "REQ-p00001",
                level="PRD",
                title="PRD Req",
                source_path=str(spec_dir / "file.md"),
            ),
        )
        args = argparse.Namespace(git_root=tmp_path)

        _regenerate_index(graph, [spec_dir], args)

        content = (spec_dir / "INDEX.md").read_text()
        lines = content.split("\n")
        h2_lines = [line for line in lines if line.startswith("## ")]
        # PRD should come before DEV
        prd_idx = next(i for i, ln in enumerate(h2_lines) if "PRD" in ln)
        dev_idx = next(i for i, ln in enumerate(h2_lines) if "DEV" in ln)
        assert prd_idx < dev_idx

    def test_REQ_d00052_G_multi_dir_shows_subsections(self, tmp_path):
        """Multiple spec dirs get ### subsections within a level."""
        dir_a = tmp_path / "spec_a"
        dir_b = tmp_path / "spec_b"
        dir_a.mkdir()
        dir_b.mkdir()
        graph = build_graph(
            make_requirement(
                "REQ-p00001",
                level="PRD",
                title="From A",
                source_path=str(dir_a / "file.md"),
            ),
            make_requirement(
                "REQ-p00002",
                level="PRD",
                title="From B",
                source_path=str(dir_b / "file.md"),
            ),
        )
        args = argparse.Namespace(git_root=tmp_path)

        _regenerate_index(graph, [dir_a, dir_b], args)

        content = (dir_a / "INDEX.md").read_text()
        h3_lines = [line for line in content.split("\n") if line.startswith("### ")]
        assert len(h3_lines) == 2

    def test_REQ_d00052_G_jny_table_has_no_addresses_column(self, tmp_path):
        """JNY table does not include an Addresses column."""
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
                addresses=["REQ-p00012"],
                source_path=str(spec_dir / "journeys.md"),
            ),
        )
        args = argparse.Namespace(git_root=tmp_path)

        _regenerate_index(graph, [spec_dir], args)

        content = (spec_dir / "INDEX.md").read_text()
        assert "Addresses" not in content
