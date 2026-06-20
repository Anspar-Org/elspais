# Verifies: REQ-d00254-A
"""Per-app green/red signal and app-dir matching (CUR-1533)."""

from elspais.graph.annotators import _compute_app_status, _match_app_dir
from tests.core.graph_test_helpers import build_graph, make_test_result

APPS = ("provenance", "reaction")


def test_match_app_dir_segment():
    assert _match_app_dir("build-reports/provenance/TEST-provenance.xml", APPS) == "provenance"
    assert _match_app_dir("provenance/test/foo_test.dart", APPS) == "provenance"
    assert _match_app_dir("provenance/lib/foo.dart", APPS) == "provenance"
    assert _match_app_dir("unrelated/x.dart", APPS) is None
    assert _match_app_dir(None, APPS) is None


def test_match_app_dir_deepest_segment_wins():
    # both "build-reports" and "provenance" present; the deeper (app) wins
    apps = ("build-reports", "provenance")
    assert _match_app_dir("build-reports/provenance/TEST.xml", apps) == "provenance"


def test_app_status_green_when_all_pass():
    g = build_graph(
        make_test_result("r1", status="passed", source_path="build-reports/provenance/TEST.xml"),
        make_test_result("r2", status="passed", source_path="build-reports/provenance/TEST.xml"),
    )
    assert _compute_app_status(g, APPS) == {"provenance": "green"}


def test_app_status_red_on_any_failure_isolated_per_app():
    g = build_graph(
        make_test_result("r1", status="passed", source_path="build-reports/provenance/TEST.xml"),
        make_test_result("r2", status="failed", source_path="build-reports/provenance/TEST.xml"),
        make_test_result("r3", status="passed", source_path="build-reports/reaction/TEST.xml"),
    )
    status = _compute_app_status(g, APPS)
    assert status == {"provenance": "red", "reaction": "green"}
