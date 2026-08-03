# Verifies: REQ-o00062-M, REQ-o00062-I, REQ-o00062-J, REQ-o00062-K, REQ-o00062-L, REQ-o00062-O
"""Optimistic-concurrency guard on the relationship, creation and file mutations.

``test_mcp_version_guard.py`` covers the content/metadata tools, whose guard
target is obvious: the node whose text the caller is rewriting. The tools here
are the ones where it is not obvious, and REQ-o00062-M settles it:

* A relationship mutation is guarded on the **referring node alone**. Only the
  referring node's rendered form carries the reference, so a token for the
  target would reject writes that cannot clobber anything.
* A creation is guarded on the **parent** -- the created node has no prior
  version, and the parent is what a concurrent writer could have moved.
* A mutation that relocates content between files is guarded on the content
  node **and** on both the origin and destination files, because all three
  change.

Three mutations reach the spec files directly rather than the in-memory graph
(``apply_link``, ``change_reference_type``, ``move_requirement``). They rewrite
files and rebuild, so a blind write there loses a concurrent edit exactly as an
in-memory one does; they are guarded on the node whose rendered form the write
changes and are exercised against a throwaway copy of the fixture.

Empirical note for the reader: ``TraceGraph.add_edge(source_id, target_id)``
stores the edge as ``target -> source`` (the target is the graph parent). Both
ends therefore see a version change -- the source because its rendered
``**Implements**:`` line is derived from its incoming edges, the target because
its outgoing traceability edges feed its version digest. REQ-o00062-M picks the
source regardless: it is the node whose file text changes.

These tests drive the registered MCP tool closures, not the ``_mutate_*``
helpers, because the guard lives in the tool wrapper.
"""

from __future__ import annotations

import inspect
import shutil
from pathlib import Path

import pytest

from elspais.graph import render

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
HHT_LIKE = FIXTURES_DIR / "hht-like"

BOGUS_VERSION = "0" * 16

CONFLICT_KEYS = {
    "success",
    "code",
    "node_id",
    "provided_version",
    "current_version",
    "current_state",
    "hint",
}

# The history-level tools are guarded by the mutation log, not by a node
# version -- they take no node id at all. Everything else that mutates must
# accept a version token (see TestEveryMutationToolIsGuarded).
# ``restore_from_safety_branch`` belongs here: it overwrites every spec file
# from a git branch and rebuilds, discarding all pending work at once.
HISTORY_TOOLS = {
    "undo_last_mutation",
    "undo_to_mutation",
    "save_mutations",
    "refresh_graph",
    "restore_from_safety_branch",
}

# MCP-only mutations that write spec files directly. Named here because they
# do not carry the ``mutate_`` prefix but are mutations all the same.
DISK_BACKED_TOOLS = {"apply_link", "change_reference_type", "move_requirement"}

# The only mutation tool whose ``if_version`` may default: a parentless
# creation has no prior state a concurrent writer could clobber, so nothing
# exists to guard (REQ-o00062-I names this as the sole exemption). Anything
# else joining this set is a lost-update hole, not a design decision.
VERSION_OPTIONAL_TOOLS = {"mutate_add_requirement"}

# Mutation tools whose stale-token/behavioral conflict coverage lives in a
# dedicated (non-parametrized) test class rather than a parametrization list,
# because their guard shape is unique: the parent-optional create, the
# three-token move, and the FILE rename. Each name here must have such a
# class; see TestAddRequirementGuardsTheParentOnlyWhenThereIsOne,
# TestMoveNodeToFileGuardsAllThreeAffectedNodes, TestRenameFileGuardsTheFile.
DEDICATED_CLASS_TOOLS = {
    "mutate_add_requirement",
    "mutate_move_node_to_file",
    "mutate_rename_file",
}


