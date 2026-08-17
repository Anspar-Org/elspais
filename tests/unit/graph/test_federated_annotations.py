# Verifies: REQ-d00269-C, REQ-d00269-D
"""Code and test annotations name the identifiers of a whole federation.

Annotating code and tests is where cross-repository evidence is most
naturally authored, so a scanner that knows only its own repository's
identifier grammar drops that evidence before any edge exists.  These
tests build real, on-disk federations with disjoint namespaces and hold
the scan to two obligations: an identifier any member owns is recognised
and wired to the requirement it names, and a reference no member claims
is reported rather than discarded.
"""

from __future__ import annotations

from pathlib import Path

from elspais.graph.factory import build_graph
from elspais.graph.GraphNode import NodeKind
from elspais.graph.relations import EdgeKind
from tests.federation_repos import make_repo

_ASSERTIONS = """
### Assertions

A. The system shall alpha.

B. The system shall beta.
"""

_TEST_SCANNING = """
[scanning.test]
enabled = true
"""


def _with_assertions(repo: Path) -> None:
    """Give the repository's single requirement two assertions."""
    spec = repo / "spec" / "reqs.md"
    spec.write_text(
        spec.read_text().replace(
            "The system shall do a thing.\n",
            "The system shall do a thing.\n" + _ASSERTIONS,
        ),
        encoding="utf-8",
    )


def _append_config(repo: Path, text: str) -> None:
    config = repo / ".elspais.toml"
    config.write_text(config.read_text() + text, encoding="utf-8")


def _federation(
    tmp_path: Path,
    *,
    code: str = "",
    tests: str = "",
) -> Path:
    """Build a two-repository federation and return the consuming repo.

    ``b`` (namespace ``BBB``) owns ``BBB-d00002``; ``d`` (namespace
    ``DDD``) declares ``b`` as an associate and owns ``DDD-d00005``.  The
    namespaces are disjoint, so an identifier resolves in exactly one of
    them.
    """
    library = make_repo(tmp_path, "b", namespace="BBB", req_id="BBB-d00002")
    consumer = make_repo(
        tmp_path,
        "d",
        namespace="DDD",
        req_id="DDD-d00005",
        associates={"b": "../b"},
        associate_namespaces={"b": "BBB"},
    )
    for repo in (library, consumer):
        _with_assertions(repo)
        _append_config(repo, _TEST_SCANNING)
    if code:
        (consumer / "src").mkdir()
        (consumer / "src" / "impl.py").write_text(code, encoding="utf-8")
    if tests:
        (consumer / "tests").mkdir()
        (consumer / "tests" / "test_x.py").write_text(tests, encoding="utf-8")
    return consumer


def _drop_associates(repo: Path) -> None:
    """Remove the repository's associate declarations, leaving it alone."""
    config = repo / ".elspais.toml"
    kept: list[str] = []
    skipping = False
    for line in config.read_text().splitlines():
        if line.startswith("[associates."):
            skipping = True
        elif line.startswith("["):
            skipping = False
        if not skipping:
            kept.append(line)
    config.write_text("\n".join(kept) + "\n", encoding="utf-8")


_COVERAGE_KINDS = {EdgeKind.IMPLEMENTS, EdgeKind.VERIFIES}


def _annotators_of(graph, req_id: str, label: str) -> set[str]:
    """IDs of the CODE/TEST nodes covering one *Assertion*.

    A same-repository edge hangs off the owning requirement carrying the
    *Assertion* label, while a cross-repository edge hangs off the
    *Assertion* node itself, so both shapes are read here.
    """
    found: set[str] = set()
    requirement = graph.find_by_id(req_id)
    assert requirement is not None, f"{req_id} is missing from the graph"
    for edge in requirement.iter_outgoing_edges():
        if edge.kind in _COVERAGE_KINDS and label in (edge.assertion_targets or []):
            found.add(edge.target.id)
    assertion = graph.find_by_id(f"{req_id}-{label}")
    if assertion is not None:
        found.update(child.id for child in assertion.iter_children(edge_kinds=_COVERAGE_KINDS))
    return found


class TestSiblingIdentifiersAreRecognised:
    """REQ-d00269-C -- any member's identifier, in any member's annotations."""

    def test_REQ_d00269_C_code_annotation_wires_to_a_sibling_requirement(self, tmp_path):
        consumer = _federation(
            tmp_path,
            code="# Implements: BBB-d00002-A\ndef foreign():\n    pass\n",
        )

        federated = build_graph(repo_root=consumer)
        library = federated._repos["b"].graph

        annotators = _annotators_of(library, "BBB-d00002", "A")
        assert len(annotators) == 1
        assert next(iter(annotators)).startswith("code:")
        assert federated.broken_references() == []

    def test_REQ_d00269_C_test_annotation_wires_to_a_sibling_requirement(self, tmp_path):
        consumer = _federation(
            tmp_path,
            tests="# Verifies: BBB-d00002-B\ndef test_foreign():\n    assert True\n",
        )

        federated = build_graph(repo_root=consumer)
        library = federated._repos["b"].graph

        assert _annotators_of(library, "BBB-d00002", "B") == {"test:tests/test_x.py::test_foreign"}
        assert federated.broken_references() == []

    def test_REQ_d00269_C_sibling_and_local_references_coexist(self, tmp_path):
        """One annotation naming both a sibling's identifier and a local one.

        Both are read out of the same line, so neither grammar can be the
        only one applied to it.
        """
        consumer = _federation(
            tmp_path,
            code=("# Implements: BBB-d00002-A, DDD-d00005-A\n" "def both():\n" "    pass\n"),
        )

        federated = build_graph(repo_root=consumer)

        assert len(_annotators_of(federated._repos["b"].graph, "BBB-d00002", "A")) == 1
        assert len(_annotators_of(federated._repos["d"].graph, "DDD-d00005", "A")) == 1

    def test_REQ_d00269_C_test_name_names_a_sibling_identifier(self, tmp_path):
        """A test function name is an annotation, spelled in underscores."""
        consumer = _federation(
            tmp_path,
            tests="def test_logging_BBB_d00002_B():\n    assert True\n",
        )

        federated = build_graph(repo_root=consumer)

        assert len(_annotators_of(federated._repos["b"].graph, "BBB-d00002", "B")) == 1
        assert federated.broken_references() == []

    def test_REQ_d00269_C_sibling_reference_is_normalized_by_its_owner(self, tmp_path):
        """The claiming repository's grammar decides what the reference means.

        The library labels its *Assertions* in uppercase, so the mis-cased
        reference below is the identifier ``BBB-d00002-A`` written badly.
        Only the library's own grammar can say so; the consumer's grammar
        does not describe the identifier at all and would leave it
        unresolved.
        """
        consumer = _federation(
            tmp_path,
            code="# Implements: BBB-d00002-a\ndef foreign():\n    pass\n",
        )

        federated = build_graph(repo_root=consumer)

        assert len(_annotators_of(federated._repos["b"].graph, "BBB-d00002", "A")) == 1
        assert federated.broken_references() == []


