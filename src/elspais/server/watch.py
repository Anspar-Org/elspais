# Implements: REQ-d00313-A+B+D, REQ-d00311-R
"""The files a served graph was built from, and which of them changed since.

A serving process answers from a graph it built earlier. It judges that graph
current against the files here and nowhere else, so the rebuild decision and
the staleness it reports cannot disagree about what was watched.

The set covers every member of the federation. For each member it holds the
configuration documents, the files the spec, code and test kinds select, the
files of the Evidence Snapshot it names, and the output area of each test
target: the result fingerprint of its run, its results and its coverage. The
selection is the build's own (``scan_plan`` and ``select_files``), asked again
at each snapshot, so a new file the selection admits counts, a scanned
directory created after the build included, and a file it skips or declines
never does.

The environment probes the graph's judgements ran are watched too, but never
by modification time: a toolchain changes without touching a file. Only
:func:`environment_changes` probes them again, and only when a caller asks,
so polling never pays for a probe.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from glob import glob
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class OutputArea:
    """The output area of one test target, as a served graph reads it.

    Attributes:
        folder: The output area.
        patterns: The results pattern and the coverage path, each joined to
            the folder.
    """

    folder: Path
    patterns: tuple[str, ...]


@dataclass(frozen=True)
class ProbeWatch:
    """One environment probe of one test target, as a served graph's judgement ran it."""

    target: str
    probe: Any


@dataclass(frozen=True)
class WatchSet:
    """What a served graph was built from.

    Attributes:
        members: Each member's root with its configuration. The scanning
            kinds are planned from it at each snapshot, so a file a kind
            selects counts, a new file included.
        files: Named files, counted whether or not they exist yet.
        areas: The output area of every test target of every member.
        probes: Every environment probe of every test target of every member.
    """

    members: tuple[tuple[Path, dict[str, Any]], ...]
    files: tuple[Path, ...]
    areas: tuple[OutputArea, ...]
    probes: tuple[ProbeWatch, ...] = ()


def watch_set(members: Iterable[tuple[Path, dict[str, Any]]]) -> WatchSet:
    """Return the files a graph was built from, given the root and configuration of each member."""
    from elspais.config import config_document_candidates, validate_config
    from elspais.utilities.coverage import RECORD_NAME
    from elspais.utilities.evidence import SNAPSHOT_FILES, TIMINGS_FILE
    from elspais.utilities.fingerprint import (
        RETAINED_RESULTS_NAME,
        declared_probes,
        target_folder,
    )

    planned: list[tuple[Path, dict[str, Any]]] = []
    files: list[Path] = []
    areas: list[OutputArea] = []
    probes: list[ProbeWatch] = []
    for repo_root, config in members:
        root = Path(repo_root)
        planned.append((root, config or {}))
        files.extend(config_document_candidates(root / ".elspais.toml"))
        typed = validate_config(config or {})
        # Implements: REQ-d00313-A, REQ-d00322-J
        # A member naming an Evidence Snapshot reads its results from the
        # snapshot's files wherever a target has none of its own, so those
        # files are build inputs, counted whether or not they exist yet.
        if typed.scanning.test.evidence and typed.scanning.test.targets:
            directory = root / typed.scanning.test.evidence
            files.extend(directory / name for name in (*SNAPSHOT_FILES, TIMINGS_FILE))
        for target in typed.scanning.test.targets:
            folder = target_folder(root, typed, target.name)
            # Implements: REQ-d00333-A, REQ-d00334-A
            # The Retained Results a run writes are results the build reads,
            # as the target's own are. Line coverage is read from its record
            # alone, so the record is watched and the tool's file is not.
            record = RECORD_NAME if target.coverage else ""
            named = (target.results, record, RETAINED_RESULTS_NAME)
            patterns = tuple(str(folder / p) for p in named if p)
            areas.append(OutputArea(folder=folder, patterns=patterns))
            probes.extend(ProbeWatch(target.name, p) for p in declared_probes(root, target))
    return WatchSet(
        members=tuple(planned), files=tuple(files), areas=tuple(areas), probes=tuple(probes)
    )


