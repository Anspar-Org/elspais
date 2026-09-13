# Implements: REQ-d00282
"""Report values: the one vocabulary naming the facts a report may state.

A report answers two questions about one estate -- which requirements it is
about, and which facts it states. ``graph/scope.py`` owns the first; this owns
the second (REQ-d00282). The two are independent in both directions
(REQ-d00282-H+I), which is why they are separate modules rather than one
selection with two halves.

A value is not a column. A column is how a report with rows and headings
renders one; a format with numbers states the same value as numbers. So this
module names values and their keys, and speaks of columns only where a table's
rendering is genuinely the subject.

A value is named by a stable key, never by the words it is displayed under: a
project may rename its display labels (REQ-d00258-K) and a selection written in
those words would break the day someone did (REQ-d00282-J). A coverage
dimension's total is the dimension's own key; the measures behind it are keyed
beneath it, so a reader can ask for the evidence they came for rather than
taking every measure of every dimension to reach it (REQ-d00282-B).

A coverage figure is a credit counted over a population, and REQ-d00282-B makes
each of the three -- the credit, the population, their proportion -- selectable
in its own right, for a dimension's total as for each measure behind it. So a
figure is offered two ways: the WHOLE FIGURE, which a table states in one cell
and a structured format states as an object of its numbers, and the SCALAR
PARTS beneath it, which each state one number. A proportion is derived from the
other two rather than being a third fact, so it is carried unrounded and only a
rendering rounds it. Some values have only the one form: the assertions a
dimension counted as passed, failed or awaiting a result are counts with no
proportion of their own (REQ-d00258-O), and though the three sum to the tested
count a reader wanting only the failures is owed only the failures.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from elspais.graph.aggregation import COVERAGE_DIMENSIONS, MEASURE_WORDS, MEASURES

# A selection is written as a list, and its items are divided by this character.
# Value keys are identifier-shaped and cannot contain it.
VALUE_LIST_SEPARATOR = ","

# A measure is keyed beneath the dimension it measures, so the key says what it
# is a measure OF as well as which measure it is (REQ-d00282-C). A scalar part
# is keyed beneath whichever of the two it decomposes, by the same character.
MEASURE_KEY_SEPARATOR = "."

# Implements: REQ-d00282-B
# name: SCALAR_PARTS
# use:  the three ways one coverage figure decomposes into a single number.
# def:  the credit, the assertions the credit was counted over, and the
#       proportion the first is of the second.
PART_COUNT = "count"
PART_TOTAL = "total"
PART_RATIO = "ratio"
SCALAR_PARTS: tuple[str, ...] = (PART_COUNT, PART_TOTAL, PART_RATIO)

# Implements: REQ-d00258-O, REQ-d00282-B
# name: COUNT_PARTS
# use:  the parts of the Tested figure that are counts and nothing else.
# def:  what came back for the assertions a dimension counted as tested.
#
# These decompose no figure, so they take no proportion of their own and are
# offered on the Tested dimension alone. They are individually selectable
# because a reader watching for failures is owed the failures and not the two
# counts that happen to sum with them.
COUNT_PARTS: tuple[str, ...] = ("passed", "failed", "awaiting")

# The dimension whose figure carries the breakdown of REQ-d00258-O.
BREAKDOWN_DIMENSION = "tested"

# Implements: REQ-d00254-B, REQ-d00282-N
# name: LINE_DIMENSIONS
# use:  tell a figure counted in LINES from one counted in *Assertions*, so no
#       surface adds the two or reads one under the other's denominator.
# def:  the figures REQ-d00254-B measures in lines. ``lcov_tested`` is NOT one
#       of them: it is a `CoverageDimension` crediting *Assertions* from line
#       evidence, so it is counted over assertions like any other dimension and
#       only its EVIDENCE is lines.
#
# A line figure has none of the four measures REQ-d00282-B decomposes -- there
# is no citation naming an *Assertion* behind a line, and nothing conducts one
# up a `Refines:` chain -- but it is still a count over a population, so
# REQ-d00282-N gives it the same three scalars every figure has.
LINE_DIMENSIONS: frozenset[str] = frozenset({"code_tested"})

# Implements: REQ-d00258-E, REQ-d00282-N
# name: PART_ATTRIBUTED
# use:  the READING of a line figure that says how many of its lines a
#       verifying test can be named for.
# def:  a fourth part beneath a line figure, offered on the dimension that
#       records per-test contexts and absent where the tooling recorded none.
#
# A different question from the figure itself, so it is named for the
# attribution rather than for the figure at large (REQ-d00282-C) and carries
# its own absence: REQ-d00258-E suppresses it where no context was recorded,
# and that suppression must not take the lines COVERED with it -- those were
# measured, and a report holding them and saying nothing has withheld an
# answer it has.
PART_ATTRIBUTED = "attributed"
ATTRIBUTION_DIMENSION = "code_tested"

# Implements: REQ-d00254-I, REQ-d00282-B
# name: FLAG_CARRIED
# use:  disclose that a dimension's verdict was carried from a baseline rather
#       than produced by the run being reported.
# def:  the `carried` bit REQ-d00254-I puts on the verified dimension, offered
#       as a value in its own right.
#
# The disclosure used to ride inside the whole figure -- "(baseline)" appended
# to a cell -- so a reader who selected the credit alone lost it. It is neither
# a measure nor a number, so it is keyed beside them rather than beneath one of
# them, and it is offered on the one dimension REQ-d00254-I gives it to.
FLAG_CARRIED = "carried"
CARRIED_DIMENSION = "verified"

# The words a flag is displayed under, one per state. A flag is not a number,
# so a table states the word rather than a count, and a format with booleans
# states the boolean (REQ-d00282-E).
_FLAG_WORDS: dict[str, str] = {FLAG_CARRIED: "provenance"}
CARRIED_CELL: dict[bool, str] = {True: "baseline", False: "fresh"}

# The words a part is displayed under. Display words only -- a selection names
# the part by its key, which no project can rename (REQ-d00282-J).
_PART_WORDS: dict[str, str] = {
    PART_COUNT: "credited",
    PART_TOTAL: "counted over",
    PART_RATIO: "proportion",
    "passed": "passed",
    "failed": "failed",
    "awaiting": "awaiting a result",
}

# Implements: REQ-d00282-C+N
# The same three parts, named for what a LINE figure counts. A key is stable and
# a display word is not (REQ-d00282-J), so the domain reads in the words while
# the grammar a selection is written in stays one grammar: ``.count`` is the
# credit of whatever figure it sits beneath, and beneath a line figure the
# credit is a line.
_LINE_PART_WORDS: dict[str, str] = {
    PART_COUNT: "lines covered",
    PART_TOTAL: "lines measured",
    PART_RATIO: "proportion",
    PART_ATTRIBUTED: "lines attributed",
}

# The decimals a proportion is ROUNDED TO when a cell renders it. The value
# itself is never rounded (REQ-d00282-B's Rationale: a proportion is derived
# from the other two, and a report stating all three states one fact three ways
# rather than three facts) -- this is a spelling, which REQ-d00282-E leaves to
# the format.
RATIO_CELL_DECIMALS = 3


@dataclass(frozen=True)
class ValueSpec:
    """One value a report may offer."""

    key: str
    header: str
    """The words this value is displayed under, absent a project override."""
    dimension: str = ""
    """The coverage dimension this value states, where it states one."""
    measure: str = ""
    """The measure of that dimension, where the value is taken on one rather
    than on the dimension's total."""
    part: str = ""
    """The single scalar this value states of the figure named above it.

    Empty for the WHOLE FIGURE, which states the credit, what it was counted
    over and their proportion together -- one cell to a table, an object of
    numbers to a structured format. One of ``SCALAR_PARTS`` or ``COUNT_PARTS``
    where the value is one number in its own right (REQ-d00282-B).
    """
    flag: str = ""
    """The bit this value discloses about the figure named above it.

    Empty for every value that states a figure or a number. ``FLAG_CARRIED``
    where the value is the provenance bit of REQ-d00254-I, which is a state
    rather than a quantity and so is rendered as a word or a boolean rather
    than as a count.
    """
    group_only: bool = False
    """Whether this value is a fact only a GROUP of requirements has.

    A report whose rows are single requirements does not offer one: there is no
    count of requirements in a row that is one requirement. Offering a value
    that could only ever be blank would be offering a name for nothing.
    """

    @property
    def states_a_figure(self) -> bool:
        """Whether this value is a coverage figure at all.

        REQ-d00282-M turns on this: a value that never states a figure and a
        value whose figure is zero are different facts, and a reader who cannot
        tell them apart reads absence as nothing-done.
        """
        return bool(self.dimension)

    @property
    def is_scalar(self) -> bool:
        """Whether this value is ONE number rather than a whole figure.

        What separates the two is not how the value looks but what it IS: a
        scalar is a number wherever it is stated, and a format with numbers
        states it as one (REQ-d00282-E).
        """
        return bool(self.part)

    @property
    def is_flag(self) -> bool:
        """Whether this value is a disclosed BIT rather than a figure.

        A flag has no denominator and no proportion, so nothing that decomposes
        a figure applies to it -- which is why it is asked about separately
        rather than being folded into ``is_scalar``.
        """
        return bool(self.flag)


