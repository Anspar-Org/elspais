# Verifies: REQ-o00062-I, REQ-o00062-J, REQ-o00062-K, REQ-o00062-L, REQ-d00131-L
"""Optimistic-concurrency guard on the MCP content/metadata mutation tools.

Every content or metadata mutation tool takes a required ``if_version``
token. The token is the value of ``node_version()`` for the state the caller
believes it is modifying; a stale token is rejected rather than silently
overwriting a concurrent writer's work.

Assertion/remainder sub-nodes resolve to the version of the owning
REQUIREMENT (see ``node_version()``), so a caller editing an assertion
supplies the parent requirement's version.

These tests drive the registered MCP tool closures (not the ``_mutate_*``
helpers) because the guard lives in the tool wrapper, immediately after
``_guard_associate_write``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from elspais.graph import render

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
HHT_LIKE = FIXTURES_DIR / "hht-like"

BOGUS_VERSION = "0" * 16

# Every content/metadata tool in scope, with a call that would mutate the
# fixture if the guard let it through. ``REQ-d00003`` is used throughout so a
# leaked mutation is visible as a change to that requirement.
IN_SCOPE_TOOL_CALLS = [
    ("mutate_rename_node", {"old_id": "REQ-d00003", "new_id": "REQ-d00099"}),
    ("mutate_update_title", {"node_id": "REQ-d00003", "new_title": "Leaked Title"}),
    ("mutate_change_status", {"node_id": "REQ-d00003", "new_status": "Deprecated"}),
    ("mutate_delete_requirement", {"node_id": "REQ-d00003", "confirm": True}),
    (
        "mutate_update_assertion",
        {"assertion_id": "REQ-d00003-A", "new_text": "SHALL have leaked"},
    ),
    ("mutate_delete_assertion", {"assertion_id": "REQ-d00003-A", "confirm": True}),
    ("mutate_rename_assertion", {"old_id": "REQ-d00003-A", "new_label": "Z"}),
    ("mutate_update_remainder", {"node_id": "REQ-d00003:section:1", "text": "leaked"}),
    ("mutate_delete_remainder", {"node_id": "REQ-d00003:section:1", "confirm": True}),
]

CONFLICT_KEYS = {
    "success",
    "code",
    "node_id",
    "provided_version",
    "current_version",
    "current_state",
    "hint",
}


def node_version(node) -> str:
    """Resolve ``render.node_version`` at call time (see test_node_version)."""
    return render.node_version(node)


@pytest.fixture
def tools(canonical_federated_graph):
    """Map of MCP tool name -> raw closure, bound to the canonical graph.

    The server shares the canonical FederatedGraph, so mutations made through
    these tools land on ``canonical_graph`` and are undone by the
    ``mutable_graph`` fixture's teardown.
    """
    pytest.importorskip("mcp")
    from elspais.mcp.server import create_server

    server = create_server(canonical_federated_graph, working_dir=HHT_LIKE)
    return {name: tool.fn for name, tool in server._tool_manager._tools.items()}


# ─────────────────────────────────────────────────────────────────────────────
# Two-client lost update
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.incremental
class TestTwoClientLostUpdate:
    """Validates REQ-o00062-I, REQ-o00062-J:

    Two clients read the same requirement version. The first write succeeds;
    the second, still holding the pre-write version, is rejected and told what
    the state now is.
    """

    TARGET = "REQ-d00001"
    A_TITLE = "Authentication Module (client A)"
    B_TITLE = "Authentication Module (client B)"

    def test_REQ_o00062_I_client_a_write_with_shared_version_succeeds(self, mutable_graph, tools):
        """REQ-o00062-I: The first writer, holding a current version, succeeds."""
        shared = node_version(mutable_graph.find_by_id(self.TARGET))
        TestTwoClientLostUpdate.shared_version = shared

        result = tools["mutate_update_title"](
            node_id=self.TARGET, new_title=self.A_TITLE, if_version=shared
        )

        assert result["success"] is True
        assert mutable_graph.find_by_id(self.TARGET).get_label() == self.A_TITLE

    def test_REQ_o00062_I_stale_version_rejected(self, mutable_graph, tools):
        """REQ-o00062-I: Client B's now-stale version is rejected, not applied."""
        result = tools["mutate_update_title"](
            node_id=self.TARGET,
            new_title=self.B_TITLE,
            if_version=self.shared_version,
        )
        TestTwoClientLostUpdate.conflict = result

        assert result["success"] is False
        assert result["code"] == "version_conflict"
        # The lost update did not happen: A's title survives.
        assert mutable_graph.find_by_id(self.TARGET).get_label() == self.A_TITLE

    def test_REQ_o00062_J_conflict_reports_both_versions(self, mutable_graph, tools):
        """REQ-o00062-J: Rejection carries the provided and the live version."""
        conflict = self.conflict
        live = node_version(mutable_graph.find_by_id(self.TARGET))

        assert CONFLICT_KEYS <= set(conflict)
        assert conflict["node_id"] == self.TARGET
        assert conflict["provided_version"] == self.shared_version
        assert conflict["current_version"] == live
        assert conflict["current_version"] != conflict["provided_version"]
        assert isinstance(conflict["hint"], str) and conflict["hint"].strip()

    def test_REQ_o00062_J_current_state_reflects_the_winning_write(self):
        """REQ-o00062-J: current_state is post-A, so B reconciles without a re-read."""
        state = self.conflict["current_state"]

        assert state["id"] == self.TARGET
        # Not the pre-A title -- B sees what it must reconcile against.
        assert state["title"] == self.A_TITLE

    def test_REQ_o00062_J_current_state_uses_the_existing_serializer(
        self, canonical_federated_graph, tools
    ):
        """REQ-o00062-J: current_state is verbatim _get_requirement output."""
        from elspais.mcp.server import _get_requirement

        assert self.conflict["current_state"] == _get_requirement(
            canonical_federated_graph, self.TARGET
        )


