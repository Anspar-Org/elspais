"""Tests for per-row enrichment used by the nav-tree display-mode toggle."""

# Verifies: REQ-d00211

from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock

from elspais.graph.factory import build_graph
from elspais.server.routes_api import api_tree_data


def _make_state(tmp_path):
    """Build a tiny on-disk fixture and return an AppState-like object."""
    spec = tmp_path / "spec"
    spec.mkdir()
    (spec / "prd.md").write_text(
        "# REQ-p00001: A Title\n\n**Level**: PRD | **Status**: Active\n\nReq one.\n\n"
        "*End* *A Title* | **Hash**: 11111111\n---\n"
    )
    (tmp_path / ".elspais.toml").write_text(
        "version = 4\n"
        '[project]\nname = "test"\nnamespace = "REQ"\n'
        '[levels.prd]\nrank = 1\nletter = "p"\nimplements = ["prd"]\n'
        '[id-patterns]\ncanonical = "{namespace}-{level.letter}{component}"\n'
        '[id-patterns.component]\nstyle = "numeric"\ndigits = 5\nleading_zeros = true\n'
        '[id-patterns.assertions]\nlabel_style = "uppercase"\nmax_count = 26\n'
        '[scanning.spec]\ndirectories = ["spec"]\n'
        "[changelog]\nhash_current = false\n"
    )
    graph = build_graph(repo_root=tmp_path)
    state = MagicMock()
    state.graph = graph
    state.repo_root = tmp_path
    from elspais.config import get_config

    state.config = get_config(start_path=tmp_path, quiet=True)
    return state


def _run_endpoint(state):
    request = MagicMock()
    request.app.state.app_state = state
    resp = asyncio.run(api_tree_data(request))
    return json.loads(resp.body)


def test_tree_rows_have_component_field(tmp_path):
    state = _make_state(tmp_path)
    rows = _run_endpoint(state)
    found = [r for r in rows if r["id"] == "REQ-p00001"]
    assert found, "REQ-p00001 missing from rows"
    assert found[0]["component"] == "00001", found[0]


def test_tree_rows_have_namespace_colors(tmp_path):
    state = _make_state(tmp_path)
    rows = _run_endpoint(state)
    assert rows, "no rows"
    sample = rows[0]
    for key in ("ns_bg", "ns_text", "ns_tint"):
        assert key in sample, f"missing {key} on row"
        assert sample[key], f"empty {key}"
    assert sample["ns_bg"].startswith("#")
    assert sample["ns_tint"].startswith("rgba(")


def test_tree_rows_fallback_to_full_id_when_unparseable(tmp_path):
    state = _make_state(tmp_path)
    rows = _run_endpoint(state)
    for r in rows:
        assert r["component"], f"row {r['id']} has empty component"


