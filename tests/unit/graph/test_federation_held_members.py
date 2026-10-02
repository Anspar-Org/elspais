"""A member graph belongs to the one federation that holds it.

Validates REQ-d00200-I+J+K: a federation refuses a member graph another
federation already holds, naming the reads through the holding federation;
every member of a built federation, and of a clone, is held; and a question
about one member is put to the federation through a read restricted to that
member's namespace.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from elspais.config import get_config
from elspais.graph.factory import _build_repository, build_graph
from elspais.graph.federated import FederatedGraph, FederationError, RepoEntry
from elspais.graph.GraphNode import GraphNode, NodeKind

FIX = Path(__file__).parents[2] / "fixtures" / "e2e-integrates"


def _git_init(repo: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)


def _copy_integrates(base: Path) -> tuple[Path, Path]:
    """Copy the app + library fixture under ``base``; return (app, library)."""
    dest = base / "proj"
    shutil.copytree(FIX, dest)
    app, library = dest / "app", dest / "library"
    _git_init(library)
    _git_init(app)
    return app, library


def _federate(app: Path) -> FederatedGraph:
    return build_graph(
        config=get_config(None, app), repo_root=app, scan_code=False, scan_tests=False
    )


def _bare(repo: Path) -> RepoEntry:
    """One repository's graph, built bare and held by no federation."""
    config = get_config(None, repo)
    graph, _ = _build_repository(config, repo, scan_code=False, scan_tests=False)
    return RepoEntry(name=repo.name, graph=graph, config=config, repo_root=repo)


@pytest.fixture(scope="module")
def integrates_fed(tmp_path_factory) -> FederatedGraph:
    """A two-member federation (APP integrates LIB), read-only."""
    app, _library = _copy_integrates(tmp_path_factory.mktemp("held_members"))
    return _federate(app)


class TestMembersAreHeldOnce:
    """Validates REQ-d00200-J+K: one federation holds each member graph."""

    # Verifies: REQ-d00200-J+K
    def test_REQ_d00200_K_every_built_member_is_refused_a_second_federation(self, integrates_fed):
        """Every member a build federated is held; wrapping any again is refused."""
        fed = integrates_fed
        entries = list(fed.iter_repos())
        assert {e.namespace for e in entries} == {"APP", "LIB"}

        for entry in entries:
            with pytest.raises(FederationError, match=f"'{entry.namespace}'.*already held"):
                FederatedGraph.from_single(entry.graph, entry.config, entry.repo_root)

    # Verifies: REQ-d00200-K
    def test_REQ_d00200_K_refusal_names_the_reads_through_the_holder(self, integrates_fed):
        """The refusal names the way to reach the member instead."""
        entry = next(e for e in integrates_fed.iter_repos() if e.namespace == "LIB")
        replay = RepoEntry(
            name=entry.name, graph=entry.graph, config=entry.config, repo_root=entry.repo_root
        )
        with pytest.raises(FederationError) as excinfo:
            FederatedGraph([replay])
        message = str(excinfo.value)
        assert "'LIB'" in message
        assert "iter_repos()" in message
        assert "namespace" in message

    # Verifies: REQ-d00200-J+K
    def test_REQ_d00200_J_a_fresh_bare_graph_is_accepted_once(self, tmp_path):
        """A graph no federation holds is accepted, and then it is held."""
        _app, library = _copy_integrates(tmp_path)
        entry = _bare(library)

        first = FederatedGraph.from_single(entry.graph, entry.config, entry.repo_root)
        assert first.find_by_id("LIB-d00007") is not None

        with pytest.raises(FederationError, match="'LIB'.*already held"):
            FederatedGraph.from_single(entry.graph, entry.config, entry.repo_root)

    # Verifies: REQ-d00200-J+K
    def test_REQ_d00200_J_a_refused_federation_holds_none_of_its_members(self, tmp_path):
        """A federation refused for one held member does not hold the others.

        Every member is judged before any is recorded, so the fresh graph
        offered alongside a held one is still free afterwards.
        """
        app, library = _copy_integrates(tmp_path)
        held = _bare(library)
        holder = FederatedGraph.from_single(held.graph, held.config, held.repo_root)
        fresh = _bare(app)

        with pytest.raises(FederationError, match="'LIB'"):
            FederatedGraph([fresh, held])

        accepted = FederatedGraph.from_single(fresh.graph, fresh.config, fresh.repo_root)
        assert accepted.find_by_id("APP-d00001") is not None
        assert holder.find_by_id("LIB-d00007") is not None

    # Verifies: REQ-d00200-J
    def test_REQ_d00200_J_a_clone_holds_its_own_copies(self, integrates_fed):
        """A clone's members are new graphs, held by the clone; the originals stay held."""
        fed = integrates_fed
        clone = fed.clone()

        originals = {e.namespace: e.graph for e in fed.iter_repos()}
        for entry in clone.iter_repos():
            assert entry.graph is not originals[entry.namespace]
            with pytest.raises(FederationError, match="already held"):
                FederatedGraph.from_single(entry.graph, entry.config, entry.repo_root)

        for entry in fed.iter_repos():
            with pytest.raises(FederationError, match="already held"):
                FederatedGraph.from_single(entry.graph, entry.config, entry.repo_root)


