# Implements: REQ-p00080-A, REQ-p00080-C, REQ-p00080-K
"""Pandoc PDF renderer.

Invokes pandoc as a subprocess to convert assembled Markdown to PDF.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# Pandoc reports a resource it could not fetch on stderr and still exits
# successfully, replacing the image with its alt text.
_UNFETCHED_RE = re.compile(r"Could not fetch resource (.+?): replacing")


def _find_bundled_template() -> Path:
    """Locate the bundled LaTeX template shipped with the package."""
    return Path(__file__).parent / "templates" / "elspais.latex"


def render_pdf(
    markdown_content: str,
    output_path: Path,
    engine: str = "xelatex",
    template: Path | None = None,
    cover: Path | None = None,
    resource_paths: list[Path] | None = None,
    unfetched: list[str] | None = None,
) -> int:
    """Render Markdown content to PDF via pandoc.

    Args:
        markdown_content: Assembled Markdown string.
        output_path: Destination PDF file.
        engine: LaTeX engine (xelatex, lualatex, pdflatex).
        template: Custom LaTeX template path, or None for bundled.
        cover: Markdown file for custom cover page.
        resource_paths: Directories pandoc should search when resolving
            relative image references. Required when assembled markdown
            references images by relative path -- pandoc would otherwise
            resolve them against the tempfile's directory in `/tmp/`.
        unfetched: Collector extended with the name of every resource
            pandoc reported it could not fetch. Pandoc drops such a
            resource and still exits successfully, so a caller that
            reports on document completeness cannot learn about the
            omission from the return code alone.

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

        if resource_paths:
            resource_arg = os.pathsep.join(str(p) for p in resource_paths)
            cmd.append(f"--resource-path={resource_arg}")

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

        stderr = result.stderr or ""

        # Pandoc drops an unfetchable image and still exits 0, so the
        # omission is only visible here. Surface it to the caller.
        # Implements: REQ-p00080-K
        if unfetched is not None:
            for match in _UNFETCHED_RE.finditer(stderr):
                name = match.group(1).strip()
                if name not in unfetched:
                    unfetched.append(name)

        if result.returncode != 0:
            # The whole stream matters when the run failed: the cause is
            # usually in the engine's output, not pandoc's own lines.
            if stderr:
                print(stderr.rstrip("\n"), file=sys.stderr)
            print("Error: pandoc failed.", file=sys.stderr)
            return result.returncode

        # On success, echo only pandoc's own diagnostics. The LaTeX engine
        # narrates font substitution at length on a healthy run, and
        # burying the one line that reports a dropped image in sixty lines
        # of font chatter discloses nothing.
        # Implements: REQ-p00080-K
        for line in stderr.splitlines():
            if line.startswith("[WARNING]") or line.startswith("[ERROR]"):
                print(line, file=sys.stderr)

        return 0

    finally:
        # Clean up temp files
        for p in [tmp_path, cover_tex_path]:
            if p:
                try:
                    os.unlink(p)
                except OSError:
                    pass
