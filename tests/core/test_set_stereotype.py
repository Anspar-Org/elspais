# Verifies: REQ-p00014-E
"""Tests for the ``set_stereotype`` mutation (viewer Template toggle).

Covers:
- Graph-level round-trip: concrete -> template -> concrete, with assertion
  children stamped both ways, mirroring the author-declaration parse path.
- Undo restores the node AND its assertion children.
- Error cases: unknown id (KeyError), non-requirement node (ValueError),
  INSTANCE node (ValueError).
- MCP guard (``_mutate_set_stereotype``): un-templating a requirement with
  live INSTANCE clones is soft-blocked unless force=True; toggle-ON never
  blocks.
- Persistence round-trip: a toggled template renders the ``**Template**``
  metadata marker and is byte-identical to the same requirement authored
  with ``**Template**`` in the source.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from elspais.graph.federated import FederatedGraph
from elspais.graph.GraphNode import NodeKind
from elspais.graph.relations import Stereotype
from elspais.graph.render import render_node
from tests.core.graph_test_helpers import build_graph, make_journey, make_requirement

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_ASSERTIONS = [
    {"label": "A", "text": "obligation one"},
    {"label": "B", "text": "obligation two"},
]


def _concrete_graph():
    """Graph with one concrete requirement (two assertions)."""
    return build_graph(
        make_requirement("REQ-p00001", title="Concrete Req", assertions=list(_ASSERTIONS))
    )


def _template_with_instance_graph():
    """Graph where REQ-p00044 Satisfies template REQ-p80001 (one INSTANCE)."""
    template = make_requirement(
        "REQ-p80001",
        title="Electronic Signature Standard",
        template=True,
        assertions=list(_ASSERTIONS),
    )
    declaring = make_requirement(
        "REQ-p00044",
        title="Document Management",
        satisfies=["REQ-p80001"],
    )
    return build_graph(template, declaring)


def _assertion_children(node):
    return [c for c in node.iter_children() if c.kind == NodeKind.ASSERTION]


def _stereotype(node):
    return node.get_field("stereotype") or Stereotype.CONCRETE


# ─────────────────────────────────────────────────────────────────────────────
# A. Mutation round-trip (graph level)
# ─────────────────────────────────────────────────────────────────────────────


class TestSetStereotypeRoundTrip:
    """TraceGraph.set_stereotype stamps node + assertion children both ways."""

    # Verifies: REQ-p00014-E
    def test_toggle_on_stamps_requirement_and_assertions(self):
        graph = _concrete_graph()
        node = graph.find_by_id("REQ-p00001")
        assert _stereotype(node) == Stereotype.CONCRETE

        entry = graph.set_stereotype("REQ-p00001", True)

        assert entry.operation == "set_stereotype"
        assert entry.target_id == "REQ-p00001"
        assert entry.after_state["stereotype"] == Stereotype.TEMPLATE.value
        assert node.get_field("stereotype") == Stereotype.TEMPLATE
        children = _assertion_children(node)
        assert len(children) == 2
        for child in children:
            assert child.get_field("stereotype") == Stereotype.TEMPLATE

    # Verifies: REQ-p00014-E
    def test_toggle_off_restores_concrete_on_node_and_assertions(self):
        graph = _concrete_graph()
        graph.set_stereotype("REQ-p00001", True)

        entry = graph.set_stereotype("REQ-p00001", False)

        assert entry.before_state["stereotype"] == Stereotype.TEMPLATE.value
        node = graph.find_by_id("REQ-p00001")
        assert node.get_field("stereotype") == Stereotype.CONCRETE
        for child in _assertion_children(node):
            assert child.get_field("stereotype") == Stereotype.CONCRETE

    # Verifies: REQ-p00014-E
    def test_before_state_records_per_assertion_stereotypes(self):
        graph = _concrete_graph()

        entry = graph.set_stereotype("REQ-p00001", True)

        recorded = entry.before_state["assertion_stereotypes"]
        assert set(recorded) == {"REQ-p00001-A", "REQ-p00001-B"}
        assert all(v == Stereotype.CONCRETE.value for v in recorded.values())

    # Verifies: REQ-p00014-E
    def test_undo_restores_node_and_assertion_children(self):
        graph = _concrete_graph()
        graph.set_stereotype("REQ-p00001", True)

        undone = graph.undo_last()

        assert undone is not None and undone.operation == "set_stereotype"
        node = graph.find_by_id("REQ-p00001")
        assert _stereotype(node) == Stereotype.CONCRETE
        for child in _assertion_children(node):
            assert _stereotype(child) == Stereotype.CONCRETE

    # Verifies: REQ-p00014-E
    def test_undo_restores_authored_template_after_toggle_off(self):
        """Undoing a toggle-OFF on an author-declared template restores TEMPLATE."""
        graph = build_graph(
            make_requirement(
                "REQ-p80001",
                title="Authored Template",
                template=True,
                assertions=list(_ASSERTIONS),
            )
        )
        node = graph.find_by_id("REQ-p80001")
        assert node.get_field("stereotype") == Stereotype.TEMPLATE

        graph.set_stereotype("REQ-p80001", False)
        assert node.get_field("stereotype") == Stereotype.CONCRETE

        graph.undo_last()

        assert node.get_field("stereotype") == Stereotype.TEMPLATE
        children = _assertion_children(node)
        assert len(children) == 2
        for child in children:
            assert child.get_field("stereotype") == Stereotype.TEMPLATE

    # Verifies: REQ-p00014-E
    def test_federated_wrapper_delegates(self):
        """FederatedGraph.set_stereotype routes to the owning repo graph."""
        graph = _concrete_graph()
        fed = FederatedGraph.from_single(
            graph, {"project": {"name": "test", "namespace": "REQ"}}, Path("/test/repo")
        )

        entry = fed.set_stereotype("REQ-p00001", True)

        assert entry.operation == "set_stereotype"
        node = graph.find_by_id("REQ-p00001")
        assert node.get_field("stereotype") == Stereotype.TEMPLATE


class TestSetStereotypeErrors:
    """Error cases raise before any mutation is applied."""

    # Verifies: REQ-p00014-E
    def test_unknown_id_raises_keyerror(self):
        graph = _concrete_graph()
        with pytest.raises(KeyError, match="REQ-nonexistent"):
            graph.set_stereotype("REQ-nonexistent", True)

    # Verifies: REQ-p00014-E
    def test_assertion_node_raises_valueerror(self):
        graph = _concrete_graph()
        with pytest.raises(ValueError, match="not a requirement"):
            graph.set_stereotype("REQ-p00001-A", True)

    # Verifies: REQ-p00014-E
    def test_journey_node_raises_valueerror(self):
        graph = build_graph(
            make_requirement("REQ-p00001", assertions=list(_ASSERTIONS)),
            make_journey("UJ-001", title="Login Flow", validates=["REQ-p00001"]),
        )
        with pytest.raises(ValueError, match="not a requirement"):
            graph.set_stereotype("UJ-001", True)

    # Verifies: REQ-p00014-E
    @pytest.mark.parametrize("is_template", [True, False])
    def test_instance_node_raises_valueerror(self, is_template):
        graph = _template_with_instance_graph()
        clone = graph.find_by_id("REQ-p00044::REQ-p80001")
        assert clone is not None
        assert clone.get_field("stereotype") == Stereotype.INSTANCE
        with pytest.raises(ValueError, match="instance"):
            graph.set_stereotype("REQ-p00044::REQ-p80001", is_template)

    # Verifies: REQ-p00014-E
    def test_error_paths_leave_no_mutation_log_entry(self):
        graph = _concrete_graph()
        with pytest.raises(KeyError):
            graph.set_stereotype("REQ-nope", True)
        with pytest.raises(ValueError):
            graph.set_stereotype("REQ-p00001-A", True)
        assert graph.mutation_log.last() is None


# ─────────────────────────────────────────────────────────────────────────────
# B. MCP guard (_mutate_set_stereotype)
# ─────────────────────────────────────────────────────────────────────────────


class TestMutateSetStereotypeGuard:
    """Un-templating with live instances is soft-blocked unless forced."""

    # Verifies: REQ-p00014-E
    def test_toggle_off_with_instances_is_blocked(self):
        from elspais.mcp.server import _mutate_set_stereotype

        graph = _template_with_instance_graph()
        result = _mutate_set_stereotype(graph, "REQ-p80001", False)

        assert result["success"] is False
        assert result["blocked"] is True
        assert result["instance_count"] == 1
        assert "force" in result["error"]
        # Guard blocks BEFORE mutating: template stereotype unchanged.
        node = graph.find_by_id("REQ-p80001")
        assert node.get_field("stereotype") == Stereotype.TEMPLATE

    # Verifies: REQ-p00014-E
    def test_toggle_off_with_force_succeeds(self):
        from elspais.mcp.server import _mutate_set_stereotype

        graph = _template_with_instance_graph()
        result = _mutate_set_stereotype(graph, "REQ-p80001", False, force=True)

        assert result["success"] is True
        assert result["mutation"]["operation"] == "set_stereotype"
        node = graph.find_by_id("REQ-p80001")
        assert node.get_field("stereotype") == Stereotype.CONCRETE

    # Verifies: REQ-p00014-E
    def test_toggle_on_never_blocks(self):
        from elspais.mcp.server import _mutate_set_stereotype

        graph = _template_with_instance_graph()
        # Even on a template that has instances, toggle-ON is not guarded.
        result = _mutate_set_stereotype(graph, "REQ-p80001", True)

        assert result.get("blocked") is None
        assert result["success"] is True

    # Verifies: REQ-p00014-E
    def test_instance_count_reflects_multiple_declaring_requirements(self):
        from elspais.mcp.server import _mutate_set_stereotype

        template = make_requirement(
            "REQ-p80001",
            title="Shared Template",
            template=True,
            assertions=list(_ASSERTIONS),
        )
        declaring_1 = make_requirement("REQ-p00044", satisfies=["REQ-p80001"])
        declaring_2 = make_requirement("REQ-p00045", satisfies=["REQ-p80001"])
        graph = build_graph(template, declaring_1, declaring_2)

        result = _mutate_set_stereotype(graph, "REQ-p80001", False)

        assert result["blocked"] is True
        assert result["instance_count"] == 2

    # Verifies: REQ-p00014-E
    def test_toggle_off_without_instances_succeeds(self):
        from elspais.mcp.server import _mutate_set_stereotype

        graph = build_graph(
            make_requirement(
                "REQ-p80001", title="Lonely Template", template=True, assertions=list(_ASSERTIONS)
            )
        )
        result = _mutate_set_stereotype(graph, "REQ-p80001", False)

        assert result["success"] is True
        assert result.get("blocked") is None

    # Verifies: REQ-p00014-E
    def test_instance_count_includes_cross_repo_instances(self):
        """A consumer repo's clone of an associate's template guards toggle-OFF.

        Uses the on-disk e2e-xrepo-template fixture in-process (no CLI):
        app Satisfies LIB-p00001, which lives in the ``library`` associate,
        so the INSTANCE parent counted by the guard is cross-repo.
        """
        from elspais.graph.factory import build_graph as factory_build_graph
        from elspais.mcp.server import _mutate_set_stereotype

        app_root = (
            Path(__file__).resolve().parents[1] / "fixtures" / "e2e-xrepo-template" / "app"
        )
        fed = factory_build_graph(repo_root=app_root)
        template = fed.find_by_id("LIB-p00001")
        assert template is not None
        assert template.get_field("stereotype") == Stereotype.TEMPLATE

        result = _mutate_set_stereotype(fed, "LIB-p00001", False)

        assert result["blocked"] is True
        assert result["instance_count"] == 1

    # Verifies: REQ-p00014-E
    def test_unknown_node_returns_error_dict(self):
        from elspais.mcp.server import _mutate_set_stereotype

        graph = _concrete_graph()
        result = _mutate_set_stereotype(graph, "REQ-nope", True)

        assert result["success"] is False
        assert "not found" in result["error"]


# ─────────────────────────────────────────────────────────────────────────────
# C. Persistence round-trip (render)
# ─────────────────────────────────────────────────────────────────────────────


class TestSetStereotypeRenderRoundTrip:
    """Toggled templates render identically to author-declared templates."""

    # Verifies: REQ-p00014-E
    def test_render_emits_template_marker_after_toggle_on(self):
        graph = _concrete_graph()
        node = graph.find_by_id("REQ-p00001")
        assert "**Template**" not in render_node(node)

        graph.set_stereotype("REQ-p00001", True)

        rendered = render_node(node)
        meta_line = next(line for line in rendered.split("\n") if line.startswith("**Level**:"))
        assert "**Template**" in meta_line

    # Verifies: REQ-p00014-E
    def test_render_omits_template_marker_after_toggle_off(self):
        graph = _concrete_graph()
        graph.set_stereotype("REQ-p00001", True)
        graph.set_stereotype("REQ-p00001", False)

        node = graph.find_by_id("REQ-p00001")
        assert "**Template**" not in render_node(node)

    # Verifies: REQ-p00014-E
    def test_toggled_template_renders_identically_to_authored_template(self):
        """The mutation path must be indistinguishable from the parse path."""
        authored_graph = build_graph(
            make_requirement(
                "REQ-p80001",
                title="Signature Standard",
                template=True,
                assertions=list(_ASSERTIONS),
            )
        )
        toggled_graph = build_graph(
            make_requirement(
                "REQ-p80001",
                title="Signature Standard",
                template=False,
                assertions=list(_ASSERTIONS),
            )
        )
        toggled_graph.set_stereotype("REQ-p80001", True)

        authored_text = render_node(authored_graph.find_by_id("REQ-p80001"))
        toggled_text = render_node(toggled_graph.find_by_id("REQ-p80001"))
        assert toggled_text == authored_text

    # Verifies: REQ-p00014-E
    def test_untoggled_template_renders_identically_to_authored_concrete(self):
        """Toggle on+off must round-trip back to the plain concrete render."""
        concrete_graph = _concrete_graph()
        toggled_graph = _concrete_graph()
        toggled_graph.set_stereotype("REQ-p00001", True)
        toggled_graph.set_stereotype("REQ-p00001", False)

        concrete_text = render_node(concrete_graph.find_by_id("REQ-p00001"))
        toggled_text = render_node(toggled_graph.find_by_id("REQ-p00001"))
        assert toggled_text == concrete_text
