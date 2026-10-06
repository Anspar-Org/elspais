"""What a ``Satisfies:`` naming *Assertions* of a template copies.

One template requirement holds A, B and C. Template requirements refine it:
one names A, one names the whole requirement, one names B, one names A and B,
and one refines the A-refiner. Each declaring requirement names a different
selection of the template, and its copies are read back as a shape written
in roles rather than identifiers, so one expectation states the copy in
every layout of the federation: everything in one repository, the
templates in an associate, and the root template in an associate with its
refiners beside the declaring requirements.
"""

from __future__ import annotations

import subprocess
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from elspais.commands._requests import TraceRequest
from elspais.commands.trace import compute_trace
from elspais.graph.factory import build_graph
from elspais.graph.GraphNode import NodeKind
from elspais.graph.metrics import satisfier_rollup
from elspais.graph.reference_faults import FaultClass
from elspais.graph.relations import EdgeKind, Stereotype
from elspais.graph.render import compute_hash_for_node, render_end_marker
from elspais.mcp.server import _get_requirement
from tests.core.test_mutation_faults_match_rebuild import (
    Case,
    _assert_memory_equals_rebuild,
    _assert_undo_restores,
    _retitle,
)

# ---------------------------------------------------------------------------
# The project
# ---------------------------------------------------------------------------

# role -> (title, status, Refines: written in roles or None, assertion labels),
# in the order the file holds them. The Draft refiner a mutation deletes is
# the last template, since a requirement copied within its repository keeps
# its original's lines.
TEMPLATES = {
    "root": ("Audit Trail", "Active", None, ("A", "B", "C")),
    "ref_whole": ("Audit Retention", "Active", "root", ("A",)),
    "ref_b": ("Time Record", "Active", "root-B", ("A",)),
    "ref_ab": ("Record Integrity", "Active", "root-A, root-B", ("A",)),
    "nested": ("Author Identity", "Active", "ref_a", ("A",)),
    "ref_a": ("Author Record", "Draft", "root-A", ("A",)),
}

# The template the declaring requirements read: what each Assertion says.
ROOT_TEXT = {
    "A": "The system SHALL record who made each change.",
    "B": "The system SHALL record when each change was made.",
    "C": "The system SHALL record why each change was made.",
}

# role -> Satisfies: written in roles
DECLARERS = {
    "d_a": "root-A",
    "d_ac": "root-A, root-C",
    "d_plus": "root-A+B",
    "d_overlap": "root-A, ref_a",
    "d_whole": "root, root-A",
    "d_missing": "root-Z",
    "d_concrete": "concrete-A",
    "d_gone": "gone-A+B",
}

NUMBERS = {
    "root": 10,
    "ref_a": 20,
    "ref_whole": 21,
    "ref_b": 22,
    "ref_ab": 23,
    "nested": 24,
    "concrete": 30,
    "gone": 40,
    "d_a": 51,
    "d_ac": 52,
    "d_plus": 53,
    "d_overlap": 54,
    "d_whole": 55,
    "d_missing": 56,
    "d_concrete": 57,
    "d_gone": 58,
}


@dataclass(frozen=True)
class Layout:
    """Which repository holds which roles, and the repository to build from."""

    repos: dict[str, str]  # directory -> namespace
    owner: Callable[[str], str]  # role -> directory
    root: str  # directory the build starts in


def _in_repo_owner(_role: str) -> str:
    return "project"


def _xrepo_owner(role: str) -> str:
    return "app" if role.startswith("d_") else "library"


def _split_owner(role: str) -> str:
    return "library" if role in ("root", "concrete", "gone") else "app"


LAYOUTS = {
    "in-repo": Layout({"project": "REQ"}, _in_repo_owner, "project"),
    "xrepo": Layout({"library": "LIB", "app": "APP"}, _xrepo_owner, "app"),
    "xrepo-split": Layout({"library": "LIB", "app": "APP"}, _split_owner, "app"),
}

LAYOUT_CASES = pytest.mark.parametrize("layout", list(LAYOUTS))


