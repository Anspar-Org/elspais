# Verifies: REQ-d00282
"""One named column is one column, in every format, on every surface that
offers the flag -- and no report at all under a selection the tool cannot
honour in full.

The other axis of the same report lives in ``tests/graph/test_scope.py``.
These are the properties that fail SILENTLY: a report whose column set moves
with the format still looks like a report, and a refused one that leaves an
artifact behind looks like the report that was asked for.
"""

from __future__ import annotations

import argparse
import csv
import io
import json

import pytest

from elspais.commands import report as report_cmd
from elspais.commands import summary as summary_cmd
from elspais.commands import trace as trace_cmd
from elspais.graph.builder import TraceGraph
from elspais.graph.GraphNode import GraphNode, NodeKind
from elspais.graph.metrics import CoverageDimension, RollupMetrics

# The selections the invariance is checked over: one dimension, two dimensions,
# and one naming its identity column out of its usual place (REQ-d00282-K).
SELECTIONS = ("tested", "implemented,uat_coverage", "status,id,implemented")


# ---------------------------------------------------------------------------
# Reading a column set back out of a rendering
# ---------------------------------------------------------------------------


def _trace_columns(graph, fmt: str, columns: list[str]) -> list[str]:
    """The columns one trace rendering states, as the reader meets them."""
    preset = trace_cmd.ReportPreset(
        name="standard", columns=list(trace_cmd.REPORT_PRESETS["standard"].columns)
    )
    formatter = {
        "csv": trace_cmd.format_csv,
        "markdown": trace_cmd.format_markdown,
        "html": trace_cmd.format_html,
        "json": trace_cmd.format_json,
    }[fmt]
    out = "\n".join(formatter(graph, preset, None, columns, None))
    if fmt == "csv":
        return next(csv.reader(io.StringIO(out)))
    if fmt == "markdown":
        header = next(ln for ln in out.splitlines() if ln.startswith("| "))
        return [c.strip() for c in header.strip("|").split("|")]
    if fmt == "html":
        row = out.split("<tr>")[1]
        return [c.split("</th>")[0] for c in row.split("<th>")[1:]]
    return list(json.loads(out)[0].keys())


def _summary_columns(data: dict, fmt: str) -> list[str]:
    """The columns one summary rendering states."""
    out = summary_cmd._render(dict(data), fmt, None)
    if fmt == "csv":
        return next(csv.reader(io.StringIO(out)))
    if fmt == "markdown":
        header = next(ln for ln in out.splitlines() if ln.startswith("| "))
        return [c.strip() for c in header.strip("|").split("|")]
    return list(json.loads(out)["levels"][0].keys())


# ---------------------------------------------------------------------------
# Estates
# ---------------------------------------------------------------------------


def _level_row(level: str, requirements: int, assertions: int) -> dict:
    """One collect_coverage-shaped level row, with every figure at zero.

    An assertion-less group is the case REQ-d00282-M turns on, so both kinds
    are built from the same shape and differ only in the count.
    """
    row = {
        "level": level,
        "total": requirements,
        "total_assertions": assertions,
        "tested_passed": 0,
        "tested_failed": 0,
        "tested_awaiting": 0,
    }
    for prefix in ("implemented", "tested", "passing", "uat_covered", "uat_passed"):
        row[f"{prefix}_total_covered"] = 0.0
        for measure in (
            "immediate_direct",
            "immediate_indirect",
            "rolled_direct",
            "rolled_indirect",
        ):
            row[f"{prefix}_{measure}"] = 0.0
    return row


@pytest.fixture()
def coverage_payload() -> dict:
    """Two groups: one with assertions and no evidence, one with no assertions.

    PRD has four assertions and nothing covering them -- a real zero. OPS has
    requirements conferring no *Assertion* at all, so it is owed no coverage
    and has no figure to state.
    """
    return {
        "levels": [_level_row("PRD", 2, 4), _level_row("OPS", 1, 0)],
        "excluded": {},
        "integrations": [],
    }


