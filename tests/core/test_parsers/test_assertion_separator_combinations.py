# Verifies: REQ-d00082-E, REQ-p00014-T
"""Regression: configured assertion separator/multi-separator combinations
must parse correctly end-to-end (CUR-1568 Task 13).

Root cause: the boundary between a requirement ID and its first assertion
label was hardcoded to the "-"/"_" characters, ignoring the configured
``[id-patterns.assertions] separator``. Repos configuring a non-"-"/"_"
separator (e.g. "/") silently lost the assertion suffix when extracting
``Verifies:`` references from test files -- the multi-assertion pattern
match stopped right before the separator character, dropping the rest of
the reference and producing a blanket (whole-requirement) edge instead of
a targeted one.

This reproduces the bug through the real production pipeline
(``elspais.graph.factory.build_graph``) against an on-disk project, mirroring
the confirmed manual repro: one PRD with assertions A, B, C and one test
file with a single ``# Verifies: <ref>`` comment.

A field incident showed that journey ``Validates:`` references are the same
risk surface: under a non-"-"/"_" separator, a correctly-styled ref wires
assertion-targeted VALIDATES edges (REQ -> journey, per the ``Validates:``
field behavior specified in spec/requirements-spec.md), while
a ref that still uses "-" produces a hard broken reference. The tests below
extend the same separator/multi-separator matrix to cover that path.

Every separator in the matrix is a character a reference list does not
already spend: "," divides one reference from the next, so a configuration
naming it as an assertion separator is refused outright (REQ-d00251-M) and
cannot appear here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from elspais.commands.health import _fault_location
from elspais.graph.GraphNode import NodeKind
from elspais.graph.reference_faults import FaultClass, FaultCode
from elspais.graph.relations import EdgeKind

_SPEC = """\
# REQ-p-widget: Widget

The system provides widgets.

## Assertions

A. The system SHALL frob.

B. The system SHALL twiddle.

C. The system SHALL blort.

*End* *REQ-p-widget*
"""

_CONFIG_TEMPLATE = """\
version = 3

[project]
name = "septest"
namespace = "REQ"

[id-patterns]
canonical = "{{namespace}}-{{level.letter}}-{{component}}"

[id-patterns.component]
style = "{style}"

[id-patterns.assertions]
label_style = "uppercase"
separator = "{sep}"
multi_separator = "{multi}"

[levels.prd]
rank = 1
letter = "p"
implements = []

[scanning.test]
enabled = true
directories = ["tests"]

[scanning.journey]
directories = ["spec"]
"""

_JOURNEY_TEMPLATE = """\
# JNY-T-01: Test Journey

The user exercises the widget end to end.

Validates: {ref}

