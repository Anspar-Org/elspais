"""Daemon management commands.

Currently provides ``elspais daemon restart`` — kills and respawns the
background daemon so it re-reads the ``.elspais.toml`` config file. In-
memory mutations are protected by default; callers opt in to discard
(``--force``) or save (``--persist``) them.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from elspais.config import find_git_root


def run(args: argparse.Namespace) -> int:
    action = getattr(args, "daemon_action", None)
    if action == "restart":
        return _run_restart(args)
    print("Usage: elspais daemon restart [--force | --persist]", file=sys.stderr)
    return 1


def _run_restart(args: argparse.Namespace) -> int:
    from elspais.mcp.daemon import restart_daemon

    repo_root = find_git_root() or Path.cwd()
    force = bool(getattr(args, "force", False))
    persist = bool(getattr(args, "persist", False))

    result = restart_daemon(repo_root, force=force, persist=persist)

    if result.get("success"):
        msg = result.get("message", "")
        if msg:
            print(msg)
        return 0

    err = result.get("error", "restart failed")
    print(f"Error: {err}", file=sys.stderr)
    return 1
