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

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field

from elspais.graph.GraphNode import GraphNode, NodeKind
from elspais.graph.reference_faults import FaultClass, ReferenceFault
from elspais.graph.relations import Edge, EdgeKind, Stereotype

# Fields an original holds that a clone of it does not copy. The stereotype
# is the clone's own; the reference text is what the original declared, and
# a clone's relationships are the edges recreated among the clones. Whether
# the original's text needs rewriting is a fact about its file, and a clone
# has no text of its own to rewrite.
UNCLONED_FIELDS: frozenset[str] = frozenset(
    {"stereotype", "implements_refs", "refines_refs", "parse_dirty", "parse_dirty_reasons"}
)


# Implements: REQ-p00014-B
def iter_subtree_requirements(
    root: GraphNode, excluded: frozenset[str] = frozenset()
) -> Iterator[GraphNode]:
    """Yield ``root`` and every requirement that refines a member, recursively.

    Membership follows outgoing REFINES edges (the cited requirement holds the
    edge to the requirement citing it) and stops at a requirement whose
    stereotype differs from the root's: over a template this keeps the walk to
    template-marked refiners, over an instance clone to the clones made with
    it. Each member is yielded once however many paths reach it. A root that
    is not a requirement is yielded alone. A requirement named in
    ``excluded`` is neither yielded nor walked through.
    """
    if root.id in excluded:
        return
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
            if refiner.kind != NodeKind.REQUIREMENT or refiner.id in excluded:
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


def owning_requirement(node: GraphNode) -> GraphNode | None:
    """The requirement holding *node*: itself, or an *Assertion*'s requirement."""
    if node.kind == NodeKind.REQUIREMENT:
        return node
    if node.kind != NodeKind.ASSERTION:
        return None
    return next(
        (
            p
            for p in node.iter_parents(edge_kinds={EdgeKind.STRUCTURES})
            if p.kind == NodeKind.REQUIREMENT
        ),
        None,
    )


# Implements: REQ-p00014-B, REQ-d00328-A+B+C+D
def copy_plan(
    targets: Iterable[GraphNode], excluded: frozenset[str] = frozenset()
) -> dict[str, tuple[GraphNode, set[str] | None]]:
    """What one declaring requirement's ``Satisfies:`` targets copy, together.

    Maps each original requirement to copy to the ids of the *Assertions*
    its copy holds, or to None where it holds them all. A requirement
    target contributes its whole template subtree. An *Assertion* target
    contributes its requirement holding that *Assertion*, and the whole
    subtree of each template requirement refining that *Assertion* or
    refining its requirement without naming an *Assertion*. Every target is
    planned at once, so each original appears once and holds the union of
    what the targets ask of it, whatever order they were declared in. An
    original named in ``excluded`` is planned for nothing.
    """
    plan: dict[str, tuple[GraphNode, set[str] | None]] = {}

    def whole(root: GraphNode) -> None:
        for member in iter_subtree_requirements(root, excluded):
            plan[member.id] = (member, None)

    for target in targets:
        if target.id in excluded:
            continue
        if target.kind == NodeKind.REQUIREMENT:
            whole(target)
            continue
        requirement = owning_requirement(target)
        if requirement is None or requirement.id in excluded:
            continue
        held = plan.get(requirement.id)
        if held is None:
            plan[requirement.id] = (requirement, {target.id})
        elif held[1] is not None:
            held[1].add(target.id)
        label = target.get_field("label", "")
        stereotype = requirement.get_field("stereotype")
        for edge in requirement.iter_outgoing_edges():
            if edge.kind != EdgeKind.REFINES:
                continue
            refiner = edge.target
            if refiner.kind != NodeKind.REQUIREMENT:
                continue
            if refiner.get_field("stereotype") != stereotype:
                continue
            if edge.assertion_targets and label not in edge.assertion_targets:
                continue
            whole(refiner)
    return plan


@dataclass
class SatisfiesCopy:
    """What one ``instantiate_subtree`` call added to a graph.

    ``copies`` holds each copy it made, keyed by the identifier of its
    original; ``edges`` each edge it linked between copies it found already
    made, or from the declaring requirement; ``relabelled`` each such edge
    whose *Assertion* labels it widened, with the labels it held before.
    Undo reads all three.
    """

    copies: dict[str, GraphNode] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    relabelled: list[tuple[Edge, list[str]]] = field(default_factory=list)


def _copy_of(original: GraphNode, copy_id: str, index: dict[str, GraphNode]) -> GraphNode | None:
    """The copy of *original* that ``index`` holds under *copy_id*, if one."""
    held = index.get(copy_id)
    if held is None:
        return None
    for edge in held.iter_outgoing_edges():
        if edge.kind == EdgeKind.INSTANCE and edge.target is original:
            return held
    return None


