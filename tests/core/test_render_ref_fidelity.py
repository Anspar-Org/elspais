# Verifies: REQ-d00132
"""Render-fidelity tests for edge-derived reference lists (CUR-1829 Task 9, Defect 3).

Validates REQ-d00132-F: renders derive Implements/Refines from live graph
edges -- deleting a node's last edge must remove the reference from the
rendered text and move the node's concurrency version.

Validates REQ-d00132-G: reference entries that never resolved to graph edges
(broken references) keep rendering -- alone, alongside edge-derived refs, and
through mutations -- so a rewrite never silently deletes an author's
unresolved reference.

These tests target the fallback in ``_derive_refs_for_edge_kind``
(graph/render.py), which resurrects the parsed ``implements_refs``/
``refines_refs`` field whenever zero matching edges exist and drops broken
refs whenever at least one edge exists. Required behavior is the union:
edge-derived refs plus unresolved leftovers, always.

The broken-reference cases require parse-time broken refs, which the
canonical fixture does not carry, so this module builds a small on-disk
fixture of its own (per test-writing conventions: custom graphs are
justified for invalid-input features).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from elspais.graph.factory import build_graph
from elspais.graph.GraphNode import make_file_id
from elspais.graph.relations import EdgeKind
from elspais.graph.render import node_version, render_file, render_node

# One spec file covering every scenario. IDs use the default REQ-p/o
# patterns; REQ-?77777 / REQ-?88888 style targets match the ID pattern but
# do not exist, so the builder records them as (hard) broken references.
SPEC_CONTENT = """\
# Render Fidelity Fixture

## REQ-p00001: Parent Anchor

**Level**: PRD | **Status**: Active | **Implements**: -

The parent SHALL anchor the hierarchy.

### Assertions

A. The parent SHALL expose capability alpha.

B. The parent SHALL expose capability beta.

*End* *Parent Anchor* | **Hash**: 00000000

---

## REQ-o00001: Valid Implementer

**Level**: OPS | **Status**: Active | **Implements**: REQ-p00001

The implementer SHALL depend on the parent.

### Assertions

A. The implementer SHALL do its work.

*End* *Valid Implementer* | **Hash**: 00000000

---

## REQ-o00002: Valid Refiner

**Level**: OPS | **Status**: Active | **Refines**: REQ-o00001

The refiner SHALL add detail to the implementer.

### Assertions

A. The refiner SHALL add detail.

*End* *Valid Refiner* | **Hash**: 00000000

---

## REQ-o00003: Broken Implementer

**Level**: OPS | **Status**: Active | **Implements**: REQ-p77777

This requirement's only reference is a typo that never resolves.

### Assertions

A. The broken implementer SHALL still be authored.

*End* *Broken Implementer* | **Hash**: 00000000

---

## REQ-o00004: Broken Refiner

**Level**: OPS | **Status**: Active | **Refines**: REQ-o77777

This requirement's only refines reference is a typo that never resolves.

### Assertions

A. The broken refiner SHALL still be authored.

*End* *Broken Refiner* | **Hash**: 00000000

---

## REQ-o00005: Mixed Implementer

**Level**: OPS | **Status**: Active | **Implements**: REQ-p00001, REQ-p77777

One implements reference resolves, the other is a typo.

### Assertions

A. The mixed implementer SHALL keep both citations.

*End* *Mixed Implementer* | **Hash**: 00000000

---

## REQ-o00006: Mixed Refiner

**Level**: OPS | **Status**: Active | **Refines**: REQ-o00001, REQ-o77777

One refines reference resolves, the other is a typo.

### Assertions

A. The mixed refiner SHALL keep both citations.

*End* *Mixed Refiner* | **Hash**: 00000000

---

## REQ-o00007: Partial Multi Implementer

**Level**: OPS | **Status**: Active | **Implements**: REQ-p00001-A+Z

Assertion A exists on the parent; assertion Z does not.

### Assertions

A. The partial implementer SHALL keep the broken expansion.

*End* *Partial Multi Implementer* | **Hash**: 00000000

---

## REQ-o00008: Unreferenced Requirement

**Level**: OPS | **Status**: Active | **Implements**: -

Starts with no references at all; mutations add them.

### Assertions

A. The unreferenced requirement SHALL start clean.

*End* *Unreferenced Requirement* | **Hash**: 00000000

