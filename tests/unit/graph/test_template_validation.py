# Verifies: REQ-p00014-G
"""In-repo validation matrix for the ``**Template**`` marker (CUR-1353 Phase 2).

Phase 2 of CUR-1353 enforces the static validation matrix from the
cross-repo-template spec. Each invalid combination produces a typed
``BrokenReference`` with a ``diagnostic`` field that explains the rule
and how the author can fix it.

The matrix covered here:

1. ``Satisfies: X`` where X exists but is NOT marked ``**Template**`` -> error.
2. ``Satisfies: X`` where X is stereotype INSTANCE -> chained instantiation
   error.
3. ``Refines: X`` where X is stereotype TEMPLATE -> compositing-templates
   error.
4. ``Refines: X`` where X is stereotype INSTANCE -> instance-content-readonly
   error.
5. ``Implements: X`` (from CODE) where X is stereotype INSTANCE -> composite-
   IDs-not-authoring-syntax error.
6. ``Verifies: X`` (from TEST) where X is stereotype INSTANCE -> same as 5.
7. REQ marked ``**Template**`` that declares ``Refines:``/``Implements:``
   metadata -> templates-are-pure-specs error.
8. REQ marked ``**Template**`` that is targeted by inbound ``Refines:`` ->
   templates-may-not-have-descendants error.

Explicitly OK (do NOT raise):

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
            for br in graph.broken_references()
            if br.source_id == "REQ-p00002" and br.edge_kind == "satisfies"
        ]
        assert brs, "expected a satisfies broken-ref"
        assert "not marked **Template**" in brs[0].diagnostic, (
            f"diagnostic should mention the missing Template marker, got: " f"{brs[0].diagnostic!r}"
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
    """Rule 3: ``Refines: X`` where X is TEMPLATE."""

    def test_refines_template_is_broken_ref(self) -> None:
        """Compositing templates via Refines is not supported."""
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
            for br in graph.broken_references()
            if br.source_id == "REQ-p00002" and br.edge_kind == "refines"
        ]
        assert brs, "expected a refines broken-ref"
        assert any(
            "Compositing templates is not supported" in br.diagnostic for br in brs
        ), f"diagnostics: {[br.diagnostic for br in brs]!r}"


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
            for br in graph.broken_references()
            if br.source_id == "REQ-p00003" and br.edge_kind == "refines"
        ]
        assert brs, "expected a refines broken-ref against the instance"
        diag = brs[0].diagnostic
        assert (
            "Refining instance content is not supported" in diag
        ), f"diagnostic should explain the rule, got: {diag!r}"
        # Diagnostic should point users at the recommended pattern.
        assert "Satisfies:" in diag and "Refines:" in diag, (
            f"diagnostic should sketch the satisfier+refines-concrete pattern, " f"got: {diag!r}"
        )


# ---------------------------------------------------------------------------
# Rule 7: Template declaring Implements/Refines metadata
# ---------------------------------------------------------------------------


class TestTemplateWithBehaviouralMetadataRaises:
    """Rule 7: Templates are pure specs; they may not declare behavioural claims."""

    def test_template_with_implements_metadata_errors(self) -> None:
        """A template with Implements: metadata produces a rule-7 broken-ref."""
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

        brs = [br for br in graph.broken_references() if br.source_id == "REQ-p00001"]
        assert brs, "expected at least one broken-ref on REQ-p00001"
        assert any(
            "Templates are pure specs" in br.diagnostic for br in brs
        ), f"diagnostics: {[br.diagnostic for br in brs]!r}"

    def test_template_with_refines_metadata_errors(self) -> None:
        """A template with Refines: metadata produces a rule-7 broken-ref."""
        other = make_requirement(
            "REQ-p00002",
            title="Other",
            assertions=[{"label": "A", "text": "exist"}],
        )
        template_with_refines = make_requirement(
            "REQ-p00001",
            title="Template",
            template=True,
            refines=["REQ-p00002"],
            assertions=[{"label": "A", "text": "be templated"}],
        )
        graph = build_graph(other, template_with_refines)

        brs = [br for br in graph.broken_references() if br.source_id == "REQ-p00001"]
        assert brs, "expected at least one broken-ref on REQ-p00001"
        assert any(
            "Templates are pure specs" in br.diagnostic for br in brs
        ), f"diagnostics: {[br.diagnostic for br in brs]!r}"


# ---------------------------------------------------------------------------
# Rule 8: Template is target of inbound Refines
# ---------------------------------------------------------------------------


class TestTemplateInboundRefinesRaises:
    """Rule 8: Templates may not have descendants via Refines."""

    def test_template_targeted_by_refines_errors(self) -> None:
        """An inbound Refines against a template produces a rule-8 broken-ref."""
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
            for br in graph.broken_references()
            if br.target_id == "REQ-p00001" and br.edge_kind == "refines"
        ]
        assert brs, "expected a refines broken-ref targeting the template"
        assert any(
            "Templates may not have descendants" in br.diagnostic for br in brs
        ), f"diagnostics: {[br.diagnostic for br in brs]!r}"

    def test_template_targeted_by_refines_from_another_template_errors(self) -> None:
        """Templates may not refine other templates either (single-REQ scope).

        CUR-1353 Phase 2 locks single-REQ scope: a template is one REQ root
        plus its directly-attached assertions. ANY inbound REFINES against a
        TEMPLATE is invalid, including from another TEMPLATE -- the
        "within-subtree refinement" carve-out is removed.
        """
        template_root = make_requirement(
            "REQ-p00001",
            title="Template Root",
            template=True,
            assertions=[{"label": "A", "text": "root obligation"}],
        )
        # A second template marked **Template** that refines the first.
        template_refiner = make_requirement(
            "REQ-p00002",
            title="Template Refiner",
            level="OPS",
            template=True,
            refines=["REQ-p00001"],
            assertions=[{"label": "A", "text": "refine obligation"}],
        )
        graph = build_graph(template_root, template_refiner)

        # Rule 8: an inbound Refines against the template target.
        rule8_brs = [
            br
            for br in graph.broken_references()
            if br.target_id == "REQ-p00001" and br.edge_kind == "refines"
        ]
        assert rule8_brs, "expected a rule-8 refines broken-ref against the template target"
        assert any(
            "Templates may not have descendants" in br.diagnostic for br in rule8_brs
        ), f"rule-8 diagnostics: {[br.diagnostic for br in rule8_brs]!r}"

        # Rule 7: the refining template declared behavioural metadata
        # (Refines:) -- this is also flagged because templates are pure specs.
        rule7_brs = [
            br
            for br in graph.broken_references()
            if br.source_id == "REQ-p00002" and br.edge_kind == "refines"
        ]
        assert rule7_brs, "expected a rule-7 refines broken-ref on the refining template"
        assert any(
            "Templates are pure specs" in br.diagnostic for br in rule7_brs
        ), f"rule-7 diagnostics: {[br.diagnostic for br in rule7_brs]!r}"

        # And no INSTANCE subtree should appear since both templates are
        # invalid-target-perspectives; no Satisfies declaration here either.
        assert graph.find_by_id("REQ-p00002::REQ-p00001") is None


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
            for br in graph.broken_references()
            if br.source_id == "REQ-p00003" and br.edge_kind == "satisfies"
        ]
        assert brs, "expected a satisfies broken-ref for chained instantiation"
        assert any(
            "Chained instantiation" in br.diagnostic for br in brs
        ), f"diagnostics: {[br.diagnostic for br in brs]!r}"

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
        impl_brs = [br for br in graph.broken_references() if br.edge_kind == "implements"]
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

        ver_brs = [br for br in graph.broken_references() if br.edge_kind == "verifies"]
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
            for br in graph.broken_references()
            if br.edge_kind == "implements" and "REQ-p00002::REQ-p00001" in br.target_id
        ]
        assert brs, "expected a rule-5 broken-ref for implements -> instance"
        diag = brs[0].diagnostic
        assert (
            "Instance assertions have no canonical on-disk identifier" in diag
        ), f"diagnostic should explain the rule, got: {diag!r}"


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
            for br in graph.broken_references()
            if br.edge_kind == "verifies" and "REQ-p00002::REQ-p00001" in br.target_id
        ]
        assert brs, "expected a rule-6 broken-ref for verifies -> instance"
        diag = brs[0].diagnostic
        assert (
            "Instance assertions have no canonical on-disk identifier" in diag
        ), f"diagnostic should explain the rule, got: {diag!r}"


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
