"""A mutation that takes away a cited target leaves the graph a build would make.

Retiring an _Assertion_, or deleting a requirement that is not Active, takes
away something other files cite. A build of the saved text reports each such
citation as an unresolved reference and binds nothing to it (REQ-p00017-H).
The graph held in memory has to agree with that build at once, wherever the
citation is written: in a test file where it binds to no test, under a
spelling the reader normalizes, inside a `Satisfies:` copy of a template, or
in another member of a federation. Bringing a retired template _Assertion_
back makes the `Satisfies:` copy of it a build makes, and a test citation
in another member that binds to no test credits nothing whatever its
target. Undo restores the prior state exactly.

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
from elspais.graph.relations import EdgeKind, Stereotype
from elspais.graph.render import compute_hash_for_node, render_end_marker, render_save
from elspais.mcp.server import _add_changelog_for_active_mutations
from elspais.utilities.hasher import compute_normalized_hash
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
        "# REQ-p00001: Core Auth\n\n**Level**: prd | **Status**: Active",
        "# REQ-p00001: Core Auth\n\n**Level**: prd | **Status**: Draft",
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


# ---------------------------------------------------------------------------
# 5. Bringing a template Assertion back
# ---------------------------------------------------------------------------

XREPO_LIVE = (
    "The dispatch flow SHALL include parsing, validation, authorization, and recording stages."
)
IN_REPO_LIVE = "The system SHALL record who made each change."

# (project, the spec file holding the template, the template Assertion, the
# text it says while live, the copies of it a build makes, an unrelated
# requirement to retitle)
RESTORE_SETUPS = {
    "xrepo-tenant-assertion": (
        _xrepo_project("tenant", assertion_satisfies=True),
        "library/spec/prd-library.md",
        "LIB-p00001-A",
        XREPO_LIVE,
        ("TEN-p00001::LIB-p00001-A",),
        "TEN-p00001",
    ),
    "xrepo-tenant": (
        _xrepo_project("tenant"),
        "library/spec/prd-library.md",
        "LIB-p00001-A",
        XREPO_LIVE,
        ("TEN-p00001::LIB-p00001-A",),
        "TEN-p00001",
    ),
    "in-repo": (
        _in_repo_project,
        "spec/prd-template.md",
        "REQ-p00010-A",
        IN_REPO_LIVE,
        ("REQ-p00011::REQ-p00010-A", "REQ-p00012::REQ-p00010-A"),
        "REQ-p00011",
    ),
}

RESTORE_CASES = pytest.mark.parametrize("setup", list(RESTORE_SETUPS))


def _record_hashes(root: Path, template: str) -> None:
    """Write the current hash of *template*, and of each requirement found stale or unhashed.

    A save of a mutation records the hash of each requirement it writes, and
    a build of a recorded hash that disagrees with the text marks the
    requirement, and each copy of it, as needing a rewrite, which that save
    then clears. A requirement with no recorded hash is one a write would
    change too, so the checks report it. Recording the hashes first keeps
    all of these out of a comparison of what the mutation did.
    """
    graph = _build(root)
    for _ns, member in graph._live_graphs():
        for node in member.iter_by_kind(NodeKind.REQUIREMENT):
            if node.get_field("stereotype") == Stereotype.INSTANCE:
                continue
            stored, current = node.get_field("hash"), compute_hash_for_node(node)
            stale = "stale_hash" in (node.get_field("parse_dirty_reasons") or ())
            if not stale and stored is not None and node.id != template:
                continue
            if stored == current:
                continue
            path = Path(node.file_node().get_field("absolute_path"))
            title = node.get_label()
            _replace_once(path, render_end_marker(title, stored), render_end_marker(title, current))
    rebuilt = _build(root)
    assert not [
        node.id
        for _ns, member in rebuilt._live_graphs()
        for node in member.iter_by_kind(NodeKind.REQUIREMENT)
        if node.get_field("parse_dirty")
    ], "premise: the starting text is in canonical form"


def _canonical_project(setup: str, *, retired: bool) -> Callable[[Path], tuple[Path, Path]]:
    """The setup's project, its template Assertion retired in the text if *retired*."""
    make, spec, assertion, live, _copies, _unrelated = RESTORE_SETUPS[setup]

    def canonical(tmp_path: Path) -> tuple[Path, Path]:
        base, root = make(tmp_path)
        if retired:
            _replace_once(base / spec, f"A. {live}", "A. <RETIRED>")
        _record_hashes(root, assertion.rsplit("-", 1)[0])
        return base, root

    return canonical


