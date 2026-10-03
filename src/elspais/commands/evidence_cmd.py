# Implements: REQ-d00322-A+B+F+H+I
"""``elspais evidence write|verify``: the *Evidence Snapshot* of one test run.

``write`` derives the snapshot from the selected targets' own results and
writes it into the directory ``[scanning.test] evidence`` names. ``verify``
derives the same snapshot in memory and compares it with the one committed
there. Both select targets through :func:`plan_target_runs`, judge each
target's results through :func:`elspais.utilities.fingerprint.judge`, and
derive, render and compare through :mod:`elspais.utilities.evidence`.
"""

from __future__ import annotations

import argparse
import copy
import dataclasses
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from elspais.config import find_git_root, get_config, validate_config


def _freshness_refusals(
    repo_root: Path, config: Any, selected: list[str], spell: Callable[[str], str]
) -> list[str]:
    """Each selected target whose results cannot be held, with the reason."""
    from elspais.utilities.fingerprint import judge

    refusals = []
    for name in selected:
        verdict = judge(repo_root, config, name)
        if verdict.state == "fresh":
            continue
        reason = f" ({verdict.reason})" if verdict.reason else ""
        changed = f": {', '.join(verdict.changed[:5])}" if verdict.changed else ""
        refusals.append(f"target {spell(name)} results are {verdict.state}{reason}{changed}")
    return refusals


# Implements: REQ-d00322-B
def _ingestion_refusals(
    graph: Any, namespace: str, selected: list[str], spell: Callable[[str], str]
) -> list[str]:
    """Each selected target whose results the build could not read in full.

    A fresh fingerprint says the run finished; it does not say its results
    were read. A reporter nothing reads, a results file that will not parse,
    and a stream that ends inside a test each leave fewer results than the
    run produced, and a snapshot of them would hold that shorter run as a
    finished one. Coverage is not part of a snapshot, so a coverage fault
    refuses nothing. A fault naming no target is the committed snapshot
    itself, which the write replaces.
    """
    chosen = set(selected)
    refusals = []
    for fault in graph.ingestion_faults(namespace=namespace):
        if fault.target not in chosen or fault.stage == "coverage":
            continue
        where = f"{fault.path}:{fault.line}" if fault.path and fault.line else fault.path
        at = f" ({where})" if where else ""
        how = "read in part" if fault.partial else "not read"
        refusals.append(f"target {spell(fault.target)} results are {how}{at}: {fault.cause}")
    for unread in graph.unread_artifacts(namespace=namespace):
        if unread.target not in chosen or unread.artifact != "results":
            continue
        at = f" ({unread.path})" if unread.path else ""
        refusals.append(f"target {spell(unread.target)} results are {unread.reason}{at}")
    return sorted(set(refusals))


# Implements: REQ-d00322-A+B+D+F
def _derive(
    repo_root: Path,
    raw_config: dict[str, Any],
    config: Any,
    selected: list[str],
    facts: tuple[tuple[str, str], ...],
    spell: Callable[[str], str],
):
    """The snapshot of the selected targets' own results, with its report.

    The report is rendered from a build that reads the snapshot alone, so it
    depends on the snapshot and the specification and on nothing else the
    tree holds (REQ-d00322-F). The tree digest is computed once and returned
    beside the snapshot, so the caller can name the changes no commit holds.

    Raises `SnapshotRefused` where a selected target's results were not read
    in full (REQ-d00322-B), or cannot be held.
    """
    from elspais.commands._requests import TraceRequest
    from elspais.commands.trace import REPORT_PRESETS, render_trace
    from elspais.graph.factory import build_graph
    from elspais.utilities.evidence import (
        SnapshotRefused,
        derive_snapshot,
        render_files,
        tree_digest,
    )
    from elspais.utilities.fingerprint import output_root

    tree = tree_digest(repo_root, exclude=config.scanning.test.evidence)
    graph = build_graph(config=raw_config, repo_root=repo_root, fresh_targets=set(selected))
    unread = _ingestion_refusals(graph, config.project.namespace, selected, spell)
    if unread:
        raise SnapshotRefused(unread)
    snapshot = derive_snapshot(
        graph, repo_root, config, selected, facts, "", tree=tree, spell=spell
    )

    # The rendered snapshot is read from a scratch directory under the output
    # root: the configuration names a snapshot by a path inside the
    # repository, and the output root is never a target's input.
    scratch_root = output_root(repo_root, config)
    scratch_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".evidence-", dir=scratch_root) as scratch:
        for name, text in render_files(snapshot).items():
            if name != "TRACEABILITY.md":
                (Path(scratch) / name).write_text(text, encoding="utf-8", newline="\n")
        reading = copy.deepcopy(raw_config)
        reading.setdefault("scanning", {}).setdefault("test", {})["evidence"] = (
            Path(scratch).resolve().relative_to(repo_root.resolve()).as_posix()
        )
        # The report describes the snapshot's own run, so the selected
        # targets are that run's fresh targets, not a baseline carried in.
        evidence_graph = build_graph(
            config=reading, repo_root=repo_root, evidence_only=True, fresh_targets=set(selected)
        )
        report = render_trace(
            evidence_graph, raw_config, TraceRequest(), "markdown", REPORT_PRESETS["evidence"]
        )
    return dataclasses.replace(snapshot, report=report), tree