# ─────────────────────────────────────────────────────────────────────────────
# Version reported on success, and threaded between mutations
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.incremental
class TestSuccessReportsVersion:
    """Validates REQ-o00062-K:

    A successful mutation reports the resulting version, and that token is
    directly usable as the ``if_version`` of the next mutation with no
    intervening read.
    """

    TARGET = "REQ-d00002"

    def test_REQ_o00062_K_success_returns_new_version(self, mutable_graph, tools):
        """REQ-o00062-K: Success carries the node's post-mutation version."""
        before = node_version(mutable_graph.find_by_id(self.TARGET))

        result = tools["mutate_update_title"](
            node_id=self.TARGET, new_title="Privacy Controls (v2)", if_version=before
        )

        assert result["success"] is True
        assert result["version"] != before
        assert result["version"] == node_version(mutable_graph.find_by_id(self.TARGET))
        TestSuccessReportsVersion.threaded = result["version"]

    def test_REQ_o00062_K_returned_token_threads_into_next_mutation(self, mutable_graph, tools):
        """REQ-o00062-K: The returned token is accepted with no re-read between."""
        result = tools["mutate_change_status"](
            node_id=self.TARGET, new_status="Draft", if_version=self.threaded
        )

        assert result["success"] is True
        assert mutable_graph.find_by_id(self.TARGET).status == "Draft"
        TestSuccessReportsVersion.threaded_2 = result["version"]

    def test_REQ_o00062_K_threading_survives_a_third_hop(self, mutable_graph, tools):
        """REQ-o00062-K: Chained mutations never need an intervening read."""
        result = tools["mutate_update_assertion"](
            assertion_id=f"{self.TARGET}-A",
            new_text="SHALL thread the version token",
            if_version=self.threaded_2,
        )

        assert result["success"] is True
        assert result["version"] == node_version(mutable_graph.find_by_id(self.TARGET))

    def test_REQ_o00062_I_the_consumed_token_is_now_stale(self, tools):
        """REQ-o00062-I: A token already spent by an earlier hop is rejected."""
        result = tools["mutate_change_status"](
            node_id=self.TARGET, new_status="Active", if_version=self.threaded
        )

        assert result["success"] is False
        assert result["code"] == "version_conflict"


# ─────────────────────────────────────────────────────────────────────────────
# Journey mutations report the RESULTING version, not the consumed token
# ─────────────────────────────────────────────────────────────────────────────


class TestJourneyMutationReportsMovedVersion:
    """Validates REQ-o00062-K, REQ-d00131-L:

    A journey renders from a cached body. A successful title edit must fold
    into that cache, so the reported ``version`` is the RESULTING token --
    returning the very ``if_version`` the caller supplied means the on-disk
    representation did not move and the edit will be silently dropped by the
    next save.
    """

    TARGET = "JNY-001"
    NEW_TITLE = "Login Flow (renamed)"

    def test_REQ_o00062_K_journey_title_update_returns_moved_version(self, mutable_graph, tools):
        """Validates REQ-o00062-K: success reports a version DIFFERENT from
        the consumed if_version, and the render shows the new title."""
        journey = mutable_graph.find_by_id(self.TARGET)
        before = node_version(journey)

        result = tools["mutate_update_title"](
            node_id=self.TARGET, new_title=self.NEW_TITLE, if_version=before
        )

        assert result["success"] is True
        # The reported token is the resulting one, not the stale input.
        assert result["version"] != before
        assert result["version"] == node_version(journey)
        # And the rendered (render_save-visible) body carries the edit.
        assert f"{self.TARGET}: {self.NEW_TITLE}" in render.render_node(journey)


