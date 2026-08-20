# Validates REQ-p00060-D, REQ-p00060-E
# Validates REQ-o00062-A, REQ-o00062-B, REQ-o00062-C, REQ-o00062-D
# Validates REQ-o00062-E, REQ-o00062-F, REQ-o00062-G, REQ-o00062-H
# Validates REQ-o00063-A
# Validates REQ-d00065-A, REQ-d00065-B, REQ-d00065-C, REQ-d00065-D, REQ-d00065-E
"""Tests for MCP mutation tools.

Tests REQ-o00062: MCP Graph Mutation Tools
Tests REQ-o00063: File Mutation Tools
Tests REQ-d00065: Mutation Tool Delegation

All mutation tools must:
- Delegate to TraceGraph mutation methods (REQ-o00062-D, REQ-d00065-D)
- Return MutationEntry for audit (REQ-o00062-E)
- Require confirm=True for destructive operations (REQ-o00062-F)
"""

from pathlib import Path

import pytest

from elspais.config.schema import ElspaisConfig
from elspais.graph import GraphNode, NodeKind
from elspais.graph.builder import TraceGraph
from elspais.graph.GraphNode import make_file_id
from elspais.graph.reference_faults import ReferenceFault
from elspais.graph.relations import EdgeKind
from tests.core.graph_test_helpers import grammar_for

# The namespace these hand-built graphs use -- a structural id carries the
# namespace of the repository holding the node.
NAMESPACE = "REQ"


def file_id(relative_path: str) -> str:
    """FILE node id for a path in the test repository."""
    return make_file_id(NAMESPACE, relative_path)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mutation_graph():
    """Create a TraceGraph with mutation support for testing."""
    graph = TraceGraph(repo_root=Path("/test/repo"), _resolver=grammar_for(NAMESPACE))

    # Create PRD requirement with assertions
    prd_node = GraphNode(
        id="REQ-p00001",
        kind=NodeKind.REQUIREMENT,
        label="Platform Security",
    )
    prd_node._content = {
        "level": "PRD",
        "status": "Active",
        "hash": "abc12345",
        "body": "The platform shall be secure.",
    }

    # Add assertions
    assertion_a = GraphNode(
        id="REQ-p00001-A",
        kind=NodeKind.ASSERTION,
        label="SHALL encrypt all data at rest",
    )
    assertion_a._content = {"label": "A", "text": "SHALL encrypt all data at rest"}
    prd_node.link(assertion_a, EdgeKind.STRUCTURES)

    assertion_b = GraphNode(
        id="REQ-p00001-B",
        kind=NodeKind.ASSERTION,
        label="SHALL use TLS 1.3 for transit",
    )
    assertion_b._content = {"label": "B", "text": "SHALL use TLS 1.3 for transit"}
    prd_node.link(assertion_b, EdgeKind.STRUCTURES)

    # Create OPS requirement that implements PRD
    ops_node = GraphNode(
        id="REQ-o00001",
        kind=NodeKind.REQUIREMENT,
        label="Database Encryption",
    )
    ops_node._content = {
        "level": "OPS",
        "status": "Active",
        "hash": "def67890",
        "body": "Database encryption operations.",
    }

    # Link PRD -> OPS
    prd_node.link(ops_node, EdgeKind.IMPLEMENTS)

    # Build graph
    graph._roots = [prd_node]
    graph._index = {
        "REQ-p00001": prd_node,
        "REQ-p00001-A": assertion_a,
        "REQ-p00001-B": assertion_b,
        "REQ-o00001": ops_node,
    }

    return graph


def _federate(graph):
    """Wrap a hand-built TraceGraph as a default-config federation-of-one.

    The mutation helpers are annotated FederatedGraph and resolve per-node
    config through graph.config_for(). A live-graph RepoEntry must carry a
    config naming the project, so the wrapper holds the defaults under the
    fixture's namespace; target normalization is a no-op for the bare
    assertion labels these tests pass, so the wrapped graph behaves exactly
    as the bare TraceGraph did.
    """
    from elspais.config import config_defaults
    from elspais.graph.federated import FederatedGraph, RepoEntry

    config = config_defaults()
    config["project"]["name"] = "test"
    config["project"]["namespace"] = NAMESPACE
    entry = RepoEntry(name="test", graph=graph, config=config, repo_root=Path("/test/repo"))
    return FederatedGraph([entry], root_repo="test")


# ─────────────────────────────────────────────────────────────────────────────
# Test: Node Mutations - REQ-o00062-A
# ─────────────────────────────────────────────────────────────────────────────


class TestMutateRenameNode:
    """Tests for mutate_rename_node() tool."""

    def test_REQ_d00065_A_delegates_to_graph_rename_node(self, mutation_graph):
        """REQ-d00065-A: Delegates to graph.rename_node()."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_rename_node

        result = _mutate_rename_node(mutation_graph, "REQ-o00001", "REQ-o00099")

        assert result["success"] is True
        # Verify node was renamed in graph
        assert mutation_graph.find_by_id("REQ-o00099") is not None
        assert mutation_graph.find_by_id("REQ-o00001") is None

    def test_REQ_o00062_E_returns_mutation_entry(self, mutation_graph):
        """REQ-o00062-E: Returns MutationEntry for audit."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_rename_node

        result = _mutate_rename_node(mutation_graph, "REQ-o00001", "REQ-o00099")

        assert "mutation" in result
        mutation = result["mutation"]
        assert mutation["operation"] == "rename_node"
        assert mutation["target_id"] == "REQ-o00001"
        assert "before_state" in mutation
        assert "after_state" in mutation

    # Verifies: REQ-o00062-A
    def test_rename_nonexistent_node_returns_error(self, mutation_graph):
        """Renaming non-existent node returns error."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_rename_node

        result = _mutate_rename_node(mutation_graph, "REQ-NONEXISTENT", "REQ-NEW")

        assert result["success"] is False
        assert "error" in result

    # Verifies: REQ-d00205-C
    @pytest.mark.parametrize(
        ("new_id", "stored_id", "note"),
        [
            # A padding variant the owning repo's grammar parses is stored
            # in its canonical spelling, and the rewrite is disclosed.
            ("REQ-o99", "REQ-o00099", "(normalized: REQ-o99 -> REQ-o00099)"),
            # Case and padding variation together: matching admits both in
            # any part of an identifier, and rendering emits the one
            # canonical spelling.
            ("req-P99", "REQ-p00099", "(normalized: req-P99 -> REQ-p00099)"),
            # An id the grammar has no opinion on (a journey id) is stored
            # exactly as given, with nothing to disclose.
            ("JNY-legacy-name", "JNY-legacy-name", None),
        ],
    )
    def test_new_id_canonicalized_under_owning_grammar(
        self, mutation_graph, new_id, stored_id, note
    ):
        """New ids the grammar parses store canonically; others store as given."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_rename_node

        result = _mutate_rename_node(_federate(mutation_graph), "REQ-o00001", new_id)

        assert result["success"] is True
        assert mutation_graph.find_by_id(stored_id) is not None
        if stored_id != new_id:
            # The given spelling must not survive alongside the canonical one.
            assert mutation_graph.find_by_id(new_id) is None
        if note:
            assert note in result["message"]
        else:
            assert "(normalized:" not in result["message"]

    # Verifies: REQ-d00205-C
    def test_bare_graph_rename_attempts_no_normalization(self, mutation_graph):
        """A graph without per-repo configs offers no grammar to normalize under.

        The bare TraceGraph has no config_for, so a padding variant is
        stored exactly as given rather than under a guessed grammar.
        """
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_rename_node

        result = _mutate_rename_node(mutation_graph, "REQ-o00001", "REQ-o99")

        assert result["success"] is True
        assert mutation_graph.find_by_id("REQ-o99") is not None
        assert mutation_graph.find_by_id("REQ-o00099") is None
        assert "(normalized:" not in result["message"]


