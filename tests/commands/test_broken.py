# Verifies: REQ-d00085
"""Tests for broken references mini-report command."""
from __future__ import annotations

from pathlib import Path

from elspais.commands.broken import collect_broken, render_broken_markdown, render_broken_text
from elspais.config import config_defaults
from elspais.graph.builder import TraceGraph
from elspais.graph.federated import FederatedGraph
from elspais.graph.mutations import BrokenReference


def _test_config() -> dict:
    """Default config with ``[project].name`` set so ``from_single`` accepts it."""
    cfg = config_defaults()
    cfg.setdefault("project", {})["name"] = "test"
    return cfg


def _make_ref(
    source: str = "REQ-p00001",
    target: str = "REQ-p00099",
    kind: str = "implements",
    foreign: bool = False,
    diagnostic: str = "",
) -> BrokenReference:
    """Create a BrokenReference for testing."""
    return BrokenReference(
        source_id=source,
        target_id=target,
        edge_kind=kind,
        presumed_foreign=foreign,
        diagnostic=diagnostic,
    )


def _make_graph(*refs: BrokenReference) -> FederatedGraph:
    """Wrap broken references in a FederatedGraph for testing."""
    tg = TraceGraph()
    for ref in refs:
        tg._broken_references.append(ref)
    return FederatedGraph.from_single(tg, config=_test_config(), repo_root=Path("."))


def _make_args(**kwargs: object) -> object:
    """Create a simple namespace with given attributes."""
    import argparse

    ns = argparse.Namespace()
    ns.format = kwargs.get("format", "text")
    ns.command = kwargs.get("command", "broken")
    return ns


# ---- Collection tests ----


class TestCollectBroken:
    """Tests for collect_broken() function."""

    def test_returns_broken_refs_from_graph(self) -> None:
        """Broken references from the graph are returned."""
        ref = _make_ref()
        graph = _make_graph(ref)
        result = collect_broken(graph, config=None)
        assert len(result) == 1
        assert result[0].source_id == "REQ-p00001"
        assert result[0].target_id == "REQ-p00099"

    def test_returns_empty_when_no_broken(self) -> None:
        """No broken references returns empty list."""
        graph = _make_graph()
        result = collect_broken(graph, config=None)
        assert result == []

    def test_keeps_foreign_when_config_none(self) -> None:
        """When config is None, presumed_foreign refs are kept."""
        ref = _make_ref(foreign=True)
        graph = _make_graph(ref)
        result = collect_broken(graph, config=None)
        assert len(result) == 1

    def test_keeps_foreign_when_allow_unresolved_false(self) -> None:
        """When allow_unresolved_cross_repo is false, foreign refs are kept."""
        ref = _make_ref(foreign=True)
        graph = _make_graph(ref)
        config: dict = {"validation": {"allow_unresolved_cross_repo": False}}
        result = collect_broken(graph, config)
        assert len(result) == 1

    def test_suppresses_foreign_when_allow_unresolved_true(self) -> None:
        """When allow_unresolved_cross_repo is true, foreign refs are filtered out."""
        foreign_ref = _make_ref(source="REQ-p00001", target="EXT-x00001", foreign=True)
        local_ref = _make_ref(source="REQ-p00002", target="REQ-p00099", foreign=False)
        graph = _make_graph(foreign_ref, local_ref)
        config: dict = {"validation": {"allow_unresolved_cross_repo": True}}
        result = collect_broken(graph, config)
        assert len(result) == 1
        assert result[0].source_id == "REQ-p00002"

    def test_keeps_non_foreign_when_allow_unresolved_true(self) -> None:
        """Non-foreign refs are kept even when allow_unresolved is true."""
        ref = _make_ref(foreign=False)
        graph = _make_graph(ref)
        config: dict = {"validation": {"allow_unresolved_cross_repo": True}}
        result = collect_broken(graph, config)
        assert len(result) == 1


# ---- Text rendering tests ----


