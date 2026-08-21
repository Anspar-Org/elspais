# Implements: REQ-d00282-A, REQ-d00280-C
"""Reading a column selection off a command invocation and carrying it onward.

The vocabulary and the resolution live in ``graph/columns.py``; this is only the
path between a reader's invocation and that authority, and the mirror of
``commands/_scope.py`` for the other axis of REQ-d00282. It exists once rather
than per command because a report reaches its formatters two ways -- computed
where it was asked for, and computed by a serving process handed parameters --
and a selection that does not survive the trip makes a daemon-served report
state different columns from a locally computed one (REQ-d00282-E).

A selection is written in column KEYS, never in the words a project displays a
column under (REQ-d00282-J), so nothing here consults the display vocabulary.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from elspais.graph.columns import (
    COLUMN_LIST_SEPARATOR,
    ColumnSelection,
    UnofferedColumns,
    parse_column_selection,
    resolve_columns,
)

__all__ = [
    "COLUMNS_PARAM",
    "UnofferedColumns",
    "columns_from_args",
    "columns_from_params",
    "columns_to_params",
    "column_params_from_args",
    "resolve_report_columns",
]

# The query parameter a selection travels to a serving process under.
COLUMNS_PARAM = "columns"


def _declared_columns(config: Mapping[str, Any] | None, name: str) -> tuple[str, ...]:
    """The columns a project declares under a scope name (REQ-d00280-C).

    One name carries both halves of what an audience reads. The lookup is
    case-insensitive for the same reason ``declared_scope`` is: a name that
    resolved for the requirements and not for the facts would be one name
    meaning two things. A declaration naming no columns constrains none.
    """
    declared = (config or {}).get("scopes") or {}
    if not isinstance(declared, dict):
        return ()
    for key, value in declared.items():
        if not isinstance(key, str) or key.lower() != name.lower():
            continue
        raw = value.get("columns") if isinstance(value, dict) else getattr(value, "columns", None)
        return tuple(str(v) for v in (raw or []))
    return ()


def columns_from_args(args: Any, config: Mapping[str, Any] | None = None) -> ColumnSelection | None:
    """The columns this invocation asks for, or None where it asks for none.

    A selection stated on the invocation REPLACES the one a named declaration
    carries rather than narrowing it: columns are not narrowable -- a second
    list intersected with the first would state a shape neither party wrote.
    """
    stated = parse_column_selection(getattr(args, "columns", None))
    if stated is not None:
        return stated
    named = getattr(args, "scope", None)
    if named:
        return parse_column_selection(_declared_columns(config, str(named)))
    return None


def columns_to_params(selection: ColumnSelection | None) -> dict[str, str]:
    """Serialize a selection for a report computed by a serving process."""
    if selection is None or not selection:
        return {}
    return {COLUMNS_PARAM: COLUMN_LIST_SEPARATOR.join(selection.keys)}


def columns_from_params(params: Mapping[str, str]) -> ColumnSelection | None:
    """Rebuild a selection a serving process was handed. Inverse of the above."""
    return parse_column_selection(params.get(COLUMNS_PARAM))


def column_params_from_args(args: Any, config: Mapping[str, Any] | None = None) -> dict[str, str]:
    """The query parameters carrying this invocation's selection onward."""
    return columns_to_params(columns_from_args(args, config))


def resolve_report_columns(
    args_or_params: Any,
    offered: Sequence[str],
    default: Sequence[str],
    config: Mapping[str, Any] | None = None,
    identity_key: str = "id",
) -> tuple[str, ...]:
    """The columns a report states, from either an invocation or params.

    Accepts both shapes because a report reaches this point two ways and both
    have to arrive at the same columns. Where nothing was named the report
    states its named default set (REQ-d00084-B); where something was named the
    selection replaces that set entirely and is judged against everything the
    report offers, refusing outright if any name is not among them
    (REQ-d00282-F).
    """
    if isinstance(args_or_params, Mapping):
        selection = columns_from_params(args_or_params)
    else:
        selection = columns_from_args(args_or_params, config)
    if selection is None:
        return tuple(default)
    return resolve_columns(selection, offered, identity_key)
