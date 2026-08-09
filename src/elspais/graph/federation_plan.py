# Implements: REQ-d00202-D+E+F+G+I+J, REQ-d00203-B
"""Resolve a federation's membership from declared associates.

Planning is separated from building: this module answers "which
repositories are in this federation, and what is each one's
configuration?" without constructing a single graph.  ``build_graph()``
turns the answer into ``RepoEntry`` objects.

Declarations are walked depth-first from the root repository.  A
repository is identified by its git origin, so the same repository
reached down two different chains -- or reached once by its main
checkout and once by a worktree -- converges on one entry rather than
being federated twice.  A repository with no origin falls back to its
resolved filesystem path, which keeps two unrelated originless
directories distinct.

That identity rule is what separates a diamond from a cycle.  A repo
already resolved somewhere else in the walk is convergence and is
skipped; a repo already on the current declaration path is a cycle and
is an error, because dependency direction is what orders resolution.
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
    "PlannedRepo",
    "plan_federation",
    "plan_federation_or_error",
]


class FederationCycleError(FederationError):
    """Raised when associate declarations form a directed cycle."""


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
    """Reduce an origin URL to a comparable identity.

    The same repository is routinely addressed as ``git@host:org/repo.git``
    and ``https://host/org/repo``; both name one repository and must
    compare equal, or a diamond through two remotes would federate twice.
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


def _git_origin(repo_root: Path) -> str | None:
    """Return the normalized origin of the repository rooted at ``repo_root``.

    Answers only for a directory that *is* a repository root.  Git
    answers from the enclosing repository for any subdirectory, so a
    federation whose members are directories inside one repository --
    every on-disk test fixture, among others -- would otherwise see one
    origin shared by all of them and read the second member as a cycle.
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
    if not toplevel or Path(toplevel).resolve() != repo_root:
        return None
    origin = _git("remote", "get-url", "origin")
    return _normalize_origin(origin) if origin else None


def _identity(repo_root: Path, git_origin: str | None) -> tuple[str, str]:
    """Identify a repository for convergence and cycle detection."""
    if git_origin:
        return ("origin", git_origin)
    return ("path", str(repo_root))


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
    from elspais.config import get_associates_config, get_config

    loader = config_loader or get_config

    planned: list[PlannedRepo] = []
    resolved: dict[tuple[str, str], PlannedRepo] = {}
    by_name: dict[str, PlannedRepo] = {}

    # One answer per directory per walk.  Identity decides diamond from
    # cycle, so a directory that answered with an origin once and with
    # None a moment later would be two repositories to this walk and a
    # cycle would go unseen.  Probing git is also the walk's dominant
    # cost, and a chain re-reaches the same directory often.
    origins: dict[Path, str | None] = {}

    def _origin_of(path: Path) -> str | None:
        if path not in origins:
            origins[path] = _git_origin(path) if path.is_dir() else None
        return origins[path]

    root_root = Path(root_repo_root).resolve()
    root_name = root_config.get("project", {}).get("name", "") or str(root_root.name)
    root_origin = _origin_of(root_root)
    root_entry = PlannedRepo(
        name=root_name,
        repo_root=root_root,
        config=root_config,
        git_origin=root_origin,
        error=None,
        declaration_path=(root_name,),
    )
    planned.append(root_entry)
    resolved[_identity(root_root, root_origin)] = root_entry
    by_name[root_name] = root_entry

    def _record(entry: PlannedRepo, identity: tuple[str, str]) -> None:
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
        on_path: dict[tuple[str, str], str],
    ) -> None:
        associates = get_associates_config(parent_config, repo_root=parent_root)
        for name, info in associates.items():
            assoc_path = Path(parent_root, info["path"]).resolve()
            child_path = declaration_path + (name,)
            origin = _origin_of(assoc_path)
            identity = _identity(assoc_path, origin)

            # Implements: REQ-d00202-E
            if identity in on_path:
                chain = " -> ".join(list(on_path.values()) + [name])
                raise FederationCycleError(
                    f"Associate declarations form a cycle: {chain}. "
                    f"Dependency direction orders federation resolution, so a "
                    f"repository cannot be reached through itself."
                )

            # Implements: REQ-d00202-F
            if identity in resolved:
                continue

            if not assoc_path.exists():
                reason = f"Path does not exist: {assoc_path}"
                if strict:
                    raise FederationError(f"Associate '{name}' path does not exist: {assoc_path}")
                _record(
                    PlannedRepo(name, assoc_path, None, origin, reason, child_path),
                    identity,
                )
                continue

            # Implements: REQ-d00203-B
            try:
                assoc_config = loader(None, assoc_path, quiet=True)
            except Exception as exc:  # noqa: BLE001 - reported, never swallowed
                reason = f"Configuration at {assoc_path} could not be loaded: {exc}"
                if strict:
                    raise FederationError(f"Associate '{name}': {reason}") from exc
                _record(
                    PlannedRepo(name, assoc_path, None, origin, reason, child_path),
                    identity,
                )
                continue

            _record(
                PlannedRepo(name, assoc_path, assoc_config, origin, None, child_path),
                identity,
            )
            _visit(
                assoc_config,
                assoc_path,
                child_path,
                {**on_path, identity: name},
            )

    _visit(root_config, root_root, (root_name,), {_identity(root_root, root_origin): root_name})
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
