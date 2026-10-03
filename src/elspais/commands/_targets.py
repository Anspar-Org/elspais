"""Resolving a command's test-target selection.

The reporting commands take the same selector ``elspais checks --run-tests``
takes, and mean something adjacent by it: which targets a run covered, rather
than which it is to execute. Both questions have one answer, so both reach
:func:`elspais.config.selected_targets` through here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

__all__ = [
    "MEMBER_SEPARATOR",
    "qualified_target",
    "resolve_expected_targets",
    "resolve_fresh_targets",
]


# Implements: REQ-d00283-D+E+H+I+J+K+L+O, REQ-d00254-I, REQ-d00316-E
def resolve_fresh_targets(args: Any, config: dict[str, Any]) -> set[str] | None:
    """The targets *args* marks as freshly-run, or ``None`` for every target.

    Naming neither selector marks nothing. REQ-d00283-D gives the ``default``
    group to a run that *executes* targets, and these commands execute none --
    they read whatever results are on disk. Resolving a default set here would
    have the tool state which targets were freshly run on the strength of a
    flag the caller did not pass, which is a claim about what they did rather
    than a fact about what happened. A bare run still selects ``default``.
    If that group holds no target, then this function refuses the run
    (REQ-d00283-K+O).

    A run that names the reserved group ``none`` marks no target fresh.
    Consequently, the report renders every result as carried from an earlier
    run (REQ-d00283-J).

    Raises:
        ValueError: If a name is neither a configured target nor a declared or
            reserved group (REQ-d00283-H). Also, if the selection reaches no
            target and does not name ``none`` (REQ-d00283-K). This function
            refuses unknown names itself because ``selected_targets`` passes
            them through on purpose.
    """
    from elspais.commands._scope import flag_values
    from elspais.config import (
        empty_selection_refusal,
        selected_targets,
        unknown_target_refusal,
        validate_config,
    )

    named = list(flag_values(args, "targets")) or None
    cfg = validate_config(config)
    named = _expand_last_run(cfg, named)
    if refusal := unknown_target_refusal(cfg, named):
        raise ValueError(refusal)
    if refusal := empty_selection_refusal(cfg, named, executes=False):
        raise ValueError(refusal)
    if named is None:
        return None
    return selected_targets(cfg, named)


# Implements: REQ-d00316-E+F+G+H
def _expand_last_run(cfg: Any, named: list[str] | None) -> list[str] | None:
    """Read the last run's record where *named* names `last-run`, and expand it."""
    from elspais.config import expand_last_run, find_git_root
    from elspais.config.schema import GROUP_LAST_RUN
    from elspais.utilities.fingerprint import last_run_path, read_last_run

    if not named or not any(n.strip().lower() == GROUP_LAST_RUN for n in named):
        return named
    root = find_git_root() or Path.cwd()
    return expand_last_run(cfg, named, read_last_run(root, cfg), last_run_path(root, cfg))


# Implements: REQ-d00283-W+X
# The character that separates a member's namespace from a target or group
# name that member declares. A namespace never holds it, and the schema refuses
# a target or group name holding it, so the first one always ends the namespace.
MEMBER_SEPARATOR = ":"


def qualified_target(namespace: str, target: str) -> str:
    """Spell the one expectation naming *target* of the member *namespace*."""
    return f"{namespace}{MEMBER_SEPARATOR}{target}"


