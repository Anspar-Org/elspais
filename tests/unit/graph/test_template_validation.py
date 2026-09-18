# Verifies: REQ-p00014-G
"""In-repo validation matrix for the ``**Template**`` marker.

The builder enforces the static validation matrix of REQ-p00014-G at build
time. Each invalid combination produces a typed ``ReferenceFault`` with a
``diagnostic`` field that explains the rule and how the author can fix it,
and the refused edge never lands in the graph.

The matrix covered here:

1. ``Satisfies: X`` where X exists but is NOT marked ``**Template**`` -> error.
2. ``Satisfies: X`` where X is stereotype INSTANCE -> chained instantiation
   error.
3. ``Refines: X`` where X is TEMPLATE, from a REQ not itself marked
   ``**Template**`` -> error (a template's refiners must themselves be
   templates).
4. ``Refines: X`` where X is stereotype INSTANCE -> instance-content-readonly
   error.
5. ``Implements: X`` (from CODE) where X is stereotype INSTANCE -> composite-
   IDs-not-authoring-syntax error.
6. ``Verifies: X`` (from TEST) where X is stereotype INSTANCE -> same as 5.
7. REQ marked ``**Template**`` that declares ``Implements:`` metadata, or
   ``Refines:`` metadata targeting a node outside its own template subtree
   -> error.

Explicitly OK (do NOT raise):

- ``Refines: X`` where X is TEMPLATE, from a REQ marked ``**Template**``:
  the subtree-forming edge (REQ-p00014-B, -M).
- ``Implements: X`` (CODE) where X is TEMPLATE: cross-cutting evidence.
- ``Verifies: X`` (TEST) where X is TEMPLATE: cross-cutting evidence.
"""

from __future__ import annotations

import pytest

from elspais.graph.relations import EdgeKind, Stereotype
from tests.core.graph_test_helpers import (
    build_graph,
    make_code_ref,
    make_requirement,
    make_test_ref,
)

# ---------------------------------------------------------------------------
# Rule 1: Satisfies against an unmarked target -> broken-ref + diagnostic
# ---------------------------------------------------------------------------


class TestSatisfiesAgainstUnmarkedRaises:
    """Rule 1: ``Satisfies: X`` against a target that isn't ``**Template**``."""

    def test_satisfies_concrete_target_is_broken_ref(self) -> None:
        """REQ-A satisfies REQ-B; REQ-B is concrete -> rule-1 broken-ref."""
        # Target REQ-p00001 is concrete (no template=True).
        concrete_target = make_requirement(
            "REQ-p00001",
            title="Concrete",
            assertions=[{"label": "A", "text": "do thing"}],
        )
        # Source declares Satisfies against unmarked target.
        downstream = make_requirement(
            "REQ-p00002",
            title="Downstream",
            satisfies=["REQ-p00001"],
            assertions=[{"label": "A", "text": "do downstream thing"}],
        )
        graph = build_graph(concrete_target, downstream)

        brs = [
            br
            for br in graph.unresolved_references()
            if br.source_id == "REQ-p00002" and br.edge_kind == "satisfies"
        ]
        assert brs, "expected a satisfies broken-ref"
        assert "not marked **Template**" in brs[0].diagnostic, (
            f"diagnostic should mention the missing Template marker, got: {brs[0].diagnostic!r}"
        )

    def test_unmarked_target_does_not_clone_instance(self) -> None:
        """When the target isn't TEMPLATE, no INSTANCE subtree should appear."""
        concrete_target = make_requirement(
            "REQ-p00001",
            title="Concrete",
            assertions=[{"label": "A", "text": "do thing"}],
        )
        downstream = make_requirement(
            "REQ-p00002",
            title="Downstream",
            satisfies=["REQ-p00001"],
        )
        graph = build_graph(concrete_target, downstream)

        # No instance clone should be created.
        assert graph.find_by_id("REQ-p00002::REQ-p00001") is None


# ---------------------------------------------------------------------------
# Rule 3: Refines TEMPLATE -> broken-ref + diagnostic
# ---------------------------------------------------------------------------


