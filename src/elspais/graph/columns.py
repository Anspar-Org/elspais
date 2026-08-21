# Implements: REQ-d00282
"""Report columns: the one vocabulary naming the facts a report may state.

A report answers two questions about one estate -- which requirements it is
about, and which facts it states. ``graph/scope.py`` owns the first; this owns
the second (REQ-d00282). The two are independent in both directions
(REQ-d00282-H+I), which is why they are separate modules rather than one
selection with two halves.

A column is named by a stable key, never by the words it is displayed under: a
project may rename its display labels (REQ-d00258-K) and a selection written in
those words would break the day someone did (REQ-d00282-J). A coverage
dimension's total is the dimension's own key; the measures behind it are keyed
beneath it, so a reader can ask for the evidence they came for rather than
taking every measure of every dimension to reach it (REQ-d00282-B).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from elspais.graph.aggregation import COVERAGE_DIMENSIONS, MEASURE_WORDS, MEASURES

# A selection is written as a list, and its items are divided by this character.
# Column keys are identifier-shaped and cannot contain it.
COLUMN_LIST_SEPARATOR = ","

# A measure is keyed beneath the dimension it measures, so the key says what it
# is a measure OF as well as which measure it is (REQ-d00282-C).
MEASURE_KEY_SEPARATOR = "."


@dataclass(frozen=True)
class ColumnSpec:
    """One column a report may offer."""

    key: str
    header: str
    """The words this column is displayed under, absent a project override."""
    dimension: str = ""
    """The coverage dimension this column states, where it states one."""
    measure: str = ""
    """The measure of that dimension, where the column states one rather than
    the dimension's total."""
    group_only: bool = False
    """Whether this column states a fact only a GROUP of requirements has.

    A report whose rows are single requirements does not offer one: there is no
    count of requirements in a row that is one requirement. Offering a column
    that could only ever be blank would be offering a name for nothing.
    """

    @property
    def states_a_figure(self) -> bool:
        """Whether this column states a coverage figure at all.

        REQ-d00282-M turns on this: a column that never states a figure and a
        column whose figure is zero are different facts, and a reader who cannot
        tell them apart reads absence as nothing-done.
        """
        return bool(self.dimension)


# Columns naming what a row is about, or a property it carries. These state no
# coverage figure; REQ-d00282-L makes the first of them the floor beneath every
# selection.
_IDENTITY_COLUMNS: tuple[ColumnSpec, ...] = (
    ColumnSpec(key="id", header="ID"),
    ColumnSpec(key="title", header="Title"),
    ColumnSpec(key="level", header="Level"),
    ColumnSpec(key="status", header="Status"),
    ColumnSpec(key="implements", header="Implements"),
    ColumnSpec(key="hash", header="Hash"),
    ColumnSpec(key="file", header="File"),
    ColumnSpec(key="journeys", header="Journeys"),
    # Facts a GROUP of requirements has and a single one does not. They are
    # offered rather than prepended unasked: how many requirements a level
    # holds, and how many assertions they confer, are facts about the group
    # like any other, and a selection that did not name them is a selection
    # that did not ask for them (REQ-d00282-A+K). The *Assertion* count is also
    # the denominator every coverage figure in the row is taken over
    # (REQ-d00258-P), which is why each figure states its own denominator
    # inside its own cell rather than leaning on a neighbouring column.
    ColumnSpec(key="requirements", header="Requirements", group_only=True),
    ColumnSpec(key="assertions", header="Assertions", group_only=True),
)

# Measured in lines rather than assertions (REQ-d00254-B), so these carry no
# measures to select among -- which is why REQ-d00282-B is written over the
# dimensions of REQ-d00277 rather than over coverage at large.
_LINE_COLUMNS: tuple[ColumnSpec, ...] = (
    ColumnSpec(key="code_tested", header="Code Tested", dimension="code_tested"),
    ColumnSpec(key="lcov_tested", header="LCOV Tested", dimension="lcov_tested"),
)

_DIMENSION_HEADERS: dict[str, str] = {
    "implemented": "Implemented",
    "tested": "Tested",
    "verified": "Passing",
    "uat_coverage": "UAT Covered",
    "uat_verified": "UAT Passed",
}


def _build_specs() -> dict[str, ColumnSpec]:
    specs: dict[str, ColumnSpec] = {c.key: c for c in _IDENTITY_COLUMNS}
    for dim in COVERAGE_DIMENSIONS:
        head = _DIMENSION_HEADERS.get(dim, dim.replace("_", " ").title())
        specs[dim] = ColumnSpec(key=dim, header=head, dimension=dim)
        for measure in MEASURES:
            key = f"{dim}{MEASURE_KEY_SEPARATOR}{measure}"
            # REQ-d00282-C: the heading names the dimension AND the measure.
            # Either half alone leaves the reader guessing -- the dimension
            # alone hides which evidence the figure counts, and the measure
            # alone hides what it is a measure of.
            specs[key] = ColumnSpec(
                key=key,
                header=f"{head} ({MEASURE_WORDS[measure]})",
                dimension=dim,
                measure=measure,
            )
    for spec in _LINE_COLUMNS:
        specs[spec.key] = spec
    return specs