def node_version(node) -> str:
    """Resolve ``render.node_version`` at call time."""
    return render.node_version(node)


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

    Undo MUST run on the same object the ``tools`` fixture mutates -- the
    FederatedGraph. Undoing on the inner TraceGraph instead bypasses
    ``_federated_log.pop()`` and ``_rebuild_ownership()``, which leaves the
    federated index inconsistent and silently contaminates later tests.
    """
    before = len(canonical_federated_graph.mutation_log)
    yield canonical_federated_graph
    while len(canonical_federated_graph.mutation_log) > before:
        if canonical_federated_graph.undo_last() is None:
            break


@pytest.fixture(scope="class")
def chain(canonical_federated_graph):
    """``rollback`` for an incremental class: undo the whole chain at teardown.

    Same federated-undo requirement as ``rollback``; the wider scope lets a
    ``@pytest.mark.incremental`` class thread version tokens across steps.
    """
    before = len(canonical_federated_graph.mutation_log)
    yield canonical_federated_graph
    while len(canonical_federated_graph.mutation_log) > before:
        if canonical_federated_graph.undo_last() is None:
            break


# ─────────────────────────────────────────────────────────────────────────────
# Edge mutations: guarded on the referring node (the source)
# ─────────────────────────────────────────────────────────────────────────────

# (tool, referring node whose version guards the call, kwargs that would mutate
# the fixture if the guard let them through). ``mutate_fix_broken_reference``
# names a target that does not exist -- the guard must fire before that is
# discovered.
EDGE_TOOL_CALLS = [
    (
        "mutate_add_edge",
        "REQ-d00003",
        {
            "source_id": "REQ-d00003",
            "target_id": "REQ-p00001",
            "edge_kind": "IMPLEMENTS",
        },
    ),
    (
        "mutate_change_edge_kind",
        "REQ-d00003",
        {"source_id": "REQ-d00003", "target_id": "REQ-p00003", "new_kind": "REFINES"},
    ),
    (
        "mutate_change_edge_targets",
        "REQ-d00003",
        {
            "source_id": "REQ-d00003",
            "target_id": "REQ-p00003",
            "assertion_targets": ["A", "B"],
        },
    ),
    (
        "mutate_delete_edge",
        "REQ-d00001",
        {"source_id": "REQ-d00001", "target_id": "REQ-o00001", "confirm": True},
    ),
    (
        "mutate_fix_broken_reference",
        "REQ-d00003",
        {
            "source_id": "REQ-d00003",
            "old_target_id": "REQ-p09999",
            "new_target_id": "REQ-p00001",
        },
    ),
]

EDGE_IDS = [call[0] for call in EDGE_TOOL_CALLS]


@pytest.mark.parametrize(
    ("tool_name", "referring_id", "kwargs"),
    EDGE_TOOL_CALLS,
    ids=EDGE_IDS,
)
class TestEdgeToolsGuardTheReferringNode:
    """Validates REQ-o00062-M, REQ-o00062-I, REQ-o00062-J, REQ-o00062-L:

    Each edge mutation takes a required ``if_version`` naming the referring
    node -- the one whose ``**Implements**:``/``**Refines**:`` line the write
    rewrites -- and refuses a stale token before touching the graph.
    """

    def test_REQ_o00062_M_if_version_is_a_required_parameter(
        self, tools, tool_name, referring_id, kwargs
    ):
        """REQ-o00062-M: if_version has no default -- callers cannot omit it."""
        params = inspect.signature(tools[tool_name]).parameters

        assert "if_version" in params, f"{tool_name} does not accept if_version"
        assert params["if_version"].default is inspect.Parameter.empty

    def test_REQ_o00062_M_omitting_if_version_is_a_type_error(
        self, rollback, tools, tool_name, referring_id, kwargs
    ):
        """REQ-o00062-M: A blind relationship write cannot reach the graph.

        ``rollback`` is held so that a build in which the call *does* get
        through cannot leave the session graph edited for later tests.
        """
        with pytest.raises(TypeError):
            tools[tool_name](**kwargs)

    def test_REQ_o00062_I_stale_version_rejected_and_graph_untouched(
        self, canonical_graph, tools, tool_name, referring_id, kwargs
    ):
        """REQ-o00062-I: A bogus token blocks the edge mutation for every tool."""
        before = node_version(canonical_graph.find_by_id(referring_id))

        result = tools[tool_name](if_version=BOGUS_VERSION, **kwargs)

        assert result["success"] is False, f"{tool_name} applied a stale-version mutation"
        assert result["code"] == "version_conflict"
        assert node_version(canonical_graph.find_by_id(referring_id)) == before

    def test_REQ_o00062_M_conflict_names_the_referring_node(
        self, tools, tool_name, referring_id, kwargs
    ):
        """REQ-o00062-M: The rejection points at the source, not the target."""
        result = tools[tool_name](if_version=BOGUS_VERSION, **kwargs)

        assert CONFLICT_KEYS <= set(result), f"{tool_name} conflict is missing keys"
        assert result["node_id"] == referring_id
        assert result["node_id"] != kwargs.get("target_id", result["node_id"] + "!")
        assert result["provided_version"] == BOGUS_VERSION
        assert result["current_version"] != BOGUS_VERSION
        assert isinstance(result["current_state"], dict)
        assert "error" not in result["current_state"]

    def test_REQ_o00062_L_missing_source_reports_node_not_found(
        self, tools, tool_name, referring_id, kwargs
    ):
        """REQ-o00062-L: An absent referring node is not a version conflict."""
        absent = {**kwargs, "source_id": "REQ-d99999"}

        result = tools[tool_name](if_version=BOGUS_VERSION, **absent)

        assert result["success"] is False
        assert result["code"] == "node_not_found"


@pytest.mark.incremental
class TestEdgeChainThreadsTheSourcesVersion:
    """Validates REQ-o00062-M, REQ-o00062-K, REQ-o00062-I:

    A caller adding, retyping, re-targeting and finally removing a reference
    threads the source's version through the whole chain, never re-reading. A
    concurrent edit to the *target* does not invalidate that token, which is
    the whole point of guarding the referring node alone.
    """

    SOURCE = "REQ-d00003"
    TARGET = "REQ-p00001"

    def test_REQ_o00062_M_editing_the_target_does_not_invalidate_the_source_token(
        self, chain, tools
    ):
        """REQ-o00062-M: The target moved under the caller; the write still
        lands, because the target's text is not what this write changes."""
        source_version = node_version(chain.find_by_id(self.SOURCE))
        target_version = node_version(chain.find_by_id(self.TARGET))
        tools["mutate_update_title"](
            node_id=self.TARGET,
            new_title="User Authentication (retitled concurrently)",
            if_version=target_version,
        )
        assert node_version(chain.find_by_id(self.TARGET)) != target_version
        assert node_version(chain.find_by_id(self.SOURCE)) == source_version

        result = tools["mutate_add_edge"](
            source_id=self.SOURCE,
            target_id=self.TARGET,
            edge_kind="IMPLEMENTS",
            if_version=source_version,
        )

        assert result["success"] is True, result.get("error")
        TestEdgeChainThreadsTheSourcesVersion.spent = source_version
        TestEdgeChainThreadsTheSourcesVersion.threaded = result["version"]

    def test_REQ_o00062_K_add_edge_returns_the_sources_new_version(self, chain):
        """REQ-o00062-K: The returned token is the source's post-write version."""
        assert self.threaded == node_version(chain.find_by_id(self.SOURCE))
        assert self.threaded != self.spent

    def test_REQ_o00062_I_the_spent_token_no_longer_admits_a_retype(self, chain, tools):
        """REQ-o00062-I: The pre-add token is stale for the next edge write."""
        result = tools["mutate_change_edge_kind"](
            source_id=self.SOURCE,
            target_id=self.TARGET,
            new_kind="REFINES",
            if_version=self.spent,
        )

        assert result["success"] is False
        assert result["code"] == "version_conflict"
        assert result["node_id"] == self.SOURCE
        assert "REQ-p00001" in render.render_node(chain.find_by_id(self.SOURCE))

    def test_REQ_o00062_K_threaded_token_admits_the_retype(self, chain, tools):
        """REQ-o00062-K: The token from the add is accepted with no re-read."""
        result = tools["mutate_change_edge_kind"](
            source_id=self.SOURCE,
            target_id=self.TARGET,
            new_kind="REFINES",
            if_version=self.threaded,
        )

        assert result["success"] is True, result.get("error")
        assert result["version"] == node_version(chain.find_by_id(self.SOURCE))
        TestEdgeChainThreadsTheSourcesVersion.threaded = result["version"]

    def test_REQ_o00062_K_threaded_token_admits_retargeting(self, chain, tools):
        """REQ-o00062-K: Assertion re-targeting continues the same chain."""
        result = tools["mutate_change_edge_targets"](
            source_id=self.SOURCE,
            target_id=self.TARGET,
            assertion_targets=["A"],
            if_version=self.threaded,
        )

        assert result["success"] is True, result.get("error")
        assert "REQ-p00001-A" in render.render_node(chain.find_by_id(self.SOURCE))
        TestEdgeChainThreadsTheSourcesVersion.threaded = result["version"]

    def test_REQ_o00062_K_threaded_token_admits_the_delete(self, chain, tools):
        """REQ-o00062-K: Removing the reference closes the chain without a read."""
        result = tools["mutate_delete_edge"](
            source_id=self.SOURCE,
            target_id=self.TARGET,
            confirm=True,
            if_version=self.threaded,
        )

        assert result["success"] is True, result.get("error")
        assert "REQ-p00001" not in render.render_node(chain.find_by_id(self.SOURCE))


