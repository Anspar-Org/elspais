# Verifies: REQ-d00282
"""One named value is one value, in every format, on every surface that
offers the flag -- and no report at all under a selection the tool cannot
honour in full.

A value is not a column: a column is how a table renders one, and a format
with numbers states the same value as numbers under the path its key spells.
The other axis of the same report lives in ``tests/graph/test_scope.py``.
These are the properties that fail SILENTLY: a report whose value set moves
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
from elspais.graph.metrics import CoverageDimension, LineCoverage, RollupMetrics

# The selections the invariance is checked over: one dimension, two dimensions,
# and one naming its identity value out of its usual place (REQ-d00282-K).
SELECTIONS = ("tested", "implemented,uat_coverage", "status,id,implemented")


# ---------------------------------------------------------------------------
# Reading a column set back out of a rendering
# ---------------------------------------------------------------------------


def _trace_stated(graph, fmt: str, values: list[str]) -> list[str]:
    """What one trace rendering states, as the reader meets it.

    A table states one heading per value; a structured format states the HEAD
    of each value's path, so two values beneath one figure meet the reader as
    one object rather than two keys (REQ-d00282-B).
    """
    preset = trace_cmd.ReportPreset(
        name="standard", values=list(trace_cmd.REPORT_PRESETS["standard"].values)
    )
    formatter = {
        "csv": trace_cmd.format_csv,
        "markdown": trace_cmd.format_markdown,
        "html": trace_cmd.format_html,
        "json": trace_cmd.format_json,
    }[fmt]
    out = "\n".join(formatter(graph, preset, None, values, None))
    if fmt == "csv":
        return next(csv.reader(io.StringIO(out)))
    if fmt == "markdown":
        header = next(ln for ln in out.splitlines() if ln.startswith("| "))
        return [c.strip() for c in header.strip("|").split("|")]
    if fmt == "html":
        row = out.split("<tr>")[1]
        return [c.split("</th>")[0] for c in row.split("<th>")[1:]]
    return list(json.loads(out)[0].keys())


def _summary_stated(data: dict, fmt: str) -> list[str]:
    """What one summary rendering states, by the same reading."""
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
    node = GraphNode("REQ-p00001", NodeKind.REQUIREMENT, label="Values")
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


class TestOneSelectionOneValueSet:
    # Verifies: REQ-d00282-K, REQ-p00084-C
    @pytest.mark.parametrize("selection", SELECTIONS)
    def test_trace_states_one_value_set_in_every_format(self, canonical_federated_graph, selection):
        """csv, markdown, html and json state the same values in the same
        order. json names them by key and the others by display word, so the
        comparison is by count and position, checked against the selection."""
        values = selection.split(",")
        stated = {
            fmt: _trace_stated(canonical_federated_graph, fmt, values)
            for fmt in ("csv", "markdown", "html", "json")
        }
        assert stated["json"] == values, stated["json"]
        expected = [trace_cmd.header_for(c, None) for c in values]
        for fmt in ("csv", "markdown", "html"):
            assert stated[fmt] == expected, f"{fmt} states {stated[fmt]}"

    # Verifies: REQ-d00282-K, REQ-p00084-C
    @pytest.mark.parametrize("selection", ("tested", "implemented,uat_coverage"))
    def test_summary_states_one_value_set_in_every_format(self, coverage_payload, selection):
        values = ["level", *selection.split(",")]
        payload = {**coverage_payload, "values": values}
        assert _summary_stated(payload, "json") == values
        expected = [summary_cmd.header_for(c, None) for c in values]
        for fmt in ("csv", "markdown"):
            assert _summary_stated(payload, fmt) == expected, fmt

    # Verifies: REQ-p00084-C, REQ-d00258-O+P
    def test_a_figure_states_its_own_denominator_and_proportion(self, coverage_payload):
        """One named value produces one cell carrying the whole fact.

        Split across companion cells, `--values implemented` produced five
        columns in CSV and one in markdown -- and the denominator a reader
        needs to check a figure (REQ-d00258-P) went missing from the format
        that dropped the companions."""
        payload = {**coverage_payload, "values": ["level", "implemented"]}
        rows = list(csv.reader(io.StringIO(summary_cmd._render(payload, "csv", None))))
        assert rows[0] == ["Level", "Implemented"]
        assert rows[1] == ["PRD", "0/4 (0.0%)"]

    # Verifies: REQ-d00282-L
    def test_the_identity_value_is_stated_whatever_was_named(self):
        """A row that cannot be attributed to what it is a fact about is not a
        report about anything."""
        values = summary_cmd._resolve_values_for(
            argparse.Namespace(values="tested", scope=None), None
        )
        assert values[0] == "level"


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
        payload = {**coverage_payload, "values": ["level", "implemented"]}
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
        payload = {**coverage_payload, "values": ["level", "implemented"]}
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
        payload = {**coverage_payload, "values": ["level", "implemented", "tested"]}
        levels = {
            lv["level"]: lv
            for lv in json.loads(summary_cmd._render(payload, "json", None))["levels"]
        }
        # A figure a group does not have is null OUTRIGHT, not an object whose
        # every number is null: there is no figure to decompose.
        assert levels["OPS"]["implemented"] is None
        assert levels["OPS"]["tested"] is None
        # PRD confers four assertions and nothing covers them: a real zero,
        # stated as the numbers it is made of.
        assert levels["PRD"]["implemented"] == {"count": 0.0, "total": 4.0, "ratio": 0.0}

    # Verifies: REQ-d00282-M, REQ-d00258-O
    def test_the_unselected_payload_keeps_the_distinction_too(self, coverage_payload):
        """A reader who named no values receives the whole payload, and it
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
        code = report_cmd.run(["summary", "trace"], ["--values", "bogus", "-o", str(out)])
        assert code != 0
        assert not out.exists(), "A refused report produced the artifact it refused"
        assert "bogus" in capsys.readouterr().err

    # Verifies: REQ-d00282-F
    def test_a_composed_report_refuses_a_section_that_states_no_values(self, tmp_path, capsys):
        """`gaps` lists what is missing rather than tabulating facts, so a
        selection reaching it is one the composed report cannot honour."""
        out = tmp_path / "report.txt"
        code = report_cmd.run(["summary", "gaps"], ["--values", "tested", "-o", str(out)])
        assert code != 0
        assert not out.exists()
        assert "gaps" in capsys.readouterr().err

    # Verifies: REQ-d00282-F
    def test_a_composed_report_is_produced_when_every_section_honours_it(self, tmp_path):
        out = tmp_path / "report.txt"
        code = report_cmd.run(["summary", "trace"], ["--values", "tested", "-o", str(out)])
        assert code == 0
        assert out.exists()

    # Verifies: REQ-d00282-F
    def test_the_refusal_names_every_value_that_did_not_resolve(self):
        from elspais.graph.values import UnofferedValues, parse_value_selection, resolve_values

        with pytest.raises(UnofferedValues) as excinfo:
            resolve_values(parse_value_selection("tested,nope,also_nope"), ("id", "tested"))
        assert excinfo.value.unoffered == ("nope", "also_nope")


