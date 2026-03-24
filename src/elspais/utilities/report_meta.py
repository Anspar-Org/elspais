# Implements: REQ-p00006-A
"""Shared report metadata for all output formats.

Provides a consistent metadata dict (version, date, source identity)
that any report renderer can include in its output.
"""
from __future__ import annotations

import socket
from datetime import datetime, timezone
from pathlib import Path


def report_metadata(repo_root: Path | None = None) -> dict[str, str]:
    """Build metadata dict for report output.

    Returns a dict with:
        version: elspais semver (e.g. "0.111.93")
        date: ISO 8601 date (e.g. "2026-03-24")
        source: branch name, commit hash, or machine:path

    The source field follows this precedence:
        1. branch name (if on a branch)
        2. commit hash (if detached HEAD with clean working tree)
        3. hostname:path (if not a git repo)
    """
    from elspais import __version__

    meta: dict[str, str] = {
        "version": __version__,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }

    if repo_root is None:
        from elspais.config import find_git_root

        repo_root = find_git_root()

    if repo_root is not None:
        from elspais.utilities.git import get_current_branch, get_current_commit

        branch = get_current_branch(repo_root)
        if branch:
            meta["source"] = branch
        else:
            commit = get_current_commit(repo_root)
            meta["source"] = commit if commit else str(repo_root)
    else:
        meta["source"] = f"{socket.gethostname()}:{Path.cwd()}"

    return meta


def format_meta_line(meta: dict[str, str]) -> str:
    """Format metadata as a single parenthesized line for text output.

    Example: (elspais 0.111.93, 2026-03-24, branch: main)
    """
    parts = [f"elspais {meta['version']}", meta["date"]]
    source = meta.get("source")
    if source:
        parts.append(source)
    return f"({', '.join(parts)})"