class TestRenderBrokenText:
    """Tests for render_broken_text()."""

    def test_empty_shows_none(self) -> None:
        output = render_broken_text([])
        assert "none" in output

    def test_shows_count_when_populated(self) -> None:
        refs = [_make_ref(), _make_ref(source="REQ-p00002", target="REQ-p00098")]
        output = render_broken_text(refs)
        assert "(2)" in output

    def test_shows_source_and_target(self) -> None:
        refs = [_make_ref()]
        output = render_broken_text(refs)
        assert "REQ-p00001" in output
        assert "REQ-p00099" in output
        assert "implements" in output

    def test_shows_foreign_tag(self) -> None:
        refs = [_make_ref(foreign=True)]
        output = render_broken_text(refs)
        assert "[foreign]" in output

    def test_no_foreign_tag_when_not_foreign(self) -> None:
        refs = [_make_ref(foreign=False)]
        output = render_broken_text(refs)
        assert "[foreign]" not in output

    def test_sorted_output(self) -> None:
        refs = [
            _make_ref(source="REQ-p00002", target="REQ-p00099"),
            _make_ref(source="REQ-p00001", target="REQ-p00099"),
        ]
        output = render_broken_text(refs)
        pos_a = output.index("REQ-p00001")
        pos_b = output.index("REQ-p00002")
        assert pos_a < pos_b

    def test_label_present(self) -> None:
        output = render_broken_text([])
        assert "BROKEN REFERENCES" in output

    def test_diagnostic_on_own_indented_line(self) -> None:
        # Verifies: REQ-d00085
        """A non-empty diagnostic is surfaced on its own indented line."""
        diag = "REQ-p00099 is a Template: target it with Satisfies:, not Refines:."
        refs = [_make_ref(diagnostic=diag)]
        output = render_broken_text(refs)
        assert diag in output
        # The diagnostic must live on its own line, indented beneath the ref
        # line (not concatenated onto the source/target/kind line).
        diag_lines = [ln for ln in output.split("\n") if diag in ln]
        assert diag_lines, f"diagnostic not found on any line: {output!r}"
        assert diag_lines[0].strip() == diag, (
            f"diagnostic line should contain only the diagnostic text, " f"got: {diag_lines[0]!r}"
        )
        assert diag_lines[0].startswith(
            "      "
        ), f"diagnostic line should be indented, got: {diag_lines[0]!r}"

    def test_no_diagnostic_line_when_empty(self) -> None:
        # Verifies: REQ-d00085
        """An empty diagnostic must NOT add an extra (blank) line."""
        with_diag = render_broken_text([_make_ref(diagnostic="boom")])
        without_diag = render_broken_text([_make_ref(diagnostic="")])
        # The diagnostic-carrying render has exactly one more line than the
        # bare one, proving the empty diagnostic adds no line.
        assert len(with_diag.split("\n")) == len(without_diag.split("\n")) + 1


# ---- Markdown rendering tests ----


class TestRenderBrokenMarkdown:
    """Tests for render_broken_markdown()."""

    def test_empty_shows_no_broken(self) -> None:
        output = render_broken_markdown([])
        assert "No broken references found" in output

    def test_shows_heading_with_count(self) -> None:
        refs = [_make_ref()]
        output = render_broken_markdown(refs)
        assert "## BROKEN REFERENCES (1)" in output

    def test_table_header(self) -> None:
        refs = [_make_ref()]
        output = render_broken_markdown(refs)
        assert "| Source | Target | Kind |" in output

    def test_table_separator(self) -> None:
        refs = [_make_ref()]
        output = render_broken_markdown(refs)
        lines = output.strip().split("\n")
        assert any("|---" in line for line in lines)

    def test_table_data_row(self) -> None:
        refs = [_make_ref()]
        output = render_broken_markdown(refs)
        assert "| REQ-p00001 | REQ-p00099 | implements |" in output

    def test_foreign_in_kind_column(self) -> None:
        refs = [_make_ref(foreign=True)]
        output = render_broken_markdown(refs)
        assert "implements [foreign]" in output

    def test_diagnostic_column_header(self) -> None:
        # Verifies: REQ-d00085
        """The markdown table exposes a Diagnostic column."""
        refs = [_make_ref()]
        output = render_broken_markdown(refs)
        assert "Diagnostic" in output

    def test_diagnostic_in_data_row(self) -> None:
        # Verifies: REQ-d00085
        """A ref's diagnostic text appears in its markdown data row."""
        diag = "Refining instance content is not supported."
        refs = [_make_ref(diagnostic=diag)]
        output = render_broken_markdown(refs)
        data_rows = [ln for ln in output.split("\n") if ln.startswith("| REQ-p00001 |")]
        assert data_rows, f"no data row found: {output!r}"
        assert diag in data_rows[0], f"diagnostic missing from data row: {data_rows[0]!r}"


# ---- render_section tests ----


