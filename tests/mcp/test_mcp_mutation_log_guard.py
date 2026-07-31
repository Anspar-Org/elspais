# Verifies: REQ-o00062-N
"""Optimistic-concurrency guard on the four history-level MCP tools.

The node-level guard (``if_version``, see ``test_mcp_version_guard.py`` and
``test_mcp_version_guard_relations.py``) protects one node's text from a
concurrent writer. It cannot protect anything here: ``undo_last_mutation``,
``undo_to_mutation``, ``refresh_graph(force=True)`` and ``save_mutations``
name no node at all. They act on the mutation log as a whole, and therefore
on every writer's pending work at once -- reversing it, discarding it, or
committing it to disk.

REQ-o00062-N gives them the matching precondition: the caller must name the
current *end* of the history. A caller that read the log, then acted on it
after somebody else appended to it, is refused and shown the entries it had
never seen.

Wire contract pinned by these tests
-----------------------------------
* Parameter: ``if_mutation_id`` on ``undo_last_mutation`` (it takes no other
  id, so the plain name reads correctly); ``if_tip_mutation_id`` on the other
  three, where ``undo_to_mutation`` already has a ``mutation_id`` meaning
  something else entirely (the target, not the tip).
* Rejection: ``code == "mutation_log_conflict"``, carrying ``provided_tip``,
  ``current_tip``, ``unseen`` and ``hint``. Sibling of ``version_conflict``,
  never conflated with it.
* ``unseen`` holds the entries appended *after* the caller's tip, oldest
  first, serialized with the existing ``_serialize_mutation_entry``.

Empty log
---------
``""`` is the wire spelling of "I believe nothing is pending", and it matches
only when the log is genuinely empty; ``current_tip`` is reported as ``None``
in that case. This choice is what lets ``refresh_graph`` keep a default for
its tip parameter (it is only required for ``force=True``) without inventing
a second "you omitted it" rejection: an omitted tip simply asserts an empty
log, and asserting that falsely is an ordinary conflict.

A tip the log has never heard of is treated as a position before the start of
the log, so ``unseen`` is *everything currently pending* -- the conservative
reading, and the only one that never under-reports what is about to be undone
or discarded.

These tests drive the registered MCP tool closures, not the ``_undo_*``
helpers, because the guard lives in the tool wrapper.
"""

from __future__ import annotations

import inspect
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from elspais.graph import render

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
HHT_LIKE = FIXTURES_DIR / "hht-like"

# A syntactically plausible mutation id (uuid4 hex) that no log will contain.
BOGUS_TIP = "0" * 32

# The wire spelling of "the log is empty".
EMPTY_TIP = ""

LOG_CONFLICT_KEYS = {
    "success",
    "code",
    "provided_tip",
    "current_tip",
    "unseen",
    "hint",
}

# tool -> the name of its tip parameter. ``restore_from_safety_branch`` is
# history-level too: it overwrites every spec file from a git branch and
# rebuilds, which discards all pending in-memory work at once.
HISTORY_TOOL_TIP_PARAMS = {
    "undo_last_mutation": "if_mutation_id",
    "undo_to_mutation": "if_tip_mutation_id",
    "refresh_graph": "if_tip_mutation_id",
    "save_mutations": "if_tip_mutation_id",
    "restore_from_safety_branch": "if_tip_mutation_id",
}

# ``refresh_graph`` is the one history tool whose tip is conditionally
# required -- a non-force refresh never discards anything.
CONDITIONALLY_REQUIRED = {"refresh_graph"}

SAVE_MESSAGE = "mutation-log guard test"


def node_version(node) -> str:
    """Resolve ``render.node_version`` at call time."""
    return render.node_version(node)


def tip_of(graph) -> str:
    """The id of the last entry in the federated mutation log, or ``""``.

    ``FederatedMutationLog`` has no ``last()`` -- it stores pointers and
    resolves them lazily -- so the tip is read off ``iter_entries()``.
    """
    entries = list(graph.mutation_log.iter_entries())
    return entries[-1].id if entries else EMPTY_TIP


def log_ids(graph) -> list[str]:
    """All pending mutation ids, oldest first."""
    return [entry.id for entry in graph.mutation_log.iter_entries()]