def _requirement_graph() -> TraceGraph:
    graph = TraceGraph()
    node = GraphNode("REQ-p00001", NodeKind.REQUIREMENT, label="Columns")
    node.set_field("level", "prd")
    node.set_field("status", "Active")
    node.set_metric(
        "rollup_metrics",
        RollupMetrics(
            total_assertions=2,
            implemented=CoverageDimension(total=2, immediate_direct_by_label={"A": 1.0}),
            tested=CoverageDimension(total=2, immediate_direct_by_label={"A": 1.0}),
        ),
    )
    graph._index[node.id] = node
    graph._roots.append(node)
    return graph


# ---------------------------------------------------------------------------
# REQ-d00282-E: the format decides how a report looks, never what it states
# ---------------------------------------------------------------------------


class TestOneSelectionOneColumnSet:
    # Verifies: REQ-d00282-E+K
    @pytest.mark.parametrize("selection", SELECTIONS)
    def test_trace_states_one_column_set_in_every_format(
        self, canonical_federated_graph, selection
    ):
        """csv, markdown, html and json state the same columns in the same
        order. json names them by key and the others by display word, so the
        comparison is by count and position, checked against the selection."""
        columns = selection.split(",")
        stated = {
            fmt: _trace_columns(canonical_federated_graph, fmt, columns)
            for fmt in ("csv", "markdown", "html", "json")
        }
        assert stated["json"] == columns, stated["json"]
        expected = [trace_cmd.header_for(c, None) for c in columns]
        for fmt in ("csv", "markdown", "html"):
            assert stated[fmt] == expected, f"{fmt} states {stated[fmt]}"

    # Verifies: REQ-d00282-E+K
    @pytest.mark.parametrize("selection", ("tested", "implemented,uat_coverage"))
    def test_summary_states_one_column_set_in_every_format(self, coverage_payload, selection):
        columns = ["level", *selection.split(",")]
        payload = {**coverage_payload, "columns": columns}
        assert _summary_columns(payload, "json") == columns
        expected = [summary_cmd.header_for(c, None) for c in columns]
        for fmt in ("csv", "markdown"):
            assert _summary_columns(payload, fmt) == expected, fmt

    # Verifies: REQ-d00282-E, REQ-d00258-O+P
    def test_a_figure_states_its_own_denominator_and_proportion(self, coverage_payload):
        """One named column produces one cell carrying the whole fact.

        Split across companion cells, `--columns implemented` produced five
        columns in CSV and one in markdown -- and the denominator a reader
        needs to check a figure (REQ-d00258-P) went missing from the format
        that dropped the companions."""
        payload = {**coverage_payload, "columns": ["level", "implemented"]}
        rows = list(csv.reader(io.StringIO(summary_cmd._render(payload, "csv", None))))
        assert rows[0] == ["Level", "Implemented"]
        assert rows[1] == ["PRD", "0/4 (0.0%)"]

    # Verifies: REQ-d00282-L
    def test_the_identity_column_is_stated_whatever_was_named(self, coverage_payload):
        """A row that cannot be attributed to what it is a fact about is not a
        report about anything."""
        columns = summary_cmd._resolve_columns(
            argparse.Namespace(columns="tested", scope=None), None
        )
        assert columns[0] == "level"


# ---------------------------------------------------------------------------
# REQ-d00282-M: nothing to state is not a figure of zero
# ---------------------------------------------------------------------------


