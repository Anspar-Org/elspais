# Verifies: REQ-d00131-L
"""Tests for ``node_version()`` -- the optimistic-concurrency node version.

A node's version is a content-addressed digest of what the node would look
like on disk: its rendered text plus its outgoing traceability references.
It exists because the requirement content hash (``compute_hash_for_node``)
deliberately ignores title, status, node identity and edges -- all of which
change the file on disk and therefore must invalidate a client's optimistic
lock.

Every class here validates REQ-d00131-L.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from elspais.graph import render
from elspais.graph.factory import build_graph as build_repo_graph
from elspais.graph.GraphNode import NodeKind, make_file_id
from elspais.graph.relations import EdgeKind
from elspais.graph.render import compute_hash_for_node
from tests.core.graph_test_helpers import (
    build_graph,
    make_code_ref,
    make_requirement,
    make_test_ref,
)


def node_version(node) -> str:
    """Resolve ``render.node_version`` at call time.

    Looking the function up lazily keeps a missing implementation a per-test
    failure rather than a module-level ImportError that aborts collection for
    the whole suite. Once ``node_version`` exists this can become a plain
    ``from elspais.graph.render import node_version``.
    """
    return render.node_version(node)


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

_HEX16 = re.compile(r"^[0-9a-f]{16}$")

# Nodes used across the classes below. CODE node ids embed an absolute path,
# so that one is resolved from the graph by suffix rather than hard-coded.
# The namespace the hht-like fixture declares; structural node ids carry it.
NAMESPACE = "REQ"

REQ_WITH_CODE_AND_TESTS = "REQ-d00001"
CODE_NODE_SUFFIX = "database/schema.sql:44"
TEST_NODE = "test:tests/test_auth.py::test_oauth_flow"
SPEC_FILE = make_file_id(NAMESPACE, "spec/dev-impl.md")

# Sentinel accepted by ``_resolve`` in place of a literal node id.
CODE_NODE = "<code-node>"


def _code_node_id(graph) -> str:
    """The id of the fixture CODE node that only REQ-d00003 references."""
    for node in graph.iter_by_kind(NodeKind.CODE):
        if node.id.endswith(CODE_NODE_SUFFIX):
            return node.id
    raise AssertionError(f"no CODE node ending in {CODE_NODE_SUFFIX}")


def _resolve(graph, ref: str):
    """Find a node by id, honouring the CODE_NODE sentinel."""
    node_id = _code_node_id(graph) if ref == CODE_NODE else ref
    node = graph.find_by_id(node_id)
    assert node is not None, f"fixture node {node_id} is missing"
    return node


def _content_hash(node) -> str | None:
    """The requirement content hash, for contrast with the node version."""
    return compute_hash_for_node(node, node.get_field("hash_mode") or "normalized-text")


def _versions_by_id(graph, kind: NodeKind) -> dict[str, str]:
    """Map node id -> version for every node of ``kind`` in ``graph``."""
    return {node.id: node_version(node) for node in graph.iter_by_kind(kind)}


@pytest.fixture(scope="module")
def rebuilt_graph():
    """A second, independent build of the canonical fixture from disk."""
    fg = build_repo_graph(repo_root=FIXTURES_DIR / "hht-like")
    return fg._repos[fg._root_repo].graph


class TestNodeVersionRebuildStability:
    """Validates REQ-d00131-L: a rebuild from unchanged content preserves versions."""

    @pytest.mark.parametrize(
        "kind",
        [
            NodeKind.REQUIREMENT,
            NodeKind.USER_JOURNEY,
            NodeKind.ASSERTION,
            NodeKind.CODE,
            NodeKind.TEST,
            NodeKind.FILE,
        ],
    )
    def test_REQ_d00131_L_rebuild_yields_identical_versions(
        self, canonical_graph, rebuilt_graph, kind
    ):
        """Rebuilding from the same files reproduces every node's version."""
        original = _versions_by_id(canonical_graph, kind)
        assert original, f"fixture has no {kind.name} nodes to compare"
        assert _versions_by_id(rebuilt_graph, kind) == original

    def test_REQ_d00131_L_distinct_requirements_have_distinct_versions(self, canonical_graph):
        """Versions discriminate between nodes -- a constant would satisfy stability."""
        versions = _versions_by_id(canonical_graph, NodeKind.REQUIREMENT)
        assert len(set(versions.values())) == len(versions)


