"""A node is marked parse-dirty only for a reason the one vocabulary names."""

from __future__ import annotations

import pytest

from elspais.graph import NodeKind
from elspais.graph.GraphNode import GraphNode


# Verifies: REQ-d00248-B
def test_a_reason_outside_the_vocabulary_is_refused():
    node = GraphNode(id="REQ-d00001", kind=NodeKind.REQUIREMENT, label="Alpha")

    with pytest.raises(ValueError, match="no_such_reason"):
        node.mark_parse_dirty("no_such_reason")

    assert not node.get_field("parse_dirty")
    assert not node.get_field("parse_dirty_reasons")
