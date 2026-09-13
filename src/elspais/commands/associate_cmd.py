# Implements: REQ-p00005-C
"""
elspais.commands.associate_cmd - Manage associate repository links.

Provides subcommands to link, unlink, list, and auto-discover
associate repositories.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import tomlkit

from elspais.associates import Associate, discover_associate_from_path
from elspais.config import find_config_file, get_config, parse_toml_document
from elspais.graph.federated import FederationError


class Outcome(Enum):
    """What a registration run did, or why it did nothing.

    Implements: REQ-d00289-B

    A run that changed the configuration, a run that deliberately did
    not, and each way a run can refuse are separate values rather than
    shades of one, so no caller has to read a message to find out which
    happened.
    """

    RECORDED = "recorded"
    UNCHANGED = "unchanged"
    REPOINTED = "repointed"

    ENTRY_EXISTS = "entry-exists"
    CONTESTED = "contested"
    WOULD_NOT_FEDERATE = "would-not-federate"


_REFUSALS = frozenset({Outcome.ENTRY_EXISTS, Outcome.CONTESTED, Outcome.WOULD_NOT_FEDERATE})


@dataclass
class Registration:
    """What a registration run recorded, in the terms it is reported in.

    Implements: REQ-d00289-A, REQ-d00289-B

    `path` is the path the configuration holds for the entry once the run
    has returned -- for a refusal, the path that was already there.
    """

    kind: Outcome
    name: str
    namespace: str
    path: str = ""
    previous_path: str = ""
    target: str = ""

    reason: str = ""
    """Why a federation refused this registration, in its own words."""

    pre_existing: bool = False
    """The reason was true of the configuration before this registration."""

    contested_paths: tuple[str, ...] = ()
    """Other directories of this same run claiming this namespace."""

    @property
    def refused(self) -> bool:
        return self.kind in _REFUSALS

    def report_lines(self) -> list[str]:
        """The lines describing this outcome, first line first."""
        match self.kind:
            case Outcome.RECORDED:
                return [f"Linked {self.name} ({self.namespace}) at {self.path}"]

            case Outcome.UNCHANGED:
                # Implements: REQ-d00289-B
                return [
                    f"No change: {self.name} ({self.namespace}) stays registered at {self.path}"
                ]

            case Outcome.REPOINTED:
                # Implements: REQ-d00289-D
                return [
                    f"Repointed {self.name} ({self.namespace}): "
                    f"was {self.previous_path}, now registered at {self.path}"
                ]

            case Outcome.ENTRY_EXISTS:
                # Implements: REQ-d00289-C
                return [
                    f"Refused: {self.name} is already registered at "
                    f"{self.previous_path}, and nothing was changed.",
                    f"Use -f to replace that path with {self.target}.",
                    "Run 'elspais associate --list' to see the current registrations.",
                ]

            case Outcome.CONTESTED:
                # Implements: REQ-d00289-G
                others = ", ".join(self.contested_paths)
                return [
                    f"Refused: {self.target} and {others} claim the namespace "
                    f"{self.namespace} in this scan; none of them was recorded.",
                    "Register the one you mean by path.",
                ]

            case Outcome.WOULD_NOT_FEDERATE if self.pre_existing:
                # Implements: REQ-d00289-I
                return [
                    f"Refused: this configuration does not federate as it stands, before "
                    f"{self.name} at {self.target} is considered. Nothing was changed.",
                    f"  {self.reason}",
                ]

            case Outcome.WOULD_NOT_FEDERATE:
                # Implements: REQ-d00289-E, REQ-d00289-H
                return [
                    f"Refused: {self.name} at {self.target} would not federate, "
                    f"and nothing was changed.",
                    f"  {self.reason}",
                ]


def run(args: argparse.Namespace) -> int:
    """Run the associate command.

    Dispatches to the appropriate subcommand based on args.

    Args:
        args: Parsed command line arguments.

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    if getattr(args, "list", False):
        return cmd_list(args)
    elif getattr(args, "unlink", None):
        return cmd_unlink(args)
    elif getattr(args, "all", False):
        return cmd_all(args)
    elif getattr(args, "associate_path", None):
        return cmd_link(args)
    else:
        print("Usage: elspais associate <path> [-f]", file=sys.stderr)
        print("       elspais associate --all [-f]", file=sys.stderr)
        print("       elspais associate --list", file=sys.stderr)
        print("       elspais associate --unlink <name>", file=sys.stderr)
        return 1