class TestMutateUpdateTitle:
    """Tests for mutate_update_title() tool."""

    # Verifies: REQ-o00062-A
    def test_delegates_to_graph_update_title(self, mutation_graph):
        """Delegates to graph.update_title()."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_update_title

        result = _mutate_update_title(mutation_graph, "REQ-p00001", "Updated Platform Security")

        assert result["success"] is True
        node = mutation_graph.find_by_id("REQ-p00001")
        assert node.get_label() == "Updated Platform Security"

    # Verifies: REQ-o00062-E
    def test_returns_mutation_entry(self, mutation_graph):
        """Returns MutationEntry for audit."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_update_title

        result = _mutate_update_title(mutation_graph, "REQ-p00001", "New Title")

        assert "mutation" in result
        mutation = result["mutation"]
        assert mutation["operation"] == "update_title"


class TestMutateChangeStatus:
    """Tests for mutate_change_status() tool."""

    # Verifies: REQ-o00062-A
    def test_delegates_to_graph_change_status(self, mutation_graph):
        """Delegates to graph.change_status()."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_change_status

        result = _mutate_change_status(mutation_graph, "REQ-p00001", "Deprecated")

        assert result["success"] is True
        node = mutation_graph.find_by_id("REQ-p00001")
        assert node.status == "Deprecated"

    # Verifies: REQ-o00062-E
    def test_returns_mutation_entry(self, mutation_graph):
        """Returns MutationEntry for audit."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_change_status

        result = _mutate_change_status(mutation_graph, "REQ-p00001", "Draft")

        assert "mutation" in result
        assert result["mutation"]["operation"] == "change_status"

    # Verifies: REQ-o00062-U
    # The single-word positive control is test_delegates_to_graph_change_status
    # above ("Deprecated" succeeds).
    @pytest.mark.parametrize("bad_status", ["In Progress", "Done!"])
    def test_refuses_multi_word_status(self, mutation_graph, bad_status):
        """A status the parser cannot read back as one word is refused before
        delegation, naming the violated constraint."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_change_status

        result = _mutate_change_status(mutation_graph, "REQ-p00001", bad_status)

        assert result["success"] is False
        assert "single word" in result["error"]
        assert bad_status in result["error"]
        node = mutation_graph.find_by_id("REQ-p00001")
        assert node.status == "Active"


class TestMutateAddRequirement:
    """Tests for mutate_add_requirement() tool."""

    def test_REQ_d00065_B_delegates_to_graph_add_requirement(self, mutation_graph):
        """REQ-d00065-B: Delegates to graph.add_requirement()."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_add_requirement

        result = _mutate_add_requirement(
            mutation_graph,
            req_id="REQ-d00001",
            title="New DEV Requirement",
            level="DEV",
            status="Draft",
            parent_id="REQ-o00001",
            edge_kind="IMPLEMENTS",
        )

        assert result["success"] is True
        node = mutation_graph.find_by_id("REQ-d00001")
        assert node is not None
        assert node.get_label() == "New DEV Requirement"

    # Verifies: REQ-o00062-E
    def test_returns_mutation_entry(self, mutation_graph):
        """Returns MutationEntry for audit."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_add_requirement

        result = _mutate_add_requirement(
            mutation_graph,
            req_id="REQ-d00002",
            title="Another Requirement",
            level="DEV",
            status="Draft",
        )

        assert "mutation" in result
        assert result["mutation"]["operation"] == "add_requirement"

    # Verifies: REQ-d00205-C
    def test_id_grammar_cannot_read_is_refused(self, mutation_graph):
        """An id the root repo's grammar cannot read is refused, not stored."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_add_requirement

        result = _mutate_add_requirement(
            _federate(mutation_graph),
            req_id="BANANA-42",
            title="Unreadable Id",
            level="dev",
        )

        assert result["success"] is False
        assert "Invalid requirement id" in result["error"]
        # Nothing was added under the refused spelling.
        assert mutation_graph.find_by_id("BANANA-42") is None

    # Verifies: REQ-d00205-C
    def test_variant_id_spelling_stored_canonically_with_disclosure(self, mutation_graph):
        """A variant spelling the grammar admits is stored canonically.

        Matching admits case and padding variation, rendering emits the one
        canonical spelling, and the rewrite is disclosed in the message.
        """
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_add_requirement

        result = _mutate_add_requirement(
            _federate(mutation_graph),
            req_id="req-P00077",
            title="Variant Spelling",
            level="prd",
        )

        assert result["success"] is True
        assert mutation_graph.find_by_id("REQ-p00077") is not None
        # The given spelling must not survive alongside the canonical one.
        assert mutation_graph.find_by_id("req-P00077") is None
        assert "(normalized: req-P00077 -> REQ-p00077)" in result["message"]

    # Verifies: REQ-o00062-U
    def test_refuses_multi_word_status(self, mutation_graph):
        """A status the parser cannot read back as one word is refused, and
        nothing is stored."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_add_requirement

        result = _mutate_add_requirement(
            mutation_graph,
            req_id="REQ-d00043",
            title="Bad Status",
            level="DEV",
            status="In Progress",
        )

        assert result["success"] is False
        assert "single word" in result["error"]
        assert mutation_graph.find_by_id("REQ-d00043") is None

    # Verifies: REQ-o00062-U
    def test_undeclared_level_is_refused_naming_declared_levels(self, mutation_graph):
        """A level the project does not declare is refused, naming the levels."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_add_requirement

        result = _mutate_add_requirement(
            _federate(mutation_graph),
            req_id="REQ-d00042",
            title="Bad Level",
            level="BANANA",
        )

        assert result["success"] is False
        assert "Unknown level" in result["error"]
        for declared in ("dev", "ops", "prd"):
            assert declared in result["error"]
        assert mutation_graph.find_by_id("REQ-d00042") is None

    # Verifies: REQ-o00062-U
    def test_level_membership_is_case_insensitive(self, mutation_graph):
        """A display-case level is accepted against lowercase-keyed levels."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_add_requirement

        result = _mutate_add_requirement(
            _federate(mutation_graph),
            req_id="REQ-d00043",
            title="Display Case Level",
            level="DEV",
        )

        assert result["success"] is True
        assert mutation_graph.find_by_id("REQ-d00043") is not None


class TestMutateDeleteRequirement:
    """Tests for mutate_delete_requirement() tool."""

    def test_REQ_o00062_F_requires_confirm_true(self, mutation_graph):
        """REQ-o00062-F: Requires confirm=True for destructive operations."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_delete_requirement

        # Without confirm=True, should NOT delete
        result = _mutate_delete_requirement(mutation_graph, "REQ-o00001", confirm=False)

        assert result["success"] is False
        assert "confirm" in result["error"].lower()
        # Node should still exist
        assert mutation_graph.find_by_id("REQ-o00001") is not None

    def test_REQ_d00065_C_deletes_when_confirmed(self, mutation_graph):
        """REQ-d00065-C: Calls graph.delete_requirement() only if confirm=True."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_delete_requirement

        result = _mutate_delete_requirement(mutation_graph, "REQ-o00001", confirm=True)

        assert result["success"] is True
        assert mutation_graph.find_by_id("REQ-o00001") is None

    # Verifies: REQ-o00062-E
    def test_returns_mutation_entry(self, mutation_graph):
        """Returns MutationEntry for audit."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_delete_requirement

        result = _mutate_delete_requirement(mutation_graph, "REQ-o00001", confirm=True)

        assert "mutation" in result
        assert result["mutation"]["operation"] == "delete_requirement"