*End* *JNY-T-01*
"""


def _make_project(
    tmp_path: Path,
    sep: str,
    multi: str,
    ref: str,
    journey_ref: str | None = None,
    style: str = "kebab-case",
) -> Path:
    """Build a minimal on-disk project: one REQ with assertions A/B/C and
    one test file with a single ``# Verifies: <ref>`` comment.

    When ``journey_ref`` is given, also writes a journey file
    (``JNY-T-01``) whose ``Validates:`` line carries that ref, so tests can
    exercise the journey ``Validates:`` wiring path alongside (or instead
    of) the CODE/TEST ``Verifies:`` path.
    """
    project = tmp_path / "project"
    (project / "spec").mkdir(parents=True)
    (project / "spec" / "prd.md").write_text(_SPEC, encoding="utf-8")

    (project / "tests").mkdir(parents=True)
    (project / "tests" / "test_widget.py").write_text(
        f"# Verifies: {ref}\ndef test_widget():\n    assert True\n",
        encoding="utf-8",
    )

    if journey_ref is not None:
        (project / "spec" / "journeys.md").write_text(
            _JOURNEY_TEMPLATE.format(ref=journey_ref),
            encoding="utf-8",
        )

    (project / ".elspais.toml").write_text(
        _CONFIG_TEMPLATE.format(sep=sep, multi=multi, style=style),
        encoding="utf-8",
    )
    return project


# Shared matrix of (separator, multi_separator, ref, expected assertion
# labels) reused by the CODE/TEST ``Verifies:`` test below and the journey
# ``Validates:`` tests further down. The project's component style is
# kebab-case, so every separator here is a character a component cannot
# contain.
_SEPARATOR_COMBINATIONS = [
    ("/", "+", "REQ-p-widget/A+C", ["A", "C"]),
    ("/", "/", "REQ-p-widget/A/C", ["A", "C"]),
    ("|", "+", "REQ-p-widget|A+C", ["A", "C"]),
    (".", "+", "REQ-p-widget.A+C", ["A", "C"]),
    ("~", "&", "REQ-p-widget~A&C", ["A", "C"]),
]


@pytest.mark.parametrize("sep,multi,ref,expected_labels", _SEPARATOR_COMBINATIONS)
def test_separator_combinations_parse_targeted_refs(sep, multi, ref, expected_labels, tmp_path):
    """A `Verifies:` ref using the *configured* separator/multi-separator
    must produce VERIFIES edges carrying exactly the referenced assertion
    labels -- never an empty (blanket) assertion_targets list."""
    from elspais.graph.factory import build_graph

    project = _make_project(tmp_path, sep, multi, ref)
    graph = build_graph(
        config_path=project / ".elspais.toml",
        repo_root=project,
        scan_code=False,
    )

    widget = graph.find_by_id("REQ-p-widget")
    assert widget is not None, "REQ-p-widget should be in the graph"

    test_nodes = list(graph.iter_by_kind(NodeKind.TEST))
    assert len(test_nodes) == 1, f"Expected exactly one TEST node, got {len(test_nodes)}"
    test_node = test_nodes[0]

    all_targets: list[str] = []
    for edge in widget.iter_outgoing_edges():
        if edge.target.id == test_node.id:
            all_targets.extend(edge.assertion_targets)

    assert all_targets, (
        f"Expected VERIFIES edge(s) from REQ-p-widget to the test with "
        f"non-empty assertion_targets for ref {ref!r} (sep={sep!r}, "
        f"multi={multi!r}); got a blanket edge with empty assertion_targets "
        f"instead (the assertion suffix was dropped during extraction)."
    )
    assert sorted(all_targets) == sorted(
        expected_labels
    ), f"Expected assertion_targets {expected_labels}, got {sorted(all_targets)}"


# Verifies: REQ-d00082-E, REQ-p00014-T
@pytest.mark.parametrize("sep,multi,ref,expected_labels", _SEPARATOR_COMBINATIONS)
def test_journey_validates_across_separator_combinations(
    sep, multi, ref, expected_labels, tmp_path
):
    """A `Validates:` ref using the *configured* separator/multi-separator must
    produce assertion-targeted VALIDATES edges (REQ -> journey, per the
    ``Validates:`` field behavior specified in spec/requirements-spec.md)
    carrying exactly the referenced assertion labels, with
    ``rollup_metrics.uat_coverage.direct_labels`` matching.
    """
    from elspais.graph.factory import build_graph

    project = _make_project(tmp_path, sep, multi, ref, journey_ref=ref)
    graph = build_graph(
        config_path=project / ".elspais.toml",
        repo_root=project,
        scan_code=False,
    )

    widget = graph.find_by_id("REQ-p-widget")
    assert widget is not None, "REQ-p-widget should be in the graph"

    jny = graph.find_by_id("JNY-T-01")
    assert jny is not None, "JNY-T-01 should be in the graph"

    validates_targets: list[str] = []
    for edge in widget.iter_outgoing_edges():
        if edge.kind == EdgeKind.VALIDATES and edge.target.id == jny.id:
            validates_targets.extend(edge.assertion_targets)

    rollup = widget.get_metric("rollup_metrics")

    assert sorted(validates_targets) == sorted(expected_labels), (
        f"Expected VALIDATES assertion_targets {expected_labels} for ref "
        f"{ref!r} (sep={sep!r}, multi={multi!r}), got {sorted(validates_targets)}"
    )
    assert rollup.uat_coverage.direct_labels == set(expected_labels)


# Verifies: REQ-d00082-E, REQ-p00014-R, REQ-d00272-A, REQ-d00252-G, REQ-d00252-K
def test_journey_dash_style_ref_under_slash_config_is_hard_broken(tmp_path):
    """A journey `Validates:` ref that still uses "-" when the project is
    configured with a "/" separator must remain a hard broken reference
    naming the journey as source, and not presumed foreign -- no associates
    are configured, and there is nothing else in the federation the target
    could belong to. A journey's `Validates:` is now read through the same
    reader as a code or test annotation (REQ-d00272-K), so the item never
    parsing under this repository's own grammar is a grammar-level verdict
    -- MALFORMED, carrying SYNTAX_ERROR -- rather than a later-stage
    UNKNOWN_REQUIREMENT (REQ-d00272-A forbids reporting a later stage than
    the one reading actually reached).

    What names the cause is what REQ-d00252-K says names one: the code
    (``E_IDENTIFIER_WITH_TRAILING_TEXT`` -- the dash-style suffix reads as
    trailing text on the correctly-spelled component), the file and the line
    the reference was written on, and that code's documented meaning. All
    three reach the surface that reports it, so no prose is carried: a
    sentence guessing at a separator would be a fourth naming the input does
    not determine, and REQ-d00252-K bars prose from naming a cause the code
    does not."""
    from elspais.graph.factory import build_graph

    sep, multi = "/", "+"
    correctly_styled_ref = "REQ-p-widget/A+C"
    dash_style_ref = "REQ-p-widget-A+C"

    project = _make_project(tmp_path, sep, multi, correctly_styled_ref, journey_ref=dash_style_ref)
    graph = build_graph(
        config_path=project / ".elspais.toml",
        repo_root=project,
        scan_code=False,
    )

    jny = graph.find_by_id("JNY-T-01")
    assert jny is not None, "JNY-T-01 should be in the graph"

    journey_broken = [br for br in graph.broken_references() if br.source_id == jny.id]
    assert (
        len(journey_broken) == 1
    ), f"Expected exactly one broken ref from {jny.id}, got {journey_broken}"
    br = journey_broken[0]

    assert br.target_id == dash_style_ref
    assert br.edge_kind == "validates"
    assert br.presumed_foreign is False, (
        "No associates are configured, so there is no other repository this "
        "reference could belong to."
    )
    assert br.fault_class is FaultClass.MALFORMED
    assert FaultCode.SYNTAX_ERROR in br.codes
    assert (
        FaultCode.IDENTIFIER_WITH_TRAILING_TEXT in br.codes
    ), f"Expected the specific code that now names the cause, got {br.codes!r}"

    # The other half of what names a cause: where the reference was written.
    file_path, line = _fault_location(graph, br.source_id, br.line)
    assert file_path, "a cause is named with the file the reference was written in"
    assert file_path.endswith(".md")
    assert line, "a cause is named with the line the reference was written on"

    assert br.diagnostic == "", (
        "The code and the location name the cause; prose guessing at a "
        f"separator would name one the input does not determine: {br.diagnostic!r}"
    )


# --------------------------------------------------------------------------- #
# Off-config separator residue in CODE/TEST references
#
# A reference that cites an assertion with a separator the repo is NOT
# configured for (e.g. "REQ-o-storageRules/Z" under separator "-") must be
# treated as ONE malformed reference token in every context that accepts
# references -- spec metadata lines, code comments, test comments -- so it
# fails resolution and surfaces as a broken reference naming the failure
# class (REQ-p00014-T, REQ-p00014-R).
#
# The spec-metadata path already does this. The reference-extraction path
# used by code and test files truncates at the "/" instead, silently
# producing a valid *blanket* edge to the real requirement and reporting
# nothing.
# --------------------------------------------------------------------------- #

_RESIDUE_CONFIG_TEMPLATE = """\
version = 4