# Implements: REQ-p00014-B, REQ-p00014-H, REQ-p00014-M, REQ-p00014-O, REQ-d00128-J
# Implements: REQ-d00328-A+B+C+D+F
def instantiate_subtree(
    targets: list[GraphNode],
    declaring_node: GraphNode,
    instance_id: Callable[[str], str],
    owning_repo: Callable[[GraphNode], tuple[str, bool]],
    index: dict[str, GraphNode],
    excluded: frozenset[str] = frozenset(),
) -> SatisfiesCopy:
    """Copy what ``declaring_node``'s ``Satisfies:`` of ``targets`` instantiates.

    This is the one place a ``Satisfies:`` copy is made: by the builder, by
    the federation for a template another repository owns, and by a
    mutation that brings an *Assertion* back. ``copy_plan`` decides what is
    copied. Each original gets one copy under the identifier
    ``instance_id`` composes; a copy ``index`` already holds is extended
    rather than made again, so declarations copied in separate passes
    still produce one copy of each original. A copy holds the original's
    content, the INSTANCE stereotype, an INSTANCE edge back to the original
    and the name of the repository owning the original. ``owning_repo``
    answers that name, and whether the original lives in the repository
    making the copy: only then does the copy keep the original's lines,
    since a line in another repository's file locates nothing here. Each
    copy enters ``index``. The subtree's own edges are recreated among the
    copies, the declaring requirement satisfies the copy of each target's
    requirement -- with the target's label where the target is an
    *Assertion* -- and the declaring requirement's file defines every copy.
    """
    plan = copy_plan(targets, excluded)
    result = SatisfiesCopy()
    declaring_file = declaring_node.file_node()
    copies: dict[str, GraphNode] = {}

    def copy(orig: GraphNode) -> GraphNode:
        copy_id = instance_id(orig.id)
        held = _copy_of(orig, copy_id, index)
        if held is not None:
            return held
        clone = GraphNode(id=copy_id, kind=orig.kind, label=orig.get_label())
        # A clone's relationships are the edges recreated among the clones,
        # so the reference text the original declared is not copied: left in
        # place it would read as a reference the clone declared and never
        # resolved.
        for key, value in orig.get_all_content().items():
            if key not in UNCLONED_FIELDS:
                clone.set_field(key, value)
        clone.set_field("stereotype", Stereotype.INSTANCE)
        repo_name, local = owning_repo(orig)
        if repo_name:
            clone.set_field("template_repo", repo_name)
        for line_field in ("parse_line", "parse_end_line"):
            line = orig.get_field(line_field) if local else None
            if line is not None or not local:
                clone.set_field(line_field, line)
        index[clone.id] = clone
        clone.link(orig, EdgeKind.INSTANCE)
        if declaring_file is not None:
            declaring_file.link(clone, EdgeKind.DEFINES)
        result.copies[orig.id] = clone
        return clone

    for requirement, held in plan.values():
        copies[requirement.id] = copy(requirement)
        for child in requirement.iter_children(edge_kinds={EdgeKind.STRUCTURES}):
            if child.kind != NodeKind.ASSERTION or child.id in excluded:
                continue
            if held is None or child.id in held:
                copies[child.id] = copy(child)

    def copy_found(orig: GraphNode) -> GraphNode | None:
        return copies.get(orig.id) or _copy_of(orig, instance_id(orig.id), index)

    recreate_subtree_edges([r for r, _held in plan.values()], copy_found, result)

    for target in targets:
        requirement = owning_requirement(target)
        root = copies.get(requirement.id) if requirement is not None else None
        if root is None:
            continue
        labels = [] if target is requirement else [target.get_field("label", "")]
        if any(
            e.kind == EdgeKind.SATISFIES and e.target is root and e.assertion_targets == labels
            for e in declaring_node.iter_outgoing_edges()
        ):
            continue
        result.edges.append(declaring_node.link(root, EdgeKind.SATISFIES, labels or None))
    return result


# Implements: REQ-d00328-A
def declared_originals(edge: Edge) -> list[GraphNode]:
    """The originals the ``Satisfies:`` that made the SATISFIES *edge* names.

    The edge lands on the copy of a requirement and carries the label of
    each *Assertion* the declaration named; with no label it named the
    requirement.
    """
    copy = edge.target
    if not edge.assertion_targets:
        return list(copy.iter_children(edge_kinds={EdgeKind.INSTANCE}))
    named: list[GraphNode] = []
    for child in copy.iter_children(edge_kinds={EdgeKind.STRUCTURES}):
        if child.kind == NodeKind.ASSERTION and child.get_field("label") in edge.assertion_targets:
            named.extend(child.iter_children(edge_kinds={EdgeKind.INSTANCE}))
    return named


