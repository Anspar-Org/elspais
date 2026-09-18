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
from elspais.graph.reference_faults import FaultClass, ReferenceFault
from elspais.graph.relations import EdgeKind, Stereotype

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


# Implements: REQ-p00014-G
def stereotype_matrix_fault(
    source: GraphNode,
    target: GraphNode,
    source_id: str,
    target_id: str,
    edge_kind: EdgeKind,
) -> ReferenceFault | None:
    """The fault a reference commits against the template validation matrix.

    Returns the ``ReferenceFault`` for a reference whose source and target
    stereotypes the matrix forbids for ``edge_kind``, or None where the
    matrix admits it. It is the one authority for the matrix's Refines,
    Implements and Verifies rows: every builder reads it before creating
    such an edge — the one-repository builder and the federation wiring a
    reference into an associated repository alike — so the graph never
    holds an edge it also reports as a fault, and a target owned by another
    repository is judged by the rule a local one is. The Satisfies rows are
    judged where a Satisfies: is instantiated, since there a refusal
    withholds a clone rather than an edge.
    """
    target_stereotype = target.get_field("stereotype")
    source_is_template = (
        source.kind == NodeKind.REQUIREMENT
        and source.get_field("stereotype") == Stereotype.TEMPLATE
    )

    def fault(diagnostic: str) -> ReferenceFault:
        return ReferenceFault(
            source_id=source_id,
            target_id=target_id,
            edge_kind=edge_kind.value,
            fault_class=FaultClass.FORBIDDEN,
            diagnostic=diagnostic,
        )

    if (
        edge_kind == EdgeKind.REFINES
        and target_stereotype == Stereotype.TEMPLATE
        and not source_is_template
    ):
        # A template's refiners must themselves be templates: the
        # template-to-template REFINES edge is what forms a template
        # subtree, so a refiner that is not marked joins nothing. One edge,
        # one report: the author either meant to decompose the template or
        # to instantiate it.
        return fault(
            f"{target_id} is a Template and {source_id} is "
            f"not: a template's refiners must themselves be "
            f"templates. Mark {source_id} **Template** to "
            f"decompose {target_id}, or declare "
            f"Satisfies: {target_id} to instantiate it."
        )
    if source_is_template and edge_kind == EdgeKind.REFINES:
        if target_stereotype not in (Stereotype.TEMPLATE, Stereotype.INSTANCE):
            # A template's Refines: may only reach its own subtree, and the
            # subtree holds template-marked nodes alone. A concrete
            # *Assertion* carries no stereotype of its own, so the test is
            # for what is admitted rather than for CONCRETE. An INSTANCE
            # target is refused below for what it is, once.
            return fault(
                f"{source_id} is marked **Template** but "
                f"refines {target_id}, which is not: a "
                f"template's Refines: may only target its "
                f"own template subtree. Mark {target_id} "
                f"**Template** or remove the reference."
            )
    if source_is_template and edge_kind == EdgeKind.IMPLEMENTS:
        # A template subtree is formed by refinement alone, so an
        # implementation claim declared by a template reaches outside it
        # whatever it names.
        return fault(
            f"Templates are pure specs; remove the "
            f"Implements: metadata or remove the "
            f"**Template** flag on {source_id}."
        )
    if edge_kind == EdgeKind.REFINES and target_stereotype == Stereotype.INSTANCE:
        # Refining instance content is not supported.
        return fault(
            "Refining instance content is not supported. "
            "Instance subtrees are read-only synthetic "
            "content with no canonical on-disk identifier. "
            "To add detail, Satisfies: the template AND "
            "Refines: a concrete REQ in your own repo."
        )
    if (
        edge_kind in (EdgeKind.IMPLEMENTS, EdgeKind.VERIFIES)
        and target_stereotype == Stereotype.INSTANCE
    ):
        # Composite ids are not authoring syntax, for CODE and TEST alike.
        return fault(
            "Instance assertions have no canonical "
            "on-disk identifier; target the template "
            "assertion directly or add a concrete "
            "assertion to your satisfier."
        )
    return None
