# Implements: REQ-d00333-E+F, REQ-d00311-H+I+N
"""Pack the recorded runs of test targets into one archive, and adopt a fetched one.

A packed baseline is a gzip-compressed tar archive. It holds the file
``elspais-baseline.json`` and, under ``targets/<name>/``, the output area of
each packed target as its run left it, *Result Fingerprint* included. The
manifest file states the version of elspais that packed it, the format of
the archive, the format of the *Result Fingerprint*, and the commit the runs
executed at.

A pack holds only a run that can serve as a *Baseline Run*: a run of a tree
identical to a commit, that recorded its end, and whose inputs did not
change while it ran. A failing run qualifies; its failures are its results.

An adopted area is an ordinary recorded run. Nothing here judges whether its
results are fresh: :func:`elspais.utilities.fingerprint.judge` reads the
adopted *Result Fingerprint* as it reads any other, so a run from another
tree, environment or configuration is stale and says why.

How a pack travels is the project's concern. ``fetch`` runs the command the
project declares, which fills an empty directory with one archive; elspais
knows no host and walks no history.
"""

from __future__ import annotations

import io
import json
import shlex
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

#: The name of the manifest file inside a packed baseline.
PACK_MANIFEST = "elspais-baseline.json"

#: The directory inside a packed baseline that holds one folder per target.
PACK_TARGETS = "targets"

#: The format of a packed baseline.
PACK_FORMAT = 1


class BaselineRefused(Exception):
    """A pack or a fetch that cannot proceed. ``reasons`` names each cause."""

    def __init__(self, reasons: list[str]) -> None:
        super().__init__("; ".join(reasons))
        self.reasons = reasons


@dataclass(frozen=True)
class Adoption:
    """What a fetch did with one packed target.

    ``outcome`` is ``"adopted"``, ``"skipped"`` or ``"refused"``; ``detail``
    says why where the target was not adopted.
    """

    target: str
    outcome: str
    detail: str = ""


# Implements: REQ-d00333-E+F, REQ-d00311-N
def _run_refusal(fingerprint: dict[str, Any]) -> str:
    """Return why a recorded run cannot serve as a *Baseline Run*, or ``""``.

    Packing and adopting both ask, so an archive assembled by other means
    holds to the same rule.
    """
    from elspais.utilities.fingerprint import input_label

    if not fingerprint.get("finished_at"):
        return "its run is in progress or recorded no end, so its results may be partial"
    during = fingerprint.get("changed_during_run") or []
    if during:
        shown = ", ".join(input_label(entry) for entry in during[:5])
        more = f" and {len(during) - 5} more" if len(during) > 5 else ""
        return f"inputs changed while it ran: {shown}{more}"
    if fingerprint.get("dirty") is not False or not fingerprint.get("commit"):
        return (
            "its run executed in a tree that differs from every commit; commit the "
            "tree and run it again"
        )
    return ""


def _target_refusal(repo_root: Path, config: Any, target: Any, head: str) -> str:
    """Return why the recorded run of *target* cannot be packed, or ``""``."""
    from elspais.utilities.fingerprint import (
        FINGERPRINT_NAME,
        read_fingerprint,
        results_present,
        target_folder,
    )

    folder = target_folder(repo_root, config, target.name)
    fingerprint = read_fingerprint(folder)
    if fingerprint is None:
        if (folder / FINGERPRINT_NAME).is_file():
            return "its Result Fingerprint is unreadable or of another format; run it again"
        return "no Result Fingerprint records a run of it; run it first"
    refusal = _run_refusal(fingerprint)
    if refusal:
        return refusal
    if not results_present(repo_root, config, target):
        return "its output area holds no results"
    # Implements: REQ-d00333-F
    commit = fingerprint["commit"]
    if commit != head:
        return (
            f"its run executed at commit {commit[:12]}, and the tree is at commit "
            f"{head[:12]}; run it again"
        )
    return ""


