# Verifies: REQ-o00062-O, REQ-o00062-I, REQ-o00062-J, REQ-o00062-K
"""MCP/HTTP mutation parity, and the version guard on the parity tools.

The review server and the MCP server drive the same graph. An agent and a
human must therefore have the same capabilities and the same safety: every
mutation the viewer can perform over HTTP has to be reachable through MCP,
with the same preconditions and the same rejection shape.

Five mutations existed only as module-level ``_mutate_*`` helpers reachable
from HTTP: the Template toggle and the four journey mutations. They are
registered MCP tools, and -- being registered after the optimistic-concurrency
contract landed -- they carry the required ``if_version`` from birth rather
than being retrofitted.

Direction of the parity claim is deliberate: HTTP is a subset of MCP. MCP
carries tools with no HTTP equivalent (``apply_link``, ``rename_node``,
``change_edge_kind``, ``save_mutations``, ...) and that is not a defect.

These tests drive the registered tool closures, not the helpers, because the
guard lives in the tool wrapper.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

import elspais
from elspais.graph import render

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
HHT_LIKE = FIXTURES_DIR / "hht-like"

APP_SOURCE = Path(elspais.__file__).parent / "server" / "app.py"

BOGUS_VERSION = "0" * 16

JOURNEY = "JNY-001"
JOURNEY_FILE = "file:spec/journeys.md"

CONFLICT_KEYS = {
    "success",
    "code",
    "node_id",
    "provided_version",
    "current_version",
    "current_state",
    "hint",
}

# Every ``/api/mutate/*`` route the review server exposes, and the MCP tool
# that reaches the same mutation. Routes are read from app.py at test time
# (see TestHttpMutationsAreReachableOverMcp) so a new route with no entry here
# fails rather than passing unnoticed.
ROUTE_TO_TOOL = {
    "/api/mutate/status": "mutate_change_status",
    "/api/mutate/template": "mutate_set_stereotype",
    "/api/mutate/title": "mutate_update_title",
    "/api/mutate/assertion": "mutate_update_assertion",
    "/api/mutate/assertion/add": "mutate_add_assertion",
    "/api/mutate/assertion/delete": "mutate_delete_assertion",
    "/api/mutate/remainder": "mutate_update_remainder",
    "/api/mutate/remainder/add": "mutate_add_remainder",
    "/api/mutate/remainder/delete": "mutate_delete_remainder",
    "/api/mutate/requirement/add": "mutate_add_requirement",
    "/api/mutate/requirement/delete": "mutate_delete_requirement",
    "/api/mutate/edge": "mutate_add_edge",
    "/api/mutate/journey/field": "mutate_update_journey_field",
    "/api/mutate/journey/section": "mutate_journey_section",
    "/api/mutate/journey/add": "mutate_add_journey",
    "/api/mutate/journey/delete": "mutate_delete_journey",
    "/api/mutate/move-to-file": "mutate_move_node_to_file",
    "/api/mutate/rename-file": "mutate_rename_file",
    "/api/mutate/undo": "undo_last_mutation",
}

# The five tools this change adds, with a call that would mutate the fixture
# if the guard let it through, and the id whose version guards that call.
# ``mutate_add_journey`` creates a node, so it is guarded by its parent FILE.
PARITY_TOOL_CALLS = [
    (
        "mutate_set_stereotype",
        "REQ-d00003",
        {"node_id": "REQ-d00003", "is_template": True},
    ),
    (
        "mutate_update_journey_field",
        JOURNEY,
        {"node_id": JOURNEY, "field_name": "goal", "value": "Leaked goal"},
    ),
    (
        "mutate_journey_section",
        JOURNEY,
        {"node_id": JOURNEY, "action": "add", "name": "Leaked Section"},
    ),
    (
        "mutate_add_journey",
        JOURNEY_FILE,
        {"journey_id": "JNY-900", "title": "Leaked Journey", "file_id": JOURNEY_FILE},
    ),
    (
        "mutate_delete_journey",
        JOURNEY,
        {"node_id": JOURNEY, "confirm": True},
    ),
]

PARITY_IDS = [call[0] for call in PARITY_TOOL_CALLS]


def node_version(node) -> str:
    """Resolve ``render.node_version`` at call time."""
    return render.node_version(node)


def _http_mutation_routes() -> set[str]:
    """The ``/api/mutate/*`` paths registered by the review server.

    Read from the app source rather than listed here, so a route added
    without a matching MCP tool is caught instead of drifting.
    """
    source = APP_SOURCE.read_text(encoding="utf-8")
    return set(re.findall(r'Route\(\s*"(/api/mutate/[^"]+)"', source))


def _registered_post_routes() -> set[str]:
    """EVERY POST path registered in app.py, not only ``/api/mutate/*``.

    ``_http_mutation_routes()`` sees the mutate prefix alone, which is how
    ``/api/save``, ``/api/revert`` and ``/api/reload`` -- three routes that
    persist or discard every writer's pending mutations -- stayed invisible
    to the guard-coverage sweeps. This scan has no prefix filter.
    """
    source = APP_SOURCE.read_text(encoding="utf-8")
    return set(re.findall(r'Route\(\s*"([^"]+)"\s*,[^)]*methods=\[[^\]]*"POST"', source))


# The three POST routes that act on the mutation log as a whole. Kept equal
# to tests/core/test_server_version_guard.py::HISTORY_ROUTES by the tripwire
# below, so a route can join this list only alongside its tip-guard tests.
HISTORY_ROUTES = {"/api/save", "/api/revert", "/api/reload"}

# POST routes that change state OUTSIDE the shared graph and its pending
# mutation log, and are therefore not subject to the version/tip guards.
# Every entry needs a reason; an unlisted new POST route fails the tripwire.
EXEMPT_POST_ROUTES = {
    "/api/shutdown",  # process lifecycle; touches no graph state
    "/api/session/attach",  # process lifetime only: records that a client is
    # using this daemon (REQ-o00074-E). Reads and writes no graph state and no
    # mutation-log entry, so there is no version for a caller to name.
    "/api/comment/add",  # append-only comment store, its own JSONL files
    "/api/comment/reply",  # (comments are an annotation layer, not the graph)
    "/api/comment/resolve",
    "/api/git/branch",  # git working-tree operations; concurrent-write
    "/api/git/push",  # safety is git's own (index locks, non-FF refusal),
    "/api/git/pull",  # and they do not read or write the mutation log
    "/api/git/checkout",
    "/api/git/commit",
    "/api/git/checkout-commit",
}


@pytest.fixture
def tools(canonical_federated_graph):
    """Map of MCP tool name -> raw closure, bound to the canonical graph."""
    pytest.importorskip("mcp")
    from elspais.mcp.server import create_server

    server = create_server(canonical_federated_graph, working_dir=HHT_LIKE)
    return {name: tool.fn for name, tool in server._tool_manager._tools.items()}


@pytest.fixture
def rollback(canonical_federated_graph):
    """Undo whatever a single test mutated, so the session graph stays pristine.

    Undo MUST run on the same object the ``tools`` fixture mutates — the
    FederatedGraph. Undoing on the inner TraceGraph instead bypasses
    ``_federated_log.pop()`` and ``_rebuild_ownership()``, which leaves the
    federated index inconsistent and silently contaminates later tests.
    """
    before = len(canonical_federated_graph.mutation_log)
    yield canonical_federated_graph
    while len(canonical_federated_graph.mutation_log) > before:
        if canonical_federated_graph.undo_last() is None:
            break


# ─────────────────────────────────────────────────────────────────────────────
# The parity claim itself
# ─────────────────────────────────────────────────────────────────────────────


class TestHttpMutationsAreReachableOverMcp:
    """Validates REQ-o00062-O:

    Every mutation exposed by the review server's HTTP interface is also
    exposed as an MCP tool. The route list is derived from the server source,
    so adding a route without a tool breaks this suite.
    """

    def test_REQ_o00062_O_route_scan_finds_the_mutation_surface(self):
        """REQ-o00062-O: The scan reads real routes -- a silent empty set would
        make the parity assertion vacuous."""
        routes = _http_mutation_routes()

        assert len(routes) >= 15, f"route scan looks broken, found {sorted(routes)}"
        # A multi-line Route(...) registration must not be missed.
        assert "/api/mutate/requirement/delete" in routes

    def test_REQ_o00062_O_every_http_route_is_mapped_to_a_tool(self):
        """REQ-o00062-O: No HTTP mutation route is unaccounted for."""
        unmapped = _http_mutation_routes() - set(ROUTE_TO_TOOL)

        assert not unmapped, (
            f"HTTP mutation routes with no MCP tool mapping: {sorted(unmapped)}. "
            "Add the route to ROUTE_TO_TOOL and register the MCP tool."
        )

    def test_REQ_o00062_O_every_http_route_has_an_mcp_tool(self, tools):
        """REQ-o00062-O: Each mapped tool is actually registered on the server."""
        missing = {
            route: tool
            for route, tool in ROUTE_TO_TOOL.items()
            if route in _http_mutation_routes() and tool not in tools
        }

        assert not missing, (
            "HTTP mutations unreachable over MCP (route -> missing tool): " f"{missing}"
        )

    def test_REQ_o00062_O_mcp_may_exceed_http(self, tools):
        """REQ-o00062-O: The superset direction is intended, not a gap.

        Asserted so a future reader does not "fix" parity by deleting MCP-only
        tools that have no viewer equivalent.
        """
        mcp_only = {"apply_link", "save_mutations", "mutate_rename_node"}

        assert mcp_only <= set(tools)
        assert not (mcp_only & set(ROUTE_TO_TOOL.values()))


# ─────────────────────────────────────────────────────────────────────────────
# No POST route may escape classification
# ─────────────────────────────────────────────────────────────────────────────


class TestEveryPostRouteIsClassified:
    """Validates REQ-o00062-O:

    The guard sweeps used to build their inventory from paths matching
    ``/api/mutate/`` only, so a state-changing route outside that prefix was
    invisible to the very test meant to catch unguarded routes. This tripwire
    enumerates ALL registered POST routes and requires each to be either a
    guarded mutate route, a tip-guarded history route, or an explicitly
    exempted non-graph route. A new state-changing POST route added without
    joining one of those lists fails here.
    """

    def test_REQ_o00062_O_post_scan_finds_the_whole_surface(self):
        """REQ-o00062-O: The scan sees past the mutate prefix -- a silently
        narrow scan is exactly the hole being closed."""
        routes = _registered_post_routes()

        assert len(routes) >= 30, f"POST route scan looks broken, found {sorted(routes)}"
        # The multi-line Route(...) registration must not be missed.
        assert "/api/mutate/requirement/delete" in routes
        # And the routes the old prefix-scan could never see must be.
        assert HISTORY_ROUTES <= routes

    def test_REQ_o00062_O_every_post_route_joins_exactly_one_list(self):
        """REQ-o00062-O: mutate-guarded, history-guarded, or exempted-with-a-
        reason. There is no fourth category."""
        routes = _registered_post_routes()
        mutate_routes = {r for r in routes if r.startswith("/api/mutate/")}

        unclassified = routes - mutate_routes - HISTORY_ROUTES - EXEMPT_POST_ROUTES

        assert not unclassified, (
            f"POST routes with no guard classification: {sorted(unclassified)}. "
            "Either add the version/tip guard and the matching test coverage "
            "(RouteCase in test_server_version_guard.py, or HISTORY_ROUTES), "
            "or exempt the route here with a reason."
        )

    def test_REQ_o00062_O_classification_lists_name_real_routes(self):
        """REQ-o00062-O: A stale entry would mask the loss of a guarded route."""
        routes = _registered_post_routes()

        stale = (HISTORY_ROUTES | EXEMPT_POST_ROUTES) - routes

        assert not stale, f"classified routes no longer registered: {sorted(stale)}"
        assert not (HISTORY_ROUTES & EXEMPT_POST_ROUTES)

    def test_REQ_o00062_O_history_routes_match_the_tip_guard_suite(self):
        """REQ-o00062-O: The list here and the list the tip-guard tests
        exercise are the same list, so a route cannot be declared history-
        guarded without the tests that make that true."""
        from tests.core.test_server_version_guard import HISTORY_ROUTES as GUARDED

        assert HISTORY_ROUTES == set(GUARDED)

    def test_REQ_o00062_O_mutate_routes_match_the_version_guard_suite(self):
        """REQ-o00062-O: Every mutate route the scan finds is in the node-
        version guard inventory (its own suite asserts the converse)."""
        from tests.core.test_server_version_guard import ROUTE_CASES, UNDO_ROUTE

        covered = {case.path for case in ROUTE_CASES} | {UNDO_ROUTE}
        mutate_routes = {r for r in _registered_post_routes() if r.startswith("/api/mutate/")}

        assert mutate_routes <= covered, (
            f"mutate routes missing from the version-guard inventory: "
            f"{sorted(mutate_routes - covered)}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# The new tools are guarded from birth
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("tool_name", "guarded_id", "kwargs"),
    PARITY_TOOL_CALLS,
    ids=PARITY_IDS,
)
class TestParityToolsGuardVersion:
    """Validates REQ-o00062-O, REQ-o00062-I, REQ-o00062-J:

    The five newly-exposed mutations take a required ``if_version`` and reject
    a stale one with the same payload shape as the tools that already had it,
    so an agent gets the same safety as the viewer.
    """

    def test_REQ_o00062_I_if_version_is_a_required_parameter(
        self, tools, tool_name, guarded_id, kwargs
    ):
        """REQ-o00062-I: if_version has no default -- callers cannot omit it."""
        params = inspect.signature(tools[tool_name]).parameters

        assert "if_version" in params, f"{tool_name} does not accept if_version"
        assert params["if_version"].default is inspect.Parameter.empty

    def test_REQ_o00062_I_omitting_if_version_is_a_type_error(
        self, tools, tool_name, guarded_id, kwargs
    ):
        """REQ-o00062-I: A call with no version cannot reach the graph at all."""
        with pytest.raises(TypeError):
            tools[tool_name](**kwargs)

    def test_REQ_o00062_I_stale_version_rejected_and_graph_untouched(
        self, canonical_graph, tools, tool_name, guarded_id, kwargs
    ):
        """REQ-o00062-I: A bogus version blocks the mutation for every tool."""
        before = node_version(canonical_graph.find_by_id(guarded_id))

        result = tools[tool_name](if_version=BOGUS_VERSION, **kwargs)

        assert result["success"] is False, f"{tool_name} applied a stale-version mutation"
        assert result["code"] == "version_conflict"
        assert canonical_graph.find_by_id(guarded_id) is not None
        assert node_version(canonical_graph.find_by_id(guarded_id)) == before

    def test_REQ_o00062_J_conflict_shape_matches_the_established_tools(
        self, tools, tool_name, guarded_id, kwargs
    ):
        """REQ-o00062-J: Every tool reports a rejection with the same keys."""
        result = tools[tool_name](if_version=BOGUS_VERSION, **kwargs)

        assert CONFLICT_KEYS <= set(result), f"{tool_name} conflict is missing keys"
        assert result["node_id"] == guarded_id
        assert result["provided_version"] == BOGUS_VERSION
        assert result["current_version"] != BOGUS_VERSION
        assert isinstance(result["current_state"], dict)
        assert "error" not in result["current_state"]

    def test_REQ_o00062_K_current_version_is_accepted_and_a_new_one_returned(
        self, rollback, tools, tool_name, guarded_id, kwargs
    ):
        """REQ-o00062-K: The live token succeeds and the result carries the
        version to thread into the next call."""
        current = node_version(rollback.find_by_id(guarded_id))

        result = tools[tool_name](if_version=current, **kwargs)

        assert result["success"] is True, result.get("error")
        assert result["version"] != current

    def test_REQ_o00062_L_missing_node_is_not_a_version_conflict(
        self, tools, tool_name, guarded_id, kwargs
    ):
        """REQ-o00062-L: An absent target is reported as node_not_found."""
        absent = {**kwargs}
        key = "file_id" if tool_name == "mutate_add_journey" else "node_id"
        absent[key] = "JNY-does-not-exist"

        result = tools[tool_name](if_version=BOGUS_VERSION, **absent)

        assert result["success"] is False
        assert result["code"] == "node_not_found"


# ─────────────────────────────────────────────────────────────────────────────
# Creation guards its parent, not the node it is about to make
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.incremental
class TestAddJourneyGuardsItsParentFile:
    """Validates REQ-o00062-O, REQ-o00062-I:

    A journey does not exist yet when it is created, so ``mutate_add_journey``
    states the version of the FILE it is added to -- the same choice
    ``mutate_add_requirement`` makes with ``parent_id``. Two agents appending
    journeys to one file therefore cannot both write blind.
    """

    NEW_ID = "JNY-901"
    SECOND_ID = "JNY-902"

    def test_REQ_o00062_I_file_version_admits_the_first_journey(self, mutable_graph, tools):
        """REQ-o00062-I: The parent FILE's version is the accepted token."""
        file_version = node_version(mutable_graph.find_by_id(JOURNEY_FILE))
        TestAddJourneyGuardsItsParentFile.spent = file_version

        result = tools["mutate_add_journey"](
            journey_id=self.NEW_ID,
            title="Password Reset",
            file_id=JOURNEY_FILE,
            if_version=file_version,
        )

        assert result["success"] is True, result.get("error")
        assert mutable_graph.find_by_id(self.NEW_ID) is not None
        TestAddJourneyGuardsItsParentFile.threaded = result["version"]

    def test_REQ_o00062_I_the_files_version_moved_with_the_addition(self, mutable_graph):
        """REQ-o00062-I: Adding a journey changes the FILE's composition, so
        the token a concurrent writer holds is genuinely stale."""
        assert node_version(mutable_graph.find_by_id(JOURNEY_FILE)) != self.spent

    def test_REQ_o00062_I_second_writer_with_the_spent_token_is_rejected(
        self, mutable_graph, tools
    ):
        """REQ-o00062-I: The pre-addition token no longer admits a write."""
        result = tools["mutate_add_journey"](
            journey_id=self.SECOND_ID,
            title="Never Lands",
            file_id=JOURNEY_FILE,
            if_version=self.spent,
        )

        assert result["success"] is False
        assert result["code"] == "version_conflict"
        assert result["node_id"] == JOURNEY_FILE, "guard must name the parent FILE"
        assert mutable_graph.find_by_id(self.SECOND_ID) is None

    def test_REQ_o00062_K_returned_token_threads_into_the_next_addition(self, mutable_graph, tools):
        """REQ-o00062-K: The token returned by the first add is directly usable."""
        result = tools["mutate_add_journey"](
            journey_id=self.SECOND_ID,
            title="Account Recovery",
            file_id=JOURNEY_FILE,
            if_version=self.threaded,
        )

        assert result["success"] is True, result.get("error")
        assert mutable_graph.find_by_id(self.SECOND_ID) is not None


# ─────────────────────────────────────────────────────────────────────────────
# Journey field/section edits carry the journey's own version
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.incremental
class TestJourneyEditsThreadVersions:
    """Validates REQ-o00062-I, REQ-o00062-K:

    Journey field and section edits are guarded by the journey node itself,
    and successive edits thread the returned token with no intervening read.
    """

    def test_REQ_o00062_K_field_update_returns_the_new_version(self, mutable_graph, tools):
        """REQ-o00062-K: Success reports the journey's post-edit version."""
        before = node_version(mutable_graph.find_by_id(JOURNEY))
        TestJourneyEditsThreadVersions.stale = before

        result = tools["mutate_update_journey_field"](
            node_id=JOURNEY,
            field_name="goal",
            value="Reach the dashboard without re-authenticating",
            if_version=before,
        )

        assert result["success"] is True, result.get("error")
        assert result["version"] == node_version(mutable_graph.find_by_id(JOURNEY))
        assert result["version"] != before
        TestJourneyEditsThreadVersions.threaded = result["version"]

    def test_REQ_o00062_K_section_add_accepts_the_threaded_token(self, mutable_graph, tools):
        """REQ-o00062-K: The field edit's token admits the section edit."""
        result = tools["mutate_journey_section"](
            node_id=JOURNEY,
            action="add",
            name="Preconditions",
            content="The user already has an account.",
            if_version=self.threaded,
        )

        assert result["success"] is True, result.get("error")
        assert "Preconditions" in render.render_node(mutable_graph.find_by_id(JOURNEY))

    def test_REQ_o00062_I_stale_token_from_before_the_field_edit_is_rejected(
        self, mutable_graph, tools
    ):
        """REQ-o00062-I: A reader holding the pre-edit journey cannot delete it."""
        result = tools["mutate_delete_journey"](
            node_id=JOURNEY, confirm=True, if_version=self.stale
        )

        assert result["success"] is False
        assert result["code"] == "version_conflict"
        assert mutable_graph.find_by_id(JOURNEY) is not None

    def test_REQ_o00062_I_delete_with_the_current_version_succeeds(self, mutable_graph, tools):
        """REQ-o00062-I: Reconciled against the live version, the delete lands."""
        current = node_version(mutable_graph.find_by_id(JOURNEY))

        result = tools["mutate_delete_journey"](node_id=JOURNEY, confirm=True, if_version=current)

        assert result["success"] is True, result.get("error")
        assert mutable_graph.find_by_id(JOURNEY) is None


# ─────────────────────────────────────────────────────────────────────────────
# The version guard does not displace the template safety guard
# ─────────────────────────────────────────────────────────────────────────────


def _template_with_instance_server():
    """MCP tools over a graph where REQ-p00044 Satisfies template REQ-p80001.

    The hht-like fixture has no ``Satisfies:`` declarations and therefore no
    INSTANCE clones, so the un-template safety guard cannot be exercised
    against it. This mirrors ``tests/core/test_set_stereotype.py``.
    """
    pytest.importorskip("mcp")
    from elspais.graph.federated import FederatedGraph
    from elspais.mcp.server import create_server
    from tests.core.graph_test_helpers import build_graph, make_requirement

    assertions = [
        {"label": "A", "text": "obligation one"},
        {"label": "B", "text": "obligation two"},
    ]
    template = make_requirement(
        "REQ-p80001",
        title="Electronic Signature Standard",
        template=True,
        assertions=list(assertions),
    )
    declaring = make_requirement(
        "REQ-p00044",
        title="Document Management",
        satisfies=["REQ-p80001"],
    )
    graph = build_graph(template, declaring)
    fed = FederatedGraph.from_single(
        graph, {"project": {"name": "test", "namespace": "REQ"}}, Path("/test/repo")
    )
    server = create_server(fed, working_dir=HHT_LIKE)
    return graph, {name: tool.fn for name, tool in server._tool_manager._tools.items()}


class TestSetStereotypeSafetyGuardSurvivesVersioning:
    """Validates REQ-o00062-O, REQ-o00062-I:

    Un-templating a requirement that has live INSTANCE clones is refused
    unless forced. A correct ``if_version`` proves the caller read current
    state -- it does not make the destructive toggle safe, so the block still
    applies, and the block is reported as a block rather than as a conflict.
    """

    def test_REQ_o00062_O_current_version_does_not_bypass_the_instance_block(self):
        """REQ-o00062-O: Same rejection as HTTP, even with a fresh token."""
        graph, tools = _template_with_instance_server()
        current = node_version(graph.find_by_id("REQ-p80001"))

        result = tools["mutate_set_stereotype"](
            node_id="REQ-p80001", is_template=False, if_version=current
        )

        assert result["success"] is False
        assert result["blocked"] is True
        assert result["instance_count"] == 1
        assert result.get("code") != "version_conflict"
        assert node_version(graph.find_by_id("REQ-p80001")) == current

    def test_REQ_o00062_I_stale_version_is_reported_before_the_instance_block(self):
        """REQ-o00062-I: A stale token is a conflict, not a soft block --
        the caller must re-read before it can even consider forcing."""
        graph, tools = _template_with_instance_server()

        result = tools["mutate_set_stereotype"](
            node_id="REQ-p80001", is_template=False, if_version=BOGUS_VERSION
        )

        assert result["code"] == "version_conflict"
        assert result.get("blocked") is None

    def test_REQ_o00062_O_force_with_a_current_version_succeeds(self):
        """REQ-o00062-O: force=True still works, and only with a live token."""
        graph, tools = _template_with_instance_server()
        current = node_version(graph.find_by_id("REQ-p80001"))

        result = tools["mutate_set_stereotype"](
            node_id="REQ-p80001", is_template=False, if_version=current, force=True
        )

        assert result["success"] is True, result.get("error")
        assert result["version"] != current

    def test_REQ_o00062_O_force_does_not_bypass_the_version_guard(self):
        """REQ-o00062-O: force overrides the instance block, never the version
        precondition -- a blind forced write is still refused."""
        graph, tools = _template_with_instance_server()

        result = tools["mutate_set_stereotype"](
            node_id="REQ-p80001", is_template=False, if_version=BOGUS_VERSION, force=True
        )

        assert result["success"] is False
        assert result["code"] == "version_conflict"

    def test_REQ_o00062_O_toggle_on_is_never_blocked(self):
        """REQ-o00062-O: Toggle-ON is safe; only the version applies."""
        graph, tools = _template_with_instance_server()
        current = node_version(graph.find_by_id("REQ-p00044"))

        result = tools["mutate_set_stereotype"](
            node_id="REQ-p00044", is_template=True, if_version=current
        )

        assert result["success"] is True, result.get("error")
        assert result.get("blocked") is None
