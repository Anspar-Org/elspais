# Implements: REQ-d00311-H+I
"""``elspais fingerprint start|finish TARGET``: record a run that elspais did not execute.

A git hook or a CI job that runs the tests of a target calls ``start`` before
the run. The hook or job calls ``finish`` after the run. Both actions use
:mod:`elspais.utilities.fingerprint`. ``elspais checks --run-tests`` uses the
same module. Consequently, every path computes the fingerprint in one way.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from elspais.config import find_git_root, get_config, validate_config


def run(args: argparse.Namespace) -> int:
    from elspais.utilities.fingerprint import RunNotStarted, finish_run, start_run

    action = getattr(args, "fingerprint_action", None)
    if action not in ("start", "finish"):
        print("Usage: elspais fingerprint {start,finish} TARGET", file=sys.stderr)
        return 1
    repo_root = find_git_root() or Path.cwd()
    config = validate_config(get_config(getattr(args, "config", None), repo_root))
    try:
        if action == "start":
            folder = start_run(repo_root, config, args.target)
            print(folder)
        else:
            fingerprint = finish_run(repo_root, config, args.target)
            changed = fingerprint.get("changed_during_run") or []
            if changed:
                print(
                    f"target {args.target}: inputs changed while it ran: "
                    f"{', '.join(changed[:5])}"
                    + (f" and {len(changed) - 5} more" if len(changed) > 5 else ""),
                    file=sys.stderr,
                )
    except KeyError as exc:
        print(f"error: {exc.args[0]}", file=sys.stderr)
        return 2
    except RunNotStarted as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0