# Implements: REQ-d00333-E+F
def pack(repo_root: Path, config: Any, targets: list[str], out: Path) -> dict[str, Any]:
    """Write the recorded runs of *targets* into the archive *out*.

    Returns the manifest written into it.

    Raises:
        BaselineRefused: The tree holds changes no commit holds, or a target's
            run cannot serve as a *Baseline Run*. Each reason names its target.
    """
    import elspais
    from elspais.utilities.fingerprint import FINGERPRINT_VERSION, target_folder
    from elspais.utilities.git import commit_state, list_uncommitted_files

    root = Path(repo_root).resolve()
    by_name = {t.name: t for t in config.scanning.test.targets}
    reasons: list[str] = []
    try:
        uncommitted = list_uncommitted_files(root)
    except (subprocess.CalledProcessError, OSError) as exc:
        raise BaselineRefused(
            [f"git could not say whether the tree matches a commit ({exc})"]
        ) from exc
    if uncommitted:
        shown = ", ".join(uncommitted[:5])
        more = f" and {len(uncommitted) - 5} more" if len(uncommitted) > 5 else ""
        reasons.append(
            f"the tree holds changes no commit holds ({shown}{more}); a Baseline Run "
            f"is a run of a tree identical to a commit"
        )
    head, _dirty = commit_state(root)
    if not head:
        reasons.append("git names no commit for the tree")
    if not targets:
        reasons.append("no target is selected")
    for name in targets:
        target = by_name.get(name)
        if target is None:
            reasons.append(f"no test target named {name!r}")
            continue
        refusal = _target_refusal(root, config, target, head)
        if refusal:
            reasons.append(f"target {name}: {refusal}")
    if reasons:
        raise BaselineRefused(reasons)

    manifest = {
        "format": PACK_FORMAT,
        "fingerprint_version": FINGERPRINT_VERSION,
        "elspais": elspais.__version__,
        "commit": head,
        "targets": sorted(targets),
    }
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(out, "w:gz") as archive:
        body = (json.dumps(manifest, indent=1, sort_keys=True) + "\n").encode("utf-8")
        info = tarfile.TarInfo(PACK_MANIFEST)
        info.size = len(body)
        archive.addfile(info, io.BytesIO(body))
        for name in sorted(targets):
            folder = target_folder(root, config, name)
            for path in sorted(folder.rglob("*")):
                if path.is_symlink() or not path.is_file():
                    continue
                arcname = f"{PACK_TARGETS}/{name}/{path.relative_to(folder).as_posix()}"
                archive.add(path, arcname=arcname, recursive=False)
    return manifest


class BaselineUnreadable(Exception):
    """A fetched file that is not a packed baseline this elspais can adopt."""


def _safe_member_path(name: str) -> PurePosixPath | None:
    """Return the member's path where it stays inside the archive's root, or ``None``."""
    path = PurePosixPath(name)
    if path.is_absolute() or not path.parts or any(p in ("..", "") for p in path.parts):
        return None
    return path


def unpack(archive_path: Path, staging: Path) -> dict[str, Any]:
    """Validate the packed baseline *archive_path* and extract it into *staging*.

    Only regular files and directories are extracted, each at a path inside
    *staging*; a link, a device or a path leaving the archive's root refuses
    the whole archive.

    Returns the manifest.

    Raises:
        BaselineUnreadable: The file is not a packed baseline this elspais reads.
    """
    from elspais.utilities.fingerprint import FINGERPRINT_VERSION

    try:
        archive = tarfile.open(archive_path, "r:*")
    except (tarfile.TarError, OSError) as exc:
        raise BaselineUnreadable(f"{archive_path.name} is not a readable archive ({exc})") from exc
    with archive:
        members: list[tuple[tarfile.TarInfo, PurePosixPath]] = []
        for member in archive.getmembers():
            path = _safe_member_path(member.name)
            if path is None or not (member.isfile() or member.isdir()):
                raise BaselineUnreadable(
                    f"{archive_path.name} holds {member.name!r}, which is not a file or "
                    f"directory inside the archive"
                )
            members.append((member, path))
        for member, path in members:
            destination = staging.joinpath(*path.parts)
            if member.isdir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            source = archive.extractfile(member)
            if source is None:
                raise BaselineUnreadable(f"{archive_path.name}: {member.name!r} cannot be read")
            destination.parent.mkdir(parents=True, exist_ok=True)
            with source, destination.open("wb") as sink:
                while chunk := source.read(1 << 16):
                    sink.write(chunk)

    manifest_path = staging / PACK_MANIFEST
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BaselineUnreadable(
            f"{archive_path.name} holds no readable {PACK_MANIFEST} ({exc})"
        ) from exc
    if not isinstance(manifest, dict):
        raise BaselineUnreadable(f"{PACK_MANIFEST} in {archive_path.name} is not an object")
    if manifest.get("format") != PACK_FORMAT:
        raise BaselineUnreadable(
            f"{archive_path.name} is a packed baseline of format "
            f"{manifest.get('format')!r}; this elspais reads format {PACK_FORMAT}"
        )
    if manifest.get("fingerprint_version") != FINGERPRINT_VERSION:
        raise BaselineUnreadable(
            f"{archive_path.name} holds Result Fingerprints of format "
            f"{manifest.get('fingerprint_version')!r}, packed by elspais "
            f"{manifest.get('elspais', '?')}; this elspais reads format "
            f"{FINGERPRINT_VERSION}"
        )
    targets = manifest.get("targets")
    if not isinstance(targets, list) or not all(isinstance(t, str) for t in targets):
        raise BaselineUnreadable(f"{PACK_MANIFEST} in {archive_path.name} names no targets")
    return manifest


