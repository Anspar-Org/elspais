"""Single shared coverage aggregation for all reporting surfaces.

Implements: REQ-d00258-C
CLI summary, MCP get_project_summary, and the viewer all read this module so
identical questions receive identical answers.

Coverage is measured on the four measures of REQ-d00069-L -- what a citation
named (direct/indirect) crossed with where the evidence sits (immediate/
rolled-up) -- plus the per-*Assertion* total of REQ-d00069-N. Every helper
here that scores coverage takes the measure it is scoring by name, so a
figure and its denominator are always made of the same kind of evidence
(REQ-d00258-I) and no surface can read a number without saying which one it
asked for. A surface reporting what still needs doing reads
``WORK_LIST_MEASURE`` (REQ-d00258-M); a surface reporting how far along the
estate is headlines ``"total"`` (REQ-d00258-A).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from elspais.graph.GraphNode import NodeKind
from elspais.graph.metrics import (
    CoverageDimension,
    CoverageSource,
    RollupMetrics,
    has_integration,
    integrates_by_associate,
    integrates_total,
    tested_and_passing,
    tested_partition,
)

# Implements: REQ-d00258-H
# Unified coverage-state vocabulary: the requirement tier, per-assertion standing,
# and viewer filter bucket all draw from this single {full,partial,failing,missing}
# set (identity map -- no separate direct/indirect tier states).
TIER_TO_BUCKET: dict[str, str] = {
    "full": "full",
    "partial": "partial",
    "failing": "failing",
    "missing": "missing",
}

# The coverage chain's RELATIVE-denominator convention, single-sourced here so
# both the requirement-level tier buckets (this module) and the badge
# projection (html/generator.py) measure each chained dimension over the SAME
# label set (REQ-d00258-C). Each measured dimension is scored over the labels
# that qualified at the PRIOR link of the chain, not over every assertion:
# Tested over IMPLEMENTED labels, Passing (verified) over TESTED labels,
# UAT-Passed over UAT-COVERED labels. ``implemented`` and ``uat_coverage`` are
# ABSOLUTE (measured over all assertions) and deliberately absent from this map.
# Implements: REQ-d00277
# The coverage dimensions, in the order a reader meets them: each answers a
# different question, conferred by a different relationship. Named once so a
# surface reporting "every dimension" cannot report a different set from the
# one the requirement defines.
COVERAGE_DIMENSIONS: tuple[str, ...] = (
    "implemented",
    "tested",
    "verified",
    "uat_coverage",
    "uat_verified",
)

DENOMINATOR_DIMENSION: dict[str, str] = {
    "tested": "implemented",
    "verified": "tested",
    "uat_verified": "uat_coverage",
}


# Implements: REQ-d00069-L, REQ-d00069-N
# Every per-*Assertion* map a surface may score, by name. The four measures of
# REQ-d00069-L are the primary entries; ``total`` is the per-*Assertion*
# greatest of them (REQ-d00069-N) and ``immediate`` is the strongest evidence
# ATTACHED here whichever a citation named -- neither is a fifth measure, both
# are derived views a surface asks for by name.
_MEASURE_ATTRS: dict[str, str] = {
    "immediate_direct": "immediate_direct_by_label",
    "immediate_indirect": "immediate_indirect_by_label",
    "rolled_direct": "rolled_direct_by_label",
    "rolled_indirect": "rolled_indirect_by_label",
}

MEASURES: tuple[str, ...] = (
    "immediate_direct",
    "immediate_indirect",
    "rolled_direct",
    "rolled_indirect",
)

# Implements: REQ-d00258-A, REQ-d00258-J
# The word each measure is reported under. ONE vocabulary, so a reader meets
# the same four names on the CLI and in the viewer and never has to work out
# whether two surfaces are talking about the same thing. Published beside a
# figure rather than compressed into a caveat marker (REQ-d00258-J).
MEASURE_WORDS: dict[str, str] = {
    "immediate_direct": "cited by name here",
    "immediate_indirect": "whole-requirement",
    "rolled_direct": "conducted direct",
    "rolled_indirect": "conducted indirect",
}


# Implements: REQ-d00258-M
# The measure a surface reporting WHICH assertions need work reads: a citation
# named the *Assertion* and the evidence is attached to it. Named once so
# ``gaps``, the health coverage checks, and anything else answering "what is
# left to do" cannot drift apart about what counts as done.
WORK_LIST_MEASURE = "immediate_direct"

# The measure a surface reporting how far along the estate is headlines
# (REQ-d00258-A): each *Assertion* counted once, at the greatest of its four.
HEADLINE_MEASURE = "total"


def measure_by_label(dim: CoverageDimension, measure: str) -> dict[str, float]:
    """The per-*Assertion* fractions of ``dim`` for ``measure``.

    ONE resolution from a measure's name to its map, so a surface names the
    measure it is reading and every surface reading that name gets the same
    numbers (REQ-d00258-C).
    """
    if measure == "total":
        return dim.total_by_label
    if measure == "immediate":
        # The stronger of the two immediate measures per *Assertion*: evidence
        # attached HERE, whether its citation named the *Assertion* or only the
        # requirement. Conducted value is deliberately absent -- this answers
        # "is there evidence at this requirement at all".
        out = dict(dim.immediate_direct_by_label)
        for lbl, frac in dim.immediate_indirect_by_label.items():
            if frac > out.get(lbl, 0.0):
                out[lbl] = frac
        return out
    attr = _MEASURE_ATTRS.get(measure)
    if attr is None:
        raise ValueError(f"unknown coverage measure: {measure!r}")
    return getattr(dim, attr)


def measure_total(dim: CoverageDimension, measure: str) -> float:
    """The summed coverage of ``dim`` in ``measure`` (an assertion count)."""
    return sum(measure_by_label(dim, measure).values())


def covered_labels(dim: CoverageDimension, measure: str) -> set[str]:
    """Assertions with ANY coverage in ``measure``.

    Read from the fractions rather than the dict keys: conduction seeds a 0.0
    entry for every *Assertion* label, so a set built from the keys would count
    an uncovered *Assertion* as covered (REQ-d00258-I).
    """
    return {lbl for lbl, frac in measure_by_label(dim, measure).items() if frac > 0}


# Implements: REQ-d00069-L, REQ-d00069-N, REQ-d00258-A, REQ-d00258-J
def dimension_measures(dim: CoverageDimension) -> dict[str, float]:
    """The four measures of one dimension, as assertion counts.

    What a citation named (direct / indirect) crossed with where the evidence
    sits (immediate / conducted up a `Refines:` chain). Each is reported in its
    own right; none is derived from another (REQ-d00069-L).
    """
    return {m: measure_total(dim, m) for m in MEASURES}


def assertion_measures(dim: CoverageDimension, label: str) -> dict[str, float]:
    """The four measures for ONE *Assertion* of a dimension, as fractions."""
    return {m: measure_by_label(dim, m).get(label, 0.0) for m in MEASURES}


def measure_phrase(values: dict[str, float], *, as_percent: bool = False) -> str:
    """Render the four measures under their one shared vocabulary.

    Built from ``MEASURE_WORDS``, so no surface composes a second wording for
    the measures another surface already names (REQ-d00258-C).
    """
    from elspais.graph.metrics import fmt_assertion_count

    def _fmt(v: float) -> str:
        return f"{round(100 * v)}%" if as_percent else fmt_assertion_count(v)

    return ", ".join(f"{MEASURE_WORDS[m]}: {_fmt(values[m])}" for m in MEASURES)


_COVERED_EPS = 1e-9


def is_covered(fraction: float) -> bool:
    """Whether a per-*Assertion* fraction counts as covered.

    An *Assertion* is covered only at (approximately) its whole value; a
    partially covered one is still work (REQ-d00258-M).
    """
    return fraction >= 1.0 - _COVERED_EPS


# Implements: REQ-d00258-I
def relative_tier(
    num_dim: CoverageDimension,
    denom_labels: set[str],
    *,
    measure: str,
) -> tuple[str, bool]:
    """Tier of ``num_dim`` in ``measure``, over the denominator ``denom_labels``.

    Returns ``(tier, is_na)``. ``is_na`` is True when the denominator is empty
    (nothing to measure -> ``missing`` at neutral severity). A failing label
    within the denominator wins (``failing``).

    ``measure`` names which per-*Assertion* map is scored, and the caller is
    required to say: the denominator was built from one measure, and scoring a
    different one here would report a figure over a denominator made of another
    kind of evidence (REQ-d00258-I).

    Single home for the relative-tier logic (REQ-d00258-C): both the badge
    projection (html/generator.py) and the requirement-level tier buckets read
    this one helper so identical questions receive identical answers.
    """
    eps = _COVERED_EPS
    if not denom_labels:
        return "missing", True
    if num_dim.failing_labels & denom_labels:
        return "failing", False
    pct = measure_by_label(num_dim, measure)
    covered = sum(min(pct.get(lbl, 0.0), 1.0) for lbl in denom_labels)
    n = len(denom_labels)
    if covered >= n - eps:
        return "full", False
    if covered > eps:
        return "partial", False
    return "missing", False


def absolute_tier(dim: CoverageDimension, *, measure: str) -> str:
    """Tier of a dimension in ``measure``, measured over ALL its assertions.

    A failing dimension is ``failing`` whatever the measure says. Otherwise the
    measure's summed coverage is compared against the assertion count, so a
    dimension reads ``full`` only when the named measure accounts for every
    *Assertion*.
    """
    eps = _COVERED_EPS
    if dim.has_failures:
        return "failing"
    covered = sum(min(v, 1.0) for v in measure_by_label(dim, measure).values())
    if dim.total > 0 and covered >= dim.total - eps:
        return "full"
    if covered > eps:
        return "partial"
    return "missing"


# Implements: REQ-d00258-C, REQ-d00258-M
@dataclass(frozen=True)
class WorkVerdict:
    """What a dimension leaves to do at one requirement.

    ``attached`` answers a different question from ``uncovered`` and neither
    stands in for the other. ``attached`` is whether ANY evidence for this
    dimension sits at this requirement -- read on the immediate measures, so
    a citation that named only the requirement counts and coverage conducted
    from a refining requirement does not. ``uncovered`` is which assertions
    no citation named, read on the work-list measure (REQ-d00258-M), each
    with the fraction it did reach.

    A requirement with nothing attached and one with a blanket citation are
    different situations calling for different words, which is why a surface
    that reads only the first reports nothing about the second.

    The fraction is carried because the surfaces consume this differently and
    both readings are taken from the one computation: a worklist distinguishes
    an *Assertion* with no evidence at all from one partly covered, since
    those are different work, while a gate reduces the same verdict to a tier
    and never looks at the fraction. Recomputing either from the other is how
    the two come to disagree.
    """

    attached: bool
    uncovered: dict[str, float]

    @property
    def needs_work(self) -> bool:
        """Whether any *Assertion* still wants evidence naming it."""
        return bool(self.uncovered)


# Implements: REQ-d00258-C, REQ-d00258-M
def work_verdict(
    rollup: RollupMetrics | None,
    dimension: str,
    labels: Iterable[str],
    *,
    restrict_to_dimension: str | None = None,
) -> WorkVerdict:
    """The one verdict every work-listing surface reaches.

    ``gaps``, the health coverage checks and the MCP work-list tools all ask
    the same question of the same data, so they ask it HERE. Deriving it at
    each call site is how two surfaces bound by one assertion came to
    disagree -- one listing a requirement's uncovered assertions while the
    other passed it green.

    ``labels`` are the requirement's *Assertion* labels; an *Assertion* with
    no entry in the fraction map is uncovered, not absent, so the caller has
    to say which exist. ``restrict_to_dimension`` applies the relative
    denominator of REQ-d00258-I, read on the same measure as the numerator.
    """
    if rollup is None:
        return WorkVerdict(attached=False, uncovered=dict.fromkeys(labels, 0.0))

    dim = getattr(rollup, dimension, None)
    if dim is None:
        return WorkVerdict(attached=False, uncovered=dict.fromkeys(labels, 0.0))

    candidates = set(labels)
    if restrict_to_dimension is not None:
        prior = getattr(rollup, restrict_to_dimension, None)
        candidates &= covered_labels(prior, WORK_LIST_MEASURE) if prior is not None else set()

    fractions = measure_by_label(dim, WORK_LIST_MEASURE)
    return WorkVerdict(
        attached=bool(covered_labels(dim, "immediate")),
        uncovered={
            lbl: fractions.get(lbl, 0.0)
            for lbl in candidates
            if not is_covered(fractions.get(lbl, 0.0))
        },
    )


def denominator_labels(rollup: RollupMetrics, dimension: str, *, measure: str) -> set[str] | None:
    """The label set a chained dimension is measured over; None if absolute.

    The denominator is the set of labels ACTUALLY covered in the prior
    dimension (fraction > 0) IN ``measure``, NOT every label present in the
    per-label map: conduction seeds a 0.0 entry for every assertion label
    (incl. unimplemented ones), so building the set from the dict keys would
    silently make this "relative" chain absolute and disagree with the
    gaps/MCP surfaces (which filter frac > 0).

    The caller names the measure because the chain is measured WITHIN one
    measure (REQ-d00258-I): Tested read on the immediate direct measure is the
    coverage of the assertions immediately-directly implemented, so that a
    figure and its denominator are made of the same kind of evidence.

    ONE definition, so the tier that reports a dimension and the check that
    reports evidence falling outside it cannot disagree about what the
    dimension counts (REQ-d00274-B).
    """
    denom_name = DENOMINATOR_DIMENSION.get(dimension)
    if denom_name is None:
        return None
    return covered_labels(getattr(rollup, denom_name), measure)


def numerator_dimension(rollup: RollupMetrics, dimension: str) -> CoverageDimension:
    """The dimension whose coverage is measured for ``dimension``.

    'verified' measures ``tested_and_passing`` (verified | lcov credit), matching
    the badge projection -- NOT the raw ``rollup.verified`` dimension, which would
    miss line-coverage credit.
    """
    return tested_and_passing(rollup) if dimension == "verified" else getattr(rollup, dimension)


# Implements: REQ-d00274-A, REQ-d00274-D
def authored_dimension(rollup: RollupMetrics, dimension: str) -> CoverageDimension:
    """The dimension holding evidence somebody WROTE for ``dimension``.

    Differs from ``numerator_dimension`` only for 'verified', whose figures union
    in line-coverage credit. That credit is derived from which lines a test run
    happened to touch: nobody wrote it against an *Assertion*, so it names none
    (REQ-d00274-A) and there is no file and line to report it at
    (REQ-d00274-D). It belongs in the figures, and not in a report about what
    an author annotated.
    """
    return getattr(rollup, dimension)


def relative_tier_for(
    rollup: RollupMetrics,
    dimension: str,
    *,
    measure: str,
) -> tuple[str, bool]:
    """``(tier, is_na)`` for one dimension of a rollup, honoring the chain.

    For a chained dimension (in ``DENOMINATOR_DIMENSION``) the tier is measured
    RELATIVELY over the label-set that qualified at the prior link, and the
    SAME ``measure`` is used on both sides of that ratio so the figure and its
    denominator are made of the same kind of evidence (REQ-d00258-I). The
    'verified' numerator is ``tested_and_passing``, matching the badge
    projection. An absolute dimension (implemented, uat_coverage) is measured
    over all its assertions and is never N/A.
    """
    denom_labels = denominator_labels(rollup, dimension, measure=measure)
    if denom_labels is None:
        return absolute_tier(getattr(rollup, dimension), measure=measure), False
    num_dim = numerator_dimension(rollup, dimension)
    return relative_tier(num_dim, denom_labels, measure=measure)


# Implements: REQ-d00274-A, REQ-d00274-D
# Which coverage contributions are the EVIDENCE for a chained dimension, so a
# finding can name the file and line the author wrote rather than only the
# assertion nothing counted. 'verified' is carried by the same test nodes as
# 'tested'; line-coverage credit contributes no node at all, which is why a
# finding may resolve no source and must still be reported.
# The evidence kinds whose source node can be named for each dimension.
#
# 'verified' is deliberately absent, and its chain link is unreachable in
# practice rather than merely unexercised: a RESULT contributes a verdict and
# nothing else, taking its labels from the declaration that produced it -- the
# same list that credits `tested`. One edge, two consumers, so a result cannot
# name an *Assertion* its declaration did not. Measured over this estate
# (2026-08-17): of 136 requirements carrying Passing evidence that names
# individual assertions, zero name a label outside the Tested denominator.
#
# The general loop is kept anyway. An exclusion here costs one iteration to
# skip and stops being correct the moment the two populations diverge; it has
# been written twice before, on two different and both wrong justifications.
_EVIDENCE_SOURCES: dict[str, frozenset[CoverageSource]] = {
    "tested": frozenset({CoverageSource.TEST_DIRECT, CoverageSource.TEST_INDIRECT}),
    "uat_verified": frozenset({CoverageSource.UAT_EXPLICIT, CoverageSource.UAT_INFERRED}),
}


# Implements: REQ-d00274-A
def named_labels(dim: CoverageDimension) -> set[str]:
    """Assertions this dimension's evidence NAMES, as opposed to reaches.

    Assertion-targeted evidence names an *Assertion*. Whole-requirement
    (blanket) evidence names the requirement, and the indirect measures extend
    its credit to every *Assertion* -- so those measures answer "which
    assertions does the credit reach", which is a different question from
    "which assertions did somebody write down".

    REQ-d00274-A is about the second question. Reading the first would report an
    *Assertion* nobody named as though evidence had been aimed at it, and would
    do so on every estate that annotates by requirement -- an author sent looking
    for an annotation that was never written. Blanket evidence is not thereby
    lost: it names the requirement, and REQ-d00274-F reports it there.

    Read from the immediate direct measure (REQ-d00069-L): a value conducted
    up a `Refines:` chain was written against the refining requirement, not
    against this *Assertion*, so counting it here would report an annotation
    nobody wrote, at a place nobody wrote it.
    """
    return covered_labels(dim, "immediate_direct")


@dataclass(frozen=True)
class UncreditedEvidence:
    """Evidence naming an *Assertion* its dimension does not count.

    ``assertion_label`` is None when the dimension counts no *Assertion* of the
    requirement at all: that is one fact about the requirement, reported once,
    not once per *Assertion* the evidence happens to name (REQ-d00274-F).

    ``result`` distinguishes evidence that only names the *Assertion* from
    evidence that also carries a verdict for it (REQ-d00274-D) -- a test aimed
    somewhere nothing is implemented, a passing test aimed there, and a failing
    one are three different things to be told.

    ``result_source_id`` is the source that returned that verdict, so the
    finding is reported at the file and line of the test it describes rather
    than at whichever source happened to be listed first.
    """

    requirement_id: str
    dimension: str
    denominator: str
    assertion_label: str | None
    labels: tuple[str, ...]
    result: EvidenceResult
    result_source_id: str | None
    source_ids: tuple[str, ...]


def _evidence_sources_for(
    rollup: RollupMetrics, dimension: str, labels: set[str]
) -> tuple[str, ...]:
    """Node ids of the evidence crediting ``labels`` in ``dimension``."""
    wanted = _EVIDENCE_SOURCES.get(dimension, frozenset())
    found: list[str] = []
    for label in sorted(labels):
        for contrib in rollup.assertion_coverage.get(label, ()):
            if contrib.source_type in wanted and contrib.source_id not in found:
                found.append(contrib.source_id)
    return tuple(found)


_PASSING_STATUSES = frozenset({"passed", "pass", "success"})
_FAILING_STATUSES = frozenset({"failed", "fail", "failure", "error"})


class EvidenceResult(str, Enum):
    """The verdict a piece of evidence carries for the *Assertion* it names.

    Three states, because a missing verdict and a failure are different facts:
    a test that returned no verdict says nothing about the *Assertion* it
    names, while a test that ran and failed against an *Assertion* nothing
    implements is the sharpest form of the defect this check exists to report
    (REQ-d00274-D). The verdict shapes what the finding says; whether the
    finding is raised at all, and at what severity, does not depend on it.
    """

    NONE = "none"
    PASSED = "passed"
    FAILED = "failed"


# Implements: REQ-d00274-D
def _evidence_result(graph: Any, source_ids: tuple[str, ...]) -> tuple[EvidenceResult, str | None]:
    """The verdict THIS evidence carries, and which source returned it.

    The second element is the source the verdict came from, so a finding can
    be reported at the file and line of the evidence it describes. Where the
    sources disagree, the one named in the wording and the one pointed at are
    the same test: sending a reader to a passing test under the words "a
    failing test" would be a true sentence over a false location (REQ-p00019-J).

    Read from the evidence node's own RESULT children, never from the
    requirement's aggregate: a dimension can credit a label because a sibling
    test passed, and saying "a passing test names this" of a test that failed
    would put the finding under a description untrue of it (REQ-p00019-J).

    A failure among the sources decides the answer, matching how a failing
    result is read everywhere else. NONE is the absence of a verdict, which a
    test reaches two ways: no RESULT of its own -- declared and not run, or run
    and not ingested -- and a RESULT whose status is neither a pass nor a fail,
    such as a skipped one. Neither is reported as a failure it never returned.
    Separating those two is the business of the Passing/Failing/No-result
    partition, not of a report about evidence crediting nothing.
    """
    passed_at: str | None = None
    for source_id in source_ids:
        node = graph.find_by_id(source_id)
        if node is None:
            continue
        for child in node.iter_children():
            if child.kind != NodeKind.RESULT:
                continue
            status = (child.get_field("status", "") or "").lower()
            if status in _FAILING_STATUSES:
                return EvidenceResult.FAILED, source_id
            if status in _PASSING_STATUSES and passed_at is None:
                passed_at = source_id
    if passed_at is not None:
        return EvidenceResult.PASSED, passed_at
    return EvidenceResult.NONE, None


# Implements: REQ-d00274-A, REQ-d00274-B, REQ-d00274-E, REQ-d00274-F
def iter_uncredited_evidence(
    graph: Any, config: dict[str, Any] | None = None
) -> list[UncreditedEvidence]:
    """Evidence that reaches no coverage answer, across the chained dimensions.

    A chained dimension counts only the assertions its denominator dimension
    covers, so evidence can name an *Assertion* outside that set and contribute
    to nothing. The denominator is read through the same helper the tier uses, so
    what is reported is exactly what the project's own figures leave out, on
    the measure they are computed on (REQ-d00274-B). The numerator is what the
    evidence NAMES (REQ-d00274-A), which is not a question of measure: an
    *Assertion* reached only because blanket evidence was extended to it was
    named by nobody, and is reported through its requirement under
    REQ-d00274-F if the dimension counts nothing of that requirement at all.

    Read-only: nothing here alters a metric, so reporting credits nothing
    (REQ-d00274-E).
    """
    out: list[UncreditedEvidence] = []
    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if not _counts_for_coverage(config, node.status):
            continue
        rollup: RollupMetrics | None = node.get_metric("rollup_metrics")
        if rollup is None or rollup.total_assertions == 0:
            continue
        # The measure the chained tier figures (tier_buckets, relative_tier,
        # the viewer badges) are actually computed on (REQ-d00274-B): this
        # report must leave out exactly what those figures leave out, so it
        # reads the same headline measure they do rather than a measure of
        # its own.
        chain_measure = HEADLINE_MEASURE
        for dimension, denom_name in DENOMINATOR_DIMENSION.items():
            denom = denominator_labels(rollup, dimension, measure=chain_measure)
            if denom is None:  # pragma: no cover - chained dimensions only
                continue
            num_dim = authored_dimension(rollup, dimension)
            if not denom:
                # The dimension counts no assertion of this requirement at all,
                # so every piece of its evidence credits nothing -- one finding
                # for the requirement, not one per assertion (REQ-d00274-F).
                # Blanket evidence is caught here and only here: it named the
                # requirement, which is what this finding is about.
                reached = covered_labels(num_dim, chain_measure)
                if not reached:
                    continue
                sources = _evidence_sources_for(rollup, dimension, reached)
                verdict, verdict_source = _evidence_result(graph, sources)
                out.append(
                    UncreditedEvidence(
                        requirement_id=node.id,
                        dimension=dimension,
                        denominator=denom_name,
                        assertion_label=None,
                        labels=tuple(sorted(reached)),
                        result=verdict,
                        result_source_id=verdict_source,
                        source_ids=sources,
                    )
                )
                continue
            uncredited = named_labels(num_dim) - denom
            for label in sorted(uncredited):
                label_sources = _evidence_sources_for(rollup, dimension, {label})
                verdict, verdict_source = _evidence_result(graph, label_sources)
                out.append(
                    UncreditedEvidence(
                        requirement_id=node.id,
                        dimension=dimension,
                        denominator=denom_name,
                        assertion_label=label,
                        labels=(label,),
                        result=verdict,
                        result_source_id=verdict_source,
                        source_ids=label_sources,
                    )
                )
    return out


@dataclass
class DimensionSums:
    """One dimension's assertion-fraction sums for a level.

    The four measures of REQ-d00069-L and the per-*Assertion* total of
    REQ-d00069-N, each summed in its own right, so a surface can report a
    figure and show the evidence behind it (REQ-d00258-A).
    """

    total: int = 0
    immediate_direct: float = 0.0
    immediate_indirect: float = 0.0
    rolled_direct: float = 0.0
    rolled_indirect: float = 0.0
    total_covered: float = 0.0


@dataclass
class LevelAggregate:
    level: str
    total_requirements: int = 0
    with_code_refs: int = 0
    with_test_refs: int = 0
    with_passing: int = 0
    total_assertions: int = 0
    implemented: DimensionSums = field(default_factory=DimensionSums)
    tested: DimensionSums = field(default_factory=DimensionSums)
    passing: DimensionSums = field(default_factory=DimensionSums)
    uat_covered: DimensionSums = field(default_factory=DimensionSums)
    uat_passed: DimensionSums = field(default_factory=DimensionSums)
    # The Tested breakdown (REQ-d00258-O): every tested assertion in this
    # level is in exactly one of the three, so they sum to the tested count.
    tested_passed: int = 0
    tested_failed: int = 0
    tested_awaiting: int = 0


@dataclass
class TierBuckets:
    total: int = 0
    full: int = 0
    partial: int = 0
    missing: int = 0
    failing: int = 0


@dataclass
class DimensionAggregate:
    """Whole-graph per-dimension sums plus the per-REQ counts health reports.

    ``total`` and the measure sums are the same assertion-fraction sums as
    ``DimensionSums``; the ``req_*`` fields and ``has_failures`` are the
    additional per-requirement tallies health.py's dimension-coverage check
    needs for its message.
    """

    total: int = 0
    # Implements: REQ-d00069-L, REQ-d00069-N
    # The four measures and the per-*Assertion* total, each summed in its own
    # right.
    immediate_direct: float = 0.0
    immediate_indirect: float = 0.0
    rolled_direct: float = 0.0
    rolled_indirect: float = 0.0
    total_covered: float = 0.0
    req_count: int = 0
    req_with_any: int = 0
    req_with_direct: int = 0
    has_failures: bool = False
    # The Tested breakdown (REQ-d00258-O). Populated only for the 'tested'
    # dimension: it breaks Tested down, and means nothing beside another.
    tested_passed: int = 0
    tested_failed: int = 0
    tested_awaiting: int = 0


def _level_keys(config: dict[str, Any] | None) -> list[str]:
    """Ordered [levels] keys: ranked keys first (by rank), rank-less keys after.

    A key missing ``rank`` still aggregates -- it is not excluded -- it just
    sorts after every ranked key, in stable (declaration) order among peers.
    """
    from elspais.config import default_level_keys

    levels_cfg = (config or {}).get("levels") or {}
    if isinstance(levels_cfg, dict) and levels_cfg:
        ordered = sorted(
            (
                (k, (v or {}).get("rank") if isinstance(v, dict) else None)
                for k, v in levels_cfg.items()
            ),
            key=lambda kv: kv[1] if kv[1] is not None else 9999,
        )
        keys = [k for k, _rank in ordered]
        if keys:
            return keys
    return default_level_keys()


def _accumulate(sums: DimensionSums, dim: CoverageDimension) -> None:
    sums.total += dim.total
    # Implements: REQ-d00069-L, REQ-d00069-N
    sums.immediate_direct += measure_total(dim, "immediate_direct")
    sums.immediate_indirect += measure_total(dim, "immediate_indirect")
    sums.rolled_direct += measure_total(dim, "rolled_direct")
    sums.rolled_indirect += measure_total(dim, "rolled_indirect")
    sums.total_covered += dim.covered


def _counts_for_coverage(config: dict[str, Any] | None, status: str | None) -> bool:
    """Whether a requirement STATUS is INCLUDED in coverage aggregation.

    The single coverage-inclusion gate (REQ-d00258-C): delegates to the
    ``status_expects_implementation`` resolver so summary/health/mcp and the
    viewer answer 'does this status count?' identically. For DEFAULT config
    (no ``[statuses.<Name>]`` override) this is EXACTLY
    ``status not in coverage_excluded_statuses()`` -- the role system remains
    the default source; an explicit ``expects_implementation`` flag diverges
    surgically. Deferred import mirrors the other config helpers here to avoid
    an import cycle.
    """
    from elspais.config import status_expects_implementation

    return status_expects_implementation(config or {}, status)


def aggregate_by_level(graph: Any, config: dict[str, Any] | None = None) -> list[LevelAggregate]:
    """Per-level assertion-fraction sums, on each of the four measures."""
    keys = _level_keys(config)
    groups: dict[str, LevelAggregate] = {k.lower(): LevelAggregate(level=k.upper()) for k in keys}

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        agg = groups.get((node.level or "").lower())
        if agg is None or not _counts_for_coverage(config, node.status):
            continue
        agg.total_requirements += 1
        rollup: RollupMetrics | None = node.get_metric("rollup_metrics")
        if rollup is None:
            if has_integration(node):
                agg.with_code_refs += 1
            continue
        passing_dim = tested_and_passing(rollup)
        agg.total_assertions += rollup.total_assertions
        _accumulate(agg.implemented, rollup.implemented)
        _accumulate(agg.tested, rollup.tested)
        _accumulate(agg.passing, passing_dim)
        _accumulate(agg.uat_covered, rollup.uat_coverage)
        _accumulate(agg.uat_passed, rollup.uat_verified)
        # REQ-d00252-F: INTEGRATES delegation counts as implemented.
        # Implements: REQ-d00258-A
        # "has any coverage at all" is asked of the per-*Assertion* total
        # (REQ-d00069-N) -- the greatest of the four measures -- so a
        # requirement counts here exactly when some measure credits it.
        if rollup.implemented.covered > 0 or has_integration(node):
            agg.with_code_refs += 1
        if rollup.tested.covered > 0:
            agg.with_test_refs += 1
        if passing_dim.covered > 0:
            agg.with_passing += 1
        # Implements: REQ-d00258-O
        part = tested_partition(rollup)
        agg.tested_passed += part.passed
        agg.tested_failed += part.failed
        agg.tested_awaiting += part.awaiting

    return [groups[k.lower()] for k in keys]


def aggregate_dimension(
    graph: Any,
    dimension: str,
    config: dict[str, Any] | None = None,
    level_filter: Any = None,
) -> DimensionAggregate:
    """Whole-graph sums + per-REQ counts for one CoverageDimension.

    Mirrors the per-level accumulation in ``aggregate_by_level`` but flattened
    across all levels (no level grouping) and generalized to any dimension
    name on ``RollupMetrics`` (e.g. 'implemented', 'tested', 'verified',
    'uat_coverage', 'uat_verified'). This is the single place health.py's
    dimension-coverage check should read counts from -- it must not
    re-implement this walk (REQ-d00258-C).

    Coverage inclusion is gated by ``status_expects_implementation`` via
    ``_counts_for_coverage(config, ...)`` -- the same resolver the viewer,
    summary, and tier buckets use (REQ-d00258-C). Behavior-preserving for
    default config; an explicit ``[statuses.<Name>].expects_implementation``
    flag diverges surgically.

    ``level_filter`` (optional) is a predicate ``(level: str | None) -> bool``.
    When given, only requirements whose level satisfies it are counted (both
    numerator and denominator). Used by the UAT coverage check so that
    non-``expects_validation`` levels neither count toward nor drag the gap
    (REQ-d00258-F).

    REQ-d00252-F: an INTEGRATES-delegating requirement has no local
    ``rollup_metrics`` but is still covered for the 'implemented' dimension
    specifically; other dimensions do not receive the INTEGRATES credit.
    """
    agg = DimensionAggregate()
    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if not _counts_for_coverage(config, node.status):
            continue
        if level_filter is not None and not level_filter(node.level):
            continue
        agg.req_count += 1
        integrates = dimension == "implemented" and has_integration(node)
        rollup: RollupMetrics | None = node.get_metric("rollup_metrics")
        if rollup is None:
            if integrates:
                agg.req_with_any += 1
                agg.req_with_direct += 1
            continue
        # Through the shared numerator, so 'verified' aggregates the Passing
        # dimension -- one kind of evidence saying it passed and neither saying
        # it failed (REQ-d00258-N) -- rather than the raw verified field, which
        # neither unions in line-coverage credit nor sees an lcov-side failure.
        # Every other dimension resolves to itself.
        if not hasattr(rollup, dimension):
            continue
        dim: CoverageDimension = numerator_dimension(rollup, dimension)
        agg.total += dim.total
        # Implements: REQ-d00069-L, REQ-d00069-N
        agg.immediate_direct += measure_total(dim, "immediate_direct")
        agg.immediate_indirect += measure_total(dim, "immediate_indirect")
        agg.rolled_direct += measure_total(dim, "rolled_direct")
        agg.rolled_indirect += measure_total(dim, "rolled_indirect")
        agg.total_covered += dim.covered
        # Implements: REQ-d00258-A, REQ-d00258-M
        # "covered on any measure" is the per-*Assertion* total; "cited by
        # name here" is the immediate direct measure, the one the work-list
        # surfaces answer on (REQ-d00258-M).
        if dim.covered > 0 or integrates:
            agg.req_with_any += 1
        if measure_total(dim, "immediate_direct") > 0 or integrates:
            agg.req_with_direct += 1
        if dim.has_failures:
            agg.has_failures = True
        # Implements: REQ-d00258-O
        if dimension == "tested":
            part = tested_partition(rollup)
            agg.tested_passed += part.passed
            agg.tested_failed += part.failed
            agg.tested_awaiting += part.awaiting
    return agg


# Implements: REQ-d00254-B, REQ-d00258-E
@dataclass
class LineAggregate:
    """Whole-graph line-coverage sums, plus the per-REQ counts health reports.

    Measured in LINES, kept apart from :class:`DimensionAggregate` because the
    two count different populations and must never be added together or
    compared as though they were the same figure.
    """

    total_lines: int = 0
    attributed_lines: float = 0.0
    covered_lines: float = 0.0
    req_count: int = 0
    req_with_covered: int = 0
    req_with_attribution: int = 0
    has_measurement: bool = False
    has_contexts: bool = False

    @property
    def has_attribution(self) -> bool:
        """Whether the ingested coverage can produce an attribution figure.

        Mirrors :attr:`LineCoverage.has_attribution` so the whole-graph answer
        and the per-requirement one are the same question (REQ-d00258-E): the
        suppression keys on whether the tooling recorded per-test contexts at
        all, not on whether the resulting count came out above zero.
        """
        return self.has_contexts


# Implements: REQ-d00254-B
def aggregate_line_coverage(
    graph: Any,
    config: dict[str, Any] | None = None,
    level_filter: Any = None,
) -> LineAggregate:
    """Whole-graph line-coverage sums over the requirements coverage includes.

    The same status-inclusion gate as :func:`aggregate_dimension`
    (REQ-d00258-C), so a requirement excluded from assertion coverage is
    excluded from line coverage too and the two reports describe one estate.
    """
    agg = LineAggregate()
    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if not _counts_for_coverage(config, node.status):
            continue
        if level_filter is not None and not level_filter(node.level):
            continue
        rollup: RollupMetrics | None = node.get_metric("rollup_metrics")
        if rollup is None:
            continue
        lines = rollup.code_tested
        if lines.total_lines == 0:
            continue
        agg.req_count += 1
        agg.total_lines += lines.total_lines
        agg.attributed_lines += lines.attributed_lines
        agg.covered_lines += lines.covered_lines
        if lines.covered_lines > 0:
            agg.req_with_covered += 1
        if lines.attributed_lines > 0:
            agg.req_with_attribution += 1
        # Implements: REQ-d00258-E
        # What the tooling provided is an OR across the estate: one target
        # measured, or one carrying contexts, means the question was asked.
        agg.has_measurement = agg.has_measurement or lines.has_measurement
        agg.has_contexts = agg.has_contexts or lines.has_contexts
    return agg


def tier_buckets(
    graph: Any,
    dimension: str = "implemented",
    config: dict[str, Any] | None = None,
) -> TierBuckets:
    """Requirement-level tier bucket counts for one dimension.

    Chained dimensions (tested/verified/uat_verified) bucket by their RELATIVE
    tier -- measured over the prior link's label set via ``relative_tier_for``
    (REQ-d00258-C) -- so a requirement whose every implemented assertion is
    tested lands in ``full`` even when some assertions are unimplemented. The
    absolute dimensions (implemented/uat_coverage) bucket by their own tier. A
    node with no rollup counts as ``missing``.

    Scored on the HEADLINE measure (REQ-d00258-A), which is what the viewer
    badge and the CLI summary report, so these counts answer the badge's
    question with the badge's answer (REQ-d00258-C). ``config`` still gates
    which requirements are counted at all.
    """
    # Implements: REQ-d00258-A, REQ-d00258-C
    # The headline measure: each *Assertion* counted once at the greatest of
    # its four (REQ-d00069-N). The same measure the viewer badge and the CLI
    # summary headline, so a requirement that badges FULL in one surface can
    # never be counted PARTIAL by another asking the same question.
    measure = HEADLINE_MEASURE
    buckets = TierBuckets()
    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if not _counts_for_coverage(config, node.status):
            continue
        buckets.total += 1
        rollup: RollupMetrics | None = node.get_metric("rollup_metrics")
        if rollup is None or getattr(rollup, dimension, None) is None:
            buckets.missing += 1
            continue
        tier, _is_na = relative_tier_for(rollup, dimension, measure=measure)
        bucket = TIER_TO_BUCKET.get(tier, "missing")
        setattr(buckets, bucket, getattr(buckets, bucket) + 1)
    return buckets


# Implements: REQ-d00069-L, REQ-d00069-N, REQ-d00258-A
def _measure_fields(prefix: str, sums: DimensionSums) -> dict[str, float]:
    """One dimension's four measures plus its total, keyed for a payload.

    Published beside the headline so a reader is never shown a figure without
    being able to see what evidence produced it (REQ-d00258-A).
    """
    return {
        f"{prefix}_immediate_direct": round(sums.immediate_direct, 3),
        f"{prefix}_immediate_indirect": round(sums.immediate_indirect, 3),
        f"{prefix}_rolled_direct": round(sums.rolled_direct, 3),
        f"{prefix}_rolled_indirect": round(sums.rolled_indirect, 3),
        f"{prefix}_total_covered": round(sums.total_covered, 3),
    }


# Implements: REQ-d00086-A, REQ-d00258-C
def collect_coverage(graph: Any, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Full coverage-summary payload shared by CLI summary and MCP.

    Per-level rows come from :func:`aggregate_by_level`; excluded-status
    counts, the per-associate Integrates rollup, and (for selective runs)
    carry-forward provenance are assembled here so every consumer renders
    from one payload. Level membership uses :func:`_level_keys` -- the SAME
    derivation ``aggregate_by_level`` uses (rank-less ``[levels]`` keys
    included), so ``excluded`` counts exactly the requirements that land in a
    rendered level bucket.
    """
    from elspais.config import get_status_roles

    roles = get_status_roles(config or {})
    exclude_status = roles.coverage_excluded_statuses()
    known_levels = {k.lower() for k in _level_keys(config)}

    # excluded counts are computed locally (aggregate_by_level excludes these
    # statuses from its sums but doesn't report per-status counts).
    excluded_counts: dict[str, int] = {}
    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if (node.level or "").lower() in known_levels and node.status in exclude_status:
            excluded_counts[node.status] = excluded_counts.get(node.status, 0) + 1

    levels = []
    for agg in aggregate_by_level(graph, config):
        levels.append(
            {
                "level": agg.level,
                "total": agg.total_requirements,
                "with_code_refs": agg.with_code_refs,
                "with_test_refs": agg.with_test_refs,
                "with_passing": agg.with_passing,
                "total_assertions": agg.total_assertions,
                "tested_passed": agg.tested_passed,
                "tested_failed": agg.tested_failed,
                "tested_awaiting": agg.tested_awaiting,
                **_measure_fields("implemented", agg.implemented),
                **_measure_fields("tested", agg.tested),
                **_measure_fields("passing", agg.passing),
                **_measure_fields("uat_covered", agg.uat_covered),
                **_measure_fields("uat_passed", agg.uat_passed),
            }
        )

    # REQ-d00252-F: per-associate Integrates rollup + federation total.
    integration_rows = integrates_by_associate(graph)
    integrations: list[dict[str, Any]] = [
        {
            "associate": row.associate,
            "requirement_count": row.requirement_count,
            "implemented_covered": row.implemented_covered,
            "implemented_total": row.implemented_total,
            "verified_covered": row.verified_covered,
            "verified_total": row.verified_total,
            "has_failures": row.has_failures,
        }
        for row in integration_rows
    ]
    integration_total: dict[str, Any] | None = None
    if integration_rows:
        tot = integrates_total(integration_rows)
        integration_total = {
            "associate": tot.associate,
            "requirement_count": tot.requirement_count,
            "implemented_covered": tot.implemented_covered,
            "implemented_total": tot.implemented_total,
            "verified_covered": tot.verified_covered,
            "verified_total": tot.verified_total,
            "has_failures": tot.has_failures,
        }

    result: dict[str, Any] = {
        "levels": levels,
        "excluded": excluded_counts,
        "integrations": integrations,
        "integration_total": integration_total,
    }

    # Implements: REQ-d00254-I
    # Carry-forward provenance (distinct RESULT target names + how many are
    # carried baselines) is meaningful only for a selective `--targets` run, so
    # a selective run isn't a silent no-op on rendered output. Omit it entirely
    # otherwise, so a full run stays byte-identical to the pre-selectivity
    # output in every format (JSON keys and the CSV row included).
    if getattr(graph, "render_fresh_targets", None) is not None:
        all_result_targets: set[str] = set()
        carried_result_targets_set: set[str] = set()
        for result_node in graph.iter_by_kind(NodeKind.RESULT):
            tgt = result_node.get_field("target")
            if not tgt:
                continue
            all_result_targets.add(tgt)
            if result_node.get_field("carried"):
                carried_result_targets_set.add(tgt)
        result["total_result_targets"] = len(all_result_targets)
        result["carried_result_targets"] = len(carried_result_targets_set)

    return result


__all__ = [
    "COVERAGE_DIMENSIONS",
    "DENOMINATOR_DIMENSION",
    "HEADLINE_MEASURE",
    "MEASURES",
    "MEASURE_WORDS",
    "TIER_TO_BUCKET",
    "WORK_LIST_MEASURE",
    "DimensionAggregate",
    "LineAggregate",
    "DimensionSums",
    "LevelAggregate",
    "TierBuckets",
    "UncreditedEvidence",
    "absolute_tier",
    "aggregate_by_level",
    "assertion_measures",
    "collect_coverage",
    "covered_labels",
    "is_covered",
    "measure_by_label",
    "measure_phrase",
    "measure_total",
    "aggregate_dimension",
    "aggregate_line_coverage",
    "authored_dimension",
    "denominator_labels",
    "dimension_measures",
    "iter_uncredited_evidence",
    "named_labels",
    "numerator_dimension",
    "relative_tier",
    "relative_tier_for",
    "tier_buckets",
]