# ─────────────────────────────────────────────────────────────────────────────
# Test: Assertion Mutations - REQ-o00062-B
# ─────────────────────────────────────────────────────────────────────────────


class TestMutateAddAssertion:
    """Tests for mutate_add_assertion() tool."""

    # Verifies: REQ-o00062-B
    def test_delegates_to_graph_add_assertion(self, mutation_graph):
        """Delegates to graph.add_assertion()."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_add_assertion

        result = _mutate_add_assertion(
            mutation_graph,
            req_id="REQ-p00001",
            text="SHALL log all access attempts",
        )

        assert result["success"] is True
        assertion = mutation_graph.find_by_id(result["assertion_id"])
        assert assertion is not None
        assert assertion.get_label() == "SHALL log all access attempts"
        assert result["label"] == assertion.get_field("label")
        assert result["message"] == f"Added assertion {result['assertion_id']}"

    # Verifies: REQ-o00062-E
    def test_returns_mutation_entry(self, mutation_graph):
        """Returns MutationEntry for audit."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_add_assertion

        result = _mutate_add_assertion(mutation_graph, "REQ-p00001", "New assertion text")

        assert "mutation" in result
        assert result["mutation"]["operation"] == "add_assertion"


class TestMutateUpdateAssertion:
    """Tests for mutate_update_assertion() tool."""

    # Verifies: REQ-o00062-B
    def test_delegates_to_graph_update_assertion(self, mutation_graph):
        """Delegates to graph.update_assertion()."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_update_assertion

        result = _mutate_update_assertion(
            mutation_graph, "REQ-p00001-A", "SHALL encrypt ALL data at rest using AES-256"
        )

        assert result["success"] is True
        assertion = mutation_graph.find_by_id("REQ-p00001-A")
        assert "AES-256" in assertion.get_label()

    # Verifies: REQ-o00062-E
    def test_returns_mutation_entry(self, mutation_graph):
        """Returns MutationEntry for audit."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_update_assertion

        result = _mutate_update_assertion(mutation_graph, "REQ-p00001-A", "Updated text")

        assert "mutation" in result
        assert result["mutation"]["operation"] == "update_assertion"


class TestMutateDeleteAssertion:
    """Tests for mutate_delete_assertion() tool."""

    # Verifies: REQ-o00062-F
    def test_requires_confirm_true(self, mutation_graph):
        """Requires confirm=True for destructive operations."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_delete_assertion

        result = _mutate_delete_assertion(mutation_graph, "REQ-p00001-A", confirm=False)

        assert result["success"] is False
        assert mutation_graph.find_by_id("REQ-p00001-A") is not None

    # Verifies: REQ-o00062-B
    def test_deletes_when_confirmed(self, mutation_graph):
        """Deletes assertion when confirmed."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_delete_assertion

        # Store original assertion ID before deletion
        original_text = mutation_graph.find_by_id("REQ-p00001-A").get_label()

        result = _mutate_delete_assertion(mutation_graph, "REQ-p00001-A", confirm=True)

        assert result["success"] is True
        # After deletion with compact=True, REQ-p00001-A now has what was REQ-p00001-B
        # Check that the original assertion text is no longer at A
        if mutation_graph.find_by_id("REQ-p00001-A"):
            # A still exists but has different content (was B, now compacted to A)
            assert mutation_graph.find_by_id("REQ-p00001-A").get_label() != original_text

    # Verifies: REQ-o00062-E
    def test_returns_mutation_entry(self, mutation_graph):
        """Returns MutationEntry for audit."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_delete_assertion

        result = _mutate_delete_assertion(mutation_graph, "REQ-p00001-A", confirm=True)

        assert "mutation" in result
        assert result["mutation"]["operation"] == "delete_assertion"


class TestMutateRenameAssertion:
    """Tests for mutate_rename_assertion() tool."""

    # Verifies: REQ-o00062-B
    def test_delegates_to_graph_rename_assertion(self, mutation_graph):
        """Delegates to graph.rename_assertion()."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_rename_assertion

        result = _mutate_rename_assertion(mutation_graph, "REQ-p00001-A", "X")

        assert result["success"] is True
        assert mutation_graph.find_by_id("REQ-p00001-X") is not None
        assert mutation_graph.find_by_id("REQ-p00001-A") is None

    # Verifies: REQ-o00062-E
    def test_returns_mutation_entry(self, mutation_graph):
        """Returns MutationEntry for audit."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_rename_assertion

        result = _mutate_rename_assertion(mutation_graph, "REQ-p00001-A", "X")

        assert "mutation" in result
        assert result["mutation"]["operation"] == "rename_assertion"

    # Verifies: REQ-d00205-C
    def test_full_assertion_id_normalized_to_bare_label(self, mutation_graph):
        """A new_label given as the parent's full assertion id stores bare.

        The label is stored bare and rendered verbatim, so "REQ-p00001-D"
        must land as label "D" -- and the rewrite must be disclosed.
        """
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_rename_assertion

        result = _mutate_rename_assertion(_federate(mutation_graph), "REQ-p00001-A", "REQ-p00001-D")

        assert result["success"] is True
        assert mutation_graph.find_by_id("REQ-p00001-D") is not None
        assert mutation_graph.find_by_id("REQ-p00001-A") is None
        assert mutation_graph.find_by_id("REQ-p00001-D").get_field("label") == "D"
        assert "(normalized: REQ-p00001-D -> D)" in result["message"]

    # Verifies: REQ-d00205-C
    def test_lowercase_label_variant_normalized_to_canonical_case(self, mutation_graph):
        """An admitted case variant of a label stores the canonical spelling.

        Under the uppercase label style, "d" names the same label as "D";
        the stored label is the canonical one and the rewrite is disclosed.
        """
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_rename_assertion

        result = _mutate_rename_assertion(_federate(mutation_graph), "REQ-p00001-A", "d")

        assert result["success"] is True
        renamed = mutation_graph.find_by_id("REQ-p00001-D")
        assert renamed is not None
        assert renamed.get_field("label") == "D"
        assert "(normalized: d -> D)" in result["message"]

    # Verifies: REQ-d00205-C
    def test_bare_canonical_label_produces_no_normalization_note(self, mutation_graph):
        """A label already bare and canonical is stored silently."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_rename_assertion

        result = _mutate_rename_assertion(_federate(mutation_graph), "REQ-p00001-A", "D")

        assert result["success"] is True
        assert mutation_graph.find_by_id("REQ-p00001-D") is not None
        assert "(normalized:" not in result["message"]


