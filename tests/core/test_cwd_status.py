# Verifies: REQ-d00254-A
"""Per-target-cwd green/red signal and target cwd matching."""

from elspais.graph.annotators import _compute_cwd_status, _match_cwd
from tests.core.graph_test_helpers import build_graph, make_test_result

CWDS = ("provenance", "reaction")


def test_match_cwd_segment():
    assert _match_cwd("build-reports/provenance/TEST-provenance.xml", CWDS) == "provenance"
    assert _match_cwd("provenance/test/foo_test.dart", CWDS) == "provenance"
    assert _match_cwd("provenance/lib/foo.dart", CWDS) == "provenance"
    assert _match_cwd("unrelated/x.dart", CWDS) is None
    assert _match_cwd(None, CWDS) is None


def test_match_cwd_deepest_segment_wins():
    # both "build-reports" and "provenance" present; the deeper cwd wins
    cwds = ("build-reports", "provenance")
    assert _match_cwd("build-reports/provenance/TEST.xml", cwds) == "provenance"


def test_cwd_status_green_when_all_pass():
    g = build_graph(
        make_test_result("r1", status="passed", source_path="build-reports/provenance/TEST.xml"),
        make_test_result("r2", status="passed", source_path="build-reports/provenance/TEST.xml"),
    )
    assert _compute_cwd_status(g, CWDS) == {"provenance": "green"}


def test_cwd_status_red_on_any_failure_isolated_per_cwd():
    g = build_graph(
        make_test_result("r1", status="passed", source_path="build-reports/provenance/TEST.xml"),
        make_test_result("r2", status="failed", source_path="build-reports/provenance/TEST.xml"),
        make_test_result("r3", status="passed", source_path="build-reports/reaction/TEST.xml"),
    )
    status = _compute_cwd_status(g, CWDS)
    assert status == {"provenance": "red", "reaction": "green"}


# Verifies: REQ-d00327-C
def test_cwd_status_reads_the_path_read_from_its_origin():
    """A path recorded relative to the target's cwd lacks the cwd's
    segment; the path read from its origin carries it."""
    g = build_graph(
        make_test_result(
            "r1",
            status="failed",
            source_path="test/foo_test.dart",
            source_file="provenance/test/foo_test.dart",
        ),
    )
    assert _compute_cwd_status(g, CWDS) == {"provenance": "red"}