def _id(layout: Layout, role: str) -> str:
    """The identifier *role* has in *layout*."""
    owner = layout.owner(role)
    return f"{layout.repos[owner]}-p{NUMBERS[role]:05d}"


def _ref(layout: Layout, written: str) -> str:
    """A reference list written in roles, spelled in *layout*'s identifiers."""
    items = []
    for item in written.split(", "):
        role, _sep, labels = item.partition("-")
        items.append(_id(layout, role) + (f"-{labels}" if labels else ""))
    return ", ".join(items)


def _config(namespace: str, associates: dict[str, str]) -> str:
    text = f"""\
version = 5

[project]
name = "{namespace.lower()}"
namespace = "{namespace}"

[levels.prd]
rank = 1
letter = "p"
implements = ["prd"]

[scanning]
skip = [".git", ".elspais"]

[scanning.spec]
directories = ["spec"]

[scanning.code]
directories = []

[scanning.test]
enabled = false
directories = []

[id-patterns]
canonical = "{{namespace}}-{{level.letter}}{{component}}"

[id-patterns.component]
style = "numeric"
digits = 5
leading_zeros = true

[id-patterns.assertions]
label_style = "uppercase"
max_count = 26

[rules.hierarchy]
allow_structural_orphans = true

[rules.format]
require_hash = false
require_assertions = true
require_status = true

[changelog]
hash_current = false
"""
    for directory, ns in associates.items():
        text += f'\n[associates.{directory}]\npath = "../{directory}"\nnamespace = "{ns}"\n'
    return text


def _block(req_id: str, title: str, status: str, marker: str, meta: str, assertions) -> str:
    body = "\n\n".join(f"{label}. {text}" for label, text in assertions)
    return (
        f"# {req_id}: {title}\n\n"
        f"**Level**: prd | **Status**: {status}{marker} | **Implements**: -\n"
        f"{meta}\n## Assertions\n\n{body}\n\n*End* *{title}*\n---\n\n"
    )


def _spec_text(layout: Layout, directory: str, retired_root_a: bool) -> str:
    text = ""
    for role, (title, status, refines, labels) in TEMPLATES.items():
        if layout.owner(role) != directory:
            continue
        meta = f"**Refines**: {_ref(layout, refines)}\n" if refines else ""
        if role == "root":
            said = dict(ROOT_TEXT)
            if retired_root_a:
                said["A"] = "<RETIRED>"
            assertions = list(said.items())
        else:
            assertions = [(label, f"The {title.lower()} SHALL hold.") for label in labels]
        text += _block(_id(layout, role), title, status, " | **Template**", meta, assertions)
    if layout.owner("concrete") == directory:
        text += _block(
            _id(layout, "concrete"),
            "Concrete Record",
            "Active",
            "",
            "",
            [("A", "The record SHALL exist.")],
        )
    for role, written in DECLARERS.items():
        if layout.owner(role) != directory:
            continue
        text += _block(
            _id(layout, role),
            f"Declarer {NUMBERS[role]}",
            "Active",
            "",
            f"**Satisfies**: {_ref(layout, written)}\n",
            [("A", "The declarer SHALL work.")],
        )
    return text


def _record_hashes(root: Path) -> None:
    """Write each requirement's hash into its End marker.

    A save records the hash of every requirement in each file it writes, so
    recording them first keeps a comparison of a mutation with a rebuild to
    what the mutation did.
    """
    graph = build_graph(repo_root=root, config_path=root / ".elspais.toml")
    for _ns, member in graph._live_graphs():
        for node in member.iter_by_kind(NodeKind.REQUIREMENT):
            if node.get_field("stereotype") == Stereotype.INSTANCE:
                continue
            path = Path(node.file_node().get_field("absolute_path"))
            title = node.get_label()
            text = path.read_text(encoding="utf-8")
            old = render_end_marker(title, node.get_field("hash"))
            assert text.count(old) == 1
            new = render_end_marker(title, compute_hash_for_node(node))
            path.write_text(text.replace(old, new), encoding="utf-8")


