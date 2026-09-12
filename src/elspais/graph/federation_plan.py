# Implements: REQ-d00202-D+E+F+G+I+J+K+L, REQ-d00203-B
"""Resolve a federation's membership from declared associates.

Planning is separated from building: this module answers "which
repositories are in this federation, and what is each one's
configuration?" without constructing a single graph.  ``build_graph()``
turns the answer into ``RepoEntry`` objects.

Declarations are walked depth-first from the root repository.  A member
is identified by the namespace its declaration names (REQ-d00202-G):
one namespace names one member, REQ-d00202-L binds that namespace to
what the repository at that path declares of itself, and two directories
claiming one namespace are a collision to report rather than one member
to guess at.  Two directories declaring different namespaces are two
members, however closely related the directories are -- their
identifiers cannot be confused.

Whether the walk has been somewhere before is asked of the DIRECTORY,
which is answerable before the repository there has been read: the same
directory reached again up the chain in hand is a cycle, and reached
again across the walk it is a diamond converging on one member.  The
namespace is what identifies a member once it HAS been read -- one
namespace found at two directories is the collision of REQ-d00202-K --
and a declaration that could not be read claims none at all
(REQ-d00202-M).

This module is the one authority on what enters a federation.  A surface
recording a declaration asks it the same question the build asks, so a
registration is admitted exactly when a build would admit it.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from elspais.graph.federated import FederationError

__all__ = [
    "FederationCycleError",
    "NamespaceConflict",
    "PlannedRepo",
    "declared_associates",
    "repository_origin",
    "plan_federation",
    "plan_federation_or_error",
]


def declared_associates(config: dict[str, Any], repo_root: Path) -> dict[str, dict]:
    """Read one repository's associate declarations for federation use.

    A declaration the config layer refuses is a federation failure like any
    other, so it is reported through the one error family every planning
    surface already handles, naming the repository whose config holds it.
    """
    from elspais.config import get_associates_config

    try:
        return get_associates_config(config, repo_root=repo_root)
    except ValueError as exc:
        raise FederationError(f"In the configuration at {repo_root}: {exc}") from exc


class FederationCycleError(FederationError):
    """Raised when associate declarations form a directed cycle."""


class NamespaceConflict(FederationError):
    """Raised when two directories of one federation claim one namespace.

    Implements: REQ-d00202-K

    Carries the two sides so a surface that can act on one of them --
    a registration about to record the second, say -- can tell which is
    which instead of parsing the message.
    """

    def __init__(
        self,
        namespace: str,
        first: tuple[Path, tuple[str, ...]],
        second: tuple[Path, tuple[str, ...]],
    ) -> None:
        self.namespace = namespace
        self.first_root, self.first_declaration = first
        self.second_root, self.second_declaration = second
        super().__init__(
            f"Two directories are federated under the namespace '{namespace}': "
            f"{self.first_root} (declared via {' -> '.join(self.first_declaration)}) "
            f"and {self.second_root} (declared via "
            f"{' -> '.join(self.second_declaration)}). A namespace identifies one "
            f"member's identifiers, so give each member its own."
        )


@dataclass(frozen=True)
class PlannedRepo:
    """One repository's place in a federation, before its graph is built.

    Attributes:
        name: The root repo's ``[project].name``, or the key under
            ``[associates]`` that first reached this repository.
        repo_root: Resolved absolute path to the repository.
        config: The repository's configuration, or None when it could
            not be loaded.
        git_origin: The repository's git origin as detected on disk,
            normalized for comparison. None when there is no origin.
        error: Why ``config`` is None. None when the repo loaded.
        declaration_path: Repository names from the root to this
            repository inclusive, along the chain that first reached it.
    """

    name: str
    repo_root: Path
    config: dict[str, Any] | None
    git_origin: str | None
    error: str | None
    declaration_path: tuple[str, ...]


def _normalize_origin(url: str) -> str:
    """Reduce an origin URL to a comparable form.

    The same repository is routinely addressed as ``git@host:org/repo.git``
    and ``https://host/org/repo``; both name one repository, so a surface
    comparing what two members were cloned from needs one spelling. This
    decides no membership -- a member is its namespace (REQ-d00202-G).
    """
    url = url.strip().rstrip("/")
    if url.endswith(".git"):
        url = url[: -len(".git")]
    # scp-style "git@host:org/repo" -> "host/org/repo"
    if "://" not in url and "@" in url and ":" in url:
        _user, _, hostpath = url.partition("@")
        host, _, path = hostpath.partition(":")
        url = f"{host}/{path}"
    else:
        for scheme in ("https://", "http://", "ssh://", "git://"):
            if url.startswith(scheme):
                url = url[len(scheme) :]
                break
        if "@" in url:
            url = url.partition("@")[2]
    return url.lower()


def repository_origin(repo_root: Path) -> str | None:
    """Return the normalized origin of the repository rooted at ``repo_root``.

    Recorded on each member and published by reporting surfaces; it
    settles nothing about membership. Answers only for a directory that
    *is* a repository root, because git answers from the enclosing
    repository for any subdirectory -- so every directory inside one
    repository would otherwise report that repository's origin as its
    own.
    """
    from elspais.utilities.git import _clean_git_env

    def _git(*args: str) -> str | None:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=repo_root,
                capture_output=True,
                text=True,
                env=_clean_git_env(),
                check=False,
            )
        except OSError:
            return None
        return result.stdout.strip() if result.returncode == 0 else None

    toplevel = _git("rev-parse", "--show-toplevel")
    # Both sides resolved: a caller may name the directory any way that
    # reaches it, and "." is not unequal to the path git prints for it.
    if not toplevel or Path(toplevel).resolve() != Path(repo_root).resolve():
        return None
    origin = _git("remote", "get-url", "origin")
    return _normalize_origin(origin) if origin else None


def _assert_declared_namespace(
    name: str, assoc_path: Path, declared_ns: str, found_ns: str
) -> None:
    """Hold a declaration to the namespace the repository there declares.

    Implements: REQ-d00202-L

    Asked wherever a declaration meets a repository that has been read --
    on loading it, and on converging onto one already loaded -- because a
    mismatch is a property of the declaration, and which of two
    declarations reached the directory first must not decide whether it is
    reported.
    """
    if declared_ns and found_ns and declared_ns != found_ns:
        raise FederationError(
            f"Associate '{name}' at {assoc_path} declares the namespace "
            f"'{declared_ns}', but the repository there declares "
            f"'{found_ns}'. Point the declaration at the repository it "
            f"means, or correct the namespace it names."
        )


def _error_identity(repo_root: Path, declaration: tuple[str, ...]) -> str:
    """Identify a declaration that could not be read, uniquely to itself.

    Implements: REQ-d00202-M, REQ-d00202-N

    Keyed by the declaration as well as the directory, because two
    declarations pointing at one unreadable path are two faults to report:
    collapsing them would have an operator fix one, re-run, and meet the
    other.
    """
    return f"\x00error:{repo_root}\x00{' -> '.join(declaration)}"


def _path_identity(repo_root: Path) -> str:
    """Identify a member that has claimed no namespace, by its directory.

    Implements: REQ-d00202-M

    A declaration that could not be read, and the root repository where it
    declares none, are placed by the one thing known about them. The prefix
    cannot occur in a namespace, so such a key never meets a real one.
    """
    return f"\x00path:{repo_root}"


def _identity(declared_namespace: str, repo_root: Path) -> str:
    """Identify a member that has been read, for collision detection.

    Implements: REQ-d00202-G

    The namespace a declaration names is the key. A declaration without
    one is refused before it reaches here (REQ-d00202-B), but a root
    repository that declares none still has to be placed, so it falls
    back to its directory -- the one case where nothing has been claimed.
    """
    return declared_namespace or _path_identity(repo_root)


def plan_federation(
    root_config: dict[str, Any],
    root_repo_root: Path,
    *,
    strict: bool = False,
    config_loader: Callable[..., dict[str, Any]] | None = None,
) -> list[PlannedRepo]:
    """Resolve every repository reachable from ``root_config``.

    Args:
        root_config: The invoking repository's configuration.
        root_repo_root: The invoking repository's root directory.
        strict: Raise on a repository that cannot be loaded instead of
            recording it as an error entry.
        config_loader: Override for config loading, for tests.

    Returns:
        The root repository first, then every reachable repository in
        depth-first declaration order.  A repository that could not be
        loaded is present with ``config=None`` and an ``error``.

    Raises:
        FederationCycleError: Declarations form a directed cycle.
        FederationError: A repository could not be loaded and
            ``strict`` is set.
    """
    from elspais.config import get_config

    loader = config_loader or get_config

    planned: list[PlannedRepo] = []
    resolved: dict[str, PlannedRepo] = {}
    by_root: dict[Path, PlannedRepo] = {}
    by_name: dict[str, PlannedRepo] = {}

    def _declared_namespace(config: dict[str, Any] | None) -> str:
        return (config or {}).get("project", {}).get("namespace", "") or ""

    root_root = Path(root_repo_root).resolve()
    root_name = root_config.get("project", {}).get("name", "") or str(root_root.name)
    root_identity = _identity(_declared_namespace(root_config), root_root)
    root_entry = PlannedRepo(
        name=root_name,
        repo_root=root_root,
        config=root_config,
        git_origin=repository_origin(root_root),
        error=None,
        declaration_path=(root_name,),
    )
    planned.append(root_entry)
    resolved[root_identity] = root_entry
    by_root[root_root] = root_entry
    by_name[root_name] = root_entry

    def _record(entry: PlannedRepo, identity: str) -> None:
        # Only a repository that was read stands for its directory. An
        # entry recording a fault is not a member the walk can converge
        # on, and must not stop a later declaration at that path being
        # reported in its own right.
        if entry.config is not None:
            by_root[entry.repo_root] = entry
        # A federation keys repositories by name, so two repositories
        # arriving under one name would leave only the later of them
        # reachable -- the earlier repo's requirements would resolve
        # against the wrong config and its graph would never be read.
        # One declaration table cannot collide with itself, so this can
        # only happen once declarations from several repos are combined.
        clash = by_name.get(entry.name)
        if clash is not None:
            raise FederationError(
                f"Two repositories are federated under the name '{entry.name}': "
                f"{clash.repo_root} (declared via {' -> '.join(clash.declaration_path)}) "
                f"and {entry.repo_root} (declared via "
                f"{' -> '.join(entry.declaration_path)}). Rename one declaration."
            )
        by_name[entry.name] = entry

        planned.append(entry)
        resolved[identity] = entry

    def _visit(
        parent_config: dict[str, Any],
        parent_root: Path,
        declaration_path: tuple[str, ...],
        on_path: dict[Path, str],
    ) -> None:
        associates = declared_associates(parent_config, parent_root)
        for name, info in associates.items():
            assoc_path = Path(parent_root, info["path"]).resolve()
            child_path = declaration_path + (name,)

            # Implements: REQ-d00202-E
            # A cycle is the same directory reached again up the chain in
            # hand.  Asked of the directory rather than of the namespace,
            # it is answerable before the repository there has been read --
            # which it must be, since reaching it again is the reason the
            # walk would not terminate.
            if assoc_path in on_path:
                chain = " -> ".join(list(on_path.values()) + [name])
                raise FederationCycleError(
                    f"Associate declarations form a cycle: {chain}. "
                    f"Dependency direction orders federation resolution, so a "
                    f"repository cannot be reached through itself."
                )

            # Implements: REQ-d00202-F
            # One directory reached by two chains is one member: the
            # diamond converges here, before anything is read a second
            # time.  The declaration is still held to the namespace that
            # member declares -- the config is already in hand, and
            # skipping the check would let the order declarations are
            # reached in decide whether a mismatch is reported.
            converged = by_root.get(assoc_path)
            if converged is not None:
                _assert_declared_namespace(
                    name,
                    assoc_path,
                    info.get("namespace") or "",
                    _declared_namespace(converged.config),
                )
                continue

            # Implements: REQ-d00202-M
            # Whether the repository can be read is settled before it is
            # allowed to claim a namespace.  A declaration pointing at
            # nothing has said nothing about a namespace, and reporting it
            # as a claimant would name a collision with a directory that
            # is not there instead of the declaration that points nowhere.
            # An error entry is keyed by its own declaration, so two
            # declarations at one unreadable path are two reported faults
            # and neither is mistaken for a member.
            identity = _error_identity(assoc_path, child_path)

            if not assoc_path.exists():
                reason = f"Path does not exist: {assoc_path}"
                if strict:
                    raise FederationError(f"Associate '{name}' path does not exist: {assoc_path}")
                # Nothing is there to have an origin.
                _record(
                    PlannedRepo(name, assoc_path, None, None, reason, child_path),
                    identity,
                )
                continue

            # Implements: REQ-d00203-B
            # A member's configuration is the one at its own root. The
            # ordinary loader walks up to a parent and falls back to
            # defaults, which would let a directory holding only spec files
            # join as a member configured by something above it -- and then
            # report the namespace it inherited as one it declared.
            if not (assoc_path / ".elspais.toml").exists():
                reason = f"No .elspais.toml at {assoc_path}"
                if strict:
                    raise FederationError(f"Associate '{name}': {reason}")
                _record(
                    PlannedRepo(
                        name, assoc_path, None, repository_origin(assoc_path), reason, child_path
                    ),
                    identity,
                )
                continue
            try:
                assoc_config = loader(None, assoc_path, quiet=True)
            except Exception as exc:  # noqa: BLE001 - reported, never swallowed
                reason = f"Configuration at {assoc_path} could not be loaded: {exc}"
                if strict:
                    raise FederationError(f"Associate '{name}': {reason}") from exc
                _record(
                    PlannedRepo(
                        name, assoc_path, None, repository_origin(assoc_path), reason, child_path
                    ),
                    identity,
                )
                continue

            # Implements: REQ-d00202-L
            # A declaration does not name a second namespace for the
            # repository -- it states the namespace its author expected to
            # find there.  A mismatch means the declaration points
            # somewhere its author did not intend, which is a mistake to
            # report rather than a preference to reconcile.
            _assert_declared_namespace(
                name,
                assoc_path,
                info.get("namespace") or "",
                _declared_namespace(assoc_config),
            )

            # Implements: REQ-d00202-K
            # The repository has been read, so the namespace its
            # declaration names is a claim it can be held to.  The same
            # namespace already resolved at another directory is the
            # second claimant K reports; at this same directory the walk
            # converged above and never arrived here.
            identity = _identity(info.get("namespace") or "", assoc_path)
            seen = resolved.get(identity)
            if seen is not None and seen.repo_root != assoc_path:
                raise NamespaceConflict(
                    info.get("namespace") or "",
                    (seen.repo_root, seen.declaration_path),
                    (assoc_path, child_path),
                )

            _record(
                PlannedRepo(
                    name,
                    assoc_path,
                    assoc_config,
                    repository_origin(assoc_path),
                    None,
                    child_path,
                ),
                identity,
            )
            _visit(
                assoc_config,
                assoc_path,
                child_path,
                {**on_path, assoc_path: name},
            )

    _visit(root_config, root_root, (root_name,), {root_root: root_name})
    return planned


def plan_federation_or_error(
    root_config: dict[str, Any],
    root_repo_root: Path,
    *,
    config_loader: Callable[..., dict[str, Any]] | None = None,
) -> tuple[list[PlannedRepo], str | None]:
    """Plan a federation for a reporting surface, reporting instead of raising.

    A diagnostic surface has to survive the very configurations it exists
    to describe: a declaration cycle or a name collision stops the walk,
    but it must reach the operator as a finding rather than as a
    traceback that takes the rest of the report with it.

    Returns:
        The plan and None, or an empty plan and the reason it could not
        be produced.
    """
    try:
        return plan_federation(root_config, root_repo_root, config_loader=config_loader), None
    except FederationError as exc:
        return [], str(exc)