def cmd_link(args: argparse.Namespace) -> int:
    """Link a single associate repository.

    If path is a directory, validates it has an associate config.
    If path is a name (no slashes), scans sibling directories.

    Args:
        args: Parsed arguments with .path set.

    Returns:
        Exit code.
    """
    path_str = args.associate_path
    repo_path = Path(path_str)

    # If it looks like a name (no path separators), search siblings
    if not repo_path.is_absolute() and "/" not in path_str and "\\" not in path_str:
        resolved = _find_by_name(path_str, args)
        if resolved is None:
            print(
                f"Error: Could not find associate '{path_str}' in sibling directories.",
                file=sys.stderr,
            )
            return 1
        repo_path = resolved

    repo_path = repo_path.resolve()

    # Validate it is an associate repo
    result = discover_associate_from_path(repo_path)
    if isinstance(result, str):
        print(f"Error: {result}", file=sys.stderr)
        return 1

    # Write to .elspais.local.toml
    config_dir = _get_config_dir(args)
    if config_dir is None:
        print("Error: No configuration directory found.", file=sys.stderr)
        return 1

    git_root = getattr(args, "git_root", None)
    gr = Path(git_root) if git_root else None
    outcome = register_associate(
        config_dir,
        str(repo_path),
        result.name,
        result.code,
        repo_root=gr or config_dir,
        force=getattr(args, "force", False),
        config_path=_get_config_path(args),
    )

    if outcome.refused:
        for line in outcome.report_lines():
            print(line, file=sys.stderr)
        return 1

    for line in outcome.report_lines():
        print(line)
    return 0


def cmd_all(args: argparse.Namespace) -> int:
    """Auto-discover and link all associate repos in sibling directories.

    Scans git_root.parent (or config_dir.parent) for sibling directories
    containing a `.elspais.toml` that loads successfully under the
    standard config schema (see `discover_associate_from_path()`). There
    is no `project.type` marker to opt a repo in or out of discovery --
    that key does not exist in the schema, and a config containing it
    would fail `load_config()` validation (`extra="forbid"`). Any
    directory whose config loads, other than the current repo itself,
    is treated as a candidate associate.

    Args:
        args: Parsed arguments.

    Returns:
        Exit code.
    """
    scan_base = _get_scan_base(args)
    if scan_base is None:
        print("Error: Cannot determine parent directory to scan.", file=sys.stderr)
        return 1

    config_dir = _get_config_dir(args)
    if config_dir is None:
        print("Error: No configuration directory found.", file=sys.stderr)
        return 1

    found: list[tuple[Path, Associate]] = []
    skipped: list[str] = []

    for child in sorted(scan_base.iterdir()):
        if not child.is_dir():
            continue
        # Skip the current repo
        if config_dir and child.resolve() == config_dir.resolve():
            continue
        result = discover_associate_from_path(child)
        if isinstance(result, Associate):
            found.append((child.resolve(), result))
        elif (child / ".elspais.toml").exists():
            # Implements: REQ-d00202-I
            # A sibling that claims to be an elspais repo but whose config
            # cannot be loaded is skipped visibly; dirs without a config are
            # not candidates and stay silent.
            skipped.append(result)

    for reason in skipped:
        print(f"  Skipping: {reason}")

    if not found:
        print("No associate repositories found in sibling directories.")
        return 0

    git_root = getattr(args, "git_root", None)
    gr = Path(git_root) if git_root else None
    config_path = _get_config_path(args)
    force = getattr(args, "force", False)
    linked_count = 0
    unchanged_count = 0
    refused_count = 0

    # Implements: REQ-d00289-G
    # Which candidates stand for one entry is settled across the whole
    # scan before any of them is written. Deciding as it went would have
    # recorded the first of an ambiguous pair and refused the second, so
    # the order the scan reached them in would be standing in for a choice
    # the operator never made.
    contested = _contested_candidates(found)

    # Implements: REQ-d00289-F
    # A candidate the tool will not record is one candidate: the scan
    # reports it and carries on, so the state of the ones around it is
    # still on the screen when the operator reads the refusal.
    for repo_path, assoc in found:
        rivals = contested.get(str(repo_path))
        if rivals is not None:
            outcome = Registration(
                kind=Outcome.CONTESTED,
                name=assoc.name,
                namespace=assoc.code,
                target=str(repo_path),
                contested_paths=rivals,
            )
        else:
            outcome = register_associate(
                config_dir,
                str(repo_path),
                assoc.name,
                assoc.code,
                repo_root=gr or config_dir,
                force=force,
                config_path=config_path,
            )

        # A refusal reads the same from either surface, on the stream a
        # script watching for one already reads.
        stream = sys.stderr if outcome.refused else sys.stdout
        for line in outcome.report_lines():
            print(f"  {line}", file=stream)
        if outcome.refused:
            refused_count += 1
            continue

        if outcome.kind is Outcome.UNCHANGED:
            unchanged_count += 1
        else:
            linked_count += 1

    print(
        f"Linked {linked_count} associate(s), {unchanged_count} unchanged, {refused_count} refused"
    )
    return 1 if refused_count else 0


