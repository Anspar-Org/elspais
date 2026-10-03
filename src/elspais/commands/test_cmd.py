# Implements: REQ-d00249-H+I+J+K, REQ-d00315-A+G+H
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
        concurrency_refusal,
        describe_stale_only,
        executable_selection,
        not_fresh_targets,
        run_configured_targets,
        unrecorded_targets,
    )

    repo_root = find_git_root() or Path.cwd()
    try:
        config = validate_config(get_config(getattr(args, "config", None), start_path=Path.cwd()))
    except Exception as exc:
        print(f"error: failed to load config: {exc}", file=sys.stderr)
        return 2

    # Implements: REQ-d00314-O+P
    concurrency = getattr(args, "concurrency", None)
    if concurrency is not None and concurrency < 1:
        print(f"error: {concurrency_refusal(concurrency)}", file=sys.stderr)
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
            f"error: target(s) {', '.join(lost)} declare no `results` pattern. This "
            f"command evaluates no check and reads no output while a command runs, so "
            f"their results would reach nothing. Have each command write its results "
            f"into $ELSPAIS_TARGET_OUTPUT and declare the `results` pattern that "
            f"matches them.",
            file=sys.stderr,
        )
        return 2

    # Implements: REQ-d00315-B+G+H
    # A stale-only run narrows the selection to the targets whose results are
    # not fresh. When all are fresh it executes nothing, and that is a success.
    if getattr(args, "stale_only", False):
        only, carry = not_fresh_targets(config, repo_root, only)
        print(describe_stale_only(only, carry), file=sys.stderr)

    results, _captured = run_configured_targets(
        config,
        repo_root,
        fail_fast=bool(getattr(args, "fail_fast", False)),
        only=only,
        concurrency=concurrency,
    )

    # Implements: REQ-d00249-J
    failed = [r.name for r in results if not r.succeeded]
    if failed:
        print(f"{len(failed)} of {len(results)} target(s) failed: {', '.join(failed)}")
        return 1
    if not results:
        print("no target executed: the results of every selected target are fresh")
        return 0
    print(f"{len(results)} target(s) passed")
    return 0