def _restore_case(setup: str) -> Case:
    _make, _spec, assertion, live, _copies, unrelated = RESTORE_SETUPS[setup]
    return Case(
        _canonical_project(setup, retired=True),
        lambda g: g.update_assertion(assertion, live),
        _retitle(unrelated),
    )


def _template_repo(setup: str) -> str:
    """The name of the repository a copy of the setup's template records."""
    return "in-repo-template" if setup == "in-repo" else "library"


class TestBringingATemplateAssertionBack:
    """Validates REQ-p00017-H, REQ-p00014-B, REQ-o00062-G."""

    @RESTORE_CASES
    # Verifies: REQ-p00017-H, REQ-p00014-B
    def test_REQ_p00014_B_bringing_back_makes_the_copy_a_build_makes(self, tmp_path, setup):
        _make, _spec, assertion, live, copies, _unrelated = RESTORE_SETUPS[setup]
        pristine_base, pristine_root = _canonical_project(setup, retired=False)(
            tmp_path / "pristine"
        )
        pristine = _state(_build(pristine_root), pristine_base)

        def observe(graph, _base):
            # The label each copy holds before, or None where none exists.
            return {
                copy: (node.get_label() if (node := graph.find_by_id(copy)) else None)
                for copy in copies
            }

        graph, base, before = _assert_memory_equals_rebuild(
            tmp_path / "work", _restore_case(setup), observe
        )

        # The mutation brought the text back to what a pristine build reads.
        assert _diff(_state(graph, base), pristine) == {}
        assert _state(graph, base) == pristine
        original = graph.find_by_id(assertion)
        for copy_id in copies:
            copy = graph.find_by_id(copy_id)
            assert copy is not None
            assert copy.get_label() == live
            assert copy.get_label() == original.get_label()
            assert not copy.get_field("retired")
            assert copy.get_field("stereotype") == Stereotype.INSTANCE
            assert copy.get_field("template_repo") == _template_repo(setup)
            # Before, the copy did not exist (a Satisfies: naming the
            # Assertion alone) or said what the retired original said.
            assert before[copy_id] in (None, "<RETIRED>")
        # No Satisfies: naming the Assertion is left unresolved.
        assert not [
            f
            for _ns, member in graph._live_graphs()
            for f in member.unresolved_references()
            if f.edge_kind == "satisfies"
        ]

    @RESTORE_CASES
    @UNDO
    # Verifies: REQ-o00062-G
    def test_REQ_o00062_G_undo_of_bringing_back_returns_to_the_retired_state(
        self, tmp_path, setup, undo
    ):
        _assert_undo_restores(tmp_path, _restore_case(setup), undo)

    @RESTORE_CASES
    @pytest.mark.parametrize("how", RETIREMENTS)
    # Verifies: REQ-p00017-H, REQ-p00014-B, REQ-o00062-G
    def test_REQ_p00017_H_retiring_then_bringing_back_restores_the_build(
        self, tmp_path, setup, how
    ):
        _make, _spec, assertion, live, _copies, _unrelated = RESTORE_SETUPS[setup]
        base, root = _canonical_project(setup, retired=False)(tmp_path)
        graph = _build(root)
        pristine = _state(graph, base)

        _retire(assertion, how)(graph)
        retired = _state(graph, base)
        assert retired != pristine
        graph.update_assertion(assertion, live)
        assert _diff(_state(graph, base), pristine) == {}
        assert _state(graph, base) == pristine

        graph.undo_last()
        assert _diff(_state(graph, base), retired) == {}
        assert _state(graph, base) == retired
        graph.undo_last()
        assert _diff(_state(graph, base), pristine) == {}
        assert _state(graph, base) == pristine


