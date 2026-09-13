# Implements: REQ-d00282-A, REQ-d00280-C
"""Reading a value selection off a command invocation and carrying it onward.

The vocabulary and the resolution live in ``graph/values.py``; this is only the
path between a reader's invocation and that authority, and the mirror of
``commands/_scope.py`` for the other axis of REQ-d00282. It exists once rather
than per command because a report reaches its formatters two ways -- computed
where it was asked for, and computed by a serving process handed parameters --
and a selection that does not survive the trip makes a daemon-served report
state different values from a locally computed one (REQ-d00282-E).

A selection is written in value KEYS, never in the words a project displays a
value under (REQ-d00282-J), so nothing here consults the display vocabulary.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from elspais.graph.values import (
    VALUE_LIST_SEPARATOR,
    UnofferedValues,
    ValueSelection,
    parse_value_selection,
    resolve_values,
)

__all__ = [
    "VALUES_PARAM",
    "UnofferedValues",
    "values_from_args",
    "value_silent_refusal",
    "values_from_params",
    "values_to_params",
    "value_params_from_args",
    "resolve_report_values",
]

# The query parameter a selection travels to a serving process under.
VALUES_PARAM = "values"


def _declared_values(config: Mapping[str, Any] | None, name: str) -> tuple[str, ...]:
    """The values a project declares under a scope name (REQ-d00280-C).

    One name carries both halves of what an audience reads. The lookup is
    case-insensitive for the same reason ``declared_scope`` is: a name that
    resolved for the requirements and not for the facts would be one name
    meaning two things. A declaration naming no values constrains none.
    """
    declared = (config or {}).get("scopes") or {}
    if not isinstance(declared, dict):
        return ()
    for key, value in declared.items():
        if not isinstance(key, str) or key.lower() != name.lower():
            continue
        raw = value.get("values") if isinstance(value, dict) else getattr(value, "values", None)
        return tuple(str(v) for v in (raw or []))
    return ()


# Implements: REQ-d00282-I
def values_from_args(args: Any, config: Mapping[str, Any] | None = None) -> ValueSelection | None:
    """The values this invocation asks for, or None where it asks for none.

    A selection stated on the invocation REPLACES the one a named declaration
    carries rather than narrowing it: values are not narrowable -- a second
    list intersected with the first would state a shape neither party wrote.
    """
    stated = parse_value_selection(getattr(args, "values", None))
    if stated is not None:
        return stated
    named = getattr(args, "scope", None)
    if named:
        return parse_value_selection(_declared_values(config, str(named)))
    return None


# Implements: REQ-d00282-F, REQ-d00280-C
def value_silent_refusal(
    args: Any,
    config: Mapping[str, Any] | None,
    report: str,
    does: str = "it lists what is missing",
) -> str | None:
    """Why a report that states no values cannot be produced under this selection.

    Some reports state facts about each requirement and some list which
    requirements are missing something; the second kind offers no values, so a
    selection reaching one of them names nothing it offers and cannot be
    honoured to any degree. F's disposition for that is non-production -- the
    opposite of the disclose-and-continue REQ-d00278-K takes for a scope name a
    member does not admit -- so this returns the reason rather than a caveat to
    print beside a report.

    A selection reaches a command two ways (``--values`` and the values half of
    a named declaration, REQ-d00280-C) and the refusal names the route the
    reader actually wrote: one telling a reader to drop a flag they never wrote
    tells them nothing. Returns None where no selection arrived at all -- a
    declaration naming no values constrains none.

    ``does`` says what the report does instead, so the refusal tells a reader
    why this report has nothing to select among rather than only that it has
    not.
    """
    stated = parse_value_selection(getattr(args, "values", None))
    if stated is not None:
        return (
            f"--values states which facts a report gives about each requirement, "
            f"and '{report}' states none: {does}. "
            "Ask for it without --values, or compose only sections that state values."
        )
    named = getattr(args, "scope", None)
    if not named:
        return None
    declared = parse_value_selection(_declared_values(config, str(named)))
    if declared is None:
        return None
    listed = ", ".join(declared.keys)
    return (
        f"the scope '{named}' declares values ({listed}), and '{report}' states "
        f"none: {does} rather than stating facts about each "
        f"requirement. Refer to a scope that declares no values, or state this "
        f"scope's requirements in full with --level/--status and their --not- forms."
    )


def values_to_params(selection: ValueSelection | None) -> dict[str, str]:
    """Serialize a selection for a report computed by a serving process."""
    if selection is None or not selection:
        return {}
    return {VALUES_PARAM: VALUE_LIST_SEPARATOR.join(selection.keys)}


def values_from_params(params: Mapping[str, str]) -> ValueSelection | None:
    """Rebuild a selection a serving process was handed. Inverse of the above."""
    return parse_value_selection(params.get(VALUES_PARAM))


def value_params_from_args(args: Any, config: Mapping[str, Any] | None = None) -> dict[str, str]:
    """The query parameters carrying this invocation's selection onward."""
    return values_to_params(values_from_args(args, config))


# Implements: REQ-d00282-E
def resolve_report_values(
    args_or_params: Any,
    offered: Sequence[str],
    default: Sequence[str],
    config: Mapping[str, Any] | None = None,
    identity_key: str = "id",
) -> tuple[str, ...]:
    """The values a report states, from either an invocation or params.

    Accepts both shapes because a report reaches this point two ways and both
    have to arrive at the same values. Where nothing was named the report
    states its named default set (REQ-d00084-B); where something was named the
    selection replaces that set entirely and is judged against everything the
    report offers, refusing outright if any name is not among them
    (REQ-d00282-F).
    """
    if isinstance(args_or_params, Mapping):
        selection = values_from_params(args_or_params)
    else:
        selection = values_from_args(args_or_params, config)
    if selection is None:
        return tuple(default)
    return resolve_values(selection, offered, identity_key)
