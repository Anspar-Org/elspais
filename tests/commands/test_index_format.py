# Validates REQ-d00052-G
"""Tests for INDEX.md table formatting and column alignment.

Validates REQ-d00052-G: _format_table produces padded markdown tables
where columns are aligned, and _regenerate_index uses aligned tables.
"""

import argparse
from pathlib import Path

from elspais.commands.index import _format_table, _make_relative, _regenerate_index
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
        # "ID" should be padded to width of "REQ-p00001" (10 chars)
        assert "| ID         |" in header_line
        # "Title" is already wider than "Short", so Title stays at 5
        assert "| Title |" in header_line

    def test_REQ_d00052_G_separator_dashes_match_column_widths(self):
        """Separator row uses dashes matching each column's computed width."""
        headers = ["ID", "Name"]
        rows = [["REQ-p00001", "My Requirement"]]

        result = _format_table(headers, rows)

        separator = result[1]
        # Column 0 width = max(len("ID"), len("REQ-p00001")) = 10
        assert "| " + "-" * 10 + " |" in separator or "----------" in separator
        # Column 1 width = max(len("Name"), len("My Requirement")) = 14
        assert "-" * 14 in separator

    def test_REQ_d00052_G_row_cells_are_padded_to_column_width(self):
        """Data row cells are left-padded to the widest value in each column."""
        headers = ["ID", "Title"]
        rows = [
            ["REQ-p00001", "Short"],
            ["REQ-d00002", "A Much Longer Title Here"],
        ]

        result = _format_table(headers, rows)

        # Column 1 width = max(len("Title"), len("Short"), len("A Much Longer Title Here")) = 24
        # First data row "Short" should be padded to 24 chars
        row_line = result[2]
        assert "| Short                    |" in row_line

    def test_REQ_d00052_G_single_row_table(self):
        """A single-row table produces 3 lines: header, separator, data."""
        headers = ["A", "B"]
        rows = [["x", "y"]]

        result = _format_table(headers, rows)

        assert len(result) == 3
        assert result[0].startswith("| ")
        assert result[1].startswith("| ")
        assert result[2].startswith("| ")

    def test_REQ_d00052_G_multiple_rows_produce_correct_line_count(self):
        """Table with N rows produces N+2 lines (header + separator + N rows)."""
        headers = ["Col1", "Col2"]
        rows = [["a", "b"], ["c", "d"], ["e", "f"]]

        result = _format_table(headers, rows)

        assert len(result) == 5  # 1 header + 1 separator + 3 data rows

    def test_REQ_d00052_G_pipes_aligned_across_all_lines(self):
        """All pipe characters are vertically aligned across header, separator, and rows."""
        headers = ["ID", "Title", "Hash"]
        rows = [
            ["REQ-p00001", "Requirements Management Tool", "bf63eda5"],
            ["REQ-o00002", "Ops", "abc12345"],
        ]

        result = _format_table(headers, rows)

        # All lines should have the same length when columns are padded
        lengths = [len(line) for line in result]
        assert len(set(lengths)) == 1, f"Lines have different lengths: {lengths}"

    def test_REQ_d00052_G_empty_cell_values_padded(self):
        """Empty cell values are padded with spaces to column width."""
        headers = ["ID", "Hash"]
        rows = [["REQ-p00001", ""], ["REQ-d00002", "abcd1234"]]

        result = _format_table(headers, rows)

        # Empty hash cell should be padded to width of "abcd1234" (8 chars)
        first_data = result[2]
        assert "|          |" in first_data or "| " + " " * 8 + " |" in first_data

    def test_REQ_d00052_G_header_wider_than_data(self):
        """When header is wider than all data cells, column uses header width."""
        headers = ["Very Long Header", "X"]
        rows = [["short", "y"]]

        result = _format_table(headers, rows)

        # "short" should be padded to len("Very Long Header") = 16
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


