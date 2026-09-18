"""The members of a template subtree.

A template is a subtree, not a single requirement: template-marked
requirements refine other template-marked requirements to decompose one
cross-cutting obligation into levels of detail (REQ-p00014). This module
is the one place that subtree is walked. The builder reads it to decide
what a ``Satisfies:`` declaration clones, the federated builder reads it
for a template owned by another repository, and the satisfier rollup
reads it over the clones, whose REFINES edges mirror the originals'.
"""

from __future__ import annotations

from collections.abc import Iterator

from elspais.graph.GraphNode import GraphNode, NodeKind
from elspais.graph.relations import EdgeKind

# Fields an original holds that a clone of it does not copy. The stereotype
# is the clone's own; the reference text is what the original declared, and
# a clone's relationships are the edges recreated among the clones.
UNCLONED_FIELDS: frozenset[str] = frozenset({"stereotype", "implements_refs", "refines_refs"})


# Implements: REQ-p00014-B
def iter_subtree_requirements(root: GraphNode) -> Iterator[GraphNode]:
    """Yield ``root`` and every requirement that refines a member, recursively.

    Membership follows outgoing REFINES edges (the cited requirement holds the
    edge to the requirement citing it) and stops at a requirement whose
    stereotype differs from the root's: over a template this keeps the walk to
    template-marked refiners, over an instance clone to the clones made with
    it. Each member is yielded once however many paths reach it. A root that
    is not a requirement is yielded alone.
    """
    if root.kind != NodeKind.REQUIREMENT:
        yield root
        return
    stereotype = root.get_field("stereotype")
    seen: set[str] = set()
    stack = [root]
    while stack:
        node = stack.pop()
        if node.id in seen:
            continue
        seen.add(node.id)
        yield node
        for edge in node.iter_outgoing_edges():
            if edge.kind != EdgeKind.REFINES:
                continue
            refiner = edge.target
            if refiner.kind != NodeKind.REQUIREMENT:
                continue
            if refiner.get_field("stereotype") != stereotype:
                continue
            stack.append(refiner)


# Implements: REQ-p00014-B, REQ-p00014-H
def subtree_nodes(root: GraphNode) -> list[GraphNode]:
    """Every member requirement of the subtree at ``root`` with its *Assertions*.

    Each requirement is followed by its directly-attached *Assertions*, so a
    caller cloning the list meets a requirement before the nodes it
    structures.
    """
    nodes: list[GraphNode] = []
    for member in iter_subtree_requirements(root):
        nodes.append(member)
        if member.kind != NodeKind.REQUIREMENT:
            continue
        for child in member.iter_children(edge_kinds={EdgeKind.STRUCTURES}):
            if child.kind == NodeKind.ASSERTION:
                nodes.append(child)
    return nodes


# Implements: REQ-p00014-M, REQ-p00014-H
def recreate_subtree_edges(originals: list[GraphNode], clone_map: dict[str, GraphNode]) -> None:
    """Recreate the subtree's own edges among the clones, each exactly once.

    A clone receives the STRUCTURES edges to its cloned *Assertions* and the
    REFINES edges to the cloned requirements refining it, carrying the
    *Assertion* labels the refinement named. Every other edge an original
    holds leads outside the subtree — to evidence, to a file, to an
    instance — and is not an edge of the subtree.
    """
    for orig in originals:
        clone = clone_map.get(orig.id)
        if clone is None:
            continue
        for edge in orig.iter_outgoing_edges():
            if edge.kind not in (EdgeKind.STRUCTURES, EdgeKind.REFINES):
                continue
            target_clone = clone_map.get(edge.target.id)
            if target_clone is None:
                continue
            clone.link(target_clone, edge.kind, assertion_targets=list(edge.assertion_targets))