# Implements: REQ-d00283-E+H+P+U+W
def resolve_expected_targets(
    config: Any, named: list[str] | None, repo_root: Path | None = None
) -> set[str]:
    """The targets whose results a run names as expected, each qualified by its member.

    A bare name is a target or group of the invoking repository. A name written
    after a member's namespace and ``:`` is a target or group of that member,
    resolved by that member's own declarations (REQ-d00283-W). The members are
    the federation ``plan_federation`` resolves, so a repository the root
    reaches only through an associate is nameable too.

    The names of one member resolve exactly as the target selector's do, so a
    group stands for its targets and an unknown name is refused naming the
    option it came from. ``none`` expects nothing. A selection standing for no
    target is refused rather than resolved to an empty expectation, because a
    run that expects nothing reports nothing missing, and that reads as a
    clean run.

    Returns:
        Every expected target spelled by :func:`qualified_target`, the
        invoking repository's included.

    Raises:
        ValueError: If a name is neither a configured target nor a declared or
            reserved group of the member it names, if it names a namespace no
            member of the federation declares, or if the names stand for no
            target and do not name ``none``.
    """
    from elspais.config import last_run_refusal, validate_config
    from elspais.config.schema import GROUP_NONE

    root_cfg = validate_config(config) if isinstance(config, dict) else config
    wanted = [n for n in (x.strip() for x in (named or [])) if n]
    if not wanted:
        return set()
    # Implements: REQ-d00316-I
    if refusal := last_run_refusal(wanted, flag="--expect"):
        raise ValueError(refusal)
    root_ns = root_cfg.project.namespace

    by_member: dict[str, list[str]] = {}
    for name in wanted:
        namespace, sep, rest = name.partition(MEMBER_SEPARATOR)
        if sep:
            if not rest.strip():
                raise ValueError(
                    f"--expect {name} names no target or group after the namespace. "
                    f"Write the member's namespace, `{MEMBER_SEPARATOR}`, and a target "
                    f"or group that member declares."
                )
            by_member.setdefault(namespace.strip(), []).append(rest.strip())
        else:
            by_member.setdefault(root_ns, []).append(name)

    members: dict[str, Any] = {root_ns: root_cfg}
    if set(by_member) - {root_ns}:
        members = _federation_configs(config, root_cfg, repo_root)

    expected: set[str] = set()
    for namespace, names in by_member.items():
        if namespace not in members:
            raise ValueError(
                f"unknown --expect namespace: {namespace} (in "
                f"{', '.join(qualified_target(namespace, n) for n in names)}). "
                f"Members of this federation: {', '.join(sorted(members))}."
            )
        expected |= {
            qualified_target(namespace, t)
            for t in _member_expected(members[namespace], names, namespace, root_ns)
        }
    if not expected and not any(n.lower() == GROUP_NONE for v in by_member.values() for n in v):
        raise ValueError(
            f"--expect {' '.join(wanted)} stands for no configured target. "
            f"To expect no results beyond what the run executes, omit --expect "
            f"or name the reserved group `{GROUP_NONE}`."
        )
    return expected


def _member_expected(cfg: Any, names: list[str], namespace: str, root_ns: str) -> set[str]:
    """Resolve *names* by the targets and groups the member *cfg* declares."""
    from elspais.config import selected_targets, unknown_target_refusal

    flag = "--expect" if namespace == root_ns else f"--expect (member {namespace})"
    if refusal := unknown_target_refusal(cfg, names, flag=flag):
        raise ValueError(refusal)
    configured = {t.name for t in cfg.scanning.test.targets}
    chosen = selected_targets(cfg, names)
    return set(configured) if chosen is None else set(chosen) & configured


def _federation_configs(config: Any, root_cfg: Any, repo_root: Path | None) -> dict[str, Any]:
    """Every federation member's validated configuration, keyed by its namespace.

    Membership is ``plan_federation``'s answer, never the root's associate
    table read here, so a member reached through another member's declarations
    is a member too (REQ-d00202-D).
    """
    from elspais.config import find_git_root, validate_config
    from elspais.graph.federation_plan import FederationError, plan_federation

    raw = config if isinstance(config, dict) else root_cfg.model_dump(by_alias=True)
    root = repo_root or find_git_root() or Path.cwd()
    try:
        plan = plan_federation(raw, root)
    except FederationError as exc:
        raise ValueError(f"--expect names another member, and the federation: {exc}") from exc
    members: dict[str, Any] = {}
    unreadable: dict[str, str] = {}
    for member in plan:
        if member.config is None:
            unreadable[member.name] = member.error or "its configuration could not be read"
            continue
        member_cfg = validate_config(member.config)
        members[member_cfg.project.namespace] = member_cfg
    if unreadable:
        reasons = "; ".join(f"{name}: {why}" for name, why in sorted(unreadable.items()))
        raise ValueError(
            f"--expect names another member, and a member could not be read: {reasons}"
        )
    return members
