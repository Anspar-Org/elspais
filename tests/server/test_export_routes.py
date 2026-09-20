# Verifies: REQ-d00298-A, REQ-d00298-B, REQ-d00298-C, REQ-d00298-D, REQ-d00298-E, REQ-d00298-F
"""Tests for GET /api/export/{report}: a viewer report as a document to download.

The export renders nothing of its own. A markdown or CSV body is what the
command's own formatter produces for the same request, byte for byte; a PDF is
that markdown converted by pandoc. The body compared against is the
formatter's return value -- the command prints it with a trailing newline the
download does not carry. Where a report reads a selection, the request
compared against is built at the command-line edge
(``report_inputs_from_args``), so the test crosses both edges rather than
calling the export's own builder twice; ``checks`` reads none, so its request
is stated outright and only the formatter is crossed.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from elspais.server.app import create_app
from elspais.server.state import AppState

_FILENAME = re.compile(
    r'^attachment; filename="(trace|summary|gaps|checks)-\d{8}-\d{6}\.(md|csv|pdf)"$'
)


@pytest.fixture(scope="module")
def client(canonical_federated_graph) -> TestClient:
    fg = canonical_federated_graph
    config = fg._repos[fg._root_repo].config
    repo_root = fg._repos[fg._root_repo].repo_root
    state = AppState(graph=fg, repo_root=repo_root, config=config)
    return TestClient(create_app(state, mount_mcp=False))


def _cli_rendering(report: str, fmt: str, graph, config, level: list[str] | None) -> str:
    """What the command line renders for these inputs, through its own edge."""
    args = argparse.Namespace(format=fmt, level=level)
    if report == "summary":
        from elspais.commands._edges import report_inputs_from_args
        from elspais.commands._requests import SummaryRequest
        from elspais.commands.summary import (
            IDENTITY_VALUE,
            OFFERED_VALUES,
            compute_summary,
            render_summary,
        )

        inputs = report_inputs_from_args(args, config, OFFERED_VALUES, IDENTITY_VALUE)
        request = SummaryRequest(inputs.scope, inputs.values, inputs.treat_active)
        return render_summary(compute_summary(graph, config, request), fmt, config)
    if report == "trace":
        from elspais.commands.trace import render_section

        output, rc = render_section(graph, args, config)
        assert rc == 0
        return output
    if report == "gaps":
        from elspais.commands._edges import report_inputs_from_args
        from elspais.commands._requests import GapsRequest
        from elspais.commands.gaps import OFFERED_VALUES, compute_gaps, gap_sections, render_gaps

        inputs = report_inputs_from_args(args, config, OFFERED_VALUES, identity_key="")
        request = GapsRequest(inputs.scope, inputs.values, inputs.treat_active)
        return render_gaps(compute_gaps(graph, config, request), fmt, gap_sections(None))
    if report == "checks":
        from elspais.commands._requests import ChecksRequest
        from elspais.commands.health import _format_report, _report_from_dict, compute_checks

        data = compute_checks(graph, config, ChecksRequest())
        return _format_report(_report_from_dict(data), args)
    raise AssertionError(report)


_DOCUMENT_CASES = [
    ("trace", "markdown"),
    ("trace", "csv"),
    ("summary", "markdown"),
    ("summary", "csv"),
    ("gaps", "markdown"),
    ("checks", "markdown"),
]


# Verifies: REQ-d00298-A, REQ-d00298-B
@pytest.mark.parametrize(("report", "fmt"), _DOCUMENT_CASES)
def test_export_body_is_the_cli_rendering_byte_for_byte(
    client, canonical_federated_graph, canonical_config, report, fmt
):
    """Every document format a report offers downloads as exactly what the
    command line renders for the same inputs."""
    response = client.get(f"/api/export/{report}", params={"format": fmt})
    assert response.status_code == 200, response.text
    expected = _cli_rendering(report, fmt, canonical_federated_graph, canonical_config, None)
    assert response.content == expected.encode("utf-8")


# Verifies: REQ-d00298-C
@pytest.mark.parametrize(
    ("report", "fmt"), [("trace", "csv"), ("summary", "markdown"), ("gaps", "markdown")]
)
def test_a_scope_sent_to_the_export_narrows_it_as_the_command_line_edge_does(
    client, canonical_federated_graph, canonical_config, report, fmt
):
    """A level narrowing arriving as a query reaches the same rows a reader
    typing `--level prd` reaches, and differs from the unnarrowed report."""
    whole = client.get(f"/api/export/{report}", params={"format": fmt})
    narrowed = client.get(f"/api/export/{report}", params={"format": fmt, "scope_level": "prd"})
    assert narrowed.status_code == 200, narrowed.text
    expected = _cli_rendering(report, fmt, canonical_federated_graph, canonical_config, ["prd"])
    assert narrowed.content == expected.encode("utf-8")
    assert narrowed.content != whole.content


# Verifies: REQ-d00298-C
def test_an_unoffered_value_is_refused_as_the_on_screen_route_refuses_it(client):
    """The export reads its query with the run route's own builder, so the
    same bad selection gets the same 400."""
    export = client.get("/api/export/trace", params={"format": "markdown", "values": "no_such"})
    shown = client.get("/api/run/trace", params={"values": "no_such"})
    assert export.status_code == shown.status_code == 400
    assert export.json() == shown.json()


# Verifies: REQ-d00298-E
@pytest.mark.parametrize(
    ("report", "fmt", "offered"),
    [
        ("gaps", "csv", ["markdown", "pdf"]),
        ("checks", "csv", ["markdown", "pdf"]),
        ("trace", "json", ["markdown", "csv", "pdf"]),
        ("summary", "html", ["markdown", "csv", "pdf"]),
    ],
)
def test_a_format_the_report_does_not_offer_is_refused_naming_the_offer(
    client, report, fmt, offered
):
    response = client.get(f"/api/export/{report}", params={"format": fmt})
    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "unoffered_format"
    assert body["offered"] == offered
    for name in offered:
        assert name in body["message"]


# Verifies: REQ-d00298-E
def test_a_missing_format_is_refused_naming_the_offer(client):
    response = client.get("/api/export/summary")
    assert response.status_code == 400
    assert response.json()["offered"] == ["markdown", "csv", "pdf"]


# Verifies: REQ-d00298-A
def test_a_report_the_viewer_cannot_export_is_not_found(client):
    response = client.get("/api/export/analysis", params={"format": "markdown"})
    assert response.status_code == 404
    assert response.json()["error"] == "unknown_report"


# Verifies: REQ-d00298-F
@pytest.mark.parametrize(
    ("report", "fmt", "media_type", "extension"),
    [
        ("trace", "markdown", "text/markdown; charset=utf-8", "md"),
        ("summary", "csv", "text/csv; charset=utf-8", "csv"),
    ],
)
def test_the_download_names_its_report_and_format(client, report, fmt, media_type, extension):
    response = client.get(f"/api/export/{report}", params={"format": fmt})
    assert response.status_code == 200
    assert response.headers["content-type"] == media_type
    disposition = response.headers["content-disposition"]
    match = _FILENAME.match(disposition)
    assert match, disposition
    assert match.group(1) == report
    assert match.group(2) == extension


_PDF_TOOLING = shutil.which("pandoc") is not None and shutil.which("xelatex") is not None


# Verifies: REQ-d00298-A, REQ-d00298-F
@pytest.mark.skipif(not _PDF_TOOLING, reason="pandoc and xelatex are needed for a PDF export")
@pytest.mark.parametrize("report", ["summary", "gaps"])
def test_a_pdf_export_is_a_pdf_document(client, report):
    response = client.get(f"/api/export/{report}", params={"format": "pdf"})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert _FILENAME.match(response.headers["content-disposition"]).group(2) == "pdf"
    assert response.content.startswith(b"%PDF")


# Verifies: REQ-d00298-D
@pytest.mark.parametrize("missing", ["pandoc", "xelatex"])
def test_missing_tooling_is_refused_naming_what_to_install(client, monkeypatch, missing):
    """Refused before anything runs: nothing downloads, and the reason says
    which tool is absent."""
    import elspais.server.export as export

    monkeypatch.setattr(
        export.shutil, "which", lambda name: None if name == missing else f"/usr/bin/{name}"
    )
    response = client.get("/api/export/trace", params={"format": "pdf"})
    assert response.status_code == 409
    body = response.json()
    assert body["error"] == "tooling_unavailable"
    assert body["tool"] == missing
    assert missing in body["message"]


# Verifies: REQ-d00298-D
def test_a_converter_that_fails_is_reported_with_its_output_not_delivered_short(
    client, monkeypatch
):
    import elspais.pdf.renderer as renderer
    import elspais.server.export as export

    monkeypatch.setattr(export.shutil, "which", lambda name: f"/usr/bin/{name}")

    def failing_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 43, stdout="", stderr="xelatex: font not found")

    monkeypatch.setattr(renderer.subprocess, "run", failing_run)
    response = client.get("/api/export/summary", params={"format": "pdf"})
    assert response.status_code == 500
    body = response.json()
    assert body["error"] == "render_failed"
    assert "xelatex: font not found" in body["message"]
    assert "43" in body["message"]


# Verifies: REQ-d00298-D
def test_a_converter_that_writes_nothing_is_a_failure_not_an_empty_download(client, monkeypatch):
    import elspais.pdf.renderer as renderer
    import elspais.server.export as export

    monkeypatch.setattr(export.shutil, "which", lambda name: f"/usr/bin/{name}")

    def silent_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(renderer.subprocess, "run", silent_run)
    response = client.get("/api/export/summary", params={"format": "pdf"})
    assert response.status_code == 500
    assert response.json()["error"] == "render_failed"


# Verifies: REQ-d00298-D
def test_a_resource_the_converter_could_not_fetch_refuses_rather_than_delivering_short(
    client, monkeypatch
):
    """Pandoc drops a resource it cannot fetch and still exits 0, so a PDF
    missing a figure it names would download looking complete. The export
    reads what the converter reported and refuses instead."""
    import elspais.pdf.renderer as renderer
    import elspais.server.export as export

    monkeypatch.setattr(export.shutil, "which", lambda name: f"/usr/bin/{name}")

    dropped = "[WARNING] Could not fetch resource diagram.png: replacing image with description"
    real_run = subprocess.run

    def dropping_run(cmd, **kwargs):
        # Only the converter is stubbed: rendering the report runs git of its
        # own, and a stub standing in for every subprocess would answer that
        # too. A converter that succeeded, wrote its document, and quietly
        # left a resource out of it.
        if not cmd or cmd[0] != "pandoc":
            return real_run(cmd, **kwargs)
        Path(cmd[cmd.index("-o") + 1]).write_bytes(b"%PDF-1.5 short")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr=dropped)

    monkeypatch.setattr(renderer.subprocess, "run", dropping_run)
    response = client.get("/api/export/summary", params={"format": "pdf"})
    assert response.status_code == 500
    body = response.json()
    assert body["error"] == "render_failed"
    assert "diagram.png" in body["message"]


# Verifies: REQ-d00298-A, REQ-d00298-E
def test_the_served_page_lists_the_offer_the_route_accepts(client):
    """The page's export control carries the server's own offer, so what a
    reader can choose is what the route will render."""
    import json

    from elspais.server.export import export_offers
    from elspais.server.routes_api import EXPORT_REQUEST_BUILDERS

    html = client.get("/").text
    match = re.search(r"data-offers='([^']+)'", html)
    assert match, "export control missing from the served page"
    assert json.loads(match.group(1)) == export_offers(EXPORT_REQUEST_BUILDERS)
    select = re.search(r'<select id="export-report".*?</select>', html, re.DOTALL).group(0)
    assert re.findall(r'<option value="([^"]+)"', select) == list(EXPORT_REQUEST_BUILDERS)
    assert 'id="btn-export"' in html
