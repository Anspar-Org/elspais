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


def build_fixture_project(
    root: Path,
    config_overrides: dict | None = None,
    spec_files: dict[str, str] | None = None,
    code_files: dict[str, str] | None = None,
    test_files: dict[str, str] | None = None,
    extra_files: dict[str, str] | None = None,
    init_git: bool = True,
) -> Path:
    """Build a project directory for a shared e2e fixture.

    Args:
        root: Project root directory (e.g., from tmp_path_factory.mktemp).
        config_overrides: Kwargs passed to helpers.base_config().
        spec_files: {relative_path: content} for spec files.
        code_files: {relative_path: content} for code files.
        test_files: {relative_path: content} for test files.
        extra_files: {relative_path: content} for any other files.
        init_git: Whether to initialize a git repo and commit.

    Returns:
        The project root path.
    """
    from tests.e2e.helpers import base_config, write_config

    config = base_config(**(config_overrides or {}))
    write_config(root / ".elspais.toml", config)

    for files in [spec_files, code_files, test_files, extra_files]:
        if files:
            for rel_path, content in files.items():
                fpath = root / rel_path
                fpath.parent.mkdir(parents=True, exist_ok=True)
                fpath.write_text(content)

    # Ensure spec/ exists even if no spec_files
    (root / "spec").mkdir(exist_ok=True)

    if init_git:
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

    return root


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