# ---------------------------------------------------------------------------
# REQ-d00282-A: a flag a command cannot honour is worse than its absence
# ---------------------------------------------------------------------------


class TestOnlyReportsThatStateValuesOfferTheFlag:
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
    def test_a_gap_listing_does_not_accept_a_value_selection(self, args_class):
        """These emit lists of what is missing, not tables of facts about
        requirements. They share the SCOPE vocabulary and not this one."""
        import dataclasses

        from elspais.commands import args as args_mod

        fields = {f.name for f in dataclasses.fields(getattr(args_mod, args_class))}
        assert "values" not in fields
        assert "level" in fields, "the scope axis is shared and stays shared"

    # Verifies: REQ-d00282-A
    @pytest.mark.parametrize("args_class", ("TraceArgs", "SummaryArgs"))
    def test_the_reports_that_state_values_accept_the_selection(self, args_class):
        import dataclasses

        from elspais.commands import args as args_mod

        fields = {f.name for f in dataclasses.fields(getattr(args_mod, args_class))}
        assert "values" in fields

    # Verifies: REQ-d00282-A+N
    def test_summary_offers_the_group_values_and_not_the_per_requirement_ones(self):
        """Its rows are levels: it has a requirement count and no title.

        The line figure IS offered: a level sums the lines its requirements
        measure, so narrowing from a requirement to the group it belongs to
        must not lose the answer (REQ-d00282-N).
        """
        offered = set(summary_cmd.OFFERED_VALUES)
        assert {"level", "requirements", "assertions", "code_tested"} <= offered
        assert not offered & {"id", "title", "hash", "file", "lcov_tested"}

    # Verifies: REQ-d00282-A
    def test_trace_offers_no_value_only_a_group_could_state(self):
        """Its rows are single requirements: there is no count of the
        requirements in one requirement."""
        assert not set(trace_cmd.OFFERED_VALUES) & {"requirements", "assertions"}
        assert {"id", "title", "code_tested"} <= set(trace_cmd.OFFERED_VALUES)


# ---------------------------------------------------------------------------
# REQ-d00282-D+H: a selection decides which facts, never which or what
# ---------------------------------------------------------------------------


