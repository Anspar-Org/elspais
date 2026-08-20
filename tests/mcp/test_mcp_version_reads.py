# Verifies: REQ-o00060-G
"""Read surfaces hand back the version token their guards demand.

Every content/metadata mutation tool requires an ``if_version`` token
(``tests/mcp/test_mcp_version_guard.py``). A caller cannot supply a token it
was never given, so the read surfaces must report it: ``get_requirement``,
``get_node`` and ``get_subtree`` carry the version a subsequent mutation of
that node will require, requirement payloads additionally carry the version of
the FILE containing them (so a file-level move needs no second fetch), and
``get_versions`` refreshes a batch of tokens without their content.

The property under test is not "a key exists" but "the token round-trips": the
value read is accepted *unchanged* by the guard, which is the only thing that
proves the read and the guard agree on the resolution rule.

Sub-nodes (ASSERTION, REMAINDER) resolve to the owning REQUIREMENT's version,
matching ``_version_owner()`` and the tokens the mutation tools take.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from elspais.graph import render
from elspais.graph.GraphNode import make_file_id

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
HHT_LIKE = FIXTURES_DIR / "hht-like"

# The namespace the hht-like fixture declares -- structural ids carry the
# namespace of the repository holding the node.
NAMESPACE = "REQ"

# A requirement, one of its assertions, and the file that contains them.
REQ = "REQ-d00003"
ASSERTION = "REQ-d00003-A"
SOURCE_FILE = make_file_id(NAMESPACE, "spec/dev-impl.md")
TARGET_FILE = make_file_id(NAMESPACE, "spec/ops-deploy.md")

UNKNOWN_ID = "REQ-z99999"


def node_version(node) -> str:
    """Resolve ``render.node_version`` at call time (see test_mcp_version_guard)."""
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

    Undo MUST run on the FederatedGraph — the object the ``tools`` fixture
    mutates. Undoing on the inner TraceGraph bypasses ``_federated_log.pop()``
    and ``_rebuild_ownership()`` and silently contaminates later tests.
    """
    before = len(canonical_federated_graph.mutation_log)
    yield canonical_federated_graph
    while len(canonical_federated_graph.mutation_log) > before:
        if canonical_federated_graph.undo_last() is None:
            break


def _iter_nested(entry):
    """Yield every node entry in a ``format="nested"`` tree."""
    yield entry
    for child in entry.get("children", []):
        yield from _iter_nested(child)


# ─────────────────────────────────────────────────────────────────────────────
# The version is on the read payloads, and it is the right one
# ─────────────────────────────────────────────────────────────────────────────


