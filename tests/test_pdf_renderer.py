# Verifies: REQ-p00080-A, REQ-p00080-C
"""Tests for the pandoc PDF renderer.

Validates REQ-p00080-A (the pdf CLI invokes pandoc) and REQ-p00080-C
(generated PDF can include image resources). Specifically exercises the
``resource_paths`` kwarg that controls pandoc's ``--resource-path`` flag,
which is required when assembled markdown references images by relative
path -- without it, pandoc would resolve relatives against the temp
markdown file's directory and miss every image.
"""

from __future__ import annotations

import os
import sys
import types
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from elspais.pdf.renderer import render_pdf


def _fake_completed(returncode: int = 0, stderr: str = "") -> types.SimpleNamespace:
    """Build a minimal stand-in for ``subprocess.CompletedProcess``."""
    return types.SimpleNamespace(returncode=returncode, stderr=stderr, stdout="")


class TestResourcePathFlag:
    """Validates REQ-p00080-C: --resource-path forwarded to pandoc."""

    def test_REQ_p00080_C_no_resource_paths_omits_flag(self, tmp_path):
        """When resource_paths is None, the pandoc command must not include
        a --resource-path argument at all.
        """
        captured = {}

        def fake_run(cmd, *args, **kwargs):
            captured["cmd"] = list(cmd)
            return _fake_completed()

        # Use the bundled latex template so the existence check passes.
        bundled = (
            Path(__file__).parent.parent / "src" / "elspais" / "pdf" / "templates" / "elspais.latex"
        )
        assert bundled.exists(), "Bundled template fixture missing"

        with patch("elspais.pdf.renderer.subprocess.run", side_effect=fake_run):
            rc = render_pdf(
                "# x",
                output_path=tmp_path / "o.pdf",
                template=bundled,
            )

        assert rc == 0
        cmd = captured["cmd"]
        # No element starting with --resource-path should appear.
        matches = [a for a in cmd if isinstance(a, str) and a.startswith("--resource-path")]
        assert matches == [], f"Expected no --resource-path arg, got: {matches}"

    def test_REQ_p00080_C_resource_paths_joined_with_os_pathsep(self, tmp_path):
        """When resource_paths is provided, pandoc receives exactly one
        --resource-path=<os.pathsep-joined> argument.
        """
        captured = {}

        def fake_run(cmd, *args, **kwargs):
            captured["cmd"] = list(cmd)
            return _fake_completed()

        bundled = (
            Path(__file__).parent.parent / "src" / "elspais" / "pdf" / "templates" / "elspais.latex"
        )
        assert bundled.exists(), "Bundled template fixture missing"

        paths = [Path("/a"), Path("/b/spec")]
        expected = f"--resource-path=/a{os.pathsep}/b/spec"

        with patch("elspais.pdf.renderer.subprocess.run", side_effect=fake_run):
            rc = render_pdf(
                "# x",
                output_path=tmp_path / "o.pdf",
                template=bundled,
                resource_paths=paths,
            )

        assert rc == 0
        cmd = captured["cmd"]
        matches = [a for a in cmd if isinstance(a, str) and a.startswith("--resource-path")]
        assert matches == [expected], (
            f"Expected exactly one --resource-path arg equal to {expected!r}, got: {matches}"
        )

    def test_REQ_p00080_C_empty_resource_paths_omits_flag(self, tmp_path):
        """An empty list (falsy) should be treated the same as None and
        omit the flag entirely -- pandoc rejects an empty --resource-path.
        """
        captured = {}

        def fake_run(cmd, *args, **kwargs):
            captured["cmd"] = list(cmd)
            return _fake_completed()

        bundled = (
            Path(__file__).parent.parent / "src" / "elspais" / "pdf" / "templates" / "elspais.latex"
        )

        with patch("elspais.pdf.renderer.subprocess.run", side_effect=fake_run):
            rc = render_pdf(
                "# x",
                output_path=tmp_path / "o.pdf",
                template=bundled,
                resource_paths=[],
            )

        assert rc == 0
        cmd = captured["cmd"]
        matches = [a for a in cmd if isinstance(a, str) and a.startswith("--resource-path")]
        assert matches == [], f"Expected no --resource-path arg, got: {matches}"


