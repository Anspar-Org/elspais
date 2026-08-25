# Verifies: REQ-d00085
"""Tests for uncited files mini-report command.

Uncited = scanned code/test FILE with no traceability markers found
(no CODE/TEST child nodes).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from elspais.commands.uncited import (
    UncitedData,
    UncitedEntry,
    collect_uncited,
    render_section,
    render_uncited_markdown,
    render_uncited_text,
)
from elspais.graph import EdgeKind, NodeKind
from elspais.graph.builder import TraceGraph
from elspais.graph.federated import FederatedGraph
from elspais.graph.GraphNode import FileType, GraphNode


def _make_graph(
    *,
    uncited_test_files: int = 0,
    uncited_code_files: int = 0,
    linked_test_files: int = 0,
) -> FederatedGraph:
    """Build a FederatedGraph with file-level uncited/linked semantics."""
    tg = TraceGraph()

    # Uncited TEST files (FILE nodes of type TEST with no TEST children)
    for i in range(uncited_test_files):
        f = GraphNode(id=f"file:tests/test_empty_{i}.py", kind=NodeKind.FILE)
        f.set_field("file_type", FileType.TEST)
        f.set_field("relative_path", f"tests/test_empty_{i}.py")
        tg._index[f.id] = f
        tg._roots.append(f)

    # Uncited CODE files (FILE nodes of type CODE with no CODE children)
    for i in range(uncited_code_files):
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

    return FederatedGraph.from_single(
        tg, config={"project": {"name": "test", "namespace": "REQ"}}, repo_root=Path(".")
    )


def _make_args(**kwargs: object) -> argparse.Namespace:
    """Create a simple namespace with given attributes."""
    ns = argparse.Namespace()
    ns.format = kwargs.get("format", "text")
    ns.command = kwargs.get("command", "uncited")
    return ns


# ---- Collection tests ----


class TestCollectUncited:
    """Tests for collect_uncited() function."""

    # Verifies: REQ-d00085-A
    def test_returns_empty_when_all_linked(self) -> None:
        """All linked files produce empty collections."""
        graph = _make_graph(linked_test_files=2)
        data = collect_uncited(graph)
        assert data.tests == []
        assert data.code == []

    # Verifies: REQ-d00085-A
    def test_returns_uncited_test_files(self) -> None:
        """Test files with no markers are collected."""
        graph = _make_graph(uncited_test_files=2)
        data = collect_uncited(graph)
        assert len(data.tests) == 2

    # Verifies: REQ-d00085-A
    def test_returns_uncited_code_files(self) -> None:
        """Code files with no markers are collected."""
        graph = _make_graph(uncited_code_files=3)
        data = collect_uncited(graph)
        assert len(data.code) == 3


# ---- Text rendering tests ----


class TestRenderUncitedText:
    """Tests for render_uncited_text()."""

    # Verifies: REQ-d00085-E
    def test_empty_shows_none(self) -> None:
        """No uncited nodes shows 'none'."""
        output = render_uncited_text(UncitedData())
        assert "none" in output

    # Verifies: REQ-d00085-E
    def test_shows_counts_when_populated(self) -> None:
        """Uncited files show counts by kind."""
        data = UncitedData(
            tests=[
                UncitedEntry("file:tests/test_a.py", "tests/test_a.py"),
                UncitedEntry("file:tests/test_b.py", "tests/test_b.py"),
            ],
            code=[UncitedEntry("file:src/foo.py", "src/foo.py")],
        )
        output = render_uncited_text(data)
        assert "(3)" in output
        assert "Test files (2)" in output
        assert "Code files (1)" in output

    # Verifies: REQ-d00085-E
    def test_label_present(self) -> None:
        """Output contains the UNCITED FILES label."""
        output = render_uncited_text(UncitedData())
        assert "UNCITED FILES" in output


# ---- Markdown rendering tests ----


class TestRenderUncitedMarkdown:
    """Tests for render_uncited_markdown()."""

    # Verifies: REQ-d00085-E
    def test_empty_shows_no_uncited(self) -> None:
        """No uncited files shows informative message."""
        output = render_uncited_markdown(UncitedData())
        assert "No uncited files found" in output

    # Verifies: REQ-d00085-E
    def test_shows_table_when_populated(self) -> None:
        """Uncited files render as markdown table."""
        data = UncitedData(
            tests=[UncitedEntry("file:tests/test_a.py", "tests/test_a.py")],
        )
        output = render_uncited_markdown(data)
        assert "| File |" in output
        assert "tests/test_a.py" in output

    # Verifies: REQ-d00085-E
    def test_heading_with_count(self) -> None:
        """Heading includes total count."""
        data = UncitedData(
            tests=[UncitedEntry("file:tests/test_a.py", "tests/test_a.py")],
            code=[UncitedEntry("file:src/foo.py", "src/foo.py")],
        )
        output = render_uncited_markdown(data)
        assert "## UNCITED FILES (2)" in output


# ---- render_section tests ----


class TestRenderSection:
    """Tests for render_section()."""

    # Verifies: REQ-d00085-E
    def test_json_format(self) -> None:
        """JSON format produces valid JSON with test/code keys."""
        graph = _make_graph(uncited_test_files=1, uncited_code_files=1)
        output, _exit_code = render_section(graph, None, _make_args(format="json"))
        parsed = json.loads(output)
        assert "tests" in parsed
        assert "code" in parsed
        assert parsed["tests"]["count"] == 1
        assert parsed["code"]["count"] == 1

    # Verifies: REQ-d00085-C
    def test_exit_code_0_when_no_uncited(self) -> None:
        """Exit code is 0 when no uncited files."""
        graph = _make_graph(linked_test_files=1)
        _output, exit_code = render_section(graph, None, _make_args())
        assert exit_code == 0

    # Verifies: REQ-d00085-C
    def test_exit_code_1_when_uncited(self) -> None:
        """Exit code is 1 when uncited files exist."""
        graph = _make_graph(uncited_test_files=1)
        _output, exit_code = render_section(graph, None, _make_args())
        assert exit_code == 1


# ---- Composability tests ----


class TestUncitedComposability:
    """Tests for uncited section composability registration."""

    # Verifies: REQ-d00085-A
    def test_returns_tuple(self) -> None:
        """render_section returns (str, int) tuple."""
        graph = _make_graph()
        result = render_section(graph, None, _make_args())
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], str)
        assert isinstance(result[1], int)

    # Verifies: REQ-d00085-A
    def test_registered_in_composable_sections(self) -> None:
        """Uncited section is registered in COMPOSABLE_SECTIONS."""
        from elspais.commands.report import COMPOSABLE_SECTIONS

        assert "uncited" in COMPOSABLE_SECTIONS

    # Verifies: REQ-d00085-E
    def test_format_support(self) -> None:
        """Uncited section declares text, markdown, json support."""
        from elspais.commands.report import FORMAT_SUPPORT

        assert "text" in FORMAT_SUPPORT["uncited"]
        assert "markdown" in FORMAT_SUPPORT["uncited"]
        assert "json" in FORMAT_SUPPORT["uncited"]

    # Verifies: REQ-d00085-C
    def test_exit_bit(self) -> None:
        """Uncited section has exit bit 64."""
        from elspais.commands.report import EXIT_BIT

        assert "uncited" in EXIT_BIT
        assert EXIT_BIT["uncited"] == 64


# ---- One name, one condition (REQ-d00285-F) ----


def _mixed_test_file_graph() -> FederatedGraph:
    """One test file holding a linked test and an unlinked one.

    This is the file that separates the two populations: it holds an unlinked
    NODE and it is not an uncited FILE.
    """
    tg = TraceGraph()
    req = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
    tg._index[req.id] = req
    tg._roots.append(req)

    f = GraphNode(id="file:tests/test_mixed.py", kind=NodeKind.FILE)
    f.set_field("file_type", FileType.TEST)
    f.set_field("relative_path", "tests/test_mixed.py")
    tg._index[f.id] = f
    tg._roots.append(f)

    linked = GraphNode(id="test::test_linked", kind=NodeKind.TEST)
    tg._index[linked.id] = linked
    f.link(linked, EdgeKind.CONTAINS)
    req.link(linked, EdgeKind.VERIFIES)

    loose = GraphNode(id="test::test_loose", kind=NodeKind.TEST)
    tg._index[loose.id] = loose
    f.link(loose, EdgeKind.CONTAINS)

    return FederatedGraph.from_single(
        tg, config={"project": {"name": "test", "namespace": "REQ"}}, repo_root=Path(".")
    )


class TestUncitedIsNotUnlinked:
    """The uncited FILES and the unlinked NODES are different populations.

    A reader comparing `elspais uncited` with the MCP `get_unlinked_nodes`
    tool meets two answers, and each surface says which question it answers.
    One name over both would make the two read as contradicting each other,
    which REQ-d00285-F forbids.
    """

    # Verifies: REQ-d00285-F
    def test_a_file_holding_an_unlinked_node_is_not_uncited(self) -> None:
        """One linked test is enough to keep the file off the uncited list,
        while the unlinked test in it is still an unlinked node."""
        graph = _mixed_test_file_graph()

        assert collect_uncited(graph).tests == []
        assert [n.id for n in graph.iter_unlinked(NodeKind.TEST)] == ["test::test_loose"]

    # Verifies: REQ-d00285-F
    def test_the_mcp_tool_reports_the_node_the_command_does_not(self) -> None:
        """The two surfaces answer different questions and say so."""
        from elspais.mcp.server import _get_unlinked_nodes

        graph = _mixed_test_file_graph()
        nodes = _get_unlinked_nodes(graph, "test")

        assert nodes["count"] == 1
        assert collect_uncited(graph).tests == []

    # Verifies: REQ-d00285-F
    def test_the_command_and_the_checks_read_one_predicate(self) -> None:
        """`elspais uncited` and `elspais checks` cannot report different sets:
        the checks read `collect_uncited` rather than walking the graph again.
        """
        from elspais.commands.health import check_uncited_code, check_uncited_tests

        graph = _make_graph(uncited_test_files=2, uncited_code_files=3, linked_test_files=1)
        data = collect_uncited(graph)

        tests_check = check_uncited_tests(graph, {})
        code_check = check_uncited_code(graph, {})

        assert tests_check.name == "tests.uncited_file"
        assert code_check.name == "code.uncited_file"
        assert {f.file_path for f in tests_check.findings} == {e.file for e in data.tests}
        assert {f.file_path for f in code_check.findings} == {e.file for e in data.code}