@pytest.mark.incremental
class TestFixBrokenReferenceGuardsTheSource:
    """Validates REQ-o00062-M, REQ-o00062-I, REQ-o00062-K:

    Repairing a dangling reference rewrites the referring requirement's
    metadata line, so it is guarded -- and guarded on that requirement, not on
    the replacement target the caller is pointing it at.
    """

    SOURCE = "REQ-d00003"
    DANGLING = "REQ-p09999"
    REPLACEMENT = "REQ-p00002"

    def test_REQ_o00062_M_dangling_reference_is_created_to_repair(self, chain, tools):
        """REQ-o00062-M: Setup -- a reference to a missing node wires no edge,
        so the source's rendered form (and version) is unchanged by it."""
        before = node_version(chain.find_by_id(self.SOURCE))

        result = tools["mutate_add_edge"](
            source_id=self.SOURCE,
            target_id=self.DANGLING,
            edge_kind="IMPLEMENTS",
            if_version=before,
        )

        assert result["success"] is True, result.get("error")
        TestFixBrokenReferenceGuardsTheSource.spent = node_version(chain.find_by_id(self.SOURCE))

    def test_REQ_o00062_M_repair_accepts_the_sources_current_version(self, chain, tools):
        """REQ-o00062-M: The source's token admits the repair."""
        result = tools["mutate_fix_broken_reference"](
            source_id=self.SOURCE,
            old_target_id=self.DANGLING,
            new_target_id=self.REPLACEMENT,
            if_version=self.spent,
        )

        assert result["success"] is True, result.get("error")
        assert self.REPLACEMENT in render.render_node(chain.find_by_id(self.SOURCE))
        TestFixBrokenReferenceGuardsTheSource.threaded = result["version"]

    def test_REQ_o00062_K_repair_returns_the_sources_new_version(self, chain):
        """REQ-o00062-K: The repair reports the version it produced."""
        assert self.threaded == node_version(chain.find_by_id(self.SOURCE))
        assert self.threaded != self.spent

    def test_REQ_o00062_I_the_pre_repair_token_is_now_stale(self, tools):
        """REQ-o00062-I: A second repairer holding the old token is refused."""
        result = tools["mutate_fix_broken_reference"](
            source_id=self.SOURCE,
            old_target_id=self.DANGLING,
            new_target_id="REQ-p00003",
            if_version=self.spent,
        )

        assert result["success"] is False
        assert result["code"] == "version_conflict"
        assert result["node_id"] == self.SOURCE


# ─────────────────────────────────────────────────────────────────────────────
# Creation: guarded on the parent, because the new node has no prior version
# ─────────────────────────────────────────────────────────────────────────────

CREATION_TOOL_CALLS = [
    (
        "mutate_add_assertion",
        {"req_id": "REQ-d00003", "label": "Z", "text": "The module SHALL have leaked."},
    ),
    (
        "mutate_add_remainder",
        {"req_id": "REQ-d00003", "heading": "Leaked", "text": "leaked prose"},
    ),
]

CREATION_IDS = [call[0] for call in CREATION_TOOL_CALLS]


@pytest.mark.parametrize(("tool_name", "kwargs"), CREATION_TOOL_CALLS, ids=CREATION_IDS)
class TestCreationToolsGuardTheOwningRequirement:
    """Validates REQ-o00062-M, REQ-o00062-I, REQ-o00062-J, REQ-o00062-L:

    An assertion or a remainder section has no version of its own before it
    exists, so its creation states the version of the requirement it is being
    appended to -- the node whose rendered block actually grows.
    """

    def test_REQ_o00062_M_if_version_is_a_required_parameter(self, tools, tool_name, kwargs):
        """REQ-o00062-M: if_version has no default -- callers cannot omit it."""
        params = inspect.signature(tools[tool_name]).parameters

        assert "if_version" in params, f"{tool_name} does not accept if_version"
        assert params["if_version"].default is inspect.Parameter.empty

    def test_REQ_o00062_M_omitting_if_version_is_a_type_error(
        self, rollback, tools, tool_name, kwargs
    ):
        """REQ-o00062-M: A blind append cannot reach the graph.

        ``rollback`` is held so that a build in which the call *does* get
        through cannot leave the session graph edited for later tests.
        """
        with pytest.raises(TypeError):
            tools[tool_name](**kwargs)

    def test_REQ_o00062_I_stale_version_rejected_and_nothing_appended(
        self, canonical_graph, tools, tool_name, kwargs
    ):
        """REQ-o00062-I: A bogus parent token blocks the creation."""
        before = node_version(canonical_graph.find_by_id("REQ-d00003"))

        result = tools[tool_name](if_version=BOGUS_VERSION, **kwargs)

        assert result["success"] is False, f"{tool_name} applied a stale-version creation"
        assert result["code"] == "version_conflict"
        assert node_version(canonical_graph.find_by_id("REQ-d00003")) == before

    def test_REQ_o00062_J_conflict_names_the_parent_requirement(self, tools, tool_name, kwargs):
        """REQ-o00062-J: The rejection identifies the requirement to re-read."""
        result = tools[tool_name](if_version=BOGUS_VERSION, **kwargs)

        assert CONFLICT_KEYS <= set(result), f"{tool_name} conflict is missing keys"
        assert result["node_id"] == "REQ-d00003"
        assert result["provided_version"] == BOGUS_VERSION
        assert isinstance(result["current_state"], dict)
        assert "error" not in result["current_state"]

    def test_REQ_o00062_L_missing_parent_reports_node_not_found(self, tools, tool_name, kwargs):
        """REQ-o00062-L: Appending to an absent requirement is not retryable."""
        result = tools[tool_name](if_version=BOGUS_VERSION, **{**kwargs, "req_id": "REQ-d99999"})

        assert result["success"] is False
        assert result["code"] == "node_not_found"