---
"""

CONFIG_CONTENT = """\
[project]
name = "render-fidelity"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]
"""


@pytest.fixture()
def fidelity_graph(tmp_path: Path):
    """Build a FederatedGraph from the on-disk fixture in tmp_path."""
    (tmp_path / ".elspais.toml").write_text(CONFIG_CONTENT, encoding="utf-8")
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    (spec_dir / "reqs.md").write_text(SPEC_CONTENT, encoding="utf-8")
    return build_graph(
        config_path=tmp_path / ".elspais.toml",
        repo_root=tmp_path,
        scan_code=False,
        scan_tests=False,
    )


def _node(graph, node_id: str):
    node = graph.find_by_id(node_id)
    assert node is not None, f"fixture node {node_id} is missing"
    return node


# (child, parent) pairs where the child's ONLY traceability edge of the
# given kind -- and its only rendered reference -- targets the parent.
LAST_EDGE_CASES = [
    pytest.param("REQ-o00001", "REQ-p00001", id="implements"),
    pytest.param("REQ-o00002", "REQ-o00001", id="refines"),
]

# (child, broken_ref) pairs where the child's only reference is broken.
BROKEN_ALONE_CASES = [
    pytest.param("REQ-o00003", "REQ-p77777", id="implements"),
    pytest.param("REQ-o00004", "REQ-o77777", id="refines"),
]

# (child, valid_ref, broken_ref) pairs mixing one resolved and one broken ref.
MIXED_CASES = [
    pytest.param("REQ-o00005", "REQ-p00001", "REQ-p77777", id="implements"),
    pytest.param("REQ-o00006", "REQ-o00001", "REQ-o77777", id="refines"),
]


class TestDeleteLastEdgeRenderFidelity:
    """Validates REQ-d00132-F: renders derive references from live edges.

    Deleting the last IMPLEMENTS/REFINES edge must remove the reference from
    the rendered requirement (no fallback resurrection of the parsed field),
    must move the node's concurrency version, and undoing the delete must
    restore both.
    """

    @pytest.mark.parametrize(("child_id", "parent_id"), LAST_EDGE_CASES)
    def test_REQ_d00132_F_delete_last_edge_removes_ref_from_render(
        self, fidelity_graph, child_id: str, parent_id: str
    ):
        """After deleting the only edge, the ref no longer renders."""
        child = _node(fidelity_graph, child_id)
        assert parent_id in render_node(child), "fixture must render the ref before delete"

        fidelity_graph.delete_edge(child_id, parent_id)

        rendered = render_node(child)
        assert parent_id not in rendered, (
            f"deleted the last edge {child_id} -> {parent_id}, but the render "
            f"still cites {parent_id} (stored-field fallback resurrected it)"
        )

    @pytest.mark.parametrize(("child_id", "parent_id"), LAST_EDGE_CASES)
    def test_REQ_d00132_F_delete_last_edge_changes_node_version(
        self, fidelity_graph, child_id: str, parent_id: str
    ):
        """The concurrency version moves when the rendered refs change."""
        child = _node(fidelity_graph, child_id)
        version_before = node_version(child)

        fidelity_graph.delete_edge(child_id, parent_id)

        assert node_version(child) != version_before, (
            f"deleting the last edge {child_id} -> {parent_id} changed the "
            "on-disk representation, so node_version() must change"
        )

    @pytest.mark.parametrize(("child_id", "parent_id"), LAST_EDGE_CASES)
    def test_REQ_d00132_F_undo_delete_restores_ref_and_version(
        self, fidelity_graph, child_id: str, parent_id: str
    ):
        """Undoing the delete restores the rendered ref and the version."""
        child = _node(fidelity_graph, child_id)
        version_before = node_version(child)

        fidelity_graph.delete_edge(child_id, parent_id)
        fidelity_graph.undo_last()

        assert parent_id in render_node(child)
        assert node_version(child) == version_before


class TestBrokenRefRenderPreservation:
    """Validates REQ-d00132-G: unresolved references keep rendering.

    Broken (never-resolved) reference entries must survive rendering both
    when they are the node's only reference and when they coexist with
    edge-derived references, so a file rewrite never silently deletes an
    author's typo'd citation.
    """

    @pytest.mark.parametrize(("child_id", "broken_ref"), BROKEN_ALONE_CASES)
    def test_REQ_d00132_G_broken_ref_alone_still_renders(
        self, fidelity_graph, child_id: str, broken_ref: str
    ):
        """A node whose only ref is broken still renders that ref."""
        child = _node(fidelity_graph, child_id)
        assert broken_ref in render_node(child)

    @pytest.mark.parametrize(("child_id", "valid_ref", "broken_ref"), MIXED_CASES)
    def test_REQ_d00132_G_mixed_valid_and_broken_refs_both_render(
        self, fidelity_graph, child_id: str, valid_ref: str, broken_ref: str
    ):
        """A resolved ref must not evict the broken one from the render."""
        child = _node(fidelity_graph, child_id)
        rendered = render_node(child)
        assert valid_ref in rendered
        assert broken_ref in rendered, (
            f"{child_id} renders only the edge-derived {valid_ref}; the "
            f"author's broken {broken_ref} entry was silently dropped"
        )

    def test_REQ_d00132_G_mixed_broken_ref_survives_file_render(self, fidelity_graph):
        """render_file (the rewrite surface) keeps the broken entries too.

        Each broken target is cited by TWO requirements: one where it is the
        only ref (REQ-o00003/REQ-o00004) and one where it coexists with a
        resolved ref (REQ-o00005/REQ-o00006). Both citations must survive a
        whole-file rewrite, so each broken ID must appear exactly twice.
        """
        file_node = _node(fidelity_graph, make_file_id("REQ", "spec/reqs.md"))
        content = render_file(file_node)
        assert content.count("REQ-p77777") == 2, (
            "the mixed requirement's broken Implements entry was dropped " "from the file rewrite"
        )
        assert content.count("REQ-o77777") == 2, (
            "the mixed requirement's broken Refines entry was dropped " "from the file rewrite"
        )

    def test_REQ_d00132_G_partial_multi_assertion_keeps_broken_expansion(self, fidelity_graph):
        """`Implements: REQ-p00001-A+Z` keeps derived A and broken Z."""
        child = _node(fidelity_graph, "REQ-o00007")
        rendered = render_node(child)
        assert "REQ-p00001-A" in rendered
        assert "REQ-p00001-Z" in rendered, (
            "the resolved A expansion evicted the broken Z expansion from " "the render"
        )


class TestMutationBrokenRefLeftovers:
    """Validates REQ-d00132-G: mutations keep leftover semantics coherent.

    Resolving a broken reference must render the new ref exactly once (no
    duplicate from the leftover); adding an edge to a missing target must
    render the (broken) ref; undoing either restores the prior render.
    """

    def test_REQ_d00132_G_fix_broken_reference_renders_new_ref_once(self, fidelity_graph):
        """fix_broken_reference replaces the broken entry with the real one."""
        child = _node(fidelity_graph, "REQ-o00003")

        fidelity_graph.fix_broken_reference("REQ-o00003", "REQ-p77777", "REQ-p00001")

        rendered = render_node(child)
        assert "REQ-p77777" not in rendered, "the resolved leftover must stop rendering"
        assert rendered.count("REQ-p00001") == 1, (
            "the fixed ref must render exactly once -- not duplicated by a " "stale leftover entry"
        )

    def test_REQ_d00132_G_undo_fix_broken_reference_restores_broken_ref(self, fidelity_graph):
        """Undoing the fix brings the broken entry back into the render."""
        child = _node(fidelity_graph, "REQ-o00003")

        fidelity_graph.fix_broken_reference("REQ-o00003", "REQ-p77777", "REQ-p00001")
        fidelity_graph.undo_last()

        rendered = render_node(child)
        assert "REQ-p77777" in rendered
        assert "REQ-p00001" not in rendered

    def test_REQ_d00132_G_add_edge_to_missing_target_renders_ref(self, fidelity_graph):
        """A mutation-added ref to a nonexistent target still renders."""
        child = _node(fidelity_graph, "REQ-o00008")

        entry = fidelity_graph.add_edge("REQ-o00008", "REQ-p66666", EdgeKind.IMPLEMENTS)
        assert entry.after_state.get("broken") is True

        assert "REQ-p66666" in render_node(child), (
            "add_edge recorded a broken reference but the render does not "
            "cite it -- saving would lose the author's mutation"
        )

    def test_REQ_d00132_G_undo_broken_add_edge_removes_ref_from_render(self, fidelity_graph):
        """Undoing the broken add removes the ref from the render again."""
        child = _node(fidelity_graph, "REQ-o00008")

        fidelity_graph.add_edge("REQ-o00008", "REQ-p66666", EdgeKind.IMPLEMENTS)
        fidelity_graph.undo_last()

        assert "REQ-p66666" not in render_node(child)


# ---------------------------------------------------------------------------
# Rename / delete coherence for broken references and rendered leftovers
# (CUR-1829 Task 9 follow-up defects A/B/C in graph/builder.py)
# ---------------------------------------------------------------------------

# A second on-disk fixture: a **Template** target gives us a broken reference
# whose TARGET EXISTS in the graph (the rule-3/8 rejection records it with a
# diagnostic), so rename_node's broken-ref retargeting loop actually fires.
# The plain-typo fixtures above never trip it (their targets don't exist, so
# renaming them is impossible).
TEMPLATE_SPEC_CONTENT = """\
# Template Rename Fixture