# Values naming what a row is about, or a property it carries. These state no
# coverage figure; REQ-d00282-L makes the first of them the floor beneath every
# selection.
_IDENTITY_VALUES: tuple[ValueSpec, ...] = (
    ValueSpec(key="id", header="ID"),
    ValueSpec(key="title", header="Title"),
    ValueSpec(key="level", header="Level"),
    ValueSpec(key="status", header="Status"),
    ValueSpec(key="implements", header="Implements"),
    ValueSpec(key="hash", header="Hash"),
    ValueSpec(key="file", header="File"),
    ValueSpec(key="journeys", header="Journeys"),
    # Facts a GROUP of requirements has and a single one does not. They are
    # offered rather than prepended unasked: how many requirements a level
    # holds, and how many assertions they confer, are facts about the group
    # like any other, and a selection that did not name them is a selection
    # that did not ask for them (REQ-d00282-A+K). The *Assertion* count is also
    # the denominator every coverage figure in the row is taken over
    # (REQ-d00258-P), which is why each figure states its own denominator
    # inside itself rather than leaning on a neighbouring value.
    ValueSpec(key="requirements", header="Requirements", group_only=True),
    ValueSpec(key="assertions", header="Assertions", group_only=True),
)

_DIMENSION_HEADERS: dict[str, str] = {
    "implemented": "Implemented",
    "tested": "Tested",
    "verified": "Passing",
    "uat_coverage": "UAT Covered",
    "uat_verified": "UAT Passed",
    # Not dimensions of REQ-d00277, but figures a value is named for all the
    # same, and their heading is derived here for the same reason: a part's
    # heading is the figure's heading with a qualifier, and deriving it from a
    # spec that already carries one qualifies it twice.
    "code_tested": "Code Tested",
    "lcov_tested": "LCOV Tested",
}