class TestReadSurfacesReportVersion:
    """Validates REQ-o00060-G:

    A read that returns a node reports the version a later mutation of that
    node will require — the value, not merely the key, must match
    ``node_version()`` for the node the guard would resolve.
    """

    def test_REQ_o00060_G_get_requirement_version_is_the_nodes_version(
        self, tools, canonical_federated_graph
    ):
        """The requirement payload reports exactly ``node_version()``."""
        payload = tools["get_requirement"](req_id=REQ)

        assert payload["version"] == node_version(canonical_federated_graph.find_by_id(REQ))

    def test_REQ_o00060_G_get_node_version_is_the_nodes_version(
        self, tools, canonical_federated_graph
    ):
        """The generic node envelope reports exactly ``node_version()``."""
        payload = tools["get_node"](node_id=REQ)

        assert payload["version"] == node_version(canonical_federated_graph.find_by_id(REQ))

    def test_REQ_o00060_G_get_node_on_file_reports_the_file_version(
        self, tools, canonical_federated_graph
    ):
        """FILE nodes are mutable (rename/move), so their reads carry a version."""
        payload = tools["get_node"](node_id=SOURCE_FILE)

        assert payload["version"] == node_version(canonical_federated_graph.find_by_id(SOURCE_FILE))

    def test_REQ_o00060_G_get_node_on_assertion_reports_owning_requirement_version(
        self, tools, canonical_federated_graph
    ):
        """A sub-node reports its owner's version — the token its mutation takes.

        ``mutate_update_assertion`` guards on the parent REQUIREMENT, so an
        assertion read that reported anything else would hand the caller a
        token the guard rejects.
        """
        assertion_payload = tools["get_node"](node_id=ASSERTION)
        parent_version = node_version(canonical_federated_graph.find_by_id(REQ))

        assert assertion_payload["version"] == parent_version
        assert assertion_payload["version"] == tools["get_requirement"](req_id=REQ)["version"]

    @pytest.mark.parametrize("fmt", ["flat", "nested"])
    def test_REQ_o00060_G_get_subtree_nodes_carry_their_versions(
        self, tools, canonical_federated_graph, fmt
    ):
        """Every node in a structured subtree carries its own version."""
        payload = tools["get_subtree"](root_id="REQ-p00001", depth=2, format=fmt)

        if fmt == "flat":
            entries = payload["nodes"]
        else:
            entries = list(_iter_nested(payload["tree"]))

        assert entries, "fixture subtree should not be empty"
        expected = {
            entry["id"]: node_version(canonical_federated_graph.find_by_id(entry["id"]))
            for entry in entries
        }
        assert {entry["id"]: entry["version"] for entry in entries} == expected

    def test_REQ_o00060_G_markdown_subtree_stays_a_rendered_string(self, tools):
        """Pin: the markdown format carries no versions.

        ``format="markdown"`` returns one prose string, not per-node records;
        there is nowhere to put a token without corrupting the rendering. The
        structured formats are the version-bearing ones.
        """
        payload = tools["get_subtree"](root_id="REQ-p00001", depth=2, format="markdown")

        assert set(payload) == {"format", "root_id", "content"}
        assert isinstance(payload["content"], str)


# ─────────────────────────────────────────────────────────────────────────────
# The token round-trips: read -> mutate, unchanged
# ─────────────────────────────────────────────────────────────────────────────


class TestVersionRoundTrip:
    """Validates REQ-o00060-G:

    A version taken from a read is accepted verbatim by the guard on a
    mutation of that node — no massaging, no second read.
    """

    def test_REQ_o00060_G_get_requirement_version_is_accepted_by_a_mutation(self, tools, rollback):
        """The token from ``get_requirement`` passes ``mutate_update_title``."""
        version = tools["get_requirement"](req_id=REQ)["version"]

        result = tools["mutate_update_title"](
            node_id=REQ, new_title="Round-tripped Title", if_version=version
        )

        assert result["success"] is True, result
        assert rollback.find_by_id(REQ).get_label() == "Round-tripped Title"

    def test_REQ_o00060_G_get_node_version_is_accepted_by_a_mutation(self, tools, rollback):
        """The token from ``get_node`` passes ``mutate_change_status``."""
        version = tools["get_node"](node_id=REQ)["version"]

        result = tools["mutate_change_status"](
            node_id=REQ, new_status="Deprecated", if_version=version
        )

        assert result["success"] is True, result
        assert rollback.find_by_id(REQ).get_field("status") == "Deprecated"

    def test_REQ_o00060_G_assertion_read_version_is_accepted_by_its_mutation(self, tools, rollback):
        """A version read off an ASSERTION is what ``mutate_update_assertion`` wants."""
        version = tools["get_node"](node_id=ASSERTION)["version"]

        result = tools["mutate_update_assertion"](
            assertion_id=ASSERTION,
            new_text="The module SHALL round-trip its version.",
            if_version=version,
        )

        assert result["success"] is True, result
        assert "round-trip" in rollback.find_by_id(ASSERTION).get_label()

    def test_REQ_o00060_G_subtree_version_is_accepted_by_a_mutation(self, tools, rollback):
        """A version read out of a subtree entry is equally usable."""
        payload = tools["get_subtree"](root_id=REQ, depth=1, format="flat")
        entry = next(e for e in payload["nodes"] if e["id"] == REQ)

        result = tools["mutate_update_title"](
            node_id=REQ, new_title="Subtree Round-trip", if_version=entry["version"]
        )

        assert result["success"] is True, result
        assert rollback.find_by_id(REQ).get_label() == "Subtree Round-trip"


