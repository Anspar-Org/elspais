# Verifies: REQ-d00295-A+B+C+D+E+G+H
"""The viewer mounts its whole surface under a configured prefix.

A hosted router places each workspace's viewer under a path of its own,
so the route table, the page's own URLs and the agent surface all have to
sit under that prefix — and an empty prefix has to leave the local viewer
exactly as it was.
"""

from __future__ import annotations

import re

import pytest
from starlette.testclient import TestClient

from elspais.server import app as app_module
from elspais.server.app import create_app, validate_base_path
from elspais.server.state import AppState

PREFIX = "/w/abc"

# Every place a browser is told to request a URL from: a raw fetch, a
# script or stylesheet source, a link, or an event stream. The route
# literals handed to apiFetch stay root-relative by design — the adapter
# prepends the prefix at request time — so they are not request sites.
_REQUEST_SITE = re.compile(r"""(?:fetch\(\s*|src=|href=|EventSource\(\s*)['"]/(?:api|static)/""")


def _state(canonical_federated_graph) -> AppState:
    fg = canonical_federated_graph
    entry = fg._repos[fg._root_repo]
    return AppState(graph=fg, repo_root=entry.repo_root, config=entry.config)


@pytest.fixture(scope="module")
def prefixed(canonical_federated_graph) -> tuple[TestClient, AppState]:
    state = _state(canonical_federated_graph)
    return TestClient(create_app(state, mount_mcp=False, base_path=PREFIX)), state


@pytest.fixture(scope="module")
def unprefixed(canonical_federated_graph) -> TestClient:
    return TestClient(create_app(_state(canonical_federated_graph), mount_mcp=False))


# ---------------------------------------------------------------------------
# A: every route answers under the prefix and nowhere else
# ---------------------------------------------------------------------------


# Verifies: REQ-d00295-A
def test_index_answers_under_the_prefix_and_not_at_the_root(prefixed):
    """The index route swallows a render failure into a 200 JSON body, so a
    status code proves nothing — the page itself has to come back."""
    client, _ = prefixed
    page = client.get(f"{PREFIX}/")
    assert page.status_code == 200
    assert page.text.lstrip().startswith("<!DOCTYPE html>"), page.text[:200]
    assert client.get("/", follow_redirects=False).status_code == 404


# Verifies: REQ-d00295-A
@pytest.mark.parametrize("route", ["/api/status", "/api/tree-data", "/api/dirty"])
def test_api_routes_answer_under_the_prefix_and_not_at_the_root(prefixed, route):
    client, _ = prefixed
    assert client.get(f"{PREFIX}{route}").status_code == 200
    assert client.get(route).status_code == 404


# Verifies: REQ-d00295-A
@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (f"{PREFIX}/api/mutate/status", 409),
        ("/api/mutate/status", 404),
        (f"/x{PREFIX}/api/mutate/status", 404),
    ],
    ids=["under-prefix-refused", "root-unmounted", "prefix-inside-path-unmounted"],
)
def test_detached_guard_fires_under_the_prefix_only(prefixed, path, expected):
    """The guard matches the path by string, so it has to know the prefix:
    a mutation under it is still refused read-only, and a path that merely
    contains the prefix further along is not a mutation route at all."""
    client, state = prefixed
    state.enter_detached("root", "main", "0000000")
    try:
        response = client.post(path, json={})
    finally:
        state.leave_detached("root")
    assert response.status_code == expected
    if expected == 409:
        assert "Read-only" in response.json()["error"]


# Verifies: REQ-d00295-A
def test_static_assets_are_served_under_the_prefix(
    canonical_federated_graph, tmp_path, monkeypatch
):
    asset_dir = tmp_path / "static"
    asset_dir.mkdir()
    (asset_dir / "probe.txt").write_text("served\n")
    monkeypatch.setattr(app_module, "_STATIC_DIR", asset_dir)
    client = TestClient(
        create_app(_state(canonical_federated_graph), mount_mcp=False, base_path=PREFIX)
    )
    assert client.get(f"{PREFIX}/static/probe.txt").text == "served\n"
    assert client.get("/static/probe.txt").status_code == 404


# ---------------------------------------------------------------------------
# B: every URL the page requests carries the prefix
# ---------------------------------------------------------------------------


# Verifies: REQ-d00295-B
def test_the_served_page_carries_the_prefix_and_no_unprefixed_request_site(prefixed):
    client, _ = prefixed
    html = client.get(f"{PREFIX}/").text
    assert f'URL_PREFIX = "{PREFIX}"' in html
    assert _REQUEST_SITE.findall(html) == []


# ---------------------------------------------------------------------------
# C, H: no prefix serves the routes it always served, and the page requests
# the URLs it always requested
# ---------------------------------------------------------------------------


