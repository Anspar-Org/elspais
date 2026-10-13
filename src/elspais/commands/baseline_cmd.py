# Implements: REQ-d00333-E+F, REQ-d00311-H+I
"""``elspais baseline pack|fetch``: carry the recorded runs of test targets between trees.

``pack`` writes the selected targets' output areas into one archive that a
CI job publishes wherever the project keeps it. ``fetch`` runs the command
the project declares to obtain such an archive, and adopts each packed run
where this tree holds none. Both use :mod:`elspais.utilities.baseline`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from elspais.config import find_git_root, get_config, validate_config


def _pack(args: argparse.Namespace, repo_root: Path, raw_config, config) -> int:
    from elspais.commands._scope import flag_values
    from elspais.commands.test_runner import SelectionRefused, plan_target_runs
    from elspais.utilities.baseline import BaselineRefused, pack

    try:
        runs = plan_target_runs(
            config,
            repo_root,
            list(flag_values(args, "targets")),
            raw_config=raw_config,
            require_command=False,
        )
    except SelectionRefused as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if len(runs) != 1 or not runs[0].is_root:
        print(
            "error: a packed baseline holds the runs of this repository's targets; "
            "select targets without a namespace",
            file=sys.stderr,
        )
        return 2
    (chosen,) = runs
    selected = sorted(
        t.name for t in config.scanning.test.targets if chosen.only is None or t.name in chosen.only
    )
    try:
        manifest = pack(repo_root, config, selected, Path(args.out))
    except BaselineRefused as exc:
        for reason in exc.reasons:
            print(f"error: {reason}", file=sys.stderr)
        return 1
    print(
        f"packed {', '.join(manifest['targets'])} at commit {manifest['commit'][:12]} "
        f"into {args.out}"
    )
    return 0


def _fetch(args: argparse.Namespace, repo_root: Path, config) -> int:
    from elspais.utilities.baseline import BaselineRefused, fetch

    try:
        manifest, outcomes = fetch(repo_root, config, replace=bool(getattr(args, "replace", False)))
    except BaselineRefused as exc:
        for reason in exc.reasons:
            print(f"error: {reason}", file=sys.stderr)
        print("error: no output area was changed", file=sys.stderr)
        return 1
    print(
        f"baseline packed by elspais {manifest.get('elspais', '?')} at commit "
        f"{str(manifest.get('commit', ''))[:12] or '?'}"
    )
    for outcome in outcomes:
        detail = f": {outcome.detail}" if outcome.detail else ""
        stream = sys.stderr if outcome.outcome == "refused" else sys.stdout
        print(f"  {outcome.target}: {outcome.outcome}{detail}", file=stream)
    return 1 if any(o.outcome == "refused" for o in outcomes) else 0


def run(args: argparse.Namespace) -> int:
    action = getattr(args, "baseline_action", None)
    if action not in ("pack", "fetch"):
        print(
            "Usage: elspais baseline pack --out FILE [--targets ...] | "
            "elspais baseline fetch [--replace]",
            file=sys.stderr,
        )
        return 2
    repo_root = find_git_root() or Path.cwd()
    try:
        raw_config = get_config(getattr(args, "config", None), repo_root)
        config = validate_config(raw_config)
    except Exception as exc:
        print(f"error: failed to load config: {exc}", file=sys.stderr)
        return 2
    if action == "pack":
        return _pack(args, repo_root, raw_config, config)
    return _fetch(args, repo_root, config)
