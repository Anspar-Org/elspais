# Verifies: REQ-d00271-A
"""The documented fault-code examples, executed.

REQ-d00271-A obliges the codes to be "documented with an example of input
that produces each".  An example is not a property of a code: it is a
property of a code under a particular identifier configuration and a
particular graph, which is why the table in ``docs/cli/linking.md`` states
both above itself and why no string constant could carry it.  A comparison
against a constant would prove the table is *spelled* consistently with the
code names; it would never prove the table is TRUE.

So the table is executed instead.  A repository is built holding exactly the
graph the table's preamble promises -- the default identifier configuration
and ``REQ-d00001`` with assertions A and B -- one source file per documented
input, and one real ``build_graph()`` over it.  What the tool then reports
for each file is compared against what the row claims.

The doc is the source for three of the four things checked: the input, the
class, and the set of ``E_*`` codes are read out of the markdown at test
time, so a row edited to claim something untrue fails here.  The fourth --
which item of a list carried which verdict, and what a binding row actually
bound to -- is held below, because the Codes column states it in prose
("on the first item", "(both instances)") that no parser should be asked to
interpret.  The two sets of inputs are asserted equal in both directions, so
a row added to the doc without an executed case fails just as loudly as a
case whose row was deleted.

One file per row is load-bearing, not tidiness: consecutive reference
comments join as a continued list (REQ-d00269-H), and the final row's
premise is that no keyword stands above it.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from elspais.graph.factory import build_graph
from elspais.graph.GraphNode import NodeKind
from elspais.graph.reference_faults import FaultCode
from elspais.graph.relations import EdgeKind

LINKING_DOC = (
    Path(__file__).resolve().parents[1] / "src" / "elspais" / "docs" / "cli" / "linking.md"
)

# The repository the table's preamble promises: the default identifier
# configuration, and REQ-d00001 carrying assertions A and B.
_CONFIG = """\
version = 5
[project]
name = "fault-code-examples"
namespace = "REQ"
[levels.dev]
rank = 1
letter = "d"
implements = ["dev"]
[scanning.spec]
directories = ["spec"]
[scanning.code]
directories = ["src"]
[scanning.test]
enabled = false
directories = []
"""

_SPEC = """\
# REQ-d00001: A documented requirement

**Level**: dev | **Status**: Active

### Assertions

A. The system SHALL do the first thing.

B. The system SHALL do the second thing.