class TestRefinesTemplateRaises:
    """Rule 3: ``Refines: X`` where X is TEMPLATE, from a REQ that is not one."""

    def test_refines_template_is_broken_ref(self) -> None:
        """A concrete REQ refining a template joins no subtree and is refused."""
        template = make_requirement(
            "REQ-p00001",
            title="Template",
            template=True,
            assertions=[{"label": "A", "text": "be templated"}],
        )
        refiner = make_requirement(
            "REQ-p00002",
            title="Refiner",
            refines=["REQ-p00001"],
            assertions=[{"label": "A", "text": "refine"}],
        )
        graph = build_graph(template, refiner)

        brs = [
            br
            for br in graph.unresolved_references()
            if br.source_id == "REQ-p00002" and br.edge_kind == "refines"
        ]
        # A concrete REQ refining a template is ONE mistake -> ONE broken-ref
        # (previously rules 3 and 8 both fired, reporting the same edge twice).
        assert len(brs) == 1, f"expected exactly one refines broken-ref, got {brs!r}"
        assert "is a Template" in brs[0].diagnostic and "Satisfies:" in brs[0].diagnostic, (
            f"diagnostic should name the template rule and the Satisfies: remedy, "
            f"got: {brs[0].diagnostic!r}"
        )

    def test_ops_refines_prd_template_single_broken_ref_with_remedy(self) -> None:
        # Verifies: REQ-p00014-G
        """An OPS REQ refining a PRD ``**Template**`` is ONE mistake.

        This exercises a different level combination (OPS -> PRD) than
        ``test_refines_template_is_broken_ref`` (same-level PRD -> PRD) to
        confirm one refused edge is one report whatever the hierarchy depth.
        The diagnostic must name both things the author may have meant: mark
        the refiner ``**Template**`` to decompose the template, or declare
        ``Satisfies:`` to instantiate it.
        """
        prd_template = make_requirement(
            "REQ-p00001",
            title="PRD Template",
            template=True,
            assertions=[{"label": "A", "text": "be templated"}],
        )
        ops_refiner = make_requirement(
            "REQ-o00002",
            title="Ops Refiner",
            level="OPS",
            refines=["REQ-p00001"],
            assertions=[{"label": "A", "text": "refine at ops level"}],
        )
        graph = build_graph(prd_template, ops_refiner)

        brs = [
            br
            for br in graph.unresolved_references()
            if br.source_id == "REQ-o00002" and br.edge_kind == "refines"
        ]
        assert len(brs) == 1, f"expected exactly one refines broken-ref, got {brs!r}"
        diag = brs[0].diagnostic
        assert "is a Template" in diag, f"diagnostic should name the template rule, got: {diag!r}"
        assert "Mark REQ-o00002 **Template**" in diag and "Satisfies: REQ-p00001" in diag, (
            f"diagnostic should offer both remedies, marking the refiner **Template** "
            f"and declaring Satisfies:, got: {diag!r}"
        )
        template_node = graph.find_by_id("REQ-p00001")
        assert not any(e.kind == EdgeKind.REFINES for e in template_node.iter_outgoing_edges()), (
            "a refused Refines: must not land as an edge"
        )


# ---------------------------------------------------------------------------
# Rule 4: Refines INSTANCE -> broken-ref + diagnostic
# ---------------------------------------------------------------------------


class TestRefinesInstanceRaises:
    """Rule 4: Refining an instance is not supported.

    Instance subtrees are read-only synthetic content with no canonical
    on-disk identifier. The recommended pattern is ``Satisfies:`` the
    template AND ``Refines:`` a concrete REQ in your own repo.
    """

    def test_refines_composite_instance_is_broken_ref(self) -> None:
        """Targeting a composite instance ID via Refines errors out."""
        template = make_requirement(
            "REQ-p00001",
            title="Template",
            template=True,
            assertions=[{"label": "A", "text": "be templated"}],
        )
        concrete_satisfier = make_requirement(
            "REQ-p00002",
            title="Concrete Satisfier",
            satisfies=["REQ-p00001"],
            assertions=[{"label": "A", "text": "satisfy"}],
        )
        # REQ-p00003 tries to refine the INSTANCE clone REQ-p00002::REQ-p00001.
        refiner_of_instance = make_requirement(
            "REQ-p00003",
            title="Refiner Of Instance",
            refines=["REQ-p00002::REQ-p00001"],
            assertions=[{"label": "A", "text": "refine instance"}],
        )
        graph = build_graph(template, concrete_satisfier, refiner_of_instance)

        brs = [
            br
            for br in graph.unresolved_references()
            if br.source_id == "REQ-p00003" and br.edge_kind == "refines"
        ]
        assert brs, "expected a refines broken-ref against the instance"
        diag = brs[0].diagnostic
        assert "Refining instance content is not supported" in diag, (
            f"diagnostic should explain the rule, got: {diag!r}"
        )
        # Diagnostic should point users at the recommended pattern.
        assert "Satisfies:" in diag and "Refines:" in diag, (
            f"diagnostic should sketch the satisfier+refines-concrete pattern, got: {diag!r}"
        )


