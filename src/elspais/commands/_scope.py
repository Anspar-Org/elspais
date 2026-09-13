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

from typing import Any

from elspais.graph.scope import (
    ReportScope,
    ScopeResult,
    describe_scope,
    scope_from_params,
    scope_to_params,
    scoped_requirements,
)

__all__ = [
    "scope_from_args",
    "scope_params_from_args",
    "scope_from_params",
    "scope_to_params",
    "resolve_scope_for_report",
    "scope_disclosure",
]


def _values(args: Any, name: str) -> tuple[str, ...]:
    raw = getattr(args, name, None)
    if not raw:
        return ()
    if isinstance(raw, str):
        raw = [raw]
    return tuple(str(v) for v in raw if str(v).strip())


def scope_from_args(args: Any, config: dict[str, Any] | None = None) -> ReportScope | None:
    """The scope this invocation asks for, or None where it asks for none.

    A named scope (``--scope``) is expanded here, so a name and the same
    selection stated in full reach the authority as one thing (REQ-d00280-B).
    """
    include: dict[str, tuple[str, ...]] = {}
    exclude: dict[str, tuple[str, ...]] = {}
    for prop in ("level", "status"):
        if wanted := _values(args, prop):
            include[prop] = wanted
        if refused := _values(args, f"not_{prop}"):
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


def scope_params_from_args(args: Any, config: dict[str, Any] | None = None) -> dict[str, str]:
    """The query parameters carrying this invocation's scope to a serving process."""
    return scope_to_params(scope_from_args(args, config))


def resolve_scope_for_report(
    graph: Any,
    args_or_params: Any,
    config: dict[str, Any] | None = None,
) -> ScopeResult:
    """The membership a report should emit, from either an invocation or params.

    Accepts both shapes because a report reaches this point two ways -- computed
    where it was asked for, or computed by a process that received the scope as
    parameters -- and both have to arrive at the same set.
    """
    if isinstance(args_or_params, dict):
        scope = scope_from_params(args_or_params)
    else:
        scope = scope_from_args(args_or_params, config)
    return scoped_requirements(graph, scope, config)


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
