# Validates REQ-p00084-C, REQ-p00084-D
"""A scoped report artifact carries its own scope disclosure.

REQ-p00084-D obliges a scoped report to declare the scope that produced it, and
the artifact a reader files is the report -- not the terminal the reader closed.
These tests pin the disclosure to the rendered document on every surface that
honours a scope (trace in each of its formats, the foundation analysis, the
coverage summary) and, at the same time, to *stdout rather than stderr*: the
defect they answer was a stream split, in which the table went to the file and
the disclosure to the terminal, so a rendering carrying the lines somewhere is
not enough. REQ-p00084-C is the other half: the requirements a report presents
do not depend on the format it is rendered in, and neither does the disclosure
stating which requirements those are.
"""

from __future__ import annotations

import argparse
import csv
import io
import json

import pytest
import tyro

from elspais.cli import _to_namespace
from elspais.commands import analysis_cmd, summary, trace
from elspais.commands._scope import (
    resolve_scope_for_report,
    scope_disclosure,
    scope_from_args,
    scope_params_from_args,
)
from elspais.commands.args import GlobalArgs
from elspais.commands.report import parse_shared_args
from elspais.commands.trace import REPORT_PRESETS, ReportPreset

TABLE_FORMATS = ["markdown", "text", "csv", "html"]


def _scope_args(**overrides) -> argparse.Namespace:
    """An invocation asking for one level of the estate."""
    fields = {
        "level": ["prd"],
        "not_level": None,
        "status": None,
        "not_status": None,
        "match_status_roles": False,
        "scope": None,
    }
    fields.update(overrides)
    return argparse.Namespace(**fields)


@pytest.fixture(scope="module")
def scoped(canonical_federated_graph, canonical_config):
    """The membership and the disclosure a level-scoped report is produced under."""
    result = resolve_scope_for_report(canonical_federated_graph, _scope_args(), canonical_config)
    lines = scope_disclosure(result)
    assert lines, "the fixture must actually narrow something for these tests to mean anything"
    ids = None if len(result.ids) == result.population else result.ids
    assert ids is not None, "a scope selecting the whole estate discloses nothing"
    return ids, lines


@pytest.fixture(scope="module")
def scope_params(canonical_config) -> dict:
    """The same scope, in the shape a serving process is handed it."""
    return scope_params_from_args(_scope_args(), canonical_config)


@pytest.fixture(scope="module")
def standard_preset() -> ReportPreset:
    return ReportPreset(name="standard", values=list(REPORT_PRESETS["standard"].values))


def _render(graph, fmt, preset, scoped_pair, config) -> str:
    ids, lines = scoped_pair
    return "\n".join(
        trace.format_json(graph, preset, ids, None, config, lines)
        if fmt == "json"
        else {
            "markdown": trace.format_markdown,
            "text": trace.format_markdown,
            "csv": trace.format_csv,
            "html": trace.format_html,
        }[fmt](graph, preset, ids, None, config, lines)
    )


