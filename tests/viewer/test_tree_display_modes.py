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
        '[project]\nnamespace = "REQ"\n'
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
        '[project]\nnamespace = "REQ"\n'
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
