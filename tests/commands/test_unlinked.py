# Verifies: REQ-d00085
"""Tests for unlinked nodes mini-report command."""
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
from elspais.graph.GraphNode import GraphNode


def _make_graph(
    *,
    unlinked_tests: int = 0,
    unlinked_code: int = 0,
    linked_tests: int = 0,
) -> FederatedGraph:
    """Build a FederatedGraph with the requested unlinked/linked nodes."""
    tg = TraceGraph()

    file_node = GraphNode(id="file:tests/test_foo.py", kind=NodeKind.FILE)
    file_node.set_field("relative_path", "tests/test_foo.py")
    tg._index[file_node.id] = file_node

    # Unlinked TEST nodes (FILE parent, no traceability edge)
    for i in range(unlinked_tests):
        t = GraphNode(id=f"test::test_foo_{i}", kind=NodeKind.TEST)
        tg._index[t.id] = t
        file_node.link(t, EdgeKind.CONTAINS)

    # Unlinked CODE nodes
    code_file = GraphNode(id="file:src/foo.py", kind=NodeKind.FILE)
    code_file.set_field("relative_path", "src/foo.py")
    tg._index[code_file.id] = code_file

    for i in range(unlinked_code):
        c = GraphNode(id=f"code::foo_func_{i}", kind=NodeKind.CODE)
        tg._index[c.id] = c
        code_file.link(c, EdgeKind.CONTAINS)

    # Linked TEST nodes (FILE parent + VERIFIES edge to a REQUIREMENT)
    if linked_tests:
        req = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        tg._index[req.id] = req
        tg._roots.append(req)
        for i in range(linked_tests):
            t = GraphNode(id=f"test::test_linked_{i}", kind=NodeKind.TEST)
            tg._index[t.id] = t
            file_node.link(t, EdgeKind.CONTAINS)
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
        """All linked nodes produce empty collections."""
        graph = _make_graph(linked_tests=2)
        data = collect_unlinked(graph)
        assert data.tests == []
        assert data.code == []

    # Implements: REQ-d00085-A
    def test_returns_unlinked_test_nodes(self) -> None:
        """Unlinked TEST nodes are collected."""
        graph = _make_graph(unlinked_tests=2)
        data = collect_unlinked(graph)
        assert len(data.tests) == 2
        assert data.tests[0].file == "tests/test_foo.py"

    # Implements: REQ-d00085-A
    def test_returns_unlinked_code_nodes(self) -> None:
        """Unlinked CODE nodes are collected."""
        graph = _make_graph(unlinked_code=3)
        data = collect_unlinked(graph)
        assert len(data.code) == 3
        assert data.code[0].file == "src/foo.py"


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
        """Unlinked nodes show counts by kind."""
        data = UnlinkedData(
            tests=[
                UnlinkedEntry("test::t1", "tests/test_a.py", 10, "t1"),
                UnlinkedEntry("test::t2", "tests/test_a.py", 20, "t2"),
            ],
            code=[UnlinkedEntry("code::c1", "src/foo.py", 5, "c1")],
        )
        output = render_unlinked_text(data)
        assert "(3)" in output
        assert "Tests (2)" in output
        assert "Code (1)" in output

    # Implements: REQ-d00085-E
    def test_label_present(self) -> None:
        """Output contains the UNLINKED NODES label."""
        output = render_unlinked_text(UnlinkedData())
        assert "UNLINKED NODES" in output


# ---- Markdown rendering tests ----


class TestRenderUnlinkedMarkdown:
    """Tests for render_unlinked_markdown()."""

    # Implements: REQ-d00085-E
    def test_empty_shows_no_unlinked(self) -> None:
        """No unlinked nodes shows informative message."""
        output = render_unlinked_markdown(UnlinkedData())
        assert "No unlinked nodes found" in output

    # Implements: REQ-d00085-E
    def test_shows_table_when_populated(self) -> None:
        """Unlinked nodes render as markdown table."""
        data = UnlinkedData(
            tests=[UnlinkedEntry("test::t1", "tests/test_a.py", 10, "t1")],
        )
        output = render_unlinked_markdown(data)
        assert "| File | Count |" in output
        assert "tests/test_a.py" in output

    # Implements: REQ-d00085-E
    def test_heading_with_count(self) -> None:
        """Heading includes total count."""
        data = UnlinkedData(
            tests=[UnlinkedEntry("test::t1", "tests/test_a.py", 10, "t1")],
            code=[UnlinkedEntry("code::c1", "src/foo.py", 5, "c1")],
        )
        output = render_unlinked_markdown(data)
        assert "## UNLINKED NODES (2)" in output


# ---- render_section tests ----


class TestRenderSection:
    """Tests for render_section()."""

    # Implements: REQ-d00085-E
    def test_json_format(self) -> None:
        """JSON format produces valid JSON with test/code keys."""
        graph = _make_graph(unlinked_tests=1, unlinked_code=1)
        output, _exit_code = render_section(graph, None, _make_args(format="json"))
        parsed = json.loads(output)
        assert "tests" in parsed
        assert "code" in parsed
        assert parsed["tests"]["count"] == 1
        assert parsed["code"]["count"] == 1

    # Implements: REQ-d00085-C
    def test_exit_code_0_when_no_unlinked(self) -> None:
        """Exit code is 0 when no unlinked nodes."""
        graph = _make_graph(linked_tests=1)
        _output, exit_code = render_section(graph, None, _make_args())
        assert exit_code == 0

    # Implements: REQ-d00085-C
    def test_exit_code_1_when_unlinked(self) -> None:
        """Exit code is 1 when unlinked nodes exist."""
        graph = _make_graph(unlinked_tests=1)
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