class TestTraceRenderingCarriesTheScope:
    """Every format the trace report renders in states the scope inside itself."""

    # Verifies: REQ-p00084-D
    @pytest.mark.parametrize("fmt", [*TABLE_FORMATS, "json"])
    def test_every_format_states_the_scope(
        self, canonical_federated_graph, canonical_config, standard_preset, scoped, fmt
    ):
        out = _render(canonical_federated_graph, fmt, standard_preset, scoped, canonical_config)
        for line in scoped[1]:
            assert line in out, f"{fmt} rendering does not state {line!r}"

    # Verifies: REQ-p00084-C
    def test_the_disclosure_does_not_depend_on_the_format(
        self, canonical_federated_graph, canonical_config, standard_preset, scoped
    ):
        """One report, five renderings, and the same statement about its scope.

        A rendering that stated a different selection -- or none -- would be a
        report a reader could not compare against the one they checked.
        """
        rendered = {
            fmt: _render(canonical_federated_graph, fmt, standard_preset, scoped, canonical_config)
            for fmt in [*TABLE_FORMATS, "json"]
        }
        for fmt, out in rendered.items():
            missing = [line for line in scoped[1] if line not in out]
            assert not missing, f"{fmt} omits {missing}"

    # Verifies: REQ-p00084-C
    def test_every_format_presents_the_same_requirements(
        self, canonical_federated_graph, canonical_config, standard_preset, scoped
    ):
        """The rows themselves, checked alongside the disclosure describing them."""
        ids, _lines = scoped
        json_out = json.loads(
            _render(canonical_federated_graph, "json", standard_preset, scoped, canonical_config)
        )
        from_json = {node["id"] for node in json_out["nodes"]}
        assert from_json == set(ids)

        csv_rows = list(
            csv.reader(
                io.StringIO(
                    _render(
                        canonical_federated_graph,
                        "csv",
                        standard_preset,
                        scoped,
                        canonical_config,
                    )
                )
            )
        )
        header_at = next(i for i, row in enumerate(csv_rows) if row and row[0] == "ID")
        from_csv = {row[0] for row in csv_rows[header_at + 1 :] if row}
        assert from_csv == set(ids)

        markdown = _render(
            canonical_federated_graph, "markdown", standard_preset, scoped, canonical_config
        )
        from_markdown = {
            line.split("|")[1].strip()
            for line in markdown.splitlines()
            if line.startswith("| REQ-")
        }
        assert from_markdown == set(ids)

    # Verifies: REQ-p00084-D
    def test_scoped_csv_stays_parseable(
        self, canonical_federated_graph, canonical_config, standard_preset, scoped
    ):
        """The disclosure is a leading one-field comment row, not loose text.

        A reader who files the CSV feeds it to something; a disclosure that made
        the file unreadable would trade one defect for another.
        """
        out = _render(canonical_federated_graph, "csv", standard_preset, scoped, canonical_config)
        rows = list(csv.reader(io.StringIO(out)))
        disclosure_rows = rows[: len(scoped[1])]
        assert [row[0] for row in disclosure_rows] == [f"# {line}" for line in scoped[1]]
        assert all(len(row) == 1 for row in disclosure_rows)
        # Every data row still carries the full set of columns.
        header = rows[len(scoped[1])]
        assert header[0] == "ID"
        assert all(len(row) == len(header) for row in rows[len(scoped[1]) + 1 :] if row)

    # Verifies: REQ-p00084-D
    def test_scoped_json_is_an_object_carrying_the_scope(
        self, canonical_federated_graph, canonical_config, standard_preset, scoped
    ):
        payload = json.loads(
            _render(canonical_federated_graph, "json", standard_preset, scoped, canonical_config)
        )
        assert payload["scope"] == list(scoped[1])
        assert isinstance(payload["nodes"], list)

    # Verifies: REQ-p00084-D
    def test_an_unscoped_json_report_declares_nothing_and_stays_an_array(
        self, canonical_federated_graph, canonical_config, standard_preset
    ):
        """D binds a *scoped* report. A report that narrowed nothing has nothing
        to declare, and its document keeps the shape every consumer reads."""
        payload = json.loads(
            "\n".join(
                trace.format_json(
                    canonical_federated_graph, standard_preset, None, None, canonical_config, []
                )
            )
        )
        assert isinstance(payload, list)


