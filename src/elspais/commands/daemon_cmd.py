"""Daemon management commands.

Currently provides ``elspais daemon`` — kills and respawns the
background daemon so it re-reads the ``.elspais.toml`` config file. A
restart holding unsaved in-memory mutations refuses until the caller
says what becomes of them: ``--persist`` saves them here with a
changelog reason, ``--discard-changes`` throws them away.
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
    print(
        "Usage: elspais daemon [--discard-changes | --persist [--message TEXT]]",
        file=sys.stderr,
    )
    return 1


def _run_restart(args: argparse.Namespace) -> int:
    from elspais.mcp.daemon import restart_daemon

    repo_root = find_git_root() or Path.cwd()
    discard_changes = bool(getattr(args, "discard_changes", False))
    persist = bool(getattr(args, "persist", False))
    message = getattr(args, "message", None)

    result = restart_daemon(
        repo_root,
        discard_changes=discard_changes,
        persist=persist,
        message=message,
    )

    if result.get("success"):
        msg = result.get("message", "")
        if msg:
            print(msg)
        return 0

    err = result.get("error", "restart failed")
    print(f"Error: {err}", file=sys.stderr)
    return 1
