# Verifies: REQ-p00014-V, REQ-p00014-R, REQ-p00017-B
"""A journey declares what it validates in exactly one place: its metadata.

REQ-p00014-V fixes *where* the declaration may live, for the same reason
REQ-p00014-U fixes how it is spelled. A journey renders from a cached body
that is regenerated from the live VALIDATES edges on save, so a journey
holding a second copy of the declaration is written back carrying both --
one current, one as originally typed, naming different requirements after
any rename. The rule removes the second copy rather than trying to keep the
two consistent.

The four behaviours pinned here are one contract seen from four sides:

- a declaration inside a section produces no relationship, and is reported
  under REQ-p00014-R rather than silently dropped;
- the metadata declaration still produces the relationship (the control:
  without it the first test passes even if journeys stopped working);
- renaming a cited requirement reconciles the citing journey's cached body,
  so the rendered file names the new identifier (REQ-p00017-B); and
- reading and writing a metadata declaration round-trips -- byte-identical
  on a second save, with exactly one ``Validates:`` line.

These build small on-disk projects rather than reusing ``canonical_graph``:
the section form is invalid input, which the canonical fixture (rightly)
does not carry, and the separator pairs are per-project configuration.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from elspais.graph.factory import build_graph
from elspais.graph.relations import EdgeKind
from elspais.graph.render import render_file, render_save

# The shipped defaults and a repository that configures neither of them.
# Both are asserted to behave identically: the separators are configuration,
# so nothing downstream may treat one pair as *the* pair.
SEPARATOR_PAIRS = [("-", "+"), ("/", "&")]

_CONFIG = """\
version = 3

[project]
name = "journey-validates-placement"
namespace = "REQ"

[id-patterns.assertions]
label_style = "uppercase"
separator = "{sep}"
multi_separator = "{multi}"

[levels.prd]
rank = 1
letter = "p"
implements = []

[scanning.journey]
directories = ["spec"]
"""

_SPEC = """\
# REQ-p00001: Widget

The system provides widgets.

## Assertions

A. The system SHALL frob.

B. The system SHALL twiddle.

*End* *Widget*
"""

# The two layouts under test. They cite the same references and differ only
# in where the citation sits.
_JOURNEY_METADATA_FORM = """\
## JNY-001: Widget Journey

**Actor**: User
**Goal**: Use widgets
Validates: {ref}

## Steps

1. Open the widget.

*End* *JNY-001*
"""

_JOURNEY_SECTION_FORM = """\
## JNY-001: Widget Journey

**Actor**: User
**Goal**: Use widgets

## Steps

1. Open the widget.

## Validates

Validates: {ref}