@pytest.mark.incremental
class TestAddAssertionThreadsTheRequirementVersion:
    """Validates REQ-o00062-M, REQ-o00062-K, REQ-o00062-I:

    Two agents appending assertions to one requirement cannot both write
    blind: the first append moves the requirement's version and the second,
    holding the pre-append token, is refused.
    """

    PARENT = "REQ-d00002"

    def test_REQ_o00062_M_parent_version_admits_the_first_assertion(self, chain, tools):
        """REQ-o00062-M: The owning requirement's token is what is accepted."""
        before = node_version(chain.find_by_id(self.PARENT))
        TestAddAssertionThreadsTheRequirementVersion.spent = before

        result = tools["mutate_add_assertion"](
            req_id=self.PARENT,
            label="E",
            text="The module SHALL rotate encryption keys annually.",
            if_version=before,
        )

        assert result["success"] is True, result.get("error")
        assert chain.find_by_id(f"{self.PARENT}-E") is not None
        TestAddAssertionThreadsTheRequirementVersion.threaded = result["version"]

    def test_REQ_o00062_K_success_returns_the_requirements_new_version(self, chain):
        """REQ-o00062-K: The token handed back is the parent's live version."""
        assert self.threaded == node_version(chain.find_by_id(self.PARENT))
        assert self.threaded != self.spent

    def test_REQ_o00062_I_second_writer_with_the_spent_token_is_rejected(self, chain, tools):
        """REQ-o00062-I: The concurrent appender must re-read first."""
        result = tools["mutate_add_assertion"](
            req_id=self.PARENT,
            label="F",
            text="The module SHALL never land.",
            if_version=self.spent,
        )

        assert result["success"] is False
        assert result["code"] == "version_conflict"
        assert chain.find_by_id(f"{self.PARENT}-F") is None

    def test_REQ_o00062_K_threaded_token_admits_the_second_assertion(self, chain, tools):
        """REQ-o00062-K: Reconciled via the returned token, the append lands."""
        result = tools["mutate_add_assertion"](
            req_id=self.PARENT,
            label="F",
            text="The module SHALL purge exports after 30 days.",
            if_version=self.threaded,
        )

        assert result["success"] is True, result.get("error")
        assert chain.find_by_id(f"{self.PARENT}-F") is not None


@pytest.mark.incremental
class TestAddRequirementGuardsTheParentOnlyWhenThereIsOne:
    """Validates REQ-o00062-M, REQ-o00062-I, REQ-o00062-K:

    ``mutate_add_requirement`` links the new requirement under ``parent_id``
    when one is given, which changes the parent -- so the parent's version is
    required. With no parent there is nothing a concurrent writer could have
    clobbered, so no token is demanded; requiring one there would block a
    legitimate blind create.
    """

    PARENT = "REQ-o00002"

    def test_REQ_o00062_M_if_version_is_optional_in_the_signature(self, tools):
        """REQ-o00062-M: Unlike every other guarded tool, this one defaults --
        the parentless path has nothing to guard."""
        params = inspect.signature(tools["mutate_add_requirement"]).parameters

        assert "if_version" in params
        assert params["if_version"].default is None

    def test_REQ_o00062_M_parentless_creation_needs_no_version(self, chain, tools):
        """REQ-o00062-M: A root-level create succeeds with no token at all."""
        result = tools["mutate_add_requirement"](
            req_id="REQ-d00901", title="Rootless Draft", level="DEV"
        )

        assert result["success"] is True, result.get("error")
        assert chain.find_by_id("REQ-d00901") is not None

    def test_REQ_o00062_M_parented_creation_rejects_a_stale_parent_token(self, chain, tools):
        """REQ-o00062-M: Supply a parent and the parent's version is enforced."""
        result = tools["mutate_add_requirement"](
            req_id="REQ-d00902",
            title="Never Lands",
            level="DEV",
            parent_id=self.PARENT,
            edge_kind="IMPLEMENTS",
            if_version=BOGUS_VERSION,
        )

        assert result["success"] is False
        assert result["code"] == "version_conflict"
        assert result["node_id"] == self.PARENT
        assert chain.find_by_id("REQ-d00902") is None

    def test_REQ_o00062_M_parented_creation_accepts_the_parents_version(self, chain, tools):
        """REQ-o00062-M: The parent's live token admits the create."""
        parent_version = node_version(chain.find_by_id(self.PARENT))
        TestAddRequirementGuardsTheParentOnlyWhenThereIsOne.spent = parent_version

        result = tools["mutate_add_requirement"](
            req_id="REQ-d00903",
            title="Session Store",
            level="DEV",
            parent_id=self.PARENT,
            edge_kind="IMPLEMENTS",
            if_version=parent_version,
        )

        assert result["success"] is True, result.get("error")
        assert chain.find_by_id("REQ-d00903") is not None
        TestAddRequirementGuardsTheParentOnlyWhenThereIsOne.threaded = result["version"]

    def test_REQ_o00062_K_success_returns_the_parents_new_version(self, chain):
        """REQ-o00062-K: The new node has no prior version, so the token handed
        back is the parent's -- the thing the next sibling create must state."""
        assert self.threaded == node_version(chain.find_by_id(self.PARENT))
        assert self.threaded != self.spent

    def test_REQ_o00062_I_the_spent_parent_token_is_rejected(self, chain, tools):
        """REQ-o00062-I: A second create under the same parent must re-read."""
        result = tools["mutate_add_requirement"](
            req_id="REQ-d00904",
            title="Also Never Lands",
            level="DEV",
            parent_id=self.PARENT,
            edge_kind="IMPLEMENTS",
            if_version=self.spent,
        )

        assert result["success"] is False
        assert result["code"] == "version_conflict"
        assert chain.find_by_id("REQ-d00904") is None

    def test_REQ_o00062_L_missing_parent_reports_node_not_found(self, tools):
        """REQ-o00062-L: Naming a parent that does not exist is not retryable."""
        result = tools["mutate_add_requirement"](
            req_id="REQ-d00905",
            title="Orphan",
            level="DEV",
            parent_id="REQ-o99999",
            edge_kind="IMPLEMENTS",
            if_version=BOGUS_VERSION,
        )

        assert result["success"] is False
        assert result["code"] == "node_not_found"