# Implements: REQ-d00282-C
def _qualified_header(
    head: str,
    measure: str,
    part: str,
    flag: str = "",
    words: Mapping[str, str] | None = None,
) -> str:
    """The words one value is displayed under, absent a project override.

    REQ-d00282-C: a value taken on a measure names the dimension AND the
    measure. Either half alone leaves the reader guessing -- the dimension
    alone hides which evidence the figure counts, and the measure alone hides
    what it is a measure of. A scalar part is a third qualifier on the same
    heading rather than a heading of its own, for the same reason: "credited"
    on its own says nothing about what was credited.
    """
    qualifiers = [MEASURE_WORDS[measure]] if measure else []
    if part:
        qualifiers.append((words or _PART_WORDS)[part])
    if flag:
        qualifiers.append(_FLAG_WORDS[flag])
    return f"{head} ({', '.join(qualifiers)})" if qualifiers else head


# Implements: REQ-d00282-C
def _figure_specs(
    dim: str, head: str, measure: str, words: Mapping[str, str] | None = None
) -> list[ValueSpec]:
    """One figure of one dimension: its composite, then its scalar parts.

    The composite comes first because it is what an unqualified name has always
    meant, and REQ-d00282-G forbids a further value moving what an already
    expressible selection states.
    """
    base = f"{dim}{MEASURE_KEY_SEPARATOR}{measure}" if measure else dim
    specs = [
        ValueSpec(
            key=base,
            header=_qualified_header(head, measure, "", words=words),
            dimension=dim,
            measure=measure,
        )
    ]
    specs += [
        ValueSpec(
            key=f"{base}{MEASURE_KEY_SEPARATOR}{part}",
            header=_qualified_header(head, measure, part, words=words),
            dimension=dim,
            measure=measure,
            part=part,
        )
        for part in SCALAR_PARTS
    ]
    return specs


