# Implements: REQ-p00001-B, REQ-p00003-A, REQ-p00003-B
# Implements: REQ-d00052-B, REQ-d00052-C, REQ-d00052-G
"""
elspais.commands.trace - Generate traceability matrix command.

Uses the graph-based system to generate traceability reports in various formats.
Commands only work with graph data (zero file I/O for reading requirements).

OUTPUT FORMATS:
- markdown: Table with columns based on the report preset
- csv: The same values, comma-separated with proper escaping
- html: Basic styled HTML table
- json: Full requirement data including body, assertions, hash, file_path

REPORT PRESETS (--report):
- minimal: ID, Title, Status only (quick overview)
- standard: ID, Title, Level, Status, Implements (default)
- full: All fields including Body, Assertions, Hash, Code/Test refs

INTERACTIVE VIEW (--view):
- Uses elspais.html.HTMLGenerator
- Generates interactive HTML with collapsible hierarchy
- Default output: traceability_view.html
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from elspais.graph.federated import FederatedGraph

from elspais.graph import NodeKind
from elspais.graph.values import (
    CARRIED_DIMENSION,
    COUNT_PARTS,
    FLAG_CARRIED,
    MEASURE_KEY_SEPARATOR,
    PART_ATTRIBUTED,
    SCALAR_PARTS,
    VALUE_SPECS,
    UnofferedValues,
    figure_cell,
    flag_cell,
    header_for,
    scalar_cell,
    scalar_value,
    structured_row,
)

# Implements: REQ-d00282-A
# Every value this report can state. A selection is judged against this set
# and nothing narrower: the values a report offers are the tool's own, so a
# name among them that does not resolve is a mistake rather than a difference
# (REQ-d00282-F). Offering a further value changes nothing an already
# expressible selection states (REQ-d00282-G) -- a selection names what it
# names, and a default set is a separate thing that may grow.
# Group-only values are left out: every row here is ONE requirement, and a
# count of the requirements in a row that is one requirement is a name for
# nothing. Offering it would be offering a value that could only be blank.
OFFERED_VALUES: tuple[str, ...] = tuple(
    key for key, spec in VALUE_SPECS.items() if not spec.group_only
)


def _data_key(value: str) -> str:
    """The ``_get_node_data`` field a value reads.

    A measure is keyed beneath its dimension in the selection vocabulary
    (``tested.immediate_direct``) and beside it in the data (``tested_immediate_direct``);
    this is the one place the two spellings meet.
    """
    return value.replace(MEASURE_KEY_SEPARATOR, "_")


@dataclass
class ReportPreset:
    """Configuration for a report preset.

    ``values`` is a named DEFAULT set (REQ-d00084-B) -- what a reader who names
    no values is answered with. A selection stated on the invocation replaces
    it (REQ-d00282-A) and reaches the formatters as their ``values`` argument.
    Detail flags (include_body, etc.) are set independently via CLI flags.
    """

    name: str
    values: list[str]
    include_body: bool = False
    include_assertions: bool = False
    include_code_refs: bool = False
    include_test_refs: bool = False
    dimension: str = ""
    """Dimension group filter.  'uat' restricts the report to UAT coverage."""


# Implements: REQ-d00084-B
# Define report presets — value sets only, detail flags set via CLI
REPORT_PRESETS = {
    "minimal": ReportPreset(
        name="minimal",
        values=["id", "title", "level", "status"],
    ),
    "standard": ReportPreset(
        name="standard",
        values=[
            "id",
            "title",
            "level",
            "status",
            "implemented",
            "tested",
            "verified",
            "uat_coverage",
            "uat_verified",
            "code_tested",
            "lcov_tested",
        ],
    ),
    "full": ReportPreset(
        name="full",
        values=[
            "id",
            "title",
            "level",
            "status",
            "implemented",
            "tested",
            "verified",
            "uat_coverage",
            "uat_verified",
            "code_tested",
            "lcov_tested",
        ],
    ),
}

DEFAULT_PRESET = "standard"

# Values for the UAT dimension report -- excludes all code-dimension values.
# A synthetic "journeys" value is appended by the formatters.
_UAT_VALUES = ["id", "title", "level", "status", "uat_coverage", "uat_verified"]


def _get_uat_journey_verdict(journey_node) -> str:
    """Derive a simple display verdict from a journey's verification metric.

    Delegates to ``JourneyVerification.verdict`` so the mapping is
    defined in one place.

    Returns:
        'fail'       if any verifying test failed.
        'pass'       if the journey is fully verified (all steps pass).
        'partial'    if some steps pass but not all.
        'unverified' if no verifying tests are recorded.
    """
    v = journey_node.get_metric("journey_verification")
    if v is None:
        return "unverified"
    return v.verdict


def _get_uat_journeys(req_node) -> list[dict]:
    """Return [{id, verdict}] for each journey that validates this requirement.

    Reads OUTGOING VALIDATES edges on the requirement node.
    The builder wires these as ``parent_req.link(journey, EdgeKind.VALIDATES)`` so
    the requirement is the edge source and the journey is the edge target.
    The verdict is derived from the journey's ``journey_verification`` metric;
    call :func:`_get_uat_journey_verdict` for the mapping.
    """
    from elspais.graph.relations import EdgeKind

    results = []
    for edge in req_node.iter_outgoing_edges():
        if edge.kind == EdgeKind.VALIDATES:
            journey = edge.target
            results.append({"id": journey.id, "verdict": _get_uat_journey_verdict(journey)})
    return results


# Implements: REQ-d00279-C
def compute_trace(
    graph: FederatedGraph,
    config: dict,
    params: dict[str, str],
) -> dict:
    """Compute trace data for engine.call.  Returns {"nodes": [...], "scope": [...]}.

    Reads the scope AND the value selection out of ``params`` because this is
    the path a report takes when a serving process answers it: a selection that
    did not survive the trip would make a daemon-served report disagree with a
    locally computed one, about which requirements it is about (REQ-d00279-C)
    or about which facts it states (REQ-d00282-E).
    """
    from elspais.commands._scope import resolve_scope_for_report, scope_disclosure
    from elspais.commands._values import values_from_params
    from elspais.graph.values import resolve_values

    result = resolve_scope_for_report(graph, params, config)
    scope_ids = None if len(result.ids) == result.population else result.ids
    nodes = [_get_node_data(node, graph) for node in _scoped_requirements(graph, scope_ids)]
    payload: dict = {"nodes": nodes, "scope": scope_disclosure(result)}
    # Implements: REQ-d00282-A+F
    # Resolved here as well as where the report is rendered, so a serving
    # process refuses a selection it cannot honour in full rather than
    # answering with a report nobody asked for. Carried back so any consumer
    # of this payload states the values the selection named; where no
    # selection was made the named default set decides and is not this
    # process's to choose.
    selection = values_from_params(params)
    if selection is not None:
        payload["values"] = list(resolve_values(selection, OFFERED_VALUES))
    return payload


def _compact_labels(labels: set[str]) -> str:
    """Compact sequential assertion labels into ranges.

    Single-letter labels: A,B,C,F,H,I,J,K,L -> A-C,F,H-L
    Numeric labels: 1,2,3,4,5,10,11,12 -> 1-5,10-12
    Text labels (non-sequential): returned comma-separated, no ranges.
    """
    if not labels:
        return ""

    sorted_labels = sorted(labels)

    # Detect label type: all single uppercase letters, all numeric, or mixed/text
    all_single_alpha = all(len(lb) == 1 and lb.isalpha() and lb.isupper() for lb in sorted_labels)
    all_numeric = all(lb.isdigit() for lb in sorted_labels)

    if not all_single_alpha and not all_numeric:
        return ",".join(sorted_labels)

    # Build runs of consecutive values (sort by actual value, not lexicographic)
    if all_single_alpha:
        values = sorted(ord(lb) for lb in sorted_labels)
    else:
        values = sorted(int(lb) for lb in sorted_labels)

    runs: list[tuple[int, int]] = []
    for v in values:
        if runs and v == runs[-1][1] + 1:
            runs[-1] = (runs[-1][0], v)
        else:
            runs.append((v, v))

    # Format runs back to labels
    parts = []
    for start, end in runs:
        if all_single_alpha:
            s, e = chr(start), chr(end)
        else:
            s, e = str(start), str(end)
        if start == end:
            parts.append(s)
        elif end == start + 1:
            parts.append(f"{s},{e}")
        else:
            parts.append(f"{s}-{e}")
    return ",".join(parts)


# Implements: REQ-d00282-M
# The mark a value with no figure to state carries in the formats people read.
# JSON carries ``null``, which is the same distinction in a format that has one.
ABSENT_FIGURE = "n/a"

# Implements: REQ-d00254-J, REQ-d00282-M
# The mark a figure that was NEVER TAKEN carries, distinct from a figure taken
# and found empty. A selective run that skipped a test target has nothing to
# say about the requirements that target covers; printing "0/5 (0%)" would say
# their tests failed to cover them, which is a different and untrue answer.
NOT_RUN_FIGURE = "\u2014"  # em dash


# Implements: REQ-d00282-B+M
# name: _store_scalars
# use:  record one coverage figure's three scalar parts on a row, beside the
#       whole figure the read formats state in one cell.
# def:  the credit, the assertions it was counted over and their proportion,
#       as NUMBERS -- or None for each where there is no figure to decompose.
#
# Kept as numbers all the way to the renderer: a value composed into prose here
# is a value a consumer has to take apart again, and the proportion it recovers
# would be the rounded one rather than the derived one. A row conferring no
# *Assertion* stores None rather than zero, so an absence never reads as work
# undone that was never owed -- and so does a row whose figure was never taken
# at all (``present=False``, REQ-d00254-J), which is the same absence reached
# by a different route.
def _store_scalars(
    data: dict, base: str, covered: float, total: int, *, present: bool = True
) -> None:
    for part in SCALAR_PARTS:
        data[f"{base}_{part}"] = scalar_value(covered, total, part) if (total and present) else None


def _get_node_data(node, graph: FederatedGraph, *, assertion_labels: bool = False) -> dict:
    """Extract data from a node for use in formatters.

    When assertion_labels is True, coverage values show compact assertion
    label ranges (e.g. "A-E (100%)") instead of counts ("5/5 (100%)").
    """
    from elspais.graph.metrics import (
        CoverageDimension,
        LineCoverage,
        RollupMetrics,
        fmt_assertion_count,
    )

    # Get implements IDs via parent iteration
    impl_ids = []
    for parent in node.iter_parents():
        if parent.kind == NodeKind.REQUIREMENT:
            impl_ids.append(parent.id)

    # Get code references (CODE nodes that implement this requirement)
    code_refs = []
    for child in node.iter_children():
        if child.kind == NodeKind.CODE:
            code_refs.append(child.id)

    # Get test references (TEST nodes that validate this requirement)
    # Build both flat list and grouped-by-assertion dict
    test_refs = []
    test_refs_grouped: dict[str, list[str]] = {}
    for edge in node.iter_outgoing_edges():
        if edge.target.kind == NodeKind.TEST:
            test_refs.append(edge.target.id)
            if edge.assertion_targets:
                for label in edge.assertion_targets:
                    test_refs_grouped.setdefault(label, []).append(edge.target.id)
            else:
                test_refs_grouped.setdefault("*", []).append(edge.target.id)

    # Get assertions
    assertions = []
    for child in node.iter_children():
        if child.kind == NodeKind.ASSERTION:
            assertions.append(
                {"label": child.get_field("label", ""), "text": child.get_label() or ""}
            )

    # Implements: REQ-d00084-D
    # Coverage values from RollupMetrics
    rollup: RollupMetrics | None = node.get_metric("rollup_metrics")
    total_a = rollup.total_assertions if rollup else 0

    # Implements: REQ-d00254-I+J
    fresh_targets = getattr(graph, "render_fresh_targets", None)
    selective = fresh_targets is not None

    def _fmt_count(num: float, total: int) -> str:
        # Implements: REQ-d00282-E
        # Through the shared cell authority, so a figure reads the same here as
        # in every other report that states one.
        if total == 0:
            return ABSENT_FIGURE
        return figure_cell(num, total)

    # Implements: REQ-d00254-B, REQ-d00258-E, REQ-d00282-C+M+N
    def _lines_measured(lines: LineCoverage) -> bool:
        """Whether a coverage run measured these lines at all.

        Two conditions, and both are real. ``total_lines`` is derived from the
        `Implements:` lines themselves, so it is nonzero for a requirement whose
        implementation nobody ran; ``has_measurement`` is recorded at ingestion
        and is what says a run happened. Either failing means there is no line
        figure to state, and a figure of zero would say the code was measured
        and never reached (REQ-d00282-M).
        """
        return lines.has_measurement and lines.total_lines > 0

    def _fmt_code_tested(lines: LineCoverage) -> str | None:
        """The line figure itself: lines covered out of lines measured.

        Named for the figure, so it states the figure (REQ-d00282-C). The
        attribution -- how many of those lines a verifying test can be named
        for -- is a different question with its own name and its own
        suppression (REQ-d00258-E); it used to be what this cell showed, which
        took the measured lines down with it whenever the tooling recorded no
        per-test contexts.
        """
        if not _lines_measured(lines):
            return None
        return figure_cell(lines.covered_lines, lines.total_lines)

    # Implements: REQ-d00258-A, REQ-d00258-J
    # (value_key, rollup_attr). All five dimensions headline on the
    # per-*Assertion* TOTAL (REQ-d00069-N, the greatest of an *Assertion*'s
    # four measures), and no marker stands in for a measure the surface does
    # not show -- the four measures behind the total are published as their
    # own values instead (below).
    _DIMS = [
        ("implemented", "implemented"),
        ("tested", "tested"),
        ("verified", "verified"),
        ("uat_coverage", "uat_coverage"),
        ("uat_verified", "uat_verified"),
    ]

    from elspais.graph.serialize import serialize_requirement_summary

    data: dict = serialize_requirement_summary(
        node,
        extras={
            "implements": impl_ids,
            "hash": node.hash or "",
            "file": (node.file_node().get_field("relative_path") if node.file_node() else ""),
            "body": node.get_field("body", "") or "",
            "assertions": assertions,
            "code_refs": code_refs,
            "test_refs": test_refs,
            "test_refs_grouped": test_refs_grouped,
        },
    )

    # Implements: REQ-d00282-H, REQ-d00282-L
    # Read for every requirement whatever the selection names: the journeys
    # value states a fact ABOUT a row, and a value switch that decided
    # whether the row existed would be a second row-selection.
    journeys = _get_uat_journeys(node)
    data["journeys_detail"] = journeys
    data["journeys"] = "; ".join(f"{j['id']}:{j['verdict']}" for j in journeys)

    if rollup:
        from elspais.graph.aggregation import (
            HEADLINE_MEASURE,
            MEASURES,
            covered_labels,
            measure_total,
        )
        from elspais.graph.metrics import tested_and_passing, tested_partition

        # Implements: REQ-d00254-J, REQ-d00282-M
        # Whether this requirement's verified figure was TAKEN AT ALL, decided
        # before any of it is recorded. "Not run" (REQ-d00254-J) means the
        # referenced TEST nodes have zero RESULT records in a selective run --
        # the target was skipped and nothing was seeded. Keyed on RESULT
        # existence, not on "no pass/fail signal": results can exist yet
        # contribute no verified signal (all skipped, say), and those are a
        # real zero rather than an absence.
        #
        # Decided HERE, above the figures, because the absence has to reach the
        # numbers and not only the cell. Deciding it afterwards left the cell
        # reading "—" while `verified.count` stated a flat 0, so a reader who
        # selected the number was told work had failed that was never run.
        has_any_result = any(
            child.kind == NodeKind.RESULT
            for edge in node.iter_outgoing_edges()
            if edge.target.kind == NodeKind.TEST
            for child in edge.target.iter_children()
        )
        _verified_not_run = (
            selective and rollup.verified.total > 0 and bool(test_refs) and not has_any_result
        )

        for key, attr in _DIMS:
            # Implements: REQ-d00258-A, REQ-d00277-C
            # "Passing" (the verified dimension) counts what the declared tests
            # returned, excluding an assertion its own tests failed.
            dim: CoverageDimension = (
                tested_and_passing(rollup) if key == "verified" else getattr(rollup, attr)
            )
            # Implements: REQ-d00069-N, REQ-d00258-A, REQ-d00258-J
            # The headline is the per-*Assertion* TOTAL -- the greatest of
            # the four measures, taken once per *Assertion* -- with no
            # marker standing in for a measure the cell does not show; the
            # four measures are published as their own values below.
            # Implements: REQ-d00282-E
            # ONE value per name, whatever the detail flag asks for: the
            # labels form replaces the count in the cell rather than splitting
            # the value in the formats that could carry two.
            # Implements: REQ-d00254-J, REQ-d00282-M
            # A dimension whose figure was never taken states none, in every
            # form it is offered in: the cell reads "not run" and the numbers
            # beneath it are absent rather than zero.
            taken = not (key == "verified" and _verified_not_run)
            if not taken:
                data[key] = NOT_RUN_FIGURE
            elif assertion_labels:
                labels = covered_labels(dim, HEADLINE_MEASURE)
                label_str = _compact_labels(labels) if labels else f"0/{dim.total}"
                pct = round(dim.covered / dim.total * 100) if dim.total else 0
                data[key] = f"{label_str} ({pct}%)" if dim.total else ABSENT_FIGURE
            else:
                data[key] = _fmt_count(dim.covered, total_a)
            _store_scalars(data, key, dim.covered, total_a, present=taken)
            for measure in MEASURES:
                measured = measure_total(dim, measure)
                data[f"{key}_{measure}"] = (
                    NOT_RUN_FIGURE if not taken else _fmt_count(measured, total_a)
                )
                _store_scalars(data, f"{key}_{measure}", measured, total_a, present=taken)
            # Implements: REQ-d00254-I, REQ-d00282-B+M
            # The provenance bit as a value of its own. It used to be legible
            # only inside the whole figure's cell, so a reader selecting the
            # credit alone could not tell a carried verdict from a fresh one.
            # Absent, not False, where no verdict was taken: "this was not
            # carried" would be a claim about a verdict that does not exist.
            if key == CARRIED_DIMENSION:
                data[f"{key}_{FLAG_CARRIED}"] = (
                    bool(dim.carried) if taken and dim.total > 0 else None
                )
        # Implements: REQ-d00258-O, REQ-d00282-E
        # The breakdown QUALIFIES the Tested figure, so it is put inside that
        # figure's value once, here, and every format states the one cell.
        # Given cells of its own in one format and a bracket in another, the
        # Tested value produced four columns in CSV and one in markdown --
        # and three of them were a display term of its own, which O forbids.
        # Empty when nothing is tested: there is no breakdown of an empty set.
        part = tested_partition(rollup)
        # Implements: REQ-d00258-O, REQ-d00282-B
        # The same three counts the breakdown states in prose, each selectable
        # on its own. Read from the partition rather than parsed back out of
        # the sentence below it -- which is the defect the scalars exist to
        # end. Absent, not zero, for a requirement conferring no *Assertion*
        # (REQ-d00282-M).
        for count_part in COUNT_PARTS:
            data[f"tested_{count_part}"] = getattr(part, count_part) if total_a else None
        data["tested_breakdown"] = (
            f"[{fmt_assertion_count(part.passed)}P {fmt_assertion_count(part.failed)}F "
            f"{fmt_assertion_count(part.awaiting)}A]"
            if part.tested
            else ""
        )
        if data["tested_breakdown"]:
            data["tested"] = f"{data['tested']} {data['tested_breakdown']}"

        ct = rollup.code_tested
        data["code_tested"] = _fmt_code_tested(ct)
        # Implements: REQ-d00282-N
        # The lines covered, the lines measured and their proportion, each in
        # its own right and each a NUMBER -- so a consumer reads what the cell
        # was made from rather than cutting it back out of the sentence.
        _store_scalars(
            data, "code_tested", ct.covered_lines, ct.total_lines, present=ct.has_measurement
        )
        # Implements: REQ-d00258-E, REQ-d00282-M+N
        # Suppressed where the tooling recorded no per-test contexts: with
        # nothing to attribute a line to a test with, a count would answer a
        # question never asked. Absent rather than zero, and absent ALONE --
        # the three values above stand, because those lines were measured.
        data[f"code_tested_{PART_ATTRIBUTED}"] = (
            ct.attributed_lines if _lines_measured(ct) and ct.has_attribution else None
        )
        # Implements: REQ-d00254-I
        # The whole figure discloses its provenance in the cell as well, for a
        # reader reading the table rather than selecting the bit.
        vdim = rollup.verified
        if not _verified_not_run and vdim.carried and vdim.total > 0:
            data["verified"] = f"{data['verified']} (baseline)"

        lt = rollup.lcov_tested
        # Implements: REQ-d00254-B, REQ-d00282-B
        # An *Assertion*-counted dimension like any other, so it decomposes
        # like one: only its EVIDENCE is lines.
        _store_scalars(data, "lcov_tested", lt.covered, lt.total)
        if lt.total > 0:
            # Implements: REQ-d00069-N, REQ-d00258-A
            # The per-*Assertion* total, like every other dimension headline.
            lt_pct = round(lt.covered / lt.total * 100)
            if assertion_labels:
                # The labels the credit landed on, in the cell the count would
                # otherwise hold -- one value either way (REQ-d00282-E).
                labels = {lbl for lbl, frac in lt.total_by_label.items() if frac > 0}
                label_str = _compact_labels(labels) if labels else f"0/{lt.total}"
                data["lcov_tested"] = f"{label_str} ({lt_pct}%)"
            else:
                data["lcov_tested"] = f"lcov {lt_pct}%"
        else:
            data["lcov_tested"] = None
    else:
        from elspais.graph.aggregation import MEASURES

        for key, _ in _DIMS:
            data[key] = ABSENT_FIGURE
            _store_scalars(data, key, 0.0, 0)
            for measure in MEASURES:
                data[f"{key}_{measure}"] = ABSENT_FIGURE
                _store_scalars(data, f"{key}_{measure}", 0.0, 0)
        data[f"{CARRIED_DIMENSION}_{FLAG_CARRIED}"] = None
        for count_part in COUNT_PARTS:
            data[f"tested_{count_part}"] = None
        data["code_tested"] = None
        _store_scalars(data, "code_tested", 0.0, 0)
        data[f"code_tested_{PART_ATTRIBUTED}"] = None
        data["lcov_tested"] = None
        _store_scalars(data, "lcov_tested", 0.0, 0)

    return data


# Implements: REQ-d00282-C, REQ-d00258-K
def _value_headers(config: dict | None = None) -> dict[str, str]:
    """The words each offered value is displayed under.

    Projected from the one authority (``header_for``) rather than spelled here,
    so a project that renames a dimension renames it on every surface while the
    key a selection names stays what it was (REQ-d00282-J).
    """
    return {key: header_for(key, config) for key in OFFERED_VALUES}


# Implements: REQ-d00282-E
# The measures behind each dimension are values like any other, named in the
# selection vocabulary (``tested.immediate_direct``) and stated only where the
# selection names them. They were previously bolted onto CSV and JSON alone,
# which made the values a report states depend on the format it was rendered
# in -- the divergence REQ-d00282-E forbids.


# Implements: REQ-d00282-E+M
def _format_row(data: dict, keys: Sequence[str]) -> list[str]:
    """One row as the formats people read state it, one cell per stated value.

    A scalar part is a number, and this is where it is SPELLED for a table --
    the value itself stays a number for the formats that have them
    (REQ-d00282-E). A value with nothing behind it reads as the absence mark
    rather than as zero (REQ-d00282-M), whatever kind of value it is.
    """
    cells: list[str] = []
    for key in keys:
        if key == "implements":
            cells.append(", ".join(data["implements"]) or "-")
            continue
        spec = VALUE_SPECS.get(key)
        value = data.get(_data_key(key), "")
        if value is None:
            cells.append(ABSENT_FIGURE)
        elif spec is not None and spec.is_flag:
            cells.append(flag_cell(value))
        elif spec is not None and spec.is_scalar:
            cells.append(scalar_cell(value, spec.part))
        else:
            cells.append(str(value))
    return cells


# Implements: REQ-d00084-B, REQ-d00282-A
def _default_values(preset: ReportPreset) -> list[str]:
    """The named default set this preset states, absent a selection.

    A preset is a default set and nothing more: it decides what a reader who
    named no values is answered with, never which requirements the report is
    about (REQ-d00282-H).
    """
    values = list(preset.values)
    if preset.dimension == "uat" and "journeys" not in values:
        values.append("journeys")
    return values


def _report_values(preset: ReportPreset, values: Sequence[str] | None) -> list[str]:
    """The values a rendering states: the selection if one was made, else the default."""
    return list(values) if values is not None else _default_values(preset)


# Implements: REQ-d00282-B+E+K+M
def _json_row(data: dict, keys: Sequence[str], node=None) -> dict:
    """One JSON object stating exactly the values the report states.

    Shared by the live-graph path and the path a serving process answers, so
    the two cannot state different values for one selection.

    The shape comes from ``structured_row``, which the coverage summary also
    builds through, so one selection reads the same in both reports. A figure
    is stated as an OBJECT of its numbers rather than as the sentence a table
    renders, keyed to mirror the path the selection names it by: a consumer
    holding ``implemented.count`` reads ``count`` inside ``implemented``, and
    never has to parse "3/7 (43%)" back into the numbers it was made from
    (REQ-d00282-E).
    """

    def part_value(key: str):
        return data.get(_data_key(key))

    def plain_value(key: str):
        if key == "journeys":
            return data.get("journeys_detail") or []
        if key == "file":
            # Implements: REQ-d00129-D, REQ-d00129-E
            fn = node.file_node() if node is not None else None
            return {
                "path": fn.get_field("relative_path") if fn else data.get("file"),
                "line": node.get_field("parse_line") if node is not None else None,
            }
        return data.get(_data_key(key))

    # The file reference is stated under the name this format has always given
    # it, which is a spelling and so the format's own (REQ-d00282-E).
    return structured_row(
        keys, part_value, plain_value, offers=OFFERED_VALUES, path_of={"file": "source"}
    )


# Implements: REQ-p00084-B+C
def _scoped_requirements(graph: FederatedGraph, scope_ids: frozenset[str] | None):
    """The requirements a rendering emits, honouring the scope it was given.

    Every formatter in this module iterates through here, so REQ-p00084-C holds
    structurally: a requirement cannot be present in one rendering of a report
    and missing from another, because there is one place that decides.
    """
    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if scope_ids is None or node.id in scope_ids:
            yield node


def format_markdown(
    graph: FederatedGraph,
    preset: ReportPreset | None = None,
    scope_ids: frozenset[str] | None = None,
    values: Sequence[str] | None = None,
    config: dict | None = None,
    scope_lines: Sequence[str] | None = None,
) -> Iterator[str]:
    """Generate markdown table. Streams one node at a time."""
    if preset is None:
        preset = REPORT_PRESETS[DEFAULT_PRESET]

    yield "# Traceability Matrix"
    yield ""

    # Implements: REQ-p00084-C+D
    # The scope rides inside the rendering, so the artifact a reader files
    # declares what selected its rows -- in this format as in every other.
    for line in scope_lines or []:
        yield f"*{line}*"
        yield ""

    # Implements: REQ-d00282-C, REQ-d00282-K
    # Stated in the order the selection names them, headed by words the project
    # configures rather than words spelled here.
    cols = _report_values(preset, values)
    headers = [header_for(col, config) for col in cols]
    yield "| " + " | ".join(headers) + " |"
    yield "|" + "|".join(["----"] * len(headers)) + "|"

    # Implements: REQ-d00254-I+J
    # Track whether any rendered row actually produced a `(baseline)`/`—`
    # marker in its verified cell, so the legend is only emitted when it's
    # relevant (and full-run output stays byte-identical to before).
    has_carry_marker = False
    # Implements: REQ-d00258-O
    has_tested_breakdown = False

    for node in _scoped_requirements(graph, scope_ids):
        data = _get_node_data(node, graph, assertion_labels=preset.include_assertions)

        if "verified" in cols:
            verified_cell = data.get("verified", "")
            if "(baseline)" in verified_cell or "—" in verified_cell:
                has_carry_marker = True
        # Implements: REQ-d00258-O
        # The breakdown is already inside the Tested cell (one cell in every
        # format); this only decides whether the key explaining it is worth
        # printing. Only where the Tested value is stated: a legend pointing
        # at a value this selection does not show explains nothing.
        if "tested" in cols and data.get("tested_breakdown"):
            has_tested_breakdown = True

        row_values = _format_row(data, cols)
        yield "| " + " | ".join(row_values) + " |"

        # Detail rows (controlled by flags, independent of the values stated)
        if preset.include_body and data["body"]:
            yield ""
            yield "<details><summary>Body</summary>"
            yield ""
            yield data["body"]
            yield ""
            yield "</details>"

        if preset.include_test_refs and data["test_refs_grouped"]:
            total = len(data["test_refs"])
            yield ""
            yield f"<details><summary>Test Refs ({total})</summary>"
            yield ""
            grouped = data["test_refs_grouped"]
            # Whole-requirement tests first, then assertion labels sorted
            for key in ["*"] + sorted(k for k in grouped if k != "*"):
                if key not in grouped:
                    continue
                refs = grouped[key]
                label = "Whole-requirement" if key == "*" else key
                yield f"**{label}** ({len(refs)}):"
                for ref in refs:
                    yield f"- `{ref}`"
                yield ""
            yield "</details>"

    # Implements: REQ-d00254-I+J
    # Only surface the legend when a row actually used a marker it explains.
    if has_carry_marker:
        yield ""
        yield (
            "> Legend: `(baseline)` = carried from a prior run (not re-run this PR, "
            "verdict still honored); `—` = target not run and no baseline "
            "(skipped, not a regression)."
        )

    # Implements: REQ-d00258-O
    # The breakdown is unreadable without its key, so the key appears whenever
    # a row carried one.
    if has_tested_breakdown:
        yield ""
        yield (
            "> Tested breakdown: `P` passed, `F` failed, `A` awaiting a result "
            "(declared, and no verdict came back). The three account for every "
            "tested assertion."
        )


def format_csv(
    graph: FederatedGraph,
    preset: ReportPreset | None = None,
    scope_ids: frozenset[str] | None = None,
    values: Sequence[str] | None = None,
    config: dict | None = None,
    scope_lines: Sequence[str] | None = None,
) -> Iterator[str]:
    """Generate CSV. Streams one node at a time.

    When test refs are included, adds a Kind column (first) and Assertion/Test Ref
    columns (last). Each test ref gets its own TEST row after its parent REQ row.
    """
    if preset is None:
        preset = REPORT_PRESETS[DEFAULT_PRESET]

    def escape(s: str) -> str:
        if "," in s or '"' in s or "\n" in s:
            return '"' + s.replace('"', '""') + '"'
        return s

    # Implements: REQ-p00084-C+D
    # A leading comment row per disclosure line. It is one escaped field, so a
    # consumer still reads the file as CSV, and it precedes the header so the
    # table beneath it is the shape it always was.
    for line in scope_lines or []:
        yield escape(f"# {line}")

    # Implements: REQ-d00282-C+E+K
    # One header and one cell per stated value, headed by the words the
    # project configures (REQ-d00258-K). Nothing rides alongside: a figure's
    # proportion lives inside its own cell and the Tested breakdown inside the
    # Tested one, so this states the same values markdown, html and json do.
    cols = _report_values(preset, values)
    header_names = [header_for(c, config) for c in cols]

    extra_prefix = []
    extra_suffix = []
    if preset.include_test_refs:
        extra_prefix.append("Kind")
        extra_suffix.extend(["Assertion", "Test Ref"])

    yield ",".join(extra_prefix + header_names + extra_suffix)

    for node in _scoped_requirements(graph, scope_ids):
        data = _get_node_data(node, graph, assertion_labels=preset.include_assertions)
        row_values = [escape(v) for v in _format_row(data, cols)]

        # Build REQ row
        req_prefix = ["REQ"] if preset.include_test_refs else []
        req_suffix = []
        if preset.include_test_refs:
            req_suffix.extend(["", ""])  # Empty Assertion and Test Ref cells for REQ row

        yield ",".join(req_prefix + row_values + req_suffix)

        # Emit TEST child rows
        if preset.include_test_refs:
            grouped = data["test_refs_grouped"]
            empty_cols = [""] * len(cols)
            for key in ["*"] + sorted(k for k in grouped if k != "*"):
                if key not in grouped:
                    continue
                for ref in grouped[key]:
                    yield ",".join(["TEST"] + empty_cols + [key, escape(ref)])


def format_html(
    graph: FederatedGraph,
    preset: ReportPreset | None = None,
    scope_ids: frozenset[str] | None = None,
    values: Sequence[str] | None = None,
    config: dict | None = None,
    scope_lines: Sequence[str] | None = None,
) -> Iterator[str]:
    """Generate basic HTML table. Streams one node at a time."""
    if preset is None:
        preset = REPORT_PRESETS[DEFAULT_PRESET]

    def escape_html(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    yield "<!DOCTYPE html>"
    yield "<html><head><style>"
    yield "table { border-collapse: collapse; width: 100%; }"
    yield "th, td { border: 1px solid #ddd; padding: 8px; text-align: left; vertical-align: top; }"
    yield "th { background-color: #4CAF50; color: white; }"
    yield "tr:nth-child(even) { background-color: #f2f2f2; }"
    yield ".assertions, .refs { font-size: 0.9em; color: #666; }"
    yield ".assertion-label { font-weight: bold; }"
    yield "details { margin: 5px 0; }"
    yield "summary { cursor: pointer; color: #4CAF50; }"
    yield "</style></head><body>"
    yield "<h1>Traceability Matrix</h1>"

    # Implements: REQ-p00084-C+D
    # A subtitle beneath the heading: the page states the scope that produced
    # it, so the file a reader saves is not silent about what it left out.
    for line in scope_lines or []:
        yield f"<p style='color: #555; font-style: italic;'>{escape_html(line)}</p>"

    cols = _report_values(preset, values)
    headers = [header_for(col, config) for col in cols]
    if preset.include_test_refs:
        headers.append("Test Refs")

    yield "<table>"
    yield "<tr>" + "".join(f"<th>{h}</th>" for h in headers) + "</tr>"

    for node in _scoped_requirements(graph, scope_ids):
        data = _get_node_data(node, graph, assertion_labels=preset.include_assertions)
        cells = []
        for val in _format_row(data, cols):
            cells.append(f"<td>{escape_html(val)}</td>")

        if preset.include_test_refs:
            grouped = data["test_refs_grouped"]
            if grouped:
                parts = []
                for key in ["*"] + sorted(k for k in grouped if k != "*"):
                    if key not in grouped:
                        continue
                    refs = grouped[key]
                    label = "Whole-requirement" if key == "*" else key
                    ref_html = "<br>".join(f"<code>{escape_html(r)}</code>" for r in refs)
                    parts.append(
                        f"<strong>{escape_html(label)}</strong> ({len(refs)}):<br>{ref_html}"
                    )
                cells.append(f"<td class='refs'>{'<br><br>'.join(parts)}</td>")
            else:
                cells.append("<td>-</td>")

        yield f"<tr>{''.join(cells)}</tr>"

    yield "</table></body></html>"


# Implements: REQ-p00084-C+D
def format_json(
    graph: FederatedGraph,
    preset: ReportPreset | None = None,
    scope_ids: frozenset[str] | None = None,
    values: Sequence[str] | None = None,
    config: dict | None = None,
    scope_lines: Sequence[str] | None = None,
) -> Iterator[str]:
    """Generate JSON array, or an object carrying the scope beside it.

    A report narrowed by a scope answers with ``{"scope": [...], "nodes": [...]}``
    so the document states what selected its rows (REQ-p00084-D); one narrowed by
    nothing has nothing to declare and stays the bare array it has always been.
    """
    if preset is None:
        preset = REPORT_PRESETS[DEFAULT_PRESET]

    cols = _report_values(preset, values)

    if scope_lines:
        yield "{"
        yield f'"scope": {json.dumps(list(scope_lines), indent=2)},'
        yield '"nodes": ['
    else:
        yield "["
    first = True
    for node in _scoped_requirements(graph, scope_ids):
        if not first:
            yield ","
        first = False

        data = _get_node_data(node, graph, assertion_labels=preset.include_assertions)
        node_dict = _json_row(data, cols, node)

        # Add detail fields (controlled by flags)
        if preset.include_body:
            node_dict["body"] = data["body"]
        if preset.include_test_refs:
            node_dict["test_refs"] = data["test_refs_grouped"]

        yield json.dumps(node_dict, indent=2)
    yield "]"
    if scope_lines:
        yield "}"


# Implements: REQ-p00006-A
def format_view(
    graph: FederatedGraph,
    embed_content: bool = False,
    base_path: str = "",
    repo_name: str | None = None,
    config: dict | None = None,
) -> str:
    """Generate interactive HTML via HTMLGenerator."""
    try:
        from elspais.html import HTMLGenerator
    except ImportError as err:
        raise ImportError(
            "HTMLGenerator requires the trace-view extra. "
            "Install with: pip install elspais[trace-view]"
        ) from err
    generator = HTMLGenerator(graph, base_path=base_path, repo_name=repo_name, config=config)
    return generator.generate(embed_content=embed_content)


# Server/viewer functions moved to commands/viewer.py


# Implements: REQ-d00085-A
def render_section(
    graph: FederatedGraph,
    args: argparse.Namespace,
    config: dict | None = None,
) -> tuple[str, int]:
    """Render trace as a composed report section.

    Returns (formatted_output, exit_code).
    """
    dimension = getattr(args, "dimension", "")
    if dimension == "uat":
        preset = ReportPreset(
            name="uat",
            values=list(_UAT_VALUES),
            dimension="uat",
        )
    else:
        preset_name = getattr(args, "preset", None) or DEFAULT_PRESET
        if preset_name not in REPORT_PRESETS:
            available = ", ".join(REPORT_PRESETS.keys())
            return f"Error: Unknown preset '{preset_name}'\nAvailable: {available}", 1
        preset = ReportPreset(
            name=preset_name,
            values=list(REPORT_PRESETS[preset_name].values),
            include_body=getattr(args, "body", False),
            include_assertions=getattr(args, "show_assertions", False),
            include_test_refs=getattr(args, "show_tests", False),
        )

    fmt = getattr(args, "format", "markdown")
    formatters = {
        "text": format_markdown,
        "markdown": format_markdown,
        "csv": format_csv,
        "html": format_html,
        "json": format_json,
    }
    formatter = formatters.get(fmt)
    if not formatter:
        return f"Error: Unknown format '{fmt}'", 1

    # Implements: REQ-d00282-A+F
    # A section composed with others states the same values it states alone,
    # and refuses the same selections -- a report is never produced under a
    # selection honoured in part.
    from elspais.commands._values import resolve_report_values

    try:
        values = resolve_report_values(args, OFFERED_VALUES, _default_values(preset), config)
    except UnofferedValues as err:
        return f"Error: {err}", 1

    # Implements: REQ-p00084-A+B+D, REQ-d00279-C
    # A section composed with others honours the same scope it honours alone.
    from elspais.commands._scope import resolve_scope_for_report, scope_disclosure

    result = resolve_scope_for_report(graph, args, config)
    scope_ids = None if len(result.ids) == result.population else result.ids
    # Implements: REQ-p00084-C+D
    # The disclosure goes THROUGH the formatter rather than ahead of it, so a
    # composed section declares its scope in the shape of the format it is
    # rendered in -- a bare line ahead of a CSV or JSON section is neither.
    scope_lines = scope_disclosure(result)
    lines = list(formatter(graph, preset, scope_ids, values, config, scope_lines))
    return "\n".join(lines), 0


# Implements: REQ-p00084-C+D
def _render_json_from_data(
    data: dict,
    preset: ReportPreset,
    values: Sequence[str] | None = None,
) -> None:
    """Render JSON output from compute_trace data dict."""
    # The scope reaches this path inside the computed data, and leaves it the
    # same way: the document states the scope a table rendering states, rather
    # than leaving it on a stream the artifact does not carry.
    scope_lines = data.get("scope") or []
    cols = _report_values(preset, values)
    nodes = []
    for node_data in data["nodes"]:
        # Implements: REQ-d00282-E
        # The same row builder the live-graph path uses, so a selection reaches
        # the same values whether a serving process or this process computed
        # the report.
        node_dict = _json_row(node_data, cols)
        if preset.include_body:
            node_dict["body"] = node_data.get("body", "")
        if preset.include_assertions:
            node_dict["assertions"] = node_data.get("assertions", [])
        if preset.include_test_refs:
            node_dict["test_refs"] = node_data.get("test_refs_grouped", {})
        nodes.append(node_dict)
    payload = {"scope": scope_lines, "nodes": nodes} if scope_lines else nodes
    print(json.dumps(payload, indent=2))


def _render_table_from_graph(
    graph: FederatedGraph,
    fmt: str,
    preset: ReportPreset,
    scope_ids: frozenset[str] | None = None,
    values: Sequence[str] | None = None,
    config: dict | None = None,
    scope_lines: Sequence[str] | None = None,
) -> int:
    """Render table or JSON formats using graph-based formatters. Returns exit code."""
    formatters = {
        "text": format_markdown,
        "markdown": format_markdown,
        "csv": format_csv,
        "html": format_html,
        # JSON is included here so UAT dimension (which always uses the graph) can
        # route through this function for all formats including JSON.
        "json": format_json,
    }
    formatter = formatters.get(fmt)
    if not formatter:
        print(f"Error: Unknown format '{fmt}'", file=sys.stderr)
        return 1
    for line in formatter(graph, preset, scope_ids, values, config, scope_lines):
        print(line)
    return 0


def _resolve_values_or_report(
    args: argparse.Namespace,
    preset: ReportPreset,
    config: dict | None,
) -> tuple[tuple[str, ...], dict[str, str]] | None:
    """The values this invocation states and the params carrying them onward.

    Returns None once it has told the reader why the selection was refused:
    REQ-d00282-F wants no report produced under a selection honoured in part,
    and the refusal reaches the reader as a message rather than a traceback.
    """
    from elspais.commands._values import resolve_report_values, value_params_from_args

    try:
        values = resolve_report_values(args, OFFERED_VALUES, _default_values(preset), config)
    except UnofferedValues as err:
        print(f"Error: {err}", file=sys.stderr)
        return None
    return values, value_params_from_args(args, config)


def run(args: argparse.Namespace) -> int:
    """Run the trace command.

    Uses engine.call for daemon-vs-local, then renders in the requested format.
    """
    from elspais.commands import _engine
    from elspais.config import get_config

    fmt = getattr(args, "format", "markdown")
    spec_dir = getattr(args, "spec_dir", None)
    # Implements: REQ-d00254-I, REQ-d00283-D+E+I
    # --targets/--groups mark provenance on the rendered graph; force a local
    # build (bypassing any cached daemon graph) so the fresh set actually
    # threads into build_graph().
    from elspais.commands._targets import resolve_fresh_targets

    dimension = getattr(args, "dimension", "")
    config_path = getattr(args, "config", None)
    config = get_config(config_path)
    try:
        fresh_targets = resolve_fresh_targets(args, config)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    skip_daemon = bool(spec_dir) or fresh_targets is not None

    if dimension == "uat":
        # Implements: REQ-d00257-A+C, REQ-d00282-H
        # `--dimension uat` is a named default value set and nothing else: it
        # states the UAT dimensions and the journeys validating each row, and
        # leaves the code dimensions out. Which requirements the report is
        # about is the scope's to decide, so a requirement no journey validates
        # is a row reading "no journeys" rather than a row a value switch
        # removed.
        preset = ReportPreset(
            name="uat",
            values=list(_UAT_VALUES),
            dimension="uat",
        )
    else:
        # Implements: REQ-d00084-B+C
        # Parse --preset and apply independent detail flags
        preset_name = getattr(args, "preset", None) or DEFAULT_PRESET
        if preset_name not in REPORT_PRESETS:
            available = ", ".join(REPORT_PRESETS.keys())
            print(f"Error: Unknown preset '{preset_name}'", file=sys.stderr)
            print(f"Available presets: {available}", file=sys.stderr)
            return 1
        preset = ReportPreset(
            name=preset_name,
            values=list(REPORT_PRESETS[preset_name].values),
            include_body=getattr(args, "body", False),
            include_assertions=getattr(args, "show_assertions", False),
            include_test_refs=getattr(args, "show_tests", False),
        )

    # Implements: REQ-d00282-A+E+F
    # Resolved before anything is built or asked of a serving process, and
    # carried in the same parameters the scope travels in.
    resolved = _resolve_values_or_report(args, preset, config)
    if resolved is None:
        return 1
    values, value_params = resolved

    # Implements: REQ-p00084-A+D, REQ-d00279-C
    from elspais.commands._scope import (
        resolve_scope_for_report,
        scope_disclosure,
        scope_params_from_args,
    )

    params = dict(scope_params_from_args(args, config))
    params.update(value_params)

    if skip_daemon:
        # Custom spec_dir (or a target selection): build graph directly
        from elspais.graph.factory import build_graph

        graph = build_graph(
            spec_dirs=[spec_dir] if spec_dir else None,
            config_path=config_path,
            fresh_targets=fresh_targets,
        )
        if fmt == "json" and dimension != "uat":
            data = compute_trace(graph, config, params)
            _render_json_from_data(data, preset, values)
        else:
            result = resolve_scope_for_report(graph, params, config)
            ids = None if len(result.ids) == result.population else result.ids
            return _render_table_from_graph(
                graph, fmt, preset, ids, values, config, scope_disclosure(result)
            )
    else:
        data = _engine.call(
            "/api/run/trace",
            params,
            compute_trace,
            config_path=config_path,
        )

        # Implements: REQ-d00084-A
        if fmt == "json" and dimension != "uat":
            _render_json_from_data(data, preset, values)
        else:
            # For non-JSON formats we need the graph to stream through formatters.
            graph = _engine.get_graph()
            result = resolve_scope_for_report(graph, params, config)
            ids = None if len(result.ids) == result.population else result.ids
            return _render_table_from_graph(
                graph, fmt, preset, ids, values, config, scope_disclosure(result)
            )

    return 0


# Implements: REQ-d00084-A
def run_graph(args: argparse.Namespace) -> int:
    """Export the full traceability graph structure as JSON."""
    from elspais.graph.annotators import annotate_graph_git_state
    from elspais.graph.factory import build_graph
    from elspais.graph.serialize import serialize_graph

    spec_dir = getattr(args, "spec_dir", None)
    config_path = getattr(args, "config", None)

    # This command exports the graph's structure, not a report over it, and
    # `GraphArgs` carries no target selector to narrow one with. Marking a
    # target set here would render the export as a selective run that nothing
    # on this surface could widen back, so the export covers every target.
    graph = build_graph(
        spec_dirs=[spec_dir] if spec_dir else None,
        config_path=config_path,
        fresh_targets=None,
    )

    annotate_graph_git_state(graph)
    print(json.dumps(serialize_graph(graph), indent=2))

    return 0