# ─────────────────────────────────────────────────────────────────────────────
# Test: Remainder (Section) Mutations - REQ-o00062-H
# ─────────────────────────────────────────────────────────────────────────────


def _build_remainder_graph() -> TraceGraph:
    """Build a graph with a requirement that has REMAINDER sections.

    Mirrors the fixture in tests/core/test_remainder_mutations.py so the
    section ID format (e.g. REQ-p00001:section:1) is produced by the real
    GraphBuilder rather than hand-constructed.
    """
    from elspais.graph.builder import GraphBuilder
    from elspais.graph.parsers import ParsedContent

    builder = GraphBuilder(namespace="REQ", resolver=grammar_for("REQ"))
    builder.add_parsed_content(
        ParsedContent(
            content_type="requirement",
            parsed_data={
                "id": "REQ-p00001",
                "title": "Requirement with Sections",
                "level": "PRD",
                "status": "Active",
                "assertions": [],
                "implements": [],
                "refines": [],
                "sections": [
                    {"heading": "preamble", "content": "Some preamble text", "line": 2},
                    {"heading": "Rationale", "content": "Why we need this", "line": 4},
                ],
            },
            start_line=1,
            end_line=5,
            raw_text="## REQ-p00001: Requirement with Sections",
        )
    )
    return builder.build()


class TestMutateRemainder:
    """Tests for remainder (section) mutation tool wrappers.

    Validates REQ-o00062-H: Section (remainder) mutations include
    add_remainder, update_remainder, delete_remainder.
    """

    def test_REQ_o00062_H_add_remainder_creates_section(self):
        """REQ-o00062-H: _mutate_add_remainder adds a queryable section."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_add_remainder

        graph = _build_remainder_graph()

        result = _mutate_add_remainder(graph, "REQ-p00001", "Notes", "Some notes text")

        assert result["success"] is True
        new_id = result["mutation"]["target_id"]
        node = graph.find_by_id(new_id)
        assert node is not None
        assert node.kind == NodeKind.REMAINDER
        assert node.get_field("heading") == "Notes"
        assert node.get_field("text") == "Some notes text"

    def test_REQ_o00062_E_add_remainder_returns_mutation_entry(self):
        """REQ-o00062-E: _mutate_add_remainder returns a MutationEntry."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_add_remainder

        graph = _build_remainder_graph()

        result = _mutate_add_remainder(graph, "REQ-p00001", "Notes", "Text")

        assert "mutation" in result
        assert result["mutation"]["operation"] == "add_remainder"

    def test_REQ_d00065_D_update_remainder_changes_text(self):
        """REQ-d00065-D: _mutate_update_remainder delegates and stores new text."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_update_remainder

        graph = _build_remainder_graph()
        section = graph.find_by_id("REQ-p00001:section:1")
        assert section.get_field("text") != "Updated rationale"

        result = _mutate_update_remainder(graph, "REQ-p00001:section:1", text="Updated rationale")

        assert result["success"] is True
        assert section.get_field("text") == "Updated rationale"

    def test_REQ_o00062_H_update_remainder_changes_heading(self):
        """REQ-o00062-H: _mutate_update_remainder updates the heading field."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_update_remainder

        graph = _build_remainder_graph()
        section = graph.find_by_id("REQ-p00001:section:1")
        assert section.get_field("heading") != "New Heading"

        result = _mutate_update_remainder(graph, "REQ-p00001:section:1", heading="New Heading")

        assert result["success"] is True
        assert section.get_field("heading") == "New Heading"

    def test_REQ_o00062_E_update_remainder_returns_mutation_entry(self):
        """REQ-o00062-E: _mutate_update_remainder returns a MutationEntry."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_update_remainder

        graph = _build_remainder_graph()

        result = _mutate_update_remainder(graph, "REQ-p00001:section:1", text="x")

        assert "mutation" in result
        assert result["mutation"]["operation"] == "update_remainder"

    def test_REQ_o00062_H_delete_remainder_removes_section(self):
        """REQ-o00062-H: _mutate_delete_remainder removes the section."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_delete_remainder

        graph = _build_remainder_graph()
        assert graph.find_by_id("REQ-p00001:section:1") is not None

        result = _mutate_delete_remainder(graph, "REQ-p00001:section:1")

        assert result["success"] is True
        assert graph.find_by_id("REQ-p00001:section:1") is None

    def test_REQ_o00062_E_delete_remainder_returns_mutation_entry(self):
        """REQ-o00062-E: _mutate_delete_remainder returns a MutationEntry."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_delete_remainder

        graph = _build_remainder_graph()

        result = _mutate_delete_remainder(graph, "REQ-p00001:section:1")

        assert "mutation" in result
        assert result["mutation"]["operation"] == "delete_remainder"

    def test_REQ_o00062_H_update_nonexistent_returns_error(self):
        """REQ-o00062-H: Updating a missing node returns error, not an exception."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_update_remainder

        graph = _build_remainder_graph()

        result = _mutate_update_remainder(graph, "REQ-p00001:section:99", text="x")

        assert result["success"] is False
        assert "error" in result

    def test_REQ_o00062_H_update_non_remainder_returns_error(self):
        """REQ-o00062-H: Updating a non-REMAINDER node returns error."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_update_remainder

        graph = _build_remainder_graph()

        # REQ-p00001 is a REQUIREMENT, not a REMAINDER
        result = _mutate_update_remainder(graph, "REQ-p00001", text="x")

        assert result["success"] is False
        assert "error" in result

    def test_REQ_o00062_H_delete_nonexistent_returns_error(self):
        """REQ-o00062-H: Deleting a missing node returns error, not an exception."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_delete_remainder

        graph = _build_remainder_graph()

        result = _mutate_delete_remainder(graph, "REQ-p00001:section:99")

        assert result["success"] is False
        assert "error" in result


# ─────────────────────────────────────────────────────────────────────────────
# Test: Edge Mutations - REQ-o00062-C
# ─────────────────────────────────────────────────────────────────────────────


