"""A mutation that takes away a cited target leaves the graph a build would make.

Retiring an _Assertion_, or deleting a requirement that is not Active, takes
away something other files cite. A build of the saved text reports each such
citation as an unresolved reference and binds nothing to it (REQ-p00017-H).
The graph held in memory has to agree with that build at once, wherever the
citation is written: in a test file where it binds to no test, under a
spelling the reader normalizes, inside a `Satisfies:` copy of a template, or
in another member of a federation. Undo restores the prior state exactly.

Each case compares one state function over the graph held after the mutation
with the same function over a rebuild of the text the mutation saved. Every
test works on a throwaway copy of an on-disk fixture.
"""

from __future__ import annotations

import dataclasses
import shutil
import subprocess
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

from elspais.graph.GraphNode import NodeKind
from elspais.graph.reference_faults import FaultClass
from elspais.graph.relations import Stereotype
from elspais.graph.render import render_save
from tests.core.test_retired_citation_unresolved import FIXTURES_DIR, _build, _replace_once

# ---------------------------------------------------------------------------
# The state a build decides
# ---------------------------------------------------------------------------


def _is_line_anchored_remainder(node_id: str) -> bool:
    # A file-level REMAINDER id carries the line it was read from, and a save
    # moves lines, so the same prose has another id after a rebuild.
    return node_id.startswith("rem:")


def _rel(value, prefix: str):
    """*value* with the project directory *prefix* stripped from every string."""
    if isinstance(value, str):
        return value.replace(prefix, "")
    if isinstance(value, (tuple, list)):
        return tuple(_rel(v, prefix) for v in value)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted(_rel(v, prefix) for v in value))
    if isinstance(value, FaultClass):
        return value.name
    return value


def _record(obj, prefix: str) -> tuple:
    """Every field of a frozen dataclass, as sortable (name, value) pairs."""
    return tuple(
        (field.name, repr(_rel(getattr(obj, field.name), prefix)))
        for field in dataclasses.fields(obj)
    )


def _instance_content(node, prefix: str) -> tuple:
    # The keyword index is rebuilt on every mutation and is not what a
    # Satisfies: copy says; a field holding None is a field not set.
    return tuple(
        sorted(
            (key, repr(_rel(value, prefix)))
            for key, value in node.get_all_content().items()
            if key != "keywords" and value is not None
        )
    )


def _state(graph, base: Path) -> dict:
    """Everything a build decides about citations, with *base* stripped."""
    prefix = f"{base}/"
    members = list(graph._live_graphs())

    faults = []
    unbound = []
    orphans = []
    index = []
    edges = []
    refs = []
    instances = []
    for namespace, member in members:
        faults += [(namespace, _record(f, prefix)) for f in member.unresolved_references()]
        unbound += [(namespace, _record(c, prefix)) for c in member.unbound_citations()]
        orphans += [(namespace, _rel(i, prefix)) for i in member._orphaned_ids]
        for node_id, node in member._index.items():
            if _is_line_anchored_remainder(node_id):
                continue
            index.append((namespace, _rel(node_id, prefix)))
            for edge in node.iter_outgoing_edges():
                if _is_line_anchored_remainder(edge.target.id):
                    continue
                edges.append(
                    (
                        _rel(edge.source.id, prefix),
                        _rel(edge.target.id, prefix),
                        edge.kind.value,
                        tuple(edge.assertion_targets),
                    )
                )
            if node.kind == NodeKind.REQUIREMENT:
                refs.append(
                    (
                        node_id,
                        tuple(node.get_field("implements_refs") or ()),
                        tuple(node.get_field("refines_refs") or ()),
                    )
                )
            if node.get_field("stereotype") == Stereotype.INSTANCE:
                instances.append((node_id, node.get_label(), _instance_content(node, prefix)))

    return {
        "faults": sorted(faults),
        "unbound": sorted(unbound),
        "roots": sorted(_rel(node.id, prefix) for node in graph.iter_roots()),
        "orphans": sorted(orphans),
        "index": sorted(index),
        "ownership": sorted(
            _rel(i, prefix) for i in graph._ownership if not _is_line_anchored_remainder(i)
        ),
        "edges": sorted(edges),
        "refs": sorted(refs),
        "instances": sorted(instances),
    }


