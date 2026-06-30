from elspais.graph.GraphNode import GraphNode, NodeKind, make_step_id
from elspais.graph.metrics import direct_coverage_for
from elspais.graph.relations import EdgeKind


# Verifies: REQ-d00256
def test_make_step_id_form():
    assert make_step_id("JNY-OQ-Login-01", 3) == "JNY-OQ-Login-01/step-3"


# Verifies: REQ-d00256
def test_direct_coverage_for_step_counts_outgoing_verifies():
    # A STEP is a coverage target like a requirement: it owns its verifying
    # tests as OUTGOING edges (step -> test).
    step = GraphNode(id="JNY-OQ-Login-01/step-1", kind=NodeKind.STEP, label="open page")
    test_node = GraphNode(id="test:t.py:1", kind=NodeKind.TEST, label="t")
    step.link(test_node, EdgeKind.VERIFIES)  # edge step -> test (outgoing from step)
    assert direct_coverage_for(step) == 1


# Verifies: REQ-d00256-A
def test_steps_become_structures_children(canonical_graph):
    """Journey ## Steps numbered list creates STEP children via STRUCTURES edges.

    JNY-001 (Login Flow) in the hht-like fixture has a ## Steps section with
    three numbered steps. After build, these should appear as STEP nodes linked
    from the journey via STRUCTURES edges.
    """
    jny = canonical_graph.find_by_id("JNY-001")
    assert jny is not None, "JNY-001 not found in canonical graph"

    steps = [
        c for c in jny.iter_children(edge_kinds={EdgeKind.STRUCTURES}) if c.kind == NodeKind.STEP
    ]

    assert [s.id for s in steps] == [
        "JNY-001/step-1",
        "JNY-001/step-2",
        "JNY-001/step-3",
    ]
    assert steps[1].get_label().startswith("System verifies")