class TestMutateAddEdge:
    """Tests for mutate_add_edge() tool."""

    # Verifies: REQ-o00062-C
    def test_delegates_to_graph_add_edge(self, mutation_graph):
        """Delegates to graph.add_edge()."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_add_edge

        # Add a new DEV requirement first
        dev_node = GraphNode(
            id="REQ-d00001",
            kind=NodeKind.REQUIREMENT,
            label="DEV Requirement",
        )
        dev_node._content = {"level": "DEV", "status": "Draft"}
        mutation_graph._index["REQ-d00001"] = dev_node

        result = _mutate_add_edge(
            mutation_graph,
            source_id="REQ-d00001",
            target_id="REQ-o00001",
            edge_kind="IMPLEMENTS",
        )

        assert result["success"] is True

    # Verifies: REQ-o00062-E
    def test_returns_mutation_entry(self, mutation_graph):
        """Returns MutationEntry for audit."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_add_edge

        # Setup node
        dev_node = GraphNode(
            id="REQ-d00002",
            kind=NodeKind.REQUIREMENT,
            label="Another DEV",
        )
        dev_node._content = {"level": "DEV", "status": "Draft"}
        mutation_graph._index["REQ-d00002"] = dev_node

        result = _mutate_add_edge(mutation_graph, "REQ-d00002", "REQ-o00001", "IMPLEMENTS")

        assert "mutation" in result
        assert result["mutation"]["operation"] == "add_edge"

    # Verifies: REQ-o00062-C, REQ-d00205-C
    def test_normalizes_full_assertion_ids_to_bare_labels(self, mutation_graph):
        """Full assertion IDs like REQ-o00001-A are normalized to bare labels.

        No config is handed to _mutate_add_edge: production must resolve it
        from the graph itself (graph.config_for(target_id), REQ-d00205-C),
        so the graph's RepoEntry is what carries the config here.
        """
        pytest.importorskip("mcp")
        from elspais.graph.federated import FederatedGraph
        from elspais.mcp.server import _mutate_add_edge

        # Setup: add assertion to target so the ID is valid
        target = mutation_graph.find_by_id("REQ-o00001")
        target.set_field("assertions", {"A": "Test assertion"})

        dev_node = GraphNode(
            id="REQ-d00003",
            kind=NodeKind.REQUIREMENT,
            label="DEV with assertion ref",
        )
        dev_node._content = {"level": "DEV", "status": "Draft"}
        mutation_graph._index["REQ-d00003"] = dev_node

        # Config matching the default REQ-{type}{component} pattern. Validated
        # the way a file on disk is, so this fixture cannot describe a
        # repository the tool would refuse to load.
        config = {
            "project": {"name": "TestProject", "namespace": "REQ"},
            "levels": {
                "p": {"rank": 1, "letter": "p", "implements": ["p"]},
                "o": {"rank": 2, "letter": "o", "implements": ["o", "p"]},
                "d": {"rank": 3, "letter": "d", "implements": ["d", "o", "p"]},
            },
            "id-patterns": {
                "canonical": "{namespace}-{type}{component}",
                "component": {"style": "numeric", "digits": 5, "leading_zeros": True},
                "assertions": {"label_style": "uppercase"},
            },
        }
        ElspaisConfig.model_validate(config)

        # Wrap AFTER all nodes are indexed -- federation ownership is
        # snapshotted at construction, and config_for(target_id) reads it.
        fed = FederatedGraph.from_single(mutation_graph, config, Path("/test/repo"))

        result = _mutate_add_edge(
            fed,
            source_id="REQ-d00003",
            target_id="REQ-o00001",
            edge_kind="IMPLEMENTS",
            assertion_targets=["REQ-o00001-A"],
        )

        assert result["success"] is True
        # Verify the edge has bare label "A", not the full "REQ-o00001-A"
        edges = [
            e
            for e in target.iter_outgoing_edges()
            if e.kind == EdgeKind.IMPLEMENTS and e.target.id == "REQ-d00003"
        ]
        assert len(edges) == 1
        assert edges[0].assertion_targets == ["A"]
        # The stored form differs from what the caller wrote, so the
        # mutation result must disclose the rewrite naming both spellings.
        assert "(normalized: REQ-o00001-A -> A)" in result["message"]

    # Verifies: REQ-d00205-C
    def test_already_bare_label_produces_no_normalization_note(self, mutation_graph):
        """A target already in canonical form is stored unchanged, silently.

        The disclosure suffix exists to flag a rewrite; emitting it when
        nothing changed would train callers to ignore it.
        """
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_add_edge

        dev_node = GraphNode(
            id="REQ-d00004",
            kind=NodeKind.REQUIREMENT,
            label="DEV with bare label ref",
        )
        dev_node._content = {"level": "DEV", "status": "Draft"}
        mutation_graph._index["REQ-d00004"] = dev_node

        result = _mutate_add_edge(
            _federate(mutation_graph),
            source_id="REQ-d00004",
            target_id="REQ-p00001",
            edge_kind="IMPLEMENTS",
            assertion_targets=["A"],
        )

        assert result["success"] is True
        assert "(normalized:" not in result["message"]


class TestMutateChangeEdgeKind:
    """Tests for mutate_change_edge_kind() tool."""

    # Verifies: REQ-o00062-C
    def test_delegates_to_graph_change_edge_kind(self, mutation_graph):
        """Delegates to graph.change_edge_kind()."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_change_edge_kind

        # Change IMPLEMENTS to REFINES
        result = _mutate_change_edge_kind(mutation_graph, "REQ-o00001", "REQ-p00001", "REFINES")

        assert result["success"] is True

    # Verifies: REQ-o00062-E
    def test_returns_mutation_entry(self, mutation_graph):
        """Returns MutationEntry for audit."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_change_edge_kind

        result = _mutate_change_edge_kind(mutation_graph, "REQ-o00001", "REQ-p00001", "REFINES")

        assert "mutation" in result
        assert result["mutation"]["operation"] == "change_edge_kind"


