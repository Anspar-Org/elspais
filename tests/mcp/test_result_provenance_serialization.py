# Verifies: REQ-d00254-F
"""_serialize_test_info exposes per-result results-file provenance.

Each serialized RESULT carries ``result_file``/``result_line`` (the results
ARTIFACT, e.g. junit.xml and its <testcase> line) alongside the existing
``file``/``line`` (the TEST's source). When a RESULT was built without those
fields (e.g. a reporter with no results file), the serializer falls back to
the source-derived file/line so viewers still render a link.

Also covers ``_serialize_journey_info`` / ``_get_assertion_uat_map``: a
journey's results hang off its step-verifying TESTs
(``JNY/STEP --VERIFIES--> TEST --YIELDS--> RESULT``), not the JNY node
itself, so serializing journeys with ``_serialize_test_info`` used to yield
``results: []`` for every journey (the "UAT Passed panel always empty"
regression).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from elspais.graph import EdgeKind, GraphNode, NodeKind
from elspais.graph.builder import TraceGraph
from elspais.graph.GraphNode import FileType
from elspais.mcp.server import (
    _get_assertion_uat_map,
    _serialize_journey_info,
    _serialize_test_info,
)


@pytest.fixture()
def provenance_graph():
    """TEST with two RESULT children: one with provenance, one without."""
    graph = TraceGraph(repo_root=Path("/test/repo"))

    file_node = GraphNode(
        id="file:tests/test_login.py", kind=NodeKind.FILE, label="test_login.py"
    )
    file_node.set_field("file_type", FileType.TEST)
    file_node.set_field("relative_path", "tests/test_login.py")

    test_node = GraphNode(
        id="test:tests/test_login.py::test_login", kind=NodeKind.TEST, label="test_login"
    )
    test_node.set_field("parse_line", 42)
    test_node.set_field("name", "test_login")
    file_node.link(test_node, EdgeKind.CONTAINS)

    with_prov = GraphNode(id="r-with-prov", kind=NodeKind.RESULT, label="r-with-prov")
    with_prov.set_field("status", "passed")
    with_prov.set_field("parse_line", 3)
    with_prov.set_field("result_file", "results/junit.xml")
    with_prov.set_field("result_line", 7)
    test_node.link(with_prov, EdgeKind.YIELDS)

    without_prov = GraphNode(id="r-no-prov", kind=NodeKind.RESULT, label="r-no-prov")
    without_prov.set_field("status", "failed")
    without_prov.set_field("parse_line", 9)
    test_node.link(without_prov, EdgeKind.YIELDS)

    graph._index[file_node.id] = file_node
    graph._index[test_node.id] = test_node
    graph._index[with_prov.id] = with_prov
    graph._index[without_prov.id] = without_prov
    return graph


def _serialized_results(graph) -> dict[str, dict]:
    test_node = graph.find_by_id("test:tests/test_login.py::test_login")
    info = _serialize_test_info(test_node, graph)
    return {r["id"]: r for r in info["results"]}


# Verifies: REQ-d00254-F
def test_result_file_and_line_exposed_per_result(provenance_graph):
    """A RESULT with stored provenance surfaces it verbatim."""
    entry = _serialized_results(provenance_graph)["r-with-prov"]
    assert entry["result_file"] == "results/junit.xml"
    assert entry["result_line"] == 7
    # file/line keep pointing at the TEST's source, not the artifact.
    assert entry["file"] == "tests/test_login.py"
    assert entry["line"] == 3


# Verifies: REQ-d00254-F
def test_result_without_provenance_falls_back_to_source(provenance_graph):
    """A RESULT built without result_file/result_line falls back to file/line."""
    entry = _serialized_results(provenance_graph)["r-no-prov"]
    assert entry["result_file"] == entry["file"] == "tests/test_login.py"
    assert entry["result_line"] == entry["line"] == 9


# ---------------------------------------------------------------------------
# Journey serialization: results come from step-verifying TESTs
# ---------------------------------------------------------------------------

_UAT_FIXTURE = Path(__file__).parents[1] / "fixtures" / "journey-uat" / "one-step-fails"


@pytest.fixture(scope="module")
def uat_graph(tmp_path_factory):
    """Full build of the on-disk one-step-fails journey-UAT fixture (read-only).

    A 3-step journey Validates: REQ-d00001-A; each step has a verifying test
    (``# Verifies: JNY-OQ-Login-01/N``) and a JUnit results.xml target yields
    one RESULT per test (step 2's fails). The full build also runs
    ``annotate_journey_verification``, stamping the journey_verification
    metric the serializer exposes.
    """
    from elspais.graph.factory import build_graph

    dest = tmp_path_factory.mktemp("one-step-fails") / "proj"
    shutil.copytree(_UAT_FIXTURE, dest)
    fg = build_graph(repo_root=dest)
    return fg._repos[fg._root_repo].graph


class TestSerializeJourneyInfo:
    """_serialize_journey_info collects results across the step-VERIFIES chain."""

    # Verifies: REQ-d00255-D, REQ-d00256-E
    def test_journey_results_collected_from_step_verifying_tests(self, uat_graph):
        """Each step test's RESULT surfaces on the journey, with step labels.

        Regression: serializing the JNY node with _serialize_test_info looked
        only at the journey's direct children, so results was always [].
        """
        jny = uat_graph.find_by_id("JNY-OQ-Login-01")
        info = _serialize_journey_info(jny, uat_graph)

        assert len(info["results"]) == 3
        by_step = {entry["step"]: entry for entry in info["results"]}
        assert set(by_step) == {"1", "2", "3"}
        assert by_step["1"]["status"] == "passed"
        assert by_step["2"]["status"] == "failed"
        assert by_step["3"]["status"] == "passed"

    # Verifies: REQ-d00255-D, REQ-d00256-E
    def test_journey_results_carry_artifact_provenance(self, uat_graph):
        """Step results keep result_file/result_line from the junit artifact."""
        jny = uat_graph.find_by_id("JNY-OQ-Login-01")
        info = _serialize_journey_info(jny, uat_graph)

        for entry in info["results"]:
            assert entry["result_file"] == "results.xml"
            assert entry["result_line"] > 0

    # Verifies: REQ-d00256-E
    def test_journey_verification_rollup_exposed(self, uat_graph):
        """The journey_verification metric surfaces as verified/total/tier."""
        jny = uat_graph.find_by_id("JNY-OQ-Login-01")
        info = _serialize_journey_info(jny, uat_graph)

        assert info["verified_steps"] == 2
        assert info["total_steps"] == 3
        assert info["tier"] == "failing"

    # Verifies: REQ-d00255-D
    def test_journey_without_verifying_tests_has_empty_results(self):
        """A journey with steps but no VERIFIES edges serializes cleanly."""
        graph = TraceGraph(repo_root=Path("/test/repo"))

        file_node = GraphNode(
            id="file:spec/journeys.md", kind=NodeKind.FILE, label="journeys.md"
        )
        file_node.set_field("file_type", FileType.JOURNEY)
        file_node.set_field("relative_path", "spec/journeys.md")

        jny = GraphNode(
            id="JNY-Bare-01", kind=NodeKind.USER_JOURNEY, label="Bare Journey"
        )
        jny.set_field("parse_line", 5)
        file_node.link(jny, EdgeKind.CONTAINS)

        step = GraphNode(id="JNY-Bare-01/1", kind=NodeKind.STEP, label="only step")
        step.set_field("label", "1")
        jny.link(step, EdgeKind.STRUCTURES)

        graph._index[file_node.id] = file_node
        graph._index[jny.id] = jny
        graph._index[step.id] = step

        info = _serialize_journey_info(jny, graph)
        assert info["results"] == []
        assert info["id"] == "JNY-Bare-01"
        assert "verified_steps" not in info


class TestAssertionUatMap:
    """_get_assertion_uat_map surfaces journey results per assertion."""

    # Verifies: REQ-d00255-D, REQ-d00256-E
    def test_uat_map_journeys_have_nonempty_results(self, uat_graph):
        """The per-assertion journey entry carries the step results.

        Regression: _get_assertion_uat_map used _serialize_test_info, so
        every journey entry had results == [] and the viewer's per-assertion
        UAT Passed panel always said "No journey results".
        """
        out = _get_assertion_uat_map(uat_graph, "REQ-d00001")

        assert out["success"] is True
        journeys = out["assertion_journeys"]["A"]["journeys"]
        assert len(journeys) == 1
        entry = journeys[0]
        assert entry["id"] == "JNY-OQ-Login-01"

        statuses = sorted(r["status"] for r in entry["results"])
        assert statuses == ["failed", "passed", "passed"]

    # Verifies: REQ-d00256-E
    def test_uat_map_journey_carries_verification_rollup(self, uat_graph):
        """verified_steps/total_steps ride along when the annotator ran."""
        out = _get_assertion_uat_map(uat_graph, "REQ-d00001")
        entry = out["assertion_journeys"]["A"]["journeys"][0]
        assert entry["verified_steps"] == 2
        assert entry["total_steps"] == 3
