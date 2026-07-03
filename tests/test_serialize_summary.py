# Verifies: REQ-d00064-A, REQ-d00064-C
"""Public node-summary serializers in ``graph.serialize``.

``serialize_requirement_summary`` and ``serialize_assertion`` are the
canonical helpers for the ``{id, title, level, status}`` /
``{id, label, text}`` shapes used by MCP, CLI, server, and HTML
surfaces. Both accept an ``extras=`` keyword for caller-specific fields.
Missing fields fall back to ``""`` so consumers don't have to dance
around nullability.
"""

from __future__ import annotations

import pytest

from elspais.graph import NodeKind
from elspais.graph.serialize import serialize_assertion, serialize_requirement_summary


def _first(graph, kind, *, required=True):
    for node in graph.iter_by_kind(kind):
        return node
    if required:
        pytest.fail(f"canonical_graph has no {kind.name} nodes")
    return None


# -----------------------------------------------------------------------------
# serialize_requirement_summary
# -----------------------------------------------------------------------------


class TestSerializeRequirementSummary:
    def test_base_keys_for_requirement(self, canonical_graph):
        node = _first(canonical_graph, NodeKind.REQUIREMENT)
        result = serialize_requirement_summary(node)

        assert set(result.keys()) == {"id", "title", "level", "status"}
        assert result["id"] == node.id
        assert result["title"] == (node.get_label() or "")
        assert result["level"] == (node.get_field("level") or "")
        assert result["status"] == (node.get_field("status") or "")

    @pytest.mark.parametrize(
        "extras,expected_extra_keys",
        [
            (None, set()),
            ({}, set()),
            ({"score": 0.5, "hash": "abc"}, {"score", "hash"}),
        ],
        ids=["none", "empty", "score+hash"],
    )
    def test_extras_extend_dict(self, canonical_graph, extras, expected_extra_keys):
        node = _first(canonical_graph, NodeKind.REQUIREMENT)
        result = serialize_requirement_summary(node, extras=extras)

        assert {"id", "title", "level", "status"}.issubset(result.keys())
        for k in expected_extra_keys:
            assert result[k] == extras[k]
        # Base keys still match the node
        assert result["id"] == node.id

    def test_extras_override_base_keys(self, canonical_graph):
        node = _first(canonical_graph, NodeKind.REQUIREMENT)
        result = serialize_requirement_summary(node, extras={"id": "OVERRIDE"})

        assert result["id"] == "OVERRIDE"
        # Other base keys still present from the node
        assert result["title"] == (node.get_label() or "")
        assert result["level"] == (node.get_field("level") or "")

    def test_extras_none_equivalent_to_omitted(self, canonical_graph):
        node = _first(canonical_graph, NodeKind.REQUIREMENT)
        assert serialize_requirement_summary(node) == serialize_requirement_summary(
            node, extras=None
        )

    def test_journey_has_no_level(self, canonical_graph):
        node = _first(canonical_graph, NodeKind.USER_JOURNEY, required=False)
        if node is None:
            pytest.skip("canonical_graph has no USER_JOURNEY nodes")
        result = serialize_requirement_summary(node)

        assert set(result.keys()) == {"id", "title", "level", "status"}
        assert result["id"] == node.id
        # Journeys don't set 'level' content; missing fields fall back to ""
        assert result["level"] == ""


# -----------------------------------------------------------------------------
# serialize_assertion
# -----------------------------------------------------------------------------


class TestSerializeAssertion:
    def test_base_keys_for_assertion(self, canonical_graph):
        node = _first(canonical_graph, NodeKind.ASSERTION)
        result = serialize_assertion(node)

        assert set(result.keys()) == {"id", "label", "text"}
        assert result["id"] == node.id
        assert result["label"] == (node.get_field("label") or "")
        assert result["text"] == (node.get_label() or "")

    @pytest.mark.parametrize(
        "extras,expected_extra_keys",
        [
            (None, set()),
            ({}, set()),
            ({"score": 0.9, "hash": "deadbeef"}, {"score", "hash"}),
        ],
        ids=["none", "empty", "score+hash"],
    )
    def test_extras_extend_dict(self, canonical_graph, extras, expected_extra_keys):
        node = _first(canonical_graph, NodeKind.ASSERTION)
        result = serialize_assertion(node, extras=extras)

        assert {"id", "label", "text"}.issubset(result.keys())
        for k in expected_extra_keys:
            assert result[k] == extras[k]

    def test_extras_override_base_keys(self, canonical_graph):
        node = _first(canonical_graph, NodeKind.ASSERTION)
        result = serialize_assertion(node, extras={"id": "OVERRIDE", "label": "Z"})

        assert result["id"] == "OVERRIDE"
        assert result["label"] == "Z"
        # Non-overridden base key still present
        assert result["text"] == (node.get_label() or "")

    def test_extras_none_equivalent_to_omitted(self, canonical_graph):
        node = _first(canonical_graph, NodeKind.ASSERTION)
        assert serialize_assertion(node) == serialize_assertion(node, extras=None)

    def test_non_assertion_node_still_returns_dict(self, canonical_graph):
        # The implementation reads via get_field/get_label and does not
        # type-check. Passing a REQUIREMENT should produce the same shape
        # (label="" since REQs don't set the 'label' field).
        node = _first(canonical_graph, NodeKind.REQUIREMENT)
        result = serialize_assertion(node)

        assert set(result.keys()) == {"id", "label", "text"}
        assert result["id"] == node.id
        assert result["text"] == (node.get_label() or "")