# ---------------------------------------------------------------------------
# Rule 7: Template declaring Implements/Refines metadata
# ---------------------------------------------------------------------------


class TestTemplateWithBehaviouralMetadataRaises:
    """Rule 7: a template's Implements:/Refines: may not reach outside its subtree."""

    def test_template_with_implements_metadata_errors(self) -> None:
        """A template with Implements: metadata produces a rule-7 broken-ref.

        Refines: is the one edge that forms a template subtree, so an
        Implements: declared by a template reaches outside it whatever it
        names.
        """
        other = make_requirement(
            "REQ-p00002",
            title="Other",
            assertions=[{"label": "A", "text": "exist"}],
        )
        template_with_impl = make_requirement(
            "REQ-p00001",
            title="Template",
            template=True,
            implements=["REQ-p00002"],
            assertions=[{"label": "A", "text": "be templated"}],
        )
        graph = build_graph(other, template_with_impl)

        brs = [br for br in graph.unresolved_references() if br.source_id == "REQ-p00001"]
        assert brs, "expected at least one broken-ref on REQ-p00001"
        assert any("Templates are pure specs" in br.diagnostic for br in brs), (
            f"diagnostics: {[br.diagnostic for br in brs]!r}"
        )

    @pytest.mark.parametrize("target", ["REQ-p00002", "REQ-p00002-A"])
    def test_template_refining_concrete_req_errors(self, target: str) -> None:
        """A template refining a concrete REQ, or its *Assertion*, reaches outside its subtree."""
        other = make_requirement(
            "REQ-p00002",
            title="Other",
            assertions=[{"label": "A", "text": "exist"}],
        )
        template_with_refines = make_requirement(
            "REQ-p00001",
            title="Template",
            template=True,
            refines=[target],
            assertions=[{"label": "A", "text": "be templated"}],
        )
        graph = build_graph(other, template_with_refines)

        brs = [
            br
            for br in graph.unresolved_references()
            if br.source_id == "REQ-p00001" and br.edge_kind == "refines"
        ]
        assert len(brs) == 1, f"expected exactly one refines broken-ref, got {brs!r}"
        diag = brs[0].diagnostic
        assert "own template subtree" in diag and f"Mark {target} **Template**" in diag, (
            f"diagnostic should name the subtree rule and the remedy, got: {diag!r}"
        )
        other_node = graph.find_by_id("REQ-p00002")
        assert not any(e.kind == EdgeKind.REFINES for e in other_node.iter_outgoing_edges()), (
            "a refused Refines: must not land as an edge"
        )


# ---------------------------------------------------------------------------
# Inbound Refines against a template: refused from a concrete REQ, the
# subtree-forming edge from another template
# ---------------------------------------------------------------------------