*End* *A documented requirement*
"""


# ---------------------------------------------------------------------------
# The documented table, read out of the markdown
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DocRow:
    """One row of the fault-code table, as the documentation states it."""

    input: str
    fault_class: str | None
    codes: frozenset[str]


def _read_table() -> list[DocRow]:
    """Every row of the fault-code table in ``linking.md``.

    The table is located by its header rather than by line number, so
    inserting prose above it does not silently empty this list -- an empty
    result is asserted against below, since a table this test could not find
    would otherwise let every row pass by vacancy.
    """
    lines = LINKING_DOC.read_text(encoding="utf-8").splitlines()
    header = next(
        (i for i, line in enumerate(lines) if line.strip().startswith("| Input | Class | Codes |")),
        None,
    )
    assert header is not None, f"no fault-code table found in {LINKING_DOC}"
    rows: list[DocRow] = []
    for line in lines[header + 2 :]:
        if not line.strip().startswith("|"):
            break
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        assert len(cells) == 3, f"malformed table row: {line!r}"
        spelled = re.search(r"`([^`]*)`", cells[0])
        assert spelled is not None, f"row states no input in backticks: {line!r}"
        klass = None if cells[1] in {"—", "-", ""} else cells[1]
        rows.append(
            DocRow(
                input=spelled.group(1),
                fault_class=klass,
                codes=frozenset(re.findall(r"E_[A-Z_]+", cells[2])),
            )
        )
    return rows


DOC_ROWS = {row.input: row for row in _read_table()}


# ---------------------------------------------------------------------------
# What each documented input is expected to produce, in full
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Expected:
    """The complete outcome of one documented input.

    ``faults``/``style``/``identifier_form``/``undeclared`` are exhaustive:
    a finding the row does not list fails the case, so an undocumented
    consequence cannot hide behind a documented one.

    Attributes:
        faults: ``(fault class label, target as written, codes)`` per
            reference fault, order-insensitive.
        style: Keyword-form codes reported for the line.
        identifier_form: ``(text as written, codes)`` per non-canonical
            spelling that bound anyway.
        undeclared: Whether the line is reported as an undeclared
            relationship.
        binds: ``(requirement id, assertion labels)`` per relationship the
            line actually produced.  Absence of a fault is not evidence a
            reference bound, so every binding row names what it bound.
    """

    faults: tuple[tuple[str, str, tuple[str, ...]], ...] = ()
    style: tuple[str, ...] = ()
    identifier_form: tuple[tuple[str, tuple[str, ...]], ...] = ()
    undeclared: bool = False
    binds: tuple[tuple[str, tuple[str, ...]], ...] = ()


_E = FaultCode

CASES: dict[str, Expected] = {
    "# Implements: REQ-d00001": Expected(binds=(("REQ-d00001", ()),)),
    "# Implements: not a reference": Expected(
        faults=(("malformed", "not a reference", (_E.SYNTAX_ERROR, _E.NOT_AN_IDENTIFIER)),),
    ),
    "# Implements: REQ-d00001+A": Expected(
        faults=(("malformed", "REQ-d00001+A", (_E.SYNTAX_ERROR, _E.WRONG_ASSERTION_SEPARATOR)),),
    ),
    "# Implements: REQ-d00001-A-B": Expected(
        faults=(("malformed", "REQ-d00001-A-B", (_E.SYNTAX_ERROR, _E.WRONG_MULTI_SEPARATOR)),),
    ),
    "# Implements: REQ-d00001-1": Expected(
        faults=(("malformed", "REQ-d00001-1", (_E.SYNTAX_ERROR, _E.LABEL_OUT_OF_SERIES)),),
    ),
    # The value is what is wrong, not the spelling: five configured digits
    # bound the component at 99999, and no repadding makes 123456 fit.
    "# Implements: REQ-d123456": Expected(
        faults=(("malformed", "REQ-d123456", (_E.SYNTAX_ERROR, _E.COMPONENT_OUT_OF_RANGE)),),
    ),
    "# Implements: REQ-d00001-AB": Expected(
        faults=(
            ("malformed", "REQ-d00001-AB", (_E.SYNTAX_ERROR, _E.IDENTIFIER_WITH_TRAILING_TEXT)),
        ),
    ),
    # The row's prose: trailing text on the first item, and a second item
    # that reads as a name no repository claims -- which is what
    # ``unknown_namespace`` says.
    "# Implements: REQ-d00001 (A, C)": Expected(
        faults=(
            (
                "malformed",
                "REQ-d00001 (A",
                (_E.SYNTAX_ERROR, _E.IDENTIFIER_WITH_TRAILING_TEXT),
            ),
            ("unknown_namespace", "C)", (_E.SYNTAX_ERROR,)),
        ),
    ),
    "# Implements: REQ-d00001-A - one environment": Expected(
        faults=(
            (
                "malformed",
                "REQ-d00001-A - one environment",
                (_E.SYNTAX_ERROR, _E.IDENTIFIER_WITH_TRAILING_TEXT),
            ),
        ),
    ),
    "# Implements: REQ-d00001-A + B": Expected(
        faults=(
            (
                "malformed",
                "REQ-d00001-A + B",
                (_E.SYNTAX_ERROR, _E.IDENTIFIER_WITH_TRAILING_TEXT),
            ),
        ),
    ),
    "# Implements: REQ-d00001-A # why": Expected(binds=(("REQ-d00001", ("A",)),)),
    # The doc's own fixture holds no REQ-d00002, so the second named item
    # is an unknown requirement in its own right. Stated here rather than
    # loosened away: the row's claim is about the empty slot, and the
    # companion fault is what the promised graph really produces.
    "# Implements: REQ-d00001,,REQ-d00002": Expected(
        faults=(
            ("malformed", "", (_E.SYNTAX_ERROR, _E.EMPTY_ITEM)),
            ("unknown_requirement", "REQ-d00002", (_E.SYNTAX_ERROR,)),
        ),
        binds=(("REQ-d00001", ()),),
    ),
    "# Implements: REQ-d00001,": Expected(
        faults=(("malformed", "", (_E.SYNTAX_ERROR, _E.TRAILING_SEPARATOR)),),
        binds=(("REQ-d00001", ()),),
    ),
    "# Implements:": Expected(
        faults=(("malformed", "", (_E.SYNTAX_ERROR, _E.EMPTY_REFERENCE_LIST)),),
    ),
    "# Implements: WIDGET-42": Expected(
        faults=(("unknown_namespace", "WIDGET-42", (_E.SYNTAX_ERROR,)),),
    ),
    "# Implements: REQ-d00099": Expected(
        faults=(("unknown_requirement", "REQ-d00099", (_E.SYNTAX_ERROR,)),),
    ),
    "# Implements: REQ-d00001-Z": Expected(
        faults=(("unknown_assertion", "REQ-d00001-Z", (_E.SYNTAX_ERROR,)),),
    ),
    # "(both instances)": two faults, one per position, and neither binds.
    "# Implements: REQ-d00001, REQ-d00001": Expected(
        faults=(
            ("forbidden", "REQ-d00001", (_E.SYNTAX_ERROR, _E.DUPLICATE_ITEM)),
            ("forbidden", "REQ-d00001", (_E.SYNTAX_ERROR, _E.DUPLICATE_ITEM)),
        ),
    ),
    "# Refines: REQ-d00001": Expected(
        faults=(("forbidden", "REQ-d00001", (_E.SYNTAX_ERROR,)),),
    ),
    "# Implements: req-d00001": Expected(
        identifier_form=(("req-d00001", (_E.NON_CANONICAL_SPELLING, _E.WRONG_CASE)),),
        binds=(("REQ-d00001", ()),),
    ),
    "# Implements: REQ-d1": Expected(
        identifier_form=(("REQ-d1", (_E.NON_CANONICAL_SPELLING, _E.WRONG_PADDING)),),
        binds=(("REQ-d00001", ()),),
    ),
    "#Implements: REQ-d00001": Expected(
        style=(_E.KEYWORD_NO_MARKER_SPACE,),
        binds=(("REQ-d00001", ()),),
    ),
    "# implements: REQ-d00001": Expected(
        style=(_E.KEYWORD_WRONG_CASE,),
        binds=(("REQ-d00001", ()),),
    ),
    "# **Implements**: REQ-d00001": Expected(
        style=(_E.KEYWORD_MARKDOWN_EMPHASIS_OFF_MARKDOWN,),
        binds=(("REQ-d00001", ()),),
    ),
    "#   REQ-d00001": Expected(undeclared=True),
}


# ---------------------------------------------------------------------------
# The repository, and what the tool reported for each documented input
# ---------------------------------------------------------------------------


@dataclass
class Reported:
    """Everything the build reported against one documented input's file."""

    faults: list = field(default_factory=list)
    style: list = field(default_factory=list)
    identifier_form: list = field(default_factory=list)
    undeclared: list = field(default_factory=list)
    binds: list = field(default_factory=list)