@pytest.fixture
def tools(canonical_federated_graph):
    """Map of MCP tool name -> raw closure, bound to the canonical graph."""
    pytest.importorskip("mcp")
    from elspais.mcp.server import create_server

    server = create_server(canonical_federated_graph, working_dir=HHT_LIKE)
    return {name: tool.fn for name, tool in server._tool_manager._tools.items()}


@pytest.fixture(scope="class")
def chain(canonical_federated_graph):
    """Undo a whole ``@pytest.mark.incremental`` class's mutations at teardown.

    Undo MUST run on the FederatedGraph, the same object the tools mutate.
    Undoing on the inner TraceGraph bypasses ``_federated_log.pop()`` and
    ``_rebuild_ownership()``, leaving the federated index inconsistent and
    silently contaminating later tests.
    """
    before = len(canonical_federated_graph.mutation_log)
    yield canonical_federated_graph
    while len(canonical_federated_graph.mutation_log) > before:
        if canonical_federated_graph.undo_last() is None:
            break


@pytest.fixture
def disk_project(tmp_path):
    """A throwaway copy of the hht-like fixture, safe to rewrite on disk.

    ``save_mutations`` writes spec files and ``refresh_graph`` re-reads them,
    so neither may run against the repository's own test data.
    """
    project = tmp_path / "hht-like"
    shutil.copytree(HHT_LIKE, project)
    return project


@pytest.fixture
def disk_tools(disk_project):
    """(tools, graph) bound to the throwaway project."""
    pytest.importorskip("mcp")
    from elspais.graph.factory import build_graph
    from elspais.mcp.server import create_server

    graph = build_graph(repo_root=disk_project)
    server = create_server(graph, working_dir=disk_project)
    return {name: tool.fn for name, tool in server._tool_manager._tools.items()}, graph


def seed(tools, graph, node_id: str, title: str) -> str:
    """Apply one title mutation and return the resulting log tip."""
    result = tools["mutate_update_title"](
        node_id=node_id,
        new_title=title,
        if_version=node_version(graph.find_by_id(node_id)),
    )
    assert result["success"] is True, result
    return tip_of(graph)


# ─────────────────────────────────────────────────────────────────────────────
# undo_last_mutation
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.incremental
class TestUndoLastRequiresTheCurrentTip:
    """Validates REQ-o00062-N:

    A caller that read the log, then undid "the last mutation" after another
    writer appended one, would silently revert work it never saw. Naming the
    tip it believes in turns that into a rejection carrying the entry it
    missed.
    """

    TARGET = "REQ-d00003"
    FIRST = "Audit Trail Implementation (writer A)"

    def test_REQ_o00062_N_two_writers_append_two_entries(self, chain, tools):
        """REQ-o00062-N: Writer A's tip goes stale the moment B appends."""
        TestUndoLastRequiresTheCurrentTip.stale_tip = seed(tools, chain, self.TARGET, self.FIRST)
        result = tools["mutate_change_status"](
            node_id=self.TARGET,
            new_status="Draft",
            if_version=node_version(chain.find_by_id(self.TARGET)),
        )
        TestUndoLastRequiresTheCurrentTip.current_tip = tip_of(chain)

        assert result["success"] is True, result
        assert self.stale_tip != self.current_tip
        assert chain.find_by_id(self.TARGET).status == "Draft"

    def test_REQ_o00062_N_stale_tip_is_rejected_and_nothing_is_undone(self, chain, tools):
        """REQ-o00062-N: A's undo does not silently swallow B's mutation."""
        depth = len(chain.mutation_log)

        result = tools["undo_last_mutation"](if_mutation_id=self.stale_tip)
        TestUndoLastRequiresTheCurrentTip.conflict = result

        assert result["success"] is False
        assert result["code"] == "mutation_log_conflict"
        assert len(chain.mutation_log) == depth
        assert chain.find_by_id(self.TARGET).status == "Draft"

    def test_REQ_o00062_N_rejection_names_both_tips(self, chain):
        """REQ-o00062-N: The rejection states what was sent and what is live."""
        conflict = self.conflict

        assert LOG_CONFLICT_KEYS <= set(conflict)
        assert conflict["provided_tip"] == self.stale_tip
        assert conflict["current_tip"] == self.current_tip
        assert conflict["current_tip"] == tip_of(chain)
        assert isinstance(conflict["hint"], str) and conflict["hint"].strip()

    def test_REQ_o00062_N_unseen_is_exactly_the_entry_appended_after_the_tip(self, chain):
        """REQ-o00062-N: The caller is shown the one mutation it never read."""
        unseen = self.conflict["unseen"]

        assert [entry["id"] for entry in unseen] == [self.current_tip]
        assert unseen[0]["operation"] == "change_status"
        assert unseen[0]["target_id"] == self.TARGET

    def test_REQ_o00062_N_unseen_uses_the_existing_serializer(self, chain):
        """REQ-o00062-N: No second serialization format for mutation entries."""
        from elspais.mcp.server import _serialize_mutation_entry

        live = chain.mutation_log.find_by_id(self.current_tip)

        assert self.conflict["unseen"] == [_serialize_mutation_entry(live)]

    def test_REQ_o00062_N_rejection_is_not_a_version_conflict(self):
        """REQ-o00062-N: The history guard has its own code and payload."""
        assert self.conflict["code"] != "version_conflict"
        assert "provided_version" not in self.conflict

    def test_REQ_o00062_N_current_tip_is_accepted(self, chain, tools):
        """REQ-o00062-N: With the live tip named, the undo runs normally."""
        depth = len(chain.mutation_log)

        result = tools["undo_last_mutation"](if_mutation_id=self.current_tip)

        assert result["success"] is True, result
        assert result["mutation"]["id"] == self.current_tip
        assert len(chain.mutation_log) == depth - 1
        assert chain.find_by_id(self.TARGET).status != "Draft"

    def test_REQ_o00062_N_an_accepted_call_reports_nothing_unseen(self, chain, tools):
        """REQ-o00062-N: When the caller's tip IS the tip, nothing was missed."""
        result = tools["undo_last_mutation"](if_mutation_id=tip_of(chain))

        assert result["success"] is True, result
        assert result.get("unseen", []) == []
        assert chain.find_by_id(self.TARGET).get_label() != self.FIRST