def _make(layout_name: str, retired_root_a: bool = False):
    layout = LAYOUTS[layout_name]

    def make(tmp_path: Path) -> tuple[Path, Path]:
        base = tmp_path / "work"
        for directory, namespace in layout.repos.items():
            repo = base / directory
            (repo / "spec").mkdir(parents=True)
            associates = {"library": "LIB"} if directory == "app" else {}
            (repo / ".elspais.toml").write_text(_config(namespace, associates), encoding="utf-8")
            (repo / "spec" / "prd-spec.md").write_text(
                _spec_text(layout, directory, retired_root_a), encoding="utf-8"
            )
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
        _record_hashes(base / layout.root)
        return base, base / layout.root

    return make


def _build(layout_name: str, tmp_path: Path, retired_root_a: bool = False):
    _base, root = _make(layout_name, retired_root_a)(tmp_path)
    return build_graph(repo_root=root, config_path=root / ".elspais.toml"), root


# ---------------------------------------------------------------------------
# Reading a copy back as roles
# ---------------------------------------------------------------------------


def _roles(layout: Layout) -> dict[str, str]:
    """identifier -> role, for every role and every template Assertion."""
    roles = {}
    for role in [*TEMPLATES, "concrete", *DECLARERS]:
        roles[_id(layout, role)] = role
    return roles


def _original(copy) -> object:
    (original,) = list(copy.iter_children(edge_kinds={EdgeKind.INSTANCE}))
    return original


@dataclass(frozen=True)
class Shape:
    """What one declaring requirement's copies hold, written in roles."""

    copies: dict[str, tuple[str, ...]]  # original role -> labels its copy holds
    refines: frozenset[tuple[str, str, tuple[str, ...]]]  # (refined, refiner, labels)
    satisfies: frozenset[tuple[str, tuple[str, ...]]]  # (copied role, labels)


def _shape(graph, layout_name: str, declarer: str) -> Shape:
    layout = LAYOUTS[layout_name]
    roles = _roles(layout)
    declaring = graph.find_by_id(_id(layout, declarer))
    prefix = f"{declaring.id}::"
    copies = [
        node
        for _ns, member in graph._live_graphs()
        for node_id, node in member._index.items()
        if node_id.startswith(prefix) and node.kind == NodeKind.REQUIREMENT
    ]
    held = {}
    refines: list[tuple[str, str, tuple[str, ...]]] = []
    for copy in copies:
        assert copy.get_field("stereotype") == Stereotype.INSTANCE
        original = _original(copy)
        assert copy.id == f"{prefix}{original.id}"
        assertions = [
            c
            for c in copy.iter_children(edge_kinds={EdgeKind.STRUCTURES})
            if c.kind == NodeKind.ASSERTION
        ]
        for assertion in assertions:
            assert _original(assertion).get_label() == assertion.get_label()
        held[roles[original.id]] = tuple(sorted(a.get_field("label") for a in assertions))
        for edge in copy.iter_outgoing_edges():
            if edge.kind == EdgeKind.REFINES:
                assert edge.target.id.startswith(prefix)
                refines.append(
                    (
                        roles[original.id],
                        roles[_original(edge.target).id],
                        tuple(edge.assertion_targets),
                    )
                )
    satisfies = [
        (roles[_original(e.target).id], tuple(e.assertion_targets))
        for e in declaring.iter_outgoing_edges()
        if e.kind == EdgeKind.SATISFIES
    ]
    # Each edge is held once.
    assert len(set(refines)) == len(refines)
    assert len(set(satisfies)) == len(satisfies)
    return Shape(held, frozenset(refines), frozenset(satisfies))


