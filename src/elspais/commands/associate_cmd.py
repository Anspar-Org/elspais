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
from pathlib import Path
from typing import Any

import tomlkit

from elspais.associates import Associate, discover_associate_from_path
from elspais.config import find_config_file, parse_toml_document
from elspais.graph.federated import FederationError


@dataclass
class Registration:
    """What a registration run recorded, in the terms it is reported in.

    Implements: REQ-d00289-A, REQ-d00289-B

    `path` is the path the configuration holds for the entry once the run
    has returned -- for a refusal, the path that was already there.
    """

    kind: str
    """One of: recorded, unchanged, repointed, replaced, refused."""

    name: str
    namespace: str
    path: str
    previous_path: str = ""
    previous_name: str = ""
    target: str = ""
    reason: str = ""
    pre_existing_fault: bool = False
    """The reason was true of the configuration before this registration."""

    scan_rival: bool = False
    """Another candidate of this same run already stands for the entry."""

    twin_name: str = ""
    twin_path: str = ""
    """An entry recording this namespace at another directory."""

    declared_in: str = ""
    """The configuration file holding an entry this run cannot retire."""

    retired_name: str = ""
    retired_path: str = ""
    """An entry this run removed, its namespace now recorded elsewhere."""

    @property
    def refused(self) -> bool:
        return self.kind == "refused"

    def report_lines(self) -> list[str]:
        """The lines describing this outcome, first line first."""
        if self.kind in ("recorded", "unchanged", "repointed", "replaced"):
            return self._recorded_lines()
        if self.reason == "entry-exists":
            # Implements: REQ-d00289-C
            lines = [
                f"Refused: {self.name} is already registered at {self.previous_path}, "
                f"and nothing was changed.",
            ]
            if self.twin_name:
                # Implements: REQ-d00289-H
                lines.append(
                    f"{self.twin_name} at {self.twin_path} records the namespace "
                    f"{self.namespace} too."
                )
            lines += [
                f"Use -f to replace that path with {self.target}.",
                "Run 'elspais associate --list' to see the current registrations.",
            ]
            return lines
        if self.reason == "same-namespace-shared":
            # Implements: REQ-d00289-H
            return [
                f"Refused: the namespace {self.namespace} is already registered to "
                f"{self.previous_name} at {self.previous_path}, and nothing was changed.",
                f"That entry is declared in {self.declared_in}, which this command does "
                f"not write, so -f cannot replace it.",
                f"Edit {self.declared_in} to point {self.previous_name} elsewhere, or "
                f"give this repository a namespace of its own.",
            ]
        if self.reason == "same-namespace":
            # Implements: REQ-d00289-H
            return [
                f"Refused: the namespace {self.namespace} is already registered to "
                f"{self.previous_name} at {self.previous_path}, and nothing was changed.",
                f"Use -f to record {self.target} instead, replacing that entry.",
                "Run 'elspais associate --list' to see the current registrations.",
            ]
        if self.scan_rival:
            # Implements: REQ-d00289-G
            return [
                f"Refused: {self.target} and {self.previous_path} are two directories "
                f"for one entry in this scan ({self.reason}), and nothing was changed.",
                "Register the one you mean by path.",
            ]
        if self.pre_existing_fault:
            # Implements: REQ-d00289-I
            return [
                f"Refused: this configuration does not federate as it stands, before "
                f"{self.name} at {self.target} is considered. Nothing was changed.",
                f"  {self.reason}",
            ]
        return [
            f"Refused: {self.name} at {self.target} would not federate, and nothing was changed.",
            f"  {self.reason}",
        ]

    def _recorded_lines(self) -> list[str]:
        """The lines for a run that wrote, or deliberately did not."""
        if self.kind == "recorded":
            lines = [f"Linked {self.name} ({self.namespace}) at {self.path}"]
        elif self.kind == "unchanged":
            lines = [f"No change: {self.name} ({self.namespace}) stays registered at {self.path}"]
        elif self.kind == "repointed":
            lines = [
                f"Repointed {self.name} ({self.namespace}): was {self.previous_path}, "
                f"now registered at {self.path}"
            ]
        else:
            # Implements: REQ-d00289-H
            lines = [
                f"Replaced {self.previous_name} at {self.previous_path} with "
                f"{self.name} ({self.namespace}) at {self.path}"
            ]
        if self.retired_name:
            # Implements: REQ-d00289-H
            lines.append(
                f"Removed {self.retired_name} at {self.retired_path}: "
                f"the namespace {self.namespace} is now recorded as {self.name}."
            )
        return lines


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
        repo_root=gr,
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

    # Implements: REQ-d00289-F
    # A candidate the tool will not record is one candidate: the scan
    # reports it and carries on, so the state of the ones around it is
    # still on the screen when the operator reads the refusal.
    recorded_here: list[tuple[str, str, str]] = []
    for repo_path, assoc in found:
        rival = _scan_rival(recorded_here, assoc.name, assoc.code, repo_path)
        if rival is not None:
            # Implements: REQ-d00289-G
            # Two candidates of one scan stand for one entry. An instruction
            # to replace what was recorded cannot decide between them -- it
            # was given about neither -- so the second is refused rather than
            # left to win by sort order.
            rival_name, rival_path, why = rival
            outcome = Registration(
                kind="refused",
                name=assoc.name,
                namespace=assoc.code,
                path=rival_path,
                previous_path=rival_path,
                previous_name=rival_name,
                target=str(repo_path),
                reason=why,
                scan_rival=True,
            )
        else:
            outcome = register_associate(
                config_dir,
                str(repo_path),
                assoc.name,
                assoc.code,
                repo_root=gr,
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

        recorded_here.append((assoc.name, assoc.code, str(repo_path)))
        if outcome.kind == "unchanged":
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
    # Implements: REQ-d00202-A, REQ-d00212-K
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

    print(f"{'Name':<20} {'Prefix':<10} {'Status':<12} Path")
    print("-" * 72)

    for assoc_name, assoc_info in associates.items():
        path_str = assoc_info["path"]
        repo_path = Path(path_str)
        if not repo_path.is_absolute() and git_root:
            repo_path = Path(git_root) / repo_path
        if not repo_path.exists():
            print(f"{assoc_name:<20} {'?':<10} {'NOT FOUND':<12} {path_str}")
            continue

        result = discover_associate_from_path(repo_path)
        if isinstance(result, str):
            print(f"{assoc_name:<20} {'?':<10} {'BROKEN':<12} {path_str}")
        else:
            spec_dir = repo_path / result.spec_path
            status = "OK" if spec_dir.exists() else "NO SPEC"
            print(f"{result.name:<20} {result.code:<10} {status:<12} {path_str}")

    return 0


def cmd_unlink(args: argparse.Namespace) -> int:
    """Remove an associate link by name.

    Finds the matching entry in .elspais.local.toml and removes it.

    Args:
        args: Parsed arguments with .unlink set to the name.

    Returns:
        Exit code.
    """
    name = args.unlink
    config_dir = _get_config_dir(args)
    if config_dir is None:
        print("Error: No configuration directory found.", file=sys.stderr)
        return 1

    local_path = config_dir / ".elspais.local.toml"
    if not local_path.exists():
        print(f"Error: No associate '{name}' found (no local config).", file=sys.stderr)
        return 1

    # Implements: REQ-d00212-K
    doc = parse_toml_document(local_path.read_text(encoding="utf-8"))
    associates = doc.get("associates", {})

    if not associates or not any(isinstance(v, dict) for v in associates.values()):
        print(f"Error: No associate '{name}' found.", file=sys.stderr)
        return 1

    # Find matching entry by name, namespace code, or path basename
    found_key = None
    found_path = None
    name_lower = name.lower()

    for assoc_key, entry in associates.items():
        if not isinstance(entry, dict):
            continue
        path_str = entry.get("path", "")
        ns = entry.get("namespace", "")

        if (
            assoc_key == name
            or assoc_key.lower() == name_lower
            or ns.lower() == name_lower
            or Path(path_str).name == name
        ):
            found_key = assoc_key
            found_path = path_str
            break

    if found_key is None:
        print(f"Error: No associate '{name}' found in linked associates.", file=sys.stderr)
        return 1

    # Remove the entry
    del associates[found_key]
    # Write back
    local_path.write_text(tomlkit.dumps(doc), encoding="utf-8")

    print(f"Unlinked {name} (was {found_key}: {found_path})")
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
    repo_root: Path | None = None,
    force: bool = False,
    config_path: Path | None = None,
) -> Registration:
    """Record an associate in `.elspais.local.toml` and say what was recorded.

    Implements: REQ-d00289-A, REQ-d00289-B, REQ-d00289-C, REQ-d00289-D, REQ-d00289-E

    The registration is decided against the entries already on disk, checked
    against the federation those entries would form, and only then written,
    so a refusal leaves the file exactly as it was.

    Args:
        config_dir: Directory containing the config files.
        repo_path: Absolute path string of the repository to record.
        assoc_name: Name of the associate entry.
        namespace: Namespace the repository declares for itself.
        repo_root: Repository root for resolving existing relative paths.
        force: Replace the path recorded for an entry that already exists.
        config_path: The main config file, read to plan the prospective
            federation.

    Returns:
        The outcome, carrying the path the configuration holds afterwards.
    """
    # Implements: REQ-d00212-K
    local_path = config_dir / ".elspais.local.toml"

    if local_path.exists():
        doc = parse_toml_document(local_path.read_text(encoding="utf-8"))
    else:
        doc = tomlkit.document()

    if "associates" not in doc:
        doc.add("associates", tomlkit.table())

    associates = doc["associates"]

    # A recorded relative path is written against the repository root, so
    # that is what it is read against -- never the current directory, which
    # under a worktree is somewhere else entirely (REQ-p00005-F).
    base = repo_root or config_dir
    resolved_new = Path(repo_path).resolve()
    existing_entry = None
    existing_path = ""
    by_path: tuple[str, dict] | None = None

    # The whole table is read before anything is decided: an entry under
    # this name and an entry under this path are different answers, and
    # which one the operator gets must not depend on which was written
    # into the file first.
    for existing_name, entry in associates.items():
        if not isinstance(entry, dict):
            continue
        entry_path = entry.get("path", "")
        if existing_name == assoc_name:
            existing_entry = existing_name
            existing_path = entry_path
        elif by_path is None and _resolve_recorded(entry_path, base) == resolved_new:
            by_path = (existing_name, entry)

    if existing_entry is None and by_path is not None:
        # This directory is already recorded, under another name; the entry
        # that answers for it is that one.
        other_name, other_entry = by_path
        return Registration(
            kind="unchanged",
            name=other_name,
            namespace=other_entry.get("namespace", ""),
            path=other_entry.get("path", ""),
        )

    entry_moves = existing_entry is not None and _resolve_recorded(existing_path, base) != (
        resolved_new
    )

    # Implements: REQ-d00289-E, REQ-d00289-H
    # What may enter a federation is not decided here. The planner is
    # asked the question a build would ask (REQ-d00202-G), and a
    # membership it refuses is a registration this refuses -- so a
    # declaration is admitted exactly when a build would admit it.
    verdict = _federation_verdict(
        config_dir,
        assoc_name,
        repo_path,
        namespace,
        repo_root=repo_root,
        config_path=config_path,
    )

    # One namespace names one member, so an entry already recording this
    # namespace at another directory is a second answer to a question that
    # admits one. It is a separate obstacle from an entry under this name,
    # and both can stand at once.
    twin_name, twin_path, twin_where = verdict.rival(
        local_entries=associates, main_entries=_main_associates(config_path)
    )
    # Only an entry this file holds alone can be retired by rewriting this
    # file. Anything else is reported and left standing, because removing
    # the local entry would leave the declaration that actually collides.
    if twin_where == "main":
        return Registration(
            kind="refused",
            name=assoc_name,
            namespace=namespace,
            path=twin_path,
            previous_path=twin_path,
            previous_name=twin_name,
            target=repo_path,
            reason="same-namespace-shared",
            declared_in=str(config_path) if config_path else ".elspais.toml",
        )
    if twin_where != "local":
        twin_name, twin_path = "", ""

    if existing_entry is not None and not entry_moves and not twin_name and not verdict.refusal:
        return Registration(
            kind="unchanged",
            name=existing_entry,
            namespace=namespace,
            path=existing_path,
        )

    if not force:
        # Where -f WAS given and the rival still cannot be retired, this
        # block is skipped deliberately: the refusal below carries the
        # collision's own reason, rather than repeating an instruction the
        # operator has already followed.
        if entry_moves:
            return Registration(
                kind="refused",
                name=existing_entry or assoc_name,
                namespace=namespace,
                path=existing_path,
                previous_path=existing_path,
                previous_name=existing_entry or "",
                target=repo_path,
                reason="entry-exists",
                twin_name=twin_name,
                twin_path=twin_path,
            )
        if twin_name:
            return Registration(
                kind="refused",
                name=assoc_name,
                namespace=namespace,
                path=twin_path,
                previous_path=twin_path,
                previous_name=twin_name,
                target=repo_path,
                reason="same-namespace",
            )

    refusal, pre_existing = verdict.refusal, verdict.pre_existing
    if refusal is not None and twin_name and force:
        # The rival is going; ask again without it, so its collision is
        # not reported against a registration that retires it.
        refusal, pre_existing = _federation_verdict(
            config_dir,
            assoc_name,
            repo_path,
            namespace,
            repo_root=repo_root,
            config_path=config_path,
            retiring=twin_name,
        ).as_reason()
    twin = (twin_name, twin_path) if twin_name else None

    if refusal is not None:
        return Registration(
            kind="refused",
            name=assoc_name,
            namespace=namespace,
            path=existing_path,
            previous_path=existing_path,
            target=repo_path,
            reason=refusal,
            pre_existing_fault=pre_existing,
        )

    # Forced past the obstacles: one entry is left holding this namespace,
    # and it is the one the operator named. The entry that recorded the
    # other directory goes with it -- excluding it from the plan above and
    # leaving it in the file would be two answers again.
    if twin is not None:
        del associates[twin_name]

    if existing_entry is not None:
        associates[existing_entry]["path"] = repo_path
        associates[existing_entry]["namespace"] = namespace
        local_path.write_text(tomlkit.dumps(doc), encoding="utf-8")
        return Registration(
            kind="repointed" if entry_moves else "unchanged",
            name=existing_entry,
            namespace=namespace,
            path=_recorded_path(local_path, existing_entry),
            previous_path=existing_path,
            retired_name=twin_name,
            retired_path=twin_path,
        )

    entry = tomlkit.table()
    entry["path"] = repo_path
    entry["namespace"] = namespace
    associates.add(assoc_name, entry)
    local_path.write_text(tomlkit.dumps(doc), encoding="utf-8")

    return Registration(
        kind="replaced" if twin is not None else "recorded",
        name=assoc_name,
        namespace=namespace,
        path=_recorded_path(local_path, assoc_name),
        previous_name=twin_name,
        previous_path=twin_path,
    )