class TestMakeRelative:
    """Tests for _make_relative path resolution.

    Validates REQ-d00052-G: helper for making file paths relative to spec dirs.
    """

    def test_REQ_d00052_G_relative_to_first_matching_spec_dir(self, tmp_path):
        """Path is made relative to the first matching spec directory."""
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        file_path = str(spec_dir / "prd-elspais.md")

        result = _make_relative(file_path, [spec_dir])

        assert result == "prd-elspais.md"

    def test_REQ_d00052_G_relative_with_subdirectory(self, tmp_path):
        """Path in a subdirectory of spec_dir returns relative path."""
        spec_dir = tmp_path / "spec"
        (spec_dir / "sub").mkdir(parents=True)
        file_path = str(spec_dir / "sub" / "file.md")

        result = _make_relative(file_path, [spec_dir])

        assert result == "sub/file.md"

    def test_REQ_d00052_G_no_matching_spec_dir_returns_full_path(self, tmp_path):
        """When path doesn't match any spec_dir, full path is returned."""
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        file_path = "/other/place/file.md"

        result = _make_relative(file_path, [spec_dir])

        assert result == "/other/place/file.md"

    def test_REQ_d00052_G_empty_path_returns_empty(self):
        """Empty file path returns empty string."""
        result = _make_relative("", [Path("/spec")])

        assert result == ""

    def test_REQ_d00052_G_multiple_spec_dirs_uses_first_match(self, tmp_path):
        """With multiple spec_dirs, path is relative to the first match."""
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        file_path = str(dir_b / "file.md")

        result = _make_relative(file_path, [dir_a, dir_b])

        assert result == "file.md"