# Implements: REQ-d00282-J
def _build_specs() -> dict[str, ValueSpec]:
    specs: dict[str, ValueSpec] = {c.key: c for c in _IDENTITY_VALUES}
    for dim in COVERAGE_DIMENSIONS:
        head = _DIMENSION_HEADERS.get(dim, dim.replace("_", " ").title())
        for spec in _figure_specs(dim, head, ""):
            specs[spec.key] = spec
        # Implements: REQ-d00258-O, REQ-d00282-B
        # Counts, and only counts: what came back for the tested assertions
        # takes no proportion of its own, so no `.ratio` is offered beneath
        # one and asking for it is refused like any other name the report does
        # not offer (REQ-d00282-F).
        # Implements: REQ-d00254-I, REQ-d00282-B
        # The provenance bit as a value of its own, so a reader selecting one
        # number of the dimension still reaches the disclosure that used to be
        # trapped inside the whole figure's cell.
        if dim == CARRIED_DIMENSION:
            key = f"{dim}{MEASURE_KEY_SEPARATOR}{FLAG_CARRIED}"
            specs[key] = ValueSpec(
                key=key,
                header=_qualified_header(head, "", "", FLAG_CARRIED),
                dimension=dim,
                flag=FLAG_CARRIED,
            )
        if dim == BREAKDOWN_DIMENSION:
            for part in COUNT_PARTS:
                key = f"{dim}{MEASURE_KEY_SEPARATOR}{part}"
                specs[key] = ValueSpec(
                    key=key,
                    header=_qualified_header(head, "", part),
                    dimension=dim,
                    part=part,
                )
        for measure in MEASURES:
            for spec in _figure_specs(dim, head, measure):
                specs[spec.key] = spec
    # Implements: REQ-d00254-B, REQ-d00282-N
    # A line figure carries none of the four measures -- there is no citation
    # naming an *Assertion* behind a line -- but it is still a count over a
    # population, so it takes the same three scalars every figure takes. The
    # attribution is a FOURTH reading of the same lines rather than a part of
    # the figure, so it is offered beside them and carries its own absence
    # (REQ-d00258-E).
    for dim in sorted(LINE_DIMENSIONS):
        head = _DIMENSION_HEADERS[dim]
        for spec in _figure_specs(dim, head, "", words=_LINE_PART_WORDS):
            specs[spec.key] = spec
        if dim == ATTRIBUTION_DIMENSION:
            key = f"{dim}{MEASURE_KEY_SEPARATOR}{PART_ATTRIBUTED}"
            specs[key] = ValueSpec(
                key=key,
                header=_qualified_header(head, "", PART_ATTRIBUTED, words=_LINE_PART_WORDS),
                dimension=dim,
                part=PART_ATTRIBUTED,
            )
    # Implements: REQ-d00254-B, REQ-d00282-B
    # ``lcov_tested`` credits *Assertions* from line evidence, so it is counted
    # over assertions and decomposes like any other figure. It is not one of
    # REQ-d00277's dimensions and nothing conducts it, so it carries no measures
    # -- the whole figure and the three scalars behind it, and no more.
    for spec in _figure_specs("lcov_tested", _DIMENSION_HEADERS["lcov_tested"], ""):
        specs[spec.key] = spec
    return specs


VALUE_SPECS: dict[str, ValueSpec] = _build_specs()


# Implements: REQ-d00282-E
# name: figure_cell
# use:  the ONE shape a coverage figure is stated in, wherever it is stated.
# def:  the credit, the assertions it was taken over, and the proportion --
#       "102/187 (54.5%)" -- in a single cell.
#
# A figure and its denominator and its percentage are one fact, so a table
# states them in one cell. Splitting them across cells made a named value
# produce three columns in one format and one in another, which is the
# divergence REQ-d00282-E forbids; keeping the shape here rather than in a
# renderer is what stops it reappearing the next time a format is added.
def figure_cell(covered: float, total: float, *, decimals: int = 0) -> str:
    """State one figure in one cell. The caller decides what an ABSENT one reads
    as (REQ-d00282-M) -- this states a figure that exists."""
    from elspais.graph.metrics import fmt_assertion_count

    pct = (covered / total * 100) if total else 0.0
    return f"{fmt_assertion_count(covered)}/{fmt_assertion_count(total)} ({pct:.{decimals}f}%)"