class TestALoneRepositoryIsUnchanged:
    """Widening the grammar is scoped to the federation that asked for it."""

    def test_REQ_d00269_C_lone_repository_does_not_claim_foreign_identifier(self, tmp_path):
        consumer = _federation(
            tmp_path,
            code="# Implements: BBB-d00002-A\ndef foreign():\n    pass\n",
        )
        _drop_associates(consumer)

        federated = build_graph(repo_root=consumer)

        assert [entry.name for entry in federated.iter_repos()] == ["d"]
        # Per REQ-d00269-D, the reference is reported rather than resolved.
        assert [br.target_id for br in federated.broken_references()] == ["BBB-d00002-A"]

    def test_REQ_d00269_C_lone_repository_scans_its_own_annotations_unchanged(self, tmp_path):
        consumer = _federation(
            tmp_path,
            code="# Implements: DDD-d00005-A\ndef local():\n    pass\n",
            tests="# Verifies: DDD-d00005-B\ndef test_local():\n    assert True\n",
        )
        federated_census = _census(build_graph(repo_root=consumer), "d")

        _drop_associates(consumer)
        lone_census = _census(build_graph(repo_root=consumer), "d")

        assert lone_census == federated_census


class TestUnresolvableReferencesAreReported:
    """REQ-d00269-D -- the diagnostic floor beneath cross-repository credit."""

    def test_REQ_d00269_D_unclaimed_reference_carries_its_raw_text(self, tmp_path):
        consumer = _federation(
            tmp_path,
            code="# Implements: ZZZ-d09999-A\ndef nobody():\n    pass\n",
        )

        federated = build_graph(repo_root=consumer)

        broken = federated.broken_references()
        assert [br.target_id for br in broken] == ["ZZZ-d09999-A"]
        assert broken[0].edge_kind == "implements"
        assert broken[0].source_id.startswith("code:")

    def test_REQ_d00269_D_an_unresolvable_test_reference_is_reported(self, tmp_path):
        consumer = _federation(
            tmp_path,
            tests="# Verifies: ZZZ-d09999-B\ndef test_nobody():\n    assert True\n",
        )

        federated = build_graph(repo_root=consumer)

        broken = federated.broken_references()
        assert [br.target_id for br in broken] == ["ZZZ-d09999-B"]
        assert broken[0].edge_kind == "verifies"

    def test_REQ_d00269_D_malformed_local_reference_is_reported(self, tmp_path):
        """The namespace is the repository's own; the rest of it is not an ID."""
        consumer = _federation(
            tmp_path,
            code="# Implements: DDD-nonsense\ndef wrong():\n    pass\n",
        )

        federated = build_graph(repo_root=consumer)

        assert [br.target_id for br in federated.broken_references()] == ["DDD-nonsense"]

    # Verifies: REQ-d00269-E
    def test_REQ_d00269_D_prose_in_the_reference_position_is_still_a_reference(self, tmp_path):
        """Position decides, so prose written where a reference belongs is one.

        Nothing about the target's shape is consulted (REQ-d00269-E), so a
        sentence opening a comment with a *Traceability* keyword is read as
        a reference and, resolving to nothing, reported rather than dropped.
        """
        consumer = _federation(
            tmp_path,
            code=(
                "# Implements: the caching strategy described above\n" "def cache():\n" "    pass\n"
            ),
        )

        federated = build_graph(repo_root=consumer)

        assert [br.target_id for br in federated.broken_references()] == [
            "the caching strategy described above"
        ]
        assert [node.id for node in federated._repos["d"].graph.iter_by_kind(NodeKind.CODE)] != []


def _census(federated, repo_name: str) -> tuple:
    """A comparable summary of one repository's scanned annotations."""
    graph = federated._repos[repo_name].graph
    nodes = sorted(
        (node.kind.value, node.id)
        for node in graph._index.values()
        if node.kind in (NodeKind.CODE, NodeKind.TEST)
    )
    edges = sorted(
        (node.id, edge.kind.value, edge.target.id)
        for node in graph._index.values()
        for edge in node.iter_outgoing_edges()
    )
    broken = sorted(str(br) for br in graph.broken_references())
    return (nodes, edges, broken)
