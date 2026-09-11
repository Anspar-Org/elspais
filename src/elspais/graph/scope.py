# Implements: REQ-d00278, REQ-d00279-A
"""Report scope: the one authority deciding whether a requirement is in scope.

A *scope* is a selection over properties a requirement carries -- its level, its
status -- written by a person and read here. This module owns the vocabulary
(REQ-d00278) and the membership judgement (REQ-d00279-A); every reporting surface
derives its answer from :func:`scoped_requirements` rather than filtering for
itself, so two surfaces asked the same question give the same answer.

The properties a scope may select on live in :data:`SCOPE_PROPERTIES`. Admitting
another one must not change what an already expressible scope selects
(REQ-d00278-M), which is why a property names its own reader and its own
configured vocabulary rather than membership branching on a fixed list.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

from elspais.graph.GraphNode import NodeKind

# A scope travels to a serving process as query parameters, so its values are
# joined by this character. Level keys and status names are validated to
# identifier shape, which cannot contain it -- see the schema's namespace check.
SCOPE_VALUE_SEPARATOR = ","


@dataclass(frozen=True)
class ScopeProperty:
    """A property of a requirement that a scope can select on."""

    name: str
    read: Callable[[Any], str]
    """The value this requirement carries for the property, or "" for none."""
    configured: Callable[[dict[str, Any] | None], set[str]]
    """The values a member's configuration defines for the property."""


def _configured_levels(config: dict[str, Any] | None) -> set[str]:
    levels = (config or {}).get("levels") or {}
    return {str(k) for k in levels} if isinstance(levels, dict) else set()


def _configured_statuses(config: dict[str, Any] | None) -> set[str]:
    """Status names a configuration defines.

    The status vocabulary is the union of the role lists -- there is no separate
    list of allowed statuses -- plus any name carrying a per-status overlay.
    """
    cfg = config or {}
    names: set[str] = set()
    roles = (((cfg.get("rules") or {}).get("format") or {}).get("status_roles")) or {}
    if isinstance(roles, dict):
        for listed in roles.values():
            if isinstance(listed, list):
                names.update(str(s) for s in listed)
    overlay = cfg.get("statuses") or {}
    if isinstance(overlay, dict):
        names.update(str(k) for k in overlay)
    return names


# Implements: REQ-d00278-A, REQ-d00278-B
SCOPE_PROPERTIES: dict[str, ScopeProperty] = {
    "level": ScopeProperty(
        name="level",
        read=lambda node: (node.level or "").strip(),
        configured=_configured_levels,
    ),
    "status": ScopeProperty(
        name="status",
        read=lambda node: (node.status or "").strip(),
        configured=_configured_statuses,
    ),
}


@dataclass(frozen=True)
class ReportScope:
    """A selection a reader wrote, before it is read against any vocabulary.

    ``include`` names, per property, the values a requirement must carry;
    ``exclude`` names the values it must not (REQ-d00278-E+F). A property absent
    from both places them no constraint.
    """

    include: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    exclude: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    match_status_roles: bool = False
    """Whether a named status stands for every status sharing its role."""

    def is_empty(self) -> bool:
        """Whether this scope constrains nothing."""
        return not any(self.include.values()) and not any(self.exclude.values())

    def properties(self) -> set[str]:
        """Every property this scope names, whether to require or to refuse."""
        return {p for p, v in self.include.items() if v} | {p for p, v in self.exclude.items() if v}


@dataclass(frozen=True)
class UnadmittedName:
    """A name the vocabulary it was resolved against does not admit."""

    prop: str
    value: str
    repo: str
    vocabulary: tuple[str, ...]

    def describe(self) -> str:
        known = ", ".join(self.vocabulary) if self.vocabulary else "nothing"
        if self.prop not in SCOPE_PROPERTIES:
            return (
                f"{self.repo}: no property named '{self.prop}'; selectable properties are {known}"
            )
        return (
            f"{self.repo}: '{self.value}' is not a {self.prop} in this vocabulary; "
            f"it admits {known}"
        )


@dataclass(frozen=True)
class ResolvedScope:
    """A scope read against one member's vocabulary.

    Values are case-folded, so a spelling differing only in case still resolves.
    """

    include: Mapping[str, frozenset[str]]
    exclude: Mapping[str, frozenset[str]]
    unadmitted: tuple[UnadmittedName, ...]
    selects_nothing: bool = False
    """Set where the scope requires a property this vocabulary has no reader for.

    REQ-d00278-K holds for a property name as much as for a value: a requirement
    cannot be shown to carry what nothing can read, so requiring it selects no
    requirement here rather than placing no constraint.
    """


def _role_siblings(config: dict[str, Any] | None, status: str) -> set[str]:
    """Every status the project assigns the same role as ``status``."""
    from elspais.config import get_status_roles

    roles = get_status_roles(config or {})
    target = roles.role_of(status)
    known = _configured_statuses(config)
    return {s for s in known if roles.role_of(s) == target}


