# Verifies: REQ-p00013-B
"""Shared fixtures and helpers for end-to-end CLI tests.

Provides subprocess helpers, path constants, and skip markers.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

_ELSPAIS = shutil.which("elspais")

REPO_ROOT = (
    Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    if shutil.which("git")
    else Path(__file__).resolve().parents[2]
)

FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"


def run_elspais(*args: str, cwd: str | Path | None = None) -> subprocess.CompletedProcess:
    """Run elspais as a subprocess and return the CompletedProcess."""
    if _ELSPAIS is None:
        pytest.skip("elspais CLI not found on PATH")
    return subprocess.run(
        [_ELSPAIS, *args],
        capture_output=True,
        text=True,
        cwd=cwd or REPO_ROOT,
        timeout=120,
    )


requires_elspais = pytest.mark.skipif(
    _ELSPAIS is None,
    reason="elspais CLI not found on PATH",
)

requires_pandoc = pytest.mark.skipif(
    shutil.which("pandoc") is None,
    reason="pandoc not found (install: https://pandoc.org/installing.html)",
)

requires_xelatex = pytest.mark.skipif(
    shutil.which("xelatex") is None,
    reason="xelatex not found (install TeX Live, MiKTeX, or MacTeX)",
)

requires_playwright = pytest.mark.skipif(
    shutil.which("playwright") is None,
    reason="playwright not found (pip install playwright && playwright install)",
)