def _main_associates(config_path: Path | None) -> dict[str, Any]:
    """The `[associates]` table of the main configuration file.

    Implements: REQ-d00289-H

    Read separately from the merged configuration because the question is
    not what the federation holds but which FILE holds it: a registration
    writes only the machine-local file, so an entry declared here is one
    it cannot retire.
    """
    if config_path is None or not config_path.exists():
        return {}
    try:
        doc = parse_toml_document(config_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - an unreadable main config is not this
        return {}  # run's fault to report; the planner says so already.
    table = doc.get("associates", {})
    return dict(table) if isinstance(table, dict) else {}


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


def _scan_rival(
    recorded_here: list[tuple[str, str, str]],
    assoc_name: str,
    namespace: str,
    repo_path: Path,
) -> tuple[str, str, str] | None:
    """A candidate of this same run that stands for the entry in hand.

    Implements: REQ-d00289-G

    Returns the rival's entry name, the directory it was recorded from,
    and why it is the same entry -- or None.
    """
    for rival_name, rival_namespace, rival_path in recorded_here:
        if rival_path == str(repo_path):
            continue
        if rival_name == assoc_name:
            return (rival_name, rival_path, f"both declare the name '{assoc_name}'")
        if rival_namespace == namespace:
            return (rival_name, rival_path, f"both declare the namespace '{namespace}'")
    return None


@dataclass
class FederationVerdict:
    """What the federation planner says about a prospective declaration.

    Implements: REQ-d00289-E, REQ-d00289-H, REQ-d00289-I

    The planner is the single authority on what enters a federation
    (REQ-d00202-G); this carries its answer in a form a registration can
    act on -- which side of a namespace collision is the one already
    recorded, and whether the fault was there before this registration.
    """

    refusal: str | None = None
    pre_existing: bool = False
    conflict: Any = None
    """The NamespaceConflict raised, where that is what refused it."""

    candidate: Path | None = None

    def as_reason(self) -> tuple[str | None, bool]:
        return self.refusal, self.pre_existing

    def rival(self, local_entries: Any = None, main_entries: Any = None) -> tuple[str, str, str]:
        """The entry already holding this namespace, and which file holds it.

        Returns the entry's name, the path recorded for it, and where it
        is declared -- ``local`` for one this run could retire, ``main``
        for one declared in the main configuration, and ``""`` where the
        collision is not this run's to settle at all (between two other
        members, or declared by another repository).

        A registration writes only the machine-local file, so an entry
        the main configuration declares cannot be retired by removing the
        local one: the declaration would come back on the next read. An
        entry declared in BOTH is the same case -- deleting the override
        leaves the main entry standing -- so only an entry the local file
        holds alone is reported as retireable.
        """
        if self.conflict is None:
            return ("", "", "")
        sides = (
            (self.conflict.first_root, self.conflict.first_declaration),
            (self.conflict.second_root, self.conflict.second_declaration),
        )
        if not any(root == self.candidate for root, _ in sides):
            return ("", "", "")
        for root, declaration in sides:
            if root == self.candidate:
                continue
            # (root_repo, entry) -- anything longer was declared by a
            # repository other than the one being configured.
            if len(declaration) != 2:
                continue
            name = declaration[-1]
            in_main = isinstance((main_entries or {}).get(name), dict)
            local = (local_entries or {}).get(name)
            if isinstance(local, dict) and not in_main:
                return (name, local.get("path", ""), "local")
            if in_main:
                # The colliding directory is the one the federation
                # reached, which a local override may have redirected --
                # the path written in the main file can be a directory
                # that is not in the federation at all.
                return (name, str(root), "main")
            return (name, str(root), "")
        return ("", "", "")


def _federation_verdict(
    config_dir: Path,
    assoc_name: str,
    repo_path: str,
    namespace: str,
    *,
    repo_root: Path | None = None,
    config_path: Path | None = None,
    retiring: str = "",
) -> FederationVerdict:
    """Ask the planner whether this declaration may join, and why not.

    Implements: REQ-d00289-E, REQ-d00289-I

    It is planned twice: a configuration that already will not federate
    refuses every candidate put to it, and reporting that against the
    candidate sends the operator to the wrong directory.

    Args:
        retiring: An entry this registration would remove, left out of
            both plans so a member about to go is not what refuses its
            successor.
    """
    from elspais.config import get_config
    from elspais.graph.federation_plan import NamespaceConflict, plan_federation

    resolved_path = config_path if config_path else find_config_file(config_dir)
    config = get_config(config_path=resolved_path, start_path=config_dir, quiet=True)
    root = repo_root or config_dir
    candidate = Path(repo_path).resolve()

    recorded = {
        name: entry for name, entry in (config.get("associates") or {}).items() if name != retiring
    }

    try:
        plan_federation({**config, "associates": recorded}, root)
    except FederationError as exc:
        # A standing collision this registration is itself one side of is
        # still this run's to settle; one between other members is not.
        return FederationVerdict(
            refusal=str(exc),
            pre_existing=True,
            conflict=exc if isinstance(exc, NamespaceConflict) else None,
            candidate=candidate,
        )

    prospective = {**recorded, assoc_name: {"path": repo_path, "namespace": namespace}}
    try:
        plan_federation({**config, "associates": prospective}, root)
    except NamespaceConflict as exc:
        return FederationVerdict(refusal=str(exc), conflict=exc, candidate=candidate)
    except FederationError as exc:
        return FederationVerdict(refusal=str(exc), candidate=candidate)

    return FederationVerdict(candidate=candidate)