class TestPandocWarningsSurfaced:
    """Validates REQ-p00080-K: pandoc's own degradation warnings reach the
    operator instead of being swallowed on a successful exit.

    Pandoc emits "[WARNING] Could not fetch resource X: replacing image
    with description" and still exits 0, so gating the stderr echo on a
    non-zero return code hides every dropped image.
    """

    # Verifies: REQ-p00080-K
    def test_REQ_p00080_K_pandoc_stderr_echoed_on_success(self, tmp_path, capsys):
        """A warning emitted alongside rc=0 is written to sys.stderr."""
        warning = (
            "[WARNING] Could not fetch resource missing/nope.png: replacing image with description"
        )

        bundled = (
            Path(__file__).parent.parent / "src" / "elspais" / "pdf" / "templates" / "elspais.latex"
        )
        assert bundled.exists(), "Bundled template fixture missing"

        def fake_run(cmd, *args, **kwargs):
            return _fake_completed(returncode=0, stderr=warning + "\n")

        with patch("elspais.pdf.renderer.subprocess.run", side_effect=fake_run):
            rc = render_pdf(
                "# x",
                output_path=tmp_path / "o.pdf",
                template=bundled,
            )

        captured = capsys.readouterr()
        assert rc == 0
        assert "Could not fetch resource missing/nope.png" in captured.err

    # Verifies: REQ-p00080-K
    def test_REQ_p00080_K_silent_pandoc_run_emits_nothing(self, tmp_path, capsys):
        """Regression guard: an empty pandoc stderr produces no output."""
        bundled = (
            Path(__file__).parent.parent / "src" / "elspais" / "pdf" / "templates" / "elspais.latex"
        )

        with patch(
            "elspais.pdf.renderer.subprocess.run",
            side_effect=lambda cmd, *a, **k: _fake_completed(returncode=0, stderr=""),
        ):
            rc = render_pdf("# x", output_path=tmp_path / "o.pdf", template=bundled)

        captured = capsys.readouterr()
        assert rc == 0
        assert captured.err == ""


class TestUnfetchedResourceCollection:
    """Validates REQ-p00080-K: resources pandoc itself could not fetch are
    handed back to the caller, so a degradation only pandoc saw can still be
    disclosed.

    The assembler judges the reference shapes it understands. Everything else
    -- a format outside its pattern, a reference-style link resolved only at
    parse time -- reaches pandoc unexamined, and pandoc drops it with a
    warning and exits 0. The renderer is the only place that degradation is
    visible, so it collects the resource names for the caller that writes the
    completion report; the return value stays an exit code, because every
    existing caller reads it as one.
    """

    # Verifies: REQ-p00080-K
    def test_REQ_p00080_K_unfetched_collector_receives_every_reported_resource(
        self, tmp_path, capsys
    ):
        """Two warnings put two resource names in the caller's list, in the
        order pandoc reported them.
        """
        stderr = (
            "[WARNING] Could not fetch resource art/photo.webp: "
            "replacing image with description\n"
            "[WARNING] Could not fetch resource figures/chart: "
            "replacing image with description\n"
        )
        bundled = (
            Path(__file__).parent.parent / "src" / "elspais" / "pdf" / "templates" / "elspais.latex"
        )

        unfetched: list[str] = []
        with patch(
            "elspais.pdf.renderer.subprocess.run",
            side_effect=lambda cmd, *a, **k: _fake_completed(returncode=0, stderr=stderr),
        ):
            rc = render_pdf(
                "# x",
                output_path=tmp_path / "o.pdf",
                template=bundled,
                unfetched=unfetched,
            )

        assert rc == 0, "the collector must not change the exit-code contract"
        assert unfetched == ["art/photo.webp", "figures/chart"], (
            f"expected both unfetchable resources, in report order, got {unfetched!r}"
        )

    # Verifies: REQ-p00080-K
    def test_REQ_p00080_K_unfetched_collector_stays_empty_on_a_clean_compile(
        self, tmp_path, capsys
    ):
        """No fetch warnings means nothing is appended -- an empty list is the
        signal that the document is whole.
        """
        bundled = (
            Path(__file__).parent.parent / "src" / "elspais" / "pdf" / "templates" / "elspais.latex"
        )

        unfetched: list[str] = []
        with patch(
            "elspais.pdf.renderer.subprocess.run",
            side_effect=lambda cmd, *a, **k: _fake_completed(returncode=0, stderr=""),
        ):
            rc = render_pdf(
                "# x",
                output_path=tmp_path / "o.pdf",
                template=bundled,
                unfetched=unfetched,
            )

        assert rc == 0
        assert unfetched == [], f"a clean compile reported omissions: {unfetched!r}"