class TestUndoLastTipIsRequired:
    """Validates REQ-o00062-N:

    An unguarded undo is exactly the failure being prevented, so the tip has
    no default.
    """

    def test_REQ_o00062_N_tip_parameter_has_no_default(self, tools):
        """REQ-o00062-N: ``if_mutation_id`` is a required parameter."""
        params = inspect.signature(tools["undo_last_mutation"]).parameters

        assert "if_mutation_id" in params
        assert params["if_mutation_id"].default is inspect.Parameter.empty

    def test_REQ_o00062_N_omitting_the_tip_is_a_type_error(self, disk_tools):
        """REQ-o00062-N: A blind undo cannot be issued at all."""
        tools, _graph = disk_tools

        with pytest.raises(TypeError):
            tools["undo_last_mutation"]()


# ─────────────────────────────────────────────────────────────────────────────
# undo_to_mutation
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.incremental
class TestUndoToPinsTheTip:
    """Validates REQ-o00062-N:

    ``undo_to_mutation`` already names where to unwind *to*. What it lacks is
    a statement of where the history *ends*, and without that a caller
    unwinds through everything that arrived after it last looked.
    """

    TARGET = "REQ-d00002"

    def test_REQ_o00062_N_three_mutations_are_appended(self, chain, tools):
        """REQ-o00062-N: Establish a log the caller has only partly seen."""
        TestUndoToPinsTheTip.floor = seed(tools, chain, self.TARGET, "Privacy Controls (1)")
        TestUndoToPinsTheTip.stale_tip = seed(tools, chain, self.TARGET, "Privacy Controls (2)")
        TestUndoToPinsTheTip.current_tip = seed(tools, chain, self.TARGET, "Privacy Controls (3)")

        assert len({self.floor, self.stale_tip, self.current_tip}) == 3
        assert chain.find_by_id(self.TARGET).get_label() == "Privacy Controls (3)"

    def test_REQ_o00062_N_stale_tip_rejected_and_nothing_unwound(self, chain, tools):
        """REQ-o00062-N: The third writer's work is not unwound behind its back."""
        depth = len(chain.mutation_log)

        result = tools["undo_to_mutation"](
            mutation_id=self.floor, if_tip_mutation_id=self.stale_tip
        )
        TestUndoToPinsTheTip.conflict = result

        assert result["success"] is False
        assert result["code"] == "mutation_log_conflict"
        assert len(chain.mutation_log) == depth
        assert chain.find_by_id(self.TARGET).get_label() == "Privacy Controls (3)"

    def test_REQ_o00062_N_unseen_lists_entries_after_the_tip_in_order(self, chain):
        """REQ-o00062-N: Only what followed the caller's position, oldest first."""
        conflict = self.conflict

        assert LOG_CONFLICT_KEYS <= set(conflict)
        assert conflict["provided_tip"] == self.stale_tip
        assert conflict["current_tip"] == self.current_tip
        assert [entry["id"] for entry in conflict["unseen"]] == [self.current_tip]
        assert self.floor not in {entry["id"] for entry in conflict["unseen"]}

    def test_REQ_o00062_N_current_tip_admits_the_unwind(self, chain, tools):
        """REQ-o00062-N: Naming the live tip lets the whole range unwind."""
        depth = len(chain.mutation_log)

        result = tools["undo_to_mutation"](
            mutation_id=self.floor, if_tip_mutation_id=self.current_tip
        )

        assert result["success"] is True, result
        assert result["mutations_undone"] == 3
        assert len(chain.mutation_log) == depth - 3
        assert chain.find_by_id(self.TARGET).get_label() != "Privacy Controls (3)"


