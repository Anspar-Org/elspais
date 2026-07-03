# Verifies: REQ-d00127-C
"""Behavior tests for centralized EdgeKind sets in elspais.graph.edge_sets.

Guards the semantic distinctions between the four edge-set constants:

- STRUCTURAL_EDGE_KINDS           -> {CONTAINS, STRUCTURES}: file/structural hierarchy
- ASSERTION_STRUCTURE_EDGES       -> {STRUCTURES}: assertion -> parent REQ (NO CONTAINS)
- TRACEABILITY_EDGE_KINDS         -> all non-structural edge kinds
- REACHABILITY_TRACEABILITY_EDGES -> {IMPLEMENTS, VERIFIES, VALIDATES}: narrow
  "non-spec node reaches a REQ" subset (NO REFINES)
"""

from __future__ import annotations

import pytest

from elspais.graph import GraphNode, NodeKind
from elspais.graph.edge_sets import (
    ASSERTION_STRUCTURE_EDGES,
    REACHABILITY_TRACEABILITY_EDGES,
    STRUCTURAL_EDGE_KINDS,
    TRACEABILITY_EDGE_KINDS,
)
from elspais.graph.relations import EdgeKind


def _node(node_id: str, kind: NodeKind) -> GraphNode:
    return GraphNode(id=node_id, kind=kind)


# --------------------------------------------------------------------------- #
# (a) ASSERTION_STRUCTURE_EDGES: assertion -> parent REQ resolution
# --------------------------------------------------------------------------- #


class TestAssertionStructureEdges:
    """Comment-anchor resolution invariant: assertion's parent walk must
    reach the REQUIREMENT and stop. If CONTAINS leaked in, the walk would
    surface the FILE ancestor through the REQ's incoming CONTAINS edge --
    breaking comment_store.validate_anchor() ownership lookup."""

    def _file_req_assertion(self) -> tuple[GraphNode, GraphNode, GraphNode]:
        f = _node("file:spec/x.md", NodeKind.FILE)
        r = _node("REQ-p00001", NodeKind.REQUIREMENT)
        a = _node("REQ-p00001-A", NodeKind.ASSERTION)
        f.link(r, EdgeKind.CONTAINS)
        r.link(a, EdgeKind.STRUCTURES)
        return f, r, a

    def test_assertion_parent_is_requirement_not_file(self):
        f, r, a = self._file_req_assertion()
        parents = list(a.iter_parents(edge_kinds=ASSERTION_STRUCTURE_EDGES))
        assert parents == [r], (
            "ASSERTION_STRUCTURE_EDGES must yield only the REQ parent; "
            "if CONTAINS leaked, FILE would also appear and corrupt "
            "comment-anchor ownership lookup."
        )

    def test_assertion_ancestors_does_not_leak_to_file(self):
        f, r, a = self._file_req_assertion()
        ancestors = {n.id for n in a.ancestors(edge_kinds=ASSERTION_STRUCTURE_EDGES)}
        assert r.id in ancestors
        assert f.id not in ancestors, "Walk via ASSERTION_STRUCTURE_EDGES must not climb into FILE."

    def test_canonical_graph_assertion_finds_owning_requirement(self, canonical_graph):
        assertion = canonical_graph.find_by_id("REQ-p00001-A")
        assert assertion is not None and assertion.kind == NodeKind.ASSERTION
        parents = list(assertion.iter_parents(edge_kinds=ASSERTION_STRUCTURE_EDGES))
        assert any(p.id == "REQ-p00001" for p in parents)
        assert not any(p.kind == NodeKind.FILE for p in parents)


# --------------------------------------------------------------------------- #
# (b) STRUCTURAL_EDGE_KINDS: FILE walk reaches REQs AND their assertions
# --------------------------------------------------------------------------- #


class TestStructuralEdgeKinds:
    """STRUCTURAL_EDGE_KINDS must span CONTAINS (FILE->REQ) and STRUCTURES
    (REQ->ASSERTION). The narrower ASSERTION_STRUCTURE_EDGES (STRUCTURES
    only) reaches nothing from a FILE, since FILE has no STRUCTURES out."""

    def _build(self) -> tuple[GraphNode, GraphNode, list[GraphNode]]:
        f = _node("file:spec/z.md", NodeKind.FILE)
        r = _node("REQ-p00010", NodeKind.REQUIREMENT)
        a1 = _node("REQ-p00010-A", NodeKind.ASSERTION)
        a2 = _node("REQ-p00010-B", NodeKind.ASSERTION)
        f.link(r, EdgeKind.CONTAINS)
        r.link(a1, EdgeKind.STRUCTURES)
        r.link(a2, EdgeKind.STRUCTURES)
        return f, r, [a1, a2]

    def test_walk_from_file_reaches_assertions(self):
        f, r, assertions = self._build()
        reached = {n.id for n in f.walk(edge_kinds=STRUCTURAL_EDGE_KINDS)}
        assert r.id in reached, "Must cross CONTAINS to REQ."
        for a in assertions:
            assert a.id in reached, (
                f"Must cross STRUCTURES from REQ to assertion {a.id}; "
                "STRUCTURAL_EDGE_KINDS missing STRUCTURES blocks this."
            )

    def test_assertion_subset_cannot_descend_from_file(self):
        f, _r, _assertions = self._build()
        reached = {n.id for n in f.walk(edge_kinds=ASSERTION_STRUCTURE_EDGES)}
        assert reached == {f.id}, (
            "ASSERTION_STRUCTURE_EDGES (STRUCTURES only) must not descend "
            "from a FILE node -- FILE uses CONTAINS to link children."
        )


