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
from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from elspais.graph.federated import FederatedGraph

from elspais.graph import NodeKind


@dataclass
class ReportPreset:
    """Configuration for a report preset.

    Columns control what appears in the table.
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


def compute_trace(
    graph: FederatedGraph,
    config: dict,  # noqa: ARG001
    params: dict[str, str],  # noqa: ARG001
) -> dict:
    """Compute trace data for engine.call.  Returns {"nodes": [...]}."""
    nodes = []
    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        nodes.append(_get_node_data(node, graph))
    return {"nodes": nodes}


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
        if total == 0:
            return "n/a"
        pct = round(num / total * 100)
        return f"{fmt_assertion_count(num)}/{total} ({pct}%)"

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

    if rollup:
        from elspais.graph.aggregation import (
            HEADLINE_MEASURE,
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
            if assertion_labels:
                labels = covered_labels(dim, HEADLINE_MEASURE)
                label_str = _compact_labels(labels) if labels else f"0/{dim.total}"
                pct = round(dim.covered / dim.total * 100) if dim.total else 0
                data[key] = f"{label_str} ({pct}%)" if dim.total else "n/a"
                data[key + "_labels"] = label_str if dim.total else "n/a"
                data[key + "_pct"] = f"{pct}%" if dim.total else "n/a"
            else:
                data[key] = _fmt_count(dim.covered, total_a)
            for suffix, _header in _MEASURE_COLUMNS:
                measure = suffix.lstrip("_")
                data[key + suffix] = _fmt_count(measure_total(dim, measure), total_a)
        # Implements: REQ-d00258-O
        # Carried beside the Tested cell rather than inside it, so each format
        # places it: the table appends it, CSV gives it columns of its own.
        # Empty when nothing is tested -- there is no breakdown of an empty set.
        part = tested_partition(rollup)
        data["tested_passed"] = part.passed
        data["tested_failed"] = part.failed
        data["tested_awaiting"] = part.awaiting
        data["tested_breakdown"] = (
            f"[{part.passed}P {part.failed}F {part.awaiting}A]" if part.tested else ""
        )

        ct = rollup.code_tested
        data["code_tested"] = _fmt_code_tested(ct)
        if assertion_labels:
            # Same guard as _fmt_code_tested (REQ-d00258-E): aggregate-only
            # coverage has no per-test attribution to report, so the cells
            # must not claim "0/N"/"0%".
            if ct.total_lines == 0 or not ct.has_attribution:
                data["code_tested_labels"] = "n/a"
                data["code_tested_pct"] = "n/a"
            else:
                data["code_tested_labels"] = f"{ct.attributed_lines:.0f}/{ct.total_lines}"
                data["code_tested_pct"] = f"{round(ct.attributed_lines / ct.total_lines * 100)}%"
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
            lt_by_label = lt.total_by_label
            lt_pct = round(lt.covered / lt.total * 100)
            data["lcov_tested"] = f"lcov {lt_pct}%"
            if assertion_labels:
                labels = {lbl for lbl, frac in lt_by_label.items() if frac > 0}
                label_str = _compact_labels(labels) if labels else f"0/{lt.total}"
                data["lcov_tested_labels"] = label_str
                data["lcov_tested_pct"] = f"{lt_pct}%"
        else:
            data["lcov_tested"] = "n/a"
            if assertion_labels:
                data["lcov_tested_labels"] = "n/a"
                data["lcov_tested_pct"] = "n/a"
    else:
        for key, _ in _DIMS:
            data[key] = "n/a"
            if assertion_labels:
                data[key + "_labels"] = "n/a"
                data[key + "_pct"] = "n/a"
            for suffix, _header in _MEASURE_COLUMNS:
                data[key + suffix] = "n/a"
        data["code_tested"] = "n/a"
        if assertion_labels:
            data["code_tested_labels"] = "n/a"
            data["code_tested_pct"] = "n/a"
        data["lcov_tested"] = "n/a"
        if assertion_labels:
            data["lcov_tested_labels"] = "n/a"
            data["lcov_tested_pct"] = "n/a"

    return data


def _column_headers() -> dict[str, str]:
    """Map column keys to display headers."""
    return {
        "id": "ID",
        "title": "Title",
        "level": "Level",
        "status": "Status",
        "implements": "Implements",
        "implemented": "Implemented",
        "tested": "Tested",
        "verified": "Passing",
        "uat_coverage": "UAT Covered",
        "uat_verified": "UAT Passed",
        "code_tested": "Code Tested",
        "lcov_tested": "LCOV Tested",
        "hash": "Hash",
        "file": "File",
        "journeys": "Journeys",
    }


# The 6 coverage dimension column keys (plus lcov_tested)
_COVERAGE_COLUMNS = [
    "implemented",
    "tested",
    "verified",
    "uat_coverage",
    "uat_verified",
    "code_tested",
    "lcov_tested",
]

# Implements: REQ-d00069-L, REQ-d00258-A
# The four measures behind each of the 5 REQ-d00258-B dimensions, published
# as their own CSV columns beside the dimension's total so a reader can see
# what evidence produced it without a caveat marker (REQ-d00258-J). The
# ``data`` key suffix (``_get_node_data``) and the display-header suffix,
# named once so the CSV writer and the data builder cannot drift apart.
_MEASURE_COLUMNS: list[tuple[str, str]] = [
    ("_immediate_direct", "Immediate Direct"),
    ("_immediate_indirect", "Immediate Indirect"),
    ("_rolled_direct", "Rolled Direct"),
    ("_rolled_indirect", "Rolled Indirect"),
]

# The 5 REQ-d00258-B display dimensions -- code_tested/lcov_tested are
# diagnostic columns outside that vocabulary and carry no total/measure
# split of their own.
_COVERAGE_COLUMNS_WITH_MEASURES = [
    "implemented",
    "tested",
    "verified",
    "uat_coverage",
    "uat_verified",
]


def _add_measure_fields(node_dict: dict, data: dict, columns: list[str]) -> None:
    """Add the four REQ-d00069-L measure fields for each rendered dimension.

    JSON's per-requirement object is where REQ-d00258-A's "available" is
    cheapest to satisfy without widening the text/markdown/html table: a
    field costs nothing to a reader who is not looking at it. Only for
    dimensions actually present in ``columns`` (the UAT preset excludes the
    code dimensions; the minimal preset excludes coverage entirely).
    """
    for col in columns:
        if col not in _COVERAGE_COLUMNS_WITH_MEASURES:
            continue
        for suffix, _header in _MEASURE_COLUMNS:
            node_dict[col + suffix] = data.get(col + suffix)


def _format_row(data: dict, columns: list[str]) -> list[str]:
    """Format a single row from node data according to columns."""
    values = []
    for col in columns:
        if col == "implements":
            values.append(", ".join(data["implements"]) or "-")
        else:
            values.append(str(data.get(col, "")))
    return values


def format_markdown(graph: FederatedGraph, preset: ReportPreset | None = None) -> Iterator[str]:
    """Generate markdown table. Streams one node at a time."""
    if preset is None:
        preset = REPORT_PRESETS[DEFAULT_PRESET]

    yield "# Traceability Matrix"
    yield ""

    # Determine columns: UAT dimension uses fixed UAT columns + synthetic journeys column
    column_headers = _column_headers()
    if preset.dimension == "uat":
        columns = list(_UAT_COLUMNS) + ["journeys"]
    else:
        columns = preset.columns
    headers = [column_headers.get(col, col.title()) for col in columns]
    yield "| " + " | ".join(headers) + " |"
    yield "|" + "|".join(["----"] * len(headers)) + "|"

    # Implements: REQ-d00254-I+J
    # Track whether any rendered row actually produced a `(baseline)`/`—`
    # marker in its verified cell, so the legend is only emitted when it's
    # relevant (and full-run output stays byte-identical to before).
    has_carry_marker = False
    # Implements: REQ-d00258-O
    has_tested_breakdown = False

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if preset.dimension == "uat":
            uat_jnys = _get_uat_journeys(node)
            if not uat_jnys:
                continue  # exclude requirements with no VALIDATES edges
            data = _get_node_data(node, graph, assertion_labels=preset.include_assertions)
            data["journeys"] = "; ".join(f"{j['id']}:{j['verdict']}" for j in uat_jnys)
        else:
            data = _get_node_data(node, graph, assertion_labels=preset.include_assertions)

        if "verified" in columns:
            verified_cell = data.get("verified", "")
            if "(baseline)" in verified_cell or "—" in verified_cell:
                has_carry_marker = True
        # Implements: REQ-d00258-O
        # Only where the Tested column is rendered: a breakdown of a figure
        # this preset does not show explains nothing, and its legend would
        # point at a column that is not there.
        if "tested" in columns and data.get("tested_breakdown"):
            data["tested"] = f"{data['tested']} {data['tested_breakdown']}"
            has_tested_breakdown = True

        row_values = _format_row(data, columns)
        yield "| " + " | ".join(row_values) + " |"

        if preset.dimension == "uat":
            continue  # no detail rows in UAT view

        # Detail rows (controlled by flags, independent of preset)
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
    # Only surface the legend when a row actually used a marker it explains,
    # and never for the UAT dimension (which has no verified column).
    if has_carry_marker and preset.dimension != "uat":
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


def format_csv(graph: FederatedGraph, preset: ReportPreset | None = None) -> Iterator[str]:
    """Generate CSV. Streams one node at a time.

    When test refs are included, adds a Kind column (first) and Assertion/Test Ref
    columns (last). Each test ref gets its own TEST row after its parent REQ row.

    When dimension == 'uat', uses UAT columns only (no code columns) and adds a
    Journeys column; only requirements with incoming VALIDATES edges are emitted.
    """
    if preset is None:
        preset = REPORT_PRESETS[DEFAULT_PRESET]

    def escape(s: str) -> str:
        if "," in s or '"' in s or "\n" in s:
            return '"' + s.replace('"', '""') + '"'
        return s

    if preset.dimension == "uat":
        # UAT dimension: fixed columns + journeys, no code columns, no test-ref rows
        col_headers = _column_headers()
        uat_csv_cols = list(_UAT_COLUMNS) + ["journeys"]
        header_names = [col_headers.get(c, c.title()) for c in uat_csv_cols]
        yield ",".join(header_names)

        for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
            uat_jnys = _get_uat_journeys(node)
            if not uat_jnys:
                continue
            data = _get_node_data(node, graph)
            data["journeys"] = "; ".join(f"{j['id']}:{j['verdict']}" for j in uat_jnys)
            row_values = [escape(str(data.get(c, ""))) for c in uat_csv_cols]
            yield ",".join(row_values)
        return

    # Build header — split coverage columns into Labels + % for CSV
    # when --assertions is active
    col_headers = _column_headers()
    header_names: list[str] = []
    csv_columns: list[str] = []  # actual data keys per CSV cell
    for c in preset.columns:
        if preset.include_assertions and c in _COVERAGE_COLUMNS:
            display = col_headers.get(c, c.title())
            header_names.extend([display, f"{display} %"])
            csv_columns.extend([c + "_labels", c + "_pct"])
        else:
            header_names.append(col_headers.get(c, c.title()))
            csv_columns.append(c)
        # Implements: REQ-d00258-O
        # Columns rather than a bracket inside the Tested cell: a machine
        # format should not need to parse a figure out of prose.
        if c == "tested":
            header_names.extend(["Tested Passed", "Tested Failed", "Tested Awaiting"])
            csv_columns.extend(["tested_passed", "tested_failed", "tested_awaiting"])
        # Implements: REQ-d00069-L, REQ-d00258-A, REQ-d00258-J
        # The four measures behind this dimension's total, as columns of
        # their own -- what REQ-d00258-A requires a reader be able to see,
        # published rather than summarized by a caveat marker (REQ-d00258-J).
        if c in _COVERAGE_COLUMNS_WITH_MEASURES:
            display = col_headers.get(c, c.title())
            header_names.extend(f"{display} {label}" for _suffix, label in _MEASURE_COLUMNS)
            csv_columns.extend(c + suffix for suffix, _label in _MEASURE_COLUMNS)

    extra_prefix = []
    extra_suffix = []
    if preset.include_test_refs:
        extra_prefix.append("Kind")
        extra_suffix.extend(["Assertion", "Test Ref"])

    yield ",".join(extra_prefix + header_names + extra_suffix)

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
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


def format_html(graph: FederatedGraph, preset: ReportPreset | None = None) -> Iterator[str]:
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

    # Determine columns for UAT dimension
    col_hdrs = _column_headers()
    if preset.dimension == "uat":
        columns = list(_UAT_COLUMNS) + ["journeys"]
        headers = [col_hdrs.get(col, col.title()) for col in columns]
    else:
        columns = preset.columns
        headers = [col_hdrs.get(col, col.title()) for col in columns]
        if preset.include_test_refs:
            headers.append("Test Refs")

    yield "<table>"
    yield "<tr>" + "".join(f"<th>{h}</th>" for h in headers) + "</tr>"

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if preset.dimension == "uat":
            uat_jnys = _get_uat_journeys(node)
            if not uat_jnys:
                continue
            data = _get_node_data(node, graph)
            data["journeys"] = "; ".join(f"{j['id']}:{j['verdict']}" for j in uat_jnys)
            cells = [f"<td>{escape_html(str(data.get(col, '')))}</td>" for col in columns]
            yield f"<tr>{''.join(cells)}</tr>"
            continue

        data = _get_node_data(node, graph, assertion_labels=preset.include_assertions)
        cells = []
        for val in _format_row(data, preset.columns):
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


def format_json(graph: FederatedGraph, preset: ReportPreset | None = None) -> Iterator[str]:
    """Generate JSON array. Streams one node at a time."""
    if preset is None:
        preset = REPORT_PRESETS[DEFAULT_PRESET]

    yield "["
    first = True
    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if preset.dimension == "uat":
            uat_jnys = _get_uat_journeys(node)
            if not uat_jnys:
                continue  # exclude requirements with no VALIDATES edges

        if not first:
            yield ","
        first = False

        data = _get_node_data(node, graph, assertion_labels=preset.include_assertions)

        if preset.dimension == "uat":
            # UAT view: only uat_coverage, uat_verified, and journeys; no code columns
            node_dict: dict = {col: data.get(col) for col in _UAT_COLUMNS}
            _add_measure_fields(node_dict, data, _UAT_COLUMNS)
            node_dict["journeys"] = uat_jnys
            yield json.dumps(node_dict, indent=2)
            continue

        # Build node dict based on preset columns
        node_dict = {}
        for col in preset.columns:
            if col == "file":
                # Implements: REQ-d00129-D, REQ-d00129-E
                _fn = node.file_node()
                node_dict["source"] = {
                    "path": _fn.get_field("relative_path") if _fn else None,
                    "line": node.get_field("parse_line"),
                }
            else:
                node_dict[col] = data.get(col)
        # Implements: REQ-d00069-L, REQ-d00258-A
        # JSON carries the four measures behind each dimension's total as
        # fields of their own -- the brief requires it, and unlike the
        # text/markdown/html table (already 11 columns wide) a JSON object
        # has no readability cost to adding four fields per dimension.
        _add_measure_fields(node_dict, data, preset.columns)

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

    lines = list(formatter(graph, preset))
    return "\n".join(lines), 0


def _render_json_from_data(data: dict, preset: ReportPreset) -> None:
    """Render JSON output from compute_trace data dict."""
    nodes = []
    for node_data in data["nodes"]:
        node_dict: dict = {}
        for col in preset.columns:
            if col == "file":
                node_dict["source"] = {
                    "path": node_data.get("file"),
                    "line": None,
                }
            else:
                node_dict[col] = node_data.get(col)
        # Implements: REQ-d00069-L, REQ-d00258-A
        _add_measure_fields(node_dict, node_data, preset.columns)
        if preset.include_body:
            node_dict["body"] = node_data.get("body", "")
        if preset.include_assertions:
            node_dict["assertions"] = node_data.get("assertions", [])
        if preset.include_test_refs:
            node_dict["test_refs"] = node_data.get("test_refs_grouped", {})
        nodes.append(node_dict)
    print(json.dumps(nodes, indent=2))


def _render_table_from_graph(graph: FederatedGraph, fmt: str, preset: ReportPreset) -> int:
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
    for line in formatter(graph, preset):
        print(line)
    return 0


def run(args: argparse.Namespace) -> int:
    """Run the trace command.

    Uses engine.call for daemon-vs-local, then renders in the requested format.
    """
    from elspais.commands import _engine

    fmt = getattr(args, "format", "markdown")
    spec_dir = getattr(args, "spec_dir", None)
    # Implements: REQ-d00254-I
    # --targets marks provenance on the rendered graph; force a local build
    # (bypassing any cached daemon graph) so the fresh set actually threads
    # into build_graph().
    fresh_targets = set(args.targets) if getattr(args, "targets", None) else None
    skip_daemon = bool(spec_dir) or fresh_targets is not None
    dimension = getattr(args, "dimension", "")

    if dimension == "uat":
        # Implements: REQ-d00257
        # UAT dimension always uses graph-based rendering (needs VALIDATES edge access)
        preset = ReportPreset(
            name="uat",
            columns=list(_UAT_COLUMNS),
            dimension="uat",
        )
        config_path = getattr(args, "config", None)
        if skip_daemon:
            from elspais.graph.factory import build_graph

            graph = build_graph(
                spec_dirs=[spec_dir] if spec_dir else None,
                config_path=config_path,
                fresh_targets=fresh_targets,
            )
        else:
            _engine.call(
                "/api/run/trace",
                {},
                compute_trace,
                config_path=config_path,
            )
            graph = _engine.get_graph()
        return _render_table_from_graph(graph, fmt, preset)

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

    if skip_daemon:
        # Custom spec_dir (or --targets): build graph directly
        from elspais.graph.factory import build_graph

        config_path = getattr(args, "config", None)
        graph = build_graph(
            spec_dirs=[spec_dir] if spec_dir else None,
            config_path=config_path,
            fresh_targets=fresh_targets,
        )
        if fmt == "json":
            data = compute_trace(graph, {}, {})
            _render_json_from_data(data, preset)
        else:
            return _render_table_from_graph(graph, fmt, preset)
    else:
        data = _engine.call(
            "/api/run/trace",
            {},
            compute_trace,
            config_path=getattr(args, "config", None),
        )

        # Implements: REQ-d00084-A
        if fmt == "json":
            _render_json_from_data(data, preset)
        else:
            # For non-JSON formats we need the graph to stream through formatters.
            graph = _engine.get_graph()
            return _render_table_from_graph(graph, fmt, preset)

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
