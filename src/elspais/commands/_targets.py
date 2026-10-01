"""Resolving a command's test-target selection.

The reporting commands take the same selector ``elspais checks --run-tests``
takes, and mean something adjacent by it: which targets a run covered, rather
than which it is to execute. Both questions have one answer, so both reach
:func:`elspais.config.selected_targets` through here.
"""

from __future__ import annotations

from typing import Any

__all__ = ["resolve_expected_targets", "resolve_fresh_targets"]


# Implements: REQ-d00283-D+E+H+I+J+K+L+O, REQ-d00254-I
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
    if refusal := unknown_target_refusal(cfg, named):
        raise ValueError(refusal)
    if refusal := empty_selection_refusal(cfg, named, executes=False):
        raise ValueError(refusal)
    if named is None:
        return None
    return selected_targets(cfg, named)


# Implements: REQ-d00283-E+H+P
def resolve_expected_targets(config: Any, named: list[str] | None) -> set[str]:
    """The targets whose results a run names as expected, by target or group name.

    The names resolve exactly as the target selector's do, so a group stands
    for its targets and an unknown name is refused naming the option it came
    from. ``none`` expects nothing. A selection standing for no target is
    refused rather than resolved to an empty expectation, because a run that
    expects nothing reports nothing missing, and that reads as a clean run.

    Raises:
        ValueError: If a name is neither a configured target nor a declared or
            reserved group, or if the names stand for no target and do not
            name ``none``.
    """
    from elspais.config import selected_targets, unknown_target_refusal, validate_config
    from elspais.config.schema import GROUP_NONE

    cfg = validate_config(config) if isinstance(config, dict) else config
    wanted = [n for n in (x.strip() for x in (named or [])) if n]
    if not wanted:
        return set()
    if refusal := unknown_target_refusal(cfg, wanted, flag="--expect"):
        raise ValueError(refusal)
    configured = {t.name for t in cfg.scanning.test.targets}
    chosen = selected_targets(cfg, wanted)
    expected = set(configured) if chosen is None else set(chosen) & configured
    if not expected and not any(n.lower() == GROUP_NONE for n in wanted):
        raise ValueError(
            f"--expect {' '.join(wanted)} stands for no configured target. "
            f"To expect no results beyond what the run executes, omit --expect "
            f"or name the reserved group `{GROUP_NONE}`."
        )
    return expected