class TestABuildMakesEachCopyAlike:
    """Validates REQ-p00014-B, REQ-p00014-O, REQ-d00128-J, REQ-d00129-C."""

    @RESTORE_CASES
    # Verifies: REQ-p00014-B, REQ-p00014-O, REQ-d00128-J, REQ-d00129-C
    def test_REQ_p00014_B_each_copy_has_the_shape_its_repository_gives_it(self, tmp_path, setup):
        make, _spec, assertion, _live, copies, _unrelated = RESTORE_SETUPS[setup]
        _base, root = make(tmp_path)
        graph = _build(root)
        original = graph.find_by_id(assertion)
        in_repo = setup == "in-repo"

        for copy_id in copies:
            copy = graph.find_by_id(copy_id)
            declaring = graph.find_by_id(copy_id.split("::", 1)[0])
            assert copy.get_field("stereotype") == Stereotype.INSTANCE
            assert copy.get_field("template_repo") == _template_repo(setup)
            # A line locates the original only in the repository holding it.
            for line_field in ("parse_line", "parse_end_line"):
                expected = original.get_field(line_field) if in_repo else None
                assert copy.get_field(line_field) == expected
            assert isinstance(copy.get_field("parse_line"), int) is in_repo
            assert {e.target.id for e in copy.iter_edges_by_kind(EdgeKind.INSTANCE)} == {assertion}
            # The declaring requirement satisfies the copied root -- the copy
            # itself where Satisfies: names the Assertion -- and its file
            # defines every copy.
            parents = [
                e.source for e in copy.iter_incoming_edges() if e.kind == EdgeKind.STRUCTURES
            ]
            copied_root = parents[0] if parents else copy
            satisfied = {e.target.id for e in declaring.iter_edges_by_kind(EdgeKind.SATISFIES)}
            assert copied_root.id in satisfied
            defined = {
                e.target.id for e in declaring.file_node().iter_edges_by_kind(EdgeKind.DEFINES)
            }
            assert {copy.id, copied_root.id} <= defined


# ---------------------------------------------------------------------------
# 6. A test citation in another member that binds to no test
# ---------------------------------------------------------------------------

ALPHA_TEST_SCANNING = """\
[scanning.test]
enabled = true
directories = ["tests"]
file_patterns = ["test_*.py"]

[scanning.spec]"""

ALPHA_TEST_FILE = "alpha/tests/test_alpha.py"
# The citation either opens the test it binds to, or follows the last test
# in the file and binds to nothing.
ALPHA_TESTS = {
    "bound": "# Verifies: REQ-p00001-A\ndef test_x():\n    pass\n",
    "unbound": "def test_x():\n    pass\n\n\n# Verifies: REQ-p00001-A\n",
}


def _foreign_citation_project(variant: str, *, draft: bool = False):
    """e2e-associated with an alpha test citing core's REQ-p00001-A."""

    def make(tmp_path: Path) -> tuple[Path, Path]:
        base = _copy(tmp_path, "e2e-associated", ("core", "alpha", "beta"))
        _replace_once(base / "alpha" / ".elspais.toml", "[scanning.spec]", ALPHA_TEST_SCANNING)
        _write(base / ALPHA_TEST_FILE, ALPHA_TESTS[variant])
        if draft:
            _replace_once(
                base / "core" / "spec" / "prd-core.md",
                "# REQ-p00001: Core Auth\n\n**Level**: prd | **Status**: Active",
                "# REQ-p00001: Core Auth\n\n**Level**: prd | **Status**: Draft",
            )
        return base, base / "core"

    return make


def _alpha_unbound(graph, base: Path) -> list[tuple[str, tuple[str, ...]]]:
    """(citing node, targets) of each unbound citation alpha records."""
    prefix = f"{base}/"
    member = dict(graph._live_graphs())["REQ-ALP"]
    return [(c.node_id.replace(prefix, ""), tuple(c.targets)) for c in member.unbound_citations()]


def _alpha_verifiers(graph, base: Path) -> set[tuple[str, tuple[str, ...]]]:
    """(test node, labels) of each VERIFIES edge from REQ-p00001 to an alpha test."""
    prefix = f"{base}/"
    return {
        (e.target.id.replace(prefix, ""), tuple(e.assertion_targets))
        for e in graph.find_by_id("REQ-p00001").iter_edges_by_kind(EdgeKind.VERIFIES)
        if e.target.id.startswith("test:")
    }


UNBOUND_CITER = f"test:{ALPHA_TEST_FILE}:5"


