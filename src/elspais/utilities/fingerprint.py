# Implements: REQ-d00311-A+B+C+D+I+J+K+L+M+N+P+R, REQ-d00312-A+B+D, REQ-d00329-B, REQ-d00333-A
"""Record the fingerprint of a test target's run, and judge the freshness of its results.

Terms:

- An input is something the results of a test target depend on: a file the
  target selects, each part of the environment the target declares, and the
  configuration of the target.
- The output area of a target is the directory ``<output_root>/<name>``.
  The command of the target writes its results and coverage there.
- A result fingerprint is a statement of one run of a target. It holds a
  manifest: the path and the content digest of each input, and the times the
  run started and finished, and the root of the tree it executed in. Where the
  run reported one, it also holds the exit status of the target's command.

A run writes its fingerprint into the output area when the run starts. The
results are fresh while the manifest matches the inputs on disk. The manifest
holds one digest for each input. Consequently, a stale finding can name the
input that changed.

The manifest names a file by its repo-relative path. It names each declared
part of the environment as ``/environment/<probe name>`` and the configuration
of the target as ``/configuration``. A repo-relative path never begins with
``/``, so neither spelling can name a file. The digest of a probe covers the
exit status and the standard output of its command, so a toolchain missing on
one machine and present on another differs. The configuration digest covers
every setting of the target except those that decide only which runs execute
it, how its finished results are credited, or which files are its inputs: the
name, groups, resources, ``inputs``, ``credit_coverage`` and
``min_coverage_fraction``. The file inputs are judged by their own entries.

The file lists the manifest as ``inputs``: a list of objects, each with a
``path`` field and a ``digest`` field. No path is ever a JSON key.
Consequently, a secret scanner that looks for a secret-like key beside a long
hex value finds nothing in the file.

:func:`elspais.graph.file_selection.select_files` selects the inputs. Scans use
the same function. Consequently, a pattern has one meaning in every context.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from glob import glob
from pathlib import Path
from typing import Any

from elspais.utilities.git import commit_state

#: The name of the fingerprint file in the output area.
FINGERPRINT_NAME = ".elspais-run.json"

#: The environment variable that holds the path of the output area for the command.
OUTPUT_ENV = "ELSPAIS_TARGET_OUTPUT"

#: The format of the *Result Fingerprint* this elspais writes and reads.
FINGERPRINT_VERSION = 3

#: The manifest spelling that begins each declared part of the environment.
ENVIRONMENT_PREFIX = "/environment/"

#: The manifest spelling of the configuration of the target.
CONFIGURATION_ENTRY = "/configuration"

#: The settings of a target left out of its configuration digest.
_NOT_CONFIGURATION = frozenset(
    {"name", "groups", "resources", "inputs", "credit_coverage", "min_coverage_fraction"}
)

#: The settings of a target's ``units`` table left out of its configuration
#: digest: they decide which tests a stale-only run retains, never what a run
#: that executes a test executes.
_NOT_UNITS_CONFIGURATION = frozenset({"dependencies", "observes"})

#: The settings of an environment probe left out of the configuration digest:
#: whether a change of the probe executes every unit decides what executes.
_NOT_PROBE_CONFIGURATION = frozenset({"affects_retention"})

#: The file in the output area holding the *Retained Results* of the run.
RETAINED_RESULTS_NAME = ".elspais-retained.jsonl"

#: The file in the output area holding the line coverage the run retained.
RETAINED_COVERAGE_NAME = ".elspais-retained-coverage.json"

#: The file in the output area recording each unit's last execution.
UNIT_LEDGER_NAME = ".elspais-units.json"

#: The file in the output area listing the units the run selected.
SELECTION_NAME = ".elspais-selection"

#: The environment variable naming the selection file for the command.
SELECTION_ENV = "ELSPAIS_SELECTION"

#: The longest a probe may run, in seconds. A probe runs inside every build,
#: so one that does not finish is recorded as such rather than awaited.
_PROBE_TIMEOUT = 60

#: The digest of each probe ``judge`` has run, keyed by its command and the
#: directory it ran in. Every judgement of a process shares it, so a build
#: runs each probe once. A served graph clears it before each rebuild.
_probe_cache: dict[tuple[str, str], str] = {}

#: The name of the file that names the last run's executed targets, in the output root.
#: A target name cannot start with ``.``, so no output area can take this name.
LAST_RUN_NAME = ".elspais-last-run.json"

_LAST_RUN_VERSION = 1


@dataclass(frozen=True)
class Freshness:
    """The freshness of the results of one target.

    ``state`` is ``"fresh"``, ``"stale"``, ``"absent"`` or ``"running"``.
    ``"absent"`` means that no results are on disk. The missing-results check
    reports that case. ``"running"`` means that a run of the target started
    and recorded no end. ``fingerprint`` then holds the fingerprint of that run.
    ``reason`` holds ``"no-fingerprint"``, ``"changed"`` or
    ``"changed-during-run"`` for stale results. Otherwise ``reason`` is empty.
    ``changed`` names the inputs that differ.
    ``"run-faults"`` means the run recorded faults after its command exited,
    and ``changed`` then names them. ``current`` is the manifest of the tree
    the judgement computed, where it computed one.
    """

    target: str
    state: str
    reason: str = ""
    changed: tuple[str, ...] = ()
    fingerprint: dict[str, Any] = field(default_factory=dict)
    current: dict[str, str] | None = None


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
    target excludes the output root, the *Evidence Snapshot* directory and
    the global skip list: a run writes the first two, so neither is an input
    of it. The skip lists of each scanning kind do not apply. Those lists
    control what a scan reads. They do not control what a run depends on.
    """
    from elspais.graph.file_selection import select_files

    typed = _typed(config)
    root = Path(repo_root).resolve()
    inputs = target.inputs
    everywhere = list(typed.scanning.skip)
    # Implements: REQ-d00311-M
    fixed_dirs = [typed.scanning.test.output_root.strip("/")]
    if typed.scanning.test.evidence:
        fixed_dirs.append(typed.scanning.test.evidence.strip("/"))
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