class TestNamespaceRestrictedReads:
    """Validates REQ-d00200-I: a member's content is read through its federation."""

    @pytest.mark.parametrize(
        "kind", [NodeKind.REQUIREMENT, NodeKind.ASSERTION, NodeKind.FILE], ids=lambda k: k.value
    )
    # Verifies: REQ-d00200-I
    def test_REQ_d00200_I_nodes_by_kind_restricted_to_one_member(self, integrates_fed, kind):
        fed = integrates_fed
        union: set[str] = set()
        for entry in fed.iter_repos():
            own = {n.id for n in entry.graph.nodes_by_kind(kind)}
            assert own, f"fixture member {entry.namespace} holds no {kind.value}"
            assert {n.id for n in fed.nodes_by_kind(kind, namespace=entry.namespace)} == own
            union |= own
        assert {n.id for n in fed.nodes_by_kind(kind)} == union
        assert {n.id for n in fed.nodes_by_kind(kind, namespace=None)} == union

    @pytest.mark.parametrize("kind", [None, NodeKind.FILE], ids=["default", "file"])
    # Verifies: REQ-d00200-I
    def test_REQ_d00200_I_iter_roots_restricted_to_one_member(self, integrates_fed, kind):
        fed = integrates_fed
        union: set[str] = set()
        for entry in fed.iter_repos():
            own = {n.id for n in entry.graph.iter_roots(kind)}
            assert own
            assert {n.id for n in fed.iter_roots(kind, namespace=entry.namespace)} == own
            union |= own
        assert {n.id for n in fed.iter_roots(kind)} == union

    # Verifies: REQ-d00200-I
    def test_REQ_d00200_I_a_namespace_no_member_declares_reads_nothing(self, integrates_fed):
        fed = integrates_fed
        assert list(fed.nodes_by_kind(NodeKind.REQUIREMENT, namespace="EVS")) == []
        assert list(fed.iter_roots(namespace="EVS")) == []
        assert list(fed.iter_structural_orphans(namespace="EVS")) == []

    # Verifies: REQ-d00200-I
    def test_REQ_d00200_I_structural_orphans_restricted_to_one_member(self, tmp_path):
        """An orphan in one member is reported under that member alone."""
        app, _library = _copy_integrates(tmp_path)
        fed = _federate(app)
        lib = next(e for e in fed.iter_repos() if e.namespace == "LIB")
        orphan = GraphNode(id="LIB-d00500", kind=NodeKind.REQUIREMENT, label="Orphan")
        lib.graph._index[orphan.id] = orphan

        assert "LIB-d00500" in {n.id for n in fed.iter_structural_orphans(namespace="LIB")}
        assert "LIB-d00500" not in {n.id for n in fed.iter_structural_orphans(namespace="APP")}
        assert "LIB-d00500" in {n.id for n in fed.iter_structural_orphans()}