class TestAddRequirementIntoChosenFileParity:
    """Validates REQ-o00062-O, REQ-o00062-M:

    HTTP's ``/api/mutate/requirement/add`` accepts ``file_id`` -- placement of
    the new requirement into a chosen FILE, guarded on that FILE's version
    (the node whose rendered composition gains the new child). Capability
    parity (REQ-o00062-O) requires the MCP tool to offer the same placement
    under the same guard.
    """

    FILE = "file:spec/dev-impl.md"

    def test_REQ_o00062_O_add_requirement_places_into_the_named_file(self, rollback, tools):
        """REQ-o00062-O: ``file_id`` plus the FILE's live token lands the
        create with the new requirement contained by that file."""
        file_node = rollback.find_by_id(self.FILE)

        result = tools["mutate_add_requirement"](
            req_id="REQ-d00910",
            title="Placed Draft",
            level="DEV",
            file_id=self.FILE,
            if_version=node_version(file_node),
        )

        assert result["success"] is True, result.get("error")
        created = rollback.find_by_id("REQ-d00910")
        assert created is not None
        assert created.file_node() is not None
        assert created.file_node().id == self.FILE
        assert "REQ-d00910" in render.render_file(rollback.find_by_id(self.FILE))

    def test_REQ_o00062_M_stale_file_token_rejects_the_placement(self, rollback, tools):
        """REQ-o00062-M: File placement is guarded on the destination FILE --
        a stale FILE token is refused, and the conflict names the file."""
        result = tools["mutate_add_requirement"](
            req_id="REQ-d00911",
            title="Never Lands",
            level="DEV",
            file_id=self.FILE,
            if_version=BOGUS_VERSION,
        )

        assert result["success"] is False
        assert result["code"] == "version_conflict"
        assert result["node_id"] == self.FILE
        assert rollback.find_by_id("REQ-d00911") is None


# ─────────────────────────────────────────────────────────────────────────────
# File mutations
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.incremental
class TestRenameFileGuardsTheFile:
    """Validates REQ-o00062-M, REQ-o00062-I, REQ-o00062-K, REQ-o00062-L:

    Renaming a FILE changes that FILE's rendered identity and nothing else's,
    so the FILE is the single guarded node.
    """

    FILE = "file:spec/glossary.md"
    RENAMED = "file:spec/glossary-renamed.md"

    def test_REQ_o00062_M_if_version_is_a_required_parameter(self, tools):
        """REQ-o00062-M: if_version has no default -- callers cannot omit it."""
        params = inspect.signature(tools["mutate_rename_file"]).parameters

        assert "if_version" in params
        assert params["if_version"].default is inspect.Parameter.empty

    def test_REQ_o00062_I_stale_version_rejected_and_the_file_keeps_its_id(self, chain, tools):
        """REQ-o00062-I: A bogus token leaves the FILE node untouched."""
        result = tools["mutate_rename_file"](
            file_id=self.FILE, new_relative_path="spec/never-lands.md", if_version=BOGUS_VERSION
        )

        assert result["success"] is False
        assert result["code"] == "version_conflict"
        assert result["node_id"] == self.FILE
        assert chain.find_by_id(self.FILE) is not None
        assert chain.find_by_id("file:spec/never-lands.md") is None

    def test_REQ_o00062_L_missing_file_reports_node_not_found(self, tools):
        """REQ-o00062-L: An absent FILE id is not a version conflict."""
        result = tools["mutate_rename_file"](
            file_id="file:spec/absent.md", new_relative_path="spec/x.md", if_version=BOGUS_VERSION
        )

        assert result["success"] is False
        assert result["code"] == "node_not_found"

    def test_REQ_o00062_M_current_version_admits_the_rename(self, chain, tools):
        """REQ-o00062-M: The FILE's live token is what the rename requires."""
        current = node_version(chain.find_by_id(self.FILE))

        result = tools["mutate_rename_file"](
            file_id=self.FILE, new_relative_path="spec/glossary-renamed.md", if_version=current
        )

        assert result["success"] is True, result.get("error")
        assert chain.find_by_id(self.RENAMED) is not None
        assert chain.find_by_id(self.FILE) is None
        TestRenameFileGuardsTheFile.returned = result["version"]

    def test_REQ_o00062_K_success_returns_the_renamed_files_version(self, chain):
        """REQ-o00062-K: The token handed back tracks the node under its new id."""
        assert self.returned == node_version(chain.find_by_id(self.RENAMED))


# (which token is stale, the node id the conflict must name)
MOVE_TOKENS = [
    ("if_version", "REQ-d00003"),
    ("if_source_file_version", "file:spec/dev-impl.md"),
    ("if_target_version", "file:spec/ops-deploy.md"),
]