class TestNodeVersionDeterminism:
    """Validates REQ-d00131-L: the version is a pure function of node state."""

    @pytest.mark.parametrize(
        "node_id", [REQ_WITH_CODE_AND_TESTS, CODE_NODE, TEST_NODE, SPEC_FILE, "JNY-001"]
    )
    def test_REQ_d00131_L_repeated_calls_are_stable(self, canonical_graph, node_id):
        """Calling twice on an untouched node returns the same digest."""
        node = _resolve(canonical_graph, node_id)
        assert node_version(node) == node_version(node)

    @pytest.mark.parametrize(
        "node_id", [REQ_WITH_CODE_AND_TESTS, CODE_NODE, TEST_NODE, SPEC_FILE, "JNY-001"]
    )
    def test_REQ_d00131_L_version_is_sixteen_hex_chars(self, canonical_graph, node_id):
        """Every kind yields the same 16-char hex digest shape."""
        assert _HEX16.match(node_version(_resolve(canonical_graph, node_id)))

    def test_REQ_d00131_L_edge_storage_order_does_not_change_version(self):
        """Outgoing edges are canonically sorted, so insertion order is immaterial."""
        parent = {
            "req_id": "REQ-p00001",
            "title": "Parent",
            "level": "PRD",
            "assertions": [{"label": "A", "text": "The system SHALL parent."}],
            "source_path": "spec/a.md",
        }
        child_one = {"level": "OPS", "implements": ["REQ-p00001"], "source_path": "spec/b.md"}
        forward = build_graph(
            make_requirement(**parent),
            make_requirement("REQ-o00001", "First", start_line=1, **child_one),
            make_requirement("REQ-o00002", "Second", start_line=20, **child_one),
        )
        reversed_ = build_graph(
            make_requirement(**parent),
            make_requirement("REQ-o00002", "Second", start_line=1, **child_one),
            make_requirement("REQ-o00001", "First", start_line=20, **child_one),
        )
        forward_parent = forward.find_by_id("REQ-p00001")
        reversed_parent = reversed_.find_by_id("REQ-p00001")

        # Sanity: the two graphs really do store the edges in opposite order.
        def targets(node):
            return [e.target.id for e in node.iter_edges_by_kind(EdgeKind.IMPLEMENTS)]

        assert targets(forward_parent) == list(reversed(targets(reversed_parent)))
        assert node_version(forward_parent) == node_version(reversed_parent)


@pytest.mark.incremental
class TestNodeVersionBumpsOnContentMutation:
    """Validates REQ-d00131-L: every on-disk-visible content change bumps the version.

    Title, status and identity changes are the cases the requirement content
    hash cannot see, so each step also asserts the content hash stays put.
    """

    def test_REQ_d00131_L_version_changes_on_title_edit(self, mutable_graph):
        """A retitled requirement renders differently and so versions differently."""
        node = mutable_graph.find_by_id("REQ-d00001")
        before, before_hash = node_version(node), _content_hash(node)

        mutable_graph.update_title("REQ-d00001", "Authentication Module (revised)")

        assert node_version(node) != before
        assert _content_hash(node) == before_hash

    def test_REQ_d00131_L_version_changes_on_status_change(self, mutable_graph):
        """The status appears on the metadata line, so it participates."""
        node = mutable_graph.find_by_id("REQ-d00002")
        before, before_hash = node_version(node), _content_hash(node)

        mutable_graph.change_status("REQ-d00002", "Draft")

        assert node_version(node) != before
        assert _content_hash(node) == before_hash

    def test_REQ_d00131_L_version_changes_on_assertion_text_edit(self, mutable_graph):
        """Editing assertion text bumps the requirement and the assertion alike."""
        req = mutable_graph.find_by_id("REQ-d00003")
        assertion = mutable_graph.find_by_id("REQ-d00003-A")
        req_before, assertion_before = node_version(req), node_version(assertion)

        mutable_graph.update_assertion("REQ-d00003-A", "The system SHALL log every mutation.")

        assert node_version(req) != req_before
        assert node_version(assertion) != assertion_before

    def test_REQ_d00131_L_version_changes_on_remainder_text_edit(self, mutable_graph):
        """Prose outside the assertions is still rendered, so it counts."""
        req = mutable_graph.find_by_id("REQ-o00001")
        remainder = mutable_graph.find_by_id("REQ-o00001:section:0")
        req_before, remainder_before = node_version(req), node_version(remainder)

        mutable_graph.update_remainder(
            "REQ-o00001:section:0", text="Deployment is gated on a green pipeline."
        )

        assert node_version(req) != req_before
        assert node_version(remainder) != remainder_before

    def test_REQ_d00131_L_version_changes_on_node_rename(self, mutable_graph):
        """The id is rendered in the header line, so renaming changes the version."""
        node = mutable_graph.find_by_id("REQ-o00002")
        before, before_hash = node_version(node), _content_hash(node)

        mutable_graph.rename_node("REQ-o00002", "REQ-o00099")

        renamed = mutable_graph.find_by_id("REQ-o00099")
        assert node_version(renamed) != before
        assert _content_hash(renamed) == before_hash