class TestUndoToTipIsRequired:
    """Validates REQ-o00062-N:

    Kept out of the incremental class above so a failure there cannot mask
    the signature contract.
    """

    def test_REQ_o00062_N_tip_parameter_has_no_default(self, tools):
        """REQ-o00062-N: ``if_tip_mutation_id`` is required."""
        params = inspect.signature(tools["undo_to_mutation"]).parameters

        assert "if_tip_mutation_id" in params
        assert params["if_tip_mutation_id"].default is inspect.Parameter.empty

    def test_REQ_o00062_N_omitting_the_tip_is_a_type_error(self, disk_tools):
        """REQ-o00062-N: The target alone is not enough to unwind."""
        tools, _graph = disk_tools

        with pytest.raises(TypeError):
            tools["undo_to_mutation"](mutation_id=BOGUS_TIP)


# ─────────────────────────────────────────────────────────────────────────────
# refresh_graph(force=True) -- discards every writer's pending work
# ─────────────────────────────────────────────────────────────────────────────


class TestRefreshGraphForceRequiresTheTip:
    """Validates REQ-o00062-N:

    ``force=True`` throws away the pending mutation log wholesale. That is
    the most destructive of the four, and the only one whose guard is
    conditional: a non-force refresh discards nothing and is unchanged.
    """

    TARGET = "REQ-d00003"
    TITLE = "Audit Trail Implementation (pending)"

    def test_REQ_o00062_N_force_with_a_stale_tip_discards_nothing(self, disk_tools):
        """REQ-o00062-N: Pending work survives a mis-stated tip."""
        tools, graph = disk_tools
        seed(tools, graph, self.TARGET, self.TITLE)
        depth = len(graph.mutation_log)

        result = tools["refresh_graph"](force=True, if_tip_mutation_id=BOGUS_TIP)

        assert result["success"] is False
        assert result["code"] == "mutation_log_conflict"
        assert len(graph.mutation_log) == depth
        assert graph.find_by_id(self.TARGET).get_label() == self.TITLE

    def test_REQ_o00062_N_force_rejection_reports_the_unseen_entries(self, disk_tools):
        """REQ-o00062-N: The caller sees precisely what it was about to discard."""
        tools, graph = disk_tools
        seed(tools, graph, self.TARGET, self.TITLE)
        second = seed(tools, graph, "REQ-d00002", "Privacy Controls (pending)")

        result = tools["refresh_graph"](force=True, if_tip_mutation_id=BOGUS_TIP)

        assert LOG_CONFLICT_KEYS <= set(result)
        assert result["provided_tip"] == BOGUS_TIP
        assert result["current_tip"] == second
        # An unrecognized tip is a position before the start of the log, so
        # everything pending is unseen.
        assert [entry["id"] for entry in result["unseen"]] == log_ids(graph)

    def test_REQ_o00062_N_force_with_an_omitted_tip_is_rejected_when_work_is_pending(
        self, disk_tools
    ):
        """REQ-o00062-N: Omitting the tip asserts an empty log; asserting that
        falsely is an ordinary conflict, not a silent discard."""
        tools, graph = disk_tools
        tip = seed(tools, graph, self.TARGET, self.TITLE)

        result = tools["refresh_graph"](force=True)

        assert result["success"] is False
        assert result["code"] == "mutation_log_conflict"
        assert result["provided_tip"] == EMPTY_TIP
        assert result["current_tip"] == tip
        assert len(graph.mutation_log) == 1

    def test_REQ_o00062_N_force_with_the_current_tip_discards_as_asked(self, disk_tools):
        """REQ-o00062-N: A caller that has seen the log may still discard it."""
        tools, graph = disk_tools
        tip = seed(tools, graph, self.TARGET, self.TITLE)

        result = tools["refresh_graph"](force=True, if_tip_mutation_id=tip)

        assert result.get("success") is not False, result
        assert result.get("code") != "mutation_log_conflict"
        # The server now serves a graph rebuilt from disk, where the pending
        # title never landed and the log is empty.
        assert tools["get_mutation_log"]()["count"] == 0

    def test_REQ_o00062_N_tip_parameter_exists_and_is_optional(self, tools):
        """REQ-o00062-N: Conditionally required -- a non-force refresh needs no tip."""
        params = inspect.signature(tools["refresh_graph"]).parameters

        assert "if_tip_mutation_id" in params
        assert params["if_tip_mutation_id"].default is not inspect.Parameter.empty