class TestMoveNodeToFileGuardsAllThreeAffectedNodes:
    """Validates REQ-o00062-M, REQ-o00062-I, REQ-o00062-J, REQ-o00062-O:

    A move changes three things: the node's home, the origin file's contents
    and the destination file's composition (including where the arrival lands
    in render order relative to anything that arrived concurrently). All three
    are stated, and any one of them being stale is enough to refuse.

    A destination that does not exist is CREATED by the move (REQ-o00062-M/O
    parity with the HTTP route), so the rejection tests here must use targets
    that fail spec-path validation -- a spec-valid absent target against this
    session-scoped server would write a real file into the checked-in fixture.
    The genuine create-success path is covered by
    TestMoveNodeCreatesMissingDestinationParity on a throwaway copy.
    """

    NODE = "REQ-d00003"
    ORIGIN = "file:spec/dev-impl.md"
    DESTINATION = "file:spec/ops-deploy.md"

    @staticmethod
    def _live_tokens(graph):
        return {
            "if_version": node_version(graph.find_by_id("REQ-d00003")),
            "if_source_file_version": node_version(graph.find_by_id("file:spec/dev-impl.md")),
            "if_target_version": node_version(graph.find_by_id("file:spec/ops-deploy.md")),
        }

    def test_REQ_o00062_M_all_three_tokens_are_required_parameters(self, tools):
        """REQ-o00062-M: The signature demands a token per affected node."""
        params = inspect.signature(tools["mutate_move_node_to_file"]).parameters

        for name, _ in MOVE_TOKENS:
            assert name in params, f"mutate_move_node_to_file does not accept {name}"
            assert params[name].default is inspect.Parameter.empty, f"{name} must be required"

    @pytest.mark.parametrize(
        ("stale_token", "expected_node_id"), MOVE_TOKENS, ids=[t[0] for t in MOVE_TOKENS]
    )
    def test_REQ_o00062_M_each_stale_token_alone_rejects_the_move(
        self, canonical_graph, tools, stale_token, expected_node_id
    ):
        """REQ-o00062-M: One stale token out of three still blocks the move,
        and the conflict names the node that actually moved on."""
        tokens = self._live_tokens(canonical_graph)
        tokens[stale_token] = BOGUS_VERSION

        result = tools["mutate_move_node_to_file"](
            node_id=self.NODE, target_file_id=self.DESTINATION, **tokens
        )

        assert result["success"] is False, f"stale {stale_token} did not block the move"
        assert result["code"] == "version_conflict"
        assert result["node_id"] == expected_node_id
        assert CONFLICT_KEYS <= set(result)
        assert canonical_graph.find_by_id(self.NODE).file_node().id == self.ORIGIN

    def test_REQ_o00062_O_destination_outside_spec_dirs_is_rejected_and_nothing_created(
        self, canonical_graph, tools
    ):
        """REQ-o00062-O: A new destination is validated against the scanning
        config exactly as the HTTP route validates it -- a path under no
        configured spec directory is refused with a plain error (neither a
        version conflict nor node_not_found: retrying or re-reading cannot
        fix it), and no file appears on disk."""
        tokens = self._live_tokens(canonical_graph)
        tokens["if_target_version"] = ""

        result = tools["mutate_move_node_to_file"](
            node_id=self.NODE, target_file_id="file:notaspecdir/x.md", **tokens
        )

        assert result["success"] is False
        assert result.get("code") not in ("version_conflict", "node_not_found")
        assert "not under any configured spec directory" in result["error"]
        assert not (HHT_LIKE / "notaspecdir" / "x.md").exists()
        assert not (HHT_LIKE / "notaspecdir").exists()
        assert canonical_graph.find_by_id("file:notaspecdir/x.md") is None
        assert canonical_graph.find_by_id(self.NODE).file_node().id == self.ORIGIN

    def test_REQ_o00062_O_path_traversal_destination_is_rejected_and_nothing_created(
        self, canonical_graph, tools
    ):
        """REQ-o00062-O: A destination that escapes the repository root is
        refused outright -- same precondition as the HTTP route -- and no
        file is written anywhere."""
        tokens = self._live_tokens(canonical_graph)
        tokens["if_target_version"] = ""

        result = tools["mutate_move_node_to_file"](
            node_id=self.NODE, target_file_id="file:../escape.md", **tokens
        )

        assert result["success"] is False
        assert result.get("code") not in ("version_conflict", "node_not_found")
        assert ".." in result["error"] or "escape" in result["error"].lower()
        assert not (HHT_LIKE.parent / "escape.md").exists()
        assert canonical_graph.find_by_id(self.NODE).file_node().id == self.ORIGIN

    def test_REQ_o00062_M_all_three_current_tokens_admit_the_move(self, rollback, tools):
        """REQ-o00062-M: With every affected node reconciled, the move lands and
        both files move on while the node's own version is content-stable."""
        tokens = self._live_tokens(rollback)

        result = tools["mutate_move_node_to_file"](
            node_id=self.NODE, target_file_id=self.DESTINATION, **tokens
        )

        assert result["success"] is True, result.get("error")
        assert rollback.find_by_id(self.NODE).file_node().id == self.DESTINATION
        assert node_version(rollback.find_by_id(self.ORIGIN)) != tokens["if_source_file_version"]
        assert node_version(rollback.find_by_id(self.DESTINATION)) != tokens["if_target_version"]

    def test_REQ_o00062_K_success_returns_the_moved_nodes_version(self, rollback, tools):
        """REQ-o00062-K: ``version`` tracks the node named by ``node_id``."""
        tokens = self._live_tokens(rollback)

        result = tools["mutate_move_node_to_file"](
            node_id=self.NODE, target_file_id=self.DESTINATION, **tokens
        )

        assert result["version"] == node_version(rollback.find_by_id(self.NODE))


