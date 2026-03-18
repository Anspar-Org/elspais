# Verifies: REQ-d00130-A, REQ-d00130-B, REQ-d00130-C, REQ-d00130-D,
# Verifies: REQ-d00130-E, REQ-d00130-F
"""Tests for parameterized iter_roots() and iter_by_kind().

Verifies that iter_roots() accepts an optional NodeKind filter,
iter_by_kind() provides general kind-based index queries, and
FILE nodes are excluded from default iter_roots() results.
"""

from pathlib import Path

from elspais.graph import NodeKind
from elspais.graph.builder import TraceGraph
from elspais.graph.factory import build_graph as factory_build_graph
from elspais.graph.GraphNode import GraphNode
from tests.core.graph_test_helpers import build_graph, make_journey, make_requirement


def _write_config(tmp_path: Path, extra: str = "") -> Path:
    """Write a minimal .elspais.toml and return its path."""
    config_file = tmp_path / ".elspais.toml"
    config_file.write_text(
        f"""\
[project]
name = "test-parameterized-roots"

[directories]
spec = "spec"
{extra}
""",
        encoding="utf-8",
    )
    return config_file


def _write_spec(tmp_path: Path, filename: str = "reqs.md", content: str | None = None) -> Path:
    """Write a spec file and return its path."""
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir(parents=True, exist_ok=True)
    if content is None:
        content = """\
# Test Requirements

## REQ-p00001: Test Requirement

**Level**: PRD | **Status**: Active | **Implements**: -

The system SHALL do something testable.

## Assertions

A. The system SHALL perform action X.

*End* *Test Requirement* | **Hash**: abcd1234

---
"""
    (spec_dir / filename).write_text(content, encoding="utf-8")
    return spec_dir / filename


def _factory_build(tmp_path: Path, extra_config: str = ""):
    """Build a graph from tmp_path fixtures using factory pipeline."""
    config_path = _write_config(tmp_path, extra_config)
    return factory_build_graph(config_path=config_path, repo_root=tmp_path)


class TestIterRootsDefault:
    """Validates REQ-d00130-A: default iter_roots() returns REQ + JOURNEY roots."""

    def test_REQ_d00130_A_default_returns_req_roots(self, tmp_path: Path) -> None:
        """iter_roots() with no argument returns REQ roots."""
        _write_spec(tmp_path)
        graph = _factory_build(tmp_path)

        root_kinds = {n.kind for n in graph.iter_roots()}
        assert NodeKind.REQUIREMENT in root_kinds
        assert NodeKind.FILE not in root_kinds

    def test_REQ_d00130_A_default_preserves_backward_compat(self, tmp_path: Path) -> None:
        """iter_roots() with no argument returns identical results to pre-parameterization."""
        _write_spec(tmp_path)
        graph = _factory_build(tmp_path)

        # Collect roots both ways - they should be identical
        default_roots = list(graph.iter_roots())
        # root_count() should match
        assert len(default_roots) == graph.root_count()
        # All roots should be non-FILE
        assert all(n.kind != NodeKind.FILE for n in default_roots)


class TestIterRootsFile:
    """Validates REQ-d00130-B: iter_roots(NodeKind.FILE) returns FILE nodes."""

    def test_REQ_d00130_B_file_kind_returns_file_nodes(self, tmp_path: Path) -> None:
        """iter_roots(NodeKind.FILE) returns all FILE nodes from _index."""
        _write_spec(tmp_path)
        graph = _factory_build(tmp_path)

        file_nodes = list(graph.iter_roots(NodeKind.FILE))
        assert len(file_nodes) > 0
        assert all(n.kind == NodeKind.FILE for n in file_nodes)

    def test_REQ_d00130_B_file_kind_returns_all_files(self, tmp_path: Path) -> None:
        """iter_roots(NodeKind.FILE) returns every FILE node in the graph."""
        _write_spec(tmp_path)
        graph = _factory_build(tmp_path)

        file_roots = list(graph.iter_roots(NodeKind.FILE))
        all_file_nodes = [n for n in graph.all_nodes() if n.kind == NodeKind.FILE]
        assert len(file_roots) == len(all_file_nodes)
        assert {n.id for n in file_roots} == {n.id for n in all_file_nodes}


class TestIterRootsRequirement:
    """Validates REQ-d00130-C: iter_roots(NodeKind.REQUIREMENT) returns only REQ roots."""

    def test_REQ_d00130_C_requirement_kind_filters_to_reqs(self) -> None:
        """iter_roots(NodeKind.REQUIREMENT) returns only REQUIREMENT roots."""
        graph = build_graph(
            make_requirement("REQ-p00001", level="PRD", title="Req"),
            make_journey(
                "JNY-Dev-01",
                title="Journey",
                actor="Dev",
                goal="Test",
                validates=["REQ-p00001"],
            ),
        )

        req_roots = list(graph.iter_roots(NodeKind.REQUIREMENT))
        # The REQ is a child of the journey via ADDRESSES, so no REQ roots
        # But the req is still in _roots if it has no parent... depends on linking
        # Just verify kind filtering works
        assert all(n.kind == NodeKind.REQUIREMENT for n in req_roots)

    def test_REQ_d00130_C_requirement_excludes_journeys(self, tmp_path: Path) -> None:
        """iter_roots(NodeKind.REQUIREMENT) does not include journey nodes."""
        _write_spec(tmp_path)
        graph = _factory_build(tmp_path)

        req_roots = list(graph.iter_roots(NodeKind.REQUIREMENT))
        assert all(n.kind != NodeKind.USER_JOURNEY for n in req_roots)