class TestMutateChangeEdgeTargets:
    """Tests for mutate_change_edge_targets() tool.

    Validates REQ-o00062-C: Edge mutation tools include change_targets action.
    """

    def test_REQ_o00062_C_delegates_to_graph_change_edge_targets(self, mutation_graph):
        """REQ-o00062-C: Delegates to graph.change_edge_targets()."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_change_edge_targets

        # REQ-o00001 implements REQ-p00001 (edge exists from fixture)
        # Change assertion targets to just ["A"]
        result = _mutate_change_edge_targets(
            _federate(mutation_graph), "REQ-o00001", "REQ-p00001", ["A"]
        )

        assert result["success"] is True
        # Verify the edge's assertion_targets is ["A"]
        parent = mutation_graph.find_by_id("REQ-p00001")
        edges = [
            e
            for e in parent.iter_outgoing_edges()
            if e.kind == EdgeKind.IMPLEMENTS and e.target.id == "REQ-o00001"
        ]
        assert len(edges) == 1
        assert edges[0].assertion_targets == ["A"]

    def test_REQ_o00062_E_returns_mutation_entry(self, mutation_graph):
        """REQ-o00062-E: Returns MutationEntry for audit."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_change_edge_targets

        result = _mutate_change_edge_targets(
            _federate(mutation_graph), "REQ-o00001", "REQ-p00001", ["B"]
        )

        assert "mutation" in result
        mutation = result["mutation"]
        assert mutation["operation"] == "change_edge_targets"

    # Verifies: REQ-d00205-C
    def test_normalizes_full_assertion_ids_to_bare_labels(self, mutation_graph):
        """Full assertion IDs are normalized to bare labels at mutation time.

        render_save spells the stored label verbatim into the Implements:
        line, so an unnormalized full ID would reach the spec file corrupted.
        """
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_change_edge_targets

        # REQ-o00001 implements REQ-p00001 (edge exists from fixture)
        result = _mutate_change_edge_targets(
            _federate(mutation_graph), "REQ-o00001", "REQ-p00001", ["REQ-p00001-A"]
        )

        assert result["success"] is True
        # Verify the edge stores the bare label "A", not the full ID
        parent = mutation_graph.find_by_id("REQ-p00001")
        edges = [
            e
            for e in parent.iter_outgoing_edges()
            if e.kind == EdgeKind.IMPLEMENTS and e.target.id == "REQ-o00001"
        ]
        assert len(edges) == 1
        assert edges[0].assertion_targets == ["A"]
        # Verifies: REQ-d00205-C -- the rewrite is disclosed in the result.
        assert "(normalized: REQ-p00001-A -> A)" in result["message"]

    # Verifies: REQ-d00205-C
    @pytest.mark.parametrize("spelling", ["REQ-p00001-a", "req-P00001-A"])
    def test_case_variant_spellings_normalize_to_bare_label(self, mutation_graph, spelling):
        """Case variants of the full assertion id normalize to the bare label.

        Matching admits case variation in any part of an identifier --
        label and namespace/type alike -- so both spellings store the one
        canonical label, and each rewrite is disclosed.
        """
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_change_edge_targets

        result = _mutate_change_edge_targets(
            _federate(mutation_graph), "REQ-o00001", "REQ-p00001", [spelling]
        )

        assert result["success"] is True
        parent = mutation_graph.find_by_id("REQ-p00001")
        edges = [
            e
            for e in parent.iter_outgoing_edges()
            if e.kind == EdgeKind.IMPLEMENTS and e.target.id == "REQ-o00001"
        ]
        assert len(edges) == 1
        assert edges[0].assertion_targets == ["A"]
        assert f"(normalized: {spelling} -> A)" in result["message"]

    # Verifies: REQ-d00205-C
    def test_bare_label_produces_no_normalization_note(self, mutation_graph):
        """A bare canonical label passes through with no disclosure suffix."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_change_edge_targets

        result = _mutate_change_edge_targets(
            _federate(mutation_graph), "REQ-o00001", "REQ-p00001", ["A"]
        )

        assert result["success"] is True
        assert "(normalized:" not in result["message"]

    # Verifies: REQ-o00062-C
    def test_change_edge_targets_error_no_edge(self, mutation_graph):
        """Returns error when no edge exists between nodes."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_change_edge_targets

        # REQ-p00001-A is an assertion, no edge from it to REQ-o00001
        result = _mutate_change_edge_targets(
            _federate(mutation_graph), "REQ-p00001-A", "REQ-o00001", ["A"]
        )

        assert result["success"] is False
        assert "error" in result