class TestTemplateInboundRefines:
    """A template's refiners must themselves be templates (REQ-p00014-G)."""

    def test_template_targeted_by_refines_errors(self) -> None:
        """An inbound Refines from a concrete REQ against a template is refused."""
        template = make_requirement(
            "REQ-p00001",
            title="Template",
            template=True,
            assertions=[{"label": "A", "text": "be templated"}],
        )
        child = make_requirement(
            "REQ-p00002",
            title="Child",
            level="OPS",
            refines=["REQ-p00001"],
            assertions=[{"label": "A", "text": "extend"}],
        )
        graph = build_graph(template, child)

        brs = [
            br
            for br in graph.unresolved_references()
            if br.target_id == "REQ-p00001" and br.edge_kind == "refines"
        ]
        assert len(brs) == 1, f"expected exactly one refines broken-ref, got {brs!r}"
        assert "is a Template" in brs[0].diagnostic and "Satisfies:" in brs[0].diagnostic, (
            f"diagnostic should name the template rule and the Satisfies: remedy, "
            f"got: {brs[0].diagnostic!r}"
        )

    # Verifies: REQ-p00014-B, REQ-p00014-G, REQ-p00014-M
    def test_template_refined_by_another_template_is_legal(self) -> None:
        """Template-to-template Refines: is the subtree-forming edge.

        A template is a subtree: template-marked REQs refine other
        template-marked REQs to decompose one obligation into levels of
        detail. The edge lands without a fault, and a Satisfies: against the
        root clones the whole subtree with the intra-subtree REFINES edge
        recreated on the clones.
        """
        template_root = make_requirement(
            "REQ-p00001",
            title="Template Root",
            template=True,
            assertions=[{"label": "A", "text": "root obligation"}],
        )
        template_refiner = make_requirement(
            "REQ-p00002",
            title="Template Refiner",
            level="OPS",
            template=True,
            refines=["REQ-p00001"],
            assertions=[{"label": "A", "text": "refine obligation"}],
        )
        satisfier = make_requirement(
            "REQ-p00003",
            title="Satisfier",
            satisfies=["REQ-p00001"],
            assertions=[{"label": "A", "text": "own obligation"}],
        )
        graph = build_graph(template_root, template_refiner, satisfier)

        faults = [
            (br.source_id, br.target_id, br.diagnostic) for br in graph.unresolved_references()
        ]
        assert not faults, f"template refining a template must produce no fault, got: {faults!r}"
        root = graph.find_by_id("REQ-p00001")
        refines = [e for e in root.iter_outgoing_edges() if e.kind == EdgeKind.REFINES]
        assert [e.target.id for e in refines] == ["REQ-p00002"], (
            "the template root must hold the REFINES edge to its template refiner"
        )

        for composite in (
            "REQ-p00003::REQ-p00001",
            "REQ-p00003::REQ-p00001-A",
            "REQ-p00003::REQ-p00002",
            "REQ-p00003::REQ-p00002-A",
        ):
            clone = graph.find_by_id(composite)
            assert clone is not None, f"expected {composite} in the cloned subtree"
            assert clone.get_field("stereotype") == Stereotype.INSTANCE
        cloned_root = graph.find_by_id("REQ-p00003::REQ-p00001")
        cloned_refines = [
            e for e in cloned_root.iter_outgoing_edges() if e.kind == EdgeKind.REFINES
        ]
        assert [e.target.id for e in cloned_refines] == ["REQ-p00003::REQ-p00002"], (
            "the intra-subtree REFINES edge must be recreated on the clones"
        )
        refiner_clone = graph.find_by_id("REQ-p00003::REQ-p00002")
        assert [
            e.target.id for e in refiner_clone.iter_outgoing_edges() if e.kind == EdgeKind.INSTANCE
        ] == ["REQ-p00002"]


# ---------------------------------------------------------------------------
# The shape of a cloned template subtree (REQ-p00014-B, -M)
# ---------------------------------------------------------------------------


def _subtree(root_id: str, *members: tuple[str, str | None]) -> list:
    """Build a template subtree: ``root_id`` plus (id, refines-target) members."""
    nodes = [
        make_requirement(
            root_id,
            title=f"Template {root_id}",
            template=True,
            assertions=[{"label": "A", "text": f"{root_id} obligation"}],
        )
    ]
    for member_id, target in members:
        nodes.append(
            make_requirement(
                member_id,
                title=f"Template {member_id}",
                template=True,
                refines=[target] if target else None,
                assertions=[{"label": "A", "text": f"{member_id} obligation"}],
            )
        )
    return nodes