def _diff(actual: dict, expected: dict) -> dict:
    """The entries of each part that only one side holds, for a readable failure."""
    out = {}
    for key in expected:
        a, e = set(map(repr, actual[key])), set(map(repr, expected[key]))
        if a != e or len(actual[key]) != len(expected[key]):
            out[key] = {"memory_only": sorted(a - e), "rebuild_only": sorted(e - a)}
    return out


# ---------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Case:
    """One project, one mutation, and an unrelated mutation to stack on it."""

    make: Callable[[Path], tuple[Path, Path]]  # tmp_path -> (base, build root)
    mutate: Callable[[object], object]
    later: Callable[[object], object]


def _git_init(*dirs: Path) -> None:
    for directory in dirs:
        subprocess.run(["git", "init", "-q", str(directory)], check=True)


def _copy(tmp_path: Path, fixture: str, repos: tuple[str, ...] = ()) -> Path:
    base = tmp_path / "project"
    shutil.copytree(FIXTURES_DIR / fixture, base)
    _git_init(*([base / r for r in repos] or [base]))
    return base


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _retire(assertion_id: str, how: str) -> Callable[[object], object]:
    if how == "delete":
        return lambda g: g.delete_assertion(assertion_id)
    return lambda g: g.update_assertion(assertion_id, "<RETIRED>")


def _retitle(node_id: str) -> Callable[[object], object]:
    return lambda g: g.update_title(node_id, "A Title Changed Later")


def _save(graph, root: Path) -> None:
    result = render_save(graph, repo_root=root, write_associates=True)
    assert result["success"] is True, result.get("errors")


def _assert_memory_equals_rebuild(tmp_path: Path, case: Case, observe=None):
    """Apply the case's mutation, then compare with a rebuild of the saved text.

    Returns the graph after the mutation, the base directory, and what
    *observe* (called with the graph and the base before the mutation) read.
    """
    base, root = case.make(tmp_path)
    graph = _build(root)
    observed = observe(graph, base) if observe else None
    case.mutate(graph)
    in_memory = _state(graph, base)

    _save(graph, root)
    rebuilt = _state(_build(root), base)

    assert _diff(in_memory, rebuilt) == {}
    assert in_memory == rebuilt
    return graph, base, observed


def _assert_undo_restores(tmp_path: Path, case: Case, undo: str) -> None:
    base, root = case.make(tmp_path)
    graph = _build(root)
    before = _state(graph, base)

    entry = case.mutate(graph)
    assert _state(graph, base) != before
    if undo == "undo_last":
        graph.undo_last()
    else:
        case.later(graph)
        graph.undo_to(entry.id)

    after = _state(graph, base)
    assert _diff(after, before) == {}
    assert after == before


UNDO = pytest.mark.parametrize("undo", ["undo_last", "undo_to"])
RETIREMENTS = ("delete", "update")


def _faults(graph, base: Path, target_prefix: str) -> set[tuple[str, str, str, FaultClass]]:
    """(member, citing node, keyword, class) of each fault naming a target."""
    prefix = f"{base}/"
    return {
        (namespace, f.source_id.replace(prefix, ""), f.edge_kind, f.fault_class)
        for namespace, member in graph._live_graphs()
        for f in member.unresolved_references()
        if f.target_id == target_prefix or f.target_id.startswith(f"{target_prefix}-")
    }


# ---------------------------------------------------------------------------
# 1. A test citation that binds to no test
# ---------------------------------------------------------------------------

UNBOUND_FILE = "tests/test_unbound.py"
# Each citation, and what retiring REQ-d00001-A adds to the faults it carries.
# The reader refuses a repeated item, so a citation repeating the retired
# Assertion was already refused for it and gains nothing; one repeating
# another target gains the fault for the retired one.
UNBOUND_TARGETS = {
    "single": ("REQ-d00001-A", {("REQ-d00001-A", "UNKNOWN_ASSERTION"): 1}),
    "repeats-retired": ("REQ-d00001-A+B, REQ-d00001-A, REQ-d00001-A", {}),
    "repeats-other": (
        "REQ-d00001-A, REQ-d00001-B, REQ-d00001-B",
        {("REQ-d00001-A", "UNKNOWN_ASSERTION"): 1},
    ),
}


def _unbound_project(targets: str) -> Callable[[Path], tuple[Path, Path]]:
    def make(tmp_path: Path) -> tuple[Path, Path]:
        base = _copy(tmp_path, "e2e-standard")
        # The citation follows the last test, so nothing lies below it to bind to.
        _write(base / UNBOUND_FILE, f"def test_x():\n    pass\n\n\n# Verifies: {targets}\n")
        return base, base

    return make


