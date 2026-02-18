# Implements: REQ-p00001-A, REQ-p00080-A, REQ-o00066-C
"""End-to-end CLI integration tests.

Invokes elspais as a subprocess to verify real command execution.
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

requires_pandoc = pytest.mark.skipif(
    shutil.which("pandoc") is None,
    reason="pandoc not found (install: https://pandoc.org/installing.html)",
)

requires_xelatex = pytest.mark.skipif(
    shutil.which("xelatex") is None,
    reason="xelatex not found (install TeX Live, MiKTeX, or MacTeX)",
)


def _run_elspais(*args: str, cwd: str | Path | None = None) -> subprocess.CompletedProcess:
    """Run elspais as a subprocess."""
    return subprocess.run(
        [sys.executable, "-m", "elspais", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=120,
    )


class TestCLIHelp:
    """Test --help works for main and subcommands."""

    def test_REQ_p00001_A_main_help(self):
        result = _run_elspais("--help")
        assert result.returncode == 0
        assert "elspais" in result.stdout

    def test_REQ_p00001_A_validate_help(self):
        result = _run_elspais("validate", "--help")
        assert result.returncode == 0

    def test_REQ_p00080_A_pdf_help(self):
        result = _run_elspais("pdf", "--help")
        assert result.returncode == 0
        assert "pandoc" in result.stdout.lower() or "pandoc" in result.stderr.lower()


class TestValidateCommand:
    """Test validate command runs end-to-end."""

    def test_REQ_p00001_A_validate_core(self):
        result = _run_elspais("validate", "--mode", "core")
        assert result.returncode == 0

    def test_REQ_o00066_C_index_validate(self):
        result = _run_elspais("index", "--mode", "core", "validate")
        assert result.returncode == 0


class TestDocsCommand:
    """Test docs command outputs content."""

    def test_REQ_p00001_A_docs_quickstart(self):
        result = _run_elspais("docs", "quickstart", "--plain")
        assert result.returncode == 0
        assert len(result.stdout) > 100


class TestTraceCommand:
    """Test trace command generates output."""

    def test_REQ_p00001_B_trace_markdown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "trace"
            result = _run_elspais("trace", "--format", "markdown", "--output", str(out))
            assert result.returncode == 0
            # trace command may add extension
            md_file = out.with_suffix(".md")
            alt_file = Path(f"{out}.md")
            assert md_file.exists() or alt_file.exists() or out.exists()


class TestPdfCommand:
    """Test PDF generation end-to-end."""

    @requires_pandoc
    @requires_xelatex
    def test_REQ_p00080_A_generates_pdf(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "test-output.pdf"
            result = _run_elspais("pdf", "--output", str(out))
            assert result.returncode == 0, f"stderr: {result.stderr}"
            assert out.exists(), "PDF file was not created"
            assert out.stat().st_size > 0, "PDF file is empty"
            # Check PDF magic bytes
            with open(out, "rb") as f:
                assert f.read(4) == b"%PDF"

    @requires_pandoc
    @requires_xelatex
    def test_REQ_p00080_F_generates_overview_pdf(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "overview.pdf"
            result = _run_elspais("pdf", "--overview", "--output", str(out))
            assert result.returncode == 0, f"stderr: {result.stderr}"
            assert out.exists()
            assert out.stat().st_size > 0
            with open(out, "rb") as f:
                assert f.read(4) == b"%PDF"