def _file_stem(index: int) -> str:
    return f"row_{index:02d}"


@pytest.fixture(scope="module")
def reported(tmp_path_factory) -> dict[str, Reported]:
    """Build the promised repository once and index findings by input."""
    inputs = sorted(CASES)
    repo = tmp_path_factory.mktemp("fault_code_examples")
    (repo / ".elspais.toml").write_text(_CONFIG, encoding="utf-8")
    (repo / "spec").mkdir()
    (repo / "spec" / "dev.md").write_text(_SPEC, encoding="utf-8")
    (repo / "src").mkdir()
    for index, text in enumerate(inputs):
        stem = _file_stem(index)
        (repo / "src" / f"{stem}.py").write_text(
            f"{text}\ndef {stem}():\n    return 1\n", encoding="utf-8"
        )
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)

    graph = build_graph(repo_root=repo, scan_code=True, scan_tests=False)

    found = {text: Reported() for text in inputs}
    by_stem = {_file_stem(i): value for i, value in enumerate(inputs)}

    def owner(source_id: str) -> str | None:
        for stem, text in by_stem.items():
            if f"/{stem}.py" in source_id or f":{stem}.py" in source_id:
                return text
        return None

    for fault in graph.unresolved_references():
        text = owner(fault.source_id)
        if text is not None:
            found[text].faults.append(
                (fault.fault_class.label, fault.target_id, tuple(fault.codes))
            )
    for finding in graph.style_findings():
        text = owner(finding.source_id)
        if text is not None:
            found[text].style.append(finding.code)
    for finding in graph.identifier_form_findings():
        text = owner(finding.source_id)
        if text is not None:
            found[text].identifier_form.append((finding.text, tuple(finding.codes)))
    for finding in graph.undeclared_relationships():
        text = owner(finding.source_id)
        if text is not None:
            found[text].undeclared.append(finding.text)

    for entry in graph.iter_repos():
        if entry.graph is None:
            continue
        for node in entry.graph.iter_by_kind(NodeKind.CODE):
            file_node = node.file_node()
            if file_node is None:
                continue
            text = owner(str(file_node.get_field("relative_path") or ""))
            if text is None:
                continue
            for edge in node.iter_incoming_edges():
                if edge.kind in (EdgeKind.IMPLEMENTS, EdgeKind.REFINES):
                    found[text].binds.append(
                        (edge.source.id, tuple(getattr(edge, "assertion_targets", ()) or ()))
                    )
    return found


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


