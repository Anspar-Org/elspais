# Implements: REQ-d00311-A+B+C+D+I+J+K+L+M+N, REQ-d00312-A+B+D
"""Record the fingerprint of a test target's run, and judge the freshness of its results.

Terms:

- An input is a file that the results of a test target depend on.
- The output area of a target is the directory ``<output_root>/<name>``.
  The command of the target writes its results and coverage there.
- A fingerprint is the record of one run of a target. The record holds a
  manifest: the path and the content digest of each input.

A run writes its fingerprint into the output area when the run starts. The
results are fresh while the manifest matches the inputs on disk. The manifest
holds one digest for each input. Consequently, a stale finding can name the
input that changed.

:func:`elspais.graph.file_selection.select_files` selects the inputs. Scans use
the same function. Consequently, a pattern has one meaning in every context.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from glob import glob
from pathlib import Path
from typing import Any

#: The name of the fingerprint file in the output area.
RECORD_NAME = ".elspais-run.json"

#: The environment variable that holds the path of the output area for the command.
OUTPUT_ENV = "ELSPAIS_TARGET_OUTPUT"

_RECORD_VERSION = 1


@dataclass(frozen=True)
class Freshness:
    """The freshness of the results of one target.

    ``state`` is ``"fresh"``, ``"stale"``, ``"absent"`` or ``"running"``.
    ``"absent"`` means that no results are on disk. The missing-results check
    reports that case. ``"running"`` means that a run of the target started
    and recorded no end. ``record`` then holds the record of that run.
    ``reason`` holds ``"no-fingerprint"``, ``"changed"`` or
    ``"changed-during-run"`` for stale results. Otherwise ``reason`` is empty.
    ``changed`` names the inputs that differ.
    """

    target: str
    state: str
    reason: str = ""
    changed: tuple[str, ...] = ()
    record: dict[str, Any] = field(default_factory=dict)


def _typed(config: Any) -> Any:
    """Return the typed configuration from a dict or a schema model."""
    if isinstance(config, dict):
        from elspais.config import validate_config

        return validate_config(config)
    return config


def output_root(repo_root: Path, config: Any) -> Path:
    """Return the project's test output root as an absolute path."""
    return (Path(repo_root) / _typed(config).scanning.test.output_root).resolve()


def target_folder(repo_root: Path, config: Any, target_name: str) -> Path:
    """Return the output area of the target.

    The output area holds the results, the coverage and the fingerprint.
    """
    return output_root(repo_root, config) / target_name


def _find_target(config: Any, target_name: str) -> Any:
    typed = _typed(config)
    for target in typed.scanning.test.targets:
        if target.name == target_name:
            return target
    configured = ", ".join(sorted(t.name for t in typed.scanning.test.targets)) or "none"
    raise KeyError(f"no test target named {target_name!r}; configured targets: {configured}")


def input_files(repo_root: Path, config: Any, target: Any) -> list[Path]:
    """Return every input of *target*, sorted.

    By default, every file in the repository is an input. The include set
    (directories and file patterns) limits the inputs. The exclude set
    (skipped directories and files) removes inputs. The walk applies the skip
    patterns first. Consequently, an exclusion wins over an inclusion. Every
    target excludes the output root and the global skip list. The skip lists
    of each scanning kind do not apply. Those lists control what a scan reads.
    They do not control what a run depends on.
    """
    from elspais.graph.file_selection import select_files

    typed = _typed(config)
    root = Path(repo_root).resolve()
    inputs = target.inputs
    everywhere = list(typed.scanning.skip)
    fixed_dirs = [typed.scanning.test.output_root.strip("/")]
    selection = select_files(
        root,
        list(inputs.directories) or ["."],
        [*inputs.skip_dirs, *everywhere, *fixed_dirs],
        [*inputs.skip_files, *everywhere],
        list(inputs.file_patterns) or ["*"],
    )
    return sorted(selection.selected)


def _digest_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_manifest(repo_root: Path, config: Any, target: Any) -> dict[str, str]:
    """Map the repo-relative path of each input of *target* to its content digest."""
    root = Path(repo_root).resolve()
    manifest: dict[str, str] = {}
    for path in input_files(root, config, target):
        try:
            manifest[path.relative_to(root).as_posix()] = _digest_file(path)
        except OSError:
            # A file that disappears after the walk is not an input.
            continue
    return manifest


def manifest_digest(manifest: dict[str, str]) -> str:
    """Return one digest for the whole manifest."""
    h = hashlib.sha256()
    for rel in sorted(manifest):
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(manifest[rel].encode("ascii"))
        h.update(b"\n")
    return h.hexdigest()


def differences(recorded: dict[str, str], current: dict[str, str]) -> list[str]:
    """Return the inputs whose digests differ between two manifests.

    An input that only one manifest holds also differs.
    """
    return sorted(
        rel for rel in set(recorded) | set(current) if recorded.get(rel) != current.get(rel)
    )


