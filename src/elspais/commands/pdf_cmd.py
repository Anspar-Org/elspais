# Implements: REQ-p00080-A, REQ-p00080-E, REQ-p00080-F, REQ-p00080-I, REQ-p00080-J, REQ-p00080-K
"""
elspais.commands.pdf_cmd - Compile spec files into a PDF document.

Assembles a structured Markdown document from the traceability graph,
then invokes Pandoc with a custom LaTeX template to produce a PDF.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from collections.abc import Iterable
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
    from elspais.config import get_config
    from elspais.pdf.assembler import MarkdownAssembler
    from elspais.utilities.patterns import build_resolver

    config = get_config(config_path, repo_root)
    resolver = build_resolver(config)

    title = getattr(args, "title", None)
    cover = getattr(args, "cover", None)
    overview = getattr(args, "overview", False)
    max_depth = getattr(args, "max_depth", None)
    assembler = MarkdownAssembler(
        graph,
        title=title,
        overview=overview,
        max_depth=max_depth,
        resolver=resolver,
        config=config,
    )
    markdown_content = assembler.assemble()

    # Content the assembler could not place. Reported before the verdict
    # so the operator reads the cause ahead of the qualified success line.
    # Implements: REQ-p00080-I, REQ-p00080-J
    diagnostics = list(assembler.iter_diagnostics())
    _report_omissions(len(diagnostics), (d.format() for d in diagnostics))

    # Invoke Pandoc to produce PDF
    output_path = getattr(args, "output", None) or Path("spec-output.pdf")
    template = getattr(args, "template", None)

    from elspais.pdf.renderer import render_pdf

    # Pandoc drops references the assembler never saw -- media types
    # outside its reference grammar, reference-style links -- and still
    # exits 0. Those omissions are as real as the ones found here.
    unfetched: list[str] = []
    rc = render_pdf(
        markdown_content,
        output_path=Path(output_path),
        engine=engine,
        template=template,
        cover=cover,
        resource_paths=assembler.resource_roots(),
        unfetched=unfetched,
    )

    # A reference the assembler already named will also be named by
    # pandoc; count it once.
    known = {d.reference for d in diagnostics}
    extra = [name for name in unfetched if name not in known]
    _report_omissions(
        len(extra),
        (
            f"  pandoc could not fetch '{name}'\n"
            f"    cause: The resource was not found on the resource path.\n"
            f"    remedy: Add the file, correct the reference, or remove the "
            f"reference from the spec."
            for name in extra
        ),
    )

    if rc == 0:
        # A document missing content it was asked to carry is not an
        # unqualified success, and must not be reported as one.
        # Implements: REQ-p00080-K
        omitted = len(diagnostics) + len(extra)
        if omitted:
            noun = "reference" if omitted == 1 else "references"
            print(
                f"PDF written to {output_path} "
                f"(INCOMPLETE: {omitted} {noun} omitted -- see warnings above)"
            )
        else:
            print(f"PDF written to {output_path}")
    return rc


def _report_omissions(count: int, blocks: Iterable[str]) -> None:
    """Print a heading and one block per omission, or nothing."""
    if not count:
        return
    noun = "reference" if count == 1 else "references"
    print(
        f"Warning: {count} {noun} could not be placed in the document.",
        file=sys.stderr,
    )
    for block in blocks:
        print(block, file=sys.stderr)
