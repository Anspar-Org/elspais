# Verifies: REQ-d00082-G
"""Reading a reference in a source file yields the parts its grammar defines.

REQ-d00082-G obliges a read reference to be delivered as the structure the
grammar accounts for -- namespace, level, component, assertion labels --
rather than as the run of characters that happened to match.

The two are separable observationally.  A repository configuring a numeric,
five-digit, zero-padded component admits ``REQ-p42-A`` (the component
pattern is ``\\d{1,5}``), but its canonical spelling of that identifier is
``REQ-p00042-A``.  A read that hands back the matched text yields
``REQ-p42-A`` -- a string naming no node, so the reference breaks.  Only a
read that goes through the parsed parts and re-renders them yields
``REQ-p00042-A`` and wires the edge.

Re-rendering from parts is not licence to repair.  There is one notation,
and a reference spelled with any other punctuation -- ``REQ_p42_A`` -- is a
reference spelled wrongly, not the same identifier in a second notation.
Reading without regard to case and padding does not extend to any further
difference (REQ-d00212-S), so such a spelling resolves to nothing and is
reported.  The two obligations bound each other: padding is settled from
the parts, and everything past case and padding is left as written.

These are file-level reads through ``build_graph``, not resolver calls: the
obligation is on what a consumer of a scanned annotation receives, and an
intact resolver can still be consumed wrongly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from elspais.graph.reference_faults import FaultClass
from elspais.graph.relations import EdgeKind

_SPEC = """\
# REQ-p00042: Widget

The system provides widgets.

## Assertions

A. The system SHALL frob.

B. The system SHALL twiddle.

C. The system SHALL blort.

*End* *REQ-p00042*
"""

_CONFIG = """\
version = 5

[project]
name = "partstest"
namespace = "REQ"

[id-patterns]
canonical = "{namespace}-{level.letter}{component}"

[id-patterns.component]
style = "numeric"
digits = 5
leading_zeros = true

[id-patterns.assertions]
label_style = "uppercase"
separator = "-"
multi_separator = "+"

[levels.prd]
rank = 1
letter = "p"
implements = []

[scanning.code]
directories = ["src"]

[scanning.test]
enabled = true
directories = ["tests"]
"""


def _make_project(tmp_path: Path, *, code: str | None = None, test: str | None = None) -> Path:
    """A project whose component is five-digit zero-padded, with at most one
    code file and one test file carrying the reference under test."""
    project = tmp_path / "project"
    (project / "spec").mkdir(parents=True)
    (project / "spec" / "prd.md").write_text(_SPEC, encoding="utf-8")
    (project / "src").mkdir()
    (project / "tests").mkdir()
    if code is not None:
        (project / "src" / "widget.py").write_text(code, encoding="utf-8")
    if test is not None:
        (project / "tests" / "test_widget.py").write_text(test, encoding="utf-8")
    (project / ".elspais.toml").write_text(_CONFIG, encoding="utf-8")
    return project


def _build(project: Path):
    from elspais.graph.factory import build_graph

    return build_graph(
        config_path=project / ".elspais.toml",
        repo_root=project,
    )


def _targets(graph, kind: EdgeKind) -> list[str]:
    """The assertion labels every *kind* edge leaving REQ-p00042 names."""
    widget = graph.find_by_id("REQ-p00042")
    assert widget is not None, "REQ-p00042 should be in the graph"
    labels: list[str] = []
    for edge in widget.iter_outgoing_edges():
        if edge.kind is kind:
            labels.extend(edge.assertion_targets)
    return sorted(labels)


def _broken(graph) -> list[str]:
    return [br.target_id for br in graph.broken_references()]


@pytest.mark.parametrize(
    "keyword,edge_kind",
    [
        ("Implements", EdgeKind.IMPLEMENTS),
        ("Verifies", EdgeKind.VERIFIES),
    ],
)
def test_annotation_reference_is_read_as_parts_not_matched_text(keyword, edge_kind, tmp_path):
    """An annotation spelled with an unpadded component wires an edge to the
    padded identifier the grammar renders from its parts.

    The matched text (``REQ-p42-A``) names nothing; only the re-rendered
    parts (``REQ-p00042-A``) reach a node.
    """
    ref = "REQ-p42-A"
    body = f"# {keyword}: {ref}\ndef frob():\n    return 1\n"
    if keyword == "Verifies":
        project = _make_project(tmp_path, test=body.replace("def frob", "def test_frob"))
    else:
        project = _make_project(tmp_path, code=body)
    graph = _build(project)

    assert _targets(graph, edge_kind) == ["A"], (
        f"Expected a {edge_kind.name} edge from REQ-p00042 naming A for the annotation "
        f"'{keyword}: {ref}'; the reference was read as its matched text rather than as "
        f"the parts its grammar defines, so it named no node."
    )
    assert ref not in _broken(graph), (
        f"{ref!r} was carried through as written and left as a broken reference; a read "
        f"reference must yield its parts, not the text that matched."
    )


def test_multi_assertion_reference_yields_each_label_as_its_own_part(tmp_path):
    """The assertion labels a reference names are parts of it, so a
    multi-assertion reference is yielded as one reference per label.

    A read that hands back the matched text yields the single string
    ``REQ-p42-A+C``, which names neither assertion.
    """
    project = _make_project(
        tmp_path,
        test="# Verifies: REQ-p42-A+C\ndef test_widget():\n    assert True\n",
    )
    graph = _build(project)

    assert _targets(graph, EdgeKind.VERIFIES) == ["A", "C"], (
        "Expected VERIFIES edges from REQ-p00042 naming A and C for the annotation "
        "'REQ-p42-A+C'; the labels are parts of the reference, and a read that yields "
        "the matched text whole names neither of them."
    )
    assert "REQ-p42-A+C" not in _broken(graph)


# Verifies: REQ-d00212-S
def test_an_underscore_spelling_is_not_repaired_into_one_that_resolves(tmp_path):
    """An underscore-spelled reference resolves to nothing and is reported.

    ``REQ_p42_A`` differs from what the configuration admits in its
    punctuation, which is neither case nor padding, so nothing may repair it
    into ``REQ-p00042-A`` (REQ-d00212-S). This is the counterpart of the
    padding test above and its exact boundary: an unpadded component IS
    settled from the parts and binds, and a substituted separator is NOT and
    does not. Repairing it would build an edge whose author wrote no such
    reference -- silently, since a reference that resolved is a reference
    that looked fine.
    """
    project = _make_project(
        tmp_path,
        test="# Verifies: REQ_p42_A\ndef test_widget():\n    assert True\n",
    )
    graph = _build(project)

    assert _targets(graph, EdgeKind.VERIFIES) == [], (
        "'REQ_p42_A' was repaired into a spelling that resolves and wired an "
        "edge from REQ-p00042; a difference past case and padding must resolve "
        "to nothing."
    )
    # Resolving to nothing is only honest because the item is still reported:
    # it is carried through verbatim, never quietly dropped.
    broken = graph.broken_references()
    assert [br.target_id for br in broken] == ["REQ_p42_A"], (
        f"the unresolvable spelling must be reported as written; got {_broken(graph)}"
    )
    assert broken[0].edge_kind == "verifies"
    # No repository declares a namespace ending where this item's does, since
    # the boundary comes from the grammar's own separator and `REQ_` is not
    # `REQ-`; so it is attributed to no repository rather than described as a
    # local identifier written badly.
    assert broken[0].fault_class is FaultClass.UNKNOWN_NAMESPACE, (
        f"got {broken[0].fault_class!r} with codes {broken[0].codes!r}"
    )