def _inside(path: Path, folder: Path) -> bool:
    try:
        path.relative_to(folder)
    except ValueError:
        return False
    return True


def _mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def snapshot(watch: WatchSet) -> dict[str, float]:
    """Return the modification time of every file in *watch* that exists now."""
    from elspais.graph.factory import kind_files, scan_plan
    from elspais.utilities.fingerprint import FINGERPRINT_NAME

    folders = [area.folder.resolve() for area in watch.areas]
    found: dict[str, float] = {}
    scans = [(root, kind) for root, config in watch.members for kind in scan_plan(config, root)]
    for root, kind in scans:
        selected = kind_files(root, kind)
        for f in selected:
            # An output area inside a scanned directory is watched as an area.
            if any(_inside(f, folder) for folder in folders):
                continue
            if (when := _mtime(f)) is not None:
                found[str(f)] = when
    for f in watch.files:
        if f.is_file() and (when := _mtime(f)) is not None:
            found[str(f)] = when
    for area in watch.areas:
        candidates = [area.folder / FINGERPRINT_NAME]
        for pattern in area.patterns:
            candidates.extend(Path(m) for m in glob(pattern, recursive=True))
        for f in candidates:
            if f.is_file() and (when := _mtime(f)) is not None:
                found[str(f)] = when
    return found


def changed_files(watch: WatchSet, recorded: dict[str, float]) -> list[Path]:
    """Return the files of *watch* that changed, appeared or disappeared since *recorded*.

    While a run of a target is in progress, only its result fingerprint counts:
    the run writes its results and coverage for as long as it runs, and the
    fingerprint changes when the run ends (REQ-d00313-D).
    """
    from elspais.utilities.fingerprint import FINGERPRINT_NAME, run_in_progress

    running = [
        area.folder.resolve() for area in watch.areas if run_in_progress(area.folder) is not None
    ]
    current = snapshot(watch)
    changed: list[Path] = []
    for key in sorted(set(recorded) | set(current)):
        if recorded.get(key) == current.get(key):
            continue
        path = Path(key)
        if any(
            _inside(path.resolve(), folder) and path.name != FINGERPRINT_NAME for folder in running
        ):
            continue
        changed.append(path)
    return changed


# Implements: REQ-d00311-R
def environment_changes(
    watch: WatchSet, recorded: dict[tuple[str, str], str]
) -> tuple[list[str], dict[tuple[str, str], str]]:
    """Probe the environment again; name each probe whose answer differs from *recorded*.

    *recorded* maps a probe's key to the digest the served graph's judgements
    saw. A probe the build never ran is not watched. Each distinct probe runs
    once. Returns the changes and the digests just measured, so a rebuild
    takes them rather than probing again.
    """
    from elspais.utilities.fingerprint import input_label

    now: dict[tuple[str, str], str] = {}
    changes: list[str] = []
    for watched in watch.probes:
        key = watched.probe.key
        if key not in recorded:
            continue
        if key not in now:
            now[key] = watched.probe.digest()
        if now[key] != recorded[key]:
            changes.append(f"target {watched.target}: {input_label(watched.probe.entry)} changed")
    return changes, now


# Implements: REQ-d00313-C
def graph_predates(holder: Any) -> list[str]:
    """Name each file the graph a holder serves predates, for a reader.

    A path inside the serving repository is given relative to it, and any
    other path in full. Empty where the holder's process watches nothing.
    """
    changed = getattr(holder, "graph_predates", None)
    if changed is None:
        return []
    root = Path(holder.get("working_dir") or ".").resolve()
    named: list[str] = []
    for path in changed():
        try:
            named.append(str(path.resolve().relative_to(root)))
        except ValueError:
            named.append(str(path))
    # Implements: REQ-d00311-R
    # A changed environment the process saw and could not rebuild for, because
    # it holds pending mutations.
    environment = getattr(holder, "environment_predates", None)
    return sorted(named) + (list(environment()) if environment is not None else [])