class TestAnUnboundCitationInAnotherMember:
    """Validates REQ-d00274-H, REQ-p00017-H, REQ-o00062-G."""

    @pytest.mark.parametrize("variant", list(ALPHA_TESTS))
    # Verifies: REQ-d00274-H
    def test_REQ_d00274_H_an_unbound_citation_binds_nothing_and_credits_nothing(
        self, tmp_path, variant
    ):
        base, root = _foreign_citation_project(variant)(tmp_path)
        graph = _build(root)

        tested = graph.find_by_id("REQ-p00001").get_metric("rollup_metrics").tested
        faults = [f for _ns, m in graph._live_graphs() for f in m.unresolved_references()]
        assert faults == []
        if variant == "bound":
            # The control: the same citation opening a test verifies it.
            assert _alpha_verifiers(graph, base) == {("test:tests/test_alpha.py::test_x", ("A",))}
            assert tested.total_by_label.get("A") == 1.0
            assert _alpha_unbound(graph, base) == []
        else:
            assert _alpha_verifiers(graph, base) == set()
            assert tested.total_by_label.get("A", 0.0) == 0.0
            assert tested.covered == 0.0
            assert _alpha_unbound(graph, base) == [(UNBOUND_CITER, ("REQ-p00001-A",))]

    @pytest.mark.parametrize("how", RETIREMENTS)
    # Verifies: REQ-d00274-H, REQ-p00017-H
    def test_REQ_d00274_H_retiring_the_target_reports_it_in_the_citing_member(self, tmp_path, how):
        case = Case(
            _foreign_citation_project("unbound"),
            _retire("REQ-p00001-A", how),
            _retitle("REQ-p00002"),
        )

        graph, base, before = _assert_memory_equals_rebuild(
            tmp_path, case, lambda g, b: _faults(g, b, "REQ-p00001")
        )

        assert before == set()
        assert _faults(graph, base, "REQ-p00001") == {
            ("REQ-ALP", UNBOUND_CITER, "verifies", FaultClass.UNKNOWN_ASSERTION)
        }
        (fault,) = dict(graph._live_graphs())["REQ-ALP"].unresolved_references()
        assert "holds no such Assertion" in fault.diagnostic
        assert _alpha_verifiers(graph, base) == set()
        assert _alpha_unbound(graph, base) == [(UNBOUND_CITER, ("REQ-p00001-A",))]

    # Verifies: REQ-d00274-H, REQ-p00017-H, REQ-o00062-P
    def test_REQ_d00274_H_deleting_a_draft_target_reports_it_in_the_citing_member(self, tmp_path):
        case = Case(
            _foreign_citation_project("unbound", draft=True),
            lambda g: g.delete_requirement("REQ-p00001"),
            _retitle("REQ-p00002"),
        )

        graph, base, _ = _assert_memory_equals_rebuild(tmp_path, case)

        reported = {f for f in _faults(graph, base, "REQ-p00001") if f[1] == UNBOUND_CITER}
        assert reported == {("REQ-ALP", UNBOUND_CITER, "verifies", FaultClass.UNKNOWN_REQUIREMENT)}
        assert _alpha_unbound(graph, base) == [(UNBOUND_CITER, ("REQ-p00001-A",))]

    @pytest.mark.parametrize(
        "mutation",
        ["delete", "update", "delete-draft"],
    )
    @UNDO
    # Verifies: REQ-o00062-G, REQ-d00274-H
    def test_REQ_o00062_G_undo_withdraws_the_other_members_fault(self, tmp_path, mutation, undo):
        if mutation == "delete-draft":
            case = Case(
                _foreign_citation_project("unbound", draft=True),
                lambda g: g.delete_requirement("REQ-p00001"),
                _retitle("REQ-p00002"),
            )
        else:
            case = Case(
                _foreign_citation_project("unbound"),
                _retire("REQ-p00001-A", mutation),
                _retitle("REQ-p00002"),
            )
        _assert_undo_restores(tmp_path, case, undo)


# ---------------------------------------------------------------------------
# 7. A requirement's hash covers its own Assertions alone
# ---------------------------------------------------------------------------