def _unbound_case(variant: str, how: str) -> Case:
    targets, _added = UNBOUND_TARGETS[variant]
    return Case(_unbound_project(targets), _retire("REQ-d00001-A", how), _retitle("REQ-d00002"))


def _unbound_faults(graph) -> Counter:
    """(target, class) of each fault the unbound citation's node carries."""
    (citation,) = [c for c in graph.unbound_citations() if c.path.endswith(UNBOUND_FILE)]
    return Counter(
        (f.target_id, f.fault_class.name)
        for f in graph.unresolved_references()
        if f.source_id == citation.node_id
    )


UNBOUND_CASES = pytest.mark.parametrize(
    "variant, how",
    [(v, h) for v in UNBOUND_TARGETS for h in RETIREMENTS],
    ids=[f"{v}-{h}" for v in UNBOUND_TARGETS for h in RETIREMENTS],
)


class TestUnboundCitationOfARetiredAssertion:
    """Validates REQ-p00017-H, REQ-d00274-H, REQ-o00062-G."""

    @UNBOUND_CASES
    # Verifies: REQ-p00017-H, REQ-d00274-H
    def test_REQ_p00017_H_unbound_citation_gets_the_fault_a_build_reports(
        self, tmp_path, variant, how
    ):
        _targets, added = UNBOUND_TARGETS[variant]

        graph, _base, before = _assert_memory_equals_rebuild(
            tmp_path, _unbound_case(variant, how), lambda g, _b: _unbound_faults(g)
        )

        assert _unbound_faults(graph) - before == Counter(added)
        assert before - _unbound_faults(graph) == Counter()

    @UNBOUND_CASES
    @UNDO
    # Verifies: REQ-o00062-G, REQ-d00274-H
    def test_REQ_o00062_G_undo_withdraws_the_unbound_citation_fault(
        self, tmp_path, variant, how, undo
    ):
        _assert_undo_restores(tmp_path, _unbound_case(variant, how), undo)


# ---------------------------------------------------------------------------
# 2. Template Assertions copied by Satisfies:
# ---------------------------------------------------------------------------

XREPO = ("app", "library", "tenant")


def _xrepo_project(
    root: str, *, assertion_satisfies: bool = False, draft: bool = False, interior: bool = False
) -> Callable[[Path], tuple[Path, Path]]:
    def make(tmp_path: Path) -> tuple[Path, Path]:
        base = _copy(tmp_path, "e2e-xrepo-template", XREPO)
        library = base / "library" / "spec" / "prd-library.md"
        if draft:
            _replace_once(library, "**Status**: Active", "**Status**: Draft")
        if interior:
            text = library.read_text(encoding="utf-8")
            _write(
                library,
                text + "\n# LIB-p00002: Dispatch Audit\n\n"
                "**Level**: prd | **Status**: Draft | **Template** | **Implements**: -\n"
                "**Refines**: LIB-p00001\n\n"
                "## Assertions\n\n"
                "A. The dispatch flow SHALL record each denial.\n\n"
                "*End* *Dispatch Audit*\n---\n",
            )
        if assertion_satisfies:
            _replace_once(
                base / "tenant" / "spec" / "prd-tenant.md",
                "**Satisfies**: LIB-p00001\n",
                "**Satisfies**: LIB-p00001-A\n",
            )
        return base, base / root

    return make


IN_REPO_CONFIG = """\
version = 5

[project]
name = "in-repo-template"
namespace = "REQ"

[levels.prd]
rank = 1
letter = "p"
implements = ["prd"]

[levels.dev]
rank = 3
letter = "d"
implements = ["dev", "prd"]

[scanning]
skip = [".git", ".elspais"]

[scanning.spec]
directories = ["spec"]

[scanning.code]
directories = ["src"]

[scanning.test]
enabled = true
directories = ["tests"]
file_patterns = ["test_*.py"]

[id-patterns]
canonical = "{namespace}-{level.letter}{component}"

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

IN_REPO_SPEC = """\
# REQ-p00010: Audit Trail

**Level**: prd | **Status**: Active | **Template** | **Implements**: -

## Assertions

A. The system SHALL record who made each change.

B. The system SHALL record when each change was made.

*End* *Audit Trail*
---

# REQ-p00011: Order Entry

**Level**: prd | **Status**: Active | **Implements**: -
**Satisfies**: REQ-p00010