class TestTraceReachesTheArtifactNotTheTerminal:
    """The disclosure travels on the stream the artifact is written from."""

    # Verifies: REQ-p00084-D
    @pytest.mark.parametrize("fmt", TABLE_FORMATS)
    def test_table_rendering_writes_the_disclosure_to_stdout(
        self, canonical_federated_graph, canonical_config, standard_preset, scoped, capsys, fmt
    ):
        """`--output` redirects stdout alone, so a disclosure printed to stderr
        never reaches the file the reader keeps."""
        ids, lines = scoped
        rc = trace._render_table_from_graph(
            canonical_federated_graph, fmt, standard_preset, ids, None, canonical_config, lines
        )
        assert rc == 0
        captured = capsys.readouterr()
        for line in lines:
            assert line in captured.out
            assert line not in captured.err

    # Verifies: REQ-p00084-D
    def test_daemon_payload_json_path_writes_the_disclosure_to_stdout(
        self, canonical_federated_graph, canonical_config, standard_preset, scope_params, capsys
    ):
        """The payload a serving process returns already carries the scope; the
        rendering of it has to agree."""
        data = trace.compute_trace(
            canonical_federated_graph, canonical_config, _trace_request(scope_params)
        )
        assert data["scope"], "the computed payload must carry a disclosure to render"
        trace._render_json_from_data(data, standard_preset)
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert payload["scope"] == data["scope"]
        assert {node["id"] for node in payload["nodes"]} == {node["id"] for node in data["nodes"]}
        for line in data["scope"]:
            assert line not in captured.err

    # Verifies: REQ-p00084-D
    def test_run_writes_the_disclosure_to_the_redirected_stream(
        self, canonical_federated_graph, canonical_config, capsys, monkeypatch
    ):
        """The whole command, from invocation to rendering.

        `cli.main` points ``sys.stdout`` at the ``--output`` file and leaves
        stderr on the terminal, so this is the stream that decides whether the
        artifact is mute.
        """
        from elspais import config as config_mod
        from elspais.commands import _engine

        monkeypatch.setattr(config_mod, "get_config", lambda *a, **k: canonical_config)
        monkeypatch.setattr(
            _engine,
            "call",
            lambda path, params, fn, **kw: fn(
                canonical_federated_graph, canonical_config, kw.get("request") or params
            ),
        )
        monkeypatch.setattr(_engine, "get_graph", lambda: canonical_federated_graph)

        args = _scope_args(format="csv")
        assert trace.run(args) == 0
        captured = capsys.readouterr()
        assert "Scope: level prd" in captured.out
        assert "Scope:" not in captured.err


class TestAnalysisDisclosesItsScope:
    """The foundation ranking is a scoped report like any other."""

    # Verifies: REQ-p00084-D
    def test_scoped_payload_carries_the_disclosure(
        self, canonical_federated_graph, canonical_config, scope_params
    ):
        data = analysis_cmd.compute_analysis(
            canonical_federated_graph, canonical_config, {**scope_params, "top": "5"}
        )
        assert data["scope"], "a ranking narrowed to one level must say so"
        ranked = {ns["node_id"] for ns in data["ranked_nodes"]}
        result = resolve_scope_for_report(canonical_federated_graph, scope_params, canonical_config)
        assert ranked <= set(result.ids)

    # Verifies: REQ-p00084-D
    def test_an_unranked_scope_declares_nothing(self, canonical_federated_graph, canonical_config):
        data = analysis_cmd.compute_analysis(canonical_federated_graph, canonical_config, {})
        assert "scope" not in data

    # Verifies: REQ-p00084-C+D
    @pytest.mark.parametrize("fmt", ["table", "json"])
    def test_both_renderings_state_the_scope_on_stdout(
        self, canonical_federated_graph, canonical_config, scope_params, capsys, fmt
    ):
        data = analysis_cmd.compute_analysis(
            canonical_federated_graph, canonical_config, {**scope_params, "top": "5"}
        )
        report = analysis_cmd._report_from_dict(data)
        if fmt == "json":
            analysis_cmd._render_json(report, data["scope"])
        else:
            analysis_cmd._render_table(report, "all", data["scope"])
        captured = capsys.readouterr()
        for line in data["scope"]:
            assert line in captured.out
            assert line not in captured.err
        if fmt == "json":
            assert json.loads(captured.out)["scope"] == data["scope"]


def _trace_request(params: dict):
    from elspais.commands._edges import report_inputs_from_params
    from elspais.commands._requests import TraceRequest

    inputs = report_inputs_from_params(params, trace.OFFERED_VALUES, identity_key="id")
    return TraceRequest(scope=inputs.scope, values=inputs.values)