class TestNonForceRefreshRefusalDoesNotRegress:
    """Validates REQ-o00062-N:

    The tip guard is layered on top of the existing pending-mutations
    refusal, not in place of it. A plain ``refresh_graph()`` with work
    pending must still refuse, with its existing message, and must not start
    demanding a tip.
    """

    TARGET = "REQ-d00003"

    def test_REQ_o00062_N_pending_mutations_still_refuse_a_plain_refresh(self, disk_tools):
        """REQ-o00062-N: The pre-existing guard rail is untouched."""
        tools, graph = disk_tools
        seed(tools, graph, self.TARGET, "Audit Trail Implementation (pending)")

        result = tools["refresh_graph"]()

        assert result["success"] is False
        assert "Unsaved mutations (1 pending)" in result["message"]
        assert result.get("code") != "mutation_log_conflict"
        assert len(graph.mutation_log) == 1

    def test_REQ_o00062_N_clean_non_force_refresh_still_works_without_a_tip(self, disk_tools):
        """REQ-o00062-N: The common read path gains no new precondition."""
        tools, graph = disk_tools

        result = tools["refresh_graph"]()

        assert result.get("success") is not False, result
        assert result.get("code") != "mutation_log_conflict"


# ─────────────────────────────────────────────────────────────────────────────
# save_mutations -- commits every writer's pending work to disk
# ─────────────────────────────────────────────────────────────────────────────