class TestClonedSubtreeShape:
    """What a Satisfies: clones, and which edges the clones carry."""

    # Verifies: REQ-p00014-B
    def test_descendants_are_cloned_recursively(self) -> None:
        """A three-level chain is cloned whole from a Satisfies: against the root."""
        satisfier = make_requirement("REQ-p00009", title="Satisfier", satisfies=["REQ-p00001"])
        graph = build_graph(
            *_subtree("REQ-p00001", ("REQ-p00002", "REQ-p00001"), ("REQ-p00003", "REQ-p00002")),
            satisfier,
        )
        assert not list(graph.unresolved_references())
        for original in ("REQ-p00001", "REQ-p00002", "REQ-p00003"):
            assert graph.find_by_id(f"REQ-p00009::{original}") is not None, original
            assert graph.find_by_id(f"REQ-p00009::{original}-A") is not None, original
        mid_clone = graph.find_by_id("REQ-p00009::REQ-p00002")
        assert [
            e.target.id for e in mid_clone.iter_outgoing_edges() if e.kind == EdgeKind.REFINES
        ] == ["REQ-p00009::REQ-p00003"]

    # Verifies: REQ-p00014-B
    def test_satisfies_against_interior_member_clones_its_subtree_only(self) -> None:
        """Declaring against an interior member is a narrower declaration."""
        satisfier = make_requirement("REQ-p00009", title="Satisfier", satisfies=["REQ-p00002"])
        graph = build_graph(
            *_subtree("REQ-p00001", ("REQ-p00002", "REQ-p00001"), ("REQ-p00003", "REQ-p00002")),
            satisfier,
        )
        assert not list(graph.unresolved_references())
        assert graph.find_by_id("REQ-p00009::REQ-p00002") is not None
        assert graph.find_by_id("REQ-p00009::REQ-p00003") is not None
        assert graph.find_by_id("REQ-p00009::REQ-p00001") is None, (
            "the member's own ancestor is not part of the subtree rooted at it"
        )
        declaring = graph.find_by_id("REQ-p00009")
        assert [
            e.target.id for e in declaring.iter_outgoing_edges() if e.kind == EdgeKind.SATISFIES
        ] == ["REQ-p00009::REQ-p00002"]

    # Verifies: REQ-p00014-M
    def test_each_cloned_assertion_is_structured_once(self) -> None:
        """A clone holds one STRUCTURES edge per cloned *Assertion*, not two."""
        satisfier = make_requirement("REQ-p00009", title="Satisfier", satisfies=["REQ-p00001"])
        graph = build_graph(*_subtree("REQ-p00001", ("REQ-p00002", "REQ-p00001")), satisfier)
        for composite in ("REQ-p00009::REQ-p00001", "REQ-p00009::REQ-p00002"):
            clone = graph.find_by_id(composite)
            structures = [
                e.target.id for e in clone.iter_outgoing_edges() if e.kind == EdgeKind.STRUCTURES
            ]
            assert structures == [f"{composite}-A"], (
                f"{composite} should structure its one cloned assertion exactly once, "
                f"got {structures!r}"
            )

    # Verifies: REQ-p00014-M
    def test_assertion_targeted_refinement_keeps_its_labels_on_the_clone(self) -> None:
        """A template refining a member's *Assertion* is cloned with the label it named."""
        satisfier = make_requirement("REQ-p00009", title="Satisfier", satisfies=["REQ-p00001"])
        graph = build_graph(*_subtree("REQ-p00001", ("REQ-p00002", "REQ-p00001-A")), satisfier)
        assert not list(graph.unresolved_references())
        root = graph.find_by_id("REQ-p00001")
        (original_edge,) = [e for e in root.iter_outgoing_edges() if e.kind == EdgeKind.REFINES]
        assert original_edge.assertion_targets == ["A"]
        cloned_root = graph.find_by_id("REQ-p00009::REQ-p00001")
        (cloned_edge,) = [
            e for e in cloned_root.iter_outgoing_edges() if e.kind == EdgeKind.REFINES
        ]
        assert cloned_edge.target.id == "REQ-p00009::REQ-p00002"
        assert cloned_edge.assertion_targets == ["A"]

    # Verifies: REQ-p00014-M
    def test_clone_carries_no_edge_the_subtree_does_not_own(self) -> None:
        """Evidence on a template is reached through INSTANCE, never copied onto a clone."""
        satisfier = make_requirement("REQ-p00009", title="Satisfier", satisfies=["REQ-p00001"])
        code = make_code_ref(implements=["REQ-p00002-A"], source_path="src/lib.py", start_line=1)
        graph = build_graph(*_subtree("REQ-p00001", ("REQ-p00002", "REQ-p00001")), satisfier, code)
        refiner_clone = graph.find_by_id("REQ-p00009::REQ-p00002")
        kinds = {e.kind for e in refiner_clone.iter_outgoing_edges()}
        assert kinds == {EdgeKind.INSTANCE, EdgeKind.STRUCTURES}, kinds
        assert not refiner_clone.get_field("refines_refs"), (
            "the reference text the original declared is not a reference the clone declares"
        )