# --------------------------------------------------------------------------- #
# (c) TRACEABILITY_EDGE_KINDS: all seven traceability kinds traversable
# --------------------------------------------------------------------------- #


TRACEABILITY_KINDS = (
    EdgeKind.IMPLEMENTS,
    EdgeKind.REFINES,
    EdgeKind.SATISFIES,
    EdgeKind.VERIFIES,
    EdgeKind.VALIDATES,
    EdgeKind.INSTANCE,
    EdgeKind.DEFINES,
    EdgeKind.YIELDS,
)


class TestTraceabilityEdgeKinds:
    """All 8 traceability kinds (IMPLEMENTS, REFINES, SATISFIES, VERIFIES,
    VALIDATES, INSTANCE, DEFINES, YIELDS) must be honored by
    TRACEABILITY_EDGE_KINDS; structural kinds (CONTAINS/STRUCTURES) must
    be excluded."""

    def test_walk_traverses_every_traceability_kind(self):
        center = _node("center", NodeKind.REQUIREMENT)
        sinks = {}
        for kind in TRACEABILITY_KINDS:
            s = _node(f"sink:{kind.value}", NodeKind.REQUIREMENT)
            center.link(s, kind)
            sinks[kind] = s
        # A structural edge that must NOT be followed.
        struct_sink = _node("structural-sink", NodeKind.REMAINDER)
        center.link(struct_sink, EdgeKind.STRUCTURES)

        reached = {n.id for n in center.walk(edge_kinds=TRACEABILITY_EDGE_KINDS)}

        for kind, s in sinks.items():
            assert (
                s.id in reached
            ), f"TRACEABILITY_EDGE_KINDS missing {kind.value}: {s.id} unreached."
        assert struct_sink.id not in reached, "TRACEABILITY_EDGE_KINDS must exclude STRUCTURES."

    @pytest.mark.parametrize("kind", TRACEABILITY_KINDS)
    def test_each_kind_individually_traversed(self, kind: EdgeKind):
        src = _node(f"src-{kind.value}", NodeKind.REQUIREMENT)
        dst = _node(f"dst-{kind.value}", NodeKind.REQUIREMENT)
        src.link(dst, kind)
        children = list(src.iter_children(edge_kinds=TRACEABILITY_EDGE_KINDS))
        assert (
            dst in children
        ), f"TRACEABILITY_EDGE_KINDS missing {kind.value} -- child not reached."


# --------------------------------------------------------------------------- #
# (d) REACHABILITY_TRACEABILITY_EDGES: narrow non-spec -> REQ subset
# --------------------------------------------------------------------------- #


class TestReachabilityTraceabilityEdges:
    """{IMPLEMENTS, VERIFIES, VALIDATES} only -- REFINES must NOT be included.
    health.py uses this set to answer "does this CODE/TEST/JNY reach a REQ?";
    REFINES is req->req only and must not count for non-spec nodes."""

    def test_code_implements_req_is_reachable(self):
        req = _node("REQ-d00200", NodeKind.REQUIREMENT)
        code = _node("code:src/foo.py:10", NodeKind.CODE)
        req.link(code, EdgeKind.IMPLEMENTS)  # health.py walks iter_parents from CODE
        parents = list(code.iter_parents(edge_kinds=REACHABILITY_TRACEABILITY_EDGES))
        assert req in parents

    def test_refines_alone_is_not_reachable(self):
        req = _node("REQ-d00201", NodeKind.REQUIREMENT)
        proxy = _node("proxy-node", NodeKind.CODE)
        req.link(proxy, EdgeKind.REFINES)  # invalid for CODE, but proves exclusion

        narrow = list(proxy.iter_parents(edge_kinds=REACHABILITY_TRACEABILITY_EDGES))
        full = list(proxy.iter_parents(edge_kinds=TRACEABILITY_EDGE_KINDS))

        assert req not in narrow, (
            "REACHABILITY_TRACEABILITY_EDGES must NOT include REFINES; "
            "otherwise health.py would falsely flag REFINES-only links."
        )
        assert req in full, "Sanity: TRACEABILITY_EDGE_KINDS includes REFINES."

    @pytest.mark.parametrize("kind", [EdgeKind.IMPLEMENTS, EdgeKind.VERIFIES, EdgeKind.VALIDATES])
    def test_each_reachability_kind_traversed(self, kind: EdgeKind):
        req = _node(f"REQ-d00210-{kind.value}", NodeKind.REQUIREMENT)
        leaf = _node(f"leaf:{kind.value}", NodeKind.CODE)
        req.link(leaf, kind)
        parents = list(leaf.iter_parents(edge_kinds=REACHABILITY_TRACEABILITY_EDGES))
        assert req in parents, f"REACHABILITY_TRACEABILITY_EDGES missing {kind.value}."