def test_tree_data_survives_requirement_cycle(tmp_path):
    """A cycle between two REQUIREMENT nodes (e.g. mutual `Integrates:` across
    repos) must not crash the nav-tree builder. The recursive `_walk` keys its
    visited-set on `(node.id, parent_id, depth)`, which never repeats inside a
    cycle because `depth` increments on every re-entry, so it recurses until it
    raises RecursionError (HTTP 500). The endpoint must break the cycle and
    return a bounded set of rows instead.

    Spec-level cycles are rejected by the builder (allow_circular=false), so we
    build a normal two-requirement graph and inject the cycle programmatically
    via the graph edge API.

    # Verifies: REQ-d00211
    # TODO(CUR-1521): replace with a dedicated cycle-handling REQ
    """
    from elspais.graph.GraphNode import NodeKind
    from elspais.graph.relations import EdgeKind

    spec = tmp_path / "spec"
    spec.mkdir()
    (spec / "prd.md").write_text(
        "# REQ-p00001: First\n\n**Level**: PRD | **Status**: Active\n\nReq one.\n\n"
        "*End* *First* | **Hash**: 11111111\n---\n"
        "# REQ-p00002: Second\n\n**Level**: PRD | **Status**: Active\n\nReq two.\n\n"
        "*End* *Second* | **Hash**: 22222222\n---\n"
    )
    (tmp_path / ".elspais.toml").write_text(
        "version = 4\n"
        '[project]\nname = "test"\nnamespace = "REQ"\n'
        '[levels.prd]\nrank = 1\nletter = "p"\nimplements = ["prd"]\n'
        '[id-patterns]\ncanonical = "{namespace}-{level.letter}{component}"\n'
        '[id-patterns.component]\nstyle = "numeric"\ndigits = 5\nleading_zeros = true\n'
        '[id-patterns.assertions]\nlabel_style = "uppercase"\nmax_count = 26\n'
        '[scanning.spec]\ndirectories = ["spec"]\n'
        "[changelog]\nhash_current = false\n"
    )
    graph = build_graph(repo_root=tmp_path)

    node_a = graph.find_by_id("REQ-p00001")
    node_b = graph.find_by_id("REQ-p00002")
    assert node_a is not None and node_b is not None, "fixture requirements missing"

    # Inject a mutual cycle: each REQUIREMENT is a REQUIREMENT-child of the other.
    node_a.link(node_b, EdgeKind.INTEGRATES)
    node_b.link(node_a, EdgeKind.INTEGRATES)

    # Sanity: the cycle is real via the same traversal `_walk` uses.
    a_req_children = [c for c in node_a.iter_children() if c.kind == NodeKind.REQUIREMENT]
    b_req_children = [c for c in node_b.iter_children() if c.kind == NodeKind.REQUIREMENT]
    assert node_b in a_req_children, "A should have B as a REQUIREMENT child"
    assert node_a in b_req_children, "B should have A as a REQUIREMENT child"

    state = MagicMock()
    state.graph = graph
    state.repo_root = tmp_path
    from elspais.config import get_config

    state.config = get_config(start_path=tmp_path, quiet=True)

    # 1. Must not raise RecursionError (currently FAILS).
    rows = _run_endpoint(state)

    # 2. Both cyclic requirements appear (cycle broken, not dropped).
    row_ids = {r["id"] for r in rows}
    assert "REQ-p00001" in row_ids, row_ids
    assert "REQ-p00002" in row_ids, row_ids

    # 3. Row count is bounded (a fix must break the cycle, not explode it).
    assert len(rows) < 50, f"unbounded expansion: {len(rows)} rows"


def test_journey_row_component_strips_jny_prefix(tmp_path):
    """Journey rows should expose `component` as the descriptor-number
    portion so the compact display mode hides the literal `JNY-` prefix."""
    spec = tmp_path / "spec"
    spec.mkdir()
    (spec / "journeys.md").write_text(
        "## JNY-Onboarding-01: New user onboarding\n\n"
        "**Actor**: New user\n\n"
        "**Goal**: Sign up\n\n"
        "*End* *JNY-Onboarding-01*\n"
    )
    (tmp_path / ".elspais.toml").write_text(
        "version = 4\n"
        '[project]\nname = "test"\nnamespace = "REQ"\n'
        '[levels.prd]\nrank = 1\nletter = "p"\nimplements = ["prd"]\n'
        '[scanning.spec]\ndirectories = ["spec"]\n'
        '[scanning.journey]\ndirectories = ["spec"]\n'
        "[changelog]\nhash_current = false\n"
    )
    graph = build_graph(repo_root=tmp_path)
    state = MagicMock()
    state.graph = graph
    state.repo_root = tmp_path
    from elspais.config import get_config

    state.config = get_config(start_path=tmp_path, quiet=True)
    rows = _run_endpoint(state)
    journeys = [r for r in rows if r.get("kind") == "journey"]
    assert journeys, "expected at least one journey row"
    j = next(r for r in journeys if r["id"] == "JNY-Onboarding-01")
    assert j["component"] == "Onboarding-01", j