*End* *JNY-001*
"""


def _make_project(
    tmp_path: Path,
    journey_template: str,
    sep: str = "-",
    multi: str = "+",
) -> Path:
    """A project whose only journey cites two assertions of one requirement.

    The citation is spelled with the separators this project configures, so
    the reference is always valid input; only its *placement* varies.
    """
    project = tmp_path / "journeys"
    (project / "spec").mkdir(parents=True)
    (project / ".elspais.toml").write_text(_CONFIG.format(sep=sep, multi=multi), encoding="utf-8")
    (project / "spec" / "prd.md").write_text(_SPEC, encoding="utf-8")
    (project / "spec" / "journeys.md").write_text(
        journey_template.format(ref=f"REQ-p00001{sep}A{multi}B"), encoding="utf-8"
    )
    return project


def _build(project: Path):
    return build_graph(config_path=project / ".elspais.toml", repo_root=project, scan_code=False)


def _validates_targets(graph) -> list[str]:
    """Every assertion label reaching JNY-001 over a VALIDATES edge.

    A VALIDATES edge runs requirement -> journey, so on the journey these
    are INCOMING edges. Reading them off the journey's outgoing edges would
    report an empty list however the journey was authored.
    """
    journey = graph.find_by_id("JNY-001")
    assert journey is not None, "JNY-001 should be in the graph"
    return sorted(
        label
        for edge in journey.iter_incoming_edges()
        if edge.kind == EdgeKind.VALIDATES
        for label in edge.assertion_targets
    )


# ---------------------------------------------------------------------------
# B (the control, stated first): the metadata declaration is read.
# ---------------------------------------------------------------------------


# Verifies: REQ-p00014-V
@pytest.mark.parametrize("sep,multi", SEPARATOR_PAIRS)
def test_REQ_p00014_V_metadata_declaration_produces_validates_edges(sep, multi, tmp_path):
    """The one admitted placement still works, whichever characters this
    repository divides its references with.

    This is the control for the section-form test below: without it, a build
    that produced no VALIDATES edges at all would read as compliance.
    """
    graph = _build(_make_project(tmp_path, _JOURNEY_METADATA_FORM, sep, multi))

    assert _validates_targets(graph) == ["A", "B"], (
        "Both labels cited in the journey's metadata must reach the graph as "
        f"targeted VALIDATES edges (sep={sep!r}, multi={multi!r})"
    )
    assert not graph.broken_references(), (
        "A declaration in the one place the rule admits must resolve, not be "
        f"reported; got {graph.broken_references()}"
    )


# ---------------------------------------------------------------------------
# A: the section declaration is reported, not silently dropped.
# ---------------------------------------------------------------------------


# Verifies: REQ-p00014-V, REQ-p00014-R
def test_REQ_p00014_V_section_declaration_produces_no_validates_edge(tmp_path):
    """A `Validates:` line inside a section validates nothing."""
    graph = _build(_make_project(tmp_path, _JOURNEY_SECTION_FORM))

    assert _validates_targets(graph) == [], (
        "A declaration outside the journey's metadata must produce no " "validation relationship"
    )
    requirement = graph.find_by_id("REQ-p00001")
    assert requirement is not None
    assert not any(
        edge.kind == EdgeKind.VALIDATES for edge in requirement.iter_outgoing_edges()
    ), "the cited requirement must not gain UAT credit from a misplaced declaration"


# Verifies: REQ-p00014-R, REQ-p00014-V
def test_REQ_p00014_R_section_declaration_is_reported_as_a_broken_reference(tmp_path):
    """Refusing to read the declaration is only safe if the author is told.

    A journey that validates less than its author wrote must not look like a
    journey that validated everything.
    """
    graph = _build(_make_project(tmp_path, _JOURNEY_SECTION_FORM))

    reported = [
        br
        for br in graph.broken_references()
        if br.edge_kind == "validates" and br.source_id == "JNY-001"
    ]
    assert len(reported) == 1, (
        "the declaration the builder refused to read must be reported exactly "
        f"once against the journey that made it; got {graph.broken_references()}"
    )
    assert (
        "REQ-p00001" in reported[0].target_id
    ), f"the report must name what was declared; got {reported[0].target_id!r}"
    # Substance, not wording: the author needs to learn where the declaration
    # belongs, and the exact sentence is free to drift.
    assert "metadata" in reported[0].diagnostic.lower(), (
        "the diagnostic must point the author at the metadata, otherwise the "
        f"report says only that something is wrong; got {reported[0].diagnostic!r}"
    )


# ---------------------------------------------------------------------------
# C: renaming a cited requirement reconciles the citing journey.
# ---------------------------------------------------------------------------


# Verifies: REQ-p00017-B
@pytest.mark.parametrize("sep,multi", SEPARATOR_PAIRS)
def test_REQ_p00017_B_rename_reconciles_a_citing_journey(sep, multi, tmp_path):
    """A journey cites the renamed requirement in its metadata, and renders
    from a cached body -- so the cache is a reference held in the graph to
    the former identifier and must move with the rename.

    Left unreconciled, the graph reports the new identifier while the text
    that would be written to disk still names the old one.
    """
    graph = _build(_make_project(tmp_path, _JOURNEY_METADATA_FORM, sep, multi))

    graph.rename_node("REQ-p00001", "REQ-p00002")

    journey = graph.find_by_id("JNY-001")
    rendered = render_file(journey.file_node())
    assert (
        f"REQ-p00002{sep}A{multi}B" in rendered
    ), f"the rendered journey file must cite the new identifier; got {rendered!r}"
    assert "REQ-p00001" not in rendered, (
        "the journey's cached body still names the former identifier -- saving "
        f"would write it back to disk; got {rendered!r}"
    )


# ---------------------------------------------------------------------------
# D: reading and writing a metadata declaration round-trips.
# ---------------------------------------------------------------------------


def _save_round(project: Path) -> tuple[list[str], bytes]:
    """Rebuild from disk, dirty the journey, save, and read the file back.

    The journey has to be genuinely re-rendered for this to test anything:
    the declaration is regenerated from the live edges only on save, so a
    round that wrote nothing would compare a file to itself.
    """
    graph = _build(project)
    graph.update_journey_field("JNY-001", "goal", "Use widgets thoroughly")
    result = render_save(graph, repo_root=project)
    return result["files_modified"], (project / "spec" / "journeys.md").read_bytes()


# Verifies: REQ-p00014-V
@pytest.mark.parametrize("sep,multi", SEPARATOR_PAIRS)
def test_REQ_p00014_V_metadata_declaration_round_trips_unchanged(sep, multi, tmp_path):
    """Save the journey twice: the second save must reproduce the first byte
    for byte, and the file must carry exactly one `Validates:` line.

    Both halves matter. A journey whose declaration is regenerated from the
    graph *and* preserved as typed comes back with two contradictory lines
    on the first save, and accumulates on every save after that.
    """
    project = _make_project(tmp_path, _JOURNEY_METADATA_FORM, sep, multi)

    first_written, first = _save_round(project)
    second_written, second = _save_round(project)

    journeys_md = str(project / "spec" / "journeys.md")
    assert journeys_md in first_written and journeys_md in second_written, (
        "both rounds must actually rewrite the journey file, otherwise the "
        "comparison below is a file against itself"
    )
    assert first == second, (
        "saving an already-saved journey must not change it; got\n"
        f"{first.decode()}\n---\n{second.decode()}"
    )

    declarations = [
        line for line in first.decode("utf-8").splitlines() if line.startswith("Validates:")
    ]
    assert declarations == [f"Validates: REQ-p00001{sep}A{multi}B"], (
        "a journey declares what it validates in exactly one place, spelled "
        f"in this repository's own grammar; got {declarations}"
    )