def file_manifest(
    repo_root: Path,
    config: Any,
    target: Any,
    digest_cache: dict[Path, str] | None = None,
) -> dict[str, str]:
    """Map the repo-relative path of each file input of *target* to its content digest.

    *digest_cache* maps a path to its digest. Targets often share inputs, so a
    caller judging several targets against one tree passes one cache to
    every call and each file is read once. A cache is valid only while no file
    changes, so a run never reads one.
    """
    root = Path(repo_root).resolve()
    manifest: dict[str, str] = {}
    for path in input_files(root, config, target):
        try:
            if digest_cache is None:
                digest = _digest_file(path)
            elif (digest := digest_cache.get(path)) is None:
                digest = digest_cache[path] = _digest_file(path)
            manifest[path.relative_to(root).as_posix()] = digest
        except OSError:
            # A file that disappears after the walk is not an input.
            continue
    return manifest


def forget_probes() -> None:
    """Forget every probe digest ``judge`` has run, so the next judgement probes again."""
    _probe_cache.clear()


def remember_probes(digests: dict[tuple[str, str], str]) -> None:
    """Take *digests*, measured just now, as the answers of their probes for later judgements."""
    _probe_cache.update(digests)


def probe_digests() -> dict[tuple[str, str], str]:
    """Return a copy of every probe digest ``judge`` has run, keyed by :attr:`DeclaredProbe.key`."""
    return dict(_probe_cache)


@dataclass(frozen=True)
class DeclaredProbe:
    """One environment probe of a test target, as it runs: in the target's ``cwd``."""

    name: str
    command: str
    cwd: Path

    @property
    def key(self) -> tuple[str, str]:
        """The key a probe's digest is held under: its command and its directory."""
        return (self.command, str(self.cwd))

    @property
    def entry(self) -> str:
        """The manifest entry that holds the probe's digest."""
        return ENVIRONMENT_PREFIX + self.name

    def digest(self) -> str:
        """Run the probe afresh and return its digest, without consulting or filling the cache."""
        return _run_probe(self.command, self.cwd)