def cmd_list(args: argparse.Namespace) -> int:
    """List current associate links and their status.

    Reads named [associates.<name>] entries from merged config and checks each path.

    Args:
        args: Parsed arguments.

    Returns:
        Exit code.
    """
    # Implements: REQ-d00202-A
    from elspais.config import get_associates_config, get_config

    config_path = _get_config_path(args)
    config = get_config(
        config_path=config_path,
        quiet=True,
    )

    try:
        associates = get_associates_config(config)
    except ValueError as exc:
        # A listing surface has to survive the declarations it exists to
        # list, and say which one it could not read.
        print(f"Cannot list associates: {exc}")
        return 1

    if not associates:
        print("No associates linked.")
        print("Use 'elspais associate <path>' or 'elspais associate --all' to link.")
        return 0

    git_root = getattr(args, "git_root", None)

    # Implements: REQ-d00290-B
    # A repository whose configuration was assembled with a machine-local
    # overlay is marked, so an answer read here can be compared against one
    # read elsewhere without the reader having to guess why they differ.
    from elspais.graph.federation_plan import uses_local_overlay

    # Implements: REQ-d00290-B
    # This repository's own overlay is where `elspais associate` writes, so
    # it is stated before the table rather than left out of it: the rows
    # answer for the associates, and this line answers for the repository
    # doing the asking.
    own_root = _get_config_dir(args)
    if own_root is not None and uses_local_overlay(own_root):
        print("This repository's configuration is locally overridden (.elspais.local.toml).")
    print(f"{'Name':<20} {'Prefix':<10} {'Status':<12} {'Local':<7} Path")
    print("-" * 80)

    for assoc_name, assoc_info in associates.items():
        path_str = assoc_info["path"]
        repo_path = Path(path_str)
        if not repo_path.is_absolute() and git_root:
            repo_path = Path(git_root) / repo_path
        if not repo_path.exists():
            print(f"{assoc_name:<20} {'?':<10} {'NOT FOUND':<12} {'-':<7} {path_str}")
            continue

        local = "yes" if uses_local_overlay(repo_path) else "-"
        result = discover_associate_from_path(repo_path)
        if isinstance(result, str):
            print(f"{assoc_name:<20} {'?':<10} {'BROKEN':<12} {local:<7} {path_str}")
        else:
            spec_dir = repo_path / result.spec_path
            status = "OK" if spec_dir.exists() else "NO SPEC"
            print(f"{result.name:<20} {result.code:<10} {status:<12} {local:<7} {path_str}")

    return 0