# Verifies: REQ-d00271-A
def test_every_documented_row_has_an_executed_example():
    """The doc and this test name the same inputs, in both directions.

    Without this, a row added to the table would be documented and never
    executed, and a case whose row was deleted would keep passing against
    nothing.
    """
    assert DOC_ROWS, "the fault-code table was found but holds no rows"
    documented = set(DOC_ROWS)
    executed = set(CASES)
    assert documented - executed == set(), (
        f"documented inputs with no executed example: {sorted(documented - executed)}"
    )
    assert executed - documented == set(), (
        f"executed examples no longer documented: {sorted(executed - documented)}"
    )


# Verifies: REQ-d00271-A
@pytest.mark.parametrize("text", sorted(CASES), ids=lambda t: t.replace(" ", "_"))
def test_documented_example_produces_what_the_row_claims(text: str, reported):
    """Each row's input, run through a real build, reports what the row says.

    Three claims are checked against the markdown itself -- the class, the
    codes, and (for a row claiming neither) that nothing faulted -- and the
    full reported outcome is checked against the case, so a consequence the
    row does not mention cannot pass unnoticed.
    """
    row = DOC_ROWS[text]
    case = CASES[text]
    seen = reported[text]

    observed_classes = {label for label, _target, _codes in seen.faults}
    observed_codes = {code for _label, _target, codes in seen.faults for code in codes}
    observed_codes.update(seen.style)
    observed_codes.update(code for _t, codes in seen.identifier_form for code in codes)

    if row.fault_class is None:
        assert seen.faults == [], (
            f"{text!r} is documented as producing no reference fault, but reported {seen.faults}"
        )
    else:
        assert row.fault_class in observed_classes, (
            f"{text!r} is documented as class {row.fault_class!r}, "
            f"but reported classes {sorted(observed_classes)}"
        )

    assert row.codes <= observed_codes, (
        f"{text!r} is documented as carrying {sorted(row.codes)}, "
        f"but reported {sorted(observed_codes)}"
    )

    assert sorted(seen.faults) == sorted(case.faults)
    assert sorted(seen.style) == sorted(case.style)
    assert sorted(seen.identifier_form) == sorted(case.identifier_form)
    assert bool(seen.undeclared) is case.undeclared
    assert sorted(seen.binds) == sorted(case.binds)


# Verifies: REQ-d00271-A
def test_every_fault_code_is_documented():
    """REQ-d00271-A obliges every code to be documented with an example.

    The codes are enumerated from the class rather than listed here: a list
    written out would let a code added later go undocumented without
    anything saying so, which is the exact obligation this checks.
    """
    codes = {
        value
        for name, value in vars(FaultCode).items()
        if not name.startswith("_") and isinstance(value, str) and value.startswith("E_")
    }
    assert codes, "no fault codes found on FaultCode"
    text = LINKING_DOC.read_text(encoding="utf-8")
    undocumented = sorted(code for code in codes if code not in text)
    assert undocumented == [], (
        f"fault codes with no documentation in {LINKING_DOC.name}: {undocumented}"
    )
