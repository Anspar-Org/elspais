# Verifies: REQ-d00085
"""Tests for unlinked files mini-report command.

Unlinked = scanned code/test FILE with no traceability markers found
(no CODE/TEST child nodes).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from elspais.commands.unlinked import (
    UnlinkedData,
    UnlinkedEntry,
    collect_unlinked,
    render_section,
    render_unlinked_markdown,
    render_unlinked_text,
)
from elspais.graph import EdgeKind, NodeKind
from elspais.graph.builder import TraceGraph
from elspais.graph.federated import FederatedGraph
from elspais.graph.GraphNode import FileType, GraphNode


def _make_graph(
    *,
    unlinked_test_files: int = 0,
    unlinked_code_files: int = 0,
    linked_test_files: int = 0,
) -> FederatedGraph:
    """Build a FederatedGraph with file-level unlinked/linked semantics."""
    tg = TraceGraph()

    # Unlinked TEST files (FILE nodes of type TEST with no TEST children)
    for i in range(unlinked_test_files):
        f = GraphNode(id=f"file:tests/test_empty_{i}.py", kind=NodeKind.FILE)
        f.set_field("file_type", FileType.TEST)
        f.set_field("relative_path", f"tests/test_empty_{i}.py")
        tg._index[f.id] = f
        tg._roots.append(f)

    # Unlinked CODE files (FILE nodes of type CODE with no CODE children)
    for i in range(unlinked_code_files):
        f = GraphNode(id=f"file:src/empty_{i}.py", kind=NodeKind.FILE)
        f.set_field("file_type", FileType.CODE)
        f.set_field("relative_path", f"src/empty_{i}.py")
        tg._index[f.id] = f
        tg._roots.append(f)

    # Linked TEST files (FILE of type TEST with TEST child + VERIFIES edge)
    if linked_test_files:
        req = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        tg._index[req.id] = req
        tg._roots.append(req)
        for i in range(linked_test_files):
            f = GraphNode(id=f"file:tests/test_linked_{i}.py", kind=NodeKind.FILE)
            f.set_field("file_type", FileType.TEST)
            f.set_field("relative_path", f"tests/test_linked_{i}.py")
            tg._index[f.id] = f
            tg._roots.append(f)
            t = GraphNode(id=f"test::test_linked_{i}", kind=NodeKind.TEST)
            tg._index[t.id] = t
            f.link(t, EdgeKind.CONTAINS)
            req.link(t, EdgeKind.VERIFIES)

    return FederatedGraph.from_single(tg, config=None, repo_root=Path("."))


def _make_args(**kwargs: object) -> argparse.Namespace:
    """Create a simple namespace with given attributes."""
    ns = argparse.Namespace()
    ns.format = kwargs.get("format", "text")
    ns.command = kwargs.get("command", "unlinked")
    return ns


# ---- Collection tests ----


class TestCollectUnlinked:
    """Tests for collect_unlinked() function."""

    # Implements: REQ-d00085-A
    def test_returns_empty_when_all_linked(self) -> None:
        """All linked files produce empty collections."""
        graph = _make_graph(linked_test_files=2)
        data = collect_unlinked(graph)
        assert data.tests == []
        assert data.code == []

    # Implements: REQ-d00085-A
    def test_returns_unlinked_test_files(self) -> None:
        """Test files with no markers are collected."""
        graph = _make_graph(unlinked_test_files=2)
        data = collect_unlinked(graph)
        assert len(data.tests) == 2

    # Implements: REQ-d00085-A
    def test_returns_unlinked_code_files(self) -> None:
        """Code files with no markers are collected."""
        graph = _make_graph(unlinked_code_files=3)
        data = collect_unlinked(graph)
        assert len(data.code) == 3


# ---- Text rendering tests ----


class TestRenderUnlinkedText:
    """Tests for render_unlinked_text()."""

    # Implements: REQ-d00085-E
    def test_empty_shows_none(self) -> None:
        """No unlinked nodes shows 'none'."""
        output = render_unlinked_text(UnlinkedData())
        assert "none" in output

    # Implements: REQ-d00085-E
    def test_shows_counts_when_populated(self) -> None:
        """Unlinked files show counts by kind."""
        data = UnlinkedData(
            tests=[
                UnlinkedEntry("file:tests/test_a.py", "tests/test_a.py"),
                UnlinkedEntry("file:tests/test_b.py", "tests/test_b.py"),
            ],
            code=[UnlinkedEntry("file:src/foo.py", "src/foo.py")],
        )
        output = render_unlinked_text(data)
        assert "(3)" in output
        assert "Test files (2)" in output
        assert "Code files (1)" in output

    # Implements: REQ-d00085-E
    def test_label_present(self) -> None:
        """Output contains the UNLINKED FILES label."""
        output = render_unlinked_text(UnlinkedData())
        assert "UNLINKED FILES" in output


# ---- Markdown rendering tests ----


class TestRenderUnlinkedMarkdown:
    """Tests for render_unlinked_markdown()."""

    # Implements: REQ-d00085-E
    def test_empty_shows_no_unlinked(self) -> None:
        """No unlinked files shows informative message."""
        output = render_unlinked_markdown(UnlinkedData())
        assert "No unlinked files found" in output

    # Implements: REQ-d00085-E
    def test_shows_table_when_populated(self) -> None:
        """Unlinked files render as markdown table."""
        data = UnlinkedData(
            tests=[UnlinkedEntry("file:tests/test_a.py", "tests/test_a.py")],
        )
        output = render_unlinked_markdown(data)
        assert "| File |" in output
        assert "tests/test_a.py" in output

    # Implements: REQ-d00085-E
    def test_heading_with_count(self) -> None:
        """Heading includes total count."""
        data = UnlinkedData(
            tests=[UnlinkedEntry("file:tests/test_a.py", "tests/test_a.py")],
            code=[UnlinkedEntry("file:src/foo.py", "src/foo.py")],
        )
        output = render_unlinked_markdown(data)
        assert "## UNLINKED FILES (2)" in output


# ---- render_section tests ----


class TestRenderSection:
    """Tests for render_section()."""

    # Implements: REQ-d00085-E
    def test_json_format(self) -> None:
        """JSON format produces valid JSON with test/code keys."""
        graph = _make_graph(unlinked_test_files=1, unlinked_code_files=1)
        output, _exit_code = render_section(graph, None, _make_args(format="json"))
        parsed = json.loads(output)
        assert "tests" in parsed
        assert "code" in parsed
        assert parsed["tests"]["count"] == 1
        assert parsed["code"]["count"] == 1

    # Implements: REQ-d00085-C
    def test_exit_code_0_when_no_unlinked(self) -> None:
        """Exit code is 0 when no unlinked files."""
        graph = _make_graph(linked_test_files=1)
        _output, exit_code = render_section(graph, None, _make_args())
        assert exit_code == 0

    # Implements: REQ-d00085-C
    def test_exit_code_1_when_unlinked(self) -> None:
        """Exit code is 1 when unlinked files exist."""
        graph = _make_graph(unlinked_test_files=1)
        _output, exit_code = render_section(graph, None, _make_args())
        assert exit_code == 1


# ---- Composability tests ----


class TestUnlinkedComposability:
    """Tests for unlinked section composability registration."""

    # Implements: REQ-d00085-A
    def test_returns_tuple(self) -> None:
        """render_section returns (str, int) tuple."""
        graph = _make_graph()
        result = render_section(graph, None, _make_args())
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], str)
        assert isinstance(result[1], int)

    # Implements: REQ-d00085-A
    def test_registered_in_composable_sections(self) -> None:
        """Unlinked section is registered in COMPOSABLE_SECTIONS."""
        from elspais.commands.report import COMPOSABLE_SECTIONS

        assert "unlinked" in COMPOSABLE_SECTIONS

    # Implements: REQ-d00085-E
    def test_format_support(self) -> None:
        """Unlinked section declares text, markdown, json support."""
        from elspais.commands.report import FORMAT_SUPPORT

        assert "text" in FORMAT_SUPPORT["unlinked"]
        assert "markdown" in FORMAT_SUPPORT["unlinked"]
        assert "json" in FORMAT_SUPPORT["unlinked"]

    # Implements: REQ-d00085-C
    def test_exit_bit(self) -> None:
        """Unlinked section has exit bit 64."""
        from elspais.commands.report import EXIT_BIT

        assert "unlinked" in EXIT_BIT
        assert EXIT_BIT["unlinked"] == 64
