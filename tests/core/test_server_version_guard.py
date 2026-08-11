# Verifies: REQ-o00062-O, REQ-o00062-I, REQ-o00062-J, REQ-o00062-K, REQ-o00062-L, REQ-o00062-N
"""Optimistic-concurrency guard on the review server's HTTP mutation routes.

The viewer's ``/api/mutate/*`` routes and the MCP mutation tools drive the same
graph inside one daemon. MCP already refuses a mutation whose caller cannot
state the version it believes it is modifying; until the same precondition
holds over HTTP, a human in the viewer and an agent over MCP can still lose
each other's work -- and the half of the parity claim that says "under the
same preconditions and returning the same rejection shape" is unmet.

These tests drive the real Starlette app through ``TestClient`` (the setup in
``test_server_routes.py``), against a throwaway copy of the ``hht-like``
fixture so the routes that touch disk have somewhere safe to write.

The route table is checked against the routes actually registered in
``app.py``, so a new mutation route added without a guard case fails here
rather than shipping unguarded.
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from starlette.testclient import TestClient

import elspais
from elspais.graph import render

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
HHT_LIKE = FIXTURES_DIR / "hht-like"

APP_SOURCE = Path(elspais.__file__).parent / "server" / "app.py"

BOGUS_VERSION = "0" * 16
BOGUS_MUTATION_ID = "f" * 32

# The wire spelling of the precondition. Named once so a rename is a one-line
# change here and the parity claim stays checkable.
VERSION_FIELD = "if_version"
TIP_FIELD = "if_mutation_id"

# The exact keys ``_guard_version`` puts on a rejection. Asserted as a set so
# a route that hand-rolls a slimmer body is caught.
CONFLICT_KEYS = {
    "success",
    "code",
    "node_id",
    "provided_version",
    "current_version",
    "current_state",
    "hint",
}

# The exact keys ``_guard_mutation_tip`` puts on a rejection.
TIP_CONFLICT_KEYS = {"success", "code", "provided_tip", "current_tip", "unseen", "hint"}

REQ = "REQ-d00003"
ASSERTION = "REQ-d00003-A"
SECTION = "REQ-d00003:section:1"
REQ_FILE = "file:spec/dev-impl.md"
OTHER_FILE = "file:spec/ops-deploy.md"
GLOSSARY_FILE = "file:spec/glossary.md"
JOURNEY = "JNY-001"
JOURNEY_FILE = "file:spec/journeys.md"

UNDO_ROUTE = "/api/mutate/undo"

# The wire spelling of the history precondition on the persistence routes,
# mirroring the MCP tools they correspond to (save_mutations,
# refresh_graph(force=True)): ``if_tip_mutation_id``, where ``""`` means
# "I believe nothing is pending".
HISTORY_TIP_FIELD = "if_tip_mutation_id"

# The three non-``/api/mutate/*`` POST routes that act on the mutation log as
# a whole: save persists every writer's pending work, revert and reload
# discard it by rebuilding from disk. Imported by the parity tripwire in
# tests/mcp/test_mcp_http_parity.py so the two suites cannot drift apart.
HISTORY_ROUTES = ("/api/save", "/api/revert", "/api/reload")

# ``/api/save`` refuses a pending change to an Active requirement until the
# caller states the changelog reason. These tests are about the tip guard, so
# they supply one and let the guard be the only thing that can refuse them.
# ``/api/revert`` and ``/api/reload`` ignore the field.
CHANGELOG_REASON = "guard test: persist the seeded edit"


@dataclass(frozen=True)
class RouteCase:
    """One ``/api/mutate/*`` route, its guarded node(s), and a valid payload.

    ``payload`` is everything the route needs *apart from* the version tokens;
    each entry of ``tokens`` names a JSON body field and the node whose version
    belongs in it. ``guarded_id`` is the node a rejection must name -- for a
    multi-token route it is the one the MCP counterpart checks first.
    """

    path: str
    guarded_id: str
    payload: dict
    tokens: dict[str, str] = field(default_factory=dict)
    returns_version: bool = True

    def token_fields(self) -> dict[str, str]:
        return self.tokens or {VERSION_FIELD: self.guarded_id}

    def with_tokens(self, resolve) -> dict:
        """Payload plus a token per guarded node, produced by ``resolve(id)``."""
        body = dict(self.payload)
        for wire_field, node_id in self.token_fields().items():
            body[wire_field] = resolve(node_id)
        return body


# Guarded ids follow the MCP counterparts exactly:
#   - sub-nodes (assertion, section) resolve to their owning REQUIREMENT
#   - a creation is guarded by the parent it is created into
#   - an edge is guarded on the referring (source) node alone      REQ-o00062-M
#   - a move is guarded on the node and on both files              REQ-o00062-M
ROUTE_CASES = [
    RouteCase("/api/mutate/status", REQ, {"node_id": REQ, "new_status": "Draft"}),
    RouteCase("/api/mutate/template", REQ, {"node_id": REQ, "is_template": True}),
    RouteCase("/api/mutate/title", REQ, {"node_id": REQ, "new_title": "Guarded Title"}),
    RouteCase(
        "/api/mutate/assertion",
        ASSERTION,
        {"assertion_id": ASSERTION, "new_text": "SHALL be guarded"},
    ),
    RouteCase(
        "/api/mutate/assertion/add",
        REQ,
        {"req_id": REQ, "text": "SHALL be newly added"},
    ),
    RouteCase(
        "/api/mutate/assertion/delete",
        ASSERTION,
        {"assertion_id": ASSERTION, "confirm": True},
        returns_version=False,
    ),
    RouteCase("/api/mutate/remainder", SECTION, {"node_id": SECTION, "text": "guarded prose"}),
    RouteCase(
        "/api/mutate/remainder/add",
        REQ,
        {"req_id": REQ, "heading": "Guard Notes", "text": "guarded"},
    ),
    RouteCase(
        "/api/mutate/remainder/delete",
        SECTION,
        {"node_id": SECTION},
        returns_version=False,
    ),
    RouteCase(
        "/api/mutate/requirement/add",
        REQ_FILE,
        {"req_id": "REQ-d00099", "title": "Guarded", "level": "DEV", "file_id": REQ_FILE},
    ),
    RouteCase(
        "/api/mutate/requirement/delete",
        REQ,
        {"node_id": REQ, "confirm": True},
        returns_version=False,
    ),
    RouteCase(
        "/api/mutate/edge",
        REQ,
        {
            "action": "add",
            "source_id": REQ,
            "target_id": "REQ-o00001",
            "edge_kind": "IMPLEMENTS",
        },
    ),
    RouteCase(
        "/api/mutate/journey/field",
        JOURNEY,
        {"node_id": JOURNEY, "field": "goal", "value": "Guarded goal"},
    ),
    RouteCase(
        "/api/mutate/journey/section",
        JOURNEY,
        {"node_id": JOURNEY, "action": "add", "name": "Guarded Section"},
    ),
    RouteCase(
        "/api/mutate/journey/add",
        JOURNEY_FILE,
        {"journey_id": "JNY-GUARD-01", "title": "Guarded Journey", "file_id": JOURNEY_FILE},
    ),
    RouteCase("/api/mutate/journey/delete", JOURNEY, {"node_id": JOURNEY, "confirm": True}),
    RouteCase(
        "/api/mutate/move-to-file",
        REQ,
        {"node_id": REQ, "target_file_id": OTHER_FILE},
        tokens={
            VERSION_FIELD: REQ,
            "if_source_file_version": REQ_FILE,
            "if_target_version": OTHER_FILE,
        },
    ),
    RouteCase(
        "/api/mutate/rename-file",
        GLOSSARY_FILE,
        {"file_id": GLOSSARY_FILE, "new_relative_path": "spec/glossary-renamed.md"},
    ),
]

CASE_IDS = [case.path for case in ROUTE_CASES]


def _registered_mutation_routes() -> set[str]:
    """The ``/api/mutate/*`` paths the review server registers.

    Read from the app source rather than listed here, so a route added without
    a guard case is caught instead of silently escaping this suite.
    """
    source = APP_SOURCE.read_text(encoding="utf-8")
    return set(re.findall(r'Route\(\s*"(/api/mutate/[^"]+)"', source))


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def viewer_project(tmp_path: Path) -> Path:
    """A throwaway copy of the hht-like fixture.

    Per-test rather than shared: an unguarded route applies its mutation, and
    two of these routes write to disk, so a shared project would carry one
    test's leaked write into the next and blur why a test failed.
    """
    project = tmp_path / "project"
    shutil.copytree(HHT_LIKE, project)
    return project


@pytest.fixture
def app_state(viewer_project: Path):
    from elspais.server.state import AppState

    return AppState.from_config(repo_root=viewer_project)


@pytest.fixture
def client(app_state) -> TestClient:
    from elspais.server.app import create_app

    return TestClient(create_app(state=app_state, mount_mcp=False))


@pytest.fixture
def version_of(app_state):
    """Resolve a node's current version token from the live graph."""

    def resolve(node_id: str) -> str:
        node = app_state.graph.find_by_id(node_id)
        assert node is not None, f"fixture node {node_id!r} missing"
        return render.node_version(node)

    return resolve


@pytest.fixture
def mcp_tools(app_state, viewer_project: Path):
    """MCP tool closures bound to the *same* graph the HTTP app serves.

    Sharing the graph is the point: the two surfaces must answer an identical
    stale token identically, which cannot be asserted across two graphs.
    """
    pytest.importorskip("mcp")
    from elspais.mcp.server import create_server

    server = create_server(app_state.graph, working_dir=viewer_project)
    return {name: tool.fn for name, tool in server._tool_manager._tools.items()}


def _graph_fingerprint(app_state) -> tuple:
    """A cheap witness that nothing in the graph moved."""
    graph = app_state.graph
    return (
        len(graph.mutation_log),
        tuple(sorted(node.id for node in graph.all_nodes())),
    )


# ─────────────────────────────────────────────────────────────────────────────
# The route table covers the real surface
# ─────────────────────────────────────────────────────────────────────────────


class TestGuardTableCoversEveryRoute:
    """Validates REQ-o00062-O:

    The guard has to hold for the whole HTTP mutation surface, not the part
    someone remembered to list. The surface is read from ``app.py``.
    """

    def test_REQ_o00062_O_route_scan_finds_the_mutation_surface(self):
        """REQ-o00062-O: A silently empty scan would make coverage vacuous."""
        routes = _registered_mutation_routes()

        assert len(routes) >= 15, f"route scan looks broken, found {sorted(routes)}"
        # The multi-line Route(...) registration must not be missed.
        assert "/api/mutate/requirement/delete" in routes

    def test_REQ_o00062_O_every_registered_route_has_a_guard_case(self):
        """REQ-o00062-O: A new mutation route with no guard case fails loudly."""
        covered = {case.path for case in ROUTE_CASES} | {UNDO_ROUTE}

        unguarded = _registered_mutation_routes() - covered

        assert not unguarded, (
            f"HTTP mutation routes with no version-guard test: {sorted(unguarded)}. "
            "Add a RouteCase (and the guard in routes_api.py) before shipping."
        )

    def test_REQ_o00062_O_guard_cases_name_real_routes(self):
        """REQ-o00062-O: A case for a route that no longer exists is dead weight
        that would otherwise mask the loss of a guarded route."""
        stale = {case.path for case in ROUTE_CASES} - _registered_mutation_routes()

        assert not stale, f"RouteCase entries for unregistered routes: {sorted(stale)}"


# ─────────────────────────────────────────────────────────────────────────────
# The precondition itself
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("case", ROUTE_CASES, ids=CASE_IDS)
class TestHttpMutationRoutesRequireAVersion:
    """Validates REQ-o00062-I, REQ-o00062-J:

    Every mutation reachable over HTTP demands the version of the state the
    caller believes it is modifying, and refuses -- with the reconciliation
    payload -- when that version is not current. A caller that supplies no
    token at all is refused on the same terms: an omitted precondition is a
    blind write, which is the failure being prevented.
    """

    def test_REQ_o00062_I_stale_token_is_rejected_with_409(self, client, case: RouteCase):
        """REQ-o00062-I: A stale token blocks the mutation on every route."""
        body = case.with_tokens(lambda _node_id: BOGUS_VERSION)

        resp = client.post(case.path, json=body)

        assert resp.status_code == 409, f"{case.path} -> {resp.status_code}: {resp.text}"
        assert resp.json()["success"] is False

    def test_REQ_o00062_I_missing_token_is_rejected_with_409(self, client, case: RouteCase):
        """REQ-o00062-I: Omitting the precondition is not a way around it."""
        resp = client.post(case.path, json=dict(case.payload))

        assert resp.status_code == 409, f"{case.path} -> {resp.status_code}: {resp.text}"
        assert resp.json()["success"] is False

    def test_REQ_o00062_J_conflict_body_carries_the_reconciliation_payload(
        self, client, case: RouteCase
    ):
        """REQ-o00062-J: The rejection tells the caller the current version and
        the current state, so it can reconcile without a second read."""
        body = case.with_tokens(lambda _node_id: BOGUS_VERSION)

        payload = client.post(case.path, json=body).json()

        assert CONFLICT_KEYS <= set(payload), f"{case.path} conflict is missing keys: {payload}"
        assert payload["code"] == "version_conflict"
        assert payload["node_id"] == case.guarded_id
        assert payload["provided_version"] == BOGUS_VERSION
        assert payload["current_version"] != BOGUS_VERSION
        assert isinstance(payload["current_state"], dict)
        assert "error" not in payload["current_state"]

    def test_REQ_o00062_I_rejected_route_changed_nothing(
        self, client, app_state, version_of, case: RouteCase
    ):
        """REQ-o00062-I: A refusal is a refusal -- the graph is untouched, not
        mutated-then-reported."""
        before_fingerprint = _graph_fingerprint(app_state)
        before_versions = {node_id: version_of(node_id) for node_id in case.token_fields().values()}

        client.post(case.path, json=case.with_tokens(lambda _node_id: BOGUS_VERSION))

        assert _graph_fingerprint(app_state) == before_fingerprint
        assert {node_id: version_of(node_id) for node_id in before_versions} == before_versions

    def test_REQ_o00062_L_absent_node_is_reported_distinctly(self, client, case: RouteCase):
        """REQ-o00062-L: Naming a node that does not exist is not a version
        conflict -- retrying with a fresh token cannot fix it."""
        absent = (
            "file:spec/does-not-exist.md" if case.guarded_id.startswith("file:") else "REQ-d99999"
        )
        body = case.with_tokens(lambda _node_id: BOGUS_VERSION)
        # Point the *guarded* field at a node that is not there. Substituting
        # any other id would leave the guard with a real target and prove
        # nothing about how an absent one is reported.
        replaced = [key for key, value in body.items() if value == case.guarded_id]
        assert replaced, f"{case.path} payload never names its guarded id"
        for key in replaced:
            body[key] = absent

        resp = client.post(case.path, json=body)

        assert resp.status_code != 200, f"{case.path} mutated an absent node"
        assert resp.json().get("code") == "node_not_found", resp.text


@pytest.mark.parametrize("case", ROUTE_CASES, ids=CASE_IDS)
class TestHttpMutationRoutesReturnTheNewVersion:
    """Validates REQ-o00062-K:

    A viewer performing a sequence of edits should not have to re-read between
    them; the current token is accepted and the resulting one comes back.
    """

    def test_REQ_o00062_K_current_token_is_accepted(self, client, version_of, case: RouteCase):
        """REQ-o00062-K: The live token is the one that works."""
        body = case.with_tokens(version_of)

        resp = client.post(case.path, json=body)

        assert resp.status_code == 200, f"{case.path} -> {resp.status_code}: {resp.text}"
        assert resp.json()["success"] is True

    def test_REQ_o00062_K_success_reports_the_resulting_version(
        self, client, version_of, case: RouteCase
    ):
        """REQ-o00062-K: The response carries the token for the next call."""
        if not case.returns_version:
            pytest.skip("MCP counterpart attaches no version to this deletion")
        supplied = version_of(case.guarded_id)

        payload = client.post(case.path, json=case.with_tokens(version_of)).json()

        assert "version" in payload, f"{case.path} returned no version: {payload}"
        if case.path == "/api/mutate/move-to-file":
            # A move does not change the moved node's own version: the version
            # is content-derived and the block text is identical in its new
            # file. Only the two FILE versions move. Returning an unchanged
            # token is correct here, and it is still the token the caller
            # needs for its next edit to that node.
            assert payload["version"] == supplied
        else:
            assert payload["version"] != supplied


# ─────────────────────────────────────────────────────────────────────────────
# One rejection body, not one per surface
# ─────────────────────────────────────────────────────────────────────────────


class TestHttpConflictIsTheMcpConflict:
    """Validates REQ-o00062-O, REQ-o00062-J:

    The parity claim is about the rejection *shape*, not merely the existence
    of a rejection. Asserting the two surfaces produce the same dict for the
    same stale token is what makes a per-route reimplementation of the check
    detectable -- a hand-rolled body will not match ``_guard_version`` output.
    """

    def test_REQ_o00062_O_conflict_body_is_identical_to_the_mcp_tool(
        self, client, mcp_tools, version_of
    ):
        """REQ-o00062-O: Same stale token, same graph, same dict."""
        http_body = client.post(
            "/api/mutate/title",
            json={"node_id": REQ, "new_title": "Guarded Title", VERSION_FIELD: BOGUS_VERSION},
        ).json()

        mcp_body = mcp_tools["mutate_update_title"](
            node_id=REQ, new_title="Guarded Title", if_version=BOGUS_VERSION
        )

        assert http_body == mcp_body

    def test_REQ_o00062_O_edge_conflict_body_is_identical_to_the_mcp_tool(self, client, mcp_tools):
        """REQ-o00062-O: Holds for a relationship mutation too, where the
        guarded node is the referring source rather than the payload's only id."""
        http_body = client.post(
            "/api/mutate/edge",
            json={
                "action": "add",
                "source_id": REQ,
                "target_id": "REQ-o00001",
                "edge_kind": "IMPLEMENTS",
                VERSION_FIELD: BOGUS_VERSION,
            },
        ).json()

        mcp_body = mcp_tools["mutate_add_edge"](
            source_id=REQ,
            target_id="REQ-o00001",
            edge_kind="IMPLEMENTS",
            if_version=BOGUS_VERSION,
        )

        assert http_body == mcp_body


# ─────────────────────────────────────────────────────────────────────────────
# Undo guards the history, not a node
# ─────────────────────────────────────────────────────────────────────────────


class TestUndoRouteGuardsTheMutationLogTip:
    """Validates REQ-o00062-N:

    Undo over HTTP unwinds every writer's pending work, not only the viewer's,
    so it is guarded on the end of the mutation history rather than on any
    node's version -- and reports what the caller had not seen.
    """

    def _apply_one_mutation(self, client, version_of) -> None:
        resp = client.post(
            "/api/mutate/title",
            json={
                "node_id": REQ,
                "new_title": "Applied By Another Writer",
                VERSION_FIELD: version_of(REQ),
            },
        )
        assert resp.status_code == 200, resp.text

    def test_REQ_o00062_N_stale_tip_is_rejected_with_a_log_conflict(self, client):
        """REQ-o00062-N: A tip the log never held is refused -- and refused as a
        history conflict, not a node version conflict."""
        resp = client.post(UNDO_ROUTE, json={TIP_FIELD: BOGUS_MUTATION_ID})

        assert resp.status_code == 409, f"{resp.status_code}: {resp.text}"
        assert resp.json()["code"] == "mutation_log_conflict"

    def test_REQ_o00062_N_conflict_body_carries_the_unseen_entries(self, client, version_of):
        """REQ-o00062-N: The caller is told which pending work it had not seen,
        because that is what it was about to discard."""
        self._apply_one_mutation(client, version_of)

        payload = client.post(UNDO_ROUTE, json={TIP_FIELD: BOGUS_MUTATION_ID}).json()

        assert TIP_CONFLICT_KEYS <= set(payload), payload
        assert payload["provided_tip"] == BOGUS_MUTATION_ID
        assert payload["current_tip"] not in (None, BOGUS_MUTATION_ID)
        assert len(payload["unseen"]) == 1

    def test_REQ_o00062_N_missing_tip_is_rejected(self, client, version_of):
        """REQ-o00062-N: An omitted tip while work is pending is a conflict --
        the wire spelling of "I believe nothing is pending" is wrong here."""
        self._apply_one_mutation(client, version_of)

        resp = client.post(UNDO_ROUTE, json={})

        assert resp.status_code == 409, f"{resp.status_code}: {resp.text}"
        assert resp.json()["code"] == "mutation_log_conflict"

    def test_REQ_o00062_N_rejected_undo_leaves_the_log_intact(self, client, app_state, version_of):
        """REQ-o00062-N: The refused undo unwound nothing."""
        self._apply_one_mutation(client, version_of)
        before = len(app_state.graph.mutation_log)

        client.post(UNDO_ROUTE, json={TIP_FIELD: BOGUS_MUTATION_ID})

        assert len(app_state.graph.mutation_log) == before

    def test_REQ_o00062_N_current_tip_is_accepted(self, client, app_state, version_of):
        """REQ-o00062-N: Naming the real tip unwinds exactly that mutation."""
        self._apply_one_mutation(client, version_of)
        tip = list(app_state.graph.mutation_log.iter_entries())[-1].id

        resp = client.post(UNDO_ROUTE, json={TIP_FIELD: tip})

        assert resp.status_code == 200, f"{resp.status_code}: {resp.text}"
        assert len(app_state.graph.mutation_log) == 0


# ─────────────────────────────────────────────────────────────────────────────
# The token a browser would actually hold
# ─────────────────────────────────────────────────────────────────────────────


class TestTokenFromTheReadSurfaceIsAccepted:
    """Validates REQ-o00062-K:

    The viewer's JS gets its token from the same read endpoints it already
    calls to render a card. If the token the read surface hands out is not the
    one the mutation route demands, the loop does not close for the GUI.
    """

    def test_REQ_o00062_K_token_from_api_node_drives_a_mutation(self, client):
        """REQ-o00062-K: Read a node over HTTP, mutate it with what you read."""
        read = client.get(f"/api/node/{REQ}").json()
        assert "version" in read, f"/api/node hands back no token: {sorted(read)}"

        resp = client.post(
            "/api/mutate/title",
            json={"node_id": REQ, "new_title": "Round Tripped", VERSION_FIELD: read["version"]},
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["version"] != read["version"]

    def test_REQ_o00062_K_second_mutation_can_use_the_returned_token(self, client):
        """REQ-o00062-K: A sequence of edits needs no re-read between them."""
        first = client.post(
            "/api/mutate/title",
            json={
                "node_id": REQ,
                "new_title": "First Edit",
                VERSION_FIELD: client.get(f"/api/node/{REQ}").json()["version"],
            },
        ).json()
        assert first.get("success") is True, first

        second = client.post(
            "/api/mutate/title",
            json={"node_id": REQ, "new_title": "Second Edit", VERSION_FIELD: first["version"]},
        )

        assert second.status_code == 200, second.text


# ─────────────────────────────────────────────────────────────────────────────
# Save / revert / reload guard the history, exactly like undo
# ─────────────────────────────────────────────────────────────────────────────

PENDING_TITLE = "Pending From Writer A"


def _seed_pending_mutation(client, version_of) -> None:
    """Writer A applies one guarded mutation, leaving one pending log entry."""
    resp = client.post(
        "/api/mutate/title",
        json={"node_id": REQ, "new_title": PENDING_TITLE, VERSION_FIELD: version_of(REQ)},
    )
    assert resp.status_code == 200, resp.text


def _log_tip(app_state) -> str:
    entries = list(app_state.graph.mutation_log.iter_entries())
    return entries[-1].id if entries else ""


def _spec_snapshot(viewer_project: Path) -> dict[str, bytes]:
    """Every spec file's bytes, keyed by relative path."""
    spec_dir = viewer_project / "spec"
    return {
        str(p.relative_to(viewer_project)): p.read_bytes()
        for p in sorted(spec_dir.rglob("*"))
        if p.is_file()
    }


@pytest.mark.parametrize("route", HISTORY_ROUTES)
class TestHistoryRoutesRequireTheMutationLogTip:
    """Validates REQ-o00062-N, REQ-o00062-O:

    ``/api/save`` persists every writer's pending mutations; ``/api/revert``
    and ``/api/reload`` rebuild from disk and discard them. All three act on
    the mutation log as a whole, so -- exactly like ``/api/mutate/undo`` and
    the MCP ``save_mutations``/``refresh_graph(force=True)`` -- they require
    the mutation-log tip and refuse a caller whose tip is stale, with the
    same ``mutation_log_conflict`` body MCP produces.
    """

    def test_REQ_o00062_N_stale_tip_is_rejected_with_409(self, client, version_of, route: str):
        """REQ-o00062-N: A tip the log never held blocks the operation."""
        _seed_pending_mutation(client, version_of)

        resp = client.post(route, json={HISTORY_TIP_FIELD: BOGUS_MUTATION_ID})

        assert resp.status_code == 409, f"{route} -> {resp.status_code}: {resp.text}"
        assert resp.json()["code"] == "mutation_log_conflict"

    def test_REQ_o00062_N_absent_tip_while_work_is_pending_is_rejected(
        self, client, version_of, route: str
    ):
        """REQ-o00062-N: An omitted tip asserts an empty log; asserting that
        falsely while work is pending is a conflict, not a free pass."""
        _seed_pending_mutation(client, version_of)

        resp = client.post(route, json={})

        assert resp.status_code == 409, f"{route} -> {resp.status_code}: {resp.text}"
        assert resp.json()["code"] == "mutation_log_conflict"

    def test_REQ_o00062_N_conflict_body_matches_the_mcp_rejection(
        self, client, app_state, version_of, route: str
    ):
        """REQ-o00062-N: One rejection dict, not one per surface -- the body
        carries the same keys and the same unseen listing as the MCP guard."""
        _seed_pending_mutation(client, version_of)
        tip = _log_tip(app_state)

        payload = client.post(route, json={HISTORY_TIP_FIELD: BOGUS_MUTATION_ID}).json()

        assert TIP_CONFLICT_KEYS <= set(payload), f"{route} conflict is missing keys: {payload}"
        assert payload["provided_tip"] == BOGUS_MUTATION_ID
        assert payload["current_tip"] == tip
        assert [entry["id"] for entry in payload["unseen"]] == [tip]
        assert isinstance(payload["hint"], str) and payload["hint"].strip()

    def test_REQ_o00062_N_rejection_leaves_the_pending_work_intact(
        self, client, app_state, version_of, route: str
    ):
        """REQ-o00062-N: The refused call persisted nothing and discarded
        nothing -- the pending entry and its in-memory effect both survive."""
        _seed_pending_mutation(client, version_of)
        graph_before = app_state.graph

        client.post(route, json={HISTORY_TIP_FIELD: BOGUS_MUTATION_ID})

        assert app_state.graph is graph_before, f"{route} replaced the graph on a rejection"
        assert len(app_state.graph.mutation_log) == 1
        assert app_state.graph.find_by_id(REQ).get_label() == PENDING_TITLE

    def test_REQ_o00062_N_current_tip_is_accepted(self, client, app_state, version_of, route: str):
        """REQ-o00062-N: A caller that has seen the log may proceed."""
        _seed_pending_mutation(client, version_of)
        tip = _log_tip(app_state)

        resp = client.post(route, json={HISTORY_TIP_FIELD: tip, "message": CHANGELOG_REASON})

        assert resp.status_code == 200, f"{route} -> {resp.status_code}: {resp.text}"
        assert resp.json()["success"] is True

    def test_REQ_o00062_N_empty_tip_with_nothing_pending_proceeds(self, client, route: str):
        """REQ-o00062-N: The no-op case must not require a read -- "" matches
        an empty log and the operation runs."""
        resp = client.post(route, json={HISTORY_TIP_FIELD: ""})

        assert resp.status_code == 200, f"{route} -> {resp.status_code}: {resp.text}"
        assert resp.json()["success"] is True


class TestHistoryRouteRejectionEffects:
    """Validates REQ-o00062-N:

    What a rejection must *not* have done, measured where each route does its
    damage: save in bytes on disk, revert and reload in discarded log entries.
    """

    def test_REQ_o00062_N_rejected_save_leaves_the_spec_files_byte_identical(
        self, client, viewer_project, version_of
    ):
        """REQ-o00062-N: The guard fires before a single byte is written."""
        _seed_pending_mutation(client, version_of)
        before = _spec_snapshot(viewer_project)

        resp = client.post("/api/save", json={HISTORY_TIP_FIELD: BOGUS_MUTATION_ID})

        assert resp.status_code == 409, f"{resp.status_code}: {resp.text}"
        assert _spec_snapshot(viewer_project) == before
        # No safety branch either: a rejected save must leave no git artifact.
        assert not (viewer_project / ".git").exists()

    def test_REQ_o00062_N_rejected_revert_keeps_the_pending_log(
        self, client, app_state, version_of
    ):
        """REQ-o00062-N: A refused revert discarded nobody's work."""
        _seed_pending_mutation(client, version_of)

        client.post("/api/revert", json={HISTORY_TIP_FIELD: BOGUS_MUTATION_ID})

        assert len(app_state.graph.mutation_log) == 1
        assert app_state.graph.find_by_id(REQ).get_label() == PENDING_TITLE

    def test_REQ_o00062_N_rejected_reload_keeps_the_pending_log(
        self, client, app_state, version_of
    ):
        """REQ-o00062-N: A refused reload discarded nobody's work."""
        _seed_pending_mutation(client, version_of)

        client.post("/api/reload", json={HISTORY_TIP_FIELD: BOGUS_MUTATION_ID})

        assert len(app_state.graph.mutation_log) == 1
        assert app_state.graph.find_by_id(REQ).get_label() == PENDING_TITLE

    def test_REQ_o00062_N_accepted_save_persists_the_pending_edit(
        self, client, app_state, viewer_project, version_of
    ):
        """REQ-o00062-N: With the live tip named, the save runs normally."""
        _seed_pending_mutation(client, version_of)

        resp = client.post(
            "/api/save",
            json={HISTORY_TIP_FIELD: _log_tip(app_state), "message": CHANGELOG_REASON},
        )

        assert resp.status_code == 200, resp.text
        assert PENDING_TITLE in (viewer_project / "spec" / "dev-impl.md").read_text()

    def test_REQ_o00062_N_accepted_revert_discards_the_pending_edit(
        self, client, app_state, version_of
    ):
        """REQ-o00062-N: With the live tip named, the revert rebuilds."""
        _seed_pending_mutation(client, version_of)

        resp = client.post("/api/revert", json={HISTORY_TIP_FIELD: _log_tip(app_state)})

        assert resp.status_code == 200, resp.text
        assert len(app_state.graph.mutation_log) == 0
        assert app_state.graph.find_by_id(REQ).get_label() != PENDING_TITLE

    def test_REQ_o00062_N_accepted_reload_discards_the_pending_edit(
        self, client, app_state, version_of
    ):
        """REQ-o00062-N: With the live tip named, the reload rebuilds."""
        _seed_pending_mutation(client, version_of)

        resp = client.post("/api/reload", json={HISTORY_TIP_FIELD: _log_tip(app_state)})

        assert resp.status_code == 200, resp.text
        assert len(app_state.graph.mutation_log) == 0
        assert app_state.graph.find_by_id(REQ).get_label() != PENDING_TITLE

    def test_REQ_o00062_N_second_writer_blind_save_sees_the_first_writers_entry(
        self, client, app_state, version_of
    ):
        """REQ-o00062-N: The asymmetric two-writer story. Writer A mutates;
        writer B, who has seen nothing, posts a save asserting an empty log.
        B is refused and shown exactly A's pending entry -- the work B was
        about to commit to disk sight unseen."""
        _seed_pending_mutation(client, version_of)
        tip = _log_tip(app_state)

        resp = client.post("/api/save", json={HISTORY_TIP_FIELD: ""})

        assert resp.status_code == 409, f"{resp.status_code}: {resp.text}"
        payload = resp.json()
        assert payload["code"] == "mutation_log_conflict"
        assert payload["provided_tip"] == ""
        assert payload["current_tip"] == tip
        assert [entry["id"] for entry in payload["unseen"]] == [tip]
        assert payload["unseen"][0]["target_id"] == REQ


# ─────────────────────────────────────────────────────────────────────────────
# The auto-refresh middleware may not discard pending mutations either
# ─────────────────────────────────────────────────────────────────────────────


class TestAutoRefreshDoesNotDiscardPendingMutations:
    """Validates REQ-o00062-N:

    ``AppState.ensure_fresh()`` runs on every request. If it rebuilds the
    graph while mutations are pending, it silently discards every writer's
    unsaved work -- the same harm the tip guard exists to prevent, reachable
    by merely touching a file's mtime. Mirroring MCP ``refresh_graph``'s
    refusal without ``force=True``, ensure_fresh SHALL NOT rebuild while the
    mutation log is non-empty; with nothing pending it may rebuild freely.
    """

    def _touch_scanned_file(self, viewer_project: Path) -> None:
        target = viewer_project / "spec" / "dev-impl.md"
        stat = target.stat()
        os.utime(target, (stat.st_atime, stat.st_mtime + 5.0))

    def test_REQ_o00062_N_pending_mutations_block_the_auto_rebuild(self, app_state, viewer_project):
        """REQ-o00062-N: The graph object and the pending entry both survive
        an mtime change while work is pending."""
        app_state.graph.update_title(REQ, PENDING_TITLE)
        assert len(app_state.graph.mutation_log) == 1
        graph_before = app_state.graph
        self._touch_scanned_file(viewer_project)
        app_state._last_stale_check = 0.0

        app_state.ensure_fresh()

        assert app_state.graph is graph_before, (
            "ensure_fresh() rebuilt over a non-empty mutation log, "
            "silently discarding pending work"
        )
        assert len(app_state.graph.mutation_log) == 1
        assert app_state.graph.find_by_id(REQ).get_label() == PENDING_TITLE

    def test_REQ_o00062_N_clean_log_still_admits_the_auto_rebuild(self, app_state, viewer_project):
        """REQ-o00062-N: With nothing pending there is nothing to protect --
        the same mtime change does trigger the rebuild."""
        graph_before = app_state.graph
        self._touch_scanned_file(viewer_project)
        app_state._last_stale_check = 0.0

        rebuilt = app_state.ensure_fresh()

        assert rebuilt is True
        assert app_state.graph is not graph_before


# ─────────────────────────────────────────────────────────────────────────────
# A refused save is not automatically a conflict
# ─────────────────────────────────────────────────────────────────────────────


class TestNotEveryRefusedSaveIsAConflict:
    """Validates REQ-o00062-O: the rejection shape a caller sees over HTTP is
    the one MCP produces, and 409 is reserved for the conflict family it names.

    ``/api/save`` used to answer 409 for every refusal, so a caller following
    the documented conflict recipe -- re-read the tip, retry -- retried
    forever against a missing changelog reason it was never told to supply,
    and against a disk that could not be written. The two are told apart now:
    a conflict stays 409 with its body untouched, a refusal the caller must
    answer is 400, and a write that failed is 500. The bodies carry a ``code``
    so the distinction survives a caller that reads the JSON rather than the
    status line.

    Both surfaces reach disk through ``persist_pending``, so the rule the MCP
    save tool enforces is the rule enforced here.
    """

    def test_REQ_o00062_O_stale_tip_is_still_the_conflict_it_was(
        self, client, app_state, version_of
    ):
        """The unification must not have disturbed the guard: same status,
        same code, same keys, and the pending work untouched."""
        _seed_pending_mutation(client, version_of)
        tip = _log_tip(app_state)

        resp = client.post(
            "/api/save",
            json={HISTORY_TIP_FIELD: BOGUS_MUTATION_ID, "message": CHANGELOG_REASON},
        )

        assert resp.status_code == 409, f"{resp.status_code}: {resp.text}"
        payload = resp.json()
        assert payload["code"] == "mutation_log_conflict"
        assert TIP_CONFLICT_KEYS <= set(payload), payload
        assert payload["current_tip"] == tip
        assert len(app_state.graph.mutation_log) == 1

    def test_REQ_o00062_O_missing_changelog_reason_is_not_a_conflict(
        self, client, app_state, version_of
    ):
        """Nothing is in conflict: one writer, a live tip, and a rule the
        caller has simply not answered yet. Retrying the identical request is
        exactly what a 409 would tell the caller to do, and it cannot work."""
        _seed_pending_mutation(client, version_of)

        resp = client.post("/api/save", json={HISTORY_TIP_FIELD: _log_tip(app_state)})

        assert resp.status_code == 400, f"{resp.status_code}: {resp.text}"
        payload = resp.json()
        assert payload["success"] is False
        assert payload["code"] == "changelog_message_required"
        assert "message" in payload["error"], payload
        assert len(app_state.graph.mutation_log) == 1, "the refused save discarded the work"

    def test_REQ_o00062_O_write_failure_is_not_a_conflict(
        self, client, app_state, viewer_project, version_of, monkeypatch
    ):
        """A real failure on the real path: the renderer raises where it would
        raise on a full or read-only disk. Nothing is in conflict, the caller
        has supplied everything asked of it, and the answer says so."""
        _seed_pending_mutation(client, version_of)
        before = _spec_snapshot(viewer_project)

        def _explode(*args, **kwargs):
            raise OSError("read-only file system")

        monkeypatch.setattr("elspais.graph.render.render_save", _explode)

        resp = client.post(
            "/api/save",
            json={HISTORY_TIP_FIELD: _log_tip(app_state), "message": CHANGELOG_REASON},
        )

        assert resp.status_code == 500, f"{resp.status_code}: {resp.text}"
        payload = resp.json()
        assert payload["success"] is False
        assert payload["code"] == "save_failed"
        assert _spec_snapshot(viewer_project) == before
        assert (
            len(app_state.graph.mutation_log) == 1
        ), "a save that could not write also destroyed the work it was holding"

    def test_REQ_o00062_O_the_save_that_answered_the_rule_succeeds(
        self, client, app_state, viewer_project, version_of
    ):
        """The positive half: with the tip named and the reason given, the
        save runs through the shared path and reaches disk."""
        _seed_pending_mutation(client, version_of)

        resp = client.post(
            "/api/save",
            json={HISTORY_TIP_FIELD: _log_tip(app_state), "message": CHANGELOG_REASON},
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["success"] is True
        assert PENDING_TITLE in (viewer_project / "spec" / "dev-impl.md").read_text()
        assert len(app_state.graph.mutation_log) == 0
