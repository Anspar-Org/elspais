"""Daemon management commands.

Provides ``elspais daemon restart`` — kills and respawns the
background daemon so it re-reads the ``.elspais.toml`` config file. A
restart holding unsaved in-memory mutations refuses until the caller
says what becomes of them: ``--persist`` saves them here with a
changelog reason, ``--discard-changes`` throws them away.

Also home to ``run_env``, which backs ``elspais mcp env``: the address a
client is told to use is the daemon's, so the knowledge of where to read
it belongs here rather than beside the client registration.
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
        "Usage: elspais daemon restart [--discard-changes | --persist [--message TEXT]]",
        file=sys.stderr,
    )
    return 1


# Implements: REQ-o00076-C, REQ-o00076-K
def run_env(args: argparse.Namespace) -> int:
    """Print the address of the daemon serving this working tree.

    A client that cannot read the daemon's record itself -- one that only
    expands environment variables -- learns the address this way, from a
    shell that can read it. Printed rather than exported because a
    process cannot set a variable in the shell that started it.
    """
    from elspais.mcp.daemon import ensure_daemon, get_daemon_info

    repo_root = find_git_root() or Path.cwd()
    port = None
    if getattr(args, "no_start", False):
        info = get_daemon_info(repo_root)
        port = info.get("port") if info else None
    else:
        try:
            port = ensure_daemon(repo_root)
        except RuntimeError as exc:
            print(f"# no daemon: {exc}", file=sys.stderr)

    if not port:
        print(
            "# No daemon is serving this working tree, so no address was printed.",
            file=sys.stderr,
        )
        return 1

    print(f"export ELSPAIS_MCP_URL=http://127.0.0.1:{port}/mcp")
    print(f"export ELSPAIS_MCP_PORT={port}")
    return 0


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
