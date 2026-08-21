# Implements: REQ-p00001-B, REQ-p00003-A, REQ-p00003-B
# Implements: REQ-d00052-B, REQ-d00052-C, REQ-d00052-G
"""
elspais.commands.trace - Generate traceability matrix command.

Uses the graph-based system to generate traceability reports in various formats.
Commands only work with graph data (zero file I/O for reading requirements).

OUTPUT FORMATS:
- markdown: Table with columns based on report preset
- csv: Same columns, comma-separated with proper escaping
- html: Basic styled HTML table
- json: Full requirement data including body, assertions, hash, file_path
- both: Generates both markdown and csv (legacy mode)

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
from elspais.graph.columns import (
    COLUMN_SPECS,
    MEASURE_KEY_SEPARATOR,
    UnofferedColumns,
    figure_cell,
    header_for,
)

# Implements: REQ-d00282-A
# Every column this report can state. A selection is judged against this set
# and nothing narrower: the columns a report offers are the tool's own, so a
# name among them that does not resolve is a mistake rather than a difference
# (REQ-d00282-F). Offering a further column changes nothing an already
# expressible selection states (REQ-d00282-G) -- a selection names what it
# names, and a default set is a separate thing that may grow.
# Group-only columns are left out: every row here is ONE requirement, and a
# count of the requirements in a row that is one requirement is a name for
# nothing. Offering it would be offering a column that could only be blank.
OFFERED_COLUMNS: tuple[str, ...] = tuple(
    key for key, spec in COLUMN_SPECS.items() if not spec.group_only
)


def _data_key(column: str) -> str:
    """The ``_get_node_data`` field a column reads.

    A measure is keyed beneath its dimension in the selection vocabulary
    (``tested.immediate_direct``) and beside it in the data (``tested_immediate_direct``);
    this is the one place the two spellings meet.
    """
    return column.replace(MEASURE_KEY_SEPARATOR, "_")


@dataclass
class ReportPreset:
    """Configuration for a report preset.

    ``columns`` is a named DEFAULT set (REQ-d00084-B) -- what a reader who names
    no columns is answered with. A selection stated on the invocation replaces
    it (REQ-d00282-A) and reaches the formatters as their ``columns`` argument.
    Detail flags (include_body, etc.) are set independently via CLI flags.
    """

    name: str
    columns: list[str]
    include_body: bool = False
    include_assertions: bool = False
    include_code_refs: bool = False
    include_test_refs: bool = False
    dimension: str = ""
    """Dimension group filter.  'uat' restricts the report to UAT coverage."""


# Implements: REQ-d00084-B
# Define report presets — columns only, detail flags set via CLI
REPORT_PRESETS = {
    "minimal": ReportPreset(
        name="minimal",
        columns=["id", "title", "level", "status"],
    ),
    "standard": ReportPreset(
        name="standard",
        columns=[
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
        columns=[
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

# Columns for the UAT dimension report -- excludes all code-dimension columns.
# A synthetic "journeys" column is appended by the formatters.
_UAT_COLUMNS = ["id", "title", "level", "status", "uat_coverage", "uat_verified"]


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

    Reads the scope AND the column selection out of ``params`` because this is
    the path a report takes when a serving process answers it: a selection that
    did not survive the trip would make a daemon-served report disagree with a
    locally computed one, about which requirements it is about (REQ-d00279-C)
    or about which facts it states (REQ-d00282-E).
    """
    from elspais.commands._columns import columns_from_params
    from elspais.commands._scope import resolve_scope_for_report, scope_disclosure
    from elspais.graph.columns import resolve_columns

    result = resolve_scope_for_report(graph, params, config)
    scope_ids = None if len(result.ids) == result.population else result.ids
    nodes = [_get_node_data(node, graph) for node in _scoped_requirements(graph, scope_ids)]
    payload: dict = {"nodes": nodes, "scope": scope_disclosure(result)}
    # Implements: REQ-d00282-A+F
    # Resolved here as well as where the report is rendered, so a serving
    # process refuses a selection it cannot honour in full rather than
    # answering with a report nobody asked for. Carried back so any consumer
    # of this payload states the columns the selection named; where no
    # selection was made the named default set decides and is not this
    # process's to choose.
    selection = columns_from_params(params)
    if selection is not None:
        payload["columns"] = list(resolve_columns(selection, OFFERED_COLUMNS))
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