# Implements: REQ-d00278-G+H+I+J+K
def resolve_scope(
    scope: ReportScope,
    config: dict[str, Any] | None,
    carried: Mapping[str, set[str]] | None = None,
    repo: str = "",
) -> ResolvedScope:
    """Read ``scope`` against one member's vocabulary.

    A property's vocabulary is what the member's configuration defines together
    with what that member's requirements carry (REQ-d00278-H) -- a requirement
    carrying a status the project never listed is one a reader can see, so it has
    to be one a reader can name.

    A name the vocabulary does not admit is recorded rather than refused
    (REQ-d00278-J+K): it selects nothing here, and the rest of the scope goes on
    selecting, because a cross-member scope naming a level only some members
    define is a legitimate scope.
    """
    carried = carried or {}
    include: dict[str, frozenset[str]] = {}
    exclude: dict[str, frozenset[str]] = {}
    unadmitted: list[UnadmittedName] = []
    selects_nothing = False

    for source, target in ((scope.include, include), (scope.exclude, exclude)):
        for prop, values in source.items():
            if not values:
                continue
            spec = SCOPE_PROPERTIES.get(prop)
            if spec is None:
                if target is include:
                    selects_nothing = True
                unadmitted.append(
                    UnadmittedName(
                        prop=prop,
                        value="",
                        repo=repo,
                        vocabulary=tuple(sorted(SCOPE_PROPERTIES)),
                    )
                )
                continue
            vocabulary = spec.configured(config) | set(carried.get(prop, set()))
            folded = {v.lower(): v for v in vocabulary}
            resolved: set[str] = set()
            for raw in values:
                key = raw.strip().lower()
                if key not in folded:
                    unadmitted.append(
                        UnadmittedName(
                            prop=prop,
                            value=raw,
                            repo=repo,
                            vocabulary=tuple(sorted(vocabulary)),
                        )
                    )
                    continue
                resolved.add(key)
                if prop == "status" and scope.match_status_roles:
                    # REQ-d00278-G widens a status to the role THE PROJECT
                    # ASSIGNS it. A status the project never listed is nameable
                    # (REQ-d00278-H) but carries no assigned role, so it stands
                    # for itself: widening it through the unknown-status default
                    # would reach statuses the reader never named.
                    if folded[key] in spec.configured(config):
                        resolved.update(s.lower() for s in _role_siblings(config, folded[key]))
            if target is include:
                # REQ-d00278-K: a name this vocabulary does not admit selects no
                # requirement HERE. An empty requirement set is what says so --
                # dropping the property instead would place no constraint at all
                # and hand back everything, which is the opposite answer.
                target[prop] = frozenset(resolved)
            elif resolved:
                # An exclusion naming nothing this vocabulary knows refuses
                # nothing, which is already what omitting it means.
                target[prop] = frozenset(resolved)

    return ResolvedScope(
        include=include,
        exclude=exclude,
        unadmitted=tuple(unadmitted),
        selects_nothing=selects_nothing,
    )


# Implements: REQ-d00278-D+E+F
def satisfies(node: Any, resolved: ResolvedScope) -> bool:
    """Whether one requirement falls within a resolved scope.

    A requirement is in scope only where it satisfies every property the scope
    names (D); it satisfies a property by carrying any of the required values (E)
    and fails it by carrying any of the refused ones (F). Where a property names
    both, F's refusal decides the overlap without a rule of its own.
    """
    if resolved.selects_nothing:
        return False
    for prop, required in resolved.include.items():
        spec = SCOPE_PROPERTIES[prop]
        if spec.read(node).lower() not in required:
            return False
    for prop, refused in resolved.exclude.items():
        spec = SCOPE_PROPERTIES[prop]
        if spec.read(node).lower() in refused:
            return False
    return True


# Implements: REQ-d00278-H
def carried_values(nodes: Iterable[Any]) -> dict[str, set[str]]:
    """The values these requirements carry, per selectable property."""
    seen: dict[str, set[str]] = {prop: set() for prop in SCOPE_PROPERTIES}
    for node in nodes:
        for prop, spec in SCOPE_PROPERTIES.items():
            value = spec.read(node)
            if value:
                seen[prop].add(value)
    return seen


@dataclass(frozen=True)
class ScopeResult:
    """The membership one scope selects over one graph, and what to disclose."""

    ids: frozenset[str]
    population: int
    """How many requirements the scope was read over, selected or not."""
    unadmitted: tuple[UnadmittedName, ...]
    scope: ReportScope

    # Implements: REQ-d00278-L
    @property
    def selected_nothing_from_a_populated_estate(self) -> bool:
        """REQ-d00278-L: an empty answer that is an answer, not an empty estate."""
        return not self.ids and self.population > 0


def _requirements(graph: Any) -> Iterator[Any]:
    yield from graph.nodes_by_kind(NodeKind.REQUIREMENT)