class TestMutateDeleteEdge:
    """Tests for mutate_delete_edge() tool."""

    # Verifies: REQ-o00062-F
    def test_requires_confirm_true(self, mutation_graph):
        """Requires confirm=True for destructive operations."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_delete_edge

        result = _mutate_delete_edge(mutation_graph, "REQ-o00001", "REQ-p00001", confirm=False)

        assert result["success"] is False

    # Verifies: REQ-o00062-C
    def test_deletes_when_confirmed(self, mutation_graph):
        """Deletes edge when confirmed."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_delete_edge

        result = _mutate_delete_edge(mutation_graph, "REQ-o00001", "REQ-p00001", confirm=True)

        assert result["success"] is True

    # Verifies: REQ-o00062-E
    def test_returns_mutation_entry(self, mutation_graph):
        """Returns MutationEntry for audit."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_delete_edge

        result = _mutate_delete_edge(mutation_graph, "REQ-o00001", "REQ-p00001", confirm=True)

        assert "mutation" in result
        assert result["mutation"]["operation"] == "delete_edge"


class TestMutateFixBrokenReference:
    """Tests for mutate_fix_broken_reference() tool."""

    # Verifies: REQ-o00062-C
    def test_delegates_to_graph_fix_broken_reference(self, mutation_graph):
        """Delegates to graph.fix_broken_reference()."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_fix_broken_reference

        # Create a broken reference scenario first
        mutation_graph._broken_references.append(
            ReferenceFault(
                source_id="REQ-o00001",
                target_id="REQ-MISSING",
                edge_kind=EdgeKind.IMPLEMENTS,
            )
        )

        result = _mutate_fix_broken_reference(
            mutation_graph, "REQ-o00001", "REQ-MISSING", "REQ-p00001"
        )

        assert result["success"] is True

    # Verifies: REQ-o00062-E
    def test_returns_mutation_entry(self, mutation_graph):
        """Returns MutationEntry for audit."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_fix_broken_reference

        mutation_graph._broken_references.append(
            ReferenceFault(
                source_id="REQ-o00001",
                target_id="REQ-BAD",
                edge_kind=EdgeKind.IMPLEMENTS,
            )
        )

        result = _mutate_fix_broken_reference(mutation_graph, "REQ-o00001", "REQ-BAD", "REQ-p00001")

        assert "mutation" in result
        assert result["mutation"]["operation"] == "fix_broken_reference"

    # Verifies: REQ-d00205-C
    def test_claimed_variant_target_normalized_with_disclosure(self, mutation_graph):
        """A variant spelling a member's grammar claims stores canonically.

        "req-P00001" is claimed by the REQ member's grammar, so the new
        target is stored and reported as "REQ-p00001" -- and because that
        node exists, the reference actually resolves rather than staying
        broken under the variant spelling. The rewrite is disclosed.
        """
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_fix_broken_reference

        mutation_graph._broken_references.append(
            ReferenceFault(
                source_id="REQ-o00001",
                target_id="REQ-MISSING",
                edge_kind=EdgeKind.IMPLEMENTS,
            )
        )

        result = _mutate_fix_broken_reference(
            _federate(mutation_graph), "REQ-o00001", "REQ-MISSING", "req-P00001"
        )

        assert result["success"] is True
        assert result["mutation"]["after_state"]["new_target_id"] == "REQ-p00001"
        assert result["mutation"]["after_state"]["fixed"] is True
        assert "(normalized: req-P00001 -> REQ-p00001)" in result["message"]

    # Verifies: REQ-d00205-C
    def test_target_no_member_claims_stays_as_given(self, mutation_graph):
        """A new target no member's grammar claims is stored as given.

        No grammar claims "OTHER-x00001", so there is nothing to normalize
        under: the spelling the caller wrote is what is stored, the
        reference stays broken and is reported, and no normalization is
        disclosed -- guessing a grammar would silently respell the
        reference.
        """
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_fix_broken_reference

        mutation_graph._broken_references.append(
            ReferenceFault(
                source_id="REQ-o00001",
                target_id="REQ-MISSING",
                edge_kind=EdgeKind.IMPLEMENTS,
            )
        )

        result = _mutate_fix_broken_reference(
            _federate(mutation_graph), "REQ-o00001", "REQ-MISSING", "OTHER-x00001"
        )

        assert result["success"] is True
        assert result["mutation"]["after_state"]["new_target_id"] == "OTHER-x00001"
        assert result["mutation"]["after_state"]["still_broken"] is True
        assert "(normalized:" not in result["message"]


# ─────────────────────────────────────────────────────────────────────────────
# Test: File Mutations - REQ-o00063
# ─────────────────────────────────────────────────────────────────────────────


class TestMutateMoveNodeToFile:
    """Tests for mutate_move_node_to_file() tool.

    Validates REQ-o00063: File mutation tools include move_node_to_file action.
    """

    @pytest.fixture
    def file_graph(self, mutation_graph):
        """Extend mutation_graph with FILE nodes and CONTAINS wiring."""
        graph = mutation_graph

        file1 = GraphNode(file_id("spec/main.md"), NodeKind.FILE, label="main.md")
        file1.set_field("relative_path", "spec/main.md")
        graph._index[file_id("spec/main.md")] = file1
        graph._roots.append(file1)

        req = graph.find_by_id("REQ-p00001")
        edge = file1.link(req, EdgeKind.CONTAINS)
        edge.metadata["render_order"] = 0.0

        file2 = GraphNode(file_id("spec/other.md"), NodeKind.FILE, label="other.md")
        file2.set_field("relative_path", "spec/other.md")
        graph._index[file_id("spec/other.md")] = file2
        graph._roots.append(file2)

        return graph

    def test_REQ_o00063_A_delegates_to_graph_move_node_to_file(self, file_graph):
        """REQ-o00063-A: Delegates to graph.move_node_to_file()."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_move_node_to_file

        result = _mutate_move_node_to_file(file_graph, "REQ-p00001", file_id("spec/other.md"))

        assert result["success"] is True
        assert "mutation" in result
        # Verify req is now under the target file
        req = file_graph.find_by_id("REQ-p00001")
        assert req.file_node().id == file_id("spec/other.md")

    def test_REQ_o00063_A_move_error_no_file_parent(self, file_graph):
        """REQ-o00063-A: Moving a node without a FILE parent returns error."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_move_node_to_file

        # Create a standalone node with no FILE ancestor
        orphan = GraphNode("REQ-d00099", NodeKind.REQUIREMENT, label="Orphan")
        orphan._content = {"level": "DEV", "status": "Draft"}
        file_graph._index["REQ-d00099"] = orphan

        result = _mutate_move_node_to_file(file_graph, "REQ-d00099", file_id("spec/other.md"))

        assert result["success"] is False
        assert "error" in result


class TestMutateRenameFile:
    """Tests for mutate_rename_file() tool.

    Validates REQ-o00063: File mutation tools include rename_file action.
    """

    @pytest.fixture
    def file_graph(self, mutation_graph):
        """Extend mutation_graph with a FILE node."""
        graph = mutation_graph

        file1 = GraphNode(file_id("spec/main.md"), NodeKind.FILE, label="main.md")
        file1.set_field("relative_path", "spec/main.md")
        graph._index[file_id("spec/main.md")] = file1
        graph._roots.append(file1)

        req = graph.find_by_id("REQ-p00001")
        edge = file1.link(req, EdgeKind.CONTAINS)
        edge.metadata["render_order"] = 0.0

        return graph

    def test_REQ_o00063_A_delegates_to_graph_rename_file(self, file_graph):
        """REQ-o00063-A: Delegates to graph.rename_file()."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_rename_file

        result = _mutate_rename_file(file_graph, file_id("spec/main.md"), "spec/renamed.md")

        assert result["success"] is True
        assert "mutation" in result
        # Verify the new ID is findable
        assert file_graph.find_by_id(file_id("spec/renamed.md")) is not None
        # Old ID should be gone
        assert file_graph.find_by_id(file_id("spec/main.md")) is None

    def test_REQ_o00063_A_rename_error_not_found(self, file_graph):
        """REQ-o00063-A: Renaming a nonexistent file returns error."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_rename_file

        result = _mutate_rename_file(file_graph, file_id("spec/nonexistent.md"), "spec/new.md")

        assert result["success"] is False
        assert "error" in result

    # Verifies: REQ-o00062-M
    @pytest.mark.parametrize(
        "bad_path",
        [
            "../escape.md",
            "/etc/evil.md",
            # validate_new_spec_path sees this as under spec/ and matching
            # *.md, so the '..'-segment guard is the ONLY defense here.
            "spec/../../evil.md",
        ],
    )
    def test_traversal_or_absolute_path_refused(self, file_graph, bad_path):
        """A path with '..' segments or an absolute path is refused."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_rename_file

        result = _mutate_rename_file(file_graph, file_id("spec/main.md"), bad_path)

        assert result["success"] is False
        assert "must not contain '..' or be absolute" in result["error"]
        # The file was not renamed.
        assert file_graph.find_by_id(file_id("spec/main.md")) is not None

    # Verifies: REQ-o00062-M
    def test_path_outside_spec_tree_refused(self, file_graph):
        """A destination outside the configured spec directories is refused."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_rename_file

        result = _mutate_rename_file(
            _federate(file_graph), file_id("spec/main.md"), "src/notaspec.md"
        )

        assert result["success"] is False
        assert "not under any configured spec directory" in result["error"]
        assert file_graph.find_by_id(file_id("spec/main.md")) is not None

    # Verifies: REQ-o00062-M
    def test_legitimate_rename_passes_spec_path_validation(self, file_graph):
        """A rename inside the configured spec tree passes the path guard.

        The bare-graph success test above never reaches
        validate_new_spec_path (no config); this one does, so it fails if
        the guard starts over-refusing legitimate destinations.
        """
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_rename_file

        result = _mutate_rename_file(
            _federate(file_graph), file_id("spec/main.md"), "spec/renamed.md"
        )

        assert result["success"] is True
        assert file_graph.find_by_id(file_id("spec/renamed.md")) is not None


# ─────────────────────────────────────────────────────────────────────────────
# Test: Undo Operations - REQ-o00062-G
# ─────────────────────────────────────────────────────────────────────────────


class TestUndoLastMutation:
    """Tests for undo_last_mutation() tool."""

    def test_REQ_o00062_G_delegates_to_graph_undo_last(self, mutation_graph):
        """REQ-o00062-G: Reverses mutations using graph.undo_last()."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_update_title, _undo_last_mutation

        # Make a mutation
        _mutate_update_title(mutation_graph, "REQ-p00001", "Changed Title")
        assert mutation_graph.find_by_id("REQ-p00001").get_label() == "Changed Title"

        # Undo it
        result = _undo_last_mutation(mutation_graph)

        assert result["success"] is True
        assert mutation_graph.find_by_id("REQ-p00001").get_label() == "Platform Security"

    # Verifies: REQ-o00062-G
    def test_returns_undone_mutation_entry(self, mutation_graph):
        """Returns the mutation that was undone."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_update_title, _undo_last_mutation

        _mutate_update_title(mutation_graph, "REQ-p00001", "New Title")
        result = _undo_last_mutation(mutation_graph)

        assert "mutation" in result
        assert result["mutation"]["operation"] == "update_title"


class TestUndoToMutation:
    """Tests for undo_to_mutation() tool."""

    def test_REQ_o00062_G_delegates_to_graph_undo_to(self, mutation_graph):
        """REQ-o00062-G: Reverses mutations using graph.undo_to()."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import (
            _mutate_change_status,
            _mutate_update_title,
            _undo_to_mutation,
        )

        # Make multiple mutations
        _mutate_update_title(mutation_graph, "REQ-p00001", "Title 1")
        result2 = _mutate_update_title(mutation_graph, "REQ-p00001", "Title 2")
        mutation_id = result2["mutation"]["id"]  # We'll undo back to (and including) this
        _mutate_change_status(mutation_graph, "REQ-p00001", "Deprecated")

        # Undo back to (and including) second mutation
        # This undoes mutations 3 and 2, leaving mutation 1
        result = _undo_to_mutation(mutation_graph, mutation_id)

        assert result["success"] is True
        assert result["mutations_undone"] == 2
        # Should have the state after first mutation (Title 1, Active)
        node = mutation_graph.find_by_id("REQ-p00001")
        assert node.get_label() == "Title 1"
        assert node.status == "Active"


