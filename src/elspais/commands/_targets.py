"""Resolving a command's test-target selection.

The reporting commands take the same selector ``elspais checks --run-tests``
takes, and mean something adjacent by it: which targets a run covered, rather
than which it is to execute. Both questions have one answer, so both reach
:func:`elspais.config.selected_targets` through here.
"""

from __future__ import annotations

from typing import Any

__all__ = ["resolve_fresh_targets"]


# Implements: REQ-d00283-E+H+I, REQ-d00254-I
def resolve_fresh_targets(args: Any, config: dict[str, Any]) -> set[str] | None:
    """The targets *args* marks as freshly-run, or ``None`` for every target.

    Naming neither selector marks nothing. REQ-d00283-D gives the ``default``
    group to a run that *executes* targets, and these commands execute none --
    they read whatever results are on disk. Resolving a default set here would
    have the tool state which targets were freshly run on the strength of a
    flag the caller did not pass, which is a claim about what they did rather
    than a fact about what happened.

    Raises:
        ValueError: If a name is neither a configured target nor a group the
            project admits. The caller reports it; a selection resolving to
            nothing is refused rather than rendered (REQ-d00283-H). Refused
            HERE rather than deeper because ``selected_targets`` carries an
            unknown name through on purpose, so nothing below this raises.
    """
    from elspais.commands._scope import flag_values
    from elspais.config import selected_targets, unknown_target_names, validate_config

    named = list(flag_values(args, "targets")) or None
    if named is None:
        return None
    cfg = validate_config(config)
    if unknown := unknown_target_names(cfg, named):
        configured = sorted(t.name for t in cfg.scanning.test.targets)
        from elspais.config import known_group_names

        raise ValueError(
            f"unknown --targets: {', '.join(unknown)}. "
            f"Configured targets: {', '.join(configured)}. "
            f"Known groups: {', '.join(sorted(known_group_names(cfg)))}."
        )
    return selected_targets(cfg, named)
