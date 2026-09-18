# Implements: REQ-d00298-A, REQ-d00298-B, REQ-d00298-D, REQ-d00298-E, REQ-d00298-F
"""A viewer report rendered as a document to download.

The viewer shows a report; this module turns the same report into the file a
reader files. It renders nothing of its own: a markdown or CSV export is the
command's own formatter run over the command's own payload, and a PDF is that
markdown handed to pandoc. What a report offers here is read off the table the
command line reads, so the two surfaces offer one set.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from elspais.graph.federated import FederatedGraph

# The reports the viewer can show and therefore export, in the order a page
# lists them.
EXPORT_REPORTS: tuple[str, ...] = ("trace", "summary", "gaps", "checks")

# The document formats an export renders directly. The machine formats a
# report also offers (json, junit, sarif) are what the run routes already
# answer with and are not documents.
DOCUMENT_FORMATS: tuple[str, ...] = ("markdown", "csv")
PDF_FORMAT = "pdf"
PDF_ENGINE = "xelatex"

MEDIA_TYPES: dict[str, str] = {
    "markdown": "text/markdown; charset=utf-8",
    "csv": "text/csv; charset=utf-8",
    PDF_FORMAT: "application/pdf",
}
EXTENSIONS: dict[str, str] = {"markdown": "md", "csv": "csv", PDF_FORMAT: "pdf"}

# What to install when a tool the PDF path needs is absent.
INSTALL_HINTS: dict[str, str] = {
    "pandoc": "install pandoc (https://pandoc.org/installing.html)",
    PDF_ENGINE: f"install a TeX distribution that provides {PDF_ENGINE}",
}


class UnofferedFormat(ValueError):
    """A format this report does not offer."""

    def __init__(self, report: str, fmt: str, offered: Sequence[str]) -> None:
        self.report = report
        self.fmt = fmt
        self.offered = tuple(offered)
        super().__init__(
            f"'{report}' does not export as {fmt}; it offers {', '.join(self.offered)}"
        )


class ToolingUnavailable(RuntimeError):
    """A tool the format needs is not on the PATH."""

    def __init__(self, tool: str) -> None:
        self.tool = tool
        super().__init__(f"{tool} not found on PATH -- {INSTALL_HINTS[tool]}")


class RenderFailed(RuntimeError):
    """The converter ran and did not produce the document."""


# Implements: REQ-d00298-A, REQ-d00298-E
def offered_formats(report: str) -> tuple[str, ...]:
    """The export formats one report offers.

    Read off the command line's own table rather than declared again here, so
    a format the command offers is the format the viewer offers. PDF is
    offered wherever markdown is, because it is that markdown converted.
    """
    from elspais.commands.report import FORMAT_SUPPORT

    supported = FORMAT_SUPPORT[report]
    offered = [fmt for fmt in DOCUMENT_FORMATS if fmt in supported]
    if "markdown" in supported:
        offered.append(PDF_FORMAT)
    return tuple(offered)


def export_offers() -> dict[str, list[str]]:
    """Every exportable report with the formats it offers, for a page to show."""
    return {report: list(offered_formats(report)) for report in EXPORT_REPORTS}


# Implements: REQ-d00298-B
def render_document(
    graph: FederatedGraph, config: dict[str, Any], report: str, request: Any, fmt: str
) -> str:
    """One report, in one document format, through the command's renderer.

    Each branch is the command's own path: the payload its ``compute_*``
    produces, rendered by the function its ``run`` renders with. Nothing here
    decides what a value means -- the request arrived with that decided.
    """
    if report == "summary":
        from elspais.commands.summary import compute_summary, render_summary

        return render_summary(compute_summary(graph, config, request), fmt, config)
    if report == "trace":
        from elspais.commands.trace import render_trace

        return render_trace(graph, config, request, fmt)
    if report == "gaps":
        from elspais.commands.gaps import compute_gaps, gap_sections, render_gaps

        data = compute_gaps(graph, config, request)
        return render_gaps(data, fmt, gap_sections(request.values, request.command))
    if report == "checks":
        from elspais.commands.health import compute_checks, render_checks

        return render_checks(compute_checks(graph, config, request), fmt, request)
    raise KeyError(report)


# Implements: REQ-d00298-D
def markdown_to_pdf(markdown: str) -> bytes:
    """Convert a rendered markdown document to PDF through pandoc.

    A missing tool is refused before anything runs, naming what to install; a
    converter that ran and left no document, or an empty one, is a failure
    carrying its own output -- never a short file that downloads as if it were
    the report.
    """
    for tool in ("pandoc", PDF_ENGINE):
        if shutil.which(tool) is None:
            raise ToolingUnavailable(tool)
    with tempfile.TemporaryDirectory(prefix="elspais-export-") as tmp:
        source = Path(tmp) / "report.md"
        output = Path(tmp) / "report.pdf"
        source.write_text(markdown, encoding="utf-8")
        result = subprocess.run(
            [
                "pandoc",
                str(source),
                f"--pdf-engine={PDF_ENGINE}",
                "--from=markdown",
                "-o",
                str(output),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RenderFailed(
                f"pandoc exited {result.returncode}: {(result.stderr or '').strip()}"
            )
        if not output.exists():
            raise RenderFailed("pandoc exited 0 and wrote no document")
        body = output.read_bytes()
    if not body:
        raise RenderFailed("pandoc wrote an empty document")
    return body


# Implements: REQ-d00298-A, REQ-d00298-D, REQ-d00298-E
def export_report(
    graph: FederatedGraph, config: dict[str, Any], report: str, request: Any, fmt: str
) -> bytes:
    """The bytes of one report in one format, or a refusal.

    Judged against the offer before anything is rendered, so a refusal has
    produced nothing. A PDF is the markdown rendering converted, which is what
    makes it state the same values the markdown states.
    """
    offered = offered_formats(report)
    if fmt not in offered:
        raise UnofferedFormat(report, fmt, offered)
    if fmt == PDF_FORMAT:
        return markdown_to_pdf(render_document(graph, config, report, request, "markdown"))
    return render_document(graph, config, report, request, fmt).encode("utf-8")


# Implements: REQ-d00298-F
def download_filename(report: str, fmt: str, now: datetime | None = None) -> str:
    """The name a download carries: which report, when, and in what format."""
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    return f"{report}-{stamp}.{EXTENSIONS[fmt]}"