class TestSuccessfulCompileNoiseFilter:
    """Validates REQ-p00080-K: on a successful compile the operator is shown
    pandoc's diagnostics and nothing else.

    The LaTeX engine narrates its font-fallback search on every healthy run,
    tens of lines ending in wording as alarming as ``! Emergency stop.``. Echo
    that alongside a genuine ``[WARNING] Could not fetch resource ...`` and the
    one line that means the document is short an image is indistinguishable
    from the routine chatter -- disclosure that cannot be read is not
    disclosure. A failed compile is the opposite case: the cause is somewhere
    in that chatter, so it is passed through whole.
    """

    # Verifies: REQ-p00080-K
    def test_REQ_p00080_K_success_echoes_pandoc_diagnostics_only(self, tmp_path, capsys):
        """rc 0: the [WARNING] line reaches stderr, the engine noise does not."""
        stderr = (
            "kpathsea: Running mktexmf Comic\n"
            "[WARNING] Could not fetch resource art/photo.webp: "
            "replacing image with description\n"
            "! Emergency stop.\n"
            "Transcript written on texput.log.\n"
        )
        bundled = (
            Path(__file__).parent.parent / "src" / "elspais" / "pdf" / "templates" / "elspais.latex"
        )

        with patch(
            "elspais.pdf.renderer.subprocess.run",
            side_effect=lambda cmd, *a, **k: _fake_completed(returncode=0, stderr=stderr),
        ):
            rc = render_pdf("# x", output_path=tmp_path / "o.pdf", template=bundled)

        captured = capsys.readouterr()
        assert rc == 0
        assert "Could not fetch resource art/photo.webp" in captured.err
        assert "Emergency stop" not in captured.err, (
            f"engine noise drowned the real warning on a successful compile: {captured.err!r}"
        )
        assert "kpathsea" not in captured.err
        assert "Transcript written" not in captured.err

    # Verifies: REQ-p00080-K
    def test_REQ_p00080_K_failure_echoes_the_whole_stderr(self, tmp_path, capsys):
        """rc != 0: every line is passed through, noise included, because the
        cause of the failure may be any one of them.
        """
        stderr = (
            "kpathsea: Running mktexmf Comic\n"
            "[ERROR] Error producing PDF.\n"
            "! Emergency stop.\n"
            "Transcript written on texput.log.\n"
        )
        bundled = (
            Path(__file__).parent.parent / "src" / "elspais" / "pdf" / "templates" / "elspais.latex"
        )

        with patch(
            "elspais.pdf.renderer.subprocess.run",
            side_effect=lambda cmd, *a, **k: _fake_completed(returncode=43, stderr=stderr),
        ):
            rc = render_pdf("# x", output_path=tmp_path / "o.pdf", template=bundled)

        captured = capsys.readouterr()
        assert rc == 43
        for fragment in (
            "kpathsea: Running mktexmf Comic",
            "[ERROR] Error producing PDF.",
            "! Emergency stop.",
            "Transcript written on texput.log.",
        ):
            assert fragment in captured.err, (
                f"a failed compile must surrender its whole stderr; {fragment!r} "
                f"was dropped from {captured.err!r}"
            )