# ─────────────────────────────────────────────────────────────────────────────
# The containing file's version rides along on requirement payloads
# ─────────────────────────────────────────────────────────────────────────────


class TestRequirementCarriesFileVersion:
    """Validates REQ-o00060-G:

    A requirement payload also reports the version of the FILE containing it,
    so a file-level operation needs no extra fetch.
    """

    def test_REQ_o00060_G_file_version_equals_the_containing_file_version(
        self, tools, canonical_federated_graph
    ):
        """``file_version`` is the containing FILE's ``node_version()``."""
        payload = tools["get_requirement"](req_id=REQ)
        file_node = canonical_federated_graph.find_by_id(REQ).file_node()

        assert payload["file_version"] == node_version(file_node)
        assert file_node.id == SOURCE_FILE

    def test_REQ_o00060_G_file_version_is_accepted_as_if_source_file_version(self, tools, rollback):
        """One read of the requirement is enough to move it between files."""
        payload = tools["get_requirement"](req_id=REQ)
        target_version = tools["get_node"](node_id=TARGET_FILE)["version"]

        result = tools["mutate_move_node_to_file"](
            node_id=REQ,
            target_file_id=TARGET_FILE,
            if_version=payload["version"],
            if_source_file_version=payload["file_version"],
            if_target_version=target_version,
        )

        assert result["success"] is True, result
        assert rollback.find_by_id(REQ).file_node().id == TARGET_FILE

    def test_REQ_o00060_G_fileless_requirement_reports_no_file_version(self):
        """A requirement with no FILE ancestor reports None instead of crashing.

        ``file_node()`` returns None for INSTANCE nodes and unlinked nodes. The
        canonical fixture has neither, so this builds the degenerate case
        directly: a requirement whose CONTAINS edge has been severed.
        """
        from elspais.mcp.server import _get_requirement
        from tests.core.graph_test_helpers import build_graph, make_requirement

        graph = build_graph(
            make_requirement(
                "REQ-p00001",
                title="Fileless",
                assertions=[{"label": "A", "text": "The system SHALL exist."}],
            )
        )
        node = graph.find_by_id("REQ-p00001")
        node.file_node().unlink(node)
        assert node.file_node() is None

        payload = _get_requirement(graph, "REQ-p00001")

        assert payload["file_version"] is None
        assert payload["version"] == node_version(node)


# ─────────────────────────────────────────────────────────────────────────────
# get_versions: the cheap path must not disagree with the expensive one
# ─────────────────────────────────────────────────────────────────────────────


class TestGetVersionsTool:
    """Validates REQ-o00060-G:

    Versions for several nodes are retrievable without their content, and the
    values are the same ones the full reads report.
    """

    def test_REQ_o00060_G_get_versions_matches_the_full_reads(self, tools):
        """The batch values are identical to what the full reads say."""
        ids = [REQ, "REQ-d00001", SOURCE_FILE, ASSERTION]

        batch = tools["get_versions"](node_ids=ids)

        expected = {
            REQ: tools["get_requirement"](req_id=REQ)["version"],
            "REQ-d00001": tools["get_requirement"](req_id="REQ-d00001")["version"],
            SOURCE_FILE: tools["get_node"](node_id=SOURCE_FILE)["version"],
            ASSERTION: tools["get_node"](node_id=ASSERTION)["version"],
        }
        assert batch == expected

    def test_REQ_o00060_G_get_versions_token_is_accepted_by_a_mutation(self, tools, rollback):
        """A token from the cheap path is a usable ``if_version``."""
        version = tools["get_versions"](node_ids=[REQ])[REQ]

        result = tools["mutate_update_title"](
            node_id=REQ, new_title="Batch Round-trip", if_version=version
        )

        assert result["success"] is True, result
        assert rollback.find_by_id(REQ).get_label() == "Batch Round-trip"

    def test_REQ_o00060_G_get_versions_omits_unknown_ids(self, tools):
        """Pinned: an unknown id is omitted, not an error.

        A refresh of a held set must not be defeated by one id that has since
        been renamed or deleted — the known ids still come back, and absence
        is the caller's signal to re-resolve the missing one.
        """
        batch = tools["get_versions"](node_ids=[REQ, UNKNOWN_ID])

        assert UNKNOWN_ID not in batch
        assert batch[REQ] == tools["get_requirement"](req_id=REQ)["version"]

    def test_REQ_o00060_G_get_versions_of_only_unknown_ids_is_empty(self, tools):
        """All-unknown is an empty mapping, still not an error."""
        _unknown_file = make_file_id(NAMESPACE, "spec/nope.md")
        assert tools["get_versions"](node_ids=[UNKNOWN_ID, _unknown_file]) == {}