COLUMN_SPECS: dict[str, ColumnSpec] = _build_specs()


# Implements: REQ-d00282-E
# name: figure_cell
# use:  the ONE shape a coverage figure is stated in, wherever it is stated.
# def:  the credit, the assertions it was taken over, and the proportion --
#       "102/187 (54.5%)" -- in a single cell.
#
# A figure and its denominator and its percentage are one fact, so they are one
# column. Splitting them across cells made a named column produce three of them
# in one format and one in another, which is the divergence REQ-d00282-E
# forbids; keeping the shape here rather than in a renderer is what stops it
# reappearing the next time a format is added.
def figure_cell(covered: float, total: float, *, decimals: int = 0) -> str:
    """State one figure in one cell. The caller decides what an ABSENT one reads
    as (REQ-d00282-M) -- this states a figure that exists."""
    from elspais.graph.metrics import fmt_assertion_count

    pct = (covered / total * 100) if total else 0.0
    return f"{fmt_assertion_count(covered)}/{fmt_assertion_count(total)} ({pct:.{decimals}f}%)"


class UnofferedColumns(ValueError):
    """A selection named columns the report does not offer.

    REQ-d00282-F: a report is not produced under a selection honoured in part.
    The columns a report offers are the tool's own and identical everywhere, so
    a name among them that does not resolve is a mistake rather than a
    difference -- unlike a scope value, which is read against each member's own
    vocabulary and may legitimately be unknown to some of them (REQ-d00278-K).
    """

    def __init__(self, unoffered: Sequence[str], offered: Iterable[str]) -> None:
        self.unoffered = tuple(unoffered)
        self.offered = tuple(sorted(offered))
        named = ", ".join(self.unoffered)
        super().__init__(
            f"No column named {named}. The columns this report offers are: "
            + ", ".join(self.offered)
        )


@dataclass(frozen=True)
class ColumnSelection:
    """The columns a reader asked for, in the order they asked for them."""

    keys: tuple[str, ...]

    def __bool__(self) -> bool:
        return bool(self.keys)

    def specs(self) -> tuple[ColumnSpec, ...]:
        return tuple(COLUMN_SPECS[k] for k in self.keys)


def parse_column_selection(raw: str | Sequence[str] | None) -> ColumnSelection | None:
    """Read a selection as written, without judging it against any report.

    Returns None where nothing was named, so a caller need not distinguish
    "asked for nothing" from "asked for everything" -- a report answering None
    states the columns it would have anyway.
    """
    if raw is None:
        return None
    items: list[str] = []
    values = [raw] if isinstance(raw, str) else list(raw)
    for value in values:
        for item in str(value).split(COLUMN_LIST_SEPARATOR):
            item = item.strip()
            if item:
                items.append(item)
    if not items:
        return None
    # A column named twice is named once: a report cannot state it twice, and
    # refusing would make a harmless request an error.
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        low = item.lower()
        if low in seen:
            continue
        seen.add(low)
        ordered.append(low)
    return ColumnSelection(keys=tuple(ordered))


# Implements: REQ-d00282-A+F+K+L
def resolve_columns(
    selection: ColumnSelection | None,
    offered: Sequence[str],
    identity_key: str = "id",
) -> tuple[str, ...]:
    """The columns a report states, given what it offers and what was asked.

    Honours the order the selection names (REQ-d00282-K) and keeps the column
    saying what each row is about whatever was named (REQ-d00282-L). Refuses
    outright where any named column is not offered (REQ-d00282-F), so a reader
    never receives a report narrower than the one they asked for while it looks
    exactly like the one they wanted.
    """
    if selection is None:
        return tuple(offered)

    offered_lower = {k.lower(): k for k in offered}
    unoffered = [k for k in selection.keys if k not in offered_lower]
    if unoffered:
        raise UnofferedColumns(unoffered, offered)

    chosen = [offered_lower[k] for k in selection.keys]
    if identity_key and identity_key in offered and identity_key not in chosen:
        chosen.insert(0, identity_key)
    return tuple(chosen)


def header_for(key: str, config: Mapping[str, Any] | None = None) -> str:
    """The words a column is displayed under.

    Read through the project's configured mapping (REQ-d00258-K) so a project
    that renames a dimension renames it everywhere, while the key a selection
    names stays what it was (REQ-d00282-J).
    """
    spec = COLUMN_SPECS.get(key)
    if spec is None:
        return key
    if not spec.dimension:
        return spec.header
    from elspais.config.status_words import get_status_words

    words = get_status_words(config or {})
    word = words.get(spec.dimension) or _DIMENSION_HEADERS.get(spec.dimension, spec.header)
    if spec.measure:
        return f"{word} ({MEASURE_WORDS[spec.measure]})"
    return word
