# Verifies: REQ-d00241-A, REQ-d00241-D, REQ-d00285-F
"""The uncited-file predicate.

Uncited = scanned code/test FILE with no traceability markers found
(no CODE/TEST child nodes).

`elspais uncited` itself is the findings report narrowed to the two checks
that read this predicate -- see `tests/commands/test_preset_listings.py`.
"""

from __future__ import annotations

from pathlib import Path

from elspais.commands.uncited import collect_uncited
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