# (project, the requirement whose Satisfies: names one template Assertion,
# the copy of that Assertion hung beneath it)
OWN_HASH_SETUPS = {
    "in-repo": (_in_repo_project, "REQ-p00012", "REQ-p00012::REQ-p00010-A"),
    "xrepo-tenant-assertion": (
        _xrepo_project("tenant", assertion_satisfies=True),
        "TEN-p00001",
        "TEN-p00001::LIB-p00001-A",
    ),
}

OWN_HASH_CASES = pytest.mark.parametrize("setup", list(OWN_HASH_SETUPS))


def _own_assertions_hash(node) -> str:
    """The hash over the Assertions *node* structures, computed apart from the renderer."""
    return compute_normalized_hash(
        [
            (child.get_field("label"), child.get_label())
            for child in node.iter_children(edge_kinds={EdgeKind.STRUCTURES})
            if child.kind == NodeKind.ASSERTION
        ]
    )


def _record_own_hash(root: Path, req_id: str) -> None:
    """Write the hash of *req_id*'s own Assertions into its End marker."""
    node = _build(root).find_by_id(req_id)
    path = Path(node.file_node().get_field("absolute_path"))
    title = node.get_label()
    own = _own_assertions_hash(node)
    if node.get_field("hash") != own:
        _replace_once(
            path, render_end_marker(title, node.get_field("hash")), render_end_marker(title, own)
        )
    recorded = _build(root).find_by_id(req_id)
    assert recorded.get_field("hash") == own
    assert "stale_hash" not in (recorded.get_field("parse_dirty_reasons") or ())


def _own_hash_project(tmp_path: Path, setup: str):
    make, req_id, copy_id = OWN_HASH_SETUPS[setup]
    _base, root = make(tmp_path)
    _record_own_hash(root, req_id)
    graph = _build(root)
    declaring = graph.find_by_id(req_id)
    # Premise: the copy is among the declaring requirement's children.
    assert copy_id in {child.id for child in declaring.iter_children()}
    assert graph.find_by_id(copy_id).kind == NodeKind.ASSERTION
    return root, graph, declaring


class TestAHashCoversItsOwnAssertions:
    """Validates REQ-d00131-S."""

    @OWN_HASH_CASES
    # Verifies: REQ-d00131-S
    def test_REQ_d00131_S_hash_leaves_out_a_satisfies_copy(self, tmp_path, setup):
        _root, _graph, declaring = _own_hash_project(tmp_path, setup)

        assert compute_hash_for_node(declaring) == _own_assertions_hash(declaring)
        assert compute_hash_for_node(declaring) == declaring.get_field("hash")

    @OWN_HASH_CASES
    # Verifies: REQ-d00131-S
    def test_REQ_d00131_S_a_saved_edit_records_the_hash_the_next_build_reads(self, tmp_path, setup):
        _make, req_id, _copy_id = OWN_HASH_SETUPS[setup]
        root, graph, declaring = _own_hash_project(tmp_path, setup)

        graph.update_assertion(f"{req_id}-A", "The record SHALL name its author.")
        in_memory = graph.find_by_id(req_id).get_field("hash")
        assert in_memory == _own_assertions_hash(graph.find_by_id(req_id))
        _save(graph, root)

        rebuilt = _build(root).find_by_id(req_id)
        assert "stale_hash" not in (rebuilt.get_field("parse_dirty_reasons") or ())
        assert rebuilt.get_field("hash") == _own_assertions_hash(rebuilt)
        assert rebuilt.get_field("hash") == in_memory

    @OWN_HASH_CASES
    # Verifies: REQ-d00131-S
    def test_REQ_d00131_S_a_changelog_row_records_the_saved_hash(self, tmp_path, setup):
        _make, req_id, _copy_id = OWN_HASH_SETUPS[setup]
        root, graph, _declaring = _own_hash_project(tmp_path, setup)

        graph.update_assertion(f"{req_id}-A", "The record SHALL name its author.")
        _save(graph, root)
        written = _add_changelog_for_active_mutations(
            graph, root, {req_id}, "Name the author.", {"name": "Tester", "id": "tester"}
        )
        assert written == 1

        rebuilt = _build(root).find_by_id(req_id)
        (row, *_older) = rebuilt.get_field("changelog")
        assert row["hash"] == rebuilt.get_field("hash")
        assert row["hash"] == _own_assertions_hash(rebuilt)
