# Implements: REQ-p00084-A+D, REQ-d00279-C
"""Reading a scope off a command invocation and carrying it to where it is read.

The vocabulary and the membership judgement live in ``graph/scope.py``; this is
only the path between a reader's invocation and that authority. It exists once
rather than per command because REQ-d00279-C obliges every path producing a
report -- a section on its own, a section composed with others, and a report
answered by a serving process -- to yield the same scoped set, and a scope
assembled separately by each command is how those paths start disagreeing.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from elspais.graph.scope import (
    ReportScope,
    ScopeResult,
    describe_scope,
    scope_from_params,
    scope_to_params,
)

__all__ = [
    "flag_values",
    "scope_from_args",
    "scope_from_params",
    "scope_to_params",
    "scope_disclosure",
]


# Implements: REQ-d00278-C, REQ-p00084-H
def flag_values(args: Any, name: str) -> tuple[str, ...]:
    """Every value this invocation named for one list-valued flag.

    The ONE place a repeated flag is gathered back into the one list it names.
    A reader may write the values space-separated behind a single flag, repeat
    the flag, or mix the two; a repetition arrives as its own inner list and is
    flattened here rather than letting the last occurrence stand for the whole.
    REQ-d00278-C admits any combination of the values a property admits, and
    keeping only the last occurrence would put some of those combinations out of
    a reader's reach while looking like the whole invocation had been read.

    Serves the scope properties and every other accumulating flag (``--treat-
    active``) so one spelling rule holds across them: a reader who has learned
    how one flag reads has learned how they all do. It also accepts the flat
    shape, which is what the composed report's argparse parser produces and what
    a caller assembling a namespace by hand hands over.
    """
    raw = getattr(args, name, None)
    if not raw:
        return ()
    if isinstance(raw, str):
        raw = [raw]
    flat: list[Any] = []
    for item in raw:
        if isinstance(item, str):
            flat.append(item)
        elif isinstance(item, (list, tuple)):
            flat.extend(item)
        else:
            flat.append(item)
    return tuple(str(v) for v in flat if str(v).strip())


def scope_from_args(args: Any, config: dict[str, Any] | None = None) -> ReportScope | None:
    """The scope this invocation asks for, or None where it asks for none.

    A named scope (``--scope``) is expanded here, so a name and the same
    selection stated in full reach the authority as one thing (REQ-d00280-B).
    """
    include: dict[str, tuple[str, ...]] = {}
    exclude: dict[str, tuple[str, ...]] = {}
    for prop in ("level", "status"):
        if wanted := flag_values(args, prop):
            include[prop] = wanted
        if refused := flag_values(args, f"not_{prop}"):
            exclude[prop] = refused
    match_roles = bool(getattr(args, "match_status_roles", False))

    named = getattr(args, "scope", None)
    if named:
        from elspais.config import declared_scope

        base = declared_scope(config or {}, str(named))
        # A scope stated on the invocation narrows the one it names rather than
        # replacing it, so a reader can take a committed scope and ask a further
        # question of it without restating the whole thing.
        merged_include = dict(base.include)
        merged_include.update(include)
        merged_exclude = dict(base.exclude)
        merged_exclude.update(exclude)
        return ReportScope(
            include=merged_include,
            exclude=merged_exclude,
            match_status_roles=match_roles or base.match_status_roles,
        )

    if not include and not exclude:
        return None
    return ReportScope(include=include, exclude=exclude, match_status_roles=match_roles)


# Implements: REQ-d00291-G, REQ-p00085-A
def active_overlay_disclosure(treat_active: Iterable[str] | None) -> list[str]:
    """What a report owes its reader about the statuses it weighed as active.

    A run can weigh a status as active. The counts in the report then include
    the requirements in that status. The text of those requirements still
    gives the original status. A reader who cannot see the request cannot see
    the reason for the difference. Therefore the report states the request.

    A status weighed as active is one of the choices that decide the
    population a figure is taken over, which is what REQ-p00085-A obliges a
    report to disclose. It is NOT a scope: a scope decides which requirements
    a report emits.

    The result is empty if the run weighs no status as active. There is then
    nothing to state.
    """
    from elspais.config import statuses_weighed_active

    names = sorted(statuses_weighed_active(treat_active))
    if not names:
        return []
    return [f"Weighed as active: {', '.join(names)} (--treat-active)"]


# Implements: REQ-d00278-L
def scope_disclosure(result: ScopeResult) -> list[str]:
    """What a scoped report owes its reader about the scope that produced it.

    REQ-p00084-D: a report narrowed on purpose and one that lost requirements on
    the way are the same artifact unless the narrowing is declared. Returns an
    empty list where nothing was narrowed and there is nothing to declare.
    """
    lines: list[str] = []
    if result.scope is not None and not result.scope.is_empty():
        lines.append(f"Scope: {describe_scope(result.scope)}")
        lines.append(f"Scope selected {len(result.ids)} of {result.population} requirements")
    # One name unadmitted in one member is one fact about the scope, however
    # many places in the scope named it.
    seen: set[tuple[str, str, str]] = set()
    for name in result.unadmitted:
        key = (name.prop, name.value, name.repo)
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"Scope: {name.describe()}")
    if result.selected_nothing_from_a_populated_estate:
        lines.append(
            f"Scope: no requirement matches this scope; the estate holds {result.population}"
        )
    return lines