def cmd_unlink(args: argparse.Namespace) -> int:
    """Retire an associate entry, or say why this file cannot retire it.

    Implements: REQ-d00289-A, REQ-d00289-B

    Implements: REQ-d00290-A

    What is recorded is read from the configuration as assembled, and the
    machine-local file is the only file written. The two are not the same
    set: a declaration sitting in the committed file is recorded and cannot
    be taken out from here, so a run that reads the file it writes reports a
    declaration it can see in a listing as not existing at all.

    Four states follow from that, and they are reported as four:

      1. Nothing in the configuration answers to the name.
      2. Only the machine-local file declares the entry -- removing it
         retires the associate.
      3. Only the committed file declares it -- nothing is written, and the
         file to edit is named.
      4. Both declare it -- removing the local entry withdraws the override
         and leaves the committed declaration standing, which the report
         states rather than reading as a retirement.

    Args:
        args: Parsed arguments with .unlink set to the name.

    Returns:
        Exit code: 0 where an entry was removed, non-zero where none was.
    """
    name = args.unlink
    config_dir = _get_config_dir(args)
    config_path = _get_config_path(args)
    if config_dir is None or config_path is None:
        print("Error: No configuration directory found.", file=sys.stderr)
        return 1

    # Implements: REQ-d00290-A
    # Every entry the configuration holds, however it was written, read
    # once -- the same answer a later run will read.
    try:
        config = get_config(config_path=config_path, start_path=config_dir, quiet=True)
    except Exception as exc:  # noqa: BLE001 - reported, never raised at a user
        # Removing a declaration is one of the ways a configuration gets
        # repaired, so meeting an unreadable one is ordinary.
        print(f"Error: the configuration cannot be read: {exc}", file=sys.stderr)
        return 1

    recorded = _assembled_associates(config)
    found_key = _matching_entry(recorded, name)
    if found_key is None:
        print(f"Error: No associate '{name}' found.", file=sys.stderr)
        return 1

    local_path = _local_config(config_dir)
    doc, local_entries = _local_associates(local_path)
    local_entry = local_entries.get(found_key)
    committed_path = _committed_path(config_path, found_key)

    if not isinstance(local_entry, dict):
        # Implements: REQ-d00289-B
        # A committed declaration outlives any local write, so the run
        # records nothing and names the file that does hold it.
        print(
            f"Refused: {found_key} is declared in {config_path.name} at "
            f"{committed_path}, and nothing was changed.",
            file=sys.stderr,
        )
        print(
            "Remove it there; a machine-local write cannot retire a committed declaration.",
            file=sys.stderr,
        )
        return 1

    # Implements: REQ-d00289-A
    # The path reported is the one the entry being removed was recorded at,
    # rather than the name the invocation matched on.
    removed_path = local_entry.get("path", "")
    del local_entries[found_key]
    local_path.write_text(tomlkit.dumps(doc), encoding="utf-8")

    if committed_path:
        # Implements: REQ-d00289-B
        # The override is gone and the associate is not: reporting this as
        # an unlink would name a retirement that did not happen.
        print(f"Removed the local override for {found_key} (was {removed_path})")
        print(
            f"{found_key} remains declared in {config_path.name} at {committed_path}. "
            f"Remove it there to retire it."
        )
        return 0

    print(f"Unlinked {name} (was {found_key}: {removed_path})")
    return 0


# --- Private helpers ---


def _get_config_path(args: argparse.Namespace) -> Path | None:
    """Get config file path from args or by discovery."""
    if hasattr(args, "config") and args.config:
        return args.config
    return find_config_file(Path.cwd())


def _get_config_dir(args: argparse.Namespace) -> Path | None:
    """Get the directory containing the config file."""
    config_path = _get_config_path(args)
    if config_path and config_path.exists():
        return config_path.parent
    return None


def _get_scan_base(args: argparse.Namespace) -> Path | None:
    """Get the base directory to scan for associates.

    Uses git_root.parent if available, otherwise config_dir.parent.
    """
    git_root = getattr(args, "git_root", None)
    if git_root:
        return Path(git_root).parent

    config_dir = _get_config_dir(args)
    if config_dir:
        return config_dir.parent

    return None