## REQ-p00090: Template Anchor

**Level**: PRD | **Status**: Active | **Template**

The template SHALL only be satisfiable, never refinable.

### Assertions

A. The template SHALL expose the templated capability.

*End* *Template Anchor* | **Hash**: 00000000

---

## REQ-p00091: Template Refiner

**Level**: PRD | **Status**: Active | **Refines**: REQ-p00090

Refining a template is rejected at build time: the reference stays an
unresolved (broken) leftover whose target nonetheless exists.

### Assertions

A. The refiner SHALL keep its authored citation.

*End* *Template Refiner* | **Hash**: 00000000

---
"""


@pytest.fixture()
def template_graph(tmp_path: Path):
    """Build a FederatedGraph whose only broken ref targets an EXISTING node."""
    (tmp_path / ".elspais.toml").write_text(CONFIG_CONTENT, encoding="utf-8")
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    (spec_dir / "templates.md").write_text(TEMPLATE_SPEC_CONTENT, encoding="utf-8")
    graph = build_graph(
        config_path=tmp_path / ".elspais.toml",
        repo_root=tmp_path,
        scan_code=False,
        scan_tests=False,
    )
    # Fixture premise: exactly one broken ref (refiner -> template), carrying
    # the template-rule diagnostic, and the leftover renders.
    brs = [br for br in graph.broken_references() if br.source_id == "REQ-p00091"]
    assert len(brs) == 1, f"fixture premise broken: {brs!r}"
    assert brs[0].target_id == "REQ-p00090"
    assert brs[0].diagnostic, "template rejection must carry a diagnostic"
    assert "REQ-p00090" in render_node(_node(graph, "REQ-p00091"))
    return graph


def _broken_refs_from(graph, source_id: str):
    return [br for br in graph.broken_references() if br.source_id == source_id]


class TestRenameRetargetsBrokenLeftovers:
    """Validates REQ-d00132-G: renaming a broken-ref target retargets the
    RENDERED leftover, not just the broken-references report.

    ``rename_node`` rewrites ``BrokenReference.target_id`` entries, but the
    text that actually renders (and saves) comes from the source node's
    stored leftover field -- the two must move together or the report and
    the file disagree about which ID the author cites.
    """

    def test_REQ_d00132_G_rename_target_updates_broken_reference_report(self, template_graph):
        """The broken-references report follows the rename (existing behavior)."""
        template_graph.rename_node("REQ-p00090", "REQ-p00092")

        brs = _broken_refs_from(template_graph, "REQ-p00091")
        assert len(brs) == 1
        assert brs[0].target_id == "REQ-p00092"

    def test_REQ_d00132_G_rename_target_updates_rendered_leftover(self, template_graph):
        """The rendered Refines: line must cite the renamed target."""
        template_graph.rename_node("REQ-p00090", "REQ-p00092")

        rendered = render_node(_node(template_graph, "REQ-p00091"))
        assert "REQ-p00092" in rendered, (
            "the broken-references report says REQ-p00092 but the render "
            "still cites the stale leftover -- saving would write the old ID"
        )
        assert "REQ-p00090" not in rendered, (
            "rename_node retargeted _broken_references but left the source "
            "node's stored leftover pointing at the old ID"
        )

    @pytest.mark.parametrize(
        ("rename_from", "rename_to", "expect_source", "expect_target"),
        [
            pytest.param("REQ-p00090", "REQ-p00092", "REQ-p00091", "REQ-p00092", id="target"),
            pytest.param("REQ-p00091", "REQ-p00092", "REQ-p00092", "REQ-p00090", id="source"),
        ],
    )
    def test_REQ_d00132_G_rename_preserves_broken_ref_diagnostic(
        self, template_graph, rename_from, rename_to, expect_source, expect_target
    ):
        """Renaming either endpoint must not strip the diagnostic.

        The retargeting loop rebuilds BrokenReference from scratch; the
        template-rule diagnostic (and presumed_foreign) must survive.
        """
        diagnostic_before = _broken_refs_from(template_graph, "REQ-p00091")[0].diagnostic

        template_graph.rename_node(rename_from, rename_to)

        brs = _broken_refs_from(template_graph, expect_source)
        assert len(brs) == 1
        assert brs[0].target_id == expect_target
        assert brs[0].diagnostic == diagnostic_before, (
            "rename_node rebuilt the BrokenReference without its diagnostic "
            "-- the author's actionable guidance was silently dropped"
        )


class TestUndoRenameRestoresBrokenRefs:
    """Validates REQ-d00132-G: undoing a rename restores broken-reference
    targets and the rendered leftover to their pre-rename spelling.

    ``_undo_rename_node`` restores node and child IDs but must also reverse
    the broken-ref retargeting (and the leftover sync), or undo leaves the
    report citing an ID that no longer exists.
    """

    def test_REQ_d00132_G_undo_rename_restores_broken_reference_target(self, template_graph):
        """After rename + undo, the report cites the original target again."""
        template_graph.rename_node("REQ-p00090", "REQ-p00092")
        template_graph.undo_last()

        brs = _broken_refs_from(template_graph, "REQ-p00091")
        assert len(brs) == 1
        assert brs[0].target_id == "REQ-p00090", (
            "undo restored the node ID REQ-p00090 but the broken-references "
            "report still cites the undone name REQ-p00092"
        )

    def test_REQ_d00132_G_undo_rename_restores_rendered_leftover(self, template_graph):
        """After rename + undo, the render cites the original target again."""
        template_graph.rename_node("REQ-p00090", "REQ-p00092")
        template_graph.undo_last()

        rendered = render_node(_node(template_graph, "REQ-p00091"))
        assert "REQ-p00090" in rendered
        assert "REQ-p00092" not in rendered


class TestDeleteRequirementBrokenRefs:
    """Validates REQ-d00132-G: deleting a requirement retires its broken
    references, and undoing the delete restores them.

    ``delete_requirement`` moves the node to _deleted_nodes but must not
    leave _broken_references entries sourced from a node that no longer
    exists -- health surfaces would report a phantom citation.
    """

    def test_REQ_d00132_G_delete_requirement_retires_and_undo_restores_broken_refs(
        self, fidelity_graph
    ):
        """REQ-o00003's only ref is broken: delete removes it, undo restores."""
        assert len(_broken_refs_from(fidelity_graph, "REQ-o00003")) == 1

        fidelity_graph.delete_requirement("REQ-o00003")
        assert _broken_refs_from(fidelity_graph, "REQ-o00003") == [], (
            "REQ-o00003 was deleted but its broken reference to REQ-p77777 "
            "still appears in the report (stale source)"
        )

        fidelity_graph.undo_last()
        brs = _broken_refs_from(fidelity_graph, "REQ-o00003")
        assert len(brs) == 1, "undoing the delete must restore the broken reference"
        assert brs[0].target_id == "REQ-p77777"