def _write(directory: Path, snapshot) -> None:
    from elspais.utilities.evidence import render_files

    directory.mkdir(parents=True, exist_ok=True)
    for name, text in render_files(snapshot).items():
        (directory / name).write_text(text, encoding="utf-8", newline="\n")


def run(args: argparse.Namespace) -> int:
    from elspais.commands._scope import flag_values
    from elspais.commands.test_runner import (
        SelectionRefused,
        plan_target_runs,
        run_configured_targets,
        unrecorded_targets,
    )
    from elspais.utilities.evidence import (
        SnapshotRefused,
        SnapshotUnreadable,
        compare,
        load_snapshot,
        parse_facts,
    )

    action = getattr(args, "evidence_action", None)
    if action not in ("write", "verify"):
        print(
            "Usage: elspais evidence {write,verify} [--targets ...] [--fact ...]",
            file=sys.stderr,
        )
        return 2
    executes = action == "verify" and bool(getattr(args, "run", False))

    root = find_git_root() or Path.cwd()
    try:
        root_config = get_config(getattr(args, "config", None), start_path=Path.cwd())
        root_typed = validate_config(root_config)
    except Exception as exc:
        print(f"error: failed to load config: {exc}", file=sys.stderr)
        return 2

    try:
        # write and verify read results another job may have left in a
        # target's output area, so a selected target needs no command of
        # its own; verify --run executes the targets, so there one must.
        runs = plan_target_runs(
            root_typed,
            root,
            list(flag_values(args, "targets")),
            raw_config=root_config,
            require_command=executes,
        )
        facts = parse_facts(list(flag_values(args, "fact")))
    except (SelectionRefused, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    # Implements: REQ-d00322-L, REQ-d00249-N
    # A snapshot describes one repository's tree. A selection naming a
    # member's targets writes or verifies that member's snapshot, in that
    # member's repository, with its configuration.
    if len(runs) > 1:
        print(
            "error: an Evidence Snapshot describes one repository, and the selection "
            f"names targets of {', '.join(r.namespace for r in runs)}. Select the "
            "targets of one repository.",
            file=sys.stderr,
        )
        return 2
    (chosen,) = runs
    repo_root, raw_config, config, only = (
        chosen.repo_root,
        chosen.raw_config,
        chosen.config,
        chosen.only,
    )
    directory = config.scanning.test.evidence
    if not directory:
        print(
            "error: no Evidence Snapshot directory is configured. Set "
            "scanning.test.evidence to the directory that holds it, for example "
            '[scanning.test] evidence = "test-evidence".',
            file=sys.stderr,
        )
        return 2
    selected = sorted(
        t.name
        for t in config.scanning.test.targets
        if t.reporter and (only is None or t.name in only)
    )

    if executes:
        # Implements: REQ-d00249-K
        # Only results on disk reach the snapshot, so a target that leaves
        # none would run and then be refused as absent.
        lost = unrecorded_targets(config, set(selected))
        if lost:
            print(
                f"error: target(s) {', '.join(chosen.spell(n) for n in lost)} declare no "
                f"`results` pattern, so a run leaves no results for the snapshot. Have "
                f"each command write its results into $ELSPAIS_TARGET_OUTPUT and declare "
                f"the `results` pattern that matches them.",
                file=sys.stderr,
            )
            return 2
        results, _captured = run_configured_targets(config, repo_root, only=set(selected))
        failed = [chosen.spell(r.name) for r in results if not r.succeeded]
        if failed:
            print(
                f"note: target(s) {', '.join(failed)} failed; comparing their results",
                file=sys.stderr,
            )

    # Implements: REQ-d00322-B
    # A snapshot describes a finished run of this tree, so a target whose
    # results are absent, stale or still being written is refused by name.
    # A target whose results the build could not read is refused in _derive.
    refusals = _freshness_refusals(repo_root, config, selected, chosen.spell)
    if refusals:
        for refusal in refusals:
            print(f"error: {refusal}", file=sys.stderr)
        return 2

    try:
        current, tree = _derive(repo_root, raw_config, config, selected, facts, chosen.spell)
    except SnapshotRefused as exc:
        for reason in exc.reasons:
            print(f"error: {reason}", file=sys.stderr)
        return 2

    if action == "write":
        if tree.uncommitted:
            print(
                "warning: the Evidence Snapshot describes a tree holding changes no "
                "commit holds, so it will not match a checkout of any commit: "
                + ", ".join(tree.uncommitted),
                file=sys.stderr,
            )
        _write(repo_root / directory, current)
        print(f"Evidence Snapshot written to {directory}")
        return 0

    # Implements: REQ-d00322-H+I
    try:
        committed = load_snapshot(repo_root / directory)
    except SnapshotUnreadable as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    differences = compare(committed, current, spell=chosen.spell)
    for difference in differences:
        print(f"{difference.kind}: {difference.detail}")
    if differences:
        print(f"The Evidence Snapshot in {directory} differs from the current results")
        return 1
    print(f"The Evidence Snapshot in {directory} matches the current results")
    return 0