class TestRenderSection:
    """Tests for render_section()."""

    def test_text_format(self) -> None:
        from elspais.commands.broken import render_section

        graph = _make_graph(_make_ref())
        output, exit_code = render_section(graph, None, _make_args(format="text"))
        assert "BROKEN REFERENCES" in output
        assert "REQ-p00001" in output

    def test_markdown_format(self) -> None:
        from elspais.commands.broken import render_section

        graph = _make_graph(_make_ref())
        output, exit_code = render_section(graph, None, _make_args(format="markdown"))
        assert "##" in output
        assert "| Source |" in output

    def test_json_format(self) -> None:
        import json

        from elspais.commands.broken import render_section

        graph = _make_graph(_make_ref())
        output, exit_code = render_section(graph, None, _make_args(format="json"))
        parsed = json.loads(output)
        assert "broken" in parsed
        assert len(parsed["broken"]) == 1
        assert parsed["broken"][0]["source"] == "REQ-p00001"

    def test_exit_code_0_when_no_broken(self) -> None:
        from elspais.commands.broken import render_section

        graph = _make_graph()
        _output, exit_code = render_section(graph, None, _make_args(format="text"))
        assert exit_code == 0

    def test_exit_code_1_when_broken(self) -> None:
        from elspais.commands.broken import render_section

        graph = _make_graph(_make_ref())
        _output, exit_code = render_section(graph, None, _make_args(format="text"))
        assert exit_code == 1

    def test_exit_code_1_json_when_broken(self) -> None:
        from elspais.commands.broken import render_section

        graph = _make_graph(_make_ref())
        _output, exit_code = render_section(graph, None, _make_args(format="json"))
        assert exit_code == 1

    def test_exit_code_0_json_when_clean(self) -> None:
        from elspais.commands.broken import render_section

        graph = _make_graph()
        _output, exit_code = render_section(graph, None, _make_args(format="json"))
        assert exit_code == 0


# ---- Composability tests ----


class TestBrokenComposability:
    """Tests for broken section composability registration."""

    def test_broken_registered_in_composable_sections(self) -> None:
        from elspais.commands.report import COMPOSABLE_SECTIONS

        assert "broken" in COMPOSABLE_SECTIONS

    def test_broken_format_support(self) -> None:
        from elspais.commands.report import FORMAT_SUPPORT

        assert "text" in FORMAT_SUPPORT["broken"]
        assert "markdown" in FORMAT_SUPPORT["broken"]
        assert "json" in FORMAT_SUPPORT["broken"]

    def test_broken_exit_bit(self) -> None:
        from elspais.commands.report import EXIT_BIT

        assert "broken" in EXIT_BIT


# ---- Daemon dict-renderer tests ----


class TestRenderBrokenDataRenderers:
    """Diagnostic surfacing in the daemon dict-based renderers."""

    @staticmethod
    def _data_ref(diagnostic: str = "") -> dict:
        return {
            "source": "REQ-p00001",
            "target": "REQ-p00099",
            "kind": "refines",
            "foreign": False,
            "diagnostic": diagnostic,
        }

    def test_data_text_includes_diagnostic(self) -> None:
        # Verifies: REQ-d00085
        """_render_broken_data_text surfaces the diagnostic on its own line."""
        from elspais.commands.broken import _render_broken_data_text

        diag = "REQ-p00099 is a Template: target it with Satisfies:."
        output = _render_broken_data_text([self._data_ref(diag)])
        diag_lines = [ln for ln in output.split("\n") if diag in ln]
        assert diag_lines, f"diagnostic not surfaced: {output!r}"
        assert diag_lines[0].strip() == diag
        assert diag_lines[0].startswith("      ")

    def test_data_text_no_line_when_empty(self) -> None:
        # Verifies: REQ-d00085
        """An empty diagnostic adds no extra line in the text renderer."""
        from elspais.commands.broken import _render_broken_data_text

        with_diag = _render_broken_data_text([self._data_ref("boom")])
        without_diag = _render_broken_data_text([self._data_ref("")])
        assert len(with_diag.split("\n")) == len(without_diag.split("\n")) + 1

    def test_data_markdown_includes_diagnostic(self) -> None:
        # Verifies: REQ-d00085
        """_render_broken_data_markdown surfaces the diagnostic in its row."""
        from elspais.commands.broken import _render_broken_data_markdown

        diag = "Refining instance content is not supported."
        output = _render_broken_data_markdown([self._data_ref(diag)])
        assert "Diagnostic" in output
        data_rows = [ln for ln in output.split("\n") if ln.startswith("| REQ-p00001 |")]
        assert data_rows, f"no data row: {output!r}"
        assert diag in data_rows[0]


# ---- JSON / compute_broken diagnostic tests ----


class TestBrokenJsonDiagnostic:
    """The diagnostic is carried through the json and compute_broken paths."""

    def test_json_format_includes_diagnostic(self) -> None:
        # Verifies: REQ-d00085
        import json

        from elspais.commands.broken import render_section

        diag = "REQ-p00099 is a Template: target it with Satisfies:."
        graph = _make_graph(_make_ref(diagnostic=diag))
        output, _exit = render_section(graph, None, _make_args(format="json"))
        parsed = json.loads(output)
        assert parsed["broken"][0]["diagnostic"] == diag

    def test_compute_broken_includes_diagnostic(self) -> None:
        # Verifies: REQ-d00085
        from elspais.commands.broken import compute_broken

        diag = "Refining instance content is not supported."
        graph = _make_graph(_make_ref(diagnostic=diag))
        result = compute_broken(graph, _test_config(), {})
        assert result["broken"][0]["diagnostic"] == diag
