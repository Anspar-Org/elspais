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

A Python test function name is the same obligation under a second notation:
the name can spell every boundary only as ``_``, so ``test_REQ_p42_A``
matches on a text a canonical identifier never contains.  Its parts are
identical to those of ``REQ-p00042-A``, and that is what the read must
yield.

These are file-level reads through ``build_graph``, not resolver calls: the
obligation is on what a consumer of a scanned annotation receives, and an
intact resolver can still be consumed wrongly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

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
version = 3

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


def test_test_function_name_reference_is_read_as_parts(tmp_path):
    """A reference spelled in a Python test function's name is yielded as
    its parts, so the underscore notation and the unpadded component both
    disappear from what the consumer receives.

    The matched text is ``REQ_p42_A``; the parts render as
    ``REQ-p00042-A``, which is the only spelling that names a node.
    """
    project = _make_project(
        tmp_path,
        test="def test_widget_REQ_p42_A():\n    assert True\n",
    )
    graph = _build(project)

    assert _targets(graph, EdgeKind.VERIFIES) == ["A"], (
        "Expected a VERIFIES edge from REQ-p00042 naming A for the test function "
        "'test_widget_REQ_p42_A'; the reference read out of the name was handed back "
        "as matched text rather than as the parts its grammar defines."
    )
    assert not any(
        "_" in target or "p42" in target for target in _broken(graph)
    ), f"Underscore-notation text leaked through as a reference: {_broken(graph)}"