# ---------------------------------------------------------------------------
# Rule 2: chained instantiation (Satisfies inside an instance subtree)
# ---------------------------------------------------------------------------


class TestChainedInstantiationRaises:
    """Rule 2: ``Satisfies:`` against an INSTANCE target."""

    def test_satisfies_target_inside_instance_subtree_errors(self) -> None:
        """Chained instantiation (satisfy a satisfier's instance) is rejected."""
        template = make_requirement(
            "REQ-p00001",
            title="Template",
            template=True,
            assertions=[{"label": "A", "text": "be templated"}],
        )
        concrete_satisfier = make_requirement(
            "REQ-p00002",
            title="Concrete Satisfier",
            satisfies=["REQ-p00001"],
            assertions=[{"label": "A", "text": "satisfy"}],
        )
        # REQ-p00003 tries to Satisfies the cloned INSTANCE root.
        chained = make_requirement(
            "REQ-p00003",
            title="Chained",
            satisfies=["REQ-p00002::REQ-p00001"],
            assertions=[{"label": "A", "text": "chained"}],
        )
        graph = build_graph(template, concrete_satisfier, chained)

        brs = [
            br
            for br in graph.unresolved_references()
            if br.source_id == "REQ-p00003" and br.edge_kind == "satisfies"
        ]
        assert brs, "expected a satisfies broken-ref for chained instantiation"
        assert any("Chained instantiation" in br.diagnostic for br in brs), (
            f"diagnostics: {[br.diagnostic for br in brs]!r}"
        )

        # And the chained instance must NOT have been cloned a second time.
        # No node with the doubly-composite ID should exist.
        chained_clone = graph.find_by_id("REQ-p00003::REQ-p00002::REQ-p00001")
        assert chained_clone is None, "chained instantiation must not produce a second-level clone"


# ---------------------------------------------------------------------------
# Explicitly OK: CODE Implements: TEMPLATE -> cross-cutting evidence
# ---------------------------------------------------------------------------


class TestImplementsTemplateIsLegal:
    """``Implements: TEMPLATE-A`` from CODE is cross-cutting evidence (legal).

    This is the post-Phase-2 behaviour: the removed
    ``_attribute_template_refs`` redirection pass is gone, so the
    IMPLEMENTS edge lands directly on the template assertion.
    """

    def test_code_implements_template_assertion_is_ok(self) -> None:
        """No broken-ref, and the IMPLEMENTS edge lands on the template."""
        template = make_requirement(
            "REQ-p00001",
            title="Template",
            template=True,
            assertions=[{"label": "A", "text": "parse"}],
        )
        code = make_code_ref(
            implements=["REQ-p00001-A"],
            source_path="src/library.py",
            start_line=1,
        )
        graph = build_graph(template, code)

        # No broken-ref for IMPLEMENTS.
        impl_brs = [br for br in graph.unresolved_references() if br.edge_kind == "implements"]
        assert not impl_brs, f"Implements: TEMPLATE should be legal, got broken-refs: {impl_brs!r}"

        # Template REQ should have an outgoing IMPLEMENTS edge to the CODE
        # implementer for assertion A. Note: IMPLEMENTS is stored as
        # `target.link(source, IMPLEMENTS)` so the REQ is the parent and the
        # CODE node is the child — `iter_outgoing_edges()` from the REQ
        # correctly traverses to its implementer.
        template_req = graph.find_by_id("REQ-p00001")
        assert template_req is not None
        impl_in = [e for e in template_req.iter_outgoing_edges() if e.kind == EdgeKind.IMPLEMENTS]
        assert impl_in, "expected an IMPLEMENTS edge from the template REQ to the code node"
        # The edge target should be the code node.
        assert any("src/library.py" in e.target.id for e in impl_in)

    def test_test_verifies_template_assertion_is_ok(self) -> None:
        """``Verifies: TEMPLATE-A`` from TEST is legal too."""
        template = make_requirement(
            "REQ-p00001",
            title="Template",
            template=True,
            assertions=[{"label": "A", "text": "parse"}],
        )
        test_ref = make_test_ref(
            verifies=["REQ-p00001-A"],
            source_path="tests/test_library.py",
            start_line=1,
            function_name="test_parse",
        )
        graph = build_graph(template, test_ref)

        ver_brs = [br for br in graph.unresolved_references() if br.edge_kind == "verifies"]
        assert not ver_brs, f"Verifies: TEMPLATE should be legal, got broken-refs: {ver_brs!r}"


