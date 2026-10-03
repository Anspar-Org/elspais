"""The e2e tier refuses to run against a build of elspais other than this checkout's.

Test-runner mechanics: no product requirement governs which program the
suite spawns, so this file cites none.
"""

from __future__ import annotations

import os
from pathlib import Path

from tests.e2e.helpers import REPO_ROOT, build_identity_refusal, program_source


def _launcher(path: Path, shebang: str) -> Path:
    path.write_text(f"#!{shebang}\nraise SystemExit(0)\n")
    path.chmod(0o755)
    return path


def _interpreter_reporting(path: Path, source: str) -> Path:
    """An executable that answers the source question with ``source``."""
    path.write_text(f"#!/bin/sh\necho {source}\n")
    path.chmod(0o755)
    return path


def test_this_checkouts_launcher_is_accepted():
    launcher = REPO_ROOT / ".venv" / "bin" / "elspais"
    assert program_source(str(launcher)) == os.path.realpath(REPO_ROOT / "src" / "elspais")
    assert build_identity_refusal(str(launcher)) is None


def test_a_launcher_importing_another_build_is_refused(tmp_path):
    elsewhere = tmp_path / "other-checkout" / "src" / "elspais"
    interpreter = _interpreter_reporting(tmp_path / "python", str(elsewhere))
    launcher = _launcher(tmp_path / "elspais", str(interpreter))

    refusal = build_identity_refusal(str(launcher))

    assert refusal is not None
    assert str(elsewhere) in refusal
    assert str(REPO_ROOT / "src" / "elspais") in refusal


def test_a_launcher_through_env_is_read_like_env(tmp_path, monkeypatch):
    elsewhere = tmp_path / "other" / "elspais"
    bindir = tmp_path / "bin"
    bindir.mkdir()
    _interpreter_reporting(bindir / "fakepython", str(elsewhere))
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    launcher = _launcher(tmp_path / "elspais", "/usr/bin/env -S fakepython")

    assert program_source(str(launcher)) == str(elsewhere)


def test_a_program_whose_source_cannot_be_told_is_refused(tmp_path):
    binary = tmp_path / "elspais"
    binary.write_bytes(b"\x7fELF not a script")
    binary.chmod(0o755)

    refusal = build_identity_refusal(str(binary))

    assert refusal is not None
    assert "could not report" in refusal