def declared_probes(repo_root: Path, target: Any) -> list[DeclaredProbe]:
    """The environment probes *target* declares, each with the directory it runs in."""
    cwd = (Path(repo_root) / target.cwd).resolve()
    return [DeclaredProbe(p.name, p.command, cwd) for p in target.environment_probes]


def _run_probe(command: str, cwd: Path) -> str:
    """Return the digest of the exit status and the standard output of a probe."""
    h = hashlib.sha256()
    try:
        completed = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=_PROBE_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        h.update(b"timed out\n")
        return h.hexdigest()
    except OSError:
        h.update(b"could not start\n")
        return h.hexdigest()
    h.update(f"exit {completed.returncode}\n".encode("ascii"))
    h.update(completed.stdout)
    return h.hexdigest()


def configuration_digest(target: Any) -> str:
    """Return the digest of the settings of *target* that can change its outcomes."""
    settings = {
        key: value
        for key, value in target.model_dump(mode="json").items()
        if key not in _NOT_CONFIGURATION
    }
    settings["environment_probes"] = [
        {k: v for k, v in probe.items() if k not in _NOT_PROBE_CONFIGURATION}
        for probe in settings.get("environment_probes", [])
    ]
    if settings.get("units") is not None:
        settings["units"] = {
            k: v for k, v in settings["units"].items() if k not in _NOT_UNITS_CONFIGURATION
        }
    return hashlib.sha256(json.dumps(settings, sort_keys=True).encode("utf-8")).hexdigest()


# Implements: REQ-d00311-R
def declared_inputs(
    repo_root: Path, target: Any, probe_cache: dict[tuple[str, str], str] | None = None
) -> dict[str, str]:
    """Map the environment and the configuration of *target* to their digests.

    Each probe runs in the target's ``cwd``. *probe_cache* holds the digest
    of each probe already run, keyed by command and directory. A run never
    passes one, so a change during the run is seen.
    """
    entries: dict[str, str] = {CONFIGURATION_ENTRY: configuration_digest(target)}
    for probe in declared_probes(repo_root, target):
        if probe_cache is None:
            digest = probe.digest()
        elif (digest := probe_cache.get(probe.key)) is None:
            digest = probe_cache[probe.key] = probe.digest()
        entries[probe.entry] = digest
    return entries


def compute_manifest(
    repo_root: Path,
    config: Any,
    target: Any,
    digest_cache: dict[Path, str] | None = None,
    probe_cache: dict[tuple[str, str], str] | None = None,
) -> dict[str, str]:
    """Map every input of *target* to its digest: its files, its environment, its configuration.

    *digest_cache* is passed to :func:`file_manifest` and *probe_cache* to
    :func:`declared_inputs`.
    """
    manifest = file_manifest(repo_root, config, target, digest_cache)
    manifest.update(declared_inputs(repo_root, target, probe_cache))
    return manifest


# Implements: REQ-d00311-E+F
def input_label(entry: str) -> str:
    """Return the words that name one manifest entry: a path, a probe, or the configuration."""
    if entry == CONFIGURATION_ENTRY:
        return "the target's configuration"
    if entry.startswith(ENVIRONMENT_PREFIX):
        return f"environment probe {entry[len(ENVIRONMENT_PREFIX) :]!r}"
    return entry


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


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def read_fingerprint(folder: Path) -> dict[str, Any] | None:
    """Return the fingerprint in the output area *folder*, or ``None``."""
    path = folder / FINGERPRINT_NAME
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return None
    # A fingerprint of another format version reads as no fingerprint. Consequently,
    # its results read as stale, never as fresh.
    if not isinstance(data, dict) or data.get("version") != FINGERPRINT_VERSION:
        return None
    inputs = data.pop("inputs", None)
    if not isinstance(inputs, list):
        return None
    manifest: dict[str, str] = {}
    for entry in inputs:
        if not isinstance(entry, dict):
            return None
        path, digest = entry.get("path"), entry.get("digest")
        if not isinstance(path, str) or not isinstance(digest, str):
            return None
        manifest[path] = digest
    data["manifest"] = manifest
    return data