[project]
name = "residuetest"
namespace = "REQ"

[id-patterns]
canonical = "{{namespace}}-{{level.letter}}-{{component}}"

[id-patterns.component]
style = "camelCase"

[id-patterns.assertions]
label_style = "uppercase"
separator = "{sep}"
multi_separator = "+"

[levels.ops]
rank = 1
letter = "o"
implements = ["o"]

[levels.dev]
rank = 2
letter = "d"
implements = ["d", "o"]

[scanning.spec]
directories = ["spec"]

[scanning.code]
directories = ["src"]
"""

_RESIDUE_SPEC_TEMPLATE = """\
# REQ-o-storageRules: Storage rules

The system stores things.

## Assertions

A. The system SHALL store.

B. The system SHALL retain.

*End* *REQ-o-storageRules*

# REQ-d-storageImpl: Storage implementation

**Implements**: {spec_ref}

The storage detail.

## Assertions

A. The system SHALL flush.

*End* *REQ-d-storageImpl*
"""


def _make_residue_project(
    tmp_path: Path,
    sep: str,
    code_ref: str,
    spec_ref: str,
) -> Path:
    """Build a minimal on-disk project carrying the *same* reference string in
    two contexts: a spec ``**Implements**:`` metadata line and a code-comment
    ``# Implements:`` line.

    Both contexts are governed by the owning repository's reference-acceptance
    rules (REQ-p00014-T), so both must reach the same verdict for the same
    string.
    """
    project = tmp_path / "residue-project"
    (project / "spec").mkdir(parents=True)
    (project / "spec" / "spec.md").write_text(
        _RESIDUE_SPEC_TEMPLATE.format(spec_ref=spec_ref), encoding="utf-8"
    )

    (project / "src").mkdir(parents=True)
    (project / "src" / "thing.py").write_text(
        f"# Implements: {code_ref}\ndef thing():\n    return None\n",
        encoding="utf-8",
    )

    (project / ".elspais.toml").write_text(
        _RESIDUE_CONFIG_TEMPLATE.format(sep=sep), encoding="utf-8"
    )
    return project


def _build_residue_graph(project: Path):
    from elspais.graph.factory import build_graph

    return build_graph(
        config_path=project / ".elspais.toml",
        repo_root=project,
        scan_code=True,
    )


def _code_node_id(graph) -> str:
    code_nodes = list(graph.iter_by_kind(NodeKind.CODE))
    assert len(code_nodes) == 1, f"Expected exactly one CODE node, got {len(code_nodes)}"
    return code_nodes[0].id


# Verifies: REQ-p00014-T, REQ-p00014-R
def test_code_comment_off_config_residue_is_a_broken_reference(tmp_path):
    """A code comment citing ``<REQ>/Z`` when the configured assertion
    separator is "-" must yield a broken reference carrying the FULL
    ``<REQ>/Z`` string and fault_class MALFORMED -- not a
    silently-truncated blanket edge to ``<REQ>``."""
    project = _make_residue_project(
        tmp_path,
        sep="-",
        code_ref="REQ-o-storageRules/Z",
        spec_ref="REQ-o-storageRules-A",
    )
    graph = _build_residue_graph(project)

    code_id = _code_node_id(graph)
    req = graph.find_by_id("REQ-o-storageRules")
    assert req is not None, "REQ-o-storageRules should be in the graph"

    code_edges = [
        edge
        for edge in req.iter_outgoing_edges()
        if edge.kind == EdgeKind.IMPLEMENTS and edge.target.id == code_id
    ]
    assert not code_edges, (
        "An off-config assertion suffix must not be truncated into a valid "
        f"blanket IMPLEMENTS edge; got edges with assertion_targets "
        f"{[e.assertion_targets for e in code_edges]}"
    )

    code_broken = [br for br in graph.broken_references() if br.source_id == code_id]
    assert (
        len(code_broken) == 1
    ), f"Expected exactly one broken reference from the code node, got {code_broken}"
    br = code_broken[0]
    assert br.target_id == "REQ-o-storageRules/Z", (
        "The broken reference must carry the whole malformed token, not the "
        f"truncated requirement prefix; got {br.target_id!r}"
    )
    assert br.edge_kind == "implements"
    # The item's leading token is this repository's own declared namespace,
    # so the reader's grammar-level verdict (REQ-d00272-C) is MALFORMED, not
    # UNKNOWN_REQUIREMENT -- the item never matched any member's identifier
    # at all, rather than matching and then naming an absent node.
    assert br.fault_class is FaultClass.MALFORMED, (
        "A reference that fails to produce a valid relationship must name the "
        f"failure class (REQ-p00014-R); got {br.fault_class}"
    )


# Verifies: REQ-p00014-T
def test_spec_and_code_contexts_agree_on_the_same_malformed_reference(tmp_path):
    """The owning repository's reference-acceptance rules apply identically in
    every context that accepts references: the same string in a spec metadata
    line and in a code comment must break the same way."""
    ref = "REQ-o-storageRules/Z"
    project = _make_residue_project(tmp_path, sep="-", code_ref=ref, spec_ref=ref)
    graph = _build_residue_graph(project)

    code_id = _code_node_id(graph)

    spec_targets = {
        br.target_id for br in graph.broken_references() if br.source_id == "REQ-d-storageImpl"
    }
    code_targets = {br.target_id for br in graph.broken_references() if br.source_id == code_id}

    assert spec_targets == {
        ref
    }, f"Spec metadata context should already report {ref!r} broken; got {spec_targets}"
    assert code_targets == spec_targets, (
        "The code-comment context must reach the same verdict as the spec "
        f"context for the same reference string; spec reported {spec_targets}, "
        f"code reported {code_targets}"
    )


# Verifies: REQ-p00014-T, REQ-d00082-E
def test_test_comment_off_config_residue_is_a_broken_reference(tmp_path):
    """The TEST context is governed by the same acceptance rules: a
    ``# Verifies: <REQ>/Z`` comment under separator "-" must break rather than
    truncate into a blanket VERIFIES edge."""
    from elspais.graph.factory import build_graph

    project = _make_project(tmp_path, "-", "+", "REQ-p-widget/Z", style="camelCase")
    graph = build_graph(
        config_path=project / ".elspais.toml",
        repo_root=project,
        scan_code=False,
    )

    widget = graph.find_by_id("REQ-p-widget")
    assert widget is not None, "REQ-p-widget should be in the graph"

    test_nodes = list(graph.iter_by_kind(NodeKind.TEST))
    assert len(test_nodes) == 1, f"Expected exactly one TEST node, got {len(test_nodes)}"
    test_id = test_nodes[0].id

    verifies_edges = [
        edge
        for edge in widget.iter_outgoing_edges()
        if edge.kind == EdgeKind.VERIFIES and edge.target.id == test_id
    ]
    assert not verifies_edges, (
        "An off-config assertion suffix must not be truncated into a valid "
        f"blanket VERIFIES edge; got assertion_targets "
        f"{[e.assertion_targets for e in verifies_edges]}"
    )

    test_broken = [br for br in graph.broken_references() if br.source_id == test_id]
    assert [br.target_id for br in test_broken] == [
        "REQ-p-widget/Z"
    ], f"Expected one broken reference carrying the whole malformed token, got {test_broken}"


# Verifies: REQ-p00014-T, REQ-d00082-E
def test_slash_configured_repo_still_parses_slash_suffix(tmp_path):
    """When the repo IS configured with separator "/", ``<REQ>/A`` is the
    legitimate assertion suffix and must keep resolving to a targeted edge --
    "/" is only residue relative to a different configured separator."""
    project = _make_residue_project(
        tmp_path,
        sep="/",
        code_ref="REQ-o-storageRules/A",
        spec_ref="REQ-o-storageRules/A",
    )
    graph = _build_residue_graph(project)

    code_id = _code_node_id(graph)
    req = graph.find_by_id("REQ-o-storageRules")
    assert req is not None, "REQ-o-storageRules should be in the graph"

    targets: list[str] = []
    for edge in req.iter_outgoing_edges():
        if edge.kind == EdgeKind.IMPLEMENTS and edge.target.id == code_id:
            targets.extend(edge.assertion_targets)

    assert sorted(targets) == [
        "A"
    ], f"Expected a targeted IMPLEMENTS edge for assertion A, got {sorted(targets)}"
    assert not [
        br for br in graph.broken_references() if br.source_id == code_id
    ], "A correctly-styled reference under the configured separator must not be reported broken"


# Verifies: REQ-p00014-T, REQ-d00082-E
def test_same_separator_multi_assertion_ref_still_resolves(tmp_path):
    """Regression guard: ``<REQ>-A+B`` under separator "-" must still expand to
    both assertions."""
    project = _make_residue_project(
        tmp_path,
        sep="-",
        code_ref="REQ-o-storageRules-A+B",
        spec_ref="REQ-o-storageRules-A",
    )
    graph = _build_residue_graph(project)

    code_id = _code_node_id(graph)
    req = graph.find_by_id("REQ-o-storageRules")
    assert req is not None, "REQ-o-storageRules should be in the graph"

    targets: list[str] = []
    for edge in req.iter_outgoing_edges():
        if edge.kind == EdgeKind.IMPLEMENTS and edge.target.id == code_id:
            targets.extend(edge.assertion_targets)

    assert sorted(targets) == [
        "A",
        "B",
    ], f"Expected both assertions A and B to be targeted, got {sorted(targets)}"
    assert not [br for br in graph.broken_references() if br.source_id == code_id]


# Verifies: REQ-p00014-T, REQ-d00082-E
def test_bare_requirement_reference_stays_a_blanket_edge(tmp_path):
    """Negative control: with no residue at all, ``Implements: <REQ>`` remains a
    legitimate blanket reference and must NOT be reported broken."""
    project = _make_residue_project(
        tmp_path,
        sep="-",
        code_ref="REQ-o-storageRules",
        spec_ref="REQ-o-storageRules",
    )
    graph = _build_residue_graph(project)

    code_id = _code_node_id(graph)
    req = graph.find_by_id("REQ-o-storageRules")
    assert req is not None, "REQ-o-storageRules should be in the graph"

    blanket = [
        edge
        for edge in req.iter_outgoing_edges()
        if edge.kind == EdgeKind.IMPLEMENTS and edge.target.id == code_id
    ]
    assert len(blanket) == 1, f"Expected one blanket IMPLEMENTS edge, got {blanket}"
    assert (
        blanket[0].assertion_targets == []
    ), f"Expected a blanket edge with no assertion targets, got {blanket[0].assertion_targets}"
    assert (
        not graph.broken_references()
    ), f"A bare requirement reference must not be reported broken; got {graph.broken_references()}"


# --------------------------------------------------------------------------- #
# Journey `Validates:` round-trip: what the tool reads, it writes back in the
# owning repository's own spelling (REQ-p00014-U).
#
# A journey's `Validates:` line is a list of references like any other. Its
# items are divided on the list separator, each item is read under the
# repository's identifier grammar, and the line the tool writes back is
# derived from the resulting edges -- so a repository configuring "/" and "&"
# must never see "-" and "+" come back out.
# --------------------------------------------------------------------------- #

_ROUNDTRIP_CONFIG = """\
version = 3