def _held_labels(copy: GraphNode) -> set[str]:
    """The labels of the *Assertions* *copy* holds."""
    return {
        child.get_field("label", "")
        for child in copy.iter_children(edge_kinds={EdgeKind.STRUCTURES})
        if child.kind == NodeKind.ASSERTION
    }


# Implements: REQ-p00014-M, REQ-p00014-H, REQ-d00328-B+E
def recreate_subtree_edges(
    requirements: list[GraphNode],
    copy_found: Callable[[GraphNode], GraphNode | None],
    result: SatisfiesCopy,
) -> None:
    """Join the copies of ``requirements`` by the edges their originals hold.

    A copy receives the STRUCTURES edges to its copied *Assertions*, and the
    REFINES edges joining it to every copy -- made now or made earlier for
    the same declaring requirement -- whose original refines its original or
    is refined by it. A copied refinement names only the labels the copy of
    its target holds, and one whose labels the copy holds none of is not
    copied. Every other edge an original holds leads outside the subtree --
    to evidence, to a file, to an instance -- and is not copied. An edge
    already joining two copies is not linked twice.
    """

    def join(parent: GraphNode, child: GraphNode, kind: EdgeKind, labels: list[str]) -> None:
        if kind == EdgeKind.REFINES and labels:
            held = _held_labels(parent)
            labels = [label for label in labels if label in held]
            if not labels:
                return
        for edge in parent.iter_outgoing_edges():
            if edge.kind != kind or edge.target is not child:
                continue
            if edge.assertion_targets == labels:
                return
            if labels and edge.assertion_targets and set(edge.assertion_targets) < set(labels):
                result.relabelled.append((edge, list(edge.assertion_targets)))
                edge.assertion_targets[:] = labels
                return
        result.edges.append(parent.link(child, kind, list(labels) or None))

    for requirement in requirements:
        requirement_copy = copy_found(requirement)
        if requirement_copy is None:
            continue
        for edge in requirement.iter_outgoing_edges():
            if edge.kind not in (EdgeKind.STRUCTURES, EdgeKind.REFINES):
                continue
            target_copy = copy_found(edge.target)
            if target_copy is not None:
                join(requirement_copy, target_copy, edge.kind, list(edge.assertion_targets))
        for edge in requirement.iter_incoming_edges():
            if edge.kind != EdgeKind.REFINES:
                continue
            source_copy = copy_found(edge.source)
            if source_copy is not None:
                join(source_copy, requirement_copy, edge.kind, list(edge.assertion_targets))


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
    ``satisfies_target_fault``'s, judged where a Satisfies: is instantiated,
    since there a refusal withholds a clone rather than an edge.
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


# Implements: REQ-p00014-G
def satisfies_target_fault(
    target: GraphNode, source_id: str, target_id: str
) -> ReferenceFault | None:
    """The fault a ``Satisfies:`` commits against the validation matrix, if any.

    Returns the ``ReferenceFault`` for a target that is an instance clone
    (chained instantiation) or that is not marked **Template**, or None where
    the target may be instantiated. It is the one authority for the matrix's
    Satisfies rows: the one-repository builder and the federation
    instantiating a template owned by another repository both read it before
    they clone, so a refused target produces no clone and the same report
    wherever it lives.
    """

    def fault(diagnostic: str) -> ReferenceFault:
        return ReferenceFault(
            source_id=source_id,
            target_id=target_id,
            edge_kind=EdgeKind.SATISFIES.value,
            fault_class=FaultClass.FORBIDDEN,
            diagnostic=diagnostic,
        )

    stereotype = target.get_field("stereotype")
    if stereotype == Stereotype.INSTANCE:
        return fault(
            "Chained instantiation is not supported. Satisfy the original template directly."
        )
    if stereotype != Stereotype.TEMPLATE:
        return fault(
            f"{target_id} is not marked **Template**; "
            f"mark {target_id} with **Template** if it's "
            f"intended to be satisfiable."
        )
    return None


# Implements: REQ-d00272-T
def copy_name_diagnostic(target_id: str, node: GraphNode | None) -> str:
    """What to tell the author whose reference is the name of a copy.

    *node* is what the graph holds under *target_id* exactly. Where it is a
    copy a ``Satisfies:`` made, the answer names the original it was made
    from; otherwise it is empty. The cause stays the one the reader found:
    the text is not an identifier an author can write.
    """
    if node is None or node.get_field("stereotype") != Stereotype.INSTANCE:
        return ""
    for original in node.iter_children(edge_kinds={EdgeKind.INSTANCE}):
        return (
            f"{target_id} is the name the tool gives a copy of {original.id}, "
            f"and a copy's name is not an identifier a reference can carry. "
            f"Name {original.id} instead."
        )
    return ""