class TestRegenerateIndexAlignment:
    """Tests for _regenerate_index table alignment.

    Validates REQ-d00052-G: _regenerate_index SHALL produce INDEX.md
    with properly padded and aligned markdown tables.
    """

    def test_REQ_d00052_G_regenerated_tables_have_aligned_columns(self, tmp_path):
        """Regenerated INDEX.md tables have aligned columns (all pipes line up)."""
        graph = build_graph(
            make_requirement("REQ-p00001", level="PRD", title="Short"),
            make_requirement("REQ-p00002", level="PRD", title="A Much Longer Requirement Title"),
        )

        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        args = argparse.Namespace()

        _regenerate_index(graph, [spec_dir], args)

        content = (spec_dir / "INDEX.md").read_text()
        # Find all table lines (lines starting with |)
        table_lines = [line for line in content.split("\n") if line.startswith("|")]

        # All table lines within the same section should have equal length
        assert len(table_lines) >= 3  # header + separator + at least 1 row
        # All lines should be the same length (aligned pipes)
        lengths = {len(line) for line in table_lines}
        assert len(lengths) == 1, f"Table lines have unequal lengths: {lengths}"

    def test_REQ_d00052_G_regenerated_header_is_padded(self, tmp_path):
        """Regenerated INDEX.md header cells are padded to column widths."""
        graph = build_graph(
            make_requirement("REQ-p00001", level="PRD", title="My Title"),
        )

        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        args = argparse.Namespace()

        _regenerate_index(graph, [spec_dir], args)

        content = (spec_dir / "INDEX.md").read_text()
        lines = content.split("\n")

        # Find the header line for the PRD section
        header_line = None
        for line in lines:
            if line.startswith("|") and "ID" in line and "Title" in line:
                header_line = line
                break

        assert header_line is not None
        # "ID" should be padded because "REQ-p00001" is wider
        assert "| ID " in header_line
        # The padding should make ID at least 10 chars wide
        parts = header_line.split("|")
        id_cell = parts[1]  # first cell after leading |
        assert len(id_cell.strip()) >= 2  # "ID" exists
        assert len(id_cell) > len(" ID ")  # padded beyond minimal

    def test_REQ_d00052_G_regenerated_separator_uses_dashes(self, tmp_path):
        """Regenerated INDEX.md separator row uses dashes matching column widths."""
        graph = build_graph(
            make_requirement("REQ-p00001", level="PRD", title="Title"),
        )

        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        args = argparse.Namespace()

        _regenerate_index(graph, [spec_dir], args)

        content = (spec_dir / "INDEX.md").read_text()
        lines = content.split("\n")

        # Find separator line (contains only |, -, and spaces)
        separator = None
        for line in lines:
            if line.startswith("|") and set(line) <= {"|", "-", " "}:
                separator = line
                break

        assert separator is not None
        # Separator should NOT be the old minimal format "|---|---|---|---|"
        assert "---|---" not in separator

    def test_REQ_d00052_G_jny_table_also_aligned(self, tmp_path):
        """JNY section table is also properly aligned with padded columns."""
        graph = build_graph(
            make_requirement("REQ-p00012", level="PRD", title="Auth Feature"),
            make_journey(
                "JNY-Dev-01",
                title="Developer Onboarding Workflow",
                actor="Developer",
                goal="Get started",
                addresses=["REQ-p00012"],
            ),
        )

        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        args = argparse.Namespace()

        _regenerate_index(graph, [spec_dir], args)

        content = (spec_dir / "INDEX.md").read_text()
        lines = content.split("\n")

        # Find JNY section lines
        in_jny = False
        jny_table_lines = []
        for line in lines:
            if "## User Journeys (JNY)" in line:
                in_jny = True
                continue
            if in_jny and line.startswith("|"):
                jny_table_lines.append(line)
            elif in_jny and line.startswith("##"):
                break

        assert len(jny_table_lines) >= 3  # header + separator + 1 row

        # All JNY table lines should have equal length
        lengths = {len(line) for line in jny_table_lines}
        assert len(lengths) == 1, f"JNY table lines have unequal lengths: {lengths}"

    def test_REQ_d00052_G_regenerated_content_still_has_correct_data(self, tmp_path):
        """Aligned tables still contain the correct requirement data."""
        graph = build_graph(
            make_requirement(
                "REQ-p00001",
                level="PRD",
                title="Requirements Management Tool",
                hash_value="bf63eda5",
            ),
        )

        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        args = argparse.Namespace()

        _regenerate_index(graph, [spec_dir], args)

        content = (spec_dir / "INDEX.md").read_text()
        # Data is present regardless of padding
        assert "REQ-p00001" in content
        assert "Requirements Management Tool" in content
        assert "bf63eda5" in content

    def test_REQ_d00052_G_multi_level_tables_each_aligned_independently(self, tmp_path):
        """Each level section has independently aligned tables."""
        graph = build_graph(
            make_requirement("REQ-p00001", level="PRD", title="PRD Req"),
            make_requirement("REQ-o00050", level="OPS", title="A Longer OPS Requirement Title"),
        )

        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        args = argparse.Namespace()

        _regenerate_index(graph, [spec_dir], args)

        content = (spec_dir / "INDEX.md").read_text()
        lines = content.split("\n")

        # Find PRD section table lines
        in_prd = False
        prd_lines = []
        in_ops = False
        ops_lines = []
        for line in lines:
            if "## Product Requirements (PRD)" in line:
                in_prd = True
                in_ops = False
                continue
            if "## Operations Requirements (OPS)" in line:
                in_ops = True
                in_prd = False
                continue
            if line.startswith("##"):
                in_prd = False
                in_ops = False
                continue
            if in_prd and line.startswith("|"):
                prd_lines.append(line)
            if in_ops and line.startswith("|"):
                ops_lines.append(line)

        # PRD section lines aligned
        if prd_lines:
            prd_lengths = {len(line) for line in prd_lines}
            assert len(prd_lengths) == 1, f"PRD lines unequal: {prd_lengths}"

        # OPS section lines aligned
        if ops_lines:
            ops_lengths = {len(line) for line in ops_lines}
            assert len(ops_lengths) == 1, f"OPS lines unequal: {ops_lengths}"

        # PRD and OPS may have different widths (independent alignment)
        # This is expected since they have different data

    def test_REQ_d00052_G_jny_addresses_column_included_and_aligned(self, tmp_path):
        """JNY table includes Addresses column with data aligned."""
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

        content = (spec_dir / "INDEX.md").read_text()

        # JNY header should include Addresses
        jny_lines = [
            line for line in content.split("\n") if line.startswith("|") and "Addresses" in line
        ]
        assert len(jny_lines) >= 1

        # Find the JNY data row
        jny_data_lines = [line for line in content.split("\n") if "JNY-Dev-01" in line]
        assert len(jny_data_lines) == 1
        jny_row = jny_data_lines[0]

        # Both addresses present in the row
        assert "REQ-d00042" in jny_row
        assert "REQ-p00012" in jny_row