# ─────────────────────────────────────────────────────────────────────────────
# Delete-assertion / delete-remainder report the parent's resulting version
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.incremental
class TestDeleteAssertionReportsParentVersion:
    """Validates REQ-o00062-K:

    ``mutate_delete_assertion`` is guarded by the owning requirement's token
    and changes that requirement's version, so its success result must carry
    the parent's resulting ``version`` -- threadable into the next mutation
    of the same requirement without a re-read.
    """

    PARENT = "REQ-o00002"

    def test_REQ_o00062_K_delete_assertion_returns_parent_resulting_version(
        self, mutable_graph, tools
    ):
        """Validates REQ-o00062-K: success carries the parent requirement's
        post-mutation version."""
        parent = mutable_graph.find_by_id(self.PARENT)
        before = node_version(parent)

        result = tools["mutate_delete_assertion"](
            assertion_id=f"{self.PARENT}-D", if_version=before, confirm=True
        )

        assert result["success"] is True
        assert "version" in result, "delete_assertion success carries no version"
        assert result["version"] == node_version(parent)
        assert result["version"] != before
        TestDeleteAssertionReportsParentVersion.threaded = result["version"]

    def test_REQ_o00062_K_returned_token_threads_into_next_parent_mutation(
        self, mutable_graph, tools
    ):
        """Validates REQ-o00062-K: the token is accepted with no re-read."""
        result = tools["mutate_change_status"](
            node_id=self.PARENT, new_status="Draft", if_version=self.threaded
        )

        assert result["success"] is True
        assert mutable_graph.find_by_id(self.PARENT).status == "Draft"


@pytest.mark.incremental
class TestDeleteRemainderReportsParentVersion:
    """Validates REQ-o00062-K:

    ``mutate_delete_remainder`` is guarded by the owning requirement's token
    and changes that requirement's version, so its success result must carry
    the parent's resulting ``version`` -- threadable into the next mutation
    of the same requirement without a re-read.
    """

    PARENT = "REQ-o00002"

    def test_REQ_o00062_K_delete_remainder_returns_parent_resulting_version(
        self, mutable_graph, tools
    ):
        """Validates REQ-o00062-K: success carries the parent requirement's
        post-mutation version."""
        parent = mutable_graph.find_by_id(self.PARENT)
        before = node_version(parent)

        result = tools["mutate_delete_remainder"](
            node_id=f"{self.PARENT}:section:1", if_version=before, confirm=True
        )

        assert result["success"] is True
        assert "version" in result, "delete_remainder success carries no version"
        assert result["version"] == node_version(parent)
        assert result["version"] != before
        TestDeleteRemainderReportsParentVersion.threaded = result["version"]

    def test_REQ_o00062_K_returned_token_threads_into_next_parent_mutation(
        self, mutable_graph, tools
    ):
        """Validates REQ-o00062-K: the token is accepted with no re-read."""
        result = tools["mutate_update_title"](
            node_id=self.PARENT,
            new_title="Backup Strategy (revised)",
            if_version=self.threaded,
        )

        assert result["success"] is True
        assert mutable_graph.find_by_id(self.PARENT).get_label() == "Backup Strategy (revised)"


# ─────────────────────────────────────────────────────────────────────────────
# Sub-nodes resolve to the owning requirement's version
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.incremental
class TestSubNodeVersionOwnership:
    """Validates REQ-o00062-I:

    ASSERTION and REMAINDER nodes have no version of their own -- they resolve
    to the owning REQUIREMENT's version, so their mutations are guarded with
    the parent requirement's token.
    """

    PARENT = "REQ-o00001"

    def test_REQ_o00062_I_assertion_update_takes_parent_requirement_version(
        self, mutable_graph, tools
    ):
        """REQ-o00062-I: Assertion edits are guarded by the parent's version."""
        parent_version = node_version(mutable_graph.find_by_id(self.PARENT))
        TestSubNodeVersionOwnership.stale = parent_version

        result = tools["mutate_update_assertion"](
            assertion_id=f"{self.PARENT}-A",
            new_text="SHALL deploy through the release pipeline",
            if_version=parent_version,
        )

        assert result["success"] is True
        assert (
            mutable_graph.find_by_id(f"{self.PARENT}-A").get_label()
            == "SHALL deploy through the release pipeline"
        )

    def test_REQ_o00062_I_assertion_update_rejects_stale_parent_version(self, mutable_graph, tools):
        """REQ-o00062-I: Editing an assertion after any sibling edit needs a fresh token."""
        result = tools["mutate_update_assertion"](
            assertion_id=f"{self.PARENT}-B",
            new_text="SHALL never land",
            if_version=self.stale,
        )

        assert result["success"] is False
        assert result["code"] == "version_conflict"
        assert result["current_version"] == node_version(mutable_graph.find_by_id(self.PARENT))
        assert "SHALL never land" not in (
            mutable_graph.find_by_id(f"{self.PARENT}-B").get_label() or ""
        )

    def test_REQ_o00062_I_remainder_update_takes_parent_requirement_version(
        self, mutable_graph, tools
    ):
        """REQ-o00062-I: Remainder-section edits are guarded by the parent's version."""
        parent_version = node_version(mutable_graph.find_by_id(self.PARENT))

        result = tools["mutate_update_remainder"](
            node_id=f"{self.PARENT}:section:1",
            text="Deployment rationale, revised.",
            if_version=parent_version,
        )

        assert result["success"] is True
        assert result["version"] == node_version(mutable_graph.find_by_id(self.PARENT))
        assert result["version"] != parent_version