# ---------------------------------------------------------------------------
# Rule 5: CODE Implements: INSTANCE -> broken-ref + diagnostic
# ---------------------------------------------------------------------------


class TestImplementsInstanceIsError:
    """Rule 5: Composite IDs are not authoring syntax for CODE."""

    def test_code_implements_composite_instance_errors(self) -> None:
        """Implements: APP::LIB-A from CODE produces a rule-5 broken-ref."""
        template = make_requirement(
            "REQ-p00001",
            title="Template",
            template=True,
            assertions=[{"label": "A", "text": "parse"}],
        )
        satisfier = make_requirement(
            "REQ-p00002",
            title="Satisfier",
            satisfies=["REQ-p00001"],
            assertions=[{"label": "A", "text": "be specific"}],
        )
        code = make_code_ref(
            implements=["REQ-p00002::REQ-p00001-A"],
            source_path="src/app.py",
            start_line=1,
        )
        graph = build_graph(template, satisfier, code)

        brs = [
            br
            for br in graph.unresolved_references()
            if br.edge_kind == "implements" and "REQ-p00002::REQ-p00001" in br.target_id
        ]
        assert brs, "expected a rule-5 broken-ref for implements -> instance"
        diag = brs[0].diagnostic
        assert "Instance assertions have no canonical on-disk identifier" in diag, (
            f"diagnostic should explain the rule, got: {diag!r}"
        )


# ---------------------------------------------------------------------------
# Rule 6: TEST Verifies: INSTANCE -> broken-ref + diagnostic
# ---------------------------------------------------------------------------


class TestVerifiesInstanceIsError:
    """Rule 6: same reasoning as rule 5, but for TEST sources."""

    def test_test_verifies_composite_instance_errors(self) -> None:
        """Verifies: APP::LIB-A from TEST produces a rule-6 broken-ref."""
        template = make_requirement(
            "REQ-p00001",
            title="Template",
            template=True,
            assertions=[{"label": "A", "text": "parse"}],
        )
        satisfier = make_requirement(
            "REQ-p00002",
            title="Satisfier",
            satisfies=["REQ-p00001"],
            assertions=[{"label": "A", "text": "be specific"}],
        )
        test_ref = make_test_ref(
            verifies=["REQ-p00002::REQ-p00001-A"],
            source_path="tests/test_app.py",
            start_line=1,
            function_name="test_parse",
        )
        graph = build_graph(template, satisfier, test_ref)

        brs = [
            br
            for br in graph.unresolved_references()
            if br.edge_kind == "verifies" and "REQ-p00002::REQ-p00001" in br.target_id
        ]
        assert brs, "expected a rule-6 broken-ref for verifies -> instance"
        diag = brs[0].diagnostic
        assert "Instance assertions have no canonical on-disk identifier" in diag, (
            f"diagnostic should explain the rule, got: {diag!r}"
        )


# ---------------------------------------------------------------------------
# Lenient: unused-template warning (Phase 4/5 follow-up)
# ---------------------------------------------------------------------------


class TestUnusedTemplateWarns:
    """Unused templates SHOULD emit a non-fatal warning (lenient until Phase 4)."""

    @pytest.mark.skip(
        reason="Phase 4/5 — warnings channel not yet implemented; "
        "revisit when iter_warnings() lands"
    )
    def test_unused_template_warning_present(self) -> None:
        """A template with no inbound Satisfies SHOULD warn (Phase 4 follow-up).

        The dedicated federated-diagnostics warnings channel does not yet
        exist (it's part of Phase 4/5 of CUR-1353). When that API lands,
        removing the skip marker will reveal a real test against the
        warnings channel.
        """
        template = make_requirement(
            "REQ-p00001",
            title="Template",
            template=True,
            assertions=[{"label": "A", "text": "be templated"}],
        )
        graph = build_graph(template)

        node = graph.find_by_id("REQ-p00001")
        assert node is not None
        assert node.get_field("stereotype") == Stereotype.TEMPLATE

        warnings_iter = getattr(graph, "iter_warnings", lambda: [])
        warnings = list(warnings_iter())
        assert any("REQ-p00001" in str(w) for w in warnings)