def _summary_request(params: dict):
    from elspais.commands._edges import report_inputs_from_params
    from elspais.commands._requests import SummaryRequest

    inputs = report_inputs_from_params(params, summary.OFFERED_VALUES, summary.IDENTITY_VALUE)
    return SummaryRequest(scope=inputs.scope, values=inputs.values)


@pytest.fixture(scope="module")
def scoped_summary(canonical_federated_graph, canonical_config, scope_params) -> dict:
    """A coverage summary computed under the same narrowing."""
    return summary.compute_summary(
        canonical_federated_graph, canonical_config, _summary_request(scope_params)
    )


class TestSummaryCsvDisclosesItsScope:
    """The one summary rendering that stated no scope now states the same one
    its text, markdown and JSON renderings do."""

    # Verifies: REQ-p00084-D
    def test_csv_states_the_scope(self, scoped_summary, canonical_config):
        assert scoped_summary["scope"], "the fixture must narrow something"
        out = summary._render_csv(scoped_summary, canonical_config)
        rows = list(csv.reader(io.StringIO(out)))
        assert [row[0] for row in rows[: len(scoped_summary["scope"])]] == [
            f"# {line}" for line in scoped_summary["scope"]
        ]

    # Verifies: REQ-p00084-C
    def test_csv_states_what_the_other_formats_state(self, scoped_summary, canonical_config):
        lines = scoped_summary["scope"]
        csv_out = summary._render_csv(scoped_summary, canonical_config)
        text_out = summary._render_text(scoped_summary, canonical_config)
        markdown_out = summary._render_markdown(scoped_summary, canonical_config)
        json_out = summary._render_json(scoped_summary)
        for line in lines:
            assert line in csv_out
            assert line in text_out
            assert line in markdown_out
        assert json.loads(json_out)["scope"] == lines

    # Verifies: REQ-p00084-D
    def test_an_unscoped_csv_declares_nothing(self, canonical_federated_graph, canonical_config):
        data = summary.compute_summary(
            canonical_federated_graph, canonical_config, _summary_request({})
        )
        assert not data["scope"]
        rows = list(csv.reader(io.StringIO(summary._render_csv(data, canonical_config))))
        assert rows[0][0] == "Level"


# ─────────────────────────────────────────────────────────────────────────────
# A scope property accumulates across the ways a reader may spell it
# ─────────────────────────────────────────────────────────────────────────────
#
# Per REQ-d00278-C a scope admits any combination of the properties it selects
# on and the values each property admits. A flag that kept only its last occurrence put
# some of those combinations out of a reader's reach while looking like the whole
# invocation had been read -- `--not-status Draft --not-status Active` selected
# as though only `Active` had been named. REQ-d00279-C is the other half: the
# tyro path (a section asked for alone) and the argparse path (a composed
# report) must read ONE invocation into one scope.


def _flat_args(**overrides) -> argparse.Namespace:
    """An invocation carrying nothing, for one property to be named on."""
    fields = {
        "level": None,
        "not_level": None,
        "status": None,
        "not_status": None,
        "match_status_roles": False,
        "scope": None,
    }
    fields.update(overrides)
    return argparse.Namespace(**fields)


# The four properties, each with the side of the scope it lands on and the name
# the scope authority knows it by.
SCOPE_FLAGS = [
    ("level", "include", "level"),
    ("not_level", "exclude", "level"),
    ("status", "include", "status"),
    ("not_status", "exclude", "status"),
]


def _selected(scope, side: str, prop: str):
    assert scope is not None
    return getattr(scope, side).get(prop)