# Verifies: REQ-d00295-C
def test_without_a_prefix_the_root_answers_the_page_and_the_api(unprefixed):
    page = unprefixed.get("/")
    assert page.status_code == 200
    assert page.text.lstrip().startswith("<!DOCTYPE html>"), page.text[:200]
    assert unprefixed.get("/api/status").status_code == 200
    assert unprefixed.get("/w/abc/api/status").status_code == 404


# Verifies: REQ-d00295-H
def test_without_a_prefix_the_page_requests_root_relative_urls(unprefixed):
    """The page prepends its prefix at request time, so an empty prefix
    leaves every request exactly the root-relative URL it always was."""
    page = unprefixed.get("/")
    assert 'URL_PREFIX = ""' in page.text
    assert _REQUEST_SITE.findall(page.text) == []


# ---------------------------------------------------------------------------
# D: the agent surface sits under the same prefix
# ---------------------------------------------------------------------------


# Verifies: REQ-d00295-D
def test_the_mcp_mount_sits_under_the_prefix(canonical_federated_graph):
    """A request the MCP transport refuses for its headers is still a
    request the transport SAW; only an unmounted path answers 404."""
    pytest.importorskip("mcp")
    app = create_app(_state(canonical_federated_graph), mount_mcp=True, base_path=PREFIX)
    with TestClient(app) as client:
        under = client.post(f"{PREFIX}/mcp", json={})
        assert under.status_code != 404, under.text
        assert client.post("/mcp", json={}).status_code == 404


# ---------------------------------------------------------------------------
# E: a malformed prefix is refused naming the form
# ---------------------------------------------------------------------------


# The accepted form, in the refusal's own words.
_FORM = r"each introduced by a single '/' and made only of ASCII letters and digits"


# Verifies: REQ-d00295-E
@pytest.mark.parametrize(
    "bad",
    [
        "w/abc",
        "/w/abc/",
        "/",
        "w",
        "//w",
        "/w//x",
        "/w?x",
        "/w#x",
        "/w abc",
        "/w/%41",
        "/w/./x",
        "/w/../x",
        "/.",
        "/..",
    ],
    ids=[
        "no-leading-slash",
        "trailing-slash",
        "root-alone",
        "bare-word",
        "doubled-leading-slash",
        "doubled-inner-slash",
        "query",
        "fragment",
        "space",
        "percent-escape",
        "dot-segment",
        "dotdot-segment",
        "dot-alone",
        "dotdot-alone",
    ],
)
def test_a_malformed_prefix_is_refused_naming_the_accepted_form(bad):
    """Every shape here is one the page, a router and the mount would
    spell differently from one another, so it names no single path and
    is refused before anything is mounted at it."""
    with pytest.raises(ValueError, match=_FORM):
        validate_base_path(bad)


# Verifies: REQ-d00295-E
@pytest.mark.parametrize("good", ["", "/w", "/w/abc", "/w.x", "/w~x", "/w-1_2", "/w/..."])
def test_an_accepted_prefix_passes_through_unchanged(good):
    assert validate_base_path(good) == good


# Verifies: REQ-d00295-E
@pytest.mark.parametrize("bad", ["//w", "/w?x"])
def test_the_factory_refuses_a_prefix_spelt_apart_by_page_and_mount(canonical_federated_graph, bad):
    """The factory refuses before building: the mount would take this
    prefix raw while the page requests its escaped or truncated spelling,
    and the two would never meet at one path."""
    with pytest.raises(ValueError, match=_FORM):
        create_app(_state(canonical_federated_graph), mount_mcp=False, base_path=bad)


# Verifies: REQ-d00295-E
def test_the_viewer_command_refuses_a_malformed_prefix_before_building(capsys, monkeypatch):
    """Refused up front: the graph build is the expensive step, and a
    prefix already known to be malformed must not pay for it."""
    import argparse

    from elspais.commands import viewer
    from elspais.server import state as state_module

    def _never(*_args, **_kwargs):
        raise AssertionError("the graph was built for a prefix already refused")

    monkeypatch.setattr(state_module.AppState, "from_config", _never)
    rc = viewer._run_server(argparse.Namespace(base_path="w/abc"), open_browser=False)
    assert rc == 1
    assert re.search(_FORM, capsys.readouterr().err)


# ---------------------------------------------------------------------------
# G: a prefix applies to the server alone
# ---------------------------------------------------------------------------


# Verifies: REQ-d00295-G
def test_the_static_generator_refuses_a_prefix_before_building(capsys, monkeypatch):
    """A generated file requests nothing from a server, so a prefix has
    nothing to apply to; it is refused rather than accepted and ignored."""
    import argparse

    from elspais.commands import viewer
    from elspais.graph import factory

    def _never(*_args, **_kwargs):
        raise AssertionError("the graph was built for a static run already refused")

    monkeypatch.setattr(factory, "build_graph", _never)
    rc = viewer._run_static(argparse.Namespace(static=True, base_path="/w/abc"))
    assert rc == 1
    err = capsys.readouterr().err
    assert "--base-path applies to the server only" in err
    assert "Remove --base-path" in err