[project]
name = "roundtrip"
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

_ROUNDTRIP_SPEC = """\
# REQ-p00001: Widget

The system provides widgets.

## Assertions

A. The system SHALL frob.

B. The system SHALL twiddle.

*End* *Widget*
"""

_ROUNDTRIP_JOURNEY = """\
### JNY-001: Widget Journey

**Actor**: User
**Goal**: Use widgets
Validates: {ref}

## Steps

1. Open the widget.
2. Frob it.

*End* *Widget Journey*
"""


def _make_roundtrip_project(tmp_path: Path, sep: str, multi: str) -> Path:
    """A project whose only journey validates two assertions of one
    requirement, cited with the separators that project configures."""
    project = tmp_path / "roundtrip"
    (project / "spec").mkdir(parents=True)
    (project / ".elspais.toml").write_text(
        _ROUNDTRIP_CONFIG.format(sep=sep, multi=multi), encoding="utf-8"
    )
    (project / "spec" / "prd.md").write_text(_ROUNDTRIP_SPEC, encoding="utf-8")
    (project / "spec" / "journeys.md").write_text(
        _ROUNDTRIP_JOURNEY.format(ref=f"REQ-p00001{sep}A{multi}B"), encoding="utf-8"
    )
    return project


# The shipped defaults and a repository that configures neither of them. Both
# are asserted to behave identically: the separators are configuration, so
# nothing downstream may treat one pair as the pair.
_ROUNDTRIP_PAIRS = [("-", "+"), ("/", "&")]