class TestAScopePropertyAccumulates:
    """Reading one invocation's scope, whichever parser handed it over."""

    # Verifies: REQ-d00278-C
    @pytest.mark.parametrize("field,side,prop", SCOPE_FLAGS)
    @pytest.mark.parametrize(
        "raw,expected",
        [
            # The flag repeated: each occurrence arrives as its own list.
            ([["Draft"], ["Active"]], ("Draft", "Active")),
            # The values space-separated behind one flag.
            ([["Draft", "Active"]], ("Draft", "Active")),
            # Both at once.
            ([["Draft"], ["Active", "Review"]], ("Draft", "Active", "Review")),
            # The flat shape older callers and the argparse parser hand over.
            (["Draft", "Active"], ("Draft", "Active")),
            # A single value, however nested.
            ([["Draft"]], ("Draft",)),
            (["Draft"], ("Draft",)),
        ],
    )
    def test_every_value_named_reaches_the_scope(self, field, side, prop, raw, expected):
        """Each spelling of the same selection reaches the authority as one thing.

        The values are asserted exactly rather than by count: a reading that
        kept the inner lists whole would carry ``"['Draft']"`` -- a value no
        requirement can ever carry -- and a count would not notice.
        """
        scope = scope_from_args(_flat_args(**{field: raw}))
        assert _selected(scope, side, prop) == expected

    # Verifies: REQ-d00278-C
    @pytest.mark.parametrize("field,_side,_prop", SCOPE_FLAGS)
    @pytest.mark.parametrize("raw", [None, [], [[]], [""], [[" "]]])
    def test_a_property_named_with_nothing_selects_nothing(self, field, _side, _prop, raw):
        assert scope_from_args(_flat_args(**{field: raw})) is None

    # Verifies: REQ-d00278-C, REQ-d00279-C
    @pytest.mark.parametrize("field,side,prop", SCOPE_FLAGS)
    def test_the_two_parsers_read_one_invocation_alike(self, field, side, prop):
        """The tyro path and the composed-report path, on the same argv.

        This is the REQ-d00279-C parity point at the level of the scope itself:
        one invocation, two parsers, and one selection.
        """
        flag = "--" + field.replace("_", "-")
        repeated = [flag, "Draft", flag, "Active"]
        spaced = [flag, "Draft", "Active"]

        for argv in (repeated, spaced):
            tyro_scope = scope_from_args(_to_namespace(tyro.cli(GlobalArgs, args=["gaps", *argv])))
            argparse_scope = scope_from_args(parse_shared_args(argv))
            assert _selected(tyro_scope, side, prop) == ("Draft", "Active"), argv
            assert tyro_scope == argparse_scope, argv

    # Verifies: REQ-d00278-C
    @pytest.mark.parametrize("field,side,prop", SCOPE_FLAGS)
    def test_the_repeated_and_the_space_separated_spelling_agree(self, field, side, prop):
        """Two spellings of one selection, read through the real CLI path.

        ``_to_namespace`` is what production hands ``scope_from_args``, so the
        conversion is inside the test rather than assumed transparent.
        """
        flag = "--" + field.replace("_", "-")
        repeated = _to_namespace(tyro.cli(GlobalArgs, args=["gaps", flag, "Draft", flag, "Active"]))
        spaced = _to_namespace(tyro.cli(GlobalArgs, args=["gaps", flag, "Draft", "Active"]))
        assert scope_from_args(repeated) == scope_from_args(spaced)
        assert _selected(scope_from_args(repeated), side, prop) == ("Draft", "Active")