def _find_by_name(name: str, args: argparse.Namespace) -> Path | None:
    """Search sibling directories for an associate by name.

    Args:
        name: Directory name or project name to find.
        args: Parsed arguments for context.

    Returns:
        Resolved Path if found, None otherwise.
    """
    scan_base = _get_scan_base(args)
    if scan_base is None:
        return None

    # Direct directory match
    candidate = scan_base / name
    if candidate.is_dir():
        result = discover_associate_from_path(candidate)
        if isinstance(result, Associate):
            return candidate

    # Scan all siblings for matching project.name
    for child in scan_base.iterdir():
        if not child.is_dir():
            continue
        result = discover_associate_from_path(child)
        if isinstance(result, Associate) and result.name == name:
            return child

    return None


def register_associate(
    config_dir: Path,
    repo_path: str,
    assoc_name: str,
    namespace: str,
    *,
    repo_root: Path,
    force: bool = False,
    config_path: Path | None = None,
) -> Registration:
    """Record an associate in `.elspais.local.toml` and say what was recorded.

    Implements: REQ-d00289-A, REQ-d00289-B, REQ-d00289-C, REQ-d00289-D, REQ-d00289-E

    Implements: REQ-d00290-A

    What is already recorded is read from the configuration as assembled,
    which is the whole of what a later run will see; the machine-local file
    is where a change is written, and nothing more. Asking the file that is
    about to be written what is recorded would answer differently for a
    declaration sitting in the committed file, which is the one thing an
    overlay may not change.

    The run decides in one direction and writes once at the end, so a
    refusal leaves the file exactly as it was:

      1. What does the configuration record under this name?
      2. Would the resulting configuration federate?
      3. Does the operator's instruction allow changing what is recorded?

    The federation is asked first because it answers the more fundamental
    question. A namespace two directories both claim is refused however
    the operator instructs (REQ-d00289-H), so reporting an entry-exists
    refusal over it would offer `-f` as a way past an obstacle `-f` does
    not move.

    Args:
        config_dir: Directory containing the config files.
        repo_path: Absolute path string of the repository to record.
        assoc_name: Name of the associate entry.
        namespace: Namespace the repository declares for itself.
        repo_root: Repository root that recorded relative paths resolve
            against. Required: under a worktree it is not the directory
            holding the configuration, and defaulting to that one resolves
            a recorded path against the wrong tree without saying so.
        force: Replace the path recorded for an entry that already exists.
        config_path: The main config file, read to plan the prospective
            federation.

    Returns:
        The outcome, carrying the path the configuration holds afterwards.
    """
    # Implements: REQ-d00290-A
    # Every entry the configuration holds, wherever it was written, read
    # once. A registration writes the machine-local file, but what counts
    # as already recorded is what a later run will read.
    resolved_path = config_path if config_path else find_config_file(config_dir)
    try:
        config = get_config(config_path=resolved_path, start_path=config_dir, quiet=True)
    except Exception as exc:  # noqa: BLE001 - reported, never raised at a user
        # Implements: REQ-d00289-I
        # This command is one of the ways a configuration gets repaired, so
        # meeting an unreadable one is ordinary. It is a fault the
        # configuration already held, and it is reported as one rather than
        # ending the run in a traceback.
        return Registration(
            kind=Outcome.WOULD_NOT_FEDERATE,
            name=assoc_name,
            namespace=namespace,
            target=repo_path,
            reason=str(exc),
            pre_existing=True,
        )

    recorded = _assembled_associates(config)
    existing = recorded.get(assoc_name)
    existing_path = existing.get("path", "") if existing else ""
    target = Path(repo_path).resolve()
    entry_moves = existing is not None and _resolve_recorded(existing_path, repo_root) != target

    # Implements: REQ-d00289-E, REQ-d00289-H
    # What may enter a federation is not decided here. The planner is
    # asked the question a build would ask (REQ-d00202-G), and a
    # membership it refuses is a registration this refuses -- so a
    # declaration is admitted exactly when a build would admit it. This
    # is asked even where there is nothing to write, since reporting "no
    # change" over a configuration that will not federate would be a run
    # that looked at a broken configuration and said nothing.
    refusal, pre_existing = _federation_refusal(
        config,
        assoc_name,
        repo_path,
        namespace,
        repo_root=repo_root,
    )
    if refusal is not None:
        return Registration(
            kind=Outcome.WOULD_NOT_FEDERATE,
            name=assoc_name,
            namespace=namespace,
            path=existing_path,
            previous_path=existing_path,
            target=repo_path,
            reason=refusal,
            pre_existing=pre_existing,
        )

    # Implements: REQ-d00289-C
    # The recorded path is a fact the invocation does not know it is
    # contradicting, so replacing it is a decision the operator makes
    # rather than an outcome they discover.
    if entry_moves and not force:
        return Registration(
            kind=Outcome.ENTRY_EXISTS,
            name=assoc_name,
            namespace=namespace,
            path=existing_path,
            previous_path=existing_path,
            target=repo_path,
        )

    if existing is not None and not entry_moves:
        # Implements: REQ-d00289-B
        return Registration(
            kind=Outcome.UNCHANGED,
            name=assoc_name,
            namespace=namespace,
            path=existing_path,
        )

    # Implements: REQ-d00290-A
    # The entry may be declared in the committed file and absent from the
    # one written here. Changing a value is what an overlay is for: the
    # entry is written locally, and the assembled result is the value given.
    local_path = _local_config(config_dir)
    doc, associates = _local_associates(local_path)
    _write_entry(associates, assoc_name, repo_path, namespace)
    local_path.write_text(tomlkit.dumps(doc), encoding="utf-8")

    return Registration(
        kind=Outcome.REPOINTED if entry_moves else Outcome.RECORDED,
        name=assoc_name,
        namespace=namespace,
        # Implements: REQ-d00289-A
        # Read back from the file, so the report states what a later run
        # will read rather than the argument meant to put it there.
        path=_recorded_path(local_path, assoc_name),
        previous_path=existing_path,
        target=repo_path,
    )