class TestSaveMutationsRequiresTheTip:
    """Validates REQ-o00062-N:

    Saving is the one history operation that cannot be undone in memory: it
    writes every pending mutation, including another writer's half-finished
    edit, to the spec files. The harm is measured here in bytes on disk.
    """

    TARGET = "REQ-d00003"
    TITLE = "Audit Trail Implementation (pending)"
    SPEC_FILE = "spec/dev-impl.md"

    def test_REQ_o00062_N_stale_tip_leaves_the_spec_files_untouched(self, disk_project, disk_tools):
        """REQ-o00062-N: The guard fires before a single byte is written."""
        tools, graph = disk_tools
        seed(tools, graph, self.TARGET, self.TITLE)
        target = disk_project / self.SPEC_FILE
        before = target.read_bytes()

        result = tools["save_mutations"](if_tip_mutation_id=BOGUS_TIP, message=SAVE_MESSAGE)

        assert result["success"] is False
        assert result["code"] == "mutation_log_conflict"
        assert target.read_bytes() == before
        assert len(graph.mutation_log) == 1

    def test_REQ_o00062_N_rejection_reports_the_work_about_to_be_persisted(self, disk_tools):
        """REQ-o00062-N: The caller is shown whose edits it nearly committed."""
        tools, graph = disk_tools
        first = seed(tools, graph, self.TARGET, self.TITLE)
        second = seed(tools, graph, "REQ-d00002", "Privacy Controls (pending)")

        result = tools["save_mutations"](if_tip_mutation_id=first, message=SAVE_MESSAGE)

        assert LOG_CONFLICT_KEYS <= set(result)
        assert result["provided_tip"] == first
        assert result["current_tip"] == second
        assert [entry["id"] for entry in result["unseen"]] == [second]

    def test_REQ_o00062_N_current_tip_persists_to_disk(self, disk_project, disk_tools):
        """REQ-o00062-N: With the live tip named, the save runs normally."""
        tools, graph = disk_tools
        tip = seed(tools, graph, self.TARGET, self.TITLE)
        target = disk_project / self.SPEC_FILE
        before = target.read_bytes()

        result = tools["save_mutations"](if_tip_mutation_id=tip, message=SAVE_MESSAGE)

        assert result["success"] is True, result
        assert target.read_bytes() != before
        assert self.TITLE in target.read_text()

    def test_REQ_o00062_N_tip_parameter_has_no_default(self, tools):
        """REQ-o00062-N: ``if_tip_mutation_id`` is required."""
        params = inspect.signature(tools["save_mutations"]).parameters

        assert "if_tip_mutation_id" in params
        assert params["if_tip_mutation_id"].default is inspect.Parameter.empty

    def test_REQ_o00062_N_omitting_the_tip_is_a_type_error(self, disk_tools):
        """REQ-o00062-N: A blind save cannot be issued at all."""
        tools, _graph = disk_tools

        with pytest.raises(TypeError):
            tools["save_mutations"](message=SAVE_MESSAGE)


# ─────────────────────────────────────────────────────────────────────────────
# restore_from_safety_branch -- overwrites every spec file, discarding the log
# ─────────────────────────────────────────────────────────────────────────────


def _run_git(project: Path, *args: str) -> None:
    env = os.environ.copy()
    env.pop("GIT_DIR", None)
    env.pop("GIT_WORK_TREE", None)
    subprocess.run(["git", *args], cwd=project, env=env, capture_output=True, check=True)


@pytest.fixture
def git_restore_tools(disk_project):
    """(tools, graph, branch_name) over a git-initialized throwaway project.

    ``restore_from_safety_branch`` checks spec files out of a git branch, so
    the throwaway project is committed and given one safety branch capturing
    its pristine state.
    """
    pytest.importorskip("mcp")
    from elspais.graph.factory import build_graph
    from elspais.mcp.server import create_server
    from elspais.utilities.git import create_safety_branch

    _run_git(disk_project, "init", "-b", "main")
    _run_git(disk_project, "config", "user.email", "guard@test")
    _run_git(disk_project, "config", "user.name", "Guard Test")
    _run_git(disk_project, "add", "-A")
    _run_git(disk_project, "commit", "-m", "pristine fixture")
    branch = create_safety_branch(disk_project, "REQ-o00062")
    assert branch["success"] is True, branch

    graph = build_graph(repo_root=disk_project)
    server = create_server(graph, working_dir=disk_project)
    tools = {name: tool.fn for name, tool in server._tool_manager._tools.items()}
    return tools, graph, branch["branch_name"]