# ─────────────────────────────────────────────────────────────────────────────
# Reads track mutations rather than serving a stale token
# ─────────────────────────────────────────────────────────────────────────────


class TestVersionsAreLive:
    """Validates REQ-o00060-G:

    The version a read reports follows the node's state; a token read after a
    mutation is the post-mutation one, so a re-read always unblocks a retry.
    """

    def test_REQ_o00060_G_get_requirement_version_changes_after_a_mutation(self, tools, rollback):
        """Read, mutate, re-read: the reported version moved with the state."""
        before = tools["get_requirement"](req_id=REQ)["version"]

        tools["mutate_update_title"](node_id=REQ, new_title="Freshly Retitled", if_version=before)

        after = tools["get_requirement"](req_id=REQ)["version"]
        assert after != before
        assert after == node_version(rollback.find_by_id(REQ))

    def test_REQ_o00060_G_reread_version_unblocks_a_rejected_retry(self, tools, rollback):
        """A stale holder re-reads and its retry is then accepted."""
        stale = tools["get_requirement"](req_id=REQ)["version"]
        tools["mutate_update_title"](node_id=REQ, new_title="Writer A", if_version=stale)

        rejected = tools["mutate_update_title"](node_id=REQ, new_title="Writer B", if_version=stale)
        assert rejected["success"] is False

        fresh = tools["get_requirement"](req_id=REQ)["version"]
        retried = tools["mutate_update_title"](node_id=REQ, new_title="Writer B", if_version=fresh)

        assert retried["success"] is True, retried
        assert rollback.find_by_id(REQ).get_label() == "Writer B"

    def test_REQ_o00060_G_get_versions_tracks_a_mutation(self, tools, rollback):
        """The cheap path is not a cache: it moves with the graph too."""
        before = tools["get_versions"](node_ids=[REQ])[REQ]

        tools["mutate_change_status"](node_id=REQ, new_status="Deprecated", if_version=before)

        after = tools["get_versions"](node_ids=[REQ])[REQ]
        assert after != before
        assert after == node_version(rollback.find_by_id(REQ))

    def test_REQ_o00060_G_file_version_changes_when_the_file_composition_changes(
        self, tools, rollback
    ):
        """Moving a requirement out re-versions the file it left."""
        before = tools["get_requirement"](req_id=REQ)["file_version"]
        target_version = tools["get_node"](node_id=TARGET_FILE)["version"]
        node_ver = tools["get_requirement"](req_id=REQ)["version"]

        moved = tools["mutate_move_node_to_file"](
            node_id=REQ,
            target_file_id=TARGET_FILE,
            if_version=node_ver,
            if_source_file_version=before,
            if_target_version=target_version,
        )
        assert moved["success"] is True, moved

        assert tools["get_node"](node_id=SOURCE_FILE)["version"] != before
        assert tools["get_requirement"](req_id=REQ)["file_version"] == node_version(
            rollback.find_by_id(TARGET_FILE)
        )