# Implements: REQ-d00282-B+E
# name: scalar_value
# use:  the ONE number a scalar part of a coverage figure states, wherever it
#       is stated.
# def:  the credit, the assertions it was counted over, or the proportion the
#       first is of the second -- as a number and nothing else.
#
# The proportion is DERIVED here rather than carried anywhere, and it is
# returned unrounded: it is not a third fact beside the other two, and a
# consumer that re-derives it from them must not disagree with one that read
# it. Rounding is a rendering decision and belongs to whatever renders a cell.
def scalar_value(covered: float, total: float, part: str) -> float:
    """One part of one figure. The caller decides what an ABSENT figure reads
    as (REQ-d00282-M) -- this decomposes a figure that exists."""
    if part == PART_COUNT:
        # A coverage count is a REAL number (REQ-d00069-M), so it is stated as
        # one even where it came out whole -- a consumer reading a schema off
        # one row must not meet an integer in the next.
        return float(covered)
    if part == PART_TOTAL:
        return float(total)
    if part == PART_RATIO:
        return (covered / total) if total else 0.0
    raise ValueError(f"{part} is not a part of a coverage figure")


# Implements: REQ-d00282-E
def scalar_cell(value: float, part: str) -> str:
    """A scalar part as a table renders it.

    REQ-d00282-E binds which values a report states, never how each is spelled,
    so a format with numbers states the number and a table states this. A
    proportion is rounded HERE and never in the value, which is what keeps the
    number a consumer reads equal to the one it can re-derive.
    """
    if part == PART_RATIO:
        return f"{value:.{RATIO_CELL_DECIMALS}f}"
    from elspais.graph.metrics import fmt_assertion_count

    return fmt_assertion_count(value)


# Implements: REQ-d00254-I, REQ-d00282-E
def flag_cell(value: bool) -> str:
    """A disclosed bit as a table renders it.

    A bit is a state, so a table states the word for the state rather than a
    number for it; a format with booleans states the boolean. Which of the two
    is a spelling, and REQ-d00282-E leaves a spelling to the format.
    """
    return CARRIED_CELL[bool(value)]


# Implements: REQ-d00282-B+D+E
# name: figure_object
# use:  the ONE shape a coverage figure takes in a format that has numbers.
# def:  the credit, the assertions it was counted over and their proportion --
#       and, for a figure carrying the breakdown of REQ-d00258-O, its counts --
#       under the very keys a selection names them by.
#
# The mirror of ``figure_cell``: one value, stated in each format's own kind. A
# table has one cell and states "3/7 (43%)"; a structured format has numbers
# and states them. It is assembled by ASKING the same reader that answers a
# selection naming one part, so the object a reader gets for ``implemented``
# holds exactly what naming ``implemented.count`` would have given them
# (REQ-d00282-D) -- an equality that holds by construction rather than by
# agreement between two computations.
#
# Returns None where the credit is absent, so a figure a row does not have is
# null rather than an object of nulls (REQ-d00282-M).
def figure_object(
    base: str,
    part_value: Callable[[str], Any],
    *,
    extra_parts: Sequence[str] = (),
) -> dict[str, Any] | None:
    """State one figure as its numbers, or None where the row has no figure."""
    parts = tuple(SCALAR_PARTS) + tuple(extra_parts)
    stated = {part: part_value(f"{base}{MEASURE_KEY_SEPARATOR}{part}") for part in parts}
    if stated[PART_COUNT] is None:
        return None
    return stated