class TestRestoreFromSafetyBranchRequiresTheTip:
    """Validates REQ-o00062-N:

    ``restore_from_safety_branch`` is the most destructive history operation
    of all: it overwrites the spec files wholesale from a git branch, then
    rebuilds -- discarding every writer's pending in-memory work AND the
    current on-disk text in one call. It therefore requires the mutation-log
    tip on the same terms as save/refresh: ``if_tip_mutation_id``, with ``""``
    meaning "I believe nothing is pending", and a stale tip refused as a
    ``mutation_log_conflict`` before a single file is touched.
    """

    TARGET = "REQ-d00003"
    TITLE = "Audit Trail Implementation (pending)"
    SPEC_FILE = "spec/dev-impl.md"
    SENTINEL = "<!-- on-disk state the pristine branch does not contain -->\n"

    def test_REQ_o00062_N_tip_parameter_exists_and_is_required(self, git_restore_tools):
        """REQ-o00062-N: ``if_tip_mutation_id`` is a required parameter."""
        tools, _graph, _branch = git_restore_tools
        params = inspect.signature(tools["restore_from_safety_branch"]).parameters

        assert "if_tip_mutation_id" in params, (
            "restore_from_safety_branch takes no mutation-log tip: a whole-repo "
            "file restore is completely unguarded"
        )
        assert params["if_tip_mutation_id"].default is inspect.Parameter.empty

    def test_REQ_o00062_N_stale_tip_restores_nothing(self, disk_project, git_restore_tools):
        """REQ-o00062-N: The refusal fires before any file is touched -- the
        pending log survives and the on-disk text keeps its sentinel."""
        tools, graph, branch = git_restore_tools
        seed(tools, graph, self.TARGET, self.TITLE)
        target = disk_project / self.SPEC_FILE
        target.write_text(target.read_text() + self.SENTINEL)
        before = target.read_bytes()

        result = tools["restore_from_safety_branch"](
            branch_name=branch, if_tip_mutation_id=BOGUS_TIP
        )

        assert result["success"] is False
        assert result["code"] == "mutation_log_conflict"
        assert target.read_bytes() == before
        assert len(graph.mutation_log) == 1
        assert graph.find_by_id(self.TARGET).get_label() == self.TITLE

    def test_REQ_o00062_N_rejection_reports_the_pending_work(self, git_restore_tools):
        """REQ-o00062-N: The caller is shown exactly what it was about to
        discard, in the same conflict shape as the other history tools."""
        tools, graph, branch = git_restore_tools
        tip = seed(tools, graph, self.TARGET, self.TITLE)

        result = tools["restore_from_safety_branch"](
            branch_name=branch, if_tip_mutation_id=BOGUS_TIP
        )

        assert LOG_CONFLICT_KEYS <= set(result)
        assert result["provided_tip"] == BOGUS_TIP
        assert result["current_tip"] == tip
        assert [entry["id"] for entry in result["unseen"]] == [tip]

    def test_REQ_o00062_N_omitting_the_tip_is_a_type_error(self, git_restore_tools):
        """REQ-o00062-N: A blind whole-repo restore cannot be issued at all."""
        tools, _graph, branch = git_restore_tools

        with pytest.raises(TypeError):
            tools["restore_from_safety_branch"](branch_name=branch)

    def test_REQ_o00062_N_current_tip_admits_the_restore(self, disk_project, git_restore_tools):
        """REQ-o00062-N: A caller that has seen the pending log may discard
        it; the files come back from the branch and the log is empty."""
        tools, graph, branch = git_restore_tools
        tip = seed(tools, graph, self.TARGET, self.TITLE)
        target = disk_project / self.SPEC_FILE
        target.write_text(target.read_text() + self.SENTINEL)

        result = tools["restore_from_safety_branch"](branch_name=branch, if_tip_mutation_id=tip)

        assert result["success"] is True, result
        assert self.SENTINEL not in target.read_text()
        assert tools["get_mutation_log"]()["count"] == 0

    def test_REQ_o00062_N_empty_tip_with_nothing_pending_admits_the_restore(
        self, git_restore_tools
    ):
        """REQ-o00062-N: "" matches an empty log; the no-op belief costs no read."""
        tools, _graph, branch = git_restore_tools

        result = tools["restore_from_safety_branch"](
            branch_name=branch, if_tip_mutation_id=EMPTY_TIP
        )

        assert result["success"] is True, result
        assert result.get("code") != "mutation_log_conflict"


# ─────────────────────────────────────────────────────────────────────────────
# Empty log
# ─────────────────────────────────────────────────────────────────────────────