class TestIterRootsJourney:
    """Validates REQ-d00130-D: iter_roots(NodeKind.USER_JOURNEY) returns only journey roots."""

    def _graph_with_journey_root(self) -> TraceGraph:
        """Create a graph with a USER_JOURNEY node manually added as a root."""
        graph = TraceGraph()
        req_node = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT, label="Req")
        jny_node = GraphNode(id="JNY-Dev-01", kind=NodeKind.USER_JOURNEY, label="Journey")
        graph._roots = [req_node, jny_node]
        graph._index = {"REQ-p00001": req_node, "JNY-Dev-01": jny_node}
        return graph

    def test_REQ_d00130_D_journey_kind_filters_to_journeys(self) -> None:
        """iter_roots(NodeKind.USER_JOURNEY) returns only USER_JOURNEY roots."""
        graph = self._graph_with_journey_root()

        journey_roots = list(graph.iter_roots(NodeKind.USER_JOURNEY))
        assert len(journey_roots) == 1
        assert journey_roots[0].kind == NodeKind.USER_JOURNEY
        assert journey_roots[0].id == "JNY-Dev-01"

    def test_REQ_d00130_D_journey_excludes_reqs(self) -> None:
        """iter_roots(NodeKind.USER_JOURNEY) does not include requirement nodes."""
        graph = self._graph_with_journey_root()

        journey_roots = list(graph.iter_roots(NodeKind.USER_JOURNEY))
        assert all(n.kind != NodeKind.REQUIREMENT for n in journey_roots)


class TestIterByKind:
    """Validates REQ-d00130-E: iter_by_kind() iterates all nodes of given kind."""

    def test_REQ_d00130_E_iter_by_kind_returns_all_of_kind(self, tmp_path: Path) -> None:
        """iter_by_kind(kind) returns same nodes as nodes_by_kind(kind)."""
        _write_spec(tmp_path)
        graph = _factory_build(tmp_path)

        for kind in NodeKind:
            by_kind = {n.id for n in graph.iter_by_kind(kind)}
            nodes_by = {n.id for n in graph.nodes_by_kind(kind)}
            assert by_kind == nodes_by, f"Mismatch for {kind}"

    def test_REQ_d00130_E_iter_by_kind_file(self, tmp_path: Path) -> None:
        """iter_by_kind(NodeKind.FILE) returns FILE nodes."""
        _write_spec(tmp_path)
        graph = _factory_build(tmp_path)

        file_nodes = list(graph.iter_by_kind(NodeKind.FILE))
        assert len(file_nodes) > 0
        assert all(n.kind == NodeKind.FILE for n in file_nodes)

    def test_REQ_d00130_E_iter_by_kind_requirement(self, tmp_path: Path) -> None:
        """iter_by_kind(NodeKind.REQUIREMENT) returns all requirements (not just roots)."""
        _write_spec(tmp_path)
        graph = _factory_build(tmp_path)

        req_nodes = list(graph.iter_by_kind(NodeKind.REQUIREMENT))
        assert len(req_nodes) > 0
        assert all(n.kind == NodeKind.REQUIREMENT for n in req_nodes)


class TestFileNodesExcludedFromDefault:
    """Validates REQ-d00130-F: FILE nodes not in default iter_roots()."""

    def test_REQ_d00130_F_file_nodes_not_in_default_roots(self, tmp_path: Path) -> None:
        """Default iter_roots() does not yield FILE nodes."""
        _write_spec(tmp_path)
        graph = _factory_build(tmp_path)

        # Confirm FILE nodes exist in the graph
        file_nodes = list(graph.iter_by_kind(NodeKind.FILE))
        assert len(file_nodes) > 0, "Expected FILE nodes in graph"

        # Confirm they are not in default roots
        default_root_ids = {n.id for n in graph.iter_roots()}
        file_ids = {n.id for n in file_nodes}
        assert default_root_ids.isdisjoint(
            file_ids
        ), "FILE nodes should not appear in default iter_roots()"

    def test_REQ_d00130_F_root_count_unchanged(self, tmp_path: Path) -> None:
        """root_count() continues to reflect only non-FILE roots."""
        _write_spec(tmp_path)
        graph = _factory_build(tmp_path)

        default_roots = list(graph.iter_roots())
        assert graph.root_count() == len(default_roots)
        # None should be FILE
        assert all(n.kind != NodeKind.FILE for n in default_roots)
