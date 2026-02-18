# Implements: REQ-p00080-A, REQ-p00080-C
"""Pandoc PDF renderer.

Invokes pandoc as a subprocess to convert assembled Markdown to PDF.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


def _find_bundled_template() -> Path:
    """Locate the bundled LaTeX template shipped with the package."""
    return Path(__file__).parent / "templates" / "elspais.latex"


def render_pdf(
    markdown_content: str,
    output_path: Path,
    engine: str = "xelatex",
    template: Path | None = None,
    cover: Path | None = None,
) -> int:
    """Render Markdown content to PDF via pandoc.

    Args:
        markdown_content: Assembled Markdown string.
        output_path: Destination PDF file.
        engine: LaTeX engine (xelatex, lualatex, pdflatex).
        template: Custom LaTeX template path, or None for bundled.
        cover: Markdown file for custom cover page.

    Returns:
        0 on success, non-zero on failure.
    """
    # Resolve template
    if template is None:
        template = _find_bundled_template()
    if not template.exists():
        print(f"Error: LaTeX template not found: {template}", file=sys.stderr)
        return 1

    # Write markdown to temp file
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".md",
        encoding="utf-8",
        delete=False,
    ) as tmp:
        tmp.write(markdown_content)
        tmp_path = tmp.name

    # If cover is provided, write a .tex file from it (it's already raw LaTeX)
    cover_tex_path = None
    if cover and cover.exists():
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".tex",
            encoding="utf-8",
            delete=False,
        ) as ctmp:
            ctmp.write(cover.read_text(encoding="utf-8"))
            cover_tex_path = ctmp.name

    try:
        cmd = [
            "pandoc",
            tmp_path,
            f"--pdf-engine={engine}",
            f"--template={template}",
            "--from=markdown+raw_tex",
            "--top-level-division=chapter",
            "-o",
            str(output_path),
        ]

        if cover_tex_path:
            cmd.extend(["-V", f"cover-tex={cover_tex_path}"])

        # Set SOURCE_DATE_EPOCH for deterministic output
        env = os.environ.copy()
        env.setdefault("SOURCE_DATE_EPOCH", "0")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
        )

        if result.returncode != 0:
            print("Error: pandoc failed.", file=sys.stderr)
            if result.stderr:
                print(result.stderr, file=sys.stderr)
            return result.returncode

        return 0

    finally:
        # Clean up temp files
        for p in [tmp_path, cover_tex_path]:
            if p:
                try:
                    os.unlink(p)
                except OSError:
                    pass