@pytest.mark.incremental
class TestNodeVersionBumpsOnEdgeMutation:
    """Validates REQ-d00131-L: outgoing traceability edges are part of the version.

    The chain adds an edge REQ-d00002 -> CODE, retargets it, retypes it, then
    deletes it. None of these touch the requirement's content hash.
    """

    def test_REQ_d00131_L_version_changes_on_edge_add(self, mutable_graph):
        """Adding an outgoing IMPLEMENTS edge bumps the source requirement."""
        node = mutable_graph.find_by_id("REQ-d00002")
        before, before_hash = node_version(node), _content_hash(node)
        TestNodeVersionBumpsOnEdgeMutation.pristine = before

        mutable_graph.add_edge(
            source_id=_code_node_id(mutable_graph),
            target_id="REQ-d00002",
            edge_kind=EdgeKind.IMPLEMENTS,
        )

        assert node_version(node) != before
        assert _content_hash(node) == before_hash

    def test_REQ_d00131_L_version_changes_on_edge_target_change(self, mutable_graph):
        """Narrowing the edge to a single assertion is a different reference."""
        node = mutable_graph.find_by_id("REQ-d00002")
        before = node_version(node)

        mutable_graph.change_edge_targets(
            source_id=_code_node_id(mutable_graph),
            target_id="REQ-d00002",
            assertion_targets=["A"],
        )

        assert node_version(node) != before

    def test_REQ_d00131_L_version_changes_on_edge_kind_change(self, mutable_graph):
        """IMPLEMENTS -> VERIFIES is a different reference kind."""
        node = mutable_graph.find_by_id("REQ-d00002")
        before = node_version(node)

        mutable_graph.change_edge_kind(
            source_id=_code_node_id(mutable_graph),
            target_id="REQ-d00002",
            new_kind=EdgeKind.VERIFIES,
        )

        assert node_version(node) != before

    def test_REQ_d00131_L_version_changes_on_edge_delete(self, mutable_graph):
        """Deleting the last chain edge restores the pre-chain version.

        The version is a pure digest of rendered text plus outgoing
        references, not a counter: with the edge gone the requirement is
        byte-identical to its pre-chain self, so the token round-trips to the
        value captured before the edge was added.
        """
        node = mutable_graph.find_by_id("REQ-d00002")
        before = node_version(node)

        mutable_graph.delete_edge(source_id=_code_node_id(mutable_graph), target_id="REQ-d00002")

        assert node_version(node) != before
        assert node_version(node) == self.pristine