# What each declaration copies: the requirement holding a named Assertion,
# restricted to what was named, with the template subtree of each template
# requirement refining a named Assertion or the whole requirement.
_UNDER_A = {"ref_a": ("A",), "ref_whole": ("A",), "ref_ab": ("A",), "nested": ("A",)}
_REFINES_UNDER_A = {
    ("root", "ref_a", ("A",)),
    ("root", "ref_whole", ()),
    ("root", "ref_ab", ("A",)),
    ("ref_a", "nested", ()),
}
# A refinement naming A and B is held as one edge per label, and a copy
# holding both keeps both.
_REFINES_UNDER_A_AND_B = _REFINES_UNDER_A | {
    ("root", "ref_b", ("B",)),
    ("root", "ref_ab", ("B",)),
}
EXPECTED = {
    "d_a": Shape(
        {"root": ("A",), **_UNDER_A},
        frozenset(_REFINES_UNDER_A),
        frozenset({("root", ("A",))}),
    ),
    "d_ac": Shape(
        {"root": ("A", "C"), **_UNDER_A},
        frozenset(_REFINES_UNDER_A),
        frozenset({("root", ("A",)), ("root", ("C",))}),
    ),
    "d_plus": Shape(
        {"root": ("A", "B"), **_UNDER_A, "ref_b": ("A",)},
        frozenset(_REFINES_UNDER_A_AND_B),
        frozenset({("root", ("A",)), ("root", ("B",))}),
    ),
    "d_overlap": Shape(
        {"root": ("A",), **_UNDER_A},
        frozenset(_REFINES_UNDER_A),
        frozenset({("root", ("A",)), ("ref_a", ())}),
    ),
    "d_whole": Shape(
        {"root": ("A", "B", "C"), **_UNDER_A, "ref_b": ("A",)},
        frozenset(_REFINES_UNDER_A_AND_B),
        frozenset({("root", ()), ("root", ("A",))}),
    ),
    "d_missing": Shape({}, frozenset(), frozenset()),
    "d_concrete": Shape({}, frozenset(), frozenset()),
    "d_gone": Shape({}, frozenset(), frozenset()),
}

# (target written in roles, class) of each Satisfies: reported unresolved.
EXPECTED_FAULTS = {
    "d_missing": [("root-Z", FaultClass.UNKNOWN_ASSERTION)],
    "d_concrete": [("concrete-A", FaultClass.FORBIDDEN)],
    # A multi-assertion item naming a requirement no member holds is
    # reported once per label, as it is where the item names one present.
    "d_gone": [
        ("gone-A", FaultClass.UNKNOWN_REQUIREMENT),
        ("gone-B", FaultClass.UNKNOWN_REQUIREMENT),
    ],
}


def _satisfies_faults(graph, layout_name: str, declarer: str) -> Counter:
    layout = LAYOUTS[layout_name]
    declaring_id = _id(layout, declarer)
    return Counter(
        (f.target_id, f.fault_class)
        for _ns, member in graph._live_graphs()
        for f in member.unresolved_references()
        if f.source_id == declaring_id and f.edge_kind == EdgeKind.SATISFIES.value
    )


# ---------------------------------------------------------------------------
# A build
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> dict[str, object]:
    """The graph a build makes in each layout."""
    return {
        name: _build(name, tmp_path_factory.mktemp(name.replace("-", "_")))[0] for name in LAYOUTS
    }


class TestTheCopyOfNamedAssertions:
    """Validates REQ-d00328-A+B+C+D+E+F."""

    @LAYOUT_CASES
    @pytest.mark.parametrize("declarer", [d for d in EXPECTED if EXPECTED[d].copies])
    # Verifies: REQ-d00328-A+B+C+D+E+F
    def test_REQ_d00328_A_the_copy_holds_what_the_declaration_names(self, built, layout, declarer):
        assert _shape(built[layout], layout, declarer) == EXPECTED[declarer]

    @LAYOUT_CASES
    # Verifies: REQ-d00328-B
    def test_REQ_d00328_B_a_refiner_of_another_assertion_is_not_copied(self, built, layout):
        graph = built[layout]
        ids = LAYOUTS[layout]
        declaring = _id(ids, "d_a")
        assert graph.find_by_id(f"{declaring}::{_id(ids, 'ref_b')}") is None
        assert graph.find_by_id(f"{declaring}::{_id(ids, 'root')}-B") is None
        assert graph.find_by_id(f"{declaring}::{_id(ids, 'root')}-C") is None
        # The copy is a requirement the declaring requirement satisfies.
        copy = graph.find_by_id(f"{declaring}::{_id(ids, 'root')}")
        assert copy.kind == NodeKind.REQUIREMENT
        assert graph.find_by_id(declaring) in copy.iter_parents(edge_kinds={EdgeKind.SATISFIES})

    # Verifies: REQ-d00328-F
    def test_REQ_d00328_F_every_layout_makes_the_same_copies(self, built):
        shapes = {
            layout: {d: _shape(built[layout], layout, d) for d in DECLARERS} for layout in LAYOUTS
        }
        assert shapes["xrepo"] == shapes["in-repo"]
        assert shapes["xrepo-split"] == shapes["in-repo"]

    @LAYOUT_CASES
    @pytest.mark.parametrize("declarer", list(DECLARERS))
    # Verifies: REQ-d00328-G
    def test_REQ_d00328_G_each_declaration_without_a_copy_is_reported_once(
        self, built, layout, declarer
    ):
        expected = Counter(
            (_ref(LAYOUTS[layout], written), fault_class)
            for written, fault_class in EXPECTED_FAULTS.get(declarer, [])
        )
        assert _satisfies_faults(built[layout], layout, declarer) == expected