class TestAbsenceIsNotZero:
    # Verifies: REQ-d00282-M
    @pytest.mark.parametrize("fmt", ("markdown", "csv"))
    def test_a_group_owed_no_coverage_states_no_figure(self, coverage_payload, fmt):
        """OPS confers no *Assertion*, so it is owed no coverage; PRD has four
        and nothing covering them. Read as the same 0 they call for opposite
        actions."""
        payload = {**coverage_payload, "columns": ["level", "implemented"]}
        out = summary_cmd._render(payload, fmt, None)
        ops_line = next(ln for ln in out.splitlines() if "OPS" in ln)
        prd_line = next(ln for ln in out.splitlines() if "PRD" in ln)
        assert "0/4 (0.0%)" in prd_line
        assert summary_cmd.ABSENT_FIGURE in ops_line, ops_line
        assert "0/" not in ops_line, ops_line

    # Verifies: REQ-d00282-M
    def test_the_text_report_says_a_group_is_owed_no_coverage(self, coverage_payload):
        """Text states it once for the group rather than printing a row of
        marks: every figure in the row is absent for the same one reason."""
        payload = {**coverage_payload, "columns": ["level", "implemented"]}
        lines = summary_cmd._render(payload, "text", None).splitlines()
        prd = lines[lines.index("  PRD:") + 1]
        ops = lines[lines.index("  OPS:") + 1]
        assert "0/4 (0.0%)" in prd
        assert "no coverage figure is stated" in ops
        assert "0/" not in ops

    # Verifies: REQ-d00282-M, REQ-d00258-O
    def test_json_states_null_where_there_is_no_figure(self, coverage_payload):
        """Including the counts qualifying Tested: a breakdown of a figure that
        was never taken is not three zeros."""
        payload = {**coverage_payload, "columns": ["level", "implemented", "tested"]}
        levels = {
            lv["level"]: lv
            for lv in json.loads(summary_cmd._render(payload, "json", None))["levels"]
        }
        assert levels["OPS"]["implemented"] is None
        assert levels["OPS"]["tested"] is None
        assert levels["PRD"]["implemented"] == "0/4 (0.0%)"

    # Verifies: REQ-d00282-M, REQ-d00258-O
    def test_the_unselected_payload_keeps_the_distinction_too(self, coverage_payload):
        """A reader who named no columns receives the whole payload, and it
        answers the same question the same way."""
        levels = {
            lv["level"]: lv
            for lv in json.loads(summary_cmd._render(coverage_payload, "json", None))["levels"]
        }
        assert levels["OPS"]["implemented_total_covered"] is None
        assert levels["OPS"]["tested_awaiting"] is None
        # A real group's zeros are real answers and stay as computed.
        assert levels["PRD"]["implemented_total_covered"] == 0.0
        assert levels["PRD"]["tested_awaiting"] == 0


# ---------------------------------------------------------------------------
# REQ-d00282-F: no report under a selection honoured in part
# ---------------------------------------------------------------------------


class TestARefusedReportProducesNothing:
    # Verifies: REQ-d00282-F
    def test_a_composed_report_writes_no_file_when_it_refuses(self, tmp_path, capsys):
        out = tmp_path / "report.txt"
        code = report_cmd.run(["summary", "trace"], ["--columns", "bogus", "-o", str(out)])
        assert code != 0
        assert not out.exists(), "A refused report produced the artifact it refused"
        assert "bogus" in capsys.readouterr().err

    # Verifies: REQ-d00282-F
    def test_a_composed_report_refuses_a_section_that_states_no_columns(self, tmp_path, capsys):
        """`gaps` lists what is missing rather than tabulating facts, so a
        selection reaching it is one the composed report cannot honour."""
        out = tmp_path / "report.txt"
        code = report_cmd.run(["summary", "gaps"], ["--columns", "tested", "-o", str(out)])
        assert code != 0
        assert not out.exists()
        assert "gaps" in capsys.readouterr().err

    # Verifies: REQ-d00282-F
    def test_a_composed_report_is_produced_when_every_section_honours_it(self, tmp_path):
        out = tmp_path / "report.txt"
        code = report_cmd.run(["summary", "trace"], ["--columns", "tested", "-o", str(out)])
        assert code == 0
        assert out.exists()

    # Verifies: REQ-d00282-F
    def test_the_refusal_names_every_column_that_did_not_resolve(self):
        from elspais.graph.columns import UnofferedColumns, parse_column_selection, resolve_columns

        with pytest.raises(UnofferedColumns) as excinfo:
            resolve_columns(parse_column_selection("tested,nope,also_nope"), ("id", "tested"))
        assert excinfo.value.unoffered == ("nope", "also_nope")