# Implements: REQ-d00311-H+I
def adopt(
    repo_root: Path, config: Any, staging: Path, manifest: dict[str, Any], *, replace: bool
) -> list[Adoption]:
    """Adopt each packed target's area into the local output area.

    A target is adopted only where its packed run can serve as a *Baseline
    Run* and its local area holds no *Result Fingerprint*, unless *replace*
    is set. A local run in progress is never
    replaced, since its command is still writing there. Every target is
    judged before any area changes.
    """
    from elspais.utilities.fingerprint import (
        FINGERPRINT_NAME,
        empty_folder,
        read_fingerprint,
        run_in_progress,
        target_folder,
    )

    root = Path(repo_root).resolve()
    configured = {t.name for t in config.scanning.test.targets}
    outcomes: list[Adoption] = []
    to_adopt: list[tuple[str, Path, Path]] = []
    for name in sorted(set(manifest["targets"])):
        # A configured name is one path segment (REQ-d00312-A), so only a
        # configured name is ever joined to a path.
        if name not in configured:
            outcomes.append(
                Adoption(name, "refused", "this repository declares no test target of that name")
            )
            continue
        packed = staging / PACK_TARGETS / name
        local = target_folder(root, config, name)
        packed_fingerprint = read_fingerprint(packed)
        if packed_fingerprint is None:
            outcomes.append(
                Adoption(name, "refused", "the pack holds no readable Result Fingerprint for it")
            )
            continue
        # Implements: REQ-d00333-E+F
        refusal = _run_refusal(packed_fingerprint)
        if refusal:
            outcomes.append(Adoption(name, "refused", f"the packed run: {refusal}"))
            continue
        if run_in_progress(local) is not None:
            outcomes.append(
                Adoption(name, "refused", "a run of it is in progress here; let it finish")
            )
            continue
        if (local / FINGERPRINT_NAME).is_file() and not replace:
            outcomes.append(
                Adoption(
                    name,
                    "skipped",
                    "a Result Fingerprint is already recorded here; --replace replaces it",
                )
            )
            continue
        to_adopt.append((name, packed, local))

    for name, packed, local in to_adopt:
        empty_folder(local)
        for path in sorted(packed.rglob("*")):
            if not path.is_file():
                continue
            destination = local / path.relative_to(packed)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(path.read_bytes())
        outcomes.append(Adoption(name, "adopted"))
    return sorted(outcomes, key=lambda a: a.target)


# Implements: REQ-d00333-F
def fetch(repo_root: Path, config: Any, *, replace: bool) -> tuple[dict[str, Any], list[Adoption]]:
    """Run the project's fetch command, validate what it fetched, and adopt it.

    Returns the pack's manifest and the outcome for each packed target.

    Raises:
        BaselineRefused: No fetch command is configured, the command failed,
            or it left no single readable packed baseline. Nothing changed.
    """
    command = config.scanning.test.baseline.fetch_command
    if not command.strip():
        raise BaselineRefused(
            [
                "no fetch command is configured; set [scanning.test.baseline] "
                'fetch_command, such as "tools/fetch-baseline.sh {dest}"'
            ]
        )
    root = Path(repo_root).resolve()
    with tempfile.TemporaryDirectory(prefix="elspais-baseline-") as scratch:
        dest = Path(scratch) / "fetched"
        dest.mkdir()
        staging = Path(scratch) / "staging"
        staging.mkdir()
        completed = subprocess.run(
            command.replace("{dest}", shlex.quote(str(dest))),
            shell=True,
            cwd=root,
            stdin=subprocess.DEVNULL,
            check=False,
        )
        if completed.returncode != 0:
            raise BaselineRefused([f"the fetch command exited {completed.returncode}: {command}"])
        fetched = sorted(p for p in dest.iterdir())
        if not fetched:
            raise BaselineRefused([f"the fetch command left nothing in {{dest}}: {command}"])
        if len(fetched) > 1 or not fetched[0].is_file() or fetched[0].is_symlink():
            names = ", ".join(p.name for p in fetched)
            raise BaselineRefused(
                [f"the fetch command must leave one archive in {{dest}}, and it left: {names}"]
            )
        try:
            manifest = unpack(fetched[0], staging)
        except BaselineUnreadable as exc:
            raise BaselineRefused([str(exc)]) from exc
        return manifest, adopt(root, config, staging, manifest, replace=replace)