def _write_fingerprint(folder: Path, fingerprint: dict[str, Any]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    on_disk = {k: v for k, v in fingerprint.items() if k != "manifest"}
    on_disk["inputs"] = [
        {"path": rel, "digest": fingerprint["manifest"][rel]}
        for rel in sorted(fingerprint["manifest"])
    ]
    (folder / FINGERPRINT_NAME).write_text(json.dumps(on_disk, indent=1, sort_keys=True) + "\n")


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
    commit, dirty = commit_state(root)
    _write_fingerprint(
        folder,
        {
            "version": FINGERPRINT_VERSION,
            "target": target_name,
            # Implements: REQ-d00311-P
            # Where the run executed, so a recorded absolute path is read
            # relative to it after the tree moves.
            "root": str(root),
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


def finish_run(
    repo_root: Path,
    config: Any,
    target_name: str,
    exit_status: int | None = None,
    *,
    spawned: bool = True,
) -> dict[str, Any]:
    """Finish a run of a target. Record each input that changed during the run.

    This function accepts only a run that ``start_run`` began. ``start_run``
    empties the output area. Without that step, result files from an earlier
    run would carry the fingerprint of this run.

    *exit_status* is the exit status of the target's command, where the
    caller knows it. A target declaring ``file_results`` reads its test
    files' result from it, so a run that records none leaves those files
    awaiting a result.

    *spawned* is false where the run retained every result and never started
    the command, so it records no exit status.

    Raises:
        RunNotStarted: No run of the target is in progress.
    """
    root = Path(repo_root).resolve()
    target = _find_target(config, target_name)
    folder = target_folder(root, config, target_name)
    fingerprint = read_fingerprint(folder)
    if fingerprint is None or fingerprint.get("finished_at"):
        raise RunNotStarted(
            f"no run of target {target_name!r} is in progress; a run begins with "
            f"`elspais fingerprint start {target_name}`, which empties the target's "
            f"folder, and only then can it be finished"
        )
    manifest = compute_manifest(root, config, target)
    fingerprint["changed_during_run"] = differences(fingerprint["manifest"], manifest)
    # Implements: REQ-d00329-B
    if exit_status is not None and spawned:
        fingerprint["exit_status"] = exit_status
    # Implements: REQ-d00333-A
    if not spawned:
        fingerprint["spawned"] = False
    fingerprint["finished_at"] = _now()
    _write_fingerprint(folder, fingerprint)
    return fingerprint


# Implements: REQ-d00333-A
def command_spawned(folder: Path) -> bool:
    """Whether the finished run in the output area *folder* started its command.

    A run that retained every result records that it never started it. An
    area holding no finished run answers true: whatever it lacks, its command
    was meant to write.
    """
    fingerprint = read_fingerprint(folder)
    return not (
        fingerprint and fingerprint.get("finished_at") and fingerprint.get("spawned") is False
    )


# Implements: REQ-d00333-H
def record_run_faults(repo_root: Path, config: Any, target_name: str, faults: list[str]) -> None:
    """Record *faults* found in a finished run after its command exited.

    A fault fails the run for every later reader, not only for the process
    that ran it: :func:`judge` reads a run that recorded one as stale and names
    the faults, so the next stale-only run executes the target again.
    """
    folder = target_folder(Path(repo_root).resolve(), config, target_name)
    fingerprint = read_fingerprint(folder)
    if fingerprint is None or not fingerprint.get("finished_at") or not faults:
        return
    fingerprint["run_faults"] = list(fingerprint.get("run_faults") or []) + list(faults)
    _write_fingerprint(folder, fingerprint)


def run_in_progress(folder: Path) -> dict[str, Any] | None:
    """Return the fingerprint of the run in progress in the output area *folder*, or ``None``.

    A run is in progress from the time its fingerprint is written with no end
    until the time its end is recorded.
    """
    fingerprint = read_fingerprint(folder)
    if fingerprint is None or fingerprint.get("finished_at"):
        return None
    return fingerprint


# Implements: REQ-d00329-B
def recorded_exit_status(folder: Path) -> int | None:
    """Return the exit status the finished run in the output area *folder* recorded, or ``None``.

    A run in progress has recorded no exit status yet, and a run finished
    without one reports none.
    """
    fingerprint = read_fingerprint(folder)
    if fingerprint is None or not fingerprint.get("finished_at"):
        return None
    status = fingerprint.get("exit_status")
    return status if isinstance(status, int) and not isinstance(status, bool) else None


def results_present(repo_root: Path, config: Any, target: Any) -> bool:
    """Return whether the output area of a target holds anything a run wrote.

    That is a file its results pattern matches, its coverage file, or, for a
    target declaring ``file_results``, the exit status its run recorded: a
    target that declares only coverage still leaves results of its run to
    judge. Each names something inside the output area of the target.
    """
    folder = target_folder(repo_root, config, target.name)
    if target.file_results and recorded_exit_status(folder) is not None:
        return True
    # Implements: REQ-d00323-I
    if target.coverage and (folder / target.coverage).is_file():
        return True
    # Implements: REQ-d00333-A
    # A run that retained every result spawned no command, and its results
    # are the Retained Results it wrote.
    if (folder / RETAINED_RESULTS_NAME).is_file():
        return True
    if not target.results:
        return False
    return any(Path(f).is_file() for f in glob(str(folder / target.results), recursive=True))


def judge(
    repo_root: Path,
    config: Any,
    target_name: str,
    *,
    digest_cache: dict[Path, str] | None = None,
) -> Freshness:
    """Return the freshness of a target's results on disk.

    A stale verdict includes its reason. *digest_cache* is passed to
    :func:`compute_manifest`. Each probe of the target's environment runs
    once per process; :func:`forget_probes` makes the next judgement probe
    again.
    """
    root = Path(repo_root).resolve()
    target = _find_target(config, target_name)
    folder = target_folder(root, config, target_name)
    # Implements: REQ-d00311-N
    # The fingerprint is read before the results. A run empties the area when it
    # starts, so an area with no results yet holds a run that is not finished.
    running = run_in_progress(folder)
    if running is not None:
        return Freshness(target=target_name, state="running", fingerprint=running)
    if not results_present(root, config, target):
        return Freshness(target=target_name, state="absent")
    fingerprint = read_fingerprint(folder)
    if fingerprint is None:
        return Freshness(target=target_name, state="stale", reason="no-fingerprint")
    during = tuple(fingerprint.get("changed_during_run") or ())
    if during:
        return Freshness(
            target=target_name,
            state="stale",
            reason="changed-during-run",
            changed=during,
            fingerprint=fingerprint,
        )
    current = compute_manifest(root, config, target, digest_cache, _probe_cache)
    changed = tuple(differences(fingerprint["manifest"], current))
    if changed:
        return Freshness(
            target=target_name,
            state="stale",
            reason="changed",
            changed=changed,
            fingerprint=fingerprint,
            current=current,
        )
    # Implements: REQ-d00333-H
    faults = tuple(str(f) for f in fingerprint.get("run_faults") or ())
    if faults:
        return Freshness(
            target=target_name,
            state="stale",
            reason="run-faults",
            changed=faults,
            fingerprint=fingerprint,
            current=current,
        )
    return Freshness(target=target_name, state="fresh", fingerprint=fingerprint, current=current)


# Implements: REQ-d00311-E+F
def describe_inputs(entries: list[str] | tuple[str, ...]) -> str:
    """Name the first few of *entries* and count the rest, in the words of :func:`input_label`."""
    shown = ", ".join(input_label(entry) for entry in entries[:5])
    more = f" and {len(entries) - 5} more" if len(entries) > 5 else ""
    return f"{shown}{more}"


# Implements: REQ-d00311-E+F, REQ-d00323-G
def stale_reason(verdict: Freshness) -> str:
    """Return why a stale verdict is stale, in words a finding can quote.

    The one wording of the reason, so the freshness finding and a failure
    read from stale results say the same thing.
    """
    if verdict.reason == "no-fingerprint":
        return "no fingerprint was recorded for its results"
    if verdict.reason == "run-faults":
        shown = "; ".join(verdict.changed[:5])
        more = f" and {len(verdict.changed) - 5} more" if len(verdict.changed) > 5 else ""
        return f"its run failed after its command exited: {shown}{more}"
    when = "while it ran" if verdict.reason == "changed-during-run" else "since it ran"
    return f"inputs changed {when}: {describe_inputs(verdict.changed)}"


#: The keys of a run reference: the commit, root and start that name a run.
RUN_REFERENCE_KEYS = ("commit", "root", "started_at")


def run_reference(fingerprint: dict[str, Any]) -> dict[str, str]:
    """The commit, root and start that name the run a fingerprint records."""
    return {key: str(fingerprint.get(key) or "") for key in RUN_REFERENCE_KEYS}


# Implements: REQ-d00323-M, REQ-d00333-L
def describe_run(run: dict[str, Any]) -> str:
    """Name a recorded run by its commit, its start and the root it executed in."""
    commit = str(run.get("commit") or "")[:12] or "an uncommitted tree"
    started = run.get("started_at") or "an unrecorded time"
    root = run.get("root")
    return f"the run of {commit} started {started}" + (f" in {root}" if root else "")


# Implements: REQ-d00333-E, REQ-d00311-N
def ended_run_refusal(fingerprint: dict[str, Any]) -> str:
    """Return why a recorded run cannot be taken from as an earlier run, or ``""``.

    A run that recorded no end may hold partial results, and inputs that
    changed while it ran leave its results describing no one tree. Adopting a
    *Baseline Run* and retaining a result both ask this.
    """
    if not fingerprint.get("finished_at"):
        return "its run is in progress or recorded no end, so its results may be partial"
    during = fingerprint.get("changed_during_run") or []
    if during:
        return f"inputs changed while it ran: {describe_inputs(during)}"
    return ""


def last_run_path(repo_root: Path, config: Any) -> Path:
    """Return the path of the file that names the last run's executed targets."""
    return output_root(repo_root, config) / LAST_RUN_NAME


# Implements: REQ-d00316-A+B+C+D
def write_last_run(repo_root: Path, config: Any, executed: list[str]) -> Path:
    """Write the targets a run executed, replacing the file an earlier run wrote.

    The file holds a JSON object: ``version`` (1), ``executed`` (the names of
    the targets the run executed, sorted) and ``finished_at`` (an ISO 8601
    time). It sits in the output root, beside the output areas, because a
    target's own area is emptied whenever that target runs.
    """
    path = last_run_path(repo_root, config)
    path.parent.mkdir(parents=True, exist_ok=True)
    last_run = {
        "version": _LAST_RUN_VERSION,
        "executed": sorted(set(executed)),
        "finished_at": _now(),
    }
    path.write_text(json.dumps(last_run, indent=1, sort_keys=True) + "\n")
    return path


# Implements: REQ-d00316-F
def read_last_run(repo_root: Path, config: Any) -> list[str] | None:
    """Return the targets the last run executed, or ``None`` where no readable file names them."""
    path = last_run_path(repo_root, config)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return None
    if not isinstance(data, dict) or data.get("version") != _LAST_RUN_VERSION:
        return None
    executed = data.get("executed")
    if not isinstance(executed, list) or not all(isinstance(n, str) for n in executed):
        return None
    return executed