class TestEmptyLogTipIsTheEmptyString:
    """Validates REQ-o00062-N:

    With nothing pending there is no tip to name. ``""`` is the caller's way
    of saying so, and it is accepted only while that remains true; a caller
    holding a real id against an empty log has lost track of the history and
    is refused, with ``current_tip`` reported as ``None`` rather than an
    invented sentinel.
    """

    def test_REQ_o00062_N_empty_tip_matches_an_empty_log(self, disk_tools):
        """REQ-o00062-N: The guard passes; the pre-existing empty-log error
        is what the caller sees."""
        tools, graph = disk_tools

        result = tools["undo_last_mutation"](if_mutation_id=EMPTY_TIP)

        assert len(graph.mutation_log) == 0
        assert result["success"] is False
        assert result.get("code") != "mutation_log_conflict"
        assert result["error"] == "No mutations to undo"

    def test_REQ_o00062_N_real_tip_against_an_empty_log_is_a_conflict(self, disk_tools):
        """REQ-o00062-N: current_tip is None, and nothing was missed."""
        tools, _graph = disk_tools

        result = tools["undo_last_mutation"](if_mutation_id=BOGUS_TIP)

        assert result["success"] is False
        assert result["code"] == "mutation_log_conflict"
        assert result["current_tip"] is None
        assert result["unseen"] == []

    def test_REQ_o00062_N_empty_tip_admits_a_save(self, disk_tools):
        """REQ-o00062-N: "" matches an empty log, so the save is admitted.

        Deliberately asserts admission rather than byte-identity. ``render_save``
        rewrites canonicalized content (term casing, spacing) whenever the
        on-disk text differs from the rendered form, which this fixture's does —
        that is parse-time canonicalization, not a mutation, and it is outside
        what the tip guard governs. Byte-identity IS asserted for the *rejected*
        case, where it is the harm being prevented.
        """
        tools, _graph = disk_tools

        result = tools["save_mutations"](if_tip_mutation_id=EMPTY_TIP, message=SAVE_MESSAGE)

        assert result["success"] is True, result
        assert result.get("code") != "mutation_log_conflict"

    def test_REQ_o00062_N_empty_tip_admits_a_forced_refresh(self, disk_tools):
        """REQ-o00062-N: force=True with nothing pending discards nothing."""
        tools, _graph = disk_tools

        result = tools["refresh_graph"](force=True, if_tip_mutation_id=EMPTY_TIP)

        assert result.get("success") is not False, result
        assert result.get("code") != "mutation_log_conflict"


# ─────────────────────────────────────────────────────────────────────────────
# No history-level tool may stay unguarded
# ─────────────────────────────────────────────────────────────────────────────


class TestEveryHistoryToolIsGuarded:
    """Validates REQ-o00062-N:

    The guard is a property of the history surface, not of the four tools
    that happened to be retrofitted. A fifth tool that reverses, discards or
    persists the log fails here rather than shipping the hole.
    """

    def test_REQ_o00062_N_every_history_tool_accepts_a_tip_parameter(self, tools):
        """REQ-o00062-N: All four name the end of the history they act on."""
        unguarded = sorted(
            name
            for name, param in HISTORY_TOOL_TIP_PARAMS.items()
            if param not in inspect.signature(tools[name]).parameters
        )

        assert not unguarded, (
            f"history-level tools with no mutation-log guard: {unguarded}. "
            "Add the tip parameter and check it before touching the log."
        )

    def test_REQ_o00062_N_the_tip_is_required_except_for_conditional_refresh(self, tools):
        """REQ-o00062-N: Only ``refresh_graph`` may default its tip, because
        only its destructive path is opt-in."""
        optional = sorted(
            name
            for name, param in HISTORY_TOOL_TIP_PARAMS.items()
            if name not in CONDITIONALLY_REQUIRED
            # A tool missing the parameter entirely fails the sweep above;
            # this one polices only a present-but-defaulted tip.
            and param in inspect.signature(tools[name]).parameters
            and inspect.signature(tools[name]).parameters[param].default
            is not inspect.Parameter.empty
        )

        assert not optional, f"history tools with an optional tip: {optional}"

    def test_REQ_o00062_N_the_history_surface_matches_the_node_guard_sweep(self):
        """REQ-o00062-N: The two sweeps enumerate the same four tools, so a
        new history tool cannot be excused from one by being absent from the
        other."""
        from tests.mcp.test_mcp_version_guard_relations import HISTORY_TOOLS

        assert set(HISTORY_TOOL_TIP_PARAMS) == HISTORY_TOOLS

    def test_REQ_o00062_N_history_tools_do_not_take_a_node_version(self, tools):
        """REQ-o00062-N: These act on the log, not on a node -- guarding them
        with ``if_version`` would name a node they never touch."""
        misguarded = sorted(
            name
            for name in HISTORY_TOOL_TIP_PARAMS
            if "if_version" in inspect.signature(tools[name]).parameters
        )

        assert not misguarded, f"history tools guarded on a node version: {misguarded}"
