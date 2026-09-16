# Verifies: REQ-d00294-E, REQ-d00294-F
"""What the surfaces say about results that are held apart.

One test that runs in several environments now has one result in each of
them. A reader who cannot tell those results apart, or who is given a count
of tests where the tool counted results, reads the run wrongly. These tests
hold the surfaces to what REQ-d00294-F asks of them, and hold the results
tally to counting every failing result.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from elspais.commands.health import check_test_results
from elspais.graph.builder import TraceGraph
from elspais.graph.federated import FederatedGraph
from elspais.graph.GraphNode import GraphNode, NodeKind
from elspais.mcp.server import (
    _serialize_node_generic,
    _serialize_node_summary,
    _serialize_result_entry,
)


def _result(
    node_id: str,
    status: str = "passed",
    environment: str | None = None,
    result_file: str | None = "reports/junit.xml",
    result_line: int | None = 12,
) -> GraphNode:
    """One RESULT node, holding only the fields these surfaces read."""
    node = GraphNode(id=node_id, kind=NodeKind.RESULT, label="Checkout::test_pays")
    node.set_field("status", status)
    node.set_field("duration", 0.5)
    node.set_field("environment", environment)
    node.set_field("result_file", result_file)
    node.set_field("result_line", result_line)
    return node


def _graph(*nodes: GraphNode) -> FederatedGraph:
    tg = TraceGraph()
    for node in nodes:
        tg._index[node.id] = node
    return FederatedGraph.from_single(
        tg, config={"project": {"name": "test", "namespace": "REQ"}}, repo_root=Path(".")
    )


# Verifies: REQ-d00294-F
def test_a_results_list_publishes_the_environment():
    """The environment a result carries is a key of its own beside it."""
    node = _result("result:REQ:reports/junit.xml:1", environment="pixel-8")
    graph = _graph(node)

    entry = _serialize_result_entry(node, graph)

    assert entry["environment"] == "pixel-8"


# Verifies: REQ-d00294-F
@pytest.mark.parametrize("environment", [None, ""])
def test_a_result_with_no_environment_reads_as_it_did(environment):
    """A project that declares no source gets the envelope it got before.

    The key is absent, not empty: an empty label would tell a reader that
    the environment was read and found blank.
    """
    node = _result("result:REQ:reports/junit.xml:1", environment=environment)
    graph = _graph(node)

    entry = _serialize_result_entry(node, graph)

    assert "environment" not in entry


# Verifies: REQ-d00294-F
def test_one_fetched_result_says_where_it_was_recorded():
    """A fetched result names its place of record and its environment."""
    node = _result("result:REQ:reports/junit.xml:2", environment="firefox", result_line=31)
    graph = _graph(node)

    properties = _serialize_node_generic(node, graph)["properties"]

    assert properties["result_file"] == "reports/junit.xml"
    assert properties["result_line"] == 31
    assert properties["environment"] == "firefox"


# Verifies: REQ-d00294-F
def test_a_fetched_result_without_a_place_omits_the_keys():
    """Keys a result does not carry are left out rather than sent empty."""
    node = _result("result:REQ:widgets:1", environment=None, result_file=None, result_line=None)
    graph = _graph(node)

    properties = _serialize_node_generic(node, graph)["properties"]

    assert "result_file" not in properties
    assert "result_line" not in properties
    assert "environment" not in properties


# Verifies: REQ-d00294-F
def test_a_listed_result_carries_its_environment():
    """A list of results names the environment, which the titles do not."""
    first = _result("result:REQ:reports/junit.xml:1", environment="chromium")
    second = _result("result:REQ:reports/junit.xml:2", environment="firefox")

    summaries = [_serialize_node_summary(first), _serialize_node_summary(second)]

    assert [s["environment"] for s in summaries] == ["chromium", "firefox"]
    assert summaries[0]["title"] == summaries[1]["title"]


# Verifies: REQ-d00294-F
def test_a_listed_result_without_an_environment_omits_the_key():
    """A result carrying no environment is listed as it was listed before."""
    summary = _serialize_node_summary(_result("result:REQ:reports/junit.xml:1"))

    assert "environment" not in summary


# Verifies: REQ-d00294-E
def test_an_errored_result_is_counted_as_a_failure():
    """A result that errored is a failure, and it is reported as one.

    Counted nowhere, an errored record leaves the totals short and says
    nothing, which reads as a clean run.
    """
    graph = _graph(
        _result("result:REQ:reports/junit.xml:1", status="passed"),
        _result("result:REQ:reports/junit.xml:2", status="error"),
    )

    chk = check_test_results(graph, config=None)

    assert chk.passed is False
    assert chk.details["failed"] == 1
    assert chk.details["passed"] == 1
    assert [f.node_id for f in chk.findings] == ["result:REQ:reports/junit.xml:2"]


# Verifies: REQ-d00294-E
def test_the_tally_counts_results_and_says_so():
    """The count is a count of results, and the message names them.

    Two results of one test are two results. A message reading "tests"
    over that count would report two tests where the project has one.
    """
    graph = _graph(
        _result("result:REQ:reports/junit.xml:1", status="passed", environment="chromium"),
        _result("result:REQ:reports/junit.xml:2", status="failed", environment="firefox"),
    )

    chk = check_test_results(graph, config=None)

    assert "2 results" in chk.message
    assert "tests" not in chk.message


# Verifies: REQ-d00294-E
def test_every_result_passing_reads_as_results_passing():
    """The passing message names results too, for the same reason."""
    graph = _graph(
        _result("result:REQ:reports/junit.xml:1", status="passed", environment="chromium"),
        _result("result:REQ:reports/junit.xml:2", status="passed", environment="firefox"),
    )

    chk = check_test_results(graph, config=None)

    assert chk.passed is True
    assert chk.message.startswith("All results passing")
    assert "tests" not in chk.message


# Verifies: REQ-d00294-F
def test_a_failing_finding_names_the_environment_and_the_record():
    """A failing finding points at the record that failed and names where.

    Several failures of one test read alike without the environment, and
    the test's own source does not say which of the records failed.
    """
    graph = _graph(
        _result("result:REQ:reports/junit.xml:1", status="passed", environment="chromium"),
        _result(
            "result:REQ:reports/junit.xml:2",
            status="failed",
            environment="firefox",
            result_line=31,
        ),
    )

    finding = check_test_results(graph, config=None).findings[0]

    assert "[firefox]" in finding.message
    assert finding.file_path == "reports/junit.xml"
    assert finding.line == 31
