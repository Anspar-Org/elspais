# Implements: REQ-d00249-H+I+J+K, REQ-d00315-A+G+H
"""``elspais test``: execute test targets and record their results, evaluating no check.

A project that splits its suite across parallel jobs runs ``elspais test``
in each job and ``elspais checks --expect ...`` once, over every recorded
result. A job then fails only for its own tests. A specification error fails
the single gate.

This command selects targets through :func:`plan_target_runs`, the
function ``elspais checks --run-tests`` calls. It executes each member's
targets through :func:`run_configured_targets`, which records each run's
fingerprint.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from elspais.config import find_git_root, get_config, validate_config


# Implements: REQ-d00249-N
def run(args: argparse.Namespace) -> int:
    from elspais.commands._scope import flag_values
    from elspais.commands.test_runner import (
        SelectionRefused,
        concurrency_refusal,
        describe_stale_only,
        not_fresh_targets,
        plan_target_runs,
        run_configured_targets,
        unrecorded_targets,
    )

    repo_root = find_git_root() or Path.cwd()
    try:
        raw_config = get_config(getattr(args, "config", None), start_path=Path.cwd())
        config = validate_config(raw_config)
    except Exception as exc:
        print(f"error: failed to load config: {exc}", file=sys.stderr)
        return 2

    # Implements: REQ-d00314-O+P
    concurrency = getattr(args, "concurrency", None)
    if concurrency is not None and concurrency < 1:
        print(f"error: {concurrency_refusal(concurrency)}", file=sys.stderr)
        return 2

    try:
        runs = plan_target_runs(
            config, repo_root, list(flag_values(args, "targets")), raw_config=raw_config
        )
    except SelectionRefused as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    # Implements: REQ-d00249-K
    lost = [run.spell(name) for run in runs for name in unrecorded_targets(run.config, run.only)]
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

    fail_fast = bool(getattr(args, "fail_fast", False))
    failed: list[str] = []
    executed = 0
    for target_run in runs:
        only = target_run.only
        # Implements: REQ-d00315-B+G+H
        # A stale-only run narrows the selection to the targets whose results
        # are not fresh. When all are fresh it executes nothing, and that is a
        # success.
        if getattr(args, "stale_only", False):
            only, carry = not_fresh_targets(target_run.config, target_run.repo_root, only)
            print(describe_stale_only(only, carry), file=sys.stderr)
        # Implements: REQ-d00249-N
        # Each member's targets execute under that member's root, with its
        # configuration, writing into its output area.
        results, _captured = run_configured_targets(
            target_run.config,
            target_run.repo_root,
            fail_fast=fail_fast,
            only=only,
            concurrency=concurrency,
        )
        executed += len(results)
        failed += [target_run.spell(r.name) for r in results if not r.succeeded]
        if fail_fast and failed:
            break

    # Implements: REQ-d00249-J
    if failed:
        print(f"{len(failed)} of {executed} target(s) failed: {', '.join(failed)}")
        return 1
    if not executed:
        print("no target executed: the results of every selected target are fresh")
        return 0
    print(f"{executed} target(s) passed")
    return 0