class TestTheCopyIsShown:
    """Validates REQ-p00014-K, REQ-d00328-A+C."""

    @LAYOUT_CASES
    # Verifies: REQ-p00014-K, REQ-d00328-A
    def test_REQ_d00328_A_the_copy_is_a_row_of_the_traceability_report(self, built, layout):
        ids = LAYOUTS[layout]
        rows = {node["id"] for node in compute_trace(built[layout], {}, TraceRequest())["nodes"]}
        for declarer in ("d_a", "d_ac", "d_overlap"):
            assert f"{_id(ids, declarer)}::{_id(ids, 'root')}" in rows

    @LAYOUT_CASES
    # Verifies: REQ-p00014-K, REQ-d00328-A
    def test_REQ_d00328_A_the_viewer_tree_shows_it_as_a_whole_copy(self, built, layout):
        from elspais.view_model import build_tree_rows

        ids = LAYOUTS[layout]
        rows = {row["id"] for row in build_tree_rows(built[layout], {})}
        root = _id(ids, "root")
        # A copy of named Assertions is shown where a copy of the whole is.
        assert f"{_id(ids, 'd_whole')}::{root}" in rows
        assert f"{_id(ids, 'd_a')}::{root}" in rows

    @LAYOUT_CASES
    # Verifies: REQ-p00014-K, REQ-d00328-A+C
    def test_REQ_d00328_C_the_viewer_lists_the_declaring_requirement_once(self, built, layout):
        from elspais.server.app import create_app
        from elspais.server.state import AppState

        ids = LAYOUTS[layout]
        graph = built[layout]
        state = AppState(graph=graph, repo_root=Path("/unused"), config={})
        client = TestClient(create_app(state, mount_mcp=False))
        declaring = _id(ids, "d_ac")
        copy_id = f"{declaring}::{_id(ids, 'root')}"

        response = client.get(f"/api/node/{copy_id}")
        assert response.status_code == 200
        sections = {s["kind"]: s["links"] for s in response.json()["incoming_links"]}
        # d_ac names two Assertions of one requirement: one copy, one link.
        assert [link["id"] for link in sections["Satisfied by"]] == [declaring]

    @LAYOUT_CASES
    # Verifies: REQ-d00328-C
    def test_REQ_d00328_C_the_declaring_requirement_is_one_parent_of_the_copy(self, built, layout):
        ids = LAYOUTS[layout]
        declaring = _id(ids, "d_ac")
        result = _get_requirement(built[layout], f"{declaring}::{_id(ids, 'root')}")
        parents = [p for p in result["parents"] if p["id"] == declaring]
        assert len(parents) == 1

    @LAYOUT_CASES
    # Verifies: REQ-d00328-C+D
    def test_REQ_d00328_C_each_copied_assertion_is_counted_once(self, built, layout):
        ids = LAYOUTS[layout]
        rollup = satisfier_rollup(built[layout].find_by_id(_id(ids, "d_ac")))
        # The declarer's own A, the copy's A and C, and one A in each of the
        # four refiners copied beneath it.
        assert rollup.total == 1 + 2 + 4


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------


def _root_assertion(layout: str, label: str) -> str:
    return f"{_id(LAYOUTS[layout], 'root')}-{label}"