# ---------------------------------------------------------------------------
# REQ-d00282-A: a flag a command cannot honour is worse than its absence
# ---------------------------------------------------------------------------


class TestOnlyReportsThatStateColumnsOfferTheFlag:
    # Verifies: REQ-d00282-A+F
    @pytest.mark.parametrize(
        "args_class",
        (
            "GapsArgs",
            "UncoveredArgs",
            "UntestedArgs",
            "UnvalidatedArgs",
            "FailingArgs",
            "AnalysisArgs",
        ),
    )
    def test_a_gap_listing_does_not_accept_a_column_selection(self, args_class):
        """These emit lists of what is missing, not tables of facts about
        requirements. They share the SCOPE vocabulary and not this one."""
        import dataclasses

        from elspais.commands import args as args_mod

        fields = {f.name for f in dataclasses.fields(getattr(args_mod, args_class))}
        assert "columns" not in fields
        assert "level" in fields, "the scope axis is shared and stays shared"

    # Verifies: REQ-d00282-A
    @pytest.mark.parametrize("args_class", ("TraceArgs", "SummaryArgs"))
    def test_the_reports_that_state_columns_accept_the_selection(self, args_class):
        import dataclasses

        from elspais.commands import args as args_mod

        fields = {f.name for f in dataclasses.fields(getattr(args_mod, args_class))}
        assert "columns" in fields

    # Verifies: REQ-d00282-A
    def test_summary_offers_the_group_columns_and_not_the_per_requirement_ones(self):
        """Its rows are levels: it has a requirement count and no title."""
        offered = set(summary_cmd.OFFERED_COLUMNS)
        assert {"level", "requirements", "assertions"} <= offered
        assert not offered & {"id", "title", "hash", "file", "code_tested", "lcov_tested"}

    # Verifies: REQ-d00282-A
    def test_trace_offers_no_column_only_a_group_could_state(self):
        """Its rows are single requirements: there is no count of the
        requirements in one requirement."""
        assert not set(trace_cmd.OFFERED_COLUMNS) & {"requirements", "assertions"}
        assert {"id", "title", "code_tested"} <= set(trace_cmd.OFFERED_COLUMNS)


# ---------------------------------------------------------------------------
# REQ-d00282-D+H: a selection decides which facts, never which or what
# ---------------------------------------------------------------------------


class TestSelectingColumnsChangesNothingElse:
    # Verifies: REQ-d00282-D
    @pytest.mark.parametrize("selection", (["id", "tested"], ["id", "title", "level", "tested"]))
    def test_a_figure_reads_the_same_however_few_columns_were_asked_for(self, selection):
        graph = _requirement_graph()
        narrow = _trace_columns(graph, "json", selection)
        rows = json.loads("\n".join(trace_cmd.format_json(graph, None, None, selection, None)))
        assert "tested" in narrow
        # The breakdown qualifying it rides in the cell; the FIGURE is what a
        # narrower selection may not move.
        assert rows[0]["tested"].startswith("1/2 (50%)")

    # Verifies: REQ-d00282-H
    def test_selecting_columns_does_not_change_which_requirements_are_reported(
        self, canonical_federated_graph
    ):
        wide = json.loads(
            "\n".join(
                trace_cmd.format_json(
                    canonical_federated_graph, None, None, ["id", "title", "tested"], None
                )
            )
        )
        narrow = json.loads(
            "\n".join(trace_cmd.format_json(canonical_federated_graph, None, None, ["id"], None))
        )
        assert [r["id"] for r in wide] == [r["id"] for r in narrow]