## Assertions

A. Order entry SHALL accept an order.

*End* *Order Entry*
---

# REQ-p00012: Billing

**Level**: prd | **Status**: Active | **Implements**: -
**Satisfies**: REQ-p00010-A

## Assertions

A. Billing SHALL issue an invoice.

*End* *Billing*
---
"""


def _in_repo_project(tmp_path: Path) -> tuple[Path, Path]:
    base = tmp_path / "project"
    _write(base / ".elspais.toml", IN_REPO_CONFIG)
    _write(base / "spec" / "prd-template.md", IN_REPO_SPEC)
    _write(base / "src" / "audit.py", "# Implements: REQ-p00010-A\ndef audit():\n    pass\n")
    _git_init(base)
    return base, base


# (project, retired Assertion, the satisfiers copying it whole, those that
# satisfy only it, an unrelated requirement to retitle)
TEMPLATE_SETUPS = {
    "xrepo-app": (_xrepo_project("app"), "LIB-p00001-A", ("APP-p00001",), (), "APP-p00002"),
    "xrepo-tenant": (_xrepo_project("tenant"), "LIB-p00001-A", ("TEN-p00001",), (), "TEN-p00001"),
    "xrepo-tenant-assertion": (
        _xrepo_project("tenant", assertion_satisfies=True),
        "LIB-p00001-A",
        (),
        ("TEN-p00001",),
        "TEN-p00001",
    ),
    "in-repo": (_in_repo_project, "REQ-p00010-A", ("REQ-p00011",), ("REQ-p00012",), "REQ-p00011"),
}

TEMPLATE_CASES = pytest.mark.parametrize(
    "setup, how",
    [(s, h) for s in TEMPLATE_SETUPS for h in RETIREMENTS],
    ids=[f"{s}-{h}" for s in TEMPLATE_SETUPS for h in RETIREMENTS],
)


def _template_case(setup: str, how: str) -> Case:
    make, retired, _whole, _only, unrelated = TEMPLATE_SETUPS[setup]
    return Case(make, _retire(retired, how), _retitle(unrelated))


class TestRetiringATemplateAssertion:
    """Validates REQ-p00017-H, REQ-p00014-B, REQ-o00062-G."""

    @TEMPLATE_CASES
    # Verifies: REQ-p00017-H, REQ-p00014-B
    def test_REQ_p00014_B_every_copy_carries_what_a_build_gives_it(self, tmp_path, setup, how):
        _make, retired, whole, only, _unrelated = TEMPLATE_SETUPS[setup]
        template = retired.rsplit("-", 1)[0]

        graph, base, _ = _assert_memory_equals_rebuild(tmp_path, _template_case(setup, how))

        original = graph.find_by_id(retired)
        original_req = graph.find_by_id(template)
        for satisfier in whole:
            # A copy of the whole template keeps the retired Assertion, saying
            # what the original now says, and the copied requirement takes the
            # original's new hash.
            copy = graph.find_by_id(f"{satisfier}::{retired}")
            assert copy is not None
            for field in ("retired", "directive", "directive_recognized"):
                assert copy.get_field(field) == original.get_field(field)
            assert copy.get_field("retired")
            assert copy.get_label() == original.get_label()
            copied_req = graph.find_by_id(f"{satisfier}::{template}")
            assert copied_req.get_field("hash") == original_req.get_field("hash")
        for satisfier in only:
            # A copy of the retired Assertion alone is withdrawn; the
            # Satisfies: naming it is reported unresolved.
            assert graph.find_by_id(f"{satisfier}::{retired}") is None
            prefix = f"{base}/"
            (fault,) = [
                f
                for _ns, member in graph._live_graphs()
                for f in member.unresolved_references()
                if f.source_id.replace(prefix, "") == satisfier and f.target_id == retired
            ]
            assert fault.edge_kind == "satisfies"
            assert fault.fault_class is FaultClass.UNKNOWN_ASSERTION
            if setup.startswith("xrepo"):
                assert "holds no such Assertion" in fault.diagnostic

    @TEMPLATE_CASES
    @UNDO
    # Verifies: REQ-o00062-G
    def test_REQ_o00062_G_undo_restores_every_copy(self, tmp_path, setup, how, undo):
        _assert_undo_restores(tmp_path, _template_case(setup, how), undo)


# ---------------------------------------------------------------------------
# 3. Citations written in a non-canonical spelling
# ---------------------------------------------------------------------------


def _misspelled_project(tmp_path: Path) -> tuple[Path, Path]:
    base = _copy(tmp_path, "e2e-standard")
    _replace_once(
        base / "spec" / "dev-refine.md", "**Refines**: REQ-d00001\n", "**Refines**: REQ-d1-a\n"
    )
    _replace_once(
        base / "src" / "auth.py", "# Implements: REQ-d00001-A", "# Implements: req-d00001-a"
    )
    _replace_once(
        base / "tests" / "test_auth.py", "# Verifies: REQ-d00001-A", "# Verifies: REQ-d01-A"
    )
    return base, base


MISSPELLED_CITERS = {
    ("REQ-d00003", "refines"),
    ("code:src/auth.py:1", "implements"),
    ("test:tests/test_auth.py::test_authenticate", "verifies"),
}


class TestRetiringAnAssertionCitedInAnotherSpelling:
    """Validates REQ-p00017-H, REQ-o00062-G."""

    @pytest.mark.parametrize("how", RETIREMENTS)
    # Verifies: REQ-p00017-H
    def test_REQ_p00017_H_faults_name_the_target_as_a_build_does(self, tmp_path, how):
        case = Case(_misspelled_project, _retire("REQ-d00001-A", how), _retitle("REQ-d00002"))

        graph, base, _ = _assert_memory_equals_rebuild(tmp_path, case)

        reported = {(citer, kw) for _ns, citer, kw, _cls in _faults(graph, base, "REQ-d00001-A")}
        assert MISSPELLED_CITERS <= reported

    @pytest.mark.parametrize("how", RETIREMENTS)
    @UNDO
    # Verifies: REQ-o00062-G
    def test_REQ_o00062_G_undo_binds_the_misspelled_citations_again(self, tmp_path, how, undo):
        case = Case(_misspelled_project, _retire("REQ-d00001-A", how), _retitle("REQ-d00002"))
        _assert_undo_restores(tmp_path, case, undo)


# ---------------------------------------------------------------------------
# 4. Deleting a requirement that is not Active
# ---------------------------------------------------------------------------


def _standard_draft_project(tmp_path: Path) -> tuple[Path, Path]:
    """e2e-standard with every kind of citation of the Draft REQ-p00003."""
    base = _copy(tmp_path, "e2e-standard")
    _replace_once(
        base / "spec" / "prd-draft.md",
        "*End* *Draft Feature*",
        "## Rationale\n\nWhy it matters.\n\n*End* *Draft Feature*",
    )
    # REQ-d00003's only parent becomes the deleted requirement.
    _replace_once(
        base / "spec" / "dev-refine.md", "**Refines**: REQ-d00001\n", "**Refines**: REQ-p00003-A\n"
    )
    _write(base / "src" / "draft.py", "# Implements: REQ-p00003-A\ndef f():\n    pass\n")
    _write(base / "src" / "draft_whole.py", "# Implements: REQ-p00003\ndef g():\n    pass\n")
    _write(
        base / "tests" / "test_draft.py",
        "# Verifies: REQ-p00003-A\ndef test_draft():\n    pass\n\n\n# Verifies: REQ-p00003\n",
    )
    _write(
        base / "spec" / "journeys.md",
        "# User Journeys\n\n---\n\n"
        "### JNY-Draft-01: Draft Flow\n\n"
        "**Actor**: End User\n**Goal**: Use the draft feature\n"
        "Validates: REQ-p00003-A\n\n"
        "## Steps\n\n1. User opens the draft feature\n\n"
        "*End* *JNY-Draft-01*\n---\n",
    )
    return base, base


def _associated_draft_project(tmp_path: Path) -> tuple[Path, Path]:
    base = _copy(tmp_path, "e2e-associated", ("core", "alpha", "beta"))
    _replace_once(
        base / "core" / "spec" / "prd-core.md",
        "# REQ-p00001: Core Auth\n\n**Level**: PRD | **Status**: Active",
        "# REQ-p00001: Core Auth\n\n**Level**: PRD | **Status**: Draft",
    )
    _replace_once(
        base / "alpha" / "spec" / "dev-alpha.md",
        "**Implements**: REQ-p00001\n",
        "**Implements**: REQ-p00001-A\n",
    )
    return base, base / "core"


# (project, deleted requirement, {(member, citing node, keyword)} each
# reported UNKNOWN_REQUIREMENT, requirements that become roots, an unrelated
# requirement to retitle). The template fixture leaves test scanning at its
# default (off), so its library test file cites nothing.
DELETE_SETUPS = {
    "single": (
        _standard_draft_project,
        "REQ-p00003",
        {
            ("REQ", "REQ-d00003", "refines"),
            ("REQ", "code:src/draft.py:1", "implements"),
            ("REQ", "code:src/draft_whole.py:1", "implements"),
            ("REQ", "test:tests/test_draft.py::test_draft", "verifies"),
            ("REQ", "test:tests/test_draft.py:6", "verifies"),
            ("REQ", "JNY-Draft-01", "validates"),
        },
        {"REQ-d00003"},
        "REQ-d00002",
    ),
    "federation": (
        _associated_draft_project,
        "REQ-p00001",
        {
            ("REQ-ALP", "REQ-ALP-d00001", "implements"),
            ("REQ", "REQ-d00001", "implements"),
        },
        {"REQ-ALP-d00001", "REQ-d00001"},
        "REQ-p00002",
    ),
    "template-app": (
        _xrepo_project("app", draft=True),
        "LIB-p00001",
        {
            ("APP", "APP-p00001", "satisfies"),
            ("LIB", "code:library/src/library.py:1", "implements"),
        },
        set(),
        "APP-p00002",
    ),
    "template-tenant-assertion": (
        _xrepo_project("tenant", assertion_satisfies=True, draft=True),
        "LIB-p00001",
        {
            ("TEN", "TEN-p00001", "satisfies"),
            ("LIB", "code:library/src/library.py:1", "implements"),
        },
        set(),
        "TEN-p00001",
    ),
    "interior-template": (
        _xrepo_project("app", interior=True),
        "LIB-p00002",
        set(),
        set(),
        "APP-p00002",
    ),
}

DELETE_CASES = pytest.mark.parametrize("setup", list(DELETE_SETUPS))


def _delete_case(setup: str) -> Case:
    make, deleted, _citers, _roots, unrelated = DELETE_SETUPS[setup]
    return Case(make, lambda g: g.delete_requirement(deleted), _retitle(unrelated))


def _ids_naming(graph, base: Path, req_id: str) -> set[str]:
    """Every node id, in any member, that is *req_id* or lies beneath it."""
    prefix = f"{base}/"
    return {
        node_id.replace(prefix, "")
        for _ns, member in graph._live_graphs()
        for node_id in member._index
        if node_id == req_id
        or node_id.startswith((f"{req_id}-", f"{req_id}:"))
        or f"::{req_id}" in node_id
    }


class TestDeletingARequirementThatIsNotActive:
    """Validates REQ-p00017-H, REQ-o00062-P, REQ-o00062-G."""

    @DELETE_CASES
    # Verifies: REQ-p00017-H, REQ-o00062-P
    def test_REQ_o00062_P_citations_are_unresolved_as_a_build_reports_them(self, tmp_path, setup):
        _make, deleted, citers, roots, _unrelated = DELETE_SETUPS[setup]

        def observe(graph, base):
            return (
                _faults(graph, base, deleted),
                _ids_naming(graph, base, deleted),
                {node.id for node in graph.iter_roots()},
            )

        graph, base, (faults_before, named_before, roots_before) = _assert_memory_equals_rebuild(
            tmp_path, _delete_case(setup), observe
        )

        assert faults_before == set()
        assert roots.isdisjoint(roots_before)
        beyond_assertions = {
            i for i in named_before if i != deleted and not i.startswith(f"{deleted}-")
        }
        # Fixture premise: the deleted requirement holds a section or is copied.
        assert bool(beyond_assertions) is (setup != "federation")
        assert _faults(graph, base, deleted) == {
            (ns, citer, kw, FaultClass.UNKNOWN_REQUIREMENT) for ns, citer, kw in citers
        }
        assert _ids_naming(graph, base, deleted) == set()
        root_ids = {node.id for node in graph.iter_roots()}
        orphaned = {i for _ns, member in graph._live_graphs() for i in member._orphaned_ids}
        assert roots <= root_ids
        assert roots.isdisjoint(orphaned)

    @DELETE_CASES
    @UNDO
    # Verifies: REQ-o00062-G
    def test_REQ_o00062_G_undo_restores_the_requirement_and_its_citations(
        self, tmp_path, setup, undo
    ):
        _assert_undo_restores(tmp_path, _delete_case(setup), undo)