# Implements: REQ-d00282-B+E+K+M
# name: nest_values
# use:  the ONE place a report's values become the object a structured format
#       states them in.
# def:  each stated value placed under the path its selection key spells, so
#       ``implemented.count`` lands at ``count`` inside ``implemented``.
#
# A selection key is a PATH -- a dimension, then a measure, then a part -- and
# the object mirrors it, so a consumer reaching a number holds the same string
# the reader wrote to select it. Flattening the path into one key instead made
# the two commands disagree (``implemented_count`` against ``implemented.count``)
# and made a figure and its parts unrelatable; nesting is what removes the
# choice. Every report builds its rows here, so trace and summary cannot state
# one selection two ways (REQ-d00282-E).
#
# Selecting a figure AND a part of it names one place twice. The figure's own
# object already holds the part, so the merge is a no-op rather than a conflict
# -- which is REQ-d00282-D holding structurally.
def nest_values(items: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    """Place each ``(key, value)`` at the path its key spells, in order."""
    out: dict[str, Any] = {}
    for key, value in items:
        path = key.split(MEASURE_KEY_SEPARATOR)
        node = out
        for step in path[:-1]:
            existing = node.get(step)
            if not isinstance(existing, dict):
                # A step that is absent, or that an earlier key stated as an
                # absence, still has to carry the value named beneath it: the
                # leaf says the same thing by being null there.
                existing = {}
                node[step] = existing
            node = existing
        leaf = path[-1]
        if isinstance(value, Mapping):
            target = node.get(leaf)
            if not isinstance(target, dict):
                target = {}
                node[leaf] = target
            target.update(value)
        elif not isinstance(node.get(leaf), dict):
            node[leaf] = value
    return out


# Implements: REQ-d00282-D
# Implements: REQ-d00282-B+E+K+M
# name: structured_row
# use:  the ONE place a report's row becomes the object a format with numbers
#       states it as. Every command that emits one builds it here.
# def:  each stated value, in the order the selection named it, at the path its
#       key spells -- a whole figure as an object of its numbers, a part or a
#       flag as the single value it is, and anything the row does not have as
#       null.
#
# Written once rather than per command because the alternative was two commands
# spelling one selection two ways: the same figure arrived as
# ``implemented_count`` from one and ``implemented.count`` from the other, and
# a consumer could not read both. Where the shape is decided in one place they
# cannot drift (REQ-d00282-E).
def structured_row(
    keys: Sequence[str],
    part_value: Callable[[str], Any],
    plain_value: Callable[[str], Any],
    *,
    offers: Iterable[str] = (),
    path_of: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """One row of a structured format, stating exactly the values named.

    ``part_value`` answers for a single number or flag beneath a figure;
    ``plain_value`` answers for everything that is not a coverage figure at
    all. ``offers`` is everything the report offers, which decides what a whole
    figure carries beside its three numbers: a report states inside a figure
    only what it would state had the reader named it separately (REQ-d00282-D).
    ``path_of`` renames the path one key is stated under, for a value a format
    states under a name of its own.
    """
    offered = set(offers)
    items: list[tuple[str, Any]] = []
    for key in keys:
        spec = VALUE_SPECS.get(key)
        path = (path_of or {}).get(key, key)
        if spec is None or not spec.states_a_figure:
            items.append((path, plain_value(key)))
        elif spec.is_scalar or spec.is_flag:
            items.append((path, part_value(key)))
        else:
            # Implements: REQ-d00254-I, REQ-d00258-O
            # What a table bundles into a figure's cell -- the Tested breakdown,
            # and the provenance the Passing cell discloses as "(baseline)" --
            # is stated inside that figure's object too, so one selection states
            # the same facts whichever format renders it (REQ-d00282-E). A
            # MEASURE of a dimension carries neither: the counts are what came
            # back overall, and the provenance is the dimension's rather than
            # any one measure's.
            extra: tuple[str, ...] = ()
            if not spec.measure:
                candidates = COUNT_PARTS if spec.dimension == BREAKDOWN_DIMENSION else ()
                if spec.dimension == CARRIED_DIMENSION:
                    candidates = (*candidates, FLAG_CARRIED)
                # Implements: REQ-d00258-E, REQ-d00282-N
                # The attribution reading rides inside the line figure's object
                # for the same reason: a reader naming the figure is stated
                # what naming its parts would have stated. Its suppression is
                # its own -- the object carries null there while the lines
                # covered stand.
                if spec.dimension == ATTRIBUTION_DIMENSION:
                    candidates = (*candidates, PART_ATTRIBUTED)
                extra = tuple(
                    part for part in candidates if f"{key}{MEASURE_KEY_SEPARATOR}{part}" in offered
                )
            items.append((path, figure_object(key, part_value, extra_parts=extra)))
    return nest_values(items)


class UnofferedValues(ValueError):
    """A selection named values the report does not offer.

    REQ-d00282-F: a report is not produced under a selection honoured in part.
    The values a report offers are the tool's own and identical everywhere, so
    a name among them that does not resolve is a mistake rather than a
    difference -- unlike a scope value, which is read against each member's own
    vocabulary and may legitimately be unknown to some of them (REQ-d00278-K).
    """

    def __init__(self, unoffered: Sequence[str], offered: Iterable[str]) -> None:
        self.unoffered = tuple(unoffered)
        self.offered = tuple(sorted(offered))
        named = ", ".join(self.unoffered)
        super().__init__(
            f"No value named {named}. The values this report offers are: " + ", ".join(self.offered)
        )


@dataclass(frozen=True)
class ValueSelection:
    """The values a reader asked for, in the order they asked for them."""

    keys: tuple[str, ...]

    def __bool__(self) -> bool:
        return bool(self.keys)

    def specs(self) -> tuple[ValueSpec, ...]:
        return tuple(VALUE_SPECS[k] for k in self.keys)


# Implements: REQ-d00282-G
# Implements: REQ-d00282-A
def parse_value_selection(raw: str | Sequence[str] | None) -> ValueSelection | None:
    """Read a selection as written, without judging it against any report.

    Returns None where nothing was named, so a caller need not distinguish
    "asked for nothing" from "asked for everything" -- a report answering None
    states the values it would have anyway.
    """
    if raw is None:
        return None
    items: list[str] = []
    values = [raw] if isinstance(raw, str) else list(raw)
    for value in values:
        for item in str(value).split(VALUE_LIST_SEPARATOR):
            item = item.strip()
            if item:
                items.append(item)
    if not items:
        return None
    # A value named twice is named once: a report cannot state it twice, and
    # refusing would make a harmless request an error.
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        low = item.lower()
        if low in seen:
            continue
        seen.add(low)
        ordered.append(low)
    return ValueSelection(keys=tuple(ordered))


# Implements: REQ-d00282-G+J
# Implements: REQ-d00282-A+F+K+L
def resolve_values(
    selection: ValueSelection | None,
    offered: Sequence[str],
    identity_key: str = "id",
) -> tuple[str, ...]:
    """The values a report states, given what it offers and what was asked.

    Honours the order the selection names (REQ-d00282-K) and keeps the value
    saying what each row is about whatever was named (REQ-d00282-L). Refuses
    outright where any named value is not offered (REQ-d00282-F), so a reader
    never receives a report narrower than the one they asked for while it looks
    exactly like the one they wanted.
    """
    if selection is None:
        return tuple(offered)

    offered_lower = {k.lower(): k for k in offered}
    unoffered = [k for k in selection.keys if k not in offered_lower]
    if unoffered:
        raise UnofferedValues(unoffered, offered)

    chosen = [offered_lower[k] for k in selection.keys]
    if identity_key and identity_key in offered and identity_key not in chosen:
        chosen.insert(0, identity_key)
    return tuple(chosen)


# Implements: REQ-d00282-C+J
# Implements: REQ-d00258-K
def header_for(key: str, config: Mapping[str, Any] | None = None) -> str:
    """The words a value is displayed under.

    Read through the project's configured mapping (REQ-d00258-K) so a project
    that renames a dimension renames it everywhere, while the key a selection
    names stays what it was (REQ-d00282-J).
    """
    spec = VALUE_SPECS.get(key)
    if spec is None:
        return key
    if not spec.dimension:
        return spec.header
    from elspais.config.status_words import get_status_words

    words = get_status_words(config or {})
    word = words.get(spec.dimension) or _DIMENSION_HEADERS.get(spec.dimension, spec.header)
    part_words = _LINE_PART_WORDS if spec.dimension in LINE_DIMENSIONS else _PART_WORDS
    return _qualified_header(word, spec.measure, spec.part, spec.flag, words=part_words)
