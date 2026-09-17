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

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from elspais.graph.values import (
    UnofferedValues,
    ValueSelection,
    parse_value_selection,
)

__all__ = [
    "VALUES_PARAM",
    "UnofferedValues",
    "values_from_args",
    "value_silent_refusal",
    "values_from_params",
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


# Implements: REQ-d00282-I, REQ-d00280-D
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
        declared = parse_value_selection(_declared_values(config, str(named)))
        # Marked as the project's rather than the reader's: a declaration is one
        # name read against every report an audience takes, so a report that
        # does not offer one of its values passes that value over instead of
        # refusing the name (REQ-d00280-D).
        return None if declared is None else replace(declared, written=False)
    return None


# Implements: REQ-d00282-F
def value_silent_refusal(
    args: Any,
    config: Mapping[str, Any] | None,
    report: str,
    does: str = "it reports findings rather than facts about each requirement",
) -> str | None:
    """Why a report that states nothing about a requirement has nothing to select.

    A report either states facts about each requirement, or lists the
    requirements one dimension has not credited -- and both read a dimension,
    so both have values to select among. A few report neither: findings about
    the project, or the files that changed. A value named to one of those names
    nothing it offers, and F's disposition for a selection that cannot be
    honoured at all is non-production rather than a caveat printed beside a
    report.

    Only a selection the reader WROTE is refused. The values half of a named
    declaration (REQ-d00280-C) constrains the reports that have values to
    select among and passes over the ones that do not: one name carries what an
    audience reads, and a declaration usable with `trace` but not beside
    `checks` would make that name unusable for the audience it describes.

    ``does`` says what the report does instead, so the refusal tells a reader
    why this report has nothing to select among rather than only that it has
    not.
    """
    stated = parse_value_selection(getattr(args, "values", None))
    if stated is None:
        return None
    return (
        f"--values states which facts a report gives about each requirement, "
        f"and '{report}' states none: {does}. "
        "Ask for it without --values, or compose only sections that state values."
    )


def values_from_params(params: Mapping[str, str]) -> ValueSelection | None:
    """Rebuild a selection a serving process was handed. Inverse of ``ReportInputs.to_params``."""
    return parse_value_selection(params.get(VALUES_PARAM))