class TestMoveNodeCreatesMissingDestinationParity:
    """Validates REQ-o00062-O, REQ-o00062-M:

    HTTP's ``/api/mutate/move-to-file`` creates a missing destination file:
    every guard runs first, and ``if_target_version`` is not required for a
    destination the move itself creates -- it has no prior version, so there
    is nothing to clobber (the same rule parentless creation follows; see
    routes_api.api_mutate_move_to_file). Capability parity (REQ-o00062-O)
    requires the MCP tool to honor the same contract instead of reporting
    ``node_not_found`` for the not-yet-existing FILE.

    Runs against the throwaway on-disk project because the HTTP contract
    creates the destination file on disk.
    """

    NODE = "REQ-d00003"
    ORIGIN = "file:spec/dev-impl.md"
    NEW_DESTINATION = "file:spec/relocated.md"
    NEW_PATH = "spec/relocated.md"

    def test_REQ_o00062_O_move_to_missing_destination_creates_and_wires_the_file(
        self, disk_project, disk_tools
    ):
        """REQ-o00062-O: With the node and origin tokens live and
        ``if_target_version=""`` for the new destination, the move lands: the
        FILE node exists afterwards and the moved node renders into it."""
        tools, graph = disk_tools

        result = tools["mutate_move_node_to_file"](
            node_id=self.NODE,
            target_file_id=self.NEW_DESTINATION,
            if_version=node_version(graph.find_by_id(self.NODE)),
            if_source_file_version=node_version(graph.find_by_id(self.ORIGIN)),
            if_target_version="",
        )

        assert result["success"] is True, result.get("error", result.get("code"))
        destination = graph.find_by_id(self.NEW_DESTINATION)
        assert destination is not None, "the move did not create the destination FILE node"
        moved = graph.find_by_id(self.NODE)
        assert moved.file_node() is not None
        assert moved.file_node().id == self.NEW_DESTINATION
        assert self.NODE in render.render_file(destination)
        # Pollution tripwire: the file was created inside the throwaway copy,
        # never inside the checked-in fixture directory.
        assert (disk_project / self.NEW_PATH).exists()
        assert not (HHT_LIKE / self.NEW_PATH).exists()

    def test_REQ_o00062_M_stale_node_token_rejects_before_the_file_is_created(
        self, disk_project, disk_tools
    ):
        """REQ-o00062-M: Guard selection -- every stated token is checked
        BEFORE the destination is created, so a refusal strands no empty file
        on disk and no FILE node in the graph."""
        tools, graph = disk_tools

        result = tools["mutate_move_node_to_file"](
            node_id=self.NODE,
            target_file_id=self.NEW_DESTINATION,
            if_version=BOGUS_VERSION,
            if_source_file_version=node_version(graph.find_by_id(self.ORIGIN)),
            if_target_version="",
        )

        assert result["success"] is False
        assert result["code"] == "version_conflict"
        assert result["node_id"] == self.NODE
        assert not (disk_project / self.NEW_PATH).exists()
        assert graph.find_by_id(self.NEW_DESTINATION) is None


# ─────────────────────────────────────────────────────────────────────────────
# MCP-only mutations that write spec files directly
# ─────────────────────────────────────────────────────────────────────────────

# (tool, node whose rendered form the write changes, kwargs, file touched on
# disk, whether that node's version moves as a result).
#
# ``move_requirement`` relocates a requirement between files without changing
# a character of its own block, so its version -- being content-derived -- is
# deliberately unchanged; the guard still matters because a concurrent editor
# of that requirement would lose the edit when the block is rewritten
# elsewhere.
DISK_TOOL_CALLS = [
    (
        "apply_link",
        "file:tests/test_auth.py",
        {"file_path": "tests/test_auth.py", "line": 5, "requirement_id": "REQ-d00001"},
        "tests/test_auth.py",
        True,
    ),
    (
        "change_reference_type",
        "REQ-d00003",
        {"req_id": "REQ-d00003", "target_id": "p00003", "new_type": "REFINES"},
        "spec/dev-impl.md",
        True,
    ),
    (
        "move_requirement",
        "REQ-d00003",
        {"req_id": "REQ-d00003", "target_file": "spec/ops-deploy.md"},
        "spec/dev-impl.md",
        False,
    ),
]

DISK_IDS = [call[0] for call in DISK_TOOL_CALLS]


@pytest.fixture
def disk_project(tmp_path):
    """A throwaway copy of the hht-like fixture, safe to rewrite on disk."""
    project = tmp_path / "hht-like"
    shutil.copytree(HHT_LIKE, project)
    return project


@pytest.fixture
def disk_tools(disk_project):
    """(tools, graph) bound to the throwaway project.

    These three tools rewrite spec files and then rebuild, so they cannot run
    against the session-scoped canonical fixture -- they would edit the
    repository's own test data.
    """
    pytest.importorskip("mcp")
    from elspais.graph.factory import build_graph
    from elspais.mcp.server import create_server

    graph = build_graph(repo_root=disk_project)
    server = create_server(graph, working_dir=disk_project)
    return {name: tool.fn for name, tool in server._tool_manager._tools.items()}, graph


@pytest.mark.parametrize(
    ("tool_name", "guarded_id", "kwargs", "touched_path", "version_moves"),
    DISK_TOOL_CALLS,
    ids=DISK_IDS,
)
class TestDiskBackedMutationsAreGuarded:
    """Validates REQ-o00062-M, REQ-o00062-I, REQ-o00062-J, REQ-o00062-K, REQ-o00062-L:

    Writing straight to the spec files loses a concurrent edit just as an
    in-memory write does -- more completely, in fact, since the write is
    already on disk when the next rebuild happens. Each of these states the
    version of the node whose rendered form it rewrites: the FILE receiving a
    ``# Implements:``/``# Verifies:`` comment, or the requirement whose
    metadata line or file placement changes.
    """

    def test_REQ_o00062_M_if_version_is_a_required_parameter(
        self, disk_tools, tool_name, guarded_id, kwargs, touched_path, version_moves
    ):
        """REQ-o00062-M: if_version has no default -- callers cannot omit it."""
        tools, _graph = disk_tools
        params = inspect.signature(tools[tool_name]).parameters

        assert "if_version" in params, f"{tool_name} does not accept if_version"
        assert params["if_version"].default is inspect.Parameter.empty

    def test_REQ_o00062_M_omitting_if_version_is_a_type_error(
        self, disk_tools, tool_name, guarded_id, kwargs, touched_path, version_moves
    ):
        """REQ-o00062-M: A blind write cannot reach the spec files."""
        tools, _graph = disk_tools

        with pytest.raises(TypeError):
            tools[tool_name](**kwargs)

    def test_REQ_o00062_I_stale_version_leaves_the_file_on_disk_untouched(
        self, disk_project, disk_tools, tool_name, guarded_id, kwargs, touched_path, version_moves
    ):
        """REQ-o00062-I: The guard fires before any bytes are written."""
        tools, _graph = disk_tools
        target = disk_project / touched_path
        before = target.read_bytes()

        result = tools[tool_name](if_version=BOGUS_VERSION, **kwargs)

        assert result["success"] is False, f"{tool_name} wrote with a stale version"
        assert result["code"] == "version_conflict"
        assert target.read_bytes() == before

    def test_REQ_o00062_J_conflict_names_the_node_whose_text_changes(
        self, disk_tools, tool_name, guarded_id, kwargs, touched_path, version_moves
    ):
        """REQ-o00062-J: The rejection carries the standard reconcile payload."""
        tools, _graph = disk_tools

        result = tools[tool_name](if_version=BOGUS_VERSION, **kwargs)

        assert CONFLICT_KEYS <= set(result), f"{tool_name} conflict is missing keys"
        assert result["node_id"] == guarded_id
        assert result["provided_version"] == BOGUS_VERSION
        assert result["current_version"] != BOGUS_VERSION
        assert isinstance(result["current_state"], dict)
        assert "error" not in result["current_state"]

    def test_REQ_o00062_K_current_version_is_accepted_and_a_version_returned(
        self, disk_project, disk_tools, tool_name, guarded_id, kwargs, touched_path, version_moves
    ):
        """REQ-o00062-K: The live token lands the write, and the result carries
        the post-write version read back from the rebuilt graph."""
        from elspais.graph.factory import build_graph

        tools, graph = disk_tools
        current = node_version(graph.find_by_id(guarded_id))

        result = tools[tool_name](if_version=current, **kwargs)

        assert result["success"] is True, result.get("error")
        rebuilt = build_graph(repo_root=disk_project)
        after = node_version(rebuilt.find_by_id(guarded_id))
        assert result["version"] == after
        assert (after != current) is version_moves

    def test_REQ_o00062_L_missing_target_reports_node_not_found(
        self, disk_tools, tool_name, guarded_id, kwargs, touched_path, version_moves
    ):
        """REQ-o00062-L: Naming something that does not exist is not retryable."""
        tools, _graph = disk_tools
        absent = {**kwargs}
        if tool_name == "apply_link":
            absent["file_path"] = "tests/test_absent.py"
        else:
            absent["req_id"] = "REQ-d99999"

        result = tools[tool_name](if_version=BOGUS_VERSION, **absent)

        assert result["success"] is False
        assert result["code"] == "node_not_found"