class TestRenameRetargetsAssertionSuffixedBrokenRefs:
    """Validates REQ-d00132-G: renaming a requirement retargets broken
    references whose target is one of its assertion-suffixed IDs.

    ``Implements: REQ-p00001-A+Z`` where Z does not exist leaves a broken
    ref / leftover "REQ-p00001-Z". Renaming REQ-p00001 must carry the
    suffixed spelling along in both the report and the render -- the
    exact-match retargeting loop must not skip it.
    """

    def test_REQ_d00132_G_rename_retargets_assertion_suffixed_broken_reference(
        self, fidelity_graph
    ):
        """The report's broken target follows the parent rename."""
        brs = _broken_refs_from(fidelity_graph, "REQ-o00007")
        assert [br.target_id for br in brs] == ["REQ-p00001-Z"], f"fixture premise: {brs!r}"

        fidelity_graph.rename_node("REQ-p00001", "REQ-p00009")

        brs = _broken_refs_from(fidelity_graph, "REQ-o00007")
        assert [br.target_id for br in brs] == ["REQ-p00009-Z"], (
            "REQ-p00001 was renamed to REQ-p00009 but the assertion-suffixed "
            "broken target kept the old parent spelling"
        )

    def test_REQ_d00132_G_rename_retargets_assertion_suffixed_rendered_leftover(
        self, fidelity_graph
    ):
        """The rendered leftover expansion follows the parent rename too."""
        fidelity_graph.rename_node("REQ-p00001", "REQ-p00009")

        rendered = render_node(_node(fidelity_graph, "REQ-o00007"))
        assert "REQ-p00009-A" in rendered, "the edge-derived expansion must follow the rename"
        assert (
            "REQ-p00009-Z" in rendered
        ), "the broken expansion's leftover still cites the old parent ID"
        assert "REQ-p00001-Z" not in rendered
