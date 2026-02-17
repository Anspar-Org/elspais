# Implements: REQ-p00080-A, REQ-p00080-E
"""
elspais.commands.pdf_cmd - Compile spec files into a PDF document.

Assembles a structured Markdown document from the traceability graph,
then invokes Pandoc with a custom LaTeX template to produce a PDF.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


def _check_tool(name: str) -> str | None:
    """Return the path to an executable, or None if not found."""
    return shutil.which(name)


def run(args: argparse.Namespace) -> int:
    """Run the pdf command.

    Builds a TraceGraph, assembles Markdown, and invokes Pandoc to generate PDF.
    """
    # Check for required external tools
    engine = getattr(args, "engine", "xelatex")
    if not _check_tool("pandoc"):
        print("Error: pandoc not found on PATH.", file=sys.stderr)
        print("Install with: https://pandoc.org/installing.html", file=sys.stderr)
        return 1

    if not _check_tool(engine):
        print(f"Error: {engine} not found on PATH.", file=sys.stderr)
        print(
            f"Install a TeX distribution that provides {engine}.",
            file=sys.stderr,
        )
        return 1

    # Build graph using factory
    from elspais.graph.factory import build_graph

    spec_dir = getattr(args, "spec_dir", None)
    config_path = getattr(args, "config", None)
    repo_root = Path(spec_dir).parent if spec_dir else Path.cwd()

    graph = build_graph(
        spec_dirs=[spec_dir] if spec_dir else None,
        config_path=config_path,
        repo_root=repo_root,
        scan_code=False,
        scan_tests=False,
    )

    # Assemble Markdown from graph
    from elspais.pdf.assembler import MarkdownAssembler

    title = getattr(args, "title", None) or "Requirements Specification"
    cover = getattr(args, "cover", None)
    assembler = MarkdownAssembler(graph, title=title)
    markdown_content = assembler.assemble()

    # Invoke Pandoc to produce PDF
    output_path = getattr(args, "output", None) or Path("spec-output.pdf")
    template = getattr(args, "template", None)

    from elspais.pdf.renderer import render_pdf

    rc = render_pdf(
        markdown_content,
        output_path=Path(output_path),
        engine=engine,
        template=template,
        cover=cover,
    )

    if rc == 0:
        print(f"PDF written to {output_path}")
    return rc