# ─────────────────────────────────────────────────────────────────────────────
# No mutation tool may stay unguarded
# ─────────────────────────────────────────────────────────────────────────────


class TestEveryMutationToolIsGuarded:
    """Validates REQ-o00062-M, REQ-o00062-I:

    The guard is a property of the mutation surface, not of the tools that
    happened to be retrofitted. A tool registered later without a version
    token fails here rather than shipping a lost-update hole.
    """

    def test_REQ_o00062_I_the_enumeration_finds_the_mutation_surface(self, tools):
        """REQ-o00062-I: A silent empty set would make the sweep vacuous."""
        mutators = {name for name in tools if name.startswith("mutate_")}

        assert len(mutators) >= 20, f"tool enumeration looks broken: {sorted(mutators)}"
        assert not (mutators & HISTORY_TOOLS)

    def test_REQ_o00062_I_every_mutate_tool_accepts_if_version(self, tools):
        """REQ-o00062-I: Every ``mutate_*`` tool takes a version token."""
        unguarded = sorted(
            name
            for name in tools
            if name.startswith("mutate_")
            and name not in HISTORY_TOOLS
            and "if_version" not in inspect.signature(tools[name]).parameters
        )

        assert not unguarded, (
            f"mutation tools with no version guard: {unguarded}. "
            "Add if_version and call _guard_version before mutating."
        )

    def test_REQ_o00062_M_if_version_is_required_on_every_tool_but_the_parentless_create(
        self, tools
    ):
        """REQ-o00062-M, REQ-o00062-I: A present-but-defaulted token is the same
        hole as a missing one -- callers could still write blind. The sole
        sanctioned exemption is parentless creation (``mutate_add_requirement``),
        and this asserts the exemption set is exactly that one tool."""
        optional = sorted(
            name
            for name in tools
            if name.startswith("mutate_")
            and name not in HISTORY_TOOLS
            and "if_version" in inspect.signature(tools[name]).parameters
            and inspect.signature(tools[name]).parameters["if_version"].default
            is not inspect.Parameter.empty
        )

        assert optional == sorted(VERSION_OPTIONAL_TOOLS), (
            f"mutation tools with an optional if_version: {optional}. "
            "Only mutate_add_requirement (parentless creation, REQ-o00062-I) may "
            "default its token; every other tool must make it required."
        )

    def test_REQ_o00062_I_every_mutate_tool_has_behavioral_conflict_coverage(self, tools):
        """REQ-o00062-I: The signature sweep above proves a token is *accepted*;
        this proves each tool is also *exercised* against a stale token. The
        union of the behavioral parametrization lists (plus the dedicated
        guard-shape classes named in DEDICATED_CLASS_TOOLS) must equal the
        registered ``mutate_*`` surface, so a tool added tomorrow fails here
        unless it also gains behavioral conflict tests."""
        from tests.mcp.test_mcp_http_parity import PARITY_TOOL_CALLS
        from tests.mcp.test_mcp_version_guard import IN_SCOPE_TOOL_CALLS

        behavioral = (
            {call[0] for call in IN_SCOPE_TOOL_CALLS}
            | {call[0] for call in EDGE_TOOL_CALLS}
            | {call[0] for call in CREATION_TOOL_CALLS}
            | {call[0] for call in DISK_TOOL_CALLS}
            | {call[0] for call in PARITY_TOOL_CALLS}
            | DEDICATED_CLASS_TOOLS
        )
        registry = {
            name for name in tools if name.startswith("mutate_") and name not in HISTORY_TOOLS
        } | DISK_BACKED_TOOLS

        uncovered = sorted(registry - behavioral)
        assert not uncovered, (
            f"mutation tools with no behavioral conflict coverage: {uncovered}. "
            "Add each to a parametrization list (IN_SCOPE/EDGE/CREATION/DISK/PARITY "
            "_TOOL_CALLS) or give it a dedicated guard class and name it in "
            "DEDICATED_CLASS_TOOLS."
        )

        stale = sorted(behavioral - registry)
        assert not stale, (
            f"behavioral lists name tools that are not registered: {stale}. "
            "Remove or rename the stale entries so the sweep stays exact."
        )

    def test_REQ_o00062_M_the_disk_backed_mutations_accept_if_version(self, tools):
        """REQ-o00062-M: The MCP-only spec-file writers are guarded too --
        they are mutations without the ``mutate_`` prefix."""
        unguarded = sorted(
            name
            for name in DISK_BACKED_TOOLS
            if "if_version" not in inspect.signature(tools[name]).parameters
        )

        assert not unguarded, f"disk-backed mutations with no version guard: {unguarded}"
