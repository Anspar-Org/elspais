# Implements: REQ-d00131-B, REQ-d00255, REQ-d00256
"""Tests for journey-id recognition inside Verifies: reference lines.

These tests confirm that JOURNEY_REF_PATTERN matches JNY-... targets
(whole journeys and addressable steps), and that _extract_ids collects
them without breaking existing REQ-id extraction.

Wiring tests (journey_with_*_graph fixtures) confirm that the generic
resolution path in builder.py wires TEST -> STEP and TEST -> JOURNEY
VERIFIES edges correctly, and that unknown step refs become
BrokenReferences.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from elspais.graph.parsers.lark.transformers.reference import ReferenceTransformer
from elspais.graph.parsers.patterns import JOURNEY_REF_PATTERN
from elspais.utilities.patterns import IdPatternConfig, IdResolver

# ---------------------------------------------------------------------------
# Fixture directory for on-disk build tests
# ---------------------------------------------------------------------------

_JOURNEY_VERIFY_FIX = Path(__file__).parents[1] / "fixtures" / "journey-verify"


def _build_trace_graph(tmp_path: Path, test_file_content: str):
    """Copy the journey-verify fixture to tmp_path, add a test file, build graph.

    Returns the primary TraceGraph (not the FederatedGraph).
    """
    from elspais.graph.factory import build_graph

    dest = tmp_path / "proj"
    shutil.copytree(_JOURNEY_VERIFY_FIX, dest)
    (dest / "tests").mkdir(parents=True, exist_ok=True)
    (dest / "tests" / "test_verify.py").write_text(test_file_content)
    fg = build_graph(repo_root=dest)
    return fg._repos[fg._root_repo].graph


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Fixtures: wiring tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def journey_with_step_test_graph(tmp_path):
    """Graph with one test that ``Verifies: JNY-OQ-Login-01/step-2``.

    Uses a file-level comment so the reference is picked up by the grammar
    (Python docstrings are not recognized as comment-style references).
    """
    return _build_trace_graph(
        tmp_path,
        "# Verifies: JNY-OQ-Login-01/step-2\ndef test_step():\n    pass\n",
    )


@pytest.fixture()
def journey_with_whole_test_graph(tmp_path):
    """Graph with one test that ``Verifies: JNY-OQ-Login-01`` (whole journey)."""
    return _build_trace_graph(
        tmp_path,
        "# Verifies: JNY-OQ-Login-01\ndef test_journey():\n    pass\n",
    )


@pytest.fixture()
def journey_with_bad_step_graph(tmp_path):
    """Graph with a test that ``Verifies: JNY-OQ-Login-01/step-9`` (non-existent)."""
    return _build_trace_graph(
        tmp_path,
        "# Verifies: JNY-OQ-Login-01/step-9\ndef test_bad():\n    pass\n",
    )


@pytest.fixture()
def capture_broken_refs():
    """Return a function that extracts broken references from a graph."""

    def _capture(graph):
        return graph.broken_references()

    return _capture


# ---------------------------------------------------------------------------
# Helpers: pattern fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def resolver():
    """Minimal IdResolver using standard REQ namespace."""
    config = IdPatternConfig.from_dict(
        {
            "project": {"namespace": "REQ"},
            "id-patterns": {
                "canonical": "{namespace}-{type.letter}{component}",
                "aliases": {"short": "{type.letter}{component}"},
                "types": {
                    "prd": {"level": 1, "aliases": {"letter": "p"}},
                    "ops": {"level": 2, "aliases": {"letter": "o"}},
                    "dev": {"level": 3, "aliases": {"letter": "d"}},
                },
                "component": {"style": "numeric", "digits": 5, "leading_zeros": True},
                "assertions": {"label_style": "uppercase", "max_count": 26},
            },
        }
    )
    return IdResolver(config)


@pytest.fixture()
def extractor(resolver):
    """ReferenceTransformer instance for calling _extract_ids."""
    return ReferenceTransformer(resolver, "test_ref")


# ---------------------------------------------------------------------------
# Pattern unit tests
# ---------------------------------------------------------------------------


# Verifies: REQ-d00255
def test_journey_ref_pattern_matches_whole_journey():
    assert JOURNEY_REF_PATTERN.fullmatch("JNY-OQ-Login-01")


# Verifies: REQ-d00256
def test_journey_ref_pattern_matches_step():
    assert JOURNEY_REF_PATTERN.fullmatch("JNY-OQ-Login-01/step-2")


def test_journey_ref_pattern_rejects_req_id():
    assert not JOURNEY_REF_PATTERN.fullmatch("REQ-p00001-A")


def test_journey_ref_pattern_rejects_bare_jny_no_number():
    # Must have -<number> suffix to be a valid JNY id
    assert not JOURNEY_REF_PATTERN.fullmatch("JNY-Login")


# ---------------------------------------------------------------------------
# _extract_ids integration tests
# ---------------------------------------------------------------------------


# Verifies: REQ-d00255
def test_extract_ids_journey_only(extractor):
    """Verifies: JNY-OQ-Login-01 yields the whole-journey id."""
    ids = extractor._extract_ids("Verifies: JNY-OQ-Login-01")
    assert "JNY-OQ-Login-01" in ids


# Verifies: REQ-d00256
def test_extract_ids_journey_step(extractor):
    """Verifies: JNY-OQ-Login-01/step-2 yields the step id with suffix."""
    ids = extractor._extract_ids("Verifies: JNY-OQ-Login-01/step-2")
    assert "JNY-OQ-Login-01/step-2" in ids


def test_extract_ids_req_still_works(extractor):
    """Existing REQ-p00001-A extraction is unaffected (no regression)."""
    ids = extractor._extract_ids("Verifies: REQ-p00001-A")
    assert "REQ-p00001-A" in ids


def test_extract_ids_mixed_line(extractor):
    """Mixed line yields both REQ and JNY ids."""
    ids = extractor._extract_ids("Verifies: REQ-p00001-A, JNY-OQ-Login-01/step-2")
    assert "REQ-p00001-A" in ids
    assert "JNY-OQ-Login-01/step-2" in ids


# ---------------------------------------------------------------------------
# Wiring tests: TEST -> STEP and TEST -> JOURNEY edges
# ---------------------------------------------------------------------------


# Verifies: REQ-d00256
def test_step_owns_outgoing_verifies_edge(journey_with_step_test_graph):
    """``Verifies: JNY-OQ-Login-01/step-2`` wires step -> test (outgoing from step).

    The covered node (STEP) is the edge source; the test is the edge target.
    This mirrors how requirements own their verifying tests as outgoing edges.
    """
    from elspais.graph.GraphNode import NodeKind
    from elspais.graph.relations import EdgeKind

    step2 = journey_with_step_test_graph.find_by_id("JNY-OQ-Login-01/step-2")
    assert step2 is not None, "step-2 not found in graph"
    verifies = [e for e in step2.iter_outgoing_edges() if e.kind == EdgeKind.VERIFIES]
    assert len(verifies) == 1
    assert verifies[0].target.kind == NodeKind.TEST  # target = child (the test)


# Verifies: REQ-d00255
def test_whole_journey_owns_outgoing_verifies_edge(journey_with_whole_test_graph):
    """``Verifies: JNY-OQ-Login-01`` wires journey -> test (outgoing from journey)."""
    from elspais.graph.GraphNode import NodeKind
    from elspais.graph.relations import EdgeKind

    jny = journey_with_whole_test_graph.find_by_id("JNY-OQ-Login-01")
    assert jny is not None, "JNY-OQ-Login-01 not found in graph"
    verifies = [e for e in jny.iter_outgoing_edges() if e.kind == EdgeKind.VERIFIES]
    assert any(e.target.kind == NodeKind.TEST for e in verifies)


# Verifies: REQ-d00256
def test_unknown_step_is_broken_reference(journey_with_bad_step_graph, capture_broken_refs):
    """A ``Verifies:`` targeting a non-existent step produces a BrokenReference."""
    refs = capture_broken_refs(journey_with_bad_step_graph)
    assert any(r.target_id == "JNY-OQ-Login-01/step-9" for r in refs)


# ---------------------------------------------------------------------------
# Rename cascade: journey rename propagates to step child IDs
# ---------------------------------------------------------------------------


# Verifies: REQ-d00256
def test_journey_rename_cascades_step_ids():
    """Renaming a USER_JOURNEY node cascades its STEP child IDs in _index."""
    from pathlib import Path

    from elspais.graph.builder import TraceGraph
    from elspais.graph.GraphNode import GraphNode, NodeKind, make_step_id
    from elspais.graph.relations import EdgeKind

    # Build a minimal in-memory graph: journey + 2 steps
    graph = TraceGraph(repo_root=Path("/tmp/test-rename-cascade"))
    jny = GraphNode(id="JNY-Test-01", kind=NodeKind.USER_JOURNEY, label="Test Journey")
    s1 = GraphNode(id=make_step_id("JNY-Test-01", 1), kind=NodeKind.STEP, label="step 1")
    s2 = GraphNode(id=make_step_id("JNY-Test-01", 2), kind=NodeKind.STEP, label="step 2")
    jny.link(s1, EdgeKind.STRUCTURES)
    jny.link(s2, EdgeKind.STRUCTURES)
    graph._roots.append(jny)
    graph._index["JNY-Test-01"] = jny
    graph._index["JNY-Test-01/step-1"] = s1
    graph._index["JNY-Test-01/step-2"] = s2

    graph.rename_node("JNY-Test-01", "JNY-Test-99")

    # Journey renamed
    assert graph.find_by_id("JNY-Test-99") is jny
    assert graph.find_by_id("JNY-Test-01") is None
    # Step IDs updated in _index
    assert graph.find_by_id("JNY-Test-99/step-1") is s1
    assert graph.find_by_id("JNY-Test-99/step-2") is s2
    assert graph.find_by_id("JNY-Test-01/step-1") is None
    assert graph.find_by_id("JNY-Test-01/step-2") is None
    # Step nodes themselves reflect the new ID
    assert s1.id == "JNY-Test-99/step-1"
    assert s2.id == "JNY-Test-99/step-2"
