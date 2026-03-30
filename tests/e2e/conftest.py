# Verifies: REQ-p00013-B
"""Shared fixtures and helpers for end-to-end CLI tests.

Provides subprocess helpers, path constants, and skip markers.
"""

import os
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


def run_elspais(
    *args: str,
    cwd: str | Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    """Run elspais as a subprocess and return the CompletedProcess."""
    if _ELSPAIS is None:
        pytest.skip("elspais CLI not found on PATH")
    run_env = None
    if env is not None:
        run_env = {**os.environ, **env}
    return subprocess.run(
        [_ELSPAIS, *args],
        capture_output=True,
        text=True,
        cwd=cwd or REPO_ROOT,
        timeout=120,
        env=run_env,
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


@pytest.fixture(autouse=True, scope="session")
def _warm_daemon():
    """Pre-start the daemon for REPO_ROOT so global-scope tests are fast.

    Without this, the first CLI invocation pays ~3s for daemon auto-start.
    With this, the daemon starts once and all subsequent calls hit it in ~0.3s.
    """
    try:
        from elspais.config import find_git_root
        from elspais.mcp.daemon import ensure_daemon

        repo_root = find_git_root()
        if repo_root:
            ensure_daemon(repo_root)
    except Exception:
        pass
    yield


def _git_init(root: Path) -> None:
    """Initialize a git repo with an initial commit."""
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    subprocess.run(["git", "init"], cwd=root, capture_output=True, env=env)
    subprocess.run(["git", "add", "."], cwd=root, capture_output=True, env=env)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, capture_output=True, env=env)


def load_fixture(fixture_name: str, dest: Path) -> Path:
    """Copy an on-disk fixture to dest (in /tmp), git init, return dest.

    Every e2e test runs against a copy in /tmp — never inside the repo tree.
    """
    src = FIXTURES_DIR / fixture_name
    for item in src.iterdir():
        if item.is_dir():
            shutil.copytree(item, dest / item.name)
        else:
            shutil.copy2(item, dest / item.name)
    _git_init(dest)
    return dest


def load_associated_fixture(dest: Path) -> Path:
    """Copy the e2e-associated fixture, git init each repo, return core root."""
    src = FIXTURES_DIR / "e2e-associated"
    shutil.copytree(src, dest, dirs_exist_ok=True)
    for repo_dir in (dest / "core", dest / "alpha", dest / "beta"):
        _git_init(repo_dir)
    return dest / "core"


def ensure_fixture_daemon(root: Path) -> None:
    """Start a daemon for a fixture project if cli_ttl allows."""
    try:
        from elspais.mcp.daemon import ensure_daemon

        ensure_daemon(root)
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _cleanup_daemon(tmp_path):
    """Stop any daemon started during the test.

    E2e tests may auto-start per-project daemons in temp directories.
    This fixture ensures they are cleaned up to prevent zombie processes.
    """
    yield
    try:
        from elspais.mcp.daemon import stop_daemon

        for daemon_json in tmp_path.rglob(".elspais/daemon.json"):
            try:
                stop_daemon(daemon_json.parent.parent)
            except Exception:
                pass
    except Exception:
        pass