# Implements: REQ-d00278-I
def _config_for_node(graph: Any, node: Any, fallback: dict[str, Any] | None) -> Any:
    """The configuration of the member that owns this requirement.

    REQ-d00278-I: a name is read in the vocabulary of the member owning the
    requirement being judged, never one merged from several. A graph that holds
    no membership answers with the invoking configuration.
    """
    repo_for_node = getattr(graph, "repo_for_node", None)
    if repo_for_node is None:
        return "", fallback
    try:
        entry = repo_for_node(node)
    except (KeyError, AttributeError):
        return "", fallback
    return getattr(entry, "name", ""), (getattr(entry, "config", None) or fallback)


# Implements: REQ-d00279-A, REQ-d00278-I+L
def scoped_requirements(
    graph: Any,
    scope: ReportScope | None,
    config: dict[str, Any] | None = None,
) -> ScopeResult:
    """The requirements a scope selects -- the one membership answer.

    Every reporting surface reads its iteration set from here. A ``None`` or
    unconstrained scope selects the whole population, so a caller need not branch
    on whether a scope was given.
    """
    nodes = list(_requirements(graph))
    population = len(nodes)

    if scope is None or scope.is_empty():
        return ScopeResult(
            ids=frozenset(n.id for n in nodes),
            population=population,
            unadmitted=(),
            scope=scope or ReportScope(),
        )

    # Resolution is per member, and cached per member rather than per node: the
    # vocabulary is a property of the repository, not of the requirement.
    by_repo: dict[str, list[Any]] = {}
    configs: dict[str, Any] = {}
    for node in nodes:
        repo, cfg = _config_for_node(graph, node, config)
        by_repo.setdefault(repo, []).append(node)
        configs[repo] = cfg

    selected: set[str] = set()
    unadmitted: list[UnadmittedName] = []
    for repo, members in by_repo.items():
        resolved = resolve_scope(
            scope,
            configs[repo],
            carried=carried_values(members),
            repo=repo or "this repository",
        )
        unadmitted.extend(resolved.unadmitted)
        selected.update(n.id for n in members if satisfies(n, resolved))

    return ScopeResult(
        ids=frozenset(selected),
        population=population,
        unadmitted=tuple(unadmitted),
        scope=scope,
    )


# Implements: REQ-p00084-D
def describe_scope(scope: ReportScope | None) -> str:
    """The scope a report was produced under, as a reader-facing phrase.

    A scoped report that does not say so is indistinguishable from one that lost
    requirements on the way, which is why every surface emitting a scoped report
    emits this beside it.
    """
    if scope is None or scope.is_empty():
        return "every requirement"
    parts: list[str] = []
    for prop in sorted(scope.properties()):
        wanted = scope.include.get(prop) or ()
        refused = scope.exclude.get(prop) or ()
        # Required values are alternatives; refused ones are all refused at once.
        # Rendering the refusals with "or" would describe a condition every
        # requirement meets, which is the opposite of what the scope does.
        clause = f"{prop} " + " and ".join(
            filter(
                None,
                [
                    " or ".join(wanted) if wanted else "",
                    ("excluding " + ", ".join(refused)) if refused else "",
                ],
            )
        )
        parts.append(clause)
    described = "; ".join(parts)
    if scope.match_status_roles:
        described += " (a named status stands for its role)"
    return described


# Implements: REQ-d00279-C
def scope_to_params(scope: ReportScope | None) -> dict[str, str]:
    """Serialize a scope for a report computed by a serving process.

    REQ-d00279-C: a report answered from a running daemon yields the same scoped
    set as one computed where it was asked for, which it cannot do if the scope
    does not survive the trip.
    """
    if scope is None or scope.is_empty():
        return {}
    params: dict[str, str] = {}
    for prop, values in scope.include.items():
        if values:
            params[f"scope_{prop}"] = SCOPE_VALUE_SEPARATOR.join(values)
    for prop, values in scope.exclude.items():
        if values:
            params[f"scope_not_{prop}"] = SCOPE_VALUE_SEPARATOR.join(values)
    if scope.match_status_roles:
        params["scope_match_status_roles"] = "1"
    return params


# Implements: REQ-d00279-C
def scope_from_params(params: Mapping[str, str]) -> ReportScope | None:
    """Rebuild a scope a serving process was handed. Inverse of scope_to_params."""
    include: dict[str, tuple[str, ...]] = {}
    exclude: dict[str, tuple[str, ...]] = {}
    for key, raw in params.items():
        if not raw or not key.startswith("scope_"):
            continue
        rest = key[len("scope_") :]
        if rest == "match_status_roles":
            continue
        target, prop = (
            (exclude, rest[len("not_") :]) if rest.startswith("not_") else (include, rest)
        )
        values = tuple(v.strip() for v in raw.split(SCOPE_VALUE_SEPARATOR) if v.strip())
        if values:
            target[prop] = values
    if not include and not exclude:
        return None
    return ReportScope(
        include=include,
        exclude=exclude,
        match_status_roles=params.get("scope_match_status_roles") == "1",
    )
