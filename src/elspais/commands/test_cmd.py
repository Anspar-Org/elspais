# Implements: REQ-d00249-H+I+J+K
"""``elspais test``: execute test targets and record their results, evaluating no check.

A project that splits its suite across parallel jobs runs ``elspais test``
in each job and ``elspais checks --expect ...`` once, over every recorded
result. A job then fails only for its own tests. A specification error fails
the single gate.

This command selects targets through :func:`executable_selection`, the
function ``elspais checks --run-tests`` calls. It executes them through
:func:`run_configured_targets`, which records each run's fingerprint.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from elspais.config import find_git_root, get_config, validate_config


def run(args: argparse.Namespace) -> int:
    from elspais.commands._scope import flag_values
    from elspais.commands.test_runner import (
        SelectionRefused,
        executable_selection,
        run_configured_targets,
        unrecorded_targets,
    )

    repo_root = find_git_root() or Path.cwd()
    try:
        config = validate_config(get_config(getattr(args, "config", None), start_path=Path.cwd()))
    except Exception as exc:
        print(f"error: failed to load config: {exc}", file=sys.stderr)
        return 2

    try:
        only = executable_selection(config, list(flag_values(args, "targets")))
    except SelectionRefused as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    # Implements: REQ-d00249-K
    lost = unrecorded_targets(config, only)
    if lost:
        print(
            f"error: target(s) {', '.join(lost)} declare no `results` pattern, and "
            f"their reporter reads the command's output. This command evaluates no "
            f"check, so their results would reach nothing. Have each command write "
            f"its results into $ELSPAIS_TARGET_OUTPUT and declare the `results` "
            f"pattern that matches them, or run `elspais checks --run-tests`, which "
            f"reads the output while the command runs.",
            file=sys.stderr,
        )
        return 2

    results, _captured = run_configured_targets(
        config, repo_root, fail_fast=bool(getattr(args, "fail_fast", False)), only=only
    )

    # Implements: REQ-d00249-J
    failed = [r.name for r in results if not r.succeeded]
    if failed:
        print(f"{len(failed)} of {len(results)} target(s) failed: {', '.join(failed)}")
        return 1
    print(f"{len(results)} target(s) passed")
    return 0
