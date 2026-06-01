# Verifies: REQ-d00252
"""End-to-end test for the ``Integrates:`` cross-repo reference (CUR-1419).

Drives the real ``elspais`` CLI against the ``e2e-integrates`` fixture
(``app`` consumer + ``library`` associate) to verify that a requirement
declaring ``**Integrates**: LIB-d00007`` resolves the federated reference
and passes ``checks`` cleanly when the associate is reachable.

The subprocess is invoked as ``python -m elspais`` with ``PYTHONPATH``
pointed at this worktree's ``src`` so the test exercises the worktree code
rather than any stale non-editable install on PATH.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

# Absolute path to this worktree's src/ so the subprocess imports the
# worktree code, not a stale installed copy.
REPO_SRC = Path(__file__).resolve().parents[2] / "src"
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "e2e-integrates"


def _git_init(root: Path) -> None:
    """Initialize a git repo with an initial commit so the CLI finds a root."""
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    subprocess.run(["git", "init", "-b", "main"], cwd=root, capture_output=True, env=env)
    subprocess.run(["git", "add", "."], cwd=root, capture_output=True, env=env)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, capture_output=True, env=env)


class TestIntegratesEndToEnd:
    """Validates REQ-d00252-D: consumer + associate checks pass end-to-end."""

    def test_REQ_d00252_D_app_checks_pass_with_associate(self, tmp_path):
        # Copy the fixture pair into a tmp dir; git init each repo so each is
        # its own git root (the CLI auto-detects the git root).
        dest = tmp_path / "e2e-integrates"
        shutil.copytree(FIXTURE, dest)
        library = dest / "library"
        app = dest / "app"
        _git_init(library)
        _git_init(app)

        env = {**os.environ, "PYTHONPATH": str(REPO_SRC)}
        result = subprocess.run(
            [sys.executable, "-m", "elspais", "checks"],
            cwd=app,
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )

        assert result.returncode == 0, (
            "elspais checks failed for the Integrates consumer with the "
            "library associate resolvable at ../library:\n"
            f"--- stdout ---\n{result.stdout}\n"
            f"--- stderr ---\n{result.stderr}"
        )