class TestOneGathererReadsEveryRepeatedFlag:
    """``flag_values`` is the one place a repeated flag becomes the one list it
    names, and it serves every accumulating flag rather than the scope
    properties alone -- so a reader who has learned how one flag reads has
    learned how they all do. Reading it per flag is how ``--not-status`` came
    to accumulate while ``--treat-active`` kept its last occurrence.
    """

    # Verifies: REQ-d00278-C
    @pytest.mark.parametrize(
        "raw,expected",
        [
            # The flag repeated: each occurrence arrives as its own list.
            ([["Draft"], ["Active"]], ("Draft", "Active")),
            # The values space-separated behind one flag.
            ([["Draft", "Active"]], ("Draft", "Active")),
            # Both at once, in the order the invocation named them.
            ([["Draft"], ["Active", "Review"]], ("Draft", "Active", "Review")),
            # The flat shape the composed report's argparse parser produces.
            (["Draft", "Active"], ("Draft", "Active")),
            # A bare string, which a caller assembling a namespace may hand
            # over -- read as one value, never as its characters.
            ("Draft", ("Draft",)),
        ],
    )
    def test_every_value_named_is_gathered_whatever_the_shape(self, raw, expected):
        from elspais.commands._scope import flag_values

        assert flag_values(argparse.Namespace(anything=raw), "anything") == expected

    # Verifies: REQ-d00278-C
    @pytest.mark.parametrize("raw", [None, [], [[]], [""], [[" "]], ""])
    def test_a_flag_named_with_nothing_gathers_nothing(self, raw):
        """An empty value is not a value: gathered, it would select on a status
        no requirement carries and quietly empty the report."""
        from elspais.commands._scope import flag_values

        assert flag_values(argparse.Namespace(anything=raw), "anything") == ()

    # Verifies: REQ-d00278-C
    def test_a_flag_the_invocation_never_named_gathers_nothing(self):
        from elspais.commands._scope import flag_values

        assert flag_values(argparse.Namespace(), "absent") == ()


class TestAccumulationIsObservableInTheSelection:
    """The defect stated as the reader met it: a set of requirements.

    The canonical estate carries PRD, OPS and DEV requirements and no status
    other than Active, so ``--not-level`` is where the two spellings can be told
    apart by what they select.
    """

    def _ids(self, graph, config, argv):
        return resolve_scope_for_report(
            graph, _to_namespace(tyro.cli(GlobalArgs, args=["gaps", *argv])), config
        ).ids

    # Verifies: REQ-d00278-C
    def test_repeating_an_exclusion_excludes_both_levels(
        self, canonical_federated_graph, canonical_config
    ):
        """Naming a second level to refuse must narrow the set, not replace the
        refusal with it -- the shape of the reported defect."""
        both = self._ids(
            canonical_federated_graph,
            canonical_config,
            ["--not-level", "ops", "--not-level", "dev"],
        )
        last_only = self._ids(canonical_federated_graph, canonical_config, ["--not-level", "dev"])
        assert both < last_only, (
            "the repeated exclusion selected as though only its last occurrence "
            f"had been read: {sorted(both)} vs {sorted(last_only)}"
        )

    # Verifies: REQ-d00279-C
    def test_both_spellings_select_the_same_requirements(
        self, canonical_federated_graph, canonical_config
    ):
        repeated = self._ids(
            canonical_federated_graph,
            canonical_config,
            ["--not-level", "ops", "--not-level", "dev"],
        )
        spaced = self._ids(
            canonical_federated_graph, canonical_config, ["--not-level", "ops", "dev"]
        )
        assert repeated == spaced

    # Verifies: REQ-d00278-C
    def test_repeating_an_inclusion_widens_the_set(
        self, canonical_federated_graph, canonical_config
    ):
        both = self._ids(
            canonical_federated_graph, canonical_config, ["--level", "prd", "--level", "ops"]
        )
        last_only = self._ids(canonical_federated_graph, canonical_config, ["--level", "ops"])
        assert last_only < both
        assert both == self._ids(
            canonical_federated_graph, canonical_config, ["--level", "prd", "ops"]
        )

    # Verifies: REQ-d00279-C
    def test_the_composed_report_path_selects_the_same_requirements(
        self, canonical_federated_graph, canonical_config
    ):
        """A composed report reads the repeated flag the way a lone section does."""
        argv = ["--not-level", "ops", "--not-level", "dev"]
        composed = resolve_scope_for_report(
            canonical_federated_graph, parse_shared_args(argv), canonical_config
        ).ids
        assert composed == self._ids(canonical_federated_graph, canonical_config, argv)