# Verifies: REQ-p00014-U, REQ-p00014-T
@pytest.mark.parametrize("sep,multi", _ROUNDTRIP_PAIRS)
def test_journey_validates_two_assertions_of_one_requirement(sep, multi, tmp_path):
    """Two labels of one requirement on a `Validates:` line are two targeted
    VALIDATES edges, whichever characters this repository divides them with."""
    from elspais.graph.factory import build_graph

    project = _make_roundtrip_project(tmp_path, sep, multi)
    graph = build_graph(config_path=project / ".elspais.toml", repo_root=project, scan_code=False)

    req = graph.find_by_id("REQ-p00001")
    assert req is not None, "REQ-p00001 should be in the graph"
    jny = graph.find_by_id("JNY-001")
    assert jny is not None, "JNY-001 should be in the graph"

    edges = [
        edge
        for edge in req.iter_outgoing_edges()
        if edge.kind == EdgeKind.VALIDATES and edge.target.id == jny.id
    ]
    targets = sorted(label for edge in edges for label in edge.assertion_targets)
    assert targets == ["A", "B"], (
        f"Both cited labels must reach the graph as targeted VALIDATES edges "
        f"(sep={sep!r}, multi={multi!r}); got {targets}"
    )
    assert req.get_metric("rollup_metrics").uat_coverage.direct_labels == {"A", "B"}
    assert not graph.broken_references(), (
        "A reference spelled in the repository's own grammar must resolve; "
        f"got {graph.broken_references()}"
    )