class TestNodeVersionPerKindResolution:
    """Validates REQ-d00131-L: each kind resolves its version by its render role."""

    @pytest.mark.parametrize(
        "child_id, owner_id",
        [
            ("REQ-d00001-A", "REQ-d00001"),
            ("REQ-d00001-D", "REQ-d00001"),
            ("REQ-d00001:section:0", "REQ-d00001"),
            ("REQ-d00001:section:1", "REQ-d00001"),
            ("REQ-o00001-B", "REQ-o00001"),
        ],
    )
    def test_REQ_d00131_L_dependent_node_resolves_to_owner_version(
        self, canonical_graph, child_id, owner_id
    ):
        """Nodes rendered by their parent share the parent's version."""
        child = canonical_graph.find_by_id(child_id)
        owner = canonical_graph.find_by_id(owner_id)
        assert node_version(child) == node_version(owner)

    @pytest.mark.parametrize(
        "content, kind, original, edited",
        [
            (
                make_code_ref(["REQ-p00001"], source_path="src/m.py"),
                NodeKind.CODE,
                "# Implements: REQ-p00001",
                "# Implements: REQ-p00001, REQ-p00002",
            ),
            (
                make_test_ref(
                    ["REQ-p00001"], source_path="tests/test_m.py", function_name="test_x"
                ),
                NodeKind.TEST,
                "# Verifies: REQ-p00001",
                "# Verifies: REQ-p00001-A",
            ),
        ],
        ids=["code", "test"],
    )
    def test_REQ_d00131_L_code_and_test_version_tracks_raw_text(
        self, content, kind, original, edited
    ):
        """CODE/TEST versions come from ``raw_text`` and round-trip with it."""
        graph = build_graph(content)
        node = next(graph.iter_by_kind(kind))

        node.set_field("raw_text", original)
        first = node_version(node)

        node.set_field("raw_text", edited)
        assert node_version(node) != first

        node.set_field("raw_text", original)
        assert node_version(node) == first

    def test_REQ_d00131_L_file_version_tracks_path(self):
        """A file's identity is its path, so the same contents at a new path differ."""
        here = build_graph(make_requirement("REQ-p00001", "One", source_path="spec/a.md"))
        there = build_graph(make_requirement("REQ-p00001", "One", source_path="spec/b.md"))

        assert node_version(here.find_by_id(make_file_id(NAMESPACE, "spec/a.md"))) != node_version(
            there.find_by_id(make_file_id(NAMESPACE, "spec/b.md"))
        )

    def test_REQ_d00131_L_file_version_tracks_child_order(self):
        """Reordering CONTAINS children rewrites the file, so the version moves."""
        first_then_second = build_graph(
            make_requirement("REQ-p00001", "One", source_path="spec/a.md", start_line=1),
            make_requirement("REQ-p00002", "Two", source_path="spec/a.md", start_line=20),
        )
        second_then_first = build_graph(
            make_requirement("REQ-p00002", "Two", source_path="spec/a.md", start_line=1),
            make_requirement("REQ-p00001", "One", source_path="spec/a.md", start_line=20),
        )

        _file_a = make_file_id(NAMESPACE, "spec/a.md")
        assert node_version(first_then_second.find_by_id(_file_a)) != node_version(
            second_then_first.find_by_id(make_file_id(NAMESPACE, "spec/a.md"))
        )

    def test_REQ_d00131_L_file_version_ignores_child_content(self):
        """Same path, same child ids in the same order -- same file version."""
        plain = build_graph(
            make_requirement(
                "REQ-p00001",
                "One",
                source_path="spec/a.md",
                assertions=[{"label": "A", "text": "The system SHALL do one thing."}],
            ),
        )
        rewritten = build_graph(
            make_requirement(
                "REQ-p00001",
                "A Completely Different Title",
                status="Draft",
                source_path="spec/a.md",
                assertions=[{"label": "A", "text": "The system SHALL do something else."}],
            ),
        )

        # The requirements differ...
        assert node_version(plain.find_by_id("REQ-p00001")) != node_version(
            rewritten.find_by_id("REQ-p00001")
        )
        # ...but the file's identity and composition do not.
        assert node_version(plain.find_by_id(make_file_id(NAMESPACE, "spec/a.md"))) == node_version(
            rewritten.find_by_id(make_file_id(NAMESPACE, "spec/a.md"))
        )