class TestSelectingValuesChangesNothingElse:
    # Verifies: REQ-d00282-D
    @pytest.mark.parametrize("selection", (["id", "tested"], ["id", "title", "level", "tested"]))
    def test_a_figure_reads_the_same_however_few_values_were_asked_for(self, selection):
        graph = _requirement_graph()
        narrow = _trace_stated(graph, "json", selection)
        rows = json.loads("\n".join(trace_cmd.format_json(graph, None, None, selection, None)))
        assert "tested" in narrow
        # The breakdown qualifying it rides inside the same object; the FIGURE
        # is what a narrower selection may not move.
        figure = rows[0]["tested"]
        assert (figure["count"], figure["total"], figure["ratio"]) == (1.0, 2.0, 0.5)

    # Verifies: REQ-p00084-B
    def test_selecting_values_does_not_change_which_requirements_are_reported(
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


# ---------------------------------------------------------------------------
# REQ-d00282-B: a figure decomposes into the three scalars it was built from
# ---------------------------------------------------------------------------


def _thirds_graph() -> TraceGraph:
    """One requirement conferring three assertions with one of them credited.

    A third is deliberately not a round number: a proportion that survives the
    trip unrounded proves it was derived rather than parsed back out of a cell
    that had already lost the precision.
    """
    graph = TraceGraph()
    node = GraphNode("REQ-p00002", NodeKind.REQUIREMENT, label="Thirds")
    node.set_field("level", "prd")
    node.set_field("status", "Active")
    node.set_metric(
        "rollup_metrics",
        RollupMetrics(
            total_assertions=3,
            implemented=CoverageDimension(total=3, immediate_direct_by_label={"A": 1.0}),
            tested=CoverageDimension(total=3, immediate_indirect_by_label={"B": 1.0}),
        ),
    )
    graph._index[node.id] = node
    graph._roots.append(node)
    return graph


def _thirds_level() -> dict:
    """The same estate as a level row: one assertion credited out of three."""
    row = _level_row("PRD", 1, 3)
    row["implemented_total_covered"] = 1.0
    row["implemented_immediate_direct"] = 1.0
    row["tested_failed"] = 2
    return row


def _at(row: dict, path: str):
    """The object a value key names, reached by walking the path it spells.

    Written as a walk rather than a lookup because the shape under test IS the
    nesting: a row that flattened ``implemented.count`` into one key would
    satisfy a lookup by the flat name and fail here.
    """
    node = row
    for step in path.split("."):
        node = node[step]
    return node


def _trace_json(graph, values: list[str]) -> dict:
    return json.loads("\n".join(trace_cmd.format_json(graph, None, None, values, None)))[0]


def _summary_json(row: dict, values: list[str]) -> dict:
    payload = {"levels": [row], "excluded": {}, "integrations": [], "values": values}
    return json.loads(summary_cmd._render(payload, "json", None))["levels"][0]


class TestAFigureDecomposesIntoItsScalars:
    # Verifies: REQ-d00282-B
    @pytest.mark.parametrize("base", ("implemented", "implemented.immediate_direct"))
    def test_trace_states_the_credit_the_population_and_their_proportion(self, base):
        """Each in its own right, for a dimension's total as for a measure
        behind it. Selecting one states one -- the reader is not made to take
        three to reach the number they came for."""
        row = _trace_json(_thirds_graph(), [f"{base}.{p}" for p in ("count", "total", "ratio")])
        stated = _at(row, base)
        assert stated["count"] == 1.0
        assert stated["total"] == 3.0
        assert stated["ratio"] == 1 / 3

    # Verifies: REQ-d00282-B
    @pytest.mark.parametrize("base", ("implemented", "implemented.immediate_direct"))
    def test_summary_states_the_same_three_about_a_group(self, base):
        row = _summary_json(
            _thirds_level(), ["level"] + [f"{base}.{p}" for p in ("count", "total", "ratio")]
        )
        stated = _at(row, base)
        assert stated["count"] == 1.0
        assert stated["total"] == 3.0
        assert stated["ratio"] == 1 / 3

    # Verifies: REQ-d00282-B
    def test_selecting_one_scalar_states_that_scalar_alone(self):
        """The defect this ends: a reader wanting the credit had to take the
        composite and cut the other two back out of it."""
        row = _trace_json(_thirds_graph(), ["id", "implemented.count"])
        # The object mirrors the path the key spells, and holds nothing the
        # selection did not name.
        assert row == {"id": "REQ-p00002", "implemented": {"count": 1.0}}

    # Verifies: REQ-d00282-B
    def test_a_scalar_is_a_number_and_not_a_sentence_about_one(self):
        """The whole point: a program consuming this must not have to regex a
        number back out of prose."""
        row = _trace_json(_thirds_graph(), ["implemented.count", "implemented.ratio"])
        assert isinstance(row["implemented"]["count"], float)
        assert isinstance(row["implemented"]["ratio"], float)
        assert not isinstance(row["implemented"]["count"], str)

    # Verifies: REQ-d00282-B
    def test_the_proportion_is_not_rounded_into_the_value(self):
        """A proportion is derived from the other two rather than being a third
        fact, so a consumer re-deriving it must not disagree with one reading
        it. Rounded to the composite's precision this would be 0.33."""
        row = _trace_json(
            _thirds_graph(), ["implemented.count", "implemented.total", "implemented.ratio"]
        )
        figure = row["implemented"]
        assert figure["ratio"] == figure["count"] / figure["total"]
        assert repr(figure["ratio"]) == repr(1 / 3)

    # Verifies: REQ-d00282-B, REQ-p00084-C
    def test_a_table_may_round_the_proportion_the_value_carries_whole(self):
        """REQ-d00282-E binds which values are stated, never how each is
        spelled: a cell states a rounded proportion and the number stays the
        number."""
        rows = list(
            csv.reader(
                io.StringIO(
                    "\n".join(
                        trace_cmd.format_csv(
                            _thirds_graph(), None, None, ["id", "implemented.ratio"], None
                        )
                    )
                )
            )
        )
        assert rows[1] == ["REQ-p00002", "0.333"]
        stated = _trace_json(_thirds_graph(), ["implemented.ratio"])["implemented"]["ratio"]
        assert stated == 1 / 3

    # Verifies: REQ-d00282-B, REQ-d00282-D
    @pytest.mark.parametrize(
        "selection",
        (
            ["implemented", "implemented.count", "implemented.total"],
            ["implemented.count", "implemented", "implemented.total"],
            ["implemented.total", "implemented.count", "implemented"],
        ),
        ids=["figure-first", "figure-between", "figure-last"],
    )
    def test_naming_a_figure_and_a_part_of_it_names_one_place_twice(self, selection):
        """A value a report states equals the one a report stating everything
        states for the same row -- the composite and the scalars are one fact
        seen two ways, so they cannot be allowed to disagree.

        Naming both merges rather than duplicating or conflicting, whichever
        order they were named in: the figure's own object already holds the
        part (REQ-d00282-D)."""
        row = _trace_json(_thirds_graph(), selection)
        assert set(row) == {"implemented"}, row
        assert row["implemented"] == {"count": 1.0, "total": 3.0, "ratio": 1 / 3}


# ---------------------------------------------------------------------------
# REQ-d00258-O + REQ-d00282-B: some values are counts and nothing else
# ---------------------------------------------------------------------------


class TestCountsOnlyValues:
    # Verifies: REQ-d00258-O, REQ-d00282-B
    @pytest.mark.parametrize("part", ("passed", "failed", "awaiting"))
    def test_each_count_of_the_breakdown_is_selectable_on_its_own(self, part):
        """Though the three sum to the tested count, a reader wanting only the
        failures is owed only the failures."""
        row = _trace_json(_thirds_graph(), ["id", f"tested.{part}"])
        assert set(row) == {"id", "tested"}
        assert set(row["tested"]) == {part}
        assert isinstance(row["tested"][part], (int, float))

    # Verifies: REQ-d00258-O, REQ-d00282-B
    def test_the_summary_states_one_count_of_the_breakdown_alone(self):
        row = _summary_json(_thirds_level(), ["level", "tested.failed"])
        assert row == {"level": "PRD", "tested": {"failed": 2}}

    # Verifies: REQ-d00258-O, REQ-d00282-B+F
    @pytest.mark.parametrize("part", ("passed", "failed", "awaiting"))
    def test_a_count_has_no_proportion_to_ask_for(self, part):
        """A count of what came back is not a credit taken over a population,
        so there is nothing for a proportion to be OF -- and a name the report
        does not offer is refused rather than quietly dropped."""
        from elspais.graph.values import VALUE_SPECS

        assert f"tested.{part}" in VALUE_SPECS
        assert f"tested.{part}.ratio" not in VALUE_SPECS
        with pytest.raises(trace_cmd.UnofferedValues):
            summary_cmd._resolve_values_for(
                argparse.Namespace(values=f"tested.{part}.ratio", scope=None), None
            )
        message, code = trace_cmd.render_section(
            _thirds_graph(),
            argparse.Namespace(
                format="json",
                preset=None,
                scope=None,
                values=f"tested.{part}.ratio",
                dimension="",
                body=False,
                show_assertions=False,
                show_tests=False,
            ),
            None,
        )
        assert code == 1
        assert f"tested.{part}.ratio" in message

    # Verifies: REQ-d00258-O, REQ-d00282-B
    def test_only_the_tested_figure_carries_a_breakdown(self):
        """The breakdown is of what came back for a tested assertion. No other
        dimension has one, so no other dimension offers its counts."""
        from elspais.graph.values import VALUE_SPECS

        assert "implemented.failed" not in VALUE_SPECS
        assert "verified.passed" not in VALUE_SPECS


# ---------------------------------------------------------------------------
# REQ-d00282-E+M: a scalar is one value in every format, and absent is not zero
# ---------------------------------------------------------------------------


class TestScalarsStateOneValueSetInEveryFormat:
    # Verifies: REQ-p00084-C
    def test_trace_states_the_same_scalar_set_in_every_format(self):
        """Rendered as a number where the format has numbers and as text where
        it has cells -- the same values either way."""
        values = ["id", "implemented.count", "implemented.ratio", "tested.failed"]
        graph = _thirds_graph()
        stated = {fmt: _trace_stated(graph, fmt, values) for fmt in ("csv", "markdown", "html")}
        expected = [trace_cmd.header_for(c, None) for c in values]
        for fmt, cells in stated.items():
            assert cells == expected, f"{fmt} states {cells}"
        # The same four values, reached by the paths their keys spell rather
        # than by four columns: two of them share one figure's object.
        row = _trace_json(graph, values)
        assert list(row) == ["id", "implemented", "tested"]
        # One credited of three, a third of them, and nothing failing.
        assert [_at(row, v) for v in values[1:]] == [1.0, 1 / 3, 0]

    # Verifies: REQ-p00084-C
    def test_summary_states_the_same_scalar_set_in_every_format(self):
        values = ["level", "implemented.count", "implemented.ratio", "tested.failed"]
        payload = {
            "levels": [_thirds_level()],
            "excluded": {},
            "integrations": [],
            "values": values,
        }
        expected = [summary_cmd.header_for(c, None) for c in values]
        for fmt in ("csv", "markdown"):
            assert _summary_stated(payload, fmt) == expected, fmt
        assert _summary_stated(payload, "json") == ["level", "implemented", "tested"]
        row = json.loads(summary_cmd._render(dict(payload), "json", None))["levels"][0]
        assert [_at(row, v) for v in values[1:]] == [1.0, 1 / 3, 2]
        # The text rendering states them too: a selection that meant one thing
        # on screen and another in the filed artifact is the divergence E ends.
        text = summary_cmd._render(dict(payload), "text", None)
        for value in values[1:]:
            assert summary_cmd.header_for(value, None) in text, value

    # Verifies: REQ-d00282-M
    @pytest.mark.parametrize("part", ("count", "total", "ratio"))
    def test_a_group_owed_no_coverage_states_no_scalar_either(self, coverage_payload, part):
        """Including the population: stating 0 assertions counted over would be
        a figure where there is none, which is the confusion M forbids."""
        values = ["level", f"implemented.{part}"]
        levels = {
            lv["level"]: lv
            for lv in json.loads(
                summary_cmd._render({**coverage_payload, "values": values}, "json", None)
            )["levels"]
        }
        assert levels["OPS"]["implemented"][part] is None
        # PRD confers four assertions and nothing covers them: a real zero
        # credited, over a real population of four.
        assert (
            levels["PRD"]["implemented"][part] == {"count": 0.0, "total": 4.0, "ratio": 0.0}[part]
        )

    # Verifies: REQ-d00282-M
    def test_a_cell_with_no_scalar_to_state_is_not_a_zero(self, coverage_payload):
        payload = {**coverage_payload, "values": ["level", "implemented.count"]}
        out = summary_cmd._render(payload, "csv", None)
        rows = {r[0]: r[1] for r in csv.reader(io.StringIO(out)) if r}
        assert rows["PRD"] == "0"
        assert rows["OPS"] == summary_cmd.ABSENT_FIGURE


# ---------------------------------------------------------------------------
# REQ-d00282-G: offering a further value moves nothing already expressible
# ---------------------------------------------------------------------------


class TestOfferingAValueMovesNothing:
    # Verifies: REQ-d00282-A
    def test_the_composite_states_what_it_always_stated(self):
        """`--values implemented` is the selection projects committed before
        the scalars existed, and it still states the one composite cell it did
        -- and, where the format has numbers, exactly the three numbers that
        cell was made from and nothing further."""
        cells = list(
            csv.reader(
                io.StringIO(
                    "\n".join(
                        trace_cmd.format_csv(
                            _thirds_graph(), None, None, ["id", "implemented"], None
                        )
                    )
                )
            )
        )
        assert cells[1] == ["REQ-p00002", "1/3 (33%)"]
        row = _trace_json(_thirds_graph(), ["id", "implemented"])
        assert row == {
            "id": "REQ-p00002",
            "implemented": {"count": 1.0, "total": 3.0, "ratio": 1 / 3},
        }

    # Verifies: REQ-d00282-A
    def test_a_report_asked_for_nothing_is_not_handed_the_new_values(self):
        """A default set may grow; one that swept in every value offered would
        move what an unselected report states each time one was added."""
        assert set(summary_cmd.DEFAULT_VALUES) < set(summary_cmd.OFFERED_VALUES)
        assert not [k for k in summary_cmd.DEFAULT_VALUES if k.endswith((".count", ".ratio"))]
        assert "implemented.count" in summary_cmd.OFFERED_VALUES

    # Verifies: REQ-d00282-A
    def test_the_named_default_sets_state_composites(self):
        for preset in trace_cmd.REPORT_PRESETS.values():
            assert not [c for c in preset.values if "." in c], preset.name


# ---------------------------------------------------------------------------
# REQ-d00282-B+E: the shape a structured format states a selection in
# ---------------------------------------------------------------------------


def _paths(obj: dict, prefix: str = "") -> list[str]:
    """Every leaf of a row, named by the path that reaches it.

    The nesting IS the property under test, so a row is read by walking it
    rather than by looking a flat key up: a report that spelled
    ``implemented.count`` as one key would pass a lookup and fail here.
    """
    found: list[str] = []
    for key, value in obj.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            found.extend(_paths(value, f"{path}."))
        else:
            found.append(path)
    return sorted(found)


class TestAValueIsStatedAtThePathItsKeySpells:
    # Verifies: REQ-d00282-B, REQ-p00084-C
    @pytest.mark.parametrize(
        "selection,expected",
        (
            ("implemented", ["implemented.count", "implemented.ratio", "implemented.total"]),
            (
                "tested.immediate_direct",
                [
                    "tested.immediate_direct.count",
                    "tested.immediate_direct.ratio",
                    "tested.immediate_direct.total",
                ],
            ),
            ("tested.immediate_direct.count", ["tested.immediate_direct.count"]),
            ("implemented.ratio", ["implemented.ratio"]),
        ),
        ids=["figure", "measure", "measure-part", "figure-part"],
    )
    def test_the_object_mirrors_the_key_a_reader_selected_by(self, selection, expected):
        """A selection key is a path -- dimension, then measure, then part --
        and the object nests exactly as deep as the key does. A consumer
        reaching a number therefore holds the same string the reader wrote to
        select it, rather than a flattened spelling it has to translate."""
        row = _trace_json(_thirds_graph(), [selection])
        assert _paths(row) == expected

    # Verifies: REQ-d00282-B, REQ-d00069-L
    def test_a_measure_of_a_measure_is_not_offered(self):
        """The path bottoms out at a scalar: there is nothing beneath a number
        to decompose, so the report refuses the name rather than nesting a
        fourth level nothing computes."""
        from elspais.graph.values import VALUE_SPECS

        assert "tested.immediate_direct.count" in VALUE_SPECS
        assert "tested.immediate_direct.count.ratio" not in VALUE_SPECS

    # Verifies: REQ-d00258-O, REQ-d00282-B, REQ-p00084-C
    def test_the_tested_figure_carries_its_breakdown_and_a_measure_of_it_does_not(self):
        """The counts are what came back for the tested assertions OVERALL, so
        they qualify the dimension's own figure. A measure of Tested counts a
        kind of evidence, not a verdict, and carrying the breakdown there would
        attribute the three counts to one measure of the four."""
        row = _trace_json(_thirds_graph(), ["tested", "tested.immediate_direct"])
        assert set(row["tested"]) == {
            "count",
            "total",
            "ratio",
            "passed",
            "failed",
            "awaiting",
            "immediate_direct",
        }
        assert set(row["tested"]["immediate_direct"]) == {"count", "total", "ratio"}

    # Verifies: REQ-p00084-C
    @pytest.mark.parametrize(
        "selection",
        (
            ["implemented"],
            ["tested"],
            ["implemented.immediate_direct"],
            ["implemented", "implemented.count", "tested.failed"],
        ),
        ids=["figure", "figure-with-breakdown", "measure", "mixed"],
    )
    def test_trace_and_summary_state_one_selection_the_same_way(self, selection):
        """Two reports over two populations, one vocabulary: the per-
        requirement report and the group report state the same selection under
        the same paths. They used to disagree -- ``implemented_count`` from one
        and ``implemented.count`` from the other -- and a consumer could not
        read both."""
        req_row = _trace_json(_thirds_graph(), selection)
        level_row = _summary_json(_thirds_level(), ["level", *selection])
        level_row.pop("level")
        assert _paths(req_row) == _paths(level_row)

    # Verifies: REQ-d00254-I, REQ-d00282-D
    def test_a_figure_states_inside_itself_only_what_that_report_offers(self):
        """The provenance bit rides inside the Passing figure of the report
        that offers it and nowhere else. A group has no such bit -- an `or`
        over a level would answer a different question under the same name --
        so the group report's Passing figure does not carry one."""
        req_row = _selective_rows(["id", "verified"])[_GENUINE_ZERO]
        level_row = _summary_json(_thirds_level(), ["level", "verified"])
        assert "carried" in req_row["verified"]
        assert "carried" not in level_row["verified"]
        assert "verified.carried" in trace_cmd.OFFERED_VALUES
        assert "verified.carried" not in summary_cmd.OFFERED_VALUES


# ---------------------------------------------------------------------------
# REQ-d00254-J + REQ-d00282-M: a figure never taken is not a figure of zero
# ---------------------------------------------------------------------------

_NOT_RUN = "REQ-p00020"
_GENUINE_ZERO = "REQ-p00021"


def _selective_graph(carried: bool = False) -> TraceGraph:
    """A selective run holding both kinds of empty Passing figure.

    Both requirements declare tests and neither has a passing assertion. The
    first one's target was SKIPPED -- its tests produced no RESULT at all, so
    the run has nothing to say about it. The second one's target RAN and
    credited nothing, which is an answer. Built in one graph so the two are
    read the same way and can only differ in what they state.

    ``carried`` is the provenance of the verdict that WAS taken: a run whose
    result came from a baseline rather than from this run (REQ-d00254-I).
    """
    from elspais.graph.relations import EdgeKind

    graph = TraceGraph()
    for req_id, ran in ((_NOT_RUN, False), (_GENUINE_ZERO, True)):
        node = GraphNode(req_id, NodeKind.REQUIREMENT, label="Selective")
        node.set_field("level", "prd")
        node.set_field("status", "Active")
        node.set_metric(
            "rollup_metrics",
            RollupMetrics(
                total_assertions=2,
                verified=CoverageDimension(total=2, carried=carried and ran),
            ),
        )
        test = GraphNode(f"test:/tmp/t_{req_id}.py::test_it", NodeKind.TEST, label="test_it")
        node.link(test, EdgeKind.VERIFIES)
        if ran:
            test.link(GraphNode(f"result:{req_id}", NodeKind.RESULT, label="r"), EdgeKind.CONTAINS)
        graph._index[node.id] = node
        graph._roots.append(node)
    # What makes the run SELECTIVE: a fresh set was named, so a target outside
    # it was not re-run (REQ-d00254-I).
    graph.render_fresh_targets = {"only-this-one"}
    return graph


def _selective_rows(values: list[str], carried: bool = False) -> dict[str, dict]:
    rows = json.loads(
        "\n".join(trace_cmd.format_json(_selective_graph(carried), None, None, values, None))
    )
    return {row["id"]: row for row in rows}


class TestAFigureNeverTakenIsNotAFigureOfZero:
    # Verifies: REQ-d00254-J, REQ-d00282-M
    @pytest.mark.parametrize("part", ("count", "total", "ratio"))
    def test_the_scalars_say_the_same_thing_the_cell_says(self, part):
        """The defect this ends: the cell read "not run" while the numbers
        beneath it read a flat 0, so a reader who selected the number was told
        work had FAILED that was never attempted.

        Both cases are read in the same assertion because the distinction is
        the subject: an absence must be null where a real zero is 0.0."""
        whole = _selective_rows(["id", "verified"])
        assert whole[_NOT_RUN]["verified"] is None, "an absence is null, not an object of nulls"
        assert whole[_GENUINE_ZERO]["verified"]["count"] == 0.0

        scalars = _selective_rows(["id", f"verified.{part}"])
        assert scalars[_NOT_RUN]["verified"][part] is None
        assert (
            scalars[_GENUINE_ZERO]["verified"][part]
            == {
                "count": 0.0,
                "total": 2.0,
                "ratio": 0.0,
            }[part]
        )

    # Verifies: REQ-d00254-J, REQ-d00282-M, REQ-p00084-C
    def test_the_table_cell_says_it_too(self):
        """One distinction, both formats: the read format marks the absence
        and the machine format nulls it, and neither prints a zero."""
        cells = {
            row[0]: row[1:]
            for row in csv.reader(
                io.StringIO(
                    "\n".join(
                        trace_cmd.format_csv(
                            _selective_graph(),
                            None,
                            None,
                            ["id", "verified", "verified.count"],
                            None,
                        )
                    )
                )
            )
        }
        assert cells[_NOT_RUN] == [trace_cmd.NOT_RUN_FIGURE, trace_cmd.ABSENT_FIGURE]
        assert cells[_GENUINE_ZERO] == ["0/2 (0%)", "0"]


# ---------------------------------------------------------------------------
# REQ-d00254-I + REQ-d00282-B+E: the provenance bit is a value of its own
# ---------------------------------------------------------------------------


class TestTheProvenanceBitIsSelectable:
    # Verifies: REQ-d00254-I, REQ-d00282-B, REQ-p00084-C
    def test_a_bit_is_a_word_in_a_table_and_a_boolean_in_a_format_that_has_one(self):
        """A bit is a state rather than a quantity, so a table states the word
        for the state and JSON states the boolean -- and where no verdict was
        taken there is no provenance to claim either, which is null rather than
        "fresh"."""
        rows = _selective_rows(["id", "verified.carried"], carried=True)
        assert rows[_GENUINE_ZERO]["verified"]["carried"] is True
        assert rows[_NOT_RUN]["verified"]["carried"] is None

        cells = {
            row[0]: row[1]
            for row in csv.reader(
                io.StringIO(
                    "\n".join(
                        trace_cmd.format_csv(
                            _selective_graph(carried=True),
                            None,
                            None,
                            ["id", "verified.carried"],
                            None,
                        )
                    )
                )
            )
        }
        assert cells[_GENUINE_ZERO] == "baseline"
        assert cells[_NOT_RUN] == trace_cmd.ABSENT_FIGURE

    # Verifies: REQ-d00254-I, REQ-p00084-C
    def test_a_fresh_verdict_reads_fresh(self):
        """The other state of the same bit, so the word is not a constant."""
        from elspais.graph.values import flag_cell

        assert (flag_cell(True), flag_cell(False)) == ("baseline", "fresh")
        rows = _selective_rows(["id", "verified.carried"], carried=False)
        assert rows[_GENUINE_ZERO]["verified"]["carried"] is False
        cells = {
            row[0]: row[1]
            for row in csv.reader(
                io.StringIO(
                    "\n".join(
                        trace_cmd.format_csv(
                            _selective_graph(carried=False),
                            None,
                            None,
                            ["id", "verified.carried"],
                            None,
                        )
                    )
                )
            )
        }
        assert cells[_GENUINE_ZERO] == "fresh"

    # Verifies: REQ-d00254-I, REQ-d00282-A+F
    def test_the_group_report_refuses_a_bit_it_cannot_state(self, tmp_path):
        """A level is a group of requirements, and an `or` over their bits
        would answer a different question under the same name. Refused rather
        than answered wrongly (REQ-d00282-F)."""
        from elspais.graph.values import UnofferedValues

        with pytest.raises(UnofferedValues):
            summary_cmd._resolve_values_for(
                argparse.Namespace(values="verified.carried", scope=None), None
            )
        out = tmp_path / "report.txt"
        code = report_cmd.run(["summary"], ["--values", "verified.carried", "-o", str(out)])
        assert code != 0
        assert not out.exists()


# ---------------------------------------------------------------------------
# REQ-d00282-B+E: a proportion is derived, and only a rendering rounds it
# ---------------------------------------------------------------------------


def _sevenths_graph() -> TraceGraph:
    """Three assertions credited of seven -- a proportion no rounding survives."""
    graph = TraceGraph()
    node = GraphNode("REQ-p00003", NodeKind.REQUIREMENT, label="Sevenths")
    node.set_field("level", "prd")
    node.set_field("status", "Active")
    node.set_metric(
        "rollup_metrics",
        RollupMetrics(
            total_assertions=7,
            implemented=CoverageDimension(
                total=7, immediate_direct_by_label={"A": 1.0, "B": 1.0, "C": 1.0}
            ),
        ),
    )
    graph._index[node.id] = node
    graph._roots.append(node)
    return graph


def _sevenths_level() -> dict:
    row = _level_row("PRD", 1, 7)
    row["implemented_total_covered"] = 3.0
    row["implemented_immediate_direct"] = 3.0
    return row


class TestAProportionSurvivesTheTrip:
    # Verifies: REQ-d00282-B, REQ-p00084-C
    def test_the_number_is_whole_and_the_cell_is_rounded(self):
        """Three of seven is not a number a cell can hold. Rounded into the
        value, a consumer re-deriving the proportion from the credit and the
        population would disagree with one that read it."""
        row = _trace_json(_sevenths_graph(), ["implemented"])
        assert row["implemented"]["ratio"] == 3 / 7
        assert repr(row["implemented"]["ratio"]) == "0.42857142857142855"
        assert row["implemented"]["ratio"] != round(3 / 7, 3)

        cell = list(
            csv.reader(
                io.StringIO(
                    "\n".join(
                        trace_cmd.format_csv(
                            _sevenths_graph(), None, None, ["implemented.ratio"], None
                        )
                    )
                )
            )
        )[1]
        assert cell == ["0.429"]

    # Verifies: REQ-d00282-B, REQ-p00084-C
    def test_the_group_report_carries_it_whole_too(self):
        """The same number over a group: one vocabulary, one precision."""
        row = _summary_json(_sevenths_level(), ["level", "implemented"])
        assert repr(row["implemented"]["ratio"]) == "0.42857142857142855"
        assert (
            row["implemented"]["count"] / row["implemented"]["total"]
            == (row["implemented"]["ratio"])
        )


# ---------------------------------------------------------------------------
# REQ-d00280-C: one declared name carries both halves of what an audience reads
# ---------------------------------------------------------------------------


class TestADeclaredScopeCarriesItsValues:
    # Verifies: REQ-d00280-C, REQ-d00282-A
    def test_a_report_run_under_a_declared_name_states_the_values_it_names(self):
        """A selection spelled at the moment a report is run is known only to
        whoever spelled it; declared beside the requirements it selects over it
        is versioned with them."""
        from elspais.commands._values import resolve_report_values

        config = {"scopes": {"Overview": {"level": ["prd"], "values": ["tested", "implemented"]}}}
        stated = resolve_report_values(
            argparse.Namespace(values=None, scope="overview"),
            summary_cmd.OFFERED_VALUES,
            summary_cmd.DEFAULT_VALUES,
            config,
            identity_key=summary_cmd.IDENTITY_VALUE,
        )
        # Read case-insensitively, in the order declared, under the identity
        # value the report keeps whatever was named (REQ-d00282-K+L).
        assert stated == ("level", "tested", "implemented")

    # Verifies: REQ-d00280-C
    def test_a_declaration_naming_no_values_constrains_none(self):
        """The two halves stay independent: a scope that selects requirements
        and names no facts leaves the report stating the facts it would have."""
        from elspais.commands._values import resolve_report_values

        config = {"scopes": {"overview": {"level": ["prd"]}}}
        stated = resolve_report_values(
            argparse.Namespace(values=None, scope="overview"),
            summary_cmd.OFFERED_VALUES,
            summary_cmd.DEFAULT_VALUES,
            config,
        )
        assert stated == tuple(summary_cmd.DEFAULT_VALUES)

    # Verifies: REQ-d00280-C, REQ-d00282-J
    def test_the_declaration_is_written_in_value_keys(self):
        """The schema knows one name for the facts a scope states. A project
        writing the retired one is told so rather than having the declaration
        silently ignored."""
        import pydantic

        from elspais.config.schema import ReportScopeConfig

        assert ReportScopeConfig(values=["tested"]).values == ["tested"]
        with pytest.raises(pydantic.ValidationError):
            ReportScopeConfig(columns=["tested"])


# ---------------------------------------------------------------------------
# REQ-d00282-N: a figure measured in lines decomposes too
# ---------------------------------------------------------------------------


def _lines_graph(
    *, total: int = 20, covered: float = 16.0, attributed: float = 4.0, **bits: bool
) -> TraceGraph:
    """One requirement whose implementation is measured in LINES.

    Sixteen of twenty is deliberately not a round proportion of the assertion
    counts elsewhere in this file: a line figure is counted over lines, and a
    report that leaned on the assertion count for its denominator would be
    caught by the arithmetic rather than by inspection.
    """
    graph = TraceGraph()
    node = GraphNode("REQ-p00003", NodeKind.REQUIREMENT, label="Lines")
    node.set_field("level", "prd")
    node.set_field("status", "Active")
    node.set_metric(
        "rollup_metrics",
        RollupMetrics(
            total_assertions=2,
            implemented=CoverageDimension(total=2, immediate_direct_by_label={"A": 1.0}),
            code_tested=LineCoverage(
                total_lines=total,
                covered_lines=covered,
                attributed_lines=attributed,
                has_measurement=bits.get("has_measurement", True),
                has_contexts=bits.get("has_contexts", True),
            ),
        ),
    )
    graph._index[node.id] = node
    graph._roots.append(node)
    return graph


def _lines_level(
    *, total: int = 20, covered: float = 16.0, attributed: float = 4.0, **bits: bool
) -> dict:
    """The same estate as a level row, so both reports answer from one shape."""
    row = _level_row("PRD", 1, 2)
    row["implemented_total_covered"] = 1.0
    row["code_tested_total"] = total
    row["code_tested_covered"] = covered
    row["code_tested_attributed"] = attributed
    row["code_tested_measured"] = bits.get("has_measurement", True)
    row["code_tested_has_contexts"] = bits.get("has_contexts", True)
    return row


LINE_PARTS = ("code_tested.count", "code_tested.total", "code_tested.ratio")


class TestALineFigureDecomposesIntoItsLines:
    # Verifies: REQ-d00282-N
    @pytest.mark.parametrize(
        "path,expected",
        (
            ("code_tested.count", 16.0),
            ("code_tested.total", 20.0),
            ("code_tested.ratio", 0.8),
            ("code_tested.attributed", 4.0),
        ),
    )
    def test_each_part_of_the_line_figure_is_selectable_alone(self, path, expected):
        """The lines covered, the lines measured and their proportion, each in
        its own right -- and the attribution as the further reading it is."""
        assert _at(_trace_json(_lines_graph(), [path]), path) == expected
        assert _at(_summary_json(_lines_level(), [path]), path) == expected

    # Verifies: REQ-d00282-C+N
    def test_the_bare_value_states_the_lines_covered_not_the_attribution(self):
        """A value named for the figure states the figure.

        The attribution is one reading of those lines and has its own name; a
        bare value that silently stated it would be the naming defect
        REQ-d00282-C exists to prevent -- and, since attribution is suppressed
        far more often than measurement is, it read as "no line coverage" for
        an estate with plenty.
        """
        graph = _lines_graph(covered=16.0, attributed=4.0)
        figure = _at(_trace_json(graph, ["code_tested"]), "code_tested")
        assert figure["count"] == 16.0
        assert figure["attributed"] == 4.0

        preset = trace_cmd.ReportPreset(name="p", values=["code_tested"])
        rows = list(trace_cmd.format_csv(graph, preset, None, ["code_tested"], None))
        body = list(csv.reader(io.StringIO("\n".join(rows))))[1]
        # The lines covered, not the four a verifying test could be named for.
        assert body[0].startswith("16/20")

    # Verifies: REQ-d00282-N, REQ-d00069-M
    def test_the_line_proportion_is_counted_over_lines_not_assertions(self):
        """A line figure carries its own population. Sharing the assertion
        count would make the proportion a ratio of two different things."""
        row = _summary_json(_lines_level(total=20, covered=16.0), ["code_tested"])
        assert row["code_tested"]["total"] == 20.0  # not the 2 assertions
        assert row["code_tested"]["ratio"] == 0.8

    # Verifies: REQ-d00282-N, REQ-p00084-C
    @pytest.mark.parametrize("fmt", ("csv", "markdown"))
    def test_a_table_states_one_cell_per_line_value(self, fmt):
        """One named value is one value wherever it is stated: the figure is a
        cell, each part is a cell, and neither format states more than the
        other."""
        values = ["code_tested", *LINE_PARTS, "code_tested.attributed"]
        stated = _trace_stated(_lines_graph(), fmt, values)
        assert len(stated) == len(values)


class TestMeasuredLinesSurviveTheAttributionSuppression:
    """REQ-d00258-E suppresses the attribution; it must take nothing with it.

    This is the boundary the defect lived on, so it is checked by MOVING it:
    one estate, rendered twice, differing only in whether the tooling recorded
    per-test contexts.
    """

    # Verifies: REQ-d00258-E, REQ-d00282-M+N
    def test_without_contexts_the_lines_are_stated_and_only_attribution_is_absent(self):
        row = _trace_json(_lines_graph(has_contexts=False, attributed=0.0), ["code_tested"])
        assert row["code_tested"]["count"] == 16.0
        assert row["code_tested"]["total"] == 20.0
        assert row["code_tested"]["ratio"] == 0.8
        assert row["code_tested"]["attributed"] is None

    # Verifies: REQ-d00258-E, REQ-d00282-M+N
    def test_flipping_the_context_bit_moves_the_attribution_and_nothing_else(self):
        """The falsifiable half: with contexts a zero attribution is STATED as
        zero, without them it is absent, and the three line values are byte
        identical across the two.

        A report that suppressed the figure along with the attribution would
        differ in all four; a report that never suppressed anything would
        differ in none.
        """
        values = ["code_tested", *LINE_PARTS, "code_tested.attributed"]
        with_ctx = _trace_json(_lines_graph(has_contexts=True, attributed=0.0), values)
        without = _trace_json(_lines_graph(has_contexts=False, attributed=0.0), values)

        assert _at(with_ctx, "code_tested.attributed") == 0.0
        assert _at(without, "code_tested.attributed") is None
        for path in LINE_PARTS:
            assert _at(with_ctx, path) == _at(without, path)

    # Verifies: REQ-d00258-E, REQ-d00282-M+N
    def test_summary_suppresses_the_attribution_on_the_same_terms(self):
        values = ["code_tested", *LINE_PARTS, "code_tested.attributed"]
        with_ctx = _summary_json(_lines_level(has_contexts=True, attributed=0.0), values)
        without = _summary_json(_lines_level(has_contexts=False, attributed=0.0), values)

        assert _at(with_ctx, "code_tested.attributed") == 0.0
        assert _at(without, "code_tested.attributed") is None
        for path in LINE_PARTS:
            assert _at(with_ctx, path) == _at(without, path)


class TestNoMeasurementIsAbsentNotZero:
    """A run that never happened and a run that reached nothing are different
    facts, and the line total cannot tell them apart on its own: it is derived
    from the `Implements:` lines, so it stands whether or not anything ran.
    """

    # Verifies: REQ-d00282-M+N, REQ-d00254-B
    @pytest.mark.parametrize("path", ("code_tested", *LINE_PARTS, "code_tested.attributed"))
    def test_an_unmeasured_estate_states_no_line_value_at_all(self, path):
        graph = _lines_graph(has_measurement=False, has_contexts=False, covered=0.0, attributed=0.0)
        assert _at(_trace_json(graph, [path]), path) is None
        level = _lines_level(has_measurement=False, has_contexts=False, covered=0.0, attributed=0.0)
        assert _at(_summary_json(level, [path]), path) is None

    # Verifies: REQ-d00282-M+N
    def test_a_measured_estate_reaching_no_line_states_a_real_zero(self):
        """The opposite polarity, and the reason the bit is read rather than
        the count: a run that reached nothing is a finding, not an absence."""
        graph = _lines_graph(has_measurement=True, has_contexts=True, covered=0.0, attributed=0.0)
        figure = _at(_trace_json(graph, ["code_tested"]), "code_tested")
        assert figure["count"] == 0.0
        assert figure["total"] == 20.0
        assert figure["ratio"] == 0.0

    # Verifies: REQ-d00282-M+N
    @pytest.mark.parametrize("fmt", ("csv", "markdown"))
    def test_a_table_marks_an_unstated_line_value_rather_than_printing_zero(self, fmt):
        graph = _lines_graph(has_measurement=False, has_contexts=False, covered=0.0, attributed=0.0)
        preset = trace_cmd.ReportPreset(name="p", values=["code_tested"])
        formatter = {"csv": trace_cmd.format_csv, "markdown": trace_cmd.format_markdown}[fmt]
        out = "\n".join(formatter(graph, preset, None, ["code_tested", *LINE_PARTS], None))
        assert "0/20" not in out
        assert trace_cmd.ABSENT_FIGURE in out


class TestTraceAndSummaryAnswerTheLineQuestionAlike:
    # Verifies: REQ-d00282-N, REQ-d00258-C
    def test_both_reports_offer_the_line_figure_and_its_parts(self):
        wanted = {"code_tested", *LINE_PARTS, "code_tested.attributed"}
        assert wanted <= set(trace_cmd.OFFERED_VALUES)
        assert wanted <= set(summary_cmd.OFFERED_VALUES)

    # Verifies: REQ-d00282-D+N
    def test_one_estate_states_one_line_figure_through_either_report(self):
        """The same lines, asked of a requirement and of the group holding it,
        arrive as the same numbers under the same path."""
        values = ["code_tested", *LINE_PARTS, "code_tested.attributed"]
        from_trace = _at(_trace_json(_lines_graph(), values), "code_tested")
        from_summary = _at(_summary_json(_lines_level(), values), "code_tested")
        assert from_trace == from_summary

    # Verifies: REQ-d00282-C+J
    def test_the_line_values_are_headed_in_the_words_of_lines(self):
        """A key is one grammar and a display word is another: `.count` is the
        credit of whatever figure it sits beneath, and beneath a line figure
        the credit is a line."""
        from elspais.graph.values import header_for

        assert header_for("code_tested.count") == "Code Tested (lines covered)"
        assert header_for("code_tested.total") == "Code Tested (lines measured)"
        assert header_for("code_tested.attributed") == "Code Tested (lines attributed)"
        # The *Assertion*-counted figures keep their own words.
        assert header_for("implemented.count") == "Implemented (credited)"


class TestLcovTestedIsCountedInAssertions:
    """REQ-d00254-B credits *Assertions* from line evidence, so `lcov_tested`
    is a coverage dimension whose EVIDENCE is lines -- not a line figure. It
    decomposes over assertions and REQ-d00282-N does not reach it.
    """

    # Verifies: REQ-d00254-B, REQ-d00282-B
    def test_lcov_tested_decomposes_over_assertions(self):
        from elspais.graph.values import LINE_DIMENSIONS

        assert "lcov_tested" not in LINE_DIMENSIONS
        graph = _lines_graph()
        rollup = graph.find_by_id("REQ-p00003").get_metric("rollup_metrics")
        rollup.lcov_tested = CoverageDimension(total=2, immediate_direct_by_label={"A": 1.0})
        figure = _at(_trace_json(graph, ["lcov_tested"]), "lcov_tested")
        assert figure == {"count": 1.0, "total": 2.0, "ratio": 0.5}

    # Verifies: REQ-d00254-B, REQ-d00282-F
    def test_lcov_tested_offers_no_line_reading(self):
        """It counts no lines, so it has no attribution to name and asking for
        one is refused like any other name the report does not offer."""
        assert "lcov_tested.attributed" not in set(trace_cmd.OFFERED_VALUES)


class TestALineFigureSurvivesAnAssertionLessGroup:
    """A whole-requirement `Implements:` attributes code to a requirement that
    confers no *Assertion*, so a level can hold lines and no assertions. The
    two figures are counted over different populations, and the absence of one
    is not the absence of the other.
    """

    # Verifies: REQ-d00282-M+N, REQ-p00084-C
    @pytest.mark.parametrize("fmt", ("text", "csv", "markdown", "json"))
    def test_every_format_states_the_lines_of_a_group_with_no_assertions(self, fmt):
        row = _lines_level()
        row["total_assertions"] = 0
        payload = {
            "levels": [row],
            "excluded": {},
            "integrations": [],
            "values": ["level", "code_tested"],
        }
        out = summary_cmd._render(dict(payload), fmt, None)
        if fmt == "json":
            assert json.loads(out)["levels"][0]["code_tested"]["count"] == 16.0
        else:
            assert "16/20" in out

    # Verifies: REQ-d00282-M
    def test_the_assertion_figures_of_that_group_are_still_absent(self):
        row = _lines_level()
        row["total_assertions"] = 0
        stated = _summary_json(row, ["implemented", "code_tested"])
        assert stated["implemented"] is None
        assert stated["code_tested"]["count"] == 16.0