def _get_node_data(node, graph: FederatedGraph, *, assertion_labels: bool = False) -> dict:
    """Extract data from a node for use in formatters.

    When assertion_labels is True, coverage columns show compact assertion
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
    # Coverage columns from RollupMetrics
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
            return "n/a"
        return figure_cell(num, total)

    def _fmt_code_tested(lines: LineCoverage) -> str:
        if lines.total_lines == 0 or not lines.has_attribution:
            # Aggregate-only tooling (e.g. lcov/coverage.json without per-test
            # attribution), and an estate with no coverage ingested at all,
            # record no context naming a test, so neither can produce an
            # attribution count -- rendering "0/N (0%)" would say no test
            # exercises this code when nothing was ever asked (REQ-d00258-E).
            # Where contexts ARE present the cell reads "0/N": that is a real
            # answer, and suppressing it would hide unattributed code.
            return "n/a"
        pct = round(lines.attributed_lines / lines.total_lines * 100)
        return f"{fmt_assertion_count(lines.attributed_lines)}/{lines.total_lines} ({pct}%)"

    # Implements: REQ-d00258-A, REQ-d00258-J
    # (column_key, rollup_attr). All five dimensions headline on the
    # per-*Assertion* TOTAL (REQ-d00069-N, the greatest of an *Assertion*'s
    # four measures), and no marker stands in for a measure the surface does
    # not show -- the four measures behind the total are published as their
    # own columns instead (below).
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
    # column states a fact ABOUT a row, and a column switch that decided
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

        for key, attr in _DIMS:
            # Implements: REQ-d00258-A, REQ-d00258-N
            # "Passing" (the verified column) counts what the declared tests
            # returned, excluding an assertion its own tests failed.
            dim: CoverageDimension = (
                tested_and_passing(rollup) if key == "verified" else getattr(rollup, attr)
            )
            # Implements: REQ-d00069-N, REQ-d00258-A, REQ-d00258-J
            # The headline is the per-*Assertion* TOTAL -- the greatest of
            # the four measures, taken once per *Assertion* -- with no
            # marker standing in for a measure the cell does not show; the
            # four measures are published as their own columns below.
            # Implements: REQ-d00282-E
            # ONE value per column, whatever the detail flag asks for: the
            # labels form replaces the count in the cell rather than splitting
            # the column in the formats that could carry two.
            if assertion_labels:
                labels = covered_labels(dim, HEADLINE_MEASURE)
                label_str = _compact_labels(labels) if labels else f"0/{dim.total}"
                pct = round(dim.covered / dim.total * 100) if dim.total else 0
                data[key] = f"{label_str} ({pct}%)" if dim.total else "n/a"
            else:
                data[key] = _fmt_count(dim.covered, total_a)
            for measure in MEASURES:
                data[f"{key}_{measure}"] = _fmt_count(measure_total(dim, measure), total_a)
        # Implements: REQ-d00258-O, REQ-d00282-E
        # The breakdown QUALIFIES the Tested figure, so it is put inside that
        # figure's value once, here, and every format states the one cell.
        # Given columns of its own in one format and a bracket in another, the
        # Tested column produced four columns in CSV and one in markdown --
        # and three of them were a display term of its own, which O forbids.
        # Empty when nothing is tested: there is no breakdown of an empty set.
        part = tested_partition(rollup)
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
        # Implements: REQ-d00254-I+J
        # Special-case the "verified" cell: distinguish "not run, no baseline"
        # from a carried (baseline) verdict, ahead of the "n/a"/count rendering
        # above. "No baseline" (REQ-d00254-J) means the referenced TEST nodes
        # have *zero* RESULT records -- the target was skipped this PR and
        # nothing was seeded. Key on RESULT existence, not on "no pass/fail
        # signal": results can exist yet contribute no verified signal (e.g. all
        # skipped / xfailed), and those must NOT render as "not run".
        vdim = rollup.verified
        has_any_result = any(
            child.kind == NodeKind.RESULT
            for edge in node.iter_outgoing_edges()
            if edge.target.kind == NodeKind.TEST
            for child in edge.target.iter_children()
        )
        if selective and vdim.total > 0 and test_refs and not has_any_result:
            data["verified"] = "—"  # em dash: not run this PR, no baseline
        elif vdim.carried and vdim.total > 0:
            data["verified"] = f"{data['verified']} (baseline)"

        lt = rollup.lcov_tested
        if lt.total > 0:
            # Implements: REQ-d00069-N, REQ-d00258-A
            # The per-*Assertion* total, like every other dimension headline.
            lt_pct = round(lt.covered / lt.total * 100)
            if assertion_labels:
                # The labels the credit landed on, in the cell the count would
                # otherwise hold -- one column either way (REQ-d00282-E).
                labels = {lbl for lbl, frac in lt.total_by_label.items() if frac > 0}
                label_str = _compact_labels(labels) if labels else f"0/{lt.total}"
                data["lcov_tested"] = f"{label_str} ({lt_pct}%)"
            else:
                data["lcov_tested"] = f"lcov {lt_pct}%"
        else:
            data["lcov_tested"] = "n/a"
    else:
        from elspais.graph.aggregation import MEASURES

        for key, _ in _DIMS:
            data[key] = "n/a"
            for measure in MEASURES:
                data[f"{key}_{measure}"] = "n/a"
        data["code_tested"] = "n/a"
        data["lcov_tested"] = "n/a"

    return data


# Implements: REQ-d00282-C, REQ-d00258-K
def _column_headers(config: dict | None = None) -> dict[str, str]:
    """The words each offered column is displayed under.

    Projected from the one authority (``header_for``) rather than spelled here,
    so a project that renames a dimension renames it on every surface while the
    key a selection names stays what it was (REQ-d00282-J).
    """
    return {key: header_for(key, config) for key in OFFERED_COLUMNS}


# Implements: REQ-d00282-E
# The measures behind each dimension are columns like any other, named in the
# selection vocabulary (``tested.immediate_direct``) and stated only where the
# selection names them. They were previously bolted onto CSV and JSON alone,
# which made the columns a report states depend on the format it was rendered
# in -- the divergence REQ-d00282-E forbids.


def _format_row(data: dict, columns: list[str]) -> list[str]:
    """Format a single row from node data according to columns."""
    values = []
    for col in columns:
        if col == "implements":
            values.append(", ".join(data["implements"]) or "-")
        else:
            values.append(str(data.get(_data_key(col), "")))
    return values


# Implements: REQ-d00084-B, REQ-d00282-A
def _default_columns(preset: ReportPreset) -> list[str]:
    """The named default set this preset states, absent a selection.

    A preset is a default set and nothing more: it decides what a reader who
    named no columns is answered with, never which requirements the report is
    about (REQ-d00282-H).
    """
    columns = list(preset.columns)
    if preset.dimension == "uat" and "journeys" not in columns:
        columns.append("journeys")
    return columns


def _report_columns(preset: ReportPreset, columns: Sequence[str] | None) -> list[str]:
    """The columns a rendering states: the selection if one was made, else the default."""
    return list(columns) if columns is not None else _default_columns(preset)


# Implements: REQ-d00282-E
def _json_row(data: dict, columns: Sequence[str], node=None) -> dict:
    """One JSON object stating exactly the columns the report states.

    Shared by the live-graph path and the path a serving process answers, so
    the two cannot state different columns for one selection.
    """
    out: dict = {}
    for col in columns:
        if col == "file":
            # Implements: REQ-d00129-D, REQ-d00129-E
            fn = node.file_node() if node is not None else None
            out["source"] = {
                "path": fn.get_field("relative_path") if fn else data.get("file"),
                "line": node.get_field("parse_line") if node is not None else None,
            }
        elif col == "journeys":
            out["journeys"] = data.get("journeys_detail") or []
        else:
            key = _data_key(col)
            out[key] = data.get(key)
    return out


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
    columns: Sequence[str] | None = None,
    config: dict | None = None,
) -> Iterator[str]:
    """Generate markdown table. Streams one node at a time."""
    if preset is None:
        preset = REPORT_PRESETS[DEFAULT_PRESET]

    yield "# Traceability Matrix"
    yield ""

    # Implements: REQ-d00282-C, REQ-d00282-K
    # Stated in the order the selection names them, headed by words the project
    # configures rather than words spelled here.
    cols = _report_columns(preset, columns)
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
        # printing. Only where the Tested column is stated: a legend pointing
        # at a column this selection does not show explains nothing.
        if "tested" in cols and data.get("tested_breakdown"):
            has_tested_breakdown = True

        row_values = _format_row(data, cols)
        yield "| " + " | ".join(row_values) + " |"

        # Detail rows (controlled by flags, independent of the columns stated)
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
    columns: Sequence[str] | None = None,
    config: dict | None = None,
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

    # Implements: REQ-d00282-C+E+K
    # One header and one cell per stated column, headed by the words the
    # project configures (REQ-d00258-K). Nothing rides alongside: a figure's
    # proportion lives inside its own cell and the Tested breakdown inside the
    # Tested one, so this states the same columns markdown, html and json do.
    cols = _report_columns(preset, columns)
    header_names = [header_for(c, config) for c in cols]
    csv_columns = [_data_key(c) for c in cols]

    extra_prefix = []
    extra_suffix = []
    if preset.include_test_refs:
        extra_prefix.append("Kind")
        extra_suffix.extend(["Assertion", "Test Ref"])

    yield ",".join(extra_prefix + header_names + extra_suffix)

    for node in _scoped_requirements(graph, scope_ids):
        data = _get_node_data(node, graph, assertion_labels=preset.include_assertions)
        row_values = [escape(v) for v in _format_row(data, csv_columns)]

        # Build REQ row
        req_prefix = ["REQ"] if preset.include_test_refs else []
        req_suffix = []
        if preset.include_test_refs:
            req_suffix.extend(["", ""])  # Empty Assertion and Test Ref columns for REQ row

        yield ",".join(req_prefix + row_values + req_suffix)

        # Emit TEST child rows
        if preset.include_test_refs:
            grouped = data["test_refs_grouped"]
            empty_cols = [""] * len(csv_columns)
            for key in ["*"] + sorted(k for k in grouped if k != "*"):
                if key not in grouped:
                    continue
                for ref in grouped[key]:
                    yield ",".join(["TEST"] + empty_cols + [key, escape(ref)])


def format_html(
    graph: FederatedGraph,
    preset: ReportPreset | None = None,
    scope_ids: frozenset[str] | None = None,
    columns: Sequence[str] | None = None,
    config: dict | None = None,
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

    cols = _report_columns(preset, columns)
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


def format_json(
    graph: FederatedGraph,
    preset: ReportPreset | None = None,
    scope_ids: frozenset[str] | None = None,
    columns: Sequence[str] | None = None,
    config: dict | None = None,
) -> Iterator[str]:
    """Generate JSON array. Streams one node at a time."""
    if preset is None:
        preset = REPORT_PRESETS[DEFAULT_PRESET]

    cols = _report_columns(preset, columns)

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
            columns=list(_UAT_COLUMNS),
            dimension="uat",
        )
    else:
        preset_name = getattr(args, "preset", None) or DEFAULT_PRESET
        if preset_name not in REPORT_PRESETS:
            available = ", ".join(REPORT_PRESETS.keys())
            return f"Error: Unknown preset '{preset_name}'\nAvailable: {available}", 1
        preset = ReportPreset(
            name=preset_name,
            columns=list(REPORT_PRESETS[preset_name].columns),
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
    # A section composed with others states the same columns it states alone,
    # and refuses the same selections -- a report is never produced under a
    # selection honoured in part.
    from elspais.commands._columns import resolve_report_columns

    try:
        columns = resolve_report_columns(args, OFFERED_COLUMNS, _default_columns(preset), config)
    except UnofferedColumns as err:
        return f"Error: {err}", 1

    # Implements: REQ-p00084-A+B+D, REQ-d00279-C
    # A section composed with others honours the same scope it honours alone.
    from elspais.commands._scope import resolve_scope_for_report, scope_disclosure

    result = resolve_scope_for_report(graph, args, config)
    scope_ids = None if len(result.ids) == result.population else result.ids
    lines = list(scope_disclosure(result))
    lines += list(formatter(graph, preset, scope_ids, columns, config))
    return "\n".join(lines), 0


def _render_json_from_data(
    data: dict,
    preset: ReportPreset,
    columns: Sequence[str] | None = None,
) -> None:
    """Render JSON output from compute_trace data dict."""
    # Implements: REQ-p00084-D
    # The scope reaches this path inside the computed data, so a JSON report
    # declares the same scope a table one does.
    _print_scope(data.get("scope") or [])
    cols = _report_columns(preset, columns)
    nodes = []
    for node_data in data["nodes"]:
        # Implements: REQ-d00282-E
        # The same row builder the live-graph path uses, so a selection reaches
        # the same columns whether a serving process or this process computed
        # the report.
        node_dict = _json_row(node_data, cols)
        if preset.include_body:
            node_dict["body"] = node_data.get("body", "")
        if preset.include_assertions:
            node_dict["assertions"] = node_data.get("assertions", [])
        if preset.include_test_refs:
            node_dict["test_refs"] = node_data.get("test_refs_grouped", {})
        nodes.append(node_dict)
    print(json.dumps(nodes, indent=2))


# Implements: REQ-p00084-D
def _print_scope(lines: list[str]) -> None:
    """Declare the scope beside the report, on stderr so a piped table is unchanged."""
    for line in lines:
        print(line, file=sys.stderr)


def _render_table_from_graph(
    graph: FederatedGraph,
    fmt: str,
    preset: ReportPreset,
    scope_ids: frozenset[str] | None = None,
    columns: Sequence[str] | None = None,
    config: dict | None = None,
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
    for line in formatter(graph, preset, scope_ids, columns, config):
        print(line)
    return 0


def _resolve_columns_or_report(
    args: argparse.Namespace,
    preset: ReportPreset,
    config: dict | None,
) -> tuple[tuple[str, ...], dict[str, str]] | None:
    """The columns this invocation states and the params carrying them onward.

    Returns None once it has told the reader why the selection was refused:
    REQ-d00282-F wants no report produced under a selection honoured in part,
    and the refusal reaches the reader as a message rather than a traceback.
    """
    from elspais.commands._columns import column_params_from_args, resolve_report_columns

    try:
        columns = resolve_report_columns(args, OFFERED_COLUMNS, _default_columns(preset), config)
    except UnofferedColumns as err:
        print(f"Error: {err}", file=sys.stderr)
        return None
    return columns, column_params_from_args(args, config)


def run(args: argparse.Namespace) -> int:
    """Run the trace command.

    Uses engine.call for daemon-vs-local, then renders in the requested format.
    """
    from elspais.commands import _engine
    from elspais.config import get_config

    fmt = getattr(args, "format", "markdown")
    spec_dir = getattr(args, "spec_dir", None)
    # Implements: REQ-d00254-I
    # --targets marks provenance on the rendered graph; force a local build
    # (bypassing any cached daemon graph) so the fresh set actually threads
    # into build_graph().
    fresh_targets = set(args.targets) if getattr(args, "targets", None) else None
    skip_daemon = bool(spec_dir) or fresh_targets is not None
    dimension = getattr(args, "dimension", "")
    config_path = getattr(args, "config", None)
    config = get_config(config_path)

    if dimension == "uat":
        # Implements: REQ-d00257-A+C, REQ-d00282-H
        # `--dimension uat` is a named default column set and nothing else: it
        # states the UAT dimensions and the journeys validating each row, and
        # leaves the code dimensions out. Which requirements the report is
        # about is the scope's to decide, so a requirement no journey validates
        # is a row reading "no journeys" rather than a row a column switch
        # removed.
        preset = ReportPreset(
            name="uat",
            columns=list(_UAT_COLUMNS),
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
            columns=list(REPORT_PRESETS[preset_name].columns),
            include_body=getattr(args, "body", False),
            include_assertions=getattr(args, "show_assertions", False),
            include_test_refs=getattr(args, "show_tests", False),
        )

    # Implements: REQ-d00282-A+E+F
    # Resolved before anything is built or asked of a serving process, and
    # carried in the same parameters the scope travels in.
    resolved = _resolve_columns_or_report(args, preset, config)
    if resolved is None:
        return 1
    columns, column_params = resolved

    # Implements: REQ-p00084-A+D, REQ-d00279-C
    from elspais.commands._scope import (
        resolve_scope_for_report,
        scope_disclosure,
        scope_params_from_args,
    )

    params = dict(scope_params_from_args(args, config))
    params.update(column_params)

    if skip_daemon:
        # Custom spec_dir (or --targets): build graph directly
        from elspais.graph.factory import build_graph

        graph = build_graph(
            spec_dirs=[spec_dir] if spec_dir else None,
            config_path=config_path,
            fresh_targets=fresh_targets,
        )
        if fmt == "json" and dimension != "uat":
            data = compute_trace(graph, config, params)
            _render_json_from_data(data, preset, columns)
        else:
            result = resolve_scope_for_report(graph, params, config)
            _print_scope(scope_disclosure(result))
            ids = None if len(result.ids) == result.population else result.ids
            return _render_table_from_graph(graph, fmt, preset, ids, columns, config)
    else:
        data = _engine.call(
            "/api/run/trace",
            params,
            compute_trace,
            config_path=config_path,
        )

        # Implements: REQ-d00084-A
        if fmt == "json" and dimension != "uat":
            _render_json_from_data(data, preset, columns)
        else:
            # For non-JSON formats we need the graph to stream through formatters.
            graph = _engine.get_graph()
            result = resolve_scope_for_report(graph, params, config)
            _print_scope(scope_disclosure(result))
            ids = None if len(result.ids) == result.population else result.ids
            return _render_table_from_graph(graph, fmt, preset, ids, columns, config)

    return 0


# Implements: REQ-d00084-A
def run_graph(args: argparse.Namespace) -> int:
    """Export the full traceability graph structure as JSON."""
    from elspais.graph.annotators import annotate_graph_git_state
    from elspais.graph.factory import build_graph
    from elspais.graph.serialize import serialize_graph

    spec_dir = getattr(args, "spec_dir", None)
    config_path = getattr(args, "config", None)
    fresh_targets = set(args.targets) if getattr(args, "targets", None) else None

    graph = build_graph(
        spec_dirs=[spec_dir] if spec_dir else None,
        config_path=config_path,
        fresh_targets=fresh_targets,
    )

    annotate_graph_git_state(graph)
    print(json.dumps(serialize_graph(graph), indent=2))

    return 0