# ─────────────────────────────────────────────────────────────────────────────
# Missing node vs. version mismatch
# ─────────────────────────────────────────────────────────────────────────────


class TestMissingNodeIsDistinct:
    """Validates REQ-o00062-L:

    Naming a node that does not exist is not retryable, so it is reported
    under its own code rather than as a version mismatch.
    """

    def test_REQ_o00062_L_missing_node_reports_node_not_found(self, tools):
        """REQ-o00062-L: An absent node id yields node_not_found."""
        result = tools["mutate_update_title"](
            node_id="REQ-d99999", new_title="Ghost", if_version=BOGUS_VERSION
        )

        assert result["success"] is False
        assert result["code"] == "node_not_found"

    def test_REQ_o00062_L_missing_node_is_not_a_version_conflict(self, tools):
        """REQ-o00062-L: node_not_found is never conflated with version_conflict."""
        result = tools["mutate_change_status"](
            node_id="REQ-d99999", new_status="Draft", if_version=BOGUS_VERSION
        )

        assert result["code"] != "version_conflict"
        assert result["code"] == "node_not_found"

    def test_REQ_o00062_L_present_node_with_bad_version_is_a_conflict(self, canonical_graph, tools):
        """REQ-o00062-L: The same call against a live node yields version_conflict."""
        result = tools["mutate_change_status"](
            node_id="REQ-d00003", new_status="Draft", if_version=BOGUS_VERSION
        )

        assert result["code"] == "version_conflict"
        assert canonical_graph.find_by_id("REQ-d00003").status != "Draft"


# ─────────────────────────────────────────────────────────────────────────────
# Every in-scope tool is guarded
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("tool_name", "kwargs"),
    IN_SCOPE_TOOL_CALLS,
    ids=[call[0] for call in IN_SCOPE_TOOL_CALLS],
)
class TestEveryInScopeToolGuards:
    """Validates REQ-o00062-I, REQ-o00062-J:

    Each content/metadata mutation tool takes a required ``if_version`` and
    rejects a mismatched one before touching the graph.
    """

    def test_REQ_o00062_I_if_version_is_a_required_parameter(self, tools, tool_name, kwargs):
        """REQ-o00062-I: if_version has no default -- callers cannot omit it."""
        import inspect

        params = inspect.signature(tools[tool_name]).parameters

        assert "if_version" in params, f"{tool_name} does not accept if_version"
        assert params["if_version"].default is inspect.Parameter.empty

    def test_REQ_o00062_I_stale_version_rejected_and_graph_untouched(
        self, canonical_graph, tools, tool_name, kwargs
    ):
        """REQ-o00062-I: A bogus version blocks the mutation for every tool."""
        before = node_version(canonical_graph.find_by_id("REQ-d00003"))

        result = tools[tool_name](if_version=BOGUS_VERSION, **kwargs)

        assert result["success"] is False, f"{tool_name} applied a stale-version mutation"
        assert result["code"] == "version_conflict"
        assert canonical_graph.find_by_id("REQ-d00003") is not None
        assert node_version(canonical_graph.find_by_id("REQ-d00003")) == before

    def test_REQ_o00062_J_conflict_shape_is_uniform(
        self, canonical_graph, tools, tool_name, kwargs
    ):
        """REQ-o00062-J: Every tool reports a rejection with the same keys."""
        result = tools[tool_name](if_version=BOGUS_VERSION, **kwargs)

        assert CONFLICT_KEYS <= set(result), f"{tool_name} conflict is missing keys"
        assert result["provided_version"] == BOGUS_VERSION
        assert result["node_id"] == next(iter(kwargs.values()))
        assert result["current_version"] != BOGUS_VERSION
        assert isinstance(result["current_state"], dict)
        assert "error" not in result["current_state"]
