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

from elspais.commands import analysis_cmd, summary, trace
from elspais.commands._scope import (
    resolve_scope_for_report,
    scope_disclosure,
    scope_params_from_args,
)
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

    # Verifies: REQ-p00084-B
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

    # Verifies: REQ-p00084-B
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
        data = trace.compute_trace(canonical_federated_graph, canonical_config, scope_params)
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
            lambda path, params, fn, **kw: fn(canonical_federated_graph, canonical_config, params),
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

    # Verifies: REQ-p00084-B+D
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


@pytest.fixture(scope="module")
def scoped_summary(canonical_federated_graph, canonical_config, scope_params) -> dict:
    """A coverage summary computed under the same narrowing."""
    return summary.compute_summary(canonical_federated_graph, canonical_config, scope_params)


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

    # Verifies: REQ-p00084-B
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
        data = summary.compute_summary(canonical_federated_graph, canonical_config, {})
        assert not data["scope"]
        rows = list(csv.reader(io.StringIO(summary._render_csv(data, canonical_config))))
        assert rows[0][0] == "Level"
