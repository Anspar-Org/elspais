"""Resolving a command's test-target selection.

The reporting commands take the same selector ``elspais checks --run-tests``
takes, and mean something adjacent by it: which targets a run covered, rather
than which it is to execute. Both questions have one answer, so both reach
:func:`elspais.config.selected_targets` through here.
"""

from __future__ import annotations

from typing import Any

__all__ = ["resolve_fresh_targets"]


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