def _git_state(repo_root: Path) -> tuple[str, bool | None]:
    """Return the current commit and whether the working tree has uncommitted changes.

    The fingerprint stores these values for a human reader only. An empty
    commit and ``None`` mean that git returned no answer.
    """
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return "", None
    commit = head.stdout.strip() if head.returncode == 0 else ""
    dirty = bool(status.stdout.strip()) if status.returncode == 0 else None
    return commit, dirty


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_record(folder: Path) -> dict[str, Any] | None:
    """Return the fingerprint in the output area *folder*, or ``None``."""
    path = folder / RECORD_NAME
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("manifest"), dict):
        return None
    return data


def _write_record(folder: Path, record: dict[str, Any]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / RECORD_NAME).write_text(json.dumps(record, indent=1, sort_keys=True) + "\n")


def empty_folder(folder: Path) -> None:
    """Remove everything inside *folder*. Create the folder if it is missing."""
    if folder.is_dir():
        for child in folder.iterdir():
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()
    folder.mkdir(parents=True, exist_ok=True)


def start_run(repo_root: Path, config: Any, target_name: str) -> Path:
    """Start a run of a target. Empty the output area, then write the fingerprint.

    Return the path of the output area. The command of the target writes its
    results there.
    """
    root = Path(repo_root).resolve()
    target = _find_target(config, target_name)
    folder = target_folder(root, config, target_name)
    empty_folder(folder)
    manifest = compute_manifest(root, config, target)
    commit, dirty = _git_state(root)
    _write_record(
        folder,
        {
            "version": _RECORD_VERSION,
            "target": target_name,
            "started_at": _now(),
            "finished_at": "",
            "commit": commit,
            "dirty": dirty,
            "digest": manifest_digest(manifest),
            "manifest": manifest,
            "changed_during_run": [],
        },
    )
    return folder


class RunNotStarted(Exception):
    """A caller tried to finish a run that no ``start`` began."""


def finish_run(repo_root: Path, config: Any, target_name: str) -> dict[str, Any]:
    """Finish a run of a target. Record each input that changed during the run.

    This function accepts only a run that ``start_run`` began. ``start_run``
    empties the output area. Without that step, result files from an earlier
    run would carry the fingerprint of this run.

    Raises:
        RunNotStarted: No run of the target is in progress.
    """
    root = Path(repo_root).resolve()
    target = _find_target(config, target_name)
    folder = target_folder(root, config, target_name)
    record = read_record(folder)
    if record is None or record.get("finished_at"):
        raise RunNotStarted(
            f"no run of target {target_name!r} is in progress; a run begins with "
            f"`elspais fingerprint start {target_name}`, which empties the target's "
            f"folder, and only then can it be finished"
        )
    manifest = compute_manifest(root, config, target)
    record["changed_during_run"] = differences(record["manifest"], manifest)
    record["finished_at"] = _now()
    _write_record(folder, record)
    return record


def run_in_progress(folder: Path) -> dict[str, Any] | None:
    """Return the record of the run in progress in the output area *folder*, or ``None``.

    A run is in progress from the time its record is written with no end
    until the time its end is recorded.
    """
    record = read_record(folder)
    if record is None or record.get("finished_at"):
        return None
    return record


def results_present(repo_root: Path, config: Any, target: Any) -> bool:
    """Return whether the results pattern of a file-channel target matches a file.

    The pattern names files inside the output area of the target.
    """
    if not target.results:
        return False
    folder = target_folder(repo_root, config, target.name)
    return any(Path(f).is_file() for f in glob(str(folder / target.results), recursive=True))


def judge(repo_root: Path, config: Any, target_name: str) -> Freshness:
    """Return the freshness of a target's results on disk.

    A stale verdict includes its reason.
    """
    root = Path(repo_root).resolve()
    target = _find_target(config, target_name)
    folder = target_folder(root, config, target_name)
    # Implements: REQ-d00311-N
    # The record is read before the results. A run empties the area when it
    # starts, so an area with no results yet holds a run that is not finished.
    running = run_in_progress(folder)
    if running is not None:
        return Freshness(target=target_name, state="running", record=running)
    if not results_present(root, config, target):
        return Freshness(target=target_name, state="absent")
    record = read_record(folder)
    if record is None:
        return Freshness(target=target_name, state="stale", reason="no-fingerprint")
    during = tuple(record.get("changed_during_run") or ())
    if during:
        return Freshness(
            target=target_name,
            state="stale",
            reason="changed-during-run",
            changed=during,
            record=record,
        )
    changed = tuple(differences(record["manifest"], compute_manifest(root, config, target)))
    if changed:
        return Freshness(
            target=target_name, state="stale", reason="changed", changed=changed, record=record
        )
    return Freshness(target=target_name, state="fresh", record=record)
