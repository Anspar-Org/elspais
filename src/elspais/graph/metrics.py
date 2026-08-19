# Implements: REQ-d00069-A, REQ-d00069-C
"""Coverage metrics data structures.

This module defines the data structures for centralized coverage tracking:
- CoverageSource: Enum indicating where coverage originated
- CoverageContribution: A single coverage claim on an assertion
- CoverageDimension: Uniform metrics for one coverage dimension
- RollupMetrics: Aggregated metrics for a requirement node

It also exposes lightweight inherited-coverage query helpers used by the
template / Satisfies pattern (CUR-1353 Phase 5):

- direct_coverage_for(node): count coverage evidence on a node, dispatched
  by NodeKind. For ASSERTIONs, walks the parent REQ's outgoing
  IMPLEMENTS/VERIFIES/VALIDATES edges filtered by ``assertion_targets``.
  For REQUIREMENTs, counts outgoing coverage edges directly. For CODE,
  TEST, FILE, and JOURNEY nodes, counts incoming coverage edges.
- inherited_coverage_for(node): for an INSTANCE node, return the template
  original's direct coverage; for any other node, fall back to direct.
- satisfier_rollup(node): combine a satisfier REQ's own concrete-assertion
  coverage with the inherited coverage from the templates it satisfies.

These helpers are queries over the live graph -- they do not persist any
new metric on the node, so the INSTANCE coverage story stays consistent
with the "instance coverage == template coverage" invariant.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from elspais.graph.GraphNode import GraphNode


class CoverageSource(Enum):
    """Source type for coverage contributions.

    Different sources have different confidence levels. Note the split between
    *implementation* evidence (CODE/REQ — feeds the ``implemented`` dimension in
    :meth:`RollupMetrics.finalize`) and *test* evidence (TEST via ``Verifies:``
    — feeds only the ``tested``/``verified`` dimensions, NEVER ``implemented``,
    per REQ-d00084-D). A test that verifies an assertion is not evidence that
    the assertion is implemented, so the two must not be conflated.

    - DIRECT: High confidence - CODE implements a specific assertion
    - EXPLICIT: High confidence - REQ implements specific assertion(s) via syntax
    - INFERRED: Review recommended - REQ implements parent REQ (claims all assertions)
    - INDIRECT: transitive CODE->TEST evidence (CODE implements, that CODE is
      verified by a TEST); provenance only — does not itself feed ``implemented``
    - CODE_INDIRECT: CODE Implements the whole REQ (blanket, no assertion
      suffix), all assertions implied; feeds the INDIRECT measures of
      ``implemented`` only, never its direct ones
    - TEST_DIRECT: TEST verifies a specific assertion (Verifies: REQ-xxx-A);
      feeds ``tested``, NOT ``implemented``
    - TEST_INDIRECT: TEST verifies whole REQ (Verifies: REQ-xxx), all assertions
      implied; feeds ``tested``, NOT ``implemented``
    - UAT_EXPLICIT: JNY names specific assertion (Validates: REQ-xxx-A)
    - UAT_INFERRED: JNY names whole REQ (Validates: REQ-xxx), all assertions implied
    """

    DIRECT = "direct"  # CODE implements assertion (implementation evidence)
    EXPLICIT = "explicit"  # REQ implements specific assertions (e.g., REQ-100-A-B)
    INFERRED = "inferred"  # REQ implements parent REQ (all assertions implied)
    INDIRECT = "indirect"  # transitive CODE->TEST evidence (provenance only)
    # CODE Implements whole REQ (blanket), all assertions implied; feeds
    # the `implemented` INDIRECT measures only (REQ-d00069-B)
    CODE_INDIRECT = "code_indirect"
    TEST_DIRECT = "test_direct"  # TEST verifies specific assertion (Verifies: REQ-xxx-A)
    TEST_INDIRECT = "test_indirect"  # TEST verifies whole REQ (Verifies: REQ-xxx)
    UAT_EXPLICIT = "uat_explicit"  # JNY names specific assertion (Validates: REQ-xxx-A)
    UAT_INFERRED = (
        "uat_inferred"  # JNY names whole REQ (Validates: REQ-xxx), all assertions implied
    )


@dataclass
class CoverageContribution:
    """A single coverage contribution to an assertion.

    Tracks which node claims to cover an assertion and how.

    Attributes:
        source_id: ID of the node providing coverage (TEST, CODE, or REQ)
        source_type: How the coverage was determined
        assertion_label: The assertion label being covered (e.g., "A", "B")
    """

    source_id: str
    source_type: CoverageSource
    assertion_label: str


@dataclass
class CoverageDimension:
    """Uniform coverage metrics for one dimension.

    Each of the 5 coverage dimensions (implemented, tested, verified,
    uat_covered, uat_verified) uses this same structure.

    Coverage is recorded on the four measures of REQ-d00069-L. Two independent
    axes: what a citation named (**direct**, this *Assertion* by name, versus
    **indirect**, the requirement as a whole) and where the evidence sits
    (**immediate**, attached here, versus **rolled**, conducted up a ``Refines:``
    chain). None is defined in terms of another. Per-assertion credit is
    **fractional** in [0.0, 1.0] -- an *Assertion* refined by several
    requirements of which only some are covered is partially covered
    (REQ-d00069-J) -- so a measure's sum may be non-integer.

    Attributes:
        total: Total assertions in the requirement
        has_failures: True if ANY result is failed/error for this dimension.
            This is **requirement-wide** -- it drives the requirement-level
            badge/``tier`` (any assertion failing => the requirement dimension
            reports a failure, REQ-d00258-G). Do NOT use it to decide a single
            assertion's standing; use ``failing_labels`` for that.
        failing_labels: The assertion labels that have an actual failing
            result/verification for THIS dimension. This is **per-assertion**
            -- it drives the per-*Assertion* standing so an assertion reads
            "failing" only when it itself failed, not because a sibling
            assertion (covered by a different, non-failing test/journey)
            failed. Invariant: ``has_failures`` is true iff ``failing_labels``
            is non-empty (for the verified/uat_verified dimensions that record
            failures). Only meaningful on ``verified``/``uat_verified``/
            ``lcov_tested`` (dims that carry pass/fail); other dims leave it
            empty.
        carried: True when every verified signal contributing to this
            dimension came from a "carried" (baseline, not freshly-run)
            RESULT node (CUR-1557). Provenance only -- never affects
            ``tier``, which is driven solely by ``has_failures``/coverage.
            Only meaningful on the ``verified`` dimension; other dimensions
            leave this at its default (``False``).
        immediate_direct_by_label: Per-assertion immediate-direct credit
            (whole where the evidence is whole, partial where the evidence
            itself is partial, REQ-d00069-M) -- a citation named this
            *Assertion* and the evidence is attached here.
        immediate_indirect_by_label: Per-assertion immediate-indirect credit
            (same strength rule as immediate_direct) -- a citation named
            only the requirement and the evidence is attached here.
        rolled_direct_by_label: Per-assertion rolled-up-direct credit (MAY
            be fractional, REQ-d00069-M) -- conducted from a refining
            requirement's own direct coverage.
        rolled_indirect_by_label: Per-assertion rolled-up-indirect credit
            (MAY be fractional) -- conducted from a refining requirement's
            own indirect coverage.
    """

    total: int = 0
    has_failures: bool = False
    failing_labels: set[str] = field(default_factory=set)
    carried: bool = False

    # Implements: REQ-d00069-L
    # The four measures, on two independent axes: what a citation NAMED
    # (direct = this *Assertion*, indirect = the requirement as a whole) x
    # WHERE the evidence sits (immediate = attached here, rolled = conducted
    # up a `Refines:` chain). Each is measured from the evidence itself; none
    # is derived from a sibling. Values are per-*Assertion* fractions in
    # [0.0, 1.0], so a measure's sum may be non-integer (REQ-d00069-M).

    # name: immediate_direct_by_label
    # use:  every work list -- "which assertions has nobody written evidence
    #       for" (``WORK_LIST_MEASURE``, REQ-d00258-M). The strictest measure,
    #       and the one a gap surface answers on.
    # def:  a citation named THIS *Assertion*, and the evidence is attached to
    #       this requirement.
    immediate_direct_by_label: dict[str, float] = field(default_factory=dict)

    # name: immediate_indirect_by_label
    # use:  showing how much green rests on whole-requirement citation --
    #       published beside the total so a reader can see it, never used to
    #       decide a work list.
    # def:  a citation named only the REQUIREMENT, so it is attributed equally
    #       to every *Assertion* of it; evidence attached to this requirement.
    immediate_indirect_by_label: dict[str, float] = field(default_factory=dict)

    # name: rolled_direct_by_label
    # use:  answering "is the detail below this finished" without claiming
    #       anyone wrote evidence here.
    # def:  conducted up a `Refines:` chain from a refining requirement's own
    #       DIRECT coverage -- the mean, in that measure, of the contributing
    #       requirements' coverage (REQ-d00069-J).
    rolled_direct_by_label: dict[str, float] = field(default_factory=dict)

    # name: rolled_indirect_by_label
    # use:  as rolled_direct, for refining requirements whose own evidence was
    #       itself whole-requirement.
    # def:  conducted the same way, from a refining requirement's INDIRECT
    #       coverage. Direct conducts into direct and indirect into indirect,
    #       so no measure is ever composed of another.
    rolled_indirect_by_label: dict[str, float] = field(default_factory=dict)

    @property
    def immediate_direct(self) -> float:
        return sum(self.immediate_direct_by_label.values())

    @property
    def immediate_indirect(self) -> float:
        return sum(self.immediate_indirect_by_label.values())

    @property
    def rolled_direct(self) -> float:
        return sum(self.rolled_direct_by_label.values())

    @property
    def rolled_indirect(self) -> float:
        return sum(self.rolled_indirect_by_label.values())

    # Implements: REQ-d00069-N
    @property
    def total_by_label(self) -> dict[str, float]:
        """Per *Assertion*, the greatest of its four measures.

        Taken per *Assertion* rather than summed across measures: an
        *Assertion* covered three ways is one covered *Assertion*, so this
        can never exceed the requirement's assertion count.
        """
        out: dict[str, float] = {}
        for src in (
            self.immediate_direct_by_label,
            self.immediate_indirect_by_label,
            self.rolled_direct_by_label,
            self.rolled_indirect_by_label,
        ):
            for label, frac in src.items():
                if frac > out.get(label, 0.0):
                    out[label] = frac
        return out

    # Implements: REQ-d00069-N
    # name: covered
    # use:  the headline figure of every REPORTING surface (REQ-d00258-A) --
    #       "how far along is this". Never a work list: it credits evidence no
    #       citation attached to the *Assertion*.
    # def:  the per-*Assertion* total summed. A derived VIEW over the four
    #       measures, not a fifth measure. Real-valued, and it can never
    #       exceed ``total``.
    @property
    def covered(self) -> float:
        return sum(self.total_by_label.values())

    # Implements: REQ-d00258-A
    @property
    def covered_pct(self) -> float:
        """The headline percentage: covered assertions over all of them."""
        return (self.covered / self.total * 100) if self.total else 0.0


# Implements: REQ-d00254-B
@dataclass
class LineCoverage:
    """Line-coverage measurement for one requirement's implementation.

    A DELIBERATELY separate type from :class:`CoverageDimension`. Line coverage
    counts LINES of implementation a test run executed; assertion coverage
    counts *Assertions* somebody wrote evidence for. They are different
    measurements over different populations, so the four measures of
    REQ-d00069-L -- which are per-*Assertion* -- cannot express this one, and a
    type that pretended otherwise would invite a reader to compare a line count
    with an assertion count.

    Attributes:
        total_lines: Implementation lines attributed to the requirement.
        attributed_lines: Lines a coverage run executed AND whose recorded
            context names a test that verifies this requirement. Requires
            per-test context data; aggregate-only coverage cannot produce it
            and leaves this at 0 (REQ-d00258-E).
        covered_lines: Lines any coverage run executed, whichever test did it.
        has_measurement: Whether a coverage run measured these lines at all.
            Recorded at ingestion, because a zero ``covered_lines`` otherwise
            says two opposite things -- that no run reached this code, and that
            no run was ever ingested.
        has_contexts: Whether the ingested coverage carried per-test contexts.
            Aggregate-only tooling records none, and without them no
            attribution figure can be computed for any requirement
            (REQ-d00258-E).
    """

    total_lines: int = 0
    attributed_lines: float = 0.0
    covered_lines: float = 0.0
    has_measurement: bool = False
    has_contexts: bool = False

    @property
    def has_attribution(self) -> bool:
        """Whether the coverage data can produce an attribution figure at all.

        REQ-d00258-E keys the suppression on what the TOOLING provided: where
        coverage arrives without per-test contexts there is nothing to
        attribute a line to a test with, and a figure would be an answer to a
        question never asked. Where contexts are present the figure is real
        even at zero -- it says no verifying test executed these lines, which
        is a fact worth reporting rather than suppressing.
        """
        return self.has_contexts


def fmt_assertion_count(value: float) -> str:
    """Format a (possibly fractional) covered-assertion count for display.

    Coverage counts are sums of per-assertion fractions (REQ-d00069-J), so they
    can be non-integer when assertions are partially covered through refinement.
    Render whole numbers without a decimal point and fractional ones with a
    single decimal place, e.g. ``2`` or ``1.5``.
    """
    rounded = round(value)
    if abs(value - rounded) < 1e-9:
        return str(int(rounded))
    return f"{value:.1f}"


@dataclass
class RollupMetrics:
    """Aggregated coverage metrics for a requirement.

    Computed once during graph annotation and stored in node._metrics.
    Provides both aggregate counts and per-assertion detail.

    The 7 CoverageDimension instances provide uniform access:
    - implemented: CODE/REQ coverage of assertions
    - tested: TEST nodes exist for assertions
    - verified: TEST results passing for assertions
    - uat_coverage: JNY Validates coverage of assertions
    - uat_verified: JNY results passing for assertions
    - lcov_tested: Coverage-based "tested" credit, kept SEPARATE from verified (CUR-1533)

    Beside them ``code_tested`` is a :class:`LineCoverage` -- a measurement in
    LINES, not assertions, and so not a coverage dimension at all.
    """

    total_assertions: int = 0
    assertion_coverage: dict[str, list[CoverageContribution]] = field(default_factory=dict)

    # The 6 uniform (per-assertion) coverage dimensions
    implemented: CoverageDimension = field(default_factory=CoverageDimension)
    tested: CoverageDimension = field(default_factory=CoverageDimension)
    verified: CoverageDimension = field(default_factory=CoverageDimension)
    uat_coverage: CoverageDimension = field(default_factory=CoverageDimension)
    uat_verified: CoverageDimension = field(default_factory=CoverageDimension)
    # CUR-1533: coverage-based "tested & passing" credit, kept SEPARATE from
    # `verified` (which is // Verifies:-based). Assertion-granular.
    lcov_tested: CoverageDimension = field(default_factory=CoverageDimension)

    # Line coverage: measured in LINES, so it is not a CoverageDimension.
    code_tested: LineCoverage = field(default_factory=LineCoverage)

    def add_contribution(self, contribution: CoverageContribution) -> None:
        """Add a coverage contribution for an assertion.

        Args:
            contribution: The coverage contribution to add.
        """
        label = contribution.assertion_label
        if label not in self.assertion_coverage:
            self.assertion_coverage[label] = []
        self.assertion_coverage[label].append(contribution)

    def finalize(self) -> None:
        """Compute aggregate counts after all contributions are added.

        Call this after adding all contributions to populate the implemented
        and uat_coverage dimensions from contribution data. The tested,
        verified, and uat_verified dimensions are populated separately by
        populate_test_dimensions() (called from annotate_coverage()).
        """
        if self.total_assertions == 0:
            return

        n = self.total_assertions

        # Track unique assertions by coverage source type. Only
        # implementation-evidence sources (DIRECT/EXPLICIT/INFERRED) are
        # collected here; they build the `implemented` dimension below.
        direct_labels: set[str] = set()
        explicit_labels: set[str] = set()
        inferred_labels: set[str] = set()
        code_indirect_labels: set[str] = set()
        uat_explicit_labels: set[str] = set()
        uat_inferred_labels: set[str] = set()

        for label, contributions in self.assertion_coverage.items():
            for contrib in contributions:
                # NOTE (REQ-d00084-D): the following sources are deliberately
                # NOT bucketed into `implemented`, and fall through:
                #   - TEST_DIRECT / TEST_INDIRECT: a test `Verifies:` an
                #     assertion -- test evidence, feeds `tested`/`verified`
                #     (via populate_test_dimensions), never `implemented`.
                #   - INDIRECT: the transitive CODE->TEST provenance edge. A
                #     tested CODE node's implemented credit already comes from
                #     its own DIRECT `Implements:` edge, and the verifying test
                #     is registered separately for result lookup (`verified`);
                #     this source adds no `implemented` credit of its own.
                if contrib.source_type == CoverageSource.DIRECT:
                    direct_labels.add(label)
                elif contrib.source_type == CoverageSource.EXPLICIT:
                    explicit_labels.add(label)
                elif contrib.source_type == CoverageSource.INFERRED:
                    inferred_labels.add(label)
                elif contrib.source_type == CoverageSource.CODE_INDIRECT:
                    code_indirect_labels.add(label)
                elif contrib.source_type == CoverageSource.UAT_EXPLICIT:
                    uat_explicit_labels.add(label)
                elif contrib.source_type == CoverageSource.UAT_INFERRED:
                    uat_inferred_labels.add(label)

        # ── Populate dimensions from contribution data ──
        # Implemented: direct == the citation named the *Assertion* (DIRECT +
        # EXPLICIT); indirect == it named the requirement (INFERRED +
        # CODE_INDIRECT). The two are DISJOINT -- an *Assertion* cited by name
        # is not also whole-requirement evidence (REQ-d00069-L).
        impl_direct = direct_labels | explicit_labels
        # Implements: REQ-d00069-B, REQ-d00069-M
        # Immediate credit here is whole -- Implemented evidence (DIRECT/
        # EXPLICIT/INFERRED sources) is all-or-nothing, unlike uat_verified
        # below, whose partially-verified journeys carry a genuine fraction.
        immediate_direct = dict.fromkeys(impl_direct, 1.0)
        immediate_indirect = dict.fromkeys(inferred_labels | code_indirect_labels, 1.0)
        self.implemented = CoverageDimension(
            total=n,
            immediate_direct_by_label=immediate_direct,
            immediate_indirect_by_label=immediate_indirect,
        )

        # UAT Coverage: direct == a journey named the *Assertion* (UAT_EXPLICIT),
        # indirect == it named only the requirement (UAT_INFERRED). Disjoint by
        # source, and neither defined in terms of the other (REQ-d00069-L).
        self.uat_coverage = CoverageDimension(
            total=n,
            immediate_direct_by_label=dict.fromkeys(uat_explicit_labels, 1.0),
            immediate_indirect_by_label=dict.fromkeys(uat_inferred_labels, 1.0),
        )

        # tested, verified, uat_verified are populated by annotate_coverage()
        # after this method runs, because they need label-set data from the
        # annotator (tested_labels, validated_labels, etc.)

    def populate_test_dimensions(
        self,
        *,
        tested_direct_labels: set[str],
        tested_indirect_labels: set[str],
        verified_direct_labels: set[str],
        verified_indirect_labels: set[str],
        verified_failures: bool,
        verified_carried: bool = False,
        uat_verified_direct_pct: dict[str, float],
        uat_verified_indirect_pct: dict[str, float],
        uat_verified_failures: bool,
        verified_failing_labels: set[str] | None = None,
        uat_verified_failing_labels: set[str] | None = None,
    ) -> None:
        """Populate tested, verified, and uat_verified dimensions.

        Called by annotate_coverage() after finalize() with the label sets
        from the annotator's tracking variables. ``uat_verified`` credit is
        FRACTIONAL per assertion (REQ-d00255-C): a partially-verified journey
        credits its verified-step ratio, so the annotator passes per-label
        fraction maps rather than plain label sets. tested/verified remain
        all-or-nothing (1.0) label sets.
        """
        n = self.total_assertions
        self.tested = CoverageDimension(
            total=n,
            immediate_direct_by_label=dict.fromkeys(tested_direct_labels, 1.0),
            immediate_indirect_by_label=dict.fromkeys(tested_indirect_labels, 1.0),
        )
        self.verified = CoverageDimension(
            total=n,
            has_failures=verified_failures,
            failing_labels=set(verified_failing_labels or ()),
            immediate_direct_by_label=dict.fromkeys(verified_direct_labels, 1.0),
            immediate_indirect_by_label=dict.fromkeys(verified_indirect_labels, 1.0),
        )
        self.verified.carried = verified_carried
        # Implements: REQ-d00069-L, REQ-d00069-M
        # The two measures record WHAT THE CITATION NAMED, and neither is
        # defined in terms of the other: a journey naming the *Assertion*
        # credits only the direct measure, a journey naming the requirement
        # credits only the indirect one. Each carries the journey's verified
        # fraction verbatim rather than flattened to 1.0 -- immediate coverage
        # records the STRENGTH of the evidence attached, and a partially
        # verified journey is partial evidence (REQ-d00255-C). Where both kinds
        # of journey reach one *Assertion*, ``total_by_label`` takes the
        # per-label maximum; folding that maximum INTO the indirect measure
        # would make it report direct credit under the whole-requirement word.
        self.uat_verified = CoverageDimension(
            total=n,
            has_failures=uat_verified_failures,
            failing_labels=set(uat_verified_failing_labels or ()),
            immediate_direct_by_label={
                lbl: f for lbl, f in uat_verified_direct_pct.items() if f > 0
            },
            immediate_indirect_by_label={
                lbl: f for lbl, f in uat_verified_indirect_pct.items() if f > 0
            },
        )


# ──────────────────────────────────────────────────────────────────────────
# Inherited-coverage query helpers (CUR-1353 Phase 5 / REQ-p00014-K)
# ──────────────────────────────────────────────────────────────────────────


# Implements: REQ-p00014-K
def direct_coverage_for(node: GraphNode) -> int:
    """Count coverage-contributing evidence for ``node``.

    The edge model used by the builder wires IMPLEMENTS/VERIFIES/VALIDATES
    edges as **outgoing** from the parent REQUIREMENT to CODE/TEST/JNY
    nodes, carrying ``assertion_targets`` to scope the coverage to a
    subset of the parent's assertions. So a node's "direct coverage" is
    not just its inbound edges -- for an ASSERTION we have to walk the
    parent REQ's outgoing coverage edges and count those whose
    ``assertion_targets`` contains this assertion's label (or is empty,
    meaning whole-REQ blanket coverage).

    For non-ASSERTION nodes, the direction matters and is dispatched by
    :class:`NodeKind`:

    - ``REQUIREMENT`` / ``STEP``: count only **outgoing** coverage edges
      (REQ -> CODE/TEST/JNY and STEP -> TEST are the outgoing convention;
      a STEP owns its verifying tests as outgoing VERIFIES edges).
    - All other kinds (``CODE``, ``TEST``, ``FILE``, ``JOURNEY``, ...):
      count only **incoming** coverage edges -- i.e. the evidence
      *received* by this node. This avoids miscounting an outgoing
      IMPLEMENTS edge from a CODE node as "the CODE node being covered".

    Args:
        node: Any graph node.

    Returns:
        The count of coverage-contributing evidence for this node.
    """
    from elspais.graph.GraphNode import NodeKind

    if node.kind == NodeKind.ASSERTION:
        label = node.get_field("label")
        count = 0
        for parent in node.iter_parents():
            if parent.kind != NodeKind.REQUIREMENT:
                continue
            for edge in parent.iter_outgoing_edges():
                if not edge.kind.contributes_to_coverage():
                    continue
                # Edge with no assertion_targets covers all assertions (blanket).
                # Edge with assertion_targets covers only those labels.
                if not edge.assertion_targets or label in edge.assertion_targets:
                    count += 1
        return count

    if node.kind in (NodeKind.REQUIREMENT, NodeKind.STEP):
        # REQ -> CODE/TEST/JNY and STEP -> TEST are the outgoing convention.
        return sum(1 for e in node.iter_outgoing_edges() if e.kind.contributes_to_coverage())

    # CODE, TEST, FILE, JOURNEY, ... -- count incoming evidence-of-coverage edges.
    return sum(1 for e in node.iter_incoming_edges() if e.kind.contributes_to_coverage())


# Implements: REQ-p00014-K
def inherited_coverage_for(node: GraphNode) -> int:
    """Return coverage for ``node``, inheriting from the template if INSTANCE.

    For an ``INSTANCE`` node, walks the outbound ``INSTANCE`` edge to find
    the template original and returns *that* node's
    :func:`direct_coverage_for` count. For any other node, returns
    ``direct_coverage_for(node)`` unchanged.

    This implements the "instance coverage == template coverage" invariant
    without persisting a derived metric on the INSTANCE node: it stays a
    query over the live graph, so the answer is always consistent with
    the current state of the template's inbound IMPLEMENTS/VERIFIES edges.

    Args:
        node: Any graph node.

    Returns:
        The inherited or direct coverage count.
    """
    from elspais.graph.relations import EdgeKind, Stereotype

    if node.get_field("stereotype") != Stereotype.INSTANCE:
        return direct_coverage_for(node)
    for edge in node.iter_outgoing_edges():
        if edge.kind == EdgeKind.INSTANCE:
            return direct_coverage_for(edge.target)
    return 0


@dataclass(frozen=True)
class SatisfierRollup:
    """Result of :func:`satisfier_rollup`.

    Attributes:
        covered: Number of assertions (own + template) with coverage > 0.
        total: Total assertions counted (own concrete + cloned template).
    """

    covered: int
    total: int

    @property
    def covered_fraction(self) -> float:
        """Fraction in ``[0, 1]``; ``0.0`` when ``total == 0``."""
        return self.covered / self.total if self.total else 0.0


# Implements: REQ-p00014-K
def satisfier_rollup(node: GraphNode) -> SatisfierRollup:
    """Combine a satisfier REQ's own and inherited coverage.

    Walks two layers:

    1. Own concrete-assertion coverage: every STRUCTURES child that is
       an ASSERTION with :func:`direct_coverage_for` > 0.
    2. Inherited template coverage: for each outbound ``SATISFIES`` edge
       (declaring REQ -> cloned root), walk that clone's STRUCTURES
       children (the instance assertions), and count each whose
       :func:`inherited_coverage_for` is > 0.

    The denominator is ``len(own_assertions) + len(template_assertions)``,
    so a satisfier that adds its own assertion *on top of* a fully
    covered template only reports full coverage once that own assertion
    is also covered. This makes satisfier-specific work visible without
    discarding the cross-cutting evidence the template already provides.

    Args:
        node: A satisfier REQUIREMENT node (declaring `Satisfies:`).

    Returns:
        A :class:`SatisfierRollup` with combined counts and fraction.
    """
    from elspais.graph.GraphNode import NodeKind
    from elspais.graph.relations import EdgeKind

    own_assertions = [
        c
        for c in node.iter_children(edge_kinds={EdgeKind.STRUCTURES})
        if c.kind == NodeKind.ASSERTION
    ]
    own_covered = sum(1 for a in own_assertions if direct_coverage_for(a) > 0)

    satisfied_clones = [
        e.target for e in node.iter_outgoing_edges() if e.kind == EdgeKind.SATISFIES
    ]
    template_assertions: list[GraphNode] = []
    for clone in satisfied_clones:
        for ce in clone.iter_outgoing_edges():
            if ce.kind == EdgeKind.STRUCTURES and ce.target.kind == NodeKind.ASSERTION:
                template_assertions.append(ce.target)
    template_covered = sum(1 for a in template_assertions if inherited_coverage_for(a) > 0)

    total = len(own_assertions) + len(template_assertions)
    covered = own_covered + template_covered
    return SatisfierRollup(covered=covered, total=total)


@dataclass(frozen=True)
class IntegratesRollup:
    """Coverage/passing status a consumer REQ inherits across INTEGRATES edges.

    Derived live by reading each library child's own persisted RollupMetrics.
    Nothing is persisted on the consumer node -- the INTEGRATES edge is the
    provenance (REQ-d00252-D).
    """

    # Covered counts are summed from per-dimension coverage, which is now a
    # sum of fractional per-assertion values (REQ-d00069-J), so they may be
    # non-integer. Totals are assertion counts and stay int.
    implemented_covered: float
    implemented_total: int
    # NOTE (REQ-d00258-N): the field name is kept for MCP/GUI wire
    # compatibility (see `integrates_rollup()`); the value is the Passing
    # dimension from `tested_and_passing()`, which counts what the library's
    # own declared tests returned and excludes an assertion any of them
    # failed.
    verified_covered: float
    verified_total: int
    # True if any integrated library node's Passing dimension reports a
    # failure. A failing assertion is excluded from the covered figure rather
    # than counted, but the figure alone cannot distinguish "failed" from
    # "never tested", so every surface showing covered/total must surface this
    # flag too (REQ-d00258-N).
    has_failures: bool = False

    @property
    def has_integrations(self) -> bool:
        return self.implemented_total > 0


# Implements: REQ-d00252
def has_integration(node: GraphNode) -> bool:
    """True if ``node`` delegates implementation via at least one INTEGRATES edge.

    This is the binary "implemented-via-integration / not-a-gap" predicate used by
    coverage surfaces (summary classification, gaps exclusion, health) so an
    integrating consumer requirement is not reported as an uncovered gap
    (REQ-d00252-F). It is intentionally cheap -- the federation rollup ratios come
    from :func:`integrates_by_associate` / :func:`integrates_total`.
    """
    from elspais.graph.relations import EdgeKind

    return any(e.kind == EdgeKind.INTEGRATES for e in node.iter_outgoing_edges())


# Implements: REQ-d00252
def integrates_rollup(node: GraphNode) -> IntegratesRollup:
    """Inherit implemented/passing status from library nodes via INTEGRATES.

    For each outgoing INTEGRATES edge (consumer REQ -> library node), read the
    library node's finalized ``rollup_metrics`` (computed in its own repo) and
    fold its implemented and Passing dimensions in. "Passing" is
    :func:`tested_and_passing` (REQ-d00258-N): what the library's own declared
    tests returned, with a failing assertion excluded. A consumer REQ with no
    INTEGRATES edges yields all zeros.
    """
    from elspais.graph.relations import EdgeKind

    impl_c = impl_t = ver_c = ver_t = 0
    fails = False
    for edge in node.iter_outgoing_edges():
        if edge.kind != EdgeKind.INTEGRATES:
            continue
        metrics = edge.target.get_metric("rollup_metrics")
        if metrics is None:
            continue
        impl_c += metrics.implemented.covered
        impl_t += metrics.implemented.total
        passing = tested_and_passing(metrics)
        ver_c += passing.covered
        ver_t += passing.total
        fails = fails or passing.has_failures
    return IntegratesRollup(
        implemented_covered=impl_c,
        implemented_total=impl_t,
        verified_covered=ver_c,
        verified_total=ver_t,
        has_failures=fails,
    )


@dataclass(frozen=True)
class AssociateIntegration:
    """Per-associate rollup of requirements integrating that associate."""

    associate: str  # owning associate repo name
    requirement_count: int  # distinct consumer requirements integrating it
    # Covered counts may be fractional (sums of per-assertion coverage,
    # REQ-d00069-J); totals are assertion counts and stay int.
    implemented_covered: float
    implemented_total: int
    # NOTE (REQ-d00258-N): the "verified" field name is kept for MCP/summary
    # wire compatibility; the value is the Passing dimension
    # (`tested_and_passing()`), which excludes a failing assertion.
    verified_covered: float
    verified_total: int
    # True if any integrated library node under this associate reports a
    # failing result -- the covered figure alone cannot say whether an
    # uncounted assertion failed or was never tested (see IntegratesRollup).
    has_failures: bool = False


# Implements: REQ-d00252
def integrates_by_associate(graph) -> list[AssociateIntegration]:
    """Summarize Integrates inheritance grouped by owning associate (REQ-d00252-F).

    Scans every INTEGRATES edge in the federation (consumer REQ -> library REQ),
    groups by the owning associate repo of the target library node, and sums the
    inherited implemented coverage plus the Passing dimension (REQ-d00258-N,
    `tested_and_passing()`), read live from each target's ``rollup_metrics``. Returns one entry per
    associate, sorted by associate name. A federation total is the caller's
    concern (see :func:`integrates_total`). ``graph`` is a FederatedGraph.
    """
    from elspais.graph.GraphNode import NodeKind
    from elspais.graph.relations import EdgeKind

    # Per-associate accumulators.
    consumers: dict[str, set[str]] = {}
    impl_c: dict[str, int] = {}
    impl_t: dict[str, int] = {}
    ver_c: dict[str, int] = {}
    ver_t: dict[str, int] = {}
    fails: dict[str, bool] = {}

    for req in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        for edge in req.iter_outgoing_edges():
            if edge.kind != EdgeKind.INTEGRATES:
                continue
            target = edge.target
            # Resolve the owning associate robustly: prefer repo_for(), fall
            # back to the ownership map, skip if neither resolves.
            owner: str | None
            try:
                owner = graph.repo_for(target.id).name
            except KeyError:
                owner = None  # node not owned by any repo -> skip
            except AttributeError:
                owner = getattr(graph, "_ownership", {}).get(target.id)
            if owner is None:
                continue

            consumers.setdefault(owner, set()).add(req.id)
            impl_c.setdefault(owner, 0)
            impl_t.setdefault(owner, 0)
            ver_c.setdefault(owner, 0)
            ver_t.setdefault(owner, 0)
            fails.setdefault(owner, False)

            metrics = target.get_metric("rollup_metrics")
            if metrics is None:
                continue
            impl_c[owner] += metrics.implemented.covered
            impl_t[owner] += metrics.implemented.total
            passing = tested_and_passing(metrics)
            ver_c[owner] += passing.covered
            ver_t[owner] += passing.total
            fails[owner] = fails[owner] or passing.has_failures

    return [
        AssociateIntegration(
            associate=name,
            requirement_count=len(consumers[name]),
            implemented_covered=impl_c[name],
            implemented_total=impl_t[name],
            verified_covered=ver_c[name],
            verified_total=ver_t[name],
            has_failures=fails[name],
        )
        for name in sorted(consumers)
    ]


# Implements: REQ-d00252
def integrates_total(items: list[AssociateIntegration]) -> AssociateIntegration:
    """Aggregate per-associate integration rows into a federation total.

    Returns an :class:`AssociateIntegration` with ``associate="total"`` whose
    fields are the field-wise sums of ``items`` (REQ-d00252-F federation total).
    ``requirement_count`` sums the per-associate distinct-consumer counts, so a
    consumer integrating two associates contributes to both.
    """
    return AssociateIntegration(
        associate="total",
        requirement_count=sum(i.requirement_count for i in items),
        implemented_covered=sum(i.implemented_covered for i in items),
        implemented_total=sum(i.implemented_total for i in items),
        verified_covered=sum(i.verified_covered for i in items),
        verified_total=sum(i.verified_total for i in items),
        has_failures=any(i.has_failures for i in items),
    )


# Implements: REQ-d00254-B
# Implements: REQ-d00258-N
def tested_and_passing(metrics: RollupMetrics) -> CoverageDimension:
    """The Passing dimension: what the declared tests themselves returned.

    An *Assertion* passes when a test declared against it returned a passing
    result and none returned a failure (REQ-d00258-N). Line coverage is not
    consulted. Executing a line of the code that implements an *Assertion*
    says the code was reached; it does not say the *Assertion* was checked,
    and a test can always carry its own `Verifies:`, so an *Assertion*
    reported as passing without one would be reporting an annotation nobody
    wrote. ``lcov_tested`` remains its own dimension, reported beside these
    (REQ-d00254-B).

    A failing *Assertion* contributes to no measure here, and the record that
    it failed survives in ``failing_labels`` -- which is what a per-*Assertion*
    standing reads first (REQ-d00258-G), so it still renders under its own
    standing rather than disappearing.

    The name is kept because every reporting surface reaches Passing through
    it, and there is one place to change if what Passing counts changes again.
    """
    vd = metrics.verified
    failing = set(vd.failing_labels)

    # Implements: REQ-d00069-L, REQ-d00258-N
    # The four measures come through with the failing assertions removed, the
    # same exclusion the scalar sums above apply: these maps ARE the Passing
    # figures now, and an *Assertion* whose declared test returned a failure
    # does not pass (REQ-d00258-N). The failure itself is not lost -- it is
    # carried in ``failing_labels``, which is what a standing reads first
    # (REQ-d00258-G).
    def _passing_only(by_label: dict[str, float]) -> dict[str, float]:
        return {lbl: frac for lbl, frac in by_label.items() if lbl not in failing}

    return CoverageDimension(
        total=vd.total,
        has_failures=vd.has_failures,
        failing_labels=failing,
        carried=vd.carried,
        immediate_direct_by_label=_passing_only(vd.immediate_direct_by_label),
        immediate_indirect_by_label=_passing_only(vd.immediate_indirect_by_label),
        rolled_direct_by_label=_passing_only(vd.rolled_direct_by_label),
        rolled_indirect_by_label=_passing_only(vd.rolled_indirect_by_label),
    )


# Implements: REQ-d00258-O
@dataclass(frozen=True)
class TestedPartition:
    """The tested assertions of one requirement, by what came back.

    Every tested *Assertion* is in exactly one of the three, so the counts sum
    to ``tested``. Passing alone would leave the remainder ambiguous: an
    *Assertion* missing from it either failed or never returned a verdict, and
    those ask for opposite things of a reader.

    Counts assertions rather than fractional credit. A partially-credited
    *Assertion* is still one *Assertion*, and it is the *Assertion* that
    passed, failed, or is waiting.
    """

    passed: int
    failed: int
    awaiting: int

    @property
    def tested(self) -> int:
        return self.passed + self.failed + self.awaiting


# Implements: REQ-d00258-O
def tested_partition(metrics: RollupMetrics) -> TestedPartition:
    """Partition a requirement's tested assertions into the three states.

    The tested set is read on the per-*Assertion* total (REQ-d00069-N),
    matching the Tested figure this breaks down (REQ-d00258-A). An *Assertion*
    is failing when a test
    declared against it reported a failure, passing when such a test reported a
    pass and none reported a failure, and awaiting a result otherwise --
    which covers a test that has not run, one whose results were never
    ingested, and one that returned no verdict.
    """
    tested_labels = {lbl for lbl, frac in metrics.tested.total_by_label.items() if frac > 0}
    passing = tested_and_passing(metrics)
    passing_by_label = passing.total_by_label
    failed = tested_labels & set(passing.failing_labels)
    passed = {lbl for lbl in tested_labels - failed if passing_by_label.get(lbl, 0.0) > 0}
    return TestedPartition(
        passed=len(passed),
        failed=len(failed),
        awaiting=len(tested_labels) - len(failed) - len(passed),
    )


__all__ = [
    "AssociateIntegration",
    "TestedPartition",
    "CoverageDimension",
    "CoverageSource",
    "CoverageContribution",
    "IntegratesRollup",
    "LineCoverage",
    "RollupMetrics",
    "SatisfierRollup",
    "direct_coverage_for",
    "fmt_assertion_count",
    "tested_partition",
    "has_integration",
    "inherited_coverage_for",
    "integrates_by_associate",
    "integrates_rollup",
    "integrates_total",
    "satisfier_rollup",
    "tested_and_passing",
]