# name -> (starts with root-A retired, mutation over (layout) -> graph -> entry)
MUTATIONS = {
    "retire-root-a-by-edit": (
        False,
        lambda layout: lambda g: g.update_assertion(_root_assertion(layout, "A"), "<RETIRED>"),
    ),
    "retire-root-a-by-delete": (
        False,
        lambda layout: lambda g: g.delete_assertion(_root_assertion(layout, "A")),
    ),
    "bring-back-root-a": (
        True,
        lambda layout: lambda g: g.update_assertion(_root_assertion(layout, "A"), ROOT_TEXT["A"]),
    ),
    "edit-root-c": (
        False,
        lambda layout: (
            lambda g: g.update_assertion(
                _root_assertion(layout, "C"), "The system SHALL record the reason for each change."
            )
        ),
    ),
    "delete-refiner": (
        False,
        lambda layout: lambda g: g.delete_requirement(_id(LAYOUTS[layout], "ref_a")),
    ),
}

MUTATION_CASES = pytest.mark.parametrize(
    "layout, mutation",
    [(layout, m) for layout in LAYOUTS for m in MUTATIONS],
    ids=[f"{layout}-{m}" for layout in LAYOUTS for m in MUTATIONS],
)


def _case(layout: str, mutation: str) -> Case:
    retired, mutate = MUTATIONS[mutation]
    return Case(
        _make(layout, retired_root_a=retired),
        mutate(layout),
        _retitle(_id(LAYOUTS[layout], "d_whole")),
    )


class TestAMutationMakesTheCopyABuildMakes:
    """Validates REQ-d00328-G+H, REQ-o00062-G."""

    @MUTATION_CASES
    # Verifies: REQ-d00328-H
    def test_REQ_d00328_H_the_copy_equals_a_rebuild_of_the_saved_text(
        self, tmp_path, layout, mutation
    ):
        _assert_memory_equals_rebuild(tmp_path, _case(layout, mutation))

    @MUTATION_CASES
    @pytest.mark.parametrize("undo", ["undo_last", "undo_to"])
    # Verifies: REQ-d00328-H, REQ-o00062-G
    def test_REQ_d00328_H_undo_restores_the_copy(self, tmp_path, layout, mutation, undo):
        _assert_undo_restores(tmp_path, _case(layout, mutation), undo)

    @LAYOUT_CASES
    # Verifies: REQ-d00328-B+D+G+H
    def test_REQ_d00328_G_retiring_the_named_assertion_reports_the_declaration(
        self, tmp_path, layout
    ):
        graph, _base, _ = _assert_memory_equals_rebuild(
            tmp_path, _case(layout, "retire-root-a-by-edit")
        )
        root_a = _root_assertion(layout, "A")
        # A declaration naming the retired Assertion alone copies nothing and
        # is reported once.
        assert _shape(graph, layout, "d_a") == Shape({}, frozenset(), frozenset())
        assert _satisfies_faults(graph, layout, "d_a") == Counter(
            {(root_a, FaultClass.UNKNOWN_ASSERTION): 1}
        )
        # A declaration also naming C keeps C, and the template refining the
        # whole requirement; the refiners of A leave with it.
        assert _shape(graph, layout, "d_ac") == Shape(
            {"root": ("C",), "ref_whole": ("A",)},
            frozenset({("root", "ref_whole", ())}),
            frozenset({("root", ("C",))}),
        )
        assert _satisfies_faults(graph, layout, "d_ac") == Counter(
            {(root_a, FaultClass.UNKNOWN_ASSERTION): 1}
        )

    @LAYOUT_CASES
    # Verifies: REQ-d00328-B+H
    def test_REQ_d00328_B_bringing_the_assertion_back_copies_its_refiners(self, tmp_path, layout):
        graph, _base, _ = _assert_memory_equals_rebuild(
            tmp_path, _case(layout, "bring-back-root-a")
        )
        for declarer in ("d_a", "d_ac", "d_plus", "d_overlap"):
            assert _shape(graph, layout, declarer) == EXPECTED[declarer]
            assert _satisfies_faults(graph, layout, declarer) == Counter()