def _local_config(config_dir: Path) -> Path:
    """The machine-local file a registration writes."""
    return config_dir / ".elspais.local.toml"


def _local_associates(local_path: Path) -> tuple[Any, Any]:
    """The local document and its `[associates]` table, creating both if absent."""
    if local_path.exists():
        doc = parse_toml_document(local_path.read_text(encoding="utf-8"))
    else:
        doc = tomlkit.document()
    if "associates" not in doc:
        doc.add("associates", tomlkit.table())
    return doc, doc["associates"]


def _write_entry(associates: Any, name: str, repo_path: str, namespace: str) -> None:
    """Record an entry in the machine-local table, adding it if it is absent.

    Implements: REQ-d00290-A

    The entry being changed may be declared in the committed file and not
    here; writing it here is what an overlay does, and the assembled
    configuration then holds the value given.
    """
    entry = associates.get(name)
    if isinstance(entry, dict):
        entry["path"] = repo_path
        entry["namespace"] = namespace
        return
    fresh = tomlkit.table()
    fresh["path"] = repo_path
    fresh["namespace"] = namespace
    associates.add(name, fresh)


def _assembled_associates(config: dict[str, Any]) -> dict[str, Any]:
    """Every associate the configuration holds, however it was written.

    Implements: REQ-d00290-A

    Read from the assembled configuration rather than from the file a
    registration writes, so a declaration carried by the machine-local
    overlay and one committed alongside it are the same fact here.
    """
    table = config.get("associates") or {}
    return {n: e for n, e in table.items() if isinstance(e, dict)}


def _matching_entry(recorded: dict[str, Any], name: str) -> str | None:
    """The entry a name addresses: its key, its namespace, or its last path segment.

    Implements: REQ-d00290-A

    The entries searched are the assembled configuration's, so a name
    addresses the same entry whichever file declared it. Key and namespace
    match without regard to case; the path is matched on its last segment,
    which is how a directory is named on a command line.
    """
    wanted = name.lower()
    for key, entry in recorded.items():
        if (
            key == name
            or key.lower() == wanted
            or str(entry.get("namespace", "")).lower() == wanted
            or Path(str(entry.get("path", ""))).name == name
        ):
            return key
    return None