@pytest.mark.incremental
class TestFileVersionIsCompositionOnly:
    """Validates REQ-d00131-L: file versions track identity and composition only."""

    def test_REQ_d00131_L_file_version_stable_when_child_prose_edited(self, mutable_graph):
        """Editing prose inside a contained requirement leaves the file version alone."""
        spec_file = mutable_graph.find_by_id(SPEC_FILE)
        req = mutable_graph.find_by_id("REQ-d00001")
        file_before, req_before = node_version(spec_file), node_version(req)

        mutable_graph.update_remainder(
            "REQ-d00001:section:1", text="Rewritten rationale for the authentication module."
        )

        assert node_version(req) != req_before
        assert node_version(spec_file) == file_before

    def test_REQ_d00131_L_file_version_changes_when_child_moves_between_files(self, mutable_graph):
        """Moving a requirement out changes the composition of both files."""
        source_file = mutable_graph.find_by_id(SPEC_FILE)
        target_file = mutable_graph.find_by_id(make_file_id(NAMESPACE, "spec/ops-deploy.md"))
        source_before, target_before = node_version(source_file), node_version(target_file)

        mutable_graph.move_node_to_file("REQ-d00003", make_file_id(NAMESPACE, "spec/ops-deploy.md"))

        assert node_version(source_file) != source_before
        assert node_version(target_file) != target_before

    def test_REQ_d00131_L_file_version_changes_on_file_rename(self, mutable_graph):
        """The path is part of the file's identity."""
        before = node_version(mutable_graph.find_by_id(make_file_id(NAMESPACE, "spec/glossary.md")))

        mutable_graph.rename_file(make_file_id(NAMESPACE, "spec/glossary.md"), "spec/terms.md")

        _terms_file = make_file_id(NAMESPACE, "spec/terms.md")
        assert node_version(mutable_graph.find_by_id(_terms_file)) != before


@pytest.fixture
def private_graph():
    """A throwaway build of the canonical fixture, safe to mutate and undo.

    These tests exercise undo itself, so they must not run against the
    session-scoped ``canonical_graph``: an undo that fails to restore state
    would leave every later test in the session reading a corrupted graph.
    ``mutable_graph`` is unusable for the same reason -- its teardown restores
    the graph *by undoing*, which is the mechanism under test.
    """
    fg = build_repo_graph(repo_root=FIXTURES_DIR / "hht-like")
    return fg._repos[fg._root_repo].graph


def _delete_assertion(graph, node_id: str) -> None:
    graph.delete_assertion(node_id)


def _delete_remainder(graph, node_id: str) -> None:
    graph.delete_remainder(node_id)


class TestUndoRestoresRenderedText:
    """Validates REQ-d00131-L: undo returns a node to the version it had.

    A node's version is a digest of its rendered text, so an undo that
    restores content but not the *order* that content renders in leaves the
    node at a different version than the one the client locked against --
    the graph looks reverted while the file it would write does not match.
    """

    @pytest.mark.parametrize(
        "delete, target",
        [
            pytest.param(_delete_assertion, "REQ-o00002-D", id="last-assertion"),
            pytest.param(_delete_assertion, "REQ-o00002-B", id="middle-assertion-compacts"),
            pytest.param(_delete_remainder, "REQ-o00002:section:1", id="remainder-section"),
        ],
    )
    def test_REQ_d00131_L_delete_then_undo_restores_requirement(
        self, private_graph, delete, target
    ):
        """Deleting a child of a requirement and undoing renders identically."""
        requirement = private_graph.find_by_id("REQ-o00002")
        before_text = render.render_node(requirement)
        before_version = node_version(requirement)

        delete(private_graph, target)
        private_graph.undo_last()

        restored = private_graph.find_by_id("REQ-o00002")
        assert render.render_node(restored) == before_text
        assert node_version(restored) == before_version

    def test_REQ_d00131_L_delete_contains_edge_then_undo_restores_file(self, private_graph):
        """A CONTAINS edge carries the position its target renders at."""
        spec_file = private_graph.find_by_id(SPEC_FILE)
        before_text = render.render_file(spec_file)
        before_version = node_version(spec_file)

        private_graph.delete_edge(source_id="REQ-d00001", target_id=SPEC_FILE)
        private_graph.undo_last()

        restored = private_graph.find_by_id(SPEC_FILE)
        assert render.render_file(restored) == before_text
        assert node_version(restored) == before_version