# Verifies: REQ-p00014-U
@pytest.mark.parametrize("sep,multi", _ROUNDTRIP_PAIRS)
def test_journey_validates_line_is_written_back_in_the_configured_spelling(sep, multi, tmp_path):
    """The `Validates:` line the tool writes is composed from the live edges
    under this repository's separators.

    The journey block reconstructed after a mutation is rebuilt from the
    live VALIDATES edges, not copied from the source text, so the
    `Validates:` line it carries is derived output. It must spell the
    reference the way this repository spells one.
    """
    from elspais.graph.factory import build_graph

    project = _make_roundtrip_project(tmp_path, sep, multi)
    graph = build_graph(config_path=project / ".elspais.toml", repo_root=project, scan_code=False)

    graph.update_journey_field("JNY-001", "goal", "Use widgets thoroughly")
    body = graph.find_by_id("JNY-001").get_field("body")
    header_block = body.split("\n\n")[0]

    assert "**Goal**: Use widgets thoroughly" in header_block, (
        "the header block should be the reconstructed one; got " f"{header_block!r}"
    )
    assert f"Validates: REQ-p00001{sep}A{multi}B" in header_block, (
        f"The derived Validates line must use the configured separators "
        f"({sep!r}, {multi!r}); got {header_block!r}"
    )
    for other_sep, other_multi in _ROUNDTRIP_PAIRS:
        if (other_sep, other_multi) == (sep, multi):
            continue
        assert f"REQ-p00001{other_sep}A{other_multi}B" not in header_block, (
            "No spelling but this repository's own may be written back; got " f"{header_block!r}"
        )