def _committed_path(config_path: Path | None, assoc_name: str) -> str:
    """The path the committed file records for an entry, or "" if it records none.

    Implements: REQ-d00289-A

    Nothing is decided here: which entries exist is settled by the
    assembled configuration, and this reads the one path a machine-local
    write cannot change so the report can state it.
    """
    if config_path is None or not config_path.exists():
        return ""
    doc = parse_toml_document(config_path.read_text(encoding="utf-8"))
    entry = doc.get("associates", {}).get(assoc_name, {})
    return str(entry.get("path", "")) if isinstance(entry, dict) else ""


def _resolve_recorded(path_str: str, base: Path) -> Path:
    """Resolve a recorded path, which may be relative to the repository root."""
    recorded = Path(path_str)
    if not recorded.is_absolute():
        return (base / recorded).resolve()
    return recorded.resolve()


def _recorded_path(local_path: Path, assoc_name: str) -> str:
    """Read back the path the configuration holds for an entry.

    Implements: REQ-d00289-A

    The report states what a later run will read, so it is taken from the
    file rather than from the argument that was meant to put it there.
    """
    doc = parse_toml_document(local_path.read_text(encoding="utf-8"))
    entry = doc.get("associates", {}).get(assoc_name, {})
    return entry.get("path", "") if isinstance(entry, dict) else ""


def _contested_candidates(
    found: list[tuple[Path, Associate]],
) -> dict[str, tuple[str, ...]]:
    """The candidates of one scan claiming one namespace, and their rivals.

    Implements: REQ-d00289-G

    One namespace names one member (REQ-d00202-G), so two candidates
    declaring one namespace are two answers to a question that admits
    one. Deciding as the scan went would record whichever it reached
    first and refuse the rest, leaving directory order to stand for a
    choice the operator never made -- an instruction to replace what is
    recorded was given about neither. So the whole scan is judged before
    any of it is written, and none of a contesting group is recorded.

    A shared *name* is not this rule's business: the entry key is a
    label, and two candidates declaring different namespaces are two
    members whose identifiers cannot be confused.

    Returns a mapping from each contested directory to the others
    contesting it.
    """
    by_namespace: dict[str, list[str]] = {}
    for repo_path, assoc in found:
        by_namespace.setdefault(assoc.code, []).append(str(repo_path))

    contested: dict[str, tuple[str, ...]] = {}
    for paths in by_namespace.values():
        unique = sorted(set(paths))
        if len(unique) < 2:
            continue
        for path in unique:
            contested[path] = tuple(o for o in unique if o != path)
    return contested


def _federation_refusal(
    config: dict[str, Any],
    assoc_name: str,
    repo_path: str,
    namespace: str,
    *,
    repo_root: Path,
) -> tuple[str | None, bool]:
    """Why the federation would refuse this declaration, and whose fault it is.

    Implements: REQ-d00289-E, REQ-d00289-I

    The planner is the one authority on what enters a federation
    (REQ-d00202-G), so this asks it, and puts the answer to the same
    refusal a build applies, rather than deciding anything. It is
    planned twice: a configuration that already will not federate refuses
    every candidate put to it, and reporting that against the candidate
    sends the operator to the wrong directory.

    Returns:
        The reason a federation would be refused and whether the
        configuration already held that fault, or ``(None, False)``.
    """
    from elspais.graph.federation_plan import plan_federation, refuse_unreadable

    recorded = config.get("associates") or {}

    try:
        refuse_unreadable(plan_federation({**config, "associates": recorded}, repo_root))
    except FederationError as exc:
        return str(exc), True

    prospective = {**recorded, assoc_name: {"path": repo_path, "namespace": namespace}}
    try:
        refuse_unreadable(plan_federation({**config, "associates": prospective}, repo_root))
    except FederationError as exc:
        return str(exc), False

    return None, False