class TestGetMutationLog:
    """Tests for get_mutation_log() tool."""

    # Verifies: REQ-o00062-E
    def test_returns_mutation_history(self, mutation_graph):
        """Returns list of mutation entries."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import (
            _get_mutation_log,
            _mutate_change_status,
            _mutate_update_title,
        )

        _mutate_update_title(mutation_graph, "REQ-p00001", "Title Change")
        _mutate_change_status(mutation_graph, "REQ-p00001", "Draft")

        result = _get_mutation_log(mutation_graph)

        assert "mutations" in result
        assert len(result["mutations"]) == 2

    # Verifies: REQ-o00062-E
    def test_respects_limit_parameter(self, mutation_graph):
        """Respects limit parameter."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import (
            _get_mutation_log,
            _mutate_change_status,
            _mutate_update_title,
        )

        _mutate_update_title(mutation_graph, "REQ-p00001", "Title 1")
        _mutate_update_title(mutation_graph, "REQ-p00001", "Title 2")
        _mutate_change_status(mutation_graph, "REQ-p00001", "Draft")

        result = _get_mutation_log(mutation_graph, limit=2)

        assert len(result["mutations"]) == 2

    # Verifies: REQ-o00062-E, REQ-o00062-N
    def test_window_is_the_most_recent_entries_newest_first(self, mutation_graph):
        """A truncated window holds the MOST RECENT entries, newest first.

        The pre-fix behavior (CUR-1829) returned the OLDEST ``limit`` entries
        while claiming to be the most recent, so ``current_tip`` derived from
        that window named a mid-log entry the tip guard would reject.
        """
        pytest.importorskip("mcp")
        from elspais.mcp.server import _get_mutation_log, _mutate_update_title

        applied_ids = []
        for i in range(1, 5):
            result = _mutate_update_title(mutation_graph, "REQ-p00001", f"Title {i}")
            applied_ids.append(result["mutation"]["id"])

        result = _get_mutation_log(mutation_graph, limit=2)

        # The last two applied mutations, newest first.
        assert [m["id"] for m in result["mutations"]] == [applied_ids[3], applied_ids[2]]
        assert result["count"] == 2
        assert result["total"] == 4
        assert result["current_tip"] == applied_ids[3]

    # Verifies: REQ-o00062-N
    def test_current_tip_is_the_id_the_tip_guard_accepts(self, mutation_graph):
        """One get_mutation_log read hands an agent a guard-passing tip,
        even when the window is truncated below the full pending count."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import (
            _get_mutation_log,
            _guard_mutation_tip,
            _mutate_update_title,
        )

        for i in range(3):
            _mutate_update_title(mutation_graph, "REQ-p00001", f"Title {i}")

        result = _get_mutation_log(mutation_graph, limit=1)

        assert _guard_mutation_tip(mutation_graph, result["current_tip"]) is None
        # Any other entry in the log is NOT the tip and must be refused.
        non_tip = list(mutation_graph.mutation_log.iter_entries())[0].id
        assert non_tip != result["current_tip"]
        conflict = _guard_mutation_tip(mutation_graph, non_tip)
        assert conflict is not None
        assert conflict["code"] == "mutation_log_conflict"

    # Verifies: REQ-o00062-E
    def test_empty_log_reports_empty_tip_and_zero_total(self, mutation_graph):
        """An empty log yields current_tip == "" (the wire spelling of
        'nothing pending') and total == 0."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _get_mutation_log

        result = _get_mutation_log(mutation_graph)

        assert result["mutations"] == []
        assert result["count"] == 0
        assert result["total"] == 0
        assert result["current_tip"] == ""


# ─────────────────────────────────────────────────────────────────────────────
# Test: Inspection Tools
# ─────────────────────────────────────────────────────────────────────────────


class TestGetOrphanedNodes:
    """Tests for get_orphaned_nodes() tool."""

    # Verifies: REQ-o00060-A
    def test_returns_orphaned_node_list(self, mutation_graph):
        """Returns list of orphaned nodes."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _get_orphaned_nodes

        # Delete edge to create orphan
        mutation_graph._orphaned_ids.add("REQ-o00001")

        result = _get_orphaned_nodes(mutation_graph)

        assert "orphans" in result
        assert "REQ-o00001" in [o["id"] for o in result["orphans"]]


class TestGetBrokenReferences:
    """Tests for get_broken_references() tool."""

    # Verifies: REQ-o00060-A
    def test_returns_broken_reference_list(self, mutation_graph):
        """Returns list of broken references."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _get_broken_references

        mutation_graph._broken_references.append(
            ReferenceFault(
                source_id="REQ-o00001",
                target_id="REQ-MISSING",
                edge_kind=EdgeKind.IMPLEMENTS,
            )
        )

        result = _get_broken_references(mutation_graph)

        assert "broken_references" in result
        assert len(result["broken_references"]) == 1
        assert result["broken_references"][0]["source_id"] == "REQ-o00001"
        assert result["broken_references"][0]["target_id"] == "REQ-MISSING"


# ─────────────────────────────────────────────────────────────────────────────
# Test: Serialization - REQ-d00064
# ─────────────────────────────────────────────────────────────────────────────


class TestSerializeMutationEntry:
    """Tests for serialize_mutation_entry() function."""

    # Verifies: REQ-d00064-B
    def test_serializes_all_fields(self, mutation_graph):
        """Serializes all MutationEntry fields."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_update_title

        result = _mutate_update_title(mutation_graph, "REQ-p00001", "New Title")

        mutation = result["mutation"]
        assert "id" in mutation
        assert "operation" in mutation
        assert "target_id" in mutation
        assert "before_state" in mutation
        assert "after_state" in mutation
        assert "timestamp" in mutation

    # Verifies: REQ-d00064-B
    def test_handles_affects_hash_flag(self, mutation_graph):
        """Includes affects_hash flag for assertion mutations."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_update_assertion

        result = _mutate_update_assertion(mutation_graph, "REQ-p00001-A", "New assertion text")

        mutation = result["mutation"]
        assert "affects_hash" in mutation
        assert mutation["affects_hash"] is True
